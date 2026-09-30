"""Persistent, evidence-led harness changes, using the existing hash-chained repair worklist.

The first registered lane is scheduler efficiency. The optimizer supplies a committed patch; this controller freezes
its baseline, runs both trees against an external fixed judge in a credential-free network namespace, and follows
the existing watchdog's exact-tree canary receipts. Retention additionally needs subsequent operational evidence.
It never edits a running release, places an order, opens a PR, funds a service, or deploys/rolls back production.
Those legs remain with the authorized operator/agent and the existing deployment watchdog.

Four more lanes (research workflow, prompts/memory, data processing, execution reliability) run the same loop with
their own predeclared metrics, surfaces, fixed judges and canaries (`league/swarm/harness_lanes.py`): a read-only House
measurement ranks their bottlenecks (`capture_lanes`), a candidate is staged only inside its lane's surface and never on
a protected path, the judge scores base and candidate on a fixed dev split and a held-out split seeded only after the
candidate is committed, the canary gates the change to a deterministic fraction of units (`league/swarm/canary.py`) and
the registered observation window compares the canary arm with the concurrent control arm, motivating units excluded.
A failed comparison flips the gate back (the old behavior at the next read); a supported one retains it.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import resource
import secrets
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Mapping

from ..ledger import Ledger
from ..watchdog import tree_digest
from ..worklist import Worklist
from . import harness_lanes as lanes

REPO = Path(__file__).resolve().parents[2]
BENCHMARK = Path(__file__).with_name("improvement_benchmark.py")
POLICY = "harness-improvement-1"
MIN_CYCLES = 20
OBSERVE_SECONDS = 900
REGRESSIONS = ("league.tests.test_swarm_loop", "league.tests.test_swarm_holds", "league.tests.test_swarm_store",
               "league.tests.test_swarm_retirement", "league.tests.test_swarm_event_waits")
# All files other than SCHEDULER_PATH, including tests, prompts, settings/budgets, evaluator/benchmark definitions,
# data access, live capital and this controller, are protected. Only Scheduler's body may differ within that file.
SCHEDULER_PATH = "league/swarm/loop.py"
#: The lanes' fixed judges: the whole directory is pinned by hash at staging and copied out of the reviewed release.
JUDGES = Path(__file__).with_name("harness_judges")
#: The operational comparison's significance level (one-sided cluster bootstrap), for every lane.
ALPHA = 0.05


class ImprovementError(ValueError):
    pass


def sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def iso(epoch: float) -> str:
    # Match SwarmStore's second-resolution timestamps for SQL text comparisons.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def git(repo: Path, *args: str, binary: bool = False) -> Any:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        raise ImprovementError(f"git {args[0]}: {result.stderr.decode(errors='replace')[-600:]}")
    return result.stdout if binary else result.stdout.decode().strip()


def snapshot(swarm: Path, *, since: float, until: float) -> dict[str, Any]:
    """Read operational cycle counts only. No strategies, quotes, validation numbers or sealed data are loaded."""
    path = Path(swarm) / "swarm.sqlite"
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        # Project only operational fields inside SQLite. The full cycle can also contain free text and Train scores;
        # neither is allowed into the optimizer's evidence. Reduce refusal/error text to booleans as well.
        rows = db.execute("""SELECT seq,at,family,json_object(
                'model_calls',json_extract(payload,'$.model_calls'), 'hold',json_extract(payload,'$.hold'),
                'trials',json_extract(payload,'$.trials'), 'pending_run',json_extract(payload,'$.pending_run'),
                'error',COALESCE(json_extract(payload,'$.error'),'') NOT IN ('',0),
                'run_refused',COALESCE(json_extract(payload,'$.run_refused'),'') NOT IN ('',0),
                'cost_usd',json_extract(payload,'$.cost_usd'))
                FROM events WHERE kind='swarm.cycle' AND json_valid(payload) AND at>=? AND at<? ORDER BY seq""",
                          (iso(since), iso(until))).fetchall()
    finally:
        db.close()
    out: dict[str, Any] = {"since": iso(since), "until": iso(until), "seconds": until - since, "cycles": 0,
                          "hold_calls": 0, "errors": 0, "refused_cycles": 0, "new_trials": 0, "model_calls": 0,
                          "model_usd": 0.0, "through_seq": rows[-1][0] if rows else 0, "examples": []}
    def count(raw):
        return max(0, int(raw)) if isinstance(raw, (int, float)) and math.isfinite(raw) else 0

    for seq, at, family, payload in rows:
        try:
            row = json.loads(payload)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        out["cycles"] += 1
        calls = count(row.get("model_calls"))
        trials = count(row.get("trials"))
        held = bool(row.get("hold")) and not trials and not row.get("pending_run")
        out["hold_calls"] += calls if held else 0
        out["model_calls"] += calls
        out["errors"] += bool(row.get("error"))
        out["refused_cycles"] += bool(row.get("run_refused"))
        out["new_trials"] += trials
        cost = row.get("cost_usd")
        if isinstance(cost, (float, int)) and math.isfinite(cost) and cost > 0:
            out["model_usd"] += float(cost)
        if held and calls and len(out["examples"]) < 8:
            out["examples"].append({"seq": seq, "at": at, "agent": family or "swarm", "excerpt": "paid hold without a new trial or queued run"})
    out["hold_call_share"] = out["hold_calls"] / max(1, out["model_calls"])
    out["model_usd"] = round(out["model_usd"], 6)
    out["trials_per_model_usd"] = out["new_trials"] / out["model_usd"] if out["model_usd"] else None
    return out


def patch_guard(before: str, after: str) -> None:
    """The registered scheduler lane cannot change imports, module code, or any other class/function."""
    def split(source: str):
        tree = ast.parse(source)
        scheduler = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Scheduler"]
        if len(scheduler) != 1:
            raise ImprovementError("exactly one Scheduler class is required")
        return scheduler[0], ast.dump(ast.Module(body=[node for node in tree.body if node is not scheduler[0]], type_ignores=[]))
    old, protected = split(before)
    new, found = split(after)
    if protected != found or [ast.dump(n) for n in old.bases + old.decorator_list + old.keywords] != [
            ast.dump(n) for n in new.bases + new.decorator_list + new.keywords]:
        raise ImprovementError("only Scheduler's body may change; imports and all other definitions are protected")
    old_imports = sorted(ast.dump(n) for n in ast.walk(old) if isinstance(n, (ast.Import, ast.ImportFrom)))
    new_imports = sorted(ast.dump(n) for n in ast.walk(new) if isinstance(n, (ast.Import, ast.ImportFrom)))
    if old_imports != new_imports:
        raise ImprovementError("candidate may not add or change Scheduler imports")
    dangerous = {"eval", "exec", "compile", "open", "__import__", "globals", "locals", "vars", "_getframe",
                 "getattr", "setattr", "delattr"}
    def calls(node):
        return {n.func.id if isinstance(n.func, ast.Name) else n.func.attr for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))}
    if (calls(new) - calls(old)) & dangerous:
        raise ImprovementError("candidate introduces reflective code execution or file access")
    if any(isinstance(node, (ast.Global, ast.Nonlocal)) or isinstance(node, ast.Attribute) and node.attr.startswith("__")
           for node in ast.walk(new)):
        raise ImprovementError("global mutation and reflective attribute access are outside the scheduler lane")
    def store_member(node):
        return (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name) and node.value.value.id == "self" and node.value.attr == "store")
    def capabilities(node):
        return {n.attr for n in ast.walk(node) if store_member(n)}
    if capabilities(new) - capabilities(old):
        raise ImprovementError("candidate introduces a new persistent-store capability")
    def state_fields(node):
        return {kw.arg for n in ast.walk(node) if isinstance(n, ast.Call) and store_member(n.func)
                and n.func.attr == "set_state" for kw in n.keywords}
    if None in state_fields(new) or state_fields(new) - state_fields(old):
        raise ImprovementError("candidate may not acquire writes to new persistent state fields")


def running_evidence(swarm: Path, release: Path | None, *, now: float) -> dict:
    """Bind a measured cohort to the actual fresh heartbeat and the bytes of its release."""
    try:
        heartbeat = json.loads((Path(swarm) / "swarm.heartbeat").read_text())
        reported = Path(heartbeat["release"])
        selected = Path(release) if release is not None else reported
        if not 0 <= now - float(heartbeat["at"]) <= 180:
            raise ImprovementError("a fresh running swarm heartbeat is required")
        if heartbeat.get("stopped") or not selected.is_dir() or selected.resolve() != reported.resolve():
            raise ImprovementError("the measured release must match the running swarm heartbeat")
        started = float(heartbeat["started_at"])
        if not math.isfinite(started) or started > now:
            raise ImprovementError("invalid swarm start time")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ImprovementError(f"cannot bind operational evidence to a running release: {exc}") from exc
    return {"release": str(selected.resolve()), "started_at": started, "digest": tree_digest(selected)[0]}


def judges_sha() -> str:
    return sha([[p.name, sha(p.read_bytes())] for p in sorted(JUDGES.glob("*.py"))])


def watchdog(rows: list[dict], digest: str) -> dict:
    """The watchdog's receipts for the exact evaluated tree `digest`, from deploys.jsonl rows (the module docstring)."""
    stages = [r for r in rows if r.get("stage") == "stage" and r.get("ok") is True and r.get("digest") == digest]
    if not stages:
        return {"waiting": "no watchdog stage receipt for the exact evaluated tree"}
    stage = stages[-1]
    attempt = [r for r in rows if r.get("deploy") == stage.get("deploy")]
    final = next((r for r in reversed(attempt) if r.get("stage") == "verdict"), None)
    rollback = any(r.get("stage") == "rollback" and r.get("ok") is True and r.get("from") == stage.get("release") for r in rows)
    canary = next((r for r in attempt if r.get("stage") == "canary" and r.get("ok") is True and int(r.get("ticks") or 0) >= 3), None)
    start = next((r for r in attempt if r.get("stage") == "start"), {})
    watches = [r for r in attempt if r.get("stage") == "watch" and not r.get("grace")]
    complete = bool(final and final.get("verdict") == "promoted" and canary and int(start.get("watch_seconds") or 0) >= 600
                    and watches and all(r.get("ok") for r in watches))
    return {"stage": stage, "attempt": attempt, "final": final, "rollback": rollback, "complete": complete}


