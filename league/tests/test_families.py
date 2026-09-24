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
        obs = [((v(1 / 9) + v(2 / 8)) / 2, 0.5), (v(5 / 5), 0.5), (v(-1), 1.0), (v(1 / 4), 0.5)]
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
        expected = (v(game(MERIWETHER_SETTLES[:3], MERIWETHER_BUYS[:3])) + v(game(MERIWETHER_SETTLES[3:], MERIWETHER_BUYS[3:]))) / 2
        self.assertAlmostEqual(rec["mean_log"], expected, places=12)
        self.assertEqual((rec["taker"]["n"], rec["maker"]["n"]), (2, 0))

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


def real_record(n=15, bound=0.02, variance=0.5, closes=None, unit="at_risk", proven=True, family="weather-favorites"):
    """A family record whose REAL record is set by the test: `closes` are (first close seq, value)."""
    rec = families.empty_record(family, "kalshi")
    rec.update(unit=unit, n=max(n, 10), proven=proven, state="proven" if proven else "unproven", bound=0.01 if proven else -0.01,
               real_n=n, members=2, members_living=2, members_counted=2)
    rec["real"] = {**rec["real"], "n": n, "bound": bound, "honest_bound": bound, "variance": variance,
                   "first_closes": closes if closes is not None else [(i + 1, 0.05) for i in range(n)]}
    return rec


class SwingRules(unittest.TestCase):
    """C2's arithmetic: the entry at 15 real settlements with a positive honest bound, the ramp's doubling at every
    10 further positive ones, the Kelly and venue caps shared by the members, the capacity hold, the bunt floor."""

    def setUp(self):
        self.rule = families.swing_rule()

    def target(self, record, members=1, entered=15, rates=None, capital="517.75"):
        return families.swing_target(record, rule=self.rule, venue="kalshi", bunt_usd="30", venue_capital=capital,
                                     members_real=members, entered_seq=entered, rates=rates)

    def test_the_constitutions_rule(self):
        self.assertEqual({k: self.rule[k] for k in ("min_real_settlements", "start_multiple", "doubling_every")},
                         {"min_real_settlements": 15, "start_multiple": 2.0, "doubling_every": 10})
        self.assertEqual((self.rule["kelly_fraction"], self.rule["max_share_of_venue"]), (1.0, 0.6))  # rung 3's, the allocator's
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["family_swing"]
            self.assertIsNone(families.swing_rule())  # no key, no family swing
            self.assertFalse(families.swing_ready(real_record(), families.swing_rule()))

    def test_the_entry_needs_15_real_settlements_and_a_positive_honest_bound(self):
        self.assertFalse(families.swing_ready(real_record(n=14), self.rule))
        self.assertTrue(families.swing_ready(real_record(n=15), self.rule))
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
        the venue at risk an event, a stake of 4% / 20% (Kalshi's position share) of $517.75 = $103.55."""
        closes = [(i + 1, 0.05) for i in range(15)] + [(100 + i, 0.05) for i in range(10)]  # the ramp at $120
        row = self.target(real_record(closes=closes, bound=0.02, variance=0.5))
        self.assertEqual((row["stake_usd"], row["limit"], row["kelly_usd"]), (D("103.55"), "kelly", D("103.55")))
        self.assertAlmostEqual(row["kelly_fraction_at_risk"], 0.04, places=12)
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
        s = families.next_state
        self.assertEqual(s("unproven", proven=False, ready=False, approved=False), "unproven")
        self.assertEqual(s("unproven", proven=True, ready=False, approved=False), "proven")
        self.assertEqual(s("proven", proven=True, ready=True, approved=False), "proven")  # the first entry waits for its audit
        self.assertEqual(s("proven", proven=True, ready=True, approved=True), "swing")
        self.assertEqual(s("swing", proven=True, ready=True, approved=False), "swing")
        self.assertEqual(s("swing", proven=True, ready=False, approved=True), "proven")  # the bound fell: bunts
        self.assertEqual(s("swing", proven=False, ready=False, approved=True), "unproven")  # and the proof too: probes
        self.assertEqual(s("unproven", proven=False, ready=True, approved=False), "proven")  # the real record alone proves


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
        self.families["weather-favorites"] = real_record(n=25, bound=0.05, closes=closes)
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
        # Its approval stays on record: the bound back above zero, the family re-enters without a second audit.
        self.families["weather-favorites"] = real_record(n=17, bound=0.05)
        self.rebalance()
        self.assertEqual(alloc.family_state(agents[0]), "swing")
        self.assertEqual(len(self.verdicts), 1)

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
        self.assertEqual((first[-1]["state"], first[-1]["venue"], first[-1]["stake_usd"], first[-1]["members_real"]),
                         ("proven", "kalshi", "30", 0))  # read at the pass's start, before it seated the member
        written = len(rows())
        self.rebalance()
        self.assertEqual(len(rows()), written)  # inside five minutes: nothing, though its member is now on real money
        self.clock.advance(301)
        self.rebalance()
        self.assertEqual([r["members_real"] for r in rows()[written:]], [1])  # that change, once
        written = len(rows())
        self.clock.advance(301)
        self.rebalance()
        self.assertEqual(len(rows()), written)  # nothing changed: nothing
        self.families["weather-favorites"] = real_record(n=6, bound=-0.5)
        self.clock.advance(301)
        self.rebalance()
        new = rows()[written:]
        self.assertEqual([r["family"] for r in new], ["weather-favorites"])
        self.assertEqual(new[0]["real"]["n"], 6)

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
        with patch.dict(CONSTITUTION["allocator"], {"swing_requires_proven_family": False}):
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
                     ("family_proven", "unit"), ("family_proven", "reference_share")):
            changed = copy.deepcopy(CONSTITUTION)
            node = changed["allocator"]
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            self.assertNotEqual(money_digest(changed), money_digest(), path)
            self.assertNotEqual(digest(changed), digest(), path)
        self.assertIs(CONSTITUTION["allocator"]["corrected_child_supersedes"], True)

    def test_the_family_swing_row_is_inside_the_tables_bounds(self):
        """The table's row: 15-40 independent real settlements, a start at 2-4x the bunt, doubling every 10."""
        row = CONSTITUTION["allocator"]["family_swing"]
        self.assertTrue(15 <= row["min_real_settlements"] <= 40)
        self.assertTrue(2 <= row["start_multiple"] <= 4)
        self.assertEqual(row["doubling_every"], 10)
        self.assertEqual(D(row["capacity_fill_ratio"]), D("0.5"))
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
        self.assertIn("A FAMILY IS ONE MECHANISM. A new mechanism from the lab or the foundry starts a family of its own", text)
        self.assertIn("your research children and parameter mutations stay in your family", text)
        self.assertIn("SIZE ON PRACTICE IS YOURS, AND PRACTICE MONEY IS FREE.", text)
        self.assertIn("so size cannot inflate your family's proof", text)
        self.assertIn("What proves (or disproves) a family faster is MORE independent events", text)
        self.assertIn("THE FAMILY SWING. When your family's REAL-money record alone has 15 or more independent settlements", text)
        self.assertIn("2x the bunt ($60 at Kalshi), doubled after every 10 further WINNING real settlements", text)
        self.assertIn("60% of the venue for the whole family (shared by its members on real money)", text)
        self.assertIn("fall under 50% of its fills at the smaller one", text)
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
        finally:
            case.ledger.close()
            case.dir.cleanup()


if __name__ == "__main__":
    unittest.main()
