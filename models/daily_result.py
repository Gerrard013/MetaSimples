from datetime import datetime

from database.db import db


class DailyResult(db.Model):
    __tablename__ = 'daily_results'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='uq_daily_result_user_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    sales_value = db.Column(db.Float, nullable=False, default=0)
    earnings_value = db.Column(db.Float, nullable=False, default=0)
    attendance_count = db.Column(db.Integer, nullable=False, default=0)
    closed_deals = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
