"""Standalone Train/Validation research scheduler with explicit collaborators.

This entry never loads an environment file, constructs a provider, runs the House,
adopts resources, schedules Gate/forward work or publishes state. Model and Gym
work cross the scoped host broker. Run it only inside a verified isolated process;
Python configuration checks are not a replacement for that process boundary.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import threading
import time
from typing import Any, Callable, Mapping


class ResearchControllerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ControllerConfig:
    runtime_scope: str
    tick_seconds: float = 20
    cycle_seconds: float = 60

    def __post_init__(self):
        if (not isinstance(self.runtime_scope, str) or not self.runtime_scope
                or len(self.runtime_scope) > 80 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in self.runtime_scope)):
            raise ResearchControllerError("an explicit independent runtime scope is required")
        for name in ("tick_seconds", "cycle_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 3600:
                raise ResearchControllerError("controller cadence must be finite and bounded")


def _no_credentials(env: Mapping[str, str]) -> None:
    if any(any(fragment in name.upper() for fragment in ("API_KEY", "API_SECRET", "TOKEN", "PASSWORD", "LEAGUE_ENV")) for name in env):
        raise ResearchControllerError("controller environment contains a credential or environment-file capability")


def explicit_settings(config: Mapping[str, Any], policy: Mapping[str, Any], *, checkpoint: str, roots: tuple[str, ...]):
    """Defaults plus supplied documents only; no local/root/env override readers."""
    from . import settings as settings_mod

    if not isinstance(config, Mapping) or not isinstance(policy, Mapping):
        raise ResearchControllerError("explicit configuration and policy documents are required")
    out = settings_mod.load(None, config=config, policy=policy)
    # This controller has no gate object or forward scheduler. These values also
    # keep its prompts and collaborators from planning an inaccessible resource.
    out["gym"]["image_checkpoint"] = checkpoint
    out["gym"]["gate_checkpoint"] = None
    out["gym"]["roots"] = list(roots)
    out["gate"] = {"enabled": False}
    out["forward"] = {"enabled": False}
    out["claude"] = {"enabled": False, "roles": []}
    out["openai"] = {"enabled": False}
    out["library"] = {"enabled": False}
    return out


def _verify_train_objective(store, expected: str) -> None:
    if store.get("train_objective") != expected:
        raise ResearchControllerError("the private Train objective is unresolved or changed")
    for family in store.families(alive=True):
        state = family.get("state") or {}
        migrated = state.get("objective_migrated")
        # A family born after the completed pass has no migration marker yet.
        if migrated not in (None, expected):
            raise ResearchControllerError("a living family has an unfinished Train objective migration")


def research_harness_identity(artifact_root: Path) -> str:
    """Bind holds to the actual runtime source, separately from the Gym evaluator.

    Source paths and bytes determine this identity; release directory names,
    tests, credentials, state files and wall-clock time do not. This reads code
    without importing House, Gate, providers, or their financial collaborators.
    """
    root = Path(artifact_root).resolve()
    files = sorted(path for path in (root / "league").rglob("*.py")
                   if "tests" not in path.relative_to(root / "league").parts)
    if not files:
        raise ResearchControllerError("research artifact has no runtime source")
    digest = hashlib.sha256()
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ResearchControllerError("research runtime source escapes the artifact")
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


class ResearchController:
    """Schedules actual research components and emits private funnel receipts."""

    def __init__(self, store, broker, config: ControllerConfig, *, researcher, tournament, architect,
                 verify_state: Callable[[], Any], clock: Callable[[], float] = time.time,
                 expected_evaluation: Mapping[str, Any] | None = None,
                 expected_train_objective: str | None = None,
                 research_settings: Mapping[str, Any] | None = None,
                 harness_identity: str | None = None):
        self.store, self.broker, self.config = store, broker, config
        self.researcher, self.tournament, self.architect = researcher, tournament, architect
        self.verify_state, self.clock = verify_state, clock
        self.expected_evaluation = dict(expected_evaluation) if expected_evaluation is not None else None
        self.expected_train_objective = expected_train_objective
        self.research_settings = research_settings if research_settings is not None else getattr(researcher, "settings", {})
        self.harness_identity = harness_identity
        self.last_cycle = float("-inf")
        self.last_family: str | None = None
        self.stop = threading.Event()
        self._stepping = threading.Lock()

    def _preflight(self):
        _no_credentials(os.environ)
        self.verify_state()
        if self.expected_train_objective is not None:
            _verify_train_objective(self.store, self.expected_train_objective)
        pool = getattr(self.researcher, "pool", None)
        if pool is not None and callable(getattr(pool, "recover", None)):
            # A free terminal receipt is still owed when new paid work is held.
            # The adapter reconciles only durable original requests, never runs
            # an evaluation here or treats an uncertain reply as a trial.
            pool.recover(researcher=self.researcher, tournament=self.tournament)
        result = self.broker.open_runtime()
        if not isinstance(result, Mapping) or result.get("scope") != self.config.runtime_scope:
            raise ResearchControllerError("broker runtime scope differs from private research state")
        if self.expected_evaluation is not None:
            actual = result.get("evaluation")
            expected = self.expected_evaluation
            if (not isinstance(actual, Mapping) or any(actual.get(key) != value for key, value in expected.items()
                                                       if key != "required_split")
                    or type(actual.get("max_split")) is not int
                    or actual["max_split"] < expected["required_split"]):
                raise ResearchControllerError("host evaluator/configuration differs from the controller artifact")
        budget = result.get("daily_budget")
        if (not isinstance(budget, Mapping) or budget.get("within_cap") is not True
                or type(budget.get("room_nanos")) is not int or budget["room_nanos"] <= 0):
            raise ResearchControllerError("the shared daily authority has no verified room for research")
        return result

    def _evidence(self, family, *, scan=None, ignore_notes=()):
        from .research_wait import evidence_key
        return evidence_key(self.store, family, self.research_settings,
                            release={"harness": self.harness_identity,
                                     "evaluation": self.expected_evaluation or {"runtime_scope": self.config.runtime_scope}},
                            scan=scan, ignore_notes=ignore_notes)

    def _pending(self, family):
        # A saved tool call or completed rewrite is owed work even when a wait's
        # other evidence is unchanged. Inspect only this private research store.
        return bool((family.get("state") or {}).get("rewrite_ready") or self.store.convo(family["id"])[1])

    def _holding(self, family, *, scan=None):
        wait = (family.get("state") or {}).get("research_wait")
        return (isinstance(wait, Mapping) and wait.get("format") == 1 and not self._pending(family)
                and wait.get("evidence") == self._evidence(family, scan=scan))

    def _remember_result(self, fid, result, began):
        """Record a hold against final evidence without swallowing mid-cycle news."""
        result = result if isinstance(result, Mapping) else {}
        with self.store.atomic():
            family = self.store.family(fid)
            if family is None or family.get("retired_at"):
                return
            wait = None
            owned = result.get("notebook_note_seqs") or ()
            owned = tuple(seq for seq in owned if type(seq) is int and seq > 0)
            if (result.get("hold") and not any(result.get(key) for key in
                    ("trials", "pending_run", "retired", "error", "gym_error", "gym_asked"))
                    and not self._pending(family)
                    and self._evidence(family, ignore_notes=owned) == began):
                wait = {"format": 1, "since": self.clock(), "evidence": self._evidence(family)}
            if wait is not None or (family.get("state") or {}).get("research_wait") is not None:
                self.store.set_state(fid, research_wait=wait)

    def _family(self):
        alive = self.store.families(alive=True)
        # A lineage waiting for its unseen test retains its record. Continuing
        # development must not silently spend/reopen a historical look.
        scan: dict[str, Any] = {}
        eligible = [f for f in alive if f.get("band") == "gym" and not any(
            (f.get("state") or {}).get(k) for k in ("gate_ready", "look_inflight", "gate_hold"))
                    and not self._holding(f, scan=scan)]
        eligible.sort(key=lambda f: (str(f.get("id"))))
        if not eligible:
            return None
        later = [f for f in eligible if self.last_family is None or f["id"] > self.last_family]
        chosen = (later or eligible)[0]
        self.last_family = chosen["id"]
        return chosen

    def _funnel(self, now: float):
        if self.store._one("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='research_baseline'") is None:
            raise ResearchControllerError("daily research funnel requires the immutable imported-run baseline")
        start = dt.datetime.fromtimestamp(now, dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        until = (start + dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self.store._all("SELECT window,status,COUNT(*) AS runs,SUM(trials) AS trials FROM runs r "
                               "WHERE at>=? AND at<? AND NOT EXISTS (SELECT 1 FROM research_baseline b "
                               "WHERE b.kind='run' AND b.identity=r.run_id) GROUP BY window,status", (since, until))
        families = self.store.families()
        scan: dict[str, Any] = {}
        return {"utc_day": start.date().isoformat(), "families": len(families),
                "alive": sum(not f.get("retired_at") for f in families),
                "awaiting_unseen": sum(bool((f.get("state") or {}).get("gate_ready")) for f in families),
                "waiting_for_evidence": sum(not f.get("retired_at") and f.get("band") == "gym"
                    and not any((f.get("state") or {}).get(key) for key in ("gate_ready", "look_inflight", "gate_hold"))
                    and self._holding(f, scan=scan) for f in families),
                "runs": [{"window": r["window"], "status": r["status"], "runs": int(r["runs"]),
                          "trials": int(r["trials"] or 0)} for r in rows],
                "unseen_evaluations_by_controller": 0, "financial_execution_by_controller": 0}

    def step(self):
        if not self._stepping.acquire(blocking=False):
            raise ResearchControllerError("a research tick is already in progress")
        try:
            now = self.clock()
            if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
                raise ResearchControllerError("invalid controller clock")
            row: dict[str, Any] = {"scope": self.config.runtime_scope, "at": now, "actions": []}
            try:
                preflight = self._preflight()
            except Exception as exc:
                # Do not increment family cycles, trials, attempts or look counts
                # when the entire paid scope has no admission evidence.
                row.update(status="held", reason=type(exc).__name__)
                row["funnel"] = self._funnel(now)
                self.store.event("swarm.isolated_controller", None, row)
                self.store.put("isolated_controller_heartbeat", row)
                return row
            row["daily_budget"] = dict(preflight["daily_budget"])
            for name, actor in (("tournament", self.tournament), ("architect", self.architect)):
                if actor.due():
                    try:
                        result = actor.run()
                        row["actions"].append({"kind": name, "result": result})
                    except Exception as exc:
                        row["actions"].append({"kind": name, "error": type(exc).__name__})
            if now - self.last_cycle >= self.config.cycle_seconds:
                family = self._family()
                if family is not None:
                    try:
                        began = self._evidence(family)
                        result = self.researcher.cycle(family["id"])
                        self._remember_result(family["id"], result, began)
                        row["actions"].append({"kind": "research", "family": family["id"], "result": result})
                    except Exception as exc:
                        row["actions"].append({"kind": "research", "family": family["id"], "error": type(exc).__name__})
                    self.last_cycle = now
            row.update(status="running", funnel=self._funnel(now))
            self.store.event("swarm.isolated_controller", None, row)
            self.store.put("isolated_controller_heartbeat", row)
            return row
        finally:
            self._stepping.release()

    def run(self, *, once=False):
        while not self.stop.is_set():
            self.step()
            if once:
                break
            self.stop.wait(self.config.tick_seconds)
        # Controller shutdown never forgets or mutates broker obligations. Host
        # operator/rollback cleanup remains available even if this process dies.
        return 0

    def close(self):
        """Never close SQLite underneath an in-flight dispatcher/late callback."""
        self.stop.set()
        pool = getattr(self.researcher, "pool", None)
        if pool is not None and not pool.stop(timeout=5):
            return False
        self.store.close()
        return True


def build_controller(root: Path, broker, config: ControllerConfig, *, image: str, artifact_root: Path,
                     config_document: Mapping[str, Any], policy_document: Mapping[str, Any], roots: tuple[str, ...]):
    """Build existing research actors with only explicit broker adapters."""
    from .research_state import artifact_identity, assert_isolated_state, guard_tournament
    from .research_adapters import ResearchModelRouter, ResearchGymPool
    from .store import SwarmStore
    from .researcher import Researcher, migrate_objective, objective_for
    from .tournament import Tournament
    from .architect import Architect

    _no_credentials(os.environ)
    identity = artifact_identity(image, artifact_root)
    verify = lambda: assert_isolated_state(root, runtime_scope=config.runtime_scope,
                                          expected_evaluator=identity, artifact_root=artifact_root)
    verify()  # fail before opening a writable store or constructing any paid collaborator
    harness = research_harness_identity(artifact_root)
    store = SwarmStore(root)
    try:
        settings = explicit_settings(config_document, policy_document, checkpoint=image, roots=roots)
        from . import settings as settings_mod
        capital_value = settings["gym"].get("capital", 5000)
        try:
            capital = Decimal(str(capital_value))
            if not capital.is_finite() or capital <= 0 or isinstance(capital_value, bool):
                raise InvalidOperation
        except InvalidOperation as exc:
            raise ResearchControllerError("explicit finite simulation capital is required") from exc
        with store.atomic():
            previous = store.get("train_objective")
            running = settings_mod.objective_span(previous)
            if previous is not None and previous != objective_for(None, running):
                raise ResearchControllerError("the stored Train objective is unreadable")
            selected = settings_mod.train_from(settings, running)
            objective = objective_for(settings, running)
            span_floors = {family["id"]: (family.get("state") or {}).get("span_trials", 0)
                           for family in store.families(alive=True)}
            # Stock migration reports per-family failures instead of raising.
            # One outer transaction prevents a partial pass from becoming paid state.
            migration = migrate_objective(store, settings=settings)
            if not isinstance(migration, Mapping) or type(migration.get("failed")) is not int or migration["failed"] != 0:
                raise ResearchControllerError("the Train objective migration did not complete")
            _verify_train_objective(store, objective)
            for family_id, floor in span_floors.items():
                if ((store.family(family_id) or {}).get("state") or {}).get("span_trials", 0) < floor:
                    raise ResearchControllerError("the Train migration lowered a historical span trial baseline")
        verify()  # The independent guard connection sees only committed changes.
        # Missing or invalid settings retain the migrated running span. Bind every
        # actor's manifest to that effective span without changing supplied documents.
        settings["gym"]["train_from"] = selected.isoformat()
        expected = {"image": image, "bundle": identity.bundle, "execution": identity.execution, "roots": list(roots),
                    "capital": format(capital.normalize(), "f"), "workers": settings["gym"].get("workers", 8),
                    "train_first": selected.isoformat(),
                    "required_split": settings_mod.train_split(settings, selected)}
    except BaseException:
        store.close()
        raise
    router = ResearchModelRouter(store, broker, settings=settings)
    pool = ResearchGymPool(store, broker, checkpoint=image, bundle=identity.bundle,
                           execution=identity.execution, train_first=selected.isoformat(),
                           roots=roots, settings=settings)
    researcher = Researcher(store, router, pool, settings, background=False)
    tournament = guard_tournament(Tournament(store, pool, settings), identity)
    architect = Architect(store, router, settings)
    return ResearchController(store, broker, config, researcher=researcher, tournament=tournament,
                              architect=architect, verify_state=verify, expected_evaluation=expected,
                              expected_train_objective=objective, research_settings=settings, harness_identity=harness)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--broker-socket", type=Path, required=True)
    parser.add_argument("--broker-uid", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--roots", required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    from .research_ipc import BrokerClient

    controller = build_controller(args.state, BrokerClient(args.broker_socket, broker_uid=args.broker_uid),
                                  ControllerConfig(args.scope), image=args.image, artifact_root=args.artifact,
                                  config_document=json.loads(args.config.read_text()),
                                  policy_document=json.loads(args.policy.read_text()), roots=tuple(args.roots.split(",")))
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: controller.stop.set())
    try:
        result = controller.run(once=args.once)
    finally:
        closed = controller.close()
    return result if closed else 2


if __name__ == "__main__":
    raise SystemExit(main())
