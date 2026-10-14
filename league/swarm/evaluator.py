"""Adopt an evaluator without transferring old selection evidence or erasing search history.

Run identities already include the Gym bundle, but family bests/robustness used to outlive that
identity. This module scopes those materialized views too. Historical runs, trials, looks, versions,
notebooks and forward records remain untouched. A stale money band returns to the Gym for fresh
qualification; its frozen live instances retain their close path. A stale band is not entry authority.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from ..xs import STRUCTURE as XS_STRUCTURE
from ..xs.identity import XS_KEY, xs_band_current

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


#: THE EQUITY IDENTITY (release E1, A8.8 as amended by the captain's A13; owner: core): the store kv key of the adopted
#: equity fingerprint, and every league/gym module the evidence modules import (hashed with them, listed explicitly; a
#: test holds the list to the imports). What they import outside league/ is `EQUITY_CALENDAR_FILES`, below.
EQUITY_KEY = "equity_evaluator"
EQUITY_GYM_FILES = ("league/gym/__init__.py", "league/gym/safety.py", "league/gym/runtime.py", "league/gym/events.py")
#: THE EQUITY EVIDENCE (A13): the modules of league/equity whose code decides what a program's evidence IS, hashed into
#: the equity identity, and nothing else of that package. They are the import closure, inside league/equity, of
#: `EQUITY_EVIDENCE_ROOTS` (the isolated runner, the decider child's "equity" kind, the screen and the engine: what
#: Validation, the sealed look and a live decision execute), and `synth` (the synthetic store the I6 ctx test and every
#: package's tests build their evidence on; it imports only modules already in the closure). A CI test holds this list
#: equal to that closure plus `EQUITY_EVIDENCE_EXTRA` (league/tests/test_equity_identity.py), so a new evidence module
#: cannot hide outside the identity. PLUMBING IS OUT: live, actions, schedule, families, bands and kinds (the
#: EquityBook, its clock, its corporate actions, the swarm reader, the band rules, the decider's kind table) move no
#: identity, so a plumbing fix never sends a live equity band back to the Gym; that live and Gym agree is policed
#: instead by the I6 ctx test (league/tests/test_equity_i6.py) and the equity twins (league/ops/twins.py).
EQUITY_EVIDENCE = ("__init__", "config", "store", "program", "ctx", "engine", "results", "runner", "synth", "sizing",
                   "screen", "child")
EQUITY_EVIDENCE_ROOTS = ("runner", "child", "screen", "engine")
EQUITY_EVIDENCE_EXTRA = ("synth",)
#: THE CALENDAR'S FILES: what the evidence modules import of this repository OUTSIDE league/, hashed with them. The
#: store's session list and the ctx's calendar read the NYSE calendar of `ltcm.data` (league/equity/store.py
#: `nyse_sessions`, league/equity/ctx.py `calendar_around`): a holiday or an early-close rule changed there changes
#: the sessions a Validation or a sealed look runs over and the ctx's half_day, session_of_month and
#: sessions_to_month_end, so a band proof must not outlive it. The three files are everything importing `ltcm.data`
#: executes (it imports `ltcm.broker`; both run ltcm/__init__.py), the same three league/equity/kinds.py `RUNTIME`
#: gives the child. A CI test holds the list equal to that import closure (league/tests/test_equity_fx_swarm.py), so
#: the evidence cannot come to import another file of the repository unhashed. They are not plumbing: from E1 on a
#: change to any of them moves the equity identity, as an evidence module's does.
EQUITY_CALENDAR_FILES = ("ltcm/__init__.py", "ltcm/broker.py", "ltcm/data/__init__.py")
#: An equity family's state keys an adoption archives and clears beside `SELECTION_KEYS` (its evidence under the old
#: engine: the Validation runs' spread and the screen's floor, both run again before any look). Its tries and its look
#: (`elane_try`, `elane_look`) are never cleared: a lineage's spent try and look stay spent. Nor is THE LOOK'S LINEAGE
#: RECORD (`elane_train_r`, the looked version's Train daily series, and `elane_template`): A9 D3's correlation test
#: reads it for every later program of either equity lane, and nothing can write it again (the look is spent), so an
#: adoption that cleared it would hand a re-coded copy of a program already looked at a second sealed look.
EQUITY_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_floor")
#: THE PANEL LANE (release E4; owner: package E). A panel family (structure "panel", lane "equity") binds to THE XS
#: IDENTITY (`league.xs.identity.xs_fingerprint`; its store kv key is `XS_KEY`, re-exported here), never to the equity
#: one: `adopt_equity` leaves it alone and `adopt_xs` is its adoption. A panel family's state keys an xs adoption
#: archives and clears beside `SELECTION_KEYS`: the Validation runs' spread and the screen's floor, both run again
#: before any look, AND NOTHING ELSE OF THE PANEL'S. Its tries and its look (`elane_try`, `elane_xs_look`) are never
#: cleared: a lineage's spent try and look stay spent. Nor are THE LINEAGE RECORDS: both Train series of every
#: program that reached the pre-check (`elane_xs_train_x`, `elane_xs_train_u`), the pre-check's own record
#: (`elane_xs_precheck`) and the template. The pinned pre-registration's lineage rule reads them for every later panel
#: program, looked at or refused, and nothing can write them again (the try and the look are spent), so an adoption
#: that cleared one would hand a re-coded copy of a program already judged a second try or a second sealed look.
XS_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_xs_floor")


def _equity_lanes() -> tuple[str, ...]:
    from ..equity import LANES

    return LANES


def is_equity_family(fam: Mapping[str, Any] | None) -> bool:
    """Whether a family row belongs to an equity lane (its spec's `lane` is "beta" or "equity")."""
    spec = (fam or {}).get("spec") or {}
    return isinstance(spec, Mapping) and str(spec.get("lane") or "") in _equity_lanes()


def is_panel_family(fam: Mapping[str, Any] | None) -> bool:
    """Whether a family row is a PANEL family (release E4): its structure is "panel" (`league.xs.STRUCTURE`; the store
    admits it in the equity lane only). It is an equity-lane family (`is_equity_family`) that binds to the xs identity,
    never to the equity one."""
    return isinstance(fam, Mapping) and str(fam.get("structure") or "") == XS_STRUCTURE


@lru_cache(maxsize=4)
def equity_fingerprint(repo: Path | None = None) -> str:
    """THE EQUITY LANE's evidence identity (A8.8 as amended by A13; owner: core): sha256 over the EVIDENCE modules of
    league/equity (`EQUITY_EVIDENCE`: league/equity/<name>.py, each of them, and no other file of the package), the 4
    `LEAGUE_FILES`, `EQUITY_GYM_FILES` and the calendar they read (`EQUITY_CALENDAR_FILES`), path and bytes, in path
    order (as `execution_fingerprint`). Equity bands bind to it as options bands bind to `execution_fingerprint`; it
    never moves for a league/live or options-only change, nor for league/equity's plumbing (live, actions, schedule,
    families, bands, kinds), nor for league/xs. A release that lacks one of its files has no identity (the read raises:
    no band proof, no look)."""
    from ..gym.driver import LEAGUE_FILES

    repo = repo or Path(__file__).resolve().parents[2]
    files = {repo / name for name in (*LEAGUE_FILES, *EQUITY_GYM_FILES, *EQUITY_CALENDAR_FILES)}
    files.update(repo / "league" / "equity" / f"{name}.py" for name in EQUITY_EVIDENCE)
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def equity_identity() -> dict[str, str]:
    """{"equity": equity_fingerprint(), "engine": league.equity.EQUITY_ENGINE_VERSION} (owner: core)."""
    from ..equity import EQUITY_ENGINE_VERSION

    return {"equity": equity_fingerprint(), "engine": EQUITY_ENGINE_VERSION}


def equity_band_current(state: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Whether an equity family's band proof (`banded_evaluator` {"engine", "equity_sha256", "run_sha"}) names the
    equity identity `expected` ({"equity", "engine"})."""
    proof = state.get("banded_evaluator") or {}
    return isinstance(proof, Mapping) and proof.get("engine") == expected.get("engine") and \
        proof.get("equity_sha256") == expected.get("equity")


def adopt_equity(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """`adopt` mirrored for the equity lanes (owner: core): at process start, when the stored `EQUITY_KEY` differs from
    `expected`, every alive equity-lane family's selection views are archived and cleared and a live equity band goes
    back to "gym" for fresh qualification (its frozen lots keep their exits), in one transaction; options families are
    never touched, NOR IS A PANEL FAMILY (release E4: it binds to the xs identity; `adopt_xs`). {adopted, families,
    previous, current}.

    A missing identity cannot authorize adoption. Runs, trials, the lineage's tries and its look with its lineage record
    (`EQUITY_SELECTION_KEYS`: the Train series and the template D3 reads are kept), refusals, forward records and the
    band's history stay; the family's `equity_evaluator` names the identity it is now judged under."""
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "equity identity unavailable"}
    from .bands import LIVE_BANDS

    expected = dict(expected)
    with store.atomic():
        previous = store.get(EQUITY_KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        try:
            rows = store.families(alive=True, lanes=_equity_lanes())
        except TypeError:  # a store before the swarm's lane filter: every family, the equity ones picked here
            rows = store.families(alive=True)
        count = 0
        for fam in rows:
            if not is_equity_family(fam) or is_panel_family(fam):
                continue  # a panel family binds to the xs identity (`adopt_xs`), never to this one
            state = fam.get("state") or {}
            if fam["band"] in LIVE_BANDS and not equity_band_current(state, expected):
                # The House keeps the lots for their exits; the band must be earned again under the new engine.
                store.set_band(fam["id"], "gym", reason="equity execution semantics changed; fresh qualification is "
                                                       "required")
            keys = (*SELECTION_KEYS, *EQUITY_SELECTION_KEYS)
            archived = {key: state[key] for key in keys if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation",
                                                           "validated_version")})
            store.event("swarm.status", fam["id"], {"action": "equity_evaluator_adopted", "from": previous,
                                                    "to": expected, "_previous_selection": archived})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared: dict[str, Any] = {key: None for key in keys}
            cleared.update(gate_ready=False, equity_evaluator=expected, previous_evaluator_selection=archived)
            # A16: a version validated (and gate-ready) under the old engine but not yet looked at is owed its
            # Validation again (the same try: no look was spent), so its recorded verdicts go stale; left current,
            # `elane.next_try` would never ask for it and the family would wait forever.
            from .elane import VALIDATION_KEY, VERDICTS_KEY

            verdicts = state.get(VERDICTS_KEY)
            if isinstance(verdicts, Mapping) and verdicts:
                cleared[VERDICTS_KEY] = {str(k): ({**dict(v), "stale": True} if isinstance(v, Mapping) else v)
                                         for k, v in verdicts.items()}
            if isinstance(state.get(VALIDATION_KEY), Mapping):
                cleared[VALIDATION_KEY] = {**dict(state[VALIDATION_KEY]), "stale": True}
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The equity engine changed. Historical runs, the lineage's Validation try and its "
                       "sealed look remain counted. Validation evidence is owed under the current engine; this does "
                       "not grant another try or another look.")
            count += 1
        store.put(EQUITY_KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected}


def adopt_xs(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """`adopt_equity` mirrored for THE PANEL LANE (release E4; owner: package E): at process start, when the stored
    `XS_KEY` differs from `expected` (`league.xs.identity.xs_identity()`: {"xs", "engine"}), every alive PANEL family's
    selection views are archived and cleared and a live panel band goes back to "gym" for fresh qualification (its
    frozen lots keep their exits), in one transaction. An ETF or stock family and an options family are never
    touched: a change to an xs evidence module retires no share lineage. {adopted, families, previous, current}.

    A missing identity cannot authorize adoption. Cleared: `SELECTION_KEYS` and `XS_SELECTION_KEYS`, and nothing else
    of the panel's. Kept: runs, trials, the lineage's try and its look, THE LINEAGE RECORDS (both Train series, the
    pre-check's record, the template: `XS_SELECTION_KEYS`' note), the Train record, refusals, forward records and the
    band's history; the family's `xs_evaluator` names the identity it is now judged under. The store's kv `XS_KEY` is
    this adoption's own mark and no band reads it: a live band's currency is read from the running release's files
    (`bands.current_xs_evaluator`)."""
    if expected is None:
        return {"adopted": False, "families": 0, "reason": "xs identity unavailable"}
    from .bands import LIVE_BANDS

    expected = dict(expected)
    with store.atomic():
        previous = store.get(XS_KEY)
        if previous == expected:
            return {"adopted": False, "families": 0}
        try:
            rows = store.families(alive=True, lanes=_equity_lanes())
        except TypeError:  # a store before the swarm's lane filter: every family, the panel ones picked here
            rows = store.families(alive=True)
        count = 0
        for fam in rows:
            if not is_panel_family(fam):
                continue
            state = fam.get("state") or {}
            if fam["band"] in LIVE_BANDS and not xs_band_current(state, expected):
                # The House keeps the lots for their exits; the band must be earned again under the new evidence.
                store.set_band(fam["id"], "gym", reason="panel evidence semantics changed; fresh qualification is "
                                                       "required")
            keys = (*SELECTION_KEYS, *XS_SELECTION_KEYS)
            archived = {key: state[key] for key in keys if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation",
                                                           "validated_version")})
            store.event("swarm.status", fam["id"], {"action": "xs_evaluator_adopted", "from": previous,
                                                    "to": expected, "_previous_selection": archived})
            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
            cleared: dict[str, Any] = {key: None for key in keys}
            cleared.update(gate_ready=False, xs_evaluator=expected, previous_evaluator_selection=archived)
            # A16, as `adopt_equity`: a version validated under the old evidence and not yet looked at is owed its
            # Validation again (the same try: no look was spent), so its recorded verdicts go stale.
            from .elane import VALIDATION_KEY, VERDICTS_KEY

            verdicts = state.get(VERDICTS_KEY)
            if isinstance(verdicts, Mapping) and verdicts:
                cleared[VERDICTS_KEY] = {str(k): ({**dict(v), "stale": True} if isinstance(v, Mapping) else v)
                                         for k, v in verdicts.items()}
            if isinstance(state.get(VALIDATION_KEY), Mapping):
                cleared[VALIDATION_KEY] = {**dict(state[VALIDATION_KEY]), "stale": True}
            store.set_state(fam["id"], **cleared)
            store.note(fam["id"], "The panel's evidence code changed. Historical runs, the lineage's Validation try and "
                       "its sealed look remain counted, and so do both Train series the lineage rule reads. Validation "
                       "evidence is owed under the current code; this does not grant another try or another look.")
            count += 1
        store.put(XS_KEY, expected)
    return {"adopted": True, "families": count, "previous": previous, "current": expected}


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
    earned, and the operator's clears of them, stand."""
    return not isinstance(previous, Mapping) or any(previous.get(key) != expected.get(key) for key in ("image", "bundle"))


def adopt(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
    """At process start, invalidate derived views once per image/bundle before workers can select.

    A missing identity cannot authorize adoption. The transition is one transaction and is restart
    safe. New families created after the transition have no old evidence to invalidate. The extension
    hold's records (`HOLD_KEYS`) are archived and cleared with the selection when the Gym changed
    (`gym_changed`) and kept when only the execution fingerprint moved. The idle count restarts from
    `evaluator_trials`, worded as the evaluator's change. The incubator's marks and reviews are cleared; its bars
    (`incubator_barred`) are kept, like the refusal and look rows: a verdict against a program is final for it. So a
    verdict held only in what the adoption clears (the gate's `review` or `gate_outcome` failing a program, an incubator
    review failing it) or only in the gate's bars owed (`incubator.load_owed`: an error kept them from the store before
    a restart) is first recorded in `incubator_barred`, in the same transaction (`incubator.adoption_bars`); an
    `incubator_barred` that cannot be read is left alone (it bars every program of the family: `incubator.family_bar`).
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
        count = 0
        holds = HOLD_KEYS if gym_changed(previous, expected) else ()
        now = float(store.clock())
        for fam in store.families(alive=True):
            if is_equity_family(fam):
                continue  # the equity lanes bind to their own identity (`adopt_equity`, I5)
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
            if fam["band"] in LIVE_BANDS and not band_current:
                # The House retains frozen instances for exits. Research only selects Gym families,
                # so an old band must return there rather than become permanently unevaluable.
                store.set_band(fam["id"], "gym", reason="execution semantics changed; fresh qualification is required")
            archived = {key: state[key] for key in (*SELECTION_KEYS, *holds) if key in state}
            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation", "validated_version")})
            # Banded identity remains an historical claim; bands.read separately denies entry.
            store.event("swarm.status", fam["id"], {"action": "evaluator_adopted", "from": previous, "to": expected,
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
                           previous_evaluator_selection=archived)
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
    return {"adopted": True, "families": count, "previous": previous, "current": expected}


__all__ = ["KEY", "SELECTION_KEYS", "HOLD_KEYS", "identity", "matches", "row_matches", "gym_changed", "adopt",
           "execution_fingerprint", "EQUITY_KEY", "EQUITY_GYM_FILES", "EQUITY_EVIDENCE", "EQUITY_EVIDENCE_ROOTS",
           "EQUITY_EVIDENCE_EXTRA", "EQUITY_CALENDAR_FILES", "EQUITY_SELECTION_KEYS", "equity_fingerprint",
           "equity_identity", "equity_band_current", "is_equity_family", "adopt_equity",
           "XS_KEY", "XS_STRUCTURE", "XS_SELECTION_KEYS", "is_panel_family", "adopt_xs"]
