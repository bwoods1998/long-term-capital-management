"""The mechanism ledger and the family swing (C1, C2 and C4 of the close-the-gaps run; Deploy B, Sept 24, 2026).

`league/families.py` is the one place a family's record is computed: every member ever born, one
observation an independent event, practice at half weight, the one-sided 80% lower bound and, for a
favourites record, the House's loss-rate bound. Since C1 an event is measured by what it made per
dollar its positions put at risk (the T0 snapshot: a practice row was growth on a $200 purse and a
real row on a $30-60 stake, so real rows weighed three to seven times their declared weight, and the
account unit moves with the stake a swing itself grows). The family swing stakes every member of a
family whose REAL record qualifies at a ramp above the bunt, audited on first entry.

`league/tests/test_promotion_on_proof.py` keeps Deploy A's account-unit arithmetic as the rollback form.
"""

import math
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator, families
from league.constitution import CONSTITUTION, digest, money_digest
from league.tests.test_promotion_on_proof import MERIWETHER_BUYS, MERIWETHER_SETTLES, KalshiHouse, LedgerCase, hand_pool

D = Decimal
P = allocator._params
F = 0.01  # `family_proven.reference_share`


def v(r):
    """An event's value in the at-risk unit: ln(1 + 1% x r) / 1%, r never below -1."""
    return math.log1p(F * max(r, -1.0)) / F


class AtRiskCase(LedgerCase):
    """A bare ledger and a registry: the at-risk unit of the constitution (`family_proven.unit`)."""

    def setUp(self):
        super().setUp()
        self.agents = {}
        self.house = SimpleNamespace(ledger=self.ledger, registry=SimpleNamespace(agents=self.agents))

    def member(self, agent, family="weather-favorites", venue="kalshi", alive=True):
        self.agents[agent] = SimpleNamespace(id=agent, family=family, venue=venue, alive=alive)

    def record(self, family="weather-favorites", venue="kalshi", **kw):
        return families.family_record(self.house, family, venue, **kw)


class AtRiskRecord(AtRiskCase):
    """C1: an event is what it made per dollar its positions put at risk, as log growth at a 1% bet."""

    def test_the_constitution_measures_an_event_at_risk(self):
        rule = families.proof_rule()
        self.assertEqual((rule["unit"], rule["reference_share"]), ("at_risk", 0.01))

    def test_an_event_is_what_it_made_per_dollar_at_risk(self):
        self.member("m1")
        self.stake(200, agent="m1")
        self.buy("KXHIGHNY-26SEP24-B72.5", 10, "0.60", agent="m1")  # $6 at risk
        self.settle("KXHIGHNY-26SEP24-B72.5", "4", agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["unit"]), (1, "at_risk"))
        self.assertAlmostEqual(rec["mean_log"], v(4 / 6), places=12)
        self.assertAlmostEqual(rec["edge_per_dollar"], 4 / 6, places=12)

    def test_a_contract_that_expires_worthless_is_finite(self):
        """A binary contract that expires worthless is -100% of its position: ln(1 - 1%) / 1%, not the ruin a log
        of zero would be; a loss past the cost (an exit fee) is still -100%."""
        self.member("m1")
        self.stake(200, agent="m1")
        self.buy("KXHIGHNY-26SEP24-B72.5", 10, "0.95", agent="m1")
        self.settle("KXHIGHNY-26SEP24-B72.5", "-9.50", agent="m1")
        self.buy("KXHIGHMIA-26SEP24-B90.5", 10, "0.95", agent="m1")
        self.settle("KXHIGHMIA-26SEP24-B90.5", "-9.60", agent="m1")
        rec = self.record()
        self.assertEqual(rec["n"], 2)
        self.assertAlmostEqual(rec["mean_log"], math.log(0.99) / 0.01, places=12)
        self.assertTrue(math.isfinite(rec["bound"]))

    def test_the_same_bet_on_a_purse_and_on_a_stake_is_the_same_observation(self):
        """The unit's point (the T0 snapshot): a $9.30 favourite bid on the $200 practice purse and on a $30 real
        stake are one mechanism's bet; on account growth the real one counted 6.7 times the other."""
        self.member("p")
        self.member("r")
        self.stake(200, agent="p")
        self.stake(30, agent="r", book="kalshi")
        self.buy("KXHIGHNY-26SEP24-B72.5", 10, "0.93", agent="p")
        self.settle("KXHIGHNY-26SEP24-B72.5", "0.70", agent="p")
        self.buy("KXHIGHMIA-26SEP24-B90.5", 10, "0.93", agent="r", book="kalshi")
        self.settle("KXHIGHMIA-26SEP24-B90.5", "0.70", agent="r", book="kalshi")
        rec = self.record()
        self.assertEqual((rec["n"], rec["real"]["n"]), (2, 1))
        self.assertAlmostEqual(rec["mean_log"], v(0.70 / 9.30), places=12)
        self.assertAlmostEqual(rec["real"]["mean_log"], rec["mean_log"], places=12)  # the real event is worth the practice one
        with patch.dict(CONSTITUTION["allocator"]["family_proven"], {"unit": "account"}):  # the rollback, by the key
            account = self.record()
        self.assertAlmostEqual(account["mean_log"], (0.5 * math.log1p(0.7 / 200) + math.log1p(0.7 / 30)) / 1.5, places=12)

    def test_weights_and_the_bound_by_hand(self):
        for agent in ("m1", "m2"):
            self.member(agent)
        self.member("m3", alive=False)  # the dead count
        self.stake(200, agent="m1")
        self.stake(200, agent="m2")
        self.stake(30, agent="m2", book="kalshi")
        self.stake(200, agent="m3")
        self.buy("KXHIGHNY-26SEP24-B72.5", 10, "0.90", agent="m1")          # E1 practice: +1 on $9
        self.settle("KXHIGHNY-26SEP24-B72.5", "1", agent="m1")
        self.buy("KXHIGHNY-26SEP24-B74.5", 10, "0.80", agent="m2")          # E1 again, another member: the same bet
        self.settle("KXHIGHNY-26SEP24-B74.5", "2", agent="m2")
        self.buy("KXHIGHMIA-26SEP24-B90.5", 10, "0.50", agent="m1")         # E2 practice: +5 on $5
        self.settle("KXHIGHMIA-26SEP24-B90.5", "5", agent="m1")
        self.buy("KXHIGHAUS-26SEP24-T96", 5, "0.60", agent="m2", book="kalshi")  # E3 REAL: -3 on $3
        self.settle("KXHIGHAUS-26SEP24-T96", "-3", agent="m2", book="kalshi")
        self.buy("KXHIGHLAX-26SEP24-B80.5", 10, "0.40", agent="m3")         # E4 practice, a dead member: +1 on $4
        self.settle("KXHIGHLAX-26SEP24-B80.5", "1", agent="m3")
        rec = self.record()
        # Each event weighs what it put at risk against its member's mean on that book: m1's practice events put $9 and $5
        # at risk (a $7 mean); m2's and m3's one event on each book weigh their book's weight (review of #242).
        w1, w2 = 0.5 * 9 / 7, 0.5 * 5 / 7
        e1 = (v(1 / 9) * w1 + v(2 / 8) * 0.5) / (w1 + 0.5)
        obs = [(e1, max(w1, 0.5)), (v(5 / 5), w2), (v(-1), 1.0), (v(1 / 4), 0.5)]
        m, sd, n_eff, bound = hand_pool(obs)
        self.assertEqual((rec["n"], rec["real_n"], rec["members"], rec["members_living"], rec["members_counted"]), (4, 1, 3, 2, 3))
        self.assertAlmostEqual(rec["mean_log"], m, places=12)
        self.assertAlmostEqual(rec["sd"], sd, places=12)
        self.assertAlmostEqual(rec["n_eff"], n_eff, places=12)
        self.assertAlmostEqual(rec["bound"], bound, places=12)
        self.assertFalse(rec["proven"])

    def test_stacked_strikes_are_one_observation_at_their_total_risk(self):
        """D4's event, in the at-risk unit: three strikes of one game are ONE bet worth what they made over what
        the three put at risk together (meriwether-h7d7702's two games, Sept 23)."""
        self.member("m1")
        self.stake(200, agent="m1")
        for ticker, quantity, price in MERIWETHER_BUYS:
            self.buy(ticker, quantity, price, agent="m1")
        for ticker, pnl in MERIWETHER_SETTLES:
            self.settle(ticker, pnl, agent="m1")
        rec = self.record()
        self.assertEqual(rec["n"], 2)
        game = lambda rows, buys: sum(float(p) for _, p in rows) / sum(q * float(c) for _, q, c in buys)  # noqa: E731
        risk = lambda buys: sum(q * float(c) for _, q, c in buys)  # noqa: E731
        first, second = risk(MERIWETHER_BUYS[:3]), risk(MERIWETHER_BUYS[3:])  # each game weighs what it put at risk
        expected = (v(game(MERIWETHER_SETTLES[:3], MERIWETHER_BUYS[:3])) * first
                    + v(game(MERIWETHER_SETTLES[3:], MERIWETHER_BUYS[3:])) * second) / (first + second)
        self.assertAlmostEqual(rec["mean_log"], expected, places=12)
        self.assertEqual((rec["taker"]["n"], rec["maker"]["n"]), (2, 0))

    def test_a_record_that_lost_its_money_on_its_big_bets_is_not_proven(self):
        """Review of #242: weighed alike, 86 wins of $0.40 on $1.60 and 14 whole losses of $5.60 -- $44 of real money lost
        -- read +0.074 an event with a bound of +0.037 and a loss-rate bound of +0.027: proven, and ready for the family
        swing to stake it up. A resting bid filled in full as the price falls through it makes exactly this record. Each
        event now weighs what it put at risk, and the record is what its dollars say."""
        self.member("m1")
        self.stake(30, agent="m1", book="kalshi")
        for i in range(100):
            ticker = f"KXHIGHNY-26SEP{i % 28 + 1:02d}{i // 28:02d}-B72.5"
            lost = i % 7 == 6
            self.buy(ticker, 7 if lost else 2, "0.80", agent="m1", book="kalshi", liquidity="maker")
            self.settle(ticker, "-5.60" if lost else "0.40", agent="m1", book="kalshi")
        rec = self.record()
        self.assertEqual((rec["n"], rec["real"]["n"]), (100, 100))
        self.assertAlmostEqual(rec["edge_per_dollar"], -44 / (86 * 1.6 + 14 * 5.6), places=9)  # sum made / sum at risk
        self.assertLess(rec["mean_log"], 0)
        self.assertFalse(rec["proven"])
        self.assertFalse(families.swing_ready(rec, families.swing_rule()))

    def test_maker_and_taker_records_apart(self):
        self.member("mk")
        self.member("tk")
        for agent in ("mk", "tk"):
            self.stake(200, agent=agent)
        for day in range(1, 11):
            ticker = f"KXHIGHNY-26SEP{day:02d}-B72.5"
            self.buy(ticker, 10, "0.60", agent="mk", liquidity="maker")
            self.settle(ticker, "2.5" if day % 3 else "-2", agent="mk")  # 7 of 10 win: not lopsided
            other = f"KXETH15M-26SEP{day:02d}1200-00"
            self.buy(other, 10, "0.50", agent="tk", liquidity="taker")
            self.settle(other, "-5" if day % 2 else "4", agent="tk")
        rec = self.record()
        self.assertEqual((rec["maker"]["n"], rec["taker"]["n"], rec["n"]), (10, 10, 20))
        maker = hand_pool([(v((2.5 if d % 3 else -2) / 6), 0.5) for d in range(1, 11)])
        self.assertAlmostEqual(rec["maker"]["mean_log"], maker[0], places=12)
        self.assertAlmostEqual(rec["maker"]["bound"], maker[3], places=12)
        self.assertTrue(rec["maker"]["positive"])
        self.assertFalse(rec["taker"]["positive"])

    def test_a_close_with_no_cost_on_record_is_never_a_win(self):
        """A settlement whose buy the ledger does not hold (carried in): a loss is a whole loss, a profit a scratch."""
        self.member("m1")
        self.stake(200, agent="m1")
        self.settle("KXHIGHNY-26SEP24-B72.5", "2", agent="m1")
        self.settle("KXHIGHMIA-26SEP24-B90.5", "-2", agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["rows_without_risk"]), (2, 2))
        self.assertAlmostEqual(rec["mean_log"], (v(0.0) + v(-1.0)) / 2, places=12)

    def test_a_favourites_record_needs_its_loss_rate_bound_at_risk_too(self):
        """Ten 95c favourites that all paid: the t bound is above zero, the loss-rate bound is not (one miss in
        seven cannot be ruled out at 80%, and one miss costs nineteen wins), in the at-risk unit as in the account one."""
        self.member("m1")
        self.stake(200, agent="m1")
        for day in range(1, 11):
            ticker = f"KXHIGHNY-26SEP{day:02d}-B72.5"
            self.buy(ticker, 10, "0.95", agent="m1", liquidity="maker")
            self.settle(ticker, "0.5", agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["lopsided"]), (10, True))
        self.assertGreater(rec["bound"], 0)
        self.assertLess(rec["loss_gate"], 0)
        self.assertEqual(rec["honest_bound"], rec["loss_gate"])
        self.assertFalse(rec["proven"])

    def test_the_real_record_is_the_real_book_alone_with_each_events_first_close(self):
        self.member("m1")
        self.stake(200, agent="m1")
        self.stake(30, agent="m1", book="kalshi")
        self.buy("KXHIGHNY-26SEP24-B72.5", 10, "0.90", agent="m1")
        self.settle("KXHIGHNY-26SEP24-B72.5", "1", agent="m1")
        self.buy("KXHIGHMIA-26SEP24-B90.5", 5, "0.90", agent="m1", book="kalshi")
        self.settle("KXHIGHMIA-26SEP24-B90.5", "0.5", agent="m1", book="kalshi")
        first = self.ledger.head()[0]
        self.buy("KXHIGHAUS-26SEP24-B90.5", 5, "0.90", agent="m1", book="kalshi")
        self.settle("KXHIGHAUS-26SEP24-B90.5", "-4.5", agent="m1", book="kalshi")
        rec = self.record()
        self.assertEqual((rec["n"], rec["real"]["n"]), (3, 2))
        self.assertEqual([seq for seq, _ in rec["real"]["first_closes"]], [first, self.ledger.head()[0]])
        self.assertAlmostEqual(rec["real"]["first_closes"][0][1], v(0.5 / 4.5), places=12)
        self.assertAlmostEqual(rec["real"]["first_closes"][1][1], v(-1.0), places=12)
        self.assertEqual(families.positive_since(rec, first - 1), 1)
        self.assertEqual(families.positive_since(rec, first), 0)

    def test_every_members_active_blocks(self):
        self.member("m1")
        self.member("gone", alive=False)
        self.member("other", family="sports-favorites")
        for agent, book, active, growth in (("m1", "kalshi-shadow", True, 0.01), ("m1", "kalshi-shadow", False, 0.0),
                                            ("m1", "kalshi", True, -0.02), ("gone", "kalshi-shadow", True, 0.03),
                                            ("other", "kalshi-shadow", True, 0.5)):
            self.ledger.append("eval.block", {"book": book, "active": active, "log_growth": growth, "key": "k"}, agent=agent)
        rec = self.record()
        self.assertEqual((rec["blocks"]["practice"], rec["blocks"]["real"]), (2, 1))
        self.assertAlmostEqual(rec["blocks"]["growth"], 0.02, places=12)


