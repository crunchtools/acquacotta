#!/usr/bin/env bash
# Post-deploy smoke test: verify the container serves both the Flask app and the
# MCP endpoint. Run against a running container.
#   Usage: ./smoke_test.sh [BASE_URL]   (default http://localhost:5000)
set -euo pipefail

BASE_URL="${1:-http://localhost:5000}"
fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

# 1) Flask app answers on / (health check)
code=$(curl -fsS -o /dev/null -w '%{http_code}' "$BASE_URL/") || fail "Flask app unreachable at $BASE_URL/"
{ [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; } || fail "Flask app returned HTTP $code at /"
echo "OK: Flask app answered HTTP $code at /"

# 2) MCP endpoint completes the initialize handshake through Apache → uvicorn
resp=$(curl -fsS -X POST "$BASE_URL/mcp" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}') \
  || fail "MCP endpoint unreachable at $BASE_URL/mcp"
echo "$resp" | grep -q '"serverInfo"' || fail "MCP endpoint did not return a valid initialize result: $resp"
echo "OK: MCP endpoint completed the initialize handshake at /mcp"

echo "SMOKE PASS"
