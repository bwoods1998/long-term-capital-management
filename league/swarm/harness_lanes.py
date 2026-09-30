"""The harness improvement loop's lanes beyond the scheduler: predeclared metrics, the protected boundary, read-only
House observers, ranking, held-out splits and the retain/revert comparison.

`league/swarm/improvement.py` runs the loop (capture -> prepare -> stage -> evaluate -> deploy -> canary -> reconcile);
this module says, per lane, WHAT is measured, what a candidate may touch, which fixed judge scores it offline, how its
canary is split and what retains it. Everything here is fixed before a candidate exists: a candidate cannot edit this
file, its judges (`league/swarm/harness_judges/`), the canary gate or the controller (`PROTECTED`), so it can improve
its lane's metric only by changing the harness, never by changing the score.

THE LANES (`LANES`; the operator's procedure is `playbooks/harness-improvement.md`):

- `research` (research workflow and tools). Bottleneck: Train runs spent on programs that cannot run. Primary metric
  `train_dq_rate` = runtime-disqualified Train runs / Train runs; secondary `gym_seconds_wasted_per_birth` = Gym
  seconds of cycles whose run was disqualified, refused or erred / families born. Surface: the researcher, its tools
  and preflight, the program contract text.
- `memory` (prompts, memory, retrieval). Bottleneck: failed mechanisms reborn. Primary `graveyard_rebirth_rate` =
  births whose mechanism is the same idea (a FROZEN detector below, not the architect's) as an earlier graveyard row on
  the same slice / births; secondary `validation_attempts_per_usd` = validation runs / research dollars. Surface: the
  architect, strategist, diagnostician and researcher prompts and retrieval.
- `data` (data processing). Bottleneck: Gym result delivery and data jobs that fail and requeue. Primary
  `slot_failure_rate` = job slots in failed Gym batches / job slots attempted; secondary `run_error_rate`. Surface: the
  Sailbox transport, the Gym pool's batch handling, the data-job supervisor and the data scripts' retry bookkeeping.
- `execution` (execution reliability). Bottlenecks: practice intents the harness rejects (`harness_reject_rate` =
  rejects whose reason names a harness condition, not the program or the account's size / intents) and restarts that
  do not restore the live instances (`restart_failure_rate`). Surface: the practice/paper/real order lifecycle and the
  live state. Every file there moves the evaluator fingerprint (`league/swarm/evaluator.py`), so this lane's
  candidates wait for a PLANNED release (an evidence reset); its canary is the practice arm.

WHAT THE OBSERVERS READ. Only operational counts, through read-only (`mode=ro`) SQLite opens: run statuses and times
(never a run's score or summary figures), cycle counters (never the cycle's note or score), births' mechanisms and the
graveyard's mechanism column (never lessons' figures), spend totals, pool events, practice receipts' kinds and reject
reasons, live order statuses and event kinds, House restarts. Never a program, a quote, a parameter, a validation
number or the holdout (`looks`). Error texts are cut to a normalized signature (`signature`).

HELD-OUT. A capture names its motivating units (the families, births or boxes whose rows the brief shows the patch
author). The retention comparison EXCLUDES them, and the offline judge scores a held-out split generated from a seed
that exists only after the candidate is committed (`heldout_seed`: the journal's private secret and the staged
commit), so an improvement must survive examples its author never saw.

Standard library only (the observers run on the House, the loop on the owner's machine).
"""

from __future__ import annotations

import ast
import datetime as dt
import fnmatch
import gzip
import hashlib
import json
import math
import random
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = 1
POLICY = "harness-lanes-1"

# ------------------------------------------------------------------------------------------------ the protected boundary
#: The evaluator fingerprint's shared files (`league.gym.driver.LEAGUE_FILES`; a test keeps this copy equal).
LEAGUE_FILES = ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/stats.py")
#: Paths no lane's candidate may change, with why. `*` matches across `/`. The success metric and this loop come first:
#: a candidate that could edit its judge, its metric or its tests could improve its score without improving the harness.
PROTECTED: tuple[tuple[str, str], ...] = (
    # the objective, the success metric and the loop that measures it
    ("league/swarm/improvement.py", "objective"), ("league/swarm/improvement_benchmark.py", "objective"),
    ("league/swarm/harness_lanes.py", "objective"), ("league/swarm/harness_judges/*", "objective"),
    ("league/swarm/canary.py", "objective"), ("league/swarm/harness_runtime.py", "objective"),
    ("scripts/harness_improve.py", "objective"), ("playbooks/harness-improvement.md", "objective"),
    ("league/swarm/benchmarks.py", "objective"), ("league/swarm/long_single_benchmarks.py", "objective"),
    ("league/swarm/evidence.py", "objective"), ("league/stats.py", "objective"), ("docs/goals/*", "objective"),
    ("docs/benchmarks/*", "objective"), ("league/tests/*", "objective"),
    # sealed evaluation data, the evaluator and what a researcher may see of Validation (D2a)
    ("league/gym/*", "sealed"), ("league/swarm/gate.py", "sealed"), ("league/swarm/bands.py", "sealed"),
    ("league/swarm/evaluator.py", "sealed"), ("league/swarm/settings.py", "sealed"), ("league/swarm/diagnostics.py", "sealed"),
    ("league/swarm/tournament.py", "sealed"), ("league/swarm/store.py", "sealed"), ("ltcm/data/*", "sealed"),
    ("scripts/data/window.py", "sealed"), ("scripts/data/images.py", "sealed"), ("scripts/data/universe.py", "sealed"),
    ("scripts/data/frames.py", "sealed"), ("scripts/data/complete.py", "sealed"), ("scripts/data/check.py", "sealed"),
    ("scripts/data/sip.py", "sealed"), ("scripts/data/backfill.py", "sealed"), ("scripts/data/calibration.py", "sealed"),
    # funded spending limits
    ("league/swarm/guard.py", "spend"), ("league/swarm/models.py", "spend"), ("league/swarm/funding.py", "spend"),
    ("league/config.json", "spend"), ("league/budget.py", "spend"), ("league/pacer.py", "spend"),
    ("league/campaigns.py", "spend"), ("league/funded.py", "spend"), ("league/economy.py", "spend"),
    ("league/project_economics.py", "spend"), ("gateway/*", "spend"),
    # capital permissions
    ("league/constitution.py", "capital"), ("league/grants.py", "capital"), ("league/capital.py", "capital"),
    ("league/live/money.py", "capital"), ("league/live/house_test.py", "capital"), ("league/live/calibration.py", "capital"),
    ("league/live/families.py", "capital"), ("league/live/step.py", "capital"), ("league/live_trading.py", "capital"),
    ("league/allocator.py", "capital"), ("league/exposure.py", "capital"),
    # the release train
    ("deploy/*", "release"), (".github/*", "release"), ("league/updater.py", "release"), ("league/watchdog.py", "release"),
    ("scripts/floor_box.py", "release"), ("CHANGELOG.md", "release"),
)
#: A candidate may ADD a test file of its own (never edit an existing one): the judges and regressions stay fixed.
NEW_TEST = "league/tests/test_harness_candidate_*.py"
#: Calls and imports a candidate may not introduce anywhere (reflection, process, network, file writes, environment).
DANGEROUS_CALLS = frozenset({"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "_getframe",
                             "setattr", "delattr", "open", "system", "popen", "Popen", "check_output", "check_call",
                             "urlopen", "create_connection", "putenv", "unsetenv", "chmod", "chown", "unlink", "rmtree",
                             "write_text", "write_bytes", "fork", "kill", "killpg"})
DANGEROUS_MODULES = frozenset({"subprocess", "socket", "urllib", "http", "ctypes", "importlib", "shutil", "pickle",
                               "marshal", "requests", "ssl", "multiprocessing"})
#: A file that already speaks to the network (the Sailbox transport) may import more of the network family.
NETWORK_MODULES = frozenset({"http", "urllib", "socket", "ssl"})
#: The spend, capital and release modules: a candidate may not start importing them (its lane never needs to).
FORBIDDEN_IMPORTS = ("league.swarm.guard", "league.swarm.funding", "league.budget", "league.pacer", "league.campaigns",
                     "league.funded", "league.economy", "league.project_economics", "league.constitution", "league.grants",
                     "league.capital", "league.live.money", "league.live.house_test", "league.live.calibration",
                     "league.live_trading", "league.allocator", "league.exposure", "league.updater", "league.watchdog",
                     "league.swarm.improvement", "league.swarm.harness_lanes", "league.swarm.harness_judges")
