"""Envio de arquivos para armazenamento compatível com S3 (assinatura AWS SigV4), só biblioteca padrão.

Serve para AWS S3, Backblaze B2, Cloudflare R2, Wasabi, MinIO. O backup sai do
servidor já cifrado pelo Cofre: o provedor de armazenamento não consegue lê-lo.
"""
import hashlib
import hmac
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _h(chave, msg):
    return hmac.new(chave, msg.encode(), hashlib.sha256).digest()


def chave_assinatura(segredo, data, regiao, servico):
    k = _h(("AWS4" + segredo).encode(), data)
    k = _h(k, regiao)
    k = _h(k, servico)
    return _h(k, "aws4_request")


def assinar(metodo, url, regiao, chave, segredo, corpo_hash, agora=None, servico="s3", extra=None):
    """Devolve os cabeçalhos assinados para a requisição."""
    agora = agora or datetime.now(timezone.utc)
    amz = agora.strftime("%Y%m%dT%H%M%SZ")
    data = amz[:8]
    u = urllib.parse.urlsplit(url)
    cab = {"host": u.netloc, "x-amz-content-sha256": corpo_hash, "x-amz-date": amz}
    cab.update({k.lower(): v for k, v in (extra or {}).items()})
    nomes = sorted(cab)
    canonico_cab = "".join(f"{k}:{str(cab[k]).strip()}\n" for k in nomes)
    assinados = ";".join(nomes)
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
    canonico_q = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}" for k, v in sorted(q))
    caminho = urllib.parse.quote(urllib.parse.unquote(u.path or "/"), safe="/-_.~")
    pedido = "\n".join([metodo, caminho, canonico_q, canonico_cab, assinados, corpo_hash])
    escopo = f"{data}/{regiao}/{servico}/aws4_request"
    texto = "\n".join(["AWS4-HMAC-SHA256", amz, escopo, hashlib.sha256(pedido.encode()).hexdigest()])
    ass = hmac.new(chave_assinatura(segredo, data, regiao, servico), texto.encode(), hashlib.sha256).hexdigest()
    cab["authorization"] = f"AWS4-HMAC-SHA256 Credential={chave}/{escopo}, SignedHeaders={assinados}, Signature={ass}"
    return cab


def _url(cfg, nome):
    base = cfg.s3_endpoint.rstrip("/") if cfg.s3_endpoint else f"https://s3.{cfg.s3_regiao}.amazonaws.com"
    return f"{base}/{cfg.s3_bucket}/{urllib.parse.quote(nome)}"


def enviar(cfg, caminho_arquivo, nome, abrir=urllib.request.urlopen):
    dados = open(caminho_arquivo, "rb").read()
    url = _url(cfg, nome)
    cab = assinar("PUT", url, cfg.s3_regiao, cfg.s3_chave, cfg.s3_segredo, hashlib.sha256(dados).hexdigest(),
                  extra={"content-type": "application/octet-stream"})
    req = urllib.request.Request(url, data=dados, method="PUT", headers=cab)
    with abrir(req, timeout=120) as r:
        return r.status


def baixar(cfg, nome, destino, abrir=urllib.request.urlopen):
    url = _url(cfg, nome)
    cab = assinar("GET", url, cfg.s3_regiao, cfg.s3_chave, cfg.s3_segredo, hashlib.sha256(b"").hexdigest())
    with abrir(urllib.request.Request(url, headers=cab), timeout=120) as r, open(destino, "wb") as f:
        f.write(r.read())
    return destino
