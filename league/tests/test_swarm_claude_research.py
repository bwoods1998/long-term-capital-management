"""THE TOP BAND ON CLAUDE (Sept 29, 2026, the owner's decision: be bold with Claude Sonnet 5.5): the bandit's top
`researcher.claude_top` families run their research cycles on Claude through the gateway, the loop, tools and limits
unchanged, and ANY Claude failure finishes the turn on the family's Sail profile (league/swarm/researcher.py,
league/swarm/claude_research.py, `ModelRouter.claude_turn`).

The real Researcher, the real ModelRouter over the real Provider with a scripted Sail (league/tests/swarm_fakes.py), a
fake Gym pool, a fake gateway meter, and a fake Claude whose `messages` checks each body with the real
`tool_request_body` (the gateway's rules) and answers from a script; one case runs the real Claude client over the
gateway's event stream."""

from __future__ import annotations

import copy
import itertools
import json
import unittest
from decimal import Decimal
from unittest import mock

from league.claude import Answer, Claude, ClaudeError, ClaudeRefusal, ClaudeTruncated, ToolUse, tool_request_body
from league.swarm import claude_research as CR
from league.swarm import pool as pool_module
from league.swarm.models import ModelError, ModelRouter
from league.swarm.researcher import TOOLS, Researcher, sanitize
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.tests import swarm_fakes
from league.tests.test_claude import FakeStream
from league.tests.test_claude_tools import tool_events
from league.tests.test_frontier import GATEWAY, FakeOpener
from league.tests.test_swarm_claude_routing import FakeClaudeMeter
from league.tests.test_swarm_researcher import ResearcherCase

SONNET = "claude-sonnet-5-5"
USAGE = {"input_tokens": 900, "cache_creation_input_tokens": 23000, "cache_read_input_tokens": 14500, "output_tokens": 2400}
SIG = "EqQBCgIYAhIM1gbcDa9GJwZA2b3hGgxBdjrkzLoky3dl1pkiMOYds"
_N = iter(range(1, 10 ** 6))


def thinking(text: str = "") -> dict:
    return {"type": "thinking", "thinking": text, "signature": SIG + str(next(_N))}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def call(name: str, args: dict, *, id: str | None = None) -> dict:
    return {"type": "tool_use", "id": id or f"toolu_{next(_N):05d}", "name": name, "input": args}


def answer(*blocks: dict, stop: str = "tool_use", cost: str | None = "0.050000", bad: dict | None = None) -> Answer:
    """An answer as `league.claude.Claude.messages` returns it; `bad` {call id: raw} marks inputs that did not parse."""
    bad = bad or {}
    uses = tuple(ToolUse(b["id"], b["name"], {} if b["id"] in bad else b["input"], raw=bad.get(b["id"], json.dumps(b["input"])),
                         error="the tool input is not valid JSON" if b["id"] in bad else None)
                 for b in blocks if b["type"] == "tool_use")
    return Answer(text="".join(b["text"] for b in blocks if b["type"] == "text"), data=None, usage=dict(USAGE),
                  cost_usd=None if cost is None else Decimal(cost), model=SONNET, stop_reason=stop, cost_verified=cost is not None,
                  id="msg", raw={}, content=tuple(copy.deepcopy(list(blocks))), tool_uses=uses)


def last_results(body: dict) -> list[dict]:
    return [b for b in body["messages"][-1]["content"] if b["type"] == "tool_result"]


def strip_marks(value):
    if isinstance(value, dict):
        return {k: strip_marks(v) for k, v in value.items() if k != "cache_control"}
    if isinstance(value, list):
        return [strip_marks(v) for v in value]
    return value


def marks(body: dict) -> list[str]:
    """Where a request's cache markers are."""
    out = [f"tools[{i}]" for i, t in enumerate(body["tools"]) if "cache_control" in t]
    out += [f"system[{i}]" for i, b in enumerate(body.get("system") or []) if "cache_control" in b]
    for t, turn in enumerate(body["messages"]):
        if isinstance(turn["content"], list):
            out += [f"messages[{t}][{i}]" for i, b in enumerate(turn["content"]) if "cache_control" in b]
    return out