#: Release classes (D8 and the evidence rules, GOAL.md section 3 and 4).
DEPLOY_RULES = {
    "research": "research-side: may deploy in session only with an adversarial review, green CI and on-box verification, "
                "never 15:30-16:00 New York while the House test runs, and never while a calibration order works",
    "money_path": "money path (a module the live path loads): deploy only after the close (20:05Z until Nov 1), two "
                  "adversarial money-path reviews, green CI",
    "evidence_reset": "evidence reset (league/gym, league/live or the fingerprint's files): a PLANNED release between "
                      "evidence windows only; log the reset in the run record; two money-path reviews",
}


def protected_reason(path: str) -> str | None:
    """The category that protects `path`, or None. A new candidate test file is allowed."""
    if fnmatch.fnmatchcase(path, NEW_TEST):
        return None
    for pattern, why in PROTECTED:
        if fnmatch.fnmatchcase(path, pattern):
            return why
    return None


def live_path_modules(tree: Path) -> set[str]:
    """Repo-relative files the live path loads, by the method D8 names (GOAL.md section 3): every import of
    `league/live/*.py` (the CLI `__main__` aside), module-level and lazy alike, and the module-level import closure of
    everything so reached. A lazy import inside a module outside `league/live` is not followed: it loads only when
    that function runs, which the operator's runtime import trace settles. Resolved statically from the tree."""
    tree = Path(tree)
    seen: set[str] = set()
    live = {p.relative_to(tree).as_posix() for p in (tree / "league" / "live").glob("*.py") if p.name != "__main__.py"}
    todo = sorted(live)

    def resolve(name: str) -> list[str]:
        parts = name.split(".")
        out = []
        for n in range(len(parts), 0, -1):
            base = tree.joinpath(*parts[:n])
            for cand in (base.with_suffix(".py"), base / "__init__.py"):
                if cand.is_file():
                    out.append(cand.relative_to(tree).as_posix())
                    # a package's parents' __init__ run too
            if out:
                break
        for n in range(1, len(parts)):
            init = tree.joinpath(*parts[:n]) / "__init__.py"
            if init.is_file():
                out.append(init.relative_to(tree).as_posix())
        return out

    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        path = tree / rel
        try:
            module = ast.parse(path.read_text())
        except (OSError, SyntaxError, ValueError):
            continue
        package = rel[:-3].split("/")[:-1]
        if rel in live:
            nodes = list(ast.walk(module))
        else:
            # Module level only: top-level statements and the bodies of top-level if/try blocks, never a def's body.
            nodes, stack = [], list(module.body)
            while stack:
                node = stack.pop()
                nodes.append(node)
                if isinstance(node, (ast.If, ast.Try)):
                    stack.extend(node.body + node.orelse + getattr(node, "finalbody", [])
                                 + [s for h in getattr(node, "handlers", []) for s in h.body])
        for node in nodes:
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    anchor = package[: len(package) - node.level + 1] if node.level > 1 else package
                    base = ".".join(anchor + ([node.module] if node.module else []))
                else:
                    base = node.module or ""
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            for name in names:
                if name.split(".")[0] in ("league", "ltcm"):
                    todo.extend(m for m in resolve(name) if m not in seen)
    return seen


def classify(paths: Iterable[str], live_modules: set[str]) -> dict[str, Any]:
    """Each changed path's release class and the strictest one (the deploy rule the whole candidate follows)."""
    out: dict[str, list[str]] = {"evidence_reset": [], "money_path": [], "research": []}
    for path in sorted(set(paths)):
        if path.startswith(("league/gym/", "league/live/")) or path in LEAGUE_FILES:
            out["evidence_reset"].append(path)
        elif path in live_modules or path.startswith("gateway/") or path == "league/constitution.py":
            out["money_path"].append(path)
        else:
            out["research"].append(path)
    strictest = next(c for c in ("evidence_reset", "money_path", "research") if out[c] or c == "research")
    return {"paths": out, "release_class": strictest, "deploy_rule": DEPLOY_RULES[strictest]}


def content_guard(path: str, before: str | None, after: str) -> None:
    """Refuse a Python change that introduces reflection, processes, network, file writes or a protected import. The
    comparison is by name, so moving an existing call is allowed; a new one is not. Not a proof of safety: the sandbox
    and the adversarial review remain."""
    if not path.endswith(".py"):
        return
    from .improvement import ImprovementError  # local: improvement imports this module

    def facts(source: str | None) -> tuple[set[str], set[str], bool]:
        if not source:
            return set(), set(), False
        tree = ast.parse(source)
        calls = {n.func.id if isinstance(n.func, ast.Name) else n.func.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))}
        modules = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                modules.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                # `from . import guard` names the module in the alias: record the base and every base.name.
                base = "." * n.level + (n.module or "")
                if n.module:
                    modules.add(base)
                modules.update(f"{base}{'.' if n.module else ''}{a.name}" for a in n.names)
        glob = any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(tree))
        return calls, modules, glob

    old_calls, old_modules, old_global = facts(before)
    new_calls, new_modules, new_global = facts(after)
    if (new_calls - old_calls) & DANGEROUS_CALLS:
        raise ImprovementError(f"{path}: candidate introduces {sorted((new_calls - old_calls) & DANGEROUS_CALLS)}")
    package = path[:-3].split("/")[:-1]
    networked = any(m.split(".")[0] in NETWORK_MODULES for m in old_modules)
    bad = set()
    for module in new_modules - old_modules:
        level = len(module) - len(module.lstrip("."))
        name = module.lstrip(".")
        absolute = ".".join((package[: len(package) - level + 1] if level else []) + [name]) if level else name
        top = absolute.split(".")[0]
        if (top in DANGEROUS_MODULES and not (networked and top in NETWORK_MODULES)) or any(
                absolute == f or absolute.startswith(f + ".") for f in FORBIDDEN_IMPORTS):
            bad.add(module)
    if bad:
        raise ImprovementError(f"{path}: candidate imports {sorted(bad)} (process, network or protected modules)")
    if new_global and not old_global:
        raise ImprovementError(f"{path}: candidate introduces global or nonlocal mutation")


# ------------------------------------------------------------------------------------------------ lanes
@dataclass(frozen=True)
class Metric:
    """A ratio of sums over units: `numerator` / `denominator` fields of the observer's per-unit tallies."""
    name: str
    numerator: str
    denominator: str
    direction: str = "lower"            # "lower" or "higher" is better
    threshold: float = 0.0              # a capture needs the metric at least this bad
    min_units: int = 0                  # ... and at least this much denominator
    min_effect: float = 0.25            # retention: relative improvement required (primary) / tolerated worsening (guard)
    abs_tolerance: float = 0.0          # a guard also passes when it worsens by at most this much in absolute terms

    def value(self, tallies: Mapping[str, float]) -> float | None:
        den = float(tallies.get(self.denominator) or 0.0)
        return float(tallies.get(self.numerator) or 0.0) / den if den > 0 else None

    def bad(self, value: float | None) -> bool:
        """Whether a measured value is a bottleneck: at least `threshold` when lower is better, at most it when higher is."""
        if value is None:
            return False
        return value >= self.threshold if self.direction == "lower" else value <= self.threshold


@dataclass(frozen=True)
class Bottleneck:
    metric: Metric
    secondary: tuple[Metric, ...]       # must not worsen (by more than each one's min_effect) at retention
    summary: str
    judge_primary: str                  # the fixed judge's count for this bottleneck (lower is better)
    judge_mode: str = "improve"         # "improve": must fall on the held-out split by judge_effect; "hold": must not rise
    judge_effect: float = 0.25
    severity: str = "high"
    canary: Mapping[str, Any] = field(default_factory=dict)   # overrides the lane's canary for this bottleneck


