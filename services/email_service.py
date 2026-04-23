import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Tuple

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer


def _build_sender() -> str:
    from_name = current_app.config.get('MAIL_FROM_NAME', 'MetaSimples')
    from_email = current_app.config.get('MAIL_FROM_EMAIL', 'no-reply@metasimples.com')
    return f'{from_name} <{from_email}>'


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_email_verification_token(email: str) -> str:
    serializer = _serializer()
    return serializer.dumps(email, salt='email-verification')


def confirm_email_verification_token(token: str, max_age: int = 86400) -> Optional[str]:
    serializer = _serializer()

    try:
        email = serializer.loads(token, salt='email-verification', max_age=max_age)
        return email
    except Exception:
        return None


def _logo_path() -> Path:
    return Path(current_app.root_path) / 'static' / 'img' / 'logo.jpeg'


def _attach_inline_logo(message: MIMEMultipart) -> bool:
    logo_path = _logo_path()

    if not logo_path.exists():
        return False

    try:
        with open(logo_path, 'rb') as logo_file:
            image = MIMEImage(logo_file.read(), _subtype='jpeg')
            image.add_header('Content-ID', '<gtechlogo>')
            image.add_header('Content-Disposition', 'inline', filename='logo.jpeg')
            message.attach(image)
        return True
    except Exception:
        return False


