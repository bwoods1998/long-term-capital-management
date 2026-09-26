"""The hourly tournament: validation, the bandit, forks, retirements, lessons, the leaderboard.

1. VALIDATION. Every living family whose best version (submitted, else its best Train score) has not been
   validated yet runs on Validation once, but only after that version's 1.5x-stress Train robustness run came back
   with a profit (`tournament.require_robustness`, Sept 26: a version that loses at 1.5x never reaches the gate); the Gym runs its 1.5x-half-spread twin in the same batch (two
   trials, counted) and returns only the validation VIEW (no trades, dates or daily series). The
   researcher is told only whether the line was met and how many of its checks passed (D2a). A version runs on
   its own NEEDS roots (a family's roots may have moved since).
2. THE LINE (`evidence.validation_line`, as the owner's decision D2 amended it): its deflated Sharpe is on traded
   days with N = the lineage's validated versions (`SwarmStore.lineage_validated`). A family that meets it goes to
   the gate's queue.
3. THE BANDIT (`evidence.thompson`): each family's share of researcher cycles and Gym priority from its
   validation evidence, with 25% for new families.
4. FORKS: the top families with a positive validation t fork (a new family on the parent's roots plus one more
   root of the rotation, same mechanism and structure; it inherits the lineage's trial count and holdout looks),
   while the population is under its ceiling. XSP is out of the rotation: its $0.50 a contract makes a narrow
   structure uneconomic.
5. RETIREMENTS: no validation improvement in 30 revisions or 2,000 Gym evaluations, or trial-adjusted
   evidence below the line (the deflated Sharpe probability under `retire_dsr_below` after
   `retire_min_validations` validations); never below the population floor. Each retiree's lesson goes to
   the graveyard (its mechanism, what it tried, its best numbers, its last notebook lines).
6. THE LEADERBOARD: one `swarm.tournament` event (the House mirrors it to its ledger) with every family's
   rank, share, validation summary, trials and band, and the totals.

Standard library only.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Mapping

from . import diagnostics, evidence
from .pool import GymJob, PoolError
from .researcher import MAX_ROOTS, needs_roots, robust_at_stress, with_roots
from .store import CLOSEABLE, SwarmStore

UNIVERSE_ROTATION = ("SPY", "QQQ", "IWM", "SPXW")
INDEX = ("XSP", "SPXW")
#: Never added by a fork (the sprint, Sept 26): XSP's $0.50 a contract makes narrow XSP structures uneconomic.
NOT_ROTATED = ("XSP",)


class Tournament:
    def __init__(self, store: SwarmStore, pool: Any, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time,
                 rng: random.Random | None = None):
        self.store = store
        self.pool = pool
        self.settings = settings
        self.clock = clock
        self.rng = rng or random.Random()

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
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        for fam in fams:
            current = self.store.family(fam["id"])
            if current is None or current.get("retired_at"):
                continue
            fam = current
            n = self.candidate_version(fam)
            if n is None:
                continue
            state = fam.get("state") or {}
            if self.cfg.get("require_robustness", True) and not robust_at_stress(state, n):
                waiting.append(fam["id"])  # its robustness run at 1.5x has not landed (or lost): not validated yet
                continue
            if n == fam.get("validated_version") and state.get("validation_image") == image and state.get("validation_bundle") == bundle:
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
        return {"queued": len(jobs), "judged": judged, "errors": errors, "waiting_robustness": waiting}

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
        if counted:  # a re-judged recorded result is no new validation for the bandit
            self.store.bump(fid, validations=1)
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
                             gate_ready=bool(line["passed"]))
        return {"version": n, "passed": line["passed"], "mean": mean, "t": t}

    # ------------------------------------------------------------------ 3. the bandit
    def allocate(self, fams: list[dict[str, Any]]) -> dict[str, float]:
        rows = []
        for fam in fams:
            nums = (fam.get("state") or {}).get("validation_numbers") or {}
            rows.append({"id": fam["id"], "validations": fam.get("validations") or 0, "mean": nums.get("mean"), "t": nums.get("t")})
        shares = evidence.thompson(rows, explore_share=float(self.cfg.get("explore_share", 0.25)),
                                   new_validations=int(self.cfg.get("new_family_validations", 2)), rng=self.rng)
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
        for fam in sorted(fams, key=lambda f: (f.get("weight") or 0.0)):
            fam = self.store.family(fam["id"]) or fam
            if fam["band"] != "gym":
                continue  # a Candidate or better is judged by its forward record, not here
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
            if why:
                if self.retire(fam, why):
                    out.append({"family": fam["id"], "why": why})
        return out

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
        totals = self.store.totals()
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(began - 3600))
        cycles = self.store._all("SELECT COUNT(*) AS n, SUM(CASE WHEN payload LIKE '%\"error\"%' THEN 1 ELSE 0 END) AS errors FROM events"
                                 " WHERE kind='swarm.cycle' AND at >= ?", (since,))[0]
        last_hour = {"cycles": int(cycles["n"] or 0), "cycle_errors": int(cycles["errors"] or 0),
                     "usd": {k: round(self.store.spent([k], since=began - 3600), 4) for k in ("sail_model", "gym_box", "openai")}}
        row = {"at": began, "seconds": round(self.clock() - began, 1), "validation": validation, "retired": retired, "born": born,
               "board": board, "totals": totals, "last_hour": last_hour}
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


__all__ = ["Tournament"]
