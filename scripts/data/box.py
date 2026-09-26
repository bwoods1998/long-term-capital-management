#!/usr/bin/env python3
"""The data box: one size-l Sailbox that downloads ThetaData history into the Gym store.

    python3 scripts/data/box.py create            create (or adopt the recorded) box, record it
    python3 scripts/data/box.py setup             allow the package hosts, install Python 3.12 +
                                                  thetadata/polars/pyarrow/numpy, then close them
    python3 scripts/data/box.py key               copy the ThetaData key into /data/secrets (0600)
    python3 scripts/data/box.py push              upload scripts/data/*.py to /data/code
    python3 scripts/data/box.py probe             authenticate and make one request from the box
    python3 scripts/data/box.py start [--stages 1,2,3,5,6] [--first ...] [--threads 4]
                                                  run the backfill in the background (nohup)
    python3 scripts/data/box.py stop              stop the backfill (it resumes from the journal)
    python3 scripts/data/box.py status            the box, its egress, and the backfill's progress
    python3 scripts/data/box.py slots N           how many of ThetaData's four requests it may use
    python3 scripts/data/box.py sleep [--wake-at ISO]   sleep (never pause: a paused box cannot wake)
    python3 scripts/data/box.py run -- ARGS       run `backfill.py ARGS` (or any data tool) on the box

Records `.data/gym/data_box.json` (gitignored; ids and facts, never a secret). Egress: the two
ThetaData hosts, plus Debian, PyPI and GitHub (for a standalone Python) only during `setup`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boxlib as bl  # noqa: E402


def say(text: str) -> None:
    print(text, flush=True)


def cmd_create(args: argparse.Namespace) -> int:
    api = bl.client()
    record = bl.read_json(bl.DATA_BOX)
    if record.get("box_id") and not args.replace:
        status = str((api.get(record["box_id"]) or {}).get("status") or "")
        if status not in ("terminated", "terminating", "failed", "create_failed", "interrupted_unsafe_to_retry"):
            say(f"the data box {record['box_id']} exists ({status})")
            return 0
    who = api.whoami()
    visibility = "private" if who.get("user_id") else "org"
    app = api.find_app("ltcm", mint_if_missing=True)
    key = record.get("create_key") if record.get("create_pending") else None
    key = key or f"ltcm-data-{uuid.uuid4()}"
    hosts = bl.normalize_hosts(list(bl.THETA_HOSTS) + list(bl.SETUP_HOSTS))
    record = {"name": args.name, "app_id": app["id"], "size": "l", "memory_limit_gib": args.memory,
              "state_disk_limit_gib": args.disk, "visibility": visibility, "create_key": key, "create_pending": True,
              "requested_at": bl.now()}
    bl.write_json(bl.DATA_BOX, record)
    row = api.create(app=app["id"], name=args.name, size="l", image={"base": "BASE_IMAGE_DEBIAN"},
                     egress={"allowlist": hosts}, auto_sleep={"automatic": True, "min_seconds_before_sleep": 900},
                     visibility=visibility, memory_limit_gib=args.memory, state_disk_limit_gib=args.disk,
                     idempotency_key=key)
    record.update({"box_id": row["sailbox_id"], "create_pending": False, "created_at": bl.now(), "status": row.get("status")})
    bl.write_json(bl.DATA_BOX, record)
    say(f"created {row['sailbox_id']} ({row.get('status')}); now `setup`, `key`, `push`, `probe`")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    api.set_egress(box, list(bl.THETA_HOSTS) + list(bl.SETUP_HOSTS))
    started = time.time()
    try:
        done = api.exec(box, ["bash", "-c", bl.SETUP_SCRIPT], timeout=1500).check()
        say(done.stdout.strip().splitlines()[-1])
    finally:
        stored = bl.policy_allowlist(api.set_egress(box, list(bl.THETA_HOSTS)))
        say(f"egress now {stored}")
    record = bl.read_json(bl.DATA_BOX)
    record.update({"setup_at": bl.now(), "setup_seconds": round(time.time() - started, 1), "egress": stored,
                   "python": done.stdout.strip().splitlines()[-1]})
    bl.write_json(bl.DATA_BOX, record)
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    api.upload(box, "/data/secrets/thetadata.env", bl.theta_env_bytes(), mode=0o600)
    check = api.exec(box, ["bash", "-c", "stat -c '%a %U %s' /data/secrets/thetadata.env; stat -c '%a' /data/secrets"], timeout=60).check()
    mode = check.stdout.split()
    say(f"key placed: /data/secrets/thetadata.env mode {mode[0]} owner {mode[1]} ({mode[2]} bytes); dir mode {mode[3]}")
    if mode[0] != "600":
        api.exec(box, ["chmod", "600", "/data/secrets/thetadata.env"], timeout=60).check()
    record = bl.read_json(bl.DATA_BOX)
    record.update({"key_placed_at": bl.now(), "key_path": "/data/secrets/thetadata.env"})
    bl.write_json(bl.DATA_BOX, record)
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    say(f"pushed {bl.push_code(api, box)} to {bl.CODE_DIR}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    bl.push_code(api, box)
    result = bl.run_py(api, box, "backfill.py probe", timeout=300)
    say(result.stdout.strip() or result.stderr.strip()[-2000:])
    return 0 if result.ok else 1


def cmd_start(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    bl.push_code(api, box)
    extra = f"--stages {shlex.quote(args.stages)} --threads {int(args.threads)}"
    if args.first:
        extra += f" --first {shlex.quote(args.first)}"
    if args.checks:
        extra += f" --checks {shlex.quote(args.checks)}"
    if args.slots is not None:
        extra += f" --slots {int(args.slots)}"
    # A string command, detached (Sail's `background`) and in its own session, so the exec's
    # timeout never reaches it; it stops only on `stop`, a crash, or an empty queue.
    command = (f"mkdir -p /data/work && cd {bl.CODE_DIR} && setsid nohup {bl.VENV_PY} backfill.py run {extra} "
               f">> /data/work/backfill.out 2>&1 < /dev/null &")
    api.exec(box, command, timeout=60, background=True)
    time.sleep(8)
    check = api.exec(box, ["bash", "-c", "cat /data/work/backfill.pid 2>/dev/null; tail -n 2 /data/work/backfill.log 2>/dev/null"], timeout=60)
    result = check
    say(f"backfill pid {check.stdout.strip()}")
    record = bl.read_json(bl.DATA_BOX)
    record.setdefault("runs", []).append({"at": bl.now(), "args": extra, "out": result.stdout.strip()})
    bl.write_json(bl.DATA_BOX, record)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    result = api.exec(box, ["bash", "-c", "p=$(cat /data/work/backfill.pid 2>/dev/null); "
                                          "if [ -n \"$p\" ] && kill -0 $p 2>/dev/null; then kill -- -$p 2>/dev/null || kill $p; echo stopped $p; "
                                          "else echo not running; fi; pkill -f 'multiprocessing.spawn' 2>/dev/null; true"],
                      timeout=60)
    say(result.stdout.strip())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    row = api.get(box)
    out = {"box_id": box, "status": row.get("status"), "egress": bl.policy_allowlist(row.get("egress_policy")),
           "disk_used_gib": round(float(row.get("disk_used_bytes") or 0) / 2**30, 2)}
    if row.get("status") == "running":
        result = bl.run_py(api, box, "backfill.py status", timeout=120)
        try:
            out["backfill"] = json.loads(result.stdout)
        except ValueError:
            out["backfill"] = result.output[-1500:]
        disk = api.exec(box, ["bash", "-c", "du -sh /data/store 2>/dev/null | cut -f1; tail -n 3 /data/work/backfill.log 2>/dev/null"], timeout=60)
        out["store_size"] = disk.stdout.strip().splitlines()[:1]
        out["log_tail"] = disk.stdout.strip().splitlines()[1:]
    try:
        out["spend"] = bl.SailboxClient.__module__ and api.spend(sailbox=box)
    except Exception as error:  # noqa: BLE001
        out["spend"] = f"unavailable: {type(error).__name__}"
    print(json.dumps(out, indent=1, default=str))
    return 0


def cmd_slots(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    api.upload(box, "/data/work/slots", f"{int(args.n)}\n".encode(), mode=0o644)
    say(f"slots set to {int(args.n)}")
    return 0


def cmd_sleep(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    row = api.sleep(box, wake_at=args.wake_at)
    say(f"asleep: {json.dumps({k: row.get(k) for k in ('status', 'wake_at')})}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    rest = [a for a in args.rest if a != "--"]
    result = bl.run_py(api, box, " ".join(shlex.quote(a) for a in rest), timeout=args.timeout,
                       on_output=lambda _s, text: print(text, end="", flush=True))
    return 0 if result.ok else 1


SAMPLE_DAYS = ("2024-01-31,2024-02-13,2024-03-15,2024-04-15,2024-06-12,"
               "2024-07-11,2024-08-05,2024-09-18,2024-11-06,2024-11-29")


def cmd_sample(args: argparse.Namespace) -> int:
    """Export Train root-days from the box and unpack them on the laptop (gitignored)."""
    import hashlib
    import io
    import shutil
    import tarfile

    api = bl.client()
    box = bl.data_box_id()
    bl.ensure_running(api, box)
    bl.push_code(api, box)
    result = bl.run_py(api, box, f"backfill.py sample --roots {shlex.quote(args.roots)} --days {shlex.quote(args.days)}",
                       timeout=900).check()
    info = json.loads(result.stdout.strip().splitlines()[-1])
    blob = api.download(box, info["tar"], timeout=900)
    if hashlib.sha256(blob).hexdigest() != info["sha256"]:
        raise SystemExit("the sample's checksum does not match what the box wrote")
    dest = Path(args.dest).expanduser()
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(dest.parent, filter="data")
    api.exec(box, ["rm", "-f", info["tar"]], timeout=60)
    say(f"sample at {dest}: {info['files']} files, days {info['days']}, {len(blob)} bytes (sha256 {info['sha256'][:12]})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--name", default="ltcm-data")
    c.add_argument("--memory", type=int, default=32)
    c.add_argument("--disk", type=int, default=256)
    c.add_argument("--replace", action="store_true")
    c.set_defaults(func=cmd_create)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    sub.add_parser("key").set_defaults(func=cmd_key)
    sub.add_parser("push").set_defaults(func=cmd_push)
    sub.add_parser("probe").set_defaults(func=cmd_probe)
    s = sub.add_parser("start")
    s.add_argument("--stages", default="1,2,3,5,6")
    s.add_argument("--first", default="")
    s.add_argument("--checks", default="")
    s.add_argument("--threads", type=int, default=8)
    s.add_argument("--slots", type=int, default=None)
    s.set_defaults(func=cmd_start)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sl_ = sub.add_parser("slots")
    sl_.add_argument("n", type=int)
    sl_.set_defaults(func=cmd_slots)
    z = sub.add_parser("sleep")
    z.add_argument("--wake-at", default=None)
    z.set_defaults(func=cmd_sleep)
    sp = sub.add_parser("sample")
    sp.add_argument("--roots", default="SPY,XSP")
    sp.add_argument("--days", default=SAMPLE_DAYS)
    sp.add_argument("--dest", default="~/Work/long-term-capital-management/.data/gym-sample/store")
    sp.set_defaults(func=cmd_sample)
    r = sub.add_parser("run")
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("rest", nargs=argparse.REMAINDER)
    r.set_defaults(func=cmd_run)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
