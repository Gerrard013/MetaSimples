import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from database.db import csrf, db
from forms import AdminAccessForm, ChecklistForm, DailyResultForm, FinanceTransactionForm, GoalForm
from models.checklist import ChecklistEntry
from models.daily_result import DailyResult
from models.finance_transaction import FinanceTransaction
from models.goal import Goal
from models.lead import Lead
from models.payment import Payment
from models.user import User
from services.ai_service import ask_ai
from services.calculations import (
    calculate_day_sales_target,
    calculate_earnings_from_sales,
    calculate_month_sales_target,
)
from services.dashboard_service import build_dashboard_context
from services.email_service import send_finance_summary_email
from services.finance_service import build_finance_context, suggest_category
from services.payment_service import (
    approve_payment,
    create_mercadopago_preference,
    normalize_billing,
    normalize_plan,
    public_plans,
    sync_mercadopago_payment,
)
from utils.validators import (
    is_valid_email,
    is_valid_whatsapp_br,
    normalize_email,
    normalize_whatsapp_br,
)

main_bp = Blueprint('main', __name__)


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash('Acesso restrito ao administrador.', 'error')
            return redirect(url_for('auth.admin_login'))

        return view_func(*args, **kwargs)

    return wrapped


def controle_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.is_admin:
            return view_func(*args, **kwargs)

        if current_user.plan_type != 'controle':
            flash('Este recurso pertence ao Controle de Gastos G Tech.', 'error')
            return redirect(url_for('main.dashboard'))

        return view_func(*args, **kwargs)

    return wrapped


def metasimples_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.is_admin:
            return view_func(*args, **kwargs)

        if current_user.plan_type == 'controle':
            flash('Seu plano atual é o Controle de Gastos G Tech.', 'info')
            return redirect(url_for('main.finance_dashboard'))

        return view_func(*args, **kwargs)

    return wrapped


@main_bp.before_app_request
def enforce_block_rule():
    if not current_user.is_authenticated:
        return None

    if current_user.is_admin:
        return None

    open_endpoints = {
        'main.blocked_access',
        'auth.logout',
        'main.payment_redirect',
        'main.payment_checkout',
        'main.payment_success',
        'main.payment_pending',
        'main.payment_failure',
        'main.mercadopago_webhook',
        'main.rpa_send_finance_summaries',
        'static',
    }

    endpoint = request.endpoint or ''

    if endpoint in open_endpoints or endpoint.startswith('auth.validate_'):
        return None

    if current_user.auto_block_if_needed():
        db.session.commit()

    if current_user.is_blocked:
        logout_user()
        return redirect(url_for('main.blocked_access'))

    metasimples_endpoints = {
        'main.dashboard',
        'main.onboarding',
        'main.daily_entry',
        'main.checklist',
        'main.history',
        'main.settings',
    }

    controle_endpoints = {
        'main.finance_dashboard',
        'main.finance_new',
        'main.finance_edit',
        'main.finance_delete',
        'main.finance_send_summary',
        'main.assistant',
    }

    if current_user.plan_type == 'controle' and endpoint in metasimples_endpoints:
        return redirect(url_for('main.finance_dashboard'))

    if current_user.plan_type == 'metasimples' and endpoint in controle_endpoints:
        flash('O Controle de Gastos é um produto separado do MetaSimples.', 'info')
        return redirect(url_for('main.dashboard'))

    return None


def _safe_float(value, default=0.0):
    try:
        if value is None or value == '':
            return float(default)

        return float(value)

    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0):
    try:
        if value is None or value == '':
            return int(default)

        return int(value)

    except (TypeError, ValueError):
        return int(default)


def _parse_decimal_input(raw_value, default=None):
    if raw_value is None:
        return default

    text = str(raw_value).strip()

    if not text:
        return default

    text = (
        text.replace('R$', '')
        .replace('%', '')
        .replace(' ', '')
        .replace('\u00a0', '')
    )

    if ',' in text and '.' in text:
        if text.rfind(',') > text.rfind('.'):
            text = text.replace('.', '').replace(',', '.')
        else:
            text = text.replace(',', '')

    elif ',' in text:
        if text.count(',') == 1:
            left, right = text.split(',')

            if len(right) in (1, 2):
                text = f'{left}.{right}'
            else:
                text = text.replace(',', '')
        else:
            text = text.replace(',', '')

    elif '.' in text:
        if text.count('.') > 1:
            text = text.replace('.', '')
        else:
            left, right = text.split('.')

            if len(right) == 3 and left.isdigit() and right.isdigit():
                text = left + right

    try:
        return float(text)

    except ValueError:
        return default


