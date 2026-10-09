"""The incubator's swarm facts (release B2, Sept 30, 2026): what research records for the House's incubator route to read.

THE ROUTE. The owner approved the incubator on Sept 29, 2026, and its reading was settled on Sept 30. It is a
shadow-to-real route for families that pass Train, pass the drift screen alone and show positive live practice. It
trades one lot of an approved real structure, at most `incubator.max_loss_usd` of maximum loss each ($75 since the
incubator cap of Oct 8, 2026; the owner's $50 before it). Its trades are never strategy evidence and never a
promotion: D2 is the only route to Probe and Sized. Every money rule of the route lives in the House
(`league/live`, the constitution's `options_money.incubator` row). The swarm records only the two facts below, in the
family's state. Each is bound to the evaluator it was made under, so no stale fact can pass.

1. THE TRAIN AND DRIFT MARK (`facts`, called by the tournament's hourly round after validation). For version `n` of an
   alive Gym-band family that holds an active practice cohort under the current evaluator, it writes
   `train_passed[str(n)] = {evaluator, objective, run, robust_pnl, drift: {t, positive, years}, at}` when ALL of these hold:
   - an eligible Train run of `n` (`train_eligible`) over the running Train span, under the current research evaluator;
   - its 1.5x Train robustness run landed with a profit (`researcher.robust_at_stress`);
   - it was not demoted (`bands.demoted`: a loss at 1.5x, or a failed drift screen);
   - THE DRIFT SCREEN knows its figures and passes them (`screen_verdict`: the tournament's own screen while it is on;
     while the tournament has switched it off, the screen at its default thresholds and at the owner's own where they
     are stricter, evaluated for the mark alone, Oct 8, 2026);
   - THE GATE HAS NOT BARRED ITS PROGRAM (`gate_bar`, below).
   `evaluator` is the store's `research_evaluator` and `objective` its `train_objective`, both as the mark was made. The
   live side (`bands.incubator`) accepts a mark only while both still equal the store's, because an evaluator adoption
   clears alive families only. The mark is written with a compare-and-set on the version's `robust_failed`,
   `drift_failed` and `train_passed` as read, so a demotion landing meanwhile wins. The newest `MARKS_KEPT` marks are
   kept per family. No Gym run is queued here: a version whose 1.5x run never landed stays unmarked (fail-closed); THE
   RE-RUNS (3, below) queue the runs a cohort version's mark waits on.

   A MARK GOES when its version is demoted or lost at 1.5x, when the gate bars its program, or when its drift figures
   are known and fail the screen (`facts`): with the verdict itself (THE VERDICT FIRST, below;
   `researcher.demote_version`), and by `sweep` (at the start of `facts`, and at the start and the end of every gate
   round, the leakage alarm's too). A mark is never removed while figures are only owed.

   THE INCUBATOR'S OWN DRIFT SCREEN (Oct 8, 2026; `screen_verdict`). The owner's term is "pass Train, pass the drift
   screen alone", and the screen binds the mark whatever the tournament does with it. FAST LANE V2 (Oct 7) switched the
   tournament's screen off for selection (`tournament.drift_screen` false: direction counts), and the mark read that as
   "never passes": no mark was written, the sweep took every mark, and no cohort could ever be pinned. Now, while the
   tournament's screen is off, the mark evaluates the screen itself at its default thresholds (`screen_settings`:
   `evidence.DRIFT_MIN_T`, every Train year but one) and, where `tournament.drift_min_t` or `drift_years_positive` are
   stricter than those, at the owner's thresholds too (a version must pass both: an off screen never loosens the
   mark), and the sweep keeps the marks. Nothing the tournament, validation, the gate or the bands select by changes:
   these settings are read here only, never written back.

   THE DIRECTION LANE'S MARK (release D-1, Oct 9, 2026; PLAN D5; `_direction_mark`). For a family whose lane is
   "direction" (`dlane.lane_of`), the drift screen alone is replaced by the lane's bar, direction-v2
   (`dlane.lane_verdict`: E1, E3, E4 and E5 on the eligible Train run, P1, R2 and R3 on the 1.5x run); the drift figures
   are kept in the mark, reported, and it says `lane` "direction". No direction mark is made while the lane takes none
   (`dlane.candidates_open`: "shadow", or K5), and the live side's reader refuses a direction mark meanwhile
   (`bands.incubator`). The alpha lane's mark is unchanged, and while `dlane.mode` is "off" every family is alpha's.
   A loosening of the owner's term "pass the drift screen alone" for the direction lane only; its cost is
   `_direction_mark`'s.

   THE GATE'S BAR (`gate_bar`) is durable, so it outlives the family's `gate_outcome` and `review` moving on to a newer
   version (the live side's own check reads `gate_outcome`, which names one program a family, and counts a passed
   `review`). A program is barred when:
   - the gate refused its version at any stage (the `refusals` rows), or a holdout look on it failed (the `looks` rows);
   - the family's `gate_outcome` names it refused, failed, demoted or held (`BAD_OUTCOMES`; a held look bars its program
     as a failed one does: THE LOOK HOLDS, Oct 2, 2026, were approved as a tightening);
   - THE GATE'S OWN REVIEW (`review`, `gate_review_bar`) names it with a verdict other than "pass", or with an audit that
     is not a readable passed audit, whatever its review contract: a failed review or audit, and one that cannot be
     read (the gate itself refuses anything but "pass"). A passed review whose audit is owed bars nothing: it is no
     verdict against the program, and the live side counts only a review and an audit that both passed;
   - THE INCUBATOR'S OWN REVIEW (`incubator_reviews[sha]`, `incubator_review_bar`) under the current review contract
     failed, or its audit is there but not a readable passed one (a failed review or audit is final for its program,
     so the live side never counts the gate's passed reading of it instead);
   - such a verdict was recorded in `incubator_barred[sha]` (THE VERDICT FIRST, below; and the sweep records every
     `gate_outcome` and every gate `review` it sees that bars a program). Every entry is kept (none is dropped for a
     newer one, nor trimmed with the incubator's reviews), so the bar outlives all of them moving on;
   - FAIL-CLOSED: its version cannot be read, or a record that would name the program cannot be read (`family_bar`:
     a `review` that is not a mapping or names no program, an `incubator_barred` or `incubator_reviews` that is not a
     mapping). The latter bars every program of the family while it stays so, and is never recorded or revoked.
   Nothing here is ever cleared: the rows are kept, and so is `incubator_barred`, which an evaluator adoption keeps
   too (it clears `gate_outcome`, `review`, the marks and the incubator's reviews, never a bar), after first recording
   there every verdict that only what it clears holds, and every bar the gate owes (`adoption_bars`, `load_owed`). A
   bar is as durable as a refusal row: a program whose review or audit failed never trades the incubator, under any
   later evaluator.

   THE PROGRAM (Oct 1, 2026). A verdict is on the program, its `gate.run_sha` (the code and the params), not on the
   family it was made in: the store links the lineages of identical code (`SwarmStore._link_code`), and the gate's and
   the incubator's review keys name the family, so the same program in another family would otherwise be read and
   passed afresh. `program_bar` (part of `gate_bar`, so no mark is made and no review is paid) bars a program when a
   refusal row names another version of it (`twins`) in any family, alive or retired, or another family holding it
   has a recorded bar, a bad `gate_outcome`, a failed gate or incubator review or audit, or (fail-closed) records that
   cannot be read. The live side's reader reads the same in its own read-only connection, and is the stricter one in
   another family: it also refuses a pass of the gate's `review` there whose audit is still owed (not final, so the
   House waits), and a retired family's `review` never moves on. So `program_bar` also bars, in every other family,
   whatever the reader's own rules refuse there (`bands.program_refusal`, FAIL-CLOSED: the two agree, and no review
   is paid for a program the reader would refuse). Such a bar is never recorded and never revokes a review
   (`program_only` leaves it out): it lifts when that family's audit lands, and lasts while a retired family's stays
   owed. In the family's own `review`, a pass whose audit is owed still bars nothing (the gate is still reading it).

   THE BACKFILL (`backfill`, at every swarm start before the evaluator adoption). Before the verdict-first bar (release B
   and earlier), a failed review or audit whose compare-and-set lost to a newer validation was written only to the
   append-only `swarm.gate` event log, and a third unclear answer only to its attempt count. The backfill reads both
   (the log from where it last stopped, `BACKFILL_KEY`) and records each as its program's bar.

   THE VERDICT FIRST (`record_verdict`, `record_bar`). The gate writes its own verdicts only while the version is still
   its to judge: its review and audit with a compare-and-set on `validation_version`, its refusal row and outcome after
   `_review_current`. A newer validation, an operator's hold or an error landing during a model read would otherwise
   leave a failed review or audit written nowhere. So every verdict against a program is recorded as its bar at
   once, in one transaction that also takes the program's marks and revokes its passed incubator review (the
   sweep's work for its family), before anything else is written and whether or not the gate's own write-back then
   succeeds: the gate's failed review or audit (a direct fail, and a third unclear answer), its refusals and bad
   outcomes, and the incubator's own failed review or audit (`put_review` records it in the same transaction as the
   review, so the newest-`REVIEWS_KEPT` trim never drops it). The live side's reader, which needs the mark, never
   sees a program so failed, not even until the next sweep. An unclear answer still to be asked again is no verdict.

2. THE INCUBATOR REVIEW AND AUDIT (`due_reviews` names the versions; `gate.Gate.incubator_reviews` makes them). The owner
   kept the gate's review and audit required. A marked version of an active, current cohort is due once its practice
   so far has at least `REVIEW_MIN_SESSIONS` completed sessions, at least `REVIEW_MIN_CLOSES` program closes and a
   positive program P&L, so the review is ready by the first look. It is due only while no FINAL review of its program
   (`gate.run_sha`) exists under the current review contract: a gate review (`review`) that failed or was audited, or an
   incubator review (`incubator_reviews[sha]`) that failed or was audited. The gate records
   `incubator_reviews[sha] = {sha, version, verdict, reasons, model, route, contract_sha, audit, at}` (the newest
   `REVIEWS_KEPT`). A failed review or audit is final for that program (recorded in `incubator_barred` at once: THE
   VERDICT FIRST), and so is the gate's bar (a passed incubator review of a program barred by name is turned into
   verdict "fail", stage "gate"). The incubator's reads keep
   their own attempt counts, their own model-call keys and their own Sail fuse (desk `<family>:incubator`), so the
   gate's own review, its three tries and its daily fuse are exactly as they were; the paid routes' shared budgets
   (Claude's funded total and any `claude.role_usd_day` line for the review or the audit; the OpenAI month) are the
   only thing the two share. The gate's own review state (`review`, `gate_ready`, `gated_sha`, `gate_outcome`) and its
   holdout looks are never touched, and no look is spent.

3. THE RE-RUNS (`reruns`, Oct 8, 2026; the swarm loop's hourly tournament round, after the marks: `Swarm.incubator_reruns`,
   league/swarm/loop.py, because league/swarm/tournament.py is the owner's deploy). A mark is bound to the Train
   objective and the evaluator it was made under, and its runs must be the running span's and the current evaluator's.
   The learning game's T0 (a new Train span, `researcher.migrate_objective`: `robustness` emptied, a new
   `train_objective`) and a Gym image change (`evaluator.adopt`: the marks, `robustness` and the selection cleared)
   leave every cohort version's mark stale and its runs another span's or image's, and the researcher queues those runs
   only for a family's best or submitted version, which a cohort version seldom is. So an active, current cohort's
   version with no current mark whose mark waits ONLY on Gym runs (`owed_runs`: no Train answer over the running span
   under the current evaluator, its drift figures owed, or its 1.5x run not landed) has them queued ONE AT A TIME, in
   that order (`owed_runs` `next`), so nothing is spent on a run its earlier answer rules out: its Train run over the
   running span, recorded as a scored Train row of the version (it brings the drift figures), then the "drift" run
   when a Train answer is in without them, then its 1.5x run (`researcher.Researcher.queue_incubator_runs`; never the
   mid run, which nothing here reads). Each at the robustness priority (`GymJob.incubator`: never superseded by a newer
   best). Never for a version that failed for good (`mark_of`'s drop: demoted, a loss at 1.5x, a known failed drift
   screen, the gate's bar), whose Train answer over the span is in and not eligible, whose drift figures over the span
   are in and fail the screen, on D2's route (the reader never admits it), or in a cohort that is failed, complete or
   under another evaluator (`practice_cohorts` reads the active, current ones only). A version is asked for again only
   once its jobs in flight have landed or failed (`Researcher._incubator`, released by `_settled`), so a failure is
   retried at a later round, and a restart, which loses the jobs, re-queues them at its first round. RERUN_ATTEMPTS
   bounds the EXECUTED failures (`RERUNS_KEY` in the family's state: a run the Gym ran that failed, erred, or landed
   without an answer under the current evaluator; never one lost to a restart, a supersession or a retirement); a
   version whose failures are spent, or whose run's own failures cap is reached (`researcher.ROBUSTNESS_ATTEMPTS`), is
   "spent" under that objective and evaluator, with one alert (`swarm.status` `incubator_reruns_spent`). They are asked
   for only while the guard allows new research (THE GATE'S RESERVE and the brake); jobs already queued are the pool's,
   which may resume an asleep box for a robustness head (`pool._take_active`: another box free, or the job aged) and
   runs them under the research hold as it runs every robustness job. They write no mark themselves: the next round's `facts` reads what landed.

WHY NEITHER FACT CAN PROMOTE ANYTHING. Neither is read by validation, the validation line, the gate's holdout, the
forward record, the bands' moves or `bands.read`. Only the live side's incubator reader (`bands.incubator`) reads them,
for the incubator route, whose trades are tuition (never a forward row) under its own money row. Research never reads
the House's real incubator rows; practice is read only from the House's `observe.sqlite`, read-only.

Adoption of a new evaluator clears the marks and the reviews (`evaluator.SELECTION_KEYS`), never the recorded bars;
`researcher.demote_version` removes a demoted version's mark. The live side's reader (`bands.incubator`) keeps its own
belt: it refuses a program barred here, one the gate's `review` names without a readable pass and passed audit, one the
incubator's own review or audit failed, a refused version, a failed look, and any record it cannot read, whatever the
mark says. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

# BAD_OUTCOMES: the gate's outcomes that bar a program, the House's reader's own list (`bands.BAD_OUTCOMES`), so the two can
# never disagree: refused, failed, demoted and held (THE LOOK HOLDS, Oct 2, 2026).
from . import dlane
from .bands import BAD_OUTCOMES, demoted
from .researcher import drift_settings, drift_verdict, robust_at_stress, row_span, running_span
from .store import SwarmStore, dumps, loads

#: Marks and incubator reviews kept per family (the newest versions' marks; the newest reviews by time). The gate's bars
#: (`incubator_barred`) are all kept for good (an adoption keeps them too): a bar dropped would let its program be marked
#: and read again.
MARKS_KEPT = 24
REVIEWS_KEPT = 8
#: A marked version is reviewed once its practice so far has this many completed sessions and program closes and a
#: positive program P&L: ready before its first look (3 sessions and 10 closes), and paid for only when it could pass.
REVIEW_MIN_SESSIONS = 2
REVIEW_MIN_CLOSES = 5
#: THE RE-RUNS (the module docstring, 3): the family-state key of the record of the re-runs queued for a version
#: ({version: {objective, evaluator, failures, queued, at, run, alerted}}, the newest `RERUNS_KEPT` versions), and how
#: many EXECUTED failures one (version, Train objective, evaluator) may have before it is spent (a restart, which loses the
#: queued jobs, charges nothing).
RERUNS_KEY = "incubator_reruns"
RERUNS_KEPT = 8
RERUN_ATTEMPTS = 3
#: The order the re-runs ask for a version's runs in (`owed_runs` `next`): each one's answer can rule out the rest.
RERUN_ORDER = ("train", "drift", "stress_1.5")
#: Incubator reviews a gate round makes (`gate.incubator_reviews`); a value past `REVIEWS_CEILING` is the ceiling.
REVIEWS_PER_ROUND = 2
REVIEWS_CEILING = 8
#: The House's practice record (`league/live/observe.py` `FILE`), read here read-only.
OBSERVE_FILE = "observe.sqlite"
NEW_YORK = "America/New_York"


# ---------------------------------------------------------------------------------------------------- small readers
def session_day(clock: Callable[[], float] = time.time) -> str:
    """Today's session day as the House names it: the New York date."""
    from zoneinfo import ZoneInfo

    return dt.datetime.fromtimestamp(float(clock()), ZoneInfo(NEW_YORK)).date().isoformat()


