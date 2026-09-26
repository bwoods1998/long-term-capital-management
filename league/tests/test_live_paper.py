"""Paper route evidence survives ambiguous dispatches, uneven fills and session changes.

These use invented quotes and the fake venue only. A proof owns only contracts identified by its own order ids.
"""

import datetime as dt
from decimal import Decimal as D

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.decider import InlineDecider
    from league.live.families import MemoryFamilies
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, at


class PaperOnlyProof(LiveCase):
    def paper_only(self):
        # Match service.options_live: no real client or book exists while real money is off.
        self.families = MemoryFamilies()
        self.live = OptionsLive(self.root, market=self.market, real=None, paper=self.paper,
                                families=self.families, decider=InlineDecider(), real_money=False,
                                config={"require_paper_proof": True}, clock=self.clock, record=self.ledger)
        return self.live

    def test_route_is_proved_with_no_real_client_book_or_eligible_family(self):
        live = self.paper_only()
        self.assertIsNone(live.book)
        self.assertIn("SPY", live._roots())
        self.run_to(9, 45)
        self.assertTrue(live.proof.passed(), live.proof.status())
        self.assertEqual(len(self.paper.sent), 2)
        self.assertEqual(self.venue.sent, [])
        self.assertFalse(live.real_money)
        self.assertEqual(live.instances, {})
        self.assertIn("real money is off", live.real_block())
        self.assertFalse(any(self.paper.held.values()))
        self.assertNotIn("SPY", live._roots(), 'completed proof no longer requires a quote read')

    def test_paper_only_restart_recovers_an_accepted_open_with_a_lost_answer(self):
        self.paper_only()
        self.paper.submit_mode = "lost"
        self.run_to(9, 35)
        cid = self.live.proof.status()["orders"][0]["cid"]
        self.live.state.close()
        self.paper._advance()
        self.paper.submit_mode = "ok"
        self.clock.set(at(MONDAY, 9, 36))
        self.paper_only()
        self.run_to(9, 46)
        self.assertTrue(self.live.proof.passed(), self.live.proof.status())
        self.assertEqual(self.live.proof.status()["orders"][0]["cid"], cid)
        self.assertEqual(len(self.paper.sent), 2)
        self.assertEqual(self.venue.sent, [])
        self.assertFalse(any(self.paper.held.values()))

    def test_weekend_does_not_start_a_paper_proof(self):
        self.paper_only()
        self.clock.set(at(MONDAY - dt.timedelta(days=2), 10, 0))
        self.assertEqual(self.live.minute()["state"], "closed")
        self.assertEqual(self.paper.sent, [])
        self.assertEqual(self.venue.sent, [])


