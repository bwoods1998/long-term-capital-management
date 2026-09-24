"""R5's drain, completed (Sept 24, 2026): a probe waiting to go back to practice only exits.

Evidence. Deploy D (18:43:49Z) put `allocator.family_probe` live: a probe on a losing family goes back
to practice once it is flat, and an Alpaca probe holding a coin, a stock or an option is never sold
for it. krasker-14, an $80 options probe on options-pullback (19 active blocks, growth -0.383), held a
contract and waited -- and bought a second real contract ($15) at 18:52:30Z, nine minutes later. The
allocator lent it nothing more, but nothing held its entries. The House now holds a waiting probe's
entries the way an agent holds its own (X1 `pause_entries`: buys held at the wake, resting buys
cancelled, sells go on), and releases the hold when the allocator no longer reports the probe waiting.

The adversarial review of the hold (Sept 24, 2026): a pass that cannot read the gate, the family's record or
the probe's evidence lists nobody waiting, and the hold was released for it; house.json, saved at the end of
the tick, was the only record of which pauses were the House's; research's pause during the hold was
refused and then lifted by the House's release; a probe that paused itself could resume while it waited;
the rows were written outside the lifecycle lock that research's own controls take; the hold stood for
good while the allocator was off; its cancels said "its own pause_entries"; and the seat market read it
as the agent's own pause. Each has a test below that fails without its fix.
"""

import threading
from decimal import Decimal
from unittest.mock import patch

from league import allocator
from league.book import Intent
from league.house import House
from league.ledger import now_iso
from league.tests.test_allocator import IDLE, HouseCaseReal
from league.tests.test_entry_controls import ControlCase
from league.tests.test_family_probe import ForwardBlocks
from league.tests.test_order_guards import RESTER
from league.venues import instrument_for

