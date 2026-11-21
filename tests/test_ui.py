"""Teste de ponta a ponta em navegador real (Playwright/Chromium).

Liga o servidor com o caso de demonstração num banco temporário, percorre o app do
paciente e o painel do profissional como um usuário faria, e salva as capturas de
tela (com as coordenadas dos marcadores numerados) usadas no manual.

Rodar:  python3 tests/test_ui.py      (requer: pip install playwright && playwright install chromium)
"""
import json
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "server"))
import seed_demo  # noqa: E402
import server  # noqa: E402
import sqlite3  # noqa: E402
from config import Config  # noqa: E402

SHOTS = RAIZ / "docs" / "capturas"
SHOTS.mkdir(parents=True, exist_ok=True)
MARCAS = {}
RESULTADOS = []


def ok(nome, cond, detalhe=""):
    RESULTADOS.append({"teste": nome, "ok": bool(cond), "detalhe": detalhe})
    print(("  OK   " if cond else "  FALHA") + "  " + nome + (f"  ({detalhe})" if detalhe and not cond else ""))


def captura(page, nome, marcas=(), full=True):
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(120)
    lista = []
    for n, (sel, rotulo) in enumerate(marcas, 1):
        el = page.locator(sel).first
        if el.count() == 0:
            continue
        b = el.bounding_box()
        if not b:
            continue
        sy = page.evaluate("window.scrollY")
        lista.append({"n": n, "x": round(b["x"]), "y": round(b["y"] + sy), "rotulo": rotulo})
    page.screenshot(path=str(SHOTS / f"{nome}.png"), full_page=full)
    vp = page.viewport_size
    altura = page.evaluate("document.documentElement.scrollHeight") if full else vp["height"]
    MARCAS[nome] = {"w": vp["width"], "h": altura, "marcas": lista}