@main_bp.app_context_processor
def inject_helpers():
    def format_brl(value):
        numeric_value = _safe_float(value, 0.0)

        return f'R$ {numeric_value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    payment_url = os.getenv('PAYMENT_URL', '#')

    return {
        'format_brl': format_brl,
        'payment_url': payment_url,
        'public_plans': public_plans(),
    }


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('main.admin_dashboard'))

        if current_user.plan_type == 'controle':
            return redirect(url_for('main.finance_dashboard'))

        goal = get_user_goal(current_user.id)

        if goal:
            return redirect(url_for('main.dashboard'))

        return redirect(url_for('main.onboarding'))

    return render_template('index.html')


@main_bp.route('/landing', methods=['GET', 'POST'])
def landing_page():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = normalize_email(request.form.get('email', ''))
        whatsapp = normalize_whatsapp_br(request.form.get('whatsapp', ''))

        if len(name) < 2:
            flash('Informe um nome válido.', 'error')
            return render_template('landing.html')

        if not is_valid_email(email, check_deliverability=False):
            flash('Informe um e-mail válido.', 'error')
            return render_template('landing.html')

        if not is_valid_whatsapp_br(whatsapp):
            flash('Informe um WhatsApp válido com DDD e 9 dígitos.', 'error')
            return render_template('landing.html')

        existing = Lead.query.filter(
            (Lead.email == email) | (Lead.whatsapp == whatsapp)
        ).first()

        if existing:
            flash('Este lead já está cadastrado. Em breve entraremos em contato.', 'info')
            return redirect(url_for('main.landing_page'))

        lead = Lead(
            name=name,
            email=email,
            whatsapp=whatsapp,
            source='landing_page',
        )

        db.session.add(lead)
        db.session.commit()

        flash('Lead cadastrado com sucesso. Em breve entraremos em contato.', 'success')
        return redirect(url_for('main.landing_page'))

    return render_template('landing.html')


@main_bp.route('/pagamento')
def payment_redirect():
    payment_url = os.getenv('PAYMENT_URL')

    if payment_url:
        return redirect(payment_url)

    flash('Configure a variável PAYMENT_URL para usar esta página.', 'info')
    return redirect(url_for('main.index'))


@main_bp.route('/acesso-bloqueado')
def blocked_access():
    return render_template('blocked_access.html')


def get_user_goal(user_id: int):
    return Goal.query.filter_by(user_id=user_id).order_by(Goal.updated_at.desc()).first()


