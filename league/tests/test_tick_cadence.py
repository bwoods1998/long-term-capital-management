"""The tick under 40 s, and research that survives restarts (H5/H6, Sept 25, 2026, the forward-first run).

Measured on the box 04:31-05:00Z Sept 25 (26 ticks, 128 living): ticks of 19-100 s, p50 60.8 s -- the
population step 22.0 s at p50 (75.3 s at its slowest), research 6.3 (24.0), wakes 6.2, poll:kalshi-shadow
5.5, hypotheses 2.2 (9.4), publish 1.2 -- and the log's tick lines 60-68 s apart at p50 in quiet hours, with `tick_seconds` (60) the floor.
On the T0 snapshot the refill asked the displacement scan 399 times a tick for 10 distinct questions
(17.1 of the tick's 18.4 s here). So the tick runs every 30 s for the wakes; the births pass runs every
five minutes or after a birth or a death, and asks each question once; research scheduling and the
foundry's step run beside the tick once a minute; a simulated venue and the site keep their minute.

H6: in the day to 04:39Z Sept 25 (26 restarts) 110 research sessions began before a restart and ended
after it; 25 were lost (23 `provider: campaign_post_unconfirmed`, 2 `tool outcome unconfirmed`) and
nothing said so, and health.json did not count the restarts.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.house import PROVIDER_RETRY_SECONDS, House, Settings
from league.ledger import now_iso
from league.researcher import Pass
from league.tests.fakes import FakeBroker
from league.tests.test_house import BUYER, HouseCase
from league.tests.test_seat_market import SeatCase


def health(house):
    return json.loads((house.root / "health.json").read_text(encoding="utf-8"))


def warnings(house, *words):
    return [e.payload for e in house.ledger.iter(kinds="ops.alert")
            if e.payload.get("level") == "warning" and all(w in e.payload.get("text", "") for w in words)]


class SimulatedVenue(FakeBroker):
    """A venue the House simulates itself (kalshi-shadow's shape): it has `advance` and walks `settlements`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.advanced = 0
        self.walked = 0

    def advance(self):
        self.advanced += 1
        return 0

    def settlements(self, since=None):
        self.walked += 1
        return []


class TheBirthsPass(HouseCase):
    def test_the_births_pass_runs_once_in_five_minutes_unless_someone_is_born_or_dies(self):
        passes = []
        with patch.object(self.house, "_births", side_effect=lambda rules: passes.append(self.clock())):
            self.house.tick()
            self.assertEqual(len(passes), 1)  # the first tick of a House
            for _ in range(9):  # 270 s of ticks with nobody born and nobody dead
                self.clock.advance(30)
                self.house.tick()
            self.assertEqual(len(passes), 1)
            self.clock.advance(30)  # five minutes since the pass
            self.house.tick()
            self.assertEqual(len(passes), 2)
            self.clock.advance(30)
            agent = self.seated("newborn")  # a birth, whoever made it
            self.house.tick()
            self.assertEqual(len(passes), 3)
            self.clock.advance(30)
            self.house.tick()
            self.assertEqual(len(passes), 3)
            self.house.kill(agent, "displaced", "a death, whoever made it")
            self.clock.advance(30)
            self.house.tick()
            self.assertEqual(len(passes), 4)

    def test_a_pass_the_probe_box_put_off_is_tried_again_on_the_next_tick(self):
        passes = []
        busy = [True]

        def turn(what):
            from contextlib import contextmanager

            @contextmanager
            def held():
                yield not busy[0]
            return held()

        with patch.object(self.house, "_births", side_effect=lambda rules: passes.append(1)), \
                patch.object(self.house, "_probe_turn", side_effect=turn):
            self.house.tick()
            self.assertEqual(passes, [])
            busy[0] = False
            self.clock.advance(30)
            self.house.tick()
            self.assertEqual(passes, [1])


    def test_a_births_pass_never_runs_beside_the_foundrys_step(self):
        passes = []
        self.house.settings.box_wait_seconds = 0.05
        with patch.object(self.house, "_births", side_effect=lambda rules: passes.append(1)):
            self.house._foundry_turn.acquire()  # the foundry's step, labelling births on the House lane
            try:
                self.house.tick()
            finally:
                self.house._foundry_turn.release()
            self.assertEqual(passes, [])
            self.clock.advance(30)
            self.house.tick()  # still due: the pass it gave up was no pass
            self.assertEqual(passes, [1])


class TheDisplacementScan(SeatCase):
    def test_a_pass_asks_each_question_once_and_answers_as_a_fresh_scan_does(self):
        young = [self.house.spawn(f"young{i}", "test-family", BUYER, reason="a House mutation") for i in range(3)]  # rung 0
        self.seated("idle")
        self.clock.advance(4000)
        questions = [dict(evidenced=True), dict(evidenced=True, exclude=(young[0].id,)), dict(evidenced=True, exclude=(young[1].id,)),
                     dict(), dict(evidenced=True, specialty=young[0].specialty), dict(evidenced=True)]
        fresh = [[row[-1].id for row in self.house._displaceable(self.rules, **q)] for q in questions]
        self.assertTrue(any(fresh))
        built = []
        standings = self.house.standings
        with patch.object(self.house, "standings", side_effect=lambda: built.append(1) or standings()):
            self.house._scan_memo = {"thread": threading.get_ident(), "roster": None, "scans": {}}
            try:
                kept = [[row[-1].id for row in self.house._displaceable(self.rules, **q)] for q in questions]
                self.assertEqual(kept, fresh)
                self.assertEqual(len(built), 3)  # evidenced on the league, not evidenced, evidenced on one desk
                self.house.kill(young[2], "credits", "a death in the pass")  # the roster moved: asked afresh
                after = [row[-1].id for row in self.house._displaceable(self.rules, evidenced=True)]
                self.assertEqual(len(built), 4)
            finally:
                self.house._scan_memo = None
        self.assertNotIn(young[2].id, after)
        self.assertEqual(after, [row[-1].id for row in self.house._displaceable(self.rules, evidenced=True)])
        self.assertTrue(after)

    def test_one_displacement_a_desk_a_minute_whatever_the_tick(self):
        young = self.house.spawn("young", "test-family", BUYER, reason="a House mutation")
        self.clock.advance(600)
        self.assertEqual(self.house.settings.tick_seconds, 30)
        self.house._desk_displaced[young.specialty] = self.clock() - 45  # a tick and a half ago
        self.assertIsNone(self.house._weakest(self.rules, evidenced=True))
        self.house._desk_displaced[young.specialty] = self.clock() - 61
        self.assertEqual(self.house._weakest(self.rules, evidenced=True).id, young.id)


class StepsBesideTheTick(HouseCase):
    def test_research_is_scheduled_beside_the_tick_once_a_minute(self):
        calls = []
        with patch.object(self.house, "_schedule_research",
                          side_effect=lambda open_for_business: calls.append((threading.get_ident(), open_for_business))):
            self.house.tick()
            self.house.wait(10)
            self.clock.advance(30)
            self.house.tick()
            self.house.wait(10)
            self.assertEqual(len(calls), 1)
            self.clock.advance(30)
            self.house.tick()
            self.house.wait(10)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(ident != threading.get_ident() for ident, _ in calls))
        self.assertEqual({flag for _, flag in calls}, {True})

    def test_the_scheduler_queues_what_is_due_and_closes_a_dead_agents_session(self):
        alive = self.seated("alive")
        dead = self.seated("dead")
        job = self.house.research_jobs.enqueue(dead.id, self.house._generation(dead.id))
        self.house.kill(dead, "displaced", "test")
        queued = []
        with patch.object(self.house, "research_due", side_effect=lambda agent: agent.id == alive.id), \
                patch.object(self.house, "queue_research", side_effect=lambda agent: queued.append(agent.id) or True):
            self.assertEqual(self.house._schedule_research(True), 1)
            self.assertEqual(self.house._schedule_research(False), 0)
        self.assertEqual(queued, [alive.id])
        self.assertEqual(self.house.research_jobs.get(job["session"])["status"], "cancelled")

    def test_the_foundry_steps_beside_the_tick_once_a_minute_with_its_own_standings_table(self):
        steps = []

        def step(*, open_for_business):
            memo = self.house._lane_memos.get(threading.get_ident())
            steps.append((threading.get_ident(), memo is not None))

        self.house.hypotheses = SimpleNamespace(tick=step, stats=lambda: {}, enabled=lambda: False, replaces_refill=lambda: False,
                                                inventory=lambda: [], evaluations=lambda: {})
        for _ in range(3):
            self.house.tick()
            self.house.wait(10)
            self.clock.advance(30)
        self.assertEqual(len(steps), 2)  # at 0 s and 60 s
        self.assertTrue(all(ident != threading.get_ident() and memo for ident, memo in steps))
        self.assertEqual(self.house._lane_memos, {})

    def test_the_site_is_checkpointed_once_a_minute(self):
        published = []
        self.house.publisher = SimpleNamespace(publish=lambda house: published.append(self.clock()))
        for _ in range(4):
            self.house.tick()
            self.clock.advance(30)
        self.assertEqual(len(published), 2)

    def test_the_house_lane_writes_no_job_rows(self):
        with patch.object(self.house, "_schedule_research", return_value=0):
            self.house.tick()
            self.house.wait(10)
        keys = {e.payload.get("key") for e in self.house.ledger.iter(kinds="ops.job")}
        self.assertFalse(any(str(k).startswith("house:") for k in keys))
        self.assertEqual(health(self.house)["tick_steps"]["background"]["house"]["key"], "house:research")


