#!/usr/bin/env python
"""px_grid8.py (the PREREG-EVL-8 judge's copy of ../price/px_grid.py; edits: GAP reads sigma_on60 and bars starting
[08:00, 08:58] ET as the seat PX-GAP-O1 does; every value against P's close uses c*_P, P's adjustment=all close read at
or after 09:00 ET of D (equal to the stored adjusted close when D is not FLAGGED); the SEAT mirrors are the top 40):
the PX lane's RECORD GRID, enumerated (outcome-free: rules only, no data).

Writes px_grid.json, the registry a PREREG-EVL-8 freeze would pin by sha256: one row per record rule with its id, family,
side, news filter, size tier, window and the exact selection text. Records are free (never seated, never screened);
the meta-learner lens weighs them forward. Prints the counts and, for stated universe scenarios, the expected members a
session (decile x filter shares; the shares are ASSUMPTIONS until the House measures them on its first passes).

Usage: px_grid.py
"""
import hashlib
import itertools
import json

FAMILIES = {
    # family: (windows it is knowable for, sides, the value's text)
    "REV1": (("O1", "ON", "C1"), ("LO", "HI"),
             "z1 = (c_P / c_P1 - cb_P / cb_P1) / sigma60 (adjusted SIP closes; cb the benchmark's)"),
    "REV5": (("O1", "ON", "C1"), ("LO", "HI"), "z5 = (c_P / c_P5 - cb_P / cb_P5) / (sigma60 x sqrt 5)"),
    "REV20": (("O1", "ON", "C1"), ("LO", "HI"), "z20 = (c_P / c_P20 - cb_P / cb_P20) / (sigma60 x sqrt 20)"),
    "REV1S": (("O1", "ON", "C1"), ("LO", "HI"),
              "z1s = (c_P / c_P1 - the mean of c_P / c_P1 over the PXU names of the issuer's SIC 2-digit group) / "
              "sigma60 (a group of fewer than 5 PXU names: no value; after Da, Liu and Schaumburg 2014's "
              "within-industry reversal)"),
    "GAP": (("O1",), ("LO", "HI"),
            "zg = (pm_D / c*_P - pmb_D / cb*_P) / sigma_on60, pm_D the close of the last raw SIP 1Min bar starting in "
            "[08:00, 08:58] ET of D (>= 3 such bars with volume, else no value)"),
    "OPENGAP": (("ON", "C1"), ("LO", "HI"),
                "zo = (o_D / c*_P - ob_D / cb*_P) / sigma60, o_D the open of D's 09:30 raw SIP 1Min bar (PREREG-EVL-5's "
                "gap minute)"),
    "DAY": (("ON", "C1"), ("LO", "HI"), "zd = (x_D / c*_P - xb_D / cb*_P) / sigma60, x_D the px1530 mark of D"),
    "DAYS": (("ON", "C1"), ("LO", "HI"),
             "zds = (x_D / c*_P - the mean of x_D / c*_P over the PXU names of the issuer's SIC 2-digit group) / sigma60 "
             "(fewer than 5: no value)"),
    "HI52": (("O1", "ON", "C1"), ("LO", "HI"), "h52 = c_P / max(adjusted SIP high over the 252 sessions through P)"),
    "VOL": (("O1", "ON", "C1"), ("HIUP", "HIDN"),
            "v = volume_P / mean(volume of the 20 sessions before P); HIUP: top decile of v with z1 > 0, HIDN: with "
            "z1 < 0 (after Gervais, Kaniel and Mingelgrin 2001, who rank a day's volume against the days before it)"),
}
NEWS = {"ANY": "no news condition", "NONE": "no stored item of the issuer in the window's news span",
        "SOME": "at least one stored item of the issuer in the window's news span"}
TIERS = {"ALL": "every PXU name", "SMALL": "benchmark IWM (ADV20 < $50M)", "LARGE": "benchmark SPY (ADV20 >= $50M)"}
WINDOWS = {"O1": "D's opening cross -> D's closing cross", "ON": "D's closing cross -> D+1's opening cross",
           "C1": "D's closing cross -> D+1's closing cross"}
