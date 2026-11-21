#!/usr/bin/env python3
"""Cria o caso de demonstração: 1 profissional e 3 pacientes com 28 dias de uso fictício.

Contas criadas (todas com a senha  demo1234):
  profissional  ana@demo.agora     (Dra. Ana Ribeiro — exemplo)
  paciente      lucas@demo.agora   adesão boa, sono influencia o foco
  paciente      marina@demo.agora  semana de humor baixo e pedido de contato
  paciente      rafael@demo.agora  adesão baixa, quase não preenche o diário
  paciente      bia@demo.agora     sem vínculo: está numa turma da Lume e comprou um e-book
  administração admin@demo.agora   chave do autenticador (TOTP): JBSWY3DPEHPK3PXP

Uso: python3 seed_demo.py [--db caminho/agora.db]
"""
import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402

SENHA = "demo1234"
TOTP_DEMO = "JBSWY3DPEHPK3PXP"  # chave pública de exemplo: só para o caso de demonstração


def pdf_amostra(titulo):
    """PDF de uma página, válido, para os e-books de demonstração."""
    t = titulo.encode("latin-1", "replace").replace(b"(", b"[").replace(b")", b"]")
    texto = (b"BT /F1 20 Tf 60 760 Td (" + t + b") Tj 0 -34 Td /F1 12 Tf (Amostra de demonstracao do Agora.) Tj "
             b"0 -18 Td (Substitua este arquivo pelo e-book final em dados/ebooks.) Tj ET")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(texto)).encode() + b" >>\nstream\n" + texto + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, pos = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        pos.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{p:010d} 00000 n \n".encode() for p in pos)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def dia(n):
    return (date.today() - timedelta(days=n)).isoformat()