class ASimulatedVenue(HouseCase):
    def new_house(self, **kw):
        from league.economy import load_game
        from league.sandbox import LocalSandbox

        self.shadow = SimulatedVenue("kalshi-shadow", family="kalshi")
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        return House(Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker, "kalshi-shadow": self.shadow},
                     sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock, game=game,
                     settings=Settings(mark_every_seconds=10 ** 6, research=False))

    def test_a_simulated_venue_is_passed_once_a_minute_and_a_real_one_every_tick(self):
        polled = {"alpaca-paper": 0, "kalshi-shadow": 0}
        books = self.house.books

        def counter(name):
            real = books[name].poll
            return lambda: polled.__setitem__(name, polled[name] + 1) or real()

        with patch.object(books["alpaca-paper"], "poll", side_effect=counter("alpaca-paper")), \
                patch.object(books["kalshi-shadow"], "poll", side_effect=counter("kalshi-shadow")):
            before = dict(polled)
            walked = self.shadow.walked
            for _ in range(4):  # 0, 30, 60, 90 s
                self.house.tick()
                self.clock.advance(30)
        # The first tick also marks (and polls) every book; after it the poll step's own passes are all.
        self.assertEqual(polled["alpaca-paper"] - before["alpaca-paper"], 4 + 1)
        self.assertEqual(polled["kalshi-shadow"] - before["kalshi-shadow"], 2 + 1)  # at 0 s and 60 s
        self.assertEqual(self.shadow.walked - walked, 2)
        self.assertEqual(health(self.house)["tick_steps"]["last"]["steps"]["poll:kalshi-shadow"] >= 0, True)

    def test_a_simulated_venue_with_no_working_order_is_not_re_quoted(self):
        self.house.tick()
        self.assertEqual(self.house.books["kalshi-shadow"].open_orders(), [])
        self.assertEqual(self.shadow.advanced, 0)
        with patch.object(self.house.books["kalshi-shadow"], "open_orders", return_value=[object()]):
            self.clock.advance(60)
            self.house.tick()
        self.assertEqual(self.shadow.advanced, 1)


