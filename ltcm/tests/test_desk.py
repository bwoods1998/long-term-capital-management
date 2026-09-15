import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.desk import (
    HEADER,
    Desk,
    MemoryStore,
    PlaybookError,
    PlaybookStore,
    SessionResult,
)
from ltcm.events import EventLog
from ltcm.manifest import DeskManifest
from ltcm.provider import BudgetExceeded, FunctionCall, ProviderError, ProviderResponse
from ltcm.tests.test_manifest import SAMPLE
from ltcm.tests.test_tools import FakeContext

PLAYBOOK = "# Earnings desk playbook\n\nRead the filing before the tape.\n"


def manifest(**overrides):
    data = {
        **SAMPLE,
        "tools": ["quote", "news", "memory_write", "memo", "propose_order", "playbook_write", "positions"],
    }
    data.update(overrides)
    return DeskManifest.from_dict(data)


def provider_response(
    *, calls=(), text="", summaries=(), status="completed", cost="0.01", request_id="req-1"
):
    items = [{"type": "reasoning", "summary": [{"text": s}]} for s in summaries]
    if text:
        items.append({"type": "message", "content": [{"type": "output_text", "text": text}]})
    function_calls = []
    for index, (name, arguments, error) in enumerate(calls):
        call_id = f"call_{index}"
        function_calls.append(FunctionCall(call_id, name, arguments, error))
        items.append(
            {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(arguments),
            }
        )
    return ProviderResponse(
        request_id=request_id,
        response_id="resp_" + request_id,
        status=status,
        output_text=text,
        function_calls=function_calls,
        reasoning_summaries=list(summaries),
        output_items=items,
        usage={"input_tokens": 10, "output_tokens": 5},
        cost_usd=Decimal(cost),
        incomplete=status == "incomplete",
        incomplete_reason="max_output_tokens" if status == "incomplete" else None,
    )


def tool_call(name, **arguments):
    return (name, arguments, None)


