#!/usr/bin/env bash
# demo_analyze_sample.sh
# ---------------------------------------------------------------------------
# Quick end-to-end demo: upload synthetic bank data → analyze → print results
#
# Usage (from repo root):
#   bash backend/scripts/demo_analyze_sample.sh
#
# Prerequisites:
#   - Server running: uvicorn app.main:app --reload --port 8000
#   - curl, jq installed
# ---------------------------------------------------------------------------

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_DIR="$SCRIPT_DIR/../data/samples"

echo "=== CreditSight AI — End-to-End Demo (feat/advanced-bank-metrics) ==="
echo ""

# ---- 1. Create application --------------------------------------------------
echo "1. Creating application..."
APP_RESP=$(curl -s -X POST "$BASE_URL/api/upload" \
  -F "company_name=DemoTech Pvt Ltd" \
  -F "cin=U74999MH2020PTC123456" \
  -F "gstin=27AAAAA1234A1ZA" \
  -F "collateral_value=2000000" \
  -F "bank_statement=@$SAMPLE_DIR/sample_bank.pdf;type=application/pdf" 2>/dev/null || \
  curl -s -X POST "$BASE_URL/api/upload" \
  -H "Content-Type: application/json" \
  -d '{"company_name":"DemoTech Pvt Ltd","collateral_value":2000000}')

APP_ID=$(echo "$APP_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('application_id',''))" 2>/dev/null)

if [ -z "$APP_ID" ]; then
  echo "❌  Failed to create application. Is the server running at $BASE_URL?"
  echo "    Response: $APP_RESP"
  exit 1
fi
echo "   Application ID: $APP_ID"

# ---- 2. Trigger analysis ----------------------------------------------------
echo ""
echo "2. Running analysis pipeline..."
curl -s -X POST "$BASE_URL/api/applications/$APP_ID/analyze" \
     -H "Content-Type: application/json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'   Status: {d.get(\"status\")} — {d.get(\"message\")}')"

# ---- 3. Poll for completion (up to 60s) ------------------------------------
echo ""
echo "3. Waiting for analysis to complete..."
for i in $(seq 1 12); do
  sleep 5
  STATUS=$(curl -s "$BASE_URL/api/applications/$APP_ID" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null)
  echo "   Attempt $i/12 — status: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "rejected" ] || [ "$STATUS" = "error" ]; then
    break
  fi
done

# ---- 4. Fetch and display results -------------------------------------------
echo ""
echo "4. Results:"
RESULT=$(curl -s "$BASE_URL/api/applications/$APP_ID")
echo "$RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
fields = [
  'status', 'credit_score', 'risk_grade', 'recommended_loan_amount',
  'average_daily_balance', 'average_transactional_balance',
  'emi_estimated_monthly', 'unusual_count', 'bounce_count',
]
for f in fields:
    val = d.get(f)
    print(f'   {f:40s}: {val}')
print()
print('   Top SHAP values:')
for k, v in (d.get('shap_values') or {}).items():
    print(f'     {k:40s}: {v}')
print()
print('   Rule flags:')
for flag in (d.get('rule_flags') or []):
    print(f'     • {flag}')
" 2>/dev/null || echo "$RESULT" | python3 -m json.tool

echo ""
echo "=== Demo complete ==="
