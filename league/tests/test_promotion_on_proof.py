"""Promotion on proof (the close-the-gaps run, Sept 24, 2026; docs/goals/LTCM_CLOSE_THE_GAPS.md D4, P1-P3).

The evidence on record: the allocator's nine promotions to real money (08:28Z Sept 23 to 00:17Z Sept
24) all ran unproven mechanisms and settled -$18.62 on 16 settlements, 0 positive; four were demoted
after one loss; and meriwether-h7d7702 was promoted twice on strikes stacked on the same games. So:
settlements count once per EVENT (D4), a first real stake is a PROBE unless the agent's family has a
proven pooled record (P1), one early loss on a probe is not a demotion (P2), and the book's entry
rules read the constitution's keys (P3's keys; `league/book.py` implements them).
"""

import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator, evaluator
from league.allocator import Evidence, bunt_ready
from league.constitution import CONSTITUTION
from league.evaluator import Evaluator, event_key
from league.ledger import Ledger
from league.tests.fakes import Clock

D = Decimal
P = allocator._params


def ev(**kw):
    base = dict(agent="a", venue="kalshi", rung=1, w_paper=1.0, w_real=1.0, e=1.0, paper_trades=0, paper_settled=0,
                real_trades=0, real_pnl=0.0, real_drawdown=0.0, haircut_log=0.0, real_seen=False)
    base.update(kw)
    return Evidence(**base)


