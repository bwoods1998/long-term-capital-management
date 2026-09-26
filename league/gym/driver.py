"""The sealed-box driver: run a batch of programs on a Gym box through Sail's files and exec APIs.

    driver = GymDriver(SailboxClient(), "sb_...")        # any client with upload / download / exec
    driver.ensure_code()                                  # the engine's code bundle, once per version
    driver.check_data("train", ["SPY", "QQQ"])            # GymDataMissing when the box lacks the data
    doc = driver.run({"condor": code, "sweep": (code, [{"a": 1}, {"a": 2}])}, window="train", roots=["SPY"])

The box is sealed (`no_network`): code and programs go in as files, results come out as a file.
- The code bundle is a deterministic tar.gz of `league/gym/` and the four standard-library league
  modules it imports (`__init__`, `safety`, `structure_core`, `stats`); its version is the engine
  version plus the bundle's hash, unpacked under `<remote_root>/code/<version>/` with a READY mark,
  so it is uploaded once per engine version per box.
- A job is named by the hash of (bundle, programs, settings): its programs go to
  `<remote_root>/jobs/<job>/programs/`, the batch writes `results.json` there, and a job whose
  results already exist (a retry after a dropped stream) is downloaded, not run twice.
- Transient failures (HTTP 408/429/5xx, connection errors) are retried with backoff; a command that
  ran and failed is not. Exit 3 from the batch is `GymDataMissing` with the batch's own message, a
  timed-out exec is `GymTimeout`, anything else is `GymError` with the output's tail.

Standard library only (the House imports it; the box runs the bundle).
"""

from __future__ import annotations

import hashlib
import io
import json
import shlex
import tarfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import ENGINE_VERSION

REPO = Path(__file__).resolve().parents[2]
LEAGUE_FILES = ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/stats.py")
RETRYABLE = (408, 425, 429, 500, 502, 503, 504)


class GymError(RuntimeError):
    """A Gym box could not run the batch (the message says why)."""


class GymDataMissing(GymError):
    """The box lacks the store data (or the packages) the batch needs."""


class GymTimeout(GymError):
    """The batch ran past its time limit on the box."""


def build_bundle(repo: Path = REPO) -> tuple[bytes, str]:
    """(the tar.gz bytes, the bundle's version) of the Gym's code, byte-for-byte reproducible."""
    files = [repo / f for f in LEAGUE_FILES]
    gym = repo / "league" / "gym"
    files += sorted(p for p in gym.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".md"))
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(files, key=lambda p: p.relative_to(repo).as_posix()):
            data = path.read_bytes()
            info = tarfile.TarInfo(path.relative_to(repo).as_posix())
            info.size, info.mtime, info.mode, info.uid, info.gid = len(data), 0, 0o644, 0, 0
            tar.addfile(info, io.BytesIO(data))
    body = raw.getvalue()
    digest = hashlib.sha256(body).hexdigest()
    import gzip

    return gzip.compress(body, mtime=0), f"{ENGINE_VERSION}-{digest[:12]}"


