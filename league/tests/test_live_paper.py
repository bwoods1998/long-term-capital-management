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
    from league.tests.live_fakes import MONDAY, at, iso


PASSED = {"schema": 2, "status": "passed", "open_witness": True, "close_witness": True}
#: The structure proofs' state keys (money rules v3): taken as passed by the tests of the vertical's and the single's.
LATER = ("paper_proof_long_butterfly", "paper_proof_credit_vertical", "paper_proof_iron_condor", "paper_proof_iron_butterfly")


class PaperOnlyProof(LiveCase):
    """The multi-leg vertical's proof (the single-leg proof, which follows it, is taken as passed here: `SingleLeg`)."""

    def paper_only(self):
        # Match service.options_live: no real client or book exists while real money is off.
        self.families = MemoryFamilies()
        self.live = OptionsLive(self.root, market=self.market, real=None, paper=self.paper,
                                families=self.families, decider=InlineDecider(), real_money=False,
                                config={"require_paper_proof": True}, clock=self.clock, record=self.ledger)
        self.live.state.put("paper_proof_single", PASSED)
        for key in LATER:
            self.live.state.put(key, PASSED)
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
        live = self.make([], config={"require_paper_proof": True})
        live.state.put("paper_proof_single", PASSED)   # the vertical's proof alone (`SingleLeg` has the single's)
        for key in LATER:
            live.state.put(key, PASSED)
        return live

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


class SingleLeg(LiveCase):
    """The review of #390 (lens 3): the single-leg route proved on the practice account too, once the vertical's has
    passed; a real long call or put waits for it."""

    LONG_CALL = """
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {}
STATE = {"opened": 0}

def decide(ctx):
    if ctx.positions or ctx.orders:
        return []
    return [{"open": "long_call", "root": "SPY", "qty": 1, "limit": "natural",
             "legs": [{"side": "long", "right": "C", "dte": 1, "strike": 603.0}]}]
"""

    def test_after_the_vertical_a_long_call_round_trip_and_real_singles_wait_for_it(self):
        from league.tests.live_fakes import family

        live = self.make([family("call", self.LONG_CALL, band="probe", structure="long_call", typical=60.0)],
                         config={"require_paper_proof": True})
        for key in LATER:
            live.state.put(key, PASSED)
        while not live.proof.passed():
            self.clock.set(self.clock() + 60)
            live.minute()
        self.assertFalse(live.proof_single.passed())
        self.clock.set(self.clock() + 60)
        live.minute()
        self.assertEqual(self.venue.sent, [], "no real long call before the single-leg proof")
        self.assertTrue(any("single-leg route" in p["why"] for p, a in self.ledger.of("live.refusal")))
        self.run_to(10, 0)
        self.assertTrue(live.proof_single.passed(), live.proof_single.status())
        singles = [b for b in self.paper.sent if not b.get("legs")]
        self.assertEqual([(b["side"], b["position_intent"], b["type"]) for b in singles],
                         [("buy", "buy_to_open", "limit"), ("sell", "sell_to_close", "limit")])
        symbol = singles[0]["symbol"]
        strike = int(symbol[-8:]) / 1000
        self.assertEqual(symbol[-9], "C")
        self.assertTrue(600 * 1.01 <= strike <= 600 * 1.02, strike)
        self.assertEqual(singles[0]["symbol"], singles[1]["symbol"])
        self.assertFalse(any(self.paper.held.values()), "the practice account is flat again")
        self.run_to(10, 2)
        self.assertEqual([b.get("position_intent") for b in self.venue.sent][:1], ["buy_to_open"],
                         "the real long call goes once both routes are proved")


#: Money rules v3 (D3): the structure proofs, in the order they run after the vertical and the single.
STRUCTURE_PROOFS = ("long_butterfly", "credit_vertical", "iron_condor", "iron_butterfly")
CREDIT_PROOFS = ("credit_vertical", "iron_condor", "iron_butterfly")


def _structure_of(body):
    """The structure an mleg body forms, as the gateway reads it from the legs alone (`structure_core.classify` over the
    types the legs could be): (type, spec)."""
    from league import structure_core as core

    legs = [core.leg(leg["symbol"], 1 if leg["position_intent"] in ("buy_to_open", "sell_to_close") else -1,
                     int(leg["ratio_qty"])) for leg in body["legs"]]
    found = []
    for type_ in core.TYPES:
        try:
            found.append((type_, core.classify(type_, legs)))
        except ValueError:
            pass
    assert len(found) == 1, found
    return found[0]


