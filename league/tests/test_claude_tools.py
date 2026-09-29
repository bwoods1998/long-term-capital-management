"""`league.claude` tool calls (Sept 29, 2026: the swarm's top researchers run their tool loop on Claude Sonnet 5.5): the one
tool-loop body the gateway admits (`tool_request_body`), a streamed answer rebuilt block by block (text, thinking with its
signature, tool calls from their `input_json_delta` fragments) into exactly the message a non-streamed call returns, strict
parsing of a call's input, and the typed errors a refused or cut turn raises with its bill. The fake opener stands in for
`urllib.request.urlopen` (league/tests/test_frontier.py)."""

from __future__ import annotations

import json
import math
import unittest
from decimal import Decimal

from league.claude import (MAX_TOKENS, MAX_TOKENS_STREAM, Claude, ClaudeError, ClaudeRefusal, ClaudeTruncated, ToolUse,
                           reservation_ceiling, tool_request_body)
from league.tests.test_claude import ERRORS, SECRET, FakeStream, http_error
from league.tests.test_frontier import GATEWAY, FakeOpener, FakeResponse

MODEL = "claude-sonnet-5-5"
MARK = {"type": "ephemeral"}
SIG = "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds"
TOOLS = [{"name": "gym_run", "description": "Run a version.", "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}},
          "eager_input_streaming": True},
         {"name": "notebook", "description": "Your memory.", "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
          "eager_input_streaming": True, "cache_control": MARK}]
SYSTEM = [{"type": "text", "text": "You are a researcher.", "cache_control": MARK}]
TURNS = [{"role": "user", "content": [{"type": "text", "text": "YOUR FAMILY"}, {"type": "text", "text": "Cycle 5.", "cache_control": MARK}]}]
USAGE = {"input_tokens": 1200, "cache_creation_input_tokens": 23000, "cache_read_input_tokens": 14500, "output_tokens": 1}
CODE = 'PARAMS = {"wing": 5}\n\ndef decide(ctx):\n    return []  # "quoted" é'

#: The message a non-streamed call would return: summarized thinking, a progress update, text and two calls.
FINAL = [
    {"type": "thinking", "thinking": "The trade count is thin; widen the wings.", "signature": SIG},
    {"type": "text", "text": "Widening the wings."},
    {"type": "tool_use", "id": "toolu_01A", "name": "gym_run", "input": {"code": CODE, "why": "wider → more trades"}},
    {"type": "thinking", "thinking": "", "signature": SIG + "2"},
    {"type": "tool_use", "id": "toolu_01B", "name": "notebook", "input": {"action": "append", "text": "Wider wings."}, "caller": {"type": "direct"}},
]


def pieces(value: dict, cut: int = 7) -> list[str]:
    """A call's input as Anthropic streams it: its JSON in fragments that split strings, escapes and characters anywhere."""
    text = json.dumps(value)
    return [text[i:i + cut] for i in range(0, len(text), cut)]