@dataclass(frozen=True)
class Lane:
    id: str
    title: str
    bottlenecks: tuple[Bottleneck, ...]
    guards: tuple[Metric, ...]          # quality and cost: must not worsen beyond min_effect
    surface: tuple[str, ...]            # editable globs (protected paths are refused anyway)
    release_classes: tuple[str, ...]
    judge: str                          # harness_judges/<judge>.py
    protocol: str
    judge_zero: tuple[str, ...]         # judge counts that must be 0 in the candidate (safety)
    judge_no_worse: tuple[str, ...]     # judge counts that must not rise
    judge_cost: str                     # the judge's cost measure
    judge_cost_rule: str                # "ratio": at most max(COST_FLOOR, COST_RATIO x baseline); "pays": the added cost
                                        # is at most max(COST_FLOOR, PAYS_SHARE x what the primary saved)
    regressions: tuple[str, ...]
    canary: Mapping[str, Any] = field(default_factory=dict)

    def bottleneck(self, name: str) -> Bottleneck:
        for b in self.bottlenecks:
            if b.metric.name == name:
                return b
        raise KeyError(name)

    def canary_for(self, bottleneck: Bottleneck) -> dict[str, Any]:
        return {**dict(self.canary), **dict(bottleneck.canary)}

    def spec(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), default=list))


COST_RATIO, COST_FLOOR, PAYS_SHARE = 1.25, 2.0, 0.25

LANES: dict[str, Lane] = {
    "research": Lane(
        id="research", title="Research workflow and tools",
        bottlenecks=(Bottleneck(
            Metric("train_dq_rate", "dq_runs", "train_runs", threshold=0.05, min_units=200, min_effect=0.25),
            (Metric("gym_seconds_wasted_per_birth", "wasted_gym_seconds", "births", min_effect=0.0),),
            "Train runs are disqualified at runtime: programs that cannot run spend a multi-year replay, a trial and "
            "a research cycle each.", judge_primary="gym_seconds_wasted", judge_effect=0.20),),
        guards=(Metric("ok_runs_per_usd", "ok_runs", "research_usd", direction="higher", min_effect=0.10),
                Metric("cycle_error_rate", "cycle_errors", "cycles", min_effect=0.20)),
        surface=("league/swarm/researcher.py", "league/swarm/preflight.py", "league/swarm/claude_research.py",
                 "league/CONTRACT.md", NEW_TEST),
        release_classes=("research", "money_path"),
        judge="research", protocol="research-workflow-v1", judge_zero=("false_refusals",), judge_no_worse=(),
        judge_cost="screen_seconds", judge_cost_rule="pays",
        regressions=("league.tests.test_swarm_researcher", "league.tests.test_swarm_store", "league.tests.test_swarm_loop"),
        canary={"mode": "arms", "unit": "family", "fraction": 0.25, "observe_seconds": 6 * 3600,
                "min_units_per_arm": 12},
    ),
    "memory": Lane(
        id="memory", title="Prompts, memory and retrieval",
        bottlenecks=(
            Bottleneck(
                Metric("graveyard_rebirth_rate", "rebirths", "births", threshold=0.05, min_units=30, min_effect=0.50),
                (Metric("validation_attempts_per_usd", "validation_runs", "research_usd", direction="higher",
                        min_effect=0.0),),
                "New families repeat mechanisms the graveyard already buried on the same slice.",
                judge_primary="rebirths_admitted", judge_effect=0.25),
            # Evidence per dollar (the owner's answer 3, Sept 30): at the Sept 30 burn a research dollar bought about
            # three validation attempts and no pass. Fewer than ten per dollar is treated as a bottleneck. Offline the
            # judge cannot price a prompt (no provider call runs in the sandbox): a candidate must hold the rebirth
            # filter and the store's cost there ("hold"), and the canary carries the whole improvement claim.
            Bottleneck(
                Metric("validation_attempts_per_usd", "validation_runs", "research_usd", direction="higher",
                       threshold=10.0, min_units=10, min_effect=0.25),
                (Metric("graveyard_rebirth_rate", "rebirths", "births", min_effect=0.0, abs_tolerance=0.02),),
                "Research dollars buy few validation attempts: prompts and memory spend model calls on programs and "
                "families that never reach Validation.", judge_primary="rebirths_admitted", judge_mode="hold")),
        guards=(Metric("births_per_family_unit", "births", "units", direction="higher", min_effect=0.50),),
        surface=("league/swarm/architect.py", "league/swarm/strategist.py", "league/swarm/diagnostician.py",
                 "league/swarm/researcher.py", "league/swarm/seeds.py", NEW_TEST),
        release_classes=("research", "money_path"),
        judge="memory", protocol="memory-rebirth-v1", judge_zero=(), judge_no_worse=("novel_refused",),
        judge_cost="sqlite_statements", judge_cost_rule="ratio",
        regressions=("league.tests.test_swarm_r11b", "league.tests.test_swarm_verdicts", "league.tests.test_swarm_store"),
        canary={"mode": "arms", "unit": "family", "fraction": 0.5, "observe_seconds": 12 * 3600,
                "min_units_per_arm": 15},
    ),
    "data": Lane(
        id="data", title="Data processing",
        bottlenecks=(Bottleneck(
            Metric("slot_failure_rate", "slots_failed", "slots", threshold=0.005, min_units=100, min_effect=0.50),
            (Metric("run_error_rate", "error_runs", "runs", min_effect=0.0),),
            "Gym batches fail on delivery and requeue: every job slot in the batch waits and may run again.",
            judge_primary="failed_transient", judge_effect=0.50),),
        guards=(Metric("gym_usd_per_ok_slot", "gym_usd", "ok_slots", min_effect=0.10),),
        surface=("league/sailbox.py", "league/swarm/pool.py", "league/data_job.py", "scripts/data/boxlib.py",
                 "scripts/data/locking.py", "scripts/data/nightly.py", "scripts/data/sip_progress.py", NEW_TEST),
        release_classes=("research", "money_path"),
        judge="data", protocol="data-retry-v1", judge_zero=("retried_permanent",), judge_no_worse=(),
        judge_cost="requests", judge_cost_rule="ratio",
        regressions=("league.tests.test_gym_driver", "league.tests.test_gym_download_retry", "league.tests.test_swarm_pool"),
        canary={"mode": "window", "unit": "box", "observe_seconds": 24 * 3600, "min_units_per_arm": 3},
    ),
    "execution": Lane(
        id="execution", title="Execution reliability",
        bottlenecks=(
            Bottleneck(Metric("harness_reject_rate", "harness_rejects", "intents", threshold=0.02, min_units=50,
                              min_effect=0.50),
                       (Metric("reject_rate", "rejects", "intents", min_effect=0.0),),
                       "Practice intents are rejected for harness conditions (missing chains or quotes, stale state, "
                       "restart gaps), not for the program or the account's size.", judge_primary="valid_rejected",
                       judge_mode="hold", severity="high"),
            Bottleneck(Metric("restart_failure_rate", "restart_failures", "restarts", threshold=0.01, min_units=1,
                              min_effect=1.0),
                       (),
                       "A House restart did not restore every live instance cleanly within ten minutes.",
                       # The fixed judge's restart scenarios pass on the Sept 30 engine (0 divergences), so offline it
                       # can only hold; a House restart failure is shown fixed by the restarts after the release.
                       judge_primary="restart_divergences", judge_mode="hold", severity="critical",
                       # Restarts are House-wide: no family arm. Deliberate post-close restart tests after the planned
                       # release are the units, compared with the restarts before it.
                       canary={"mode": "window", "unit": "restart", "observe_seconds": 5 * 86400,
                               "min_units_per_arm": 3})),
        guards=(Metric("live_error_rate", "live_errors", "restarts_or_one", min_effect=0.0),),
        surface=("league/live/shadow.py", "league/live/paper.py", "league/live/real.py", "league/live/venue.py",
                 "league/live/chains.py", "league/live/state.py", "league/live/observe.py", "league/live/decider.py",
                 NEW_TEST),
        release_classes=("evidence_reset",),
        judge="execution", protocol="execution-recovery-v1", judge_zero=("invalid_accepted",),
        judge_no_worse=("valid_rejected", "restart_divergences"), judge_cost="cpu_seconds", judge_cost_rule="ratio",
        regressions=("league.tests.test_shadow_restart", "league.tests.test_live_practice", "league.tests.test_live_paper",
                     "league.tests.test_live_observe"),
        # Five trading sessions of practice: a calendar week of wall-clock time (the measurement's longest window).
        canary={"mode": "practice", "unit": "family", "fraction": 0.5, "observe_seconds": 7 * 86400,
                "min_units_per_arm": 8, "planned_release": True},
    ),
}


