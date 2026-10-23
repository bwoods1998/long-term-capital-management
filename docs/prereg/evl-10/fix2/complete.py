"""Second fix round of PREREG-EVL-10 (Oct 23): section 1.4's COMPLETE, as the round restates it. SYNTHETIC ONLY: no
store, House or gateway is read; scan times are drawn, never read.

COMPLETE (restated): a session whose stored r2_scan times have no gap over 5 minutes between consecutive times,
counting 07:30:00 ET as the first time and tau - 30 s as the last.

(1) The section 11 tests: a 90 s grid from 07:31:10 to 15:38:40 is COMPLETE; a gap of exactly 300 s is COMPLETE; one of
    301 s is not; a first scan more than 5 minutes after 07:30:00, or a last one more than 5 minutes before tau - 30 s,
    is not. (The recheck's suggested grid "every 90 s to 15:39:05" lands on 15:38:40, not 15:39:05: 29,275 s is not a
    multiple of 90.)
(2) The House's cadence (section 1.5's WHEN): R2's scans come only on the jobs the House's publishes start; publishes
    60-121 s apart (house.py's H5 note: once a minute at most, 97-121 s apart in a busy session); `_background` runs one
    job per key at a time, so a publish while R2's job (one scan and at most one streamed call, the whole answer within
    90 s) is still running starts none. Under the old literal rule no session is complete (q = Q_DEFAULT for good);
    under the restated rule every session without a House stall is, and a stall of over 5 minutes makes it incomplete.
(3) q(D) then leaves Q_DEFAULT: the frozen `fix1/r2_spec.share` on five complete sessions' counts.
"""
from __future__ import annotations

import importlib.util
import random
import sys

sys.dont_write_bytecode = True

GAP = 300.0                                    # "no gap over 5 minutes"
START = 7.5 * 3600                             # 07:30:00 ET, seconds of the day
TAU = 15 * 3600 + 40 * 60                      # tau on a full day: the close (16:00) - 20 minutes
LAST = TAU - 30                                # tau - 30 s


def hms(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def complete(scans: list[float], start: float = START, last: float = LAST) -> bool:
    """The restated COMPLETE: 07:30:00 counted as the first time, tau - 30 s as the last, no consecutive gap over GAP."""
    times = [start] + sorted(t for t in scans if start <= t <= last) + [last]
    return all(b - a <= GAP for a, b in zip(times, times[1:]))


def complete_literal(scans: list[float], start: float = START, last: float = LAST) -> bool:
    """The rule as the first fix round wrote it: a stored scan at or before 07:30:00 and one at or after tau - 30 s."""
    if not scans:
        return False
    s = sorted(scans)
    return s[0] <= start and s[-1] >= last and all(b - a <= GAP for a, b in zip(s, s[1:]))


def t(h: int, m: int, sec: int = 0) -> float:
    return h * 3600 + m * 60 + sec


# (1) the tests
grid = [t(7, 31, 10) + 90 * k for k in range(10_000) if t(7, 31, 10) + 90 * k <= t(15, 38, 40)]
print(f"(1) grid: {len(grid)} scans {hms(grid[0])} .. {hms(grid[-1])} every 90 s -> COMPLETE {complete(grid)} "
      f"(literal rule {complete_literal(grid)})")
at = t(12, 1, 10)
assert at in grid
for extra, label in ((300, "a gap of exactly 5 minutes"), (301, "one gap of 5 minutes 1 second")):
    s = [x for x in grid if not at < x < at + extra] + [at + extra]
    gaps = sorted({round(b - a) for a, b in zip(sorted(s), sorted(s)[1:])})
    print(f"    {label} ({hms(at)} -> {hms(at + extra)}, none between; gaps {gaps[-3:]} s): COMPLETE {complete(s)}")
late_first = [x for x in grid if x >= t(7, 35, 1)]
print(f"    first scan {hms(late_first[0])} (more than 5 minutes after 07:30:00): COMPLETE {complete(late_first)}")
early_last = [x for x in grid if x <= t(15, 34, 29)]
print(f"    last scan {hms(early_last[-1])} (more than 5 minutes before tau - 30 s = {hms(LAST)}): "
      f"COMPLETE {complete(early_last)}")
print(f"    a scan before 07:30:00 does not shorten the first gap (07:29:59 added to the late-first case): "
      f"COMPLETE {complete([t(7, 29, 59)] + late_first)}")


# (2) the House's cadence
def session(rng: random.Random, call_share: float, stall: float = 0.0) -> list[float]:
    """Scan times of one session: publishes from a uniform phase before 07:30:00, 60-121 s apart; a job (one scan, then a
    streamed call of 3-90 s with probability `call_share`) starts at a publish only when the last one has finished; an
    optional House stall (no publish) of `stall` seconds at a uniform time of the session."""
    p = START - rng.uniform(0, 121)
    stall_at = rng.uniform(START, LAST - stall) if stall else None
    busy_until = -1.0
    scans: list[float] = []
    while p < LAST:
        if stall_at is not None and stall_at <= p < stall_at + stall:
            p = stall_at + stall + rng.uniform(0, 60)
            continue
        if p >= START and p >= busy_until:
            scans.append(p)
            busy_until = p + 1.0 + (rng.uniform(3, 90) if rng.random() < call_share else 0.0)
        p += rng.uniform(60, 121)
    return scans


rng = random.Random(20261023_2)
N = 20_000
print(f"\n(2) the House's cadence, {N:,} sessions a cell (seed 202610232):")
for call_share, stall in ((1.0, 0.0), (0.3, 0.0), (0.0, 0.0), (1.0, 240.0), (1.0, 361.0)):
    ok = lit = 0
    worst = 0.0
    for _ in range(N):
        s = session(rng, call_share, stall)
        ok += complete(s)
        lit += complete_literal(s)
        times = [START] + s + [LAST]
        worst = max(worst, max(b - a for a, b in zip(times, times[1:])))
    print(f"    a call due at {call_share:.0%} of jobs, House stall {stall:.0f} s: COMPLETE {ok / N:.4f} "
          f"(literal rule {lit / N:.4f}); the largest gap seen {worst:.0f} s")

# (3) q(D) from the frozen share function (fix1/r2_spec.py, sha256 fd5c040e..., imported read only)
spec = importlib.util.spec_from_file_location("r2_spec", "/home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/fix1/r2_spec.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)
counts = [80, 95, 102, 88, 110]                 # invented qualifying-issuer counts of five complete sessions
print(f"\n(3) r2_spec.share: no complete session {R.share([])}; five complete sessions {counts} -> "
      f"q = {R.share(counts):.4f} (40 / {sum(counts) / len(counts):.1f})")
