"""The `fast_lane` job (after each `direction` run) and FAST LANE V2's report (Oct 7, 2026; D2 and D4, and the review of
Oct 7): the drift fit and the same-risk buy-and-hold beside every screen result and every band row, the contamination
measures beside every holdout look, the D5 status of every live band, and the Probe loss budget.

REPORTED, NEVER A BAR: nothing in the tournament, the gate, the bands or the money table reads any of it
(`league/tests/test_fast_lane_v2.py` pins that no module of `league/swarm`, `league/live` or `league/gym` imports this
module or the direction figures).

THE JOB (`run`): after each `direction` run (at the House's start, after the grant, and daily 01:00Z), it opens the swarm
store and the live state READ-ONLY (`guard.readonly()`: every SQLite open in the child is a `mode=ro` URI), builds the
report with the screen rows of the last `JOB_DAYS` days (every holdout look, every band row and the Probe budget whole),
and writes it atomically to `<state>/fast-lane-report.json`, so a pass or a band is never shown without its
buy-and-hold beside it, whether or not anyone runs the script. A Probe or Sized family whose look has no buy-and-hold
(the closes file lacks its days) is one House warning. `scripts/fast_lane_report.py` is the same report on COPIES, from
the command line, with any `--since`.

THE REPORT (`report`), JSON:
- `screen`: one row for every Validation run of a version (stress 1.0, status ok) since `since`, from the store's run
  rows (the durable record: a superseded or pruned verdict still has its row); `passed` is the tournament's verdict for
  the version (`validation_verdicts`, which keeps each version's latest and the newest 64 versions), None with
  `verdict_kept` False when the map no longer holds it. And every holdout look since `since`: family, version, window,
  passed, pnl, `bh` (the same-risk buy-and-hold, `league/ops/direction.py`), `drift_train` (the Gym's own Train fit); a
  look adds `drift_window` (the daily-close fit on its holdout daily P&L), its `tail` (as the gate recorded it) and its
  `contamination` (below).
- `contamination`: pooled over every look in `screen` (below).
- `bands`: every Candidate, Probe or Sized family: its banded version's screen rows; its live realized P&L (forward rows,
  source "real", that version, net of fees) with `bh` and `drift_window` over its live sessions since `live_promoted_at`
  (zeros included); `live_vs_holdout`; its D5 status (`money.live_demotion`: D5, or DM1 under `probe.demotion` "dm1"
  since release L-D, its `rule` named).
- `probe_budget`: `real.probe_tally` on the live state under the constitution's `probe.loss_basis` (gross realized Probe
  losses at fast lane v2; net since release L-D, Oct 9, 2026), with `realized_basis` naming the basis in force, at risk,
  the open count, the room. THE ROLLING PROBE BUDGET (release L-D): `realized_usd` is the window's figure (the closes of
  the last `window_sessions` New York sessions, from `window_start`, `real.probe_realized`) against `budget_usd`, and
  `realized_total_usd` every close's against `total_budget_usd`; `room_usd` is what the tighter of the two envelopes
  leaves and `binding` names it.

CONTAMINATION, MEASURED (the review of Oct 7, 2026; goal item 5: "contamination measured and stated"). 123 of the
holdout's 184 sessions (through 2026-06-30) are inside the training of Opus 5.5 (cutoff June 2026); the other authors'
cutoffs are unknown (DeepSeek-V4-Flash wrote most versions). Three measures, each reported only and each weak in power:
1. Per look: the holdout daily series split at `evidence.CONTAMINATION_TAIL_FROM` into the in-training HEAD and the
   after-cutoff TAIL: each part's days, P&L, daily Sharpe, own block-bootstrap p (2,000 draws, seeded by the program),
   and whether that part alone would meet the look's level with a positive P&L; and the head-minus-tail Sharpe gap.
2. Pooled over the looks (`contamination`): the mean head-minus-tail Sharpe gap, its standard error and t (a positive
   mean says the programs did better inside the authors' training than after it, as a contaminated author's would), and
   the share of looks whose head alone passes against the share whose tail alone passes. With a handful of looks and a
   61-session tail its power is low: a gap of 0.1 daily Sharpe needs on the order of 100 looks to show.
3. Per live band (`live_vs_holdout`): the live realized P&L per dollar of maximum loss against the holdout's
   (`pnl_per_max_loss` of the banded version's holdout run): live trading is after every author's training.
"""
from __future__ import annotations

import math
import sqlite3
import statistics
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

FILE = "fast-lane-report.json"
#: The job's window for Validation screen rows (looks, bands and the budget are whole).
JOB_DAYS = 7
VALIDATION = ("2025-01-02", "2025-12-31")


def _ny():
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


