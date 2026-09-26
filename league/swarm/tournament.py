"""The hourly tournament: validation, the bandit, forks, retirements, lessons, the leaderboard.

1. VALIDATION. Every living family whose best version (submitted, else its best Train score) has not been
   validated yet runs on Validation once; the Gym runs its 1.5x-half-spread twin in the same batch (two
   trials, counted) and returns only the validation VIEW (no trades, dates or daily series). The
   researcher is told the mean, t, quarters positive and whether the line was met.
2. THE LINE (`evidence.validation_line`, the plan's): a family that meets it goes to the gate's queue.
3. THE BANDIT (`evidence.thompson`): each family's share of researcher cycles and Gym priority from its
   validation evidence, with 25% for new families.
4. FORKS: the top families with a positive validation t fork (a new family on another root of the
   universe, same mechanism and structure; it inherits the lineage's trial count and holdout looks), while
   the population is under its ceiling.
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
from .store import CLOSEABLE, SwarmStore

UNIVERSE_ROTATION = ("SPY", "QQQ", "IWM", "XSP", "SPXW")
INDEX = ("XSP", "SPXW")


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
        for fam in fams:
            n = self.candidate_version(fam)
            if n is None or n == fam.get("validated_version"):
                continue
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            job = GymJob(family=fam["id"], version=n, code=version["code"], params=version["params"], window="validation",
                         roots=tuple(fam["roots"]), stress=1.0, purpose="validation", priority=1.0)
            jobs.append((fam, n, self.pool.submit(job)))
        errors = {}
        judged = {}
        deadline = self.clock() + timeout
        for fam, n, job in jobs:
            try:
                result = self.pool.wait(job, max(1.0, deadline - self.clock()))
            except PoolError as exc:
                errors[fam["id"]] = str(exc)[:300]
                continue
            fid = fam["id"]
            years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
            row = self.store.add_run(fid, n, result, window="validation", stress=1.0, purpose="validation", program_years=years)
            stressed = evidence.stressed_of(result)
            if isinstance(result.get("stress_1.5"), dict):
                twin = result["stress_1.5"]
                self.store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": twin.get("status") or "ok", "trials": 1,
                                            "summary": dict(twin)}, window="validation", stress=evidence.STRESS, purpose="validation",
                                   program_years=years)
            fam = self.store.family(fid)
            if fam is None:
                continue
            line = evidence.validation_line(result, stressed, lineage_trials=self.store.lineage_trials(fid),
                                            trial_sharpes=self.store.lineage_trial_sharpes(fid))
            view = diagnostics.validation_view(result, line)
            summary = result.get("summary") or {}
            mean = evidence.daily_mean(summary)
            t = evidence.daily_t(summary)
            improved = mean is not None and (fam.get("best_validation") is None or float(mean) > float(fam["best_validation"]))
            fields: dict[str, Any] = {"validated_version": n}
            if improved:
                fields.update(best_validation=float(mean), since_val_revisions=0, since_val_trials=0)
            self.store.update_family(fid, **fields)
            self.store.bump(fid, validations=1)
            self.store.set_state(fid, validation_view=view, validation_line=line, validation_version=n,
                                 typical_max_loss_usd=typical_max_loss(result),
                                 validation_numbers={"mean": mean, "t": t, "sharpe_daily": summary.get("sharpe_daily"),
                                                     "quarters": summary.get("quarters_positive")},
                                 gate_ready=bool(line["passed"]))
            judged[fid] = {"version": n, "passed": line["passed"], "mean": mean, "t": t}
        return {"queued": len(jobs), "judged": judged, "errors": errors}

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
            child = self.fork(fam)
            if child:
                born.append(child)
        return born

    def fork(self, fam: Mapping[str, Any]) -> str | None:
        """A child on the next root of the universe the parent does not trade (index roots only for types
        allowed there), with the parent's best program as its first version."""
        roots = [r for r in self.settings.get("gym", {}).get("roots", UNIVERSE_ROTATION)]
        taken = {tuple(f["roots"]) for f in self.store.families(alive=True) if f["mechanism"] == fam["mechanism"]}
        for root in roots:
            if (root,) in taken or root in fam["roots"]:
                continue
            if root in INDEX and fam["structure"] in ("calendar", "diagonal"):
                continue
            spec = dict(fam.get("spec") or {})
            spec.update({"id": f"{fam['id'].split('-on-')[0]}-on-{root.lower()}", "mechanism": fam["mechanism"],
                         "structure": fam["structure"], "roots": [root]})
            spec.pop("signal", None)  # its first version is the parent's program on the new root, not a starter
            child = self.store.add_family(spec, origin="fork", parent=fam["id"])
            best = self.store.version(fam["id"], self.candidate_version(fam))
            if best and best.get("code"):
                code = best["code"]
                for old in fam["roots"]:
                    code = code.replace(f'"{old}"', f'"{root}"').replace(f"'{old}'", f"'{root}'")
                self.store.add_version(child["id"], code, best.get("params") or {}, author=f"fork of {fam['id']}",
                                       note=f"the parent's version {best['n']} moved to {root}")
                self.store.note(child["id"], f"Forked from {fam['id']} (validation t {((fam.get('state') or {}).get('validation_numbers') or {}).get('t')}) "
                                             f"onto {root}. Version 1 is the parent's best with its roots renamed; check NEEDS, widths "
                                             f"and risk_usd for this root.")
            self.store.set_state(fam["id"], forked_at=self.clock())
            self.store.event("swarm.born", child["id"], {"parent": fam["id"], "mechanism": fam["mechanism"],
                                                          "structure": fam["structure"], "roots": [root], "origin": "fork"})
            return child["id"]
        return None

    # ------------------------------------------------------------------ 5. retirements
    def retirements(self, fams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        floor = int(self.settings.get("population", {}).get("floor", 16))
        alive = len(fams)
        out = []
        for fam in sorted(fams, key=lambda f: (f.get("weight") or 0.0)):
            if alive - len(out) <= floor:
                break
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
                    why = f"its trial-adjusted evidence fell below the line (deflated Sharpe probability {dsr:.3f})"
            if why:
                self.retire(fam, why)
                out.append({"family": fam["id"], "why": why})
        return out

    def retire(self, fam: Mapping[str, Any], why: str) -> None:
        state = fam.get("state") or {}
        notes = self.store.notebook(fam["id"], limit=4)
        lesson = (f"{fam['structure']} on {', '.join(fam['roots'])}: {why}. Tried {fam.get('revisions')} versions over "
                  f"{self.store.lineage_trials(fam['id'])} lineage trials; best Train score {fam.get('best_train')}; best validation "
                  f"{json_safe(state.get('validation_view'))}. Last notes: " + " | ".join(n["text"][:240] for n in notes))
        self.store.bury(fam["id"], lesson, {"validation": state.get("validation_view"), "best_train": fam.get("best_train")})
        self.store.retire(fam["id"], why)
        try:
            self.pool.cancel_family(fam["id"])
        except Exception:  # noqa: BLE001
            pass

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
