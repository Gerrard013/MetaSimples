import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from database.db import db
from forms import ChecklistForm, DailyResultForm, GoalForm
from models.checklist import ChecklistEntry
from models.daily_result import DailyResult
from models.goal import Goal
from models.lead import Lead
from models.payment import Payment
from models.user import User
from services.calculations import (
    calculate_day_sales_target,
    calculate_earnings_from_sales,
    calculate_month_sales_target,
)
from services.dashboard_service import build_dashboard_context

main_bp = Blueprint('main', __name__)


def _now():
    return datetime.utcnow()


def _today():
    return date.today()


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


def format_brl(value):
    numeric_value = _safe_float(value, 0.0)
    return f"R$ {numeric_value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def get_user_goal(user_id):
    return Goal.query.filter_by(user_id=user_id).order_by(Goal.updated_at.desc()).first()


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            flash('Acesso restrito ao administrador.', 'error')
            return redirect(url_for('auth.admin_login'))
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
        'static',
    }

    endpoint = request.endpoint or ''

    if endpoint in open_endpoints or endpoint.startswith('auth.validate_'):
        return None

    if getattr(current_user, 'auto_block_if_needed', None):
        if current_user.auto_block_if_needed():
            db.session.commit()

    if getattr(current_user, 'is_blocked', False):
        logout_user()
        return redirect(url_for('main.blocked_access'))

    return None


@main_bp.app_context_processor
def inject_helpers():
    payment_url = os.getenv('PAYMENT_URL', '#')
    return {
        'format_brl': format_brl,
        'payment_url': payment_url,
    }


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('main.admin_dashboard'))

        goal = get_user_goal(current_user.id)
        if goal:
            return redirect(url_for('main.dashboard'))
        return redirect(url_for('main.onboarding'))

    return render_template('index.html')


@main_bp.route('/blocked-access')
def blocked_access():
    return render_template('blocked_access.html')


