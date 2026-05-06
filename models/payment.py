from datetime import datetime

from database.db import db


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    net_amount = db.Column(db.Numeric(10, 2), nullable=True)
    fee_amount = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(db.String(30), nullable=False, default='pending', index=True)
    gateway = db.Column(db.String(50), nullable=True)
    gateway_payment_id = db.Column(db.String(120), nullable=True, index=True)
    external_reference = db.Column(db.String(120), nullable=True, unique=True)
    plan_type = db.Column(db.String(30), nullable=True, index=True)
    billing_cycle = db.Column(db.String(30), nullable=True, index=True)
    duration_days = db.Column(db.Integer, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
