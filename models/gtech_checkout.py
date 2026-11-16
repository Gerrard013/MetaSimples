from datetime import datetime
from database.db import db


class GTechCheckout(db.Model):
    """Standalone G Tech catalog checkout; distinct from MetaSimples subscription payments."""
    __tablename__ = "gtech_checkout_orders"

    order_id = db.Column(db.String(36), primary_key=True)
    sku = db.Column(db.String(40), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    total_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    preference_id = db.Column(db.String(150), nullable=True)
    checkout_url = db.Column(db.Text, nullable=True)
    gateway_payment_id = db.Column(db.String(120), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
