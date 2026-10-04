"""Pack reviewed Git bytes for the standalone research host; no deployment or provider calls.

The artifact has no Git history, runtime databases, credentials or market datasets.
Its manifest lives beside the artifact so every mounted file has an independent hash.
The rollback drill switches only disposable code pointers and proves state bytes stay put.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess


class ResearchReleaseError(RuntimeError):
    pass


def _git(repo, *args):
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], capture_output=True, check=True)
    return result.stdout


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _json(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _configuration(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResearchReleaseError("controller configuration contains a credential capability")
            normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
            normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized).replace("-", "_").lower()
            if re.search(r"(?:^|_)(?:api_key|api_secret|password|private_key|token|secret|credentials?|authorization|auth|league_env)$", normalized):
                raise ResearchReleaseError("controller configuration contains a credential capability")
            _configuration(item)
    elif isinstance(value, list):
        for item in value:
            _configuration(item)


def _path(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or PurePosixPath(name).as_posix() != name or any(p in (".", "..") for p in parts):
        raise ResearchReleaseError("release path is not plain")
    return parts


def _artifact_path(name):
    parts = _path(name)
    # Code needed by the existing actors and their evaluator fingerprint; no data files.
    return (parts[0] in ("league", "ltcm") and name.endswith((".py", ".md"))
            and not any(p in ("tests", "__pycache__", ".git") or p.startswith(".") for p in parts))


def _write(path, body):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def pack(repo: Path, head: str, destination: Path, *, config: dict, policy: dict) -> dict:
    """Export immutable commit blobs, including exact explicit configuration documents."""
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not isinstance(config, dict) or not isinstance(policy, dict):
        raise ResearchReleaseError("exact commit and explicit configuration documents required")
    _configuration(config)
    _configuration(policy)
    repo, destination = repo.resolve(), destination.absolute()
    if destination.exists() or destination.is_symlink() or destination.parent.resolve() != destination.parent:
        raise ResearchReleaseError("use a fresh destination under a plain existing parent")
    if destination == repo or repo in destination.parents:
        raise ResearchReleaseError("release output must be outside the checkout")
    if _git(repo, "rev-parse", head + "^{commit}").decode().strip() != head:
        raise ResearchReleaseError("exact committed source required")
    files = []
    for record in _git(repo, "ls-tree", "-rz", "--full-tree", head).split(b"\0"):
        if not record:
            continue
        meta, raw_name = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        name = raw_name.decode()
        if not _artifact_path(name):
            continue
        if mode not in ("100644", "100755") or kind != "blob":
            raise ResearchReleaseError("reviewed code may not contain symlinks or submodules")
        files.append((name, oid))
    required = {"league/swarm/research_controller.py", "league/swarm/research_state.py",
                "league/swarm/research_adapters.py", "league/swarm/research_ipc.py",
                "league/swarm/research_host.py", "league/swarm/research_sandbox.py",
                "league/swarm/research_transport.py", "league/swarm/daily_compute.py"}
    if not required <= {name for name, _ in files}:
        raise ResearchReleaseError("commit does not contain the standalone research authority")
    destination.mkdir(mode=0o700)
    artifact = destination / "artifact"
    artifact.mkdir(mode=0o700)
    try:
        for name, oid in files:
            _write(artifact / name, _git(repo, "cat-file", "blob", oid))
        _write(artifact / "research-config.json", _json(config))
        _write(artifact / "research-policy.json", _json(policy))
        manifest = {p.relative_to(artifact).as_posix(): _sha(p.read_bytes()) for p in sorted(artifact.rglob("*")) if p.is_file()}
        receipt = {"schema": 1, "head": head, "artifact": str(artifact), "files": manifest,
                   "config_relative": "research-config.json", "policy_relative": "research-policy.json",
                   "provider_calls": 0, "deployed": False}
        body = _json(receipt)
        _write(destination / "release.json", body)
        return {**receipt, "receipt_sha256": _sha(body)}
    except BaseException:
        shutil.rmtree(destination)
        raise


def verify_release(receipt_path: Path, *, approved_sha256: str) -> dict:
    body = receipt_path.read_bytes()
    if not isinstance(approved_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", approved_sha256) or _sha(body) != approved_sha256:
        raise ResearchReleaseError("release receipt differs from its independently approved SHA256")
    receipt = json.loads(body)
    if not isinstance(receipt, dict) or receipt.get("schema") != 1 or not isinstance(receipt.get("files"), dict):
        raise ResearchReleaseError("release receipt is incomplete")
    artifact = Path(receipt["artifact"])
    if artifact.resolve() != artifact or not artifact.is_dir():
        raise ResearchReleaseError("artifact root is not plain")
    files = {}
    for path in artifact.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ResearchReleaseError("release has an unreviewed filesystem object")
        if path.is_file():
            files[path.relative_to(artifact).as_posix()] = _sha(path.read_bytes())
    if files != receipt["files"]:
        raise ResearchReleaseError("artifact differs from its reviewed manifest")
    return {**receipt, "receipt_sha256": approved_sha256}


def rollback_drill(previous_receipt: Path, candidate_receipt: Path, state_root: Path, output: Path, *,
                   previous_sha256: str, candidate_sha256: str) -> dict:
    """A source-pointer rehearsal only; real host lifecycle/billing checks are separate."""
    previous = verify_release(previous_receipt, approved_sha256=previous_sha256)
    candidate = verify_release(candidate_receipt, approved_sha256=candidate_sha256)
    state_root, output = state_root.resolve(), output.absolute()
    if not state_root.is_dir() or output.exists() or output.parent.resolve() != output.parent:
        raise ResearchReleaseError("existing state and fresh plain drill output required")
    code_roots = (Path(previous["artifact"]), Path(candidate["artifact"]))
    if any(root == state_root or root in state_root.parents or state_root in root.parents for root in code_roots):
        raise ResearchReleaseError("research state must stay outside both code artifacts")
    if any(root == output or root in output.parents or output in root.parents for root in code_roots):
        raise ResearchReleaseError("drill output must stay outside both code artifacts")
    if state_root == output or state_root in output.parents or output in state_root.parents:
        raise ResearchReleaseError("drill output must be outside durable state")
    def state_hashes():
        rows = {}
        for path in state_root.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ResearchReleaseError("durable state has an unreviewed filesystem object")
            if path.is_file():
                rows[path.relative_to(state_root).as_posix()] = _sha(path.read_bytes())
        return rows
    before = state_hashes()
    output.mkdir(mode=0o700)
    current = output / "current"
    previous_link = output / "previous"
    current.symlink_to(code_roots[0], target_is_directory=True)
    previous_link.symlink_to(code_roots[0], target_is_directory=True)
    def point(root):
        temporary = output / ".next"
        temporary.symlink_to(root, target_is_directory=True)
        os.replace(temporary, current)
        descriptor = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    point(code_roots[1])
    candidate_seen = current.resolve() == code_roots[1]
    point(previous_link.resolve())
    restored = current.resolve() == code_roots[0]
    after = state_hashes()
    if not candidate_seen or not restored or before != after:
        raise ResearchReleaseError("rollback did not restore code and preserve state bytes")
    receipt = {"schema": 1, "candidate_head": candidate["head"], "previous_head": previous["head"],
               "source_pointer_restored": restored, "durable_state_unchanged": True, "state_sha256": before,
               "provider_calls": 0, "controller_lifecycle_rehearsed": False, "production_deployed": False}
    _write(output / "rollback.json", _json(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("pack")
    export.add_argument("--repo", type=Path, required=True)
    export.add_argument("--head", required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--config", type=Path, required=True)
    export.add_argument("--policy", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--receipt", type=Path, required=True)
    check.add_argument("--receipt-sha256", required=True)
    drill = sub.add_parser("drill")
    for name in ("previous", "candidate", "state", "output"):
        drill.add_argument("--" + name, type=Path, required=True)
    drill.add_argument("--previous-sha256", required=True)
    drill.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args(argv)
    if args.operation == "pack":
        result = pack(args.repo, args.head, args.output, config=json.loads(args.config.read_text()), policy=json.loads(args.policy.read_text()))
    elif args.operation == "verify":
        result = verify_release(args.receipt, approved_sha256=args.receipt_sha256)
    else:
        result = rollback_drill(args.previous, args.candidate, args.state, args.output,
                                previous_sha256=args.previous_sha256, candidate_sha256=args.candidate_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
