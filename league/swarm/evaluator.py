"""Adopt an evaluator without transferring old selection evidence or erasing search history.

Run identities already include the Gym bundle, but family bests/robustness used to outlive that
identity. This module scopes those materialized views too. Historical runs, trials, looks, versions,
notebooks and forward records remain untouched. A stale money band returns to the Gym for fresh
qualification; its frozen live instances retain their close path. A stale band is not entry authority.

TWO KINDS OF ADOPTION (`adopt`, split on `gym_changed`; Oct 3, 2026). Only a change of the Gym itself (its image or
bundle, or no identity before) clears the research selection. A change of league/live alone moves the execution
fingerprint and leaves every Gym row current (`matches`: the same image and bundle answer the same), so the selection
those rows earned stands: the family's bests (`BEST_COLUMNS`) and the Gym's selection (`GYM_KEYS`), with the extension
hold's records and the idle and dormancy counts. Twice a league/live-only release cleared it anyway (Oct 1: the validated
families retired themselves on the "evaluator changed" note; Oct 3: every alive family's best went, and the practice
league was offered no program until each researcher happened to run its old best again). The owner's term for an
evidence reset is that practice restarts and the Gym's trials, lineages and looks are kept: so is its selection.

THE MONEY SIDE DOES NOT MOVE: NO REAL-ORDER ROUTE CARRIES ACROSS A LEAGUE/LIVE CHANGE. Either kind returns a money band
whose banded evaluator is stale to the Gym (`bands.current_banded_evaluator` pins the execution fingerprint: a band never
carries across a league/live change) and clears the live route's facts (`LIVE_KEYS`) of every alive family: the
incubator's marks and reviews, owed again under the new fingerprint, and the gate's `review` WHEN IT PASSED. A passing
review is a live-route fact, not kept Gym evidence (Oct 3, 2026). Beside a kept validation it is what `bands.read`
grants D2's execution tuition on (its Gym-band row: one-lot real orders, never evidence), and that row names no
execution fingerprint, so a kept pass would carry real orders across the change with nothing new asked of the program.
A league/live-only adoption therefore clears a passing review for every family, whether or not it ever held a band
(archived in the event), and the restoration never gives one back: after one, no validated family has a tuition row
until the gate has reviewed and audited its program again. Nothing else is reset for that; the gate's own rule decides
(`Gate.run`):

- a family at the gate (`gate_ready`, which is kept) is taken up at the gate's next round and, holding no review, is
  reviewed and audited again before anything else. What that asks is the router's: a paid route (Claude, OpenAI) reads
  the program anew; Sail's request key names the review contract, the family and the version, none of which a
  league/live change moves, so an answer Sail already gave for it is read again (`ModelRouter.sail`);
- a look in flight at the restart is owed again by the gate (`Gate.owe` gives the place back), behind the same review;
- a program the gate is done with (`gated_sha`: its look was made, or it was refused or held) is not taken up, and
  `Tournament.gate_spent` readies it no more, so it has no tuition row after the adoption. A returned band's program
  is one of these: its review kept, a stale band would have become one-lot real orders that nothing ends.

UNDER THE FAST LANE (release F1, Oct 3, 2026; this tree: `gate.SEALED_LOOKS` True, `bands.TUITION_ROWS` False) THE
SEALED LOOK IS THE ROUTE TO PROBE, and what this docstring says of the gate holds as it runs. After a league/live-only
adoption a gate-ready family holds no passing review, so the gate reviews and audits its program again and then makes
its ONE look; a look in flight at the restart was never recorded and is owed again; a program the gate is done with
(its look made, refused or held) is never taken up, and one whose review, audit or any refusal is on record in any
family is never read again at all (THE PROGRAM BAR, `Gate.program_bar`). A SPENT LOOK STAYS SPENT: the look rows, the
gate's mark, the lineage's ration, Holm's count and every bar outlive every adoption. A band a look earned returns to
the Gym at the adoption like any other (its proof pins the execution fingerprint), and its program gets NO second
look: until a later release gives such a band back on the same look after a fresh review, a look-earned band does not
survive a league/live or Gym release. Tuition stays retired (`bands.read` gives no Gym-band row), so what this
docstring says of a tuition row holds only on that retired read (`bands.read(tuition=True)`, its own tests), and no
real order follows from a kept or restored selection: the only real order a kept selection can lead to is a Probe's,
after the review, the audit and the look. The adoption's own rule is unchanged: a passing review is cleared and never
given back, and one that did not pass is kept (it costs its program its practice row, `bands.observe`, and the look
route for good). Evidence v3's own gate (`Gate(sealed_looks=False)`: a kept gate-ready version goes to practice with no
review, audit or look, `Gate._to_practice`) is reached by its own tests only.

A REVIEW THAT DID NOT PASS IS KEPT AS IT IS (`review_stands`; Oct 3, 2026): a failed review, a failed audit, and a
record that cannot be read as a pass. It grants no order under any reader (each asks for a pass with a passed audit),
and it is the gate's own memory that it failed the program: cleared, the gate would read that program again where it is
still at the gate, and practice would be offered it again (`bands.observe` gives no row to a program whose review
failed). A league/live change gives no program a second reading, so a league/live-only adoption leaves such a review
where it is, and the restoration gives one back with the selection the earlier adoption archived. (An adoption of a new
Gym clears the record with everything else, as before. The verdict stays: the program's bar and its refusal row are
kept, and THE PROGRAM BAR on the look route, release F1, refuses it on the new Gym too, with no second reading.)

Bars, refusals and looks are untouched (a verdict against a program that a review holds is recorded as its bar first,
whether the review is then kept or cleared: `incubator.adoption_bars`), and the House still ends every practice cohort
whose practice evaluator changed.

WHAT STANDS OF THE GATE. Its place (`gate_ready`), its mark that it is done with a program (`gated_sha`) and its outcome
(`gate_outcome`) are kept with the Gym's selection: they say where the Gym's evidence stands at the gate, and none of
them grants an order. A version that WAITS for the look's bar (release F1: the power hold is a wait, `gate.waiting`)
holds its place under the gate's own marker (`look_wait`), which is no selection key: no adoption archives, clears or
gives it back. It names a version and stands only with that version's kept validation, so after a league/live-only
adoption the version waits on as it did, and after an adoption of a new Gym (the validation cleared) it holds no place
until the tournament validates it again. Every reader of the kept validation line reads a verdict judged on the Gym in force, possibly
under an earlier execution fingerprint (`on_gym_in_force`): the line is Gym evidence, and what a route owes under the
new fingerprint is its own to ask for.

THE ONE-TIME RESTORATION (`restorable`). The release before this rule archived and cleared every selection at a
league/live-only adoption. At the next league/live-only adoption an alive family that holds no best, and nothing it
selected since, is given back what that adoption archived (`ARCHIVE_KEY`), exactly: its bests and the Gym's selection,
and a review of the gate that did not pass (`review_stands`). Not the live route's facts (a passing review among them:
no tuition row comes back with a selection), and not the idle, dormancy and stall counts, which that adoption
restarted without archiving them (they go on from its restart).
Nothing is given back where the archive is no longer the family's standing: the drift screen failed a version it selects
since, or Train's objective (its span) was chosen anew since. One thing was not archived and cannot be given back as it
was: a holdout look in flight at that adoption (its marker is no selection key, and that release's gate dropped it);
the gate place is then given back as the tournament's own rule sets it, so the review and the look are owed again and
nothing waits on a look that never comes.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

KEY = "research_evaluator"
SELECTION_KEYS = (
    "best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note",
    "robustness", "robust_failed", "robust_why", "drift_failed", "validation_version", "validation_image",
    "validation_bundle", "validation_line", "validation_view", "validation_numbers", "typical_max_loss_usd",
    "typical_by_version", "gate_ready", "review", "gated_sha", "gate_outcome",
    # The incubator's facts (release B2, `incubator.py`): its Train and drift marks and its reviews, evaluator-bound. Its
    # bars (`incubator_barred`: a failed review or audit, the gate's or the incubator's, a refusal, a bad outcome) are
    # NOT here: an adoption keeps them, so a bar is as durable as a refusal row for its program (the owner's term: a
    # program whose review or audit failed never trades the incubator).
    "train_passed", "incubator_reviews",
)
#: THE EXTENSION HOLD's records (`researcher.extension_held`): the hold a validation on the Gym earned, the versions held
#: (`extension_versions`, which a hold the operator cleared stays in), and the last hold cleared and lapsed. They are Gym
#: evidence: an adoption that changes the Gym (`gym_changed`) archives them with the selection and clears them, so a
#: version is held again only when it meets the checks on the new Gym, even one the operator cleared, whose 2017-19
#: extension verdict is then owed again under the new Gym before the operator clears it again.
HOLD_KEYS = ("extension_hold", "extension_versions", "extension_cleared", "extension_lapsed")
#: THE LIVE ROUTE'S FACTS: what an adoption clears even when the Gym did not change (`gym_changed` false: league/live
#: alone moved the execution fingerprint). The incubator's Train and drift marks name the evaluator they were made
#: under, so the live side reads them as stale either way (`incubator.current_mark`), and its reviews read a program for
#: the live route, whose code is what changed. The gate's `review` is one of them (Oct 3, 2026; the module docstring):
#: beside a kept validation a PASSING one is what `bands.read` grants a tuition row on (one-lot real orders), so every
#: family owes it again after a league/live change, and the gate asks for it by its own rule. No real-order route
#: carries across one. A review that did not pass is the one thing under these keys that such an adoption leaves as it
#: is (`review_stands`): it grants nothing, and clearing it would give its program a second reading.
LIVE_KEYS = ("train_passed", "incubator_reviews", "review")
#: THE GYM'S SELECTION: every other key of `SELECTION_KEYS`. Gym evidence on one image and bundle (the Train best and its
#: candidates, a submission, the robustness and drift marks, the validation and its sizing), and where that evidence
#: stands at the gate (`gate_ready`, `gated_sha`, `gate_outcome`: its place, the gate's mark that it is done with a
#: program, and its outcome; none of them grants an order). The same image and bundle answer the same, so a
#: league/live-only adoption keeps it.
GYM_KEYS = tuple(key for key in SELECTION_KEYS if key not in LIVE_KEYS)
#: The family's own columns that hold its bests: archived and cleared with the selection when the Gym changes, kept
#: with it otherwise.
BEST_COLUMNS = ("best_train", "best_version", "best_validation", "validated_version")
#: Where an adoption that clears the selection keeps what it cleared, in the family's state (its event's
#: `_previous_selection` holds the same): the latest such adoption's only, each one replacing the one before.
ARCHIVE_KEY = "previous_evaluator_selection"
#: The action of the event an adoption writes for each alive family (`researcher.ADOPTED_ACTION` reads it).
ADOPTED = "evaluator_adopted"


@lru_cache(maxsize=4)
def execution_fingerprint(repo: Path | None = None) -> str:
    """Bind qualification to executable semantics even when a version bump was forgotten.

    Include the complete Gym and live implementations and the Gym's shared dependencies, not
    documentation. Conservative extra invalidation on an implementation-only change is allowed;
    silently carrying a band across a changed runtime/fill/context implementation is not.
    Releases are immutable, so each process hashes them once.
    """
    from ..gym.driver import LEAGUE_FILES

    repo = repo or Path(__file__).resolve().parents[2]
    files = {repo / name for name in LEAGUE_FILES}
    for name in ("gym", "live"):
        files.update((repo / "league" / name).rglob("*.py"))
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def identity(image: Any, bundle: Any) -> dict[str, str] | None:
    return {"image": str(image), "bundle": str(bundle), "execution": execution_fingerprint()} if image and bundle else None


def matches(result: Mapping[str, Any] | None, expected: Mapping[str, Any] | None) -> bool:
    """Identity-less test pools keep their existing contract; production always has both identifiers."""
    if expected is None:
        return True
    return (isinstance(result, Mapping) and result.get("gym_image") == expected["image"] and
            result.get("gym_bundle") == expected["bundle"])


def row_matches(store: Any, row: Mapping[str, Any] | None, expected: Mapping[str, Any] | None = None) -> bool:
    expected = expected if expected is not None else store.get(KEY)
    if expected is None:
        return True
    if row is None:
        return False
    summary = row.get("summary") or {}
    if "gym_image" in summary or "gym_bundle" in summary:
        return matches(summary, expected)
    return matches(store.run_result(str(row.get("run_id") or "")), expected)


def gym_changed(previous: Mapping[str, Any] | None, expected: Mapping[str, Any]) -> bool:
    """Whether an adoption changes the Gym itself (its image or bundle; no identity before counts as a change), not only
    the execution fingerprint. A change of league/live alone moves the fingerprint and leaves every recorded validation
    current (`matches`, `Tournament.recorded_validation`: the same image and bundle answer the same), so the holds they
    earned, and the operator's clears of them, stand, and so does the research selection they earned (`adopt`)."""
    return not isinstance(previous, Mapping) or any(previous.get(key) != expected.get(key) for key in ("image", "bundle"))


