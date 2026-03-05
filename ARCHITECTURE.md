# Architecture – Cross-Border Payments API

## Overview

This platform processes USDC → COP transfers through pluggable vendor modules.  
Every transfer requires a confirmed on-chain txhash before funds are routed to a vendor.

```
Client
  │
  ▼
[ ALB / HTTPS ]
  │
  ▼
[ Payments API  :8000 ] ──── POST /transfer
  │        │
  │        ├── 1. Validate txhash → [ Mock Blockchain Service :8001 ]
  │        │
  │        └── 2. Route to vendor → [ VendorA | VendorB | VendorN ]
  │
  ▼
[ Prometheus :9090 ] ◄── scrapes /metrics
  │
  ▼
[ Grafana :3000 ] ◄── dashboards
```

---

## Services

| Service | Port | Purpose |
|---|---|---|
| `payments-api` | 8000 | Main transfer API |
| `mock-blockchain` | 8001 | Txhash confirmation oracle |
| `prometheus` | 9090 | Metrics collection |
| `grafana` | 3000 | Dashboards + DORA metrics |

---

## Transfer Flow

```
POST /transfer { amount, vendor, txhash }
       │
       ▼
 [1] Validate txhash
       GET /confirm/{txhash} → mock-blockchain
       ├── "confirmed"  → proceed
       └── "not found"  → HTTP 422 (rejected, logged)
       │
       ▼
 [2] Lookup vendor
       VENDOR_REGISTRY["vendorA"] → VendorA instance
       └── Unknown vendor → HTTP 400
       │
       ▼
 [3] vendor.process(amount, txhash)
       ├── VendorA → { status: "success", reference_id, amount_cop }
       └── VendorB → { status: "pending", queue_id, estimated_minutes }
       │
       ▼
 [4] Emit metrics + structured audit log
       │
       ▼
 [5] Return TransferResponse to client
```

---

## Vendor Extensibility

Vendors follow the **Open/Closed Principle** — you extend without modifying existing code.

### Adding VendorC (3 steps)

**Step 1 – Create `api/vendors/vendor_c.py`:**
```python
from api.vendors.base import BaseVendor

class VendorC(BaseVendor):
    async def process(self, amount: float, txhash: str) -> dict:
        # Call vendorC's real API here
        return {"status": "success", "vendor": "vendorC"}
```

**Step 2 – Register in `api/vendors/__init__.py`:**
```python
from api.vendors.vendor_c import VendorC

VENDOR_REGISTRY = {
    "vendorA": VendorA(),
    "vendorB": VendorB(),
    "vendorC": VendorC(),   # ← this is the entire change
}
```

**Step 3 – Deploy.** No other files change.

The `BaseVendor` abstract class enforces the contract: every vendor must implement `async process(amount, txhash) -> dict` and return at minimum `{"status": "..."}`.

---

## Infrastructure (AWS)

```
┌─────────────────────────────────────────────────┐
│  VPC  10.0.0.0/16                                │
│                                                  │
│  ┌──────────┐     ┌──────────────────────────┐  │
│  │  Public  │     │  Private Subnets (x2 AZ) │  │
│  │ Subnets  │     │                          │  │
│  │  (x2 AZ) │     │  ┌─────────────────────┐ │  │
│  │          │     │  │  ECS Fargate Tasks  │ │  │
│  │   [ALB]  │────►│  │  payments-api       │ │  │
│  │  HTTPS   │     │  │  (non-root, no SSH) │ │  │
│  └──────────┘     │  └─────────────────────┘ │  │
│                   └──────────────────────────┘  │
│                                                  │
│  Secrets: AWS SSM Parameter Store (encrypted)    │
│  Logs:    CloudWatch Logs (/ecs/payments-api)    │
│  Images:  ECR (immutable tags, scan-on-push)     │
└─────────────────────────────────────────────────┘
```

### Key decisions

- **Fargate** (serverless ECS): no EC2 instances to patch; reduces attack surface.
- **Private subnets** for tasks: containers are not internet-reachable directly.
- **ALB with HTTPS only**: TLS termination at the load balancer.
- **Immutable ECR tags**: `IMAGE_TAG = git SHA`, preventing tag overwrite attacks.
- **Deployment circuit breaker**: ECS auto-rolls back on health check failure.

---

## Observability

### Metrics (Prometheus + Grafana)

| Metric | Labels | Purpose |
|---|---|---|
| `transfer_requests_total` | vendor, status | Request volume and success/failure rate |
| `transfer_latency_seconds` | vendor | P50/P95/P99 latency per vendor |
| `txhash_confirmations_total` | result | Confirmed vs rejected blockchain queries |

### Structured Logging

Every request emits a JSON log line with:
```json
{
  "timestamp": "...",
  "level": "INFO",
  "message": "Transfer completed",
  "vendor": "vendorA",
  "txhash": "0x123...",
  "amount": 100,
  "latency_ms": 42.1,
  "client_ip": "..."
}
```

Logs are shipped to **CloudWatch Logs** in production with 90-day retention.

---

## DORA Metrics

| Metric | How it's captured |
|---|---|
| **Deployment Frequency** | Count of successful `deploy` job runs in GitHub Actions |
| **Lead Time** | `BUILD_END - github.sha commit timestamp` (logged in CI) |
| **Change Failure Rate** | `smoke-test` failures / total deployments |
| **MTTR** | Time from `DORA_FAILURE_AT` to next successful deployment |

All four are available in **GitHub Actions job history** and can be exported to a DORA dashboard (e.g., LinearB, Faros, or a custom Grafana panel querying the GH API).

---

## Local Development

```bash
# Start the full stack
docker compose up --build

# Run unit tests
pip install -r api/requirements.txt pytest pytest-asyncio httpx
pytest tests/ -v

# Manual smoke test
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0x123abc456def"}'

# Grafana dashboard
open http://localhost:3000  # admin / admin
```
