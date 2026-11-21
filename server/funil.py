"""Funil de serviços, turmas, compras avulsas, e-mails de relacionamento, Web Push e administração.

Mixin da classe API (server.py). Fica separado para o servidor principal continuar legível.
Privacidade por padrão:
  - eventos do funil são anônimos e agregados (sem id de usuário, sem dado clínico);
  - nada no funil é disparado por dado clínico (humor, triagem, diário);
  - mensagens de interesse são cifradas no banco e apagadas após AGORA_RETENCAO_MESES.
"""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import catalogo as cat
import email_envio
import pagamentos as pag
import push

EVENTOS_FUNIL = {"site_visita", "site_comecar", "site_servicos", "ver_servicos", "abrir_item", "clicar_interesse",
                 "enviar_interesse", "clicar_comprar", "ver_turmas", "abrir_minhas", "instalar_app"}
STATUS_INTERESSE = ("novo", "contatado", "agendado", "convertido", "sem_resposta", "descartado")
SEQUENCIA_DIAS = (1, 4, 10)


def agora_dt():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or agora_dt()).isoformat(timespec="seconds")


def _txt(v, n):
    return str(v or "").strip()[:n]


def fuso_horario(nome):
    """zoneinfo quando houver base de fusos; senão, fuso fixo (o Brasil não tem horário de verão desde 2019)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nome or "America/Sao_Paulo")
    except Exception:
        fixos = {"America/Sao_Paulo": -3, "America/Manaus": -4, "America/Rio_Branco": -5, "America/Noronha": -2,
                 "America/Belem": -3, "America/Fortaleza": -3, "America/Recife": -3, "America/Cuiaba": -4}
        return timezone(timedelta(hours=fixos.get(nome or "", -3)))


class Funil:
    # ------------------------------------------------------------ rotas deste módulo
    ROTAS_FUNIL = {
        ("GET", "catalogo"): "catalogo_publico",
        ("POST", "interesse"): "interesse",
        ("POST", "eventos"): "evento_funil",
        ("GET", "turmas"): "turmas_lista",
        ("POST", "turmas/:id/inscrever"): "turma_inscrever",
        ("POST", "turmas/:id/sair"): "turma_sair",
        ("GET", "minhas"): "minhas",
        ("POST", "missoes/:id/feita"): "missao_feita",
        ("POST", "produtos/comprar"): "produto_comprar",
        ("GET", "ebook/link"): "ebook_link",
        ("GET", "ebook/baixar"): "ebook_baixar",
        ("GET", "descadastrar"): "descadastrar_pagina",
        ("POST", "descadastrar"): "descadastrar",
        ("POST", "conta/marketing"): "conta_marketing",
        ("GET", "push/chave"): "push_chave",
        ("POST", "push/inscrever"): "push_inscrever",
        ("POST", "push/cancelar"): "push_cancelar",
        ("POST", "push/pendentes"): "push_pendentes",
        ("GET", "push/lembretes"): "push_lembretes_ler",
        ("POST", "push/lembretes"): "push_lembretes_gravar",
        ("GET", "admin/resumo"): "admin_resumo",
        ("GET", "admin/interesses"): "admin_interesses",
        ("POST", "admin/interesses/:id/status"): "admin_interesse_status",
        ("GET", "admin/turmas"): "admin_turmas",
        ("POST", "admin/turmas"): "admin_turma_criar",
        ("POST", "admin/turmas/:id"): "admin_turma_editar",
        ("GET", "admin/turmas/:id/inscritos"): "admin_inscritos",
        ("POST", "admin/turmas/:id/avisar"): "admin_turma_avisar",
        ("GET", "admin/compras"): "admin_compras",
        ("POST", "admin/compras/:id/estornar"): "admin_estornar",
        ("GET", "admin/catalogo"): "admin_catalogo",
        ("POST", "admin/catalogo"): "admin_catalogo_ajustar",
        ("GET", "admin/erros"): "admin_erros",
    }

    # ------------------------------------------------------------ utilidades
    def segredo_links(self):
        return self.cofre.derivar(b"links-assinados")

    def assina_link(self, *partes, validade=None):
        exp = str(int(time.time() + validade)) if validade else "0"
        msg = "|".join([*map(str, partes), exp]).encode()
        return exp + "." + hmac.new(self.segredo_links(), msg, hashlib.sha256).hexdigest()[:32]

    def confere_link(self, token, *partes):
        try:
            exp, ass = str(token).split(".", 1)
            if exp != "0" and int(exp) < time.time():
                return False
        except ValueError:
            return False
        msg = "|".join([*map(str, partes), exp]).encode()
        return hmac.compare_digest(hmac.new(self.segredo_links(), msg, hashlib.sha256).hexdigest()[:32], ass)

    def link_descadastro(self, email):
        from urllib.parse import quote
        return f"{self.cfg.url_publica}/api/descadastrar?e={quote(email)}&t={self.assina_link('desc', email)}"

    def rodape_email(self, email=None):
        r = self.catalogo.responsavel()
        txt = f"\n--\nResponsável técnico: {r['nome']}, psicólogo, {r['crp']}.\nContato: {r['contato']}\n"
        if email:
            txt += f"Não quer mais receber estes e-mails? {self.link_descadastro(email)}\n"
        return txt

    def _plataforma(self, cab, query=None):
        p = (cab.get("X-Agora-Plataforma") or (query or {}).get("plataforma") or "web").lower()
        return "android" if p == "android" else "web"

    def _vinculado(self, con, uid):
        return bool(uid and con.execute("SELECT 1 FROM vinculos WHERE paciente_id=? AND ativo=1", (uid,)).fetchone())

    def exige_admin(self, cab):
        u = self.usuario(cab)
        if not u.get("admin"):
            self.erro(403, "Área só para administradores.")
        if self.cfg.exigir_2fa_admin and not u.get("totp_segredo"):
            self.erro(403, "Ative a verificação em duas etapas para usar a administração.", {"precisa2faAtivar": True})
        return u

    # ------------------------------------------------------------ catálogo
    def catalogo_publico(self, cab, query, **_):
        u = self.usuario_opcional(cab)
        con = self.db.con()
        try:
            vinc = u and u["papel"] == "paciente" and self._vinculado(con, u["id"])
        finally:
            con.close()
        linhas = ["pessoas"] if query.get("contexto") == "app" else None  # app do paciente: só a linha "Para você"
        out = self.catalogo.publico(self._plataforma(cab, query), bool(vinc), linhas)
        out["vinculado"] = bool(vinc)
        if vinc:
            out["aviso"] = "Você já é acompanhado por um profissional no Agora. Converse com ele sobre outros serviços."
        return out

    def interesse(self, corpo, cab, ip="?", **_):
        if self.lim.excedeu(f"interesse:{ip}", 8, 3600):
            self.erro(429, "Recebemos vários pedidos daqui. Tente de novo mais tarde.")
        self.lim.marcar(f"interesse:{ip}")
        if _txt(corpo.get("site"), 200):  # armadilha para robôs: campo escondido
            return {"ok": True}
        it = self.catalogo.item(corpo.get("item"))
        if not it:
            self.erro(400, "Escolha um serviço da lista.")
        u = self.usuario_opcional(cab)
        nome = _txt(corpo.get("nome") or (u and u["nome"]), 80)
        email = _txt(corpo.get("email") or (u and u["email"]), 120).lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            self.erro(400, "Digite um e-mail válido para a resposta.")
        if not nome:
            self.erro(400, "Digite seu nome.")
        if not corpo.get("aceite"):
            self.erro(400, "Para responder, precisamos que você aceite o uso destes dados para este contato.")
        mkt = 1 if corpo.get("marketing") else 0
        con = self.db.con()
        try:
            agora_s = iso()
            cur = con.execute("INSERT INTO interesses(item_id,nome,email,contato,mensagem,origem,usuario_id,marketing,criado_em,atualizado_em) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (it["id"], nome, email, _txt(corpo.get("contato"), 60),
                               self.cofre.cifrar(_txt(corpo.get("mensagem"), 1000), "interesse"),
                               _txt(corpo.get("origem"), 40), u["id"] if u else None, mkt, agora_s, agora_s))
            con.execute("INSERT INTO eventos_funil(quando,nome,item_id,origem,plataforma) VALUES (?,?,?,?,?)",
                        (agora_s, "enviar_interesse", it["id"], _txt(corpo.get("origem"), 40), self._plataforma(cab)))
            if mkt:
                con.execute("INSERT INTO sequencias(email,nome,item_id,etapa,proximo_em,descadastrado,criado_em) VALUES (?,?,?,0,?,0,?) "
                            "ON CONFLICT(email) DO UPDATE SET descadastrado=0, item_id=excluded.item_id",
                            (email, nome, it["id"], iso(agora_dt() + timedelta(days=SEQUENCIA_DIAS[0])), agora_s))
                if u:
                    con.execute("UPDATE usuarios SET marketing=1 WHERE id=?", (u["id"],))
            r = self.catalogo.responsavel()
            email_envio.enviar(self.cfg, con, email, f"Recebemos seu contato: {it['nome']}",
                               f"Olá, {nome.split(' ')[0]}.\n\nRecebemos seu interesse em {it['nome']}. "
                               f"Vamos responder por este e-mail em até 2 dias úteis.\n\n"
                               "Se estiver em sofrimento intenso ou pensando em se machucar, não espere: ligue 188 (CVV, 24 horas, gratuito) "
                               "ou procure o pronto atendimento mais perto. Em emergência, SAMU 192.\n" + self.rodape_email())
            email_envio.enviar(self.cfg, con, self.cfg.alerta_email or r["contato"], f"[Agora] Novo interesse: {it['nome']}",
                               f"Item: {it['nome']} ({it['id']})\nNome: {nome}\nE-mail: {email}\nOrigem: {_txt(corpo.get('origem'), 40)}\n"
                               f"Veja a mensagem no painel de administração (/app/admin.html). Registro #{cur.lastrowid}.\n")
            con.commit()
        finally:
            con.close()
        return {"ok": True, "mensagem": "Recebemos. A resposta chega no seu e-mail em até 2 dias úteis."}

    def evento_funil(self, corpo, cab, ip="?", **_):
        nome = _txt(corpo.get("nome"), 30)
        if nome not in EVENTOS_FUNIL:
            return {"ok": False}
        if self.lim.excedeu(f"ev:{ip}", 120, 3600):
            return {"ok": False}
        self.lim.marcar(f"ev:{ip}")
        item = _txt(corpo.get("item"), 40)
        con = self.db.con()
        con.execute("INSERT INTO eventos_funil(quando,nome,item_id,origem,plataforma) VALUES (?,?,?,?,?)",
                    (iso(), nome, item if self.catalogo.item(item) else None, _txt(corpo.get("origem"), 40), self._plataforma(cab)))
        con.commit()
        con.close()
        return {"ok": True}

    # ------------------------------------------------------------ turmas
    def _turma_json(self, con, t, uid=None):
        conf = con.execute("SELECT COUNT(*) n FROM inscricoes WHERE turma_id=? AND status IN ('confirmada','pendente')", (t["id"],)).fetchone()["n"]
        it = self.catalogo.item(t["item_id"]) or {}
        preco = t["preco"] if t["preco"] is not None else (it.get("venda") or {}).get("valor")
        out = {"id": t["id"], "item": t["item_id"], "itemNome": it.get("nome", t["item_id"]), "nome": t["nome"], "inicio": t["inicio"],
               "fim": t["fim"], "encontros": t["encontros"], "local": t["local"], "vagas": t["vagas"],
               "restam": max(0, t["vagas"] - conf), "preco": preco, "responsavel": self.catalogo.responsavel()}
        if uid:
            i = con.execute("SELECT status FROM inscricoes WHERE turma_id=? AND usuario_id=? AND status!='cancelada' ORDER BY id DESC",
                            (t["id"], uid)).fetchone()
            out["minha"] = i["status"] if i else None
            if i and i["status"] == "confirmada":
                out["link"] = t["link"]
        return out

    def turmas_lista(self, cab, query, **_):
        u = self.usuario_opcional(cab)
        con = self.db.con()
        try:
            sql, args = "SELECT * FROM turmas WHERE ativo=1 AND (inicio IS NULL OR inicio>=date('now','-7 day'))", []
            if query.get("item"):
                sql += " AND item_id=?"
                args.append(query["item"])
            return {"turmas": [self._turma_json(con, t, u and u["id"]) for t in con.execute(sql + " ORDER BY inicio", args).fetchall()]}
        finally:
            con.close()

    def turma_inscrever(self, cab, ids, **_):
        u = self.usuario(cab)
        if self._plataforma(cab) == "android":
            self.erro(403, "Inscrições em turmas são feitas pelo site.", {"abrirNoSite": True})
        con = self.db.con()
        try:
            t = con.execute("SELECT * FROM turmas WHERE id=? AND ativo=1", (ids[0],)).fetchone()
            if not t:
                self.erro(404, "Turma não encontrada.")
            if u["papel"] == "paciente" and self._vinculado(con, u["id"]):
                it = self.catalogo.item(t["item_id"]) or {}
                if it.get("psicologico"):
                    self.erro(403, "Você já é acompanhado por um profissional no Agora. Converse com ele antes de entrar num grupo.")
            atual = con.execute("SELECT * FROM inscricoes WHERE turma_id=? AND usuario_id=? AND status IN ('confirmada','espera')",
                                (t["id"], u["id"])).fetchone()
            if atual:
                return {"ok": True, "status": atual["status"]}
            info = self._turma_json(con, t)
            agora_s = iso()
            if info["restam"] <= 0:
                con.execute("INSERT INTO inscricoes(turma_id,usuario_id,status,criado_em,atualizado_em) VALUES (?,?, 'espera', ?, ?)",
                            (t["id"], u["id"], agora_s, agora_s))
                con.commit()
                return {"ok": True, "status": "espera", "mensagem": "Turma cheia. Você entrou na lista de espera e avisamos se abrir vaga."}
            if not info["preco"]:
                con.execute("INSERT INTO inscricoes(turma_id,usuario_id,status,criado_em,atualizado_em) VALUES (?,?, 'confirmada', ?, ?)",
                            (t["id"], u["id"], agora_s, agora_s))
                con.commit()
                return {"ok": True, "status": "confirmada"}
            con.execute("UPDATE inscricoes SET status='cancelada', atualizado_em=? WHERE turma_id=? AND usuario_id=? AND status='pendente'",
                        (agora_s, t["id"], u["id"]))
            prov = self.prov()
            try:
                r = pag.novo_checkout(con, self.cfg, u, f"item:{t['item_id']}", prov, valor=info["preco"],
                                      meta={"turma": t["id"]}, nome=f"{info['itemNome']}: {t['nome']}")
            except pag.ErroPag as e:
                self.erro(e.status, e.msg)
            con.execute("INSERT INTO inscricoes(turma_id,usuario_id,status,checkout_id,criado_em,atualizado_em) VALUES (?,?,'pendente',?,?,?)",
                        (t["id"], u["id"], r["checkout"], agora_s, agora_s))
            self.audita(con, u["id"], "inscricao", t["id"])
            con.commit()
            return {"ok": True, "status": "pendente", **r}
        finally:
            con.close()

    def turma_sair(self, cab, ids, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            n = con.execute("UPDATE inscricoes SET status='cancelada', atualizado_em=? WHERE turma_id=? AND usuario_id=? AND status IN ('espera','pendente')",
                            (iso(), ids[0], u["id"])).rowcount
            con.commit()
            if not n:
                self.erro(400, "Para desistir de uma vaga já paga, fale com a equipe: a devolução segue os Termos de uso.")
            return {"ok": True}
        finally:
            con.close()

    def minhas(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            turmas = []
            for i in con.execute("SELECT DISTINCT turma_id FROM inscricoes WHERE usuario_id=? AND status!='cancelada'", (u["id"],)).fetchall():
                t = con.execute("SELECT * FROM turmas WHERE id=?", (i["turma_id"],)).fetchone()
                if not t:
                    continue
                tj = self._turma_json(con, t, u["id"])
                if tj["minha"] == "confirmada":
                    tj["missoes"] = [{"id": m["id"], "semana": m["semana"], "titulo": m["titulo"], "texto": m["texto"],
                                      "feita": bool(m["quando"])} for m in con.execute(
                        "SELECT m.*, f.quando FROM missoes m LEFT JOIN missoes_feitas f ON f.missao_id=m.id AND f.usuario_id=? "
                        "WHERE m.turma_id=? ORDER BY m.semana", (u["id"], t["id"]))]
                turmas.append(tj)
            compras = []
            pls = pag.planos(self.cfg)
            for c in con.execute("SELECT * FROM compras WHERE usuario_id=? ORDER BY id DESC", (u["id"],)).fetchall():
                pid = "item:" + c["item_id"]
                compras.append({"id": c["id"], "item": c["item_id"], "nome": pls.get(pid, {}).get("nome", c["item_id"]),
                                "entrega": c["entrega"], "status": c["status"], "valor": c["valor"], "criadoEm": c["criado_em"]})
            return {"turmas": turmas, "compras": compras}
        finally:
            con.close()

    def missao_feita(self, corpo, cab, ids, **_):
        u = self.usuario(cab)
        con = self.db.con()
        try:
            m = con.execute("SELECT m.* FROM missoes m JOIN inscricoes i ON i.turma_id=m.turma_id AND i.usuario_id=? AND i.status='confirmada' "
                            "WHERE m.id=?", (u["id"], ids[0])).fetchone()
            if not m:
                self.erro(404, "Missão não encontrada nas suas turmas.")
            if corpo.get("desfazer"):
                con.execute("DELETE FROM missoes_feitas WHERE missao_id=? AND usuario_id=?", (m["id"], u["id"]))
            else:
                nota = _txt(corpo.get("nota"), 600)
                con.execute("INSERT OR REPLACE INTO missoes_feitas VALUES (?,?,?,?)",
                            (m["id"], u["id"], iso(), self.cofre.cifrar(nota, "missao") if nota else None))
            con.commit()
            return {"ok": True}
        finally:
            con.close()

    # ------------------------------------------------------------ produtos avulsos
    def produto_comprar(self, corpo, cab, **_):
        u = self.usuario(cab)
        pid = _txt(corpo.get("produto"), 80)
        pl = pag.planos(self.cfg).get(pid)
        if not pl or pl.get("tipo") != "avulso":
            self.erro(400, "Produto inexistente.")
        if pl["entrega"] == "turma":
            self.erro(400, "Para turmas, escolha a data em Turmas abertas.")
        if self._plataforma(cab) == "android" and not pl.get("android"):
            self.erro(403, "Este produto é vendido só pelo site.", {"abrirNoSite": True})
        it = self.catalogo.item(pl["item"]) or {}
        con = self.db.con()
        try:
            if it.get("psicologico") and u["papel"] == "paciente" and self._vinculado(con, u["id"]):
                self.erro(403, "Você já é acompanhado por um profissional no Agora. Converse com ele sobre este serviço.")
            if pl["entrega"] == "ebook" and con.execute("SELECT 1 FROM compras WHERE usuario_id=? AND item_id=? AND status='paga'",
                                                        (u["id"], pid[5:])).fetchone():
                self.erro(409, "Você já tem este e-book. Ele está em Minhas compras.")
            prov = self.prov()
            try:
                r = pag.novo_checkout(con, self.cfg, u, pid, prov)
            except pag.ErroPag as e:
                self.erro(e.status, e.msg)
            self.audita(con, u["id"], "checkout", f"{pid}:{prov.nome}")
            con.commit()
            return r
        finally:
            con.close()

    def _arquivo_ebook(self, item):
        nome = item.split(":")[-1]
        if not nome.replace("-", "").isalnum():
            return None
        arq = Path(self.cfg.ebooks_dir) / f"{nome}.pdf"
        return arq if arq.is_file() else None

    def ebook_link(self, cab, query, **_):
        u = self.usuario(cab)
        item = _txt(query.get("item"), 80)
        con = self.db.con()
        try:
            ok = con.execute("SELECT 1 FROM compras WHERE usuario_id=? AND item_id=? AND status='paga'", (u["id"], item)).fetchone()
        finally:
            con.close()
        if not ok:
            self.erro(404, "Compra não encontrada.")
        if not self._arquivo_ebook(item):
            self.erro(503, "O arquivo ainda não foi publicado. Avisamos por e-mail assim que estiver pronto.")
        from urllib.parse import quote
        return {"url": f"/api/ebook/baixar?i={quote(item)}&u={u['id']}&t={self.assina_link('ebook', item, u['id'], validade=600)}"}

    def ebook_baixar(self, query, **_):
        item, uid = _txt(query.get("i"), 80), _txt(query.get("u"), 12)
        if not self.confere_link(query.get("t", ""), "ebook", item, uid):
            self.erro(403, "Link vencido. Abra Minhas compras e toque em Baixar de novo.")
        arq = self._arquivo_ebook(item)
        if not arq:
            self.erro(404, "Arquivo não encontrado.")
        return {"_arquivo": str(arq), "_nome": arq.name, "_tipo": "application/pdf"}

    # ------------------------------------------------------------ e-mails de relacionamento
    def descadastrar_pagina(self, query, **_):
        email = _txt(query.get("e"), 120).lower()
        ok = self.confere_link(query.get("t", ""), "desc", email)
        if ok:
            self._descadastra(email)
        msg = "Pronto: você não recebe mais e-mails de conteúdo." if ok else "Link inválido. Responda qualquer e-mail nosso pedindo o descadastro."
        return {"_html": f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Descadastro</title>"
                         f"<body style='font:16px system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem'><h1>Descadastro</h1><p>{msg}</p>"
                         f"<p><a href='/'>Voltar ao site</a></p>"}

    def descadastrar(self, query, corpo, **_):  # One-Click (RFC 8058): o provedor de e-mail faz POST
        email = _txt(query.get("e") or corpo.get("e"), 120).lower()
        if not self.confere_link(query.get("t") or corpo.get("t", ""), "desc", email):
            self.erro(403, "Link inválido.")
        self._descadastra(email)
        return {"ok": True}

    def _descadastra(self, email):
        con = self.db.con()
        con.execute("UPDATE sequencias SET descadastrado=1 WHERE email=?", (email,))
        con.execute("UPDATE interesses SET marketing=0 WHERE email=?", (email,))
        con.execute("UPDATE usuarios SET marketing=0 WHERE email=?", (email,))
        con.commit()
        con.close()

    def conta_marketing(self, corpo, cab, **_):
        u = self.usuario(cab)
        sim = 1 if corpo.get("aceito") else 0
        con = self.db.con()
        con.execute("UPDATE usuarios SET marketing=? WHERE id=?", (sim, u["id"]))
        if sim:
            con.execute("INSERT INTO sequencias(email,nome,item_id,etapa,proximo_em,descadastrado,criado_em) VALUES (?,?,NULL,0,?,0,?) "
                        "ON CONFLICT(email) DO UPDATE SET descadastrado=0", (u["email"], u["nome"], iso(agora_dt() + timedelta(days=1)), iso()))
        else:
            con.execute("UPDATE sequencias SET descadastrado=1 WHERE email=?", (u["email"],))
        self.audita(con, u["id"], "marketing", sim)
        con.commit()
        con.close()
        return {"ok": True, "marketing": bool(sim)}

    TEXTOS_SEQUENCIA = (
        ("Três ajustes pequenos para a semana",
         "Organizar a semana com TDAH costuma dar mais certo com passos curtos do que com planos perfeitos:\n\n"
         "1. Escolha uma única prioridade por dia e escreva onde você vai vê-la.\n2. Divida a tarefa mais pesada até o primeiro passo caber em 5 minutos.\n"
         "3. Marque um horário fixo para revisar a lista, mesmo que seja só 2 minutos.\n\nO app Agora faz isso com você: {app}\n"),
        ("Quando a semana sai do trilho",
         "Dias ruins fazem parte. Uma rotina que só funciona em dia bom é frágil. Experimente ter uma versão mínima de cada rotina, "
         "a que você consegue fazer cansado. No Agora, crie uma rotina curta chamada 'dia ruim' com 2 ou 3 passos.\n"),
        ("Quando vale procurar acompanhamento",
         "Ferramentas ajudam, mas não substituem cuidado profissional. Se o cansaço, a desorganização ou a ansiedade estão atrapalhando "
         "trabalho, estudos ou relações há semanas, vale conversar com um psicólogo. Se quiser, veja os serviços em {servicos}.\n"
         "Em sofrimento intenso, ligue 188 (CVV, 24 horas).\n"),
    )

    def enviar_sequencias(self, limite=200):
        con = self.db.con()
        enviados = 0
        try:
            agora_s = iso()
            for s in con.execute("SELECT * FROM sequencias WHERE descadastrado=0 AND etapa<? AND proximo_em<=? LIMIT ?",
                                 (len(SEQUENCIA_DIAS), agora_s, limite)).fetchall():
                assunto, texto = self.TEXTOS_SEQUENCIA[s["etapa"]]
                corpo = f"Olá, {(s['nome'] or '').split(' ')[0] or 'tudo bem'}.\n\n" + texto.format(
                    app=f"{self.cfg.url_publica}/app/", servicos=f"{self.cfg.url_publica}/servicos") + self.rodape_email(s["email"])
                email_envio.enviar(self.cfg, con, s["email"], assunto, corpo, descadastro=self.link_descadastro(s["email"]))
                prox_etapa = s["etapa"] + 1
                prox = (iso(datetime.fromisoformat(s["criado_em"]) + timedelta(days=SEQUENCIA_DIAS[prox_etapa]))
                        if prox_etapa < len(SEQUENCIA_DIAS) else None)
                con.execute("UPDATE sequencias SET etapa=?, proximo_em=? WHERE email=?", (prox_etapa, prox, s["email"]))
                con.commit()
                enviados += 1
        finally:
            con.close()
        return enviados

    # ------------------------------------------------------------ retenção
    def aplicar_retencao(self):
        con = self.db.con()
        try:
            corte = iso(agora_dt() - timedelta(days=30 * self.cfg.retencao_meses))
            r = {
                "interesses": con.execute("DELETE FROM interesses WHERE atualizado_em<? AND status NOT IN ('convertido')", (corte,)).rowcount,
                "eventos": con.execute("DELETE FROM eventos_funil WHERE quando<?", (iso(agora_dt() - timedelta(days=400)),)).rowcount,
                "caixa_saida": con.execute("DELETE FROM caixa_saida WHERE criado_em<datetime('now','-30 day')").rowcount,
                "tokens": con.execute("DELETE FROM tokens WHERE expira<?", (int(time.time()),)).rowcount,
                "resets": con.execute("DELETE FROM resets_senha WHERE expira<?", (int(time.time()) - 86400,)).rowcount,
                "limites": con.execute("DELETE FROM limites WHERE t<?", (time.time() - 86400,)).rowcount,
                "push": con.execute("DELETE FROM push_pendentes WHERE criado_em<?", (iso(agora_dt() - timedelta(days=7)),)).rowcount,
                "erros": con.execute("DELETE FROM erros WHERE quando<?", (iso(agora_dt() - timedelta(days=90)),)).rowcount,
                "checkouts": con.execute("DELETE FROM checkouts WHERE status='aberto' AND criado_em<?", (iso(agora_dt() - timedelta(days=30)),)).rowcount,
                "sequencias": con.execute("DELETE FROM sequencias WHERE (descadastrado=1 OR etapa>=?) AND criado_em<?",
                                          (len(SEQUENCIA_DIAS), corte)).rowcount,
            }
            # auditoria fica 5 anos (guarda de registros do serviço psicológico)
            r["auditoria"] = con.execute("DELETE FROM auditoria WHERE quando<?", (iso(agora_dt() - timedelta(days=5 * 366)),)).rowcount
            con.commit()
            return r
        finally:
            con.close()

    # ------------------------------------------------------------ Web Push
    def push_chave(self, **_):
        return {"chave": self.cfg.vapid_publica if push.configurado(self.cfg) else None}

    def push_inscrever(self, corpo, cab, **_):
        u = self.usuario(cab)
        sub = corpo.get("inscricao") or {}
        endpoint = _txt(sub.get("endpoint"), 600)
        chaves = sub.get("keys") or {}
        if not endpoint.startswith("https://") or not chaves.get("auth"):
            self.erro(400, "Inscrição de notificação inválida.")
        con = self.db.con()
        con.execute("INSERT INTO push_inscricoes(usuario_id,endpoint,p256dh,auth,criado_em) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(endpoint) DO UPDATE SET usuario_id=excluded.usuario_id, auth=excluded.auth, p256dh=excluded.p256dh, falhas=0",
                    (u["id"], endpoint, _txt(chaves.get("p256dh"), 200), _txt(chaves.get("auth"), 100), iso()))
        con.commit()
        con.close()
        return {"ok": True}

    def push_cancelar(self, corpo, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        con.execute("DELETE FROM push_inscricoes WHERE usuario_id=? AND endpoint=?", (u["id"], _txt(corpo.get("endpoint"), 600)))
        con.commit()
        con.close()
        return {"ok": True}

    def push_pendentes(self, corpo, **_):
        """Chamado pelo service worker: prova a posse da inscrição com o segredo `auth`."""
        con = self.db.con()
        try:
            s = con.execute("SELECT * FROM push_inscricoes WHERE endpoint=?", (_txt(corpo.get("endpoint"), 600),)).fetchone()
            if not s or not hmac.compare_digest(str(s["auth"] or ""), _txt(corpo.get("auth"), 100)):
                self.erro(403, "Inscrição desconhecida.")
            rows = con.execute("SELECT id,titulo,corpo,url FROM push_pendentes WHERE usuario_id=? AND entregue=0 ORDER BY id LIMIT 5",
                               (s["usuario_id"],)).fetchall()
            con.executemany("UPDATE push_pendentes SET entregue=1 WHERE id=?", [(r["id"],) for r in rows])
            con.commit()
            return {"mensagens": [{"titulo": r["titulo"], "corpo": r["corpo"], "url": r["url"]} for r in rows]}
        finally:
            con.close()

    def notificar(self, con, uid, titulo, corpo, url="/app/"):
        """Enfileira a mensagem e toca as inscrições do usuário."""
        con.execute("INSERT INTO push_pendentes(usuario_id,titulo,corpo,url,criado_em) VALUES (?,?,?,?,?)", (uid, titulo, corpo, url, iso()))
        res = []
        for s in con.execute("SELECT * FROM push_inscricoes WHERE usuario_id=?", (uid,)).fetchall():
            r = push.tocar(self.cfg, self.http_push, s["endpoint"])
            if r == "expirada" or (r == "falha" and s["falhas"] >= 5):
                con.execute("DELETE FROM push_inscricoes WHERE id=?", (s["id"],))
            elif r == "falha":
                con.execute("UPDATE push_inscricoes SET falhas=falhas+1 WHERE id=?", (s["id"],))
            res.append(r)
        return res

    def push_lembretes_ler(self, cab, **_):
        u = self.usuario(cab)
        con = self.db.con()
        r = con.execute("SELECT dados,fuso FROM lembretes_push WHERE usuario_id=?", (u["id"],)).fetchone()
        n = con.execute("SELECT COUNT(*) n FROM push_inscricoes WHERE usuario_id=?", (u["id"],)).fetchone()["n"]
        con.close()
        return {"lembretes": json.loads(r["dados"]) if r else [], "fuso": r["fuso"] if r else "America/Sao_Paulo", "aparelhos": n}

    def push_lembretes_gravar(self, corpo, cab, **_):
        u = self.usuario(cab)
        lista = []
        for l in (corpo.get("lembretes") or [])[:12]:
            hora = _txt(l.get("hora"), 5)
            if len(hora) != 5 or hora[2] != ":" or not (hora[:2] + hora[3:]).isdigit() or int(hora[:2]) > 23 or int(hora[3:]) > 59:
                continue
            dias = [int(d) for d in (l.get("dias") or range(7)) if str(d).isdigit() and 0 <= int(d) <= 6]
            lista.append({"hora": hora, "texto": _txt(l.get("texto"), 80) or "Hora de olhar o Agora", "dias": sorted(set(dias)),
                          "url": "/app/" + _txt(l.get("aba"), 20).strip("/") if l.get("aba") else "/app/"})
        fuso = _txt(corpo.get("fuso"), 40) or "America/Sao_Paulo"
        con = self.db.con()
        con.execute("INSERT OR REPLACE INTO lembretes_push(usuario_id,dados,fuso,ultimo_envio) VALUES (?,?,?,COALESCE((SELECT ultimo_envio FROM lembretes_push WHERE usuario_id=?),''))",
                    (u["id"], json.dumps(lista, ensure_ascii=False), fuso, u["id"]))
        con.commit()
        con.close()
        return {"ok": True, "lembretes": lista}

    def disparar_lembretes(self, quando=None):
        """Roda a cada minuto pelo agendador. Envia os lembretes cujo horário local chegou."""
        quando = quando or agora_dt()
        con = self.db.con()
        n = 0
        try:
            for r in con.execute("SELECT * FROM lembretes_push").fetchall():
                local = quando.astimezone(fuso_horario(r["fuso"]))
                chave = local.strftime("%Y-%m-%d %H:%M")
                if r["ultimo_envio"] == chave:
                    continue
                for l in json.loads(r["dados"]):
                    if l["hora"] == local.strftime("%H:%M") and (local.weekday() + 1) % 7 in l["dias"]:
                        self.notificar(con, r["usuario_id"], "Agora", l["texto"], l.get("url") or "/app/")
                        con.execute("UPDATE lembretes_push SET ultimo_envio=? WHERE usuario_id=?", (chave, r["usuario_id"]))
                        n += 1
            con.commit()
        finally:
            con.close()
        return n

    # ------------------------------------------------------------ administração
    def admin_resumo(self, cab, **_):
        self.exige_admin(cab)
        con = self.db.con()
        try:
            d30 = iso(agora_dt() - timedelta(days=30))
            agora_s = iso()
            q = lambda sql, *a: [dict(r) for r in con.execute(sql, a).fetchall()]  # noqa: E731
            funil = {r["nome"]: r["n"] for r in q("SELECT nome, COUNT(*) n FROM eventos_funil WHERE quando>=? GROUP BY nome", d30)}
            receita = q("SELECT plano, COUNT(*) n, COALESCE(SUM(valor),0) total FROM pagamentos WHERE status='aprovado' AND criado_em>=? GROUP BY plano", d30)
            estornos = con.execute("SELECT COALESCE(SUM(valor),0) s FROM pagamentos WHERE status='estornado' AND criado_em>=?", (d30,)).fetchone()["s"]
            ck = {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM checkouts WHERE criado_em>=? GROUP BY status", d30)}
            mrr = 0
            pls = pag.planos(self.cfg)
            for a in q("SELECT plano, COUNT(*) n FROM assinaturas WHERE status='ativa' AND fim_periodo>? GROUP BY plano", agora_s):
                p = pls.get(a["plano"], {})
                mrr += a["n"] * (p.get("valor", 0) if p.get("tipo") == "recorrente" else round(p.get("valor", 0) / 12))
            for x in receita:
                x["nome"] = pls.get(x["plano"], {}).get("nome", x["plano"])
            ativas = q("SELECT plano, COUNT(*) n FROM assinaturas WHERE status='ativa' AND fim_periodo>? GROUP BY plano", agora_s)
            for x in ativas:
                x["nome"] = pls.get(x["plano"], {}).get("nome", x["plano"])
            return {
                "usuarios": {r["papel"]: r["n"] for r in q("SELECT papel, COUNT(*) n FROM usuarios GROUP BY papel")},
                "novos30": con.execute("SELECT COUNT(*) n FROM usuarios WHERE criado_em>=?", (d30,)).fetchone()["n"],
                "ativos7": con.execute("SELECT COUNT(*) n FROM usuarios WHERE ultimo_acesso>=?", (iso(agora_dt() - timedelta(days=7)),)).fetchone()["n"],
                "assinaturasAtivas": ativas,
                "receita30": receita, "receitaTotal30": sum(r["total"] for r in receita), "estornos30": estornos,
                "recorrenteMensal": mrr, "checkouts30": ck,
                "funil30": funil,
                "interesses": q("SELECT item_id, status, COUNT(*) n FROM interesses GROUP BY item_id, status"),
                "interessesNovos": con.execute("SELECT COUNT(*) n FROM interesses WHERE status='novo'").fetchone()["n"],
                "compras30": q("SELECT item_id, entrega, COUNT(*) n, COALESCE(SUM(valor),0) total FROM compras WHERE status='paga' AND criado_em>=? GROUP BY item_id", d30),
                "turmasAbertas": con.execute("SELECT COUNT(*) n FROM turmas WHERE ativo=1").fetchone()["n"],
                "erros7": con.execute("SELECT COUNT(*) n FROM erros WHERE quando>=?", (iso(agora_dt() - timedelta(days=7)),)).fetchone()["n"],
                "meta": 3000000,  # R$ 30 mil/mês em centavos
            }
        finally:
            con.close()

    def admin_interesses(self, cab, query, **_):
        self.exige_admin(cab)
        con = self.db.con()
        try:
            sql, args = "SELECT * FROM interesses", []
            if query.get("status"):
                sql += " WHERE status=?"
                args.append(query["status"])
            out = []
            for r in con.execute(sql + " ORDER BY id DESC LIMIT 300", args).fetchall():
                d = dict(r)
                d["mensagem"] = self.cofre.decifrar(d["mensagem"], "interesse")
                it = self.catalogo.item(d["item_id"]) or {}
                d["itemNome"] = it.get("nome", d["item_id"])
                out.append(d)
            return {"interesses": out, "status": STATUS_INTERESSE}
        finally:
            con.close()

    def admin_interesse_status(self, corpo, cab, ids, **_):
        a = self.exige_admin(cab)
        st = corpo.get("status")
        if st not in STATUS_INTERESSE:
            self.erro(400, "Status inválido.")
        con = self.db.con()
        con.execute("UPDATE interesses SET status=?, atualizado_em=? WHERE id=?", (st, iso(), ids[0]))
        self.audita(con, a["id"], "interesse_status", f"{ids[0]}:{st}")
        con.commit()
        con.close()
        return {"ok": True}

    def admin_turmas(self, cab, **_):
        self.exige_admin(cab)
        con = self.db.con()
        try:
            out = []
            for t in con.execute("SELECT * FROM turmas ORDER BY ativo DESC, inicio DESC").fetchall():
                j = self._turma_json(con, t)
                j.update(ativo=bool(t["ativo"]), link=t["link"],
                         espera=con.execute("SELECT COUNT(*) n FROM inscricoes WHERE turma_id=? AND status='espera'", (t["id"],)).fetchone()["n"])
                out.append(j)
            itens = [{"id": i["id"], "nome": i["nome"]} for i in self.catalogo.dados["itens"] if (i.get("venda") or {}).get("modo") == "turma"]
            return {"turmas": out, "itens": itens}
        finally:
            con.close()

    def _dados_turma(self, corpo, parcial=False):
        d = {}
        for k, n in (("nome", 80), ("inicio", 10), ("fim", 10), ("encontros", 200), ("local", 120), ("link", 300)):
            if k in corpo or not parcial:
                d[k] = _txt(corpo.get(k), n) or None
        for k in ("vagas", "preco"):
            if k in corpo and corpo[k] not in (None, ""):
                d[k] = max(0, int(corpo[k]))
        if "ativo" in corpo:
            d["ativo"] = 1 if corpo["ativo"] else 0
        if d.get("link") and not d["link"].startswith("https://"):
            self.erro(400, "O link da sala precisa começar com https://")
        return d

    def admin_turma_criar(self, corpo, cab, **_):
        a = self.exige_admin(cab)
        it = self.catalogo.item(corpo.get("item"))
        if not it or (it.get("venda") or {}).get("modo") != "turma":
            self.erro(400, "Escolha um programa em grupo do catálogo.")
        d = self._dados_turma(corpo)
        if not d.get("nome"):
            self.erro(400, "Dê um nome à turma (ex.: Turma de março, terças 19h).")
        con = self.db.con()
        try:
            cur = con.execute("INSERT INTO turmas(item_id,nome,inicio,fim,encontros,vagas,preco,local,link,ativo,criado_em) VALUES (?,?,?,?,?,?,?,?,?,1,?)",
                              (it["id"], d["nome"], d.get("inicio"), d.get("fim"), d.get("encontros"), d.get("vagas", 12),
                               d.get("preco"), d.get("local"), d.get("link"), iso()))
            tid = cur.lastrowid
            for semana, (titulo, texto) in enumerate(cat.MISSOES_THS.get(it["id"], []), start=1):
                con.execute("INSERT INTO missoes(turma_id,semana,titulo,texto) VALUES (?,?,?,?)", (tid, semana, titulo, texto))
            self.audita(con, a["id"], "turma_criada", tid)
            con.commit()
            return {"ok": True, "id": tid}
        finally:
            con.close()

    def admin_turma_editar(self, corpo, cab, ids, **_):
        a = self.exige_admin(cab)
        d = self._dados_turma(corpo, parcial=True)
        if not d:
            self.erro(400, "Nada para mudar.")
        con = self.db.con()
        try:
            antes = con.execute("SELECT * FROM turmas WHERE id=?", (ids[0],)).fetchone()
            if not antes:
                self.erro(404, "Turma não encontrada.")
            con.execute("UPDATE turmas SET " + ",".join(f"{k}=?" for k in d) + " WHERE id=?", (*d.values(), ids[0]))
            # vaga nova: chama o primeiro da lista de espera
            depois = con.execute("SELECT * FROM turmas WHERE id=?", (ids[0],)).fetchone()
            if self._turma_json(con, depois)["restam"] > 0:
                self._chamar_espera(con, depois)
            self.audita(con, a["id"], "turma_editada", ids[0])
            con.commit()
            return {"ok": True}
        finally:
            con.close()

    def _chamar_espera(self, con, t):
        e = con.execute("SELECT i.id, u.email, u.nome, u.id uid FROM inscricoes i JOIN usuarios u ON u.id=i.usuario_id "
                        "WHERE i.turma_id=? AND i.status='espera' ORDER BY i.id LIMIT 1", (t["id"],)).fetchone()
        if not e:
            return
        con.execute("UPDATE inscricoes SET status='cancelada', atualizado_em=? WHERE id=?", (iso(), e["id"]))
        email_envio.enviar(self.cfg, con, e["email"], f"Abriu vaga: {t['nome']}",
                           f"Olá, {e['nome'].split(' ')[0]}.\n\nAbriu uma vaga na turma {t['nome']}. Para garantir, abra o app em "
                           f"{self.cfg.url_publica}/app/#servicos e toque em Inscrever.\n" + self.rodape_email())
        self.notificar(con, e["uid"], "Abriu vaga", f"Turma {t['nome']}", "/app/#servicos")

    def admin_inscritos(self, cab, ids, **_):
        self.exige_admin(cab)
        con = self.db.con()
        try:
            rows = con.execute("SELECT i.id, i.status, i.criado_em, u.nome, u.email, u.contato, "
                               "(SELECT COUNT(*) FROM missoes_feitas f JOIN missoes m ON m.id=f.missao_id WHERE m.turma_id=i.turma_id AND f.usuario_id=u.id) missoes "
                               "FROM inscricoes i JOIN usuarios u ON u.id=i.usuario_id WHERE i.turma_id=? AND i.status!='cancelada' ORDER BY i.status, i.id",
                               (ids[0],)).fetchall()
            total = con.execute("SELECT COUNT(*) n FROM missoes WHERE turma_id=?", (ids[0],)).fetchone()["n"]
            return {"inscritos": [dict(r) for r in rows], "missoesTotal": total}
        finally:
            con.close()

    def admin_turma_avisar(self, corpo, cab, ids, **_):
        a = self.exige_admin(cab)
        texto = _txt(corpo.get("texto"), 1500)
        if not texto:
            self.erro(400, "Escreva o aviso.")
        con = self.db.con()
        try:
            t = con.execute("SELECT * FROM turmas WHERE id=?", (ids[0],)).fetchone()
            if not t:
                self.erro(404, "Turma não encontrada.")
            n = 0
            for u in con.execute("SELECT u.id, u.email, u.nome FROM inscricoes i JOIN usuarios u ON u.id=i.usuario_id "
                                 "WHERE i.turma_id=? AND i.status='confirmada'", (t["id"],)).fetchall():
                email_envio.enviar(self.cfg, con, u["email"], f"{t['nome']}: aviso da equipe", f"Olá, {u['nome'].split(' ')[0]}.\n\n{texto}\n" + self.rodape_email())
                self.notificar(con, u["id"], t["nome"], texto[:120], "/app/#minhas")
                n += 1
            self.audita(con, a["id"], "turma_aviso", t["id"])
            con.commit()
            return {"ok": True, "enviados": n}
        finally:
            con.close()

    def admin_compras(self, cab, **_):
        self.exige_admin(cab)
        con = self.db.con()
        try:
            rows = con.execute("SELECT c.*, u.nome, u.email FROM compras c LEFT JOIN usuarios u ON u.id=c.usuario_id ORDER BY c.id DESC LIMIT 300").fetchall()
            return {"compras": [dict(r) for r in rows]}
        finally:
            con.close()

    def admin_estornar(self, corpo, cab, ids, **_):
        a = self.exige_admin(cab)
        con = self.db.con()
        try:
            c = con.execute("SELECT * FROM compras WHERE id=?", (ids[0],)).fetchone()
            if not c or c["status"] != "paga":
                self.erro(400, "Compra não encontrada ou já estornada.")
            prov = self.prov(c["provedor"])
            try:
                prov.estornar(c["ref_pagamento"], c["valor"])
            except pag.ErroPag as e:
                self.erro(e.status, e.msg)
            ev = {"evento_id": f"admin-estorno:{c['id']}", "tipo": "pagamento_estornado", "ref_pagamento": c["ref_pagamento"],
                  "checkout": c["checkout_id"], "valor": c["valor"]}
            res = pag.aplicar_evento(con, self.cfg, c["provedor"], ev)
            if c["turma_id"]:
                t = con.execute("SELECT * FROM turmas WHERE id=?", (c["turma_id"],)).fetchone()
                if t:
                    self._chamar_espera(con, t)
            self.audita(con, a["id"], "estorno", f"{c['id']}:{_txt(corpo.get('motivo'), 120)}")
            con.commit()
            return {"ok": True, "resultado": res}
        finally:
            con.close()

    def admin_catalogo(self, cab, **_):
        self.exige_admin(cab)
        return {"itens": self.catalogo.dados["itens"], "linhas": self.catalogo.dados["linhas"], "marcas": self.catalogo.dados.get("marcas", {}),
                "responsavel": self.catalogo.responsavel()}

    def admin_catalogo_ajustar(self, corpo, cab, **_):
        a = self.exige_admin(cab)
        it = self.catalogo.item(corpo.get("item"))
        if not it:
            self.erro(404, "Item não encontrado.")
        aj = {}
        for k in cat.CAMPOS_EDITAVEIS:
            if k in corpo:
                aj[k] = bool(corpo[k]) if k in ("ativo", "noApp") else _txt(corpo[k], 400)
        if "preco" in corpo and corpo["preco"] not in (None, ""):
            aj["preco"] = max(0, int(corpo["preco"]))
        if it.get("psicologico"):
            vetadas = sorted({p for k in ("nome", "resumo", "paraQuem", "formato", "valor") for p in cat.Catalogo.revisar_texto(aj.get(k))})
            if vetadas:
                self.erro(400, "Serviço psicológico não pode ser anunciado com: " + ", ".join(vetadas) + " (Código de Ética, art. 20).")
        con = self.db.con()
        try:
            r = con.execute("SELECT dados FROM catalogo_ajustes WHERE item_id=?", (it["id"],)).fetchone()
            atual = json.loads(r["dados"]) if r else {}
            atual.update(aj)
            con.execute("INSERT OR REPLACE INTO catalogo_ajustes VALUES (?,?,?)", (it["id"], json.dumps(atual, ensure_ascii=False), iso()))
            self.audita(con, a["id"], "catalogo", f"{it['id']}:{','.join(aj)}")
            con.commit()
            self.catalogo.recarregar(con)
        finally:
            con.close()
        return {"ok": True, "item": self.catalogo.item(it["id"])}

    def admin_erros(self, cab, **_):
        self.exige_admin(cab)
        con = self.db.con()
        rows = con.execute("SELECT * FROM erros ORDER BY id DESC LIMIT 100").fetchall()
        con.close()
        return {"erros": [dict(r) for r in rows]}

    # ------------------------------------------------------------ agendador
    def tarefas_periodicas(self, quando=None):
        """Lembretes a cada minuto; e-mails de conteúdo e retenção uma vez por hora."""
        out = {"lembretes": self.disparar_lembretes(quando)}
        hora = (quando or agora_dt()).strftime("%Y%m%d%H")
        if getattr(self, "_ultima_hora", None) != hora:
            self._ultima_hora = hora
            out["emails"] = self.enviar_sequencias()
            out["retencao"] = self.aplicar_retencao()
        return out


def gerar_segredo():
    return secrets.token_urlsafe(32)
