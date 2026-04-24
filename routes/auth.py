from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from database.db import db
from forms import LoginForm, RegisterForm
from models.goal import Goal
from models.lead import Lead
from models.user import User
from services.email_service import confirm_email_token, send_confirmation_email
from utils.validators import (
    format_whatsapp_br,
    is_valid_email,
    is_valid_whatsapp_br,
    normalize_email,
    normalize_whatsapp_br,
)


auth_bp = Blueprint('auth', __name__)


def _get_post_login_redirect(user_id: int):
    goal = Goal.query.filter_by(user_id=user_id).order_by(Goal.updated_at.desc()).first()

    if goal:
        return url_for('main.dashboard')

    return url_for('main.onboarding')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(_get_post_login_redirect(current_user.id))

    form = RegisterForm()

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        whatsapp = normalize_whatsapp_br(form.whatsapp.data)
        trial_days = int(current_app.config.get('DEFAULT_TRIAL_DAYS', 7))

        if not is_valid_email(email, check_deliverability=False):
            flash('Informe um e-mail válido.', 'error')
            return render_template('register.html', form=form)

        if not is_valid_whatsapp_br(whatsapp):
            flash('Informe um WhatsApp válido no padrão do Brasil com DDD e 9 dígitos.', 'error')
            return render_template('register.html', form=form)

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            if not existing_user.email_verified:
                sent, message = send_confirmation_email(existing_user)
                existing_user.verification_sent_at = datetime.utcnow()
                db.session.commit()

                if sent:
                    flash('Este e-mail já estava cadastrado. Reenviamos a confirmação para seu e-mail.', 'info')
                else:
                    current_app.logger.warning(
                        'Falha ao reenviar confirmação para %s: %s',
                        existing_user.email,
                        message,
                    )
                    flash('Este e-mail já está cadastrado, mas não conseguimos reenviar a confirmação. Verifique o SMTP no Railway.', 'warning')

                return redirect(url_for('auth.login'))

            flash('Este e-mail já está cadastrado. Faça login.', 'error')
            return redirect(url_for('auth.login'))

        existing_whatsapp = User.query.filter_by(whatsapp=whatsapp).first()

        if existing_whatsapp:
            flash('Este WhatsApp já está cadastrado.', 'error')
            return render_template('register.html', form=form)

        now = datetime.utcnow()

        user = User(
            name=form.name.data.strip(),
            email=email,
            whatsapp=whatsapp,
            is_admin=False,
            is_active_account=True,
            is_blocked=False,
            email_verified=False,
            email_verified_at=None,
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
                    source='register',
                )
            )

        db.session.commit()

        sent, message = send_confirmation_email(user)

        if sent:
            flash('Conta criada. Enviamos um link de confirmação para o seu e-mail.', 'success')
        else:
            current_app.logger.warning(
                'Falha ao enviar confirmação para %s: %s',
                user.email,
                message,
            )
            flash('Conta criada, mas o e-mail de confirmação não foi enviado. Verifique as variáveis SMTP no Railway.', 'warning')

        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)


@auth_bp.route('/confirmar-email/<token>')
def confirm_email(token):
    email = confirm_email_token(token)

    if not email:
        flash('Link de confirmação inválido ou expirado. Solicite um novo link.', 'error')
        return redirect(url_for('auth.login'))

    email = normalize_email(email)
    user = User.query.filter_by(email=email).first()

    if not user:
        flash('Usuário não encontrado para este link.', 'error')
        return redirect(url_for('auth.register'))

    if user.email_verified:
        flash('Seu e-mail já estava confirmado. Faça login.', 'info')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    user.email_verified_at = datetime.utcnow()
    user.is_active_account = True
    user.is_blocked = False
    user.blocked_reason = None

    db.session.commit()

    flash('E-mail confirmado com sucesso. Agora você já pode entrar.', 'success')
    return redirect(url_for('auth.login'))


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
        flash('Este e-mail já está confirmado. Faça login.', 'info')
        return redirect(url_for('auth.login'))

    sent, message = send_confirmation_email(user)
    user.verification_sent_at = datetime.utcnow()
    db.session.commit()

    if sent:
        flash('Enviamos um novo link de confirmação para seu e-mail.', 'success')
    else:
        current_app.logger.warning(
            'Falha ao reenviar confirmação para %s: %s',
            user.email,
            message,
        )
        flash('Não conseguimos enviar o e-mail. Verifique as variáveis SMTP no Railway.', 'error')

    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_get_post_login_redirect(current_user.id))

    form = LoginForm()

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(form.password.data):
            flash('E-mail ou senha inválidos.', 'error')
            return render_template('login.html', form=form)

        if not user.is_admin and not user.email_verified:
            flash('Você precisa confirmar seu e-mail antes de entrar.', 'warning')
            return render_template('login.html', form=form, pending_email=email)

        if user.auto_block_if_needed():
            db.session.commit()

        if user.is_blocked:
            flash('Seu acesso está suspenso. Regularize o pagamento para voltar a usar o sistema.', 'error')
            return redirect(url_for('main.blocked_access'))

        login_user(user, remember=True)
        flash('Login realizado com sucesso.', 'success')

        return redirect(_get_post_login_redirect(user.id))

    return render_template('login.html', form=form)


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

    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()

        if not user or not user.is_admin or not user.check_password(form.password.data):
            flash('Credenciais administrativas inválidas.', 'error')
            return render_template('admin/login.html', form=form)

        user.email_verified = True
        user.email_verified_at = user.email_verified_at or datetime.utcnow()
        user.is_active_account = True
        user.is_blocked = False
        user.blocked_reason = None
        db.session.commit()

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