def send_email(subject: str, recipient: str, html_body: str, text_body: str = '') -> Tuple[bool, str]:
    if not current_app.config.get('MAIL_ENABLED'):
        return False, 'MAIL_ENABLED=false'

    host = current_app.config.get('MAIL_HOST')
    port = current_app.config.get('MAIL_PORT')
    username = current_app.config.get('MAIL_USERNAME')
    password = current_app.config.get('MAIL_PASSWORD')
    use_tls = current_app.config.get('MAIL_USE_TLS', True)
    use_ssl = current_app.config.get('MAIL_USE_SSL', False)
    sender = _build_sender()

    if not host:
        return False, 'MAIL_HOST vazio'
    if not port:
        return False, 'MAIL_PORT vazio'
    if not username:
        return False, 'MAIL_USERNAME vazio'
    if not password:
        return False, 'MAIL_PASSWORD vazio'
    if not current_app.config.get('MAIL_FROM_EMAIL'):
        return False, 'MAIL_FROM_EMAIL vazio'

    message = MIMEMultipart('related')
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient

    alternative = MIMEMultipart('alternative')
    message.attach(alternative)

    if text_body:
        alternative.attach(MIMEText(text_body, 'plain', 'utf-8'))

    alternative.attach(MIMEText(html_body, 'html', 'utf-8'))
    _attach_inline_logo(message)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
                server.login(username, password)
                server.sendmail(sender, [recipient], message.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(username, password)
                server.sendmail(sender, [recipient], message.as_string())

        return True, 'E-mail enviado com sucesso.'
    except smtplib.SMTPAuthenticationError as exc:
        return False, f'SMTPAuthenticationError: {exc}'
    except smtplib.SMTPException as exc:
        return False, f'SMTPException: {exc}'
    except Exception as exc:
        return False, f'Erro geral SMTP: {exc}'


def _email_shell(title: str, subtitle: str, content_html: str) -> str:
    return f"""
    <html>
      <body style="margin:0;padding:0;background:#eef3f8;font-family:Arial,Helvetica,sans-serif;color:#122033;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#eef3f8;padding:32px 16px;">
          <tr>
            <td align="center">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 12px 40px rgba(14,30,56,0.14);">
                <tr>
                  <td style="background:linear-gradient(135deg,#0f2744 0%,#173a66 48%,#12b8f5 100%);padding:28px 32px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="vertical-align:middle;">
                          <img src="cid:gtechlogo" alt="G Tech" style="display:block;width:88px;max-width:88px;height:auto;border:0;">
                        </td>
                        <td style="vertical-align:middle;padding-left:16px;">
                          <div style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:0.2px;">G Tech Innovation &amp; Solutions</div>
                          <div style="font-size:14px;line-height:1.5;color:#dcecff;margin-top:6px;">Confiança, tecnologia e comprometimento em cada acesso.</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="padding:34px 32px 12px 32px;">
                    <div style="font-size:13px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;color:#12b8f5;margin-bottom:10px;">MetaSimples</div>
                    <h1 style="margin:0;font-size:30px;line-height:1.2;color:#10233d;">{title}</h1>
                    <p style="margin:12px 0 0 0;font-size:16px;line-height:1.7;color:#49627f;">{subtitle}</p>
                  </td>
                </tr>

                <tr>
                  <td style="padding:8px 32px 16px 32px;">
                    {content_html}
                  </td>
                </tr>

                <tr>
                  <td style="padding:0 32px 12px 32px;">
                    <div style="border-top:1px solid #e5edf5;"></div>
                  </td>
                </tr>

                <tr>
                  <td style="padding:8px 32px 32px 32px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f6f9fc;border:1px solid #e6eef7;border-radius:16px;">
                      <tr>
                        <td style="padding:18px 20px;">
                          <div style="font-size:15px;font-weight:700;color:#0f2744;margin-bottom:6px;">Compromisso G Tech</div>
                          <div style="font-size:14px;line-height:1.7;color:#4d627c;">
                            Nossa prioridade é entregar uma experiência segura, clara e profissional em cada etapa do seu acesso ao MetaSimples.
                          </div>
                        </td>
                      </tr>
                    </table>

                    <p style="margin:18px 0 0 0;font-size:12px;line-height:1.7;color:#73879e;">
                      Este é um e-mail automático do sistema MetaSimples by G Tech Innovation &amp; Solutions.
                    </p>
                  </td>
                </tr>

              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """


def send_verification_email(user) -> Tuple[bool, str]:
    app_name = current_app.config.get('APP_NAME', 'MetaSimples')
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '')
    token = generate_email_verification_token(user.email)

    verification_url = url_for('auth.verify_email', token=token, _external=True)
    login_url = url_for('auth.login', _external=True)

    subject = f'Confirme seu e-mail no {app_name}'

    text_body = f"""
Olá, {user.name}!

Recebemos seu cadastro no {app_name}.
Para ativar sua conta com segurança, confirme seu e-mail clicando no link abaixo:

{verification_url}

Depois da confirmação, seu login poderá ser feito em:
{login_url}

Suporte WhatsApp: {support_whatsapp}
G Tech Innovation & Solutions
""".strip()

    content_html = f"""
    <p style="margin:0 0 18px 0;font-size:16px;line-height:1.8;color:#23384f;">
      Olá, <strong>{user.name}</strong>.
    </p>

    <p style="margin:0 0 18px 0;font-size:16px;line-height:1.8;color:#23384f;">
      Recebemos seu cadastro no <strong>{app_name}</strong>. Para proteger seu acesso e concluir a ativação da conta,
      confirme seu e-mail pelo botão abaixo.
    </p>

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:26px 0 24px 0;">
      <tr>
        <td align="center" style="border-radius:14px;background:linear-gradient(135deg,#0f2744 0%,#12b8f5 100%);">
          <a href="{verification_url}" style="display:inline-block;padding:15px 26px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:14px;">
            Confirmar meu e-mail
          </a>
        </td>
      </tr>
    </table>

    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px 0;background:#f7fbff;border:1px solid #dfeaf5;border-radius:16px;">
      <tr>
        <td style="padding:18px 18px 8px 18px;">
          <div style="font-size:14px;font-weight:700;color:#0f2744;">Acesso seguro</div>
        </td>
      </tr>
      <tr>
        <td style="padding:0 18px 18px 18px;font-size:14px;line-height:1.8;color:#4b627b;">
          Esse passo garante mais segurança, confiança e integridade no uso da sua conta.
        </td>
      </tr>
    </table>

    <p style="margin:0 0 12px 0;font-size:14px;line-height:1.8;color:#4b627b;">
      Se o botão não funcionar, copie e cole este link no navegador:
    </p>

    <p style="margin:0 0 20px 0;font-size:14px;line-height:1.8;word-break:break-word;">
      <a href="{verification_url}" style="color:#118dd6;text-decoration:none;">{verification_url}</a>
    </p>

    <p style="margin:0;font-size:14px;line-height:1.8;color:#4b627b;">
      Suporte WhatsApp:
      <strong style="color:#0f2744;">{support_whatsapp or 'Não informado'}</strong>
    </p>
    """

    html_body = _email_shell(
        title='Confirmação de e-mail',
        subtitle='Seu acesso está quase pronto. Falta apenas uma etapa para liberar sua conta com segurança.',
        content_html=content_html,
    )

    return send_email(subject, user.email, html_body, text_body)


