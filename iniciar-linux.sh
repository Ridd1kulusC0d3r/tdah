#!/usr/bin/env bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 não foi encontrado. Instale com: sudo apt install python3  (ou o gerenciador da sua distro)"
  read -r -p "Aperte Enter para fechar." _; exit 1
fi
[ -f dados/agora.db ] || { echo "Preparando o caso de demonstração..."; python3 server/seed_demo.py; }
( sleep 1.5; xdg-open "http://localhost:8765/app/" >/dev/null 2>&1 || true ) &
python3 server/server.py "$@"