class Capacity(AtRiskCase):
    """E3: capacity is measured -- markets a family bids a day, the fill rate by size, settlements a day, and the
    dollars a day that implies at the stake."""

    def bid(self, agent, market, quantity, price, *, book="kalshi-shadow", filled=False, n=[0]):
        n[0] += 1
        order = f"ord-{n[0]}"
        inst = {"asset_class": "event", "market_id": market, "symbol": market, "venue": book, "multiplier": "1"}
        for status in ("new", "accepted"):  # an order has several rows; it is one bid
            self.ledger.append("book.order", {"book": book, "order_id": order, "side": "buy", "status": status, "limit_price": price,
                                              "quantity": str(quantity), "instrument": inst,
                                              "shares": [{"agent": agent, "quantity": str(quantity), "intent_id": f"in-{order}"}]})
        if filled:
            self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "order_id": order, "instrument": inst,
                                             "quantity": str(quantity), "price": price, "cash_delta": str(-quantity * float(price)),
                                             "liquidity": "maker"}, agent=agent)

    def test_fill_rates_by_size_and_the_dollars_a_day_at_the_stake(self):
        self.member("m1")
        self.stake(200, agent="m1")
        for i in range(6):  # $9 bids: 4 of 6 markets filled
            self.bid("m1", f"KXHIGHNY-26SEP{i + 1:02d}-B72.5", 10, "0.90", filled=i < 4)
        for i in range(5):  # $18 bids: 1 of 5 filled
            self.bid("m1", f"KXHIGHMIA-26SEP{i + 1:02d}-B90.5", 20, "0.90", filled=i < 1)
        self.clock.advance(2 * 86400)  # two days of bids
        self.buy("KXHIGHNY-26SEP01-B72.5", 1, "0.90", agent="m1")
        self.settle("KXHIGHNY-26SEP01-B72.5", "0.10", agent="m1")  # an edge of 0.10 / 0.90 a dollar at risk
        rec = self.record(now=self.clock(), stake_usd=30)
        cap = rec["capacity"]
        self.assertEqual(cap["fill_rates"]["<=$12"], {"markets_bid": 6, "markets_filled": 4, "fill_rate": 4 / 6, "basis": "all"})
        self.assertEqual(cap["fill_rates"]["$12-25"]["markets_filled"], 1)
        self.assertEqual((cap["size_usd"], cap["size_bucket"], cap["fill_rate_at_size"]), (6.0, "<=$12", 4 / 6))  # 20% of $30
        self.assertAlmostEqual(cap["markets_per_day"], 11 / 2, places=6)
        self.assertAlmostEqual(cap["usd_per_day"], 11 / 2 * (4 / 6) * (0.10 / 0.90) * 6.0, places=6)
        rates = cap["fill_rates"]
        # A swing from a $60 stake to $120 moves a position from $12 to $24: 0.2 filled at $12-25 is under half of 0.67.
        self.assertTrue(families.capacity_holds(rates, 12.0, 24.0, ratio=0.5, min_markets=5))
        self.assertFalse(families.capacity_holds(rates, 6.0, 12.0, ratio=0.5, min_markets=5))  # one bucket
        self.assertFalse(families.capacity_holds(rates, 12.0, 24.0, ratio=0.5, min_markets=6))  # $12-25 not measured enough
        self.assertFalse(families.capacity_holds(rates, 24.0, 48.0, ratio=0.5, min_markets=5))  # never bid that large

    def test_no_bid_is_no_estimate(self):
        self.member("m1")
        cap = self.record(now=self.clock(), stake_usd=30)["capacity"]
        self.assertIsNone(cap["usd_per_day"])
        self.assertIn("no bid", cap["why"])


