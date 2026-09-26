#!/usr/bin/env python3
"""The Gym image and the gate image: sealed forks of the data box, checkpointed for a year.

    python3 scripts/data/images.py build gym [--version v1] [--force]
    python3 scripts/data/images.py build gate [--version v1] [--force]
    python3 scripts/data/images.py verify gym|gate [--checkpoint ID]
    python3 scripts/data/images.py status

`build` (run from the owner's machine with the Sail key):
  1. checks the data box's journal holds what the image needs (gym: the core five over 2023-2025;
     gate: that and the core five's holdout), unless --force;
  2. stops the backfill (a checkpoint of a running download would fork a second downloader; ThetaData
     allows one session per account), checkpoints the data box, and restarts the backfill;
  3. forks a box from that checkpoint, seals it (`{"no_network": true}`) before anything else runs,
     and kills any process the fork carried over;
  4. prunes it: the Gym image keeps Train and Validation only and loses the key and the working
     area; the gate image keeps every window and its journal but loses the key;
  5. writes the gate's `GATE` mark (gate only; `league.gym.store.mint_gate_capability` needs it, and
     the Gym image must not carry it) and verifies from inside: a connection out fails, no key file and no `THETADATA_API_KEY` line
     anywhere under /data, /root, /tmp or /home, and (Gym) no file dated in the holdout or later and
     a manifest/calendar/expiries that stop at 2025-12-31;
  6. checkpoints it twice with a one-year TTL (retrying with backoff, every error recorded), records both ids in `.data/gym/images.json`, and
     puts the fork to sleep (Gym boxes are forks of the checkpoint; nothing is left running).

Sail's checkpoint API has failed for a day before: two checkpoints, and this script rebuilds either
image from the data box at any time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

import boxlib as bl  # noqa: E402
import storelib as sl  # noqa: E402

YEAR_SECONDS = 365 * 86400

KINDS = {
    "gym": {"keep": ("train", "validation"), "prune": "--keep train,validation --drop-key --drop-work",
            "needs_stages": (1,)},
    "gate": {"keep": ("train", "validation", "holdout", "forward"),
             "prune": "--keep train,validation,holdout,forward --drop-key --keep-journal", "needs_stages": (1, 2)},
}

#: Run inside a sealed box: every line must come out as expected, or the image is refused.
NETWORK_PROBE = r"""
import socket
for host, port in (("mdds-01.thetadata.us", 443), ("nexus-api.thetadata.us", 443), ("1.1.1.1", 443), ("pypi.org", 443)):
    try:
        socket.create_connection((host, port), timeout=5).close()
        print("NETWORK-OPEN", host)
    except OSError as exc:
        print("NETWORK-CLOSED", host, type(exc).__name__)
"""

INSIDE_CHECK = r"""
import json, os, pathlib, subprocess
out = {}
out["key_file"] = os.path.exists("/data/secrets/thetadata.env") or os.path.exists("/data/secrets")
hits = subprocess.run(["grep", "-rIl", "THETADATA_API_KEY", "/data", "/root", "/tmp", "/home"],
                      capture_output=True, text=True).stdout.split()
