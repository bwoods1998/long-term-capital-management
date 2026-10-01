"""Persistent, evidence-led harness changes, using the existing hash-chained repair worklist.

The first registered lane is scheduler efficiency. The optimizer supplies a committed patch; this controller freezes
its baseline, runs both trees against an external fixed judge in a credential-free network namespace, and follows
the existing watchdog's exact-tree canary receipts. Retention additionally needs subsequent operational evidence.
It never edits a running release, places an order, opens a PR, funds a service, or deploys/rolls back production.
Those legs remain with the authorized operator/agent and the existing deployment watchdog.

Four more lanes (research workflow, prompts/memory, data processing, execution reliability) run the same loop with
their own predeclared metrics, surfaces, fixed judges and canaries (`league/swarm/harness_lanes.py`): a read-only House
measurement ranks their bottlenecks that repay a cycle (`capture_lanes`); a candidate is staged only as modifications
and additions inside its lane's surface, never on a protected path or a frozen symbol, and (arms lanes) with every
change inside a gated branch whose else is the baseline's code; the judge scores the baseline and the candidate with
its gate forced open and closed (closed must equal the baseline) on a fixed dev split and a held-out split seeded only
after the candidate is committed; the canary gates the change to a deterministic fraction of units
(`league/swarm/canary.py`), or (window lanes) the window after the release is compared with a fresh control window
before it; the registered window is judged once, after it ends, motivating units excluded. A failed comparison flips
the gate back (the old behavior at the next read); a supported one retains it until it graduates into main without its
gate; another release inside the window voids it.

What the controller refuses and what is only defense in depth (`harness_lanes` module docstring): staging refuses a diff
that touches a protected path (`git diff --no-renames --name-status`, deletions and renames included); every candidate
needs an ADVERSARIAL REVIEW of its exact patch and evaluated tree recorded here with the verdict approve (`review`)
before the loop's deploy step (`deploy`) issues the ticket the tree is deployed under, and registering its canary
(lanes) or opening its observation window (the scheduler lane) voids it, with a rollback asked for, when the watchdog's
receipts show the tree on the House before that approval and ticket (`unreviewed`); and capture, staging, evaluation,
the judges, the benchmarks and the retain/revert decision run from the PINNED BASE commit: this controller refuses to run
unless its own code is that commit's (`pinned`; the CLI re-executes itself from a separate checkout of the base), takes
the judges and the benchmark from the base tree, judges the base tree with only the candidate's staged files laid over
it, and accepts a House measurement only when the code that took it is the base's (`measured_by_base`). The import and
state rule and the per-name content and symbol guards are static analysis of arbitrary Python: they refuse the routes
reviewers found and are never a guarantee.
"""
from __future__ import annotations

import ast
import datetime as dt
import fnmatch
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
from .harness_runtime import write_json

REPO = Path(__file__).resolve().parents[2]
BENCHMARK = Path(__file__).with_name("improvement_benchmark.py")
BENCHMARK_PATH = "league/swarm/improvement_benchmark.py"
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
#: A capture's measurement must have been taken this recently, of a running swarm with a fresh heartbeat: the candidate
#: is bound to the release that measurement saw, and a stale document (another release running since) would bind it to a
#: tree the deploy would roll back to.
FRESH_SECONDS = 3600
#: The environment marker the judges' sandbox sets: the gate honors its judges' override only where it is present
#: (`canary.py`), so nothing a candidate's code does on the House can force a gate.
JUDGE_MARKER = "LTCM_HARNESS_JUDGE"
#: The controller's own code: what captures, stages, judges, measures and decides (with every file of the judges'
#: directory). It must be the pinned base commit's, byte for byte, wherever a candidate's fate is computed (`pinned`).
CONTROLLER = ("league/swarm/improvement.py", "league/swarm/harness_lanes.py", "league/swarm/canary.py",
              "league/swarm/harness_runtime.py", "league/swarm/improvement_benchmark.py", "league/ledger.py",
              "league/worklist.py", "league/watchdog.py", "scripts/harness_improve.py", "scripts/floor_box.py")
JUDGES_PATH = "league/swarm/harness_judges"
#: A review report names its verdict on a line of its own: `VERDICT: approve` or `VERDICT: reject`.
VERDICT_LINE = re.compile(r"^\s*VERDICT:\s*(approve|reject)\s*$", re.I | re.M)


def controller_paths(root: Path = REPO) -> list[str]:
    """The controller's files as this checkout has them (`CONTROLLER` and the judges' Python files)."""
    judges = sorted(f"{JUDGES_PATH}/{p.name}" for p in (Path(root) / JUDGES_PATH).glob("*.py"))
    return list(CONTROLLER) + judges


def base_blobs(repo: Path, commit: str, paths: list[str]) -> dict[str, str]:
    """{path: git blob id} of `paths` (files, or directories listed recursively) in `commit`."""
    out = {}
    for line in git(repo, "ls-tree", "-r", "--full-tree", commit, "--", *paths).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            out[path] = parts[2]
    return out


class ImprovementError(ValueError):
    pass


def sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


#: SwarmStore's second-resolution timestamps, for SQL text comparisons (one definition, the lanes').
iso = lanes.iso


def git(repo: Path, *args: str, binary: bool = False) -> Any:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        raise ImprovementError(f"git {args[0]}: {result.stderr.decode(errors='replace')[-600:]}")
    return result.stdout if binary else result.stdout.decode().strip()


def commit_reader(repo: Path, commit: str) -> Any:
    """`read(repo-relative path) -> source or None` over one commit's blobs (cached): the tree a guard resolves names in."""
    cache: dict[str, str | None] = {}

    def read(rel: str) -> str | None:
        if rel not in cache:
            result = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{commit}:{rel}"], capture_output=True,
                                    check=False)
            cache[rel] = result.stdout.decode(errors="replace") if result.returncode == 0 else None
        return cache[rel]
    return read


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


def tree_judges_sha(tree: Path) -> str:
    """The judges' hash in an archived tree (the base's: the judges a candidate is scored by come from there)."""
    return sha([[p.name, sha(p.read_bytes())] for p in sorted((Path(tree) / JUDGES_PATH).glob("*.py"))])


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


