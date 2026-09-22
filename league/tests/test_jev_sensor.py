"""Jev as the cheap sensor: gate triggers, backoff, sampling, outage fallback, caps, cache,
triage dedupe, hypothesis links and inactivity transitions."""
import json
import random
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.exposure import Exposure, keys_of
from league.hypothesis_memory import HypothesisMemory, mechanism_id
from league.jev import MODEL, Sensor
from league.ledger import Ledger, now_iso
from league.pacer import Pacer
from league.research_gate import report, session_outcome
from league.sensors import JevFloor
from league.tests.fakes import Clock
from league.tests.test_house import HouseCase
from league.triage import Triage


class FakeJev:
    """A gateway stand-in: answers every noul question with `p` (or p(text)), or raises."""

    def __init__(self, p=0.9, *, fail=False, cost="0.0001"):
        self.p, self.fail, self.cost, self.calls = p, fail, cost, []

    def __call__(self, ident, body):
        request = json.loads(body)
        self.calls.append((ident, request))
        if self.fail:
            raise TimeoutError("gateway timed out")
        items = request["state"]["items"]
        answers = {name: {"type": "noul", "noul": self.p(items[name]) if callable(self.p) else self.p}
                   for name in request["questions"]}
        return {"model": MODEL, "answers": answers, "usage": {"input_tokens": 100}}, Decimal(self.cost)


class SensorTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def sensor(self, client, **kw):
        return Sensor(Path(self.dir.name) / "jev.sqlite", client, clock=self.clock, **kw)

    def test_cache_means_one_question_is_bought_once(self):
        jev = FakeJev(0.8)
        sensor = self.sensor(jev)
        items = {"a": ("text a", "q?"), "b": ("text b", "q?")}
        self.assertEqual(sensor.ask("gate", {}, items), {"a": 0.8, "b": 0.8})
        self.assertEqual(sensor.ask("gate", {}, items), {"a": 0.8, "b": 0.8})
        self.assertEqual(len(jev.calls), 1)
        self.assertEqual(sensor.stats()["today"]["gate"]["cache_hits"], 2)

    def test_batches_at_most_sixteen_questions_per_request(self):
        jev = FakeJev(0.1)
        sensor = self.sensor(jev)
        answers = sensor.ask("triage", {"shared": "x"}, {f"k{n}": (f"t{n}", "q?") for n in range(40)})
        self.assertEqual(len(answers), 40)
        self.assertEqual([len(r["questions"]) for _, r in jev.calls], [16, 16, 8])
        self.assertTrue(all(r["model"] == MODEL for _, r in jev.calls))

    def test_daily_dollar_and_call_caps_are_checked_before_calling(self):
        jev = FakeJev(0.5, cost="0.001")
        sensor = self.sensor(jev, daily_usd="0.0045")
        sensor.ask("gate", {}, {f"k{n}": ("t", "q?") for n in range(16 * 5)})
        # 0.001 spent per call; a new call needs room for the unconfirmed worst case ($0.003).
        self.assertEqual(len(jev.calls), 2)
        self.assertIn("daily Jev cap", sensor.refusal("gate"))
        capped = Sensor(Path(self.dir.name) / "calls.sqlite", FakeJev(0.5), clock=self.clock, daily_calls=10,
                        purpose_calls={"links": 1})
        capped.ask("links", {}, {f"k{n}": ("t", "q?") for n in range(40)})
        self.assertEqual(capped.calls_today("links"), 1)
        self.clock.advance(86400)
        self.assertEqual(capped.refusal("links"), "", "caps are per UTC day")

    def test_outage_returns_none_opens_the_breaker_and_counts_worst_case(self):
        jev = FakeJev(fail=True)
        sensor = self.sensor(jev, cooldown_seconds=600)
        answers = sensor.ask("gate", {}, {f"k{n}": ("t", "q?") for n in range(40)})
        self.assertEqual(set(answers.values()), {None})
        self.assertEqual(len(jev.calls), 1, "no retry storm: the rest of the batch is not attempted")
        self.assertEqual(sensor.spent_today(), Decimal("0.003"))
        sensor.ask("gate", {}, {"k0": ("t", "q?")})
        self.assertEqual(len(jev.calls), 1, "the breaker is open")
        self.clock.advance(601)
        jev.fail = False
        self.assertEqual(sensor.ask("gate", {}, {"k0": ("t", "q?")}), {"k0": 0.9})
        # A re-bought body uses a new request identity: the gateway refuses a repeated one.
        self.assertNotEqual(jev.calls[0][0], jev.calls[-1][0])
        # So does the same body from a fresh store (a lost or restored jev.sqlite).
        other = Sensor(Path(self.dir.name) / "fresh.sqlite", jev, clock=self.clock)
        other.ask("gate", {}, {"k0": ("t", "q?")})
        self.assertNotIn(jev.calls[-1][0], [ident for ident, _ in jev.calls[:-1]])
        self.assertEqual(Sensor(Path(self.dir.name) / "fresh.sqlite", jev, clock=self.clock).salt, other.salt, "stable per store")