def real_record(n=15, bound=0.02, variance=0.5, closes=None, unit="at_risk", proven=True, family="weather-favorites", entry=None,
                dates=None):
    """A family record whose REAL record is set by the test: `closes` are (first close seq, value). Its entry look
    (`families.entry_look`) stands at its real count's checkpoint and passes with a positive bound unless `entry` says.
    `dates`: the distinct settlement dates its real record spans (M1, Sept 25, 2026), one an event unless the test says;
    the pooled record spans as many as its count."""
    rec = families.empty_record(family, "kalshi")
    rec.update(unit=unit, n=max(n, 10), proven=proven, state="proven" if proven else "unproven", bound=0.01 if proven else -0.01,
               real_n=n, members=2, members_living=2, members_counted=2, dates=max(n, 10))
    rule = families.swing_rule()
    checkpoint = families.entry_checkpoint(n, rule) if rule else None
    look = {"checkpoint": checkpoint, "next_checkpoint": None, "confidence": (rule or {}).get("entry_confidence"),
            "honest_bound": bound, "ready": (checkpoint is not None and bound is not None and bound > 0) if entry is None else entry}
    look["dates_so_far"] = n if dates is None else dates  # the dates its events span now (M1)
    rec["real"] = {**rec["real"], "n": n, "bound": bound, "honest_bound": bound, "variance": variance, "entry": look,
                   "first_closes": closes if closes is not None else [(i + 1, 0.05) for i in range(n)],
                   "dates": n if dates is None else dates}
    return rec


class SwingRules(unittest.TestCase):
    """C2's arithmetic: the entry at 10 real settlements (15 before M1, Sept 25, 2026) with a positive honest bound, the
    ramp's doubling at every 10 further positive ones, the Kelly and venue caps shared by the members, the capacity hold,
    the bunt floor."""

    def setUp(self):
        self.rule = families.swing_rule()

    def target(self, record, members=1, entered=15, rates=None, capital="517.75"):
        return families.swing_target(record, rule=self.rule, venue="kalshi", bunt_usd="30", venue_capital=capital,
                                     members_real=members, entered_seq=entered, rates=rates)

    def test_the_constitutions_rule(self):
        self.assertEqual({k: self.rule[k] for k in ("min_real_settlements", "start_multiple", "doubling_every", "min_distinct_dates")},
                         {"min_real_settlements": 10, "start_multiple": 2.0, "doubling_every": 10, "min_distinct_dates": 5})
        self.assertEqual((self.rule["kelly_fraction"], self.rule["max_share_of_venue"]), (1.0, 0.6))  # rung 3's, the allocator's
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["family_swing"]
            self.assertIsNone(families.swing_rule())  # no key, no family swing
            self.assertFalse(families.swing_ready(real_record(), families.swing_rule()))

    def test_the_hold_needs_10_real_settlements_on_5_dates_and_a_positive_honest_bound(self):
        self.assertFalse(families.swing_ready(real_record(n=9), self.rule))
        self.assertTrue(families.swing_ready(real_record(n=10), self.rule))
        self.assertFalse(families.swing_ready(real_record(n=40, dates=4), self.rule))  # M1: a regime is not an edge
        self.assertTrue(families.swing_ready(real_record(n=40, dates=5), self.rule))
        self.assertFalse(families.swing_ready(real_record(n=40, bound=0.0), self.rule))
        self.assertFalse(families.swing_ready(real_record(n=40, bound=None), self.rule))

    def test_a_favourites_real_record_must_clear_its_loss_rate_bound(self):
        """Honest for lopsided records (the 04:15Z decision): fifteen real 93c favourites that all paid have a t
        bound far above zero, and no swing, until losses on record say the loss rate is under breakeven."""
        clean = {f"e{i}": [(v(0.07 / 0.93), 1.0)] for i in range(15)}
        real = families.pool(clean, 10, 0.8, win_rate=0.8, risk=F, scale=F)
        self.assertGreater(real["bound"], 0)
        self.assertLess(real["loss_gate"], 0)
        self.assertEqual(real["honest_bound"], real["loss_gate"])
        record = real_record()
        record["real"] = {**record["real"], **real}
        self.assertFalse(families.swing_ready(record, self.rule))
        # Thirty clean ones clear it at 93c (an 80% upper bound of 5.2% on the loss rate against 7% breakeven).
        clean = {f"e{i}": [(v(0.07 / 0.93), 1.0)] for i in range(30)}
        record["real"] = {**record["real"], **families.pool(clean, 10, 0.8, win_rate=0.8, risk=F, scale=F)}
        self.assertTrue(families.swing_ready(record, self.rule))
        # Its Kelly variance is the loss-rate model's, not the no-loss sample's zero.
        self.assertGreater(record["real"]["variance"], 0.04)

    def test_the_ramp_starts_at_twice_the_bunt_and_doubles_every_ten_positive_settlements(self):
        """The worked example: 15 real settlements at $30 bunts start the family at $60 a member; ten more
        POSITIVE ones make it $120; a negative one never counts toward a doubling."""
        base = [(i + 1, 0.05) for i in range(15)]
        strong = dict(bound=0.5, variance=0.5)  # Kelly well above the ramp: the ramp is what is under test
        self.assertEqual(self.target(real_record(closes=base, **strong))["stake_usd"], D("60.00"))
        nine = base + [(100 + i, 0.04) for i in range(9)] + [(200 + i, -0.3) for i in range(5)]
        row = self.target(real_record(closes=nine, **strong))
        self.assertEqual((row["stake_usd"], row["positive_since_entry"], row["next_doubling_in"]), (D("60.00"), 9, 1))
        ten = nine + [(300, 0.02)]
        row = self.target(real_record(closes=ten, **strong))
        self.assertEqual((row["stake_usd"], row["level"], row["limit"]), (D("120.00"), 1, "ramp"))
        twenty = ten + [(400 + i, 0.02) for i in range(10)]
        self.assertEqual(self.target(real_record(closes=twenty, **strong))["stake_usd"], D("240.00"))
        self.assertEqual(self.target(real_record(closes=twenty, **strong), entered=None)["stake_usd"], D("60.00"))  # no entry yet

    def test_the_venue_share_caps_the_family_and_its_members_share_it(self):
        """$310.65 is 0.6 x $517.75: the family's, shared by its members on real money (members of one family bid
        the same markets: two at 60% each would be one mechanism at 120% of the venue)."""
        closes = [(i + 1, 0.05) for i in range(15)] + [(100 + i, 0.05) for i in range(30)]  # level 3: $480
        one = self.target(real_record(closes=closes, bound=1.0))
        self.assertEqual((one["stake_usd"], one["limit"], one["venue_share_usd"]), (D("310.65"), "venue_share", D("310.65")))
        two = self.target(real_record(closes=closes, bound=1.0), members=2)
        self.assertEqual((two["stake_usd"], two["limit"]), (D("155.32"), "venue_share"))

    def test_kelly_on_the_bound_caps_a_thin_record(self):
        """Full Kelly (rung 3's fraction) on the REAL record's honest bound: 0.02 over a variance of 0.5 puts 4% of
        the venue at risk an event, a stake of 4% / 25% (the most of a stake one Kalshi event may hold, the book's
        `max_event_share`) of $517.75 = $82.84. Review of #242: over the position's 20% ($103.55) a member could put 25%
        of its stake on one event's strikes, 1.25 x Kelly on the bound."""
        closes = [(i + 1, 0.05) for i in range(15)] + [(100 + i, 0.05) for i in range(10)]  # the ramp at $120
        row = self.target(real_record(closes=closes, bound=0.02, variance=0.5))
        self.assertEqual((row["stake_usd"], row["limit"], row["kelly_usd"]), (D("82.84"), "kelly", D("82.84")))
        self.assertAlmostEqual(row["kelly_fraction_at_risk"], 0.04, places=12)
        # The most the book lets one event hold at that stake is Kelly's capital at risk an event, never more.
        event = D(str(CONSTITUTION["allocator"]["max_event_share"])) * row["stake_usd"]
        self.assertLessEqual(event, D("0.04") * D("517.75"))
        self.assertEqual(families.event_share("kalshi"), 0.25)
        self.assertEqual(families.event_share("alpaca"), float(CONSTITUTION["allocator"]["position_share"]))  # a trade is an event
        thin = self.target(real_record(bound=0.001, variance=0.5))  # Kelly under the bunt: a proven family keeps its bunt
        self.assertEqual((thin["stake_usd"], thin["limit"]), (D("30"), "bunt"))
        crowded = self.target(real_record(bound=1.0), members=12)  # 310.65 / 12 = 25.88, under the bunt
        self.assertEqual((crowded["stake_usd"], crowded["limit"]), (D("30"), "bunt"))

    def test_capacity_holds_the_ramp_where_fills_at_the_bigger_size_halve(self):
        closes = [(i + 1, 0.05) for i in range(15)] + [(100 + i, 0.05) for i in range(10)]  # the ramp at $120: $24 positions
        thin = {"<=$12": {"markets_bid": 10, "fill_rate": 0.6}, "$12-25": {"markets_bid": 8, "fill_rate": 0.25}}
        row = self.target(real_record(closes=closes, bound=1.0), rates=thin)
        self.assertEqual((row["stake_usd"], row["limit"], row["held_level"], row["level"]), (D("60.00"), "capacity", 0, 1))
        deep = {"<=$12": {"markets_bid": 10, "fill_rate": 0.6}, "$12-25": {"markets_bid": 8, "fill_rate": 0.35}}
        self.assertEqual(self.target(real_record(closes=closes, bound=1.0), rates=deep)["stake_usd"], D("120.00"))
        unmeasured = {"<=$12": {"markets_bid": 10, "fill_rate": 0.6}, "$12-25": {"markets_bid": 3, "fill_rate": 0.0}}
        self.assertEqual(self.target(real_record(closes=closes, bound=1.0), rates=unmeasured)["stake_usd"], D("120.00"))

    def test_the_account_unit_sizes_kelly_on_the_account(self):
        """The rollback unit: Kelly's fraction is of the account, not of the capital at risk."""
        closes = [(i + 1, 0.05) for i in range(15)] + [(100 + i, 0.05) for i in range(10)]
        row = self.target(real_record(closes=closes, bound=0.002, variance=0.05, unit="account"))
        self.assertEqual((row["stake_usd"], row["limit"]), (D("30"), "bunt"))  # 0.04 x $517.75 = $20.71: the bunt
        row = self.target(real_record(closes=closes, bound=0.01, variance=0.05, unit="account"))
        self.assertEqual((row["stake_usd"], row["limit"]), (D("103.55"), "kelly"))

    def test_the_states(self):
        """"proven" follows the pooled record alone; a proven family ENTERS on its entry look and an approved audit, and
        STAYS while its real record holds at 80%; leaving returns it to bunts (probes when the proof went too)."""
        s = families.next_state
        self.assertEqual(s("unproven", proven=False, entry=False, hold=False, approved=False), "unproven")
        self.assertEqual(s("unproven", proven=True, entry=False, hold=False, approved=False), "proven")
        self.assertEqual(s("proven", proven=True, entry=True, hold=True, approved=False), "proven")  # the entry waits for its audit
        self.assertEqual(s("proven", proven=True, entry=True, hold=True, approved=True), "swing")
        self.assertEqual(s("proven", proven=True, entry=False, hold=True, approved=True), "proven")  # no passing look, no entry
        self.assertEqual(s("swing", proven=True, entry=False, hold=True, approved=False), "swing")  # staying needs the hold only
        self.assertEqual(s("swing", proven=True, entry=True, hold=False, approved=True), "proven")  # the bound fell: bunts
        self.assertEqual(s("swing", proven=False, entry=True, hold=True, approved=True), "unproven")  # the proof went: probes
        # The main session's decision on the review of #242: the real record alone neither proves nor swings a family.
        self.assertEqual(s("unproven", proven=False, entry=True, hold=True, approved=True), "unproven")
        self.assertEqual(s("proven", proven=False, entry=True, hold=True, approved=True), "unproven")


