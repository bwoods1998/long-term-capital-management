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
from league.agents import code_sha
from league.house import House, Newcomer, Settings, entry_defect, kaplan_meier_median, posts_maker_entries
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
#: The review of #245 (Sept 24, 2026), the floor's own words (T0 snapshot). meriwether-h2d625d-2's BIRTH reason: its
#: parent's research replaced the KXMLBTOTAL program with another mechanism (moneyline favourites, a taker file). Its
#: later rewrite (`TAKER_FIX`) fixed THAT file's taker entry, which its parent never ran.
H2D_BIRTH = ("Replace the unsupported KXMLBTOTAL coin-flip under entries with the specialty's previously measured, "
             "series-routed pregame heavy-favourite moneyline hypothesis: CFB favourite YES or soccer underdog NO, with "
             "liquidity, spread, timing, resolution, fee and position limits.")
#: meriwether-44's birth reason (22:07Z Sept 23): a liquidity claim in the words "the wrong side".
WRONG_SIDE = ("Genuinely new hypothesis for this line (not a duplicate of the 102 WNBA/football/soccer taker trials): a "
              "post-only MAKER bid on 90-98c YES favourites in maker-free soft cricket moneylines (KXT20MATCH, KXWT20MATCH), "
              "pre-game. My deployed 90-98c TAKER on maker-fee major-sport moneylines is idle midweek and is the wrong side; "
              "the favourite-longshot bias lives in maker-free soft moneyline books and is only captured passively as a maker.")
#: meriwether's rewrite of Sept 21, 2026: from resting orders TO market orders -- makers and takers named, no maker fix.
TO_TAKER = ("Two independent, peer-proven fixes to reverse my 8-trade/0-fill collapse: (1) switch entry from limit-at-ask (which "
            "replay treats as a resting maker order, and which cancelled 12/12 forward paper orders with 0 fills) to "
            'type="market" for a guaranteed taker fill; (2) replace the totals series with a passing 12-series set.')
#: "The opposite side" says what is bought, not that anything was wrong.
OPPOSITE_SIDE = ("Replace the idle rule with a falsifiable variant: rest a NO bid, the opposite side of the 90c favourite, "
                 "pre-game, held to settlement.")
#: A program that rests its entries post-only (a maker), and another program that takes, as the parents here do.
MAKER = BUYER.replace("test-buyer", "test-maker").replace(
    '"type": "market", "reason": "test buy"', '"type": "limit", "limit_price": 59000, "post_only": True, "reason": "test maker bid"')
