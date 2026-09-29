#!/usr/bin/env python3
"""The Gym image and the gate image: sealed forks of the data box, checkpointed for a year.

    python3 scripts/data/images.py build gym [--version v1] [--force] [--train-from 2020-01-02]
                                             [--roots R,...] [--root-first XSP=2020-01-02,...] [--early-names R,...]
    python3 scripts/data/images.py build gate [--version v1] [--force]
    python3 scripts/data/images.py verify gym|gate [--checkpoint ID] [--train-from D] [--root-first R=D,...]
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

THE 2020-21 EXTENSION (Sept 27, 2026). `--train-from 2020-01-02` (Gym only) keeps stages 9 and 10's days as Train in
the Gym image; without it (the default) they are "pre" and pruned, so an image built after the fetch holds exactly what
one built before it held. The gate never takes them (it runs the holdout and forward days only). The choice is recorded
in images.json (`train_from`) and checked from inside: no file dated before Train's first day.

TRAIN FROM 2017 (Sept 29, 2026). `--train-from 2017-01-03` keeps 2017-19 as Train too, with the underlying of the 60
sessions before 2017-01-03 as history (`HISTORY_REACH_DAYS` covers them). `--root-first ROOT=DATE,...` gives a root
its own later first Train day (`storelib.parse_root_first`): nothing of that root before it stays but the underlying of
the 60 sessions before it, as history. So `XSP=2020-01-02` drops XSP's 2017-19, if thin, and keeps its 2020-21. It
replaces `--early-roots` (kept, unchanged, for the images built from 2020 with it; the two never mix, and a build from
before 2020 refuses `--early-roots`), is recorded in images.json (`root_first`) and checked from inside, root by root.

The names (every root outside the core five) enter Train before 2020-01-02 only on purpose (`NAMES_FIRST`): an
engine that lacks a name's split rows reads a split as a crash, and pruning keeps files by date, so a name's partly
fetched earlier years would enter too. A build from before 2020 therefore lists its roots (`--roots`), and every name
has a `--root-first` of 2020-01-02 or later unless `--early-names` names it (once its split rows are in
`league/gym/events.py` and its years are complete). The inside check holds every name that is not in `--early-names`
to 2020-01-02 (its history to the 100 days before), whatever the build was told, and holds the image's first chain to
its `train_from` exactly: the Gym reads a store's first Train day from its first chain, and the pool refuses a Train
run whose span is not that day. `--early-names` is recorded in images.json (`early_names`).

The fork prunes with the data tools of the build that asked for it (`boxlib.push_code` before the prune): the data
box may be running other code (a fetch pushes its own), which would not know `--root-first`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

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

#: The store's own facts, inside the check below (`store` and `out` are the check's): split out so the tests read a
#: synthetic image with exactly the code the sealed box runs.
STORE_FACTS = r"""
dates = sorted(p.stem for p in store.glob("*/*/*.parquet"))
out["files"] = len(dates)
out["first_date"] = dates[0] if dates else None
first_by_kind = {}
first_by_root = {}
for p in store.glob("*/*/*.parquet"):
    kind, root = p.parent.parent.name, p.parent.name
    if kind not in first_by_kind or p.stem < first_by_kind[kind]:
        first_by_kind[kind] = p.stem
    row = first_by_root.setdefault(kind, {})
    if root not in row or p.stem < row[root]:
        row[root] = p.stem
out["first_by_kind"] = first_by_kind
out["first_by_root"] = first_by_root
out["last_date"] = dates[-1] if dates else None
out["dated_after_validation"] = sum(1 for d in dates if d > "2025-12-31")
import polars as pl
m = pl.read_parquet(store / "manifest.parquet")
out["manifest_rows"] = m.height
out["manifest_windows"] = sorted(set(m["window"].to_list()))
out["history_kinds"] = sorted(set(m.filter(pl.col("window") == "history")["kind"].to_list()))
out["manifest_last"] = str(m["date"].max()) if m.height else None
out["manifest_first"] = str(m["date"].min()) if m.height else None
c = pl.read_parquet(store / "calendar.parquet")
out["calendar_last"] = str(c["date"].max()) if c.height else None
out["calendar_first"] = str(c["date"].min()) if c.height else None
e = pl.read_parquet(store / "expiries.parquet")
out["expiries_last_date"] = str(e["date"].max()) if e.height else None
out["version"] = (store / "VERSION").read_text().strip()
out["gate_mark"] = (store / "GATE").is_file()
"""

INSIDE_CHECK = r"""
import json, os, pathlib, subprocess
out = {}
out["key_file"] = os.path.exists("/data/secrets/thetadata.env") or os.path.exists("/data/secrets")
# A key LINE (the name assigned a value), not source code that merely names the variable.
# Parquet in the store is columnar data we wrote ourselves; every other file is searched.
hits = subprocess.run(["grep", "-rIlE", "--exclude=*.parquet", r"THETADATA_API_KEY[[:space:]]*=[[:space:]]*[A-Za-z0-9_-]{8,}",
                       "/data", "/root", "/tmp", "/home", "/etc", "/var/tmp"], capture_output=True, text=True).stdout.split()
