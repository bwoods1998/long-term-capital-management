"""THE FAST LANE'S SCREEN BENCHMARK (fast lane v2, Oct 7, 2026; the owner's goal item 4: "a program trades at Probe size
as soon as it passes a pre-registered screen whose false-positive rate you have measured"). Pre-registered: the receipt
`docs/benchmarks/fast_lane_screen_1.json` is frozen and committed BEFORE the run, and `--run` refuses when any file it
pins differs (this script, `league/swarm/evidence.py`, `league/stats.py`, `league/gym/results.py`, the input database).

    python scripts/screen_benchmark.py --freeze [--db HOUSE_SQLITE]   # write the receipt (commit it, then run)
    python scripts/screen_benchmark.py --run [--processes 8]          # the run: the result JSON and the report
    python scripts/screen_benchmark.py --dev --reps 2                 # a smoke run of the same code; writes nothing

THE SCREEN judged (the tree's own `evidence.validation_line` and `evidence.holdout_line`, unchanged): the Validation line
(t >= 1.65 on daily P&L, a probabilistic Sharpe >= 0.95 with N = 1 a program, 2 of 4 quarters, mean > 0, profit at 1.5x
the half-spread, 50 trades on 25 days) on a simulated 2025, and for a program that passes it ONE holdout look at the flat
one-sided level 0.10 (P&L > 0, half the Validation Sharpe) on a simulated Jan 2 - Sep 25, 2026.

THE INPUT, read-only (`mode=ro`): the House store's Validation run rows (`window='validation'`, the 1.0x row and its 1.5x
twin) and the families' lineage. Never a holdout run, a look or its detail. One profile per DISTINCT program (the same
trades, days, sessions, t and P&L in another family is the same program, counted once): T trades on d distinct days of
D sessions; sd_day = |mean| sqrt(d) / |t|; cost = the daily mean at 1.0x less the daily mean at 1.5x (floored at 0).

THE CALENDARS: NYSE sessions (`ltcm.data.us_equity_session`): Validation 2025-01-02..2025-12-31 (250), the holdout
2026-01-02..2026-09-25 (184). A program with D < 250 sessions trades the last D.

THE WORLDS. Null (each judged against the cap): zero mean net of Gym costs in four shapes (gauss; t3, Student t with 3
degrees of freedom at unit variance; skew, 24% winners and a lost stake otherwise; ar, AR(0.2) shocks), in both
windows; and mid, zero at the mid paying its own cost (net mean -2 x cost: the 1.0x run pays twice the 0.5x step).
drift_only: every program's traded-day P&L is its exposure to ONE common market factor with a yearly Sharpe of 1
(shared by every program of a replication, in both windows): direction profit, REPORTED, never a bar. Planted: an
all-days yearly Sharpe of 1, 2 and 3 (gauss).

EACH TRIAL: the new Validation line with its stress twin; for a pass, the new holdout look on Binomial(184, d/D) traded
days with `validation_sharpe` the Validation `sharpe_daily`. Beside it, TODAY'S RULE (before fast lane v2): t >= 2,
3 of 4 quarters, the deflated Sharpe with N = the program's lineage size in the store, and a look with lcb95 > 0 and
Holm at the next level, 0.0125.

ACCEPTANCE (pre-registered): in EVERY null world, the floor-eligible per-program false-positive rate's exact one-sided
95% upper bound (Clopper-Pearson, `league.stats.exact_upper`) is at most 2%. If it holds, the constants ship. If any
world fails, MIN_T is raised by 0.1, a new receipt is frozen and the run is made again, until it holds. A result never
loosens a constant.

Standard library only; at most 8 processes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import random
import sqlite3
import subprocess
import sys
import time
from multiprocessing import get_context
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))  # the checkout's own league package

RECEIPT = REPO / "docs" / "benchmarks" / "fast_lane_screen_1.json"
HASHED = ("scripts/screen_benchmark.py", "league/swarm/evidence.py", "league/stats.py", "league/gym/results.py")
DEFAULT_DB = "/home/bwoods1998/Work/.ltcm-main/scratch/blockers-1007/house.sqlite"

PROTOCOL = {
    "seed": "fast-lane-screen-1",
    "reps": {"null": 40, "drift_only": 20, "planted": 10},
    "null_worlds": ["gauss", "t3", "skew", "ar", "mid"],
    "planted_sharpes": [1, 2, 3],
    "planted_shape": "gauss",
    "drift_sharpe_year": 1.0,
    "validation_window": ["2025-01-02", "2025-12-31"],
    "holdout_window": ["2026-01-02", "2026-09-25"],
    "contamination_tail_from": "2026-07-01",
    "floor": {"trades": 50, "days": 25},
    "look_size_draws": 6000,
    "max_processes": 8,
    "cap": 0.02,
    "confidence": 0.95,
    "looks_per_lineage": 3,
    "old_rule": {"min_t": 2.0, "quarters": 3, "dsr": 0.95, "dsr_n": "the program's lineage size in the store",
                 "look": "lcb95 > 0 and p <= 0.0125 (Holm at the next look), P&L > 0, half the Validation Sharpe"},
    "removed_checks": ["t", "dsr", "quarters", "stress", "mean", "look_pnl", "look_sharpe"],
    "tickets_usd": [40, 125],
    "demote_multiple": 3,
    "probe_budget_usd": 400,
}
ACCEPTANCE = ("In every null world (gauss, t3, skew, ar, mid), the floor-eligible per-program false-positive rate's exact "
              "one-sided 95% upper bound (Clopper-Pearson, league.stats.exact_upper) is at most 2%. If it holds, the "
              "constants ship. If any world fails, MIN_T is raised by 0.1, a new receipt is frozen and the run is made "
              "again, until it holds. A result never loosens a constant.")


# ----------------------------------------------------------------------------------------------- the input
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sessions(first: str, last: str) -> list[str]:
    from ltcm.data import us_equity_session

    out, day, end = [], dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    while day <= end:
        if us_equity_session(day) is not None:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def profiles(db: str) -> tuple[list[dict], dict]:
    """One profile per distinct program from the store's Validation rows (1.0x with its 1.5x twin), with its lineage."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        lineage = {fid: lin for fid, lin in con.execute("SELECT id, lineage FROM swarm_families")}
        base, twin = {}, {}
        for run_id, fam, stress, at, summ in con.execute(
                "SELECT run_id, family, stress, at, summary FROM swarm_runs_recent WHERE window='validation' AND status='ok' "
                "ORDER BY at, run_id"):
            try:
                s = json.loads(summ)
            except (TypeError, ValueError):
                continue
            if stress == 1.5:
                twin[run_id[:-4]] = s
            elif stress == 1.0:
                base[run_id] = (fam, at, s)
        last_at = con.execute("SELECT max(at) FROM swarm_runs_recent WHERE window='validation'").fetchone()[0]
    finally:
        con.close()
    seen: dict[tuple, dict] = {}
    for rid, (fam, at, s) in base.items():
        t, m = s.get("t_daily"), s.get("mean_return_on_max_loss_daily")
        T, d, D = int(s.get("trades") or 0), int(s.get("days_traded") or 0), int(s.get("days") or 0)
        tw = twin.get(rid)
        if t in (None, 0) or m in (None, 0) or d < 2 or D < 2 or tw is None or tw.get("mean_return_on_max_loss_daily") is None:
            continue
        key = (T, d, D, round(float(t), 3), s.get("pnl"))  # one program counted once, whatever family carries it
        if key in seen:
            seen[key]["last_at"] = max(seen[key]["last_at"], at)
            continue
        seen[key] = {"key": "|".join(map(str, key)), "T": T, "d": d, "D": min(D, 250), "sd": abs(m) * math.sqrt(d) / abs(t),
                     "cost": max(0.0, float(m) - float(tw["mean_return_on_max_loss_daily"])),
                     "lineage": lineage.get(fam, fam), "first_at": at, "last_at": at,
                     "eligible": T >= PROTOCOL["floor"]["trades"] and d >= PROTOCOL["floor"]["days"]}
    out = list(seen.values())
    sizes: dict[str, int] = {}
    for p in out:
        sizes[p["lineage"]] = sizes.get(p["lineage"], 0) + 1
    for p in out:
        p["lineage_size"] = sizes[p["lineage"]]
    week_from = (dt.datetime.fromisoformat(last_at.replace("Z", "+00:00")) - dt.timedelta(days=7)).isoformat().replace("+00:00", "Z")
    eligible_lineages = {p["lineage"] for p in out if p["eligible"]}
    meta = {"programs": len(out), "eligible": sum(p["eligible"] for p in out), "lineages": len(sizes),
            "eligible_lineages": len(eligible_lineages),
            "largest_lineage": max(sizes.values()) if sizes else 0, "snapshot_last_validation": last_at,
            "week_from": week_from,
            "validated_last_7_days": sum(1 for p in out if p["last_at"] >= week_from),
            "eligible_validated_last_7_days": sum(1 for p in out if p["last_at"] >= week_from and p["eligible"])}
    return out, meta


