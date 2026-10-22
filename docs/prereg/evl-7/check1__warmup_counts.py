#!/usr/bin/env python
"""warmup_counts.py: upper bounds on the learners' training rows at each early decision, from SPEED-FACTS.md's
outcome-free intent COUNTS only (before merging by issuer, before TRADABLE and the 1.25x exclusion, so every figure is
an UPPER bound). O1 trains with a 1-session lag, ON with a 2-session lag (section 1.5; H5's alarm). Warm-up: >= 2,000
rows from >= 3 sessions (section 1.7). Sessions after Oct 21 are not counted in the facts: shown as +x."""
O1 = {"Oct19": 135 + 22 + 4 + 2, "Oct20": 248 + 52 + 43 + 1, "Oct21": 515 + 44 + 58 + 1}      # NEWS-ALL, 8K-ALL, ERN-ALL, INS-BUY
ON = {"Oct19": 235 + 1 + 0 + 1, "Oct20": 219 + 155 + 45 + 11, "Oct21": 550 + 271 + 19 + 4}    # NEWS-DAY, NEWSPM, 8K-ON, ERN-REACT-ON
for name, d, lag in (("EVL-LRN-O1", O1, 1), ("EVL-LRN-ON", ON, 2)):
    days = list(d)
    print(name, "per session (upper bounds):", d)
    for i, dec in enumerate(["Oct22", "Oct23", "Oct26"]):
        k = 3 + i - lag + 1          # settled sessions among Oct19.. at this decision
        known = days[:min(k, 3)]
        extra = max(0, k - 3)
        rows = sum(d[x] for x in known)
        print(f"  decision {dec}: settled sessions {known}{' + ' + str(extra) + ' later session(s)' if extra else ''}; "
              f"rows <= {rows}{' + x' if extra else ''}; warm-up met: {'no' if (rows < 2000 and not extra) or k < 3 else 'only if the later sessions add ' + str(max(0, 2000 - rows)) + '+'}")
