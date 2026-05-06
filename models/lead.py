from datetime import datetime

from database.db import db


class Lead(db.Model):
    __tablename__ = 'leads'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), nullable=False, unique=True, index=True)
    whatsapp = db.Column(db.String(20), nullable=False, unique=True, index=True)
    source = db.Column(db.String(80), nullable=True, default='landing_page')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'whatsapp': self.whatsapp,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
