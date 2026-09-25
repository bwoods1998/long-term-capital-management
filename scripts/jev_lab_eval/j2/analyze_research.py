"""Part A, step 4: does Jev's p (frozen question p3) tell which research sessions are worth buying?

Train = sessions that started Sept 22-23 (every threshold and model weight is fitted there only);
held-out = Sept 24 00:00Z - Sept 25 06:00Z. Writes research_results.md (tables) and research_results.json.
"""
import json
import math
from collections import Counter, defaultdict

from stats import auc, boot_auc, fmt, logistic

S = [json.loads(l) for l in open("sessions.jsonl")]
J = json.load(open("jev_research.json"))
for s in S:
    s["p"] = J.get(s["session"])
POP = [s for s in S if s["source"] == "run" and s["p"] is not None]
POP_R = [s for s in S if s["source"] in ("run", "refusal_prompt") and s["p"] is not None]
OWN = ("book.settle", "book.fill", "book.refused", "refusal_prompt")
lines = []


def out(x=""):
    lines.append(x)
    print(x)


def train(rows):
    return [r for r in rows if r["split"] == "train"]


def test(rows):
    return [r for r in rows if r["split"] == "test"]


# ------------------------------------------------------------------ deterministic features
def rate_table(rows, key, label, prior=20):
    """Smoothed train rate of `label` per value of `key` (unseen values get the overall rate)."""
    base = sum(label(r) for r in rows) / max(1, len(rows))
    n, k = Counter(), Counter()
    for r in rows:
        n[key(r)] += 1
        k[key(r)] += label(r)
    return (lambda v: (k[v] + prior * base) / (n[v] + prior) if v in n else base), base


def features(r, tables):
    kind_rate, rec_rate, prev_rate = tables
    streak = r["streak"] if r["streak"] is not None else 0
    return [kind_rate(r["kind"]), math.log1p(streak), rec_rate(r["record"] or "none"),
            1.0 if (r["n_fill"] or r["n_settle"]) else 0.0, prev_rate(r["prev_outcome"] or "none"),
            1.0 if r["any_new"] else 0.0, math.log1p(r["hours_since_prev"] or 0.0)]


FEATURE_NAMES = ["kind_rate", "log1p_streak", "record_rate", "fills_or_settles", "prev_outcome_rate", "any_new", "log1p_hours_since_prev"]


def build_scores(rows, label):
    """Fit on train rows only; return dict name -> scorer(row) (higher = more worth running)."""
    tr = train(rows)
    y = [1 if label(r) else 0 for r in tr]
    kind_rate, _ = rate_table(tr, lambda r: r["kind"], label)
    rec_rate, _ = rate_table(tr, lambda r: r["record"] or "none", label)
    prev_rate, _ = rate_table(tr, lambda r: r["prev_outcome"] or "none", label)
    tables = (kind_rate, rec_rate, prev_rate)
    X = [features(r, tables) for r in tr]
    det, wd, _ = logistic(X, y)
    comb, wc, _ = logistic([x + [r["p"]] for x, r in zip(X, tr)], y)
    raw = {
        "jev_p": lambda r: r["p"],
        "trigger_kind": lambda r: kind_rate(r["kind"]),
        "streak (neg)": lambda r: -(r["streak"] or 0),
        "record_class": lambda r: rec_rate(r["record"] or "none"),
        "fills_or_settles": lambda r: 1.0 if (r["n_fill"] or r["n_settle"]) else 0.0,
        "any_new_evidence": lambda r: 1.0 if r["any_new"] else 0.0,
        "prev_outcome": lambda r: prev_rate(r["prev_outcome"] or "none"),
        "deterministic_model": lambda r: det(features(r, tables)),
        "det_model+jev": lambda r: comb(features(r, tables) + [r["p"]]),
    }
    cached = {}
    for name, f in raw.items():
        values = {r["session"]: f(r) for r in rows}
        cached[name] = (lambda v: (lambda r: v[r["session"]]))(values)
    return cached, {"deterministic": dict(zip(FEATURE_NAMES, [round(w, 3) for w in wd])),
        "combined": dict(zip(FEATURE_NAMES + ["jev_p"], [round(w, 3) for w in wc]))}