def practice_current(evaluator: Any, research: Mapping[str, Any] | None) -> bool:
    """A cohort's practice evaluator is the current research evaluator. The House writes it as
    "<Gym bundle>:<fill model version>:<execution fingerprint>" (`league/live/step.py`); the bundle and the fingerprint
    must be the store's `research_evaluator`'s. The fill model is the House's alone, and a cohort under an older one is
    completed by the House itself."""
    if not isinstance(evaluator, str) or not isinstance(research, Mapping):
        return False
    bundle, execution = research.get("bundle"), research.get("execution")
    if not bundle or not execution:
        return False
    head, tail = f"{bundle}:", f":{execution}"
    return evaluator.startswith(head) and evaluator.endswith(tail) and len(evaluator) > len(head) + len(tail)


def current_mark(mark: Any, evaluator: Any, objective: Any) -> bool:
    """A Train and drift mark made under the running research evaluator and Train objective (both known)."""
    return (isinstance(mark, Mapping) and evaluator is not None and objective is not None
            and mark.get("evaluator") == evaluator and mark.get("objective") == objective)


def final_review(state: Mapping[str, Any], sha: str) -> dict[str, Any] | None:
    """The FINAL review of program `sha` under the current review contract, or None: the gate's (`review`) or the
    incubator's (`incubator_reviews`), when it failed or its audit was made. A review that passed with its audit still
    owed is not final."""
    from .gate import gate_contract as review_contract

    contract = review_contract()["sha256"]
    reviews = state.get("incubator_reviews")
    for record in (state.get("review"), reviews.get(sha) if isinstance(reviews, Mapping) else None):
        if isinstance(record, Mapping) and record.get("sha") == sha and record.get("contract_sha") == contract \
                and (record.get("verdict") == "fail" or "audit" in record):
            return dict(record)
    return None


def _audit_bar(record: Mapping[str, Any], whose: str) -> str | None:
    """A review record's verdict and audit read fail-closed (`gate_review_bar`, `incubator_review_bar`)."""
    verdict = record.get("verdict")
    if verdict == "fail":
        stage = record.get("stage")
        if stage == "gate":
            return f"{whose} review of it was revoked (the gate barred it)"
        return f"{whose} audit failed it" if stage == "audit" else f"{whose} reviewer failed it"
    if verdict != "pass":
        return f"{whose} review of it cannot be read"
    if "audit" not in record:
        return None  # a passed review whose audit is owed: no verdict against it, and never a passed review and audit
    audit = record.get("audit")
    if not isinstance(audit, Mapping) or audit.get("verdict") not in ("pass", "fail"):
        return f"{whose} audit of it cannot be read"
    return f"{whose} audit failed it" if audit["verdict"] == "fail" else None