def summary(ledger, agent, *, candidate=False, trials=0, reason="finished", text="No credits are worth spending now."):
    return ledger.append("agent.research", {"tool": "summary", "session": f"s-{ledger.head()[0]}", "candidate": candidate,
                                            "trials": trials, "reason": reason, "summary": text, "cost_usd": "0.016"}, agent=agent)


class GateCase(HouseCase):
    def ready(self, *, p=0.1, fail=False, rng=None, settings=None):
        self.house.settings.research = True
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={
            "start": now_iso(self.clock)[:10], "days": 10, "sail_usd": "50", "openai_usd": "50"})
        self.house.pacer.may_spend = lambda kind: True
        self.house.behind_the_clock = lambda kind: False  # a fixed interval; the halving has its own tests
        self.house.researcher = SimpleNamespace(research=lambda *a, **k: SimpleNamespace(candidate=None))
        self.jev = FakeJev(p, fail=fail)
        self.sensor = Sensor(self.house.root / "jev.sqlite", self.jev, clock=self.clock)
        self.rng = rng or SimpleNamespace(random=lambda: 0.99)
        self.house.jev_floor = JevFloor(self.house, self.sensor, {"research_gate": dict(settings or {})}, rng=self.rng)
        agent = self.seated()
        self.house._state["last_research"][agent.id] = self.clock()
        self.interval = self.house.research_interval_hours(agent) * 3600
        return agent

    def gates(self, agent=None):
        return [e.payload for e in self.house.ledger.read(kinds="research.gate", agent=agent, limit=10000)]

    def researched(self, agent):
        """What House.research does at the end of a pass, plus the pass's summary row."""
        self.house._state["last_research"][agent.id] = self.clock()


