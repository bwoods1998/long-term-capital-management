"""Part B: Merton passes by role, and whether Jev over the REQUEST text predicts 'this pass produced nothing'.

Train = passes Sept 22-23 (question choice, direction and threshold fitted there only); held-out = Sept 24 00:00Z - Sept 25 06:00Z.
Two labels: `nothing` (no artifact: no strategy file / PR / cards / lesson) and `no_yield` (no downstream result: for a consult,
code AND a retained candidate AND a replay pass; for the engineer, a PR whose repair reached canary/observing/verified within 24 h;
for architect/teacher/..., a merged PR; for the foundry, cards written). Writes merton_results.md / .json.
"""
import json
import math
from collections import Counter, defaultdict

from common import TRAIN_END, WINDOW_END, WINDOW_START, load
from phr_merton import Q
from stats import auc, boot_auc, fmt, logistic

M = [json.loads(l) for l in open("merton.jsonl")]
J = json.load(open("jev_merton.json"))
for m in M:
    m["no_yield"] = not m["yield_"]
    for qid, (sign, _) in Q.items():
        p = J.get(f"j2m:{qid}:{m['seq']}")
        m[qid] = None if p is None else (p if sign > 0 else 1 - p)  # oriented: high = predicts nothing
lines = []


def out(x=""):
    lines.append(x)
    print(x)


train = [m for m in M if m["split"] == "train"]
test = [m for m in M if m["split"] == "test"]

# ------------------------------------------------------------------ counts by role (plus the auditor from audit.verdict)
out("## Part B results (Merton)\n")
out("### B1. Passes by role, Sept 22 00:00Z - Sept 25 06:00Z\n")
out("| role | passes | $ | errors | produced an artifact | downstream yield | 'nothing' passes | $ on 'nothing' | train / held-out passes |")
out("|---|---|---|---|---|---|---|---|---|")
roles = defaultdict(list)
for m in M:
    roles[m["role"]].append(m)
for role, g in sorted(roles.items(), key=lambda kv: -sum(x["cost"] for x in kv[1])):
    usd = sum(x["cost"] for x in g)
    nothing = [x for x in g if x["nothing"]]
    out(f"| {role} | {len(g)} | {usd:.2f} | {sum(x['error'] for x in g)} | {sum(x['produced'] for x in g)} | {sum(x['yield_'] for x in g)} | "
        f"{len(nothing)} | {sum(x['cost'] for x in nothing):.2f} | {sum(x['split'] == 'train' for x in g)} / {sum(x['split'] == 'test' for x in g)} |")
audits = [r for r in load("eval") if r["kind"] == "audit.verdict" and WINDOW_START <= r["at"] < WINDOW_END]
out(f"| auditor (audit.verdict) | {len(audits)} | {sum(float(a['p'].get('cost_usd') or 0) for a in audits):.2f} | - | "
    f"{sum(1 for a in audits if a['p'].get('approve'))} approvals | - | - | - | not asked (a refusal is a product) |")
out("\nConsultant detail: " + json.dumps(Counter(
    ("code" if x["produced"] else "no code") + (" + candidate" if x.get("candidate") else "") + (" + replay passed" if x.get("replay_passed") else "")
    for x in roles["consultant"])))
out("Engineer later repair states (within 24 h) for passes that opened a PR: " + json.dumps(Counter(
    ",".join(x.get("later_states") or ["none"]) for x in roles["engineer"] if x["produced"])))

# ------------------------------------------------------------------ Jev AUCs
def rate(rows, key, label, prior=5):
    base = sum(label(r) for r in rows) / max(1, len(rows))
    n, k = Counter(), Counter()
    for r in rows:
        n[key(r)] += 1
        k[key(r)] += label(r)
    return lambda v: (k[v] + prior * base) / (n[v] + prior) if v in n else base


