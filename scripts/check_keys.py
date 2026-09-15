"""Report which Long Term Capital Management credentials are present, without printing any secret.

Usage: python3 scripts/check_keys.py

Reads `.env` (KEY=value lines) and the PEM files under `.data/ltcm/keys/`. Prints each
expected name with present/missing, the value length and a short SHA-256 fingerprint so a
misplaced or truncated key is visible. Never prints values.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
KEYS = ROOT / ".data" / "ltcm" / "keys"

EXPECTED_ENV = [
    ("SAIL_API_KEY", "Sail inference"),
    ("ALPACA_PAPER_KEY_ID", "Alpaca paper trading key id"),
    ("ALPACA_PAPER_SECRET_KEY", "Alpaca paper trading secret"),
    ("ALPACA_LIVE_KEY_ID", "Alpaca live trading key id"),
    ("ALPACA_LIVE_SECRET_KEY", "Alpaca live trading secret"),
    ("KALSHI_KEY_ID", "Kalshi API key id (UUID)"),
    ("COINBASE_KEY_NAME", "Coinbase key id or name (the part before '#', or the JSON 'id'/'name')"),
    ("COINBASE_API_SECRET", "Coinbase Ed25519 secret (the part after '#'); optional if coinbase.pem exists"),
    ("CAPITAL_PUBLISH_TOKEN", "Site publication token (shared with the Cloudflare secret)"),
]
EXPECTED_FILES = [
    ("kalshi.pem", "Kalshi RSA private key"),
    ("coinbase.pem", "Coinbase EC private key (PEM); optional if COINBASE_API_SECRET is set"),
]
OPTIONAL = {"COINBASE_API_SECRET", "coinbase.pem"}


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def mode_ok(path: Path) -> bool:
    try:
        return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    except FileNotFoundError:
        return False


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    env = read_env(ENV)
    print(f".env: {'present' if ENV.exists() else 'missing'}"
          f"{'' if not ENV.exists() else (' (permissions ok)' if mode_ok(ENV) else ' (WARNING: readable by others; run chmod 600 .env)')}")
    missing = 0
    for name, label in EXPECTED_ENV:
        value = env.get(name) or os.environ.get(name)
        if value:
            print(f"  {name:28} present  len={len(value):<4} sha256={fingerprint(value)}  {label}")
        else:
            missing += name not in OPTIONAL
            print(f"  {name:28} {'optional' if name in OPTIONAL else 'MISSING '} {label}")
    print(f"keys dir: {KEYS} {'present' if KEYS.exists() else 'missing'}"
          f"{'' if not KEYS.exists() else (' (permissions ok)' if mode_ok(KEYS) else ' (WARNING: run chmod 700 on it)')}")
    for filename, label in EXPECTED_FILES:
        path = KEYS / filename
        if path.exists():
            text = path.read_text(encoding="utf-8")
            pem = "PRIVATE KEY" in text
            print(f"  {filename:28} present  bytes={len(text):<5} pem={'yes' if pem else 'NO'}"
                  f" sha256={fingerprint(text)} {'' if mode_ok(path) else '(WARNING: chmod 600)'}  {label}")
        else:
            missing += filename not in OPTIONAL
            print(f"  {filename:28} {'optional' if filename in OPTIONAL else 'MISSING '} {label}")
    if not (env.get("COINBASE_API_SECRET") or os.environ.get("COINBASE_API_SECRET") or (KEYS / "coinbase.pem").exists()):
        missing += 1
        print("  coinbase secret              MISSING  need COINBASE_API_SECRET or coinbase.pem")
    print(f"{missing} missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
