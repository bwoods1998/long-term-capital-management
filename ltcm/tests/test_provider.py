import email.message
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError

from ltcm.events import EventLog
from ltcm.provider import (
    PROFILES,
    DISPLAY_NAMES,
    RATE_CARD_URL,
    BudgetExceeded,
    FunctionCall,
    Provider,
    ProviderError,
    Transport,
    TransportError,
    cost_from_usage,
    function_calls_of,
    output_text_of,
    reasoning_summaries_of,
    reservation_usd,
)

PRO = "deepseek-ai/DeepSeek-V4-Pro-0813"
FLASH = "deepseek-ai/DeepSeek-V4-Flash-0731"


def response(
    *,
    rid="resp_one",
    status="completed",
    output=None,
    usage="default",
    model=PRO,
    incomplete=None,
):
    body = {"id": rid, "object": "response", "status": status, "model": model}
    if output is not None:
        body["output"] = output
    if usage == "default":
        usage = {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 200, "reasoning_tokens": 0},
            "output_tokens": 500,
            "output_tokens_details": {"cached_tokens": 0, "reasoning_tokens": 300},
            "total_tokens": 1500,
        }
    if usage is not None:
        body["usage"] = usage
    if incomplete is not None:
        body["incomplete_details"] = {"reason": incomplete}
    return body


def message(text):
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def call(name, arguments, call_id="call_1"):
    return {"type": "function_call", "call_id": call_id, "name": name, "arguments": arguments}


