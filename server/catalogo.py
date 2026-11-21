"""Catálogo de serviços: leitura, ajustes do administrador e regras de exibição.

Fonte: server/catalogo_padrao.json (ou AGORA_CATALOGO), mais os ajustes gravados
pelo painel de administração na tabela catalogo_ajustes (preço, ativo, textos).

Regras de exibição no app (conformidade CFP e Google Play):
  - só itens com noApp=true e ativo=true;
  - paciente vinculado a um profissional não vê serviços psicológicos de terceiros
    (o cuidado dele é com quem já o acompanha);
  - no app Android só aparecem atendimentos individuais ao vivo (venda.android=true)
    e formulários de interesse ou proposta, sem preço de produto digital;
  - todo serviço psicológico leva nome e CRP do responsável técnico;
  - nenhum texto de desconto, gratuidade de atendimento ou promessa de resultado.
"""
import copy
import json
import os
from pathlib import Path

PADRAO = Path(__file__).resolve().parent / "catalogo_padrao.json"
MODOS_VENDA = ("sessao", "turma", "ebook")
CAMPOS_EDITAVEIS = ("nome", "resumo", "paraQuem", "formato", "valor", "ativo", "noApp")
PALAVRAS_PROIBIDAS = ("desconto", "promoção", "promocao", "grátis na primeira", "garantido", "garantia de resultado",
                      "cura", "100%", "pacote", "imperdível", "últimas vagas")


class Catalogo:
    def __init__(self, cfg, banco=None):
        self.cfg, self.banco = cfg, banco
        self.recarregar()

    def recarregar(self, con=None):
        arq = Path(os.environ.get("AGORA_CATALOGO") or getattr(self.cfg, "catalogo_arquivo", "") or PADRAO)
        self.base = json.loads(arq.read_text(encoding="utf-8"))
        ajustes = {}
        fechar = False
        if con is None and self.banco is not None:
            con, fechar = self.banco.con(), True
        if con is not None:
            try:
                ajustes = {r["item_id"]: json.loads(r["dados"]) for r in con.execute("SELECT item_id, dados FROM catalogo_ajustes")}
            except Exception:
                ajustes = {}
            finally:
                if fechar:
                    con.close()
        self.dados = copy.deepcopy(self.base)
        for it in self.dados["itens"]:
            aj = ajustes.get(it["id"]) or {}
            for k in CAMPOS_EDITAVEIS:
                if k in aj:
                    it[k] = aj[k]
            if "preco" in aj and isinstance(it.get("venda"), dict):
                it["venda"]["valor"] = int(aj["preco"])
        self.indice = {i["id"]: i for i in self.dados["itens"]}
        # produtos avulsos entram na tabela de planos dos pagamentos
        self.cfg._produtos = self.planos_avulsos()

    def item(self, item_id):
        return self.indice.get(str(item_id or ""))

    def planos_avulsos(self):
        out = {}
        for it in self.dados["itens"]:
            v = it.get("venda") or {}
            if v.get("modo") not in MODOS_VENDA or not v.get("valor") or not it.get("ativo", True):
                continue
            base = {"nome": it["nome"], "valor": int(v["valor"]), "tipo": "avulso", "entrega": v["modo"], "publico": "qualquer",
                    "item": it["id"], "android": bool(v.get("android")), "descricao": it.get("resumo", "")}
            if v["modo"] == "ebook" and v.get("titulos"):
                for t in v["titulos"]:
                    pid = f"item:{it['id']}:{t['id']}"
                    out[pid] = dict(base, id=pid, nome=t["titulo"], sub=t["id"])
            else:
                out[f"item:{it['id']}"] = dict(base, id=f"item:{it['id']}")
        return out

    def responsavel(self):
        return {"nome": self.cfg.responsavel_nome, "crp": self.cfg.responsavel_crp, "contato": self.cfg.contato_publico}

    def visivel(self, it, plataforma="web", vinculado=False):
        if not it.get("ativo", True) or not it.get("noApp"):
            return False
        v = it.get("venda") or {}
        if vinculado and it.get("psicologico"):
            return False
        if plataforma == "android":
            return bool(v.get("android")) or v.get("modo") in ("interesse", "proposta")
        return True

    def publico(self, plataforma="web", vinculado=False, linhas=None):
        """linhas: restringe a linhas do catálogo (o app do paciente pede só "pessoas"; empresas e psicólogos ficam no site)."""
        resp = self.responsavel()
        itens = []
        for it in self.dados["itens"]:
            if not self.visivel(it, plataforma, vinculado) or (linhas and it.get("linha") not in linhas):
                continue
            v = it.get("venda") or {}
            marca = self.dados.get("marcas", {}).get(it.get("marca"), {})
            x = {k: it.get(k) for k in ("id", "linha", "etapa", "nome", "resumo", "paraQuem", "formato", "marca", "psicologico")}
            x["marcaNome"] = marca.get("nome", it.get("marca"))
            x["modo"] = v.get("modo", "interesse")
            if x["modo"] in MODOS_VENDA:
                x["preco"] = v.get("valor")
            x["valorTexto"] = it.get("valor") if not (plataforma == "android" and x["modo"] == "ebook") else None
            if v.get("titulos"):
                x["titulos"] = v["titulos"]
            if it.get("psicologico"):
                x["responsavel"] = resp
            itens.append(x)
        linhas = [l for l in self.dados["linhas"] if any(i["linha"] == l["id"] for i in itens)]
        return {"versao": self.dados.get("versao"), "linhas": linhas, "itens": itens, "responsavel": resp,
                "etapas": self.dados.get("etapas", [])}

    @staticmethod
    def revisar_texto(texto):
        """Devolve as expressões vetadas encontradas (publicidade de serviço psicológico)."""
        t = str(texto or "").lower()
        return [p for p in PALAVRAS_PROIBIDAS if p in t]


