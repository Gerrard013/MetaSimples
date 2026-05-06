from datetime import datetime

from database.db import db


class ChecklistEntry(db.Model):
    __tablename__ = 'checklist_entries'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='uq_checklist_user_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    leads_answered = db.Column(db.Boolean, nullable=False, default=False)
    follow_up_done = db.Column(db.Boolean, nullable=False, default=False)
    proposals_sent = db.Column(db.Boolean, nullable=False, default=False)
    post_sale_done = db.Column(db.Boolean, nullable=False, default=False)
    goal_reviewed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