GATE = dict(win_rate=0.8, risk=F, scale=F)  # the loss-rate gate's reading of an at-risk record (`family_record`)
WIN, LOSS = v(0.5), v(-0.5)
#: Fifteen events whose honest bound is above zero at 80% and below it at 90% (10 wins and 5 losses, not lopsided).
FIFTEEN = [WIN, WIN, LOSS] * 5


def events(values):
    """Real events as `pool` observes them: (first close, value, weight)."""
    return [(i + 1, value, 1.0) for i, value in enumerate(values)]


def dated(values, per_day=1):
    """Each event's own settlement date (M1, Sept 25, 2026), `per_day` events a date, by first close."""
    return {i + 1: f"2026-10-{i // per_day + 1:02d}" for i in range(len(values))}


def look(values, rule, per_day=1):
    return families.entry_look(events(values), rule, gate=GATE, days=dated(values, per_day))


class EntryLooks(unittest.TestCase):
    """Finding 10 of the review of #242, the main session's decision (Sept 24, 2026): the swing's ENTRY is judged only at
    `min_real_settlements` real settlements and every `entry_every` more, on the first that many real events, at
    `entry_confidence` for the t bound and the loss-rate bound alike; staying (and the ramp's doubling) is the whole real
    record at the table's 80% at every pass. An edgeless family re-read at every settlement at 80% entered 37% of the time
    by 30 real settlements and 44% by 50; at every 5th at 90%, 19% and 22%."""

    def setUp(self):
        self.rule = families.swing_rule()

    def test_the_constitutions_entry_rule(self):
        self.assertEqual((self.rule["entry_every"], self.rule["entry_confidence"]), (5, 0.9))
        with patch.dict(CONSTITUTION["allocator"]["family_swing"]):
            del CONSTITUTION["allocator"]["family_swing"]["entry_every"]
            del CONSTITUTION["allocator"]["family_swing"]["entry_confidence"]
            self.assertEqual((families.swing_rule()["entry_every"], families.swing_rule()["entry_confidence"]), (1, 0.8))  # #242's

    def test_the_checkpoints_are_10_then_every_5(self):
        c = lambda n: families.entry_checkpoint(n, self.rule)  # noqa: E731
        self.assertEqual([c(n) for n in (0, 9, 10, 14, 15, 16, 19, 20, 24, 25, 41)],
                         [None, None, 10, 10, 15, 15, 15, 20, 20, 25, 40])

    def test_the_entry_is_the_first_checkpoint_events_at_90_percent(self):
        look = families.entry_look(events(FIFTEEN), self.rule, gate=GATE, days=dated(FIFTEEN))
        self.assertEqual((look["checkpoint"], look["next_checkpoint"], look["confidence"]), (15, 20, 0.9))
        self.assertLess(look["honest_bound"], 0)
        self.assertFalse(look["ready"])
        at_80 = families.pool({str(i): [(x, 1.0)] for i, x in enumerate(FIFTEEN)}, 10, 0.8, **GATE)
        self.assertGreater(at_80["honest_bound"], 0)  # the look #242 took, at every settlement, would have entered here

    def test_a_failed_look_waits_for_the_next_checkpoint(self):
        """Four more wins make the 19 events' 90% bound positive, but 19 is no checkpoint: the look at 15 stands. The
        twentieth settlement is the next look, on the first 20."""
        nineteen = FIFTEEN + [WIN] * 4
        all_19 = families.pool({str(i): [(x, 1.0)] for i, x in enumerate(nineteen)}, 10, 0.9, **GATE)
        self.assertGreater(all_19["honest_bound"], 0)
        seen = look(nineteen, self.rule)
        self.assertEqual((seen["checkpoint"], seen["ready"]), (15, False))
        self.assertEqual(seen["honest_bound"], look(FIFTEEN, self.rule)["honest_bound"])
        seen = look(nineteen + [WIN], self.rule)
        self.assertEqual((seen["checkpoint"], seen["ready"]), (20, True))

    def test_a_favourites_entry_needs_its_loss_rate_bound_at_90_percent(self):
        """Clean 93c favourites: the loss-rate bound clears zero after 23 at 80% and after 32 at 90%: the look at 30 fails
        and the look at 35 passes, while staying at 80% already holds at 30."""
        win = v(0.07 / 0.93)
        seen = look([win] * 30, self.rule)
        self.assertEqual((seen["checkpoint"], seen["ready"]), (30, False))
        self.assertLess(seen["loss_gate"], 0)
        self.assertGreater(seen["bound"], 0)  # the t bound alone would have let it in
        hold = families.pool({str(i): [(win, 1.0)] for i in range(30)}, 10, 0.8, **GATE)
        self.assertTrue(families.swing_ready({"real": {**hold, "dates": 30}}, self.rule))
        seen = look([win] * 35, self.rule)
        self.assertEqual((seen["checkpoint"], seen["ready"]), (35, True))

    def test_staying_is_the_whole_record_at_80_percent_at_every_pass(self):
        """The exit side needs no correction: a swinging family stays while its whole record's 80% bound holds, at any
        count, a count between checkpoints included."""
        for n in (15, 17, 23):
            values = (FIFTEEN + [WIN] * 10)[:n]
            hold = families.pool({str(i): [(x, 1.0)] for i, x in enumerate(values)}, 10, 0.8, **GATE)
            self.assertTrue(families.swing_ready({"real": {**hold, "dates": n}}, self.rule), n)
        lost = families.pool({str(i): [(x, 1.0)] for i, x in enumerate(FIFTEEN + [LOSS] * 3)}, 10, 0.8, **GATE)
        self.assertFalse(families.swing_ready({"real": {**lost, "dates": 18}}, self.rule))


class EntryLookOnTheLedger(AtRiskCase):
    """`family_record` carries the entry look, from the ledger alone: a restart looks at exactly the same events."""

    def settle_real(self, values):
        start = getattr(self, "settled", 0)
        self.settled = start + len(values)
        for i, won in enumerate(values, start):
            ticker = f"KXHIGHNY-26SEP{i % 28 + 1:02d}{i // 28:02d}-B72.5"  # one event each
            self.buy(ticker, 10, "0.50", agent="m1", book="kalshi", liquidity="maker")  # $5 at risk
            self.settle(ticker, "2.5" if won else "-2.5", agent="m1", book="kalshi")  # +50% or -50% of it

    def test_the_record_carries_the_look_at_its_checkpoint(self):
        self.member("m1")
        self.stake(30, agent="m1", book="kalshi")
        pattern = [True, True, False] * 5
        self.settle_real(pattern + [True] * 2)  # 17 real events: the look is still the one at 15
        record = self.record()
        self.assertEqual(record["real"]["n"], 17)
        self.assertEqual((record["real"]["entry"]["checkpoint"], record["real"]["entry"]["ready"]), (15, False))
        self.assertTrue(families.swing_ready(record, families.swing_rule()))  # it would stay, were it in
        self.assertFalse(families.entry_ready(record, families.swing_rule()))
        again = families.family_record(self.house, "weather-favorites", "kalshi", tape=families.TradeTape())  # a restart
        self.assertEqual(again["real"]["entry"], record["real"]["entry"])
        self.settle_real([True] * 3)  # the twentieth settlement: the next look, on the first 20
        record = self.record()
        self.assertEqual((record["real"]["entry"]["checkpoint"], record["real"]["entry"]["ready"]), (20, True))
        self.assertTrue(families.entry_ready(record, families.swing_rule()))