def thresholds(rows, score):
    """(threshold, train skip share, dollars, o1 lost, o2 lost) for every distinct cut `score < t` on train rows, via cumulative sums."""
    rs = sorted(rows, key=score)
    n, usd = len(rs), sum(r["cost"] for r in rs)
    o1, o2 = sum(r["o1"] for r in rs), sum(r["o2"] for r in rs)
    out_, i, cn, cu, c1, c2 = [], 0, 0, 0.0, 0, 0
    while i <= n:
        t = score(rs[i]) if i < n else float("inf")
        out_.append((t, cn / n, cu / usd if usd else 0, c1 / o1 if o1 else 0, c2 / o2 if o2 else 0))
        if i == n:
            break
        j = i
        while j < n and score(rs[j]) == t:
            cn += 1; cu += rs[j]["cost"]; c1 += rs[j]["o1"]; c2 += rs[j]["o2"]
            j += 1
        i = j
    return out_


def skip_curve(rows, score, targets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)):
    """Thresholds chosen on train: the cut whose train skip share is closest to q (ties kept whole); applied to held-out."""
    tr, te = train(rows), test(rows)
    cuts = thresholds(tr, score)
    res = []
    for q in targets:
        t = min(cuts, key=lambda c: abs(c[1] - q))[0]
        res.append((q, t) + tuple(apply(te, score, t)) + tuple(apply(tr, score, t)))
    return res


def apply(rows, score, t):
    skipped = [r for r in rows if score(r) < t]
    n, usd = len(rows), sum(r["cost"] for r in rows)
    o1, o2 = sum(r["o1"] for r in rows), sum(r["o2"] for r in rows)
    return (len(skipped) / n if n else 0, sum(r["cost"] for r in skipped) / usd if usd else 0,
            sum(r["o1"] for r in skipped) / o1 if o1 else 0, sum(r["o2"] for r in skipped) / o2 if o2 else 0)


def best_under(rows, score, max_o2_loss=0.10):
    """The cut that skips the most TRAIN dollars with train o2 loss <= max_o2_loss; its held-out result."""
    tr, te = train(rows), test(rows)
    ok = [c for c in thresholds(tr, score) if c[4] <= max_o2_loss]
    if not ok:
        return None
    best = max(ok, key=lambda c: c[2])
    return {"threshold": best[0], "train": best[1:], "test": apply(te, score, best[0])}


def section(rows, title):
    out(f"\n### {title}\n")
    tr, te = train(rows), test(rows)
    out(f"n train {len(tr)} (o1 {sum(r['o1'] for r in tr)}, o2 {sum(r['o2'] for r in tr)}, ${sum(r['cost'] for r in tr):.2f}); "
        f"n held-out {len(te)} (o1 {sum(r['o1'] for r in te)}, o2 {sum(r['o2'] for r in te)}, ${sum(r['cost'] for r in te):.2f}); "
        f"held-out agents {len(set(r['agent'] for r in te))}\n")
    mp = lambda rr: sum(r["p"] for r in rr) / max(1, len(rr))
    out(f"Mean Jev p: train {mp(tr):.3f}, held-out {mp(te):.3f}; share p<0.1: train {sum(r['p'] < 0.1 for r in tr) / max(1, len(tr)):.0%}, held-out {sum(r['p'] < 0.1 for r in te) / max(1, len(te)):.0%}\n")
    scores2, w2 = build_scores(rows, lambda r: r["o2"])
    scores1, _ = build_scores(rows, lambda r: r["o1"])
    out("| score (higher = run) | AUC o1 held-out [95% agent-clustered] | AUC o2 held-out | AUC o2 train |")
    out("|---|---|---|---|")
    res = {}
    for name in scores2:
        a1 = boot_auc(te, scores1[name], lambda r: r["o1"])
        a2 = boot_auc(te, scores2[name], lambda r: r["o2"])
        a2t = auc([scores2[name](r) for r in tr], [r["o2"] for r in tr])
        res[name] = {"o1_test": a1, "o2_test": a2, "o2_train": a2t}
        out(f"| {name} | {fmt(a1)} | {fmt(a2)} | {a2t:.3f} |" if a2t is not None else f"| {name} | {fmt(a1)} | {fmt(a2)} | n/a |")
    out(f"\nLogistic weights (standardized features, fitted on train, label o2): {json.dumps(w2)}\n")
    out("Skip curve on the held-out window (threshold = the train quantile that skips share q of train sessions; "
        "skip when score < threshold). Columns: held-out share of sessions skipped / dollars skipped / candidates (o1) lost / replay passes (o2) lost.\n")
    out("| score | q=0.1 | q=0.2 | q=0.3 | q=0.4 | q=0.5 | q=0.6 | q=0.7 | q=0.8 | q=0.9 |")
    out("|---|---|---|---|---|---|---|---|---|---|")
    curves = {}
    for name in ("jev_p", "trigger_kind", "prev_outcome", "deterministic_model", "det_model+jev"):
        cv = skip_curve(rows, scores2[name])
        curves[name] = cv
        cells = [f"{c[2]:.0%}/{c[3]:.0%}/{c[4]:.0%}/{c[5]:.0%}" for c in cv]
        out(f"| {name} | " + " | ".join(cells) + " |")
    out("\nThe ≥30% dollars / ≤10% replay-pass test: threshold = the one that skips the most TRAIN dollars with train o2 loss ≤ 10%, applied unchanged to held-out.\n")
    out("| score | threshold | train: sessions/dollars/o1/o2 skipped | held-out: sessions/dollars/o1/o2 skipped | meets ≥30% $ and ≤10% o2 on held-out? |")
    out("|---|---|---|---|---|")
    bests = {}
    for name in ("jev_p", "trigger_kind", "prev_outcome", "deterministic_model", "det_model+jev"):
        b = best_under(rows, scores2[name])
        bests[name] = b
        if b is None:
            out(f"| {name} | none | | | |")
            continue
        tr_, te_ = b["train"], b["test"]
        ok = te_[1] >= 0.30 and te_[3] <= 0.10
        out(f"| {name} | {b['threshold']:.4g} | {tr_[0]:.0%}/{tr_[1]:.0%}/{tr_[2]:.0%}/{tr_[3]:.0%} | {te_[0]:.0%}/{te_[1]:.0%}/{te_[2]:.0%}/{te_[3]:.0%} | {'yes' if ok else 'no'} |")
    return {"auc": res, "curves": curves, "best": bests, "weights": w2}


