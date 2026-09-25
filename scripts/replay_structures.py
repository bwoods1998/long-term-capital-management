#!/usr/bin/env python3
"""Replay an options strategy (structures or single contracts) over a LOCAL copy of the options
history, the way the House would judge it, and print what the House would decide.

    python3 scripts/replay_structures.py league/seeds/options_condor.py
    python3 scripts/replay_structures.py STRATEGY.py --from 2026-08-25 --to 2026-09-24 --params '{"width": 2}' --json

Built Sept 25, 2026 for the options-desk run (builder S3) so the structure founders are judged off the
House box. The same pieces the House uses, in the same order (`House._run_replay`):

- NEEDS held to the `alpaca-options` specialty (`niches.constrain`), PARAMS checked by
  `parameters.require_valid`, the code by `safety.check_code`;
- the window of `House._live_window` (`replay_days` of `league/config.json` days back from the end, six
  times that for a daily strategy), starting after the sealed holdout (`deep_replay.HOLDOUT`);
- the tape of `House.tape_for` (`OptionsHistory.tape`, 15-minute execution bars, warmup = the NEEDS'
  bar limit, the order cap of practice rung 1), with the underlyings' bars read from the local copy
  (`stored_underlier`) instead of the gateway;
- the replay the agent's box runs (`replay.run_replay`), at the practice rung's stake and caps;
- the replay gate the evaluator applies (`Evaluator.replay_gate`: closed trades, blocks,
  out-of-sample growth above the constitution's floor, deflated Sharpe) against a throwaway ledger,
  so the family has no earlier trials: a first look.

It prints pass/fail and the reasons, trades and closed structures, growth over the window, and
out-of-sample growth: the mean log growth a block of the last third (the replay's own split,
`oos_fraction` 0.34) against the first two thirds (the fit window). Nothing touches the House.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league import options_history as oh  # noqa: E402
from league import parameters  # noqa: E402
from league.agents import niche_of  # noqa: E402
from league.constitution import CONSTITUTION  # noqa: E402
from league.deep_replay import HOLDOUT  # noqa: E402
from league.evaluator import Evaluator  # noqa: E402
from league.ledger import Ledger  # noqa: E402
from league.niches import constrain, load as load_niches  # noqa: E402
from league.replay import run_replay  # noqa: E402
from league.safety import check_code  # noqa: E402
from league.service import load_config  # noqa: E402

DEFAULT_HISTORY = Path.home() / "Work" / ".options-history" / "options_history.sqlite"
OOS_FRACTION = 0.34  # `replay.run_replay`'s default, the House's


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(text: str, *, end: bool = False) -> float:
    text = text.strip()
    if len(text) == 10:
        text += "T23:59:59Z" if end else "T00:00:00Z"
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def declared(code: str) -> tuple[dict, dict]:
    """The strategy's NEEDS and PARAMS, read the way the replay reads them (the module run once)."""
    namespace: dict = {"__name__": "strategy"}
    exec(compile(code, "<strategy>", "exec"), namespace)  # noqa: S102 - a local strategy file, checked by check_code first
    return dict(namespace.get("NEEDS") or {}), dict(namespace.get("PARAMS") or {})


