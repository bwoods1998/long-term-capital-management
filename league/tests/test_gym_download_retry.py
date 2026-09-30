"""Real Transport -> SailboxClient -> GymDriver, with a fake HTTP opener and no sockets.

A result-download failure must not rerun a completed batch. Classifying a sanitized transport
error must not accidentally retry an exec/upload, an unknown cause, or a TLS/auth failure.
"""

import errno
import io
import json
import socket
import ssl
import traceback
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from league.gym.driver import GymDriver, GymError
from league.sailbox import SailboxClient, SailboxError, SailboxTransportError, Transport

BOX = "sb_0123456789abcdef"
SECRET = "synthetic-credential-must-not-appear"
PROGRAMS = {"synthetic": "NEEDS = {}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"}


class FakeOpener:
    """A completed synthetic batch; injected errors happen at the actual HTTP boundary."""

    def __init__(self, *, failures=(), fail_operation="download", fail_command=None, existing=False):
        self.failures = list(failures)
        self.fail_operation = fail_operation
        self.fail_command = fail_command
        self.existing = existing
        self.calls = []

    def open(self, request, timeout):
        method, path = request.get_method(), urlsplit(request.full_url).path
        if method == "GET" and path.endswith("/files"):
            operation, command = "download", None
        elif method == "PUT" and path.endswith("/files"):
            operation, command = "upload", None
        elif method == "POST" and path.endswith("/exec"):
            operation, command = "exec", json.loads(request.data)["command"]
        else:
            raise AssertionError(f"unexpected fake route: {method} {path}")
        self.calls.append((operation, command))
        if (operation == self.fail_operation and self.failures
                and (self.fail_command is None or self.fail_command in (command or ""))):
            raise self.failures.pop(0)
        if operation == "download":
            return io.BytesIO(b'{"batch":{},"results":[{"program":"synthetic","status":"ok"}]}')
        if operation == "upload":
            return io.BytesIO(b"{}")
        # The code bundle is present; only the first invocation needs to run the batch.
        code = 1 if command.startswith("test -f ") and command.endswith("results.json") and not self.existing else 0
        if "--programs " in command:
            self.existing = True
        events = [{"type": "started", "exec_request_id": "synthetic-exec"},
                  {"type": "exit", "return_code": code, "status": "succeeded" if code == 0 else "failed"}]
        return io.BytesIO(b"\n".join(json.dumps(event).encode() for event in events))

    def count(self, operation):
        return sum(kind == operation for kind, _ in self.calls)

    def batches(self):
        return sum(kind == "exec" and "--programs " in command for kind, command in self.calls)


