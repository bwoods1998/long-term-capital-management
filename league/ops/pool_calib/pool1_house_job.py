"""POOL1 CALIBRATION: THE ONE READ-ONLY HOUSE JOB (PREREG-POOL1 section 12, after 20:05Z Mon Oct 19; section 4.2 (c)).
NOT RUN BEFORE THEN. Sent whole through scratch/weekend/ops/boxrun.py (one call a step, each under 180 s), driven by
calib/house_job/drive.py, which refuses to start outside the PREREG's window.

TRAIN ERAS ONLY. What it reads, read-only (sqlite mode=ro; the equity store's files):
- forward.sqlite `fwd_registry` (ids, reasons, groups, lineages, first days, NEEDS, program sha, and the frozen code
  for the event-field scan and the runs); no `fwd_days`, `fwd_checks`, `fwd_ll` or any forward value;
- forward-screen.sqlite `fwd1_lineages` (type, case, judged: no verdict, no check, no floor);
- swarm.sqlite `families` (structure, spec: lane, hidden year, card sha; band, retired_at; the NAMES of sealed state
  keys only; the E2 record's passed version) and `family_cards` (declared class, inputs);
- the equity store's Train-era bars (2016-01-04..2019-12-31 and 2022-01-03..2024-12-31 and their history sessions),
  through the House's own runner (league/equity/runner.Isolated in the job's own decider child, as
  forward_screen.HouseRuns.etf_pools does) and screen.series' accounting, per symbol.
No Validation, holdout, look or forward figure; no live, cash, account or P&L figure; no env or secret.
ITS ONLY BOX WRITES ARE ITS DECIDER CHILD'S LOG LINES (forward-decider.log, as the forward jobs' children write).
It runs at nice 19.

TASKS (sys.argv): `meta` (the founding lineages and their members' metadata; no run); `prices` (the cost-free
close-to-close returns of every ETF on the Train eras, for the regime cells); `run --units PID:PART,...
[--budget S]` (each PART one engine run: e0k10, e0k15, e1k10, e1k15 the Train eras at k 1.0 and 1.5; s0, s1, ... the
member's seen spans at k 1.0, elane_folds.seen_spans(its hidden year), re-run in the child (DEVIATIONS D16); units are
run in order until S seconds have passed). Output: one line "POOL1 <base64 gzip JSON>"."""
from __future__ import annotations

import base64
import datetime as dt
import gzip
import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

VERSION = "POOL1-house-job-1"
ROOT = Path("/workspace/state")
CODE = "/workspace/current"
SEALED_STATE = ("elane_try", "elane_verdicts", "elane_look", "elane_xs_precheck", "elane_xs_look")
PASS_REASONS = ("train_pass", "seed", "live")
RUN_BUDGET = 60.0           # one engine run's budget in the child (a retry alone may raise it to 150)
EVENT_WORD = re.compile(r"\bevents(?:_next)?\b")
EVENT_FIELD = re.compile(r"(?:\.|\[\s*['\"])events(?:_next)?\b")
T0 = time.time()