class ResearchGateTest(GateCase):
    def test_first_decision_runs_on_the_clock_then_abstention_backs_off(self):
        agent = self.ready()
        self.assertFalse(self.house.research_due(agent), "the clock still decides first")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["reason"], "clock")
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "one empty pass is below v0's `after`: the clock decides")
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "two empty passes: wait twice the interval")
        self.assertEqual(self.gates()[-1]["decision"], "skip")
        self.assertEqual(self.gates()[-1]["reason"], "backoff:2")
        rows = len(self.gates())
        for _ in range(30):
            self.clock.advance(60)
            self.assertFalse(self.house.research_due(agent))
        self.assertEqual(len(self.gates()), rows, "re-checks inside a skipped slot write nothing")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["reason"], "backoff_elapsed")

    def test_backoff_is_exponential_and_capped(self):
        agent = self.ready(settings={"max_factor": 4, "max_skip_hours": 1000})
        for _ in range(5):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        waited = 0
        while not self.house.research_due(agent):
            self.clock.advance(600)
            waited += 600
            self.assertLess(waited, 10 * self.interval)
        self.assertGreaterEqual(waited, 4 * self.interval - 600)
        self.assertLess(waited, 4 * self.interval + 600, "five abstentions wait the cap, not 32 intervals")

    def test_deterministic_triggers_run_despite_backoff(self):
        agent = self.ready()
        ledger = self.house.ledger
        cases = [
            ("book.fill", lambda: ledger.append("book.fill", {"book": "alpaca-paper", "price": "1"}, agent=agent.id)),
            ("book.settle", lambda: ledger.append("book.settle", {"book": "alpaca-paper"}, agent=agent.id)),
            ("book.refused", lambda: ledger.append("book.refused", {"book": "kalshi", "reasons": ["x"]}, agent=agent.id)),
            ("eval.verdict:promote", lambda: ledger.append("eval.verdict", {"decision": "promote", "to_rung": 1}, agent=agent.id)),
            ("credit.grant", lambda: ledger.append("credit.grant", {"reason": "epoch payout", "usd": "1"}, agent=agent.id)),
            ("library.note:niche", lambda: ledger.append("library.note", {"title": "t", "text": "x" * 50, "niche": agent.niche}, agent="peer")),
        ]
        for name, write in cases:
            with self.subTest(trigger=name):
                summary(ledger, agent.id)
                summary(ledger, agent.id)
                self.researched(agent)
                self.clock.advance(self.interval)
                self.assertFalse(self.house.research_due(agent))
                write()
                self.clock.advance(60)
                self.assertTrue(self.house.research_due(agent))
                self.assertEqual(self.gates()[-1]["reason"], "trigger")
                self.assertTrue(any(t.startswith(name) for t in self.gates()[-1]["triggers"]), self.gates()[-1])

    def test_routine_verdicts_and_own_notes_are_not_triggers(self):
        agent = self.ready()
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.house.ledger.append("eval.verdict", {"decision": "look"}, agent=agent.id)
        self.house.ledger.append("library.note", {"title": "t", "text": "x" * 50, "niche": agent.niche}, agent=agent.id)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))

    def test_code_rung_and_fulfilled_request_are_triggers(self):
        agent = self.ready()
        request = self.house.commons.request_tool(agent.id, "funding_feed", "perpetual funding rates for BTC and ETH, please")
        for name, change in [("rung", lambda: self.house.evaluator.seat(agent.id, 2, "test")),
                             ("tool.fulfilled", lambda: self.house.commons.fulfil(request["queued"], "built: ctx.funding"))]:
            with self.subTest(trigger=name):
                summary(self.house.ledger, agent.id)
                summary(self.house.ledger, agent.id)
                self.researched(agent)
                self.clock.advance(self.interval)
                self.assertFalse(self.house.research_due(agent))
                change()
                self.assertTrue(self.house.research_due(agent))
                self.assertTrue(any(t.startswith(name) for t in self.gates()[-1]["triggers"]), self.gates()[-1])

    def test_refusal_fast_path_is_never_gated(self):
        agent = self.ready()
        for _ in range(4):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(61)
        self.house.ledger.append("book.refused", {"book": "alpaca-paper", "reasons": ["oversized"]}, agent=agent.id)
        self.assertTrue(self.house.research_due(agent), "a new refusal on its own book is answered within a minute, as before")

    def test_a_productive_last_session_is_never_skipped(self):
        agent = self.ready()
        summary(self.house.ledger, agent.id, candidate=True, trials=1)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))

    def test_known_blocker_waits_for_change_not_backoff(self):
        agent = self.ready(settings={"max_skip_hours": 1000})
        self.house.commons.request_tool(agent.id, "funding_feed", "perpetual funding rates for BTC and ETH, please")
        summary(self.house.ledger, agent.id, text="The perpetual funding/OI feed remains not_supplied; spend nothing.")
        self.researched(agent)
        self.house.jev_floor.tick(True)
        self.assertEqual(self.house.jev_floor.inactivity.current(agent.id), "missing_data")
        for _ in range(12):
            self.clock.advance(self.interval)
            self.assertFalse(self.house.research_due(agent))
        self.assertTrue(all(g["reason"] == "blocked:missing_data" for g in self.gates() if g["decision"] == "skip"))
        reasons = [g for g in self.gates() if g["decision"] == "skip"]
        self.assertLess(len(reasons), 4, "repeated identical skips are aggregated")
        self.assertEqual(sum(g["sessions"] for g in reasons) + self.house.jev_floor.state.agent(agent.id)["episode"]["pending"], 12)
        # The blocker lifting is itself the trigger.
        request = self.house.commons._requests()[0]["id"]
        self.house.commons.fulfil(request, "built: ctx.funding")
        self.assertTrue(self.house.research_due(agent))

    def test_heartbeat_prevents_freezing(self):
        agent = self.ready(settings={"max_skip_hours": 12, "max_factor": 64})
        for _ in range(6):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        waited = 0
        while not self.house.research_due(agent):
            self.clock.advance(600)
            waited += 600
        self.assertLessEqual(waited, 12 * 3600 + 600)
        self.assertEqual(self.gates()[-1]["reason"], "heartbeat")

    def test_sampling_runs_about_ten_percent_of_skips(self):
        agent = self.ready(rng=random.Random(7), settings={"max_skip_hours": 10 ** 6, "max_factor": 10 ** 6})
        for _ in range(20):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        gate = self.house.jev_floor.gate
        decisions = []
        for _ in range(1000):
            state = self.house.jev_floor.state.agent(agent.id)
            state["recheck_at"] = 0
            decisions.append(gate.allow(agent, last=self.house._state["last_research"][agent.id]))
        rate = sum(decisions) / len(decisions)
        self.assertGreater(rate, 0.07)
        self.assertLess(rate, 0.13)
        samples = [g for g in self.gates() if g["decision"] == "sample"]
        self.assertEqual(len(samples), sum(decisions))
        self.assertTrue(all(g["sampled"] for g in samples))

    def test_report_measures_skips_savings_and_sampled_misses(self):
        agent = self.ready(rng=SimpleNamespace(random=lambda: 0.05))
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["decision"], "sample")
        summary(self.house.ledger, agent.id, candidate=True, trials=1)  # the sampled session found something: a miss
        self.researched(agent)
        self.house.jev_floor.gate.rng = SimpleNamespace(random=lambda: 0.99)
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        out = report(self.house.ledger)
        self.assertEqual(out["sampled"], 1)
        self.assertEqual(out["sampled_misses"], 1)
        self.assertEqual(out["sampled_miss_rate"], 1.0)
        self.assertEqual(out["skipped_sessions"], 1)
        self.assertEqual(Decimal(out["estimated_savings_usd"]), Decimal("0.016"))

    def test_jev_relevance_runs_on_uncertain_and_falls_back_when_down(self):
        agent = self.ready(p=0.5)
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.house.ledger.append("library.note", {"title": "Spread lesson", "text": "x" * 80, "niche": "alpaca-crypto-alts"}, agent="peer")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "uncertain relevance favors a run")
        self.assertEqual(self.gates()[-1]["reason"], "jev_relevant_note")
        self.assertEqual(len(self.jev.calls), 1)
        # A different agent with the same strategy asks the same (note, strategy sha): cached.
        # Now the outage: a new note, Jev down, the deterministic decision (skip) stands.
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.house.ledger.append("library.note", {"title": "Other", "text": "y" * 80, "niche": "alpaca-crypto-alts"}, agent="peer")
        self.jev.fail = True
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.assertTrue(self.gates()[-1]["reason"].endswith("jev_unavailable"), self.gates()[-1])
        calls = len(self.jev.calls)
        for _ in range(120):
            self.clock.advance(60)
            self.house.research_due(agent)
        self.assertEqual(len(self.jev.calls), calls, "ticks inside a skipped slot and an open breaker buy nothing")

    def test_rows_keep_the_v0_shape(self):
        agent = self.ready()
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        row = self.gates()[-1]
        self.assertLessEqual({"agent", "decision", "reason", "empty_streak", "sampled", "triggers", "cost_usd"}, set(row))
        self.assertEqual(row["empty_streak"], 2)

    def test_a_strategy_merton_wrote_is_not_an_empty_pass(self):
        agent = self.ready()
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        session = "research:consulted"
        self.house.ledger.append("agent.research", {"tool": "merton", "session": session, "wrote_code": True}, agent=agent.id)
        self.house.ledger.append("agent.research", {"tool": "summary", "session": session, "candidate": False, "trials": 0,
                                                     "reason": "finished", "summary": "kept his file for later"}, agent=agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["empty_streak"], 0)

    def test_sampling_by_hash_is_stable_and_near_the_dial(self):
        agent = self.ready()
        gate = self.house.jev_floor.gate
        gate.rng = None
        picks = [gate._sampled(agent, 1789000000.0, slot) for slot in range(3000)]
        self.assertEqual(picks, [gate._sampled(agent, 1789000000.0, slot) for slot in range(3000)], "a restart does not re-roll")
        self.assertGreater(sum(picks) / len(picks), 0.08)
        self.assertLess(sum(picks) / len(picks), 0.12)

    def test_game_switch_turns_every_gate_off(self):
        agent = self.ready()
        self.house.game["research"]["gate"]["enabled"] = False
        for _ in range(4):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates(), [])

    def test_relevance_is_cached_by_note_and_strategy_sha(self):
        agent = self.ready(p=0.9)
        twin = self.seated(name="twin")  # the same file, so the same strategy sha
        self.house._state["last_research"][twin.id] = self.clock()
        for member in (agent, twin):
            summary(self.house.ledger, member.id)
            summary(self.house.ledger, member.id)
        self.house.ledger.append("library.note", {"title": "Fee change", "text": "z" * 80, "niche": "alpaca-crypto-alts"}, agent="peer")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertTrue(self.house.research_due(twin))
        self.assertEqual(len(self.jev.calls), 1, "one (note, strategy sha) question bought once for both")
        self.assertEqual(self.gates(twin.id)[-1]["reason"], "jev_relevant_note")

    def test_a_failing_gate_fails_open(self):
        agent = self.ready()
        self.house.jev_floor.gate.allow = lambda *a, **k: 1 / 0
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))

    def test_switching_this_gate_off_falls_back_to_v0(self):
        agent = self.ready(settings={"enabled": False})
        self.assertIsNone(self.house.jev_floor.gate)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates(), [])
        self.house._state["empty_research"] = {agent.id: 3}  # v0's own count
        self.researched(agent)
        self.clock.advance(self.interval)
        self.house.research_due(agent)
        self.assertEqual(self.gates()[-1]["empty_streak"], 3, "v0 decided and wrote its row")
        self.assertNotIn("triggers", self.gates()[-1])


