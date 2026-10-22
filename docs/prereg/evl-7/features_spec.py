"""FEATURES-R2 reference spec (design-reader lens): the deterministic, model-free features of an event, the R2 and T2
read sets, and the outcome-free hash. Pure functions over row dicts shaped like league/events/store.py's tables; a
synthetic self-test at the bottom. Nothing here reads the lane's store.

Every feature of an event e (knowable time tau) is computed from rows whose knowable time is BEFORE tau and which were
STORED before the decision that first reads it (the lane's stored-before rule, A72); the value is written once
(table `features`, additive) with its computation time, and never recomputed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import re

SALT = "R2|"
STOP = frozenset("the and for with from that this its are was has have will into over after amid about stock shares "
                 "inc corp co ltd plc company announces reports says".split())
#: Headline flags (case-insensitive), frozen.
KEYWORDS = {
    "kw_upgrade": r"\bupgrade[sd]?\b", "kw_downgrade": r"\bdowngrade[sd]?\b", "kw_initiate": r"\binitiat\w*",
    "kw_pt": r"\bprice target\b", "kw_raise": r"\b(raises?|raised|boosts?|lifts?)\b",
    "kw_cut": r"\b(lowers?|lowered|cuts?|slashes?|reduces?)\b", "kw_beat": r"\bbeats?\b", "kw_miss": r"\bmiss(es)?\b",
    "kw_fda": r"\b(fda|approval|approves?|cleared)\b", "kw_deal": r"\b(acquir\w*|merger|to buy|buyout|takeover)\b",
    "kw_offering": r"\b(offering|private placement|at-the-market)\b",
    "kw_buyback": r"\b(buyback|repurchase)\b", "kw_dividend": r"\bdividend\b", "kw_contract": r"\b(contract|awarded)\b",
    "kw_guidance": r"\b(guidance|outlook|sees|forecast)\b",
    "kw_move": r"(shares are trading|stock is (moving|trading|up|down)|why is|shares (rise|fall|jump|drop|slide|soar)"
               r"|trading (higher|lower)|\bmovers?\b)",
}
_KW = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}
ITEMS = ("1.01", "1.02", "2.01", "2.02", "2.03", "3.02", "5.02", "7.01", "8.01", "9.01")


def h(event: str) -> float:
    """The outcome-free uniform hash of an event id in [0, 1): fixed salt, SHA-256, first 8 bytes."""
    return int.from_bytes(hashlib.sha256((SALT + event).encode("utf-8")).digest()[:8], "big") / 2.0 ** 64


def words(headline: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", (headline or "").lower()) if w not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def meta(event: dict, prior_news: list[dict], prior_8k: list[dict], prior_f4_buys: list[dict], universe: dict,
         window_load: int, ern_load: int, v1: dict | None, decided_at: dt.datetime) -> dict:
    """The model-free features of one event. `prior_news`: articles naming the event's ticker (any number of symbols)
    with knowable_at in [tau - 72h, tau); `prior_8k`: the issuer's 8-Ks knowable in [tau - 72h, tau); `prior_f4_buys`:
    the issuer's PREREG-EVL-2 INSIDER BUY Form 4s knowable in [tau - 10d, tau); `universe`: the issuer's row for the
    entry session (prev_close, adv20, sigma60, bench); `v1`: the stored v1 verdict row or None."""
    tau = event["knowable_at"]
    et = tau - dt.timedelta(hours=4)          # (EDT; the House uses zoneinfo America/New_York)
    out = {"hour_et": et.hour, "dow": et.weekday(), "after_hours": int(et.hour >= 16 or (et.hour, et.minute) < (9, 30)),
           "log_adv20": math.log(max(1.0, float(universe["adv20"]))),
           "log_prev_close": math.log(max(0.01, float(universe["prev_close"]))),
           "sigma60": universe.get("sigma60"), "bench_iwm": int(universe.get("bench") == "IWM"),
           "window_load": window_load, "ern_load": ern_load}
    day = tau - dt.timedelta(hours=24)
    out["cov_24h"] = sum(1 for a in prior_news if a["knowable_at"] >= day)
    out["cov_72h"] = len(prior_news)
    out["src_72h"] = len({a.get("source") for a in prior_news})
    out["f8k_72h"] = len(prior_8k)
    out["ern_72h"] = sum(1 for f in prior_8k if "2.02" in f.get("items", []))
    out["ins_buy_10d"] = int(bool(prior_f4_buys))
    if event["kind"] == "news":
        w = words(event.get("headline", ""))
        out["dup_72h"] = max([jaccard(w, words(a.get("headline", ""))) for a in prior_news], default=0.0)
        out["src_fiscal"] = int(event.get("source") == "fiscal.ai")
        out["src_benzinga"] = int(event.get("source") == "benzinga")
        out["summary_len"] = len(event.get("summary") or "")
        for k, rx in _KW.items():
            out[k] = int(bool(rx.search(event.get("headline", ""))))
    else:
        items = set(event.get("items", []))
        for it in ITEMS:
            out["item_" + it.replace(".", "_")] = int(it in items)
        out["n_items"] = len(items)
        out["log_text_len"] = math.log(1 + float(event.get("text_len") or 0))
        out["ex99"] = int(str(event.get("doc_kind") or "").upper().startswith("EX-99"))
    if v1 is not None and v1.get("status") == "ok" and v1.get("answered_at") and v1["answered_at"] <= decided_at:
        out["v1_score"] = v1["score"]
        out["v1_guidance"] = v1.get("guidance")
        out["v1_missing"] = 0
    else:
        out["v1_score"], out["v1_guidance"], out["v1_missing"] = 0, None, 1
    return out


def derived(r2: dict | None, universe: dict, kind: str) -> dict:
    """Features derived from a stored R2 read and the universe row (both knowable before the decision)."""
    if r2 is None:
        return {"r2_missing": 1}
    out = {"r2_missing": 0}
    pc = float(universe["prev_close"])
    if kind == "news":
        new, old = r2.get("pt_new"), r2.get("pt_old")
        out["pt_upside"] = (new / pc - 1.0) if (new and pc > 0) else None
        out["pt_chg"] = (new / old - 1.0) if (new and old) else None
    else:
        deal = r2.get("deal_usd_m")
        out["deal_rel_adv20"] = (deal * 1e6 / (20.0 * float(universe["adv20"]))) if deal else None
    return out


#: THE R2 SET's per-window rule (prereg clause R.4): cap, the most of (b) [v1 score >= 2 by (score desc, h asc)], and the
#: hash share of (c). ern and ern_close read every candidate (a). The caps and the share scale by m (clause R.5).
WINDOWS = {"news_open": (160, 120, 1 / 8), "news_day": (60, 0, 1 / 16), "8k": (20, 0, 1 / 16), "ern": (90, None, None)}


def r2_set(window: str, candidates: list[dict], m: float = 1.0) -> list[str]:
    """THE R2 READ SET of one decision window (8k_open and 8k_close share "8k"; ern and ern_close share "ern"), in ASK
    ORDER. Candidates: the window control's events (one article an issuer for news windows), eligible and TRADABLE,
    each with `v1_ok` and `v1_score` (its stored PROMPT-DOC / PROMPT-NEWS verdict). Outcome-free and deterministic: it
    reads only v1 scores and the hash."""
    cap, b_max, share = WINDOWS[window]
    cap = int(cap * m)
    if b_max is None:                                            # (a) every earnings 8-K, ascending h
        return [c["event"] for c in sorted(candidates, key=lambda c: h(c["event"]))][:cap]
    b_max = int(b_max * m)
    share = min(1.0, share * m)
    b = [c["event"] for c in sorted([c for c in candidates if c.get("v1_ok") and c["v1_score"] >= 2],
                                    key=lambda c: (-c["v1_score"], h(c["event"])))][:b_max]
    taken = set(b)
    rest = [c["event"] for c in sorted(candidates, key=lambda c: h(c["event"]))
            if h(c["event"]) < share and c["event"] not in taken]
    return (b + rest)[:cap]


def hash_sample(window: str, candidates: list[dict], read: set[str], m: float = 1.0) -> list[str]:
    """THE UNBIASED SAMPLE of a window for the reader study and the learners: the candidates with h below the window's
    realized threshold, the largest t <= share (times m) such that every candidate with h < t was read."""
    cap, b_max, share = WINDOWS[window]
    share = 1.0 if share is None else min(1.0, share * m)
    out = []
    for c in sorted(candidates, key=lambda c: h(c["event"])):
        if h(c["event"]) >= share or c["event"] not in read:
            break
        out.append(c["event"])
    return out


def t2_set(r2_reads: dict[str, dict], n_top: int = 12) -> list[str]:
    """THE T2 SET (EVL-R2-ERN-TOP-O1's cascade): of the ern window's candidates that pass that program's R2 filters
    (`r2_reads`: event -> stored ok R2 fields), the n_top by R2 p_up, then surprise, then h."""
    ok = {e: r for e, r in r2_reads.items() if r is not None}
    return sorted(ok, key=lambda e: (-ok[e]["p_up"], -ok[e]["surprise"], h(e)))[:n_top]


def cascade_rank(r2_reads: dict[str, dict], t2_reads: dict[str, dict], slots: int = 8) -> list[str]:
    """EVL-R2-ERN-TOP-O1's slots: the T2 set re-ranked by T2 p_up (an event with no stored ok T2 read ranks by its R2
    p_up on the same scale), then R2 p_up, then surprise, then h; the first `slots`."""
    top = t2_set(r2_reads)
    def key(e):
        t = t2_reads.get(e)
        return (-(t["p_up"] if t else r2_reads[e]["p_up"]), -r2_reads[e]["p_up"], -r2_reads[e]["surprise"], h(e))
    return sorted(top, key=key)[:slots]


if __name__ == "__main__":
    import random
    rnd = random.Random(7)
    cands = [{"event": f"news:{100000 + i}", "v1_ok": True, "v1_score": rnd.choice([-1, 0, 0, 1, 1, 2, 2, 3])}
             for i in range(515)]
    s1 = r2_set("news_open", cands)
    s2 = r2_set("news_open", list(reversed(cands)))
    print("r2_set size", len(s1), "deterministic under input order:", s1 == s2,
          "score>=2 share in set", round(sum(1 for c in cands if c["event"] in set(s1) and c["v1_score"] >= 2) / len(s1), 3),
          "hash members", sum(1 for e in s1 if h(e) < 1 / 8))
    hs_ = hash_sample("news_open", cands, set(s1))
    print("hash sample", len(hs_), "all below threshold read:", all(e in set(s1) for e in hs_))
    reads = {e: {"p_up": rnd.choice(range(0, 101, 5)), "surprise": rnd.randint(-3, 3)} for e in s1[:40]}
    t2 = {e: {"p_up": rnd.choice(range(0, 101, 5))} for e in t2_set(reads)[:9]}
    print("t2_set", len(t2_set(reads)), "cascade picks", len(cascade_rank(reads, t2)))
    hs = [h(f"8k:0000{n}") for n in range(20000)]
    print("hash uniform mean", round(sum(hs) / len(hs), 4), "share < 1/8", round(sum(x < 0.125 for x in hs) / len(hs), 4))
    ev = {"kind": "news", "knowable_at": dt.datetime(2026, 10, 22, 12, 0), "headline": "Acme shares are trading higher "
          "after Morgan Stanley upgrade", "source": "benzinga", "summary": ""}
    pn = [{"knowable_at": dt.datetime(2026, 10, 22, 11, 0), "headline": "Morgan Stanley upgrades Acme to Overweight",
           "source": "benzinga"}]
    m = meta(ev, pn, [], [], {"adv20": 5e6, "prev_close": 12.0, "sigma60": 0.03, "bench": "IWM"}, 300, 0, None,
             dt.datetime(2026, 10, 22, 13, 15))
    print("meta sample:", {k: m[k] for k in ("dup_72h", "kw_upgrade", "kw_move", "cov_24h", "v1_missing")})
