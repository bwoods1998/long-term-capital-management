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
        what="the research budget from trailing realized profit; funding notices"),
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
        what="the public-safe daily scoreboard, committed through the gateway"),
    # Twice: 15:00Z runs the drills and requests the rollback drill last (the updater launches it); 17:00Z checks its verdict (and runs any drill
    # the first could not reach). A drill done this month is never run again (`league/ops/drills.py`).
    Job("drills", "league.ops.drills", (S.monthly_first(5, 15, 0), S.monthly_first(5, 17, 0)), grace=6 * HOUR, cpu=1800, wall=3600, owner="WP1/WP3",
        what="the monthly failure drills, each with a recovery check", retry=False),
    Job("postmortem", "league.ops.postmortem", (S.weekly(5, 14, 0),), grace=6 * HOUR, cpu=900, wall=1800, owner="Phase 5",
        paid=True, what="the weekly post-mortem"),
    Job("agenda", "league.ops.agenda", (S.daily(3, 0),), grace=6 * HOUR, cpu=900, wall=1800, owner="Phase 2",
        paid=True, what="the strategist's daily agenda"),
    Job("engineer", "league.ops.engineer", (S.daily(4, 0),), grace=6 * HOUR, cpu=1800, wall=3600, owner="Phase 4",
        paid=True, what="the engineer's daily harness change", retry=False),
)


def by_name(jobs: Sequence[Job] = JOBS) -> dict[str, Job]:
    return {job.name: job for job in jobs}
