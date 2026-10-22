#!/usr/bin/env python
"""meta_spec.py: the REFERENCE SPEC of PREREG-EVL-8's meta-learners (EVL-META-O1, EVL-META-ON), standard library only,
pure functions over row dicts shaped like league/events/store.py's tables. It is the text of the design as code: the
House's league/events/meta.py ports it. A synthetic self-test at the bottom (no lane data is read here).

THE DECISION of entry session D at decision time tau (09:15 ET for O1; the close less 14 minutes for ON):
  pool    = members (one per issuer) of the auction's SOURCES' intents of D            (pool_members)
  feats   = the member's binary features from rows stored before tau                  (features)
  state   = per sub-rule (A, G, NB) over the sessions that ENTERED by tau             (state)
  walk    = qualifying sub-rules by LCB, each giving its eligible members until K     (walk)
Every input is filtered by its stored / answered / settled time < tau; nothing is random; ties are fixed.
"""
from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------------------------- registered constants
K = 16                 # picks a decision at most (the shadow record; real money takes its room in this order)
H = 60.0               # half-life of a session's weight, in sessions entered
TAU = 0.0030           # prior sd of a sub-rule's relative edge (after cost, per event)
SF = 0.0020            # block-noise floor of a relative block (sector and style clustering)
Z = 3.0                # the lower confidence bound's multiplier
HURDLE = 0.0           # a sub-rule qualifies when -cbar + LCB > HURDLE
MINB = 3               # settled blocks a sub-rule needs to be awake
WARM = 10              # no pick at the first WARM entry sessions after the registration (the state builds)
WINSOR = 0.10          # within-session deviations clipped at +-10% for the variance estimate
VAR_FLOOR = 0.015 ** 2
IMPUTE_AFTER = 3       # sessions after a session's scheduled exit before its unsettled TRADABLE members are imputed
IMPUTE_A = -0.30       # ... at a = -30% (the reading that trades less), replaced by the settled value once settled
ISSUER_GAP = 5         # PREREG-EVL-1 section 5's one position per issuer per program, as the shadow keeps it

# ---------------------------------------------------------------------------------------------- the vocabulary
GROUPS_O1: dict[str, tuple[str, ...]] = {
    "FAM": ("news-on", "news-day", "8k", "ern", "ins", "price"),
    "SCORE": ("s>=1", "s>=2", "s=3", "s<=-1", "smiss"),
    "GUIDE": ("raised", "lowered"),
    "SRC": ("bz", "other"),
    "HOUR": ("h16-20", "h20-04", "h04-08", "h08-0930", "h0930-12", "h12-16"),
    "COV": ("c0", "c1-3", "c4+"),
    "LIQ": ("adv<10M", "adv10-100M", "adv>=100M"),
    "PX": ("px<10", "px10-50", "px>=50"),
    "VOL": ("sd<2%", "sd2-4%", "sd>=4%"),
    "R5": ("r5<=-5%", "r5mid", "r5>=+5%"),
    "R20": ("r20<=-10%", "r20mid", "r20>=+10%"),
}
GROUPS_ON: dict[str, tuple[str, ...]] = dict(GROUPS_O1, REACT=("re<=0.96", "remid", "re>=1.04"),
                                             GAP=("gap<=0.98", "gapmid", "gap>=1.02"))


def group_of(groups: Mapping[str, Sequence[str]]) -> dict[str, str]:
    return {f: g for g, fs in groups.items() for f in fs}


def grid_rules(groups: Mapping[str, Sequence[str]]) -> list[str]:
    """Every single feature and every pair of features of DIFFERENT groups, as ids 'g:<f>' and 'g:<f1>&<f2>' (the two
    names in Python string order). O1: 39 features, 720 sub-rules; ON: 45 and 969 (grid_count.py)."""
    gof = group_of(groups)
    feats = sorted(gof)
    out = [f"g:{f}" for f in feats]
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            if gof[a] != gof[b]:
                out.append(f"g:{a}&{b}")
    return out


def _bin3(x: float | None, lo: float, hi: float, names: Sequence[str]) -> str | None:
    if x is None or not math.isfinite(x):
        return None
    return names[0] if x <= lo else (names[2] if x >= hi else names[1])


def et_hour_bin(hour: int, minute: int) -> str:
    hm = hour * 60 + minute
    if 16 * 60 <= hm < 20 * 60:
        return "h16-20"
    if hm >= 20 * 60 or hm < 4 * 60:
        return "h20-04"
    if hm < 8 * 60:
        return "h04-08"
    if hm < 9 * 60 + 30:
        return "h08-0930"
    if hm < 12 * 60:
        return "h0930-12"
    return "h12-16"