def _sd(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _roots(store: Any, fam: Mapping[str, Any], n: int) -> tuple[str, ...]:
    from ..swarm.researcher import needs_roots

    version = store.version(fam["id"], n) or {}
    return needs_roots(version.get("code"), fam.get("roots") or ())


# ------------------------------------------------------------------------------------------------- screen rows
def validation_runs(store: Any, fid: str, since: str | None) -> dict[int, dict[str, Any]]:
    """{version: its latest Validation run row at stress 1.0 with status ok, since `since`} (the store's run rows)."""
    out: dict[int, dict[str, Any]] = {}
    for row in store.runs(fid, window="validation", limit=1_000_000):
        if row.get("version") is None or str(row.get("status")) != "ok" or str(row.get("purpose")) != "validation":
            continue
        try:
            if float(row.get("stress")) != 1.0:
                continue
        except (TypeError, ValueError):
            continue
        if since is not None and str(row.get("at") or "") < since:
            continue
        n = int(row["version"])
        if n not in out or str(row.get("at") or "") > str(out[n].get("at") or ""):
            out[n] = row
    return out


def validation_row(store: Any, fam: Mapping[str, Any], n: int, run: Mapping[str, Any], verdict: Any, closes: Mapping,
                   validation_days: list[str]) -> dict[str, Any]:
    from . import direction as DIR

    summary = run.get("summary") or {}
    pnl, days, sharpe = summary.get("pnl"), summary.get("days"), summary.get("sharpe_daily")
    sd = None
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (pnl, days, sharpe)) and days and sharpe:
        sd = abs((float(pnl) / float(days)) / float(sharpe))  # sigma_P = mean daily P&L / the daily Sharpe
    market = DIR.market_returns(closes, _roots(store, fam, n), validation_days)
    kept = isinstance(verdict, Mapping)
    return {"family": fam["id"], "version": n, "window": "validation", "passed": bool(verdict.get("passed")) if kept else None,
            "verdict_kept": kept, "at": run.get("at"), "verdict_at": verdict.get("at") if kept else None, "pnl": pnl,
            "bh": DIR.same_risk_bh(sd, market), "drift_train": DIR.train_fit(store, fam, n)}


def _part(values: list[float], seed: str, level: float) -> dict[str, Any]:
    from .. import stats
    from ..swarm import evidence

    boot = evidence.block_bootstrap(values, seed=seed, draws=evidence.BOOTSTRAP_DRAWS)
    pnl = sum(values)
    return {"days": len(values), "pnl": round(pnl, 2), "sharpe_daily": stats.sharpe(values) if len(values) >= 2 else None,
            "p": boot["p"] if boot else None, "passes_level": bool(boot is not None and boot["p"] <= level and pnl > 0)}


def contamination(daily: Mapping[str, float], *, seed: str) -> dict[str, Any]:
    """Measure 1 (the module docstring): the holdout daily series split at the contamination tail's first day."""
    from ..swarm import evidence

    cut, level = evidence.CONTAMINATION_TAIL_FROM, evidence.LOOK_LEVEL
    head = [x for d, x in sorted(daily.items()) if d < cut]
    tail = [x for d, x in sorted(daily.items()) if d >= cut]
    out = {"from": cut, "level": level, "head": _part(head, f"{seed}:head", level), "tail": _part(tail, f"{seed}:tail", level)}
    a, b = out["head"]["sharpe_daily"], out["tail"]["sharpe_daily"]
    out["sharpe_gap"] = (a - b) if a is not None and b is not None else None
    return out


def look_row(store: Any, fam: Mapping[str, Any] | None, look: Mapping[str, Any], closes: Mapping) -> dict[str, Any]:
    from . import direction as DIR

    fid, n = look["family"], int(look["version"])
    numbers = ((look.get("detail") or {}).get("numbers") or {})
    row = {"family": fid, "version": n, "window": "holdout", "passed": bool(look["passed"]), "at": look.get("at"),
           "pnl": numbers.get("pnl"), "p": look.get("p_value"), "level": numbers.get("level"), "rule": numbers.get("rule"),
           "tail": numbers.get("tail")}
    daily: dict[str, float] = {}
    for run in store.version_runs(fid, n, window="holdout", stress=1.0, limit=5):
        result = store.run_result(str(run["run_id"])) or {}
        for d in result.get("daily") or []:
            if isinstance(d, (list, tuple)) and len(d) >= 2 and isinstance(d[1], (int, float)) and not isinstance(d[1], bool):
                daily[str(d[0])[:10]] = daily.get(str(d[0])[:10], 0.0) + float(d[1])
        if daily:
            break
    roots = _roots(store, fam, n) if fam else ()
    market = DIR.market_returns(closes, roots, sorted(daily))
    row["bh"] = DIR.same_risk_bh(_sd(list(daily.values())), market) if daily else {"usd": None, "why": "no holdout daily series"}
    row["drift_window"] = DIR.daily_fit(daily, market)
    row["drift_train"] = DIR.train_fit(store, fam, n) if fam else None
    row["contamination"] = (contamination(daily, seed=f"report:{fid}:{n}") if daily
                            else {"why": "no holdout daily series"})
    return row