# Missões semanais dos treinos de habilidades sociais (Lume). Texto psicoeducativo:
# o programa em si é conduzido em grupo pelo psicólogo responsável.
MISSOES_THS = {
    "ths-tdah": [
        ("Mapa das situações", "Anote três situações sociais da semana que deram trabalho. Para cada uma: onde, com quem e o que você queria que tivesse acontecido."),
        ("Escuta até o fim", "Em duas conversas, espere a outra pessoa terminar a frase antes de responder. Se a ideia escapar, anote uma palavra e volte a ouvir."),
        ("Pedir uma pausa", "Use uma vez a frase: 'me dá um minuto para pensar?'. Repare como a conversa continua depois."),
        ("Combinar por escrito", "Depois de um combinado importante, mande uma mensagem curta resumindo o que ficou decidido."),
        ("Dizer não com cuidado", "Recuse um pedido que não cabe na sua semana usando: reconhecer o pedido, dizer o limite, oferecer o que é possível."),
        ("Retomar depois do atraso", "Se atrasar ou esquecer algo, avise em uma frase, sem justificativa longa, e diga o próximo passo."),
        ("Feedback pequeno", "Peça a alguém de confiança um retorno sobre uma conversa sua: o que funcionou e uma coisa a ajustar."),
        ("Plano de manutenção", "Escolha as duas habilidades do programa que mais ajudaram e escreva quando e onde vai praticá-las no próximo mês."),
    ],
    "ths-tech": [
        ("Inventário de reuniões", "Liste as reuniões da semana e marque em quais você falou o que queria. Em uma delas, anote o que travou."),
        ("Uma pergunta na daily", "Faça uma pergunta de esclarecimento numa reunião, em até duas frases."),
        ("Discordar com dados", "Em uma revisão de código ou decisão técnica, discorde usando: o que observei, o risco que vejo, uma alternativa."),
        ("Pedir ajuda cedo", "Quando ficar travado mais de 40 minutos, peça ajuda descrevendo o que já tentou."),
        ("Negociar prazo", "Responda a um pedido urgente com uma estimativa honesta e uma pergunta sobre prioridade."),
        ("Elogio específico", "Reconheça o trabalho de um colega dizendo exatamente o que ajudou você."),
        ("1:1 preparado", "Leve para sua próxima conversa com a liderança três tópicos escritos: o que avançou, o que trava, o que precisa."),
        ("Plano de manutenção", "Escolha as duas habilidades que mais fizeram diferença e combine consigo mesmo onde vai praticá-las."),
    ],
}
