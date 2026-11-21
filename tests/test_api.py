"""Testes da API do servidor (somente biblioteca padrão).  Rodar:  python3 -m unittest tests.test_api -v"""
import base64
import contextlib
import hashlib
import hmac
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import google_play  # noqa: E402
import pagamentos  # noqa: E402
import server  # noqa: E402
from config import Config  # noqa: E402


CHAVE_TESTE = base64.b64encode(bytes(range(32))).decode()


class HttpFalso:
    """Transporte HTTP falso: responde chamadas aos provedores a partir de um dicionário de rotas."""

    def __init__(self):
        self.rotas, self.chamadas = {}, []

    def quando(self, metodo, trecho, status, corpo):
        self.rotas[(metodo, trecho)] = (status, corpo)

    def __call__(self, metodo, url, cab=None, corpo=None, timeout=20):
        self.chamadas.append((metodo, url, cab, corpo))
        for (m, t), r in self.rotas.items():
            if m == metodo and t in url:
                return r() if callable(r) else r
        return 404, {"erro": "rota falsa ausente: " + url}


def cfg_teste(**extra):
    base = dict(url_publica="http://teste.local", ambiente="desenvolvimento", provedor="simulado", limite_registro=1000,
                mp_token="TEST-token", mp_segredo_webhook="segredo-mp", stripe_chave="sk_test_x", stripe_segredo_webhook="whsec_teste",
                play_token_rtdn="tok-rtdn", smtp_host="", atras_de_proxy=False, chave=CHAVE_TESTE, agendador=False, permitir_cifra_python=True,
                vapid_privada="", vapid_publica="", alerta_email="", exigir_2fa_admin=True)
    base.update(extra)
    return Config(**base)


class Base(unittest.TestCase):
    cfg_extra = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(Path(cls.tmp.name) / "t.db")
        cls.http = HttpFalso()
        cls.cfg = cfg_teste(**cls.cfg_extra)
        cls.api = server.API(server.Banco(cls.db), cls.cfg, cls.http)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.cria_handler(cls.api))
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def req(self, caminho, corpo=None, token=None, metodo=None, cru=False, cab=None, bruto=None):
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        r = urllib.request.Request(self.url + caminho, data=dados, method=metodo or ("POST" if dados is not None else "GET"))
        r.add_header("Content-Type", "application/json")
        for k, v in (cab or {}).items():
            r.add_header(k, v)
        if token:
            r.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(r) as resp:
                c = resp.read()
                return resp.status, (c if cru else json.loads(c or b"{}"))
        except urllib.error.HTTPError as e:
            c = e.read()
            if cru:
                return e.code, c
            try:
                return e.code, json.loads(c or b"{}")
            except ValueError:
                return e.code, {"html": c[:200]}

    def conta(self, email, papel="paciente", nome="Teste", senha="senha-forte"):
        s, j = self.req("/api/registrar", {"email": email, "senha": senha, "nome": nome, "papel": papel})
        self.assertEqual(s, 200, j)
        return j["token"]

    def sql(self, q, args=()):
        con = sqlite3.connect(self.db)
        con.row_factory = sqlite3.Row
        try:
            r = con.execute(q, args).fetchall()
            con.commit()
            return r
        finally:
            con.close()

    def uid(self, email):
        return self.sql("SELECT id FROM usuarios WHERE email=?", (email,))[0]["id"]


