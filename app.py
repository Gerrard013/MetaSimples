import os

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config.settings import Config
from database.db import csrf, db, login_manager, migrate
from models.user import User
from routes.auth import auth_bp
from routes.main import main_bp



def ensure_admin_user(app: Flask) -> None:
    with app.app_context():
        admin_email = app.config.get('ADMIN_EMAIL')
        admin_password = app.config.get('ADMIN_PASSWORD')
        existing_admin = User.query.filter_by(email=admin_email).first()
        if not existing_admin:
            admin = User(
                name='Administrador MetaSimples',
                email=admin_email,
                is_admin=True,
                is_blocked=False,
                whatsapp=None,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()



def ensure_schema_updates(app: Flask) -> None:
    """Atualizações seguras para produção/local sem precisar rodar Alembic manual agora."""
    with app.app_context():
        engine_name = db.engine.url.get_backend_name()
        with db.engine.begin() as conn:
            if engine_name.startswith('postgresql'):
                user_columns = {
                    'whatsapp': "ALTER TABLE users ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(20)",
                    'plan_type': "ALTER TABLE users ADD COLUMN IF NOT EXISTS plan_type VARCHAR(30) NOT NULL DEFAULT 'metasimples'",
                    'is_active_account': "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active_account BOOLEAN NOT NULL DEFAULT TRUE",
                    'is_blocked': "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT FALSE",
                    'blocked_reason': "ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked_reason VARCHAR(255)",
                    'email_verified': "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE",
                    'email_verified_at': "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP",
                    'verification_sent_at': "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_sent_at TIMESTAMP",
                    'trial_started_at': "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                    'trial_expires_at': "ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_expires_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP + INTERVAL '7 days')",
                    'paid_until': "ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_until TIMESTAMP",
                    'access_blocked_at': "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_blocked_at TIMESTAMP",
                }
                for sql in user_columns.values():
                    conn.exec_driver_sql(sql)
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_users_plan_type ON users(plan_type)",
                    "CREATE INDEX IF NOT EXISTS idx_users_email_verified ON users(email_verified)",
                    "CREATE INDEX IF NOT EXISTS idx_users_is_blocked ON users(is_blocked)",
                    "CREATE INDEX IF NOT EXISTS idx_users_whatsapp ON users(whatsapp)",
                ]:
                    conn.exec_driver_sql(idx_sql)

                conn.exec_driver_sql("""
                    CREATE TABLE IF NOT EXISTS finance_transactions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        type VARCHAR(20) NOT NULL,
                        date DATE NOT NULL,
                        amount NUMERIC(10,2) NOT NULL DEFAULT 0,
                        merchant VARCHAR(120),
                        category VARCHAR(80) NOT NULL DEFAULT 'Outros',
                        ai_suggested_category VARCHAR(80),
                        category_confirmed BOOLEAN NOT NULL DEFAULT TRUE,
                        description VARCHAR(255),
                        payment_method VARCHAR(80),
                        is_recurring BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                for column, sql_type in {
                    'merchant': 'VARCHAR(120)',
                    'ai_suggested_category': 'VARCHAR(80)',
                    'category_confirmed': 'BOOLEAN NOT NULL DEFAULT TRUE',
                    'is_recurring': 'BOOLEAN NOT NULL DEFAULT FALSE',
                }.items():
                    conn.exec_driver_sql(f"ALTER TABLE finance_transactions ADD COLUMN IF NOT EXISTS {column} {sql_type}")
                for idx_sql in [
                    "CREATE INDEX IF NOT EXISTS idx_finance_transactions_user_id ON finance_transactions(user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_finance_transactions_date ON finance_transactions(date)",
                    "CREATE INDEX IF NOT EXISTS idx_finance_transactions_type ON finance_transactions(type)",
                    "CREATE INDEX IF NOT EXISTS idx_finance_transactions_category ON finance_transactions(category)",
                    "CREATE INDEX IF NOT EXISTS idx_finance_transactions_merchant ON finance_transactions(merchant)",
                ]:
                    conn.exec_driver_sql(idx_sql)

                payment_cols = {
                    'net_amount': 'NUMERIC(10,2)',
                    'fee_amount': 'NUMERIC(10,2)',
                    'gateway_payment_id': 'VARCHAR(120)',
                    'plan_type': 'VARCHAR(30)',
                    'billing_cycle': 'VARCHAR(30)',
                    'duration_days': 'INTEGER',
                }
                for column, sql_type in payment_cols.items():
                    conn.exec_driver_sql(f"ALTER TABLE payments ADD COLUMN IF NOT EXISTS {column} {sql_type}")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_payments_gateway_payment_id ON payments(gateway_payment_id)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_payments_plan_type ON payments(plan_type)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_payments_billing_cycle ON payments(billing_cycle)")
            else:
                user_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()]
                sqlite_user_adds = {
                    'whatsapp': "ALTER TABLE users ADD COLUMN whatsapp VARCHAR(20)",
                    'plan_type': "ALTER TABLE users ADD COLUMN plan_type VARCHAR(30) NOT NULL DEFAULT 'metasimples'",
                    'is_active_account': "ALTER TABLE users ADD COLUMN is_active_account BOOLEAN NOT NULL DEFAULT 1",
                    'is_blocked': "ALTER TABLE users ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0",
                    'blocked_reason': "ALTER TABLE users ADD COLUMN blocked_reason VARCHAR(255)",
                    'email_verified': "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0",
                    'email_verified_at': "ALTER TABLE users ADD COLUMN email_verified_at DATETIME",
                    'verification_sent_at': "ALTER TABLE users ADD COLUMN verification_sent_at DATETIME",
                    'trial_started_at': "ALTER TABLE users ADD COLUMN trial_started_at DATETIME",
                    'trial_expires_at': "ALTER TABLE users ADD COLUMN trial_expires_at DATETIME",
                    'paid_until': "ALTER TABLE users ADD COLUMN paid_until DATETIME",
                    'access_blocked_at': "ALTER TABLE users ADD COLUMN access_blocked_at DATETIME",
                }
                for column, sql in sqlite_user_adds.items():
                    if column not in user_cols:
                        conn.exec_driver_sql(sql)

                finance_tables = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='finance_transactions'").fetchall()
                if finance_tables:
                    finance_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(finance_transactions)").fetchall()]
                    sqlite_finance_adds = {
                        'merchant': "ALTER TABLE finance_transactions ADD COLUMN merchant VARCHAR(120)",
                        'ai_suggested_category': "ALTER TABLE finance_transactions ADD COLUMN ai_suggested_category VARCHAR(80)",
                        'category_confirmed': "ALTER TABLE finance_transactions ADD COLUMN category_confirmed BOOLEAN NOT NULL DEFAULT 1",
                        'is_recurring': "ALTER TABLE finance_transactions ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT 0",
                    }
                    for column, sql in sqlite_finance_adds.items():
                        if column not in finance_cols:
                            conn.exec_driver_sql(sql)

                payment_tables = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'").fetchall()
                if payment_tables:
                    payment_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(payments)").fetchall()]
                    sqlite_payment_adds = {
                        'net_amount': "ALTER TABLE payments ADD COLUMN net_amount NUMERIC(10,2)",
                        'fee_amount': "ALTER TABLE payments ADD COLUMN fee_amount NUMERIC(10,2)",
                        'gateway_payment_id': "ALTER TABLE payments ADD COLUMN gateway_payment_id VARCHAR(120)",
                        'plan_type': "ALTER TABLE payments ADD COLUMN plan_type VARCHAR(30)",
                        'billing_cycle': "ALTER TABLE payments ADD COLUMN billing_cycle VARCHAR(30)",
                        'duration_days': "ALTER TABLE payments ADD COLUMN duration_days INTEGER",
                    }
                    for column, sql in sqlite_payment_adds.items():
                        if column not in payment_cols:
                            conn.exec_driver_sql(sql)

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
    ensure_schema_updates(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    ensure_admin_user(app)

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
