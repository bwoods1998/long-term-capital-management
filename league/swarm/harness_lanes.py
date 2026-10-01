"""The harness improvement loop's lanes beyond the scheduler: predeclared metrics, the protected boundary, read-only
House observers, ranking, held-out splits and the retain/revert comparison.

`league/swarm/improvement.py` runs the loop (capture -> prepare -> stage -> evaluate -> deploy -> canary -> reconcile);
this module says, per lane, WHAT is measured, what a candidate may touch, which fixed judge scores it offline, how its
canary is split and what retains it. Everything here is fixed before a candidate exists: a candidate cannot edit this
file, its judges (`league/swarm/harness_judges/`), the canary gate or the controller (`PROTECTED`).

THE LANES (`LANES`; the operator's procedure is `playbooks/harness-improvement.md`):

- `research` (research workflow and tools). Bottleneck: Train runs spent on programs that cannot run. Primary metric
  `train_dq_rate` = runtime-disqualified Train runs / Train runs; secondary `gym_seconds_wasted_per_birth`; guards: OK
  runs per research dollar, cycle errors, and cycles that ran the Gym but name no recorded run. Surface: the
  researcher's admission and tools, preflight, the Claude research adapter. Canary: 25% of families, concurrent.
- `memory` (prompts, memory, retrieval). Bottleneck: failed mechanisms reborn. Primary `graveyard_rebirth_rate` =
  births whose mechanism is the same idea (a FROZEN detector below, not the architect's) as an earlier graveyard row on
  the same slice / births; or `validation_attempts_per_usd` = Validation runs at the normal spread / research dollars.
  Surface: the architect's admission, the strategist, diagnostician and researcher prompts and retrieval. Canary: 50% of
  mechanisms (families born in the window), concurrent, with the canary arm's share of births held to its fraction.
- `data` (data processing). Bottleneck: Gym result delivery and data jobs that fail and requeue. Primary
  `slot_failure_rate`. Surface: the Sailbox transport, the data-job supervisor and the data scripts' retry bookkeeping;
  never the Gym pool, which writes this lane's own metric. Canary: the day after the release against a fresh control
  day before it.
- `execution` (execution reliability). Bottlenecks: practice intents the harness rejects (`harness_reject_rate`) and
  restarts that do not restore the live instances (`restart_failure_rate`). Surface: the practice engine, its chains,
  its receipts and the decider; never the real-money order path, the brokerage account, the live state or paper orders
  (capital). Every file there moves the evaluator fingerprint (`league/swarm/evaluator.py`), so a candidate is a
  PLANNED release (an evidence reset) compared before and after, never a runtime gate splitting practice evidence.

WHAT NO LANE MAY CHANGE, AND HOW IT IS CHECKED. Two kinds of check, which must not be confused:

- MACHINE-CHECKED STEPS (the controller refuses; no analysis of what code means). Staging refuses a candidate whose diff,
  listed with `git diff --no-renames --name-status` (deletions and renames included), touches a protected path
  (`PROTECTED`: the objective and this loop, sealed data and the evaluator, spend limits, capital permissions, the release
  train) or any path outside its lane's surface. Every candidate needs an ADVERSARIAL REVIEW of its exact patch and
  evaluated tree, recorded in the journal with the verdict approve, before the loop's deploy step issues the ticket the
  tree is deployed under (`HarnessImprovement.review`, `deploy`); registering its canary (`canary_start`; the scheduler
  lane's `reconcile`) voids it, and asks for a rollback, when the watchdog shows the tree on the House before that
  approval, without a ticket issued in the two hours before the deploy, or deployed in hours its release class forbids
  (`unreviewed`). The release train itself does not read the journal, so a deploy made around the loop is caught
  there, not prevented. The judges, the benchmarks, the rules and the retain/revert decision are the
  PINNED BASE commit's code (a separate checkout the CLI re-executes from; the controller refuses to run any other code,
  `HarnessImprovement.pinned`), the candidate is judged as the base tree with only its staged surface files laid over
  it, and a House measurement must carry the blob hashes of the base's measuring code (`measure`'s `code`). The
  candidate's own modules still run inside the judge's interpreter, which imports the tree: between them and the judge's
  answer stand the per-run nonce, the static guards below, the review and the canary, not a process boundary.
  These machine-checked steps are the hard controls: the protected paths and the surface, the review before the tree
  reaches the House, and the pinned-base evaluation.
- DEFENSE IN DEPTH (static analysis of arbitrary Python: useful, never complete). The import and state rule
  (`protected_routes`, `content_guard`): no new route to the store, evaluator, gate, bands, settings or constitution (an
  import of one, of a name from or re-exported from one, of their parent packages, any star import, an imported module's
  attribute that reaches one: resolved statically over the base and candidate trees) or to a process, file, network or
  loader module (`NO_NEW_IMPORTS`; through another module that imports one, `RESTRICTED_MODULES`; a module's
  `__builtins__`), and no new mutation or bare hand-out of a protected module's state through the names a file already
  binds. Inside the surface files, the frozen
  symbols (`FROZEN_SYMBOLS`, `symbol_guard`): every function that writes or holds a reference to a writer of trial,
  lineage, look, graveyard, state or receipt records (the store's general writers and raw SQL that writes included),
  Train eligibility, the idle and drift screens, the evaluation key, the cycle record the research lane's metrics come
  from, a program's path from the model's tool call to the Gym, the architect's same-idea rule and its pass from the model
  call to `admit`; in `Architect.admit` (the memory lane's lever: it may refuse more) what an admitted birth keeps (its
  text, slice, lineage and trials). And `content_guard`: no new use of a store writer, a sealed reader or a Validation
  key, raw SQL statement, private collaborator access, file-writing constructor, reflection, process or network name;
  in the practice engine no reject reason reworded. These guards refuse the routes reviewers have found; they do NOT
  guarantee that a candidate cannot change trial counts, read sealed data or write files by a route nobody listed.
  The review, the base-pinned judges and regressions (the D2a sentinels among them) and the canary carry that.

WHAT THE OBSERVERS READ. Only operational counts, through read-only (`mode=ro`) SQLite opens: run statuses and times
(never a run's score or summary figures), cycle counters (never the cycle's note or score), births' mechanisms and the
graveyard's mechanism column (never lessons' figures), spend totals, pool events, practice receipts' kinds and reject
reasons, live order statuses and event kinds, House restarts. Never a program, a quote, a parameter, a validation
number or the holdout (`looks`). Error texts are cut to a normalized signature (`signature`).

HELD-OUT, HONESTLY. A capture names its motivating units (the families, mechanisms or boxes the brief shows the patch
author); the arms comparison excludes them, and a before/after window is later than all of them. The offline judge's
held-out split is PRIVATE FAMILIES ITS DEV SPLIT NEVER USES AND NO PUBLIC TEXT NAMES: each lane's pool lives outside
this public repo (the owner's `~/Work/.ltcm-main/harness-heldout/<judge>.json`, mode 0600), pinned here by SHA-256
(`HELDOUT_POOLS`, which says how families are burned), and reaches the judge only on standard input in held-out runs, never as a file in the sandbox; its cases are drawn from a
seed that exists only after the candidate is committed (`heldout_seed`), stratified so every class appears. The author
sees only pass or fail for it (the brief and the journal's notes carry the verdict's public reasons only); the
evaluation receipt in the owner's journal keeps the held-out split's scalar counts and the full reasons for the owner,
never its per-class detail or anything a held-out run printed, and is never given to an author. An "improve" rule also asks the
dev split's count (the motivating failures) to fall wherever its baseline has any, and the concurrent canary (or the
window after the release) is the held-out test of the House itself.

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
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence
import builtins as _builtins

SCHEMA = 1
POLICY = "harness-lanes-1"
BUILTIN_NAMES = frozenset(dir(_builtins))

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
    # the real-money order path and the real book: the only writer of real orders, the brokerage account's reads and
    # writes, the live state; paper orders at the venue
    ("league/live/real.py", "capital"), ("league/live/venue.py", "capital"), ("league/live/state.py", "capital"),
    ("league/live/paper.py", "capital"),
    # the release train
    ("deploy/*", "release"), (".github/*", "release"), ("league/updater.py", "release"), ("league/watchdog.py", "release"),
    ("scripts/floor_box.py", "release"), ("CHANGELOG.md", "release"),
)
#: A candidate may ADD a test file of its own (a new file only: staging refuses an edit of an existing one, an earlier
#: candidate's included), never edit an existing test: the judges and regressions stay fixed.
NEW_TEST = "league/tests/test_harness_candidate_*.py"
#: Names a candidate may not introduce anywhere (reflection, processes, network, file writes and moves, environment,
#: output a judge could mistake for its answer, exits, dynamic attribute access). Counted per name wherever the name is
#: used (a call, an attribute read, a plain name or an imported one: `f = os.system` or `from os import system as sh`
#: counts as much as a call): moving an existing use is allowed, one more is not. Defense in depth: a list of names
#: is never every route to a file or a process (the module docstring).
DANGEROUS_CALLS = frozenset({
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars", "_getframe", "setattr", "delattr", "getattr",
    "open", "fdopen", "system", "popen", "Popen", "check_output", "check_call", "urlopen", "create_connection", "putenv",
    "unsetenv", "chmod", "chown", "unlink", "rmtree", "write_text", "write_bytes", "fork", "forkpty", "kill", "killpg",
    "print", "write", "writelines", "exit", "_exit", "abort", "settrace", "setprofile", "register", "breakpoint",
    # file moves and creation, raw databases
    "rename", "renames", "rmdir", "removedirs", "truncate", "ftruncate", "touch", "mkdir", "makedirs", "symlink",
    "symlink_to", "hardlink_to", "link_to", "mkfifo", "mknod", "copyfile", "sendfile", "connect", "executescript",
    # files written through constructors and writers that are not `open` (the fourth review: a logging FileHandler can
    # rewrite the House's gate file; io.FileIO truncates the store; an archive writes members), and downloads to a path
    "FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler", "basicConfig", "dictConfig",
    "fileConfig", "FileIO", "ZipFile", "PyZipFile", "TarFile", "GzipFile", "BZ2File", "LZMAFile", "writestr",
    "extractall", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "TemporaryDirectory", "mkstemp",
    "mkdtemp", "makefile", "urlretrieve", "dump", "save", "savez", "savez_compressed", "savetxt", "tofile", "to_csv",
    "to_parquet", "to_pickle", "to_json", "setStream",
    # process replacement and spawning
    "execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe", "spawnl", "spawnle", "spawnlp",
    "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp", "startfile", "dup2",
    # dynamic attribute access and module loading by string
    "attrgetter", "methodcaller", "import_module", "run_path", "run_module", "exec_module", "load_module",
    "find_spec", "reload"})
DANGEROUS_MODULES = frozenset({"subprocess", "socket", "urllib", "http", "ctypes", "importlib", "shutil", "pickle",
                               "marshal", "requests", "ssl", "multiprocessing", "atexit", "builtins", "inspect", "gc",
                               "__main__", "_common", "sys", "signal", "code", "pdb", "traceback", "weakref", "runpy",
                               "tempfile", "glob", "types", "zipimport", "pty", "fcntl", "mmap", "resource", "sqlite3",
                               "threading", "_thread", "concurrent", "asyncio", "select", "selectors", "posix", "nt",
                               # file writers that are not `open`: logging's handlers, raw io, archives, compressed
                               # files, key-value files, in-place file rewriting
                               "logging", "io", "pathlib", "zipfile", "tarfile", "gzip", "bz2", "lzma", "shelve", "dbm",
                               "fileinput", "codecs"})
#: A file that already speaks to the network (the Sailbox transport) may import more of the network family.
NETWORK_MODULES = frozenset({"http", "urllib", "socket", "ssl"})
#: Modules a candidate may never add an import of, counted per import statement (a second `import os` inside a function
#: is one more, even where the file already imports os at the top), whatever the file already imports. Their members a
#: file already reaches stay governed by the per-name counts. Defense in depth (`protected_routes`).
NO_NEW_IMPORTS = frozenset({"os", "subprocess", "shutil", "socket", "pathlib", "io", "logging", "tempfile", "importlib",
                            "ctypes"})
#: Modules a candidate may not reach through another module of the tree that imports them (`from .loop import os`,
#: `loop.subprocess`, `from .library import __builtins__`), counted per route by top-level name (`protected_routes`).
RESTRICTED_MODULES = NO_NEW_IMPORTS | DANGEROUS_MODULES
#: The store, the evaluator, the gate, the bands, the settings and the constitution: a candidate may never add a route
#: to them (absolute or relative, the module, a name from it or re-exported from it, a parent package, a star import, a
#: module attribute that reaches it), nor mutate their state. Defense in depth (`protected_routes`).
PROTECTED_MODULES = ("league.swarm.store", "league.swarm.evaluator", "league.swarm.gate", "league.swarm.bands",
                     "league.swarm.settings", "league.constitution")
#: `os` members a candidate may start using (pure path and identity helpers); any other `os.<name>` or `from os import
#: <name>` is refused (remove, replace, system, exec*, spawn*, environ, ...).
OS_SAFE = frozenset({"path", "sep", "linesep", "fspath", "fsencode", "fsdecode", "getpid", "cpu_count", "PathLike", "name",
                     "curdir", "pardir", "extsep", "altsep", "pathsep", "devnull"})
#: Modules a new `import X as Y` may not alias (an alias hides the module's members from the per-name counts).
NO_ALIAS = frozenset({"os", "operator", "functools", "pathlib", "io", "shutil", "subprocess", "sqlite3", "sys", "builtins",
                      "importlib", "inspect", "types", "gc", "ctypes", "logging", "tempfile", "zipfile", "tarfile", "gzip",
                      "bz2", "lzma", "shelve", "dbm", "fileinput", "codecs"})
#: Store methods that write (every `SwarmStore` method but its reads): a candidate may not start calling one
#: (counted per name: moving an existing call is allowed, one more is not). The lanes' metrics, the lineage's trials,
#: eligibility marks and the run rows live in what these write.
STORE_WRITES = frozenset({"put", "update_family", "bump", "set_state", "compare_and_set_state", "hold_gate", "set_band",
                          "retire", "retire_gym", "link_lineages", "_link_code", "add_family", "add_version",
                          "add_versions", "add_run", "prune_runs", "note", "bury", "add_look", "refuse", "add_forward",
                          "replace_forward", "event", "add_spend", "upsert_box", "box_used", "set_box_state", "save_convo",
                          "_exec", "practice_event", "_reject"})
#: Store reads of the holdout, Validation and forward evidence (D2a): a candidate may not start reading them, called or
#: held as a reference. `runs` (its `window="validation"` rows), `run` and `run_result` return a Validation run's row or
#: its full result as readily as a Train one's (the fourth review), so any new use of them counts.
SEALED_READS = frozenset({"looks", "looked", "lineage_looks", "lineage_validated", "lineage_trial_sharpes", "forward",
                          "version_runs", "runs", "run", "run_result"})
#: Store writers and sealed readers with everyday names: counted on ANY object (an over-approximation, defense in depth),
#: so a new `runner.run(...)` or `result.note` is refused too. The brief tells the author.
GENERIC_SEALED = frozenset({"run", "runs", "note", "put", "event", "refuse", "retire", "bump", "forward"}) & (
    STORE_WRITES | SEALED_READS)
#: A string in a key position (a subscript, a call's argument, a keyword's value, a comparison) that names Validation, the
#: holdout or a line's figures (`fam["state"]["validation_line"]["numbers"]`, `runs(fid, window="validation")`): a
#: candidate may not add one (counted per text). Prose in a new prompt constant is not a key position.
SEALED_KEY = re.compile(r"validation|holdout|^numbers$|^looks?$|^forward$", re.I)
#: A key is a word, not prose: a sentence a gated prompt prints ("the validation line") is no key.
KEY_SHAPE = re.compile(r"[A-Za-z_][\w.:-]*")
#: Raw SQL calls: the text of every one is frozen (a new or changed statement is refused), and a function whose statement
#: writes (INSERT, UPDATE, DELETE, ...) or is not a plain string is a record writer, frozen whole (`symbol_guard`).
RAW_SQL = frozenset({"execute", "executemany", "executescript", "_exec", "_all", "_one"})
SQL_WRITE = re.compile(r"\b(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX)\b", re.I)
#: `sys`/`os` members a candidate may not start using: the interpreter's plumbing, the process's output and exit.
PLUMBING = frozenset({"modules", "argv", "stdout", "stderr", "stdin", "exit", "_exit", "_getframe", "settrace",
                      "setprofile", "meta_path", "path_hooks", "path", "displayhook", "excepthook", "environ",
                      "__stdout__", "__stderr__", "write", "dup2", "execv", "execve", "spawnv", "exc_info", "exception",
                      "last_traceback", "last_value", "last_exc", "_current_frames", "addaudithook"})
#: Frame and code introspection (a frame's locals would hold a judge's nonce): reflection whatever the object.
FRAME_ATTRS = frozenset({"tb_frame", "tb_next", "f_back", "f_locals", "f_globals", "f_builtins", "f_code", "gi_frame",
                         "cr_frame", "ag_frame", "co_consts", "co_code"})
#: Dunder attributes a candidate may use freely; any other new one (`__dict__`, `__globals__`, `__subclasses__`, ...)
#: is reflection.
SAFE_DUNDERS = frozenset({"__name__", "__qualname__", "__doc__", "__init__", "__post_init__", "__enter__", "__exit__",
                          "__len__", "__iter__", "__next__", "__eq__", "__hash__", "__repr__", "__str__", "__lt__",
                          "__contains__", "__getitem__", "__bool__", "__future__", "__all__"})
#: An object's collaborators a candidate may not replace (`self.store = ...`): the store, the pool, the model router.
COLLABORATORS = frozenset({"store", "pool", "router", "settings", "clock", "system", "contract", "driver", "client",
                           "transport", "lab", "ledger", "worklist"})
#: The gate's public names; its judges' override (`canary._FORCED`) is never a candidate's to touch.
GATE_NAMES = frozenset({"enabled", "mechanism_unit"})
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


def protected_touch(entries: Iterable[tuple[str, str]]) -> list[str]:
    """MACHINE-CHECKED (the module docstring): the entries of `git diff --no-renames --name-status` (status, path) that
    touch a protected path, whatever the status: a deletion, a type change, either side of a rename (with --no-renames
    a rename is a delete and an add). A candidate's own test file may only be added: a change or deletion of an existing
    one (an earlier candidate's included) touches the fixed tests."""
    out = []
    for status, path in entries:
        why = protected_reason(path)
        if why is None and fnmatch.fnmatchcase(path, NEW_TEST) and status[:1] != "A":
            why = "objective: an existing test"
        if why:
            out.append(f"{status[:1]} {path} ({why})")
    return out


def blob_sha(data: bytes) -> str:
    """Git's blob id of `data` (what `git ls-tree` prints for a file holding these bytes)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def loaded_code() -> dict[str, str]:
    """Every repository module this process has loaded, by repo-relative path, with its git blob id: a measurement
    carries it (`measure`'s `code`), so the owner's controller can check that the code which measured the House is the
    pinned base commit's, never a candidate's (`HarnessImprovement.measured_by_base`)."""
    import sys

    here = Path(__file__).resolve().parents[2]
    out: dict[str, str] = {}
    for module in list(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if not name:
            continue
        try:
            path = Path(name).resolve()
            rel = path.relative_to(here).as_posix()
            if rel.endswith(".py"):
                out[rel] = blob_sha(path.read_bytes())
        except (OSError, ValueError):
            continue
    return dict(sorted(out.items()))


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


def _fingerprinted(path: str) -> bool:
    return path.startswith(("league/gym/", "league/live/")) or path in LEAGUE_FILES


def _collaborator(node: ast.AST) -> bool:
    """`self.settings`, `self.store._x`, ...: an object's shared collaborators, or anything reached through them."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("self", "cls") \
                and node.attr in COLLABORATORS:
            return True
        node = node.value
    return False


def _docstrings(tree: ast.AST) -> set[int]:
    """The ids of every docstring's Constant node (a module's, a class's or a function's first statement)."""
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            out.add(id(body[0].value))
    return out


def _facts(source: str | None) -> dict[str, Any]:
    """What `content_guard` compares, counted: uses of dangerous names (calls, attribute reads, plain and imported
    names), imported modules and aliases, sys/os plumbing and other `os` members, dunder accesses, attribute-assignment
    targets on anything but `self`/`cls`, store writers and sealed readers named (called or held), Validation keys,
    calls through an expression, private attributes of a collaborator, raw SQL statements, mentions of the judges'
    override, gate members, reject-reason texts."""
    out: dict[str, Any] = {"calls": Counter(), "modules": set(), "plumbing": Counter(), "dunders": Counter(),
                           "attr_targets": Counter(), "forced": 0, "gate": Counter(), "global": False, "canary_import": 0,
                           "writes": Counter(), "sealed": Counter(), "private": Counter(), "sql": Counter(),
                           "aliases": Counter(), "os": Counter(), "reasons": Counter(), "sealed_keys": Counter(),
                           "indirect": Counter()}
    if not source:
        return out
    tree = ast.parse(source)
    docs = _docstrings(tree)
    methods = {f.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef) for f in c.body
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    keys: list[ast.AST] = []
    for n in ast.walk(tree):
        # The texts in key positions (`SEALED_KEY`): a subscript, a call's arguments and keyword values, a comparison.
        if isinstance(n, ast.Subscript):
            keys.append(n.slice)
        elif isinstance(n, ast.Call):
            # The gate's own key names its bottleneck (`harness:memory:validation_attempts_per_usd:...`): not a read.
            gate_call = isinstance(n.func, ast.Attribute) and n.func.attr == "enabled" \
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "canary"
            keys.extend(list(n.args[1:] if gate_call else n.args) + [k.value for k in n.keywords])
        elif isinstance(n, ast.Compare):
            keys.extend([n.left] + list(n.comparators))
    for k in keys:
        for c in ast.walk(k) if isinstance(k, (ast.Tuple, ast.List, ast.Set)) else [k]:
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and KEY_SHAPE.fullmatch(c.value) \
                    and SEALED_KEY.search(c.value):
                out["sealed_keys"][c.value[:80]] += 1
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and not isinstance(n.func, (ast.Name, ast.Attribute)):
            # `[f][0](...)`, `(lambda: f)()(...)`, `table[k](...)`: a call through an expression hides what it calls.
            out["indirect"]["a call through an expression"] += 1
        if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute)):
            name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            if isinstance(n.func, ast.Name) and name in STORE_WRITES:
                out["writes"][name] += 1
            if isinstance(n.func, ast.Name) and name in SEALED_READS:
                out["sealed"][name] += 1
            if name in RAW_SQL:
                out["sql"][f"{name}:{ast.dump(n.args[0]) if n.args else '<no statement>'}"] += 1
            if name == "replace" and len(n.args) == 1 and not n.keywords:
                # `Path.replace(target)` moves a file; `str.replace` always takes two arguments.
                out["calls"]["replace/1"] += 1
        if isinstance(n, ast.Attribute):
            # A store writer or sealed reader counts wherever it is named, called or not: `mark = self.store.set_state`
            # or `[self.store.update_family][0](...)` is as much a write as the call (the fourth review).
            if n.attr in STORE_WRITES:
                out["writes"][n.attr] += 1
            if n.attr in SEALED_READS:
                out["sealed"][n.attr] += 1
        if isinstance(n, ast.Import):
            out["modules"].update(a.name for a in n.names)
            out["canary_import"] += sum(a.name.endswith(".canary") or a.name == "canary" for a in n.names)
            for a in n.names:
                if a.asname and a.name.split(".")[0] in NO_ALIAS:
                    out["aliases"][f"import {a.name} as {a.asname}"] += 1
        elif isinstance(n, ast.ImportFrom):
            # `from . import guard` names the module in the alias: record the base and every base.name.
            base = "." * n.level + (n.module or "")
            if n.module:
                out["modules"].add(base)
            out["modules"].update(f"{base}{'.' if n.module else ''}{a.name}" for a in n.names)
            if (n.module or "").endswith("canary"):
                out["gate"].update(f"canary.{a.name}" for a in n.names)
            for a in n.names:
                if a.name == "canary" and a.asname not in (None, "canary"):
                    out["gate"][f"canary as {a.asname}"] += 1
                # An imported name counts as a use of that name, whatever it is bound as.
                if a.name in DANGEROUS_CALLS:
                    out["calls"][a.name] += 1
                # A module's own dunders and frame names, imported (`from .library import __builtins__`, `__loader__`,
                # `__spec__`), are reflection exactly as the same attribute read is (the sixth review).
                if (a.name.startswith("__") and a.name.endswith("__") and a.name not in SAFE_DUNDERS) \
                        or a.name in FRAME_ATTRS:
                    out["dunders"][a.name] += 1
                if a.name in STORE_WRITES:
                    out["writes"][a.name] += 1
                if a.name in SEALED_READS:
                    out["sealed"][a.name] += 1
                if n.level == 0 and n.module in ("os", "sys") and a.name not in (OS_SAFE if n.module == "os" else ()):
                    out["os"][f"{n.module}.{a.name}"] += 1
                if a.name in PLUMBING and n.module in ("os", "sys"):
                    out["plumbing"][f"{n.module}.{a.name}"] += 1
                if a.asname and (n.module or "").split(".")[0] in NO_ALIAS:
                    out["aliases"][f"from {n.module} import {a.name} as {a.asname}"] += 1
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out["global"] = True
        if isinstance(n, ast.Attribute):
            if n.attr in DANGEROUS_CALLS:
                out["calls"][n.attr] += 1
            if isinstance(n.value, ast.Name) and n.value.id in ("sys", "os") and n.attr in PLUMBING:
                out["plumbing"][f"{n.value.id}.{n.attr}"] += 1
            if isinstance(n.value, ast.Name) and n.value.id == "os" and n.attr not in OS_SAFE:
                out["os"][f"os.{n.attr}"] += 1
            if isinstance(n.value, ast.Name) and n.value.id in DANGEROUS_MODULES - NETWORK_MODULES:
                # A member of a process, interpreter or file module the file already imports (`subprocess.run`).
                out["os"][f"{n.value.id}.{n.attr}"] += 1
            if isinstance(n.value, ast.Name) and n.value.id == "canary":
                out["gate"][f"canary.{n.attr}"] += 1
            if (n.attr.startswith("__") and n.attr.endswith("__") and n.attr not in SAFE_DUNDERS) or n.attr in FRAME_ATTRS:
                out["dunders"][n.attr] += 1
            if n.attr.startswith("_") and not n.attr.startswith("__") and (
                    _collaborator(n.value) or (isinstance(n.value, ast.Name) and n.value.id in COLLABORATORS)):
                # `self.store._db`, `store._exec`: a collaborator's internals.
                out["private"][ast.dump(n)] += 1
            if "_FORCED" in n.attr:
                out["forced"] += 1
        elif isinstance(n, ast.Name):
            if n.id in DANGEROUS_CALLS:
                out["calls"][n.id] += 1
            if n.id.startswith("__") and n.id.endswith("__") and n.id not in SAFE_DUNDERS:
                out["dunders"][n.id] += 1
            if "_FORCED" in n.id:
                out["forced"] += 1
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            if "_FORCED" in n.value:
                out["forced"] += 1
            if id(n) not in docs and reject_class(n.value) != "other":
                # A text the practice receipts' reject classes read (`REJECT_CLASSES`).
                out["reasons"][f"{reject_class(n.value)}:{n.value}"] += 1
        elif isinstance(n, ast.alias) and "_FORCED" in (n.name + str(n.asname)):
            out["forced"] += 1
        targets: list[ast.AST] = []
        if isinstance(n, ast.Assign):
            targets = list(n.targets)
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
            targets = [n.target]
        elif isinstance(n, ast.Delete):
            targets = list(n.targets)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS \
                and _collaborator(n.func.value):
            # `self.settings.update(...)`: state every unit shares (an arm's change would reach the control).
            out["attr_targets"][ast.dump(n.func)] += 1
        for t in targets:
            if isinstance(t, ast.Subscript) and _collaborator(t.value):
                out["attr_targets"][ast.dump(t.value)] += 1
            for sub in ast.walk(t):
                if not isinstance(sub, ast.Attribute) or not isinstance(sub.ctx, (ast.Store, ast.Del)):
                    continue
                if not (isinstance(sub.value, ast.Name) and sub.value.id in ("self", "cls")):
                    out["attr_targets"][ast.dump(sub)] += 1
                elif sub.attr in methods or sub.attr in COLLABORATORS:
                    # An instance may keep new state, never replace one of its methods or collaborators.
                    out["attr_targets"][f"{sub.value.id}.{sub.attr}"] += 1
    return out


