from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import requests
from flask import current_app, url_for

from database.db import db
from models.payment import Payment


PLAN_LABELS = {
    'controle': 'Controle de Gastos G Tech',
    'metasimples': 'MetaSimples',
}

BILLING_CONFIG = {
    'mensal': {
        'months': 1,
        'days': 30,
        'label': '1 mês',
        'discount_label': 'acesso mensal',
    },
    'trimestral': {
        'months': 3,
        'days': 90,
        'label': '3 meses',
        'discount_label': 'pagamento antecipado',
    },
    'anual': {
        'months': 12,
        'days': 365,
        'label': '1 ano',
        'discount_label': 'melhor economia',
    },
}

DEFAULT_PRICES = {
    'controle': {
        'mensal': Decimal('150.00'),
        'trimestral': Decimal('299.70'),
        'anual': Decimal('599.88'),
    },
    'metasimples': {
        'mensal': Decimal('150.00'),
        'trimestral': Decimal('299.70'),
        'anual': Decimal('599.88'),
    },
}


def normalize_plan(plan: str | None) -> str:
    plan = (plan or 'metasimples').strip().lower()

    if plan in ('controle', 'controle-gastos', 'gastos', 'financeiro', 'controle_gtech'):
        return 'controle'

    return 'metasimples'


def normalize_billing(billing: str | None) -> str:
    billing = (billing or 'mensal').strip().lower()

    if billing in ('3', 'tri', 'trimestre', 'trimestral'):
        return 'trimestral'

    if billing in ('12', 'ano', 'anual', 'annual'):
        return 'anual'

    return 'mensal'


def _env_decimal(key: str, default: Decimal) -> Decimal:
    raw = current_app.config.get(key)

    if raw is None or str(raw).strip() == '':
        return default

    try:
        return Decimal(str(raw).replace(',', '.')).quantize(Decimal('0.01'))
    except Exception:
        return default


def plan_price(plan: str, billing: str = 'mensal') -> Decimal:
    plan = normalize_plan(plan)
    billing = normalize_billing(billing)
    default = DEFAULT_PRICES[plan][billing]
    key = f'PLAN_{plan.upper()}_{billing.upper()}_PRICE'
    legacy_key = 'PLAN_CONTROLE_PRICE' if plan == 'controle' else 'PLAN_METASIMPLES_PRICE'

    if billing == 'mensal' and current_app.config.get(legacy_key) not in (None, ''):
        return _env_decimal(legacy_key, default)

    return _env_decimal(key, default)


def mp_customer_total(base_amount: Decimal) -> Decimal:
    fee_percent = (
        Decimal(str(current_app.config.get('MERCADOPAGO_FEE_PERCENT', '5.31')).replace(',', '.'))
        / Decimal('100')
    )
    fee_fixed = Decimal(str(current_app.config.get('MERCADOPAGO_FEE_FIXED', '0.00')).replace(',', '.'))

    if fee_percent < 0:
        fee_percent = Decimal('0')

    if fee_percent >= Decimal('0.50'):
        fee_percent = Decimal('0.0531')

    gross = (base_amount + fee_fixed) / (Decimal('1') - fee_percent)

    return gross.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def payment_duration_days(billing: str) -> int:
    return BILLING_CONFIG[normalize_billing(billing)]['days']


def payment_description(plan: str, billing: str) -> str:
    plan = normalize_plan(plan)
    billing = normalize_billing(billing)
    cfg = BILLING_CONFIG[billing]

    return f"{PLAN_LABELS[plan]} — {cfg['label']} ({cfg['discount_label']})"


def public_plans() -> dict:
    data = {}

    for plan in ('controle', 'metasimples'):
        data[plan] = {}

        for billing in ('mensal', 'trimestral', 'anual'):
            base = plan_price(plan, billing)
            total = mp_customer_total(base)
            months = BILLING_CONFIG[billing]['months']

            data[plan][billing] = {
                'base': base,
                'total': total,
                'monthly_equivalent': (base / Decimal(str(months))).quantize(Decimal('0.01')),
                'charged_monthly_equivalent': (total / Decimal(str(months))).quantize(Decimal('0.01')),
                'label': BILLING_CONFIG[billing]['label'],
                'days': BILLING_CONFIG[billing]['days'],
            }

    return data


