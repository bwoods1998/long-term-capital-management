#!/usr/bin/env python
"""check2/budget_check.py: arithmetic only (no lane data). (1) the close/open decision time budget the isolated parts
need against release 1019g's constants (house.py DECIDE_BUDGET 150, CLOSE_GRACE 60 s; calendar.py close decide -14 min,
send -11 min; run.py EVL5_BUDGET 45, EVL5_FINISH 15) and the drafts' part bounds (EVL-7 draft 90/120 s, EVL-8 draft PX
120/60 s, META 30 s); (2) PX request totals with the controls at 200 (draft s3.2) instead of the 60 that
price/fees_and_requests.out priced; (3) the charge basis."""
DECIDE_BUDGET, CLOSE_GRACE, FINISH = 150.0, 60.0, 15.0
close_window = (14 - 11) * 60 - CLOSE_GRACE           # decision start (close-13) to send-by (close-11)
parts_close = {"EVL-5": 45.0, "EVL-7 (draft)": 120.0, "PX (EVL-8)": 60.0, "META (EVL-8)": 30.0}
parts_open = {"EVL-7 (draft)": 90.0, "PX (EVL-8)": 120.0, "META (EVL-8)": 30.0}
print("CLOSE: seconds from decision start to send-by", close_window, "| task bound less finish", DECIDE_BUDGET - FINISH)
print("  isolated part bounds", parts_close, "sum", sum(parts_close.values()))
print("OPEN: open window 09:15->09:27 =", 12 * 60, "s | task bound less finish", DECIDE_BUDGET - FINISH)
print("  isolated part bounds", parts_open, "sum", sum(parts_open.values()))
# (2) requests: fees_and_requests.out rows, prints row recomputed for 3 x 40 + 2 x 200
base = {2000: 802, 3000: 837, 4500: 892, 6041: 948}
prints_old = 720                                       # 3 x 40 + 2 x 60 = 240 events, 2 prints, 1.5 pages
events_new = 3 * 40 + 2 * 200
prints_new = events_new * 2 * 1.5
for n, tot in base.items():
    new = tot - prints_old + prints_new
    print(f"N_U={n}: draft s12 total {tot} ({tot/200:.1f} min) -> with 200-name controls {new:.0f} ({new/200:.1f} min of 200/min)")
print("events a session", events_new, "print reads", prints_new)
# (3) charges
print("PX at 0.11 x3 =", round(3 * 0.11, 2), "| at the EVL-6 draft per-version 0.14 x3 =", round(3 * 0.14, 2),
      "| difference", round(3 * 0.14 - 3 * 0.11, 2))