class FakeClaude:
    """Claude through the gateway, for the router: each body is checked by the real `tool_request_body`, kept, and answered
    from `script` (an Answer, an exception, or a callable of the body returning either)."""

    def __init__(self, model: str, script: list, requests: list):
        self.model, self.script, self.requests = model, script, requests

    def messages(self, system, messages, tools, *, agent, role=None, max_tokens=16000, effort="medium", tool_choice="auto",
                 request_id=None, stream=True, timeout=None):
        body = tool_request_body(self.model, system, messages, tools, tool_choice=tool_choice, max_tokens=max_tokens, effort=effort,
                                 stream=stream)
        self.requests.append({"body": copy.deepcopy(body), "agent": agent, "role": role, "request_id": request_id, "timeout": timeout})
        step = self.script.pop(0) if self.script else answer(text("done"), stop="end_turn")
        if callable(step):
            step = step(body)
        if isinstance(step, BaseException):
            raise step
        return step

    def settlement(self, request_id):
        return None


class ClaudeCase(ResearcherCase):
    """A family in the top band, Claude configured for the researcher, one starter cycle run."""

    def setUp(self):
        super().setUp()
        self.claude_script: list = []
        self.requests: list = []
        self.meter = FakeClaudeMeter(100)
        self.router = self.claude_router()
        self.store.update_family(self.fam["id"], weight=1.0)
        self.researcher().cycle(self.fam["id"])  # the starter: no model call
        self.fid = self.fam["id"]

    def claude_router(self):
        return ModelRouter(self.store, self.provider, settings=self.settings, claude_meter=self.meter,
                           claude_factory=lambda model: FakeClaude(model, self.claude_script, self.requests))

    def researcher(self):
        return Researcher(self.store, self.router, self.pool, self.settings, clock=self.clock, background=False, starter=program_for)

    def cycle(self, fid=None):
        return self.researcher().cycle(fid or self.fid)

    def bodies(self):
        return [r["body"] for r in self.requests]

    def researcher_spend(self, family=None):
        return round(self.router.claude_spent(role="researcher", family=family), 6)

    def revise_call(self, params=None):
        return call("gym_run", {"code": self.code, "params": params or {"vrp_min": 1.4}, "why": "fewer, richer entries"})