def pooled_contamination(screen: list[dict]) -> dict[str, Any]:
    """Measure 2 (the module docstring): over every look row with a daily series."""
    rows = [r for r in screen if r.get("window") == "holdout" and isinstance((r.get("contamination") or {}).get("head"), Mapping)]
    gaps = [float(r["contamination"]["sharpe_gap"]) for r in rows if r["contamination"].get("sharpe_gap") is not None]
    mean = statistics.fmean(gaps) if gaps else None
    se = statistics.stdev(gaps) / math.sqrt(len(gaps)) if len(gaps) >= 2 else None
    out = {"looks": len(rows), "with_gap": len(gaps), "mean_sharpe_gap": mean, "se": se,
           "t": (mean / se) if mean is not None and se else None,
           "head_pass_share": (sum(1 for r in rows if r["contamination"]["head"]["passes_level"]) / len(rows)) if rows else None,
           "tail_pass_share": (sum(1 for r in rows if r["contamination"]["tail"]["passes_level"]) / len(rows)) if rows else None,
           "reading": ("head = the holdout's sessions inside Opus 5.5's training (to 2026-06-30), tail = after it; a positive "
                       "mean gap or a head pass share above the tail's is what contamination would show; low power"),
           "reported_only": True}
    return out


# ------------------------------------------------------------------------------------------------- band rows
def band_row(store: Any, fam: Mapping[str, Any], screen: list[dict], closes: Mapping, today: str) -> dict[str, Any]:
    from ..live import money as M
    from . import direction as DIR

    state = fam.get("state") or {}
    n = state.get("banded_version")
    out: dict[str, Any] = {"family": fam["id"], "band": fam["band"], "version": n,
                           "screen": [r for r in screen if r["family"] == fam["id"] and r["version"] == n]}
    rows = store.forward(fam["id"])
    real = [r for r in rows if r.get("source") == "real" and n is not None and r.get("version") == int(n)]
    promoted = state.get("live_promoted_at")
    first = (datetime.fromtimestamp(float(promoted), _ny()).date().isoformat() if isinstance(promoted, (int, float))
             else min((str(r["day"]) for r in real), default=today))
    days = DIR.sessions(first, today) if first <= today else []
    by_day = {d: 0.0 for d in days}
    for r in real:
        by_day[str(r["day"])] = by_day.get(str(r["day"]), 0.0) + float(r["pnl"])
    market = DIR.market_returns(closes, _roots(store, fam, int(n)) if n is not None else fam.get("roots") or (), sorted(by_day))
    from ..live.families import validation_r_sd

    table = M.Table.from_constitution()
    fwd = M.forward_stats(rows, table.sized_confidence, version=n)
    out["live"] = {"realized_usd": round(sum(float(r["pnl"]) for r in real), 2), "trades": len(real), "sessions": len(days),
                   "since": first, "bh": DIR.same_risk_bh(_sd(list(by_day.values())), market),
                   "drift_window": DIR.daily_fit(by_day, market)}
    # Measure 3 (the module docstring): live is after every author's training.
    risk = sum(float(r.get("max_loss") or 0.0) for r in real if float(r.get("max_loss") or 0.0) > 0)
    holdout = store.version_runs(fam["id"], int(n), window="holdout", stress=1.0, limit=1) if n is not None else []
    held = (holdout[0].get("summary") or {}).get("pnl_per_max_loss") if holdout else None
    live = (sum(float(r["pnl"]) for r in real) / risk) if risk > 0 else None
    out["live_vs_holdout"] = {"live_pnl_per_max_loss": live, "holdout_pnl_per_max_loss": held,
                              "gap": (float(held) - live) if live is not None and isinstance(held, (int, float)) else None,
                              "trades": len(real)}
    # The demotion in force for its band (release L-D: `probe.demotion`; DM1 reads the Validation sd the live row reads).
    sd = validation_r_sd(state, n)
    out["d5"] = {"demoted": M.live_demotion(table, str(fam["band"]), fwd, sd), "rule": table.probe_demotion,
                 "real_pnl": fwd.real_pnl, "real_max_loss": fwd.real_max_loss, "replay_gap": fwd.replay_gap,
                 "replay_n": fwd.replay_n, "real_n": fwd.real_n, "real_r_sum": fwd.real_r_sum,
                 "sigma": M.dm1_sigma(fwd, sd)[0] if table.probe_demotion == "dm1" else None}
    return out


