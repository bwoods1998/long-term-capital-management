"""Collect Long-Term Capital Management venue credentials privately and verify them read-only.

    .venv/bin/python scripts/setup_venues.py setup    # hidden prompts; writes .env and key files
    .venv/bin/python scripts/setup_venues.py verify   # one read-only authenticated call per venue

`setup` never echoes secrets, never sends anything over the network, refuses symlinks, and
writes owner-only files. `verify` makes exactly these read-only requests:
Alpaca `GET /v2/account` (paper and live), Kalshi `GET /trade-api/v2/portfolio/balance`,
Coinbase `GET /api/v3/brokerage/accounts`. It prints statuses and balances, never keys.

Signing references (checked 2026-09-14): Alpaca header auth
https://docs.alpaca.markets/reference/getaccount-1; Kalshi RSA-PSS over timestamp+method+path
https://docs.kalshi.com/getting_started/api_keys; Coinbase CDP JWT (ES256 for ECDSA PEM keys,
EdDSA for Ed25519 secret keys) https://docs.cdp.coinbase.com/api-reference/v2/authentication.
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import secrets
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
KEYS = ROOT / ".data" / "ltcm" / "keys"
TIMEOUT = 30

ALPACA_PAPER = "https://paper-api.alpaca.markets"
ALPACA_LIVE = "https://api.alpaca.markets"
KALSHI_HOST = "https://api.elections.kalshi.com"
KALSHI_PREFIX = "/trade-api/v2"
COINBASE_HOST = "api.coinbase.com"


# ----------------------------------------------------------------------------- storage

def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(updates: dict[str, str]) -> None:
    if ENV.is_symlink():
        raise SystemExit(".env is a symlink; refusing to write")
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    tmp = ENV.with_suffix(".env.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out).rstrip("\n") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, ENV)
    os.chmod(ENV, 0o600)


def write_key_file(name: str, text: str) -> Path:
    KEYS.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(KEYS, 0o700)
    path = KEYS / name
    if path.is_symlink():
        raise SystemExit(f"{path} is a symlink; refusing to write")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text.strip() + "\n")
    os.chmod(path, 0o600)
    return path


def hidden(prompt: str, *, optional: bool = False) -> str:
    while True:
        value = getpass.getpass(prompt + (" (optional, Enter to skip): " if optional else ": ")).strip()
        if value or optional:
            return value
        print("  a value is required")


def multiline_hidden(prompt: str) -> str:
    """Read a PEM block without echo: paste all lines, then an empty line to finish."""
    print(prompt)
    print("  Paste the full PEM including the BEGIN/END lines, then press Enter on an empty line.")
    lines: list[str] = []
    while True:
        line = getpass.getpass("")
        if not line.strip():
            if lines:
                break
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines)
    if "PRIVATE KEY" not in text or "-----END" not in text:
        raise SystemExit("that did not look like a PEM private key; nothing written")
    return text


# ------------------------------------------------------------------------------- setup

def setup() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("run setup in an interactive terminal")
    print("Long-Term Capital Management venue setup. Nothing you type is echoed or sent anywhere.")
    print("Each section can be skipped if it was saved before. Values are saved as you go.\n")
    existing = read_env()

    def keep(label: str, *names: str) -> bool:
        if all(existing.get(n) for n in names):
            answer = input(f"{label} already saved. Keep it? [Y/n]: ").strip().lower()
            return answer in ("", "y", "yes")
        return False

    if not keep("Alpaca", "ALPACA_PAPER_KEY_ID", "ALPACA_PAPER_SECRET_KEY"):
        print("Alpaca (dashboard: API Keys; one pair with the Paper toggle on, one with it off)")
        updates = {
            "ALPACA_PAPER_KEY_ID": hidden("  paper key id"),
            "ALPACA_PAPER_SECRET_KEY": hidden("  paper secret key"),
        }
        live_id = hidden("  live key id", optional=True)
        if live_id:
            updates["ALPACA_LIVE_KEY_ID"] = live_id
            updates["ALPACA_LIVE_SECRET_KEY"] = hidden("  live secret key")
        write_env(updates)
        print("  saved\n")

    if not (keep("Kalshi", "KALSHI_KEY_ID") and (KEYS / "kalshi.pem").exists()):
        print("Kalshi (Account settings: API keys; you downloaded an RSA private key file once)")
        key_id = hidden("  key id (UUID)")
        kalshi_path = hidden("  path to the downloaded private key file, e.g. ~/Downloads/kalshi.txt", optional=True)
        if kalshi_path:
            text = Path(kalshi_path).expanduser().read_text(encoding="utf-8")
            if "PRIVATE KEY" not in text:
                raise SystemExit(f"{kalshi_path} is not a PEM private key")
        else:
            text = multiline_hidden("  Kalshi private key")
        write_key_file("kalshi.pem", text)
        write_env({"KALSHI_KEY_ID": key_id})
        print("  saved\n")

    if not keep("Coinbase", "COINBASE_KEY_NAME"):
        print("Coinbase (CDP portal: Secret API keys, View + Trade permissions, no Transfer)")
        print("  Enter the key id and the secret from the JSON separately (the 'id' and 'privateKey'")
        print("  values, without quotes). Or give the path to the downloaded JSON file at the first prompt.")
        raw = hidden("  key id (or JSON file path)")
        candidate = Path(raw).expanduser()
        if candidate.exists():
            raw = candidate.read_text(encoding="utf-8").strip()
        updates = {}
        if not raw.startswith("{") and "#" not in raw:
            updates["COINBASE_KEY_NAME"] = raw.strip()
            secret = hidden("  secret (the privateKey value)")
            if "PRIVATE KEY" in secret:
                write_key_file("coinbase.pem", secret.replace("\\n", "\n"))
                updates["COINBASE_API_SECRET"] = ""
            else:
                updates["COINBASE_API_SECRET"] = secret.strip().strip('"').rstrip(",")
        elif raw.startswith("{"):
            # A pasted multi-line JSON arrives one hidden line at a time; keep reading
            # until it parses or the paste ends with an empty line.
            data = None
            for _ in range(200):
                try:
                    data = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    more = getpass.getpass("")
                    if not more.strip():
                        break
                    raw += "\n" + more
            if data is None:
                raise SystemExit("could not parse the JSON key; give the file path instead")
            name = data.get("name") or data.get("id")
            private = data.get("privateKey") or data.get("private_key")
            if not name or not private:
                raise SystemExit("JSON key needs id/name and privateKey")
            updates["COINBASE_KEY_NAME"] = str(name).strip()
            if "PRIVATE KEY" in private:
                write_key_file("coinbase.pem", private.replace("\\n", "\n"))
                updates["COINBASE_API_SECRET"] = ""
            else:
                updates["COINBASE_API_SECRET"] = private.strip()
        elif "#" in raw:
            key_id, secret = raw.split("#", 1)
            updates["COINBASE_KEY_NAME"] = key_id.strip()
            updates["COINBASE_API_SECRET"] = secret.strip()
        else:
            raise SystemExit("expected a JSON key file path or keyId#secret")
        write_env(updates)
        print("  saved\n")

    if not keep("Site publication token", "CAPITAL_PUBLISH_TOKEN"):
        print("Site publication token (any random string of 40+ characters; Enter to generate one)")
        token = hidden("  token", optional=True) or secrets.token_urlsafe(48)
        if len(token) < 40:
            raise SystemExit("token must be at least 40 characters")
        write_env({"CAPITAL_PUBLISH_TOKEN": token})
        print("  saved\n")

    print(f"Credentials are in {ENV} (mode 600) and key files under {KEYS} (mode 700).")
    print("Now run:  .venv/bin/python scripts/setup_venues.py verify")
    return 0


# ------------------------------------------------------------------------------ verify

def http(method: str, url: str, headers: dict[str, str]) -> tuple[int, dict]:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "WoodsCapital/0.1", **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read(1_000_000)
            return response.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        body = exc.read(4000).decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"error": body[:300]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"transport: {type(exc).__name__}: {str(exc)[:120]}"}


def verify_alpaca(env: dict[str, str], label: str, base: str, key: str, secret: str) -> bool:
    if not env.get(key):
        print(f"Alpaca {label}: skipped (no {key})")
        return True
    status, body = http("GET", base + "/v2/account", {"APCA-API-KEY-ID": env[key], "APCA-API-SECRET-KEY": env[secret]})
    if status == 200:
        print(f"Alpaca {label}: OK  status={body.get('status')} cash=${body.get('cash')} equity=${body.get('equity')}"
              f" buying_power=${body.get('buying_power')} options_level={body.get('options_approved_level')}"
              f" crypto={body.get('crypto_status')}")
        return True
    print(f"Alpaca {label}: FAILED http={status} {json.dumps(body)[:200]}")
    return False


def kalshi_sign(private_pem: bytes, timestamp_ms: str, method: str, path: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(private_pem, password=None)
    message = (timestamp_ms + method + path).encode("utf-8")
    signature = key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def verify_kalshi(env: dict[str, str]) -> bool:
    pem_path = KEYS / "kalshi.pem"
    if not env.get("KALSHI_KEY_ID") or not pem_path.exists():
        print("Kalshi: FAILED (missing KALSHI_KEY_ID or kalshi.pem)")
        return False
    path = KALSHI_PREFIX + "/portfolio/balance"
    timestamp = str(int(time.time() * 1000))
    try:
        signature = kalshi_sign(pem_path.read_bytes(), timestamp, "GET", path)
    except Exception as exc:  # noqa: BLE001
        print(f"Kalshi: FAILED signing ({type(exc).__name__})")
        return False
    status, body = http("GET", KALSHI_HOST + path, {
        "KALSHI-ACCESS-KEY": env["KALSHI_KEY_ID"],
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "Accept": "application/json",
    })
    if status == 200 and "balance" in body:
        cents = body.get("balance")
        print(f"Kalshi: OK  balance=${int(cents) / 100:.2f} portfolio_value=${int(body.get('portfolio_value', 0)) / 100:.2f}")
        return True
    print(f"Kalshi: FAILED http={status} {json.dumps(body)[:200]}")
    return False


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def coinbase_jwt(env: dict[str, str], method: str, path: str) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    key_name = env["COINBASE_KEY_NAME"]
    now = int(time.time())
    payload = {"sub": key_name, "iss": "cdp", "nbf": now, "exp": now + 120,
               "uri": f"{method} {COINBASE_HOST}{path}"}
    header = {"typ": "JWT", "kid": key_name, "nonce": secrets.token_hex(16)}
    secret = env.get("COINBASE_API_SECRET")
    pem_path = KEYS / "coinbase.pem"
    if secret:
        raw = base64.b64decode(secret + "=" * (-len(secret) % 4))
        try:
            key = serialization.load_der_private_key(raw, password=None)
        except ValueError:
            seed = raw[:32] if len(raw) in (32, 64) else None
            if seed is None:
                raise SystemExit("Coinbase secret is neither DER nor a 32/64-byte Ed25519 key")
            key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    elif pem_path.exists():
        key = serialization.load_pem_private_key(pem_path.read_bytes(), password=None)
    else:
        raise SystemExit("no Coinbase secret or coinbase.pem")
    if isinstance(key, ed25519.Ed25519PrivateKey):
        header["alg"] = "EdDSA"
        signing_input = b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + \
            b64url(json.dumps(payload, separators=(",", ":")).encode())
        signature = key.sign(signing_input.encode("ascii"))
    else:
        header["alg"] = "ES256"
        signing_input = b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + \
            b64url(json.dumps(payload, separators=(",", ":")).encode())
        der = key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return signing_input + "." + b64url(signature)


def verify_coinbase(env: dict[str, str]) -> bool:
    if not env.get("COINBASE_KEY_NAME"):
        print("Coinbase: FAILED (missing COINBASE_KEY_NAME)")
        return False
    path = "/api/v3/brokerage/accounts"
    try:
        token = coinbase_jwt(env, "GET", path)
    except Exception as exc:  # noqa: BLE001
        print(f"Coinbase: FAILED building JWT ({type(exc).__name__}: {str(exc)[:100]})")
        return False
    status, body = http("GET", f"https://{COINBASE_HOST}{path}?limit=50", {"Authorization": "Bearer " + token})
    if status == 200 and "accounts" in body:
        funded = []
        for account in body["accounts"]:
            value = account.get("available_balance", {}).get("value", "0")
            currency = account.get("available_balance", {}).get("currency", "?")
            try:
                if float(value) > 0:
                    funded.append(f"{value} {currency}")
            except ValueError:
                pass
        print(f"Coinbase: OK  accounts={len(body['accounts'])} funded=[{', '.join(funded) or 'none'}]")
        return True
    print(f"Coinbase: FAILED http={status} {json.dumps(body)[:200]}")
    return False


def verify() -> int:
    env = read_env()
    if ENV.exists() and stat.S_IMODE(ENV.stat().st_mode) & 0o077:
        print("WARNING: .env is readable by other users; run chmod 600 .env")
    results = [
        verify_alpaca(env, "paper", ALPACA_PAPER, "ALPACA_PAPER_KEY_ID", "ALPACA_PAPER_SECRET_KEY"),
        verify_alpaca(env, "live", ALPACA_LIVE, "ALPACA_LIVE_KEY_ID", "ALPACA_LIVE_SECRET_KEY"),
        verify_kalshi(env),
        verify_coinbase(env),
    ]
    print("all venues verified" if all(results) else "some venues failed; fix and re-run verify")
    return 0 if all(results) else 1


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "setup"
    if command == "setup":
        raise SystemExit(setup())
    if command == "verify":
        raise SystemExit(verify())
    raise SystemExit(__doc__)