# ===================================================================== contas e clínica
class TestContas(Base):
    def test_01_health_e_planos(self):
        s, j = self.req("/api/health")
        self.assertEqual((s, j["ok"], j["versao"]), (200, True, server.VERSAO))
        s, j = self.req("/api/planos")
        self.assertEqual({p["id"] for p in j["planos"]}, {"plus_mensal", "plus_anual", "pro_mensal"})
        self.assertTrue(j["simulado"])

    def test_02_validacao_registro(self):
        self.assertEqual(self.req("/api/registrar", {"email": "x", "senha": "12345678", "nome": "a"})[0], 400)
        self.assertEqual(self.req("/api/registrar", {"email": "a@b.c", "senha": "123", "nome": "a"})[0], 400)
        self.assertEqual(self.req("/api/registrar", {"email": "a@b.c", "senha": "12345678", "nome": "a", "papel": "admin"})[0], 400)
        self.conta("dup@t.br")
        self.assertEqual(self.req("/api/registrar", {"email": "DUP@t.br", "senha": "senha-forte", "nome": "x"})[0], 409)

    def test_03_login_e_logout(self):
        self.conta("login@t.br")
        self.assertEqual(self.req("/api/entrar", {"email": "login@t.br", "senha": "errada!!"})[0], 401)
        s, j = self.req("/api/entrar", {"email": "login@t.br", "senha": "senha-forte"})
        self.assertEqual(s, 200)
        self.assertEqual(self.req("/api/eu", token=j["token"])[1]["email"], "login@t.br")
        self.assertEqual(self.req("/api/sair", {}, token=j["token"])[0], 200)
        self.assertEqual(self.req("/api/eu", token=j["token"])[0], 401)

    def test_04_limite_de_tentativas(self):
        self.conta("forca@t.br")
        for _ in range(5):
            self.assertEqual(self.req("/api/entrar", {"email": "forca@t.br", "senha": "chute-errado"})[0], 401)
        s, j = self.req("/api/entrar", {"email": "forca@t.br", "senha": "senha-forte"})
        self.assertEqual(s, 429, "a 6ª tentativa é bloqueada mesmo com a senha certa")
        self.assertIn("espera", j)
        self.api.lim.limpar("login:127.0.0.1:forca@t.br")
        self.assertEqual(self.req("/api/entrar", {"email": "forca@t.br", "senha": "senha-forte"})[0], 200)

    def test_05_senha_e_token_nao_ficam_em_claro(self):
        tok = self.conta("cripto@t.br")
        h = self.sql("SELECT senha_hash FROM usuarios WHERE email='cripto@t.br'")[0][0]
        self.assertTrue(h.startswith("pbkdf2$200000$"))
        self.assertNotIn("senha-forte", h)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tokens WHERE hash=?", (tok,))[0][0], 0)

    def test_06_recuperacao_de_senha(self):
        velho = self.conta("esqueci@t.br")
        s, j = self.req("/api/senha/esqueci", {"email": "esqueci@t.br"})
        self.assertEqual(s, 200)
        s2, j2 = self.req("/api/senha/esqueci", {"email": "ninguem@t.br"})
        self.assertEqual(j, j2, "a resposta não revela se o e-mail existe")
        texto = self.sql("SELECT texto FROM caixa_saida WHERE para='esqueci@t.br' ORDER BY id DESC")[0][0]
        tok = texto.split("redefinir=")[1].split()[0]
        self.assertEqual(self.req("/api/senha/redefinir", {"token": "falso", "senha": "nova-senha-1"})[0], 400)
        self.assertEqual(self.req("/api/senha/redefinir", {"token": tok, "senha": "curta"})[0], 400)
        self.assertEqual(self.req("/api/senha/redefinir", {"token": tok, "senha": "nova-senha-1"})[0], 200)
        self.assertEqual(self.req("/api/senha/redefinir", {"token": tok, "senha": "outra-senha-2"})[0], 400, "link de uso único")
        self.assertEqual(self.req("/api/eu", token=velho)[0], 401, "sessões antigas caem ao trocar a senha")
        self.assertEqual(self.req("/api/entrar", {"email": "esqueci@t.br", "senha": "nova-senha-1"})[0], 200)

    def test_07_papeis(self):
        pac = self.conta("pap@t.br")
        self.assertEqual(self.req("/api/pro/pacientes", token=pac)[0], 403)
        self.assertEqual(self.req("/api/pro/pacientes")[0], 401)
        pro = self.conta("pap-pro@t.br", "profissional")
        self.assertEqual(self.req("/api/paciente/sync", {"dados": {}}, token=pro)[0], 403)

    def test_08_fluxo_clinico_completo(self):
        pro = self.conta("ana@t.br", "profissional", "Dra. Ana")
        pac = self.conta("lu@t.br", "paciente", "Lucas")
        codigo = self.req("/api/pro/convite", {}, token=pro)[1]["codigo"]
        self.assertEqual(len(codigo), 6)
        self.assertEqual(self.req("/api/paciente/vincular", {"codigo": "ZZZZZZ"}, token=pac)[0], 404)
        cons = {"checkins": True, "foco": True, "rotinas": True, "tarefas": False, "triagem": True}
        s, eu = self.req("/api/paciente/vincular", {"codigo": codigo.lower(), "consentimento": cons}, token=pac)
        self.assertEqual(s, 200, eu)
        self.assertEqual(eu["vinculo"]["profissional"], "Dra. Ana")
        outro = self.conta("intruso@t.br")
        self.assertEqual(self.req("/api/paciente/vincular", {"codigo": codigo}, token=outro)[0], 404, "convite reutilizado")

        hoje = date.today().isoformat()
        dados = {"profile": {"name": "Lucas"}, "checkins": {hoje: {"mood": 2, "sleepH": 6, "activityMin": 30}},
                 "sessions": [{"date": hoje, "min": 25}], "tasks": [{"id": "t", "title": "segredo", "done": False, "steps": []}],
                 "courses": [{"id": "c", "name": "curso"}], "routines": [], "routineRuns": [{"date": hoje, "routineId": "r1", "done": 3, "total": 3}],
                 "screenings": [{"date": hoje, "positives": 4, "positive": True}], "notes": [{"text": "privado"}]}
        self.assertTrue(self.req("/api/paciente/sync", {"dados": dados}, token=pac)[1]["compartilhado"])
        lista = self.req("/api/pro/pacientes", token=pro)[1]["pacientes"]
        a = lista[0]["adesao7"]
        self.assertEqual((a["diasComCheckin"], a["minutosFoco"], a["rotinasConcluidas"], a["humorBaixoDias"]), (1, 25, 1, 1))
        pid = lista[0]["id"]
        det = self.req(f"/api/pro/pacientes/{pid}", token=pro)[1]
        self.assertNotIn("tasks", det["dados"], "tarefas não consentidas não chegam ao profissional")
        self.assertNotIn("courses", det["dados"])
        self.assertNotIn("notes", det["dados"])
        self.req("/api/paciente/consentimento", {"consentimento": dict(cons, checkins=False)}, token=pac)
        self.req("/api/paciente/sync", {"dados": dados}, token=pac)
        self.assertNotIn("checkins", self.req(f"/api/pro/pacientes/{pid}", token=pro)[1]["dados"])

        self.assertEqual(self.req(f"/api/pro/pacientes/{pid}/prescrever", {"tipo": "rotina", "conteudo": {"titulo": "x", "passos": []}}, token=pro)[0], 400)
        s, j = self.req(f"/api/pro/pacientes/{pid}/prescrever", {"tipo": "rotina", "conteudo": {
            "titulo": "Pausa", "horario": "15:00", "passos": [{"t": "Alongar", "min": 999}]}}, token=pro)
        presc = self.req("/api/paciente/sync", {"dados": dados}, token=pac)[1]["prescricoes"]
        self.assertEqual(presc[0]["conteudo"]["passos"][0]["min"], 120)
        self.req(f"/api/pro/prescricoes/{j['id']}/arquivar", {}, token=pro)
        self.assertEqual(self.req("/api/eu", token=pac)[1]["prescricoes"], [])
        pro2 = self.conta("outra@t.br", "profissional")
        self.assertEqual(self.req(f"/api/pro/pacientes/{pid}", token=pro2)[0], 404)
        self.assertTrue(self.req("/api/paciente/contato", {"motivo": "quero conversar"}, token=pac)[1]["encaminhado"])
        ped = self.req(f"/api/pro/pacientes/{pid}", token=pro)[1]["pedidos"][0]
        self.req(f"/api/pro/pedidos/{ped['id']}/visto", {}, token=pro)
        self.assertEqual(self.req("/api/pro/pacientes", token=pro)[1]["pacientes"][0]["pedidosContato"], 0)
        self.req("/api/paciente/desvincular", {}, token=pac)
        self.assertEqual(self.req("/api/pro/pacientes", token=pro)[1]["pacientes"], [])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM snapshots WHERE paciente_id=?", (pid,))[0][0], 0)

    def test_09_limite_do_plano_gratis_do_profissional(self):
        pro = self.conta("lim-pro@t.br", "profissional")
        for i in range(self.cfg.pro_gratis_pacientes):
            pac = self.conta(f"lim{i}@t.br")
            c = self.req("/api/pro/convite", {}, token=pro)[1]["codigo"]
            self.assertEqual(self.req("/api/paciente/vincular", {"codigo": c, "consentimento": {}}, token=pac)[0], 200)
        s, j = self.req("/api/pro/convite", {}, token=pro)
        self.assertEqual((s, j.get("recurso")), (402, "pro"))
        self.assertEqual(self.req("/api/pro/pacientes", token=pro)[1]["limitePacientes"], self.cfg.pro_gratis_pacientes)

    def test_10_exclusao_de_conta(self):
        tok = self.conta("sair@t.br")
        self.assertEqual(self.req("/api/conta/excluir", {"senha": "errada"}, token=tok)[0], 401)
        s, dados = self.req("/api/conta/exportar", token=tok)
        self.assertEqual((s, dados["conta"]["email"]), (200, "sair@t.br"))
        self.assertEqual(self.req("/api/conta/excluir", {"senha": "senha-forte"}, token=tok)[0], 200)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM usuarios WHERE email='sair@t.br'")[0][0], 0)
        self.assertEqual(self.req("/api/entrar", {"email": "sair@t.br", "senha": "senha-forte"})[0], 401)

    def test_11_estaticos_rotas_e_seguranca(self):
        s, c = self.req("/", cru=True)
        self.assertEqual(s, 200)
        self.assertIn(b"Uma coisa", c)
        s, c = self.req("/app/", cru=True)
        self.assertIn(b"Agora TDAH", c)
        for p in ("/app/pro.html", "/app/manifest.webmanifest", "/app/config.js", "/privacidade.html", "/termos.html",
                  "/excluir-conta.html", "/.well-known/assetlinks.json", "/termos"):
            self.assertEqual(self.req(p, cru=True)[0], 200, p)
        r = urllib.request.Request(self.url + "/pro.html")
        r.method = "GET"

        class SemRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            urllib.request.build_opener(SemRedir).open(r)
        except urllib.error.HTTPError as e:
            self.assertEqual((e.code, e.headers["Location"]), (301, "/app/pro.html"))
        for p in ("/../server/server.py", "/%2e%2e/server/server.py", "/app/../server/config.py", "/app/%2e%2e/server/config.py"):
            self.assertEqual(self.req(p, cru=True)[0], 404, p)
        self.assertEqual(self.req("/api/nao-existe")[0], 404)
        self.assertEqual(self.req("/api/entrar", bruto=b"{nao json")[0], 400)
        with urllib.request.urlopen(self.url + "/app/") as resp:
            self.assertEqual(resp.headers["X-Frame-Options"], "DENY")

    def test_12_cors_para_o_app_android(self):
        r = urllib.request.Request(self.url + "/api/health", method="OPTIONS", headers={"Origin": "https://localhost",
                                                                                      "Access-Control-Request-Method": "POST"})
        with urllib.request.urlopen(r) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "https://localhost")
        r = urllib.request.Request(self.url + "/api/health", headers={"Origin": "https://site-malicioso.com"})
        with urllib.request.urlopen(r) as resp:
            self.assertIsNone(resp.headers["Access-Control-Allow-Origin"])


