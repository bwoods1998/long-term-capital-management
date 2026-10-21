"""THE DONE READER OF THE GOAL OF OCT 19, 2026 (V2): every 100 settled real-money events at Probe size or above.

The rule is docs/goals/DONE-RULE-EVL-2.md, pinned here by its sha256 (`RULE_SHA256`; league/tests/test_events_done.py
fails while the file and the constant differ). This module reads it; it never changes it.

- `counted(store)`: the lane's settled real-money events of every seating program version, split into the COUNTED
  Probe+ events (the buy's band probe or sized, bought after the program's latest move to probe: `bands.probe_since`),
  the `before_promotion` ones (a Probe+ buy before that move) and the `learning` ones; every row enriched with the
  shadow's benchmark return `b` (outcomes) and the fill gap per side against the shadow's auction prices.
- `figures(rows)`: n, by program, P&L, mean r, the 95% issuer-block lower bound (rule item 4.5), benchmark-net a beside,
  the fill gaps (item 4.7).
- `captain_steps(root, start, end)`: rule item 4.8 from the House's records (before-copies, the files' modification
  times, the stall job's runs in ops.sqlite).
- `read(...)`: the whole reading, PURE over what it is given (the store, the state root, the ledger, the loss figures,
  the checkpoint history): every figure, the current reading, the new checkpoints (100, 200, ...; each over exactly the
  first c events), each item pass or fail with its number, the pivot and the $800 stop. It opens nothing for writing.
- `run(store, now=...)`: the House's nightly call (league/events/house.py `_screen`, after the band review): the
  history from `<state>/events/done.json`, `read`, and the file written again with the history APPEND-ONLY (a written
  checkpoint is never rewritten). `receipt(doc)`: the `done` receipt's summary (figures only).

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
RULE_SHA256 = "2f92a153501771c50a6bec9bf6d2c3fca9c78002199964d72a9d4d4528217069"
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
#: The operator tools' before-copies: `<file>.before-<what>-<YYYYMMDDTHHMMSSZ>`.
BEFORE = re.compile(r"^(swarm|ops|budget)\.json\.before-(.*?)-?(\d{8}T\d{6}Z)$")
#: The files an operator edits by hand whose modification time is an edit (the House only reads them).
EDITED = ("swarm.json", "ops.json")
ITEMS = ("events", "programs", "after_promotion", "pnl", "bound", "profit_vs_compute", "fills", "no_captain")
UTC = dt.timezone.utc


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


def counted(store: Any) -> dict[str, Any]:
    """The lane's settled real-money events (rule items 1 and 5): {counted, before_promotion, learning: [rows], promoted:
    {(program, version): the latest move to probe, or None}}, each list in the count's order (the sale's time, program,
    version, event). Read-only."""
    out: dict[str, Any] = {"counted": [], "before_promotion": [], "learning": [], "promoted": {}}
    if not _has_table(store, "real_fills"):
        return out   # a store from before release 1019b: no real fill
    for prog in P.SEATING:
        key = (prog.id, prog.version)
        rows = _enrich(store, prog.id, prog.version,
                       BA.real_events(store, prog.id, prog.version, at=("learning",) + BA.PROBE_PLUS))
        since = BA.probe_since(store, prog.id, prog.version) if _has_table(store, "band_history") else None
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
    if not _has_table(store, "band_history"):
        return None
    seating = {(p.id, p.version) for p in P.SEATING}
    moments = []
    for row in store.db.execute("SELECT program, version, since, written_at FROM band_history WHERE band='probe'"):
        if (str(row["program"]), int(row["version"])) not in seating:
            continue
        times = [t for t in (_parse(row["since"]), _parse(row["written_at"])) if t is not None]
        if times:
            moments.append(max(times))
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


def operator_edits(root: str | os.PathLike[str], start: dt.datetime, end: dt.datetime) -> list[dict[str, Any]]:
    """Rule item 4.8's operator edits in [start, end]: the before-copies by their stamp, and the modification time of
    `swarm.json` and `ops.json`, [{file, what, at}], oldest first."""
    out = []
    root = Path(root)
    try:
        names = [p.name for p in root.iterdir()]
    except OSError:
        names = []
    for name in names:
        m = BEFORE.match(name)
        if not m:
            continue
        try:
            at = _stamp(m.group(3))
        except ValueError:
            continue
        if start <= at <= end:
            out.append({"file": f"{m.group(1)}.json", "what": m.group(2) or None, "at": S.iso(at)})
    for name in EDITED:
        try:
            at = dt.datetime.fromtimestamp((root / name).stat().st_mtime, UTC)
        except OSError:
            continue
        if start <= at <= end:
            out.append({"file": name, "what": "modified", "at": S.iso(at)})
    return sorted(out, key=lambda e: (e["at"], e["file"]))


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


def captain_steps(root: str | os.PathLike[str] | None, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    """Rule item 4.8 over [start, end]: {holds, why, edits, owner (the stall runs with an owner step: {at, causes}),
    stall_runs, unlooked (the UTC days with no ok stall run)}."""
    out: dict[str, Any] = {"from": S.iso(start), "to": S.iso(end), "edits": [], "owner": [], "stall_runs": 0,
                           "unlooked": [], "holds": False, "why": None}
    if root is None:
        return {**out, "why": "the House's records were not read"}
    root = Path(root)
    out["edits"] = operator_edits(root, start, end)
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
        except (TypeError, ValueError):
            checks = {}
        causes = sorted(str(c) for c, chk in (checks.items() if isinstance(checks, Mapping) else ())
                        if isinstance(chk, Mapping) and chk.get("stalled") and chk.get("owner_step")
                        and c not in NEWS_CAUSES)
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
        whys.append(f"{len(out['edits'])} operator edit(s), the first {out['edits'][0]['file']} at {out['edits'][0]['at']}")
    if out["owner"]:
        whys.append(f"an owner step waiting at {len(out['owner'])} stall run(s) ({', '.join(out['owner'][0]['causes'])})")
    if out["unlooked"]:
        whys.append(f"no stall run on {len(out['unlooked'])} UTC day(s), the first {out['unlooked'][0]}")
    return {**out, "holds": not whys, "why": "; ".join(whys) or None, "edits": out["edits"][-40:],
            "owner": out["owner"][-40:], "unlooked": out["unlooked"][:20]}


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
    """Each Done item (rule item 4) over the first-c rows: {name: {pass, value, need, why}}."""
    fig = fig if fig is not None else figures(rows)
    n = len(rows)
    big = [p for p in fig["programs"] if p["n"] >= DONE_PER_PROGRAM]
    bound = fig["bound"]
    gaps = fig["fills"]
    sides_ok = all(gaps[f"{s}_n"] > 0 and abs(gaps[f"{s}_mean_bp"]) <= FILL_BP for s in ("entry", "exit"))
    q = quiet or {"holds": False, "why": f"fewer than {QUIET_LAST} events"}
    return {
        "events": {"pass": n >= DONE_EVENTS, "value": n, "need": f">= {DONE_EVENTS}"},
        "programs": {"pass": len(big) >= DONE_PROGRAMS, "value": len(big),
                     "need": f">= {DONE_PROGRAMS} programs with >= {DONE_PER_PROGRAM} each"},
        "after_promotion": {"pass": n > 0, "value": n, "excluded": int(excluded),
                            "need": "every counted event bought after its program's promotion"},
        "pnl": {"pass": n > 0 and fig["pnl_usd"] > 0, "value": fig["pnl_usd"], "need": "> 0"},
        "bound": {"pass": bound is not None and bound["lower"] > 0, "value": None if bound is None else bound["lower"],
                  "need": "95% issuer-block lower bound of r > 0"},
        "profit_vs_compute": {"pass": bool(profit.get("pass")), "value": profit.get("profit_usd"),
                              "compute_usd": profit.get("compute_usd"), "need": "profit >= metered compute",
                              "why": profit.get("why")},
        "fills": {"pass": sides_ok, "value": {s: _round(gaps[f"{s}_mean_bp"]) for s in ("entry", "exit")},
                  "n": {s: gaps[f"{s}_n"] for s in ("entry", "exit")}, "need": f"|signed mean| <= {FILL_BP:g} bp a side"},
        "no_captain": {"pass": bool(q.get("holds")), "value": q.get("why"),
                       "need": f"the last {QUIET_LAST} with no captain step"},
    }


def _quiet(root: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    last = list(rows)[-QUIET_LAST:]
    if len(last) < QUIET_LAST:
        return None
    buys = [t for t in (_parse(r.get("bought_at")) for r in last) if t is not None]
    sales = [t for t in (_parse(r.get("sold_at")) for r in last) if t is not None]
    if not buys or not sales:
        return {"holds": False, "why": "the last events' times cannot be read"}
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


def checkpoint(rows: Sequence[Mapping[str, Any]], c: int, *, excluded: int, profit: Mapping[str, Any], stop: Mapping[str, Any],
               root: Any, now: dt.datetime, learning: Mapping[str, Any]) -> dict[str, Any]:
    """Checkpoint c over exactly the first c Probe+ events (rule item 3)."""
    first = list(rows)[:c]
    fig = figures(first)
    judged = items(first, excluded=excluded, profit=profit, quiet=_quiet(root, first), fig=fig)
    return {"c": c, "written_at": S.iso(now), "rule_sha256": RULE_SHA256, "figures": fig, "items": judged,
            "done": c >= DONE_EVENTS and all(v["pass"] for v in judged.values()), "pivot": _pivot(first, c),
            "stop": dict(stop), "learning": dict(learning)}


# ------------------------------------------------------------------------------------------------ the reading
def read(store: Any, *, now: dt.datetime, root: str | os.PathLike[str] | None = None,
         ledger: Mapping[str, Any] | None = None, loss: Mapping[str, Any] | None = None,
         history: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The whole reading (the module docstring), pure: `store` the lane's store (its `db` read only), `root` the House's
    state root (operator edits, the stall runs), `ledger` the metered ledger (league/ops/metered.py), `loss` the loss
    budget's figures (league/ops/fast_lane.py `probe_budget`), `history` the checkpoints already written (kept as they
    are; a checkpoint c already in it is never written again)."""
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
            new.append(checkpoint(rows, c, excluded=len(ev["before_promotion"]), profit=profit, stop=stop, root=root,
                                  now=now, learning=learning))
        c += EVERY
    checkpoints = sorted(kept + new, key=lambda h: h["c"])
    fig = figures(rows)
    current = items(rows, excluded=len(ev["before_promotion"]), profit=profit, quiet=_quiet(root, rows), fig=fig)
    done_at = next((h["c"] for h in checkpoints if h.get("done")), None)
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
        "done": {"holds": done_at is not None, "checkpoint": done_at},
        "checkpoints": checkpoints, "new_checkpoints": [h["c"] for h in new],
    }


