"""Validação de assinaturas compradas pelo Google Play (Play Billing), só com a biblioteca padrão.

Fluxo:
  1. O app Android compra pelo Play Billing e envia o purchaseToken para
     POST /api/pagamentos/google-play.
  2. O servidor autentica na Google Play Developer API com a conta de serviço
     (JWT assinado em RS256, implementado aqui sem bibliotecas externas),
     consulta purchases.subscriptionsv2 e libera o direito até expiryTime.
  3. Compras novas são confirmadas (acknowledge) em até 3 dias, senão o Google estorna.
  4. As notificações em tempo real (RTDN, via Pub/Sub push) chegam em
     POST /api/webhooks/google-play?token=... e disparam nova consulta à API.
"""
import base64
import hashlib
import json
import time
import urllib.parse

from pagamentos import CARENCIA_DIAS, ErroPag, Http, de_iso, iso
from datetime import timedelta

ESCOPO = "https://www.googleapis.com/auth/androidpublisher"
API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
# Prefixo DER do DigestInfo de SHA-256 (RFC 8017, seção 9.2)
DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


# ---------------------------------------------------------------- ASN.1 / RSA
def _der(b, i):
    tag = b[i]
    tam = b[i + 1]
    i += 2
    if tam & 0x80:
        n = tam & 0x7F
        tam = int.from_bytes(b[i:i + n], "big")
        i += n
    return tag, b[i:i + tam], i + tam


def _sequencia(b):
    itens, i = [], 0
    while i < len(b):
        tag, val, i = _der(b, i)
        itens.append((tag, val))
    return itens


def carregar_chave(pem):
    """Lê uma chave RSA privada PEM (PKCS#8 ou PKCS#1) e devolve (n, e, d)."""
    linhas = [l for l in pem.strip().splitlines() if not l.startswith("-----")]
    der = base64.b64decode("".join(linhas))
    tag, conteudo, _ = _der(der, 0)
    itens = _sequencia(conteudo)
    if "BEGIN PRIVATE KEY" in pem:  # PKCS#8: versão, algoritmo, OCTET STRING com a chave PKCS#1
        _, rsa_der = itens[2]
        _, conteudo, _ = _der(rsa_der, 0)
        itens = _sequencia(conteudo)
    nums = [int.from_bytes(v, "big") for t, v in itens if t == 0x02]
    _, n, e, d = nums[:4]
    return n, e, d


def assinar_rs256(msg, chave):
    n, _, d = chave
    k = (n.bit_length() + 7) // 8
    t = DIGESTINFO_SHA256 + hashlib.sha256(msg).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def verificar_rs256(msg, assinatura, n, e):
    k = (n.bit_length() + 7) // 8
    em = pow(int.from_bytes(assinatura, "big"), e, n).to_bytes(k, "big")
    t = DIGESTINFO_SHA256 + hashlib.sha256(msg).digest()
    return em == b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


def jwt_conta_servico(conta, agora=None):
    agora = int(agora or time.time())
    cab = b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": conta.get("private_key_id", "")}).encode())
    corpo = b64url(json.dumps({"iss": conta["client_email"], "scope": ESCOPO,
                               "aud": conta.get("token_uri", "https://oauth2.googleapis.com/token"),
                               "iat": agora, "exp": agora + 3600}).encode())
    base = f"{cab}.{corpo}".encode()
    return f"{cab}.{corpo}.{b64url(assinar_rs256(base, carregar_chave(conta['private_key'])))}"


def conta_externa(uid):
    """Identificador opaco do usuário passado ao Play Billing (obfuscatedAccountId)."""
    return hashlib.sha256(f"agora-conta:{uid}".encode()).hexdigest()[:40]


class GooglePlay:
    def __init__(self, cfg, http=None, conta=None):
        self.cfg, self.http = cfg, http or Http()
        if conta is None and cfg.play_conta_servico:
            with open(cfg.play_conta_servico, encoding="utf-8") as f:
                conta = json.load(f)
        self.conta = conta
        self._token, self._expira = None, 0

    def token(self):
        if not self.conta:
            raise ErroPag(500, "PLAY_CONTA_SERVICO_JSON não configurado.")
        if self._token and time.time() < self._expira - 60:
            return self._token
        corpo = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                        "assertion": jwt_conta_servico(self.conta)})
        st, j = self.http("POST", self.conta.get("token_uri", "https://oauth2.googleapis.com/token"),
                          {"Content-Type": "application/x-www-form-urlencoded"}, corpo)
        if st >= 400 or "access_token" not in j:
            raise ErroPag(502, "Google recusou a conta de serviço. Confira as permissões no Play Console.")
        self._token, self._expira = j["access_token"], time.time() + int(j.get("expires_in", 3600))
        return self._token

    def consultar(self, purchase_token):
        url = f"{API}/{self.cfg.play_pacote}/purchases/subscriptionsv2/tokens/{urllib.parse.quote(purchase_token, safe='')}"
        st, j = self.http("GET", url, {"Authorization": f"Bearer {self.token()}"})
        if st == 404 or st == 410:
            raise ErroPag(404, "Compra não encontrada no Google Play.")
        if st >= 400:
            raise ErroPag(502, f"Google Play respondeu {st}.")
        return j

    def reconhecer(self, produto, purchase_token):
        url = (f"{API}/{self.cfg.play_pacote}/purchases/subscriptions/{urllib.parse.quote(produto)}"
               f"/tokens/{urllib.parse.quote(purchase_token, safe='')}:acknowledge")
        st, _ = self.http("POST", url, {"Authorization": f"Bearer {self.token()}"}, {})
        return st < 400


ATIVOS = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD"}


def interpretar(resp, cfg):
    itens = resp.get("lineItems") or []
    fim = max([de_iso(i.get("expiryTime")) for i in itens if i.get("expiryTime")] or [None], default=None) if itens else None
    produto = itens[0].get("productId") if itens else None
    estado = resp.get("subscriptionState", "")
    return {"estado": estado, "ativo": estado in ATIVOS, "produto": produto, "plano": cfg.play_produtos.get(produto or ""),
            "fim": fim, "reconhecido": resp.get("acknowledgementState") == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
            "conta": ((resp.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId")),
            "token_anterior": resp.get("linkedPurchaseToken")}


def evento(info, purchase_token, ev_id):
    if info["ativo"] and info["fim"]:
        return {"evento_id": ev_id, "tipo": "assinatura_ativa", "ref_assinatura": purchase_token,
                "fim_periodo": iso(info["fim"] + timedelta(days=0 if info["estado"].endswith("GRACE_PERIOD") else 0)),
                "ref_pagamento": f"{purchase_token[:24]}:{iso(info['fim'])[:10]}", "metodo": "google_play"}
    if info["estado"] in ("SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"):
        return {"evento_id": ev_id, "tipo": "assinatura_atrasada", "ref_assinatura": purchase_token}
    return {"evento_id": ev_id, "tipo": "assinatura_cancelada", "ref_assinatura": purchase_token,
            "fim_periodo": iso(info["fim"]) if info["fim"] else None}


def ler_rtdn(bruto):
    """Decodifica a mensagem push do Pub/Sub. Devolve (purchaseToken, subscriptionId, tipo) ou None."""
    try:
        msg = json.loads(bruto or b"{}").get("message") or {}
        dados = json.loads(base64.b64decode(msg.get("data") or b"e30="))
    except Exception:
        return None
    sn = dados.get("subscriptionNotification")
    if not sn:
        return None  # teste do console, compra única, etc.
    return sn.get("purchaseToken"), sn.get("subscriptionId"), sn.get("notificationType"), msg.get("messageId")
