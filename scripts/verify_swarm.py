#!/usr/bin/env python3
"""Verify the swarm ON THE HOUSE BOX after a deploy (read-only; standard library only).

    python3 scripts/verify_swarm.py --root /workspace/state [--since-minutes 60] [--floor 16] [--birth-hours 6]

Checks, each PASS / FAIL / WAIT with its numbers, as one JSON document (exit 0 when nothing FAILs):

- process     the swarm's heartbeat is fresh (< 60 s), its pid is alive, it runs the House's release;
- population  at most the ceiling alive (`population` in effect: <root>/swarm.json over the release's
              policy.json; the plan: 48 at the start, a ceiling of 96, a floor of 16); below the start the
              architect refills hourly (WAIT when it is refilling). The floor counts the families that research
              (F1: dead slots may leave below it, a WAIT while the architect bears: a family was born, or the
              swarm started, within `--birth-hours`); fewer alive than the floor with no birth for that long is
              a FAIL (the population collapsed and nothing refills it; the check names the architect's last
              passes and why each was skipped). With `population.floor_researching` false the floor counts
              every living family, and fewer alive than the floor is a FAIL at once, as before;
- cycles      every living family has completed at least one model cycle (a cycle with a model call and no
              error), and the median cycle is under 180 s; the slowest and the error count are reported;
- gym         Gym boxes ready or busy, batches run, program-years, trials in total;
- tournament  the hourly tournament has written a leaderboard (a `swarm.tournament` event);
- guard       the Sail guard's last reading (balance, the House's line) and whether it brakes;
- spend       the swarm's spend in the last hour by kind ($/hour);
- ledger      the House ledger holds the mirrored `swarm.*` rows (the House's step is running);
- gate        holdout looks and passes so far, the leakage alarm, refusals (WAIT until a family meets the line).

It never writes: the stores are opened read-only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path


def ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def epoch(text: object) -> float | None:
    """An ISO time of the store ("2026-10-03T14:38:00Z") in seconds, or None."""
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/workspace/state")
    parser.add_argument("--since-minutes", type=float, default=60.0)
    parser.add_argument("--floor", type=int, default=None, help="the population floor (default: swarm.json's, else 16)")
    parser.add_argument("--birth-hours", type=float, default=6.0,
                        help="below the floor, FAIL when no family was born (and the swarm did not start) within this long")
    parser.add_argument("--now", type=float, default=None, help=argparse.SUPPRESS)  # a store copy read at its own time
    args = parser.parse_args(argv)
    root = Path(args.root)
    now = time.time() if args.now is None else float(args.now)
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - args.since_minutes * 60))
    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "root": str(root), "checks": {}}
    checks = out["checks"]

    try:
        beat = json.loads((root / "swarm.heartbeat").read_text())
    except (OSError, ValueError):
        beat = None
    current = root.parent / "current"
    release = str(current.resolve()) if current.exists() else None
    if beat is None:
        checks["process"] = {"result": "FAIL", "why": "no heartbeat"}
    else:
        age = now - float(beat.get("at") or 0)
        ok = age < 60 and alive(beat.get("pid")) and (release is None or beat.get("release") == release)
        checks["process"] = {"result": "PASS" if ok else "FAIL", "pid": beat.get("pid"), "heartbeat_age_s": round(age, 1),
                             "release": beat.get("release"), "house_release": release, "status": beat.get("status")}

    db_path = root / "swarm.sqlite"
    if not db_path.exists():
        checks["store"] = {"result": "FAIL", "why": "no swarm.sqlite"}
        print(json.dumps(out, indent=1, default=str))
        return 1
    db = ro(db_path)
    fams = [dict(r) for r in db.execute("SELECT id, band, retired_at FROM families")]
    living = [f["id"] for f in fams if not f["retired_at"]]
    try:  # the settings in effect: swarm.json over the release's policy.json (settings as code, V3-A)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from league.swarm import settings as settings_mod

        pop = dict(settings_mod.load(root).get("population") or {})
    except Exception:  # noqa: BLE001 - no release beside this script: swarm.json alone, as before
        try:
            pop = dict(json.loads((root / "swarm.json").read_text()).get("population") or {})
        except (OSError, ValueError, AttributeError):
            pop = {}
    start, ceiling = int(pop.get("start", 48)), int(pop.get("ceiling", 96))
    floor = args.floor if args.floor is not None else int(pop.get("floor", 16))
    # THE FLOOR COUNTS RESEARCH (F1): the floor holds the families that research, so dead slots may leave below it and
    # the architect refills (WAIT); with `population.floor_researching` false it counts every living family, as before.
    below = len(living) < floor and pop.get("floor_researching", True) is False
    # A population below the floor is refilling only while the architect bears: with no birth (and no swarm start) for
    # `--birth-hours` it has collapsed, and waiting will not mend it (a FAIL, with the architect's last passes).
    born = epoch(db.execute("SELECT MAX(born_at) AS at FROM families").fetchone()["at"])
    try:
        started = float((beat or {}).get("started_at"))
    except (TypeError, ValueError):
        started = None
    marks = [t for t in (born, started) if t is not None]
    quiet = now - max(marks) if marks else None
    collapsed = len(living) < floor and quiet is not None and quiet > args.birth_hours * 3600.0
    passes = []
    for r in db.execute("SELECT at, payload FROM events WHERE kind='swarm.architect' ORDER BY seq DESC LIMIT 6"):
        try:
            made = json.loads(r["payload"])
        except ValueError:
            continue
        passes.append({"at": r["at"], "born": len(made.get("born") or []), "skipped": made.get("skipped"),
                       "error": bool(made.get("error"))})
    verdict = "FAIL" if below or collapsed or len(living) > ceiling else ("WAIT" if len(living) < start else "PASS")
    checks["population"] = {"result": verdict, "alive": len(living), "floor": floor, "start": start, "ceiling": ceiling,
                            "retired": len(fams) - len(living),
                            "bands": {b: sum(1 for f in fams if f["band"] == b) for b in ("gym", "candidate", "probe", "sized", "retired")},
                            "hours_since_a_birth_or_the_start": None if quiet is None else round(quiet / 3600.0, 2),
                            "architect_passes": passes}
    if collapsed:
        checks["population"]["why"] = (f"{len(living)} alive, under the floor of {floor}, and no family was born in the last "
                                       f"{args.birth_hours:g} hours: the architect is not refilling it")

    cycles = [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM events WHERE kind='swarm.cycle'")]
    model = [c for c in cycles if int(c.get("model_calls") or 0) > 0 and not c.get("error")]
    done = {c["family"] for c in model}
    recent = [json.loads(r["payload"]) for r in db.execute("SELECT payload FROM events WHERE kind='swarm.cycle' AND at >= ?", (since,))]
    secs = [float(c.get("seconds") or 0) for c in model]
    missing = sorted(set(living) - done)
    checks["cycles"] = {"result": "PASS" if not missing and secs and statistics.median(secs) < 180 else ("WAIT" if model else "FAIL"),
                        "families_with_a_model_cycle": len(done & set(living)), "missing": missing[:20],
                        "median_seconds": round(statistics.median(secs), 1) if secs else None,
                        "p90_seconds": round(sorted(secs)[max(0, -(-9 * len(secs) // 10) - 1)], 1) if secs else None,
                        "slowest_seconds": round(max(secs), 1) if secs else None,
                        "under_180_share": round(sum(1 for s in secs if s < 180) / len(secs), 3) if secs else None,
                        "cycles_total": len(cycles), "cycles_recent": len(recent),
                        "errors_recent": sum(1 for c in recent if c.get("error")),
                        "error_examples": sorted({str(c.get("error"))[:120] for c in recent if c.get("error")})[:5]}

    boxes = [dict(r) for r in db.execute("SELECT id, kind, state, jobs, busy_seconds FROM boxes")]
    runs = dict(db.execute("SELECT COUNT(*) AS runs, COALESCE(SUM(trials),0) AS trials, COALESCE(SUM(program_years),0) AS years FROM runs").fetchone())
    gym_live = [b for b in boxes if b["kind"] == "gym" and b["state"] in ("ready", "busy", "asleep")]
    checks["gym"] = {"result": "PASS" if gym_live and runs["trials"] > 0 else "FAIL",
                     "by_state": {s: sum(1 for b in boxes if f"{b['kind']}:{b['state']}" == s) for s in {f"{b['kind']}:{b['state']}" for b in boxes}},
                     "jobs": sum(int(b["jobs"]) for b in boxes), "busy_hours": round(sum(float(b["busy_seconds"]) for b in boxes) / 3600, 2),
                     "trials": runs["trials"], "program_years": round(runs["years"], 2)}

    tour = db.execute("SELECT at, payload FROM events WHERE kind='swarm.tournament' ORDER BY seq DESC LIMIT 1").fetchone()
    if tour:
        payload = json.loads(tour["payload"])
        checks["tournament"] = {"result": "PASS", "at": tour["at"], "board_rows": len(payload.get("board") or []),
                                "validated": len((payload.get("validation") or {}).get("judged") or {}),
                                "gate_ready": sum(1 for r in payload.get("board") or [] if r.get("gate_ready")),
                                "born": payload.get("born"), "retired": payload.get("retired"), "totals": payload.get("totals")}
    else:
        checks["tournament"] = {"result": "FAIL", "why": "no tournament written yet"}

    kv = {r["key"]: json.loads(r["value"]) for r in db.execute("SELECT key, value FROM kv")}
    checks["gym"]["pool_token"] = kv.get("pool_token")  # its boxes are named ltcm-swarm-<token>-<kind>-...
    guard = kv.get("guard") or {}
    checks["guard"] = {"result": "PASS" if guard.get("last") else "FAIL", **(guard.get("last") or {})}

    hour = now - 3600
    spend = {r["kind"]: round(float(r["usd"]), 4) for r in db.execute("SELECT kind, SUM(usd) AS usd FROM spend WHERE epoch >= ? GROUP BY kind", (hour,))}
    total = {r["kind"]: round(float(r["usd"]), 4) for r in db.execute("SELECT kind, SUM(usd) AS usd FROM spend GROUP BY kind")}
    checks["spend"] = {"result": "PASS", "last_hour": spend, "usd_per_hour": round(sum(spend.values()), 4), "since_start": total}

    ledger = root / "ledger.sqlite"
    if ledger.exists():
        lg = ro(ledger)
        rows = {r["kind"]: r["n"] for r in lg.execute("SELECT kind, COUNT(*) AS n FROM ledger WHERE kind LIKE 'swarm.%' GROUP BY kind")}
        born = lg.execute("SELECT COUNT(*) AS n FROM ledger WHERE kind='agent.born'").fetchone()["n"]
        lg.close()
        checks["ledger"] = {"result": "PASS" if rows and born == 0 else "FAIL", "swarm_rows": rows,
                            "house_agent_born_rows": born, "note": "the swarm's House seats no agent of its own"}
    else:
        checks["ledger"] = {"result": "FAIL", "why": "no House ledger"}

    looks = [dict(r) for r in db.execute("SELECT family, version, passed, at FROM looks ORDER BY seq")]
    refusals = [dict(r) for r in db.execute("SELECT family, stage, reason, at FROM refusals ORDER BY seq DESC LIMIT 10")]
    # THE LOOK HOLDS (L6, Oct 2, 2026): a store from before them has no table.
    holds = [dict(r) for r in db.execute("SELECT family, version, stage, at FROM look_holds ORDER BY seq DESC LIMIT 10")] \
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='look_holds'").fetchone() else []
    checks["gate"] = {"result": "PASS" if looks else "WAIT", "looks": len(looks), "passes": sum(1 for x in looks if x["passed"]),
                      "leakage_alarm": kv.get("leakage_alarm"), "recent_refusals": refusals, "recent_look_holds": holds}
    db.close()
    print(json.dumps(out, indent=1, default=str))
    return 1 if any(c.get("result") == "FAIL" for c in checks.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