def _absolute(module: str, level: int, package: Sequence[str]) -> str:
    """A relative import's absolute name, from the importing file's package (`package`: its path's directories)."""
    if not level:
        return module
    anchor = list(package[: len(package) - level + 1]) if level > 1 else list(package)
    return ".".join(anchor + ([module] if module else []))


#: The packages the protected modules live in (`league`, `league.swarm`). Importing one (`import league`, `import
#: league.live.decider`, which binds `league`, `from league import swarm`, `from .. import swarm`) reaches every protected
#: module that has loaded as an attribute (`league.swarm.settings.DEFAULTS`): it counts as an import of a protected module.
PROTECTED_PARENTS = frozenset(".".join(m.split(".")[:n]) for m in PROTECTED_MODULES for n in range(1, m.count(".") + 1))


def protected_module(module: str) -> str | None:
    """The protected module `module` is or lies under (`PROTECTED_MODULES`), or the protected parent package it is."""
    for m in PROTECTED_MODULES:
        if module == m or module.startswith(m + "."):
            return m
    return module if module in PROTECTED_PARENTS else None


def tree_reader(root: Path) -> Any:
    """`read(repo-relative path) -> source or None` over a directory tree (a checkout, an archived commit)."""
    def read(rel: str) -> str | None:
        try:
            return (Path(root) / rel).read_text()
        except (OSError, UnicodeDecodeError):
            return None
    return read