# ===================================================================== pagamentos simulados e direitos
class TestPlanosSimulados(Base):
    def compra(self, tok, plano, resultado="aprovado", cab=None):
        s, j = self.req("/api/pagamentos/checkout", {"plano": plano}, token=tok, cab=cab)
        self.assertEqual(s, 200, j)
        self.assertTrue(j["url"].startswith("/app/checkout-simulado.html?c="))
        info = self.req("/api/pagamentos/simulado?c=" + j["checkout"])[1]
        self.assertEqual(info["plano"]["id"], plano)
        s2, r = self.req("/api/pagamentos/simulado/confirmar", {"checkout": j["checkout"], "resultado": resultado})
        self.assertEqual(s2, 200, r)
        return j["checkout"], r

    def test_01_plus_mensal_libera_recursos(self):
        tok = self.conta("plus@t.br")
        self.assertEqual(self.req("/api/nuvem", {"dados": {"x": 1}}, token=tok)[0], 402)
        self.assertEqual(self.req("/api/sala/entrar", {"minutos": 25}, token=tok)[0], 402)
        self.compra(tok, "plus_mensal")
        eu = self.req("/api/eu", token=tok)[1]
        self.assertTrue(eu["direitos"]["plus"])
        self.assertTrue(eu["assinaturas"][0]["recorrente"])
        self.assertEqual(self.req("/api/nuvem", {"dados": {"tasks": [1, 2]}}, token=tok)[0], 200)
        self.assertEqual(self.req("/api/nuvem", token=tok)[1]["dados"], {"tasks": [1, 2]})
        self.assertEqual(self.req("/api/sala/entrar", {"minutos": 25}, token=tok)[0], 200)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM pagamentos WHERE usuario_id=?", (self.uid("plus@t.br"),))[0][0], 1)

    def test_02_recusado_nao_libera(self):
        tok = self.conta("recusa@t.br")
        self.compra(tok, "plus_mensal", "recusado")
        self.assertFalse(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])

    def test_03_anual_soma_365_dias_e_acumula(self):
        tok = self.conta("anual@t.br")
        self.compra(tok, "plus_anual", "pix")
        ate1 = datetime.fromisoformat(self.req("/api/eu", token=tok)[1]["direitos"]["plus_ate"])
        self.assertAlmostEqual((ate1 - datetime.now(timezone.utc)).days, 364, delta=1)
        self.compra(tok, "plus_anual", "pix")
        ate2 = datetime.fromisoformat(self.req("/api/eu", token=tok)[1]["direitos"]["plus_ate"])
        self.assertAlmostEqual((ate2 - ate1).days, 365, delta=1, msg="segunda compra começa onde a primeira termina")
        s, j = self.req("/api/pagamentos/cancelar", {"assinatura": self.req("/api/eu", token=tok)[1]["assinaturas"][0]["id"]}, token=tok)
        self.assertEqual(s, 400, "anual não tem renovação para cancelar")

    def test_04_confirmar_duas_vezes_e_idempotente(self):
        tok = self.conta("idem@t.br")
        ck, r1 = self.compra(tok, "plus_anual", "pix")
        s, r2 = self.req("/api/pagamentos/simulado/confirmar", {"checkout": ck, "resultado": "pix"})
        self.assertEqual(r2["resultado"], "duplicado")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM assinaturas WHERE usuario_id=?", (self.uid("idem@t.br"),))[0][0], 1)

    def test_05_cancelar_mantem_ate_o_fim_e_expira(self):
        tok = self.conta("cancela@t.br")
        self.compra(tok, "plus_mensal")
        aid = self.req("/api/eu", token=tok)[1]["assinaturas"][0]["id"]
        s, j = self.req("/api/pagamentos/cancelar", {"assinatura": aid}, token=tok)
        self.assertEqual(s, 200)
        eu = self.req("/api/eu", token=tok)[1]
        self.assertTrue(eu["direitos"]["plus"], "continua até o fim do período pago")
        self.assertTrue(eu["assinaturas"][0]["cancelar_no_fim"])
        ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        self.sql("UPDATE assinaturas SET fim_periodo=? WHERE id=?", (ontem, aid))
        self.assertFalse(self.req("/api/eu", token=tok)[1]["direitos"]["plus"], "acabou o período, acabou o acesso")
        self.assertEqual(self.req("/api/nuvem", token=tok)[0], 402)

    def test_06_plano_errado_para_o_papel_e_android(self):
        pac = self.conta("papel-pac@t.br")
        self.assertEqual(self.req("/api/pagamentos/checkout", {"plano": "pro_mensal"}, token=pac)[0], 403)
        self.assertEqual(self.req("/api/pagamentos/checkout", {"plano": "inexistente"}, token=pac)[0], 400)
        s, j = self.req("/api/pagamentos/checkout", {"plano": "plus_mensal"}, token=pac, cab={"X-Agora-Plataforma": "android"})
        self.assertEqual(s, 403, "o app Android não vende assinatura fora do Google Play")

    def test_07_pro_libera_pacientes_ilimitados(self):
        pro = self.conta("pro-pago@t.br", "profissional")
        for i in range(self.cfg.pro_gratis_pacientes):
            pac = self.conta(f"pp{i}@t.br")
            c = self.req("/api/pro/convite", {}, token=pro)[1]["codigo"]
            self.req("/api/paciente/vincular", {"codigo": c, "consentimento": {}}, token=pac)
        self.assertEqual(self.req("/api/pro/convite", {}, token=pro)[0], 402)
        ck, _ = self.compra(pro, "pro_mensal")
        self.assertIn("/app/pro.html?pagamento=retorno", pagamentos.Simulado(self.cfg).urls(ck, pagamentos.planos(self.cfg)["pro_mensal"])["sucesso"])
        self.assertEqual(self.req("/api/pro/convite", {}, token=pro)[0], 200)
        self.assertIsNone(self.req("/api/pro/pacientes", token=pro)[1]["limitePacientes"])


