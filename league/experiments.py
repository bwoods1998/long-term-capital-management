"""Content-addressed replay inputs and evaluator code, retained before paid execution.

The cache name describes a query; the artifact hash identifies the exact bytes used. Artifacts
are private to the House, written atomically and never overwritten. A started experiment without
a finish remains visible after a crash. Reproduction runs the archived kit, not today's evaluator.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from .ledger import Ledger, canonical

HEX = re.compile(r"^[0-9a-f]{64}$")


class ArtifactError(ValueError):
    pass


class Archive:
    def __init__(self, root: str | Path, *, max_artifact_bytes: int = 512 * 1024 * 1024):
        self.root = Path(root)
        self.max_artifact_bytes = max_artifact_bytes
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, ident: str) -> Path:
        if not isinstance(ident, str) or not HEX.fullmatch(ident):
            raise ArtifactError("invalid artifact identity")
        return self.root / ident[:2] / (ident + ".json.gz")

    def put(self, value: Any) -> str:
        if shutil.disk_usage(self.root).free < 256 * 1024 * 1024:
            raise ArtifactError("archive disk reserve reached; stop before paid execution")
        digest, size = hashlib.sha256(), 0
        fd, name = tempfile.mkstemp(prefix=".artifact-", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as out:
                with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as compressed:
                    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                    buffered = bytearray()
                    for chunk in encoder.iterencode(value):
                        raw = chunk.encode("utf-8")
                        size += len(raw)
                        if size > self.max_artifact_bytes:
                            raise ArtifactError("artifact exceeds archive limit")
                        digest.update(raw)
                        buffered.extend(raw)
                        if len(buffered) >= 65536:
                            compressed.write(buffered)
                            buffered.clear()
                    if buffered:
                        compressed.write(buffered)
                out.flush()
                os.fsync(out.fileno())
            ident = digest.hexdigest()
            path = self.path(ident)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.link(name, path)  # publish a complete file without replacing an existing one
            except FileExistsError:
                self.verify(ident)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            os.unlink(name)
        return ident

    def verify(self, ident: str) -> None:
        digest, size = hashlib.sha256(), 0
        try:
            with gzip.open(self.path(ident), "rb") as source:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_artifact_bytes:
                        raise ArtifactError("artifact exceeds archive limit")
                    digest.update(chunk)
        except (OSError, EOFError) as exc:
            raise ArtifactError(f"unreadable artifact {ident}") from exc
        if digest.hexdigest() != ident:
            raise ArtifactError(f"artifact digest mismatch: {ident}")

    def get(self, ident: str) -> Any:
        try:
            with gzip.open(self.path(ident), "rb") as source:
                raw = source.read(self.max_artifact_bytes + 1)
        except (OSError, EOFError) as exc:
            raise ArtifactError(f"unreadable artifact {ident}") from exc
        if len(raw) > self.max_artifact_bytes or hashlib.sha256(raw).hexdigest() != ident:
            raise ArtifactError(f"artifact digest mismatch: {ident}")
        return json.loads(raw)


class Experiments:
    def __init__(self, root: str | Path, ledger: Ledger, *, clock=time.time):
        self.archive = Archive(root)
        self.ledger, self.clock = ledger, clock
        self._kit: str | None = None

    def begin(self, *, agent: str, family: str, lineage: list[str], code: str,
              params: Mapping[str, Any], needs: Mapping[str, Any], tape: Mapping[str, Any],
              query: str, stake: float, limits: Mapping[str, Any]) -> dict[str, Any]:
        from .sandbox import kit_files

        if self._kit is None:
            self._kit = self.archive.put({name: Path(path).read_text(encoding="utf-8") for name, path in kit_files().items()})
        tape_id = self.archive.put(tape)
        manifest = {
            "schema": 1, "kind": "historical_replay", "code": self.archive.put({"code": code}),
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "params": dict(params), "needs": dict(needs), "tape": tape_id, "query": query,
            "evaluator": self._kit, "python": list(sys.version_info[:3]),
            "stake": stake, "limits": dict(limits),
            "validation": "reused_development_tail_not_independent_forward_evidence",
        }
        ident = self.archive.put(manifest)
        attempt = secrets.token_hex(16)
        self.ledger.append("experiment.started", {"attempt": attempt, "manifest": ident,
            "tape": tape_id, "evaluator": self._kit, "family": family, "lineage": lineage},
            agent=agent, id=f"experiment:{attempt}:started")
        return {"attempt": attempt, "manifest": ident, "tape": tape_id, "evaluator": self._kit,
                "started": self.clock(), "agent": agent}

    def finish(self, attempt: Mapping[str, Any], result: Mapping[str, Any], *, seconds: float = 0) -> dict[str, Any]:
        result_id = self.archive.put(result)
        row = {"attempt": attempt["attempt"], "manifest": attempt["manifest"], "result": result_id,
               "tape": attempt["tape"], "evaluator": attempt["evaluator"],
               "elapsed_seconds": max(0, self.clock() - attempt["started"]),
               "sandbox_seconds": max(0, seconds), "ok": bool(result.get("ok"))}
        self.ledger.append("experiment.finished", row, agent=attempt["agent"],
                           id=f"experiment:{attempt['attempt']}:finished")
        return {key: row[key] for key in ("attempt", "manifest", "result", "tape", "evaluator")}


def reproduce(archive: Archive, manifest_id: str, *, timeout: float = 600) -> dict[str, Any]:
    """Replay in a temporary subprocess with an empty credential environment and archived code.

    Use inside an isolated offline environment, as with LocalSandbox. This is not a network
    sandbox for arbitrary untrusted artifacts; production replay continues to use sealed boxes.
    """
    manifest = archive.get(manifest_id)
    if manifest.get("schema") != 1 or manifest.get("kind") != "historical_replay":
        raise ArtifactError("not a supported replay manifest")
    if manifest["python"][:2] != list(sys.version_info[:2]):
        raise ArtifactError("reproduction requires the recorded Python major/minor version")
    kit = archive.get(manifest["evaluator"])
    spec = {"code": archive.get(manifest["code"])["code"], "params": manifest["params"],
            "tape": archive.get(manifest["tape"]), "stake": manifest["stake"], "limits": manifest["limits"]}
    if hashlib.sha256(spec["code"].encode("utf-8")).hexdigest() != manifest["code_sha256"]:
        raise ArtifactError("strategy digest does not match manifest")
    token = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix="ltcm-reproduce-") as directory:
        root = Path(directory)
        for name, source in kit.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or not name.endswith(".py"):
                raise ArtifactError("invalid archived evaluator path")
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        (root / "spec.json").write_text(canonical({**spec, "token": token}), encoding="utf-8")
        done = subprocess.run([sys.executable, "-E", "-s", "replay.py", "--spec", "spec.json"],
                              cwd=root, env={"PATH": os.defpath}, capture_output=True, text=True, timeout=timeout)
        from .runner import parse_result
        result = parse_result(done.stdout, token, "REPLAY-RESULT")
        if result is None:
            raise ArtifactError(f"archived replay returned no result (exit {done.returncode})")
        return result


def reproduce_evaluation(archive: Archive, ident: str, *, timeout: float = 30) -> dict[str, Any]:
    """Recompute a historical selection verdict using its archived judge and trial inputs.

    Like reproduce(), this executes archived source: use an isolated offline environment.
    """
    evaluation = archive.get(ident)
    policy = archive.get(evaluation['policy'])
    if policy['python'][:2] != list(sys.version_info[:2]):
        raise ArtifactError('judgment reproduction requires the recorded Python major/minor')
    with tempfile.TemporaryDirectory(prefix='ltcm-judge-') as directory:
        root = Path(directory)
        package = root / 'league'
        package.mkdir()
        (package / '__init__.py').write_text('')
        for name in ('evaluator.py', 'stats.py', 'ledger.py'):
            (package / name).write_text(policy['sources'][name], encoding='utf-8')
        (package / 'constitution.py').write_text('import json\nCONSTITUTION=json.loads(' + repr(canonical(policy['constitution'])) + ')\n', encoding='utf-8')
        inputs = {**evaluation, 'result': archive.get(evaluation['result'])}
        (root / 'inputs.json').write_text(canonical(inputs), encoding='utf-8')
        program = '''import json
from league.ledger import Ledger
from league.evaluator import Evaluator
data=json.load(open('inputs.json'))
ledger=Ledger('ledger.sqlite')
family=data['verdict']['family']
for score in data['prior_trial_sharpes']:
    ledger.append('eval.trial', {'family':family, 'sharpe':score}, agent='prior')
verdict=Evaluator(ledger).record_trial('candidate',family,data['result'],tape_id=data['verdict']['tape'],promote=False)
print(json.dumps(verdict.numbers,sort_keys=True,allow_nan=False))
ledger.close()
'''
        (root / 'judge.py').write_text(program, encoding='utf-8')
        done = subprocess.run([sys.executable, '-E', '-s', 'judge.py'], cwd=root,
                              env={'PATH': os.defpath}, capture_output=True, text=True, timeout=timeout)
        if done.returncode:
            raise ArtifactError(f'archived judge failed (exit {done.returncode})')
        return json.loads(done.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs='?')
    parser.add_argument('--evaluation', help='verify and reproduce this archived selection decision')
    parser.add_argument("--root", type=Path, required=True, help="House state directory")
    parser.add_argument("--reproduce", action="store_true", help="execute the archived evaluator in a local subprocess")
    parser.add_argument("--expected-result", help="compare the reproduced result with this artifact")
    args = parser.parse_args()
    archive = Archive(args.root / "experiments")
    if args.evaluation:
        expected = archive.get(args.evaluation)['verdict']
        result = reproduce_evaluation(archive, args.evaluation)
        matches = canonical(expected) == canonical(result)
        print(json.dumps({'evaluation': args.evaluation, 'matches': matches, 'verdict': result}, indent=2))
        raise SystemExit(0 if matches else 1)
    if not args.manifest:
        parser.error('give a manifest or --evaluation')
    manifest = archive.get(args.manifest)
    for key in ("tape", "code", "evaluator"):
        archive.get(manifest[key])
    output: dict[str, Any] = {"manifest": args.manifest, "verified": True, "details": manifest}
    if args.reproduce:
        result = reproduce(archive, args.manifest)
        output["result"] = result
        if args.expected_result:
            output["matches"] = canonical(result) == canonical(archive.get(args.expected_result))
    print(json.dumps(output, indent=2))
    if output.get("matches") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
