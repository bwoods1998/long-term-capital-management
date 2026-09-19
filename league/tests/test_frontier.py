"""Adversarial tests of `league.frontier`: the one request shape that may reach the gateway, how
its answer is read, and how every failure becomes a `FrontierError`.

The fake `opener` stands in for `urllib.request.urlopen`: it records each `Request` and returns a
context-manager response with `.headers.get` and a JSON body (or raises what urllib would raise).
"""

from __future__ import annotations

import io
import json
import socket
import unittest
import urllib.error
from decimal import Decimal

from league.frontier import AGENT_HEADER, COST_HEADER, MAX_OUTPUT_TOKENS, MODEL, Answer, Frontier, FrontierError, extract_json, output_text

GATEWAY = "https://gateway.example.test"
SECRET = "gw-token-5f1c-DO-NOT-LEAK"


class FakeResponse:
    def __init__(self, payload=None, *, headers=None, raw: bytes | None = None):
        self.body = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.headers = dict(headers or {})
        self.closed = False

    def read(self, *_):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True
        return False


class FakeOpener:
    """Returns (or raises) the scripted items in order and keeps every request it was given."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[tuple] = []

    def __call__(self, request, timeout=None):
        self.calls.append((request, timeout))
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def request(self):
        return self.calls[-1][0]

    def headers(self) -> dict[str, str]:
        return {k.lower(): v for k, v in self.request.header_items()}

    def body(self) -> dict:
        return json.loads(self.request.data.decode("utf-8"))


def http_error(code: int, detail: str = "refused") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(GATEWAY, code, "error", {}, io.BytesIO(detail.encode("utf-8")))


def ok(text='{"approve": true}', *, cost="0.0421", **more) -> FakeResponse:
    headers = {} if cost is None else {COST_HEADER: cost}
    return FakeResponse({"output_text": text, "usage": {"input_tokens": 10, "output_tokens": 5}, "model": MODEL, **more}, headers=headers)


def frontier(opener, **kw) -> Frontier:
    return Frontier(GATEWAY, lambda: SECRET, opener=opener, **kw)


class RequestShape(unittest.TestCase):
    def test_the_request_the_gateway_receives(self):
        opener = FakeOpener(ok())
        frontier(opener, timeout=123.0).ask(system="be careful", user="the packet", agent="audit:alpha")
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, GATEWAY + "/v1/frontier/responses")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 123.0)
        headers = opener.headers()
        self.assertEqual(headers["authorization"], "Bearer " + SECRET)
        self.assertEqual(headers[AGENT_HEADER.lower()], "audit:alpha")
        self.assertEqual(headers["content-type"], "application/json")
        body = opener.body()
        self.assertEqual(body["model"], "gpt-6-astra")
        self.assertEqual(body["model"], MODEL)
        self.assertEqual(body["input"], [{"role": "system", "content": "be careful"}, {"role": "user", "content": "the packet"}])
        self.assertEqual(body["max_output_tokens"], 6000)
        self.assertEqual(body["reasoning"], {"effort": "medium"})
        # The gateway settles a call when its one response arrives: nothing streamed, nothing detached.
        self.assertNotIn("stream", body)
        self.assertNotIn("background", body)
        self.assertEqual(set(body), {"model", "input", "max_output_tokens", "reasoning"})

    def test_a_trailing_slash_on_the_gateway_url_is_not_doubled(self):
        opener = FakeOpener(ok())
        Frontier(GATEWAY + "///", lambda: SECRET, opener=opener).ask(system="s", user="u", agent="a")
        self.assertEqual(opener.request.full_url, GATEWAY + "/v1/frontier/responses")

    def test_max_output_tokens_is_clamped_to_the_gateways_reservation(self):
        for asked, sent in ((10**9, 16000), (16001, 16000), (16000, 16000), (15999, 15999), (1, 1), (0, 1), (-50, 1), ("700", 700)):
            opener = FakeOpener(ok())
            frontier(opener).ask(system="s", user="u", agent="a", max_output_tokens=asked)
            self.assertEqual(opener.body()["max_output_tokens"], sent, asked)
        self.assertEqual(MAX_OUTPUT_TOKENS, 16000)

    def test_the_agent_header_is_cut_to_sixty_characters(self):
        opener = FakeOpener(ok())
        frontier(opener).ask(system="s", user="u", agent="audit:" + "x" * 200)
        self.assertEqual(len(opener.headers()[AGENT_HEADER.lower()]), 60)

    def test_the_token_is_read_for_every_call_so_a_rotated_token_is_used(self):
        tokens = iter(["first", "second"])
        opener = FakeOpener(ok(), ok())
        client = Frontier(GATEWAY, lambda: next(tokens), opener=opener)
        client.ask(system="s", user="u", agent="a")
        self.assertEqual(opener.headers()["authorization"], "Bearer first")
        client.ask(system="s", user="u", agent="a")
        self.assertEqual(opener.headers()["authorization"], "Bearer second")

    def test_the_effort_and_a_custom_model_are_sent(self):
        opener = FakeOpener(ok())
        frontier(opener, model="gpt-6-mini").ask(system="s", user="u", agent="a", effort="high")
        self.assertEqual((opener.body()["model"], opener.body()["reasoning"]), ("gpt-6-mini", {"effort": "high"}))

    def test_the_response_is_closed(self):
        response = ok()
        frontier(FakeOpener(response)).ask(system="s", user="u", agent="a")
        self.assertTrue(response.closed)


class ReadingTheAnswer(unittest.TestCase):
    def test_cost_usage_model_and_text(self):
        answer = frontier(FakeOpener(ok("hello", cost="0.0421"))).ask(system="s", user="u", agent="a")
        self.assertIsInstance(answer, Answer)
        self.assertEqual(answer.text, "hello")
        self.assertEqual(answer.cost_usd, Decimal("0.0421"))
        self.assertIsInstance(answer.cost_usd, Decimal)
        self.assertEqual(answer.usage, {"input_tokens": 10, "output_tokens": 5})
        self.assertEqual(answer.model, MODEL)

    def test_a_missing_or_unreadable_cost_header_is_zero(self):
        for cost in (None, "", "free", "1,5", "$0.04"):
            answer = frontier(FakeOpener(ok(cost=cost))).ask(system="s", user="u", agent="a")
            self.assertEqual(answer.cost_usd, Decimal(0), cost)

    def test_a_cost_header_that_is_not_a_finite_number_is_not_passed_on(self):
        # BUG (low): frontier.py:100. `Decimal("NaN")` and `Decimal("Infinity")` parse without
        # `InvalidOperation`, so they become `Answer.cost_usd`. The auditor then evaluates
        # `answer.cost_usd > 0`, which RAISES `decimal.InvalidOperation` for NaN, and
        # `Economy.charge` raises on Infinity: an audit that was paid for ends in an uncaught
        # exception with no `audit.verdict` row. The header comes from our own gateway, so this
        # needs a gateway bug to happen, but the House should not crash on it.
        # FIX: `if not cost_usd.is_finite() or cost_usd < 0: cost_usd = Decimal(0)` (or raise FrontierError).
        for cost in ("NaN", "Infinity", "-Infinity", "sNaN"):
            answer = frontier(FakeOpener(ok(cost=cost))).ask(system="s", user="u", agent="a")
            self.assertTrue(answer.cost_usd.is_finite(), cost)

    def test_the_model_falls_back_to_the_one_asked_for(self):
        answer = frontier(FakeOpener(FakeResponse({"output_text": "x"}))).ask(system="s", user="u", agent="a")
        self.assertEqual((answer.model, answer.usage), (MODEL, {}))

    def test_output_text_from_the_convenience_field(self):
        self.assertEqual(output_text({"output_text": "plain", "output": [{"type": "message", "content": [{"type": "output_text", "text": "other"}]}]}), "plain")

    def test_output_text_from_the_output_items(self):
        payload = {
            "output": [
                {"type": "reasoning", "content": [{"type": "output_text", "text": "thinking aloud"}], "summary": []},
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "first"},
                    {"type": "refusal", "text": "not this"},
                    {"type": "text", "text": "second"},
                    {"type": "output_text", "text": None},
                    "junk",
                ]},
                "junk",
                {"type": "message", "content": [{"type": "output_text", "text": "third"}]},
            ]
        }
        self.assertEqual(output_text(payload), "first\nsecond\nthird")

    def test_an_empty_or_wrongly_typed_convenience_field_falls_back_to_the_items(self):
        items = [{"type": "message", "content": [{"type": "output_text", "text": "from items"}]}]
        for field in ("", None, 7, ["x"]):
            self.assertEqual(output_text({"output_text": field, "output": items}), "from items", field)

    def test_nothing_to_read_is_an_empty_string(self):
        for payload in ({}, {"output": None}, {"output": []}, {"output": [{"type": "message", "content": None}]}):
            self.assertEqual(output_text(payload), "")

    def test_ask_reads_the_items_form_end_to_end(self):
        payload = {"output": [{"type": "message", "content": [{"type": "output_text", "text": 'noise {"approve": false} noise'}]}]}
        answer = frontier(FakeOpener(FakeResponse(payload, headers={COST_HEADER: "0.01"}))).ask(system="s", user="u", agent="a")
        self.assertEqual(answer.json(), {"approve": False})


class ExtractJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(extract_json('{"approve": true, "findings": []}'), {"approve": True, "findings": []})

    def test_noise_before_and_after(self):
        text = 'Here is my verdict:\n```json\n{"approve": false, "summary": "look-ahead"}\n```\nThank you.'
        self.assertEqual(extract_json(text), {"approve": False, "summary": "look-ahead"})

    def test_braces_that_are_not_json_are_skipped(self):
        text = 'the set {a, b} and {not: json} come first, then {"approve": true, "n": {"deep": [1, {"x": 2}]}} and {"late": 1}'
        self.assertEqual(extract_json(text), {"approve": True, "n": {"deep": [1, {"x": 2}]}})

    def test_the_first_object_wins_and_an_array_is_not_an_answer(self):
        self.assertEqual(extract_json('[1, 2] {"a": 1} {"b": 2}'), {"a": 1})
        # An object inside an array is still the first object in the text.
        self.assertEqual(extract_json('[{"inner": 1}]'), {"inner": 1})

    def test_braces_inside_strings(self):
        self.assertEqual(extract_json('x {"summary": "uses {braces} and \\"quotes\\"", "approve": false} y'),
                         {"summary": "uses {braces} and \"quotes\"", "approve": False})

    def test_an_empty_object(self):
        self.assertEqual(extract_json("{}"), {})

    def test_no_object_raises(self):
        for text in ("", "no json here", "{", "{{{{", "[1, 2, 3]", '"approve": true', "{'approve': True}"):
            with self.assertRaises(FrontierError, msg=text):
                extract_json(text)

    def test_a_truncated_answer_raises(self):
        with self.assertRaises(FrontierError):
            extract_json('{"approve": true, "findings": [{"severity": "blo')

    def test_answer_json_uses_it(self):
        self.assertEqual(Answer('ok {"a": 1}', Decimal(0), {}, MODEL).json(), {"a": 1})
        with self.assertRaises(FrontierError):
            Answer("nothing", Decimal(0), {}, MODEL).json()


class Failures(unittest.TestCase):
    def test_http_refusals_carry_their_status(self):
        for code in (402, 403, 429, 500, 502, 503):
            refusal = http_error(code, "the month's budget is spent")
            self.addCleanup(refusal.close)
            with self.assertRaises(FrontierError) as caught:
                frontier(FakeOpener(refusal)).ask(system="s", user="u", agent="a")
            self.assertEqual(caught.exception.status, code)
            self.assertIn(str(code), str(caught.exception))
            self.assertIn("the month's budget is spent", str(caught.exception))
            self.assertNotIn(SECRET, str(caught.exception))

    def test_the_refusal_detail_is_cut_short(self):
        refusal = http_error(500, "x" * 5000)
        self.addCleanup(refusal.close)
        with self.assertRaises(FrontierError) as caught:
            frontier(FakeOpener(refusal)).ask(system="s", user="u", agent="a")
        self.assertLess(len(str(caught.exception)), 400)

    def test_transport_failures_have_no_status(self):
        for exc in (urllib.error.URLError("dns"), socket.timeout("slow"), TimeoutError("slow"), ConnectionResetError("reset"), OSError("broken")):
            with self.assertRaises(FrontierError) as caught:
                frontier(FakeOpener(exc)).ask(system="s", user="u", agent="a")
            self.assertIsNone(caught.exception.status, exc)
            self.assertNotIn(SECRET, str(caught.exception))

    def test_a_body_that_is_not_json_is_a_frontier_error(self):
        for raw in (b"", b"<html>bad gateway</html>", b'{"output_text": "cut'):
            with self.assertRaises(FrontierError):
                frontier(FakeOpener(FakeResponse(raw=raw))).ask(system="s", user="u", agent="a")

    def test_a_json_body_that_is_not_an_object_is_a_frontier_error(self):
        # BUG (low-medium): frontier.py:92 and :103. `json.load` happily returns a list, a string
        # or `null`; `output_text(payload)` then calls `payload.get` and raises AttributeError
        # OUTSIDE the try block. Callers catch only `FrontierError` (auditor.py:88), so the House
        # gets an uncaught AttributeError instead of a veto row, and a gateway or proxy that
        # answers 200 with `null` or `[]` crashes the judge pass.
        # FIX: after `json.load`, `if not isinstance(payload, dict): raise FrontierError(...)`.
        for raw in (b"[]", b"null", b'"ok"', b"42"):
            with self.assertRaises(FrontierError, msg=raw):
                frontier(FakeOpener(FakeResponse(raw=raw))).ask(system="s", user="u", agent="a")


if __name__ == "__main__":
    unittest.main()