class TestSimuladoEmProducao(Base):
    cfg_extra = {"ambiente": "producao"}

    def test_simulado_desligado_em_producao(self):
        tok = self.conta("prod@t.br")
        s, j = self.req("/api/pagamentos/checkout", {"plano": "plus_mensal"}, token=tok)
        self.assertEqual(s, 403)
        self.assertEqual(self.req("/api/pagamentos/simulado?c=qualquer")[0], 404)
        self.assertFalse(self.req("/api/planos")[1]["simulado"])


# ===================================================================== Mercado Pago
def assinatura_mp(segredo, data_id, req_id, ts=None):
    ts = str(ts or int(time.time()))
    manifesto = f"id:{data_id.lower()};request-id:{req_id};ts:{ts};"
    return f"ts={ts},v1={hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()}"


class TestMercadoPago(Base):
    cfg_extra = {"provedor": "mercadopago"}

    def webhook(self, corpo, data_id, assinatura=None, req_id="req-123"):
        cab = {"x-request-id": req_id, "x-signature": assinatura or assinatura_mp("segredo-mp", data_id, req_id)}
        return self.req(f"/api/webhooks/mercadopago?data.id={data_id}&type={corpo['type']}", bruto=json.dumps(corpo).encode(), cab=cab)

    def test_01_assinatura_mensal_ponta_a_ponta(self):
        tok = self.conta("mp@t.br")
        self.http.quando("POST", "/preapproval", 201, {"id": "PRE123", "init_point": "https://www.mercadopago.com.br/subscriptions/checkout?preapproval_id=PRE123", "status": "pending"})
        s, j = self.req("/api/pagamentos/checkout", {"plano": "plus_mensal"}, token=tok)
        self.assertEqual(s, 200, j)
        self.assertIn("mercadopago.com.br", j["url"])
        metodo, url, cab, corpo = self.http.chamadas[-1]
        self.assertEqual(cab["Authorization"], "Bearer TEST-token")
        self.assertEqual(corpo["auto_recurring"]["transaction_amount"], 9.9)
        self.assertEqual(corpo["external_reference"], j["checkout"])
        self.assertIn("/app/?pagamento=retorno", corpo["back_url"])

        prox = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        self.http.quando("GET", "/preapproval/PRE123", 200, {"id": "PRE123", "status": "authorized", "external_reference": j["checkout"],
                                                              "next_payment_date": prox})
        ev = {"id": 991, "type": "subscription_preapproval", "action": "updated", "data": {"id": "PRE123"}}
        self.assertEqual(self.webhook(ev, "PRE123", assinatura="ts=1,v1=errado")[0], 401, "assinatura falsa é recusada")
        s, r = self.webhook(ev, "PRE123")
        self.assertEqual((s, r["resultados"]), (200, ["assinatura ativa"]))
        self.assertEqual(self.webhook(ev, "PRE123")[1]["resultados"], ["duplicado"])
        d = self.req("/api/eu", token=tok)[1]["direitos"]
        self.assertTrue(d["plus"])
        self.assertGreater(datetime.fromisoformat(d["plus_ate"]), datetime.now(timezone.utc) + timedelta(days=32))

        # cobrança do mês seguinte (authorized_payment) estende o período
        prox2 = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        self.http.quando("GET", "/authorized_payments/AP1", 200, {"id": "AP1", "preapproval_id": "PRE123", "transaction_amount": 9.9,
                                                                   "payment": {"id": 555, "status": "approved"}})
        self.http.quando("GET", "/preapproval/PRE123", 200, {"id": "PRE123", "status": "authorized", "external_reference": j["checkout"],
                                                              "next_payment_date": prox2})
        s, r = self.webhook({"id": 992, "type": "subscription_authorized_payment", "action": "created", "data": {"id": "AP1"}}, "AP1")
        self.assertEqual(r["resultados"], ["assinatura ativa"])
        self.assertGreater(datetime.fromisoformat(self.req("/api/eu", token=tok)[1]["direitos"]["plus_ate"]), datetime.now(timezone.utc) + timedelta(days=60))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM pagamentos WHERE ref_externa='555'")[0][0], 1)

        # cancelamento pelo usuário chama a API e mantém até o fim
        self.http.quando("PUT", "/preapproval/PRE123", 200, {"id": "PRE123", "status": "cancelled"})
        aid = self.req("/api/eu", token=tok)[1]["assinaturas"][0]["id"]
        self.assertEqual(self.req("/api/pagamentos/cancelar", {"assinatura": aid}, token=tok)[0], 200)
        self.assertEqual(self.http.chamadas[-1][3], {"status": "cancelled"})
        self.assertTrue(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])

    def test_02_pix_anual_e_estorno(self):
        tok = self.conta("mp-pix@t.br")
        self.http.quando("POST", "/checkout/preferences", 201, {"id": "PREF1", "init_point": "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=PREF1"})
        j = self.req("/api/pagamentos/checkout", {"plano": "plus_anual"}, token=tok)[1]
        corpo = self.http.chamadas[-1][3]
        self.assertEqual((corpo["items"][0]["unit_price"], corpo["notification_url"]), (89.0, "http://teste.local/api/webhooks/mercadopago"))
        self.http.quando("GET", "/v1/payments/777", 200, {"id": 777, "status": "approved", "external_reference": j["checkout"],
                                                          "transaction_amount": 89.0, "payment_type_id": "bank_transfer"})
        s, r = self.webhook({"id": 1, "type": "payment", "action": "payment.created", "data": {"id": "777"}}, "777")
        self.assertTrue(r["resultados"][0].startswith("acesso liberado"))
        self.assertTrue(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])
        self.http.quando("GET", "/v1/payments/777", 200, {"id": 777, "status": "refunded", "external_reference": j["checkout"], "transaction_amount": 89.0})
        s, r = self.webhook({"id": 2, "type": "payment", "action": "payment.updated", "data": {"id": "777"}}, "777")
        self.assertEqual(r["resultados"], ["estornado"])
        self.assertFalse(self.req("/api/eu", token=tok)[1]["direitos"]["plus"], "estorno corta o acesso")

    def test_03_manifesto_igual_ao_sdk_oficial(self):
        # Mesmo algoritmo do WebhookSignatureValidator do SDK oficial (Node, mercadopago 3.x)
        ts, did, rid = "1704908010", "123456", "abc-req"
        man = f"id:{did};request-id:{rid};ts:{ts};"
        v1 = hmac.new(b"segredo-mp", man.encode(), hashlib.sha256).hexdigest()
        p = pagamentos.MercadoPago(self.cfg)
        p.verificar_webhook({"x-signature": f"ts={int(time.time())},v1=" + hmac.new(b"segredo-mp", f"id:{did};request-id:{rid};ts:{int(time.time())};".encode(), hashlib.sha256).hexdigest(),
                             "x-request-id": rid}, {"data.id": did}, b"{}")
        with self.assertRaises(pagamentos.ErroPag):
            p.verificar_webhook({"x-signature": f"ts={ts},v1={v1}", "x-request-id": rid}, {"data.id": did}, b"{}")  # antigo demais