def on_gym_in_force(judged: Any, current: Any) -> bool:
    """Whether a Gym verdict recorded under evaluator `judged` (a validation's, `researcher.VERDICTS_KEY`) was judged on
    the Gym in force (`current`: the store's `KEY`, None in a store that never adopted one): under that very identity, or
    under one that differs from it by the execution fingerprint alone (`gym_changed`). Such a verdict stands across a
    league/live-only adoption: nothing archived it, and nothing is owed again for it."""
    return judged == current or (isinstance(current, Mapping) and not gym_changed(judged, current))


def _held(value: Any) -> bool:
    """A family holds something under a key: anything but None, False and an empty text, list or mapping (zero counts)."""
    return value is not None and value is not False and value != "" and value != [] and value != {}


def review_stands(review: Any) -> bool:
    """Whether the gate's `review` record is KEPT AS IT IS by a league/live-only adoption, and given back by the
    restoration (the module docstring): it is there and it is not a pass. A PASS is the verdict "pass" with its audit
    passed, or still owed (the gate is reading the program: no verdict against it yet); that is the live route's fact,
    cleared and never given back. Everything else stands: a failed review, a failed audit (the gate writes it as the
    review's own verdict "fail", stage "audit"), a review the gate revoked, and FAIL-CLOSED a record that cannot be read
    as a pass (a verdict that is neither word, an audit that is there but is no readable passed audit, a record that is
    no mapping). The same reading as the incubator's bar of the gate's review (`incubator.gate_review_bar`, with
    `incubator.family_bar` for a record that is no mapping), so a review is kept exactly when it bars."""
    if not _held(review):
        return False  # no review at all
    if not isinstance(review, Mapping) or review.get("verdict") != "pass":
        return True
    if "audit" not in review:
        return False  # a pass whose audit is owed
    audit = review["audit"]
    return not (isinstance(audit, Mapping) and audit.get("verdict") == "pass")