out["key_mentions"] = [h for h in hits if not h.startswith("/data/code/")]
store = pathlib.Path("/data/store")
dates = sorted(p.stem for p in store.glob("*/*/*.parquet"))
out["files"] = len(dates)
out["first_date"] = dates[0] if dates else None
out["last_date"] = dates[-1] if dates else None
out["dated_after_validation"] = sum(1 for d in dates if d > "2025-12-31")
import polars as pl
m = pl.read_parquet(store / "manifest.parquet")
out["manifest_rows"] = m.height
out["manifest_windows"] = sorted(set(m["window"].to_list()))
out["manifest_last"] = str(m["date"].max()) if m.height else None
c = pl.read_parquet(store / "calendar.parquet")
out["calendar_last"] = str(c["date"].max()) if c.height else None
e = pl.read_parquet(store / "expiries.parquet")
out["expiries_last_date"] = str(e["date"].max()) if e.height else None
out["version"] = (store / "VERSION").read_text().strip()
out["gate_mark"] = (store / "GATE").is_file()
out["work_exists"] = os.path.exists("/data/work")
out["processes"] = subprocess.run(["pgrep", "-fa", "backfill.py|universe.py"], capture_output=True, text=True).stdout.strip()
print(json.dumps(out))
"""


def say(text: str) -> None:
    print(text, flush=True)


def seal(api: Any, box: str) -> Any:
    """`{"no_network": true}` on the box, read back from the API."""
    api.transport("PUT", f"/sailboxes/{box}/egress-policy", {"document": {"no_network": True}})
    policy = api.egress(box)
    document = policy.get("document") if isinstance(policy, Mapping) else None
    if not (isinstance(document, Mapping) and document.get("no_network")):
        raise SystemExit(f"the seal did not hold on {box}: {policy}")
    return policy


def stage_done(journal_lines: list[dict[str, Any]], stages: tuple[int, ...], plan_counts: Mapping[str, int]) -> dict[str, Any]:
    done: dict[str, int] = {}
    for row in journal_lines:
        if row.get("type") == "task" and row.get("status") in ("ok", "empty"):
            done[str(row.get("stage"))] = done.get(str(row.get("stage")), 0) + 1
    return {str(s): {"done": done.get(str(s), 0), "planned": plan_counts.get(str(s))} for s in stages}


def verify_inside(api: Any, box: str, kind: str) -> dict[str, Any]:
    net = api.exec(box, ["/opt/data-venv/bin/python", "-c", NETWORK_PROBE], timeout=120)
    inside = api.exec(box, ["/opt/data-venv/bin/python", "-c", INSIDE_CHECK], timeout=600)
    try:
        facts = json.loads(inside.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SystemExit(f"the inside check failed on {box}: {inside.output[-1500:]}")
    lines = net.stdout.strip().splitlines()
    facts["network"] = lines
    problems = []
    if not lines or any(not line.startswith("NETWORK-CLOSED") for line in lines):
        problems.append("a connection out did not fail")
    if facts["key_file"] or facts["key_mentions"]:
        problems.append("a key file or a key line is present")
    if facts["processes"]:
        problems.append("a data process is running")
    if kind == "gym":
        if facts["dated_after_validation"]:
            problems.append(f"{facts['dated_after_validation']} files dated after 2025-12-31")
        if set(facts["manifest_windows"]) - {"train", "validation"}:
            problems.append(f"manifest windows {facts['manifest_windows']}")
        for key in ("manifest_last", "calendar_last", "expiries_last_date"):
            if facts.get(key) and facts[key] > "2025-12-31":
                problems.append(f"{key} {facts[key]}")
        if facts["work_exists"]:
            problems.append("/data/work exists")
        if facts["gate_mark"]:
            problems.append("the Gym image carries the gate's GATE mark")
    elif kind == "gate" and not facts["gate_mark"]:
        problems.append("the gate image has no GATE mark (league.gym.store.mint_gate_capability needs it)")
    facts["problems"] = problems
    facts["passed"] = not problems
    return facts


def checkpoint_with_retry(api: Any, box: str, *, name: str, ttl_seconds: int, attempts: int = 6,
                          sleep: Callable[[float], None] = time.sleep, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Sail's checkpoint API has failed for hours at a time (Sept 25; Sept 26 06:35Z and 07:00Z on the
    House box): retry with backoff and keep every error, verbatim, for the record."""
    delay = 30.0
    for attempt in range(1, attempts + 1):
        try:
            return api.checkpoint(box, name=name, ttl_seconds=ttl_seconds, timeout=1800)
        except bl.SailboxError as error:
            entry = {"at": bl.now(), "box": box, "name": name, "attempt": attempt, "status": error.status,
                     "error": str(error)[:500]}
            if errors is not None:
                errors.append(entry)
            say(f"  checkpoint {name} attempt {attempt} failed: {entry['error']}")
            if attempt == attempts:
                raise
            sleep(delay)
            delay = min(delay * 2, 600.0)
    raise AssertionError("unreachable")