def archive(repo: Path, head: str, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    raw = git(repo, "archive", "--format=tar", head, binary=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as bundle:
        for member in bundle.getmembers():
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts or not (member.isfile() or member.isdir()):
                raise ImprovementError("candidate archive contains a link or non-file entry")
        bundle.extractall(target, filter="data")


def release_digest(root: Path) -> str:
    """Use the owner's actual upload selection and watchdog hash, including upload-normalized executable modes."""
    from scripts.floor_box import UPLOAD_TREES, SKIP_DIRS, SKIP_SUFFIXES, SKIP_NAMES, is_secret
    with tempfile.TemporaryDirectory(prefix="harness-release-") as temp:
        release = Path(temp)
        for tree in UPLOAD_TREES:
            for source in sorted((root / tree).rglob("*")):
                relative = source.relative_to(root)
                if not source.is_file() or source.is_symlink() or SKIP_DIRS & set(relative.parts):
                    continue
                if relative.suffix in SKIP_SUFFIXES or relative.name in SKIP_NAMES or relative.name.startswith("."):
                    continue
                if is_secret(relative):
                    raise ImprovementError("credential path in candidate release")
                target = release / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                target.chmod(0o755 if relative.suffix == ".sh" else 0o644)
        return tree_digest(release)[0]


def sandbox(tree: Path, judge: Path, command: list[str], *, python: Path, timeout: int = 600) -> dict:
    """No host home, credentials, production state or network. Refuse when namespace isolation is unavailable."""
    if not shutil.which("bwrap"):
        raise ImprovementError("bwrap is required; evaluation never falls back to unsandboxed execution")
    python = python.absolute()
    argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv"]
    for path in ("/usr", "/lib", "/lib64"):
        if Path(path).exists():
            argv += ["--ro-bind", path, path]
    interpreter = "/usr/bin/python3"
    venv = python.parent.parent
    if (venv / "pyvenv.cfg").exists():
        argv += ["--ro-bind", str(venv), "/venv"]
        interpreter = "/venv/bin/python"
    elif python.resolve().parent != Path("/usr/bin"):
        raise ImprovementError("use /usr/bin/python3 or an isolated virtual environment")
    argv += ["--ro-bind", str(tree), "/work", "--ro-bind", str(judge), "/judge", "--tmpfs", "/tmp",
             "--proc", "/proc", "--dev", "/dev", "--chdir", "/work", "--setenv", "PYTHONPATH", "/work",
             "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "OPENBLAS_NUM_THREADS", "1",
             "--setenv", "OMP_NUM_THREADS", "1", "--setenv", "PATH", "/usr/bin:/bin", "--", interpreter, *command]
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 ** 3, 2 * 1024 ** 3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 ** 2, 32 * 1024 ** 2))

    def tail(handle, size):
        handle.seek(max(0, handle.seek(0, 2) - size))
        return handle.read().decode(errors="replace")

    began = time.monotonic()
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_before = usage.ru_utime + usage.ru_stime
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True, preexec_fn=limits)
        problem = None
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            problem = "sandbox timeout"
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return {"exit": process.returncode, "seconds": round(time.monotonic() - began, 6),
                "cpu_seconds": round(usage.ru_utime + usage.ru_stime - cpu_before, 6), "error": problem,
                "stdout": tail(out, 16000), "stderr": tail(err, 4000)}