class RestartsCounted(HouseCase):
    def at(self, iso):
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()

    def restart(self):
        self.house.close(wait=None)
        self.house = self.new_house()

    def test_health_counts_the_last_days_restarts_and_names_the_last_start(self):
        self.clock.now = self.at("2026-09-22T12:00:00Z")
        self.restart()  # two days ago
        self.clock.now = self.at("2026-09-23T15:00:00Z")  # a Wednesday, inside the regular session
        self.restart()
        self.clock.now = self.at("2026-09-23T22:30:00Z")  # after the close
        self.restart()
        self.clock.now = self.at("2026-09-24T12:00:00Z")
        self.restart()
        self.house.tick()
        out = health(self.house)
        self.assertEqual(out["restarts_24h"], 3)
        self.assertEqual(out["restarts_24h_in_session"], 1)
        self.assertEqual(out["last_start"]["at"], "2026-09-24T12:00:00.000Z")
        self.assertEqual(out["last_start"]["release"], Path(__file__).resolve().parents[2].name)


class SessionsAcrossARestart(HouseCase):
    """A session in flight at a restart resumes (`durable_research`), or it is lost and a warning names it."""

    class Researcher:
        def __init__(self, reasons, candidate=None):
            self.reasons, self.candidate, self.lab = dict(reasons), candidate, None

        def research(self, agent, standing, *, session):
            out = Pass(agent.id)
            out.reason = self.reasons[session]
            out.candidate = self.candidate
            return out

    def in_flight(self, agent):
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.research_jobs.start(job["session"], {"agent": asdict(self.house.registry.get(agent.id)), "standing": {}})
        return job["session"]

    def restart(self):
        self.house.close(wait=None)
        self.house = self.new_house()

    def test_a_session_lost_to_a_restart_is_a_warning_that_names_it_and_gives_the_agent_its_turn_back(self):
        lost, kept, fine = self.seated("lost"), self.seated("kept"), self.seated("fine")
        sessions = {lost.id: self.in_flight(lost), kept.id: self.in_flight(kept), fine.id: self.in_flight(fine)}
        self.restart()
        self.assertEqual(health(self.house)["restart_research"]["at_start"], 3)
        self.house.researcher = self.Researcher({sessions[lost.id]: "provider: campaign_post_unconfirmed",
                                                 sessions[kept.id]: "tool outcome unconfirmed: replay",
                                                 sessions[fine.id]: "finished"})
        for agent in (lost, kept, fine):
            with patch.object(self.house, "research_interval_hours", return_value=3.0):
                self.house.research(self.house.registry.get(agent.id))
        self.assertEqual(self.house.research_jobs.get(sessions[lost.id])["status"], "cancelled")
        self.assertEqual(self.house.research_jobs.get(sessions[kept.id])["status"], "cancelled")
        self.assertEqual(self.house.research_jobs.get(sessions[fine.id])["status"], "done")
        # Its turn comes back as a broken session's does: due again PROVIDER_RETRY_SECONDS on, not an interval on.
        self.assertAlmostEqual(self.house._state["last_research"][lost.id], self.clock() - (3.0 * 3600 - PROVIDER_RETRY_SECONDS))
        self.assertAlmostEqual(self.house._state["last_research"][fine.id], self.clock())
        self.house.tick()
        told = warnings(self.house, "research sessions lost to the restart")
        self.assertEqual(len(told), 1)  # one warning a tick, naming each
        self.assertIn(sessions[lost.id], told[0]["text"])
        self.assertIn(sessions[kept.id], told[0]["text"])
        self.assertNotIn(sessions[fine.id], told[0]["text"])
        self.assertEqual(sorted(told[0]["sessions"]), sorted([sessions[lost.id], sessions[kept.id]]))
        block = health(self.house)["restart_research"]
        self.assertEqual((block["at_start"], block["resumed"], block["lost_count"], block["waiting"]), (3, 1, 2, []))
        self.assertTrue(all(row["began_before_start"] for row in block["lost"]))
        self.clock.advance(30)
        self.house.tick()
        self.assertEqual(len(warnings(self.house, "research sessions lost to the restart")), 1)  # told once

    def test_a_lost_session_that_recovered_its_candidate_is_named_but_counts_as_its_pass(self):
        agent = self.seated("recovered")
        session = self.in_flight(agent)
        self.restart()
        self.house.researcher = self.Researcher({session: "tool outcome unconfirmed: replay"}, candidate={"code": BUYER})
        with patch.object(self.house, "_commit_research", return_value=None), patch.object(self.house, "_trace_adoption"):
            self.house.research(self.house.registry.get(agent.id))
        self.assertEqual(self.house.research_jobs.get(session)["status"], "done")
        self.assertAlmostEqual(self.house._state["last_research"][agent.id], self.clock())
        self.house.tick()
        told = warnings(self.house, "research session lost to the restart", session)
        self.assertEqual(len(told), 1)
        self.assertIn("its retained candidate recovered", told[0]["text"])

    def test_a_session_whose_candidate_commit_a_restart_interrupted_is_named(self):
        agent = self.seated("committing")
        session = self.in_flight(agent)
        self.house.research_jobs.ready(session, {"agent": agent.id})
        self.house.research_jobs.applying(session)
        self.restart()
        self.house.researcher = self.Researcher({})
        self.house.research(self.house.registry.get(agent.id))
        self.house.tick()
        told = warnings(self.house, "lost to the restart", session, "candidate commit unconfirmed")
        self.assertEqual(len(told), 1)


class TheReviewOfH5(HouseCase):
    """The adversarial review of #297 (Sept 25, 2026): what the House lane and a thirty-second tick broke."""

    def test_a_job_the_house_lane_lands_while_the_tick_asks_about_merton_does_not_fail_the_tick(self):
        # The tick asked "is a Merton role running?" by walking `_jobs` live. Since H5 the House lane queues
        # research beside it (`_schedule_research` -> `_background`), and a key added mid-walk raised
        # "dictionary changed size during iteration": a failed tick, and an error alert inside a deploy's watch.
        started = []
        self.house.merton = SimpleNamespace(due=lambda: ["teacher"], run=lambda role: started.append(role),
                                            follow=lambda: None)
        jobs = self.house._jobs

        class Landing:
            """A finished Merton job, asked whether it is alive while the lane lands a research job."""

            def is_alive(self):
                jobs.setdefault("research:newcomer", threading.Thread(target=lambda: None))
                return False

        jobs["merton:auditor"] = Landing()
        with patch.object(self.house.pacer, "may_spend", return_value=True):  # today's frontier allowance is open
            self.house.tick()
        self.house.wait(10)
        self.assertEqual(started, ["teacher"])
