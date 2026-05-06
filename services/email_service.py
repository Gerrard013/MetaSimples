import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_email_token(email: str) -> str:
    return _serializer().dumps(email, salt='email-confirmation')


def confirm_email_token(token: str, max_age: int = 86400):
    try:
        return _serializer().loads(token, salt='email-confirmation', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None


def generate_password_reset_token(email: str) -> str:
    return _serializer().dumps(email, salt='password-reset')


def reset_password_token_email(token: str, max_age: int = 3600):
    try:
        return _serializer().loads(token, salt='password-reset', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None


def _build_sender() -> tuple[str, str]:
    from_name = current_app.config.get('MAIL_FROM_NAME', 'MetaSimples')
    from_email = (
        current_app.config.get('MAIL_FROM_EMAIL')
        or current_app.config.get('MAIL_USERNAME')
        or 'onboarding@resend.dev'
    )
    return f'{from_name} <{from_email}>', from_email


def send_email_resend(subject: str, recipient: str, html_body: str, text_body: str = '') -> tuple[bool, str]:
    api_key = current_app.config.get('RESEND_API_KEY')
    sender_header, _ = _build_sender()

    if not api_key:
        return False, 'RESEND_API_KEY não configurada.'

    payload = {
        'from': sender_header,
        'to': [recipient],
        'subject': subject,
        'html': html_body,
    }

    if text_body:
        payload['text'] = text_body

    try:
        response = requests.post(
            'https://api.resend.com/emails',
            json=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=8,
        )

        if response.status_code >= 400:
            current_app.logger.error('Erro Resend %s: %s', response.status_code, response.text)
            return False, f'Erro Resend: {response.status_code} - {response.text}'

        return True, 'E-mail enviado com sucesso via Resend.'

    except requests.RequestException as exc:
        current_app.logger.exception('Falha HTTP Resend ao enviar e-mail para %s', recipient)
        return False, str(exc)


def send_email_smtp(subject: str, recipient: str, html_body: str, text_body: str = '') -> tuple[bool, str]:
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

            with smtplib.SMTP_SSL(host, port, context=context, timeout=5) as server:
                server.login(username, password)
                server.sendmail(envelope_sender, [recipient], message.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=5) as server:
                server.ehlo()

                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()

                server.login(username, password)
                server.sendmail(envelope_sender, [recipient], message.as_string())

        return True, 'E-mail enviado com sucesso via SMTP.'

    except Exception as exc:
        current_app.logger.exception('Falha ao enviar e-mail SMTP para %s', recipient)
        return False, str(exc)


def send_email(subject: str, recipient: str, html_body: str, text_body: str = '') -> tuple[bool, str]:
    if not current_app.config.get('MAIL_ENABLED'):
        return False, 'Envio de e-mail desativado por configuração.'

    provider = current_app.config.get('EMAIL_PROVIDER', 'resend').lower().strip()

    if provider == 'resend':
        return send_email_resend(subject, recipient, html_body, text_body)

    return send_email_smtp(subject, recipient, html_body, text_body)


def send_confirmation_email(user) -> tuple[bool, str]:
    app_name = current_app.config.get('APP_NAME', 'MetaSimples')
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '')
    token = generate_email_token(user.email)
    confirm_url = url_for('auth.confirm_email', token=token, _external=True)
    subject = f'Confirme seu cadastro | {app_name}'

    text_body = f'''
Olá, {user.name}!

Para ativar sua conta no {app_name}, confirme seu e-mail acessando o link abaixo:

{confirm_url}

Este link expira em 24 horas.

Suporte WhatsApp: {support_whatsapp or 'Não informado'}

Equipe {app_name}
'''.strip()

    html_body = f'''
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color: #111827; line-height: 1.6; background: #f3f4f6; padding: 24px;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; padding: 28px; border-radius: 16px;">
          <div style="font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#0ea5e9;">G Tech Innovation & Solutions</div>
          <h2 style="margin: 10px 0 8px 0;">Confirme seu cadastro</h2>
          <p>Olá, <strong>{user.name}</strong>!</p>
          <p>Recebemos seu cadastro no <strong>{app_name}</strong>. Para liberar seu acesso, confirme seu e-mail clicando no botão abaixo.</p>
          <p style="margin: 28px 0;">
            <a href="{confirm_url}" style="display:inline-block;padding:14px 20px;background:#111827;color:#ffffff;text-decoration:none;border-radius:10px;font-weight:bold;">Confirmar meu e-mail</a>
          </p>
          <p style="font-size: 14px; color: #4b5563;">Se o botão não funcionar, copie e cole este link no navegador:</p>
          <p style="font-size: 13px; word-break: break-all;"><a href="{confirm_url}">{confirm_url}</a></p>
          <div style="background:#f9fafb;border-radius:12px;padding:16px;margin-top:20px;">
            <p style="margin:0;"><strong>Suporte WhatsApp:</strong> {support_whatsapp or 'Não informado'}</p>
          </div>
          <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;">
          <p style="font-size: 13px; color: #6b7280;">Este link expira em 24 horas.</p>
          <p style="font-size: 13px; color: #6b7280;">Equipe {app_name}</p>
        </div>
      </body>
    </html>
    '''

    return send_email(subject=subject, recipient=user.email, html_body=html_body, text_body=text_body)


def send_password_reset_email(user) -> tuple[bool, str]:
    app_name = current_app.config.get('APP_NAME', 'G Tech')
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '')
    token = generate_password_reset_token(user.email)
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    subject = f'Redefinição de senha | {app_name}'

    text_body = f'''
Olá, {user.name}!

Recebemos uma solicitação para redefinir sua senha no {app_name}.

Acesse o link abaixo para criar uma nova senha:

{reset_url}

Este link expira em 1 hora.

Se você não solicitou isso, ignore este e-mail.

Suporte WhatsApp: {support_whatsapp or 'Não informado'}

Equipe {app_name}
'''.strip()

    html_body = f'''
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color: #111827; line-height: 1.6; background: #f3f4f6; padding: 24px;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; padding: 28px; border-radius: 16px;">
          <div style="font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#0ea5e9;">G Tech Innovation & Solutions</div>
          <h2 style="margin: 10px 0 8px 0;">Redefinir senha</h2>
          <p>Olá, <strong>{user.name}</strong>!</p>
          <p>Recebemos uma solicitação para redefinir sua senha no <strong>{app_name}</strong>.</p>
          <p style="margin: 28px 0;">
            <a href="{reset_url}" style="display:inline-block;padding:14px 20px;background:#111827;color:#ffffff;text-decoration:none;border-radius:10px;font-weight:bold;">Criar nova senha</a>
          </p>
          <p style="font-size: 14px; color: #4b5563;">Se o botão não funcionar, copie e cole este link no navegador:</p>
          <p style="font-size: 13px; word-break: break-all;"><a href="{reset_url}">{reset_url}</a></p>
          <div style="background:#f9fafb;border-radius:12px;padding:16px;margin-top:20px;">
            <p style="margin:0;"><strong>Suporte WhatsApp:</strong> {support_whatsapp or 'Não informado'}</p>
          </div>
          <hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb;">
          <p style="font-size: 13px; color: #6b7280;">Este link expira em 1 hora. Se você não solicitou isso, ignore este e-mail.</p>
          <p style="font-size: 13px; color: #6b7280;">Equipe {app_name}</p>
        </div>
      </body>
    </html>
    '''

    return send_email(subject=subject, recipient=user.email, html_body=html_body, text_body=text_body)