class InactivityTest(GateCase):
    def rows(self, agent):
        return [e.payload for e in self.house.ledger.read(kinds="agent.inactive", agent=agent.id)]

    def test_rows_only_on_change_and_each_reason(self):
        agent = self.ready()
        floor = self.house.jev_floor
        sweep = lambda: floor.inactivity.update([agent])  # noqa: E731
        sweep()
        self.assertEqual(self.rows(agent), [], "no research yet and nothing wrong: no row")
        summary(self.house.ledger, agent.id)
        sweep()
        sweep()
        self.assertEqual([r["reason"] for r in self.rows(agent)], ["abstained"])
        summary(self.house.ledger, agent.id, reason="provider: provider_http_503", text="")
        sweep()
        summary(self.house.ledger, agent.id, trials=2, text="both replays errored")
        sweep()
        self.house._state["idle"][agent.id] = {"barren": 0, "shut": 4, "offered": 0}
        sweep()
        self.house.ledger.append("book.refused", {"book": "alpaca-paper", "reasons": ["outside the specialty"]}, agent=agent.id)
        sweep()
        (self.house.root / "PAUSE").write_text("maintenance")
        sweep()
        (self.house.root / "PAUSE").unlink()
        self.house.ledger.append("book.fill", {"book": "alpaca-paper"}, agent=agent.id)
        sweep()
        self.assertEqual([r["reason"] for r in self.rows(agent)],
                         ["abstained", "provider_failure", "failed_evaluation", "market_closed", "order_rejected", "paused", None])
        self.assertEqual(self.rows(agent)[-1]["was"], "paused")

    def test_barren_wakes_are_an_abstention_but_missing_data_wins(self):
        agent = self.ready()
        self.house._state["idle"][agent.id] = {"barren": 12, "shut": 0, "offered": 30}
        self.house.jev_floor.inactivity.update([agent])
        self.assertEqual(self.rows(agent)[-1]["reason"], "abstained")
        self.assertIn("12 wakes", self.rows(agent)[-1]["detail"])
        summary(self.house.ledger, agent.id, text="The underlying-value feed remains not_supplied; nothing to test.")
        self.house.jev_floor.inactivity.update([agent])
        self.assertEqual(self.rows(agent)[-1]["reason"], "missing_data")

    def test_missing_data_from_an_unresolved_request(self):
        agent = self.ready()
        self.house.commons.request_tool(agent.id, "options_history", "historical option chains for replay of long calls")
        summary(self.house.ledger, agent.id, text="Spend no credits; nothing to test.")
        self.house.jev_floor.inactivity.update([agent])
        row = self.rows(agent)[-1]
        self.assertEqual(row["reason"], "missing_data")
        self.assertEqual(row["requests"], ["options_history"])


class TriageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def triage(self, jev=None, **settings):
        sensor = Sensor(Path(self.dir.name) / "jev.sqlite", jev, clock=self.clock) if jev else None
        requests = lambda: [{"by": e.agent, "name": e.payload["name"], "status": "open"}  # noqa: E731
                            for e in self.ledger.iter(kinds="tool.request")]
        return Triage(self.ledger, sensor, clock=self.clock, path=Path(self.dir.name) / "triage.json", settings=settings,
                      requests=requests, niche_of=lambda a: "kalshi-attention")

    def reports(self):
        return [e.payload for e in self.ledger.iter(kinds="repair.reported")]

    def test_exact_dedupe_keeps_every_piece_of_evidence_and_agent(self):
        for agent in ("leahy-27", "leahy-30", "leahy-31"):
            self.ledger.append("tool.request", {"name": "underlying_value_feed", "description": "point-in-time observed values for attention series"}, agent=agent)
        summary(self.ledger, "leahy-30", text="Spend nothing; the underlying-value feed remains unimplemented.")
        triage = self.triage()
        out = triage.run()
        reports = self.reports()
        self.assertEqual(len(reports), 1)
        row = reports[0]
        self.assertEqual(row["key"], "missing_data:underlying_value_feed")
        self.assertEqual(row["kind"], "missing_data")
        self.assertEqual(row["source"], "triage")
        self.assertEqual(row["agents"], ["leahy-27", "leahy-30", "leahy-31"])
        self.assertEqual(len(row["evidence"]), 4, "three requests and the abstention they cost")
        self.assertTrue(all({"seq", "at", "agent", "excerpt"} <= set(e) for e in row["evidence"]))
        self.assertEqual(row["severity"], "medium")
        self.assertEqual(out["reported"], 1)
        # Nothing new: nothing written. New evidence: a new row for the same key.
        triage.state["last_run"] = 0
        triage.run()
        self.assertEqual(len(self.reports()), 1)
        self.ledger.append("tool.request", {"name": "underlying_value_feed", "description": "again, the observed values please"}, agent="leahy-40")
        triage.run()
        self.assertEqual(len(self.reports()), 2)
        self.assertEqual(self.reports()[-1]["agents"], ["leahy-40"])
        self.assertEqual(self.reports()[-1]["all_agents"], 4)

    def test_keys_and_excerpts_match_the_worklist_reporters(self):
        """The repair worklist (night/repairs) reports the same tool requests and abstentions
        deterministically; its fold counts a row once only if (seq, agent, excerpt[:200]) match."""
        description = "  point-in-time observed values for attention series, with source timestamps  "
        self.ledger.append("tool.request", {"name": "Underlying Value-Feed", "description": description}, agent="leahy-27")
        self.triage().run()
        row = self.reports()[0]
        self.assertEqual(row["key"], "missing_data:underlying_value_feed")
        self.assertEqual(row["evidence"][0]["excerpt"][:200], description[:200])

    def test_jev_merges_a_differently_named_request_for_the_same_feed(self):
        jev = FakeJev(0.95)
        self.ledger.append("tool.request", {"name": "underlying_value_feed", "description": "point-in-time observed values for attention series counts"}, agent="leahy-27")
        triage = self.triage(jev)
        triage.run()
        self.ledger.append("tool.request", {"name": "attention_observations", "description": "observed values for attention series counts, point-in-time"}, agent="leahy-30")
        triage.run()
        self.assertEqual(triage.state["aliases"], {"missing_data:attention_observations": "missing_data:underlying_value_feed"})
        last = self.reports()[-1]
        self.assertEqual(last["key"], "missing_data:underlying_value_feed")
        self.assertEqual(last["aliases"], ["attention_observations"])
        self.assertEqual(last["evidence"][0]["agent"], "leahy-30")
        self.assertTrue(any(e.payload["question"] == "same_feed" for e in self.ledger.iter(kinds="triage.item")))

    def test_uncertain_same_feed_keeps_requests_separate(self):
        jev = FakeJev(0.6)
        self.ledger.append("tool.request", {"name": "underlying_value_feed", "description": "point-in-time observed values for attention series counts"}, agent="a")
        triage = self.triage(jev)
        triage.run()
        self.ledger.append("tool.request", {"name": "attention_observations", "description": "observed values for attention series counts"}, agent="b")
        triage.run()
        self.assertEqual(triage.state["aliases"], {})
        self.assertEqual({r["key"] for r in self.reports()}, {"missing_data:underlying_value_feed", "missing_data:attention_observations"})

    def test_bug_reports_are_classified_once_and_capped(self):
        jev = FakeJev(lambda text: 0.9 if "reconcile" in text else 0.1)
        for n in range(3):
            self.ledger.append("agent.thought", {"phase": "research", "text": f"The book does not reconcile: fill {n} was recorded twice, a phantom position."}, agent=f"a{n}")
        self.ledger.append("agent.thought", {"phase": "research", "text": "The spread was wrong for my rule, so I lost money on that trade today."}, agent="b")
        triage = self.triage(jev)
        triage.run()
        bugs = [r for r in self.reports() if r["kind"] == "bug_report"]
        self.assertEqual(len(bugs), 1, "numbers normalized: one defect, three witnesses")
        self.assertEqual(bugs[0]["agents"], ["a0", "a1", "a2"])
        self.assertEqual(len(jev.calls), 1)
        capped = self.triage(FakeJev(0.9), max_questions_per_run=0)
        capped.state = {"seq": 0, "last_run": 0, "groups": {}, "aliases": {}}
        capped.run()
        self.assertEqual(len([r for r in self.reports() if r["kind"] == "bug_report"]), 1)

    def test_the_same_defect_restated_joins_one_group(self):
        jev = FakeJev(lambda text: 0.95)
        triage = self.triage(jev)
        self.ledger.append("agent.research", {"tool": "journal", "text": "Found a material exit bug: _right(occ) checks s[-9] for C/P and misroutes every put exit."}, agent="k-1")
        triage.run()
        self.ledger.append("agent.research", {"tool": "journal", "text": "The OCC exit bug is still live: _right(occ) reads s[-9], so put exits are misrouted as calls."}, agent="k-2")
        triage.state["last_run"] = 0
        triage.run()
        keys = {r["key"] for r in self.reports() if r["kind"] == "bug_report"}
        self.assertEqual(len(keys), 1)
        self.assertEqual(sorted({a for r in self.reports() for a in r["agents"]}), ["k-1", "k-2"])
        self.assertTrue(any(e.payload["question"] == "same_defect" for e in self.ledger.iter(kinds="triage.item")))

    def test_capped_bug_questions_wait_for_the_next_run(self):
        jev = FakeJev(0.9)
        for n in range(20):
            self.ledger.append("agent.thought", {"phase": "research", "text": f"Defect {'abcdefghijklmnopqrstuvwxyz'[n]}: the ledger shows a duplicate fill that never reached the venue."}, agent=f"a{n}")
        triage = self.triage(jev, max_questions_per_run=16)
        triage.run()
        self.assertEqual(len(triage.state["pending_bugs"]), 4)
        triage.state["last_run"] = 0
        triage.run()
        self.assertEqual(triage.state["pending_bugs"], [])
        self.assertEqual(len({a for r in self.reports() if r["kind"] == "bug_report" for a in r["agents"]}), 20,
                         "every witness is reported, whether or not its text joined an earlier group")

    def test_abstention_without_request_joins_the_request_jev_matches(self):
        jev = FakeJev(0.9)
        self.ledger.append("tool.request", {"name": "funding_rates", "description": "perpetual funding rate and open interest feed for BTC ETH"}, agent="r-1")
        triage = self.triage(jev)
        triage.run()
        summary(self.ledger, "r-2", text="Spend nothing. The perpetual funding rate and open interest feed for BTC remains not_supplied.")
        triage.run()
        self.assertEqual(self.reports()[-1]["key"], "missing_data:funding_rates")
        self.assertEqual(self.reports()[-1]["agents"], ["r-2"])
        # Without Jev it joins its niche's single "unrequested" group instead of a key per sentence.
        summary(self.ledger, "r-3", text="Nothing to do: the settlement-source history is unavailable for these markets.")
        summary(self.ledger, "r-4", text="The settlement-source data remains missing; abstaining again.")
        plain = self.triage()
        plain.state = {"seq": self.ledger.head()[0] - 2, "last_run": 0, "groups": {}, "aliases": {}, "names": {}}
        plain.run()
        self.assertEqual(self.reports()[-1]["key"], "missing_data:research:kalshi-attention")
        self.assertEqual(self.reports()[-1]["agents"], ["r-3", "r-4"])

    def test_postmortems_only_report_defect_causes(self):
        self.ledger.append("agent.postmortem", {"cause": "displaced", "text": "the league was full"}, agent="x-1")
        self.ledger.append("agent.postmortem", {"cause": "stuck", "text": "never woke for a day"}, agent="x-2")
        self.triage().run()
        self.assertEqual([r["key"] for r in self.reports()], ["strategy_defect:x:stuck"])


class HypothesisLinkTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def card(self, text, niche="kalshi-weather"):
        ident = mechanism_id(text, niche)
        self.ledger.append("hypothesis.card", {"id": ident, "mechanism": text, "niche": niche, "author": "researcher"})
        return ident

    def memory(self, p):
        sensor = Sensor(Path(self.dir.name) / "jev.sqlite", FakeJev(p), clock=self.clock)
        return HypothesisMemory(self.ledger, sensor, path=Path(self.dir.name) / "memory.json", clock=self.clock)

    def links(self):
        return [e.payload for e in self.ledger.iter(kinds="hypothesis.link")]

    def test_confident_rewording_uncertain_related_never_genealogy(self):
        a = self.card("Buy NO on high-temperature favourites priced 90 to 97 cents a few hours before close, because the day's high is set.")
        trials_before = self.ledger.count(kinds="eval.trial")
        self.memory(0.95).run()
        b = self.card("Favourite high-temperature NO contracts at 90-97 cents shortly before close win because the daily high is already set.")
        self.memory(0.95).run()
        c = self.card("Buy NO on favourite high-temperature contracts before close when the forecast high is already set by afternoon.")
        self.memory(0.6).run()
        relations = {(l["a"], l["b"]): (l["relation"], l["method"]) for l in self.links()}
        self.assertEqual(relations[tuple(sorted((a, b)))], ("rewording", "jev"))
        self.assertIn(("related", "jev"), relations.values())
        self.assertNotIn(("rewording", "jev"), [relations[k] for k in relations if c in k], "an uncertain label is never a rewording")
        self.assertEqual(self.ledger.count(kinds="eval.trial"), trials_before)
        self.assertEqual(self.ledger.count(kinds=("agent.born", "agent.forked", "agent.strategy")), 0)

    def test_ids_follow_the_card_rule_and_numbers_only_changes_are_rewordings(self):
        import hashlib
        text = "Buy NO on favourites priced 0.90 to 0.97 within 12 hours of close."
        self.assertEqual(mechanism_id(text, "kalshi-weather"),
                         hashlib.sha256(("buy no on favourites priced 0 90 to 0 97 within 12 hours of close" + "\n" + "kalshi-weather").encode()).hexdigest()[:16])
        a = self.card(text)
        b = self.card("Buy NO on favourites priced 0.92 to 0.98 within 6 hours of close.")
        HypothesisMemory(self.ledger, None, path=Path(self.dir.name) / "m.json", clock=self.clock).run()
        self.assertEqual(self.links(), [{"a": min(a, b), "b": max(a, b), "relation": "rewording", "confidence": 1.0, "method": "exact"}])

    def test_same_words_in_another_niche_are_related_exactly(self):
        text = "Fade the first hour gap on megacap stocks when volume is below its twenty day average and spreads are tight."
        a = self.card(text, "alpaca-megacaps")
        b = self.card(text, "alpaca-index-etfs")
        HypothesisMemory(self.ledger, None, path=Path(self.dir.name) / "m.json", clock=self.clock).run()
        self.assertEqual(self.links(), [{"a": min(a, b), "b": max(a, b), "relation": "related", "confidence": 1.0, "method": "exact"}])

    def test_capped_pairs_wait_for_the_next_run(self):
        base = "Buy NO on favourite high temperature contracts before close because the daily high is set"
        for n, extra in enumerate(["early", "late", "cloudy", "sunny", "windy"]):
            self.card(f"{base} on {extra} days")
        memory = self.memory(0.5)
        memory.settings["max_questions_per_run"] = 3
        first = memory.run()
        self.assertGreater(first["pending"], 0)
        for _ in range(10):
            if not memory.run()["pending"]:
                break
        self.assertEqual(memory.state["pending"], [])
        self.assertTrue(all(l["relation"] == "related" for l in self.links() if l["method"] == "jev"))
        self.assertGreaterEqual(len([l for l in self.links() if l["method"] == "jev"]), 4)

    def test_failure_history_keeps_linked_records_apart(self):
        code = "'''Sell the spike on rain contracts when the forecast probability jumps without a model update behind it.'''\ndef decide(ctx): return {}"
        self.ledger.append("agent.born", {"_code": code, "code_sha256": "c1", "specialty": "kalshi-weather"}, agent="w-1")
        self.ledger.append("eval.trial", {"code_sha256": "c1", "passed": False, "reasons": ["deflated Sharpe 0.1"]}, agent="w-1")
        self.ledger.append("eval.trial", {"code_sha256": "c1", "passed": False, "reasons": ["too few trades"]}, agent="w-1")
        code2 = "'''Fade rain contract spikes when forecast probability jumps with no weather model update behind it.'''\ndef decide(ctx): return {}"
        self.ledger.append("agent.born", {"_code": code2, "code_sha256": "c2", "specialty": "kalshi-weather"}, agent="w-9")
        memory = self.memory(0.95)
        memory.run()
        history = memory.failure_history(mechanism_id(code2.split("'''")[1], "kalshi-weather"))
        self.assertTrue(history["known"])
        self.assertEqual(history["own"]["failed_trials"], 0, "a rewording does not inherit failures")
        self.assertEqual(history["linked"][0]["relation"], "rewording")
        self.assertEqual(history["linked"][0]["record"]["failed_trials"], 2)


