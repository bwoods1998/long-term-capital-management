"""The hourly tournament: validation, the allocation, forks, retirements, lessons, the leaderboard.

1. VALIDATION. Every living family whose best version (submitted, else its best Train score) has not been
   validated yet runs on Validation once, but only after that version's 1.5x-stress Train robustness run came back
   with a profit (`tournament.require_robustness`, Sept 26: a version that loses at 1.5x never reaches the gate), and only
   when it passes THE DRIFT SCREEN (`tournament.drift_screen`, Sept 27, `evidence.drift_screen`: its Train drift-adjusted
   alpha has a pooled t of at least `drift_min_t` and is positive in all Train years but one: a candidate that fails is
   demoted, `researcher.screen_best`, and the next candidate that passes is validated in its place; a version whose Train
   run predates the figures waits until the researcher's robustness label "drift" has run it again). The Gym runs its
   1.5x-half-spread twin in the same batch (two trials, counted) and returns only the validation VIEW (no trades, dates
   or daily series). The
   researcher is told only whether the line was met and how many of its checks passed (D2a). A version runs on
   its own NEEDS roots (a family's roots may have moved since). AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1, Oct 3, 2026;
   `tournament.reuse_validations`, `known_validation`): a version whose program (code, merged params and roots) another
   family's version already validated on the Gym image and bundle in use (a revival or a fork that carries its parent's
   program unchanged) is judged from that result by the line as it stands for its own lineage: no Gym job, no trial, no
   new validated version in the deflated Sharpe's count. It keeps its own copy of the record (rows with no trial that
   name the source) and its state says where the verdict is from (`validation_inherited`); two such families in one
   round cost one job.
2. THE LINE (`evidence.validation_line`, as the owner's decision D2 and FAST LANE V2 of Oct 7, 2026 amended it): its
   deflated Sharpe is on traded days with N = 1, the program itself (fast lane v2; before it, the lineage's validated
   versions, `SwarmStore.lineage_validated`, kept for the benchmark scripts). A family that meets it goes to
   the gate's queue. Then THE INCUBATOR'S TRAIN AND DRIFT MARKS (`incubator.facts`, release B2, Sept 30, 2026): each
   version an alive Gym family practises in an active, current cohort is marked `train_passed` once it has an eligible
   Train run, a profitable 1.5x run, no demotion and a passed drift screen, under the current evaluator. The mark is
   a fact for the House's incubator route only (one lot, never evidence, never a promotion); nothing here reads it.
   THE DIRECTION LANE (release D-1, Oct 9, 2026; `league/swarm/dlane.py`): the verdict also keeps the Validation run's sd
   of P&L per dollar of maximum loss beside `typical_max_loss_usd` (`sigma_fields`, the operator's decision 4: release
   L-D's DM1 reads it), and a direction version that missed the line goes to the gate when D2 is the lane's screen in
   force and its Validation pre-check passes (`precheck_entry`; D2 is refused unless its receipt is pinned). While
   `dlane.mode` is "off" neither is done.
   THE DIRECTION LANE'S RATION (release D-1b, Oct 9, 2026; DSCREEN-ADOPT): ONE Validation try and ONE holdout look per
   direction lineage (`dlane.val_tries`, `dlane.looks_per_lineage`), so D2's measured false-positive rate per program is
   the lineage's. A direction version is validated only while its connected lineage has no try yet, or when it is that
   try already (validated again on a new Gym image: `dlane.try_open`); one member of a lineage a round (`waiting_lane`);
   a family whose lineage's try is used is owed none (`spent_lane`, which the ops' stall check reads). The backstop: a
   verdict that is not its lineage's first try (a result that raced past the guard, landing late) is recorded as rows and
   trials and never judged into the family's state (`lane_try`), so it can never enter the gate. The lineage's try is kept
   in the family's state (`dlane.TRY_KEY`: did it enter the gate). THE TRY IS ALWAYS JUDGED (the review's finding 1): the
   lineage's first try is judged even when the researcher moved the candidate on while its job was out (`judge`), and a
   try with no verdict, or whose verdict entered the gate on another Gym image, is validated again as that very version
   (`dlane.try_owed`), never the candidate, so no lineage dies with its try spent unjudged.
   RETIREMENT (`_why`, `dlane.lineage_spent`): a Gym
   direction family whose lineage has used its try or its look, with no try of its own still waiting for its look,
   retires, THE COHORT KEEP's or not (THE RATION BEFORE THE KEEP, Oct 10, 2026, the readiness audit's M3: until then the
   keep spared it as it spares the clocks, holding a population slot with nothing left to validate); a direction family
   never forks once its lineage's try is used (`lane_forks`). The alpha lane keeps its counts; with the lane off nothing
   here is read. THE ALWAYS-IN CARD (Oct 10, 2026; dlane.py): an always-in direction family's version is validated only
   with a G1 pass on record (`dlane.always_in_try`: the program behaved always-in on Train), else it waits
   (`always_in_refused`, no try spent), and a family whose version due for Validation G1 refused retires in `_why`,
   after the ration (`dlane.always_in_failed`, an IDLE death that binds no card); an always-in family never forks
   (`lane_forks`: a fork adds a root, and each root's always-in idea has its own try).
3. THE ALLOCATION (Release B, league/swarm/allocation.py; `allocation.mode` "value"): each family's share of researcher
   turns and Gym priority by its expected information value (the variance of its next validation's pass or fail under
   an empirical-Bayes posterior, discounted by the idea's trials, its own and those inherited at birth, by exhaustion:
   its lineage's holdout looks spent, a drift-failed validation, a hold streak, and by half for a structure real money
   cannot open), with a floor for every family, an explicit exploration share for breadth across mechanism classes,
   and caps on one family's and one class's share. A validated version that failed the drift
   screen earns nothing by its validation (the family counts as unvalidated). "bandit" restores THE BANDIT
   (`evidence.thompson`, `Tournament.bandit`): R11-5's Thompson sampling, at least 25% for the explore pool, only an old
   family whose latest validation mean is positive exploited, each earning at most `exploit_per_positive` (0.15) of the
   share. THE PRACTICE BONUS (`practice.apply_bonus`), on either: a family
   with a positive practice record on live quotes gains at most `practice.bonus` (25%) of its share, and the bonus moves
   at most `practice.bonus_total` (10%) of all share; it changes research attention only, never what is validated, the
   gate, the bands or money. The round's event records it (`practice_bonus`, private).
4. FORKS: the top `fork_top` (3; 0 turns forks off) families whose validation t is at least `fork_min_t` (1.0) with a
   positive validation mean fork, each at most once every `fork_cooldown_hours` (6) (never one whose validated version
   failed the drift screen) (a new family on the parent's roots plus one more root of the rotation, same mechanism and
   structure; it inherits the lineage's trial count and holdout looks), while the population is under its ceiling.
   XSP is out of the rotation: its $0.50 a contract makes a narrow structure uneconomic. Only a family of a type
   `architect.structures` allows forks (THE STRUCTURES, Oct 1, 2026: league/swarm/architect.py `allowed_structures`;
   every type while it is unset); one of another type is never retired for it and keeps researching until a rule
   retires it.
5. RETIREMENTS: no validation improvement in `retire_revisions` (30) or `retire_evaluations` (2,000; the defaults,
   swarm.json may set others) Gym evaluations, or trial-adjusted
   evidence below the line (the deflated Sharpe probability under `retire_dsr_below` after
   `retire_min_validations` validations), or, as the fallback for a dead family that never calls retire, THE IDLE
   RULE (`researcher.idle_dead`, R3: `researcher.retire_idle_evaluations` Gym evaluations since its birth or last
   validation without an eligible Train version, or three times as many with its best Train score below zero, or
   `researcher.dormant_cycles` cycles in a row with only stored results, holds and refused runs while its best does
   not await validation; or, F1's DEPTH RULE, `researcher.retire_short_cycles` (10) cycles after a counted validation
   that met at most `researcher.retire_short_checks` (5) of the line's checks, `researcher.short_dead`; never while a
   validated version awaits the gate); never below the population floor, which counts the families that research (F1,
   THE FLOOR COUNTS RESEARCH, `researcher.floor_counts`: a dead slot, dead by the idle rule or holding three cycles in
   a row with nothing pending, is not counted and so is never held by it; `population.floor_researching` false counts
   every living family, as before), and by
   no rule while the operator holds its validated version at the gate (`researcher.held_at_gate`). Each retiree's
   lesson goes to the graveyard (its mechanism, what it tried, its best numbers, its last notebook lines); an idle-rule
   lesson carries the verdict of its Train record (R11-1, `researcher.train_record`: DRIFT, STRESS, THIN or EXHAUSTED,
   tested findings), and only an untested family's (it never traded on Train) says it was a time limit, not a
   refutation. A validation that meets `researcher.extension_hold_checks` (6) of the line's checks sets the family's
   extension hold (R11-4's swarm rule, `researcher.judge_extension`); a validation of the held version below them ends
   it. Each counted verdict records the family's trials (`validated_trials`), from which the idle rule counts, and its
   cycles (`validated_cycles`, the depth rule's count), and restarts its dormant cycles. Each verdict, counted or re-judged, is also kept per version with the evaluator it was
   judged under (`validation_verdicts`, Oct 1): THE VALIDATED-FAMILY GUARD (`researcher.retire_guard`) reads it, so a
   researcher may not retire a family that holds a version whose latest verdict passed the line (archived by an
   adoption or not) unless a later validation of that version failed it. No rule here reads it. THE IDLE PASS (R4,
   `idle_pass`) retires by the idle rule alone every
   `tournament.retire_every_seconds` (300) between the rounds.
   THE COHORT KEEP (L1, release B, Sept 30, `incubator_keep`): a Gym family with an ACTIVE practice cohort (the House's
   frozen program, `practice.cohort_status`) is spared the revision, evaluation and idle rules until its cohort completes,
   fails or reaches its session window, so a family is still alive when its practice sample is complete and the
   incubator takes its first look (families lived a median 1.71 hours on Sept 30). The cohort's record is read BEFORE
   TODAY under its own evaluator, the incubator's own basis, realized only (the open mark starts below zero at every open,
   the entry's fees and spread booked against it, and is left to the first look). Before the cohort meets the
   incubator's sample (3 completed sessions, 10 program closes) it is kept whatever its record so far: the first look is
   the one pre-registered P&L test, and a record judged sooner would drop a third or more of the cohorts whose first look
   would pass. Once it meets the sample it is kept only while that record is not negative (program-closed P&L at least
   0, and all closes at least 0). A cohort the House has not practised on `KEEP_UNPRACTICED` (2) sessions while it
   practises others, or whose practice row began before it (the incubator never looks at it), is not kept. At most
   `tournament.incubator_keep_max` (12; 0 turns it off) families: first THE INCUBATOR'S COHORTS (`incubator_held`: the
   sample met, a record not negative, and the swarm's own incubator facts admitting the cohort's program, so every
   cohort the House's incubator can pin from its L2' keep is one of them), then the rest that meet the
   sample (each group by return on risk, highest first), then those whose record so far is not negative, then the
   rest, each by the practice league's own order (`bands.priority`). The incubator's cohorts are never cut by the cap
   (at most `KEEP_CEILING`), so the keep never holds fewer families than the House can have pinned, and a pinned
   family (retired, its incubation would go to exits only) is never dropped for a higher return. The swarm never reads
   the House's live state, so it holds every cohort that could be pinned. It never spares a family from the
   deflated-Sharpe rule, the population floor or the operator's gate hold, nor (since Oct 10, 2026) a direction family
   from its lineage's ration. Research attention only: no trial count, look, validation, gate, band or money rule reads
   it. The keep is saved at each read (`practice.KEEP_KV`, the
   incubator's cohorts' families too), so a kept family's researcher is not urged to retire it for being idle, and its
   researcher's, the mechanism test's and the diagnostician's own retire wait for it (THE KEEP WAITS FOR RETIREMENT,
   Oct 9, researcher.py: a retired family's cohort can never be pinned). A record that cannot be read leaves the last
   good keep standing for `KEEP_STALE_SECONDS` (an hour), then none; a FRESH PROCESS (a deploy, a restart, the
   induced-failure kill: its idle pass runs at once) whose first read fails takes the keep the last process saved for
   the rest of that hour (the incubator's cohorts' families first, never cut by the cap) and does not overwrite it
   before then. The round records the kept families and what each was spared in one private `swarm.status` event
   (`incubator_keep`).
6. THE LEADERBOARD: one `swarm.tournament` event (the House mirrors it to its ledger) with every family's
   rank, share, validation summary, trials and band, and the totals. Its order (`board_rank`): Candidates and beyond,
   then families at the gate or with a look out, then by share, so the architect's and the strategist's first 60 rows
   always hold the most advanced families (the allocation gives them the floor share: the gate decides them next).
7. THE LEARNING GAME (Oct 8, 2026; league/swarm/game.py). For a game-arm family in mode "gate" (`played`): its candidate
   for Validation is its latest CONFIRMED version not yet judged, none without one (`game.candidate`, in place of
   submitted, else best Train); it has `game.val_tries` (2) Validation tries (`game_try_left`: a version validated before,
   as after an adoption, is no new try); its ladder look's seen run is an eligible Train run for it, and its robustness
   requirement is met by that look (a look needed a profitable 1.5x seen run, and the state keeps only the last six
   versions' figures); the game's three retirement rules come first (`game.retire_reason`: its private looks spent
   without a pass, two failed private confirmations, its Validation tries used and failed; one public reason for all
   three; Gym band only, under the floor); it is never forked (the game's children replace forks); and THE GAME'S
   VALIDATION WAIT (`game_dormant`): the dormancy clause spares such a family only while its CONFIRMED version awaits a
   Validation it can have (a try left, an eligible Train run under the evaluator in force: `game_train_ok`) or a look of
   it is out (its best is never validated otherwise, so today's wait would spare a holding family for ever). The round's
   `validation` names such a family that waits for a CONFIRM (`waiting_game`, only when there is one: the ops' stall check
   owes it no Validation). Each round, before Validation, a SELECT PASS that landed while the rules were off reads its
   CONFIRM year (`game.confirm_waiting`); after it, control's records of the versions it validated are queued
   (`game.shadow_validated`), a look whose hidden run failed or was lost is queued again (`game.requeue_stale`) and a best
   that meets the ladder's triggers with no look out is looked at (`game.recheck`); after the forks, the game's children
   are born (`game.reproduce`). Control, legacy families and the game off: every rule above as it was. Every game call is
   wrapped: a game error never fails a round (one private `swarm.status` event names its type, never its words).

Standard library only.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable, Mapping

from . import diagnostics, dlane, evidence, game, incubator, practice
from .architect import allowed_structures
from .pool import GymJob, PoolError
from .researcher import (IDLE_CAUSE, MAX_ROOTS, VALIDATED_CYCLES_KEY, awaiting_validation, dormant_count, dormant_limit,
                         drift_failed, drift_verdict, floor_counts, held_at_gate, idle_cause, idle_dead, judge_extension,
                         kept_families, merged_key, needs_roots, params_of, record_verdict, revalidation_owed,
                         robust_at_stress, screen_best, short_dead, train_record, validation_drift_failed, with_roots)
from .store import CLOSEABLE, SwarmStore

UNIVERSE_ROTATION = ("SPY", "QQQ", "IWM", "SPXW")
INDEX = ("XSP", "SPXW")
#: Never added by a fork (the sprint, Sept 26): XSP's $0.50 a contract makes narrow XSP structures uneconomic.
NOT_ROTATED = ("XSP",)
#: `IDLE_CAUSE` (researcher.py, re-exported here) is the words of an UNTESTED idle-rule death; a tested one carries its
#: verdict (R11-1, `researcher.idle_cause`).

#: THE COHORT KEEP (L1, the module docstring): `tournament.incubator_keep_max`'s default (the key absent). A number reads
#: as its whole part, at most `KEEP_CEILING`; 0 or below, or anything that is not a finite number (null, a boolean, a
#: string), turns it off, as `retire_every_seconds` does.
KEEP_MAX = 12
KEEP_CEILING = 96
#: The incubator's pre-registered practice sample (its money row's `min_sessions` and `min_trades`, the House's cohort
#: target `observe_min_sessions` and `observe_min_trades`): before a cohort meets it, its record is not judged; once it
#: does, it is kept only while that record is not negative, and first (a test holds these equal to the House's).
KEEP_SAMPLE_SESSIONS = 3
KEEP_SAMPLE_TRADES = 10
#: A cohort the House has not practised on this many sessions (`practice.cohort_status` `unpracticed`: left out by
#: `observe_max` or the roots cap, a Train cohort with `observe_train` off, or shed) is not kept, while the House
#: practises another active cohort (with none practised, the House is down or `live.observe` is off: an outage keeps them).
KEEP_UNPRACTICED = 2
#: When the practice record cannot be read, the last keep read stands this long, never longer: a record that stays
#: unreadable gives every family main's rules again (and one alert). Counted from the last good read, by this process or,
#: for a fresh one, by the process that saved `practice.KEEP_KV` (`Tournament.incubator_keep`).
KEEP_STALE_SECONDS = 3600.0


def _sample_met(r: Mapping[str, Any]) -> bool:
    """A cohort row (`practice.cohort_status`) that met the incubator's sample before today."""
    return (r.get("sessions") is not None and int(r["sessions"]) >= KEEP_SAMPLE_SESSIONS
            and int(r["closes_program"]) >= KEEP_SAMPLE_TRADES)


