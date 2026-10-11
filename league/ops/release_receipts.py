"""RELEASE RECEIPTS (release E3, D17): a deploy's declared metric, read back by the stall job after its window.

Owner: C (league/ops/E3_INTERFACES.md). Protected. A release declares what it expects to move; the House reads the
metric back and lists the verdict. Listed, never reverted: a receipt changes no setting and rolls nothing back.

A DECLARATION is an object {"id", "release", "metric", "direction": "up" | "down", "min_delta", "window_hours",
"why"} in `<release>/league/ops/release_receipts.json` (`DECLARATIONS`: {"schema": 1, "receipts": [...]};
protected, rule-level; under league/, because the House box's release carries league/, ltcm/, playbooks/, scripts/
and deploy/ only (scripts/floor_box.py `UPLOAD_TREES`): a file under docs/ is never at hand there; `window_hours` is
`READ_AFTER_HOURS` when left out). `metric` is a dotted path into
`funnel.window(root, start, end)` that resolves to a number (`metric`).

THE READ (`step`, called by league/ops/stall.py `run`, which is read-only on the swarm store; the receipts live in
their own `<state>/release-receipts.sqlite`, 0600, table `l3_receipts`, append-only). `deployed_at` =
`funnel.release_start(base, <the running release's name>)` when the stall job first sees the id (that sighting's time
when the deploy record has none); the release's name is its directory's (`Path(release_dir).name`, as the scoreboard
names it). before = the metric over [deployed_at - w, deployed_at); after = over [deployed_at, deployed_at + w), read
once now >= deployed_at + w; sd = the sample sd of the metric over the four windows before `deployed_at`. Verdict
(`VERDICTS`): "moved" when (after - before) in the declared direction >= min_delta; "wrong_way" when <= -min_delta;
"flat" otherwise; "unreadable" when either is not a number. A receipt not read `UNREAD_GRACE_HOURS` after its window
closed is `unread` (alarm RR1); one read "flat" or "wrong_way" is alarm RR2 (league/ops/forward_report.py).

WHAT A ROW KEEPS. The "declared" row holds the declaration as it was first seen (release, metric, direction,
min_delta, window_hours), `deployed_at`, the metric BEFORE (`value`) and `sd`; the "read" row repeats them with the
metric AFTER (`value`) and the verdict. A receipt is read from its own declared row, so a later release that drops or
rewrites the declaration changes nothing of a receipt already declared (`UNIQUE (id, kind)`: one declaration and one
read an id, for ever). `sd` is None unless all four windows gave a number: it is description, never part of the
verdict.

NEVER RAISES (`step`): every failure is a string in its `errors` and the stall alarm goes on. A metric the funnel
cannot give (a path that names nothing, a number that is not finite) is None, never a zero: the verdict is then
"unreadable". THE FUNNEL'S OWN FAILURE IS NOT THE METRIC'S ANSWER: when the funnel reports a section it could not read
(its `errors`) and the metric is None, the receipt is asked again on the next pass (the stall job runs every half
hour) for `UNREAD_GRACE_HOURS`; only after them is it declared with no before, or read "unreadable", so a store
locked for one minute does not decide a receipt that is read once, for ever.

Standard library only.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

DB = "release-receipts.sqlite"
#: Where a release declares its receipts, relative to the release directory.
DECLARATIONS = "league/ops/release_receipts.json"
#: A declaration's default window in hours.
READ_AFTER_HOURS = 72
#: A receipt still unread this many hours after its window closed is `unread`.
UNREAD_GRACE_HOURS = 24
VERDICTS = ("moved", "flat", "wrong_way", "unreadable")
DIRECTIONS = ("up", "down")
#: `l3_receipts.kind`: `value` is the metric BEFORE on "declared" and AFTER on "read".
KINDS = ("declared", "read")
APPEND_ONLY_ERROR = "release-receipts.sqlite is append-only"
#: The declarations file's schema this code reads.
FILE_SCHEMA = 1
#: The windows before `deployed_at` the sample sd is taken over.
SD_WINDOWS = 4
#: An id, a release label and a metric path: short words, digits and `._:-` (a metric path's parts are joined by ".").
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,79}$")

#: The whole store (idempotent). Complete from step 0.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS l3_receipts (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('declared','read')), release TEXT NOT NULL, metric TEXT NOT NULL,
  direction TEXT NOT NULL, min_delta REAL NOT NULL, window_hours REAL NOT NULL, deployed_at REAL NOT NULL,
  value REAL, sd REAL, verdict TEXT, at REAL NOT NULL, UNIQUE (id, kind));
CREATE TRIGGER IF NOT EXISTS l3_receipts_no_update BEFORE UPDATE ON l3_receipts
  BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_ERROR}'); END;
CREATE TRIGGER IF NOT EXISTS l3_receipts_no_delete BEFORE DELETE ON l3_receipts
  BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_ERROR}'); END;
"""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _read(release_dir: str | Path | None) -> tuple[list[dict[str, Any]], list[str]]:
    """(the declarations kept, what was dropped and why) of a release directory's file."""
    if release_dir is None:
        return [], []
    path = Path(release_dir) / DECLARATIONS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], []
    except (OSError, ValueError) as exc:
        return [], [f"{DECLARATIONS} is unreadable ({type(exc).__name__})"]
    if not isinstance(doc, Mapping) or doc.get("schema") != FILE_SCHEMA or not isinstance(doc.get("receipts"), list):
        return [], [f"{DECLARATIONS} is not a schema {FILE_SCHEMA} receipts file"]
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(doc["receipts"]):
        name = str(entry.get("id"))[:80] if isinstance(entry, Mapping) and isinstance(entry.get("id"), str) else f"#{index}"
        why = None
        if not isinstance(entry, Mapping):
            why = "not an object"
        elif not all(isinstance(entry.get(k), str) and _NAME.match(entry[k]) for k in ("id", "release", "metric")):
            why = "its id, release or metric is not a short name"
        elif entry["id"] in seen:
            why = "its id is declared twice (the first stands)"
        elif entry.get("direction") not in DIRECTIONS:
            why = f"its direction is not one of {', '.join(DIRECTIONS)}"
        elif _number(entry.get("min_delta")) is None or _number(entry["min_delta"]) < 0:   # type: ignore[operator]
            why = "its min_delta is not a number at or above 0"
        elif "window_hours" in entry and not (_number(entry["window_hours"]) or 0.0) > 0.0:
            why = "its window_hours is not a number above 0"
        elif not isinstance(entry.get("why", ""), str):
            why = "its why is not text"
        if why is not None:
            dropped.append(f"declaration {name} dropped: {why}")
            continue
        seen.add(entry["id"])
        kept.append({"id": entry["id"], "release": entry["release"], "metric": entry["metric"],
                     "direction": entry["direction"], "min_delta": float(entry["min_delta"]),
                     "window_hours": float(entry.get("window_hours", READ_AFTER_HOURS)),
                     "why": str(entry.get("why", ""))})
    return kept, dropped


