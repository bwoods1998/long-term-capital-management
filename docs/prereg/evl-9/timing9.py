#!/usr/bin/env python
"""timing9.py: PREREG-EVL-9's timing table (the captain's W11; check 2's major 10), ARITHMETIC ONLY on the code's own
constants, read from git (origin/rel/1019h: calendar.py, house.py, run.py, equity/live.py, constitution.py,
universe.py), on the earlier files' part bounds (PREREG-EVL-5's 45 s; PREREG-EVL-7's 90 s / 120 s, its section 1.11 item
8) and on PREREG-EVL-8's timing table (evl8/PREREG-EVL-8.md section 4.6, its final text: decide-open-px8 60 s never past
09:19:30; decide-close-px8 in [15:46:00, 15:46:50]; decide-close-meta8 on the lane's close receipt when that is by
15:48:25, 15 s, never past 15:48:40). No lane data.

Usage: timing9.py [REF]   (default origin/rel/1019h)
"""
import datetime as dt
import re
import subprocess
import sys

REPO = "/home/bwoods1998/Work/long-term-capital-management"
REF = sys.argv[1] if len(sys.argv) > 1 else "origin/rel/1019h"


def show(path):
    return subprocess.run(["git", "-C", REPO, "show", f"{REF}:{path}"], capture_output=True, text=True, check=True).stdout


def num(src, name):
    m = re.search(rf"^\s*{name}\s*=\s*([0-9.]+)", src, re.M)
    return float(m.group(1))


cal = show("league/events/calendar.py")
house = show("league/events/house.py")
run = show("league/events/run.py")
live = show("league/equity/live.py")
const = show("league/constitution.py")
uni = show("league/events/universe.py")

OPEN_DECIDE = dt.time(*map(int, re.search(r"OPEN_DECIDE_AT = dt.time\((\d+), (\d+)\)", cal).groups()))
CLOSE_DECIDE_BEFORE = int(re.search(r"CLOSE_DECIDE_BEFORE = dt.timedelta\(minutes=(\d+)\)", cal).group(1))
CLOSE_SEND_BEFORE = int(re.search(r"CLOSE_SEND_BEFORE = dt.timedelta\(minutes=(\d+)\)", cal).group(1))
DECIDE_BUDGET = num(house, "DECIDE_BUDGET")
CLOSE_GRACE = int(re.search(r"CLOSE_GRACE = dt.timedelta\(minutes=(\d+)\)", house).group(1)) * 60
HOLD_LEAD = int(re.search(r"HOLD_LEAD = dt.timedelta\(seconds=(\d+)\)", house).group(1))
SCORE_AT = re.search(r"SCORE_AT = dt.time\((\d+), (\d+)\)", house).groups()
EVL5_BUDGET, EVL5_FINISH = num(run, "EVL5_BUDGET"), num(run, "EVL5_FINISH")
MARK_BATCH = num(run, "MARK_BATCH")
wait = re.search(r'EVENT_DECIDE_WAIT_S = \{"open": ([0-9.]+), "close": ([0-9.]+)\}', live)
WAIT_OPEN, WAIT_CLOSE = float(wait.group(1)), float(wait.group(2))
op = re.search(r'"order_path": \{"open_decide_before_open_s": (\d+), "open_send_before_open_s": (\d+), '
               r'"open_until_before_open_s": (\d+),\s*"close_decide_before_close_s": (\d+), "close_send_before_close_s": '
               r'(\d+),\s*"close_until_before_close_s": (\d+)\}', const)
