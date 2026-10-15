"""The `forward_report` job: the forward record's daily meters, its report file, its funnel counts and its alarms.

Owner: C (league/ops/E3_INTERFACES.md). Protected (release E3). After the forward shadow and 35 minutes before each
open; in a pause too. It writes `fwd_cey`, `fwd_meter` and `fwd_groups` of `<state>/forward.sqlite`
(league/ops/forward_db.py; first write stands a day) and `<state>/forward-report.json` (0600, atomic:
`context.write_json`). Operator only: nothing here reaches a generator, the scoreboard or the website.

THE METERS (`meters`; arithmetic in league/ops/forward_stats.py), for every forward day up to the last `fwd_runs`
`through` with no `fwd_cey` row, in order:
- N_eff AND CEY (D6). Day d; W = the last `NEFF_WINDOW` forward days up to d. A lineage's representative is its lowest
  pid whose reason is train_pass, seed or live, else its lowest pid; controls are excluded; above `neff_max_members`,
  those with the smallest `sha256("neff-1|" + key)` are kept (`representatives`). A member is a representative whose
  counted days inside W form an unbroken run of at least `NEFF_MIN_DAYS` sessions ending at d, with non-zero variance
  of x (`population`). cey_day(d) = N_eff(d) / 252; CEY(D) = the sum of cey_day over forward days d <= D;
  "provisional" while n_w < `NEFF_PROVISIONAL`; `median20` = the median cey_day of the last 20 forward days.
- THE REPLAY MULTIPLE (D7). `sim_py(D)` = (the sum, over swarm `runs` rows of equity-lane families (structure "etf" or
  "stock") with status not in `funnel.NOT_RUN` and trials > 0, of `json_extract(summary, '$.days') * trials`, plus the
  count of `fwd_days` rows of non-control pids, any engine, with day <= D) / 252 (`sim_program_years`). `hist_iy` = the
  history's independent years over 2016 through `config.LOOK_CAP`'s year, on the as-of close-to-close returns of the
  registered non-control NEEDS symbols (`elane.cfg(settings)["universe"]` when none) that have a bar on each session
  (`hist_independent_years`; prices only, read with the capability `GATE_REASON`; a `MissingData` leaves it and the
  multiple None that day). replay_multiple(D) = sim_py(D) / (hist_iy + CEY(D)). House only.
- THE BH/BY "ANY EDGE ANYWHERE" METER (D8). One p a lineage: the `p_x` of its representative's latest checkpoint (the
  largest n, a final one included) under the NEWEST engine that pid has a checkpoint for; a lineage with no
  checkpoint is outside it. The same over every control with a checkpoint, on its `p_x0` (the cost-free excess),
  gives `controls_bh`, `controls_by` and `controls_p10`. Reading: "none yet" while BY = 0; "unreliable" beside it
  while `controls_by` > 0.
- RC RECORDING AND READS (D9). Each forward day, for grp in {train_pass, train_fail (registry reasons), look_pass,
  look_fail (tags), seed, control:<g>}: n, `mean_x`, `mean_r`, `mean_w`, `mean_x0` (control groups) and `ugroups`. A
  pid is in a tag group on day d iff the tag's `at` is before `schedule.moments(d).close_at`. THE PAIRS: (look_pass,
  look_fail), (train_pass, train_fail), and each of those four against THE POOLED CONTROLS of that day (the unweighted
  mean of `mean_x0` of control:<g> over the base groups its `ugroups` name). A session is USABLE for a pair when both
  sides have n >= `RC_MIN_GROUP`; a pair's k-th read is taken the night of its `RC_READS[k]`-th usable session, over
  exactly those sessions (`rc_pairs`). NO DIFFERENCE IS COMPUTED OR SHOWN BEFORE A PAIR'S READ.

READINGS THE SPEC LEFT OPEN, each fixed here and held by a test:
- AS OF THE DAY. A day's meters read the registry as it stood: a row counts from its `first_day` (a representative,
  a NEEDS symbol of hist_iy), a checkpoint from its own `day`, so a day written late reads what its own night would
  have. The swarm's `runs` rows carry no forward day: sim_py reads every one present when the row is first written.
- THE ENGINE. A day's counted rows are the newest engine's (`forward_db.engine_now`): the night a label moves, every
  active program's history is written again under the new id.
- A CHECKPOINT WITH NO p (a program that never traded has no t) stays in D8's family with p = 1: it was tested and
  showed nothing, and the family's size is the number of lineages tested, not the number that traded. `min_p` is the
  smallest p a lineage does have. It stays in the store and is never in the report (one program's figure).
- A GROUP'S ROW is written every forward day, n 0 and its means NULL when no pid of it has a counted row.

A DAY'S METERS WAIT FOR ITS ROWS (`_awaited`; the review's fix). A day's rows are first-write and never recomputed,
and a night the budget cut, or one a vendor bar came late to, leaves programs without their row for the day until
the next night's whole recompute fills it. Written the night itself, the day's N_eff and CEY (the goal's measure of
compounding) and its RC group counts would be short of those programs for good. So a day is written once no active
registered program that was owed it (its `first_day` on or before the day, held by the registry at the day's close)
is still AWAITED for its row under the newest engine, or once `METER_WAIT_NIGHTS` later nights have run, whichever
comes first; in the second case it is written as it stands and one `meter_partial` event (once a day; the count of
the rows still awaited) marks it. The days after a waiting day wait behind it (CEY is a running sum). FW5
reads no partial day: neither in its run of days nor in its medians.
ONLY AN ABSENCE THE NEXT NIGHTS CAN FILL IS AWAITED (the verification's fix). Awaited without end, ONE program that
never gets a row again (a holder of a halted symbol, the shadow's STATED LIMIT; a program that hangs every night)
made every later day's meters `METER_WAIT_NIGHTS` sessions late and partial for good, and FW5, which reads no
partial day, read nothing from then on. So a program without its row for a day is awaited when its absence began
that day (it has its row, under any engine, for the session before, which it was owed too), whatever the cause; or
when it has been without one for fewer than `METER_WAIT_NIGHTS` owed sessions running and is neither suspect
(`forward_db.suspect`) nor behind in the shadow's queue (`_behind`: its last attempt failed twice in the child). A
STANDING absentee is so awaited at the start of its absence (its first day, or its first `METER_WAIT_NIGHTS` - 1)
and never again: the days after are written the night itself, are no partial days, and FW5 reads them. FW2 goes on
telling a program that fails night after night. The price, stated: when such an absentee RETURNS, the days it missed
keep meters written without its row and carry no mark (a mark would need an event kind of its own); its rows are in
`fwd_days` for whoever reads the record itself. A CONTROL is made in the job's own process and no budget leaves one
stale: one without its row is awaited, by the same rule, only when its data failed (a `data_failed` event of its
own for that night or a later one). A night whose deadline deferred the controls left every due program stale too,
and the day waits for those.

THE METER'S FLOOR (`METER_MIN`; the review's fix). BH and BY over one or two lineages are a verdict on a program
(with one lineage, BH is 1 exactly when that lineage's p is at or under q), and no program without a "live" tag has
its forward verdict shown to anyone. The store keeps the whole row; the report and the funnel show `m` always and
the counts and the reading only once the family holds `METER_MIN` lineages (the controls' side once it holds as many
controls): under it the report's `bh`, `by_` and `unreliable` are None with the reading "too few lineages to read",
and the funnel's `bh` and `by` are 0.

THE REPORT (`section`, written to `FILE`; read by the dlane report through `read_section`): `SECTION_KEYS`. Forward
rows reach only this file, the dlane report's `forward_record` section and `forward_twins.a14_reading`: no
per-program forward figure for a pid without a "live" tag, no RC difference before a pair's read, no figure of the
sealed memory tables (counts only). There is no running A14: A14 is read only at a Done checkpoint, by the Done
meter, over its own counted closes. A part of the report that cannot be read is {"error": <the exception's name>},
never a zero, and the rest is written.

WHEN THE REPORT IS STALE (`read_section`, `alarms`): older than `STALE_HOURS` AND a run of this job fell due after it
was written and is `DUE_GRACE_HOURS` overdue (the job is due 35 minutes before each open: `DUE_BEFORE_OPEN_MINUTES`).
A Friday night's report read on a Sunday is two days old and not stale: no run was due.

THE FUNNEL (`funnel_rows`, read by league/ops/funnel.py `window` as `forward_record`): INTEGERS ONLY (`FUNNEL_KEYS`).

THE ALARMS (`alarms`; `ALARMS`: id -> level). Each row is {"id", "level": "info" | "warning", "text", "new"}; the
dlane report carries them and each warning is also a `ctx.alert` of the job that finds it. EVERY TEXT HOLDS IDS, COUNTS
AND DATES ONLY: no decimal figure, no "bp", no "%", no return, no dollar figure (`text_ok`). Each alarm is read on
its own: one that cannot be read (a store locked that minute) is an info row under its id that says so, never
silence and never the loss of the others.
EACH ALARM FOLLOWS ITS OWN SWITCH (`raised`; the review's fix: the first build silenced all thirteen with the forward
mode). With `elane.forward.mode` off none of FW1-FW9 is raised and no forward part of the report is read; with
`elane.contam.mode` off neither CP1 nor CP2 is (a route nobody probes any more is not "unprobed"); RR1, RR2 and MM1
have no switch: the release receipts have none, and a memory alert is the swarm's own failure, which the memory mode
does not reach (a family born with a hidden year keeps its seen spans whatever the mode). So with the forward record
rolled back the job still writes `FILE` ({"at", "mode": "off", "memory", "contamination", "receipts", "alarms"}),
still raises RR, CP and MM, and `alarms` still hands them to the dlane report.
- FW1 (warning): the mode is "record" AND (no `fwd_days` row by 09:00 ET the next session for the last closed forward
  day on which at least one active registry row had `first_day` <= that day, OR the report is stale): a stalled job.
  Silent on an empty registry, on the sessions before a first registration's `first_day`, and while the mode is off.
  THE QUESTION IS SETTLED AT THIS JOB'S MORNING RUN, 35 minutes before the open (08:55): the forward shadow starts no
  program within 300 s of 09:00 (`FW1_SETTLED_S`) and an after-trigger never fires for a shadow that failed, so the
  morning run is the first to see a night that wrote nothing and says so before the open (read from 09:00 on, it
  would be told a day late). "Had" is read as of that day: a row counts when the registry held it by that day's close
  (one registered later was owed no row that night; the next night's whole recompute fills its days).
- FW2 (warning): programs left stale two nights running, or a pid with a `data_failed` or a `run_failed` event on two
  nights running (counts in the text).
- FW3 (warning, or info): a `restated` event written last night (written once a value, so this is its first night).
  The text counts the restatements by cause, as the event's bars hash tells it (league/ops/E3_INTERFACES.md, fact 1):
  those whose decisions read bars that have moved since (the vendor's: a correction, or adjusted prices rounded to
  cents) and those that read the same bars (the recompute itself is not deterministic). ITS LEVEL IS ITS CAUSE
  (`_restated`; decided at the integration, on the shadow's measurement): the vendor restates a symbol's whole
  adjusted history at every dividend and split, so an ex-day of a held symbol restates nearly every stored day of
  every holder, most weeks; that is data, counted with its cause, and reads "info" (listed, never mailed). It is a
  "warning" when any restatement read THE SAME bars, or is a program's that cannot say which it read (no bars hash):
  the recompute itself moved, which nothing but a defect explains. A control's restatement carries no bars hash by
  construction (it reads no bar: `bars` "none") and is the vendor's too.
- FW4 (warning): `verify_chain` not ok (owner step: stop the forward jobs and compare with the backup).
- FW5 (warning): cey_day under its 20-day median for 10 forward days running while equity births continue.
- FW6 (warning): a live instance with 5 or more priced closes whose mean twin gap is beyond the A14 bound either
  way, or with 20 or more sessions under the A14 agreement bound (before any checkpoint); the text names the instance
  and the counts, no figure. A session whose intents differ counts against the bound whatever its cause (A14's rule is
  not changed by it); the text says how many of them read other bars (the bars hash: a disagreement is data).
- FW7 (warning): while `eq_instances` holds a live row: the live book's kv `eq_decide` for the last session is status
  "failed", or status "done" with no `why` and `at` later than that session's `close_at` + 2,400 s while an instance
  the record names (every living one when it names none) was in the book by then: a catch-up decide with nobody
  seated, whose record the seating pass wrote again without its `why`, kept nobody waiting.
- FW8 (warning): the equity fingerprint moved while a lineage is live (`identity_moved`).
- FW9 (warning; the rehearsal of Oct 15, 2026): THE ETF LANE'S TWINS FROM THE FIRST SESSION, as FX1 and FX2 are the
  panel lane's. FW6 reads an instance's agreement from 20 sessions, and the first Done checkpoint comes sooner; a
  missing row it never read. So:
  (a) A LIVING ETF INSTANCE WITH A SESSION THAT HAS NO `fwd_twins` ROW (`_twin_gaps`). The sessions read run from its
  first row (its first decision session, `forward_twins.d_first`, while it has none) through the session before the
  last E3 night's `through`: that night writes the row of that session. The sessions of a retirement it came back
  from (its `twin_retired` day to its next `twin_revived` day) are left out. One row an instance. The text counts
  the sessions, names the first missing one, and names the latest twin event of it (interrupted, run sha mismatch,
  unregistered). It catches every cause: a twin run interrupted, deferred, refused for its run sha or its key, one
  that raised, a re-based twin that raised. A14 counts each such session as not agreed, and no Done checkpoint is
  final while one is missing. A panel instance is FX1's. An instance with no registry row is read here: no twin is
  made for it in either lane. Silent while `elane.forward.twins` is false (no row is made).
  (b) EACH `fwd_twins` ROW OF AN ETF INSTANCE WITH `agree` 0 (`_twin_disagreed`), told once with its cause (the rows
  written since the report before, as FX2), from the first session. A disagreement is data: the text says so.
- RR1 (warning): a declared release receipt unread 24 h after its window closed; RR2 (info): a receipt read "flat"
  or "wrong_way" (listed for `RR2_DAYS` days, never reverted).
- CP1 (info): a route unprobed for 45 days, or a readable 2025 or 2026H1 cell newly "recalled"; CP2 (warning): a route
  whose last three attempts added no cell. THE ROUTES CP1 READS are the swarm's configured ones
  (`elane_yield.cfg(settings)["routes"]`) and every route the probe's file holds, and its 45 days count from the
  route's last COMPLETED probe; for a route with none, from the earliest of its first attempt (the file's
  `first_attempted_at`, which the probe writes once and never moves) and the first report that saw it configured
  (`contamination.first_seen`, carried from report to report). Read off the file's rows by their last attempt, a
  route whose probe never finishes restarted its clock every Saturday and a route with no row was never read: a
  probe that cannot answer from the ops child was told by nothing.
- MM1 (warning): a `swarm.status` "elane_memory" alert in the last 24 h.
FW8 and MM1 read back to the report before this one when that is longer than 24 h (never past `LOOKBACK_DAYS`): the
job does not run between a Friday night and a Monday morning, and what happened then is still told once.
- FX1, FX2, FX3 (warning; RELEASE E4, package J: league/ops/forward_xs.py `alarms`, `ALARMS`): the panel lane's twin
  marker behind its store, a REBALANCE session of a live panel program whose live and twin orders disagree, and
  panel programs left stale two panel nights running. They follow two switches (`elane.forward.mode` and
  `elane.panel.mode`); `ALARMS` here is release E3's own list.

RELEASE E4 (package J), WHAT ELSE READS A PANEL PROGRAM HERE. Its rows are E3's rows (x = r - w * b is its residual
against its matched cells), so D6 to D8 read it as any lineage. D9 keeps it APART: a panel pid stands in the groups
"xs:train_pass", "xs:train_fail", "xs:look_pass" and "xs:look_fail" (written from the first day a panel row is
registered), never in an ETF group, and no RC pair reads them (no panel control exists). The replay multiple's
numerator counts a panel family's Train runs; its denominator does not hold the panel's independent history (the
multiple overstates: stated). A NIGHT here (`_nights`: FW2, FW3's start, the funnel's `stale`) is one of this
release's own job; the panel lane's nights (their own job and their own day: a panel row is final a session after
an ETF row) are FX3's. So once a panel program is registered a day's meters wait for its panel rows (A DAY'S
METERS WAIT FOR ITS ROWS, above): they are written at the morning run after the panel night that holds them, the
second morning after the day, and are not partial for that cause.

Standard library and numpy only (numpy inside the functions that read arrays).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import forward_db, forward_stats, guard
from . import schedule as S
from .context import read_json, write_json

FILE = "forward-report.json"
#: The reason the job mints its `EquityGateCapability` with (D7's hist_iy reads prices up to the look cap).
GATE_REASON = "forward-report"
#: The report file is stale past this many hours (`read_section` then gives None and `alarms` one FW1 row), once a
#: run of the job fell due after it was written (the module docstring).
STALE_HOURS = 36.0
#: The job's calendar trigger (league/ops/registry.py: `S.session_open(-35)`) and its grace.
DUE_BEFORE_OPEN_MINUTES = 35
DUE_GRACE_HOURS = 3.0
#: The report's top-level keys (`section`).
SECTION_KEYS = ("at", "mode", "t0", "through", "engine", "registry", "shadow", "checkpoints", "meter", "cey", "fills",
                "rc", "memory", "contamination", "receipts", "alarms")
#: The report's keys while the forward record is off (`run`): no forward part.
OFF_KEYS = ("at", "mode", "memory", "contamination", "receipts", "alarms")
#: `funnel_rows`' keys, every value an integer (never a figure).
FUNNEL_KEYS = ("registered", "registered_total", "lineages", "controls", "program_sessions", "program_sessions_total",
               "stale", "errors", "checkpoints", "bh", "by", "oof_seen", "oof_rows")
#: The alarms: id -> level (the module docstring).
ALARMS: dict[str, str] = {"FW1": "warning", "FW2": "warning", "FW3": "warning", "FW4": "warning", "FW5": "warning",
                          "FW6": "warning", "FW7": "warning", "FW8": "warning", "FW9": "warning", "RR1": "warning",
                          "RR2": "info", "CP1": "info", "CP2": "warning", "MM1": "warning"}
#: The RC pairs among the program groups (D9); each of the four groups is also read against the pooled controls.
RC_PAIRS = (("look_pass", "look_fail"), ("train_pass", "train_fail"))
#: The pooled controls' name as a pair's second side (`rc_pairs`).
RC_CONTROLS = "controls"
#: D9's program groups: registry reasons, then tags.
GROUP_REASONS = ("train_pass", "train_fail", "seed")
GROUP_TAGS = ("look_pass", "look_fail")
#: The reasons a lineage's representative is first taken from (D6).
REPRESENTATIVE_REASONS = ("train_pass", "seed", "live")
#: FW1's deadline: 09:00 New York, this many seconds before the next session's open; and how long before it the
#: question is settled (the forward shadow starts no program within these seconds of 09:00, its `OPEN_MARGIN_SECONDS`:
#: this job's morning run, `DUE_BEFORE_OPEN_MINUTES` before the open, is the first moment that reads it).
FW1_BEFORE_OPEN_S = 1800
FW1_SETTLED_S = 300
#: FW5: cey_day under the median of the last `MEDIAN_DAYS` forward days for this many forward days running.
FW5_DAYS = 10
MEDIAN_DAYS = 20
#: FW6: the fewest priced closes, and the fewest readable sessions, an instance is read on.
FW6_CLOSES = 5
FW6_SESSIONS = 20
#: FW7: a decide later than this many seconds after its session's close is late (16:40 New York).
FW7_LATE_S = 2400
#: FW9: the twin events that say why an instance's twin row was not made; a missing row's text names the latest.
FW9_EVENTS = ("twin_interrupted", "twin_sha_mismatch", "twin_unregistered")
#: CP1: a route with no completed probe for this many days; the eras whose recalled cells it names; CP2: idle attempts.
CP1_DAYS = 45
CP1_ERAS = ("2025", "2026H1")
CP2_IDLE = 3
#: RR2 lists a receipt read "flat" or "wrong_way" for this many days after its read.
RR2_DAYS = 7
#: A DAY'S METERS WAIT FOR ITS ROWS: at most this many later nights (it is then written as it stands, marked partial).
METER_WAIT_NIGHTS = 3
#: THE METER'S FLOOR: BH, BY and the reading are shown once the family holds this many lineages (D9's own floor).
METER_MIN = forward_db.RC_MIN_GROUP
#: The reading under the floor.
METER_UNREAD = "too few lineages to read"
#: MM1 and FW8 read the last 24 hours, or back to the report before this one, never past this many days.
RECENT_HOURS = 24.0
LOOKBACK_DAYS = 7
#: What no alarm text and no alert of an E3 job may hold (T8): a decimal figure, "bp", a percent or a dollar sign.
_FIGURE = re.compile(r"\d[.,]\d|\bbp\b|%|\$", re.IGNORECASE)


# ------------------------------------------------------------------------------------------------------------ settings
def _cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`forward_db.cfg`, or its code defaults (mode "off") when the settings cannot be read."""
    try:
        return dict(forward_db.cfg(settings))
    except Exception:  # noqa: BLE001 - an unreadable block is "off"
        return dict(forward_db.DEFAULTS)