def lane_sha(lane: Lane) -> str:
    return hashlib.sha256(json.dumps(lane.spec(), sort_keys=True).encode()).hexdigest()


def surface_check(lane: Lane, paths: Sequence[str]) -> None:
    from .improvement import ImprovementError

    if not paths:
        raise ImprovementError("the candidate changes nothing")
    for path in paths:
        why = protected_reason(path)
        if why:
            raise ImprovementError(f"{path} is protected ({why}); every lane's candidate is refused there")
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in lane.surface):
            raise ImprovementError(f"{path} is outside the {lane.id} lane's surface {list(lane.surface)}")


# ------------------------------------------------------------------------------------------------ observers (read only)
def iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def epoch_of(text: Any) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def connect_ro(path: Path) -> sqlite3.Connection:
    """A read-only open. A WAL file whose -wal/-shm are absent (no writer has it open) is opened immutable, because a
    mode=ro open would otherwise create them."""
    path = Path(path)
    uri = f"file:{path}?mode=ro"
    try:
        with open(path, "rb") as handle:
            head = handle.read(20)
        wal = len(head) >= 20 and head[18] == 2
    except OSError:
        wal = False
    if wal and not (Path(str(path) + "-wal").exists() and Path(str(path) + "-shm").exists()):
        uri += "&immutable=1"
    return sqlite3.connect(uri, uri=True, timeout=5)


def signature(text: Any) -> str:
    """An error text cut to its shape: quoted identifiers kept (API names), other quoted text, numbers, hex and paths
    replaced, at most 160 characters."""
    out = str(text or "")
    out = re.sub(r"(['\"])([^'\"]{0,80})\1", lambda m: m.group(0) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", m.group(2))
                 else "'<text>'", out)
    out = re.sub(r"(/[\w.-]+)+", "<path>", out)
    out = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", out)
    out = re.sub(r"\b\d+(?:\.\d+)?\b", "#", out)
    out = re.sub(r"([\^~])\1+", r"\1", out)
    return re.sub(r"\s+", " ", out).strip()[:160]


_STOP = frozenset("a an and are as at be by for from in into is it its of on or than that the their then this to when with "
                  "options option sell buy".split())
#: THE REBIRTH DETECTOR, frozen here so a candidate that changes the architect's own rule (`architect.same_idea`) cannot
#: change what this lane counts. A birth is a rebirth when an earlier graveyard row on the same slice (structure group and
#: roots) has the same idea: content-word Jaccard of the mechanisms' FIRST SENTENCES (the claim) >= FIRST_IDEA, or of the
#: whole texts >= SAME_IDEA (the architect's rule). Calibrated Sept 30, 2026 on the House's 739 births of the previous
#: day: whole-text Jaccard never reached 0.5 (the long texts dilute it) although clear rebirths existed; every inspected
#: pair at first-sentence Jaccard >= 0.3 (8 of 8) restated a buried idea, against 1 of 3 at 0.2-0.3. About 2% of births.
SAME_IDEA = 0.5
FIRST_IDEA = 0.3
SINGLES = ("long_single", "long_call", "long_put")


def words(text: Any) -> frozenset[str]:
    return frozenset(w for w in "".join(c if c.isalnum() else " " for c in str(text).lower()).split()
                     if len(w) > 2 and w not in _STOP)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def first_sentence(text: Any) -> str:
    return re.split(r"(?<=[.;:])\s", " ".join(str(text or "").split()), maxsplit=1)[0]


def same_idea(a: Any, b: Any) -> float:
    """The detector's score for two mechanisms (see FIRST_IDEA): >= 1.0 means the same idea."""
    whole = jaccard(words(a), words(b)) / SAME_IDEA
    first = jaccard(words(first_sentence(a)), words(first_sentence(b))) / FIRST_IDEA
    return max(whole, first)


def slice_key(structure: Any, roots: Any) -> tuple[str, tuple[str, ...]]:
    if isinstance(roots, str):
        try:
            roots = json.loads(roots)
        except ValueError:
            roots = [roots]
    group = "single" if structure in SINGLES else str(structure)
    return group, tuple(sorted(str(r).upper() for r in roots or []))


def _num(value: Any) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) and x > 0 else 0.0


def _add(units: dict[str, dict[str, float]], unit: str, **values: float) -> None:
    row = units.setdefault(str(unit), {})
    for name, value in values.items():
        row[name] = row.get(name, 0.0) + float(value)


def totals(units: Mapping[str, Mapping[str, float]], exclude: Iterable[str] = ()) -> dict[str, float]:
    skip = set(exclude)
    out: dict[str, float] = {}
    for unit, row in units.items():
        if unit in skip:
            continue
        for name, value in row.items():
            out[name] = out.get(name, 0.0) + float(value)
    return out


RESEARCH_KINDS = ("claude", "sail_model", "openai")
_WASTED = ("disqualified", "refused", "error")


def _spend(db: sqlite3.Connection, since: float, until: float) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(usd by kind, research usd by family, gym box seconds/usd/job slots) over [since, until)."""
    kinds: dict[str, float] = {}
    by_family: dict[str, float] = {}
    for kind, family, usd in db.execute("SELECT kind, family, usd FROM spend WHERE epoch>=? AND epoch<?", (since, until)):
        value = float(usd or 0.0)
        kinds[kind] = kinds.get(kind, 0.0) + value
        if kind in RESEARCH_KINDS and family:
            by_family[family] = by_family.get(family, 0.0) + value
    return kinds, by_family, {}


def _research(db: sqlite3.Connection, root: Path, since: float, until: float, examples: int) -> dict[str, Any]:
    units: dict[str, dict[str, float]] = {}
    lo, hi = iso(since), iso(until)
    statuses: dict[str, str] = {}
    dq_paths: list[tuple[str, str, str, str]] = []
    refused: list[tuple[str, str, str]] = []
    for run_id, family, status, at, path, summary in db.execute(
            "SELECT run_id, family, status, at, path, CASE WHEN status='refused' THEN summary END FROM runs "
            "WHERE window='train' AND purpose='train' AND at>=? AND at<?", (lo, hi)):
        statuses[str(run_id)] = str(status)
        _add(units, family, train_runs=1, dq_runs=status == "disqualified", ok_runs=status == "ok",
             refused_runs=status == "refused", error_runs=status == "error")
        if status == "disqualified" and path:
            dq_paths.append((str(family), str(at), str(path), str(run_id)))
        if status == "refused" and summary:
            try:
                refused.append((str(family), str(at), str((json.loads(summary) or {}).get("reason") or "")))
            except ValueError:
                pass
    # A cycle names the run it made. Worker run ids can carry a suffix in the store (`-<family>` or an evaluator scope):
    # match exactly, else on the 24-character worker id.
    prefix = {rid[:24]: status for rid, status in statuses.items()}
    matched = unmatched = 0
    for family, run_id, gym_seconds, cost, error in db.execute(
            "SELECT family, json_extract(payload,'$.run_id'), json_extract(payload,'$.gym_seconds'), "
            "json_extract(payload,'$.cost_usd'), COALESCE(json_extract(payload,'$.error'),'') NOT IN ('',0) "
            "FROM events WHERE kind='swarm.cycle' AND json_valid(payload) AND at>=? AND at<?", (lo, hi)):
        seconds = _num(gym_seconds)
        status = statuses.get(str(run_id)) or prefix.get(str(run_id)[:24]) if run_id else None
        if run_id and seconds:
            matched += status is not None
            unmatched += status is None
        wasted = status in _WASTED
        _add(units, family or "swarm", cycles=1, cycle_errors=bool(error), gym_seconds=seconds,
             wasted_gym_seconds=seconds if wasted else 0.0, wasted_model_usd=_num(cost) if wasted else 0.0)
    for (fid,) in db.execute("SELECT id FROM families WHERE born_at>=? AND born_at<?", (lo, hi)):
        _add(units, fid, births=1)
    kinds, by_family, _ = _spend(db, since, until)
    for fid, usd in by_family.items():
        _add(units, fid, research_usd=usd)
    signatures: dict[str, dict[str, Any]] = {}
    for family, at, path, run_id in dq_paths[-max(0, examples):]:
        result = _read_runtime(root / path)
        text = signature((result or {}).get("disqualified") or ((result or {}).get("messages") or ["unreadable"])[0])
        row = signatures.setdefault(text, {"signature": text, "n": 0, "families": [], "first_at": at})
        row["n"] += 1
        if family not in row["families"] and len(row["families"]) < 8:
            row["families"].append(family)
    for family, at, reason in refused[-max(0, examples):]:
        text = "refused: " + signature(reason)
        row = signatures.setdefault(text, {"signature": text, "n": 0, "families": [], "first_at": at})
        row["n"] += 1
        if family not in row["families"] and len(row["families"]) < 8:
            row["families"].append(family)
    ranked = sorted(signatures.values(), key=lambda r: (-r["n"], r["signature"]))
    return {"units": units, "spend": kinds, "join": {"cycles_with_gym_seconds_matched": matched, "unmatched": unmatched},
            "examples": ranked[:16], "sampled_disqualified": min(len(dq_paths), max(0, examples)),
            "disqualified_with_result": len(dq_paths)}


def _read_runtime(path: Path) -> dict[str, Any] | None:
    """Only a retained result's `runtime` block (errors and why it was disqualified); nothing it measured."""
    try:
        doc = json.loads(gzip.decompress(Path(path).read_bytes()))
    except (OSError, ValueError, EOFError):
        return None
    runtime = doc.get("runtime") if isinstance(doc, dict) else None
    if not isinstance(runtime, dict):
        return None
    return {"disqualified": runtime.get("disqualified"), "messages": list(runtime.get("messages") or [])[:2]}


