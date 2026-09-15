# -*- coding: utf-8 -*-
"""Envio de e-mails NÃO relacionados à segurança de autenticação (boas-vindas).

Os e-mails de segurança (confirmação de conta, código de recuperação de senha) são
enviados pelo próprio Supabase Auth — nunca por este módulo — porque só o Supabase gera
e valida o token/OTP correspondente (ver `auth/README.md`, seção 4).

Este módulo reaproveita o MESMO relay SMTP (Gmail) já configurado em `st.secrets` para o
recurso de tickets de suporte em `streamlit_app.py` (`EMAIL_SISTEMA`/`SENHA_APP`), só que
para o e-mail de boas-vindas pós-cadastro, onde total controle de marca/conteúdo importa.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

logger = logging.getLogger(__name__)

_SMTP_SERVER = "smtp.gmail.com"
_SMTP_PORT = 587


def _credenciais_smtp() -> tuple[str, str] | None:
    _user = st.secrets.get("EMAIL_SISTEMA", "")
    _pass = st.secrets.get("SENHA_APP", "")
    if not _user or not _pass or _user == "seu_email_de_envio@gmail.com":
        return None
    return _user, _pass


def enviar_boas_vindas(destinatario: str, nome: str) -> bool:
    """Envia o e-mail de boas-vindas pós-cadastro. NUNCA lança — falha graciosamente
    (loga e retorna False) porque um problema no envio de e-mail de marketing/cortesia
    não deve impedir o usuário de concluir o cadastro (que já foi persistido no Supabase
    antes desta chamada)."""
    _cred = _credenciais_smtp()
    if _cred is None:
        logger.info("[AUTH-EMAIL] SMTP não configurado — e-mail de boas-vindas não enviado.")
        return False
    _smtp_user, _smtp_pass = _cred

    _texto = (
        f"Olá, {nome}!\n\n"
        "Sua conta no Motor Nacional de Inteligência Logística foi criada com sucesso.\n"
        f"Você já pode entrar com o e-mail {destinatario} e a senha cadastrada.\n\n"
        "Se você não reconhece este cadastro, ignore este e-mail.\n"
    )
    _html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#1f2937;">
  <h2 style="color:#111827;">Bem-vindo(a), {nome}!</h2>
  <p>Sua conta no <strong>Motor Nacional de Inteligência Logística</strong> foi criada com sucesso.</p>
  <p>Você já pode entrar com o e-mail <strong>{destinatario}</strong> e a senha cadastrada.</p>
  <p style="color:#6b7280;font-size:12px;margin-top:24px;">
    Se você não reconhece este cadastro, ignore este e-mail.
  </p>
</body></html>"""

    try:
        _msg = MIMEMultipart("alternative")
        _msg["From"] = _smtp_user
        _msg["To"] = destinatario
        _msg["Subject"] = "Bem-vindo ao Motor Nacional de Inteligência Logística"
        _msg.attach(MIMEText(_texto, "plain"))
        _msg.attach(MIMEText(_html, "html"))

        _server = smtplib.SMTP(_SMTP_SERVER, _SMTP_PORT)
        try:
            _server.starttls()
            _server.login(_smtp_user, _smtp_pass)
            _server.send_message(_msg)
        finally:
            _server.quit()
        return True
    except Exception:
        logger.warning("[AUTH-EMAIL] Falha ao enviar e-mail de boas-vindas (não bloqueia o cadastro).",
                       exc_info=True)
        return False


def enviar_notificacao_compartilhamento(destinatario: str, remetente_nome: str, remetente_email: str,
                                        estudo_nome: str, mensagem: str = "") -> bool:
    """[COMPARTILHAR - 448ª geração] Notifica por e-mail o destinatário de que um estudo foi
    compartilhado com ele. NUNCA lança — o compartilhamento em si já foi persistido antes desta
    chamada; falha de e-mail (cortesia) não deve derrubar a operação. Retorna True se enviou."""
    _cred = _credenciais_smtp()
    if _cred is None:
        logger.info("[AUTH-EMAIL] SMTP não configurado — notificação de compartilhamento não enviada.")
        return False
    _smtp_user, _smtp_pass = _cred
    _quem = (remetente_nome or "").strip() or (remetente_email or "").strip() or "Um usuário"
    _est = (estudo_nome or "Estudo").strip()
    _msg_extra = (mensagem or "").strip()

    _texto = (
        f"Olá!\n\n"
        f"{_quem} compartilhou com você o estudo \"{_est}\" no Motor Nacional de "
        f"Inteligência Logística para Exames.\n\n"
        + (f"Mensagem de {_quem}: {_msg_extra}\n\n" if _msg_extra else "")
        + "Para ver e baixar o estudo, entre na aplicação com este e-mail e abra o menu do seu "
        "Perfil → seção \"Estudos recebidos\".\n\n"
        "Se você não esperava este compartilhamento, ignore este e-mail.\n"
    )
    import html as _he
    _msg_html = (f'<p style="background:#f3f4f6;border-left:3px solid #2563eb;padding:10px 14px;'
                 f'border-radius:6px;color:#374151;">💬 {_he.escape(_msg_extra)}</p>') if _msg_extra else ""
    _html = f"""\
<html><body style="font-family:Arial,sans-serif;color:#1f2937;">
  <h2 style="color:#111827;">📥 Você recebeu um estudo</h2>
  <p><strong>{_he.escape(_quem)}</strong> compartilhou com você o estudo
     <strong>"{_he.escape(_est)}"</strong> no <strong>Motor Nacional de Inteligência Logística
     para Exames</strong>.</p>
  {_msg_html}
  <p>Para ver e baixar, entre na aplicação com este e-mail e abra
     <strong>Perfil → Estudos recebidos</strong>.</p>
  <p style="color:#6b7280;font-size:12px;margin-top:24px;">
    Se você não esperava este compartilhamento, ignore este e-mail.
  </p>
</body></html>"""

    try:
        _msg = MIMEMultipart("alternative")
        _msg["From"] = _smtp_user
        _msg["To"] = destinatario
        _msg["Subject"] = f'{_quem} compartilhou um estudo com você'
        _msg.attach(MIMEText(_texto, "plain"))
        _msg.attach(MIMEText(_html, "html"))

        _server = smtplib.SMTP(_SMTP_SERVER, _SMTP_PORT)
        try:
            _server.starttls()
            _server.login(_smtp_user, _smtp_pass)
            _server.send_message(_msg)
        finally:
            _server.quit()
        return True
    except Exception:
        logger.warning("[AUTH-EMAIL] Falha ao enviar notificação de compartilhamento (não bloqueia a operação).",
                       exc_info=True)
        return False
