#!/usr/bin/env python3
"""Gera prototipo/: o Agora como site estático, pronto para publicar sem servidor.

Funciona em qualquer hospedagem de arquivos (Netlify Drop, Cloudflare Pages, GitHub Pages,
Vercel), na raiz de um domínio ou numa subpasta, e até aberto direto do disco.
  - site público (início, começar, serviços, páginas legais) com links relativos;
  - app do paciente completo, com dados de exemplo, guardando tudo no aparelho;
  - catálogo de serviços em modo vitrine: pedidos viram e-mail para a equipe;
  - sem contas, vínculo, pagamentos nem administração (precisam do servidor);
  - faixa "Protótipo" em todas as páginas e noindex (fora do Google até o lançamento).

  python3 ferramentas/gerar_prototipo.py        → prototipo/ e dist/agora-prototipo.zip
"""
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "server"))
DEST = RAIZ / "prototipo"
APP_FORA = {"admin.html", "checkout-simulado.html", "pro.html"}  # precisam do servidor

FAIXA = ('<div style="position:sticky;top:0;z-index:99;background:#ffe977;color:#18211d;font:600 14px/1.35 system-ui,sans-serif;'
         'padding:8px 16px;text-align:center">Protótipo: os dados ficam só no seu aparelho. Contas, vínculo com o psicólogo e pagamentos '
         'chegam na versão de lançamento.</div>')

PRO_PLACEHOLDER = '''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Painel do psicólogo · Agora</title>
<link rel="icon" href="icon.svg" type="image/svg+xml"><link rel="stylesheet" href="fonts/fonts.css">
<style>body{margin:0;background:#edefea;color:#18211d;font:17px/1.6 "Atkinson Next",system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;padding:16px}
main{max-width:34rem;background:#fff;border:1px solid #d5d9d1;border-radius:16px;padding:28px}h1{font-size:1.9rem;line-height:1.1;margin:0 0 12px;letter-spacing:-.02em}
a.b{display:inline-block;margin-top:14px;background:#0b6b57;color:#fff;text-decoration:none;font-weight:700;padding:12px 18px;border-radius:10px}
@media (prefers-color-scheme:dark){body{background:#111513;color:#e7ebe6}main{background:#191e1b;border-color:#2c332f}}</style></head>
<body><main><h1>Painel do psicólogo</h1>
<p>No lançamento, o psicólogo acompanha entre as sessões o que o paciente escolheu compartilhar, prescreve rotinas e recebe um resumo pronto para cada consulta. Até 3 pacientes de graça.</p>
<p>Quer testar no piloto com seus pacientes? Escreva para a equipe.</p>
<a class="b" href="mailto:CONTATO?subject=Piloto%20do%20painel%20do%20Agora">Quero entrar no piloto</a>
<p style="margin-top:18px"><a href="../index.html">Voltar ao site</a> · <a href="index.html">Abrir o app do paciente</a></p></main></body></html>
'''


def relativizar(html, nivel):
    """Troca caminhos absolutos do servidor por relativos (funciona em subpasta e no disco)."""
    pre = "../" * nivel
    trocas = [('"/app/fonts/fonts.css"', f'"{pre}app/fonts/fonts.css"'), ('"/app/icon.svg"', f'"{pre}app/icon.svg"'),
              ('"/app/pro.html"', f'"{pre}app/pro.html"'), ('"/app/#', f'"{pre}app/index.html#'), ('"/app/"', f'"{pre}app/index.html"'),
              ('"/servicos"', f'"{pre}servicos.html"'), ('"/comecar"', f'"{pre}comecar.html"'), ('"/#', f'"{pre}index.html#'),
              ('"/doc.css"', f'"{pre}doc.css"'), ('"/"', f'"{pre}index.html"')]
    for a, b in trocas:
        html = html.replace(a, b)
    html = re.sub(r'"/(privacidade|termos|excluir-conta)\.html"', lambda m: f'"{pre}{m.group(1)}.html"', html)
    return html