def _memory(db: sqlite3.Connection, since: float, until: float) -> dict[str, Any]:
    """Units are mechanisms (`canary.mechanism_unit`): the memory lane's gate acts on a proposal before the store gives
    it a family id, so births, validation runs and spend are all keyed by their family's mechanism."""
    from .canary import mechanism_unit

    units: dict[str, dict[str, float]] = {}
    lo, hi = iso(since), iso(until)
    graves: dict[tuple[str, tuple[str, ...]], list[tuple[str, str, frozenset[str], frozenset[str]]]] = {}
    for family, at, mechanism, structure, roots in db.execute(
            "SELECT family, at, mechanism, structure, roots FROM graveyard WHERE at<?", (hi,)):
        graves.setdefault(slice_key(structure, roots), []).append(
            (str(at), str(family), words(mechanism), words(first_sentence(mechanism))))
    unit_of = {str(fid): mechanism_unit(mechanism) for fid, mechanism in db.execute("SELECT id, mechanism FROM families")}
    pairs = []
    by_origin: dict[str, list[int]] = {}
    for fid, origin, mechanism, structure, roots, born in db.execute(
            "SELECT id, origin, mechanism, structure, roots, born_at FROM families WHERE born_at>=? AND born_at<? "
            "ORDER BY born_at, id", (lo, hi)):
        mine, claim = words(mechanism), words(first_sentence(mechanism))
        best, match = 0.0, None
        for at, grave, their, their_claim in graves.get(slice_key(structure, roots), ()):
            if at < str(born) and grave != fid:
                score = max(jaccard(mine, their) / SAME_IDEA, jaccard(claim, their_claim) / FIRST_IDEA)
                if score > best:
                    best, match = score, grave
        reborn = best >= 1.0
        _add(units, unit_of.get(str(fid)) or mechanism_unit(mechanism), births=1, rebirths=reborn)
        tally = by_origin.setdefault(str(origin), [0, 0])
        tally[0] += 1
        tally[1] += reborn
        if reborn and len(pairs) < 16:
            pairs.append({"family": fid, "unit": unit_of.get(str(fid)), "origin": origin, "structure": structure,
                          "graveyard_row": match, "similarity": round(best, 3),
                          "mechanism": " ".join(str(mechanism).split())[:160]})
    for family, n in db.execute("SELECT family, COUNT(*) FROM runs WHERE window='validation' AND at>=? AND at<? "
                                "GROUP BY family", (lo, hi)):
        _add(units, unit_of.get(str(family), str(family)), validation_runs=n)
    kinds, by_family, _ = _spend(db, since, until)
    for fid, usd in by_family.items():
        _add(units, unit_of.get(str(fid), str(fid)), research_usd=usd)
    for row in units.values():
        row["units"] = 1.0
    return {"units": units, "spend": kinds, "by_origin": {k: {"births": v[0], "rebirths": v[1]} for k, v in by_origin.items()},
            "examples": pairs, "graveyard_rows": sum(len(v) for v in graves.values())}


def _data(db: sqlite3.Connection, root: Path, since: float, until: float) -> dict[str, Any]:
    units: dict[str, dict[str, float]] = {}
    lo, hi = iso(since), iso(until)
    for detail, usd in db.execute("SELECT detail, usd FROM spend WHERE kind='gym_box' AND epoch>=? AND epoch<?", (since, until)):
        try:
            row = json.loads(detail or "{}")
        except ValueError:
            continue
        jobs = _num(row.get("jobs"))
        _add(units, row.get("box") or "unknown", gym_usd=float(usd or 0.0), gym_seconds=_num(row.get("seconds")),
             slots=jobs, batches=1 if jobs else 0)
    failures: dict[str, dict[str, Any]] = {}
    actions: dict[str, int] = {}
    for at, payload in db.execute("SELECT at, payload FROM events WHERE kind='swarm.pool' AND at>=? AND at<?", (lo, hi)):
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        action = str(p.get("action") or "")
        actions[action] = actions.get(action, 0) + 1
        if action == "batch_failed":
            jobs = _num(p.get("jobs"))
            _add(units, p.get("box") or "unknown", slots_failed=jobs, batches_failed=1)
            text = signature(p.get("error"))
            row = failures.setdefault(text, {"signature": text, "n": 0, "slots": 0, "boxes": [], "first_at": at})
            row["n"] += 1
            row["slots"] += jobs
            if p.get("box") not in row["boxes"] and len(row["boxes"]) < 8:
                row["boxes"].append(p.get("box"))
    for row in units.values():
        row["ok_slots"] = max(0.0, row.get("slots", 0.0) - row.get("slots_failed", 0.0))
    runs = {status: n for status, n in db.execute("SELECT status, COUNT(*) FROM runs WHERE at>=? AND at<? GROUP BY status", (lo, hi))}
    nightly = None
    try:
        record = json.loads((root / "data" / "nightly.json").read_text())
        if isinstance(record, dict):
            nightly = {k: record.get(k) for k in ("status", "day", "last_ok", "failures", "pending", "attempts") if k in record}
            nightly["keys"] = sorted(record)[:20]
    except (OSError, ValueError):
        pass
    return {"units": units, "runs": runs, "pool_actions": actions, "nightly": nightly,
            "run_totals": {"runs": float(sum(runs.values())), "error_runs": float(runs.get("error", 0))},
            "examples": sorted(failures.values(), key=lambda r: -r["n"])[:12]}


#: Reject reasons by who caused them. Program: the intent itself was malformed or broke the contract. Feasibility: the
#: account's size or the venue's rules refused a well-formed intent. Harness: the House lacked what it needed (a chain,
#: a quote, fresh state) or lost it (a restart). The rest are unclassified and count only in `rejects`.
REJECT_CLASSES = (
    ("program", re.compile(r"malformed|unknown (?:leg|structure|type|root)|not (?:a|an) (?:intent|structure)|invalid|"
                           r"no such position|missing (?:legs|limit)|TypeError|ValueError|KeyError", re.I)),
    ("feasibility", re.compile(r"buys none|max[_ ]loss|buying power|budget|capital|too (?:wide|many)|cap\b|caps\b|"
                               r"limit (?:is|of) |per (?:day|order)|at most|exceeds|risk", re.I)),
    ("harness", re.compile(r"no (?:chain|quote|quotes|snapshot|market)|stale|not loaded|missing (?:chain|quote|data)|"
                           r"unavailable|timed? ?out|restart|lost|unknown order|not ready|gateway|transport", re.I)),
)


def reject_class(reason: Any) -> str:
    text = str(reason or "")
    for name, pattern in REJECT_CLASSES:
        if pattern.search(text):
            return name
    return "other"