def section(label_name, rows_tr, rows_te, title):
    label = lambda r: r[label_name]
    out(f"\n### {title}: label `{label_name}` (1 = the pass produced nothing)\n")
    out(f"train n {len(rows_tr)} ({sum(label(r) for r in rows_tr)} nothing, ${sum(r['cost'] for r in rows_tr):.2f}); "
        f"held-out n {len(rows_te)} ({sum(label(r) for r in rows_te)} nothing, ${sum(r['cost'] for r in rows_te):.2f})\n")
    role_rate = rate(rows_tr, lambda r: r["role"], label)
    # Each question's direction is chosen on TRAIN (pre-registered sign flipped when its train AUC is below 0.5).
    scores, flipped = {}, []
    for qid in Q:
        a_tr = auc([r[qid] for r in rows_tr], [label(r) for r in rows_tr])
        if a_tr is not None and a_tr < 0.5:
            scores[qid + " (flipped on train)"] = (lambda q: lambda r: 1 - r[q])(qid)
            flipped.append(qid)
        else:
            scores[qid] = (lambda q: lambda r: r[q])(qid)
    scores["role (train rate)"] = lambda r: role_rate(r["role"])
    scores["engineer: attempt>1 or an earlier empty pass on the key"] = lambda r: 1.0 if (r["det"].get("attempt", 0) > 1 or r["det"].get("prior_empty_on_key", 0) > 0) else 0.0
    scores["consultant: agent consulted before"] = lambda r: 1.0 if r["det"].get("prior_consults", 0) > 0 else 0.0
    scores["request mentions missing data (regex)"] = lambda r: 1.0 if r["det"].get("q_missing") else 0.0
    out("| score (high = predicts nothing) | train AUC | held-out AUC [95% clustered by requester] |")
    out("|---|---|---|")
    tr_auc = {}
    for name, f in scores.items():
        a_tr = auc([f(r) for r in rows_tr], [label(r) for r in rows_tr])
        a_te = boot_auc(rows_te, f, label, cluster="agent", reps=500) if 0 < sum(label(r) for r in rows_te) < len(rows_te) else (None, None, None)
        tr_auc[name] = a_tr
        out(f"| {name} | {a_tr:.3f} | {fmt(a_te)} |" if a_tr is not None else f"| {name} | n/a | {fmt(a_te)} |")
    jev_names = [n for n in scores if n.split(" ")[0] in Q]
    best_q = max(jev_names, key=lambda q: tr_auc[q] if tr_auc[q] is not None else 0)
    out(f"\nQuestion chosen on train: `{best_q}` (train AUC {tr_auc[best_q]:.3f}).")
    # combined: role rate + chosen Jev question, logistic on train
    fq = scores[best_q]
    X = [[role_rate(r["role"]), fq(r)] for r in rows_tr]
    comb, w, _ = logistic(X, [1 if label(r) else 0 for r in rows_tr], iters=300)
    scores["role + jev (logistic)"] = lambda r: comb([role_rate(r["role"]), fq(r)])
    a_te = boot_auc(rows_te, scores["role + jev (logistic)"], label, cluster="agent", reps=500) if 0 < sum(label(r) for r in rows_te) < len(rows_te) else (None, None, None)
    out(f"Role + `{best_q}` logistic (weights {[round(x, 3) for x in w]}): held-out AUC {fmt(a_te)}\n")
    # skip rule: route to the cheap path when score >= t; t = the cut that skips the most TRAIN dollars with <= 10% of train useful passes lost
    out("Skip rule (route away from Merton when score ≥ t; t chosen on train as the cut that skips the most train dollars while losing ≤ 10% of train useful passes):\n")
    out("| score | t | train: passes/$ skipped, useful lost | held-out: passes/$ skipped, useful lost | held-out $ saved |")
    out("|---|---|---|---|---|")
    res = {}
    for name in (best_q, "role (train rate)", "role + jev (logistic)"):
        f = scores[name]
        useful_tr = [r for r in rows_tr if not label(r)]
        best = None
        for t in sorted(set(f(r) for r in rows_tr)) + [float("inf")]:
            sk = [r for r in rows_tr if f(r) >= t]
            lost = sum(1 for r in sk if not label(r)) / max(1, len(useful_tr))
            d = sum(r["cost"] for r in sk)
            if lost <= 0.10 and (best is None or d > best[1]):
                best = (t, d, len(sk), lost)
        t = best[0]
        def summ(rows):
            sk = [r for r in rows if f(r) >= t]
            useful = [r for r in rows if not label(r)]
            usd = sum(r["cost"] for r in rows)
            return (len(sk) / max(1, len(rows)), sum(r["cost"] for r in sk) / usd if usd else 0,
                    sum(1 for r in sk if not label(r)) / max(1, len(useful)), sum(r["cost"] for r in sk))
        a, b = summ(rows_tr), summ(rows_te)
        res[name] = {"t": t, "train": a, "test": b}
        out(f"| {name} | {t:.3g} | {a[0]:.0%}/{a[1]:.0%}, {a[2]:.0%} | {b[0]:.0%}/{b[1]:.0%}, {b[2]:.0%} | ${b[3]:.2f} |")
    return {"train_auc": tr_auc, "best_q": best_q, "skip": res}


results = {}
for label_name in ("nothing", "no_yield"):
    results[label_name] = section(label_name, train, test, "B2. All roles")
for role in ("consultant", "engineer"):
    tr = [m for m in train if m["role"] == role]
    te = [m for m in test if m["role"] == role]
    for label_name in ("nothing", "no_yield"):
        if 0 < sum(m[label_name] for m in tr) < len(tr):
            results[f"{role}:{label_name}"] = section(label_name, tr, te, f"B3. {role} only")
json.dump(results, open("merton_results.json", "w"), default=str)
open("merton_results.md", "w").write("\n".join(lines) + "\n")
