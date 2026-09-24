"""The loop's joints (L2 and L3 of the close-the-gaps run, Sept 24, 2026), on a real House.

L2, the research economy follows evidence, not the clock: the Sail research cap, a session the
provider broke is not a pass, and an agent under the abstention lock researches on the cheapest
profile. L3, warnings that repeat escalate: the same warning text ten times in thirty minutes is
one error alert with its traceback, listed in health.json until it stops; and "the lab evaluated
nothing in the last hour while its queue is not empty" is a health failure the watchdog reads.
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from league.campaigns import CampaignBudget
from league.house import alert_key
from league.ledger import now_iso
from league.researcher import Pass
from league.tests.test_jev_sensor import GateCase, summary


def health(house):
    """What `House._health` writes at the end of a tick."""
    house._health({"at": now_iso(house.clock)})
    return json.loads((house.root / "health.json").read_text(encoding="utf-8"))


class RepeatedWarnings(GateCase):
    """Sept 23-24, 2026: "the lab's step failed (IndexError: list index out of range)" was a warning
    115 times in 2 h 18 min, 43 of them in two hours, and nothing escalated."""

    def alerts(self, level=None):
        return [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if level is None or e.payload.get("level") == level]

    def test_the_same_text_folded_ten_times_in_thirty_minutes_is_one_error_with_its_traceback(self):
        for n in range(9):
            self.house.alert("warning", f"the lab's step failed {n + 3} times (IndexError at 0x7f{n}a1)", phase="breed")
            self.clock.advance(120)
        self.assertEqual(self.alerts("error"), [], "nine is not ten")
        self.house.alert("warning", "the lab's step failed 12 times (IndexError at 0x7f9a1)", phase="breed", _traceback="Traceback: IndexError")
        errors = self.alerts("error")
        self.assertEqual(len(errors), 1)
        error = errors[0]
        self.assertIn("repeated 10 times in 30 minutes", error["text"])
        self.assertIn("the lab's step failed 12 times", error["text"])
        self.assertEqual((error["phase"], error["_traceback"]), ("breed", "Traceback: IndexError"))  # the last payload
        self.assertEqual(error["repeated"]["count"], 10)
        self.assertEqual(error["began_at"], error["repeated"]["first_seen"])
        for _ in range(5):
            self.clock.advance(60)
            self.house.alert("warning", "the lab's step failed 99 times (IndexError at 0x7f9a1)")
        self.assertEqual(len(self.alerts("error")), 1, "ONE error alert for the run of repeats")
        listed = health(self.house)["repeating_warnings"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["count"], 15)
        self.assertIn("the lab's step failed 99 times", listed[0]["text"])
        self.assertEqual(listed[0]["first_seen"], error["began_at"])

    def test_it_is_listed_until_it_stops_for_thirty_minutes_and_can_escalate_again(self):
        for _ in range(10):
            self.house.alert("warning", "publishing failed (PublishError: HTTP 400)")
            self.clock.advance(30)
        self.assertEqual(len(health(self.house)["repeating_warnings"]), 1)
        self.clock.advance(29 * 60)
        self.assertEqual(len(health(self.house)["repeating_warnings"]), 1)
        self.clock.advance(2 * 60)
        self.assertEqual(health(self.house)["repeating_warnings"], [])
        for _ in range(10):
            self.house.alert("warning", "publishing failed (PublishError: HTTP 502)")
            self.clock.advance(30)
        self.assertEqual(len(self.alerts("error")), 2, "a new run of repeats is a new alert")

    def test_slow_repeats_other_words_and_other_levels_do_not_escalate(self):
        for _ in range(12):
            self.house.alert("warning", "the frontier budget $7.94 left")
            self.clock.advance(4 * 60)  # three hours of it, never ten inside thirty minutes
        for n in range(12):
            self.house.alert("info", "a birth")
            self.house.alert("warning", f"desk {chr(97 + n)}: offered markets and no intent")
        self.assertEqual(self.alerts("error"), [])

    def test_a_restart_keeps_the_count_and_does_not_say_it_twice(self):
        for _ in range(10):
            self.house.alert("warning", "alpaca-paper: could not poll (TransportError)")
            self.clock.advance(20)
        self.house._save_state()
        self.house.close(wait=None)
        self.house = self.new_house()
        for _ in range(3):
            self.house.alert("warning", "alpaca-paper: could not poll (TransportError)")
        self.assertEqual(len(self.alerts("error")), 1)
        self.assertEqual(health(self.house)["repeating_warnings"][0]["count"], 13)

    def test_a_house_with_no_runs_rebuilds_them_from_the_ledger_so_the_watch_inherits_them(self):
        """Review of #236 (Sept 24, 2026): Deploy A's House counted no runs, so Deploy B's House found
        none in house.json and began every run at its own restart. A site refusing every checkpoint
        through Deploy A then escalated inside Deploy B's ten-minute watch with `began_at` after the
        promotion, and the watchdog would have rolled the healthy release back for a condition it
        inherited. A House with no runs rebuilds them from the ledger's own warnings."""
        from league.watchdog import HouseHealth

        text = 'publishing failed (PublishError: the site refused the checkpoint: HTTP 400 {"error":"Invalid checkpoint."})'
        first = None
        for _ in range(20):  # the release before: one warning a tick, and no runs kept
            row = self.house.ledger.append("ops.alert", {"level": "warning", "text": text})
            first = first or row.at
            self.clock.advance(40)
        self.house._state.pop("repeating_warnings", None)
        health(self.house)  # its last tick; the next House loads a house.json with no runs
        self.house._state.pop("repeating_warnings", None)
        self.house._save_state()
        watch = HouseHealth(self.house.root, clock=self.clock, restart_within=None)
        self.assertTrue(watch().ok)  # the reading just before the promotion
        self.house.close(wait=None)
        self.house = self.new_house()
        for _ in range(15):  # the watch after the promotion: the same refusal, one a tick
            self.clock.advance(40)
            self.house.alert("warning", text)
            health(self.house)
            reading = watch()
            self.assertTrue(reading.ok, reading.reasons)
        errors = self.alerts("error")
        self.assertEqual(len(errors), 1, "the run had repeated before the restart: it escalates once")
        self.assertEqual(errors[0]["began_at"], first, "and began when the first warning of the run was written")
        self.assertEqual(health(self.house)["repeating_warnings"][0]["first_seen"], first)

    def test_a_run_rebuilt_from_the_ledger_that_had_escalated_does_not_escalate_again(self):
        for _ in range(10):
            self.house.alert("warning", "alpaca-paper: could not poll (TransportError)")
            self.clock.advance(20)
        self.assertEqual(len(self.alerts("error")), 1)
        self.house._state.pop("repeating_warnings", None)  # a lost house.json
        self.house.alert("warning", "alpaca-paper: could not poll (TransportError)")
        self.assertEqual(len(self.alerts("error")), 1)
        self.assertEqual(health(self.house)["repeating_warnings"][0]["count"], 11)

    def test_numbers_and_ids_fold_and_words_do_not(self):
        self.assertEqual(alert_key("haghani-52: its wake failed (GET /v2/orders/7974aa54-fbb9-4d9a-9aa0-61dbb64ca0d6 timed out)"),
                         alert_key("haghani-51: its wake failed (GET /v2/orders/daa7473c-ecf3-4897-90ef-092a4786e741 timed out)"))
        self.assertEqual(alert_key("cash differs by -40.0000"), alert_key("cash differs by 41.2200"))
        self.assertNotEqual(alert_key("kalshi does not reconcile"), alert_key("alpaca-paper does not reconcile"))


