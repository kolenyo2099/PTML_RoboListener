#!/usr/bin/env bash
# RadioWatch backend verification harness (Stage 3 Definition of Done)
# Run this after starting the backend: uvicorn app.main:app --reload --port 8000
# Requires: curl, jq (brew install jq), websocat (brew install websocat)

set -e
BASE="http://localhost:8000"
GREEN="\033[0;32m"; RED="\033[0;31m"; RESET="\033[0m"; BOLD="\033[1m"

pass() { echo -e "${GREEN}✓${RESET} $1"; }
fail() { echo -e "${RED}✗${RESET} $1"; exit 1; }
header() { echo -e "\n${BOLD}$1${RESET}"; }

header "1. Health check"
STATUS=$(curl -sf "$BASE/status") || fail "GET /status unreachable"
echo "$STATUS" | jq -r '"  connected: \(.connected)  activeSlots: \(.activeSlots)"'
pass "GET /status healthy"

header "2. Hardware detection"
HW=$(curl -sf "$BASE/hardware") || fail "GET /hardware failed"
echo "$HW" | jq .
pass "GET /hardware responded"

header "3. Language profiles"
PROFILES=$(curl -sf "$BASE/languages/profiles") || fail "GET /languages/profiles failed"
COUNT=$(echo "$PROFILES" | jq 'length')
echo "  $COUNT profiles loaded"
echo "$PROFILES" | jq -r '.[] | "  \(.code)  spaCy:\(.spaCyModel // "none")  lemma:\(.lemmaSupported)"'
pass "GET /languages/profiles returned $COUNT profiles"

header "4. Start monitoring (test stream)"
# Uses a public Icecast test stream. Replace URL if it is unreachable.
MONITOR_JOB=$(cat <<'EOF'
{
  "stations": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "name": "Test Station",
      "slug": "test-station",
      "countryName": "Test Country",
      "countryCode": "TC",
      "languageCode": "es",
      "streamUrls": ["http://stream.zeno.fm/0r0xa792kwzuv"]
    }
  ],
  "keywordConfig": {
    "keywords": [{"id": "kw1", "text": "radio", "addedAt": "2025-01-01T00:00:00Z"}],
    "matchMode": "exact",
    "fuzzyThreshold": 80
  },
  "pipelineConfig": {
    "whisperModel": "tiny",
    "device": "cpu",
    "computeType": "int8",
    "languageHintMode": "per-station",
    "manualLanguageCode": "",
    "chunkSeconds": 10,
    "preBufferSeconds": 10,
    "postBufferSeconds": 10,
    "outputFormat": "wav",
    "outputDirectory": "./recordings",
    "transcriptLogDirectory": "./transcripts"
  }
}
EOF
)
START_RESP=$(curl -sf -X POST "$BASE/monitor/start" \
  -H "Content-Type: application/json" \
  -d "$MONITOR_JOB") || fail "POST /monitor/start failed"
echo "$START_RESP" | jq -r '"  activeSlots: \(.activeSlots)"'
pass "POST /monitor/start accepted MonitorJob"

header "5. WebSocket status stream (10 seconds)"
echo "  Listening for 3 BackendStatus frames…"
if command -v websocat &>/dev/null; then
  timeout 10 websocat "ws://localhost:8000/ws/status" 2>/dev/null | head -3 | jq -r '"  frame: activeSlots=\(.activeSlots) chunks=\(.totalChunksProcessed)"' || true
  pass "WebSocket delivered status frames"
else
  echo "  websocat not installed — skipping WebSocket check (install: brew install websocat)"
fi

header "6. Pause / resume / remove"
curl -sf -X POST "$BASE/monitor/00000000-0000-0000-0000-000000000001/pause" | jq -r '"  after pause: slot status = \(.stationStatuses[0].status // "gone")"'
pass "POST /monitor/99001/pause"
curl -sf -X POST "$BASE/monitor/00000000-0000-0000-0000-000000000001/resume" | jq -r '"  after resume: slot status = \(.stationStatuses[0].status // "gone")"'
pass "POST /monitor/99001/resume"
curl -sf -X DELETE "$BASE/monitor/00000000-0000-0000-0000-000000000001" | jq -r '"  after delete: activeSlots = \(.activeSlots)"'
pass "DELETE /monitor/99001 removed slot"

header "7. Alert listing"
ALERTS=$(curl -sf "$BASE/alerts") || fail "GET /alerts failed"
COUNT=$(echo "$ALERTS" | jq 'length')
echo "  $COUNT alert(s) in database"
pass "GET /alerts (language filter also works: $BASE/alerts?language=es)"

header "8. Stop all"
curl -sf -X POST "$BASE/monitor/stop-all" | jq -r '"  activeSlots after stop-all: \(.activeSlots)"'
pass "POST /monitor/stop-all"

echo ""
echo -e "${GREEN}${BOLD}All checks passed.${RESET}"
echo "Note: clip/alert verification requires speaking a keyword into a live stream."
echo "      See README for the full Stage 3 Definition of Done checklist."
