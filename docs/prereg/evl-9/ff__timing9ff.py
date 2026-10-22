#!/usr/bin/env python
"""timing9ff.py: PREREG-EVL-9's timing table for the final minimal fix (re-check 1's major 1, re-check 2's major 4).
ARITHMETIC ONLY on the code's own constants, read from git (origin/rel/1019h: calendar.py, house.py, run.py,
equity/live.py, live/step.py, constitution.py, universe.py), and on the earlier files' newest texts:
  PREREG-EVL-7 (evl7/PREREG-EVL-7.md, sha256 2f2cff59...): the learner part is ITS OWN live receipt
    decide-*-lrnlive:<D>, started in the House's turn once decide-open:<D> / decide-close:<D> has finished; its bound
    the earlier of 90 s (open) / 120 s (close) from its own start and its task's own bound less EVL5_FINISH; EVL-LRN-ON's
    part fetches the '1530' marks of its candidates as its own first read; a learner pick waits for its own receipt
    (A113's reading) and keeps no room from an earlier row while it waits.
  PREREG-EVL-8 (evl8/PREREG-EVL-8.md, sha256 430ea725..., section 4.6): the book decides at its minute tick,
    MINUTE_OFFSET into each minute; the last tick inside the close window is the 15:48 tick; decide-open-px8 is the
    first task after the lane's open receipt, 60 s, never past 09:19:30; decide-close-meta8 the first task after the
    lane's close receipt, 15 s, never past 15:48:40; the pre-passes YIELD before each step and write nothing until whole;
    this file's buys are planned in LATE PASSES at the book's later ticks, after PREREG-EVL-8's.
No lane data. Usage: timing9ff.py [REF]   (default origin/rel/1019h)
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


cal, house, run = show("league/events/calendar.py"), show("league/events/house.py"), show("league/events/run.py")
live, step, const = show("league/equity/live.py"), show("league/live/step.py"), show("league/constitution.py")
uni = show("league/events/universe.py")
OPEN_DECIDE = dt.time(*map(int, re.search(r"OPEN_DECIDE_AT = dt.time\((\d+), (\d+)\)", cal).groups()))
CLOSE_DECIDE_BEFORE = int(re.search(r"CLOSE_DECIDE_BEFORE = dt.timedelta\(minutes=(\d+)\)", cal).group(1))
DECIDE_BUDGET = num(house, "DECIDE_BUDGET")
CLOSE_GRACE = int(re.search(r"CLOSE_GRACE = dt.timedelta\(minutes=(\d+)\)", house).group(1)) * 60
EVL5_BUDGET, EVL5_FINISH = num(run, "EVL5_BUDGET"), num(run, "EVL5_FINISH")
MINUTE_OFFSET = num(step, "MINUTE_OFFSET")
wait = re.search(r'EVENT_DECIDE_WAIT_S = \{"open": ([0-9.]+), "close": ([0-9.]+)\}', live)
WAIT_OPEN, WAIT_CLOSE = float(wait.group(1)), float(wait.group(2))
op = re.search(r'"order_path": \{"open_decide_before_open_s": (\d+), "open_send_before_open_s": (\d+), '
               r'"open_until_before_open_s": (\d+),\s*"close_decide_before_close_s": (\d+), "close_send_before_close_s": '
               r'(\d+),\s*"close_until_before_close_s": (\d+)\}', const)
OPEN_UNTIL_BEFORE, CLOSE_UNTIL_BEFORE = int(op.group(3)), int(op.group(6))
sip = re.search(r"SIP_DELAY = dt.timedelta\(minutes=(\d+)\)", uni)
SIP_DELAY = int(sip.group(1)) if sip else 16
EVL7_OPEN, EVL7_CLOSE = 90.0, 120.0                     # PREREG-EVL-7 section 1.11 item 8
EVL8_PX_OPEN, EVL8_PX_OPEN_LAST = 60.0, (9, 19, 30)     # PREREG-EVL-8 section 4.6
EVL8_META_CLOSE, EVL8_META_LAST = 15.0, (15, 48, 40)
W9_OPEN, W9_CLOSE = 60.0, 10.0                          # this file's parts' bounds (section 7.3)
W9_OPEN_LAST = (9, 20, 30)
W9_PRE = {"open": ((9, 1, 0), (9, 13, 0)), "close": ((15, 33, 0), (15, 43, 0))}


def t(h, m, s=0):
    return dt.datetime(2026, 10, 23, h, m, s)


def hms(x):
    return x.strftime("%H:%M:%S")


def sec(x):
    return dt.timedelta(seconds=x)


def next_tick(x):
    """The book's first minute tick at or after x (MINUTE_OFFSET seconds into a minute)."""
    base = x.replace(second=0, microsecond=0) + sec(MINUTE_OFFSET)
    return base if base >= x else base + dt.timedelta(minutes=1)


print(f"constants from {REF}: open decide {OPEN_DECIDE}; close decide = close - {CLOSE_DECIDE_BEFORE} min; open_until = "
      f"open - {OPEN_UNTIL_BEFORE} s; close_until = close - {CLOSE_UNTIL_BEFORE} s; DECIDE_BUDGET {DECIDE_BUDGET:.0f} s; "
      f"CLOSE_GRACE {CLOSE_GRACE} s; EVL5_BUDGET {EVL5_BUDGET:.0f} s, EVL5_FINISH {EVL5_FINISH:.0f} s; MINUTE_OFFSET "
      f"{MINUTE_OFFSET:.0f} s; book EVENT_DECIDE_WAIT_S open {WAIT_OPEN:.0f} s, close {WAIT_CLOSE:.0f} s; SIP_DELAY "
      f"{SIP_DELAY} min")