class TheLabEvaluatesNothing(GateCase):
    """At T0 of the close-the-gaps run the lab's last batch was 23:37:17Z with 618 candidates queued,
    two hours before anything but a warning said so."""

    def lab(self, *, queued, last_batch, oldest=None):
        rows = {"batches": [{"at": last_batch}], "candidates": [{"at": oldest if oldest is not None else self.clock() - 7200}]}
        self.house.lab = SimpleNamespace(
            health=lambda: {"queued": queued, "refusal": None, "error": "IndexError: list index out of range"},
            _q=lambda sql, params=(): rows["batches"] if "batches" in sql else rows["candidates"])

    def test_an_hour_of_nothing_with_a_queue_is_a_health_failure_and_one_error(self):
        self.lab(queued=618, last_batch=self.clock() - 3000)
        self.assertEqual(health(self.house)["failures"], [])
        self.clock.advance(700)
        failures = health(self.house)["failures"]
        self.assertEqual([f["check"] for f in failures], ["lab_evaluates"])
        self.assertIn("618 candidates are queued", failures[0]["text"])
        self.assertIn("IndexError", failures[0]["text"])
        errors = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if e.payload.get("level") == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["began_at"], failures[0]["since"])
        health(self.house)
        self.assertEqual(len([e for e in self.house.ledger.iter(kinds="ops.alert") if e.payload.get("level") == "error"]), 1)
        self.lab(queued=618, last_batch=self.clock() - 10)
        self.assertEqual(health(self.house)["failures"], [])
        infos = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if e.payload.get("level") == "info"]
        self.assertTrue(any("evaluates again" in text for text in infos), infos)

    def test_an_empty_queue_or_a_queue_younger_than_an_hour_is_no_failure(self):
        self.lab(queued=0, last_batch=self.clock() - 86400)
        self.assertEqual(health(self.house)["failures"], [])
        self.lab(queued=5, last_batch=self.clock() - 86400, oldest=self.clock() - 1800)
        self.assertEqual(health(self.house)["failures"], [], "the queue filled half an hour ago: it has had no hour yet")


