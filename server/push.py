"""Web Push sem conteúdo (RFC 8030 + VAPID RFC 8292), só biblioteca padrão.

O servidor manda um "toque" vazio ao serviço de push do navegador. O service worker
acorda, busca as mensagens pendentes em /api/push/pendentes (provando que é dono da
inscrição com o segredo `auth` dela) e mostra a notificação. Assim nenhum texto passa
pelos servidores do Google, Mozilla ou Apple, e dispensa a cifra aes128gcm do payload.
"""
import time
from urllib.parse import urlparse

import cripto


def gerar_chaves():
    d, pub = cripto.nova_chave_ec()
    return cripto.b64u(d.to_bytes(32, "big")), cripto.b64u(cripto.publica_bytes(pub))


def _chave_privada(cfg):
    return int.from_bytes(cripto.de_b64u(cfg.vapid_privada), "big")


def configurado(cfg):
    return bool(cfg.vapid_privada and cfg.vapid_publica)


def cabecalho_vapid(cfg, endpoint, agora=None):
    u = urlparse(endpoint)
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int((agora or time.time()) + 12 * 3600), "sub": cfg.vapid_contato}
    jwt = cripto.jwt_es256(_chave_privada(cfg), claims)
    return f"vapid t={jwt}, k={cfg.vapid_publica}"


def tocar(cfg, http, endpoint, ttl=3600, urgencia="normal"):
    """Envia o toque vazio. Devolve 'ok', 'expirada' (apagar inscrição) ou 'falha'."""
    if not configurado(cfg):
        return "desligado"
    cab = {"TTL": str(ttl), "Urgency": urgencia, "Authorization": cabecalho_vapid(cfg, endpoint), "Content-Length": "0"}
    try:
        st, _ = http("POST", endpoint, cab, b"")
    except Exception:
        return "falha"
    if st in (404, 410):
        return "expirada"
    return "ok" if 200 <= st < 300 else "falha"
