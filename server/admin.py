#!/usr/bin/env python3
"""Ferramenta de administração do Agora (linha de comando).

  python3 server/admin.py chave                      gera uma AGORA_CHAVE nova (cole no .env)
  python3 server/admin.py vapid                      gera o par de chaves das notificações push
  python3 server/admin.py promover EMAIL             dá acesso de administrador a uma conta
  python3 server/admin.py rebaixar EMAIL             tira o acesso de administrador
  python3 server/admin.py zerar-2fa EMAIL            desliga a verificação em duas etapas (celular perdido)
  python3 server/admin.py recifrar                   recifra o banco com a chave atual (depois de trocar a chave)
  python3 server/admin.py tarefas                    roda lembretes, e-mails de conteúdo e retenção uma vez
  python3 server/admin.py conferir                   mostra o que falta configurar para produção
  python3 server/admin.py estado                     resumo do banco e da migração

Todas aceitam --db caminho/agora.db (padrão: AGORA_DB ou dados/agora.db).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cripto  # noqa: E402
import migracoes  # noqa: E402
import push  # noqa: E402
from config import RAIZ, Config  # noqa: E402


def _api(db):
    import server
    return server.API(server.Banco(db), Config())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Administração do Agora")
    ap.add_argument("comando", choices=["chave", "vapid", "promover", "rebaixar", "zerar-2fa", "recifrar", "tarefas", "conferir", "estado"])
    ap.add_argument("email", nargs="?")
    ap.add_argument("--db", default=os.environ.get("AGORA_DB", str(RAIZ / "dados" / "agora.db")))
    a = ap.parse_args(argv)

    if a.comando == "chave":
        print("AGORA_CHAVE=" + cripto.nova_chave_texto())
        print("# Guarde uma cópia desta chave fora do servidor (gerenciador de senhas). Sem ela, banco e backups não abrem.")
        return 0
    if a.comando == "vapid":
        priv, pub = push.gerar_chaves()
        print(f"AGORA_VAPID_PRIVADA={priv}\nAGORA_VAPID_PUBLICA={pub}")
        return 0
    if a.comando == "conferir":
        faltas = Config().avisos_producao()
        print("Tudo configurado." if not faltas else "Falta configurar:\n  - " + "\n  - ".join(faltas))
        return 0 if not [f for f in faltas if "opcional" not in f and "recomendado" not in f] else 1

    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    api = _api(a.db)
    con = api.db.con()
    try:
        if a.comando in ("promover", "rebaixar", "zerar-2fa"):
            if not a.email:
                raise SystemExit("Informe o e-mail da conta.")
            r = con.execute("SELECT id, nome FROM usuarios WHERE email=?", (a.email.strip().lower(),)).fetchone()
            if not r:
                raise SystemExit("Conta não encontrada. A pessoa precisa criar a conta antes no app ou no painel.")
            if a.comando == "zerar-2fa":
                con.execute("UPDATE usuarios SET totp_segredo=NULL, totp_pendente=NULL, totp_rec=NULL WHERE id=?", (r["id"],))
                con.execute("DELETE FROM tokens WHERE usuario_id=?", (r["id"],))
                api.audita(con, None, "2fa_zerada_cli", r["id"])
                print(f"Verificação em duas etapas desligada para {r['nome']}. As sessões abertas foram encerradas.")
            else:
                con.execute("UPDATE usuarios SET admin=? WHERE id=?", (1 if a.comando == "promover" else 0, r["id"]))
                api.audita(con, None, "admin_" + a.comando, r["id"])
                print(f"{r['nome']} {'agora é' if a.comando == 'promover' else 'deixou de ser'} administrador."
                      + (" No primeiro acesso a /app/admin.html será pedido para ligar a verificação em duas etapas." if a.comando == "promover" else ""))
            con.commit()
        elif a.comando == "recifrar":
            n = migracoes.cifrar_legado(con, api.cofre)
            con.commit()
            print(f"{n} campo(s) recifrado(s) com a chave atual. Já pode tirar a chave antiga de AGORA_CHAVES_ANTIGAS.")
        elif a.comando == "tarefas":
            api._ultima_hora = None
            print(json.dumps(api.tarefas_periodicas(), ensure_ascii=False))
        elif a.comando == "estado":
            print(json.dumps({**migracoes.resumo(con), "usuarios": con.execute("SELECT papel, COUNT(*) FROM usuarios GROUP BY papel").fetchall(),
                              "admins": [r[0] for r in con.execute("SELECT email FROM usuarios WHERE admin=1")]}, ensure_ascii=False, default=list))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
