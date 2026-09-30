"""Synthetic diagnostic of long-single frequency, drift and adaptive-search gates.

No market data, model calls, real strategy execution or live promotion. Each Monte Carlo replication
is an independent synthetic swarm with its own persistent-within-replication lineage and Holm history.
Development freezes the generator, evaluator, protocol and sample count before confirmation is read.

    python -m league.swarm.long_single_benchmarks --cohort development --output development.json
    python -m league.swarm.long_single_benchmarks --cohort confirmation --frozen development.json --output confirmation.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import sys
import tempfile
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

from .. import stats
from ..gym import results
from . import evidence
from .benchmarks import digest
from .researcher import CANDIDATES, robust_at_stress
from .store import SwarmStore

PROTOCOL = {
    "id": "long-single-gates-1",
    "train_years": [2020, 2021, 2022, 2023, 2024],
    "validation_year": 2025, "holdout_year": 2026, "sessions": 252,
    "capital_usd": 1500.0, "premium_cap_usd": 75.0, "spot_and_strike": 100.0, "contract_multiplier": 100,
    "round_trip_spread_usd": 1.5, "round_trip_fees_usd": 1.3,
    "market_drift": 0.001, "market_noise_sd": 0.006, "prior_global_failed_looks": 2,
    "adaptive_variants": 64, "candidate_limit": CANDIDATES,
    "selection": "rank eligible drift-passing Train versions; stress/mid top candidates; continue after validation/holdout failure",
    "cases": {
        "sparse_planted_edge": {"trades_per_year": 12, "signal": 0.007, "policy": "forecast", "positive": True},
        "train_validation_frequency_gap": {"trades_per_year": 48, "signal": 0.007, "policy": "forecast", "positive": True},
        "incremental_after_drift": {"trades_per_year": 126, "signal": 0.007, "policy": "forecast", "positive": True},
        "drift_only_directional": {"trades_per_year": 252, "signal": 0.0, "policy": "call", "positive": False},
        "cost_erased_signal": {"trades_per_year": 126, "signal": 0.0004, "policy": "forecast", "positive": False},
        "unselected_noise": {"trades_per_year": 126, "signal": 0.0, "policy": "forecast", "positive": False,
                             "noise_control": True},
        "adaptive_noise": {"trades_per_year": 126, "signal": 0.0, "policy": "forecast", "positive": False,
                           "noise_control": True, "adaptive": True},
    },
}
SOURCES = ("league/stats.py", "league/gym/results.py", "league/swarm/benchmarks.py", "league/swarm/evidence.py",
           "league/swarm/researcher.py", "league/swarm/store.py")
LIMITATIONS = [
    "Invented ATM same-day option terminal payoffs and uniform root returns, not calibrated option chains or market opportunities.",
    "One contract at a time, same-day closure, no overlap, gap/assignment risk, partial fills, exercise or liquidity failures.",
    "The strong positive controls deliberately implant a large causal signal; this is a sensitivity test, not a return forecast.",
    "Positive means positive expected incremental trading P&L after synthetic costs; project/service costs are not recovered here.",
    "Noise controls include invented carry exactly offsetting base trading costs, making a demanding zero-net-edge control.",
    "The cash test has known same-day debits and liquidation payoffs; settlement constraints and brokerage permissions are not modeled.",
    "Independent Monte Carlo worlds do not share Holm history; all looks within each world do. Two synthetic prior failed looks are seeded.",
    "The frozen five-candidate attempt schedule is a statistical diagnostic, not a simulation of model research or asynchronous scheduling.",
    "Synthetic holdout is generated data, never the sealed market holdout. Model review, execution and independent forward evidence are excluded.",
    "Finite false-pass counts and confidence bounds do not establish calibration for real markets, dependence or nonstationarity.",
    "Frequency-only diagnostic probes cannot qualify a strategy or affect its ranking; they are separately recorded and counted.",
]


def fingerprints() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    sources = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCES}
    return {"protocol_sha": digest(PROTOCOL), "generator_sha": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "evaluator_sources": sources, "evaluator_sha": digest(sources), "runtime": {"python": sys.version}}


def rng(*parts: Any) -> random.Random:
    return random.Random(digest([PROTOCOL["id"], *parts]))


def fair_payoff(mean_signed_return: float) -> float:
    """Exact E[100 * max(S_T - K, 0)] for the synthetic uniform signed return.

    This is an explicitly invented pricing convention. Base premium uses zero drift; the adversarial
    noise control uses its side's physical mean and an explicit fee/spread credit to make net EV zero.
    """
    width = math.sqrt(3) * PROTOCOL["market_noise_sd"]
    mean = mean_signed_return
    value = 0.0 if mean <= -width else mean if mean >= width else (width + mean) ** 2 / (4 * width)
    return PROTOCOL["spot_and_strike"] * PROTOCOL["contract_multiplier"] * value


def generated(case: str, cohort: str, replication: int, window: str, variant: int = 0, *, stress: float = 1.0) -> dict:
    """Signals and schedules precede independent future shocks. Noise variants share one market path.

    Terminal call/put payoffs give exact known means and contractual loss bounds. The cash guard stops
    entries once the one-lot premium and fees no longer fit, retaining zero days thereafter.
    """
    if case not in PROTOCOL["cases"] or cohort not in ("development", "confirmation"):
        raise ValueError("unknown case or cohort")
    if replication < 0 or variant < 0 or stress < 0 or window not in ("train", "validation", "holdout", "diagnostic"):
        raise ValueError("invalid simulation request")
    spec = PROTOCOL["cases"][case]
    years = PROTOCOL["train_years"] if window == "train" else [PROTOCOL["holdout_year"] if window == "holdout" else PROTOCOL["validation_year"]]
    group = "shared_noise" if spec.get("noise_control") else case
    equity = PROTOCOL["capital_usd"]
    daily, trades, returns, exposure = [], [], {}, {}
    unavailable = 0
    for year in years:
        market = rng(cohort, replication, group, window, year, "market")
        signal = rng(cohort, replication, group, window, year, "policy", variant)
        active = set(signal.sample(range(PROTOCOL["sessions"]), spec["trades_per_year"]))
        sides = [1 if signal.random() < 0.5 else -1 for _ in range(PROTOCOL["sessions"])]
        day = dt.date(year, 1, 1)
        for index in range(PROTOCOL["sessions"]):
            while day.weekday() >= 5:
                day += dt.timedelta(days=1)
            stamp = day.isoformat()
            side = 1 if spec["policy"] == "call" else sides[index]
            # A publicly observed synthetic predictor affects a later return; policy never reads that shock.
            shock = market.uniform(-math.sqrt(3), math.sqrt(3)) * PROTOCOL["market_noise_sd"]
            move = PROTOCOL["market_drift"] + shock + (spec["signal"] * side if index in active else 0.0)
            returns[stamp] = {"SYN": {"ret_on": 0.0, "ret_in": move, "session": 390,
                                      "rv_day": PROTOCOL["market_noise_sd"] ** 2}}
            pnl = 0.0
            premium = fair_payoff(side * PROTOCOL["market_drift"]) if spec.get("noise_control") else fair_payoff(0.0)
            costs = PROTOCOL["round_trip_spread_usd"] * stress + PROTOCOL["round_trip_fees_usd"]
            risk = premium + costs
            if premium > PROTOCOL["premium_cap_usd"]:
                raise AssertionError("synthetic premium exceeds the frozen one-contract budget")
            if index in active and equity >= risk:
                carry = PROTOCOL["round_trip_spread_usd"] + PROTOCOL["round_trip_fees_usd"] if spec.get("noise_control") else 0.0
                terminal = PROTOCOL["spot_and_strike"] * PROTOCOL["contract_multiplier"] * max(0.0, side * move)
                pnl = terminal - premium - costs + carry
                if pnl < -risk:
                    raise AssertionError("the synthetic option lost more than its declared maximum loss")
                trades.append({"day": stamp, "root": "SYN", "type": "long_call" if side > 0 else "long_put",
                               "qty": 1, "pnl": pnl, "max_loss": risk, "fees": PROTOCOL["round_trip_fees_usd"],
                               "entry_premium": premium, "terminal_value": terminal, "explicit_cost_credit": carry,
                               "return_on_max_loss": pnl / risk})
                exposure[stamp] = {"SYN": (0, 390, move)}
                equity += pnl
            elif index in active:
                unavailable += 1
            daily.append([stamp, pnl, equity])
            day += dt.timedelta(days=1)
    roots_by_day = {row[0]: ["SYN"] for row in daily}
    return {"status": "ok", "trades": trades, "daily": daily, "roots": ["SYN"], "needs": {"roots": ["SYN"]},
            "summary": results.summarize(trades, daily, PROTOCOL["capital_usd"]),
            "by_year": results.by_year(trades, daily, roots_by_day=roots_by_day),
            "drift": results.drift(daily, returns, exposure, ["SYN"]),
            "cash": {"start": PROTOCOL["capital_usd"], "end": equity, "unaffordable_entries": unavailable},
            "market_sha": digest(returns), "path_sha": digest(daily)}


def compact(result: dict) -> dict:
    summary = result["summary"]
    return {"pnl": summary["pnl"], "trades": summary["trades"], "days_traded": summary["days_traded"],
            "t_daily": summary["t_daily"], "sharpe_daily": summary["sharpe_daily"],
            "drift": evidence.drift_numbers(result["drift"]), "cash": result["cash"], "path_sha": result["path_sha"]}


def record(store: SwarmStore, version: int, value: dict, window: str, stress: float, identity: list[Any]) -> None:
    """Record every computed outcome, including diagnostics, in an isolated real accounting store."""
    store.add_run("policy", version, {"run_id": digest(identity), "status": "ok", "summary": value["summary"], "trials": 1},
                  window=window, stress=stress, purpose="benchmark_diagnostic" if window == "probe" else window)


def trial(case: str, cohort: str, replication: int) -> dict:
    spec = PROTOCOL["cases"][case]
    variants = PROTOCOL["adaptive_variants"] if spec.get("adaptive") else 1
    with tempfile.TemporaryDirectory(prefix="ltcm-synthetic-gates-") as tmp, closing(SwarmStore(Path(tmp))) as store:
        family = {"mechanism": "Invented options outcomes for a frozen statistical diagnostic.", "structure": "long_single",
                  "roots": ["SYN"], "dte": [0, 0]}
        store.add_family({**family, "id": "policy"}, origin="synthetic-benchmark")
        store.add_family({**family, "id": "background"}, origin="synthetic-benchmark")
        for i in range(PROTOCOL["prior_global_failed_looks"]):
            store.add_look("background", i + 1, f"synthetic-prior-{i}", passed=False, p_value=0.5, detail={"invented_prior": True})
        rows = []
        for variant in range(variants):
            # An immutable manifest for accounting; this is deliberately not claimed to be an executable option strategy.
            version = store.add_version("policy", "# synthetic policy manifest\n" + json.dumps({"case": case, "variant": variant}),
                                        {}, author="synthetic-benchmark")["n"]
            train = generated(case, cohort, replication, "train", variant)
            record(store, version, train, "train", 1.0, [case, cohort, replication, variant, "train", 1.0])
            score = evidence.train_score(train, first_year=PROTOCOL["train_years"][0])
            drift = evidence.drift_screen(evidence.drift_numbers(train["drift"]), first_year=PROTOCOL["train_years"][0])
            rows.append({"variant": variant, "version": version, "train": compact(train), "score": score, "drift_screen": drift})
        candidates = sorted((r for r in rows if r["score"]["eligible"] and r["drift_screen"]["passed"]),
                            key=lambda r: (-r["score"]["score"], r["variant"]))[:PROTOCOL["candidate_limit"]]
        attempts, passed, stopped = [], False, None
        for candidate in candidates:
            variant, version = candidate["variant"], candidate["version"]
            stress = generated(case, cohort, replication, "train", variant, stress=evidence.STRESS)
            mid = generated(case, cohort, replication, "train", variant, stress=0.0)
            for value, amount in ((stress, evidence.STRESS), (mid, 0.0)):
                record(store, version, value, "train", amount, [case, cohort, replication, variant, "train", amount])
            robust = robust_at_stress({"robustness": {str(version): {"stress_1.5": evidence.robustness_view(stress)}}}, version)
            attempt = {"variant": variant, "train_stress_passed": robust, "train_stress_pnl": stress["summary"]["pnl"],
                       "validation": None, "holdout": None}
            attempts.append(attempt)
            if not robust:
                continue
            normal = generated(case, cohort, replication, "validation", variant)
            stressed = generated(case, cohort, replication, "validation", variant, stress=evidence.STRESS)
            for value, amount in ((normal, 1.0), (stressed, evidence.STRESS)):
                record(store, version, value, "validation", amount, [case, cohort, replication, variant, "validation", amount])
            n, sharpes = store.lineage_validated("policy")
            line = evidence.validation_line(normal, stressed, validated_versions=n, version_sharpes=sharpes,
                                            lineage_trials=store.lineage_trials("policy"))
            attempt["validation"] = line
            if not line["passed"]:
                continue
            looks = store.looks()
            if evidence.leakage_alarm(len(looks), sum(bool(r["passed"]) for r in looks)):
                stopped = "leakage_alarm"
                break
            if store.lineage_looks("policy") >= evidence.LOOKS_PER_LINEAGE:
                stopped = "lineage_look_limit"
                break
            unseen = generated(case, cohort, replication, "holdout", variant)
            record(store, version, unseen, "holdout", 1.0, [case, cohort, replication, variant, "holdout"])
            holdout = evidence.holdout_line(unseen, validation_sharpe=normal["summary"]["sharpe_daily"],
                                            previous_ps=[r["p_value"] for r in looks],
                                            seed=digest([case, cohort, replication, variant, "bootstrap"]))
            store.add_look("policy", version, digest([case, variant]), passed=holdout["passed"],
                           p_value=holdout["p"], detail=holdout)
            attempt["holdout"] = holdout
            if holdout["passed"]:
                passed = True
                break
        diagnostic = None
        if not spec.get("adaptive"):
            normal = generated(case, cohort, replication, "diagnostic")
            stressed = generated(case, cohort, replication, "diagnostic", stress=evidence.STRESS)
            for value, amount in ((normal, 1.0), (stressed, evidence.STRESS)):
                record(store, 1, value, "probe", amount, [case, cohort, replication, "frequency-diagnostic", amount])
            line = evidence.validation_line(normal, stressed, validated_versions=1,
                                            version_sharpes=[evidence.traded_sharpe(normal["summary"])],
                                            lineage_trials=store.lineage_trials("policy"))
            failed = [key for key, ok in line["checks"].items() if not ok]
            diagnostic = {"line": line, "frequency_only_rejection": bool(failed) and set(failed) <= {"trades", "days"},
                          "not_used_for_selection": True, "independent_path": compact(normal)}
        validated, _ = store.lineage_validated("policy")
        return {"replication": replication, "case": case, "statistical_pipeline_passed": passed, "stopped": stopped,
                "variants": variants, "train_eligible": sum(r["score"]["eligible"] for r in rows),
                "train_frequency_eligible": sum(all(y["trades"] >= evidence.TRAIN_YEAR_MIN_TRADES and
                                                     y["days_traded"] >= evidence.TRAIN_YEAR_MIN_DAYS
                                                     for y in r["score"]["years"].values()) for r in rows),
                "train_drift_passed": sum(r["drift_screen"]["passed"] for r in rows),
                "candidate_count": len(candidates), "baseline_score": rows[0]["score"]["score"],
                "best_candidate_score": candidates[0]["score"]["score"] if candidates else None,
                "normal_train_pnl": rows[0]["train"]["pnl"], "train": rows if variants == 1 else None,
                "train_cash_constrained_variants": sum(r["train"]["cash"]["unaffordable_entries"] > 0 for r in rows),
                "attempts": attempts, "diagnostic_validation": diagnostic,
                "accounting": {"lineage_trials": store.lineage_trials("policy"), "validated_versions": validated,
                               "lineage_looks": store.lineage_looks("policy"), "global_looks": len(store.looks()),
                               "diagnostic_trials": 0 if spec.get("adaptive") else 2,
                               "trial_rows": store.totals()["runs"]}}


def benchmark(cohort: str, replications: int = 64, *, frozen: dict | None = None) -> dict:
    if cohort not in ("development", "confirmation") or not 1 <= replications <= 256:
        raise ValueError("invalid cohort or replication count")
    fingerprints_now = fingerprints()
    if cohort == "confirmation":
        if frozen is None or frozen.get("cohort") != "development" or frozen.get("replications") != replications:
            raise ValueError("confirmation requires the frozen development report and identical sample count")
        if set(frozen.get("cases") or {}) != set(PROTOCOL["cases"]) or any(
                len(group.get("replications") or []) != replications for group in frozen["cases"].values()):
            raise ValueError("the frozen development report is incomplete")
        if any(frozen.get(key) != value for key, value in fingerprints_now.items()):
            raise ValueError("generator, protocol or evaluator changed after development; confirmation is not admissible")
    began = time.monotonic()
    groups = {}
    for case, spec in PROTOCOL["cases"].items():
        rows = [trial(case, cohort, i) for i in range(replications)]
        passes = sum(r["statistical_pipeline_passed"] for r in rows)
        failures = Counter(key for r in rows for attempt in r["attempts"] if attempt["validation"]
                           for key, ok in attempt["validation"]["checks"].items() if not ok)
        holdout_failures = Counter(key for r in rows for attempt in r["attempts"] if attempt["holdout"]
                                   for key, ok in attempt["holdout"]["checks"].items() if not ok)
        cost = PROTOCOL["round_trip_spread_usd"] + PROTOCOL["round_trip_fees_usd"]
        mu, signal = PROTOCOL["market_drift"], spec["signal"]
        incremental = 0.5 * (fair_payoff(signal + mu) + fair_payoff(signal - mu) - fair_payoff(mu) - fair_payoff(-mu)) - cost
        if spec.get("noise_control"):
            incremental = 0.0
        groups[case] = {"oracle_positive_incremental_edge": spec["positive"], "oracle_net_incremental_per_trade": incremental,
                        "oracle_gross_directional_drift_per_trade": fair_payoff(mu) - fair_payoff(0.0)
                            if spec["policy"] == "call" else 0.0,
                        "pipeline_passes": passes, "missed_positive_controls": replications - passes if spec["positive"] else None,
                        "false_passes": passes if not spec["positive"] else None,
                        "pass_rate": passes / replications, "pass_rate_upper_95": stats.exact_upper(passes, replications, 0.05),
                        "train_frequency_rejections": sum(not r["train_frequency_eligible"] for r in rows),
                        "no_train_eligible_variant": sum(not r["train_eligible"] for r in rows),
                        "no_candidate_after_train_and_drift": sum(r["candidate_count"] == 0 for r in rows),
                        "frequency_only_diagnostic_rejections": sum(bool((r["diagnostic_validation"] or {}).get("frequency_only_rejection")) for r in rows),
                        "validation_failed_checks": dict(failures), "holdout_failed_checks": dict(holdout_failures),
                        "train_cash_constrained_variants": sum(r["train_cash_constrained_variants"] for r in rows),
                        "lineage_trials": sum(r["accounting"]["lineage_trials"] for r in rows),
                        "holdout_looks": sum(r["accounting"]["lineage_looks"] for r in rows), "replications": rows}
    return {"cohort": cohort, "replications": replications, "protocol": PROTOCOL, **fingerprints_now,
            "frozen_development_sha": digest(frozen) if frozen is not None else None,
            "cases": groups, "limitations": LIMITATIONS, "elapsed_seconds": round(time.monotonic() - began, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=("development", "confirmation"), default="development")
    parser.add_argument("--replications", type=int, default=64)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("the output already exists; keep benchmark receipts immutable")
    frozen = json.loads(args.frozen.read_text()) if args.frozen else None
    report = benchmark(args.cohort, args.replications, frozen=frozen)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "cohort": args.cohort, "protocol_sha": report["protocol_sha"],
                      "generator_sha": report["generator_sha"], "elapsed_seconds": report["elapsed_seconds"],
                      "passes": {k: v["pipeline_passes"] for k, v in report["cases"].items()}}))


if __name__ == "__main__":
    main()
