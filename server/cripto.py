"""Criptografia do Agora — só biblioteca padrão, conferida contra vetores oficiais.

  ChaCha20-Poly1305 (RFC 8439) .... cifra os dados de saúde guardados no banco e os backups
  TOTP (RFC 6238) ................. verificação em duas etapas de profissionais e administradores
  ECDSA P-256 / ES256 (RFC 7518) .. assinatura VAPID das notificações Web Push

Se o pacote `cryptography` estiver instalado, a cifra usa a implementação dele
(mesmo formato, muito mais rápida). Sem ele, roda a implementação em Python
abaixo, que os testes comparam com os vetores da RFC e com a biblioteca.
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time

try:  # aceleração opcional, mesmo formato de saída
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305 as _CC20
except Exception:  # pragma: no cover - depende do ambiente
    _CC20 = None

M32 = 0xFFFFFFFF


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def de_b64u(s):
    s = s.encode() if isinstance(s, str) else s
    return base64.urlsafe_b64decode(s + b"=" * (-len(s) % 4))


# ------------------------------------------------------------------ ChaCha20-Poly1305
def _rotl(v, c):
    return ((v << c) & M32) | (v >> (32 - c))


def _bloco(k, contador, n):
    st = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574, *k, contador & M32, *n]
    w = st[:]
    for _ in range(10):
        for a, b, c, d in ((0, 4, 8, 12), (1, 5, 9, 13), (2, 6, 10, 14), (3, 7, 11, 15),
                           (0, 5, 10, 15), (1, 6, 11, 12), (2, 7, 8, 13), (3, 4, 9, 14)):
            w[a] = (w[a] + w[b]) & M32; w[d] = _rotl(w[d] ^ w[a], 16)
            w[c] = (w[c] + w[d]) & M32; w[b] = _rotl(w[b] ^ w[c], 12)
            w[a] = (w[a] + w[b]) & M32; w[d] = _rotl(w[d] ^ w[a], 8)
            w[c] = (w[c] + w[d]) & M32; w[b] = _rotl(w[b] ^ w[c], 7)
    return struct.pack("<16I", *[(w[i] + st[i]) & M32 for i in range(16)])


def chacha20(chave, contador, nonce, dados):
    k = struct.unpack("<8I", chave)
    n = struct.unpack("<3I", nonce)
    out = bytearray()
    for i in range(0, len(dados), 64):
        parte = dados[i:i + 64]
        ks = _bloco(k, contador + i // 64, n)[:len(parte)]
        out += (int.from_bytes(parte, "little") ^ int.from_bytes(ks, "little")).to_bytes(len(parte), "little")
    return bytes(out)


def poly1305(chave, msg):
    r = int.from_bytes(chave[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(chave[16:32], "little")
    p, acc = (1 << 130) - 5, 0
    for i in range(0, len(msg), 16):
        acc = ((acc + int.from_bytes(msg[i:i + 16] + b"\x01", "little")) * r) % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(b):
    return b"\x00" * (-len(b) % 16)


def _mac(chave, nonce, aad, ct):
    otk = _bloco(struct.unpack("<8I", chave), 0, struct.unpack("<3I", nonce))[:32]
    return poly1305(otk, aad + _pad16(aad) + ct + _pad16(ct) + struct.pack("<QQ", len(aad), len(ct)))


def aead_cifrar(chave, nonce, texto, aad=b"", puro=False):
    if _CC20 and not puro:
        return _CC20(chave).encrypt(nonce, texto, aad or None)
    ct = chacha20(chave, 1, nonce, texto)
    return ct + _mac(chave, nonce, aad, ct)


def aead_decifrar(chave, nonce, dados, aad=b"", puro=False):
    if _CC20 and not puro:
        try:
            return _CC20(chave).decrypt(nonce, dados, aad or None)
        except Exception:
            raise ValueError("autenticação falhou")
    ct, tag = dados[:-16], dados[-16:]
    if not hmac.compare_digest(_mac(chave, nonce, aad, ct), tag):
        raise ValueError("autenticação falhou")
    return chacha20(chave, 1, nonce, ct)


class Cofre:
    """Cifra campos do banco. Formato: c1.<id da chave>.<base64url(nonce|cifrado|tag)>.

    A chave atual cifra; as antigas (rotação) continuam decifrando. Texto que não
    começa com "c1." é tratado como legado em claro e devolvido como está, o que
    permite migrar bancos antigos sem parar o serviço."""

    PREFIXO = "c1."

    def __init__(self, chave, antigas=()):
        if len(chave) != 32:
            raise ValueError("A chave precisa ter 32 bytes.")
        self.chaves = {self.ident(chave): chave}
        for k in antigas:
            self.chaves[self.ident(k)] = k
        self.atual = self.ident(chave)

    @staticmethod
    def ident(chave):
        return hashlib.sha256(b"agora-chave:" + chave).hexdigest()[:8]

    def cifrar(self, texto, contexto=""):
        if texto is None:
            return None
        bruto = texto.encode() if isinstance(texto, str) else texto
        nonce = os.urandom(12)
        ct = aead_cifrar(self.chaves[self.atual], nonce, bruto, contexto.encode())
        return f"{self.PREFIXO}{self.atual}.{b64u(nonce + ct)}"

    def decifrar(self, valor, contexto=""):
        if valor is None or not str(valor).startswith(self.PREFIXO):
            return valor
        _, kid, corpo = valor.split(".", 2)
        if kid not in self.chaves:
            raise ValueError("Chave de criptografia desconhecida: confira AGORA_CHAVE e AGORA_CHAVES_ANTIGAS.")
        b = de_b64u(corpo)
        return aead_decifrar(self.chaves[kid], b[:12], b[12:], contexto.encode()).decode()

    def derivar(self, rotulo):
        """Subchave para outro uso (links assinados etc.), sem expor a chave principal."""
        return hmac.new(self.chaves[self.atual], b"agora-derivar:" + rotulo, hashlib.sha256).digest()

    def cifrado(self, valor):
        return isinstance(valor, str) and valor.startswith(self.PREFIXO)

    def precisa_recifrar(self, valor):
        return self.cifrado(valor) and valor.split(".", 2)[1] != self.atual

    # arquivos inteiros (backup): cabeçalho + blocos de 1 MiB, cada um autenticado
    def cifrar_arquivo(self, origem, destino, bloco=1 << 20):
        chave = self.chaves[self.atual]
        base = os.urandom(8)
        with open(origem, "rb") as fi, open(destino, "wb") as fo:
            fo.write(b"AGORABK1" + self.atual.encode() + base)
            i = 0
            while True:
                parte = fi.read(bloco)
                fim = len(parte) < bloco
                nonce = base + struct.pack(">I", i)
                ct = aead_cifrar(chave, nonce, parte, b"fim" if fim else b"meio")
                fo.write(struct.pack(">I", len(ct)) + ct)
                i += 1
                if fim:
                    break

    def decifrar_arquivo(self, origem, destino):
        with open(origem, "rb") as fi, open(destino, "wb") as fo:
            cab = fi.read(24)
            if cab[:8] != b"AGORABK1":
                raise ValueError("Não é um backup cifrado do Agora.")
            kid, base = cab[8:16].decode(), cab[16:24]
            if kid not in self.chaves:
                raise ValueError("Este backup foi cifrado com outra chave.")
            chave, i, fim = self.chaves[kid], 0, False
            while not fim:
                t = fi.read(4)
                if len(t) < 4:
                    raise ValueError("Backup truncado.")
                ct = fi.read(struct.unpack(">I", t)[0])
                nonce = base + struct.pack(">I", i)
                try:
                    pt, fim = aead_decifrar(chave, nonce, ct, b"fim"), True
                except ValueError:
                    pt = aead_decifrar(chave, nonce, ct, b"meio")
                fo.write(pt)
                i += 1


def chave_de_texto(txt):
    """Aceita a chave em base64 (padrão), base64url ou hexadecimal."""
    txt = (txt or "").strip()
    for f in (lambda s: base64.b64decode(s, validate=True), de_b64u, bytes.fromhex):
        try:
            k = f(txt)
            if len(k) == 32:
                return k
        except Exception:
            pass
    raise ValueError("AGORA_CHAVE inválida: gere uma com  python3 server/admin.py chave")


def nova_chave_texto():
    return base64.b64encode(os.urandom(32)).decode()


# ------------------------------------------------------------------ TOTP
B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def novo_segredo_totp():
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def hotp(segredo_bytes, contador, digitos=6, alg=hashlib.sha1):
    h = hmac.new(segredo_bytes, struct.pack(">Q", contador), alg).digest()
    o = h[-1] & 0x0F
    n = struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF
    return str(n % (10 ** digitos)).zfill(digitos)


def _seg(segredo_b32):
    s = segredo_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def totp(segredo_b32, quando=None, passo=30, digitos=6):
    return hotp(_seg(segredo_b32), int((quando or time.time()) // passo), digitos)


def confere_totp(segredo_b32, codigo, ultimo_contador=0, quando=None, janela=1, passo=30):
    """Devolve o contador aceito (para impedir reuso do mesmo código) ou 0."""
    codigo = "".join(c for c in str(codigo) if c.isdigit())
    if len(codigo) != 6:
        return 0
    atual = int((quando or time.time()) // passo)
    k = _seg(segredo_b32)
    for c in range(atual - janela, atual + janela + 1):
        if c > ultimo_contador and hmac.compare_digest(hotp(k, c), codigo):
            return c
    return 0


def uri_totp(segredo_b32, conta, emissor="Agora"):
    from urllib.parse import quote
    return f"otpauth://totp/{quote(emissor)}:{quote(conta)}?secret={segredo_b32}&issuer={quote(emissor)}&algorithm=SHA1&digits=6&period=30"


def codigos_recuperacao(n=8):
    alfa = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ["".join(secrets.choice(alfa) for _ in range(4)) + "-" + "".join(secrets.choice(alfa) for _ in range(4)) for _ in range(n)]


def hash_codigo(c):
    return hashlib.sha256(("agora-rec:" + c.strip().upper()).encode()).hexdigest()


# ------------------------------------------------------------------ ECDSA P-256 (ES256)
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _soma(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        m = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (m * m - x1 - x2) % P
    return x3, (m * (x1 - x3) - y1) % P


def _mult(k, ponto=G):
    r, q = None, ponto
    while k:
        if k & 1:
            r = _soma(r, q)
        q = _soma(q, q)
        k >>= 1
    return r


def no_curva(pt):
    x, y = pt
    return (y * y - (x * x * x + A * x + B)) % P == 0


def nova_chave_ec():
    d = secrets.randbelow(N - 1) + 1
    return d, _mult(d)


def publica_bytes(pub):
    return b"\x04" + pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")


def assinar_es256(d, msg):
    z = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    while True:
        k = secrets.randbelow(N - 1) + 1
        r = _mult(k)[0] % N
        if not r:
            continue
        s = pow(k, -1, N) * (z + r * d) % N
        if s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verificar_es256(pub, msg, assinatura):
    r, s = int.from_bytes(assinatura[:32], "big"), int.from_bytes(assinatura[32:], "big")
    if not (0 < r < N and 0 < s < N):
        return False
    z = int.from_bytes(hashlib.sha256(msg).digest(), "big")
    w = pow(s, -1, N)
    pt = _soma(_mult(z * w % N), _mult(r * w % N, pub))
    return pt is not None and pt[0] % N == r


def jwt_es256(d, claims):
    import json
    cab = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    corpo = b64u(json.dumps(claims, separators=(",", ":")).encode())
    ass = assinar_es256(d, f"{cab}.{corpo}".encode())
    return f"{cab}.{corpo}.{b64u(ass)}"


def spki_der_p256(pub):
    """Chave pública em DER (SubjectPublicKeyInfo), para conferir com o OpenSSL nos testes."""
    return bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200") + publica_bytes(pub)