class ExposureTest(HouseCase):
    def test_exact_keys(self):
        event = SimpleNamespace(venue="kalshi-shadow", market_id="KXWTI-26SEP2214-T90.99", symbol="KXWTI-26SEP2214-T90.99")
        self.assertEqual(keys_of(event), {"event": "KXWTI-26SEP2214", "series": "KXWTI"})
        self.assertEqual(keys_of(SimpleNamespace(venue="alpaca-paper", market_id=None, symbol="BTC/USD")), {"underlying": "BTC"})

    def test_groups_bets_across_agents_report_only(self):
        from league.book import Holding
        from league.venues import instrument_for
        book = self.house.books["alpaca-paper"]
        for agent in ("a-1", "b-1"):
            account = book._account(agent) if hasattr(book, "_account") else None
            if account is None:
                from league.book import Account
                account = book.accounts.setdefault(agent, Account(agent))
            account.holdings["BTC"] = Holding(self.btc, quantity=Decimal("0.001"), cost=Decimal("80"))
        out = Exposure(self.house, None, clock=self.clock).run()
        self.assertEqual(out["shared_groups"][0]["key"], "underlying:BTC")
        self.assertEqual(out["shared_groups"][0]["agents"], ["a-1", "b-1"])
        self.assertIn("report only", out["authority"])


