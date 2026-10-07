"""The research funnel (the owner's goal of Oct 7, 2026, items 3 and 6): what the swarm's own records say happened in a
window of time, read read-only, for the daily page's Funnel table (`league/ops/scoreboard.py`) and the stall alarm
(`league/ops/stall.py`).

Each count comes from the record that is the event itself, never from a summary another job wrote:

- births: the swarm's `swarm.born` events (every birth: the founders, the architect's, a reseed, a fork);
- versions: the program versions the researchers wrote (`versions.created_at`);
- Gym runs: the `runs` rows by window (`train`, `validation`, `holdout`, `forward`, `probe`, `mechanism`), counted as
  run when the Gym evaluated the program (status not `refused` or `error`; those are counted apart as `not_run`). A
  validation is two rows (its 1.5x stress twin is a second trial);
- validations judged and passed: the tournament rounds' verdicts (`swarm.tournament` events, `validation.judged`), a
  verdict read from an identical program's validation included (F1: no Gym run);
- looks and passes: the `looks` table (the holdout ration);
- band moves to Candidate, Probe and Sized: `swarm.band` events; the bands now: the living families' `band`;
- research spend by meter: the `spend` table (Sail: `sail_model` and `gym_box`; Claude: `claude`; OpenAI apart, closed);
- braked hours: the Sail guard's `swarm.guard` brake and release events, each brake's hours given to the causes it
  named when it began (`guard_hours`);
- real orders and closes by route: the live book (`live.sqlite`: orders by `placed_at`, positions by `closed_at`), each
  routed as the close economics routes it (`economics.route_of`): the House's routes (calibration, the House's live
  test, another House family) against the agents' (the incubator, tuition, D2 Probe/Sized, another agent route).

READ-ONLY: every SQLite open is `mode=ro` (`guard.read`); each section that cannot be read is an `errors` entry and its
counts None, never a zero. Standard library only.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping

from . import guard
from . import schedule as S

SWARM_DB = "swarm.sqlite"
LIVE_DB = "live.sqlite"
WINDOWS = ("train", "validation", "holdout", "forward", "probe", "mechanism")
#: A `runs` row with one of these statuses is not a Gym evaluation (the Gym refused the program, or failed).
NOT_RUN = ("refused", "error")
BANDS = ("candidate", "probe", "sized")
METER_KINDS = {"sail": ("sail_model", "gym_box"), "claude": ("claude",), "openai": ("openai",)}
HOUSE_ROUTES = ("calibration", "house_test", "house_other")
AGENT_ROUTES = ("incubator", "tuition", "d2_real", "agent_other")


def _count(db: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    value = guard.ids(db, sql, params)
    return int(value[0] or 0) if value else 0


def _json_rows(db: sqlite3.Connection, kind: str, path: str, start: str, end: str) -> list[Any]:
    """The value at JSON `path` of every `kind` event in `[start, end)`, parsed. SQLite's JSON1 reads it in place (a
    tournament's payload carries its whole board); without JSON1 the payloads are read and parsed one by one."""
    try:
        raw = guard.ids(db, f"SELECT json_extract(payload, '{path}') FROM events WHERE kind=? AND at>=? AND at<? ORDER BY seq",
                        (kind, start, end))
    except sqlite3.OperationalError:
        out = []
        for text in guard.ids(db, "SELECT payload FROM events WHERE kind=? AND at>=? AND at<? ORDER BY seq", (kind, start, end)):
            try:
                value: Any = json.loads(text)
            except (TypeError, ValueError):
                continue
            for part in path.lstrip("$.").split("."):
                value = value.get(part) if isinstance(value, Mapping) else None
            out.append(value)
        return out
    parsed = []
    for value in raw:
        if isinstance(value, str) and value[:1] in "{[":
            try:
                value = json.loads(value)
            except ValueError:
                pass
        parsed.append(value)
    return parsed


