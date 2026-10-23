#!/usr/bin/env python
"""timing8b.py: PREREG-EVL-8's FINAL-FIX timing table (the captain's F7; re-check 2's major 3), ARITHMETIC ONLY on the
code's own constants, read from git (origin/rel/1019h: house.py, gw.py, run.py, calendar.py, equity/live.py,
live/step.py, constitution.py, universe.py) and the texts' part bounds (PREREG-EVL-5's 45 s; PREREG-EVL-7's 90 s /
120 s). No lane data. It replaces timing8.py's close and open arithmetic: reads at the code's DATA_INTERVAL (not a
150-a-minute bucket, which is new code), a per-read timeout capped at the PX run's end, the book's ONE decision an
auction at its minute tick, and this file's buys in late passes at the book's minute ticks.

Usage: timing8b.py [REF]   (default origin/rel/1019h)
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


house, gw, run, cal = (show(p) for p in ("league/events/house.py", "league/events/gw.py", "league/events/run.py",
                                         "league/events/calendar.py"))
live, step, const, uni = (show(p) for p in ("league/equity/live.py", "league/live/step.py", "league/constitution.py",
                                            "league/events/universe.py"))
DATA_INTERVAL = num(house, "DATA_INTERVAL")
DECISION_MARGIN = num(house, "DECISION_MARGIN")
DECIDE_BUDGET = num(house, "DECIDE_BUDGET")
RECORD_BUDGET, VERDICT_BUDGET = num(house, "RECORD_BUDGET"), num(house, "VERDICT_BUDGET")
CLOSE_GRACE = int(re.search(r"CLOSE_GRACE = dt.timedelta\(minutes=(\d+)\)", house).group(1)) * 60
HOLD_LEAD = int(re.search(r"HOLD_LEAD = dt.timedelta\(seconds=(\d+)\)", house).group(1))
ONE_SLOT = "one-slot feeds lane" in house
NOT_PROMISE = "A BOUND IS NOT A PROMISE" in house
GW_TIMEOUT = float(re.search(r"timeout: float = ([0-9.]+)", gw).group(1))
EVL5_BUDGET, EVL5_FINISH = num(run, "EVL5_BUDGET"), num(run, "EVL5_FINISH")
OPEN_DECIDE = dt.time(*map(int, re.search(r"OPEN_DECIDE_AT = dt.time\((\d+), (\d+)\)", cal).groups()))
CLOSE_DECIDE_BEFORE = int(re.search(r"CLOSE_DECIDE_BEFORE = dt.timedelta\(minutes=(\d+)\)", cal).group(1))
wait = re.search(r'EVENT_DECIDE_WAIT_S = \{"open": ([0-9.]+), "close": ([0-9.]+)\}', live)
WAIT_OPEN, WAIT_CLOSE = float(wait.group(1)), float(wait.group(2))
ONE_DECISION = "ONE DECISION A SESSION AND AUCTION" in live
MINUTE_OFFSET = num(step, "MINUTE_OFFSET")
EQUITY_TICK_UNTIL = num(step, "EQUITY_TICK_UNTIL")
op = re.search(r'"order_path": \{"open_decide_before_open_s": (\d+), "open_send_before_open_s": (\d+), '
               r'"open_until_before_open_s": (\d+),\s*"close_decide_before_close_s": (\d+), "close_send_before_close_s": '
               r'(\d+),\s*"close_until_before_close_s": (\d+)\}', const)
OPEN_SEND_BEFORE, OPEN_UNTIL_BEFORE = int(op.group(2)), int(op.group(3))
CLOSE_DECIDE_S, CLOSE_SEND_S, CLOSE_UNTIL_S = int(op.group(4)), int(op.group(5)), int(op.group(6))
sip = re.search(r"SIP_DELAY = dt.timedelta\(minutes=(\d+)\)", uni)
SIP_DELAY = int(sip.group(1)) if sip else 16
EVL7_OPEN, EVL7_CLOSE = 90.0, 120.0     # PREREG-EVL-7 section 1.11 item 8 (its text of 08:09 PDT Oct 22)
META_BOUND = 15.0                        # this file's decide-close-meta8 bound


def t(h, m, s=0.0):
    return dt.datetime(2026, 10, 23, h, m) + dt.timedelta(seconds=s)


def hms(x):
    return x.strftime("%H:%M:%S")


def sec(a, b):
    return (b - a).total_seconds()


print(f"constants from {REF}: DATA_INTERVAL {DATA_INTERVAL} s ({60 / DATA_INTERVAL:.0f} reads a minute at most, one slot: "
      f"{ONE_SLOT}; 'a bound is not a promise': {NOT_PROMISE}); the gateway client's read timeout {GW_TIMEOUT:.0f} s; "
      f"DECISION_MARGIN {DECISION_MARGIN:.0f} s; DECIDE_BUDGET {DECIDE_BUDGET:.0f} s; RECORD_BUDGET {RECORD_BUDGET:.0f} s; "
      f"VERDICT_BUDGET {VERDICT_BUDGET:.0f} s; CLOSE_GRACE {CLOSE_GRACE} s; HOLD_LEAD {HOLD_LEAD} s; EVL5_BUDGET "
      f"{EVL5_BUDGET:.0f} s, EVL5_FINISH {EVL5_FINISH:.0f} s; the book: one decision an auction {ONE_DECISION}, its wait "
      f"for the lane's decision open {WAIT_OPEN:.0f} s / close {WAIT_CLOSE:.0f} s, its minute tick {MINUTE_OFFSET:.0f} s "
      f"into each minute after the options path's own reads (skipped when those hung and ended past second "
      f"{EQUITY_TICK_UNTIL:.0f}); order path open_send = open - {OPEN_SEND_BEFORE} s, open_until = open - "
      f"{OPEN_UNTIL_BEFORE} s, close decide = close - {CLOSE_DECIDE_S} s, close_send = close - {CLOSE_SEND_S} s, "
      f"close_until = close - {CLOSE_UNTIL_S} s; SIP_DELAY {SIP_DELAY} min")

# ------------------------------------------------------------------------------------------------ THE CLOSE
close = t(16, 0)
tau = close - dt.timedelta(minutes=CLOSE_DECIDE_BEFORE)
lane_run = tau + dt.timedelta(seconds=CLOSE_GRACE)
lead = lane_run - dt.timedelta(seconds=HOLD_LEAD)
cut = close - dt.timedelta(seconds=CLOSE_UNTIL_S)
book_main = close - dt.timedelta(seconds=CLOSE_DECIDE_S) + dt.timedelta(seconds=WAIT_CLOSE)
px_last_send = t(15, 46, 45)
px_read_cap = t(15, 46, 50)
px_end = lane_run - dt.timedelta(seconds=DECISION_MARGIN)
print("\nCLOSE (a full day; an early close moves every row by close - 16:00):")
print(f"  HOLD_LEAD's lead from {hms(lead)}; tau {hms(tau)} (the 15:29 bar on the Basic plan's tape from "
      f"{hms(t(15, 30) + dt.timedelta(minutes=SIP_DELAY))}); the lane's live close run {hms(lane_run)}; the book's main "
      f"close pass at its first tick at or after {hms(book_main)} (its wait ends then: the lane's run has only just "
      f"started), i.e. {hms(book_main + dt.timedelta(seconds=MINUTE_OFFSET))} or later; close_until {hms(cut)}")
ticks = [t(15, 47, MINUTE_OFFSET), t(15, 48, MINUTE_OFFSET), t(15, 49, MINUTE_OFFSET)]
inside = [x for x in ticks if x < cut]
print(f"  the book's ticks inside the close window: {', '.join(hms(x) for x in inside)} (+ the options path's reads); the "
      f"{hms(ticks[-1])} tick is past close_until: THE LAST TICK INSIDE THE WINDOW IS THE 15:48 TICK")
for n_u, n in ((2000, 32), (3000, 42), (4500, 57), (6041, 73)):
    spacing = n * DATA_INTERVAL
    print(f"  N_U {n_u}: decide-close-px8 sends {n} reads at DATA_INTERVAL: {spacing:.1f} s when each returns within "
          f"{DATA_INTERVAL} s; from {hms(tau)} the last is sent by {hms(tau + dt.timedelta(seconds=spacing - DATA_INTERVAL))} "
          f"(the run sends none after {hms(px_last_send)}: {sec(tau, px_last_send) / DATA_INTERVAL:.0f} reads at most)")
print(f"  each PX read's timeout min({GW_TIMEOUT:.0f} s, {hms(px_read_cap)} - now): a read sent at {hms(px_last_send)} "
      f"returns or is abandoned by {hms(px_read_cap)}; the run writes and ends by {hms(px_end)} (DECISION_MARGIN before "
      f"the lane's run), so the lane's live close run starts at {hms(lane_run)} whatever the gateway does (with the "
      f"client's own {GW_TIMEOUT:.0f} s a read sent at {hms(px_last_send)} could return at "
      f"{hms(px_last_send + dt.timedelta(seconds=GW_TIMEOUT))}, {sec(lane_run, px_last_send + dt.timedelta(seconds=GW_TIMEOUT)):.0f} s late)")
px_need = sec(lane_run, ticks[1])
meta_need = px_need - META_BOUND
print(f"  PX-DROP-ON's and PX-SURGE-ON's late pass: the lane's close receipt in before the 15:48 tick reads it "
      f"({hms(ticks[1])} or later): the lane's run at most {px_need:.0f} s (+ the options path's reads of that minute)")
print(f"  EVL-META-ON's late pass: decide-close-meta8 (bound {META_BOUND:.0f} s, the first task on the lane's receipt) "
      f"finished before the 15:48 tick: the lane's run at most {meta_need:.0f} s at META's bound "
      f"({px_need:.0f} s less META's own run time)")
inner = EVL5_BUDGET + EVL7_CLOSE + EVL5_FINISH
print(f"  the lane's run's isolated parts at their own bounds: PREREG-EVL-5 {EVL5_BUDGET:.0f} s + PREREG-EVL-7 "
      f"{EVL7_CLOSE:.0f} s + finish {EVL5_FINISH:.0f} s = {inner:.0f} s (before the earlier rows' own time) against "
      f"{sec(lane_run, cut):.0f} s to close_until: at such closes this file's close rows buy nothing (never an earlier row)")
print(f"  PREREG-EVL-5's part alone at its bound with its finish: {EVL5_BUDGET + EVL5_FINISH:.0f} s, leaving "
      f"{px_need - EVL5_BUDGET - EVL5_FINISH:.0f} s (PX-ON) / {meta_need - EVL5_BUDGET - EVL5_FINISH:.0f} s (META-ON) for "
      f"every earlier row")

# ------------------------------------------------------------------------------------------------ THE OPEN
open_ = t(9, 30)
tau_o = dt.datetime.combine(open_.date(), OPEN_DECIDE)
rec_o = tau_o + dt.timedelta(seconds=DECIDE_BUDGET)
cut_o = open_ - dt.timedelta(seconds=OPEN_UNTIL_BEFORE)
send_o = open_ - dt.timedelta(seconds=OPEN_SEND_BEFORE)
px_o_end = rec_o + dt.timedelta(seconds=60)
ticks_o = [t(9, m, MINUTE_OFFSET) for m in range(15, 28)]
late_o = [x for x in ticks_o if px_o_end <= x < cut_o]
print("\nOPEN:")
print(f"  tau {hms(tau_o)} (the 08:58 bar on the tape from {hms(t(8, 59) + dt.timedelta(minutes=SIP_DELAY))}); the lane's "
      f"open run from {hms(tau_o)}, its receipt by {hms(rec_o)} at DECIDE_BUDGET (PREREG-EVL-7's learner part "
      f"{EVL7_OPEN:.0f} s inside it); the book's main open pass on that receipt, or at its first tick at or after "
      f"{hms(tau_o + dt.timedelta(seconds=WAIT_OPEN))}; sends from {hms(send_o)}; open_until {hms(cut_o)}")
for n_u, n in ((2000, 10), (3000, 15), (4500, 23), (6041, 31)):
    print(f"  N_U {n_u}: PX-GAP-O1's pm_D reads {n} x {DATA_INTERVAL} s = {n * DATA_INTERVAL:.1f} s")
print(f"  decide-open-px8 (PX-GAP-O1, then EVL-META-O1) the first task on the lane's open receipt, 60 s, never past "
      f"{hms(px_o_end + dt.timedelta(seconds=60))} (by {hms(px_o_end)} on a receipt at the bound); THE OPEN LATE PASS at the first "
      f"book tick after it finished: {len(late_o)} ticks inside the window even then ({hms(late_o[0])} to "
      f"{hms(late_o[-1])})")
print("\nREQUESTS: under release 1019h every lane read goes through its one slot at DATA_INTERVAL (at most "
      f"{60 / DATA_INTERVAL:.0f} a minute); this file's reads run only in its own runs on that slot, so they never share "
      "a moment with the lane's own reads; the 150-a-minute token bucket over every data-host read is NEW CODE (the "
      "judge's harness H2), and when it ships this file's reads keep the slot's spacing.")
