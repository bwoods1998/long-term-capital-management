"""The Sailbox client, against a fake transport. Nothing here opens a socket.

Every test drives `SailboxClient` through a transport that records the request it was handed and
replays a scripted answer, so what is under test is the request *shape* -- the thing that is
expensive to get wrong against a live API that creates billable machines.
"""

from __future__ import annotations

import base64
import unittest

from ltcm import sailbox
from ltcm.sailbox import (
    FLOOR_HOSTS,
    SailboxClient,
    SailboxError,
    Transport,
    check_egress,
    floor_policy,
    hourly_cost,
    normalize_hosts,
    policy_allowlist,
    remote_path,
    usd,
)

APP = "app_0f6a2c31-8b4d-4e7a-9c15-2d8e6f4a1b03"
BOX = "sb_9c8f1e2a-3b4d-4f5a-8c7e-1d2f3a4b5c6d"
CHECKPOINT = "sbcp_1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"


def event_stream(*events):
    """One scripted NDJSON exec stream, as the transport hands it back."""
    return iter(list(events))


def out(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class FakeTransport:
    """Records every request and replays a scripted answer per (method, path)."""

    def __init__(self, responses=None):
        self.calls: list[dict] = []
        self.responses = dict(responses or {})

    def __call__(self, method, path, body=None, *, data=None, query=None,
                 idempotency_key=None, stream=False, raw=False, timeout=60.0):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "data": data,
                # The real transport drops empty parameters before it builds the URL.
                "query": {k: v for k, v in dict(query or {}).items() if v is not None},
                "idempotency_key": idempotency_key,
                "stream": stream,
                "raw": raw,
                "timeout": timeout,
            }
        )
        answer = self.responses.get((method, path))
        if isinstance(answer, list):
            answer = answer.pop(0) if answer else {}
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            answer = answer(body, query)
        return {} if answer is None else answer

    def last(self, method=None, path=None) -> dict:
        for call in reversed(self.calls):
            if (method is None or call["method"] == method) and (path is None or call["path"] == path):
                return call
        raise AssertionError(f"no call for {method} {path}")


class AllowlistTests(unittest.TestCase):
    def test_normalize_lowercases_dedupes_and_sorts(self):
        self.assertEqual(
            normalize_hosts(["B.example.com", "a.example.com.", "b.example.com"]),
            ["a.example.com", "b.example.com"],
        )

    def test_wildcard_entry_is_accepted(self):
        self.assertEqual(normalize_hosts(["*.workers.dev"]), ["*.workers.dev"])

    def test_bad_entries_are_refused(self):
        for entry in ("", "api.example.com:443", "http://api.example.com", "a/b", "*", 7):
            with self.subTest(entry=entry), self.assertRaises(SailboxError):
                normalize_hosts([entry])

    def test_empty_and_oversized_lists_are_refused(self):
        with self.assertRaises(SailboxError):
            normalize_hosts([])
        with self.assertRaises(SailboxError):
            normalize_hosts([f"h{n}.example.com" for n in range(129)])

    def test_the_floor_can_reach_the_sailbox_control_plane_for_its_sandboxes(self):
        # run_code forks and drives a desk's sandbox through sailbox-api; a floor that cannot
        # resolve it fails every run in forty milliseconds, as the first live session showed.
        self.assertIn("sailbox-api.sailresearch.com", FLOOR_HOSTS)
        self.assertIn("sailbox-api.sailresearch.com", floor_policy()["allowlist"])

    def test_floor_policy_carries_every_required_host_and_the_gateway(self):
        policy = floor_policy()
        for host in FLOOR_HOSTS:
            self.assertIn(host, policy["allowlist"])
        self.assertIn("*.workers.dev", policy["allowlist"])
        self.assertEqual(len(policy["allowlist"]), len(FLOOR_HOSTS) + 1)

    def test_floor_policy_is_an_allowlist_and_nothing_else(self):
        # No `rules`: the floor signs its own venue requests, so Sail is never given a credential
        # to inject. No `no_network`, or the box could not reach the provider at all.
        self.assertEqual(set(floor_policy()), {"allowlist"})

    def test_floor_policy_takes_an_exact_gateway_when_wildcards_are_not_wanted(self):
        policy = floor_policy(gateway_host="ltcm-gateway.blake.workers.dev")
        self.assertIn("ltcm-gateway.blake.workers.dev", policy["allowlist"])
        self.assertNotIn("*.workers.dev", policy["allowlist"])

    def test_gateway_can_be_left_out_entirely(self):
        self.assertEqual(sorted(FLOOR_HOSTS), floor_policy(gateway_host=None)["allowlist"])