def _ro(root: Path, name: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{root / name}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _num(x, digits: int = 12):
    if x is None:
        return None
    v = float(x)
    if not math.isfinite(v):
        return None
    return float(f"{v:.{digits}g}")


def _arr(a) -> list:
    return [_num(v) for v in a]


# ------------------------------------------------------------------------------------------------------------ meta
def meta(root: Path) -> dict:
    """Every forward-registry lineage (controls excluded) with its FIRST PASSING version (the member: the lowest pid
    whose reason is train_pass, seed or live), and what 1.1-1.2 and 7.2 need of it. Counts and words only."""
    from league.swarm import cards, elane_folds

    out: dict = {"version": VERSION, "now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "errors": []}
    f = _ro(root, "forward.sqlite")
    reg = [dict(r) for r in f.execute(
        "SELECT pid, key, family, version, lane, reason, ugroup, lineage, first_day, program_sha, needs, code "
        "FROM fwd_registry WHERE reason != 'control' ORDER BY pid")]
    f.close()
    fwd1: dict = {}
    try:
        s = _ro(root, "forward-screen.sqlite")
        fwd1 = {r["lineage"]: {"type": r["type"], "case": r["case_"], "judged": int(r["judged"])}
                for r in s.execute("SELECT lineage, type, case_, judged FROM fwd1_lineages")}
        s.close()
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"fwd1_lineages: {type(exc).__name__}")
    d = _ro(root, "swarm.sqlite")
    cols = [r[1] for r in d.execute("PRAGMA table_info(families)")]
    mcol = "mechanism" if "mechanism" in cols else None
    fams: dict = {}
    for r in d.execute(f"SELECT id, structure, spec, state, retired_at, band{', ' + mcol if mcol else ''} FROM families"):
        try:
            spec = json.loads(r["spec"] or "{}")
            st = json.loads(r["state"] or "{}")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(spec, dict):
            continue
        st = st if isinstance(st, dict) else {}
        rec = st.get("elane_e2") if isinstance(st.get("elane_e2"), dict) else {}
        fams[r["id"]] = {"spec": spec, "structure": r["structure"], "alive": r["retired_at"] is None,
                         "band": r["band"], "pv": rec.get("passed_version"),
                         "sealed": any(k in st for k in SEALED_STATE), "mech": r[mcol] if mcol else None}
    cards_by_fam, cards_by_sha = {}, {}
    try:
        for r in d.execute("SELECT family, sha, card FROM family_cards ORDER BY at"):
            try:
                c = json.loads(r["card"])
            except Exception:  # noqa: BLE001
                continue
            cards_by_fam[r["family"]] = c
            cards_by_sha.setdefault(r["sha"], c)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"family_cards: {type(exc).__name__}")
    d.close()

    def card(fid):
        c = cards_by_fam.get(fid)
        if c is None:
            sha = ((fams.get(fid) or {}).get("spec") or {}).get("card_sha")
            c = cards_by_sha.get(sha) if sha else None
        return c or {}

    lin: dict = {}
    for r in reg:
        lin.setdefault(r["lineage"], []).append(r)
    members = []
    for key, rows in sorted(lin.items()):
        passes = sorted((r for r in rows if r["reason"] in PASS_REASONS), key=lambda r: r["pid"])
        if not passes:
            continue
        m = passes[0]
        fam = fams.get(m["family"]) or {}
        cd = card(m["family"])
        try:
            ik = cards.infer_key(fam.get("mech") or "", fam.get("structure")) if fam.get("mech") else None
        except Exception:  # noqa: BLE001
            ik = None
        try:
            needs = json.loads(m["needs"] or "{}")
        except Exception:  # noqa: BLE001
            needs = {}
        hidden = elane_folds.hidden_year(fam) if fam else None
        try:
            seen = [[a.isoformat(), b.isoformat()] for a, b in elane_folds.seen_spans(hidden)]
        except Exception:  # noqa: BLE001
            seen = []
        code = str(m["code"] or "")
        any_alive_gym = any((fams.get(r["family"]) or {}).get("alive") and (fams.get(r["family"]) or {}).get("band") == "gym"
                            and (fams.get(r["family"]) or {}).get("pv") is not None for r in passes)
        any_sealed = any((fams.get(r["family"]) or {}).get("sealed") for r in rows)
        j = fwd1.get(key) or {}
        members.append({
            "lineage": key, "pid": int(m["pid"]), "key": m["key"], "family": m["family"], "version": m["version"],
            "lane": m["lane"], "reason": m["reason"], "ugroup": m["ugroup"], "first_day": m["first_day"],
            "program_sha": m["program_sha"], "needs_symbols": list(needs.get("symbols") or []),
            "declared_class": cd.get("mechanism_class") or None, "inputs": list(cd.get("inputs") or []),
            "infer_key_class": (ik or {}).get("class"), "event_word": bool(EVENT_WORD.search(code)),
            "event_field": bool(EVENT_FIELD.search(code)), "seen_spans": seen, "hidden": hidden is not None,
            "seat_shape": bool(any_alive_gym and not any_sealed), "reached_sealed": bool(any_sealed),
            "fwd1_type": j.get("type"), "fwd1_case": j.get("case"), "fwd1_judged": j.get("judged"),
            "lineage_pids": [int(r["pid"]) for r in rows], "panel": str(m["ugroup"]).startswith("panel"),
        })
    out["members"] = members
    out["lineages"] = len(lin)
    out["elapsed_s"] = round(time.time() - T0, 1)
    return out


