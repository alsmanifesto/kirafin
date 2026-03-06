import time
import httpx
import logging
import json
import os
import threading
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator
from prometheus_client import Counter, Histogram, make_asgi_app

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

# ─── Embedded Mock Blockchain (runs in same process on port 8001) ─────────────
blockchain_app = FastAPI(title="Mock Blockchain Service")

@blockchain_app.get("/health")
def blockchain_health():
    return {"status": "ok"}

@blockchain_app.get("/confirm/{txhash}")
def confirm(txhash: str):
    if txhash.startswith("0x") and len(txhash) >= 10 and not txhash.endswith("bad"):
        return {"txhash": txhash, "result": "confirmed", "block": 19_500_000}
    return {"txhash": txhash, "result": "not found", "block": None}

def start_blockchain_server():
    uvicorn.run(blockchain_app, host="0.0.0.0", port=8001, log_level="warning")

# Start blockchain in background thread on container startup
blockchain_thread = threading.Thread(target=start_blockchain_server, daemon=True)
blockchain_thread.start()

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(title="Cross-Border Payments API", version="1.0.0")

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

BLOCKCHAIN_SERVICE_URL = os.getenv(
    "BLOCKCHAIN_SERVICE_URL", "http://127.0.0.1:8001"
)

from api.vendors import get_vendor


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

    # ── Step 1: Validate txhash with mock blockchain ──────────────────────────
    logger.info("Validating txhash", extra={"extra": {**audit_context, "step": "txhash_validation"}})
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            bc_resp = await client.get(
                f"{BLOCKCHAIN_SERVICE_URL}/confirm/{payload.txhash}"
            )
            bc_data = bc_resp.json()
    except Exception as e:
        logger.error("Blockchain service unreachable", extra={"extra": {**audit_context, "error": str(e)}})
        TXHASH_CONFIRMATIONS.labels(result="error").inc()
        raise HTTPException(status_code=503, detail="Blockchain service unavailable")

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
