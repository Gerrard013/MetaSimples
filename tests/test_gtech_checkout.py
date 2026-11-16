"""No real Mercado Pago payments, API calls, or production credentials are used."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

db_path = tempfile.NamedTemporaryFile(prefix="gtech_metasimples_test_", suffix=".sqlite3", delete=False)
db_path.close()
os.environ["DATABASE_URL"] = "sqlite:///" + db_path.name
os.environ["SECRET_KEY"] = "unit-test-only"
os.environ["ADMIN_EMAIL"] = "admin@unit-test.local"
os.environ["ADMIN_PASSWORD"] = "unit-test-only-password"
os.environ["MERCADOPAGO_ACCESS_TOKEN"] = "test-access-token-not-for-live"
os.environ["MERCADOPAGO_WEBHOOK_SECRET"] = "test-mp-webhook-secret"
os.environ["APP_BASE_URL"] = "https://metasimples-production.up.railway.app"
os.environ["GTECH_CHECKOUT_SHARED_SECRET"] = "test-only-shared-secret-longer-than-32-chars"
os.environ["GTECH_STORE_CHECKOUT_ENABLED"] = "true"
os.environ["GTECH_NFC_DIRECT_CHECKOUT"] = "false"

from app import app
from database.db import db
from models.gtech_checkout import GTechCheckout
from routes.gtech_checkout import _reconcile_authoritative_payment


class MockResponse:
    status_code = 201
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        return None
    def json(self):
        return self.data


class GTechMerchantBridgeTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.create_all()
        self.client = app.test_client()
        self.order_id = str(uuid.uuid4())

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def signed(self, data):
        raw=json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        secret=os.environ["GTECH_CHECKOUT_SHARED_SECRET"].encode()
        return raw, {"Content-Type": "application/json", "X-GTech-Signature": "sha256="+hmac.new(secret,raw,hashlib.sha256).hexdigest()}

    def create(self, sku="foto",quantity=1,**other):
        data={"order_id": self.order_id, "sku":sku, "quantity":quantity, **other}
        raw,headers=self.signed(data)
        return self.client.post("/api/gtech/checkout",data=raw,headers=headers)

    def test_reject_unauthenticated_or_disabled(self):
        self.assertEqual(self.client.post("/api/gtech/checkout",json={"sku":"foto"}).status_code,401)
        with patch.dict(os.environ,{"GTECH_STORE_CHECKOUT_ENABLED":"false"}):
            self.assertEqual(self.create().status_code,503)

    def test_no_arbitrary_price_even_when_signed(self):
        expected_url="https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=mock"
        with patch("routes.gtech_checkout.requests.post",return_value=MockResponse({"id":"pref-test-1","init_point":expected_url})) as api:
            resp=self.create("foto",1,price=1,total_cents=1)
        self.assertEqual(resp.status_code,200,resp.get_data(as_text=True))
        self.assertEqual(resp.json["checkout_url"],expected_url)
        self.assertEqual(resp.json["amount_cents"],1000)
        payload=api.call_args.kwargs["json"]
        self.assertEqual(payload["items"][0]["unit_price"],10.0)
        self.assertEqual(payload["external_reference"],"GTECH-"+self.order_id)
        self.assertEqual(payload["back_urls"]["success"],"https://gtech-ultra-final-production.up.railway.app/pedido/"+self.order_id+"?retorno=sucesso")
        with app.app_context():
            row=db.session.get(GTechCheckout,self.order_id)
            self.assertEqual(row.status,"pending")
            self.assertEqual(row.total_cents,1000)

    def test_nfc_shipping_and_stock_gate(self):
        self.assertEqual(self.create("nfc",1).status_code,409)
        self.assertEqual(self.create("foto",11).status_code,400)
        self.assertEqual(self.create("site_setup",2).status_code,400)

    def test_webhook_requires_signature_and_api_amount_match(self):
        self.create_mock_order(15000,sku="google")
        content={"data":{"id":"123456789"}}
        unauth=self.client.post("/webhooks/gtech-mercadopago",json=content)
        self.assertEqual(unauth.status_code,401)
        with app.app_context():
            with patch("routes.gtech_checkout.requests.get",return_value=MockResponse({
                "external_reference":"GTECH-"+self.order_id,
                "transaction_amount":1,"currency_id":"BRL","status":"approved"
            })):
                self.assertFalse(_reconcile_authoritative_payment("123456789"))
            self.assertEqual(db.session.get(GTechCheckout,self.order_id).status,"pending")

        ts=str(int(time.time()*1000))
        request_id="mock-req-123"
        manifest=f"id:123456789;request-id:{request_id};ts:{ts};"
        sig=hmac.new(os.environ["MERCADOPAGO_WEBHOOK_SECRET"].encode(),manifest.encode(),hashlib.sha256).hexdigest()
        headers={"x-signature":f"ts={ts},v1={sig}","x-request-id":request_id}
        with patch("routes.gtech_checkout.requests.get",return_value=MockResponse({
            "external_reference":"GTECH-"+self.order_id,
            "transaction_amount":150,"currency_id":"BRL","status":"approved"
        })) as call:
            good=self.client.post("/webhooks/gtech-mercadopago",json=content,headers=headers)
        self.assertEqual(good.status_code,200,good.get_data(as_text=True))
        self.assertEqual(call.call_count,1)
        with app.app_context():
            row=db.session.get(GTechCheckout,self.order_id)
            self.assertEqual(row.status,"approved")
            self.assertEqual(row.gateway_payment_id,"123456789")

    def test_legacy_metasimples_return_no_longer_trusts_url_status(self):
        import inspect
        from routes.main import payment_success
        source=inspect.getsource(payment_success)
        self.assertNotIn("request.args.get('status'",source)
        self.assertNotIn("approve_payment(payment",source)
        self.assertIn("payment.status == 'approved'",source)

    def test_legacy_subscription_rejects_underpayment(self):
        from models.user import User
        from models.payment import Payment
        from services.payment_service import sync_mercadopago_payment
        with app.app_context():
            user=User.query.filter_by(email="admin@unit-test.local").first()
            self.assertIsNotNone(user)
            pending=Payment(user_id=user.id,amount=150,status="pending",
                            gateway="mercadopago",external_reference="unit-test-subscription")
            db.session.add(pending)
            db.session.commit()
            with patch("services.payment_service.requests.get",return_value=MockResponse({
                "external_reference":"unit-test-subscription",
                "transaction_amount":1,
                "currency_id":"BRL",
                "status":"approved",
            })):
                ok,message=sync_mercadopago_payment("123456789")
            self.assertFalse(ok)
            self.assertIn("divergente",message)
            self.assertEqual(db.session.get(Payment,pending.id).status,"pending")

    def test_status_is_private_and_not_query_parameter_based(self):
        self.create_mock_order(1000)
        no_sig=self.client.get("/api/gtech/status/"+self.order_id)
        self.assertEqual(no_sig.status_code,401)
        raw=("status:"+self.order_id).encode()
        sig=hmac.new(os.environ["GTECH_CHECKOUT_SHARED_SECRET"].encode(),raw,hashlib.sha256).hexdigest()
        response=self.client.get("/api/gtech/status/"+self.order_id,headers={"X-GTech-Signature":"sha256="+sig})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["status"],"pending")
        self.assertEqual(response.json["amount_cents"],1000)

    def create_mock_order(self,cents,sku="foto"):
        with app.app_context():
            db.session.add(GTechCheckout(
                order_id=self.order_id,sku=sku,quantity=1,total_cents=cents,status="pending"
            ))
            db.session.commit()


if __name__ == "__main__":
    unittest.main()
