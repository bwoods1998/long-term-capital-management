"""FAST LANE V2's report (Oct 7, 2026; D2 and D4): the drift fit and the same-risk buy-and-hold beside every screen result
and every band row, the D5 status of every live band, and the Probe loss budget. REPORTED, NEVER A BAR: nothing in the
tournament, the gate, the bands or the money table reads any of it (`league/tests/test_fast_lane_v2.py` pins that).

    python scripts/fast_lane_report.py --swarm-root COPY --live LIVE_COPY --closes direction-closes.json [--since ISO]

It opens COPIES only (the swarm store read-only, the live state's copy read-only) and never the House's live files.
It prints JSON:
- `screen`: one row for every Validation verdict since `--since` (pass or fail; `validation_verdicts`) and every holdout
  look: family, version, window, passed, pnl, `bh` (the same-risk buy-and-hold, `league/ops/direction.py`),
  `drift_train` (the Gym's own Train fit); a look adds `drift_window` (the daily-close fit on its holdout daily P&L) and
  its `tail` (the contamination tail from 2026-07-01, `evidence.CONTAMINATION_TAIL_FROM`).
- `bands`: every Candidate, Probe or Sized family: its banded version's screen rows; its live realized P&L (forward rows,
  source "real", that version, net of fees) with `bh` and `drift_window` over its live sessions since `live_promoted_at`
  (zeros included); its D5 status (`money.demotion`).
- `probe_budget`: `real.probe_tally` on the live copy: realized, at risk, open count, the room left of the budget.
The captain's daily funnel report quotes it.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
VALIDATION = ("2025-01-02", "2025-12-31")


def _sd(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _roots(store: Any, fam: Mapping[str, Any], n: int) -> tuple[str, ...]:
    from league.swarm.researcher import needs_roots

    version = store.version(fam["id"], n) or {}
    return needs_roots(version.get("code"), fam.get("roots") or ())


def validation_row(store: Any, fam: Mapping[str, Any], n: int, verdict: Mapping[str, Any], closes: Mapping,
                   validation_days: list[str]) -> dict[str, Any]:
    from league.ops import direction as DIR

    runs = store.version_runs(fam["id"], n, window="validation", stress=1.0, limit=1)
    summary = (runs[0].get("summary") or {}) if runs else {}
    pnl, days, sharpe = summary.get("pnl"), summary.get("days"), summary.get("sharpe_daily")
    sd = None
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (pnl, days, sharpe)) and days and sharpe:
        sd = abs((float(pnl) / float(days)) / float(sharpe))  # sigma_P = mean daily P&L / the daily Sharpe
    market = DIR.market_returns(closes, _roots(store, fam, n), validation_days)
    return {"family": fam["id"], "version": n, "window": "validation", "passed": bool(verdict.get("passed")),
            "at": verdict.get("at"), "pnl": pnl, "bh": DIR.same_risk_bh(sd, market),
            "drift_train": DIR.train_fit(store, fam, n)}


def look_row(store: Any, fam: Mapping[str, Any] | None, look: Mapping[str, Any], closes: Mapping) -> dict[str, Any]:
    from league.ops import direction as DIR

    fid, n = look["family"], int(look["version"])
    numbers = ((look.get("detail") or {}).get("numbers") or {})
    row = {"family": fid, "version": n, "window": "holdout", "passed": bool(look["passed"]), "at": look.get("at"),
           "pnl": numbers.get("pnl"), "p": look.get("p_value"), "level": numbers.get("level"), "rule": numbers.get("rule"),
           "tail": numbers.get("tail")}
    daily: dict[str, float] = {}
    for run in store.version_runs(fid, n, window="holdout", stress=1.0, limit=5):
        result = store.run_result(str(run["run_id"])) or {}
        for d in result.get("daily") or []:
            if isinstance(d, (list, tuple)) and len(d) >= 2 and isinstance(d[1], (int, float)):
                daily[str(d[0])[:10]] = daily.get(str(d[0])[:10], 0.0) + float(d[1])
        if daily:
            break
    roots = _roots(store, fam, n) if fam else ()
    market = DIR.market_returns(closes, roots, sorted(daily))
    row["bh"] = DIR.same_risk_bh(_sd(list(daily.values())), market) if daily else {"usd": None, "why": "no holdout daily series"}
    row["drift_window"] = DIR.daily_fit(daily, market)
    row["drift_train"] = DIR.train_fit(store, fam, n) if fam else None
    return row


def band_row(store: Any, fam: Mapping[str, Any], screen: list[dict], closes: Mapping, today: str) -> dict[str, Any]:
    from league.live import money as M
    from league.ops import direction as DIR

    state = fam.get("state") or {}
    n = state.get("banded_version")
    out: dict[str, Any] = {"family": fam["id"], "band": fam["band"], "version": n,
                           "screen": [r for r in screen if r["family"] == fam["id"] and r["version"] == n]}
    rows = store.forward(fam["id"])
    real = [r for r in rows if r.get("source") == "real" and n is not None and r.get("version") == int(n)]
    promoted = state.get("live_promoted_at")
    first = (datetime.fromtimestamp(float(promoted), NEW_YORK).date().isoformat() if isinstance(promoted, (int, float))
             else min((str(r["day"]) for r in real), default=today))
    days = DIR.sessions(first, today) if first <= today else []
    by_day = {d: 0.0 for d in days}
    for r in real:
        by_day[str(r["day"])] = by_day.get(str(r["day"]), 0.0) + float(r["pnl"])
    market = DIR.market_returns(closes, _roots(store, fam, int(n)) if n is not None else fam.get("roots") or (), sorted(by_day))
    table = M.Table.from_constitution()
    fwd = M.forward_stats(rows, table.sized_confidence, version=n)
    out["live"] = {"realized_usd": round(sum(float(r["pnl"]) for r in real), 2), "trades": len(real), "sessions": len(days),
                   "since": first, "bh": DIR.same_risk_bh(_sd(list(by_day.values())), market),
                   "drift_window": DIR.daily_fit(by_day, market)}
    out["d5"] = {"demoted": M.demotion(fwd), "real_pnl": fwd.real_pnl, "real_max_loss": fwd.real_max_loss,
                 "replay_gap": fwd.replay_gap, "replay_n": fwd.replay_n}
    return out


def probe_budget(live_path: str | Path, today: str) -> dict[str, Any]:
    from datetime import date

    from league.live import money as M
    from league.live.real import probe_tally

    day = date.fromisoformat(today)
    week_start = (day - timedelta(days=day.weekday())).isoformat()
    with closing(sqlite3.connect(f"file:{Path(live_path)}?mode=ro", uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row

        def rows(sql: str, params: tuple = ()) -> list[dict]:
            return [dict(r) for r in db.execute(sql, params)]

        open_n, realized, at_risk = probe_tally(rows, week_start=week_start)
    table = M.Table.from_constitution()
    return {"realized_usd": str(M.cents(realized)), "at_risk_usd": str(M.cents(at_risk)), "open": open_n,
            "max_open": table.probe_max_open, "budget_usd": str(table.probe_loss_budget),
            "room_usd": str(M.cents(max(M.ZERO, table.probe_loss_budget - realized - at_risk)))}


def report(swarm_root: str | Path, live_path: str | Path | None, closes_path: str | Path, *, since: str | None = None,
           today: str | None = None) -> dict[str, Any]:
    from league.ops import direction as DIR
    from league.swarm.store import SwarmStore

    today = today or datetime.now(NEW_YORK).date().isoformat()
    closes = DIR.load_closes(closes_path)
    validation_days = DIR.sessions(*VALIDATION)
    store = SwarmStore(Path(swarm_root), readonly=True)
    try:
        families = {f["id"]: f for f in store.families()}
        screen: list[dict] = []
        for fam in families.values():
            verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
            for n, verdict in sorted(verdicts.items(), key=lambda kv: int(kv[0])):
                if isinstance(verdict, Mapping) and (since is None or str(verdict.get("at") or "") >= since):
                    screen.append(validation_row(store, fam, int(n), verdict, closes, validation_days))
        for look in store.looks():
            if since is None or str(look.get("at") or "") >= since:
                screen.append(look_row(store, families.get(look["family"]), look, closes))
        bands = [band_row(store, fam, screen, closes, today) for fam in families.values()
                 if fam.get("band") in ("candidate", "probe", "sized") and not fam.get("retired_at")]
    finally:
        store.close()
    out: dict[str, Any] = {"at": today, "since": since, "closes": str(closes_path), "screen": screen, "bands": bands,
                           "reported_only": True}
    out["probe_budget"] = probe_budget(live_path, today) if live_path else None
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--swarm-root", required=True, help="a COPY of the swarm's state root")
    parser.add_argument("--live", help="a COPY of live.sqlite")
    parser.add_argument("--closes", required=True, help="direction-closes.json (league/ops/direction.py)")
    parser.add_argument("--since", help="ISO time: Validation verdicts and looks from it")
    args = parser.parse_args(argv)
    print(json.dumps(report(args.swarm_root, args.live, args.closes, since=args.since), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the checkout's own league package
    raise SystemExit(main())