def tool_events(blocks=FINAL, *, stop="tool_use", cost="0.086800", known=True, fragments=None, cut=False, output=2400):
    """A relayed tool-loop stream: every block of `blocks` as start + deltas + stop, then the stop and the gateway's cost.
    `fragments` {index: [partial_json, ...]} replaces a call's fragments (for invalid or truncated input)."""
    out = [{"type": "message_start", "message": {"id": "msg_t", "type": "message", "role": "assistant", "model": MODEL, "content": [],
                                                 "stop_reason": None, "usage": USAGE}}]
    for index, block in enumerate(blocks):
        kind = block["type"]
        if kind == "thinking":
            out.append({"type": "content_block_start", "index": index, "content_block": {"type": "thinking", "thinking": ""}})
            if block["thinking"]:
                half = len(block["thinking"]) // 2
                out += [{"type": "content_block_delta", "index": index, "delta": {"type": "thinking_delta", "thinking": part}}
                        for part in (block["thinking"][:half], block["thinking"][half:])]
            out.append({"type": "content_block_delta", "index": index, "delta": {"type": "signature_delta", "signature": block["signature"]}})
        elif kind == "text":
            out.append({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            out.append({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": block["text"]}})
        elif kind == "tool_use":
            start = {k: v for k, v in block.items() if k != "input"}
            out.append({"type": "content_block_start", "index": index, "content_block": {**start, "input": {}}})
            parts = (fragments or {}).get(index, [""] + pieces(block["input"]))
            out += [{"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": p}} for p in parts]
        out.append({"type": "content_block_stop", "index": index})
        out.append({"type": "ping"})
    if not cut:
        out += [{"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": output}},
                {"type": "message_stop"}]
    if cost is not None:
        out.append({"type": "ltcm.cost", "cost_usd": cost, "known": known, "stop": stop})
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in out)


def tearDownModule():
    for error in ERRORS:
        error.close()


def client(opener, **kw):
    return Claude(GATEWAY, lambda: SECRET, model=MODEL, opener=opener, **kw)


def turn(claude, **kw):
    args = dict(agent="swarm-researcher", role="researcher", max_tokens=16000, effort="medium", request_id="swarm:condor:c5:m0:ab12")
    args.update(kw)
    return claude.messages(SYSTEM, TURNS, TOOLS, **args)


class Body(unittest.TestCase):
    def test_the_tool_loop_body_the_gateway_admits(self):
        body = tool_request_body(MODEL, SYSTEM, TURNS, TOOLS, max_tokens=16000, effort="medium")
        self.assertEqual(body, {"model": MODEL, "max_tokens": 16000, "stream": True, "system": SYSTEM, "tools": TOOLS,
                                "tool_choice": {"type": "auto"}, "messages": TURNS,
                                "thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "medium"}})
        self.assertNotIn("budget_tokens", json.dumps(body), "adaptive thinking with an effort, never a budget")
        for key in ("temperature", "top_p", "top_k"):
            self.assertNotIn(key, body)
        unstreamed = tool_request_body(MODEL, "plain", TURNS, TOOLS, tool_choice={"type": "none"}, max_tokens=10 ** 6, stream=False)
        self.assertEqual((unstreamed["thinking"], unstreamed["max_tokens"], unstreamed["tool_choice"], unstreamed["system"]),
                         ({"type": "adaptive"}, MAX_TOKENS, {"type": "none"}, [{"type": "text", "text": "plain"}]))
        self.assertNotIn("stream", unstreamed)
        self.assertEqual(tool_request_body(MODEL, SYSTEM, TURNS, TOOLS, max_tokens=10 ** 6)["max_tokens"], MAX_TOKENS_STREAM)
        # The loop's turns: a call, its thinking passed back with its signature, its result, the next note.
        loop = TURNS + [{"role": "assistant", "content": FINAL},
                        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01A", "content": "{}"},
                                                     {"type": "tool_result", "tool_use_id": "toolu_01B", "content": "bad", "is_error": True},
                                                     {"type": "text", "text": "Tools offered now: every tool."}]}]
        self.assertEqual(tool_request_body(MODEL, SYSTEM, loop, TOOLS)["messages"], loop)

    def test_what_the_gateway_would_refuse_fails_here_first(self):
        refused = {
            "forced tool choice": dict(tool_choice={"type": "any"}),
            "a named tool": dict(tool_choice={"type": "tool", "name": "gym_run"}),
            "an unknown effort": dict(effort="extreme"),
            "a bad tool name": dict(tools=[{**TOOLS[0], "name": "gym run"}]),
            "a repeated tool": dict(tools=[TOOLS[0], TOOLS[0]]),
            "a server tool": dict(tools=TOOLS + [{"type": "web_search_20260209", "name": "web_search"}]),
            "strict": dict(tools=[{**TOOLS[0], "strict": True}]),
            "no tools": dict(tools=[]),
            "a schema that is not an object": dict(tools=[{**TOOLS[0], "input_schema": {"type": "array"}}]),
            "a fifth marker": dict(tools=[{**t, "cache_control": MARK} for t in TOOLS] + [{"name": "x", "input_schema": {"type": "object"},
                                                                                          "cache_control": MARK}]),
            "a one-hour marker": dict(system=[{"type": "text", "text": "s", "cache_control": {"type": "ephemeral", "ttl": "1h"}}]),
            "an assistant turn last": dict(messages=TURNS + [{"role": "assistant", "content": "prefill"}]),
            "a thinking block without its signature": dict(messages=TURNS + [
                {"role": "assistant", "content": [{"type": "thinking", "thinking": ""}]}, TURNS[0]]),
            "a thinking block with a marker": dict(messages=TURNS + [
                {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": SIG, "cache_control": MARK}]}, TURNS[0]]),
            "a call from code execution": dict(messages=TURNS + [
                {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "gym_run", "input": {},
                                                   "caller": {"type": "code_execution_20260120"}}]}, TURNS[0]]),
            "an image": dict(messages=[{"role": "user", "content": [{"type": "image", "source": {}}]}]),
            "an empty turn": dict(messages=[{"role": "user", "content": ""}]),
        }
        for why, change in refused.items():
            args = dict(model=MODEL, system=SYSTEM, messages=TURNS, tools=TOOLS)
            args.update(change)
            model, system, messages, tools = args.pop("model"), args.pop("system"), args.pop("messages"), args.pop("tools")
            with self.subTest(why), self.assertRaises(ClaudeError):
                tool_request_body(model, system, messages, tools, **args)

    def test_the_hold_is_the_gateways_worst_case_for_the_same_bytes_and_counts_every_tool_and_turn(self):
        body = tool_request_body(MODEL, SYSTEM, TURNS + [{"role": "assistant", "content": FINAL},
                                                          {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01A",
                                                                                        "content": "y" * 12000}]}], TOOLS, max_tokens=16000)
        size = len(json.dumps(body).encode("utf-8"))
        # gateway/lib/claude.mjs worstCase: ceil(((bytes + 4096) x $2.50 + max_tokens x $10) per million), in micro-dollars.
        worst = Decimal(math.ceil((size + 4096) * 2.5 + 16000 * 10)) / 1000000
        ceiling = reservation_ceiling(body)
        self.assertGreaterEqual(ceiling, worst)
        self.assertLess(ceiling - worst, Decimal("0.00001"))
        smaller = tool_request_body(MODEL, SYSTEM, TURNS, TOOLS, max_tokens=16000)
        self.assertGreater(ceiling - reservation_ceiling(smaller), Decimal("0.03"), "twelve thousand bytes of result are held")