class FamilySwingOnTheFloor(KalshiHouse):
    """C2 in a House: the first family swing is audited on the family's REAL record, then every member on real
    money is staked at the ramp; the bound falling returns them to bunts by free cash; the envelope bounds every
    increase."""

    READY = dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6, paper_settled=6)

    def setUp(self):
        super().setUp()
        room = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"})
        room.start()
        self.addCleanup(room.stop)
        self.verdicts = []
        approve = self.auditor.audit

        def audit(agent, verdict, **kwargs):
            self.verdicts.append(verdict)
            family = verdict.numbers.get("family_swing")
            if family:
                # As the real auditor writes a family swing's verdict (`Auditor.audit`): against the member, naming the family.
                row = {"approve": self.auditor.approve, "summary": "test", "family_swing": family}
                self.house.ledger.append("audit.verdict", row, agent=agent.id)
                return row
            return approve(agent, verdict)

        self.auditor.audit = audit

    def seated_bunts(self, n=2):
        self.families["weather-favorites"] = real_record(n=5, bound=-0.5)  # proven on the pooled record, 5 real events
        agents = [self.agent(f"kay{i}") for i in range(n)]
        self.table = {a.id: dict(self.READY) for a in agents}
        with self.evidence_of(self.table):
            self.tick()
        book = self.house.books["kalshi"]
        self.assertEqual([book.account(a.id).staked for a in agents], [D("30")] * n)
        return agents, book

    def rebalance(self):
        with self.evidence_of(self.table):
            return self.house.allocator.rebalance()

    def test_the_first_family_swing_is_audited_then_every_member_is_staked_at_twice_the_bunt(self):
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        self.rebalance()
        self.assertEqual(alloc.family_state(a), "proven")  # the first entry waits for its audit
        self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("30")] * 2)
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)
        verdict = self.verdicts[0]
        context = verdict.numbers["allocation_context"]
        self.assertEqual((verdict.numbers["via"], verdict.numbers["book"], verdict.numbers["family_swing"]),
                         ("family_swing", "kalshi", "weather-favorites@kalshi"))
        self.assertEqual((context["family_swing"], context["band_to"], context["stake_usd"], context["members_on_real_money"]),
                         (True, "swing", "60.00", 2))
        self.assertEqual(verdict.numbers["family_packet"]["real_record"]["n"], 15)
        self.rebalance()
        self.assertEqual(alloc.family_state(a), "swing")
        self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("60.00")] * 2)
        row = alloc.board()["agents"][a.id]
        self.assertEqual((row["band"], row["family_state"], row["stake_limit"]), ("swing", "swing", "ramp"))
        self.assertEqual(alloc.band_of(a.id), "swing")  # the book's daily-loss rule of every stake above the bunt
        self.assertEqual(alloc.tier(a), "bunt")  # its proof: a swinging family's member is a proven family's
        family = alloc.board()["families"]["kalshi"]["weather-favorites"]
        self.assertEqual((family["state"], family["members_real"], family["stake_usd"], family["real"]["n"]), ("swing", 2, "60.00", 15))
        self.assertEqual(book.limits[a.id].max_position_usd, D("12.00"))  # a fifth of $60
        self.rebalance()
        self.assertEqual(len(self.verdicts), 1)  # audited once

    def test_a_vetoed_family_swing_stays_in_bunts_until_the_cooldown_passes(self):
        (a, _), book = self.seated_bunts()
        self.auditor.approve = False
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)
        self.assertEqual(self.house.allocator.family_state(a), "proven")
        self.assertEqual(book.account(a.id).staked, D("30"))
        self.clock.advance(float(self.house.game["audit"]["cooldown_hours"]) * 3600 + 60)
        self.auditor.approve = True
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual(len(self.verdicts), 2)
        self.assertEqual(self.house.allocator.family_state(a), "swing")

    def swinging(self):
        agents, book = self.seated_bunts()
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual([book.account(x.id).staked for x in agents], [D("60.00")] * 2)
        return agents, book

    def test_the_ramp_doubles_after_ten_more_positive_real_settlements(self):
        agents, book = self.swinging()
        entered = self.house.allocator.state["families"]["weather-favorites@kalshi"]["entered_seq"]
        closes = [(i + 1, 0.05) for i in range(15)] + [(entered + 1 + i, 0.05) for i in range(10)]
        # Kelly above the ramp's $120 (0.08 / 0.5 of $500 at risk an event, over a 25% event share: $160 a member).
        self.families["weather-favorites"] = real_record(n=25, bound=0.08, closes=closes)
        self.rebalance()
        self.assertEqual([book.account(x.id).staked for x in agents], [D("120.00")] * 2)
        swing = self.house.allocator.family("weather-favorites", "kalshi")["swing"]
        self.assertEqual((swing["level"], swing["positive_since_entry"], swing["limit"]), (1, 10, "ramp"))

    def test_a_bound_that_falls_returns_the_members_to_bunts_by_free_cash(self):
        agents, book = self.swinging()
        submitted = len(self.real.submitted)
        self.families["weather-favorites"] = real_record(n=16, bound=-0.01)
        self.rebalance()
        alloc = self.house.allocator
        self.assertEqual(alloc.family_state(agents[0]), "proven")
        self.assertEqual([book.account(x.id).staked for x in agents], [D("30.00")] * 2)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual(alloc.board()["agents"][agents[0].id]["band"], "bunt")
        self.assertEqual(alloc.state["families"]["weather-favorites@kalshi"]["was"], "swing")
        # Leaving the swing lapsed its approval (the main session's decision on the review of #242): the bound back above
        # zero, the family asks for a new audit and re-enters on that one.
        self.assertEqual(alloc.state["family_audits"]["weather-favorites@kalshi"]["status"], "lapsed")
        self.families["weather-favorites"] = real_record(n=17, bound=0.05)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "proven")
        self.house.wait(5)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")
        self.assertEqual(len(self.verdicts), 2)

    def test_newcomers_share_a_swinging_familys_caps_from_their_first_dollar(self):
        """Review of #242: the pass's record shared the family's caps among the members it counted on real money when the
        pass began, so two practice members seated into the family in one pass were each lent the ONE-member share: the
        family held $150 against its $50 Kelly cap until the next pass (and longer at those limits had they traded)."""
        (a,), book = self.seated_bunts(1)
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=15, bound=0.01, variance=0.5)  # Kelly binds, under the ramp's $60
        self.rebalance(); self.house.wait(5); self.rebalance()
        cap = D(alloc.family("weather-favorites", "kalshi")["swing"]["kelly_usd"])
        self.assertEqual(book.account(a.id).staked, cap)
        news = [self.agent(f"new{i}") for i in range(2)]
        self.table.update({n.id: dict(self.READY) for n in news})
        self.rebalance()
        # Shared three ways the Kelly cap is under the bunt, which a proven family's member keeps: $30 each, and the member
        # already seated is swept back to it by free cash in the same pass.
        self.assertEqual([book.account(x.id).staked for x in (a, *news)], [D("30.00")] * 3)
        record = alloc.family("weather-favorites", "kalshi")
        self.assertEqual((record["members_real"], record["swing"]["members_real"]), (3, 3))
        for n in news:  # each lent its share from its first dollar (and the envelope checked that), never swept back to it
            lent = [D(e.payload["usd"]) for e in self.house.ledger.iter(kinds="book.stake", agent=n.id) if e.payload.get("book") == "kalshi"]
            self.assertEqual(lent, [D("30.00")])

    def test_the_swing_holds_only_while_the_grant_releases_stakes_above_the_bunt(self):
        """Review of #242: the grant's rung-3 release (`allows_live(3)`, its `max_rung`) was read only when the first audit
        was asked for; with an approval on record, a grant narrowed to rung 2 left the family staked above the bunt."""
        agents, book = self.swinging()
        alloc = self.house.allocator
        with patch.object(self.house, "grant", SimpleNamespace(allows_live=lambda rung: rung <= 2)):
            alloc._released = None
            self.assertFalse(alloc._swing_released())
        with patch.object(allocator.Allocator, "_swing_released", return_value=False):
            self.rebalance()
            self.assertEqual(alloc.family_state(agents[0]), "proven")
            self.assertEqual([book.account(x.id).staked for x in agents], [D("30.00")] * 2)  # free cash back to the bunts
        self.rebalance()  # released again: leaving lapsed its approval, so a new audit is asked before it re-enters
        self.assertEqual(alloc.family_state(agents[0]), "proven")
        self.house.wait(5)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")
        self.assertEqual(len(self.verdicts), 2)

    def started_not_finished(self):
        """The family's first audit is asked for and the House stops before it runs (its job never starts here)."""
        agents, book = self.seated_bunts()
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        with patch.object(self.house, "_background", return_value=True):
            self.rebalance()
        alloc = self.house.allocator
        running = dict(alloc.state["family_audits"]["weather-favorites@kalshi"])
        self.assertEqual(running["status"], "running")
        alloc._save()
        return agents, running

    def restart(self):
        self.house.allocator = allocator.Allocator(self.house, self.house.allocator.path.parent)
        return self.house.allocator

    def test_a_family_audit_that_finished_before_a_restart_is_read_back_not_asked_again(self):
        agents, running = self.started_not_finished()
        key = "weather-favorites@kalshi"
        # The audit wrote its verdict (as the auditor does, naming the family) and the House restarted before the
        # allocator recorded it.
        self.house.ledger.append("audit.verdict", {"approve": True, "summary": "test", "family_swing": key}, agent=running["agent"])
        alloc = self.restart()
        self.assertEqual(alloc.state["family_audits"][key]["status"], "running")
        self.rebalance()
        self.assertEqual((alloc.state["family_audits"][key]["status"], alloc.state["family_audits"][key]["approve"]), ("done", True))
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")
        self.assertEqual(self.verdicts, [])  # the auditor was never asked twice

    def test_a_family_audit_that_never_finished_is_asked_again_after_a_restart(self):
        agents, _ = self.started_not_finished()
        self.restart()
        self.rebalance()
        self.house.wait(5)
        self.assertEqual([v.numbers.get("family_swing") for v in self.verdicts], ["weather-favorites@kalshi"])
        self.rebalance()
        self.assertEqual(self.house.allocator.family_state(agents[0]), "swing")

    def test_a_failed_audit_request_is_not_a_failed_record(self):
        """Review of #242: an error while ASKING for the family's audit (its member's evidence unreadable) made the whole
        family unreadable for money: its proven members were swept to $10 probes at every pass while its state said proven."""
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        with patch.object(allocator.Allocator, "_family_swing_verdict", side_effect=KeyError("pnl")):
            self.rebalance()
            self.assertEqual(alloc.family_state(a), "proven")
            self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("30")] * 2)
        alerts = [e.payload.get("text") for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertTrue(any("audit request" in str(t) for t in alerts))
        self.rebalance(); self.house.wait(5); self.rebalance()  # asked again at the next pass, and it swings
        self.assertEqual(alloc.family_state(a), "swing")

    def test_without_an_auditor_there_is_no_family_swing(self):
        """A gate that fails open is not a gate: no auditor, no first entry."""
        agents, book = self.seated_bunts()
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        with patch.object(self.house, "auditor", None):
            self.rebalance(); self.house.wait(5); self.rebalance()
            self.assertEqual(self.house.allocator.family_state(agents[0]), "proven")
        self.assertEqual([book.account(x.id).staked for x in agents], [D("30")] * 2)

    def test_a_proven_family_whose_last_member_died_is_followed_until_it_falls(self):
        (a,), _ = self.seated_bunts(1)
        alloc = self.house.allocator
        self.house.kill(a, "evidence", "test")
        self.families["weather-favorites"] = real_record(n=12, bound=-0.5, proven=False)
        self.rebalance()
        self.assertEqual(alloc.state["families"]["weather-favorites@kalshi"]["state"], "unproven")

    def test_a_real_record_alone_neither_proves_nor_swings_a_family(self):
        """Finding 11 of the review of #242, the main session's decision: the table has one proof, the POOLED record. A
        family whose REAL record clears the swing's entry and hold while its pooled record is not proven (a practice record
        that contradicts it) is unproven: probes, no audit asked, no swing. #242 called it proven and swung it."""
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=20, bound=0.05, proven=False)
        self.rebalance(); self.house.wait(5); self.rebalance()
        self.assertEqual(alloc.family_state(a), "unproven")
        self.assertEqual(self.verdicts, [])  # never audited for a swing it cannot take
        self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("10")] * 2)  # probes, by free cash

    def test_the_entry_waits_for_a_passing_look(self):
        """Finding 10, the main session's decision: a proven family whose whole real record holds at 80% but whose entry
        look at its checkpoint fails (at 90%, on its first 15) is not audited and does not swing until a look passes."""
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=17, bound=0.05, entry=False)
        self.rebalance(); self.house.wait(5); self.rebalance()
        self.assertEqual((alloc.family_state(a), self.verdicts), ("proven", []))
        self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("30")] * 2)
        self.families["weather-favorites"] = real_record(n=20, bound=0.05)  # the look at 20 passes
        self.rebalance(); self.house.wait(5); self.rebalance()
        self.assertEqual(alloc.family_state(a), "swing")

    def test_an_approval_lapses_when_a_members_program_changes(self):
        """Finding 12, the main session's decision: an approval licenses an entry until a member of the family takes a new
        program after the audit looked (as the agent-level route voids an approval on new code); the entry then asks for a
        new audit."""
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        practice = self.agent("kay9")  # a practice member of the family
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        with patch.object(self.house, "_background", return_value=True):
            self.rebalance()  # the entry's audit is asked for; it runs in a moment (below), as it would on the audit lane
        key = "weather-favorites@kalshi"
        running = dict(alloc.state["family_audits"][key])
        alloc._run_family_audit(key, running["agent"], self.house.allocator._family_swing_verdict(
            self.house.registry.get(running["agent"]), alloc.family("weather-favorites", "kalshi"), key, 2))
        self.assertEqual((alloc.state["family_audits"][key]["status"], alloc.state["family_audits"][key]["approve"]), ("done", True))
        member = self.house.registry.get(practice.id)  # it takes a new program before the family enters
        self.house.ledger.append("agent.strategy", {"code_sha256": member.code_sha256, "params": member.params, "needs": member.needs,
                                                    "reason": "test: a new program", "_code": member.code}, agent=practice.id)
        before = len(self.verdicts)
        self.rebalance()
        self.assertEqual(alloc.family_state(a), "proven")  # no entry on the lapsed approval
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), before + 1)  # a new audit was asked for
        self.rebalance()
        self.assertEqual(alloc.family_state(a), "swing")
        self.assertEqual([book.account(x.id).staked for x in (a, b)], [D("60.00")] * 2)

    def approved_not_entered(self):
        """Two seated bunts of a proven family whose entry's audit has approved it, the family not yet in the swing (the
        grant holds rung 3 back at these passes)."""
        agents, book = self.seated_bunts()
        alloc = self.house.allocator
        key = "weather-favorites@kalshi"
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        with patch.object(self.house, "_background", return_value=True):
            self.rebalance()  # the entry's audit is asked for; it runs in a moment (below), as on the audit lane
        running = dict(alloc.state["family_audits"][key])
        alloc._run_family_audit(key, running["agent"], alloc._family_swing_verdict(
            self.house.registry.get(running["agent"]), alloc.family("weather-favorites", "kalshi"), key, 2))
        self.assertEqual(alloc.state["family_audits"][key]["status"], "done")
        return agents, book, key

    def test_a_member_born_into_the_family_lapses_its_approval(self):
        """The main session's decision (Sept 24, 2026): a member BORN into the family after the audit started -- a research
        child, which is how a real-money line changes its code (it forks; it never adopts in place) -- lapses the approval
        as a member's new program does, and the entry asks for a new audit. A birth into another family changes nothing."""
        (a, b), book, key = self.approved_not_entered()
        alloc = self.house.allocator
        with patch.object(allocator.Allocator, "_swing_released", return_value=False):
            self.agent("hawk", family="kalshi-favorites")  # another family's newborn
            self.rebalance()
            self.assertEqual(alloc.state["family_audits"][key]["status"], "done")
            self.agent("kay-child")  # born into this family
            self.rebalance()
            self.assertEqual(alloc.state["family_audits"][key]["status"], "lapsed")
            self.assertIn("kay-child was born into the family after the audit", alloc.state["family_audits"][key]["why"])
        before = len(self.verdicts)
        self.rebalance()  # released: no entry on the lapsed approval, a new audit is asked for
        self.assertEqual(alloc.family_state(a), "proven")
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), before + 1)
        self.rebalance()
        self.assertEqual(alloc.family_state(a), "swing")

    def test_a_birth_leaves_a_running_swing_alone_and_audits_its_next_entry(self):
        agents, book = self.swinging()
        alloc = self.house.allocator
        key = "weather-favorites@kalshi"
        self.agent("kay-child")
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")  # untouched: it stays while its 80% bound holds
        self.assertEqual([book.account(x.id).staked for x in agents], [D("60.00")] * 2)
        self.assertEqual(alloc.state["family_audits"][key]["status"], "lapsed")  # its next entry is audited again

    def test_the_family_swings_audit_is_not_its_members_own(self):
        """Review of #242: the family's verdict is written against one member (the one with the most real trades), but it
        judged the FAMILY's stake. Read as that member's own, its approval let the member take the agent-level swing (rung
        3, up to 60% of the venue) without the audit that route requires, and a veto would hold its own promotions."""
        (a, b), book = self.seated_bunts()
        alloc = self.house.allocator
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        self.rebalance(); self.house.wait(5); self.rebalance()
        self.assertEqual(alloc.family_state(a), "swing")
        rep = self.house.registry.get(alloc.state["family_audits"]["weather-favorites@kalshi"]["agent"])
        self.assertEqual(allocator.audit_standing(self.house, rep), "none")
        self.assertIsNone(self.house._audit_wait(rep))  # the family's verdict starts no cooldown of its own
        for x in (a, b):
            self.table[x.id] = dict(e=1.30, w_paper=1.21, w_real=1.1, real_trades=8, real_stay_closed=8, paper_trades=6, paper_settled=6)
        before = len(self.verdicts)
        self.rebalance()
        self.house.wait(5)
        self.assertIn(rep.id, [v.agent for v in self.verdicts[before:]])  # its own agent-level swing was audited
        self.assertEqual(self.house.evaluator.rung(rep.id), 3)  # and the approval of that audit, not its family's, seated it
        self.auditor.approve = False  # a family veto is the family's too: it holds none of the member's own promotions
        self.house.ledger.append("audit.verdict", {"approve": False, "summary": "test", "family_swing": "weather-favorites@kalshi"},
                                 agent=rep.id)
        self.assertEqual(allocator.audit_standing(self.house, rep), "approved")

    def test_the_envelope_bounds_every_increase(self):
        """A $200 envelope holding the family's two $30 bunts and nine $10 probes of another family has $50 of
        headroom: the swing's targets are $60 a member (the venue share, $120, shared by two), and the raises stop
        at the headroom: $30 to one, $20 to the other."""
        tight = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "200"})
        tight.start()
        self.addCleanup(tight.stop)
        agents, book = self.seated_bunts()
        others = [self.agent(f"hawk{i}", family="kalshi-favorites") for i in range(9)]
        self.table.update({a.id: dict(self.READY) for a in others})
        self.rebalance()
        alloc = self.house.allocator
        self.assertEqual([book.account(a.id).staked for a in others], [D("10")] * 9)
        self.assertEqual(alloc.headroom("kalshi"), D("50"))
        self.families["weather-favorites"] = real_record(n=15, bound=1.0)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")
        self.assertEqual([str(alloc.target_stake(a, "bunt", alloc._evidence[a.id])) for a in agents], ["60.00", "60.00"])
        self.assertEqual(sorted(book.account(x.id).staked for x in agents), [D("50.00"), D("60.00")])
        self.assertEqual(alloc.headroom("kalshi"), D("0"))
        self.assertLessEqual(alloc.committed("kalshi"), alloc.capital("kalshi"))

    def test_a_proven_familys_newcomer_never_displaces_a_swinging_familys_member(self):
        """Capital follows proof one step up (as a probe never displaces a proven family's bunt, Deploy A): with
        the envelope full, a proven family's newcomer with the better E waits; the family swing is not undone."""
        tight = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "60"})
        tight.start()
        self.addCleanup(tight.stop)
        (a,), book = self.seated_bunts(1)
        self.families["weather-favorites"] = real_record(n=15, bound=1.0)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual(self.house.allocator.family_state(a), "swing")
        self.assertEqual(book.account(a.id).staked, D("36.00"))  # 60% of the $60 envelope: the venue share binds
        self.families["sports-favorites"] = real_record(n=5, bound=-0.5, family="sports-favorites")  # proven
        newcomer = self.agent("hawk", family="sports-favorites")
        self.table[newcomer.id] = dict(self.READY, e=1.50)
        self.rebalance()
        self.assertEqual((self.house.evaluator.rung(a.id), self.house.evaluator.rung(newcomer.id)), (2, 1))
        status = self.house._state["promotion_status"][newcomer.id]
        self.assertEqual(status["stage"], "envelope")

    def test_the_capacity_is_read_at_the_familys_own_stake(self):
        """The board's capacity is at the stake a member is lent: an unproven family's probe ($10: a $2 position)."""
        self.records.stop()  # the real family record, from the ledger
        self.agent()
        self.house.allocator.rebalance()
        family = self.house.allocator.board()["families"]["kalshi"]["weather-favorites"]
        self.assertEqual((family["state"], family["stake_usd"], family["capacity"]["size_usd"]), ("unproven", "10", 2.0))
        self.records.start()

    def test_a_family_whose_record_cannot_be_read_keeps_its_swing_entry(self):
        """A read that fails once is an unproven family's for money -- probes' limits, no swing -- but the ledger's
        state is not moved: the ramp does not start again for it."""
        agents, _ = self.swinging()
        alloc = self.house.allocator
        entered = alloc.state["families"]["weather-favorites@kalshi"]["entered_seq"]
        with patch.object(allocator, "family_record", side_effect=KeyError("pnl")):
            self.rebalance()
            self.assertEqual(alloc.family_state(agents[0]), "unproven")
        self.assertEqual(alloc.state["families"]["weather-favorites@kalshi"]["entered_seq"], entered)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")

    def test_family_record_rows_are_written_at_most_every_five_minutes_and_only_when_changed(self):
        self.seated_bunts(1)
        rows = lambda: [e.payload for e in self.house.ledger.iter(kinds="family.record")]  # noqa: E731
        first = [r for r in rows() if r["family"] == "weather-favorites"]
        # The member the pass seated counts among its family's members for the rest of that pass (review of #242).
        self.assertEqual((first[-1]["state"], first[-1]["venue"], first[-1]["stake_usd"], first[-1]["members_real"]),
                         ("proven", "kalshi", "30", 1))
        written = len(rows())
        self.families["weather-favorites"] = real_record(n=6, bound=-0.5)
        self.rebalance()
        self.assertEqual(len(rows()), written)  # inside five minutes: nothing, though its record changed
        self.clock.advance(301)
        self.rebalance()
        new = rows()[written:]
        self.assertEqual([(r["family"], r["real"]["n"]) for r in new], [("weather-favorites", 6)])  # that change, once
        written = len(rows())
        self.clock.advance(301)
        self.rebalance()
        self.assertEqual(len(rows()), written)  # nothing changed: nothing

    def test_a_family_record_row_is_not_written_again_because_the_clock_moved(self):
        """Review of #242: the capacity estimate's rates move with the clock alone (a window that slides), so on the T0
        snapshot 36 of the 43 families followed changed digest every five minutes with no new trade: about 10,000 rows a
        day burying the state changes the rows exist to record."""
        self.records.stop()  # the real family record, from the ledger
        try:
            a = self.agent()
            for i in range(6):  # a member's bids an hour apart, measured by the capacity estimate
                self.house.ledger.append("book.order", {
                    "book": "kalshi-shadow", "order_id": f"o{i}", "side": "buy", "status": "new", "limit_price": "0.90", "quantity": "10",
                    "instrument": {"market_id": f"KXHIGHNY-26SEP{i + 1:02d}-B72.5", "multiplier": "1"},
                    "shares": [{"agent": a.id, "quantity": "10"}]})
                self.clock.advance(3600)
            rows = lambda: [e.payload for e in self.house.ledger.iter(kinds="family.record") if e.payload["family"] == "weather-favorites"]  # noqa: E731
            self.house.allocator.rebalance()
            self.assertEqual(len(rows()), 1)
            self.assertIsNotNone(rows()[0]["capacity"]["markets_per_day"])
            self.clock.advance(301)
            self.house.allocator.rebalance()
            self.assertEqual(len(rows()), 1)  # nothing but the clock moved: no row
        finally:
            self.records.start()

    def test_the_states_survive_a_restart_through_the_ledger(self):
        agents, _ = self.swinging()
        self.clock.advance(301)
        self.rebalance()  # the swing's row
        restored = families.restore_states(self.house.ledger)
        self.assertEqual(restored["weather-favorites@kalshi"]["state"], "swing")
        entered = self.house.allocator.state["families"]["weather-favorites@kalshi"]["entered_seq"]
        self.assertEqual(restored["weather-favorites@kalshi"]["entered_seq"], entered)


