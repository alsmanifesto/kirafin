"""
Integration + unit tests for the Payments API.
These run both locally and in CI/CD after each deployment.
"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

import os
os.environ["BLOCKCHAIN_SERVICE_URL"] = "http://mock-blockchain:8001"

from api.main import app

client = TestClient(app)

VALID_TXHASH = "0x123abc456def7890"  # Ends normally → confirmed by mock
INVALID_TXHASH = "0xdeadbeefbad"     # Ends with "bad" → not found by mock


def make_bc_mock(result: dict):
    """Build a properly shaped httpx AsyncClient mock."""
    mock_response = MagicMock()
    mock_response.json.return_value = result  # json() is SYNC in httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


# ─── Health ──────────────────────────────────────────────────────────────────
def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ─── Happy path: vendorA ──────────────────────────────────────────────────────
def test_transfer_vendor_a_success():
    with patch("api.main.httpx.AsyncClient", return_value=make_bc_mock({"result": "confirmed", "block": 19_500_000})):
        resp = client.post(
            "/transfer",
            json={"amount": 100, "vendor": "vendorA", "txhash": VALID_TXHASH},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["vendor"] == "vendorA"


# ─── Happy path: vendorB ──────────────────────────────────────────────────────
def test_transfer_vendor_b_pending():
    with patch("api.main.httpx.AsyncClient", return_value=make_bc_mock({"result": "confirmed", "block": 19_500_000})):
        resp = client.post(
            "/transfer",
            json={"amount": 50, "vendor": "vendorB", "txhash": VALID_TXHASH},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["vendor"] == "vendorB"


# ─── Invalid txhash → 422 ────────────────────────────────────────────────────
def test_invalid_txhash_rejected():
    with patch("api.main.httpx.AsyncClient", return_value=make_bc_mock({"result": "not found", "block": None})):
        resp = client.post(
            "/transfer",
            json={"amount": 100, "vendor": "vendorA", "txhash": INVALID_TXHASH},
        )
        assert resp.status_code == 422
        assert "not found" in resp.json()["detail"].lower()


# ─── Unknown vendor → 400 ─────────────────────────────────────────────────────
def test_unknown_vendor_rejected():
    with patch("api.main.httpx.AsyncClient", return_value=make_bc_mock({"result": "confirmed"})):
        resp = client.post(
            "/transfer",
            json={"amount": 100, "vendor": "vendorX", "txhash": VALID_TXHASH},
        )
        assert resp.status_code == 400


# ─── Negative amount → validation error ──────────────────────────────────────
def test_negative_amount_rejected():
    resp = client.post(
        "/transfer",
        json={"amount": -10, "vendor": "vendorA", "txhash": VALID_TXHASH},
    )
    assert resp.status_code == 422


# ─── Bad txhash format → validation error ────────────────────────────────────
def test_bad_txhash_format_rejected():
    resp = client.post(
        "/transfer",
        json={"amount": 100, "vendor": "vendorA", "txhash": "notahash"},
    )
    assert resp.status_code == 422


# ─── Negative amount → validation error ──────────────────────────────────────
def test_negative_amount_rejected():
    resp = client.post(
        "/transfer",
        json={"amount": -10, "vendor": "vendorA", "txhash": VALID_TXHASH},
    )
    assert resp.status_code == 422


# ─── Bad txhash format → validation error ────────────────────────────────────
def test_bad_txhash_format_rejected():
    resp = client.post(
        "/transfer",
        json={"amount": 100, "vendor": "vendorA", "txhash": "notahash"},
    )
    assert resp.status_code == 422