def marcar(html):
    html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1)
    return re.sub(r"(<body[^>]*>)", r"\1" + FAIXA.replace("\\", "\\\\"), html, count=1)


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    (DEST / "app").mkdir(parents=True)
    # catálogo público (mesmas regras do servidor: só o que aparece no app, com responsável técnico)
    import catalogo as cat
    from config import Config
    publico = cat.Catalogo(Config(), None).publico("web", False)
    contato = publico["responsavel"]["contato"]
    texto_cat = json.dumps(publico, ensure_ascii=False, indent=1)
    texto_cat_app = json.dumps(cat.Catalogo(Config(), None).publico("web", False, ["pessoas"]), ensure_ascii=False, indent=1)

    # páginas legais: as do protótipo descrevem o que esta versão faz (nada sai do aparelho) e não têm lacunas;
    # as de site/ são da versão com servidor e ficam para o lançamento completo.
    cfg = Config()
    legais = RAIZ / "ferramentas" / "prototipo_legal"
    from datetime import date
    trocas = {"{{CONTATO}}": contato, "{{RESP_NOME}}": cfg.responsavel_nome, "{{RESP_CRP}}": cfg.responsavel_crp,
              "{{DATA}}": date.today().strftime("%d/%m/%Y")}
    for arq in (RAIZ / "site").iterdir():
        if arq.suffix == ".html":
            fonte = legais / arq.name if (legais / arq.name).exists() else arq
            html = fonte.read_text(encoding="utf-8")
            for a, b in trocas.items():
                html = html.replace(a, b)
            assert "[" + "NOME" not in html and "{{" not in html, f"lacuna em {arq.name}"
            (DEST / arq.name).write_text(marcar(relativizar(html, 0)), encoding="utf-8")
        elif arq.is_file():
            shutil.copy2(arq, DEST / arq.name)
    (DEST / "catalogo.json").write_text(texto_cat, encoding="utf-8")

    for arq in (RAIZ / "app").iterdir():
        if arq.name in APP_FORA:
            continue
        if arq.is_dir():
            shutil.copytree(arq, DEST / "app" / arq.name)
        elif arq.suffix == ".html":
            (DEST / "app" / arq.name).write_text(marcar(arq.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            shutil.copy2(arq, DEST / "app" / arq.name)
    (DEST / "app" / "catalogo.json").write_text(texto_cat_app, encoding="utf-8")  # app: só "Para você"
    (DEST / "app" / "pro.html").write_text(PRO_PLACEHOLDER.replace("CONTATO", contato), encoding="utf-8")

    # hospedagens: GitHub Pages (sem Jekyll), Netlify e Cloudflare Pages (cabeçalhos e endereços curtos)
    (DEST / ".nojekyll").write_text("")
    (DEST / "_headers").write_text("""/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  X-Robots-Tag: noindex
""")
    (DEST / "_redirects").write_text("/servicos /servicos.html 200\n/comecar /comecar.html 200\n/app /app/index.html 200\n")
    (DEST / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (DEST / "PUBLICAR.md").write_text(PUBLICAR, encoding="utf-8")

    (RAIZ / "dist").mkdir(exist_ok=True)
    zipar = RAIZ / "dist" / "agora-prototipo.zip"
    with zipfile.ZipFile(zipar, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(DEST.rglob("*")):
            if f.is_file():
                z.write(f, Path("agora-prototipo") / f.relative_to(DEST))
    n = sum(1 for f in DEST.rglob("*") if f.is_file())
    print(f"prototipo/ com {n} arquivos · {zipar.relative_to(RAIZ)} {zipar.stat().st_size / 1e6:.2f} MB")


PUBLICAR = """# Publicar o protótipo do Agora

Esta pasta é o Agora como site estático: não precisa de servidor, banco nem Python.
O app do paciente funciona completo, com dados de exemplo, e guarda tudo no aparelho de quem usa.
Contas, vínculo com o psicólogo, pagamentos e administração ficam para a versão de lançamento.

Todas as páginas têm a faixa amarela "Protótipo" e pedem para não aparecer no Google (noindex).

## Jeito mais rápido: Netlify Drop (2 minutos)

1. Abra https://app.netlify.com/drop e entre com sua conta (Google ou GitHub servem).
2. Arraste **esta pasta inteira** (agora-prototipo) para a área pontilhada.
3. Pronto: o Netlify mostra um endereço como `https://nome-aleatorio.netlify.app`.
   Em *Site configuration › Change site name* você troca para algo como `agora-prototipo`.

## Cloudflare Pages

1. https://dash.cloudflare.com › Workers & Pages › Create › Pages › **Upload assets**.
2. Dê um nome ao projeto, arraste esta pasta e clique em *Deploy*.
3. Para usar seu domínio: *Custom domains* › `prototipo.seudominio.com.br`.

## GitHub Pages (quando criar o repositório)

1. No repositório, crie a pasta `docs/` ou um repositório só para o protótipo e suba o conteúdo desta pasta.
2. Settings › Pages › Source: *Deploy from a branch* › branch `main`, pasta `/` (ou `/docs`).
3. O endereço fica `https://SEU-USUARIO.github.io/NOME-DO-REPO/`. Os links são relativos, então funciona em subpasta.

## Endereços

| Página | Caminho |
|---|---|
| Site | `index.html` |
| Por onde começar | `comecar.html` |
| Serviços (vitrine; pedidos viram e-mail) | `servicos.html` |
| App do paciente (instalável no celular) | `app/index.html` |
| Painel do psicólogo (convite para o piloto) | `app/pro.html` |

## Antes de divulgar

- [ ] Conferir o e-mail de contato que aparece nos botões e nas páginas legais (vem de `AGORA_CONTATO_PUBLICO`).
- [ ] Ler `privacidade.html` e `termos.html` desta pasta: são as versões da demonstração, sem campos em aberto.
- [ ] Abrir no celular e instalar o app pela opção "Adicionar à tela inicial".

Para gerar de novo depois de mudar o app: `python3 ferramentas/gerar_prototipo.py`.
"""

if __name__ == "__main__":
    main()
