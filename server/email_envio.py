"""Envio de e-mail (recuperação de senha, avisos de cobrança) só com a biblioteca padrão.

Sem SMTP configurado (desenvolvimento), a mensagem vai para a tabela caixa_saida e
para o terminal, para que dê para testar o fluxo inteiro sem servidor de e-mail.
"""
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import make_msgid


def enviar(cfg, con, para, assunto, texto, descadastro=None):
    if not cfg.smtp_host:
        con.execute("INSERT INTO caixa_saida(para,assunto,texto,criado_em) VALUES (?,?,?,datetime('now'))",
                    (para, assunto, texto))
        sys.stderr.write(f"[e-mail não enviado: SMTP não configurado] para={para} assunto={assunto}\n")
        return False
    msg = EmailMessage()
    msg["From"] = cfg.smtp_remetente
    msg["To"] = para
    msg["Subject"] = assunto
    msg["Message-ID"] = make_msgid(domain="agora")
    if descadastro:  # e-mail de relacionamento: descadastro em um clique (RFC 8058)
        msg["List-Unsubscribe"] = f"<{descadastro}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(texto)
    ctx = ssl.create_default_context()
    if cfg.smtp_porta == 465:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_porta, context=ctx, timeout=20) as s:
            if cfg.smtp_usuario:
                s.login(cfg.smtp_usuario, cfg.smtp_senha)
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_porta, timeout=20) as s:
            s.starttls(context=ctx)
            if cfg.smtp_usuario:
                s.login(cfg.smtp_usuario, cfg.smtp_senha)
            s.send_message(msg)
    return True