def features(m: Mapping, auction: str) -> frozenset[str]:
    """The binary features of a pool member, from its stored-before-tau inputs (m: the member's EVENT row and its
    inputs, all already filtered by tau): fam, score (an `ok` verdict answered before tau, else None), guidance, source
    (news), knowable hour (ET, (h, m)), cov72 (single-symbol articles naming the symbol knowable in the 72 h before the
    event, stored before tau, the event excluded), adv20, prev_close (the universe row of D), closes20 (the 20 raw
    closes before D, oldest first, from the bars table, fetched before tau), and for ON: react (the stored 15:30 mark
    of D over prev_close) and gap (the stored 09:30 mark of D over prev_close). An input that is missing switches its
    group off (no feature of that group), except SCORE, whose 'smiss' says no score."""
    f: set[str] = set()
    fam = m.get("fam")
    if fam in GROUPS_O1["FAM"]:
        f.add(fam)
    s = m.get("score")
    if s is None:
        f.add("smiss")
    else:
        s = int(s)
        if s >= 1:
            f.add("s>=1")
        if s >= 2:
            f.add("s>=2")
        if s == 3:
            f.add("s=3")
        if s <= -1:
            f.add("s<=-1")
    g = m.get("guidance")
    if g in ("raised", "lowered"):
        f.add(g)
    if fam in ("news-on", "news-day"):
        src = str(m.get("source") or "").strip().lower()
        if src:
            f.add("bz" if src == "benzinga" else "other")
    hm = m.get("hour_et")
    if hm is not None:
        f.add(et_hour_bin(int(hm[0]), int(hm[1])))
    cov = m.get("cov72")
    if cov is not None:
        f.add("c0" if cov == 0 else ("c1-3" if cov <= 3 else "c4+"))
    adv = m.get("adv20")
    if adv is not None:
        f.add("adv<10M" if adv < 10e6 else ("adv10-100M" if adv < 100e6 else "adv>=100M"))
    px = m.get("prev_close")
    if px is not None:
        f.add("px<10" if px < 10 else ("px10-50" if px < 50 else "px>=50"))
    cl = m.get("closes20")
    if cl and len(cl) == 20 and all(c and c > 0 for c in cl):
        lr = [math.log(cl[i + 1] / cl[i]) for i in range(19)]
        mu = sum(lr) / 19
        sd = math.sqrt(sum((x - mu) ** 2 for x in lr) / 18)
        f.add("sd<2%" if sd < 0.02 else ("sd2-4%" if sd < 0.04 else "sd>=4%"))
        f.add(_bin3(cl[-1] / cl[-6] - 1.0, -0.05, 0.05, GROUPS_O1["R5"]))
        f.add(_bin3(cl[-1] / cl[0] - 1.0, -0.10, 0.10, GROUPS_O1["R20"]))
    if auction == "ON":
        if m.get("react") is not None:
            f.add(_bin3(m["react"], 0.96, 1.04, GROUPS_ON["REACT"]))
        if m.get("gap") is not None:
            f.add(_bin3(m["gap"], 0.98, 1.02, GROUPS_ON["GAP"]))
    return frozenset(x for x in f if x)


def rules_of(feats: Iterable[str], tags: Iterable[str], gof: Mapping[str, str]) -> set[str]:
    """The sub-rules a member satisfies: its singles, its cross-group pairs, and 'p:<program>:<version>' for every
    SOURCE that holds an intent on it (its tags)."""
    fs = sorted(feats)
    out = {f"g:{a}" for a in fs}
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            if gof[a] != gof[b]:
                out.add(f"g:{a}&{b}")
    out.update(f"p:{t}" for t in tags)
    return out


# ---------------------------------------------------------------------------------------------- the state
def session_stats(members: Sequence[Mapping]) -> tuple[dict[str, tuple[int, float]], int, float, float]:
    """One ENTERED session: members with keys rules (set), a (after-cost abnormal return, the judge's column) and
    tradable. Returns ({rule: (n, sum a)}, n_pool, P_s, the session's winsorised within variance)."""
    rows = [m for m in members if m.get("tradable")]
    n = len(rows)
    if n == 0:
        return {}, 0, 0.0, 0.0
    P = math.fsum(m["a"] for m in rows) / n
    var = math.fsum(min(max(m["a"] - P, -WINSOR), WINSOR) ** 2 for m in rows) / max(n - 1, 1)
    acc: dict[str, list] = {}
    for m in rows:
        for j in m["rules"]:
            c = acc.setdefault(j, [0, 0.0])
            c[0] += 1
            c[1] += m["a"]
    return {j: (c[0], c[1]) for j, c in acc.items()}, n, P, var


def state(sessions: Sequence[tuple[dict[str, tuple[int, float]], int, float, float]]) -> dict[str, tuple[float, float, int]]:
    """{rule: (A, G, NB)} over the ENTERED sessions in session order (the last is the newest, weight 1)."""
    var = [v for (_, n, _, v) in sessions if n > 0]
    s2 = max(VAR_FLOOR, (math.fsum(var) / len(var)) if var else VAR_FLOOR)
    N = len(sessions)
    out: dict[str, list] = {}
    for i, (stats, n, P, _) in enumerate(sessions):
        if n == 0:
            continue
        w = 2.0 ** (-(N - 1 - i) / H)
        for j, (nj, sj) in stats.items():
            rel = sj / nj - P
            V = SF ** 2 + s2 / nj
            c = out.setdefault(j, [0.0, 0.0, 0])
            c[0] += w / V
            c[1] += w * rel / V
            c[2] += 1
    return {j: (c[0], c[1], c[2]) for j, c in out.items()}