out["key_mentions"] = hits
out["store_non_parquet"] = sorted(str(p) for p in pathlib.Path("/data/store").rglob("*")
                                  if p.is_file() and p.suffix != ".parquet" and p.name not in ("VERSION", "GATE"))
store = pathlib.Path("/data/store")""" + STORE_FACTS + r"""out["work_exists"] = os.path.exists("/data/work")
out["processes"] = subprocess.run(["pgrep", "-fa", "[b]ackfill.py (run|one)|[u]niverse.py|[m]ultiprocessing.spawn|[l]eague.gym.calibrate"],
                                  capture_output=True, text=True).stdout.strip()
print(json.dumps(out))
"""


#: After the prune: the page cache dropped and the free memory overwritten, so neither the deleted
#: key file's cached pages nor a stopped process's freed pages go into the image's checkpoint.
SCRUB = r"""
sync; echo 3 > /proc/sys/vm/drop_caches
/opt/data-venv/bin/python - <<'PY'
import os
free = 0
for line in open('/proc/meminfo'):
    if line.startswith('MemAvailable:'):
        free = int(line.split()[1]) * 1024
chunk, held = 256 * 2**20, []
target = int(free * 0.85)
while sum(len(b) for b in held) + chunk <= target:
    b = bytearray(chunk)
    for i in range(0, chunk, 4096):
        b[i] = 0
    held.append(b)
