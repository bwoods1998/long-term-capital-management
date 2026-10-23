"""cost_r2.py: READER-2's metered cost a read, a session and a traded event (design-reader2 lens). OUTCOME-FREE.

Inputs: the frozen texts of r2_spec.py; the gateway's prices (gateway/wrangler.jsonc CLAUDE_MODELS on origin/rel/1019h:
Sonnet 5.5 $2 in / $2.50 5-minute write / $10 out, Opus 5.5 $4 / $5 / $20, Haiku 4.5 $1 / $1.25 / $5, the 4.6+ rows
with geo us 1.1, assumed billed); the gateway's worst-case hold (lib/claude.mjs worstCase: (body bytes + 4,096) at the
cache-write rate plus max_tokens at the output rate, times the dearest geo); counts from speed/SPEED-FACTS.md (shadow
intents a session, Oct 19-21) and evl5/HOUSE-FACTS.json (2,911 v1 verdicts, $2.6073). Every content length, the
liquid share and the token counts below are ASSUMPTIONS, printed with the results as a range (lo, mid, hi).
Run: .venv/bin/python cost_r2.py > cost_r2.out
"""
from __future__ import annotations

import json

import r2_spec as R

PRICE = {"sonnet55": {"in": 2.0, "write": 2.5, "out": 10.0, "geo": 1.1},
         "opus55": {"in": 4.0, "write": 5.0, "out": 20.0, "geo": 1.1},
         "haiku45": {"in": 1.0, "write": 1.25, "out": 5.0, "geo": 1.0}}

# (lo, mid, hi) assumptions
A = {
    "chars_per_token_prose": (4.2, 4.0, 3.7), "chars_per_token_doc": (3.9, 3.6, 3.3),
    "article_chars": (220, 300, 420),                  # headline + summary + source + times
    "news_prior_lines": (4, 15, 40), "line_chars": (100, 120, 175),
    "news_prior_filing_lines": (0, 2, 6), "filing_line_chars": 48,
    "doc_text_chars": (9000, 14500, 16000),
    "doc_news_lines": (2, 10, 25),
    "so_overhead_tokens": (150, 300, 600),             # structured outputs' injected format text (unmeasured)
    "news_answer_tokens": (55, 75, 110), "doc_answer_tokens": (90, 115, 160),
    "news_thinking_tokens": (0, 300, 800), "doc_thinking_tokens": (100, 500, 1200),   # effort low (unmeasured)
    "liquid_share": (0.4, 0.6, 0.8),                    # share of qualifying issuers with adv20 >= $10M (unknown)
}

# SPEED-FACTS (shadow intents a session; one per issuer a window), Oct 19 / 20 / 21
COUNTS = {"news_o1_v1ge2": (54, 88, 165), "news_on_v1ge2": (54, 54, 142), "8k_o1_v1ge2": (10, 12, 7),
          # F8K(D) at D's close: CTRL-8K-ON 1 / 45 / 19 less EVL-8K-READ-ON's v1 >= 2 intents - / 9 / 2 (Oct 19 partial)
          "8k_on_v1le1": (1, 36, 17)}
CAP_8K_ON = 8
REAL_BUYS_SESSION = (12 + 10 + 13 + 1 + 2 + 7 + 2) / 2   # SPEED-FACTS real-money buys Oct 20-21, all programs
EQUITY = 1898.0


def tok(chars, per):
    return chars / per


def news_tokens(i):
    P = A["chars_per_token_prose"][i]
    fixed = len(R.SYSTEM_NEWS) + len(R.USER_NEWS) + 60
    prior = A["news_prior_lines"][i] * A["line_chars"][i] + A["news_prior_filing_lines"][i] * A["filing_line_chars"]
    tin = tok(fixed + A["article_chars"][i] + prior, P) + A["so_overhead_tokens"][i]
    tout = A["news_answer_tokens"][i] + A["news_thinking_tokens"][i]
    return tin, tout


def doc_tokens(i):
    P, Dd = A["chars_per_token_prose"][i], A["chars_per_token_doc"][i]
    fixed = len(R.SYSTEM_DOC) + len(R.USER_DOC) + 80
    tin = tok(fixed + A["doc_news_lines"][i] * A["line_chars"][i], P) + tok(A["doc_text_chars"][i], Dd) \
        + A["so_overhead_tokens"][i]
    tout = A["doc_answer_tokens"][i] + A["doc_thinking_tokens"][i]
    return tin, tout


def usd(model, tin, tout):
    p = PRICE[model]
    return p["geo"] * (tin * p["in"] + tout * p["out"]) / 1e6


def hold(model, body_bytes, max_tokens):
    p = PRICE[model]
    return p["geo"] * ((body_bytes + 4096) * p["write"] + max_tokens * p["out"]) / 1e6


