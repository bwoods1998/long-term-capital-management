"""The hourly tournament: validation, the bandit, forks, retirements, lessons, the leaderboard.

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
   its own NEEDS roots (a family's roots may have moved since).
2. THE LINE (`evidence.validation_line`, as the owner's decision D2 amended it): its deflated Sharpe is on traded
   days with N = the lineage's validated versions (`SwarmStore.lineage_validated`). A family that meets it goes to
   the gate's queue. Then THE INCUBATOR'S TRAIN AND DRIFT MARKS (`incubator.facts`, release B2, Sept 30, 2026): each
   version an alive Gym family practises in an active, current cohort is marked `train_passed` once it has an eligible
   Train run, a profitable 1.5x run, no demotion and a passed drift screen, under the current evaluator. The mark is
   a fact for the House's incubator route only (one lot, never evidence, never a promotion); nothing here reads it.
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
4. FORKS: the top families with a positive validation t fork (never one whose validated version failed the drift screen) (a new family on the parent's roots plus one more
   root of the rotation, same mechanism and structure; it inherits the lineage's trial count and holdout looks),
   while the population is under its ceiling. XSP is out of the rotation: its $0.50 a contract makes a narrow
   structure uneconomic. Only a family of a type `architect.structures` allows forks (THE STRUCTURES, Oct 1, 2026:
   league/swarm/architect.py `allowed_structures`; every type while it is unset); one of another type is never retired
   for it and keeps researching until a rule retires it.
5. RETIREMENTS: no validation improvement in `retire_revisions` (30) or `retire_evaluations` (2,000; the defaults,
   swarm.json may set others) Gym evaluations, or trial-adjusted
   evidence below the line (the deflated Sharpe probability under `retire_dsr_below` after
   `retire_min_validations` validations), or, as the fallback for a dead family that never calls retire, THE IDLE
   RULE (`researcher.idle_dead`, R3: `researcher.retire_idle_evaluations` Gym evaluations since its birth or last
   validation without an eligible Train version, or three times as many with its best Train score below zero, or
   `researcher.dormant_cycles` cycles in a row with only stored results, holds and refused runs while its best does
   not await validation; never while a validated version awaits the gate); never below the population floor, and by
   no rule while the operator holds its validated version at the gate (`researcher.held_at_gate`). Each retiree's
   lesson goes to the graveyard (its mechanism, what it tried, its best numbers, its last notebook lines); an idle-rule
   lesson carries the verdict of its Train record (R11-1, `researcher.train_record`: DRIFT, STRESS, THIN or EXHAUSTED,
   tested findings), and only an untested family's (it never traded on Train) says it was a time limit, not a
   refutation. A validation that meets `researcher.extension_hold_checks` (6) of the line's checks sets the family's
   extension hold (R11-4's swarm rule, `researcher.judge_extension`); a validation of the held version below them ends
   it. Each counted verdict records the family's trials (`validated_trials`), from which the idle rule counts, and
   restarts its dormant cycles. THE IDLE PASS (R4, `idle_pass`) retires by the idle rule alone every
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
   `tournament.incubator_keep_max` (12; 0 turns it off) families: first those that meet the sample (by return on risk,
   highest first), then those whose record so far is not negative, then the rest, each by the practice league's own
   order (`bands.priority`). It never spares a family from the deflated-Sharpe rule, its researcher's or the
   diagnostician's own retire, the population floor or the operator's gate hold. Research attention only: no trial
   count, look, validation, gate, band or money rule reads it. The keep is saved at each read (`practice.KEEP_KV`), so a
   kept family's researcher is not urged to retire it for being idle (the retire tool stays offered). A record that
   cannot be read leaves the last good keep standing for `KEEP_STALE_SECONDS` (an hour), then none; a FRESH PROCESS (a
   deploy, a restart, the induced-failure kill: its idle pass runs at once) whose first read fails takes the keep the
   last process saved for the rest of that hour and does not overwrite it before then. The round records
   the kept families and what each was spared in one private `swarm.status` event (`incubator_keep`).
6. THE LEADERBOARD: one `swarm.tournament` event (the House mirrors it to its ledger) with every family's
   rank, share, validation summary, trials and band, and the totals. Its order (`board_rank`): Candidates and beyond,
   then families at the gate or with a look out, then by share, so the architect's and the strategist's first 60 rows
   always hold the most advanced families (the allocation gives them the floor share: the gate decides them next).

Standard library only.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Callable, Mapping

from . import diagnostics, evidence, incubator, practice
from .architect import allowed_structures
from .pool import GymJob, PoolError
from .researcher import (IDLE_CAUSE, MAX_ROOTS, drift_verdict, held_at_gate, idle_cause, idle_dead, judge_extension,
                         needs_roots, robust_at_stress, screen_best, train_record, validation_drift_failed, with_roots)
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


def keep_order(rows: list[Mapping[str, Any]], alive: Mapping[str, Any] | set[str] | frozenset[str],
               cap: int) -> list[dict[str, Any]]:
    """THE COHORT KEEP's choice (pure): of the active cohorts `rows` (`practice.cohort_status`, each record before today),
    each one whose family is in `alive` (the living Gym families), whose session window has not run out (`elapsed <
    window`), that the House is practising (`unpracticed < KEEP_UNPRACTICED`, unless it practises no active cohort at
    all: an outage) and that the incubator can look at
    (`sessions` known), and that either has not met the incubator's sample (`KEEP_SAMPLE_SESSIONS` completed sessions and
    `KEEP_SAMPLE_TRADES` program closes) or has a record that is not negative (`pnl_program >= 0` and `pnl_all >= 0`, to
    the cent). Ordered: the sample met, by return on risk, highest first; then the rest whose record so far is not
    negative; then the rest; each then by the practice league's order (`bands.priority`), then by version. One row a
    family (its first), at most `cap`; each row gains `sample` and `negative`."""
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
        negative = round(float(r["pnl_program"]), 2) < 0 or round(float(r["pnl_all"]), 2) < 0
        sample = int(r["sessions"]) >= KEEP_SAMPLE_SESSIONS and int(r["closes_program"]) >= KEEP_SAMPLE_TRADES
        if sample and negative:
            continue
        ror = r.get("return_on_risk") if sample else None
        head = (0, ror is None, -float(ror or 0.0)) if sample else (1 + int(negative), False, 0.0)
        ranked.append((head + tuple(priority(r)) + (int(r["version"]),), {**dict(r), "sample": sample, "negative": negative}))
    ranked.sort(key=lambda x: x[0])
    out: list[dict[str, Any]] = []
    for _, row in ranked:
        if len(out) >= max(0, int(cap)):
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
    def candidate_version(self, fam: Mapping[str, Any]) -> int | None:
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
        waiting: list[str] = []
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
            if n is None:
                continue
            state = fam.get("state") or {}
            from .evaluator import KEY, row_matches

            # A startup adoption clears cached bests. Defense in depth for an old submission
            # restored or arriving late: no current validation is bought with stale Train evidence.
            current_evaluator = self.store.get(KEY)
            if current_evaluator is not None:
                run_ids = [state.get("submitted_run"), state.get("best_train_run")]
                eligible_train = any(row is not None and row.get("version") == n and row_matches(self.store, row, current_evaluator)
                                     for row in (self.store.run(str(rid)) for rid in run_ids if rid))
                if not eligible_train:
                    waiting.append(fam["id"])
                    continue
            if self.cfg.get("require_robustness", True) and not robust_at_stress(state, n):
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
            recorded = self.recorded_validation(fam["id"], n)
            if recorded is not None:  # validated before (a best submitted again): judged from its result, no new trial
                row = self.judge(fam["id"], n, recorded, record=False)
                if row is not None:
                    judged[fam["id"]] = row
                continue
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
        return {"queued": len(jobs), "judged": judged, "errors": errors, "waiting_robustness": waiting,
                "waiting_drift": drift["waiting"], "failed_drift": sorted(set(drift["failed"]))}

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

    def judge(self, fid: str, n: int, result: Mapping[str, Any], *, record: bool = True) -> dict[str, Any] | None:
        """Record a validation result (and its stress twin: two trials) and judge it by the line. Also called for a
        result that lands after the round stopped waiting: every evaluation counts. Its verdict is written only while
        `n` is still the family's candidate (the researcher's current best): a result for a version the family has
        moved on from is stale, whatever its number. `record=False` re-judges a result already recorded."""
        fam = self.store.family(fid)
        if fam is None:
            return None
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
            if fam.get("retired_at") or self.candidate_version(fam) != int(n) or result.get("gym_image") != image or result.get("gym_bundle") != bundle:
                return None  # stale: its trials count, its verdict does not
            return self._verdict(fid, fam, n, result, counted=record)

    def _verdict(self, fid: str, fam: Mapping[str, Any], n: int, result: Mapping[str, Any], *, counted: bool) -> dict[str, Any]:
        stressed = evidence.stressed_of(result)
        validated, sharpes = self.store.lineage_validated(fid)
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
            self.store.set_state(fid, validated_trials=int(fam.get("trials") or 0), dormant_cycles=0)
        state = fam.get("state") or {}
        typical = dict(state.get("typical_by_version") or {})
        if state.get("validation_version") is not None and state.get("typical_max_loss_usd") is not None:
            typical.setdefault(str(state["validation_version"]), state["typical_max_loss_usd"])
        loss = typical_max_loss(result)
        if loss is not None:
            typical[str(n)] = loss
        self.store.set_state(fid, validation_view=view, validation_line=line, validation_version=n,
                             validation_image=result.get("gym_image"),
                             validation_bundle=result.get("gym_bundle"),
                             typical_max_loss_usd=loss, typical_by_version=typical,
                             validation_numbers={"mean": mean, "t": t, "sharpe_daily": summary.get("sharpe_daily"),
                                                 "quarters": summary.get("quarters_positive")},
                             gate_ready=bool(line["passed"]) and not self.gate_spent(fid, n, state))
        out = {"version": n, "passed": line["passed"], "mean": mean, "t": t}
        # THE EXTENSION HOLD (R11-4's swarm rule): a version that met `researcher.extension_hold_checks` of the line's checks
        # waits for its 2017-19 extension result, exempt from the dormancy clause, until the operator clears the flag. A
        # validation of the held version below the checks ends its hold (`judge_extension`); the verdict row says which.
        change = judge_extension(self.store, fid, n, line, self.settings, clock=self.clock)
        if change == "held":
            out["extension_hold"] = True
        elif change == "lapsed":
            out["extension_lapsed"] = True
        return out

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
            self.store.event("swarm.born", child["id"], {"parent": fam["id"], "mechanism": fam["mechanism"],
                                                          "structure": fam["structure"], "roots": pooled, "origin": "fork"})
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
        """The hourly round's reason to retire a family (its rules in order, the idle rule last), or None. A family THE
        COHORT KEEP holds (`kept`, else `incubator_keep`) answers to the deflated-Sharpe rule alone; the rule it was
        spared is recorded (`keep_spared`)."""
        if fam["band"] != "gym":
            return None  # a Candidate or better is judged by its forward record, not here
        state = fam.get("state") or {}
        from .researcher import extension_held
        if held_at_gate(fam) or state.get("gate_ready") or state.get("look_inflight") or extension_held(fam):
            # The operator holds its validated version at the gate: no rule retires it until the hold is cleared (the
            # look it holds must still happen; `SwarmStore.retire_gym` refuses it too).
            return None
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
                spared = clock[0] if clock else ("idle" if idle_dead(fam, self.settings, current=current) else None)
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
        spare now (`keep_order` over `practice.cohort_status`, at most `keep_max`). Reads the practice record read-only and
        saves what it keeps (`practice.KEEP_KV`, for the researchers' status); never raises. When the practice record or
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
                chosen = keep_order(rows, alive, cap)
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
        `negative`, `sessions` and `closes_program` None: this process has not read the record). At most `cap` (a cap
        lowered since): the store keeps no order, so the first by name. Never raises."""
        try:
            value = self.store.get(practice.KEEP_KV)
            if not isinstance(value, Mapping):
                return None
            at, families = value.get("at"), value.get("families")
            if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 <= now - float(at) <= KEEP_STALE_SECONDS:
                return None
            if not isinstance(families, Mapping):
                return None
            rows = [{"family": fid, "version": version, "sample": None, "negative": None, "sessions": None,
                     "closes_program": None}
                    for fid, version in sorted(families.items())
                    if isinstance(fid, str) and isinstance(version, int) and not isinstance(version, bool)][:max(0, cap)]
        except Exception:  # noqa: BLE001 - a retirement pass never fails on the keep
            return None
        return (float(at), rows) if rows else None

    def _keep_set(self, now: float, chosen: list[dict[str, Any]], read: str) -> None:
        """The keep in memory, and saved for the researchers (`practice.KEEP_KV`; a store error only loses the save)."""
        self.kept, self.kept_rows, self.keep_read = frozenset(r["family"] for r in chosen), list(chosen), read
        try:
            self.store.put(practice.KEEP_KV, {"at": now, "families": {r["family"]: int(r["version"]) for r in chosen}})
        except Exception:  # noqa: BLE001 - the researchers' status line is a courtesy; the keep itself stands
            pass

    def keep_event(self) -> dict[str, Any] | None:
        """The round's one private `swarm.status` event of THE COHORT KEEP (action `incubator_keep`): the kept families in
        order (version, whether the sample is met, whether the record so far is negative, completed sessions, program
        closes before today), the rule each family it spared since the last event would have retired it by (`spared`),
        the cap, how the record read and, when it did not, why (`error`). None when the keep is off, or keeps and spares
        nothing and read well. An unreadable record alerts once until it reads again."""
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
        dead = idle_dead(fam, self.settings, current=current if current is not None else self.identity())
        if not dead:
            return None
        if fam["id"] in (self.incubator_keep() if kept is None else kept):
            self.keep_spared[fam["id"]] = "idle"
            return None
        # THE IDLE RULE'S VERDICT (R11-1): the death is filed under what its Train record shows; only an untested family
        # (it never traded on Train) is "a time limit, not a finding". Train figures only (D2).
        return f"It {dead}. {idle_cause(train_record(self.store, fam)['screen'])}"

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
            result = self.store.retire_gym(fid, why, floor=int(self.settings.get("population", {}).get("floor", 16)),
                                           source="tournament")
        if result["status"] != "retired" or result.get("already_retired"):
            return None
        try:
            self.pool.cancel_family(fid)
        except Exception:  # noqa: BLE001
            pass
        return why

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
                                       source="tournament")
        if result["status"] != "retired" or result.get("already_retired"):
            return False
        try:
            self.pool.cancel_family(fam["id"])
        except Exception:  # noqa: BLE001
            pass
        return True

    # ------------------------------------------------------------------ the whole round
    def run(self) -> dict[str, Any]:
        began = self.clock()
        self.store.put("tournament_at", began)
        fams = self.store.families(alive=True)
        validation = self.validate(fams)
        facts = self.incubator_facts()
        fams = self.store.families(alive=True)
        self.allocate(fams)  # the shares retirements rank by (the least favoured go first)
        retired = self.retirements(self.store.families(alive=True))
        self.keep_event()  # THE COHORT KEEP's one private event a round
        born = self.forks(self.store.families(alive=True))
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


__all__ = ["Tournament", "IDLE_CAUSE", "keep_order", "KEEP_MAX", "KEEP_CEILING", "KEEP_SAMPLE_SESSIONS", "KEEP_SAMPLE_TRADES",
           "KEEP_UNPRACTICED", "KEEP_STALE_SECONDS"]