class StructureProofs(LiveCase):
    """Money rules v3 (D3): each further real structure type's own paper round trip, one at a time, after the vertical's
    and the single's; a real open of a type waits for its own."""

    def paper_only(self, table=None):
        self.families = MemoryFamilies()
        self.live = OptionsLive(self.root, market=self.market, real=None, paper=self.paper, families=self.families,
                                decider=InlineDecider(), real_money=False, table=table,
                                config={"require_paper_proof": True}, clock=self.clock, record=self.ledger)
        self.live.state.put("paper_proof", PASSED)
        self.live.state.put("paper_proof_single", PASSED)
        return self.live

    def passed_kinds(self):
        return [p["kind"] for p, _ in self.ledger.of("live.paper_proof") if p["status"] == "passed"]

    def test_each_structure_is_proved_in_turn_with_its_own_shape_and_sign(self):
        live = self.paper_only()
        self.assertIn("SPY", live._roots())
        self.run_to(10, 0)
        for kind in STRUCTURE_PROOFS:
            self.assertTrue(live.proofs[kind].passed(), (kind, live.proofs[kind].status()))
            self.assertIn(f"of a {kind}", live.proofs[kind].status()["why"])
        self.assertEqual(self.passed_kinds(), list(STRUCTURE_PROOFS))
        self.assertEqual(self.venue.sent, [])
        self.assertFalse(any(self.paper.held.values()), "the practice account is flat again")
        self.assertNotIn("SPY", live._roots(), "every proof done: no read for them")
        # One open and one close each, never interleaved: no two proofs hold paper contracts at once.
        self.assertEqual([b["client_order_id"].split("-")[1] for b in self.paper.sent],
                         ["plb", "plb", "pcv", "pcv", "pic", "pic", "pib", "pib"])
        spot = self.market.level("SPY")
        for kind, (opened, closed) in zip(STRUCTURE_PROOFS, zip(self.paper.sent[::2], self.paper.sent[1::2])):
            type_, spec = _structure_of(opened)
            self.assertEqual(type_, kind)
            self.assertEqual({leg["position_intent"] for leg in opened["legs"]}, {"buy_to_open", "sell_to_open"})
            self.assertEqual({leg["position_intent"] for leg in closed["legs"]}, {"sell_to_close", "buy_to_close"})
            self.assertEqual(sorted(leg["symbol"] for leg in opened["legs"]), sorted(leg["symbol"] for leg in closed["legs"]))
            self.assertEqual((opened["qty"], opened["order_class"], opened["type"], opened["time_in_force"]),
                             ("1", "mleg", "limit", "day"))
            open_price, close_price = D(opened["limit_price"]), D(closed["limit_price"])
            if kind in CREDIT_PROOFS:
                # Alpaca's convention: a credit negative, a debit positive; and never at or past the collateral.
                self.assertLess(open_price, 0, kind)
                self.assertLess(-open_price, spec.collateral, kind)
                self.assertGreater(close_price, 0, kind)
                self.assertLess(close_price, spec.collateral, kind)
            else:
                self.assertGreater(open_price, 0)
                self.assertLess(open_price, spec.max_value)
                self.assertLessEqual(close_price, 0)
            # Every wing is $1 and, but for the iron butterfly's put, no short leg starts in the money.
            if kind in CREDIT_PROOFS:
                self.assertEqual(spec.collateral, 1)
            else:
                self.assertEqual(spec.max_value, 1)
            for leg in spec.legs:
                if leg.sign < 0 and not (kind == "iron_butterfly" and leg.right == "put"):
                    itm = leg.strike < D(str(spot)) if leg.right == "call" else leg.strike > D(str(spot))
                    self.assertFalse(itm, (kind, leg.occ, spot))
        butterfly = next(b for b in self.paper.sent if b["client_order_id"].startswith("lv-plb"))
        self.assertEqual(sorted(leg["ratio_qty"] for leg in butterfly["legs"]), ["1", "1", "2"])

    def test_only_the_proofs_the_money_tables_real_types_need_run(self):
        import copy

        from league.constitution import CONSTITUTION
        from league.live import money as M

        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["real_types"] = ["debit_vertical", "long_butterfly", "long_call", "long_put"]
        live = self.paper_only(table=M.Table.from_constitution(c))
        self.run_to(10, 0)
        self.assertTrue(live.proofs["long_butterfly"].passed())
        for kind in CREDIT_PROOFS:
            self.assertEqual(live.proofs[kind].status(), {}, kind)
        self.assertEqual(self.passed_kinds(), ["long_butterfly"])
        self.assertNotIn("SPY", live._roots())

    def test_a_proof_that_failed_today_holds_back_none_of_the_others_and_runs_again_next_session(self):
        live = self.paper_only()
        live.state.put("paper_proof_long_butterfly", {"schema": 2, "day": MONDAY.isoformat(), "status": "failed",
                                                      "tries": 3, "orders": []})
        self.run_to(10, 0)
        self.assertFalse(live.proofs["long_butterfly"].passed())
        self.assertEqual(self.passed_kinds(), list(CREDIT_PROOFS))
        self.live.state.close()
        tuesday = MONDAY + dt.timedelta(days=1)
        self.clock.set(at(tuesday, 9, 31))
        self.market.day = tuesday
        live = self.paper_only()
        self.run_to(9, 45)
        self.assertTrue(live.proofs["long_butterfly"].passed(), live.proofs["long_butterfly"].status())

    def test_a_blocked_proof_is_skipped_and_its_type_stays_shadow_only(self):
        live = self.paper_only()
        live.state.put("paper_proof_credit_vertical", {"schema": 2, "status": "blocked", "why": "the owner's"})
        self.run_to(10, 0)
        self.assertEqual(self.passed_kinds(), ["long_butterfly", "iron_condor", "iron_butterfly"])
        self.assertIn("credit_vertical route", live._proof_refusal("credit_vertical"))

    def test_an_uneven_condor_open_is_unwound_leg_by_leg_and_proved_on_a_new_attempt(self):
        live = self.paper_only()
        for kind in ("long_butterfly", "credit_vertical"):
            live.state.put(f"paper_proof_{kind}", PASSED)
        seen = []

        def uneven_first_condor(body):
            cid = body.get("client_order_id", "")
            if cid.startswith("lv-pic") and body.get("legs") and not seen:
                seen.append(cid)
                self.paper.fill = "uneven"
            elif not body.get("legs"):
                self.paper.fill = "natural"   # the cleanup's single legs fill; the next attempt is whole
        self.paper.on_submit = uneven_first_condor
        self.run_to(10, 15)
        self.assertTrue(live.proofs["iron_condor"].passed(), live.proofs["iron_condor"].status())
        self.assertTrue(live.proofs["iron_butterfly"].passed())
        self.assertFalse(any(self.paper.held.values()))
        cleanup = [b for b in self.paper.sent if not b.get("legs")]
        self.assertEqual([(b["position_intent"], b["qty"]) for b in cleanup], [("sell_to_close", "1")])
        self.assertEqual(live.proofs["iron_condor"].status()["tries"], 2)

    def test_a_restart_mid_attempt_finishes_it_before_any_other_proof(self):
        live = self.paper_only()
        self.run_to(9, 36)                                  # the butterfly's open has filled
        self.assertEqual(live.proofs["long_butterfly"].status()["status"], "open_filled")
        self.live.state.close()
        self.clock.set(at(MONDAY, 9, 37))
        live = self.paper_only()
        self.assertIs(live._active_proof(MONDAY.isoformat()), live.proofs["long_butterfly"])
        self.run_to(9, 45)
        self.assertTrue(live.proofs["long_butterfly"].passed())
        self.assertEqual([b["client_order_id"].split("-")[1] for b in self.paper.sent][:2], ["plb", "plb"])


