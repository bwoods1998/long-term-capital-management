#!/usr/bin/env bash
# Place the floor's secrets where they belong. Run this yourself; it never prints a value.
#
#   bash scripts/place_secrets.sh
#
# 1. Cloudflare gateway secrets (venue keys, Sail key, gateway token) via `wrangler secret put`.
# 2. The box's own .env (Sail key, publish token, gateway token) via `floor_box.py secrets`.
#
# Reads: .env and .data/ltcm/keys/kalshi.pem. Requires: a wrangler login, and the box created
# by `scripts/floor_box.py create` (its id is in .data/ltcm/box.json).
set -euo pipefail
cd "$(dirname "$0")/.."

if ! grep -q '^GATEWAY_TOKEN=' .env; then
  printf 'GATEWAY_TOKEN=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" >> .env
  chmod 600 .env
  echo "generated GATEWAY_TOKEN in .env"
fi

value() { grep "^$1=" .env | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }

echo "== gateway secrets"
( cd gateway
  for name in GATEWAY_TOKEN KALSHI_KEY_ID COINBASE_KEY_NAME COINBASE_API_SECRET SAIL_API_KEY; do
    v="$(value "$name")"
    if [ -z "$v" ]; then echo "  $name: missing in .env, skipped"; continue; fi
    printf '%s' "$v" | npx wrangler secret put "$name" >/dev/null 2>&1 && echo "  $name: set" || echo "  $name: FAILED"
  done
  if [ -f ../.data/ltcm/keys/kalshi.pem ]; then
    npx wrangler secret put KALSHI_PRIVATE_KEY < ../.data/ltcm/keys/kalshi.pem >/dev/null 2>&1 && echo "  KALSHI_PRIVATE_KEY: set" || echo "  KALSHI_PRIVATE_KEY: FAILED"
  else
    echo "  KALSHI_PRIVATE_KEY: kalshi.pem not found, skipped"
  fi
  npx wrangler secret list 2>/dev/null | grep -o '"name": *"[A-Z_]*"' | tr -d '" ' | sed 's/^name://' | tr '\n' ' '; echo
)

echo "== box secrets"
.venv/bin/python scripts/floor_box.py secrets

echo
echo "Next: .venv/bin/python scripts/floor_box.py start   # then: scripts/floor_box.py status"