print('scrubbed', sum(len(b) for b in held) // 2**20, 'MiB')
PY
sync; echo 3 > /proc/sys/vm/drop_caches
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
    latest = {}
    for row in journal_lines:
        if row.get("type") == "task":
            key = (str(row.get("stage")), row.get("task"))
            if row.get("status") in ("ok", "empty"):
                latest[key] = row
            elif row.get("status") == "invalidated":
                latest.pop(key, None)
    done: dict[str, int] = {}
    for stage, _ in latest:
        done[stage] = done.get(stage, 0) + 1
    return {str(s): {"done": done.get(str(s), 0), "planned": plan_counts.get(str(s))} for s in stages}


def verify_inside(api: Any, box: str, kind: str, *, sleep: Callable[[float], None] = time.sleep,
                  train_from: str | None = None, root_first: Mapping[str, str] | None = None,
                  early_names: Sequence[str] | None = None) -> dict[str, Any]:
    net = api.exec(box, ["/opt/data-venv/bin/python", "-c", NETWORK_PROBE], timeout=120)
    # Detached and polled: on a store of 20,000 files the check outlived one exec stream (Sept 26 14:31Z).
    api.upload(box, "/root/inside_check.py", INSIDE_CHECK.encode(), mode=0o600)
    api.exec(box, "rm -f /root/inside_check.json; setsid nohup /opt/data-venv/bin/python /root/inside_check.py "
                  "> /root/inside_check.json 2> /root/inside_check.err < /dev/null &", timeout=60, background=True)
    facts = None
    for _ in range(120):
        sleep(10)
        out = api.exec(box, ["bash", "-c", "cat /root/inside_check.json 2>/dev/null"], timeout=60).stdout.strip()
        if out:
            try:
                facts = json.loads(out.splitlines()[-1])
                break
            except ValueError:
                pass
    err = api.exec(box, ["bash", "-c", "cat /root/inside_check.err 2>/dev/null; rm -f /root/inside_check.*"], timeout=60).stdout
    if facts is None:
        raise SystemExit(f"the inside check did not finish on {box}: {err[-1500:]}")
    lines = net.stdout.strip().splitlines()
    facts["network"] = lines
    facts["problems"] = problems_of(facts, kind, train_from=train_from, root_first=root_first, early_names=early_names)
    facts["passed"] = not facts["problems"]
    return facts


#: How far before Train's first day the history sessions' underlying may reach (60 sessions is about 87 calendar days).
HISTORY_REACH_DAYS = 100
#: The first day a name (a root outside the core five) may have in a Gym image that starts before it, unless the build
#: names it in `--early-names` (the module docstring): the names' own fetch began at 2020-01-02 (`storelib.EARLY`), and
#: their earlier years need their split rows in the Gym's events table first.
NAMES_FIRST = sl.EARLY[0]


def parse_names(value: Any) -> tuple[str, ...]:
    """`--early-names ROOT,...` (or a sequence) as upper-case roots, in order; refused: a root that is not a symbol or
    is one of the core five (they need no leave), and one named twice."""
    if not value:
        return ()
    parts = value.split(",") if isinstance(value, str) else [str(v) for v in value]
    out: list[str] = []
    for part in parts:
        root = part.strip().upper()
        if not root:
            continue
        if not root.isalnum():
            raise ValueError(f"--early-names: not a root: {root!r}")
        if root in sl.CORE_FIVE:
            raise ValueError(f"--early-names: {root} is a core root; only the names need it")
        if root in out:
            raise ValueError(f"--early-names names {root} twice")
        out.append(root)
    return tuple(out)


def names_without_a_first_day(roots: Sequence[str], root_first: Mapping[str, dt.date] | None,
                              early_names: Sequence[str] = ()) -> list[str]:
    """The names of `roots` that a build starting before `NAMES_FIRST` would let into Train before it: neither in
    `early_names` nor given a `root_first` day on or after `NAMES_FIRST`."""
    own = {str(r).upper(): d for r, d in (root_first or {}).items()}
    allowed = {str(r).upper() for r in early_names}
    return [r for r in roots if str(r).upper() not in sl.CORE_FIVE and str(r).upper() not in allowed
            and not (own.get(str(r).upper()) is not None and own[str(r).upper()] >= NAMES_FIRST)]


def problems_of(facts: Mapping[str, Any], kind: str, *, train_from: str | None = None,
                root_first: Mapping[str, str] | None = None, early_names: Sequence[str] | None = None) -> list[str]:
    """What is wrong with an image from its inside facts (empty: it passes). `train_from` is the Gym image's first Train
    day (None: 2022-01-03, every image before the 2020-21 extension): no chain (nbbo, oi, trade_quote) is dated before
    it, and its first chain (nbbo) is dated exactly then (the Gym's `train_first`, which the pool holds to the swarm's
    span); with it, the underlying and the calendar may reach back to the history sessions (at most
    `HISTORY_REACH_DAYS`) and the manifest's "history" rows are underlying only. Without it, nothing is dated before
    2022-01-03. `root_first` ({root: ISO day}, Train from 2017) holds each listed root to its own day the same way
    (`first_by_root`); from a `train_from` before `NAMES_FIRST`, every name outside `early_names` is held to
    `NAMES_FIRST` too. An image built with either and checked without its per-root facts is refused."""
    lines = facts.get("network") or []
    problems = []
    if not lines or any(not line.startswith("NETWORK-CLOSED") for line in lines):
        problems.append("a connection out did not fail")
    if facts["key_file"] or facts["key_mentions"]:
        problems.append("a key file or a key line is present")
    if facts.get("store_non_parquet"):
        problems.append(f"unexpected files in the store: {facts['store_non_parquet'][:5]}")
    if facts["processes"]:
        problems.append("a data process is running")
    if kind == "gym":
        if facts["dated_after_validation"]:
            problems.append(f"{facts['dated_after_validation']} files dated after 2025-12-31")
        first = str(train_from or sl.TRAIN[0].isoformat())
        reach = (dt.date.fromisoformat(first) - dt.timedelta(days=HISTORY_REACH_DAYS)).isoformat() if train_from else first
        by_kind = facts.get("first_by_kind") or {}
        for name, day in sorted(by_kind.items()):
            floor = reach if name == "underlying" else first
            if day and str(day) < floor:
                problems.append(f"the first {name} file {day} is before {floor}")
        if train_from and str(by_kind.get("nbbo")) != first:
            problems.append(f"the first chain (nbbo) is {by_kind.get('nbbo')}, not the image's first Train day {first}: "
                            f"the Gym would read {by_kind.get('nbbo')} as its first Train day and the pool would refuse "
                            f"every Train run from {first}")
        for key in ("first_date", "manifest_first", "calendar_first"):
            if facts.get(key) and str(facts[key]) < reach:
                problems.append(f"{key} {facts[key]} is before {reach}")
        # Each root's own first day: the build's `root_first`, and NAMES_FIRST for every name it did not leave early.
        own_days = {str(r): (str(d), "") for r, d in (root_first or {}).items()}
        names_held = bool(train_from) and first < NAMES_FIRST.isoformat()
        by_root = facts.get("first_by_root")
        if (own_days or names_held) and not isinstance(by_root, Mapping):
            problems.append("no first_by_root facts: the image's own first Train day per root cannot be checked")
        by_root = by_root if isinstance(by_root, Mapping) else {}
        if names_held:
            allowed = {str(r).upper() for r in (early_names or ())}
            seen = {str(root) for row in by_root.values() if isinstance(row, Mapping) for root in row}
            for root in sorted(seen):
                if root.upper() in sl.CORE_FIVE or root.upper() in allowed:
                    continue
                day, _ = own_days.get(root, ("", ""))
                if day < NAMES_FIRST.isoformat():
                    own_days[root] = (NAMES_FIRST.isoformat(), " (a name enters Train before "
                                      f"{NAMES_FIRST} only with its split rows and --early-names)")
        for root, (own, why) in sorted(own_days.items()):
            own_reach = (dt.date.fromisoformat(own) - dt.timedelta(days=HISTORY_REACH_DAYS)).isoformat()
            for name, row in sorted(by_root.items()):
                day = row.get(root) if isinstance(row, Mapping) else None
                floor = own_reach if name == "underlying" else own
                if day and str(day) < floor:
                    problems.append(f"the first {name} file of {root} {day} is before {floor}{why}")
        allowed = {"train", "validation"} | ({"history"} if train_from else set())
        if set(facts["manifest_windows"]) - allowed:
            problems.append(f"manifest windows {facts['manifest_windows']}")
        if set(facts.get("history_kinds") or []) - {"underlying"}:
            problems.append(f"history rows of {facts['history_kinds']}: the history sessions carry the underlying only")
        for key in ("manifest_last", "calendar_last", "expiries_last_date"):
            if facts.get(key) and facts[key] > "2025-12-31":
                problems.append(f"{key} {facts[key]}")
        if facts["work_exists"]:
            problems.append("/data/work exists")
        if facts["gate_mark"]:
            problems.append("the Gym image carries the gate's GATE mark")
    elif kind == "gate" and not facts["gate_mark"]:
        problems.append("the gate image has no GATE mark (league.gym.store.mint_gate_capability needs it)")
    if kind == "gate":
        for key in ("first_date", "manifest_first"):
            if facts.get(key) and str(facts[key]) < sl.TRAIN[0].isoformat():
                problems.append(f"{key} {facts[key]}: the gate never carries the 2020-21 extension")
    return problems


def _iso(root_first: Mapping[str, Any] | None) -> dict[str, str] | None:
    """{root: ISO day} for images.json and the inside check (None when there is none)."""
    return {str(r): (d.isoformat() if isinstance(d, dt.date) else str(d)) for r, d in sorted(root_first.items())} \
        if root_first else None


def prune_arguments(spec: Mapping[str, Any], *, roots: tuple[str, ...] | None = None, train_from: dt.date | None = None,
                    early_roots: tuple[str, ...] | None = None,
                    root_first: Mapping[str, dt.date] | None = None) -> str:
    """The fork's `backfill.py prune` arguments: the kind's own, then the roots, Train's first day and each root's."""
    own = ",".join(f"{r}={d}" for r, d in sorted((_iso(root_first) or {}).items()))
    return spec["prune"] + (f" --roots {','.join(roots)}" if roots else "") + (
        f" --train-from {train_from.isoformat()}" if train_from else "") + (
        f" --early-roots {','.join(early_roots)}" if early_roots else "") + (f" --root-first {own}" if own else "")


def checkpoint_with_retry(api: Any, box: str, *, name: str, ttl_seconds: int, attempts: int = 6,
                          sleep: Callable[[float], None] = time.sleep, errors: list[dict[str, Any]] | None = None,
                          check_lease: Callable[[], None] = lambda: None) -> dict[str, Any]:
    """Sail's checkpoint API has failed for hours at a time (Sept 25; Sept 26 06:35Z and 07:00Z on the
    House box): retry with backoff and keep every error, verbatim, for the record."""
    delay = 30.0
    for attempt in range(1, attempts + 1):
        check_lease()
        try:
            result = api.checkpoint(box, name=name, ttl_seconds=ttl_seconds, timeout=1800)
            check_lease()
            return result
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


def wait_until_complete(kind: str, *, poll: float = 120.0, api: Any = None, sleep: Callable[[float], None] = time.sleep,
                        log: Callable[[str], None] = say, needs: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Block until the data box's progress shows every stage this image needs as complete."""
    api = api or bl.client()
    box = bl.data_box_id()
    last = None
    needs = tuple(needs or KINDS[kind]["needs_stages"])
    while True:
        try:
            progress = json.loads(api.download(box, "/data/work/progress.json"))
            rows = {str(s): (progress.get("stages") or {}).get(str(s)) or {} for s in needs}
            if all(r.get("planned") and r.get("done", 0) >= r["planned"] for r in rows.values()):
                log(f"{kind}: stages {sorted(rows)} complete at {bl.now()}")
                return rows
            summary = {s: f"{r.get('done')}/{r.get('planned')}" for s, r in rows.items()}
            if summary != last:
                log(f"{kind}: waiting, stages {summary} at {bl.now()}")
                last = summary
        except (bl.SailboxError, ValueError, KeyError) as error:
            log(f"{kind}: progress unreadable ({type(error).__name__}); retrying")
        sleep(poll)


def build(kind: str, *, version: str, force: bool, api: Any = None, sleep: Callable[[float], None] = time.sleep,
          ttl_days: int = 365, rehearsal: bool = False, keep: bool = False,
          needs: tuple[int, ...] | None = None, roots: tuple[str, ...] | None = None,
          train_from: dt.date | None = None, early_roots: tuple[str, ...] | None = None,
          root_first: Mapping[str, Any] | str | None = None,
          early_names: Sequence[str] | str | None = None) -> dict[str, Any]:
    """Build one image. `rehearsal` runs every step on whatever the store holds now, then
    terminates the fork and records the result under `rehearsals` (never as the current image).
    One build at a time: each stops and restarts the data box's backfill around its checkpoint.
    `train_from` (the Gym only; 2020-01-02 switches the 2020-21 extension on, 2017-01-03 Train from 2017) is Train's
    first day in the image, `root_first` ({root: day}) a root's own later first Train day, and `early_roots` (the older
    form, core roots only, from 2020 only) the roots whose 2020-21 days it keeps (all fetched ones by default). From
    before `NAMES_FIRST` the build lists its `roots`, and each name there has a `root_first` on or after `NAMES_FIRST`
    or is in `early_names` (the module docstring)."""
    if early_roots and train_from is None:
        raise SystemExit("--early-roots goes with --train-from")
    if root_first and train_from is None:
        raise SystemExit("--root-first goes with --train-from")
    if early_roots and root_first:
        raise SystemExit("--early-roots and --root-first do not mix (--root-first replaces --early-roots)")
    if train_from is not None and kind != "gym":
        raise SystemExit("--train-from is for the Gym image: the gate never carries Train's earlier years")
    if train_from is not None:
        sl.window_of(train_from, train_from)  # refuses a first day outside 2017-01-03..2022-01-03
    try:
        root_first = sl.parse_root_first(root_first, train_from) or None
        early_names = parse_names(early_names) or None
    except ValueError as error:
        raise SystemExit(str(error)) from None
    before_names = train_from is not None and train_from < NAMES_FIRST
    if early_roots and before_names:
        raise SystemExit(f"--early-roots is for an image from {NAMES_FIRST} (a root it leaves out starts at "
                         f"{sl.TRAIN[0]}); from {train_from} give each root its own day with --root-first")
    if early_names and not before_names:
        raise SystemExit(f"--early-names goes with a --train-from before {NAMES_FIRST}")
    if before_names:
        if not roots:
            raise SystemExit(f"an image from before {NAMES_FIRST} lists its roots (--roots), so that each name's first "
                             f"Train day is checked before the fork")
        stray = sorted(set(early_names or ()) - {str(r).upper() for r in roots})
        if stray:
            raise SystemExit(f"--early-names {','.join(stray)}: not among --roots")
        loose = names_without_a_first_day(roots, root_first, early_names or ())
        if loose:
            raise SystemExit(f"from {train_from}, these names would enter Train before {NAMES_FIRST}: "
                             f"{','.join(loose)}. List each in --root-first at {NAMES_FIRST} or later, or, once its split "
                             f"rows are in league/gym/events.py and its years are complete, in --early-names")
    import fcntl

    bl.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(bl.STATE_DIR / "images.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        api = api or bl.client()
        data_box = bl.data_box_id()
        bl.ensure_running(api, data_box)
        with bl.RemoteLease(api, data_box) as lease:
            return _build(kind, version=version, force=force, api=api, sleep=sleep, ttl_days=ttl_days,
                          rehearsal=rehearsal, keep=keep, needs=needs, roots=roots, check_lease=lease.check,
                          train_from=train_from, early_roots=early_roots, root_first=root_first,
                          early_names=early_names)


def _build(kind: str, *, version: str, force: bool, api: Any, sleep: Callable[[float], None],
           ttl_days: int, rehearsal: bool, keep: bool, needs: tuple[int, ...] | None = None,
           roots: tuple[str, ...] | None = None,
           check_lease: Callable[[], None] = lambda: None, train_from: dt.date | None = None,
           early_roots: tuple[str, ...] | None = None,
           root_first: Mapping[str, dt.date] | None = None,
           early_names: tuple[str, ...] | None = None) -> dict[str, Any]:
    api = api or bl.client()
    spec = dict(KINDS[kind])
    if needs:
        spec["needs_stages"] = tuple(needs)
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
    from nightly import BoxHandle

    data = BoxHandle(api, data_box)
    was_running = data.backfill_running()
    last_args = None
    if was_running:
        last_args = (bl.read_json(bl.DATA_BOX).get("runs") or [{}])[-1].get("args")
        if not last_args:
            raise RuntimeError("cannot stop a backfill without its restart arguments")
        check_lease()
        data.stop_backfill()
        say("  backfill stopped for the checkpoint")
    try:
        source = checkpoint_with_retry(api, data_box, name=f"ltcm-data-for-{kind}-{version}",
                                       ttl_seconds=(2 if rehearsal else 30) * 86400,
                                       sleep=sleep, errors=errors, check_lease=check_lease)
    finally:
        if was_running and last_args:
            check_lease()
            data.start_backfill(last_args)
            say("  backfill restarted")
    say(f"  data box checkpoint {source['checkpoint_id']}")
    # 3. fork, seal first, stop anything carried over
    check_lease()
    fork = api.from_checkpoint(source["checkpoint_id"], name=f"ltcm-{kind}-image-{version}", timeout=1800)
    box = fork["sailbox_id"]
    say(f"  fork {box}; sealing")
    seal(api, box)
    api.exec(box, ["bash", "-c", "pkill -f '[b]ackfill.py|[u]niverse.py|[m]ultiprocessing|[l]ocking.py serve' ; "
                                  "rm -f /data/work/backfill.pid; true"], timeout=60)
    # 4. prune, with this build's own data tools: the data box may run other code (a fetch pushes its own)
    check_lease()
    bl.push_code(api, box)
    prune_args = prune_arguments(spec, roots=roots, train_from=train_from, early_roots=early_roots,
                                 root_first=root_first)
    pruned = bl.run_py(api, box, f"backfill.py prune {prune_args}", timeout=3600).check()
    say(f"  pruned: {pruned.stdout.strip().splitlines()[-1]}")
    if kind == "gate":
        # The mark league.gym.store.mint_gate_capability requires; only the gate image carries it.
        api.upload(box, "/data/store/GATE", f"gate image {version} built {bl.now()}\n".encode(), mode=0o444)
    else:
        api.exec(box, ["rm", "-f", "/data/store/GATE"], timeout=60)
    scrub = api.exec(box, ["bash", "-c", SCRUB], timeout=900)
    say(f"  memory: {scrub.stdout.strip() or scrub.output[-300:]}")
    # 5. verify
    check_lease()
    facts = verify_inside(api, box, kind, train_from=train_from.isoformat() if train_from else None,
                          root_first=_iso(root_first), early_names=early_names)
    say(f"  inside: {json.dumps({k: facts[k] for k in ('passed', 'problems', 'files', 'first_date', 'last_date', 'manifest_windows', 'network')})}")
    if not facts["passed"]:
        api.sleep(box)
        raise SystemExit(f"the {kind} image failed its checks; the fork {box} is asleep for inspection")
    # 6. two checkpoints, one year each, then sleep
    checkpoints = []
    started = time.time()
    for label in (("a",) if rehearsal else ("a", "b")):
        row = checkpoint_with_retry(api, box, name=f"ltcm-{kind}-image-{version}-{label}", ttl_seconds=ttl_days * 86400,
                                    sleep=sleep, errors=errors, check_lease=check_lease)
        checkpoints.append(row["checkpoint_id"])
        say(f"  checkpoint {label}: {row['checkpoint_id']} ({time.time() - started:.0f}s)")
    check_lease()
    record = bl.read_json(bl.IMAGES)
    if rehearsal:
        if keep:
            api.sleep(box)
        else:
            api.terminate(box)
        record.setdefault("rehearsals", []).append({"kind": kind, "version": version, "box_id": box, "terminated": not keep,
                                                    "train_from": train_from.isoformat() if train_from else None,
                                                    "root_first": _iso(root_first),
                                                    "early_names": list(early_names) if early_names else None,
                                                    "checkpoints": checkpoints, "ttl_days": ttl_days, "at": bl.now(),
                                                    "passed": facts["passed"], "files": facts["files"],
                                                    "checkpoint_errors": errors})
        check_lease()
        bl.write_json(bl.IMAGES, record)
        return record["rehearsals"][-1]
    api.sleep(box)
    entry = {
        "version": version, "box_id": box, "checkpoints": checkpoints, "source_checkpoint": source["checkpoint_id"],
        "built_at": bl.now(), "ttl_days": ttl_days, "sealed": {"no_network": True}, "windows": list(spec["keep"]),
        "train_from": train_from.isoformat() if train_from else None,
        "early_roots": list(early_roots) if early_roots else None,
        "root_first": _iso(root_first),
        "early_names": list(early_names) if early_names else None,
        "stages_at_build": have, "roots": list(roots) if roots else "all", "checkpoint_errors": errors, "gate_mark": facts["gate_mark"], "verified": {k: facts[k] for k in ("files", "first_date", "last_date", "manifest_rows",
                                                                    "manifest_windows", "network", "version")},
    }
    record.setdefault(kind, {}).update({"current": entry})
    record[kind].setdefault("history", []).append(entry)
    check_lease()
    bl.write_json(bl.IMAGES, record)
    return entry


def finish(kind: str, box: str, *, version: str, source_checkpoint: str, ttl_days: int = 365,
           sleep: Callable[[float], None] = time.sleep, api: Any = None,
           lease: Any = None) -> dict[str, Any]:
    """Verify, checkpoint twice and record a fork that `build` already pruned (when a build stopped
    after its prune, e.g. on an interrupted check)."""
    api = api or bl.client()
    if lease is None:
        data_box = bl.data_box_id()
        bl.ensure_running(api, data_box)
        with bl.RemoteLease(api, data_box) as held:
            return finish(kind, box, version=version, source_checkpoint=source_checkpoint,
                          ttl_days=ttl_days, sleep=sleep, api=api, lease=held)
    lease.check()
    bl.ensure_running(api, box)
    if kind == "gate":
        api.upload(box, "/data/store/GATE", f"gate image {version} built {bl.now()}\n".encode(), mode=0o444)
    recorded = (bl.read_json(bl.IMAGES).get(kind) or {}).get("current") or {}
    train_from = recorded.get("train_from") if recorded.get("box_id") == box else None
    root_first = recorded.get("root_first") if recorded.get("box_id") == box else None
    early_names = recorded.get("early_names") if recorded.get("box_id") == box else None
    facts = verify_inside(api, box, kind, sleep=sleep, train_from=train_from, root_first=root_first,
                          early_names=early_names)
    say(f"  inside: {json.dumps({k: facts[k] for k in ('passed', 'problems', 'files', 'first_date', 'last_date', 'manifest_windows')})}")
    if not facts["passed"]:
        api.sleep(box)
        raise SystemExit(f"the {kind} image failed its checks; the fork {box} is asleep for inspection")
    errors: list[dict[str, Any]] = []
    checkpoints = []
    for label in ("a", "b"):
        lease.check()
        row = checkpoint_with_retry(api, box, name=f"ltcm-{kind}-image-{version}-{label}", ttl_seconds=ttl_days * 86400,
                                    sleep=sleep, errors=errors, check_lease=lease.check)
        checkpoints.append(row["checkpoint_id"])
        say(f"  checkpoint {label}: {row['checkpoint_id']}")
    api.sleep(box)
    lease.check()
    record = bl.read_json(bl.IMAGES)
    previous = (record.get(kind) or {}).get("current") or {}
    entry = {**(previous if previous.get("box_id") == box else {}),
             "version": version, "box_id": box, "checkpoints": checkpoints, "source_checkpoint": source_checkpoint,
             "built_at": bl.now(), "ttl_days": ttl_days, "sealed": {"no_network": True}, "windows": list(KINDS[kind]["keep"]),
             "checkpoint_errors": errors, "gate_mark": facts["gate_mark"], "finished_by": "images.py finish",
             "verified": {k: facts[k] for k in ("files", "first_date", "last_date", "manifest_rows", "manifest_windows",
                                                "network", "version")}}
    record.setdefault(kind, {}).update({"current": entry})
    record[kind].setdefault("history", []).append(entry)
    bl.write_json(bl.IMAGES, record)
    return entry


def verify_arguments(entry: Mapping[str, Any], train_from: str | None = None, root_first: Any = None,
                     early_names: Any = None) -> dict[str, Any]:
    """The first Train day and each root's that `verify` checks an image against: the ones given, else the ones
    images.json recorded for it (`entry`). A `--root-first` is read against the image's own first Train day, so it needs
    no `--train-from` when images.json records one."""
    first = train_from or entry.get("train_from")
    try:
        own = _iso(sl.parse_root_first(root_first, dt.date.fromisoformat(str(first)) if first else None)) \
            if root_first else entry.get("root_first")
        names = list(parse_names(early_names)) if early_names else entry.get("early_names")
    except ValueError as error:
        raise SystemExit(str(error)) from None
    return {"train_from": first, "root_first": own or None, "early_names": names or None}


def verify(kind: str, checkpoint: str | None = None, train_from: str | None = None,
           root_first: Any = None, early_names: Any = None) -> dict[str, Any]:
    """Wake the recorded image box (or fork a new one from a checkpoint) and check it again, against the first Train day
    that image was built with (`train_from` names it for a checkpoint images.json does not know), and each root's own
    (`root_first` and `early_names`, likewise; `verify_arguments`)."""
    record = bl.read_json(bl.IMAGES).get(kind) or {}
    entry = record.get("current") or {}
    if checkpoint:
        # The checkpoint's own image: its train_from, not the current one's (an older or newer build may differ).
        entry = next((e for e in [entry, *reversed(record.get("history") or [])]
                      if checkpoint in (e.get("checkpoints") or []) or checkpoint == e.get("source_checkpoint")), {})
    against = verify_arguments(entry, train_from, root_first, early_names)  # refused before any box is woken
    api = bl.client()
    if checkpoint:
        box = api.from_checkpoint(checkpoint, name=f"ltcm-{kind}-verify", timeout=1800)["sailbox_id"]
        created = True
    else:
        box, created = entry["box_id"], False
        bl.ensure_running(api, box)
    try:
        return verify_inside(api, box, kind, **against)
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
    b.add_argument("--keep", action="store_true", help="with --rehearsal: leave the fork asleep (for a nightly rehearsal)")
    b.add_argument("--when-complete", action="store_true", help="wait until the data box holds what the image needs")
    b.add_argument("--roots", default="", help="keep only these roots (default: every root in the store)")
    b.add_argument("--needs", default="", help="the stages that must be complete (default gym 1, gate 1,2); "
                                                "Gym v2: 1,3,5 (2022 and the trade_quote samples)")
    b.add_argument("--train-from", default="", help="the Gym image's first Train day: 2020-01-02 keeps the 2020-21 "
                                                     "extension (stages 9, 10), 2017-01-03 2017-19 too; default "
                                                     "2022-01-03")
    b.add_argument("--root-first", default="", help="with --train-from: ROOT=YYYY-MM-DD,... a root's own later first "
                                                     "Train day (e.g. XSP=2020-01-02); from before 2020-01-02 every "
                                                     "name in --roots needs one on or after 2020-01-02")
    b.add_argument("--early-names", default="", help="from before 2020-01-02: the names that keep their earlier years "
                                                      "(only once their split rows are in league/gym/events.py)")
    b.add_argument("--early-roots", default="", help="with --train-from: only these core roots keep their 2020-21 days "
                                                      "(the older form; --root-first replaces it)")
    v = sub.add_parser("verify")
    v.add_argument("kind", choices=sorted(KINDS))
    v.add_argument("--checkpoint", default=None)
    v.add_argument("--train-from", default=None, help="the first Train day of a checkpoint images.json does not record")
    v.add_argument("--root-first", default="", help="its roots' own first Train days (ROOT=YYYY-MM-DD,...; default "
                                                     "images.json's)")
    v.add_argument("--early-names", default="", help="the names it keeps before 2020-01-02 (default images.json's)")
    f = sub.add_parser("finish", help="verify, checkpoint and record a fork a build already pruned")
    f.add_argument("kind", choices=sorted(KINDS))
    f.add_argument("--box", required=True)
    f.add_argument("--version", required=True)
    f.add_argument("--source-checkpoint", required=True)
    f.add_argument("--ttl-days", type=int, default=365)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        needs = tuple(int(x) for x in args.needs.split(",") if x.strip()) or None
        if args.when_complete:
            wait_until_complete(args.kind, needs=needs)
        roots = tuple(r.strip() for r in args.roots.split(",") if r.strip()) or None
        train_from = dt.date.fromisoformat(args.train_from) if args.train_from else None
        early = tuple(r.strip().upper() for r in args.early_roots.split(",") if r.strip()) or None
        print(json.dumps(build(args.kind, version=args.version, force=args.force or args.rehearsal,
                               ttl_days=args.ttl_days, rehearsal=args.rehearsal, keep=args.keep, needs=needs,
                               roots=roots, train_from=train_from, early_roots=early,
                               root_first=args.root_first or None, early_names=args.early_names or None), indent=1))
    elif args.cmd == "finish":
        print(json.dumps(finish(args.kind, args.box, version=args.version, source_checkpoint=args.source_checkpoint,
                                ttl_days=args.ttl_days), indent=1))
    elif args.cmd == "verify":
        print(json.dumps(verify(args.kind, args.checkpoint, args.train_from, args.root_first or None,
                                args.early_names or None), indent=1))
    else:
        print(json.dumps(bl.read_json(bl.IMAGES), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