class StructureGate(LiveCase):
    """A real open of each type waits for its own paper proof (`OptionsLive._proof_refusal`), and real money opens no
    short leg in the money on an American-style root (`money.entry_refusal`)."""

    REAL = ("debit_vertical", "long_call", "long_put") + STRUCTURE_PROOFS

    def test_each_type_waits_for_its_own_proof_and_an_unproved_type_never_opens(self):
        live = self.make([], config={"require_paper_proof": True})
        for type_ in self.REAL:
            self.assertIn("has not yet proved", live._proof_refusal(type_), type_)
        live.state.put("paper_proof", PASSED)
        self.assertIsNone(live._proof_refusal("debit_vertical"))
        self.assertIn("single-leg route", live._proof_refusal("long_call"))
        live.state.put("paper_proof_single", PASSED)
        self.assertIsNone(live._proof_refusal("long_call"))
        self.assertIsNone(live._proof_refusal("long_put"))
        for kind in STRUCTURE_PROOFS:
            self.assertIn(f"{kind} route", live._proof_refusal(kind))
            live.state.put(f"paper_proof_{kind}", PASSED)
            self.assertIsNone(live._proof_refusal(kind))
        live.state.put("paper_proof_iron_condor", {"status": "passed"})          # no witnesses: not a pass
        self.assertIn("iron_condor route", live._proof_refusal("iron_condor"))
        self.assertIn("has not yet proved", live._proof_refusal("calendar"), "a type with no proof never opens")
        live.proofs.pop("iron_butterfly")
        self.assertIn("iron_butterfly route", live._proof_refusal("iron_butterfly"), "a missing proof cannot pass")
        live.settings["require_paper_proof"] = False
        self.assertIsNone(live._proof_refusal("iron_condor"))

    RETRY_CONDOR = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {}