def by_kind(rows):
    out("\n### Jev p by trigger kind (held-out AUC within kind; kinds with ≥20 sessions and ≥3 of each class)\n")
    out("| trigger kind | split | n | $ | o1 | o2 | mean p | AUC o1 | AUC o2 |")
    out("|---|---|---|---|---|---|---|---|---|")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["kind"], r["split"])].append(r)
    for (kind, split), g in sorted(groups.items(), key=lambda kv: (kv[0][1], -len(kv[1]))):
        o1, o2 = sum(r["o1"] for r in g), sum(r["o2"] for r in g)
        mp = sum(r["p"] for r in g) / len(g)
        a1 = boot_auc(g, lambda r: r["p"], lambda r: r["o1"], reps=300) if len(g) >= 20 and 3 <= o1 <= len(g) - 3 else (None, None, None)
        a2 = boot_auc(g, lambda r: r["p"], lambda r: r["o2"], reps=300) if len(g) >= 20 and 3 <= o2 <= len(g) - 3 else (None, None, None)
        out(f"| {kind} | {split} | {len(g)} | {sum(r['cost'] for r in g):.2f} | {o1} | {o2} | {mp:.2f} | {fmt(a1)} | {fmt(a2)} |")


results = {}
out("## Part A results (research sessions)")
results["gate_runs"] = section(POP, "A1. Population as specified: gate `run` sessions (non-sampled)")
by_kind(POP_R)
results["gate_runs_plus_refusal"] = section(POP_R, "A2. Gate runs plus the House's refusal fast path (F2 routes it through the gate)")
F2 = [r for r in POP_R if r["f2_would"]]
results["f2_surviving"] = section(F2, "A3. F2-surviving subset: sessions of A2 that F2's rules 9-12 would still run (replayed)")
NOTF2 = [r for r in POP_R if r["f2_would"] is False]
out(f"\nF2 drop (A2 minus A3), held-out: {len(test(NOTF2))} sessions, ${sum(r['cost'] for r in test(NOTF2)):.2f}, "
    f"o1 {sum(r['o1'] for r in test(NOTF2))}, o2 {sum(r['o2'] for r in test(NOTF2))}; "
    f"mean Jev p {sum(r['p'] for r in test(NOTF2)) / max(1, len(test(NOTF2))):.2f} vs {sum(r['p'] for r in test(F2)) / max(1, len(test(F2))):.2f} on the survivors")
json.dump(results, open("research_results.json", "w"), default=str)
open("research_results.md", "w").write("\n".join(lines) + "\n")
