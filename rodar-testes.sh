#!/usr/bin/env bash
# Roda os testes da API (só Python) e, se o Playwright estiver instalado, o teste de navegador.
cd "$(dirname "$0")"
python3 -m unittest tests.test_api tests.test_producao -v || exit 1
if python3 -c "import playwright" 2>/dev/null; then python3 tests/test_ui.py; else
  echo "Playwright não instalado: pulei o teste de navegador (pip install playwright && playwright install chromium)."; fi
