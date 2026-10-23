"""budget_r2.py: the lane's expected-false-pass count before and after PREREG-EVL-10 (design-reader2). OUTCOME-FREE.

Charges as the newest texts state them (goal-2026-10-19/): PREREG-EVL-6 section 5 (fifteen versions x 0.13 = 1.95,
lifetime budget 3.9 = 30 x 0.13); PREREG-EVL-7 section 4 (2 x c7, c7 = 0.13); PREREG-EVL-8 section 6.6 (5 x 0.13);
PREREG-EVL-9 section 10 (2 x c9, c9 = 0.13); A104's three day-news births (0.13 each) if R3 registers them; this
file's two consumer seats at c10 = max(0.13, the measured worst per-run rate rounded up). The registering amendment
restates USED and LEFT from R3's validator before the tag is pushed.
"""
import json
import sys

BUDGET = 3.9
USED = {"PREREG-EVL-6 (15 versions)": 15 * 0.13, "PREREG-EVL-7 (2 learners)": 2 * 0.13,
        "PREREG-EVL-8 (3 PX + 2 META)": 5 * 0.13, "PREREG-EVL-9 (2 warm learners)": 2 * 0.13}


def main(c10: float = 0.13) -> None:
    out = {}
    for seats in (1, 2):
        for births in (0, 3):
            used = sum(USED.values()) + 0.13 * births
            after = used + seats * c10
            out[f"{seats}_seat_{births}_births"] = {
                "used_before": round(used, 2), "evl10_adds": round(seats * c10, 2), "used_after": round(after, 2),
                "left_after": round(BUDGET - after, 2), "charges_left_after": int(round((BUDGET - after) / 0.13 + 1e-9)),
                "evl10_lifetime_max (3 runs a seat)": round(3 * seats * c10, 2)}
    out["c10"] = c10
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.13)
