"""Release E2, THE EQUITY LANES' BIRTHS (league/swarm/elane_births.py, league/swarm/architect.py `equity_pass`): the switch,
the equity quota across lanes, the LANES/EQUITY request, the admission (lane, structure, symbols, agenda, closed cells,
the same idea in research, a lineage with its try, the card, the quota), the births as equity families with their
first program, and the options architect untouched. E1's switch and card admission are fakes as INTERFACES fixes them
(league/tests/elane_e2_fakes.py). Every family, program and number here is invented."""

from __future__ import annotations

import unittest

from league.swarm import cards, elane_births, elane_train, elane_yield
from league.swarm.architect import Architect
from league.swarm.elane_births import BIRTHS_AT_KEY, LAST_KEY, EquityPass, EquityQuota
from league.tests import elane_e2_fakes as fx


class BirthCase(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(max_per_pass=4)
        self.answers: list = []
        self.router = fx.FakeRouter(lambda call: self.answers.pop(0) if self.answers else fx.answer([]))
        self.arch = Architect(self.store, self.router, self.settings, clock=self.clock)

    def born_options(self, n: int) -> None:
        for i in range(n):
            self.store.event("swarm.born", f"opt-{i}", {"structure": "debit_vertical", "roots": ["SPY"]})

    def pass_(self) -> dict:
        return self.arch.equity_pass()


class TheSwitch(BirthCase):
    def test_off_unless_the_lanes_are_on_and_the_share_above_zero(self):
        self.assertTrue(elane_births.births_on(self.settings))
        self.assertTrue(self.arch.equity_due())
        off = fx.settings()
        off["elane"]["mode"] = "off"
        self.assertFalse(elane_births.births_on(off))
        zero = fx.settings()
        zero["elane"]["birth_share"] = 0.0
        self.assertFalse(elane_births.births_on(zero))
        out = Architect(self.store, self.router, zero, clock=self.clock).equity_pass()
        self.assertEqual(out["skipped"], "off")
        self.assertEqual(self.router.calls, [], "no model is asked while off")

    def test_cadence_refills_faster_below_the_start(self):
        self.store.put(BIRTHS_AT_KEY, self.clock())
        self.clock.advance(1800)
        self.assertTrue(self.arch.equity_due(), "below `start` families in research: the refill cadence")
        for i in range(8):
            fx.e2_family(self.store, f"r{i}", symbols=(fx.UNIVERSE[i % 9],), mechanism=f"Invented idea number {i} for the test.")
        self.assertFalse(self.arch.equity_due(), "at `start`: the pass's own cadence (two hours)")
        self.clock.advance(7200)
        self.assertTrue(self.arch.equity_due())

    def test_the_days_dollars_close_the_pass(self):
        elane_yield.book(self.store, "sail:pro_asap", usd=8.0, known=True, purpose="births", answered=True, now=self.clock())
        self.assertFalse(self.arch.equity_due())


class TheQuota(BirthCase):
    def test_the_share_of_the_windows_births(self):
        self.born_options(30)
        q = EquityQuota(self.store, self.settings, now=self.clock())
        self.assertEqual(q.target, 10, "a quarter of all births: 10 beside 30")
        self.assertEqual(q.want, 4, "capped by max_per_pass")
        for i in range(8):
            self.store.event("swarm.born", f"eq-{i}", {"lane": "equity"})
        q = EquityQuota(self.store, self.settings, now=self.clock())
        self.assertEqual((q.window, q.want), ({"options": 30, "equity": 8}, 2))

    def test_an_options_ceiling_never_stops_the_equity_lanes(self):
        q = EquityQuota(self.store, self.settings, now=self.clock())
        self.assertEqual(q.want, 1, "min_per_pass with no options birth in the window")
        self.assertIn("propose 1", q.text())

    def test_room_in_train_research(self):
        tight = fx.settings(max_alive=2, max_per_pass=4)
        self.born_options(40)
        fx.e2_family(self.store, "one")
        q = EquityQuota(self.store, tight, now=self.clock())
        self.assertEqual(q.want, 1)
        self.assertTrue(q.admits("beta"))
        q.born("beta")
        self.assertFalse(q.admits("equity"))

    def test_off_wants_nothing(self):
        off = fx.settings()
        off["elane"]["mode"] = "off"
        self.assertEqual(EquityQuota(self.store, off, now=self.clock()).want, 0)


class TheRequest(BirthCase):
    def test_the_lanes_block_the_agenda_the_bar_and_the_contract(self):
        system, user = EquityPass(self.arch).request(EquityQuota(self.store, self.settings, now=self.clock()))
        self.assertIn("THE PROGRAM CONTRACT", system)
        self.assertIn("NEEDS", system)
        for words in ("MARKET BETA", "EQUITY (labelled EQUITY)", "THE UNIVERSE", "index SPY, QQQ, IWM, DIA",
                      "defensive TLT, GLD", "THE RATION", "THE TRAIN BAR (equity-v1)", "THE AGENDA", "Lou, Polk and Skouras",
                      "Moskowitz, Ooi and Pedersen", "Frazzini and Pedersen", "McConnell and Xu", "EQUITY QUOTA",
                      "FAMILY CARD VOCABULARY"):
            self.assertIn(words, user)
        self.assertIn("earnings_drift: post-earnings drift", user)
        self.assertIn("REFUSED until its data exist", user)
        self.assertNotIn("STRUCTURE FAMILIES", user, "the options structure groups are not the equity cards' words")
        self.assertNotRegex(user, r"\b202[56]\b")

    def test_the_card_vocabulary_is_the_equity_cards_own(self):
        """Finding 9 of the adversarial review: the equity architect was shown the options inputs, the minute of the day
        and an intraday holding, which E1's `card_errors` refuses on an equity card, and no `equity_premium`."""
        text = elane_births.vocabulary_text(self.settings)
        for words in ("equity_premium", "trend_momentum", "reversal_liquidity", "calendar_flow", "- underlying_price:",
                      "- share_volume:", "- clock: the session calendar", "- days_1_3:", "REBIRTH"):
            self.assertIn(words, text)
        for words in ("implied_vol", "iv_term_structure", "iv_skew", "option_liquidity", "open_interest", "- intraday:",
                      "minute of the day", "volatility_risk_premium", "pinning_gamma", "dispersion"):
            self.assertNotIn(words, text)


class TheBirths(BirthCase):
    def test_births_as_equity_families_with_their_first_program(self):
        self.born_options(9)  # the target is 3
        rows = [fx.proposal("overnight-spy"),
                fx.proposal("trend-sectors", lane="equity", agenda="trend", symbols=("XLK", "XLF", "XLE"), code=""),
                fx.proposal("pead-spy", lane="equity", agenda="earnings_drift", symbols=("SPY",))]
        self.answers.append(fx.answer(rows, cost=0.12))
        out = self.pass_()
        self.assertEqual(out["born"], ["overnight-spy", "trend-sectors"])
        self.assertEqual(out["route"], "sail:pro_asap")
        beta = self.store.family("overnight-spy")
        self.assertEqual((beta["structure"], beta["roots"]), ("etf", ["SPY"]))
        self.assertEqual({k: beta["spec"][k] for k in ("lane", "symbols", "agenda", "e2_route")},
                         {"lane": "beta", "symbols": ["SPY"], "agenda": "overnight", "e2_route": "sail:pro_asap"})
        self.assertEqual(self.store.latest_version("overnight-spy")["author"], "architect:sail:pro_asap")
        self.assertIsNone(self.store.latest_version("trend-sectors"), "no program: the researcher writes v1")
        self.assertEqual(cards.card_of(self.store, "overnight-spy")["card"]["lane"], "beta")
        self.assertEqual(elane_train.record_of(beta)["status"], "researching")
        born = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.born" and e["family"] in out["born"]]
        self.assertEqual([p["lane"] for p in born], ["beta", "equity"])
        self.assertEqual(elane_yield.ledger(self.store)["routes"]["sail:pro_asap"]["births"], 2)
        self.assertEqual(out["refused"]["count"], 1)
        self.assertIn("needs data the House does not hold", self.store.get(LAST_KEY)["refused"][0]["why"])
        _, again = EquityPass(self.arch).request(EquityQuota(self.store, self.settings, now=self.clock()))
        # The next request says the refusal in closed words (release E2.4): the proposal by its place, its lane and its
        # agenda key, the House's sentence for the class; never its slug, never the refusal's own text.
        self.assertIn("- proposal 3 of 3 (equity, earnings_drift): its \"agenda\" must be one key of THE AGENDA whose data "
                      "the House holds (overnight, reversal, trend, rotation, low_vol, turn_of_month, other)", again)
        self.assertNotIn("pead-spy", again)
        self.assertIn("EQUITY TRAIN MAP", again)
        call = self.router.calls[0]
        self.assertEqual((call["role"], call["sail_profile"], call["claude"]), ("elane", "pro_asap", False))
        self.assertTrue(call["key"].startswith("swarm:elane:births:"))

    def test_the_box_refuses_each_reason_by_name(self):
        self.born_options(60)
        bad_lane = fx.proposal("x-lane", lane="alpha")
        bad_lane["card"]["lane"] = "alpha"
        stock_beta = fx.proposal("x-stock", structure="stock")
        stock_beta["structure"] = "stock"
        foreign = fx.proposal("x-foreign", symbols=("AAPL",))
        no_card = fx.proposal("x-card")
        no_card["card"].pop("hypothesis")
        rows = [bad_lane, stock_beta, foreign, no_card, fx.proposal("x-agenda", agenda="astrology")]
        self.answers.append(fx.answer(rows))
        out = self.pass_()
        self.assertEqual(out["born"], [])
        whys = {r["slug"]: r["why"] for r in self.store.get(LAST_KEY)["refused"]}
        self.assertTrue(whys["x-lane"].startswith("lane:"))
        self.assertTrue(whys["x-stock"].startswith("structure:"))
        self.assertTrue(whys["x-foreign"].startswith("symbols:"))
        self.assertTrue(whys["x-card"].startswith("card: hypothesis"))
        self.assertTrue(whys["x-agenda"].startswith("agenda:"))

    def test_a_closed_cell_the_same_idea_in_research_and_a_lineage_with_its_try(self):
        self.born_options(60)
        mech = "Invented mechanism: sector trend followers are paid for slow-moving institutional capital."
        for i in range(3):
            fx.e2_family(self.store, f"dead{i}", lane="equity", agenda="trend", symbols=("XLK",),
                         mechanism=f"Unrelated invented idea {i} about something else entirely.",
                         record={"status": "refuted", "versions": {"1": {"fails": ["Y2"]}},
                                 "refuted": {"at": "2026-10-10T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        fx.e2_family(self.store, "busy", lane="equity", agenda="rotation", symbols=("XLK", "XLF"), mechanism=mech)
        passed = fx.e2_family(self.store, "won", lane="equity", agenda="reversal", symbols=("QQQ",),
                              record={"status": "passed", "passed_version": 1, "versions": {"1": {"passed": True}}})
        rows = [fx.proposal("into-closed", lane="equity", agenda="trend", symbols=("XLK",)),
                fx.proposal("same-idea", lane="equity", agenda="rotation", symbols=("XLF", "XLK"), mechanism=mech,
                            code=fx.program("XLK")),
                fx.proposal("child-of-won", lane="equity", agenda="reversal", symbols=("QQQ",), parent=passed["id"],
                            code=fx.program("QQQ"))]
        self.answers.append(fx.answer(rows))
        out = self.pass_()
        self.assertEqual(out["born"], [])
        whys = {r["slug"]: r["why"] for r in self.store.get(LAST_KEY)["refused"]}
        self.assertIn("CLOSED", whys["into-closed"])
        self.assertIn("in Train research: busy", whys["same-idea"])
        self.assertIn("has its one Validation try", whys["child-of-won"])

    def test_a_seeded_lineage_has_its_try(self):
        self.born_options(60)
        seed = self.store.add_family({"id": "seed-overnight-qqq", "mechanism": "The captain's seed: overnight on QQQ "
                                      "after a down close.", "structure": "etf", "roots": ["QQQ"], "lane": "beta"},
                                     origin="seed")
        self.answers.append(fx.answer([fx.proposal("qqq-child", symbols=("QQQ",), parent=seed["id"],
                                                   code=fx.program("QQQ"))]))
        out = self.pass_()
        self.assertEqual(out["born"], [])
        self.assertIn("has its one Validation try", self.store.get(LAST_KEY)["refused"][0]["why"])

    def test_a_declared_parent_never_hides_a_tried_lineage_of_the_same_idea(self):
        # The integration review's seal-3, case 1: the seed's lineage has its try. The same mechanism on the same slice
        # with no parent was refused; naming ANY untried equity family as its parent bore it in that family's lineage
        # with a fresh Validation try (the refusal is shown back to the architect and the reply offers `parent`).
        self.born_options(60)
        mech = ("Index holders are paid for bearing overnight risk they cannot trade out of: buy SPY at the close and "
                "sell at the next open.")
        self.store.add_family({"id": "seed-overnight-spy", "mechanism": mech, "structure": "etf", "roots": ["SPY"],
                               "symbols": ["SPY"], "lane": "beta"}, origin="seed")
        other = fx.e2_family(self.store, "tom-dia", lane="beta", agenda="turn_of_month", symbols=("DIA",),
                             mechanism="Invented turn of the month idea on DIA: payroll flows lift the last sessions.",
                             record={"status": "stalled", "versions": {"1": {"fails": ["STATE"]}},
                                     "stalled": {"at": "2026-10-10T00:00:00Z", "codes": ["STATE"], "versions": 1, "why": "x"}})
        self.store.retire(other["id"], "STALLED on Train")
        for parent in (None, "tom-dia"):
            extra = {"parent": parent} if parent else {}
            self.answers.append(fx.answer([fx.proposal("overnight-again", symbols=("SPY",), mechanism=mech,
                                                       code=fx.program("SPY"), **extra)]))
            out = self.pass_()
            self.assertEqual(out["born"], [], f"parent {parent}")
            why = self.store.get(LAST_KEY)["refused"][0]["why"]
            self.assertIn("it continues seed-overnight-spy's lineage, which has its one Validation try", why)
            self.clock.advance(4 * 3600)
        # A different idea under the same declared parent is still born, in that parent's lineage.
        self.answers.append(fx.answer([fx.proposal("tom-again", agenda="turn_of_month", symbols=("DIA",), parent="tom-dia",
                                                   mechanism="Month-end rebalancing by pension funds lifts DIA over "
                                                             "the last sessions of each month.",
                                                   code=fx.program("DIA"))]))
        out = self.pass_()
        self.assertEqual(out["born"], ["tom-again"], self.store.get(LAST_KEY))
        self.assertEqual(self.store.family("tom-again")["parent"], "tom-dia")

    def test_a_newer_untried_family_of_the_slice_never_hides_an_older_tried_one(self):
        # seal-3, case 2 (no parent declared): an older tried family and a newer untried dead family both hold the idea
        # on the slice; the admission read the newest alone and bore the proposal.
        self.born_options(60)
        seed_idea = "Index holders earn the overnight premium: hold SPY from close until next open every session."
        newer = "Hold SPY from close until next open only after a down day, when dealers demand extra compensation."
        asked = "Overnight premium: hold SPY from close until next open every session after a down day."
        from league.swarm.architect import same_idea

        self.assertTrue(same_idea(asked, seed_idea) and same_idea(asked, newer), "the proposal holds both ideas")
        self.store.add_family({"id": "seed-overnight-spy", "mechanism": seed_idea, "structure": "etf", "roots": ["SPY"],
                               "symbols": ["SPY"], "lane": "beta"}, origin="seed")
        self.clock.advance(60)
        dead = fx.e2_family(self.store, "overnight-down", symbols=("SPY",), mechanism=newer,
                            record={"status": "stalled", "versions": {"1": {"fails": ["STATE"]}},
                                    "stalled": {"at": "2026-10-10T00:00:00Z", "codes": ["STATE"], "versions": 1, "why": "x"}})
        self.store.retire(dead["id"], "STALLED on Train")
        self.answers.append(fx.answer([fx.proposal("overnight-x", symbols=("SPY",), mechanism=asked,
                                                   code=fx.program("SPY"))]))
        out = self.pass_()
        self.assertEqual(out["born"], [])
        self.assertIn("it continues seed-overnight-spy's lineage", self.store.get(LAST_KEY)["refused"][0]["why"])

    def test_a_rebirth_from_a_tried_lineage_is_refused_whatever_parent_it_declares(self):
        # seal-3, the rebirth path: the row a card is reborn from was checked only while no parent was set.
        from unittest import mock

        from league.swarm import elane_births

        self.born_options(60)
        won = fx.e2_family(self.store, "won", lane="equity", agenda="reversal", symbols=("QQQ",),
                           record={"status": "passed", "passed_version": 1, "versions": {"1": {"passed": True}}})
        row = self.store.add_family({"id": "dead-child", "mechanism": "An invented trend idea on XLK that was refuted.",
                                     "structure": "etf", "roots": ["XLK"], "symbols": ["XLK"], "lane": "equity",
                                     "agenda": "trend", "e2_route": "sail:pro_asap"}, origin="architect", parent=won["id"])
        self.assertEqual(row["lineage"], self.store.family("won")["lineage"], "the dead row sits in the tried lineage")
        untried = fx.e2_family(self.store, "tom-dia", lane="beta", agenda="turn_of_month", symbols=("DIA",),
                               mechanism="Invented turn of the month idea on DIA: payroll flows lift the last sessions.",
                               record={"status": "stalled", "versions": {}, "stalled": {"at": "x", "codes": [], "versions": 0}})
        self.store.retire(untried["id"], "STALLED on Train")

        class Index:
            def check(self, card, structure, mechanism, _, *, roots=None):
                return {"ok": True, "rebirth": True, "row": "dead-child"}

        for parent in (None, "tom-dia"):
            extra = {"parent": parent} if parent else {}
            self.answers.append(fx.answer([fx.proposal("reborn", lane="equity", agenda="trend", symbols=("XLF",),
                                                       mechanism="A different invented trend idea on another sector "
                                                                 "with a new input.", code=fx.program("XLF"), **extra)]))
            with mock.patch.object(elane_births.EquityPass, "rebirth_index", lambda self: Index()):
                out = self.pass_()
            self.assertEqual(out["born"], [], f"parent {parent}")
            self.assertIn("its rebirth continues dead-child's lineage", self.store.get(LAST_KEY)["refused"][0]["why"])
            self.clock.advance(4 * 3600)

    def test_the_quota_bounds_the_pass_and_a_bad_program_is_born_without_it(self):
        rows = [fx.proposal("first", code="import os\n" + fx.program()), fx.proposal("second", symbols=("QQQ",),
                                                                                    code=fx.program("QQQ"))]
        self.answers.append(fx.answer(rows))
        out = self.pass_()
        self.assertEqual(out["equity_want"], 1)
        self.assertEqual(out["born"], ["first"])
        self.assertIsNone(self.store.latest_version("first"))
        refused = elane_train.record_of(self.store.family("first"))["refused"][0]["why"]
        self.assertIn("the architect's program: refused by the code rules", refused)
        self.assertIn("born", self.store.get(LAST_KEY)["refused"][0]["why"])

    def test_a_failed_route_falls_to_the_next_and_both_are_booked(self):
        from league.swarm.models import ModelError

        def script(call):
            if call["sail_profile"] == "pro_asap":
                return ModelError("busy")
            return fx.answer([fx.proposal("via-glm")], model="glm_asap")
        self.arch.router = self.router = fx.FakeRouter(script)
        out = Architect(self.store, self.router, self.settings, clock=self.clock).equity_pass()
        self.assertEqual((out["route_chosen"], out["route"]), ("sail:pro_asap", "sail:glm_asap"))
        rows = elane_yield.ledger(self.store)["routes"]
        self.assertEqual((rows["sail:pro_asap"]["failed"], rows["sail:glm_asap"]["births"]), (1, 1))
        self.assertEqual(self.store.family("via-glm")["spec"]["e2_route"], "sail:glm_asap")


class TheGraveyardBinds(BirthCase):
    """Finding 11 of the adversarial review: a card in the cell of a family E2 refuted on Train needs a valid rebirth
    claim (E1's `cards.RebirthIndex`), and no other equity family's row (an outcome lesson) can bind or be quoted."""

    def refuted(self, fid: str, lane: str = "equity", symbols: tuple[str, ...] = ("XLK",)) -> dict:
        fam = fx.e2_family(self.store, fid, lane=lane, agenda="trend", symbols=symbols,
                           mechanism=f"Invented trend idea {fid} on one sector, refuted on Train.",
                           record={"status": "refuted", "versions": {"1": {"fails": ["Y2"]}},
                                   "refuted": {"at": "2026-10-10T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        cards.put(self.store, fam["id"], fx.card(lane, symbols), "etf")
        self.store.bury(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        self.store.retire(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        return fam

    def test_a_card_in_a_refuted_cell_needs_a_rebirth(self):
        self.born_options(60)
        dead = self.refuted("dead-trend")
        self.answers.append(fx.answer([fx.proposal("again", lane="equity", agenda="trend", symbols=("XLF",),
                                                   code=fx.program("XLF"))]))
        out = self.pass_()
        self.assertEqual(out["born"], [])
        why = self.store.get(LAST_KEY)["refused"][0]["why"]
        self.assertTrue(why.startswith("graveyard:"), why)
        self.assertIn(dead["id"], why)
        self.assertNotIn("invented Train lesson", why, "the refusal names the row, never its lesson")

    def test_the_binding_is_off_with_the_architects_rebirth_switch(self):
        self.born_options(60)
        self.refuted("dead-trend")
        settings = fx.settings(max_per_pass=4)
        settings["architect"] = {"card_rebirth": "off"}
        arch = Architect(self.store, self.router, settings, clock=self.clock)
        self.answers.append(fx.answer([fx.proposal("again", lane="equity", agenda="trend", symbols=("XLF",),
                                                   code=fx.program("XLF"))]))
        self.assertEqual(arch.equity_pass()["born"], ["again"])

    def test_no_other_equity_row_binds_or_is_read(self):
        self.born_options(60)
        other = fx.e2_family(self.store, "looked-at", lane="equity", agenda="trend", symbols=("XLE",))
        cards.put(self.store, other["id"], fx.card("equity", ("XLE",)), "etf")
        self.store.bury(other["id"], "best validation: failed its look (an outcome lesson no generator may read)")
        self.store.retire(other["id"], "its equity lineage has used its one sealed look")
        self.answers.append(fx.answer([fx.proposal("free", lane="equity", agenda="trend", symbols=("XLF",),
                                                   code=fx.program("XLF"))]))
        self.assertEqual(self.pass_()["born"], ["free"], "only E2's own Train refutations bind")


class TheOptionsArchitect(BirthCase):
    def test_no_equity_row_reaches_the_options_architects_graveyard(self):
        opt = self.store.add_family({"id": "opt-dead", "mechanism": "An invented options idea that died on Train.",
                                     "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        self.store.bury(opt["id"], "REFUTED: an invented options lesson.")
        eq = fx.e2_family(self.store, "eq-dead")
        self.store.bury(eq["id"], "best validation: failed its look (an outcome lesson no generator may read)")
        self.assertEqual([r["family"] for r in self.arch.graves(limit=20)], ["opt-dead"])
        self.assertEqual(self.arch.graveyard_ids(), {"opt-dead"})
        from league.swarm.architect import GraveyardDigest

        self.assertEqual([p["id"] for p in GraveyardDigest(self.store, self.settings, clock=self.clock).rows()], ["opt-dead"])
        prompt = self.arch.prompt()
        self.assertNotIn("eq-dead", prompt)


if __name__ == "__main__":
    unittest.main()