def send_welcome_email(user) -> Tuple[bool, str]:
    app_name = current_app.config.get('APP_NAME', 'MetaSimples')
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '')
    login_url = url_for('auth.login', _external=True)
    dashboard_url = url_for('main.dashboard', _external=True)

    subject = f'Sua conta no {app_name} foi ativada'

    text_body = f"""
Olá, {user.name}!

Seu e-mail foi confirmado com sucesso.
Sua conta no {app_name} já está ativa.

Login: {login_url}
Dashboard: {dashboard_url}

Suporte WhatsApp: {support_whatsapp}
G Tech Innovation & Solutions
""".strip()

    content_html = f"""
    <p style="margin:0 0 18px 0;font-size:16px;line-height:1.8;color:#23384f;">
      Olá, <strong>{user.name}</strong>.
    </p>

    <p style="margin:0 0 18px 0;font-size:16px;line-height:1.8;color:#23384f;">
      Seu e-mail foi confirmado com sucesso e sua conta no <strong>{app_name}</strong> já está ativa.
    </p>

    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.8;color:#23384f;">
      Agora você já pode entrar no sistema e começar a acompanhar suas metas, rotina comercial e resultados com mais clareza.
    </p>

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:26px 0 24px 0;">
      <tr>
        <td align="center" style="border-radius:14px;background:linear-gradient(135deg,#0f2744 0%,#12b8f5 100%);">
          <a href="{login_url}" style="display:inline-block;padding:15px 26px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:14px;">
            Entrar na minha conta
          </a>
        </td>
      </tr>
    </table>

    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 22px 0;background:#f7fbff;border:1px solid #dfeaf5;border-radius:16px;">
      <tr>
        <td style="padding:18px;">
          <div style="font-size:14px;font-weight:700;color:#0f2744;margin-bottom:8px;">Próximo passo</div>
          <div style="font-size:14px;line-height:1.8;color:#4b627b;">
            Acesse seu painel, ajuste sua meta e comece a registrar sua evolução diária com organização e constância.
          </div>
        </td>
      </tr>
    </table>

    <p style="margin:0 0 10px 0;font-size:14px;line-height:1.8;color:#4b627b;">
      Login: <a href="{login_url}" style="color:#118dd6;text-decoration:none;">{login_url}</a>
    </p>

    <p style="margin:0 0 20px 0;font-size:14px;line-height:1.8;color:#4b627b;">
      Dashboard: <a href="{dashboard_url}" style="color:#118dd6;text-decoration:none;">{dashboard_url}</a>
    </p>

    <p style="margin:0;font-size:14px;line-height:1.8;color:#4b627b;">
      Suporte WhatsApp:
      <strong style="color:#0f2744;">{support_whatsapp or 'Não informado'}</strong>
    </p>
    """

    html_body = _email_shell(
        title='Conta ativada com sucesso',
        subtitle='Seu acesso foi liberado. Agora você já pode usar o MetaSimples com a segurança e o suporte da G Tech.',
        content_html=content_html,
    )

    return send_email(subject, user.email, html_body, text_body)