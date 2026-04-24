from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    whatsapp = db.Column(db.String(20), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    is_blocked = db.Column(db.Boolean, nullable=False, default=False, index=True)
    blocked_reason = db.Column(db.String(255), nullable=True)

    email_verified = db.Column(db.Boolean, nullable=False, default=False, index=True)
    email_verified_at = db.Column(db.DateTime, nullable=True)
    verification_sent_at = db.Column(db.DateTime, nullable=True)

    trial_started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    trial_expires_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.utcnow() + timedelta(days=7),
        index=True,
    )

    paid_until = db.Column(db.DateTime, nullable=True, index=True)
    access_blocked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    goals = db.relationship(
        'Goal',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )

    daily_results = db.relationship(
        'DailyResult',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )

    checklist_entries = db.relationship(
        'ChecklistEntry',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )

    payments = db.relationship(
        'Payment',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False

        return check_password_hash(self.password_hash, password)

    def can_access_system(self, now=None) -> bool:
        now = now or datetime.utcnow()

        if self.is_admin:
            return True

        if not self.email_verified:
            return False

        if not self.is_active_account or self.is_blocked:
            return False

        if self.paid_until and self.paid_until >= now:
            return True

        return self.trial_expires_at and self.trial_expires_at >= now

    def auto_block_if_needed(self, now=None) -> bool:
        now = now or datetime.utcnow()

        if self.is_admin:
            return False

        if not self.email_verified:
            return False

        if self.can_access_system(now=now):
            return False

        self.is_blocked = True
        self.access_blocked_at = now

        if not self.blocked_reason:
            self.blocked_reason = 'Acesso suspenso por inadimplência ou fim do período de teste.'

        return True

    @property
    def access_status(self) -> str:
        if self.is_admin:
            return 'admin'

        if not self.email_verified:
            return 'aguardando confirmação'

        if self.is_blocked:
            return 'bloqueado'

        if self.can_access_system():
            return 'ativo'

        return 'expirado'


@login_manager.user_loader
def load_user(user_id: str):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None