def gate_review_bar(review: Any, sha: str) -> str | None:
    """Why the gate's own review record (`review`: the newest program the gate read for the family) bars program `sha`,
    or None when it names another program or none (the module docstring, 1). Whatever its review contract, as
    `bands.observe` (which drops such a program even from shadow): a verdict other than "pass" (a failed review, or one
    that cannot be read) and an audit that is there but is not a readable passed audit bar it; a passed review whose
    audit is owed does not. A record that cannot be read at all is `family_bar`'s."""
    if not isinstance(review, Mapping) or not isinstance(review.get("sha"), str) or review.get("sha") != sha:
        return None
    return _audit_bar(review, "the gate's")


def incubator_review_bar(record: Any, sha: str) -> str | None:
    """Why the incubator's own review of program `sha` (`incubator_reviews[sha]`) bars it, or None (the module docstring,
    1): under the current review contract only (a review under another is asked again, as `final_review` says), a
    verdict other than "pass" or an audit that is there but is not a readable passed audit. A record that is not this
    program's under the current contract is none (it is read again, never counted by the live side)."""
    from .gate import gate_contract as review_contract

    if not isinstance(record, Mapping) or record.get("sha") != sha or record.get("contract_sha") != review_contract()["sha256"]:
        return None
    return _audit_bar(record, "the incubator's")


def family_bar(state: Mapping[str, Any]) -> str | None:
    """FAIL-CLOSED (the module docstring, 1): why every program of a family is barred while a record that would name one
    cannot be read, or None. A gate `review` that is not a mapping or names no program (an empty one is no review), and
    an `incubator_barred` or `incubator_reviews` that is not a mapping. It names no program, so nothing of it is
    recorded or revoked: the marks come back once the record reads again."""
    review = state.get("review")
    if review is not None and not isinstance(review, Mapping):
        return "the gate's review record cannot be read"
    if isinstance(review, Mapping) and review and not (isinstance(review.get("sha"), str) and review.get("sha")):
        return "the gate's review record names no program"
    for key, what in (("incubator_barred", "the recorded bars"), ("incubator_reviews", "the incubator's reviews")):
        if state.get(key) is not None and not isinstance(state.get(key), Mapping):
            return f"{what} cannot be read"
    return None


def gate_bar(store: SwarmStore, fam: Mapping[str, Any], n: int, *, sha: str | None = None,
             refused: list[dict[str, Any]] | None = None, looks: list[dict[str, Any]] | None = None,
             program_only: bool = False) -> str | None:
    """Why version `n`'s program is barred from the incubator for good, or None (the module docstring, 1): a refusal of
    the version at any stage, a failed holdout look on its program, the family's `gate_outcome` naming it refused,
    failed, demoted or held, the gate's review or audit failing it or unreadable for it (`gate_review_bar`), the incubator's
    own failing it (`incubator_review_bar`), or such a verdict of the gate recorded earlier (`incubator_barred`, an
    entry there bars its program even when the entry cannot be read). Fail-closed: a version that cannot be read is
    barred, and so is every program of a family whose records cannot be read (`family_bar`), unless `program_only`
    (the sweep's revocations, which are for good, take only bars that name the program). `refused` (the family's
    refusal rows) and `looks` (every look) may be passed in by a caller reading many versions."""
    fid = str(fam["id"])
    state = fam.get("state") or {}
    if not program_only:
        why = family_bar(state)
        if why is not None:
            return why
    for row in refused if refused is not None else store.refusals(fid):
        if row.get("version") == int(n):
            return f"the gate refused it (the {row.get('stage')})"
    if sha is None:
        from .gate import run_sha

        version = store.version(fid, int(n))
        if version is None:
            return "its version cannot be read"
        sha = run_sha(version)
    for look in looks if looks is not None else store.looks():
        if look.get("run_sha") == sha and not look.get("passed"):
            return "its holdout look failed"
    outcome = state.get("gate_outcome")
    if isinstance(outcome, Mapping) and outcome.get("sha") == sha and outcome.get("result") in BAD_OUTCOMES:
        return f"the gate's outcome for it is {outcome['result']}"
    why = gate_review_bar(state.get("review"), sha)
    if why is not None:
        return why
    reviews = state.get("incubator_reviews")
    why = incubator_review_bar(reviews.get(sha), sha) if isinstance(reviews, Mapping) else None
    if why is not None:
        return why
    recorded = state.get("incubator_barred")
    if isinstance(recorded, Mapping) and sha in recorded:
        entry = recorded[sha]
        return str(entry.get("why") or "the gate barred it") if isinstance(entry, Mapping) else "the gate barred it"
    return program_bar(store, fid, int(n), sha, program_only=program_only)


def twins(store: SwarmStore, fid: str, n: int) -> list[tuple[str, int]]:
    """Every version, in any family (alive or retired), of the same PROGRAM as version `n` of family `fid`: the same code
    and the same params, so the same `gate.run_sha` (the store links such lineages, `SwarmStore._link_code`), itself
    included. [] when the version cannot be read."""
    row = store._one("SELECT sha, params FROM versions WHERE family=? AND n=?", (str(fid), int(n)))
    if row is None:
        return []
    params = dumps(loads(row["params"], {}) or {})
    return [(str(r["family"]), int(r["n"])) for r in store._all("SELECT family, n, params FROM versions WHERE sha=? "
                                                                "ORDER BY family, n", (row["sha"],))
            if dumps(loads(r["params"], {}) or {}) == params]


def owed_audit_bar(review: Any, sha: str) -> str | None:
    """Why ANOTHER family's gate `review` holds off program `sha` while it is not final, or None: it names the program
    with a pass whose audit is still owed. The reader (`bands.program_refusal`) refuses the program in every family
    then, until that audit lands (never, once that family retired: its `review` stays). No verdict against the program,
    so it is never recorded and never revokes a review (`program_bar`, unless `program_only`)."""
    if (isinstance(review, Mapping) and review.get("sha") == sha and review.get("verdict") == "pass"
            and "audit" not in review):
        return "the gate's review of it passed with its audit still owed"
    return None


def program_bar(store: SwarmStore, fid: str, n: int, sha: str, *, program_only: bool = False) -> str | None:
    """THE PROGRAM (the module docstring, 1): why program `sha` (version `n` of family `fid`) is barred by a verdict made
    on the same program elsewhere, or None: a refusal of another version of it (`twins`) in any family, alive or
    retired, or, in another family holding it, a recorded bar, a bad `gate_outcome`, the gate's review or audit failing
    it (`gate_review_bar`) or the incubator's (`incubator_review_bar`); FAIL-CLOSED (unless `program_only`, as
    `gate_bar`): another such family's state or records cannot be read (`family_bar`), its gate `review` names the
    program with a pass whose audit is still owed (`owed_audit_bar`), or anything else THE READER'S BELT refuses there
    (`bands.program_refusal`, the reader's own rules on that family's state). So wherever the reader (`bands.incubator`)
    refuses a program for another family's records, this bars it too, and no mark is made and no review is paid for a
    program the reader would refuse. `program_only` (the sweep's revocations, for good) takes only the verdicts."""
    from .bands import program_refusal

    for other, m in twins(store, fid, n):
        if (other, m) == (str(fid), int(n)):
            continue
        refused = store._one("SELECT stage FROM refusals WHERE family=? AND version=? LIMIT 1", (other, m))
        if refused is not None:
            return f"the gate refused it in {other}@{m} (the {refused['stage']})"
        if other == str(fid):
            continue
        row = store._one("SELECT state FROM families WHERE id=?", (other,))
        if row is None:
            continue
        state = loads(row["state"], None)
        if not isinstance(state, Mapping):
            if program_only:
                continue
            return f"the state of {other}, which holds the same program, cannot be read"
        why = None if program_only else family_bar(state)
        outcome = state.get("gate_outcome")
        if why is None and isinstance(outcome, Mapping) and outcome.get("sha") == sha and outcome.get("result") in BAD_OUTCOMES:
            why = f"the gate's outcome for it is {outcome['result']}"
        why = why or gate_review_bar(state.get("review"), sha)
        reviews = state.get("incubator_reviews")
        why = why or (incubator_review_bar(reviews.get(sha), sha) if isinstance(reviews, Mapping) else None)
        recorded = state.get("incubator_barred")
        if why is None and isinstance(recorded, Mapping) and sha in recorded:
            entry = recorded[sha]
            why = str(entry.get("why") or "the gate barred it") if isinstance(entry, Mapping) else "the gate barred it"
        if why is None and not program_only:
            # THE READER'S BELT, read its own way: a pass whose audit is owed, then whatever else it refuses here.
            why = owed_audit_bar(state.get("review"), sha) or program_refusal(state, sha)
        if why is not None:
            return f"{why} (in {other}, which holds the same program)"
    return None


def unrecorded_bars(state: Mapping[str, Any]) -> dict[str, str]:
    """The gate's verdicts against a program that `incubator_barred` does not hold yet, {sha: why}: the family's
    `gate_outcome` naming it refused, failed, demoted or held, and the gate's `review` barring it (`gate_review_bar`). Each
    names one program a family and moves on with the next version, so the sweep records it first. {} while
    `incubator_barred` cannot be read (`family_bar` bars the whole family then)."""
    recorded = state.get("incubator_barred")
    if recorded is not None and not isinstance(recorded, Mapping):
        return {}
    out: dict[str, str] = {}
    outcome = state.get("gate_outcome")
    if isinstance(outcome, Mapping) and outcome.get("result") in BAD_OUTCOMES and outcome.get("sha"):
        out[str(outcome["sha"])] = f"the gate's outcome for it was {outcome['result']}"
    review = state.get("review")
    if isinstance(review, Mapping) and isinstance(review.get("sha"), str) and review.get("sha"):
        why = gate_review_bar(review, review["sha"])
        if why is not None:
            out.setdefault(review["sha"], why)
    return {sha: why for sha, why in out.items() if sha not in (recorded or {})}