def run_list(members: list) -> list:
    """The runs the calibration needs, members first by pid: every member that 1.2's metadata does not already put
    out (panels, equity_premium, event readers by card input or code word, a stocks symbol)."""
    out = []
    for m in sorted(members, key=lambda x: x["pid"]):
        if m["panel"] or m["declared_class"] == "equity_premium" or "event_calendar" in m["inputs"] \
                or m["event_word"] or "stocks" in str(m["ugroup"]):
            continue
        for part in ("e0k10", "e0k15", "e1k10", "e1k15"):
            out.append(f"{m['pid']}:{part}")
        if m["hidden"]:                      # no hidden year: the seen spans are the eras themselves (e0k10, e1k10)
            for i in range(len(m["seen_spans"])):
                out.append(f"{m['pid']}:s{i}")
    return out


# ---------------------------------------------------------------------------------------------------------- prices
def prices(root: Path) -> dict:
    """{era: {"days": [ISO], sym: [R]}}: each ETF's cost-free close-to-close return on every Train-era session (0 at
    an era's first session or where a close is missing), from the store's adjustment=all closes."""
    from league.equity import config as econfig
    from league.equity.store import EquityStore, from_ordinal

    store = EquityStore(root / "equity-daily")
    syms = [s for s, c in econfig.UNIVERSE.items() if c == econfig.ETF]
    out: dict = {"version": VERSION, "missing": []}
    for e, (first, last) in enumerate(econfig.TRAIN_ERA_SEGMENTS):
        ref = store.span(["SPY"], first, last, history=0)
        days = [from_ordinal(int(x)).isoformat() for x in ref.days[int(ref.first):]]
        ent = {"days": days}
        for s in syms:
            try:
                bars = store.span([s], first, last, history=0)
            except Exception as exc:  # noqa: BLE001 - a symbol the store does not hold
                out["missing"].append(f"e{e}:{s}:{type(exc).__name__}")
                continue
            bd = [from_ordinal(int(x)).isoformat() for x in bars.days]
            c = [float(v) for v in bars.adj[s][:, 3]]
            at = {d: i for i, d in enumerate(bd)}
            r = []
            for d in days:
                t = at.get(d)
                ok = t is not None and t >= 1 and math.isfinite(c[t]) and math.isfinite(c[t - 1]) and c[t - 1] > 0
                r.append(_num(c[t] / c[t - 1] - 1.0) if ok else (0.0 if t is not None and math.isfinite(c[t]) else None))
            ent[s] = r
        out[f"e{e}"] = ent
    out["elapsed_s"] = round(time.time() - T0, 1)
    return out


# ------------------------------------------------------------------------------------------------------------- runs
def _capital(result, default) -> float:
    try:
        v = float(str(result.get("capital")))
    except (TypeError, ValueError):
        v = float(default)
    return v if math.isfinite(v) and v > 0 else float(default)