@main_bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
@metasimples_required
def onboarding():
    goal = get_user_goal(current_user.id)
    form = GoalForm(obj=goal)

    if request.method == 'GET' and goal:
        form.target_income_month.data = (
            str(int(goal.target_income_month))
            if float(goal.target_income_month).is_integer()
            else str(goal.target_income_month)
        )
        form.working_days_month.data = goal.working_days_month
        form.use_commission.data = _safe_float(goal.commission_percent, 0) > 0
        form.commission_percent.data = (
            ''
            if _safe_float(goal.commission_percent, 0) <= 0
            else str(goal.commission_percent)
        )

    if form.validate_on_submit():
        target_income_month = _parse_decimal_input(request.form.get('target_income_month'), None)
        use_commission = request.form.get('use_commission') == 'on'
        commission_percent = (
            0.0
            if not use_commission
            else _parse_decimal_input(request.form.get('commission_percent'), None)
        )
        working_days_month = _safe_int(request.form.get('working_days_month'), 0)

        if target_income_month is None or target_income_month <= 0:
            flash('Informe uma meta mensal válida. Ex.: 3000 ou 3.000,50.', 'error')
            return render_template('onboarding.html', form=form, goal=goal)

        if working_days_month <= 0 or working_days_month > 31:
            flash('Informe uma quantidade válida de dias trabalhados no mês.', 'error')
            return render_template('onboarding.html', form=form, goal=goal)

        if use_commission and (
            commission_percent is None or commission_percent < 0 or commission_percent > 100
        ):
            flash('Informe uma comissão válida entre 0 e 100.', 'error')
            return render_template('onboarding.html', form=form, goal=goal)

        target_sales_month = calculate_month_sales_target(target_income_month, commission_percent)
        target_sales_day = calculate_day_sales_target(target_sales_month, working_days_month)

        if not goal:
            goal = Goal(user_id=current_user.id)
            db.session.add(goal)

        goal.target_income_month = target_income_month
        goal.commission_percent = commission_percent
        goal.working_days_month = working_days_month
        goal.target_sales_month = target_sales_month
        goal.target_sales_day = target_sales_day

        db.session.commit()

        flash('Meta configurada com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('onboarding.html', form=form, goal=goal)


@main_bp.route('/dashboard')
@login_required
@metasimples_required
def dashboard():
    goal = get_user_goal(current_user.id)

    if not goal:
        return redirect(url_for('main.onboarding'))

    context = build_dashboard_context(current_user.id, goal)

    return render_template('dashboard.html', goal=goal, **context)


@main_bp.route('/daily-entry', methods=['GET', 'POST'])
@login_required
@metasimples_required
def daily_entry():
    goal = get_user_goal(current_user.id)

    if not goal:
        return redirect(url_for('main.onboarding'))

    today = date.today()
    form = DailyResultForm()

    if not form.date.data:
        form.date.data = today

    if form.validate_on_submit():
        result = DailyResult.query.filter_by(
            user_id=current_user.id,
            date=form.date.data,
        ).first()

        sales_value = _parse_decimal_input(request.form.get('sales_value'), None)
        attendance_count = _safe_int(request.form.get('attendance_count'), 0)
        closed_deals = _safe_int(request.form.get('closed_deals'), 0)
        commission_percent = _safe_float(goal.commission_percent, 0)

        if sales_value is None or sales_value < 0:
            flash('Informe um valor de venda válido. Ex.: 3000 ou 3.000,50.', 'error')
            return render_template(
                'daily_entry.html',
                form=form,
                goal=goal,
                result=result,
                today=today,
            )

        earnings_value = calculate_earnings_from_sales(sales_value, commission_percent)

        if not result:
            result = DailyResult(user_id=current_user.id, date=form.date.data)
            db.session.add(result)

        result.sales_value = sales_value
        result.earnings_value = earnings_value
        result.attendance_count = attendance_count
        result.closed_deals = closed_deals
        result.notes = form.notes.data.strip() if form.notes.data else ''

        db.session.commit()

        flash('Resultado diário salvo com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    existing_result = DailyResult.query.filter_by(
        user_id=current_user.id,
        date=form.date.data or today,
    ).first()

    return render_template(
        'daily_entry.html',
        form=form,
        goal=goal,
        result=existing_result,
        today=today,
    )


@main_bp.route('/checklist', methods=['GET', 'POST'])
@login_required
@metasimples_required
def checklist():
    goal = get_user_goal(current_user.id)

    if not goal:
        return redirect(url_for('main.onboarding'))

    today = date.today()
    existing = ChecklistEntry.query.filter_by(user_id=current_user.id, date=today).first()
    form = ChecklistForm(obj=existing)

    if not form.date.data:
        form.date.data = today

    if form.validate_on_submit():
        entry = ChecklistEntry.query.filter_by(
            user_id=current_user.id,
            date=form.date.data,
        ).first()

        if not entry:
            entry = ChecklistEntry(user_id=current_user.id, date=form.date.data)
            db.session.add(entry)

        entry.leads_answered = bool(form.leads_answered.data)
        entry.follow_up_done = bool(form.follow_up_done.data)
        entry.proposals_sent = bool(form.proposals_sent.data)
        entry.post_sale_done = bool(form.post_sale_done.data)
        entry.goal_reviewed = bool(form.goal_reviewed.data)

        db.session.commit()

        flash('Checklist salvo com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('checklist.html', form=form, goal=goal)


@main_bp.route('/history')
@login_required
@metasimples_required
def history():
    goal = get_user_goal(current_user.id)

    if not goal:
        return redirect(url_for('main.onboarding'))

    results = (
        DailyResult.query.filter_by(user_id=current_user.id)
        .order_by(DailyResult.date.desc())
        .all()
    )

    return render_template('history.html', goal=goal, results=results)


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@metasimples_required
def settings():
    goal = get_user_goal(current_user.id)

    if not goal:
        return redirect(url_for('main.onboarding'))

    form = GoalForm(obj=goal)

    if request.method == 'GET':
        form.target_income_month.data = (
            str(int(goal.target_income_month))
            if float(goal.target_income_month).is_integer()
            else str(goal.target_income_month)
        )
        form.working_days_month.data = goal.working_days_month
        form.use_commission.data = _safe_float(goal.commission_percent, 0) > 0
        form.commission_percent.data = (
            ''
            if _safe_float(goal.commission_percent, 0) <= 0
            else str(goal.commission_percent)
        )

    if form.validate_on_submit():
        target_income_month = _parse_decimal_input(request.form.get('target_income_month'), None)
        use_commission = request.form.get('use_commission') == 'on'
        commission_percent = (
            0.0
            if not use_commission
            else _parse_decimal_input(request.form.get('commission_percent'), None)
        )
        working_days_month = _safe_int(request.form.get('working_days_month'), 0)

        if target_income_month is None or target_income_month <= 0:
            flash('Informe uma meta mensal válida. Ex.: 3000 ou 3.000,50.', 'error')
            return render_template('settings.html', form=form, goal=goal)

        if working_days_month <= 0 or working_days_month > 31:
            flash('Informe uma quantidade válida de dias trabalhados no mês.', 'error')
            return render_template('settings.html', form=form, goal=goal)

        if use_commission and (
            commission_percent is None or commission_percent < 0 or commission_percent > 100
        ):
            flash('Informe uma comissão válida entre 0 e 100.', 'error')
            return render_template('settings.html', form=form, goal=goal)

        goal.target_income_month = target_income_month
        goal.commission_percent = commission_percent
        goal.working_days_month = working_days_month
        goal.target_sales_month = calculate_month_sales_target(
            goal.target_income_month,
            goal.commission_percent,
        )
        goal.target_sales_day = calculate_day_sales_target(
            goal.target_sales_month,
            goal.working_days_month,
        )

        db.session.commit()

        flash('Configurações atualizadas com sucesso.', 'success')
        return redirect(url_for('main.settings'))

    return render_template('settings.html', form=form, goal=goal)


@main_bp.route('/admin/leads')
@admin_required
def admin_dashboard():
    search = request.args.get('q', '').strip()

    leads_query = Lead.query.order_by(Lead.created_at.desc())
    users_query = User.query.order_by(User.created_at.desc())
    payments_query = Payment.query.order_by(Payment.created_at.desc())

    if search:
        like = f'%{search}%'

        leads_query = leads_query.filter(
            (Lead.name.ilike(like))
            | (Lead.email.ilike(like))
            | (Lead.whatsapp.ilike(like))
        )

        users_query = users_query.filter(
            (User.name.ilike(like))
            | (User.email.ilike(like))
            | (User.whatsapp.ilike(like))
        )

    leads = leads_query.limit(100).all()
    users = users_query.limit(100).all()
    payments = payments_query.limit(50).all()

    stats = {
        'total_leads': Lead.query.count(),
        'total_users': User.query.filter_by(is_admin=False).count(),
        'blocked_users': User.query.filter_by(is_blocked=True, is_admin=False).count(),
        'pending_payments': Payment.query.filter_by(status='pending').count(),
    }

    access_form = AdminAccessForm()
    now = datetime.utcnow()

    return render_template(
        'admin/dashboard.html',
        leads=leads,
        users=users,
        payments=payments,
        stats=stats,
        access_form=access_form,
        now=now,
        search=search,
    )


@main_bp.route('/admin/user/<int:user_id>/toggle-block', methods=['POST'])
@admin_required
def toggle_user_block(user_id: int):
    user = db.session.get(User, user_id)

    if not user:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    if user.is_admin:
        flash('Não é permitido bloquear o administrador.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    desired_state = request.form.get('action', 'toggle')
    reason = request.form.get('reason', '').strip() or 'Bloqueio manual realizado pelo administrador.'

    if desired_state == 'block':
        user.is_blocked = True
        user.access_blocked_at = datetime.utcnow()
        user.blocked_reason = reason
        flash('Usuário bloqueado com sucesso.', 'success')

    elif desired_state == 'unblock':
        user.is_blocked = False
        user.blocked_reason = None
        user.access_blocked_at = None

        if not user.paid_until or user.paid_until < datetime.utcnow():
            user.paid_until = datetime.utcnow() + timedelta(days=30)

        flash('Usuário desbloqueado com sucesso.', 'success')

    else:
        user.is_blocked = not user.is_blocked

        if user.is_blocked:
            user.access_blocked_at = datetime.utcnow()
            user.blocked_reason = reason
        else:
            user.blocked_reason = None
            user.access_blocked_at = None

        flash('Status de acesso atualizado com sucesso.', 'success')

    db.session.commit()

    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/user/<int:user_id>/grant-access', methods=['POST'])
@admin_required
def grant_user_access(user_id: int):
    user = db.session.get(User, user_id)

    if not user:
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    if user.is_admin:
        flash('O administrador não precisa desta ação.', 'info')
        return redirect(url_for('main.admin_dashboard'))

    days = _safe_int(request.form.get('paid_days'), 30)
    reason = request.form.get('reason', '').strip() or 'Liberação manual de acesso pelo administrador.'

    if days <= 0:
        flash('Informe uma quantidade de dias válida.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    base_date = (
        user.paid_until
        if user.paid_until and user.paid_until > datetime.utcnow()
        else datetime.utcnow()
    )

    user.paid_until = base_date + timedelta(days=days)
    user.is_blocked = False
    user.access_blocked_at = None
    user.blocked_reason = None

    payment = Payment(
        user_id=user.id,
        amount=0,
        status='manual_release',
        gateway='admin',
        external_reference=f'admin-{user.id}-{int(datetime.utcnow().timestamp())}',
        paid_at=datetime.utcnow(),
        due_date=user.paid_until,
    )

    db.session.add(payment)
    db.session.commit()

    flash(f'Acesso liberado por {days} dias. Motivo: {reason}', 'success')
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/finance')
@controle_required
def finance_dashboard():
    selected_month = _safe_int(request.args.get('month'), date.today().month)
    selected_year = _safe_int(request.args.get('year'), date.today().year)

    if selected_month < 1 or selected_month > 12:
        selected_month = date.today().month

    if selected_year < 2000 or selected_year > 2100:
        selected_year = date.today().year

    context = build_finance_context(
        user_id=current_user.id,
        year=selected_year,
        month=selected_month,
    )

    return render_template('finance/dashboard.html', **context)


@main_bp.route('/finance/new', methods=['GET', 'POST'])
@controle_required
def finance_new():
    form = FinanceTransactionForm()
    transaction_type = request.args.get('type', '').strip().lower()

    if request.method == 'GET':
        form.date.data = date.today()

        if transaction_type in ('income', 'expense'):
            form.type.data = transaction_type

        merchant_hint = request.args.get('merchant', '').strip()

        if merchant_hint:
            form.merchant.data = merchant_hint
            form.category.data = suggest_category(
                merchant_hint,
                form.type.data or 'expense',
                current_user.id,
            )

    if form.validate_on_submit():
        amount = _parse_decimal_input(request.form.get('amount'), None)

        if amount is None or amount <= 0:
            flash('Informe um valor válido. Ex.: 49,90 ou 1500.', 'error')
            return render_template('finance/form.html', form=form, editing=False)

        tx_type = form.type.data or 'expense'
        merchant = (form.merchant.data or '').strip()
        description = (form.description.data or '').strip()
        typed_category = (form.category.data or '').strip()

        suggested_category = suggest_category(
            ' '.join([merchant, description]),
            tx_type,
            current_user.id,
        )

        final_category = typed_category or suggested_category

        transaction = FinanceTransaction(
            user_id=current_user.id,
            type=tx_type,
            date=form.date.data or date.today(),
            amount=amount,
            merchant=merchant or None,
            category=final_category,
            ai_suggested_category=suggested_category,
            category_confirmed=bool(typed_category),
            payment_method=(form.payment_method.data or '').strip() or None,
            description=description or None,
        )

        db.session.add(transaction)
        db.session.commit()

        if not typed_category:
            flash(f'Lançamento salvo. A IA sugeriu a categoria: {suggested_category}.', 'success')
        else:
            flash('Lançamento financeiro salvo com sucesso.', 'success')

        return redirect(url_for('main.finance_dashboard'))

    return render_template('finance/form.html', form=form, editing=False)


@main_bp.route('/finance/<int:transaction_id>/edit', methods=['GET', 'POST'])
@controle_required
def finance_edit(transaction_id):
    transaction = FinanceTransaction.query.filter_by(
        id=transaction_id,
        user_id=current_user.id,
    ).first()

    if not transaction:
        flash('Lançamento não encontrado.', 'error')
        return redirect(url_for('main.finance_dashboard'))

    form = FinanceTransactionForm(obj=transaction)

    if request.method == 'GET':
        form.type.data = transaction.type
        form.date.data = transaction.date
        form.amount.data = str(transaction.amount).replace('.', ',')
        form.merchant.data = transaction.merchant or ''
        form.category.data = transaction.category or ''
        form.payment_method.data = transaction.payment_method or ''
        form.description.data = transaction.description or ''

    if form.validate_on_submit():
        amount = _parse_decimal_input(request.form.get('amount'), None)

        if amount is None or amount <= 0:
            flash('Informe um valor válido. Ex.: 49,90 ou 1500.', 'error')
            return render_template(
                'finance/form.html',
                form=form,
                editing=True,
                transaction=transaction,
            )

        tx_type = form.type.data or 'expense'
        merchant = (form.merchant.data or '').strip()
        description = (form.description.data or '').strip()
        typed_category = (form.category.data or '').strip()

        suggested_category = suggest_category(
            ' '.join([merchant, description]),
            tx_type,
            current_user.id,
        )

        final_category = typed_category or suggested_category

        transaction.type = tx_type
        transaction.date = form.date.data or date.today()
        transaction.amount = amount
        transaction.merchant = merchant or None
        transaction.category = final_category
        transaction.ai_suggested_category = suggested_category
        transaction.category_confirmed = bool(typed_category)
        transaction.payment_method = (form.payment_method.data or '').strip() or None
        transaction.description = description or None

        db.session.commit()

        flash('Lançamento atualizado com sucesso.', 'success')
        return redirect(url_for('main.finance_dashboard'))

    return render_template(
        'finance/form.html',
        form=form,
        editing=True,
        transaction=transaction,
    )


@main_bp.route('/finance/<int:transaction_id>/delete', methods=['POST'])
@controle_required
def finance_delete(transaction_id):
    transaction = FinanceTransaction.query.filter_by(
        id=transaction_id,
        user_id=current_user.id,
    ).first()

    if not transaction:
        flash('Lançamento não encontrado.', 'error')
        return redirect(url_for('main.finance_dashboard'))

    db.session.delete(transaction)
    db.session.commit()

    flash('Lançamento excluído com sucesso.', 'success')
    return redirect(url_for('main.finance_dashboard'))


@main_bp.route('/finance/send-summary', methods=['POST'])
@controle_required
def finance_send_summary():
    context = build_finance_context(current_user.id)

    sent, message = send_finance_summary_email(current_user, context)

    if sent:
        flash('Resumo financeiro enviado para seu e-mail.', 'success')
    else:
        current_app.logger.warning(
            'Resumo financeiro não enviado para %s: %s',
            current_user.email,
            message,
        )
        flash(
            'O resumo foi gerado, mas o e-mail não saiu. Verifique RESEND_API_KEY e MAIL_FROM_EMAIL.',
            'warning',
        )

    return redirect(url_for('main.finance_dashboard'))


@main_bp.route('/internal/rpa/send-finance-summaries', methods=['POST'])
@csrf.exempt
def rpa_send_finance_summaries():
    secret = current_app.config.get('RPA_SECRET', '').strip()
    received_secret = request.headers.get('X-RPA-SECRET', '').strip()

    if not secret or received_secret != secret:
        return jsonify({
            'ok': False,
            'message': 'Acesso não autorizado.',
        }), 401

    users = User.query.filter(
        User.is_admin.is_(False),
        User.plan_type == 'controle',
        User.is_blocked.is_(False),
    ).all()

    sent_count = 0
    failed_count = 0
    skipped_count = 0
    failures = []

    for user in users:
        try:
            if hasattr(user, 'can_access_system') and not user.can_access_system(datetime.utcnow()):
                skipped_count += 1
                continue

            context = build_finance_context(user.id)
            sent, message = send_finance_summary_email(user, context)

            if sent:
                sent_count += 1
            else:
                failed_count += 1
                failures.append({
                    'email': user.email,
                    'message': message,
                })

        except Exception as exc:
            current_app.logger.exception(
                'Erro no RPA financeiro para %s',
                getattr(user, 'email', 'email-desconhecido'),
            )

            failed_count += 1
            failures.append({
                'email': getattr(user, 'email', 'email-desconhecido'),
                'message': str(exc),
            })

    return jsonify({
        'ok': True,
        'sent': sent_count,
        'failed': failed_count,
        'skipped': skipped_count,
        'failures': failures[:10],
    }), 200


@main_bp.route('/assistant', methods=['GET', 'POST'])
@controle_required
def assistant():
    question = ''
    answer = ''
    context = build_finance_context(current_user.id)

    if request.method == 'POST':
        question = request.form.get('question', '').strip()

        if not question:
            flash('Digite uma pergunta para a IA G Tech.', 'error')
            return render_template(
                'assistant.html',
                question=question,
                answer=answer,
                finance=context,
            )

        context_text = (
            f"Resumo: {context.get('natural_summary')}. "
            f"Previsão: {context.get('forecast', {}).get('message')}. "
            f"Meta sugerida: {context.get('saving_goal')}. "
            f"Melhor dia de pagamento: {context.get('bill_day_hint')}."
        )

        ok, response = ask_ai(question, context=context_text)

        answer = (
            response
            if ok
            else 'Não consegui consultar a IA agora. Tente novamente em alguns instantes.'
        )

    return render_template(
        'assistant.html',
        question=question,
        answer=answer,
        finance=context,
    )


@main_bp.route('/payment')
def payment_checkout():
    plan = normalize_plan(
        request.args.get('plan') or getattr(current_user, 'plan_type', 'metasimples')
    )
    billing = normalize_billing(request.args.get('billing') or 'mensal')

    if not current_user.is_authenticated:
        flash('Crie sua conta para vincular o pagamento ao seu acesso.', 'info')
        return redirect(url_for('auth.register', plan=plan, billing=billing))

    if not current_user.is_admin and current_user.plan_type != plan:
        flash('Esse pagamento pertence a outro produto. Abrimos o plano correto da sua conta.', 'warning')
        plan = current_user.plan_type

    ok, result = create_mercadopago_preference(current_user, plan, billing)

    if not ok:
        flash(f'Não conseguimos iniciar o pagamento: {result}', 'error')

        if current_user.is_authenticated and current_user.plan_type == 'controle':
            return redirect(url_for('main.finance_dashboard'))

        return redirect(url_for('main.index'))

    return redirect(result)


@main_bp.route('/payment/success')
@login_required
def payment_success():
    external_reference = request.args.get('external_reference', '')
    status = request.args.get('status', 'approved')
    collection_id = request.args.get('collection_id') or request.args.get('payment_id')

    payment = (
        Payment.query.filter_by(external_reference=external_reference).first()
        if external_reference
        else None
    )

    if collection_id:
        sync_mercadopago_payment(str(collection_id))

        if external_reference:
            payment = Payment.query.filter_by(external_reference=external_reference).first()

    if payment and (status == 'approved' or payment.status == 'approved'):
        approve_payment(payment, mp_payment_id=str(collection_id) if collection_id else None)
        db.session.commit()
        flash('Pagamento aprovado. Seu acesso foi liberado automaticamente.', 'success')
    else:
        flash(
            'Pagamento recebido pelo Mercado Pago. Assim que for aprovado, seu acesso será liberado.',
            'info',
        )

    if current_user.plan_type == 'controle':
        return redirect(url_for('main.finance_dashboard'))

    return redirect(url_for('main.dashboard'))


@main_bp.route('/payment/pending')
@login_required
def payment_pending():
    flash('Seu pagamento está pendente. Assim que for confirmado, o acesso será atualizado.', 'info')
    return redirect(url_for('main.blocked_access'))


@main_bp.route('/payment/failure')
@login_required
def payment_failure():
    flash('O pagamento não foi aprovado. Você pode tentar novamente com Pix ou cartão.', 'error')

    if current_user.is_authenticated and current_user.plan_type == 'controle':
        return redirect(url_for('main.finance_dashboard'))

    return redirect(url_for('main.index'))


@main_bp.route('/webhooks/mercadopago', methods=['POST'])
def mercadopago_webhook():
    payload = request.get_json(silent=True) or {}

    current_app.logger.info('Webhook Mercado Pago recebido: %s', payload)

    payment_id = None
    data = payload.get('data') if isinstance(payload, dict) else None

    if isinstance(data, dict):
        payment_id = data.get('id')

    payment_id = (
        payment_id
        or payload.get('id')
        or request.args.get('id')
        or request.args.get('data.id')
    )

    if payment_id:
        ok, message = sync_mercadopago_payment(str(payment_id))

        if not ok:
            current_app.logger.warning('Webhook Mercado Pago não sincronizou: %s', message)

    return {'status': 'received'}, 200