def _count(value: Any) -> int | None:
    """A version number (a positive int, never a boolean), else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def _selected(archive: Mapping[str, Any]) -> set[int]:
    """The versions a selection selects: its bests (submitted, by Train score, validated), the version its validation
    line judged, and its Train candidates."""
    rows = archive.get("train_candidates")
    found = [archive.get(key) for key in ("best_version", "validated_version", "best_train_version", "validation_version")]
    found += [row[1] for row in (rows if isinstance(rows, list) else []) if isinstance(row, (list, tuple)) and len(row) == 3]
    return {n for n in map(_count, found) if n is not None}


def _objective_moved(store: Any, state: Mapping[str, Any], seq: int, at: str) -> bool:
    """Whether Train's objective (its span: `researcher.migrate_objective`, which runs before `adopt` at every swarm
    start) was chosen anew after the event `seq` written at `at`: a pass wrote its `train_objective` event since, or a
    pass that an error cut short left this family on another objective than the store's (such a pass writes no event,
    and the next start finishes it). The migration empties every best its new span has no run for, and an old span's
    score never stands beside a new span's, so an archive from before it is another objective's selection. Any pass
    since counts, one that came back to the earlier span too: the bests were chosen anew by it."""
    if state.get("objective_migrated") not in (None, store.get("train_objective")):
        return True
    # The (kind, at) index bounds the read to the status events since that adoption; `seq` orders those of its second.
    for row in store._all("SELECT seq, payload FROM events WHERE kind='swarm.status' AND at>=? AND family IS NULL "
                          "AND payload LIKE ?", (str(at), '%"train_objective"%')):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if int(row["seq"]) > int(seq) and isinstance(payload, Mapping) and payload.get("action") == "train_objective":
            return True
    return False


def _look_owed(store: Any, fid: str, after: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """THE GATE PLACE of a selection given back (`restorable`; `after`: the family's state with it). True when it holds
    no place (`gate_ready` false, no look in flight) although the tournament's own rule would give it one
    (`Tournament._verdict`: the line met, and the gate not done with the program, `Tournament.gate_spent`): its
    validation met the line on the Gym in force, its program was never looked at and is not the gate's `gated_sha`, the
    gate never refused the version on a verdict (`incubator.refused_version`), it was neither demoted nor ended by a
    gate outcome (`bands.BAD_OUTCOMES`), and it does not wait before the gate for its unit (release F1,
    `researcher.unit_waiting`: `Tournament._verdict` gives such a version no place, and `Tournament.release_unit`
    readies it when the limit moves; the mark is no selection key, so it stands through the adoption beside the
    selection given back).

    One archived state reads so: a holdout look in flight when the earlier adoption cleared the selection. `Gate.look`
    clears `gate_ready` and keeps the look in its marker (`look_inflight`, no selection key, so never archived); that
    release's gate then dropped the marker without owing the look again (`Gate._owe`: the validation it was sent for was
    gone). Given back as archived, the family would hold a validated version that no gate round takes up and no
    tournament round readies: it would wait for good on a review and a look that never come (a look is made only
    behind a review that passed, and a passing review is not given back, so no tuition row waits with it). A marker
    still in the state is left to the gate, which owes that look again itself."""
    from .bands import BAD_OUTCOMES, demoted
    from .gate import run_sha

    line, n = after.get("validation_line"), _count(after.get("validation_version"))
    if after.get("gate_ready") or after.get("look_inflight") or n is None:
        return False
    if not isinstance(line, Mapping) or line.get("passed") is not True:
        return False
    if after.get("validation_image") != expected.get("image") or after.get("validation_bundle") != expected.get("bundle"):
        return False
    version = store.version(fid, n)
    if version is None or not version.get("sha"):
        return False
    sha = run_sha(version)
    outcome = after.get("gate_outcome")
    ended = isinstance(outcome, Mapping) and outcome.get("sha") == sha and outcome.get("result") in BAD_OUTCOMES
    from .incubator import refused_version  # the rule's third reader: a refusal row stands whatever was cleared
    from .researcher import unit_waiting  # THE UNIT ON VALIDATION: its mark is no selection key, so it stands in `after`

    return not (store.looked(sha) or after.get("gated_sha") == sha or ended or demoted(after, n)
                or refused_version(store, fid, n) or unit_waiting(after) is not None)


def restorable(store: Any, fam: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any] | None:
    """THE ONE-TIME RESTORATION (the module docstring), for one alive family at a league/live-only adoption of `expected`:
    {"adopted_at", "columns", "values", "keys", "look_owed"} (what `adopt` writes back, the names given back, and
    whether the gate place was given back for a look that adoption cut off), {"why"} when an earlier league/live-only
    adoption's archive stands but is not given back, or None when there is none to speak of.

    WHAT IS GIVEN BACK. The selection in the family's state (`ARCHIVE_KEY`), when all of this holds:

    - it is the archive of the family's newest adoption (that adoption's own event carries the same
      `_previous_selection`): an adoption under this rule writes its own event and archives no selection, so a second
      run finds its own event first and gives nothing back, whatever became of the family's best meanwhile;
    - that adoption was itself league/live-only, and the Gym has not changed since: the image and bundle it archived
      FROM are those it adopted and those in force now (`gym_changed`), so every row behind the archive is still current;
    - the family holds no best and no validation (`BEST_COLUMNS` all empty), and nothing of the Gym's selection that it
      made since: a family that selected on its own keeps its own. The drift marks are the one exception: a failing run
      marks its version without any best (`Researcher.drift_blocks`), so marks made since stay beside the archived ones;
    - no drift mark made since names a version the archive selects (`_selected`: its bests, the version its validation
      judged, its candidates): the family ran that version again and the screen failed it, which is its own newer
      evidence, and no writer leaves a failed version as the best (a demotion clears it);
    - Train's objective was not chosen anew since (`_objective_moved`): the archive's bests were scored over the span
      then running, and `migrate_objective` never lets an old span's score stand beside a new span's. Nothing is given
      back then, the validation neither: what that pass would have left of the selection is its own to say.

    AND A REVIEW THAT DID NOT PASS (`review_stands`). The archived review of the gate, when it failed its program (or
    cannot be read as a pass) and the family holds no such review of its own since, is given back as it was archived:
    the gate failed that program once, and it is not read again for a league/live change.

    WHAT IS NOT. The live route's facts (`LIVE_KEYS`: owed again under the new fingerprint), a PASSING review of the
    gate among them for every family, banded before or not: no tuition row (`bands.read`) comes back with a selection,
    and the gate reads the program again first, where its own rule takes the family up (the module docstring). And the
    idle, dormancy and stall counts (`since_val_trials`, `since_val_revisions`, `stall`, `dormant_cycles`, and the
    earlier value of `evaluator_trials`), which that adoption restarted without archiving them: they go on from its
    restart, which only lengthens the family's time before the idle rule.

    WHAT CANNOT BE, AS IT WAS. A holdout look in flight at that adoption: `gate_ready` was archived as cleared and the
    look's marker was not archived at all. The gate place is then given back ready (`_look_owed`), which is where the
    gate itself leaves a look a restart cut off; the gate reviews the program again before it makes that look (a look
    was sent only behind a review that passed, and that one is not given back)."""
    state = fam.get("state") or {}
    archive = state.get(ARCHIVE_KEY)
    if not isinstance(archive, Mapping):
        return None
    # The newest first, by the events' own order (`NOT INDEXED`: the scan stops at the first one it meets).
    row = store._one("SELECT seq, at, payload FROM events NOT INDEXED WHERE kind='swarm.status' AND family=? "
                     "AND payload LIKE ? ORDER BY seq DESC LIMIT 1", (str(fam["id"]), f'%"{ADOPTED}"%'))
    try:
        payload = json.loads(row["payload"]) if row else None
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, Mapping) or payload.get("action") != ADOPTED or payload.get("_previous_selection") != archive:
        return None  # not its newest adoption's archive: a later adoption kept its selection, or gave this one back
    source, target = payload.get("from"), payload.get("to")
    if not isinstance(target, Mapping) or gym_changed(source, target) or gym_changed(source, expected):
        return None  # that adoption changed the Gym, or the Gym changed since: the archive is another Gym's evidence
    if any(fam.get(column) is not None for column in BEST_COLUMNS):
        return {"why": "it holds a best or a validation of its own since"}
    own = sorted(key for key in GYM_KEYS if key != "drift_failed" and _held(state.get(key)) and state[key] != archive.get(key))
    if own:
        return {"why": "it selected on its own since (" + ", ".join(own) + ")"}
    since = state.get("drift_failed")
    failed = sorted(_selected(archive) & {int(k) for k in since if str(k).isdecimal()}) if isinstance(since, Mapping) else []
    if failed:
        return {"why": "the drift screen failed, since, a version it archived (" + ", ".join(map(str, failed)) + ")"}
    if _objective_moved(store, state, int(row["seq"]), str(row["at"])):
        return {"why": "Train's objective was chosen anew since, and its archive is the earlier one's selection"}
    from .researcher import DRIFT_FAILED_KEPT

    values = {key: archive[key] for key in GYM_KEYS if key in archive}  # never a live route's fact: no pass comes back
    if review_stands(archive.get("review")) and not review_stands(state.get("review")):
        values["review"] = archive["review"]  # the gate failed that program: its verdict comes back with the selection
    if "drift_failed" in values:
        marks = {str(k): v for part in (values["drift_failed"], since) if isinstance(part, Mapping)
                 for k, v in part.items() if str(k).isdecimal()}
        values["drift_failed"] = {k: marks[k] for k in sorted(marks, key=int)[-DRIFT_FAILED_KEPT:]}
    owed = _look_owed(store, str(fam["id"]), {**state, **values}, expected)
    if owed:
        values["gate_ready"] = True
    columns = {column: archive.get(column) for column in BEST_COLUMNS}
    keys = sorted([column for column, value in columns.items() if value is not None] +
                  [key for key, value in values.items() if _held(value) and value != state.get(key)])
    if not keys:
        return None  # it archived nothing the family does not hold
    return {"adopted_at": str(row["at"]), "columns": columns, "values": values, "keys": keys, "look_owed": owed}


def adopt(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """At process start, invalidate derived views once per evaluator identity before workers can select.

    A missing identity cannot authorize adoption. The transition is one transaction and is restart
    safe. New families created after the transition have no old evidence to invalidate. Two kinds (the module
    docstring):

    - THE GYM CHANGED (`gym_changed`: a new image or bundle, or no identity before). The research selection
      (`SELECTION_KEYS` and the family's bests, `BEST_COLUMNS`) and the extension hold's records (`HOLD_KEYS`) are
      archived (`ARCHIVE_KEY`, and the event's `_previous_selection`) and cleared, the idle count restarts from
      `evaluator_trials`, worded as the evaluator's change, and the family's note says what is owed again.
    - LEAGUE/LIVE ALONE (only the execution fingerprint moved). The bests, the Gym's selection (`GYM_KEYS`) and the
      hold's records stand, and the idle and dormancy counts go on. Only the live route's facts (`LIVE_KEYS`) are
      archived, in the event, and cleared, for every family: the incubator's marks and reviews, and the gate's `review`
      when it passed, so no tuition row (`bands.read`) carries across the change and none follows from a returned
      band's program; the gate reviews a program again by its own rule (the module docstring). A review that did NOT
      pass is kept as it is (`review_stands`): the gate never reads a program again that it failed. No note says
      anything is owed again: a family whose band returned is told that, and nothing else. An alive family whose
      selection an earlier league/live-only adoption archived and cleared is given it back, once (`restorable`), and
      told so; never a review that passed.

    Both return a money band whose banded evaluator is stale to the Gym (`bands.current_banded_evaluator`). The
    incubator's marks and reviews and the gate's passing review are cleared; the bars (`incubator_barred`) are kept,
    like the refusal and look rows: a verdict against a program is final for it. So a verdict held in what an adoption
    clears or may clear (the gate's `review` or `gate_outcome` failing a program, an incubator review failing it) or
    only in the gate's bars owed (`incubator.load_owed`: an error kept them from the store before a restart) is first
    recorded in `incubator_barred`, in the same transaction (`incubator.adoption_bars`); an `incubator_barred` that
    cannot be read is left alone (it bars every program of the family: `incubator.family_bar`).

    Each alive family's `evaluator_adopted` event says `gym_changed`, `kept` (the names of what it still holds of its
    bests, the Gym's selection and the hold's records, and `review` when one that did not pass stands: none when the
    Gym changed) and `restored` ({"adopted_at": the earlier adoption's time, "keys": the names given back, and
    "look_owed": True when its gate place was given back ready for a look that adoption cut off}, else None;
    `not_restored` says why an archive that stood was not given back). The result says `gym_changed`, `kept` (the
    rule's names; a review that did not pass is kept beside them, family by family), `bests` (the families holding a
    best after it), `restored` ({family: the earlier adoption's time}) and `returned` (the families whose band returned).
    """
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "evaluator identity unavailable"}
    from . import incubator

    expected = dict(expected)
    try:
        owed = incubator.load_owed(store.root)
    except Exception:  # noqa: BLE001 - the gate reads them again at its start and records them
        owed = {}
    with store.atomic():
        previous = store.get(KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        count = bests = 0
        gym = gym_changed(previous, expected)
        holds = HOLD_KEYS if gym else ()
        restored: dict[str, str] = {}
        returned: list[str] = []
        now = float(store.clock())
        for fam in store.families(alive=True):
            state = fam.get("state") or {}
            from .bands import LIVE_BANDS, current_banded_evaluator
            from .gate import run_sha

            # THE BARS FIRST: every verdict against a program that only what this clears holds, recorded for good.
            recorded = state.get("incubator_barred")
            bars: dict[str, Any] = {}
            if recorded is None or isinstance(recorded, Mapping):
                new = {sha: (n, why) for (fid, sha), (n, why) in owed.items() if fid == fam["id"]}
                for sha, why in incubator.adoption_bars(state).items():
                    new.setdefault(sha, (None, why))
                bars = {sha: {"why": why, "at": now, **({"version": n} if n is not None else {})}
                        for sha, (n, why) in new.items() if sha not in (recorded or {})}

            version = store.version(fam["id"], state.get("banded_version")) if state.get("banded_version") else None
            band_current = version is not None and current_banded_evaluator(state, run_sha(version))
            moved = fam["band"] in LIVE_BANDS and not band_current
            if moved:
                # The House retains frozen instances for exits. Research only selects Gym families,
                # so an old band must return there rather than become permanently unevaluable.
                store.set_band(fam["id"], "gym", reason="execution semantics changed; fresh qualification is required")
                returned.append(str(fam["id"]))
            if not gym:
                # LEAGUE/LIVE ALONE: the Gym's evidence stands. Only the live route's facts go (archived in the event), a
                # passing review of the gate among them, for every family: no real-order route carries across the change.
                try:
                    back = restorable(store, fam, expected)
                except Exception as exc:  # noqa: BLE001 - a restoration never keeps the swarm from starting
                    back = {"why": f"its archive could not be read ({type(exc).__name__})"}
                given = back if back is not None and "keys" in back else None
                values: dict[str, Any] = dict(given["values"]) if given else {}
                # Cleared as an adoption of a new Gym leaves each: no mark, no incubator review, no review record at all.
                # A REVIEW THAT DID NOT PASS IS LEFT AS IT IS (`review_stands`): the family's own, or the one given back.
                stands = review_stands(state.get("review"))
                gone = [key for key in LIVE_KEYS if key != "review" or not stands]
                values.update({key: {} for key in gone if key != "review"})
                if not stands and not review_stands(values.get("review")):
                    values["review"] = None
                values["evaluator"] = expected
                if bars:
                    values["incubator_barred"] = {**dict(recorded or {}), **bars}
                after = {**state, **values}
                best = given["columns"] if given else fam
                kept = sorted([column for column in BEST_COLUMNS if best.get(column) is not None] +
                              [key for key in (*GYM_KEYS, *HOLD_KEYS) if _held(after.get(key))] +
                              (["review"] if review_stands(after.get("review")) else []))
                event = {"action": ADOPTED, "from": previous, "to": expected, "gym_changed": False, "kept": kept,
                         "restored": {"adopted_at": given["adopted_at"], "keys": given["keys"],
                                      **({"look_owed": True} if given.get("look_owed") else {})} if given else None,
                         "_previous_selection": {key: state[key] for key in gone if key in state},
                         "incubator_barred": sorted(sha[:12] for sha in bars)}
                if back is not None and "why" in back:
                    event["not_restored"] = back["why"]
                store.event("swarm.status", fam["id"], event)
                if given:
                    store.update_family(fam["id"], **given["columns"])
                    restored[str(fam["id"])] = given["adopted_at"]
                store.set_state(fam["id"], **values)
                if moved:
                    store.note(fam["id"], "The live executor changed (league/live), so this family's money band returned to "
                               "the Gym: a band is entry authority only under the executor that earned it, and its frozen "
                               "live instances only close. The Gym did not change, so your Train selection, stress/drift "
                               "checks and validation stand and nothing is owed again on Train or Validation. This does not "
                               "grant another holdout look.")
                if given:
                    store.note(fam["id"], f"The evaluator adoption of {given['adopted_at']} changed only the live executor "
                               "(league/live), not the Gym, so the selection it cleared is given back as it was: your "
                               "Train best and candidates, the stress/drift checks and any validation. The note of that "
                               "time saying they are owed again no longer applies: nothing is owed again, and no prior "
                               "program needs to be run again. This does not grant another holdout look.")
                bests += best.get("best_train") is not None or best.get("best_version") is not None
                count += 1
                continue
            archived = {key: state[key] for key in (*SELECTION_KEYS, *holds) if key in state}
            archived.update({key: fam.get(key) for key in BEST_COLUMNS})
            # Banded identity remains an historical claim; bands.read separately denies entry.
            store.event("swarm.status", fam["id"], {"action": ADOPTED, "from": previous, "to": expected,
                                                       "gym_changed": True, "kept": [], "restored": None,
                                                       "_previous_selection": archived,
                                                       "incubator_barred": sorted(sha[:12] for sha in bars)})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared = {key: None for key in (*SELECTION_KEYS, *holds)}
            if holds:
                cleared["extension_versions"] = []
            # The idle count starts again from here (`researcher.idle_evaluations`), and its words say the evaluator
            # changed (`evaluator_trials`), not Train's span (`span_trials` is `migrate_objective`'s mark alone).
            cleared.update(train_candidates=[], robustness={}, robust_failed=[], robust_why={}, drift_failed={},
                           train_passed={}, incubator_reviews={}, gate_ready=False, dormant_cycles=0,
                           evaluator_trials=int(fam.get("trials") or 0), evaluator=expected,
                           **{ARCHIVE_KEY: archived})
            if bars:
                cleared["incubator_barred"] = {**dict(recorded or {}), **bars}
            if fam["band"] != "gym" and band_current:
                # Sizing of a genuinely unchanged, already qualified semantic engine remains
                # attached to its banded version. Changed semantics are blocked by the entry proof.
                cleared.pop("typical_by_version", None)
                cleared.pop("typical_max_loss_usd", None)
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The evaluator changed. Historical runs, lineage trials and holdout looks remain counted. "
                       "Train selection, stress/drift checks and validation are owed under the current evaluator; "
                       "rerun a defensible prior program before submitting it. This does not grant another holdout look.")
            count += 1
        store.put(KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected, "gym_changed": gym,
            "kept": [] if gym else [*BEST_COLUMNS, *GYM_KEYS, *HOLD_KEYS], "bests": bests, "restored": restored,
            "returned": returned}


def adoption_words(out: Mapping[str, Any]) -> str:
    """The swarm's start line for an adoption (`loop.Swarm.run`): which kind it was and what the families keep or owe."""
    n = int(out.get("families") or 0)
    if out.get("gym_changed", True):
        return f"evaluator adopted: {n} families owe fresh evidence"
    words = (f"evaluator adopted (league/live only, the Gym did not change): {n} families keep their research selection, "
             f"{int(out.get('bests') or 0)} with a best")
    restored, returned = out.get("restored") or {}, out.get("returned") or []
    if restored:
        words += (f"; {len(restored)} given back the selection the league/live-only adoption of "
                  f"{', '.join(sorted(set(restored.values())))} archived")
    if returned:
        words += f"; {len(returned)} stale money band(s) returned to the Gym"
    return words


__all__ = ["KEY", "SELECTION_KEYS", "HOLD_KEYS", "LIVE_KEYS", "GYM_KEYS", "BEST_COLUMNS", "ARCHIVE_KEY", "ADOPTED",
           "identity", "matches", "row_matches", "gym_changed", "on_gym_in_force", "review_stands", "restorable", "adopt",
           "adoption_words", "execution_fingerprint"]