def _mode(settings: Mapping[str, Any] | None) -> str:
    value = _cfg(settings).get("mode")
    return value if value in forward_db.MODES else "off"


def _settings(root: Path, settings: Mapping[str, Any] | None, config: Any = None) -> Mapping[str, Any] | None:
    """The swarm's settings as it loads them when none were handed in (None when they cannot be read: "off")."""
    if settings is not None:
        return settings
    try:
        from ..swarm import settings as settings_mod

        return settings_mod.load(root, config=config if isinstance(config, Mapping) else None)
    except Exception:  # noqa: BLE001
        return None


def _probing(settings: Mapping[str, Any] | None) -> bool:
    """Whether the contamination probe is on (`elane.contam.mode`): CP1 and CP2's switch."""
    from . import contam_probe

    return contam_probe.mode(settings) != "off"


def raised(alarm: Any, settings: Mapping[str, Any] | None) -> bool:
    """EACH ALARM FOLLOWS ITS OWN SWITCH (the module docstring): FW1-FW9 the forward mode, CP1 and CP2 the probe's;
    RR1, RR2 and MM1 have none."""
    group = str(alarm)[:2]
    if group == "FW":
        return _mode(settings) != "off"
    if group == "FX":   # RELEASE E4 (package J): the panel twin's alarms (league/ops/forward_xs.py `ALARMS`)
        from . import forward_xs

        return forward_xs.raised(alarm, settings)
    if group == "CP":
        return _probing(settings)
    return str(alarm) in ALARMS


def text_ok(text: Any) -> bool:
    """Whether an alarm or alert text holds ids, counts and dates only (T8): no decimal figure, no "bp", no percent
    sign, no dollar sign. What every E3 job's alert is held to (league/tests/test_forward_report.py)."""
    return isinstance(text, str) and bool(text) and _FIGURE.search(text) is None


# -------------------------------------------------------------------------------------------------------- the calendar
def _iso_day(value: Any) -> str:
    return value.isoformat() if isinstance(value, dt.date) else str(value)[:10]


def forward_days(first: Any, last: Any) -> list[str]:
    """The sessions d with first <= d <= last, as ISO days (league/equity/schedule.py's calendar)."""
    from ..equity import schedule as ES

    day, end = dt.date.fromisoformat(_iso_day(first)), dt.date.fromisoformat(_iso_day(last))
    out = []
    while day <= end:
        if ES.is_session(day):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def _window(day: str, size: int) -> list[str]:
    """The last `size` forward days up to `day` (D1: none before `forward_db.t0()`)."""
    return forward_days(forward_db.t0(), day)[-int(size):]


def _close_at(day: str) -> float | None:
    from ..equity import schedule as ES

    moments = ES.moments(day)
    return None if moments is None else float(moments.close_at)


def _last_due(now: float) -> float | None:
    """The latest instant this job fell due on its calendar trigger and is `DUE_GRACE_HOURS` overdue; None when the
    calendar names none in its horizon."""
    from ..equity import schedule as ES

    day = ES.ny_day(now)
    for _ in range(ES.HORIZON_DAYS + 1):
        moments = ES.moments(day)
        if moments is not None:
            due = float(moments.open_at) - 60.0 * DUE_BEFORE_OPEN_MINUTES
            if due + DUE_GRACE_HOURS * 3600.0 <= now:
                return due
        day -= dt.timedelta(days=1)
    return None


def _stale(at: float | None, now: float) -> bool:
    """WHEN THE REPORT IS STALE (the module docstring); a report with no readable time is."""
    if at is None:
        return True
    if now - at <= STALE_HOURS * 3600.0:
        return False
    due = _last_due(now)
    return due is not None and at < due


