"""Reproducible synthetic checks of the statistical research gates, without market data or writes to the swarm.

These are generated daily cash outcomes, not a simulated trading edge. They exercise the real summary, Train,
Validation, and holdout arithmetic. They do not certify fills, drift adjustment, program safety, or profitability.
Development and confirmation cohorts use independent deterministic streams. Protocol/source hashes make reports
comparable without silently changing the question; this module never changes thresholds or promotes a family.

    python -m league.swarm.benchmarks --replications 32 --output /private/path/report.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any

from .. import stats
from ..gym import results
from . import evidence

PROTOCOL = {
    "id": "statistical-gates-1",
    "sessions": 252,
    "train_years": [2022, 2023, 2024],
    "validation_year": 2025,
    "holdout_year": 2026,
    "daily_noise_sd": 8.0,
    "spread_usd": 0.9,
    "fees_usd": 0.1,
    "max_loss_usd": 100.0,
    "validated_versions": 1,
    "cases": {
        "absent_signal": {"gross_edge": 0.0, "stride": 1, "expectation": "negative_control"},
        "planted_edge": {"gross_edge": 6.0, "stride": 1, "expectation": "positive_control"},
        "cost_erased_edge": {"gross_edge": 0.5, "stride": 1, "expectation": "negative_control"},
        "edge_disappears": {"gross_edge": 6.0, "holdout_edge": 0.0, "stride": 1, "expectation": "negative_control"},
        "positive_sparse": {"gross_edge": 6.0, "stride": 10, "expectation": "frequency_diagnostic"},
    },
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def generated(case: str, cohort: str, replication: int, years: list[int], *, stress: float = 1.0,
              copies: int = 1) -> dict[str, Any]:
    """Invent outcomes; stress shares the same gross stream and charges extra spread. Copies split lots, not days."""
    if case not in PROTOCOL["cases"] or cohort not in ("development", "confirmation"):
        raise ValueError("unknown case or cohort")
    if replication < 0 or copies < 1 or stress < 0:
        raise ValueError("invalid simulation parameters")
    spec = PROTOCOL["cases"][case]
    trades, daily = [], []
    for year in years:
        rng = random.Random(digest([PROTOCOL["id"], cohort, case, replication, year]))
        day = dt.date(year, 1, 1)
        for index in range(PROTOCOL["sessions"]):
            while day.weekday() >= 5:
                day += dt.timedelta(days=1)
            stamp = day.isoformat()
            # This is a synthetic weekday calendar, not an exchange-calendar claim.
            edge = spec.get("holdout_edge", spec["gross_edge"]) if year == PROTOCOL["holdout_year"] else spec["gross_edge"]
            gross = rng.gauss(edge, PROTOCOL["daily_noise_sd"])
            pnl = 0.0
            if index % spec["stride"] == 0:
                pnl = gross - PROTOCOL["spread_usd"] * stress - PROTOCOL["fees_usd"]
                for _ in range(copies):
                    risk = PROTOCOL["max_loss_usd"] / copies
                    trades.append({"day": stamp, "pnl": pnl / copies, "max_loss": risk,
                                   "return_on_max_loss": pnl / PROTOCOL["max_loss_usd"],
                                   "fees": PROTOCOL["fees_usd"] / copies, "qty": 1})
            daily.append([stamp, pnl])
            day += dt.timedelta(days=1)
    return {"status": "ok", "trades": trades, "daily": daily,
            "summary": results.summarize(trades, daily, 10_000.0), "by_year": results.by_year(trades, daily)}


def trial(case: str, cohort: str, replication: int, previous_ps: list[float]) -> dict[str, Any]:
    train = generated(case, cohort, replication, PROTOCOL["train_years"])
    train_line = evidence.train_score(train)
    train_ok = bool(train_line["eligible"] and train_line["score"] is not None and train_line["score"] > 0)
    normal = generated(case, cohort, replication, [PROTOCOL["validation_year"]])
    stressed = generated(case, cohort, replication, [PROTOCOL["validation_year"]], stress=1.5)
    validation = evidence.validation_line(normal, stressed, validated_versions=PROTOCOL["validated_versions"],
                                          version_sharpes=[], lineage_trials=1)
    holdout = None
    if train_ok and validation["passed"]:
        unseen = generated(case, cohort, replication, [PROTOCOL["holdout_year"]])
        holdout = evidence.holdout_line(unseen, validation_sharpe=normal["summary"]["sharpe_daily"],
                                        previous_ps=previous_ps, seed=digest([cohort, case, replication, "bootstrap"]))
        previous_ps.append(holdout["p"])
    return {"replication": replication, "train_eligible": train_line["eligible"], "train_positive": train_ok,
            "train_why": train_line["why"], "validation_passed": validation["passed"],
            "validation_failed_checks": [k for k, v in validation["checks"].items() if not v],
            "holdout_tested": holdout is not None, "pipeline_passed": bool(holdout and holdout["passed"]),
            "holdout_failed_checks": None if holdout is None else [k for k, v in holdout["checks"].items() if not v]}


def benchmark(replications: int = 32) -> dict[str, Any]:
    if not 1 <= replications <= 512:
        raise ValueError("replications must be in [1, 512]")
    began = time.monotonic()
    root = Path(__file__).resolve().parents[2]
    sources = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
               for p in ("league/stats.py", "league/gym/results.py", "league/swarm/evidence.py")}
    out: dict[str, Any] = {"protocol": PROTOCOL, "protocol_sha": digest(PROTOCOL),
                           "generator_sha": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           "evaluator_sources": sources, "evaluator_sha": digest(sources),
                           "replications": replications, "cohorts": {},
                           "limitations": ["Synthetic returns; no claim about market edge or actual fills.",
                                            "Does not exercise drift screen, code review, or live promotion.",
                                            "One validated version per generated family; not an adaptive-search calibration.",
                                            "Finite control counts cannot establish a small false-promotion rate.",
                                            "Positive sparse is a diagnostic of existing frequency rules, not permission to relax them."]}
    for cohort in ("development", "confirmation"):
        groups, ps = {}, []
        # All holdout looks in a cohort share the real Holm history, including failed looks.
        for case, spec in PROTOCOL["cases"].items():
            rows = [trial(case, cohort, i, ps) for i in range(replications)]
            passes = sum(r["pipeline_passed"] for r in rows)
            groups[case] = {"expectation": spec["expectation"], "pipeline_passes": passes,
                            "pipeline_pass_rate": passes / replications,
                            "pass_rate_upper_95": stats.exact_upper(passes, replications, 0.05),
                            "train_positive": sum(r["train_positive"] for r in rows),
                            "validation_passes": sum(r["validation_passed"] for r in rows),
                            "holdout_looks": sum(r["holdout_tested"] for r in rows), "trials": rows}
        out["cohorts"][cohort] = {"cases": groups, "holdout_looks": len(ps)}
    out["elapsed_seconds"] = round(time.monotonic() - began, 3)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replications", type=int, default=32)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(args.replications)
    text = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(text + "\n")
        print(json.dumps({"output": str(args.output), "protocol_sha": report["protocol_sha"],
                          "evaluator_sha": report["evaluator_sha"], "elapsed_seconds": report["elapsed_seconds"]}))
    else:
        print(text)


if __name__ == "__main__":
    main()