# ===================================================================== Stripe
def assinatura_stripe(segredo, corpo, ts=None):
    ts = str(ts or int(time.time()))
    return f"t={ts},v1={hmac.new(segredo.encode(), ts.encode() + b'.' + corpo, hashlib.sha256).hexdigest()}"


class TestStripe(Base):
    cfg_extra = {"provedor": "stripe"}

    def evento(self, tipo, obj, eid):
        corpo = json.dumps({"id": eid, "type": tipo, "data": {"object": obj}}).encode()
        return self.req("/api/webhooks/stripe", bruto=corpo, cab={"Stripe-Signature": assinatura_stripe("whsec_teste", corpo)})

    def test_01_assinatura_renovacao_e_cancelamento(self):
        tok = self.conta("stripe@t.br")
        self.http.quando("POST", "/checkout/sessions", 200, {"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"})
        j = self.req("/api/pagamentos/checkout", {"plano": "plus_mensal"}, token=tok)[1]
        enviado = dict(x.split("=", 1) for x in self.http.chamadas[-1][3].split("&"))
        self.assertEqual(enviado["mode"], "subscription")
        self.assertEqual(enviado["line_items%5B0%5D%5Bprice_data%5D%5Brecurring%5D%5Binterval%5D"], "month")
        self.assertEqual(enviado["line_items%5B0%5D%5Bprice_data%5D%5Bunit_amount%5D"], "990")
        corpo = json.dumps({"id": "evt_x", "type": "x", "data": {"object": {}}}).encode()
        self.assertEqual(self.req("/api/webhooks/stripe", bruto=corpo, cab={"Stripe-Signature": "t=1,v1=00"})[0], 401)
        velho = assinatura_stripe("whsec_teste", corpo, ts=int(time.time()) - 3600)
        self.assertEqual(self.req("/api/webhooks/stripe", bruto=corpo, cab={"Stripe-Signature": velho})[0], 401, "fora da janela de 5 min")

        s, r = self.evento("checkout.session.completed", {"id": "cs_1", "mode": "subscription", "client_reference_id": j["checkout"],
                                                          "subscription": "sub_1", "customer": "cus_1"}, "evt_1")
        self.assertEqual(r["resultados"], ["assinatura ativa"])
        fim = int((datetime.now(timezone.utc) + timedelta(days=31)).timestamp())
        s, r = self.evento("invoice.paid", {"id": "in_1", "customer": "cus_1", "amount_paid": 990,
                                            "parent": {"subscription_details": {"subscription": "sub_1", "metadata": {"checkout": j["checkout"]}}},
                                            "lines": {"data": [{"period": {"end": fim}}]}}, "evt_2")
        self.assertEqual(r["resultados"], ["assinatura ativa"])
        self.assertEqual(self.evento("invoice.paid", {"id": "in_1", "subscription": "sub_1", "lines": {"data": []}}, "evt_2")[1]["resultados"], ["duplicado"])
        self.assertTrue(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])

        self.http.quando("POST", "/billing_portal/sessions", 200, {"url": "https://billing.stripe.com/p/session/1"})
        aid = self.req("/api/eu", token=tok)[1]["assinaturas"][0]["id"]
        self.assertIn("billing.stripe.com", self.req("/api/pagamentos/portal", {"assinatura": aid}, token=tok)[1]["url"])

        s, r = self.evento("invoice.payment_failed", {"id": "in_2", "subscription": "sub_1"}, "evt_3")
        self.assertEqual(r["resultados"], ["assinatura atrasada"])
        self.assertTrue(self.req("/api/eu", token=tok)[1]["direitos"]["plus"], "carência: acesso segue até o fim do período")
        s, r = self.evento("customer.subscription.deleted", {"id": "sub_1", "status": "canceled", "customer": "cus_1"}, "evt_4")
        self.assertEqual(r["resultados"], ["assinatura cancelada"])
        self.assertFalse(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])

    def test_02_pagamento_unico(self):
        tok = self.conta("stripe-ano@t.br")
        self.http.quando("POST", "/checkout/sessions", 200, {"id": "cs_2", "url": "https://checkout.stripe.com/c/pay/cs_2"})
        j = self.req("/api/pagamentos/checkout", {"plano": "plus_anual"}, token=tok)[1]
        s, r = self.evento("checkout.session.completed", {"id": "cs_2", "mode": "payment", "payment_status": "unpaid",
                                                          "client_reference_id": j["checkout"]}, "evt_10")
        self.assertEqual(r["resultados"], [], "Pix ainda não pago não libera")
        s, r = self.evento("checkout.session.async_payment_succeeded", {"id": "cs_2", "mode": "payment", "client_reference_id": j["checkout"],
                                                                        "amount_total": 8900, "payment_intent": "pi_2"}, "evt_11")
        self.assertTrue(r["resultados"][0].startswith("acesso liberado"))