def declarations(release_dir: str | Path) -> list[dict[str, Any]]:
    """The declarations of `<release_dir>/league/ops/release_receipts.json`, each with its `window_hours`. A
    malformed entry is dropped and named (`step` lists it in its `errors` and never declares it). [] when the file is
    absent or unreadable."""
    return _read(release_dir)[0]


def metric(window: Mapping[str, Any], path: str) -> float | None:
    """The number at the dotted `path` of a `funnel.window` object (e.g. "forward_record.program_sessions"); None
    when the path does not resolve to a finite number (a bool is not a number)."""
    value: Any = window
    for part in str(path).split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return _number(value)


def verdict(before: float | None, after: float | None, direction: str, min_delta: float) -> str:
    """D17's verdict (`VERDICTS`) of one receipt."""
    if before is None or after is None or direction not in DIRECTIONS:
        return "unreadable"
    moved = (after - before) * (1.0 if direction == "up" else -1.0)
    if moved >= min_delta:
        return "moved"
    return "wrong_way" if moved <= -min_delta else "flat"


def _open(root: str | Path) -> sqlite3.Connection:
    """The receipts' store, writable: created 0600 with `SCHEMA`."""
    path = Path(root) / DB
    path.parent.mkdir(parents=True, exist_ok=True)
    os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
    os.chmod(path, 0o600)
    db = sqlite3.connect(str(path), timeout=5.0, isolation_level=None, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
    except sqlite3.Error:
        db.close()
        raise
    return db


def _sd(values: list[float | None]) -> float | None:
    """The sample sd (ddof 1) of the windows' values; None unless every one is a number."""
    if len(values) < 2 or any(v is None for v in values):
        return None
    mean = math.fsum(values) / len(values)                                  # type: ignore[arg-type]
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1))   # type: ignore[operator]