class PolicyReadbackTests(unittest.TestCase):
    def test_current_shape_matches(self):
        policy = floor_policy()
        row = {"egress_policy": {"policy_id": None, "name": None, "document": policy}}
        report = check_egress(row, policy)
        self.assertTrue(report["ok"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["extra"], [])

    def test_older_network_policy_shape_matches_too(self):
        policy = floor_policy()
        row = {"network_policy": {"mode": "allowlist", "allowed_hosts": policy["allowlist"]}}
        self.assertTrue(check_egress(row, policy)["ok"])

    def test_a_missing_host_is_reported(self):
        policy = floor_policy()
        short = [h for h in policy["allowlist"] if h != "api.coinbase.com"]
        row = {"egress_policy": {"document": {"allowlist": short}}}
        report = check_egress(row, policy)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], ["api.coinbase.com"])

    def test_an_extra_host_is_reported(self):
        policy = floor_policy()
        row = {"egress_policy": {"document": {"allowlist": policy["allowlist"] + ["evil.test"]}}}
        report = check_egress(row, policy)
        self.assertFalse(report["ok"])
        self.assertEqual(report["extra"], ["evil.test"])

    def test_no_network_never_counts_as_matching(self):
        policy = floor_policy()
        row = {"egress_policy": {"document": {"no_network": True, "allowlist": policy["allowlist"]}}}
        self.assertFalse(check_egress(row, policy)["ok"])

    def test_an_open_box_never_counts_as_matching(self):
        self.assertFalse(check_egress({"egress_policy": {"document": {}}}, floor_policy())["ok"])
        self.assertFalse(check_egress({}, floor_policy())["ok"])

    def test_allowlist_reader_normalizes_what_sail_stored(self):
        self.assertEqual(
            policy_allowlist({"document": {"allowlist": ["B.test.", "a.test"]}}),
            ["a.test", "b.test"],
        )


