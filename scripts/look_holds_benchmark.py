"""THE LOOK HOLDS (L6(b) and L6(c), Oct 2, 2026) on the fixed evaluator benchmark (#452, `evaluator-suite-1`).

The owner's rule for the holds: fixed benchmarks show false promotions do not rise, and the missed-signal cost is
reported. The pinned suite scores the evaluator's stages up to one synthetic holdout look and does not run the gate, so
this tool overlays the holds on the suite's own recorded outcomes:

    python scripts/look_holds_benchmark.py run --suite evaluator --json --output FULL --receipt RECEIPT [--compare OLD]
    python scripts/look_holds_benchmark.py analyze FULL SIDE OUT

`run` runs the pinned suite exactly as its CLI does (`league.swarm.evaluator_benchmarks.main`), and records each engine
case-world's hold figures (its Train drift fit through `evidence.drift_lean`, its Validation all-days daily Sharpe) by its
holdout seed into `holds_side.json` beside FULL. The suite file on disk is unchanged (it stays pinned), and the rows it
scores are untouched: only `figures` is wrapped in memory. `analyze` then counts, per case, the promotions with and without
the holds at the owner's thresholds (0.25, 0.30), with N the world's holdout sessions and the level the suite's fixed Holm
history gives (`evidence.holm_level`); and re-simulates the search tier's current rule with and without the power hold
before each look (the gate's order: the rations first), on the suite's own generated outcomes (the search tier has no
drift figures, so the drift hold does not apply there). The base simulation must equal the suite's own counts
(`reported_base_*` in OUT). Synthetic worlds only: no market data, no sealed day, no model call.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DRIFT_SHARE, MIN_POWER = 0.25, 0.30


def run(argv: list[str]) -> int:
    from league.gym import results as R
    from league.swarm import evaluator_benchmarks as EB
    from league.swarm import evidence

    side: dict[str, dict] = {}
    original = EB.figures

    def figures(train, train_stress, validation, validation_stress, holdout, seed):
        row = original(train, train_stress, validation, validation_stress, holdout, seed)
        lean = evidence.drift_lean(evidence.drift_numbers(train.get("drift")), first_year=EB.PROTOCOL["train_first_year"])
        summary = R.view(validation, "validation").get("summary") or {}
        side[seed] = {"lean": lean, "sharpe_daily": summary.get("sharpe_daily"),
                      "holdout_days": len(R.view(holdout, "holdout").get("daily") or [])}
        return row

    EB.figures = figures
    try:
        code = EB.main(argv)
    finally:
        out = Path(argv[argv.index("--output") + 1])
        (out.parent / "holds_side.json").write_text(json.dumps(side, default=str))
    return code


def hold(lean: dict, sharpe, sessions: int, level: float) -> dict:
    from league.swarm import evidence

    drift = (not lean.get("known")) or bool(lean.get("long_delta") and (lean.get("share") is None or lean["share"] >= DRIFT_SHARE))
    power = evidence.holdout_power(sharpe, sessions, level)
    return {"drift": drift, "power": power is None or power < MIN_POWER, "power_value": power, "share": lean.get("share"),
            "beta": lean.get("beta")}


def search_current(case: str, replication: int, *, holds: bool, cohort: str = "development",
                   cache: dict | None = None) -> dict:
    """`EB.search_trial` for the current rule alone, with THE LOOK HOLDS before each look when `holds` (rations first).
    `cache` shares the generated outcomes between the two modes of one trial (as the suite shares them across variants)."""
    from league.swarm import evaluator_benchmarks as EB
    from league.swarm import evidence

    cache = {} if cache is None else cache

    def get(key, make):
        if key not in cache:
            cache[key] = make()
        return cache[key]

    S = EB.SEARCH
    spec = S["cases"][case]
    rule = EB.VARIANTS["current"]
    train_years, v_year, h_year = S["train_years"], S["validation_year"], S["holdout_year"]
    figs = get(("figs",), lambda: [EB._train_figures(EB.search_outcomes(case, replication, v, train_years, cohort=cohort))
                                   for v in range(spec["variants"])])
    trains = figs
    ranked = []
    for v, fig in enumerate(figs):
        eligible, score = EB.train_eligible(fig, rule)
        if eligible:
            ranked.append((-score, v))
    ranked = [v for _, v in sorted(ranked)[:S["candidates"]]]
    looks = list(EB.PROTOCOL["prior_holdout_ps"])
    sharpes: list[float] = []
    lineage_looks = validations = held = 0
    promoted = False
    for v in ranked:
        stress = get(("train_stress", v), lambda v=v: EB.search_outcomes(case, replication, v, train_years, 1.5, cohort))
        if not stress["summary"]["pnl"] > 0:
            continue
        normal = get(("validation", v), lambda v=v: EB.search_outcomes(case, replication, v, [v_year], cohort=cohort))
        stressed = get(("validation_stress", v), lambda v=v: EB.search_outcomes(case, replication, v, [v_year], 1.5, cohort))
        validations += 1
        sharpe = evidence.traded_sharpe(normal["summary"])
        if sharpe is not None:
            sharpes.append(sharpe)
        line = evidence.validation_line(normal, {"status": "ok", "summary": stressed["summary"]}, validated_versions=validations,
                                        version_sharpes=sharpes, lineage_trials=len(trains) + 2 * validations)
        if not EB.validation_passes(line, rule):
            continue
        if lineage_looks >= S["looks_per_lineage"]:
            break
        if holds:
            power = evidence.holdout_power(normal["summary"]["sharpe_daily"], S["sessions"], evidence.holm_level(looks))
            if power is None or power < MIN_POWER:
                held += 1
                continue
        unseen = get(("holdout", v), lambda v=v: EB.search_outcomes(case, replication, v, [h_year], cohort=cohort))
        look = evidence.holdout_line(unseen, validation_sharpe=normal["summary"]["sharpe_daily"], previous_ps=looks,
                                     seed=EB._seed(cohort, S["id"], case, replication, v, "holdout"))
        looks.append(look["p"])
        lineage_looks += 1
        if look["passed"]:
            promoted = True
            break
    return {"promoted": promoted, "looks": lineage_looks, "held": held}


def analyze(full_path: str, side_path: str, out_path: str) -> int:
    from league.swarm import evaluator_benchmarks as EB
    from league.swarm import evidence

    full = json.loads(Path(full_path).read_text())
    side = json.loads(Path(side_path).read_text())
    cohort = full.get("cohort") or "development"
    sessions = int(full["world_sessions"]["holdout"])
    level = evidence.holm_level(EB.PROTOCOL["prior_holdout_ps"])
    kinds = {c["id"]: c for c in EB.CASES}
    engine: dict[str, dict] = {}
    for r, rep in enumerate(full["replication_rows"]):
        for cid, row in rep["cases"].items():
            case = kinds[cid]
            e = engine.setdefault(cid, {"kind": case["kind"], "family": case["family"], "of": 0, "promoted": 0,
                                        "promoted_with_holds": 0, "held_promotions": [], "would_be_held": 0, "reached_holdout": 0,
                                        "shares": [], "powers": []})
            e["of"] += 1
            seed = EB._seed(cohort, cid, rep["replication"], "holdout")
            fig = side.get(seed)
            if fig is None:
                # Refused by the static check: no figures, never promoted.
                assert not row.get("promoted"), cid
                continue
            if fig["holdout_days"] != sessions and fig["holdout_days"]:
                e.setdefault("holdout_days_differ", []).append(fig["holdout_days"])
            h = hold(fig["lean"], fig["sharpe_daily"], sessions, level)
            e["shares"].append(h["share"])
            e["powers"].append(h["power_value"])
            held = h["drift"] or h["power"]
            stages = row.get("stages") or {}
            before = all(v for k, v in stages.items() if k != "holdout")
            e["reached_holdout"] += int(before)
            e["would_be_held"] += int(before and held)
            e["promoted"] += int(bool(row["promoted"]))
            if row["promoted"] and held:
                e["held_promotions"].append({"replication": rep["replication"], "drift": h["drift"], "power": h["power"],
                                             "share": h["share"], "beta": h["beta"], "power_value": h["power_value"]})
            e["promoted_with_holds"] += int(bool(row["promoted"]) and not held)
    negatives = [e for e in engine.values() if e["kind"] == "negative"]
    positives = [e for e in engine.values() if e["kind"] == "positive"]
    rates = {
        "false_promotions": {"base": sum(e["promoted"] for e in negatives), "with_holds": sum(e["promoted_with_holds"] for e in negatives),
                             "of": sum(e["of"] for e in negatives)},
        "missed_signals": {"base": sum(e["of"] - e["promoted"] for e in positives),
                           "with_holds": sum(e["of"] - e["promoted_with_holds"] for e in positives),
                           "of": sum(e["of"] for e in positives)},
        "smoke_promoted": {"base": sum(e["promoted"] for e in engine.values() if e["kind"] == "smoke"),
                           "with_holds": sum(e["promoted_with_holds"] for e in engine.values() if e["kind"] == "smoke")},
    }
    search: dict[str, dict] = {}
    reported = ((full.get("variants") or {}).get("current") or {}).get("search_by_case") or {}
    for case, spec in EB.SEARCH["cases"].items():
        reps = int(full["search_replications"])
        base, held = [], []
        for r in range(reps):
            cache: dict = {}
            base.append(search_current(case, r, holds=False, cohort=cohort, cache=cache))
            held.append(search_current(case, r, holds=True, cohort=cohort, cache=cache))
        print(f"search {case}: done", file=sys.stderr, flush=True)
        search[case] = {"positive": spec["positive"], "of": reps,
                        "promoted": {"base": sum(x["promoted"] for x in base), "with_holds": sum(x["promoted"] for x in held)},
                        "looks": {"base": sum(x["looks"] for x in base), "with_holds": sum(x["looks"] for x in held)},
                        "holds": sum(x["held"] for x in held)}
        if case in reported:
            search[case]["reported_base_promoted"] = reported[case].get("promoted")
            search[case]["reported_base_lineages_with_look"] = reported[case].get("lineages_with_look")
    report = {"suite": full["suite"], "suite_sha": full["suite_sha"], "pinned": full["pinned"], "cohort": cohort,
              "tree": full["tree"].get("git_head"), "holdout_sessions": sessions, "holm_level": level,
              "thresholds": {"drift_share": DRIFT_SHARE, "min_power": MIN_POWER}, "engine_rates": rates,
              "engine_cases": {cid: {k: v for k, v in e.items() if k not in ("shares", "powers")} | {
                  "share_range": [min((s for s in e["shares"] if s is not None), default=None),
                                  max((s for s in e["shares"] if s is not None), default=None)],
                  "power_range": [min((p for p in e["powers"] if p is not None), default=None),
                                  max((p for p in e["powers"] if p is not None), default=None)]}
                  for cid, e in sorted(engine.items())},
              "search": search,
              "search_rates": {
                  "noise_promoted": {k: sum(s["promoted"][k] for s in search.values() if not s["positive"]) for k in ("base", "with_holds")},
                  "noise_looks": {k: sum(s["looks"][k] for s in search.values() if not s["positive"]) for k in ("base", "with_holds")},
                  "signal_missed": {k: sum(s["of"] - s["promoted"][k] for s in search.values() if s["positive"]) for k in ("base", "with_holds")},
                  "signal_of": sum(s["of"] for s in search.values() if s["positive"]),
                  "noise_of": sum(s["of"] for s in search.values() if not s["positive"])}}
    Path(out_path).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"engine_rates": rates, "search_rates": report["search_rates"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the checkout's own league package
    mode = sys.argv[1]
    if mode == "run":
        raise SystemExit(run(sys.argv[2:]))
    raise SystemExit(analyze(*sys.argv[2:5]))