#: The probe budget's `realized_basis` label for each `probe.loss_basis` (release L-D: the basis in force, never a fixed
#: "gross" beside a net figure).
REALIZED_BASIS = {
    "gross": "gross: each closed Probe position's own loss",
    "net": "net: the closed Probe positions' losses less their gains, from inception, floored at $0 (a Sized gain never counts)",
}


def probe_budget(live_path: str | Path, today: str) -> dict[str, Any]:
    from ..live import money as M
    from ..live.real import probe_figures

    with closing(sqlite3.connect(f"file:{Path(live_path)}?mode=ro", uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row

        def rows(sql: str, params: tuple = ()) -> list[dict]:
            return [dict(r) for r in db.execute(sql, params)]

        table = M.Table.from_constitution()
        # The figures `RealBook.exposure` gives `money.plan_open` (release L-D: the window's and the total's).
        open_n, window, total, at_risk, since = probe_figures(rows, day=today, table=table)
    rooms = {"window": table.probe_loss_budget - window - at_risk, "total": table.probe_loss_total - total - at_risk}
    binding = min(rooms, key=lambda k: (rooms[k], k != "window"))
    return {"realized_usd": str(M.cents(window)), "realized_total_usd": str(M.cents(total)),
            "realized_basis": REALIZED_BASIS[table.probe_loss_basis], "window_sessions": table.probe_loss_window,
            "window_start": since,
            "at_risk_usd": str(M.cents(at_risk)), "open": open_n, "max_open": table.probe_max_open,
            "budget_usd": str(table.probe_loss_budget), "total_budget_usd": str(table.probe_loss_total),
            "room_usd": str(M.cents(max(M.ZERO, rooms[binding]))), "binding": binding}


def report(swarm_root: str | Path, live_path: str | Path | None, closes_path: str | Path, *, since: str | None = None,
           today: str | None = None) -> dict[str, Any]:
    """The report (the module docstring), from the swarm store at `swarm_root` (opened read-only), the live state at
    `live_path` (read-only; None leaves the budget out) and the closes file."""
    from ..swarm.store import SwarmStore
    from . import direction as DIR

    today = today or datetime.now(_ny()).date().isoformat()
    closes = DIR.load_closes(closes_path)
    validation_days = DIR.sessions(*VALIDATION)
    store = SwarmStore(Path(swarm_root), readonly=True)
    try:
        families = {f["id"]: f for f in store.families()}
        screen: list[dict] = []
        for fam in families.values():
            verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
            for n, run in sorted(validation_runs(store, fam["id"], since).items()):
                verdict = verdicts.get(str(n)) if isinstance(verdicts, Mapping) else None
                screen.append(validation_row(store, fam, n, run, verdict, closes, validation_days))
        for look in store.looks():
            if since is None or str(look.get("at") or "") >= since:
                screen.append(look_row(store, families.get(look["family"]), look, closes))
        bands = [band_row(store, fam, screen, closes, today) for fam in families.values()
                 if fam.get("band") in ("candidate", "probe", "sized") and not fam.get("retired_at")]
    finally:
        store.close()
    out: dict[str, Any] = {"at": today, "since": since, "closes": str(closes_path), "screen": screen,
                           "contamination": pooled_contamination(screen), "bands": bands, "reported_only": True}
    out["probe_budget"] = probe_budget(live_path, today) if live_path else None
    return out


# ------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    from . import direction as DIR
    from . import guard
    from .context import write_json

    root = Path(ctx.root)
    now = datetime.fromtimestamp(ctx.now(), _ny())
    today = now.date().isoformat()
    since = (now - timedelta(days=JOB_DAYS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    live = root / "live.sqlite"
    with guard.readonly():
        out = report(root, live if live.exists() else None, root / DIR.FILE, since=since, today=today)
    out["window_days"] = JOB_DAYS
    write_json(root / FILE, out)
    bare = sorted({b["family"] for b in out["bands"] if b["band"] in ("probe", "sized")
                   and not any(r["window"] == "holdout" and (r.get("bh") or {}).get("usd") is not None for r in b["screen"])})
    if bare:
        ctx.alert("warning", f"fast lane: {len(bare)} Probe or Sized families have no same-risk buy-and-hold beside their "
                             f"holdout look (the direction job's closes lack their days): {', '.join(bare[:8])}")
    return {"ok": True, "screen": len(out["screen"]), "bands": len(out["bands"]), "looks": out["contamination"]["looks"],
            "without_bh": len(bare)}


__all__ = ["run", "report", "FILE", "JOB_DAYS", "contamination", "pooled_contamination", "validation_runs"]