# --------------------------------------------------------------------------------------------------------- the adapter
class Adapter(unittest.TestCase):
    NAMES = [t["name"] for t in TOOLS]

    def test_the_tools_keep_their_names_descriptions_and_schemas_with_one_marker_last(self):
        tools = CR.anthropic_tools(TOOLS)
        self.assertEqual([t["name"] for t in tools], self.NAMES)
        for mine, theirs in zip(TOOLS, tools):
            self.assertEqual((theirs["description"], theirs["input_schema"], theirs["eager_input_streaming"]),
                             (mine["description"], mine["parameters"], True))
        self.assertEqual([i for i, t in enumerate(tools) if "cache_control" in t], [len(tools) - 1])
        self.assertEqual(json.dumps(tools), json.dumps(CR.anthropic_tools(TOOLS)), "the same bytes every time")

    def test_a_sail_history_becomes_valid_anthropic_turns(self):
        items = [
            {"role": "user", "content": "YOUR FAMILY"},
            {"role": "user", "content": "Cycle 1: the starter ran."},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "\n\n"}]},
            {"type": "function_call", "call_id": "call_1", "name": "gym_run", "arguments": '{"code": "X"}'},
            {"type": "function_call_output", "call_id": "call_1", "output": '{"status": "ok"}'},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Reading it."}]},
            {"type": "function_call", "call_id": "call_2", "name": "notebook", "arguments": '{"action": "read"}'},
            {"type": "function_call", "call_id": "call.3/x", "name": "submit", "arguments": "{not json"},
            {"type": "function_call_output", "call_id": "call_2", "output": "[]"},
            {"type": "function_call_output", "call_id": "call.3/x", "output": '{"error": "bad"}'},
            {"type": "function_call_output", "call_id": "call_orphan", "output": "late"},
            {"type": "reasoning", "summary": []},
            {"role": "user", "content": "Cycle 2. Now: revise."},
        ]
        turns = CR.anthropic_messages(items, self.NAMES)
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user", "assistant", "user"])
        self.assertEqual(turns[0]["content"], [text("YOUR FAMILY"), text("Cycle 1: the starter ran.")])
        self.assertEqual(turns[1]["content"], [call("gym_run", {"code": "X"}, id="call_1")], "the empty message is dropped")
        self.assertEqual(turns[2]["content"], [{"type": "tool_result", "tool_use_id": "call_1", "content": '{"status": "ok"}'}])
        self.assertEqual(turns[3]["content"], [text("Reading it."), call("notebook", {"action": "read"}, id="call_2"),
                                               call("submit", {"INVALID_JSON": "{not json"}, id="call_3_x")])
        results, rest = turns[4]["content"][:2], turns[4]["content"][2:]
        self.assertEqual([r["tool_use_id"] for r in results], ["call_2", "call_3_x"], "parallel results first, in one turn")
        self.assertEqual(rest, [text("Result of a tool: late"), text("Cycle 2. Now: revise.")], "an orphan result is text")
        body = tool_request_body(SONNET, "s", turns, CR.anthropic_tools(TOOLS))  # the gateway's rules hold
        self.assertEqual(len(body["messages"]), 5)

    def test_a_call_with_no_result_is_answered_and_ids_stay_one_to_one(self):
        turns = CR.anthropic_messages([{"role": "user", "content": "go"},
                                       {"type": "function_call", "call_id": "a b", "name": "gym_run", "arguments": "{}"},
                                       {"type": "function_call", "call_id": "a_b", "name": "gym_run", "arguments": "{}"}], self.NAMES)
        ids = [b["id"] for b in turns[1]["content"]]
        self.assertEqual(len(set(ids)), 2, ids)
        self.assertEqual([(r["tool_use_id"], r["is_error"]) for r in turns[2]["content"]], [(ids[0], True), (ids[1], True)])

    def test_a_claude_answer_is_stored_as_sail_items_and_reads_back_as_the_same_pairs_without_thinking(self):
        first, second = call("notebook", {"action": "append", "text": "Wider."}), call("submit", {"run_id": "run-1"})
        content = [thinking("Plan."), thinking(""), text("Two calls."), first, second]
        calls = CR.tool_calls(answer(*content).tool_uses, {t["name"]: t["parameters"] for t in TOOLS})
        items = CR.sail_items(content, calls)
        self.assertEqual([i["type"] for i in items], ["message", "function_call", "function_call"], "no thinking is stored")
        self.assertEqual([(i["call_id"], json.loads(i["arguments"])) for i in items[1:]],
                         [(first["id"], first["input"]), (second["id"], second["input"])])
        history = [{"role": "user", "content": "brief"}, *items,
                   {"type": "function_call_output", "call_id": first["id"], "output": "{}"},
                   {"type": "function_call_output", "call_id": second["id"], "output": '{"ok": true}'},
                   {"role": "user", "content": "next cycle"}]
        turns = CR.anthropic_messages(sanitize(history), self.NAMES)
        self.assertEqual(turns[1]["content"], [text("Two calls."), first, second])
        self.assertEqual([r["tool_use_id"] for r in turns[2]["content"][:2]], [first["id"], second["id"]])
        self.assertNotIn("thinking", json.dumps(turns))

    def test_an_input_that_did_not_parse_is_stored_as_invalid_json(self):
        bad = call("gym_run", {})
        calls = CR.tool_calls(answer(bad, bad={bad["id"]: '{"code": "x'}).tool_uses, {t["name"]: t["parameters"] for t in TOOLS})
        self.assertTrue(calls[0].error.startswith("INVALID_JSON"))
        [item] = CR.sail_items([bad], calls)
        self.assertEqual(json.loads(item["arguments"]), {"INVALID_JSON": '{"code": "x'})


class Inputs(unittest.TestCase):
    SCHEMAS = {t["name"]: t["parameters"] for t in TOOLS}

    def check(self, name, args):
        [out] = CR.tool_calls([ToolUse("toolu_1", name, args, raw=json.dumps(args))], self.SCHEMAS)
        return out

    def test_each_input_is_checked_against_its_tools_schema_before_it_runs(self):
        cases = {
            "a string page": ("read_run", {"run_id": "r", "section": "summary", "page": "2"}, "page must be an integer"),
            "a boolean stress": ("gym_run", {"stress": True}, "stress must be a number"),
            "a missing required key": ("read_run", {"run_id": "r"}, "missing section"),
            "an unknown top-level key": ("gym_run", {"program": "X"}, "no key program"),
            "an enum miss": ("notebook", {"action": "delete"}, "one of append, read"),
            "a variant that is not an object": ("gym_sweep", {"variants": [{}, 3]}, "variants[1] must be an object"),
            "a hold that is not a boolean": ("gym_run", {"hold": "yes"}, "hold must be true or false"),
            "an unknown tool": ("pause_entries", {}, "unknown tool"),
        }
        for why, (name, args, message) in cases.items():
            with self.subTest(why):
                out = self.check(name, args)
                self.assertIn(message, out.error)
                self.assertEqual(out.arguments, {})

    def test_what_is_unambiguous_is_accepted(self):
        out = self.check("Notebook", {"action": "append", "text": "x"})
        self.assertEqual((out.name, out.error), ("notebook", None), "a miscased name that names one tool")
        out = self.check("gym_run", {"hold": True, "note": "nothing new", "code": None, "params": None})
        self.assertEqual((out.arguments, out.error), ({"hold": True, "note": "nothing new"}, None), "optional nulls are dropped")
        out = self.check("read_run", {"run_id": "r", "section": "trades", "page": 2.0})
        self.assertIsNone(out.error)
        self.assertIsNone(self.check("gym_sweep", {"variants": [{}, {"vrp_min": 1.5}], "params": {"any": [1]}}).error,
                          "PARAMS overrides stay free-form, as their schemas say")