OPEN_UNTIL_BEFORE, CLOSE_UNTIL_BEFORE = int(op.group(3)), int(op.group(6))
sip = re.search(r"SIP_DELAY = dt.timedelta\(minutes=(\d+)\)", uni)
SIP_DELAY = int(sip.group(1)) if sip else 16
EVL7_OPEN, EVL7_CLOSE = 90.0, 120.0
EVL8_OPEN_BOUND, EVL8_OPEN_LAST = 60.0, (9, 19, 30)
EVL8_META_BY, EVL8_META_BOUND, EVL8_META_LAST = (15, 48, 25), 15.0, (15, 48, 40)
# THIS FILE'S PARTS (section 7.3's CLOCK): bounds of the warm parts and the book's margin
W9_OPEN_BOUND = 60.0          # decide-open-warm9 after decide-open-px8 (or the lane's receipt)
W9_CLOSE_BOUND = 10.0         # decide-close-warm9 after decide-close-meta8 (or the lane's receipt)
W9_SEND_MARGIN = 20.0         # real money buys only intents written >= 20 s before the book's cut-off
W9_PRE_OPEN = (9, 1, 0)       # prepass-warm9:open after EVL-8's prepass-meta:open (09:00:00)
W9_PRE_CLOSE = (15, 33, 0)    # prepass-warm9:close after EVL-8's prepass-meta:close (15:30:00)
W9_PRE_BOUND = 120.0
W9_PRE_LAST = {"open": (9, 13, 0), "close": (15, 43, 0)}
SYNTH_COMPUTE_S = 10.0        # B6's test bound on a synthetic 850-candidate pool (features, fit, scores)


def t(h, m, s=0):
    return dt.datetime(2026, 10, 23, h, m, s)


def hms(x):
    return x.strftime("%H:%M:%S")


def sec(x):
    return dt.timedelta(seconds=x)


print(f"constants from {REF}: open decide {OPEN_DECIDE}, close decide = close - {CLOSE_DECIDE_BEFORE} min, send-by = close - "
      f"{CLOSE_SEND_BEFORE} min; order_path open_until = open - {OPEN_UNTIL_BEFORE} s, close_until = close - "
      f"{CLOSE_UNTIL_BEFORE} s; DECIDE_BUDGET {DECIDE_BUDGET:.0f} s, CLOSE_GRACE {CLOSE_GRACE} s, HOLD_LEAD {HOLD_LEAD} s; "
      f"SCORE_AT {SCORE_AT[0]}:{SCORE_AT[1]} ET; EVL5_BUDGET {EVL5_BUDGET:.0f} s, EVL5_FINISH {EVL5_FINISH:.0f} s; book "
      f"EVENT_DECIDE_WAIT_S open {WAIT_OPEN:.0f} s, close {WAIT_CLOSE:.0f} s; SIP_DELAY {SIP_DELAY} min; MARK_BATCH "
      f"{MARK_BATCH:.0f}")

# ---------------------------------------------------------------- OPEN (EVL-WL-O1)
open_ = t(9, 30)
tau_o = dt.datetime.combine(open_.date(), OPEN_DECIDE)
cut_o = open_ - sec(OPEN_UNTIL_BEFORE)
rec_o = tau_o + sec(DECIDE_BUDGET)
px8_last = t(*EVL8_OPEN_LAST)
w9o_last = px8_last + sec(W9_OPEN_BOUND)
w9o_send = cut_o - sec(60)
print("\nOPEN (EVL-WL-O1):")
print(f"  prepass-warm9:open at {hms(t(*W9_PRE_OPEN))}, bound {W9_PRE_BOUND:.0f} s, never past {hms(t(*W9_PRE_LAST['open']))} "
      f"(after EVL-8's prepass-meta:open at 09:00:00; lowest priority; a cache only)")
print(f"  tau {hms(tau_o)}; the lane's open run starts {hms(tau_o)}, its receipt by {hms(rec_o)} at the task bound "
      f"(PREREG-EVL-7's EVL-LRN-O1 part {EVL7_OPEN:.0f} s inside it); EVL-8's decide-open-px8 on that receipt, "
      f"{EVL8_OPEN_BOUND:.0f} s, never past {hms(px8_last)}")
print(f"  decide-open-warm9 on the later of decide-open-px8's finish and the lane's receipt: bound {W9_OPEN_BOUND:.0f} s, never "
      f"past {hms(w9o_last)}; the book plans this file's open rows in the late pass after EVL-8's, sending by "
      f"{hms(w9o_send)} (60 s before the cut-off {hms(cut_o)}): {(w9o_send - w9o_last).seconds} s of slack at the latest")
