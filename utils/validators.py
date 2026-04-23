import re
from email_validator import EmailNotValidError, validate_email


EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
PHONE_DIGITS_REGEX = re.compile(r'\D+')


def normalize_email(email: str) -> str:
    if not email:
        return ''
    return email.strip().lower()


def is_valid_email(email: str, check_deliverability: bool = True) -> bool:
    normalized = normalize_email(email)
    if not normalized or not EMAIL_REGEX.match(normalized):
        return False

    try:
        validate_email(normalized, check_deliverability=check_deliverability)
        return True
    except EmailNotValidError:
        return False


def normalize_whatsapp_br(whatsapp: str) -> str:
    if not whatsapp:
        return ''

    digits = PHONE_DIGITS_REGEX.sub('', whatsapp)

    if digits.startswith('55') and len(digits) in (12, 13):
        digits = digits[2:]

    return digits


def is_valid_whatsapp_br(whatsapp: str) -> bool:
    digits = normalize_whatsapp_br(whatsapp)

    # Celular BR com DDD + 9 dígitos = 11 números
    if len(digits) != 11:
        return False

    if not digits.isdigit():
        return False

    ddd = int(digits[:2])
    ninth_digit = digits[2]
    remaining = digits[3:]

    # DDDs válidos no Brasil começam em 11
    if ddd < 11 or ddd > 99:
        return False

    # Celular moderno no BR começa com 9 depois do DDD
    if ninth_digit != '9':
        return False

    # Evita números repetidos tipo 99999999999
    if digits == digits[0] * len(digits):
        return False

    # Evita sequências obviamente ruins
    invalid_sequences = {
        '12345678',
        '23456789',
        '34567890',
        '87654321',
        '98765432',
    }
    if remaining in invalid_sequences:
        return False

    return True


def format_whatsapp_br(whatsapp: str) -> str:
    digits = normalize_whatsapp_br(whatsapp)
    if len(digits) == 11:
        return f'({digits[:2]}) {digits[2:7]}-{digits[7:]}'
    return digits