# ----------------------------------------------------------------------------------------------- the worlds
_V = _H = None


def _calendars() -> tuple[list[str], list[str]]:
    global _V, _H
    if _V is None:
        _V, _H = sessions(*PROTOCOL["validation_window"]), sessions(*PROTOCOL["holdout_window"])
    return _V, _H


def shocks(rng: random.Random, n: int, shape: str) -> list[float]:
    """n unit-variance, mean-zero shocks of the world's shape."""
    out = []
    prev = rng.gauss(0.0, 1.0)
    g = 0.76 / 0.24
    norm = math.sqrt(0.24 * g * g + 0.76)
    for _ in range(n):
        if shape == "t3":
            z = rng.gauss(0.0, 1.0) / math.sqrt(rng.gammavariate(1.5, 2.0) / 3.0) / math.sqrt(3.0)
        elif shape == "skew":
            z = (g if rng.random() < 0.24 else -1.0) / norm
        elif shape == "ar":
            prev = 0.2 * prev + math.sqrt(1.0 - 0.04) * rng.gauss(0.0, 1.0)
            z = prev
        else:
            z = rng.gauss(0.0, 1.0)
        out.append(z)
    return out


def mu_for(sharpe_year: float, f: float, sd: float) -> float:
    """The traded-day mean giving an all-days daily Sharpe of sharpe_year / sqrt(252) at traded share f."""
    target = sharpe_year / math.sqrt(252.0)
    lo, hi = 0.0, 10.0 * sd
    for _ in range(80):
        mid = (lo + hi) / 2
        m_all = f * mid
        v_all = f * (sd * sd + mid * mid) - m_all * m_all
        if v_all <= 0 or m_all / math.sqrt(v_all) < target:
            lo = mid
        else:
            hi = mid
    return hi