def create_mercadopago_preference(user, plan: str, billing: str = 'mensal') -> tuple[bool, str]:
    plan = normalize_plan(plan)
    billing = normalize_billing(billing)
    access_token = current_app.config.get('MERCADOPAGO_ACCESS_TOKEN', '').strip()

    if not access_token:
        return False, 'MERCADOPAGO_ACCESS_TOKEN não configurado.'

    base_amount = plan_price(plan, billing)
    charge_amount = mp_customer_total(base_amount)
    duration_days = payment_duration_days(billing)
    title = payment_description(plan, billing)
    external_reference = f'{plan}-{billing}-{user.id}-{int(datetime.utcnow().timestamp())}'

    payment = Payment(
        user_id=user.id,
        amount=charge_amount,
        status='pending',
        gateway='mercadopago',
        external_reference=external_reference,
        due_date=datetime.utcnow() + timedelta(days=3),
    )

    payment.plan_type = plan
    payment.billing_cycle = billing
    payment.duration_days = duration_days
    payment.net_amount = base_amount
    payment.fee_amount = charge_amount - base_amount

    db.session.add(payment)
    db.session.commit()

    app_base = current_app.config.get('APP_BASE_URL', '').rstrip('/')

    payload = {
        'items': [
            {
                'id': f'{plan}-{billing}',
                'title': title,
                'description': 'Acesso G Tech com painel, automação e inteligência financeira/comercial.',
                'currency_id': 'BRL',
                'quantity': 1,
                'unit_price': float(charge_amount),
            }
        ],
        'payer': {
            'name': user.name,
            'email': user.email,
        },
        'back_urls': {
            'success': f'{app_base}{url_for("main.payment_success")}',
            'failure': f'{app_base}{url_for("main.payment_failure")}',
            'pending': f'{app_base}{url_for("main.payment_pending")}',
        },
        'auto_return': 'approved',
        'notification_url': f'{app_base}{url_for("main.mercadopago_webhook")}',
        'external_reference': external_reference,
        'statement_descriptor': current_app.config.get('MERCADOPAGO_STATEMENT_DESCRIPTOR', 'GTECH'),
        'payment_methods': {
            'installments': int(current_app.config.get('MERCADOPAGO_MAX_INSTALLMENTS', 3)),
        },
        'metadata': {
            'user_id': user.id,
            'plan_type': plan,
            'billing_cycle': billing,
            'duration_days': duration_days,
            'base_amount': str(base_amount),
            'charged_amount': str(charge_amount),
        },
    }

    try:
        response = requests.post(
            'https://api.mercadopago.com/checkout/preferences',
            json=payload,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            timeout=12,
        )

        if response.status_code >= 400:
            current_app.logger.error('Erro Mercado Pago %s: %s', response.status_code, response.text)
            return False, f'Erro Mercado Pago: {response.status_code} - {response.text}'

        data = response.json()
        init_point = data.get('init_point') or data.get('sandbox_init_point')

        if not init_point:
            return False, 'Mercado Pago não retornou init_point.'

        return True, init_point

    except requests.RequestException as exc:
        current_app.logger.exception('Falha ao criar preferência Mercado Pago')
        return False, str(exc)


def approve_payment(payment: Payment, mp_payment_id: str | None = None) -> None:
    user = payment.user
    now = datetime.utcnow()
    days = int(
        getattr(payment, 'duration_days', None)
        or payment_duration_days(getattr(payment, 'billing_cycle', 'mensal'))
    )

    base_date = user.paid_until if user.paid_until and user.paid_until > now else now

    user.paid_until = base_date + timedelta(days=days)
    user.is_blocked = False
    user.is_active_account = True
    user.blocked_reason = None
    user.access_blocked_at = None

    if getattr(payment, 'plan_type', None):
        user.plan_type = normalize_plan(payment.plan_type)

    payment.status = 'approved'
    payment.paid_at = payment.paid_at or now

    if mp_payment_id and hasattr(payment, 'gateway_payment_id'):
        payment.gateway_payment_id = str(mp_payment_id)


def sync_mercadopago_payment(mp_payment_id: str) -> tuple[bool, str]:
    access_token = current_app.config.get('MERCADOPAGO_ACCESS_TOKEN', '').strip()

    if not access_token:
        return False, 'MERCADOPAGO_ACCESS_TOKEN não configurado.'

    try:
        response = requests.get(
            f'https://api.mercadopago.com/v1/payments/{mp_payment_id}',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=12,
        )

        if response.status_code >= 400:
            current_app.logger.error(
                'Erro ao consultar pagamento Mercado Pago %s: %s',
                response.status_code,
                response.text,
            )
            return False, f'Erro Mercado Pago {response.status_code}'

        data = response.json()
        external_reference = data.get('external_reference')
        status = data.get('status')

        if not external_reference:
            return False, 'Pagamento sem external_reference.'

        payment = Payment.query.filter_by(external_reference=external_reference).first()

        if not payment:
            return False, 'Pagamento não encontrado no sistema.'

        payment.status = status or payment.status

        if status == 'approved':
            approve_payment(payment, mp_payment_id=str(mp_payment_id))

        db.session.commit()

        return True, status or 'updated'

    except requests.RequestException as exc:
        current_app.logger.exception('Falha ao sincronizar pagamento Mercado Pago')
        return False, str(exc)