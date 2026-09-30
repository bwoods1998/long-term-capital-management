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
3. THE BANDIT (`evidence.thompson`): each family's share of researcher cycles and Gym priority from its
   validation evidence, with at least 25% for the explore pool; a validated version that failed the drift screen earns
   nothing by its validation (the family counts as unvalidated). R11-5: only an old family whose latest validation mean
   is positive is exploited, each earning at most `exploit_per_positive` (0.15) of the share; an old family at zero or
   below competes in the explore pool with the new ones. THE PRACTICE BONUS (`practice.apply_bonus`): a family
   with a positive practice record on live quotes gains at most `practice.bonus` (25%) of its share, and the bonus moves
   at most `practice.bonus_total` (10%) of all share; it changes research attention only, never what is validated, the
   gate, the bands or money. The round's event records it (`practice_bonus`, private).
4. FORKS: the top families with a positive validation t fork (never one whose validated version failed the drift screen) (a new family on the parent's roots plus one more
   root of the rotation, same mechanism and structure; it inherits the lineage's trial count and holdout looks),
   while the population is under its ceiling. XSP is out of the rotation: its $0.50 a contract makes a narrow
   structure uneconomic.
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
   extension hold (R11-4's swarm rule, `researcher.mark_extension`). Each counted verdict records the family's trials
   (`validated_trials`), from which the idle rule counts, and restarts its dormant cycles. THE IDLE PASS (R4,
   `idle_pass`) retires by the idle rule alone every `tournament.retire_every_seconds` (300) between the rounds.
6. THE LEADERBOARD: one `swarm.tournament` event (the House mirrors it to its ledger) with every family's
   rank, share, validation summary, trials and band, and the totals.

Standard library only.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Mapping

from . import diagnostics, evidence, incubator, practice
from .pool import GymJob, PoolError
from .researcher import (IDLE_CAUSE, MAX_ROOTS, drift_verdict, held_at_gate, idle_cause, idle_dead, mark_extension, needs_roots,
                         robust_at_stress, screen_best, train_record, validation_drift_failed, with_roots)
from .store import CLOSEABLE, SwarmStore

UNIVERSE_ROTATION = ("SPY", "QQQ", "IWM", "SPXW")
INDEX = ("XSP", "SPXW")
#: Never added by a fork (the sprint, Sept 26): XSP's $0.50 a contract makes narrow XSP structures uneconomic.
NOT_ROTATED = ("XSP",)
#: `IDLE_CAUSE` (researcher.py, re-exported here) is the words of an UNTESTED idle-rule death; a tested one carries its
#: verdict (R11-1, `researcher.idle_cause`).


class Tournament:
    def __init__(self, store: SwarmStore, pool: Any, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time,
                 rng: random.Random | None = None):
        self.store = store
        self.pool = pool
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.Random()
        self.idle_at = float("-inf")  # the last idle pass (`idle_due`); in memory: a restarted swarm runs one at once
        self.practice_bonus: dict[str, float] = {}  # the last allocation's practice bonus by family (`allocate`)

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
        # waits for its 2017-19 extension result, exempt from the dormancy clause, until the operator clears the flag.
        if mark_extension(self.store, fid, n, line, self.settings, clock=self.clock):
            out["extension_hold"] = True
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

    # ------------------------------------------------------------------ 3. the bandit
    def allocate(self, fams: list[dict[str, Any]]) -> dict[str, float]:
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
        for fam in fams:
            if validation_drift_failed(fam):
                continue  # its validated version failed the drift screen: nothing to fork
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
        the child's roots, as its first version."""
        fam = self.store.family(fam["id"]) or fam
        if fam.get("retired_at") or len(fam["roots"]) >= MAX_ROOTS:
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
        for fam in sorted(fams, key=lambda f: (f.get("weight") or 0.0)):
            why = self._retire_if(fam["id"], lambda fam: self._why(fam, current))
            if why:
                out.append({"family": fam["id"], "why": why})
        return out

    def _why(self, fam: Mapping[str, Any], current: tuple[Any, Any]) -> str | None:
        """The hourly round's reason to retire a family (its rules in order, the idle rule last), or None."""
        if fam["band"] != "gym":
            return None  # a Candidate or better is judged by its forward record, not here
        state = fam.get("state") or {}
        from .researcher import extension_held
        if held_at_gate(fam) or state.get("gate_ready") or state.get("look_inflight") or extension_held(fam):
            # The operator holds its validated version at the gate: no rule retires it until the hold is cleared (the
            # look it holds must still happen; `SwarmStore.retire_gym` refuses it too).
            return None
        why = None
        if int(fam.get("since_val_revisions") or 0) >= int(self.cfg.get("retire_revisions", 30)):
            why = f"no validation improvement in {fam['since_val_revisions']} revisions"
        elif int(fam.get("since_val_trials") or 0) >= int(self.cfg.get("retire_evaluations", 2000)):
            why = f"no validation improvement in {fam['since_val_trials']} Gym evaluations"
        else:
            line = (fam.get("state") or {}).get("validation_line") or {}
            dsr = (line.get("numbers") or {}).get("dsr")
            if int(fam.get("validations") or 0) >= int(self.cfg.get("retire_min_validations", 6)) and dsr is not None \
                    and dsr < float(self.cfg.get("retire_dsr_below", 0.05)):
                # No figure in the reason: it becomes a graveyard lesson researchers read (D2a).
                why = "its trial-adjusted evidence fell below the line (the deflated Sharpe probability)"
        if not why:
            # The fallback for a dead family that never called retire (R3): Train figures only in the reason.
            why = self.idle_why(fam, current=current)
        return why

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

    def idle_why(self, fam: Mapping[str, Any], *, current: tuple[Any, Any] | None = None) -> str | None:
        """THE IDLE RULE's reason to retire a living Gym family (`researcher.idle_dead`), or None: never outside the Gym
        band nor while the operator holds its validated version at the gate (`held_at_gate`); `idle_dead` itself exempts
        a version at the gate, a look out, a passing validation owed again on the Gym running now (`current`, R4) and,
        from its dormancy clause, a best that awaits validation."""
        if fam.get("band") != "gym" or fam.get("retired_at") or held_at_gate(fam):
            return None
        dead = idle_dead(fam, self.settings, current=current if current is not None else self.identity())
        if not dead:
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
        retired, skipped = [], []
        for fam in sorted(self.store.families(alive=True), key=lambda f: (f.get("weight") or 0.0, f["id"])):
            if busy is not None and busy(fam["id"]):
                skipped.append(fam["id"])
                continue
            why = self._retire_if(fam["id"], lambda fam: self.idle_why(fam, current=current))
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
        born = self.forks(self.store.families(alive=True))
        fams = self.store.families(alive=True)
        self.allocate(fams)  # again, so a newborn fork has its share at once
        board = []
        for fam in sorted(fams, key=lambda f: -(f.get("weight") or 0.0)):
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
               "incubator": facts}
        self.store.event("swarm.tournament", None, row)
        self.store.put("leaderboard", {"at": began, "board": board, "totals": totals})
        return row


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


__all__ = ["Tournament", "IDLE_CAUSE"]
