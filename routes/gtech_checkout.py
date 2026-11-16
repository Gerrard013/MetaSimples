"""Secure payment bridge for the G Tech site, reusing MetaSimples Mercado Pago credentials.

DISABLED by default. Requires a shared bridge secret and explicit GTECH_STORE_CHECKOUT_ENABLED=true.
Orders are not MetaSimples user subscriptions; money is considered paid only after MP API verification.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit

import requests
from flask import Blueprint, current_app, jsonify, request

from database.db import db
from models.gtech_checkout import GTechCheckout

gtech_checkout_bp = Blueprint("gtech_checkout", __name__)

# Server-side catalogue is authoritative. Neither the browser nor the G Tech
# site may send an arbitrary price and create a R$ 1 preference for a R$ 500 item.
PRODUCTS = {
    "nfc": {"title": "Plaquinha NFC personalizada - G Tech", "unit_cents": 7999, "limit": 8},
    "foto": {"title": "Restauração de fotografia - G Tech", "unit_cents": 1000, "limit": 10},
    "google": {"title": "Perfil da Empresa no Google - G Tech", "unit_cents": 15000, "limit": 1},
    "site_setup": {"title": "Criação de site profissional - G Tech", "unit_cents": 50000, "limit": 1},
}


def _enabled() -> bool:
    return os.getenv("GTECH_STORE_CHECKOUT_ENABLED", "false").strip().lower() == "true"


def _secret() -> str:
    return os.getenv("GTECH_CHECKOUT_SHARED_SECRET", "").strip()


def _signed(raw: bytes, header: str) -> bool:
    secret = _secret()
    if not secret or len(secret) < 32 or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + expected, header)


def _checkout_host_ok(url: str) -> bool:
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
        return u.scheme == "https" and u.username is None and u.password is None and (
            host in ("mercadopago.com.br", "mercadopago.com") or
            host.endswith(".mercadopago.com.br") or host.endswith(".mercadopago.com")
        )
    except ValueError:
        return False


def _return_site_url(path: str) -> str:
    # Hard-coded official domain, not controlled by a checkout buyer.
    return "https://gtech-ultra-final-production.up.railway.app" + path


@gtech_checkout_bp.post("/api/gtech/checkout")
def create_store_checkout():
    if not _enabled():
        return jsonify(error="Cobranças da G Tech ainda não foram liberadas."), 503
    if not _signed(request.get_data(), request.headers.get("X-GTech-Signature", "")):
        return jsonify(error="Não autorizado."), 401

    form = request.get_json(silent=True) or {}
    order_id, sku = str(form.get("order_id", "")), str(form.get("sku", ""))
    try:
        qty = int(form.get("quantity", 1))
        uuid.UUID(order_id, version=4)
    except (TypeError, ValueError, AttributeError):
        return jsonify(error="Pedido inválido."), 400
    if sku not in PRODUCTS or str(uuid.UUID(order_id)) != order_id:
        return jsonify(error="Produto inválido."), 400
    offer = PRODUCTS[sku]
    if qty < 1 or qty > offer["limit"]:
        return jsonify(error="Quantidade indisponível."), 400
    # NFC stock/shipping must be reviewed and consciously enabled separately.
    if sku == "nfc" and os.getenv("GTECH_NFC_DIRECT_CHECKOUT", "false").lower() != "true":
        return jsonify(error="Confirme o estoque e a entrega pelo WhatsApp antes de pagar o NFC."), 409

    token = current_app.config.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        return jsonify(error="Gateway indisponível."), 503
    external = "GTECH-" + order_id
    order = db.session.get(GTechCheckout, order_id)
    if order:
        if order.sku != sku or order.quantity != qty:
            return jsonify(error="Esse pedido já existe para outro produto."), 409
        if order.status == "approved":
            return jsonify(error="Pedido já pago."), 409
        if order.checkout_url and _checkout_host_ok(order.checkout_url):
            return jsonify(order_id=order_id, checkout_url=order.checkout_url, amount_cents=order.total_cents)
    else:
        order = GTechCheckout(
            order_id=order_id, sku=sku, quantity=qty,
            total_cents=offer["unit_cents"] * qty, status="pending"
        )
        db.session.add(order)
        db.session.commit()

    app_base = current_app.config.get("APP_BASE_URL", "").rstrip("/")
    if not app_base.startswith("https://"):
        return jsonify(error="Gateway sem URL HTTPS de webhook."), 503

    payload = {
        "items": [{
            "id": sku, "title": offer["title"],
            "currency_id": "BRL", "quantity": qty,
            "unit_price": offer["unit_cents"] / 100
        }],
        "external_reference": external,
        "back_urls": {
            "success": _return_site_url("/pedido/" + order_id + "?retorno=sucesso"),
            "pending": _return_site_url("/pedido/" + order_id + "?retorno=pendente"),
            "failure": _return_site_url("/pedido/" + order_id + "?retorno=erro"),
        },
        "notification_url": app_base + "/webhooks/gtech-mercadopago",
        "statement_descriptor": "GTECH",
        "auto_return": "approved",
        "metadata": {"gtech_order_id": order_id, "catalog_sku": sku},
    }
    try:
        resp = requests.post(
            "https://api.mercadopago.com/checkout/preferences",
            json=payload, timeout=12,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                     "X-Idempotency-Key": order_id}
        )
        resp.raise_for_status()
        result = resp.json()
        checkout_url = str(result.get("init_point") or "")
        if not _checkout_host_ok(checkout_url):
            raise ValueError("MP returned an unexpected checkout host")
        order.preference_id = str(result.get("id") or "")[:150]
        order.checkout_url = checkout_url
        db.session.commit()
        return jsonify(order_id=order_id, checkout_url=checkout_url, amount_cents=order.total_cents)
    except (requests.RequestException, ValueError, TypeError) as exc:
        current_app.logger.warning("G Tech payment preference failed: %s", type(exc).__name__)
        return jsonify(error="Não foi possível iniciar o pagamento. Nenhuma compra foi confirmada."), 502


def _reconcile_authoritative_payment(payment_id: str) -> bool:
    """MP API check is the sole authority to set status approved."""
    if not re.fullmatch(r"[0-9]{1,25}", payment_id):
        return False
    token = current_app.config.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        return False
    try:
        resp = requests.get(
            "https://api.mercadopago.com/v1/payments/" + payment_id,
            headers={"Authorization": "Bearer " + token}, timeout=12
        )
        resp.raise_for_status()
        item = resp.json()
        external = str(item.get("external_reference") or "")
        if not external.startswith("GTECH-"):
            return False
        order = db.session.get(GTechCheckout, external[len("GTECH-"):])
        if not order:
            return False
        if item.get("currency_id") != "BRL":
            return False
        amount_cents = int(
            (Decimal(str(item.get("transaction_amount", ""))) * Decimal("100"))
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if amount_cents != order.total_cents:
            current_app.logger.warning("Amount mismatch for G Tech order %s", order.order_id)
            return False
        status = str(item.get("status") or "")
        if status == "approved":
            if order.status != "approved":
                order.status = "approved"
                order.paid_at = datetime.utcnow()
                order.gateway_payment_id = payment_id
                db.session.commit()
            return True
        if order.status != "approved" and status in (
            "pending", "in_process", "rejected", "cancelled", "refunded", "charged_back"
        ):
            order.status = status
            db.session.commit()
        return True
    except (requests.RequestException, ValueError, TypeError, InvalidOperation):
        current_app.logger.warning("G Tech payment validation failed.")
        return False


def _mp_signature_valid(payment_id: str) -> bool:
    """Verify Mercado Pago x-signature when configured; never trust a client status."""
    secret = current_app.config.get("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    if not secret:
        return False  # Fail closed: production must configure the signature secret.
    signature = request.headers.get("x-signature", "")
    request_id = request.headers.get("x-request-id", "")
    parts = dict(
        (k.strip(), v.strip()) for p in signature.split(",") if "=" in p
        for k, v in [p.split("=", 1)]
    )
    ts, v1 = parts.get("ts", ""), parts.get("v1", "")
    if not ts.isdigit() or not re.fullmatch(r"[a-fA-F0-9]{64}", v1):
        return False
    # Reject replayed signatures older than five minutes.
    import time
    if abs(time.time() - int(ts) / 1000) > 300:
        return False
    manifest = f"id:{payment_id.lower()};request-id:{request_id};ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), v1.lower())


@gtech_checkout_bp.post("/webhooks/gtech-mercadopago")
def gtech_payment_webhook():
    payload = request.get_json(silent=True) or {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    payment_id = str(data.get("id") or request.args.get("data.id") or "")
    if not re.fullmatch(r"[0-9]{1,25}", payment_id):
        return jsonify(status="ignored"), 200
    if not _mp_signature_valid(payment_id):
        return jsonify(error="Assinatura inválida."), 401
    if not _reconcile_authoritative_payment(payment_id):
        return jsonify(status="pending_verification"), 202
    return jsonify(status="received"), 200


@gtech_checkout_bp.get("/api/gtech/status/<order_id>")
def checkout_status(order_id: str):
    if not _signed(b"status:" + order_id.encode(), request.headers.get("X-GTech-Signature", "")):
        return jsonify(error="Não autorizado."), 401
    try:
        uuid.UUID(order_id, version=4)
    except ValueError:
        return jsonify(error="Pedido inválido."), 400
    order = db.session.get(GTechCheckout, order_id)
    if not order:
        return jsonify(error="Pedido inexistente."), 404
    return jsonify(order_id=order_id, status=order.status, sku=order.sku, amount_cents=order.total_cents)
