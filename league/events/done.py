"""THE DONE READER OF THE GOAL OF OCT 19, 2026 (V2): every 100 settled real-money events at Probe size or above.

The rule is docs/goals/DONE-RULE-EVL-2.md, pinned here by its sha256 (`RULE_SHA256`; league/tests/test_events_done.py
fails while the file and the constant differ). This module reads it; it never changes it.

- `counted(store)`: the lane's settled real-money events of every seating program version, split into the COUNTED
  Probe+ events (the buy's band probe or sized, bought after the program's PROMOTION: its EARLIEST move to probe,
  `promoted_at`, so a demotion and a return to Probe never drop the stay that was demoted: A84), the
  `before_promotion` ones (a GUARD: a Probe+ buy with no promotion on record, before it, or with no readable time; one
  inside a checkpoint's span fails its item 4.3) and the `learning` ones; every row enriched with the shadow's
  benchmark return `b` (outcomes) and the fill gap per side against the shadow's auction prices.
- `figures(rows)`: n, by program, P&L, mean r, the 95% issuer-block lower bound (rule item 4.5), benchmark-net a beside,
  the fill gaps (item 4.7).
- `captain_steps(root, start, end)`: rule item 4.8 from the House's records (the operator files' before-copies and
  change times, the pause files, the stall job's runs in ops.sqlite, the deploy record): `fail` when a step shows,
  else `unverifiable` (never a pass: the House keeps no record of every operator channel; A84), so Done at a checkpoint
  needs the captain's attestation (`attested`).
- `read(...)`: the whole reading, PURE over what it is given (the store, the state root, the ledger, the loss figures,
  the checkpoint history, the attestations): every figure, the current reading, the new checkpoints (100, 200, ...;
  each over exactly the first c events), each item pass or fail with its number, the pivot and the $800 stop. It opens
  nothing for writing.
- `run(store, now=...)`: the House's nightly call (league/events/house.py `_screen`, after the band review): the
  history (`history`: done.json, the append-only `done-history.jsonl` and the `done` receipts; `Unreadable` when a
  record exists that cannot be read, and then nothing is written), `read`, each new checkpoint appended to
  done-history.jsonl and done.json written again (a written checkpoint is never rewritten). `receipt(doc)`: the `done`
  receipt's summary (figures only).

Standard library only. Nothing here sends an order, moves a band or changes a setting.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import bands as BA
from . import calendar as C
from . import programs as P
from . import screen as SC
from . import store as S

RULE_FILE = "docs/goals/DONE-RULE-EVL-2.md"
#: sha256 of docs/goals/DONE-RULE-EVL-2.md (the pinned rule; a change is a new rule and a new constant).
RULE_SHA256 = "8eb743e58213d7e32c74c6e0b40e63d74b5d884d7ba7e267a39cfed540f44df3"
SCHEMA = 1
FILE = "done.json"
JOB = "done"
LANE = "event"

EVERY = 100                 # a checkpoint at every 100th Probe+ event
DONE_EVENTS = 300
DONE_PROGRAMS = 3
DONE_PER_PROGRAM = 50
LEVEL = 0.95
DRAWS = 10_000
SEED_DONE = "DONE-RULE-EVL-2|done|issuer"
SEED_A = "DONE-RULE-EVL-2|done-a|issuer"
SEED_PIVOT = "DONE-RULE-EVL-2|pivot|issuer"
FILL_BP = 15.0
QUIET_LAST = 100
PIVOT_AT = 400
LOSS_TOTAL_USD = 800.0
#: The stall causes that are news, not an owner step (league/ops/dlane_report.py NEWS_CAUSES).
NEWS_CAUSES = ("done",)
OPS_DB = "ops.sqlite"
#: The checkpoints' append-only record beside done.json (rule items 3 and 8; A84): one JSON line per checkpoint, as written.
HISTORY = "done-history.jsonl"
#: The captain's attestations of item 4.8 (rule item 4.8; A84): one JSON line each, appended after a checkpoint's span.
ATTEST = "done-attest.jsonl"
#: The watchdog's append-only deploy record, in the state root's parent (league/live_trading.py `owner_change`).
DEPLOYS = "deploys.jsonl"
RELEASE_CHANGES = ("promote", "rollback")
#: An operator tool's before-copy is any name in the state root with `.before` in it (`<file>.before-<what>-<stamp>`,
#: or unstamped: `swarm.json.before-train2020` is on the House); its stamp, when it has one, is a moment of the copy.
BEFORE = ".before"
STAMP = re.compile(r"(\d{8}T\d{6}Z)$")
#: The files an operator writes by hand (the House only reads them), each read by its change times: swarm.json and
#: ops.json (an edit with no before-copy), PAUSE and swarm.stop (a pause; league/ops/stall.py PAUSE_FILES).
WATCHED = ("swarm.json", "ops.json", "PAUSE", "swarm.stop")
#: item 4.8's three readings: a step is on the House's records (fail); none is, but the records do not cover every
#: operator channel (unverifiable: the captain's attestation decides); the item's events are not there yet (short).
FAIL, UNVERIFIABLE, SHORT = "fail", "unverifiable", "short"
#: What the House's records cannot see (rule item 4.8): why item 4.8 is never a pass from them alone.
UNSEEN = ("the House keeps no record of every operator channel (a Sail exec such as boxrun, floor_box, the ship "
          "scripts, the gateway's admin), of a pause or kill-switch flip between two stall runs, or of a hand write to "
          "sqlite, kv or the bands: the captain's attestation over this span decides (rule item 4.8)")
ITEMS = ("events", "programs", "after_promotion", "pnl", "bound", "profit_vs_compute", "fills", "no_captain")
UTC = dt.timezone.utc


class Unreadable(RuntimeError):
    """A Done record exists that cannot be read (done.json, done-history.jsonl, a `done` receipt), or a checkpoint a
    record names is in no history: the reader writes nothing (a checkpoint is never written again: rule item 3) and
    the House's hook warns."""