# -------------------------------------------------------------------------------------------------------- the readers
def _rows(db: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return guard.rows(db, sql, params)


def _one(db: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    found = guard.ids(db, sql, params)
    return found[0] if found else None


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _counted(db: sqlite3.Connection, engine: int | None, first: str, last: str) -> list[dict[str, Any]]:
    """D4's COUNTED rows of every pid with first <= day <= last, as `forward_db.counted_days` reads one pid's: the
    engine's rows with status "ok" and no `audit_mismatch` event for that (pid, day)."""
    if engine is None:
        return []
    return _rows(db, "SELECT d.pid, d.day, d.r, d.w, d.b, d.r0 FROM fwd_days d WHERE d.engine=? AND d.status='ok' AND "
                     "d.day>=? AND d.day<=? AND NOT EXISTS (SELECT 1 FROM fwd_events e WHERE e.kind='audit_mismatch' "
                     "AND e.pid=d.pid AND e.day=d.day)", (int(engine), first, last))


def _lineage_representatives(db: sqlite3.Connection, day: str) -> list[tuple[int, str]]:
    """(pid, key) of each lineage's representative among the rows registered by `day` (D6), in pid order."""
    best: dict[str, tuple[int, int, str]] = {}
    for row in _rows(db, "SELECT pid, key, lineage, reason FROM fwd_registry WHERE lane!='control' AND first_day<=? "
                         "ORDER BY pid", (day,)):
        rank = (0 if row["reason"] in REPRESENTATIVE_REASONS else 1, int(row["pid"]), str(row["key"]))
        if row["lineage"] not in best or rank < best[row["lineage"]]:
            best[row["lineage"]] = rank
    return sorted((pid, key) for _, pid, key in best.values())


def _representatives(db: sqlite3.Connection, day: str, max_members: int | None) -> list[tuple[int, str]]:
    found = _lineage_representatives(db, day)
    if max_members is not None and len(found) > int(max_members):
        found = sorted(found, key=lambda row: hashlib.sha256(("neff-1|" + row[1]).encode()).hexdigest())[:int(max_members)]
    return sorted(found)


def representatives(db: sqlite3.Connection, day: str) -> list[int]:
    """D6's representatives on `day`: one pid a lineage (its lowest pid whose reason is train_pass, seed or live,
    else its lowest pid), controls excluded, cut to `neff_max_members` by the smallest `sha256("neff-1|" + key)`
    (the code default here; `meters` passes the setting)."""
    return [pid for pid, _ in _representatives(db, _iso_day(day), int(forward_db.DEFAULTS["neff_max_members"]))]


def _population(db: sqlite3.Connection, day: str, max_members: int | None) -> tuple[list[str], Any]:
    import numpy as np

    window = _window(day, forward_db.NEFF_WINDOW)
    members = _representatives(db, day, max_members)
    out = np.full((len(members), len(window)), np.nan, dtype=np.float64)
    if not window or not members:
        return [key for _, key in members], out
    row_of = {pid: i for i, (pid, _) in enumerate(members)}
    column = {d: j for j, d in enumerate(window)}
    held = np.full(out.shape, np.nan, dtype=np.float64)
    for row in _counted(db, forward_db.engine_now(db), window[0], window[-1]):
        i = row_of.get(int(row["pid"]))
        if i is not None:
            held[i, column[row["day"]]] = float(row["r"]) - float(row["w"]) * float(row["b"])
    # Only the unbroken run ending at `day` is a member's record: a gap (no row, a disqualified day, an audit mark)
    # ends it, and what lies before the gap is not read.
    back = np.isfinite(held)[:, ::-1]
    runs = np.where(back.all(axis=1), len(window), np.argmin(back, axis=1))
    for i, n in enumerate(runs.tolist()):
        if n:
            out[i, len(window) - n:] = held[i, len(window) - n:]
    return [key for _, key in members], out


def population(db: sqlite3.Connection, day: str) -> tuple[list[str], Any]:
    """(the representatives' registry keys, X) for D6 on `day`: X an (N, T) float ndarray of daily excess over the
    window's forward days, NaN outside a member's unbroken run of counted days ending at `day`
    (`forward_stats.pairwise_corr`'s shape)."""
    return _population(db, _iso_day(day), int(forward_db.DEFAULTS["neff_max_members"]))


def sim_program_years(root: str | Path, db: sqlite3.Connection, day: str) -> float:
    """D7's sim_py through `day` (the swarm store read-only)."""
    from . import funnel

    path = Path(root) / funnel.SWARM_DB
    simulated = 0.0
    if path.exists():
        marks = ", ".join("?" * len(funnel.NOT_RUN))
        # (release E4: a panel family's Train runs are replays of the same years: they count)
        where = (f"FROM runs r JOIN families f ON f.id=r.family WHERE f.structure IN ('etf', 'stock', 'panel') AND "
                 f"r.trials>0 AND r.status NOT IN ({marks})")

        def read(swarm: sqlite3.Connection) -> float:
            try:
                return float(_one(swarm, "SELECT coalesce(sum(json_extract(r.summary, '$.days') * r.trials), 0) " + where,
                                  funnel.NOT_RUN) or 0.0)
            except sqlite3.OperationalError:   # an SQLite built without its JSON functions: read the summaries here
                parts = []
                for row in _rows(swarm, "SELECT r.summary, r.trials " + where, funnel.NOT_RUN):
                    try:
                        days = json.loads(row["summary"]).get("days")
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if isinstance(days, (int, float)) and not isinstance(days, bool):
                        parts.append(float(days) * int(row["trials"]))
                return math.fsum(parts)

        simulated = guard.read(path, read)
    recorded = int(_one(db, "SELECT count(*) FROM fwd_days d JOIN fwd_registry r ON r.pid=d.pid WHERE r.lane!='control' "
                            "AND d.day<=?", (_iso_day(day),)) or 0)
    return (simulated + recorded) / forward_stats.YEAR_SESSIONS


def _year_bars(store: Any, symbols: Sequence[str], year: int) -> Any:
    """One calendar year's slice up to the look cap, with history before it (the first return's base is its last
    session: `Bars.first` says where the year begins, however many history sessions the store hands a slice): Train
    days through `EquityStore.span`, the Validation year through its window, the look's span after it."""
    from ..equity import config
    from ..equity import store as ST

    first, last = dt.date(year, 1, 1), min(dt.date(year, 12, 31), config.LOOK_CAP)
    train_first, train_last = config.WINDOWS["train"]
    if last <= train_last:
        return store.span(symbols, max(first, train_first), last, history=1)
    name = "validation" if last <= config.WINDOWS["validation"][1] else ST.LOOK
    return store.bars(symbols, name, history=1, start=first, end=last)


def hist_independent_years(root: str | Path, symbols: Sequence[str]) -> float | None:
    """D7's hist_iy over `symbols` (`forward_stats.independent_years` on the store's as-of close-to-close returns, a
    year at a time through `config.LOOK_CAP`); None when the store cannot give it (`MissingData`)."""
    import numpy as np

    from ..equity import config
    from ..equity import store as ST

    try:
        store_root = Path(root) / ST.STORE_DIR
        store = ST.EquityStore(store_root, gate=ST.mint_equity_gate_capability(store_root, GATE_REASON))
        held = store.symbols()
        names = sorted({str(s).strip().upper() for s in symbols} & set(held))
        if not names:
            return None
        by_year: dict[int, Any] = {}
        for year in range(ST.FIRST_YEAR, config.LOOK_CAP.year + 1):
            bars = _year_bars(store, names, year)
            # The year's sessions and the ONE session before them (none before the store's first): a slice carries
            # as many history sessions as the store gives a run, and only the last is a return's base here.
            base = max(int(bars.first) - 1, 0)
            if bars.n - base < 2:
                continue
            # The as-of return of a session is the adjustment=all close ratio (the as-of factor cancels in a ratio).
            closes = np.vstack([bars.adj[sym][base:, 3] for sym in bars.symbols])
            whole = np.isfinite(closes).all(axis=1) & (closes > 0).all(axis=1)   # a bar on each of those sessions
            closes = closes[whole]
            by_year[year] = closes[:, 1:] / closes[:, :-1] - 1.0
        return forward_stats.independent_years(by_year)
    except (ST.MissingData, ST.StoreRefused, ValueError, OSError):
        return None


def _needs_symbols(db: sqlite3.Connection, day: str) -> list[str]:
    """The union of the NEEDS symbols of the non-control rows registered by `day`."""
    out: set[str] = set()
    for text in guard.ids(db, "SELECT DISTINCT needs FROM fwd_registry WHERE lane!='control' AND first_day<=?", (day,)):
        try:
            symbols = json.loads(text).get("symbols")
        except (TypeError, ValueError, AttributeError):
            continue
        out.update(str(s).upper() for s in symbols or () if isinstance(s, str))
    return sorted(out)


def _universe(settings: Mapping[str, Any] | None) -> list[str]:
    from ..swarm import elane

    return [str(s).upper() for s in elane.cfg(settings)["universe"]]


# ----------------------------------------------------------------------------------------------------- the day's rows
def _latest_checks(db: sqlite3.Connection, day: str, *, controls: bool) -> dict[int, dict[str, Any]]:
    """{pid: its latest checkpoint by `day`}: the largest n (a final one included) under the NEWEST engine that pid
    has a checkpoint for (D8)."""
    out: dict[int, dict[str, Any]] = {}
    for row in _rows(db, "SELECT c.pid, c.n, c.engine, c.p_x, c.p_x0 FROM fwd_checks c JOIN fwd_registry r ON r.pid=c.pid "
                         f"WHERE c.day<=? AND r.lane{'=' if controls else '!='}'control'", (day,)):
        held = out.get(int(row["pid"]))
        if held is None or (int(row["engine"]), int(row["n"])) > (int(held["engine"]), int(held["n"])):
            out[int(row["pid"])] = row
    return out


def _meter_row(db: sqlite3.Connection, day: str) -> dict[str, Any]:
    """D8's row of `day` (the module docstring: a checkpoint with no p is in the family at p = 1)."""
    latest = _latest_checks(db, day, controls=False)
    family = [latest[pid]["p_x"] for pid, _ in _lineage_representatives(db, day) if pid in latest]
    ps = [1.0 if p is None else float(p) for p in family]
    known = [float(p) for p in family if p is not None]
    controls = [row["p_x0"] for row in _latest_checks(db, day, controls=True).values()]
    cs = [1.0 if p is None else float(p) for p in controls]
    return {"day": day, "m": len(ps), "bh": forward_stats.bh(ps), "by_": forward_stats.by(ps),
            "min_p": min(known) if known else None, "controls_m": len(cs), "controls_bh": forward_stats.bh(cs),
            "controls_by": forward_stats.by(cs),
            "controls_p10": sum(1 for p in controls if p is not None and float(p) <= forward_db.Q) / len(cs) if cs else None}


def _base_groups(ugroups: Sequence[str]) -> str:
    return "+".join(sorted({part for text in ugroups for part in str(text).split("+") if part}))


def _group_rows(db: sqlite3.Connection, day: str) -> list[dict[str, Any]]:
    """D9's rows of `day`: one a program group, and one a control group registered by then."""
    close = _close_at(day)
    counted = {int(row["pid"]): row for row in _counted(db, forward_db.engine_now(db), day, day)}
    registry = {int(row["pid"]): row for row in _rows(
        db, "SELECT pid, lane, reason, ugroup FROM fwd_registry WHERE first_day<=?", (day,))}
    from . import forward_xs

    groups: dict[str, list[int]] = {name: [] for name in (*GROUP_REASONS, *GROUP_TAGS)}
    if any(forward_xs.is_panel(row) for row in registry.values()):
        # RELEASE E4 (package J): a panel pid stands in the panel's own groups ("xs:..."), never in an ETF group: a
        # residual against matched cells and an ETF excess are not one quantity, and no control group is the panel's.
        groups.update({name: [] for name in forward_xs.GROUPS})
    for pid, row in registry.items():
        if row["lane"] == "control":
            groups.setdefault(f"control:{row['ugroup']}", [])
            if pid in counted:
                groups[f"control:{row['ugroup']}"].append(pid)
        elif row["reason"] in GROUP_REASONS and pid in counted:
            groups.setdefault(forward_xs.group(row, row["reason"]), []).append(pid)
    if close is not None:
        for row in _rows(db, "SELECT pid, tag, min(at) AS at FROM fwd_tags WHERE tag IN (?, ?) GROUP BY pid, tag", GROUP_TAGS):
            pid = int(row["pid"])
            if float(row["at"]) < close and pid in counted and pid in registry and registry[pid]["lane"] != "control":
                groups[forward_xs.group(registry[pid], row["tag"])].append(pid)
    out = []
    for name in sorted(groups):
        pids = sorted(groups[name])
        rows = [counted[pid] for pid in pids]
        x = [float(r["r"]) - float(r["w"]) * float(r["b"]) for r in rows]
        x0 = [float(r["r0"]) - float(r["w"]) * float(r["b"]) for r in rows if r["r0"] is not None]
        out.append({"day": day, "grp": name, "n": len(pids), "mean_x": _mean(x),
                    "mean_r": _mean([float(r["r"]) for r in rows]), "mean_w": _mean([float(r["w"]) for r in rows]),
                    "mean_x0": _mean(x0) if name.startswith("control:") and len(x0) == len(rows) else None,
                    "ugroups": _base_groups([registry[pid]["ugroup"] for pid in pids])})
    return out


def rc_pairs(db: sqlite3.Connection, day: str) -> list[dict[str, Any]]:
    """D9 through `day`: one object a pair: {"a", "b", "usable" (its usable sessions so far), "next_read" (the count
    its next read is taken at; None after the last), "reads": [{"n", "day", "mean_bp", "t"}] (only the reads taken)}.
    No difference before a pair's read."""
    by_day: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _rows(db, "SELECT day, grp, n, mean_x, mean_x0, ugroups FROM fwd_groups WHERE day<=? ORDER BY day",
                     (_iso_day(day),)):
        by_day.setdefault(row["day"], {})[row["grp"]] = row
    floor = forward_db.RC_MIN_GROUP

    def program(groups: Mapping[str, Mapping[str, Any]], name: str) -> float | None:
        row = groups.get(name)
        return float(row["mean_x"]) if row and int(row["n"]) >= floor and row["mean_x"] is not None else None

    def pooled(groups: Mapping[str, Mapping[str, Any]], name: str) -> float | None:
        """THE POOLED CONTROLS of a program group's day: every control group it names has `floor` pids."""
        named = [g for g in str((groups.get(name) or {}).get("ugroups") or "").split("+") if g]
        values = []
        for group in named:
            row = groups.get(f"control:{group}")
            if not row or int(row["n"]) < floor or row["mean_x0"] is None:
                return None
            values.append(float(row["mean_x0"]))
        return _mean(values)

    pairs = [*RC_PAIRS, *((name, RC_CONTROLS) for pair in RC_PAIRS for name in pair)]
    out = []
    for a, b in pairs:
        days, first, second = [], [], []
        for d in sorted(by_day):
            left = program(by_day[d], a)
            right = pooled(by_day[d], a) if b == RC_CONTROLS else program(by_day[d], b)
            if left is not None and right is not None:
                days.append(d)
                first.append(left)
                second.append(right)
        reads = []
        for count in forward_db.RC_READS:
            if len(days) >= count:   # over exactly its first `count` usable sessions, whatever came after
                reads.append({**forward_stats.rc_read(first[:count], second[:count]), "day": days[count - 1]})
        out.append({"a": a, "b": b, "usable": len(days),
                    "next_read": next((c for c in forward_db.RC_READS if c > len(days)), None), "reads": reads})
    return out


def _write_day(root: str | Path, db: sqlite3.Connection, day: str, *, now: float, settings: Mapping[str, Any] | None,
               cap: int, history: dict[tuple[str, ...], float | None], awaited: int = 0) -> dict[str, int]:
    """One forward day's D6, D7, D8 and D9 rows, computed and then written in one transaction; the rows written."""
    n = forward_stats.neff(_population(db, day, cap)[1])
    cey_day = float(n["neff"]) / forward_stats.YEAR_SESSIONS
    total = math.fsum([*(float(v) for v in guard.ids(db, "SELECT cey_day FROM fwd_cey WHERE day<?", (day,))), cey_day])
    try:
        sim_py: float | None = sim_program_years(root, db, day)
    except Exception:  # noqa: BLE001 - an unread swarm store is None that day, never a zero
        sim_py = None
    try:
        symbols = tuple(_needs_symbols(db, day) or _universe(settings))
        if symbols not in history:
            history[symbols] = hist_independent_years(root, symbols)
        hist_iy = history[symbols]
    except Exception:  # noqa: BLE001
        hist_iy = None
    meter, groups = _meter_row(db, day), _group_rows(db, day)
    wrote = {"cey": 0, "meter": 0, "groups": 0}
    with db:   # one transaction a day; the `fwd_cey` row is the day's mark and goes last
        for g in groups:
            wrote["groups"] += db.execute(
                "INSERT OR IGNORE INTO fwd_groups(day, grp, n, mean_x, mean_r, mean_w, mean_x0, ugroups) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?)", (g["day"], g["grp"], g["n"], g["mean_x"], g["mean_r"], g["mean_w"],
                                                   g["mean_x0"], g["ugroups"])).rowcount
        wrote["meter"] += db.execute(
            "INSERT OR IGNORE INTO fwd_meter(day, m, bh, by_, min_p, controls_m, controls_bh, controls_by, "
            "controls_p10, at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day, meter["m"], meter["bh"], meter["by_"], meter["min_p"], meter["controls_m"], meter["controls_bh"],
             meter["controls_by"], meter["controls_p10"], float(now))).rowcount
        wrote["cey"] += db.execute(
            "INSERT OR IGNORE INTO fwd_cey(day, n_w, members, neff, neff_raw, cey_day, cey_total, sim_py, hist_iy, "
            "replay_multiple, at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (day, n["n_w"], n["members"], n["neff"], n["neff_raw"], cey_day, total, sim_py, hist_iy,
             forward_stats.replay_multiple(sim_py, hist_iy, total), float(now))).rowcount
        if awaited and wrote["cey"]:
            # Written after its wait, short of these awaited rows: marked once, and FW5 reads no such day.
            forward_db.event(db, "meter_partial", day=day, at=float(now), once="day",
                             payload={"why": f"written after {METER_WAIT_NIGHTS} later nights with programs still "
                                             "without their row for the day", "programs": int(awaited)})
    return wrote