class FakeProvider:
    """Replays scripted responses and records exactly how the desk asked for them."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": list(items), **kwargs})
        if not self.script:
            raise AssertionError("the desk asked for more turns than were scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class DeskCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "playbooks").mkdir()
        (self.root / "playbooks" / "earnings-01.md").write_text(PLAYBOOK, encoding="utf-8")
        self.time = [1_789_000_000.0]  # 2026-09-10T00:26:40Z
        self.log = EventLog(self.root / "events.sqlite", clock=lambda: self.time[0])
        self.ctx = FakeContext()

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def desk(self, provider, mf=None):
        return Desk(
            mf or manifest(),
            provider,
            self.ctx,
            self.log,
            clock=lambda: self.time[0],
            repo_root=self.root,
        )

    def events(self, stream=None):
        return self.log.read(stream=stream) if stream else self.log.read()


class SessionIdentityTests(DeskCase):
    def test_session_id_is_derived_from_the_utc_minute(self):
        desk = self.desk(FakeProvider())
        self.assertEqual(desk.session_id("market_open"), "earnings-01:20260910-0026:market_open")
        self.time[0] += 15  # still the same minute, so a crash-retry reuses the id
        self.assertEqual(desk.session_id("market_open"), "earnings-01:20260910-0026:market_open")
        self.time[0] += 60
        self.assertEqual(desk.session_id("market_open"), "earnings-01:20260910-0027:market_open")
        for bad in ("", "Market Open", "market open", "1open", None, "x" * 60, "a/b"):
            with self.assertRaises(ValueError):
                desk.session_id(bad)
        # The service names cadence slots this way; the id has to accept them.
        self.assertEqual(
            desk.session_id("cadence:09:45"), "earnings-01:20260910-0027:cadence:09:45"
        )


class PromptTests(DeskCase):
    def test_the_prompt_puts_the_stable_context_first(self):
        desk = self.desk(FakeProvider())
        items = desk.build_prompt("earnings-01:20260910-0026:market_open", "market_open")
        self.assertEqual([i["role"] for i in items], ["system", "user"])
        system, user = items[0]["content"], items[1]["content"]
        self.assertTrue(system.startswith(HEADER))
        self.assertIn("enforced in code", system)
        self.assertIn("public", system)
        self.assertIn(SAMPLE["mandate"], system)
        self.assertIn(SAMPLE["persona"], system)
        self.assertIn("position 25% of desk equity", system)
        self.assertIn("Read the filing before the tape.", system)
        self.assertIn("end_session", system)
        # Volatile state stays out of the cached prefix.
        self.assertNotIn("NVDA beat", system)
        self.assertIn("NVDA beat", user)
        self.assertIn("AAPL", user)
        self.assertIn("Cash 500", user)
        self.assertIn("MSFT", user)
        self.assertIn("market_open", user)

    def test_context_answers_wrapped_in_an_object_still_render(self):
        class Wrapped(FakeContext):
            def memory_read(self, query, limit):
                return {"entries": super().memory_read(query, limit)}

            def positions(self):
                return {"positions": [p.to_dict() for p in super().positions()], "as_of": "now"}

            def outcomes(self, limit):
                return {"fills": super().outcomes(limit)}

            def balance(self):
                return {"balance": super().balance().to_dict()}

        desk = self.desk(FakeProvider())
        desk.ctx = Wrapped()
        user = desk.build_prompt("s", "market_open")[1]["content"]
        self.assertIn("NVDA beat", user)
        self.assertIn("AAPL", user)
        self.assertIn("Cash 500", user)
        self.assertIn("MSFT", user)

    def test_the_memory_limit_is_honoured_and_failures_degrade(self):
        desk = self.desk(FakeProvider())
        desk.build_prompt("s", "market_open")
        self.assertIn(("memory_read", ("", 40)), self.ctx.seen)
        desk.ctx = FakeContext(fail={"memory_read", "positions", "balance", "outcomes"})
        items = desk.build_prompt("s", "market_open")
        self.assertIn("no memory yet", items[1]["content"])
        self.assertIn("no open positions", items[1]["content"])


class LoopTests(DeskCase):
    def test_tool_calls_then_end_session(self):
        provider = FakeProvider(
            provider_response(
                summaries=["Checking the reaction against the surprise."],
                calls=[
                    tool_call("quote", instrument={"asset_class": "equity", "symbol": "AAPL"}),
                    tool_call("memory_write", text="AAPL beat on revenue", kind="fact", symbol="AAPL"),
                ],
                request_id="req-1",
            ),
            provider_response(
                text="Nothing to trade today.",
                calls=[tool_call("end_session", summary="No setup; waiting for the 10-Q.")],
                request_id="req-2",
                cost="0.02",
            ),
        )
        desk = self.desk(provider)
        result = desk.run_session("market_open")

        self.assertIsInstance(result, SessionResult)
        self.assertEqual(result.session_id, "earnings-01:20260910-0026:market_open")
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.requests, 2)
        self.assertEqual(result.cost_usd, Decimal("0.03"))
        self.assertEqual(result.reason, "end_session")
        self.assertEqual(result.intents, [])

        kinds = [event.kind for event in self.events(stream="desk:earnings-01")]
        self.assertEqual(
            kinds,
            [
                "desk.session_started",
                "desk.thought",
                "desk.tool_call",
                "desk.tool_result",
                "desk.tool_call",
                "desk.tool_result",
                "desk.thought",
                "desk.tool_call",
                "desk.tool_result",
                "desk.session_ended",
            ],
        )
        self.assertTrue(all(event.public for event in self.events()))
        started = self.events()[0]
        self.assertEqual(started.payload, {"session_id": result.session_id, "trigger": "market_open"})
        ended = self.events()[-1]
        self.assertEqual(ended.payload["requests"], 2)
        self.assertEqual(ended.payload["cost_usd"], "0.03")
        self.assertEqual(ended.payload["reason"], "end_session")
        quote_call = self.events()[2]
        self.assertEqual(quote_call.payload["tool"], "quote")
        self.assertEqual(quote_call.payload["call_id"], "call_0")
        self.assertEqual(quote_call.payload["arguments"]["instrument"]["symbol"], "AAPL")
        self.assertIn("bid 100.10", self.events()[3].payload["summary"])
        self.assertEqual(self.log.verify(), len(self.events()))

    def test_the_conversation_grows_with_output_items_and_tool_results(self):
        provider = FakeProvider(
            provider_response(calls=[tool_call("positions")], request_id="req-1"),
            provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-2"),
        )
        desk = self.desk(provider)
        desk.run_session("market_close")
        first, second = provider.calls[0], provider.calls[1]
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(second["items"][2]["type"], "function_call")
        self.assertEqual(second["items"][3]["type"], "function_call_output")
        self.assertEqual(second["items"][3]["call_id"], "call_0")
        self.assertIn("AAPL", second["items"][3]["output"])
        self.assertEqual(first["request_key"], "earnings-01:20260910-0026:market_close:0")
        self.assertEqual(second["request_key"], "earnings-01:20260910-0026:market_close:1")
        self.assertEqual(first["cache_key"], "earnings-01")
        self.assertEqual(first["desk_id"], "earnings-01")
        self.assertEqual(first["session_id"], "earnings-01:20260910-0026:market_close")
        self.assertEqual(first["desk_cap_usd_per_day"], Decimal("3"))
        self.assertEqual(first["max_output_tokens"], 8192)
        self.assertEqual(first["reasoning_effort"], "medium")
        self.assertEqual(provider.calls[0]["profile"], "pro_flex")
        self.assertEqual([t["name"] for t in first["tools"]][-1], "end_session")

    def test_a_session_stops_when_the_model_stops_calling_tools(self):
        # One tool-less reply earns a reminder and a second try; a second one ends the session.
        provider = FakeProvider(
            provider_response(text="I have nothing to add."),
            provider_response(text="Still nothing."),
        )
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "no_tool_calls")
        self.assertEqual(result.turns, 2)
        nudge = provider.calls[1]["items"][-1]
        self.assertEqual(nudge["role"], "user")
        self.assertIn("without calling a tool", nudge["content"])
        self.assertEqual(
            [e.kind for e in self.events()],
            ["desk.session_started", "desk.thought", "desk.thought", "desk.session_ended"],
        )

    def test_an_incomplete_response_ends_the_session_after_publishing_what_came_back(self):
        provider = FakeProvider(
            provider_response(
                status="incomplete",
                text="partial",
                calls=[tool_call("quote", instrument={"asset_class": "equity", "symbol": "AAPL"})],
            )
        )
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "incomplete:max_output_tokens")
        self.assertEqual([e.kind for e in self.events()][1], "desk.thought")
        self.assertNotIn("desk.tool_call", [e.kind for e in self.events()])

    def test_a_failed_response_ends_the_session(self):
        provider = FakeProvider(provider_response(status="failed"))
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "provider_failed")

    def test_the_turn_limit_is_the_manifest_limit(self):
        mf = manifest(model={**SAMPLE["model"], "max_turns": 2})
        provider = FakeProvider(
            provider_response(calls=[tool_call("positions")], request_id="req-1"),
            provider_response(calls=[tool_call("positions")], request_id="req-2"),
        )
        result = self.desk(provider, mf).run_session("market_open")
        self.assertEqual(result.reason, "max_turns")
        self.assertEqual(result.turns, 2)
        self.assertEqual(result.requests, 2)

    def test_the_budget_stops_the_session_and_raises_an_ops_alert(self):
        provider = FakeProvider(
            provider_response(calls=[tool_call("positions")], request_id="req-1"),
            BudgetExceeded("provider_desk_cap_exceeded"),
        )
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "provider_desk_cap_exceeded")
        self.assertEqual(result.turns, 1)
        alerts = self.log.read(stream="ops", kind="ops.alert")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].payload["level"], "warn")
        self.assertIn("provider_desk_cap_exceeded", alerts[0].payload["text"])
        self.assertEqual(self.events(stream="desk:earnings-01")[-1].kind, "desk.session_ended")

    def test_a_provider_failure_ends_the_session_with_an_alert(self):
        provider = FakeProvider(ProviderError("provider_http_500"))
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "provider_http_500")
        self.assertEqual(result.requests, 0)
        self.assertEqual(self.log.read(stream="ops")[0].payload["level"], "error")

    def test_a_malformed_tool_call_is_reported_and_the_session_continues(self):
        provider = FakeProvider(
            provider_response(calls=[("quote", {}, "arguments were not valid JSON: JSONDecodeError")]),
            provider_response(calls=[tool_call("end_session", summary="recovered")], request_id="req-2"),
        )
        result = self.desk(provider).run_session("market_open")
        self.assertEqual(result.reason, "end_session")
        summary = [e for e in self.events() if e.kind == "desk.tool_result"][0].payload["summary"]
        self.assertIn("not valid JSON", summary)
        output = provider.calls[1]["items"][-1]["output"]
        self.assertIn("error", json.loads(output))

    def test_proposed_intents_come_back_on_the_result(self):
        provider = FakeProvider(
            provider_response(
                calls=[
                    tool_call(
                        "propose_order",
                        instrument={"asset_class": "equity", "symbol": "AAPL"},
                        side="buy",
                        quantity="2",
                        order_type="market",
                        rationale="Documented revenue beat; ten day hold, exit on the next print.",
                    )
                ]
            ),
            provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-2"),
        )
        result = self.desk(provider).run_session("earnings_release")
        self.assertEqual(len(result.intents), 1)
        self.assertTrue(result.intents[0]["approved"])
        self.assertEqual(result.intents[0]["intent_id"], self.ctx.intents[0].id)
        self.assertEqual(self.ctx.intents[0].session_id, result.session_id)

    def test_replaying_a_session_reuses_event_ids(self):
        def script():
            return (
                provider_response(calls=[tool_call("positions")], request_id="req-1"),
                provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-2"),
            )

        first = self.desk(FakeProvider(*script())).run_session("market_open")
        before = [event.id for event in self.events()]
        second = self.desk(FakeProvider(*script())).run_session("market_open")
        self.assertEqual(first.session_id, second.session_id)
        self.assertEqual([event.id for event in self.events()], before)


class PlaybookTests(DeskCase):
    def test_a_write_versions_the_file_and_publishes_a_diff(self):
        new_text = "# Earnings desk playbook\n\nRead the transcript before the tape.\n"
        provider = FakeProvider(
            provider_response(
                calls=[tool_call("playbook_write", text=new_text, reason="Transcripts beat releases.")]
            ),
            provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-2"),
        )
        desk = self.desk(provider)
        desk.run_session("market_close")

        self.assertEqual((self.root / "playbooks" / "earnings-01.md").read_text(), new_text)
        history = self.root / "playbooks" / "history" / "earnings-01"
        self.assertEqual(sorted(p.name for p in history.iterdir()), ["v1.md", "v2.md"])
        self.assertEqual((history / "v1.md").read_text(), PLAYBOOK)
        self.assertEqual((history / "v2.md").read_text(), new_text)

        updates = [e for e in self.events() if e.kind == "desk.playbook_updated"]
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].payload["version"], 2)
        self.assertEqual(updates[0].payload["reason"], "Transcripts beat releases.")
        diff = updates[0].payload["diff"]
        self.assertIn("-Read the filing before the tape.", diff)
        self.assertIn("+Read the transcript before the tape.", diff)
        self.assertTrue(updates[0].public)
        # The full text is not echoed into the tool_call event; the diff carries the change.
        call_event = [e for e in self.events() if e.kind == "desk.tool_call"][0]
        self.assertEqual(set(call_event.payload["arguments"]), {"reason", "chars"})

    def test_refused_edits_never_touch_the_file(self):
        store = PlaybookStore(self.root, manifest())
        for text, reason in (
            ("", "empty"),
            ("   \n ", "blank"),
            ("x" * 20_001, "too long"),
            ("valid text", ""),
            (None, "not a string"),
            (PLAYBOOK, "identical"),
        ):
            with self.assertRaises(PlaybookError):
                store.write(text, reason)
        self.assertEqual((self.root / "playbooks" / "earnings-01.md").read_text(), PLAYBOOK)
        self.assertEqual(store.versions(), [])

    def test_a_refused_edit_reaches_the_model_as_an_error(self):
        provider = FakeProvider(
            provider_response(calls=[tool_call("playbook_write", text="x" * 20_001, reason="big")]),
            provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-2"),
        )
        desk = self.desk(provider)
        desk.run_session("market_close")
        self.assertEqual([e for e in self.events() if e.kind == "desk.playbook_updated"], [])
        outputs = [i for i in provider.calls[1]["items"] if isinstance(i, dict) and "output" in i]
        output = json.loads(outputs[-1]["output"])
        self.assertIn("20000", output["error"])

    def test_versions_keep_climbing(self):
        store = PlaybookStore(self.root, manifest())
        store.write("one", "first")
        second = store.write("two", "second")
        self.assertEqual(second["version"], 3)
        self.assertEqual(store.versions(), [1, 2, 3])
        self.assertEqual(store.current_version(), 3)
        self.assertEqual(store.version_text(2), "one\n")
        self.assertEqual(store.read(), "two\n")

    def test_a_playbook_outside_the_playbooks_directory_is_refused(self):
        with self.assertRaises(Exception):
            PlaybookStore(self.root, manifest(playbook="playbooks/../../etc/passwd.md"))


class MemoryTests(DeskCase):
    def store(self):
        return MemoryStore(self.root / "memory.sqlite", clock=lambda: self.time[0])

    def entry(self, text, **extra):
        return {"desk_id": "earnings-01", "text": text, "kind": "fact", **extra}

    def test_keyword_hits_outrank_recency(self):
        store = self.store()
        store.write(self.entry("NVDA guided datacenter revenue higher", symbol="NVDA"))
        self.time[0] += 3600
        store.write(self.entry("AAPL margins slipped", symbol="AAPL"))
        self.time[0] += 3600
        store.write(self.entry("Market was quiet", symbol=None))
        newest_first = [e["text"] for e in store.read("", 10)]
        self.assertEqual(newest_first[0], "Market was quiet")
        ranked = store.read("NVDA datacenter", 10)
        self.assertEqual(ranked[0]["text"], "NVDA guided datacenter revenue higher")
        self.assertEqual(len(ranked), 3)  # non-matching entries stay, ranked below
        self.assertEqual(store.read("AAPL", 1)[0]["symbol"], "AAPL")
        store.close()

    def test_more_matching_terms_rank_higher(self):
        store = self.store()
        store.write(self.entry("AAPL beat on revenue and raised guidance", symbol="AAPL"))
        self.time[0] += 3600
        store.write(self.entry("AAPL is a company", symbol="AAPL"))
        ranked = store.read("AAPL revenue guidance", 5)
        self.assertEqual(ranked[0]["text"], "AAPL beat on revenue and raised guidance")
        store.close()

    def test_tags_and_kind_are_searchable_and_round_trip(self):
        store = self.store()
        written = store.write(self.entry("Something happened", tags=["earnings", "drift"], kind="lesson"))
        self.assertEqual(written["tags"], ["earnings", "drift"])
        self.assertEqual(written["kind"], "lesson")
        self.assertEqual(store.read("drift", 5)[0]["id"], written["id"])
        self.assertEqual(store.read("lesson", 5)[0]["id"], written["id"])
        store.close()

    def test_writes_are_idempotent_under_replay(self):
        store = self.store()
        entry = self.entry("Same note", session_id="earnings-01:20260910-0026:market_open")
        first = store.write(entry)
        self.time[0] += 900  # a replay happens later, but derives the same id
        again = store.write(entry)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(first["at"], again["at"])
        self.assertEqual(store.count("earnings-01"), 1)
        store.close()

    def test_entries_are_scoped_per_desk_and_validated(self):
        store = self.store()
        store.write(self.entry("mine"))
        store.write({"desk_id": "filings-01", "text": "theirs", "kind": "fact"})
        self.assertEqual(len(store.read("", 10, desk_id="earnings-01")), 1)
        self.assertEqual(len(store.read("", 10)), 2)
        for bad in ({}, {"desk_id": "d"}, {"desk_id": "d", "text": "  "}, {"text": "x"},
                    {"desk_id": "d", "text": "x" * 4001}, {"desk_id": "d", "text": "x", "tags": "no"}):
            with self.assertRaises(ValueError):
                store.write(bad)
        store.close()



class LessonsTests(unittest.TestCase):
    """The lessons a post-mortem states reach the log however the model laid them out."""

    def test_inline_enumerations_are_split_into_lessons(self):
        from ltcm.desk import _lessons_from

        prose = (
            "Post-mortem (no orders this session): Worst decision \u2014 on KXFEDDECISION-26SEP I set a "
            "92\u201393% estimate. Rules changed: added three to the playbook \u2014 (1) consolidate "
            "no-setup notes to one per symbol per session, (2) sub-8c event-contract edges are "
            "record-only no-trades, (3) shrink extreme tail estimates at least halfway toward the "
            "market before acting. Waiting on the FOMC resolution to re-check rule 2."
        )
        lessons = _lessons_from(prose)
        self.assertEqual(len(lessons), 3)
        self.assertTrue(lessons[0].startswith("consolidate no-setup notes"))
        self.assertTrue(lessons[1].startswith("sub-8c event-contract edges"))
        self.assertTrue(lessons[2].startswith("shrink extreme tail estimates"))
        self.assertNotIn("Waiting on the FOMC", lessons[2])

    def test_a_semicolon_list_ends_before_the_calibration_sentence(self):
        from ltcm.desk import _lessons_from

        prose = (
            "Rules changed: appended three \u2014 (1) scheduled catalysts override intraday "
            "mean-reversion extremes, (2) pre-commit mechanical post-release triggers before the "
            "catalyst, (3) pair every probability forecast with the live market price. Calibration "
            "unscoreable until FOMC resolves 2026-09-16; I was ~3-4c above the market on H25 (0.92 vs 0.89)."
        )
        lessons = _lessons_from(prose)
        self.assertEqual(len(lessons), 3)
        self.assertTrue(lessons[2].startswith("pair every probability forecast"))
        self.assertNotIn("Calibration", lessons[2])

    def test_a_single_rule_sentence_counts_when_nothing_is_enumerated(self):
        from ltcm.desk import _lessons_from

        prose = (
            "Rule changed: added playbook rule 6 (pre-catalyst sessions must close with a written "
            "mechanical plan, or an explicit stay-flat line; prose is not a plan), with one matching "
            "lesson memory entry. Rules 1-5 were already in place and none failed."
        )
        lessons = _lessons_from(prose)
        self.assertEqual(len(lessons), 1)
        self.assertTrue(lessons[0].startswith("added playbook rule 6"))

    def test_bullets_and_numbered_lines_still_read_as_before(self):
        from ltcm.desk import _lessons_from

        self.assertEqual(_lessons_from("- one\n* two\n3. three\nprose"), ["one", "two", "three"])
        self.assertEqual(_lessons_from("Nothing learned today, the book was flat."), [])

class GuardrailCopyTests(unittest.TestCase):
    """The words that keep the recursive loop honest are pinned, because tonight's desks copied
    an abandoned threshold from each other's memory and called it a lesson."""

    def test_the_header_forbids_tightening_the_mandate(self):
        self.assertIn("Your playbook may not tighten your mandate", HEADER)
        self.assertIn("a post-mortem may not write one", HEADER)

    def test_the_postmortem_asks_for_evidence_from_the_desks_own_record(self):
        import inspect
        from ltcm import desk as desk_module

        source = inspect.getsource(desk_module)
        self.assertIn("write no new rules, and end the session", source)
        self.assertIn("never from another desk's memory", source)


if __name__ == "__main__":
    unittest.main()