def adoption_bars(state: Mapping[str, Any]) -> dict[str, str]:
    """What an evaluator adoption must record in `incubator_barred` before it clears the selection (`evaluator.adopt`),
    {sha: why}: `unrecorded_bars` (the gate's `review` and `gate_outcome`, which the adoption clears) and every incubator
    review that fails its program whatever its contract (`incubator_reviews`, cleared too). {} while `incubator_barred`
    cannot be read (it is left alone, and `family_bar` bars the whole family)."""
    recorded = state.get("incubator_barred")
    if recorded is not None and not isinstance(recorded, Mapping):
        return {}
    out = unrecorded_bars(state)
    reviews = state.get("incubator_reviews")
    for sha, record in (reviews.items() if isinstance(reviews, Mapping) else ()):
        if isinstance(record, Mapping) and record.get("sha") == sha and sha not in (recorded or {}) and sha not in out:
            why = _audit_bar(record, "the incubator's")
            if why is not None:
                out[str(sha)] = why
    return out


def save_owed(root: str | Path, owed: Mapping[tuple[str, str], tuple[int | None, str]]) -> None:
    """Keep the gate's bars owed (`gate.Gate.bars_owed`) beside the store (`bands.BARS_OWED_FILE`, written whole and
    replaced at once), so a restart cannot lose them: the gate reads them back at its start (`load_owed`), the evaluator
    adoption records them (`evaluator.adopt`) and the reader refuses their programs meanwhile. No file when none is owed."""
    import os

    from .bands import BARS_OWED_FILE

    path = Path(root) / BARS_OWED_FILE
    if not owed:
        path.unlink(missing_ok=True)
        return
    bars = [{"family": fid, "sha": sha, "version": n, "why": why} for (fid, sha), (n, why) in sorted(owed.items())]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"bars": bars}, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def load_owed(root: str | Path) -> dict[tuple[str, str], tuple[int | None, str]]:
    """The bars owed kept beside the store (`save_owed`), {(family, sha): (version, why)}; {} when none (or unreadable:
    the reader then refuses every program, fail-closed, until the gate writes the file again)."""
    from .bands import owed_bars

    out: dict[tuple[str, str], tuple[int | None, str]] = {}
    for bar in owed_bars(root) or []:
        version = bar.get("version")
        out[(str(bar.get("family")), str(bar["sha"]))] = (int(version) if isinstance(version, int) else None,
                                                          str(bar.get("why") or "the gate barred it"))
    return out


#: THE BACKFILL's place in the event log (`backfill`): the last `swarm.gate` event it read.
BACKFILL_KEY = "incubator_backfill_seq"
_FAILS = {"review": "the gate's reviewer failed it", "audit": "the gate's audit failed it",
          "incubator_review": "the incubator's reviewer failed it", "incubator_audit": "the incubator's audit failed it"}
_THIRD_UNCLEAR = {"review_attempt": "the gate's reviewer could not reach a verdict three times",
                  "audit_attempt": "the gate's audit could not reach a verdict three times",
                  "incubator_review_attempt": "the incubator's reviewer could not reach a verdict three times",
                  "incubator_audit_attempt": "the incubator's audit could not reach a verdict three times"}