def _behind(db: sqlite3.Connection, pid: int) -> bool:
    """A program whose LAST attempt failed twice in the child: a `run_failed` or a `run_behind` event newer than every
    row of its own, under any engine. The shadow's queue puts it behind its class until a run of it completes
    (league/ops/forward_shadow.py `Shadow._behind`, THE QUEUE'S HEAD); read here as the queue reads it."""
    failed = _one(db, "SELECT MAX(at) FROM fwd_events WHERE kind IN ('run_failed', 'run_behind') AND pid=?", (int(pid),))
    if failed is None:
        return False
    wrote = _one(db, "SELECT MAX(at) FROM fwd_days WHERE pid=?", (int(pid),))
    return wrote is None or float(wrote) < float(failed)


def _awaited(db: sqlite3.Connection, day: str) -> int:
    """How many registered rows A LATER NIGHT CAN STILL GIVE their row for `day` (the module docstring: A DAY'S METERS
    WAIT FOR ITS ROWS, and ONLY AN ABSENCE THE NEXT NIGHTS CAN FILL IS AWAITED).

    WHO LACKS IT: an active registered program that was owed `day` (first day on or before it; held by the registry at
    its close) and has no row for it under the newest engine; and a control in the same place whose data failed on
    that night or a later one (a `data_failed` event of its own: no budget leaves a control stale).
    WHOSE ABSENCE IS AWAITED: one that began on `day` (it has its row, under any engine, for the session before, which
    it was owed too), whatever its cause; or one of fewer than `METER_WAIT_NIGHTS` owed sessions running, `day` among
    them, of a program that is neither suspect nor behind in the queue. One without its row for `METER_WAIT_NIGHTS`
    owed sessions running is a standing absentee and is awaited no more."""
    engine, closed = forward_db.engine_now(db), _close_at(day)
    if engine is None or closed is None:
        return 0
    missing = _rows(db, "SELECT r.pid, r.first_day, r.registered_at FROM fwd_registry r WHERE r.first_day<=? AND "
                        "r.registered_at<=? AND NOT EXISTS (SELECT 1 FROM fwd_days d WHERE d.pid=r.pid AND d.day=? AND "
                        "d.engine=?) AND (r.lane!='control' OR EXISTS (SELECT 1 FROM fwd_events e WHERE "
                        "e.kind='data_failed' AND e.pid=r.pid AND e.day>=?))", (day, closed, day, int(engine), day))
    if not missing:
        return 0
    stopped = set(guard.ids(db, "SELECT DISTINCT pid FROM fwd_tags WHERE tag='stopped'"))
    # The forward days before `day` that an absence of `METER_WAIT_NIGHTS` sessions spans, the nearest first.
    before = [(session, _close_at(session)) for session in _window(day, METER_WAIT_NIGHTS)[-2::-1]]
    awaited = 0
    for row in missing:
        pid = int(row["pid"])
        if pid in stopped and not forward_db.active(db, pid):
            continue
        absent, began = 1, False                    # the owed sessions running without its row; it began on `day`
        for nearest, (session, close_at) in enumerate(before):
            if session < str(row["first_day"]) or close_at is None or float(row["registered_at"]) > close_at:
                break                               # not owed that session, nor any before it
            if _one(db, "SELECT 1 FROM fwd_days WHERE pid=? AND day=? LIMIT 1", (pid, session)) is not None:
                began = nearest == 0
                break
            absent += 1
        if began or (absent < METER_WAIT_NIGHTS and not forward_db.suspect(db, pid) and not _behind(db, pid)):
            awaited += 1
    return awaited


def _partial_days(db: sqlite3.Connection) -> set[str]:
    """The days whose meters were written short of a row still awaited (`meter_partial`; a day written without a
    standing absentee's row is not one)."""
    return {str(day) for day in guard.ids(db, "SELECT DISTINCT day FROM fwd_events WHERE kind='meter_partial'")}


def meters(root: str | Path, db: sqlite3.Connection, *, now: float, settings: Mapping[str, Any] | None
           ) -> dict[str, Any]:
    """The D6, D7, D8 and D9 rows of every forward day up to the last `fwd_runs` `through` that has no `fwd_cey` row,
    in order (first write stands: a second call writes nothing): {"days", "cey", "meter", "groups" (rows written)}.

    A DAY THAT CANNOT BE WRITTEN STOPS THE PASS THERE: the answer then also holds "error": {"day", "why" (the
    exception's name)}, nothing of that day is written (one transaction a day) and no later day is (CEY is a running
    sum: a later day written first would stand without it for good). The next pass begins at that day again. So does
    A DAY THAT WAITS FOR ITS ROWS (the module docstring): the answer then holds "waiting": {"day", "programs"}."""
    out: dict[str, Any] = {"days": 0, "cey": 0, "meter": 0, "groups": 0}
    through = _one(db, "SELECT max(through) FROM fwd_runs WHERE through IS NOT NULL")
    if through is None:
        return out
    have = set(guard.ids(db, "SELECT day FROM fwd_cey"))
    cap = int(_cfg(settings)["neff_max_members"])
    history: dict[tuple[str, ...], float | None] = {}
    nights = [str(n) for n in guard.ids(db, "SELECT DISTINCT through FROM fwd_runs WHERE through IS NOT NULL")]
    for day in forward_days(forward_db.t0(), through):
        if day in have:
            continue
        try:
            # A DAY'S METERS WAIT FOR ITS ROWS (the module docstring): the pass stops at a day still awaited.
            awaited = _awaited(db, day)
            if awaited and sum(1 for night in nights if night > day) < METER_WAIT_NIGHTS:
                out["waiting"] = {"day": day, "programs": awaited}
                break
            wrote = _write_day(root, db, day, now=now, settings=settings, cap=cap, history=history, awaited=awaited)
        except Exception as exc:  # noqa: BLE001 - named, and the pass stops: unread is never zero
            out["error"] = {"day": day, "why": type(exc).__name__}
            break
        for key, rows in wrote.items():
            out[key] += rows
        out["days"] += 1
    return out


# ------------------------------------------------------------------------------------------------------- the report
def _part(read: Callable[[], Any]) -> Any:
    """One part of the report; what cannot be read is named, never a zero, and the rest is written."""
    try:
        return read()
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def _registry(db: sqlite3.Connection, now: float) -> dict[str, Any]:
    by_reason = {reason: 0 for reason in forward_db.REASONS}
    today = dict(by_reason)
    for row in _rows(db, "SELECT reason, count(*) AS n, sum(registered_at>=?) AS fresh FROM fwd_registry GROUP BY reason",
                     (now - 86400.0,)):
        by_reason[row["reason"]] = int(row["n"])
        today[row["reason"]] = int(row["fresh"] or 0)
    stopped: dict[str, int] = {"cap": 0, "disqualified": 0}
    for pid in guard.ids(db, "SELECT DISTINCT pid FROM fwd_tags WHERE tag='stopped'"):
        if not forward_db.active(db, int(pid)):
            value = _one(db, "SELECT value FROM fwd_tags WHERE pid=? AND tag='stopped' ORDER BY at DESC, value DESC LIMIT 1",
                         (pid,))
            cause = str(value or "").split(":")[0] or "other"
            stopped[cause] = stopped.get(cause, 0) + 1
    suspects = sum(1 for pid in guard.ids(db, "SELECT DISTINCT pid FROM fwd_tags WHERE tag='suspect'")
                   if forward_db.suspect(db, int(pid)))
    try:
        chain = forward_db.verify_chain(db)
        chain = {"ok": chain.get("ok") is True, "rows": chain.get("rows"), "first_bad": chain.get("first_bad")}
    except Exception as exc:  # noqa: BLE001 - unread is not ok, and not broken either: it is named
        chain = {"ok": None, "error": type(exc).__name__}
    return {"total": sum(by_reason.values()), "programs": sum(n for r, n in by_reason.items() if r != "control"),
            "controls": by_reason["control"],
            "lineages": int(_one(db, "SELECT count(DISTINCT lineage) FROM fwd_registry WHERE lane!='control'") or 0),
            "by_reason": by_reason, "today": today, "stopped": stopped, "suspects": suspects, "chain": chain}