CONTROLS = ("EVL-CTRL-NEWS-ALL-O1", "EVL-CTRL-NEWS-DAY-ON", "EVL-CTRL-NEWSPM-ON", "EVL-CTRL-8K-ALL-O1",
            "EVL-CTRL-8K-ON", "EVL-CTRL-ERN-ALL-O1")

rows = []
for fam, (wins, sides, text) in FAMILIES.items():
    for side, news, tier, win in itertools.product(sides, NEWS, TIERS, wins):
        rid = f"PXR-{fam}-{side}-{news}-{tier}-{win}"
        sel = {"LO": "the bottom decile of the family's value over the PXU names of the decision",
               "HI": "the top decile of the family's value over the PXU names of the decision",
               "HIUP": "the top decile of v over the PXU names of the decision, z1 > 0",
               "HIDN": "the top decile of v over the PXU names of the decision, z1 < 0"}[side]
        rows.append({"id": rid, "family": fam, "side": side, "news": news, "tier": tier, "window": win,
                     "value": text, "select": f"{sel}; then {NEWS[news]}; then {TIERS[tier]}", "window_text": WINDOWS[win]})
for c, k, sgn in itertools.product(CONTROLS, (1, 2, 3, 5), ("UP", "DN")):
    rid = f"PXR-DRIFT-{c.replace('EVL-CTRL-', '')}-K{k}-{sgn}-O1"
    rows.append({"id": rid, "family": "DRIFT", "side": sgn, "news": "ANY", "tier": "ALL", "window": "O1",
                 "value": "zs = (c_P / c_E - cb_P / cb_E) / (sigma60 x sqrt(sessions from E to P)), E the session before "
                          "the control event's entry session",
                 "select": f"every PXU issuer of a {c} event whose exit session is the {k}th session before D; "
                           f"{'zs >= +1' if sgn == 'UP' else 'zs <= -1'}; one row per issuer and D (the latest event)",
                 "window_text": WINDOWS["O1"]})
for news, tier, win in itertools.product(NEWS, TIERS, WINDOWS):
    rows.append({"id": f"PXR-UNIV-{news}-{tier}-{win}", "family": "UNIV", "side": "ALL", "news": news, "tier": tier,
                 "window": win, "value": "none", "select": f"every PXU name; then {NEWS[news]}; then {TIERS[tier]}",
                 "window_text": WINDOWS[win]})
for seat, win in (("DROP", "ON"), ("GAP", "O1"), ("SURGE", "ON")):
    rows.append({"id": f"PXR-SEAT-{seat}-{win}", "family": "SEAT", "side": seat, "news": "NONE", "tier": "ALL",
                 "window": win, "value": f"PX-{seat}-{win}'s own rule and ranking, top 40",
                 "select": f"exactly the seat PX-{seat}-{win}'s shadow events, settled on the bar basis",
                 "window_text": WINDOWS[win]})

blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
json.dump(rows, open("px_grid8.json", "w"), indent=1, sort_keys=True)
by = {}
for r in rows:
    by[r["family"]] = by.get(r["family"], 0) + 1
print("records", len(rows), "by family", by)
print("px_grid8.json canonical sha256", hashlib.sha256(blob).hexdigest())
print("\nexpected members a session of ONE decile record (assumed shares: news NONE 0.80 / SOME 0.20; tier SMALL "
      "0.60 / LARGE 0.40 at ADV20 >= $10M):")
for n in (1500, 2000, 3000):
    dec = n / 10
    print(f"  N_U={n}: ALL/ANY {dec:.0f}; NONE/ALL {dec * .8:.0f}; SOME/ALL {dec * .2:.0f}; NONE/SMALL {dec * .8 * .6:.0f}; "
          f"SOME/LARGE {dec * .2 * .4:.0f}; panel rows a session (3 windows) {3 * n}")
