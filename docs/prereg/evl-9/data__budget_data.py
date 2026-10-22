"""The warm-start data build's request budget and wall-clock (counts and API limits only; no price, no outcome).
Inputs: the scout's record counts (evl9/scout/count_listed_events.out.json, fetch_budget.out.json), this lens's
count_gap.out.json and fsds_members.out.json, the repo calendar (league.equity.store.nyse_sessions at rel/1019g), API
limits (SEC 10/s, the House's 6.67/s; Alpaca Basic 200/min shared, 10,000 points a page, news 50 a page; auctions
100/min). Two windows: W5 = entry sessions 2021-01-04..2026-10-16, W10 = 2016-03-01..2026-10-16."""
import datetime as dt, json, math, sys
sys.path.insert(0, "/dev/shm/warm-data/src")
from league.equity.store import nyse_sessions
SC = "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl9/scout/"
le = json.load(open(SC + "count_listed_events.out.json"))["by_year"]
gap = json.load(open("count_gap.out.json"))
SEC_RATE = 1 / 0.15            # the House's MIN_INTERVAL (ltcm.data.edgar), requests/s
ALP = {"shared_100": 100.0, "paper_190": 190.0}   # requests/min the build may use
def sessions(a, b): return [d for d, _ in nyse_sessions(a, b)]
END = dt.date(2026, 10, 16)
W = {"W5": dt.date(2021, 1, 4), "W10": dt.date(2016, 3, 1)}
out = {}
for name, start in W.items():
    ses = sessions(start, END)
    look = sessions(start - dt.timedelta(days=45), END)          # 20+ sessions of look-back bars
    years = [str(y) for y in range(start.year, 2027)]
    frac0 = (dt.date(start.year, 12, 31) - start).days / 365.0     # share of the first year inside the window
    f4p = sum(le[y]["f4_P_purchase_filings"] * (frac0 if y == years[0] else 1.0) for y in years)
    k8 = sum(le[y]["8k"] * (frac0 if y == years[0] else 1.0) for y in years)
    k8_listed = sum(le[y]["8k_listed_issuer"] * (frac0 if y == years[0] else 1.0) for y in years)
    issuers = max(le[y]["issuers_with_symbol"] for y in years)
    # SEC
    atom8k_pages_upper = 17596 if name == "W10" else math.ceil(17596 * k8 / sum(le[y]["8k"] for y in le)) + 14280 // 4
    f4_txt = round(f4p) + gap["oct1_16_form4"]                    # P-buy filings (S2 index) + every Oct 1-16 Form 4
    fsds_req = 47 * 5                                             # sub.txt by range requests (3 measured + slack)
    s2_files = sum(1 for y in range(start.year - 1, 2027) for q in range(1, 5) if (y, q) <= (2026, 3))
    sec_req = atom8k_pages_upper + f4_txt + fsds_req + s2_files + 1
    sec_h = sec_req / SEC_RATE / 3600
    # Alpaca daily bars: <= 12,590 PIT symbols (2016-2026 upper bound), raw + all, 200 a request, 10,000 points a page
    n_sym = 12590
    pages_per_chunk = math.ceil(200 * len(look) / 10000)
    bars_grouped = 2 * math.ceil(n_sym / 200) * pages_per_chunk            # every symbol in an asof-group of 200
    bars_alone = 2 * n_sym * math.ceil(len(look) / 10000)                   # worst case: every spell alone
    # 1Min: O1 premarket [08:00, 08:59) for <= 700 O1 candidates a session (59 bars: 2 pages a 200-name chunk);
    # ON '1530' mark: [15:00, 15:30) for <= 900 ON candidates (31 bars: 1 page), plus a [09:30, 15:00) re-read for <= 5%
    pm_req = len(ses) * math.ceil(700 / 200) * math.ceil(200 * 59 / 10000)
    m1530_req = len(ses) * (math.ceil(900 / 200) + 1)
    days = (END - (start - dt.timedelta(days=10))).days
    news = {str(r): math.ceil(days * r / 50) for r in (1000, 1500, 2000, 3000)}
    # auctions (after the one-row gateway change): one request a 200-name chunk of a session's O1+ON candidates (<= 1,200
    # names), days D and D+1 (<= 2 day objects a name: 400 objects, one page), at the endpoint's 100/min
    auc_req = len(ses) * math.ceil(1200 / 200)
    alp_base = bars_grouped + pm_req + m1530_req
    rows = {"sessions": len(ses), "lookback_sessions": len(look), "form4_P_filings_est": round(f4p), "8k_est": round(k8),
            "8k_listed_issuer_est": round(k8_listed), "max_issuers_with_symbol_a_year": issuers,
            "sec": {"atom_8k_pages_upper": atom8k_pages_upper, "form4_txt": f4_txt, "fsds_range": fsds_req,
                    "s2_quarter_files": s2_files, "requests": sec_req, "hours_at_6.67_per_s": round(sec_h, 2)},
            "alpaca": {"bars_grouped": bars_grouped, "bars_alone_worst": bars_alone, "premarket_1min": pm_req,
                       "mark1530_1min": m1530_req, "auctions": auc_req, "auctions_hours_at_90": round(auc_req / 90 / 60, 2), "news_pages_by_articles_a_day": news}}
    for k, rate in ALP.items():
        rows["alpaca"][f"hours_{k}"] = {r: round((alp_base + n) / rate / 60, 1) for r, n in news.items()}
        rows["alpaca"][f"hours_{k}_bars_worst_extra"] = round((bars_alone - bars_grouped) / rate / 60, 1)
    out[name] = rows
json.dump(out, open("budget_data.out.json", "w"), indent=1)
print(json.dumps(out, indent=1))
