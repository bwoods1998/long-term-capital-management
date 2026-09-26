#!/usr/bin/env bash
# Owner-only credential placement. Reads .env without printing values; no venue keys go to House.
# Real/paper Alpaca, OpenAI and GitHub keys are placed manually with wrangler; see gateway/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'OWNER'
import os, stat, subprocess
from pathlib import Path
from league.service import load_env, secret
path = Path('.env')
if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
    raise SystemExit('.env must be a regular owner-only file (chmod 600)')
load_env(path)
for name in ('GATEWAY_TOKEN', 'SAIL_API_KEY'):
    value = secret(name)
    if not value:
        raise SystemExit(name + ' is missing; placement stopped')
    subprocess.run(['npx','wrangler','secret','put',name],cwd='gateway',input=value.encode(),check=True,stdout=subprocess.DEVNULL)
    print(name + ': placed')
OWNER
python3 scripts/floor_box.py secrets