def one_run(root: Path, decider, fdb, pid: int, part: str, seen: list, run_budget: float = RUN_BUDGET) -> dict:
    """One engine run of the member's registered version: a Train era at k 1.0 or 1.5, or one of its seen spans at
    k 1.0. Its series from `screen.POOL_SKIP` (S2's convention): days (ordinals), r, and for k 1.0 also w, b, exits,
    invested, sides (the weights of lots entering or exiting), the exposure per symbol (screen.series of that
    symbol's lots) and each universe symbol's close-to-close return on the run's own bars."""
    from league.equity import config as econfig
    from league.equity import screen as S
    from league.equity.runner import Isolated
    from league.equity.store import EquityStore, from_ordinal
    from league.ops import forward_db
    from league.ops.forward_screen import lot_sides

    row = fdb.execute("SELECT key FROM fwd_registry WHERE pid=?", (int(pid),)).fetchone()
    program = forward_db.program(fdb, str(row["key"]))
    iso = Isolated(decider, root / "equity-daily", budget_seconds=float(run_budget))
    needs = iso._needs(program.code, program.params, program.key)
    store = EquityStore(root / "equity-daily")
    if part.startswith("e"):
        e, k = int(part[1]), (econfig.K_BASE if part[2:] == "k10" else econfig.K_STRESS)
        first, last = econfig.TRAIN_ERA_SEGMENTS[e]
    else:
        i = int(part[1:])
        first, last = (dt.date.fromisoformat(x) for x in seen[i])
        k = econfig.K_BASE
    bars = store.span(needs.symbols, first, last, history=needs.history)
    run = iso._run(program.code, program.params, program.key, bars, k)
    result = run.result
    status = str(result.get("status"))
    out = {"pid": int(pid), "part": part, "status": status, "span": [first.isoformat(), last.isoformat()],
           "k": float(k)}
    if status != "ok":
        out["why"] = str(result.get("reason") or "")[:200]
        return out
    universe = [str(s) for s in (result.get("symbols") or needs.symbols)]
    cap = _capital(result, econfig.SLEEVE_USD)
    lots = result.get("lots") or []
    ser = S.series(lots, run.bars, universe=universe, capital=cap)
    skip = S.POOL_SKIP
    days = [int(x) for x in ser.days[skip:]]
    out.update(days=days, r=_arr(ser.r[skip:]), universe=universe, capital=cap, skip=skip)
    if k != econfig.K_BASE:
        return out
    out.update(w=_arr(ser.w[skip:]), b=_arr(ser.b[skip:]), exits=[int(x) for x in ser.exits[skip:]],
               invested=[int(bool(x)) for x in ser.invested[skip:]], lots=len(lots))
    sd = lot_sides({"lots": lots})
    iso_days = [from_ordinal(x).isoformat() for x in days]
    out["sides"] = [_num(sd.get(d, 0.0)) for d in iso_days]
    ws = {}
    for s in universe:
        mine = [lot for lot in lots if str(lot.get("symbol")) == s]
        if mine:
            ws[s] = _arr(S.series(mine, run.bars, universe=universe, capital=cap).w[skip:])
    out["ws"] = ws
    lo = int(run.bars.first)
    R = {}
    for s in universe:
        c = [float(v) for v in run.bars.adj[s][:, 3]]
        rr = []
        for t in range(lo + skip, lo + skip + len(days)):
            ok = t >= 1 and math.isfinite(c[t]) and math.isfinite(c[t - 1]) and c[t - 1] > 0
            rr.append(_num(c[t] / c[t - 1] - 1.0) if ok else 0.0)
        R[s] = rr
    out["R"] = R
    return out


def run_units(root: Path, decider, units: list, seen_of: dict, budget: float, run_budget: float = RUN_BUDGET) -> dict:
    from league.ops import forward_db

    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    done, errors, left = {}, {}, []
    try:
        for unit in units:
            if done or errors:
                if time.time() - T0 > budget:
                    left.append(unit)
                    continue
            pid, part = unit.split(":")
            try:
                done[unit] = one_run(root, decider, fdb, int(pid), part, seen_of.get(pid) or [], run_budget)
            except Exception as exc:  # noqa: BLE001 - the program's or the House's: the driver retries once
                errors[unit] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        fdb.close()
    return {"version": VERSION, "done": done, "errors": errors, "left": left, "elapsed_s": round(time.time() - T0, 1)}


def emit(obj: dict) -> None:
    blob = base64.b64encode(gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), 9)).decode()
    sys.stdout.write("POOL1 " + blob + "\n")


def main(argv: list) -> int:
    try:
        os.nice(19)
    except Exception:  # noqa: BLE001
        pass
    sys.path.insert(0, os.path.realpath(CODE))
    sys.dont_write_bytecode = True
    task = argv[0] if argv else "meta"
    if task == "meta":
        emit(meta(ROOT))
        return 0
    if task == "prices":
        emit(prices(ROOT))
        return 0
    if task == "run":
        units = argv[argv.index("--units") + 1].split(",")
        budget = float(argv[argv.index("--budget") + 1]) if "--budget" in argv else 100.0
        seen_of = json.loads(argv[argv.index("--seen") + 1]) if "--seen" in argv else {}
        run_budget = float(argv[argv.index("--run-budget") + 1]) if "--run-budget" in argv else RUN_BUDGET
        from league.ops import forward_shadow

        decider = forward_shadow._decider(ROOT)
        try:
            emit(run_units(ROOT, decider, units, seen_of, budget, run_budget))
        finally:
            try:
                decider.close()
            except Exception:  # noqa: BLE001
                pass
        return 0
    sys.stderr.write(f"unknown task {task!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