def market_path(rep: int) -> dict[str, float]:
    """drift_only's common market factor for one replication: a standardized daily shock plus the drift of a yearly
    Sharpe of 1, on every Validation and holdout session."""
    V, H = _calendars()
    rng = random.Random(f"{PROTOCOL['seed']}:market:{rep}")
    drift = PROTOCOL["drift_sharpe_year"] / math.sqrt(252.0)
    return {day: rng.gauss(0.0, 1.0) + drift for day in V + H}


def series(days: list[str], traded: int, per: int, mu: float, sd: float, rng: random.Random, shape: str,
           market: dict | None = None) -> dict:
    from league.gym import results as R

    picked = sorted(rng.sample(range(len(days)), min(traded, len(days))))
    zs = shocks(rng, len(picked), shape)
    trades, daily, k = [], [], 0
    act = dict(zip(picked, zs))
    for i, day in enumerate(days):
        p = 0.0
        if i in act:
            r = sd * market[day] if market is not None else mu + sd * act[i]
            for _ in range(per):
                pnl = 100.0 * r
                trades.append({"day": day, "pnl": pnl, "max_loss": 100.0, "qty": 1, "return_on_max_loss": r, "fees": 0.65})
                p += pnl
            k += 1
        daily.append([day, p])
    return {"status": "ok", "trades": trades, "daily": daily, "summary": R.summarize(trades, daily, 10000.0)}