class TheSailResearchCap(GateCase):
    """Sept 23, 2026, 22-23Z: Sail research spent $11.66 in an hour (344 calls) once the OpenAI tier
    fell and cheap research moved to Sail. turbo.json `sail_research_usd_per_hour` ($2) stops NEW
    Sail sessions while the last hour's Sail research spend has reached it."""

    def setUp(self):
        super().setUp()
        self.agent = self.ready()
        self.guard = CampaignBudget(self.house.root / "campaigns.sqlite", clock=self.clock)
        self.addCleanup(self.guard.close)
        self.house.campaigns = self.guard
        self.house._sail_research_cap = Decimal("2")
        self.clock.advance(self.interval)

    def spend(self, usd, *, settled=True):
        micro = int(Decimal(usd) * 1_000_000)
        with self.guard.lock:
            self.guard.db.execute("INSERT INTO commitments VALUES(?,?,?,?,?,?)",
                                  (f"sail:{self.clock()}:{usd}", "baseline-research", "sail", micro * 20, micro if settled else None, self.clock()))

    def test_new_sail_sessions_stop_at_the_cap_and_start_again_under_it(self):
        self.spend("1.20")
        self.spend("0.50", settled=False)  # a call in flight counts once it settles
        self.assertTrue(self.house.research_due(self.agent))
        self.house._sail_cap_cache = None
        self.spend("0.85")
        self.assertFalse(self.house.research_due(self.agent), "$2.05 settled in the hour: no new Sail session")
        state = health(self.house)["research_economy"]["sail_cap"]
        self.assertEqual((state["capped"], state["last_hour_usd"], state["cap_usd"]), (True, "2.05", "2"))
        self.assertEqual(state["inflight_calls"], 1)
        rows = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "sail research cap"]
        self.assertEqual([r["capped"] for r in rows], [True])
        self.clock.advance(3601)
        self.assertTrue(self.house.research_due(self.agent), "an hour later the spend has left the window")
        rows = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "sail research cap"]
        self.assertEqual([r["capped"] for r in rows], [True, False])

    def test_a_job_queued_while_the_cap_was_open_does_not_start_once_it_has_closed(self):
        """Review of #236 (Sept 24, 2026): the tick enqueues every due agent at once and the research
        lane (6 workers) takes them one by one; each worker asks `research_due` again, which let any
        queued job through as a session "under way". Up to 34 research jobs waited for the lane at
        once on Sept 24 00Z, so the cap could have been passed by every session queued before it
        closed. A job not begun has bought nothing: it waits for the cap like a new session."""
        self.assertTrue(self.house.research_due(self.agent))
        job = self.house.research_jobs.enqueue(self.agent.id, self.house._generation(self.agent.id))  # the lane is busy
        self.spend("2.40")
        self.house._sail_cap_cache = None
        self.assertFalse(self.house.research_due(self.agent), "queued, not begun: no paid call yet, so the cap holds it")
        self.assertEqual(self.house.research_jobs.active(self.agent.id)["session"], job["session"], "the job stays queued")
        self.clock.advance(3601)
        self.assertTrue(self.house.research_due(self.agent), "the hour's spend left the window: the queued job runs")

    def test_a_session_already_started_resumes_and_luna_is_not_capped(self):
        self.spend("3.00")
        self.assertFalse(self.house.research_due(self.agent))
        job = self.house.research_jobs.enqueue(self.agent.id, self.house._generation(self.agent.id))
        self.house.research_jobs.start(job["session"], {"standing": {}})
        self.assertTrue(self.house.research_due(self.agent), "a session already under way is not stopped half-paid")
        other = self.seated("luna-agent")
        self.house._state["last_research"][other.id] = self.clock() - self.interval
        self.house.researcher.provider = SimpleNamespace(settings_for=lambda agent, s: {**s, "profile": "openai_luna"})
        self.assertTrue(self.house.research_due(other), "the cap is on Sail's spend")


