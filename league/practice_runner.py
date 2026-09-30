"""Finite, credential-free LOCAL simulations of the observe cohort engine.

The trusted parent reads a supplied JSON bundle. Only the strategy child executes
programs, inside mandatory bubblewrap, without the input file, result directory,
host home, credentials or network. Nothing here is live evidence or research feedback.
See docs/local-practice.md for the input and recovery contracts.
"""

from __future__ import annotations

import argparse
import ast
import copy
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import math
import os
import re
import resource
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .live.decider import Decider, DeciderError

REPO = Path(__file__).resolve().parents[1]
SCHEMA = 1
MAX_BYTES = 32 * 1024 * 1024
MAX_FRAMES = 800
MAX_PROGRAMS = 4
MAX_SECONDS = 180
NY = ZoneInfo("America/New_York")
MARKER = "local-practice.json"
RUNTIME_FILES = (
    "league/__init__.py", "league/safety.py", "league/structure_core.py",
    "league/live/__init__.py", "league/live/decider.py", "league/gym/__init__.py",
    "league/gym/runtime.py", "league/gym/safety.py", "league/gym/ctx.py",
    "league/gym/greeks.py", "league/gym/venue.py",
)
EXTRA_EVALUATOR_FILES = ("league/constitution.py", "league/swarm/settings.py", "league/swarm/bands.py",
                         "league/swarm/evaluator.py", "ltcm/data/__init__.py")
DISCLAIMER = "Local simulation only; not live practice, forward evidence, promotion evidence, or researcher feedback."


