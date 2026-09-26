"""Process locks for the single ThetaData session and cross-host data operations.

The controller lease is held by a small process on the data box. A stopped controller leaves
the lock held for 40 minutes (longer than a checkpoint request can run), then it expires. A
live controller renews it once a minute. No key is read by this module.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LEASE_SECONDS = 2400
_CHILDREN: dict[str, subprocess.Popen] = {}


@contextlib.contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another process holds {path}") from exc
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write(path: Path, value: dict) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value))
    tmp.chmod(0o600)
    tmp.replace(path)


def serve(root: Path, token: str, ttl: float = LEASE_SECONDS) -> int:
    with process_lock(root / "operation.lock"):
        state = root / "operation.json"
        heartbeat = root / f"operation-{token}.heartbeat"
        heartbeat.touch(mode=0o600)
        write(state, {"token": token, "pid": os.getpid(), "started_at": time.time()})
        try:
            while heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < ttl:
                time.sleep(1)
        finally:
            if read(state).get("token") == token:
                state.unlink(missing_ok=True)
            heartbeat.unlink(missing_ok=True)
    return 0


def lease_command(root: Path, command: str, token: str) -> int:
    root.mkdir(parents=True, exist_ok=True)
    state = root / "operation.json"
    heartbeat = root / f"operation-{token}.heartbeat"
    if command == "acquire":
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--root", str(root),
                                  "--token", token], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            if read(state).get("token") == token:
                _CHILDREN[token] = child
                return 0
            if child.poll() is not None:
                return 1
            time.sleep(0.05)
        child.terminate()
        return 1
    if read(state).get("token") != token or not heartbeat.exists():
        return 1
    if command == "renew":
        heartbeat.touch()
    elif command == "release":
        heartbeat.unlink()
        for _ in range(30):
            if read(state).get("token") != token:
                child = _CHILDREN.pop(token, None)
                if child is not None:
                    child.wait(timeout=5)
                return 0
            time.sleep(0.1)
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("acquire", "renew", "release", "serve"))
    parser.add_argument("--root", default="/data/run")
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    if not args.token.isalnum():
        parser.error("token must be alphanumeric")
    if args.command == "serve":
        return serve(Path(args.root), args.token)
    return lease_command(Path(args.root), args.command, args.token)


if __name__ == "__main__":
    raise SystemExit(main())