def swarm_counts(db: sqlite3.Connection, start: float, end: float) -> dict[str, Any]:
    """The swarm store's counts in `[start, end)` (one read transaction: `guard.read`)."""
    a, b = S.iso(start), S.iso(end)
    out: dict[str, Any] = {}
    out["births"] = _count(db, "SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=? AND at<?", (a, b))
    out["versions"] = _count(db, "SELECT count(*) FROM versions WHERE created_at>=? AND created_at<?", (a, b))
    runs = {w: 0 for w in WINDOWS}
    other = not_run = 0
    for row in guard.rows(db, 'SELECT "window" AS w, status, count(*) AS n FROM runs WHERE at>=? AND at<? '
                              'GROUP BY "window", status', (a, b)):
        n = int(row["n"] or 0)
        if row["status"] in NOT_RUN:
            not_run += n
        elif row["w"] in runs:
            runs[row["w"]] += n
        else:
            other += n
    out["gym_runs"] = {**runs, "other": other}
    out["gym_runs_total"] = sum(runs.values()) + other
    out["gym_not_run"] = not_run
    judged = passed = 0
    for verdicts in _json_rows(db, "swarm.tournament", "$.validation.judged", a, b):
        if isinstance(verdicts, Mapping):
            for verdict in verdicts.values():
                judged += 1
                passed += 1 if isinstance(verdict, Mapping) and verdict.get("passed") is True else 0
    out["validations"] = {"judged": judged, "passed": passed}
    looks = guard.rows(db, "SELECT count(*) AS n, coalesce(sum(passed), 0) AS passed FROM looks WHERE at>=? AND at<?", (a, b))
    out["looks"] = {"taken": int(looks[0]["n"] or 0), "passed": int(looks[0]["passed"] or 0)}
    moves = {band: 0 for band in BANDS}
    for to in _json_rows(db, "swarm.band", "$.band_to", a, b):
        if to in moves:
            moves[to] += 1
    out["band_moves"] = moves
    spend = {meter: 0.0 for meter in METER_KINDS}
    for row in guard.rows(db, "SELECT kind, coalesce(sum(usd), 0) AS usd FROM spend WHERE epoch>=? AND epoch<? GROUP BY kind",
                          (float(start), float(end))):
        for meter, kinds in METER_KINDS.items():
            if row["kind"] in kinds:
                spend[meter] += float(row["usd"] or 0.0)
    out["spend_usd"] = {meter: round(usd, 2) for meter, usd in spend.items()}
    return out


def bands_now(db: sqlite3.Connection) -> dict[str, int]:
    """The living families by band, and `alive` (every living family)."""
    out = {band: 0 for band in ("gym", *BANDS)}
    for row in guard.rows(db, "SELECT band, count(*) AS n FROM families WHERE retired_at IS NULL GROUP BY band"):
        out[str(row["band"])] = out.get(str(row["band"]), 0) + int(row["n"] or 0)
    out["alive"] = sum(out.values())
    return out


def guard_hours(db: sqlite3.Connection, start: float, end: float) -> dict[str, Any]:
    """The hours the Sail guard was braked in `[start, end)`, from its brake and release events (the guard writes one at
    each change, and one at its first check). Each braked stretch is given to the causes its brake event named
    (`unknown` for a brake that named none). `known` is False when no event before `end` says what the guard was."""
    a, b = S.iso(start), S.iso(end)

    def parse(rows: list[dict[str, Any]]) -> list[tuple[float, str, list[str]]]:
        out = []
        for row in rows:
            at = S.epoch(row["at"])
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                continue
            action = payload.get("action") if isinstance(payload, Mapping) else None
            if at is None or action not in ("brake", "release"):
                continue
            causes = payload.get("causes")
            causes = [str(c) for c in causes] if isinstance(causes, list) and causes else ["unknown"]
            out.append((at, action, causes))
        return out

    # The guard's hold events (research_hold/research_release) share the kind: read back far enough to find a change.
    before = parse(guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.guard' AND at<? ORDER BY seq DESC LIMIT 50",
                              (a,)))
    inside = parse(guard.rows(db, "SELECT at, payload FROM events WHERE kind='swarm.guard' AND at>=? AND at<? ORDER BY seq",
                              (a, b)))
    braked, causes = (before[0][1] == "brake", before[0][2]) if before else (False, ["unknown"])
    known = bool(before) or bool(inside)
    t, seconds, by_cause, since = float(start), 0.0, {}, (float(start) if braked else None)

    def add(until: float) -> None:
        nonlocal seconds
        span = max(0.0, until - t)
        seconds += span
        for cause in causes:
            by_cause[cause] = by_cause.get(cause, 0.0) + span

    for at, action, named in inside:
        if braked:
            add(at)
        if action == "brake" and not braked:
            since = at
        braked, causes, t = action == "brake", named if action == "brake" else causes, at
        if not braked:
            since = None
    if braked:
        add(float(end))
    return {"hours": round(seconds / 3600.0, 2), "by_cause": {c: round(s / 3600.0, 2) for c, s in sorted(by_cause.items())},
            "braked_now": braked, "braked_since": None if since is None else S.iso(since),
            "causes_now": list(causes) if braked else [], "known": known}


