#!/usr/bin/env python3
"""Agora TDAH — servidor (somente biblioteca padrão do Python).

Rotas:
  /                 site público (pasta site/)
  /app/             app do paciente, painel do profissional e checkout (pasta app/)
  /api/...          API JSON (contas, vínculo, prescrições, pagamentos, webhooks,
                    catálogo de serviços, turmas, push e administração)

Banco de dados: SQLite num único arquivo. Configuração por variáveis de ambiente
ou arquivo .env (veja .env.example).

Uso:  python3 server.py [--porta 8765] [--host 127.0.0.1] [--db caminho/agora.db]
"""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalogo as cat  # noqa: E402
import cripto  # noqa: E402
import email_envio  # noqa: E402
import google_play  # noqa: E402
import migracoes  # noqa: E402
import pagamentos as pag  # noqa: E402
import push  # noqa: E402
from config import Config  # noqa: E402
from funil import Funil  # noqa: E402

VERSAO = "2.0.0"
RAIZ = Path(__file__).resolve().parent.parent
APP_DIR = RAIZ / "app"
SITE_DIR = RAIZ / "site"
PBKDF2_ITER = 200_000
TOKEN_VIDA = 60 * 60 * 24 * 30  # 30 dias
SALA_JANELA = 90  # segundos sem batimento = saiu da sala
MAX_CORPO = 2 * 1024 * 1024
RESET_VIDA = 60 * 60  # 1 hora

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, nome TEXT NOT NULL,
  papel TEXT NOT NULL CHECK (papel IN ('paciente','profissional')),
  senha_hash TEXT NOT NULL, criado_em TEXT NOT NULL,
  registro TEXT DEFAULT '', contato TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tokens (
  hash TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, expira INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS convites (
  codigo TEXT PRIMARY KEY, profissional_id INTEGER NOT NULL,
  criado_em TEXT NOT NULL, usado_por INTEGER
);
CREATE TABLE IF NOT EXISTS vinculos (
  paciente_id INTEGER NOT NULL, profissional_id INTEGER NOT NULL,
  consentimento TEXT NOT NULL, criado_em TEXT NOT NULL, ativo INTEGER DEFAULT 1,
  PRIMARY KEY (paciente_id, profissional_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
  paciente_id INTEGER PRIMARY KEY, dados TEXT NOT NULL, atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nuvem (
  usuario_id INTEGER PRIMARY KEY, dados TEXT NOT NULL, atualizado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prescricoes (
  id INTEGER PRIMARY KEY, profissional_id INTEGER NOT NULL, paciente_id INTEGER NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('rotina','tarefa','mensagem')),
  conteudo TEXT NOT NULL, criado_em TEXT NOT NULL, ativo INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pedidos_contato (
  id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL, profissional_id INTEGER,
  motivo TEXT, criado_em TEXT NOT NULL, visto INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sala (
  usuario_id INTEGER PRIMARY KEY, apelido TEXT, intencao TEXT,
  fim_previsto INTEGER, ultimo_batimento INTEGER
);
CREATE TABLE IF NOT EXISTS auditoria (
  id INTEGER PRIMARY KEY, quando TEXT, usuario_id INTEGER, acao TEXT, alvo TEXT
);
CREATE TABLE IF NOT EXISTS resets_senha (
  hash TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, expira INTEGER NOT NULL, usado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS caixa_saida (
  id INTEGER PRIMARY KEY, para TEXT, assunto TEXT, texto TEXT, criado_em TEXT
);
""" + pag.ESQUEMA_PAG

# Campos do snapshot que cada consentimento libera para o profissional.
CONSENT_CAMPOS = {
    "checkins": ["checkins"],
    "foco": ["sessions"],
    "rotinas": ["routines", "routineRuns"],
    "tarefas": ["tasks", "courses"],
    "triagem": ["screenings"],
}

_lock = threading.Lock()


def agora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_senha(senha, sal=None):
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), PBKDF2_ITER).hex()
    return f"pbkdf2${PBKDF2_ITER}${sal}${h}"


def confere_senha(senha, guardado):
    try:
        _, it, sal, h = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False


SENHA_FALSA = hash_senha("senha-que-ninguem-usa")  # mantém o tempo de resposta igual para e-mail inexistente


def h_token(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


class Banco:
    def __init__(self, caminho):
        self.caminho = str(caminho)
        con = self.con()
        con.executescript(ESQUEMA)
        con.commit()
        self.versao = migracoes.aplicar(con)
        con.close()

    def con(self):
        c = sqlite3.connect(self.caminho, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        return c


class ErroAPI(Exception):
    def __init__(self, status, msg, extra=None):
        super().__init__(msg)
        self.status, self.msg, self.extra = status, msg, extra or {}


class Limitador:
    """Limite de tentativas (janela deslizante) gravado no banco.

    Sobrevive a reinícios e vale para todos os processos que usam o mesmo arquivo,
    então reiniciar o serviço não zera a proteção contra adivinhação de senha."""

    def __init__(self, banco):
        self.db = banco

    def excedeu(self, chave, maximo, janela):
        agora = time.time()
        con = self.db.con()
        try:
            r = con.execute("SELECT COUNT(*) n, MIN(t) m FROM limites WHERE chave=? AND t>?", (chave, agora - janela)).fetchone()
        finally:
            con.close()
        if r["n"] >= maximo:
            return int(r["m"] + janela - agora) + 1
        return 0

    def marcar(self, chave):
        con = self.db.con()
        con.execute("INSERT INTO limites VALUES (?,?)", (chave, time.time()))
        con.commit()
        con.close()

    def limpar(self, chave):
        con = self.db.con()
        con.execute("DELETE FROM limites WHERE chave=?", (chave,))
        con.commit()
        con.close()


def filtra_snapshot(dados, consentimento):
    out = {"profile": {"name": dados.get("profile", {}).get("name", "")}}
    for chave, liberado in consentimento.items():
        if liberado:
            for campo in CONSENT_CAMPOS.get(chave, []):
                if campo in dados:
                    out[campo] = dados[campo]
    out["_sharedAt"] = dados.get("_sharedAt")
    return out


def resumo_adesao(dados, dias=7):
    """Indicadores de adesão dos últimos N dias a partir do snapshot filtrado."""
    hoje = date.today()
    datas = {(hoje - timedelta(days=i)).isoformat() for i in range(dias)}
    checkins = dados.get("checkins") or {}
    sess = dados.get("sessions") or []
    ck = [checkins[d] for d in datas if d in checkins]
    foco = sum(s.get("min", 0) for s in sess if s.get("date") in datas)
    humor = [c.get("mood") for c in ck if c.get("mood")]
    sono = [c.get("sleepH") for c in ck if c.get("sleepH") is not None]
    ativ = [c.get("activityMin") or 0 for c in ck]
    runs = [r for r in (dados.get("routineRuns") or []) if r.get("date") in datas and r.get("done", 1)]
    return {
        "diasComCheckin": len(ck),
        "minutosFoco": foco,
        "humorMedio": round(sum(humor) / len(humor), 1) if humor else None,
        "sonoMedio": round(sum(sono) / len(sono), 1) if sono else None,
        "atividadeTotal": sum(ativ),
        "rotinasConcluidas": len(runs),
        "humorBaixoDias": sum(1 for h in humor if h <= 2),
    }


class API(Funil):
    def __init__(self, banco, cfg=None, http=None):
        self.db = banco
        self.cfg = cfg or Config()
        self.http = http  # transporte HTTP dos provedores (testes injetam um falso)
        self.http_push = http or pag.Http()
        self.lim = Limitador(banco)
        self._play = None
        self.cofre = self.cfg.cofre(Path(banco.caminho).resolve().parent)
        con = banco.con()
        try:
            self.cifrados_na_partida = migracoes.cifrar_legado(con, self.cofre)
            con.commit()
        finally:
            con.close()
        self.catalogo = cat.Catalogo(self.cfg, banco)
        self.ROTAS = {**API.ROTAS, **Funil.ROTAS_FUNIL}

    def erro(self, status, msg, extra=None):
        raise ErroAPI(status, msg, extra)

    def cifra(self, texto, ctx):
        return self.cofre.cifrar(texto, ctx)

    def decifra(self, valor, ctx):
        return self.cofre.decifrar(valor, ctx)

    def usuario_opcional(self, cab):
        try:
            return self.usuario(cab) if (cab.get("Authorization") or "").startswith("Bearer ") else None
        except ErroAPI:
            return None

    # ---------- utilidades ----------
    def usuario(self, cabecalhos, papel=None):
        auth = cabecalhos.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise ErroAPI(401, "Entre na sua conta para continuar.")
        con = self.db.con()
        try:
            r = con.execute(
                "SELECT u.* FROM tokens t JOIN usuarios u ON u.id=t.usuario_id WHERE t.hash=? AND t.expira>?",
                (h_token(auth[7:]), int(time.time())),
            ).fetchone()
        finally:
            con.close()
        if not r:
            raise ErroAPI(401, "Sua sessão expirou. Entre de novo.")
        if papel and r["papel"] != papel:
            raise ErroAPI(403, "Esta área é só para " + papel + "s.")
        agora_h = agora_iso()[:13]
        if (r["ultimo_acesso"] or "")[:13] != agora_h:  # no máximo uma gravação por hora
            con = self.db.con()
            con.execute("UPDATE usuarios SET ultimo_acesso=? WHERE id=?", (agora_iso(), r["id"]))
            con.commit()
            con.close()
        return dict(r)

    def audita(self, con, uid, acao, alvo=""):
        con.execute("INSERT INTO auditoria(quando,usuario_id,acao,alvo) VALUES (?,?,?,?)",
                    (agora_iso(), uid, acao, str(alvo)))

    def emite_token(self, con, uid):
        tok = secrets.token_urlsafe(32)
        con.execute("INSERT INTO tokens VALUES (?,?,?)", (h_token(tok), uid, int(time.time()) + TOKEN_VIDA))
        return tok

    def prov(self, nome=None):
        try:
            return pag.provedor(self.cfg, nome, self.http)
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)

    def play(self):
        if self._play is None:
            self._play = google_play.GooglePlay(self.cfg, self.http)
        return self._play

    # ---------- rotas ----------
    ROTAS = {
        ("GET", "health"): "health",
        ("POST", "registrar"): "registrar",
        ("POST", "entrar"): "entrar",
        ("POST", "sair"): "sair",
        ("GET", "eu"): "eu",
        ("POST", "senha/esqueci"): "senha_esqueci",
        ("POST", "2fa/iniciar"): "dois_fatores_iniciar",
        ("POST", "2fa/ativar"): "dois_fatores_ativar",
        ("POST", "2fa/desativar"): "dois_fatores_desativar",
        ("POST", "senha/redefinir"): "senha_redefinir",
        ("POST", "conta/excluir"): "conta_excluir",
        ("GET", "conta/exportar"): "conta_exportar",
        ("GET", "nuvem"): "nuvem_ler",
        ("POST", "nuvem"): "nuvem_gravar",
        ("POST", "paciente/vincular"): "vincular",
        ("POST", "paciente/consentimento"): "consentimento",
        ("POST", "paciente/sync"): "sync",
        ("POST", "paciente/contato"): "pedir_contato",
        ("POST", "paciente/desvincular"): "desvincular",
        ("POST", "pro/convite"): "convite",
        ("GET", "pro/pacientes"): "pacientes",
        ("GET", "pro/pacientes/:id"): "paciente",
        ("POST", "pro/pacientes/:id/prescrever"): "prescrever",
        ("POST", "pro/prescricoes/:id/arquivar"): "arquivar",
        ("POST", "pro/pedidos/:id/visto"): "pedido_visto",
        ("POST", "sala/entrar"): "sala_entrar",
        ("POST", "sala/batimento"): "sala_batimento",
        ("POST", "sala/sair"): "sala_sair",
        ("GET", "sala"): "sala_estado",
        ("GET", "planos"): "planos",
        ("POST", "pagamentos/checkout"): "checkout",
        ("GET", "pagamentos/minha"): "minha_assinatura",
        ("POST", "pagamentos/cancelar"): "cancelar",
        ("POST", "pagamentos/portal"): "portal",
        ("GET", "pagamentos/simulado"): "simulado_info",
        ("POST", "pagamentos/simulado/confirmar"): "simulado_confirmar",
        ("POST", "pagamentos/google-play"): "google_play_verificar",
        ("POST", "webhooks/mercadopago"): "webhook_mercadopago",
        ("POST", "webhooks/stripe"): "webhook_stripe",
        ("POST", "webhooks/google-play"): "webhook_google_play",
    }

    def rota(self, metodo, caminho, corpo, cab, query=None, bruto=b"", ip="?"):
        partes = [p for p in caminho.split("/") if p][1:]  # remove 'api'
        chave = (metodo, "/".join(p if not p.isdigit() else ":id" for p in partes))
        ids = [int(p) for p in partes if p.isdigit()]
        nome = self.ROTAS.get(chave)
        if not nome:
            raise ErroAPI(404, "Endereço da API não encontrado.")
        return getattr(self, nome)(corpo=corpo, cab=cab, ids=ids, query=query or {}, bruto=bruto, ip=ip)

    def health(self, **_):
        out = {"ok": True, "app": "Agora TDAH", "versao": VERSAO}
        try:
            con = self.db.con()
            out["banco"] = {"ok": con.execute("SELECT 1").fetchone()[0] == 1,
                            "migracao": con.execute("PRAGMA user_version").fetchone()[0], "esperada": migracoes.VERSAO_ATUAL}
            con.close()
        except Exception:
            out.update(ok=False, banco={"ok": False})
        out["cifra"] = "cryptography" if cripto._CC20 else "python"
        out["push"] = push.configurado(self.cfg)
        out["ambiente"] = self.cfg.ambiente
        return out

    # ---------- contas ----------
    def registrar(self, corpo, ip="?", **_):
        if self.lim.excedeu(f"reg:{ip}", self.cfg.limite_registro, 3600):
            raise ErroAPI(429, "Muitas contas criadas daqui. Tente de novo mais tarde.")
        email = str(corpo.get("email", "")).strip().lower()
        nome = str(corpo.get("nome", "")).strip()[:80]
        senha = str(corpo.get("senha", ""))
        papel = corpo.get("papel", "paciente")
        if "@" not in email or len(email) > 120:
            raise ErroAPI(400, "Digite um e-mail válido.")
        if len(senha) < 8:
            raise ErroAPI(400, "A senha precisa ter pelo menos 8 caracteres.")
        if papel not in ("paciente", "profissional"):
            raise ErroAPI(400, "Papel inválido.")
        if not nome:
            raise ErroAPI(400, "Digite seu nome.")
        con = self.db.con()
        try:
            with _lock:
                if con.execute("SELECT 1 FROM usuarios WHERE email=?", (email,)).fetchone():
                    raise ErroAPI(409, "Já existe uma conta com este e-mail. Use Entrar.")
                cur = con.execute(
                    "INSERT INTO usuarios(email,nome,papel,senha_hash,criado_em,registro,contato,origem,marketing) VALUES (?,?,?,?,?,?,?,?,?)",
                    (email, nome, papel, hash_senha(senha), agora_iso(),
                     str(corpo.get("registro", ""))[:40], str(corpo.get("contato", ""))[:120],
                     str(corpo.get("origem", ""))[:40], 1 if corpo.get("marketing") else 0))
                uid = cur.lastrowid
                tok = self.emite_token(con, uid)
                self.audita(con, uid, "registro", papel)
                con.commit()
        finally:
            con.close()
        self.lim.marcar(f"reg:{ip}")
        return {"token": tok, "usuario": {"id": uid, "nome": nome, "papel": papel, "email": email}}

    def entrar(self, corpo, ip="?", **_):
        email = str(corpo.get("email", "")).strip().lower()
        chave = f"login:{ip}:{email}"
        espera = self.lim.excedeu(chave, 5, 15 * 60) or self.lim.excedeu(f"login-ip:{ip}", 30, 15 * 60)
        if espera:
            raise ErroAPI(429, f"Muitas tentativas. Espere {max(1, espera // 60)} min ou use Esqueci minha senha.", {"espera": espera})
        con = self.db.con()
        try:
            r = con.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
            ok = confere_senha(str(corpo.get("senha", "")), r["senha_hash"] if r else SENHA_FALSA)
            if not r or not ok:
                self.lim.marcar(chave)
                self.lim.marcar(f"login-ip:{ip}")
                raise ErroAPI(401, "E-mail ou senha não conferem.")
            if r["totp_segredo"]:
                codigo = str(corpo.get("codigo", "")).strip()
                if not codigo:
                    raise ErroAPI(401, "Digite o código do app autenticador.", {"precisa2fa": True})
                if not self._confere_segundo_fator(con, r, codigo):
                    self.lim.marcar(chave)
                    self.lim.marcar(f"login-ip:{ip}")
                    raise ErroAPI(401, "Código não confere. Use o código atual do app ou um código de recuperação.", {"precisa2fa": True})
            tok = self.emite_token(con, r["id"])
            self.audita(con, r["id"], "login", ip)
            con.commit()
        finally:
            con.close()
        self.lim.limpar(chave)  # depois do commit: o limitador usa outra conexão
        return {"token": tok, "usuario": {"id": r["id"], "nome": r["nome"], "papel": r["papel"], "email": r["email"]}}

    # ---------- verificação em duas etapas (TOTP) ----------
    def _confere_segundo_fator(self, con, r, codigo):
        segredo = self.decifra(r["totp_segredo"], "totp")
        c = cripto.confere_totp(segredo, codigo, r["totp_ultimo"] or 0)
        if c:
            con.execute("UPDATE usuarios SET totp_ultimo=? WHERE id=?", (c, r["id"]))
            return True
        rec = json.loads(r["totp_rec"] or "[]")
        h = cripto.hash_codigo(codigo)
        if h in rec:
            rec.remove(h)
            con.execute("UPDATE usuarios SET totp_rec=? WHERE id=?", (json.dumps(rec), r["id"]))
            self.audita(con, r["id"], "2fa_recuperacao", len(rec))
            return True
        return False

    def dois_fatores_iniciar(self, cab, **_):
        u = self.usuario(cab)
        if u["totp_segredo"]:
            raise ErroAPI(409, "A verificação em duas etapas já está ligada.")
        segredo = cripto.novo_segredo_totp()
        con = self.db.con()
        con.execute("UPDATE usuarios SET totp_pendente=? WHERE id=?", (self.cifra(segredo, "totp"), u["id"]))
        con.commit()
        con.close()
        return {"segredo": segredo, "uri": cripto.uri_totp(segredo, u["email"], "Agora"),
                "instrucao": "No app autenticador (Google Authenticator, Aegis, 1Password), adicione a conta lendo o QR ou digitando a chave. Depois digite o código de 6 dígitos."}

    def dois_fatores_ativar(self, corpo, cab, **_):
        u = self.usuario(cab)
        if not u["totp_pendente"]:
            raise ErroAPI(400, "Comece por Ativar verificação em duas etapas.")
        segredo = self.decifra(u["totp_pendente"], "totp")
        c = cripto.confere_totp(segredo, corpo.get("codigo", ""))
        if not c:
            raise ErroAPI(400, "Código não confere. Confira se o relógio do celular está certo e tente o código novo.")
        codigos = cripto.codigos_recuperacao()
        con = self.db.con()
        con.execute("UPDATE usuarios SET totp_segredo=?, totp_pendente=NULL, totp_ultimo=?, totp_rec=? WHERE id=?",
                    (self.cifra(segredo, "totp"), c, json.dumps([cripto.hash_codigo(x) for x in codigos]), u["id"]))
        self.audita(con, u["id"], "2fa_ligada")
        con.commit()
        con.close()
        return {"ok": True, "recuperacao": codigos,
                "aviso": "Guarde estes códigos fora do celular. Cada um entra uma vez se você perder o aparelho."}

    def dois_fatores_desativar(self, corpo, cab, **_):
        u = self.usuario(cab)
        if not confere_senha(str(corpo.get("senha", "")), u["senha_hash"]):
            raise ErroAPI(401, "Senha incorreta.")
        con = self.db.con()
        try:
            if u["totp_segredo"] and not self._confere_segundo_fator(con, u, str(corpo.get("codigo", ""))):
                raise ErroAPI(401, "Código não confere.")
            con.execute("UPDATE usuarios SET totp_segredo=NULL, totp_pendente=NULL, totp_rec=NULL WHERE id=?", (u["id"],))
            self.audita(con, u["id"], "2fa_desligada")
            con.commit()
        finally:
            con.close()
        return {"ok": True}

    def sair(self, cab, **_):
        auth = cab.get("Authorization", "")
        con = self.db.con()
        con.execute("DELETE FROM tokens WHERE hash=?", (h_token(auth[7:]),))
        con.commit()
        con.close()
        return {"ok": True}

    def senha_esqueci(self, corpo, ip="?", **_):
        email = str(corpo.get("email", "")).strip().lower()
        resposta = {"ok": True, "mensagem": "Se houver uma conta com este e-mail, enviamos um link para criar uma senha nova. Ele vale por 1 hora."}
        if self.lim.excedeu(f"reset:{ip}", 5, 3600) or self.lim.excedeu(f"reset:{email}", 3, 3600):
            return resposta
        self.lim.marcar(f"reset:{ip}")
        self.lim.marcar(f"reset:{email}")
        con = self.db.con()
        try:
            r = con.execute("SELECT id,nome,email FROM usuarios WHERE email=?", (email,)).fetchone()
            if r:
                tok = secrets.token_urlsafe(32)
                con.execute("INSERT INTO resets_senha VALUES (?,?,?,0)", (h_token(tok), r["id"], int(time.time()) + RESET_VIDA))
                link = f"{self.cfg.url_publica}/app/?redefinir={tok}"
                texto = (f"Olá, {r['nome'].split(' ')[0]}.\n\nRecebemos um pedido para criar uma senha nova no Agora TDAH.\n"
                         f"Abra este link em até 1 hora:\n\n{link}\n\nSe não foi você, ignore este e-mail: sua senha continua a mesma.\n")
                try:
                    email_envio.enviar(self.cfg, con, r["email"], "Agora TDAH: criar senha nova", texto)
                except Exception as e:  # pragma: no cover
                    sys.stderr.write(f"falha ao enviar e-mail: {e!r}\n")
                self.audita(con, r["id"], "reset_pedido", ip)
            con.commit()
        finally:
            con.close()
        return resposta

    def senha_redefinir(self, corpo, **_):
        tok, senha = str(corpo.get("token", "")), str(corpo.get("senha", ""))
        if len(senha) < 8:
            raise ErroAPI(400, "A senha precisa ter pelo menos 8 caracteres.")
        con = self.db.con()
        try:
            r = con.execute("SELECT * FROM resets_senha WHERE hash=? AND usado=0 AND expira>?", (h_token(tok), int(time.time()))).fetchone()
            if not r:
                raise ErroAPI(400, "Este link expirou ou já foi usado. Peça outro em Esqueci minha senha.")
            con.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (hash_senha(senha), r["usuario_id"]))
            con.execute("UPDATE resets_senha SET usado=1 WHERE usuario_id=?", (r["usuario_id"],))
            con.execute("DELETE FROM tokens WHERE usuario_id=?", (r["usuario_id"],))
            self.audita(con, r["usuario_id"], "reset_concluido")
            con.commit()
        finally:
            con.close()
        return {"ok": True}

    def conta_excluir(self, corpo, cab, **_):
        u = self.usuario(cab)
        if not confere_senha(str(corpo.get("senha", "")), u["senha_hash"]):
            raise ErroAPI(401, "Senha incorreta.")
        con = self.db.con()
        try:
            for a in con.execute("SELECT * FROM assinaturas WHERE usuario_id=? AND cancelar_no_fim=0 AND status='ativa'", (u["id"],)).fetchall():
                if pag.planos(self.cfg).get(a["plano"], {}).get("tipo") == "recorrente" and a["provedor"] in ("mercadopago", "stripe"):
                    try:
                        self.prov(a["provedor"]).cancelar(dict(a))
                    except Exception as e:  # registra e segue: a exclusão não pode travar
                        sys.stderr.write(f"cancelamento na exclusão falhou: {e!r}\n")
            uid = u["id"]
            for sql in ("DELETE FROM tokens WHERE usuario_id=?", "DELETE FROM snapshots WHERE paciente_id=?",
                        "DELETE FROM nuvem WHERE usuario_id=?", "DELETE FROM sala WHERE usuario_id=?",
                        "DELETE FROM vinculos WHERE paciente_id=? OR profissional_id=?", "DELETE FROM prescricoes WHERE paciente_id=? OR profissional_id=?",
                        "DELETE FROM pedidos_contato WHERE paciente_id=? OR profissional_id=?", "DELETE FROM convites WHERE profissional_id=?",
                        "DELETE FROM resets_senha WHERE usuario_id=?", "DELETE FROM assinaturas WHERE usuario_id=?",
                        "DELETE FROM checkouts WHERE usuario_id=?", "DELETE FROM inscricoes WHERE usuario_id=?",
                        "DELETE FROM missoes_feitas WHERE usuario_id=?", "DELETE FROM push_inscricoes WHERE usuario_id=?",
                        "DELETE FROM push_pendentes WHERE usuario_id=?", "DELETE FROM lembretes_push WHERE usuario_id=?",
                        "DELETE FROM interesses WHERE usuario_id=?", "UPDATE compras SET usuario_id=NULL WHERE usuario_id=?",
                        "DELETE FROM usuarios WHERE id=?"):
                con.execute(sql, (uid,) * sql.count("?"))
            con.execute("DELETE FROM interesses WHERE email=?", (u["email"],))
            con.execute("DELETE FROM sequencias WHERE email=?", (u["email"],))
            # pagamentos ficam (obrigação fiscal), sem ligação com nome ou e-mail
            self.audita(con, None, "conta_excluida", hashlib.sha256(u["email"].encode()).hexdigest()[:16])
            con.commit()
        finally:
            con.close()
        return {"ok": True}

    def conta_exportar(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            n = con.execute("SELECT dados FROM nuvem WHERE usuario_id=?", (u["id"],)).fetchone()
            s = con.execute("SELECT dados FROM snapshots WHERE paciente_id=?", (u["id"],)).fetchone()
            interesses = [{**dict(r), "mensagem": self.decifra(r["mensagem"], "interesse")} for r in con.execute(
                "SELECT item_id,nome,email,contato,mensagem,origem,status,criado_em FROM interesses WHERE usuario_id=? OR email=?", (u["id"], u["email"]))]
            return {"conta": {k: u[k] for k in ("id", "email", "nome", "papel", "criado_em", "origem", "marketing")},
                    "copia_na_nuvem": json.loads(self.decifra(n["dados"], "nuvem")) if n else None,
                    "compartilhado_com_profissional": json.loads(self.decifra(s["dados"], "snapshot")) if s else None,
                    "interesses": interesses,
                    "compras": [dict(r) for r in con.execute("SELECT item_id,entrega,valor,status,criado_em FROM compras WHERE usuario_id=?", (u["id"],))],
                    "turmas": [dict(r) for r in con.execute("SELECT t.nome, i.status, i.criado_em FROM inscricoes i JOIN turmas t ON t.id=i.turma_id WHERE i.usuario_id=?", (u["id"],))],
                    "lembretes": [dict(r) for r in con.execute("SELECT dados, fuso FROM lembretes_push WHERE usuario_id=?", (u["id"],))],
                    **pag.resumo_assinaturas(con, self.cfg, u["id"])}
        finally:
            con.close()

    def eu(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            out = {"id": u["id"], "nome": u["nome"], "papel": u["papel"], "email": u["email"],
                   "direitos": pag.direitos(con, u["id"]), "contaPlay": google_play.conta_externa(u["id"]),
                   "admin": bool(u["admin"]), "doisFatores": bool(u["totp_segredo"]), "marketing": bool(u["marketing"]),
                   "exige2fa": bool(u["admin"] and self.cfg.exigir_2fa_admin and not u["totp_segredo"])}
            out.update(pag.resumo_assinaturas(con, self.cfg, u["id"]))
            if u["papel"] == "paciente":
                v = con.execute(
                    "SELECT v.*, u.nome AS pro_nome, u.contato AS pro_contato, u.registro AS pro_registro FROM vinculos v "
                    "JOIN usuarios u ON u.id=v.profissional_id WHERE v.paciente_id=? AND v.ativo=1", (u["id"],)).fetchone()
                out["vinculo"] = None if not v else {
                    "profissional": v["pro_nome"], "registro": v["pro_registro"], "contato": v["pro_contato"],
                    "consentimento": json.loads(v["consentimento"])}
                out["prescricoes"] = self._prescricoes_paciente(con, u["id"])
                n = con.execute("SELECT atualizado_em, versao FROM nuvem WHERE usuario_id=?", (u["id"],)).fetchone()
                out["nuvemEm"] = n["atualizado_em"] if n else None
                out["nuvemVersao"] = n["versao"] if n else 0
            else:
                out["limitePacientes"] = None if out["direitos"]["pro"] else self.cfg.pro_gratis_pacientes
            return out
        finally:
            con.close()

    # ---------- cópia na nuvem (Plus) ----------
    def _exige_plus(self, con, u):
        if not pag.direitos(con, u["id"])["plus"]:
            raise ErroAPI(402, "Este recurso é do Agora Plus.", {"recurso": "plus"})

    def nuvem_gravar(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        dados = corpo.get("dados")
        if not isinstance(dados, dict):
            raise ErroAPI(400, "Dados ausentes.")
        con = self.db.con()
        try:
            self._exige_plus(con, u)
            txt = json.dumps(dados, ensure_ascii=False)
            if len(txt) > MAX_CORPO:
                raise ErroAPI(413, "Seus dados passaram do limite da cópia na nuvem.")
            with _lock:
                atual = con.execute("SELECT versao, atualizado_em FROM nuvem WHERE usuario_id=?", (u["id"],)).fetchone()
                base = corpo.get("versao_base")
                if atual and base is not None and not corpo.get("forcar") and int(base) != (atual["versao"] or 1):
                    raise ErroAPI(409, "A cópia na nuvem mudou em outro aparelho desde a última vez.",
                                  {"conflito": True, "versao": atual["versao"], "atualizado_em": atual["atualizado_em"]})
                versao = ((atual["versao"] or 1) + 1) if atual else 1
                em = agora_iso()
                con.execute("INSERT OR REPLACE INTO nuvem(usuario_id,dados,atualizado_em,versao) VALUES (?,?,?,?)",
                            (u["id"], self.cifra(txt, "nuvem"), em, versao))
                con.commit()
            return {"ok": True, "atualizado_em": em, "versao": versao}
        finally:
            con.close()

    def nuvem_ler(self, cab, **_):
        u = self.usuario(cab, "paciente")
        con = self.db.con()
        try:
            self._exige_plus(con, u)
            r = con.execute("SELECT dados, atualizado_em, versao FROM nuvem WHERE usuario_id=?", (u["id"],)).fetchone()
            return {"dados": json.loads(self.decifra(r["dados"], "nuvem")) if r else None,
                    "atualizado_em": r["atualizado_em"] if r else None, "versao": r["versao"] if r else 0}
        finally:
            con.close()

    # ---------- paciente ----------
    def _prescricoes_paciente(self, con, pid):
        rows = con.execute(
            "SELECT p.id,p.tipo,p.conteudo,p.criado_em FROM prescricoes p JOIN vinculos v "
            "ON v.profissional_id=p.profissional_id AND v.paciente_id=p.paciente_id AND v.ativo=1 "
            "WHERE p.paciente_id=? AND p.ativo=1 ORDER BY p.id", (pid,)).fetchall()
        return [{"id": r["id"], "tipo": r["tipo"], "conteudo": json.loads(r["conteudo"]), "criadoEm": r["criado_em"]} for r in rows]

    def vincular(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        codigo = str(corpo.get("codigo", "")).strip().upper()
        cons = corpo.get("consentimento") or {}
        cons = {k: bool(cons.get(k)) for k in CONSENT_CAMPOS}
        con = self.db.con()
        try:
            with _lock:
                c = con.execute("SELECT * FROM convites WHERE codigo=?", (codigo,)).fetchone()
                if not c or c["usado_por"]:
                    raise ErroAPI(404, "Código de convite inválido ou já usado. Peça um novo ao seu profissional.")
                con.execute("UPDATE vinculos SET ativo=0 WHERE paciente_id=?", (u["id"],))
                con.execute("INSERT OR REPLACE INTO vinculos VALUES (?,?,?,?,1)",
                            (u["id"], c["profissional_id"], json.dumps(cons), agora_iso()))
                con.execute("UPDATE convites SET usado_por=? WHERE codigo=?", (u["id"], codigo))
                self.audita(con, u["id"], "vinculo", c["profissional_id"])
                con.commit()
        finally:
            con.close()
        return self.eu(cab=cab)

    def consentimento(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        cons = {k: bool((corpo.get("consentimento") or {}).get(k)) for k in CONSENT_CAMPOS}
        con = self.db.con()
        con.execute("UPDATE vinculos SET consentimento=? WHERE paciente_id=? AND ativo=1", (json.dumps(cons), u["id"]))
        self.audita(con, u["id"], "consentimento", json.dumps(cons))
        con.commit()
        con.close()
        return {"ok": True, "consentimento": cons}

    def desvincular(self, cab, **_):
        u = self.usuario(cab, "paciente")
        con = self.db.con()
        con.execute("UPDATE vinculos SET ativo=0 WHERE paciente_id=?", (u["id"],))
        con.execute("DELETE FROM snapshots WHERE paciente_id=?", (u["id"],))
        self.audita(con, u["id"], "desvinculo")
        con.commit()
        con.close()
        return {"ok": True}

    def sync(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        dados = corpo.get("dados")
        if not isinstance(dados, dict):
            raise ErroAPI(400, "Dados ausentes.")
        con = self.db.con()
        try:
            v = con.execute("SELECT consentimento FROM vinculos WHERE paciente_id=? AND ativo=1", (u["id"],)).fetchone()
            if v:
                dados["_sharedAt"] = agora_iso()
                filtrado = filtra_snapshot(dados, json.loads(v["consentimento"]))
                con.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                            (u["id"], self.cifra(json.dumps(filtrado, ensure_ascii=False), "snapshot"), agora_iso()))
                con.commit()
            return {"ok": True, "compartilhado": bool(v), "prescricoes": self._prescricoes_paciente(con, u["id"])}
        finally:
            con.close()

    def pedir_contato(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        con = self.db.con()
        v = con.execute("SELECT profissional_id FROM vinculos WHERE paciente_id=? AND ativo=1", (u["id"],)).fetchone()
        con.execute("INSERT INTO pedidos_contato(paciente_id,profissional_id,motivo,criado_em) VALUES (?,?,?,?)",
                    (u["id"], v["profissional_id"] if v else None, self.cifra(str(corpo.get("motivo", ""))[:300], "pedido"), agora_iso()))
        con.commit()
        con.close()
        return {"ok": True, "encaminhado": bool(v)}

    # ---------- profissional ----------
    def convite(self, cab, **_):
        u = self.usuario(cab, "profissional")
        con = self.db.con()
        try:
            if not pag.direitos(con, u["id"])["pro"]:
                n = con.execute("SELECT COUNT(*) n FROM vinculos WHERE profissional_id=? AND ativo=1", (u["id"],)).fetchone()["n"]
                if n >= self.cfg.pro_gratis_pacientes:
                    raise ErroAPI(402, f"O plano grátis vincula até {self.cfg.pro_gratis_pacientes} pacientes. Assine o Agora Pro para convidar mais.",
                                  {"recurso": "pro"})
            alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            codigo = "".join(secrets.choice(alfabeto) for _ in range(6))
            con.execute("INSERT INTO convites VALUES (?,?,?,NULL)", (codigo, u["id"], agora_iso()))
            con.commit()
        finally:
            con.close()
        return {"codigo": codigo, "link": f"{self.cfg.url_publica}/app/?convite={codigo}"}

    def pacientes(self, cab, **_):
        u = self.usuario(cab, "profissional")
        con = self.db.con()
        try:
            rows = con.execute(
                "SELECT p.id,p.nome,v.consentimento,v.criado_em,s.dados,s.atualizado_em FROM vinculos v "
                "JOIN usuarios p ON p.id=v.paciente_id LEFT JOIN snapshots s ON s.paciente_id=p.id "
                "WHERE v.profissional_id=? AND v.ativo=1 ORDER BY p.nome", (u["id"],)).fetchall()
            pend = {r["paciente_id"]: r["n"] for r in con.execute(
                "SELECT paciente_id, COUNT(*) n FROM pedidos_contato WHERE profissional_id=? AND visto=0 GROUP BY paciente_id",
                (u["id"],))}
            out = []
            for r in rows:
                dados = json.loads(self.decifra(r["dados"], "snapshot")) if r["dados"] else {}
                out.append({"id": r["id"], "nome": r["nome"], "vinculadoEm": r["criado_em"],
                            "atualizadoEm": r["atualizado_em"], "consentimento": json.loads(r["consentimento"]),
                            "adesao7": resumo_adesao(dados, 7), "pedidosContato": pend.get(r["id"], 0)})
            convites = [dict(x) for x in con.execute(
                "SELECT codigo,criado_em FROM convites WHERE profissional_id=? AND usado_por IS NULL ORDER BY criado_em DESC LIMIT 5",
                (u["id"],))]
            d = pag.direitos(con, u["id"])
            return {"pacientes": out, "convitesAbertos": convites, "profissional": u["nome"], "direitos": d,
                    "limitePacientes": None if d["pro"] else self.cfg.pro_gratis_pacientes,
                    **pag.resumo_assinaturas(con, self.cfg, u["id"])}
        finally:
            con.close()

    def _checa_vinculo(self, con, pro_id, pid):
        v = con.execute("SELECT consentimento FROM vinculos WHERE profissional_id=? AND paciente_id=? AND ativo=1",
                        (pro_id, pid)).fetchone()
        if not v:
            raise ErroAPI(404, "Paciente não encontrado ou sem vínculo ativo.")
        return json.loads(v["consentimento"])

    def paciente(self, cab, ids, **_):
        u = self.usuario(cab, "profissional")
        pid = ids[0]
        con = self.db.con()
        try:
            cons = self._checa_vinculo(con, u["id"], pid)
            p = con.execute("SELECT id,nome FROM usuarios WHERE id=?", (pid,)).fetchone()
            s = con.execute("SELECT dados,atualizado_em FROM snapshots WHERE paciente_id=?", (pid,)).fetchone()
            dados = json.loads(self.decifra(s["dados"], "snapshot")) if s else {}
            presc = con.execute("SELECT id,tipo,conteudo,criado_em FROM prescricoes WHERE profissional_id=? AND paciente_id=? AND ativo=1 ORDER BY id DESC",
                                (u["id"], pid)).fetchall()
            ped = con.execute("SELECT id,motivo,criado_em,visto FROM pedidos_contato WHERE profissional_id=? AND paciente_id=? ORDER BY id DESC LIMIT 10",
                              (u["id"], pid)).fetchall()
            self.audita(con, u["id"], "visualizou", pid)
            con.commit()
            return {"id": p["id"], "nome": p["nome"], "consentimento": cons, "dados": dados,
                    "atualizadoEm": s["atualizado_em"] if s else None,
                    "adesao7": resumo_adesao(dados, 7), "adesao28": resumo_adesao(dados, 28),
                    "prescricoes": [{"id": r["id"], "tipo": r["tipo"], "conteudo": json.loads(r["conteudo"]), "criadoEm": r["criado_em"]} for r in presc],
                    "pedidos": [{**dict(r), "motivo": self.decifra(r["motivo"], "pedido")} for r in ped]}
        finally:
            con.close()

    def prescrever(self, corpo, cab, ids, **_):
        u = self.usuario(cab, "profissional")
        pid = ids[0]
        tipo = corpo.get("tipo")
        c = corpo.get("conteudo") or {}
        if tipo not in ("rotina", "tarefa", "mensagem"):
            raise ErroAPI(400, "Tipo de prescrição inválido.")
        titulo = str(c.get("titulo", "")).strip()[:120]
        if not titulo:
            raise ErroAPI(400, "Dê um título à prescrição.")
        limpo = {"titulo": titulo}
        if tipo == "rotina":
            passos = [{"t": str(p.get("t", ""))[:120], "min": max(1, min(120, int(p.get("min", 5))))}
                      for p in (c.get("passos") or []) if str(p.get("t", "")).strip()]
            if not passos:
                raise ErroAPI(400, "Uma rotina precisa de pelo menos um passo.")
            limpo["passos"] = passos[:20]
            limpo["horario"] = str(c.get("horario", ""))[:5]
        elif tipo == "tarefa":
            limpo["passos"] = [str(p)[:120] for p in (c.get("passos") or []) if str(p).strip()][:12]
        else:
            limpo["texto"] = str(c.get("texto", ""))[:600]
        con = self.db.con()
        try:
            self._checa_vinculo(con, u["id"], pid)
            cur = con.execute("INSERT INTO prescricoes(profissional_id,paciente_id,tipo,conteudo,criado_em) VALUES (?,?,?,?,?)",
                              (u["id"], pid, tipo, json.dumps(limpo, ensure_ascii=False), agora_iso()))
            self.audita(con, u["id"], "prescreveu", f"{pid}:{tipo}")
            con.commit()
            return {"ok": True, "id": cur.lastrowid}
        finally:
            con.close()

    def arquivar(self, cab, ids, **_):
        u = self.usuario(cab, "profissional")
        con = self.db.con()
        con.execute("UPDATE prescricoes SET ativo=0 WHERE id=? AND profissional_id=?", (ids[0], u["id"]))
        con.commit()
        con.close()
        return {"ok": True}

    def pedido_visto(self, cab, ids, **_):
        u = self.usuario(cab, "profissional")
        con = self.db.con()
        con.execute("UPDATE pedidos_contato SET visto=1 WHERE id=? AND profissional_id=?", (ids[0], u["id"]))
        con.commit()
        con.close()
        return {"ok": True}

    # ---------- sala de foco (body doubling): Plus ou paciente vinculado ----------
    def sala_entrar(self, corpo, cab, **_):
        u = self.usuario(cab)
        minutos = max(5, min(120, int(corpo.get("minutos", 25))))
        apelido = str(corpo.get("apelido") or u["nome"].split(" ")[0])[:24]
        con = self.db.con()
        try:
            vinc = con.execute("SELECT 1 FROM vinculos WHERE paciente_id=? AND ativo=1", (u["id"],)).fetchone()
            if not vinc and not pag.direitos(con, u["id"])["plus"]:
                raise ErroAPI(402, "A sala com outras pessoas é do Agora Plus.", {"recurso": "plus"})
            con.execute("INSERT OR REPLACE INTO sala VALUES (?,?,?,?,?)",
                        (u["id"], apelido, str(corpo.get("intencao", ""))[:60], int(time.time()) + minutos * 60, int(time.time())))
            con.commit()
        finally:
            con.close()
        return self.sala_estado()

    def sala_batimento(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        con.execute("UPDATE sala SET ultimo_batimento=? WHERE usuario_id=?", (int(time.time()), u["id"]))
        con.commit()
        con.close()
        return self.sala_estado()

    def sala_sair(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        con.execute("DELETE FROM sala WHERE usuario_id=?", (u["id"],))
        con.commit()
        con.close()
        return {"ok": True}

    def sala_estado(self, **_):
        agora = int(time.time())
        con = self.db.con()
        rows = con.execute("SELECT apelido,intencao,fim_previsto FROM sala WHERE ultimo_batimento>? ORDER BY fim_previsto",
                           (agora - SALA_JANELA,)).fetchall()
        con.close()
        return {"pessoas": [{"apelido": r["apelido"], "intencao": r["intencao"],
                             "restaMin": max(0, (r["fim_previsto"] - agora) // 60)} for r in rows]}

    # ---------- pagamentos ----------
    def planos(self, **_):
        return {"planos": [p for p in pag.planos(self.cfg).values() if p["tipo"] != "avulso"], "provedor": self.cfg.provedor, "moeda": "BRL",
                "simulado": self.cfg.simulado_permitido(), "playProdutos": self.cfg.play_produtos}

    def checkout(self, corpo, cab, **_):
        u = self.usuario(cab)
        if (cab.get("X-Agora-Plataforma") or "").lower() == "android":
            raise ErroAPI(403, "Assinaturas não são vendidas pelo app Android. Se você já assina, é só entrar na conta.")
        if str(corpo.get("plano", "")).startswith("item:"):
            raise ErroAPI(400, "Produtos do catálogo são comprados em Serviços.")
        prov = self.prov()
        con = self.db.con()
        try:
            r = pag.novo_checkout(con, self.cfg, u, str(corpo.get("plano", "")), prov)
            self.audita(con, u["id"], "checkout", f"{corpo.get('plano')}:{prov.nome}")
            con.commit()
            return r
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)
        finally:
            con.close()

    def minha_assinatura(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            return {"direitos": pag.direitos(con, u["id"]), **pag.resumo_assinaturas(con, self.cfg, u["id"])}
        finally:
            con.close()

    def cancelar(self, corpo, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            r = pag.cancelar_assinatura(con, self.cfg, u["id"], int(corpo.get("assinatura") or 0), self.http)
            self.audita(con, u["id"], "cancelou", corpo.get("assinatura"))
            con.commit()
            return r
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)
        finally:
            con.close()

    def portal(self, corpo, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            a = con.execute("SELECT * FROM assinaturas WHERE id=? AND usuario_id=?", (int(corpo.get("assinatura") or 0), u["id"])).fetchone()
            if not a:
                raise ErroAPI(404, "Assinatura não encontrada.")
            url = self.prov(a["provedor"]).portal(dict(a), f"{self.cfg.url_publica}/app/#mais")
            if not url:
                raise ErroAPI(400, "Este meio de pagamento não tem portal. Use Cancelar renovação.")
            return {"url": url}
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)
        finally:
            con.close()

    def _ck_simulado(self, con, ck):
        if not self.cfg.simulado_permitido():
            raise ErroAPI(404, "Checkout simulado desligado.")
        r = con.execute("SELECT * FROM checkouts WHERE id=? AND provedor='simulado'", (ck,)).fetchone()
        if not r:
            raise ErroAPI(404, "Checkout não encontrado.")
        return r

    def simulado_info(self, query, **_):
        con = self.db.con()
        try:
            r = self._ck_simulado(con, str(query.get("c", "")))
            pl = dict(pag.planos(self.cfg)[r["plano"]])
            meta = pag.meta_checkout(r)
            if meta.get("valor"):
                pl["valor"] = meta["valor"]
            u = con.execute("SELECT email FROM usuarios WHERE id=?", (r["usuario_id"],)).fetchone()
            return {"checkout": r["id"], "status": r["status"], "plano": pl, "email": u["email"] if u else ""}
        finally:
            con.close()

    def simulado_confirmar(self, corpo, **_):
        resultado = corpo.get("resultado")
        if resultado not in ("aprovado", "pix", "recusado"):
            raise ErroAPI(400, "Resultado inválido.")
        con = self.db.con()
        try:
            r = self._ck_simulado(con, str(corpo.get("checkout", "")))
            pl = dict(pag.planos(self.cfg)[r["plano"]])
            pl["valor"] = pag.meta_checkout(r).get("valor") or pl["valor"]
            ev = pag.Simulado(self.cfg).evento(r, pl, resultado)
            res = pag.aplicar_evento(con, self.cfg, "simulado", ev)
            con.commit()
            return {"ok": True, "resultado": res}
        finally:
            con.close()

    def _webhook(self, nome, cab, query, bruto):
        prov = self.prov(nome)
        try:
            prov.verificar_webhook(cab, query, bruto)
            evs = prov.eventos(cab, query, bruto)
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)
        except ValueError:
            raise ErroAPI(400, "Corpo do webhook inválido.")
        con = self.db.con()
        try:
            res = [pag.aplicar_evento(con, self.cfg, nome, ev) for ev in evs]
            con.commit()
        finally:
            con.close()
        return {"ok": True, "resultados": res}

    def webhook_mercadopago(self, cab, query, bruto, **_):
        return self._webhook("mercadopago", cab, query, bruto)

    def webhook_stripe(self, cab, query, bruto, **_):
        return self._webhook("stripe", cab, query, bruto)

    def _aplicar_play(self, con, uid, purchase_token, produto, ev_id):
        gp = self.play()
        try:
            info = google_play.interpretar(gp.consultar(purchase_token), self.cfg)
        except pag.ErroPag as e:
            raise ErroAPI(e.status, e.msg)
        plano = info["plano"] or self.cfg.play_produtos.get(produto or "")
        if not plano:
            raise ErroAPI(400, "Produto do Google Play não mapeado (PLAY_PRODUTOS).")
        if uid is not None and info["conta"] and info["conta"] != google_play.conta_externa(uid):
            raise ErroAPI(403, "Esta compra pertence a outra conta.")
        existente = con.execute("SELECT * FROM assinaturas WHERE provedor='google_play' AND ref_externa=?", (purchase_token,)).fetchone()
        if uid is None and not existente:
            # RTDN sem compra registrada: tenta herdar do token anterior (upgrade/renovação com novo token)
            anterior = info["token_anterior"] and con.execute(
                "SELECT * FROM assinaturas WHERE provedor='google_play' AND ref_externa=?", (info["token_anterior"],)).fetchone()
            if not anterior:
                return "compra ainda não vinculada a uma conta"
            uid = anterior["usuario_id"]
        if not existente and uid is not None:
            ck = "ck_play_" + hashlib.sha256(purchase_token.encode()).hexdigest()[:16]
            con.execute("INSERT OR IGNORE INTO checkouts(id,usuario_id,plano,provedor,ref_externa,criado_em) VALUES (?,?,?,?,?,?)",
                        (ck, uid, plano, "google_play", purchase_token, agora_iso()))
            ev = google_play.evento(info, purchase_token, ev_id)
            ev["checkout"] = ck
        else:
            ev = google_play.evento(info, purchase_token, ev_id)
        res = pag.aplicar_evento(con, self.cfg, "google_play", ev)
        if info["ativo"] and not info["reconhecido"] and info["produto"]:
            gp.reconhecer(info["produto"], purchase_token)
        return res

    def google_play_verificar(self, corpo, cab, **_):
        u = self.usuario(cab, "paciente")
        token = str(corpo.get("token", "")).strip()
        if not token:
            raise ErroAPI(400, "purchaseToken ausente.")
        con = self.db.con()
        try:
            res = self._aplicar_play(con, u["id"], token, corpo.get("produto"), f"app:{token[:32]}:{int(time.time() // 60)}")
            con.commit()
            return {"ok": True, "resultado": res, "direitos": pag.direitos(con, u["id"])}
        finally:
            con.close()

    def webhook_google_play(self, query, bruto, **_):
        tok = query.get("token", "")
        if not self.cfg.play_token_rtdn or not hmac.compare_digest(str(tok), self.cfg.play_token_rtdn):
            raise ErroAPI(401, "Token do Pub/Sub não confere.")
        msg = google_play.ler_rtdn(bruto)
        if not msg:
            return {"ok": True, "resultado": "ignorado"}
        purchase_token, produto, tipo, mid = msg
        con = self.db.con()
        try:
            res = self._aplicar_play(con, None, purchase_token, produto, f"rtdn:{mid}:{tipo}")
            con.commit()
            return {"ok": True, "resultado": res}
        finally:
            con.close()


TIPOS_EXTRA = {".webmanifest": "application/manifest+json", ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".css": "text/css; charset=utf-8"}
_CSP_CACHE = {}


def politica_csp(caminho, dados):
    """Content-Security-Policy com o hash de cada <script> embutido na página (sem 'unsafe-inline' para scripts)."""
    import base64
    import re
    chave = (str(caminho), hashlib.sha256(dados).hexdigest())
    if chave not in _CSP_CACHE:
        hashes = [f"'sha256-{base64.b64encode(hashlib.sha256(m.encode()).digest()).decode()}'"
                  for m in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", dados.decode("utf-8", "replace"), re.S)]
        _CSP_CACHE[chave] = "; ".join([
            "default-src 'self'", "script-src 'self' " + " ".join(hashes), "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:", "font-src 'self'", "connect-src 'self'", "media-src 'self' data: blob:",
            "worker-src 'self'", "manifest-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
            "frame-ancestors 'none'"])
    return _CSP_CACHE[chave]


def log_json(**campos):
    sys.stderr.write(json.dumps({"t": agora_iso(), **campos}, ensure_ascii=False) + "\n")


def registrar_erro(api, rota, e):
    """Guarda o erro interno (sem corpo da requisição, que pode ter dado de saúde) e avisa por e-mail, no máximo 1 vez por hora."""
    import traceback
    detalhe = "".join(traceback.format_exception(type(e), e, e.__traceback__))[-3000:]
    log_json(nivel="erro", rota=rota, tipo=type(e).__name__, detalhe=detalhe.splitlines()[-1] if detalhe else "")
    try:
        con = api.db.con()
        con.execute("INSERT INTO erros(quando,rota,tipo,detalhe) VALUES (?,?,?,?)", (agora_iso(), rota, type(e).__name__, detalhe))
        ultimo = con.execute("SELECT MAX(quando) q FROM erros WHERE avisado=1").fetchone()["q"]
        if api.cfg.alerta_email and (not ultimo or ultimo < (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")):
            n = con.execute("SELECT COUNT(*) n FROM erros WHERE avisado=0").fetchone()["n"]
            email_envio.enviar(api.cfg, con, api.cfg.alerta_email, f"[Agora] {n} erro(s) interno(s)",
                               f"Último: {type(e).__name__} em {rota}.\nVeja /app/admin.html › Erros ou a tabela erros do banco.\n")
            con.execute("UPDATE erros SET avisado=1 WHERE avisado=0")
        con.commit()
        con.close()
    except Exception:  # pragma: no cover - o registro de erro nunca pode derrubar a resposta
        pass


def cria_handler(api, servir_estaticos=True):
    cfg = api.cfg

    class Handler(BaseHTTPRequestHandler):
        server_version = "Agora/" + VERSAO.split(".")[0]
        sys_version = ""

        def log_message(self, fmt, *args):
            if os.environ.get("AGORA_LOG") or cfg.producao:
                # caminho sem query string: tokens de links assinados não vão para o log
                log_json(nivel="acesso", ip=self._ip(), metodo=self.command, caminho=urlparse(self.path).path,
                         status=args[1] if len(args) > 1 else "", ms=round((time.time() - getattr(self, "_t0", time.time())) * 1000))

        def _ip(self):
            if cfg.atras_de_proxy and self.headers.get("X-Forwarded-For"):
                return self.headers["X-Forwarded-For"].split(",")[0].strip()
            return self.client_address[0]

        def _cors(self):
            origem = self.headers.get("Origin")
            if origem and origem in cfg.cors:
                self.send_header("Access-Control-Allow-Origin", origem)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Agora-Plataforma")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Max-Age", "600")

        def _seguranca(self, csp=None):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Content-Security-Policy", csp or "default-src 'none'; frame-ancestors 'none'")
            if cfg.producao:
                self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        def _json(self, status, obj):
            dados = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self._seguranca()
            self._cors()
            self.end_headers()
            self.wfile.write(dados)

        def _html_api(self, html):
            dados = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self._seguranca("default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(dados)

        def _arquivo_api(self, r):
            dados = Path(r["_arquivo"]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", r.get("_tipo", "application/octet-stream"))
            self.send_header("Content-Disposition", f'attachment; filename="{r.get("_nome", "arquivo")}"')
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "private, no-store")
            self._seguranca()
            self.end_headers()
            self.wfile.write(dados)

        def _api(self, metodo):
            self._t0 = time.time()
            try:
                tam = int(self.headers.get("Content-Length") or 0)
                if tam > MAX_CORPO:
                    raise ErroAPI(413, "Envio grande demais.")
                bruto = self.rfile.read(tam) if tam else b""
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                corpo = {}
                if bruto and "/webhooks/" not in url.path:
                    try:
                        corpo = json.loads(bruto or b"{}")
                    except json.JSONDecodeError:
                        raise ErroAPI(400, "JSON inválido.")
                    if not isinstance(corpo, dict):
                        raise ErroAPI(400, "JSON inválido.")
                r = api.rota(metodo, url.path, corpo, self.headers, query, bruto, self._ip())
                if isinstance(r, dict) and "_html" in r:
                    return self._html_api(r["_html"])
                if isinstance(r, dict) and "_arquivo" in r:
                    return self._arquivo_api(r)
                self._json(200, r)
            except ErroAPI as e:
                if e.status == 429 and (cfg.producao or os.environ.get("AGORA_LOG")):
                    log_json(nivel="aviso", evento="limite", ip=self._ip(), caminho=urlparse(self.path).path)
                self._json(e.status, {"erro": e.msg, **e.extra})
            except Exception as e:
                registrar_erro(api, urlparse(self.path).path, e)
                self._json(500, {"erro": "Erro interno no servidor. A equipe foi avisada."})

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            if self.path.startswith("/api/"):
                return self._api("POST")
            self._json(404, {"erro": "Não encontrado."})

        def _redir(self, destino):
            self.send_response(301)
            self.send_header("Location", destino)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            url = urlparse(self.path)
            caminho = url.path
            if caminho.startswith("/api/"):
                return self._api("GET")
            if not servir_estaticos:
                return self._json(404, {"erro": "Não encontrado."})
            if caminho == "/app":
                return self._redir("/app/")
            if caminho == "/pro.html":
                return self._redir("/app/pro.html")
            if caminho.startswith("/app/"):
                base, rel = APP_DIR, caminho[len("/app/"):]
            else:
                base, rel = SITE_DIR, caminho.lstrip("/")
            if rel in ("", ) or rel.endswith("/"):
                rel += "index.html"
            alvo = (base / rel).resolve()
            if base not in alvo.parents or not alvo.is_file():
                html = (base / (rel + ".html")).resolve()
                if base in html.parents and html.is_file():
                    alvo = html
                else:
                    self.send_error(404, "Arquivo não encontrado")
                    return
            dados = alvo.read_bytes()
            tipo = TIPOS_EXTRA.get(alvo.suffix) or mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
            self.send_response(200)
            texto = tipo.startswith(("text/", "application/javascript", "application/manifest", "application/json", "image/svg"))
            self.send_header("Content-Type", tipo + ("; charset=utf-8" if texto and "charset" not in tipo else ""))
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "public, max-age=604800, immutable" if alvo.suffix == ".woff2" else "no-cache")
            if alvo.name == "sw.js":
                self.send_header("Service-Worker-Allowed", "/app/")
            csp = politica_csp(alvo, dados) if alvo.suffix == ".html" else ("default-src 'none'; style-src 'unsafe-inline'" if alvo.suffix == ".svg" else None)
            self._seguranca(csp)
            self.end_headers()
            self.wfile.write(dados)

    return Handler


def iniciar_agendador(api, intervalo=60):
    """Lembretes push a cada minuto; e-mails de conteúdo e limpeza (retenção) a cada hora."""
    parar = threading.Event()

    def laco():
        while not parar.wait(intervalo - time.time() % intervalo):
            try:
                api.tarefas_periodicas()
            except Exception as e:  # pragma: no cover
                registrar_erro(api, "agendador", e)

    threading.Thread(target=laco, daemon=True, name="agendador").start()
    return parar


def main(argv=None):
    ap = argparse.ArgumentParser(description="Servidor Agora TDAH")
    ap.add_argument("--porta", type=int, default=int(os.environ.get("AGORA_PORTA", 8765)))
    ap.add_argument("--host", default=os.environ.get("AGORA_HOST", "127.0.0.1"))
    ap.add_argument("--db", default=os.environ.get("AGORA_DB", str(RAIZ / "dados" / "agora.db")))
    a = ap.parse_args(argv)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    if cfg.producao:
        faltas = [f for f in cfg.avisos_producao() if "opcional" not in f and "recomendado" not in f]
        if faltas:
            raise SystemExit("Produção sem configuração obrigatória:\n  - " + "\n  - ".join(faltas))
    api = API(Banco(a.db), cfg)
    if api.cifrados_na_partida:
        print(f"  {api.cifrados_na_partida} campo(s) antigo(s) cifrado(s) no banco.")
    srv = ThreadingHTTPServer((a.host, a.porta), cria_handler(api))
    srv.daemon_threads = True
    if cfg.agendador:
        iniciar_agendador(api)
    url = f"http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.porta}"
    print(f"Agora TDAH {VERSAO} no ar ({cfg.ambiente}).")
    print(f"  Site .................. {url}/")
    print(f"  App do paciente ....... {url}/app/")
    print(f"  Painel do profissional  {url}/app/pro.html")
    print(f"  Pagamentos ............ {cfg.provedor}{' (teste: nenhum dinheiro de verdade)' if cfg.simulado_permitido() else ''}")
    print(f"  Administração ......... {url}/app/admin.html")
    print(f"  Banco de dados ........ {a.db} (migração {api.db.versao}, cifra {'cryptography' if cripto._CC20 else 'python'})")

    print("Para desligar, feche esta janela ou aperte Ctrl+C.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor desligado.")


if __name__ == "__main__":
    main()
