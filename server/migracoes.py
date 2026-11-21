"""Migrações do banco (PRAGMA user_version).

Cada item da lista MIGRACOES roda uma única vez, em ordem, dentro de uma transação.
Bancos novos e antigos passam pelo mesmo caminho: o esquema base (server.ESQUEMA)
cria as tabelas da 1.x e as migrações levam até a versão atual.

Para mudar o banco: acrescente uma função no fim da lista. Nunca edite uma que já
foi publicada.
"""
import json


def _colunas(con, tabela):
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def _add(con, tabela, coluna, tipo):
    if coluna not in _colunas(con, tabela):
        con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def _script(con, sql):
    """Como executescript, mas sem o COMMIT implícito: a migração fica numa transação só."""
    for st in sql.split(";"):
        if st.strip():
            con.execute(st)


def m1_producao(con):
    """2.0: segurança, funil de serviços, turmas, compras avulsas e push."""
    for col, tipo in (("admin", "INTEGER DEFAULT 0"), ("totp_segredo", "TEXT"), ("totp_pendente", "TEXT"),
                      ("totp_ultimo", "INTEGER DEFAULT 0"), ("totp_rec", "TEXT"), ("marketing", "INTEGER DEFAULT 0"),
                      ("origem", "TEXT DEFAULT ''"), ("ultimo_acesso", "TEXT")):
        _add(con, "usuarios", col, tipo)
    _add(con, "nuvem", "versao", "INTEGER DEFAULT 1")
    _add(con, "checkouts", "meta", "TEXT")
    _script(con, """
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS limites (chave TEXT NOT NULL, t REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_limites ON limites(chave, t);
CREATE TABLE IF NOT EXISTS erros (
  id INTEGER PRIMARY KEY, quando TEXT NOT NULL, rota TEXT, tipo TEXT, detalhe TEXT, avisado INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS catalogo_ajustes (item_id TEXT PRIMARY KEY, dados TEXT NOT NULL, atualizado_em TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS interesses (
  id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, nome TEXT, email TEXT, contato TEXT, mensagem TEXT,
  origem TEXT, usuario_id INTEGER, marketing INTEGER DEFAULT 0, status TEXT DEFAULT 'novo',
  criado_em TEXT NOT NULL, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_interesses_status ON interesses(status, criado_em);
CREATE TABLE IF NOT EXISTS eventos_funil (
  id INTEGER PRIMARY KEY, quando TEXT NOT NULL, nome TEXT NOT NULL, item_id TEXT, origem TEXT, usuario_id INTEGER, plataforma TEXT
);
CREATE INDEX IF NOT EXISTS ix_eventos_funil ON eventos_funil(quando, nome);
CREATE TABLE IF NOT EXISTS turmas (
  id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, nome TEXT NOT NULL, inicio TEXT, fim TEXT, encontros TEXT,
  vagas INTEGER NOT NULL DEFAULT 12, preco INTEGER, local TEXT, link TEXT, ativo INTEGER DEFAULT 1, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inscricoes (
  id INTEGER PRIMARY KEY, turma_id INTEGER NOT NULL, usuario_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pendente','confirmada','espera','cancelada')),
  checkout_id TEXT, criado_em TEXT NOT NULL, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_inscricoes ON inscricoes(turma_id, status);
CREATE TABLE IF NOT EXISTS missoes (
  id INTEGER PRIMARY KEY, turma_id INTEGER NOT NULL, semana INTEGER NOT NULL, titulo TEXT NOT NULL, texto TEXT
);
CREATE TABLE IF NOT EXISTS missoes_feitas (
  missao_id INTEGER NOT NULL, usuario_id INTEGER NOT NULL, quando TEXT NOT NULL, nota TEXT,
  PRIMARY KEY (missao_id, usuario_id)
);
CREATE TABLE IF NOT EXISTS compras (
  id INTEGER PRIMARY KEY, usuario_id INTEGER, item_id TEXT NOT NULL, entrega TEXT NOT NULL, turma_id INTEGER,
  checkout_id TEXT UNIQUE, provedor TEXT, ref_pagamento TEXT, valor INTEGER,
  status TEXT NOT NULL CHECK (status IN ('paga','estornada')), criado_em TEXT NOT NULL, atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS sequencias (
  email TEXT PRIMARY KEY, nome TEXT, item_id TEXT, etapa INTEGER DEFAULT 0, proximo_em TEXT,
  descadastrado INTEGER DEFAULT 0, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_inscricoes (
  id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, endpoint TEXT UNIQUE NOT NULL, p256dh TEXT, auth TEXT,
  criado_em TEXT NOT NULL, falhas INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS push_pendentes (
  id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, titulo TEXT, corpo TEXT, url TEXT,
  criado_em TEXT NOT NULL, entregue INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lembretes_push (
  usuario_id INTEGER PRIMARY KEY, dados TEXT NOT NULL, fuso TEXT, ultimo_envio TEXT
);
""")


MIGRACOES = [m1_producao]
VERSAO_ATUAL = len(MIGRACOES)


def aplicar(con):
    """Aplica as migrações que faltam. Devolve a versão final do banco."""
    con.isolation_level = None  # transações explícitas
    v = con.execute("PRAGMA user_version").fetchone()[0]
    for i, m in enumerate(MIGRACOES[v:], start=v + 1):
        con.execute("BEGIN")
        try:
            m(con)
            con.execute(f"PRAGMA user_version={i}")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    con.isolation_level = ""
    return con.execute("PRAGMA user_version").fetchone()[0]


# Campos sensíveis cifrados no banco: (tabela, chave primária, coluna, contexto do AAD)
CAMPOS_CIFRADOS = (
    ("nuvem", "usuario_id", "dados", "nuvem"),
    ("snapshots", "paciente_id", "dados", "snapshot"),
    ("pedidos_contato", "id", "motivo", "pedido"),
    ("interesses", "id", "mensagem", "interesse"),
    ("usuarios", "id", "totp_segredo", "totp"),
    ("missoes_feitas", "rowid", "nota", "missao"),
)


def cifrar_legado(con, cofre):
    """Cifra textos em claro herdados da 1.x e recifra os que usam chave antiga.

    Idempotente: pode rodar a cada partida. Devolve quantos campos mudaram."""
    n = 0
    for tabela, pk, col, ctx in CAMPOS_CIFRADOS:
        for row in con.execute(f"SELECT {pk} AS k, {col} AS v FROM {tabela} WHERE {col} IS NOT NULL AND {col} != ''").fetchall():
            v = row["v"] if hasattr(row, "keys") else row[1]
            k = row["k"] if hasattr(row, "keys") else row[0]
            if cofre.cifrado(v) and not cofre.precisa_recifrar(v):
                continue
            claro = cofre.decifrar(v, ctx) if cofre.cifrado(v) else v
            con.execute(f"UPDATE {tabela} SET {col}=? WHERE {pk}=?", (cofre.cifrar(claro, ctx), k))
            n += 1
    con.execute("INSERT OR REPLACE INTO meta VALUES ('cifrado_em', datetime('now'))")
    return n


def resumo(con):
    return {"versao": con.execute("PRAGMA user_version").fetchone()[0], "atual": VERSAO_ATUAL,
            "tabelas": [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]}


if __name__ == "__main__":  # pragma: no cover
    import sqlite3
    import sys
    c = sqlite3.connect(sys.argv[1])
    print(json.dumps(resumo(c), ensure_ascii=False, indent=1))
