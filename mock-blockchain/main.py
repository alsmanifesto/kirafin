"""
Mock Blockchain Confirmation Service

Returns "confirmed" for any txhash that:
  - Starts with 0x
  - Has at least 10 characters
  - Does NOT end with "bad" (to allow testing failure cases)

In production: query an actual node (Ethereum, Polygon, etc.)
"""
from fastapi import FastAPI

app = FastAPI(title="Mock Blockchain Service", version="1.0.0")

# Pre-seeded hashes for deterministic test behaviour
CONFIRMED_HASHES = {
    "0x123abc",
    "0xabc123def456",
    "0x" + "a" * 64,  # full-length mock hash
}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/confirm/{txhash}")
def confirm(txhash: str):
    # Deterministic logic: anything starting 0x and not ending in "bad" is confirmed
    if txhash.startswith("0x") and len(txhash) >= 10 and not txhash.endswith("bad"):
        return {"txhash": txhash, "result": "confirmed", "block": 19_500_000}
    return {"txhash": txhash, "result": "not found", "block": None}
