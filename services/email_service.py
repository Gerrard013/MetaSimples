import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_email_token(email: str) -> str:
    return _serializer().dumps(email, salt='email-confirmation')


def confirm_email_token(token: str, max_age: int = 86400):
    try:
        return _serializer().loads(
            token,
            salt='email-confirmation',
            max_age=max_age,
        )
    except SignatureExpired:
        return None
    except BadSignature:
        return None


def _build_sender() -> tuple[str, str]:
    from_name = current_app.config.get('MAIL_FROM_NAME', 'MetaSimples')
    from_email = current_app.config.get('MAIL_FROM_EMAIL') or current_app.config.get('MAIL_USERNAME')

    header_sender = f'{from_name} <{from_email}>'
    return header_sender, from_email


def send_email(
    subject: str,
    recipient: str,
    html_body: str,
    text_body: str = '',
) -> tuple[bool, str]:
    if not current_app.config.get('MAIL_ENABLED'):
        return False, 'Envio de e-mail desativado por configuração.'

    host = current_app.config.get('MAIL_HOST')
    port = int(current_app.config.get('MAIL_PORT') or 587)
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    use_ssl = current_app.config.get('MAIL_USE_SSL', False)

    sender_header, envelope_sender = _build_sender()

    if not all([host, port, username, password, envelope_sender]):
        return False, 'Configuração SMTP incompleta.'

    message = MIMEMultipart('alternative')
    message['Subject'] = subject
    message['From'] = sender_header
    message['To'] = recipient

    if text_body:
        message.attach(MIMEText(text_body, 'plain', 'utf-8'))

    message.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        if use_ssl:
            context = ssl.create_default_context()

            with smtplib.SMTP_SSL(host, port, context=context, timeout=25) as server:
                server.login(username, password)
                server.sendmail(envelope_sender, [recipient], message.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=25) as server:
                server.ehlo()

                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()

                server.login(username, password)
                server.sendmail(envelope_sender, [recipient], message.as_string())

        return True, 'E-mail enviado com sucesso.'

    except Exception as exc:
        current_app.logger.exception('Falha ao enviar e-mail para %s', recipient)
        return False, str(exc)


def send_confirmation_email(user) -> tuple[bool, str]:
    app_name = current_app.config.get('APP_NAME', 'MetaSimples')
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '')
    token = generate_email_token(user.email)

    confirm_url = url_for(
        'auth.confirm_email',
        token=token,
        _external=True,
    )

    subject = f'Confirme seu cadastro | {app_name}'

    text_body = f"""
Olá, {user.name}!

Para ativar sua conta no {app_name}, confirme seu e-mail acessando o link abaixo:

{confirm_url}

Este link expira em 24 horas.

Suporte WhatsApp: {support_whatsapp or 'Não informado'}

Equipe {app_name}
""".strip()

    html_body = f"""
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color: #111827; line-height: 1.6; background: #f3f4f6; padding: 24px;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; padding: 28px; border-radius: 16px;">
          <h2 style="margin: 0 0 8px 0;">Confirme seu cadastro</h2>

          <p>Olá, <strong>{user.name}</strong>!</p>

          <p>
            Recebemos seu cadastro no <strong>{app_name}</strong>.
            Para liberar seu acesso, confirme seu e-mail clicando no botão abaixo.
          </p>

          <p style="margin: 28px 0;">
            <a href="{confirm_url}" style="display:inline-block;padding:14px 20px;background:#111827;color:#ffffff;text-decoration:none;border-radius:10px;font-weight:bold;">
              Confirmar meu e-mail
            </a>
          </p>

          <p style="font-size: 14px; color: #4b5563;">
            Se o botão não funcionar, copie e cole este link no navegador:
          </p>

          <p style="font-size: 13px; word-break: break-all;">
            <a href="{confirm_url}">{confirm_url}</a>
          </p>

          <div style="background:#f9fafb;border-radius:12px;padding:16px;margin-top:20px;">
            <p style="margin:0;">
              <strong>Suporte WhatsApp:</strong> {support_whatsapp or 'Não informado'}
            </p>
          </div>

          <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;">

          <p style="font-size: 13px; color: #6b7280;">
            Este link expira em 24 horas.
          </p>

          <p style="font-size: 13px; color: #6b7280;">
            Equipe {app_name}
          </p>
        </div>
      </body>
    </html>
    """

    return send_email(
        subject=subject,
        recipient=user.email,
        html_body=html_body,
        text_body=text_body,
    )