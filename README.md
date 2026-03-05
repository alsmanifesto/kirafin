# Cross-Border Payments API

USDC → COP transfer platform with pluggable vendor architecture, full observability, and SOC 2-aligned infrastructure.

## Quick Start (Local)

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Payments API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

## Make a Transfer

```bash
# Valid transfer → vendorA (success)
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0x123abc456def"}'

# Valid transfer → vendorB (pending)
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 50, "vendor": "vendorB", "txhash": "0xdeadbeef1234"}'

# Invalid txhash → rejected
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0xbadtxhashbad"}'
```

## Run Tests

```bash
# Unit tests
pip install pytest pytest-asyncio httpx
pytest tests/ -v

# Post-deploy smoke tests
API_URL=http://localhost:8000 bash tests/post-deploy-smoke-test.sh
```

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Infrastructure design, vendor extensibility, txhash flow
- [SOC2.md](./SOC2.md) — SOC 2 Trust Services Criteria alignment
- [OPERATION.md](./OPERATION.md) — Operation and validations procedures

## Adding a New Vendor

1. Create `api/vendors/vendor_c.py` subclassing `BaseVendor`
2. Register it in `api/vendors/__init__.py`
3. Deploy — no other changes required

See [ARCHITECTURE.md](./ARCHITECTURE.md#vendor-extensibility) for details.
