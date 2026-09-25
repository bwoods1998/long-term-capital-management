"""Research runs on outcomes (F2) and a refusal buys research once a day (X2), Sept 25, 2026.

Replayed on the T0 snapshot (the 24 hours to 04:23Z Sept 25; `scripts/gate_replay.py`): 2,566 sessions
for $87.65; 387 `clock` runs ($27.72), 350 of them idle agents re-running every 12 minutes at the
winners' pace; 121 of 122 heartbeats a newborn's first session at age 0; 275 samples of locked winners
retained 4 candidates; 670 refusals were 86 distinct (agent, day, reason) triples and bought 437 prompt
sessions and 107 gate runs; 134 of 204 lesson-triggered rows had only a post-mortem behind them. These
tests pin rules 9-12 of league/research_gate.py under `clock_runs: real_positions`.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from league.research_gate import lesson_arm, lesson_names, lesson_terms, lesson_words, refusal_class, report
from league.tests.test_jev_sensor import GateCase, summary

REFUSED = ("one event may hold at most 25% of the stake: KXBTCD-26SEP2501 would hold $3.80 of this account's $13.27 "
           "(holdings at cost, working buys on every market of the event, and this order; constitution allocator.max_event_share)")
REFUSED_AGAIN = ("one event may hold at most 25% of the stake: KXBTCD-26SEP2502 would hold $4.10 of this account's $13.40 "
                 "(holdings at cost, working buys on every market of the event, and this order; constitution allocator.max_event_share)")


class RealBook:
    """The real-money book an agent is on (`House.book_of`), holding what a test puts in it."""

    real_money = True

    def __init__(self, name="alpaca"):
        self.name, self.accounts, self.orders = name, {}, {}

    def hold(self, agent):
        self.accounts[agent.id] = SimpleNamespace(holdings={"BTC/USD": SimpleNamespace(quantity=1)}, staked=0)

    def seat(self, agent):
        self.accounts[agent.id] = SimpleNamespace(holdings={}, staked=0)

    def account(self, agent_id):
        return self.accounts[agent_id]

    def open_orders(self, agent_id=None):
        return list(self.orders.get(agent_id, []))


class Outcomes(GateCase):
    def f2(self, **settings):
        return self.ready(legacy=False, settings={"clock_runs": "real_positions", "abstain_lock_after": 3, "practice_pause_after": 3,
                                                  "max_skip_hours": 24, "practice_max_skip_hours": 72, "idle_runs": "barren",
                                                  "sample_hours": 6, "lesson_arm": "parity", "refusal_dedupe": True, **settings})

    def win(self, agent, n=3, growth=0.004):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{i}"}, agent=agent.id)
        self.house.standings()

    def on_real_money(self, *agents, holding=True):
        """Put `agents` on a real-money book of their own (`House.book_of`), holding a position or not."""
        book = RealBook()
        for agent in agents:
            (book.hold if holding else book.seat)(agent)
            self.real_books[agent.id] = book
        if not getattr(self, "_patched", False):
            practice, self._patched = self.house.book_of, True
            self.house.book_of = lambda a: self.real_books.get(a.id) or practice(a)
        return book

    def setUp(self):
        super().setUp()
        self.real_books = {}

    def refuse(self, agent, text=REFUSED, book="alpaca-paper"):
        return self.house.ledger.append("book.refused", {"book": book, "reasons": [text]}, agent=agent.id)

    # ----------------------------------------------------------------- rule 9: the clock
    def test_a_practice_winner_no_longer_researches_on_the_clock(self):
        agent = self.f2()
        self.win(agent)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "a positive practice record is not an outcome: it waits for one")
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"], row["record"], row["money"]), ("skip", "nothing_new:winner", "winner", "practice"))

    def test_a_real_agent_with_a_position_keeps_its_clock_and_one_without_waits(self):
        holder, empty = self.f2(), self.seated("empty")
        self.house._state["last_research"][empty.id] = self.clock()
        self.on_real_money(holder)
        book = self.on_real_money(empty, holding=False)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(holder))
        self.assertEqual((self.gates(holder.id)[-1]["reason"], self.gates(holder.id)[-1]["money"]), ("clock", "real"))
        self.assertFalse(self.house.research_due(empty), "real money, nothing held, nothing refused: it waits for evidence")
        self.assertEqual(self.gates(empty.id)[-1]["reason"], "nothing_new:unproven")
        book.orders[empty.id] = [{"order_id": "o1"}]
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(empty), "a working order on real money is a position to manage")
        self.assertEqual(self.gates(empty.id)[-1]["reason"], "clock")

    def test_a_real_agent_that_met_a_refusal_again_runs_on_the_clock_not_on_the_refusal(self):
        agent = self.f2()
        self.on_real_money(agent, holding=False)
        self.clock.advance(60)
        self.refuse(agent, book="alpaca")
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent), "the first refusal of its kind today is news (the fast path)")
        self.assertEqual(self.gates()[-1]["reason"], "refusal")
        self.researched(agent)
        self.refuse(agent, REFUSED_AGAIN, book="alpaca")
        self.clock.advance(60)
        self.assertFalse(self.house.research_due(agent), "the same rule refused it again today: no prompt session")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "but a real agent that met a refusal since its last session keeps its clock")
        row = self.gates()[-1]
        self.assertEqual((row["reason"], row["money"], row["refusals_deduped"]), ("clock", "real", 1))

    def test_the_heartbeat_is_three_days_on_practice_and_one_on_real_money(self):
        practice = self.f2()
        real = self.seated("real")
        self.house._state["last_research"][real.id] = self.clock()
        self.on_real_money(real, holding=False)
        self.clock.advance(25 * 3600)
        self.assertTrue(self.house.research_due(real))
        self.assertEqual(self.gates(real.id)[-1]["reason"], "heartbeat")
        self.assertFalse(self.house.research_due(practice), "a practice agent's heartbeat is 72 hours")
        self.clock.advance(48 * 3600)
        self.assertTrue(self.house.research_due(practice))
        self.assertEqual(self.gates(practice.id)[-1]["reason"], "heartbeat")

    def test_a_newborn_trades_before_it_researches(self):
        """121 of the 122 heartbeats of the day to T0 were a newborn's first session at age 0: an agent
        that never researched has `last` 0, and 24 hours had always passed since the epoch."""
        self.f2()
        newborn = self.seated("newborn")
        self.assertNotIn(newborn.id, self.house._state["last_research"])
        self.assertFalse(self.house.research_due(newborn))
        self.assertEqual(self.gates(newborn.id)[-1]["reason"], "nothing_new:unproven")
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue"}, agent=newborn.id)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(newborn), "its first fill is its first research")
        self.assertEqual(self.gates(newborn.id)[-1]["trigger"], "book.fill")

    def test_a_replay_only_agent_keeps_its_clock(self):
        self.f2()
        rung0 = self.house.spawn("rung-zero", "test-family", self.seated("donor").code, reason="a House mutation")
        self.house._state["last_research"][rung0.id] = self.clock()
        self.assertEqual(self.house.evaluator.rung(rung0.id), 0)
        self.clock.advance(self.house.research_interval_hours(rung0) * 3600)
        self.assertTrue(self.house.research_due(rung0), "on rung 0 research is its only way up")
        self.assertEqual(self.gates(rung0.id)[-1]["reason"], "clock")

    def test_an_idle_program_researches_on_its_barren_outcome_not_on_the_clock(self):
        agent = self.f2()
        self.house._state["idle"][agent.id] = {"barren": 12, "shut": 0, "offered": 4}
        self.clock.advance(self.house.research_interval_hours(agent) * 3600)
        self.assertFalse(self.house.research_due(agent), "idle already when the rule began: no burst at deploy")
        self.assertEqual(self.gates()[-1]["reason"], "nothing_new:idle")
        self.house._state["idle"][agent.id] = {"barren": 21, "shut": 0, "offered": 4}
        self.clock.advance(60)
        self.assertFalse(self.house.research_due(agent), "nine more barren wakes are not yet an outcome")
        self.house._state["idle"][agent.id] = {"barren": 22, "shut": 0, "offered": 4}
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent), "ten more wakes with live markets and nothing done are")
        self.assertIn("barren:10", self.gates()[-1]["triggers"])
        self.researched(agent)
        summary(self.house.ledger, agent.id, candidate=True, trials=1)
        self.house._state["idle"].pop(agent.id)  # its new code was adopted: a fresh count (`_commit_research`)
        self.house._state["idle"][agent.id] = {"barren": 0, "shut": 40, "offered": 0}
        self.clock.advance(self.house.research_interval_hours(agent) * 3600)
        if self.house.research_due(agent):  # the market closing is the existing `market` trigger, once
            self.assertEqual(self.gates()[-1]["trigger"], "market")
            self.researched(agent)
        self.house._state["idle"][agent.id] = {"barren": 0, "shut": 80, "offered": 0}
        self.clock.advance(self.house.research_interval_hours(agent) * 3600)
        self.assertFalse(self.house.research_due(agent), "a closed market is the calendar, not an outcome")

    # ----------------------------------------------------------------- rule 10: the pause
    def test_a_practice_agent_pauses_after_three_empty_sessions_until_its_next_fill(self):
        agent = self.f2()
        self.win(agent)
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.house.ledger.append("book.settle", {"book": "alpaca-paper", "pnl": "1.00"}, agent=agent.id)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "under rule 7 a settlement woke it; paused, only a fill does")
        self.assertEqual(self.gates()[-1]["reason"], "practice_pause:3")
        self.refuse(agent)
        self.clock.advance(60)
        self.assertFalse(self.house.research_due(agent), "nor does a refusal, on the fast path or the gate's")
        self.clock.advance(80 * 3600)
        self.assertFalse(self.house.research_due(agent), "nor the heartbeat")
        self.assertEqual(self.house.jev_floor.gate.lock_profile(agent), "flash_asap")
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue"}, agent=agent.id)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "book.fill")

    def test_a_real_agent_keeps_the_lock_a_settlement_still_wakes(self):
        agent = self.f2()
        self.on_real_money(agent, holding=False)
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.house.ledger.append("book.settle", {"book": "alpaca", "pnl": "1.00"}, agent=agent.id)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual((self.gates()[-1]["trigger"], self.gates()[-1]["money"]), ("book.settle", "real"))

    def test_a_skip_is_drawn_for_the_sample_once_in_six_hours_not_once_an_interval(self):
        agent = self.f2(sample_percent=100)
        self.rng.random = lambda: 0.0
        runs = 0
        for _ in range(8):  # 24 hours at the 3-hour interval
            self.clock.advance(self.interval)
            runs += bool(self.house.research_due(agent))
        samples = [g for g in self.gates() if g["decision"] == "sample"]
        self.assertEqual(runs, len(samples))
        self.assertLessEqual(len(samples), 5, "at most one draw per six-hour window (four windows, one at the edge)")
        self.assertGreaterEqual(len(samples), 3)

    # ----------------------------------------------------------------- rule 11: refusals
    def test_a_refusal_buys_research_once_per_agent_reason_and_day(self):
        agent = self.f2()
        self.clock.advance(120)
        self.refuse(agent)
        self.assertTrue(self.house.research_due(agent), "the fast path: a new refusal is news")
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"], row["trigger"]), ("run", "refusal", "book.refused"))
        self.researched(agent)
        self.clock.advance(120)
        self.refuse(agent, REFUSED_AGAIN)
        self.assertFalse(self.house.research_due(agent), "the same rule on another event and other amounts: the same reason")
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "and the gate does not count it as a trigger either")
        self.refuse(agent, "insufficient desk cash: need 5.00 have 1.20")
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent), "another reason is news")
        self.researched(agent)
        self.clock.advance(86400)
        self.refuse(agent)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent), "and the first reason is news again the next UTC day")
        self.assertEqual(report(self.house.ledger)["refusals_deduped"], 1)
        self.assertEqual(self.house.jev_floor.state.data["totals"]["refusals_deduped"], 1)

    def test_the_refusal_class_takes_out_what_varies(self):
        self.assertEqual(refusal_class(REFUSED), refusal_class(REFUSED_AGAIN))
        self.assertNotEqual(refusal_class(REFUSED), refusal_class("insufficient desk cash: need 5.00 have 1.20"))
        self.assertEqual(refusal_class("insufficient desk cash: need 5.00 have 1.20"), refusal_class("insufficient desk cash: need 12.40 have 0.07"))
        self.assertEqual(refusal_class("the alpaca book is frozen until it reconciles: cash differs by 0.0108"),
                         "the alpaca book is frozen until it reconciles: cash differs by #")

    def test_without_the_gate_every_new_refusal_is_news_as_before(self):
        agent = self.f2()
        self.house.jev_floor = None
        self.clock.advance(120)
        self.refuse(agent)
        self.assertTrue(self.house.research_due(agent))
        self.house._state["last_research"][agent.id] = self.clock()
        self.clock.advance(120)
        self.refuse(agent, REFUSED_AGAIN)
        self.assertTrue(self.house.research_due(agent))

    # ----------------------------------------------------------------- rule 12: lessons
    def named(self, arm):
        """A seated agent in the given arm of the teacher's comparison (`lesson_arm`)."""
        for n in range(40):
            agent = self.seated(f"learner-{n}")
            self.house._state["last_research"][agent.id] = self.clock()
            if lesson_arm(agent.id) == arm:
                return agent
        raise AssertionError(arm)

    def test_a_post_mortem_is_not_a_lesson_and_the_teacher_names_desks_by_their_short_name(self):
        self.f2()
        agent = self.named("lesson")
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.house.ledger.append("playbook.entry", {"title": "Post-mortem: x", "source": "graveyard",
                                                    "text": f"x (family {agent.family}, niche {agent.niche}) died of displaced."})
        self.clock.advance(60)
        self.assertFalse(self.house.research_due(agent), "a desk-mate's post-mortem is the graveyard's, not a lesson")
        short = agent.niche.split("-", 1)[1]
        self.house.ledger.append("playbook.entry", {"title": "Lesson: 2026-09-25-x", "source": "teacher",
                                                    "text": f"Audit {short} descendants before forking another."})
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates(agent.id)[-1]["trigger"], "lesson")

    def test_the_control_arm_is_not_woken_by_a_lesson(self):
        self.f2()
        control = self.named("control")
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(control))
        self.house.ledger.append("playbook.entry", {"title": "Lesson: 2026-09-25-y", "source": "teacher",
                                                    "text": f"What {control.family} keeps doing wrong."})
        self.clock.advance(60)
        self.assertFalse(self.house.research_due(control), "the odd half is the teacher's control")
        self.assertTrue(self.house.jev_floor.state.data.get("lesson_arm_since"))

    def test_lesson_words_match_on_word_boundaries(self):
        words = lesson_words("mullins-6", "kalshi-weather", "kalshi-weather", "weather-favourites-no")
        self.assertEqual(words, {"mullins-6", "kalshi-weather", "weather", "weather-favourites-no"})
        self.assertEqual(lesson_words("london-1", "kalshi-open"), {"london-1", "kalshi-open"}, "'open' is an ordinary word")
        entry = SimpleNamespace(payload={"source": "teacher", "title": "Lesson", "text": "The kalshi-crypto-15m-lab family; mullins-60 lost."})
        self.assertIn("crypto-15m", lesson_terms(entry))
        self.assertTrue(lesson_names({"crypto-15m"}, entry))
        self.assertFalse(lesson_names({"mullins-6"}, entry), "mullins-60 is not mullins-6")
        self.assertFalse(lesson_names({"crypto-15m"}, SimpleNamespace(payload={**entry.payload, "source": "graveyard"})))


if __name__ == "__main__":
    unittest.main()
