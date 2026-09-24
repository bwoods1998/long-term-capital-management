"""The evidence clock and the seat market (S1, S3, S4), corrected children (L1) and a live defect,
the close-the-gaps run, Sept 24, 2026.

Measured on the T0 snapshot (2026-09-24 01:42Z): 103 deaths in 24 hours, median life 14.3 h, 70 of them
before three fills, while a day-horizon desk needs one to three days per settlement (the scoreboard's
evidence clocks: kalshi-weather 31.8 h from a member's first fill to its third independent settlement,
kalshi-prices 36.5 h, kalshi-sports 20.5 h). Displacement took haghani-46 (38 fills), haghani-39 (26),
meriwether-hadd32b (24), hawkins-21 (8), mullins-13 (9) and mullins-14 (6 fills, holding a replay-passed
candidate, 113 trades and +38.4% in replay, whose admission was cancelled with it). 25 graduates and 5
cards waited up to 11 h. meriwether-h2d625d kept trading real money on taker entries while its research
child had passed replay with the maker fix. A Kalshi trader with three independent settlements was treated as short of
the bunt line's record.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.admissions import Admissions
from league.constitution import CONSTITUTION
from league.house import House, Newcomer, Settings, kaplan_meier_median
from league.lab import static_literal
from league.sandbox import LocalSandbox
from league.tests.fakes import FakeBroker
from league.tests.test_house import BUYER
from league.tests.test_seat_market import SeatCase, alerts
from league.venues import instrument_for

DESK = "alpaca-crypto-majors"
BTC = instrument_for("alpaca-paper", {"symbol": "BTC/USD"}).to_dict()
SPY = BUYER.replace('"BTC/USD"', '"SPY"')
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mullins_14_candidate.json"
#: meriwether-h2d625d-2's own account of its program (its `agent.strategy` row, 00:22:20Z Sept 24, 2026).
TAKER_FIX = ("Fix two defects in the deployed deep-favourites rule. (1) The taker/taker side loses ~1.1% on Kalshi and the "
             "firm-measured edge on >90c favourites is on the MAKER side (+2.15c/contract resting post-only bids), yet the "
             "current file buys at the ask (marketable, taker). Switch to post-only resting bids at the bid (2-way favourite YES) "
             "and at the NO bid = 1-yes_ask (3-way soccer longshot complement). (2) The current file never read open_orders, so "
             "an unfilled resting bid would stack a duplicate intent every 30-min wake; now skip markets with an existing working order.")
#: mullins-14's birth reason (Sept 22, 2026): a safety change of a MAKER parent that says "post-only" without naming a defect.
MAKER_SAFETY = ("Test a narrowly falsifiable safety hypothesis after the failed 12-hour all-series candidate: restricting the "
                "favourite-maker NO strategy to rain markets, which produced the strongest observed live and replay subgroup, "
                "while enforcing hours_to_resolve<=48, per-market event-risk capacity, free-cash reservation, and a strictly "
                "below-current-ask post-only price. Acceptance is the normal replay gate; otherwise retain the deployed strategy.")


class EvidenceCase(SeatCase):
    def buy(self, agent, *, liquidity="taker", book="alpaca-paper", instrument=BTC):
        self.house.ledger.append("book.fill", {"book": book, "instrument": instrument, "side": "buy", "quantity": "0.001",
                                               "price": "60000", "source": "venue", "liquidity": liquidity}, agent=agent.id)

    def close(self, agent, n=1):
        for _ in range(n):
            self.house.ledger.append("book.fill", {"book": "alpaca-paper", "instrument": BTC, "side": "sell", "quantity": "0.001",
                                                   "price": "61000", "source": "venue", "realized": "1.0", "flat": True}, agent=agent.id)

    def desk_clock(self, hours, desk=DESK):
        """A desk's evidence clock as `evidence_clocks` stores it, measured now."""
        self.house._state["evidence_clocks"] = {"at": "now", "epoch": self.clock(), "desks": {desk: {"hours": hours}}}

    def proven(self, *families):
        """The allocator's family record, with `families` proven (the record Deploy A introduced)."""
        real = self.house.allocator.family

        def family(name, venue):
            record = dict(real(name, venue))
            if name in families:
                record.update(proven=True, state="proven")
            return record

        return patch.object(self.house.allocator, "family", side_effect=family)