def read_deploys(deploy_log: Path) -> list[dict]:
    """The watchdog's deploys.jsonl rows; a line a writer is still appending is skipped."""
    rows = []
    for line in Path(deploy_log).read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def in_session(epoch: float) -> bool:
    """New York's regular session, weekdays 09:30 to 16:05 (a money-path gate never flips on to new behavior then)."""
    try:
        from zoneinfo import ZoneInfo

        local = dt.datetime.fromtimestamp(epoch, ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 - no tz database: New York's summer offset, the stricter reading until Nov 1
        local = dt.datetime.fromtimestamp(epoch, dt.timezone(dt.timedelta(hours=-4)))
    minute = local.hour * 60 + local.minute
    return local.weekday() < 5 and 9 * 60 + 30 <= minute < 16 * 60 + 5


def house_test_hours(epoch: float) -> bool:
    """15:30-16:00 New York on a weekday, while the House test runs (D8: no research-side deploy then)."""
    try:
        from zoneinfo import ZoneInfo

        local = dt.datetime.fromtimestamp(epoch, ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001 - no tz database: New York's summer offset
        local = dt.datetime.fromtimestamp(epoch, dt.timezone(dt.timedelta(hours=-4)))
    minute = local.hour * 60 + local.minute
    return local.weekday() < 5 and 15 * 60 + 30 <= minute < 16 * 60


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


def changes(repo: Path, base: str, head: str) -> list[tuple[str, str, str, str]]:
    """(status, path, old mode, new mode) of every change from `base` to `head`, with renames and copies split into a
    delete and an add (`--no-renames`), so a moved file can never hide its source path."""
    raw = git(repo, "diff", "--raw", "--no-renames", "-z", base, head)
    parts = raw.split("\0")
    out = []
    i = 0
    while i < len(parts) - 1:
        meta = parts[i]
        if not meta.startswith(":"):
            i += 1
            continue
        old_mode, new_mode, _, _, status = meta[1:].split()
        out.append((status[:1], parts[i + 1], old_mode, new_mode))
        i += 2
    return out


def name_status(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    """(status, path) of every change from `base` to `head` as `git diff --no-renames --name-status` lists it: a rename
    or copy is a delete and an add, so a moved file never hides its source path."""
    parts = git(repo, "diff", "--no-renames", "--name-status", "-z", base, head).split("\0")
    out = []
    i = 0
    while i < len(parts) - 1:
        status = parts[i]
        if not status:
            i += 1
            continue
        out.append((status, parts[i + 1]))
        i += 2
    return out


def candidate_tree(repo: Path, base: str, head: str, paths: list[str], target: Path) -> Path:
    """The tree a candidate is judged as: the BASE commit's archive with only its staged files (`paths`, each added or
    modified, never protected: staging refused anything else) laid over it from `head`. So every file the candidate did
    not stage, the judges' imports and the fixed tests included, is the base's by construction; and the result must be
    `head`'s exact release tree (a commit with any other change cannot be the one deployed)."""
    archive(repo, base, target)
    for path in paths:
        destination = target / path
        if ".." in Path(path).parts or Path(path).is_absolute():
            raise ImprovementError(f"{path}: not a path inside the tree")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(git(repo, "show", f"{head}:{path}", binary=True))
    with tempfile.TemporaryDirectory(prefix="harness-head-") as temp:
        archive(repo, head, Path(temp) / "head")
        if release_digest(Path(temp) / "head") != release_digest(target):
            raise ImprovementError("the candidate commit differs from its base beyond its staged files")
    return target


def sandbox(tree: Path, judge: Path, command: list[str], *, python: Path, timeout: int = 600,
            stdin: bytes | None = None) -> dict:
    """No host home, credentials, production state or network. Refuse when namespace isolation is unavailable.
    `stdin` (the judges' per-run nonce) is written to the child's standard input, never its arguments."""
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
             "--setenv", JUDGE_MARKER, "1",
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
        process = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True, preexec_fn=limits,
                                   stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL)
        problem = None
        if stdin is not None:
            try:
                process.stdin.write(stdin)
                process.stdin.close()
            except OSError:
                pass  # the child exited before reading: its answer will not carry the nonce
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
    def __init__(self, root: Path, *, repo: Path = REPO, clock=time.time, heldout: Path | None = None):
        """`heldout`: the private directory of the judges' held-out pools (`harness_lanes.HELDOUT_POOLS`), outside the
        repo and outside any patch author's view; needed only to evaluate a lane candidate."""
        self.root, self.repo, self.clock = Path(root), Path(repo), clock
        self.heldout = None if heldout is None else Path(heldout)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.ledger = Ledger(self.root / "harness.sqlite", clock=clock)
        self.worklist = Worklist(self.ledger, clock=clock)

    def close(self):
        self.ledger.close()

    def pinned(self, base: str) -> None:
        """Refuse to compute anything about a candidate unless this controller's own code (`CONTROLLER`, the judges)
        is the pinned base commit's, byte for byte: so neither a candidate's tree nor an unreviewed edit in the
        operator's checkout decides, judges or measures it. `scripts/harness_improve.py` re-executes itself from a
        separate checkout of the base (`<journal>/controllers/<base>`) when it is not."""
        paths = controller_paths()
        want = base_blobs(self.repo, base, list(CONTROLLER) + [JUDGES_PATH])
        want = {p: v for p, v in want.items() if p in CONTROLLER or p.endswith(".py")}
        have = {}
        for path in sorted(set(paths) | set(want)):
            try:
                have[path] = lanes.blob_sha((REPO / path).read_bytes())
            except OSError:
                continue
        differ = sorted(p for p in set(want) | set(have) if want.get(p) != have.get(p))
        if differ:
            raise ImprovementError(f"the controller is not running the pinned base commit {base[:12]}'s code ({differ[:6]} "
                                   "differ): run it from a checkout of the base (scripts/harness_improve.py re-executes "
                                   "itself from <journal>/controllers/<base>)")

    def measured_by_base(self, measurement: Mapping[str, Any], base: str, what: str = "the measurement") -> None:
        """Refuse a House measurement unless the code that took it (`measure`'s `code`: the repository modules its
        process had loaded, by git blob id) is the pinned base commit's: a candidate's tree, or anything that rewrote the
        measuring code on the House, never measures its own canary."""
        code = measurement.get("code")
        if not isinstance(code, Mapping) or "league/swarm/harness_lanes.py" not in code:
            raise ImprovementError(f"{what} does not say which code took it (`code`): measure again with the base "
                                   "release's scripts/harness_improve.py")
        want = base_blobs(self.repo, base, sorted(str(p) for p in code))
        differ = sorted(str(p) for p, v in code.items() if want.get(str(p)) != v)
        if differ:
            raise ImprovementError(f"{what} was not taken by the pinned base commit {base[:12]}'s code ({differ[:6]} "
                                   "differ): measure with the base release's scripts/harness_improve.py")

    def approved(self, proposal: Mapping[str, Any]) -> dict[str, Any] | None:
        """The latest adversarial review of exactly this patch and this evaluated tree (its release digest), when its
        verdict is approve (`review`)."""
        reviews = [r for r in proposal.get("reviews") or [] if r.get("patch_sha") == proposal.get("patch_sha")
                   and r.get("head") == proposal.get("head") and proposal.get("release_digest")
                   and r.get("release_digest") == proposal.get("release_digest")]
        return reviews[-1] if reviews and reviews[-1].get("verdict") == "approve" else None

    @staticmethod
    def deploys_of(proposal: Mapping[str, Any], rows: list[dict]) -> list[tuple[float, float]]:
        """Each deploy attempt that staged the evaluated tree (`stage` ok with its digest), as (its first watchdog row,
        its verdict's row, or its last row while it has none): when that deploy put the tree on the House."""
        digest = proposal.get("release_digest")
        attempts = {r.get("deploy") for r in rows if r.get("stage") == "stage" and r.get("ok") is True
                    and digest and r.get("digest") == digest and r.get("deploy")}
        times: dict[Any, list[float]] = {}
        verdicts: dict[Any, float] = {}
        for r in rows:
            at = lanes.epoch_of(r.get("at")) if r.get("deploy") in attempts else None
            if at is not None:
                times.setdefault(r.get("deploy"), []).append(at)
                if r.get("stage") == "verdict":
                    verdicts.setdefault(r.get("deploy"), at)
        return sorted((min(t), verdicts.get(d, max(t))) for d, t in times.items())

    @classmethod
    def exposure(cls, proposal: Mapping[str, Any], rows: list[dict]) -> float | None:
        """When the evaluated tree first reached the House: the earliest watchdog row (`start`, before staging) of any
        deploy attempt that staged that exact tree (`stage` ok with its digest), or None when none did."""
        spans = cls.deploys_of(proposal, rows)
        return spans[0][0] if spans else None

    #: A deploy ticket covers a deploy the watchdog starts within this long after it was issued (the deploy step names
    #: the commit to send now, at an hour its release class allows): a later deploy needs a new ticket.
    TICKET_SECONDS = 2 * 3600

    def unreviewed(self, proposal: Mapping[str, Any], rows: list[dict]) -> str | None:
        """MACHINE-CHECKED: why the evaluated tree's exposure on the House is not covered, or None. Every deploy of it
        must come after an approving adversarial review of that exact tree was recorded and within `TICKET_SECONDS` of a
        ticket the loop's deploy step (`deploy`) issued, both on the journal's clock before the watchdog's first row for
        it, and run (its first row to its verdict) wholly outside the hours its release class forbids: New York's session
        for a money-path or evidence-reset tree, 15:30-16:00 New York for a research-side one (the sixth review: the
        deploy step checks the hours when it issues the ticket, this checks when the tree actually went out)."""
        spans = self.deploys_of(proposal, rows)
        if not spans:
            return None
        first = spans[0][0]
        digest = str(proposal.get("release_digest"))[:12]
        review = self.approved(proposal)
        approvals = [float(r["at"]) for r in proposal.get("reviews") or [] if r.get("verdict") == "approve"
                     and r.get("release_digest") == proposal.get("release_digest") and r.get("head") == proposal.get("head")]
        if review is None or not approvals or min(approvals) >= first:
            return (f"the evaluated tree {digest} reached the House ({iso(first)}) before an adversarial review approving "
                    "it was recorded")
        tickets = sorted(float(t["at"]) for t in proposal.get("deploys") or [] if t.get("release_digest") == proposal.get(
            "release_digest"))
        release_class = (proposal.get("classification") or {}).get("release_class") or "research"
        for began, ended in spans:
            covering = [t for t in tickets if t < began]
            if not covering:
                return (f"the evaluated tree {digest} reached the House ({iso(began)}) without the loop's deploy step "
                        "(`deploy KEY`, which checks the approval) before it")
            if began - covering[-1] > self.TICKET_SECONDS:
                return (f"the evaluated tree {digest} reached the House ({iso(began)}) more than "
                        f"{self.TICKET_SECONDS // 3600} hours after its latest deploy ticket ({iso(covering[-1])}): the "
                        "deploy step issues a ticket for a deploy now, at hours it checks")
            minutes = [began + k * 60.0 for k in range(int((ended - began) // 60) + 1)] + [ended]
            if release_class in ("money_path", "evidence_reset") and any(in_session(t) for t in minutes):
                return (f"the {release_class} tree {digest} was deployed in New York's session ({iso(began)} to "
                        f"{iso(ended)}): it deploys only outside 09:30-16:05")
            if release_class == "research" and any(house_test_hours(t) for t in minutes):
                return (f"the evaluated tree {digest} was deployed 15:30-16:00 New York ({iso(began)} to {iso(ended)}), "
                        "while the House test runs")
        return None

    def deploy(self, key: str) -> dict:
        """THE LOOP'S DEPLOY STEP (machine-checked): the only sanctioned route of an evaluated candidate's tree to the
        House. It refuses unless the journal holds an adversarial review approving exactly this patch and this evaluated
        tree (`approved`), and outside the hours its release class allows (a money-path or evidence-reset tree never in
        New York's session; a research-side one never 15:30-16:00 New York, while the House test runs). It records a
        deploy ticket and names the exact commit and tree to send through the watchdog. The release train itself
        (`scripts/floor_box.py`, the watchdog) does not read this journal: a deploy made around this step, or before the
        approval, is caught when the canary is registered (`canary_start`, the scheduler lane's `reconcile`), which
        voids the candidate and asks for a rollback."""
        job = self.worklist.get(key)
        if job is None or job.state != "canary":
            raise ImprovementError("only an evaluated candidate awaiting its canary is deployed (its evaluation passed)")
        proposal = dict(job.carry["_proposal"])
        if proposal.get("canary") or proposal.get("observation"):
            raise ImprovementError("this candidate's canary has already started")
        self.pinned(proposal["base"])
        review = self.approved(proposal)
        if review is None:
            raise ImprovementError(f"no deploy without an adversarial review approving exactly patch "
                                   f"{str(proposal.get('patch_sha'))[:16]} and tree {str(proposal.get('release_digest'))[:12]} "
                                   "(`review`); the journal has none")
        release_class = (proposal.get("classification") or {}).get("release_class") or "research"
        now = self.clock()
        if release_class in ("money_path", "evidence_reset") and in_session(now):
            raise ImprovementError(f"a {release_class} tree deploys only outside New York's session (09:30-16:05)")
        if release_class == "research" and house_test_hours(now):
            raise ImprovementError("no deploy 15:30-16:00 New York, while the House test runs")
        ticket = {"n": len(proposal.get("deploys") or []) + 1, "at": now, "release_digest": proposal["release_digest"],
                  "head": proposal["head"], "review": review["n"], "release_class": release_class}
        proposal["deploys"] = list(proposal.get("deploys") or []) + [ticket]
        rule = (proposal.get("classification") or {}).get("deploy_rule") or lanes.DEPLOY_RULES.get(release_class)
        self.worklist.transition(key, "canary", commit=proposal["head"], attempt=job.attempt,
                                 note=f"Deploy step {ticket['n']}: review {review['n']} approves tree "
                                      f"{proposal['release_digest'][:12]}; deploy commit {proposal['head'][:12]} exactly "
                                      "through the watchdog.", extra={"_proposal": proposal, "deploy_ticket": ticket})
        return {"ticket": ticket, "commit": proposal["head"], "release_digest": proposal["release_digest"],
                "deploy_rule": rule,
                "deploy": (f"from a clean checkout of commit {proposal['head']} (nothing else in league/, ltcm/, playbooks/, "
                           "scripts/ or deploy/), `python3 scripts/floor_box.py deploy`; the watchdog's stage receipt "
                           f"must show digest {proposal['release_digest']}")}

    def review(self, key: str, *, report: Path, reviewer: str, patch_sha: str, review_usd: float | None = None) -> dict:
        """Record an ADVERSARIAL REVIEW of an evaluated candidate's exact patch (`<artifact>/candidate.patch`) and tree
        (its release digest, known once `evaluate` passed). The report must name the patch's sha256 (`patch_sha`) and
        state `VERDICT: approve` or `VERDICT: reject`; the reviewer is a separate agent, never the patch's author
        (`stage --author`). It is kept beside the candidate and recorded in the journal. An approval is what lets the
        deploy step run (`deploy`), and the canary start (lanes) or the observation window open (the scheduler lane); a
        rejection sends the candidate back to revising (or rejects it on its last attempt), with a rollback asked for
        when a deploy ticket was already issued."""
        job = self.worklist.get(key)
        if job is None or job.state != "canary":
            raise ImprovementError("a review is of an evaluated candidate awaiting its deploy (`evaluate` passed): its "
                                   "exact tree is known then")
        proposal = dict(job.carry.get("_proposal") or {})
        if proposal.get("canary") or proposal.get("observation"):
            raise ImprovementError("this candidate's canary has already started: a review comes before the deploy")
        if not proposal.get("release_digest"):
            raise ImprovementError("the candidate has no evaluated tree to review")
        if not proposal.get("patch_sha") or patch_sha != proposal["patch_sha"]:
            raise ImprovementError("the review must name the staged patch's sha256 (`--patch-sha`, the brief's and "
                                   "`next`'s `patch_sha`): it reviewed another diff")
        reviewer = str(reviewer or "").strip()
        if not reviewer:
            raise ImprovementError("name the reviewer (an agent separate from the patch's author)")
        if proposal.get("author") and reviewer.lower() == str(proposal["author"]).strip().lower():
            raise ImprovementError("the patch's author cannot review it: an adversarial review is a separate agent's")
        text = Path(report).read_text(errors="replace")
        if patch_sha not in text and patch_sha[:16] not in text:
            raise ImprovementError("the report does not cite the patch it reviewed (its sha256, or the first 16 hex)")
        verdicts = VERDICT_LINE.findall(text)
        if len(verdicts) != 1:
            raise ImprovementError("the report states exactly one verdict on its own line: `VERDICT: approve` or "
                                   "`VERDICT: reject`")
        verdict = verdicts[0].lower()
        artifact = Path(proposal["artifact"])
        n = len(proposal.get("reviews") or []) + 1
        kept = artifact / f"review-{n}.md"
        kept.write_text(text)
        row = {"n": n, "reviewer": reviewer[:120], "verdict": verdict, "patch_sha": patch_sha, "head": proposal.get("head"),
               "release_digest": proposal["release_digest"], "report": str(kept), "report_sha": sha(text.encode()),
               "at": self.clock()}
        proposal["reviews"] = list(proposal.get("reviews") or []) + [row]
        ticketed = bool(proposal.get("deploys"))
        if verdict == "approve":
            state, note = job.state, (f"Adversarial review {n} by {reviewer[:60]} approved patch {patch_sha[:16]} (tree "
                                      f"{proposal['release_digest'][:12]}); the deploy step (`deploy`) may run.")
        else:
            state = "revising" if job.attempt < self.MAX_ATTEMPTS else "rejected"
            note = (f"Adversarial review {n} by {reviewer[:60]} rejected patch {patch_sha[:16]}: see {kept}"
                    + ("; a deploy ticket was issued: if the tree reached the House, roll it back through the watchdog."
                       if ticketed else ""))
        extra: dict[str, Any] = {"_proposal": proposal, "review": row}
        if verdict == "reject":
            extra["_failure"] = {"phase": "review", "reason": f"rejected by review {n}: {kept}", "rollback": ticketed}
        self.worklist.transition(key, state, commit=proposal.get("head"), attempt=job.attempt, cost_usd=review_usd or 0,
                                 note=note, extra=extra)
        return row

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

    def stage(self, key: str, candidate: str, *, authoring_usd: float | None = None, author: str | None = None) -> dict:
        job = self.worklist.get(key)
        if job is None or job.state not in ("proposed", "admitted", "patching", "revising"):
            raise ImprovementError("candidate needs an open measured bottleneck")
        if not str(author or "").strip():
            # The review's reviewer-is-not-the-author check needs a name to compare (refused before an attempt counts).
            raise ImprovementError("name the patch's author (`stage --author AGENT`): its adversarial reviewer must be "
                                   "another agent")
        if job.details.get("lane"):
            return self._stage_lane(job, candidate, authoring_usd=authoring_usd, author=author)
        base = str(job.details["base"])
        head = None
        attempt = job.attempt + 1
        git(self.repo, "rev-parse", "--verify", f"{base}^{{commit}}")
        self.pinned(base)
        try:
            head = git(self.repo, "rev-parse", "--verify", f"{candidate}^{{commit}}")
            git(self.repo, "merge-base", "--is-ancestor", base, head)
            paths = [path for _, path in name_status(self.repo, base, head)]
            if paths != [SCHEDULER_PATH]:
                raise ImprovementError("scheduler lane may change only league/swarm/loop.py; every other path is protected")
            patch_guard(git(self.repo, "show", f"{base}:{SCHEDULER_PATH}"), git(self.repo, "show", f"{head}:{SCHEDULER_PATH}"))
            with tempfile.TemporaryDirectory(prefix="harness-baseline-") as temp:
                tree = Path(temp) / "base"
                archive(self.repo, base, tree)
                if release_digest(tree) != job.details["source"]["digest"]:
                    raise ImprovementError("baseline commit does not match the measured running release")
                benchmark_sha = sha((tree / BENCHMARK_PATH).read_bytes())
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
                    "baseline": job.details["baseline"], "source": job.details["source"], "judge_sha": benchmark_sha,
                    "regressions": list(REGRESSIONS), "observation_seconds": OBSERVE_SECONDS,
                    "author": (author or "").strip()[:120] or None, "reviews": []}
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
        self.pinned(proposal["base"])
        if (proposal["judge_sha"] != sha(BENCHMARK.read_bytes()) or proposal["policy"] != POLICY
                or proposal["regressions"] != list(REGRESSIONS)):
            raise ImprovementError("the frozen judge changed; register a new candidate under the new protocol")
        artifact = Path(proposal["artifact"])
        judge = artifact / "judge"
        judge.mkdir(exist_ok=True)
        receipt = {"policy": POLICY, "judge_sha": proposal["judge_sha"], "base": proposal["base"], "head": proposal["head"], "trees": {}}
        with tempfile.TemporaryDirectory(prefix="harness-eval-") as temp:
            for name in ("base", "head"):
                tree = Path(temp) / name
                if name == "base":
                    archive(self.repo, proposal["base"], tree)
                    # The benchmark is the BASE tree's, never the candidate's or the operator's checkout.
                    if sha((tree / BENCHMARK_PATH).read_bytes()) != proposal["judge_sha"]:
                        raise ImprovementError("the base tree's benchmark is not the pinned one")
                    (judge / "benchmark.py").write_bytes((tree / BENCHMARK_PATH).read_bytes())
                else:
                    # The candidate is the base tree with only its staged file laid over it.
                    candidate_tree(self.repo, proposal["base"], proposal["head"], [SCHEDULER_PATH], tree)
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
            # read-only measurement only once it has ended and no decision exists yet. The retain/revert decision itself
            # runs only as the pinned base commit's code, checked against the owner's repository (`pinned`,
            # `measured_by_base`): where that repository is absent it refuses, and the owner's machine decides.
            proposal = job.carry.get("_proposal") or {}
            arm = proposal.get("canary") or {}
            rows = read_deploys(deploy_log)
            now = self.clock()
            if proposal.get("observation") or not arm.get("since") or now < float(arm["since"]) + float(proposal["observation_seconds"]):
                light = {"since": float(arm.get("since") or now), "until": now, "deploys": rows, "current": current_release,
                         "source": {}, "lanes": {}}
                return self.reconcile_lane(key, measurement=light)
            # The registered window is measured once (read only) and kept in the journal: a decision that must wait
            # (a money-path gate before the close) re-reads the kept measurement on the next tick, never the House.
            since, until = float(arm["since"]), float(arm["since"]) + float(proposal["observation_seconds"])
            kept = self.root / "windows" / f"{sha([key, since, until])[:24]}.json"
            measurement = None
            try:
                measurement = json.loads(kept.read_text())
            except (OSError, ValueError):
                pass
            if not isinstance(measurement, dict) or measurement.get("since") != since or measurement.get("until") != until:
                measurement = lanes.measure(swarm, since=since, now=until, lanes=[job.details["lane"]], examples=0)
                kept.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                try:
                    write_json(kept, json.loads(json.dumps(measurement, default=str)))
                except ValueError:  # a non-finite figure: decide on this copy now, measure again next time
                    pass
            measurement.update(deploys=rows, current=current_release)
            return self.reconcile_lane(key, measurement=measurement)
        proposal = dict(job.carry["_proposal"])
        rows = read_deploys(deploy_log)
        receipts = watchdog(rows, proposal["release_digest"])
        if "waiting" in receipts:
            return receipts
        stage, attempt, final = receipts["stage"], receipts["attempt"], receipts["final"]
        if receipts["rollback"] or final and final.get("verdict") in ("rolled_back", "refused", "failed"):
            result = {"decision": "reverted" if receipts["rollback"] or final.get("verdict") == "rolled_back" else "rejected",
                      "release": stage.get("release"), "watchdog": final}
            self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt, note="The exact-tree watchdog rejected or reverted the candidate.",
                                     extra={"_proposal": proposal, **result})
            return result
        if not proposal.get("observation"):
            # MACHINE-CHECKED: the tree reached the House only after an approving review and the loop's deploy step.
            problem = self.unreviewed(proposal, rows)
            if problem:
                result = {"decision": "rollback_required", "reason": problem, "release": stage.get("release")}
                proposal["observation"] = result
                self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt,
                                         note=f"{problem}: roll it back through the watchdog; no observation window opens.",
                                         extra={"_proposal": proposal, **result})
                return result
        if not receipts["complete"]:
            return {"waiting": "a complete successful watchdog canary and watch are required"}
        if current_release != stage.get("release"):
            return {"waiting": "the evaluated release is not currently running", "current": current_release}
        if proposal.get("observation"):
            return proposal["observation"]  # one registered observation window; later favorable peeks cannot reverse it
        if self.approved(proposal) is None:
            # MACHINE-CHECKED: the observation window opens only for a tree an adversarial review approved before its
            # deploy (`unreviewed` above); a review recorded later never opens it.
            return {"waiting": f"an adversarial review approving patch {str(proposal.get('patch_sha'))[:16]} is required "
                               "before the deploy and the observation window (`review`, then `deploy`)"}
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
        """Register every lane bottleneck over its predeclared threshold (and paying back a cycle) as a durable
        candidate, ranked. `measurement` is `harness_lanes.measure` of the running House (read only). The same evidence
        twice buys no second attempt."""
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
        # The candidate is bound to the release this document saw running: only a fresh measurement of a live swarm
        # (its heartbeat fresh when measured) may register one. A stale document from an earlier release would bind the
        # candidate to a tree whose deploy rolls the newer release back.
        taken = measurement.get("taken_at")
        if not isinstance(taken, (int, float)) or not 0 <= self.clock() - float(taken) <= FRESH_SECONDS:
            raise ImprovementError(f"the measurement was not taken in the last {FRESH_SECONDS} s: measure the running "
                                   "House again (a capture binds its candidate to the release running now)")
        age = source.get("heartbeat_age")
        if source.get("stopped") or not isinstance(age, (int, float)) or not 0 <= float(age) <= 180:
            raise ImprovementError("the measured swarm had no fresh heartbeat: its running release is not known")
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
            voided = old is not None and old.state == "rejected" and \
                ((old.carry.get("_proposal") or {}).get("observation") or {}).get("decision") == "voided"
            if old is not None and (old.through.get("research", 0) >= through
                                    or (old.state not in ("proposed", "admitted") and not voided)):
                row["state"] = old.state
                out.append(row)
                continue
            # The rules a candidate will be staged, judged and decided by are the base's: so is the code registering it.
            self.pinned(base)
            data = measurement["lanes"][name]
            motivating = lanes.motivating_units(name, data)
            baseline: dict[str, Any] = {"metrics": lanes.lane_metrics(name, data),
                                        "heldout_metrics": lanes.lane_metrics(name, data, exclude=motivating),
                                        "window": measurement["window"], "until": float(measurement["until"]),
                                        "population": dict(data.get("population") or {})}
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
                                          "value": row["value"], "payback": row.get("payback"),
                                          "required_units": row.get("required_units"),
                                          **({"voids": int(old.details.get("voids") or 0) + 1} if voided else {})})
            if voided:
                # A voided comparison judged nothing: the bottleneck, measured again, reopens. The first void does not
                # count against its three attempts; every later one does (a stream of voids, each a deploy and on the
                # execution lane an evidence reset, cannot run on without a decision).
                voids = int(self.worklist.get(key).details.get("voids") or 1)
                free = voids <= 1
                self.worklist.transition(key, "proposed", attempt=max(0, old.attempt - 1) if free else old.attempt,
                                         note=("Reopened on a new measurement after a voided canary"
                                               + (" (the first void: the attempt is not counted)." if free else
                                                  f" (void {voids}: the attempt counts; declare a release freeze over the "
                                                  "next window before its canary).")),
                                         extra={"_proposal": {"reopened_after": "voided", "voids": voids},
                                                "decision": "reopened"})
            row["state"] = self.worklist.get(key).state
            out.append(row)
        return out

    def brief(self, key: str) -> dict[str, Any]:
        """What the patch author may see: the measured bottleneck and its motivating examples, the lane's surface,
        protected paths and frozen symbols, the predeclared metric, the judge's dev split, the gate. Never the held-out
        split's cases or figures."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane"):
            raise ImprovementError("no lane candidate with that key")
        lane = lanes.LANES[job.details["lane"]]
        b = lane.bottleneck(job.details["metric"])
        canary = lane.canary_for(b)
        arms = canary.get("mode") == "arms"
        unit = {"family": 'the family id (`fam["id"]`)',
                "mechanism": "canary.mechanism_unit(mechanism) inside `Architect.admit` (the admitted text: a birth's "
                             'family id does not exist yet), or canary.mechanism_unit(fam["mechanism"]) for a family in '
                             "league/swarm/researcher.py",
                }.get(canary.get("unit")) if arms else None
        where = {"research": "`Researcher._admit` (the check before any Gym run or sweep; the judge screens through it), "
                             "calling new code in preflight.py or new functions",
                 "memory": "`Architect.admit` for admission (refuse a restated idea: never change what an admitted birth "
                           "keeps). An architect prompt is per pass, not per mechanism, so it cannot be an arms candidate"
                 }.get(lane.id)
        gate = ('from league.swarm import canary          # at the top of the module\n'
                f'if canary.enabled("{key}", <unit>, root=<the swarm state directory, e.g. self.store.root>):\n'
                "    ... the new behavior\nelse:\n    ... the old behavior, byte for byte the baseline's code") if arms else None
        frozen = {path: list(names) for path, names in lanes.FROZEN_SYMBOLS.items()
                  if any(fnmatch.fnmatchcase(path, g) for g in lane.surface)}
        return {"key": key, "lane": lane.id, "title": lane.title, "bottleneck": b.summary,
                "metric": {"name": b.metric.name, "is": f"{b.metric.numerator} / {b.metric.denominator}",
                           "direction": b.metric.direction, "must_improve_by": b.metric.min_effect},
                "secondary_must_not_worsen": [m.name for m in b.secondary], "guards_must_not_worsen": [m.name for m in lane.guards],
                "population_guards": [m.name for m in lane.population_guards],
                "measured": job.details.get("baseline", {}).get("metrics"), "stake": job.details.get("stake"),
                "payback": job.details.get("payback"),
                "motivating_examples": job.evidence[:12],
                "surface": list(lane.surface),
                "protected": "machine-checked on the diff's file list: every path in league/swarm/harness_lanes.py "
                             "PROTECTED (the objective and this loop, sealed data and the evaluator, spend limits, capital "
                             "permissions including the real-money order path, the release train) and every path outside "
                             "the surface, whatever the status (git diff --no-renames --name-status: deletions and renames "
                             "included); no mode change and no edit of an existing test. Static defense in depth on top "
                             "(not a guarantee; the review checks what it cannot): no new route to the store, evaluator, "
                             "gate, bands, settings or constitution (an import of one, of a name from or re-exported from "
                             "one, of their parent packages `league` and `league.swarm`, `import league.<anything>`, any "
                             "star import, or an imported module's attribute that reaches one), no mutation or bare "
                             "hand-out of their state (`settings_mod.DEFAULTS[...] = ...`, `.clear()`, `d = "
                             "settings_mod.DEFAULTS`, `f(settings_mod.TRAIN_STARTS)`, a default value, a match subject, a "
                             "loop over `.values()`, a part `.get()` returns; read a setting inline), no import of "
                             "os, subprocess, shutil, socket, pathlib, io, logging, tempfile, importlib or ctypes, nor of a "
                             "process, file or loader module through another module that imports it (`from .loop import "
                             "os`, `loop.os`) or of a module's `__builtins__`; no new use "
                             "(aliased, held as a reference or called) of a process, network, reflection, file-write "
                             "(constructors included) or file-move, print, exit or dynamic-access name, `os` member beyond "
                             "the path helpers, interpreter plumbing, assignment to another object's attribute, store writer "
                             "or reader of the holdout, Validation or forward evidence (counted by NAME on any object: a new "
                             f"`.{'`, `.'.join(sorted(lanes.GENERIC_SEALED))}` on anything is refused, so name your own "
                             "methods otherwise), key naming Validation, raw SQL statement, collaborator's private "
                             "attribute, call through an expression, or new path to a function that writes records; no "
                             "definition under a name existing code uses, no new dunder, no new member of an existing class "
                             "with bases",
                "review": "an adversarial review of your exact patch and evaluated tree by a separate agent, recorded with "
                          "the verdict approve, is required before the deploy step and the canary "
                          "(playbooks/harness-improvement.md, the review checklist)",
                "frozen": {"symbols": frozen,
                           "rule": "every function that writes trial, lineage, look or graveyard records "
                                   f"({', '.join(sorted(lanes.TRIAL_WRITES))}) is frozen whole, except "
                                   + ", ".join(f"{q} (its writes, their conditions and the bindings {', '.join(n)} frozen)"
                                               for (_, q), n in lanes.GUARDED_BINDINGS.items())},
                "judge": {"script": f"league/swarm/harness_judges/{lane.judge}.py", "protocol": lane.protocol,
                          "dev_split": "fixed; readable in the judge file", "primary": b.judge_primary, "mode": b.judge_mode,
                          "must_fall_on_heldout_by": b.judge_effect if b.judge_mode == "improve" else None,
                          "must_be_zero": list(lane.judge_zero), "must_not_rise": list(lane.judge_no_worse),
                          "cost": lane.judge_cost, "cost_rule": lane.judge_cost_rule, "regressions": list(lane.regressions),
                          "gate_runs": "gate forced open (judged) and forced closed (must equal the baseline exactly)"
                                       if arms else None},
                "heldout": "private classes the dev split never uses, kept outside the repo and never shown, drawn from "
                           "a seed that exists only after your commit is staged; you see only pass or fail for it",
                "canary": {**canary, "unit_in_code": unit, "gate": gate, "where": where if arms else None,
                           "rule": ("every change must sit in a gated branch whose else is the baseline's code, or be a new "
                                    "definition, a new plain constant or a new import; the gate is asked about the lane's "
                                    "unit (the one its observer splits); a changed module constant or prose cannot be "
                                    "gated") if arms else "no gate: the window after the release against a fresh "
                                                                    "control window before it"},
                "release_classes": list(lane.release_classes),
                "deploy_rules": {c: lanes.DEPLOY_RULES[c] for c in lane.release_classes},
                "attempts_left": max(0, self.MAX_ATTEMPTS - job.attempt)}

    def _stage_lane(self, job: Any, candidate: str, *, authoring_usd: float | None = None, author: str | None = None) -> dict:
        key, lane = job.key, lanes.LANES[job.details["lane"]]
        bottleneck = lane.bottleneck(job.details["metric"])
        base = str(job.details["base"])
        head = None
        attempt = job.attempt + 1
        if attempt > self.MAX_ATTEMPTS:
            raise ImprovementError(f"this bottleneck has used its {self.MAX_ATTEMPTS} attempts; a new capture on a new base is required")
        canary = lane.canary_for(bottleneck)
        mode = canary.get("mode", "window")
        git(self.repo, "rev-parse", "--verify", f"{base}^{{commit}}")
        self.pinned(base)  # not the candidate's fault: refused before an attempt is counted
        try:
            if job.details.get("lane_sha") != lanes.lane_sha(lane) or job.details.get("policy") != lanes.POLICY:
                raise ImprovementError("the lane's predeclared definition changed after capture; capture again")
            head = git(self.repo, "rev-parse", "--verify", f"{candidate}^{{commit}}")
            git(self.repo, "merge-base", "--is-ancestor", base, head)
            # MACHINE-CHECKED first: any protected path touched, a deletion or either side of a rename included.
            touched = lanes.protected_touch(name_status(self.repo, base, head))
            if touched:
                raise ImprovementError(f"the candidate touches protected paths {touched[:6]}; every lane's candidate is "
                                       "refused there")
            entries = changes(self.repo, base, head)
            for status, path, old_mode, new_mode in entries:
                if status not in ("M", "A"):
                    raise ImprovementError(f"{path}: a lane candidate only modifies or adds files ({status}: no delete, "
                                           "rename, copy or type change)")
                if new_mode != "100644" or (status == "M" and old_mode != new_mode):
                    raise ImprovementError(f"{path}: mode {old_mode} -> {new_mode}: only regular, non-executable files")
                if fnmatch.fnmatchcase(path, lanes.NEW_TEST) and status != "A":
                    # An earlier candidate's test guards the behavior it retained: no later candidate may weaken it.
                    raise ImprovementError(f"{path}: a candidate adds a test file of its own; it never edits an existing "
                                           "one (an earlier candidate's included)")
            paths = [path for _, path, _, _ in entries]
            lanes.surface_check(lane, paths)
            gates = 0
            # Re-exports resolve over each side's own tree: the base's for the baseline, the candidate's for the change.
            read_base, read_head = commit_reader(self.repo, base), commit_reader(self.repo, head)
            for path in paths:
                after = git(self.repo, "show", f"{head}:{path}")
                try:
                    before = git(self.repo, "show", f"{base}:{path}")
                except ImprovementError:
                    before = None
                lanes.content_guard(path, before, after, read_before=read_base, read_after=read_head)
                lanes.symbol_guard(path, before, after)
                if mode == "arms" and not fnmatch.fnmatchcase(path, lanes.NEW_TEST):
                    gates += lanes.gate_coverage(path, before, after, key, canary.get("unit"))
            if mode == "arms" and not gates:
                raise ImprovementError(f"the {lane.id} lane's canary gates the change per {canary.get('unit')}: "
                                       f'`if canary.enabled("{key}", <unit>, root=...):` in a surface module (see the brief)')
            with tempfile.TemporaryDirectory(prefix="harness-baseline-") as temp:
                tree = Path(temp) / "base"
                archive(self.repo, base, tree)
                if release_digest(tree) != job.details["source"]["digest"]:
                    raise ImprovementError("baseline commit does not match the measured running release")
                classification = lanes.classify(paths, lanes.live_path_modules(tree))
                # The judges the candidate is scored by are the BASE tree's (never the candidate's, never the operator's
                # checkout): pinned by hash here, copied from the base tree at evaluation.
                judge_sha = tree_judges_sha(tree)
            if classification["release_class"] not in lane.release_classes:
                raise ImprovementError(f"a {classification['release_class']} change is outside the {lane.id} lane "
                                       f"({list(lane.release_classes)}): {classification['paths']}")
            pays = lanes.payback(lane, job.details.get("stake") or {}, classification["release_class"])
            if pays["pays"] is False:
                raise ImprovementError(f"{pays['why']}: keep the change {min(lane.release_classes, key=lambda c: lanes.CYCLE_USD[c])}"
                                       f" (outside the modules the live path loads) or leave this bottleneck")
        except (ImprovementError, SyntaxError, OSError) as exc:
            self.worklist.transition(key, "revising" if attempt < self.MAX_ATTEMPTS else "rejected", attempt=attempt, commit=head,
                                     note=f"Candidate preflight refused: {exc}", cost_usd=authoring_usd or 0,
                                     extra={"_failure": {"phase": "stage", "candidate": head or str(candidate)[:100],
                                                         "base": base, "reason": str(exc)[:1000]}})
            raise ImprovementError(str(exc)) from exc
        artifact = self.root / "candidates" / sha([key, head])[:20]
        artifact.mkdir(parents=True, exist_ok=True)
        patch = git(self.repo, "diff", "--binary", "--no-renames", base, head, binary=True)
        (artifact / "candidate.patch").write_bytes(patch)
        proposal = {"base": base, "head": head, "artifact": str(artifact.resolve()), "patch_sha": sha(patch),
                    "policy": lanes.POLICY, "lane": lane.id, "metric": bottleneck.metric.name, "lane_sha": lanes.lane_sha(lane),
                    "judge_sha": judge_sha, "protocol": lane.protocol, "regressions": list(lane.regressions),
                    "classification": classification, "canary_mode": mode, "gates": gates, "payback": pays,
                    "observation_seconds": int(canary.get("observe_seconds", OBSERVE_SECONDS)),
                    "baseline": job.details["baseline"], "source": job.details["source"], "paths": paths,
                    "author": (author or "").strip()[:120] or None, "reviews": [],
                    "cost": {"authoring_usd": authoring_usd}}
        self.worklist.transition(key, "testing", commit=head, attempt=attempt, cost_usd=authoring_usd or 0,
                                 note=f"Patch pinned inside the {lane.id} surface ({classification['release_class']}); "
                                      "isolated evaluation on the dev and held-out splits is owed.",
                                 extra={"_proposal": proposal})
        return proposal

    def _evaluate_lane(self, job: Any, *, python: Path) -> dict:
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        bottleneck = lane.bottleneck(proposal["metric"])
        self.pinned(proposal["base"])
        if (proposal["judge_sha"] != judges_sha() or proposal["lane_sha"] != lanes.lane_sha(lane)
                or proposal["policy"] != lanes.POLICY or proposal["regressions"] != list(lane.regressions)):
            raise ImprovementError("the frozen judge or lane changed; register a new candidate under the new protocol")
        pool = self.heldout_pool(lane)
        artifact = Path(proposal["artifact"])
        judge = artifact / "judge"
        judge.mkdir(exist_ok=True)
        seed = lanes.heldout_seed(self.secret(), job.key, proposal["head"])
        arms = proposal["canary_mode"] == "arms"
        receipt: dict[str, Any] = {"policy": lanes.POLICY, "lane": lane.id, "metric": proposal["metric"],
                                   "judge_sha": proposal["judge_sha"], "base": proposal["base"], "head": proposal["head"],
                                   "heldout_seed": seed, "trees": {}}

        def judged(tree: Path, split: str, gate: str) -> dict[str, Any]:
            nonce = secrets.token_hex(16)
            command = [f"/judge/{lane.judge}.py", "--split", split, "--seed", seed, "--nonce-stdin"]
            stdin = (nonce + "\n").encode()
            if split == "heldout":
                # The private pool rides on standard input, after the nonce, held-out runs only: it is never a file in
                # the sandbox, the judge reads it before the tree's code loads, and nothing of it is kept.
                command.append("--pool-stdin")
                stdin += pool + b"\n"
            if gate != "none":
                command += ["--gate", gate, "--key", job.key]
            result = sandbox(tree, judge, command, python=python, stdin=stdin)
            try:
                metrics = json.loads(result["stdout"].splitlines()[-1]) if result["exit"] == 0 else None
            except (ValueError, IndexError):
                metrics = None
            # The last line only, with this run's nonce: a line the tree's code printed cannot pass for the answer.
            if not isinstance(metrics, dict) or metrics.get("nonce") != nonce or metrics.get("protocol") != lane.protocol \
                    or metrics.get("split") != split or metrics.get("provider_calls") != 0 or metrics.get("gate") != gate:
                metrics = None
            if split == "heldout":
                # The author sees only pass or fail for the held-out split: no per-class detail and no output of the
                # run (the tree's code could print what it saw) is kept.
                result = {k: v for k, v in result.items() if k not in ("stdout", "stderr")}
                if metrics is not None:
                    metrics = {k: v for k, v in metrics.items() if not isinstance(v, (dict, list))}
            return {"benchmark": result, "metrics": metrics}

        def tested(tree: Path, gate: str) -> dict[str, Any]:
            if gate == "none":
                return sandbox(tree, judge, ["-m", "unittest", *proposal["regressions"], "-q"], python=python)
            # With the gate open, the tests the lever supersedes are skipped (they pin the old admission it changes);
            # closed, every one runs.
            skips = [x for t in lane.supersedes for x in ("--skip", t)] if gate == "open" else []
            return sandbox(tree, judge, ["/judge/_regress.py", "--gate", gate, "--key", job.key, *skips, "--",
                                         *proposal["regressions"]], python=python)

        runs = [("base", "base", "none")] + ([("head", "closed", "closed"), ("head", "open", "open")] if arms
                                             else [("head", "head", "none")])
        with tempfile.TemporaryDirectory(prefix="harness-eval-") as temp:
            trees = {"base": Path(temp) / "base", "head": Path(temp) / "head"}
            archive(self.repo, proposal["base"], trees["base"])
            # The judges are the BASE tree's (pinned at staging), never the candidate's or the operator's checkout.
            if tree_judges_sha(trees["base"]) != proposal["judge_sha"]:
                raise ImprovementError("the base tree's judges are not the pinned ones")
            for source in sorted((trees["base"] / JUDGES_PATH).glob("*.py")):
                (judge / source.name).write_bytes(source.read_bytes())
            # The candidate is the base tree with only its staged surface files laid over it: every protected file the
            # judges import (the gate, the store, the Gym) and every fixed test is the base's by construction.
            staged = proposal.get("paths") or [p for _, p, _, _ in changes(self.repo, proposal["base"], proposal["head"])]
            candidate_tree(self.repo, proposal["base"], proposal["head"], list(staged), trees["head"])
            for commit, label, gate in runs:
                receipt["trees"][label] = {"splits": {split: judged(trees[commit], split, gate) for split in ("dev", "heldout")},
                                           "regressions": tested(trees[commit], gate), "gate": gate}
            head_digest = release_digest(trees["head"])
            receipt["trees"]["base"]["release_digest"] = release_digest(trees["base"])
        verdict = lanes.judge_verdict(lane, bottleneck, receipt["trees"])
        passed = verdict["passed"]
        cpu = sum(float((t.get("regressions") or {}).get("cpu_seconds") or 0.0)
                  + sum(float(((s.get("benchmark") or {}).get("cpu_seconds")) or 0.0) for s in t["splits"].values())
                  for t in receipt["trees"].values())
        receipt.update(passed=passed, verdict=verdict, release_digest=head_digest,
                       limitations="Synthetic fixed benchmark; its held-out split is private classes the dev split never "
                                   "uses, kept outside the repo (pinned by hash), seeded after the commit. Retention still "
                                   "needs the exact-tree deployment, the canary and the registered observation window.",
                       cost_accounting={"provider_calls": 0, "sandbox_cpu_seconds": round(cpu, 3),
                                        "authoring_usd": (proposal.get("cost") or {}).get("authoring_usd"),
                                        "note": "Authoring and review dollars are what the operator reported at each step "
                                                "(stage --authoring-usd, canary --deploy-usd); unknown when not reported."})
        (artifact / "evaluation.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n")
        proposal.update(evaluation_sha=sha(json.loads(json.dumps(receipt, default=str))), release_digest=head_digest,
                        evaluation={"passed": passed, "public_reasons": verdict["public_reasons"]})
        state = "canary" if passed else ("revising" if job.attempt < self.MAX_ATTEMPTS else "rejected")
        self.worklist.transition(job.key, state, commit=proposal["head"], attempt=job.attempt,
                                 note=("Fixed benchmark (gate open and closed), held-out split and regressions passed; "
                                       f"exact-tree deployment under the {proposal['classification']['release_class']} rule, "
                                       "then the canary, is owed." if passed else
                                       "Not demonstrated under the frozen judge: " + "; ".join(verdict["public_reasons"])[:1500]),
                                 extra={"_proposal": proposal, "decision": "await_canary" if passed else "reject",
                                        "_failure": None if passed else {"phase": "evaluate",
                                                                         "reason": "; ".join(verdict["public_reasons"])[:1000]}})
        return receipt

    def heldout_pool(self, lane: Any) -> bytes:
        """The lane's private held-out pool, checked against its pinned hash (`Lane.heldout_pool`)."""
        if not re.fullmatch(r"[0-9a-f]{64}", lane.heldout_pool or ""):
            raise ImprovementError(f"the {lane.id} lane has no pinned held-out pool")
        if self.heldout is None:
            raise ImprovementError("evaluation needs the private held-out pools (`--heldout DIR`, outside the repo)")
        path = self.heldout / f"{lane.judge}.json"
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ImprovementError(f"the {lane.id} lane's held-out pool is missing ({path}): restore it from its backup; "
                                   "never regenerate it (a new pool is a new lane definition)") from exc
        if sha(raw) != lane.heldout_pool:
            raise ImprovementError(f"the {lane.id} lane's held-out pool at {path} is not the pinned one: restore it from "
                                   "its backup; never regenerate it")
        try:
            json.loads(raw)
        except ValueError as exc:
            raise ImprovementError(f"the {lane.id} lane's held-out pool is not JSON") from exc
        return b" ".join(raw.split(b"\n"))  # one line on the judge's standard input

    def _write_arm(self, key: str, arm: Mapping[str, Any] | None) -> Path:
        """Set (or with None remove) one key's arm in `<root>/canary.json`, the file the gate reads (`canary.FILE`)."""
        from . import canary as gate

        path = self.root / "canary.json"
        arms = gate.read(path)
        if arm is None:
            arms.pop(key, None)
        else:
            arms[key] = dict(arm)
        write_json(path, {"schema": gate.SCHEMA, "arms": arms})
        return path

    def _session_bound(self, proposal: Mapping[str, Any]) -> bool:
        """A gate in code the live path loads (or an evidence reset) turns new behavior on only outside the session."""
        return ((proposal.get("classification") or {}).get("release_class") in ("money_path", "evidence_reset")
                and in_session(self.clock()))

    def canary_start(self, key: str, *, measurement: Mapping[str, Any], fraction: float | None = None,
                     control: Mapping[str, Any] | None = None, deploy_usd: float | None = None) -> dict:
        """Start the registered observation once the exact evaluated tree is deployed and promoted by the watchdog: open
        the gate for `fraction` of the lane's units (arms), or date the before/after window against `control`, a fresh
        measurement of the base release over the observation length just before the deploy that does not overlap the
        capture (window). First, in every lane, the watchdog's receipts must show the tree reaching the House only after
        an approving review and the deploy step's ticket (`unreviewed`): otherwise the candidate is voided and its
        release must be rolled back."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane") or job.state != "canary":
            raise ImprovementError("the candidate is not awaiting its canary")
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        bottleneck = lane.bottleneck(proposal["metric"])
        canary = lane.canary_for(bottleneck)
        self.pinned(proposal["base"])
        self.measured_by_base(measurement, proposal["base"])
        if control is not None:
            self.measured_by_base(control, proposal["base"], "the control measurement")
        rows = list(measurement.get("deploys") or [])
        # MACHINE-CHECKED, in every lane: the evaluated tree reached the House only after an adversarial review approving
        # exactly it was recorded and the loop's deploy step issued its ticket (`unreviewed`). A deploy before either
        # voids the candidate, and its release must be rolled back: no canary is registered on unreviewed code.
        problem = self.unreviewed(proposal, rows)
        if problem:
            return self._void(job, proposal, f"{problem}: roll it back through the watchdog", gated=False, rollback=True)
        if self.approved(proposal) is None:
            raise ImprovementError(f"the canary needs an adversarial review of patch {str(proposal.get('patch_sha'))[:16]} "
                                   "recorded with the verdict approve (`review KEY --report R --reviewer NAME "
                                   "--patch-sha SHA`), then the deploy step (`deploy KEY`); none is")
        if not proposal.get("deploys"):
            raise ImprovementError("the canary needs the loop's deploy step first (`deploy KEY`: it checks the approval "
                                   "and issues the ticket the tree is deployed under)")
        receipts = watchdog(rows, proposal["release_digest"])
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
        mode = proposal["canary_mode"]
        if proposal.get("lane_sha") != lanes.lane_sha(lane):
            return self._void(job, proposal, "the lane's predeclared definition or rules changed after the capture",
                              gated=False)
        # The deploy must have replaced the measured base: a candidate captured on an older release (a stale
        # measurement) and deployed over a newer one rolled that release back.
        replaced = next((r.get("current") for r in receipts["attempt"] if r.get("stage") == "start"), None)
        staged = [r for r in measurement.get("deploys") or [] if r.get("stage") == "stage" and r.get("ok") is True
                  and r.get("release") == replaced and r.get("digest")]
        if replaced and staged and staged[-1]["digest"] != (proposal.get("source") or {}).get("digest"):
            return self._void(job, proposal, f"the evaluated tree replaced release {replaced}, not the measured base: "
                              f"roll back to {replaced} through the watchdog (the candidate was built on an older release)",
                              gated=False)
        promoted = lanes.epoch_of(final.get("at")) or float(measurement["until"])
        window = float(proposal["observation_seconds"])
        if mode == "arms":
            if self._session_bound(proposal):
                return {"waiting": "a money-path gate opens only outside New York's session (09:30-16:05): start it after "
                                   "the close"}
            share = float(fraction if fraction is not None else canary.get("fraction", 0.25))
            if not 0.05 <= share <= 0.5:
                raise ImprovementError("a canary arm holds between 5% and 50% of the units: the rest are the control")
            # The arm opens when the file is installed; two minutes' allowance for that, then the window runs.
            arm = {"lane": lane.id, "mode": mode, "fraction": share, "salt": secrets.token_hex(8), "state": "canary",
                   "since": round(max(promoted, float(measurement["until"])) + 120.0, 3), "release": release,
                   "release_digest": proposal["release_digest"], "deploy": receipts["stage"].get("deploy")}
            path = self._write_arm(key, arm)
        else:
            began = min((lanes.epoch_of(r.get("at")) or promoted for r in receipts["attempt"]), default=promoted)
            if control is None:
                return {"waiting": "a window canary needs its control: on the House, `measure --since S --until U` of the "
                                   f"base release over the {window:.0f} s just before the deploy (U <= {iso(began)}), "
                                   "then `canary KEY --measurement m.json --control control.json`"}
            capture_until = float((proposal.get("baseline") or {}).get("until") or 0.0)
            c_since, c_until = float(control.get("since") or 0.0), float(control.get("until") or 0.0)
            if control.get("schema") != lanes.SCHEMA or control.get("policy") != lanes.POLICY:
                raise ImprovementError("the control is not a harness-lanes-1 measurement")
            if abs((c_until - c_since) - window) > 60 or c_until > began + 60:
                raise ImprovementError(f"the control must be the {window:.0f} s just before the deploy began "
                                       f"({iso(began)}); it is {iso(c_since)} to {iso(c_until)}")
            if c_since < capture_until - 60:
                raise ImprovementError("the control window overlaps the capture window, which was chosen for being bad "
                                       "(regression to the mean would favor retention): the deploy must wait until "
                                       f"{iso(capture_until + window)}")
            if (control.get("source") or {}).get("digest") != proposal["source"].get("digest"):
                raise ImprovementError("the control window did not run the base release")
            if any(c_since < s < c_until for s in (control.get("starts") or [])) and canary.get("unit") != "restart":
                raise ImprovementError("the swarm restarted inside the control window: measure another one")
            data = (control.get("lanes") or {}).get(lane.id) or {}
            extras = ("runs", "error_runs", "restarts", "restart_failures", "live_errors", "restarts_or_one")
            proposal["control"] = {"units": data.get("units") or {}, "window": control.get("window"),
                                   "extra": {k: v for k, v in lanes.lane_tallies(lane.id, data).items() if k in extras},
                                   "population": dict(data.get("population") or {}), "sha": sha(control)}
            need = job.details.get("required_units")
            if canary.get("unit") == "restart":
                cap = int(canary.get("max_units", 60))
                need = lanes.required_units(proposal["control"]["extra"], bottleneck.metric, alpha=ALPHA, cap=cap)
                if need is None:
                    extra = proposal["control"]["extra"]
                    return self._void(job, proposal, f"the control window's restarts ({int(extra.get('restart_failures') or 0)} "
                                      f"failed of {int(extra.get('restarts') or 0)}) cannot show a fall with at most {cap} "
                                      "deliberate restarts on the exact test: roll the candidate back or keep it through a "
                                      "new capture", gated=False)
                need = max(need, int(canary.get("min_units_per_arm", 1)))
            proposal["required_units"] = need
            arm = {"lane": lane.id, "mode": mode, "since": round(promoted, 3), "release": release,
                   "release_digest": proposal["release_digest"], "deploy": receipts["stage"].get("deploy")}
            path = None
        proposal["canary"] = arm
        proposal.setdefault("cost", {})["deploy_usd"] = deploy_usd
        self.worklist.transition(key, "observing", commit=proposal["head"], attempt=job.attempt, cost_usd=deploy_usd or 0,
                                 note=f"Canary started ({mode}); the registered window ends {iso(arm['since'] + window)}.",
                                 extra={"_proposal": proposal})
        out = {"started": arm, "window_until": arm["since"] + window}
        if proposal.get("required_units"):
            out["required_units"] = proposal["required_units"]
        if path is not None:
            out["gate_file"] = str(path)
            out["install"] = ("the House gate reads <swarm-state>/harness/canary.json: when this journal is not that "
                              "directory, replace that file atomically (mode 0600) with this one within two minutes")
        return out

    def _void(self, job: Any, proposal: dict, reason: str, *, gated: bool, rollback: bool = False) -> dict:
        """Record that the registered comparison cannot be judged (`voided`): a gate flips back; a window lane's code
        stays deployed for the operator to roll back or keep through a new capture (`rollback`: it must be rolled
        back, whatever the lane: it reached the House unreviewed). The next capture reopens the bottleneck without
        counting the attempt (`capture_lanes`)."""
        arm = proposal.get("canary") or {}
        if gated and arm:
            self._write_arm(job.key, {**arm, "state": "reverted"})
        result = {"decision": "voided", "reason": reason, **({"rollback": True} if rollback else {})}
        proposal["observation"] = result
        self.worklist.transition(job.key, "rejected", commit=proposal.get("head"), attempt=job.attempt,
                                 note=f"Voided: {reason}. " + ("The gate is flipped back. " if gated and arm else "")
                                      + "A new capture may register the bottleneck again.",
                                 extra={"_proposal": proposal, "decision": "voided"})
        return result

    def canary_stop(self, key: str, *, state: str = "reverted", commit: str | None = None) -> dict:
        """By hand: flip a gate back to the old behavior at once (`reverted`, any time); re-install a gate the
        registered decision retained (`retained`, never instead of that decision); or record that a retained change
        graduated into main with its gate removed (`graduated`, `commit` the main commit), which drops its arm."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane"):
            raise ImprovementError("no lane candidate with that key")
        if state not in ("reverted", "retained", "graduated"):
            raise ImprovementError("a gate is reverted, retained or graduated")
        proposal = dict(job.carry.get("_proposal") or {})
        arm = dict(proposal.get("canary") or {})
        decision = (proposal.get("observation") or {}).get("decision")
        if arm.get("mode") != "arms" and state != "graduated":
            raise ImprovementError("this candidate has no gate to flip: roll it back through the watchdog")
        if state == "retained":
            if decision != "retained":
                raise ImprovementError(f"only the registered decision retains a gate (it is {decision or 'not made'}): "
                                       "an operator may revert at any time, never retain")
            if self._session_bound(proposal):
                raise ImprovementError("a money-path gate turns new behavior on only outside New York's session")
            path = self._write_arm(key, {**arm, "state": "retained"})
            self.worklist.transition(key, "verified", commit=proposal.get("head"), attempt=job.attempt,
                                     note="Operator re-installed the retained gate.", extra={"_proposal": proposal})
            return {"gate": "retained", "gate_file": str(path)}
        if state == "graduated":
            if decision != "retained" or job.state != "verified":
                raise ImprovementError("only a retained change graduates")
            if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ImprovementError("graduation names the full main commit that carries the change without its gate")
            proposal["graduated"] = {"commit": commit, "at": self.clock()}
            gated = arm.get("mode") == "arms"
            path = self._write_arm(key, None) if gated else None
            self.worklist.transition(key, "verified", commit=proposal.get("head"), attempt=job.attempt,
                                     note=(f"Graduated into main at {commit[:12]} without its gate; the arm is dropped."
                                           if gated else f"Merged into main at {commit[:12]}."),
                                     extra={"_proposal": proposal, "decision": "graduated"})
            return {"gate": "graduated", "commit": commit, "gate_file": None if path is None else str(path)}
        arm.update(state="reverted", flipped_at=self.clock())
        proposal["canary"] = arm
        path = self._write_arm(key, arm)
        self.worklist.transition(key, "rejected", commit=proposal.get("head"), attempt=job.attempt,
                                 note="Operator flipped the gate back: the old behavior for every unit.",
                                 extra={"_proposal": proposal, "decision": "withdrawn" if decision == "retained" else "gate_reverted"})
        return {"gate": "reverted", "gate_file": str(path)}

    def reconcile_lane(self, key: str, *, measurement: Mapping[str, Any]) -> dict:
        """The registered decision on the window [canary since, since + observation_seconds), measured once that window
        has ended: the canary arm against the concurrent control arm with the motivating units excluded (arms), or the
        window against the fresh control window before the deploy (window). Computed once; a later measurement never
        reopens it. Another release promoted, or (window) the swarm restarted, inside the window voids it."""
        job = self.worklist.get(key)
        if job is None or not job.details.get("lane") or job.state not in ("canary", "observing", "verified"):
            raise ImprovementError("the candidate is not awaiting or following a canary")
        proposal = dict(job.carry["_proposal"])
        lane = lanes.LANES[proposal["lane"]]
        bottleneck = lane.bottleneck(proposal["metric"])
        receipts = watchdog(list(measurement.get("deploys") or []), proposal["release_digest"])
        final = receipts.get("final") or {}
        arm = proposal.get("canary")
        gated = (arm or {}).get("mode") == "arms"
        if "waiting" not in receipts and (receipts["rollback"] or final.get("verdict") in ("rolled_back", "refused", "failed")):
            result = {"decision": "reverted", "release": receipts["stage"].get("release"), "watchdog": final}
            if gated:
                self._write_arm(key, {**arm, "state": "reverted"})
            self.worklist.transition(key, "rejected", commit=proposal["head"], attempt=job.attempt,
                                     note="The watchdog rolled the candidate's release back.", extra={"_proposal": proposal, **result})
            return result
        if proposal.get("observation"):
            return proposal["observation"]
        if not arm:
            return {"waiting": "the canary has not started: run the canary step"}
        since, window = float(arm["since"]), float(proposal["observation_seconds"])
        end = since + window
        if self.clock() < end:
            return {"waiting": "the registered window has not ended", "until": iso(end)}
        if abs(float(measurement["since"]) - since) > 60 or abs(float(measurement["until"]) - end) > 60:
            return {"waiting": "measure exactly the registered window", "since": since, "until": end}
        if float(measurement.get("taken_at") or 0.0) < end - 60:
            return {"waiting": "the measurement was not taken after the window ended (release B's `measure` records when)"}
        # The retain/revert decision runs from the pinned base commit, on a measurement the base's code took.
        self.pinned(proposal["base"])
        self.measured_by_base(measurement, proposal["base"])
        others = sorted({str(r.get("deploy")) for r in measurement.get("deploys") or []
                         if r.get("stage") == "verdict" and r.get("verdict") == "promoted" and r.get("deploy") != arm.get("deploy")
                         and since < (lanes.epoch_of(r.get("at")) or 0.0) < end})
        # A start inside the window that ran another release (a switch with no promoted verdict, a manual rollback): the
        # candidate's code was not what ran. A restart of the candidate's own release changes no code: not a void.
        starts = measurement.get("start_releases")
        if starts is not None:
            foreign = sorted({str(s.get("release")) for s in starts
                              if since < float(s.get("at") or 0.0) < end and s.get("release") != arm.get("release")})
        else:
            # An older measurement names no start's release: any start inside a before/after window voids it, as does a
            # swarm started inside the window when no start was read at all.
            began = float((measurement.get("source") or {}).get("started_at") or 0.0)
            restarted = [s for s in (measurement.get("starts") or []) if since < float(s) < end] or (
                [began] if measurement.get("starts") is None and since < began < end else [])
            restarts_are_units = lane.canary_for(bottleneck).get("unit") == "restart"
            foreign = ["unknown"] if restarted and arm["mode"] == "window" and not restarts_are_units else []
        void = (f"another release ({', '.join(others)[:200]}) was promoted inside the registered window" if others else
                f"the swarm ran another release ({', '.join(foreign)[:200]}) inside the registered window" if foreign else
                "the lane's predeclared definition or rules changed during the canary"
                if proposal.get("lane_sha") != lanes.lane_sha(lane) else None)
        data = (measurement.get("lanes") or {}).get(lane.id)
        if void is None and not isinstance(data, Mapping):
            return {"waiting": f"the measurement has no {lane.id} lane"}
        seed = sha([key, arm.get("salt") or arm["since"]])
        extras = ("runs", "error_runs", "restarts", "restart_failures", "live_errors", "restarts_or_one")
        motivating = job.details.get("motivating") or []
        if void is not None:
            result: dict[str, Any] = {"decision": "voided", "reason": void}
        elif gated:
            treated, control = lanes.split_arms(data.get("units") or {}, key=key, salt=arm["salt"], fraction=arm["fraction"],
                                                exclude=list(motivating) + list(lane.arm_exclude), needs=lane.arm_needs)
            result = lanes.retention(lane, bottleneck, treated, control, seed=seed, alpha=ALPHA,
                                     population=(lanes.lane_tallies(lane.id, {"population": data.get("population")}),
                                                 dict((proposal.get("baseline") or {}).get("population") or {})),
                                     fraction=float(arm["fraction"]))
        else:
            # Before/after: the window after the release against the fresh control window just before it (never the
            # capture's, which was chosen for being bad). Both are later than every motivating row: held out by time.
            motivating = []
            before = proposal.get("control") or {}
            treated = dict(data.get("units") or {})
            control = dict(before.get("units") or {})
            after = {k: v for k, v in lanes.lane_tallies(lane.id, data).items() if k in extras}
            result = lanes.retention(lane, bottleneck, treated, control, seed=seed, alpha=ALPHA,
                                     extra_treated=after or None, extra_control=dict(before.get("extra") or {}) or None,
                                     population=(lanes.lane_tallies(lane.id, {"population": data.get("population")}),
                                                 dict(before.get("population") or {})),
                                     min_units=proposal.get("required_units"))
        if result["decision"] == "retained" and gated and self._session_bound(proposal):
            # The window is fixed, so deciding after the close gives the same answer; only the flip waits.
            return {"waiting": "a money-path gate turns new behavior on for everyone only outside New York's session "
                               "(09:30-16:05): reconcile after the close"}
        result.update(release=arm["release"], window={"since": iso(since), "until": iso(end)}, mode=arm["mode"],
                      motivating_excluded=len(motivating), measurement_sha=sha(dict(measurement)),
                      limitations="Operational evidence of the harness change, not strategy alpha or profitability.")
        if result["decision"] == "voided":
            if gated:
                self._write_arm(key, {**arm, "state": "reverted"})
            state = "rejected"
            note = (f"Voided: {void}. The comparison cannot be judged; " + ("the gate is flipped back. " if gated else
                    "roll the candidate back or keep it through a new capture. ") + "A new capture may register it again.")
        elif result["decision"] == "retained":
            if gated:
                self._write_arm(key, {**arm, "state": "retained"})
            state, note = "verified", ("The canary beat its predeclared metric against the control; the gate is retained "
                                       "until the change graduates into main." if gated else
                                       "The window beat its predeclared metric against the control window; retained.")
        elif result["decision"] == "revert_recommended" and gated:
            self._write_arm(key, {**arm, "state": "reverted"})
            result["decision"] = "reverted"
            state, note = "rejected", "The canary did not beat its predeclared metric; the gate is flipped back (old behavior)."
        elif result["decision"] == "revert_recommended":
            state, note = "observing", "Rollback recommended; the operator must execute it and the watchdog confirm it."
        else:
            # Too little activity: nothing supports the change, so it fails closed (the gate flips back; a window
            # lane's release is rolled back by the operator through the watchdog).
            if gated:
                self._write_arm(key, {**arm, "state": "reverted"})
            state, note = ("rejected" if gated else "observing",
                           "Too little activity in the registered window; no retention and no fresh peek"
                           + (": the gate is flipped back." if gated else
                              ": rollback recommended; the operator must execute it and the watchdog confirm it."))
        proposal["observation"] = result
        self.worklist.transition(key, state, commit=proposal["head"], attempt=job.attempt, note=note,
                                 extra={"_proposal": proposal, "decision": result["decision"]})
        return result

    def next_steps(self, *, root: str = "<journal>", repo: str = "<owner repo>") -> list[dict]:
        """One command per open lane candidate: the next step the operator runs (the playbook's procedure)."""
        cli = f"python scripts/harness_improve.py --root {root} --repo {repo}"
        out = []
        for job in sorted((j for j in self.worklist.jobs().values() if j.details.get("lane")),
                          key=lambda j: (int(j.details.get("rank") or 99), j.key)):
            p = job.carry.get("_proposal") or {}
            # On the House, measure with the BASE release's code (the watchdog keeps it for rollback): the controller
            # refuses a measurement whose code is not the base's (`measured_by_base`).
            release = str((job.details.get("source") or {}).get("release") or "/workspace/releases/<the base release>")
            house = f"python -B {release.rstrip('/')}/scripts/harness_improve.py measure --swarm /workspace/state"
            lane = lanes.LANES[job.details["lane"]]
            b = lane.bottleneck(job.details["metric"])
            mode = lane.canary_for(b).get("mode")
            obs = float(lane.canary_for(b).get("observe_seconds", OBSERVE_SECONDS))
            step = {"key": job.key, "lane": lane.id, "metric": job.details["metric"], "state": job.state, "attempt": job.attempt}
            decision = (p.get("observation") or {}).get("decision") or job.last_status.get("decision")
            if job.state in ("proposed", "admitted"):
                step["next"] = f"{cli} prepare {job.key} --worktree <a new directory>"
            elif job.state in ("patching", "revising"):
                failure = job.carry.get("_failure") or {}
                why = failure.get("reason") if job.state == "revising" else None
                step["next"] = (f"write and commit the patch in {p.get('worktree') or '<the worktree>'} within the brief; then "
                                f"{cli} stage {job.key} --candidate <full commit sha> --author <the agent> "
                                "--authoring-usd <the agent's $>")
                if why:
                    step["last_refusal"] = why[:400]
                if job.state == "revising" and failure.get("rollback"):
                    step["rollback"] = ("a review rejected a tree the deploy step had ticketed: if it reached the House, roll "
                                        "it back through the watchdog first")
            elif job.state == "testing":
                step["next"] = f"{cli} evaluate {job.key} --python <a venv python with numpy>"
            elif job.state == "canary" and not p.get("canary") and self.approved(p) is None:
                step["next"] = (f"adversarial review (required before the deploy step and the canary): give an agent other "
                                f"than the author {p.get('artifact')}/candidate.patch (sha256 {p.get('patch_sha')}), the "
                                "brief and the playbook's review checklist; its report cites that sha and states `VERDICT: "
                                f"approve` or `VERDICT: reject`; then `{cli} review {job.key} --report <report.md> --reviewer "
                                f"<agent> --patch-sha {p.get('patch_sha')}`")
                step["patch_sha"] = p.get("patch_sha")
            elif job.state == "canary" and not p.get("canary") and not p.get("deploys"):
                step["next"] = (f"the deploy step: `{cli} deploy {job.key}` (it checks the approving review of tree "
                                f"{str(p.get('release_digest'))[:12]} and the deploy hours, and issues the ticket); only then "
                                "send the tree through the watchdog")
            elif job.state == "canary" and not p.get("canary"):
                rule = (p.get("classification") or {}).get("deploy_rule")
                digest = str(p.get("release_digest"))[:12]
                if mode == "window":
                    earliest = float((p.get("baseline") or {}).get("until") or 0.0) + obs
                    step["next"] = (f"deploy exactly the evaluated tree {digest} (commit {p.get('head')}) through the "
                                    f"watchdog ({rule}), no earlier than {iso(earliest)} (the control window must not "
                                    f"overlap the capture); just before, on the House `{house} --since <deploy - {obs:.0f}> "
                                    f"--until <deploy> > control.json`; after the promotion `{house} --seconds 900 > m.json` "
                                    f"and here `{cli} canary {job.key} --measurement m.json --control control.json`")
                else:
                    step["next"] = (f"deploy exactly the evaluated tree {digest} (commit {p.get('head')}) through the "
                                    f"watchdog ({rule}); then on the House `{house} --seconds 900 > m.json` and here "
                                    f"`{cli} canary {job.key} --measurement m.json`, and install canary.json")
            elif job.state == "observing" and p.get("canary") and not p.get("observation"):
                since = float(p["canary"]["since"])
                until = since + float(p["observation_seconds"])
                step["next"] = (f"after {iso(until)}: on the House `{house} --since {since} --until {until} --lanes {lane.id} "
                                f"> m.json` and here `{cli} reconcile {job.key} --measurement m.json`")
                if p.get("required_units") and lane.canary_for(b).get("unit") == "restart":
                    step["next"] = (f"make at least {p['required_units']} deliberate post-close House restarts before "
                                    f"{iso(until)} (none in session); then " + step["next"])
            elif job.state == "verified" and mode == "arms" and not p.get("graduated"):
                step["next"] = (f"graduate: from main, apply {p.get('artifact')}/candidate.patch keeping only the new branch "
                                "(the gate and the old branch removed), open a PR under the same deploy rule, and after it "
                                f"merges `{cli} canary {job.key} --graduated <main commit>`; until then the House's "
                                "canary.json must keep this gate retained")
                step["decision"] = decision
            elif job.state == "verified" and not p.get("graduated"):
                step["next"] = (f"merge: open a PR merging the candidate commit {p.get('head')} into main under its deploy "
                                "rule (the next release built from main drops it otherwise), and after it merges "
                                f"`{cli} canary {job.key} --graduated <main commit>`")
                step["decision"] = decision
            elif job.state == "observing" and decision in ("revert_recommended", "insufficient_activity"):
                step["next"] = (f"roll back: through the watchdog, back from release {(p.get('canary') or {}).get('release')} "
                                f"to the base release; then on the House `{house} --seconds 900 > m.json` and here "
                                f"`{cli} reconcile {job.key} --measurement m.json` records the watchdog's rollback")
                step["decision"] = decision
            elif decision == "voided":
                why = str((p.get("observation") or {}).get("reason") or "")
                step["next"] = (f"voided ({why[:300]}): " + (
                    "the tree reached the House without an approving review and the deploy step before it: roll it back "
                    "through the watchdog now; then measure and rank again (a new capture may register it)"
                    if (p.get("observation") or {}).get("rollback") else
                    "measure and rank again on the running release (a new capture may register it)" if mode == "arms" else
                    "the candidate's release is still deployed: roll it back through the watchdog, or keep it through a "
                    "new capture (measure and rank again on the running release)"))
                step["decision"] = decision
            elif job.state == "rejected" and (job.carry.get("_failure") or {}).get("rollback"):
                # A review rejected a ticketed tree on the candidate's last attempt (the sixth review): the tree may be on
                # the House with nothing left to revise.
                step["rollback"] = step["next"] = (
                    "a review rejected a tree the deploy step had ticketed: if it reached the House, roll it back through "
                    "the watchdog; the bottleneck has used its attempts (a new capture on a new base may register it)")
                step["decision"] = decision
            else:
                step["next"] = None
                step["decision"] = decision
            out.append(step)
        return out

    def gates(self) -> dict[str, Any]:
        """Every arm the journal's canary.json holds, and the retained ones not yet graduated into main (they live only
        in that file: if the House's copy is lost, they silently fall back to the old behavior)."""
        from . import canary as gate

        arms = gate.read(self.root / "canary.json")
        ungraduated = sorted(k for k, j in self.worklist.jobs().items() if j.details.get("lane") and j.state == "verified"
                             and not (j.carry.get("_proposal") or {}).get("graduated"))
        return {"arms": {k: v.get("state") for k, v in arms.items()}, "retained_not_graduated": ungraduated}


__all__ = ["HarnessImprovement", "ImprovementError", "snapshot", "patch_guard", "sandbox", "release_digest", "watchdog",
           "changes", "name_status", "candidate_tree", "read_deploys", "in_session", "judges_sha", "tree_judges_sha",
           "controller_paths", "base_blobs", "CONTROLLER"]
