from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from database.db import db
from forms import LoginForm, RegisterForm
from models.goal import Goal
from models.lead import Lead
from models.user import User
from services.payment_service import normalize_billing, normalize_plan
from utils.validators import (
    format_whatsapp_br,
    is_valid_email,
    is_valid_whatsapp_br,
    normalize_email,
    normalize_whatsapp_br,
)

auth_bp = Blueprint('auth', __name__)


def _product_home_for(user: User):
    if user.is_admin:
        return url_for('main.admin_dashboard')

    if user.plan_type == 'controle':
        return url_for('main.finance_dashboard')

    goal = Goal.query.filter_by(user_id=user.id).order_by(Goal.updated_at.desc()).first()

    if goal:
        return url_for('main.dashboard')

    return url_for('main.onboarding')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(_product_home_for(current_user))

    form = RegisterForm()
    selected_plan = normalize_plan(request.values.get('plan'))
    selected_billing = normalize_billing(request.values.get('billing'))

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        whatsapp = normalize_whatsapp_br(form.whatsapp.data)
        trial_days = int(current_app.config.get('DEFAULT_TRIAL_DAYS', 7))

        if not is_valid_email(email, check_deliverability=False):
            flash('Informe um e-mail válido.', 'error')
            return render_template(
                'register.html',
                form=form,
                selected_plan=selected_plan,
                selected_billing=selected_billing,
            )

        if not is_valid_whatsapp_br(whatsapp):
            flash('Informe um WhatsApp válido no padrão do Brasil com DDD e 9 dígitos.', 'error')
            return render_template(
                'register.html',
                form=form,
                selected_plan=selected_plan,
                selected_billing=selected_billing,
            )

        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado. Faça login.', 'error')
            return redirect(url_for('auth.login', plan=selected_plan))

        if User.query.filter_by(whatsapp=whatsapp).first():
            flash('Este WhatsApp já está cadastrado.', 'error')
            return render_template(
                'register.html',
                form=form,
                selected_plan=selected_plan,
                selected_billing=selected_billing,
            )

        now = datetime.utcnow()
        payment_first = bool(current_app.config.get('PAYMENT_REQUIRED_BEFORE_ACCESS', False))

        user = User(
            name=form.name.data.strip(),
            email=email,
            whatsapp=whatsapp,
            plan_type=selected_plan,
            is_active_account=not payment_first,
            is_blocked=payment_first,
            blocked_reason='Aguardando confirmação de pagamento.' if payment_first else None,
            email_verified=True,
            email_verified_at=now,
            verification_sent_at=now,
            trial_started_at=now,
            trial_expires_at=now + timedelta(days=trial_days),
        )

        user.set_password(form.password.data)
        db.session.add(user)

        existing_lead = Lead.query.filter(
            (Lead.email == email) | (Lead.whatsapp == whatsapp)
        ).first()

        if not existing_lead:
            db.session.add(
                Lead(
                    name=user.name,
                    email=email,
                    whatsapp=whatsapp,
                    source=f'register_{selected_plan}',
                )
            )

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception('Erro ao salvar cadastro: %s', exc)
            flash('Não conseguimos criar sua conta agora. Revise os dados e tente novamente.', 'error')
            return render_template(
                'register.html',
                form=form,
                selected_plan=selected_plan,
                selected_billing=selected_billing,
            ), 500

        login_user(user, remember=True)

        flash(
            'Conta criada com sucesso. Você já pode usar o sistema durante o período de teste.',
            'success',
        )

        return redirect(_product_home_for(user))

    return render_template(
        'register.html',
        form=form,
        selected_plan=selected_plan,
        selected_billing=selected_billing,
    )


@auth_bp.route('/confirmar-email/<token>')
def confirm_email(token):
    flash('Confirmação automática temporariamente dispensada nesta fase de lançamento.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/reenviar-confirmacao', methods=['POST'])
def resend_confirmation():
    flash('Confirmação por e-mail será ativada após validação do domínio G Tech.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_product_home_for(current_user))

    form = LoginForm()
    selected_plan = normalize_plan(request.values.get('plan')) if request.values.get('plan') else None

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(form.password.data):
            flash('E-mail ou senha inválidos.', 'error')
            return render_template('login.html', form=form, selected_plan=selected_plan)

        if user.auto_block_if_needed():
            db.session.commit()

        if user.is_blocked:
            flash('Seu acesso está suspenso ou aguardando pagamento.', 'error')
            return redirect(url_for('main.blocked_access'))

        login_user(user, remember=True)

        if selected_plan and user.plan_type != selected_plan:
            flash('Essa conta pertence a outro produto. Abrimos o painel correto para evitar mistura.', 'warning')
        else:
            flash('Login realizado com sucesso.', 'success')

        return redirect(_product_home_for(user))

    return render_template('login.html', form=form, selected_plan=selected_plan)


@auth_bp.route('/esqueci-senha', methods=['GET', 'POST'])
def forgot_password():
    support_whatsapp = current_app.config.get('SUPPORT_WHATSAPP', '').strip()

    if request.method == 'POST':
        flash(
            'Recuperação automática por e-mail será ativada em breve. Para redefinir sua senha agora, fale com o suporte G Tech pelo WhatsApp.',
            'info',
        )

        if support_whatsapp:
            return redirect(f'https://wa.me/{support_whatsapp}')

        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html', support_whatsapp=support_whatsapp)


@auth_bp.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def reset_password(token):
    flash('Recuperação automática por e-mail será ativada em breve. Fale com o suporte G Tech.', 'info')
    return redirect(url_for('auth.forgot_password'))


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('main.admin_dashboard'))

    form = LoginForm()
    selected_plan = normalize_plan(request.values.get('plan')) if request.values.get('plan') else None

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        user = User.query.filter_by(email=email, is_admin=True).first()

        if not user or not user.check_password(form.password.data):
            flash('Credenciais administrativas inválidas.', 'error')
            return render_template('admin/login.html', form=form)

        login_user(user, remember=True)
        flash('Login administrativo realizado com sucesso.', 'success')
        return redirect(url_for('main.admin_dashboard'))

    return render_template('admin/login.html', form=form)


@auth_bp.route('/api/validate/email')
def validate_email_api():
    email = normalize_email(request.args.get('email', ''))
    exists_in_users = bool(User.query.filter_by(email=email).first()) if email else False
    exists_in_leads = bool(Lead.query.filter_by(email=email).first()) if email else False

    return {
        'valid': is_valid_email(email, check_deliverability=False),
        'exists': exists_in_users or exists_in_leads,
    }


@auth_bp.route('/api/validate/whatsapp')
def validate_whatsapp_api():
    whatsapp = normalize_whatsapp_br(request.args.get('whatsapp', ''))
    exists_in_users = bool(User.query.filter_by(whatsapp=whatsapp).first()) if whatsapp else False
    exists_in_leads = bool(Lead.query.filter_by(whatsapp=whatsapp).first()) if whatsapp else False

    return {
        'valid': is_valid_whatsapp_br(whatsapp),
        'exists': exists_in_users or exists_in_leads,
        'formatted': format_whatsapp_br(whatsapp),
    }