def _execution(root: Path, since: float, until: float) -> dict[str, Any]:
    units: dict[str, dict[str, float]] = {}
    reasons: dict[str, dict[str, Any]] = {}
    practice: dict[str, Any] = {"available": False}
    path = root / "observe.sqlite"
    if path.exists():
        db = connect_ro(path)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "events" in tables:
                practice["available"] = True
                for family, kind, body in db.execute(
                        "SELECT family, kind, CASE WHEN kind='rejected' THEN body END FROM events "
                        "WHERE recorded_at>=? AND recorded_at<? AND kind IN ('intent','rejected','order','fill')",
                        (since, until)):
                    if kind == "intent":
                        _add(units, family, intents=1)
                    elif kind == "order":
                        _add(units, family, orders=1)
                    elif kind == "fill":
                        _add(units, family, fills=1)
                    else:
                        try:
                            reason = (json.loads(body or "{}") or {}).get("reason")
                        except ValueError:
                            reason = None
                        cls = reject_class(reason)
                        _add(units, family, rejects=1, harness_rejects=cls == "harness", program_rejects=cls == "program",
                             feasibility_rejects=cls == "feasibility")
                        text = signature(reason)
                        row = reasons.setdefault(text, {"signature": text, "class": cls, "n": 0, "families": []})
                        row["n"] += 1
                        if family not in row["families"] and len(row["families"]) < 8:
                            row["families"].append(family)
        finally:
            db.close()
    live: dict[str, Any] = {}
    restarts: list[dict[str, Any]] = []
    live_path, ledger_path = root / "live.sqlite", root / "ledger.sqlite"
    events: list[tuple[float, str, str]] = []
    if live_path.exists():
        db = connect_ro(live_path)
        try:
            live["orders"] = {f"{s}": n for s, n in db.execute(
                "SELECT status, COUNT(*) FROM orders WHERE placed_at>=? AND placed_at<? GROUP BY status", (since, until))}
            events = [(float(a), str(k), str(p)) for a, k, p in db.execute(
                "SELECT at, kind, CASE WHEN kind IN ('live.instance','live.error') THEN payload ELSE '' END FROM events "
                "WHERE at>=? AND at<? AND kind IN ('live.instance','live.error') ORDER BY seq", (since, until + 600))]
        finally:
            db.close()
    if ledger_path.exists():
        db = connect_ro(ledger_path)
        try:
            starts = [(epoch_of(at), json.loads(payload).get("release")) for at, payload in db.execute(
                "SELECT at, payload FROM ledger WHERE kind='ops.started' AND at>=? AND at<? ORDER BY seq", (iso(since), iso(until)))]
        finally:
            db.close()
        for began, release in starts:
            if began is None:
                continue
            after = [e for e in events if began <= e[0] < began + 600]
            errors = [e for e in after if e[1] == "live.error"]
            instance_errors = []
            for _, kind, payload in after:
                if kind != "live.instance":
                    continue
                try:
                    p = json.loads(payload)
                except ValueError:
                    continue
                if p.get("error") or "fatal" in str(p.get("state") or "") or "could not" in str(p.get("state") or ""):
                    instance_errors.append(signature(p.get("error") or p.get("state")))
            first = min((e[0] for e in after), default=None)
            failed = bool(errors or instance_errors)
            restarts.append({"at": iso(began), "release": release, "failed": failed, "live_errors": len(errors),
                             "instance_errors": instance_errors[:4],
                             "first_live_event_seconds": None if first is None else round(first - began, 1)})
    live["restarts"] = restarts
    restart_tally = {"restarts": float(len(restarts)), "restart_failures": float(sum(r["failed"] for r in restarts)),
                     "live_errors": float(sum(r["live_errors"] for r in restarts)),
                     "restarts_or_one": float(max(1, len(restarts)))}
    return {"units": units, "practice": practice, "live": live, "restart_totals": restart_tally,
            "examples": sorted(reasons.values(), key=lambda r: -r["n"])[:12]}


