from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from database.db import db
from forms import LoginForm, RegisterForm
from models.goal import Goal
from models.lead import Lead
from models.user import User
from services.email_service import (
    confirm_email_token,
    generate_password_reset_token,
    reset_password_token_email,
    send_password_reset_email,
    send_welcome_email,
)
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
            return redirect(url_for('auth.login'))

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
            email_verified=False,
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

        try:
            sent, message = send_welcome_email(user)
        except Exception as exc:
            sent = False
            message = str(exc)
            current_app.logger.exception('Erro inesperado ao enviar confirmação para %s', user.email)

        if sent:
            flash('Conta criada. Enviamos um link de confirmação para seu e-mail. Confirme antes de acessar.', 'success')
        else:
            current_app.logger.warning('Conta criada, mas falha ao enviar e-mail para %s: %s', user.email, message)
            flash('Conta criada, mas o e-mail não foi enviado. Você pode reenviar pela tela de login.', 'warning')

        return redirect(url_for('auth.login', plan=selected_plan))

    return render_template(
        'register.html',
        form=form,
        selected_plan=selected_plan,
        selected_billing=selected_billing,
    )


@auth_bp.route('/confirmar-email/<token>')
def confirm_email(token):
    email = confirm_email_token(token)

    if not email:
        flash('Link de confirmação inválido ou expirado. Solicite um novo link.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=normalize_email(email)).first()

    if not user:
        flash('Usuário não encontrado para este link.', 'error')
        return redirect(url_for('auth.register'))

    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    user.verification_sent_at = user.verification_sent_at or datetime.utcnow()
    db.session.commit()

    flash('E-mail confirmado com sucesso. Agora você pode acessar o sistema.', 'success')
    return redirect(url_for('auth.login', plan=user.plan_type))


@auth_bp.route('/reenviar-confirmacao', methods=['POST'])
def resend_confirmation():
    email = normalize_email(request.form.get('email', ''))

    if not email:
        flash('Informe seu e-mail para reenviar a confirmação.', 'error')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()

    if not user:
        flash('Não encontramos uma conta com este e-mail.', 'error')
        return redirect(url_for('auth.login'))

    if user.email_verified:
        flash('Este e-mail já foi confirmado. Faça login normalmente.', 'info')
        return redirect(url_for('auth.login', plan=user.plan_type))

    try:
        sent, message = send_welcome_email(user)
    except Exception as exc:
        sent = False
        message = str(exc)
        current_app.logger.exception('Erro inesperado ao reenviar confirmação para %s', user.email)

    user.verification_sent_at = datetime.utcnow()
    db.session.commit()

    if sent:
        flash('Enviamos um novo link de confirmação para seu e-mail.', 'success')
    else:
        current_app.logger.warning('Falha ao reenviar confirmação para %s: %s', user.email, message)
        flash('Não conseguimos enviar o e-mail agora, mas sua conta continua criada. Fale com o suporte G Tech.', 'warning')

    return redirect(url_for('auth.login', plan=user.plan_type))


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

        if not user.is_admin and not user.email_verified:
            flash('Confirme seu e-mail antes de acessar o sistema. Enviamos o link no cadastro.', 'warning')
            return render_template(
                'login.html',
                form=form,
                selected_plan=selected_plan or user.plan_type,
                pending_verification_email=user.email,
            )

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
    if current_user.is_authenticated:
        return redirect(_product_home_for(current_user))

    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))

        if not email:
            flash('Informe seu e-mail.', 'error')
            return render_template('forgot_password.html')

        user = User.query.filter_by(email=email).first()

        if user:
            try:
                sent, message = send_password_reset_email(user)
                if not sent:
                    current_app.logger.warning('Falha ao enviar recuperação para %s: %s', user.email, message)
            except Exception as exc:
                current_app.logger.exception('Erro inesperado ao enviar recuperação para %s: %s', email, exc)

        flash('Se este e-mail estiver cadastrado, enviaremos um link para redefinir a senha.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')


@auth_bp.route('/redefinir-senha/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = reset_password_token_email(token)

    if not email:
        flash('Link de recuperação inválido ou expirado. Solicite um novo link.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=normalize_email(email)).first()

    if not user:
        flash('Usuário não encontrado para este link.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')

        if len(password) < 8:
            flash('A nova senha precisa ter pelo menos 8 caracteres.', 'error')
            return render_template('reset_password.html', token=token)

        if password != password_confirm:
            flash('As senhas não conferem.', 'error')
            return render_template('reset_password.html', token=token)

        user.set_password(password)
        db.session.commit()

        flash('Senha alterada com sucesso. Faça login com sua nova senha.', 'success')
        return redirect(url_for('auth.login', plan=user.plan_type))

    return render_template('reset_password.html', token=token)


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