def gera_dados(nome, perfil, seed):
    rnd = random.Random(seed)
    rotinas = [
        {"id": "r1", "name": "Arranque da manhã", "time": "07:30",
         "steps": [{"t": "Beber água", "min": 1}, {"t": "Remédio e café", "min": 5}, {"t": "Banho", "min": 10}]},
        {"id": "r2", "name": "Desligar o dia", "time": "22:30",
         "steps": [{"t": "Anotar o que ficou na cabeça", "min": 3}, {"t": "Celular fora do quarto", "min": 1}]},
    ]
    checkins, sessions, runs = {}, [], []
    for i in range(27, -1, -1):
        d = dia(i)
        p_ck = {"bom": .9, "baixo": .85, "irregular": .3}[perfil]
        sono = round((5 + rnd.random() * 3.5) * 2) / 2
        ativ = rnd.choice([0, 0, 20, 30, 45]) if perfil != "irregular" else rnd.choice([0, 0, 0, 20])
        base = 2 + (sono >= 7) + (.7 if ativ >= 20 else 0) + (rnd.random() - .5) * 1.2
        if perfil == "baixo" and i < 7:
            base -= 1.6
        humor = max(1, min(5, round(base)))
        if rnd.random() < p_ck or (perfil == "baixo" and i < 7):
            checkins[d] = {"mood": humor, "energy": max(1, min(5, round(base + rnd.random() - .5))), "sleepH": sono,
                           "sleepQ": max(1, min(5, round(sono - 3.5))), "activityMin": ativ,
                           "activityType": rnd.choice(["caminhada", "academia", "bike"]) if ativ else "",
                           "meds": rnd.random() < .8, "note": ""}
        n = {"bom": 2.5, "baixo": 1.2, "irregular": .5}[perfil] + (1 if sono >= 7 else 0)
        for _ in range(int(n + rnd.random() * 1.5)):
            sessions.append({"date": d, "min": rnd.choice([15, 25, 25, 50]), "feel": rnd.choice(["fluiu", "ok", "travei"])})
        if rnd.random() < {"bom": .8, "baixo": .5, "irregular": .2}[perfil]:
            runs.append({"date": d, "routineId": "r1", "done": 3, "total": 3})
        if rnd.random() < {"bom": .5, "baixo": .3, "irregular": .1}[perfil]:
            runs.append({"date": d, "routineId": "r2", "done": 2, "total": 2})
    if perfil == "baixo":
        checkins[dia(1)]["note"] = "não consegui sair da cama de manhã"
        checkins[dia(3)]["note"] = "briga no trabalho, travei o dia todo"
    tarefas = [
        {"id": "t1", "title": "Relatório mensal", "energy": "alta", "type": "trabalho", "priority": "alta", "created": dia(5), "done": False,
         "steps": [{"t": "Abrir a planilha", "done": True}, {"t": "Escrever o resumo", "done": False}]},
        {"id": "t2", "title": "Marcar dentista", "energy": "baixa", "type": "saude", "priority": "media", "created": dia(9), "done": False, "steps": []},
    ]
    asrs = [{"date": dia(25), "type": "ASRS-A", "answers": [3, 3, 2, 4, 3, 2], "positives": 5, "positive": True}]
    cursos = [{"id": "c1", "name": "Python para análise de dados", "platform": "Alura", "total": 40, "done": 12 + seed % 9,
               "deadline": (date.today() + timedelta(days=45)).isoformat(), "priority": "alta"}]
    return {"v": 2, "profile": {"name": nome}, "tasks": tarefas, "courses": cursos, "routines": rotinas, "routineRuns": runs,
            "sessions": sessions, "checkins": checkins, "screenings": asrs}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(server.RAIZ / "dados" / "agora.db"))
    a = ap.parse_args(argv)
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    api = server.API(server.Banco(a.db))

    def conta(email, nome, papel, **extra):
        try:
            r = api.registrar(corpo={"email": email, "nome": nome, "senha": SENHA, "papel": papel, **extra})
        except server.ErroAPI as e:
            if e.status != 409:
                raise
            import cripto
            r = api.entrar(corpo={"email": email, "senha": SENHA, "codigo": cripto.totp(TOTP_DEMO)})
        return {"Authorization": "Bearer " + r["token"]}

    pro = conta("ana@demo.agora", "Dra. Ana Ribeiro (exemplo)", "profissional",
                registro="CRP 00/00000 (fictício)", contato="(31) 90000-0000 — número fictício")
    ja = {p["nome"] for p in api.pacientes(cab=pro)["pacientes"]}
    # A profissional de demonstração tem o Agora Pro de cortesia (pacientes ilimitados).
    con = api.db.con()
    pid = con.execute("SELECT id FROM usuarios WHERE email='ana@demo.agora'").fetchone()["id"]
    if not con.execute("SELECT 1 FROM assinaturas WHERE usuario_id=? AND provedor='cortesia'", (pid,)).fetchone():
        agora = server.agora_iso()
        fim = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(timespec="seconds")
        con.execute("INSERT INTO assinaturas(usuario_id,plano,direito,provedor,ref_externa,status,fim_periodo,cancelar_no_fim,criado_em,atualizado_em) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", (pid, "pro_mensal", "pro", "cortesia", "demo", "ativa", fim, 1, agora, agora))
        con.commit()
    con.close()
    todos = {"checkins": True, "foco": True, "rotinas": True, "tarefas": True, "triagem": True}
    for email, nome, perfil, seed, cons in [
        ("lucas@demo.agora", "Lucas Andrade", "bom", 7, todos),
        ("marina@demo.agora", "Marina Costa", "baixo", 11, dict(todos, tarefas=False)),
        ("rafael@demo.agora", "Rafael Souza", "irregular", 23, dict(todos, tarefas=False, triagem=False)),
    ]:
        cab = conta(email, nome, "paciente")
        if nome not in ja:
            codigo = api.convite(cab=pro)["codigo"]
            api.vincular(corpo={"codigo": codigo, "consentimento": cons}, cab=cab)
        api.sync(corpo={"dados": gera_dados(nome.split()[0], perfil, seed)}, cab=cab)
        if perfil == "baixo" and nome not in ja:
            api.pedir_contato(corpo={"motivo": "humor muito baixo no diário"}, cab=cab)
    lucas = [p for p in api.pacientes(cab=pro)["pacientes"] if p["nome"].startswith("Lucas")][0]
    if not api.paciente(cab=pro, ids=[lucas["id"]])["prescricoes"]:
        api.prescrever(cab=pro, ids=[lucas["id"]], corpo={"tipo": "rotina", "conteudo": {
            "titulo": "Pausa de corpo", "horario": "15:00",
            "passos": [{"t": "Levantar e alongar o pescoço", "min": 2}, {"t": "Respirar 6 vezes na janela", "min": 2},
                       {"t": "Escrever em 1 linha o que estou fazendo", "min": 1}]}})
        api.prescrever(cab=pro, ids=[lucas["id"]], corpo={"tipo": "mensagem", "conteudo": {
            "titulo": "Observar horários", "texto": "Repare em que horário a tarefa pesada flui melhor. Só observar."}})
    funil_demo(api, conta)
    print("Caso de demonstração pronto. Senha de todas as contas: " + SENHA)
    print("  Profissional:   ana@demo.agora")
    print("  Pacientes:      lucas@demo.agora · marina@demo.agora · rafael@demo.agora · bia@demo.agora")
    print("  Administração:  admin@demo.agora  (autenticador: chave " + TOTP_DEMO + ")")


