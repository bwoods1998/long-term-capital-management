"""R5's drain, completed (Sept 24, 2026): a probe waiting to go back to practice only exits.

Evidence. Deploy D (18:43:49Z) put `allocator.family_probe` live: a probe on a losing family goes back
to practice once it is flat, and an Alpaca probe holding a coin, a stock or an option is never sold
for it. krasker-14, an $80 options probe on options-pullback (19 active blocks, growth -0.383), held a
contract and waited -- and bought a second real contract ($15) at 18:52:30Z, nine minutes later. The
allocator lent it nothing more, but nothing held its entries. The House now holds a waiting probe's
entries the way an agent holds its own (X1 `pause_entries`: buys held at the wake, resting buys
cancelled, sells go on), and releases the hold when the allocator no longer reports the probe waiting.
"""

from league.house import House
from league.tests.test_entry_controls import ControlCase
from league.tests.test_order_guards import RESTER


class DrainHold(ControlCase):
    def waiting(self, *agents):
        return {"probes_waiting_flat": [a.id for a in agents]}

    def test_a_waiting_probe_has_its_entries_held_by_a_house_row(self):
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        paused = self.house.registry.entries_paused(agent.id)
        self.assertEqual(paused["session"], House.DRAIN_SESSION)
        (row,) = self.strategy_rows(agent)
        self.assertEqual((row["control"], row["entries"], row["session"]), ("pause_entries", "paused", House.DRAIN_SESSION))
        self.assertIn("losing", row["note"])
        self.assertIn(agent.id, self.house._state["drain_holds"])
        current = self.house.registry.get(agent.id)
        self.assertEqual((current.code, current.params), (agent.code, agent.params))  # the strategy in force is unchanged

    def test_its_buys_are_held_at_the_wake_and_its_exits_go_on(self):
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        submitted = len(self.broker.submitted)
        self.house._hold_draining_probes(self.waiting(agent))
        self.clock.advance(301)
        self.house.tick()  # it sells what it holds; no new buy
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual([order.side for order in self.broker.submitted[submitted:]], ["sell"])

    def test_its_resting_buys_are_cancelled_when_the_hold_is_made(self):
        agent = self.seated("rester", RESTER.replace('"wake_minutes": 5', '"wake_minutes": 1440'))
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        (order,) = book.open_orders(agent.id)
        self.house._hold_draining_probes(self.waiting(agent))
        self.assertEqual(book.open_orders(agent.id), [])

    def test_the_hold_is_released_once_the_probe_is_no_longer_waiting(self):
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.house._hold_draining_probes(self.waiting(agent))  # the next pass: nothing new
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries"])
        self.house._hold_draining_probes({})  # it went back to practice (or its family turned)
        self.assertIsNone(self.house.registry.entries_paused(agent.id))
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries", "resume_entries"])
        self.assertEqual(self.house._state["drain_holds"], {})

    def test_its_own_pause_is_left_as_it_is(self):
        agent = self.seated()
        self.apply(agent, "pause_entries")  # its own, from research
        self.house._hold_draining_probes(self.waiting(agent))
        self.house._hold_draining_probes({})
        self.assertEqual([r["session"] for r in self.strategy_rows(agent)], ["s1"])  # no House row either way
        self.assertIsNotNone(self.house.registry.entries_paused(agent.id))

    def test_research_cannot_resume_it_while_the_hold_stands(self):
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.assertEqual(self.apply(agent, "resume_entries", n=1), [])
        (reason,) = self.not_applied(agent)
        self.assertIn("the House holds your entries", reason)
        self.assertIsNotNone(self.house.registry.entries_paused(agent.id))
        self.house._hold_draining_probes({})
        self.assertEqual(self.house._control_refusal(agent, "resume_entries"), "")

    def test_a_dead_agent_is_not_held_and_its_hold_is_dropped(self):
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.house.kill(agent, "evidence", "test")
        self.house._hold_draining_probes({})
        self.assertEqual(self.house._state["drain_holds"], {})
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries"])  # no row for the dead