class EvidenceClocks(EvidenceCase):
    def test_the_kaplan_meier_median_censors_the_ones_still_waiting(self):
        self.assertEqual(kaplan_meier_median([(10.0, True), (20.0, True), (30.0, False)]), 20.0)
        self.assertEqual(kaplan_meier_median([(5.0, False), (8.0, False), (9.0, True)]), 9.0)
        self.assertIsNone(kaplan_meier_median([(10.0, True), (20.0, False), (30.0, False)]))
        self.assertIsNone(kaplan_meier_median([]))

    def test_a_desks_clock_is_the_median_hours_from_first_fill_to_the_third_independent_settlement(self):
        quick, slow, waiting = self.seated("quick"), self.seated("slow"), self.seated("waiting")
        idle = self.seated("idle", SPY)  # the index-ETF desk: one fill, never a settlement
        for agent in (quick, slow, waiting, idle):
            self.buy(agent)
        self.clock.advance(10 * 3600)
        self.close(quick, 3)
        self.clock.advance(10 * 3600)
        self.close(slow, 3)
        self.clock.advance(10 * 3600)
        self.close(waiting, 2)  # two of three at 30 h: still waiting, and counted as such
        clocks = self.house.evidence_clocks(fresh=True)
        desk = clocks["desks"][DESK]
        self.assertEqual((desk["members"], desk["reached"], desk["hours"]), (3, 2, 20.0))
        self.assertIsNone(clocks["desks"][idle.specialty]["hours"])  # not reached: the plain grace stands
        self.assertEqual(self.house._desk_clocks(), {DESK: 20.0 * 3600})
        self.assertEqual(self.house._state["evidence_clocks"]["epoch"], self.clock())
        self.house._save_state()
        saved = json.loads((Path(self.house.root) / "house.json").read_text())
        self.assertEqual(saved["evidence_clocks"]["desks"][DESK]["hours"], 20.0)
        self.assertEqual(len(alerts(self.house, "info", "evidence clock")), 1)

    def test_the_clocks_are_measured_at_startup_and_again_each_day(self):
        started = House(Path(self.dir.name) / "fresh", brokers={"alpaca-paper": FakeBroker("alpaca-paper")},
                        sandbox=LocalSandbox(Path(self.dir.name) / "fresh-boxes"), clock=self.clock,
                        settings=Settings(mark_every_seconds=0, research=False))
        try:
            self.assertEqual(started._state["evidence_clocks"]["epoch"], self.clock())
        finally:
            started.close(wait=None)
        first = self.house.evidence_clocks()["epoch"]
        self.clock.advance(3600)
        self.assertEqual(self.house.evidence_clocks()["epoch"], first)
        self.clock.advance(86400)
        self.assertEqual(self.house.evidence_clocks()["epoch"], self.clock())


