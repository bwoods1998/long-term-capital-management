"""Actual disposable Bubblewrap probes and synthetic host-verifier refusals; no paid runtime."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
from dataclasses import replace
from unittest import mock

from league.swarm import research_sandbox as sandbox
from league.swarm.research_ipc import create_listener
from league.swarm.research_transport import PeerIdentity


PROBE = """import json,os,socket,subprocess
blocked={}
for name,path in [('artifact','/artifact/config.json'),('home','/home'),('host_proc','/proc/1/root/home')]:
    try:
        if name=='artifact':
            with open(path,'w') as handle:handle.write('escaped')
            blocked[name]=False
        else:blocked[name]=not os.path.exists(path)
    except OSError:blocked[name]=True
try:
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.settimeout(0.1);s.connect(('192.0.2.1',443));blocked['network']=False
except OSError:blocked['network']=True
finally:s.close()
blocked['nested_userns']=subprocess.run(['/usr/bin/unshare','-Ur','/usr/bin/true'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
    connection.connect('/broker.sock')
    connection.sendall(json.dumps(blocked).encode()+b'\\n')
    connection.recv(1)
"""


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.artifact = self.base / "artifact"
        self.state = self.base / "private-state"
        self.broker = self.base / "private-broker"
        for path in (self.artifact, self.state, self.broker):
            path.mkdir(mode=0o700)
        for name, text in (("config.json", "{}"), ("policy.json", "{}"), ("probe.py", PROBE)):
            (self.artifact / name).write_text(text)
        self.listener = create_listener(self.broker / "broker.sock")
        self.listener.settimeout(5)
        self.addCleanup(self.listener.close)
        files = tuple((p.name, hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(self.artifact.iterdir()))
        self.spec = sandbox.SandboxSpec("synthetic-sandbox", self.artifact, files, self.state,
                                       self.broker / "broker.sock", os.getuid(), "sbcp_" + "a" * 32,
                                       ("SPY",), "config.json", "policy.json")

    def running(self):
        if not Path("/usr/bin/bwrap").is_file() or not Path("/usr/bin/unshare").is_file():
            self.skipTest("Linux Bubblewrap/unshare probe prerequisite unavailable")
        process = sandbox.launch_disposable_probe(self.spec, "probe.py")
        self.addCleanup(process.close)
        connection, _ = self.listener.accept()
        self.addCleanup(connection.close)
        connection.settimeout(5)
        body = b""
        while not body.endswith(b"\n"):
            body += connection.recv(4096)
        return process, connection, json.loads(body)

    def test_actual_disposable_probe_enforces_mount_network_environment_and_privilege_walls(self):
        process, connection, blocked = self.running()
        self.assertEqual(blocked, {"artifact": True, "home": True, "host_proc": True, "network": True, "nested_userns": True})
        peer = sandbox.peer_identity(connection)
        observed = process.observe_peer(peer)
        self.assertEqual(observed.scope, self.spec.scope)
        self.assertTrue(observed.probe_only)
        self.assertGreater(observed.peer_starttime, 0)
        self.assertEqual(len(observed.mounts_sha256), 64)
        self.assertEqual(len(observed.network_sha256), 64)
        self.assertTrue(all(observed.namespaces[name] != process.host_namespaces[name] for name in observed.namespaces))
        self.assertEqual((self.artifact / "config.json").read_text(), "{}")
        with self.assertRaisesRegex(sandbox.SandboxError, "probes cannot authorize"):
            process.verify_peer(peer, None)
        connection.sendall(b"x")
        self.assertEqual(process.process.wait(5), 0)

    def test_unrelated_kernel_peer_or_claimed_uid_cannot_borrow_the_namespace(self):
        process, connection, _ = self.running()
        with self.assertRaisesRegex(sandbox.SandboxError, "outside|supervisor"):
            process.observe_peer(PeerIdentity(os.getpid(), os.getuid(), os.getgid()))
        peer = sandbox.peer_identity(connection)
        with self.assertRaisesRegex(sandbox.SandboxError, "UID/GID"):
            process.observe_peer(replace(peer, uid=peer.uid + 1))

    def test_pid_birth_change_dead_peer_or_denied_proc_never_produces_proof(self):
        process, connection, _ = self.running()
        peer = sandbox.peer_identity(connection)
        observation = process.observe_peer(peer)
        process.peer_births[peer.pid] = observation.peer_starttime + 1
        with self.assertRaisesRegex(sandbox.SandboxError, "PID was reused"):
            process.observe_peer(peer)
        process.peer_births.clear()
        original = Path.read_bytes
        def denied(path):
            if str(path).startswith("/proc/"):
                raise PermissionError("synthetic ptrace denial")
            return original(path)
        with mock.patch.object(Path, "read_bytes", denied):
            with self.assertRaisesRegex(sandbox.SandboxError, "fresh host /proc evidence unavailable"):
                process.observe_peer(peer)
        connection.sendall(b"x")
        process.process.wait(5)
        with self.assertRaises(sandbox.SandboxError):
            process.observe_peer(peer)

    def test_fresh_mount_inspection_and_changed_artifact_close_the_scope(self):
        process, connection, _ = self.running()
        peer = sandbox.peer_identity(connection)
        original = sandbox._mounts
        def extra_mount(raw):
            mounts = original(raw)
            mounts["/home"] = {"options": ["ro"], "root": "/home", "fs": "btrfs"}
            return mounts
        with mock.patch.object(sandbox, "_mounts", extra_mount):
            with self.assertRaisesRegex(sandbox.SandboxError, "unapproved host mount"):
                process.observe_peer(peer)
        (self.artifact / "policy.json").write_text('{"changed": true}')
        with self.assertRaisesRegex(sandbox.SandboxError, "exact reviewed manifest"):
            process.observe_peer(peer)

    def test_manifest_refuses_extra_secret_symlink_and_parent_mounts_before_launch(self):
        for name, content in ((".env", "SYNTHETIC_PRIVATE_CREDENTIAL"), ("unreviewed.txt", "extra")):
            path = self.artifact / name
            path.write_text(content)
            with self.assertRaises(sandbox.SandboxError):
                sandbox.launch_disposable_probe(self.spec, "probe.py")
            path.unlink()
        secret = self.base / "outside-secret"
        secret.write_text("SYNTHETIC_OUTSIDE_VALUE")
        link = self.artifact / "symlink"
        link.symlink_to(secret)
        with self.assertRaises(sandbox.SandboxError):
            sandbox.launch_disposable_probe(self.spec, "probe.py")
        link.unlink()
        with self.assertRaises(sandbox.SandboxError):
            sandbox.launch_disposable_probe(replace(self.spec, state_root=self.artifact), "probe.py")
        self.state.chmod(0o755)
        with self.assertRaises(sandbox.SandboxError):
            sandbox.launch_disposable_probe(self.spec, "probe.py")

    def test_fixed_production_entry_has_only_controller_and_approved_paths(self):
        argv = self.spec.controller_argv()
        self.assertEqual(argv[:3], ("/usr/bin/python3", "-m", "league.swarm.research_controller"))
        self.assertEqual(argv[argv.index("--state") + 1], "/state")
        self.assertEqual(argv[argv.index("--broker-socket") + 1], "/broker.sock")
        self.assertNotIn(str(self.broker), argv)
        self.assertNotIn(str(self.artifact), argv)
        self.assertNotIn("--env", argv)
        with self.assertRaisesRegex(sandbox.SandboxError, "actual reviewed evaluator identity"):
            sandbox.launch_sandbox(self.spec)
        for changes in ({"scope": "wrong scope"}, {"image": "sb_live-resource"}, {"config_relative": "../production.json"},
                        {"roots": ("SPY", "SPY")}, {"artifact_files": ()}):
            with self.assertRaises(sandbox.SandboxError):
                replace(self.spec, **changes)

    def test_state_cannot_expose_another_socket_or_symlink_capability(self):
        other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(other.close)
        other.bind(str(self.state / "unapproved.sock"))
        with self.assertRaisesRegex(sandbox.SandboxError, "unapproved socket"):
            sandbox.launch_disposable_probe(self.spec, "probe.py")
        (self.state / "unapproved.sock").unlink()
        (self.state / "host-home").symlink_to(Path.home())
        with self.assertRaisesRegex(sandbox.SandboxError, "symlink"):
            sandbox.launch_disposable_probe(self.spec, "probe.py")

    def context(self):
        host = self.base / "host-evidence"
        host.mkdir(mode=0o700)
        runbook, adapter = host / "reviewed-runbook.txt", host / "reviewed-adapter.py"
        runbook.write_text("synthetic reviewed rollback/runbook")
        adapter.write_text("# synthetic reviewed host adapter")
        now = time.time()
        receipt = {"schema": 1, "scope": self.spec.scope, "broker_uid": self.spec.broker_uid, "broker_root": str(self.broker),
                   "policy_digest": "a" * 64, "observed_at": now - 1, "valid_until": now + 30,
                   "facts": sorted(sandbox._EXTERNAL), "runbook": {"path": str(runbook), "sha256": hashlib.sha256(runbook.read_bytes()).hexdigest()},
                   "adapters": [{"path": str(adapter), "sha256": hashlib.sha256(adapter.read_bytes()).hexdigest()}],
                   "provenance": "synthetic explicit host review; no real account or Gym evidence"}
        path = host / "context.json"
        path.write_text(json.dumps(receipt))
        path.chmod(0o600)
        return sandbox.HostContextEvidence(path, hashlib.sha256(path.read_bytes()).hexdigest()), receipt

    def test_external_account_and_gym_facts_need_exact_fresh_host_review_and_actual_files(self):
        evidence, receipt = self.context()
        observed = sandbox._host_context(evidence, self.spec, time.time())
        self.assertEqual(observed["policy_digest"], "a" * 64)
        with self.assertRaises(sandbox.SandboxError):
            sandbox._host_context(replace(evidence, approved_sha256="0" * 64), self.spec, time.time())
        with self.assertRaises(sandbox.SandboxError):
            sandbox._host_context(evidence, self.spec, receipt["valid_until"] + 1)
        Path(receipt["adapters"][0]["path"]).write_text("# changed")
        with self.assertRaisesRegex(sandbox.SandboxError, "adapter changed"):
            sandbox._host_context(evidence, self.spec, time.time())


if __name__ == "__main__":
    unittest.main()