class _Exports:
    """Where a module's names come from, resolved statically from a tree's sources (`read`): a name is PROTECTED when it
    is a protected module or parent package, comes from one (`from .store import SwarmStore`), or is re-exported or
    computed from one in another module (`researcher.settings_mod`, `from .architect import SwarmStore`, `CFG =
    settings_mod.DEFAULTS` in a module a candidate then imports CFG from), followed through every module's own imports,
    star imports and module-level assignments. Defense in depth: a name reached through an object at run time (an
    instance's attribute, a function's return value) is not followed."""

    def __init__(self, read: Any) -> None:
        self.read, self.trees, self.memo, self.modules, self.outside = read, {}, {}, {}, {}

    def external(self, module: str, name: str, depth: int = 0) -> str | None:
        """The module outside the tree that `module`'s attribute `name` is or comes from, followed through the tree's
        own re-exports (the sixth review): `import os` binds `os`; `from os import environ` binds a member of `os`;
        `from .loop import os` or `_o = os` passes either on; every module's `__builtins__` is `builtins`. A name a
        function or a call computes is not followed (defense in depth)."""
        key = (module, name)
        if key in self.outside or depth > 16:
            return self.outside.get(key)
        self.outside[key] = None  # an import cycle resolves to nothing
        src = self.source(module)
        if src is None or self.is_module(f"{module}.{name}"):
            return None
        package, tree = src
        out = None
        for node in _scope(tree.body):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if (a.asname or a.name.split(".")[0]) == name:
                        target = a.name if a.asname else a.name.split(".")[0]
                        out = out or (None if self.is_module(target) else target)
            elif isinstance(node, ast.ImportFrom):
                base = _absolute(node.module or "", node.level, package)
                if not base:
                    continue
                inside = self.is_module(base)
                for a in node.names:
                    if a.name == "*":
                        out = out or (self.external(base, name, depth + 1) if inside else None)
                    elif (a.asname or a.name) == name:
                        out = out or (self.external(base, a.name, depth + 1) if inside else base)
            elif _binds(node, name) and isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
                    getattr(node, "value", None), (ast.Name, ast.Attribute)):
                root = _root_name(node.value)
                out = out or (self.external(module, root.id, depth + 1) if root is not None else None)
        if out is None and name == "__builtins__":
            out = "builtins"
        self.outside[key] = out
        return out

    def source(self, module: str) -> tuple[list[str], ast.Module] | None:
        """(the module's package as path parts, its AST), or None when the tree has no such module."""
        if module not in self.trees:
            found = None
            base = module.replace(".", "/")
            for rel in (f"{base}.py", f"{base}/__init__.py"):
                text = self.read(rel) if module else None
                if text is not None:
                    try:
                        found = (rel.split("/")[:-1], ast.parse(text))
                    except (SyntaxError, ValueError):
                        found = None
                    break
            self.trees[module] = found
        return self.trees[module]

    def is_module(self, module: str) -> bool:
        return bool(module) and self.source(module) is not None

    def member(self, module: str, name: str, depth: int = 0) -> str | None:
        """The protected module (or parent) that `module`'s attribute `name` is, comes from or is computed from."""
        hit = protected_module(module)
        if hit and module not in PROTECTED_PARENTS:
            return hit  # anything from a protected module
        hit = protected_module(f"{module}.{name}")
        if hit:
            return hit  # a protected module or parent package itself
        key = (module, name)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = None  # an import cycle resolves to nothing new
        out = self._binding(module, name, depth + 1) if depth < 16 else None
        self.memo[key] = out
        return out

    def module_of(self, module: str, name: str, depth: int = 0) -> str | None:
        """The (unprotected) module `module`'s attribute `name` is, when it is one: a submodule or an imported module."""
        if self.is_module(f"{module}.{name}"):
            return f"{module}.{name}"
        key = (module, name)
        if key in self.modules or depth > 16:
            return self.modules.get(key)
        self.modules[key] = None
        src = self.source(module)
        out = None
        for node in _scope(src[1].body) if src else ():
            if isinstance(node, ast.Import):
                for a in node.names:
                    if (a.asname or a.name.split(".")[0]) == name:
                        target = a.name if a.asname else a.name.split(".")[0]
                        out = target if self.is_module(target) else out
            elif isinstance(node, ast.ImportFrom):
                base = _absolute(node.module or "", node.level, src[0])
                for a in node.names:
                    if a.name != "*" and (a.asname or a.name) == name and base:
                        out = self.module_of(base, a.name, depth + 1) or out
        self.modules[key] = out
        return out

    def chain(self, module: str, node: ast.AST, depth: int = 0) -> str | None:
        """The protected module an expression evaluated in `module` reaches through its names and module attributes."""
        if isinstance(node, ast.Name):
            return self.member(module, node.id, depth)
        if isinstance(node, ast.Attribute):
            inner = self.chain(module, node.value, depth)
            if inner:
                return inner
            owner = self.chain_module(module, node.value, depth)
            return self.member(owner, node.attr, depth) if owner else None
        if isinstance(node, (ast.Subscript, ast.Starred)):
            return self.chain(module, node.value, depth)
        return None

    def chain_module(self, module: str, node: ast.AST, depth: int = 0) -> str | None:
        """The module an expression evaluated in `module` denotes (`pkg`, `pkg.sub`), when it denotes one."""
        if isinstance(node, ast.Name):
            return self.module_of(module, node.id, depth)
        if isinstance(node, ast.Attribute):
            owner = self.chain_module(module, node.value, depth)
            return self.module_of(owner, node.attr, depth) if owner else None
        return None

    def _binding(self, module: str, name: str, depth: int) -> str | None:
        src = self.source(module)
        if src is None:
            return None
        package, tree = src
        for node in _scope(tree.body):
            if isinstance(node, ast.ImportFrom):
                base = _absolute(node.module or "", node.level, package)
                for a in node.names:
                    if a.name == "*" and base:
                        hit = protected_module(base) or self.member(base, name, depth)
                        if hit:
                            return hit
                    elif (a.asname or a.name) == name and base:
                        hit = self.member(base, a.name, depth)
                        if hit:
                            return hit
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if (a.asname or a.name.split(".")[0]) == name:
                        hit = protected_module(a.name if a.asname else a.name.split(".")[0])
                        if hit:
                            return hit
            elif _binds(node, name) and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                value = getattr(node, "value", None) or getattr(node, "iter", None)
                for item in getattr(node, "items", None) or []:
                    value = item.context_expr
                for sub in ast.walk(value) if value is not None else ():
                    if isinstance(sub, (ast.Name, ast.Attribute)) and isinstance(getattr(sub, "ctx", None), ast.Load):
                        hit = self.chain(module, sub, depth)
                        if hit:
                            return hit
        return None


#: Calls that return a part of their receiver, not a new object: `settings_mod.DEFAULTS.get("gym")` is the shared
#: section as much as `settings_mod.DEFAULTS["gym"]` is (the sixth review).
VIEWS = frozenset({"get", "values", "items", "setdefault", "pop", "popitem", "copy", "__getitem__"})


def _root_name(node: ast.AST, *, views: bool = False) -> ast.Name | None:
    """The name an attribute or item chain starts from (`settings_mod` in `settings_mod.DEFAULTS["gym"]`); with `views`,
    also through a call that returns a part of its receiver (`settings_mod.DEFAULTS.get("gym").update`, `VIEWS`)."""
    while True:
        if isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
            node = node.value
        elif views and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in VIEWS:
            node = node.func.value
        else:
            break
    return node if isinstance(node, ast.Name) else None


def _leaves(node: ast.AST) -> Iterable[ast.AST]:
    """The values an expression may evaluate to: through a conditional, `or`/`and`, a walrus and a star."""
    if isinstance(node, ast.IfExp):
        yield from _leaves(node.body)
        yield from _leaves(node.orelse)
    elif isinstance(node, ast.BoolOp):
        for value in node.values:
            yield from _leaves(value)
    elif isinstance(node, (ast.NamedExpr, ast.Starred, ast.Await)):
        yield from _leaves(node.value)
    else:
        yield node


def protected_routes(source: str | None, path: str, read: Any = None) -> tuple[Counter, Counter]:
    """What a file's imports reach of the protected modules, and what it does to them, counted (`content_guard`
    compares the candidate's counts with the baseline's: moving code is allowed, one more is not).

    ROUTES, per import statement and per module attribute read: each restricted module an import brings in
    (`NO_NEW_IMPORTS` by top-level name; a protected module, a name from one, a protected parent package; every star
    import, whatever it names; a name another module re-exports or computes from a protected module, `_Exports`), and
    each protected module reached through an attribute of an imported module (`researcher.settings_mod`, `pkg.store`).

    MUTATIONS of the names the file binds to protected modules or to their non-function members (`settings_mod`,
    `from .settings import DEFAULTS`): an item or attribute assigned or deleted on them, a mutator named on them
    (`settings_mod.TRAIN_STARTS.clear()`, called or not), and the module object or a part of it handed out bare (`d =
    settings_mod.DEFAULTS`, `f(settings_mod.DEFAULTS["gym"])`, a return, a container) where other code could mutate it.

    Static resolution over `read` (repo-relative path -> source, default the running checkout): DEFENSE IN DEPTH, never a
    proof that no route exists (an object handed over at run time is not followed; the review checks)."""
    routes: Counter = Counter()
    mutations: Counter = Counter()
    if not source:
        return routes, mutations
    exports = _Exports(read or tree_reader(Path(__file__).resolve().parents[2]))
    package = path.split("/")[:-1]
    tree = ast.parse(source)
    modules: dict[str, str] = {}      # names the file binds by import to an unprotected module
    protected: dict[str, bool] = {}   # names bound to a protected module or member: True when they may be mutable
    for n in ast.walk(tree):
        found: set[str] = set()
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                bound, target = a.asname or top, a.name if a.asname else top
                if top in NO_NEW_IMPORTS:
                    found.add(top)
                hit = protected_module(a.name) or protected_module(target)
                if hit:
                    found.add(hit)
                    protected[bound] = True
                elif exports.is_module(target):
                    modules[bound] = target
        elif isinstance(n, ast.ImportFrom):
            base = _absolute(n.module or "", n.level, package)
            top = base.split(".")[0]
            if top in NO_NEW_IMPORTS:
                found.add(top)
            for a in n.names:
                bound = a.asname or a.name
                if a.name == "*":
                    found.add(f"from {base or '.'} import *")
                    continue
                if not base or top in NO_NEW_IMPORTS:
                    continue
                hit = exports.member(base, a.name)
                if hit:
                    found.add(hit)
                    # A function or class of a protected module is not mutable state; the module, a parent package,
                    # a constant, a table or a re-export may be.
                    src = exports.source(base) if protected_module(base) and base not in PROTECTED_PARENTS else None
                    kinds = [type(x) for x in _scope(src[1].body) if _binds(x, a.name)] if src else []
                    protected[bound] = not kinds or any(k not in (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                                                        for k in kinds)
                else:
                    sub = exports.module_of(base, a.name)
                    if sub:
                        modules[bound] = sub
                    # A process, file or loader module (or a member of one) another module of the tree imports, passed
                    # on (`from .loop import os as _o`, `from .library import __builtins__`): the sixth review.
                    outside = exports.external(base, a.name)
                    if outside and outside.split(".")[0] in RESTRICTED_MODULES:
                        found.add(f"{outside.split('.')[0]} (re-exported as {base}.{a.name})")
        routes.update(found)
    # A protected module reached through an attribute of an imported module (`researcher.settings_mod.DEFAULTS`).
    def module_expr(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return modules.get(node.id)
        if isinstance(node, ast.Attribute):
            owner = module_expr(node.value)
            return exports.module_of(owner, node.attr) if owner else None
        return None

    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute):
            owner = module_expr(n.value)
            hit = exports.member(owner, n.attr) if owner else None
            if hit:
                routes[f"{hit} (through {ast.unparse(n)[:60]})"] += 1
            outside = exports.external(owner, n.attr) if owner and not hit else None
            if outside and outside.split(".")[0] in RESTRICTED_MODULES:
                # `loop.os.remove`, `library.__builtins__`: another module's process, file or loader module.
                routes[f"{outside.split('.')[0]} (through {ast.unparse(n)[:60]})"] += 1
    # Mutations of the names bound to protected modules or their mutable members.
    mutable = {name for name, may in protected.items() if may}

    def rooted(node: ast.AST, *, bare: bool) -> bool:
        root = _root_name(node, views=True)
        if root is None:
            return False
        if root.id in mutable:
            return True
        # A protected class or function, handed out bare, is no table; an item or attribute of one may be.
        return root.id in protected and not (bare and isinstance(node, ast.Name))

    for n in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(n, (ast.Assign, ast.Delete)):
            targets = list(n.targets)
        elif isinstance(n, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [n.target]
        elif isinstance(n, ast.withitem) and n.optional_vars is not None:
            targets = [n.optional_vars]
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, (ast.Attribute, ast.Subscript)) and isinstance(sub.ctx, (ast.Store, ast.Del)) \
                        and rooted(sub, bare=False):
                    mutations[f"assigns {ast.unparse(sub)[:80]}"] += 1
        if isinstance(n, ast.Attribute) and n.attr in MUTATORS and rooted(n.value, bare=False):
            mutations[f"mutates {ast.unparse(n)[:80]}"] += 1
        escapes: list[ast.AST] = []
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.Return, ast.Yield,
                          ast.YieldFrom)) and getattr(n, "value", None) is not None:
            escapes.append(n.value)
        elif isinstance(n, ast.Call):
            escapes += list(n.args) + [k.value for k in n.keywords]
        elif isinstance(n, (ast.List, ast.Tuple, ast.Set)):
            escapes += list(n.elts)
        elif isinstance(n, ast.Dict):
            escapes += [v for v in n.values if v is not None]
        elif isinstance(n, ast.Lambda):
            escapes.append(n.body)
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            escapes.append(n.iter)
        elif isinstance(n, ast.withitem):
            escapes.append(n.context_expr)
        elif isinstance(n, ast.Match):
            # `match settings_mod.DEFAULTS: case dict() as d: d.clear()` binds the subject (the sixth review).
            escapes.append(n.subject)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            # A default value is bound to the parameter on every call (`def f(d=settings_mod.DEFAULTS)`).
            escapes += [d for d in list(n.args.defaults) + list(n.args.kw_defaults) if d is not None]
        for e in (leaf for escape in escapes for leaf in _leaves(escape)):
            viewed = isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and e.func.attr in VIEWS
            if (isinstance(e, (ast.Name, ast.Attribute, ast.Subscript)) or viewed) and rooted(e, bare=True):
                mutations[f"hands out {ast.unparse(e)[:80]}"] += 1
    return routes, mutations


def restricted_imports(source: str | None, path: str, read: Any = None) -> Counter:
    """The routes `protected_routes` counts: per import statement each restricted module it brings in (a protected
    module, a name from or re-exported from one, a protected parent package, every star import, `NO_NEW_IMPORTS`), and
    each protected module reached through an imported module's attribute. Defense in depth (static resolution)."""
    return protected_routes(source, path, read)[0]


