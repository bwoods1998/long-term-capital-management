#!/usr/bin/env python
"""fetch_budget_judge.py (the EVL-9 judge): requests and hours of PREREG-EVL-9's history build, from COUNTS and API
limits only (the scout's, the data lens's and the learners lens's count outputs, and the repo calendar). No price, bar,
return or outcome is read. Inputs are copied below with their source file."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
E = os.path.dirname(HERE)
lrn = json.load(open(os.path.join(E, "learners", "fetch_budget9.out.json")))
gap = json.load(open(os.path.join(E, "data", "count_gap.out.json")))
SESS_O1, SESS_ON = 1202, 1201            # judge/count_sessions.py (league.equity.store.nyse_sessions)
NEWS_DAYS = (365 * 4 + 1 + 289 + 47)      # 2021-11-15 .. 2026-10-22 inclusive, calendar days (lookback + overlap)
sec = {
    "atom_8k_pages": lrn["sec"]["atom_pages_8k_scaled"],
    "atom_form4_owner_only_pages": lrn["sec"]["atom_pages_f4_scaled"],
    "form345_quarters_2021q1_2026q3": 23,
    "fsds_sub_range_reads_2021q1_2026q3": 23 * 3,
    "form4_txt_2026_10_01_to_10_16": (gap["oct1_16_form4"] if isinstance(gap["oct1_16_form4"], int) else gap["oct1_16_form4"]["total"]),
    "form4_txt_overlap_2026_10_19_to_10_22_est": 4 * 800,
    "submissions_zip": 0,
}
sec["requests"] = sum(v for k, v in sec.items() if k != "submissions_zip")
sec["hours_at_6.67_per_s"] = round(sec["requests"] / 6.67 / 3600, 2)
news = {}
for per_day in (130, 500, 1500, 3000):
    pages = NEWS_DAYS * -(-per_day // 50)
    news[str(per_day)] = {"requests": pages, "hours_at_100_per_min": round(pages / 100 / 60, 2),
                          "hours_at_190_per_min": round(pages / 190 / 60, 2)}
bars = {"batched_one_adjustment": lrn["bars_1day"]["batched_requests"],
        "batched_raw_and_all": 2 * lrn["bars_1day"]["batched_requests"],
        "asof_alone_worst_extra": lrn["bars_1day"]["ended_spells_alone_upper_requests"]}
min1 = {"on_candidates_420": lrn["min1_on"]["420_candidates"]["requests"],
        "on_candidates_850": lrn["min1_on"]["850_candidates"]["requests"]}
auctions = {"per_session": 6, "requests": 6 * SESS_O1, "hours_at_90_per_min": round(6 * SESS_O1 / 90 / 60, 2)}
lo = bars["batched_raw_and_all"] + min1["on_candidates_420"] + auctions["requests"]
hi = bars["batched_raw_and_all"] + min1["on_candidates_850"] + auctions["requests"] + bars["asof_alone_worst_extra"]
price = {"requests_typical_lo": lo, "requests_worst_hi": hi,
         "hours_at_100_per_min": [round(lo / 100 / 60, 2), round(hi / 100 / 60, 2)],
         "hours_at_190_per_min": [round(lo / 190 / 60, 2), round(hi / 190 / 60, 2)]}
gbt = {"secs_per_round_700k_x_54": 3.289, "rounds_per_run_at_Rstar_200": 200 + 5 * 200 + 200,
       "hours_per_run": round((200 + 5 * 200 + 200) * 3.289 / 3600, 2)}   # learners/gbt_cost9.out
out = {"sessions": {"O1": SESS_O1, "ON": SESS_ON}, "news_days": NEWS_DAYS, "sec_before_T_F": sec,
       "news_before_T_F": news, "price_after_CODE_PIN": {"bars_1day": bars, "min1_on_marks": min1,
       "auctions": auctions, "total": price}, "gbt_train": gbt}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(HERE, "fetch_budget_judge.out.json"), "w"), indent=1)