def window(needs: dict, start: str | None, end: str | None, last_bar: float) -> tuple[str, str]:
    """`House._live_window` ending at `end` (default: the last underlier bar in the copy), clamped to
    start after the sealed holdout, as `House.tape_for` does for an options tape."""
    _, horizon, _ = niche_of(needs)
    end_ts = _stamp(end, end=True) if end else last_bar
    days = int(load_config().get("replay_days", 21)) * (6 if horizon == "day" else 1)
    start_ts = _stamp(start) if start else end_ts - days * 86400
    after_holdout = datetime.fromisoformat(HOLDOUT[1]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    return max(_iso(start_ts), after_holdout.strftime("%Y-%m-%dT%H:%M:%SZ")), _iso(end_ts)


def judge(result: dict, family: str) -> tuple[bool, list[str]]:
    """The evaluator's replay gate on a throwaway ledger (no earlier trials in the family)."""
    with tempfile.TemporaryDirectory(prefix="replay-structures-") as root:
        ledger = Ledger(Path(root) / "ledger.sqlite")
        try:
            return Evaluator(ledger).replay_gate(family, result)
        finally:
            if hasattr(ledger, "close"):
                ledger.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("strategy", help="a strategy file (league/CONTRACT.md)")
    parser.add_argument("--from", dest="start", default=None, help="ISO start (default: the House's window)")
    parser.add_argument("--to", dest="end", default=None, help="ISO end (default: the copy's last bar)")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY), help="the local options history copy")
    parser.add_argument("--params", default="", help="JSON PARAMS overriding the file's (an edit replay)")
    parser.add_argument("--stress", type=float, default=1.0, help="execution stress: multiplies what fills pay")
    parser.add_argument("--scale", type=float, default=1.0, help="the book's size against practice rung 1 (0.5: an edit replay)")
    parser.add_argument("--niche", default="alpaca-options")
    parser.add_argument("--json", action="store_true", help="print the whole summary as JSON")
    parser.add_argument("--trades", action="store_true", help="print every closed trade")
    args = parser.parse_args(argv)

    code = Path(args.strategy).read_text(encoding="utf-8")
    try:
        check_code(code)
    except Exception as exc:  # noqa: BLE001 - CodeRefused says why
        print(f"REFUSED by the safety check: {exc}")
        return 2
    needs, defaults = declared(code)
    needs = constrain(needs, load_niches()[args.niche])
    params = {**defaults, **(json.loads(args.params) if args.params else {})}
    parameters.require_valid(params, needs)
    mutable = parameters.inspect(params, needs)["mutable"]
    _, horizon, _ = niche_of(needs)

    store = oh.OptionsHistory(args.history)
    underlier = oh.stored_underlier(store)
    last = store.db.execute("SELECT MAX(ts) FROM underlier_bars WHERE timeframe = '15Min'").fetchone()[0]
    start_iso, end_iso = window(needs, args.start, args.end, float(last))
    rung = CONSTITUTION["rungs"]["1"]
    stake = float(rung["stake_usd"]) * args.scale
    limits = {"max_position_usd": float(rung["max_position_usd"]) * args.scale, "max_order_usd": float(rung["max_order_usd"]) * args.scale}
    warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
    t0 = time.time()
    tape = store.tape(needs, start_iso, end_iso, horizon=horizon, warmup=warmup, execution="15Min", underlier_bars=underlier,
                      max_order_usd=float(rung["max_order_usd"]))
    tape["spread_model"]["stress"] = args.stress
    built = time.time() - t0
    size_mb = len(json.dumps(tape, separators=(",", ":"))) / 1e6
    t0 = time.time()
    result = run_replay(code, params, tape, stake=stake, limits=limits, oos_fraction=OOS_FRACTION, audit=args.trades)
    ran = time.time() - t0
    passed, reasons = judge(result, str(needs.get("style") or Path(args.strategy).stem)) if result.get("ok") else (False, [f"the replay failed: {result.get('error')}"])

    blocks = result.get("blocks") or []
    growth = sum(float(b["log_growth"]) for b in blocks)
    ins, oos = result.get("in_sample") or {}, result.get("out_of_sample") or {}
    options = result.get("options") or {}
    summary = {
        "strategy": args.strategy, "window": [start_iso, end_iso], "horizon": horizon, "symbols": needs.get("symbols"),
        "structures": bool(needs.get("structures")), "params": params, "mutable_params": mutable,
        "tape": {"steps": len(tape["steps"]), "contracts": len(tape["contracts"]), "json_mb": round(size_mb, 1),
                 "recorded_quotes": tape.get("recorded_quotes"), "build_seconds": round(built, 1)},
        "replay_seconds": round(ran, 1), "ok": result.get("ok"), "error": result.get("error"),
        "gate": {"passed": passed, "reasons": reasons, "floor": CONSTITUTION["ladder"]["replay"]},
        "trades": result.get("trades"), "structures_opened": (options.get("structures") or {}).get("opened"),
        "structures_closed": (options.get("structures") or {}).get("closed"),
        "settled_at_expiry": (options.get("structures") or {}).get("settled_at_expiry"),
        "not_evaluated": (options.get("structures") or {}).get("not_evaluated"),
        "house_close_offers": (options.get("structures") or {}).get("house_close_offers"),
        "fills": result.get("fills"), "fees_usd": result.get("fees_usd"), "refused": result.get("refused"),
        "refusal_reasons": result.get("refusal_reasons"), "final_equity": result.get("final_equity"), "stake": stake,
        "return_pct": result.get("return_pct"), "max_drawdown": result.get("max_drawdown"),
        "blocks": len(blocks), "growth": round(growth, 6), "growth_pct": round((math.exp(growth) - 1) * 100, 3),
        "fit_window": {"blocks": ins.get("blocks"), "mean_log_growth": ins.get("mean_log_growth")},
        "out_of_sample": {"blocks": oos.get("blocks"), "active_blocks": oos.get("active_blocks"), "mean_log_growth": oos.get("mean_log_growth")},
        "digest": (result.get("digest") or {}).get("all"), "by_underlying": (result.get("digest") or {}).get("by_group"),
    }
    if args.trades:
        summary["fill_log"] = result.get("fill_log")
    if args.json:
        print(json.dumps(summary, indent=1, default=str))
        return 0 if passed else 1
    print(f"{args.strategy}: {'PASS' if passed else 'FAIL'}  ({horizon}, {', '.join(needs.get('symbols') or [])}, {start_iso} .. {end_iso})")
    for reason in reasons:
        print(f"  - {reason}")
    print(f"  trades (closed structures) {summary['trades']}  opened {summary['structures_opened']}  settled at expiry "
          f"{summary['settled_at_expiry']}  not evaluated {summary['not_evaluated']}  fills {summary['fills']}  fees ${summary['fees_usd']}")
    print(f"  equity {stake:.2f} -> {summary['final_equity']:.2f} ({summary['return_pct']:+.3f}%), max drawdown {summary['max_drawdown']:.4f}")
    print(f"  growth {growth:+.6f} over {len(blocks)} blocks; fit window {ins.get('mean_log_growth')} a block over {ins.get('blocks')}; "
          f"OUT OF SAMPLE {oos.get('mean_log_growth')} a block over {oos.get('blocks')} ({oos.get('active_blocks')} active)")
    print(f"  refused {summary['refused']}: {json.dumps(summary['refusal_reasons'])[:400]}")
    print(f"  tape: {summary['tape']['steps']} steps, {summary['tape']['contracts']} contracts, {summary['tape']['json_mb']} MB, "
          f"built in {summary['tape']['build_seconds']} s; replay {summary['replay_seconds']} s")
    print(f"  mutable PARAMS (edit replay, lab): {mutable}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
