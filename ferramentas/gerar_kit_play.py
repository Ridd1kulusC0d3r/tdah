#!/usr/bin/env python3
"""Gera as imagens da ficha da Google Play em play/imagens/.

  python3 ferramentas/gerar_kit_play.py

  - icone-512.png            ícone da ficha (512 x 512, PNG, fundo cheio: a Play arredonda os cantos)
  - destaque-1024x500.jpg    gráfico de destaque (JPEG, sem transparência)
  - celular-01..06.jpg       capturas 1080 x 1920 (9:16) do app Android, com os dados de exemplo

As capturas vêm do mesmo www/ que vai para o app (android/preparar-www.py), sem servidor,
exatamente como a pessoa vê depois de instalar. Precisa do Playwright (já usado nos testes).
"""
import functools
import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WWW = RAIZ / "android" / "www"
DEST = RAIZ / "play" / "imagens"

# sem a faixa "Dados de exemplo" e sem o aviso de boas-vindas: a captura mostra o app em uso
LIMPAR = ".banner{display:none!important}.toast{display:none!important}"

TELAS = [
    # arquivo, legenda (vai no topo da captura), passos
    ("celular-01", "Uma ação por vez", ["go:agora"]),
    ("celular-02", "Foco com tempo visível", ["go:agora", "click:[data-act=focus]", "wait:900"]),
    ("celular-03", "Tarefas quebradas em passos pequenos", ["go:tarefas"]),
    ("celular-04", "Rotinas que você toca no automático", ["go:rotinas"]),
    ("celular-05", "Diário de humor, sono e energia", ["go:diario"]),
    ("celular-06", "Leve um resumo para a sua sessão", ["go:mais", "click:[data-act=preparo]", "wait:500"]),
]

MOLDURA = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="fonts/fonts.css">
<style>html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#18211d}
.t{height:300px;display:flex;align-items:center;justify-content:center;padding:0 90px;box-sizing:border-box;text-align:center;
color:#edefea;font:700 76px/1.08 "Atkinson Next",system-ui,sans-serif;letter-spacing:-.02em}
.t b{color:#ffe977;font-weight:700}
.tela{position:absolute;left:90px;top:300px;width:900px;height:1600px;border-radius:44px;overflow:hidden;box-shadow:0 0 0 10px #2c332f}
.tela img{width:100%;display:block}</style></head>
<body><div class="t">TITULO</div><div class="tela"><img src="IMG"></div></body></html>"""

DESTAQUE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="fonts/fonts.css">
<style>html,body{margin:0;width:1024px;height:500px;overflow:hidden;background:#18211d;color:#edefea;font-family:"Atkinson Next",system-ui,sans-serif}
.w{position:absolute;inset:0;display:flex;align-items:center;gap:56px;padding:0 70px}
svg{flex:none;width:250px;height:250px}
h1{margin:0;font-size:84px;line-height:1;letter-spacing:-.03em}
p{margin:18px 0 0;font-size:38px;line-height:1.2;color:#c9d0c7;max-width:600px}
p b{color:#ffe977}</style></head>
<body><div class="w"><svg viewBox="0 0 512 512"><circle cx="256" cy="256" r="196" fill="none" stroke="#edefea" stroke-width="50"/>
<path d="M256 256V88a168 168 0 0 1 159.8 116.1Z" fill="#ffe977"/></svg>
<div><h1>Agora</h1><p>Organização para quem tem TDAH: <b>uma ação por vez</b>, rotinas, foco e diário.</p></div></div></body></html>"""


class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    from playwright.sync_api import sync_playwright
    subprocess.run([sys.executable, str(RAIZ / "android" / "preparar-www.py")], check=True, capture_output=True)
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    shutil.copy2(RAIZ / "app" / "icon-maskable-512.png", DEST / "icone-512.png")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Silencioso, directory=str(WWW)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://agora.test:{srv.server_port}/"
    temp = WWW / "_kit"
    temp.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--host-resolver-rules=MAP agora.test 127.0.0.1"])
        # telas do app: 360 x 640 a 2,5x = 900 x 1600, encaixadas na moldura 1080 x 1920
        ctx = b.new_context(viewport={"width": 360, "height": 640}, device_scale_factor=2.5, is_mobile=True, has_touch=True,
                            color_scheme="light", locale="pt-BR", timezone_id="America/Sao_Paulo")
        pg = ctx.new_page()
        def abrir(recarregar=False):
            pg.reload() if recarregar else pg.goto(base + "index.html")
            pg.wait_for_selector("#exemplo")  # boas-vindas: o exemplo não é salvo, então ela volta a cada abertura
            pg.click("#exemplo")
            pg.wait_for_selector(".now")
            pg.add_style_tag(content=LIMPAR)
        abrir()
        for nome, titulo, passos in TELAS:
            for p in passos:
                tipo, _, arg = p.partition(":")
                if tipo == "go":
                    pg.evaluate("window.scrollTo(0,0)")
                    pg.click(f"[data-go={arg}]")
                elif tipo == "click":
                    pg.click(arg)
                elif tipo == "wait":
                    pg.wait_for_timeout(int(arg))
            pg.wait_for_timeout(350)
            pg.evaluate("window.scrollTo(0,0)")
            pg.add_style_tag(content=LIMPAR)
            pg.screenshot(path=str(temp / f"{nome}.png"))
            if nome == "celular-02":  # sai do foco para seguir
                abrir(True)
        ctx.close()
        # molduras com legenda
        ctx = b.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        pg = ctx.new_page()
        for nome, titulo, _ in TELAS:
            (temp / f"{nome}.html").write_text(MOLDURA.replace("TITULO", titulo).replace("IMG", f"{nome}.png")
                                               .replace("fonts/", "../fonts/"), encoding="utf-8")  # um arquivo por tela: o Chromium guarda em cache
            pg.goto(base + f"_kit/{nome}.html")
            pg.wait_for_load_state("networkidle")
            pg.evaluate("document.fonts.ready")
            pg.screenshot(path=str(DEST / f"{nome}.jpg"), type="jpeg", quality=90)
        ctx.close()
        ctx = b.new_context(viewport={"width": 1024, "height": 500}, device_scale_factor=1)
        pg = ctx.new_page()
        (WWW / "_destaque.html").write_text(DESTAQUE, encoding="utf-8")
        pg.goto(base + "_destaque.html")
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        pg.screenshot(path=str(DEST / "destaque-1024x500.jpg"), type="jpeg", quality=92)
        b.close()
    srv.shutdown()
    shutil.rmtree(temp)
    (WWW / "_destaque.html").unlink()
    for f in sorted(DEST.iterdir()):
        print(f"{f.relative_to(RAIZ)}  {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
