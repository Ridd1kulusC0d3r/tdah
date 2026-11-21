"""Configuração do Agora TDAH lida de variáveis de ambiente (ou de um arquivo .env).

Tudo tem um padrão seguro para desenvolvimento local. Em produção, preencha o .env
(veja .env.example na raiz do projeto).
"""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_dotenv():
    """Lê RAIZ/.env (formato CHAVE=valor) sem sobrescrever o ambiente já definido."""
    arq = Path(os.environ.get("AGORA_ENV_ARQUIVO", RAIZ / ".env"))
    if not arq.is_file():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_carregar_dotenv()


def env(nome, padrao=""):
    return os.environ.get(nome, padrao)


def env_int(nome, padrao):
    try:
        return int(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


class Config:
    """Snapshot da configuração. Testes criam instâncias com valores próprios."""

    def __init__(self, **extra):
        self.url_publica = env("AGORA_URL_PUBLICA", "http://localhost:8765").rstrip("/")
        self.ambiente = env("AGORA_AMBIENTE", "desenvolvimento")  # desenvolvimento | producao
        self.atras_de_proxy = env("AGORA_ATRAS_DE_PROXY", "0") == "1"
        self.limite_registro = env_int("AGORA_LIMITE_REGISTRO", 20)  # contas novas por IP por hora
        self.cors = [o.strip() for o in env("AGORA_CORS", "https://localhost,capacitor://localhost,http://localhost").split(",") if o.strip()]
        # pagamentos
        self.provedor = env("AGORA_PAGAMENTO", "simulado")  # simulado | mercadopago | stripe
        self.mp_token = env("MP_ACCESS_TOKEN")
        self.mp_segredo_webhook = env("MP_WEBHOOK_SECRET")
        self.stripe_chave = env("STRIPE_SECRET_KEY")
        self.stripe_segredo_webhook = env("STRIPE_WEBHOOK_SECRET")
        self.stripe_versao = env("STRIPE_API_VERSION", "")
        self.preco_plus_mensal = env_int("AGORA_PRECO_PLUS_MENSAL", 990)
        self.preco_plus_anual = env_int("AGORA_PRECO_PLUS_ANUAL", 8900)
        self.preco_pro_mensal = env_int("AGORA_PRECO_PRO_MENSAL", 6900)
        self.pro_gratis_pacientes = env_int("AGORA_PRO_GRATIS_PACIENTES", 3)
        # Google Play
        self.play_pacote = env("PLAY_PACOTE", "br.com.agoratdah.app")
        self.play_conta_servico = env("PLAY_CONTA_SERVICO_JSON")  # caminho do JSON da conta de serviço
        self.play_token_rtdn = env("PLAY_RTDN_TOKEN")
        self.play_produtos = dict(
            p.split(":", 1) for p in env("PLAY_PRODUTOS", "agora_plus_mensal:plus_mensal,agora_plus_anual:plus_anual").split(",") if ":" in p)
        # e-mail
        self.smtp_host = env("AGORA_SMTP_HOST")
        self.smtp_porta = env_int("AGORA_SMTP_PORTA", 587)
        self.smtp_usuario = env("AGORA_SMTP_USUARIO")
        self.smtp_senha = env("AGORA_SMTP_SENHA")
        self.smtp_remetente = env("AGORA_SMTP_REMETENTE", "Agora TDAH <nao-responda@localhost>")
        # criptografia dos dados guardados (obrigatória em produção)
        self.chave = env("AGORA_CHAVE")
        self.chaves_antigas = [c for c in env("AGORA_CHAVES_ANTIGAS").split(",") if c.strip()]
        # Em produção a cifra usa a biblioteca mantida `cryptography`. A implementação em Python puro existe
        # para desenvolvimento e testes; liberar em produção só com esta variável (não recomendado).
        self.permitir_cifra_python = env("AGORA_PERMITIR_CIFRA_PYTHON", "0") == "1"
        # responsável técnico (aparece em todo serviço psicológico anunciado)
        self.responsavel_nome = env("AGORA_RESPONSAVEL_NOME", "Deivison Mendes")
        self.responsavel_crp = env("AGORA_RESPONSAVEL_CRP", "CRP-04/65709")
        self.contato_publico = env("AGORA_CONTATO_PUBLICO", "contato@psicologotech.com.br")
        # segurança
        self.exigir_2fa_admin = env("AGORA_EXIGIR_2FA_ADMIN", "1") == "1"
        self.retencao_meses = env_int("AGORA_RETENCAO_MESES", 24)  # contatos de interesse sem resposta
        self.alerta_email = env("AGORA_ALERTA_EMAIL")              # recebe aviso de erro interno
        # Web Push (gere com: python3 server/admin.py vapid)
        self.vapid_privada = env("AGORA_VAPID_PRIVADA")
        self.vapid_publica = env("AGORA_VAPID_PUBLICA")
        self.vapid_contato = env("AGORA_VAPID_CONTATO", "mailto:contato@psicologotech.com.br")
        # backup externo compatível com S3 (AWS, Backblaze B2, Cloudflare R2, Wasabi...)
        self.s3_endpoint = env("AGORA_S3_ENDPOINT")  # ex.: https://s3.us-east-005.backblazeb2.com
        self.s3_regiao = env("AGORA_S3_REGIAO", "us-east-1")
        self.s3_bucket = env("AGORA_S3_BUCKET")
        self.s3_chave = env("AGORA_S3_CHAVE")
        self.s3_segredo = env("AGORA_S3_SEGREDO")
        # conteúdo
        self.ebooks_dir = env("AGORA_EBOOKS_DIR", str(RAIZ / "dados" / "ebooks"))
        self.agendador = env("AGORA_AGENDADOR", "1") == "1"  # lembretes, e-mails e retenção dentro do servidor
        for k, v in extra.items():
            setattr(self, k, v)

    @property
    def producao(self):
        return self.ambiente == "producao"

    def cofre(self, pasta_dados):
        """Cofre de criptografia. Em produção exige AGORA_CHAVE; fora dela cria uma chave local."""
        import cripto
        antigas = [cripto.chave_de_texto(c) for c in self.chaves_antigas]
        if self.producao and cripto._CC20 is None and not self.permitir_cifra_python:
            raise SystemExit("Produção exige o pacote cryptography (biblioteca mantida e auditada). Instale com:  pip install cryptography")
        if self.chave:
            return cripto.Cofre(cripto.chave_de_texto(self.chave), antigas)
        if self.producao:
            raise SystemExit("AGORA_CHAVE não configurada. Gere com:  python3 server/admin.py chave  e coloque no .env")
        arq = Path(pasta_dados) / ".chave-desenvolvimento"
        if not arq.is_file():
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(cripto.nova_chave_texto())
            try:
                os.chmod(arq, 0o600)
            except OSError:
                pass
        return cripto.Cofre(cripto.chave_de_texto(arq.read_text()), antigas)

    def avisos_producao(self):
        """Lista o que falta para ligar em produção com segurança."""
        faltas = []
        if not self.chave:
            faltas.append("AGORA_CHAVE (criptografia dos dados)")
        try:
            import cripto
            if cripto._CC20 is None and not self.permitir_cifra_python:
                faltas.append("pacote cryptography (pip install cryptography)")
        except Exception:
            pass
        if not self.url_publica.startswith("https://"):
            faltas.append("AGORA_URL_PUBLICA com https://")
        if self.provedor == "simulado":
            faltas.append("AGORA_PAGAMENTO=mercadopago ou stripe")
        if self.provedor == "mercadopago" and not (self.mp_token and self.mp_segredo_webhook):
            faltas.append("MP_ACCESS_TOKEN e MP_WEBHOOK_SECRET")
        if self.provedor == "stripe" and not (self.stripe_chave and self.stripe_segredo_webhook):
            faltas.append("STRIPE_SECRET_KEY e STRIPE_WEBHOOK_SECRET")
        if not self.smtp_host:
            faltas.append("AGORA_SMTP_HOST (e-mails de senha e de turmas)")
        if not (self.vapid_privada and self.vapid_publica):
            faltas.append("AGORA_VAPID_PRIVADA/PUBLICA (lembretes no navegador) — opcional")
        if not self.s3_bucket:
            faltas.append("AGORA_S3_* (cópia do backup fora do servidor) — recomendado")
        return faltas

    def simulado_permitido(self):
        return self.provedor == "simulado" and not self.producao