class AProviderFailureIsNotAPass(GateCase):
    """A session that ends in a provider 502 or 504 is refunded (league/researcher.py) and is not a
    completed pass: the House gives the agent its turn back in fifteen minutes, and the empty-pass
    count and the gate's abstention streak do not move."""

    def test_the_agent_is_due_again_in_fifteen_minutes_and_nothing_counts_it(self):
        agent = self.ready()
        self.clock.advance(self.interval)
        self.house.researcher = SimpleNamespace(research=lambda *a, **k: Pass(agent.id, turns=3, reason="provider: provider_http_502"))
        before = int((self.house._state.get("empty_research") or {}).get(agent.id) or 0)
        self.house.research(agent)
        self.assertEqual(int((self.house._state.get("empty_research") or {}).get(agent.id) or 0), before)
        self.assertEqual(self.house.research_jobs.last_finished(agent.id), 0, "not a finished pass")
        self.assertFalse(self.house.research_due(agent))
        self.clock.advance(15 * 60 + 1)
        self.assertTrue(self.house.research_due(agent))

    def test_a_session_the_model_itself_ended_is_still_a_pass(self):
        agent = self.ready()
        self.clock.advance(self.interval)
        self.house.researcher = SimpleNamespace(research=lambda *a, **k: Pass(agent.id, turns=3, reason="provider: max_output_tokens"))
        self.house.research(agent)
        self.assertGreater(self.house.research_jobs.last_finished(agent.id), 0)
        self.clock.advance(15 * 60 + 1)
        self.assertFalse(self.house.research_due(agent), "the interval runs from a pass the agent's own model spent")


class TheAbstentionLockBuysTheCheapestProfile(GateCase):
    """An agent under `abstain_lock` (three abstaining sessions in a row) researches on game.json
    `research.gate.abstain_lock_profile`, flash_asap: $0.0027 a call against Luna's $0.0080 and
    pro_asap's $0.0299 on the same frozen packets (league/routing_evidence.json, Sept 22, 2026)."""

    def test_a_locked_agents_new_session_moves_to_the_lock_profile(self):
        from league.routing import TaskRouter

        agent = self.ready(legacy=False, settings={"clock_runs": "winners_and_idle", "abstain_lock_after": 3,
                                                   "abstain_lock_profile": "flash_asap"})
        router = TaskRouter(self.house.ledger, clock=self.clock, config={"record": False})
        router.lock = self.house.jev_floor.gate.lock_profile
        sail = {"profile": "pro_asap", "fast_profile": "pro_asap", "max_output_tokens": 32000}
        self.assertEqual(router.research_settings(agent, sail)["profile"], "pro_asap", "not locked: unchanged")
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        self.clock.advance(self.interval)
        self.house.research_due(agent)  # the gate reads the three abstentions
        self.assertEqual(self.house.jev_floor.gate.lock_profile(agent), "flash_asap")
        moved = router.research_settings(agent, sail)
        self.assertEqual((moved["profile"], moved["fast_profile"]), ("flash_asap", ""))
        luna = router.research_settings(agent, {**sail, "profile": "openai_luna", "max_output_tokens": 6000})
        self.assertEqual(luna["profile"], "flash_asap")
        self.assertEqual(router.research_settings(agent, {**sail, "profile": "flash_flex"})["profile"], "flash_flex",
                         "a cheaper Sail profile it already runs on is kept")
        summary(self.house.ledger, agent.id, candidate=True, trials=1)
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue"}, agent=agent.id)
        self.clock.advance(60)
        self.house.research_due(agent)
        self.assertIsNone(self.house.jev_floor.gate.lock_profile(agent), "a candidate lifts the lock")