STATE = {}

def decide(ctx):
    if ctx.positions or ctx.orders:
        return []
    return [{"open": "iron_condor", "root": "SPY", "qty": 1, "limit": "natural",
             "legs": [{"side": "long", "right": "P", "rel": 1, "offset": -1.0},
                      {"side": "short", "right": "P", "dte": 1, "atm": -3},
                      {"side": "short", "right": "C", "dte": 1, "atm": 3},
                      {"side": "long", "right": "C", "rel": 2, "offset": 1.0}]}]
'''

    def test_a_real_condor_waits_for_the_paper_condor_then_goes(self):
        from league.tests.live_fakes import family

        live = self.make([family("condor", self.RETRY_CONDOR, band="probe", structure="iron_condor", typical=60.0)],
                         config={"require_paper_proof": True})
        for key in ("paper_proof", "paper_proof_single", "paper_proof_long_butterfly", "paper_proof_credit_vertical"):
            live.state.put(key, PASSED)
        self.run_to(9, 34)
        self.assertEqual(self.venue.sent, [])
        self.assertTrue(any("iron_condor route" in p["why"] for p, _ in self.ledger.of("live.refusal")))
        self.run_to(9, 45)
        self.assertTrue(live.proofs["iron_condor"].passed(), live.proofs["iron_condor"].status())
        self.assertTrue(self.venue.sent, "the real condor goes once its paper round trip has passed")
        type_, _ = _structure_of(self.venue.sent[0])
        self.assertEqual(type_, "iron_condor")
        self.assertLess(D(self.venue.sent[0]["limit_price"]), 0, "a credit, Alpaca's sign")
        passed_at = live.proofs["iron_condor"].status()["passed_at"]
        self.assertGreaterEqual(min(o["submitted_at"] for o in self.venue.book), iso(passed_at - 60))

    ITM_CREDIT = '''
NEEDS = {"roots": ["ROOT"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {}
STATE = {"sent": 0}

def decide(ctx):
    if ctx.positions or ctx.orders or STATE["sent"]:
        return []
    STATE["sent"] = 1
    return [{"open": "credit_vertical", "root": "ROOT", "qty": 1, "limit": "natural",
             "legs": [{"side": "short", "right": "C", "dte": 1, "atm": -2},
                      {"side": "long", "right": "C", "rel": 0, "offset": 1.0}]}]
'''

    def credit_family(self, root):
        from league.tests.live_fakes import family

        live = self.make([family("itm", self.ITM_CREDIT.replace("ROOT", root), band="probe", structure="credit_vertical",
                                 typical=60.0)], config={"require_paper_proof": True})
        for key in ("paper_proof", "paper_proof_single") + tuple(f"paper_proof_{k}" for k in STRUCTURE_PROOFS):
            live.state.put(key, PASSED)
        self.run_to(9, 33)
        return live

    def test_an_in_the_money_short_call_never_opens_on_an_equity_root(self):
        self.credit_family("SPY")
        self.assertEqual(self.venue.sent, [])
        refusals = [p["why"] for p, _ in self.ledger.of("live.refusal")]
        self.assertTrue(any("in the money" in why and "American-style" in why for why in refusals), refusals)

    def test_the_same_credit_vertical_opens_on_a_european_index_root(self):
        self.credit_family("XSP")
        self.assertEqual(len([b for b in self.venue.sent if b.get("legs")]), 1, [p for p, _ in self.ledger.of("live.refusal")])
        type_, spec = _structure_of(self.venue.sent[0])
        self.assertEqual(type_, "credit_vertical")
        short = next(leg for leg in spec.legs if leg.sign < 0)
        self.assertLess(short.strike, D(str(self.market.level("XSP"))), "its short call is in the money: European, allowed")
