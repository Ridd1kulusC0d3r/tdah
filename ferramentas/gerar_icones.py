#!/usr/bin/env python3
"""Gera o ícone do Agora (web e Android) e as telas de abertura do Android.

Marca: um relógio de tinta verde-escura com a fatia do "agora" em amarelo marca-texto.
Uso: python3 ferramentas/gerar_icones.py   (requer Pillow)
"""
from pathlib import Path
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
TINTA, PAPEL, MARCA = (24, 33, 29), (237, 239, 234), (255, 233, 119)
RES = RAIZ / "android" / "android" / "app" / "src" / "main" / "res"
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="116" fill="#18211d"/>'
       '<circle cx="256" cy="256" r="148" fill="none" stroke="#edefea" stroke-width="38"/>'
       '<path d="M256 256V129a127 127 0 0 1 120.8 87.8Z" fill="#ffe977"/></svg>\n')


def marca(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float):
    """Anel claro + fatia amarela de 12h até ~2h20 (72°)."""
    w = r * 38 / 148
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=PAPEL, width=round(w))
    ri = r * 127 / 148
    d.pieslice([cx - ri, cy - ri, cx + ri, cy + ri], start=-90, end=-18, fill=MARCA)


def icone(lado: int, redondo=False, fundo=True, escala=1.0) -> Image.Image:
    k = 4  # desenha grande e reduz, para bordas suaves
    L = lado * k
    im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if fundo:
        if redondo:
            d.ellipse([0, 0, L - 1, L - 1], fill=TINTA)
        else:
            d.rounded_rectangle([0, 0, L - 1, L - 1], radius=L * 116 / 512, fill=TINTA)
    marca(d, L / 2, L / 2, L * 148 / 512 * escala)
    return im.resize((lado, lado), Image.LANCZOS)


def main():
    (RAIZ / "app" / "icon.svg").write_text(SVG, encoding="utf-8")
    for n in (192, 512):
        icone(n).save(RAIZ / "app" / f"icon-{n}.png")
    if not RES.exists():
        print("ícones web prontos (projeto Android não encontrado)")
        return
    dens = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for nome, f in dens.items():
        pasta = RES / f"mipmap-{nome}"
        if not pasta.exists():
            continue
        icone(round(48 * f)).save(pasta / "ic_launcher.png")
        icone(round(48 * f), redondo=True).save(pasta / "ic_launcher_round.png")
        # primeiro plano adaptativo: 108 dp, área segura de 66 dp no centro
        icone(round(108 * f), fundo=False, escala=0.62).save(pasta / "ic_launcher_foreground.png")
    cor = RES / "values" / "ic_launcher_background.xml"
    if cor.exists():
        cor.write_text('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#18211D</color>\n</resources>\n', encoding="utf-8")
    for splash in RES.glob("drawable*/splash.png"):
        w, h = Image.open(splash).size
        im = Image.new("RGB", (w, h), TINTA)
        lado = round(min(w, h) * 0.34)
        m = icone(lado, fundo=False, escala=1.25)
        im.paste(m, ((w - lado) // 2, (h - lado) // 2), m)
        im.save(splash)
    print("ícones e telas de abertura gerados")


if __name__ == "__main__":
    main()
