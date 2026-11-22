"""Testes da 2.0: criptografia, migração, 2FA, funil de serviços, turmas, compras, push, backup e administração.

Rodar:  python3 -m unittest tests.test_producao -v
"""
import base64
import contextlib
import hashlib
import hmac
import io
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cripto  # noqa: E402
import migracoes  # noqa: E402
import pagamentos  # noqa: E402
import push  # noqa: E402
import s3  # noqa: E402
import server  # noqa: E402
from test_api import Base, cfg_teste  # noqa: E402

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    TEM_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover
    TEM_CRYPTOGRAPHY = False


# ===================================================================== primitivas
class TestCripto(unittest.TestCase):
    def test_01_chacha20_poly1305_rfc8439(self):
        # RFC 8439, seção 2.8.2
        k = bytes(range(0x80, 0xA0))
        n = bytes.fromhex("070000004041424344454647")
        aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
        pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, "
              b"sunscreen would be it.")
        out = cripto.aead_cifrar(k, n, pt, aad, puro=True)
        self.assertEqual(out[:16].hex(), "d31a8d34648e60db7b86afbc53ef7ec2")
        self.assertEqual(out[-16:].hex(), "1ae10b594f09e26a7e902ecbd0600691")
        self.assertEqual(cripto.aead_decifrar(k, n, out, aad, puro=True), pt)
        with self.assertRaises(ValueError):
            cripto.aead_decifrar(k, n, out[:-1] + bytes([out[-1] ^ 1]), aad, puro=True)

    def test_02_poly1305_rfc8439(self):
        chave = bytes.fromhex("85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b")
        self.assertEqual(cripto.poly1305(chave, b"Cryptographic Forum Research Group").hex(), "a8061dc1305136c6c22b8baf0c0127a9")

    @unittest.skipUnless(TEM_CRYPTOGRAPHY, "pacote cryptography ausente")
    def test_03_igual_a_biblioteca_cryptography(self):
        import os
        for tam in (0, 1, 63, 64, 65, 1000):
            k, n, pt, aad = os.urandom(32), os.urandom(12), os.urandom(tam), os.urandom(tam % 7)
            self.assertEqual(cripto.aead_cifrar(k, n, pt, aad, puro=True), ChaCha20Poly1305(k).encrypt(n, pt, aad or None))

    def test_04_totp_rfc6238(self):
        seg = b"12345678901234567890"
        for t, esperado in ((59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924"), (2000000000, "69279037")):
            self.assertEqual(cripto.hotp(seg, t // 30, 8), esperado)
        b32 = base64.b32encode(seg).decode()
        agora = 1_700_000_000
        cod = cripto.totp(b32, agora)
        c = cripto.confere_totp(b32, cod, 0, agora)
        self.assertTrue(c)
        self.assertEqual(cripto.confere_totp(b32, cod, c, agora), 0, "o mesmo código não pode entrar duas vezes")
        self.assertTrue(cripto.confere_totp(b32, cripto.totp(b32, agora - 30), 0, agora), "aceita 30 s de atraso do relógio")
        self.assertEqual(cripto.confere_totp(b32, cripto.totp(b32, agora - 120), 0, agora), 0)

    @unittest.skipUnless(TEM_CRYPTOGRAPHY, "pacote cryptography ausente")
    def test_05_es256_conferido_pela_cryptography(self):
        d, pub = cripto.nova_chave_ec()
        self.assertTrue(cripto.no_curva(pub))
        msg = b"agora"
        sig = cripto.assinar_es256(d, msg)
        pk = serialization.load_der_public_key(cripto.spki_der_p256(pub))
        pk.verify(utils.encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")), msg, ec.ECDSA(hashes.SHA256()))
        self.assertTrue(cripto.verificar_es256(pub, msg, sig))
        self.assertFalse(cripto.verificar_es256(pub, b"outra", sig))

    def test_06_cofre_rotacao_e_arquivo(self):
        k1, k2 = bytes(32), bytes([1]) * 32
        c1 = cripto.Cofre(k1)
        v = c1.cifrar("diário: dormi mal", "nuvem")
        self.assertTrue(v.startswith("c1."))
        self.assertNotIn("dormi", v)
        with self.assertRaises(ValueError):
            c1.decifrar(v, "snapshot")  # contexto errado não abre
        c2 = cripto.Cofre(k2, [k1])
        self.assertEqual(c2.decifrar(v, "nuvem"), "diário: dormi mal")
        self.assertTrue(c2.precisa_recifrar(v))
        self.assertEqual(c2.decifrar("texto antigo em claro"), "texto antigo em claro")
        with tempfile.TemporaryDirectory() as t:
            orig, cif, volta = Path(t) / "a", Path(t) / "b", Path(t) / "c"
            orig.write_bytes(bytes(range(256)) * 9000)  # > 2 blocos
            c1.cifrar_arquivo(orig, cif, bloco=1 << 20)
            c2.decifrar_arquivo(cif, volta)
            self.assertEqual(orig.read_bytes(), volta.read_bytes())
            dados = bytearray(cif.read_bytes())
            dados[100] ^= 1
            cif.write_bytes(bytes(dados))
            with self.assertRaises(ValueError):
                c1.decifrar_arquivo(cif, Path(t) / "d")

    def test_07_sigv4_chave_de_assinatura_aws(self):
        # vetor da documentação da AWS ("Deriving the signing key")
        k = s3.chave_assinatura("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20120215", "us-east-1", "iam")
        self.assertEqual(k.hex(), "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d")

    def test_08_sigv4_exemplo_get_object_aws(self):
        # exemplo GET Object da documentação do S3 (Signature Version 4, com cabeçalho Range)
        cab = s3.assinar("GET", "https://examplebucket.s3.amazonaws.com/test.txt", "us-east-1", "AKIAIOSFODNN7EXAMPLE",
                         "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", hashlib.sha256(b"").hexdigest(),
                         agora=datetime(2013, 5, 24, tzinfo=timezone.utc), extra={"range": "bytes=0-9"})
        self.assertIn("Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request", cab["authorization"])
        self.assertIn("SignedHeaders=host;range;x-amz-content-sha256;x-amz-date", cab["authorization"])
        self.assertTrue(cab["authorization"].endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))


# ===================================================================== migração da 1.3
class TestMigracao(unittest.TestCase):
    def test_banco_da_versao_1_3_e_cifrado_na_partida(self):
        with tempfile.TemporaryDirectory() as t:
            db = str(Path(t) / "velho.db")
            con = sqlite3.connect(db)
            con.executescript(server.ESQUEMA)  # esquema 1.x, user_version 0
            con.execute("INSERT INTO usuarios(email,nome,papel,senha_hash,criado_em) VALUES ('a@t.br','A','paciente',?,?)",
                        (server.hash_senha("senha-forte"), server.agora_iso()))
            con.execute("INSERT INTO nuvem VALUES (1, ?, ?)", (json.dumps({"tasks": [{"t": "segredo de saúde"}]}), server.agora_iso()))
            con.execute("INSERT INTO pedidos_contato(paciente_id,motivo,criado_em) VALUES (1,'estou mal',?)", (server.agora_iso(),))
            con.commit()
            con.close()
            api = server.API(server.Banco(db), cfg_teste())
            self.assertEqual(api.db.versao, migracoes.VERSAO_ATUAL)
            self.assertEqual(api.cifrados_na_partida, 2)
            bruto = sqlite3.connect(db).execute("SELECT dados FROM nuvem").fetchone()[0]
            self.assertTrue(bruto.startswith("c1."))
            self.assertNotIn("segredo", bruto)
            self.assertEqual(json.loads(api.decifra(bruto, "nuvem"))["tasks"][0]["t"], "segredo de saúde")
            # segunda partida: nada a fazer, nada quebra
            api2 = server.API(server.Banco(db), cfg_teste())
            self.assertEqual(api2.cifrados_na_partida, 0)
            self.assertEqual(sqlite3.connect(db).execute("PRAGMA user_version").fetchone()[0], migracoes.VERSAO_ATUAL)


# ===================================================================== API
class Producao(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ebooks = Path(cls.tmp.name) / "ebooks"
        cls.ebooks.mkdir()
        (cls.ebooks / "tdah-no-trabalho.pdf").write_bytes(b"%PDF-1.4\n% amostra\n")
        cls.cfg.ebooks_dir = str(cls.ebooks)

    def admin(self, email="adm@t.br"):
        tok = self.conta(email, "profissional", "Admin")
        self.sql("UPDATE usuarios SET admin=1 WHERE email=?", (email,))
        s, j = self.req("/api/admin/resumo", token=tok)
        self.assertEqual((s, j.get("precisa2faAtivar")), (403, True), "admin sem 2FA não entra")
        seg = self.req("/api/2fa/iniciar", {}, token=tok)[1]["segredo"]
        s, j = self.req("/api/2fa/ativar", {"codigo": cripto.totp(seg)}, token=tok)
        self.assertEqual(s, 200, j)
        return tok, seg, j["recuperacao"]

    def pagar_simulado(self, url, resultado="aprovado"):
        ck = parse_qs(urlparse(url).query)["c"][0]
        s, j = self.req("/api/pagamentos/simulado/confirmar", {"checkout": ck, "resultado": resultado})
        self.assertEqual(s, 200, j)
        return ck, j


class TestSeguranca(Producao):
    def test_01_health_completo(self):
        s, j = self.req("/api/health")
        self.assertEqual(s, 200)
        self.assertEqual(j["banco"]["migracao"], migracoes.VERSAO_ATUAL)
        self.assertIn(j["cifra"], ("cryptography", "python"))

    def test_02_dois_fatores_ponta_a_ponta(self):
        tok = self.conta("2fa@t.br", "profissional")
        s, j = self.req("/api/2fa/ativar", {"codigo": "123456"}, token=tok)
        self.assertEqual(s, 400)
        seg = self.req("/api/2fa/iniciar", {}, token=tok)[1]["segredo"]
        self.assertEqual(self.req("/api/2fa/ativar", {"codigo": "000000"}, token=tok)[0], 400)
        s, j = self.req("/api/2fa/ativar", {"codigo": cripto.totp(seg)}, token=tok)
        self.assertEqual((s, len(j["recuperacao"])), (200, 8))
        guardado = self.sql("SELECT totp_segredo, totp_rec FROM usuarios WHERE email='2fa@t.br'")[0]
        self.assertTrue(guardado["totp_segredo"].startswith("c1."), "segredo TOTP cifrado no banco")
        self.assertNotIn(j["recuperacao"][0], guardado["totp_rec"], "códigos de recuperação só como hash")
        s, j2 = self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte"})
        self.assertEqual((s, j2.get("precisa2fa")), (401, True))
        self.assertNotIn("token", j2)
        self.assertEqual(self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte", "codigo": "111111"})[0], 401)
        self.sql("UPDATE usuarios SET totp_ultimo=0 WHERE email='2fa@t.br'")
        s, j3 = self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte", "codigo": cripto.totp(seg)})
        self.assertEqual(s, 200, j3)
        self.assertEqual(self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte", "codigo": cripto.totp(seg)})[0], 401,
                         "mesmo código não serve duas vezes")
        rec = j["recuperacao"][0]
        self.assertEqual(self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte", "codigo": rec})[0], 200)
        self.assertEqual(self.req("/api/entrar", {"email": "2fa@t.br", "senha": "senha-forte", "codigo": rec})[0], 401, "recuperação é de uso único")
        self.assertTrue(self.req("/api/eu", token=j3["token"])[1]["doisFatores"])

    def test_03_limite_persiste_entre_reinicios(self):
        self.conta("lim@t.br")
        for _ in range(5):
            self.req("/api/entrar", {"email": "lim@t.br", "senha": "errada!!"})
        self.assertEqual(self.req("/api/entrar", {"email": "lim@t.br", "senha": "senha-forte"})[0], 429)
        outra = server.API(server.Banco(self.db), self.cfg, self.http)  # "reinício" do processo
        with self.assertRaises(server.ErroAPI) as e:
            outra.entrar({"email": "lim@t.br", "senha": "senha-forte"}, ip="127.0.0.1")
        self.assertEqual(e.exception.status, 429)

    def test_04_cabecalhos_csp_e_estaticos(self):
        import urllib.request
        with urllib.request.urlopen(self.url + "/app/") as r:
            csp = r.headers["Content-Security-Policy"]
            html = r.read().decode()
        self.assertIn("script-src 'self' 'sha256-", csp)
        self.assertNotIn("unsafe-inline' ;", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        import re
        for corpo in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
            h = base64.b64encode(hashlib.sha256(corpo.encode()).digest()).decode()
            self.assertIn(h, csp)
        for pagina in ("/app/", "/app/pro.html", "/app/admin.html", "/app/checkout-simulado.html", "/", "/servicos", "/comecar"):
            with urllib.request.urlopen(self.url + pagina) as r:
                self.assertNotRegex(r.read().decode(), r'\son[a-z]+="', f"{pagina}: manipulador inline quebra a CSP")
        with urllib.request.urlopen(self.url + "/api/health") as r:
            self.assertIn("default-src 'none'", r.headers["Content-Security-Policy"])
            self.assertIsNone(r.headers.get("Strict-Transport-Security"), "HSTS só em produção")

    def test_05_nuvem_cifrada_e_conflito(self):
        tok = self.conta("nv@t.br")
        uid = self.uid("nv@t.br")
        self.sql("INSERT INTO assinaturas(usuario_id,plano,direito,provedor,status,fim_periodo,criado_em,atualizado_em) "
                 "VALUES (?,?,?,?,?,?,?,?)", (uid, "plus_anual", "plus", "cortesia", "ativa", "2099-01-01T00:00:00+00:00", "x", "x"))
        s, j = self.req("/api/nuvem", {"dados": {"tasks": [{"t": "consulta sexta"}], "preparo": {"trabalhar": "rascunho privado"}}}, token=tok)
        self.assertEqual((s, j["versao"]), (200, 1))
        self.assertNotIn("preparo", self.req("/api/nuvem", token=tok)[1]["dados"])
        self.assertNotIn("consulta", self.sql("SELECT dados FROM nuvem WHERE usuario_id=?", (uid,))[0]["dados"])
        self.assertEqual(self.req("/api/nuvem", {"dados": {"a": 1}, "versao_base": 1}, token=tok)[1]["versao"], 2)
        s, j = self.req("/api/nuvem", {"dados": {"a": 2}, "versao_base": 1}, token=tok)  # aparelho atrasado
        self.assertEqual((s, j["conflito"], j["versao"]), (409, True, 2))
        self.assertEqual(self.req("/api/nuvem", {"dados": {"a": 3}, "versao_base": 1, "forcar": True}, token=tok)[1]["versao"], 3)
        s, j = self.req("/api/nuvem", token=tok)
        self.assertEqual((j["dados"], j["versao"]), ({"a": 3}, 3))

    def test_06_snapshot_e_pedido_cifrados_e_link_de_convite(self):
        pro = self.conta("pro-c@t.br", "profissional")
        s, c = self.req("/api/pro/convite", {}, token=pro)
        self.assertTrue(c["link"].endswith("/app/?convite=" + c["codigo"]))
        pac = self.conta("pac-c@t.br")
        self.req("/api/paciente/vincular", {"codigo": c["codigo"], "consentimento": {"checkins": True}}, token=pac)
        self.req("/api/paciente/sync", {"dados": {"checkins": {"2026-11-10": {"mood": 2}}, "notes": "privado"}}, token=pac)
        self.req("/api/paciente/contato", {"motivo": "semana difícil"}, token=pac)
        self.assertTrue(self.sql("SELECT dados FROM snapshots")[0]["dados"].startswith("c1."))
        self.assertNotIn("difícil", self.sql("SELECT motivo FROM pedidos_contato")[0]["motivo"])
        pid = self.uid("pac-c@t.br")
        s, ficha = self.req(f"/api/pro/pacientes/{pid}", token=pro)
        self.assertEqual(ficha["dados"]["checkins"]["2026-11-10"]["mood"], 2)
        self.assertNotIn("notes", ficha["dados"])
        self.assertEqual(ficha["pedidos"][0]["motivo"], "semana difícil")

    def test_07_erro_interno_registrado_sem_vazar(self):
        original = self.api.health
        self.api.health = lambda **_: 1 / 0
        try:
            s, j = self.req("/api/health")
        finally:
            self.api.health = original
        self.assertEqual(s, 500)
        self.assertNotIn("ZeroDivision", j["erro"])
        self.assertEqual(self.sql("SELECT tipo FROM erros ORDER BY id DESC LIMIT 1")[0]["tipo"], "ZeroDivisionError")


class TestFunil(Producao):
    def test_01_catalogo_por_contexto(self):
        s, web = self.req("/api/catalogo")
        ids = {i["id"] for i in web["itens"]}
        self.assertIn("ths-tdah", ids)
        self.assertNotIn("mentoria", ids, "mentoria de carreira não aparece no app")
        self.assertNotIn("plus", ids)
        for i in web["itens"]:
            if i["psicologico"]:
                self.assertEqual(i["responsavel"]["crp"], self.cfg.responsavel_crp)
            for palavra in ("desconto", "promoção", "garantido", "novos pacientes"):
                self.assertNotIn(palavra, json.dumps(i, ensure_ascii=False).lower())
        self.assertEqual(next(i for i in web["itens"] if i["id"] == "ths-tdah")["marcaNome"], "Lume")
        s, andr = self.req("/api/catalogo", cab={"X-Agora-Plataforma": "android"})
        a_ids = {i["id"] for i in andr["itens"]}
        self.assertIn("terapia", a_ids)
        self.assertNotIn("ebooks", a_ids, "Play: produto digital fora do faturamento do Google não aparece")
        self.assertNotIn("ths-tdah", a_ids, "Play: turma não é atendimento individual ao vivo")
        pro = self.conta("pro-f@t.br", "profissional")
        c = self.req("/api/pro/convite", {}, token=pro)[1]["codigo"]
        pac = self.conta("pac-f@t.br")
        self.req("/api/paciente/vincular", {"codigo": c, "consentimento": {}}, token=pac)
        s, v = self.req("/api/catalogo", token=pac)
        self.assertTrue(v["vinculado"])
        self.assertFalse([i for i in v["itens"] if i["psicologico"]], "vinculado não vê serviço psicológico de terceiros")

    def test_02_interesse_cifrado_sequencia_e_descadastro(self):
        self.assertEqual(self.req("/api/interesse", {"item": "terapia", "nome": "R", "email": "robo@t.br", "aceite": True, "site": "http://spam"})[0], 200)
        self.assertFalse(self.sql("SELECT 1 FROM interesses WHERE email='robo@t.br'"), "armadilha de robô não grava")
        self.assertEqual(self.req("/api/interesse", {"item": "nao-existe", "nome": "A", "email": "a@t.br", "aceite": True})[0], 400)
        self.assertEqual(self.req("/api/interesse", {"item": "terapia", "nome": "A", "email": "a@t.br"})[0], 400, "sem aceite não grava")
        s, j = self.req("/api/interesse", {"item": "terapia", "nome": "Ana Lima", "email": "ana@t.br", "mensagem": "ansiedade no trabalho",
                                           "aceite": True, "marketing": True, "origem": "site-servicos"})
        self.assertEqual(s, 200, j)
        r = self.sql("SELECT * FROM interesses WHERE email='ana@t.br'")[0]
        self.assertNotIn("ansiedade", r["mensagem"])
        caixa = [dict(x) for x in self.sql("SELECT para, assunto, texto FROM caixa_saida")]
        conf = next(x for x in caixa if x["para"] == "ana@t.br")
        self.assertIn("188", conf["texto"])
        self.assertIn(self.cfg.responsavel_crp, conf["texto"])
        self.sql("UPDATE sequencias SET proximo_em='2000-01-01' WHERE email='ana@t.br'")
        self.assertEqual(self.api.enviar_sequencias(), 1)
        email = self.sql("SELECT texto FROM caixa_saida WHERE para='ana@t.br' ORDER BY id DESC LIMIT 1")[0]["texto"]
        link = next(l for l in email.split() if "/api/descadastrar" in l)
        caminho = link.replace(self.cfg.url_publica, "")
        s, html = self.req(caminho.replace("t=", "t=x"), cru=True)
        self.assertIn("inválido", html.decode())
        s, html = self.req(caminho, cru=True)
        self.assertIn("Pronto", html.decode())
        self.assertEqual(self.sql("SELECT descadastrado FROM sequencias WHERE email='ana@t.br'")[0][0], 1)
        self.assertEqual(self.api.enviar_sequencias(), 0)

    def test_03_eventos_anonimos(self):
        self.assertTrue(self.req("/api/eventos", {"nome": "ver_servicos", "origem": "app"})[1]["ok"])
        self.assertFalse(self.req("/api/eventos", {"nome": "humor_baixo"})[1]["ok"], "só eventos da lista")
        cols = {r[1] for r in sqlite3.connect(self.db).execute("PRAGMA table_info(eventos_funil)")}
        self.assertIn("usuario_id", cols)
        self.assertFalse(self.sql("SELECT 1 FROM eventos_funil WHERE usuario_id IS NOT NULL"))

    def test_04_turma_pagamento_missoes_espera_e_estorno(self):
        adm, _, _ = self.admin("adm-t@t.br")
        s, j = self.req("/api/admin/turmas", {"item": "ths-tdah", "nome": "Turma teste", "inicio": "2099-03-03", "vagas": 1,
                                               "link": "https://meet.exemplo/abc"}, token=adm)
        self.assertEqual(s, 200, j)
        tid = j["id"]
        self.assertEqual(len(self.sql("SELECT * FROM missoes WHERE turma_id=?", (tid,))), 8)
        t = next(x for x in self.req("/api/turmas?item=ths-tdah")[1]["turmas"] if x["id"] == tid)
        self.assertEqual((t["restam"], t["preco"]), (1, 72000))
        self.assertNotIn("link", t, "link da sala só para confirmados")
        a = self.conta("aluno1@t.br")
        self.assertEqual(self.req(f"/api/turmas/{tid}/inscrever", {}, token=a, cab={"X-Agora-Plataforma": "android"})[0], 403)
        s, j = self.req(f"/api/turmas/{tid}/inscrever", {}, token=a)
        self.assertEqual(j["status"], "pendente")
        self.pagar_simulado(j["url"], "pix")
        s, m = self.req("/api/minhas", token=a)
        turma = m["turmas"][0]
        self.assertEqual((turma["minha"], turma["link"], len(turma["missoes"])), ("confirmada", "https://meet.exemplo/abc", 8))
        self.assertEqual(m["compras"][0]["status"], "paga")
        mid = turma["missoes"][0]["id"]
        self.assertEqual(self.req(f"/api/missoes/{mid}/feita", {"nota": "falei na reunião"}, token=a)[0], 200)
        self.assertNotIn("reunião", self.sql("SELECT nota FROM missoes_feitas")[0]["nota"])
        self.assertTrue(self.req("/api/minhas", token=a)[1]["turmas"][0]["missoes"][0]["feita"])
        b = self.conta("aluno2@t.br")
        self.assertEqual(self.req(f"/api/turmas/{tid}/inscrever", {}, token=b)[1]["status"], "espera")
        intruso = self.conta("intruso@t.br")
        self.assertEqual(self.req(f"/api/missoes/{mid}/feita", {}, token=intruso)[0], 404)
        compra = self.req("/api/admin/compras", token=adm)[1]["compras"][0]
        s, j = self.req(f"/api/admin/compras/{compra['id']}/estornar", {"motivo": "desistência"}, token=adm)
        self.assertEqual((s, j["resultado"]), (200, "compra estornada"), j)
        self.assertEqual(self.req("/api/minhas", token=a)[1]["turmas"], [])
        aviso = self.sql("SELECT assunto FROM caixa_saida WHERE para='aluno2@t.br' ORDER BY id DESC LIMIT 1")[0]["assunto"]
        self.assertIn("Abriu vaga", aviso)
        self.assertEqual(self.req(f"/api/admin/compras/{compra['id']}/estornar", {}, token=adm)[0], 400, "não estorna duas vezes")

    def test_05_ebook_compra_e_download_assinado(self):
        u = self.conta("leitor@t.br")
        pid = "item:ebooks:tdah-no-trabalho"
        self.assertEqual(self.req("/api/produtos/comprar", {"produto": pid}, token=u, cab={"X-Agora-Plataforma": "android"})[0], 403)
        self.assertEqual(self.req("/api/pagamentos/checkout", {"plano": pid}, token=u)[0], 400, "produto não passa pelo checkout de planos")
        self.assertEqual(self.req("/api/ebook/link?item=ebooks:tdah-no-trabalho", token=u)[0], 404)
        s, j = self.req("/api/produtos/comprar", {"produto": pid}, token=u)
        self.assertEqual(s, 200, j)
        self.pagar_simulado(j["url"])
        self.assertEqual(self.req("/api/produtos/comprar", {"produto": pid}, token=u)[0], 409)
        s, j = self.req("/api/ebook/link?item=ebooks:tdah-no-trabalho", token=u)
        self.assertEqual(s, 200, j)
        s, pdf = self.req(j["url"], cru=True)
        self.assertEqual((s, pdf[:5]), (200, b"%PDF-"))
        self.assertEqual(self.req(j["url"].replace("&u=", "&u=9"), cru=True)[0], 403, "link é da pessoa")
        q = parse_qs(urlparse(j["url"]).query)
        vencido = self.api.assina_link("ebook", q["i"][0], q["u"][0], validade=-10)
        self.assertEqual(self.req(f"/api/ebook/baixar?i={q['i'][0]}&u={q['u'][0]}&t={vencido}", cru=True)[0], 403)

    def test_06_sessao_no_android_e_vinculado_bloqueado(self):
        u = self.conta("sessao@t.br")
        s, j = self.req("/api/produtos/comprar", {"produto": "item:terapia"}, token=u, cab={"X-Agora-Plataforma": "android"})
        self.assertEqual(s, 200, "atendimento individual ao vivo pode ser vendido fora do Google Play")
        self.pagar_simulado(j["url"])
        self.assertEqual(self.req("/api/minhas", token=u)[1]["compras"][0]["entrega"], "sessao")
        self.assertEqual(self.req("/api/produtos/comprar", {"produto": "item:ths-tdah"}, token=u)[0], 400)

    def test_07_avulso_pelo_stripe(self):
        u = self.conta("stripe-av@t.br")
        api = server.API(server.Banco(self.db), cfg_teste(provedor="stripe"), self.http)
        self.http.quando("POST", "/checkout/sessions", 200, {"id": "cs_av", "url": "https://checkout.stripe.com/av"})
        r = api.produto_comprar(corpo={"produto": "item:opc"}, cab={"Authorization": "Bearer " + u})
        corpo = self.http.chamadas[-1][3]
        self.assertIn("mode=payment", corpo)
        self.assertIn("unit_amount%5D=22000", corpo)
        ev = json.dumps({"id": "evt_av", "type": "checkout.session.completed", "data": {"object": {
            "mode": "payment", "payment_status": "paid", "client_reference_id": r["checkout"], "amount_total": 22000, "payment_intent": "pi_av"}}}).encode()
        ts = str(int(time.time()))
        sig = hmac.new(b"whsec_teste", ts.encode() + b"." + ev, hashlib.sha256).hexdigest()
        res = api.webhook_stripe(cab={"Stripe-Signature": f"t={ts},v1={sig}"}, query={}, bruto=ev)
        self.assertIn("compra registrada", res["resultados"][0])
        self.assertEqual(self.sql("SELECT status, valor FROM compras WHERE ref_pagamento='pi_av'")[0][:], ("paga", 22000))

    def test_08_admin_catalogo_veta_publicidade_irregular(self):
        adm, seg, rec = self.admin("adm-c@t.br")
        s, j = self.req("/api/admin/catalogo", {"item": "terapia", "resumo": "Primeira sessão com desconto"}, token=adm)
        self.assertEqual(s, 400)
        self.assertIn("desconto", j["erro"])
        s, j = self.req("/api/admin/catalogo", {"item": "ths-tech", "preco": 80000, "ativo": True}, token=adm)
        self.assertEqual((s, j["item"]["venda"]["valor"]), (200, 80000))
        self.assertEqual(next(i for i in self.req("/api/catalogo")[1]["itens"] if i["id"] == "ths-tech")["preco"], 80000)
        self.assertEqual(self.req("/api/admin/catalogo", {"item": "ths-tech", "ativo": False}, token=adm)[0], 200)
        self.assertNotIn("ths-tech", {i["id"] for i in self.req("/api/catalogo")[1]["itens"]})
        self.req("/api/admin/catalogo", {"item": "ths-tech", "ativo": True}, token=adm)
        comum = self.conta("comum@t.br")
        self.assertEqual(self.req("/api/admin/resumo", token=comum)[0], 403)
        s, r = self.req("/api/admin/resumo", token=adm)
        self.assertEqual(s, 200)
        for k in ("usuarios", "funil30", "receita30", "recorrenteMensal", "interessesNovos", "meta"):
            self.assertIn(k, r)

    def test_09_push_lembrete_vapid(self):
        priv, pub = push.gerar_chaves()
        self.cfg.vapid_privada, self.cfg.vapid_publica = priv, pub
        try:
            u = self.conta("push@t.br")
            self.assertEqual(self.req("/api/push/chave")[1]["chave"], pub)
            sub = {"endpoint": "https://push.exemplo.com/send/abc", "keys": {"p256dh": "BPx", "auth": "segredo-auth"}}
            self.assertEqual(self.req("/api/push/inscrever", {"inscricao": sub}, token=u)[0], 200)
            s, j = self.req("/api/push/lembretes", {"lembretes": [{"hora": "08:30", "texto": "Check-in do dia", "dias": [1, 2, 3, 4, 5]},
                                                                    {"hora": "99:00"}], "fuso": "America/Sao_Paulo"}, token=u)
            self.assertEqual(len(j["lembretes"]), 1)
            self.http.quando("POST", "push.exemplo.com", 201, {})
            n = len(self.http.chamadas)
            seg_feira = datetime(2026, 11, 16, 11, 30, tzinfo=timezone.utc)  # 08:30 em Brasília
            self.assertEqual(self.api.disparar_lembretes(seg_feira), 1)
            self.assertEqual(self.api.disparar_lembretes(seg_feira), 0, "não repete no mesmo minuto")
            self.assertEqual(self.api.disparar_lembretes(datetime(2026, 11, 15, 11, 30, tzinfo=timezone.utc)), 0, "domingo fora da lista")
            metodo, url, cab, corpo = self.http.chamadas[n]
            self.assertEqual((metodo, url, corpo), ("POST", sub["endpoint"], b""))
            jwt = cab["Authorization"].split("t=")[1].split(",")[0]
            h, c, a = jwt.split(".")
            claims = json.loads(cripto.de_b64u(c))
            self.assertEqual(claims["aud"], "https://push.exemplo.com")
            pubpt = cripto.de_b64u(pub)
            ponto = (int.from_bytes(pubpt[1:33], "big"), int.from_bytes(pubpt[33:], "big"))
            self.assertTrue(cripto.verificar_es256(ponto, f"{h}.{c}".encode(), cripto.de_b64u(a)))
            self.assertEqual(self.req("/api/push/pendentes", {"endpoint": sub["endpoint"], "auth": "errado"})[0], 403)
            s, j = self.req("/api/push/pendentes", {"endpoint": sub["endpoint"], "auth": "segredo-auth"})
            self.assertEqual(j["mensagens"][0]["corpo"], "Check-in do dia")
            self.assertEqual(self.req("/api/push/pendentes", {"endpoint": sub["endpoint"], "auth": "segredo-auth"})[1]["mensagens"], [])
            self.http.quando("POST", "push.exemplo.com", 410, {})
            self.api.disparar_lembretes(datetime(2026, 11, 17, 11, 30, tzinfo=timezone.utc))
            self.assertFalse(self.sql("SELECT 1 FROM push_inscricoes"), "inscrição expirada (410) é apagada")
        finally:
            self.cfg.vapid_privada = self.cfg.vapid_publica = ""

    def test_10_retencao_e_exclusao(self):
        u = self.conta("ret@t.br")
        self.req("/api/interesse", {"item": "terapia", "nome": "Ret", "email": "ret@t.br", "aceite": True, "marketing": True}, token=u)
        self.sql("INSERT INTO interesses(item_id,nome,email,criado_em,atualizado_em) VALUES ('aula','Velho','velho@t.br','2000-01-01','2000-01-01')")
        r = self.api.aplicar_retencao()
        self.assertGreaterEqual(r["interesses"], 1)
        self.assertFalse(self.sql("SELECT 1 FROM interesses WHERE email='velho@t.br'"))
        s, exp = self.req("/api/conta/exportar", token=u)
        self.assertEqual(exp["interesses"][0]["item_id"], "terapia")
        self.assertEqual(self.req("/api/conta/excluir", {"senha": "senha-forte"}, token=u)[0], 200)
        self.assertFalse(self.sql("SELECT 1 FROM interesses WHERE email='ret@t.br'"))
        self.assertFalse(self.sql("SELECT 1 FROM sequencias WHERE email='ret@t.br'"))


class TestOperacao(unittest.TestCase):
    def test_backup_cifrado_restaura_e_envia_para_s3(self):
        import backup
        with tempfile.TemporaryDirectory() as t:
            db = str(Path(t) / "agora.db")
            cfg = cfg_teste(s3_bucket="meu-bucket", s3_endpoint="https://s3.exemplo.com", s3_chave="AK", s3_segredo="SK", s3_regiao="us-east-1")
            api = server.API(server.Banco(db), cfg)
            api.registrar({"email": "b@t.br", "senha": "senha-forte", "nome": "B"})
            enviados = []

            class Resp:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            def abrir_falso(req, timeout=0):
                enviados.append(req)
                return Resp()

            orig = backup.s3.enviar
            backup.s3.enviar = lambda c, arq, nome: orig(c, arq, nome, abrir=abrir_falso)
            try:
                r = backup.fazer(db, Path(t) / "bk", 5, cfg=cfg)
            finally:
                backup.s3.enviar = orig
            self.assertTrue(r["arquivo"].endswith(".cifrado"))
            self.assertEqual(r["remoto"], "s3://meu-bucket/" + Path(r["arquivo"]).name)
            self.assertNotIn(b"b@t.br", Path(r["arquivo"]).read_bytes())
            self.assertFalse(list((Path(t) / "bk").glob("*.tmp")), "cópia em claro apagada")
            req = enviados[0]
            self.assertEqual(req.get_method(), "PUT")
            self.assertTrue(req.full_url.startswith("https://s3.exemplo.com/meu-bucket/agora-"))
            self.assertIn("AWS4-HMAC-SHA256 Credential=AK/", req.headers["Authorization"])
            volta = backup.restaurar(r["arquivo"], Path(t) / "restaurado.db", cfg=cfg)
            self.assertEqual(volta["usuarios"], 1)
            with self.assertRaises(ValueError):
                backup.restaurar(r["arquivo"], Path(t) / "outra.db", cfg=cfg_teste(chave=cripto.nova_chave_texto()))

    def test_admin_cli(self):
        import admin
        with tempfile.TemporaryDirectory() as t:
            db = str(Path(t) / "a.db")
            import os
            os.environ["AGORA_CHAVE"] = cripto.nova_chave_texto()
            try:
                api = server.API(server.Banco(db), cfg_teste(chave=os.environ["AGORA_CHAVE"]))
                api.registrar({"email": "dono@t.br", "senha": "senha-forte", "nome": "Dono", "papel": "profissional"})
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    admin.main(["promover", "dono@t.br", "--db", db])
                    admin.main(["chave"])
                    admin.main(["vapid"])
                    admin.main(["estado", "--db", db])
                txt = out.getvalue()
                self.assertIn("administrador", txt)
                self.assertIn("AGORA_CHAVE=", txt)
                self.assertIn("AGORA_VAPID_PUBLICA=", txt)
                self.assertEqual(sqlite3.connect(db).execute("SELECT admin FROM usuarios").fetchone()[0], 1)
            finally:
                os.environ.pop("AGORA_CHAVE", None)

    def test_producao_exige_cryptography(self):
        import cripto as cr
        original = cr._CC20
        cr._CC20 = None
        try:
            with tempfile.TemporaryDirectory() as t:
                with self.assertRaises(SystemExit) as e:
                    server.API(server.Banco(str(Path(t) / "p.db")), cfg_teste(ambiente="producao", permitir_cifra_python=False))
                self.assertIn("cryptography", str(e.exception))
        finally:
            cr._CC20 = original

    def test_producao_recusa_sem_chave(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                server.API(server.Banco(str(Path(t) / "p.db")), cfg_teste(ambiente="producao", chave=""))


if __name__ == "__main__":
    unittest.main()
