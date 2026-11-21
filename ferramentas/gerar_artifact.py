#!/usr/bin/env python3
"""Gera dist/agora-artifact.html: o app do paciente sem o esqueleto do documento,
para publicar como página hospedada (o host adiciona doctype/head/body)."""
import re
from pathlib import Path
raiz = Path(__file__).resolve().parent.parent
s = (raiz / "app" / "index.html").read_text(encoding="utf-8")
head = re.search(r"<head>(.*?)</head>", s, re.S).group(1)
body = re.search(r"<body>(.*?)</body>", s, re.S).group(1)
head = re.sub(r'<meta charset[^>]*>\s*|<meta name="viewport"[^>]*>\s*|<link rel="(manifest|icon)"[^>]*>\s*', "", head)
# a página publicada não tem a pasta fonts/: embute as fontes em base64
import base64
fontes = raiz / "app" / "fonts"
css = (fontes / "fonts.css").read_text(encoding="utf-8")
for arq in fontes.glob("*.woff2"):
    css = css.replace(f"url({arq.name})", "url(data:font/woff2;base64," + base64.b64encode(arq.read_bytes()).decode() + ")")
head = head.replace('<link rel="stylesheet" href="fonts/fonts.css">', "<style>" + css + "</style>")
out = head.strip() + "\n" + body.strip() + "\n"
(raiz / "dist" / "agora-artifact.html").write_text(out, encoding="utf-8")
print("dist/agora-artifact.html", len(out), "bytes")
