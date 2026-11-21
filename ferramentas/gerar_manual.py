#!/usr/bin/env python3
"""Gera docs/manual.html: manual ilustrado e autocontido (capturas embutidas, sem internet).

Entradas: docs/capturas/*.png + marcas.json (geradas por tests/test_ui.py),
docs/resultado-testes-ui.json e docs/resultado-testes-api.txt.
"""
import base64
import html
import io
import json
import re
from datetime import datetime
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
CAP = RAIZ / "docs" / "capturas"
MARCAS = json.loads((CAP / "marcas.json").read_text(encoding="utf-8"))
E = html.escape


def img_b64(nome, largura_max=1100):
    im = Image.open(CAP / f"{nome}.png").convert("RGB")
    w, h = im.size
    if w > largura_max:
        im = im.resize((largura_max, round(h * largura_max / w)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=78, method=5)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def figura(nome, titulo, estreita=False):
    m = MARCAS.get(nome, {"w": 1, "h": 1, "marcas": []})
    pontos = "".join(
        f'<span class="mk" style="left:{100 * k["x"] / m["w"]:.2f}%;top:{100 * k["y"] / m["h"]:.2f}%">{i}</span>'
        for i, k in enumerate(m["marcas"], 1))
    leg = "".join(f"<li><b>{i}</b>{E(k['rotulo'])}</li>" for i, k in enumerate(m["marcas"], 1))
    return f'''<figure class="shot{' narrow' if estreita else ''}"><div class="frame"><img src="{img_b64(nome)}" alt="{E(titulo)}" loading="lazy">{pontos}</div>
<figcaption><span class="label">{E(titulo)}</span>{f'<ol class="leg">{leg}</ol>' if leg else ''}</figcaption></figure>'''


# ---------------- diagramas SVG ----------------
SVG_COMO = '''<svg viewBox="0 0 760 300" role="img" aria-label="Como funciona: o app do paciente guarda os dados no aparelho, envia só o que foi autorizado ao servidor da clínica, e o painel do profissional lê esses dados e devolve prescrições">
<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--ink)"/></marker></defs>
<rect x="10" y="40" width="210" height="200" rx="16" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/>
<text x="115" y="72" text-anchor="middle" font-weight="700" fill="var(--ink)" font-size="15">App do paciente</text>
<text x="115" y="94" text-anchor="middle" fill="var(--muted)" font-size="12">celular ou computador</text>
<rect x="30" y="112" width="170" height="40" rx="8" fill="var(--sunk)"/><text x="115" y="137" text-anchor="middle" fill="var(--ink)" font-size="12">Tarefas · rotinas · foco</text>
<rect x="30" y="160" width="170" height="40" rx="8" fill="var(--sunk)"/><text x="115" y="185" text-anchor="middle" fill="var(--ink)" font-size="12">Diário · painel · triagem</text>
<text x="115" y="224" text-anchor="middle" fill="var(--muted)" font-size="11">tudo salvo no aparelho</text>
<rect x="275" y="70" width="210" height="140" rx="16" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/>
<text x="380" y="102" text-anchor="middle" font-weight="700" fill="var(--ink)" font-size="15">Servidor da clínica</text>
<text x="380" y="124" text-anchor="middle" fill="var(--muted)" font-size="12">server.py + agora.db</text>
<rect x="295" y="140" width="170" height="44" rx="8" fill="var(--accent-soft)" stroke="var(--accent)"/><text x="380" y="160" text-anchor="middle" fill="var(--ink)" font-size="12" font-weight="700">Filtro de consentimento</text><text x="380" y="176" text-anchor="middle" fill="var(--muted)" font-size="11">só grava o que foi liberado</text>
<rect x="540" y="40" width="210" height="200" rx="16" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/>
<text x="645" y="72" text-anchor="middle" font-weight="700" fill="var(--ink)" font-size="15">Painel do profissional</text>
<text x="645" y="94" text-anchor="middle" fill="var(--muted)" font-size="12">navegador do consultório</text>
<rect x="560" y="112" width="170" height="40" rx="8" fill="var(--sunk)"/><text x="645" y="137" text-anchor="middle" fill="var(--ink)" font-size="12">Adesão · gráficos · resumo</text>
<rect x="560" y="160" width="170" height="40" rx="8" fill="var(--sunk)"/><text x="645" y="185" text-anchor="middle" fill="var(--ink)" font-size="12">Prescrever rotina e recado</text>
<path d="M222 120 L272 120" stroke="var(--ink)" stroke-width="2" marker-end="url(#ar)"/><text x="247" y="110" text-anchor="middle" fill="var(--ink)" font-size="11">dados</text>
<path d="M487 120 L537 120" stroke="var(--ink)" stroke-width="2" marker-end="url(#ar)"/><text x="512" y="110" text-anchor="middle" fill="var(--ink)" font-size="11">leitura</text>
<path d="M537 190 L487 190" stroke="var(--accent)" stroke-width="2" marker-end="url(#ar)"/><text x="512" y="208" text-anchor="middle" fill="var(--accent)" font-size="11">prescrição</text>
<path d="M272 190 L222 190" stroke="var(--accent)" stroke-width="2" marker-end="url(#ar)"/><text x="247" y="208" text-anchor="middle" fill="var(--accent)" font-size="11">volta</text>
<text x="380" y="278" text-anchor="middle" fill="var(--muted)" font-size="12">Sem servidor, o app do paciente funciona sozinho. O servidor só entra quando há vínculo com um profissional.</text>
</svg>'''

ETAPAS = [("Abre o app", "uma próxima ação"), ("Humor em 1 toque", "ajusta a energia"), ("Começa o foco", "timer + som + sala"),
          ("Registra", "fluiu, ok ou travei"), ("Painel", "padrões de sono e humor"), ("Profissional", "vê adesão e prescreve")]


def fontes_embutidas():
    """As fontes do app, embutidas em base64: o manual abre igual sem internet."""
    import base64
    pasta = RAIZ / "app" / "fonts"
    b = lambda n: base64.b64encode((pasta / n).read_bytes()).decode()
    return ("@font-face{font-family:'Atkinson Next';font-weight:200 800;font-display:swap;src:url(data:font/woff2;base64," + b("next-latin.woff2") + ") format('woff2')}"
            "@font-face{font-family:'Atkinson Next';font-weight:200 800;font-display:swap;unicode-range:U+0100-024F,U+1E00-1EFF;src:url(data:font/woff2;base64," + b("next-latin-ext.woff2") + ") format('woff2')}"
            "@font-face{font-family:'Atkinson Mono';font-weight:400;font-display:swap;src:url(data:font/woff2;base64," + b("mono-400.woff2") + ") format('woff2')}")


def svg_jornada():
    w, n = 760, len(ETAPAS)
    passo = (w - 40) / n
    g = []
    for i, (a, b) in enumerate(ETAPAS):
        cx = 20 + passo * i + passo / 2
        if i < n - 1:
            g.append(f'<path d="M{cx + 30:.0f} 70 L{cx + passo - 30:.0f} 70" stroke="var(--line)" stroke-width="3"/>')
        cor = "var(--accent)" if i in (0, 2) else "var(--deep)"
        g.append(f'<circle cx="{cx:.0f}" cy="70" r="26" fill="{cor}"/><text x="{cx:.0f}" y="76" text-anchor="middle" fill="var(--bg)" font-weight="700" font-size="16">{i + 1}</text>')
        g.append(f'<text x="{cx:.0f}" y="122" text-anchor="middle" fill="var(--ink)" font-weight="700" font-size="13">{E(a)}</text>')
        g.append(f'<text x="{cx:.0f}" y="141" text-anchor="middle" fill="var(--muted)" font-size="11.5">{E(b)}</text>')
    g.append(f'<path d="M{20 + passo * (n - 0.5):.0f} 160 C {20 + passo * (n - 0.5):.0f} 200, {20 + passo * 0.5:.0f} 200, {20 + passo * 0.5:.0f} 160" fill="none" stroke="var(--accent)" stroke-width="2" stroke-dasharray="5 5"/>')
    g.append(f'<text x="{w / 2:.0f}" y="210" text-anchor="middle" fill="var(--accent)" font-size="12">a rotina prescrita aparece no Agora do paciente</text>')
    return f'<svg viewBox="0 0 {w} 225" role="img" aria-label="Jornada de uso em seis etapas, do app aberto à prescrição do profissional">{"".join(g)}</svg>'


SVG_ARQ = '''<svg viewBox="0 0 760 330" role="img" aria-label="Arquitetura: app web e Android, servidor Python com SQLite, provedores de pagamento e Google Play">
<g font-size="12" fill="var(--ink)">
<rect x="10" y="14" width="235" height="150" rx="12" fill="var(--surface)" stroke="var(--line)" stroke-width="2"/>
<text x="24" y="38" font-weight="700">app/ (web e PWA)</text>
<text x="24" y="60">index.html: paciente, 1 arquivo</text><text x="24" y="78">pro.html: painel do psicólogo</text>
<text x="24" y="96">checkout-simulado.html</text><text x="24" y="114">localStorage + sw.js offline</text><text x="24" y="132">Web Audio, Notification API</text>
<text x="24" y="152" fill="var(--muted)">config.js define a API</text>
<rect x="10" y="176" width="235" height="140" rx="12" fill="var(--surface)" stroke="var(--line)" stroke-width="2"/>
<text x="24" y="200" font-weight="700">android/ (Capacitor 8)</text>
<text x="24" y="222">mesmo app web empacotado</text><text x="24" y="240">notificações locais nativas</text><text x="24" y="258">não vende Plus (regra da Play)</text>
<text x="24" y="276">GitHub Actions gera APK e AAB</text><text x="24" y="304" fill="var(--muted)">br.com.agoratdah.app</text>
<rect x="265" y="14" width="235" height="302" rx="12" fill="var(--surface)" stroke="var(--accent)" stroke-width="2"/>
<text x="280" y="38" font-weight="700">server/ (Python, só stdlib)</text>
<text x="280" y="60">server.py: rotas e API</text><text x="280" y="78">pagamentos.py: planos, eventos</text><text x="280" y="96">google_play.py: JWT RS256 próprio</text>
<text x="280" y="114">email_envio.py: smtplib</text><text x="280" y="132">config.py: lê o .env</text><text x="280" y="150">backup.py: cópia do SQLite</text>
<text x="280" y="176">PBKDF2 · tokens só como hash</text><text x="280" y="194">limite de tentativas de login</text><text x="280" y="212">consentimento aplicado aqui</text>
<text x="280" y="230">webhooks com assinatura HMAC</text><text x="280" y="248">eventos idempotentes</text><text x="280" y="266">auditoria de acesso</text>
<text x="280" y="300" fill="var(--muted)">site/ servido em /</text>
<rect x="520" y="14" width="230" height="150" rx="12" fill="var(--surface)" stroke="var(--line)" stroke-width="2"/>
<text x="534" y="38" font-weight="700">Provedores</text>
<text x="534" y="60">Mercado Pago: Pix, cartão,</text><text x="534" y="78">boleto e assinatura</text><text x="534" y="100">Stripe: alternativa</text>
<text x="534" y="122">Google Play Billing (fase 2)</text><text x="534" y="150" fill="var(--muted)">webhook → /api/webhooks/...</text>
<rect x="520" y="176" width="230" height="140" rx="12" fill="var(--surface)" stroke="var(--line)" stroke-width="2"/>
<text x="534" y="200" font-weight="700">Produção</text>
<text x="534" y="222">Docker + Caddy (HTTPS)</text><text x="534" y="240">ou systemd + proxy</text><text x="534" y="258">SQLite num volume</text><text x="534" y="276">backup diário, 30 cópias</text>
<text x="534" y="304" fill="var(--muted)">tests/: unittest + Playwright</text>
</g>
<g stroke="var(--ink)" stroke-width="1.6" fill="none"><path d="M247 90 H262"/><path d="M247 245 H262"/><path d="M502 90 H517"/><path d="M502 245 H517"/></g>
</svg>'''

SVG_PAG = '''<svg viewBox="0 0 760 250" role="img" aria-label="Fluxo do pagamento: o app pede o checkout ao servidor, a pessoa paga no provedor, o provedor avisa o servidor por webhook assinado e o servidor libera o Plus">
<defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--ink)"/></marker></defs>
<g font-size="12" fill="var(--ink)" text-anchor="middle">
<rect x="10" y="40" width="160" height="90" rx="12" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/><text x="90" y="72" font-weight="700" font-size="14">App</text><text x="90" y="94">toca em Assinar</text><text x="90" y="112" fill="var(--muted)">Mais › Planos</text>
<rect x="205" y="40" width="160" height="90" rx="12" fill="var(--surface)" stroke="var(--accent)" stroke-width="2"/><text x="285" y="72" font-weight="700" font-size="14">Servidor</text><text x="285" y="94">cria o checkout</text><text x="285" y="112" fill="var(--muted)">guarda o pedido</text>
<rect x="400" y="40" width="160" height="90" rx="12" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/><text x="480" y="72" font-weight="700" font-size="14">Provedor</text><text x="480" y="94">página de pagamento</text><text x="480" y="112" fill="var(--muted)">Pix, cartão, boleto</text>
<rect x="595" y="40" width="155" height="90" rx="12" fill="var(--surface)" stroke="var(--good)" stroke-width="2"/><text x="672" y="72" font-weight="700" font-size="14">Plus liberado</text><text x="672" y="94">até o fim do período</text><text x="672" y="112" fill="var(--muted)">+3 dias de carência</text>
</g>
<g stroke="var(--ink)" stroke-width="1.8" fill="none"><path d="M172 72 H202" marker-end="url(#seta)"/><path d="M367 72 H397" marker-end="url(#seta)"/></g>
<path d="M480 132 C480 200, 285 200, 285 134" stroke="var(--accent)" stroke-width="1.8" fill="none" marker-end="url(#seta)"/>
<path d="M367 108 C460 108, 520 160, 593 108" stroke="var(--good)" stroke-width="1.8" fill="none" stroke-dasharray="5 4" marker-end="url(#seta)"/>
<g font-size="11.5" text-anchor="middle"><text x="187" y="62" fill="var(--ink)">1</text><text x="382" y="62" fill="var(--ink)">2 redireciona</text>
<text x="382" y="214" fill="var(--accent)">3 webhook assinado (HMAC) → o servidor confere e consulta a API do provedor</text>
<text x="560" y="150" fill="var(--good)">4 libera</text></g>
<text x="380" y="242" font-size="11.5" text-anchor="middle" fill="var(--muted)">O payload do webhook nunca é confiado sozinho; cada evento é gravado uma vez só (idempotente).</text>
</svg>'''

SVG_LEGENDA = '''<svg viewBox="0 0 760 90" role="img" aria-label="Legenda dos símbolos usados no manual e no app">
<g font-size="12.5" fill="var(--ink)">
<circle cx="24" cy="24" r="13" fill="#ffe977" stroke="#18211d" stroke-width="2"/><text x="24" y="29" text-anchor="middle" fill="#18211d" font-weight="800">1</text><text x="46" y="29">Marcador da captura: veja o item com o mesmo número abaixo da imagem</text>
<rect x="11" y="52" width="60" height="22" rx="5" fill="var(--hl)"/><text x="41" y="67" text-anchor="middle" fill="var(--ink)" font-weight="700" font-size="11">prescrita</text><text x="84" y="67">Veio do profissional</text>
<rect x="200" y="52" width="66" height="22" rx="6" fill="var(--bad)"/><text x="233" y="67" text-anchor="middle" fill="#fff" font-weight="700" font-size="11">!!! Alta</text><text x="276" y="67">Prioridade</text><circle cx="380" cy="63" r="11" fill="var(--m1)"/><circle cx="406" cy="63" r="11" fill="var(--m3)"/><circle cx="432" cy="63" r="11" fill="var(--m5)"/><text x="452" y="67">Carinhas: azul = pra baixo, cinza = neutro, laranja = muito bem</text>
</g></svg>'''

SVG_TERMINAL = '''<svg viewBox="0 0 640 220" role="img" aria-label="Janela preta que abre ao dar dois cliques no lançador, com os endereços do app e do painel">
<rect x="1" y="1" width="638" height="218" rx="10" fill="#0f1420" stroke="#2f3a4f"/><rect x="1" y="1" width="638" height="30" rx="10" fill="#1a2130"/>
<circle cx="20" cy="16" r="5" fill="#ff6b6b"/><circle cx="38" cy="16" r="5" fill="#ffd43b"/><circle cx="56" cy="16" r="5" fill="#69db7c"/>
<g font-family="Atkinson Mono, Consolas, monospace" font-size="13" fill="#e8ecf3">
<text x="18" y="58">Caso de demonstração pronto. Senha de todas as contas: demo1234</text>
<text x="18" y="84">Agora TDAH 1.3.0 no ar (desenvolvimento).</text>
<text x="18" y="108">  App do paciente ....... <tspan fill="#ffe977">http://localhost:8765/app/</tspan></text>
<text x="18" y="132">  Painel do profissional  <tspan fill="#8fb0ff">http://localhost:8765/app/pro.html</tspan></text>
<text x="18" y="156">  Banco de dados ........ dados/agora.db</text>
<text x="18" y="184" fill="#9aa4b6">Para desligar, feche esta janela ou aperte Ctrl+C.</text></g>
<circle cx="600" cy="108" r="13" fill="#ffe977"/><text x="600" y="113" text-anchor="middle" font-size="13" font-weight="700" fill="#18211d">1</text>
<circle cx="600" cy="132" r="13" fill="#8fb0ff" transform="translate(0,8)"/><text x="600" y="145" text-anchor="middle" font-size="13" font-weight="700" fill="#0d1526">2</text>
<circle cx="600" cy="184" r="13" fill="#e8ecf3"/><text x="600" y="189" text-anchor="middle" font-size="13" font-weight="700" fill="#0f1420">3</text>
</svg>'''


def testes_html():
    ui = json.loads((RAIZ / "docs" / "resultado-testes-ui.json").read_text(encoding="utf-8"))
    api_txt = (RAIZ / "docs" / "resultado-testes-api.txt").read_text(encoding="utf-8")
    api_linhas = re.findall(r"^(test_\w+) \(.*?\) \.\.\. (ok|FAIL|ERROR)", api_txt, re.M)
    n_ui = sum(r["ok"] for r in ui["resultados"])
    n_api = sum(1 for _, s in api_linhas if s == "ok")
    linhas_ui = "".join(f'<tr><td>{"✓" if r["ok"] else "✕"}</td><td>{E(r["teste"])}</td></tr>' for r in ui["resultados"])
    linhas_api = "".join(f'<tr><td>{"✓" if s == "ok" else "✕"}</td><td class="mono">{E(t)}</td></tr>' for t, s in api_linhas)
    return n_ui, len(ui["resultados"]), n_api, len(api_linhas), ui["quando"], linhas_ui, linhas_api


def main():
    n_ui, t_ui, n_api, t_api, quando, linhas_ui, linhas_api = testes_html()
    corpo = f'''
<header class="top"><div class="brand"><svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" stroke-width="3"/><path d="M16 16 L16 5 A11 11 0 0 1 26.4 12.6 Z" fill="var(--accent)"/></svg><b>Agora</b><i>TDAH</i></div><span class="pill mono">Manual, versão 2.0</span></header>
<div class="layout">
<nav class="toc" aria-label="Seções do manual"><span class="label">Neste manual</span>
<a href="#agir">Faça isto primeiro</a><a href="#como">Como funciona</a><a href="#instalar">Instalação</a><a href="#paciente">Uso: paciente</a><a href="#profissional">Uso: profissional</a><a href="#servicos">Serviços e turmas</a><a href="#admin">Administração</a><a href="#relatorios">Relatórios</a><a href="#pagamentos">Planos e pagamentos</a><a href="#publicar">Publicar na internet</a><a href="#seguranca">Segurança e operação</a><a href="#android">App Android</a><a href="#site">Site público</a><a href="#problemas">Solução de problemas</a><a href="#glossario">Glossário</a><a href="#tecnico">Seção técnica</a></nav>
<main>
<section class="hero"><h1>Uma coisa por vez.</h1><p class="lead">O Agora é um sistema para TDAH em duas partes: um <b>app gratuito para o paciente</b> (celular e computador) e um <b>painel para o psicólogo</b> acompanhar e prescrever rotinas entre as sessões, no mesmo modelo do Dietbox. </p>
<p class="lead">A <b>versão 2.0</b> deixa o sistema pronto para produção e vira um funil de cuidado: tela de <b>Serviços</b> com terapia, turmas de treino de habilidades sociais da Lume com missões semanais e e-books; <b>painel de administração</b> com receita contra a meta, funil, contatos, turmas, compras e estornos; dados de saúde <b>cifrados no banco</b>, <b>verificação em duas etapas</b>, backup cifrado fora do servidor, lembretes com o app fechado e convite por link.</p></section>

<section id="agir" class="act"><span class="label">Faça isto primeiro · uma ação</span><h2>Dê dois cliques no lançador do seu sistema</h2>
<div class="tabs" role="tablist" data-tabs="go">
<button role="tab" aria-selected="true" data-t="w">Windows</button><button role="tab" aria-selected="false" data-t="m">macOS</button><button role="tab" aria-selected="false" data-t="l">Linux</button></div>
<div data-p="go" data-t="w"><p>Abra a pasta do Agora e dê dois cliques em <code>iniciar-windows.bat</code>.</p></div>
<div data-p="go" data-t="m" hidden><p>Abra a pasta do Agora e dê dois cliques em <code>iniciar-mac.command</code>.</p></div>
<div data-p="go" data-t="l" hidden><p>Abra a pasta do Agora e dê dois cliques em <code>iniciar-linux.sh</code> (ou rode <code>./iniciar-linux.sh</code>).</p></div>
<p class="small muted">O navegador abre sozinho em <span class="mono">localhost:8765/app/</span>; o site público fica em <span class="mono">localhost:8765/</span>. Sem Python instalado? Veja <a href="#instalar">Instalação</a>. Só quer olhar? Abra <code>app/index.html</code> direto no navegador: funciona sem servidor, com dados de exemplo.</p></section>

<section id="como"><h2>Como funciona</h2>
<p>O app do paciente guarda tudo no próprio aparelho. Quando o paciente se vincula a um profissional, ele escolhe o que compartilhar, e o servidor da clínica grava só essa parte. O profissional lê, prescreve, e a prescrição volta para o app.</p>
<div class="diagram">{SVG_COMO}</div>
<h3>A jornada de uso</h3><div class="diagram">{svg_jornada()}</div>
<h3>Legenda</h3><div class="diagram">{SVG_LEGENDA}</div></section>

<section id="instalar"><h2>Instalação passo a passo</h2>
<p>Você precisa do <b>Python 3.9 ou mais novo</b>. Nada mais: o Agora não usa bibliotecas externas.</p>
<div class="tabs" role="tablist" data-tabs="so">
<button role="tab" aria-selected="true" data-t="w">Windows</button><button role="tab" aria-selected="false" data-t="m">macOS</button><button role="tab" aria-selected="false" data-t="l">Linux</button><button role="tab" aria-selected="false" data-t="c">Celular</button></div>
<div data-p="so" data-t="w"><ol class="steps">
<li><b>Instale o Python.</b> Baixe em <span class="mono">python.org/downloads</span>. Na primeira tela do instalador, marque <b>Add Python to PATH</b> e clique em Install Now.</li>
<li><b>Descompacte o Agora</b> numa pasta fácil, como <span class="mono">Documentos\\agora-tdah</span>.</li>
<li><b>Dê dois cliques em <code>iniciar-windows.bat</code>.</b> Se o Windows mostrar "O Windows protegeu o computador", clique em <i>Mais informações</i> › <i>Executar assim mesmo</i>.</li>
<li><b>Deixe a janela preta aberta.</b> Ela é o servidor. Fechar a janela desliga o app.</li></ol></div>
<div data-p="so" data-t="m" hidden><ol class="steps">
<li><b>Confira o Python.</b> Abra o Terminal e digite <code>python3 --version</code>. Se não aparecer 3.9 ou mais, instale pelo <span class="mono">python.org/downloads</span>.</li>
<li><b>Descompacte o Agora</b> em Documentos.</li>
<li><b>Dê dois cliques em <code>iniciar-mac.command</code>.</b> Na primeira vez, o macOS pode bloquear: clique com o botão direito no arquivo › <i>Abrir</i> › <i>Abrir</i>.</li>
<li><b>Deixe a janela do Terminal aberta</b> enquanto usa o app.</li></ol></div>
<div data-p="so" data-t="l" hidden><ol class="steps">
<li><b>Python 3 já vem na maioria das distribuições.</b> Confira com <code>python3 --version</code>; se faltar, <code>sudo apt install python3</code>.</li>
<li><b>Descompacte</b> e entre na pasta: <code>cd agora-tdah</code>.</li>
<li><b>Rode</b> <code>./iniciar-linux.sh</code>. Para liberar celulares da mesma rede: <code>./iniciar-linux.sh --host 0.0.0.0</code>.</li></ol></div>
<div data-p="so" data-t="c" hidden><ol class="steps">
<li><b>Ligue o servidor aberto para a rede</b> no computador: <code>python3 server/server.py --host 0.0.0.0</code>.</li>
<li><b>Descubra o IP do computador</b> (ex.: <span class="mono">192.168.0.12</span>) e abra no celular, na mesma rede Wi-Fi: <span class="mono">http://192.168.0.12:8765/app/</span>.</li>
<li><b>Adicione à tela inicial.</b> No Chrome: menu ⋮ › <i>Adicionar à tela inicial</i>. No Safari: compartilhar › <i>Adicionar à Tela de Início</i>.</li>
<li><b>Para instalar como app completo fora da rede de casa</b>, o servidor precisa de HTTPS (veja <a href="#publicar">Publicar na internet</a>) ou o app Android (veja <a href="#android">App Android</a>).</li></ol></div>
<figure class="shot narrow"><div class="frame">{SVG_TERMINAL}</div><figcaption><span class="label">A janela que abre ao dar dois cliques</span><ol class="leg"><li><b>1</b>Endereço do app do paciente</li><li><b>2</b>Endereço do painel do profissional</li><li><b>3</b>Fechar esta janela desliga o Agora</li></ol></figcaption></figure>
<div class="callout"><b>Caso de demonstração.</b> Na primeira vez, o lançador cria contas de exemplo. Senha de todas: <code>demo1234</code>. Profissional: <code>ana@demo.agora</code>. Pacientes: <code>lucas@demo.agora</code>, <code>marina@demo.agora</code>, <code>rafael@demo.agora</code>. Para zerar, apague a pasta <code>dados</code>.</div></section>

<section id="paciente"><h2>Uso guiado: paciente</h2>
<h3>1. A tela Agora</h3><p>É a tela principal. O app escolhe <b>uma</b> próxima ação e diz o motivo. Se for hora de uma rotina, ela aparece no lugar da tarefa.</p>{figura("01-agora", "Tela Agora (computador)")}
<h3>2. Modo foco</h3><p>O botão grande abre o foco. O tempo continua certo mesmo se você trocar de aba. Ao terminar, o app pergunta como foi e soma os minutos ao placar.</p>{figura("02-foco", "Modo foco com sala")}
<h3>3. Tarefas tipificadas, com prioridade</h3><p>Escreva tudo que está na cabeça, uma linha por coisa, e marque o tipo (trabalho, estudo, casa, saúde, finanças, pessoal), a prioridade (alta, média, baixa) e a energia que a tarefa pede. A lista fica agrupada por prioridade e pode ser filtrada por tipo.</p>{figura("03-tarefas", "Despejo e lista")}{figura("03b-tarefas-tipos", "Agrupadas por prioridade, filtradas por tipo")}
<h3>4. Cursos</h3><p>Cadastre cada curso com total de aulas, aulas feitas, prazo e prioridade. O app calcula o ritmo necessário para o prazo e coloca a próxima aula do curso mais urgente no Agora. "Estudar agora" abre o foco já ligado ao curso.</p>{figura("03c-cursos", "Lista de cursos")}
<h3>5. Rotinas</h3><p>Sequências curtas com tempo por passo. Rotinas com selo laranja vieram do seu profissional.</p>{figura("04-rotinas", "Lista de rotinas")}{figura("08-rotina-player", "Rotina passo a passo", True)}
<h3>6. Diário</h3><p>Humor com carinhas, energia, sono (horas e qualidade) e atividade física. Menos de um minuto por dia.</p>{figura("06-diario", "Diário do dia")}
<p>Se você marcar o humor mais baixo, o app mostra contatos de apoio antes de qualquer outra coisa.</p>{figura("07-apoio", "Apoio em dia muito difícil", True)}
<h3>7. Painel</h3><p>Escolha 7, 14 ou 28 dias. Indicadores com tendência e comparação com o período anterior, foco × humor, calendário do humor com carinhas, distribuição do humor, sono com faixa saudável, atividade física por semana contra a meta da OMS, foco por dia da semana, foco por tipo de tarefa, progresso dos cursos e comparações tiradas dos seus próprios dados.</p>{figura("05-painel", "Painel")}
<h3>8. Temas</h3><p>Sete temas: Automático (segue o sistema), Claro, Clean, Escuro, Matrix, Oceano e Lavanda. Troque em Mais › Aparência ou pelas bolinhas no rodapé do menu lateral.</p>{figura("26-temas", "Escolha de tema")}<div class="pair">{figura("24-matrix", "Tema Matrix", True)}{figura("27-clean", "Tema Clean", True)}</div>{figura("25-matrix-painel", "Painel no tema Matrix")}
<h3>9. Mais: conta, planos, triagem, vínculo, lembretes e backup</h3><p>No topo ficam a sua conta (criar, entrar, esqueci minha senha, excluir conta) e os planos. Mais abaixo, a triagem, o vínculo com o profissional e os lembretes: na hora de cada rotina e um lembrete diário do diário, às 21h por padrão.</p>{figura("09-mais", "Tela Mais")}{figura("10-vinculo", "Escolha do que compartilhar")}
<h3>No celular e no escuro</h3><div class="pair">{figura("20-mobile-agora", "Agora no celular", True)}{figura("21-mobile-foco", "Foco no celular", True)}</div>{figura("22-escuro", "Tema escuro")}</section>

<section id="profissional"><h2>Uso guiado: profissional</h2>
<ol class="steps"><li><b>Abra</b> <span class="mono">http://localhost:8765/app/pro.html</span> e crie sua conta (ou entre com <code>ana@demo.agora</code>).</li>
<li><b>Clique em Convidar paciente.</b> Passe o código de 6 letras ao paciente.</li>
<li><b>O paciente</b> abre o app › Mais › Vincular, cria a conta, digita o código e escolhe o que compartilhar.</li>
<li><b>Acompanhe e prescreva.</b> O paciente aparece na lista; quem pede atenção fica no topo.</li>
<li><b>Grátis até 3 pacientes.</b> Para vincular mais, assine o Agora Pro no cartão "Seu plano", na lateral.</li>
<li><b>Convite por link.</b> A caixa do convite traz um link pronto e um botão para mandar no WhatsApp: ao abrir, o app já preenche o código.</li>
<li><b>Ligue a verificação em duas etapas</b> no botão do topo: leia a chave no app autenticador (Google Authenticator, Aegis, 1Password), digite o código e guarde os 8 códigos de recuperação.</li></ol>
<div class="pair">{figura("46-pro-convite", "Convite com link", True)}{figura("47-pro-2fa", "Verificação em duas etapas", True)}</div>
{figura("11-pro-visao", "Ficha do paciente: visão geral")}{figura("12-pro-prescrever", "Prescrever rotina")}{figura("23-pro-escuro", "Painel no tema escuro")}</section>

<section id="servicos"><h2>Serviços, turmas e e-books</h2>
<p>Em <b>Mais › Serviços da equipe</b>, o paciente vê o que a equipe oferece, separado por linha: terapia individual, grupos, treinos de habilidades sociais da <b>Lume</b> (adultos com TDAH e profissionais de tecnologia), e-books e serviços para empresas. Todo serviço psicológico mostra o nome e o CRP do responsável técnico. O app continua completo e de graça sem nada disso.</p>
{figura("40-servicos", "Serviços, com Minhas turmas e compras no topo")}
<ol class="steps"><li><b>Tenho interesse</b> abre um formulário curto. A pessoa aceita o uso dos dados para aquele contato e, se quiser, os 3 e-mails de conteúdo. A resposta chega por e-mail em até 2 dias úteis.</li>
<li><b>Pagar e agendar</b> (sessão individual) leva ao pagamento; a equipe escreve depois para marcar o horário.</li>
<li><b>Ver turmas abertas</b> mostra datas, vagas e valor. <i>Garantir vaga</i> leva ao pagamento; com a turma cheia, a pessoa entra na lista de espera e é avisada se abrir vaga.</li>
<li><b>Minhas turmas e compras</b>: o link da sala do encontro (só para confirmados), as 8 missões semanais para marcar como feitas e o botão Baixar dos e-books.</li></ol>
<div class="pair">{figura("41-turmas", "Turmas abertas", True)}{figura("42-interesse", "Formulário de interesse", True)}</div>
<div class="callout"><b>Regras que o sistema aplica sozinho.</b> Nenhuma oferta é disparada pelo diário, humor ou triagem: o aviso de semana pesada mostra só caminhos de cuidado (CVV 188, UBS, cadastro do CFP). Paciente vinculado a um profissional não vê serviços psicológicos de terceiros. No app Android só aparecem atendimentos individuais e formulários de interesse; e-books e turmas são vendidos pelo site, como o Google Play exige.</div>
{figura("43-ajuda", "Onde buscar ajuda: acolhimento sem venda", True)}
<h3>No site</h3><p>As páginas <span class="mono">/servicos</span> e <span class="mono">/comecar</span> levam o mesmo catálogo para quem chega pelo Google ou por redes sociais, com formulário de interesse e pedido de proposta para empresas.</p>
<div class="pair">{figura("44-site-servicos", "Pedido de proposta no site", True)}{figura("45-site-comecar", "Página Começar", True)}</div></section>

<section id="admin"><h2>Administração</h2>
<p>Abra <span class="mono">/app/admin.html</span> com uma conta de profissional promovida a administradora (<code>python3 server/admin.py promover SEU@EMAIL</code>). No primeiro acesso, o sistema pede para ligar a verificação em duas etapas. Na demonstração: <code>admin@demo.agora</code>, senha <code>demo1234</code>, chave do autenticador <code>JBSWY3DPEHPK3PXP</code>.</p>
{figura("50-admin-resumo", "Resumo: receita de 30 dias contra a meta de R$ 30 mil, base e funil anônimo")}
<ol class="steps"><li><b>Contatos:</b> cada pedido de interesse com a mensagem (guardada cifrada). Mude a situação conforme avança: contatado, agendado, virou cliente.</li>
<li><b>Turmas:</b> crie uma turma a partir do programa do catálogo; os treinos da Lume já vêm com as 8 missões. Veja inscritos e quantas missões cada um fez, mande aviso por e-mail e notificação, ajuste vagas (abrir vaga chama o primeiro da espera) e encerre.</li>
<li><b>Compras:</b> sessões, turmas e e-books pagos. <i>Estornar</i> pede confirmação, devolve o dinheiro pelo provedor, cancela a vaga e chama a lista de espera.</li>
<li><b>Catálogo:</b> ligue e desligue itens, ajuste preço e texto. O sistema recusa desconto, promoção ou promessa de resultado em serviço psicológico.</li>
<li><b>Erros:</b> falhas internas do servidor, sem conteúdo das requisições.</li></ol>
{figura("51-admin-contatos", "Contatos de interesse")}{figura("52-admin-turmas", "Turmas e inscritos")}
<div class="pair">{figura("53-admin-catalogo", "Catálogo com trava de publicidade", True)}{figura("54-admin-compras", "Compras e estorno", True)}</div></section>

<section id="relatorios"><h2>Relatórios</h2>
<p><b>Resumo para a sessão.</b> Na ficha do paciente, aba <i>Resumo p/ sessão</i>: um texto pronto com adesão, humor, sono, foco, rotinas e triagem, comparando 7 com 28 dias. Copie e cole no seu prontuário depois de revisar.</p>{figura("13-pro-resumo", "Resumo para a sessão")}
<p><b>Diário dia a dia.</b> Aba <i>Diário</i>: tabela de 28 dias com humor, energia, sono, atividade, medicação, foco e notas.</p>
<p><b>Relatório do mês (Plus).</b> No Painel, toque em <i>Relatório do mês</i>: 30 dias de foco, humor, sono, atividade, rotinas e tarefas concluídas numa página, com botão para imprimir ou salvar em PDF e levar à consulta.</p>{figura("17-relatorio", "Relatório do mês")}
<p><b>Para o paciente.</b> O Painel do app é o relatório pessoal. Em Mais › Seus dados, <i>Copiar backup</i> gera um texto com todos os dados, que pode ser guardado ou restaurado em outro aparelho.</p></section>


<section id="pagamentos"><h2>Planos e pagamentos</h2>
<p>O paciente usa tudo de graça. O <b>Plus</b> (R$ 9,90/mês ou R$ 89/ano) libera cópia na nuvem, sala de foco com outras pessoas, relatório do mês e sons extras. O <b>Agora Pro</b> (R$ 69/mês) libera pacientes ilimitados para o profissional. Os valores ficam no <code>.env</code>.</p>
<div class="diagram">{SVG_PAG}</div>
<h3>Como o paciente assina</h3>
<ol class="steps"><li><b>Crie a conta</b> em Mais › Sua conta.</li><li><b>Em Planos</b>, toque em <i>Assinar por R$ 9,90/mês</i> (cartão, renova sozinho) ou <i>R$ 89,00/ano no Pix ou cartão</i> (não renova).</li>
<li><b>Pague na página do provedor.</b> Na versão de teste, é uma página simulada com botões "aprovado" e "recusado".</li><li><b>Volte ao app:</b> o Plus aparece em segundos, com a data de validade.</li></ol>
{figura("14-planos", "Planos no app")}{figura("15-checkout", "Checkout de teste")}{figura("16-plus-ativo", "Plus ativo, cópia na nuvem e cancelamento")}
<p><b>Cancelar</b> é um toque em <i>Cancelar renovação</i>. O Plus continua até o fim do período pago e nada é apagado. Se uma renovação falhar, o acesso segue por mais 3 dias de carência.</p>
<h3>Como o profissional assina o Pro</h3>{figura("18-pro-plano", "Cartão Seu plano no painel")}
<h3>Ligar os pagamentos de verdade</h3>
<div class="tabs" role="tablist" data-tabs="pg"><button role="tab" aria-selected="true" data-t="mp">Mercado Pago</button><button role="tab" aria-selected="false" data-t="st">Stripe</button><button role="tab" aria-selected="false" data-t="si">Modo de teste</button></div>
<div data-p="pg" data-t="mp"><ol class="steps">
<li><b>Crie a aplicação</b> em <span class="mono">mercadopago.com.br/developers</span> › Suas integrações › Criar aplicação (produto: pagamentos online e assinaturas).</li>
<li><b>Copie o Access Token de produção</b> para <code>MP_ACCESS_TOKEN</code> no <code>.env</code>. Para testar antes, use as credenciais de teste e contas de teste do próprio Mercado Pago.</li>
<li><b>Configure o webhook</b> em Webhooks › Configurar notificações: URL <span class="mono">https://SEU-DOMINIO/api/webhooks/mercadopago</span>, eventos <i>Pagamentos</i> e <i>Planos e assinaturas</i>. Copie a assinatura secreta para <code>MP_WEBHOOK_SECRET</code>.</li>
<li><b>Mude</b> <code>AGORA_PAGAMENTO=mercadopago</code> e reinicie o servidor.</li>
<li><b>Faça uma compra de teste</b> de cada plano e confira o Plus liberado.</li></ol></div>
<div data-p="pg" data-t="st" hidden><ol class="steps">
<li><b>Pegue a chave secreta</b> em Desenvolvedores › Chaves de API e coloque em <code>STRIPE_SECRET_KEY</code>.</li>
<li><b>Crie o endpoint de webhook</b> <span class="mono">https://SEU-DOMINIO/api/webhooks/stripe</span> com os eventos <i>checkout.session.completed</i>, <i>checkout.session.async_payment_succeeded</i>, <i>invoice.paid</i>, <i>invoice.payment_failed</i>, <i>customer.subscription.updated</i>, <i>customer.subscription.deleted</i> e <i>charge.refunded</i>. Copie o segredo para <code>STRIPE_WEBHOOK_SECRET</code>.</li>
<li><b>Ative o portal do cliente</b> em Configurações › Faturamento › Portal (para "Trocar cartão").</li>
<li><b>Mude</b> <code>AGORA_PAGAMENTO=stripe</code> e reinicie.</li></ol></div>
<div data-p="pg" data-t="si" hidden><p>Com <code>AGORA_PAGAMENTO=simulado</code> (o padrão), o checkout abre uma página local com "Pix (teste)", "Cartão aprovado" e "Cartão recusado". Nenhum dinheiro de verdade é cobrado. Com <code>AGORA_AMBIENTE=producao</code>, o modo simulado é desligado automaticamente.</p></div>
<div class="callout"><b>Antes de cobrar de verdade:</b> CNPJ com atividade compatível, nota fiscal de serviço digital (fale com o seu contador sobre o enquadramento) e os textos de privacidade e termos revisados por advogado.</div></section>

<section id="publicar"><h2>Publicar na internet</h2>
<p>Para ter endereço próprio com HTTPS (necessário para pagamentos, notificações e o app Android), use um servidor na nuvem com Linux (uma VPS de entrada atende o piloto) e um domínio.</p>
<div class="tabs" role="tablist" data-tabs="dp"><button role="tab" aria-selected="true" data-t="dk">Com Docker</button><button role="tab" aria-selected="false" data-t="sd">Sem Docker</button></div>
<div data-p="dp" data-t="dk"><ol class="steps">
<li><b>Aponte o domínio</b> (registro A) para o IP do servidor.</li>
<li><b>Copie a pasta</b> do Agora para o servidor e entre nela.</li>
<li><b>Crie o .env:</b> <code>cp .env.example .env</code> e preencha domínio, pagamentos e e-mail.</li>
<li><b>Suba tudo:</b> <code>docker compose up -d</code>. O Caddy pede o certificado HTTPS sozinho; o serviço <i>backup</i> copia o banco todo dia para <code>backups/</code> e guarda 30 cópias.</li>
<li><b>Confira</b> <span class="mono">https://SEU-DOMINIO/api/health</span>: deve responder <code>"ok": true</code>.</li></ol></div>
<div data-p="dp" data-t="sd" hidden><ol class="steps">
<li><b>Copie</b> o projeto para <code>/opt/agora-tdah</code> e crie o <code>.env</code>.</li>
<li><b>Instale o serviço:</b> copie <code>deploy/agora.service</code> para <code>/etc/systemd/system/</code> e rode <code>sudo systemctl enable --now agora</code>.</li>
<li><b>Coloque HTTPS na frente</b> com Caddy: <code>caddy reverse-proxy --from SEU-DOMINIO --to 127.0.0.1:8765</code>.</li>
<li><b>Agende o backup:</b> <code>python3 server/backup.py --db /var/lib/agora/agora.db --destino /var/backups/agora</code> no cron, uma vez por dia.</li></ol></div></section>

<section id="seguranca"><h2>Segurança e operação</h2>
<p>O roteiro completo está em <code>docs/PRODUCAO.md</code> (antes do primeiro deploy, rotina, atualização, backup, troca de chave). O plano de incidentes em <code>docs/INCIDENTES.md</code> e o relatório de impacto (RIPD) em <code>docs/RIPD.md</code>.</p>
<ol class="steps"><li><b>Gere a chave de criptografia:</b> <code>python3 server/admin.py chave</code>. Cole em <code>AGORA_CHAVE</code> no <code>.env</code> e <b>guarde uma cópia fora do servidor</b>. Sem ela, banco e backups não abrem. Em produção, o servidor não liga sem a chave.</li>
<li><b>Gere as chaves de notificação:</b> <code>python3 server/admin.py vapid</code> (lembretes com o app fechado no navegador).</li>
<li><b>Configure o S3</b> (Backblaze B2, Cloudflare R2, AWS) em <code>AGORA_S3_*</code>: o backup diário sai cifrado e conferido.</li>
<li><b>Confira</b>: <code>python3 server/admin.py conferir</code> lista o que falta.</li>
<li><b>Homologação:</b> <code>docker compose --profile homologacao up -d</code> sobe uma cópia com pagamento de teste, protegida por senha, em outro subdomínio.</li></ol>
<div class="callout"><b>O que fica cifrado no banco:</b> cópia na nuvem, o que o paciente compartilha com o profissional, pedidos de contato, mensagens de interesse, anotações das missões e os segredos da verificação em duas etapas. Nome, e-mail e registros de compra não são cifrados (precisam ser buscados e constam em nota fiscal).</div></section>

<section id="android"><h2>App Android</h2>
<p>O app Android é o mesmo app web empacotado com Capacitor, com notificações nativas: os lembretes de rotina e do diário chegam mesmo com o app fechado. O painel do profissional fica só na web.</p>
<ol class="steps">
<li><b>Suba o projeto para o GitHub</b> (repositório privado).</li>
<li><b>Gere a chave de assinatura uma única vez:</b> <code>android/gerar-chave.sh</code>. Guarde o arquivo e a senha num cofre: sem eles não dá para atualizar o app.</li>
<li><b>Cadastre os secrets</b> no GitHub (Settings › Secrets › Actions): <code>AGORA_API_URL</code>, <code>AGORA_KEYSTORE_BASE64</code> e <code>AGORA_KEYSTORE_SENHA</code>.</li>
<li><b>Rode o workflow</b> Actions › Android › Run workflow. Ele gera <code>agora-debug.apk</code> (instale no celular para testar) e <code>agora-release.aab</code> (para a Play Store).</li>
<li><b>Envie o AAB</b> ao Play Console, preencha a ficha da loja e a declaração de segurança dos dados, e siga o checklist abaixo.</li></ol>
{figura("28-android-planos", "No Android, o Plus não é vendido dentro do app", True)}
<h3>Checklist da Play Store</h3>
<div class="tablewrap"><table>
<tr><td>Conta de desenvolvedor</td><td>Prefira conta de <b>organização</b> com o seu CNPJ (exige número D-U-N-S). Conta pessoal criada depois de 13/11/2023 precisa de teste fechado com 12 testadores por 14 dias seguidos antes de publicar.</td></tr>
<tr><td>Cobrança</td><td>Assinatura digital comprada dentro do app tem de usar o Google Play Billing, e o app não pode levar a pessoa para pagar no site. Por isso o app Android ainda não vende o Plus. Sessões de terapia (serviço clínico, atendimento 1:1) podem ser cobradas fora do Google Play.</td></tr>
<tr><td>Saúde</td><td>Preencher a declaração de apps de saúde no Play Console e deixar claro na ficha que o app não faz diagnóstico.</td></tr>
<tr><td>Privacidade</td><td>URL da política (<span class="mono">/privacidade.html</span>), seção de segurança dos dados e URL de exclusão de conta (<span class="mono">/excluir-conta.html</span>).</td></tr>
<tr><td>Identificador</td><td><code>br.com.agoratdah.app</code>. Não muda depois do primeiro envio: troque antes, em <code>android/capacitor.config.json</code> e no projeto Android, se for usar outro domínio.</td></tr>
</table></div></section>

<section id="site"><h2>Site público</h2>
<p>O endereço principal mostra a página de apresentação, com preços puxados do servidor e links para o app, o painel e as páginas legais. A página de exclusão de conta funciona sem o app, como a Play Store exige.</p>
{figura("30-site", "Página inicial")}<div class="pair">{figura("32-site-celular", "Site no celular", True)}{figura("31-excluir-conta", "Excluir conta pela web", True)}</div>
<p class="small muted">As páginas de privacidade e termos são rascunhos com campos entre colchetes: preencha e revise com um advogado antes de publicar.</p></section>

<section id="problemas"><h2>Solução de problemas</h2>
<dl class="faq">
<dt>Dei dois cliques e a janela fechou na hora.</dt><dd>O Python não está instalado ou não está no PATH. No Windows, reinstale marcando <b>Add Python to PATH</b>.</dd>
<dt>Aparece "Address already in use" ou a porta 8765 está ocupada.</dt><dd>O Agora já está aberto em outra janela, ou outro programa usa a porta. Feche a outra janela ou rode <code>python3 server/server.py --porta 8800</code> e abra <span class="mono">localhost:8800</span>.</dd>
<dt>O celular não abre o endereço do computador.</dt><dd>Ligue o servidor com <code>--host 0.0.0.0</code>, confira se os dois estão no mesmo Wi-Fi e libere o Python no firewall quando o sistema perguntar.</dd>
<dt>Em "Vincular" aparece que preciso abrir pelo endereço da clínica.</dt><dd>Você abriu o arquivo direto ou a página hospedada. O vínculo só existe quando o app é aberto pelo servidor (<span class="mono">http://…:8765</span>).</dd>
<dt>"Código de convite inválido ou já usado".</dt><dd>Cada código vale para uma pessoa. Peça um código novo ao profissional.</dd>
<dt>A rotina prescrita não apareceu.</dt><dd>No app, vá em Mais › <i>Sincronizar agora</i>. Ela chega na próxima sincronização.</dd>
<dt>O som não toca.</dt><dd>Navegadores só tocam som depois de um toque na página. Toque no botão do som de novo. No iPhone, tire do modo silencioso.</dd>
<dt>Perdi meus dados ao trocar de navegador.</dt><dd>Os dados ficam no navegador onde você usa o app. Use Mais › <i>Copiar backup</i> no antigo e <i>Restaurar backup</i> no novo.</dd>
<dt>Paguei e o Plus não apareceu.</dt><dd>O app espera até 30 segundos pela confirmação. Se o webhook não chegar, confira no painel do provedor se a URL é <span class="mono">https://SEU-DOMINIO/api/webhooks/...</span> e se o segredo no <code>.env</code> é o mesmo. O terminal do servidor mostra o motivo de cada recusa.</dd>
<dt>Esqueci minha senha e o e-mail não chega.</dt><dd>Sem SMTP configurado (<code>AGORA_SMTP_HOST</code>), o e-mail não sai: o link fica na tabela <code>caixa_saida</code> do banco, para testes. Em produção, preencha os dados de SMTP no <code>.env</code>.</dd>
<dt>"Muitas tentativas. Espere..." ao entrar.</dt><dd>Depois de 5 senhas erradas em 15 minutos, o login daquele e-mail fica bloqueado por um tempo. Espere ou use Esqueci minha senha.</dd>
<dt>O app Android não conecta ao servidor.</dt><dd>Confira o secret <code>AGORA_API_URL</code> (com https) e se o domínio está em <code>AGORA_CORS</code> (o padrão já inclui <span class="mono">https://localhost</span>, usado pelo app).</dd>
<dt>Os lembretes não chegam no celular.</dt><dd>Toque em Mais › Lembretes › Permitir notificações e, no Android, desative a otimização de bateria para o Agora.</dd>
<dt>Perdi o celular com o autenticador.</dt><dd>Entre com um dos 8 códigos de recuperação no lugar do código. Sem eles, quem cuida do servidor roda <code>python3 server/admin.py zerar-2fa SEU@EMAIL</code>.</dd>
<dt>"A nuvem tem uma versão mais nova".</dt><dd>Outro aparelho salvou depois deste. Escolha qual vale: trazer a da nuvem ou manter a deste aparelho.</dd>
<dt>O servidor não liga e fala em AGORA_CHAVE.</dt><dd>Em produção a chave é obrigatória. Gere com <code>python3 server/admin.py chave</code>. Se a chave mudou, coloque a antiga em <code>AGORA_CHAVES_ANTIGAS</code>.</dd>
<dt>O lembrete com o app fechado não chega.</dt><dd>Confira em Mais › Lembretes se está <i>Ligado</i> e se o navegador permitiu notificações. No iPhone, o Safari só aceita depois de instalar o app na tela inicial.</dd>
<dt>Quero apagar tudo da demonstração.</dt><dd>Feche o servidor e apague a pasta <code>dados</code>. No app, use Mais › <i>Apagar tudo</i>.</dd></dl></section>

<section id="glossario"><h2>Glossário</h2><dl class="gloss">
<dt>ASRS 1.1</dt><dd>Adult ADHD Self-Report Scale, questionário de rastreio da OMS. A parte A tem 6 perguntas; 4 ou mais na faixa de atenção sugerem avaliação completa. Não é diagnóstico.</dd>
<dt>Carência</dt><dd>Três dias a mais de acesso quando uma renovação atrasa, enquanto o provedor tenta cobrar de novo.</dd>
<dt>Checkout</dt><dd>A página do provedor onde a pessoa paga.</dd>
<dt>Body doubling</dt><dd>Fazer uma tarefa com outra pessoa presente, mesmo à distância. No Agora, é a Sala de foco.</dd>
<dt>Cegueira temporal</dt><dd>Dificuldade de perceber a passagem do tempo, comum no TDAH. Por isso o tempo fica sempre visível.</dd>
<dt>Consentimento</dt><dd>A escolha do paciente sobre o que o profissional pode ver. Vale por categoria e pode mudar a qualquer momento.</dd>
<dt>Despejo</dt><dd>Escrever tudo que está na cabeça de uma vez, sem organizar.</dd>
<dt>Prioridade</dt><dd>Alta, média ou baixa. Prioridade alta pesa mais na escolha da próxima ação; prazo perto pesa ainda mais.</dd>
<dt>Ritmo do curso</dt><dd>Quantas aulas por semana faltam para terminar o curso no prazo.</dd>
<dt>Energia</dt><dd>Quanto a tarefa exige (baixa, média, alta) e quanta disposição você tem hoje.</dd>
<dt>Local-first</dt><dd>Os dados ficam primeiro no seu aparelho; a internet é opcional.</dd>
<dt>Prescrição</dt><dd>Rotina, tarefa ou recado que o profissional envia ao app do paciente.</dd>
<dt>PWA</dt><dd>Aplicativo web que pode ser instalado na tela inicial e funciona sem internet.</dd>
<dt>Webhook</dt><dd>Aviso automático que o provedor de pagamento manda ao servidor quando algo muda numa cobrança. Vem assinado, e o servidor confere a assinatura.</dd>
<dt>Play Billing</dt><dd>Sistema de cobrança do Google Play, obrigatório para vender assinatura digital dentro de apps Android distribuídos pela loja.</dd>
<dt>Verificação em duas etapas (2FA)</dt><dd>Além da senha, um código de 6 dígitos que muda a cada 30 segundos no app autenticador do celular.</dd>
<dt>Criptografia em repouso</dt><dd>Os dados ficam embaralhados no banco e só voltam a ser legíveis com a chave, que não fica no banco.</dd>
<dt>Lista de espera</dt><dd>Fila de quem quer vaga numa turma cheia. Quando abre vaga, o primeiro é avisado por e-mail e notificação.</dd>
<dt>Missão</dt><dd>Prática semanal do treino de habilidades sociais, marcada pelo participante no app entre um encontro e outro.</dd>
<dt>Funil</dt><dd>O caminho de quem conhece o Agora até virar cliente: visita, abre serviços, pede contato, compra. Contado de forma anônima.</dd>
<dt>Responsável técnico</dt><dd>Psicólogo com CRP que responde pelos serviços psicológicos anunciados.</dd>
<dt>Ruído marrom</dt><dd>Som de fundo mais grave que o ruído branco; muita gente com TDAH relata que ajuda a focar.</dd></dl></section>

<section id="tecnico"><h2>Seção técnica</h2>
<h3>Arquitetura</h3><div class="diagram">{SVG_ARQ}</div>
<h3>Estrutura de pastas</h3>
<pre>agora-tdah/
├── COMECE-AQUI.md            ← leia primeiro
├── iniciar-windows.bat · iniciar-mac.command · iniciar-linux.sh
├── rodar-testes.sh
├── .env.example · Dockerfile · docker-compose.yml · deploy/ (Caddyfile, agora.service)
├── app/     index.html (paciente) · pro.html (profissional) · admin.html (administração) · checkout-simulado.html · config.js · sw.js
├── site/    index.html · servicos.html · comecar.html · privacidade · termos · excluir-conta
├── server/  server.py · funil.py · catalogo.py · catalogo_padrao.json · pagamentos.py · cripto.py · migracoes.py
│            push.py · s3.py · admin.py · backup.py · google_play.py · email_envio.py · config.py · seed_demo.py
├── android/ projeto Capacitor (preparar-www.py, gerar-chave.sh, android/)
├── .github/workflows/  testes.yml (testes a cada push) · android.yml (APK e AAB)
├── tests/   test_api.py · test_producao.py · test_ui.py
├── docs/   manual.html · PRODUCAO.md · INCIDENTES.md · RIPD.md · ESPECIFICACAO.md · RELATORIO-TESTES.md · capturas/
└── dados/  agora.db (criado ao rodar; fora do controle de versão)</pre>
<h3>Opções do servidor</h3>
<pre>python3 server/server.py --porta 8765 --host 127.0.0.1 --db dados/agora.db
# variáveis equivalentes: AGORA_PORTA, AGORA_HOST, AGORA_DB · AGORA_LOG=1 mostra cada requisição</pre>
<h3>Configuração (.env)</h3><p>Todas as variáveis estão comentadas em <code>.env.example</code>: endereço público, CORS, provedor de pagamento e segredos, preços, Google Play e SMTP. Produção: veja <a href="#publicar">Publicar na internet</a>.</p>
<h3>API de pagamentos</h3><pre>GET  /api/planos                         planos e preços
POST /api/pagamentos/checkout            {{"plano": "plus_mensal"}} → url do provedor
GET  /api/pagamentos/minha               direitos, assinaturas e pagamentos
POST /api/pagamentos/cancelar            não renovar (acesso segue até o fim)
POST /api/pagamentos/portal              portal do Stripe (trocar cartão)
POST /api/pagamentos/google-play         valida purchaseToken (fase 2)
POST /api/webhooks/mercadopago|stripe|google-play
POST /api/senha/esqueci · /api/senha/redefinir · /api/conta/excluir · GET /api/conta/exportar
GET|POST /api/nuvem                      cópia na nuvem (Plus), com versão (409 em conflito)
POST /api/2fa/iniciar|ativar|desativar   verificação em duas etapas
GET  /api/catalogo                       serviços visíveis para este contexto (web, Android, vinculado)
POST /api/interesse · /api/eventos       formulário de interesse · evento anônimo do funil
GET  /api/turmas · POST /api/turmas/:id/inscrever|sair · GET /api/minhas · POST /api/missoes/:id/feita
POST /api/produtos/comprar               sessão ou e-book · GET /api/ebook/link → link assinado de 10 min
GET|POST /api/descadastrar               descadastro em um clique (link assinado)
GET  /api/push/chave · POST /api/push/inscrever|cancelar|pendentes|lembretes
GET  /api/admin/resumo|interesses|turmas|compras|catalogo|erros  (admin + 2FA)
POST /api/admin/turmas · /api/admin/turmas/:id · .../avisar · /api/admin/compras/:id/estornar · /api/admin/catalogo</pre>
<h3>Linha de comando</h3><pre>python3 server/admin.py chave | vapid | promover EMAIL | rebaixar EMAIL | zerar-2fa EMAIL | recifrar | tarefas | conferir | estado
python3 server/backup.py --db dados/agora.db --destino backups          # backup cifrado (+ S3)
python3 server/backup.py --restaurar ARQUIVO.db.cifrado --db novo.db    # restaurar</pre>
<h3>Resultado dos testes</h3>
<div class="kpis"><div class="kpi"><span class="label">Navegador (ponta a ponta)</span><b>{n_ui}/{t_ui}</b></div><div class="kpi"><span class="label">API e produção (unittest)</span><b>{n_api}/{t_api}</b></div><div class="kpi"><span class="label">Rodado em</span><b class="smallb">{E(quando.replace("T", " "))}</b></div></div>
<p class="small muted">Executados num ambiente Linux na nuvem, com Python 3.13 e Chromium headless via Playwright, em telas de 1280, 1360 e 390 px, temas claro e escuro. Detalhes em <code>docs/RELATORIO-TESTES.md</code>.</p>
<details><summary>Ver as {t_ui} verificações de navegador</summary><div class="tablewrap"><table>{linhas_ui}</table></div></details>
<details><summary>Ver os {t_api} testes da API</summary><div class="tablewrap"><table>{linhas_api}</table></div></details>
<p class="small muted">Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} por ferramentas/gerar_manual.py.</p></section>
</main></div>'''

    css = '''
:root{--bg:#edefea;--surface:#fff;--sunk:#e3e6df;--ink:#18211d;--muted:#59645f;--line:#d5d9d1;--accent:#0b6b57;--accent-soft:#ffe977;--hl:#ffe977;--deep:#18211d;--m1:#5b6cb8;--m3:#9aa3ab;--m5:#ee8f2a;--bad:#b42318;
--f-display:"Atkinson Next","Segoe UI",system-ui,sans-serif;--f-body:"Atkinson Next","Segoe UI",system-ui,sans-serif;--f-mono:"Atkinson Mono",ui-monospace,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111513;--surface:#191e1b;--sunk:#232925;--ink:#e7ebe6;--muted:#9aa49e;--line:#2c332f;--accent:#4fbf9f;--accent-soft:#3d3a1c;--hl:#5b5222;--deep:#e7ebe6;--m1:#8c9cf0;--m3:#a9b2ba;--m5:#f5a24a;--bad:#ff8a7a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111513;--surface:#191e1b;--sunk:#232925;--ink:#e7ebe6;--muted:#9aa49e;--line:#2c332f;--accent:#4fbf9f;--accent-soft:#3d3a1c;--hl:#5b5222;--deep:#e7ebe6;--m1:#8c9cf0;--m3:#a9b2ba;--m5:#f5a24a;--bad:#ff8a7a;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:400 16.5px/1.6 var(--f-body)}
h1,h2,h3{font-family:var(--f-display);font-weight:780;line-height:1.12;letter-spacing:-.025em;text-wrap:balance}h1{font-size:clamp(2rem,6vw,3rem);margin:0}h2{font-size:1.6rem;margin:0 0 12px}h3{font-size:1.15rem;margin:28px 0 8px}
p{max-width:68ch}a{color:var(--accent)}code,.mono{font-family:var(--f-mono);font-size:.88em}code{background:var(--sunk);padding:1px 6px;border-radius:5px}
.label{font-size:.86rem;color:var(--muted);font-weight:650;display:block}
.small{font-size:.88rem}.muted{color:var(--muted)}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:env(safe-area-inset-top,0px);z-index:5}
.brand{display:flex;align-items:center;gap:10px}.brand b{font:800 1.34rem/1 var(--f-display);letter-spacing:-.03em}.brand i{font-style:normal;font-size:.82rem;font-weight:600;color:var(--muted)}
.pill{border-radius:6px;padding:3px 9px;background:var(--sunk);color:var(--muted);font-size:.78rem;font-weight:700}
.layout{display:grid;grid-template-columns:210px minmax(0,1fr);gap:32px;padding-inline:20px;max-width:1180px;margin:0 auto}
.toc{position:sticky;top:76px;align-self:start;display:grid;gap:4px;padding-block:28px}.toc a{color:var(--muted);text-decoration:none;font-weight:600;padding:5px 8px;border-radius:8px}.toc a:hover{color:var(--ink);background:var(--sunk)}
main{padding-block:28px 80px;min-width:0}main>section{padding-block:28px;border-bottom:1px solid var(--line)}
.lead{font-size:1.15rem}
.act{background:var(--surface);border:1.5px solid var(--ink);border-radius:16px;padding:22px!important;margin-block:10px 20px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0}.tabs button{font:inherit;font-weight:650;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;padding:6px 14px;cursor:pointer;min-height:38px}
.tabs button[aria-selected="true"]{background:var(--deep);border-color:var(--deep);color:var(--bg)}
ol.steps{display:grid;gap:10px;padding-left:22px}ol.steps li{padding-left:4px}
.diagram{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px;overflow-x:auto}.diagram svg{display:block;width:100%;min-width:560px;height:auto}
.shot{margin:16px 0 26px}.shot .frame{position:relative;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--surface)}.shot img,.shot .frame svg{display:block;width:100%;height:auto}
.shot.narrow{max-width:440px}.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.mk{position:absolute;transform:translate(-50%,-50%);width:28px;height:28px;border-radius:50%;background:#ffe977;color:#18211d;font:800 14px/26px var(--f-body);text-align:center;border:2px solid #18211d;box-shadow:0 0 0 2px #fff,0 3px 10px rgb(0 0 0 / .35)}
figcaption{padding-top:8px}.leg{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:4px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.leg li{display:flex;gap:8px;align-items:baseline;font-size:.92rem}.leg b{flex:none;width:22px;height:22px;border-radius:50%;background:#ffe977;color:#18211d;border:1.5px solid #18211d;font-size:.78rem;display:grid;place-items:center}
.callout{border-left:3px solid var(--accent);background:var(--surface);padding:12px 16px;border-radius:0 10px 10px 0;margin-top:16px}
.faq dt,.gloss dt{font-weight:700;margin-top:14px}.faq dd,.gloss dd{margin:4px 0 0;color:var(--ink);max-width:68ch}
pre{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;overflow-x:auto;font:13px/1.55 var(--f-mono)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:12px 0}.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px}.kpi b{font:780 1.7rem/1.1 var(--f-display);letter-spacing:-.02em}.kpi b.smallb{font-size:1rem}
details{margin-top:10px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 14px}summary{cursor:pointer;font-weight:700}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem;margin-top:8px}td{border-bottom:1px solid var(--line);padding:6px 8px}
@media (max-width:820px){.layout{grid-template-columns:1fr}.toc{display:none}body{font-size:16px}}
@media print{.top,.toc,.tabs{display:none}[hidden]{display:block!important}}
'''
    js = '''document.querySelectorAll("[data-tabs]").forEach(g=>{const k=g.dataset.tabs;g.querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{
g.querySelectorAll("button").forEach(x=>x.setAttribute("aria-selected",x===b));document.querySelectorAll('[data-p="'+k+'"]').forEach(p=>p.hidden=p.dataset.t!==b.dataset.t);}))});
(function(){var u=navigator.userAgent,t=/Mac/.test(u)&&!/iPhone|iPad/.test(u)?"m":/Linux/.test(u)&&!/Android/.test(u)?"l":/Android|iPhone|iPad/.test(u)?"c":"w";
["go","so"].forEach(function(k){var b=document.querySelector('[data-tabs="'+k+'"] [data-t="'+t+'"]');if(b)b.click();});})();'''
    pagina = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Manual do Agora</title>
<style>{fontes_embutidas()}{css}</style></head><body>{corpo}<script>{js}</script></body></html>'''
    destino = RAIZ / "docs" / "manual.html"
    destino.write_text(pagina, encoding="utf-8")
    # versão para publicar como página hospedada (sem esqueleto do documento)
    sem = pagina.split("<head>", 1)[1]
    sem = re.sub(r'<meta charset[^>]*>|<meta name="viewport"[^>]*>', "", sem).replace("</head><body>", "\n").replace("</body></html>", "")
    (RAIZ / "dist" / "manual-artifact.html").write_text(sem, encoding="utf-8")
    print(f"docs/manual.html {destino.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