def _nights(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """The last two nights (a night is a `through`; its latest `fwd_runs` row), newest first. The panel lane's own
    nights (release E4: league/ops/forward_xs.py, its own job and its own day) are not among them: FX3 reads those."""
    from . import forward_xs

    out: list[dict[str, Any]] = []
    for row in _rows(db, "SELECT * FROM fwd_runs WHERE through IS NOT NULL AND job!=? ORDER BY run DESC LIMIT 20",
                     (forward_xs.JOB,)):
        if all(row["through"] != held["through"] for held in out):
            out.append(row)
    return sorted(out, key=lambda row: row["through"], reverse=True)[:2]


def _shadow(db: sqlite3.Connection) -> dict[str, Any]:
    nights = _nights(db)
    last = nights[0] if nights else None
    night = last["through"] if last else None
    failed = {kind: int(_one(db, "SELECT count(DISTINCT pid) FROM fwd_events WHERE kind=? AND day=?", (kind, night)) or 0)
              for kind in ("run_failed", "data_failed", "run_disqualified")} if night else \
        {"run_failed": 0, "data_failed": 0, "run_disqualified": 0}
    lost = _rows(db, "SELECT day, at FROM fwd_events WHERE kind='night_failed' ORDER BY seq DESC LIMIT 1")
    sessions = "SELECT count(*) FROM fwd_days d JOIN fwd_registry r ON r.pid=d.pid WHERE r.lane!='control' AND d.engine=?"
    engine = forward_db.engine_now(db)
    return {"through": night, "nights": int(_one(db, "SELECT count(DISTINCT through) FROM fwd_runs") or 0),
            "programs": last["programs"] if last else None, "sessions": last["sessions"] if last else None,
            "stale": last["stale"] if last else None, "errors": last["errors"] if last else None,
            "budget_hit": bool(last["budget_hit"]) if last else None,
            "seconds": int(round(float(last["seconds"]))) if last else None,
            "program_sessions": int(_one(db, sessions + " AND d.day=?", (engine, night)) or 0) if night else 0,
            "program_sessions_total": int(_one(db, sessions, (engine,)) or 0), **failed,
            "night_failed": {"day": lost[0]["day"], "at": S.iso(lost[0]["at"])} if lost else None}


def _checkpoints(db: sqlite3.Connection) -> dict[str, Any]:
    """How many programs have a checkpoint at each count (the checkpoint of record: any engine), controls apart."""
    out: dict[str, Any] = {str(n): 0 for n in forward_db.CHECKPOINTS}
    out.update(later=0, final=0, controls=0)
    for row in _rows(db, "SELECT c.n, c.final, r.lane='control' AS control, count(DISTINCT c.pid) AS pids FROM "
                         "fwd_checks c JOIN fwd_registry r ON r.pid=c.pid GROUP BY c.n, c.final, r.lane='control'"):
        if row["control"]:
            out["controls"] += int(row["pids"])
        elif str(row["n"]) in out and not row["final"]:
            out[str(row["n"])] += int(row["pids"])
        elif row["final"]:
            out["final"] += int(row["pids"])
        else:
            out["later"] += int(row["pids"])
    return out


def _meter(db: sqlite3.Connection) -> dict[str, Any] | None:
    """The latest `fwd_meter` row as the report shows it: counts and the controls' share; never `min_p`, and no
    count over a family under `METER_MIN` (THE METER'S FLOOR, the module docstring: `m` is always shown)."""
    rows = _rows(db, "SELECT day, m, bh, by_, controls_m, controls_bh, controls_by, controls_p10 FROM fwd_meter "
                     "ORDER BY day DESC LIMIT 1")
    engines = [int(e) for e in guard.ids(db, "SELECT DISTINCT engine FROM fwd_days ORDER BY engine")]
    if not rows:
        return {"day": None, "engines": engines}
    row = rows[0]
    if int(row["m"] or 0) < METER_MIN:      # THE METER'S FLOOR: a count over fewer lineages is a verdict on a program
        row.update(bh=None, by_=None)
        reading = METER_UNREAD
    else:
        reading = "none yet" if not row["by_"] else "edge somewhere"
    unreliable: bool | None = bool(row["controls_by"])
    if int(row["controls_m"] or 0) < METER_MIN:
        row.update(controls_bh=None, controls_by=None, controls_p10=None)
        unreliable = None
    return {**row, "q": forward_db.Q, "reading": reading, "unreliable": unreliable, "floor": METER_MIN,
            "engines": engines}


def _cey(db: sqlite3.Connection) -> dict[str, Any] | None:
    rows = _rows(db, f"SELECT * FROM fwd_cey ORDER BY day DESC LIMIT {MEDIAN_DAYS}")
    if not rows:
        return {"day": None}
    row = {k: v for k, v in rows[0].items() if k != "at"}
    return {**row, "provisional": int(row["n_w"]) < forward_db.NEFF_PROVISIONAL,
            "median20": statistics.median(float(r["cey_day"]) for r in rows), "days": len(rows)}


def _under_median(db: sqlite3.Connection) -> tuple[int, str | None]:
    """(for how many forward days running, ending at the latest, cey_day was under the median of the last
    `MEDIAN_DAYS` forward days up to it; the first of those days). A PARTIAL day (`meter_partial`: written short of a
    row a later night could still have given it) is read as no day at all: a night the budget cut says nothing of
    what the generators do. A day written without a standing absentee's row is no partial day and is read."""
    partial = _partial_days(db)
    rows = [row for row in _rows(db, "SELECT day, cey_day FROM fwd_cey ORDER BY day DESC LIMIT "
                                     f"{MEDIAN_DAYS + 10 * FW5_DAYS + len(partial)}")[::-1] if row["day"] not in partial]
    run, first = 0, None
    for i in range(len(rows) - 1, max(-1, len(rows) - 1 - 10 * FW5_DAYS), -1):
        window = [float(r["cey_day"]) for r in rows[max(0, i - MEDIAN_DAYS + 1):i + 1]]
        if not float(rows[i]["cey_day"]) < statistics.median(window):
            break
        run, first = run + 1, rows[i]["day"]
    return run, first


def _live_pids(db: sqlite3.Connection) -> set[int]:
    return {int(pid) for pid in guard.ids(db, "SELECT DISTINCT pid FROM fwd_tags WHERE tag='live'")}


def _fills(db: sqlite3.Connection) -> dict[str, Any]:
    """The fill gap and the twins as recorded (D10-D12): aggregates, and one row a live instance (the seated programs'
    twins are shown: the Done meter's A14 reads them). An instance whose registry row has no "live" tag is in the
    aggregates only."""
    timing = {}
    for at in ("open", "close"):
        drift = [float(v) for v in guard.ids(db, "SELECT drift_bp FROM fwd_fillgap WHERE at=?", (at,))]
        mean = _mean(drift)
        sd = math.sqrt(math.fsum((v - mean) ** 2 for v in drift) / (len(drift) - 1)) if len(drift) > 1 else None
        timing[at] = {"n": len(drift), "mean_bp": mean, "se_bp": None if sd is None else sd / math.sqrt(len(drift))}
    lots = _rows(db, "SELECT * FROM fwd_lotgap")
    columns = ("model_bp", "entry_slip_bp", "exit_slip_bp", "timing_entry_bp", "timing_exit_bp", "exec_entry_bp",
               "exec_exit_bp", "side_gap_bp", "twin_gap_bp")
    # A29's two columns beside the registered ones (a store nobody has opened for writing since the release that added
    # them reads NULL there: no re-base, and each row compared with the un-re-based twin itself).
    beside = "rebased, base_agree" if forward_db.has_column(db, "fwd_twins", "rebased") \
        and forward_db.has_column(db, "fwd_twins", "base_agree") else "NULL AS rebased, NULL AS base_agree"
    twins = _rows(db, f"SELECT instance, pid, agree, cause, {beside} FROM fwd_twins")
    causes = {cause: 0 for cause in forward_db.CAUSES}
    for row in twins:
        if row["agree"] == 0:
            causes[row["cause"] or "unknown"] = causes.get(row["cause"] or "unknown", 0) + 1
    readable = [row for row in twins if row["agree"] is not None]
    agreed = sum(1 for row in readable if row["agree"] == 1)
    part = _rows(db, "SELECT p.* FROM fwd_part p WHERE p.through=(SELECT max(q.through) FROM fwd_part q WHERE "
                     "q.instance=p.instance)")
    matched, missed, extra = (sum(int(row[k]) for row in part) for k in ("matched", "missed", "extra"))
    live = _live_pids(db)
    return {"timing": timing,
            "livelike": {"rows": int(_one(db, "SELECT count(*) FROM fwd_ll") or 0),
                         "no_minute": int(_one(db, "SELECT count(*) FROM fwd_events WHERE kind='no_minute'") or 0)},
            "lots": {"n": len(lots), "priced": sum(1 for row in lots if row["twin_gap_bp"] is not None),
                     "mean": {c: _mean([float(row[c]) for row in lots if row[c] is not None]) for c in columns},
                     "bound_bp": forward_db.A14_GAP_BP},
            "participation": {"instances": len(part), "matched": matched, "missed": missed, "extra": extra,
                              "rate": matched / (matched + missed + extra) if matched + missed + extra else None},
            "intents": {"sessions": len(readable), "agreed": agreed, "disagreed": len(readable) - agreed, "causes": causes,
                        "unreadable": len(twins) - len(readable),
                        "share": agreed / len(readable) if readable else None, "bound": forward_db.A14_AGREE},
            "by_instance": [row for row in _instances(lots, twins) if row["pid"] in live],
            "rebase": _rebase(twins, live)}


def _rebase(twins: Sequence[Mapping[str, Any]], live: set[int]) -> dict[str, Any]:
    """BESIDE THE INTENTS, NEVER IN A RULE (the captain's A29: the twin is re-based after a difference, so a miss
    counts once): how many times the twins were re-based, and the agreement of the UN-RE-BASED twin runs over the
    same sessions (`sessions`: those with a readable un-re-based comparison; `agreed`; `share`), in all and one row a
    LIVE instance, so a program whose live path has left its replay's days is seen. A row from before the release
    was compared with the un-re-based twin itself (`rebased` NULL: its `agree`)."""
    out: dict[str, dict[str, Any]] = {}
    for row in twins:
        held = out.setdefault(str(row["instance"]), {"instance": str(row["instance"]), "pid": row["pid"], "rebases": 0,
                                                     "sessions": 0, "agreed": 0})
        held["rebases"] = max(held["rebases"], int(row["rebased"] or 0))
        first = row["agree"] if row["rebased"] is None else row["base_agree"]
        if first is not None:
            held["sessions"] += 1
            held["agreed"] += 1 if int(first) == 1 else 0
    rows = [{**held, "pid": None if held["pid"] is None else int(held["pid"]),
             "share": held["agreed"] / held["sessions"] if held["sessions"] else None}
            for _, held in sorted(out.items())]
    sessions, agreed = sum(r["sessions"] for r in rows), sum(r["agreed"] for r in rows)
    return {"rebases": sum(r["rebases"] for r in rows), "sessions": sessions, "agreed": agreed,
            "share": agreed / sessions if sessions else None,
            "by_instance": [r for r in rows if r["pid"] in live]}


def _instances(lots: Sequence[Mapping[str, Any]], twins: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row an instance of the twins' tables: its priced closes and their mean twin gap, its readable sessions,
    those that agreed and those that did not, by cause (`forward_db.CAUSES`: "bars" when the live decision read other
    as-of bars than the store now gives; the vendor rounds adjusted prices to cents)."""
    out: dict[str, dict[str, Any]] = {}

    def slot(row: Mapping[str, Any]) -> dict[str, Any]:
        held = out.setdefault(str(row["instance"]), {"instance": str(row["instance"]), "pid": row["pid"], "lots": 0,
                                                     "gaps": [], "sessions": 0, "agreed": 0, "unreadable": 0,
                                                     "causes": {cause: 0 for cause in forward_db.CAUSES}})
        if held["pid"] is None:
            held["pid"] = row["pid"]
        return held

    for row in lots:
        held = slot(row)
        held["lots"] += 1
        if row["twin_gap_bp"] is not None:
            held["gaps"].append(float(row["twin_gap_bp"]))
    for row in twins:
        held = slot(row)
        if row["agree"] is None:
            held["unreadable"] += 1
        else:
            held["sessions"] += 1
            held["agreed"] += 1 if row["agree"] == 1 else 0
            if row["agree"] == 0:   # a disagreement is data: counted with its cause (the bars hash), never an error
                cause = row["cause"] if row["cause"] in held["causes"] else "unknown"
                held["causes"][cause] += 1
    return [{"instance": v["instance"], "pid": None if v["pid"] is None else int(v["pid"]), "lots": v["lots"],
             "priced": len(v["gaps"]), "mean_twin_gap_bp": _mean(v["gaps"]), "sessions": v["sessions"],
             "agreed": v["agreed"], "disagreed": v["sessions"] - v["agreed"], "causes": v["causes"],
             "unreadable": v["unreadable"]} for _, v in sorted(out.items())]


def _rc(db: sqlite3.Connection) -> dict[str, Any]:
    day = _one(db, "SELECT max(day) FROM fwd_groups")
    if day is None:
        return {"day": None, "groups": {}, "pairs": []}
    return {"day": day, "groups": {row["grp"]: int(row["n"]) for row in _rows(
        db, "SELECT grp, n FROM fwd_groups WHERE day=? ORDER BY grp", (day,))}, "pairs": rc_pairs(db, day)}


def _memory(root: Path) -> dict[str, Any] | None:
    """The memory tables' row counts (league/swarm/elane_memory.py `counts`: counts only, never a figure of a row)."""
    from ..swarm import elane_memory
    from . import funnel

    path = root / funnel.SWARM_DB
    return guard.read(path, lambda db: dict(elane_memory.counts(db))) if path.exists() else None


def _configured_routes(settings: Mapping[str, Any] | None) -> list[str]:
    """The model routes the swarm is configured to ask (`elane.e2.routes`): what the probe is owed on."""
    from ..swarm import elane_yield

    return [str(key) for key in elane_yield.cfg(settings)["routes"]]


def _first_seen(previous: Any, settings: Mapping[str, Any] | None, now: float) -> dict[str, str]:
    """{route: when a report first saw it configured}, carried from the report before this one (THE ROUTES CP1 READS,
    the module docstring); a route no longer configured is dropped. {} while the probe is off."""
    if not _probing(settings):
        return {}
    held = (previous.get("contamination") or {}).get("first_seen") if isinstance(previous, Mapping) and isinstance(
        previous.get("contamination"), Mapping) else None
    held = held if isinstance(held, Mapping) else {}
    return {key: held[key] if S.epoch(held.get(key)) is not None else S.iso(now) for key in _configured_routes(settings)}


def _contamination(root: Path, first_seen: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """`<state>/contamination.json` as the report carries it: one row a route, its cells as counts and names only; and
    `first_seen` (`_first_seen`). None with no file and no configured route."""
    from . import contam_probe

    doc = read_json(root / contam_probe.FILE, None)
    if not isinstance(doc, Mapping) or not isinstance(doc.get("routes"), Mapping):
        return {"version": None, "routes": {}, "first_seen": dict(first_seen)} if first_seen else None
    routes: dict[str, Any] = {}
    for key, row in sorted(doc["routes"].items()):
        if not isinstance(row, Mapping):
            continue
        cells = [(f"{stratum}/{era}", cell) for stratum, eras in sorted((row.get("cells") or {}).items())
                 if isinstance(eras, Mapping) for era, cell in sorted(eras.items()) if isinstance(cell, Mapping)]
        routes[str(key)] = {"at": row.get("at"), "attempted_at": row.get("attempted_at"),
                            "first_attempted_at": row.get("first_attempted_at"), "model": row.get("model"),
                            "probes": row.get("probes"), "attempts": row.get("attempts"), "idle": row.get("idle"),
                            "partial": "partial" in row,
                            "cells": len(cells), "readable": sum(1 for _, c in cells if c.get("readable") is True),
                            "recalled": [name for name, c in cells if c.get("recalled") is True]}
    return {"version": doc.get("version"), "routes": routes, "first_seen": dict(first_seen or {})}


def _receipts(root: Path, now: float) -> list[dict[str, Any]]:
    from . import release_receipts

    return release_receipts.summary(root, now=now)


def _previously_recalled(root: Path, route: str, at: Any) -> set[str] | None:
    """The cells the route's probe BEFORE its current one called recalled (the file's `history`); None with none."""
    from . import contam_probe

    doc = read_json(root / contam_probe.FILE, None)
    history = doc.get("history") if isinstance(doc, Mapping) else None
    older = [row for row in history or () if isinstance(row, Mapping) and row.get("route") == route
             and S.epoch(row.get("at")) is not None and S.epoch(at) is not None and S.epoch(row["at"]) < S.epoch(at)]
    if not older:
        return None
    last = max(older, key=lambda row: S.epoch(row["at"]))
    return {f"{stratum}/{era}" for stratum, eras in (last.get("cells") or {}).items() if isinstance(eras, Mapping)
            for era, cell in eras.items() if isinstance(cell, Mapping) and cell.get("recalled") is True}


# ------------------------------------------------------------------------------------------------------- the alarms
def _row(alarm: str, text: str, subject: str = "", level: str | None = None) -> dict[str, Any]:
    """One alarm row; its text opens with its id and its subject, then a colon: what `new` is told by. `level`: the
    row's own when its alarm's depends on its cause (FW3), else `ALARMS`'."""
    head = f"{alarm} {subject}".strip()
    return {"id": alarm, "level": level or ALARMS[alarm], "text": f"{head}: {text}", "new": True}


def _head(text: Any) -> str:
    return str(text).split(": ", 1)[0]


def _owed(db: sqlite3.Connection, now: float) -> tuple[str, str, int] | None:
    """FW1's day: (the last forward day whose rows were due by `now`, the session whose 09:00 New York was the
    deadline, how many registered rows were owed one), or None when nothing was owed: an empty registry, or no active
    row whose `first_day` is on or before that day and that the registry held by that day's close. The deadline is
    read as passed from `FW1_SETTLED_S` before it (the module docstring: this job's morning run)."""
    from ..equity import schedule as ES

    first, day = forward_db.t0(), ES.ny_day(now)
    for _ in range(2 * ES.HORIZON_DAYS):
        if day < first:
            return None
        if ES.is_session(day):
            after = ES.next_session(day)
            moments, closed = ES.moments(after), _close_at(day.isoformat())
            if moments is not None and closed is not None \
                    and float(moments.open_at) - FW1_BEFORE_OPEN_S - FW1_SETTLED_S <= now:
                iso = day.isoformat()
                held = "FROM fwd_registry WHERE first_day<=? AND registered_at<=? AND pid {op} (SELECT pid FROM fwd_tags " \
                       "WHERE tag='stopped')"
                owed = int(_one(db, "SELECT count(*) " + held.format(op="NOT IN"), (iso, closed)) or 0)
                owed += sum(1 for pid in guard.ids(db, "SELECT pid " + held.format(op="IN"), (iso, closed))
                            if forward_db.active(db, int(pid)))
                return (iso, after.isoformat(), owed) if owed else None
        day -= dt.timedelta(days=1)
    return None


def _stalled(db: sqlite3.Connection, now: float) -> list[dict[str, Any]]:
    """FW1's first half (the stale report is `alarms`': the reader's)."""
    owed = _owed(db, now)
    if owed is None or _one(db, "SELECT count(*) FROM fwd_days WHERE day=?", (owed[0],)):
        return []
    return [_row("FW1", f"no forward row for {owed[0]} by 09:00 New York on {owed[1]} though {owed[2]} registered rows "
                        "were owed one: the forward shadow did not complete (its receipt and forward-decider.log say "
                        "why)")]


def _backlog(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """FW2: the last two nights."""
    nights = _nights(db)
    if len(nights) < 2:
        return []
    out = []
    new, old = nights
    if int(new["stale"] or 0) > 0 and int(old["stale"] or 0) > 0:
        out.append(_row("FW2", f"programs were left stale two nights running ({old['through']}: {int(old['stale'])}, "
                               f"{new['through']}: {int(new['stale'])}): the night's budget does not cover the registry",
                        "stale"))
    failed = {(kind, night["through"]): set(guard.ids(
        db, "SELECT DISTINCT pid FROM fwd_events WHERE kind=? AND day=? AND pid IS NOT NULL", (kind, night["through"])))
        for kind in ("data_failed", "run_failed") for night in nights}
    earlier = failed[("data_failed", old["through"])] | failed[("run_failed", old["through"])]
    data, alone = failed[("data_failed", new["through"])] & earlier, failed[("run_failed", new["through"])] & earlier
    if data or alone:
        out.append(_row("FW2", f"{len(data | alone)} programs failed on both {old['through']} and {new['through']} "
                               f"({len(data)} without data, {len(alone)} whose run failed alone)", "failed"))
    return out


def _restated(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """FW3: `restated` events written since the last night began, counted by cause. One event is one program's
    restatement that night: its payload holds how many stored days differ (`days`; 1 when it does not say) and whether
    the decisions behind them read bars that have moved since (`bars`: "moved" | "same"; a control's says "none": it
    reads no bar). THE LEVEL (the module docstring): "info" when every restatement read bars that moved or is a
    control's; "warning" when one read the same bars or cannot say."""
    nights = _nights(db)
    if not nights:
        return []
    found = _rows(db, "SELECT pid, payload FROM fwd_events WHERE kind='restated' AND at>=?", (float(nights[0]["started"]),))
    if not found:
        return []
    days, causes, controls = 0, {"moved": 0, "same": 0}, 0
    for row in found:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = None
        payload = payload if isinstance(payload, Mapping) else {}
        count = payload.get("days")
        days += count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 1
        if payload.get("bars") in causes:
            causes[payload["bars"]] += 1
        elif payload.get("bars") == "none":
            controls += 1
    untold = len(found) - causes["moved"] - causes["same"]
    level = "warning" if causes["same"] or untold > controls else "info"
    return [_row("FW3", f"{days} stored days of {len({row['pid'] for row in found})} programs were restated on the night of "
                        f"{nights[0]['through']}: {causes['moved']} of the {len(found)} restatements read bars that have "
                        f"moved since (a vendor correction, or adjusted prices rounded to cents), {causes['same']} read "
                        f"the same bars (a recompute that is not deterministic)"
                        + (f", {untold} carry no bars hash" if untold else ""), level=level)]


def _chain(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """FW4."""
    chain = forward_db.verify_chain(db)
    if chain.get("ok") is True:
        return []
    return [_row("FW4", f"the registry's hash chain does not hold from pid {chain.get('first_bad')} ({chain.get('rows')} "
                        "rows): stop the forward jobs and compare with the backup")]


def _converging(db: sqlite3.Connection, root: Path, now: float) -> list[dict[str, Any]]:
    """FW5."""
    run, first = _under_median(db)
    if run < FW5_DAYS or first is None:
        return []
    births = _equity_births(root, _close_at(first) or now - FW5_DAYS * 86400.0, now)
    if not births:
        return []
    return [_row("FW5", f"the day's clean-evidence increment has been under its {MEDIAN_DAYS}-day median for {run} "
                        f"forward days running (since {first}) while {births} equity births went on: the generators may "
                        "be converging")]


def _twins_early(db: sqlite3.Connection, root: Path) -> list[dict[str, Any]]:
    """FW6: a living instance's twins before any checkpoint reads them."""
    out = []
    retired = _retired_instances(root)
    for row in _instances(_rows(db, "SELECT instance, pid, twin_gap_bp FROM fwd_lotgap"),
                          _rows(db, "SELECT instance, pid, agree, cause FROM fwd_twins")):
        if row["instance"] in retired:
            continue
        gap = row["mean_twin_gap_bp"]
        if row["priced"] >= FW6_CLOSES and gap is not None and abs(gap) > forward_db.A14_GAP_BP:
            out.append(_row("FW6", f"its mean twin gap over {row['priced']} priced closes is beyond the A14 bound "
                                   f"({'worse' if gap < 0 else 'better'} than the model)", f"instance {row['instance']} gap"))
        if row["sessions"] >= FW6_SESSIONS and row["agreed"] < forward_db.A14_AGREE * row["sessions"]:
            out.append(_row("FW6", f"{row['agreed']} of {row['sessions']} sessions agree with its twin, under the A14 "
                                   f"bound ({row['causes']['bars']} of the {row['disagreed']} that differ read other bars "
                                   "than the store now holds)", f"instance {row['instance']} intents"))
    return out


def _payload(text: Any) -> Mapping[str, Any]:
    try:
        held = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return held if isinstance(held, Mapping) else {}


def _retired_spans(db: sqlite3.Connection, pid: int | None, instance: str) -> list[tuple[str, str | None]]:
    """FW9: the instance's retirements it came back from, as [(its `twin_retired` day, the first `twin_revived` day on
    or after it | None)], oldest first (league/ops/forward_twins.py `_epochs`). A span with no revival yet runs on."""
    if pid is None:
        return []
    marks: dict[str, set[str]] = {"twin_retired": set(), "twin_revived": set()}
    for row in _rows(db, "SELECT kind, day, payload FROM fwd_events WHERE pid=? AND day IS NOT NULL AND kind IN "
                         "('twin_retired', 'twin_revived')", (int(pid),)):
        if _payload(row["payload"]).get("instance") == instance:
            marks[str(row["kind"])].add(str(row["day"])[:10])
    revived = sorted(marks["twin_revived"])
    return [(gone, next((day for day in revived if day >= gone), None)) for gone in sorted(marks["twin_retired"])]


def _last_twin_event(db: sqlite3.Connection, instance: str) -> tuple[str, str] | None:
    """FW9: (kind, day) of the latest `FW9_EVENTS` event that names `instance`; None with none."""
    marks = ", ".join("?" * len(FW9_EVENTS))
    for row in _rows(db, f"SELECT kind, day, at, payload FROM fwd_events WHERE kind IN ({marks}) ORDER BY seq DESC",
                     FW9_EVENTS):
        if _payload(row["payload"]).get("instance") == instance:
            return str(row["kind"]), str(row["day"] or S.iso(row["at"]))[:10]
    return None


def _living_instances(root: Path) -> list[dict[str, Any]]:
    """The live book's living equity instances (`eq_instances` with no `retired_at`): {"id", "created_at"}. [] with no
    book or no such table; an unreadable book raises (the alarm says it could not be read)."""
    from . import funnel

    path = root / funnel.LIVE_DB
    if not path.exists():
        return []

    def read(db: sqlite3.Connection) -> list[dict[str, Any]]:
        if "eq_instances" not in set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'")):
            return []
        return _rows(db, "SELECT id, created_at FROM eq_instances WHERE retired_at IS NULL ORDER BY id")

    return guard.read(path, read)


def _twin_gaps(db: sqlite3.Connection, root: Path, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """FW9 (a): a living ETF instance with a session that has no `fwd_twins` row, from its first row (its first
    decision session while it has none) through the session before the last E3 night's `through`. The sessions of a
    retirement it came back from are left out. A panel instance is FX1's. One with no registry row is read here: no
    twin is made for it in either lane. Silent while `elane.forward.twins` is false (no row is made)."""
    from ..equity import schedule as ES
    from . import forward_twins, forward_xs

    living = _living_instances(root) if _cfg(settings).get("twins") is True else []
    nights = _nights(db) if living else []
    if not nights:
        return []
    last = ES.previous_session(dt.date.fromisoformat(str(nights[0]["through"])[:10])).isoformat()
    out = []
    for inst in living:
        iid = str(inst["id"])
        found = _rows(db, "SELECT pid, ugroup FROM fwd_registry WHERE key=?", (forward_twins.registry_key(iid),))
        if found and forward_xs.is_panel(found[0]):
            continue
        pid = int(found[0]["pid"]) if found else None
        have = {str(day) for day in guard.ids(db, "SELECT day FROM fwd_twins WHERE instance=?", (iid,))}
        try:
            first = min(have) if have else forward_twins.d_first(inst).isoformat()
        except (KeyError, TypeError, ValueError):
            out.append(_row("FW9", "its first decision session cannot be read from the live book, so its twin rows "
                                   "cannot be checked", f"instance {iid} missing"))
            continue
        spans = _retired_spans(db, pid, iid)
        days = [day for day in forward_days(first, last)
                if not any(gone <= day and (back is None or day < back) for gone, back in spans)]
        missing = [day for day in days if day not in have]
        if not missing:
            continue
        text = (f"its shadow twin has no row for {len(missing)} of its {len(days)} sessions from {first} to {last} "
                f"(the first: {missing[0]}). A14 counts each as not agreed, and no Done checkpoint is final while one "
                "is missing")
        if pid is None:
            text += ". Its key is not in the forward registry, so no twin is made"
        hint = _last_twin_event(db, iid)
        if hint is not None:
            text += f". Its latest twin event: {hint[0]} of {hint[1]}"
        out.append(_row("FW9", text, f"instance {iid} missing"))
    return out


def _twin_disagreed(db: sqlite3.Connection, since: float) -> list[dict[str, Any]]:
    """FW9 (b): each `fwd_twins` row of an ETF instance with `agree` 0 written since `since`, told once with its
    cause, from the first session (FW6's share waits for 20). A panel row is FX2's."""
    out = []
    for row in _rows(db, "SELECT t.instance, t.day, t.cause FROM fwd_twins t LEFT JOIN fwd_registry r ON r.pid=t.pid "
                         "WHERE t.agree=0 AND t.at>=? AND (r.ugroup IS NULL OR r.ugroup NOT LIKE ?) "
                         "ORDER BY t.instance, t.day", (float(since), forward_db.PANEL_UGROUP + "%")):
        cause = row["cause"] if row["cause"] in forward_db.CAUSES else "unknown"
        out.append(_row("FW9", f"its live and twin intents disagree on {row['day']} (cause: {cause}). A14 counts it "
                               "once as not agreed, and the twin is re-based after it (A29)",
                        f"instance {row['instance']} {row['day']}"))
    return out


def _identity(db: sqlite3.Connection, since: float) -> list[dict[str, Any]]:
    """FW8."""
    moved = int(_one(db, "SELECT count(*) FROM fwd_events WHERE kind='identity_moved' AND at>=?", (since,)) or 0)
    if not moved:
        return []
    return [_row("FW8", f"the equity fingerprint moved while a lineage is live ({moved} identity_moved events since "
                        f"{S.iso(since)[:10]}): the forward series go on under a new engine label")]


def _each(checks: Sequence[tuple[str, Callable[[], list[dict[str, Any]]]]]) -> list[dict[str, Any]]:
    """Every alarm read on its own: one that cannot be read is an info row that says so (never silence, and never
    the loss of the others)."""
    out: list[dict[str, Any]] = []
    for alarm, read in checks:
        try:
            out += read()
        except Exception as exc:  # noqa: BLE001
            out.append({**_row(alarm, f"this alarm could not be read ({type(exc).__name__})", "unread"), "level": "info"})
    return out


def _equity_births(root: Path, start: float, end: float) -> int:
    """Equity-lane births in [start, end) (the funnel's own count); 0 when the swarm store cannot say."""
    from . import funnel

    try:
        counts = guard.read(root / funnel.SWARM_DB, lambda db: funnel.equity_counts(db, start, end))
        return sum(int(counts[lane]["births"]) for lane in funnel.EQUITY_LANES)
    except Exception:  # noqa: BLE001 - FW5 needs births it can see
        return 0


def _retired_instances(root: Path) -> set[str]:
    """The live book's retired equity instances (FW6 reads the living ones); empty when the book cannot say."""
    from . import funnel

    try:
        return set(guard.read(root / funnel.LIVE_DB, lambda db: guard.ids(
            db, "SELECT id FROM eq_instances WHERE retired_at IS NOT NULL")))
    except Exception:  # noqa: BLE001
        return set()


def _decide_alarm(root: Path) -> list[dict[str, Any]]:
    """FW7, from the live book (read-only)."""
    from . import funnel

    path = root / funnel.LIVE_DB
    if not path.exists():
        return []

    def read(db: sqlite3.Connection) -> tuple[int, Any, list[dict[str, Any]]]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        if not {"eq_instances", "kv"} <= tables:
            return 0, None, []
        return (int(_one(db, "SELECT count(*) FROM eq_instances WHERE retired_at IS NULL") or 0),
                _one(db, "SELECT value FROM kv WHERE key='eq_decide'"),
                _rows(db, "SELECT id, created_at, retired_at FROM eq_instances"))

    live, raw, instances = guard.read(path, read)
    try:
        decide = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        decide = None
    if not live or not isinstance(decide, Mapping) or not isinstance(decide.get("day"), str):
        return []
    day, status = decide["day"][:10], decide.get("status")
    if status == "failed":
        return [_row("FW7", f"the equity decide of {day} failed: the live programs took no decision that session")]
    close, at = _close_at(day), S.epoch(decide.get("at"))
    if status == "done" and not decide.get("why") and close is not None and at is not None and at > close + FW7_LATE_S:
        # NOBODY WAITED FOR A DECIDE THAT SEATED ITS PROGRAMS LATER. A catch-up decide with no live program is
        # written with a `why` and is ignored above; the book's seating pass (league/equity/live.py `_seat_step`) then
        # seats a program that passed its look afterwards and writes the record again without the `why`, keeping
        # the catch-up's `at`. Late is a decide that an instance was waiting for at the deadline: one the record
        # names (every living one when it names none) that the book held by then. One it cannot place counts as
        # waiting: unread is never on time.
        named = decide.get("instances") if isinstance(decide.get("instances"), list) else []
        asked = {str(name) for name in named}
        waited = [row for row in instances if (str(row["id"]) in asked if asked else row["retired_at"] is None)]
        placed = {str(row["id"]) for row in waited}
        on_time = [row for row in waited if not isinstance(row["created_at"], (int, float))
                   or float(row["created_at"]) <= close + FW7_LATE_S]
        if on_time or not waited or asked - placed:
            return [_row("FW7", f"the equity decide of {day} ran late (past 40 minutes after its close)")]
    return []


def _receipt_alarms(receipts: Any, now: float) -> list[dict[str, Any]]:
    out = []
    for row in receipts if isinstance(receipts, list) else ():
        day = S.iso(row["closes_at"])[:10]
        if row.get("unread"):
            out.append(_row("RR1", f"unread though its window closed on {day}: the stall job's receipts step did not "
                                   "read it", f"receipt {row['id']}"))
        elif row.get("verdict") in ("flat", "wrong_way") and now - float(row["read_at"]) <= RR2_DAYS * 86400.0:
            out.append(_row("RR2", f"read {row['verdict']} on {S.iso(row['read_at'])[:10]} (listed, never reverted)",
                            f"receipt {row['id']}"))
    return out


def _probe_alarms(root: Path, contamination: Any, now: float) -> list[dict[str, Any]]:
    """CP1 and CP2 (THE ROUTES CP1 READS, the module docstring): every route the file holds and every configured one
    (`contamination.first_seen`)."""
    out = []
    routes = contamination.get("routes") if isinstance(contamination, Mapping) else None
    routes = routes if isinstance(routes, Mapping) else {}
    first_seen = contamination.get("first_seen") if isinstance(contamination, Mapping) else None
    first_seen = first_seen if isinstance(first_seen, Mapping) else {}
    for key in [*routes, *(k for k in first_seen if k not in routes)]:
        row = routes.get(key) if isinstance(routes.get(key), Mapping) else {}
        at = S.epoch(row.get("at"))
        if at is not None:
            seen, never = at, ""
        else:
            # No probe of it ever completed: from its first attempt (written once, never moved) or the first report that
            # saw it configured, whichever is earlier (its last attempt is read too: all a row of an earlier build has).
            known = [t for t in (S.epoch(row.get("first_attempted_at")), S.epoch(row.get("attempted_at")),
                                 S.epoch(first_seen.get(key))) if t is not None]
            seen = min(known) if known else None
            never = " (no probe of it has ever completed)"
        if seen is not None and now - seen > CP1_DAYS * 86400.0:
            out.append(_row("CP1", f"no completed probe since {S.iso(seen)[:10]}{never}", f"route {key} unprobed"))
        recalled = [name for name in row.get("recalled") or () if name.split("/")[-1] in CP1_ERAS]
        before = _previously_recalled(root, key, row.get("at")) if recalled else None
        fresh = [name for name in recalled if before is None or name not in before]
        if fresh and at is not None and now - at <= RR2_DAYS * 86400.0:
            out.append(_row("CP1", f"{len(fresh)} readable cells newly recalled ({', '.join(fresh)})",
                            f"route {key} recall"))
        if isinstance(row.get("idle"), int) and not isinstance(row.get("idle"), bool) and row["idle"] >= CP2_IDLE:
            out.append(_row("CP2", f"its last {row['idle']} probe attempts added no cell", f"route {key}"))
    return out


def _memory_alarm(root: Path, since: float) -> list[dict[str, Any]]:
    """MM1: the swarm's `swarm.status` alerts of action "elane_memory" since `since`."""
    from . import funnel

    path = root / funnel.SWARM_DB
    if not path.exists():
        return []
    rows = guard.read(path, lambda db: _rows(
        db, "SELECT payload FROM events WHERE kind='swarm.status' AND at>=? AND payload LIKE '%elane_memory%' ORDER BY seq "
            "DESC LIMIT 2000", (S.iso(since),)))
    n = 0
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        n += 1 if isinstance(payload, Mapping) and payload.get("action") == "elane_memory" and payload.get("alert") is True \
            else 0
    return [_row("MM1", f"{n} memory alerts (swarm.status elane_memory) since {S.iso(since)[:10]}: a hidden year not "
                        "stamped at a birth, or an ingest that failed")] if n else []


def section(root: str | Path, *, now: float, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The report (`SECTION_KEYS`): `at`, `mode`, `t0`, `through`, `engine`, `registry` (counts by reason; stopped by
    cause; suspects), `shadow` (programs, sessions, stale, `run_failed`, `data_failed`, `run_disqualified`, the last
    `night_failed`), `checkpoints`, `meter` (with `engines`: the distinct engine ids in `fwd_days`), `cey` (with
    `neff_raw` beside), `fills` (timing, livelike, lots, participation, intents: agreed, disagreed by cause,
    unreadable; `rebase`: A29's re-bases and the un-re-based twins' own agreement beside, in all and a live
    instance), `rc` (one object a pair; group counts), `memory` (counts), `contamination`, `receipts`, `alarms`.
    Each object carries its tables' column names; what may appear is bounded by the module docstring."""
    root, now = Path(root), float(now)
    mode = _mode(settings)
    previous = read_json(root / FILE, None)
    before = S.epoch(previous.get("at")) if isinstance(previous, Mapping) else None
    since = max(now - LOOKBACK_DAYS * 86400.0, min(now - RECENT_HOURS * 3600.0, before if before is not None else now))
    out: dict[str, Any] = {key: None for key in SECTION_KEYS}
    out.update(at=S.iso(now), mode=mode, t0=_part(lambda: forward_db.t0().isoformat()))
    alarms: list[dict[str, Any]] = []
    db = None
    try:  # with the forward record off no forward part is read (EACH ALARM FOLLOWS ITS OWN SWITCH)
        db = forward_db.open_db(root, readonly=True) if mode != "off" else None
    except Exception:  # noqa: BLE001 - no forward store yet (or one that cannot be opened): nothing recorded to report
        db = None
    if db is not None:
        try:
            engine = _part(lambda: forward_db.engine_now(db))
            out["engine"] = engine if isinstance(engine, dict) else \
                {"id": engine, "label": None if engine is None else _part(lambda: forward_db.engine_label(db, engine))}
            for key, read in (("registry", lambda: _registry(db, now)), ("shadow", lambda: _shadow(db)),
                              ("checkpoints", lambda: _checkpoints(db)), ("meter", lambda: _meter(db)),
                              ("cey", lambda: _cey(db)), ("fills", lambda: _fills(db)), ("rc", lambda: _rc(db))):
                out[key] = _part(read)
            out["through"] = (out["shadow"] or {}).get("through")
            if mode != "off":
                alarms += _each((("FW1", lambda: _stalled(db, now)), ("FW2", lambda: _backlog(db)),
                                 ("FW3", lambda: _restated(db)), ("FW4", lambda: _chain(db)),
                                 ("FW5", lambda: _converging(db, root, now)), ("FW6", lambda: _twins_early(db, root)),
                                 ("FW8", lambda: _identity(db, since)),
                                 ("FW9", lambda: _twin_gaps(db, root, settings)),
                                 ("FW9", lambda: _twin_disagreed(db, since))))
                from . import forward_xs

                # RELEASE E4 (package J): the panel twin's alarms (FX1-FX3; each read on its own, never raising)
                alarms += forward_xs.alarms(db, root, now=now, since=since, settings=settings)
        finally:
            db.close()
    out["memory"] = _part(lambda: _memory(root))
    out["contamination"] = _part(lambda: _contamination(root, _first_seen(previous, settings, now)))
    out["receipts"] = _part(lambda: _receipts(root, now))
    alarms += _each(((("FW7", lambda: _decide_alarm(root)),) if mode != "off" else ())
                    + (("RR1", lambda: _receipt_alarms(out["receipts"], now)),)
                    + ((("CP1", lambda: _probe_alarms(root, out["contamination"], now)),) if _probing(settings) else ())
                    + (("MM1", lambda: _memory_alarm(root, since)),))
    known = {_head(a.get("text")) for a in (previous.get("alarms") or ()) if isinstance(a, Mapping)} \
        if isinstance(previous, Mapping) and isinstance(previous.get("alarms"), list) else set()
    out["alarms"] = [{**a, "new": _head(a["text"]) not in known} for a in alarms]
    return out


def _alarm_rows(doc: Any) -> list[dict[str, Any]]:
    rows = doc.get("alarms") if isinstance(doc, Mapping) else None
    return [{"id": a["id"], "level": a["level"], "text": a["text"], "new": bool(a.get("new"))}
            for a in rows or () if isinstance(a, Mapping) and isinstance(a.get("id"), str)
            and a.get("level") in ("info", "warning") and isinstance(a.get("text"), str)]


def read_section(root: str | Path) -> dict[str, Any] | None:
    """`<root>/forward-report.json` as written; None when absent, unreadable or stale (older than `STALE_HOURS` with a
    run of the job overdue since: the module docstring)."""
    doc = read_json(Path(root) / FILE, None)
    if not isinstance(doc, dict) or _stale(S.epoch(doc.get("at")), time.time()):
        return None
    return doc


def _zero() -> dict[str, int]:
    return {key: 0 for key in FUNNEL_KEYS}


def funnel_rows(root: str | Path, start: float, end: float) -> dict[str, int]:
    """The forward record's counts in [start, end), INTEGERS ONLY (`FUNNEL_KEYS`): `registered` and `registered_total`,
    `lineages`, `controls`, `program_sessions` and `program_sessions_total` (non-control `fwd_days` rows), `stale`,
    `errors`, `checkpoints`, `bh`, `by`, and from the swarm store read-only `oof_seen` and `oof_rows` (the seen-fact
    and out-of-fold rows with `at` in the window: `elane_memory.counts`' tables). An absent forward store or memory
    table is zeros (nothing was recorded); an unreadable one raises.

    A program-session and a checkpoint are counted once, when first written (the row of its first engine: the night a
    label moves writes every stored day again and counts nothing twice); the `_total`s, `lineages` and `controls` are
    everything up to `end`; `stale` is the last night's that ended in the window; `errors` the window's nights'
    errors and the nights that failed at their preflight; `bh` and `by` the latest meter row written before `end`
    whose family holds `METER_MIN` lineages (0 with none: THE METER'S FLOOR, the module docstring)."""
    from . import forward_xs, funnel

    root, a, b = Path(root), float(start), float(end)
    out = _zero()
    if (root / forward_db.DB).exists():
        first_engine = "NOT EXISTS (SELECT 1 FROM {t} e WHERE e.pid=d.pid AND e.{k}=d.{k} AND e.engine<d.engine)"
        days = ("SELECT count(*) FROM fwd_days d JOIN fwd_registry r ON r.pid=d.pid WHERE r.lane!='control' AND "
                + first_engine.format(t="fwd_days", k="day"))
        checks = ("SELECT count(*) FROM fwd_checks d JOIN fwd_registry r ON r.pid=d.pid WHERE r.lane!='control' AND "
                  + first_engine.format(t="fwd_checks", k="n"))

        def read(db: sqlite3.Connection) -> dict[str, int]:
            registry = "SELECT count(*) FROM fwd_registry WHERE lane{op}'control' AND registered_at<?"
            night = _rows(db, "SELECT stale FROM fwd_runs WHERE finished>=? AND finished<? AND job!=? ORDER BY run DESC "
                              "LIMIT 1", (a, b, forward_xs.JOB))
            meter = _rows(db, "SELECT bh, by_ FROM fwd_meter WHERE at<? AND m>=? ORDER BY day DESC LIMIT 1", (b, METER_MIN))
            return {"registered": _one(db, registry.format(op="!=") + " AND registered_at>=?", (b, a)),
                    "registered_total": _one(db, registry.format(op="!="), (b,)),
                    "lineages": _one(db, "SELECT count(DISTINCT lineage) FROM fwd_registry WHERE lane!='control' AND "
                                         "registered_at<?", (b,)),
                    "controls": _one(db, registry.format(op="="), (b,)),
                    "program_sessions": _one(db, days + " AND d.at>=? AND d.at<?", (a, b)),
                    "program_sessions_total": _one(db, days + " AND d.at<?", (b,)),
                    "stale": night[0]["stale"] if night else 0,
                    "errors": (_one(db, "SELECT coalesce(sum(errors), 0) FROM fwd_runs WHERE finished>=? AND finished<?",
                                    (a, b)) or 0)
                    + (_one(db, "SELECT count(*) FROM fwd_events WHERE kind='night_failed' AND at>=? AND at<?", (a, b)) or 0),
                    "checkpoints": _one(db, checks + " AND d.at>=? AND d.at<?", (a, b)),
                    "bh": meter[0]["bh"] if meter else 0, "by": meter[0]["by_"] if meter else 0}

        out.update({key: int(value or 0) for key, value in guard.read(root / forward_db.DB, read).items()})
    if (root / funnel.SWARM_DB).exists():
        def memory(db: sqlite3.Connection) -> dict[str, int]:
            tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mem_%'"))
            return {key: int(_one(db, f"SELECT count(*) FROM {table} WHERE at>=? AND at<?", (S.iso(a), S.iso(b))) or 0)
                    if table in tables else 0 for key, table in (("oof_seen", "mem_seen"), ("oof_rows", "mem_contrib"))}

        out.update(guard.read(root / funnel.SWARM_DB, memory))
    return out


def alarms(root: str | Path, *, now: float, settings: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """The alarms for the dlane report: the file's alarms when it is under `STALE_HOURS` old, each by its own switch
    (`raised`: with `forward_db.mode(settings)` "off" none of FW1-FW9, with the probe off no CP; RR and MM always);
    with a stale or absent file one FW1 row, or [] while the forward record is off. Every row is {"id", "level",
    "text", "new"}. Never raises for a missing or unreadable file.

    `settings` None: the swarm's own, as it loads them. A report that is old with no run of the job overdue since is
    not stale (the module docstring). FW1 keeps its silences here too: with the report stale or absent it is raised
    only when the registry holds a row that was owed a forward day (an empty registry, the sessions before a first
    registration's first day and a store not yet created owe nothing)."""
    try:
        root, now = Path(root), float(now)
        settings = _settings(root, settings)
        doc = read_json(root / FILE, None)
        at = S.epoch(doc.get("at")) if isinstance(doc, Mapping) else None
        if isinstance(doc, Mapping) and not _stale(at, now):
            return [row for row in _alarm_rows(doc) if raised(row["id"], settings)]
        if _mode(settings) == "off" or (isinstance(doc, Mapping) and doc.get("mode") == "off"):
            return []     # a stale report is FW1's to tell, and FW1 is silent while the forward record is off
        if not (root / forward_db.DB).exists():
            return []
        try:
            db = forward_db.open_db(root, readonly=True)
            try:
                owed = _owed(db, now)
            finally:
                db.close()
            if owed is None:
                return []
            why = f"{owed[2]} registered rows were owed the forward day {owed[0]}"
        except Exception:  # noqa: BLE001 - a stale report over a store that cannot be read is told, not hidden
            why = "the forward store could not be read"
        when = "there is no forward report" if at is None else f"the forward report was last written on {S.iso(at)[:10]}"
        return [{**_row("FW1", f"{when} though {why}: the forward_report job is stalled (its receipts say why)", "report"),
                 "new": True}]
    except Exception:  # noqa: BLE001 - never the dlane report's failure
        return []


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py). With the forward mode "off" it writes the report's parts that are not the
    forward record's (`OFF_KEYS`: {"at", "mode": "off", "memory", "contamination", "receipts", "alarms"}; the alarms
    RR, CP and MM, each by its own switch) to `FILE` and returns skipped; else `meters`, then `section` written to
    `FILE`. Each warning alarm is also a `ctx.alert("warning", text)`. The receipt holds counts, never a figure.

    THE REPORT IS WRITTEN WHATEVER THE METERS DID: when a day's meters cannot be written (a store locked, a row that
    cannot be read), that day and the days after it stay unwritten for the next run, the report and its alarms are
    still written, and the receipt is `failed` with the day and the exception's name (the runner starts the job again
    inside its grace)."""
    root, now = Path(ctx.root), float(ctx.now())
    settings = _settings(root, None, getattr(ctx, "config", None))
    if _mode(settings) == "off":
        # The forward record is off: no meter, no forward part. What has another switch, or none, is still written
        # and still raised (the memory counts, the probe's file, the release receipts; RR, CP, MM).
        whole = section(root, now=now, settings=settings)
        doc = {key: whole[key] for key in OFF_KEYS}
        write_json(root / FILE, doc)
        for alarm in doc["alarms"]:
            if alarm["level"] == "warning":
                ctx.alert("warning", f"forward: {alarm['text']}")
        return {"status": "skipped", "why": "the forward record is off (elane.forward.mode)",
                "alarms": [alarm["id"] for alarm in doc["alarms"]]}
    wrote: dict[str, Any] = {"days": 0, "cey": 0, "meter": 0, "groups": 0}
    try:
        db = forward_db.open_db(root)
        try:
            wrote = meters(root, db, now=now, settings=settings)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - the report is written without today's meters; the receipt says so
        wrote["error"] = {"day": None, "why": type(exc).__name__}
    error = wrote.pop("error", None)
    doc = section(root, now=now, settings=settings)
    write_json(root / FILE, doc)
    for alarm in doc["alarms"]:
        if alarm["level"] == "warning":
            ctx.alert("warning", f"forward: {alarm['text']}")
    out = {"path": str(root / FILE), "through": doc["through"], **wrote, "alarms": [alarm["id"] for alarm in doc["alarms"]]}
    if error is not None:
        return {"status": "failed", "error": f"the meters of {error['day'] or 'the night'} could not be written "
                                             f"({error['why']}); the report was written without them", **out}
    return {"ok": True, **out}


__all__ = ["FILE", "GATE_REASON", "STALE_HOURS", "SECTION_KEYS", "OFF_KEYS", "FUNNEL_KEYS", "ALARMS", "RC_PAIRS",
           "METER_WAIT_NIGHTS", "METER_MIN", "raised", "run", "meters",
           "representatives", "population", "sim_program_years", "hist_independent_years", "rc_pairs", "section",
           "read_section", "funnel_rows", "alarms", "text_ok", "forward_days"]