def build(kind: str, *, version: str, force: bool, api: Any = None, sleep: Callable[[float], None] = time.sleep,
          ttl_days: int = 365, rehearsal: bool = False) -> dict[str, Any]:
    """Build one image. `rehearsal` runs every step on whatever the store holds now, then
    terminates the fork and records the result under `rehearsals` (never as the current image)."""
    api = api or bl.client()
    spec = KINDS[kind]
    errors: list[dict[str, Any]] = []
    data_box = bl.data_box_id()
    bl.ensure_running(api, data_box)
    # 1. is the data there?
    journal = [json.loads(line) for line in api.download(data_box, "/data/work/journal.jsonl", timeout=600).decode().splitlines()
               if line.strip().startswith("{")]
    progress = json.loads(api.download(data_box, "/data/work/progress.json"))
    counts = {k: v.get("planned") for k, v in (progress.get("stages") or {}).items()}
    have = stage_done(journal, spec["needs_stages"], counts)
    complete = all(v["planned"] and v["done"] >= v["planned"] for v in have.values())
    say(f"{kind} image {version}: stages needed {have} -> {'complete' if complete else 'NOT complete'}")
    if not complete and not force:
        raise SystemExit("the data box does not hold what this image needs yet (--force to build anyway)")
    # 2. a checkpoint of the data box with no download running
    was_running = api.exec(data_box, ["bash", "-c", "p=$(cat /data/work/backfill.pid 2>/dev/null); [ -n \"$p\" ] && kill -0 $p 2>/dev/null && echo yes || echo no"],
                           timeout=60).stdout.strip() == "yes"
    last_args = None
    if was_running:
        last_args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")
        api.exec(data_box, ["bash", "-c", "p=$(cat /data/work/backfill.pid); kill -- -$p 2>/dev/null || kill $p; "
                                          "for i in $(seq 1 60); do kill -0 $p 2>/dev/null || break; sleep 1; done; "
                                          "pkill -f multiprocessing.spawn; true"], timeout=120)
        say("  backfill stopped for the checkpoint")
    try:
        source = checkpoint_with_retry(api, data_box, name=f"ltcm-data-for-{kind}-{version}",
                                       ttl_seconds=(2 if rehearsal else 30) * 86400,
                                       sleep=sleep, errors=errors)
    finally:
        if was_running and last_args:
            command = (f"mkdir -p /data/work && cd {bl.CODE_DIR} && setsid nohup {bl.VENV_PY} backfill.py run {last_args} "
                       f">> /data/work/backfill.out 2>&1 < /dev/null &")
            api.exec(data_box, command, timeout=60, background=True)
            say("  backfill restarted")
    say(f"  data box checkpoint {source['checkpoint_id']}")
    # 3. fork, seal first, stop anything carried over
    fork = api.from_checkpoint(source["checkpoint_id"], name=f"ltcm-{kind}-image-{version}", timeout=1800)
    box = fork["sailbox_id"]
    say(f"  fork {box}; sealing")
    seal(api, box)
    api.exec(box, ["bash", "-c", "pkill -f 'backfill.py|universe.py|multiprocessing' ; rm -f /data/work/backfill.pid; true"], timeout=60)
    # 4. prune
    pruned = bl.run_py(api, box, f"backfill.py prune {spec['prune']}", timeout=3600).check()
    say(f"  pruned: {pruned.stdout.strip().splitlines()[-1]}")
    if kind == "gate":
        # The mark league.gym.store.mint_gate_capability requires; only the gate image carries it.
        api.upload(box, "/data/store/GATE", f"gate image {version} built {bl.now()}\n".encode(), mode=0o444)
    else:
        api.exec(box, ["rm", "-f", "/data/store/GATE"], timeout=60)
    # 5. verify
    facts = verify_inside(api, box, kind)
    say(f"  inside: {json.dumps({k: facts[k] for k in ('passed', 'problems', 'files', 'first_date', 'last_date', 'manifest_windows', 'network')})}")
    if not facts["passed"]:
        api.sleep(box)
        raise SystemExit(f"the {kind} image failed its checks; the fork {box} is asleep for inspection")
    # 6. two checkpoints, one year each, then sleep
    checkpoints = []
    started = time.time()
    for label in (("a",) if rehearsal else ("a", "b")):
        row = checkpoint_with_retry(api, box, name=f"ltcm-{kind}-image-{version}-{label}", ttl_seconds=ttl_days * 86400,
                                    sleep=sleep, errors=errors)
        checkpoints.append(row["checkpoint_id"])
        say(f"  checkpoint {label}: {row['checkpoint_id']} ({time.time() - started:.0f}s)")
    record = bl.read_json(bl.IMAGES)
    if rehearsal:
        api.terminate(box)
        record.setdefault("rehearsals", []).append({"kind": kind, "version": version, "box_id": box, "terminated": True,
                                                    "checkpoints": checkpoints, "ttl_days": ttl_days, "at": bl.now(),
                                                    "passed": facts["passed"], "files": facts["files"],
                                                    "checkpoint_errors": errors})
        bl.write_json(bl.IMAGES, record)
        return record["rehearsals"][-1]
    api.sleep(box)
    entry = {
        "version": version, "box_id": box, "checkpoints": checkpoints, "source_checkpoint": source["checkpoint_id"],
        "built_at": bl.now(), "ttl_days": ttl_days, "sealed": {"no_network": True}, "windows": list(spec["keep"]),
        "stages_at_build": have, "checkpoint_errors": errors, "gate_mark": facts["gate_mark"], "verified": {k: facts[k] for k in ("files", "first_date", "last_date", "manifest_rows",
                                                                    "manifest_windows", "network", "version")},
    }
    record.setdefault(kind, {}).update({"current": entry})
    record[kind].setdefault("history", []).append(entry)
    bl.write_json(bl.IMAGES, record)
    return entry


def verify(kind: str, checkpoint: str | None = None) -> dict[str, Any]:
    """Wake the recorded image box (or fork a new one from a checkpoint) and check it again."""
    api = bl.client()
    entry = (bl.read_json(bl.IMAGES).get(kind) or {}).get("current") or {}
    if checkpoint:
        box = api.from_checkpoint(checkpoint, name=f"ltcm-{kind}-verify", timeout=1800)["sailbox_id"]
        created = True
    else:
        box, created = entry["box_id"], False
        bl.ensure_running(api, box)
    try:
        return verify_inside(api, box, kind)
    finally:
        api.terminate(box) if created else api.sleep(box)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("kind", choices=sorted(KINDS))
    b.add_argument("--version", default="v1")
    b.add_argument("--force", action="store_true")
    b.add_argument("--ttl-days", type=int, default=365)
    b.add_argument("--rehearsal", action="store_true", help="every step on the store as it is; the fork is terminated")
    v = sub.add_parser("verify")
    v.add_argument("kind", choices=sorted(KINDS))
    v.add_argument("--checkpoint", default=None)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args.kind, version=args.version, force=args.force or args.rehearsal,
                               ttl_days=args.ttl_days, rehearsal=args.rehearsal), indent=1))
    elif args.cmd == "verify":
        print(json.dumps(verify(args.kind, args.checkpoint), indent=1))
    else:
        print(json.dumps(bl.read_json(bl.IMAGES), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