print(f"  the book's own wait for the lane's open decision ends {hms(tau_o + sec(WAIT_OPEN))}: every earlier row is planned "
      f"from the lane's receipt as today; this file's part starts only after it, so it delays none")

# ---------------------------------------------------------------- CLOSE (EVL-WL-ON)
close = t(16, 0)
tau_c = close - dt.timedelta(minutes=CLOSE_DECIDE_BEFORE)
run_c = tau_c + sec(CLOSE_GRACE)
cut_c = close - sec(CLOSE_UNTIL_BEFORE)
bar_1530 = t(15, 30) + dt.timedelta(minutes=SIP_DELAY)
w9c_write_by = cut_c - sec(W9_SEND_MARGIN)
print("\nCLOSE (EVL-WL-ON, a full day; an early close moves every row by (close - 16:00)):")
print(f"  prepass-warm9:close at {hms(t(*W9_PRE_CLOSE))}, bound {W9_PRE_BOUND:.0f} s, never past "
      f"{hms(t(*W9_PRE_LAST['close']))} (after EVL-8's prepass-meta:close at 15:30:00; lowest priority; a cache only)")
print(f"  tau {hms(tau_c)}; the 15:30 bars on the tape from {hms(bar_1530)}; EVL-8's decide-close-px8 in "
      f"[{hms(bar_1530)}, 15:46:50]; the lane's live close run from {hms(run_c)} (PREREG-EVL-5's part {EVL5_BUDGET:.0f} s, "
      f"PREREG-EVL-7's EVL-LRN-ON part {EVL7_CLOSE:.0f} s, which fetches the '1530' marks of the pool's candidates as its "
      f"first read); the book's cut-off {hms(cut_c)}")
print(f"  decide-close-warm9 on the lane's close receipt, after decide-close-meta8 when that runs: its own bound "
      f"{W9_CLOSE_BOUND:.0f} s (B6's test: {SYNTH_COMPUTE_S:.0f} s or less on a synthetic 850-candidate pool), no network "
      f"read (the marks as stored by the lane's run); real money buys only intents written by {hms(w9c_write_by)} "
      f"({W9_SEND_MARGIN:.0f} s before the cut-off)")
for meta_runs, label in ((True, "when EVL-8's META-ON runs at its full 15 s"), (False, "when it does not run")):
    need = W9_CLOSE_BOUND + (EVL8_META_BOUND if meta_runs else 0.0)
    latest = w9c_write_by - sec(need)
    print(f"  {label}: the lane's close receipt must be in by {hms(latest)}, so the lane's run may take at most "
          f"{(latest - run_c).seconds} s; PREREG-EVL-5's part at its bound with the receipt's finish "
          f"({EVL5_BUDGET + EVL5_FINISH:.0f} s) leaves {(latest - run_c).seconds - EVL5_BUDGET - EVL5_FINISH:.0f} s for "
          f"every earlier row and PREREG-EVL-7's part; PREREG-EVL-7's part at its {EVL7_CLOSE:.0f} s bound alone exceeds it")
print(f"  NOT FINISHED by {hms(w9c_write_by)}: the decision is still written when the part finishes inside its bound "
      f"(a planned pick with binding 'window', the shadow keeps it); NOT STARTED or CUT: no intent at that close, and "
      f"decide-close-warm9-late:<D> decides it later by itself exactly as of tau (training state and a reported shadow, "
      f"never judged, never traded)")
score_h, score_m = int(SCORE_AT[0]), int(SCORE_AT[1])
print(f"\nTHE HISTORY JOB'S RATE PAUSES (check 2's minor 11): the House's score at {score_h:02d}:{score_m:02d} ET is "
      f"{(score_h + 4) % 24:02d}:{score_m:02d}Z (the next day) in EDT and {(score_h + 5) % 24:02d}:{score_m:02d}Z from Nov 1 (EST); the job pauses from 20:25 ET "
      f"to the score receipt's finish")
