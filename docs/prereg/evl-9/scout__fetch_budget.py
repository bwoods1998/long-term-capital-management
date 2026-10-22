"""fetch_budget.py -- the fetch plan's request counts, hours and metered dollars, from the scout's COUNTED inputs only.

Inputs (all outcome-free, made by this scout's scripts): count_edgar_index.out.json, count_submissions.out.json,
count_form345.out.json, count_listed_events.out.json, sample_accept_times.out.json; the session count from the repo's
calendar (league.equity.store.nyse_sessions: 2,716 sessions 2016-01-04..2026-10-21); rates from the code and the
vendors' docs: SEC <= 10 requests/s (the House's ltcm.data.edgar.MIN_INTERVAL 0.15 s = 6.67/s), Alpaca Basic 200
market-data requests/min shared with the House (the House spaces its own reads 0.5 s apart; history runs at 100/min
outside the House's decision windows), Alpaca's auctions endpoint 100/min (its reference page), bars and auctions
10,000 data points a page (the limit counts all symbols), news 50 articles a page. No price or return is read.
Output: fetch_budget.out.json and a printed table.
"""
import json
import math

SESS = 2716
DAYS = 3947          # calendar days 2016-01-01..2026-10-21 (news is published every day)
SEC_RPS = 1 / 0.15
ALP_RPM = 100
AUC_RPM = 100


def load(name):
    return json.load(open(name))


def main():
    sub = load("count_submissions.out.json")
    f345 = load("count_form345.out.json")
    lst = load("count_listed_events.out.json")
    smp = load("sample_accept_times.out.json")
    years = sub["by_year"]
    k8 = sum(v["8-K"] for v in years.values())
    f4 = sum(v["4"] for v in years.values())
    k8_listed = sum(v["8k_listed_issuer"] for v in lst["by_year"].values())
    f4_sym = sum(v["f4_with_symbol"] for v in lst["by_year"].values())
    p_buy = sum(v["f4_P_purchase_filings"] for v in lst["by_year"].values())
    zip345 = sum(v.get("zip_bytes", 0) for v in f345["quarters"].values())
    syms = lst["distinct_symbols_2016_2026"]
    atom8 = smp["atom_8k"]["pages_at_100"]
    atom4 = lst["form4_atom_pages_owner_only"]
    rows = []

    def add(name, requests, rate_per_s, mb=None, note=""):
        rows.append({"source": name, "requests": int(requests), "hours": round(requests / rate_per_s / 3600, 2),
                     "download_MB": mb, "metered_usd": 0.0, "note": note})

    add("SEC bulk submissions.zip (forms, items, filing dates, every CIK)", 1, SEC_RPS, 1570.2,
        "one file on www.sec.gov; measured ~2-3 min on blake-desktop")
    add("SEC Insider Transactions Data Sets 2016q1-2026q3 (Form 4 XML, parsed by SEC)", 43, SEC_RPS,
        round(zip345 / 1e6, 1), "two quarters under /files/datastandardsinnovation/")
    add("8-K acceptance times: browse-edgar getcompany Atom, 100 a page, per filer CIK", atom8, SEC_RPS, None,
        "<updated> = .hdr.sgml acceptance (24/24 checked)")
    add("8-K acceptance times ALTERNATIVE: one .hdr.sgml per 8-K", k8, SEC_RPS, None, "slow; exact; items too")
    add("Form 4 acceptance times: getcompany type=4 owner=only Atom per issuer CIK", atom4, SEC_RPS, None,
        "type=4 with owner=include prefix-matches 424B*; owner=only lists Form 4s")
    for label, n_sym in (("PIT symbols (Form 4 issuers with a symbol)", syms),):
        bars_ub = n_sym * SESS
        req = 2 * math.ceil(bars_ub / 10000) + 2 * math.ceil(n_sym / 200)
        add(f"Alpaca SIP 1Day bars raw + all, {label}, UPPER bound {n_sym} x {SESS} sessions", req, ALP_RPM / 60, None,
            "200 symbols a request, 10,000 bars a page")
        add(f"Alpaca SIP 1Day bars raw + all, ENDED spells fetched alone with asof inside the spell, UPPER bound "
            f"{n_sym} spells", 2 * n_sym, ALP_RPM / 60, None, "equity_panel's plan: each ended asset alone")
    # one-minute marks of event days only (09:30 minute; 15:00-15:30 window): one request per day per 200 names
    # NAMES a session: SPEED-FACTS.md, the controls' intents of Oct 21 summed (515+550+271+44+19+58 = 1,457; overlapping, so an
    # UPPER bound on distinct event names a session)
    NAMES = 1457
    for lab, per_day_names in (("09:30 minute of event names", NAMES), ("15:00-15:30 minutes of event names", NAMES)):
        req = SESS * math.ceil(per_day_names / 200)
        add(f"Alpaca SIP 1Min {lab} (<= {per_day_names} names a session)", req, ALP_RPM / 60, None,
            "15:00-15:30 is 31 bars a name: 200 names = 6,200 points, one page")
    req = SESS * math.ceil(NAMES / 200)
    add("Alpaca auctions (open+close prints) of event names, IF the gateway admits v2/stocks/auctions", req,
        AUC_RPM / 60, None, "reviewed gateway change: one VENUE_PATHS row; one day object holds both auctions "
        "(to verify on the first probe)")
    for per_day in (130, 500, 1500, 3000):
        req = math.ceil(per_day * DAYS / 50)
        add(f"Alpaca news history 2016-2026 at {per_day} articles/day (metadata, include_content=false)", req,
            ALP_RPM / 60, None, "the per-day count is a count-only probe (gap)")
    out = {"inputs": {"distinct_8k_2016_2026": k8, "distinct_form4_2016_2026": f4, "8k_listed_issuer": k8_listed,
                      "form4_with_symbol": f4_sym, "form4_P_purchase_filings": p_buy, "pit_symbols": syms,
                      "sessions": SESS, "atom_8k_pages": atom8, "atom_f4_pages": atom4},
           "rows": rows}
    json.dump(out, open("fetch_budget.out.json", "w"), indent=1)
    print(json.dumps(out["inputs"], indent=1))
    for r in rows:
        print(f"{r['requests']:>9,}  {r['hours']:>7.2f} h  {str(r['download_MB'] or ''):>8}  {r['source']}")


if __name__ == "__main__":
    main()