def book_counts(root: str | Path, start: float, end: float) -> dict[str, Any]:
    """Real orders placed (and of them filled) and real positions closed in `[start, end)`, by route: the House's
    routes against the agents' (`HOUSE_ROUTES`, `AGENT_ROUTES`). An absent book is an empty one (nothing traded)."""
    from .economics import route_of

    path = Path(root) / LIVE_DB
    out = {"orders": {"agent": 0, "house": 0}, "filled": {"agent": 0, "house": 0}, "closes": {"agent": 0, "house": 0}}
    if not path.exists():
        return out

    def read(db: sqlite3.Connection) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        orders = guard.rows(db, "SELECT family, instance, tuition, filled_qty FROM orders WHERE placed_at>=? AND placed_at<?",
                            (float(start), float(end))) if "orders" in tables else []
        closes = guard.rows(db, "SELECT family, instance, tuition FROM positions WHERE status!='open' AND closed_at IS NOT NULL "
                                "AND closed_at>=? AND closed_at<?", (float(start), float(end))) if "positions" in tables else []
        return orders, closes

    orders, closes = guard.read(path, read)
    side = lambda row: "house" if route_of(row) in HOUSE_ROUTES else "agent"  # noqa: E731
    for row in orders:
        out["orders"][side(row)] += 1
        if int(row.get("filled_qty") or 0) > 0:
            out["filled"][side(row)] += 1
    for row in closes:
        out["closes"][side(row)] += 1
    return out


def release_start(base: str | Path, release: str) -> float | None:
    """When the running release `release` began: its latest `promoted` verdict in `<base>/deploys.jsonl`; None when the
    record has none (a release deployed before the record, or one whose record cannot be read)."""
    latest = None
    try:
        with (Path(base) / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if '"promoted"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("stage") == "verdict" and row.get("verdict") == "promoted" and row.get("release") == release:
                    at = S.epoch(row.get("at"))
                    if at is not None and (latest is None or at > latest):
                        latest = at
    except OSError:
        return None
    return latest


def window(root: str | Path, start: float, end: float) -> dict[str, Any]:
    """Every count of the funnel in `[start, end)`; a section that cannot be read is in `errors` and absent."""
    root = Path(root)
    out: dict[str, Any] = {"from": S.iso(start), "to": S.iso(end), "errors": {}}
    try:
        out.update(guard.read(root / SWARM_DB, lambda db: {**swarm_counts(db, start, end),
                                                           "braked": guard_hours(db, start, end)}))
    except Exception as exc:  # noqa: BLE001 - unread is never zero
        out["errors"]["swarm"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        out["book"] = book_counts(root, start, end)
    except Exception as exc:  # noqa: BLE001
        out["errors"]["book"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


def read(root: str | Path, base: str | Path, release: str, now: float) -> dict[str, Any]:
    """The funnel for the daily page: the last 24 hours, since the running release began (None when its start is not
    on record), and the bands now."""
    since = release_start(base, release)
    out: dict[str, Any] = {"day": window(root, now - 86400.0, now), "since": None if since is None else S.iso(since),
                           "release": window(root, since, now) if since is not None and since < now else None}
    try:
        out["bands_now"] = guard.read(Path(root) / SWARM_DB, bands_now)
    except Exception as exc:  # noqa: BLE001
        out["bands_now"] = None
        out["day"]["errors"]["bands_now"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out


__all__ = ["swarm_counts", "bands_now", "guard_hours", "book_counts", "release_start", "window", "read", "WINDOWS",
           "NOT_RUN", "BANDS", "METER_KINDS", "HOUSE_ROUTES", "AGENT_ROUTES", "SWARM_DB", "LIVE_DB"]