class LedgerCase(unittest.TestCase):
    """A bare ledger with the rows a Book writes, by ticker."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.house = SimpleNamespace(ledger=self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    @staticmethod
    def inst(ticker, right="no", venue="kalshi-shadow"):
        if venue.startswith("alpaca"):
            return {"asset_class": "crypto", "symbol": ticker, "venue": venue, "market_id": None, "multiplier": "1"}
        return {"asset_class": "event", "symbol": ticker, "venue": venue, "market_id": ticker, "right": right, "multiplier": "1"}

    def stake(self, usd, agent="a", book="kalshi-shadow"):
        self.ledger.append("book.stake", {"book": book, "usd": str(usd), "note": "t", "real_money": book in ("kalshi", "alpaca")},
                           agent=agent)

    def buy(self, ticker, quantity, price, agent="a", book="kalshi-shadow", liquidity="taker"):
        cost = D(str(quantity)) * D(str(price))
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "realized": None, "flat": None,
                                         "instrument": self.inst(ticker, venue=book), "quantity": str(quantity),
                                         "price": str(price), "cash_delta": str(-cost), "liquidity": liquidity}, agent=agent)

    def sell(self, ticker, realized, agent="a", book="kalshi-shadow", flat=True, liquidity="taker"):
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "sell", "realized": str(realized),
                                         "flat": flat, "instrument": self.inst(ticker, venue=book), "quantity": "1",
                                         "price": "1", "cash_delta": "1", "liquidity": liquidity}, agent=agent)

    def settle(self, ticker, pnl, agent="a", book="kalshi-shadow"):
        self.ledger.append("book.settle", {"book": book, "instrument": self.inst(ticker, venue=book), "pnl": str(pnl),
                                           "cost": "1", "payout": "1", "quantity": "1", "result": "no"}, agent=agent)


#: meriwether-h7d7702's practice record at its promotion of 00:39:48Z Sept 24, 2026 (the T0 snapshot,
#: seq 308404-379415): NO at strikes 7, 8 and 9 of two MLB totals, every one a taker, six settlements.
MERIWETHER_BUYS = [("KXMLBTOTAL-26SEP231310WSHDET-7", 25, "0.37"), ("KXMLBTOTAL-26SEP231310WSHDET-8", 19, "0.50"),
                   ("KXMLBTOTAL-26SEP231310WSHDET-9", 16, "0.58"), ("KXMLBTOTAL-26SEP231545MINSF-7", 25, "0.37"),
                   ("KXMLBTOTAL-26SEP231545MINSF-8", 20, "0.48"), ("KXMLBTOTAL-26SEP231545MINSF-9", 17, "0.57")]
MERIWETHER_SETTLES = [("KXMLBTOTAL-26SEP231310WSHDET-7", "15.546"), ("KXMLBTOTAL-26SEP231310WSHDET-8", "9.3337"),
                      ("KXMLBTOTAL-26SEP231310WSHDET-9", "6.5835"), ("KXMLBTOTAL-26SEP231545MINSF-7", "15.546"),
                      ("KXMLBTOTAL-26SEP231545MINSF-8", "10.2252"), ("KXMLBTOTAL-26SEP231545MINSF-9", "7.1641")]


class IndependentSettlements(LedgerCase):
    """D4: on the event books a closed trade and a settlement count once per EVENT."""

    def test_the_event_of_a_kalshi_market(self):
        self.assertEqual(event_key({"market_id": "KXMLBTOTAL-26SEP231840MILPHI-6"}), "KXMLBTOTAL-26SEP231840MILPHI")
        self.assertEqual(event_key({"market_id": "KXBTCD-26SEP2401-T62999.99"}), "KXBTCD-26SEP2401")
        self.assertEqual(event_key({"market_id": "KXHIGHNY-26SEP24-B72.5"}), "KXHIGHNY-26SEP24")
        self.assertEqual(event_key({"market_id": "KXETH15M-26SEP232145-45"}), "KXETH15M-26SEP232145")
        # A player prop names the game, then the player: one game is one event (Kalshi's event
        # ticker, and the House's own tapes: `league/tapes.py`), never one event per player.
        self.assertEqual(event_key({"market_id": "KXMLBHIT-26SEP222140LAAATH-LAAMTROUT27-4"}), "KXMLBHIT-26SEP222140LAAATH")
        self.assertEqual(event_key({"market_id": "kxhighny-26sep24-b72.5"}), "KXHIGHNY-26SEP24")
        self.assertEqual(event_key({"symbol": "KXRAIN-26SEP19-MIA"}), "KXRAIN-26SEP19")
        # An explicit event on the instrument wins; a bare name is its own event; nothing is nothing.
        self.assertEqual(event_key({"market_id": "KXA-1-2", "event_ticker": "KXA-EVENT"}), "KXA-EVENT")
        self.assertEqual(event_key({"market_id": "M7"}), "M7")
        self.assertIsNone(event_key({}))
        self.assertIsNone(event_key(None))

    def test_three_strikes_of_one_game_are_one_settlement_and_two_games_are_two(self):
        for strike in ("6", "7", "8"):
            self.settle(f"KXMLBTOTAL-26SEP231840MILPHI-{strike}", "1")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        for strike in ("7", "8", "9", "10"):
            self.settle(f"KXMLBTOTAL-26SEP231835TORBALG2-{strike}", "1")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (2, 2))
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):  # the old count, by the key
            self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (7, 7))

    def test_a_flat_sale_counts_toward_its_event(self):
        self.sell("KXBTCD-26SEP2401-T62999.99", "0.40")
        self.settle("KXBTCD-26SEP2401-T63249.99", "0.10")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        self.sell("KXBTCD-26SEP2402-T62999.99", "0.40", flat=False)  # a partial sale closes nothing
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (1, 1))
        self.sell("KXBTCD-26SEP2402-T62999.99", "0.40")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (2, 1))

    def test_the_real_book_counts_the_same_way_and_a_stay_counts_from_its_start(self):
        self.settle("KXHIGHNY-26SEP24-B72.5", "1", book="kalshi")
        self.settle("KXHIGHNY-26SEP24-B74.5", "1", book="kalshi")
        start = self.ledger.head()[0]
        self.settle("KXHIGHMIA-26SEP24-B90.5", "1", book="kalshi")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi"), (2, 2))
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi", since_seq=start), (1, 1))

    def test_alpaca_counts_every_closed_trade(self):
        for _ in range(3):
            self.sell("BTC/USD", "0.40", book="alpaca-paper")
        self.assertEqual(allocator.closed_trades(self.house, "a", "alpaca-paper"), (3, 0))

    def test_a_closed_row_without_a_market_counts_alone(self):
        for _ in range(3):
            self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1"}, agent="a")
        self.assertEqual(allocator.closed_trades(self.house, "a", "kalshi-shadow"), (3, 3))

    def test_meriwether_h7d7702s_stacked_record_does_not_reach_the_bunt_line(self):
        """Promoted at 00:39:48Z Sept 24, 2026 "E 1.1303 ... on 6 closed trades": two games."""
        self.stake(200)
        for ticker, quantity, price in MERIWETHER_BUYS:
            self.buy(ticker, quantity, price)
        for ticker, pnl in MERIWETHER_SETTLES:
            self.settle(ticker, pnl)
        trades, settled = allocator.closed_trades(self.house, "a", "kalshi-shadow")
        self.assertEqual((trades, settled), (2, 2))
        p = P()
        self.assertFalse(bunt_ready(ev(e=1.1303, paper_trades=trades, paper_settled=settled), p))
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):
            trades, settled = allocator.closed_trades(self.house, "a", "kalshi-shadow")
            self.assertEqual((trades, settled), (6, 6))
            self.assertTrue(bunt_ready(ev(e=1.1303, paper_trades=trades, paper_settled=settled), P()))
        # Its first promotion, 20:07:05Z Sept 23, "E 1.0973 ... on 3 closed trades", was ONE game.
        self.assertEqual(len({event_key({"market_id": t}) for t, _ in MERIWETHER_SETTLES[:3]}), 1)


class EvaluatorCountsEvents(LedgerCase):
    """The old ladder's gates (`enabled: False`, the rollback) count the same way."""

    def test_the_settled_lane_counts_one_settlement_an_event(self):
        ev_ = Evaluator(self.ledger, clock=self.clock)
        for strike in ("7", "8", "9"):
            self.settle(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", "1")
        lane = ev_._settled_lane("a", "kalshi-shadow", 1, "day", 0)
        self.assertEqual((lane["settled"], lane["open"]), (1, False))
        self.settle("KXMLBTOTAL-26SEP231545MINSF-7", "1")
        self.settle("KXHIGHNY-26SEP24-B72.5", "1")
        lane = ev_._settled_lane("a", "kalshi-shadow", 1, "day", 0)
        self.assertEqual((lane["settled"], lane["open"]), (3, True))

    def test_the_screens_closed_trade_count_is_independent(self):
        ev_ = Evaluator(self.ledger, clock=self.clock)
        self.stake(200)
        for strike in ("7", "8", "9"):
            self.buy(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", 10, "0.4")
            self.settle(f"KXMLBTOTAL-26SEP231310WSHDET-{strike}", "5")
        self.assertEqual(ev_.independent_closed("a", "kalshi-shadow"), 1)
        self.assertEqual(len(ev_.trade_returns("a", "kalshi-shadow")[0]), 3)  # the statistics still see three trades
        with patch.dict(CONSTITUTION["allocator"], {"independent_settlements": "trade"}):
            self.assertEqual(Evaluator(self.ledger, clock=self.clock).independent_closed("a", "kalshi-shadow"), 3)


class MoneySet(unittest.TestCase):
    """Every key of Deploy A's money set carries a row of the plan's closed table, inside its bounds."""

    def setUp(self):
        self.r = CONSTITUTION["allocator"]

    def test_independent_settlements_are_counted_per_event(self):
        self.assertEqual(self.r["independent_settlements"], "event")

    def test_one_event_holds_at_most_a_quarter_of_a_real_stake(self):
        self.assertEqual(self.r["max_event_share"], "0.25")
        self.assertTrue(D("0.2") <= D(self.r["max_event_share"]) <= D("0.5"))

    def test_an_unproven_familys_first_real_stake_is_a_probe(self):
        probe, bunt = self.r["probe_bunt_usd"], self.r["bunt_usd"]
        self.assertEqual(probe, {"kalshi": "10", "alpaca": "25"})
        self.assertTrue(D("5") <= D(probe["kalshi"]) <= D("15"))
        self.assertTrue(D("20") <= D(probe["alpaca"]) <= D("25"))
        # A proven family's bunt is unchanged and never smaller than a probe.
        self.assertEqual(bunt, {"kalshi": "30", "alpaca": "25"})
        self.assertTrue(D("30") <= D(bunt["kalshi"]) <= D("60") and D("25") <= D(bunt["alpaca"]) <= D("60"))
        self.assertTrue(all(D(probe[v]) <= D(bunt[v]) for v in probe))
        # Alpaca takes no crypto order under $10, and the book refuses an order over half an account.
        self.assertGreaterEqual(D(probe["alpaca"]) / 2, D(self.r["venue_minimum_usd"]["alpaca"]))
        self.assertEqual(self.r["option_bunt_usd"], "80")  # one contract cannot be cut smaller

    def test_a_family_is_proven_by_its_pooled_record(self):
        rule = self.r["family_proven"]
        self.assertEqual(rule, {"min_independent_settlements": 10, "practice_weight": "0.5", "real_weight": "1",
                                "confidence": "0.8"})
        self.assertTrue(10 <= rule["min_independent_settlements"] <= 20)

    def test_the_one_loss_trial_and_the_event_position_share(self):
        self.assertEqual(self.r["hysteresis_after_settled"], 3)
        self.assertTrue(0 <= self.r["hysteresis_after_settled"] <= 5)
        self.assertEqual(self.r["position_share_event"], "0.2")
        self.assertTrue(D("0.15") <= D(self.r["position_share_event"]) <= D("0.5"))
        self.assertEqual(self.r["position_share"], 0.5)  # Alpaca keeps its half
        self.assertEqual(self.r["real_drawdown_demote"], 0.35)  # the stay drawdown always applies, unchanged

    def test_the_book_side_keys(self):
        self.assertEqual(self.r["longshot_floor_real"], "0.30")
        self.assertTrue(D("0.15") <= D(self.r["longshot_floor_real"]) <= D("0.35"))
        self.assertEqual(self.r["real_entry_liquidity"], "maker_unless_family_taker_positive")

    def test_the_lines_that_may_only_rise_did_not_fall(self):
        self.assertGreaterEqual(self.r["bunt_at"], 1.01)
        self.assertGreaterEqual(self.r["bunt_min_trades"], 5)
        self.assertGreaterEqual(self.r["bunt_min_settled"], 3)
        self.assertGreaterEqual(self.r["swing_min_real_trades"], 8)


if __name__ == "__main__":
    unittest.main()


def hand_pool(observations):
    """The family record's pooled statistics, written out independently: weighted mean, the
    reliability-weighted sd, n_eff = (sum w)^2 / sum w^2, and the one-sided 80% lower bound on
    Student's t with n_eff - 1 degrees of freedom (None under two effective observations)."""
    from league import stats

    W = sum(w for _, w in observations)
    W2 = sum(w * w for _, w in observations)
    m = sum(v * w for v, w in observations) / W
    n_eff = W * W / W2
    if n_eff < 2:
        return m, None, n_eff, None
    sd = math.sqrt(sum(w * (v - m) ** 2 for v, w in observations) / (W - W2 / W))
    return m, sd, n_eff, m - stats.t_quantile(0.8, n_eff - 1) * sd / math.sqrt(n_eff)


class FamilyCase(LedgerCase):
    def setUp(self):
        super().setUp()
        self.agents = {}
        self.house = SimpleNamespace(ledger=self.ledger, registry=SimpleNamespace(agents=self.agents))

    def member(self, agent, family="weather-favorites", venue="kalshi", alive=True):
        self.agents[agent] = SimpleNamespace(id=agent, family=family, venue=venue, alive=alive)

    def record(self, family="weather-favorites", venue="kalshi"):
        return allocator.family_record(self.house, family, venue)


class FamilyRecord(FamilyCase):
    """P1's proof: the family's pooled forward record over independent events."""

    def test_the_pooled_numbers_by_hand(self):
        for agent in ("m1", "m2"):
            self.member(agent)
        self.member("m3", alive=False)  # the dead count
        self.stake(200, agent="m1")
        self.stake(200, agent="m2")
        self.stake(30, agent="m2", book="kalshi")
        self.stake(200, agent="m3")
        self.settle("KXHIGHNY-26SEP24-B72.5", "2", agent="m1")      # E1 practice +1%
        self.settle("KXHIGHNY-26SEP24-B74.5", "2", agent="m2")      # E1 again, another member: the same bet
        self.settle("KXHIGHMIA-26SEP24-B90.5", "4", agent="m1")     # E2 practice +2%
        self.settle("KXHIGHAUS-26SEP24-T96", "0.6", agent="m2", book="kalshi")  # E3 REAL +2%
        self.settle("KXHIGHLAX-26SEP24-B80.5", "-1", agent="m3")    # E4 practice -0.5%
        rec = self.record()
        obs = [(math.log(1.01), 0.5), (math.log(1.02), 0.5), (math.log(1.02), 1.0), (math.log(0.995), 0.5)]
        m, sd, n_eff, bound = hand_pool(obs)
        self.assertEqual((rec["n"], rec["real_n"], rec["members"], rec["members_counted"]), (4, 1, 3, 3))
        self.assertAlmostEqual(rec["mean_log"], m, places=12)
        self.assertAlmostEqual(rec["sd"], sd, places=12)
        self.assertAlmostEqual(rec["n_eff"], n_eff, places=12)
        self.assertAlmostEqual(rec["bound"], bound, places=12)
        self.assertFalse(rec["proven"])  # 4 independent settlements, 10 needed
        self.assertEqual(rec["state"], "unproven")

    def test_ten_independent_winning_events_prove_a_family_and_nine_do_not(self):
        self.member("m1")
        self.stake(200, agent="m1")
        for day in range(1, 10):
            self.settle(f"KXHIGHNY-26SEP{day:02d}-B72.5", str(1 + day / 10), agent="m1")
        rec = self.record()
        self.assertEqual(rec["n"], 9)
        self.assertGreater(rec["bound"], 0)
        self.assertFalse(rec["proven"])
        self.settle("KXHIGHNY-26SEP10-B72.5", "1.5", agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["proven"], rec["state"]), (10, True, "proven"))
        # One big loss on the eleventh event takes the bound under zero: unproven again.
        self.settle("KXHIGHNY-26SEP11-B72.5", "-30", agent="m1")
        rec = self.record()
        self.assertLessEqual(rec["bound"], 0)
        self.assertFalse(rec["proven"])

    def test_stacked_strikes_are_one_observation_worth_their_sum(self):
        self.member("m1")
        self.stake(200, agent="m1")
        for ticker, quantity, price in MERIWETHER_BUYS:
            self.buy(ticker, quantity, price, agent="m1")
        for ticker, pnl in MERIWETHER_SETTLES:
            self.settle(ticker, pnl, agent="m1")
        rec = self.record()
        self.assertEqual(rec["n"], 2)
        wshdet = sum(math.log1p(float(p) / 200) for _, p in MERIWETHER_SETTLES[:3])
        minsf = sum(math.log1p(float(p) / 200) for _, p in MERIWETHER_SETTLES[3:])
        self.assertAlmostEqual(rec["mean_log"], (wshdet + minsf) / 2, places=12)
        self.assertEqual(rec["taker"]["n"], 2)  # every entry was a taker fill
        self.assertEqual(rec["maker"]["n"], 0)

    def test_an_event_several_members_traded_is_one_observation_at_the_largest_weight(self):
        self.member("p")
        self.member("r")
        self.stake(200, agent="p")
        self.stake(20, agent="r", book="kalshi")
        self.settle("KXBTCD-26SEP2401-T62999.99", "4", agent="p")            # practice +2%
        self.settle("KXBTCD-26SEP2401-T63249.99", "-1", agent="r", book="kalshi")  # real -5%
        rec = self.record()
        self.assertEqual((rec["n"], rec["real_n"]), (1, 1))
        expected = (0.5 * math.log(1.02) + 1.0 * math.log(0.95)) / 1.5
        self.assertAlmostEqual(rec["mean_log"], expected, places=12)
        self.assertIsNone(rec["bound"])  # one observation: no bound

    def test_a_swept_or_dead_member_keeps_its_record_and_a_cutoff_starts_it_afresh(self):
        self.member("gone", alive=False)
        self.stake(200, agent="gone")
        self.settle("KXHIGHNY-26SEP20-B72.5", "2", agent="gone")
        self.stake(-202, agent="gone")  # swept at death: its net stake is now below zero
        self.assertEqual(self.record()["n"], 1)
        self.assertAlmostEqual(self.record()["mean_log"], math.log(1.01), places=12)
        self.ledger.append("book.fill_correction", {"book": "kalshi-shadow", "cash_delta": "0", "fees_delta": "0",
                                                    "realized_delta": "0", "holding_cost_deltas": {}}, agent="gone")
        self.assertEqual(self.record()["n"], 0)  # a repaired attribution starts its evidence afresh

    def test_members_are_the_familys_on_that_venue_only(self):
        self.member("w1")
        self.member("other", family="sports-favorites")
        self.member("alp", venue="alpaca")
        for agent in ("w1", "other", "alp"):
            self.stake(200, agent=agent)
            self.settle(f"KXHIGHNY-26SEP2{len(agent)}-B72.5", "2", agent=agent)
        rec = self.record()
        self.assertEqual((rec["n"], rec["members"]), (1, 1))

    def test_maker_and_taker_records_apart(self):
        self.member("mk")
        self.member("tk")
        for agent in ("mk", "tk"):
            self.stake(200, agent=agent)
        for day in range(1, 11):
            ticker = f"KXHIGHNY-26SEP{day:02d}-B72.5"
            self.buy(ticker, 10, "0.95", agent="mk", liquidity="maker")
            self.settle(ticker, str(0.4 + day / 100), agent="mk")
            other = f"KXETH15M-26SEP{day:02d}1200-00"
            self.buy(other, 10, "0.50", agent="tk", liquidity="taker")
            self.settle(other, "-2" if day % 2 else "1.5", agent="tk")
        rec = self.record()
        self.assertEqual((rec["maker"]["n"], rec["taker"]["n"], rec["n"]), (10, 10, 20))
        self.assertTrue(rec["maker"]["positive"])
        self.assertFalse(rec["taker"]["positive"])
        self.assertEqual((rec["maker"]["members"], rec["taker"]["members"]), (1, 1))
        m, _, _, bound = hand_pool([(math.log1p((0.4 + d / 100) / 200), 0.5) for d in range(1, 11)])
        self.assertAlmostEqual(rec["maker"]["mean_log"], m, places=12)
        self.assertAlmostEqual(rec["maker"]["bound"], bound, places=12)

    def test_alpaca_counts_one_observation_per_closed_trade(self):
        for agent in ("a1", "a2"):
            self.member(agent, family="crypto-alts-reversion", venue="alpaca")
            self.stake(200, agent=agent, book="alpaca-paper")
            self.buy("BTC/USD", "0.001", "80000", agent=agent, book="alpaca-paper")
            self.sell("BTC/USD", "1.00", agent=agent, book="alpaca-paper")
        rec = self.record("crypto-alts-reversion", "alpaca")
        self.assertEqual(rec["n"], 2)
        self.assertAlmostEqual(rec["mean_log"], math.log(1.005), places=12)

    def test_the_rows_are_the_evaluators_trade_returns(self):
        """One definition: a member's log growths are ln(1 + r) of `Evaluator.trade_returns` read
        through a fixed ledger position (the stake is the most it was ever lent)."""
        self.member("m1")
        self.stake(200, agent="m1")
        self.buy("KXHIGHNY-26SEP20-B72.5", 10, "0.9", agent="m1")
        self.sell("KXHIGHNY-26SEP20-B72.5", "0.30", agent="m1", flat=False)
        self.sell("KXHIGHNY-26SEP20-B72.5", "0.20", agent="m1")
        self.settle("KXHIGHMIA-26SEP20-B90.5", "-1.5", agent="m1")
        self.stake(-150, agent="m1")  # a sweep does not rescale what was closed
        returns, _ = Evaluator(self.ledger).trade_returns("m1", "kalshi-shadow", until_seq=self.ledger.head()[0])
        self.assertEqual(len(returns), 2)
        rec = self.record()
        self.assertAlmostEqual(rec["mean_log"] * rec["n"], sum(math.log1p(r) for r in returns), places=12)

    def test_the_tape_reads_only_new_rows(self):
        self.member("m1")
        self.stake(200, agent="m1")
        tape = allocator.TradeTape()
        self.settle("KXHIGHNY-26SEP20-B72.5", "2", agent="m1")
        first = allocator.family_record(self.house, "weather-favorites", "kalshi", tape=tape)
        cursor = tape.cursor
        self.assertEqual((first["n"], cursor), (1, self.ledger.head()[0]))
        self.settle("KXHIGHNY-26SEP21-B72.5", "2", agent="m1")
        with patch.object(self.ledger, "iter", wraps=self.ledger.iter) as reads:
            second = allocator.family_record(self.house, "weather-favorites", "kalshi", tape=tape)
        self.assertEqual(second["n"], 2)
        self.assertEqual([c.kwargs.get("after") for c in reads.call_args_list], [cursor])  # one read, from the cursor
