from datetime import date, datetime
from decimal import Decimal

from database.db import db


class FinanceTransaction(db.Model):
    __tablename__ = 'finance_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    type = db.Column(db.String(20), nullable=False, index=True)  # income ou expense
    date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal('0.00'))

    # Para IA/categorização: merchant = estabelecimento; category = categoria confirmada.
    merchant = db.Column(db.String(120), nullable=True, index=True)
    category = db.Column(db.String(80), nullable=False, default='Outros', index=True)
    ai_suggested_category = db.Column(db.String(80), nullable=True)
    category_confirmed = db.Column(db.Boolean, nullable=False, default=True)

    description = db.Column(db.String(255), nullable=True)
    payment_method = db.Column(db.String(80), nullable=True)
    is_recurring = db.Column(db.Boolean, nullable=False, default=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