class TransportTests(unittest.TestCase):
    def transport(self):
        return Transport(key_source=lambda: "sk-not-a-real-key")

    def test_only_the_sail_api_is_addressable(self):
        for url in ("http://sailbox-api.sailresearch.com/v1", "https://evil.test/v1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Transport(key_source=lambda: "k", base_url=url)

    def test_the_route_allowlist_covers_what_the_client_uses(self):
        allowed = self.transport().allowed
        for method, path in (
            ("POST", "/apps/find"),
            ("POST", "/sailboxes"),
            ("GET", "/sailboxes"),
            ("GET", "/sailboxes/spend"),
            ("POST", "/sailboxes/from_checkpoint"),
            ("GET", f"/sailboxes/{BOX}"),
            ("POST", f"/sailboxes/{BOX}/exec"),
            ("POST", f"/sailboxes/{BOX}/exec/exec_123/wait"),
            ("PUT", f"/sailboxes/{BOX}/files"),
            ("GET", f"/sailboxes/{BOX}/files"),
            ("POST", f"/sailboxes/{BOX}/checkpoint"),
            ("POST", f"/sailboxes/{BOX}/sleep"),
            ("POST", f"/sailboxes/{BOX}/resume"),
            ("POST", f"/sailboxes/{BOX}/pause"),
            ("POST", f"/sailboxes/{BOX}/terminate"),
            ("POST", f"/sailboxes/{BOX}/auto_sleep"),
            ("GET", f"/sailboxes/{BOX}/egress-policy"),
            ("PUT", f"/sailboxes/{BOX}/egress-policy"),
        ):
            with self.subTest(route=f"{method} {path}"):
                self.assertTrue(allowed(method, path))

    def test_everything_else_is_refused(self):
        allowed = self.transport().allowed
        for method, path in (
            ("DELETE", f"/sailboxes/{BOX}"),
            ("POST", f"/sailboxes/{BOX}"),
            ("GET", "/secrets"),
            ("PUT", "/secrets/KALSHI"),
            ("POST", "/v1/sailboxes"),
            ("GET", "/sailboxes/../secrets"),
            ("POST", "/sailboxes/not-a-box/exec"),
            ("GET", f"/sailboxes/{BOX}/ssh"),
            ("POST", "/egress-policies"),
        ):
            with self.subTest(route=f"{method} {path}"):
                self.assertFalse(allowed(method, path))

    def test_a_route_off_the_allowlist_never_reaches_the_network(self):
        # `open` would raise if it were reached: the guard fires first.
        transport = Transport(key_source=lambda: "k", opener=object())
        with self.assertRaises(SailboxError):
            transport("DELETE", f"/sailboxes/{BOX}")

    def test_guest_paths_are_checked_before_they_are_sent(self):
        self.assertEqual(remote_path("/workspace/ltcm/config.json"), "/workspace/ltcm/config.json")
        for bad in ("workspace/x", "/workspace/../etc/shadow", "/workspace/$(whoami)", "/x;y", ""):
            with self.subTest(path=bad), self.assertRaises(SailboxError):
                remote_path(bad)

    def test_an_api_error_carries_the_status_and_not_the_request(self):
        error = sailbox._error(409, b'{"error":{"message":"already exists","type":"conflict_error"}}')
        self.assertEqual(error.status, 409)
        self.assertEqual(error.kind, "conflict_error")
        self.assertIn("already exists", str(error))
        self.assertNotIn("Bearer", str(error))


class CreateTests(unittest.TestCase):
    def client(self, responses=None):
        transport = FakeTransport(responses or {})
        return SailboxClient(transport), transport

    def test_the_create_body_is_the_shape_the_api_documents(self):
        api, transport = self.client(
            {("POST", "/sailboxes"): {"sailbox_id": BOX, "status": "running"}}
        )
        policy = floor_policy()
        api.create(app=APP, name="ltcm-floor", size="s", egress=policy,
                   auto_sleep={"automatic": False}, visibility="private")
        call = transport.last("POST", "/sailboxes")
        self.assertEqual(
            call["body"],
            {
                "app_id": APP,
                "name": "ltcm-floor",
                "size": "s",
                "image": {"base": "BASE_IMAGE_DEBIAN"},
                "visibility": "private",
                "auto_sleep": {"automatic": False},
                "egress_policy": policy,
            },
        )
        self.assertTrue(call["idempotency_key"].startswith("ltcm-create-"))

    def test_autosleep_off_is_what_keeps_the_floor_awake(self):
        api, transport = self.client(
            {("POST", "/sailboxes"): {"sailbox_id": BOX, "status": "running"}}
        )
        api.create(app=APP, name="n", egress=floor_policy(), auto_sleep={"automatic": False})
        self.assertIs(transport.last("POST", "/sailboxes")["body"]["auto_sleep"]["automatic"], False)

    def test_the_older_network_policy_contract_is_used_when_egress_policy_is_rejected(self):
        rejection = SailboxError("sailbox api 400: unknown field egress_policy", status=400)
        api, transport = self.client(
            {("POST", "/sailboxes"): [rejection, {"sailbox_id": BOX, "status": "running"}]}
        )
        api.create(app=APP, name="n", egress=floor_policy())
        body = transport.last("POST", "/sailboxes")["body"]
        self.assertNotIn("egress_policy", body)
        self.assertEqual(body["network_policy"]["mode"], "allowlist")
        self.assertEqual(sorted(body["network_policy"]["allowed_hosts"]), floor_policy()["allowlist"])
        # A fresh key, because Sail remembers 400s against the one that was already used.
        keys = [c["idempotency_key"] for c in transport.calls]
        self.assertNotEqual(keys[0], keys[1])

    def test_an_unrelated_four_hundred_is_not_retried(self):
        rejection = SailboxError("sailbox api 400: name is required", status=400)
        api, transport = self.client({("POST", "/sailboxes"): [rejection]})
        with self.assertRaises(SailboxError):
            api.create(app=APP, name="n", egress=floor_policy())
        self.assertEqual(len(transport.calls), 1)

    def test_a_create_that_answered_two_hundred_but_failed_is_still_a_failure(self):
        api, _ = self.client(
            {("POST", "/sailboxes"): {"sailbox_id": BOX, "status": "failed",
                                      "error_message": "no capacity"}}
        )
        with self.assertRaises(SailboxError) as caught:
            api.create(app=APP, name="n", egress=floor_policy())
        self.assertIn("no capacity", str(caught.exception))

    def test_a_bad_size_or_visibility_never_reaches_the_api(self):
        api, transport = self.client()
        with self.assertRaises(SailboxError):
            api.create(app=APP, name="n", size="xl")
        with self.assertRaises(SailboxError):
            api.create(app=APP, name="n", visibility="world")
        self.assertEqual(transport.calls, [])

    def test_find_app_mints_when_missing(self):
        api, transport = self.client({("POST", "/apps/find"): {"id": APP, "name": "ltcm"}})
        self.assertEqual(api.find_app("ltcm")["id"], APP)
        self.assertEqual(
            transport.last("POST", "/apps/find")["body"], {"name": "ltcm", "mint_if_missing": True}
        )

    def test_set_egress_sends_an_inline_document_and_reads_the_policy_back(self):
        # The wildcard `*.workers.dev` is accepted by the API but is not what the box's resolver
        # honours, so the exact gateway host has to be on the list. The body is the documented
        # shape: a `document` wrapper, never a bare `allowlist`, which the API refuses as unknown.
        wanted = list(FLOOR_HOSTS) + ["ltcm-gateway.example.workers.dev"]
        api, transport = self.client(
            {
                ("PUT", f"/sailboxes/{BOX}/egress-policy"): {},
                ("GET", f"/sailboxes/{BOX}/egress-policy"): {"document": {"allowlist": wanted}},
            }
        )
        readback = api.set_egress(BOX, ["LTCM-Gateway.example.workers.dev", *FLOOR_HOSTS])
        sent = transport.last("PUT", f"/sailboxes/{BOX}/egress-policy")["body"]
        self.assertEqual(set(sent), {"document"})
        self.assertEqual(sent["document"], {"allowlist": normalize_hosts(wanted)})
        self.assertEqual(policy_allowlist(readback), normalize_hosts(wanted))

    def test_verify_egress_reads_the_policy_endpoint_when_the_row_is_silent(self):
        policy = floor_policy()
        api, transport = self.client(
            {
                ("GET", f"/sailboxes/{BOX}"): {"sailbox_id": BOX},
                ("GET", f"/sailboxes/{BOX}/egress-policy"): {"document": policy},
            }
        )
        self.assertTrue(api.verify_egress(BOX, policy)["ok"])
        self.assertEqual(transport.calls[-1]["path"], f"/sailboxes/{BOX}/egress-policy")


class ExecTests(unittest.TestCase):
    def client(self, *events):
        transport = FakeTransport({("POST", f"/sailboxes/{BOX}/exec"): event_stream(*events)})
        return SailboxClient(transport), transport

    def test_output_is_decoded_streamed_and_accumulated(self):
        api, transport = self.client(
            {"type": "started", "exec_request_id": "exec_1"},
            {"type": "stdout", "data": out("hello "), "seq": 1},
            {"type": "stderr", "data": out("warned"), "seq": 1},
            {"type": "heartbeat"},
            {"type": "stdout", "data": out("world"), "seq": 2},
            {"type": "exit", "status": "succeeded", "return_code": 0},
        )
        seen: list[tuple[str, str]] = []
        result = api.exec(BOX, ["echo", "hi"], on_output=lambda k, t: seen.append((k, t)))
        self.assertEqual(result.stdout, "hello world")
        self.assertEqual(result.stderr, "warned")
        self.assertEqual(result.output, "hello warnedworld")
        self.assertEqual((result.return_code, result.status, result.exec_id), (0, "succeeded", "exec_1"))
        self.assertTrue(result.ok)
        self.assertEqual(seen, [("stdout", "hello "), ("stderr", "warned"), ("stdout", "world")])
        self.assertTrue(transport.last("POST", f"/sailboxes/{BOX}/exec")["stream"])

    def test_the_request_body_carries_the_command_and_timeout(self):
        api, transport = self.client({"type": "exit", "status": "succeeded", "return_code": 0})
        api.exec(BOX, ["python3", "-m", "ltcm", "--help"], timeout=120)
        self.assertEqual(
            transport.last("POST", f"/sailboxes/{BOX}/exec")["body"],
            {"command": ["python3", "-m", "ltcm", "--help"], "timeout": 120},
        )

    def test_a_shell_string_takes_cwd_and_background(self):
        api, transport = self.client({"type": "started", "exec_request_id": "e"})
        result = api.exec(BOX, "sh run.sh", cwd="/workspace", background=True)
        body = transport.last("POST", f"/sailboxes/{BOX}/exec")["body"]
        self.assertEqual(body["cwd"], "/workspace")
        self.assertIs(body["background"], True)
        self.assertEqual((result.status, result.return_code), ("background", 0))

    def test_cwd_and_background_are_refused_for_an_argument_array(self):
        api, _ = self.client()
        with self.assertRaises(SailboxError):
            api.exec(BOX, ["ls"], cwd="/workspace")
        with self.assertRaises(SailboxError):
            api.exec(BOX, ["ls"], background=True)

    def test_a_nonzero_exit_fails_the_check(self):
        api, _ = self.client(
            {"type": "stderr", "data": out("boom")},
            {"type": "exit", "status": "failed", "return_code": 2},
        )
        result = api.exec(BOX, ["false"])
        self.assertFalse(result.ok)
        with self.assertRaises(SailboxError) as caught:
            result.check()
        self.assertIn("boom", str(caught.exception))

    def test_a_dropped_stream_is_reconciled_through_the_wait_route(self):
        transport = FakeTransport(
            {
                ("POST", f"/sailboxes/{BOX}/exec"): event_stream(
                    {"type": "started", "exec_request_id": "exec_9"},
                    {"type": "stdout", "data": out("partial")},
                ),
                ("POST", f"/sailboxes/{BOX}/exec/exec_9/wait"): {
                    "exec_request_id": "exec_9",
                    "status": "succeeded",
                    "stdout": "partial",
                    "stderr": "",
                    "return_code": 0,
                },
            }
        )
        result = SailboxClient(transport).exec(BOX, ["slow"])
        self.assertEqual((result.status, result.return_code), ("succeeded", 0))
        self.assertEqual(transport.calls[-1]["path"], f"/sailboxes/{BOX}/exec/exec_9/wait")

    def test_a_reconcile_that_also_fails_leaves_the_result_honest(self):
        transport = FakeTransport(
            {
                ("POST", f"/sailboxes/{BOX}/exec"): event_stream({"type": "started", "exec_request_id": "e1"}),
                ("POST", f"/sailboxes/{BOX}/exec/e1/wait"): SailboxError("gone", status=503),
            }
        )
        result = SailboxClient(transport).exec(BOX, ["x"])
        self.assertEqual(result.status, "unconfirmed")
        self.assertIsNone(result.return_code)
        self.assertFalse(result.ok)

    def test_an_error_event_marks_the_command_failed(self):
        api, _ = self.client(
            {"type": "started", "exec_request_id": "e"},
            {"type": "error", "error_code": "permission_denied"},
            {"type": "exit", "status": "failed", "return_code": 1},
        )
        result = api.exec(BOX, ["x"])
        self.assertEqual(result.error_code, "permission_denied")
        self.assertFalse(result.ok)


class FileTests(unittest.TestCase):
    def test_upload_sends_bytes_with_the_documented_query(self):
        transport = FakeTransport({("PUT", f"/sailboxes/{BOX}/files"): {"size_bytes": 3}})
        SailboxClient(transport).upload(BOX, "/workspace/run.sh", b"#!\n", mode=0o700)
        call = transport.last("PUT", f"/sailboxes/{BOX}/files")
        self.assertEqual(call["data"], b"#!\n")
        self.assertEqual(
            call["query"],
            {"path": "/workspace/run.sh", "mode": 0o700, "create_parents": "true"},
        )

    def test_upload_refuses_a_bad_mode_a_bad_path_and_text(self):
        api = SailboxClient(FakeTransport())
        with self.assertRaises(SailboxError):
            api.upload(BOX, "/workspace/x", b"", mode=0o7777)
        with self.assertRaises(SailboxError):
            api.upload(BOX, "/workspace/../etc/passwd", b"")
        with self.assertRaises(SailboxError):
            api.upload(BOX, "/workspace/x", "not bytes")

    def test_download_asks_for_raw_bytes(self):
        transport = FakeTransport({("GET", f"/sailboxes/{BOX}/files"): b"{}"})
        self.assertEqual(SailboxClient(transport).download(BOX, "/workspace/health.json"), b"{}")
        self.assertTrue(transport.last("GET", f"/sailboxes/{BOX}/files")["raw"])


class LifecycleTests(unittest.TestCase):
    def test_checkpoint_sends_name_and_ttl_and_refuses_a_foreign_answer(self):
        transport = FakeTransport(
            {
                ("POST", f"/sailboxes/{BOX}/checkpoint"): {
                    "sailbox_id": BOX,
                    "checkpoint_id": CHECKPOINT,
                    "status": "running",
                    "checkpoint_generation": 3,
                }
            }
        )
        api = SailboxClient(transport)
        row = api.checkpoint(BOX, name="code-only", ttl_seconds=30 * 86400)
        self.assertEqual(row["checkpoint_id"], CHECKPOINT)
        self.assertEqual(
            transport.last("POST", f"/sailboxes/{BOX}/checkpoint")["body"],
            {"name": "code-only", "ttl_seconds": 2592000},
        )
        transport.responses[("POST", f"/sailboxes/{BOX}/checkpoint")] = {
            "sailbox_id": "sb_00000000-0000-0000-0000-000000000000",
            "checkpoint_id": CHECKPOINT,
        }
        with self.assertRaises(SailboxError):
            api.checkpoint(BOX)

    def test_checkpoints_joins_the_operator_record_to_the_live_counters(self):
        transport = FakeTransport(
            {("GET", f"/sailboxes/{BOX}"): {"checkpoint_generation": 4,
                                            "last_checkpointed_at": "2026-09-15T10:00:00Z"}}
        )
        report = SailboxClient(transport).checkpoints(
            BOX, recorded=[{"checkpoint_id": CHECKPOINT, "name": "code-only"}]
        )
        self.assertEqual(report["checkpoint_generation"], 4)
        self.assertEqual(report["recorded"][0]["name"], "code-only")

    def test_fork_refuses_an_answer_from_another_checkpoint(self):
        transport = FakeTransport(
            {("POST", "/sailboxes/from_checkpoint"): {
                "sailbox_id": BOX, "status": "running",
                "checkpoint_id": "sbcp_deadbeef-0000-0000-0000-000000000000",
                "source_checkpoint_generation": 1}}
        )
        with self.assertRaises(SailboxError):
            SailboxClient(transport).from_checkpoint(CHECKPOINT, name="fork-1")

    def test_fork_sends_the_checkpoint_and_the_new_name(self):
        transport = FakeTransport(
            {("POST", "/sailboxes/from_checkpoint"): {
                "sailbox_id": BOX, "status": "running", "checkpoint_id": CHECKPOINT,
                "source_checkpoint_generation": 1}}
        )
        SailboxClient(transport).from_checkpoint(CHECKPOINT, name="fork-1")
        self.assertEqual(
            transport.last("POST", "/sailboxes/from_checkpoint")["body"],
            {"checkpoint_id": CHECKPOINT, "name": "fork-1"},
        )

    def test_sleep_carries_a_wake_time_when_one_is_given(self):
        transport = FakeTransport({("POST", f"/sailboxes/{BOX}/sleep"): {"status": "sleeping"}})
        api = SailboxClient(transport)
        api.sleep(BOX)
        self.assertEqual(transport.last("POST", f"/sailboxes/{BOX}/sleep")["body"], {})
        api.sleep(BOX, wake_at="2026-09-16T13:00:00Z")
        self.assertEqual(
            transport.last("POST", f"/sailboxes/{BOX}/sleep")["body"],
            {"wake_at": "2026-09-16T13:00:00Z"},
        )

    def test_a_resume_that_can_never_work_raises(self):
        transport = FakeTransport(
            {("POST", f"/sailboxes/{BOX}/resume"): {
                "sailbox_id": BOX, "status": "failed",
                "resume_state": "terminal_unavailable", "error_message": "host gone"}}
        )
        with self.assertRaises(SailboxError):
            SailboxClient(transport).resume(BOX)

    def test_auto_sleep_refuses_a_window_alongside_automatic_off(self):
        api = SailboxClient(FakeTransport())
        with self.assertRaises(SailboxError):
            api.set_auto_sleep(BOX, automatic=False, min_seconds_before_sleep=30)

    def test_auto_sleep_sends_what_the_api_documents(self):
        transport = FakeTransport({("POST", f"/sailboxes/{BOX}/auto_sleep"): {}})
        api = SailboxClient(transport)
        api.set_auto_sleep(BOX, automatic=False)
        self.assertEqual(transport.last()["body"], {"automatic": False})
        api.set_auto_sleep(BOX, automatic=True, min_seconds_before_sleep=300)
        self.assertEqual(transport.last()["body"], {"automatic": True, "min_seconds_before_sleep": 300})

    def test_every_mutating_call_carries_an_idempotency_key(self):
        transport = FakeTransport()
        api = SailboxClient(transport)
        for call in (api.sleep, api.resume, api.pause, api.terminate):
            transport.calls.clear()
            try:
                call(BOX)
            except SailboxError:
                pass
            self.assertTrue(transport.calls[0]["idempotency_key"], msg=call.__name__)

    def test_an_id_that_is_not_a_sailbox_id_never_reaches_the_api(self):
        transport = FakeTransport()
        for bad in ("sb-nope", "../secrets", "", None):
            with self.subTest(bad=bad), self.assertRaises(SailboxError):
                SailboxClient(transport).get(bad)
        self.assertEqual(transport.calls, [])

    def test_list_pages_until_has_more_is_false(self):
        transport = FakeTransport(
            {("GET", "/sailboxes"): [
                {"sailboxes": [{"sailbox_id": BOX}], "has_more": True},
                {"sailboxes": [{"sailbox_id": "sb_2"}], "has_more": False},
            ]}
        )
        rows = SailboxClient(transport).list_boxes(app=APP)
        self.assertEqual(len(rows), 2)
        self.assertEqual(transport.calls[1]["query"]["offset"], 1)


class SpendTests(unittest.TestCase):
    RESPONSE = {
        "start_at": "2026-09-01T00:00:00Z",
        "end_at": "2026-09-15T12:00:00Z",
        "finalized_cost_usd_nanos": 12_300_000,
        "estimated_active_cost_usd_nanos": 700_000,
        "estimated_total_cost_usd_nanos": 13_000_000,
        "duration_seconds": 3600,
        "vcpu_seconds": 120.5,
        "rates": {
            "vcpu_second_usd_nanos": 4167,
            "memory_gib_second_usd_nanos": 2222,
            "state_disk_gib_second_usd_nanos": 194,
            "s_creation_usd_nanos": 5_000_000,
        },
    }

    def test_the_spend_query_names_this_box_and_the_window(self):
        transport = FakeTransport({("GET", "/sailboxes/spend"): self.RESPONSE})
        SailboxClient(transport).spend(sailbox=BOX, since="2026-09-01T00:00:00Z")
        self.assertEqual(
            transport.last("GET", "/sailboxes/spend")["query"],
            {"sailbox_id": BOX, "from": "2026-09-01T00:00:00Z"},
        )

    def test_nanos_become_dollars(self):
        report = usd(self.RESPONSE)
        self.assertAlmostEqual(report["total_usd"], 0.013)
        self.assertAlmostEqual(report["finalized_usd"], 0.0123)
        self.assertAlmostEqual(report["s_creation_usd"], 0.005)
        self.assertAlmostEqual(report["rates_usd_per_hour"]["vcpu"], 0.015, places=4)
        self.assertAlmostEqual(report["rates_usd_per_hour"]["memory_gib"], 0.008, places=4)

    def test_a_spend_response_missing_everything_still_reduces(self):
        self.assertEqual(usd({})["total_usd"], 0.0)

    def test_hourly_cost_follows_observed_usage_not_the_ceiling(self):
        # Sail bills what a Sailbox uses, not what its size allows: a mostly idle floor is cheap.
        cost = hourly_cost(
            {"cpu_used_vcpu": 0.02, "memory_used_bytes": 200 * 1024**2,
             "disk_used_bytes": 3 * 1024**3},
            usd(self.RESPONSE),
        )
        self.assertLess(cost, 0.01)
        self.assertGreater(cost, 0.0)

    def test_status_projects_the_box_and_checks_the_policy(self):
        policy = floor_policy()
        transport = FakeTransport(
            {
                ("GET", f"/sailboxes/{BOX}"): {
                    "sailbox_id": BOX, "name": "ltcm-floor", "status": "running",
                    "vcpu_count": 1, "memory_mib": 16384, "state_disk_size_gib": 32,
                    "auto_sleep": {"automatic": False},
                    "egress_policy": {"document": policy},
                },
                ("GET", "/sailboxes/spend"): self.RESPONSE,
            }
        )
        report = SailboxClient(transport).status(BOX, expected_egress=policy)
        self.assertTrue(report["egress_ok"])
        self.assertEqual(report["vcpu_count"], 1)
        self.assertEqual(len(report["egress"]), len(policy["allowlist"]))
        self.assertAlmostEqual(report["spend"]["total_usd"], 0.013)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
