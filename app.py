import os
from datetime import datetime

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config.settings import Config
from database.db import csrf, db, login_manager, migrate
from models.user import User
from routes.auth import auth_bp
from routes.main import main_bp


def ensure_admin_user(app: Flask) -> None:
    with app.app_context():
        admin_email = (app.config.get('ADMIN_EMAIL') or '').strip().lower()
        admin_password = app.config.get('ADMIN_PASSWORD')

        if not admin_email or not admin_password:
            app.logger.warning('ADMIN_EMAIL ou ADMIN_PASSWORD não configurados.')
            return

        app.logger.info('Verificando administrador padrão...')
        app.logger.info('ADMIN_EMAIL configurado: %s', admin_email)

        admin_user = User.query.filter_by(is_admin=True).first()
        admin_by_email = User.query.filter_by(email=admin_email).first()

        if admin_user and admin_by_email and admin_user.id != admin_by_email.id:
            app.logger.warning(
                'Conflito de admins detectado. O admin principal será mantido e o email configurado será sincronizado.'
            )

        if admin_user:
            if admin_user.email != admin_email:
                existing_with_target_email = User.query.filter_by(email=admin_email).first()

                if existing_with_target_email and existing_with_target_email.id != admin_user.id:
                    existing_with_target_email.is_admin = False
                    db.session.add(existing_with_target_email)
                    app.logger.info(
                        'Removendo privilégio admin de usuário antigo com email %s',
                        existing_with_target_email.email
                    )

                admin_user.email = admin_email

            admin_user.name = 'Administrador MetaSimples'
            admin_user.is_admin = True
            admin_user.is_active_account = True
            admin_user.is_blocked = False
            admin_user.blocked_reason = None
            admin_user.email_verified = True

            if not admin_user.email_verified_at:
                admin_user.email_verified_at = datetime.utcnow()

            admin_user.set_password(admin_password)

            db.session.add(admin_user)
            db.session.commit()

            app.logger.info('Administrador sincronizado com sucesso: %s', admin_user.email)
            return

        if admin_by_email:
            admin_by_email.name = 'Administrador MetaSimples'
            admin_by_email.is_admin = True
            admin_by_email.is_active_account = True
            admin_by_email.is_blocked = False
            admin_by_email.blocked_reason = None
            admin_by_email.email_verified = True

            if not admin_by_email.email_verified_at:
                admin_by_email.email_verified_at = datetime.utcnow()

            admin_by_email.set_password(admin_password)

            db.session.add(admin_by_email)
            db.session.commit()

            app.logger.info('Usuário promovido a administrador com sucesso: %s', admin_by_email.email)
            return

        admin = User(
            name='Administrador MetaSimples',
            email=admin_email,
            is_admin=True,
            is_active_account=True,
            is_blocked=False,
            whatsapp=None,
            email_verified=True,
            email_verified_at=datetime.utcnow(),
        )
        admin.set_password(admin_password)

        db.session.add(admin)
        db.session.commit()

        app.logger.info('Administrador criado com sucesso: %s', admin.email)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    with app.app_context():
        import models  # noqa: F401
        db.create_all()
        ensure_admin_user(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app


app = create_app()


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=debug_mode)