MONEYLINE = BUYER.replace("test-buyer", "test-moneyline")


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

    def test_the_houses_closing_sales_are_not_a_members_settlements(self):
        """The review of #245 (Sept 24, 2026): the House's sale of a dead member's holdings ("the House is closing
        this account") counted as the member's settlement, so a member with two closes that died holding a third
        position "reached" its third settlement at its death. The House's closing sales are the House's: a forced
        exit at death says nothing of how long the desk's markets take (the scoreboard's own-fill rule)."""
        member = self.seated("member")
        self.buy(member)
        self.clock.advance(3600)
        self.close(member, 2)
        self.house.registry.died(member.id, "displaced", "test")
        self.clock.advance(60)
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "instrument": BTC, "side": "sell", "quantity": "0.001",
                                               "price": "61000", "source": "venue", "realized": "1.0", "flat": True,
                                               "reason": "the House is closing this account"}, agent=member.id)
        desk = self.house.evidence_clocks(fresh=True)["desks"][DESK]
        self.assertEqual((desk["members"], desk["reached"]), (1, 0), "censored at its death: its third close was the House's")
        self.assertEqual(desk["longest_waiting_hours"], 1.0)

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
            with patch.object(self.house, "_forward_scorable", return_value=True):
                self.assertIsNone(self.house._weakest(self.rules, newcomer=Newcomer(forward=0.01)),
                                  "no forward record of its own YET: nothing to compare, so it keeps its seat")
            with patch.object(self.house, "_forward_scorable", return_value=False):
                self.assertEqual(self.house._weakest(self.rules, newcomer=Newcomer(forward=0.01)).id, trader.id,
                                 "no record it could ever have (the lab never scores it): judged as before, never kept for good")
        two = self.seated("two")
        self.buy(two)
        self.buy(two)
        self.clock.advance(self.grace + 1)
        with patch.object(self.house, "_forward_scorable", return_value=True):  # the trader waits for its record
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

    def test_the_seats_protection_and_the_bunt_line_read_one_record(self):
        """The invariant: for every count of closed trades and settlements on either kind of book, the
        seat's protection ends exactly when the allocator's bunt line (`allocator.bunt_ready`) has its
        record -- never a line of its own."""
        from league import allocator as allocator_module

        agent = self.seated("any")
        line = allocator_module._params()
        now = self.clock()
        for book, venue in (("kalshi-shadow", "kalshi"), ("alpaca-paper", "alpaca")):
            for closed in range(7):
                for settled in range(min(closed, 5) + 1):
                    evidence = SimpleNamespace(paper_trades=closed, venue=venue, e=10.0,
                                               paper_settled=settled if book in allocator_module.EVENT_BOOKS else 0)
                    with patch.object(allocator_module, "closed_trades", return_value=(closed, settled)):
                        pending = self.house._trading_pending(agent, SimpleNamespace(name=book), now - 60, now, self.rules)
                    self.assertEqual(pending, not allocator_module.bunt_ready(evidence, line), (book, closed, settled))


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

    def test_a_proven_familys_retained_candidate_is_seated_before_an_older_unproven_one(self):
        """At T0 fourteen authors had died holding candidates within the day; only mullins-14's family
        (weather-favorites) was proven, and it died after ten of them: the seat follows proof first."""
        older = self.seated("older")
        self.queued(older, self.retained(BUYER + "\n# an unproven family's\n"), "research:older:1")
        self.house.kill(older, "displaced", "test")
        self.clock.advance(3600)
        author = self.house.spawn("author", "proven-family", BUYER + "\n# its own\n", reason="a test agent")
        self.house.evaluator.seat(author.id, 1, "test")
        self.queued(author, self.retained(BUYER + "\n# a proven family's\n"), "research:author:1")
        self.house.kill(author, "displaced", "test")
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.clock.advance(601)
        with self.proven("proven-family"):
            self.assertEqual([w["author"] for w in self.house.seat_waiters(fresh=True)["retained"]], [author.id, older.id])
            child = self.house._refill(self.rules)
        self.assertEqual(child.parent, author.id)
        self.assertEqual(self.row("research:older:1")["status"], "orphaned")

    def test_a_candidate_handed_on_during_an_admission_pass_is_not_cancelled_by_it(self):
        """The review of #245 (Sept 24, 2026): the pass folds the admission rows once. An admission displaced a
        resident, whose candidate went to the seat queue; the admission then seated nobody, and the loop reached the
        dead author's row as folded ("deferred") and cancelled it: the retained candidate was lost."""
        living = self.seated("living")
        self.queued(living, self.retained(BUYER + "\n# the living author's candidate\n"), "research:living:1")
        loser = self.seated("loser")
        self.queued(loser, self.retained(BUYER + "\n# the loser's own candidate\n"), "research:loser:1")
        self.rules.update(newcomer_seconds=600, max_population=2)
        self.clock.advance(self.grace + 601)
        with patch.object(self.house, "fork", return_value=None):  # capacity or endowment unavailable after the kill
            self.assertIsNone(self.house._refill(self.rules))
        self.assertFalse(self.house.registry.get(loser.id).alive)
        self.assertEqual(self.row("research:loser:1")["status"], "orphaned")
        self.assertEqual([w["session"] for w in self.house.seat_waiters(fresh=True)["retained"]], ["research:loser:1"])
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual((child.parent, self.row("research:loser:1")["status"]), (loser.id, "admitted"), "and it is seated next")

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

    CHILD = MAKER  # the maker fix: its entries rest post-only (`posts_maker_entries`)

    def parent(self, *, liquidity="taker", rung=2):
        parent = self.seated("meriwether")
        for _ in range(3):
            self.buy(parent, liquidity=liquidity)
        if rung >= 2:
            self.house.evaluator.promote(parent.id, 2, "test: real money")
        return parent

    def child(self, parent, reason, *, passed=True, code=None):
        """A child born from its parent's research candidate (a fork with new code, House-staked)."""
        child = self.house.spawn(parent.line or parent.name, parent.family, code or self.CHILD, parent=parent.id, reason=reason)
        self.house.evaluator.seat(child.id, 1, "its code passed replay as its parent's candidate")
        self.house.ledger.append("agent.forked", {"child": child.id, "new_code": True, "staked_by": "house", "reason": reason,
                                                  "endowment_usd": "8", "box_forked": False}, agent=parent.id)
        self.house.ledger.append("eval.trial", {"passed": passed, "code_sha256": child.code_sha256, "family": parent.family,
                                                "trades": 40, "reasons": []}, agent=parent.id)
        return child

    def rewrite(self, child, code, reason):
        """A paper child with no record rewrites itself as `House._commit_research` writes it: the research row
        (`Registry.adopt`), then the House's row with `was`, and the replay the new file passed."""
        was = self.house.registry.get(child.id).code_sha256
        needs, params = dict(static_literal(code, "NEEDS")), dict(static_literal(code, "PARAMS"))
        self.house.registry.adopt(child.id, code=code, needs=needs, params=params, reason=reason)
        self.house.ledger.append("agent.strategy", {"code_sha256": code_sha(code), "was": was, "reason": "it rewrote itself: it had no "
                                                    "record to protect", "passed_replay": True, "_code": code, "params": params,
                                                    "needs": needs}, agent=child.id)
        self.house.ledger.append("eval.trial", {"passed": True, "code_sha256": code_sha(code), "family": child.family, "trades": 40,
                                                "reasons": []}, agent=child.id)
        return self.house.registry.get(child.id)

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
        """Off and absent alike, whatever the live constitution says (B-families' #242 turns it on for Deploy B:
        the review of #245 found this test asserted the key's absence from the constitution itself)."""
        parent = self.parent()
        self.child(parent, TAKER_FIX)
        with patch.dict(CONSTITUTION["allocator"], {"corrected_child_supersedes": False}):
            self.assertEqual(self.house._supersede_by_research(), 0)
        with patch.dict(CONSTITUTION["allocator"], {}):
            CONSTITUTION["allocator"].pop("corrected_child_supersedes", None)
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive)
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 1, "and on, the same pair is superseded")

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


    # The review of #245 (Sept 24, 2026). Each failed on the branch as built.
    def test_a_childs_rewrite_of_its_own_earlier_program_is_not_its_parents_defect(self):
        """The live case: meriwether-h2d625d trades KXMLBTOTAL unders (6 real taker fills, 5 of 5 real settlements
        won); its child was born with ANOTHER program (moneyline favourites, taker) and at 00:22Z Sept 24 fixed the
        taker entry of THAT file. L1's first pass retired the parent for it."""
        parent = self.parent()
        child = self.child(parent, H2D_BIRTH, code=MONEYLINE)
        self.rewrite(child, MAKER, TAKER_FIX)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive, "the parent never ran the program its child fixed")
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)

    def test_a_childs_rewrite_of_its_parents_own_program_supersedes_the_parent(self):
        """The rewrite route where the account IS the parent's: a copy of the parent's program (a House mutation)
        fixed in place, with the parent still running that program."""
        parent = self.parent()
        child = self.house.spawn(parent.line or parent.name, parent.family, parent.code, parent=parent.id,
                                 params={"notional": 15.0}, reason="a parameter mutation of its parent")
        self.house.evaluator.seat(child.id, 1, "test")
        self.rewrite(child, MAKER, TAKER_FIX)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 1)
        self.assertEqual(self.house.registry.get(parent.id).cause, "superseded")

    def test_a_birth_account_of_a_program_the_parent_has_since_replaced_is_not_its_defect(self):
        parent = self.parent(rung=1)
        self.child(parent, TAKER_FIX)
        self.house.registry.adopt(parent.id, code=MONEYLINE, needs=dict(static_literal(MONEYLINE, "NEEDS")),
                                  params=dict(static_literal(MONEYLINE, "PARAMS")), reason="the parent's own rewrite since")
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive)

    def test_the_wrong_side_of_a_maker_edge_is_a_liquidity_claim_and_spares_a_maker_parent(self):
        """meriwether-44's words: as a "side" defect (any entry at all) it retired a MAKER parent."""
        self.assertEqual(entry_defect(WRONG_SIDE), "liquidity")
        parent = self.parent(liquidity="maker")
        self.child(parent, WRONG_SIDE)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)

    def test_the_opposite_side_names_no_defect(self):
        self.assertIsNone(entry_defect(OPPOSITE_SIDE))
        self.assertEqual(entry_defect("Fix the wrong side: buy YES, not NO, on the favourite."), "side")
        parent = self.parent(liquidity="maker")
        self.child(parent, OPPOSITE_SIDE)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertTrue(self.house.registry.get(parent.id).alive)

    def test_a_child_that_moves_to_market_orders_is_no_maker_fix(self):
        """meriwether's rewrite of Sept 21 names makers, takers and a fix: a taker parent is not retired for a child
        that takes too. The maker fix is a program that rests its entries post-only."""
        self.assertEqual(entry_defect(TO_TAKER), "liquidity")
        self.assertFalse(posts_maker_entries(MONEYLINE))
        self.assertTrue(posts_maker_entries(MAKER))
        parent = self.parent()
        self.child(parent, TO_TAKER, code=MONEYLINE)
        with self.supersedes():
            self.assertEqual(self.house._supersede_by_research(), 0)
        self.assertEqual(self.house.evaluator.rung(parent.id), 2)

if __name__ == "__main__":
    import unittest

    unittest.main()