def send_finance_summary_email(user, finance_context: dict) -> tuple[bool, str]:
    subject = 'Seu resumo financeiro G Tech'
    summary = finance_context.get('natural_summary', 'Resumo financeiro indisponível.')
    forecast = finance_context.get('forecast', {}).get('message', '')
    saving_goal = finance_context.get('saving_goal', '')
    bill_day_hint = finance_context.get('bill_day_hint', '')
    top_category = finance_context.get('top_category', 'Sem gastos')
    total_income = finance_context.get('total_income', 0)
    total_expense = finance_context.get('total_expense', 0)
    balance = finance_context.get('balance', 0)

    def money(v):
        try:
            return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        except Exception:
            return 'R$ 0,00'

    text_body = (
        f"Olá, {user.name}!\n\n"
        f"Resumo financeiro G Tech:\n"
        f"Entradas: {money(total_income)}\n"
        f"Saídas: {money(total_expense)}\n"
        f"Saldo: {money(balance)}\n"
        f"Maior categoria: {top_category}\n\n"
        f"{summary}\n{forecast}\n{saving_goal}\n{bill_day_hint}\n\nEquipe G Tech"
    )

    html_body = f"""
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color: #111827; background: #f3f4f6; padding: 24px; line-height: 1.6;">
        <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 18px; overflow: hidden;">
          <div style="background:#07111f;color:#ffffff;padding:24px;">
            <div style="font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#74dcff;">G Tech Innovation &amp; Solutions</div>
            <h1 style="margin:10px 0 0;font-size:26px;">Seu resumo financeiro</h1>
            <p style="margin:8px 0 0;color:#d8e6f7;">Clareza rápida para decidir melhor hoje.</p>
          </div>
          <div style="padding:24px;">
            <p>Olá, <strong>{user.name}</strong>!</p>
            <div style="display:grid;gap:12px;margin:18px 0;">
              <div style="padding:14px;border-radius:12px;background:#f8fafc;"><strong>Entradas:</strong> {money(total_income)}</div>
              <div style="padding:14px;border-radius:12px;background:#f8fafc;"><strong>Saídas:</strong> {money(total_expense)}</div>
              <div style="padding:14px;border-radius:12px;background:#e0f2fe;"><strong>Saldo:</strong> {money(balance)}</div>
            </div>
            <p><strong>Maior categoria:</strong> {top_category}</p>
            <p>{summary}</p>
            <p>{forecast}</p>
            <p>{saving_goal}</p>
            <p>{bill_day_hint}</p>
            <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
            <p style="font-size:13px;color:#6b7280;">Este é um envio automático/RPA do Controle G Tech.</p>
          </div>
        </div>
      </body>
    </html>
    """

    return send_email(subject=subject, recipient=user.email, html_body=html_body, text_body=text_body)


def send_welcome_email(user) -> tuple[bool, str]:
    return send_confirmation_email(user)