def content_guard(path: str, before: str | None, after: str, *, read_before: Any = None, read_after: Any = None) -> None:
    """DEFENSE IN DEPTH (static analysis of arbitrary Python cannot be complete: the module docstring). Refuse a Python
    change that adds a route to a protected module or a process, file, network or loader module (`protected_routes`: an
    import of one, of a name from or re-exported from one, of a parent package, a star import, a module attribute that
    reaches one), a mutation or bare hand-out of a protected module's state, and one that introduces reflection,
    processes, network, file writes (calls and constructors), output or exits a judge could mistake for its answer,
    interpreter plumbing, attribute assignment on another object, a store writer or sealed reader named anywhere (called
    or held), a Validation key, a call through an expression, the judges' gate override, or a gate in the evaluator
    fingerprint's files. Every comparison is a count, so moving existing code is allowed and one more is not. Re-exports
    resolve over `read_before` (the base tree) and `read_after` (the candidate tree), each repo-relative path -> source.
    Never a proof of safety: the adversarial review, the base-pinned judges and regressions, and the canary remain."""
    if not path.endswith(".py"):
        return
    from .improvement import ImprovementError  # local: improvement imports this module

    (was, held), (now, done) = protected_routes(before, path, read_before), protected_routes(after, path, read_after)
    added = sorted(m for m, v in now.items() if v > was.get(m, 0))
    if added:
        raise ImprovementError(f"{path}: candidate adds a route to {added[:4]}: no candidate may import the store, "
                               "evaluator, gate, bands, settings or constitution (nor a name from or re-exported from one, "
                               "their parent packages `league` and `league.swarm`, or anything by a star import), or os, "
                               "subprocess, shutil, socket, pathlib, io, logging, tempfile, importlib or ctypes")
    touched = sorted(m for m, v in done.items() if v > held.get(m, 0))
    if touched:
        raise ImprovementError(f"{path}: candidate mutates or hands out a protected module's state {touched[:4]}: read a "
                               "setting inline, never assign, mutate or pass on the module or its tables")
    old, new = _facts(before), _facts(after)

    def more(field: str) -> list[str]:
        return sorted(k for k, v in new[field].items() if v > old[field].get(k, 0))

    risky = [k for k in more("calls") if k in DANGEROUS_CALLS or k == "replace/1"]
    if risky:
        raise ImprovementError(f"{path}: candidate introduces {risky}")
    for field, what in (("plumbing", "interpreter plumbing"), ("dunders", "reflective attributes"),
                        ("attr_targets", "assignment to another object's attribute"),
                        ("os", "process, file or interpreter module members"),
                        ("aliases", "an alias of a process, file or dynamic-access module"),
                        ("writes", "store writes, called or held as a reference (the lanes' records, the lineage's trials, "
                                   "eligibility marks)"),
                        ("sealed", "reads of the holdout, Validation or forward evidence (called or held as a reference)"),
                        ("sealed_keys", "a key naming Validation, the holdout or a line's figures (D2a)"),
                        ("indirect", "a call through an expression (it hides what it calls)"),
                        ("sql", "a new or changed raw SQL statement"),
                        ("private", "a collaborator's private attributes")):
        found = more(field)
        if found:
            raise ImprovementError(f"{path}: candidate introduces {what} {[k[:120] for k in found[:4]]}")
    if path.startswith("league/live/"):
        # The practice receipts' reject reasons are what the execution lane's metric classifies: a candidate may add a
        # reason, never reword or drop one (`reject_class` would move its rejects to another class).
        lost = sorted(k for k, v in old["reasons"].items() if new["reasons"].get(k, 0) < v)
        if lost:
            raise ImprovementError(f"{path}: candidate rewords or drops reject reasons the execution lane classifies "
                                   f"{[k[:80] for k in lost[:4]]}")
    if new["forced"] > old["forced"]:
        raise ImprovementError(f"{path}: the judges' gate override is not a candidate's to name")
    bad_gate = [k for k in more("gate") if k.split(".", 1)[-1] not in GATE_NAMES or " as " in k]
    if bad_gate:
        raise ImprovementError(f"{path}: a candidate uses only canary.enabled and canary.mechanism_unit, as `canary` ({bad_gate})")
    if new["canary_import"] > old["canary_import"]:
        raise ImprovementError(f"{path}: import the gate as `from league.swarm import canary`")
    if _fingerprinted(path) and (new["gate"] or any(m.endswith("canary") for m in new["modules"])):
        raise ImprovementError(f"{path}: no canary gate may sit in the evaluator fingerprint's files: a change there is a "
                               "planned release (an evidence reset), compared before and after")
    package = path[:-3].split("/")[:-1]
    networked = any(m.split(".")[0] in NETWORK_MODULES for m in old["modules"])
    bad = set()
    for module in new["modules"] - old["modules"]:
        level = len(module) - len(module.lstrip("."))
        name = module.lstrip(".")
        absolute = ".".join((package[: len(package) - level + 1] if level else []) + [name]) if level else name
        top = absolute.split(".")[0]
        if (top in DANGEROUS_MODULES and not (networked and top in NETWORK_MODULES)) or any(
                absolute == f or absolute.startswith(f + ".") for f in FORBIDDEN_IMPORTS):
            bad.add(module)
    if bad:
        raise ImprovementError(f"{path}: candidate imports {sorted(bad)} (process, network, interpreter or protected modules)")
    if new["global"] and not old["global"]:
        raise ImprovementError(f"{path}: candidate introduces global or nonlocal mutation")


# ------------------------------------------------------------------------------------------------ frozen symbols
#: Store methods that WRITE the records the multiple-testing control, the lineage, the holdout's looks and the
#: graveyard live in (every Gym evaluation is a trial: `SwarmStore.add_run`).
#: The store's general writers are here too (`update_family` writes the lineage, the parent and the trial counters;
#: `bump` the counters; `set_state` the robustness and drift marks eligibility reads; `add_version` the versions a run is
#: counted against), and the practice engine's receipts (`practice_event`, `_reject`: the execution lane's metric). A
#: function that executes raw SQL that writes (or SQL that is not a plain string) is a writer too (`_writes`).
TRIAL_WRITES = frozenset({"add_run", "add_versions", "add_family", "link_lineages", "retire", "retire_gym", "bury",
                          "add_look", "add_forward", "replace_forward", "hold_gate", "set_band", "prune_runs", "refuse",
                          "update_family", "bump", "set_state", "compare_and_set_state", "add_version", "_link_code",
                          "practice_event", "_reject"})
#: Symbols in lane-surface files no lane may change (their AST, bound once, must be the baseline's): the idle and drift
#: screens, Train eligibility and the score's objective, the evaluation key and reuse, the cycle record the research
#: lane's metrics are computed from, the architect's same-idea rule its lineage links use, and the architect's pass
#: from its model call to `admit` (the text the rebirth detector reads, and a spend reservation).
FROZEN_SYMBOLS: dict[str, tuple[str, ...]] = {
    "league/swarm/researcher.py": (
        "RETIRE_IDLE_EVALUATIONS", "NEGATIVE_FACTOR", "DORMANT_CYCLES", "RETIRE_HOLD_CYCLES", "RETIRE_HOLD_TRIALS",
        "EXTENSION_HOLD_CHECKS", "SCREENS", "DRIFT_PURPOSES", "OBJECTIVE", "CORE_SPAN", "NOT_RUN", "TRANSIENT",
        "idle_limit", "dormant_limit", "dormant_count", "hold_streak", "idle_evaluations", "idle_dead", "_idle_since",
        "revalidation_owed", "held_at_gate", "awaiting_validation", "train_record", "_run_record", "extension_checks",
        "checks_met", "extension_held", "mark_extension", "drift_settings", "drift_row", "row_span", "running_span",
        "version_drift", "drift_verdict", "failed_why", "drift_failed", "validation_drift_failed", "screen_best",
        "demote_version", "completed_run", "new_run", "landed", "robust_at_stress", "candidates_with", "transient",
        "span_of", "objective_for", "_migrated_to", "migrate_objective",
        "Researcher.train_span", "Researcher.train_first_year", "Researcher._robust_of", "Researcher._gym_identity",
        "Researcher.eval_key", "Researcher._result_key", "Researcher._reusable", "Researcher._restart_dormancy",
        "Researcher._with_score", "Researcher.dead", "Researcher.hold_offer", "Researcher.can_retire",
        "Researcher.retire_floor", "Researcher._scored", "Researcher.eligible_run", "Researcher.screen",
        "Researcher.drift_blocks", "Researcher._demote", "Researcher._terminal", "Researcher.cycle",
        "Researcher._count_dormancy", "Researcher._count_holds",
        # A program's path from the model's tool call to the Gym: the arguments a tool call carries, the program text
        # and its parameters, variants and roots. A change here could rewrite the program the Gym evaluates (wrap its
        # decide in try/except, so a runtime error never reaches the Gym's disqualification rule).
        "Researcher._model_cycle", "Researcher._first_cycle", "Researcher._execute", "Researcher._gym_sweep",
        "Researcher._stored_run", "Researcher._sweep_group", "with_roots", "needs_of", "needs_roots",
        "params_of", "sweep_variants", "check_code", "holding", "date_like"),
    # The architect's pass: the model call and its spend reservation, the parse of the answer into proposals and the
    # hand-off to `admit` (a proposal's text reaches the store unchanged: the rebirth detector reads what was proposed).
    "league/swarm/architect.py": ("SAME_IDEA", "_STOP", "words", "same_idea", "salvage_families", "_FAMILIES",
                                  "SALVAGE_MIN", "Architect.run", "Architect._digest_call", "Architect._salvage_retry"),
    # The model's tool calls parsed into the arguments `Researcher._execute` receives (the program among them).
    "league/swarm/claude_research.py": ("ToolCall", "tool_calls", "validate", "check_input", "_type_error", "resolve_name",
                                        "_object", "_finite"),
    # The practice engine's receipts: what the execution lane's metric counts and classifies.
    "league/live/shadow.py": ("ShadowAccount.practice_event", "ShadowAccount._reject"),
}
#: Functions that write trial records yet stay a lane's lever (the architect's admission: refusing a restated idea is
#: the memory lane's improvement). Their trial writes, with every condition around them, and these bindings (the
#: admitted text, the slice, the lineage a birth joins or counts, the lessons a birth reads, and every rule that could
#: admit MORE: the cap, the duplicate and class checks, the citation rule) must stay the baseline's; nothing may mutate
#: them. The lever adds refusals (a gated `continue`), never an admission.
GUARDED_BINDINGS: dict[tuple[str, str], tuple[str, ...]] = {
    ("league/swarm/architect.py", "Architect.admit"): (
        "row", "structure", "named", "roots", "mechanism", "spec", "dead", "same", "declared", "parent", "prior", "home",
        "ideas", "twins", "fam", "alive", "kin", "cap", "known", "strict", "living", "allowed_roots", "per_class",
        "classes", "cls", "cited", "lessons", "lo", "hi", "dte", "born"),
}
MUTATORS = frozenset({"update", "pop", "popitem", "clear", "setdefault", "append", "extend", "insert", "remove",
                      "discard", "add", "sort", "reverse", "__setitem__", "__delitem__"})


def _scope(body: Sequence[ast.stmt]) -> Iterable[ast.stmt]:
    """The statements of one scope, through compound statements, never into a nested def or class."""
    for node in body:
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field_name in ("body", "orelse", "finalbody"):
            yield from _scope(getattr(node, field_name, None) or [])
        for handler in getattr(node, "handlers", None) or []:
            yield from _scope(handler.body)
        for case in getattr(node, "cases", None) or []:
            yield from _scope(case.body)


def _binds(node: ast.stmt, name: str) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        targets = [node.target]
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        targets = [node.target]
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        targets = [i.optional_vars for i in node.items if i.optional_vars is not None]
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name.split(".")[0]) == name for a in node.names)
    return any(isinstance(sub, ast.Name) and sub.id == name for t in targets for sub in ast.walk(t))


def _head_only(node: ast.stmt) -> str:
    """A compound statement's own line (a loop's target and iterable, a with's items), not its body."""
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return ast.dump(ast.Tuple(elts=[node.target, node.iter], ctx=ast.Load()))
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return ast.dump(ast.Tuple(elts=[i.context_expr for i in node.items], ctx=ast.Load()))
    return ast.dump(node)


def _symbol(tree: ast.Module, qualname: str) -> list[str]:
    """Every binding of `qualname` ("NAME" or "Class.method") in the module, dumped."""
    body: Sequence[ast.stmt] = tree.body
    *owners, name = qualname.split(".")
    for owner in owners:
        classes = [n for n in _scope(body) if isinstance(n, ast.ClassDef) and n.name == owner]
        if len(classes) != 1:
            return [f"<{len(classes)} bindings of class {owner}>"] if classes else []
        body = classes[0].body
    return [ast.dump(n) for n in _scope(body) if _binds(n, name)]