# ------------------------------------------------------------------------------------------------ on the House
def load(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    """A done.json, or None (none, unreadable, another schema or rule)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None


def history_of(doc: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The checkpoints a done.json holds (append-only: every one is kept as written)."""
    rows = (doc or {}).get("checkpoints")
    return [dict(h) for h in rows if isinstance(h, Mapping) and isinstance(h.get("c"), int)] if isinstance(rows, list) else []


def write(path: str | os.PathLike[str], doc: Mapping[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


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
    parent by default) and writes `<state>/events/done.json` (the lane store's root) with the history append-only."""
    from ..ops import metered as MT

    root = Path(store.root)
    state = Path(state) if state is not None else root.parent
    path = root / FILE
    old = load(path)
    doc = read(store, now=now, root=state, ledger=MT.load(state), loss=_loss(state, now), history=history_of(old))
    write(path, doc)
    return doc


def receipt(doc: Mapping[str, Any]) -> dict[str, Any]:
    """The `done` receipt's summary: figures only."""
    fig = (doc.get("current") or {}).get("figures") or {}
    bound = fig.get("bound") or {}
    return {"counted": doc.get("counted"), "next_checkpoint": doc.get("next_checkpoint"),
            "new_checkpoints": list(doc.get("new_checkpoints") or []), "done": (doc.get("done") or {}).get("holds"),
            "pivot": (doc.get("pivot") or {}).get("retire"), "stop": (doc.get("stop") or {}).get("spent"),
            "lower": _round(bound.get("lower"), 6), "learning": (doc.get("learning") or {}).get("n"),
            "rule": str(RULE_SHA256)[:8]}


__all__ = ["RULE_FILE", "RULE_SHA256", "counted", "figures", "first_promotion", "captain_steps", "operator_edits",
           "items", "checkpoint", "read", "run", "load", "write", "history_of", "receipt", "rule_sha256"]