def posterior(A: float, G: float) -> tuple[float, float, float]:
    prec = A + TAU ** -2
    mean = G / prec
    sd = prec ** -0.5
    return mean, sd, mean - Z * sd


# ---------------------------------------------------------------------------------------------- the walk
def walk(members: Sequence[Mapping], st: Mapping[str, tuple[float, float, int]], cbar: float, *,
         session_index: int) -> list[tuple[str, str, float]]:
    """THE PICKS of one decision: [(event, rule, lcb)] in rank order. members: today's pool with keys event, cik,
    adv20, rules (set), eligible (TRADABLE at the decision, not held by the program within ISSUER_GAP sessions, a LIVE
    universe row). session_index: entry sessions since the registration (1 = the first)."""
    if session_index <= WARM:
        return []
    awake: dict[str, set] = {}
    for m in members:
        if not m.get("eligible"):
            continue
        for j in m["rules"]:
            awake.setdefault(j, set()).add(m["event"])
    qual = []
    for j in awake:
        A, G, NB = st.get(j, (0.0, 0.0, 0))
        if NB < MINB:
            continue
        mean, sd, lcb = posterior(A, G)
        if -cbar + lcb > HURDLE:
            qual.append((-lcb, -NB, j, lcb))
    qual.sort()
    order = sorted((m for m in members if m.get("eligible")), key=lambda m: (-float(m.get("adv20") or 0.0), m["event"]))
    taken: set[str] = set()
    ciks: set[str] = set()
    out = []
    for _, _, j, lcb in qual:
        for m in order:
            if len(out) >= K:
                return out
            if m["event"] in taken or m["cik"] in ciks or j not in m["rules"]:
                continue
            taken.add(m["event"])
            ciks.add(m["cik"])
            out.append((m["event"], j, lcb))
    return out


def cbar_of(members: Sequence[Mapping]) -> float:
    """The pool's mean replay round-trip cost (score.py: per side 0.5 bp + impact 5 bp when ADV >= $10M else 10 bp, plus
    the fees at the Probe notional), from rows known before tau; here the side costs as fractions."""
    xs = [float(m["cost_rt"]) for m in members if m.get("eligible") and m.get("cost_rt") is not None]
    return math.fsum(xs) / len(xs) if xs else 0.0


# ---------------------------------------------------------------------------------------------- self-test
def _selftest() -> None:
    import random
    rnd = random.Random(8)
    J = grid_rules(GROUPS_O1)
    assert len(J) == 720, len(J)
    assert len(grid_rules(GROUPS_ON)) == 969
    gof = group_of(GROUPS_ON)
    # a member's features and rules
    m = {"fam": "news-on", "score": 3, "source": "Benzinga", "hour_et": (6, 15), "cov72": 2, "adv20": 2.5e7,
         "prev_close": 14.2, "closes20": [10 + 0.1 * i for i in range(20)]}
    f = features(m, "O1")
    assert {"news-on", "s>=1", "s>=2", "s=3", "bz", "h04-08", "c1-3", "adv10-100M", "px10-50", "r5mid",
            "r20>=+10%"} <= f, f
    rl = rules_of(f, ["EVL-NEWS-READ-O1:2"], gof)
    assert "g:s=3" in rl and "g:adv10-100M&s>=2" in rl and "p:EVL-NEWS-READ-O1:2" in rl
    assert "g:s>=1&s>=2" not in rl            # same group: never a pair
    # the walk: the rule with the evidence takes the slots; nothing before WARM; a sleeping rule never qualifies
    feats_pool = []
    for i in range(200):
        fam = rnd.choice(["news-on", "8k", "ern"])
        sc = rnd.choice([None, -1, 0, 1, 2, 3])
        mm = {"fam": fam, "score": sc, "hour_et": (rnd.randrange(24), 0), "adv20": rnd.choice([5e6, 5e7, 5e8]),
              "prev_close": rnd.choice([5.0, 20.0, 80.0])}
        feats_pool.append(features(mm, "O1"))
    sessions = []
    true_rule = "g:adv>=100M&s>=2"
    for s in range(30):
        mem = []
        for i, fs in enumerate(feats_pool):
            rules = rules_of(fs, [], gof)
            a = rnd.gauss(0.0, 0.03) + (0.006 if true_rule in rules else -0.0014)
            mem.append({"rules": rules, "a": a, "tradable": True})
        sessions.append(session_stats(mem))
    st = state(sessions)
    today = [{"event": f"news:{i}", "cik": str(i), "adv20": 1e6 * i, "rules": rules_of(fs, [], gof), "eligible": True}
             for i, fs in enumerate(feats_pool)]
    assert walk(today, st, 0.0014, session_index=WARM) == []
    picks = walk(today, st, 0.0014, session_index=WARM + 1)
    hit = sum(1 for e, j, _ in picks if true_rule in today[int(e.split(':')[1])]["rules"])
    print(f"selftest: {len(picks)} picks, {hit} inside the true rule; top rule {picks[0][1] if picks else None}")
    assert "g:never-seen" not in st
    print("selftest ok")


if __name__ == "__main__":
    _selftest()