def _negative(r: Mapping[str, Any]) -> bool:
    """A cohort row whose program-closed or all-closes P&L before today is below zero, to the cent."""
    return round(float(r["pnl_program"]), 2) < 0 or round(float(r["pnl_all"]), 2) < 0


def incubator_held(root: Any, rows: list[Mapping[str, Any]],
                   alive: Mapping[str, Any] | set[str] | frozenset[str]) -> frozenset[tuple[str, int]]:
    """THE INCUBATOR'S COHORTS in THE COHORT KEEP (L1 beside the House's L2' keep and pins, `league/live/incubator.py`):
    the (family, version) of the active cohorts `rows` whose family is in `alive` that the House's incubator can pin, as
    far as the swarm can see. Each met the incubator's sample with a record before today that is not negative,
    and the swarm's own incubator facts admit its program (`bands.incubator`, the very reader the House pins by,
    read-only: alive, Gym band, a current Train-and-drift mark, a passed review and audit, no bar), with the row's run
    sha the cohort's. Every cohort the House pins is one of these: a pin needs a first look that passed on that sample,
    a re-check that still passes (program and all closes above $0 before today), and those facts with the snapshot's
    run sha. The swarm never reads the House's live state (its first-look verdicts and pins sit beside its real book),
    so it cannot tell which of these were pinned; it holds them all. A cohort whose facts cannot be read is held (fail
    open for keeping a cohort, as the House's L2' keep: research attention only). Never raises."""
    if root is None:
        return frozenset()
    from .bands import incubator as facts_of

    held: set[tuple[str, int]] = set()
    for r in rows:
        try:
            if r["family"] not in alive or not _sample_met(r) or _negative(r):
                continue
            key = (str(r["family"]), int(r["version"]))
        except (KeyError, TypeError, ValueError):
            continue
        try:
            facts = facts_of(root, family=key[0], version=key[1])
        except Exception:  # noqa: BLE001 - the swarm store unreadable for a moment: kept, never retired on it
            held.add(key)
            continue
        if r.get("run_sha") and any(isinstance(f, Mapping) and f.get("run_sha") == r.get("run_sha") for f in facts):
            held.add(key)
    return frozenset(held)


def keep_order(rows: list[Mapping[str, Any]], alive: Mapping[str, Any] | set[str] | frozenset[str],
               cap: int, *,
               held: set[tuple[str, int]] | frozenset[tuple[str, int]] = frozenset()) -> list[dict[str, Any]]:
    """THE COHORT KEEP's choice (pure): of the active cohorts `rows` (`practice.cohort_status`, each record before today),
    each one whose family is in `alive` (the living Gym families), whose session window has not run out (`elapsed <
    window`), that the House is practising (`unpracticed < KEEP_UNPRACTICED`, unless it practises no active cohort at
    all: an outage) and that the incubator can look at
    (`sessions` known), and that either has not met the incubator's sample (`KEEP_SAMPLE_SESSIONS` completed sessions and
    `KEEP_SAMPLE_TRADES` program closes) or has a record that is not negative (`pnl_program >= 0` and `pnl_all >= 0`, to
    the cent). Ordered: THE INCUBATOR'S COHORTS (`held`, (family, version) from `incubator_held`: the sample met), by
    return on risk, highest first; then the rest that met the sample, the same way; then the rest whose record so far
    is not negative; then the rest; each then by the practice league's order (`bands.priority`), then by version. One
    row a family (its first), at most `cap`, except that the incubator's cohorts are never cut by the cap (at most
    `KEEP_CEILING`), so the keep never holds fewer families than the House's incubator can have pinned and a pinned
    family is never dropped for a higher return; `cap` 0 or below keeps none. Each row gains `sample`, `negative` and
    `held`."""
    from .bands import priority

    # The House practising no active cohort at all (down, or `live.observe` off) is an outage, not a cohort left out: the
    # unpractised rule waits for it (the window still bounds the keep).
    practising = any(int(r.get("unpracticed") or 0) < KEEP_UNPRACTICED for r in rows)
    ranked = []
    for r in rows:
        if r["family"] not in alive or r.get("sessions") is None:
            continue
        if int(r["elapsed"]) >= int(r["window"]) or (practising and int(r.get("unpracticed") or 0) >= KEEP_UNPRACTICED):
            continue
        negative = _negative(r)
        sample = _sample_met(r)
        if sample and negative:
            continue
        mine = sample and (str(r["family"]), int(r["version"])) in held
        ror = r.get("return_on_risk") if sample else None
        head = (int(not mine), ror is None, -float(ror or 0.0)) if sample else (2 + int(negative), False, 0.0)
        ranked.append((head + tuple(priority(r)) + (int(r["version"]),),
                       {**dict(r), "sample": sample, "negative": negative, "held": mine}))
    ranked.sort(key=lambda x: x[0])
    cap = max(0, int(cap))
    out: list[dict[str, Any]] = []
    for _, row in ranked:
        # The incubator's cohorts come first, so the cap cuts only the rest.
        if cap == 0 or len(out) >= (max(cap, KEEP_CEILING) if row["held"] else cap):
            break
        if all(row["family"] != o["family"] for o in out):
            out.append(row)
    return out


