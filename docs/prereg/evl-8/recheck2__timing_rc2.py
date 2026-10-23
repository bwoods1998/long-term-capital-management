#!/usr/bin/env python
"""timing_rc2.py: re-check 2 of PREREG-EVL-8, arithmetic only on release 1019h's constants read from git (no lane data).

Checks section 4.6's close-side claims against (1) the lane's data spacing (house.py DATA_INTERVAL), (2) the gateway
client's read timeout (gw.py Gateway timeout) on the House's one-slot lane, and (3) the book's cadence (league/live/
step.py: once a minute, a few seconds after each minute) and its one close decision at close_decide + 60 s.
"""
import re
import subprocess

REPO = "/home/bwoods1998/Work/long-term-capital-management"
REF = "origin/rel/1019h"


def show(path):
    return subprocess.run(["git", "-C", REPO, "show", f"{REF}:{path}"], capture_output=True, text=True, check=True).stdout


house, gw, live, step = (show(p) for p in ("league/events/house.py", "league/events/gw.py", "league/equity/live.py",
                                            "league/live/step.py"))
DATA_INTERVAL = float(re.search(r"^DATA_INTERVAL = ([0-9.]+)", house, re.M).group(1))
TIMEOUT = float(re.search(r"timeout: float = ([0-9.]+)", gw).group(1))
WAIT_CLOSE = float(re.search(r'EVENT_DECIDE_WAIT_S = \{"open": [0-9.]+, "close": ([0-9.]+)\}', live).group(1))
one_slot = "one-slot feeds lane" in house
not_promise = "A BOUND IS NOT A PROMISE" in house
cadence = "once a minute, a few seconds after each minute" in step
one_decision = "ONE DECISION A SESSION AND AUCTION" in live
print(f"{REF}: DATA_INTERVAL {DATA_INTERVAL} s ({60 / DATA_INTERVAL:.0f} reads a minute); gateway read timeout "
      f"{TIMEOUT:.0f} s; one-slot lane: {one_slot}; 'a bound is not a promise': {not_promise}; book once a minute a few "
      f"seconds after it: {cadence}; one book decision an auction: {one_decision}; book close wait {WAIT_CLOSE:.0f} s")

# (1) PX-ON's reads at the code's spacing (section 4.6 states 13-29 s on a 150-a-minute bucket)
for n_u, reqs in ((2000, 32), (3000, 42), (4500, 57), (6041, 73)):
    print(f"  N_U {n_u}: {reqs} PX-ON reads x {DATA_INTERVAL} s = {reqs * DATA_INTERVAL:.1f} s of spacing alone "
          f"(text: {reqs / 150 * 60:.0f} s at 150 a minute); window 15:46:00-15:46:42 = 42 s")

# (2) a read sent at the last allowed second and held to the gateway timeout
last_send = 42            # 15:46:42 ET, seconds after 15:46:00
lane_start = 60           # 15:47:00 ET
late = last_send + TIMEOUT - lane_start
print(f"  a PX read sent at 15:46:{last_send} and held to the {TIMEOUT:.0f} s timeout returns at "
      f"15:46:{last_send}+{TIMEOUT:.0f}s: the lane's live close run (one slot) starts up to {late:.0f} s late")

# (3) the book's late pass at the close: its ticks are a few seconds after each minute; the window ends 15:49:00
for phase in (2, 5, 10):
    last_tick = f"15:48:{phase:02d}"
    meta_by = 48 * 60 + phase          # seconds after 15:00:00
    receipt_by = meta_by - 15          # META-ON's own 15 s bound
    lane_takes = receipt_by - 47 * 60
    print(f"  book tick phase {phase:2d} s: last close-window tick {last_tick}; EVL-META-ON trades only if "
          f"decide-close-meta8 has finished by then, so the lane's close receipt is in by 15:{receipt_by // 60:02d}:"
          f"{receipt_by % 60:02d} (the lane's run at most {lane_takes} s; the text says 15:48:25 and 85 s)")
print(f"  the book's one close decision is at its first tick >= 15:46:00 + {WAIT_CLOSE:.0f} s = 15:47:00: PX-ON's "
      f"intents (by 15:46:50) are in it; PREREG-EVL-7's EVL-LRN-ON intents (written inside the lane's run from 15:47:00) "
      f"are not, so PX-ON's buys are planned and sent a tick before any EVL-LRN-ON buy")
