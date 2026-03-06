import time
import logging
import json
import os
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator
from prometheus_client import Counter, Histogram, make_asgi_app
from api.vendors import get_vendor

# ─── Structured logging ───────────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "extra"):
            log.update(record.extra)
        return json.dumps(log)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger("payments_api")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ─── Prometheus metrics ────────────────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "transfer_requests_total",
    "Total transfer requests",
    ["vendor", "status"],
)
REQUEST_LATENCY = Histogram(
    "transfer_latency_seconds",
    "Transfer request latency",
    ["vendor"],
)
TXHASH_CONFIRMATIONS = Counter(
    "txhash_confirmations_total",
    "Txhash confirmation outcomes",
    ["result"],
)

# ─── Mock blockchain (direct function call — no HTTP, no threads) ─────────────
# In production: replace with httpx call to actual blockchain node RPC endpoint
def confirm_txhash(txhash: str) -> dict:
    if txhash.startswith("0x") and len(txhash) >= 10 and not txhash.endswith("bad"):
        return {"txhash": txhash, "result": "confirmed", "block": 19_500_000}
    return {"txhash": txhash, "result": "not found", "block": None}

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Cross-Border Payments API", version="1.0.0")

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


class TransferRequest(BaseModel):
    amount: float
    vendor: str
    txhash: str

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("txhash")
    @classmethod
    def txhash_must_be_hex(cls, v):
        if not v.startswith("0x") or len(v) < 10:
            raise ValueError("txhash must be a valid hex string starting with 0x")
        return v


class TransferResponse(BaseModel):
    status: str
    vendor: str
    txhash: str
    amount: float
    vendor_response: dict


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transfer", response_model=TransferResponse)
async def transfer(payload: TransferRequest, request: Request):
    start = time.time()
    audit_context = {
        "vendor": payload.vendor,
        "txhash": payload.txhash,
        "amount": payload.amount,
        "client_ip": request.client.host,
    }

    # ── Step 1: Validate txhash (direct function call) ────────────────────────
    logger.info("Validating txhash", extra={"extra": {**audit_context, "step": "txhash_validation"}})
    bc_data = confirm_txhash(payload.txhash)
    confirmation_result = bc_data.get("result", "not found")
    TXHASH_CONFIRMATIONS.labels(result=confirmation_result).inc()

    if confirmation_result != "confirmed":
        logger.warning(
            "Txhash not confirmed",
            extra={"extra": {**audit_context, "bc_result": confirmation_result}},
        )
        REQUEST_COUNT.labels(vendor=payload.vendor, status="rejected").inc()
        raise HTTPException(status_code=422, detail=f"Txhash validation failed: {confirmation_result}")

    logger.info("Txhash confirmed", extra={"extra": {**audit_context, "bc_result": "confirmed"}})

    # ── Step 2: Forward to vendor ─────────────────────────────────────────────
    try:
        vendor = get_vendor(payload.vendor)
    except KeyError:
        REQUEST_COUNT.labels(vendor=payload.vendor, status="unknown_vendor").inc()
        raise HTTPException(status_code=400, detail=f"Unknown vendor: {payload.vendor}")

    logger.info("Forwarding to vendor", extra={"extra": {**audit_context, "step": "vendor_forward"}})
    vendor_response = await vendor.process(payload.amount, payload.txhash)

    elapsed = time.time() - start
    REQUEST_LATENCY.labels(vendor=payload.vendor).observe(elapsed)
    REQUEST_COUNT.labels(vendor=payload.vendor, status=vendor_response.get("status", "unknown")).inc()

    logger.info(
        "Transfer completed",
        extra={
            "extra": {
                **audit_context,
                "vendor_status": vendor_response.get("status"),
                "latency_ms": round(elapsed * 1000, 2),
            }
        },
    )

    return TransferResponse(
        status=vendor_response.get("status"),
        vendor=payload.vendor,
        txhash=payload.txhash,
        amount=payload.amount,
        vendor_response=vendor_response,
    )
