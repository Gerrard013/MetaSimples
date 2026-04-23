import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'

load_dotenv(ENV_PATH)


def _to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'change-me')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///metasimples.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    APP_NAME = os.getenv('APP_NAME', 'MetaSimples')
    APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000')
    SUPPORT_WHATSAPP = os.getenv('SUPPORT_WHATSAPP', '')
    DEFAULT_TRIAL_DAYS = int(os.getenv('DEFAULT_TRIAL_DAYS', '7'))
    PAYMENT_URL = os.getenv('PAYMENT_URL', '')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')

    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '').strip().lower()
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')

    MAIL_ENABLED = _to_bool(os.getenv('MAIL_ENABLED', 'false'))
    MAIL_HOST = os.getenv('MAIL_HOST', '').strip()
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '').strip()
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '').strip().replace(' ', '')
    MAIL_USE_TLS = _to_bool(os.getenv('MAIL_USE_TLS', 'true'))
    MAIL_USE_SSL = _to_bool(os.getenv('MAIL_USE_SSL', 'false'))
    MAIL_FROM_NAME = os.getenv('MAIL_FROM_NAME', 'MetaSimples').strip()
    MAIL_FROM_EMAIL = os.getenv('MAIL_FROM_EMAIL', '').strip()

    WTF_CSRF_TIME_LIMIT = None