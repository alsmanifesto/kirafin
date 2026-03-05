#!/usr/bin/env bash
API_URL="${API_URL:-http://localhost:8000}"
PASS=0
FAIL=0

green() { echo -e "\033[0;32m✓ $1\033[0m"; }
red()   { echo -e "\033[0;31m✗ $1\033[0m"; }

assert_status() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    green "$desc (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$desc – expected $expected, got $actual"; FAIL=$((FAIL+1))
  fi
}

assert_field() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    green "$desc (value='$actual')"; PASS=$((PASS+1))
  else
    red "$desc – expected '$expected', got '$actual'"; FAIL=$((FAIL+1))
  fi
}

echo "══════════════════════════════════════════"
echo " Post-Deploy Smoke Tests → $API_URL"
echo "══════════════════════════════════════════"

echo -e "\n[1] Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
assert_status "GET /health" "200" "$STATUS"

echo -e "\n[2] Valid txhash + vendorA"
RESPONSE=$(curl -s -X POST "$API_URL/transfer" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0x123abc456def"}')
VS=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/transfer" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0x123abc456def"}')
assert_status "POST /transfer vendorA" "200" "$HTTP"
assert_field  "vendorA status=success" "success" "$VS"

echo -e "\n[3] Valid txhash + vendorB"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/transfer" \
  -H "Content-Type: application/json" \
  -d '{"amount": 50, "vendor": "vendorB", "txhash": "0xdeadbeef1234"}')
assert_status "POST /transfer vendorB" "200" "$HTTP"

echo -e "\n[4] Invalid txhash"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/transfer" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorA", "txhash": "0xdeadbeefbad"}')
assert_status "POST /transfer invalid txhash → 422" "422" "$HTTP"

echo -e "\n[5] Unknown vendor"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/transfer" \
  -H "Content-Type: application/json" \
  -d '{"amount": 100, "vendor": "vendorX", "txhash": "0x123abc456def"}')
assert_status "POST /transfer unknown vendor → 400" "400" "$HTTP"

echo -e "\n══════════════════════════════════════════"
echo " Results: $PASS passed, $FAIL failed"
echo "══════════════════════════════════════════"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