class Stream(unittest.TestCase):
    def test_the_streamed_answer_is_exactly_the_message_a_non_streamed_call_returns(self):
        opener = FakeOpener(FakeStream(tool_events()))
        answer = turn(client(opener, read_timeout=120.0))
        self.assertEqual(list(answer.content), FINAL, "every block as it came: thinking, its signature, the calls' parsed inputs")
        self.assertEqual(answer.tool_uses, (ToolUse("toolu_01A", "gym_run", FINAL[2]["input"], raw="".join(pieces(FINAL[2]["input"]))),
                                            ToolUse("toolu_01B", "notebook", FINAL[4]["input"], raw="".join(pieces(FINAL[4]["input"])))))
        self.assertEqual(answer.tool_uses[0].input["code"], CODE, "escapes and characters split across fragments")
        self.assertEqual((answer.text, answer.stop_reason, answer.cost_usd, answer.cost_verified),
                         ("Widening the wings.", "tool_use", Decimal("0.086800"), True))
        self.assertEqual(answer.usage["output_tokens"], 2400)
        # The same message answered as JSON reads the same.
        payload = {"id": "msg_t", "type": "message", "role": "assistant", "model": MODEL, "content": FINAL, "stop_reason": "tool_use",
                   "usage": {**USAGE, "output_tokens": 2400}}
        plain = turn(client(FakeOpener(FakeResponse(payload, headers={"X-LTCM-Cost-USD": "0.086800"}))), stream=False)
        self.assertEqual(plain.content, answer.content)
        self.assertEqual([(u.id, u.name, u.input, u.error) for u in plain.tool_uses], [(u.id, u.name, u.input, u.error) for u in answer.tool_uses])

    def test_the_request_the_gateway_receives(self):
        opener = FakeOpener(FakeStream(tool_events()))
        turn(client(opener, read_timeout=120.0, timeout=600.0), timeout=180.0)
        self.assertEqual(opener.calls[0][1], 120.0, "the socket timeout is the gap allowed between events")
        headers = opener.headers()
        self.assertEqual((headers["x-ltcm-role"], headers["x-ltcm-agent"], headers["x-ltcm-request"]),
                         ("researcher", "swarm-researcher", "swarm:condor:c5:m0:ab12"))
        self.assertEqual(opener.body(), tool_request_body(MODEL, SYSTEM, TURNS, TOOLS, max_tokens=16000, effort="medium"))

    def test_the_calls_overall_limit_is_its_own(self):
        now = [0.0]
        with self.assertRaises(ClaudeError) as slow:
            turn(client(FakeOpener(FakeStream(tool_events(), clock=now, tick=5.0)), timeout=600.0, clock=lambda: now[0]), timeout=60.0)
        self.assertIn("60-second limit", str(slow.exception))
        self.assertIsNone(slow.exception.cost_usd)

    def test_an_input_that_is_not_json_is_an_error_on_its_call_never_a_guess(self):
        for bad in (['{"code": "x', '", "why": }'], ['[1, 2]'], ['{"stress": NaN}'], ['{"a": 1}{']):
            with self.subTest(bad=bad):
                answer = turn(client(FakeOpener(FakeStream(tool_events(fragments={2: bad})))))
                first = answer.tool_uses[0]
                self.assertEqual((first.input, first.raw), ({}, "".join(bad)))
                self.assertTrue(first.error)
                self.assertIsNone(answer.tool_uses[1].error, "the other call of the same answer is intact")
                self.assertEqual(answer.content[2]["input"], {})

    def test_a_call_with_no_fragments_has_an_empty_input(self):
        answer = turn(client(FakeOpener(FakeStream(tool_events(fragments={2: [], 4: [""]})))))
        self.assertEqual([(u.input, u.error) for u in answer.tool_uses], [({}, None), ({}, None)])

    def test_a_cut_or_refused_turn_raises_with_its_bill_and_content(self):
        cut_input = pieces(FINAL[2]["input"])[:3]
        with self.assertRaises(ClaudeTruncated) as cut:
            turn(client(FakeOpener(FakeStream(tool_events(FINAL[:3], stop="max_tokens", fragments={2: cut_input})))))
        self.assertEqual(cut.exception.cost_usd, Decimal("0.086800"))
        self.assertEqual(cut.exception.answer.stop_reason, "max_tokens")
        self.assertTrue(cut.exception.answer.tool_uses[0].error, "the cut input is kept as it came, marked, never run")
        with self.assertRaises(ClaudeTruncated):
            turn(client(FakeOpener(FakeStream(tool_events(stop="model_context_window_exceeded")))))
        with self.assertRaises(ClaudeRefusal) as refused:
            turn(client(FakeOpener(FakeStream(tool_events(FINAL[:3], stop="refusal", fragments={2: cut_input}, cost="0.012000")))))
        self.assertEqual(refused.exception.cost_usd, Decimal("0.012000"))
        self.assertEqual(refused.exception.answer.content[0]["signature"], SIG)
        with self.assertRaises(ClaudeError) as paused:
            turn(client(FakeOpener(FakeStream(tool_events(stop="pause_turn")))))
        self.assertNotIsInstance(paused.exception, (ClaudeRefusal, ClaudeTruncated))
        # A stream cut before its end, and the gateway's refusals, keep their typed errors.
        with self.assertRaises(ClaudeError) as early:
            turn(client(FakeOpener(FakeStream(tool_events(cut=True, cost="0.408000", known=False)))))
        self.assertIn("ended before the answer", str(early.exception))
        with self.assertRaises(ClaudeError) as capped:
            turn(client(FakeOpener(http_error(402, '{"error": "funded", "cap": "claude_funded"}'))))
        self.assertEqual((capped.exception.status, capped.exception.cap), (402, "claude_funded"))

    def test_an_end_turn_answer_with_no_call_is_an_answer(self):
        answer = turn(client(FakeOpener(FakeStream(tool_events(FINAL[:2], stop="end_turn")))))
        self.assertEqual((answer.text, answer.tool_uses, answer.stop_reason), ("Widening the wings.", (), "end_turn"))


if __name__ == "__main__":
    unittest.main()