def trial(args: tuple) -> dict:
    """One program in one world: the new screen, its variants with one check removed, and today's rule."""
    from league.swarm import evidence as E

    p, world, S, rep = args
    V, H = _calendars()
    rng = random.Random(f"{PROTOCOL['seed']}:{world}:{S}:{rep}:{p['key']}")
    days = V[-p["D"]:]
    f = p["d"] / max(1, p["D"])
    per = max(1, round(p["T"] / p["d"]))
    shape = world if world in ("gauss", "t3", "skew", "ar") else "gauss"
    market = market_path(rep) if world == "drift_only" else None
    mu = 0.0
    if world == "mid":
        mu = -2.0 * p["cost"]
    elif world == "planted":
        mu = mu_for(S, f, p["sd"])
    v = series(days, p["d"], per, mu, p["sd"], rng, shape, market)
    s = v["summary"]
    stressed = {"summary": {"pnl": s["pnl"] - 100.0 * p["cost"] * len(v["trades"])}}
    line = E.validation_line(v, stressed, validated_versions=1, version_sharpes=[])
    checks = dict(line["checks"])
    k, _ = E.quarters_positive(s)
    t = s.get("t_daily")
    old = dict(checks)
    old["t"] = t is not None and t >= PROTOCOL["old_rule"]["min_t"]
    old["quarters"] = k >= PROTOCOL["old_rule"]["quarters"]
    dsr_old = E.deflated(s, validated_versions=p["lineage_size"], version_sharpes=[])
    old["dsr"] = dsr_old is not None and dsr_old >= PROTOCOL["old_rule"]["dsr"]
    key_of = {"t": "t", "dsr": "dsr", "quarters": "quarters", "stress": "stress", "mean": "mean_positive"}
    vals = {"new": all(checks.values()), "old": all(old.values())}
    for name, check in key_of.items():
        vals[f"no_{name}"] = all(ok for c, ok in checks.items() if c != check)
    dh = sum(1 for _ in range(len(H)) if rng.random() < f)
    h = series(H, max(2, dh), per, mu, p["sd"], rng, shape, market)  # drawn always: the same holdout for every variant
    look: dict = {}
    if any(vals.values()):
        hl = E.holdout_line(h, validation_sharpe=s.get("sharpe_daily"), previous_ps=[],
                            seed=f"{PROTOCOL['seed']}:look:{world}:{S}:{rep}:{p['key']}")
        lc = hl["checks"]
        n = hl["numbers"]
        look = {"new": bool(hl["passed"]), "pnl": bool(lc["pnl"]), "level": bool(lc["level"]), "sharpe": bool(lc["sharpe"]),
                "status": bool(lc["status_ok"]),
                "old": bool(lc["status_ok"] and lc["pnl"] and lc["sharpe"] and n["lcb95"] is not None and n["lcb95"] > 0
                            and hl["p"] <= 0.0125),
                "tail_days": n["tail"]["days"]}
    return {"world": world, "S": S, "rep": rep, "key": p["key"], "eligible": p["eligible"], "lineage": p["lineage"],
            "vals": vals, "look": look}


def look_size(args: tuple) -> tuple[str, bool, bool, bool]:
    from league.swarm import evidence as E

    shape, i = args
    rng = random.Random(f"{PROTOCOL['seed']}:size:{shape}:{i}")
    n = 184
    if shape == "ar":
        x, prev = [], rng.gauss(0.0, 1.0)
        for _ in range(n):
            prev = 0.2 * prev + math.sqrt(1 - 0.04) * rng.gauss(0.0, 1.0)
            x.append(prev)
    elif shape == "sparse":
        g = 0.76 / 0.24
        x = [((g if rng.random() < 0.24 else -1.0) if rng.random() < 0.17 else 0.0) for _ in range(n)]
    else:
        x = [rng.gauss(0.0, 1.0) for _ in range(n)]
    b = E.block_bootstrap(x, seed=f"{shape}{i}")
    return shape, b["p"] <= 0.10, b["p"] <= 0.05, b["lcb95"] > 0


# ----------------------------------------------------------------------------------------------- the report
def screen_pass(row: dict, variant: str = "new") -> bool:
    """The screen under `variant`: "new", "old", or the new one with a check removed ("no_t", ..., "no_look_pnl")."""
    look = row["look"]
    if variant == "old":
        return row["vals"]["old"] and bool(look.get("old"))
    if variant in ("no_look_pnl", "no_look_sharpe"):
        if not row["vals"]["new"]:
            return False
        dropped = "pnl" if variant == "no_look_pnl" else "sharpe"
        return all(look.get(c) for c in ("status", "pnl", "level", "sharpe") if c != dropped)
    val = row["vals"]["new" if variant == "new" else variant]
    return val and bool(look.get("new"))