class TheEvidenceClock(EvidenceCase):
    def test_a_trader_keeps_its_seat_until_its_desks_evidence_clock_has_run(self):
        trader = self.seated("trader")
        self.buy(trader)  # one fill: the forward rule is for three
        self.desk_clock(20.0)
        self.clock.advance(self.grace + 1)
        self.assertIsNone(self.house._weakest(self.rules), "the twelve-hour grace has run, the desk's twenty-hour clock has not")
        self.clock.advance(20 * 3600 - self.grace)
        self.assertEqual(self.house._weakest(self.rules).id, trader.id)

    def test_the_clock_never_shortens_the_plain_grace(self):
        trader = self.seated("trader")
        self.buy(trader)
        self.desk_clock(1.9)  # kalshi-crypto-15m's clock at T0
        self.clock.advance(self.grace - 60)
        self.assertIsNone(self.house._weakest(self.rules))
        self.clock.advance(61)
        self.assertEqual(self.house._weakest(self.rules).id, trader.id)

    def test_a_trader_with_three_fills_is_displaced_only_by_a_newcomer_with_a_better_forward_record(self):
        trader = self.seated("trader")
        for _ in range(3):
            self.buy(trader)
        self.clock.advance(self.grace + 1)
        with patch.object(self.house, "_resident_forward", return_value=-0.001):
            self.assertIsNone(self.house._weakest(self.rules), "a newcomer with no forward score")
            self.assertIsNone(self.house._weakest(self.rules, newcomer=Newcomer(forward=-0.002)), "a worse forward record")
            self.assertIsNone(self.house._weakest(self.rules, newcomer=Newcomer(forward=-0.001)), "an equal one is not better")
            self.assertEqual(self.house._weakest(self.rules, newcomer=Newcomer(forward=0.0005)).id, trader.id)
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=Newcomer(forward=0.0005)),
                              "a trader short of its record keeps its seat against an evidenced newcomer (`_trading_pending` stands)")
        with patch.object(self.house, "_resident_forward", return_value=None):
            self.assertIsNone(self.house._weakest(self.rules, newcomer=Newcomer(forward=0.01)),
                              "no forward record of its own yet: nothing to compare, so it keeps its seat")
        two = self.seated("two")
        self.buy(two)
        self.buy(two)
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, two.id, "two fills: the forward rule does not apply")

    def test_a_proven_familys_resident_is_never_displaced_by_an_unproven_newcomer(self):
        trader = self.seated("trader")
        self.buy(trader)
        idle = self.seated("idle")
        proven = Newcomer(family="test-family", venue="alpaca")
        with self.proven("test-family"):
            self.clock.advance(600)
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True), "a proven family's never-traded seat inside its grace")
            self.assertEqual(self.house._weakest(self.rules, evidenced=True, newcomer=proven).id, idle.id)
            self.clock.advance(self.grace)
            self.assertEqual(self.house._weakest(self.rules).id, idle.id, "a never-traded resident past its grace still goes first")
            self.house.kill(idle, "displaced", "test")
            self.clock.advance(float(self.house.settings.tick_seconds) + 1)
            self.assertIsNone(self.house._weakest(self.rules), "a proven family's trader")
            self.assertIsNone(self.house._weakest(self.rules, evidenced=True, newcomer=Newcomer(family="another", venue="alpaca")))
            self.assertEqual(self.house._weakest(self.rules, newcomer=proven).id, trader.id)

    def test_a_losing_familys_trader_is_displaced_before_the_other_traders(self):
        gone = self.house.spawn("gone", "losing-family", BUYER, reason="a test agent")
        self.house.evaluator.seat(gone.id, 1, "test")
        self.blocks(gone, -0.01, 6)
        self.house.kill(gone, "evidence", "a test death")
        loser = self.house.spawn("loser", "losing-family", BUYER, reason="a test agent")
        self.house.evaluator.seat(loser.id, 1, "test")
        self.buy(loser)
        self.blocks(loser, 0.0, 1)
        other = self.seated("other")
        self.buy(other)
        self.blocks(other, -0.005, 1)
        self.clock.advance(self.grace + 1)
        self.assertEqual(self.house._weakest(self.rules).id, loser.id, "its family's pooled record is negative after six blocks")


class TradingPending(EvidenceCase):
    def test_a_kalshi_trader_with_three_independent_settlements_has_its_record(self):
        """The allocator's bunt line reads `bunt_min_settled` on an event book; `_trading_pending` read only
        `bunt_min_trades` (the Sept 24 review)."""
        agent = self.seated("kalshi")
        for market in ("KXHIGHNY-26SEP24-T70", "KXHIGHCHI-26SEP24-T65", "KXRAIN-26SEP24-NYC"):
            self.house.ledger.append("book.settle", {"book": "kalshi-shadow", "payout": "10", "pnl": "0.5",
                                                     "instrument": {"asset_class": "event", "market_id": market, "symbol": market,
                                                                    "venue": "kalshi-shadow", "right": "no"}}, agent=agent.id)
        now = self.clock()
        self.assertFalse(self.house._trading_pending(agent, SimpleNamespace(name="kalshi-shadow"), now - 60, now, self.rules))
        self.assertTrue(self.house._trading_pending(agent, SimpleNamespace(name="alpaca-paper"), now - 60, now, self.rules),
                        "an Alpaca book has no settled route: five closed trades")


class SeatsHoldingNothing(EvidenceCase):
    def test_the_hourly_watch_names_the_seats_with_no_forward_score_no_fill_and_no_grace(self):
        idle = self.seated("idle")
        trader = self.seated("trader")
        self.buy(trader)
        self.clock.advance(self.grace + 1)
        self.seated("young")  # its grace still runs
        report = self.house._seat_market_watch(fresh=True)
        self.assertEqual(report["seats_holding_none"], {"count": 1, "ids": [idle.id]})
        with patch.object(self.house, "_resident_forward", return_value=0.001):
            self.assertEqual(self.house._seat_market_watch(fresh=True)["seats_holding_none"], {"count": 0, "ids": []})
        self.assertIn("evidence_clocks", report)
        self.house._health({"at": "now"})
        health = json.loads((Path(self.house.root) / "health.json").read_text())
        self.assertIn("seats_holding_none", health["seats"])


