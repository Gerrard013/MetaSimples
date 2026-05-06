import os
from dotenv import load_dotenv

load_dotenv()


def _normalize_database_url(url: str) -> str:
    if not url:
        return 'sqlite:///metasimples.db'

    if url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql+psycopg://', 1)

    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+psycopg://', 1)

    return url


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default

    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _as_int(value: str, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == '':
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-now')

    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.getenv('DATABASE_URL', 'sqlite:///metasimples.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }

    WTF_CSRF_TIME_LIMIT = None

    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'

    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@metasimples.com')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'TroqueEssaSenha123!')

    APP_NAME = os.getenv('APP_NAME', 'G Tech')
    APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    SUPPORT_WHATSAPP = os.getenv('SUPPORT_WHATSAPP', '')
    DEFAULT_TRIAL_DAYS = _as_int(os.getenv('DEFAULT_TRIAL_DAYS', '7'), 7)

    # E-mail transacional.
    # Produção recomendada: Resend.
    MAIL_ENABLED = _as_bool(os.getenv('MAIL_ENABLED', 'false'))
    EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'resend').strip().lower()
    RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')

    MAIL_HOST = os.getenv('MAIL_HOST', '')
    MAIL_PORT = _as_int(os.getenv('MAIL_PORT', '587'), 587)
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '').replace(' ', '')
    MAIL_USE_TLS = _as_bool(os.getenv('MAIL_USE_TLS', 'true'))
    MAIL_USE_SSL = _as_bool(os.getenv('MAIL_USE_SSL', 'false'))
    MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME', 'G Tech')
    MAIL_FROM_EMAIL = os.getenv('MAIL_FROM_EMAIL', 'onboarding@resend.dev')

    # RPA interno.
    # Usado para endpoint automático de resumo financeiro.
    RPA_SECRET = os.getenv('RPA_SECRET', '')

    # Mercado Pago Checkout Pro / Preferences API.
    MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN', '')
    MERCADOPAGO_PUBLIC_KEY = os.getenv('MERCADOPAGO_PUBLIC_KEY', '')
    MERCADOPAGO_WEBHOOK_SECRET = os.getenv('MERCADOPAGO_WEBHOOK_SECRET', '')
    MERCADOPAGO_STATEMENT_DESCRIPTOR = os.getenv('MERCADOPAGO_STATEMENT_DESCRIPTOR', 'GTECH')
    MERCADOPAGO_MAX_INSTALLMENTS = _as_int(os.getenv('MERCADOPAGO_MAX_INSTALLMENTS', '3'), 3)

    # Taxa repassada ao cliente no checkout, se o serviço de pagamento usar esse cálculo.
    MERCADOPAGO_FEE_PERCENT = os.getenv('MERCADOPAGO_FEE_PERCENT', '5.31')
    MERCADOPAGO_FEE_FIXED = os.getenv('MERCADOPAGO_FEE_FIXED', '0.00')

    # Preços base líquidos.
    # O app pode somar a taxa configurada do Mercado Pago no checkout.
    PLAN_CONTROLE_PRICE = os.getenv('PLAN_CONTROLE_PRICE', '150.00')
    PLAN_METASIMPLES_PRICE = os.getenv('PLAN_METASIMPLES_PRICE', '150.00')

    PLAN_CONTROLE_MENSAL_PRICE = os.getenv('PLAN_CONTROLE_MENSAL_PRICE', '150.00')
    PLAN_CONTROLE_TRIMESTRAL_PRICE = os.getenv('PLAN_CONTROLE_TRIMESTRAL_PRICE', '299.70')
    PLAN_CONTROLE_ANUAL_PRICE = os.getenv('PLAN_CONTROLE_ANUAL_PRICE', '958.80')

    PLAN_METASIMPLES_MENSAL_PRICE = os.getenv('PLAN_METASIMPLES_MENSAL_PRICE', '150.00')
    PLAN_METASIMPLES_TRIMESTRAL_PRICE = os.getenv('PLAN_METASIMPLES_TRIMESTRAL_PRICE', '299.70')
    PLAN_METASIMPLES_ANUAL_PRICE = os.getenv('PLAN_METASIMPLES_ANUAL_PRICE', '958.80')

    PAYMENT_URL = os.getenv('PAYMENT_URL', '#')
    PAYMENT_URL_CONTROLE = os.getenv('PAYMENT_URL_CONTROLE', '')
    PAYMENT_URL_METASIMPLES = os.getenv('PAYMENT_URL_METASIMPLES', '')
    PAYMENT_REQUIRED_BEFORE_ACCESS = _as_bool(
        os.getenv('PAYMENT_REQUIRED_BEFORE_ACCESS', 'false')
    )

    # IA.
    # Sem chave: usa consultor local grátis.
    # Com chave: pode usar Groq, xAI/Grok ou OpenRouter via API.
    AI_PROVIDER = os.getenv('AI_PROVIDER', 'local').strip().lower()
    AI_API_KEY = os.getenv('AI_API_KEY', '')
    AI_MODEL = os.getenv('AI_MODEL', 'llama-3.1-8b-instant')
    AI_API_BASE_URL = os.getenv('AI_API_BASE_URL', '')