class HarnessImprovement:
    def __init__(self, root: Path, *, repo: Path = REPO, clock=time.time):
        self.root, self.repo, self.clock = Path(root), Path(repo), clock
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.ledger = Ledger(self.root / "harness.sqlite", clock=clock)
        self.worklist = Worklist(self.ledger, clock=clock)

    def close(self):
        self.ledger.close()

    def capture(self, swarm: Path, *, base: str, seconds: int = 3600, release: Path | None = None) -> list[str]:
        # The deployed release need not contain .git. The owner's evaluation step resolves this immutable SHA and
        # checks its archived release digest against the actual measured bytes before admitting any candidate.
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise ImprovementError("base must be the full reviewed Git commit SHA")
        if not 900 <= seconds <= 86400:
            raise ImprovementError("the measurement window must be between 900 and 86400 seconds")
        now = self.clock()
        source = running_evidence(swarm, release, now=now)
        # After a retained change, the next generation starts from that exact measured tree. An unrelated release
        # still needs its reviewed SHA supplied by the operator; no guessed mapping from a release name to code.
        for job in self.worklist.jobs().values():
            proposal = job.carry.get("_proposal") or {}
            if job.state == "verified" and proposal.get("release_digest") == source["digest"]:
                base = proposal["head"]
        current = snapshot(swarm, since=max(now - seconds, source["started_at"]), until=now)
        if current["cycles"] < MIN_CYCLES or current["hold_call_share"] < 0.25:
            return []
        key = "harness:scheduler:" + base[:16]
        old = self.worklist.get(key)
        if old is not None and (old.through.get("research", 0) >= current["through_seq"] or old.state not in ("proposed", "admitted")):
            return [key]  # unchanged evidence and in-flight/rejected candidates do not buy a new optimization attempt
        self.worklist.report(key=key, kind="shared_defect", summary="Paid research cycles repeatedly hold without producing a new trial or queued run.",
                             evidence=current["examples"], agents=[r["agent"] for r in current["examples"]], source="research",
                             severity="high", through_seq=current["through_seq"], details={"base": base, "baseline": current,
                                 "source": source, "policy": POLICY})
        return [key]

    def prepare(self, key: str, destination: Path) -> dict:
        """Open the patch-writing leg in a detached worktree; a separate authorized agent authors the patch."""
        job = self.worklist.get(key)
        if job is None or job.state not in ("proposed", "admitted"):
            raise ImprovementError("an unassigned measured bottleneck is required")
        destination = Path(destination).resolve()
        if destination.exists():
            raise ImprovementError("the isolated worktree destination must not already exist")
        git(self.repo, "worktree", "add", "--detach", str(destination), str(job.details["base"]))
        proposal = {"base": job.details["base"], "worktree": str(destination)}
        if job.details.get("lane"):
            proposal["brief"] = self.brief(key)
        self.worklist.transition(key, "patching", note="Isolated worktree ready for an authorized patch author; no model call or deployment was made.",
                                 attempt=job.attempt, extra={"_proposal": proposal})
        return proposal

    def stage(self, key: str, candidate: str) -> dict:
        job = self.worklist.get(key)
        if job is None or job.state not in ("proposed", "admitted", "patching", "revising"):
            raise ImprovementError("candidate needs an open measured bottleneck")
        if job.details.get("lane"):
            return self._stage_lane(job, candidate)
        base = str(job.details["base"])
        head = None
        attempt = job.attempt + 1
        try:
            git(self.repo, "rev-parse", "--verify", f"{base}^{{commit}}")
            head = git(self.repo, "rev-parse", "--verify", f"{candidate}^{{commit}}")
            git(self.repo, "merge-base", "--is-ancestor", base, head)
            paths = git(self.repo, "diff", "--name-only", base, head).splitlines()
            if paths != [SCHEDULER_PATH]:
                raise ImprovementError("scheduler lane may change only league/swarm/loop.py; every other path is protected")
            patch_guard(git(self.repo, "show", f"{base}:{SCHEDULER_PATH}"), git(self.repo, "show", f"{head}:{SCHEDULER_PATH}"))
            with tempfile.TemporaryDirectory(prefix="harness-baseline-") as temp:
                tree = Path(temp) / "base"
                archive(self.repo, base, tree)
                if release_digest(tree) != job.details["source"]["digest"]:
                    raise ImprovementError("baseline commit does not match the measured running release")
        except (ImprovementError, SyntaxError, OSError) as exc:
            self.worklist.transition(key, "revising", attempt=attempt, commit=head, note=f"Candidate preflight refused: {exc}",
                                     extra={"_failure": {"phase": "stage", "candidate": head or str(candidate)[:100],
                                                         "base": base, "reason": str(exc)[:1000]}})
            raise ImprovementError(str(exc)) from exc
        artifact = self.root / "candidates" / sha([key, head])[:20]
        artifact.mkdir(parents=True, exist_ok=True)
        patch = git(self.repo, "diff", "--binary", base, head, binary=True)
        (artifact / "candidate.patch").write_bytes(patch)
        proposal = {"base": base, "head": head, "artifact": str(artifact.resolve()), "patch_sha": sha(patch), "policy": POLICY,
                    "baseline": job.details["baseline"], "source": job.details["source"], "judge_sha": sha(BENCHMARK.read_bytes()),
                    "regressions": list(REGRESSIONS), "observation_seconds": OBSERVE_SECONDS}
        self.worklist.transition(key, "testing", commit=head, attempt=attempt, note="Patch pinned; protected paths unchanged. Isolated evaluation is owed.",
                                 extra={"_proposal": proposal})
        return proposal

    def evaluate(self, key: str, *, python: Path) -> dict:
        job = self.worklist.get(key)
        if job is None or job.state != "testing":
            raise ImprovementError("candidate is not awaiting evaluation")
        if job.details.get("lane"):
            return self._evaluate_lane(job, python=python)
        proposal = dict(job.carry["_proposal"])
        if (proposal["judge_sha"] != sha(BENCHMARK.read_bytes()) or proposal["policy"] != POLICY
                or proposal["regressions"] != list(REGRESSIONS)):
            raise ImprovementError("the frozen judge changed; register a new candidate under the new protocol")
        artifact = Path(proposal["artifact"])
        judge = artifact / "judge"
        judge.mkdir(exist_ok=True)
        (judge / "benchmark.py").write_bytes(BENCHMARK.read_bytes())
        receipt = {"policy": POLICY, "judge_sha": proposal["judge_sha"], "base": proposal["base"], "head": proposal["head"], "trees": {}}
        with tempfile.TemporaryDirectory(prefix="harness-eval-") as temp:
            for name in ("base", "head"):
                tree = Path(temp) / name
                archive(self.repo, proposal[name], tree)
                results = sandbox(tree, judge, ["/judge/benchmark.py"], python=python)
                tests = sandbox(tree, judge, ["-m", "unittest", *proposal["regressions"], "-q"], python=python)
                try:
                    metrics = json.loads(results["stdout"].splitlines()[-1]) if results["exit"] == 0 else None
                except (ValueError, IndexError):
                    metrics = None
                required = ("quality", "idle_model_turns", "sqlite_statements", "cpu_seconds", "provider_calls")
                if not isinstance(metrics, dict) or any(not isinstance(metrics.get(field), (int, float))
                        or not math.isfinite(metrics[field]) or metrics[field] < 0 for field in required):
                    metrics = None
                receipt["trees"][name] = {"benchmark": results, "metrics": metrics, "regressions": tests,
                                           "release_digest": release_digest(tree)}
        old, new = [receipt["trees"][name] for name in ("base", "head")]
        a, b = old["metrics"], new["metrics"]
        passed = bool(a and b and old["regressions"]["exit"] == new["regressions"]["exit"] == 0
                      and b.get("protocol") == a.get("protocol") == "scheduler-work-v1"
                      and b.get("quality") == 5 and 0 <= a.get("quality", -1) <= 5
                      and b.get("provider_calls") == a.get("provider_calls") == 0
                      and b.get("idle_model_turns", math.inf) <= a.get("idle_model_turns", -1)
                      and (b["idle_model_turns"] < a["idle_model_turns"] or b["sqlite_statements"] <= 0.8 * a["sqlite_statements"])
                      and b.get("cpu_seconds", math.inf) <= max(0.25, 1.25 * a.get("cpu_seconds", 0)))
        receipt["passed"] = passed
        receipt["limitations"] = "Synthetic scheduler quality/cost comparison. Production retention still requires an exact-tree watchdog canary and subsequent observations."
        receipt["cost_accounting"] = {"provider_calls": 0, "external_patch_authoring_usd": None, "local_compute_usd": None,
                                      "note": "External authoring and compute dollars are unknown here, not zero; operational research cost is recorded separately."}
        (artifact / "evaluation.json").write_text(json.dumps(receipt, indent=2) + "\n")
        proposal.update(evaluation_sha=sha(receipt), release_digest=new["release_digest"], evaluation=receipt)
        self.worklist.transition(key, "canary" if passed else "rejected", commit=proposal["head"], attempt=job.attempt,
                                 note="Fixed controls and regressions improved; exact-tree deployment/canary is owed." if passed else
                                      "No demonstrated improvement under the frozen controls; keep the running harness.",
                                 extra={"_proposal": proposal, "decision": "await_canary" if passed else "reject"})
        return receipt

    def reconcile(self, key: str, *, deploy_log: Path, current_release: str, swarm: Path) -> dict:
        job = self.worklist.get(key)
        if job is None or job.state not in ("canary", "observing", "verified"):
            raise ImprovementError("candidate is not awaiting or following a deployment")
        if job.details.get("lane"):
            # On the House: the deploy receipts every time (a rollback is noticed at once), the registered window's
            # read-only measurement only once it has ended and no decision exists yet.
            proposal = job.carry.get("_proposal") or {}
            arm = proposal.get("canary") or {}
            rows = []
            for line in Path(deploy_log).read_text().splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
            now = self.clock()
            if proposal.get("observation") or not arm.get("since") or now < float(arm["since"]) + float(proposal["observation_seconds"]):
                light = {"since": float(arm.get("since") or now), "until": now, "deploys": rows, "current": current_release,
                         "source": {}, "lanes": {}}
                return self.reconcile_lane(key, measurement=light)
            measurement = lanes.measure(swarm, since=float(arm["since"]),
                                        now=float(arm["since"]) + float(proposal["observation_seconds"]),
                                        lanes=[job.details["lane"]], examples=0)
            measurement.update(deploys=rows, current=current_release)
            return self.reconcile_lane(key, measurement=measurement)
        proposal = dict(job.carry["_proposal"])
        rows = []
        for line in Path(deploy_log).read_text().splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except ValueError:
                continue  # a writer may be appending the last line
        stages = [r for r in rows if r.get("stage") == "stage" and r.get("ok") is True and r.get("digest") == proposal["release_digest"]]
        if not stages:
            return {"waiting": "no watchdog stage receipt for the exact evaluated tree"}
        stage = stages[-1]
        attempt = [r for r in rows if r.get("deploy") == stage.get("deploy")]
        final = next((r for r in reversed(attempt) if r.get("stage") == "verdict"), None)
        rollback = any(r.get("stage") == "rollback" and r.get("ok") is True and r.get("from") == stage.get("release") for r in rows)
        if rollback or final and final.get("verdict") in ("rolled_back", "refused", "failed"):
            result = {"decision": "reverted" if rollback or final.get("verdict") == "rolled_back" else "rejected",
                      "release": stage.get("release"), "watchdog": final}
            self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt, note="The exact-tree watchdog rejected or reverted the candidate.",
                                     extra={"_proposal": proposal, **result})
            return result
        canary = next((r for r in attempt if r.get("stage") == "canary" and r.get("ok") is True and int(r.get("ticks", 0)) >= 3), None)
        start = next((r for r in attempt if r.get("stage") == "start"), {})
        watches = [r for r in attempt if r.get("stage") == "watch" and not r.get("grace")]
        if not final or final.get("verdict") != "promoted" or not canary or int(start.get("watch_seconds", 0)) < 600 or not watches or any(not r.get("ok") for r in watches):
            return {"waiting": "a complete successful watchdog canary and watch are required"}
        if current_release != stage.get("release"):
            return {"waiting": "the evaluated release is not currently running", "current": current_release}
        if proposal.get("observation"):
            return proposal["observation"]  # one registered observation window; later favorable peeks cannot reverse it
        at = dt.datetime.fromisoformat(final["at"].replace("Z", "+00:00")).timestamp()
        source = running_evidence(swarm, None, now=self.clock())
        if Path(source["release"]).name != current_release or source["digest"] != proposal["release_digest"]:
            return {"waiting": "the swarm heartbeat and current release do not match the evaluated tree"}
        if source["started_at"] > at:
            return {"waiting": "the observed swarm restarted after the registered deployment cohort began"}
        proposal["canary"] = {"deploy": stage["deploy"], "release": current_release, "promoted_at": final["at"], "receipt_sha": sha(attempt)}
        until = at + proposal["observation_seconds"]
        if self.clock() < until:
            if job.state != "observing":
                self.worklist.transition(key, "observing", commit=proposal["head"], attempt=job.attempt, note="Exact-tree watchdog passed; awaiting subsequent operational evidence.", extra={"_proposal": proposal})
            return {"waiting": "subsequent observation window", "seconds": self.clock() - at}
        after = snapshot(swarm, since=at, until=until)
        before = proposal["baseline"]
        improved = after["hold_call_share"] <= before["hold_call_share"] * 0.8
        quality = (after["cycles"] >= MIN_CYCLES and after["new_trials"] > 0 and all(
            after[field] / max(1, after["cycles"]) <= before[field] / max(1, before["cycles"])
            for field in ("errors", "refused_cycles")))
        efficiency = before["trials_per_model_usd"] is not None and after["trials_per_model_usd"] is not None and after["trials_per_model_usd"] >= before["trials_per_model_usd"]
        result = {"decision": "retained" if improved and quality and efficiency else "revert_recommended", "release": current_release,
                  "before": before, "after": after, "improved": improved, "quality_preserved": quality, "cost_efficiency_preserved": efficiency,
                  "limitations": "Operational evidence, not strategy alpha or project profitability; rollout cohorts may differ."}
        if after["cycles"] < MIN_CYCLES:
            result.update(decision="insufficient_activity", reason="The fixed observation window had fewer than 20 cycles; retention is unproved.")
        proposal["observation"] = result
        self.worklist.transition(key, "verified" if result["decision"] == "retained" else "observing", commit=proposal["head"], attempt=job.attempt,
                                 note=("Subsequent observations support retention." if result["decision"] == "retained" else
                                       "Rollback recommended; operator must execute and watchdog must confirm it." if result["decision"] == "revert_recommended" else
                                       "Insufficient post-deploy activity in the registered window. Operator review is required; no automatic retention or fresh peek."),
                                 extra={"_proposal": proposal, **result})
        return result

    # ------------------------------------------------------------------ the lanes (league/swarm/harness_lanes.py)
    MAX_ATTEMPTS = 3

    def secret(self) -> str:
        """The journal's private held-out secret (mode 0600), created once. Never shown in a brief or a receipt."""
        path = self.root / "heldout.secret"
        if not path.exists():
            part = path.with_name(path.name + ".part")
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_hex(32) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(part, path)
        value = path.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ImprovementError("the journal's held-out secret is malformed; restore it from a backup, never regenerate it")
        return value

    def capture_lanes(self, measurement: Mapping[str, Any], *, base: str) -> list[dict]:
        """Register every lane bottleneck over its predeclared threshold as a durable candidate, ranked. `measurement` is
        `harness_lanes.measure` of the running House (read only). The same evidence twice buys no second attempt."""
        if not re.fullmatch(r"[0-9a-f]{40}", base):
            raise ImprovementError("base must be the full reviewed Git commit SHA")
        if measurement.get("schema") != lanes.SCHEMA or measurement.get("policy") != lanes.POLICY:
            raise ImprovementError("the measurement is not a harness-lanes-1 document")
        span = float(measurement["until"]) - float(measurement["since"])
        if not 900 <= span <= 7 * 86400:
            raise ImprovementError("a capture's measurement window is between 900 seconds and seven days")
        source = dict(measurement.get("source") or {})
        if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("digest") or "")):
            raise ImprovementError("the measurement lacks the running release's tree digest")
        for job in self.worklist.jobs().values():
            proposal = job.carry.get("_proposal") or {}
            if job.state == "verified" and proposal.get("release_digest") == source["digest"]:
                base = proposal["head"]  # a retained change's exact tree is the next generation's baseline
        through = int(float(measurement["until"]))
        digest = sha(measurement)
        out = []
        for row in lanes.rank(measurement):
            row = dict(row)
            if not row["captured"]:
                out.append(row)
                continue
            name, metric = row["lane"], row["metric"]
            lane = lanes.LANES[name]
            bottleneck = lane.bottleneck(metric)
            key = f"harness:{name}:{metric}:{base[:16]}"
            row["key"] = key
            old = self.worklist.get(key)
            if old is not None and (old.through.get("research", 0) >= through or old.state not in ("proposed", "admitted")):
                row["state"] = old.state
                out.append(row)
                continue
            data = measurement["lanes"][name]
            motivating = lanes.motivating_units(name, data)
            baseline: dict[str, Any] = {"metrics": lanes.lane_metrics(name, data),
                                        "heldout_metrics": lanes.lane_metrics(name, data, exclude=motivating),
                                        "window": measurement["window"]}
            if lane.canary_for(bottleneck).get("mode") == "window":
                # The before cohort of a before/after comparison (the arms modes need none: their control is concurrent).
                baseline["units"] = data.get("units") or {}
                baseline["extra"] = {k: v for k, v in lanes.lane_tallies(name, data).items()
                                     if k in ("runs", "error_runs", "restarts", "restart_failures", "live_errors", "restarts_or_one")}
            evidence = [{"at": str(e.get("first_at") or measurement["window"]["until"]),
                         "agent": str((e.get("families") or e.get("boxes") or [e.get("family") or "house"])[0]),
                         "excerpt": str(e.get("signature") or e.get("mechanism") or "")[:600]}
                        for e in (data.get("examples") or [])[:12]]
            self.worklist.report(key=key, kind="shared_defect", summary=f"{lane.title}: {bottleneck.summary}", evidence=evidence,
                                 agents=motivating[:200], source="research", severity=row["severity"], through_seq=through,
                                 details={"lane": name, "metric": metric, "base": base, "policy": lanes.POLICY,
                                          "lane_sha": lanes.lane_sha(lane), "baseline": baseline, "motivating": motivating,
                                          "source": {k: source.get(k) for k in ("release", "digest", "started_at")},
                                          "measurement_sha": digest, "stake": row["stake"], "rank": row["rank"],
                                          "value": row["value"]})
            row["state"] = self.worklist.get(key).state
            out.append(row)
        return out

    def brief(self, key: str) -> dict[str, Any]:
        """What the patch author may see: the measured bottleneck and its motivating examples, the lane's surface and
        protected paths, the predeclared metric, the judge's dev split, the canary gate. Never the held-out split."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane"):
            raise ImprovementError("no lane candidate with that key")
        lane = lanes.LANES[job.details["lane"]]
        b = lane.bottleneck(job.details["metric"])
        canary = lane.canary_for(b)
        unit = {"family": "the family id (fam['id'])", "restart": None, "box": None}.get(canary.get("unit"), None)
        if lane.id == "memory":
            unit = "canary.mechanism_unit(mechanism) (the proposal's mechanism text)"
        gate = (f'from league.swarm import canary\nif canary.enabled("{key}", <unit>, root=<the swarm state directory>):\n'
                "    ... the new behavior\nelse:\n    ... the old behavior, byte for byte") if canary.get("mode") in ("arms", "practice") else None
        return {"key": key, "lane": lane.id, "title": lane.title, "bottleneck": b.summary,
                "metric": {"name": b.metric.name, "is": f"{b.metric.numerator} / {b.metric.denominator}",
                           "direction": b.metric.direction, "must_improve_by": b.metric.min_effect},
                "secondary_must_not_worsen": [m.name for m in b.secondary], "guards_must_not_worsen": [m.name for m in lane.guards],
                "measured": job.details.get("baseline", {}).get("metrics"), "stake": job.details.get("stake"),
                "motivating_examples": job.evidence[:12],
                "surface": list(lane.surface),
                "protected": "every path in league/swarm/harness_lanes.py PROTECTED (the objective and this loop, sealed data "
                             "and the evaluator, spend limits, capital permissions, the release train) and every path outside "
                             "the surface; no new process, network, reflection, file-write call or spend/capital import",
                "judge": {"script": f"league/swarm/harness_judges/{lane.judge}.py", "protocol": lane.protocol,
                          "dev_split": "fixed; readable in the judge file", "primary": b.judge_primary, "mode": b.judge_mode,
                          "must_fall_on_heldout_by": b.judge_effect if b.judge_mode == "improve" else None,
                          "must_be_zero": list(lane.judge_zero), "must_not_rise": list(lane.judge_no_worse),
                          "cost": lane.judge_cost, "cost_rule": lane.judge_cost_rule, "regressions": list(lane.regressions)},
                "heldout": "a second split generated from a seed that exists only after your commit is staged; never shown",
                "canary": {**canary, "unit_in_code": unit, "gate": gate},
                "release_classes": list(lane.release_classes),
                "deploy_rules": {c: lanes.DEPLOY_RULES[c] for c in lane.release_classes},
                "attempts_left": max(0, self.MAX_ATTEMPTS - job.attempt)}

    def _stage_lane(self, job: Any, candidate: str) -> dict:
        key, lane = job.key, lanes.LANES[job.details["lane"]]
        bottleneck = lane.bottleneck(job.details["metric"])
        base = str(job.details["base"])
        head = None
        attempt = job.attempt + 1
        if attempt > self.MAX_ATTEMPTS:
            raise ImprovementError(f"this bottleneck has used its {self.MAX_ATTEMPTS} attempts; a new capture on a new base is required")
        try:
            if job.details.get("lane_sha") != lanes.lane_sha(lane) or job.details.get("policy") != lanes.POLICY:
                raise ImprovementError("the lane's predeclared definition changed after capture; capture again")
            git(self.repo, "rev-parse", "--verify", f"{base}^{{commit}}")
            head = git(self.repo, "rev-parse", "--verify", f"{candidate}^{{commit}}")
            git(self.repo, "merge-base", "--is-ancestor", base, head)
            paths = git(self.repo, "diff", "--name-only", base, head).splitlines()
            lanes.surface_check(lane, paths)
            added: list[str] = []
            for path in paths:
                try:
                    after = git(self.repo, "show", f"{head}:{path}")
                except ImprovementError:
                    raise ImprovementError(f"{path}: a lane candidate may not delete a file") from None
                try:
                    before = git(self.repo, "show", f"{base}:{path}")
                except ImprovementError:
                    before = None
                lanes.content_guard(path, before, after)
            diff = git(self.repo, "diff", "--unified=0", base, head)
            added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
            with tempfile.TemporaryDirectory(prefix="harness-baseline-") as temp:
                tree = Path(temp) / "base"
                archive(self.repo, base, tree)
                if release_digest(tree) != job.details["source"]["digest"]:
                    raise ImprovementError("baseline commit does not match the measured running release")
                classification = lanes.classify(paths, lanes.live_path_modules(tree))
            if classification["release_class"] not in lane.release_classes:
                raise ImprovementError(f"a {classification['release_class']} change is outside the {lane.id} lane "
                                       f"({list(lane.release_classes)}): {classification['paths']}")
            canary = lane.canary_for(bottleneck)
            mode = canary.get("mode", "window")
            gated = any("canary.enabled(" in line for line in added) and any(key in line for line in added)
            if mode in ("arms", "practice") and not gated:
                raise ImprovementError(f"the {lane.id} lane's canary gates the change per {canary.get('unit')}: call "
                                       f'canary.enabled("{key}", <unit>, root=...) around the new behavior (see the brief)')
        except (ImprovementError, SyntaxError, OSError) as exc:
            self.worklist.transition(key, "revising" if attempt < self.MAX_ATTEMPTS else "rejected", attempt=attempt, commit=head,
                                     note=f"Candidate preflight refused: {exc}",
                                     extra={"_failure": {"phase": "stage", "candidate": head or str(candidate)[:100],
                                                         "base": base, "reason": str(exc)[:1000]}})
            raise ImprovementError(str(exc)) from exc
        artifact = self.root / "candidates" / sha([key, head])[:20]
        artifact.mkdir(parents=True, exist_ok=True)
        patch = git(self.repo, "diff", "--binary", base, head, binary=True)
        (artifact / "candidate.patch").write_bytes(patch)
        proposal = {"base": base, "head": head, "artifact": str(artifact.resolve()), "patch_sha": sha(patch),
                    "policy": lanes.POLICY, "lane": lane.id, "metric": bottleneck.metric.name, "lane_sha": lanes.lane_sha(lane),
                    "judge_sha": judges_sha(), "protocol": lane.protocol, "regressions": list(lane.regressions),
                    "classification": classification, "canary_mode": mode,
                    "observation_seconds": int(canary.get("observe_seconds", OBSERVE_SECONDS)),
                    "baseline": job.details["baseline"], "source": job.details["source"]}
        self.worklist.transition(key, "testing", commit=head, attempt=attempt,
                                 note=f"Patch pinned inside the {lane.id} surface ({classification['release_class']}); "
                                      "isolated evaluation on the dev and held-out splits is owed.",
                                 extra={"_proposal": proposal})
        return proposal

    def _evaluate_lane(self, job: Any, *, python: Path) -> dict:
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        bottleneck = lane.bottleneck(proposal["metric"])
        if (proposal["judge_sha"] != judges_sha() or proposal["lane_sha"] != lanes.lane_sha(lane)
                or proposal["policy"] != lanes.POLICY or proposal["regressions"] != list(lane.regressions)):
            raise ImprovementError("the frozen judge or lane changed; register a new candidate under the new protocol")
        artifact = Path(proposal["artifact"])
        judge = artifact / "judge"
        judge.mkdir(exist_ok=True)
        for source in sorted(JUDGES.glob("*.py")):
            (judge / source.name).write_bytes(source.read_bytes())
        seed = lanes.heldout_seed(self.secret(), job.key, proposal["head"])
        receipt: dict[str, Any] = {"policy": lanes.POLICY, "lane": lane.id, "metric": proposal["metric"],
                                   "judge_sha": proposal["judge_sha"], "base": proposal["base"], "head": proposal["head"],
                                   "heldout_seed": seed, "trees": {}}
        with tempfile.TemporaryDirectory(prefix="harness-eval-") as temp:
            for name in ("base", "head"):
                tree = Path(temp) / name
                archive(self.repo, proposal[name], tree)
                splits = {}
                for split in ("dev", "heldout"):
                    result = sandbox(tree, judge, [f"/judge/{lane.judge}.py", "--split", split, "--seed", seed], python=python)
                    try:
                        metrics = json.loads(result["stdout"].splitlines()[-1]) if result["exit"] == 0 else None
                    except (ValueError, IndexError):
                        metrics = None
                    if not isinstance(metrics, dict) or metrics.get("protocol") != lane.protocol \
                            or metrics.get("split") != split or metrics.get("provider_calls") != 0:
                        metrics = None
                    splits[split] = {"benchmark": result, "metrics": metrics}
                tests = sandbox(tree, judge, ["-m", "unittest", *proposal["regressions"], "-q"], python=python)
                receipt["trees"][name] = {"splits": splits, "regressions": tests, "release_digest": release_digest(tree)}
        verdict = lanes.judge_verdict(lane, bottleneck, receipt["trees"])
        passed = verdict["passed"]
        receipt.update(passed=passed, verdict=verdict,
                       limitations="Synthetic fixed benchmark. Retention still needs the exact-tree deployment, the canary and "
                                   "the registered observation window against the concurrent control.",
                       cost_accounting={"provider_calls": 0, "external_patch_authoring_usd": None, "local_compute_usd": None,
                                        "note": "External authoring and compute dollars are unknown here, not zero."})
        (artifact / "evaluation.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n")
        head_tree = receipt["trees"]["head"]
        proposal.update(evaluation_sha=sha(json.loads(json.dumps(receipt, default=str))),
                        release_digest=head_tree["release_digest"], evaluation={"passed": passed, "verdict": verdict})
        state = "canary" if passed else ("revising" if job.attempt < self.MAX_ATTEMPTS else "rejected")
        self.worklist.transition(job.key, state, commit=proposal["head"], attempt=job.attempt,
                                 note=("Fixed benchmark, held-out split and regressions passed; exact-tree deployment under "
                                       f"the {proposal['classification']['release_class']} rule, then the canary, is owed."
                                       if passed else "Not demonstrated under the frozen judge: " + "; ".join(verdict["reasons"])[:1500]),
                                 extra={"_proposal": proposal, "decision": "await_canary" if passed else "reject"})
        return receipt

    def _write_arm(self, key: str, arm: Mapping[str, Any] | None) -> Path:
        """Set (or with None remove) one key's arm in `<root>/canary.json`, the file the gate reads (`canary.FILE`)."""
        from . import canary as gate

        path = self.root / "canary.json"
        arms = gate.read(path)
        if arm is None:
            arms.pop(key, None)
        else:
            arms[key] = dict(arm)
        part = path.with_name(path.name + f".{os.getpid()}.part")
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump({"schema": gate.SCHEMA, "arms": arms}, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, path)
        return path

    def canary_start(self, key: str, *, measurement: Mapping[str, Any], fraction: float | None = None) -> dict:
        """Start the registered observation once the exact evaluated tree is deployed and promoted by the watchdog: open
        the gate for `fraction` of the lane's units (arms modes) or date the before/after window (window mode)."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane") or job.state != "canary":
            raise ImprovementError("the candidate is not awaiting its canary")
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        canary = lane.canary_for(lane.bottleneck(proposal["metric"]))
        receipts = watchdog(list(measurement.get("deploys") or []), proposal["release_digest"])
        if "waiting" in receipts:
            return receipts
        final = receipts["final"] or {}
        if receipts["rollback"] or final.get("verdict") in ("rolled_back", "refused", "failed"):
            result = {"decision": "reverted" if receipts["rollback"] or final.get("verdict") == "rolled_back" else "rejected",
                      "release": receipts["stage"].get("release"), "watchdog": final}
            self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt,
                                     note="The exact-tree watchdog rejected or reverted the candidate.", extra={"_proposal": proposal, **result})
            return result
        if not receipts["complete"]:
            return {"waiting": "a complete successful watchdog canary and watch are required"}
        release = receipts["stage"].get("release")
        if measurement.get("current") != release or (measurement.get("source") or {}).get("digest") != proposal["release_digest"]:
            return {"waiting": "the evaluated release is not the one running", "current": measurement.get("current")}
        promoted = lanes.epoch_of(final.get("at")) or float(measurement["until"])
        mode = proposal["canary_mode"]
        if mode in ("arms", "practice"):
            share = float(fraction if fraction is not None else canary.get("fraction", 0.25))
            if not 0.05 <= share <= 0.5:
                raise ImprovementError("a canary arm holds between 5% and 50% of the units: the rest are the control")
            # The arm opens when the file is installed; two minutes' allowance for that, then the window runs.
            arm = {"lane": lane.id, "mode": mode, "fraction": share, "salt": secrets.token_hex(8), "state": "canary",
                   "since": round(max(promoted, float(measurement["until"])) + 120.0, 3), "release": release,
                   "release_digest": proposal["release_digest"]}
            path = self._write_arm(key, arm)
        else:
            arm = {"lane": lane.id, "mode": mode, "since": round(promoted, 3), "release": release,
                   "release_digest": proposal["release_digest"]}
            path = None
        proposal["canary"] = arm
        self.worklist.transition(key, "observing", commit=proposal["head"], attempt=job.attempt,
                                 note=f"Canary started ({mode}); the registered window ends "
                                      f"{iso(arm['since'] + proposal['observation_seconds'])}.", extra={"_proposal": proposal})
        out = {"started": arm, "window_until": arm["since"] + proposal["observation_seconds"]}
        if path is not None:
            out["gate_file"] = str(path)
            out["install"] = ("the House gate reads <swarm-state>/harness/canary.json: when this journal is not that "
                              "directory, replace that file atomically (mode 0600) with this one within two minutes")
        return out

    def canary_stop(self, key: str, *, state: str = "reverted") -> dict:
        """Flip a key's gate to the old behavior (`reverted`) or keep it for everyone (`retained`) by hand; recorded."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane"):
            raise ImprovementError("no lane candidate with that key")
        if state not in ("reverted", "retained"):
            raise ImprovementError("a gate is reverted or retained")
        proposal = dict(job.carry.get("_proposal") or {})
        arm = dict(proposal.get("canary") or {})
        if arm.get("mode") not in ("arms", "practice"):
            raise ImprovementError("this candidate has no gate to flip: roll it back through the watchdog")
        arm.update(state=state, flipped_at=self.clock())
        proposal["canary"] = arm
        path = self._write_arm(key, arm)
        self.worklist.transition(key, "verified" if state == "retained" else "rejected", commit=proposal.get("head"),
                                 attempt=job.attempt, note=f"Operator flipped the gate: {state}.",
                                 extra={"_proposal": proposal, "decision": f"gate_{state}"})
        return {"gate": state, "gate_file": str(path)}

    def reconcile_lane(self, key: str, *, measurement: Mapping[str, Any]) -> dict:
        """The registered decision on the window [canary since, since + observation_seconds): the canary arm against the
        concurrent control arm with the motivating units excluded from both (arms modes), or the window, held out by
        time, against the capture's baseline (window mode). Computed once; a later measurement never reopens it."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane") or job.state not in ("canary", "observing", "verified"):
            raise ImprovementError("the candidate is not awaiting or following a canary")
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        bottleneck = lane.bottleneck(proposal["metric"])
        receipts = watchdog(list(measurement.get("deploys") or []), proposal["release_digest"])
        final = receipts.get("final") or {}
        if "waiting" not in receipts and (receipts["rollback"] or final.get("verdict") in ("rolled_back", "refused", "failed")):
            result = {"decision": "reverted", "release": receipts["stage"].get("release"), "watchdog": final}
            if (proposal.get("canary") or {}).get("mode") in ("arms", "practice"):
                self._write_arm(key, {**proposal["canary"], "state": "reverted"})
            self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt,
                                     note="The watchdog rolled the candidate's release back.", extra={"_proposal": proposal, **result})
            return result
        if proposal.get("observation"):
            return proposal["observation"]
        arm = proposal.get("canary")
        if not arm:
            return {"waiting": "the canary has not started: run the canary step"}
        since, window = float(arm["since"]), float(proposal["observation_seconds"])
        if abs(float(measurement["since"]) - since) > 60 or float(measurement["until"]) < since + window:
            return {"waiting": "measure exactly the registered window", "since": since, "until": since + window}
        if measurement.get("current") != arm["release"] or (measurement.get("source") or {}).get("digest") != proposal["release_digest"]:
            return {"waiting": "the evaluated release is not running; the window cannot be judged",
                    "current": measurement.get("current")}
        started = float((measurement.get("source") or {}).get("started_at") or 0.0)
        restarts_are_units = lane.canary_for(bottleneck).get("unit") == "restart"
        if arm["mode"] == "window" and started > since and not restarts_are_units:
            return {"waiting": "the swarm restarted inside a before/after window; this comparison is confounded"}
        data = (measurement.get("lanes") or {}).get(lane.id)
        if not isinstance(data, Mapping):
            return {"waiting": f"the measurement has no {lane.id} lane"}
        motivating = job.details.get("motivating") or []
        seed = sha([key, arm.get("salt") or arm["since"]])
        extras = ("runs", "error_runs", "restarts", "restart_failures", "live_errors", "restarts_or_one")
        if arm["mode"] in ("arms", "practice"):
            treated, control = lanes.split_arms(data.get("units") or {}, key=key, salt=arm["salt"], fraction=arm["fraction"],
                                                exclude=motivating)
            result = lanes.retention(lane, bottleneck, treated, control, seed=seed, alpha=ALPHA)
        else:
            # Before/after: the window is later than every motivating row, so it is held out by time. Dropping the
            # motivating units (the boxes that failed) from the capture's side would remove the bottleneck itself.
            motivating = []
            treated = dict(data.get("units") or {})
            control = dict(proposal["baseline"].get("units") or {})
            after = {k: v for k, v in lanes.lane_tallies(lane.id, data).items() if k in extras}
            before = dict(proposal["baseline"].get("extra") or {})
            result = lanes.retention(lane, bottleneck, treated, control, seed=seed, alpha=ALPHA,
                                     extra_treated=after or None, extra_control=before or None)
        result.update(release=arm["release"], window={"since": iso(since), "until": iso(since + window)}, mode=arm["mode"],
                      motivating_excluded=len(motivating),
                      limitations="Operational evidence of the harness change, not strategy alpha or profitability.")
        if result["decision"] == "retained":
            if arm["mode"] in ("arms", "practice"):
                self._write_arm(key, {**arm, "state": "retained"})
            state, note = "verified", "The canary beat its predeclared metric against the control; the gate is retained."
        elif result["decision"] == "revert_recommended" and arm["mode"] in ("arms", "practice"):
            self._write_arm(key, {**arm, "state": "reverted"})
            result["decision"] = "reverted"
            state, note = "rejected", "The canary did not beat its predeclared metric; the gate is flipped back (old behavior)."
        elif result["decision"] == "revert_recommended":
            state, note = "observing", "Rollback recommended; the operator must execute it and the watchdog confirm it."
        else:
            state, note = "observing", "Too little activity in the registered window; no retention and no fresh peek."
        proposal["observation"] = result
        self.worklist.transition(key, state, commit=proposal["head"], attempt=job.attempt, note=note,
                                 extra={"_proposal": proposal, "decision": result["decision"]})
        return result

    def next_steps(self, *, root: str = "<journal>", repo: str = "<owner repo>") -> list[dict]:
        """One command per open lane candidate: the next step the operator runs (the playbook's procedure)."""
        cli = f"python scripts/harness_improve.py --root {root} --repo {repo}"
        house = "python -B scripts/harness_improve.py measure --swarm /workspace/state"
        out = []
        for job in sorted((j for j in self.worklist.jobs().values() if j.details.get("lane")),
                          key=lambda j: (int(j.details.get("rank") or 99), j.key)):
            p = job.carry.get("_proposal") or {}
            lane = lanes.LANES[job.details["lane"]]
            step = {"key": job.key, "lane": lane.id, "metric": job.details["metric"], "state": job.state, "attempt": job.attempt}
            if job.state in ("proposed", "admitted"):
                step["next"] = f"{cli} prepare {job.key} --worktree <a new directory>"
            elif job.state in ("patching", "revising"):
                why = (job.carry.get("_failure") or {}).get("reason") if job.state == "revising" else None
                step["next"] = (f"write and commit the patch in {p.get('worktree') or '<the worktree>'} within the brief; then "
                                f"{cli} stage {job.key} --candidate <full commit sha>")
                if why:
                    step["last_refusal"] = why[:400]
            elif job.state == "testing":
                step["next"] = f"{cli} evaluate {job.key} --python <a venv python with numpy>"
            elif job.state == "canary" and not p.get("canary"):
                rule = (p.get("classification") or {}).get("deploy_rule")
                step["next"] = (f"deploy exactly the evaluated tree {str(p.get('release_digest'))[:12]} through the watchdog "
                                f"({rule}); then on the House `{house} --seconds 900 > m.json` and here "
                                f"`{cli} canary {job.key} --measurement m.json`")
            elif job.state == "observing" and p.get("canary") and not p.get("observation"):
                since = float(p["canary"]["since"])
                until = since + float(p["observation_seconds"])
                step["next"] = (f"after {iso(until)}: on the House `{house} --since {since} --until {until} --lanes {lane.id} "
                                f"> m.json` and here `{cli} reconcile {job.key} --measurement m.json`")
            else:
                step["next"] = None
                step["decision"] = job.last_status.get("decision")
            out.append(step)
        return out


__all__ = ["HarnessImprovement", "ImprovementError", "snapshot", "patch_guard", "sandbox", "release_digest", "watchdog",
           "judges_sha"]