D = Decimal


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

    def test_a_sell_decided_before_the_hold_still_goes_out(self):
        """A hold made while a wake is in flight moves no generation (a pause restates the strategy in force): the wake is
        not dropped at the batch, and its sell reaches the book."""
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.clock.advance(301)
        outcome = self.house.wake(agent)  # it decides to sell
        self.assertEqual([i.side for i in outcome["intents"]], ["sell"])
        self.house._hold_draining_probes(self.waiting(agent))  # the pass holds it before the batch goes out
        submitted = len(self.broker.submitted)
        self.assertEqual([o.status for o in self.house._submit_wakes("alpaca-paper", [outcome])], ["filled"])
        self.assertEqual([order.side for order in self.broker.submitted[submitted:]], ["sell"])
        self.assertEqual(book.account(agent.id).holdings, {})

    # -- the adversarial review of the hold (Sept 24, 2026) ------------------------------------------------------------

    def test_a_house_row_is_the_houses_whatever_house_json_kept(self):
        """house.json is saved at the end of a tick, many steps after the pass: a restart in between kept the House's row
        and lost its `drain_holds` entry, and the hold then read as the probe's own pause -- never released by the House."""
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.house._state["drain_holds"] = {}  # the House restarted from a house.json saved before the row
        self.assertIn("the House holds your entries", self.house._control_refusal(agent, "resume_entries"))
        self.house._hold_draining_probes(self.waiting(agent))  # still waiting: nothing new
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries"])
        self.house._hold_draining_probes({})  # back to practice
        self.assertIsNone(self.house.registry.entries_paused(agent.id))
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries", "resume_entries"])
        self.assertEqual(self.house._state["drain_holds"], {})

    def test_a_hold_that_cannot_be_written_costs_the_others_theirs(self):
        """A pass that stopped at one probe's row lost the `drain_holds` entries of the probes held before it."""
        first, second = self.seated("buyer"), self.seated("zeta")
        append = self.house.ledger.append

        def failing(kind, payload, **kw):
            if kind == "agent.strategy" and kw.get("agent") == second.id:
                raise OSError("disk I/O error")
            return append(kind, payload, **kw)

        with patch.object(self.house.ledger, "append", side_effect=failing):
            self.house._hold_draining_probes(self.waiting(first, second))  # no exception: the next pass tries again
        self.assertEqual(self.house.registry.entries_paused(first.id)["session"], House.DRAIN_SESSION)
        self.assertEqual(sorted(self.house._state["drain_holds"]), [first.id])
        self.assertTrue([e for e in self.house.ledger.iter(kinds="ops.alert") if second.id in str(e.payload.get("text"))])
        self.house._hold_draining_probes(self.waiting(second))  # the next pass: the second is held, the first went back
        self.assertEqual(self.house.registry.entries_paused(second.id)["session"], House.DRAIN_SESSION)
        self.assertIsNone(self.house.registry.entries_paused(first.id))

    def test_a_research_pause_during_the_hold_is_its_own_and_outlasts_it(self):
        """A pause research asked while the House held the entries was refused as "already paused", and the House's
        release then opened them: the agent's own pause, resumed by the House."""
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.assertEqual(self.apply(agent, "pause_entries"), ["pause_entries"])
        paused = self.house.registry.entries_paused(agent.id)
        self.assertEqual(paused["session"], "s1")
        self.assertEqual(self.strategy_rows(agent)[-1]["was"]["session"], House.DRAIN_SESSION)
        self.assertEqual(self.apply(agent, "resume_entries", n=1), [])  # still waiting: the House holds it
        self.house._hold_draining_probes({})  # the drain ends: its own pause is left as it is
        self.assertEqual([r["session"] for r in self.strategy_rows(agent)], [House.DRAIN_SESSION, "s1"])
        self.assertEqual(self.house.registry.entries_paused(agent.id)["session"], "s1")
        self.assertEqual(self.house._state["drain_holds"], {})

    def test_a_waiting_probe_that_paused_itself_may_not_resume_until_the_drain_ends(self):
        """Its own pause holds it, so the House writes no row -- and research could lift it while it still waited, its
        buys going through until the next pass held them again (wakes run before the pass in a tick)."""
        agent = self.seated()
        self.apply(agent, "pause_entries")
        self.house._hold_draining_probes(self.waiting(agent))
        self.assertEqual(self.apply(agent, "resume_entries", n=1), [])
        (reason,) = self.not_applied(agent)
        self.assertIn("the House holds your entries", reason)
        self.house._hold_draining_probes({})
        self.assertEqual([r["session"] for r in self.strategy_rows(agent)], ["s1"])  # no row of the House's either way
        self.assertEqual(self.apply(agent, "resume_entries", n=2), ["resume_entries"])  # back in practice: its own to lift

    def test_the_hold_is_written_under_the_lifecycle_lock(self):
        """Research applies its controls on its own thread under the lifecycle lock (`_apply_controls`), and the House's row
        restates the strategy it read: written outside the lock, it could land on an edit made meanwhile and undo it, or on
        a pause research made meanwhile, which the House would then lift as its own."""
        agent = self.seated()
        done = threading.Event()

        def hold():
            self.house._hold_draining_probes(self.waiting(agent))
            done.set()

        with self.house._lifecycle_lock:
            worker = threading.Thread(target=hold)
            worker.start()
            self.assertFalse(done.wait(0.3))
            self.assertIsNone(self.house.registry.entries_paused(agent.id))
        worker.join(10)
        self.assertTrue(done.is_set())
        self.assertEqual(self.house.registry.entries_paused(agent.id)["session"], House.DRAIN_SESSION)

    def test_every_hold_is_released_while_the_allocator_is_off(self):
        """The pass (and the hold after it) runs only while the allocator is on: switched off, nothing drains a probe and
        its hold stood for good, research's resume refused with it."""
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        with patch.object(allocator, "enabled", return_value=False):
            self.house.tick()
        self.assertIsNone(self.house.registry.entries_paused(agent.id))
        self.assertEqual([r["control"] for r in self.strategy_rows(agent)], ["pause_entries", "resume_entries"])
        self.assertEqual(self.house._state["drain_holds"], {})

    def test_the_cancels_at_the_hold_say_the_house_holds_it(self):
        """They said "its own pause_entries: its entries are held until it resumes them" on the order's row."""
        agent = self.seated("rester", RESTER.replace('"wake_minutes": 5', '"wake_minutes": 1440'))
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        (order,) = book.open_orders(agent.id)
        self.house._hold_draining_probes(self.waiting(agent))
        (reason,) = [e.payload["reason"] for e in self.house.ledger.iter(kinds="book.order")
                     if e.payload.get("order_id") == order.order_id and e.payload.get("status") == "cancelled"]
        self.assertIn("the House holds", reason)
        self.assertNotIn("its own pause_entries", reason)

    def test_the_houses_hold_is_not_its_own_pause_to_the_seat_market(self):
        """The House demotes between passes too (an audit's veto after promotion ends on its own thread), and such a
        probe sits on practice under the House's hold until the next pass releases it: a hold older than the displacement
        grace (2 epochs, 12 hours) read as its own pause past it, and its seat could be given away at once
        (`_paused_past`, which displacement and the seat report read)."""
        agent = self.seated()
        self.house._hold_draining_probes(self.waiting(agent))
        self.clock.advance(13 * 3600)
        self.assertFalse(self.house._paused_past(agent, 12 * 3600, self.clock()))
        self.apply(agent, "pause_entries")  # its own, over the hold: counted from now
        self.assertFalse(self.house._paused_past(agent, 12 * 3600, self.clock()))
        self.clock.advance(13 * 3600)
        self.assertTrue(self.house._paused_past(agent, 12 * 3600, self.clock()))


