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
    # THE TOP-UP RAISE's reader (Oct 10, 2026; the no-captain audit's item 2): the rule read again every hour at :35 and at
    # the House's start, written only when it raises a meter or sets a day's first figure (the full job when budget.json
    # is unusable: a deploy that changed the rule, a stale file). A top-up reaches research within the hour, not at the
    # next 00:30 run. A few seconds; in session like the grant; its grace outlasts the longest job's wall, so an
    # occurrence behind a long job waits and runs rather than being `missed`. In a pause too, like `budget`.
    Job("budget_refresh", "league.ops.budget_refresh", (S.at_start(), S.hourly(35)), grace=70 * MINUTE, cpu=300,
        wall=600, owner="no captain", in_pause=True,
        what="the research budget read again: a top-up raises today's figure, the knobs and the guard's caps within the "
             "hour (raise-only; the full job when budget.json is unusable)"),
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
        what="the stall alarm: births (and the architect's jam and yield), Gym runs, Validations, the guard's brake, the "
             "budget's runway, research under budget, the swarm's alerts, an owner deploy, a "
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
    # THE EQUITY LANE's daily store (release E1, Oct 2026; league/ops/equity_data.py): Alpaca SIP daily bars, raw and
    # adjustment=all, from 2016 through the gateway, audited, written atomically to <state>/equity-daily/. At the House's
    # start (after `direction`: the grant first) and daily at 22:30Z, past the close and its settling in both seasons. It
    # only reads the gateway and writes its own directory, so it runs in a pause too. About two dozen bar pages a run.
    Job("equity_data", "league.ops.equity_data", (S.at_start(), S.daily(22, 30)), grace=3 * HOUR, cpu=600, wall=1800,
        in_pause=True, owner="equity lane",
        what="the equity lane's daily store: SIP daily bars (raw and all) from 2016, audited (calendar, sane bars, splits, "
             "volumes, the 1Day bar's regular session), into <state>/equity-daily/"),
    # THE EQUITY TWINS (release E1; league/ops/twins.py `run`): each closed equity lot's replay twin in closed form from
    # the House's own official opens and closes (`eq_bars`), into the swarm store's kv `equity_twins`, final once judged.
    # Daily at 01:15Z and 40 minutes before each open (after the book's morning re-fetch of the bars at open - 60), each
    # before the `dlane` report that reads them; at the House's start too. Its one write is that measurement record (no
    # band, no order, no money), so it runs in a pause like the report.
    Job("equity_twins", "league.ops.twins", (S.at_start(), S.daily(1, 15), S.session_open(-40)), grace=3 * HOUR,
        cpu=120, wall=300, in_pause=True, owner="equity lane",
        what="each closed equity lot's replay twin (closed form, the engine's fill at the official open or close), the "
             "gap in bp a side and the same-risk buy-and-hold, into the swarm store's kv equity_twins"),
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
    # THE FORWARD RECORD (release E3, "record and measure"; league/ops/forward_db.py): six jobs that record clean
    # evidence and measure it. They move no money, gate nothing, show no generator anything and write no verdict; each
    # is skipped (a `skipped` receipt) while its switch is off (`elane.forward.mode`, `elane.contam.mode`). The five of
    # the record read the House's stores read-only and write only <state>/forward.sqlite, the fill minutes and the
    # report, so they run in a pause too: a forward day not recorded is lost for good. No wall is over an hour (the
    # grant's hourly grace waits behind the longest).
    # The registry, hourly at :25 (off the grant's :05, the stall alarm's :20 and :50, the refresh's :35 and the
    # engineer's :40) and at the House's start: a version's forward window opens at the first close after it was scored,
    # so it is registered within the hour. Seconds a run; idempotent (each row one transaction with its chain link).
    Job("forward_register", "league.ops.forward_register", (S.at_start(), S.hourly(25)), grace=70 * MINUTE, cpu=120,
        wall=300, in_pause=True, owner="E3 forward record",
        what="the forward registry: every equity version judged on the Train bar (passed or failed), each seed and live "
             "instance and the skill-free controls, hash-chained with its forward route and alpha; the tags learned "
             "later and the stop rules; into <state>/forward.sqlite"),
    # The send-minute 1Min bars, 45 minutes after each close (13:45 ET on a half day) and at the House's start (its
    # backfill fetches a missed day): two bar requests a session on the free SIP route.
    Job("fill_minutes", "league.ops.fill_minutes", (S.at_start(), S.session_close(45)), grace=3 * HOUR, cpu=120,
        wall=300, in_pause=True, owner="E3 forward record",
        what="the send-minute 1Min bars of the universe (the minutes after the open send and before the close) for the "
             "live-like price beside each official fill, into <state>/equity-fill-minutes/"),
    # The nightly recompute, after the daily store (22:30Z: about 18:35 ET until Nov 1, 17:35 ET after); the job itself
    # never runs inside 09:00-17:30 ET on a session. Its decider child is its own (never the live process's), inherits
    # this RLIMIT_CPU and the nice, and its preflight makes a child that cannot start a failed job, never a damaged
    # record. `cpu_seconds_night` (1,800 s of child time) is its own budget inside the 2,700.
    Job("forward_shadow", "league.ops.forward_shadow", (S.after("equity_data"),), grace=3 * HOUR, cpu=2700, wall=3300,
        in_pause=True, owner="E3 forward record",
        what="the forward shadow: every registered program recomputed whole on its own forward days in the job's own "
             "decider child, the controls beside them, checkpoints at 20, 60, 120 and 250 sessions, the live-like "
             "re-price and the live twins (recorded, never a verdict)"),
    # The day's meters and the report file, after the shadow and again 35 minutes before each open (the FW1 read: a
    # forward day owed and not recorded by 09:00 ET).
    Job("forward_report", "league.ops.forward_report", (S.after("forward_shadow"), S.session_open(-35)),
        grace=3 * HOUR, cpu=300, wall=600, in_pause=True, owner="E3 forward record",
        what="the forward record's meters (clean evidence-years, the replay multiple, the BH/BY meter, the group "
             "means) and its report with alarms FW1-FW8, into <state>/forward-report.json (operator-only)"),
    # The morning marks, 25 minutes before each open (after the book's re-fetch of the last decision's bars at open -
    # 60 and the twins at open - 40): a day whose bars the audit found different leaves the counted days; then the
    # registry's chain is read whole.
    Job("forward_audit", "league.ops.forward_audit", (S.session_open(-25),), grace=40 * MINUTE, cpu=120, wall=300,
        in_pause=True, owner="E3 forward record",
        what="the forward record's morning marks: a forward day whose bars the morning audit found different is marked "
             "(it leaves the counted days), and the registry's hash chain is verified"),
    # The contamination probe, Saturday 00:10Z (Friday evening in New York): the start of the UTC day, the equity
    # lanes' `usd_day` line still whole. One model route a run, at most `elane.contam.usd_run` dollars ($3), resumable
    # by its scored cells (every run's request keys are its own: none is asked twice), and paid, so never started twice
    # for one occurrence.
    Job("contam_probe", "league.ops.contam_probe", (S.weekly(5, 0, 10),), grace=6 * HOUR, cpu=300, wall=3300,
        paid=True, retry=False, owner="E3 contamination",
        what="the contamination probe: one model route a week asked what it recalls of the eras programs are judged "
             "on, scored on the House against a permutation by whole period; aggregates only, into "
             "<state>/contamination.json"),
    # THE PANEL LANE's data and measurement jobs (release E4, "breadth"; league/xs/E4_INTERFACES.md). WITH THE LANE'S
    # SWITCH OFF NONE OF THEM RUNS: each one's first statements are the switch (`league.ops.equity_universe.lane_off`:
    # `elane.panel.mode` "off" in the box's settings is a `skipped` receipt: no gateway call, no file) and
    # `league.xs.config.quiet(now, its own wall)`: a start that could still be working at a wall of the session
    # (09:25-09:45 and 15:50-16:35 ET) is a `skipped` receipt too, and the occurrence is not lost (it runs at its next
    # daily time). They read the gateway and write their own files under <state>/equity-daily/, so they run in a pause
    # too. They go last: at a House start every older job that is due at the same instant goes first.
    # NO AT-START TRIGGER (the review's live-9): at a House start before an open the chain's whole fetch (55 minutes of
    # wall) held the one ops child past the pre-open's grace. `equity_panel` HAS ITS OWN DAILY TIME (the review's
    # live-4), fifteen minutes after the universe job's (one child at a time: it starts when that one has ended): its
    # only trigger was `after("equity_universe")`, so a night the universe job failed fetched no bars, ran no I6, and
    # raised none of the panel job's own alarms. It now runs every night on the last good universe.
    Job("equity_universe", "league.ops.equity_universe", (S.daily(1, 40),), grace=3 * HOUR, cpu=120,
        wall=900, in_pause=True, owner="breadth",
        what="the point-in-time S&P 500 membership from a pinned public file and the changes table (the gateway's "
             "reader), the assets and their aids, the audit, into <state>/equity-daily/universe/ (counts only out)"),
    Job("equity_panel", "league.ops.equity_panel", (S.daily(1, 55),), grace=3 * HOUR, cpu=600, wall=3300,
        in_pause=True, owner="breadth",
        what="the panel's daily bars through the venue's asof (never 2020), the store's vintage rule, the coverage "
             "audit and its verdict, the nightly I6, into <state>/equity-daily/panel/"),
    Job("equity_spreads", "league.ops.equity_spreads", (S.daily(6, 30),), grace=6 * HOUR, cpu=300, wall=3000,
        in_pause=True, owner="breadth",
        what="the panel's half-spreads: quote samples at the instants the book trades, on Train-segment sessions, "
             "resumable, into <state>/equity-daily/spreads.json"),
    Job("equity_neff", "league.ops.equity_neff", (S.monthly_first(5, 10, 0),), grace=6 * HOUR, cpu=600, wall=900,
        in_pause=True, owner="breadth",
        what="the panel's independent names (N_eff on Train segment 2) into <state>/equity-daily/neff.json"),
    Job("french", "league.ops.french", (S.monthly_first(5, 11, 0),), grace=6 * HOUR, cpu=60, wall=300,
        in_pause=True, owner="breadth",
        what="the French library's daily factors where a route to them exists (none today: a skipped receipt)"),
    Job("xs_zero_edge", "league.ops.xs_zero_edge",
        (S.weekly(6, 6, 0), S.weekly(6, 8, 0), S.weekly(6, 10, 0), S.weekly(6, 12, 0)), grace=100 * MINUTE, cpu=2400,
        wall=3000, in_pause=True, owner="breadth",
        what="the panel Train bar's zero-edge expected column: seeded random-score programs through the whole bar, "
             "25 a run, into the swarm store's kv elane_xs_zero_edge"),
)


def by_name(jobs: Sequence[Job] = JOBS) -> dict[str, Job]:
    return {job.name: job for job in jobs}