class ExposureJevTest(unittest.TestCase):
    def test_related_but_not_identical_contracts_are_asked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = Clock()
            jev = FakeJev(lambda text: 0.9 if "BTC" in text or "KXBTC" in text else 0.1)
            sensor = Sensor(Path(tmp) / "jev.sqlite", jev, clock=clock)
            groups = {"series:KXBTCD": {"level": "series", "agents": {"a"}}, "underlying:BTC": {"level": "underlying", "agents": {"b"}},
                      "series:KXHIGHNY": {"level": "series", "agents": {"c"}}}
            exposure = Exposure(SimpleNamespace(books={}), sensor, clock=clock)
            related = exposure._related(groups)
            self.assertEqual([(r["a"], r["b"]) for r in related], [("series:KXBTCD", "underlying:BTC")])
            self.assertEqual(related[0]["agents"], ["a", "b"])
            calls = len(jev.calls)
            exposure._related(groups)
            self.assertEqual(len(jev.calls), calls, "cached by pair")


class FloorTickTest(HouseCase):
    def floor(self):
        self.jev = FakeJev(0.1)
        self.house.jev_floor = JevFloor(self.house, Sensor(self.house.root / "jev.sqlite", self.jev, clock=self.clock), {})
        return self.house.jev_floor

    def test_tick_runs_the_jobs_and_publishes_health(self):
        self.floor()
        self.house.ledger.append("tool.request", {"name": "funding_rates", "description": "perpetual funding feed for BTC and ETH"}, agent="r-1")
        self.house.tick()
        self.house.wait(10)
        self.clock.advance(60)
        self.house.tick()
        self.house.wait(10)
        health = json.loads((self.house.root / "health.json").read_text())
        self.assertEqual(health["jev"]["sensor"]["model"], MODEL)
        self.assertEqual(health["jev"]["exposure"]["positions"], 0)
        self.assertEqual(health["jev"]["triage"]["groups"], 1)
        self.assertEqual([e.payload["key"] for e in self.house.ledger.iter(kinds="repair.reported")], ["missing_data:funding_rates"])

    def test_a_pause_stops_paid_jobs_but_not_the_inactivity_sweep(self):
        floor = self.floor()
        agent = self.seated()
        (self.house.root / "PAUSE").write_text("rebuild")
        self.house.ledger.append("tool.request", {"name": "funding_rates", "description": "perpetual funding feed for BTC and ETH"}, agent="r-1")
        self.house.tick()
        self.house.wait(10)
        self.assertEqual(floor.inactivity.current(agent.id), "paused")
        self.assertEqual(self.house.ledger.count(kinds="repair.reported"), 0)
        self.assertEqual(self.jev.calls, [])


class ReportCliTest(GateCase):
    def test_cli_reads_a_ledger_file_without_writing(self):
        import contextlib
        import io
        from league.research_gate import main
        agent = self.ready()
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        head = self.house.ledger.head()
        before = (self.house.root / "jev.sqlite").read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(self.house.root / "ledger.sqlite"), "--sensor", str(self.house.root / "jev.sqlite")])
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["skipped_sessions"], 1)
        self.assertEqual(printed["jev"]["model"], MODEL)
        self.assertEqual(self.house.ledger.head(), head)
        self.assertEqual((self.house.root / "jev.sqlite").read_bytes(), before)


class OutcomeTest(unittest.TestCase):
    def test_session_outcomes_match_the_production_reasons(self):
        self.assertEqual(session_outcome({"reason": "finished", "candidate": False, "trials": 0}), "abstained")
        self.assertEqual(session_outcome({"reason": "no tool call", "candidate": False}), "abstained")
        self.assertEqual(session_outcome({"reason": "provider: provider_http_503"}), "provider_failure")
        self.assertEqual(session_outcome({"reason": "finished", "candidate": True, "trials": 1}), "candidate")
        self.assertEqual(session_outcome({"reason": "finished", "candidate": False, "trials": 2}), "failed_evaluation")


if __name__ == "__main__":
    unittest.main()