class DurableProof(LiveCase):
    def make_proof(self):
        return self.make([], config={"require_paper_proof": True})

    def restart(self, hh=9, mm=36, *, day=MONDAY):
        self.live.state.close()
        self.clock.set(at(day, hh, mm))
        self.market.day = day
        return self.make_proof()

    def inventory(self):
        return {symbol: qty for symbol, qty in self.paper.held.items() if qty}

    def assert_passed_flat(self):
        self.assertTrue(self.live.proof.passed(), self.live.proof.status())
        self.assertEqual(self.inventory(), {})
        row = self.live.proof.status()
        self.assertTrue(row["open_witness"])
        self.assertTrue(row["close_witness"])

    def test_accepted_open_with_lost_answer_is_recovered_after_restart_without_another_open(self):
        self.make_proof()
        self.paper.submit_mode = "lost"
        self.run_to(9, 35)
        saved = self.live.proof.status()
        self.assertEqual(saved["orders"][0]["cid"], self.paper.sent[0]["client_order_id"])
        self.assertEqual(saved["baseline"], {s: "0" for s in saved["legs"]})
        self.paper._advance()
        self.paper.submit_mode = "ok"
        self.restart()
        self.run_to(9, 46)
        self.assert_passed_flat()
        self.assertEqual(len(self.paper.sent), 2)
        recovered = self.live.proof.status()["orders"][0]
        self.assertEqual(recovered["answer"]["status"], "filled")
        self.assertTrue(all(leg["filled_avg_price"] is not None for leg in recovered["answer"]["legs"]))
        observed = self.live.state.events(kinds=["paper_proof.order_observed"])
        self.assertTrue(any(event["payload"]["cid"] == recovered["cid"]
                            and event["payload"]["answer"]["status"] == "filled" for event in observed))

    def test_dispatch_crash_has_already_committed_the_client_id_and_baseline(self):
        self.make_proof()
        def crash_after_accept(body):
            saved = self.live.proof.status()
            self.assertEqual(saved["orders"][-1]["body"], body)
            self.assertEqual(set(saved["baseline"]), {leg["symbol"] for leg in body["legs"]})
            self.paper._create(body)
            raise RuntimeError("process stopped after the venue accepted")
        self.paper.on_submit = crash_after_accept
        self.run_to(9, 35)
        self.paper.on_submit = None
        self.paper._advance()
        self.restart()
        self.run_to(9, 45)
        self.assert_passed_flat()
        self.assertEqual(len(self.paper.sent), 2)

    def test_ambiguous_open_not_found_never_starts_another_attempt(self):
        self.make_proof()
        self.paper.submit_mode = "lost_absent"
        self.run_to(9, 35)
        cid = self.live.proof.status()["orders"][0]["cid"]
        self.paper.submit_mode = "ok"
        self.restart(9, 35, day=MONDAY + dt.timedelta(days=1))
        self.run_to(9, 55)
        self.assertFalse(self.live.proof.passed())
        self.assertEqual(self.live.proof.status()["orders"][0]["cid"], cid)
        self.assertEqual(len(self.paper.sent), 1)

    def test_accepted_close_with_lost_answer_is_looked_up_instead_of_resent(self):
        self.make_proof()
        self.run_to(9, 37)
        self.paper.submit_mode = "lost"
        self.run_to(9, 38)
        saved = self.live.proof.status()
        self.assertEqual(saved["orders"][-1]["action"], "close")
        self.paper._advance()
        self.paper.submit_mode = "ok"
        self.restart(9, 39)
        self.run_to(9, 46)
        self.assert_passed_flat()
        self.assertEqual(len(self.paper.sent), 2)

    def test_uneven_open_is_cancelled_and_owned_long_closed_before_retry(self):
        self.make_proof()
        self.paper.fill = "uneven"
        self.run_to(9, 36)
        self.assertEqual(sum(abs(q) for q in self.inventory().values()), D(1))
        self.paper.fill = "natural"
        self.run_to(9, 48)
        self.assert_passed_flat()
        self.assertEqual(len(self.paper.sent), 4)
        self.assertEqual(self.paper.sent[1]["position_intent"], "sell_to_close")
        self.assertEqual(self.paper.sent[1]["qty"], "1")

    def test_cancel_acknowledgment_is_not_terminal_confirmation(self):
        self.make_proof()
        self.paper.fill = "uneven"
        self.paper.cancel_delay = 180
        self.run_to(9, 37)
        self.assertEqual(len(self.paper.sent), 1)
        self.assertEqual(self.paper.book[0]["status"], "pending_cancel")
        self.assertFalse(self.live.proof.passed())
        self.paper.fill = "natural"
        self.run_to(9, 52)
        self.assert_passed_flat()

    def test_uneven_close_recovers_only_the_remaining_short_and_requires_a_new_full_roundtrip(self):
        self.make_proof()
        self.run_to(9, 37)
        self.paper.fill = "uneven"
        self.run_to(9, 38)
        self.paper.fill = "none"
        self.run_to(9, 47)
        self.assertFalse(self.live.proof.passed())
        self.paper.fill = "natural"
        self.run_to(9, 58)
        self.assert_passed_flat()
        recovery = [body for body in self.paper.sent if not body.get("legs")]
        self.assertTrue(recovery)
        self.assertEqual({(body["position_intent"], body["qty"], body["symbol"]) for body in recovery},
                         {("buy_to_close", "1", self.paper.sent[0]["legs"][1]["symbol"])})

    def test_prior_day_filled_open_stays_owned_and_closes_before_any_new_attempt(self):
        self.make_proof()
        self.run_to(9, 36)
        old_legs = self.live.proof.status()["legs"]
        self.restart(9, 35, day=MONDAY + dt.timedelta(days=1))
        self.run_to(9, 46)
        self.assert_passed_flat()
        self.assertEqual(len(self.paper.sent), 2)
        self.assertEqual([leg["symbol"] for leg in self.paper.sent[1]["legs"]], old_legs)

    def test_unreadable_initial_inventory_prevents_dispatch(self):
        self.make_proof()
        reads = []
        def unavailable():
            reads.append(True)
            raise RuntimeError("positions unavailable")
        self.paper.positions = unavailable
        self.run_to(9, 46)
        self.assertTrue(reads)
        self.assertEqual(self.paper.sent, [])
        self.assertFalse(self.live.proof.passed())

    def test_missing_close_inventory_witness_blocks_pass_even_when_order_is_filled(self):
        self.make_proof()
        self.run_to(9, 38)
        read_positions = self.paper.positions
        self.paper.positions = lambda: (_ for _ in ()).throw(RuntimeError("positions unavailable"))
        self.run_to(9, 44)
        self.assertFalse(self.live.proof.passed())
        self.assertEqual(len(self.paper.sent), 2)
        self.paper.positions = read_positions
        self.run_to(9, 45)
        self.assert_passed_flat()

    def test_missing_open_inventory_witness_cannot_be_inferred_from_filled_order(self):
        self.make_proof()
        original = self.paper.positions
        self.paper.positions = lambda: list(self.paper.extra_positions)
        self.run_to(9, 43)
        self.assertFalse(self.live.proof.passed())
        self.assertEqual(len(self.paper.sent), 1)
        self.assertFalse(self.live.proof.status()["open_witness"])
        self.paper.positions = original
        self.run_to(9, 49)
        self.assert_passed_flat()

    def test_unrelated_legacy_paper_inventory_is_never_owned_or_closed(self):
        self.make_proof()
        legacy = {"AAPL": D("0.2"), "SOFI261016P00005000": D(1), "SOFI261016P00006000": D(-1)}
        self.paper.held.update(legacy)
        self.run_to(9, 45)
        self.assertTrue(self.live.proof.passed(), self.live.proof.status())
        self.assertEqual(self.inventory(), legacy)
        self.assertTrue(all(leg["symbol"].startswith("SPY") for body in self.paper.sent for leg in body["legs"]))

    def test_preexisting_selected_contract_is_not_adopted_as_proof_inventory(self):
        self.make_proof()
        self.paper.held["SPY260929C00600000"] = D(1)
        self.run_to(9, 45)
        self.assertEqual(self.paper.sent, [])
        self.assertFalse(self.live.proof.passed())
        self.assertEqual(self.inventory(), {"SPY260929C00600000": D(1)})

    def test_legacy_pass_without_inventory_witnesses_is_not_accepted(self):
        self.make_proof()
        self.live.state.put("paper_proof", {"status": "passed"})
        self.assertFalse(self.live.proof.passed())
        self.run_to(9, 45)
        self.assertEqual(self.live.proof.status()["status"], "blocked")
        self.assertEqual(self.paper.sent, [])

    def test_missing_paper_proof_cannot_disable_the_required_gate(self):
        self.make_proof()
        self.live.proof = None
        self.run_to(9, 36)
        self.assertIn("paper account has not yet proved", self.live.real_block())

    def test_malformed_lookup_with_extra_contract_cannot_become_proof_evidence(self):
        self.make_proof()
        self.run_to(9, 35)
        order = self.paper.book[0]
        order["legs"].append({**order["legs"][0], "symbol": "SPY260929C00602000"})
        self.run_to(9, 45)
        self.assertFalse(self.live.proof.passed())
        self.assertEqual(len(self.paper.sent), 1)
        self.assertIn("contracts or quantity differ", self.live.proof.status()["why"])
