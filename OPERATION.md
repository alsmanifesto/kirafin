# Operation Team Procedures 
1. Run the stack
```bash
docker compose up --build
```

2. API validation
```bash
curl http://localhost:8000/health
```
Transfer validation (vendorA → success):
```bash
curl -s -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0x123abc456def"}' | python3 -m json.tool
```
Expected response
```bash
{
    "status": "success",
    "vendor": "vendorA",
    "txhash": "0x123abc456def",
    "amount": 100.0,
    "vendor_response": {
        "status": "success",
        "vendor": "vendorA",
        "reference_id": "VA-BC456DEF",
        "amount_cop": 415000.0
    }
}
```
Transfer validation (vendorB → pending):
```bash
curl -s -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 50, "vendor": "vendorB", "txhash": "0xdeadbeef1234"}' | python3 -m json.tool
  ```
Invalid Txhash (end in "bad") → should be 422:
```bash
bashcurl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0xdeadbeefbad"}'
# → 422
```
Unknown vendor → 400:
```bash
bashcurl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorX", "txhash": "0x123abc456def"}'
# → 400
```

**Swagger UI:**
http://localhost:8000/docs

3. Validate blockchain mock directly
```bash
Hash válido → confirmed
curl http://localhost:8001/confirm/0x123abc456def
# → {"txhash":"0x123abc456def","result":"confirmed","block":19500000}

# Invalid Hash (ends in bad) → not found
curl http://localhost:8001/confirm/0xdeadbeefbad
# → {"txhash":"0xdeadbeefbad","result":"not found","block":null}
```
4. Running Unit Tests
```bash
python3 -m pip install pytest pytest-asyncio httpx fastapi pydantic prometheus-client

python3 -m pytest tests/test_transfer.py -v
```
Smoke tests (simulates CI post-deploy):
```bash
API_URL=http://localhost:8000 bash tests/post-deploy-smoke-test.sh
```
Expected response:

✓ GET /health (HTTP 200)
✓ POST /transfer vendorA (HTTP 200)
✓ vendorA returns status=success (value='success')
✓ POST /transfer vendorB (HTTP 200)
✓ POST /transfer invalid txhash → 422 (HTTP 422)
✓ POST /transfer unknown vendor → 400 (HTTP 400)

Results: 6 passed, 0 failed

5. Observability
Prometheus — metrics:

```bash
curl -s http://localhost:8000/metrics | grep -E "transfer_|txhash_"
```

transfer_requests_total{status="success",vendor="vendorA"} 2.0
transfer_requests_total{status="pending",vendor="vendorB"} 1.0
txhash_confirmations_total{result="confirmed"} 3.0
txhash_confirmations_total{result="not found"} 1.0
transfer_latency_seconds_count{vendor="vendorA"} 2.0

**Prometheus UI — Verify that scrapes the API:**

http://localhost:9090/targets
Target payments-api should be on UP state.
Puedes hacer queries en http://localhost:9090/graph:
promqlrate(transfer_requests_total[1m])
histogram_quantile(0.99, rate(transfer_latency_seconds_bucket[5m]))

**Grafana — dashboard:**

http://localhost:3000
usuario: admin
password: admin
Dashboard: "Payments API – DORA & Operational Metrics"

6. Validate logging (audit trail SOC 2)
```bash
docker logs payments-api 2>&1 | python3 -m json.tool
```
Each request generates logs like:
```bash
json{"timestamp": "...", "level": "INFO", "message": "Validating txhash", "vendor": "vendorA", "txhash": "0x123...", "step": "txhash_validation"}
{"timestamp": "...", "level": "INFO", "message": "Transfer completed", "vendor": "vendorA", "latency_ms": 2.3}
```
For invalid txhash:
```bash
json{"timestamp": "...", "level": "WARNING", "message": "Txhash not confirmed", "bc_result": "not found"}
```

7. Validate Terraform
```bash
cd terraform
terraform init
terraform validate
# → Success! The configuration is valid.

terraform plan -var="image_tag=abc123"
# Muestra el plan de recursos sin crear nada
```



