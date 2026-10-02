"""The incubator's swarm facts (release B2, Sept 30, 2026): what research records for the House's incubator route to read.

THE ROUTE. The owner approved the incubator on Sept 29, 2026, and its reading was settled on Sept 30. It is a
shadow-to-real route for families that pass Train, pass the drift screen alone and show positive live practice. It
trades one lot of an approved real structure, at most $50 maximum loss each. Its trades are never strategy evidence and
never a promotion: D2 is the only route to Probe and Sized. Every money rule of the route lives in the House
(`league/live`, the constitution's `options_money.incubator` row). The swarm records only the two facts below, in the
family's state. Each is bound to the evaluator it was made under, so no stale fact can pass.

1. THE TRAIN AND DRIFT MARK (`facts`, called by the tournament's hourly round after validation). For version `n` of an
   alive Gym-band family that holds an active practice cohort under the current evaluator, it writes
   `train_passed[str(n)] = {evaluator, objective, run, robust_pnl, drift: {t, positive, years}, at}` when ALL of these hold:
   - an eligible Train run of `n` (`train_eligible`) over the running Train span, under the current research evaluator;
   - its 1.5x Train robustness run landed with a profit (`researcher.robust_at_stress`);
   - it was not demoted (`bands.demoted`: a loss at 1.5x, or a failed drift screen);
   - THE DRIFT SCREEN is on, knows its figures and passes them (`researcher.drift_verdict`);
   - THE GATE HAS NOT BARRED ITS PROGRAM (`gate_bar`, below).
   `evaluator` is the store's `research_evaluator` and `objective` its `train_objective`, both as the mark was made. The
   live side (`bands.incubator`) accepts a mark only while both still equal the store's, because an evaluator adoption
   clears alive families only. The mark is written with a compare-and-set on the version's `robust_failed`,
   `drift_failed` and `train_passed` as read, so a demotion landing meanwhile wins. The newest `MARKS_KEPT` marks are
   kept per family. No Gym run is queued here: a version whose 1.5x run never landed stays unmarked (fail-closed).

   A MARK GOES when its version is demoted or lost at 1.5x, when the gate bars its program, or when the drift screen is
   switched off (an off screen never passes: the mark is made again once the screen is on and passes): with the
   verdict itself (THE VERDICT FIRST, below; `researcher.demote_version`), and by `sweep` (at the start of `facts`, and
   at the start and the end of every gate round, the leakage alarm's too). A mark is never removed while figures are
   only owed.

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
import time
from pathlib import Path
from typing import Any, Callable, Mapping

# BAD_OUTCOMES: the gate's outcomes that bar a program, the House's reader's own list (`bands.BAD_OUTCOMES`), so the two can
# never disagree: refused, failed, demoted and held (THE LOOK HOLDS, Oct 2, 2026).
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
    from ..gym.review_contract import review_contract

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
    from ..gym.review_contract import review_contract

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
    # builds on it). The drift screen is the sweep's own business: `screen_on` here only keeps its marks for it.
    swept, done, why_of = _swept(store, view, True, store.looks(), clock)
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
    loss at 1.5x, a known failed drift screen, the gate's bar) or the drift screen is off. Figures only owed never drop
    a mark."""
    state = fam.get("state") or {}
    if demoted(state, n):
        return None, "demoted (a loss at 1.5x or a failed drift screen)", True
    robust = robust_at_stress(state, n)
    if robust is False:
        return None, "its 1.5x Train run lost money", True
    bar = gate_bar(store, fam, n)
    if bar is not None:
        return None, f"barred by the gate: {bar}", True
    if drift_settings(settings) is None:
        return None, "the drift screen is off (an off screen never passes)", True
    if robust is None:
        return None, "its 1.5x Train run has not landed", False
    stressed = ((state.get("robustness") or {}).get(str(n)) or {}).get("stress_1.5") or {}
    from .evaluator import matches

    if ("gym_image" in stressed or "gym_bundle" in stressed) and not matches(stressed, evaluator):
        return None, "its 1.5x Train run is another evaluator's", False
    run = eligible_train_run(store, fam, n, evaluator)
    if run is None:
        return None, "no eligible Train run under the current evaluator", False
    screen = drift_verdict(store, fam, n, settings)
    if screen is None:
        return None, "the drift screen is off (an off screen never passes)", True
    if not screen["known"]:
        return None, "its drift figures are owed", False
    if not screen["passed"]:
        return None, f"it fails the drift screen: {screen['why']}", True
    t = screen.get("t")
    return {"evaluator": dict(evaluator), "objective": objective, "run": str(run["run_id"]),
            "robust_pnl": round(float(stressed["pnl"]), 2),
            "drift": {"t": None if t is None else round(float(t), 4), "positive": int(screen.get("positive") or 0),
                      "years": int(screen.get("years") or 0)},
            "at": float(clock())}, "", False


def _kept(marks: Mapping[str, Any]) -> dict[str, Any]:
    keys = sorted((k for k in marks if str(k).isdigit()), key=int)[-MARKS_KEPT:]
    return {k: marks[k] for k in keys}


def sweep(store: SwarmStore, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time) -> dict[str, list[str]]:
    """THE SWEEP (the module docstring, 1), over every alive family, whatever its band or its cohort's status: a mark goes
    when its version is demoted or lost at 1.5x, when its program is barred (`gate_bar`), or, every mark, while the
    drift screen is off; a family's `gate_outcome` naming a program refused, failed, demoted or held, and its gate `review`
    failing a program or unreadable for it, are recorded in `incubator_barred` (`unrecorded_bars`: so the bar outlives
    either moving on); a passed incubator review of a program barred by name becomes verdict "fail", stage "gate". It
    only removes and records bars: it never writes a mark or a pass, nor anything the gate, validation or the bands
    read. Returns {"removed": ["family@version"], "barred": ["family:sha12"], "revoked": ["family@version"]}; anything
    done is one private `swarm.gate` event (`incubator_sweep`)."""
    out: dict[str, list[str]] = {"removed": [], "barred": [], "revoked": []}
    screen_on = drift_settings(settings) is not None
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
        if not _swept(store, fam, screen_on, looks, clock)[0]:
            continue  # nothing to remove: no write transaction is taken
        with store.atomic():  # read again under the store's lock, then written
            now = store.family(str(fam["id"])) or {}
            if not now or now.get("retired_at"):
                continue
            values, done, why = _swept(store, now, screen_on, looks, clock)
            if values:
                store.set_state(str(fam["id"]), **values)
                for key in out:
                    out[key].extend(done[key])
                why_of.update(why)
    if any(out.values()):
        store.event("swarm.gate", None, {"action": "incubator_sweep", **out, "why": why_of})
    return out


def _swept(store: SwarmStore, fam: Mapping[str, Any], screen_on: bool, looks: list[dict[str, Any]],
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
        elif not screen_on:
            why = "the drift screen is off (an off screen never passes)"
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
           "eligible_train_run", "reviewable", "put_review", "reviews_per_round", "session_day", "MARKS_KEPT",
           "REVIEWS_KEPT", "REVIEW_MIN_SESSIONS", "REVIEW_MIN_CLOSES", "REVIEWS_PER_ROUND", "REVIEWS_CEILING", "OBSERVE_FILE"]