def _functions(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level functions and the methods of module-level classes, by qualified name."""
    out: dict[str, ast.AST] = {}
    for node in _scope(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, node)
        elif isinstance(node, ast.ClassDef):
            for sub in _scope(node.body):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.setdefault(f"{node.name}.{sub.name}", sub)
    return out


def _sql_text(node: ast.AST) -> str | None:
    """A statement's text when it is a plain string (a constant, or constants joined), else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _sql_text(node.left), _sql_text(node.right)
        return None if a is None or b is None else a + b
    if isinstance(node, ast.JoinedStr):
        # An f-string's literal parts: the statement's verb and tables are there, the values are parameters.
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _record_write(node: ast.AST, called: frozenset[int] | set[int] = frozenset()) -> bool:
    """A write of the records the lanes, the lineage and the evidence live in: a call of a trial or store writer by name
    (`TRIAL_WRITES`), a reference to one that is not that call's own name (`mark = self.store.set_state`,
    `[self.store.update_family][0]`, `for w in (self.store.bump,)`: `called` holds the ids of the names calls use), or raw
    SQL whose statement writes or cannot be read (not a plain string)."""
    if isinstance(node, ast.Attribute) and node.attr in TRIAL_WRITES and id(node) not in called:
        return True
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if node.func.attr in TRIAL_WRITES:
        return True
    if node.func.attr in RAW_SQL:
        text = _sql_text(node.args[0]) if node.args else None
        return text is None or bool(SQL_WRITE.search(text))
    return False


def _writes(func: ast.AST, *, conditions: bool = True) -> list[str]:
    """The trial writes inside `func` (calls and references, `_record_write`), each with the chain of conditions and
    loops around it."""
    found: list[str] = []
    called = {id(n.func) for n in ast.walk(func) if isinstance(n, ast.Call)}

    def walk(node: ast.AST, chain: tuple[str, ...]) -> None:
        if _record_write(node, called):
            found.append(" > ".join(chain + (ast.dump(node),)) if conditions else ast.dump(node))
        for field_name, value in ast.iter_fields(node):
            children = value if isinstance(value, list) else [value]
            for child in children:
                if not isinstance(child, ast.AST):
                    continue
                link = chain
                if isinstance(node, (ast.If, ast.While)) and field_name in ("body", "orelse"):
                    link = chain + (f"{type(node).__name__}:{field_name}:{ast.dump(node.test)}",)
                elif isinstance(node, ast.IfExp) and field_name in ("body", "orelse"):
                    link = chain + (f"IfExp:{field_name}:{ast.dump(node.test)}",)
                elif isinstance(node, (ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try)) and field_name in (
                        "body", "orelse", "handlers", "finalbody"):
                    link = chain + (f"{type(node).__name__}:{field_name}:{_head_only(node)}",)
                elif isinstance(node, (ast.BoolOp, ast.comprehension)):
                    link = chain + (f"{type(node).__name__}:{ast.dump(node)}",)
                walk(child, link)

    walk(func, ())
    return sorted(found)


#: Method names every list, dict, set, str and bytes has, and a few words most objects use: an attribute by one of these
#: names counts as a reference to the module's own function of that name only on `self`, `cls` or one of the module's
#: classes (`seen.add(x)` is a set's add, not `observe.add`); any other name counts on whatever object it is read.
GENERIC_ATTRS = frozenset(n for t in (list, dict, set, str, bytes, tuple) for n in dir(t) if not n.startswith("_")) | {
    "run", "status", "close", "start", "stop", "read", "summary", "__init__"}


def _writer_names(functions: Mapping[str, ast.AST], classes: frozenset[str] = frozenset()) -> set[str]:
    """The short names of the module's functions that write records (`_writes`), directly or by calling (or naming)
    another such function of the module: the closure, by name (an over-approximation: a name shared with an unrelated
    function counts too, which can only refuse more)."""
    names = {q.rsplit(".", 1)[-1] for q, f in functions.items() if _writes(f)}
    while True:
        more = {q.rsplit(".", 1)[-1] for q, f in functions.items() if q.rsplit(".", 1)[-1] not in names
                and _references(f, names, classes)}
        if not more:
            return names
        names |= more


def _references(tree: ast.AST, names: set[str], classes: frozenset[str] = frozenset()) -> Counter:
    """How often `tree` names each of `names` (an attribute, or a plain name it reads), definitions aside. A generic
    name (`GENERIC_ATTRS`) counts as an attribute only on `self`, `cls` or one of the module's `classes`."""
    owners = {"self", "cls"} | set(classes)
    out: Counter = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in names and (
                node.attr not in GENERIC_ATTRS or (isinstance(node.value, ast.Name) and node.value.id in owners)):
            out[node.attr] += 1
        elif isinstance(node, ast.Name) and node.id in names and isinstance(node.ctx, ast.Load):
            out[node.id] += 1
    return out


def _aliases(value: ast.AST, names: Sequence[str]) -> bool:
    """Whether `value` hands out a guarded binding itself (or a part of one, or one of its methods) rather than a value
    computed from it: the name, an attribute or item of it, a container, a choice or a lambda holding one."""
    if isinstance(value, ast.Name):
        return value.id in names
    if isinstance(value, (ast.Attribute, ast.Subscript)):
        return _aliases(value.value, names)
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        return any(_aliases(e, names) for e in value.elts)
    if isinstance(value, ast.Starred):
        return _aliases(value.value, names)
    if isinstance(value, ast.Dict):
        return any(v is not None and _aliases(v, names) for v in value.values)
    if isinstance(value, ast.IfExp):
        return _aliases(value.body, names) or _aliases(value.orelse, names)
    if isinstance(value, ast.BoolOp):
        return any(_aliases(v, names) for v in value.values)
    if isinstance(value, ast.NamedExpr):
        return _aliases(value.value, names)
    if isinstance(value, ast.Lambda):
        return _aliases(value.body, names)
    return False


def symbol_guard(path: str, before: str | None, after: str) -> None:
    """DEFENSE IN DEPTH (static: the module docstring). Refuse a change to a frozen symbol (`FROZEN_SYMBOLS`), to a
    function that writes trial records or holds a reference to a writer (frozen whole), to any trial write or the
    conditions around it, or to a guarded binding (`GUARDED_BINDINGS`: no rebinding, mutation, mutator reference or alias);
    refuse a new writer of trial records anywhere in a surface file, and a new call of (or reference to) a function of the
    module that writes records directly or through a call."""
    if not path.endswith(".py"):
        return
    from .improvement import ImprovementError

    if before is None:
        if any(_writes(f) for f in _functions(ast.parse(after)).values()):
            raise ImprovementError(f"{path}: a new file may not write trial, lineage, look or graveyard records")
        return
    old, new = ast.parse(before), ast.parse(after)
    for qualname in FROZEN_SYMBOLS.get(path, ()):
        was = _symbol(old, qualname)
        if was and _symbol(new, qualname) != was:
            raise ImprovementError(f"{path}: {qualname} is frozen (the multiple-testing control, eligibility, the screens "
                                   "or the records the lanes measure); no lane may change it")
    guarded = {q: names for (p, q), names in GUARDED_BINDINGS.items() if p == path}
    old_f, new_f = _functions(old), _functions(new)
    writers = {q for q, f in old_f.items() if _writes(f)}
    for qualname in sorted(writers - set(guarded)):
        # Every binding compared (a second `def` of the same name later in the class would shadow the first).
        if _symbol(new, qualname) != _symbol(old, qualname):
            raise ImprovementError(f"{path}: {qualname} writes trial, lineage, look or graveyard records and is frozen whole")
    for qualname, func in new_f.items():
        if qualname not in writers and _writes(func):
            raise ImprovementError(f"{path}: {qualname} would be a new writer of trial, lineage, look or graveyard records")
    # A new path to an existing writer: a new call of (or reference to) a function of this module that writes records,
    # directly or through another such function (`_writer_names`), counted per name.
    classes = frozenset(n.name for n in _scope(old.body) if isinstance(n, ast.ClassDef))
    reach = _writer_names(old_f, classes)
    was, now = _references(old, reach, classes), _references(new, reach, classes)
    grown = sorted(n for n, v in now.items() if v > was.get(n, 0))
    if grown:
        raise ImprovementError(f"{path}: candidate adds a call of (or reference to) {grown[:6]}, which write trial, "
                               "lineage, look or graveyard records directly or through a call: a new path to a record writer")
    for qualname, names in guarded.items():
        a, b = old_f.get(qualname), new_f.get(qualname)
        if a is None:
            continue
        if b is None or len(_symbol(new, qualname)) != 1:
            raise ImprovementError(f"{path}: {qualname} is guarded: bound once, never removed, renamed or shadowed")
        if _writes(a) != _writes(b):
            raise ImprovementError(f"{path}: {qualname}'s trial and lineage writes, and the conditions around them, are frozen")

        def bindings(func: ast.AST) -> Counter:
            body = getattr(func, "body", [])
            found: Counter = Counter()
            for node in _scope(body):
                for name in names:
                    if _binds(node, name):
                        found[f"{name}:{_head_only(node)}"] += 1
            for node in ast.walk(func):
                if isinstance(node, ast.NamedExpr) and node.target.id in names:
                    found[f"{node.target.id}:{ast.dump(node)}"] += 1
                targets: list[ast.AST] = []
                if isinstance(node, (ast.Assign, ast.Delete)):
                    targets = list(node.targets)
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                for t in targets:
                    if isinstance(t, (ast.Subscript, ast.Attribute)):
                        root = t
                        while isinstance(root, (ast.Subscript, ast.Attribute)):
                            root = root.value
                        if isinstance(root, ast.Name) and root.id in names:
                            found[f"mutate:{ast.dump(node)}"] += 1
                # A mutator named on a guarded binding, called or not (`forget = dead.clear; forget()`, the fourth
                # review), and a guarded binding (or a part of one) bound to another name: the alias could mutate it.
                if isinstance(node, ast.Attribute) and node.attr in MUTATORS and isinstance(node.value, ast.Name) \
                        and node.value.id in names:
                    found[f"mutate:{ast.dump(node)}"] += 1
                value = getattr(node, "value", None) if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign,
                                                                           ast.NamedExpr)) else None
                if value is not None and _aliases(value, names):
                    found[f"alias:{ast.dump(node)}"] += 1
            return found

        if bindings(a) != bindings(b):
            raise ImprovementError(f"{path}: {qualname} may refuse more proposals, but what it admits (the text, the slice, "
                                   f"the lineage and its trials: {', '.join(names)}) must stay the baseline's")


# ------------------------------------------------------------------------------------------------ gate coverage
#: What a lane's gate must be asked about, so the gate splits the units the observer splits: the family (a name for it
#: in the unit expression: `fam["id"]`, `fid`, `family`) or the mechanism: `canary.mechanism_unit(mechanism)`, the
#: admitted text inside `Architect.admit` (a guarded binding: the text the birth keeps), or `canary.mechanism_unit(
#: fam["mechanism"])` for a family's stored text. Any other argument (a prompt, a pass, a row's raw text) would split
#: units the observer does not.
UNIT_NAMES = frozenset({"fam", "fid", "family", "family_id"})
MECHANISM_HOMES = {"league/swarm/architect.py": ("Architect.admit",)}
#: Where a memory-lane gate may be asked about a family's stored text (`canary.mechanism_unit(fam["mechanism"])`): the
#: researcher's per-family cycle (its retrieval and prompts), nowhere else (the fourth review: a per-pass text elsewhere
#: could still be keyed by a loop's `fam`).
FAMILY_MECHANISM_HOMES = ("league/swarm/researcher.py",)


def _mechanism_arg(node: ast.AST, path: str | None, where: str | None) -> bool:
    if isinstance(node, ast.Name) and node.id == "mechanism":
        return path is None or where in MECHANISM_HOMES.get(path, ())
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in ("fam", "family")
            and isinstance(node.slice, ast.Constant) and node.slice.value == "mechanism"
            and (path is None or path in FAMILY_MECHANISM_HOMES))


def unit_ok(node: ast.AST, unit: str | None, *, path: str | None = None, where: str | None = None) -> bool:
    if unit == "family":
        return any(isinstance(n, ast.Name) and n.id in UNIT_NAMES for n in ast.walk(node))
    if unit == "mechanism":
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "mechanism_unit"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "canary" and len(node.args) == 1
                and not node.keywords and _mechanism_arg(node.args[0], path, where))
    return True


