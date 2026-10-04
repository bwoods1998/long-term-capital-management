"""Host-only Bubblewrap launch and fresh kernel observations of an isolated peer.

The production entry is fixed to research_controller; a disposable probe entry can
exercise Linux isolation but cannot produce a paid IsolationProof. This module has
no provider or credential factory and never launches anything at import. Approval
of exact-head CI, rollback, billing and deployment time remains a host responsibility.
The separate host-context receipt is explicit trusted evidence for global facts a
namespace observer cannot prove (billing authority, Gym data and reviewed adapters).
Missing or denied /proc evidence fails closed, without a claimed-boolean fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import socket
import stat
import struct
import subprocess
import time
from dataclasses import dataclass

from .research_transport import IsolationProof, PeerIdentity, ISOLATION_FACTS, NAMESPACE_FACTS

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SCOPE = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
_PHYSICAL = frozenset(("controller_credentials_absent", "production_mounts_absent",
                       "controller_network_only_broker", "kernel_peer_authenticated")) | NAMESPACE_FACTS
_EXTERNAL = ISOLATION_FACTS - _PHYSICAL
_ENV = {"PATH": "/usr/bin", "PYTHONPATH": "/artifact", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C.UTF-8"}
_ENV_OBSERVED = {**_ENV, "PWD": "/state"}


class SandboxError(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise SandboxError(reason)


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _json(body):
    def pairs(items):
        out = {}
        for key, value in items:
            _require(key not in out, "duplicate sandbox evidence field")
            out[key] = value
        return out
    return json.loads(body, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(SandboxError("nonfinite sandbox evidence")))


def _digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _plain(path, *, private=False):
    path = Path(path)
    _require(path.is_absolute() and path.resolve() == path, "sandbox mount needs a plain absolute path")
    for part in (path, *path.parents):
        _require(not part.is_symlink(), "symlinked sandbox mount is refused")
    if private:
        info = path.stat()
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                 "sandbox state must be host-owned and private")
    return path


def _disjoint(*paths):
    _require(not any(a == b or a in b.parents or b in a.parents for i, a in enumerate(paths) for b in paths[i + 1:]),
             "artifact, state and broker-private roots must be disjoint")


def _relative(value):
    _require(isinstance(value, str) and PurePosixPath(value).as_posix() == value and not value.startswith("/")
             and all(p not in ("", ".", "..") for p in value.split("/")), "invalid reviewed artifact path")
    return value


@dataclass(frozen=True)
class SandboxSpec:
    scope: str
    artifact_root: Path
    artifact_files: tuple[tuple[str, str], ...]
    state_root: Path
    broker_socket: Path
    broker_uid: int
    image: str
    roots: tuple[str, ...]
    config_relative: str
    policy_relative: str
    expected_evaluator: object = None

    def __post_init__(self):
        _require(all(isinstance(path, Path) for path in (self.artifact_root, self.state_root, self.broker_socket)), "explicit filesystem paths required")
        _require(isinstance(self.scope, str) and bool(_SCOPE.fullmatch(self.scope)), "invalid isolated scope")
        _require(type(self.broker_uid) is int and self.broker_uid >= 0, "explicit broker UID required")
        _require(isinstance(self.image, str) and re.fullmatch(r"sbcp_[0-9a-fA-F-]{8,64}", self.image), "reviewed Train/Validation checkpoint required")
        _require(isinstance(self.roots, tuple) and self.roots and len(set(self.roots)) == len(self.roots)
                 and all(re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", root) for root in self.roots), "invalid approved roots")
        _relative(self.config_relative)
        _relative(self.policy_relative)
        _require(isinstance(self.artifact_files, tuple) and self.artifact_files and len(dict(self.artifact_files)) == len(self.artifact_files),
                 "exact reviewed artifact file manifest required")
        for path, sha in self.artifact_files:
            _relative(path)
            _require(isinstance(sha, str) and _SHA.fullmatch(sha), "exact artifact SHA256 required")
        _require({self.config_relative, self.policy_relative} <= dict(self.artifact_files).keys(), "configuration must be in reviewed artifact")

    def controller_argv(self):
        return ("/usr/bin/python3", "-m", "league.swarm.research_controller", "--state", "/state",
                "--artifact", "/artifact", "--scope", self.scope, "--image", self.image,
                "--broker-socket", "/broker.sock", "--broker-uid", str(self.broker_uid),
                "--config", "/artifact/" + self.config_relative, "--policy", "/artifact/" + self.policy_relative,
                "--roots", ",".join(self.roots))


@dataclass(frozen=True)
class HostContextEvidence:
    """Exact host-approved private receipt; it is never supplied by the controller."""
    receipt_path: Path
    approved_sha256: str


def _host_context(evidence, spec, now):
    _require(isinstance(evidence, HostContextEvidence) and isinstance(evidence.approved_sha256, str)
             and _SHA.fullmatch(evidence.approved_sha256), "fresh trusted host-context evidence required")
    path = _plain(evidence.receipt_path)
    info = path.stat()
    _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o077,
             "host-context receipt must be owner-only")
    _disjoint(spec.artifact_root, spec.state_root, path.parent)
    body = path.read_bytes()
    _require(_sha(body) == evidence.approved_sha256, "host-context receipt changed")
    value = _json(body)
    _require(set(value) == {"schema", "scope", "broker_uid", "broker_root", "policy_digest", "observed_at", "valid_until",
                            "facts", "runbook", "adapters", "provenance"} and value["schema"] == 1,
             "host-context receipt schema is incomplete")
    _require(value["scope"] == spec.scope and value["broker_uid"] == spec.broker_uid
             and isinstance(value["policy_digest"], str) and _SHA.fullmatch(value["policy_digest"]), "host context differs from sandbox scope")
    start, end = value["observed_at"], value["valid_until"]
    _require(type(start) in (int, float) and type(end) in (int, float) and 0 <= start <= now <= end <= start + 300,
             "host-context observation expired")
    _require(isinstance(value["facts"], list) and set(value["facts"]) == _EXTERNAL and len(value["facts"]) == len(_EXTERNAL)
             and isinstance(value["provenance"], str) and value["provenance"].strip(), "global budget/Gym/review facts need explicit trusted evidence")
    broker_root = _plain(Path(value["broker_root"]), private=True)
    _disjoint(spec.artifact_root, spec.state_root, broker_root)
    for record in [value["runbook"], *value["adapters"]]:
        _require(isinstance(record, dict) and set(record) == {"path", "sha256"}, "reviewed runbook/adapter files required")
        file = _plain(Path(record["path"]))
        _require(_SHA.fullmatch(record["sha256"]) and _sha(file.read_bytes()) == record["sha256"], "reviewed host runbook/adapter changed")
    _require(value["adapters"], "reviewed host adapters required")
    value["adapters_sha256"] = _digest(value["adapters"])
    return value


def _verify_artifact(spec):
    root = _plain(spec.artifact_root)
    _require(root.is_dir(), "reviewed artifact directory missing")
    expected = dict(spec.artifact_files)
    found = {}
    for path in root.rglob("*"):
        _require(not path.is_symlink(), "artifact symlink could escape the approved mount")
        _require(path.name not in {".env", ".git", "swarm.sqlite", "money.sqlite", "book.sqlite", "provider.sqlite"},
                 "artifact contains private runtime or credential state")
        if path.is_file():
            _require(stat.S_ISREG(path.stat().st_mode), "artifact must contain only ordinary reviewed files")
            found[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
        else:
            _require(path.is_dir(), "nonordinary artifact object refused")
    _require(found == expected, "artifact files differ from exact reviewed manifest")
    return _digest(found)


def _verify_state_tree(root):
    for path in root.rglob("*"):
        info = path.lstat()
        _require(not path.is_symlink() and (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)),
                 "state contains an unapproved socket, device or symlink capability")
        _require(path.name not in {".env", "money.sqlite", "book.sqlite", "provider.sqlite"},
                 "state contains financial or credential files")


def _read_proc(pid, name, *, link=False):
    try:
        path = Path("/proc") / str(pid) / name
        return os.readlink(path) if link else path.read_bytes()
    except OSError as exc:
        raise SandboxError("fresh host /proc evidence unavailable; authenticated isolation attestation is still required") from exc


def _birth(pid):
    raw = _read_proc(pid, "stat").decode()
    # comm may contain spaces and parentheses; Linux's closing delimiter precedes fixed fields.
    fields = raw[raw.rfind(")") + 2:].split()
    _require(len(fields) >= 20 and fields[0] != "Z", "sandbox process is absent or exited")
    return int(fields[19]), int(fields[1])


def _unescape(raw):
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), raw)


def _mounts(raw):
    out = {}
    for line in raw.decode().splitlines():
        before, after = line.split(" - ", 1)
        fields, filesystem = before.split(), after.split()
        target = _unescape(fields[4])
        _require(target not in out, "overmounted sandbox path refused")
        out[target] = {"root": _unescape(fields[3]), "options": fields[5].split(","), "fs": filesystem[0]}
    return out


@dataclass(frozen=True)
class NamespaceObservation:
    scope: str
    peer: PeerIdentity
    peer_starttime: int
    namespaces: dict[str, str]
    mounts_sha256: str
    network_sha256: str
    observed_at: float
    probe_only: bool


class SandboxProcess:
    def __init__(self, spec, process, namespace_status, *, probe_only, artifact_sha256, status_fd):
        self.spec, self.process, self.namespace_status = spec, process, namespace_status
        self.probe_only, self.artifact_sha256 = probe_only, artifact_sha256
        self.status_fd = status_fd
        self.launch_starttime = _birth(process.pid)[0]
        self.peer_births = {}
        self.host_namespaces = {n: _read_proc(os.getpid(), "ns/" + n, link=True) for n in ("user", "pid", "mnt", "net")}
        # --disable-userns enters a nested namespace for the command after the
        # reaper starts. Pin that actual kernel peer namespace at first full
        # observation, rather than incorrectly equating it with the reaper's.
        self.captured_peer_user_namespace = None

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)
        for pipe in (self.process.stdout, self.process.stderr):
            if pipe:
                pipe.close()
        if self.status_fd is not None:
            os.close(self.status_fd)
            self.status_fd = None

    def observe_peer(self, peer):
        _require(isinstance(peer, PeerIdentity) and self.process.poll() is None, "live kernel peer and launched sandbox required")
        _require(_birth(self.process.pid)[0] == self.launch_starttime, "sandbox launch PID was reused")
        birth, parent = _birth(peer.pid)
        _require(peer.pid != self.process.pid, "Bubblewrap supervisor is not a controller peer")
        seen, current = {peer.pid}, parent
        while current != self.process.pid:
            _require(current > 1 and current not in seen and len(seen) < 64, "kernel peer is outside the launched sandbox")
            seen.add(current)
            _, current = _birth(current)
        _require(self.namespace_status["child-pid"] in seen, "kernel peer is outside captured namespace child")
        _require(peer.pid not in self.peer_births or self.peer_births[peer.pid] == birth, "controller PID was reused")
        namespaces = {n: _read_proc(peer.pid, "ns/" + n, link=True) for n in self.host_namespaces}
        _require(all(namespaces[n] != self.host_namespaces[n] for n in namespaces), "controller shares a host namespace")
        _require(self.captured_peer_user_namespace is None or namespaces["user"] == self.captured_peer_user_namespace,
                 "controller escaped observed user namespace")
        for name, key in (("pid", "pid-namespace"), ("mnt", "mnt-namespace"), ("net", "net-namespace")):
            _require(namespaces[name] == f"{name}:[{self.namespace_status[key]}]", "controller escaped captured namespace")
        status = dict(line.split(":", 1) for line in _read_proc(peer.pid, "status").decode().splitlines() if ":" in line)
        _require(all(int(value, 16) == 0 for key, value in status.items() if key.startswith("Cap"))
                 and status.get("NoNewPrivs", "").strip() == "1", "controller retains privilege")
        _require(all(int(v) == peer.uid for v in status["Uid"].split()) and all(int(v) == peer.gid for v in status["Gid"].split()), "kernel UID/GID evidence differs")
        _require(len(status["NSpid"].split()) >= 2, "host PID view was mounted into controller")
        environment = {}
        for item in _read_proc(peer.pid, "environ").split(b"\0"):
            if item:
                name, value = item.decode().split("=", 1)
                _require(name not in environment, "duplicate controller environment field")
                environment[name] = value
        _require(environment == _ENV_OBSERVED, "controller environment differs from cleared allowlist")
        raw_mounts = _read_proc(peer.pid, "mountinfo")
        mounts = _mounts(raw_mounts)
        devices = {"/dev/null", "/dev/zero", "/dev/full", "/dev/random", "/dev/urandom", "/dev/tty", "/dev/pts"}
        expected = {"/", "/usr", "/lib", "/lib64", "/proc", "/dev", "/tmp", "/artifact", "/state", "/broker.sock"} | devices
        _require(set(mounts) == expected, "controller contains an unapproved host mount")
        _require(all("ro" in mounts[p]["options"] for p in ("/usr", "/lib", "/lib64", "/artifact", "/broker.sock")), "reviewed code or socket mount is writable")
        _require(mounts["/proc"]["fs"] == "proc" and mounts["/proc"]["root"] == "/"
                 and {"nosuid", "nodev", "noexec"} <= set(mounts["/proc"]["options"]), "controller lacks its own bounded procfs")
        for target, source in (("artifact", self.spec.artifact_root), ("state", self.spec.state_root), ("broker.sock", self.spec.broker_socket)):
            try:
                observed, original = (Path("/proc") / str(peer.pid) / "root" / target).stat(), source.stat()
            except OSError as exc:
                raise SandboxError("fresh host mount binding evidence unavailable") from exc
            _require((observed.st_dev, observed.st_ino) == (original.st_dev, original.st_ino), "sandbox mount bound a different source")
        routes = _read_proc(peer.pid, "net/route")
        _require(len(routes.decode().splitlines()) == 1, "controller has an IP route")
        devices_raw = _read_proc(peer.pid, "net/dev")
        interfaces = {line.split(":", 1)[0].strip() for line in devices_raw.decode().splitlines() if ":" in line}
        _require(interfaces == {"lo"}, "controller has a host network interface")
        _require(_verify_artifact(self.spec) == self.artifact_sha256, "approved artifact changed since launch")
        _verify_state_tree(self.spec.state_root)
        if not self.probe_only:
            _verify_evaluator(self.spec)
        _require(_birth(peer.pid)[0] == birth, "controller PID changed during observation")
        self.peer_births[peer.pid] = birth
        self.captured_peer_user_namespace = namespaces["user"]
        return NamespaceObservation(self.spec.scope, peer, birth, namespaces, _sha(raw_mounts),
                                    _sha(routes + b"\0" + devices_raw), time.time(), self.probe_only)

    def verify_peer(self, peer, context):
        _require(not self.probe_only, "disposable probes cannot authorize paid research")
        observation = self.observe_peer(peer)
        value = _host_context(context, self.spec, observation.observed_at)
        return IsolationProof(self.spec.scope, peer, self.spec.broker_uid, value["broker_root"], value["policy_digest"],
                              "namespaces", observation.observed_at, min(value["valid_until"], observation.observed_at + 5),
                              value["runbook"]["sha256"], observation.mounts_sha256, observation.network_sha256,
                              value["adapters_sha256"], tuple(sorted(_PHYSICAL | _EXTERNAL)),
                              "fresh host kernel launch/peer/proc evidence; " + value["provenance"])


def peer_identity(connection):
    """Extract the Linux kernel identity; a request body never provides it."""
    _require(isinstance(connection, socket.socket) and hasattr(socket, "SO_PEERCRED"), "Linux Unix peer authentication required")
    return PeerIdentity(*struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)))


def _launch(spec, argv, *, probe_only):
    _require(isinstance(spec, SandboxSpec), "reviewed sandbox specification required")
    artifact_sha = _verify_artifact(spec)
    state = _plain(spec.state_root, private=True)
    broker = _plain(spec.broker_socket)
    _plain(broker.parent, private=True)
    _verify_state_tree(state)
    _disjoint(spec.artifact_root, state, broker.parent)
    info = broker.stat()
    _require(stat.S_ISSOCK(info.st_mode) and info.st_uid == spec.broker_uid and stat.S_IMODE(info.st_mode) == 0o600,
             "only the approved private broker socket may be mounted")
    for name in ("/usr", "/lib", "/lib64"):
        _require(Path(name).is_dir(), "reviewed system runtime missing")
    read_fd, write_fd = os.pipe()
    command = ["/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--new-session", "--die-with-parent", "--cap-drop", "ALL"]
    for source, destination, flag in (("/usr", "/usr", "--ro-bind"), ("/lib", "/lib", "--ro-bind"), ("/lib64", "/lib64", "--ro-bind"),
                                     (str(spec.artifact_root), "/artifact", "--ro-bind"), (str(state), "/state", "--bind"),
                                     (str(broker), "/broker.sock", "--ro-bind")):
        command.extend((flag, source, destination))
    command.extend(("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--chdir", "/state", "--clearenv"))
    for name, value in _ENV.items():
        command.extend(("--setenv", name, value))
    command.extend(("--json-status-fd", str(write_fd), "--", *argv))
    process = None
    try:
        process = subprocess.Popen(command, env={}, cwd="/", pass_fds=(write_fd,), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        os.close(write_fd)
        write_fd = None
        _require(select.select([read_fd], [], [], 5)[0], "Bubblewrap launch evidence timed out")
        body = b""
        while b"\n" not in body and len(body) < 8192:
            piece = os.read(read_fd, 8192 - len(body))
            _require(piece, "Bubblewrap did not establish namespace isolation")
            body += piece
        status = _json(body.split(b"\n", 1)[0])
        _require(type(status.get("child-pid")) is int and all(type(status.get(k)) is int for k in ("pid-namespace", "mnt-namespace", "net-namespace")),
                 "Bubblewrap namespace launch receipt incomplete")
        sandbox = SandboxProcess(spec, process, status, probe_only=probe_only, artifact_sha256=artifact_sha, status_fd=read_fd)
        read_fd = None  # Bubblewrap writes terminal status too; keep the trusted pipe alive until process cleanup.
        return sandbox
    except BaseException:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait(5)
            for pipe in (process.stdout, process.stderr):
                if pipe:
                    pipe.close()
        raise
    finally:
        if read_fd is not None:
            os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def launch_sandbox(spec):
    """Explicit production entry; caller must first prove CI/rollback/billing/time gates."""
    _verify_evaluator(spec)
    return _launch(spec, spec.controller_argv(), probe_only=False)


def _verify_evaluator(spec):
    from .research_state import ArtifactIdentity, artifact_identity
    _require(isinstance(spec, SandboxSpec) and isinstance(spec.expected_evaluator, ArtifactIdentity)
             and spec.expected_evaluator.image == spec.image, "production launch requires actual reviewed evaluator identity")
    _require(artifact_identity(spec.image, spec.artifact_root) == spec.expected_evaluator,
             "sandbox artifact differs from actual bundle/execution identity")


def launch_disposable_probe(spec, script_relative):
    """Only reviewed probe bytes; observations from this entry never qualify a paid runtime."""
    script = _relative(script_relative)
    _require(script in dict(spec.artifact_files) and script.endswith(".py"), "probe must be in exact approved artifact")
    return _launch(spec, ("/usr/bin/python3", "/artifact/" + script), probe_only=True)