def programs_archive(programs: Mapping[str, Any]) -> bytes:
    """A tar.gz of `<name>.py` (and `<name>.json` for parameter sets) from {name: code | (code, params)}."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(programs):
            if not name or "/" in name or name.startswith("."):
                raise GymError(f"a program name is a plain file stem, not {name!r}")
            value = programs[name]
            code, params = (value, None) if isinstance(value, str) else (value[0], value[1])
            members = [(f"{name}.py", code.encode("utf-8"))]
            if params is not None:
                members.append((f"{name}.json", json.dumps(params, sort_keys=True).encode()))
            for member, data in members:
                info = tarfile.TarInfo(member)
                info.size, info.mtime, info.mode = len(data), 0, 0o644
                tar.addfile(info, io.BytesIO(data))
    import gzip

    return gzip.compress(raw.getvalue(), mtime=0)


class GymDriver:
    """Runs Gym batches on one sealed box."""

    def __init__(self, client: Any, box: str, *, remote_root: str = "/workspace/gym", store_root: str = "/data/store",
                 python: str = "python3", retries: int = 3, backoff: float = 2.0, sleep: Callable[[float], None] = time.sleep,
                 repo: Path = REPO, cleanup: bool = True):
        self.client = client
        self.box = box
        self.remote_root = remote_root.rstrip("/")
        self.store_root = store_root
        self.python = python
        self.retries = max(1, int(retries))
        self.backoff = float(backoff)
        self.sleep = sleep
        self.cleanup = cleanup
        self._bundle, self.version = build_bundle(repo)
        self.code_dir = f"{self.remote_root}/code/{self.version}"
        self.calls: list[str] = []

    # ------------------------------------------------------------------ transport
    def _retry(self, what: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                self.calls.append(what)
                return fn(*args, **kwargs)
            except Exception as exc:  # the real client raises SailboxError(status=...), transports OSError
                status = getattr(exc, "status", None)
                transient = (status in RETRYABLE) or (status is None and isinstance(exc, (OSError, ConnectionError, TimeoutError)))
                if not transient or attempt == self.retries - 1:
                    raise GymError(f"{what} failed on {self.box}: {exc}") from exc
                last = exc
                self.sleep(self.backoff * (2 ** attempt))
        raise GymError(f"{what} failed on {self.box}: {last}")  # pragma: no cover

    def _exec(self, command: str, *, timeout: int = 600) -> Any:
        return self._retry("exec", self.client.exec, self.box, command, timeout=timeout)

    @staticmethod
    def _tail(result: Any) -> str:
        return (str(getattr(result, "stderr", "") or "") + str(getattr(result, "stdout", "") or ""))[-600:].strip()

    # ------------------------------------------------------------------ the code
    def ensure_code(self) -> str:
        """Upload and unpack the code bundle unless this version is already on the box; return its path."""
        q = shlex.quote
        probe = self._exec(f"test -f {q(self.code_dir + '/READY')}", timeout=60)
        if getattr(probe, "return_code", 1) == 0:
            return self.code_dir
        archive = f"{self.code_dir}.tgz"
        self._retry("upload", self.client.upload, self.box, archive, self._bundle)
        unpack = self._exec(f"mkdir -p {q(self.code_dir)} && tar -xzf {q(archive)} -C {q(self.code_dir)} && "
                            f"touch {q(self.code_dir + '/READY')}", timeout=300)
        if getattr(unpack, "return_code", 1) != 0:
            raise GymError(f"unpacking the Gym's code failed: {self._tail(unpack)}")
        return self.code_dir

    def _batch(self, args: str) -> str:
        q = shlex.quote
        return f"cd {q(self.code_dir)} && PYTHONHASHSEED=0 {q(self.python)} -m league.gym.batch {args}"

    def check_data(self, window: str, roots: Sequence[str]) -> dict:
        """What the box's store holds for the window and roots; GymDataMissing when a root has no day."""
        q = shlex.quote
        self.ensure_code()
        deps = self._exec(f"{q(self.python)} -c 'import numpy, pyarrow'", timeout=120)
        if getattr(deps, "return_code", 1) != 0:
            raise GymDataMissing(f"the box lacks numpy or pyarrow for {self.python}: {self._tail(deps)}")
        result = self._exec(self._batch(f"--check --window {q(window)} --roots {q(','.join(roots))} --store {q(self.store_root)}"),
                            timeout=300)
        code = getattr(result, "return_code", None)
        if code == 3:
            raise GymDataMissing(self._tail(result) or f"the box is missing {window} data for {', '.join(roots)}")
        if code != 0:
            raise GymError(f"the data check failed (exit {code}): {self._tail(result)}")
        return json.loads(str(result.stdout).strip().splitlines()[-1])

    # ------------------------------------------------------------------ a batch
    def job_id(self, programs: Mapping[str, Any], settings: Mapping[str, Any]) -> str:
        body = json.dumps({"bundle": self.version, "programs": {k: programs[k] for k in sorted(programs)}, "settings": settings},
                          sort_keys=True, default=list)
        return hashlib.sha256(body.encode()).hexdigest()[:20]

    def run(self, programs: Mapping[str, Any], *, window: str, roots: Sequence[str], workers: int = 8, split: int = 1,
            stress: float = 1.0, capital: float = 10_000.0, detail: str = "full", start: str | None = None,
            end: str | None = None, gate_reason: str | None = None, timeout: int = 3600) -> dict:
        """Run `programs` ({name: code} or {name: (code, params or [params, ...])}) and return the batch's document."""
        if not programs:
            raise GymError("no programs to run")
        if window == "validation" and (start or end):
            raise GymError("a validation run is the whole window: no start or end cut")
        q = shlex.quote
        settings = {"window": window, "roots": [r.upper() for r in roots], "workers": int(workers), "split": int(split),
                    "stress": float(stress), "capital": float(capital), "detail": detail, "start": start, "end": end,
                    "gate": gate_reason, "store": self.store_root}
        self.ensure_code()
        job = self.job_id(programs, settings)
        jobdir = f"{self.remote_root}/jobs/{job}"
        out = f"{jobdir}/results.json"
        done = self._exec(f"test -f {q(out)}", timeout=60)
        if getattr(done, "return_code", 1) != 0:
            self._retry("upload", self.client.upload, self.box, f"{jobdir}/programs.tgz", programs_archive(programs))
            args = (f"--programs {q(jobdir + '/programs')} --window {q(window)} --roots {q(','.join(settings['roots']))} "
                    f"--store {q(self.store_root)} --out {q(out)} --workers {int(workers)} --split {int(split)} "
                    f"--stress {float(stress)} --capital {float(capital)} --detail {q(detail)}")
            if start:
                args += f" --start {q(start)}"
            if end:
                args += f" --end {q(end)}"
            if gate_reason:
                args += f" --gate {q(gate_reason)}"
            command = (f"mkdir -p {q(jobdir + '/programs')} && tar -xzf {q(jobdir + '/programs.tgz')} -C {q(jobdir + '/programs')} && "
                       + self._batch(args))
            result = self._exec(command, timeout=int(timeout))
            status = str(getattr(result, "status", ""))
            code = getattr(result, "return_code", None)
            if status == "timed_out":
                raise GymTimeout(f"the batch ran past {timeout} s on {self.box}")
            if code == 3:
                raise GymDataMissing(self._tail(result))
            if code == 4:
                raise GymError(f"the box refused a sealed window: {self._tail(result)}")
            if code != 0:
                raise GymError(f"the batch failed (exit {code}, status {status}): {self._tail(result)}")
        raw = self._retry("download", self.client.download, self.box, out)
        doc = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        if len(doc.get("results") or []) < len(programs):
            raise GymError(f"the batch returned {len(doc.get('results') or [])} results for {len(programs)} programs")
        doc["batch"]["job"] = job
        doc["batch"]["bundle"] = self.version
        if self.cleanup:
            self._exec(f"rm -rf {q(jobdir)}", timeout=120)
        return doc


__all__ = ["GymDriver", "GymError", "GymDataMissing", "GymTimeout", "build_bundle", "programs_archive"]
