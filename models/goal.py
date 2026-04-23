from datetime import datetime

from database.db import db


class Goal(db.Model):
    __tablename__ = 'goals'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    target_income_month = db.Column(db.Float, nullable=False, default=0)
    commission_percent = db.Column(db.Float, nullable=False, default=0)
    working_days_month = db.Column(db.Integer, nullable=False, default=22)
    target_sales_month = db.Column(db.Float, nullable=False, default=0)
    target_sales_day = db.Column(db.Float, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