def step(root: str | Path, base: str | Path, release_dir: str | Path, *, now: float) -> dict[str, Any]:
    """D17, one pass (the module docstring): {"declared": [id] (declared in this pass), "read": [{"id", "verdict"}]
    (read in this pass), "unread": [id], "errors": [str]}. NEVER RAISES: the stall alarm goes on without it."""
    out: dict[str, Any] = {"declared": [], "read": [], "unread": [], "errors": []}
    try:
        from . import funnel

        now = float(now)
        grace = UNREAD_GRACE_HOURS * 3600.0
        kept, dropped = _read(release_dir)
        out["errors"].extend(dropped)
        if not kept and not (Path(root) / DB).exists():
            return out   # nothing declared and no receipt waiting: the store is not made for nothing
        windows: dict[tuple[float, float], Mapping[str, Any] | None] = {}

        def value(path: str, start: float, end: float) -> tuple[float | None, bool]:
            """(the metric over [start, end), whether a None is the funnel's own failure: a section it could not read)."""
            if (start, end) not in windows:
                try:
                    windows[(start, end)] = funnel.window(root, start, end)
                except Exception as exc:  # noqa: BLE001 - unread is never zero: the metric is None
                    windows[(start, end)] = None
                    out["errors"].append(f"the funnel could not be read ({type(exc).__name__})")
            found = windows[(start, end)]
            if found is None:
                return None, True
            number = metric(found, path)
            return number, number is None and bool(found.get("errors"))

        db = _open(root)
        try:
            known = {(r["id"], r["kind"]) for r in db.execute("SELECT id, kind FROM l3_receipts")}
            fresh = [d for d in kept if (d["id"], "declared") not in known]
            if fresh:
                on_record = funnel.release_start(base, Path(release_dir).name) if base is not None else None
                on_record = None if on_record is None or on_record > now else float(on_record)
                deployed = now if on_record is None else on_record
                for d in fresh:
                    w = d["window_hours"] * 3600.0
                    before = [value(d["metric"], deployed - (k + 1) * w, deployed - k * w) for k in range(SD_WINDOWS)]
                    if before[0][1] and on_record is not None and now < on_record + grace:
                        # The funnel could not read the window before the deploy: asked again on the next pass, for a
                        # day; after it the receipt is declared with no before (its verdict will be "unreadable").
                        out["errors"].append(f"receipt {d['id']} not declared yet: the funnel could not read its metric")
                        continue
                    done = db.execute(
                        "INSERT OR IGNORE INTO l3_receipts(id, kind, release, metric, direction, min_delta, "
                        "window_hours, deployed_at, value, sd, verdict, at) VALUES(?, 'declared', ?, ?, ?, ?, ?, ?, ?, "
                        "?, NULL, ?)", (d["id"], d["release"], d["metric"], d["direction"], d["min_delta"],
                                        d["window_hours"], deployed, before[0][0], _sd([b[0] for b in before]), now))
                    if done.rowcount:
                        out["declared"].append(d["id"])
            read = {r["id"] for r in db.execute("SELECT id FROM l3_receipts WHERE kind='read'")}
            for row in [dict(r) for r in db.execute("SELECT * FROM l3_receipts WHERE kind='declared' ORDER BY seq")]:
                closes = row["deployed_at"] + row["window_hours"] * 3600.0
                if row["id"] in read or now < closes:
                    continue
                late = now >= closes + grace
                try:
                    after, failed = value(row["metric"], row["deployed_at"], closes)
                    if failed and not late:
                        # The funnel's own failure, not the metric's answer: asked again on the next pass, for a day.
                        out["errors"].append(f"receipt {row['id']} not read yet: the funnel could not read its metric")
                        continue
                    said = verdict(row["value"], after, row["direction"], row["min_delta"])
                    db.execute("INSERT INTO l3_receipts(id, kind, release, metric, direction, min_delta, window_hours, "
                               "deployed_at, value, sd, verdict, at) VALUES(?, 'read', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (row["id"], row["release"], row["metric"], row["direction"], row["min_delta"],
                                row["window_hours"], row["deployed_at"], after, row["sd"], said, now))
                    out["read"].append({"id": row["id"], "verdict": said})
                except Exception as exc:  # noqa: BLE001 - this receipt stays unread; the others are still read
                    out["errors"].append(f"receipt {row['id']} could not be read ({type(exc).__name__})")
                    if late:
                        out["unread"].append(row["id"])
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - never the stall job's failure
        out["errors"].append(f"{type(exc).__name__}: {str(exc)[:160]}")
    return out


