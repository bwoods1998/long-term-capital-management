"""Re-check 2 of PREREG-EVL-10 (honesty / implementability lens). SYNTHETIC ONLY: no store, House or gateway is read.

(1) A85's reservation for a PROMOTED EVL-R2-ON as release 1019l's book computes it (league/events/book.py `reservation`,
    the real function) when its picks history is found (the median of its last 5 decisions) versus when it is not
    found: on origin/feat/scheduler the file's pass writes its summary only under eq_event_decisions (day,
    "close-evl10"), while league/equity/live.py `_event_recent` reads rows WHERE at='close' only, so the counts are
    empty and `reservation` reserves the program's WHOLE room.
(2) COMPLETE (section 1.4) against WHEN (section 1.5): scans start at the first House publish at or after 07:30:00 ET
    and stop at tau - 30 s, so a scan at or before 07:30:00 and one at or after tau - 30 s both need an exact hit.
"""
from __future__ import annotations

import random
import sys
from decimal import Decimal

sys.path.insert(0, "/home/bwoods1998/Work/ltcm-v3/rel-1019l")   # release 1019l's tree (3df7dd9d), read only

from league.events import book as B  # noqa: E402

E = Decimal("1906")
s = B.settings()            # the constitution in force on 1019l (Probe share 0.05)
print("probe share", s.share("probe"), "max_open probe (no program)", s.max_open("probe"))

room = 14                   # PREREG-EVL-6 section 6: a v6-era version at Probe, nothing held
found = [{"band": "probe", "room": room, "picks": [5, 6, 6, 7, 5], "weights": []}]
missing = [{"band": "probe", "room": room, "picks": [], "weights": []}]
for name, rows in (("history found (median picks)", found), ("history not found (feat/scheduler's key)", missing)):
    cash, risk = B.reservation(rows, s, E)
    print(f"{name}: cash and invested room reserved ${cash:.2f} = {float(cash / E):.0%} of E; loss budget ${risk:.2f}")

# (2) the publishes' phase is uniform; publishes 60-121 s apart (house.py's H5 note)
rng = random.Random(20261023)
hits_start = hits_end = 0
N = 100_000
start, end = 7.5 * 3600, 15 * 3600 + 39 * 60 + 30          # 07:30:00 and tau - 30 s on a full day (seconds ET)
for _ in range(N):
    t = start - rng.uniform(0, 60) + 0.0
    scans = []
    while t < end:
        if t >= start:
            scans.append(t)
        t += rng.uniform(60, 121)
    hits_start += scans[0] <= start
    hits_end += scans[-1] >= end
print(f"sessions with a scan at or before 07:30:00: {hits_start}/{N}; with one at or after tau - 30 s: {hits_end}/{N}")
print("so q(D) = Q_DEFAULT 0.5 on every session under the literal COMPLETE")
