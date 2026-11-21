"""Pagamentos do Agora TDAH — planos, checkout, webhooks e direitos de acesso.

Provedores:
  simulado     — checkout falso para desenvolvimento e testes (desligado em produção)
  mercadopago  — Pix, cartão e boleto (Checkout Pro) e assinatura recorrente (preapproval)
  stripe       — Checkout Session em modo assinatura ou pagamento único
  google_play  — compras feitas dentro do app Android (ver google_play.py)

Todo provedor converte o que recebe em EVENTOS normalizados, aplicados por
aplicar_evento(). Isso deixa a regra de negócio num lugar só e torna a gravação
idempotente (o mesmo webhook entregue duas vezes não concede acesso em dobro).
O payload do webhook nunca é confiado: o servidor sempre consulta a API do
provedor para saber o estado real antes de liberar acesso.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CARENCIA_DIAS = 3          # acesso continua alguns dias se a renovação atrasar
TOLERANCIA_ASSINATURA = 300  # segundos de diferença aceitos no carimbo de tempo do webhook


class ErroPag(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status, self.msg = status, msg


def agora():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def de_iso(s):
    if not s:
        return None
    s = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def de_epoch(n):
    return datetime.fromtimestamp(int(n), tz=timezone.utc) if n else None


def planos(cfg):
    """Planos de assinatura + produtos avulsos do catálogo (sessão, turma, e-book)."""
    return {**_planos_base(cfg), **getattr(cfg, "_produtos", {})}


def _planos_base(cfg):
    return {
        "plus_mensal": {"id": "plus_mensal", "nome": "Agora Plus mensal", "valor": cfg.preco_plus_mensal, "tipo": "recorrente",
                        "intervalo": "mes", "direito": "plus", "publico": "paciente",
                        "descricao": "Cópia na nuvem para trocar de aparelho, sala de foco com outras pessoas, relatório do mês e sons extras."},
        "plus_anual": {"id": "plus_anual", "nome": "Agora Plus anual", "valor": cfg.preco_plus_anual, "tipo": "unico", "dias": 365,
                       "direito": "plus", "publico": "paciente",
                       "descricao": "Um ano de Plus num pagamento só. Aceita Pix."},
        "pro_mensal": {"id": "pro_mensal", "nome": "Agora Pro", "valor": cfg.preco_pro_mensal, "tipo": "recorrente",
                       "intervalo": "mes", "direito": "pro", "publico": "profissional",
                       "descricao": f"Pacientes ilimitados no painel (o plano grátis vincula até {cfg.pro_gratis_pacientes})."},
    }


def reais(centavos):
    return f"{centavos / 100:.2f}"


# ------------------------------------------------------------------ HTTP
class Http:
    """Cliente HTTP mínimo (urllib). Os testes trocam por um transporte falso."""

    def __call__(self, metodo, url, cabecalhos=None, corpo=None, timeout=20):
        dados = None
        cab = dict(cabecalhos or {})
        if corpo is not None:
            if isinstance(corpo, (bytes, str)):
                dados = corpo.encode() if isinstance(corpo, str) else corpo
            else:
                dados = json.dumps(corpo).encode()
                cab.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                txt = r.read()
                return r.status, (json.loads(txt) if txt else {})
        except urllib.error.HTTPError as e:
            txt = e.read()
            try:
                return e.code, json.loads(txt)
            except Exception:
                return e.code, {"erro": txt.decode(errors="replace")[:500]}


# ------------------------------------------------------------------ provedores
class Provedor:
    nome = "base"
    recorrente_suportado = True

    def __init__(self, cfg, http=None):
        self.cfg, self.http = cfg, http or Http()

    def criar_checkout(self, ck, plano, usuario):
        raise NotImplementedError

    def cancelar(self, assinatura):
        """Pede ao provedor para não renovar. O acesso segue até o fim do período pago."""
        return True

    def portal(self, assinatura, url_volta):
        return None

    def estornar(self, ref_pagamento, valor=None):
        """Devolve o dinheiro de um pagamento único. O webhook do provedor confirma depois."""
        raise ErroPag(400, "Este meio de pagamento não faz estorno pelo sistema. Faça pelo painel do provedor.")

    def verificar_webhook(self, cab, query, bruto):
        raise ErroPag(404, "Este provedor não recebe webhooks.")

    def eventos(self, cab, query, bruto):
        return []

    def urls(self, ck, plano=None):
        base = self.cfg.url_publica
        if plano and plano.get("publico") == "profissional":
            pagina, ancora = "/app/pro.html", ""
        else:
            pagina, ancora = "/app/", "#servicos" if plano and plano.get("tipo") == "avulso" else "#mais"
        return {"sucesso": f"{base}{pagina}?pagamento=retorno&c={ck}{ancora}", "falha": f"{base}{pagina}?pagamento=falha{ancora}",
                "webhook": f"{base}/api/webhooks/{self.nome}"}


class Simulado(Provedor):  # noqa: D101
    """Checkout de mentira: abre uma página local com botões aprovar/recusar."""
    nome = "simulado"

    def criar_checkout(self, ck, plano, usuario):
        return {"url": f"/app/checkout-simulado.html?c={ck}", "ref": f"sim_{ck}"}

    def estornar(self, ref_pagamento, valor=None):
        return {"ok": True, "ref": "simrefund_" + str(ref_pagamento)}

    def evento(self, ck_row, plano, resultado):
        ev_id = f"sim:{ck_row['id']}:{resultado}"
        if resultado == "recusado":
            return {"evento_id": ev_id, "tipo": "pagamento_recusado", "checkout": ck_row["id"]}
        if plano["tipo"] in ("unico", "avulso"):
            return {"evento_id": ev_id, "tipo": "pagamento_aprovado", "checkout": ck_row["id"], "valor": plano["valor"],
                    "ref_pagamento": f"simpay_{ck_row['id']}", "metodo": "pix" if resultado == "pix" else "cartao"}
        return {"evento_id": ev_id, "tipo": "assinatura_ativa", "checkout": ck_row["id"], "ref_assinatura": f"simsub_{ck_row['id']}",
                "fim_periodo": iso(agora() + timedelta(days=31 + CARENCIA_DIAS)), "valor": plano["valor"],
                "ref_pagamento": f"simpay_{ck_row['id']}", "metodo": "cartao"}


class MercadoPago(Provedor):
    nome = "mercadopago"
    API = "https://api.mercadopago.com"

    def _cab(self, idem=None):
        c = {"Authorization": f"Bearer {self.cfg.mp_token}", "Content-Type": "application/json"}
        if idem:
            c["X-Idempotency-Key"] = idem
        return c

    def _get(self, caminho):
        st, j = self.http("GET", self.API + caminho, self._cab())
        if st >= 400:
            raise ErroPag(502, f"Mercado Pago respondeu {st} em {caminho}.")
        return j

    def criar_checkout(self, ck, plano, usuario):
        u = self.urls(ck, plano)
        if plano["tipo"] == "recorrente":
            corpo = {"reason": plano["nome"], "external_reference": ck, "payer_email": usuario["email"],
                     "auto_recurring": {"frequency": 1, "frequency_type": "months",
                                        "transaction_amount": float(reais(plano["valor"])), "currency_id": "BRL"},
                     "back_url": u["sucesso"], "status": "pending"}
            st, j = self.http("POST", self.API + "/preapproval", self._cab(ck), corpo)
        else:
            corpo = {"items": [{"id": plano["id"], "title": plano["nome"], "quantity": 1, "currency_id": "BRL",
                                "unit_price": float(reais(plano["valor"]))}],
                     "payer": {"email": usuario["email"]}, "external_reference": ck,
                     "back_urls": {"success": u["sucesso"], "failure": u["falha"], "pending": u["sucesso"]},
                     "auto_return": "approved", "notification_url": u["webhook"],
                     "statement_descriptor": "AGORA TDAH"}
            st, j = self.http("POST", self.API + "/checkout/preferences", self._cab(ck), corpo)
        if st >= 400 or not j.get("init_point"):
            raise ErroPag(502, "O Mercado Pago não criou o checkout. Confira o MP_ACCESS_TOKEN e tente de novo.")
        return {"url": j["init_point"], "ref": str(j.get("id", ""))}

    def cancelar(self, assinatura):
        st, _ = self.http("PUT", f"{self.API}/preapproval/{assinatura['ref_externa']}", self._cab(), {"status": "cancelled"})
        if st >= 400:
            raise ErroPag(502, "O Mercado Pago não confirmou o cancelamento. Tente de novo em alguns minutos.")
        return True

    def estornar(self, ref_pagamento, valor=None):
        corpo = {"amount": float(reais(valor))} if valor else {}
        st, j = self.http("POST", f"{self.API}/v1/payments/{ref_pagamento}/refunds", self._cab("rf_" + str(ref_pagamento)), corpo)
        if st >= 400:
            raise ErroPag(502, "O Mercado Pago não aceitou o estorno. Confira no painel do Mercado Pago.")
        return {"ok": True, "ref": str(j.get("id", ""))}

    @staticmethod
    def _data_id(query, corpo):
        did = (query.get("data.id") or query.get("id") or "")
        if not did and isinstance(corpo, dict):
            did = str((corpo.get("data") or {}).get("id") or corpo.get("id") or "")
        return str(did).strip()

    def verificar_webhook(self, cab, query, bruto):
        segredo = self.cfg.mp_segredo_webhook
        if not segredo:
            raise ErroPag(500, "MP_WEBHOOK_SECRET não configurado.")
        sig = cab.get("x-signature") or cab.get("X-Signature") or ""
        partes = dict(p.strip().split("=", 1) for p in sig.split(",") if "=" in p)
        ts, v1 = partes.get("ts", ""), partes.get("v1", "")
        if not ts.isdigit() or not v1:
            raise ErroPag(401, "Assinatura do webhook ausente ou malformada.")
        req_id = (cab.get("x-request-id") or cab.get("X-Request-Id") or "").strip()
        try:
            corpo = json.loads(bruto or b"{}")
        except ValueError:
            corpo = {}
        did = self._data_id(query, corpo)
        if did.isalnum():
            did = did.lower()
        manifesto = (f"id:{did};" if did else "") + (f"request-id:{req_id};" if req_id else "") + f"ts:{ts};"
        esperado = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, v1):
            raise ErroPag(401, "Assinatura do webhook não confere.")
        if abs(time.time() - int(ts) / (1000 if len(ts) > 11 else 1)) > 60 * 60 * 24:
            raise ErroPag(401, "Webhook antigo demais.")

    def eventos(self, cab, query, bruto):
        corpo = json.loads(bruto or b"{}")
        tipo = corpo.get("type") or corpo.get("topic") or query.get("type") or query.get("topic") or ""
        did = self._data_id(query, corpo)
        if not did:
            return []
        base_id = f"mp:{tipo}:{did}:{corpo.get('action', '')}:{corpo.get('id', '')}"
        if tipo == "payment":
            p = self._get(f"/v1/payments/{did}")
            st = p.get("status")
            ev = {"evento_id": base_id + ":" + str(st), "checkout": p.get("external_reference"), "ref_pagamento": str(p.get("id")),
                  "valor": round(float(p.get("transaction_amount") or 0) * 100), "metodo": p.get("payment_type_id") or ""}
            if st == "approved":
                return [dict(ev, tipo="pagamento_aprovado")]
            if st in ("refunded", "charged_back", "cancelled"):
                return [dict(ev, tipo="pagamento_estornado")]
            if st == "rejected":
                return [dict(ev, tipo="pagamento_recusado")]
            return []
        if tipo in ("subscription_preapproval", "preapproval"):
            pa = self._get(f"/preapproval/{did}")
            return [self._ev_preapproval(pa, base_id)]
        if tipo in ("subscription_authorized_payment", "authorized_payment"):
            ap = self._get(f"/authorized_payments/{did}")
            pa = self._get(f"/preapproval/{ap.get('preapproval_id')}")
            pago = (ap.get("payment") or {}).get("status") == "approved"
            ev = self._ev_preapproval(pa, base_id + ":" + str((ap.get("payment") or {}).get("status")))
            if pago:
                ev.update(valor=round(float(ap.get("transaction_amount") or 0) * 100),
                          ref_pagamento=str((ap.get("payment") or {}).get("id") or ap.get("id")))
            elif (ap.get("payment") or {}).get("status") == "rejected":
                ev["tipo"] = "assinatura_atrasada"
            return [ev]
        return []

    @staticmethod
    def _ev_preapproval(pa, ev_id):
        st = pa.get("status")
        prox = de_iso(pa.get("next_payment_date"))
        fim = (prox or agora() + timedelta(days=31)) + timedelta(days=CARENCIA_DIAS)
        tipo = {"authorized": "assinatura_ativa", "paused": "assinatura_atrasada", "cancelled": "assinatura_cancelada"}.get(st, "ignorar")
        return {"evento_id": ev_id + ":" + str(st), "tipo": tipo, "checkout": pa.get("external_reference"),
                "ref_assinatura": str(pa.get("id")), "fim_periodo": iso(fim)}


class Stripe(Provedor):
    nome = "stripe"
    API = "https://api.stripe.com/v1"

    @staticmethod
    def form(d, prefixo=""):
        itens = []
        for k, v in d.items():
            chave = f"{prefixo}[{k}]" if prefixo else str(k)
            if isinstance(v, dict):
                itens += Stripe.form(v, chave)
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    itens += Stripe.form(x, f"{chave}[{i}]") if isinstance(x, dict) else [(f"{chave}[{i}]", str(x))]
            elif v is not None:
                itens.append((chave, "true" if v is True else "false" if v is False else str(v)))
        return itens

    def _req(self, metodo, caminho, dados=None, idem=None):
        cab = {"Authorization": f"Bearer {self.cfg.stripe_chave}"}
        if self.cfg.stripe_versao:
            cab["Stripe-Version"] = self.cfg.stripe_versao
        corpo = None
        if dados is not None:
            cab["Content-Type"] = "application/x-www-form-urlencoded"
            corpo = urllib.parse.urlencode(self.form(dados))
        if idem:
            cab["Idempotency-Key"] = idem
        st, j = self.http(metodo, self.API + caminho, cab, corpo)
        if st >= 400:
            raise ErroPag(502, f"Stripe respondeu {st}: {(j.get('error') or {}).get('message', '')}".strip())
        return j

    def criar_checkout(self, ck, plano, usuario):
        u = self.urls(ck, plano)
        preco = {"currency": "brl", "unit_amount": plano["valor"], "product_data": {"name": plano["nome"]}}
        d = {"client_reference_id": ck, "customer_email": usuario["email"], "success_url": u["sucesso"],
             "cancel_url": u["falha"], "locale": "pt-BR", "metadata": {"checkout": ck, "plano": plano["id"]}}
        if plano["tipo"] == "recorrente":
            preco["recurring"] = {"interval": "month"}
            d.update(mode="subscription", subscription_data={"metadata": {"checkout": ck, "plano": plano["id"]}})
        else:
            d.update(mode="payment", payment_intent_data={"metadata": {"checkout": ck, "plano": plano["id"]}})
        d["line_items"] = [{"price_data": preco, "quantity": 1}]
        j = self._req("POST", "/checkout/sessions", d, idem=ck)
        return {"url": j["url"], "ref": j["id"]}

    def cancelar(self, assinatura):
        self._req("POST", f"/subscriptions/{assinatura['ref_externa']}", {"cancel_at_period_end": True})
        return True

    def estornar(self, ref_pagamento, valor=None):
        d = {"payment_intent": ref_pagamento}
        if valor:
            d["amount"] = valor
        j = self._req("POST", "/refunds", d, idem="rf_" + str(ref_pagamento))
        return {"ok": True, "ref": j.get("id")}

    def portal(self, assinatura, url_volta):
        if not assinatura.get("cliente"):
            return None
        return self._req("POST", "/billing_portal/sessions", {"customer": assinatura["cliente"], "return_url": url_volta})["url"]

    def verificar_webhook(self, cab, query, bruto):
        segredo = self.cfg.stripe_segredo_webhook
        if not segredo:
            raise ErroPag(500, "STRIPE_WEBHOOK_SECRET não configurado.")
        sig = cab.get("Stripe-Signature") or cab.get("stripe-signature") or ""
        ts, assinaturas = "", []
        for p in sig.split(","):
            if "=" in p:
                k, v = p.strip().split("=", 1)
                if k == "t":
                    ts = v
                elif k == "v1":
                    assinaturas.append(v)
        if not ts.isdigit() or not assinaturas:
            raise ErroPag(401, "Assinatura do webhook ausente ou malformada.")
        esperado = hmac.new(segredo.encode(), ts.encode() + b"." + (bruto or b""), hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(esperado, a) for a in assinaturas):
            raise ErroPag(401, "Assinatura do webhook não confere.")
        if abs(time.time() - int(ts)) > TOLERANCIA_ASSINATURA:
            raise ErroPag(401, "Webhook fora da janela de tempo.")

    @staticmethod
    def _fim_assinatura(sub):
        fim = sub.get("current_period_end")
        if not fim:
            itens = ((sub.get("items") or {}).get("data") or [])
            fim = max([i.get("current_period_end") or 0 for i in itens] or [0])
        return de_epoch(fim) if fim else None

    def eventos(self, cab, query, bruto):
        e = json.loads(bruto or b"{}")
        t, o, eid = e.get("type"), (e.get("data") or {}).get("object") or {}, e.get("id")
        meta = o.get("metadata") or {}
        if t == "checkout.session.completed":
            ck = o.get("client_reference_id") or meta.get("checkout")
            if o.get("mode") == "payment":
                if o.get("payment_status") == "paid":
                    return [{"evento_id": eid, "tipo": "pagamento_aprovado", "checkout": ck, "valor": o.get("amount_total"),
                             "ref_pagamento": o.get("payment_intent") or o.get("id"), "metodo": "stripe"}]
                return []
            return [{"evento_id": eid, "tipo": "assinatura_ativa", "checkout": ck, "ref_assinatura": o.get("subscription"),
                     "cliente": o.get("customer"), "fim_periodo": iso(agora() + timedelta(days=31 + CARENCIA_DIAS))}]
        if t == "checkout.session.async_payment_succeeded" and o.get("mode") == "payment":
            return [{"evento_id": eid, "tipo": "pagamento_aprovado", "checkout": o.get("client_reference_id") or meta.get("checkout"),
                     "valor": o.get("amount_total"), "ref_pagamento": o.get("payment_intent"), "metodo": "pix"}]
        if t in ("invoice.paid", "invoice.payment_failed"):
            sub = o.get("subscription") or (((o.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
            if not sub:
                return []
            linhas = ((o.get("lines") or {}).get("data") or [])
            fim = max([((l.get("period") or {}).get("end") or 0) for l in linhas] or [0])
            ck = (((o.get("parent") or {}).get("subscription_details") or {}).get("metadata") or {}).get("checkout") \
                or ((o.get("subscription_details") or {}).get("metadata") or {}).get("checkout")
            if t == "invoice.payment_failed":
                return [{"evento_id": eid, "tipo": "assinatura_atrasada", "ref_assinatura": sub, "checkout": ck}]
            return [{"evento_id": eid, "tipo": "assinatura_ativa", "ref_assinatura": sub, "checkout": ck, "cliente": o.get("customer"),
                     "fim_periodo": iso((de_epoch(fim) if fim else agora() + timedelta(days=31)) + timedelta(days=CARENCIA_DIAS)),
                     "valor": o.get("amount_paid"), "ref_pagamento": o.get("id"), "metodo": "stripe"}]
        if t in ("customer.subscription.updated", "customer.subscription.deleted"):
            st, fim = o.get("status"), self._fim_assinatura(o)
            ev = {"evento_id": eid, "ref_assinatura": o.get("id"), "checkout": meta.get("checkout"), "cliente": o.get("customer"),
                  "cancelar_no_fim": bool(o.get("cancel_at_period_end"))}
            if t == "customer.subscription.deleted" or st == "canceled":
                return [dict(ev, tipo="assinatura_cancelada", fim_periodo=iso(agora()))]
            if st in ("past_due", "unpaid"):
                return [dict(ev, tipo="assinatura_atrasada")]
            if st in ("active", "trialing") and fim:
                return [dict(ev, tipo="assinatura_ativa", fim_periodo=iso(fim + timedelta(days=CARENCIA_DIAS)))]
            return []
        if t == "charge.refunded":
            return [{"evento_id": eid, "tipo": "pagamento_estornado", "ref_pagamento": o.get("payment_intent") or o.get("id")}]
        return []


PROVEDORES = {"simulado": Simulado, "mercadopago": MercadoPago, "stripe": Stripe}


def provedor(cfg, nome=None, http=None):
    nome = nome or cfg.provedor
    if nome not in PROVEDORES:
        raise ErroPag(500, f"Provedor de pagamento desconhecido: {nome}")
    if nome == "simulado" and cfg.producao:
        raise ErroPag(403, "O checkout simulado fica desligado em produção.")
    return PROVEDORES[nome](cfg, http)


# ------------------------------------------------------------------ regras
ESQUEMA_PAG = """
CREATE TABLE IF NOT EXISTS checkouts (
  id TEXT PRIMARY KEY, usuario_id INTEGER NOT NULL, plano TEXT NOT NULL, provedor TEXT NOT NULL,
  ref_externa TEXT, status TEXT NOT NULL DEFAULT 'aberto', criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assinaturas (
  id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, plano TEXT NOT NULL, direito TEXT NOT NULL,
  provedor TEXT NOT NULL, ref_externa TEXT, cliente TEXT, status TEXT NOT NULL,
  fim_periodo TEXT NOT NULL, cancelar_no_fim INTEGER DEFAULT 0, criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assin_ref ON assinaturas(provedor, ref_externa);
CREATE INDEX IF NOT EXISTS ix_assin_usuario ON assinaturas(usuario_id);
CREATE TABLE IF NOT EXISTS pagamentos (
  id INTEGER PRIMARY KEY, usuario_id INTEGER, plano TEXT, provedor TEXT NOT NULL, ref_externa TEXT,
  valor INTEGER, metodo TEXT, status TEXT NOT NULL, criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos_webhook (
  provedor TEXT NOT NULL, evento_id TEXT NOT NULL, tipo TEXT, recebido_em TEXT NOT NULL,
  PRIMARY KEY (provedor, evento_id)
);
"""


def novo_checkout(con, cfg, usuario, plano_id, prov, valor=None, meta=None, nome=None):
    pl = planos(cfg).get(plano_id)
    if not pl:
        raise ErroPag(400, "Plano inexistente.")
    if pl["publico"] not in (usuario["papel"], "qualquer"):
        raise ErroPag(403, "Este plano não é para o seu tipo de conta.")
    if valor is not None or nome:
        pl = dict(pl, valor=int(valor if valor is not None else pl["valor"]), nome=nome or pl["nome"])
    ck = "ck_" + secrets.token_urlsafe(12)
    r = prov.criar_checkout(ck, pl, usuario)
    meta = dict(meta or {}, valor=pl["valor"])
    con.execute("INSERT INTO checkouts(id,usuario_id,plano,provedor,ref_externa,criado_em,meta) VALUES (?,?,?,?,?,?,?)",
                (ck, usuario["id"], plano_id, prov.nome, r.get("ref"), iso(agora()), json.dumps(meta)))
    return {"checkout": ck, "url": r["url"]}


def meta_checkout(ck_row):
    try:
        return json.loads(ck_row["meta"] or "{}")
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


def _entregar_avulso(con, ck, pl, provedor_nome, ev):
    """Pagamento aprovado de produto avulso: registra a compra e confirma a vaga da turma."""
    meta = meta_checkout(ck)
    agora_s = iso(agora())
    item = pl["item"] + (":" + pl["sub"] if pl.get("sub") else "")
    con.execute("INSERT OR IGNORE INTO compras(usuario_id,item_id,entrega,turma_id,checkout_id,provedor,ref_pagamento,valor,status,criado_em,atualizado_em) "
                "VALUES (?,?,?,?,?,?,?,?,'paga',?,?)", (ck["usuario_id"], item, pl["entrega"], meta.get("turma"), ck["id"], provedor_nome,
                                                        ev.get("ref_pagamento"), ev.get("valor") or meta.get("valor"), agora_s, agora_s))
    if meta.get("turma"):
        con.execute("UPDATE inscricoes SET status='confirmada', atualizado_em=? WHERE checkout_id=?", (agora_s, ck["id"]))
    con.execute("UPDATE checkouts SET status='pago' WHERE id=?", (ck["id"],))
    _registrar_pagamento(con, ck["usuario_id"], ck["plano"], provedor_nome, ev)
    return f"compra registrada: {pl['nome']}"


def _registrar_pagamento(con, uid, plano, provedor_nome, ev, status="aprovado"):
    if not ev.get("ref_pagamento"):
        return
    if con.execute("SELECT 1 FROM pagamentos WHERE provedor=? AND ref_externa=? AND status=?",
                   (provedor_nome, ev["ref_pagamento"], status)).fetchone():
        return
    con.execute("INSERT INTO pagamentos(usuario_id,plano,provedor,ref_externa,valor,metodo,status,criado_em) VALUES (?,?,?,?,?,?,?,?)",
                (uid, plano, provedor_nome, ev["ref_pagamento"], ev.get("valor"), ev.get("metodo", ""), status, iso(agora())))


def aplicar_evento(con, cfg, provedor_nome, ev):
    """Aplica um evento normalizado. Devolve um texto curto com o que aconteceu."""
    if not ev or ev.get("tipo") in (None, "ignorar"):
        return "ignorado"
    try:
        con.execute("INSERT INTO eventos_webhook VALUES (?,?,?,?)", (provedor_nome, str(ev["evento_id"]), ev["tipo"], iso(agora())))
    except Exception:  # chave repetida = já processado
        return "duplicado"
    pls = planos(cfg)
    ck = con.execute("SELECT * FROM checkouts WHERE id=?", (ev.get("checkout"),)).fetchone() if ev.get("checkout") else None
    assin = None
    if ev.get("ref_assinatura"):
        assin = con.execute("SELECT * FROM assinaturas WHERE provedor=? AND ref_externa=?", (provedor_nome, ev["ref_assinatura"])).fetchone()
    agora_s = iso(agora())
    tipo = ev["tipo"]

    if tipo == "pagamento_recusado":
        if ck:
            con.execute("UPDATE checkouts SET status='recusado' WHERE id=?", (ck["id"],))
        return "recusado"

    if tipo == "pagamento_estornado":
        row = con.execute("SELECT * FROM pagamentos WHERE provedor=? AND ref_externa=?", (provedor_nome, ev.get("ref_pagamento"))).fetchone()
        uid = (row["usuario_id"] if row else None) or (ck["usuario_id"] if ck else None)
        if not uid:
            return "estorno sem pagamento conhecido"
        plano = (row["plano"] if row else None) or (ck["plano"] if ck else None)
        _registrar_pagamento(con, uid, plano, provedor_nome, ev, status="estornado")
        if pls.get(plano, {}).get("tipo") == "avulso" or str(plano or "").startswith("item:"):
            compra = con.execute("SELECT * FROM compras WHERE provedor=? AND ref_pagamento=?", (provedor_nome, ev.get("ref_pagamento"))).fetchone()
            if compra:
                con.execute("UPDATE compras SET status='estornada', atualizado_em=? WHERE id=?", (agora_s, compra["id"]))
                con.execute("UPDATE inscricoes SET status='cancelada', atualizado_em=? WHERE checkout_id=?", (agora_s, compra["checkout_id"]))
            return "compra estornada"
        direito = pls.get(plano, {}).get("direito", "plus")
        con.execute("UPDATE assinaturas SET status='estornada', fim_periodo=?, atualizado_em=? WHERE usuario_id=? AND direito=? AND fim_periodo>?",
                    (agora_s, agora_s, uid, direito, agora_s))
        return "estornado"

    if tipo == "pagamento_aprovado":
        if not ck:
            return "pagamento sem checkout conhecido"
        pl = pls.get(ck["plano"])
        if not pl:
            return "produto fora do catálogo: confira o painel"
        if pl["tipo"] == "avulso":
            return _entregar_avulso(con, ck, pl, provedor_nome, ev)
        if pl["tipo"] == "recorrente":  # cobrança de assinatura chega também como "payment": só registra
            _registrar_pagamento(con, ck["usuario_id"], ck["plano"], provedor_nome, ev)
            return "pagamento de assinatura registrado"
        atual = con.execute("SELECT MAX(fim_periodo) m FROM assinaturas WHERE usuario_id=? AND direito=? AND fim_periodo>?",
                            (ck["usuario_id"], pl["direito"], agora_s)).fetchone()["m"]
        inicio = max(agora(), de_iso(atual) or agora())
        fim = iso(inicio + timedelta(days=pl.get("dias", 365)))
        con.execute("INSERT INTO assinaturas(usuario_id,plano,direito,provedor,ref_externa,status,fim_periodo,criado_em,atualizado_em) "
                    "VALUES (?,?,?,?,?,'ativa',?,?,?)", (ck["usuario_id"], ck["plano"], pl["direito"], provedor_nome,
                                                        ev.get("ref_pagamento"), fim, agora_s, agora_s))
        con.execute("UPDATE checkouts SET status='pago' WHERE id=?", (ck["id"],))
        _registrar_pagamento(con, ck["usuario_id"], ck["plano"], provedor_nome, ev)
        return "acesso liberado até " + fim[:10]

    if tipo in ("assinatura_ativa", "assinatura_atrasada", "assinatura_cancelada"):
        if not assin and not ck:
            return "assinatura desconhecida"
        status = {"assinatura_ativa": "ativa", "assinatura_atrasada": "atrasada", "assinatura_cancelada": "cancelada"}[tipo]
        if not assin:
            pl = pls[ck["plano"]]
            fim = ev.get("fim_periodo") or iso(agora() + timedelta(days=31 + CARENCIA_DIAS))
            if status != "ativa":
                fim = agora_s
            con.execute("INSERT INTO assinaturas(usuario_id,plano,direito,provedor,ref_externa,cliente,status,fim_periodo,cancelar_no_fim,criado_em,atualizado_em) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (ck["usuario_id"], ck["plano"], pl["direito"], provedor_nome, ev.get("ref_assinatura"),
                                                           ev.get("cliente"), status, fim, int(bool(ev.get("cancelar_no_fim"))), agora_s, agora_s))
            con.execute("UPDATE checkouts SET status='pago' WHERE id=?", (ck["id"],))
            if status == "ativa":
                _registrar_pagamento(con, ck["usuario_id"], ck["plano"], provedor_nome, ev)
            return "assinatura " + status
        fim = assin["fim_periodo"]
        if status == "ativa" and ev.get("fim_periodo"):
            fim = max(fim, ev["fim_periodo"])
        if tipo == "assinatura_cancelada" and ev.get("fim_periodo"):
            # Stripe e Google Play informam quando o acesso termina; no Mercado Pago o período pago continua.
            fim = min(fim, max(ev["fim_periodo"], agora_s)) if provedor_nome in ("stripe", "google_play") else fim
        cancelar = int(bool(ev.get("cancelar_no_fim"))) if "cancelar_no_fim" in ev else assin["cancelar_no_fim"]
        con.execute("UPDATE assinaturas SET status=?, fim_periodo=?, cliente=COALESCE(?,cliente), cancelar_no_fim=?, atualizado_em=? WHERE id=?",
                    (status, fim, ev.get("cliente"), cancelar, agora_s, assin["id"]))
        if status == "ativa":
            _registrar_pagamento(con, assin["usuario_id"], assin["plano"], provedor_nome, ev)
        return "assinatura " + status
    return "ignorado"


def direitos(con, uid):
    agora_s = iso(agora())
    out = {"plus": False, "pro": False, "plus_ate": None, "pro_ate": None}
    for r in con.execute("SELECT direito, MAX(fim_periodo) fim FROM assinaturas WHERE usuario_id=? AND fim_periodo>? "
                         "AND status NOT IN ('estornada') GROUP BY direito", (uid, agora_s)):
        out[r["direito"]] = True
        out[r["direito"] + "_ate"] = r["fim"]
    return out


def resumo_assinaturas(con, cfg, uid):
    pls = planos(cfg)
    rows = con.execute("SELECT * FROM assinaturas WHERE usuario_id=? ORDER BY fim_periodo DESC LIMIT 10", (uid,)).fetchall()
    pag = con.execute("SELECT plano,provedor,valor,metodo,status,criado_em FROM pagamentos WHERE usuario_id=? ORDER BY id DESC LIMIT 20", (uid,)).fetchall()
    agora_s = iso(agora())
    return {
        "assinaturas": [{"id": r["id"], "plano": r["plano"], "nome": pls.get(r["plano"], {}).get("nome", r["plano"]),
                         "provedor": r["provedor"], "status": r["status"], "fim_periodo": r["fim_periodo"],
                         "vigente": r["fim_periodo"] > agora_s and r["status"] != "estornada",
                         "recorrente": pls.get(r["plano"], {}).get("tipo") == "recorrente",
                         "cancelar_no_fim": bool(r["cancelar_no_fim"])} for r in rows],
        "pagamentos": [dict(p) for p in pag],
    }


def cancelar_assinatura(con, cfg, uid, assinatura_id, http=None):
    a = con.execute("SELECT * FROM assinaturas WHERE id=? AND usuario_id=?", (assinatura_id, uid)).fetchone()
    if not a:
        raise ErroPag(404, "Assinatura não encontrada.")
    if planos(cfg).get(a["plano"], {}).get("tipo") != "recorrente":
        raise ErroPag(400, "Plano anual não renova sozinho: não há o que cancelar.")
    if a["provedor"] == "google_play":
        raise ErroPag(400, "Assinaturas feitas pelo Google Play são canceladas no app Play Store, em Pagamentos e assinaturas.")
    if a["provedor"] not in ("cortesia",):
        provedor(cfg, a["provedor"], http).cancelar(dict(a))
    con.execute("UPDATE assinaturas SET cancelar_no_fim=1, atualizado_em=? WHERE id=?", (iso(agora()), a["id"]))
    return {"ok": True, "acesso_ate": a["fim_periodo"]}
