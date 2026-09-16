#!/usr/bin/env python3
"""Backtest a strategy against Kalshi and Coinbase history, from this machine.

    python3 scripts/backtest.py --strategy kalshi_favorites --days 3
    python3 scripts/backtest.py --strategy hourly_ranges --params '{"series": ["KXBTCD", "KXETHD"]}' --days 2 --step-minutes 5
    python3 scripts/backtest.py --strategy mine --code path/to/mine.py --end 2026-09-15T00:00:00Z --days 1

Prints a readable summary, then the report as JSON (its `split` is in and out of sample).
Progress goes to stderr. Settled history is cached under `.data/history-cache` (128 MB cap).
Public market data only; no keys are read.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ltcm.backtest import iso, run_backtest, split_report  # noqa: E402
from ltcm.history import History  # noqa: E402


def summary(report: dict, split: dict) -> str:
    def money(value):
        return "n/a" if value is None else f"${value:,.2f}"

    lo, hi = report.get("ci95_mean_pnl") or [None, None]
    lines = [
        f"{report.get('strategy')}  {report.get('start')} -> {report.get('end')}  ({report.get('steps')} steps, fill model {report.get('fill_model')})",
        f"  trades {report.get('trades')}  fills {report.get('fills')} ({report.get('maker_fills', 0)} maker)  "
        f"settled {report.get('settled')}  wins {report.get('wins')}",
        f"  notional {money(report.get('notional_usd'))}  pnl {money(report.get('pnl_usd'))} "
        f"(realized {money(report.get('realized_pnl_usd'))}, unrealized {money(report.get('unrealized_pnl_usd'))})  "
        f"fees {money(report.get('fees_usd'))}",
        f"  return on notional {report.get('return_on_notional')}  max drawdown {money(report.get('max_drawdown_usd'))}  "
        f"mean trade pnl 95% CI [{lo}, {hi}]",
        f"  in sample: {split['in_sample']}",
        f"  out of sample: {split['out_of_sample']}",
        f"  orders {report.get('orders')}  rejected {report.get('rejected')}  cancelled {report.get('cancelled')}  "
        f"expired {report.get('expired')}  errors {report.get('errors')}",
        f"  markets {report.get('markets_priced')}/{report.get('markets_loaded')} priced  "
        f"http requests {report.get('http_requests')} (cache hits {report.get('cache_hits')})  "
        f"runtime {report.get('runtime_seconds')}s",
    ]
    if report.get("unsupported"):
        lines.append(f"  UNSUPPORTED: {report['unsupported']}")
    for day in report.get("daily") or []:
        lines.append(f"  {day['day']}: {day['trades']} trades, {money(day['pnl_usd'])}")
    for note in report.get("notes") or []:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strategy", required=True, help="a starter name (ltcm/starters) or the name for --code")
    parser.add_argument("--code", help="a strategy source file (default: ltcm/starters/<strategy>.py)")
    parser.add_argument("--params", default="{}", help="strategy params as JSON")
    parser.add_argument("--days", type=float, default=2.0, help="window length in days, ending at --end")
    parser.add_argument("--end", help="ISO-8601 UTC end (default: now, floored to the step)")
    parser.add_argument("--step-minutes", type=float, default=15.0)
    parser.add_argument("--series", nargs="*", help="Kalshi series to load (default: the strategy's own)")
    parser.add_argument("--products", nargs="*", help="Coinbase products for kit.products()")
    parser.add_argument("--learning-usd", type=float, default=10.0)
    parser.add_argument("--max-markets", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-seconds", type=float, default=0.0, help="wall-clock budget (0: none)")
    parser.add_argument("--fill-model", default="conservative", choices=("conservative", "touch"),
                        help="touch: resting orders also fill on a touch or a print (the optimistic bracket)")
    parser.add_argument("--cache-dir", default=str(ROOT / ".data" / "history-cache"))
    parser.add_argument("--json-only", action="store_true", help="print only the report JSON")
    args = parser.parse_args(argv)

    step = int(args.step_minutes * 60)
    end_ts = int(time.time()) // step * step if not args.end else None
    end = args.end or iso(end_ts)
    from ltcm.backtest import parse_time

    start = iso(parse_time(end) - args.days * 86400)
    spec = {
        "strategy": args.strategy,
        "params": json.loads(args.params),
        "start": start,
        "end": end,
        "step_minutes": args.step_minutes,
        "learning_usd": args.learning_usd,
        "max_markets": args.max_markets,
        "seed": args.seed,
        "max_seconds": args.max_seconds,
        "fill_model": args.fill_model,
    }
    if args.code:
        spec["code"] = Path(args.code).read_text(encoding="utf-8")
    if args.series:
        spec["series"] = args.series
    if args.products:
        spec["products"] = args.products
    history = History(cache_dir=args.cache_dir)
    # --code is a file on this machine that the operator chose to run here; a model's code runs
    # in a desk's sandbox instead (python3 -m ltcm.backtest there).
    report = run_backtest(spec, history=history, trusted_code=bool(args.code))
    split = report.get("split") or split_report(report)
    if not args.json_only:
        print(summary(report, split))
        print()
    print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
