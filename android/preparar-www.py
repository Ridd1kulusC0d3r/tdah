#!/usr/bin/env python3
"""Copia o app web (../app) para www/ e grava a configuração do Android.

A URL da API vem da variável AGORA_API_URL (ex.: https://agora.seudominio.com.br).
Sem ela, o app funciona só com os dados do aparelho (sem conta, planos ou vínculo).
"""
import json
import os
import shutil
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORIGEM = AQUI.parent / "app"
DESTINO = AQUI / "www"
FORA = {"pro.html", "admin.html", "checkout-simulado.html", "sw.js", "manifest.webmanifest"}  # painel, administração e checkout ficam só na web

if DESTINO.exists():
    shutil.rmtree(DESTINO)
DESTINO.mkdir()
for arq in ORIGEM.iterdir():
    if arq.is_file() and arq.name not in FORA:
        shutil.copy2(arq, DESTINO / arq.name)
    elif arq.is_dir() and arq.name == "fonts":  # fontes hospedadas no próprio app
        shutil.copytree(arq, DESTINO / arq.name)
api = os.environ.get("AGORA_API_URL", "").rstrip("/")
cfg = {"plataforma": "android"}
if api:
    cfg["api"] = api
(DESTINO / "config.js").write_text(
    "// Gerado por android/preparar-www.py. Não edite à mão.\n"
    f"window.AGORA_CONFIG = {json.dumps(cfg)};\n", encoding="utf-8")
print(f"www/ pronto ({len(list(DESTINO.iterdir()))} arquivos). API: {api or '(nenhuma: só dados do aparelho)'}")