def rule_sha256(repo: str | os.PathLike[str] | None = None) -> str:
    """The sha256 of the rule file in a tree (this module's own by default)."""
    base = Path(repo) if repo is not None else Path(__file__).resolve().parents[2]
    return hashlib.sha256((base / RULE_FILE).read_bytes()).hexdigest()


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, places: int = 2) -> float | None:
    number = _num(value)
    return None if number is None else round(number, places)


def _parse(text: Any) -> dt.datetime | None:
    try:
        return S.parse_iso(str(text))
    except (TypeError, ValueError):
        return None


def _has_table(store: Any, name: str) -> bool:
    return store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


# ------------------------------------------------------------------------------------------------ the events
def _ratio(store: Any, symbol: str, day: str) -> float:
    """Alpaca's adjusted / raw daily close of `day` (1.0 when either bar is missing): league/events/score.py `_ratio`."""
    closes = {}
    for adj in ("raw", "all"):
        row = store.db.execute("SELECT c FROM bars WHERE symbol=? AND day=? AND adj=?", (symbol, day, adj)).fetchone()
        value = None if row is None else _num(row[0])
        closes[adj] = value if value is not None and value > 0 else None
    return closes["all"] / closes["raw"] if closes["raw"] and closes["all"] else 1.0


def _enrich(store: Any, program: str, version: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each event with its program, version, the shadow's benchmark return `b`, `a` = r - b, and its fill gaps per side
    (`entry_gap_bp`, `exit_gap_bp`; rule item 4.7) against the shadow's auction prices made raw again."""
    if not rows:
        return []
    exits = SC.exit_overrides(store, program, version)
    out = []
    for row in rows:
        event = str(row["event"])
        e = dict(row, program=program, version=int(version), b=None, a=None, entry_gap_bp=None, exit_gap_bp=None)
        o = store.db.execute("SELECT entry_px, exit_px, b FROM outcomes WHERE program=? AND version=? AND event=? AND "
                             "status='settled'", (program, int(version), event)).fetchone()
        i = store.db.execute("SELECT symbol, entry_day, exit_day FROM intents WHERE program=? AND version=? AND event=?",
                             (program, int(version), event)).fetchone()
        fills = {str(f["side"]): f for f in store.db.execute(
            "SELECT side, price FROM real_fills WHERE program=? AND version=? AND event=?", (program, int(version), event))}
        if o is not None:
            b = _num(o["b"])
            if b is not None:
                e["b"], e["a"] = b, float(row["r"]) - b
            if i is not None:
                symbol = str(i["symbol"])
                shadow_in = _num(o["entry_px"])
                if shadow_in and shadow_in > 0 and "buy" in fills and _num(fills["buy"]["price"]):
                    raw_in = shadow_in / _ratio(store, symbol, str(i["entry_day"]))
                    e["entry_gap_bp"] = (float(fills["buy"]["price"]) / raw_in - 1.0) * 1e4
                shadow_out = _num(o["exit_px"])
                exit_day = exits.get(event)
                exit_day = exit_day.isoformat() if exit_day is not None else str(i["exit_day"])
                if shadow_out and shadow_out > 0 and "sell" in fills and _num(fills["sell"]["price"]):
                    raw_out = shadow_out / _ratio(store, symbol, exit_day)
                    e["exit_gap_bp"] = (1.0 - float(fills["sell"]["price"]) / raw_out) * 1e4
        out.append(e)
    return out


def _order(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    return (str(row["sold_at"]), str(row["program"]), int(row["version"]), str(row["event"]))


def promoted_at(store: Any, program: str, version: int) -> dt.datetime | None:
    """Rule item 1: (program, version)'s PROMOTION, its EARLIEST move to probe in `band_history`, at the later of the
    move's `since` and its `written_at`; None when it never moved there. A demotion and a return to Probe never move it
    (A84: the current stay alone would drop the stay a demotion ended, losers by construction)."""
    if not _has_table(store, "band_history"):
        return None
    moments = []
    for row in store.db.execute("SELECT since, written_at FROM band_history WHERE program=? AND version=? AND "
                                "band='probe'", (program, int(version))):
        times = [t for t in (_parse(row["since"]), _parse(row["written_at"])) if t is not None]
        if times:
            moments.append(max(times))
    return min(moments) if moments else None


def counted(store: Any) -> dict[str, Any]:
    """The lane's settled real-money events (rule items 1 and 5): {counted, before_promotion, learning: [rows], promoted:
    {(program, version): its promotion (`promoted_at`), or None}}, each list in the count's order (the sale's time,
    program, version, event). COUNTED: every Probe+ buy after the program's promotion, whatever its stays since;
    BEFORE_PROMOTION, the guard: a Probe+ buy with no promotion on record, not after it, or with no readable time.
    Read-only."""
    out: dict[str, Any] = {"counted": [], "before_promotion": [], "learning": [], "promoted": {}}
    if not _has_table(store, "real_fills"):
        return out   # a store from before release 1019b: no real fill
    for prog in P.SEATING:
        key = (prog.id, prog.version)
        rows = _enrich(store, prog.id, prog.version,
                       BA.real_events(store, prog.id, prog.version, at=("learning",) + BA.PROBE_PLUS))
        since = promoted_at(store, prog.id, prog.version)
        out["promoted"][key] = since
        for row in rows:
            if row["band"] not in BA.PROBE_PLUS:
                out["learning"].append(row)
                continue
            bought = _parse(row.get("bought_at"))
            if since is not None and bought is not None and bought > since:
                out["counted"].append(row)
            else:
                out["before_promotion"].append(row)
    for name in ("counted", "before_promotion", "learning"):
        out[name].sort(key=_order)
    return out


def first_promotion(store: Any) -> dt.datetime | None:
    """Rule item 4.6: the earliest move to probe in `band_history` (any seating version), at the later of its `since`
    and `written_at`; None before any."""
    moments = [m for m in (promoted_at(store, p.id, p.version) for p in P.SEATING) if m is not None]
    return min(moments) if moments else None


# ------------------------------------------------------------------------------------------------ the figures
def _bound(rows: Sequence[Mapping[str, Any]], seed_text: str, *, value: str = "r", sided: str = "two") -> dict[str, Any] | None:
    use = [r for r in rows if _num(r.get(value)) is not None]
    if not use:
        return None
    out = SC.bootstrap_bounds(use, "issuer", LEVEL, DRAWS, SC.seed_of(seed_text), sided=sided, value=value)
    return {"seed": seed_text, "sided": sided, "issuers": out["groups"], "n": out["events"], "mean": out["mean"],
            "lower": out["lower"], "upper": out["upper"]}


def _gaps(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for side in ("entry", "exit"):
        values = [v for v in (_num(r.get(f"{side}_gap_bp")) for r in rows) if v is not None]
        out[f"{side}_n"] = len(values)
        out[f"{side}_mean_bp"] = None if not values else math.fsum(values) / len(values)
    return out


def _by_program(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for r in rows:
        cell = out.setdefault((str(r["program"]), int(r["version"])), {"n": 0, "pnl": 0.0})
        cell["n"] += 1
        cell["pnl"] += float(r["pnl"])
    return out


def figures(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every figure of a set of Probe+ events (rule items 4.1-4.5, 4.7 and 5)."""
    progs = _by_program(rows)
    bound, a_bound = _bound(rows, SEED_DONE), _bound(rows, SEED_A, value="a")
    a_values = [float(r["a"]) for r in rows if _num(r.get("a")) is not None]
    return {
        "n": len(rows), "issuers": len({str(r["issuer"]) for r in rows}),
        "programs": [{"id": k[0], "version": k[1], "n": v["n"], "pnl_usd": round(v["pnl"], 2)}
                     for k, v in sorted(progs.items(), key=lambda kv: (-kv[1]["n"], kv[0]))],
        "pnl_usd": round(math.fsum(float(r["pnl"]) for r in rows), 2),
        "mean_r": None if not rows else math.fsum(float(r["r"]) for r in rows) / len(rows),
        "bound": bound,
        "a": {"n": len(a_values), "mean": None if not a_values else math.fsum(a_values) / len(a_values),
              "bound": a_bound},
        "fills": _gaps(rows),
        "first_sold_at": rows[0]["sold_at"] if rows else None, "last_sold_at": rows[-1]["sold_at"] if rows else None,
    }


def _pnl(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    return {"n": len(rows), "pnl_usd": round(math.fsum(float(r["pnl"]) for r in rows), 2)}


# ------------------------------------------------------------------------------------------------ the captain
def _stamp(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _moments(path: Path) -> list[dt.datetime] | None:
    """A file's change times: its modification time and its status-change time (ctime: a copy's own making, which a
    copy that keeps the original's mtime and a later `touch` cannot move back); None when it cannot be read."""
    try:
        st = path.stat()
    except OSError:
        return None
    return [dt.datetime.fromtimestamp(t, UTC) for t in (st.st_mtime, st.st_ctime)]


def operator_edits(root: str | os.PathLike[str], start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
    """Rule item 4.8's operator files changed at or after `start`: every before-copy in the state root (any name with
    `.before` in it, by its stamp when it has one and its change times) and the WATCHED files (by their change times),
    [{file, what, at, in_span}], oldest first. `in_span`: a moment in [start, end] (an edit: a step); else a change
    after `end`, which can hide an edit in the span (a later write or touch moves both times)."""
    out = []
    root = Path(root)
    try:
        names = sorted(p.name for p in root.iterdir())
    except OSError:
        names = []
    files = [(n, n[:n.index(BEFORE)], n[n.index(BEFORE) + len(BEFORE):].strip("-") or None) for n in names if BEFORE in n]
    files += [(n, n, "changed") for n in WATCHED if n in names]
    for name, of, what in files:
        moments = _moments(root / name)
        if moments is None:
            continue
        stamp = STAMP.search(name)
        if stamp:
            try:
                moments.append(_stamp(stamp.group(1)))
            except ValueError:
                pass
        inside = sorted(m for m in moments if start <= m <= end)
        after = sorted(m for m in moments if m > end)
        if inside or after:
            out.append({"file": of, "name": name, "what": what, "at": S.iso((inside or after)[0]), "in_span": bool(inside)})
    return sorted(out, key=lambda e: (e["at"], e["name"]))


def _stall_runs(root: Path, start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]] | None:
    """The `ok` stall runs of ops.sqlite due in [start, end] (read-only); None when they cannot be read."""
    from ..ops import guard

    path = root / OPS_DB
    if not path.exists():
        return None
    try:
        return guard.read(path, lambda db: [dict(r) for r in db.execute(
            "SELECT due_at, summary_json FROM runs WHERE job='stall' AND status='ok' AND due_at>=? AND due_at<=? "
            "ORDER BY due_at", (S.iso(start), S.iso(end)))])
    except Exception:  # noqa: BLE001 - unreadable receipts: nobody is seen to have looked
        return None


def owner_deploys(base: str | os.PathLike[str], start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """The owner's release changes in [start, end] on the watchdog's record (`<base>/deploys.jsonl`): a promotion or
    rollback that succeeded with no updater `sha` or `attestation` and is no drill's (league/live_trading.py
    `owner_change`). {rows: [{at, stage, release}], why: None or why the record could not be read whole}."""
    path = Path(base) / DEPLOYS
    rows: list[Mapping[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    return {"rows": [], "why": f"{DEPLOYS} has a line that cannot be read"}
                if isinstance(row, Mapping):
                    rows.append(row)
    except OSError:
        return {"rows": [], "why": f"{DEPLOYS} could not be read"}
    drills = {str(r.get("deploy")) for r in rows if r.get("stage") == "drill" and r.get("deploy")}
    out = []
    for row in rows:
        if row.get("stage") not in RELEASE_CHANGES or row.get("ok") is not True:
            continue
        if row.get("sha") or row.get("attestation") or str(row.get("deploy")) in drills:
            continue
        if any(str(row.get(k) or "").startswith("drill-") for k in ("release", "current", "from")):
            continue
        at = _parse(row.get("at"))
        if at is None and isinstance(row.get("ts"), (int, float)) and not isinstance(row.get("ts"), bool):
            at = dt.datetime.fromtimestamp(float(row["ts"]), UTC)
        if at is not None and start <= at <= end:
            out.append({"at": S.iso(at), "stage": row.get("stage"),
                        "release": row.get("current") or row.get("to") or row.get("release")})
    return {"rows": out, "why": None}


def _check_steps(checks: Mapping[str, Any]) -> list[str]:
    """A stall run's captain steps: every stalled check that names an owner step (but the news causes), and a pause or
    the kill switch it found standing however briefly (league/ops/stall.py `paused` and `kill_on`'s numbers)."""
    causes = {str(c) for c, chk in checks.items() if isinstance(chk, Mapping) and chk.get("stalled")
              and chk.get("owner_step") and c not in NEWS_CAUSES}
    paused = (checks.get("paused") or {}).get("numbers") if isinstance(checks.get("paused"), Mapping) else None
    if isinstance(paused, Mapping) and (paused.get("maintenance_pause") is True or paused.get("swarm_stopped") is True):
        causes.add("paused")
    kill = (checks.get("kill_on") or {}).get("numbers") if isinstance(checks.get("kill_on"), Mapping) else None
    if isinstance(kill, Mapping) and kill.get("kill_switch") is True:
        causes.add("kill_on")
    return sorted(causes)


def captain_steps(root: str | os.PathLike[str] | None, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """Rule item 4.8 over [start, end]: {status, holds, why, from, to, edits, later, owner (the stall runs with a step:
    {at, causes}), deploys (the owner's, beside: the attestation counts their hand steps), stall_runs, unlooked (the
    UTC days with no ok stall run)}. `status` is FAIL when the House's records show a step or cannot be read, else
    UNVERIFIABLE (A84): the records do not cover every operator channel, so `holds` is never True from them alone."""
    out: dict[str, Any] = {"from": S.iso(start), "to": S.iso(end), "edits": [], "later": [], "owner": [], "deploys": [],
                           "stall_runs": 0, "unlooked": [], "status": FAIL, "holds": False, "why": None}
    if root is None:
        return {**out, "why": "the House's records were not read"}
    root = Path(root)
    changed = operator_edits(root, start, end)
    out["edits"] = [e for e in changed if e["in_span"]]
    out["later"] = [e for e in changed if not e["in_span"]]
    deploys = owner_deploys(root.parent, start, end)
    out["deploys"] = deploys["rows"]
    # The whole UTC days the span touches: a stall run of the span's first or last day is that day's look, and an owner
    # step it found waiting is counted (the reading less likely to pass).
    runs = _stall_runs(root, dt.datetime.combine(start.date(), dt.time(0), UTC),
                       dt.datetime.combine(end.date() + dt.timedelta(days=1), dt.time(0), UTC) - dt.timedelta(seconds=1))
    if runs is None:
        return {**out, "why": "the stall job's runs (ops.sqlite) could not be read"}
    looked = set()
    for run in runs:
        looked.add(str(run.get("due_at") or "")[:10])
        try:
            checks = (json.loads(run.get("summary_json") or "{}") or {}).get("checks") or {}
        except (TypeError, ValueError, AttributeError):
            checks = {}
        causes = _check_steps(checks) if isinstance(checks, Mapping) else []
        if causes:
            out["owner"].append({"at": str(run.get("due_at")), "causes": causes})
    out["stall_runs"] = len(runs)
    day = start.date()
    while day <= end.date():
        if day.isoformat() not in looked:
            out["unlooked"].append(day.isoformat())
        day += dt.timedelta(days=1)
    whys = []
    if out["edits"]:
        whys.append(f"{len(out['edits'])} operator edit(s), the first {out['edits'][0]['name']} at {out['edits'][0]['at']}")
    if out["owner"]:
        whys.append(f"a captain step at {len(out['owner'])} stall run(s) ({', '.join(out['owner'][0]['causes'])})")
    if out["unlooked"]:
        whys.append(f"no stall run on {len(out['unlooked'])} UTC day(s), the first {out['unlooked'][0]}")
    if not whys:
        notes = [UNSEEN]
        if out["later"]:
            notes.append(f"{len(out['later'])} operator file(s) changed after the span, which can hide an edit in it "
                         f"(the first {out['later'][0]['name']} at {out['later'][0]['at']})")
        if out["deploys"]:
            notes.append(f"{len(out['deploys'])} owner deploy(s) in the span, the first at {out['deploys'][0]['at']}: "
                         "the attestation counts their hand steps")
        if deploys["why"]:
            notes.append(deploys["why"])
        out.update(status=UNVERIFIABLE, why="no captain step on the House's records, but " + "; ".join(notes))
    else:
        out["why"] = "; ".join(whys)
    return {**out, "holds": False, "edits": out["edits"][-40:], "later": out["later"][-40:],
            "owner": out["owner"][-40:], "deploys": out["deploys"][-40:], "unlooked": out["unlooked"][:20]}


def _attestations(path: Path) -> dict[str, Any]:
    """`<lane root>/done-attest.jsonl`: {rows, why}. A file with a line that cannot be read gives no attestation (the
    reading less likely to pass)."""
    rows = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"rows": [], "why": None}
    except OSError as exc:
        return {"rows": [], "why": f"{ATTEST} could not be read ({type(exc).__name__})"}
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return {"rows": [], "why": f"{ATTEST} has a line that cannot be read: no attestation is taken"}
        if not isinstance(row, Mapping):
            return {"rows": [], "why": f"{ATTEST} has a line that is not a record: no attestation is taken"}
        rows.append(dict(row))
    return {"rows": rows, "why": None}


def attested(cp: Mapping[str, Any], attestations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Rule item 4.8's attestation of checkpoint `cp`, or None: every attestation of its c names exactly its item-4.8
    span (`from`, `to`), `steps` 0 (an integer), the sha256 of the record it was read from and a time `at` after the
    span; one that says otherwise, or a different span, is no attestation (the reading less likely to pass)."""
    q = (cp.get("items") or {}).get("no_captain") or {}
    if q.get("status") != UNVERIFIABLE or not q.get("from") or not q.get("to"):
        return None
    mine = [a for a in attestations if isinstance(a, Mapping) and a.get("c") == cp.get("c")
            and not isinstance(a.get("c"), bool)]
    if not mine:
        return None
    to = _parse(q["to"])
    for a in mine:
        steps, at = a.get("steps"), _parse(a.get("at"))
        if (a.get("from"), a.get("to")) != (q["from"], q["to"]) or not isinstance(steps, int) or isinstance(steps, bool) \
                or steps != 0 or not isinstance(a.get("sha256"), str) or not a["sha256"] or at is None or to is None \
                or at < to:
            return None
    return dict(mine[0])


# ------------------------------------------------------------------------------------------------ the items
def _profit_vs_compute(lane_rows: Sequence[Mapping[str, Any]], first: dt.datetime | None, ledger: Mapping[str, Any] | None,
                       now: dt.datetime) -> dict[str, Any]:
    """Rule item 4.6: the lane's realized profit (every band) since the first promotion against the metered compute
    over the same span (league/ops/metered.py `since`), read now."""
    from ..ops import metered as MT

    out: dict[str, Any] = {"first_promotion": None if first is None else S.iso(first), "profit_usd": None,
                           "compute_usd": None, "compute_from": None, "partial": None, "missing": [], "read_at": S.iso(now),
                           "pass": False, "why": None}
    if first is None:
        return {**out, "why": "no promotion yet"}
    sold = [r for r in lane_rows if (_parse(r["sold_at"]) or first) >= first]
    out["profit_usd"] = round(math.fsum(float(r["pnl"]) for r in sold), 2)
    if not isinstance(ledger, Mapping):
        return {**out, "why": "no metered ledger read"}
    span = MT.since(ledger, first.date(), now.timestamp())
    out.update(compute_usd=_round(span["usd"], 4), compute_from=span["from"], partial=bool(span["partial"]),
               missing=list(span["missing"]))
    if span["usd"] is None:
        return {**out, "why": "the metered compute is not measured"}
    if span["partial"]:
        return {**out, "why": f"the metered compute is partly measured (from {span['from']}; the reading less likely "
                              "to pass)"}
    ok = out["profit_usd"] >= float(span["usd"])
    return {**out, "pass": ok, "why": None if ok else "realized profit below the metered compute"}


def _stop(loss: Mapping[str, Any] | None, now: dt.datetime) -> dict[str, Any]:
    """Rule item 7: the $800 loss budget, from the House's own figures (league/ops/fast_lane.py `probe_budget`)."""
    out: dict[str, Any] = {"read_at": S.iso(now), "realized_total_usd": None, "at_risk_usd": None,
                           "total_budget_usd": LOSS_TOTAL_USD, "used_usd": None, "spent": None, "why": None}
    if not isinstance(loss, Mapping):
        return {**out, "why": "the loss budget's figures were not read"}
    realized, risk = _num(loss.get("realized_total_usd")), _num(loss.get("at_risk_usd"))
    budget = _num(loss.get("total_budget_usd"))
    budget = LOSS_TOTAL_USD if budget is None else min(budget, LOSS_TOTAL_USD)
    if realized is None or risk is None:
        return {**out, "why": "the loss budget's figures could not be read"}
    used = realized + risk
    return {**out, "realized_total_usd": round(realized, 2), "at_risk_usd": round(risk, 2), "total_budget_usd": budget,
            "used_usd": round(used, 2), "spent": used >= budget,
            "why": "the $800 loss budget is spent: stop all spend and report" if used >= budget else None}


def items(rows: Sequence[Mapping[str, Any]], *, excluded: int, profit: Mapping[str, Any],
          quiet: Mapping[str, Any] | None, fig: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Each Done item (rule item 4) over the first-c rows: {name: {pass, value, need, why}}. `excluded`: the guard's
    Probe+ events (no promotion on record, not after it, no readable time) sold within the rows' span: item 4.3 fails
    on any (A84)."""
    fig = fig if fig is not None else figures(rows)
    n = len(rows)
    big = [p for p in fig["programs"] if p["n"] >= DONE_PER_PROGRAM]
    bound = fig["bound"]
    gaps = fig["fills"]
    sides_ok = all(gaps[f"{s}_n"] > 0 and abs(gaps[f"{s}_mean_bp"]) <= FILL_BP for s in ("entry", "exit"))
    q = quiet or {"status": SHORT, "holds": False, "why": f"fewer than {QUIET_LAST} events"}
    return {
        "events": {"pass": n >= DONE_EVENTS, "value": n, "need": f">= {DONE_EVENTS}"},
        "programs": {"pass": len(big) >= DONE_PROGRAMS, "value": len(big),
                     "need": f">= {DONE_PROGRAMS} programs with >= {DONE_PER_PROGRAM} each"},
        "after_promotion": {"pass": n > 0 and int(excluded) == 0, "value": n, "excluded": int(excluded),
                            "need": "every Probe+ event of the span bought after its program's promotion (none "
                                    "outside the count)"},
        "pnl": {"pass": n > 0 and fig["pnl_usd"] > 0, "value": fig["pnl_usd"], "need": "> 0"},
        "bound": {"pass": bound is not None and bound["lower"] > 0, "value": None if bound is None else bound["lower"],
                  "need": "95% issuer-block lower bound of r > 0"},
        "profit_vs_compute": {"pass": bool(profit.get("pass")), "value": profit.get("profit_usd"),
                              "compute_usd": profit.get("compute_usd"), "need": "profit >= metered compute",
                              "why": profit.get("why")},
        "fills": {"pass": sides_ok, "value": {s: _round(gaps[f"{s}_mean_bp"]) for s in ("entry", "exit")},
                  "n": {s: gaps[f"{s}_n"] for s in ("entry", "exit")}, "need": f"|signed mean| <= {FILL_BP:g} bp a side"},
        "no_captain": {"pass": bool(q.get("holds")), "status": q.get("status"), "value": q.get("why"),
                       "from": q.get("from"), "to": q.get("to"), "attestation": q.get("status") == UNVERIFIABLE,
                       "need": f"the last {QUIET_LAST} with no captain step (the House's records and the captain's "
                               "attestation)"},
    }


def _quiet(root: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    last = list(rows)[-QUIET_LAST:]
    if len(last) < QUIET_LAST:
        return None
    buys = [t for t in (_parse(r.get("bought_at")) for r in last) if t is not None]
    sales = [t for t in (_parse(r.get("sold_at")) for r in last) if t is not None]
    if not buys or not sales:
        return {"status": FAIL, "holds": False, "why": "the last events' times cannot be read"}
    return captain_steps(root, min(buys), max(sales))


def _pivot(rows: Sequence[Mapping[str, Any]], c: int) -> dict[str, Any]:
    """Rule item 6: at a checkpoint c >= 400, the 95% upper bound (one-sided) of r below zero retires the lane."""
    if c < PIVOT_AT:
        return {"read": False, "retire": False, "upper": None, "why": f"read from the {PIVOT_AT}th event"}
    bound = _bound(rows, SEED_PIVOT, sided="one")
    upper = None if bound is None else bound["upper"]
    retire = upper is not None and upper < 0
    return {"read": True, "retire": retire, "upper": upper, "lane": LANE,
            "why": "the lane's 95% upper bound of r is below zero: retire it and move its budget to the next lane"
            if retire else None}


def _guarded(guard: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> int:
    """The guard's Probe+ events sold at or before the last of `rows` (rule item 4.3; all of them when `rows` is empty)."""
    if not rows:
        return len(guard)
    last = str(rows[-1]["sold_at"])
    return sum(1 for g in guard if str(g.get("sold_at")) <= last)


def checkpoint(rows: Sequence[Mapping[str, Any]], c: int, *, guard: Sequence[Mapping[str, Any]], profit: Mapping[str, Any],
               stop: Mapping[str, Any], root: Any, now: dt.datetime, learning: Mapping[str, Any]) -> dict[str, Any]:
    """Checkpoint c over exactly the first c Probe+ events (rule item 3). `pending` is "attestation" when every item
    but item 4.8 passes and item 4.8 is unverifiable from the House's records: Done at c then waits on the captain's
    attestation (`attested`), read every night; the checkpoint itself is never written again."""
    first = list(rows)[:c]
    fig = figures(first)
    judged = items(first, excluded=_guarded(guard, first), profit=profit, quiet=_quiet(root, first), fig=fig)
    others = all(v["pass"] for k, v in judged.items() if k != "no_captain")
    pending = "attestation" if (c >= DONE_EVENTS and others and judged["no_captain"]["status"] == UNVERIFIABLE) else None
    return {"c": c, "written_at": S.iso(now), "rule_sha256": RULE_SHA256, "figures": fig, "items": judged,
            "done": c >= DONE_EVENTS and all(v["pass"] for v in judged.values()), "pending": pending,
            "pivot": _pivot(first, c), "stop": dict(stop), "learning": dict(learning)}


# ------------------------------------------------------------------------------------------------ the reading
def read(store: Any, *, now: dt.datetime, root: str | os.PathLike[str] | None = None,
         ledger: Mapping[str, Any] | None = None, loss: Mapping[str, Any] | None = None,
         history: Sequence[Mapping[str, Any]] = (), attestations: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The whole reading (the module docstring), pure: `store` the lane's store (its `db` read only), `root` the House's
    state root (operator edits, the stall runs; its parent's deploy record), `ledger` the metered ledger
    (league/ops/metered.py), `loss` the loss budget's figures (league/ops/fast_lane.py `probe_budget`), `history` the
    checkpoints already written (kept as they are; a checkpoint c already in it is never written again),
    `attestations` the captain's attestations of item 4.8 (`attested`)."""
    ev = counted(store)
    rows = ev["counted"]
    lane_rows = sorted(ev["counted"] + ev["before_promotion"] + ev["learning"], key=_order)
    first = first_promotion(store)
    profit = _profit_vs_compute(lane_rows, first, ledger, now)
    stop = _stop(loss, now)
    learning = _pnl(ev["learning"])
    kept = [dict(h) for h in history if isinstance(h, Mapping) and isinstance(h.get("c"), int)]
    have = {h["c"] for h in kept}
    new = []
    c = EVERY
    while c <= len(rows):
        if c not in have:
            new.append(checkpoint(rows, c, guard=ev["before_promotion"], profit=profit, stop=stop, root=root,
                                  now=now, learning=learning))
        c += EVERY
    checkpoints = sorted(kept + new, key=lambda h: h["c"])
    fig = figures(rows)
    current = items(rows, excluded=len(ev["before_promotion"]), profit=profit, quiet=_quiet(root, rows), fig=fig)
    done_at, done_by, attestation = None, None, None
    for h in checkpoints:
        if h.get("done"):
            done_at, done_by = h["c"], "records"
            break
        if h.get("pending") == "attestation" and h["c"] >= DONE_EVENTS:
            attestation = attested(h, attestations)
            if attestation is not None:
                done_at, done_by = h["c"], "attestation"
                break
    pivot = next((h["pivot"] for h in reversed(checkpoints) if (h.get("pivot") or {}).get("read")),
                 {"read": False, "retire": False, "upper": None, "why": f"read from the {PIVOT_AT}th event"})
    bands = BA.bands(store) if _has_table(store, "bands") else {}
    by = _by_program(rows)
    return {
        "schema": SCHEMA, "rule": {"file": RULE_FILE, "sha256": RULE_SHA256}, "at": S.iso(now), "lane": LANE,
        "counted": len(rows), "toward": DONE_EVENTS, "next_checkpoint": (len(rows) // EVERY + 1) * EVERY,
        "first_promotion": None if first is None else S.iso(first),
        "programs": [{"id": p.id, "version": p.version, "band": bands.get((p.id, p.version), "learning"),
                      "promoted_at": None if ev["promoted"].get((p.id, p.version)) is None
                      else S.iso(ev["promoted"][(p.id, p.version)]),
                      "n": by.get((p.id, p.version), {}).get("n", 0),
                      "pnl_usd": round(by.get((p.id, p.version), {}).get("pnl", 0.0), 2)} for p in P.SEATING],
        "learning": learning, "before_promotion": _pnl(ev["before_promotion"]),
        "current": {"figures": fig, "items": current, "note": "the reading now, over every counted event: not a "
                                                              "checkpoint, never a Done claim"},
        "profit_vs_compute": profit, "stop": stop, "pivot": pivot,
        "done": {"holds": done_at is not None, "checkpoint": done_at, "by": done_by, "attestation": attestation,
                 "pending": [h["c"] for h in checkpoints if h.get("pending") == "attestation" and h["c"] != done_at]},
        "checkpoints": checkpoints, "new_checkpoints": [h["c"] for h in new],
    }


# ------------------------------------------------------------------------------------------------ on the House
def load(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    """A done.json, or None (none, unreadable, another schema). `run` refuses to write over one it cannot read."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None


def history_of(doc: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The checkpoints a done.json holds (append-only: every one is kept as written)."""
    rows = (doc or {}).get("checkpoints")
    return [dict(h) for h in rows if isinstance(h, Mapping) and isinstance(h.get("c"), int)] if isinstance(rows, list) else []


def logged(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """The checkpoints of `done-history.jsonl` (append-only, one JSON line per checkpoint as written), the first line of
    each c kept; [] when there is none. `Unreadable` on any line that is not a checkpoint's record (a cut write)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise Unreadable(f"{HISTORY} could not be read ({type(exc).__name__})") from exc
    out: dict[int, dict[str, Any]] = {}
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise Unreadable(f"{HISTORY} line {n} cannot be read") from exc
        if not isinstance(row, dict) or not isinstance(row.get("c"), int) or isinstance(row.get("c"), bool):
            raise Unreadable(f"{HISTORY} line {n} is not a checkpoint's record")
        out.setdefault(row["c"], row)
    return [out[c] for c in sorted(out)]


def receipted(store: Any) -> set[int]:
    """Every checkpoint c a `done` receipt names as written (`new_checkpoints`). `Unreadable` on a summary that cannot
    be read."""
    if not _has_table(store, "receipts"):
        return set()
    out: set[int] = set()
    for row in store.db.execute("SELECT summary FROM receipts WHERE job=?", (JOB,)):
        if row["summary"] is None:
            continue
        try:
            summary = json.loads(row["summary"])
        except (TypeError, ValueError) as exc:
            raise Unreadable("a done receipt's summary cannot be read") from exc
        for c in (summary.get("new_checkpoints") or []) if isinstance(summary, Mapping) else ():
            if isinstance(c, int) and not isinstance(c, bool):
                out.add(c)
    return out


def history(store: Any, root: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Every checkpoint already written (rule item 3), from done.json and the append-only done-history.jsonl (the log's
    record of a c wins), oldest first. `Unreadable`, and nothing is to be written, when done.json exists but cannot be
    read at this schema (a cut write, a restore, another schema), when the log cannot be read whole, or when a `done`
    receipt names a checkpoint that neither holds (a lost history is never written again from that night's figures)."""
    root = Path(root) if root is not None else Path(store.root)
    path = root / FILE
    doc = load(path)
    if doc is None and path.exists():
        raise Unreadable(f"{FILE} exists but cannot be read at schema {SCHEMA}: it is left as it is and nothing is "
                         "written (a checkpoint is never written again)")
    by_c = {h["c"]: h for h in history_of(doc)}
    by_c.update({h["c"]: h for h in logged(root / HISTORY)})
    lost = sorted(receipted(store) - set(by_c))
    if lost:
        raise Unreadable(f"checkpoint(s) {lost} named by a done receipt are in neither {FILE} nor {HISTORY}: never "
                         "written again")
    return [by_c[c] for c in sorted(by_c)]


def write(path: str | os.PathLike[str], doc: Mapping[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(doc, sort_keys=True, default=str))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def append(path: str | os.PathLike[str], records: Iterable[Mapping[str, Any]]) -> None:
    """Append each record as one JSON line to `path` (done-history.jsonl), synced to disk before done.json is written."""
    lines = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in records)
    if not lines:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(lines)
        handle.flush()
        os.fsync(handle.fileno())


def _loss(state: Path, now: dt.datetime) -> dict[str, Any] | None:
    """The loss budget's figures (league/ops/fast_lane.py `probe_budget`, read-only on `<state>/live.sqlite`)."""
    live = state / "live.sqlite"
    if not live.exists():
        return None
    try:
        from ..ops import fast_lane

        return fast_lane.probe_budget(live, now.astimezone(C.NY).date().isoformat())
    except Exception:  # noqa: BLE001 - not read: the stop says so
        return None


def run(store: Any, *, now: dt.datetime, state: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """The House's nightly reading (league/events/house.py `_screen`): reads the store, `<state>` (the lane store's
    parent by default), the history (`history`; `Unreadable` and no write when a record cannot be read) and the
    attestations, appends each new checkpoint to `<state>/events/done-history.jsonl` and then writes
    `<state>/events/done.json` (the lane store's root)."""
    from ..ops import metered as MT

    root = Path(store.root)
    state = Path(state) if state is not None else root.parent
    before = history(store, root)
    attest = _attestations(root / ATTEST)
    doc = read(store, now=now, root=state, ledger=MT.load(state), loss=_loss(state, now), history=before,
               attestations=attest["rows"])
    doc["attestations"] = {"n": len(attest["rows"]), "why": attest["why"]}
    fresh = set(doc["new_checkpoints"])
    append(root / HISTORY, [h for h in doc["checkpoints"] if h["c"] in fresh])
    write(root / FILE, doc)
    return doc


def receipt(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The `done` receipt's summary: figures only."""
    fig = (doc.get("current") or {}).get("figures") or {}
    bound = fig.get("bound") or {}
    return {"counted": doc.get("counted"), "next_checkpoint": doc.get("next_checkpoint"),
            "new_checkpoints": list(doc.get("new_checkpoints") or []), "done": (doc.get("done") or {}).get("holds"),
            "done_by": (doc.get("done") or {}).get("by"), "pending": list((doc.get("done") or {}).get("pending") or []),
            "pivot": (doc.get("pivot") or {}).get("retire"), "stop": (doc.get("stop") or {}).get("spent"),
            "lower": _round(bound.get("lower"), 6), "learning": (doc.get("learning") or {}).get("n"),
            "rule": str(RULE_SHA256)[:8]}


__all__ = ["RULE_FILE", "RULE_SHA256", "Unreadable", "counted", "promoted_at", "figures", "first_promotion",
           "captain_steps", "operator_edits", "owner_deploys", "attested", "items", "checkpoint", "read", "run", "load",
           "write", "append", "history", "history_of", "logged", "receipted", "receipt", "rule_sha256"]