def running_source(root: Path, *, now: float) -> dict[str, Any]:
    """The running swarm's release and start from its heartbeat, and the release tree's digest when it can be hashed
    here (`league.watchdog.tree_digest`); the owner's staging step checks the digest against the base commit."""
    source: dict[str, Any] = {}
    try:
        beat = json.loads((Path(root) / "swarm.heartbeat").read_text())
        source = {"release": beat.get("release"), "started_at": beat.get("started_at"), "heartbeat_age": now - float(beat["at"]),
                  "stopped": beat.get("stopped")}
        release = Path(str(beat.get("release") or ""))
        if release.is_dir():
            try:
                from ..watchdog import tree_digest

                source["digest"] = tree_digest(release)[0]
            except Exception as exc:  # noqa: BLE001 - a source without its digest cannot stage a candidate
                source["digest_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        source["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return source


def measure(root: Path, *, now: float | None = None, seconds: int = 6 * 3600, since: float | None = None,
            lanes: Sequence[str] | None = None, examples: int = 40) -> dict[str, Any]:
    """Read-only measurement of every lane over [since, now) (default: the last `seconds`). Opens nothing writable."""
    root = Path(root)
    now = time.time() if now is None else float(now)
    since = now - seconds if since is None else float(since)
    if not 0 < now - since <= 7 * 86400:
        raise ValueError("a measurement window is between one second and seven days")
    wanted = list(lanes or LANES)
    out: dict[str, Any] = {"schema": SCHEMA, "policy": POLICY, "at": now, "since": since, "until": now,
                           "window": {"since": iso(since), "until": iso(now), "seconds": round(now - since, 1)},
                           "source": running_source(root, now=now), "lanes": {}, "errors": {}}
    db = connect_ro(root / "swarm.sqlite")
    try:
        for name in wanted:
            try:
                if name == "research":
                    out["lanes"][name] = _research(db, root, since, now, examples)
                elif name == "memory":
                    out["lanes"][name] = _memory(db, since, now)
                elif name == "data":
                    out["lanes"][name] = _data(db, root, since, now)
                elif name == "execution":
                    out["lanes"][name] = _execution(root, since, now)
            except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
                out["errors"][name] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        db.close()
    try:
        link = root.parent / "current"
        out["current"] = link.resolve().name if link.is_symlink() else None
        rows = []
        for line in (root.parent / "deploys.jsonl").read_text().splitlines()[-400:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append({k: row.get(k) for k in ("at", "deploy", "release", "stage", "ok", "digest", "verdict", "ticks",
                                                     "watch_seconds", "grace", "from", "to")})
        out["deploys"] = rows
    except OSError:
        out["deploys"] = None
    for name, lane in out["lanes"].items():
        lane["metrics"] = lane_metrics(name, lane)
    return out


def lane_tallies(name: str, lane: Mapping[str, Any], exclude: Iterable[str] = ()) -> dict[str, float]:
    skip = set(exclude)
    tally = totals(lane.get("units") or {}, skip)
    if name == "data":
        tally.update({k: float(v) for k, v in (lane.get("run_totals") or {}).items()})
    if name == "execution":
        tally.update({k: float(v) for k, v in (lane.get("restart_totals") or {}).items()})
    if name in ("research", "memory"):
        spend = lane.get("spend") or {}
        tally.setdefault("research_usd", 0.0)
        if not skip:
            # Research spend booked without a family (the architect, the strategist) still counts in the whole population.
            tally["research_usd"] = sum(float(spend.get(k) or 0.0) for k in RESEARCH_KINDS)
    return tally


def lane_metrics(name: str, lane: Mapping[str, Any], exclude: Iterable[str] = ()) -> dict[str, Any]:
    spec = LANES[name]
    tally = lane_tallies(name, lane, exclude)
    out: dict[str, Any] = {"tallies": {k: round(v, 4) for k, v in sorted(tally.items())}}
    for metric in [b.metric for b in spec.bottlenecks] + [m for b in spec.bottlenecks for m in b.secondary] + list(spec.guards):
        value = metric.value(tally)
        out[metric.name] = None if value is None else round(value, 6)
    return out


# ------------------------------------------------------------------------------------------------ ranking
def _gym_usd_per_second(measurement: Mapping[str, Any]) -> float | None:
    units = ((measurement.get("lanes") or {}).get("data") or {}).get("units") or {}
    tally = totals(units)
    return tally["gym_usd"] / tally["gym_seconds"] if tally.get("gym_seconds") else None


def rank(measurement: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Bottlenecks over their capture thresholds, most money at stake per day first (execution: severity first)."""
    window_days = max(1e-9, float(measurement["until"]) - float(measurement["since"])) / 86400.0
    usd_per_gym_second = _gym_usd_per_second(measurement)
    data_units = ((measurement.get("lanes") or {}).get("data") or {}).get("units")
    gym_usd = totals(data_units).get("gym_usd") if data_units is not None else None
    out = []
    for name, lane in (measurement.get("lanes") or {}).items():
        spec = LANES[name]
        tally = lane_tallies(name, lane)
        for b in spec.bottlenecks:
            value = b.metric.value(tally)
            denominator = tally.get(b.metric.denominator, 0.0)
            over = b.metric.bad(value) and denominator >= b.metric.min_units
            stake: dict[str, Any] = {"basis": None, "usd_per_day": None}
            if name == "research":
                wasted, seconds = tally.get("wasted_gym_seconds", 0.0), tally.get("gym_seconds", 0.0)
                # Cycle Gym seconds count each program's batch wall time (a batch runs several programs on one box), so
                # the box dollars are shared by the wasted fraction of cycle Gym seconds, plus the wasted cycles' model $.
                box = gym_usd * wasted / seconds if seconds and gym_usd is not None else None
                usd = None if box is None else box + tally.get("wasted_model_usd", 0.0)
                stake = {"basis": "the wasted share of cycle Gym seconds x the window's Gym box $, plus the model $ of the "
                                  "cycles whose run was disqualified, refused or erred",
                         "wasted_gym_seconds_per_day": round(wasted / window_days, 1),
                         "wasted_model_usd_per_day": round(tally.get("wasted_model_usd", 0.0) / window_days, 2),
                         "usd_per_day": None if usd is None else round(usd / window_days, 2)}
            elif name == "memory" and b.metric.name == "validation_attempts_per_usd":
                usd = tally.get("research_usd", 0.0)
                stake = {"basis": "research $ per day: the dollars whose evidence yield this bottleneck is about; at the "
                                  "predeclared effect the same validation attempts cost min_effect / (1 + min_effect) less",
                         "usd_per_day": round(usd / window_days, 2),
                         "validation_attempts_per_day": round(tally.get("validation_runs", 0.0) / window_days, 1)}
            elif name == "memory":
                usd = tally.get("research_usd", 0.0)
                births = tally.get("births", 0.0)
                per_birth = usd / births if births else None
                stake = {"basis": "reborn families x research $ per family born in the window (an upper bound: the spend "
                                  "of the window over its births)",
                         "rebirths_per_day": round(tally.get("rebirths", 0.0) / window_days, 1),
                         "usd_per_day": None if per_birth is None else round(tally.get("rebirths", 0.0) * per_birth / window_days, 2)}
            elif name == "data":
                slots, failed = tally.get("slots", 0.0), tally.get("slots_failed", 0.0)
                secs = tally.get("gym_seconds", 0.0)
                usd = (failed * secs / slots * usd_per_gym_second) if slots and usd_per_gym_second else None
                stake = {"basis": "failed job slots x measured box-seconds per slot x $ per box-second (the rerun)",
                         "failed_slots_per_day": round(failed / window_days, 1),
                         "usd_per_day": None if usd is None else round(usd / window_days, 2)}
            elif name == "execution":
                stake = {"basis": "not priced: execution failures risk real orders and evidence; ranked by severity"}
            if stake.get("usd_per_day") is not None:
                share = (b.metric.min_effect / (1.0 + b.metric.min_effect) if b.metric.direction == "higher"
                         else b.metric.min_effect)
                stake["usd_per_day_at_effect"] = round(stake["usd_per_day"] * share, 2)
            out.append({"lane": name, "metric": b.metric.name, "value": None if value is None else round(value, 6),
                        "denominator": denominator, "threshold": b.metric.threshold, "min_units": b.metric.min_units,
                        "captured": bool(over), "severity": b.severity, "summary": b.summary, "stake": stake,
                        "secondary": {m.name: m.value(tally) for m in b.secondary},
                        "min_effect": b.metric.min_effect, "direction": b.metric.direction,
                        "offline": b.judge_mode, "release_classes": list(spec.release_classes),
                        "examples": (lane.get("examples") or [])[:8],
                        "why_not": None if over else ("no data" if value is None else
                                                      f"{b.metric.name} {value:.4f} not past {b.metric.threshold} "
                                                      f"({b.metric.direction} is better) or denominator "
                                                      f"{denominator:.0f} below {b.metric.min_units}")})
    # Captured first; among them the ones whose fixed judge can show the improvement offline (cheap evidence before a
    # canary), then the dollars a day the predeclared effect is worth; execution (unpriced: real orders and evidence
    # are at risk) by severity ahead of the priced ones.
    weight = {"critical": 3, "high": 2, "medium": 1}
    out.sort(key=lambda r: (not r["captured"], r["offline"] != "improve",
                            -1e9 * weight.get(r["severity"], 1) if r["lane"] == "execution" else
                            -(r["stake"].get("usd_per_day_at_effect") or 0.0), r["lane"], r["metric"]))
    for n, row in enumerate(out, 1):
        row["rank"] = n
    return out


def motivating_units(lane: str, measurement_lane: Mapping[str, Any]) -> list[str]:
    """The units a brief shows its patch author: every unit named by an example. The retention comparison excludes them."""
    found: list[str] = []
    for row in measurement_lane.get("examples") or []:
        for key in ("families", "boxes"):
            found.extend(str(u) for u in row.get(key) or [])
        for key in ("family", "unit"):
            if row.get(key):
                found.append(str(row[key]))
        if row.get("graveyard_row"):
            found.append(str(row["graveyard_row"]))
    return sorted(set(found))


# ------------------------------------------------------------------------------------------------ held-out and arms
def heldout_seed(secret: str, key: str, head: str) -> str:
    """The held-out split's seed: unknowable before the candidate commit exists, and never shown to its author."""
    return hashlib.sha256(f"{secret}\0{key}\0{head}".encode()).hexdigest()[:16]


def split_arms(units: Mapping[str, Mapping[str, float]], *, key: str, salt: str, fraction: float,
               exclude: Iterable[str] = ()) -> tuple[dict[str, Mapping[str, float]], dict[str, Mapping[str, float]]]:
    from .canary import in_arm

    skip = set(exclude)
    canary, control = {}, {}
    for unit, row in units.items():
        if unit in skip:
            continue
        (canary if in_arm(salt, key, unit, fraction) else control)[unit] = row
    return canary, control


def _ratio(rows: Sequence[Mapping[str, float]], metric: Metric) -> float | None:
    num = sum(float(r.get(metric.numerator) or 0.0) for r in rows)
    den = sum(float(r.get(metric.denominator) or 0.0) for r in rows)
    return num / den if den > 0 else None


def compare(metric: Metric, treated: Mapping[str, Mapping[str, float]], control: Mapping[str, Mapping[str, float]], *,
            seed: str, resamples: int = 2000, extra_treated: Mapping[str, float] | None = None,
            extra_control: Mapping[str, float] | None = None) -> dict[str, Any]:
    """The metric in each group (a ratio of sums over units) and a one-sided cluster-bootstrap p-value that the treated
    group is better. Units are resampled whole, so correlated rows of one family count once. `extra_*` are group-level
    tallies with no unit split (e.g. restarts)."""
    def has(row: Mapping[str, float]) -> bool:
        return metric.numerator in row or metric.denominator in row

    # Only rows that carry the metric's fields resample: a unit without them adds nothing to either sum, and a group
    # tally (`extra_*`) joins only the metrics it holds.
    a = [r for r in treated.values() if has(r)] + ([extra_treated] if extra_treated and has(extra_treated) else [])
    b = [r for r in control.values() if has(r)] + ([extra_control] if extra_control and has(extra_control) else [])
    va, vb = _ratio(a, metric), _ratio(b, metric)
    out: dict[str, Any] = {"metric": metric.name, "treated": va, "control": vb, "direction": metric.direction,
                           "treated_denominator": sum(float(r.get(metric.denominator) or 0.0) for r in a),
                           "control_denominator": sum(float(r.get(metric.denominator) or 0.0) for r in b),
                           "units": [len(treated), len(control)]}
    if va is None or vb is None:
        out.update(relative=None, p_value=None)
        return out
    sign = 1.0 if metric.direction == "lower" else -1.0
    out["relative"] = (vb - va) * sign / abs(vb) if vb else (0.0 if va == vb else None)
    if len(a) < 2 or len(b) < 2:
        # Too few units to resample (a House-wide count such as restarts): an exact one-sided test on the pooled counts
        # when they are counts of events among trials, else no inference.
        num = [sum(float(r.get(metric.numerator) or 0.0) for r in g) for g in (a, b)]
        den = [sum(float(r.get(metric.denominator) or 0.0) for r in g) for g in (a, b)]
        if all(float(x).is_integer() for x in num + den) and all(0 <= n <= d for n, d in zip(num, den)):
            k1, n1, k2, n2 = (int(x) for x in (num[0], den[0], num[1], den[1]))
            out["p_value"] = fisher_less(k1, n1, k2, n2) if metric.direction == "lower" else fisher_less(n1 - k1, n1, n2 - k2, n2)
            out["test"] = "fisher_exact_one_sided"
        else:
            out["p_value"] = None
        return out
    out["test"] = "cluster_bootstrap_one_sided"
    rng = random.Random(int(hashlib.sha256(f"{seed}:{metric.name}".encode()).hexdigest()[:12], 16))
    worse = draws = 0
    if a and b:
        for _ in range(resamples):
            ra = _ratio([a[rng.randrange(len(a))] for _ in a], metric)
            rb = _ratio([b[rng.randrange(len(b))] for _ in b], metric)
            if ra is None or rb is None:
                continue
            draws += 1
            worse += (rb - ra) * sign <= 0
    out["p_value"] = (worse + 1) / (draws + 1) if draws else None
    return out


def fisher_less(k1: int, n1: int, k2: int, n2: int) -> float:
    """One-sided Fisher exact p-value that group 1's event rate (k1 of n1) is below group 2's (k2 of n2): the
    hypergeometric probability of k1 or fewer events in group 1 given the pooled total."""
    total, events = n1 + n2, k1 + k2
    if n1 <= 0 or n2 <= 0:
        return 1.0
    denominator = math.comb(total, events)
    low = max(0, events - n2)
    return min(1.0, sum(math.comb(n1, x) * math.comb(n2, events - x) for x in range(low, k1 + 1)) / denominator)


def judge_verdict(lane: Lane, bottleneck: Bottleneck, trees: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The offline decision from both trees' judge runs (dev and heldout) and regressions: the fixed benchmark and the
    regression comparison, quality (safety counts at 0, protected counts not rising) and cost."""
    reasons: list[str] = []
    base, head = trees["base"], trees["head"]
    if (base.get("regressions") or {}).get("exit") != 0:
        reasons.append("the baseline fails its own fixed regressions: the comparison is void")
    if (head.get("regressions") or {}).get("exit") != 0:
        reasons.append("the candidate fails the fixed regressions")
    primary = bottleneck.judge_primary
    for split in ("dev", "heldout"):
        a = ((base.get("splits") or {}).get(split) or {}).get("metrics")
        b = ((head.get("splits") or {}).get(split) or {}).get("metrics")
        if not isinstance(a, Mapping) or not isinstance(b, Mapping):
            reasons.append(f"{split}: a judge run gave no valid answer")
            continue
        for name in lane.judge_zero:
            if b.get(name) != 0:
                reasons.append(f"{split}: {name} is {b.get(name)}; it must be 0")
        for name in lane.judge_no_worse + (primary,):
            if not isinstance(b.get(name), (int, float)) or not isinstance(a.get(name), (int, float)) or b[name] > a[name]:
                reasons.append(f"{split}: {name} rose from {a.get(name)} to {b.get(name)}")
        cost_a, cost_b = a.get(lane.judge_cost), b.get(lane.judge_cost)
        if not isinstance(cost_a, (int, float)) or not isinstance(cost_b, (int, float)):
            reasons.append(f"{split}: the cost {lane.judge_cost} is missing")
        elif lane.judge_cost_rule == "pays":
            saved = max(0.0, float(a.get(primary) or 0) - float(b.get(primary) or 0))
            if cost_b - cost_a > max(COST_FLOOR, PAYS_SHARE * saved):
                reasons.append(f"{split}: {lane.judge_cost} rose {cost_a} -> {cost_b}, more than {PAYS_SHARE:.0%} of the "
                               f"{saved} {primary} it saved")
        elif cost_b > max(COST_FLOOR, COST_RATIO * cost_a):
            reasons.append(f"{split}: {lane.judge_cost} rose {cost_a} -> {cost_b} (at most {COST_RATIO}x or {COST_FLOOR})")
    if bottleneck.judge_mode == "improve":
        a = (((base.get("splits") or {}).get("heldout") or {}).get("metrics") or {}).get(primary)
        b = (((head.get("splits") or {}).get("heldout") or {}).get("metrics") or {}).get(primary)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            pass  # reported above
        elif a <= 0:
            reasons.append(f"heldout: the baseline's {primary} is already 0; the benchmark cannot show an improvement")
        elif b > (1.0 - bottleneck.judge_effect) * a:
            reasons.append(f"heldout: {primary} {a} -> {b}, less than the predeclared {bottleneck.judge_effect:.0%} fall")
    return {"passed": not reasons, "reasons": reasons, "mode": bottleneck.judge_mode, "primary": primary,
            "effect": bottleneck.judge_effect, "cost_rule": lane.judge_cost_rule}


def retention(lane: Lane, bottleneck: Bottleneck, treated: Mapping[str, Mapping[str, float]],
              control: Mapping[str, Mapping[str, float]], *, seed: str, extra_treated: Mapping[str, float] | None = None,
              extra_control: Mapping[str, float] | None = None, alpha: float = 0.05) -> dict[str, Any]:
    """The registered decision: the primary metric better by at least `min_effect` with p <= alpha and enough
    denominator in each group; every secondary and guard metric (quality and cost) no worse than its tolerance."""
    min_units = int(lane.canary_for(bottleneck).get("min_units_per_arm", 1))
    primary = compare(bottleneck.metric, treated, control, seed=seed, extra_treated=extra_treated, extra_control=extra_control)

    def clusters(units: Mapping[str, Any], extra: Mapping[str, float] | None) -> float:
        # Units resample as clusters; a House-wide count (restarts) is its own count of events.
        return float(len(units)) if units else float((extra or {}).get(bottleneck.metric.denominator) or 0.0)

    # Enough clusters in each group, and each group's denominator at the capture's own minimum.
    enough = (clusters(treated, extra_treated) >= min_units and clusters(control, extra_control) >= min_units
              and primary["treated_denominator"] >= max(1, bottleneck.metric.min_units)
              and primary["control_denominator"] >= max(1, bottleneck.metric.min_units))
    improved = (enough and primary["relative"] is not None and primary["relative"] >= bottleneck.metric.min_effect
                and primary["p_value"] is not None and primary["p_value"] <= alpha)
    checks = []
    for metric in list(bottleneck.secondary) + list(lane.guards):
        row = compare(metric, treated, control, seed=seed, extra_treated=extra_treated, extra_control=extra_control)
        # A guard fails when it worsens by more than its tolerance (relative, or absolute when `abs_tolerance` is set);
        # an unmeasurable guard does not block by itself, but the decision records it.
        sign = 1.0 if metric.direction == "lower" else -1.0
        worse = None if row["treated"] is None or row["control"] is None else (row["treated"] - row["control"]) * sign
        # A zero control makes the relative change undefined: then only the absolute tolerance can pass it (a guard that
        # goes from no errors to some errors fails). Unmeasured on either side passes, and the decision records it.
        row["ok"] = ((row["relative"] is not None and row["relative"] >= -metric.min_effect)
                     or (worse is not None and worse <= metric.abs_tolerance) or worse is None)
        checks.append(row)
    decision = ("insufficient_activity" if not enough else
                "retained" if improved and all(c["ok"] for c in checks) else "revert_recommended")
    return {"decision": decision, "primary": primary, "checks": checks, "alpha": alpha, "min_units_per_arm": min_units,
            "min_effect": bottleneck.metric.min_effect}


__all__ = ["LANES", "Lane", "Metric", "Bottleneck", "PROTECTED", "protected_reason", "classify", "live_path_modules",
           "content_guard", "surface_check", "measure", "rank", "lane_metrics", "motivating_units", "heldout_seed",
           "split_arms", "compare", "retention", "judge_verdict", "fisher_less", "signature", "words", "jaccard", "same_idea",
           "slice_key", "reject_class", "lane_sha", "DEPLOY_RULES", "COST_RATIO", "COST_FLOOR", "PAYS_SHARE"]