def funil_demo(api, conta):
    """Turmas da Lume, uma aluna com missões, um e-book comprado, contatos e eventos do funil."""
    import cripto
    pasta = Path(api.cfg.ebooks_dir)
    pasta.mkdir(parents=True, exist_ok=True)
    for it in api.catalogo.dados["itens"]:
        for t in (it.get("venda") or {}).get("titulos", []):
            arq = pasta / f"{t['id']}.pdf"
            if not arq.exists():
                arq.write_bytes(pdf_amostra(t["titulo"]))
    adm = conta("admin@demo.agora", "Equipe Lume (exemplo)", "profissional")
    con = api.db.con()
    con.execute("UPDATE usuarios SET admin=1, totp_segredo=COALESCE(totp_segredo, ?) WHERE email='admin@demo.agora'",
                (api.cifra(TOTP_DEMO, "totp"),))
    con.commit()
    ja = con.execute("SELECT COUNT(*) n FROM turmas").fetchone()["n"]
    con.close()
    if ja:
        return
    # o login do admin pede código: usa a sessão já aberta pelo registro (ou entra com o código atual)
    if "Authorization" not in adm:
        r = api.entrar(corpo={"email": "admin@demo.agora", "senha": SENHA, "codigo": cripto.totp(TOTP_DEMO)})
        adm = {"Authorization": "Bearer " + r["token"]}
    em = lambda d: (date.today() + timedelta(days=d)).isoformat()  # noqa: E731
    t1 = api.admin_turma_criar(cab=adm, corpo={"item": "ths-tdah", "nome": "Turma de demonstração · terças 19h", "inicio": em(-14), "fim": em(42),
                                               "encontros": "8 encontros semanais de 90 min", "local": "Online", "vagas": 10,
                                               "link": "https://meet.exemplo.invalid/turma-demo"})["id"]
    api.admin_turma_criar(cab=adm, corpo={"item": "ths-tech", "nome": "Turma de março · quintas 20h", "inicio": em(30), "fim": em(86),
                                          "encontros": "8 encontros semanais de 90 min", "local": "Online", "vagas": 12})
    api.admin_turma_criar(cab=adm, corpo={"item": "grupo-tdah", "nome": "Grupo mensal · sábados 10h", "inicio": em(10),
                                          "encontros": "4 encontros por mês", "local": "Online", "vagas": 8})
    bia = conta("bia@demo.agora", "Beatriz Lima", "paciente")
    r = api.turma_inscrever(cab=bia, ids=[t1])
    api.simulado_confirmar(corpo={"checkout": r["checkout"], "resultado": "pix"})
    r = api.produto_comprar(cab=bia, corpo={"produto": "item:ebooks:tdah-no-trabalho"})
    api.simulado_confirmar(corpo={"checkout": r["checkout"], "resultado": "aprovado"})
    missoes = api.minhas(cab=bia)["turmas"][0]["missoes"]
    for m in missoes[:2]:
        api.missao_feita(cab=bia, ids=[m["id"]], corpo={"nota": "consegui praticar uma vez"})
    for i, (item, nome, email, msg, origem) in enumerate([
        ("terapia", "Carlos Mendes (exemplo)", "carlos@exemplo.invalid", "Procuro terapia online, de preferência à noite.", "site-servicos"),
        ("ths-tech", "Júlia Prado (exemplo)", "julia@exemplo.invalid", "Sou dev e travo em reuniões. A próxima turma é quando?", "app"),
        ("palestra", "RH Exemplo Ltda.", "rh@exemplo.invalid", "Palestra sobre burnout para 80 pessoas em abril.", "site-servicos"),
    ]):
        api.interesse(corpo={"item": item, "nome": nome, "email": email, "mensagem": msg, "aceite": True, "origem": origem}, cab={}, ip=f"10.0.0.{i}")
    con = api.db.con()
    rnd = random.Random(5)
    for n, nome in ((420, "site_visita"), (130, "site_comecar"), (95, "site_servicos"), (160, "ver_servicos"), (70, "abrir_item"),
                    (31, "clicar_interesse"), (14, "enviar_interesse"), (22, "clicar_comprar"), (40, "ver_turmas"), (85, "instalar_app")):
        for _ in range(n):
            quando = (datetime.now(timezone.utc) - timedelta(days=rnd.random() * 29)).isoformat(timespec="seconds")
            con.execute("INSERT INTO eventos_funil(quando,nome,origem,plataforma) VALUES (?,?,?,?)", (quando, nome, "demo", "web"))
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