@main_bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    form = GoalForm()
    goal = get_user_goal(current_user.id)

    if request.method == 'GET' and goal:
        form.target_income_month.data = format_brl(goal.target_income_month)
        form.use_commission.data = _safe_float(goal.commission_percent, 0) > 0
        form.commission_percent.data = str(goal.commission_percent or '')
        form.working_days_month.data = goal.working_days_month

    if form.validate_on_submit():
        target_income_month = _parse_decimal_input(form.target_income_month.data, 0.0)
        commission_percent = _parse_decimal_input(form.commission_percent.data, 0.0) if form.use_commission.data else 0.0
        working_days_month = _safe_int(form.working_days_month.data, 22)

        target_sales_month = calculate_month_sales_target(target_income_month, commission_percent)
        target_sales_day = calculate_day_sales_target(target_sales_month, working_days_month)

        if goal is None:
            goal = Goal(user_id=current_user.id)

        goal.target_income_month = target_income_month
        goal.commission_percent = commission_percent
        goal.working_days_month = working_days_month
        goal.target_sales_month = target_sales_month
        goal.target_sales_day = target_sales_day

        db.session.add(goal)
        db.session.commit()

        flash('Meta salva com sucesso. Seu painel já está liberado.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('onboarding.html', form=form, has_goal=bool(goal))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    goal = get_user_goal(current_user.id)
    if not goal:
        flash('Antes de continuar, preencha sua meta inicial para liberar o painel.', 'info')
        return redirect(url_for('main.onboarding'))

    context = build_dashboard_context(current_user.id, goal)
    context['goal'] = goal
    context['now'] = _now()

    return render_template('dashboard.html', **context)


@main_bp.route('/daily-entry', methods=['GET', 'POST'])
@login_required
def daily_entry():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    goal = get_user_goal(current_user.id)
    if not goal:
        flash('Antes de lançar resultados, preencha sua meta inicial.', 'info')
        return redirect(url_for('main.onboarding'))

    form = DailyResultForm()
    today = _today()
    existing = DailyResult.query.filter_by(user_id=current_user.id, date=today).first()

    if request.method == 'GET':
        form.date.data = today
        if existing:
            form.sales_value.data = format_brl(existing.sales_value)
            form.attendance_count.data = existing.attendance_count
            form.closed_deals.data = existing.closed_deals
            form.notes.data = getattr(existing, 'notes', None)

    if form.validate_on_submit():
        target_date = form.date.data or today
        sales_value = _parse_decimal_input(form.sales_value.data, 0.0)
        attendance_count = _safe_int(form.attendance_count.data, 0)
        closed_deals = _safe_int(form.closed_deals.data, 0)
        notes = form.notes.data.strip() if form.notes.data else None

        record = DailyResult.query.filter_by(user_id=current_user.id, date=target_date).first()
        if record is None:
            record = DailyResult(user_id=current_user.id, date=target_date)

        record.sales_value = sales_value
        record.earnings_value = calculate_earnings_from_sales(sales_value, _safe_float(goal.commission_percent, 0))
        record.attendance_count = attendance_count
        record.closed_deals = closed_deals

        if hasattr(record, 'notes'):
            record.notes = notes

        db.session.add(record)
        db.session.commit()

        flash('Resultado do dia salvo com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('daily_entry.html', form=form, goal=goal, existing=existing)


@main_bp.route('/checklist', methods=['GET', 'POST'])
@login_required
def checklist():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    goal = get_user_goal(current_user.id)
    if not goal:
        flash('Antes de usar o checklist, preencha sua meta inicial.', 'info')
        return redirect(url_for('main.onboarding'))

    form = ChecklistForm()
    today = _today()
    existing = ChecklistEntry.query.filter_by(user_id=current_user.id, date=today).first()

    if request.method == 'GET':
        form.date.data = today
        if existing:
            form.leads_answered.data = existing.leads_answered
            form.follow_up_done.data = existing.follow_up_done
            form.proposals_sent.data = existing.proposals_sent
            form.post_sale_done.data = existing.post_sale_done
            form.goal_reviewed.data = existing.goal_reviewed

    if form.validate_on_submit():
        target_date = form.date.data or today

        entry = ChecklistEntry.query.filter_by(user_id=current_user.id, date=target_date).first()
        if entry is None:
            entry = ChecklistEntry(user_id=current_user.id, date=target_date)

        entry.leads_answered = bool(form.leads_answered.data)
        entry.follow_up_done = bool(form.follow_up_done.data)
        entry.proposals_sent = bool(form.proposals_sent.data)
        entry.post_sale_done = bool(form.post_sale_done.data)
        entry.goal_reviewed = bool(form.goal_reviewed.data)

        db.session.add(entry)
        db.session.commit()

        flash('Checklist salvo com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('checklist.html', form=form, goal=goal, existing=existing)


@main_bp.route('/history')
@login_required
def history():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    goal = get_user_goal(current_user.id)
    if not goal:
        flash('Antes de acessar o histórico, preencha sua meta inicial.', 'info')
        return redirect(url_for('main.onboarding'))

    records = (
        DailyResult.query
        .filter_by(user_id=current_user.id)
        .order_by(DailyResult.date.desc())
        .all()
    )

    return render_template('history.html', records=records, goal=goal)


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    form = GoalForm()
    goal = get_user_goal(current_user.id)

    if request.method == 'GET' and goal:
        form.target_income_month.data = format_brl(goal.target_income_month)
        form.use_commission.data = _safe_float(goal.commission_percent, 0) > 0
        form.commission_percent.data = str(goal.commission_percent or '')
        form.working_days_month.data = goal.working_days_month

    if form.validate_on_submit():
        target_income_month = _parse_decimal_input(form.target_income_month.data, 0.0)
        commission_percent = _parse_decimal_input(form.commission_percent.data, 0.0) if form.use_commission.data else 0.0
        working_days_month = _safe_int(form.working_days_month.data, 22)

        target_sales_month = calculate_month_sales_target(target_income_month, commission_percent)
        target_sales_day = calculate_day_sales_target(target_sales_month, working_days_month)

        if goal is None:
            goal = Goal(user_id=current_user.id)

        goal.target_income_month = target_income_month
        goal.commission_percent = commission_percent
        goal.working_days_month = working_days_month
        goal.target_sales_month = target_sales_month
        goal.target_sales_day = target_sales_day

        db.session.add(goal)
        db.session.commit()

        flash('Configurações e metas salvas com sucesso.', 'success')
        return redirect(url_for('main.dashboard'))

    if not goal:
        flash('Você ainda não definiu sua meta. Preencha abaixo para liberar seu painel.', 'info')

    return render_template('settings.html', form=form, has_goal=bool(goal))


@main_bp.route('/payment')
@login_required
def payment_redirect():
    payment_url = os.getenv('PAYMENT_URL', '#')
    return redirect(payment_url)


@main_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    search = request.args.get('q', '').strip()

    users_query = User.query.order_by(User.created_at.desc())
    leads_query = Lead.query.order_by(Lead.created_at.desc())
    payments_query = Payment.query.order_by(Payment.created_at.desc())

    if search:
        like = f'%{search}%'
        users_query = users_query.filter(
            db.or_(
                User.name.ilike(like),
                User.email.ilike(like),
                User.whatsapp.ilike(like),
            )
        )
        leads_query = leads_query.filter(
            db.or_(
                Lead.name.ilike(like),
                Lead.email.ilike(like),
                Lead.whatsapp.ilike(like),
            )
        )

    users = users_query.all()
    leads = leads_query.limit(100).all()
    payments = payments_query.limit(100).all()

    stats = {
        'total_leads': Lead.query.count(),
        'total_users': User.query.filter_by(is_admin=False).count(),
        'blocked_users': User.query.filter_by(is_blocked=True, is_admin=False).count(),
        'pending_payments': Payment.query.filter_by(status='pending').count(),
    }

    return render_template(
        'admin/dashboard.html',
        users=users,
        leads=leads,
        payments=payments,
        stats=stats,
        search=search,
        now=_now(),
    )


@main_bp.route('/admin/users/<int:user_id>/toggle-block', methods=['POST'])
@admin_required
def toggle_user_block(user_id):
    user = User.query.get_or_404(user_id)

    if user.is_admin:
        flash('Não é permitido bloquear o administrador.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    action = request.form.get('action', '').strip()
    reason = request.form.get('reason', '').strip()

    if action == 'block':
        user.is_blocked = True
        user.is_active_account = False
        user.access_blocked_at = _now()
        user.blocked_reason = reason or 'Acesso bloqueado pelo administrador.'
        flash(f'Acesso de {user.name} bloqueado com sucesso.', 'success')
    elif action == 'unblock':
        user.is_blocked = False
        user.is_active_account = True
        user.access_blocked_at = None
        user.blocked_reason = None
        flash(f'Acesso de {user.name} desbloqueado com sucesso.', 'success')
    else:
        flash('Ação inválida.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    db.session.commit()
    return redirect(url_for('main.admin_dashboard'))


@main_bp.route('/admin/users/<int:user_id>/grant-access', methods=['POST'])
@admin_required
def grant_user_access(user_id):
    user = User.query.get_or_404(user_id)

    if user.is_admin:
        flash('Essa ação não se aplica ao administrador.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    reason = request.form.get('reason', '').strip()
    paid_days_raw = request.form.get('paid_days', '30').strip()

    try:
        paid_days = int(paid_days_raw)
    except ValueError:
        flash('Informe uma quantidade de dias válida.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    if paid_days <= 0:
        flash('A quantidade de dias deve ser maior que zero.', 'error')
        return redirect(url_for('main.admin_dashboard'))

    base_date = _now()
    if user.paid_until and user.paid_until > base_date:
        base_date = user.paid_until

    user.paid_until = base_date + timedelta(days=paid_days)
    user.is_blocked = False
    user.is_active_account = True
    user.access_blocked_at = None
    user.blocked_reason = None

    payment = Payment(
        user_id=user.id,
        amount=0,
        status='paid',
        due_date=user.paid_until,
    )

    db.session.add(payment)
    db.session.add(user)
    db.session.commit()

    if reason:
        flash(f'Acesso de {user.name} liberado por {paid_days} dias. Motivo: {reason}', 'success')
    else:
        flash(f'Acesso de {user.name} liberado por {paid_days} dias.', 'success')

    return redirect(url_for('main.admin_dashboard'))