class AgentSwingGate(KalshiHouse):
    """`swing_requires_proven_family` (the coordinator's key, Deploy B's digest): the agent-level swing is a proven
    or swinging family's agent's; false restores the swing of Sept 23 for every family."""

    SWING_READY = dict(e=1.30, w_paper=1.21, w_real=1.1, real_trades=8, real_stay_closed=8, paper_trades=6, paper_settled=6)

    def test_the_key_gates_the_agent_level_swing_where_it_is_read(self):
        self.assertIs(CONSTITUTION["allocator"]["swing_requires_proven_family"], True)
        a = self.agent()  # an unproven family (the canned default)
        with self.evidence_of({a.id: dict(ProbesReady)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        alloc = self.house.allocator
        with patch.object(allocator, "audit_standing", return_value="approved"), self.evidence_of({a.id: self.SWING_READY}):
            alloc.rebalance()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertFalse(alloc.swing_allowed(a))
        # The key's rollback alone: M1's settlement dates (Sept 25, 2026), which every swing look asks, are
        # league/tests/test_capital_follows_proof.py's (this canned family's real record spans none).
        with patch.dict(CONSTITUTION["allocator"], {"swing_requires_proven_family": False}), \
                patch.dict(CONSTITUTION["allocator"]["family_swing"], {"min_distinct_dates": 0}):
            self.assertTrue(alloc.swing_allowed(a))
            with patch.object(allocator, "audit_standing", return_value="approved"), self.evidence_of({a.id: self.SWING_READY}):
                alloc.rebalance()
            self.assertEqual(self.house.evaluator.rung(a.id), 3)  # Sept 23's agent-level swing, for an unproven family

    def test_a_swing_audit_of_an_unproven_family_commits_when_the_key_is_off(self):
        """`House._commit_promotion` reads the same key (`Allocator.swing_allowed`)."""
        from league.evaluator import Verdict

        a = self.agent()
        with self.evidence_of({a.id: dict(ProbesReady)}):
            self.tick()
        verdict = Verdict(a.id, 2, "eligible", "swing", {"via": "allocator", "book": "kalshi"})
        generation = self.house._generation(a.id)
        self.house._commit_promotion(a.id, verdict, 2, generation)
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        with patch.dict(CONSTITUTION["allocator"], {"swing_requires_proven_family": False}):
            self.house._commit_promotion(a.id, verdict, 2, self.house._generation(a.id))
        self.assertEqual(self.house.evaluator.rung(a.id), 3)


ProbesReady = dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)


class Readers(KalshiHouse):
    """One source: the House's births (`family_forward`), the lab's lineage weights (`family_score`) and the board."""

    def test_family_forward_is_the_houses_on_the_same_rows(self):
        a, b = self.agent("kay"), self.agent("hawk", family="kalshi-favorites")
        for agent, active, growth in ((a, True, 0.01), (a, True, -0.03), (a, False, 0.5), (b, True, 0.02)):
            self.house.ledger.append("eval.block", {"book": "kalshi-shadow", "active": active, "log_growth": growth, "key": "k"}, agent=agent.id)
        self.house.allocator.rebalance()
        self.assertEqual(self.house.allocator.family_forward(), self.house.family_forward())
        blocks, growth = self.house.allocator.family_forward()["weather-favorites"]
        self.assertEqual(blocks, 2)
        self.assertTrue(families.losing(blocks, growth, 2))
        self.assertFalse(families.losing(blocks, growth, 3))

    def test_the_lineage_score_follows_the_family(self):
        a = self.agent()
        alloc = self.house.allocator
        self.assertEqual(alloc.family_score("weather-favorites", "kalshi"), 0)
        self.families["weather-favorites"] = real_record(n=5, bound=-0.5)
        alloc.rebalance()
        self.assertEqual(alloc.lineage_score(["nobody", a.id]), 1)
        losing = real_record(n=5, proven=False)
        losing.update(n=12, mean_log=-0.02)
        self.families["weather-favorites"] = losing
        alloc.rebalance()
        self.assertEqual(alloc.family_score("weather-favorites", "kalshi"), -1)


class Protected(unittest.TestCase):
    def test_the_ledger_is_a_money_judge_and_its_rows_are_private(self):
        from league.ci import FORBIDDEN
        from league.ledger import KINDS

        self.assertIn("league/families.py", FORBIDDEN)
        self.assertIs(KINDS["family.record"], False)

    def test_every_new_key_is_a_money_rule_in_the_digest(self):
        """Deploy B's digest change (2 of 2): the family swing, its unit, the agent-level swing's gate and the
        corrected child's supersession all move the money digest the live grant pins."""
        import copy

        for path in (("family_swing",), ("corrected_child_supersedes",), ("swing_requires_proven_family",),
                     ("family_proven", "unit"), ("family_proven", "reference_share"),
                     ("family_swing", "entry_every"), ("family_swing", "entry_confidence")):
            changed = copy.deepcopy(CONSTITUTION)
            node = changed["allocator"]
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            self.assertNotEqual(money_digest(changed), money_digest(), path)
            self.assertNotEqual(digest(changed), digest(), path)
        self.assertIs(CONSTITUTION["allocator"]["corrected_child_supersedes"], True)

    def test_the_family_swing_row_is_inside_the_tables_bounds(self):
        """The table's row: 15-40 independent real settlements, a start at 2-4x the bunt, doubling every 10. The forward-first
        run's M1 (Sept 25, 2026): 10-15, with 5 distinct settlement dates at every look."""
        row = CONSTITUTION["allocator"]["family_swing"]
        self.assertTrue(10 <= row["min_real_settlements"] <= 15)
        self.assertEqual(row["min_distinct_dates"], 5)
        self.assertTrue(2 <= row["start_multiple"] <= 4)
        self.assertEqual(row["doubling_every"], 10)
        self.assertEqual(D(row["capacity_fill_ratio"]), D("0.5"))
        # The entry's looks (the main session's decision on the review of #242): at 10 (M1) and every 5 more, at 90%.
        self.assertEqual((row["entry_every"], D(row["entry_confidence"])), (5, D("0.9")))
        self.assertEqual(CONSTITUTION["allocator"]["max_share_of_venue"], 0.6)  # unchanged
        self.assertEqual(CONSTITUTION["rungs"]["3"]["kelly_fraction"], 1.0)  # unchanged


class RulesText(unittest.TestCase):
    """What every agent reads (`league/rules.py`): its family's record is its proof, what a family is, what sizing on
    practice buys under the at-risk unit, and the numbers that make a family proven and swinging."""

    def text(self, constitution=None):
        import json
        from league.rules import rules_text

        with open("league/game.json") as f:
            return " ".join(rules_text(json.load(f), constitution).split())

    def test_the_agents_are_told_the_mechanism_ledger(self):
        text = self.text()
        self.assertIn("80% lower bound on what their events made per dollar put at risk is above zero", text)
        # C8 (Sept 25, 2026; the Deploy B review): under `allocator.family_key` "mechanism" the text says the House's rule --
        # a params-only child (a lab nudge included) stays, any other code, venue, series or symbols founds its own.
        self.assertIn("A FAMILY IS ONE MECHANISM: a program's code beyond its PARAMS, with the venue, series and symbols it "
                      "trades. A child that changes only your PARAMS (an Alpha Lab nudge of your parameters included) stays in "
                      "your family", text)
        self.assertIn("founds (or joins) the family of ITS mechanism and proves itself there from zero", text)
        self.assertNotIn("whatever they change", text)
        # The label's rule (`family_key` "label", or absent): every lab graduate is born into a `-lab-<lineage>` family, a
        # nudge of a member's parameters included (`Lab._names`), and research children keep the label.
        labels = {**CONSTITUTION, "allocator": {**CONSTITUTION["allocator"], "family_key": "label"}}
        old = self.text(labels)
        self.assertIn("A FAMILY IS ONE MECHANISM. Every lab graduate (a lab nudge of your parameters included) and every "
                      "foundry card starts a family of its own", old)
        self.assertIn("your research children stay in your family, whatever they change", old)
        self.assertIn("SIZE ON PRACTICE IS YOURS, AND PRACTICE MONEY IS FREE.", text)
        self.assertIn("weighs what it put at risk against your usual size on that book: scaling every bet up or down proves "
                      "nothing faster, a big losing bet counts for its dollars", text)
        self.assertIn("What proves (or disproves) a family faster is MORE independent events", text)
        self.assertIn("THE FAMILY SWING. When your family is PROVEN and its REAL-money record reaches 10 independent settlements, "
                      "its entry is judged there and at every 5 more (10, 15, 20, ...): on those first settlements, with their "
                      "lower bound at 90% above zero (the loss-rate test too, for favourites), spanning at least 5 distinct "
                      "settlement dates", text)
        self.assertIn("Staying in the swing, and every doubling, needs the whole real record on as many dates.", text)
        self.assertIn("2x the bunt ($60 at Kalshi), doubled after every 10 further WINNING real settlements while the whole "
                      "real record's lower bound at 80% stays above zero", text)
        self.assertIn("60% of the venue for the whole family (shared by its members on real money)", text)
        self.assertIn("fall under 50% of its fills at the smaller one", text)
        self.assertIn("its next entry is audited again, as it is when a member of the family takes a new program or a new "
                      "member is born into it", text)
        start, end = text.index("- YOUR FAMILY'S RECORD"), text.index("- REAL MONEY AT KALSHI")
        self.assertNotIn("paper", text[start:end].lower())  # the copy rule: practice, never paper

    def test_the_text_follows_the_keys(self):
        import copy

        c = copy.deepcopy(CONSTITUTION)
        del c["allocator"]["family_swing"]
        c["allocator"]["swing_requires_proven_family"] = False
        c["allocator"]["family_proven"]["unit"] = "account"
        text = self.text(c)
        self.assertNotIn("THE FAMILY SWING", text)
        self.assertNotIn("for a PROVEN family's member only", text)
        self.assertIn("lower bound on their mean log growth an event", text)
        self.assertIn("a conviction-sized practice record proves (or disproves) your family faster than a token one", text)
        self.assertIn("for a PROVEN family's member only", self.text())


class FamilyPacket(unittest.TestCase):
    """The auditor gets the family packet with `allocation_context` (the Sept 23 lesson), once, and its verdict row
    names the family it judged."""

    def test_the_packet_and_the_row(self):
        import tempfile
        from pathlib import Path

        from league.economy import Economy
        from league.evaluator import Evaluator, Verdict
        from league.ledger import Ledger
        from league.tests.test_auditor import AuditorCase, says

        case = AuditorCase("test_an_allocator_audit_is_judged_against_the_allocators_envelope")
        case.dir = tempfile.TemporaryDirectory()
        case.ledger = Ledger(Path(case.dir.name) / "ledger.db")
        case.evaluator, case.economy = Evaluator(case.ledger), Economy(case.ledger)
        try:
            agent = case.make_agent("fav-1")
            context = {"allocator": "capital is the ladder", "family_swing": True, "band_to": "swing", "stake_usd": "60.00",
                       "purpose": "the FAMILY SWING: every member of the family on real money is staked at the ramp",
                       "tuition": {"max_loss_usd": "517.75", "max_agents": 101}}
            packet_in = {"family": "favourites", "real_record": {"n": 15, "honest_bound": 0.02}}
            verdict = Verdict(agent.id, 2, "eligible", "family swing", {"via": "family_swing", "book": "kalshi", "family_swing": "favourites@kalshi",
                                                                        "family_packet": packet_in, "allocation_context": context})
            auditor = case.auditor(says({"approve": True, "confidence": 0.8, "summary": "ok", "findings": []}))
            packet = auditor.packet(agent, verdict)
            self.assertEqual(packet["family_packet"], packet_in)
            self.assertNotIn("family_packet", packet["test_passed"])  # sent once
            self.assertIn("FAMILY SWING", packet["promotion_context"]["purpose"])
            self.assertEqual(packet["promotion_context"]["allocation_context"]["stake_usd"], "60.00")
            row = auditor.audit(agent, verdict, charge=False)
            self.assertTrue(row["approve"])
            self.assertEqual(row["family_swing"], "favourites@kalshi")
            from league.auditor import SYSTEM

            self.assertIn("FAMILY SWING", SYSTEM)
            # A call that fails names the family too (review of #242): the House's own audit readers skip it, and the
            # allocator reads it back after a restart instead of asking again before the error cooldown.
            import urllib.error

            failed = case.auditor(urllib.error.URLError("no route")).audit(agent, verdict, charge=False)
            self.assertTrue(failed["error"])
            self.assertEqual(case.ledger.last("audit.verdict", agent=agent.id).payload["family_swing"], "favourites@kalshi")
        finally:
            case.ledger.close()
            case.dir.cleanup()


if __name__ == "__main__":
    unittest.main()