def backfill(store: SwarmStore, *, clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """THE BACKFILL (Oct 1, 2026), at every swarm start before the evaluator adoption: a verdict the gate made before the
    verdict-first bar existed (release B and earlier) but wrote nowhere the reader reads (its compare-and-set lost to a
    newer validation, so only its `swarm.gate` event holds it), recorded as its program's bar (`incubator_barred`, in the
    family the verdict was made in, alive or retired). It reads the append-only event log from where it last stopped
    (`BACKFILL_KEY`): a failed review or audit (the gate's or the incubator's) and a bar an error kept from the store
    (`incubator_bar_error`); and every third unclear answer (the attempt counts in the key-values, which no event
    records as a fail). Each (family, version) is read as its program (`gate.run_sha`). Idempotent: a recorded bar is
    kept as it is. Returns {"read", "barred"}; anything recorded is one private `swarm.gate` event (`incubator_backfill`)."""
    from .gate import run_sha

    raw = store.get(BACKFILL_KEY, 0)
    last = int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 0
    found: dict[str, dict[str, tuple[int | None, str]]] = {}
    shas: dict[tuple[str, int], str | None] = {}

    def program(fid: str, n: Any) -> str | None:
        if isinstance(n, bool) or not isinstance(n, int):
            return None
        if (fid, n) not in shas:
            row = store._one("SELECT sha, params FROM versions WHERE family=? AND n=?", (fid, n))
            shas[(fid, n)] = None if row is None else run_sha({"sha": row["sha"], "params": loads(row["params"], {}) or {}})
        return shas[(fid, n)]

    top = int((store._one("SELECT MAX(seq) AS seq FROM events WHERE kind='swarm.gate'") or {}).get("seq") or 0)
    read = int((store._one("SELECT COUNT(*) AS n FROM events WHERE kind='swarm.gate' AND seq>? AND seq<=?", (last, top))
                or {}).get("n") or 0)
    # Only the rows that can hold a fail are loaded (payloads are compact JSON with sorted keys: `store.dumps`).
    rows = store._all("SELECT seq, family, payload FROM events WHERE kind='swarm.gate' AND seq>? AND seq<=? AND "
                      "(payload LIKE '%\"verdict\":\"fail\"%' OR payload LIKE '%\"action\":\"incubator_bar_error\"%') "
                      "ORDER BY seq", (last, top))
    for row in rows:
        payload, fid = loads(row["payload"], None), row["family"]
        if not isinstance(payload, Mapping) or not fid:
            continue
        action, n = payload.get("action"), payload.get("version")
        if action in _FAILS and payload.get("verdict") == "fail":
            sha = program(str(fid), n)
            if sha is not None:
                found.setdefault(str(fid), {}).setdefault(sha, (n, _FAILS[action]))
        elif action == "incubator_bar_error" and isinstance(payload.get("sha"), str) and payload["sha"]:
            numbers = [n] if isinstance(n, int) else [int(v["n"]) for v in store._all(
                "SELECT n FROM versions WHERE family=?", (str(fid),))]
            for m in numbers:
                sha = program(str(fid), m)
                if sha is not None and sha.startswith(payload["sha"]):
                    found.setdefault(str(fid), {}).setdefault(sha, (m, str(payload.get("bar") or "the gate barred it")))
    by_sha: dict[str, list[tuple[str, int]]] | None = None
    for row in store._all("SELECT key, value FROM kv WHERE key LIKE '%_attempt:%'"):
        stage, _, rest = str(row["key"]).partition(":")
        count = loads(row["value"], 0)
        if stage not in _THIRD_UNCLEAR or isinstance(count, bool) or not isinstance(count, int) or count < 3:
            continue
        parts = rest.split(":")
        if stage.endswith("review_attempt") and len(parts) == 3 and parts[2].isdigit():
            sha = program(parts[1], int(parts[2]))
            if sha is not None:
                found.setdefault(parts[1], {}).setdefault(sha, (int(parts[2]), _THIRD_UNCLEAR[stage]))
        elif stage.endswith("audit_attempt") and len(parts) == 2:
            if by_sha is None:
                by_sha = {}
                for v in store._all("SELECT family, n, sha, params FROM versions"):
                    key = run_sha({"sha": v["sha"], "params": loads(v["params"], {}) or {}})
                    by_sha.setdefault(key, []).append((str(v["family"]), int(v["n"])))
            for fid, n in by_sha.get(parts[1], []):
                found.setdefault(fid, {}).setdefault(parts[1], (n, _THIRD_UNCLEAR[stage]))
    barred: list[str] = []
    for fid, bars in sorted(found.items()):
        with store.atomic():
            recorded = ((store.family(fid) or {}).get("state") or {}).get("incubator_barred")
            if recorded is not None and not isinstance(recorded, Mapping):
                continue  # never written over (`family_bar` bars every program of the family while it stays so)
            for sha, (n, why) in sorted(bars.items()):
                if sha not in (recorded or {}):
                    _record_bar(store, fid, sha, why, n, clock)
                    barred.append(f"{fid}:{sha[:12]}")
    if top > last:
        store.put(BACKFILL_KEY, top)
    if barred:
        store.event("swarm.gate", None, {"action": "incubator_backfill", "barred": barred, "read": read})
    return {"read": read, "barred": barred}


def verdict_bar(record: Any, whose: str) -> str | None:
    """Why a review record as its reader returned it or as it is kept (the gate's `review`, `incubator_reviews[sha]`)
    bars its program, or None (`_audit_bar`): a failed review or audit and a verdict or audit that cannot be read. An
    answer still to be asked again (an unclear review or audit: the gate asks up to three times) is no verdict yet, and a
    record that is not a mapping is none (`family_bar` reads a kept one)."""
    if not isinstance(record, Mapping):
        return None
    audit = record.get("audit")
    if record.get("verdict") == "unclear" or (isinstance(audit, Mapping) and audit.get("verdict") == "unclear"):
        return None
    return _audit_bar(record, whose)


def record_verdict(store: SwarmStore, fid: str, sha: str, record: Any, *, whose: str, version: int | None = None,
                   clock: Callable[[], float] = time.time) -> str | None:
    """THE VERDICT FIRST (the module docstring, 1) for a review or audit: when `record` bars program `sha`
    (`verdict_bar`: `whose` is "the gate's" or "the incubator's"), it is recorded as the program's bar at once
    (`record_bar`). Returns the bar's words, or None when it bars nothing."""
    why = verdict_bar(record, whose)
    if why is not None:
        record_bar(store, fid, sha, why, version=version, clock=clock)
    return why


def record_bar(store: SwarmStore, fid: str, sha: str, why: str, *, version: int | None = None,
               clock: Callable[[], float] = time.time) -> dict[str, list[str]]:
    """THE VERDICT FIRST (the module docstring, 1): record a verdict against program `sha` in family `fid`'s
    `incubator_barred[sha]` and, in the same transaction, take the program's marks and revoke its passed incubator
    review (`sweep`'s work for this family), whatever the caller then writes or fails to write. The first entry for a
    program is kept. An `incubator_barred` that cannot be read is never written over (`family_bar` bars every program
    of the family while it stays so; the marks still go). Returns {removed, barred, revoked} as `sweep` does; anything
    done is one private `swarm.gate` event (`incubator_bar`), written after the transaction."""
    with store.atomic():
        done, why_of = _record_bar(store, fid, sha, why, version, clock)
    _bar_event(store, fid, sha, why, version, done, why_of)
    return done


def _record_bar(store: SwarmStore, fid: str, sha: str, why: str, version: int | None,
                clock: Callable[[], float]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """`record_bar`'s writes, inside the caller's transaction."""
    fam = store.family(fid)
    if fam is None:
        return {"removed": [], "barred": [], "revoked": []}, {}
    state = fam.get("state") or {}
    recorded = state.get("incubator_barred")
    view, values = fam, {}
    added = (recorded is None or isinstance(recorded, Mapping)) and sha not in (recorded or {})
    if added:
        entry: dict[str, Any] = {"why": str(why), "at": float(clock())}
        if version is not None:
            entry["version"] = int(version)
        values["incubator_barred"] = {**dict(recorded or {}), sha: entry}
        view = {**fam, "state": {**state, "incubator_barred": values["incubator_barred"]}}
    # The sweep's work for this family, on the view that holds the new entry (its own record of `unrecorded_bars`
    # builds on it).
    swept, done, why_of = _swept(store, view, store.looks(), clock)
    values.update(swept)
    if added:
        done["barred"].insert(0, f"{fid}:{sha[:12]}")
    if values:
        store.set_state(fid, **values)
    return done, why_of


def _bar_event(store: SwarmStore, fid: str, sha: str, why: str, version: int | None, done: Mapping[str, list[str]],
               why_of: Mapping[str, str]) -> None:
    if any(done.values()):
        store.event("swarm.gate", fid, {"action": "incubator_bar", "version": version, "sha": sha[:12], "bar": why,
                                        **done, "why": dict(why_of)})


def reviews_per_round(settings: Mapping[str, Any]) -> int:
    """`gate.incubator_reviews`: a whole number from 0 (off) to `REVIEWS_CEILING`; anything else is the default."""
    raw = (settings.get("gate") or {}).get("incubator_reviews", REVIEWS_PER_ROUND)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or float(raw) != int(raw):
        return REVIEWS_PER_ROUND
    return max(0, min(REVIEWS_CEILING, int(raw)))


def screen_settings(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """THE INCUBATOR'S OWN DRIFT SCREEN (the module docstring, 1): the settings the mark's drift screen is read under.
    While the tournament's screen is on (`researcher.drift_settings` not None), `settings` itself, so the mark and the
    tournament read one screen at the same thresholds. While the tournament has switched it off (`tournament.drift_screen`
    false, FAST LANE V2), a copy with the screen on at its DEFAULT thresholds (`drift_min_t` and `drift_years_positive`
    left out: `evidence.DRIFT_MIN_T`, and every Train year but one): an off screen is the tournament's choice for
    selection, never a pass, and never a reason to mark nothing. Never written back: the tournament, validation, the gate
    and the bands read `settings` as they were."""
    if drift_settings(settings) is not None:
        return settings
    tournament = {k: v for k, v in dict(settings.get("tournament") or {}).items()
                  if k not in ("drift_min_t", "drift_years_positive")}
    return {**dict(settings), "tournament": {**tournament, "drift_screen": True}}


def screen_verdict(store: SwarmStore, fam: Mapping[str, Any], n: Any, settings: Mapping[str, Any]) -> dict[str, Any] | None:
    """THE INCUBATOR'S OWN DRIFT SCREEN on version `n` (the module docstring, 1): the tournament's verdict
    (`researcher.drift_verdict`) while its screen is on. While it is off, the verdict at the defaults (`screen_settings`)
    and, when that passes, at the owner's own thresholds as configured (`tournament.drift_min_t`,
    `drift_years_positive`, read as the screen reads them): a version must pass both, so an owner's threshold stricter
    than the default binds the mark and a looser one never loosens it. Both read one set of figures, so `known` is the
    same in each."""
    if drift_settings(settings) is not None:
        return drift_verdict(store, fam, n, settings)
    verdict = drift_verdict(store, fam, n, screen_settings(settings))
    if verdict is None or not verdict["known"] or not verdict["passed"]:
        return verdict
    owner = {**dict(settings), "tournament": {**dict(settings.get("tournament") or {}), "drift_screen": True}}
    stricter = drift_verdict(store, fam, n, owner)
    return stricter if stricter is not None and stricter["known"] and not stricter["passed"] else verdict


# ---------------------------------------------------------------------------------------------------- the cohorts
def practice_cohorts(root: str | Path, *, research: Mapping[str, Any] | None, before: str) -> list[dict[str, Any]]:
    """The House's ACTIVE practice cohorts under the current evaluator (`practice_current`), with their practice so far,
    read-only (`mode=ro`, a one-second timeout). Never raises: [] without the file, before its cohorts table, or on any
    error. One row a cohort, oldest first:

        family, version, first_day, run_sha (the snapshot's program), evaluator (the cohort's practice evaluator)
        sessions         completed sessions (`practice.sessions`, less today's); None when there is no practice row or it
                         is older than the cohort (a record from before the cohort is not the cohort's)
        closes_program   program-closed trades (not forced) under the cohort's evaluator that closed before `before`
        pnl_program      their P&L (the engine's, after its fees)
    """
    path = Path(root) / OBSERVE_FILE
    if not path.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            return _cohorts(db, research, str(before))
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - a fact that cannot be read is not written
        return []


def _cohorts(db: sqlite3.Connection, research: Mapping[str, Any] | None, before: str) -> list[dict[str, Any]]:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"cohorts", "practice", "trades"} <= tables:
        return []
    columns = {row[1] for row in db.execute("PRAGMA table_info(trades)")}
    if not {"evaluator", "forced", "exit_day"} <= columns:
        return []
    out = []
    rows = db.execute("SELECT family, version, first_day, snapshot FROM cohorts WHERE status='active' "
                      "ORDER BY admitted_at, family, version").fetchall()
    for family, version, first_day, snapshot in rows:
        try:
            snap = json.loads(snapshot)
        except (TypeError, ValueError):
            continue
        if not isinstance(snap, dict) or not practice_current(snap.get("practice_evaluator"), research):
            continue
        evaluator = snap["practice_evaluator"]
        live = db.execute("SELECT first_day, last_day, sessions FROM practice WHERE family=? AND version=?",
                          (family, version)).fetchone()
        sessions = None
        if live is not None and str(live[0]) >= str(first_day):
            sessions = int(live[2] or 0) - int(str(live[1]) == before)
        closes, pnl = db.execute("SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM trades WHERE family=? AND version=? "
                                 "AND evaluator=? AND forced=0 AND exit_day < ?",
                                 (family, version, evaluator, before)).fetchone()
        out.append({"family": str(family), "version": int(version), "first_day": str(first_day),
                    "run_sha": snap.get("run_sha"), "evaluator": evaluator, "sessions": sessions,
                    "closes_program": int(closes or 0), "pnl_program": float(pnl or 0.0)})
    return out


# ---------------------------------------------------------------------------------------------------- 1. the mark
def eligible_train_run(store: SwarmStore, fam: Mapping[str, Any], n: int, evaluator: Mapping[str, Any]) -> dict[str, Any] | None:
    """Version `n`'s newest eligible Train run (`train_eligible`, completed, at the normal spread) over the running Train
    span under `evaluator` (`evaluator.row_matches`), or None."""
    from .evaluator import row_matches

    span = running_span(store)
    for row in store.version_runs(fam["id"], int(n), window="train", stress=1.0, limit=20):
        if row.get("status") != "ok" or (row.get("summary") or {}).get("train_eligible") is not True:
            continue
        if row_span(row) == span and row_matches(store, row, evaluator):
            return row
    return None


def mark_of(store: SwarmStore, fam: Mapping[str, Any], n: int, settings: Mapping[str, Any], *, evaluator: Mapping[str, Any],
            objective: Any, clock: Callable[[], float] = time.time) -> tuple[dict[str, Any] | None, str, bool]:
    """(the mark, why not, drop): version `n`'s Train and drift mark (the module docstring) when every condition holds,
    else None with the reason. `drop` is True when an existing mark must go: the version failed for good (demoted, a
    loss at 1.5x, a known failed drift screen, the gate's bar). Figures only owed never drop a mark. The drift screen is
    the incubator's own (`screen_verdict`): the tournament's while it is on, else the screen at its defaults and at the
    owner's stricter thresholds. A DIRECTION family is marked by its lane's bar instead (`_direction_mark`)."""
    state = fam.get("state") or {}
    if demoted(state, n):
        return None, "demoted (a loss at 1.5x or a failed drift screen)", True
    robust = robust_at_stress(state, n)
    if robust is False:
        return None, "its 1.5x Train run lost money", True
    bar = gate_bar(store, fam, n)
    if bar is not None:
        return None, f"barred by the gate: {bar}", True
    if robust is None:
        return None, "its 1.5x Train run has not landed", False
    stressed = ((state.get("robustness") or {}).get(str(n)) or {}).get("stress_1.5") or {}
    from .evaluator import matches

    if ("gym_image" in stressed or "gym_bundle" in stressed) and not matches(stressed, evaluator):
        return None, "its 1.5x Train run is another evaluator's", False
    run = eligible_train_run(store, fam, n, evaluator)
    if run is None:
        return None, "no eligible Train run under the current evaluator", False
    if dlane.lane_of(store, fam, settings) == dlane.DIRECTION:  # release D-1: the lane's bar, not the drift screen alone
        return _direction_mark(store, fam, n, settings, run=run, evaluator=evaluator, objective=objective,
                               robust_pnl=stressed.get("pnl"), clock=clock)
    screen = screen_verdict(store, fam, n, settings)
    if screen is None or not screen["known"]:
        return None, "its drift figures are owed", False
    if not screen["passed"]:
        return None, f"it fails the drift screen: {screen['why']}", True
    t = screen.get("t")
    return {"evaluator": dict(evaluator), "objective": objective, "run": str(run["run_id"]),
            "robust_pnl": round(float(stressed["pnl"]), 2),
            "drift": {"t": None if t is None else round(float(t), 4), "positive": int(screen.get("positive") or 0),
                      "years": int(screen.get("years") or 0)},
            "at": float(clock())}, "", False


def _direction_mark(store: SwarmStore, fam: Mapping[str, Any], n: int, settings: Mapping[str, Any], *,
                    run: Mapping[str, Any], evaluator: Mapping[str, Any], objective: Any, robust_pnl: Any,
                    clock: Callable[[], float]) -> tuple[dict[str, Any] | None, str, bool]:
    """THE DIRECTION LANE'S MARK (release D-1, Oct 9, 2026; PLAN D5, HARNESS C7): `mark_of` for a family whose lane is
    "direction", once the conditions every mark shares hold (not demoted, a profit at 1.5x, no bar of the gate's, the
    1.5x run and an eligible Train run under the current evaluator). In place of the drift screen alone, the lane's own
    bar, direction-v2 (`dlane.lane_verdict`): E1, E3, E4 and E5 on that eligible Train run (E5 priced at today's closes
    and equity), P1, R2 and R3 on the version's 1.5x run.
    - No mark while the lane takes none (`dlane.candidates_open`: "shadow", or K5 holding a "gate" lane in shadow): a mark
      already made stays (only the live side's reader, `bands.incubator`, refuses it meanwhile), and none is dropped.
    - Figures owed (`known` False) never drop a mark; a known failure of E1, E3, E4 or a 1.5x rule drops it (the same
      program fails them again); an E5 failure is today's prices', so it never drops one.
    - The mark is the alpha mark's shape plus `lane` "direction", `bar` (the objective's name) and `direction` (its
      figures, operator-only). Its `drift` keeps the drift screen's figures, REPORTED (the live side's reader checks only
      that it is a mapping): {"known": False} when they are owed, which here holds nothing up.
    LOOSENING of the owner's Sept 29-30 term "pass the drift screen alone", under the bypass-earlier-rules grant of Oct 3,
    for the direction lane only (the alpha lane's mark is unchanged). Its cost (PLAN D5): with no edge, about -$36 a week
    expected; at most $150 a week of the incubator's own envelope; its closes are never evidence."""
    if not dlane.candidates_open(store, settings):
        return None, "the direction lane takes no incubator mark while it is in shadow (dlane.mode, or K5)", False
    verdict = dlane.lane_verdict(store, fam, n, settings, run=run)
    if not verdict["known"]:
        return None, f"its direction figures are owed: {verdict['why']}", False
    if not verdict["passed"]:
        return None, f"it fails the direction lane's bar: {verdict['why']}", bool(verdict["drop"])
    screen = screen_verdict(store, fam, n, settings)
    if screen is not None and screen["known"]:
        t = screen.get("t")
        drift = {"t": None if t is None else round(float(t), 4), "positive": int(screen.get("positive") or 0),
                 "years": int(screen.get("years") or 0), "passed": bool(screen["passed"]), "reported": True}
    else:
        drift = {"known": False, "reported": True}
    score, robust = verdict.get("score") or {}, verdict.get("robust") or {}
    unit = score.get("unit") or {}
    return {"evaluator": dict(evaluator), "objective": objective, "run": str(run["run_id"]),
            "robust_pnl": round(float(robust_pnl), 2), "drift": drift, "lane": dlane.DIRECTION, "bar": dlane.OBJECTIVE,
            "direction": {"score": score.get("score"), "active": list(score.get("active") or []),
                          "unit": {k: unit.get(k) for k in ("scaled_usd", "cap_usd", "verdict")},
                          "t_pool_15": robust.get("t_pool_15"), "ratio": robust.get("ratio"),
                          "reported": {**dict(score.get("reported") or {}), **dict(robust.get("reported") or {})}},
            "at": float(clock())}, "", False


def _kept(marks: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted((k for k in marks if str(k).isdigit()), key=int)[-MARKS_KEPT:]
    return {k: marks[k] for k in keys}


def sweep(store: SwarmStore, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time) -> dict[str, list[str]]:
    """THE SWEEP (the module docstring, 1), over every alive family, whatever its band or its cohort's status: a mark goes
    when its version is demoted or lost at 1.5x, or when its program is barred (`gate_bar`) (an off tournament screen
    takes no mark: the mark's screen is the incubator's own, `screen_verdict`); a family's `gate_outcome` naming a
    program refused, failed, demoted or held, and its gate `review` failing a program or unreadable for it, are recorded
    in `incubator_barred` (`unrecorded_bars`: so the bar outlives either moving on); a passed incubator review of a
    program barred by name becomes verdict "fail", stage "gate". It only removes and records bars: it never writes a
    mark or a pass, nor anything the gate, validation or the bands read. Returns {"removed": ["family@version"],
    "barred": ["family:sha12"], "revoked": ["family@version"]}; anything done is one private `swarm.gate` event
    (`incubator_sweep`)."""
    out: dict[str, list[str]] = {"removed": [], "barred": [], "revoked": []}
    looks: list[dict[str, Any]] | None = None
    why_of: dict[str, str] = {}
    for fam in store.families(alive=True):
        state = fam.get("state") or {}
        reviews = state.get("incubator_reviews")
        passed = isinstance(reviews, Mapping) and any(isinstance(r, Mapping) and r.get("verdict") == "pass"
                                                      for r in reviews.values())
        if not (state.get("train_passed") or unrecorded_bars(state) or passed):
            continue
        if looks is None:
            looks = store.looks()
        if not _swept(store, fam, looks, clock)[0]:
            continue  # nothing to remove: no write transaction is taken
        with store.atomic():  # read again under the store's lock, then written
            now = store.family(str(fam["id"])) or {}
            if not now or now.get("retired_at"):
                continue
            values, done, why = _swept(store, now, looks, clock)
            if values:
                store.set_state(str(fam["id"]), **values)
                for key in out:
                    out[key].extend(done[key])
                why_of.update(why)
    if any(out.values()):
        store.event("swarm.gate", None, {"action": "incubator_sweep", **out, "why": why_of})
    return out


def _swept(store: SwarmStore, fam: Mapping[str, Any], looks: list[dict[str, Any]],
           clock: Callable[[], float]) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, str]]:
    """One family's part of `sweep`: (the state values to write, {removed, barred, revoked}, why each mark goes)."""
    from .gate import run_sha

    fid = str(fam["id"])
    state = fam.get("state") or {}
    at = float(clock())
    marks = dict(state.get("train_passed") or {})
    raw = state.get("incubator_reviews")
    reviews = {k: dict(v) for k, v in raw.items() if isinstance(v, Mapping)} if isinstance(raw, Mapping) else {}
    values: dict[str, Any] = {}
    done: dict[str, list[str]] = {"removed": [], "barred": [], "revoked": []}
    why_of: dict[str, str] = {}
    new = unrecorded_bars(state)
    view = fam
    if new:  # every entry is kept, one that cannot be read too (it still bars its program: `gate_bar`)
        bars = {**dict(state.get("incubator_barred") or {}), **{sha: {"why": why, "at": at} for sha, why in new.items()}}
        values["incubator_barred"] = bars
        done["barred"].extend(f"{fid}:{sha[:12]}" for sha in new)
        view = {**fam, "state": {**state, "incubator_barred": bars}}
    refused = store.refusals(fid)

    def barred(n: int, sha: str | None = None, *, program_only: bool = False) -> str | None:
        if sha is None:
            version = store.version(fid, n)
            if version is None:
                return "its version cannot be read"
            sha = run_sha(version)
        return gate_bar(store, view, n, sha=sha, refused=refused, looks=looks, program_only=program_only)

    for key in list(marks):
        if not str(key).isdigit():
            continue
        n = int(key)
        if demoted(state, n):
            why = "demoted (a loss at 1.5x or a failed drift screen)"
        elif robust_at_stress(state, n) is False:
            why = "its 1.5x Train run lost money"
        else:
            bar = barred(n)
            why = None if bar is None else f"barred by the gate: {bar}"
        if why is not None:
            marks.pop(key)
            values["train_passed"] = marks
            done["removed"].append(f"{fid}@{n}")
            why_of[f"{fid}@{n}"] = why
    for sha, record in reviews.items():
        if record.get("verdict") != "pass" or record.get("version") is None:
            continue
        # For good: only a bar that names this program (never a family's record that cannot be read for a while).
        bar = barred(int(record["version"]), sha, program_only=True)
        if bar is not None:
            reviews[sha] = {**record, "verdict": "fail", "stage": "gate", "reasons": [bar], "revoked_at": at}
            values["incubator_reviews"] = reviews
            done["revoked"].append(f"{fid}@{int(record['version'])}")
    return values, done, why_of


def facts(store: SwarmStore, settings: Mapping[str, Any], root: str | Path | None = None, *,
          clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """THE TRAIN AND DRIFT MARKS (the module docstring, 1), for the tournament's hourly round, after THE SWEEP (`sweep`).
    Returns the round's account: {cohorts, marked, written, removed, waiting, barred, revoked} (written and removed as
    "family@version"). Writes no mark without a research evaluator and a Train objective in the store, or without a
    readable practice record."""
    from .evaluator import KEY

    out: dict[str, Any] = {"cohorts": 0, "marked": 0, "written": [], "removed": [], "waiting": 0}
    swept = sweep(store, settings, clock=clock)
    out.update(removed=list(swept["removed"]), barred=swept["barred"], revoked=swept["revoked"])
    evaluator, objective = store.get(KEY), store.get("train_objective")
    if not isinstance(evaluator, Mapping) or objective is None:
        out["skipped"] = "no research evaluator or Train objective in the store"
        return out
    cohorts = practice_cohorts(root if root is not None else store.root, research=evaluator, before=session_day(clock))
    out["cohorts"] = len(cohorts)
    for cohort in cohorts:
        fid, n = cohort["family"], int(cohort["version"])
        fam = store.family(fid)
        if fam is None or fam.get("retired_at") or fam.get("band") != "gym":
            continue
        state = fam.get("state") or {}
        marks = dict(state.get("train_passed") or {})
        mark, _, drop = mark_of(store, fam, n, settings, evaluator=evaluator, objective=objective, clock=clock)
        if mark is None:
            if drop and str(n) in marks:
                marks.pop(str(n))
                changed = "removed"
            else:
                out["waiting"] += 1
                continue
        elif current_mark(marks.get(str(n)), evaluator, objective):
            out["marked"] += 1
            continue
        else:
            marks[str(n)] = mark
            changed = "written"
        expect = {key: state.get(key) for key in ("robust_failed", "drift_failed", "train_passed")}
        with store.atomic():
            now = store.family(fid) or {}
            if now.get("retired_at") or now.get("band") != "gym":
                continue
            if changed == "written" and gate_bar(store, now, n) is not None:
                continue  # a verdict against it landed since `mark_of` read the family (a row, `review`, a recorded bar)
            done = store.compare_and_set_state(fid, expect, train_passed=_kept(marks))
        if done:
            out[changed].append(f"{fid}@{n}")
            if changed == "written":
                out["marked"] += 1
    return out


# ---------------------------------------------------------------------------------------------------- 3. the re-runs
#: The Gym's final answers to a Train run (the program's answer: run again on the same span and evaluator, it says the
#: same). A row of status "error" or "failed" is none: the Gym could not finish it.
ANSWERED = ("ok", "disqualified", "no_data", "refused")


def train_answer(store: SwarmStore, fam: Mapping[str, Any], n: int, evaluator: Mapping[str, Any]) -> str | None:
    """Version `n`'s Train answer over the running Train span under `evaluator`: "eligible" (`eligible_train_run`),
    "ineligible" (a scored run that is not eligible, or the Gym's final answer: disqualified, no data, refused), or None
    (none yet: its Train run is owed)."""
    from .evaluator import row_matches

    if eligible_train_run(store, fam, n, evaluator) is not None:
        return "eligible"
    span = running_span(store)
    for row in store.version_runs(fam["id"], int(n), window="train", stress=1.0, limit=20):
        if row.get("status") not in ANSWERED or row_span(row) != span or not row_matches(store, row, evaluator):
            continue
        summary = row.get("summary") or {}
        if row.get("status") != "ok" or summary.get("train_eligible") is False:
            return "ineligible"
    return None


def owed_runs(store: SwarmStore, settings: Mapping[str, Any], root: str | Path | None = None, *,
              clock: Callable[[], float] = time.time) -> list[dict[str, Any]]:
    """THE RE-RUNS' list (the module docstring, 3): each active, current cohort's version in an alive Gym family with no
    current mark whose mark waits only on Gym runs, oldest cohort first: [{family, version, train, drift, robust, next,
    why}] (`train`: its Train run over the running span is owed; `drift`: its figures are owed while a Train answer is
    in; `robust`: its 1.5x run has not landed; `next`: the first of those in `RERUN_ORDER`, the one run to ask for now;
    `why`: `mark_of`'s reason). [] without a research evaluator and Train objective or a readable practice record.
    Read-only."""
    from .evaluator import KEY
    from .gate import run_sha
    from .researcher import version_drift

    evaluator, objective = store.get(KEY), store.get("train_objective")
    if not isinstance(evaluator, Mapping) or objective is None:
        return []
    out = []
    for cohort in practice_cohorts(root if root is not None else store.root, research=evaluator, before=session_day(clock)):
        fid, n = cohort["family"], int(cohort["version"])
        fam = store.family(fid)
        if fam is None or fam.get("retired_at") or fam.get("band") != "gym":
            continue
        state = fam.get("state") or {}
        if current_mark((state.get("train_passed") or {}).get(str(n)), evaluator, objective):
            continue
        if (state.get("validation_line") or {}).get("passed") and state.get("validation_version"):
            continue  # D2's route: the House's reader never admits it to the incubator (`bands.incubator`)
        mark, why, drop = mark_of(store, fam, n, settings, evaluator=evaluator, objective=objective, clock=clock)
        if mark is not None or drop:
            continue  # marked at this round's `facts`, or failed for good (demoted, a loss at 1.5x, the screen, a bar)
        version = store.version(fid, n)
        if version is None or not version.get("code") or cohort["run_sha"] != run_sha(version):
            continue  # the cohort practises another program than this version's
        answer = train_answer(store, fam, n, evaluator)
        if answer == "ineligible":
            continue  # the Gym's answer over this span is in: it can never be marked under it
        # A direction family's mark is its lane's bar, not the drift screen (release D-1, `_direction_mark`): `mark_of`'s
        # drop above already says when it failed for good.
        screen = screen_verdict(store, fam, n, settings) if dlane.lane_of(store, fam, settings) != dlane.DIRECTION else None
        if screen is not None and screen["known"] and not screen["passed"]:
            continue  # its figures over this span are in and fail the screen (`mark_of` reads its 1.5x run first)
        owed = {"train": answer is None, "drift": answer is not None and version_drift(store, fam, n) is None,
                "robust": robust_at_stress(state, n) is None}
        if any(owed.values()):
            step = next(label for label, key in zip(RERUN_ORDER, ("train", "drift", "robust")) if owed[key])
            out.append({"family": fid, "version": n, **owed, "next": step, "why": why})
    return out


def reruns(store: SwarmStore, settings: Mapping[str, Any], researcher: Any, root: str | Path | None = None, *,
           clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """THE RE-RUNS (the module docstring, 3): for each of `owed_runs`, its `next` run queued through
    `researcher.queue_incubator_runs`, unless this process has one of its jobs in flight (`researcher._incubator`, until
    `_settled` releases it) or it is spent (`RERUN_ATTEMPTS` executed failures under this Train objective and evaluator,
    or its run's own cap, `researcher.ROBUSTNESS_ATTEMPTS`). Returns {"owed": n, "queued": [...], "waiting": [...],
    "spent": [...], "jobs": {name: [run]}} ("family@version": queued now; in flight, the re-runs' or the researcher's own;
    spent), {} when nothing is owed. One private `swarm.robustness` event (`incubator_reruns`) when anything was queued,
    and one alert the first time a version is spent (`swarm.status` `incubator_reruns_spent`)."""
    from .evaluator import KEY
    from .researcher import ROBUSTNESS_ATTEMPTS

    rows = owed_runs(store, settings, root, clock=clock)
    if not rows:
        return {}
    evaluator, objective = dict(store.get(KEY)), store.get("train_objective")
    inflight = getattr(researcher, "_incubator", None)
    if not isinstance(inflight, dict):
        inflight = {}
        researcher._incubator = inflight
    lock = getattr(researcher, "_incubator_lock", None)
    if lock is None:
        lock = researcher._incubator_lock = threading.Lock()
    out: dict[str, Any] = {"owed": len(rows), "queued": [], "waiting": [], "spent": []}
    for row in rows:
        fid, n, step = row["family"], int(row["version"]), row["next"]
        name = f"{fid}@{n}"
        key = (fid, n, dumps(objective), dumps(evaluator))
        with lock:
            busy = bool(inflight.get(key))
        if busy:
            out["waiting"].append(name)
            continue
        record = _record(store, fid, n, objective, evaluator)
        tries = (((((store.family(fid) or {}).get("state") or {}).get("robustness") or {}).get(str(n)) or {})
                 .get("failures") or {}).get(step) if step != "train" else None
        if int(record.get("failures") or 0) >= RERUN_ATTEMPTS or int(tries or 0) >= ROBUSTNESS_ATTEMPTS:
            out["spent"].append(name)
            if not record.get("alerted"):
                _note(store, fid, n, objective, evaluator, clock, alerted=True)
                store.event("swarm.status", fid, {
                    "action": "incubator_reruns_spent", "alert": True, "version": n, "run": step,
                    "failures": int(record.get("failures") or 0), "objective": objective,
                    "text": f"the incubator's re-runs of {name} are spent ({step} failed): its cohort cannot be marked "
                            "under this Train objective and Gym image"})
            continue
        with lock:
            inflight[key] = {step}  # before the submit: a job that fails at once releases it (`_settled`)

        def settled(label: str, result: Mapping[str, Any], key: tuple = key, fid: str = fid, n: int = n) -> None:
            _settled(store, researcher, key, fid, n, label, result, objective=objective, evaluator=evaluator, clock=clock)

        try:
            queued = researcher.queue_incubator_runs(fid, n, step, settled=settled)
        except Exception:
            with lock:
                inflight.pop(key, None)
            raise
        if not queued:
            with lock:
                if inflight.get(key) == {step}:
                    inflight.pop(key, None)  # nothing queued: in flight as the researcher's own, or retired; asked again
            out["waiting"].append(name)
            continue
        _note(store, fid, n, objective, evaluator, clock, run=step)
        out["queued"].append(name)
        out.setdefault("jobs", {})[name] = list(queued)
    if out["queued"]:
        store.event("swarm.robustness", None, {"action": "incubator_reruns", **out})
    return out


def _settled(store: SwarmStore, researcher: Any, key: tuple, fid: str, n: int, label: str, result: Mapping[str, Any], *,
             objective: Any, evaluator: Mapping[str, Any], clock: Callable[[], float]) -> None:
    """A re-run's job landed or failed (on the pool's dispatcher thread, after the researcher recorded it): it leaves this
    process's in-flight set, and when the Gym RAN it and the version still has no answer for it under `evaluator` (a
    failure, an error, or a result of another span or image), one executed failure is counted (`RERUNS_KEY`). A job
    that never ran (superseded, retired, abandoned, cancelled: `researcher.NOT_RUN`) charges nothing."""
    from .researcher import NOT_RUN, landed

    lock = getattr(researcher, "_incubator_lock", None)
    inflight = getattr(researcher, "_incubator", None)
    if lock is not None and isinstance(inflight, dict):
        with lock:
            left = inflight.get(key)
            if left is not None:
                left.discard(label)
                if not left:
                    inflight.pop(key, None)
    failed = result.get("status") == "failed"
    reason = str(result.get("reason") or "")
    if failed and any(word in reason for word in NOT_RUN):
        return
    fam = store.family(fid) or {}
    if not fam or fam.get("retired_at"):
        return
    if label == "train":
        answered = train_answer(store, fam, n, evaluator) is not None
    else:
        row = (((fam.get("state") or {}).get("robustness") or {}).get(str(n)) or {}).get(label)
        answered = landed(row)
    if answered:
        return
    _note(store, fid, n, objective, evaluator, clock, failed=True)
    store.event("swarm.robustness", fid, {"version": int(n), "action": "incubator_rerun_failed", "run": label,
                                          "why": (reason or str(result.get("status") or ""))[:200]})


def _record(store: SwarmStore, fid: str, n: int, objective: Any, evaluator: Mapping[str, Any]) -> dict[str, Any]:
    """Version `n`'s re-runs record under this Train objective and evaluator (`RERUNS_KEY`), {} without one or for one of
    another objective or evaluator. A failure count that cannot be read counts as spent (fail-closed: no more Gym spend
    on it)."""
    raw = ((store.family(fid) or {}).get("state") or {}).get(RERUNS_KEY)
    record = raw.get(str(n)) if isinstance(raw, Mapping) else None
    if not isinstance(record, Mapping) or record.get("objective") != objective or record.get("evaluator") != evaluator:
        return {}
    failures = record.get("failures", 0)
    ok = isinstance(failures, int) and not isinstance(failures, bool) and failures >= 0
    return {**dict(record), "failures": failures if ok else RERUN_ATTEMPTS}


def _note(store: SwarmStore, fid: str, n: int, objective: Any, evaluator: Mapping[str, Any], clock: Callable[[], float], *,
          run: str | None = None, failed: bool = False, alerted: bool = False) -> None:
    """Writes version `n`'s re-runs record (`RERUNS_KEY`, the newest `RERUNS_KEPT` versions): a queueing (`run`), an
    executed failure, or the spent alert, under the store's transaction. A retired family is left alone."""
    with store.atomic():
        fam = store.family(fid) or {}
        if not fam or fam.get("retired_at"):
            return
        raw = (fam.get("state") or {}).get(RERUNS_KEY)
        records = {k: dict(v) for k, v in raw.items() if isinstance(v, Mapping)} if isinstance(raw, Mapping) else {}
        record = {"objective": objective, "evaluator": dict(evaluator), "failures": 0, "queued": 0,
                  **_record(store, fid, n, objective, evaluator)}
        record["at"] = float(clock())
        if run is not None:
            record.update(run=run, queued=int(record.get("queued") or 0) + 1)
        if failed:
            record["failures"] = int(record["failures"]) + 1
        if alerted:
            record["alerted"] = True
        records[str(n)] = record
        keep = sorted(records, key=lambda k: (float(records[k].get("at") or 0.0), k))[-RERUNS_KEPT:]
        store.set_state(fid, **{RERUNS_KEY: {k: records[k] for k in keep}})


# ---------------------------------------------------------------------------------------------------- 2. the reviews
def due_reviews(store: SwarmStore, settings: Mapping[str, Any], root: str | Path | None = None, *,
                clock: Callable[[], float] = time.time) -> list[dict[str, Any]]:
    """The versions that need an incubator review (the module docstring, 2), oldest cohort first: [{family, version, sha,
    sessions, closes}]. [] without a research evaluator and Train objective, without a current mark on any alive Gym
    family (the practice record is not read then), or without a readable practice record."""
    from .evaluator import KEY
    from .gate import run_sha

    evaluator, objective = store.get(KEY), store.get("train_objective")
    if not isinstance(evaluator, Mapping) or objective is None:
        return []
    marked = {fam["id"]: fam for fam in store.families(alive=True) if fam.get("band") == "gym"
              and any(current_mark(m, evaluator, objective) for m in ((fam.get("state") or {}).get("train_passed") or {}).values())}
    if not marked:
        return []
    out = []
    looks = store.looks()
    for cohort in practice_cohorts(root if root is not None else store.root, research=evaluator, before=session_day(clock)):
        fam = marked.get(cohort["family"])
        if fam is None:
            continue
        n, state = int(cohort["version"]), fam.get("state") or {}
        if state.get("gate_hold") or demoted(state, n):
            continue  # the operator holds it (no paid stage), or it failed for good
        if not current_mark((state.get("train_passed") or {}).get(str(n)), evaluator, objective):
            continue
        sessions, closes = cohort["sessions"], cohort["closes_program"]
        if sessions is None or sessions < REVIEW_MIN_SESSIONS or closes < REVIEW_MIN_CLOSES or not cohort["pnl_program"] > 0:
            continue
        version = store.version(fam["id"], n)
        if version is None or not version.get("code"):
            continue
        sha = run_sha(version)
        if cohort["run_sha"] != sha:
            continue  # the cohort practises another program than this version's
        if final_review(state, sha) is not None or gate_bar(store, fam, n, sha=sha, looks=looks) is not None:
            continue  # final for its program; the gate's bar too (the live side never admits it: no review is paid)
        if state.get("gate_ready") and state.get("validation_version") == n:
            continue  # the gate is reviewing this very version now: its review and audit serve
        out.append({"family": fam["id"], "version": n, "sha": sha, "sessions": sessions, "closes": closes,
                    "first_day": cohort["first_day"]})
    out.sort(key=lambda r: (r["first_day"], r["family"], r["version"]))
    return out


def reviewable(store: SwarmStore, fid: str, n: int, sha: str) -> bool:
    """Before each paid stage: the family is alive in the Gym band, not held by the operator, version `n` is not demoted,
    its mark is current, its program is still `sha`, the gate has not barred it, and the gate is not reviewing this very
    version (its own review and audit then serve)."""
    from .evaluator import KEY
    from .gate import run_sha

    fam = store.family(fid) or {}
    state = fam.get("state") or {}
    if fam.get("retired_at") or fam.get("band") != "gym" or state.get("gate_hold") or demoted(state, n):
        return False
    if state.get("gate_ready") and state.get("validation_version") == n:
        return False
    if not current_mark((state.get("train_passed") or {}).get(str(n)), store.get(KEY), store.get("train_objective")):
        return False
    version = store.version(fid, n)
    if version is None or not version.get("code") or run_sha(version) != sha:
        return False
    return gate_bar(store, fam, n, sha=sha) is None


def put_review(store: SwarmStore, fid: str, sha: str, record: Mapping[str, Any], *,
               clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """Record program `sha`'s incubator review in its family's state, keeping the newest `REVIEWS_KEPT`, and return the
    record kept. A failed review or audit is recorded as the program's bar in the same transaction (THE VERDICT FIRST,
    `record_bar`), so the trim never drops the verdict: it is final for that program. A pass of a program already
    barred by name (`incubator_barred`: a verdict that landed while this read was in flight) is kept as the sweep's
    revoked record (verdict "fail", stage "gate"), never written over it as a pass."""
    why = verdict_bar(record, "the incubator's")
    with store.atomic():
        state = (store.family(fid) or {}).get("state") or {}
        records = {k: v for k, v in dict(state.get("incubator_reviews") or {}).items() if isinstance(v, Mapping)}
        kept = dict(record)
        recorded = state.get("incubator_barred")
        if why is None and kept.get("verdict") == "pass" and isinstance(recorded, Mapping) and sha in recorded:
            entry = recorded[sha]
            bar = str(entry.get("why") or "the gate barred it") if isinstance(entry, Mapping) else "the gate barred it"
            kept.update(verdict="fail", stage="gate", reasons=[bar], revoked_at=float(clock()))
        records[sha] = kept
        keep = sorted(records, key=lambda k: (float(records[k].get("at") or 0.0), k))[-REVIEWS_KEPT:]
        store.set_state(fid, incubator_reviews={k: records[k] for k in keep})
        if why is not None:
            done, why_of = _record_bar(store, fid, sha, why, record.get("version"), clock)
    if why is not None:
        _bar_event(store, fid, sha, why, record.get("version"), done, why_of)
    return kept


__all__ = ["facts", "sweep", "due_reviews", "practice_cohorts", "practice_current", "current_mark", "final_review",
           "mark_of", "gate_bar", "gate_review_bar", "incubator_review_bar", "family_bar", "unrecorded_bars", "verdict_bar",
           "record_verdict", "record_bar", "BAD_OUTCOMES", "twins", "program_bar", "owed_audit_bar", "adoption_bars",
           "save_owed", "load_owed", "backfill", "BACKFILL_KEY",
           "eligible_train_run", "reviewable", "put_review", "reviews_per_round", "screen_settings", "session_day",
           "owed_runs", "reruns", "train_answer", "screen_verdict", "RERUNS_KEY", "RERUNS_KEPT", "RERUN_ATTEMPTS",
           "RERUN_ORDER", "ANSWERED", "MARKS_KEPT",
           "REVIEWS_KEPT", "REVIEW_MIN_SESSIONS", "REVIEW_MIN_CLOSES", "REVIEWS_PER_ROUND", "REVIEWS_CEILING", "OBSERVE_FILE"]
