#!/usr/bin/env python3
"""Cópia de segurança do banco SQLite sem parar o servidor, cifrada e (opcional) enviada para S3.

  python3 server/backup.py --db dados/agora.db --destino backups --manter 30
  python3 server/backup.py --restaurar backups/agora-20261114-030000.db.cifrado --db dados/agora-restaurado.db
  python3 server/backup.py --restaurar s3:agora-20261114-030000.db.cifrado --db dados/agora-restaurado.db

A cópia é feita com a API de backup do sqlite3, conferida com PRAGMA integrity_check,
cifrada com a AGORA_CHAVE (ChaCha20-Poly1305 em blocos autenticados) e, se AGORA_S3_BUCKET
estiver configurado, enviada para o armazenamento externo. A cópia em claro é apagada.
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s3  # noqa: E402
from config import Config  # noqa: E402


def fazer(db, destino, manter=30, cfg=None, enviar=True):
    cfg = cfg or Config()
    cofre = cfg.cofre(Path(db).resolve().parent)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"agora-{datetime.now():%Y%m%d-%H%M%S}.db"
    claro = destino / (nome + ".tmp")
    with sqlite3.connect(db) as origem, sqlite3.connect(claro) as copia:
        origem.backup(copia)
        ok = copia.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        claro.unlink(missing_ok=True)
        raise SystemExit(f"cópia corrompida: {ok}")
    cifrado = destino / (nome + ".cifrado")
    cofre.cifrar_arquivo(claro, cifrado)
    claro.unlink()
    remoto = None
    if enviar and cfg.s3_bucket:
        s3.enviar(cfg, cifrado, cifrado.name)
        remoto = f"s3://{cfg.s3_bucket}/{cifrado.name}"
    antigas = sorted(destino.glob("agora-*.db.cifrado"))[:-manter] if manter else []
    for v in antigas:
        v.unlink()
    return {"arquivo": str(cifrado), "kb": cifrado.stat().st_size // 1024, "remoto": remoto, "removidas": len(antigas)}


def restaurar(origem, db_destino, cfg=None):
    cfg = cfg or Config()
    destino = Path(db_destino)
    if destino.exists():
        raise SystemExit(f"{destino} já existe. Restaure para um arquivo novo e troque com o servidor desligado.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    cofre = cfg.cofre(destino.resolve().parent)
    if str(origem).startswith("s3:"):
        local = destino.with_suffix(".baixado")
        s3.baixar(cfg, str(origem)[3:], local)
        origem = local
    cofre.decifrar_arquivo(origem, destino)
    with sqlite3.connect(destino) as c:
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    if ok != "ok":
        raise SystemExit(f"backup restaurado mas o banco falhou na conferência: {ok}")
    return {"banco": str(destino), "usuarios": n}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="dados/agora.db")
    ap.add_argument("--destino", default="backups")
    ap.add_argument("--manter", type=int, default=30, help="quantas cópias antigas manter")
    ap.add_argument("--restaurar", help="arquivo .cifrado (ou s3:nome) para restaurar em --db")
    ap.add_argument("--sem-s3", action="store_true")
    a = ap.parse_args(argv)
    if a.restaurar:
        r = restaurar(a.restaurar, a.db)
        print(f"restaurado: {r['banco']} ({r['usuarios']} conta(s)). Pare o servidor, troque o arquivo e ligue de novo.")
        return
    r = fazer(a.db, a.destino, a.manter, enviar=not a.sem_s3)
    print(f"backup ok: {r['arquivo']} ({r['kb']} KB){' enviado para ' + r['remoto'] if r['remoto'] else ''}; "
          f"{r['removidas']} cópia(s) antiga(s) removida(s)")


if __name__ == "__main__":
    main()