def main():
    out = {"assumptions": A, "prices": PRICE, "per_read": {}, "hold": {}, "daily": {}, "per_traded_event": {}}
    for model in ("sonnet55", "opus55", "haiku45"):
        rows = {}
        for i, lab in enumerate(("lo", "mid", "hi")):
            n_in, n_out = news_tokens(i)
            f_in, f_out = doc_tokens(i)
            rows[lab] = {"news": round(usd(model, n_in, n_out), 5), "8k": round(usd(model, f_in, f_out), 5),
                         "tokens": {"news": [round(n_in), round(n_out)], "8k": [round(f_in), round(f_out)]}}
        out["per_read"][model] = rows
    schema_news, schema_doc = len(json.dumps(R.SCHEMA_NEWS)), len(json.dumps(R.SCHEMA_DOC))
    nb = len(R.SYSTEM_NEWS) + len(R.USER_NEWS) + 420 + 40 * 175 + 6 * 48 + schema_news + 400
    db = len(R.SYSTEM_DOC) + len(R.USER_DOC) + 16000 * 1.15 + 25 * 175 + schema_doc + 400
    out["hold"] = {"news_body_bytes_max": round(nb), "doc_body_bytes_max": round(db),
                   "sonnet55_news": round(hold("sonnet55", nb, R.MAX_TOKENS["news"]), 4),
                   "sonnet55_doc": round(hold("sonnet55", db, R.MAX_TOKENS["doc"]), 4),
                   "opus55_doc": round(hold("opus55", db, R.MAX_TOKENS["doc"]), 4)}
    # reads a session (in season / off season), by the frozen set rules (r2_spec: N_NEWS 24, caps)
    for i, lab in enumerate(("lo", "mid", "hi")):
        lam = A["liquid_share"][i]
        o1_news = [min(R.N_NEWS_O1 + 2, lam * c) for c in COUNTS["news_o1_v1ge2"]]   # +2: score-3 issuers always read
        on_news = [min(R.N_NEWS + 2, lam * c) for c in COUNTS["news_on_v1ge2"]]
        o1_8k = [min(R.CAP_8K_O1, lam * c) for c in COUNTS["8k_o1_v1ge2"]]
        reads = {"news": sum(o1_news) / 3 + sum(on_news) / 3, "8k": sum(o1_8k) / 3}
        reads_oct21 = {"news": o1_news[2] + on_news[2], "8k": o1_8k[2]}
        for model in ("sonnet55", "opus55"):
            pr = out["per_read"][model][lab]
            d_mean = sum(reads[k] * pr[k] for k in reads)
            d_21 = sum(reads_oct21[k] * pr[k] for k in reads_oct21)
            out["daily"].setdefault(model, {})[lab] = {
                "reads_mean_oct19_21": {k: round(v, 1) for k, v in reads.items()},
                "reads_oct21": {k: round(v, 1) for k, v in reads_oct21.items()},
                "usd_mean_oct19_21": round(d_mean, 3), "usd_oct21": round(d_21, 3)}
    # THE RECOMMENDED REGISTRATION: EVL-R2-ON alone (NEWS-ON sample + 8K-ON, v1 <= 1, cap 8)
    on_only = {}
    for i, lab in enumerate(("lo", "mid", "hi")):
        lam = A["liquid_share"][i]
        on_news = [min(R.N_NEWS + 2, lam * c) for c in COUNTS["news_on_v1ge2"]]
        on_8k = [min(R.CAP_8K_ON, lam * c) for c in COUNTS["8k_on_v1le1"]]
        pr = out["per_read"]["sonnet55"][lab]
        reads = {"news": sum(on_news[1:]) / 2, "8k": sum(on_8k[1:]) / 2}       # Oct 20-21 (Oct 19 partial)
        d_on = sum(reads[k] * pr[k] for k in reads)
        po = out["per_read"]["opus55"][lab]
        on_only[lab] = {"reads": {k: round(v, 1) for k, v in reads.items()}, "sonnet55_usd_day": round(d_on, 3),
                        "opus55_usd_day": round(sum(reads[k] * po[k] for k in reads), 3),
                        "bp_learning_6buys": round(1e4 * d_on / 6 / (0.02 * EQUITY), 1),
                        "bp_probe_6buys": round(1e4 * d_on / 6 / (0.035 * EQUITY), 1)}
    out["on_only"] = on_only
    # per traded event: two consumers, at most 8 picks each a session; real buys assumed 10-14 of the 16
    for model in ("sonnet55", "opus55"):
        mid = out["daily"][model]["mid"]["usd_oct21"]
        hi = out["daily"][model]["hi"]["usd_oct21"]
        r = {}
        for buys in (10, 14):
            for band, share_ in (("learning", 0.02), ("probe", 0.035)):
                r[f"{buys}_buys_{band}_bp_mid"] = round(1e4 * mid / buys / (share_ * EQUITY), 1)
                r[f"{buys}_buys_{band}_bp_hi"] = round(1e4 * hi / buys / (share_ * EQUITY), 1)
        out["per_traded_event"][model] = r
    # v1 at Oct 21 volume for context (cost_model.py of the EVL-7 lens, scaled to the measured blend): 1.30-1.42
    out["context"] = {"v1_usd_per_verdict_measured": round(2.6073 / 2911, 6),
                      "v1_day_oct21_volume_evl7_lens": "1.30 (model) to 1.42 (scaled to measured)",
                      "lane_line_usd_day": 3.00, "house_fixed_usd_day_A87": 1.25, "metered_cap_no_profit": 5.00,
                      "real_buys_a_session_all_programs_oct20_21": REAL_BUYS_SESSION}
    # the $0.01 smoke test: two Sonnet calls on pinned synthetic texts (smoke_r2.py), worst actual cost each
    smoke = {}
    for kind, mt, chars in (("doc", 400, 700), ("news", 300, 300)):
        sys_user = len(R.SYSTEM_DOC) + len(R.USER_DOC) if kind == "doc" else len(R.SYSTEM_NEWS) + len(R.USER_NEWS)
        tin = (sys_user + chars) / 3.5 + 600            # 600: a pessimistic structured-outputs overhead
        smoke[kind] = {"max_tokens": mt, "worst_usd": round(usd("sonnet55", tin, mt), 5),
                       "expected_usd": round(usd("sonnet55", tin - 300, 150), 5)}
    smoke["worst_total"] = round(smoke["doc"]["worst_usd"] + smoke["news"]["worst_usd"], 5)
    out["smoke_test"] = smoke
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