class RetainedCandidates(EvidenceCase):
    """S3: a resident that dies holding a replay-passed candidate hands it to the seat queue."""

    def setUp(self):
        super().setUp()
        self.house.close(wait=None)  # a House with a Kalshi practice book too, for mullins-14's weather candidate
        from league.economy import load_game

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.shadow = FakeBroker("kalshi-shadow", family="kalshi")
        self.house = House(Path(self.dir.name) / "house-retained",
                           brokers={"alpaca-paper": self.broker, "kalshi-shadow": self.shadow},
                           sandbox=LocalSandbox(Path(self.dir.name) / "boxes-retained"), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False), game=game)
        self.rules = self.house.game["economy"]

    def retained(self, code, *, purpose="a retained test candidate", trades=40, niche=DESK):
        from league import niches as niches_module

        needs = niches_module.constrain(static_literal(code, "NEEDS"), self.house.niches[niche])
        return {"code": code, "params": static_literal(code, "PARAMS"), "needs": needs, "passed": True, "purpose": purpose,
                "numbers": {"trades": trades, "passed": True, "return_pct": 12.0}}

    def queued(self, author, candidate, session, *, status="deferred"):
        queue = Admissions(self.house.ledger)
        row = queue.enqueue(author.id, self.house._generation(author.id), candidate, session)
        queue.record(row, status, "niche is full; waiting for an eligible seat")
        return row

    def row(self, session):
        return next(r for r in Admissions(self.house.ledger).rows() if r["session"] == session)

    def test_a_resident_that_dies_holding_a_candidate_hands_it_to_the_seat_queue_and_it_is_seated_first(self):
        author = self.seated("author")
        candidate = self.retained(BUYER + "\n# a better program\n")
        self.queued(author, candidate, "research:author:1")
        living = self.seated("living")
        self.queued(living, self.retained(BUYER + "\n# the living author's candidate\n"), "research:living:1")
        self.house.kill(author, "displaced", "test")
        self.assertEqual(self.row("research:author:1")["status"], "orphaned")
        waiters = self.house.seat_waiters(fresh=True)["retained"]
        self.assertEqual([(w["author"], w["niche"], w["session"]) for w in waiters], [(author.id, DESK, "research:author:1")])
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual((child.parent, child.code, child.family), (author.id, candidate["code"], author.family))
        self.assertEqual(self.house.evaluator.rung(child.id), 1)
        self.assertEqual(self.house.registry.lineage(child.id)[:2], [child.id, author.id])
        self.assertEqual(self.row("research:author:1")["status"], "admitted")
        self.assertEqual(self.row("research:living:1")["status"], "deferred", "the dead author's candidate went first")
        self.assertEqual(self.house.seat_waiters(fresh=True)["retained"], [])
        route = self.house.ledger.get(f"birth-route:{child.id}")
        self.assertEqual(route.payload["route"], "retained")

    def test_only_the_authors_latest_passing_candidate_is_handed_on(self):
        author = self.seated("author")
        self.queued(author, self.retained(BUYER + "\n# older\n"), "research:author:1")
        self.clock.advance(60)
        self.queued(author, self.retained(BUYER + "\n# newer\n"), "research:author:2")
        failed = self.retained(BUYER + "\n# failed\n")
        failed["passed"] = False
        self.clock.advance(60)
        self.queued(author, failed, "research:author:3")
        self.house.kill(author, "displaced", "test")
        self.assertEqual([self.row(f"research:author:{n}")["status"] for n in (1, 2, 3)], ["deferred", "orphaned", "deferred"])

    def test_mullins_14s_candidate_cancelled_with_its_author_before_the_deploy_is_seated_first(self):
        """The test case: mullins-14 died at 00:12:02Z Sept 24 and its admissions were cancelled "parent retired or
        changed; candidate evidence retained" (01:38:54Z). After the deploy the House finds the latest and seats it."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        written = fixture["author"]
        author = self.house.spawn("mullins", written["family"], written["code"], reason="the weather desk's rain favourites")
        self.house.evaluator.seat(author.id, 1, "test")
        self.assertEqual(author.specialty, "kalshi-weather")
        candidate = {k: fixture["candidate"][k] for k in ("code", "params", "needs", "passed", "purpose", "numbers")}
        session = fixture["admission"]["session"]
        row = self.queued(author, candidate, session)
        self.house.registry.died(author.id, "displaced", "the seat market before Deploy B: no hand-off")
        Admissions(self.house.ledger).record(row, "cancelled", fixture["admission"]["cancelled_reason"])
        living = self.seated("living")
        self.queued(living, self.retained(BUYER + "\n# waiting since before\n"), "research:living:1")
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertIsNotNone(child)
        self.assertEqual((child.parent, child.family, child.specialty), (author.id, "weather-favorites", "kalshi-weather"))
        self.assertEqual(child.code, fixture["candidate"]["code"])
        self.assertEqual(child.params, fixture["candidate"]["params"])
        self.assertEqual(child.needs["max_hours_to_close"], 18)
        self.assertEqual(self.row(session)["status"], "admitted")
        self.assertEqual(self.house.evaluator.rung(child.id), 1)

    def test_a_candidate_nobody_can_make_room_for_waits_is_told_and_expires(self):
        author = self.seated("author")
        self.queued(author, self.retained(BUYER + "\n# waiting\n"), "research:author:1")
        self.house.kill(author, "displaced", "test")
        self.house.niches[DESK].max_members = 1
        resident = self.seated("resident")
        self.house.evaluator.promote(resident.id, 2, "test: real money")
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(len(alerts(self.house, "warning", "retained research candidate")), 1)
        self.assertEqual(len(self.house.seat_waiters(fresh=True)["retained"]), 1)
        self.clock.advance(self.house.RETAINED_TTL_SECONDS)
        self.assertIsNone(self.house._refill(self.rules))
        self.assertEqual(self.row("research:author:1")["status"], "dropped")
        self.assertEqual(self.house.seat_waiters(fresh=True)["retained"], [])


class CorrectedChildren(EvidenceCase):
    """L1: meriwether-h2d625d (taker entries on real money) and its child meriwether-h2d625d-2 (the maker fix,
    passed replay 00:18:31Z Sept 24) while the parent kept trading."""

    CHILD = BUYER.replace("test-buyer", "test-maker")

    def parent(self, *, liquidity="taker", rung=2):
        parent = self.seated("meriwether")
        for _ in range(3):
            self.buy(parent, liquidity=liquidity)
        if rung >= 2:
            self.house.evaluator.promote(parent.id, 2, "test: real money")
        return parent

    def child(self, parent, reason, *, passed=True):
        child = self.house.spawn(parent.line or parent.name, parent.family, self.CHILD, parent=parent.id, reason=reason)
        self.house.evaluator.seat(child.id, 1, "its code passed replay as its parent's candidate")
        self.house.ledger.append("agent.forked", {"child": child.id, "new_code": True, "staked_by": "house", "reason": reason,
                                                  "endowment_usd": "8", "box_forked": False}, agent=parent.id)
        self.house.ledger.append("eval.trial", {"passed": passed, "code_sha256": child.code_sha256, "family": parent.family,
                                                "trades": 40, "reasons": []}, agent=parent.id)
        return child

    def supersedes(self):
        return patch.dict(CONSTITUTION["allocator"], {"corrected_child_supersedes": True})

    def test_a_child_that_fixes_its_real_money_parents_taker_entry_supersedes_it(self):
        parent = self.parent()
        child = self.child(parent, TAKER_FIX)
        with self.supersedes():
            self.house.enroll()
        gone = self.house.registry.get(parent.id)
        self.assertFalse(gone.alive)
        self.assertEqual(gone.cause, "superseded")
        demoted = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=parent.id) if e.payload.get("decision") == "demote"]
        self.assertEqual([(d["from_rung"], d["to_rung"]) for d in demoted], [(2, 1)])
        self.assertIn(child.id, demoted[0]["reason"])
        self.assertEqual(demoted[0]["band_to"], "paper")
        self.assertTrue(self.house.registry.get(child.id).alive)
        self.assertEqual(self.house.evaluator.rung(child.id), 1, "the allocator seats the child on its own evidence")

    def test_without_the_constitution_key_nothing_is_superseded(self):
        parent = self.parent()
        self.child(parent, TAKER_FIX)
        self.assertNotIn("corrected_child_supersedes", {k for k, v in CONSTITUTION["allocator"].items() if v})
        self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive)
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)

    def test_a_maker_parent_is_not_superseded_by_a_child_that_mentions_post_only(self):
        """mullins-2, the floor's best real record, rests maker bids; mullins-14's reason says "post-only"."""
        parent = self.parent(liquidity="maker")
        self.child(parent, MAKER_SAFETY)
        self.child(parent, TAKER_FIX)  # a taker complaint about a maker parent's code is not its defect
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)

    def test_a_practice_parent_is_retired_by_the_research_route_too(self):
        parent = self.parent(rung=1)
        self.child(parent, TAKER_FIX)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 1)
        self.assertEqual(self.house.registry.get(parent.id).cause, "superseded")
        self.assertEqual([e for e in self.house.ledger.iter(kinds="eval.verdict", agent=parent.id) if e.payload.get("decision") == "demote"], [])

    def test_a_child_whose_program_has_not_passed_replay_supersedes_nobody(self):
        parent = self.parent()
        self.child(parent, TAKER_FIX, passed=False)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive)


if __name__ == "__main__":
    import unittest

    unittest.main()
