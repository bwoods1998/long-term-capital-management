"""`league.claude`: the one request shape that reaches the gateway's Claude route, how the answer is read (the stop reason
before the content, text blocks only), how every failure becomes a typed `ClaudeError`, and the funded meter's reading.
The fake opener stands in for `urllib.request.urlopen` (league/tests/test_frontier.py)."""

from __future__ import annotations

import io
import json
import socket
import unittest
import urllib.error
from decimal import Decimal

from league.claude import (AGENT_HEADER, COST_HEADER, MAX_TOKENS, MAX_TOKENS_STREAM, MODEL, REQUEST_HEADER, ROLE_HEADER, Claude,
                           ClaudeError, ClaudeMeter, ClaudeRefusal, ClaudeTruncated, extract_json, request_body,
                           reservation_ceiling)
from league.tests.test_frontier import FakeOpener, FakeResponse

GATEWAY = "https://gateway.example.test"
SECRET = "gw-token-5f1c-DO-NOT-LEAK"
USAGE = {"input_tokens": 2000, "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 0, "output_tokens": 900}


def message(text='{"decision": "retire"}', *, stop="end_turn", model=MODEL, usage=USAGE, cost="0.047000", **more):
    payload = {"id": "msg_1", "type": "message", "role": "assistant", "model": model, "stop_reason": stop, "usage": usage,
               "content": [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": text}], **more}
    return FakeResponse(payload, headers={} if cost is None else {COST_HEADER: cost})


ERRORS: list[urllib.error.HTTPError] = []


def http_error(code, detail="refused", headers=None):
    error = urllib.error.HTTPError(GATEWAY, code, "error", headers or {}, io.BytesIO(detail.encode("utf-8")))
    ERRORS.append(error)
    return error


def tearDownModule():
    for error in ERRORS:
        error.close()


def client(opener, **kw):
    return Claude(GATEWAY, lambda: SECRET, opener=opener, **kw)


class RequestShape(unittest.TestCase):
    def test_the_request_the_gateway_receives(self):
        opener = FakeOpener(message())
        schema = {"type": "object", "additionalProperties": False, "required": ["decision"],
                  "properties": {"decision": {"type": "string"}}}
        client(opener).ask("THE RULES", "the family", agent="swarm-diagnostician", role="diagnostician", schema=schema)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, GATEWAY + "/v1/claude/messages")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 600.0)
        headers = opener.headers()
        self.assertEqual(headers["authorization"], "Bearer " + SECRET)
        self.assertEqual(headers[AGENT_HEADER.lower()], "swarm-diagnostician")
        self.assertEqual(headers[ROLE_HEADER.lower()], "diagnostician")
        self.assertEqual(opener.body(), {
            "model": "claude-opus-5-5", "max_tokens": 16000,
            "system": [{"type": "text", "text": "THE RULES", "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": "the family"}],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": schema}},
        })

    def test_no_sampling_no_prefill_no_forced_tool_and_effort_always_explicit(self):
        body = request_body(MODEL, "s", [{"role": "user", "content": "q"}], effort="medium", cache=False)
        self.assertEqual(body["output_config"], {"effort": "medium"}, "Opus 5.5 defaults to medium: always say it")
        self.assertNotIn("cache_control", body["system"][0])
        for key in ("temperature", "top_p", "top_k", "tool_choice", "tools", "stream"):
            self.assertNotIn(key, body)
        self.assertNotIn("system", request_body(MODEL, "", [{"role": "user", "content": "q"}]), "no empty system block")
        self.assertEqual(request_body(MODEL, "s", [{"role": "user", "content": "q"}], max_tokens=10 ** 6)["max_tokens"], MAX_TOKENS)
        for bad in ([{"role": "user", "content": "q"}, {"role": "assistant", "content": "{"}], [],
                    [{"role": "system", "content": "x"}], [{"role": "user", "content": ""}]):
            with self.assertRaises(ClaudeError):
                request_body(MODEL, "s", bad)
        with self.assertRaises(ClaudeError):
            request_body(MODEL, "s", [{"role": "user", "content": "q"}], effort="minimal")
        opener = FakeOpener()
        with self.assertRaises(ClaudeError):
            client(opener).ask("s", "q", agent="a", role="Bad Role")
        self.assertEqual(opener.calls, [], "refused before any request")

    def test_converse_carries_earlier_turns(self):
        opener = FakeOpener(message("ok"))
        client(opener).converse("s", [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                      {"role": "user", "content": "c"}], agent="a")
        self.assertEqual([t["role"] for t in opener.body()["messages"]], ["user", "assistant", "user"])

    def test_the_ceiling_is_never_below_the_gateways_worst_case(self):
        body = request_body(MODEL, "rules " * 3000, [{"role": "user", "content": "packet " * 5000}])
        size = len(json.dumps(body).encode("utf-8"))
        gateway = (Decimal(size + 4096) * 5 + Decimal(16000) * 20) / 1000000  # gateway/lib/claude.mjs worstCase
        self.assertGreaterEqual(reservation_ceiling(body), gateway)
        self.assertLess(reservation_ceiling(body) - gateway, Decimal("0.00001"))
        sonnet = request_body("claude-sonnet-5", "s", [{"role": "user", "content": "q"}], max_tokens=1000)
        self.assertGreaterEqual(reservation_ceiling(sonnet), (Decimal(len(json.dumps(sonnet)) + 4096) * Decimal("2.5") + 1000 * 10) / 10 ** 6)
        with self.assertRaises(ClaudeError):
            reservation_ceiling({**body, "model": "claude-opus-5"})


class Answers(unittest.TestCase):
    def test_only_text_blocks_are_the_answer_and_the_gateway_cost_is_verified(self):
        answer = client(FakeOpener(message("hello"))).ask("s", "q", agent="a")
        self.assertEqual(answer.text, "hello")
        self.assertEqual(answer.cost_usd, Decimal("0.047000"))
        self.assertTrue(answer.cost_verified)
        self.assertEqual(answer.stop_reason, "end_turn")
        self.assertEqual(answer.usage["cache_creation_input_tokens"], 3000)
        self.assertIsNone(answer.data, "no schema, no parse")
        unverified = client(FakeOpener(message("hello", cost=None))).ask("s", "q", agent="a")
        self.assertFalse(unverified.cost_verified)
        self.assertIsNone(unverified.cost_usd)
        other = client(FakeOpener(message("hello", model="claude-sonnet-5"))).ask("s", "q", agent="a")
        self.assertFalse(other.cost_verified, "an answer from another model is not this call's verified cost")

    def test_a_schema_answer_is_parsed_and_one_without_json_is_an_error_that_carries_its_bill(self):
        schema = {"type": "object"}
        self.assertEqual(client(FakeOpener(message('{"decision": "rewrite"}'))).ask("s", "q", agent="a", schema=schema).data,
                         {"decision": "rewrite"})
        self.assertEqual(client(FakeOpener(message('Here: {"decision": "retire"} done'))).ask("s", "q", agent="a", schema=schema).data,
                         {"decision": "retire"})
        with self.assertRaises(ClaudeError) as caught:
            client(FakeOpener(message("no json here"))).ask("s", "q", agent="a", schema=schema)
        self.assertEqual(caught.exception.cost_usd, Decimal("0.047000"))

    def test_the_stop_reason_is_read_before_the_content(self):
        with self.assertRaises(ClaudeRefusal) as refused:
            client(FakeOpener(message("", stop="refusal", stop_details={"type": "refusal", "category": "cyber"}))).ask("s", "q", agent="a")
        self.assertEqual(refused.exception.cost_usd, Decimal("0.047000"), "a refusal is billed at its usage")
        self.assertEqual(refused.exception.answer.stop_reason, "refusal")
        with self.assertRaises(ClaudeTruncated) as cut:
            client(FakeOpener(message('{"decision": "rew', stop="max_tokens"))).ask("s", "q", agent="a", schema={"type": "object"})
        self.assertEqual(cut.exception.cost_usd, Decimal("0.047000"))
        with self.assertRaises(ClaudeError):
            client(FakeOpener(message("x", stop="pause_turn"))).ask("s", "q", agent="a")

    def test_every_failure_is_a_claude_error_with_its_status_and_the_gateways_settled_cost(self):
        with self.assertRaises(ClaudeError) as capped:
            client(FakeOpener(http_error(402, '{"error": "left of the $100.00 funded", "cap": "claude_funded"}'))).ask("s", "q", agent="a")
        self.assertEqual((capped.exception.status, capped.exception.cost_usd), (402, None))
        with self.assertRaises(ClaudeError) as lost:
            client(FakeOpener(http_error(502, "no answer", {COST_HEADER: "0.000000"}))).ask("s", "q", agent="a")
        self.assertEqual((lost.exception.status, lost.exception.cost_usd), (502, Decimal("0")))
        for failure in (urllib.error.URLError("down"), socket.timeout("slow"), ConnectionResetError("reset")):
            with self.assertRaises(ClaudeError) as caught:
                client(FakeOpener(failure)).ask("s", "q", agent="a")
            self.assertIsNone(caught.exception.status)
            self.assertIsNone(caught.exception.cost_usd, "unknown: the caller keeps its hold")
            self.assertNotIn(SECRET, str(caught.exception))
        with self.assertRaises(ClaudeError):
            client(FakeOpener(FakeResponse(raw=b"<html>"))).ask("s", "q", agent="a")

    def test_the_request_id_rides_along_and_the_gateways_record_of_it_can_be_read(self):
        opener = FakeOpener(message(), FakeResponse({"request": "swarm:a:1:ab", "state": "settled", "cost_usd": "0.047000"}),
                            FakeResponse({"request": "x", "state": "released", "cost_usd": "0.000000"}), FakeResponse({"state": "bogus"}),
                            urllib.error.URLError("down"))
        c = client(opener)
        c.ask("s", "q", agent="a", request_id="swarm:a:1:ab")
        self.assertEqual(opener.headers()[REQUEST_HEADER.lower()], "swarm:a:1:ab")
        self.assertEqual(c.settlement("swarm:a:1:ab"), {"state": "settled", "cost_usd": Decimal("0.047000")})
        self.assertEqual(opener.request.full_url, GATEWAY + "/v1/claude/request/swarm:a:1:ab")
        self.assertEqual(opener.request.get_method(), "GET")
        self.assertEqual(c.settlement("x"), {"state": "released", "cost_usd": Decimal("0")})
        self.assertIsNone(c.settlement("x"), "an unknown state is no record")
        self.assertIsNone(c.settlement("x"), "an unreadable gateway is no record")
        self.assertIsNone(c.settlement("bad id!"))
        with self.assertRaises(ClaudeError):
            client(FakeOpener()).ask("s", "q", agent="a", request_id="has space")

    def test_a_gateway_refusal_names_its_cap(self):
        for code, body, cap in ((503, '{"error": "Claude is not configured.", "cap": "setup"}', "setup"),
                                (423, '{"error": "kill", "cap": "kill_switch"}', "kill_switch"), (502, "<html>", None)):
            with self.assertRaises(ClaudeError) as caught:
                client(FakeOpener(http_error(code, body))).ask("s", "q", agent="a")
            self.assertEqual((caught.exception.status, caught.exception.cap), (code, cap))

    def test_extract_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n{"a": {"b": 2}}\n```'), {"a": {"b": 2}})
        self.assertIsNone(extract_json("nothing"))


START = {"type": "message_start", "message": {"id": "msg_9", "type": "message", "role": "assistant", "model": MODEL, "content": [],
                                               "stop_reason": None, "usage": {"input_tokens": 2000, "cache_read_input_tokens": 30000,
                                                                              "cache_creation_input_tokens": 0, "output_tokens": 1}}}


def events(text='{"decision": "retire"}', *, stop="end_turn", cost="0.184000", known=True, extra=(), cut=False):
    """A relayed stream: Anthropic's events (thinking, then the text in two deltas), then the gateway's ltcm.cost."""
    out = [START, {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
           {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Weighing it."}},
           {"type": "content_block_stop", "index": 0}, {"type": "ping"},
           {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
           {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text[: len(text) // 2]}},
           {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text[len(text) // 2:]}},
           {"type": "content_block_stop", "index": 1}, *extra]
    if not cut:
        out += [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 6000}},
                {"type": "message_stop"}]
    if cost is not None:
        out.append({"type": "ltcm.cost", "cost_usd": cost, "known": known, "stop": stop})
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in out)


class FakeStream:
    """A relayed event stream read line by line; `fail` (an exception) is raised after `fail_after` lines; `tick` moves
    the clock on every line."""

    def __init__(self, text, *, fail=None, fail_after=None, clock=None, tick=0.0, content_type="text/event-stream; charset=utf-8"):
        self.lines = text.encode("utf-8").splitlines(keepends=True)
        self.headers = {"Content-Type": content_type}
        self.fail, self.fail_after, self.clock, self.tick, self.read_lines = fail, fail_after, clock, tick, 0

    def readline(self):
        if self.fail is not None and self.read_lines >= self.fail_after:
            raise self.fail
        if self.clock is not None:
            self.clock[0] += self.tick
        self.read_lines += 1
        return self.lines.pop(0) if self.lines else b""

    def read(self):
        return b"".join(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Streaming(unittest.TestCase):
    def test_a_streamed_request_asks_for_events_summarized_thinking_and_up_to_32000_tokens(self):
        body = request_body(MODEL, "s", [{"role": "user", "content": "q"}], max_tokens=10 ** 6, stream=True)
        self.assertEqual((body["stream"], body["thinking"], body["max_tokens"]),
                         (True, {"type": "adaptive", "display": "summarized"}, MAX_TOKENS_STREAM))
        self.assertNotIn("stream", request_body(MODEL, "s", [{"role": "user", "content": "q"}]))
        opener = FakeOpener(FakeStream(events()))
        client(opener, read_timeout=120.0).ask("s", "q", agent="a", stream=True, max_tokens=32000)
        self.assertEqual(opener.calls[0][1], 120.0, "the socket timeout is the gap allowed between events")
        self.assertEqual((opener.body()["stream"], opener.body()["max_tokens"]), (True, 32000))

    def test_the_final_message_is_rebuilt_from_the_events_and_the_gateways_cost(self):
        answer = client(FakeOpener(FakeStream(events()))).ask("s", "q", agent="a", stream=True, schema={"type": "object"})
        self.assertEqual((answer.text, answer.data, answer.stop_reason, answer.id), ('{"decision": "retire"}', {"decision": "retire"},
                                                                                       "end_turn", "msg_9"))
        self.assertEqual(answer.usage, {"input_tokens": 2000, "cache_read_input_tokens": 30000, "cache_creation_input_tokens": 0,
                                        "output_tokens": 6000}, "input and cache from message_start, output from message_delta")
        self.assertEqual((answer.cost_usd, answer.cost_verified), (Decimal("0.184000"), True))
        self.assertEqual([b["type"] for b in answer.raw["content"]], ["thinking", "text"])

    def test_refusal_and_truncation_are_the_same_typed_errors_with_their_bill(self):
        with self.assertRaises(ClaudeRefusal) as refused:
            client(FakeOpener(FakeStream(events("", stop="refusal", cost="0.012000")))).ask("s", "q", agent="a", stream=True)
        self.assertEqual(refused.exception.cost_usd, Decimal("0.012000"))
        with self.assertRaises(ClaudeTruncated) as cut:
            client(FakeOpener(FakeStream(events('{"deci', stop="max_tokens")))).ask("s", "q", agent="a", stream=True)
        self.assertEqual(cut.exception.cost_usd, Decimal("0.184000"))

    def test_a_stream_that_errs_stops_early_or_loses_its_tail_is_an_error_with_what_the_gateway_booked(self):
        overloaded = {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
        with self.assertRaises(ClaudeError) as failed:
            client(FakeOpener(FakeStream(events(extra=[overloaded], cut=True, cost="0.064020")))).ask("s", "q", agent="a", stream=True)
        self.assertIn("overloaded_error", str(failed.exception))
        self.assertEqual(failed.exception.cost_usd, Decimal("0.064020"))
        with self.assertRaises(ClaudeError) as early:
            client(FakeOpener(FakeStream(events(cut=True, cost="0.662015", known=False)))).ask("s", "q", agent="a", stream=True)
        self.assertIn("ended before the answer", str(early.exception))
        self.assertEqual(early.exception.cost_usd, Decimal("0.662015"), "the worst case the gateway kept")
        # A complete answer whose ltcm.cost never came is still an answer: its cost is unknown (the caller's hold stands
        # and is trued up from the gateway's record of the call).
        lost = client(FakeOpener(FakeStream(events(cost=None)))).ask("s", "q", agent="a", stream=True)
        self.assertEqual((lost.text, lost.cost_usd, lost.cost_verified), ('{"decision": "retire"}', None, False))

    def test_a_complete_answer_whose_cost_the_gateway_could_not_read_is_not_verified(self):
        answer = client(FakeOpener(FakeStream(events(cost="0.662015", known=False)))).ask("s", "q", agent="a", stream=True)
        self.assertEqual((answer.cost_usd, answer.cost_verified), (Decimal("0.662015"), False))

    def test_a_quiet_stream_and_one_past_the_overall_limit_are_errors_with_an_unknown_cost(self):
        with self.assertRaises(ClaudeError) as quiet:
            client(FakeOpener(FakeStream(events(), fail=socket.timeout("timed out"), fail_after=6))).ask("s", "q", agent="a", stream=True)
        self.assertIn("stalled", str(quiet.exception))
        self.assertIsNone(quiet.exception.cost_usd)
        now = [0.0]
        with self.assertRaises(ClaudeError) as slow:
            client(FakeOpener(FakeStream(events(), clock=now, tick=50.0)), timeout=600.0, clock=lambda: now[0]).ask(
                "s", "q", agent="a", stream=True)
        self.assertIn("600-second limit", str(slow.exception))

    def test_a_gateway_that_answers_json_to_a_streamed_call_is_read_as_json(self):
        answer = client(FakeOpener(message("hello"))).ask("s", "q", agent="a", stream=True)
        self.assertEqual((answer.text, answer.cost_verified), ("hello", True))
        with self.assertRaises(ClaudeError) as capped:
            client(FakeOpener(http_error(402, '{"error": "funded", "cap": "claude_funded"}'))).ask("s", "q", agent="a", stream=True)
        self.assertEqual(capped.exception.cap, "claude_funded")


class Meter(unittest.TestCase):
    def health(self, claude):
        return FakeResponse({"ok": True, "claude": claude})

    def test_the_funded_total_less_what_is_spent_is_read_and_kept_for_its_ttl(self):
        now = [1000.0]
        opener = FakeOpener(self.health({"cap_usd": "100.00", "spent_usd": "12.345678", "inflight_usd": "0.3", "calls": 4}),
                            self.health({"cap_usd": "100.00", "spent_usd": "20.000000"}))
        meter = ClaudeMeter(GATEWAY, lambda: SECRET, opener=opener, ttl=60, clock=lambda: now[0])
        self.assertEqual(meter.remaining(), Decimal("87.654322"))
        self.assertEqual(meter.remaining(), Decimal("87.654322"))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.request.full_url, GATEWAY + "/v1/health")
        now[0] += 61
        self.assertEqual(meter.remaining(), Decimal("80.000000"))

    def test_an_unreadable_gateway_is_unknown_never_a_number(self):
        for reply in (self.health({"cap_usd": "100.00", "spent_usd": "0.000000", "configured": False}),urllib.error.URLError("down"), self.health(None), self.health({"cap_usd": "x", "spent_usd": "1"}),
                      FakeResponse(raw=b"not json")):
            meter = ClaudeMeter(GATEWAY, lambda: SECRET, opener=FakeOpener(reply), ttl=0)
            self.assertIsNone(meter.remaining())


if __name__ == "__main__":
    unittest.main()
