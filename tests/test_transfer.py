import pytest
import os
os.environ["BLOCKCHAIN_SERVICE_URL"] = "http://localhost:8001"

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

VALID_TXHASH = "0x123abc456def7890"
INVALID_TXHASH = "0xdeadbeefbad"


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_transfer_vendor_a_success():
    resp = client.post("/transfer", json={
        "amount": 100, "vendor": "vendorA", "txhash": VALID_TXHASH
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["vendor"] == "vendorA"


def test_transfer_vendor_b_pending():
    resp = client.post("/transfer", json={
        "amount": 50, "vendor": "vendorB", "txhash": VALID_TXHASH
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_invalid_txhash_rejected():
    resp = client.post("/transfer", json={
        "amount": 100, "vendor": "vendorA", "txhash": INVALID_TXHASH
    })
    assert resp.status_code == 422
    assert "not found" in resp.json()["detail"].lower()


def test_unknown_vendor_rejected():
    resp = client.post("/transfer", json={
        "amount": 100, "vendor": "vendorX", "txhash": VALID_TXHASH
    })
    assert resp.status_code == 400


def test_negative_amount_rejected():
    resp = client.post("/transfer", json={
        "amount": -10, "vendor": "vendorA", "txhash": VALID_TXHASH
    })
    assert resp.status_code == 422


def test_bad_txhash_format_rejected():
    resp = client.post("/transfer", json={
        "amount": 100, "vendor": "vendorA", "txhash": "notahash"
    })
    assert resp.status_code == 422
