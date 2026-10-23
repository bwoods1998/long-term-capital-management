"""Second fix round of PREREG-EVL-10 (Oct 23): the per-program rules this file's pass must carry. SYNTHETIC ONLY: no
store, House, gateway or run record is read; release 1019l's own code (3df7dd9d, read only, no bytecode written) is
imported for its Settings, Program rows and A85's `reservation`.

(1) `Program.evl6` on release 1019l is True only for PREREG-EVL-6's own versions (`regfile` 6) and for births born at or
    after REGISTERED_AT_6. A seatable row of a later PREREG file (this file's EVL-R2-ON) is neither, so on that code it
    reads False, and with it `Settings.max_open("probe", row)` is 6, not PREREG-EVL-6 section 6's 14, and the unsettled
    hold (`_event_decide`), the under_bar / reach_bar_off skip (`_event_gate`) and the at-size count (`_size_event`),
    which all test `program.evl6`, are off for it. A row whose `evl6` reads True gets 14.
(2) A85's reservation (`book.reservation`, the real function) for a PROMOTED EVL-R2-ON at Probe with nothing held, in
    the four cases: its picks history found or not (whether its summaries reach the main (day, "close") row that
    `_event_recent` reads), times room 14 (evl6 True) or 6 (evl6 False). Only both fixes give the stated 30% of E.
(3) PREREG-EVL-7's learner rows, for the captain (not this file's): their `evl6` on release 1019l.
"""
from __future__ import annotations

import dataclasses
import sys
import types
from decimal import Decimal

sys.dont_write_bytecode = True
sys.path.insert(0, "/home/bwoods1998/Work/ltcm-v3/rel-1019l")   # release 1019l's tree (3df7dd9d), read only

from league.events import book as B  # noqa: E402
from league.events import programs as P  # noqa: E402

E = Decimal("1906")
s = B.settings()
print("release 1019l settings: max_open", dict(s.max_opens), "max_open_v6", dict(s.max_opens_v6),
      "share probe", s.share("probe"))

# (1) a seatable close-entry row of a later PREREG file: an existing PREREG row's shape with this file's id and number
base = next(p for p in P.PREREG_SEATING if p.entry_at == "close")
row10 = dataclasses.replace(base, id="EVL-R2-ON", version=1, family="r2-on", prereg=10, regfile=None, born_at=None,
                            spec=None)
assert row10.seatable
print(f"\n(1) EVL-R2-ON as a plain PREREG row (prereg 10, regfile None, born_at None): evl6 = {row10.evl6}; "
      f"max_open('probe', row) = {s.max_open('probe', row10)}; max_open('probe') = {s.max_open('probe')}")
flagged = types.SimpleNamespace(evl6=True)
print(f"    a row whose evl6 reads True: max_open('probe', row) = {s.max_open('probe', flagged)}; "
      f"max_open('learning', row) = {s.max_open('learning', flagged)}; max_open('sized', row) = "
      f"{s.max_open('sized', flagged)}")

# (2) A85's reservation for the promoted row at Probe, nothing held, at the next open
print("\n(2) A85's reservation at the next open (book.reservation, E = $1,906, Probe share 0.05):")
for room, why in ((14, "room 14 (evl6 True)"), (6, "room 6 (evl6 False)")):
    for picks, how in (([5, 6, 6, 7, 5], "history found (summary in the main row), picks 5, 6, 6, 7, 5"),
                       ([], "history not found (summary only in (day, 'close-evl10'))")):
        cash, risk = B.reservation([{"band": "probe", "room": room, "picks": picks, "weights": []}], s, E)
        print(f"    {why}, {how}: cash and invested room ${cash:.2f} = {float(cash / E):.0%} of E; "
              f"loss budget ${risk:.2f}")

# (3) PREREG-EVL-7's learners on release 1019l (for the captain; not this file's rows)
print("\n(3) PREREG-EVL-7's learner rows on release 1019l:",
      ", ".join(f"{p.id} evl6={p.evl6} max_open(probe)={s.max_open('probe', p)}" for p in P.LEARNER_ROWS))