# ---------------------------------------------------------------- OPEN (EVL-WL-O1)
tau_o = dt.datetime.combine(t(9, 30).date(), OPEN_DECIDE)
task_o = tau_o + sec(DECIDE_BUDGET)
cut_o = t(9, 30) - sec(OPEN_UNTIL_BEFORE)
lrn_o_last = task_o - sec(EVL5_FINISH)
px8_last = t(*EVL8_PX_OPEN_LAST)
w9o_last = t(*W9_OPEN_LAST)
tick_o = next_tick(w9o_last)
print("\nOPEN (EVL-WL-O1):")
print(f"  prepass-warm9:open from {hms(t(*W9_PRE['open'][0]))} (after EVL-8's prepass-meta:open, 09:00:00), lowest "
      f"priority, YIELDS before each step to any lane task due, writes nothing until whole, never past "
      f"{hms(t(*W9_PRE['open'][1]))}")
print(f"  tau {hms(tau_o)}; the lane's decide-open task's Deadline {hms(task_o)}; PREREG-EVL-7's decide-open-lrnlive "
      f"in that turn once the House's receipt is in, bound min(start + {EVL7_OPEN:.0f} s, {hms(lrn_o_last)}); EVL-8's "
      f"decide-open-px8 the next task, {EVL8_PX_OPEN:.0f} s, never past {hms(px8_last)}")
print(f"  decide-open-warm9: the next task after both (any status, or their bounds), ahead of any record or verdict "
      f"pass due; bound {W9_OPEN:.0f} s, never past {hms(w9o_last)}")
print(f"  the open late pass for this file's buys: the first book tick after it finishes, after EVL-8's late pass; at the "
      f"latest {hms(tick_o)}; the cut-off {hms(cut_o)}: {(cut_o - tick_o).seconds} s of slack (every tick from then to "
      f"{hms(cut_o - sec(60 - MINUTE_OFFSET))} plans again while a pick waits)")

# ---------------------------------------------------------------- CLOSE (EVL-WL-ON)
close = t(16, 0)
tau_c = close - dt.timedelta(minutes=CLOSE_DECIDE_BEFORE)
run_c = tau_c + sec(CLOSE_GRACE)
task_c = run_c + sec(DECIDE_BUDGET)
lrn_c_last = task_c - sec(EVL5_FINISH)
cut_c = close - sec(CLOSE_UNTIL_BEFORE)
last_tick = next_tick(cut_c - sec(60))
print("\nCLOSE (EVL-WL-ON; a full day; an early close moves every row by (close - 16:00)):")
print(f"  prepass-warm9:close from {hms(t(*W9_PRE['close'][0]))} (after EVL-8's prepass-meta:close, 15:30:00), as the "
      f"open's, never past {hms(t(*W9_PRE['close'][1]))}")
print(f"  tau {hms(tau_c)}; EVL-8's decide-close-px8 ends by 15:46:55; the lane's live close run from {hms(run_c)}, its "
      f"task's Deadline {hms(task_c)} (PREREG-EVL-5's part {EVL5_BUDGET:.0f} s); PREREG-EVL-7's decide-close-lrnlive in "
      f"that turn once the House's receipt is in, its first read the '1530' marks of its candidates (this file's "
      f"candidates), bound min(start + {EVL7_CLOSE:.0f} s, {hms(lrn_c_last)}); EVL-8's decide-close-meta8 the next task, "
      f"{EVL8_META_CLOSE:.0f} s, never past {hms(t(*EVL8_META_LAST))}")
print(f"  decide-close-warm9: the next task after both (any status, or their bounds), ahead of any record or verdict pass "
      f"due; bound {W9_CLOSE:.0f} s; no network read; started at any time before the close - 5 minutes (15:55:00)")
print(f"  the book's close cut-off {hms(cut_c)}; its last tick inside the window {hms(last_tick)}; THIS FILE'S BUYS: the "
      f"close late pass after EVL-8's, at the first tick at which decide-close-warm9 has finished 'ok' naming the "
      f"learner; real money only for a decision finished before the {hms(last_tick)} tick reads it")
budget = (last_tick - run_c).total_seconds()
for meta, lab in ((EVL8_META_CLOSE, "EVL-META-ON at its full 15 s"), (0.0, "no EVL-META-ON run")):
    room = budget - meta - W9_CLOSE
    print(f"  with {lab} and this file's part at its {W9_CLOSE:.0f} s bound: the lane's close run plus PREREG-EVL-7's "
          f"part must take at most {room:.0f} s (from {hms(run_c)}); PREREG-EVL-5's part at its bound with its finish "
          f"({EVL5_BUDGET + EVL5_FINISH:.0f} s) alone {'exceeds' if EVL5_BUDGET + EVL5_FINISH > room else 'fits'} it; "
          f"PREREG-EVL-7's part at its {EVL7_CLOSE:.0f} s bound alone exceeds it")
for fin, s_ in ((t(15, 47, 58), "planned"), (t(15, 48, 5), "not planned (binding 'window'; the shadow keeps it)")):
    tk = next_tick(fin)
    print(f"  TEST: decide-close-warm9 finished at {hms(fin)} -> first tick {hms(tk)}: "
          f"{'planned at ' + hms(tk) if tk <= last_tick else s_}")
print("  NOT STARTED by the close - 5 minutes, or CUT at its bound: no intent at that close; "
      "decide-close-warm9-late:<D> decides it later by itself exactly as of tau (training state and a reported shadow)")
print("\nTHE HISTORY JOB'S RATE PAUSES, in ET: 09:00-09:45, 15:30-16:20, 18:25-18:45 and 20:25 ET to the finish of the "
      "House's 20:30 ET score; the score is 00:30Z (EDT) and 01:30Z from Nov 1 (EST)")