def rows(root: str | Path) -> list[dict[str, Any]]:
    """Every `l3_receipts` row in seq order (read-only; [] when the store is absent)."""
    from . import guard

    path = Path(root) / DB
    if not path.exists():
        return []

    def read(db: sqlite3.Connection) -> list[dict[str, Any]]:
        if not guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table' AND name='l3_receipts'"):
            return []
        return guard.rows(db, "SELECT * FROM l3_receipts ORDER BY seq")

    return guard.read(path, read)


def summary(root: str | Path, *, now: float) -> list[dict[str, Any]]:
    """One object a receipt for the forward report (league/ops/forward_report.py: its `receipts` section and the alarms
    RR1 and RR2): {"id", "release", "metric", "direction", "min_delta", "window_hours", "deployed_at", "declared_at",
    "closes_at", "before", "sd", "after", "verdict", "read_at", "unread"}; `unread` is True for a receipt with no read
    `UNREAD_GRACE_HOURS` after its window closed. Raises what `rows` raises (an unreadable store)."""
    out: dict[str, dict[str, Any]] = {}
    found = rows(root)
    for row in found:
        if row["kind"] == "declared":
            closes = float(row["deployed_at"]) + float(row["window_hours"]) * 3600.0
            out[row["id"]] = {"id": row["id"], "release": row["release"], "metric": row["metric"],
                              "direction": row["direction"], "min_delta": row["min_delta"],
                              "window_hours": row["window_hours"], "deployed_at": row["deployed_at"],
                              "declared_at": row["at"], "closes_at": closes, "before": row["value"], "sd": row["sd"],
                              "after": None, "verdict": None, "read_at": None,
                              "unread": float(now) >= closes + UNREAD_GRACE_HOURS * 3600.0}
    for row in found:
        if row["kind"] == "read" and row["id"] in out:
            out[row["id"]].update(after=row["value"], verdict=row["verdict"], read_at=row["at"], unread=False)
    return list(out.values())


__all__ = ["DB", "DECLARATIONS", "READ_AFTER_HOURS", "UNREAD_GRACE_HOURS", "VERDICTS", "DIRECTIONS", "KINDS", "SCHEMA",
           "APPEND_ONLY_ERROR", "declarations", "metric", "step", "rows", "verdict", "summary"]