# ------------------------------------------------------------------------------------------------------ the cycle itself
class Cycles(ClaudeCase):
    def test_a_cycle_on_claude_revise_run_read_note_submit(self):
        run_call = self.revise_call()
        note = call("notebook", {"action": "append", "text": "Richer entries cut the trade count."})

        def read(body):
            run_id = json.loads(last_results(body)[0]["content"])["run_id"]
            return answer(thinking("It is the best."), note, call("submit", {"run_id": run_id, "note": "best"}))

        self.claude_script[:] = [answer(thinking("Widen."), text("Revising."), run_call), read,
                                 answer(text("Next I will widen the wings."), stop="end_turn")]
        out = self.cycle()
        self.assertNotIn("error", out)
        self.assertEqual((out["route"], out["model_calls"], out["tool_calls"], out["claude_calls"]), ("claude", 3, 3, 3))
        self.assertEqual(out["profile"], SONNET)
        self.assertEqual(self.sail.bodies, [], "Sail was never asked")
        fam = self.store.family(self.fid)
        self.assertEqual((fam["revisions"], fam["best_version"], fam["trials"]), (2, 2, 2))
        self.assertEqual(self.store.version(self.fid, 2)["author"], SONNET, "the version is authored by the model that wrote it")
        self.assertEqual(self.store.notebook(self.fid)[-1]["text"], "Richer entries cut the trade count.")
        self.assertEqual(out["claude_usage"], {"input": 2700, "cache_write": 69000, "cache_read": 43500, "output": 7200})
        self.assertAlmostEqual(out["claude_usd"], 0.15)
        self.assertAlmostEqual(self.researcher_spend(self.fid), 0.15, msg="three answers settled at their cost, holds replaced")
        self.assertEqual(self.store.get("claude_unsettled"), {})
        first = self.requests[0]
        self.assertEqual((first["role"], first["agent"], first["body"]["model"], first["body"]["output_config"]),
                         ("researcher", "swarm-researcher", SONNET, {"effort": "medium"}))
        self.assertEqual(first["body"]["tool_choice"], {"type": "auto"}, "forced tool choice is refused by Sonnet 5.5")
        self.assertIn("This turn is a REVISE", first["body"]["messages"][-1]["content"][-1]["text"])
        self.assertEqual(first["timeout"], 180.0)
        # The cycle event carries the route and the first day's measurement.
        event = [e for e in self.store.events_after(0) if e["kind"] == "swarm.cycle"][-1]["payload"]
        self.assertEqual((event["route"], event["claude_calls"]), ("claude", 3))
        # The stored history is Sail's shape: the next cycle on Sail reads it like any other.
        [*_, stored] = self.store.convo(self.fid)[0]
        kinds = [i.get("type") or i.get("role") for i in stored["items"]]
        self.assertEqual(kinds.count("function_call"), 3)
        self.assertNotIn("thinking", json.dumps(stored))

    def test_the_session_is_append_only_and_passes_every_answer_back_exactly(self):
        run_call = self.revise_call()
        answers = [answer(thinking("Widen."), text("Revising."), run_call),
                   answer(thinking(""), call("notebook", {"action": "append", "text": "Noted."})),
                   answer(text("Done for this cycle."), stop="end_turn")]
        self.claude_script[:] = list(answers)
        self.cycle()
        bodies = self.bodies()
        self.assertEqual(len(bodies), 3)
        for before, after, given in zip(bodies, bodies[1:], answers):
            head = strip_marks(after["messages"][:len(before["messages"])])
            self.assertEqual(head, strip_marks(before["messages"]), "every earlier turn unchanged")
            self.assertEqual(after["messages"][len(before["messages"])], {"role": "assistant", "content": list(given.content)},
                             "the answer passed back exactly, thinking and signature included")
            self.assertEqual(json.dumps(after["system"]), json.dumps(before["system"]))
            self.assertEqual(json.dumps(after["tools"]), json.dumps(before["tools"]))
            self.assertEqual(after["messages"][-1]["content"][0]["type"], "tool_result", "the tool results come first")

    def test_prompt_caching_three_markers_the_tail_moves_and_the_prefix_is_shared(self):
        self.claude_script[:] = [answer(self.revise_call()), answer(text("Read it."), stop="end_turn")]
        self.cycle()
        first, second = self.bodies()
        last = len(first["tools"]) - 1
        self.assertEqual(marks(first), [f"tools[{last}]", "system[0]", f"messages[0][{len(first['messages'][0]['content']) - 1}]"])
        self.assertEqual(marks(second), [f"tools[{last}]", "system[0]", f"messages[2][{len(second['messages'][2]['content']) - 1}]"],
                         "the tail marker moved; none on a thinking block")
        self.assertEqual([t["name"] for t in first["tools"]], [t["name"] for t in TOOLS], "every tool, on every turn")
        # A second family and a second cycle: the same tools and system bytes (one cached prefix for the whole band).
        other = self.store.add_family(family_spec(next(s for s in SEEDS if s["id"] == "putspread-dip")), origin="seed")
        self.store.update_family(other["id"], weight=0.9)
        self.assertTrue(self.cycle(other["id"]).get("starter"))
        self.claude_script[:] = [answer(text("Holding."), call("gym_run", {"hold": True, "note": "nothing new"}))]
        self.cycle(other["id"])
        self.claude_script[:] = [answer(call("gym_run", {"hold": True, "note": "nothing new either"}))]
        self.cycle()
        third, fourth = self.bodies()[2:]
        for body in (third, fourth):
            self.assertEqual(json.dumps(body["system"]), json.dumps(first["system"]))
            self.assertEqual(json.dumps(body["tools"]), json.dumps(first["tools"]))
        self.assertIn(f"YOUR FAMILY: {other['id']}", json.dumps(third["messages"][0]))
        self.assertNotIn("thinking", json.dumps(fourth["messages"]), "no thinking crosses cycles")

    def test_a_call_to_a_tool_not_offered_on_the_turn_is_refused_and_never_run(self):
        self.claude_script[:] = [answer(call("notebook", {"action": "append", "text": "sneaky"}), self.revise_call()),
                                 answer(text("ok"), stop="end_turn")]
        out = self.cycle()
        self.assertNotIn("error", out)
        self.assertEqual(out["claude_refused_calls"], 1)
        self.assertEqual(self.store.notebook(self.fid), [], "the notebook is not offered on a REVISE turn")
        refusal = last_results(self.bodies()[1])[0]
        self.assertIn("notebook is not offered on this turn", refusal["content"])
        self.assertEqual(out["tool_calls"], 1, "the run ran; the refused call cost no tool call")

    def test_the_real_client_over_the_gateways_stream(self):
        """The real Claude client end to end: the body it sends is the router's, and the streamed call runs."""
        run_input = {"code": self.code, "params": {"vrp_min": 1.45}, "why": "streamed"}
        blocks = [thinking("Widen the wings."), {"type": "tool_use", "id": "toolu_01S", "name": "gym_run", "input": run_input}]
        opener = FakeOpener(FakeStream(tool_events(blocks, cost="0.061000")),
                            FakeStream(tool_events([text("Read it.")], stop="end_turn", cost="0.020000")))
        self.router = ModelRouter(self.store, self.provider, settings=self.settings, claude_meter=self.meter,
                                  claude_factory=lambda model: Claude(GATEWAY, lambda: "synthetic", model=model, opener=opener))
        out = self.cycle()
        self.assertNotIn("error", out)
        self.assertEqual((out["claude_calls"], out["tool_calls"], out["claude_usd"]), (2, 1, 0.081))
        self.assertEqual(self.store.versions(self.fid)[-1]["params"], {"vrp_min": 1.45})
        sent = json.loads(opener.calls[1][0].data)
        self.assertEqual(sent["messages"][-2]["content"][0]["signature"], blocks[0]["signature"], "the signature went back")
        self.assertEqual({k.lower(): v for k, v in opener.calls[0][0].header_items()}["x-ltcm-role"], "researcher")