class PracticeError(ValueError):
    """An input, isolation, state or identity boundary was refused."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise PracticeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _json(data: bytes) -> Any:
    def bad(value):
        raise PracticeError(f"non-finite JSON number: {value}")
    return json.loads(data, object_pairs_hook=_object, parse_constant=bad)


def _keys(value: Any, allowed: set[str], required: set[str]) -> None:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise PracticeError(f"expected object keys {sorted(required)}; allowed {sorted(allowed)}")


def _at(value: Any) -> float:
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() != dt.timedelta(0):
            raise ValueError("UTC required")
        return stamp.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise PracticeError("timestamps must be explicit UTC ISO dates") from None


def validate_bundle(value: Any) -> dict:
    """Pure structural/causal checks. Never compile or execute a supplied program."""
    from .gym.safety import check_program
    from .live.venue import occ_parts

    _keys(value, {"schema", "kind", "label", "programs", "frames"}, {"schema", "kind", "label", "programs", "frames"})
    if value["schema"] != SCHEMA or type(value["schema"]) is not int or value["kind"] not in ("replay", "synthetic"):
        raise PracticeError("schema 1 and kind replay or synthetic are required")
    if not isinstance(value["label"], str) or not 1 <= len(value["label"]) <= 200:
        raise PracticeError("a short input label is required")
    programs, frames = value["programs"], value["frames"]
    if not isinstance(programs, list) or not 1 <= len(programs) <= MAX_PROGRAMS:
        raise PracticeError("supply one to four programs")
    roots, families = set(), set()
    for p in programs:
        fields = {"family", "version", "code", "params", "roots", "structure"}
        _keys(p, fields, fields)
        if not isinstance(p["family"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", p["family"]) or p["family"] in families:
            raise PracticeError("families must be unique plain lowercase identifiers")
        families.add(p["family"])
        if type(p["version"]) is not int or not 1 <= p["version"] <= 1_000_000:
            raise PracticeError("version must be a positive integer")
        if not isinstance(p["code"], str) or not 1 <= len(p["code"].encode()) <= 65536 or not isinstance(p["params"], dict):
            raise PracticeError("code and parameter object required")
        if len(canonical(p["params"])) > 16384 or not isinstance(p["structure"], str) or not re.fullmatch(r"[a-z_]{1,40}", p["structure"]):
            raise PracticeError("oversized parameters or malformed structure")
        if (not isinstance(p["roots"], list) or not p["roots"]
                or any(not isinstance(r, str) or not re.fullmatch(r"[A-Z]{1,6}", r) for r in p["roots"])
                or len(set(p["roots"])) != len(p["roots"])):
            raise PracticeError("roots must be unique upper-case symbols")
        try:
            check_program(p["code"])
            needs = [ast.literal_eval(n.value) for n in ast.parse(p["code"]).body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in n.targets)]
            matches = len(needs) == 1 and isinstance(needs[0], dict) and set(needs[0].get("roots", [])) == set(p["roots"])
        except (ValueError, SyntaxError, TypeError, RecursionError) as exc:
            raise PracticeError("program failed static input validation") from exc
        if not matches:
            raise PracticeError("literal NEEDS roots must equal the declared roots")
        roots.update(p["roots"])
    if len(roots) > MAX_PROGRAMS:
        raise PracticeError("at most four distinct roots")
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise PracticeError("supply 1 to 800 frames")
    previous = -math.inf
    contracts = {}
    for frame in frames:
        _keys(frame, {"at", "stocks", "options"}, {"at", "stocks", "options"})
        at = _at(frame["at"])
        minute = math.floor(at / 60)
        if minute <= previous:
            raise PracticeError("frames must advance strictly, at most one observation per minute")
        previous = minute
        for key, option in (("stocks", False), ("options", True)):
            rows = frame[key]
            if not isinstance(rows, dict) or len(rows) > (512 if option else MAX_PROGRAMS):
                raise PracticeError("oversized snapshot")
            for symbol, row in rows.items():
                parts = occ_parts(symbol) if option else None
                if (option and (not parts or parts[0] not in roots)) or (not option and symbol not in roots):
                    raise PracticeError("snapshot outside declared roots")
                if option:
                    key = (dt.datetime.fromtimestamp(at, NY).date(), parts[0])
                    seen = contracts.setdefault(key, set())
                    seen.add(symbol)
                    if len(seen) > 256:
                        raise PracticeError("at most 256 distinct contracts per root/session")
                allowed = {"latestQuote"} if option else {"latestQuote", "latestTrade", "minuteBar"}
                _keys(row, allowed, set())
                for name, packet in row.items():
                    fields = ({"t", "bp", "ap", "bs", "as"} if name == "latestQuote" else
                              {"t", "p", "s"} if name == "latestTrade" else {"t", "o", "h", "l", "c", "v"})
                    _keys(packet, fields, {"t"})
                    if name != "minuteBar" and _at(packet["t"]) > at:
                        raise PracticeError("quote/trade timestamp is later than its observation")
                    _at(packet["t"])
                    for field, number in packet.items():
                        if field != "t" and number is not None and (type(number) not in (int, float) or not math.isfinite(number) or number < 0):
                            raise PracticeError("snapshot numbers must be finite nonnegative numbers or null")
    return copy.deepcopy(value)


def _plain_path(path: Path) -> Path:
    path = path.absolute()
    if any(c in str(path) for c in ("?", "#", "\n", "\r", "\x00")):
        raise PracticeError("reserved URI/control characters are not accepted in paths")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise PracticeError("symlink paths are not accepted")
    return Path(os.path.normpath(path))


def load_bundle(path: Path) -> dict:
    path = _plain_path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES or path.stat().st_nlink != 1:
        raise PracticeError("input must be a regular JSON file of at most 32 MiB")
    return validate_bundle(_json(path.read_bytes()))


class RecordedMarket:
    """One explicitly observed frame, no carry-forward, history, transport or credentials."""

    def __init__(self):
        from .live.venue import Rate
        self.frame = {"stocks": {}, "options": {}}
        self.now = 0.0
        self.minute_calls = Rate(1000, clock=lambda: self.now)
        self.incomplete_bars_withheld = 0

    def select(self, frame: dict) -> None:
        self.now = _at(frame["at"])
        self.frame = copy.deepcopy(frame)
        for row in self.frame["stocks"].values():
            bar = row.get("minuteBar")
            if bar is not None and _at(bar["t"]) + 60 > self.now:
                del row["minuteBar"]
                self.incomplete_bars_withheld += 1

    def stocks(self, symbols):
        self.minute_calls.take()
        return {s: copy.deepcopy(self.frame["stocks"][s]) for s in symbols if s in self.frame["stocks"]}

    def chain(self, underlying, *, expiry_from, expiry_to, strike_from=None, strike_to=None, **_):
        from .live.venue import occ_parts
        self.minute_calls.take()
        out = {}
        for symbol, row in self.frame["options"].items():
            root, expiry, _, strike = occ_parts(symbol)
            if (root == underlying and expiry_from <= expiry <= expiry_to
                    and (strike_from is None or strike >= strike_from) and (strike_to is None or strike <= strike_to)):
                out[symbol] = copy.deepcopy(row)
        return out

    def contracts(self, symbols, **_):
        self.minute_calls.take()
        return {s: copy.deepcopy(self.frame["options"][s]) for s in symbols if s in self.frame["options"]}

    def bars(self, symbols, **_):
        return {s: [] for s in symbols}  # prior-session information was not supplied; never invent it


class ObserveOnlyFamilies:
    """Explicit local programs, not a claim of Gym or live eligibility."""

    def __init__(self, programs: list[dict]):
        self.rows = [{**copy.deepcopy(p), "family": "local_" + p["family"], "observe": True, "band": "gym",
                      "tier": "train", "lineage": "local_simulation", "needs_roots": list(p["roots"]),
                      "run_sha": digest(p), "validation_passed": False, "holdout_passed": False}
                     for p in programs]

    def read(self, *_, **__):
        return []

    def observe(self, family=None, version=None):
        return copy.deepcopy([p for p in self.rows if (family is None or p["family"] == family)
                              and (version is None or p["version"] == version)])

    def denied(self, *_, **__):
        raise PracticeError("local simulation cannot admit ordinary instances, write forward evidence or change bands")

    add_forward = set_band = confirm_band = promoted_at = forward_rows = admit_open = denied


def _stage_runtime(target: Path) -> None:
    for name in RUNTIME_FILES:
        source = _plain_path(REPO / name)
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source.read_bytes())
        path.chmod(0o444)


def sandbox_command(runtime: Path, *, python: Path) -> list[str]:
    """No input/output/home/checkout mounts; numpy is the only third-party child dependency."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise PracticeError("bwrap is mandatory; there is no unsandboxed fallback")
    import numpy

    python = python.absolute()
    argv = [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL"]
    for name in ("/usr", "/lib", "/lib64"):
        if Path(name).exists():
            argv += ["--ro-bind", name, name]
    venv = python.parent.parent
    if not (venv / "pyvenv.cfg").is_file() or not python.resolve().is_relative_to("/usr"):
        raise PracticeError("use an isolated virtual environment based on the system Python")
    package = Path(numpy.__file__).parent
    site = f"/venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    argv += ["--ro-bind", str(python.resolve()), "/venv/bin/python",
             "--ro-bind", str(venv / "pyvenv.cfg"), "/venv/pyvenv.cfg",
             "--ro-bind", str(package), site + "/numpy"]
    native = package.parent / "numpy.libs"
    if native.exists():
        argv += ["--ro-bind", str(native), site + "/numpy.libs"]
    argv += ["--ro-bind", str(runtime), "/work", "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev",
             "--chdir", "/work", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
             "--setenv", "HOME", "/tmp", "--setenv", "OPENBLAS_NUM_THREADS", "1",
             "--setenv", "OMP_NUM_THREADS", "1", "--setenv", "LIVE_DECIDER_MEMORY_MB", "1024",
             "--", "/venv/bin/python", "-E", "-s", "-B", "-m", "league.live.decider"]
    return argv