# ===================================================================== Google Play
class TestGooglePlay(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pem = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                             capture_output=True, text=True, check=True).stdout
        cls.pem = pem
        cls.conta_srv = {"client_email": "agora@projeto.iam.gserviceaccount.com", "private_key": pem, "private_key_id": "k1",
                         "token_uri": "https://oauth2.googleapis.com/token"}
        cls.api._play = google_play.GooglePlay(cls.cfg, cls.http, cls.conta_srv)

    def test_01_jwt_rs256_valido(self):
        jwt = google_play.jwt_conta_servico(self.conta_srv, agora=1_700_000_000)
        cab, corpo, sig = jwt.split(".")
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(cab)))["alg"], "RS256")
        dados = json.loads(base64.urlsafe_b64decode(pad(corpo)))
        self.assertEqual((dados["iss"], dados["exp"] - dados["iat"]), (self.conta_srv["client_email"], 3600))
        n, e, _ = google_play.carregar_chave(self.pem)
        self.assertTrue(google_play.verificar_rs256(f"{cab}.{corpo}".encode(), base64.urlsafe_b64decode(pad(sig)), n, e))
        # confere com o OpenSSL
        with tempfile.TemporaryDirectory() as t:
            Path(t, "k.pem").write_text(self.pem)
            pub = subprocess.run(["openssl", "pkey", "-in", str(Path(t, "k.pem")), "-pubout"], capture_output=True, text=True, check=True).stdout
            Path(t, "pub.pem").write_text(pub)
            Path(t, "msg").write_bytes(f"{cab}.{corpo}".encode())
            Path(t, "sig").write_bytes(base64.urlsafe_b64decode(pad(sig)))
            r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(Path(t, "pub.pem")), "-signature", str(Path(t, "sig")), str(Path(t, "msg"))],
                               capture_output=True, text=True)
            self.assertIn("Verified OK", r.stdout)

    def test_02_compra_no_app_e_rtdn(self):
        tok = self.conta("play@t.br")
        uid = self.uid("play@t.br")
        fim = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
        self.http.quando("POST", "oauth2.googleapis.com/token", 200, {"access_token": "ya29.teste", "expires_in": 3600})
        resp = {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE", "acknowledgementState": "ACKNOWLEDGEMENT_STATE_PENDING",
                "lineItems": [{"productId": "agora_plus_mensal", "expiryTime": fim}],
                "externalAccountIdentifiers": {"obfuscatedExternalAccountId": google_play.conta_externa(uid)}}
        self.http.quando("GET", "subscriptionsv2/tokens/TOKEN-ABC", 200, resp)
        self.http.quando("POST", ":acknowledge", 200, {})
        s, j = self.req("/api/pagamentos/google-play", {"token": "TOKEN-ABC", "produto": "agora_plus_mensal"}, token=tok)
        self.assertEqual(s, 200, j)
        self.assertTrue(j["direitos"]["plus"])
        self.assertTrue(any(":acknowledge" in c[1] for c in self.http.chamadas), "compra nova é confirmada no Google")
        outro = self.conta("ladrao@t.br")
        self.assertEqual(self.req("/api/pagamentos/google-play", {"token": "TOKEN-ABC"}, token=outro)[0], 403, "token de outra conta")
        aid = self.req("/api/eu", token=tok)[1]["assinaturas"][0]["id"]
        self.assertEqual(self.req("/api/pagamentos/cancelar", {"assinatura": aid}, token=tok)[0], 400, "cancela-se no Play Store")

        # RTDN: assinatura expirou
        self.http.quando("GET", "subscriptionsv2/tokens/TOKEN-ABC", 200, dict(resp, subscriptionState="SUBSCRIPTION_STATE_EXPIRED",
                                                                                lineItems=[{"productId": "agora_plus_mensal", "expiryTime": "2020-01-01T00:00:00Z"}]))
        msg = {"message": {"messageId": "m1", "data": base64.b64encode(json.dumps({"subscriptionNotification": {
            "purchaseToken": "TOKEN-ABC", "subscriptionId": "agora_plus_mensal", "notificationType": 13}}).encode()).decode()}}
        self.assertEqual(self.req("/api/webhooks/google-play?token=errado", msg)[0], 401)
        s, r = self.req("/api/webhooks/google-play?token=tok-rtdn", msg)
        self.assertEqual((s, r["resultado"]), (200, "assinatura cancelada"))
        self.assertFalse(self.req("/api/eu", token=tok)[1]["direitos"]["plus"])


# ===================================================================== seed
class TestSeed(unittest.TestCase):
    def test_seed_idempotente(self):
        import seed_demo
        with tempfile.TemporaryDirectory() as t:
            db = str(Path(t) / "d.db")
            with contextlib.redirect_stdout(io.StringIO()):
                seed_demo.main(["--db", db])
                seed_demo.main(["--db", db])
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM vinculos WHERE ativo=1").fetchone()[0], 3)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM prescricoes").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM assinaturas WHERE provedor='cortesia'").fetchone()[0], 1)
            con.close()


if __name__ == "__main__":
    unittest.main()
