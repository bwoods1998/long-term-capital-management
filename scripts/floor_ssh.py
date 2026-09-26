#!/usr/bin/env python3
"""Open an SSH path into the floor box for the owner, for the day exec cannot run.

    python3 scripts/floor_ssh.py                      # enable sshd on the box, issue a certificate
    python3 scripts/floor_ssh.py --key ~/.ssh/id_ed25519.pub --allow 203.0.113.7/32

Why this exists (Sept 16, 2026): the floor box ran its 32 GiB disk full. Sail's runtime writes
a record for every exec before it launches, so with the disk full every exec fails, and the
files API (which can read and write single files but cannot list or delete) is not enough to
find and remove the culprit. SSH is the other door: Sail's runtime installs the org CA, starts
sshd and exposes port 22 as raw TCP (docs: sailboxes-networking). Sessions sign in as root.

Steps, all documented by Sail:
  1. POST /sailboxes/{id}/ssh  {"allowlist": [<your address>/32], "wait": true}
  2. POST /ssh/certificate     {"public_key": <your public key>}  -> a short-lived certificate
  3. save it next to your private key as <key>-cert.pub and connect with the host and port the
     first call returns (the script prints the ssh command).

Nothing here prints a secret: the API key is read from .env and sent in one header.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import floor_box  # noqa: E402
from league.service import load_env  # noqa: E402

API = "https://sailbox-api.sailresearch.com/v1"


def call(key: str, method: str, path: str, body: dict | None, *, timeout: float = 180.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read(4000).decode("utf-8", "replace")
        raise SystemExit(f"{method} {path} -> {error.code}: {detail[:600]}") from None
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {"raw": raw[:600].decode("utf-8", "replace")}


def my_address() -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=15) as response:
        return response.read().decode("utf-8").strip()


def scrub(value):
    if isinstance(value, dict):
        return {k: ("<hidden>" if any(s in k.lower() for s in ("token", "secret", "certificate", "private")) else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--key", default=str(Path.home() / ".ssh" / "id_ed25519.pub"), help="your SSH public key (default ~/.ssh/id_ed25519.pub)")
    parser.add_argument("--allow", action="append", help="address or CIDR allowed to connect (default: this machine's public address)")
    parser.add_argument("--box", help="sailbox id (default: the floor box recorded by floor_box.py)")
    args = parser.parse_args(argv)

    env = load_env(ROOT / ".env")
    key = env.get("SAIL_API_KEY")
    if not key:
        raise SystemExit("SAIL_API_KEY is not in .env")
    box = args.box or floor_box.require_box(floor_box.read_state())
    public_key_path = Path(args.key).expanduser()
    if not public_key_path.is_file():
        raise SystemExit(f"no public key at {public_key_path}; make one with: ssh-keygen -t ed25519")
    public_key = public_key_path.read_text(encoding="utf-8").strip()
    allow = args.allow or [f"{my_address()}/32"]

    print(f"enabling sshd on {box} for {', '.join(allow)} ...")
    enabled = call(key, "POST", f"/sailboxes/{box}/ssh", {"allowlist": allow, "wait": True})
    print("  ->", json.dumps(scrub(enabled))[:800])

    print("issuing a certificate for", public_key_path.name, "...")
    issued = call(key, "POST", "/ssh/certificate", {"public_key": public_key})
    certificate = issued.get("certificate")
    if not certificate:
        raise SystemExit(f"no certificate in the answer: {json.dumps(scrub(issued))[:400]}")
    private_key_path = public_key_path.with_suffix("")  # id_ed25519.pub -> id_ed25519
    cert_path = Path(str(private_key_path) + "-cert.pub")
    cert_path.write_text(certificate.strip() + "\n", encoding="utf-8")
    cert_path.chmod(0o600)
    print(f"  saved {cert_path} (key id {issued.get('key_id')})")

    host = enabled.get("host") or enabled.get("hostname") or (enabled.get("listener") or {}).get("host") or "<host from the answer above>"
    port = enabled.get("port") or (enabled.get("listener") or {}).get("port") or 22
    print()
    print("connect with:")
    print(f"  ssh -i {private_key_path} -p {port} root@{host}")
    print("or, with the Sail CLI installed:")
    print(f"  sail box ssh alias {box} && ssh ltcm-floor.sail")
    print()
    print("on the box, find and remove what filled the disk, then start the loop again from here:")
    print("  df -h /; du -xsh /workspace/state/* /workspace/archive/* /tmp /var/* 2>/dev/null | sort -h | tail -15")
    print("  python3 scripts/floor_box.py start")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
