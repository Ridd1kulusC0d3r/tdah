#!/usr/bin/env python3
"""Copia o app web (../app) para www/ e grava a configuração do Android.

A URL da API vem da variável AGORA_API_URL (ex.: https://agora.seudominio.com.br).
Sem ela, o app funciona só com os dados do aparelho (sem conta, planos ou vínculo).
"""
import json
import os
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ORIGEM = AQUI.parent / "app"
DESTINO = AQUI / "www"
# política pública mesmo sem site hospedado (o GitHub mostra o Markdown); troque por AGORA_PRIVACIDADE_URL quando o site estiver no ar
PRIVACIDADE_PADRAO = "https://github.com/Ridd1kulusC0d3r/tdah/blob/main/PRIVACIDADE.md"
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
# endereço da política de privacidade (a Play exige um link público; o app mostra em Mais)
cfg["privacidade"] = os.environ.get("AGORA_PRIVACIDADE_URL", "").strip() or (api + "/privacidade.html" if api else PRIVACIDADE_PADRAO)
if not api:
    # sem servidor: vitrine com os serviços que podem aparecer no Android (atendimento e interesse), pedidos por e-mail
    sys.path.insert(0, str(AQUI.parent / "server"))
    import catalogo as cat
    from config import Config
    (DESTINO / "catalogo.json").write_text(json.dumps(cat.Catalogo(Config(), None).publico("android", False, ["pessoas"]),
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
(DESTINO / "config.js").write_text(
    "// Gerado por android/preparar-www.py. Não edite à mão.\n"
    f"window.AGORA_CONFIG = {json.dumps(cfg)};\n", encoding="utf-8")
print(f"www/ pronto ({len(list(DESTINO.iterdir()))} arquivos). API: {api or '(nenhuma: só dados do aparelho)'} · privacidade: {cfg['privacidade']}")