def rate(k: int, n: int) -> dict:
    from league import stats

    return {"k": k, "n": n, "rate": k / n if n else None,
            "upper95": stats.exact_upper(k, n, 1.0 - PROTOCOL["confidence"]) if n else None}


def lineage_rate(rows: list[dict], order: dict[str, int]) -> dict:
    """The per-lineage false-positive rate, over the lineages with a floor-eligible program: a lineage passes when one of
    its programs (in the store's order) passes its look among its first `looks_per_lineage` looks (a look is spent by
    each program that passes Validation)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["rep"], r["lineage"]), []).append(r)
    groups = {k: v for k, v in groups.items() if any(r["eligible"] for r in v)}
    k = 0
    by_size: dict[int, list[int]] = {}
    for (_, _), members in groups.items():
        members.sort(key=lambda r: order[r["key"]])
        looks, hit = 0, False
        for r in members:
            if not r["vals"]["new"]:
                continue
            looks += 1
            if looks > PROTOCOL["looks_per_lineage"]:
                break
            if r["look"].get("new"):
                hit = True
                break
        k += hit
        size = len(members)
        bucket = by_size.setdefault(size, [0, 0])
        bucket[0] += hit
        bucket[1] += 1
    largest = max(by_size) if by_size else 0
    return {**rate(k, len(groups)), "largest_lineage": largest,
            "largest_lineage_rate": (by_size[largest][0] / by_size[largest][1]) if largest else None}


def analyze(rows: list[dict], sizes: list[tuple], P: list[dict], meta: dict) -> dict:
    from league.swarm import evidence as E

    order = {p["key"]: i for i, p in enumerate(P)}
    out: dict = {"meta": meta, "worlds": {}}

    def subset(world, S=0, eligible=None):
        return [r for r in rows if r["world"] == world and r["S"] == S and (eligible is None or r["eligible"] == eligible)]

    accept = True
    for world in PROTOCOL["null_worlds"]:
        allr, elig = subset(world), subset(world, eligible=True)
        w = {"screen_all": rate(sum(screen_pass(r) for r in allr), len(allr)),
             "screen_eligible": rate(sum(screen_pass(r) for r in elig), len(elig)),
             "validation_eligible": rate(sum(r["vals"]["new"] for r in elig), len(elig)),
             "look_given_validation": rate(sum(screen_pass(r) for r in elig), sum(r["vals"]["new"] for r in elig)),
             "todays_rule_eligible": rate(sum(screen_pass(r, "old") for r in elig), len(elig)),
             "todays_validation_eligible": rate(sum(r["vals"]["old"] for r in elig), len(elig)),
             "lineage": lineage_rate(allr, order),
             "removed": {c: rate(sum(screen_pass(r, f"no_{c}") for r in elig), len(elig))
                         for c in PROTOCOL["removed_checks"]}}
        w["accepted"] = w["screen_eligible"]["upper95"] <= PROTOCOL["cap"]
        accept = accept and w["accepted"]
        out["worlds"][world] = w
    drift = subset("drift_only", 0, True)
    out["drift_only"] = {"screen_eligible": rate(sum(screen_pass(r) for r in drift), len(drift)),
                         "validation_eligible": rate(sum(r["vals"]["new"] for r in drift), len(drift)),
                         "todays_rule_eligible": rate(sum(screen_pass(r, "old") for r in drift), len(drift)),
                         "note": "direction profit (a common market factor, yearly Sharpe 1): reported, never a bar"}
    out["power"] = {}
    for S in PROTOCOL["planted_sharpes"]:
        elig = subset("planted", S, True)
        out["power"][str(S)] = {"screen_eligible": rate(sum(screen_pass(r) for r in elig), len(elig)),
                                "validation_eligible": rate(sum(r["vals"]["new"] for r in elig), len(elig)),
                                "todays_rule_eligible": rate(sum(screen_pass(r, "old") for r in elig), len(elig)),
                                "removed": {c: rate(sum(screen_pass(r, f"no_{c}") for r in elig), len(elig))
                                            for c in PROTOCOL["removed_checks"]}}
    size_counts: dict[str, list[int]] = {}
    for shape, a, b, c in sizes:
        x = size_counts.setdefault(shape, [0, 0, 0, 0])
        x[0] += 1
        x[1] += a
        x[2] += b
        x[3] += c
    out["look_size"] = {s: {"n": n, "p_le_0.10": a / n, "p_le_0.05": b / n, "lcb95_above_0": c / n}
                        for s, (n, a, b, c) in sorted(size_counts.items())}
    worst = max((w["screen_eligible"]["rate"] or 0.0) for w in out["worlds"].values())
    worst_val = max((w["validation_eligible"]["rate"] or 0.0) for w in out["worlds"].values())
    week, week_e = meta["validated_last_7_days"], meta["eligible_validated_last_7_days"]
    lo, hi = PROTOCOL["tickets_usd"]
    m = PROTOCOL["demote_multiple"]
    out["volume"] = {"programs_validated_last_7_days": week, "eligible_validated_last_7_days": week_e,
                     "worst_null_screen_rate": worst, "worst_null_validation_rate": worst_val,
                     "false_validation_passes_a_week": week_e * worst_val, "false_probes_a_week": week_e * worst,
                     "demotion_loss_usd": [m * lo, m * hi],
                     "demotions_the_budget_covers": [PROTOCOL["probe_budget_usd"] // (m * hi), PROTOCOL["probe_budget_usd"] // (m * lo)],
                     "false_probe_loss_a_week_usd": [round(week_e * worst * m * lo, 2), round(week_e * worst * m * hi, 2)]}
    H = len(_calendars()[1])
    tail = len([d for d in _calendars()[1] if d >= PROTOCOL["contamination_tail_from"]])
    out["tail_power"] = {str(S): {"tail_61": E.holdout_power(S / math.sqrt(252.0), tail, 0.10),
                                  "look_184": E.holdout_power(S / math.sqrt(252.0), H, 0.10)}
                         for S in PROTOCOL["planted_sharpes"]}
    out["contamination"] = (f"Stated, not measured: {H - tail} of the holdout's {H} sessions (through 2026-06-30) are inside the "
                            "training of Opus 5.5 (cutoff June 2026); the cutoffs of DeepSeek-V4-Flash (about 93% of versions), "
                            "Kimi-K3 and GPT-6 Astra are unknown. A synthetic benchmark cannot measure it. Every look carries "
                            f"its {tail}-session tail from {PROTOCOL['contamination_tail_from']} beside it (numbers.tail), "
                            "weak in power and never a bar.")
    out["accepted"] = accept
    return out


def markdown(result: dict) -> str:
    def pct(x):
        return "n/a" if x is None else f"{100.0 * x:.2f}%"

    a = result["analysis"]
    lines = [f"# Fast lane screen benchmark 1 ({result['receipt']['name']})", "",
             f"Run {result['finished_at']} on tree {result['receipt']['tree_head']} (receipt hashes verified). "
             f"Acceptance: {ACCEPTANCE}", "",
             f"**Verdict: {'ACCEPTED: the constants ship' if a['accepted'] else 'NOT ACCEPTED: raise MIN_T by 0.1 and run again'}.**",
             "", f"Input: {a['meta']['programs']} distinct programs ({a['meta']['eligible']} floor-eligible) in "
             f"{a['meta']['lineages']} lineages ({a['meta']['eligible_lineages']} with a floor-eligible program; the largest "
             f"holds {a['meta']['largest_lineage']}).", "",
             "## False positives (no-edge programs that reach Validation and pass the screen)", "",
             "| Null world | Screen, eligible (95% upper) | Screen, all | Validation alone | Look given Validation | Per lineage (<= 3 looks) | Today's rule |",
             "|---|---|---|---|---|---|---|"]
    for world, w in a["worlds"].items():
        lines.append(f"| {world} | {pct(w['screen_eligible']['rate'])} ({pct(w['screen_eligible']['upper95'])}) | "
                     f"{pct(w['screen_all']['rate'])} | {pct(w['validation_eligible']['rate'])} | "
                     f"{pct(w['look_given_validation']['rate'])} | {pct(w['lineage']['rate'])} | "
                     f"{pct(w['todays_rule_eligible']['rate'])} |")
    lines += ["", "Per lineage, the largest lineage's rate: " + "; ".join(
        f"{world} {pct(w['lineage']['largest_lineage_rate'])} ({w['lineage']['largest_lineage']} programs)"
        for world, w in a["worlds"].items()) + "."]
    d = a["drift_only"]
    lines += ["", f"drift_only (direction profit, reported, never a bar): screen {pct(d['screen_eligible']['rate'])}, "
              f"Validation {pct(d['validation_eligible']['rate'])}, today's rule {pct(d['todays_rule_eligible']['rate'])}.", "",
              "## Power (floor-eligible, planted all-days yearly Sharpe)", "",
              "| Sharpe | Screen | Validation alone | Today's rule |", "|---|---|---|---|"]
    for S, w in a["power"].items():
        lines.append(f"| {S} | {pct(w['screen_eligible']['rate'])} | {pct(w['validation_eligible']['rate'])} | "
                     f"{pct(w['todays_rule_eligible']['rate'])} |")
    lines += ["", "## The cost of each kept check (removed in turn): floor-eligible false positives in each null world, and power", "",
              "| Removed | FP gauss | FP t3 | FP skew | FP ar | FP mid | Power S1 | Power S2 | Power S3 |", "|---|---|---|---|---|---|---|---|---|"]
    for c in PROTOCOL["removed_checks"]:
        fp = [pct(a["worlds"][w]["removed"][c]["rate"]) for w in PROTOCOL["null_worlds"]]
        pw = [pct(a["power"][str(S)]["removed"][c]["rate"]) for S in PROTOCOL["planted_sharpes"]]
        lines.append(f"| {c} | " + " | ".join(fp + pw) + " |")
    v = a["volume"]
    lines += ["", "## Volume and dollars", "",
              f"- Programs validated in the snapshot's last 7 days: {v['programs_validated_last_7_days']} "
              f"({v['eligible_validated_last_7_days']} floor-eligible).",
              f"- If all were no-edge, at the worst null world's rates: {v['false_validation_passes_a_week']:.1f} false Validation "
              f"passes and {v['false_probes_a_week']:.2f} false Probes a week.",
              f"- A demoted false Probe loses about {PROTOCOL['demote_multiple']} x its maximum loss: "
              f"${v['demotion_loss_usd'][0]}-{v['demotion_loss_usd'][1]} for ${PROTOCOL['tickets_usd'][0]}-"
              f"{PROTOCOL['tickets_usd'][1]} tickets; the ${PROTOCOL['probe_budget_usd']} budget covers "
              f"{v['demotions_the_budget_covers'][0]}-{v['demotions_the_budget_covers'][1]} demotions; false Probes could "
              f"cost ${v['false_probe_loss_a_week_usd'][0]}-{v['false_probe_loss_a_week_usd'][1]} a week.", "",
              "## The look's own size at 0.10 (no edge, 184 sessions)", ""]
    for s, x in a["look_size"].items():
        lines.append(f"- {s}: P(p <= 0.10) {pct(x['p_le_0.10'])}, P(p <= 0.05) {pct(x['p_le_0.05'])}, "
                     f"P(lcb95 > 0) {pct(x['lcb95_above_0'])} (n {x['n']}).")
    lines += ["", "## Contamination", "", a["contamination"], "",
              "The tail look's power (normal approximation, level 0.10, an every-session program): " +
              "; ".join(f"Sharpe {S}: {pct(x['tail_61'])} on the 61-session tail, {pct(x['look_184'])} on the 184-session look"
                        for S, x in a["tail_power"].items()) + ".", ""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------- the commands
def hashes(db: str) -> dict:
    out = {name: sha256_file(REPO / name) for name in HASHED}
    out["input_db"] = sha256_file(Path(db))
    return out


def git_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def freeze(receipt: Path, db: str) -> dict:
    if receipt.exists():
        raise SystemExit(f"{receipt} exists: a frozen receipt is never rewritten (freeze a new one under a new name)")
    doc = {"name": receipt.stem, "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "tree_head": git_head(), "input_db": db, "sha256": hashes(db), "protocol": PROTOCOL, "acceptance": ACCEPTANCE,
           "constants": constants()}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return doc


def constants() -> dict:
    from league.swarm import evidence as E

    return {"MIN_T": E.MIN_T, "MIN_DSR": E.MIN_DSR, "MIN_QUARTERS_POSITIVE": E.MIN_QUARTERS_POSITIVE, "MIN_TRADES": E.MIN_TRADES,
            "MIN_DAYS": E.MIN_DAYS, "STRESS": E.STRESS, "LOOK_LEVEL": E.LOOK_LEVEL,
            "HOLDOUT_SHARPE_SHARE": E.HOLDOUT_SHARPE_SHARE, "BOOTSTRAP_DRAWS": E.BOOTSTRAP_DRAWS,
            "BOOTSTRAP_BLOCK": E.BOOTSTRAP_BLOCK}


def jobs_for(P: list[dict], reps: dict) -> list[tuple]:
    out = []
    for world in PROTOCOL["null_worlds"]:
        out += [(p, world, 0, r) for r in range(reps["null"]) for p in P]
    out += [(p, "drift_only", 0, r) for r in range(reps["drift_only"]) for p in P]
    for S in PROTOCOL["planted_sharpes"]:
        out += [(p, "planted", S, r) for r in range(reps["planted"]) for p in P]
    return out


def execute(db: str, reps: dict, processes: int, size_draws: int) -> tuple[list[dict], list[tuple], list[dict], dict]:
    P, meta = profiles(db)
    jobs = jobs_for(P, reps)
    with get_context("fork").Pool(min(processes, PROTOCOL["max_processes"])) as pool:
        rows = pool.map(trial, jobs, chunksize=200)
        sizes = pool.map(look_size, [(s, i) for s in ("gauss", "ar", "sparse") for i in range(size_draws)], chunksize=200)
    return rows, sizes, P, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--dev", action="store_true")
    parser.add_argument("--receipt", default=str(RECEIPT))
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--processes", type=int, default=8)
    parser.add_argument("--reps", type=int, default=2, help="--dev only: the null replications")
    args = parser.parse_args(argv)
    receipt = Path(args.receipt)
    if args.freeze:
        doc = freeze(receipt, args.db)
        print(json.dumps({"receipt": str(receipt), "tree_head": doc["tree_head"], "sha256": doc["sha256"]}, indent=1))
        return 0
    if args.dev:
        reps = {"null": args.reps, "drift_only": max(1, args.reps // 2), "planted": max(1, args.reps // 2)}
        t0 = time.time()
        rows, sizes, P, meta = execute(args.db, reps, args.processes, 300)
        analysis = analyze(rows, sizes, P, meta)
        print(json.dumps({"seconds": round(time.time() - t0, 1), "accepted": analysis["accepted"],
                          "worlds": {w: x["screen_eligible"] for w, x in analysis["worlds"].items()},
                          "power": {S: x["screen_eligible"]["rate"] for S, x in analysis["power"].items()}}, indent=1))
        return 0
    doc = json.loads(receipt.read_text())
    if doc.get("input_db") != args.db:
        args.db = doc["input_db"]
    now = hashes(args.db)
    differ = sorted(k for k, v in doc["sha256"].items() if now.get(k) != v)
    if differ:
        raise SystemExit(f"refused: these differ from the frozen receipt {receipt.name}: {', '.join(differ)}")
    if doc["protocol"] != json.loads(json.dumps(PROTOCOL)):
        raise SystemExit("refused: the protocol differs from the frozen receipt")
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    rows, sizes, P, meta = execute(args.db, PROTOCOL["reps"], args.processes, PROTOCOL["look_size_draws"])
    analysis = analyze(rows, sizes, P, meta)
    result = {"receipt": {"name": doc["name"], "path": str(receipt.relative_to(REPO)) if receipt.is_relative_to(REPO) else str(receipt),
                          "tree_head": doc["tree_head"], "sha256": doc["sha256"]},
              "started_at": started, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "seconds": round(time.time() - t0, 1), "processes": min(args.processes, PROTOCOL["max_processes"]),
              "trials": len(rows), "constants": constants(), "analysis": analysis}
    base = receipt.with_suffix("")
    out_json = base.parent / f"{base.name}.result.json"
    out_md = base.parent / f"{base.name.upper()}.md"
    out_json.write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + "\n")
    out_md.write_text(markdown(result))
    print(json.dumps({"accepted": analysis["accepted"], "result": str(out_json), "report": str(out_md),
                      "seconds": result["seconds"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
