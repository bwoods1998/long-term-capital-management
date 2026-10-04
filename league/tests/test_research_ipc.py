import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest

from league.swarm.research_ipc import (BrokerClient, BrokerServer, ResearchIPCError,
                                     REQUEST_LIMIT, _encode, _read, create_listener)


class Broker:
    def __init__(self):
        self.calls = []
        self.peers = []

    def authorize_peer(self, pid, uid, gid):
        self.peers.append((pid, uid, gid))

    def handle(self, operation, payload):
        self.calls.append((operation, payload))
        if payload.get("fail"):
            raise RuntimeError("PRIVATE_PROVIDER_SECRET_must_not_cross")
        return {"operation": operation, "payload": payload}


class ResearchIPCTest(unittest.TestCase):
    def setUp(self):
        self.broker = Broker()
        self.server = BrokerServer(self.broker, controller_uid=os.getuid())

    def request(self, **changes):
        return {"version": 1, "request_id": "a" * 32, "operation": "summary", "payload": {}, **changes}

    def exchange(self, body, *, uid=None):
        client, host = socket.socketpair()
        errors = []
        server = self.server if uid is None else BrokerServer(self.broker, controller_uid=uid)
        def serve():
            with host:
                try:
                    server.serve_connection(host)
                except Exception as exc:
                    errors.append(exc)
        worker = threading.Thread(target=serve)
        worker.start()
        with client:
            try:
                client.sendall(body)
                client.shutdown(socket.SHUT_WR)
                response = _read(client, 32 * 1024 * 1024)
            except (ResearchIPCError, OSError):
                response = None
        worker.join(2)
        self.assertFalse(worker.is_alive())
        return response, errors

    def test_authenticated_request_dispatches_once(self):
        result, errors = self.exchange(_encode(self.request(), REQUEST_LIMIT))
        self.assertEqual(errors, [])
        self.assertTrue(result["ok"])
        self.assertEqual(self.broker.calls, [("summary", {})])
        self.assertEqual(self.broker.peers, [(os.getpid(), os.getuid(), os.getgid())])

    def test_wrong_peer_never_reads_or_dispatches(self):
        result, errors = self.exchange(_encode(self.request(), REQUEST_LIMIT), uid=os.getuid() + 1)
        self.assertIsNone(result)
        self.assertIsInstance(errors[0], ResearchIPCError)
        self.assertEqual(self.broker.calls, [])

    def test_unknown_routes_extra_credentials_and_wrong_version_never_dispatch(self):
        for changes in ({"operation": "exec"}, {"operation": "/orders"}, {"token": "secret"},
                        {"version": True}, {"request_id": "../../production"}, {"payload": []}):
            result, errors = self.exchange(_encode(self.request(**changes), REQUEST_LIMIT))
            self.assertIsNone(result, changes)
            self.assertTrue(errors, changes)
        self.assertEqual(self.broker.calls, [])

    def test_duplicate_nonfinite_and_oversized_fields_never_dispatch(self):
        for raw in (b'{"version":1,"version":1}', b'{"payload":NaN}', b"{"):
            self.exchange(struct.pack("!I", len(raw)) + raw)
        self.exchange(struct.pack("!I", REQUEST_LIMIT + 1))
        self.exchange(struct.pack("!I", 100) + b"truncated")
        self.assertEqual(self.broker.calls, [])

    def test_provider_exception_is_generic_and_no_second_dispatch(self):
        response, errors = self.exchange(_encode(self.request(payload={"fail": True}), REQUEST_LIMIT))
        self.assertEqual(errors, [])
        self.assertFalse(response["ok"])
        self.assertNotIn("PRIVATE_PROVIDER_SECRET", json.dumps(response))
        self.assertEqual(len(self.broker.calls), 1)

    def test_private_listener_and_real_client_peer_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.chmod(root, 0o700)
            path = root / "broker.sock"
            listener = create_listener(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            worker = threading.Thread(target=self.server.serve_once, args=(listener,))
            worker.start()
            response = BrokerClient(path, broker_uid=os.getuid(), timeout=2).summary()
            worker.join(2)
            listener.close()
            self.assertFalse(worker.is_alive())
            self.assertEqual(response["operation"], "summary")
            with self.assertRaises(ResearchIPCError):
                create_listener(path)

    def test_existing_symlink_or_public_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "broker.sock"
            os.chmod(root, 0o755)
            with self.assertRaises(ResearchIPCError):
                create_listener(path)
            os.chmod(root, 0o700)
            path.symlink_to(root / "missing")
            with self.assertRaises(ResearchIPCError):
                create_listener(path)

    def test_client_refuses_wrong_host_without_sending_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.chmod(root, 0o700)
            listener = create_listener(root / "broker.sock")
            seen = []
            def receive():
                peer, _ = listener.accept()
                with peer:
                    seen.append(peer.recv(1))
            worker = threading.Thread(target=receive)
            worker.start()
            with self.assertRaises(ResearchIPCError):
                BrokerClient(root / "broker.sock", broker_uid=os.getuid() + 1, timeout=2).summary()
            worker.join(2)
            listener.close()
            self.assertEqual(seen, [b""])
            self.assertEqual(self.broker.calls, [])

    def test_client_rejects_unbounded_json_before_connecting(self):
        client = BrokerClient("/missing/broker.sock", broker_uid=os.getuid(), timeout=1)
        with self.assertRaises(ResearchIPCError):
            client.request("evaluate", {"data": "x" * REQUEST_LIMIT})
        with self.assertRaises(ResearchIPCError):
            client.request("evaluate", {"cost": float("nan")})