class FakeTransport:
    """Scripted stand-in for the HTTPS transport. Never touches a socket."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, method, route, body=None, idempotency_key=None):
        self.calls.append({"method": method, "route": route, "body": body, "key": idempotency_key})
        if not self.script:
            raise AssertionError(f"unscripted transport call: {method} {route}")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def posts(self):
        return [c for c in self.calls if c["method"] == "POST"]


class ProviderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.time = [1_789_000_000.0]
        self.slept = []
        self.log = EventLog(self.root / "events.sqlite", clock=lambda: self.time[0])

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def provider(self, transport, **kwargs):
        kwargs.setdefault("floor_cap_usd_per_day", "25")
        built = Provider(
            self.root / "provider.sqlite",
            transport=transport,
            clock=lambda: self.time[0],
            log=self.log,
            sleep=self.slept.append,
            **kwargs,
        )
        self.addCleanup(built.close)
        return built

    def respond(self, provider, profile="pro_flex", key="s1:0", cap="2.50", items=None, **kwargs):
        return provider.respond(
            profile,
            items or [{"role": "user", "content": "hello"}],
            desk_id="earnings-01",
            session_id="s1",
            request_key=key,
            desk_cap_usd_per_day=cap,
            **kwargs,
        )


class RateCardTests(unittest.TestCase):
    def test_every_profile_carries_the_september_2026_list_price(self):
        expected = {
            "pro_asap": (PRO, "asap", "0.92", "0.04", "2.77"),
            "pro_flex": (PRO, "flex", "0.46", "0.02", "1.39"),
            "flash_asap": (FLASH, "asap", "0.09", "0.02", "0.18"),
            "flash_flex": (FLASH, "flex", "0.05", "0.01", "0.09"),
            "kimi_asap": ("moonshotai/Kimi-K2.6", "asap", "1.00", "0.20", "4.00"),
            "kimi_balanced": ("moonshotai/Kimi-K2.6", "balanced", "0.45", "0.20", "3.00"),
            "kimi_flex": ("moonshotai/Kimi-K2.6", "flex", "0.35", "0.10", "2.00"),
            "k3": ("moonshotai/Kimi-K3", "asap", "2.50", "0.25", "12.50"),
            "glm_asap": ("zai-org/GLM-5.3", "asap", "0.98", "0.18", "3.08"),
            "glm_balanced": ("zai-org/GLM-5.3", "balanced", "0.50", "0.12", "2.50"),
            "glm_flex": ("zai-org/GLM-5.3", "flex", "0.40", "0.08", "1.80"),
            "glm_flash_asap": ("zai-org/GLM-5.3-Flash", "asap", "0.11", "0.02", "0.35"),
            "glm_flash_flex": ("zai-org/GLM-5.3-Flash", "flex", "0.05", "0.01", "0.18"),
            "oss_asap": ("openai/gpt-oss-120b", "asap", "0.06", "0.03", "0.40"),
        }
        self.assertEqual(PROFILES, expected)
        for name, (_, window, *prices) in PROFILES.items():
            self.assertIn(window, ("asap", "balanced", "standard", "flex"), name)
            for price in prices:
                self.assertEqual(str(Decimal(price)), price, name)

    def test_reservation_is_input_estimate_plus_the_whole_output_cap(self):
        # (3000/3 + 4096) input tokens at 0.46/M + 8192 output tokens at 1.39/M.
        self.assertEqual(reservation_usd("pro_flex", 3000, 8192), Decimal("0.01373104"))
        self.assertEqual(reservation_usd("flash_flex", 0, 1000), Decimal("0.00029480"))
        self.assertEqual(reservation_usd("k3", 30, 100), Decimal("0.01151500"))
        with self.assertRaises(ProviderError):
            reservation_usd("nope", 1, 1)

    def test_cost_from_usage_bills_cached_input_once(self):
        usage = {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 200},
            "output_tokens": 500,
        }
        # 800 * 0.46 + 200 * 0.02 + 500 * 1.39 = 1067 per million.
        self.assertEqual(cost_from_usage("pro_flex", usage), Decimal("0.00106700"))
        # Reasoning tokens are already inside output_tokens and are not billed again.
        usage["output_tokens_details"] = {"reasoning_tokens": 400, "cached_tokens": 0}
        self.assertEqual(cost_from_usage("pro_flex", usage), Decimal("0.00106700"))

    def test_cost_from_usage_refuses_inconsistent_accounting(self):
        for usage in (
            None,
            {},
            {"input_tokens": 10, "output_tokens": 5, "input_tokens_details": "?"},
            {"input_tokens": 10, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 11}},
            {"input_tokens": -1, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 0}},
            {"input_tokens": 1.5, "output_tokens": 5, "input_tokens_details": {"cached_tokens": 0}},
            {"input_tokens": 10, "output_tokens": None, "input_tokens_details": {"cached_tokens": 0}},
        ):
            self.assertIsNone(cost_from_usage("pro_flex", usage), usage)
        # Absent cache details are read as "nothing cached", which can only overcharge us.
        self.assertEqual(
            cost_from_usage("pro_flex", {"input_tokens": 10, "output_tokens": 5}),
            Decimal("0.00001155"),
        )


class BodyTests(ProviderCase):
    def test_body_matches_the_responses_api_shape(self):
        provider = self.provider(FakeTransport())
        body = provider.build_body(
            "pro_flex",
            [{"role": "user", "content": "hi"}],
            tools=[{"name": "quote", "description": "d", "parameters": {"type": "object"}}],
            reasoning_effort="high",
            max_output_tokens=4096,
            cache_key="earnings-01",
        )
        self.assertEqual(body["model"], PRO)
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertIs(body["tools"][0]["strict"], False)
        self.assertEqual(body["tool_choice"], "auto")
        self.assertEqual(body["reasoning"], {"effort": "high", "generate_summary": "detailed"})
        self.assertEqual(body["max_output_tokens"], 4096)
        self.assertIs(body["background"], True)  # flex must be background
        self.assertEqual(body["metadata"], {"completion_window": "flex"})
        self.assertEqual(body["prompt_cache_key"], "earnings-01")
        asap = provider.build_body("flash_asap", [{"role": "user", "content": "hi"}])
        self.assertIs(asap["background"], False)
        self.assertEqual(asap["metadata"], {"completion_window": "asap"})
        provider.close()

    def test_body_validation(self):
        provider = self.provider(FakeTransport())
        for kwargs in (
            {"profile": "nope"},
            {"reasoning_effort": "turbo"},
            {"max_output_tokens": 9},
            {"max_output_tokens": 99999},
            {"cache_key": "x" * 200},
        ):
            base = {"profile": "pro_flex", "items": [{"role": "user", "content": "hi"}]}
            base.update(kwargs)
            with self.assertRaises(ProviderError):
                provider.build_body(base.pop("profile"), base.pop("items"), **base)
        with self.assertRaises(ProviderError):
            provider.build_body("pro_flex", [])
        with self.assertRaises(ProviderError):
            provider.build_body("pro_flex", [{"role": "user", "content": "hi"}], tools=[{"a": 1}])
        provider.close()


class BudgetTests(ProviderCase):
    def test_desk_cap_refuses_before_dispatch(self):
        transport = FakeTransport()
        provider = self.provider(transport)
        with self.assertRaises(BudgetExceeded) as caught:
            self.respond(provider, cap="0.001")
        self.assertEqual(caught.exception.code, "provider_desk_cap_exceeded")
        self.assertEqual(transport.calls, [])
        self.assertIsNone(provider.record("s1:0"))
        self.assertEqual(provider.spent_today("earnings-01"), Decimal(0))
        provider.close()

    def test_floor_cap_refuses_even_when_the_desk_has_room(self):
        transport = FakeTransport()
        provider = self.provider(transport, floor_cap_usd_per_day="0.005")
        with self.assertRaises(BudgetExceeded) as caught:
            self.respond(provider, cap="100")
        self.assertEqual(caught.exception.code, "provider_floor_cap_exceeded")
        self.assertEqual(transport.calls, [])
        provider.close()

    def test_floor_cap_counts_every_desk(self):
        transport = FakeTransport(response(status="completed", usage=None))
        provider = self.provider(transport, floor_cap_usd_per_day="0.02")
        self.respond(provider, key="a:0", cap="100")
        spent = provider.spent_today()
        self.assertGreater(spent, Decimal("0.01"))
        with self.assertRaises(BudgetExceeded):
            provider.respond(
                "pro_flex",
                [{"role": "user", "content": "hello"}],
                desk_id="filings-01",
                session_id="s2",
                request_key="b:0",
                desk_cap_usd_per_day="100",
            )
        self.assertEqual(provider.spent_today("filings-01"), Decimal(0))
        provider.close()

    def test_balance_below_the_reserve_refuses(self):
        # 3106.14 fractional cents is $31.06, which is under a $50 reserve.
        transport = FakeTransport({"available": True, "balance": 3106.14, "balance_unavailable": False})
        provider = self.provider(transport, reserve_floor_usd="50")
        with self.assertRaises(BudgetExceeded) as caught:
            self.respond(provider)
        self.assertEqual(caught.exception.code, "provider_credit_below_reserve")
        self.assertEqual([c["method"] for c in transport.calls], ["GET"])
        self.assertEqual(transport.calls[0]["route"], "/v2/usage/summary")
        provider.close()

    def test_balance_reports_dollars_and_caches_for_sixty_seconds(self):
        transport = FakeTransport(
            {"available": True, "balance": 3106.14, "balance_unavailable": False},
            {"available": True, "balance": 10.0, "balance_unavailable": False},
        )
        provider = self.provider(transport)
        self.assertEqual(provider.check_balance(), Decimal("31.06"))
        self.assertEqual(provider.check_balance(), Decimal("31.06"))  # cached
        self.assertEqual(len(transport.calls), 1)
        self.time[0] += 61
        self.assertEqual(provider.check_balance(), Decimal("0.10"))
        provider.close()

    def test_unconfirmed_balance_is_not_a_refusal(self):
        transport = FakeTransport(
            {"available": True, "balance": None, "balance_unavailable": True},
            response(status="completed"),
        )
        provider = self.provider(transport, reserve_floor_usd="50")
        result = self.respond(provider)
        self.assertIsNone(provider.check_balance())  # still cached, no second lookup
        self.assertEqual(result.status, "completed")
        provider.close()


class DispatchTests(ProviderCase):
    def test_foreground_request_settles_from_usage(self):
        transport = FakeTransport(response(model=FLASH, output=[message("done")]))
        provider = self.provider(transport)
        result = self.respond(provider, profile="flash_asap")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output_text, "done")
        self.assertEqual(result.response_id, "resp_one")
        # 800 * 0.09 + 200 * 0.02 + 500 * 0.18 = 166 per million.
        self.assertEqual(result.cost_usd, Decimal("0.00016600"))
        self.assertEqual(provider.spent_today("earnings-01"), Decimal("0.00016600"))
        post = transport.posts[0]
        self.assertEqual(post["route"], "/v1/responses")
        self.assertEqual(post["key"], result.request_id)
        self.assertIs(post["body"]["background"], False)
        provider.close()

    def test_request_key_dedupe_never_pays_twice(self):
        transport = FakeTransport(response(output=[message("first")]))
        provider = self.provider(transport)
        first = self.respond(provider)
        again = self.respond(provider)
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(first.request_id, again.request_id)
        self.assertEqual(again.output_text, "first")
        self.assertEqual(again.cost_usd, first.cost_usd)
        self.assertEqual(provider.spent_today("earnings-01"), first.cost_usd)
        provider.close()

    def test_dedupe_resumes_a_dispatched_request_by_polling(self):
        transport = FakeTransport(
            response(status="queued", usage=None),
            TransportError("provider_http_503", retry_after=7),
            response(status="completed", output=[message("late")]),
        )
        provider = self.provider(transport)
        with self.assertRaises(TransportError) as caught:
            self.respond(provider)
        self.assertEqual(caught.exception.code, "provider_http_503")
        self.assertEqual(caught.exception.retry_after, 7)
        self.assertEqual(provider.record("s1:0")["response_id"], "resp_one")
        resumed = self.respond(provider)  # the retry polls; it does not resubmit
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(resumed.output_text, "late")
        provider.close()

    def test_background_polls_until_completion(self):
        transport = FakeTransport(
            response(status="queued", usage=None),
            response(status="in_progress", usage=None),
            response(status="completed", output=[message("ok")]),
        )
        provider = self.provider(transport, poll_interval=3.0)
        result = self.respond(provider)
        self.assertEqual(result.status, "completed")
        self.assertEqual([c["method"] for c in transport.calls], ["POST", "GET", "GET"])
        self.assertEqual(transport.calls[1]["route"], "/v1/responses/resp_one")
        self.assertEqual(self.slept, [3.0, 3.0])
        self.assertIs(transport.posts[0]["body"]["background"], True)
        provider.close()

    def test_background_failure_is_terminal_and_keeps_the_reservation(self):
        transport = FakeTransport(
            response(status="queued", usage=None),
            response(status="failed", usage=None),
        )
        provider = self.provider(transport)
        result = self.respond(provider)
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.terminal is False)
        reserved = Decimal(provider.record("s1:0")["reserved_usd"])
        self.assertEqual(result.cost_usd, reserved)
        self.assertEqual(provider.spent_today("earnings-01"), reserved)
        self.assertEqual(provider.record("s1:0")["error"], "usage_unsettled")
        provider.close()

    def test_unknown_usage_keeps_the_reservation_as_the_charge(self):
        transport = FakeTransport(
            response(model=FLASH, status="completed", output=[message("hi")], usage={"input_tokens": "lots"})
        )
        provider = self.provider(transport)
        result = self.respond(provider, profile="flash_asap")
        reserved = Decimal(provider.record("s1:0")["reserved_usd"])
        self.assertEqual(result.cost_usd, reserved)
        self.assertEqual(provider.spent_today("earnings-01"), reserved)
        self.assertEqual(provider.record("s1:0")["error"], "usage_unsettled")
        provider.close()

    def test_incomplete_is_terminal_and_reported(self):
        transport = FakeTransport(
            response(status="incomplete", output=[message("half")], incomplete="max_output_tokens")
        )
        provider = self.provider(transport)
        result = self.respond(provider, profile="pro_asap")
        self.assertTrue(result.incomplete)
        self.assertEqual(result.incomplete_reason, "max_output_tokens")
        self.assertEqual(result.output_text, "half")
        provider.close()

    def test_a_different_model_is_refused_after_the_id_is_stored(self):
        transport = FakeTransport(response(model="moonshotai/Kimi-K3"))
        provider = self.provider(transport)
        with self.assertRaises(ProviderError) as caught:
            self.respond(provider, profile="pro_asap")
        self.assertEqual(caught.exception.code, "provider_model_mismatch")
        row = provider.record("s1:0")
        self.assertEqual(row["response_id"], "resp_one")  # persisted before validation
        self.assertEqual(row["error"], "provider_model_mismatch")
        provider.close()

    def test_a_bad_response_id_is_refused(self):
        transport = FakeTransport({"id": "not-a-response", "status": "completed", "model": PRO})
        provider = self.provider(transport)
        with self.assertRaises(ProviderError) as caught:
            self.respond(provider)
        self.assertEqual(caught.exception.code, "provider_bad_response_id")
        provider.close()

    def test_provider_request_event_is_private_and_carries_the_cost(self):
        transport = FakeTransport(response(model=FLASH, output=[message("done")]))
        provider = self.provider(transport)
        result = self.respond(provider, profile="flash_asap")
        events = self.log.read(stream="ops", kind="provider.request")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertFalse(event.public)
        self.assertEqual(event.payload["request_id"], result.request_id)
        self.assertEqual(event.payload["desk_id"], "earnings-01")
        self.assertEqual(event.payload["session_id"], "s1")
        self.assertEqual(event.payload["profile"], "flash_asap")
        self.assertEqual(event.payload["status"], "completed")
        self.assertEqual(event.payload["cost_usd"], "0.00016600")
        self.assertEqual(event.payload["usage"]["output_tokens"], 500)
        self.assertNotIn("_response_id", event.public_payload())
        provider.close()

    def test_estimate_matches_what_respond_reserves(self):
        transport = FakeTransport(response(status="completed", usage=None))
        provider = self.provider(transport)
        items = [{"role": "user", "content": "hello"}]
        self.respond(provider, items=items, max_output_tokens=2048)
        reserved = Decimal(provider.record("s1:0")["reserved_usd"])
        chars = len(json.dumps({"input": items, "tools": []}, separators=(",", ":")))
        self.assertEqual(provider.estimate("pro_flex", chars, 2048), reserved)
        provider.close()


class ParsingTests(unittest.TestCase):
    def test_reasoning_summaries_tolerate_every_shape(self):
        payload = {
            "output": [
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "first"}]},
                {"type": "reasoning", "summary": "second"},
                {"type": "reasoning", "summary": [{"text": "third"}, {"text": "   "}]},
                {"type": "reasoning", "content": [{"summary": [{"text": "fourth"}]}]},
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [{"type": "output_text", "text": "not a summary"}]},
            ]
        }
        self.assertEqual(
            reasoning_summaries_of(payload), ["first", "second", "third", "fourth"]
        )
        self.assertEqual(reasoning_summaries_of(None), [])
        self.assertEqual(reasoning_summaries_of({"output": "plain"}), [])

    def test_output_text_joins_message_blocks(self):
        payload = {
            "output": [
                {"type": "reasoning", "summary": [{"text": "hidden"}]},
                {"type": "message", "content": [{"type": "output_text", "text": "a"}]},
                {"type": "message", "content": [{"type": "output_text", "text": "b"}]},
            ]
        }
        self.assertEqual(output_text_of(payload), "a\nb")
        self.assertEqual(output_text_of({"output": "bare"}), "bare")

    def test_function_calls_report_bad_json_instead_of_raising(self):
        payload = {
            "output": [
                call("quote", '{"instrument": {"symbol": "AAPL"}}', "c1"),
                call("bars", "{not json", "c2"),
                call("news", "[1, 2]", "c3"),
                call("facts", {"symbol": "AAPL"}, "c4"),
                call("chain", 17, "c5"),
                {"type": "function_call", "call_id": "c6", "arguments": "{}"},
            ]
        }
        calls = function_calls_of(payload)
        self.assertEqual([c.call_id for c in calls], ["c1", "c2", "c3", "c4", "c5", "c6"])
        self.assertEqual(calls[0].arguments, {"instrument": {"symbol": "AAPL"}})
        self.assertTrue(calls[0].ok)
        self.assertFalse(calls[1].ok)
        self.assertIn("not valid JSON", calls[1].error)
        self.assertEqual(calls[1].arguments, {})
        self.assertIn("must be a JSON object", calls[2].error)
        self.assertEqual(calls[3].arguments, {"symbol": "AAPL"})  # already-decoded arguments
        self.assertIn("not a JSON string", calls[4].error)
        self.assertIn("no name", calls[5].error)
        self.assertEqual(function_calls_of({"output": []}), [])

    def test_function_call_defaults(self):
        one = FunctionCall("c1", "quote")
        self.assertEqual(one.arguments, {})
        self.assertTrue(one.ok)


class TransportTests(unittest.TestCase):
    def test_only_the_allowlisted_routes_are_reachable(self):
        transport = Transport(key_source=lambda: "k")
        self.assertTrue(transport.allowed("POST", "/v1/responses"))
        self.assertTrue(transport.allowed("GET", "/v1/responses/resp_abc123"))
        self.assertTrue(transport.allowed("GET", "/v2/usage/summary"))
        self.assertTrue(transport.allowed("GET", "/v2/usage/summary?range=7d"))
        self.assertTrue(transport.allowed("GET", RATE_CARD_URL))
        for method, route in (
            ("POST", RATE_CARD_URL),
            ("GET", "https://docs.sailresearch.com/"),
            ("GET", "https://docs.sailresearch.com/support.md"),
            ("GET", "https://docs.sailresearch.com/pricing.md?x=1"),
            ("GET", "http://docs.sailresearch.com/pricing.md"),
            ("GET", "/v1/responses"),
            ("POST", "/v1/responses/resp_abc"),
            ("DELETE", "/v1/responses/resp_abc"),
            ("POST", "/v2/usage/summary"),
            ("GET", "/v1/responses/../../admin"),
            ("GET", "/v1/responses/resp_abc?x=1"),
            ("GET", "/v2/usage/summary?range=evil"),
            ("GET", "/v1/models"),
        ):
            self.assertFalse(transport.allowed(method, route), f"{method} {route}")

    def test_the_transport_only_speaks_to_the_sail_host(self):
        for base in ("http://api.sailresearch.com", "https://evil.example.com", "https://api.sailresearch.com/v1"):
            with self.assertRaises(ValueError):
                Transport(base_url=base, key_source=lambda: "k")
        with self.assertRaises(ValueError):
            Transport(key_source=lambda: "k", headers={"Authorization": "Bearer other"})

    def test_http_errors_collapse_to_codes_and_expose_retry_after(self):
        headers = email.message.Message()
        headers["Retry-After"] = "30"
        opener = _Opener(HTTPError("https://api.sailresearch.com/v1/responses", 429, "slow down", headers, None))
        transport = Transport(key_source=lambda: "secret-key", opener=opener)
        with self.assertRaises(TransportError) as caught:
            transport("POST", "/v1/responses", {"model": "m"}, "idem-1")
        self.assertEqual(caught.exception.code, "provider_http_429")
        self.assertEqual(caught.exception.retry_after, 30)
        self.assertNotIn("secret-key", str(caught.exception))

    def test_socket_failures_collapse_to_timeout_or_unconfirmed(self):
        cases = {
            TimeoutError(): "provider_transport_timeout",
            URLError(TimeoutError()): "provider_transport_timeout",
            URLError("no route to host"): "provider_transport_unconfirmed",
            ValueError("anything else"): "provider_transport_unconfirmed",
        }
        for error, code in cases.items():
            transport = Transport(key_source=lambda: "k", opener=_Opener(error))
            with self.assertRaises(TransportError) as caught:
                transport("GET", "/v2/usage/summary")
            self.assertEqual(caught.exception.code, code)

    def test_headers_carry_the_key_and_the_idempotency_key(self):
        opener = _Opener(_Response({"id": "resp_x", "status": "completed"}))
        transport = Transport(key_source=lambda: "sail-key", opener=opener)
        self.assertEqual(transport("POST", "/v1/responses", {"background": False}, "idem-1")["id"], "resp_x")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer sail-key")
        self.assertEqual(opener.request.get_header("Idempotency-key"), "idem-1")
        self.assertEqual(opener.timeout, 1500)  # foreground generation is awaited inline, patiently
        transport("GET", "/v2/usage/summary")
        self.assertEqual(opener.timeout, 45)
        self.assertIsNone(opener.request.get_header("Idempotency-key"))

    def test_oversized_bodies_are_refused_before_sending(self):
        opener = _Opener(_Response({"id": "resp_x", "status": "completed"}))
        transport = Transport(key_source=lambda: "k", opener=opener)
        with self.assertRaises(TransportError) as caught:
            transport("POST", "/v1/responses", {"input": "x" * 9_000_000})
        self.assertEqual(caught.exception.code, "provider_request_too_large")
        with self.assertRaises(TransportError) as caught:
            transport("GET", "/v1/models")
        self.assertEqual(caught.exception.code, "provider_route_not_allowed")

    def test_a_missing_key_is_a_code_not_a_path(self):
        transport = Transport(key_source=_no_key)
        with self.assertRaises(TransportError) as caught:
            transport("GET", "/v2/usage/summary")
        self.assertEqual(caught.exception.code, "provider_key_missing")


class RateCardDriftTests(ProviderCase):
    """`rate_card_check` diffs `PROFILES` against the published card, and only alerts."""

    #: One row per profile the floor holds, in the page's `aria-label` shape.
    LIVE = {
        ("DeepSeek V4 Pro", "Default (ASAP)"): ("0.92", "0.04", "2.77"),
        ("DeepSeek V4 Pro", "Flex"): ("0.46", "0.02", "1.39"),
        ("DeepSeek V4 Flash", "Default (ASAP)"): ("0.09", "0.02", "0.18"),
        ("DeepSeek V4 Flash", "Flex"): ("0.05", "0.01", "0.09"),
        ("Kimi K2.6", "Default (ASAP)"): ("1.00", "0.20", "4.00"),
        ("Kimi K2.6", "Balanced"): ("0.45", "0.20", "3.00"),
        ("Kimi K2.6", "Flex"): ("0.35", "0.10", "2.00"),
        ("Kimi K3", "Default (ASAP)"): ("2.50", "0.25", "12.50"),
        ("GLM-5.3", "Default (ASAP)"): ("0.98", "0.18", "3.08"),
        ("GLM-5.3", "Balanced"): ("0.50", "0.12", "2.50"),
        ("GLM-5.3", "Flex"): ("0.40", "0.08", "1.80"),
        ("GLM-5.3 Flash", "Default (ASAP)"): ("0.11", "0.02", "0.35"),
        ("GLM-5.3 Flash", "Flex"): ("0.05", "0.01", "0.18"),
        ("gpt-oss-120b", "Default (ASAP)"): ("0.06", "0.03", "0.40"),
    }

    def page(self, overrides=None, drop=()):
        rows = dict(self.LIVE)
        rows.update(overrides or {})
        for key in drop:
            rows.pop(key, None)
        lines = ["# Pricing", ""]
        for (model, window), (inp, cached, out) in rows.items():
            lines.append(
                f'<tr aria-label="{model} {window} pricing: input ${inp}, '
                f'cached ${cached}, output ${out} per 1M tokens."><td>{model}</td></tr>'
            )
        return "\n".join(lines)

    def checker(self, payload):
        return self.provider(lambda method, route, body=None, idempotency_key=None: payload)

    def alerts(self):
        return [e.payload for e in self.log.read(kind="ops.alert", limit=100)]

    def test_a_card_that_matches_raises_nothing(self):
        result = self.checker({"text": self.page()}).rate_card_check()
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["unchecked"], [])
        self.assertEqual(result["checked"], len(PROFILES))
        self.assertEqual(self.alerts(), [])

    def test_a_price_that_moved_is_named_in_an_alert(self):
        page = self.page({("GLM-5.3", "Default (ASAP)"): ("1.40", "0.26", "4.40")})
        result = self.checker({"text": page}).rate_card_check()
        self.assertEqual([d["profile"] for d in result["drift"]], ["glm_asap"])
        self.assertEqual(result["drift"][0]["published"], ["1.40", "0.26", "4.40"])
        self.assertEqual(result["drift"][0]["ours"], ["0.98", "0.18", "3.08"])
        texts = [a["text"] for a in self.alerts()]
        self.assertEqual(len(texts), 1)
        self.assertIn("glm_asap", texts[0])
        self.assertIn("0.98/0.18/3.08", texts[0])
        self.assertIn("1.40/0.26/4.40", texts[0])
        self.assertEqual(self.alerts()[0]["level"], "error")

    def test_a_profile_with_no_published_row_is_flagged_rather_than_passed(self):
        page = self.page(drop=[("gpt-oss-120b", "Default (ASAP)")])
        result = self.checker({"text": page}).rate_card_check()
        self.assertEqual(result["unchecked"], ["oss_asap"])
        self.assertEqual(self.alerts()[0]["level"], "warn")
        self.assertIn("no published row for oss_asap", self.alerts()[0]["text"])

    def test_a_page_whose_format_changed_fails_loudly(self):
        result = self.checker({"text": "# Pricing\n\nSee the table."}).rate_card_check()
        self.assertEqual(result["error"], "unparsed")
        self.assertIn("format has changed", self.alerts()[0]["text"])

    def test_the_check_never_edits_the_profiles(self):
        before = dict(PROFILES)
        page = self.page({("Kimi K3", "Default (ASAP)"): ("9.99", "9.99", "9.99")})
        self.checker({"text": page}).rate_card_check()
        self.assertEqual(PROFILES, before)

    def test_a_transport_failure_is_quiet(self):
        def broken(method, route, body=None, idempotency_key=None):
            raise TransportError("provider_transport_timeout")

        result = self.provider(broken).rate_card_check()
        self.assertEqual(result["error"], "TransportError")
        self.assertEqual(result["drift"], [])
        self.assertEqual(self.alerts(), [])

    def test_the_page_is_fetched_from_the_docs_url_only(self):
        seen = []

        def transport(method, route, body=None, idempotency_key=None):
            seen.append((method, route))
            return {"text": self.page()}

        self.provider(transport).rate_card_check()
        self.assertEqual(seen, [("GET", RATE_CARD_URL)])

    def test_a_plain_string_body_is_accepted_too(self):
        result = self.checker(self.page()).rate_card_check()
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["rows"], len(self.LIVE))

    def grouped_page(self, names):
        """The card as it is published now: each model's rows inside a `<tbody data-model>`
        group, with a display name that is prose and may carry a date suffix."""
        lines = ["# Pricing", ""]
        for slug, display in names.items():
            lines.append(f'      <tbody className="pricing-model-group" data-model="{slug}">')
            for (model, window), (inp, cached, out) in self.LIVE.items():
                if model != DISPLAY_NAMES[slug]:
                    continue
                lines.append(
                    f'        <tr className="pricing-row" aria-label="{display} {window} pricing: '
                    f'input ${inp}, cached ${cached}, output ${out} per 1M tokens.">'
                )
            lines.append("      </tbody>")
        return "\n".join(lines)

    def test_rows_are_matched_by_the_model_slug_when_the_display_name_drifts(self):
        # Sail renamed the DeepSeek rows "DeepSeek V4 Pro 0813" and "DeepSeek V4 Flash 0731";
        # the slug in the group did not change, and the slug is what the API takes.
        names = {slug: display for slug, display in DISPLAY_NAMES.items()}
        names["deepseek-ai/DeepSeek-V4-Pro-0813"] = "DeepSeek V4 Pro 0813"
        names["deepseek-ai/DeepSeek-V4-Flash-0731"] = "DeepSeek V4 Flash 0731"
        result = self.checker({"text": self.grouped_page(names)}).rate_card_check()
        self.assertEqual(result["unchecked"], [])
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["checked"], len(PROFILES))
        self.assertEqual(self.alerts(), [])

    def test_a_row_in_the_wrong_group_is_not_mistaken_for_ours(self):
        page = self.grouped_page(dict(DISPLAY_NAMES)).replace(
            'data-model="openai/gpt-oss-120b"', 'data-model="openai/gpt-oss-120b-v2"'
        ).replace("gpt-oss-120b Default", "gpt-oss-120b v2 Default")
        result = self.checker({"text": page}).rate_card_check()
        self.assertEqual(result["unchecked"], ["oss_asap"])

    def test_punctuation_in_a_model_name_is_not_a_price_change(self):
        page = self.page().replace("GLM-5.3 Flash", "GLM 5.3 flash")
        result = self.checker({"text": page}).rate_card_check()
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["unchecked"], [])


class RateCardTransportTests(unittest.TestCase):
    def test_the_rate_card_is_fetched_as_text_without_the_key(self):
        class TextResponse(_Response):
            def __init__(self, text):
                self.raw = text.encode("utf-8")

        opener = _Opener(TextResponse('aria-label="GLM-5.3 Flex pricing: ..."'))
        transport = Transport(key_source=lambda: "sail-key", opener=opener)
        payload = transport("GET", RATE_CARD_URL)
        self.assertIn("aria-label", payload["text"])
        self.assertEqual(opener.request.full_url, RATE_CARD_URL)
        self.assertIsNone(opener.request.get_header("Authorization"))
        self.assertEqual(opener.timeout, 45)


def _no_key():
    raise TransportError("provider_key_missing")


class _Response:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.raw


class _Opener:
    """Stands in for urllib's opener. Records the request; never opens a socket."""

    def __init__(self, result):
        self.result = result
        self.request = None
        self.timeout = None

    def open(self, request, timeout=None):
        self.request = request
        self.timeout = timeout
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


if __name__ == "__main__":
    unittest.main()
