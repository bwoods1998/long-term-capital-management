"""The House's jobs: what each one is, when it is due, how long it may wait to start, and what it may cost.

Each job is a module with `run(ctx) -> dict` (`league/ops/context.py` is the `ctx`). Modules owned by other work
packages are imported lazily by name and may be absent: a due job whose module is not in the running release writes a
`skipped` receipt that says so, never an error. The times are chosen outside every US session in both seasons, except
`preopen` (an hour before the open) and `economics` (ten minutes after the close), which follow the session itself.

`grace` is how long after it is due a job may still START; past it, the occurrence is `missed` (a receipt row and a
House warning). `cpu` and `wall` bound the child: `RLIMIT_CPU` and a kill after `wall` seconds of wall time. A run that
fails is started again inside its grace (`store.retry_state`) unless `retry` is False: a job that must not be repeated
after it may have done part of its work (the drills restart the House and roll a release back; the engineer opens a
pull request).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from . import schedule as S
from .schedule import Trigger

HOUR = 3600
MINUTE = 60


@dataclass(frozen=True)
class Job:
    name: str
    module: str
    triggers: tuple[Trigger, ...]
    grace: float
    cpu: int = 600
    wall: int = 900
    owner: str = "WP2"
    what: str = ""
    #: Runs while the House is in a maintenance PAUSE (or has stopped buying work). A job that changes the House's
    #: records, posts in public or spends (hygiene, the grant, the scoreboard, drills, the paid roles) does not: it gets
    #: a `skipped` receipt naming the pause, and the next occurrence after the pause runs.
    in_pause: bool = False
    #: Spends Claude or Sail money: also skipped while the House has stopped buying work (`stopped_because`).
    paid: bool = False
    #: May a failed run be started again inside its grace (`store.retry_state`)? Not for jobs whose repeat would act twice.
    retry: bool = True


JOBS: tuple[Job, ...] = (
    # The grant's grace outlasts the longest job's wall (an hour: drills, engineer) from five minutes after it began: one
    # child runs at a time, so an hourly occurrence behind a long job waits and runs, never `missed`.
    Job("grant", "league.ops.grant", (S.at_start(), S.hourly(5)), grace=70 * MINUTE, cpu=120, wall=300, owner="WP4",
        what="the standing grant: re-ratify after an owner deploy that moved the money digest, or a deposit"),
    Job("budget", "league.ops.budget", (S.after("economics"), S.daily(0, 30)), grace=3 * HOUR, cpu=300, wall=600,
        owner="WP3", in_pause=True,
        what="the research budget (the owner's ceiling, each meter's runway); funding notices"),
    Job("hygiene", "league.ops.hygiene", (S.daily(2, 0),), grace=3 * HOUR, cpu=600, wall=1200,
        what="end barred practice cohorts, retire dead pool rows and idle families, report stale live instances"),
    Job("clock", "league.ops.clock", (S.daily(11, 0),), grace=2 * HOUR, cpu=120, wall=300,
        in_pause=True,
        what="the venue's clock and calendar against the House's session calendar"),
    Job("preopen", "league.ops.preopen", (S.session_open(-60),), grace=40 * MINUTE, cpu=300, wall=600,
        in_pause=True,
        what="the nine pre-open checks; a FAIL is a House warning"),
    Job("economics", "league.ops.economics", (S.session_close(10),), grace=3 * HOUR, cpu=900, wall=1800,
        in_pause=True,
        what="the one-cutoff close economics and the trailing 30-day realized options P&L"),
    Job("scoreboard", "league.ops.scoreboard", (S.daily(23, 30),), grace=2 * HOUR, cpu=120, wall=300,
        what="the public-safe daily scoreboard and its funnel, committed through the gateway"),
    # Every half hour, round the clock (the owner's goal of Oct 7, 2026, item 6), at :20 and :50, off the grant's :05 and
    # the engineer's :40. Read-only and a few seconds: it runs in session like the grant, and its grace outlasts the
    # longest job's wall, so an occurrence behind a long job waits and runs rather than being `missed`. It runs in a
    # maintenance pause too (read-only, like preopen and clock), so a pause left on is itself an owner step it reports.
    Job("stall", "league.ops.stall", (S.hourly(20), S.hourly(50)), grace=70 * MINUTE, cpu=120, wall=300, owner="self-running",
        in_pause=True,
        what="the stall alarm: births, Gym runs, Validations, the guard's brake, the budget's runway, an owner deploy, a "
             "pause, a refused grant or the kill switch waiting; one stall notice listing them all, an owner step's at "
             "once and every 12 h, the rest every 24 h"),
    # Twice: 15:00Z runs the drills and requests the rollback drill last (the updater launches it); 17:00Z checks its verdict (and runs any drill
    # the first could not reach). A drill done this month is never run again (`league/ops/drills.py`).
    Job("drills", "league.ops.drills", (S.monthly_first(5, 15, 0), S.monthly_first(5, 17, 0)), grace=6 * HOUR, cpu=1800, wall=3600, owner="WP1/WP3",
        what="the monthly failure drills, each with a recovery check", retry=False),
    Job("postmortem", "league.ops.postmortem", (S.weekly(5, 14, 0),), grace=6 * HOUR, cpu=900, wall=1800, owner="Phase 5",
        paid=True, what="the weekly post-mortem"),
    Job("agenda", "league.ops.agenda", (S.daily(3, 0),), grace=6 * HOUR, cpu=900, wall=1800, owner="Phase 2",
        paid=True, what="the strategist's daily agenda"),
    # Authoring at 04:00Z (after the scoreboard); every hour at :40 the candidate in flight moves on (CI, the review, the
    # merge, the deploy, the canary, the decision, a revert) without waiting a day per step.
    Job("engineer", "league.ops.engineer", (S.daily(4, 0), S.hourly(40)), grace=50 * MINUTE, cpu=1800, wall=3000,
        owner="Phase 4", paid=True, what="the engineer's harness change: author daily, move the candidate along hourly",
        retry=False),
    # At a House start the grant goes first (occurrences due at the same instant start in this order, `runner.due`).
    Job("direction", "league.ops.direction", (S.at_start(), S.daily(1, 0)), grace=3 * HOUR, cpu=120, wall=600,
        in_pause=True, owner="fast lane v2",
        what="the roots' daily closes for the same-risk buy-and-hold beside each screen result and band row (reported, "
             "never a bar)"),
    Job("fast_lane", "league.ops.fast_lane", (S.after("direction"),), grace=3 * HOUR, cpu=600, wall=1200,
        in_pause=True, owner="fast lane v2",
        what="the fast lane's report (read-only): the buy-and-hold and the drift fit beside each screen result and band "
             "row, the contamination measures, D5 and the Probe budget, into <state>/fast-lane-report.json"),
    # THE LEARNING GAME (Oct 8, 2026): the operator's daily report at 00:00Z, read-only like the fast lane's; it runs in a
    # pause too (the day-1 plumbing read must not wait for one).
    Job("game", "league.ops.game_report", (S.daily(0, 0),), grace=3 * HOUR, cpu=600, wall=1200, in_pause=True,
        owner="learning game",
        what="the learning game's report (read-only, operator-only): R1-R6 of its measurement plan and the pre-registered "
             "decisions, into <state>/game/report-<day>.json"),
    # THE DIRECTION LANE (release D-1, Oct 9, 2026): the operator's daily report at the House's start and 01:30Z, after the
    # `direction` closes (01:00Z) and the fast lane's report it reads; read-only like theirs but for K5's kv (the trip,
    # `dlane_k5`, and the operator's clear recorded, `dlane_k5_base`), so it runs in a pause too. With `dlane.mode` "off" it
    # writes no report (a `skipped` receipt), and still holds the program loss line (DONE-RULE-A1 A1.3: `lane_off`).
    # Since the review of the weekend fixes (Oct 10, 2026) also 30 minutes before each open: a Probe position held to its
    # expiry is priced by the House's overnight reconciliation (pid 14's at 01:11Z Oct 8; from Nov 1 the same New York
    # hour is past 01:30Z), so a program that an expiry reconciled overnight carried past the program loss line is retired
    # before the next session rather than after it. About 30 seconds a run (Oct 9's receipts).
    Job("dlane", "league.ops.dlane_report", (S.at_start(), S.daily(1, 30), S.session_open(-30)), grace=3 * HOUR,
        cpu=600, wall=1200, in_pause=True, owner="direction lane",
        what="the direction lane's report (operator-only): the funnel per lane, the Probe envelope, the DONE meter of the "
             "pinned rule (done_screen, done_all) beside the same-risk buy-and-hold, alarms A1-A9, PL1 and K5, into "
             "<state>/dlane-report.json; the program loss line (A1.3), the lane off too"),
)


def by_name(jobs: Sequence[Job] = JOBS) -> dict[str, Job]:
    return {job.name: job for job in jobs}