class DrainHoldThroughThePass(ForwardBlocks, HouseCaseReal):
    """The hold as the allocator's pass makes and ends it, on a real (fake) Alpaca book."""

    TABLE = dict(e=1.10, w_paper=1.21, paper_trades=6)

    def strategy_rows(self, agent):
        return [e.payload for e in self.house.ledger.iter(kinds="agent.strategy", agent=agent.id)]

    def held(self):
        """A probe holding BTC on the real book, its family losing, held by the pass."""
        a = self.agent("haghani", code=IDLE)
        with self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        book = self.house.books["alpaca"]
        btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        buy = Intent.new(agent=a.id, instrument=btc, side="buy", quantity=D("0.000125"), reason="test", created_at=now_iso(self.clock))
        self.assertEqual(book.submit([buy])[0].status, "filled")
        self.blocks("alloc-test", *[-0.01] * 6, book="alpaca-paper", code=IDLE)
        with self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.assertEqual(self.house.registry.entries_paused(a.id)["session"], House.DRAIN_SESSION)
        return a, book, btc

    def still_held(self, a):
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertEqual((self.house.registry.entries_paused(a.id) or {}).get("session"), House.DRAIN_SESSION)
        self.assertEqual([r["control"] for r in self.strategy_rows(a)], ["pause_entries"])

    def test_the_pass_holds_a_waiting_probe_and_releases_it_back_in_practice(self):
        a, book, btc = self.held()
        quantity = book.account(a.id).holdings[btc.key].quantity
        sell = Intent.new(agent=a.id, instrument=btc, side="sell", quantity=quantity, reason="its own exit", created_at=now_iso(self.clock))
        self.assertEqual(book.submit([sell])[0].status, "filled")
        with self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertIsNone(self.house.registry.entries_paused(a.id))
        self.assertEqual([r["control"] for r in self.strategy_rows(a)], ["pause_entries", "resume_entries"])

    def test_a_pass_that_cannot_read_the_gate_keeps_the_hold(self):
        """The gate fails closed (`family_unreadable`: nobody seated, nobody demoted) and the pass lists no probe waiting:
        read as "no longer waiting", the hold was released -- the losing family's probe free to buy on real money until
        the next readable pass held it again."""
        a, _, _ = self.held()
        with patch.object(allocator, "fold_demotions", side_effect=OSError("disk I/O error")), self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.assertEqual(self.house.allocator.board()["agents"][a.id]["probe_gate"], "unreadable")
        self.still_held(a)
        with self.evidence_of({a.id: self.TABLE}):
            self.tick()  # read again: waiting, as it was
        self.still_held(a)

    def test_a_pass_that_cannot_read_its_familys_record_keeps_the_hold(self):
        a, _, _ = self.held()
        with patch.object(allocator, "family_record", side_effect=RuntimeError("the tape could not be read")), \
                self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.still_held(a)

    def test_a_pass_that_cannot_read_its_evidence_keeps_the_hold(self):
        a, _, _ = self.held()
        with patch.object(allocator, "evidence", side_effect=RuntimeError("its record is torn")):
            self.tick()
        self.still_held(a)

    def test_a_family_that_turns_releases_the_hold_on_real_money(self):
        a, book, _ = self.held()
        self.blocks("alloc-test", *[0.02] * 6, book="alpaca-paper", code=IDLE)  # its record turns positive
        with self.evidence_of({a.id: self.TABLE}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertIsNone(self.house.registry.entries_paused(a.id))
        self.assertEqual([r["control"] for r in self.strategy_rows(a)], ["pause_entries", "resume_entries"])
