#!/usr/bin/env python3
"""Gera docs/RELATORIO-TESTES.md a partir dos resultados dos testes."""
import json
import platform
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ui = json.loads((RAIZ / "docs" / "resultado-testes-ui.json").read_text(encoding="utf-8"))
api_txt = (RAIZ / "docs" / "resultado-testes-api.txt").read_text(encoding="utf-8")
api = re.findall(r"^(test_\w+) \(.*?\) \.\.\. (?:.*?\n)*?.*?\b(ok|FAIL|ERROR)$", api_txt, re.M)
n_ui = sum(r["ok"] for r in ui["resultados"])
_sem = RAIZ / "docs" / "resultado-testes-sem-cryptography.txt"
SEM = _sem.read_text(encoding="utf-8").strip() if _sem.exists() else "não rodado"
n_api = sum(1 for _, s in api if s == "ok")
try:
    from playwright import __version__ as pwv
except Exception:
    pwv = "?"
linhas = [
    "# Relatório de testes — Agora 2.0", "",
    f"Executado em {ui['quando'].replace('T', ' ')} num ambiente Linux na nuvem.", "",
    "| Suíte | Resultado |", "|---|---|",
    f"| API e produção (`tests/test_api.py` e `tests/test_producao.py`, unittest) | **{n_api}/{len(api)}** |",
    f"| Mesmos testes sem o pacote opcional `cryptography` (cifra em Python puro) | **{SEM}** |",
    f"| Ponta a ponta no navegador (`tests/test_ui.py`, Playwright + Chromium) | **{n_ui}/{len(ui['resultados'])}** |", "",
    "## Ambiente", "",
    f"- Python {sys.version.split()[0]} em {platform.system()} {platform.release()}",
    f"- Playwright {pwv}, Chromium headless",
    "- Telas: 1280×860 e 1360×900 (computador), 390×844 (celular); temas claro, escuro, Matrix e Clean",
    "- Modo Android simulado: AGORA_CONFIG de Android e plugin de notificações falso para conferir os lembretes agendados",
    "- Não testado aqui: entrega real de Web Push pelos serviços do Google/Mozilla/Apple, envio real ao S3, build nativo do Android (o ambiente não tem o Android SDK; o build roda no GitHub Actions), pagamentos reais nos provedores e envio real de e-mail",
    "- Fuso America/Sao_Paulo, locale pt-BR, relógio fixado em 10:05 para resultado determinístico",
    "- Banco SQLite temporário com o caso de demonstração (`server/seed_demo.py`)", "",
    "## O que a API cobre", "",
    "Registro e validação, login e logout, limite de tentativas, recuperação de senha, exclusão e exportação de conta, senha em PBKDF2 e token só como hash, papéis, "
    "convite de uso único, filtro de consentimento aplicado no servidor (tarefas não liberadas nunca chegam ao profissional), "
    "revogação de consentimento, prescrição com limites, arquivamento, isolamento entre profissionais, pedido de contato, "
    "desvínculo apagando o snapshot, limite do plano grátis do profissional, checkout simulado (aprovado, recusado, Pix, idempotência, cancelamento e expiração), "
    "simulado desligado em produção, bloqueio de venda pelo Android, Mercado Pago (assinatura, renovação, Pix, estorno, assinatura HMAC igual ao SDK oficial), "
    "Stripe (assinatura, falha, cancelamento, Pix assíncrono, janela de tempo), Google Play (JWT RS256 conferido com o OpenSSL, compra, acknowledge, conta errada, RTDN), "
    "CORS do app Android, rotas do site, cabeçalhos de segurança, path traversal e JSON inválido. "
    "Na 2.0: ChaCha20-Poly1305 e Poly1305 contra os vetores da RFC 8439 e contra a biblioteca cryptography, TOTP contra a RFC 6238, ECDSA P-256 conferido pela cryptography, "
    "assinatura SigV4 contra os exemplos da AWS, migração de banco 1.3 com cifragem na partida, verificação em duas etapas com códigos de recuperação de uso único, "
    "limite de tentativas que sobrevive a reinício, CSP com hash de cada script, conflito de versão na nuvem, erro interno registrado sem vazar, catálogo por contexto "
    "(web, Android, paciente vinculado), formulário de interesse com armadilha para robôs, sequência de e-mails com descadastro assinado, eventos anônimos, turma com pagamento, "
    "missões, lista de espera e estorno, e-book com link assinado que expira, compra avulsa pelo Stripe, trava de publicidade no catálogo, lembrete Web Push com JWT VAPID, "
    "retenção, exportação e exclusão, backup cifrado com envio S3 e restauração, CLI de administração e recusa de partida em produção sem chave. No navegador, o teste confere também que nenhuma página pede arquivos a servidores de fora (as fontes ficam no próprio app).", "",
    "| Teste da API | Resultado |", "|---|---|"]
linhas += [f"| `{t}` | {'✓' if s == 'ok' else '✕ ' + s} |" for t, s in api]
linhas += ["", "## Verificações no navegador", "", "| # | Verificação | Resultado |", "|---|---|---|"]
linhas += [f"| {i} | {r['teste']} | {'✓' if r['ok'] else '✕ ' + r['detalhe']} |" for i, r in enumerate(ui["resultados"], 1)]
linhas += ["", "## Como repetir", "", "```bash", "./rodar-testes.sh", "# ou separadamente:",
           "python3 -m unittest tests.test_api tests.test_producao -v", "python3 tests/test_ui.py   # requer: pip install playwright && playwright install chromium", "```", "",
           "As capturas de tela do manual (`docs/capturas/`) são geradas pelo teste de navegador."]
(RAIZ / "docs" / "RELATORIO-TESTES.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
print(f"RELATORIO-TESTES.md  api {n_api}/{len(api)}  ui {n_ui}/{len(ui['resultados'])}")
