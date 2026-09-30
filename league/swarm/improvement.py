"""Persistent, evidence-led harness changes, using the existing hash-chained repair worklist.

The first registered lane is scheduler efficiency. The optimizer supplies a committed patch; this controller freezes
its baseline, runs both trees against an external fixed judge in a credential-free network namespace, and follows
the existing watchdog's exact-tree canary receipts. Retention additionally needs subsequent operational evidence.
It never edits a running release, places an order, opens a PR, funds a service, or deploys/rolls back production.
Those legs remain with the authorized operator/agent and the existing deployment watchdog.
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
        self.worklist.transition(key, "patching", note="Isolated worktree ready for an authorized patch author; no model call or deployment was made.",
                                 attempt=job.attempt, extra={"_proposal": proposal})
        return proposal

    def stage(self, key: str, candidate: str) -> dict:
        job = self.worklist.get(key)
        if job is None or job.state not in ("proposed", "admitted", "patching", "revising"):
            raise ImprovementError("candidate needs an open measured bottleneck")
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


__all__ = ["HarnessImprovement", "ImprovementError", "snapshot", "patch_guard", "sandbox", "release_digest"]