def is_gate(node: ast.AST, key: str, unit: str | None = None, *, path: str | None = None, where: str | None = None) -> bool:
    """`canary.enabled("<key>", <unit>, root=<state dir>)`, the only gate form a candidate may use, asked about the
    lane's unit (`unit_ok`)."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "enabled"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "canary" and len(node.args) == 2
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == key
            and [kw.arg for kw in node.keywords] == ["root"] and unit_ok(node.args[1], unit, path=path, where=where))


class _Ungate(ast.NodeTransformer):
    """Replace every gated branch with its old one: `if <gate>: new else: old` -> old; `new if <gate> else old` -> old."""

    def __init__(self, key: str, unit: str | None = None, path: str | None = None) -> None:
        self.key, self.unit, self.path, self.gates, self.wrong_unit = key, unit, path, 0, 0
        self.scope: list[str] = []

    def _nested(self, node: ast.AST) -> Any:
        self.scope.append(node.name)
        try:
            return self.generic_visit(node)
        finally:
            self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _nested

    def _gate(self, node: ast.AST) -> bool:
        return is_gate(node, self.key, self.unit, path=self.path, where=".".join(self.scope) or None)

    def visit_Call(self, node: ast.Call) -> Any:
        if is_gate(node, self.key) and not self._gate(node):
            self.wrong_unit += 1
        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> Any:
        if self._gate(node.test):
            self.gates += 1
            out = []
            for stmt in node.orelse:
                result = self.visit(stmt)
                out.extend(result if isinstance(result, list) else [result] if result is not None else [])
            return out
        return self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        # `from league.swarm import canary` (or `from . import canary`) may sit anywhere: it only loads the gate.
        if [(a.name, a.asname) for a in node.names] == [("canary", None)] and (
                (node.level == 0 and node.module == "league.swarm") or (node.level == 1 and node.module is None)):
            return None
        return node

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        if self._gate(node.test):
            self.gates += 1
            return self.visit(node.orelse)
        return self.generic_visit(node)


def _docless(body: list[ast.stmt]) -> list[ast.stmt]:
    return body[1:] if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
        and isinstance(body[0].value.value, str) else body


def _plain(node: ast.AST) -> bool:
    """A value with no effect when evaluated: constants and containers, sums and joins of them."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_plain(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is None or _plain(k) for k in node.keys) and all(_plain(v) for v in node.values)
    if isinstance(node, ast.BinOp):
        return _plain(node.left) and _plain(node.right)
    if isinstance(node, ast.UnaryOp):
        return _plain(node.operand)
    if isinstance(node, ast.JoinedStr):
        return all(isinstance(v, ast.Constant) for v in node.values)
    return False


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _inert_def(node: ast.stmt, *, member: bool = False) -> bool:
    """A new definition that runs nothing when the module loads and changes no lookup: plain decorators, literal
    defaults, no dunder name (a module's `__getattr__`, a class's `__bool__` act with the gate closed; a NEW class's own
    members, `member`, may be dunders: nothing existing knows the class), and a new class only on builtin bases
    (another base's `__init_subclass__` or metaclass runs when the class is made)."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        ok_decorators = all(isinstance(d, ast.Name) and d.id in ("staticmethod", "classmethod", "property")
                            for d in node.decorator_list)
        defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
        return ok_decorators and all(_plain(d) for d in defaults) and (member or not _dunder(node.name))
    if isinstance(node, ast.ClassDef):
        return (not node.decorator_list and not node.keywords and not _dunder(node.name)
                and all(isinstance(b, ast.Name) and b.id in BUILTIN_NAMES for b in node.bases)
                and all(_inert_def(s, member=True) or _new_plain_assign(s, set()) or isinstance(s, ast.Pass)
                        for s in _docless(node.body)))
    return False


def _new_plain_assign(node: ast.stmt, bound: set[str]) -> bool:
    if isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        return len(names) == len(node.targets) and not set(names) & bound and _plain(node.value)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id not in bound and (node.value is None or _plain(node.value))
    return False


def _import_names(node: ast.stmt) -> list[str]:
    """The names an import statement binds."""
    if isinstance(node, ast.Import):
        return [a.asname or a.name.split(".")[0] for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [a.asname or a.name for a in node.names]
    return []


def _referenced(tree: ast.AST) -> set[str]:
    """Every name `tree` reads or binds: plain names, attribute names, definitions and imports. A new definition,
    constant or import that takes one of these names would change what existing code (a frozen function included)
    resolves it to, so it is no new inert definition."""
    out = set(BUILTIN_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            out.update(_import_names(node))
    return out


#: Names every class has (`object`'s): a new method by one of them overrides behavior with the gate closed.
OBJECT_NAMES = frozenset(dir(object))


def _strip_new(head: list[ast.stmt], base: list[ast.stmt], taken: set[str] = frozenset(), *,
               owner: ast.ClassDef | None = None) -> list[ast.stmt]:
    """`head`'s statements of one scope without what it adds: new inert definitions, new plain constants, new imports,
    each under a name no existing code uses (`taken`: the baseline module's names and the builtins; a new
    `def round`, `LONG_SINGLE = ...` or `from x import same_slice` rebinds what existing code calls, so it is a change).
    An existing class (`owner`) is compared member by member the same way, more strictly: a new member there may only
    be a new method under a name `object` does not have, and none at all in a class with bases or decorators (a base's
    method, a dispatch by name like `NodeTransformer.visit_*`, or a dataclass's or NamedTuple's fields would change);
    a new class attribute or field, or an import in the class body, is a change."""
    bound = {n.name for n in base if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))} | set(taken)
    for n in base:
        for t in (n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)]):
            if isinstance(t, ast.Name):
                bound.add(t.id)
        bound.update(_import_names(n))
    imports = {ast.dump(n) for n in base if isinstance(n, (ast.Import, ast.ImportFrom))}
    classes = {n.name: n for n in base if isinstance(n, ast.ClassDef)}
    plain_owner = owner is None or not (owner.bases or owner.keywords or owner.decorator_list)
    out: list[ast.stmt] = []
    for node in head:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name not in bound:
            if _inert_def(node) and plain_owner and not (owner is not None and node.name in OBJECT_NAMES):
                continue
        elif owner is None and isinstance(node, (ast.Import, ast.ImportFrom)) and ast.dump(node) not in imports \
                and not set(_import_names(node)) & bound:
            continue
        elif owner is None and _new_plain_assign(node, bound):
            continue
        elif isinstance(node, ast.ClassDef) and node.name in classes:
            node = ast.ClassDef(name=node.name, bases=node.bases, keywords=node.keywords,
                                body=_strip_new(_docless(node.body), _docless(classes[node.name].body), taken,
                                                owner=classes[node.name]),
                                decorator_list=node.decorator_list, type_params=getattr(node, "type_params", []))
        out.append(node)
    return out


class _Docless(ast.NodeTransformer):
    def generic_visit(self, node: ast.AST) -> ast.AST:
        node = super().generic_visit(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            node.body = _docless(node.body) or [ast.Pass()]
        return node


def gate_coverage(path: str, before: str | None, after: str, key: str, unit: str | None = None) -> int:
    """For an arms-mode lane: `after` must be `before` plus gated branches (`if canary.enabled(KEY, unit, root=...):
    new else: old`, the old branch byte for byte the baseline's code), new inert definitions, new plain constants and new
    imports. So with the gate closed the module runs exactly the baseline. Returns the number of gates."""
    from .improvement import ImprovementError

    if not path.endswith(".py"):
        raise ImprovementError(f"{path}: an arms-mode lane changes only Python: a prose or data change cannot be gated per "
                               "unit (put new text in a new constant chosen under the gate)")
    head = ast.parse(after)
    ungate = _Ungate(key, unit, path)
    head = ungate.visit(head)
    if ungate.wrong_unit:
        raise ImprovementError(f"{path}: the gate must be asked about the lane's unit ({unit}: "
                               + ('a name for the family, e.g. fam["id"]' if unit == "family" else
                                  'canary.mechanism_unit(mechanism) inside Architect.admit, or '
                                  'canary.mechanism_unit(fam["mechanism"]) in league/swarm/researcher.py') + "), the unit "
                               "its observer splits")
    base = ast.parse(before) if before is not None else ast.Module(body=[], type_ignores=[])
    taken = _referenced(base)
    head, base = _Docless().visit(head), _Docless().visit(base)
    kept = _strip_new(_docless(head.body), _docless(base.body), taken)
    if [ast.dump(n) for n in kept] != [ast.dump(n) for n in _docless(base.body)]:
        same = {ast.dump(n) for n in _docless(base.body)}
        changed = sorted({str(getattr(n, "name", f"line {getattr(n, 'lineno', '?')}")) for n in kept if ast.dump(n) not in same})
        raise ImprovementError(f"{path}: not every change is gated: with canary.enabled({key!r}, ...) closed the module must be "
                               f"the baseline's (changed outside a gated branch: {changed[:6]})")
    return ungate.gates


# ------------------------------------------------------------------------------------------------ lanes
#: Tally keys that name no unit a gate routes: cycles with no family (`swarm`), rows with no family or box recorded.
PSEUDO_UNITS = ("swarm", "None", "", "unknown", "null")


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
    judge_floor: float = 0.0            # "improve": the baseline's held-out count must be at least this for a fall to mean
                                        # anything (the judges' held-out splits are built to reach it)
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
    # Whole-population guards, the window against the capture's (before/after, a tolerance, no test): costs no arm can
    # carry, such as research dollars booked with no family (the architect's and the strategist's calls).
    population_guards: tuple[Metric, ...] = ()
    priced: bool = True                 # a captured bottleneck must show it repays a cycle (execution: severity instead)
    arm_needs: str | None = None        # arms: only units with this tally (> 0) in the window are compared
    arm_exclude: tuple[str, ...] = PSEUDO_UNITS   # arms: pseudo-units that are no unit (familyless cycles, no box)
    birth_balance: bool = False         # arms: the canary arm's share of births must not fall below its fraction
    # The held-out pool: the private file `<held-out directory>/<judge>.json` (never in this public repo, never in a
    # patch author's view), pinned by its SHA-256 here. The loop hands it to the judge on standard input, held-out runs
    # only (`HarnessImprovement._evaluate_lane`).
    heldout_pool: str = ""
    # Regression tests the lane's lever is allowed to supersede: run with the gate CLOSED (the old behavior must still
    # pass them), skipped with it OPEN. Each pins the old admission behavior the lever exists to change, never an
    # invariant (trial and lineage accounting, looks, eligibility), which the judge's safety counts carry.
    supersedes: tuple[str, ...] = ()

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
#: Pinned private held-out pools (`Lane.heldout_pool`): SHA-256 of `<held-out directory>/<judge>.json`. The files live
#: outside the repo (`~/Work/.ltcm-main/harness-heldout/` on the owner's machine, mode 0600 in a 0700 directory, backed
#: up with the journal); a lost pool is restored from its backup, never regenerated (a new pool is a new lane hash).
#: Burns are by FAMILY: a fault family any public text names (a PR body and its edit history, a comment, a commit, a
#: docstring, a test fixture, a judge's dev split or vocabulary) is burned whole, and a rotated pool draws its cases from
#: families no public text names, checked by a scan of every public text; the owner's private notes beside the pools
#: record which families are burned. Public text gives the pools by count and hash only.
HELDOUT_POOLS = {
    "research": "594e8e70d7dd6a91c7bbc163b37127bdf5dbfc5c6b8c39dc8556fe3c5070d86e",
    "memory": "2cbaea0004457b96969f8ac9a01224d301892045ba71c07e339a273d77ec89b5",
    "data": "aa17f07ef5befd661aa850ea7372bb4ec4dbd926551f935d0fff0fcf9673df4a",
    "execution": "eecc352b864c624c7913b3b037892a9a099afc4530e21b329ece2f96c1d692d1",
}
#: The research judge's "pays" rule in House terms (Sept 30, 2026, 24 hours read-only): 14.2% of Train runs were
#: disqualified at runtime (2,755 of 19,365), and a Gym job slot took 26 box-seconds (517,618 box-seconds over 19,910
#: slots; a cycle's 130 Gym seconds are its batch's wall time, shared). A screen pays when its added CPU seconds per
#: program are at most PAYS_SHARE of the box-seconds it saves per program at the House's rate, and never above
#: SCREEN_CAP_SECONDS per program (it runs on the House, beside the trading loop, for about 19,000 programs a day). The
#: judge measures the screens' process CPU time, not wall time, so a loaded machine does not fail a sound candidate.
HOUSE_DQ_RATE, BOX_SECONDS_PER_JOB, SCREEN_CAP_SECONDS, SCREEN_FLOOR_SECONDS = 0.142, 26.0, 0.25, 0.01
#: A cycle's cost before it starts (authoring, adversarial reviews, a deploy and its verification; Sept 30 agent rates,
#: estimates): a captured bottleneck is worth a cycle only when its dollars a day at the predeclared effect repay this
#: within PAYBACK_DAYS. Staging checks it again with the candidate's actual release class; the journal records the
#: actual dollars each step reports (`stage --authoring-usd`, `canary --deploy-usd`).
PAYBACK_DAYS = 30
CYCLE_USD = {"research": 10.0, "money_path": 25.0, "evidence_reset": 40.0}
#: Every lane that may edit the researcher or the architect runs the tests that pin the lineage, the rounds, the drift
#: screen, dedupe, the evaluator identity, the graveyard digest and release B's mechanism test (the researcher runs it,
#: and its shadow verdicts stay blind), beside its own.
CORE_REGRESSIONS = ("league.tests.test_swarm_long_single", "league.tests.test_swarm_rounds", "league.tests.test_swarm_drift",
                    "league.tests.test_swarm_dedupe", "league.tests.test_swarm_evaluator",
                    "league.tests.test_swarm_graveyard_digest", "league.tests.test_swarm_mechanism",
                    # D2a at run time (the fourth review): Validation runs, lines, views and a leaderboard seeded with
                    # sentinel figures; no model-facing text (the researcher's cycle, status, brief, prompt and
                    # read_run tool, the architect's prompt, the strategist's and the diagnostician's packets) may
                    # carry one in a common printed form (rounded or truncated). Run with the gate forced open too,
                    # so a gated leak printed in one of those forms fails here, by whichever route it came.
                    "league.tests.test_swarm_d2a_sentinel")
UNATTRIBUTED = Metric("unattributed_usd_per_hour", "unattributed_usd", "hours", min_effect=0.25, abs_tolerance=0.25)
#: The memory lane's lever (refusing a restated buried idea) supersedes these regressions with its gate open: each admits
#: a restated dead idea and checks the birth continues its lineage. With the gate closed they still run and must pass;
#: the memory judge's `trials_uncounted` and `rebirths_fresh_lineage` carry the lineage invariant for what is admitted.
MEMORY_SUPERSEDES: tuple[str, ...] = (
    "league.tests.test_swarm_rounds.ArchitectTests.test_a_proposal_on_a_retired_familys_slice_continues_its_lineage",
    # Only the admission half of the lesson-view test: its prompt half (D2a in the architect's prompt) stays required.
    "league.tests.test_swarm_graveyard_digest.ArchitectRoutes.test_a_birth_on_a_buried_slice_carries_lesson_view_lessons",
    "league.tests.test_swarm_graveyard_digest.ArchitectRoutes.test_proposals_cite_the_rows_they_differ_from",
)

LANES: dict[str, Lane] = {
    "research": Lane(
        id="research", title="Research workflow and tools",
        bottlenecks=(Bottleneck(
            Metric("train_dq_rate", "dq_runs", "train_runs", threshold=0.05, min_units=200, min_effect=0.25),
            (Metric("gym_seconds_wasted_per_birth", "wasted_gym_seconds", "births", min_effect=0.0),),
            "Train runs are disqualified at runtime: programs that cannot run spend a multi-year replay, a trial and "
            "a research cycle each.", judge_primary="gym_seconds_wasted", judge_effect=0.20,
            judge_floor=5 * 130.0),),
        guards=(Metric("ok_runs_per_usd", "ok_runs", "research_usd", direction="higher", min_effect=0.10),
                Metric("cycle_error_rate", "cycle_errors", "cycles", min_effect=0.20),
                # A cycle that ran the Gym but names no recorded run: the join the lane's own metrics rest on.
                Metric("unmatched_gym_cycle_rate", "gym_cycles_unmatched", "gym_cycles", min_effect=0.0,
                       abs_tolerance=0.01),
                # OK Train runs that made no trade: a program whose runtime errors were hidden from the Gym (its decide
                # wrapped in try/except) stops being disqualified and trades nothing. A screen that stops broken
                # programs before the Gym leaves this share alone.
                Metric("zero_trade_ok_rate", "ok_zero_trade_runs", "ok_runs", min_effect=0.10, abs_tolerance=0.02)),
        surface=("league/swarm/researcher.py", "league/swarm/preflight.py", "league/swarm/claude_research.py", NEW_TEST),
        release_classes=("research", "money_path"),
        judge="research", protocol="research-workflow-v3", judge_zero=("false_refusals",), judge_no_worse=(),
        judge_cost="screen_cpu_seconds", judge_cost_rule="pays",
        regressions=("league.tests.test_swarm_researcher", "league.tests.test_swarm_store", "league.tests.test_swarm_loop")
        + CORE_REGRESSIONS,
        canary={"mode": "arms", "unit": "family", "fraction": 0.25, "observe_seconds": 6 * 3600,
                "min_units_per_arm": 12},
        population_guards=(UNATTRIBUTED,), heldout_pool=HELDOUT_POOLS["research"],
    ),
    "memory": Lane(
        id="memory", title="Prompts, memory and retrieval",
        bottlenecks=(
            Bottleneck(
                Metric("graveyard_rebirth_rate", "rebirths", "births", threshold=0.05, min_units=30, min_effect=0.50),
                (Metric("validation_attempts_per_usd", "validation_runs", "research_usd", direction="higher",
                        min_effect=0.0),),
                "New families repeat mechanisms the graveyard already buried on the same slice.",
                judge_primary="rebirths_admitted", judge_effect=0.25, judge_floor=5),
            # Evidence per dollar (the owner's answer 3, Sept 30). A validation attempt is one Validation run at the
            # normal spread (its 1.5x stress twin is the same attempt). Fewer than ten per research dollar is treated as
            # a bottleneck. Offline the judge cannot price a prompt (no provider call runs in the sandbox): a candidate
            # must hold the rebirth filter and the lineage there ("hold"), and the canary carries the whole claim.
            Bottleneck(
                Metric("validation_attempts_per_usd", "validation_runs", "research_usd", direction="higher",
                       threshold=10.0, min_units=10, min_effect=0.25),
                (Metric("graveyard_rebirth_rate", "rebirths", "births", min_effect=0.0, abs_tolerance=0.02),),
                "Research dollars buy few validation attempts: prompts and memory spend model calls on programs and "
                "families that never reach Validation.", judge_primary="rebirths_admitted", judge_mode="hold",
                # Families born in the window need about a day of Train runs before a first Validation attempt.
                canary={"observe_seconds": 48 * 3600})),
        guards=(),
        surface=("league/swarm/architect.py", "league/swarm/strategist.py", "league/swarm/diagnostician.py",
                 "league/swarm/researcher.py", "league/swarm/seeds.py", NEW_TEST),
        release_classes=("research", "money_path"),
        # v4 (release B', family cards): the judge's cases carry cards and admission runs as production runs it; a
        # restatement of a row a mechanism verdict buried must meet the card check (`card_path_admitted`, 0), which the
        # lever may not loosen however far it cuts the idea rows' rebirths; every idea row's slice holds a same-cell
        # control (a new idea under the row's exact card key), so a refusal keyed on cards fails on `novel_refused`;
        # every proposal is written and cites a buried row the same way, so a refusal keyed on a citation or on the
        # text's form fails there too; and no claim recurs in a batch but a twin pair (a restatement and its moved idea,
        # a control and its twin, as many of each), so a refusal keyed on a claim's recurring fails there as well.
        judge="memory", protocol="memory-rebirth-v4",
        judge_zero=("trials_uncounted", "mechanism_rewritten", "card_path_admitted"),
        judge_no_worse=("novel_refused", "rebirths_fresh_lineage"),
        judge_cost="sqlite_statements", judge_cost_rule="ratio",
        # The researcher, the strategist and the diagnostician are in this surface: their tests run too (the fourth
        # review: a retrieval change there could show Validation figures to a model). So do release B's card tests and
        # THE STRUCTURES' (the architect's admission: a complete card, the card-based rebirth refusal, a rebirth's
        # lineage and its row's and cell's budgets, the allowed types), which the rounds' and the graveyard digest's
        # tests leave to them with `require_card` off: a lever may refuse more, never loosen those.
        regressions=("league.tests.test_swarm_r11b", "league.tests.test_swarm_verdicts", "league.tests.test_swarm_store",
                     "league.tests.test_swarm_researcher", "league.tests.test_swarm_strategist",
                     "league.tests.test_swarm_diagnostician", "league.tests.test_swarm_cards",
                     "league.tests.test_swarm_architect_structures") + CORE_REGRESSIONS,
        canary={"mode": "arms", "unit": "mechanism", "fraction": 0.5, "observe_seconds": 12 * 3600,
                "min_units_per_arm": 15},
        population_guards=(UNATTRIBUTED,), arm_needs="births", birth_balance=True, heldout_pool=HELDOUT_POOLS["memory"],
        supersedes=MEMORY_SUPERSEDES,
    ),
    "data": Lane(
        id="data", title="Data processing",
        bottlenecks=(Bottleneck(
            Metric("slot_failure_rate", "slots_failed", "slots", threshold=0.005, min_units=100, min_effect=0.50),
            (Metric("run_error_rate", "error_runs", "runs", min_effect=0.0),),
            "Gym batches fail on delivery and requeue: every job slot in the batch waits and may run again.",
            judge_primary="failed_transient", judge_effect=0.50, judge_floor=5),),
        guards=(Metric("gym_usd_per_ok_slot", "gym_usd", "ok_slots", min_effect=0.10),),
        # Not the Gym pool (`league/swarm/pool.py`): it writes this lane's own metric (its `batch_failed` events and the
        # job slots it books as Gym box spend), and the judge never runs it. A pool change is a reviewed change outside
        # the loop.
        surface=("league/sailbox.py", "league/data_job.py", "scripts/data/boxlib.py",
                 "scripts/data/locking.py", "scripts/data/nightly.py", "scripts/data/sip_progress.py", NEW_TEST),
        release_classes=("research", "money_path"),
        judge="data", protocol="data-retry-v3", judge_zero=("retried_permanent",), judge_no_worse=(),
        judge_cost="requests", judge_cost_rule="ratio",
        regressions=("league.tests.test_gym_driver", "league.tests.test_gym_download_retry", "league.tests.test_swarm_pool"),
        canary={"mode": "window", "unit": "box", "observe_seconds": 24 * 3600, "min_units_per_arm": 3},
        heldout_pool=HELDOUT_POOLS["data"],
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
                       # Restarts are House-wide: deliberate post-close restart tests after the planned release are the
                       # units, against the restarts of the control window before it (`required_units`).
                       # At most three deliberate post-close restarts an evening over the five days: a control whose
                       # counts need more for the exact test voids the canary at its start (`required_units`).
                       canary={"unit": "restart", "observe_seconds": 5 * 86400, "min_units_per_arm": 3,
                               "max_units": 15})),
        guards=(Metric("live_error_rate", "live_errors", "restarts_or_one", min_effect=0.0),),
        # The practice engine, its chains, its receipts and the decider. The real-money order path, the brokerage
        # account, the live state and paper orders are capital (`PROTECTED`). Every file here moves the evaluator
        # fingerprint, so a change is a planned release (an evidence reset) compared before and after: no runtime
        # gate may split practice evidence under one fingerprint.
        surface=("league/live/shadow.py", "league/live/chains.py", "league/live/observe.py", "league/live/decider.py",
                 NEW_TEST),
        release_classes=("evidence_reset",),
        judge="execution", protocol="execution-recovery-v2", judge_zero=("invalid_accepted",),
        judge_no_worse=("valid_rejected", "restart_divergences"), judge_cost="cpu_seconds", judge_cost_rule="ratio",
        regressions=("league.tests.test_shadow_restart", "league.tests.test_live_practice", "league.tests.test_live_paper",
                     "league.tests.test_live_observe"),
        # Five trading sessions of practice after the planned release: a calendar week of wall-clock time.
        canary={"mode": "window", "unit": "family", "observe_seconds": 7 * 86400, "min_units_per_arm": 8,
                "planned_release": True},
        priced=False, heldout_pool=HELDOUT_POOLS["execution"],
    ),
}


#: The module-level rules a lane's capture and registered decision rest on beyond its `Lane` row: the rebirth
#: detector, the reject classes, the cost and payback constants, the observers, the arms split and the comparison, and
#: the loop's decision step. They are hashed into `lane_sha`, so a change to any of them after a capture refuses staging
#: and voids a canary that has not been decided (`HarnessImprovement.canary_start`, `reconcile_lane`).
RULE_SYMBOLS: dict[str, tuple[str, ...]] = {
    "league/swarm/harness_lanes.py": (
        "SAME_IDEA", "FIRST_IDEA", "_STOP", "SINGLES", "words", "jaccard", "first_sentence", "same_idea", "slice_key",
        "REJECT_CLASSES", "reject_class", "signature", "COST_RATIO", "HOUSE_DQ_RATE", "PAYBACK_DAYS", "CYCLE_USD",
        "HELDOUT_POOLS", "PSEUDO_UNITS", "RESEARCH_KINDS", "_WASTED", "_num", "_add", "totals", "_spend", "_research",
        "_read_runtime", "_memory", "_data", "_execution", "measure", "lane_tallies", "lane_metrics", "rank", "payback",
        "motivating_units", "heldout_seed", "split_arms", "_ratio", "compare", "fisher_less", "judge_counts", "_pays",
        "judge_verdict", "binomial_low", "required_units", "retention"),
    "league/swarm/canary.py": ("MECHANISM_CHARS", "in_arm", "mechanism_unit", "decide"),
    "league/swarm/improvement.py": ("ALPHA", "HarnessImprovement.canary_start", "HarnessImprovement.reconcile_lane"),
}
_RULES: dict[str, str] = {}


def rules_sha() -> str:
    """The hash of `RULE_SYMBOLS` as the running code defines them (each symbol's AST, docstrings aside)."""
    if "sha" not in _RULES:
        here = Path(__file__).resolve().parents[2]
        dumps = {}
        for path, names in RULE_SYMBOLS.items():
            tree = _Docless().visit(ast.parse((here / path).read_text()))
            for name in names:
                found = _symbol(tree, name)
                if not found:
                    raise ValueError(f"{path}: the lane rule {name} is not defined")
                dumps[f"{path}:{name}"] = found
        _RULES["sha"] = hashlib.sha256(json.dumps(dumps, sort_keys=True).encode()).hexdigest()
    return _RULES["sha"]


def lane_sha(lane: Lane) -> str:
    """The lane's predeclared definition: its row and the rules it is measured and decided by (`RULE_SYMBOLS`)."""
    return hashlib.sha256(json.dumps({"lane": lane.spec(), "rules": rules_sha()}, sort_keys=True).encode()).hexdigest()


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


def _spend(db: sqlite3.Connection, since: float, until: float) -> tuple[dict[str, float], dict[str, float], float]:
    """(usd by kind, research usd by family, research usd booked with no family) over [since, until)."""
    kinds: dict[str, float] = {}
    by_family: dict[str, float] = {}
    unattributed = 0.0
    for kind, family, usd in db.execute("SELECT kind, family, usd FROM spend WHERE epoch>=? AND epoch<?", (since, until)):
        value = float(usd or 0.0)
        kinds[kind] = kinds.get(kind, 0.0) + value
        if kind in RESEARCH_KINDS and family:
            by_family[family] = by_family.get(family, 0.0) + value
        elif kind in RESEARCH_KINDS:
            unattributed += value
    return kinds, by_family, unattributed


def _research(db: sqlite3.Connection, root: Path, since: float, until: float, examples: int) -> dict[str, Any]:
    units: dict[str, dict[str, float]] = {}
    lo, hi = iso(since), iso(until)
    statuses: dict[str, str] = {}
    dq_paths: list[tuple[str, str, str, str]] = []
    refused: list[tuple[str, str, str]] = []
    # An OK run's trade count only (a count, never its score): the zero-trade guard (`zero_trade_ok_rate`).
    for run_id, family, status, at, path, summary, trades in db.execute(
            "SELECT run_id, family, status, at, path, CASE WHEN status='refused' THEN summary END, "
            "CASE WHEN status='ok' AND json_valid(summary) THEN json_extract(summary,'$.trades') END FROM runs "
            "WHERE window='train' AND purpose='train' AND at>=? AND at<?", (lo, hi)):
        statuses[str(run_id)] = str(status)
        _add(units, family, train_runs=1, dq_runs=status == "disqualified", ok_runs=status == "ok",
             refused_runs=status == "refused", error_runs=status == "error",
             ok_zero_trade_runs=status == "ok" and isinstance(trades, (int, float)) and trades == 0)
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
        if seconds:
            # A cycle that spent Gym seconds names the run it recorded; one that names none (or an unknown one) is
            # unmatched: its seconds cannot be judged, and a rise is a guard breach (`unmatched_gym_cycle_rate`).
            matched += status is not None
            unmatched += status is None
        wasted = status in _WASTED
        _add(units, family or "swarm", cycles=1, cycle_errors=bool(error), gym_seconds=seconds,
             wasted_gym_seconds=seconds if wasted else 0.0, wasted_model_usd=_num(cost) if wasted else 0.0,
             gym_cycles=1 if seconds else 0, gym_cycles_unmatched=1 if seconds and status is None else 0)
    for (fid,) in db.execute("SELECT id FROM families WHERE born_at>=? AND born_at<?", (lo, hi)):
        _add(units, fid, births=1)
    kinds, by_family, unattributed = _spend(db, since, until)
    for fid, usd in by_family.items():
        _add(units, fid, research_usd=usd)
    signatures: dict[str, dict[str, Any]] = {}
    # The newest `examples` of each (none with 0: a slice `[-0:]` would be the whole list).
    sampled = dq_paths[len(dq_paths) - examples:] if examples > 0 else []
    for family, at, path, run_id in sampled:
        result = _read_runtime(root / path)
        text = signature((result or {}).get("disqualified") or ((result or {}).get("messages") or ["unreadable"])[0])
        row = signatures.setdefault(text, {"signature": text, "n": 0, "families": [], "first_at": at})
        row["n"] += 1
        if family not in row["families"] and len(row["families"]) < 8:
            row["families"].append(family)
    for family, at, reason in (refused[len(refused) - examples:] if examples > 0 else []):
        text = "refused: " + signature(reason)
        row = signatures.setdefault(text, {"signature": text, "n": 0, "families": [], "first_at": at})
        row["n"] += 1
        if family not in row["families"] and len(row["families"]) < 8:
            row["families"].append(family)
    ranked = sorted(signatures.values(), key=lambda r: (-r["n"], r["signature"]))
    return {"units": units, "spend": kinds, "join": {"cycles_with_gym_seconds_matched": matched, "unmatched": unmatched},
            "population": {"unattributed_usd": unattributed, "hours": (until - since) / 3600.0},
            "examples": ranked[:16], "sampled_disqualified": len(sampled),
            "disqualified_with_result": len(dq_paths)}


def _read_runtime(path: Path) -> dict[str, Any] | None:
    """Only a retained result's `runtime` block (errors and why it was disqualified); nothing it measured."""
    try:
        doc = json.loads(gzip.decompress(Path(path).read_bytes()))
    except (OSError, ValueError, EOFError, zlib.error, RecursionError):
        # A corrupt or truncated file (a flipped byte in its deflate data raises zlib.error) is one unreadable example.
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
    # A validation attempt is the run at the normal spread; the tournament writes its 1.5x stress twin beside it
    # (`tournament.judge`), which is the same attempt.
    for family, n in db.execute("SELECT family, COUNT(*) FROM runs WHERE window='validation' AND stress=1.0 "
                                "AND at>=? AND at<? GROUP BY family", (lo, hi)):
        _add(units, unit_of.get(str(family), str(family)), validation_runs=n)
    kinds, by_family, unattributed = _spend(db, since, until)
    for fid, usd in by_family.items():
        _add(units, unit_of.get(str(fid), str(fid)), research_usd=usd)
    for row in units.values():
        row["units"] = 1.0
    return {"units": units, "spend": kinds, "by_origin": {k: {"births": v[0], "rebirths": v[1]} for k, v in by_origin.items()},
            "population": {"unattributed_usd": unattributed, "hours": (until - since) / 3600.0},
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
    taken = time.time()
    now = taken if now is None else float(now)
    since = now - seconds if since is None else float(since)
    if not 0 < now - since <= 7 * 86400:
        raise ValueError("a measurement window is between one second and seven days")
    if now > taken + 60:
        raise ValueError("a measurement cannot end in the future: a registered window is measured once it has ended")
    wanted = list(lanes or LANES)
    out: dict[str, Any] = {"schema": SCHEMA, "policy": POLICY, "at": now, "taken_at": taken, "since": since, "until": now,
                           "window": {"since": iso(since), "until": iso(now), "seconds": round(now - since, 1)},
                           "source": running_source(root, now=taken), "lanes": {}, "errors": {}}
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
            except Exception as exc:  # noqa: BLE001 - one lane's odd data never loses the other lanes' measurement
                out["errors"][name] = f"{type(exc).__name__}: {str(exc)[:300]}"
    finally:
        db.close()
    # The swarm's starts in the window and the release each ran (a start of another release inside a registered window
    # voids its comparison; a restart of the same release does not).
    ledger = root / "ledger.sqlite"
    if ledger.exists():
        try:
            db = connect_ro(ledger)
            try:
                rows = db.execute("SELECT at, CASE WHEN json_valid(payload) THEN json_extract(payload,'$.release') END "
                                  "FROM ledger WHERE kind='ops.started' AND at>=? AND at<? ORDER BY seq",
                                  (iso(since), iso(now))).fetchall()
            finally:
                db.close()
            out["starts"] = [e for e in (epoch_of(at) for at, _ in rows) if e is not None]
            out["start_releases"] = [{"at": e, "release": None if r is None else Path(str(r)).name}
                                     for e, r in ((epoch_of(at), r) for at, r in rows) if e is not None]
        except sqlite3.Error as exc:
            out["errors"]["starts"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:
        link = root.parent / "current"
        out["current"] = link.resolve().name if link.is_symlink() else None
        rows = []
        lines = (root.parent / "deploys.jsonl").read_text().splitlines()
        recent = len(lines) - 400
        seen: set[Any] = set()
        for n, line in enumerate(lines):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            # The last 400 rows whole; before them each attempt's first row, its stage, verdict and rollback rows: when
            # every tree first reached the House stays in view however many deploys followed (the sixth review).
            first = row.get("deploy") not in seen
            seen.add(row.get("deploy"))
            if n >= recent or first or row.get("stage") in ("stage", "verdict", "rollback"):
                rows.append({k: row.get(k) for k in ("at", "deploy", "release", "stage", "ok", "digest", "verdict", "ticks",
                                                     "watch_seconds", "grace", "from", "to", "current", "previous")})
        out["deploys"] = rows
    except OSError:
        out["deploys"] = None
    for name, lane in out["lanes"].items():
        lane["metrics"] = lane_metrics(name, lane)
    # The code that took this measurement (run it from the base release's directory): the owner's controller refuses a
    # measurement whose measuring code is not the pinned base commit's (`HarnessImprovement.measured_by_base`).
    out["code"] = loaded_code()
    return out


def lane_tallies(name: str, lane: Mapping[str, Any], exclude: Iterable[str] = ()) -> dict[str, float]:
    skip = set(exclude)
    tally = totals(lane.get("units") or {}, skip)
    tally.update({k: float(v) for k, v in (lane.get("population") or {}).items()})
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
    for metric in ([b.metric for b in spec.bottlenecks] + [m for b in spec.bottlenecks for m in b.secondary] + list(spec.guards)
                   + list(spec.population_guards)):
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
            pays = payback(spec, stake)
            if over and pays["pays"] is False:
                over = False
            need = None
            if spec.canary_for(b).get("unit") == "restart":
                # House-wide events on the exact test: the planned sample must be able to reach alpha against the
                # capture's own counts (a fresh control replaces them at the canary).
                need = required_units(tally, b.metric, alpha=0.05, cap=int(spec.canary_for(b).get("max_units", 60)))
                if over and need is None:
                    over = False
                    pays = {**pays, "why": "the exact test cannot reach alpha against these counts with any planned sample"}
            out.append({"lane": name, "metric": b.metric.name, "value": None if value is None else round(value, 6),
                        "denominator": denominator, "threshold": b.metric.threshold, "min_units": b.metric.min_units,
                        "captured": bool(over), "severity": b.severity, "summary": b.summary, "stake": stake,
                        "secondary": {m.name: m.value(tally) for m in b.secondary},
                        "min_effect": b.metric.min_effect, "direction": b.metric.direction,
                        "offline": b.judge_mode, "release_classes": list(spec.release_classes), "payback": pays,
                        "required_units": None if need is None else max(need, int(spec.canary_for(b).get("min_units_per_arm", 1))),
                        "examples": (lane.get("examples") or [])[:8],
                        "why_not": None if over else ("no data" if value is None else
                                                      pays.get("why") if b.metric.bad(value) and denominator >= b.metric.min_units
                                                      else f"{b.metric.name} {value:.4f} not past {b.metric.threshold} "
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


def payback(lane: Lane, stake: Mapping[str, Any], release_class: str | None = None) -> dict[str, Any]:
    """Whether a cycle repays its estimated cost (`CYCLE_USD` of `release_class`, else of the lane's cheapest class)
    within PAYBACK_DAYS at the predeclared effect. An unpriced lane (execution: real orders and evidence at risk) is
    never refused on price."""
    klass = release_class or min(lane.release_classes, key=lambda c: CYCLE_USD[c])
    cost = CYCLE_USD[klass]
    value = stake.get("usd_per_day_at_effect")
    if not lane.priced:
        return {"pays": None, "class": klass, "cycle_usd": cost, "why": "not priced: ranked by severity"}
    if value is None:
        return {"pays": False, "class": klass, "cycle_usd": cost,
                "why": "does not show it pays back: the measurement cannot price it (no Gym dollars measured)"}
    worth = float(value) * PAYBACK_DAYS
    ok = worth >= cost
    return {"pays": ok, "class": klass, "cycle_usd": cost, "usd_over_payback": round(worth, 2),
            "why": None if ok else (f"does not pay back: ${float(value):.2f} a day at the predeclared effect is "
                                    f"${worth:.2f} over {PAYBACK_DAYS} days, below a {klass} cycle's ${cost:.0f}")}


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
               exclude: Iterable[str] = (), needs: str | None = None
               ) -> tuple[dict[str, Mapping[str, float]], dict[str, Mapping[str, float]]]:
    """The canary and control arms of `units`: `exclude` (motivating units, pseudo-units) dropped, and with `needs` only
    the units holding that tally (the memory lane compares only families born in the window: its gate acts at birth)."""
    from .canary import in_arm

    skip = set(exclude)
    canary, control = {}, {}
    for unit, row in units.items():
        if unit in skip or (needs and not float(row.get(needs) or 0.0) > 0):
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


def judge_counts(lane: Lane) -> tuple[str, ...]:
    """The judge counts a closed gate must leave exactly as the baseline's (every lane's primary, safety and quality)."""
    return tuple(dict.fromkeys([b.judge_primary for b in lane.bottlenecks] + list(lane.judge_zero) + list(lane.judge_no_worse)))


def _pays(lane: Lane, primary: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> str | None:
    """The research judge's cost rule in House terms (HOUSE_DQ_RATE, BOX_SECONDS_PER_JOB): None when it pays."""
    cases = float(b.get("cases") or 0)
    broken = float(b.get("broken_cases") or 0)
    if not cases or not broken:
        return "the judge reported no cases"
    per_program = float(b[lane.judge_cost]) / cases
    added = (float(b[lane.judge_cost]) - float(a[lane.judge_cost])) / cases
    caught = max(0.0, float(a.get("broken_reaching_gym") or 0) - float(b.get("broken_reaching_gym") or 0)) / broken
    saved = caught * HOUSE_DQ_RATE * BOX_SECONDS_PER_JOB
    if per_program > SCREEN_CAP_SECONDS:
        return f"screens take {per_program:.3f} CPU s a program, above the {SCREEN_CAP_SECONDS} s cap"
    if added > max(SCREEN_FLOOR_SECONDS, PAYS_SHARE * saved):
        return (f"the screens add {added:.3f} CPU s a program, more than {PAYS_SHARE:.0%} of the {saved:.3f} Gym "
                "box-seconds a program they save at the House's rate")
    return None


def judge_verdict(lane: Lane, bottleneck: Bottleneck, trees: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The offline decision: the fixed benchmark and the regression comparison. `trees` holds `base` and either `head`
    (window lanes: no gate) or `closed` and `open` (arms lanes: the candidate with its gate forced closed and open).
    Closed must equal the baseline on every judge count and pass the regressions (the old behavior is intact); open (or
    head) must keep the safety counts at 0, not raise the protected counts, stay within the cost rule, pass the
    regressions and, in "improve" mode, cut the held-out primary by the predeclared effect from a baseline at least
    `judge_floor`. Held-out failures are reported without their figures (`public_reasons`)."""
    reasons: list[tuple[str, str]] = []   # (split or "all", text)
    base = trees["base"]
    arms = "open" in trees
    judged = trees["open"] if arms else trees["head"]

    def metrics(tree: Mapping[str, Any], split: str) -> Mapping[str, Any] | None:
        m = ((tree.get("splits") or {}).get(split) or {}).get("metrics")
        return m if isinstance(m, Mapping) else None

    if (base.get("regressions") or {}).get("exit") != 0:
        reasons.append(("all", "the baseline fails its own fixed regressions: the comparison is void"))
    for name in (("closed", "open") if arms else ("head",)):
        if (trees[name].get("regressions") or {}).get("exit") != 0:
            reasons.append(("all", f"the candidate fails the fixed regressions (gate {name})" if arms
                            else "the candidate fails the fixed regressions"))
    primary = bottleneck.judge_primary
    for split in ("dev", "heldout"):
        a, b = metrics(base, split), metrics(judged, split)
        if a is None or b is None:
            reasons.append((split, "a judge run gave no valid answer"))
            continue
        if arms:
            c = metrics(trees["closed"], split)
            if c is None:
                reasons.append((split, "the gate-closed judge run gave no valid answer"))
            else:
                moved = [n for n in judge_counts(lane) if c.get(n) != a.get(n)]
                if moved:
                    reasons.append((split, f"with its gate closed the candidate is not the baseline ({', '.join(moved)} "
                                           "moved): a change sits outside the gated branch"))
        for name in lane.judge_zero:
            if b.get(name) != 0:
                reasons.append((split, f"{name} is {b.get(name)}; it must be 0"))
        for name in lane.judge_no_worse + (primary,):
            if not isinstance(b.get(name), (int, float)) or not isinstance(a.get(name), (int, float)) or b[name] > a[name]:
                reasons.append((split, f"{name} rose from {a.get(name)} to {b.get(name)}"))
        cost_a, cost_b = a.get(lane.judge_cost), b.get(lane.judge_cost)
        if not isinstance(cost_a, (int, float)) or not isinstance(cost_b, (int, float)):
            reasons.append((split, f"the cost {lane.judge_cost} is missing"))
        elif lane.judge_cost_rule == "pays":
            why = _pays(lane, primary, a, b)
            if why:
                reasons.append((split, why))
        elif cost_b > max(COST_FLOOR, COST_RATIO * cost_a):
            reasons.append((split, f"{lane.judge_cost} rose {cost_a} -> {cost_b} (at most {COST_RATIO}x or {COST_FLOOR})"))
    if bottleneck.judge_mode == "improve":
        a = (metrics(base, "heldout") or {}).get(primary)
        b = (metrics(judged, "heldout") or {}).get(primary)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            pass  # reported above
        elif a < max(bottleneck.judge_floor, 1e-9):
            reasons.append(("heldout", f"the baseline's {primary} ({a}) is below the judge's floor {bottleneck.judge_floor}: "
                                       "the held-out split cannot show a fall (a judge defect, not the candidate's)"))
        elif b > (1.0 - bottleneck.judge_effect) * a:
            reasons.append(("heldout", f"{primary} {a} -> {b}, less than the predeclared {bottleneck.judge_effect:.0%} fall"))
        # The motivating failures must fall too, wherever the baseline has any: a change written from the public
        # held-out classes alone, which leaves the failures that captured the bottleneck, is not the improvement.
        a = (metrics(base, "dev") or {}).get(primary)
        b = (metrics(judged, "dev") or {}).get(primary)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > 0 and b > (1.0 - bottleneck.judge_effect) * a:
            reasons.append(("dev", f"{primary} {a} -> {b} on the dev split (the motivating failures), less than the "
                                   f"predeclared {bottleneck.judge_effect:.0%} fall"))
    public = [text if split != "heldout" else "held-out split: not passed (its cases and figures stay private)"
              for split, text in reasons]
    return {"passed": not reasons, "reasons": [f"{split}: {text}" if split != "all" else text for split, text in reasons],
            "public_reasons": list(dict.fromkeys(public)), "mode": bottleneck.judge_mode, "primary": primary,
            "effect": bottleneck.judge_effect, "cost_rule": lane.judge_cost_rule, "gate": "open and closed" if arms else None}


def binomial_low(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if n <= 0:
        return 1.0
    p = min(max(p, 0.0), 1.0)
    return min(1.0, sum(math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(0, k + 1)))


def required_units(control: Mapping[str, float], metric: Metric, *, alpha: float, cap: int = 60) -> int | None:
    """The fewest treated events-free units that could reach `alpha` against the control's counts on the exact test
    (a House-wide count such as restarts); None when even `cap` cannot."""
    k2, n2 = int(control.get(metric.numerator) or 0), int(control.get(metric.denominator) or 0)
    for n1 in range(1, cap + 1):
        if fisher_less(0, n1, k2, n2) <= alpha:
            return n1
    return None


def retention(lane: Lane, bottleneck: Bottleneck, treated: Mapping[str, Mapping[str, float]],
              control: Mapping[str, Mapping[str, float]], *, seed: str, extra_treated: Mapping[str, float] | None = None,
              extra_control: Mapping[str, float] | None = None, alpha: float = 0.05,
              population: tuple[Mapping[str, float], Mapping[str, float]] | None = None, fraction: float | None = None,
              min_units: int | None = None) -> dict[str, Any]:
    """The registered decision: the primary metric better by at least `min_effect` with p <= alpha and enough
    denominator in each group; every secondary and guard metric (quality and cost) no worse than its tolerance; every
    population guard (the window's whole-population tallies against the capture's, `population` = (window, capture))
    no worse than its tolerance; and, with `lane.birth_balance` and the arm's `fraction`, the canary arm's share of the
    births not significantly below its fraction (a canary that refuses more than restated ideas misses signals)."""
    min_units = int(min_units if min_units is not None else lane.canary_for(bottleneck).get("min_units_per_arm", 1))
    primary = compare(bottleneck.metric, treated, control, seed=seed, extra_treated=extra_treated, extra_control=extra_control)

    def clusters(units: Mapping[str, Any], extra: Mapping[str, float] | None) -> float:
        # Units that carry the primary metric resample as clusters; a House-wide count (restarts), which no unit
        # carries, is its own count of events.
        fields = (bottleneck.metric.numerator, bottleneck.metric.denominator)
        carrying = [r for r in units.values() if any(f in r for f in fields)]
        return float(len(carrying)) if carrying else float((extra or {}).get(bottleneck.metric.denominator) or 0.0)

    # Enough clusters in each group, and each group's denominator at the capture's own minimum.
    enough = (clusters(treated, extra_treated) >= min_units and clusters(control, extra_control) >= min_units
              and primary["treated_denominator"] >= max(1, bottleneck.metric.min_units)
              and primary["control_denominator"] >= max(1, bottleneck.metric.min_units))
    improved = (enough and primary["relative"] is not None and primary["relative"] >= bottleneck.metric.min_effect
                and primary["p_value"] is not None and primary["p_value"] <= alpha)
    checks = []

    def tolerate(metric: Metric, row: dict[str, Any]) -> dict[str, Any]:
        # A guard fails when it worsens by more than its tolerance (relative, or absolute when `abs_tolerance` is set).
        # A zero control makes the relative change undefined: then only the absolute tolerance can pass it (a guard that
        # goes from no errors to some errors fails). Unmeasured on either side passes, and the decision records it.
        sign = 1.0 if metric.direction == "lower" else -1.0
        worse = None if row["treated"] is None or row["control"] is None else (row["treated"] - row["control"]) * sign
        row["ok"] = ((row["relative"] is not None and row["relative"] >= -metric.min_effect)
                     or (worse is not None and worse <= metric.abs_tolerance) or worse is None)
        return row

    for metric in list(bottleneck.secondary) + list(lane.guards):
        checks.append(tolerate(metric, compare(metric, treated, control, seed=seed, extra_treated=extra_treated,
                                               extra_control=extra_control)))
    if population is not None:
        window, capture = population
        for metric in lane.population_guards:
            va, vb = metric.value(window), metric.value(capture)
            sign = 1.0 if metric.direction == "lower" else -1.0
            row = {"metric": metric.name, "scope": "population: the window against the capture", "treated": va,
                   "control": vb, "relative": None if va is None or vb is None else
                   ((vb - va) * sign / abs(vb) if vb else (0.0 if va == vb else None))}
            checks.append(tolerate(metric, row))
    if lane.birth_balance and fraction:
        births = [int(sum(float(r.get("births") or 0) for r in group.values())) for group in (treated, control)]
        n, k = sum(births), births[0]
        p_low = binomial_low(k, n, float(fraction))
        checks.append({"metric": "birth_balance", "treated": k, "control": births[1], "expected_share": fraction,
                       "p_value": round(p_low, 6), "ok": n == 0 or p_low > alpha,
                       "note": "the canary arm's births against its fraction (one-sided binomial): over-refusal fails"})
    decision = ("insufficient_activity" if not enough else
                "retained" if improved and all(c["ok"] for c in checks) else "revert_recommended")
    return {"decision": decision, "primary": primary, "checks": checks, "alpha": alpha, "min_units_per_arm": min_units,
            "min_effect": bottleneck.metric.min_effect}


__all__ = ["LANES", "Lane", "Metric", "Bottleneck", "PROTECTED", "protected_reason", "protected_touch", "classify",
           "live_path_modules", "restricted_imports", "NO_NEW_IMPORTS", "PROTECTED_MODULES", "blob_sha", "loaded_code",
           "content_guard", "symbol_guard", "gate_coverage", "is_gate", "surface_check", "measure", "rank", "lane_metrics",
           "motivating_units", "heldout_seed", "split_arms", "compare", "retention", "judge_verdict", "judge_counts",
           "payback", "required_units", "binomial_low", "fisher_less", "signature", "words", "jaccard", "same_idea",
           "slice_key", "reject_class", "lane_sha", "DEPLOY_RULES", "COST_RATIO", "COST_FLOOR", "PAYS_SHARE", "CYCLE_USD",
           "PAYBACK_DAYS", "FROZEN_SYMBOLS", "GUARDED_BINDINGS", "TRIAL_WRITES"]
