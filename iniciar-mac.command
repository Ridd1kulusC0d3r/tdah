#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "  Python 3 não foi encontrado."
  echo "  Instale em https://www.python.org/downloads/ e dê dois cliques neste arquivo de novo."
  echo ""
  read -n 1 -s -r -p "Aperte qualquer tecla para fechar."
  exit 1
fi
[ -f dados/agora.db ] || { echo "Preparando o caso de demonstração..."; python3 server/seed_demo.py; }
( sleep 1.5; open "http://localhost:8765/app/" ) &
python3 server/server.py
