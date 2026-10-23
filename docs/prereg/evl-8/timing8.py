#!/usr/bin/env python
"""timing8.py: PREREG-EVL-8's timing table (the captain's F7) and request load (check 2's minor 11), ARITHMETIC ONLY
on the code's own constants, read from git (origin/rel/1019h: calendar.py, house.py, run.py, equity/live.py,
constitution.py) and the texts' part bounds (PREREG-EVL-5's 45 s; PREREG-EVL-7's work text 90 s / 120 s). No lane data.

Usage: timing8.py [REF]   (default origin/rel/1019h)
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
EVL5_BUDGET, EVL5_FINISH = num(run, "EVL5_BUDGET"), num(run, "EVL5_FINISH")
MARK_BATCH = num(run, "MARK_BATCH")
wait = re.search(r'EVENT_DECIDE_WAIT_S = \{"open": ([0-9.]+), "close": ([0-9.]+)\}', live)
WAIT_OPEN, WAIT_CLOSE = float(wait.group(1)), float(wait.group(2))
HELD_OVERDUE_S = num(live, "HELD_OVERDUE_S")
op = re.search(r'"order_path": \{"open_decide_before_open_s": (\d+), "open_send_before_open_s": (\d+), '
               r'"open_until_before_open_s": (\d+),\s*"close_decide_before_close_s": (\d+), "close_send_before_close_s": '
               r'(\d+),\s*"close_until_before_close_s": (\d+)\}', const)
OPEN_UNTIL_BEFORE, CLOSE_UNTIL_BEFORE = int(op.group(3)), int(op.group(6))
sip = re.search(r"SIP_DELAY = dt.timedelta\(minutes=(\d+)\)", uni)
SIP_DELAY = int(sip.group(1)) if sip else 16
EVL7_OPEN, EVL7_CLOSE = 90.0, 120.0           # PREREG-EVL-7 (work text of 05:48 PDT Oct 22, section 1.11 item 8)


def t(h, m, s=0):
    return dt.datetime(2026, 10, 23, h, m, s)


def hms(x):
    return x.strftime("%H:%M:%S")


print(f"constants from {REF}: open decide {OPEN_DECIDE}, close decide = close - {CLOSE_DECIDE_BEFORE} min, send-by = "
      f"close - {CLOSE_SEND_BEFORE} min; order_path open_until = open - {OPEN_UNTIL_BEFORE} s, close_until = close - "
      f"{CLOSE_UNTIL_BEFORE} s; DECIDE_BUDGET {DECIDE_BUDGET:.0f} s, CLOSE_GRACE {CLOSE_GRACE} s, HOLD_LEAD {HOLD_LEAD} s; "
      f"EVL5_BUDGET {EVL5_BUDGET:.0f} s, EVL5_FINISH {EVL5_FINISH:.0f} s; book EVENT_DECIDE_WAIT_S open {WAIT_OPEN:.0f} s, "
      f"close {WAIT_CLOSE:.0f} s; HELD_OVERDUE_S {HELD_OVERDUE_S:.0f} s; SIP_DELAY {SIP_DELAY} min; MARK_BATCH "
      f"{MARK_BATCH:.0f}")
close = t(16, 0)
tau_c = close - dt.timedelta(minutes=CLOSE_DECIDE_BEFORE)
run_c = tau_c + dt.timedelta(seconds=CLOSE_GRACE)
cut_c = close - dt.timedelta(seconds=CLOSE_UNTIL_BEFORE)
lead_c = run_c - dt.timedelta(seconds=HOLD_LEAD)
bar_1530 = t(15, 30) + dt.timedelta(minutes=SIP_DELAY)
px_c_end = run_c - dt.timedelta(seconds=10)
print("\nCLOSE (a full day):")
print(f"  tau (the close decision time) {hms(tau_c)}; the 15:30 bars on the Basic plan's tape from {hms(bar_1530)}; HOLD_LEAD"
      f" from {hms(lead_c)}; the lane's live close run starts {hms(run_c)}; the book's cut-off {hms(cut_c)} "
      f"({(cut_c - run_c).seconds} s after the run starts); the task bound {hms(run_c + dt.timedelta(seconds=DECIDE_BUDGET))}")
print(f"  decide-close-px8 (PX-ON) in [{hms(bar_1530)}, {hms(px_c_end)}]: {(px_c_end - bar_1530).seconds} s, ending "
      f"{(run_c - px_c_end).seconds} s before the lane's run")
inner = EVL5_BUDGET + EVL7_CLOSE + EVL5_FINISH
print(f"  inside the lane's run, the isolated parts' own bounds: PREREG-EVL-5 {EVL5_BUDGET:.0f} s + PREREG-EVL-7 "
      f"{EVL7_CLOSE:.0f} s + finish {EVL5_FINISH:.0f} s = {inner:.0f} s, against {(cut_c - run_c).seconds} s to the cut-off "
      f"and {DECIDE_BUDGET:.0f} s of task bound (before the earlier rows' own time)")
meta_need = 15 + 20
latest_receipt = cut_c - dt.timedelta(seconds=meta_need)
print(f"  decide-close-meta8 (EVL-META-ON) on the lane's close receipt when that is by {hms(latest_receipt)} (its 15 s bound "
      f"plus 20 s for the book's late pass before {hms(cut_c)}): the lane's run may then take at most "
      f"{(latest_receipt - run_c).seconds} s; PREREG-EVL-5's part alone at its bound with the receipt's finish "
      f"({EVL5_BUDGET + EVL5_FINISH:.0f} s) leaves {(latest_receipt - run_c).seconds - EVL5_BUDGET - EVL5_FINISH:.0f} s for "
      f"the earlier rows; with PREREG-EVL-7's learner at its bound, none")
open_ = t(9, 30)
tau_o = dt.datetime.combine(open_.date(), OPEN_DECIDE)
cut_o = open_ - dt.timedelta(seconds=OPEN_UNTIL_BEFORE)
bar_0858 = t(8, 59) + dt.timedelta(minutes=SIP_DELAY)
rec_o = tau_o + dt.timedelta(seconds=DECIDE_BUDGET)
px_o_end = tau_o + dt.timedelta(seconds=DECIDE_BUDGET + 120)
print("\nOPEN:")
print(f"  tau {hms(tau_o)}; the 08:58 bar on the tape from {hms(bar_0858)}; the lane's open run starts {hms(tau_o)} and its "
      f"receipt is in by {hms(rec_o)} at the task bound (PREREG-EVL-7's learner part {EVL7_OPEN:.0f} s inside it); the book waits "
      f"for it to {hms(tau_o + dt.timedelta(seconds=WAIT_OPEN))}; the cut-off {hms(cut_o)}")
print(f"  decide-open-px8 (PX-GAP-O1 then EVL-META-O1) on that receipt, bound 60 s, never past {hms(px_o_end)}; the book's "
      f"late pass for this file's open rows by {hms(cut_o - dt.timedelta(seconds=60))}: "
      f"{(cut_o - dt.timedelta(seconds=60) - px_o_end).seconds} s of slack at the latest")
# ---- requests (check 2's minor 11): price/fees_and_requests.out's rows with the controls at 200 names
base = {2000: 802, 3000: 837, 4500: 892, 6041: 948}
prints_old = (3 * 40 + 2 * 60) * 2 * 1.5
prints_new = (3 * 40 + 2 * 200) * 2 * 1.5
peak_close = {2000: 32, 3000: 42, 4500: 57, 6041: 73}
print("\nREQUESTS A SESSION (the Basic plan's 200 a minute; price/fees_and_requests.out with the controls at 200 names):")
for n_u, tot in base.items():
    new = tot - prints_old + prints_new
    print(f"  N_U {n_u}: {new:.0f} requests ({new / 200:.1f} minutes of the plan); at the close's PX run {peak_close[n_u]} "
          f"({peak_close[n_u] / 150 * 60:.0f} s of the lane's 150-a-minute bucket)")
print(f"  auction prints: {3 * 40 + 2 * 200} print-settled events a session x 2 prints x 1.5 pages = {prints_new:.0f}"
      f" ({prints_new - prints_old:.0f} more than with 60-name controls: 2 x 140 more events)")