class Tournament:
    def __init__(self, store: SwarmStore, pool: Any, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time,
                 rng: random.Random | None = None):
        self.store = store
        self.pool = pool
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.Random()
        self.allocation: dict[str, Any] = {}  # the last allocation's report (`allocate`; allocation.py's `value_shares`)
        #: The families the last allocation named useful experiments (THE CONCURRENCY, allocation.py): none under the bandit.
        self.useful: frozenset[str] = frozenset()
        self.idle_at = float("-inf")  # the last idle pass (`idle_due`); in memory: a restarted swarm runs one at once
        self.practice_bonus: dict[str, float] = {}  # the last allocation's practice bonus by family (`allocate`)
        # THE COHORT KEEP (L1, `incubator_keep`), in memory: the last good read (when, the families, their rows; -inf
        # until this process has read, or taken the saved keep), how the last read went ("ok", "stale", "failed" or
        # "off"), and each kept family's spared rule since the round's event.
        self.kept_at = float("-inf")
        self.kept: frozenset[str] = frozenset()
        self.kept_rows: list[dict[str, Any]] = []
        self.keep_read = "off"
        self.keep_error: str | None = None  # why the last read failed ("stale" or "failed")
        self.keep_spared: dict[str, str] = {}
        self._keep_told = False

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("tournament", {})

    def due(self) -> bool:
        last = float(self.store.get("tournament_at", 0.0) or 0.0)
        return self.clock() - last >= float(self.cfg.get("every_seconds", 3600))

    # ------------------------------------------------------------------ 1-2. validation and the line
    def played(self, fam: Mapping[str, Any]) -> bool:
        """THE LEARNING GAME's rules apply to this family: mode "gate" and the game arm (`game.arm`). False with the game
        off, in "shadow", for a control or legacy family, and on any error (today's rules then)."""
        try:
            return game.cfg(self.settings)["mode"] == "gate" and game.arm(self.store, fam, self.settings) == "game"
        except Exception:  # noqa: BLE001
            return False

    def candidate_version(self, fam: Mapping[str, Any]) -> int | None:
        if self.played(fam):
            try:  # THE LEARNING GAME: its latest CONFIRMED version, none without one (also `judge`'s stale check)
                return game.candidate(self.store, fam)
            except Exception:  # noqa: BLE001 - on the dispatcher's thread too (`judge`): no Validation on an error
                return None
        if fam.get("best_version"):
            return int(fam["best_version"])
        state = fam.get("state") or {}
        return int(state["best_train_version"]) if state.get("best_train_version") else None

    def validate(self, fams: list[dict[str, Any]], *, timeout: float = 3000.0) -> dict[str, Any]:
        """Queue validation for every family with an unvalidated best; wait; judge. One job a family: the Gym runs
        the 1.5x-stress twin itself and carries its figures as `stress_1.5` (a second trial, counted here)."""
        jobs = []
        errors = {}
        judged = {}
        inherited: dict[str, dict[str, Any]] = {}  # AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1): verdicts read, not run
        asked: set[tuple[str, str, tuple[str, ...]]] = set()  # this round's jobs by program: a twin reads the first's result
        twins: list[tuple[dict[str, Any], int, dict[str, Any]]] = []
        waiting: list[str] = []
        waiting_game: list[str] = []  # THE LEARNING GAME: no CONFIRMED version, or its tries used (owed no Validation)
        # THE DIRECTION LANE'S RATION (release D-1b): a direction lineage whose one Validation try is used is owed none
        # (`spent_lane`); and one try a lineage a round, so two members of one lineage never validate side by side
        # (`lane_lines`: the connected lineages that already have a job, a twin or a verdict this round).
        spent_lane: list[str] = []
        lane_waiting: list[str] = []
        calls_refused: list[str] = []  # a direction candidate whose code names another open (owed no Validation)
        always_in_refused: list[str] = []  # THE ALWAYS-IN CARD: a candidate with no G1 pass on record (owed no Validation)
        lane_lines: set[str] = set()
        drift: dict[str, list[str]] = {"waiting": [], "failed": []}
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        for fam in fams:
            # THE DRIFT SCREEN first: a candidate whose figures fail is demoted and the next one that passes stands in its place.
            drift["failed"] += [fam["id"]] * len(screen_best(self.store, fam["id"], self.settings, clock=self.clock))
            current = self.store.family(fam["id"])
            if current is None or current.get("retired_at"):
                continue
            fam = current
            n = self.candidate_version(fam)
            played = self.played(fam)
            if n is None:
                if played:
                    waiting_game.append(fam["id"])
                continue
            if played and not self.game_try_left(fam, n):
                waiting_game.append(fam["id"])
                continue  # THE LEARNING GAME: its Validation tries are used
            lines = self.lane_lines(fam)
            again = False  # the lineage's own try validated again in place of a candidate that moved on (below)
            if lines is not None:
                # THE DIRECTION LANE'S RATION (release D-1b): one Validation try a direction lineage (`dlane.try_open`: a
                # version already its lineage's try may be validated again on a new Gym image), and one a round.
                if not dlane.try_open(self.store, fam, n, self.settings):
                    # THE LINEAGE'S TRY, VALIDATED AGAIN (release D-1b, the review's finding 1, Oct 9, 2026): the researcher
                    # moved the candidate on (a submit, a better Train run) while the try's job was out or before its look,
                    # and the try is owed a verdict on the Gym in use (`dlane.try_owed`: its result was stale, or the
                    # verdict that entered the gate is on another image). That version is validated, never the candidate,
                    # and no new try is spent: the try's Train checks below were met when it was first sent.
                    owed = dlane.try_owed(self.store, fam, self.settings, image=image, bundle=bundle)
                    if owed is None:
                        spent_lane.append(fam["id"])
                        continue
                    n, again = owed, True
                if lines & lane_lines:
                    lane_waiting.append(fam["id"])
                    continue
            state = fam.get("state") or {}
            from .evaluator import KEY, row_matches

            # A startup adoption clears cached bests. Defense in depth for an old submission
            # restored or arriving late: no current validation is bought with stale Train evidence.
            current_evaluator = self.store.get(KEY)
            if current_evaluator is not None and not again:
                run_ids = [state.get("submitted_run"), state.get("best_train_run")]
                if played:  # THE LEARNING GAME: the seen Train run its ladder look recorded
                    run_ids.append(self._game_read(game.look_seen_run, fam, n))
                eligible_train = any(row is not None and row.get("version") == n and row_matches(self.store, row, current_evaluator)
                                     for row in (self.store.run(str(rid)) for rid in run_ids if rid))
                if not eligible_train:
                    waiting.append(fam["id"])
                    continue
            if not again and self.cfg.get("require_robustness", True) and not robust_at_stress(state, n) \
                    and not (played and self._game_read(game.seen_robust_ok, fam, n)):
                waiting.append(fam["id"])  # its robustness run at 1.5x has not landed (or lost): not validated yet
                continue
            if n == fam.get("validated_version") and state.get("validation_image") == image and state.get("validation_bundle") == bundle:
                continue
            screen = drift_verdict(self.store, fam, n, self.settings)
            if screen is not None and not screen["passed"]:
                # A version whose Train run predates the figures waits for its run again (the researcher's robustness label
                # "drift"); one that fails was demoted above, so this is a candidate the demotion could not replace. Before
                # the image/engine reset below: a validated family owed re-validation keeps its gate_ready (its idle-rule
                # exemption and the operator's hold) while its figures are made.
                drift["failed" if screen["known"] else "waiting"].append(fam["id"])
                continue
            if state.get("validation_image") != image or state.get("validation_bundle") != bundle:
                self.store.compare_and_set_state(fam["id"], {"validation_image": state.get("validation_image"),
                                                           "validation_bundle": state.get("validation_bundle")}, gate_ready=False)
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            if lines is not None:
                # THE CALLS-ONLY CODE CHECK (release D-1b, the review's finding 3; `dlane.calls_only_code`): a direction
                # version whose code names a put, a short leg or any open but long_call is never validated, so it spends
                # no try, opens no tuition (tuition reads the Validation line) and never reaches the gate. The researcher
                # refuses such a program before any version; this holds for one made while the lane was off.
                if dlane.calls_only_code(version["code"], version.get("params") or {}) is not None:
                    calls_refused.append(fam["id"])
                    continue
                # THE ALWAYS-IN CARD's G1 (Oct 10, 2026; `dlane.always_in_try`): an always-in family's version is validated
                # only with a G1 pass on record (its score's, else its Train run's own reading), so a program that did not
                # enter on the clock alone spends no try (the family retires: `_why`, `dlane.always_in_failed`), and one
                # with no reading waits. The lineage's own try validated again (`again`) was checked when it was sent.
                if not again and dlane.always_in_try(self.store, fam, n, self.settings) is not None:
                    always_in_refused.append(fam["id"])
                    continue
                lane_lines.update(lines)  # this direction lineage's try for the round (whichever way it is judged below)
            recorded = self.recorded_validation(fam["id"], n)
            if recorded is not None:  # validated before (a best submitted again): judged from its result, no new trial
                row = self.judge(fam["id"], n, recorded, record=False)
                if row is not None:
                    judged[fam["id"]] = row
                continue
            if self.reuse_validations():
                # AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1): a fork or a revival that carries its parent's program
                # unchanged takes the verdict of the validation that program already had on this Gym; no job, no trial.
                known = self.known_validation(fam, version)
                if known is not None:
                    row = self.judge(fam["id"], n, known[0], record=False, inherited=known[1])
                    if row is not None:
                        judged[fam["id"]] = row
                        inherited[fam["id"]] = known[1]
                    continue
                program = self.program_key(fam, version)
                if program in asked:
                    twins.append((fam, n, version))  # the same program is asked this round: it reads that result below
                    continue
                asked.add(program)
            job = GymJob(family=fam["id"], version=n, code=version["code"], params=version["params"], window="validation",
                         roots=needs_roots(version["code"], fam["roots"]), stress=1.0, purpose="validation", priority=1.0)
            if (self.store.family(fam["id"]) or {}).get("retired_at"):
                continue
            jobs.append((fam, n, self.pool.submit(job)))
        deadline = self.clock() + timeout
        for fam, n, job in jobs:
            try:
                result = self.pool.wait(job, max(1.0, deadline - self.clock()),
                                        late=lambda r, fid=fam["id"], n=n: self.judge(fid, n, r))
            except PoolError as exc:
                errors[fam["id"]] = str(exc)[:300]
                continue
            row = self.judge(fam["id"], n, result)
            if row is not None:
                judged[fam["id"]] = row
        waiting_twin: list[str] = []
        for fam, n, version in twins:
            # Its twin's job is back: the verdict is read from that result now. One that failed or is still out leaves
            # this family for the next round (its twin's result, or its own job then).
            known = self.known_validation(fam, version)
            row = self.judge(fam["id"], n, known[0], record=False, inherited=known[1]) if known is not None else None
            if row is None:
                waiting_twin.append(fam["id"])
                continue
            judged[fam["id"]] = row
            inherited[fam["id"]] = known[1]  # type: ignore[index]
        out = {"queued": len(jobs), "judged": judged, "errors": errors, "waiting_robustness": waiting,
               "waiting_drift": drift["waiting"], "failed_drift": sorted(set(drift["failed"]))}
        if inherited or waiting_twin:
            out.update(inherited=inherited, waiting_twin=waiting_twin)
        if waiting_game:  # the ops' stall check reads it: a game-arm best is owed no Validation without a CONFIRM
            out["waiting_game"] = waiting_game
        if spent_lane:  # THE DIRECTION LANE'S RATION (release D-1b): its lineage's one try is used: owed no Validation
            out["spent_lane"] = spent_lane
        if lane_waiting:  # another member of its direction lineage took this round's try: the next round reads its verdict
            out["waiting_lane"] = lane_waiting
        if calls_refused:  # its candidate names another open than a long call: owed no Validation until a calls-only one
            out["calls_refused"] = calls_refused
        if always_in_refused:  # THE ALWAYS-IN CARD: its candidate has no G1 pass on record: owed no Validation
            out["always_in_refused"] = always_in_refused
        return out

    def lane_lines(self, fam: Mapping[str, Any]) -> set[str] | None:
        """THE DIRECTION LANE'S RATION (release D-1b): a direction family's connected lineages (the set its tries and looks
        are counted over), or None for every alpha family and every family while the lane is off (nothing is read)."""
        if dlane.lane_of(self.store, fam, self.settings) != dlane.DIRECTION:
            return None
        row = self.store._one("SELECT lineage FROM families WHERE id=?", (fam["id"],))
        return set(self.store._connected_lineages(row["lineage"])) if row else {str(fam["id"])}

    def _game_read(self, read: Callable[..., Any], fam: Mapping[str, Any], n: Any) -> Any:
        """One of the game's reads of a version (`game.look_seen_run`, `game.seen_robust_ok`), None on an error."""
        try:
            return read(self.store, fam, n)
        except Exception:  # noqa: BLE001
            return None

    def game_try_left(self, fam: Mapping[str, Any], n: int) -> bool:
        """THE LEARNING GAME's Validation tries (`game.validations_left`): one is left, or version `n` was validated before
        (an adoption's re-validation of it is no new try). False on an error (no Validation)."""
        try:
            return game.validations_left(self.store, fam, self.settings) > 0 or \
                bool(self.store.version_runs(fam["id"], int(n), window="validation", stress=1.0, limit=1))
        except Exception:  # noqa: BLE001
            return False

    def reuse_validations(self) -> bool:
        """`tournament.reuse_validations` (true, F1): AN IDENTICAL PROGRAM IS VALIDATED ONCE; JSON false validates every
        family's version by itself, as before."""
        return self.cfg.get("reuse_validations", True) is not False

    @staticmethod
    def program_key(fam: Mapping[str, Any], version: Mapping[str, Any]) -> tuple[str, str, tuple[str, ...]]:
        """A version's program as Validation runs it: its code (the sha), its merged params (`researcher.merged_key`: `{}`
        and a default spelled out are one program) and the roots it runs on (`needs_roots`, sorted)."""
        code = str(version.get("code") or "")
        return (str(version.get("sha") or ""), merged_key(params_of(code) or {}, dict(version.get("params") or {})),
                tuple(sorted(str(r).upper() for r in needs_roots(code, fam["roots"]))))

    def known_validation(self, fam: Mapping[str, Any], version: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1, Oct 3, 2026: 136 of 742 Validation runs repeated a result already
        known, and a fork and a revival reproduced their parents' results to the cent). (the full result, where it is
        from) of a validation another family's version made of the same program (`program_key`: the same code, merged
        params and roots) on the Gym image and bundle in use now, the newest; None when there is none. The same program
        on the same data and engine answers the same, so the verdict is judged from that result by the line as it
        stands for this family (`judge` with `inherited`: no Gym job, no trial, no new validated version in the
        lineage's count; the family keeps its own copy of the record, a row with no trial, so the gate and every
        later round read it as they read any validation). Another image or bundle is another Gym: that result is not
        reused."""
        sha = str(version.get("sha") or "")
        if not sha or not version.get("code"):
            return None
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        want = self.program_key(fam, version)
        for other in self.store._all("SELECT family, n FROM versions WHERE sha=? AND family!=? ORDER BY created_at DESC, family, n",
                                     (sha, fam["id"])):
            twin_family = self.store.family(other["family"])
            twin = self.store.version(other["family"], other["n"])
            if twin_family is None or twin is None or not twin.get("code") or self.program_key(twin_family, twin) != want:
                continue
            for row in self.store.version_runs(other["family"], int(other["n"]), window="validation", stress=1.0, limit=20):
                if not row.get("path"):
                    continue
                result = self.store.run_result(row["run_id"])
                if result is not None and result.get("gym_image") == image and result.get("gym_bundle") == bundle:
                    return result, {"family": other["family"], "version": int(other["n"]), "run": row["run_id"]}
        return None

    def recorded_validation(self, fid: str, n: int) -> dict[str, Any] | None:
        """The full result of a validation this version already had on the Gym image in use now (the same program on the
        same code and data answers the same; another image may hold other days, so its result is not reused)."""
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        for row in self.store.runs(fid, window="validation", limit=500):
            if row.get("version") == n and float(row.get("stress") or 1.0) == 1.0 and row.get("path"):
                result = self.store.run_result(row["run_id"])
                if result is not None and result.get("gym_image") == image and result.get("gym_bundle") == bundle:
                    return result
        return None

    def judge(self, fid: str, n: int, result: Mapping[str, Any], *, record: bool = True,
              inherited: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        """Record a validation result (and its stress twin: two trials) and judge it by the line. Also called for a
        result that lands after the round stopped waiting: every evaluation counts. Its verdict is written only while
        `n` is still the family's candidate (the researcher's current best): a result for a version the family has
        moved on from is stale, whatever its number. `record=False` re-judges a result already recorded. `inherited`
        (F1, with `record=False`): the result is another family's validation of the same program (`known_validation`);
        the verdict is this family's validation all the same (its count and its idle clocks), its state says where it
        is from, and the result is kept as this family's own rows WITH NO TRIAL (it and its stress twin, their summaries
        naming the source): nothing was evaluated, so no trial, no lineage count and no program-year moves."""
        fam = self.store.family(fid)
        if fam is None:
            return None
        if inherited is not None and not record:
            copy = {**result, "trials": 0, "summary": {**(result.get("summary") or {}), "inherited": dict(inherited)}}
            row = self.store.add_run(fid, n, copy, window="validation", stress=1.0, purpose="validation")
            if isinstance(result.get("stress_1.5"), dict):
                twin = result["stress_1.5"]
                self.store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": twin.get("status") or "ok", "trials": 0,
                                            "summary": {**dict(twin), "inherited": dict(inherited)}}, window="validation",
                                   stress=evidence.STRESS, purpose="validation")
        if record:
            years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
            row = self.store.add_run(fid, n, result, window="validation", stress=1.0, purpose="validation", program_years=years)
            if isinstance(result.get("stress_1.5"), dict):
                twin = result["stress_1.5"]
                self.store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": twin.get("status") or "ok", "trials": 1,
                                            "summary": dict(twin)}, window="validation", stress=evidence.STRESS, purpose="validation",
                                   program_years=years)
        with self.store.atomic():  # also exclude another connection retiring the family while this verdict writes
            fam = self.store.family(fid) or fam
            image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
            # THE DIRECTION LANE'S RATION (release D-1b, the review's finding 1, Oct 9, 2026): a direction lineage's one
            # Validation try is judged even when the researcher moved the family's candidate on while its job was out.
            # Its run is the lineage's try whatever happens (`dlane.lineage_tries`), so dropping its verdict as stale
            # spent the try with no verdict and no look, and retired the family (SPENT_TRY). The gate looks at the
            # version validated (`validation_version`), so the try's own version goes to the gate. A result from another
            # Gym image or bundle is still stale (`dlane.try_owed` has the try validated again on the current one).
            moved = self.candidate_version(fam) != int(n) and self.lane_try(fid, fam, n, result) is not True
            if fam.get("retired_at") or moved or result.get("gym_image") != image or result.get("gym_bundle") != bundle:
                return None  # stale: its trials count, its verdict does not
            return self._verdict(fid, fam, n, result, counted=record or inherited is not None, inherited=inherited)

    def _verdict(self, fid: str, fam: Mapping[str, Any], n: int, result: Mapping[str, Any], *, counted: bool,
                 inherited: Mapping[str, Any] | None = None) -> dict[str, Any]:
        lane_try = self.lane_try(fid, fam, n, result)
        if lane_try is False:
            # THE DIRECTION LANE'S RATION, the backstop (release D-1b): a second try of a direction lineage that raced past
            # `dlane.try_open` (a result landing late) is recorded (its rows and trials, above) and never judged into the
            # family's state, so it can neither enter the gate nor displace the lineage's own try there.
            self.store.event("swarm.status", fid, {"action": "lane_try_refused", "version": int(n),
                                                   "why": "not its direction lineage's one Validation try"})
            return {"version": n, "passed": False, "refused": "not its direction lineage's one Validation try"}
        stressed = evidence.stressed_of(result)
        validated, sharpes = 1, []  # FAST LANE V2 (D1): the deflated Sharpe's N is the program itself, never the lineage's history
        line = evidence.validation_line(result, stressed, validated_versions=validated, version_sharpes=sharpes,
                                        lineage_trials=self.store.lineage_trials(fid))
        view = diagnostics.validation_view(result, line)
        summary = result.get("summary") or {}
        mean = evidence.daily_mean(summary)
        t = evidence.daily_t(summary)
        improved = mean is not None and (fam.get("best_validation") is None or float(mean) > float(fam["best_validation"]))
        fields: dict[str, Any] = {"validated_version": n}
        if improved:
            fields.update(best_validation=float(mean), since_val_revisions=0, since_val_trials=0)
        self.store.update_family(fid, **fields)
        if counted:  # a re-judged recorded result is no new validation for the bandit (nor for the idle rule)
            self.store.bump(fid, validations=1)
            # The idle rule counts the Gym evaluations since the last validation from here (`researcher.idle_evaluations`);
            # `fam` was read after this validation's own trials were recorded. Its dormancy clause starts again too: a
            # verdict is news the researcher may act on (`researcher.dormant_count`).
            # THE DEPTH RULE (F1, `researcher.short_dead`) counts the family's cycles from here too.
            self.store.set_state(fid, validated_trials=int(fam.get("trials") or 0), dormant_cycles=0,
                                 **{VALIDATED_CYCLES_KEY: int(fam.get("cycles") or 0)})
        state = fam.get("state") or {}
        typical = dict(state.get("typical_by_version") or {})
        if state.get("validation_version") is not None and state.get("typical_max_loss_usd") is not None:
            typical.setdefault(str(state["validation_version"]), state["typical_max_loss_usd"])
        loss = typical_max_loss(result)
        if loss is not None:
            typical[str(n)] = loss
        sigma = self.sigma_fields(state, n, summary)
        precheck = self.precheck_entry(fam, line, summary)
        entered = bool(line["passed"]) or precheck
        lane_fields: dict[str, Any] = {}
        if lane_try is True:  # the lineage's one try (release D-1b): what `dlane.lineage_spent` reads
            lane_fields[dlane.TRY_KEY] = {"version": int(n), "at": self.store.now(), "first": True, "entered": entered}
        from .evaluator import KEY

        # THE VALIDATED-FAMILY GUARD's record (`researcher.retire_guard`): this version's latest verdict and the evaluator
        # it was judged under, kept across adoptions, so a version's pass archived by one is known refuted only by a
        # failure under the evaluator in force, even after another version's validation replaced the line below.
        # A DIRECTION VERDICT SAYS HOW IT WAS SCREENED (Oct 10, 2026; the readiness audit's M5): `passed` stays the
        # Validation line's answer (the guard, the tuition and the alpha lane read it), and a direction family's verdict
        # also records `entered` (the line, or D2's Validation pre-check: it went to the gate) and the lane's `screen` in
        # force ("D2" or "S-C"). Until now a D2 pre-check entry read as a failed Validation everywhere it was counted
        # (eqp-realcalm-drift-call reached Probe with `validation_verdicts` {"17": passed false}): the daily funnel
        # (league/ops/funnel.py), the dlane report's lane funnel and its A3 gate-wait alarm. An alpha family's verdict,
        # and every verdict while the lane is off, is written exactly as before.
        screened = self.lane_screen(fam)
        verdicts = record_verdict(state, n, bool(line["passed"]), evaluator=self.store.get(KEY), at=self.store.now(),
                                  **({"entered": entered, "screen": screened} if screened is not None else {}))
        source = inherited if inherited is not None else summary.get("inherited")
        self.store.set_state(fid, validation_view=view, validation_line=line, validation_version=n,
                             validation_verdicts=verdicts,
                             validation_image=result.get("gym_image"),
                             validation_bundle=result.get("gym_bundle"),
                             typical_max_loss_usd=loss, typical_by_version=typical, **sigma,
                             validation_numbers={"mean": mean, "t": t, "sharpe_daily": summary.get("sharpe_daily"),
                                                 "quarters": summary.get("quarters_positive")},
                             # AN IDENTICAL PROGRAM IS VALIDATED ONCE (F1): whose validation this verdict was read from
                             # (None for the family's own), for the version `validation_version` names; its own copy
                             # of the record says so too, so a later re-judging keeps it.
                             validation_inherited=dict(source) if isinstance(source, Mapping) else None,
                             gate_ready=entered and not self.gate_spent(fid, n, state), **lane_fields)
        out = {"version": n, "passed": line["passed"], "mean": mean, "t": t}
        if screened is not None:  # M5 (above): the round's verdict row, which the funnels count
            out.update(entered=entered, screen=screened)
        if inherited is not None:
            out["inherited"] = dict(inherited)
        # THE EXTENSION HOLD (R11-4's swarm rule): a version that met `researcher.extension_hold_checks` of the line's checks
        # waits for its 2017-19 extension result, exempt from the dormancy clause, until the operator clears the flag. A
        # validation of the held version below the checks ends its hold (`judge_extension`); the verdict row says which.
        change = judge_extension(self.store, fid, n, line, self.settings, clock=self.clock)
        if change == "held":
            out["extension_hold"] = True
        elif change == "lapsed":
            out["extension_lapsed"] = True
        return out

    def lane_try(self, fid: str, fam: Mapping[str, Any], n: int, result: Mapping[str, Any]) -> bool | None:
        """THE DIRECTION LANE'S RATION at a verdict (release D-1b): None for every alpha family, every family while the lane
        is off and a run the Gym could not make (`dlane.NOT_A_TRY`: no try); True when version `n` is its direction
        lineage's one Validation try (`dlane.first_try`, its rows already recorded); False for any other try (it raced
        past `dlane.try_open`: `_verdict` records nothing of it)."""
        if dlane.lane_of(self.store, fam, self.settings) != dlane.DIRECTION:
            return None
        if str(result.get("status") or "") in dlane.NOT_A_TRY:
            return None
        return dlane.first_try(self.store, fid, n, self.settings)

    def sigma_fields(self, state: Mapping[str, Any], n: int, summary: Mapping[str, Any]) -> dict[str, Any]:
        """THE SIGMA WRITER (release D-1, Oct 9, 2026; the operator's decision 4, for release L-D's DM1, which reads it in
        league/live/families.py `validation_r_sd`): the sd of per-trade P&L per dollar of maximum loss in version `n`'s
        Validation run (`dlane.validation_r_sd`: |mean| x sqrt(trades) / |t|, from this run's summary), kept beside
        `typical_max_loss_usd` in the same two shapes, so the banded version's figure survives a newer validation:
        `validation_r_sd_by_version[str(n)]` and `validation_r_sd` (the version `validation_version` names). A figure that
        is not finite and above zero is OMITTED: no key for `n` in the map, and the scalar left unwritten (or written None
        over an older version's, which `validation_version` moving on to `n` would otherwise make `n`'s); DM1 then reads
        the forward record's sd, else its fallback. While `dlane.mode` is "off" nothing is written (THE ROLLBACK). A map
        that cannot be read starts empty."""
        if not dlane.on(self.settings):
            return {}
        sd = dlane.validation_r_sd(summary)
        held = state.get("validation_r_sd_by_version")
        by_version = {str(k): v for k, v in held.items()} if isinstance(held, Mapping) else {}
        if sd is None:
            by_version.pop(str(n), None)
        else:
            by_version[str(n)] = sd
        out: dict[str, Any] = {}
        if by_version or "validation_r_sd_by_version" in state:
            out["validation_r_sd_by_version"] = by_version
        if sd is not None or "validation_r_sd" in state:
            out["validation_r_sd"] = sd
        return out

    def precheck_entry(self, fam: Mapping[str, Any], line: Mapping[str, Any], summary: Mapping[str, Any]) -> bool:
        """D2'S VALIDATION PRE-CHECK (release D-1; PLAN D6, the operator's decision 6): True when a DIRECTION family's
        version that missed the Validation line goes to the gate all the same, because the screen in force for its lane is
        D2 (`dlane.screen_effective` "precheck": only behind `dlane.screen` "D2" with a receipt sha256 and its `c` pinned
        in the repository's policy.json, else refused) and the pre-check passes (`dlane.d2_precheck`). The line itself is
        left as judged, so its tuition is not opened (`bands.read` reads `validation_line`), and the gate judges the look
        by D2's pooled test. False for every alpha family, every version that met the line, and while the lane is off."""
        if line.get("passed") or not dlane.on(self.settings):
            return False
        lane = dlane.lane_of(self.store, fam, self.settings)
        if lane != dlane.DIRECTION or dlane.screen_effective(self.settings, lane)["validation"] != "precheck":
            return False
        return bool(dlane.d2_precheck(summary)["passed"])

    def lane_screen(self, fam: Mapping[str, Any]) -> str | None:
        """The screen a DIRECTION family's verdict is recorded under (M5, `_verdict`): the lane's screen in force
        (`dlane.screen_effective`: "D2", or "S-C" when D2 is not chosen or is refused). None for every alpha family and
        while the lane is off, whose verdicts carry no screen."""
        if not dlane.on(self.settings):
            return None
        lane = dlane.lane_of(self.store, fam, self.settings)
        if lane != dlane.DIRECTION:
            return None
        return str(dlane.screen_effective(self.settings, lane)["screen"])

    def gate_spent(self, fid: str, n: int, state: Mapping[str, Any]) -> bool:
        """The gate is done with version `n` (R4, the verification of PR #402): its holdout look was made or the gate refused
        it (`gated_sha`), so the gate never takes it up again (`Gate.run` skips it). Validated again after a Gym deploy, it
        does not go back to `gate_ready`, which would keep it from the idle rule with nothing ever to look at."""
        from .gate import run_sha  # a local import: the tournament only reads the gate's mark

        version = self.store.version(fid, n)
        if version is None or not version.get("sha"):
            return False
        sha = run_sha(version)
        return bool(self.store.looked(sha) or state.get("gated_sha") == sha)

    def incubator_facts(self) -> dict[str, Any]:
        """THE INCUBATOR'S TRAIN AND DRIFT MARKS (`incubator.facts`, step 2 of the round), never failing the round: an error
        is one private `swarm.status` event and the marks wait for the next round."""
        try:
            return incubator.facts(self.store, self.settings, self.store.root, clock=self.clock)
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.status", None, {"action": "incubator_facts_error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return {"error": type(exc).__name__}

    # ------------------------------------------------------------------ 3. the allocation
    def allocate(self, fams: list[dict[str, Any]]) -> dict[str, float]:
        """Each living family's share of researcher turns and Gym priority (`families.weight`). THE ALLOCATOR
        (league/swarm/allocation.py, Release B; `allocation.mode` "value"): expected information value with an explicit
        exploration share split by mechanism class, and caps on a family's and a class's share; "bandit" is R11-5's
        Thompson bandit below. The practice bonus rides on either. The round's event records the report (`allocation`)."""
        from . import allocation

        if allocation.cfg(self.settings)["mode"] == "value":
            try:
                shares, report = allocation.allocate_from_store(self.store, fams, self.settings, now=self.clock())
            except Exception as exc:  # noqa: BLE001 - a round never fails on its allocation: the bandit answers, and says why
                self.allocation = {"mode": "bandit", "fallback": f"{type(exc).__name__}: {str(exc)[:200]}"}
                self.useful = frozenset()
                return self.bandit(fams)
            self.useful = frozenset(report.pop("useful_ids", ()) or ())  # kept here, out of the round's event
            shares, self.practice_bonus = practice.apply_bonus(shares, self.store, self.settings)
            report["practice_bonus"] = dict(self.practice_bonus)
            self.allocation = report
            for fid, share in shares.items():
                self.store.update_family(fid, weight=share)
            return shares
        self.allocation = {"mode": "bandit"}
        self.useful = frozenset()
        return self.bandit(fams)

    def bandit(self, fams: list[dict[str, Any]]) -> dict[str, float]:
        """R11-5's Thompson bandit (`allocation.mode` "bandit"): the allocation before Release B."""
        rows = []
        for fam in fams:
            # A validated version that failed the drift screen earns no share by its validation: it counts as unvalidated.
            nums = {} if validation_drift_failed(fam) else (fam.get("state") or {}).get("validation_numbers") or {}
            rows.append({"id": fam["id"], "validations": fam.get("validations") or 0, "mean": nums.get("mean"), "t": nums.get("t")})
        # R11-5: the exploit pool is the old families with a positive validation mean; each earns at most
        # `tournament.exploit_per_positive` (0.15) of the share, the rest is the explore pool's (null: `explore_share` alone).
        per = self.cfg.get("exploit_per_positive", evidence.EXPLOIT_PER_POSITIVE)
        per = float(per) if isinstance(per, (int, float)) and not isinstance(per, bool) else None
        shares = evidence.thompson(rows, explore_share=float(self.cfg.get("explore_share", 0.25)),
                                   new_validations=int(self.cfg.get("new_family_validations", 2)), rng=self.rng,
                                   exploit_per_positive=per)
        # THE PRACTICE BONUS (league/swarm/practice.py): a small, capped share for positive practice on live quotes. It
        # moves research attention only; the weight never reaches validation, the gate, the bands or money.
        shares, self.practice_bonus = practice.apply_bonus(shares, self.store, self.settings)
        for fid, share in shares.items():
            self.store.update_family(fid, weight=share)
        return shares

    # ------------------------------------------------------------------ 4. forks
    def forks(self, fams: list[dict[str, Any]]) -> list[str]:
        ceiling = int(self.settings.get("population", {}).get("ceiling", 96))
        alive = len(fams)
        if alive >= ceiling:
            return []
        now = self.clock()
        cooldown = float(self.cfg.get("fork_cooldown_hours", 6)) * 3600
        scored = []
        allowed = allowed_structures(self.settings)
        for fam in fams:
            if validation_drift_failed(fam):
                continue  # its validated version failed the drift screen: nothing to fork
            if self.played(fam):
                continue  # THE LEARNING GAME: the game's own children replace forks for the game arm (`game.reproduce`)
            if not self.lane_forks(fam):
                continue  # THE DIRECTION LANE'S RATION (release D-1b): a fork would join a lineage with no try left
            if fam["structure"] not in allowed:
                continue  # THE STRUCTURES (`architect.structures`): a type no birth may be does not breed; it researches on
            nums = (fam.get("state") or {}).get("validation_numbers") or {}
            t = nums.get("t")
            if isinstance(t, (int, float)) and t >= float(self.cfg.get("fork_min_t", 1.0)) and (nums.get("mean") or 0) > 0:
                if now - float((fam.get("state") or {}).get("forked_at") or 0) >= cooldown:
                    scored.append((float(t), fam))
        scored.sort(key=lambda x: -x[0])
        born = []
        for _, fam in scored[: int(self.cfg.get("fork_top", 3))]:
            if alive + len(born) >= ceiling:
                break
            with self.store.atomic():
                if len(self.store.families(alive=True)) >= ceiling:
                    break
                child = self.fork(fam)
            if child:
                born.append(child)
        return born

    def lane_forks(self, fam: Mapping[str, Any]) -> bool:
        """May `fam` fork under THE DIRECTION LANE'S RATION (release D-1b)? Always for an alpha family and while the lane is
        off. A direction family only while its lineage has a Validation try left (`dlane.lineage_tries` under
        `val_tries`): a fork joins its parent's lineage (its tries and its looks), so once the lineage's one try is used a
        fork could never be validated. A fork is offered only to a validated parent, so with one try a direction family
        never forks. An always-in direction family (THE ALWAYS-IN CARD, Oct 10, 2026) never forks."""
        if dlane.lane_of(self.store, fam, self.settings) != dlane.DIRECTION:
            return True
        try:
            # THE ALWAYS-IN CARD (Oct 10, 2026): never for an always-in family (a fork adds a root, and each root's always-in
            # idea has its own one try; with `val_tries` 1 no direction family forks anyway).
            if dlane.always_in_family(self.store, fam, self.settings):
                return False
            return len(dlane.lineage_tries(self.store, fam["id"])) < dlane.cfg(self.settings)["val_tries"]
        except Exception:  # noqa: BLE001 - an unreadable lineage forks nothing
            return False

    def fork(self, fam: Mapping[str, Any]) -> str | None:
        """A child on the parent's roots plus the next root of the rotation the parent does not trade (never XSP; index
        roots only for types allowed there; at most five roots), with the parent's best program, its NEEDS widened to
        the child's roots, as its first version. None for a parent of a type `architect.structures` leaves out."""
        fam = self.store.family(fam["id"]) or fam
        if fam.get("retired_at") or len(fam["roots"]) >= MAX_ROOTS or fam["structure"] not in allowed_structures(self.settings):
            return None
        roots = [str(r).upper() for r in self.settings.get("gym", {}).get("roots", UNIVERSE_ROTATION) if str(r).upper() not in NOT_ROTATED]
        taken = {tuple(sorted(f["roots"])) for f in self.store.families(alive=True) if f["mechanism"] == fam["mechanism"]}
        for root in roots:
            pooled = list(fam["roots"]) + [root]
            if tuple(sorted(pooled)) in taken or root in fam["roots"]:
                continue
            if root in INDEX and fam["structure"] in ("calendar", "diagonal"):
                continue
            best = self.store.version(fam["id"], self.candidate_version(fam))
            code = with_roots(best["code"], pooled) if best and best.get("code") else None
            spec = dict(fam.get("spec") or {})
            spec.update({"id": f"{fam['id'].split('-on-')[0]}-on-{root.lower()}", "mechanism": fam["mechanism"],
                         "structure": fam["structure"], "roots": pooled})
            spec.pop("signal", None)  # its first version is the parent's program on the pooled roots, not a starter
            # The entire connected lineage shares its trials and three holdout looks, including later looks on other roots.
            child = self.store.add_family(spec, origin="fork", parent=fam["id"])
            if best and code:
                self.store.add_version(child["id"], code, best.get("params") or {}, author=f"fork of {fam['id']}",
                                       note=f"the parent's version {best['n']} on {', '.join(pooled)}")
                self.store.note(child["id"], f"Forked from {fam['id']} onto {', '.join(pooled)}: its roots and {root}. Version 1 is "
                                             f"the parent's best with {root} added to NEEDS; check widths and risk_usd for {root}.")
            self.store.set_state(fam["id"], forked_at=self.clock())
            born = {"parent": fam["id"], "mechanism": fam["mechanism"], "structure": fam["structure"], "roots": pooled,
                    "origin": "fork"}
            # THE DIRECTION LANE (release D-1): a direction parent's fork is a direction family (its spec, copied above,
            # carries the lane), and its birth says so, so the births' quota and the funnel (`dlane.born_counts`, which
            # reads a payload without a lane as alpha's) count it in its lane. An alpha fork's event is as before in every
            # mode; while the lane is off nothing is read.
            if dlane.lane_of(self.store, child, self.settings) == dlane.DIRECTION:
                born["lane"] = dlane.DIRECTION
            self.store.event("swarm.born", child["id"], born)
            return child["id"]
        return None

    # ------------------------------------------------------------------ 5. retirements
    def retirements(self, fams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        current = self.identity()
        kept = self.incubator_keep()  # read once, before any store transaction
        for fam in sorted(fams, key=lambda f: (f.get("weight") or 0.0)):
            why = self._retire_if(fam["id"], lambda fam: self._why(fam, current, kept))
            if why:
                out.append({"family": fam["id"], "why": why})
        return out

    def _why(self, fam: Mapping[str, Any], current: tuple[Any, Any], kept: frozenset[str] | None = None) -> str | None:
        """The hourly round's reason to retire a family (its rules in order, the idle rule last), or None. A direction
        family's spent ration comes first (THE RATION BEFORE THE KEEP, M3); after it, a family THE COHORT KEEP holds
        (`kept`, else `incubator_keep`) answers to the deflated-Sharpe rule alone; the rule it was spared is recorded
        (`keep_spared`)."""
        if fam["band"] != "gym":
            return None  # a Candidate or better is judged by its forward record, not here
        state = fam.get("state") or {}
        from .researcher import extension_held
        if held_at_gate(fam) or state.get("gate_ready") or state.get("look_inflight") or extension_held(fam):
            # The operator holds its validated version at the gate: no rule retires it until the hold is cleared (the
            # look it holds must still happen; `SwarmStore.retire_gym` refuses it too).
            return None
        if self.played(fam):
            # THE LEARNING GAME's reasons first (a game-arm family in "gate"): never a figure, a tier or a year in them.
            try:
                why = game.retire_reason(self.store, fam, self.settings)
            except Exception:  # noqa: BLE001 - today's rules then
                why = None
            if why:
                return why
        # THE DIRECTION LANE'S RATION (release D-1b): a direction lineage that has used its one Validation try or its one
        # holdout look without a pass still in play retires (`dlane.lineage_spent`: words only, never a figure). After the
        # gate's own holds above; never for an alpha family, nor while the lane is off.
        # THE RATION BEFORE THE KEEP (Oct 10, 2026; the readiness audit's M3): it is asked BEFORE THE COHORT KEEP, which
        # until now spared it as it spares the clocks. A spent direction family has nothing left to validate or look at,
        # so the keep held its population slot for nothing: at 20:12Z Oct 9 the keep (cap 12) spared 8 direction families
        # by the ration while births ran 1-2 a pass under `population.start` 16. It now retires and frees the slot; its
        # practice cohort ends with it, so its program loses the incubator route (a tightening of a money route, listed in
        # the dlane report's TIGHTENED). `lineage_spent` is None for every alpha family and while the lane is off, so the
        # alpha lane and the rollback keep THE COHORT KEEP's order exactly.
        # THE ALWAYS-IN CARD (Oct 10, 2026; `dlane.always_in_failed`): an always-in family whose version due for Validation
        # G1 refused at the try (it did not behave always-in on Train) loses the always-in exemption and retires, after
        # the ration (a spent lineage retires on its own cause, and a member holding the lineage's try is never retired
        # by G1) and before the keep; its cause is an untested death (IDLE), so no graveyard row of it binds, and it spent
        # no try. A G1 failure of any other version only makes that version ineligible (`dlane.train_score`).
        spent = dlane.lineage_spent(self.store, fam, self.settings)
        if spent:
            return spent
        failed = dlane.always_in_failed(self.store, fam, self.settings)
        if failed:
            return failed
        clock: tuple[str, str] | None = None
        if int(fam.get("since_val_revisions") or 0) >= int(self.cfg.get("retire_revisions", 30)):
            clock = ("revisions", f"no validation improvement in {fam['since_val_revisions']} revisions")
        elif int(fam.get("since_val_trials") or 0) >= int(self.cfg.get("retire_evaluations", 2000)):
            clock = ("evaluations", f"no validation improvement in {fam['since_val_trials']} Gym evaluations")
        dsr = None
        line = (fam.get("state") or {}).get("validation_line") or {}
        figure = (line.get("numbers") or {}).get("dsr")
        if int(fam.get("validations") or 0) >= int(self.cfg.get("retire_min_validations", 6)) and figure is not None \
                and figure < float(self.cfg.get("retire_dsr_below", 0.05)):
            # No figure in the reason: it becomes a graveyard lesson researchers read (D2a).
            dsr = "its trial-adjusted evidence fell below the line (the deflated Sharpe probability)"
        if fam["id"] in (self.incubator_keep() if kept is None else kept):
            # THE COHORT KEEP (L1): its practice cohort is still running and not losing. Evidence still retires it.
            if dsr is None:
                spared = (clock[0] if clock
                          else ("idle" if idle_dead(fam, self.settings, current=current) else None))
                if spared:
                    self.keep_spared[fam["id"]] = spared
            return dsr
        why = clock[1] if clock else dsr
        if not why:
            # The fallback for a dead family that never called retire (R3): Train figures only in the reason.
            why = self.idle_why(fam, current=current, kept=frozenset())
        return why

    # ------------------------------------------------------------------ 5a. the cohort keep (L1)
    def keep_max(self) -> int:
        """`tournament.incubator_keep_max`: absent, `KEEP_MAX` (12); a number, its whole part, at most `KEEP_CEILING`; 0 or
        below, or anything that is not a finite number (null, a boolean, a string), 0: THE COHORT KEEP off."""
        raw = self.cfg.get("incubator_keep_max", KEEP_MAX)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            return 0
        return max(0, min(KEEP_CEILING, int(raw)))

    def incubator_keep(self) -> frozenset[str]:
        """THE COHORT KEEP (L1, the module docstring): the living Gym families the revision, evaluation and idle rules
        spare now (`keep_order` over `practice.cohort_status`, at most `keep_max` beside the incubator's cohorts,
        `incubator_held`). Reads the practice record and the swarm's incubator facts read-only and saves what it keeps
        (`practice.KEEP_KV`, for the researchers' status); never raises. When the practice record or
        the swarm's families cannot be read, the last good keep stands for `KEEP_STALE_SECONDS`, then none does. A fresh
        process (no read of its own yet: a deploy, a restart, the induced-failure kill) whose read fails takes the keep the
        last process saved (`_saved_keep`) as that last good keep, from the time it was read, so its first idle pass does
        not retire what that keep protects and the saved keep is not overwritten before its hour has passed."""
        cap = self.keep_max()
        now = self.clock()
        if cap <= 0:
            self._keep_set(now, [], "off")
            return self.kept
        rows, chosen, error = None, None, None
        try:
            rows = practice.cohort_status(getattr(self.store, "root", None), today=practice.session_day(now))
        except Exception as exc:  # noqa: BLE001 - a retirement pass never fails on the keep
            error = f"the practice record (observe.sqlite) could not be read ({type(exc).__name__})"
        if rows is None:
            error = error or "the practice record (observe.sqlite) could not be read"
        else:
            try:
                alive = {f["id"] for f in self.store.families(alive=True) if f.get("band") == "gym"} if rows else set()
                held = incubator_held(getattr(self.store, "root", None), rows, alive) if rows else frozenset()
                chosen = keep_order(rows, alive, cap, held=held)
            except Exception as exc:  # noqa: BLE001
                error = f"the swarm's families could not be read or ordered ({type(exc).__name__})"
        if chosen is None:
            self.keep_error = error
            if self.kept_at == float("-inf"):
                # A FRESH PROCESS whose first read fails (the review of release B, Sept 30): the saved keep stands.
                saved = self._saved_keep(now, cap)
                if saved is not None:
                    self.kept_at, self.kept_rows = saved
                    self.kept = frozenset(r["family"] for r in self.kept_rows)
            if now - self.kept_at <= KEEP_STALE_SECONDS:
                self.keep_read = "stale"
                return self.kept
            self._keep_set(now, [], "failed")
            return self.kept
        self.kept_at, self.keep_error = now, None
        self._keep_set(now, chosen, "ok")
        return self.kept

    def _saved_keep(self, now: float, cap: int) -> tuple[float, list[dict[str, Any]]] | None:
        """The keep the last process saved (`practice.KEEP_KV`), for a fresh process whose first read fails: (when it was
        read, its families as rows), or None when there is none, it keeps no family, it was read more than
        `KEEP_STALE_SECONDS` ago (or in the future), or it cannot be read. Only a good read saves a family (a failed or off
        read saves none), so its time is the last good read's. Its rows carry the family and version only (`sample`,
        `negative`, `sessions` and `closes_program` None: this process has not read the record; `held` True for a
        family the saved keep names among the incubator's cohorts, its `held`). The incubator's cohorts' families
        first (at most `KEEP_CEILING`, never cut by the cap, as `keep_order`), then at most `cap` in all (a cap lowered
        since): the store keeps no order, so each by name. Never raises."""
        try:
            value = self.store.get(practice.KEEP_KV)
            if not isinstance(value, Mapping):
                return None
            at, families = value.get("at"), value.get("families")
            if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= now - float(at) <= KEEP_STALE_SECONDS:
                return None
            if not isinstance(families, Mapping):
                return None
            named = value.get("held")
            named = {f for f in named if isinstance(f, str)} if isinstance(named, list) else set()
            rows = [{"family": fid, "version": version, "sample": None, "negative": None, "sessions": None,
                     "closes_program": None, "held": fid in named}
                    for fid, version in sorted(families.items())
                    if isinstance(fid, str) and isinstance(version, int) and not isinstance(version, bool)]
            held = [r for r in rows if r["held"]][:KEEP_CEILING]
            rows = held + [r for r in rows if not r["held"]][:max(0, cap - len(held))]
        except Exception:  # noqa: BLE001 - a retirement pass never fails on the keep
            return None
        return (float(at), rows) if rows else None

    def _keep_set(self, now: float, chosen: list[dict[str, Any]], read: str) -> None:
        """The keep in memory, and saved for the researchers (`practice.KEEP_KV`; a store error only loses the save),
        with the incubator's cohorts' families (`held`) when there are any."""
        self.kept, self.kept_rows, self.keep_read = frozenset(r["family"] for r in chosen), list(chosen), read
        value: dict[str, Any] = {"at": now, "families": {r["family"]: int(r["version"]) for r in chosen}}
        held = sorted(r["family"] for r in chosen if r.get("held"))
        if held:
            value["held"] = held
        try:
            self.store.put(practice.KEEP_KV, value)
        except Exception:  # noqa: BLE001 - the researchers' status line is a courtesy; the keep itself stands
            pass

    def keep_event(self) -> dict[str, Any] | None:
        """The round's one private `swarm.status` event of THE COHORT KEEP (action `incubator_keep`): the kept families in
        order (version, whether the sample is met, whether the record so far is negative, completed sessions, program
        closes before today), the incubator's cohorts' families among them (`held`, when there are any), the rule each
        family it spared since the last event would have retired it by (`spared`), the cap, how the record read and,
        when it did not, why (`error`). None when the keep is off, or keeps and spares nothing and read well. An
        unreadable record alerts once until it reads again."""
        spared, self.keep_spared = dict(sorted(self.keep_spared.items())), {}
        if self.keep_read == "ok":
            self._keep_told = False
        if self.keep_read == "off" or (self.keep_read == "ok" and not self.kept_rows and not spared):
            return None
        alive = {f["id"] for f in self.store.families(alive=True)} if self.kept_rows else set()
        payload: dict[str, Any] = {
            "action": "incubator_keep", "cap": self.keep_max(), "read": self.keep_read,
            "kept": [{"family": r["family"], "version": r["version"], "sample": r["sample"], "negative": r["negative"],
                      "sessions": r["sessions"], "closes": r["closes_program"]}
                     for r in self.kept_rows if r["family"] in alive],
            "spared": spared}
        held = [r["family"] for r in self.kept_rows if r.get("held") and r["family"] in alive]
        if held:
            payload["held"] = held
        if self.keep_read != "ok" and self.keep_error:
            payload["error"] = self.keep_error
        if self.keep_read == "failed" and not self._keep_told:
            self._keep_told = True
            payload.update(alert=True, text=f"{self.keep_error or 'the cohort keep could not be read'}: the cohort keep "
                                            "(L1) spares no family until it can")
        self.store.event("swarm.status", None, payload)
        return payload

    def identity(self) -> tuple[Any, Any]:
        """(the Gym image, its engine bundle) the pool runs now, as `validate` reads them; what could not be read is None
        (like `Researcher._gym_identity`: a pool error never fails a retirement pass, and an unknown identity only makes
        a passing validation look owed, `revalidation_owed`, never a family dead)."""
        image = bundle = None
        try:
            image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        except Exception:  # noqa: BLE001
            pass
        return image, bundle

    def idle_why(self, fam: Mapping[str, Any], *, current: tuple[Any, Any] | None = None,
                 kept: frozenset[str] | None = None) -> str | None:
        """THE IDLE RULE's reason to retire a living Gym family (`researcher.idle_dead`), or None: never outside the Gym
        band nor while the operator holds its validated version at the gate (`held_at_gate`); `idle_dead` itself exempts
        a version at the gate, a look out, a passing validation owed again on the Gym running now (`current`, R4) and,
        from its dormancy clause, a best that awaits validation. Never for a family THE COHORT KEEP holds (`kept`, else
        `incubator_keep`, read only for a dead family); the spared rule is recorded (`keep_spared`)."""
        if fam.get("band") != "gym" or fam.get("retired_at") or held_at_gate(fam):
            return None
        current = current if current is not None else self.identity()
        dead = idle_dead(fam, self.settings, current=current)
        if not dead and self.played(fam):
            dead = self.game_dormant(fam, current)
        if not dead:
            return None
        if fam["id"] in (self.incubator_keep() if kept is None else kept):
            self.keep_spared[fam["id"]] = "idle"
            return None
        # THE IDLE RULE'S VERDICT (R11-1): the death is filed under what its Train record shows; only an untested family
        # (it never traded on Train) is "a time limit, not a finding". Train figures only (D2). THE DEPTH RULE's death
        # (F1) of a family with a Train score says what ended it (D2a's count, no figure): still EXHAUSTED.
        screen = train_record(self.store, fam)["screen"]
        if screen == "scored" and dead == short_dead(fam, self.settings):
            screen = "short"
        return f"It {dead}. {idle_cause(screen)}"

    def game_dormant(self, fam: Mapping[str, Any], current: tuple[Any, Any] | None) -> str | None:
        """THE GAME'S VALIDATION WAIT (the module docstring, 7): the dormancy clause of `idle_dead` for a game-arm family in
        "gate" whose best awaits validation by today's reading (`awaiting_validation`), which is all that spared it there:
        it is dead unless its CONFIRMED version awaits Validation (not validated, not failed by the drift screen) or a
        look of it is out (`game.in_flight`). The clause's own words; None otherwise and on an error."""
        from .researcher import extension_held

        limit, cycles = dormant_limit(self.settings), dormant_count(fam)
        state = fam.get("state") or {}
        if limit <= 0 or cycles < limit or not awaiting_validation(fam) or extension_held(fam) or state.get("gate_ready") \
                or state.get("look_inflight") or revalidation_owed(fam, current):
            return None
        try:
            n = game.candidate(self.store, fam)
            if (n is not None and n != fam.get("validated_version") and drift_failed(fam, n) is None
                    and self.game_try_left(fam, n) and self.game_train_ok(fam, n)) or game.in_flight(self.store, fam):
                return None
        except Exception:  # noqa: BLE001 - today's wait then
            return None
        return f"made no new Gym evaluation in its last {cycles} cycles (only stored results, holds and refused runs)"

    def game_train_ok(self, fam: Mapping[str, Any], n: int) -> bool:
        """`validate`'s eligible Train run for a game candidate under the evaluator in force (its submitted or best Train
        run, or its ladder look's seen run): without one (an adoption since its look) it waits in `validate` for ever, so
        THE GAME'S VALIDATION WAIT does not spare it for that."""
        from .evaluator import KEY, row_matches

        current = self.store.get(KEY)
        if current is None:
            return True
        state = fam.get("state") or {}
        run_ids = [state.get("submitted_run"), state.get("best_train_run"), self._game_read(game.look_seen_run, fam, n)]
        return any(row is not None and row.get("version") == n and row_matches(self.store, row, current)
                   for row in (self.store.run(str(rid)) for rid in run_ids if rid))

    def _retire_if(self, fid: str, judge: Callable[[Mapping[str, Any]], str | None]) -> str | None:
        """Read the family, judge it and retire it in ONE store transaction (R4, the review of PR #402): a result landing
        meanwhile (its trials, its dormant count restarted) either lands first and is judged, or waits for the retirement
        and counts on the retired family; never judged on one state and retired on another. `SwarmStore.retire_gym` nests
        in it and checks `population.floor`. The pool's queued work is cancelled after, outside the transaction (the pool
        takes its own lock before the store's). The reason, or None."""
        with self.store.atomic():
            fam = self.store.family(fid)
            if fam is None or fam.get("retired_at"):
                return None
            why = judge(fam)
            if not why:
                return None
            # THE FLOOR COUNTS RESEARCH (F1): a dead slot is not held at the floor (`floor_counts`).
            result = self.store.retire_gym(fid, why, floor=int(self.settings.get("population", {}).get("floor", 16)),
                                           source="tournament", counts=self.floor_counts())
        if result["status"] != "retired" or result.get("already_retired"):
            return None
        try:
            self.pool.cancel_family(fid)
        except Exception:  # noqa: BLE001
            pass
        return why

    def floor_counts(self) -> Callable[[Mapping[str, Any]], bool] | None:
        """THE FLOOR COUNTS RESEARCH (F1, `researcher.floor_counts`): the living families `population.floor` counts, on
        the Gym the pool runs now: every one but a dead slot, a family the saved cohort keep holds always counted. None
        (every living family) while `population.floor_researching` is false."""
        kept = kept_families(self.store, float(self.clock()))
        return floor_counts(self.settings, current=self.identity(), kept=kept.__contains__)

    def idle_due(self) -> bool:
        """THE IDLE PASS is due: `tournament.retire_every_seconds` (300) since the last; 0, null, a boolean or not a finite
        number turns it off (the hourly round still retires by the same rule)."""
        raw = self.cfg.get("retire_every_seconds", 300)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 < raw < float("inf"):
            return False
        return self.clock() - self.idle_at >= float(raw)

    def idle_pass(self, *, busy: Callable[[str], bool] | None = None) -> dict[str, Any]:
        """THE IDLE PASS (R4, Sept 28): the hourly round's idle-rule retirements alone, every `retire_every_seconds` between
        its rounds, so a dead family leaves within minutes of dying (after R3 dead families held until the hourly round,
        which the operator did not wait for: 60 retired by hand). The same rule, reasons and lessons as the round's
        fallback (`idle_why`), the least favoured first, each read, judged and retired in one transaction (`_retire_if`),
        never below `population.floor`. A family `busy` says is in a researcher's cycle now is left to the next pass (its
        cycle may be making the evaluation that keeps it alive). The loop never runs it while the hourly round runs. No
        model call and no Gym job."""
        self.idle_at = self.clock()
        current = self.identity()
        kept = self.incubator_keep()  # THE COHORT KEEP, read once, before any store transaction
        retired, skipped = [], []
        for fam in sorted(self.store.families(alive=True), key=lambda f: (f.get("weight") or 0.0, f["id"])):
            if busy is not None and busy(fam["id"]):
                skipped.append(fam["id"])
                continue
            why = self._retire_if(fam["id"], lambda fam: self.idle_why(fam, current=current, kept=kept))
            if why:
                retired.append({"family": fam["id"], "why": why})
        return {"retired": retired, "busy": len(skipped), "alive": len(self.store.families(alive=True))}

    def retire(self, fam: Mapping[str, Any], why: str) -> bool:
        result = self.store.retire_gym(fam["id"], why, floor=int(self.settings.get("population", {}).get("floor", 16)),
                                       source="tournament", counts=self.floor_counts())
        if result["status"] != "retired" or result.get("already_retired"):
            return False
        try:
            self.pool.cancel_family(fam["id"])
        except Exception:  # noqa: BLE001
            pass
        return True

    # ------------------------------------------------------------------ the learning game's steps
    def game_step(self, step: str, call: Callable[[], Any]) -> Any:
        """One of THE LEARNING GAME's round steps, never failing the round: an error is one private `swarm.status` event
        naming the step and the error's type (never its words, which could carry a figure), and None."""
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.status", None, {"action": "game_error", "step": step, "error": type(exc).__name__})
            return None

    # ------------------------------------------------------------------ the whole round
    def run(self) -> dict[str, Any]:
        began = self.clock()
        self.store.put("tournament_at", began)
        fams = self.store.families(alive=True)
        self.game_step("confirm_waiting", lambda: game.confirm_waiting(self.store, self.settings))
        validation = self.validate(fams)
        self.game_step("shadow_validated", lambda: game.shadow_validated(self.store, self.settings, self.pool, self.clock))
        self.game_step("requeue_stale", lambda: game.requeue_stale(self.store, self.settings, self.pool, self.clock))
        self.game_step("recheck", lambda: game.recheck(self.store, self.settings, self.pool, self.clock))
        facts = self.incubator_facts()
        fams = self.store.families(alive=True)
        self.allocate(fams)  # the shares retirements rank by (the least favoured go first)
        retired = self.retirements(self.store.families(alive=True))
        self.keep_event()  # THE COHORT KEEP's one private event a round
        born = self.forks(self.store.families(alive=True))
        born += self.game_step("reproduce", lambda: game.reproduce(self.store, self.settings, self.clock)) or []
        fams = self.store.families(alive=True)
        self.allocate(fams)  # again, so a newborn fork has its share at once
        board = []
        # THE LEADERBOARD'S ORDER: Candidates and beyond, then the families at the gate or with a look out, then the rest
        # by share. The allocator gives the first two the floor share (the gate or the forward record decides them, not
        # research), and the architect and the strategist read only the first 60 rows: the swarm's most advanced families
        # are always in them.
        for fam in sorted(fams, key=board_rank):
            state = fam.get("state") or {}
            board.append({"family": fam["id"], "band": fam["band"], "share": round(float(fam.get("weight") or 0.0), 4),
                          "structure": fam["structure"], "roots": fam["roots"], "revisions": fam["revisions"],
                          "lineage_trials": self.store.lineage_trials(fam["id"]), "best_train": fam.get("best_train"),
                          "validation": state.get("validation_numbers"), "gate_ready": bool(state.get("gate_ready")),
                          "closeable": fam["structure"] in CLOSEABLE})
            if state.get("gate_hold"):
                board[-1]["gate"] = "held by the operator"  # `SwarmStore.hold_gate`: the gate looks at nothing of it
        totals = self.store.totals()
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(began - 3600))
        cycles = self.store._all("SELECT COUNT(*) AS n, SUM(CASE WHEN payload LIKE '%\"error\"%' THEN 1 ELSE 0 END) AS errors FROM events"
                                 " WHERE kind='swarm.cycle' AND at >= ?", (since,))[0]
        last_hour = {"cycles": int(cycles["n"] or 0), "cycle_errors": int(cycles["errors"] or 0),
                     "usd": {k: round(self.store.spent([k], since=began - 3600), 4) for k in ("sail_model", "gym_box", "openai")}}
        row = {"at": began, "seconds": round(self.clock() - began, 1), "validation": validation, "retired": retired, "born": born,
               "board": board, "totals": totals, "last_hour": last_hour, "practice_bonus": dict(self.practice_bonus),
               "allocation": dict(self.allocation), "incubator": facts}
        self.store.event("swarm.tournament", None, row)
        self.store.put("leaderboard", {"at": began, "board": board, "totals": totals})
        return row


def board_rank(fam: Mapping[str, Any]) -> tuple:
    """A living family's place on the leaderboard (`Tournament.run`): outside the Gym band first, then at the gate or with a
    look out, then by share (the larger first), then by id."""
    state = fam.get("state") or {}
    stage = 0 if (fam.get("band") or "gym") != "gym" else 1 if (state.get("gate_ready") or state.get("look_inflight")) else 2
    return (stage, -float(fam.get("weight") or 0.0), str(fam.get("id")))


def typical_max_loss(result: Mapping[str, Any]) -> float | None:
    """The median maximum loss of ONE structure in a validation run, for the live path's sizing: the Gym's own
    `median_max_loss_per_structure` when the (validation-view) summary carries it, else the trades' median when
    the result has them, else the mean maximum loss a trade opened."""
    s = result.get("summary") or {}
    value = s.get("median_max_loss_per_structure")
    if isinstance(value, (int, float)) and value > 0:
        return round(float(value), 2)
    losses = sorted(float(t["max_loss"]) / max(1, int(t.get("qty") or 1)) for t in (result.get("trades") or [])
                    if isinstance(t.get("max_loss"), (int, float)))
    if losses:
        return round(losses[len(losses) // 2], 2)
    opened, trades = s.get("max_loss_opened"), s.get("trades")
    if isinstance(opened, (int, float)) and isinstance(trades, int) and trades > 0:
        return round(float(opened) / trades, 2)
    return None


def json_safe(value: Any) -> str:
    import json

    try:
        return json.dumps(value, default=str)[:400]
    except (TypeError, ValueError):
        return str(value)[:400]


__all__ = ["Tournament", "IDLE_CAUSE", "keep_order", "incubator_held", "KEEP_MAX", "KEEP_CEILING", "KEEP_SAMPLE_SESSIONS",
           "KEEP_SAMPLE_TRADES", "KEEP_UNPRACTICED", "KEEP_STALE_SECONDS"]