class ResultDownloadRetry(unittest.TestCase):
    def setUp(self):
        self.no_network = patch("socket.socket", side_effect=AssertionError("tests must not open sockets"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def driver(self, opener, **kwargs):
        client = SailboxClient(Transport(key_source=lambda: SECRET, opener=opener))
        self.delays = []
        return GymDriver(client, BOX, backoff=0.25, sleep=self.delays.append, **kwargs)

    def http_error(self, status):
        error = HTTPError("https://synthetic.invalid/" + SECRET, status, SECRET, {},
                          io.BytesIO(b'{"error":{"message":"synthetic response"}}'))
        self.addCleanup(error.close)
        return error

    @staticmethod
    def run_batch(driver):
        return driver.run(PROGRAMS, window="train", roots=["SPY"])

    def test_known_transient_transport_failures_retry_only_the_completed_result(self):
        errors = [TimeoutError(SECRET), URLError(TimeoutError(SECRET)),
                  URLError(ConnectionResetError(SECRET)), URLError(socket.gaierror(socket.EAI_AGAIN, SECRET)),
                  OSError(errno.ENETUNREACH, SECRET)]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                opener = FakeOpener(failures=[error])
                driver = self.driver(opener)
                doc = self.run_batch(driver)
                self.assertEqual(doc["results"][0]["status"], "ok")
                self.assertEqual(opener.count("download"), 2)
                self.assertEqual(opener.count("upload"), 1)
                self.assertEqual(opener.batches(), 1)
                self.assertEqual(self.delays, [0.25])
                self.assertEqual(driver.calls, ["exec", "exec", "upload", "exec", "download", "download", "exec"])

    def test_exhaustion_obeys_attempt_limit_backoff_and_preserves_result_for_recovery(self):
        opener = FakeOpener(failures=[TimeoutError(SECRET) for _ in range(3)])
        driver = self.driver(opener)
        with self.assertRaises(GymError) as caught:
            self.run_batch(driver)
        self.assertEqual(opener.count("download"), 3)
        self.assertEqual(opener.count("upload"), 1)
        self.assertEqual(opener.batches(), 1)
        self.assertEqual(self.delays, [0.25, 0.5])
        self.assertFalse(any(command.startswith("rm -rf ") for kind, command in opener.calls if kind == "exec"))
        cause = caught.exception.__cause__
        self.assertIsInstance(cause, SailboxTransportError)
        self.assertTrue(cause.transient)
        self.assertIsNone(cause.status)
        self.assertEqual(cause.kind, "transport")
        self.assertIsNone(cause.__cause__)
        self.assertTrue(cause.__suppress_context__)
        self.assertNotIn(SECRET, "".join(traceback.format_exception(caught.exception)))
        self.assertNotIn(SECRET, repr(vars(cause)))
        # A later call can recover the already written file, without a second upload or exec.
        self.run_batch(driver)
        self.assertEqual(opener.count("download"), 4)
        self.assertEqual(opener.count("upload"), 1)
        self.assertEqual(opener.batches(), 1)

    def test_single_attempt_configuration_never_sleeps(self):
        opener = FakeOpener(failures=[TimeoutError(SECRET)])
        with self.assertRaises(GymError):
            self.run_batch(self.driver(opener, retries=1))
        self.assertEqual(opener.count("download"), 1)
        self.assertEqual(self.delays, [])

    def test_tls_auth_permanent_and_unknown_failures_stop_without_retry(self):
        errors = [ssl.SSLCertVerificationError(1, SECRET), URLError(ssl.SSLError(1, SECRET)),
                  URLError(socket.gaierror(socket.EAI_NONAME, SECRET)), PermissionError(errno.EACCES, SECRET),
                  OSError(SECRET), URLError(SECRET), RuntimeError("synthetic unknown failure"),
                  SailboxError("synthetic unknown Sailbox failure"),
                  *[self.http_error(status) for status in (400, 401, 403, 404)]]
        for error in errors:
            with self.subTest(error=type(error).__name__, status=getattr(error, "code", None)):
                opener = FakeOpener(failures=[error])
                with self.assertRaises(GymError) as caught:
                    self.run_batch(self.driver(opener))
                self.assertEqual(opener.count("download"), 1)
                self.assertEqual(self.delays, [])
                self.assertNotIn(SECRET, "".join(traceback.format_exception(caught.exception)))
                if isinstance(caught.exception.__cause__, SailboxTransportError):
                    self.assertFalse(caught.exception.__cause__.transient)

    def test_transient_http_status_retries_are_unchanged(self):
        opener = FakeOpener(failures=[self.http_error(503), self.http_error(429)])
        self.run_batch(self.driver(opener))
        self.assertEqual(opener.count("download"), 3)
        self.assertEqual(self.delays, [0.25, 0.5])
        self.assertEqual(opener.batches(), 1)

    def test_sanitized_transport_errors_do_not_newly_retry_exec_or_upload(self):
        for operation in ("exec", "upload"):
            for error in (TimeoutError(SECRET), URLError(ConnectionResetError(SECRET))):
                with self.subTest(operation=operation, error=type(error).__name__):
                    opener = FakeOpener(failures=[error], fail_operation=operation,
                                        fail_command="--programs " if operation == "exec" else None)
                    with self.assertRaises(GymError) as caught:
                        self.run_batch(self.driver(opener))
                    self.assertEqual(opener.count("upload"), 1)
                    self.assertEqual(opener.count("exec"), 3 if operation == "exec" else 2)
                    self.assertEqual(opener.count("download"), 0)
                    self.assertEqual(opener.batches(), 1 if operation == "exec" else 0)
                    self.assertEqual(self.delays, [])
                    self.assertIsInstance(caught.exception.__cause__, SailboxTransportError)
                    self.assertTrue(caught.exception.__cause__.transient)

    def test_transport_itself_never_retries(self):
        opener = FakeOpener(failures=[TimeoutError(SECRET)])
        client = SailboxClient(Transport(key_source=lambda: SECRET, opener=opener))
        with self.assertRaises(SailboxTransportError):
            client.download(BOX, "/workspace/results.json")
        self.assertEqual(opener.count("download"), 1)

    def test_a_download_outside_run_does_not_implicitly_opt_in(self):
        opener = FakeOpener(failures=[TimeoutError(SECRET)])
        driver = self.driver(opener)
        with self.assertRaises(GymError):
            driver._retry("download", driver.client.download, BOX, "/workspace/results.json")
        self.assertEqual(opener.count("download"), 1)
        self.assertEqual(self.delays, [])


if __name__ == "__main__":
    unittest.main()