class SandboxedDecider(Decider):
    """The existing bounded JSON protocol, with mandatory OS isolation on EVERY spawn."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.failure = None
        self.expected_roots = {}

    def _spawn(self, budget_seconds=10.0):
        if self._runtime is None:
            self._runtime = Path(tempfile.mkdtemp(prefix="local-practice-runtime-"))
            _stage_runtime(self._runtime)
        argv = sandbox_command(self._runtime, python=Path(self.python))

        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env={"PATH": "/usr/bin:/bin"}, close_fds=True, preexec_fn=limits)
        self.pid = self.proc.pid
        self._ready.clear()

    def _raw(self, message, deadline):
        try:
            answer = super()._raw(message, deadline)
            if message[0] == "load" and answer.get("ok"):
                expected = self.expected_roots.get(message[1])
                if expected is None or set(answer.get("needs", {}).get("roots", [])) != expected:
                    raise PracticeError("child NEEDS disagrees with the frozen root declaration")
            return answer
        except Exception as exc:
            self.failure = type(exc).__name__
            raise

    def probe(self):
        try:
            answer = self.ping()
        except (OSError, DeciderError) as exc:
            raise PracticeError("mandatory sandbox probe failed; no program was loaded") from exc
        if (answer.get("routed_interfaces") is None or set(answer["routed_interfaces"]) - {"lo"}
                or any(not (ipaddress.ip_address(a).is_loopback or ipaddress.ip_address(a).is_unspecified)
                       for a in answer.get("addresses", []))
                or any(k in answer.get("env", {}) for k in ("GATEWAY_TOKEN", "SAIL_API_KEY"))):
            raise PracticeError("sandbox probe reported unexpected network or credentials")
        return answer


def _write(path: Path, value: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as stream:
        stream.write(canonical(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.chmod(0o600)
    os.replace(tmp, path)


def check_state(root: Path, *, allow_scratch: bool = False) -> None:
    """Before any engine constructor: reject real state and every non-observe account."""
    if not root.exists():
        return
    if not root.is_dir() or root.is_symlink():
        raise PracticeError("state must be a private directory")
    allowed = {"live.sqlite", "live.sqlite-wal", "live.sqlite-shm", "live-shadow.json", "observe.sqlite",
               "observe.sqlite-wal", "observe.sqlite-shm", "swarm.json", "live-shadow.json.tmp",
               "progress.json", "progress.json.tmp"}
    for path in root.rglob("*"):
        scratch = allow_scratch and re.fullmatch(r"live-shadow\.json\.[a-z0-9_]{8}\.tmp", path.name)
        if (path.is_symlink() or not path.is_file() or (path.name not in allowed and not scratch)
                or path.stat().st_nlink != 1 or path.stat().st_uid != os.getuid()):
            raise PracticeError("unrecognized, linked or nonregular state file")
    dbpath = root / "live.sqlite"
    if dbpath.exists():
        db = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for name in ("instances", "positions", "orders", "fills"):
                if name in tables and db.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone():
                    raise PracticeError("real instance/order/position/fill state is forbidden")
        finally:
            db.close()
    path = root / "live-shadow.json"
    if path.exists():
        raw = _json(path.read_bytes())
        if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("accounts"), list):
            raise PracticeError("malformed shadow state")
        if any(not isinstance(r, dict) or not str(r.get("instance", "")).endswith(":o") for r in raw["accounts"]):
            raise PracticeError("non-observe shadow state is forbidden")


@contextmanager
def private_output(path: Path, input_path: Path):
    path, input_path = _plain_path(path), _plain_path(input_path)
    import numpy
    package = Path(numpy.__file__).resolve().parent
    mounts = (Path("/usr"), Path("/lib"), Path("/lib64"), package, package.parent / "numpy.libs")
    if any(p.is_relative_to(base) for p in (path, input_path) for base in mounts):
        raise PracticeError("input/output cannot be in a mounted system runtime tree")
    if path == REPO or path.is_relative_to(REPO) or input_path.is_relative_to(path) or path.is_relative_to(input_path):
        raise PracticeError("output must be separate from the checkout and input")
    created = False
    try:
        path.mkdir(mode=0o700)  # do not manufacture a missing parent or open an arbitrary existing tree
        created = True
    except FileExistsError:
        if (not path.is_dir() or path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o700
                or not (path / MARKER).is_file()):
            raise PracticeError("output must be new, or a marked owner-only local practice directory")
    if not created:
        allowed = {MARKER, "run.lock", "input.json", "input.json.tmp", "report.json", "state", "attempt", "report.json.tmp", MARKER + ".tmp"}
        if any(p.name not in allowed or p.is_symlink() or (p.is_file() and p.stat().st_nlink != 1) for p in path.iterdir()):
            raise PracticeError("unrecognized or linked output content")
    fd = os.open(path / "run.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PracticeError("another local practice run owns this output") from None
        yield path
    finally:
        os.close(fd)


def identity(bundle: dict) -> dict:
    import numpy
    from .gym.fills import FillModel
    from .swarm.evaluator import execution_fingerprint

    return {"schema": SCHEMA, "purpose": "local_simulation", "kind": bundle["kind"], "input_sha256": digest(bundle),
            "execution_sha256": execution_fingerprint.__wrapped__(), "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "extra_sources": {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in EXTRA_EVALUATOR_FILES},
            "python": sys.version, "numpy": numpy.__version__, "fill_model": {"basis": "natural_only", "version": FillModel().version},
            "programs": [{"family": p["family"], "version": p["version"], "sha256": digest(p)} for p in bundle["programs"]]}


def _state_hashes(root: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir()) if p.is_file()}


def _finalize_state(root: Path) -> None:
    """Seal durable SQLite bytes before hashing; read-only inspection must not create WAL/SHM artifacts.

    All engine/summary connections are closed by the caller. Checkpointing folds committed WAL data into the
    main files; DELETE mode then makes each completed DB self-contained. Never discard or ignore WAL bytes.
    A concurrent reader/writer that prevents finalization leaves an incomplete run, eligible for clean rebuild.
    """
    for name in ("live.sqlite", "observe.sqlite"):
        path = root / name
        if not path.exists():
            continue
        db = sqlite3.connect(path, timeout=1.0, isolation_level=None)
        try:
            busy, frames, checked = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if busy or (frames >= 0 and frames != checked):
                raise PracticeError("private SQLite checkpoint is busy or incomplete")
            if db.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
                raise PracticeError("private SQLite finalization failed")
        finally:
            db.close()
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise PracticeError("private SQLite sidecars remain after finalization")


def _simulate(bundle: dict, root: Path, provenance: dict, decider) -> dict:
    """Private engine seam for trusted-fixture unit tests. Public run() always supplies SandboxedDecider."""
    from .gym.fills import FillModel
    from .live.observe import practice_summary
    from .live.step import OptionsLive

    check_state(root)
    root.mkdir(mode=0o700, exist_ok=True)
    _write(root / "swarm.json", {"live": {"observe": True, "observe_max": MAX_PROGRAMS, "observe_roots_max": MAX_PROGRAMS,
                                         "observe_train": True, "calibration": False, "house_test": False}})
    market = RecordedMarket()
    families = ObserveOnlyFamilies(bundle["programs"])
    if isinstance(decider, SandboxedDecider):
        decider.expected_roots = {f"{p['family']}@{p['version']}:o": set(p["roots"]) for p in families.rows}
    market.now = _at(bundle["frames"][0]["at"])
    engine = OptionsLive(root, market=market, real=None, paper=None, families=families, real_money=False,
                         config={"thread": False}, decider=decider, observe_decider=decider,
                         fill_model=FillModel(), clock=lambda: market.now)
    engine.observe_store.evaluator = "local-simulation-natural-only:" + digest(provenance)
    begin = time.monotonic()
    summaries = []
    try:
        for index, frame in enumerate(bundle["frames"]):
            if time.monotonic() - begin > MAX_SECONDS:
                raise PracticeError("finite run exceeded its wall-time budget")
            market.select(frame)
            result = engine.minute()
            if getattr(decider, "failure", None) is not None:
                raise PracticeError("strategy sandbox failed; the run is incomplete")
            if any(i.error or i.fatal for i in engine.instances.values()):
                raise PracticeError("a local program was refused or disqualified; the run is incomplete")
            if (engine.book is not None or engine.proof is not None or engine.proof_single is not None
                    or any(not i.observe or i.kind != "shadow" for i in engine.instances.values())
                    or any(not k.endswith(":o") for k in engine.shadow.accounts)):
                raise PracticeError("non-observation execution state")
            summaries.append({"at": frame["at"], "state": result.get("state"), "shadow": result.get("shadow"),
                              "data_errors": result.get("data_errors", []), "decider_error": result.get("observe_decider")})
            _write(root / "progress.json", {"frames_completed": index + 1, "last_at": frame["at"],
                                           "input_sha256": provenance["input_sha256"], "use": DISCLAIMER})
        report = {"schema": SCHEMA, "kind": bundle["kind"], "label": bundle["label"], "use": DISCLAIMER,
                  "provenance": provenance, "frames": summaries, "summary": practice_summary(root),
                  "capabilities": {"history": "unavailable", "volume": "completed first-observed minute bars only",
                                   "incomplete_bars_withheld": market.incomplete_bars_withheld},
                  "admission": "Explicit local programs; no Train/Validation eligibility asserted.",
                  "end": "Input exhausted; open positions remain marked, not forcibly liquidated."}
    finally:
        engine.close()
        engine.state.close()
    _finalize_state(root)
    check_state(root)
    return report


def run(input_path: Path, output: Path) -> dict:
    """Finite public API. Mandatory sandbox is probed before any supplied program can load."""
    bundle = load_bundle(input_path)
    provenance = identity(bundle)
    with private_output(output, input_path) as root:
        marker = root / MARKER
        old = _json(marker.read_bytes()) if marker.exists() else None
        if old is not None and old.get("identity") != provenance:
            raise PracticeError("input/program/runtime identity changed; use a new output directory")
        if old and digest(_json((root / "input.json").read_bytes())) != provenance["input_sha256"]:
            raise PracticeError("the frozen input changed")
        for name in ("state", "attempt"):
            check_state(root / name, allow_scratch=name == "attempt" and bool(old) and old.get("status") == "running")
        if old and old.get("status") == "complete":
            report = _json((root / "report.json").read_bytes())
            if digest(report) != old.get("report_sha256"):
                raise PracticeError("completed report changed")
            if _state_hashes(root / "state") != old.get("state_sha256"):
                raise PracticeError("completed private state changed")
            return report
        _write(root / "input.json", bundle)
        _write(marker, {"identity": provenance, "status": "running", "use": DISCLAIMER})
        work = root / "attempt"
        if work.exists():
            shutil.rmtree(work)  # only the marked, prechecked private attempt; never resume half a multi-file commit
        if (root / "state").exists():
            shutil.rmtree(root / "state")
        decider = SandboxedDecider(memory_mb=1024)
        try:
            decider.probe()
            report = _simulate(bundle, work, provenance, decider)
        finally:
            decider.close()
        if identity(bundle) != provenance:
            raise PracticeError("runtime files changed during the simulation; the run is incomplete")
        report["recovery"] = "replayed_from_start" if old else "fresh"
        os.replace(work, root / "state")
        _write(root / "report.json", report)
        _write(marker, {"identity": provenance, "status": "complete", "report_sha256": digest(report),
                        "state_sha256": _state_hashes(root / "state"), "use": DISCLAIMER})
        return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.input, args.output)
    except (PracticeError, OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(2, f"Local practice refused: {exc}\n")
    print(json.dumps({"kind": report["kind"], "frames": len(report["frames"]), "use": report["use"],
                      "report": str(args.output.absolute() / "report.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