class Fallbacks(ClaudeCase):
    """Every Claude failure finishes the turn on the family's Sail profile: never a cycle error."""

    def sail_revises(self):
        self.steps = [{"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.3}, "why": "sail"})]}]

    def check_fallback(self, kind, *, billed=0.0, held=False):
        out = self.cycle()
        self.assertNotIn("error", out, kind)
        self.assertTrue(out["claude_fallback"].startswith(kind + ":"), out.get("claude_fallback"))
        first = self.sail.bodies[0]
        self.assertEqual((first["tool_choice"], [t["name"] for t in first["tools"]]), ("required", ["gym_run", "gym_sweep"]),
                         "the REVISE turn is retried on Sail, where a call is required")
        self.assertTrue(first["input"][-1]["content"].startswith("Cycle 2."), "the same transcript: the status is last")
        self.assertEqual(out["model_calls"], 2, "the failed attempt is no model call")
        self.assertEqual([v["params"] for v in self.store.versions(self.fid)][-1], {"vrp_min": 1.3}, "Sail's run ran")
        self.assertNotIn({"vrp_min": 9.9}, [v["params"] for v in self.store.versions(self.fid)], "nothing of Claude's turn ran")
        if held:
            self.assertGreater(self.researcher_spend(), 0.1, "an unknown bill keeps its hold until the true-up")
            self.assertEqual(len(self.store.get("claude_unsettled")), 1)
        else:
            self.assertAlmostEqual(self.researcher_spend(), billed)
            self.assertEqual(self.store.get("claude_unsettled") or {}, {})
        self.assertAlmostEqual(out.get("claude_usd", 0.0), round(self.researcher_spend(), 6))
        return out

    def refused_turn(self, exc_type, stop, cost="0.012000"):
        return exc_type(f"stopped: {stop}", answer=answer(thinking(""), self.revise_call({"vrp_min": 9.9}), stop=stop, cost=cost))

    def gateway(self, status, cap=None):
        return ClaudeError(f"Claude call refused: HTTP {status}", status=status, cap=cap)

    def test_each_failure_kind_falls_back_to_sail(self):
        cases = {
            "refusal": (lambda: self.refused_turn(ClaudeRefusal, "refusal"), dict(billed=0.012)),
            "truncated": (lambda: self.refused_turn(ClaudeTruncated, "max_tokens", "0.160000"), dict(billed=0.16)),
            "http 402 funded": (lambda: self.gateway(402, "claude_funded"), {}),
            "http 403 unpriced": (lambda: self.gateway(403), {}),
            "http 423 kill switch": (lambda: self.gateway(423, "kill_switch"), {}),
            "http 429": (lambda: self.gateway(429), {}),
            "stream": (lambda: ClaudeError("the Claude stream ran past its 180-second limit"), dict(held=True)),
            "unknown": (lambda: RuntimeError("the client broke"), dict(held=True)),
        }
        for name, (failure, expect) in cases.items():
            with self.subTest(name):
                self.setUp()
                self.claude_script[:] = [failure()]
                self.sail_revises()
                self.check_fallback(name.split()[0], **expect)
                self.assertEqual(len(self.requests), 1)
                self.doCleanups()

    def test_no_call_on_a_revise_turn_is_retried_on_sail_and_its_text_is_discarded(self):
        self.claude_script[:] = [answer(text("I think I should widen the wings."), stop="end_turn", cost="0.030000")]
        self.sail_revises()
        self.check_fallback("no_call", billed=0.03)
        stored = json.dumps(self.store.convo(self.fid)[0][-1])
        self.assertNotIn("I think I should widen", stored)

    def test_the_lines_no_room_and_the_reserve_fall_back_without_a_call_or_a_hold(self):
        yesterday = self.clock.t - (self.clock.t % 86400) - 60
        cases = {
            "line": lambda: self.store.add_spend("claude", 100.0, family="elsewhere", detail={"role": "researcher"}),
            "family_fuse": lambda: self.store.add_spend("claude", 15.0, family=self.fid, detail={"role": "researcher"}),
            "no_room": lambda: setattr(self.meter, "value", 30),  # $25 above the reserve: all of it kept for the other roles
        }
        for kind, arrange in cases.items():
            with self.subTest(kind):
                self.setUp()
                self.settings["claude"]["usd_cap"] = 1000.0  # only the line under test binds
                arrange()
                before = self.store.spent(["claude"])
                self.sail_revises()
                out = self.cycle()
                self.assertTrue(out["claude_fallback"].startswith(kind + ":"), out["claude_fallback"])
                self.assertEqual(self.requests, [], "Claude was never asked")
                self.assertEqual(self.store.spent(["claude"]), before, "no hold was booked")
                self.assertNotIn("error", out)
                self.doCleanups()
        # Yesterday's spend does not count against today's lines; another family's does not count against this one's fuse.
        self.setUp()
        now = self.clock.t
        self.clock.t = yesterday
        self.store.add_spend("claude", 100.0, family=self.fid, detail={"role": "researcher"})
        self.clock.t = now
        self.store.add_spend("claude", 14.0, family="elsewhere", detail={"role": "researcher"})
        self.meter.value = 60
        self.settings["claude"]["usd_cap"] = 1000.0  # the swarm's own lifetime Claude line (the owner raises it with a top-up)
        self.claude_script[:] = [answer(call("gym_run", {"hold": True, "note": "nothing new"}))]
        out = self.cycle()
        self.assertNotIn("claude_fallback", out)
        self.assertEqual(out["claude_calls"], 1)

    def test_an_invalid_input_is_answered_as_an_error_never_run_and_the_valid_call_beside_it_runs(self):
        bad = call("read_run", {"run_id": "r", "section": "summary", "page": "2"})
        unparsed = call("graveyard", {})
        self.claude_script[:] = [answer(self.revise_call()),
                                 answer(call("notebook", {"action": "append", "text": "Kept."}), bad, unparsed,
                                        bad={unparsed["id"]: '{"query": "vol'})]
        out = self.cycle()
        self.assertNotIn("error", out)
        self.assertTrue(out["claude_fallback"].startswith("invalid: invalid input for read_run: page must be an integer"))
        self.assertEqual(self.store.notebook(self.fid)[-1]["text"], "Kept.", "the valid call ran")
        self.assertEqual(out["tool_calls"], 2, "the run and the note; the invalid calls cost no tool call")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(len(self.sail.bodies), 1, "the next turn is Sail's")
        outputs = {i["call_id"]: json.loads(i["output"]) for i in self.sail.bodies[0]["input"] if i.get("type") == "function_call_output"}
        self.assertIn("page must be an integer", outputs[bad["id"]]["error"])
        self.assertTrue(outputs[unparsed["id"]]["error"].startswith("INVALID_JSON"))
        self.assertEqual(self.sail.bodies[0]["tool_choice"], "auto")

    def test_an_exception_in_the_adapter_falls_back(self):
        self.sail_revises()
        with mock.patch.object(CR.ClaudeSession, "request", side_effect=ValueError("the conversation holds 61 turns")):
            out = self.cycle()
        self.assertTrue(out["claude_fallback"].startswith("unknown: ValueError"))
        self.assertNotIn("error", out)
        self.assertEqual(self.requests, [])

    def test_a_failure_later_in_the_cycle_keeps_the_rest_on_sail(self):
        self.claude_script[:] = [answer(self.revise_call()), self.gateway(529)]
        self.steps = [{"text": "Read it on Sail."}]
        out = self.cycle()
        self.assertNotIn("error", out)
        self.assertEqual((out["claude_calls"], out["model_calls"], len(self.sail.bodies)), (1, 2, 1))
        self.assertEqual(self.sail.bodies[0]["tool_choice"], "auto")
        self.assertEqual(out["profile"], "pro_asap", "the family's own Sail profile (the top band's)")


class Selection(ClaudeCase):
    def test_only_the_top_claude_top_by_weight_and_only_while_the_role_is_configured(self):
        others = [self.store.add_family(family_spec(s), origin="seed") for s in SEEDS[1:3]]
        self.store.update_family(others[0]["id"], weight=0.5)
        self.store.update_family(others[1]["id"], weight=0.1)
        self.settings["researcher"]["claude_top"] = 2
        r = self.researcher()
        route = lambda fid: r.claude_route(self.store.family(fid))  # noqa: E731
        self.assertEqual([route(f) for f in (self.fid, others[0]["id"], others[1]["id"])], [True, True, False])
        self.settings["researcher"]["claude_top"] = 0
        self.assertFalse(route(self.fid))
        self.settings["researcher"]["claude_top"] = 12
        self.settings["claude"]["roles"] = ["architect", "audit", "diagnostician"]
        self.assertFalse(route(self.fid), "no \"researcher\" in claude.roles: every family on Sail")
        self.settings["claude"]["roles"].append("researcher")
        unconfigured = Researcher(self.store, ModelRouter(self.store, self.provider, settings=self.settings), self.pool, self.settings,
                                  clock=self.clock, background=False)
        self.assertFalse(unconfigured.claude_route(self.store.family(self.fid)), "no client or meter: Sail")

    def test_a_family_outside_the_band_sends_sail_exactly_todays_bodies(self):
        script = [{"calls": [("gym_run", {"code": self.code, "params": {"vrp_min": 1.3}})]}, {"text": "done"}]

        def run(configured: bool) -> list:
            self.doCleanups()
            swarm_fakes._N = itertools.count(1)  # the fakes' run and call ids and the Gym's job ids start alike
            pool_module._IDS = itertools.count(1)
            self.setUp()
            if not configured:
                self.router = ModelRouter(self.store, self.provider, settings=self.settings)
            self.settings["researcher"]["claude_top"] = 1
            other = self.store.add_family(family_spec(next(s for s in SEEDS if s["id"] == "ironfly-quiet")), origin="seed")
            self.store.update_family(other["id"], weight=0.2)
            self.assertTrue(self.cycle(other["id"]).get("starter"))
            self.steps = copy.deepcopy(script)
            out = self.cycle(other["id"])
            self.assertNotIn("route", out)
            self.assertEqual(self.requests, [], "Claude was never asked for a family outside the band")
            return copy.deepcopy(self.sail.bodies)

        with_claude, without = run(True), run(False)
        self.assertEqual(len(with_claude), 2)
        self.assertEqual(json.dumps(with_claude), json.dumps(without), "byte-identical Sail requests")


class Router(ClaudeCase):
    def turn(self, **kw):
        args = dict(role="researcher", family=self.fid, key=f"swarm:{self.fid}:c2:m0:1", model=SONNET, system="s",
                    tools=CR.anthropic_tools(TOOLS), messages=[{"role": "user", "content": "go"}], family_usd_day=15.0, keep_usd=25.0)
        args.update(kw)
        return self.router.claude_turn(**args)

    def test_a_turn_is_held_then_settled_and_its_request_id_names_the_call(self):
        self.claude_script[:] = [answer(call("gym_run", {"hold": True}), cost="0.042000")]
        reply = self.turn()
        self.assertEqual((reply.model, reply.cost_usd, reply.held_usd), (SONNET, 0.042, 0.0))
        self.assertTrue(self.requests[0]["request_id"].startswith(f"swarm:{self.fid}:c2:m0:1:"))
        rows = self.store._all("SELECT usd, detail FROM spend WHERE kind='claude' ORDER BY seq")
        self.assertEqual(len(rows), 2, "the hold, then its settlement")
        hold = json.loads(rows[0]["detail"])
        self.assertEqual((hold["role"], hold["model"], hold["effort"], hold["max_tokens"]), ("researcher", SONNET, "medium", 16000))
        self.assertAlmostEqual(self.researcher_spend(), 0.042)

    def test_each_failure_is_a_model_error_naming_its_kind(self):
        for failure, kind in ((ClaudeRefusal("no", answer=answer(stop="refusal", cost="0.01")), "refusal"),
                              (ClaudeTruncated("cut", answer=answer(stop="max_tokens", cost="0.2")), "truncated"),
                              (ClaudeError("HTTP 402", status=402, cap="claude_funded"), "http"),
                              (ClaudeError("the stream broke"), "stream"),
                              (ClaudeError("stopped for pause_turn", answer=answer(stop="pause_turn")), "answer")):
            self.claude_script[:] = [failure]
            with self.subTest(kind), self.assertRaises(ModelError) as caught:
                self.turn()
            self.assertEqual(caught.exception.kind, kind)
        with self.assertRaises(ModelError) as bad:
            self.turn(tool_choice={"type": "any"})
        self.assertEqual(bad.exception.kind, "admission")
        self.settings["claude"]["roles"].remove("researcher")
        with self.assertRaises(ModelError) as off:
            self.turn()
        self.assertEqual(off.exception.kind, "off")

    def test_the_researcher_asks_on_its_role_model_and_an_unpriced_one_is_never_sent(self):
        self.assertEqual(self.router.claude_model("researcher"), SONNET, "claude.role_model.researcher")
        self.claude_script[:] = [answer(call("gym_run", {"hold": True}))]
        self.turn(model=None)
        self.assertEqual(self.requests[-1]["body"]["model"], SONNET)
        self.settings["claude"]["role_model"] = {"researcher": "claude-unpriced-9"}
        with self.assertRaises(ModelError) as unpriced:
            self.turn(model=None)
        self.assertEqual(unpriced.exception.kind, "admission")
        self.assertIn("no verified price", str(unpriced.exception))
        self.assertEqual(len(self.requests), 1, "never sent")

    def test_a_typo_in_a_line_never_lifts_it(self):
        for value in ("lots", -1, float("nan"), True):
            with self.subTest(family_usd_day=value), self.assertRaises(ModelError) as caught:
                self.turn(family_usd_day=value)
            self.assertEqual(caught.exception.kind, "family_fuse")
        with self.assertRaises(ModelError) as kept:
            self.turn(keep_usd="lots")
        self.assertEqual(kept.exception.kind, "no_room", "a reserve that does not read keeps everything")
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