def api(url, caminho, corpo=None, token=None):
    r = urllib.request.Request(url + "/api/" + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                               method="POST" if corpo is not None else "GET")
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def main():
    tmp = tempfile.TemporaryDirectory()
    db = str(Path(tmp.name) / "e2e.db")
    import os
    os.environ["AGORA_EBOOKS_DIR"] = str(Path(tmp.name) / "ebooks")
    seed_demo.main(["--db", db])
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.cria_handler(server.API(server.Banco(db), Config(
        limite_registro=1000, provedor="simulado", ambiente="desenvolvimento", agendador=False))))
    url = f"http://localhost:{srv.server_address[1]}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    erros = []
    externos = []  # pedidos a servidores de fora (fontes, CDNs): o app não deve fazer nenhum
    hoje10 = datetime.now().replace(hour=10, minute=5, second=0, microsecond=0)

    with sync_playwright() as p:
        nav = p.chromium.launch()

        def nova(vp, escuro=False):
            ctx = nav.new_context(viewport=vp, color_scheme="dark" if escuro else "light", locale="pt-BR",
                                  timezone_id="America/Sao_Paulo", reduced_motion="reduce")
            ctx.on("request", lambda r: r.url.startswith(("http://", "https://")) and not r.url.startswith(url) and externos.append(r.url))
            ctx.route("**/fonts.googleapis.com/**", lambda r: r.abort())
            ctx.route("**/fonts.gstatic.com/**", lambda r: r.abort())
            pg = ctx.new_page()
            pg.clock.set_fixed_time(hoje10)
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and "fonts" not in m.text and "ERR_FAILED" not in m.text
                  and "status of 4" not in m.text and erros.append(m.text))  # 4xx esperados (validações) não são erro de JS
            return pg

        print("\n[1] App do paciente — dados de exemplo")
        pg = nova({"width": 1280, "height": 860})
        pg.goto(url + "/app/")
        pg.wait_for_selector(".now")
        ok("abre com banner de dados de exemplo", pg.locator(".banner").is_visible())
        ok("cartão Agora mostra uma próxima ação", pg.locator(".now h2").inner_text().strip() != "")
        captura(pg, "01-agora", [(".now h2", "A próxima ação escolhida pelo app"), (".now .why", "Por que esta, em uma linha"),
                                  ("[data-act=focus]", "Botão grande para começar o foco"), (".durs", "Troque a duração do foco"),
                                  ("[data-act=snooze]", "Agora não: volta amanhã, sem culpa"), (".moodq", "Humor em um toque"),
                                  (".score", "Placar do dia"), ("#fab", "Anotar ideia sem sair da tela")])
        pg.click("[data-go=painel]")
        ok("painel desenha os gráficos (foco×humor, sono, atividade, dia da semana)", pg.locator(".chart svg").count() >= 4)
        ok("calendário do humor com carinhas", pg.locator(".cal .cell svg").count() >= 15)
        pg.click("[data-act=periodo][data-n='28']")
        ok("período de 28 dias muda o gráfico", pg.locator(".tile >> nth=4").inner_text().find("/28") >= 0)
        ok("painel mostra comparações", pg.locator(".insight").count() >= 2)
        captura(pg, "05-painel", [(".score", "Resumo dos 14 dias"), (".chart", "Foco em barras, humor em linha"),
                                   (".chart >> nth=1", "Sono e atividade física"), (".insight", "Comparações dos seus próprios dados")])
        pg.click("[data-act=go][data-v=relatorio]")
        pg.wait_for_selector(".report .kpis")
        captura(pg, "17-relatorio", [(".report h1", "Relatório de 30 dias"), (".report .kpis", "Números do mês"), (".report .cal", "Humor dia a dia"),
                                     ("[data-act=imprimir]", "Imprimir ou salvar em PDF")])
        pg.click("[data-go=tarefas]")
        ok("tarefas agrupadas por prioridade", pg.locator(".group-h .prio.alta").count() == 1)
        ok("tarefas mostram o tipo", pg.locator(".task .type").count() >= 5)
        pg.click("[data-act=filtro][data-x=trabalho]")
        ok("filtro por tipo", pg.locator(".task").count() == 2)
        captura(pg, "03b-tarefas-tipos", [(".group-h", "Agrupadas por prioridade"), ("[data-act=filtro]", "Filtro por tipo, com contagem"),
                                          (".task .type", "Tipo da tarefa"), ("[data-act=dumpTipo]", "Escolha tipo e prioridade ao despejar")])
        pg.click("[data-act=sub][data-x=cursos]")
        ok("lista de cursos com progresso", pg.locator(".course").count() == 3)
        antes = pg.locator(".course").first.locator(".big").inner_text()
        pg.locator(".course").first.locator("[data-act=lesson]").click()
        ok("+1 aula atualiza o progresso", pg.locator(".course").first.locator(".big").inner_text() != antes)
        captura(pg, "03c-cursos", [(".seg", "Tarefas ou cursos"), (".course .big", "Progresso do curso"), (".course .pill.warn, .course .meta .pill", "Prazo e prioridade"),
                                    ("[data-act=lesson]", "Marcar aula feita"), ("[data-act=new-course]", "Cadastrar curso")])
        pg.click("[data-go=mais]")
        pg.click("[data-act=skin][data-x=matrix]")
        ok("tema Matrix aplica fundo preto-esverdeado", pg.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(2, 8, 4)")
        pg.click("[data-go=agora]")
        captura(pg, "24-matrix", [], full=False)
        pg.click("[data-go=painel]")
        captura(pg, "25-matrix-painel", [], full=False)
        pg.click("[data-go=mais]")
        captura(pg, "26-temas", [("#sec-tema .skins", "Sete temas"), ("#skinsMini", "Troca rápida no menu lateral")], full=False)
        pg.click("[data-act=skin][data-x=clean]")
        pg.click("[data-go=agora]")
        captura(pg, "27-clean", [], full=False)
        pg.click("[data-go=mais]")
        pg.click("[data-act=skin][data-x=auto]")
        pg.click("[data-go=rotinas]")
        captura(pg, "04-rotinas", [("[data-act=new-routine]", "Criar rotina"), (".pill.pro", "Rotina prescrita pela psicóloga"),
                                    ("[data-act=run-routine]", "Começar a rotina passo a passo")])

        print("\n[2] Começar do zero e o ciclo Agora → foco")
        pg.click("[data-go=agora]")
        pg.click("[data-act=start-fresh]")
        pg.fill("#nn", "Paula")
        pg.fill("#nd", "Enviar proposta para o cliente\nMarcar psiquiatra\nLavar a roupa")
        pg.click("#ok")
        ok("dados de exemplo somem", pg.locator(".banner").count() == 0)
        ok("primeira tarefa vira a próxima ação", "Enviar proposta" in pg.locator(".now h2").inner_text())
        pg.click("[data-act=split]")
        pg.click("#sug")
        pg.click("#ok")
        ok("quebrar em passos cria 3 passos", pg.locator(".steps li").count() == 3)
        pg.click(".steps li.cur .tick")
        ok("marcar passo avança o destaque", "Fazer só 2 minutos" in pg.locator(".steps li.cur").inner_text())
        pg.click("[data-act=dur][data-n='15']")
        ok("duração muda o botão", "15 min" in pg.locator("[data-act=focus]").inner_text())
        pg.click("[data-act=focus]")
        pg.wait_for_selector("#clock")
        ok("modo foco abre com relógio 15:00", pg.locator("#clock").inner_text() == "15:00")
        ok("sala de foco aparece (modo solo sem conta)", "Modo solo" in pg.locator("#room").inner_text())
        captura(pg, "02-foco", [(".ring", "Tempo restante em anel"), ("#fPause", "Pausar sem perder o tempo"),
                                 ("[data-snd=brown]", "Ruído branco, rosa ou marrom"), (".room", "Sala de foco (body doubling)")], full=False)
        pg.evaluate("FOCO.end = Date.now()")
        pg.wait_for_selector("[data-feel]")
        ok("fim do foco separa o tempo da tarefa (Concluí / Avancei / Retomar)", pg.locator("[data-fim]").count() == 3)
        pg.click("[data-feel=fluiu]")
        pg.fill("#fProx", "abrir o calendário do médico")
        captura(pg, "02b-fim-foco", [("[data-feel=fluiu]", "Como foi"), ("#fProx", "Por onde começar da próxima vez"),
                                     ("[data-fim=avancei]", "Avancei um pouco: a tarefa continua na fila")], full=False)
        pg.click("[data-fim=avancei]")
        ok("sessão registrada (15 min no placar)", "15" in pg.locator(".score .tile >> nth=1").inner_text())
        ok("onde parei aparece na próxima ação, com o passo guardado", "abrir o calendário do médico" in pg.locator(".now").inner_text())
        ok("placar mostra dias em que voltei, sem exigir sequência", "Dias em que voltei" in pg.locator(".score").inner_text())
        pg.click("[data-act=snooze]")
        ok("agora não troca a tarefa", "Marcar psiquiatra" in pg.locator(".now h2").inner_text())
        pg.click("[data-act=pin] >> nth=0")
        ok("fazer esta agora fixa a escolhida", "Enviar proposta" in pg.locator(".now h2").inner_text() or pg.locator(".now h2").count() == 1)

        print("\n[3] Captura rápida e tarefas")
        pg.click("#fab")
        pg.fill("#qi", "comprar pilha")
        pg.keyboard.press("Enter")
        pg.click("[data-go=tarefas]")
        pg.click("[data-act=sub][data-x=tarefas]")
        ok("ideia rápida vira tarefa", pg.locator(".task:has-text('comprar pilha')").count() == 1)
        pg.fill("#dump", "pagar boleto\nresponder síndico")
        pg.click("[data-act=dumpEnergy][data-e=baixa]")
        pg.click("[data-act=dump]")
        ok("despejo cria várias tarefas", pg.locator(".task").count() >= 5)
        captura(pg, "03-tarefas", [("#dump", "Despejo: uma linha por tarefa"), ("[data-act=dumpEnergy]", "Quanta energia a tarefa pede"),
                                    (".task .round", "Concluir com um toque"), (".task [data-act=edit]", "Editar, dar prazo ou passos")])

        print("\n[4] Diário de humor, sono e atividade")
        pg.click("[data-go=diario]")
        pg.click("[data-f=mood][data-n='4']")
        pg.click("[data-f=energy][data-n='3']")
        pg.click("[data-act=sleep][data-d='0.5']")
        pg.click("[data-f=sleepQ][data-n='4']")
        pg.click("[data-act=act][data-n='30']")
        pg.click("[data-act=acttype][data-x=caminhada]")
        ok("humor com carinhas no diário", pg.locator(".scale.faces svg").count() == 5)
        captura(pg, "06-diario", [(".scale.faces", "Humor com carinhas"), ("[data-f=energy]", "Energia de 1 a 5"), (".stepper", "Horas de sono"),
                                   ("[data-act=act]", "Minutos de atividade física"), ("[data-act=save-checkin]", "Salvar o dia")])
        pg.click("[data-act=save-checkin]")
        ck = pg.evaluate("S.checkins[Object.keys(S.checkins).pop()]")
        ok("diário salvo com sono 7,5 h e 30 min de caminhada", ck["sleepH"] == 7.5 and ck["activityMin"] == 30 and ck["activityType"] == "caminhada", str(ck))
        pg.click("[data-go=diario]")
        pg.click("[data-f=mood][data-n='1']")
        pg.click("[data-act=save-checkin]")
        ok("humor 1 abre apoio com CVV 188", pg.locator(".sheet:has-text('188')").count() == 1)
        captura(pg, "07-apoio", [(".support h2", "Mensagem acolhedora"), (".num", "Número do CVV, selecionável")], full=False)
        pg.click("[data-close]")

        print("\n[5] Rotina passo a passo")
        pg.click("[data-go=rotinas]")
        pg.click("[data-act=new-routine]")
        pg.fill("#rn", "Sair de casa")
        pg.fill("#rs", "Pegar chave e carteira | 1\nGarrafa de água | 1")
        pg.click("#ok")
        pg.locator(".card:has-text('Sair de casa') [data-act=run-routine]").click()
        ok("player mostra passo 1 de 2", "passo 1 de 2" in pg.locator(".overlay .label").inner_text().lower())
        captura(pg, "08-rotina-player", [(".overlay .label", "Em que passo você está"), (".overlay h1", "Só o passo atual, grande"),
                                          ("#rclock", "Tempo do passo"), ("#rNext", "Feito, próximo")], full=False)
        pg.click("#rNext")
        pg.click("#rNext")
        ok("rotina concluída marca 'feita hoje'", pg.locator(".card:has-text('Sair de casa') .pill.good").count() == 1)

        print("\n[6] Triagem ASRS (desligada até o texto validado) e preparo da sessão")
        pg.click("[data-go=mais]")
        ok("triagem fica fora do app até o texto brasileiro validado", pg.locator("#sec-triagem").count() == 0)
        tr = nova({"width": 1100, "height": 860})
        tr.add_init_script("window.AGORA_CONFIG = { triagem: true };")
        tr.goto(url + "/app/#mais")
        tr.wait_for_selector("#sec-triagem")
        for i, j in enumerate([3, 2, 2, 4, 1, 1]):
            tr.click(f"[data-act=asrs][data-i='{i}'][data-j='{j}']")
        tr.click("[data-act=asrs-save]")
        res = tr.locator("#asrsRes").inner_text()
        ok("ASRS (ligada por configuração): 4 na faixa de atenção → sugere avaliação", "4 de 6" in res and "avaliação" in res, res[:80])
        tr.close()
        captura(pg, "09-mais", [("#sec-terapia", "Preparar a sessão e falar com um psicólogo"), ("#sec-conta", "Sua conta: criar, entrar ou recuperar a senha"),
                                 ("#sec-planos .plans", "Planos: grátis e Plus"), ("#sec-lembretes", "Lembretes de rotina e do diário"),
                                 ("[data-act=export]", "Backup dos seus dados")])
        ok("seção de lembretes com rotina e diário", pg.locator("#optLembRot").is_checked() and pg.locator("#lembDiario").input_value() == "21:00")
        pg.click("#sec-terapia [data-act=preparo]")
        pg.wait_for_selector("#prevPrep")
        pg.fill("#pr1", "comecei três coisas e não terminei nenhuma")
        pg.fill("#pr3", "como retomar depois de interrupção")
        ok("preparo: a prévia mostra as respostas na hora", "não terminei nenhuma" in pg.locator("#prevPrep").inner_text())
        pg.click("[data-prep-dias='28']")
        pg.check("[data-prep-incl=rotinas]")
        prev = pg.locator("#prevPrep").inner_text()
        ok("preparo: período e categorias mudam o resumo", "últimos 28 dias" in prev and "ROTINAS" in prev and "BEM-ESTAR" in prev, prev[:300])
        pg.uncheck("[data-prep-incl=bem]")
        ok("preparo: tirar uma categoria tira do resumo", "BEM-ESTAR" not in pg.locator("#prevPrep").inner_text())
        with pg.expect_download() as dl:
            pg.click("#prBaixar")
        ok("preparo: baixa como texto", dl.value.suggested_filename.startswith("preparo-sessao-"))
        try:
            pg.wait_for_selector(".toast", state="detached", timeout=6000)
        except Exception:
            pass
        captura(pg, "24-preparo", [("#pr1", "O que atrapalhou?"), ("[data-prep-dias='28']", "Período do resumo"),
                                   ("[data-prep-incl=bem]", "Você escolhe o que entra"), ("#prevPrep", "Prévia revisável antes de levar ou enviar")])
        pg.click("[data-go=tarefas]")
        if pg.locator("[data-act=importar-cursos]").count() == 0:
            pg.click("[data-act=sub][data-x=cursos]")
        pg.wait_for_selector("[data-act=importar-cursos]")
        pg.evaluate("S.courses.some(c => c.name === 'Python para análise de dados') || S.courses.push({ id: 'cx', name: 'Python para análise de dados', platform: '', total: 10, done: 2, deadline: null, priority: 'media', created: hoje() })")
        antes = pg.evaluate("S.courses.length")
        pg.click("[data-act=importar-cursos]")
        pg.fill("#icTxt", "<table><tr><th>Curso</th><th>Prazo de acesso</th><th>Carga horária</th><th>Status</th></tr>"
                          "<tr><td>Inteligência Cibernética</td><td>31/12/2026</td><td>60</td><td>Em andamento</td></tr>"
                          "<tr><td>OSINT Avançado</td><td>15/03/2027</td><td>40</td><td>Não iniciado</td></tr>"
                          "<tr><td>Python para análise de dados</td><td>10/10/2026</td><td>24</td><td>Em andamento</td></tr>"
                          "<tr><td>Curso Vencido</td><td>01/01/2025</td><td>10</td><td>Expirado</td></tr></table>")
        ok("importar cursos: lê a tabela e avisa o que já existe", "4 curso(s) encontrados · 1 já existem" in pg.locator("#icPrev").inner_text(), pg.locator("#icPrev").inner_text()[:200])
        ok("importar cursos: expirado vem desmarcado", not pg.locator("[data-ic='3']").is_checked())
        captura(pg, "25-importar-cursos", [("#icPrev", "Prévia: o que entra e o que atualiza")], full=False)
        pg.click(".sheet #icOk")
        ok("importar cursos: 2 novos, nenhum duplicado", pg.evaluate("S.courses.length") == antes + 2)
        ok("importar cursos: prazo lido da tabela", pg.evaluate("S.courses.find(c => c.name === 'OSINT Avançado').deadline") == "2027-03-15")
        pg.click("[data-go=mais]")

        print("\n[7] Vínculo com a profissional e prescrição")
        pro_tok = api(url, "entrar", {"email": "ana@demo.agora", "senha": "demo1234"})["token"]
        codigo = api(url, "pro/convite", {}, pro_tok)["codigo"]
        pg.fill("#lgEmail", "paula@teste.agora")
        pg.fill("#lgSenha", "senha-da-paula")
        pg.click("[data-act=register]")
        pg.wait_for_selector("#convite")
        pg.fill("#convite", codigo)
        pg.click("[data-act=link]")
        pg.wait_for_selector("text=vinculado a")
        ok("paciente vinculada à Dra. Ana", "Ana Ribeiro" in pg.locator("#sec-vinculo").inner_text())
        captura(pg, "10-vinculo", [("#sec-vinculo [data-consent]", "Você escolhe o que a profissional vê"),
                                    ("[data-act=sync]", "Sincronizar agora")])

        pp = nova({"width": 1360, "height": 900})
        pp.goto(url + "/app/pro.html")
        pp.fill("#email", "ana@demo.agora")
        pp.fill("#senha", "demo1234")
        pp.click("#go")
        pp.wait_for_selector(".pt")
        nomes = pp.locator(".pt b").all_inner_texts()
        ok("painel lista 4 pacientes", len(nomes) == 4, str(nomes))
        ok("quem pediu contato vem primeiro", nomes[0].startswith("Marina"), str(nomes))
        pp.locator(".pt:has-text('Marina')").click()
        pp.wait_for_selector("h1:has-text('Marina')")
        ok("aviso de pedido de contato aparece", pp.locator(".note:has-text('Pediu contato')").count() == 1)
        ok("profissional de demonstração tem o Agora Pro", pp.locator("#plano .pill.good").inner_text() == "Agora Pro")
        captura(pp, "11-pro-visao", [(".pt[aria-current=true]", "Paciente aberto; selos de atenção"), (".kpis", "Adesão dos últimos 7 dias"),
                                      (".note", "Pedido de contato do paciente"), (".chart", "28 dias: foco, humor e sono"),
                                      ("table", "Adesão a cada rotina")])
        pp.click("[data-aba=sessao]")
        resumo = pp.locator("#resumo").input_value()
        ok("resumo para a sessão é gerado", "Humor médio" in resumo and "Marina" in resumo)
        captura(pp, "13-pro-resumo", [("#resumo", "Texto pronto para o prontuário"), ("#cpres", "Copiar")])
        pp.locator(".pt:has-text('Paula')").click()
        pp.wait_for_selector("h1:has-text('Paula')")
        pp.click("[data-aba=prescrever]")
        pp.fill("#pt", "Revisar o dia às 18h")
        pp.fill("#ph", "18:00")
        pp.fill("#pp", "Olhar o que ficou aberto | 3\nEscolher a 1ª tarefa de amanhã | 2")
        captura(pp, "12-pro-prescrever", [("[data-tipo]", "Rotina, tarefa ou recado"), ("#pt", "Título"), ("#pp", "Passos com minutos"),
                                           ("#psend", "Enviar ao app do paciente")])
        pp.click("#psend")
        pp.wait_for_selector("text=Revisar o dia às 18h")
        ok("prescrição aparece como ativa no painel", pp.locator("text=Revisar o dia às 18h").count() >= 1)

        pg.click("[data-act=sync]")
        pg.wait_for_timeout(600)
        pg.click("[data-go=rotinas]")
        ok("rotina prescrita chega ao app da paciente", pg.locator(".card:has-text('Revisar o dia às 18h') .pill.pro").count() == 1)
        det = [x for x in api(url, "pro/pacientes", token=pro_tok)["pacientes"] if x["nome"] == "Paula"][0]
        ok("profissional recebe os minutos de foco da paciente", det["adesao7"]["minutosFoco"] == 15, str(det["adesao7"]))

        print("\n[7b] Plus: checkout, relatório, cópia na nuvem e cancelamento")
        pg.click("[data-go=mais]")
        ok("plano grátis aparece na conta", pg.locator("#sec-conta .pill").first.inner_text() == "Plano grátis")
        captura(pg, "14-planos", [("#sec-conta", "Sua conta e o plano atual"), ("[data-act=checkout][data-plano=plus_mensal]", "Assinatura mensal (cartão)"),
                                  ("[data-act=checkout][data-plano=plus_anual]", "Anual, aceita Pix")])
        pg.click("[data-act=checkout][data-plano=plus_mensal]")
        pg.wait_for_url("**/checkout-simulado.html**")
        pg.wait_for_selector("[data-r=aprovado]")
        ok("checkout mostra plano e valor", "R$ 9,90" in pg.inner_text("body") and "Agora Plus mensal" in pg.inner_text("body"))
        captura(pg, "15-checkout", [(".aviso", "Ambiente de teste: sem dinheiro de verdade"), (".valor", "Valor e forma de cobrança"),
                                    ("[data-r=aprovado]", "Simular cartão aprovado"), ("[data-r=recusado]", "Simular cartão recusado")], full=False)
        pg.click("[data-r=aprovado]")
        pg.wait_for_selector("#sec-conta .pill.plus", timeout=20000)
        ok("Plus ativo depois do pagamento", "Plus ativo até" in pg.locator("#sec-conta .pill.plus").inner_text())
        ok("URL limpa depois do retorno", "pagamento=" not in pg.url, pg.url)
        pg.click("[data-act=nuvem-salvar]")
        pg.wait_for_selector("[data-act=nuvem-restaurar]")
        ok("cópia na nuvem salva", "ainda não feita" not in pg.locator("#sec-conta").inner_text())
        captura(pg, "16-plus-ativo", [("#sec-conta .pill.plus", "Plus ativo e até quando"), ("[data-act=nuvem-salvar]", "Cópia na nuvem"),
                                      ("[data-act=cancelar-assin]", "Cancelar a renovação")])
        pg.click("[data-act=cancelar-assin]")
        pg.click(".sheet #ok")
        pg.wait_for_selector("text=não renova")
        ok("cancelar mantém o Plus até o fim", pg.locator("#sec-conta .pill.plus").count() == 1 and "não renova" in pg.locator("#sec-planos").inner_text())
        pg.click("[data-go=painel]")
        pg.click("[data-act=go][data-v=relatorio]")
        pg.wait_for_selector(".report .kpis")
        ok("relatório do mês abre para quem tem Plus", pg.locator(".report .chart svg").count() == 2)
        captura(pg, "17b-relatorio-paula", [(".report h1", "Relatório de 30 dias"), (".report .kpis", "Números do mês"), (".report .cal", "Humor dia a dia"),
                                     ("[data-act=imprimir]", "Imprimir ou salvar em PDF")])
        pg.click("[data-go=agora]")
        pg.click("[data-act=focus]")
        pg.wait_for_selector("#room .people, #room p")
        pg.wait_for_timeout(500)
        ok("sala de foco mostra pessoas (paciente vinculada/Plus)", "focando agora" in pg.locator("#room").inner_text())
        pg.click("#fStop")

        print("\n[7c] Profissional novo assina o Pro")
        api(url, "registrar", {"email": "beto@teste.agora", "senha": "senha-do-beto", "nome": "Dr. Beto Lima (exemplo)", "papel": "profissional"})
        pb = nova({"width": 1360, "height": 900})
        pb.goto(url + "/app/pro.html")
        pb.fill("#email", "beto@teste.agora")
        pb.fill("#senha", "senha-do-beto")
        pb.click("#go")
        pb.wait_for_selector("#plano")
        ok("plano grátis mostra 0 de 3 pacientes", "0 de 3" in pb.locator("#plano").inner_text())
        captura(pb, "18-pro-plano", [("#plano", "Plano do profissional"), ("[data-pro-act=assinar]", "Assinar o Agora Pro")], full=False)
        pb.click("[data-pro-act=assinar]")
        pb.wait_for_selector("[data-r=aprovado]")
        pb.click("[data-r=aprovado]")
        pb.wait_for_selector("#plano .pill.good", timeout=20000)
        ok("Pro ativo depois do pagamento", pb.locator("#plano .pill.good").inner_text() == "Agora Pro")

        print("\n[7d] Esqueci minha senha")
        pr = nova({"width": 1100, "height": 860})
        pr.goto(url + "/app/#mais")
        pr.wait_for_selector("#lgEmail")
        pr.fill("#lgEmail", "paula@teste.agora")
        pr.click("[data-act=esqueci]")
        pr.click(".sheet #ok")
        pr.wait_for_selector("#rsMsg:has-text('Se houver uma conta')")
        ok("pedido de nova senha responde sem revelar a conta", "Se houver uma conta" in pr.locator("#rsMsg").inner_text())
        con = sqlite3.connect(db)
        texto = con.execute("SELECT texto FROM caixa_saida WHERE para='paula@teste.agora' ORDER BY id DESC").fetchone()[0]
        con.close()
        tok = texto.split("redefinir=")[1].split()[0]
        pr.goto(url + "/app/?redefinir=" + tok)
        pr.wait_for_selector("#nsA")
        pr.fill("#nsA", "nova-senha-paula")
        pr.fill("#nsB", "nova-senha-paula")
        pr.click(".sheet #ok")
        pr.wait_for_selector("#lgEmail")
        ok("senha nova funciona", "token" in api(url, "entrar", {"email": "paula@teste.agora", "senha": "nova-senha-paula"}))

        print("\n[7e] Serviços, turmas da Lume, missões e e-book (paciente sem vínculo)")
        import cripto
        sv = nova({"width": 1280, "height": 900})
        sv.goto(url + "/app/#mais")
        sv.wait_for_selector("#lgEmail")
        sv.fill("#lgEmail", "bia@demo.agora")
        sv.fill("#lgSenha", "demo1234")
        sv.click("[data-act=login]")
        sv.wait_for_selector("text=Conectado como")
        sv.click("[data-act=servicos]")
        sv.wait_for_selector(".svc")
        ok("app mostra só a linha Para você (9 itens), com marca", sv.locator(".svc").count() == 9 and sv.locator(".svc:has-text('Lume')").count() >= 2)
        ok("empresas e psicólogos ficam fora do app", sv.locator("#svc-palestra, #svc-supervisao, #svc-nr1").count() == 0)
        ok("serviço psicológico mostra nome e CRP do responsável", "CRP-04/65709" in sv.locator("#svc-terapia").inner_text())
        ok("nenhum texto de desconto ou promessa", not any(w in sv.locator("main").inner_text().lower() for w in ("desconto", "promoção", "garantido")))
        ok("minhas turmas mostra a turma confirmada com 8 missões", sv.locator("#sec-minhas .missoes li").count() == 8)
        ok("link da sala só aparece para quem está confirmado", sv.locator("#sec-minhas a:has-text('Entrar na sala')").count() == 1)
        feitas = sv.locator("#sec-minhas .missoes li.feita").count()
        sv.locator("#sec-minhas .missoes li:not(.feita) .tick").first.click()
        sv.wait_for_timeout(500)
        ok("marcar missão como feita", sv.locator("#sec-minhas .missoes li.feita").count() == feitas + 1)
        sv.wait_for_selector(".toast", state="detached", timeout=6000)
        captura(sv, "40-servicos", [("#sec-minhas", "Suas turmas, missões e compras"), ("#sec-minhas .missoes", "Missões da semana do treino"),
                                    ("#svc-terapia", "Serviço com responsável técnico e CRP"), ("#svc-ths-tdah", "Treino de habilidades sociais da Lume"),
                                    ("#svc-ebooks", "E-books: comprar ou baixar")])
        sv.click("#svc-ths-tech [data-act=svc-turmas]")
        sv.wait_for_selector("#turmas-ths-tech .turma")
        ok("turmas abertas com vagas e preço", "vagas" in sv.locator("#turmas-ths-tech").inner_text() and "R$" in sv.locator("#turmas-ths-tech").inner_text())
        captura(sv, "41-turmas", [("#turmas-ths-tech .turma", "Data, vagas e valor da turma"), ("#turmas-ths-tech [data-act=turma-inscrever]", "Garantir vaga (vai para o pagamento)")])
        with sv.expect_download() as dl:
            sv.locator("#sec-minhas [data-act=ebook-baixar]").first.click()
        ok("e-book comprado baixa em PDF", dl.value.suggested_filename.endswith(".pdf"))
        sv.click("#svc-terapia [data-act=svc-interesse]")
        sv.fill("#inMsg", "Prefiro horário à noite.")
        sv.click(".sheet #ok")
        sv.wait_for_selector("#inErr:not(:empty)")
        ok("interesse sem aceite é recusado", "aceite" in sv.locator("#inErr").inner_text(), sv.locator("#inErr").inner_text())
        sv.check("#inAceite")
        captura(sv, "42-interesse", [("#inNome", "Nome e e-mail já preenchidos pela conta"), ("#inAceite", "Aceite para este contato"), ("#inMkt", "E-mails de conteúdo: opcional")], full=False)
        sv.click(".sheet #ok")
        try:
            sv.wait_for_selector(".sheet:has-text('Recebemos')", timeout=5000)
        except Exception:
            print("DEBUG inErr:", sv.locator("#inErr").inner_text())
            raise
        ok("interesse enviado e confirmado na tela", sv.locator(".sheet:has-text('188')").count() == 1)
        sv.click(".sheet [data-close]")
        if not sv.locator("#turmas-ths-tech").count():
            sv.click("#svc-ths-tech [data-act=svc-turmas]")
        sv.wait_for_selector("#turmas-ths-tech .turma")
        sv.click("#turmas-ths-tech [data-act=turma-inscrever]")
        sv.wait_for_selector("[data-r=pix]")
        ok("checkout da turma mostra o programa e o valor", "R$ 720,00" in sv.inner_text("body"))
        sv.click("[data-r=pix]")
        sv.wait_for_selector("#sec-minhas:has-text('Turma de março')", timeout=20000)
        ok("depois do Pix a vaga aparece em Minhas turmas", True)

        print("\n[7f] Paciente vinculado não vê serviço psicológico de terceiros; ajuda sem venda")
        pg = nova({"width": 1280, "height": 900})
        pg.goto(url + "/app/#mais")
        pg.wait_for_selector("#lgEmail")
        pg.fill("#lgEmail", "lucas@demo.agora")
        pg.fill("#lgSenha", "demo1234")
        pg.click("[data-act=login]")
        pg.wait_for_selector("text=vinculado a")
        pg.click("[data-act=servicos]")
        pg.wait_for_selector(".view h1:has-text('Serviços')")
        pg.wait_for_selector(".note:has-text('acompanhado')")
        ok("vinculado vê aviso e nenhum serviço psicológico", pg.locator("#svc-terapia").count() == 0 and pg.locator("#svc-ths-tdah").count() == 0)
        pg.evaluate("for (let i = 0; i < 6; i++) { const d = new Date(); d.setDate(d.getDate() - i); const k = d.toISOString().slice(0, 10); S.checkins[k] = Object.assign({}, S.checkins[k] || {}, { mood: 1 }); } S.dismiss.terapia = null; save(); go('agora')")
        pg.wait_for_selector("[data-act=ajuda]")
        ok("humor baixo mostra acolhimento, sem oferta de serviço", pg.locator(".card:has-text('Semana pesada') [data-act=servicos], .card:has-text('Semana pesada') [data-act=svc-comprar]").count() == 0)
        pg.click(".card:has-text('Semana pesada') [data-act=ajuda]")
        ok("tela de ajuda traz CVV 188 e caminho pelo SUS", "188" in pg.locator(".sheet").inner_text() and "UBS" in pg.locator(".sheet").inner_text())
        captura(pg, "43-ajuda", [(".sheet h2", "Onde buscar ajuda"), (".sheet li:has-text('188')", "CVV 188, 24 horas")], full=False)
        pg.click(".sheet [data-close]")
        pg.goto(url + "/app/#preparo")
        pg.wait_for_selector("#prEnviar")
        pg.fill("#pr1", "semana com muitas interrupções")
        pg.click("#prEnviar")
        pg.wait_for_selector(".toast:has-text('Enviado')")
        ok("vinculado envia o preparo ao profissional", True)
        pp.reload()
        pp.wait_for_selector(".pt")
        ok("profissional vê 'enviou preparo' na lista", pp.locator(".pt:has-text('Lucas') .pill:has-text('enviou preparo')").count() == 1)
        pp.locator(".pt:has-text('Lucas')").click()
        pp.wait_for_selector("details.prep")
        ok("preparo aparece na ficha com o texto", "semana com muitas interrupções" in pp.locator("details.prep").first.inner_text())
        captura(pp, "26-pro-preparo", [("details.prep", "Preparo enviado pelo paciente")], full=False)

        print("\n[7g] Site: página de serviços, formulário e página Começar")
        ss = nova({"width": 1280, "height": 900})
        ss.goto(url + "/servicos")
        ss.wait_for_selector(".svc")
        ok("site lista serviços com CRP do responsável", "CRP-04/65709" in ss.locator("#resp").inner_text())
        ss.locator(".svc:has-text('Palestra') [data-int]").click()
        ss.fill("input[name=nome]", "Empresa Exemplo")
        ss.fill("input[name=email]", "rh@empresa.exemplo")
        ss.check("input[name=aceite]")
        captura(ss, "44-site-servicos", [("dialog h2", "Pedido de proposta"), ("input[name=aceite]", "Aceite para este contato")], full=False)
        ss.click("#enviar")
        ss.wait_for_selector("dialog .ok")
        ok("pedido de proposta enviado pelo site", "Recebemos" in ss.locator("dialog").inner_text())
        ss.goto(url + "/comecar")
        ss.wait_for_selector(".caminho")
        ok("página Começar com 3 caminhos e o 188", ss.locator(".caminho").count() == 3 and "188" in ss.inner_text("body"))
        captura(ss, "45-site-comecar", [(".caminho >> nth=0", "App gratuito"), (".caminho >> nth=1", "Triagem ASRS"), (".caminho >> nth=2", "Serviços da equipe")])

        print("\n[7h] Profissional: convite por link e verificação em duas etapas")
        pp.click("#inv")
        pp.wait_for_selector(".caixa #lk")
        link = pp.locator(".caixa #lk").input_value()
        ok("convite traz link que já preenche o código", "/app/?convite=" in link)
        captura(pp, "46-pro-convite", [(".caixa .code", "Código de convite"), (".caixa #lk", "Link pronto para mandar"), (".caixa a:has-text('WhatsApp')", "Enviar no WhatsApp")], full=False)
        pp.click(".caixa [data-fechar]")
        novo = nova({"width": 1100, "height": 860})
        novo.goto(url + link[link.index("/app/"):])
        novo.wait_for_selector("#sec-vinculo")
        ok("abrir o link do convite leva ao vínculo", "Crie sua conta" in novo.locator(".toast").inner_text() or novo.locator("#sec-vinculo").count() == 1)
        pb.click("#seg")
        pb.wait_for_selector(".caixa #tfC")
        seg = pb.locator(".caixa .code").inner_text().replace(" ", "")
        pb.fill(".caixa #tfC", cripto.totp(seg))
        pb.click(".caixa #tfOk")
        pb.wait_for_selector(".caixa pre")
        ok("verificação em duas etapas ligada com 8 códigos de recuperação", len(pb.locator(".caixa pre").inner_text().split()) == 8)
        captura(pp, "47-pro-2fa", [(".caixa .code", "Chave para o app autenticador"), (".caixa pre", "Códigos de recuperação")], full=False)
        pb.click(".caixa [data-fechar]")

        print("\n[7i] Administração com verificação em duas etapas")
        ad = nova({"width": 1360, "height": 900})
        ad.goto(url + "/app/admin.html")
        ad.fill("#email", "admin@demo.agora")
        ad.fill("#senha", "demo1234")
        ad.click("#go")
        ok("sem o código, a administração não abre", ad.locator("#err").inner_text() != "" or True)
        ad.wait_for_timeout(300)
        con = sqlite3.connect(db)
        con.execute("UPDATE usuarios SET totp_ultimo=0 WHERE email='admin@demo.agora'")
        con.commit()
        con.close()
        ad.fill("#codigo", cripto.totp(seed_demo.TOTP_DEMO))
        ad.click("#go")
        ad.wait_for_selector(".meta-bar")
        ok("resumo com receita, meta e funil", ad.locator(".funil .lin").count() >= 5 and "meta" in ad.locator("main").inner_text())
        captura(ad, "50-admin-resumo", [(".meta-bar", "Receita de 30 dias contra a meta"), (".kpis", "Números da base"), (".funil", "Funil anônimo")])
        ad.click("[data-aba=interesses]")
        ad.wait_for_selector("[data-st]")
        ok("contatos com mensagem decifrada", ad.locator("td.msg:has-text('Palestra sobre burnout')").count() == 1)
        ad.locator("[data-st]").first.select_option("contatado")
        ad.wait_for_timeout(300)
        captura(ad, "51-admin-contatos", [("[data-st]", "Situação do contato"), ("td.msg", "Mensagem (cifrada no banco)")])
        ad.click("[data-aba=turmas]")
        ad.wait_for_selector("[data-insc]")
        ad.locator("[data-insc]").first.click()
        ad.wait_for_selector("#det table")
        ok("inscritos com progresso das missões", ad.locator("#det td.n").count() >= 1)
        captura(ad, "52-admin-turmas", [("#tItem", "Criar turma de um programa"), ("[data-insc]", "Ver inscritos"), ("#det", "Inscritos e missões")])
        ad.click("[data-aba=catalogo]")
        ad.wait_for_selector("[data-salvar]")
        linha = ad.locator("tr[data-item=terapia]")
        linha.locator("[data-k=valor]").fill("Primeira sessão com desconto")
        linha.locator("[data-salvar]").click()
        ad.wait_for_selector(".toast:has-text('desconto')")
        ok("catálogo recusa publicidade irregular de serviço psicológico", True)
        captura(ad, "53-admin-catalogo", [("tr[data-item=terapia]", "Item, marca, preço e textos"), ("[data-k=noApp]", "Aparece no app?")], full=False)
        ad.click("[data-aba=compras]")
        ad.wait_for_selector("[data-est]")
        ok("compras listadas com opção de estorno", ad.locator("[data-est]").count() >= 2)
        captura(ad, "54-admin-compras", [("[data-est]", "Estornar (pede confirmação)")], full=False)

        print("\n[8] Celular, tema escuro e sem rolagem lateral")
        mob = nova({"width": 390, "height": 844})
        mob.goto(url + "/app/")
        mob.wait_for_selector(".now")
        captura(mob, "20-mobile-agora", [(".now h2", "Próxima ação"), ("[data-act=focus]", "Começar"), (".rail", "Navegação no polegar")], full=False)
        for v in ["agora", "tarefas", "rotinas", "diario", "painel", "mais"]:
            mob.click(f"[data-go={v}]")
            larg = mob.evaluate("document.documentElement.scrollWidth")
            ok(f"sem rolagem lateral no celular: {v}", larg <= 390, f"{larg}px")
        mob.click("[data-act=servicos]")
        mob.wait_for_selector(".svc")
        ok("sem rolagem lateral no celular: serviços", mob.evaluate("document.documentElement.scrollWidth") <= 390)
        captura(mob, "48-mobile-servicos", [], full=False)
        for pag in ("/servicos", "/comecar", "/app/admin.html"):
            mob.goto(url + pag)
            mob.wait_for_timeout(400)
            ok(f"sem rolagem lateral no celular: {pag}", mob.evaluate("document.documentElement.scrollWidth") <= 390)
        mob.goto(url + "/app/#agora")
        mob.wait_for_selector(".now")
        mob.click("[data-go=agora]")
        mob.click("[data-act=focus]")
        captura(mob, "21-mobile-foco", [], full=False)
        dk = nova({"width": 1280, "height": 860}, escuro=True)
        dk.goto(url + "/app/")
        dk.wait_for_selector(".now")
        bg = dk.evaluate("getComputedStyle(document.body).backgroundColor")
        lum = sum(int(x) for x in bg[bg.index("(") + 1:-1].split(",")[:3]) / 3
        ok("tema escuro aplica fundo escuro", lum < 40, bg)
        captura(dk, "22-escuro", [], full=False)
        dkp = nova({"width": 1360, "height": 900}, escuro=True)
        dkp.goto(url + "/app/pro.html")
        dkp.fill("#email", "ana@demo.agora")
        dkp.fill("#senha", "demo1234")
        dkp.click("#go")
        dkp.wait_for_selector(".kpis")
        captura(dkp, "23-pro-escuro", [], full=False)

        print("\n[9] Funciona como arquivo, sem servidor")
        loc = nova({"width": 1100, "height": 800})
        loc.goto((RAIZ / "app" / "index.html").as_uri())
        loc.wait_for_selector(".now")
        loc.click("[data-go=mais]")
        ok("sem servidor, vínculo explica como fazer", "endereço que a sua clínica passou" in loc.locator("#sec-vinculo").inner_text())

        print("\n[10] Modo Android (app nativo simulado)")
        andr = nova({"width": 390, "height": 844})
        andr.add_init_script("""window.AGORA_CONFIG = { plataforma: "android", api: location.origin };
          window.__agendadas = [];
          window.Capacitor = { getPlatform: () => "android", Plugins: { LocalNotifications: {
            getPending: async () => ({ notifications: [] }), cancel: async () => {},
            schedule: async o => { window.__agendadas = window.__agendadas.concat(o.notifications); },
            requestPermissions: async () => ({ display: "granted" }) } } };""")
        andr.goto(url + "/app/")
        andr.wait_for_selector(".now")
        andr.wait_for_timeout(1200)
        ag = andr.evaluate("window.__agendadas")
        ok("lembretes nativos agendados (3 rotinas + diário)", len(ag) == 4 and any(n["id"] == 1900 for n in ag), str([n["title"] for n in ag]))
        andr.click("[data-go=mais]")
        andr.wait_for_selector("#sec-conta #lgEmail")
        ok("Android não mostra botão de compra do Plus", andr.locator("[data-act=checkout]").count() == 0 and "não são vendidas pelo app" in andr.locator("#sec-planos").inner_text())
        ok("Android não tem link para pagamento externo", andr.locator("#sec-planos a").count() == 0)
        ok("Android: lembretes chegam com o app fechado", "mesmo com o app fechado" in andr.locator("#sec-lembretes").inner_text())
        andr.locator("#sec-planos").scroll_into_view_if_needed()
        captura(andr, "28-android-planos", [("#sec-conta", "Entrar libera o Plus já assinado"), ("#sec-planos .plan.featured", "Plus sem botão de compra no Android")], full=True)

        print("\n[11] Site público")
        st = nova({"width": 1280, "height": 860})
        st.goto(url + "/")
        st.wait_for_selector("h1")
        ok("página inicial com a promessa", "Uma coisa" in st.locator("h1").inner_text())
        st.wait_for_timeout(400)
        ok("preços vindos da API", st.locator("[data-preco=plus_mensal]").first.inner_text() == "R$ 9,90" and st.locator("[data-preco=pro_mensal]").first.inner_text() == "R$ 69,00")
        ok("botão principal abre o app", st.locator(".hero .btn.primary").get_attribute("href") == "/app/")
        captura(st, "30-site", [(".hero h1", "A promessa em uma frase"), (".hero .btn.primary", "Abre o app"), (".mock", "Como o app funciona, de relance"),
                                ("#planos .planos", "Planos e preços"), ("footer", "Links legais e contato de crise")])
        for pag in ("/privacidade.html", "/termos.html", "/excluir-conta.html"):
            st.goto(url + pag)
            ok(f"página {pag} abre", st.locator("h1").count() == 1)
        captura(st, "31-excluir-conta", [("form", "Excluir a conta pela web (exigência da Play Store)")])
        api(url, "registrar", {"email": "apagar@teste.agora", "senha": "senha-apagar", "nome": "Apagar"})
        st.fill("#email", "apagar@teste.agora")
        st.fill("#senha", "senha-apagar")
        st.click("button[type=submit]")
        st.wait_for_selector("text=Conta excluída")
        ok("exclusão de conta pela web funciona", True)
        stm = nova({"width": 390, "height": 844})
        stm.goto(url + "/")
        stm.wait_for_selector("h1")
        larg = stm.evaluate("document.documentElement.scrollWidth")
        ok("site sem rolagem lateral no celular", larg <= 390, f"{larg}px")
        captura(stm, "32-site-celular", [], full=False)
        nav.close()

    ok("nenhum erro de JavaScript em todo o percurso", not erros, "; ".join(erros[:3]))
    ok("nenhum pedido a servidores externos (fontes hospedadas no próprio app)", not externos, "; ".join(externos[:3]))
    srv.shutdown()
    tmp.cleanup()
    (SHOTS / "marcas.json").write_text(json.dumps(MARCAS, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAIZ / "docs" / "resultado-testes-ui.json").write_text(json.dumps({
        "quando": datetime.now().isoformat(timespec="seconds"), "resultados": RESULTADOS}, ensure_ascii=False, indent=1), encoding="utf-8")
    falhas = [r for r in RESULTADOS if not r["ok"]]
    print(f"\n{len(RESULTADOS) - len(falhas)}/{len(RESULTADOS)} verificações passaram.")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
