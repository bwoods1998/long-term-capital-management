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

    def test_ten_independent_events_prove_a_family_and_nine_do_not(self):
        self.member("m1")
        self.stake(200, agent="m1")
        results = ["2.5", "2.5", "-1", "2.5", "2.5", "-1", "2.5", "2.5", "-1", "2.5"]  # 7 of 10 win: not lopsided
        for day, pnl in enumerate(results[:9], start=1):
            self.buy(f"KXHIGHNY-26SEP{day:02d}-B72.5", 10, "0.60", agent="m1")
            self.settle(f"KXHIGHNY-26SEP{day:02d}-B72.5", pnl, agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["lopsided"]), (9, False))
        self.assertGreater(rec["bound"], 0)
        self.assertFalse(rec["proven"])
        self.buy("KXHIGHNY-26SEP10-B72.5", 10, "0.60", agent="m1")
        self.settle("KXHIGHNY-26SEP10-B72.5", results[9], agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["proven"], rec["state"]), (10, True, "proven"))
        # One big loss on the eleventh event takes the bound under zero: unproven again.
        self.settle("KXHIGHNY-26SEP11-B72.5", "-30", agent="m1")
        rec = self.record()
        self.assertLessEqual(rec["bound"], 0)
        self.assertFalse(rec["proven"])

    def test_ten_small_wins_and_no_loss_do_not_prove_a_favourites_family(self):
        """The House's own rule for a lopsided record (`stats.lopsided_growth_lcb`, beside the t bound,
        as `Evaluator._judge_family` applies it): ten 95c favourites that all paid have a t bound above
        zero, but at 80% one miss in seven cannot be ruled out, and one miss costs nineteen wins."""
        self.member("m1")
        self.stake(200, agent="m1")
        for day in range(1, 11):
            ticker = f"KXHIGHNY-26SEP{day:02d}-B72.5"
            self.buy(ticker, 10, "0.95", agent="m1", liquidity="maker")
            self.settle(ticker, "0.5", agent="m1")
        rec = self.record()
        self.assertEqual((rec["n"], rec["lopsided"]), (10, True))
        self.assertGreater(rec["bound"], 0)             # the t bound alone would prove it
        self.assertLess(rec["loss_gate"], 0)            # the loss-rate gate does not
        self.assertAlmostEqual(rec["risk_per_entry"], 9.5 / 200, places=12)
        self.assertEqual((rec["proven"], rec["state"]), (False, "unproven"))
        with patch.dict(CONSTITUTION["ladder"], {"lopsided_win_rate": 1.01}):  # no record is lopsided: the t bound alone
            self.assertTrue(self.record()["proven"])

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
        made = {d: (2.5 + d / 100 if d % 3 else -1.0) for d in range(1, 11)}  # 7 of 10 win: not lopsided
        for day in range(1, 11):
            ticker = f"KXHIGHNY-26SEP{day:02d}-B72.5"
            self.buy(ticker, 10, "0.60", agent="mk", liquidity="maker")
            self.settle(ticker, str(made[day]), agent="mk")
            other = f"KXETH15M-26SEP{day:02d}1200-00"
            self.buy(other, 10, "0.50", agent="tk", liquidity="taker")
            self.settle(other, "-2" if day % 2 else "1.5", agent="tk")
        rec = self.record()
        self.assertEqual((rec["maker"]["n"], rec["taker"]["n"], rec["n"]), (10, 10, 20))
        self.assertTrue(rec["maker"]["positive"])
        self.assertFalse(rec["taker"]["positive"])
        self.assertEqual((rec["maker"]["members"], rec["taker"]["members"]), (1, 1))
        m, _, _, bound = hand_pool([(math.log1p(made[d] / 200), 0.5) for d in range(1, 11)])
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
        # $1.00 made on $200 less the practice haircut on the $80 entry and the $1 exit (crypto, 4 bps a side)
        self.assertAlmostEqual(rec["mean_log"], math.log1p((1.00 - 81 * 4 / 10_000) / 200), places=12)

    def test_an_alpaca_practice_trade_pays_the_haircut_e_takes(self):
        """Review of #224 (Sept 24, 2026): the allocator's E takes `evidence.alpaca_paper_haircut_bps` off
        every alpaca-paper fill (Alpaca's practice fills look optimistic), but the family's proof read the
        same fills raw. A practice trade now pays it on its entry and exit notional; a real trade does not."""
        self.member("a1", family="crypto-alts-reversion", venue="alpaca")
        self.stake(200, agent="a1", book="alpaca-paper")
        self.stake(25, agent="a1", book="alpaca")
        self.buy("ETH/USD", "0.02", "2500", agent="a1", book="alpaca-paper")  # a $50 entry
        self.sell("ETH/USD", "0.40", agent="a1", book="alpaca-paper")       # the helper's exit: $1 of notional
        self.buy("SOL/USD", "0.1", "150", agent="a1", book="alpaca")         # a $15 real entry
        self.sell("SOL/USD", "0.30", agent="a1", book="alpaca")
        bps = CONSTITUTION["allocator"]["evidence"]["alpaca_paper_haircut_bps"]["crypto"]
        real = math.log1p(0.30 / 25)
        rec = self.record("crypto-alts-reversion", "alpaca")
        self.assertEqual(rec["n"], 2)
        self.assertAlmostEqual(rec["mean_log"], hand_pool([(math.log1p((0.40 - 51 * bps / 10_000) / 200), 0.5), (real, 1.0)])[0], places=12)
        with patch.dict(CONSTITUTION["allocator"]["evidence"], {"alpaca_paper_haircut_bps": 0}):  # the rule off: raw fills
            raw = self.record("crypto-alts-reversion", "alpaca")
        self.assertAlmostEqual(raw["mean_log"], hand_pool([(math.log1p(0.40 / 200), 0.5), (real, 1.0)])[0], places=12)

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

    def test_a_trade_is_measured_against_what_had_been_lent_by_then(self):
        """huang-6 traded a $25 stake that was raised to $60 later (Sept 21, 2026): its early trades grew
        its wealth by what they made over $25, and a later raise must not shrink them. Each row is
        `trade_returns` read through that row's own ledger position."""
        self.member("m1")
        self.stake(25, agent="m1", book="kalshi")
        self.settle("KXDOGE15M-26SEP211445-45", "4.253", agent="m1", book="kalshi")
        self.stake(35, agent="m1", book="kalshi")
        self.settle("KXDOGE15M-26SEP212145-45", "-9.552", agent="m1", book="kalshi")
        self.stake(-54.7117, agent="m1", book="kalshi")
        rec = self.record()
        self.assertEqual(rec["n"], 2)
        self.assertAlmostEqual(rec["mean_log"], (math.log1p(4.253 / 25) + math.log1p(-9.552 / 60)) / 2, places=12)
        ev_ = Evaluator(self.ledger)
        first = self.ledger.head()[0] - 3  # the first settlement's seq
        self.assertAlmostEqual(ev_.trade_returns("m1", "kalshi", until_seq=first)[0][0], 4.253 / 25, places=12)

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


KALSHI_IDLE = '''
NEEDS = {"venue": "kalshi", "horizon": "hour", "style": "favorites", "series": ["KXBTCD"]}
PARAMS = {}
def decide(ctx):
    return {"intents": [], "thought": "waiting"}
'''


def canned(family, venue="kalshi", *, proven=False, n=4, bound=-0.01, taker_positive=False):
    """A family record as `allocator.family_record` returns it, with the numbers a test sets."""
    side = {"n": n, "n_eff": float(n), "mean_log": 0.01, "sd": 0.02, "bound": bound, "positive": False, "members": 1}
    return {"family": family, "venue": venue, "through": 0, "members": 2, "members_counted": 1, "n": n,
            "n_eff": float(n), "mean_log": 0.01, "sd": 0.02, "bound": bound, "proven": proven,
            "state": "proven" if proven else "unproven", "real_n": 0,
            "maker": dict(side), "taker": {**side, "positive": taker_positive, "bound": 0.004 if taker_positive else bound},
            "rule": allocator._family_rule()}


class KalshiHouse(unittest.TestCase):
    """A House with a real (fake) Kalshi venue and its practice book: probes are $10 and bunts $30 here."""

    def setUp(self):
        import threading  # noqa: F401 - the House's own threads
        from league.economy import load_game
        from league.house import House, Settings
        from league.tests.fakes import FakeBroker
        from league.tests.test_ladder import FakeAuditor, InProcessSandbox

        strategies = patch("league.strategies.all_strategies", return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.real = FakeBroker("kalshi", cash="1000", family="kalshi")
        self.paper = FakeBroker("kalshi-shadow", family="kalshi")
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.auditor = FakeAuditor()
        self.house = House(Path(self.dir.name) / "house", brokers={"kalshi": self.real, "kalshi-shadow": self.paper},
                           sandbox=InProcessSandbox(), clock=self.clock, game=game, auditor=self.auditor,
                           settings=Settings(mark_every_seconds=0, research=False, real_money=True))
        self.auditor.ledger = self.house.ledger
        # Without a grant the envelope is the tuition line: room for a $30 bunt and a probe or two.
        tuition = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "100"})
        tuition.start()
        self.addCleanup(tuition.stop)
        self.families: dict = {}
        self.records = patch.object(allocator, "family_record", side_effect=self._record)
        self.records.start()
        self.addCleanup(self.records.stop)

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def _record(self, house, family, venue, **kw):
        return self.families.get(family) or canned(family, venue)

    def agent(self, name="kay", family="weather-favorites"):
        agent = self.house.spawn(name, family, KALSHI_IDLE, reason="test", endowment="2.5")
        self.house.evaluator.seat(agent.id, 1, "test: straight to practice")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def evidence_of(self, table):
        real = allocator.evidence

        def fake(house, agent, rung=None):
            rung = house.evaluator.rung(agent.id) if rung is None else rung
            if agent.id not in table:
                return real(house, agent, rung)
            row = dict(table[agent.id])
            row.setdefault("cooling", False)
            return ev(agent=agent.id, venue=agent.venue, rung=rung, **row)
        return patch.object(allocator, "evidence", side_effect=fake)

    def tick(self, n=1, seconds=300):
        for _ in range(n):
            self.clock.advance(seconds)
            self.house.tick()

    def promote_row(self, agent):
        return [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "promote"][-1]


class ProbesAndBunts(KalshiHouse):
    """P1: a paper agent at the bunt line is seated as a probe unless its family is proven."""

    READY = dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)

    def test_an_unproven_familys_agent_is_seated_as_a_probe(self):
        a = self.agent()
        with self.evidence_of({a.id: self.READY}):
            self.tick()
        house = self.house
        self.assertEqual(house.evaluator.rung(a.id), 2)
        self.assertEqual(house.books["kalshi"].account(a.id).staked, D("10"))
        row = house.allocator.board()["agents"][a.id]
        self.assertEqual((row["band"], row["family"], row["family_state"], row["family_n"]), ("probe", "weather-favorites", "unproven", 4))
        self.assertEqual(row["family_bound"], -0.01)
        promote = self.promote_row(a)
        # A first-class band (the publisher and the site know it since #222 and personal-site #6): the
        # verdict, the board's row and its summary all say "probe", with the family record behind it.
        self.assertEqual((promote["band_from"], promote["band_to"], promote["stake_usd"]), ("paper", "probe", "10"))
        self.assertEqual(promote["family"]["state"], "unproven")
        self.assertIn("probe", promote["reason"])
        self.assertEqual(house.allocator.band_of(a.id), "bunt")  # the book's daily-loss rule: probes are bunts
        board = house.allocator.board()
        self.assertEqual(board["bands"]["kalshi"]["probe"], {"count": 1, "capital_usd": D("10")})
        self.assertNotIn("bunt", board["bands"]["kalshi"])
        self.assertEqual([(m["from_band"], m["to_band"]) for m in board["moves"] if m["agent"] == a.id], [("paper", "probe")])

    def test_a_proven_familys_agent_is_seated_as_a_bunt(self):
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=16, bound=0.0033)
        a = self.agent()
        with self.evidence_of({a.id: self.READY}):
            self.tick()
        self.assertEqual(self.house.books["kalshi"].account(a.id).staked, D("30"))
        row = self.house.allocator.board()["agents"][a.id]
        self.assertEqual((row["band"], row["family_state"], row["family_n"]), ("bunt", "proven", 16))
        self.assertEqual(self.promote_row(a)["band_to"], "bunt")

    def test_a_probe_becomes_a_bunt_the_pass_after_its_family_is_proven_and_back(self):
        a = self.agent()
        book = self.house.books["kalshi"]
        table = {a.id: dict(self.READY, w_real=1.0)}
        with self.evidence_of(table):
            self.tick()
            self.assertEqual(book.account(a.id).staked, D("10"))
            self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=10, bound=0.001)
            self.tick()
            self.assertEqual(book.account(a.id).staked, D("30"))
            self.assertEqual(self.house.allocator.board()["agents"][a.id]["band"], "bunt")
            sizes = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "size"]
            self.assertEqual((sizes[-1]["band"], sizes[-1]["moved_usd"]), ("bunt", "20.00"))
            # The bound falls to zero or below: back to a probe, by free cash only.
            self.families["weather-favorites"] = canned("weather-favorites", proven=False, n=11, bound=-0.0001)
            self.tick()
            self.assertEqual(book.account(a.id).staked, D("10"))
            self.assertEqual(self.house.allocator.board()["agents"][a.id]["band"], "probe")
            sizes = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "size"]
            self.assertEqual(sizes[-1]["band"], "probe")

    def test_a_bunt_turned_probe_never_sells_to_shrink(self):
        from league.book import Intent
        from league.ledger import now_iso
        from league.tests.test_book import event

        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=16, bound=0.0033)
        a = self.agent()
        book = self.house.books["kalshi"]
        table = {a.id: dict(self.READY, w_real=1.0)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(book.account(a.id).staked, D("30"))
        instrument = event(venue="kalshi")
        self.real.set_quote(instrument, ".79", ".80")
        book.resolves_at = lambda instrument: self.clock() + 3600
        intent = Intent.new(agent=a.id, instrument=instrument, side="buy", quantity=D(3), reason="test", created_at=now_iso(self.clock))
        self.assertEqual(book.submit([intent])[0].status, "filled")
        held = {k: h.quantity for k, h in book.account(a.id).holdings.items()}
        self.assertTrue(held)
        self.families["weather-favorites"] = canned("weather-favorites", proven=False, n=17, bound=-0.002)
        submitted = len(self.real.submitted)
        with self.evidence_of(table):
            self.house.allocator.rebalance()
        account = book.account(a.id)
        self.assertEqual([o for o in self.real.submitted[submitted:] if o.side == "sell"], [])
        self.assertEqual({k: h.quantity for k, h in account.holdings.items()}, held)
        self.assertLess(account.staked, D("30"))  # free cash came back ...
        self.assertGreaterEqual(account.cash - book._reserved_cash(a.id), D(0))  # ... and only free cash
        self.assertGreaterEqual(book.equity(a.id), D("9.99"))  # to the probe's $10, its position kept
        self.assertEqual(self.house.allocator.board()["agents"][a.id]["band"], "probe")

    def test_a_raise_the_envelope_cannot_lend_does_not_raise_the_limits(self):
        """Review of #224 (Sept 24, 2026): a probe whose family is proven while the envelope has no room
        for the bunt's $20 raise keeps a fifth of what it holds ($2), not a fifth of the $30 it was not
        lent ($6: a 60% position, and the book's 30% desk cap let a $3.00 one fill). The raise, once
        there is room for it, brings the bunt's limits with it."""
        agents = [self.agent(f"kay{i}") for i in range(10)]  # ten $10 probes fill the $100 envelope
        book = self.house.books["kalshi"]
        table = {a.id: dict(self.READY, w_real=1.0) for a in agents}
        a = agents[0]
        with self.evidence_of(table):
            self.tick()
            self.assertEqual([book.account(x.id).staked for x in agents], [D("10")] * 10)
            self.assertEqual(self.house.allocator.headroom("kalshi"), D(0))
            self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=10, bound=0.001)
            self.tick()
            self.house.wake(self.house.registry.get(a.id))  # every wake re-seats: the limits are written again
            self.assertEqual(book.account(a.id).staked, D("10"))
            row = self.house.allocator.board()["agents"][a.id]
            self.assertEqual((row["band"], row["target_usd"]), ("bunt", "30"))
            self.assertEqual((book.limits[a.id].max_position_usd, book.limits[a.id].max_order_usd), (D("2.00"), D("2.00")))
            with patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "120"}):  # room for one raise
                self.tick()
            self.assertEqual(book.account(a.id).staked, D("30"))
            self.assertEqual((book.limits[a.id].max_position_usd, book.limits[a.id].max_order_usd), (D("6.00"), D("6.00")))

    def full_floor(self):
        """A $40 envelope held by a proven family's $30 bunt (E 1.02) and an unproven family's $10 probe (E 1.06)."""
        tight = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "40"})
        tight.start()
        self.addCleanup(tight.stop)
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=16, bound=0.0033)
        proven, probe = self.agent("mullins", family="weather-favorites"), self.agent("hawkins", family="kalshi-favorites")
        table = {proven.id: dict(self.READY, e=1.02, w_real=1.0), probe.id: dict(self.READY, e=1.06, w_real=1.0)}
        with self.evidence_of(table):
            self.tick()
        book = self.house.books["kalshi"]
        self.assertEqual((book.account(proven.id).staked, book.account(probe.id).staked), (D("30"), D("10")))
        self.assertEqual(self.house.allocator.headroom("kalshi"), D(0))
        return proven, probe, table

    def test_a_probe_never_displaces_a_proven_familys_bunt(self):
        """Review of #224 (Sept 24, 2026): with the envelope full, an unproven family's newcomer at E 1.05
        displaced the proven family's flat bunt at E 1.02 -- $30 of proven money back to practice to seat
        $10 of unproven money, on the agent-level E the family's proof replaced. It waits instead."""
        proven, probe, table = self.full_floor()
        newcomer = self.agent("huang", family="crypto-15m-favorites")
        table[newcomer.id] = dict(self.READY, e=1.05)
        with self.evidence_of(table):
            self.tick()
        rungs = [self.house.evaluator.rung(a.id) for a in (proven, probe, newcomer)]
        self.assertEqual(rungs, [2, 2, 1])
        status = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=newcomer.id) if e.payload.get("decision") == "progress"]
        self.assertEqual((status[-1]["stage"], status[-1]["reason"]),
                         ("envelope", "the kalshi envelope cannot seat another $10 probe and no weaker flat probe can be displaced"))

    def test_a_proven_familys_newcomer_still_displaces_a_weaker_probe(self):
        proven, probe, table = self.full_floor()
        table[probe.id] = dict(self.READY, e=1.01, w_real=1.0)  # now the weakest flat agent on the floor
        newcomer = self.agent("mullins", family="weather-favorites")
        table[newcomer.id] = dict(self.READY, e=1.08)
        with self.evidence_of(table):
            self.tick()
        self.assertEqual([self.house.evaluator.rung(a.id) for a in (proven, probe)], [2, 1])  # the probe gave way
        self.assertEqual(self.house.evaluator.rung(newcomer.id), 1)  # its $30 still waits for the $20 the probe's $10 did not free

    def test_a_probe_keeps_what_it_makes_on_its_own_base(self):
        """`bunt_growth: "w_real"` applies to both tiers, each on its own base, up to the swing line."""
        a = self.agent()
        alloc = self.house.allocator
        self.assertEqual(alloc.target_stake(a, "bunt", ev(agent=a.id, rung=2, w_real=1.2)), D("12.00"))
        self.assertEqual(alloc.target_stake(a, "bunt", ev(agent=a.id, rung=2, w_real=2.0)), D("12.50"))  # 10 x 1.25
        self.assertEqual(alloc.target_stake(a, "bunt", ev(agent=a.id, rung=2, w_real=0.8)), D("10"))
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=12, bound=0.001)
        alloc._begin_pass()
        self.assertEqual(alloc.target_stake(a, "bunt", ev(agent=a.id, rung=2, w_real=1.2)), D("36.00"))

    def test_the_family_is_read_once_a_pass(self):
        agents = [self.agent(f"kay{i}") for i in range(3)]
        table = {a.id: dict(e=1.0, w_paper=1.0, paper_trades=1) for a in agents}
        with self.evidence_of(table):
            self.records.stop()
            with patch.object(allocator, "family_record", side_effect=self._record) as reads:
                self.house.allocator.rebalance()
            self.records.start()
        families = [c.args[1] for c in reads.call_args_list]
        self.assertEqual(families.count("weather-favorites"), 1)

    def test_the_book_reads_the_familys_taker_record(self):
        a = self.agent()
        alloc = self.house.allocator
        self.assertEqual(alloc.family_taker(a.id), {"family": "weather-favorites", "positive": False, "n": 4,
                                                   "mean_log": 0.01, "bound": -0.01})
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=12, bound=0.002, taker_positive=True)
        alloc.rebalance()
        self.assertTrue(alloc.family_taker(a.id)["positive"])
        self.assertIsNone(alloc.family_taker("nobody"))
        with patch.object(allocator, "enabled", return_value=False):
            self.assertIsNone(alloc.family_taker(a.id))
        # The TAKER record, not the family's proof: a family proven on resting bids (weather favourites,
        # every observation a maker's) has no taker record, and its real entries stay post-only. Review
        # of #224: answering with the whole record's proof passed every other test.
        record = canned("weather-favorites", proven=True, n=16, bound=0.0033)
        record["taker"] = {"n": 0, "n_eff": 0.0, "mean_log": 0.0, "sd": None, "bound": None, "positive": False, "members": 0}
        self.families["weather-favorites"] = record
        alloc.rebalance()
        self.assertEqual(alloc.tier(a), "bunt")
        self.assertEqual(alloc.family_taker(a.id), {"family": "weather-favorites", "positive": False, "n": 0,
                                                   "mean_log": 0.0, "bound": None})

    def test_the_audit_judges_a_probe_as_a_probe(self):
        a = self.agent()
        alloc = self.house.allocator
        context = alloc.context(ev(agent=a.id, venue="kalshi", e=1.1, paper_trades=6), "bunt")
        self.assertEqual((context["band_to"], context["tier"], context["stake_usd"]), ("probe", "probe", "10"))
        self.assertEqual(context["family"]["family"], "weather-favorites")
        self.assertEqual((context["family"]["state"], context["family"]["n"], context["family"]["bound"]), ("unproven", 4, -0.01))
        self.assertIn("taker", context["family"])
        self.assertEqual(context["family"]["rule"]["min_independent_settlements"], 10)


class OptionsProbe(unittest.TestCase):
    def test_an_options_probe_is_still_one_affordable_contract(self):
        """One contract cannot be cut smaller: an options probe is staked `option_bunt_usd` ($80)."""
        from league.tests.test_allocator import HouseCaseReal

        class Case(HouseCaseReal):
            def runTest(self):
                pass

        case = Case()
        case.setUp()
        try:
            from league import seeds

            agent = case.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test",
                                     specialty="alpaca-options")
            with patch.object(allocator, "family_record", return_value=canned("options-breakout", "alpaca")):
                self.assertEqual(case.house.allocator.tier(agent), "probe")
                self.assertEqual(case.house.allocator.target_stake(agent, "bunt"), D("80"))
        finally:
            case.tearDown()


class GrantSeats(unittest.TestCase):
    def test_the_grants_seat_count_follows_the_smallest_real_stake_the_probe(self):
        from league.live_trading import policy

        grant = policy({"kalshi": "517.75", "alpaca": "500"})
        self.assertEqual((grant["stake_usd"], grant["max_agents"]), ("10", 101))  # floor($1,017.75 / $10)
        self.assertIn("probes of $25 at alpaca, $10 at kalshi for an unproven family", grant["scaling"])


class OneLossTrial(unittest.TestCase):
    """P2: the hysteresis exit applies once an agent has `hysteresis_after_settled` independent real
    results in its current stay; before that only the stay drawdown and death send it back."""

    def test_an_early_loss_is_not_a_demotion_and_the_third_settlement_restores_the_exit(self):
        p = P()
        line = p["bunt_at"] * p["hysteresis"]
        self.assertEqual(p["hysteresis_after_settled"], 3)
        self.assertEqual(allocator.target_band(ev(rung=2, e=line - 0.05, real_stay_closed=0), p)[0], "bunt")
        band, why = allocator.target_band(ev(rung=2, e=line - 0.05, real_stay_closed=2), p)
        self.assertEqual(band, "bunt")
        self.assertIn("not a demotion", why)
        self.assertEqual(allocator.target_band(ev(rung=2, e=line - 0.05, real_stay_closed=3), p)[0], "paper")
        # The stay drawdown always applies, trial or not.
        self.assertEqual(allocator.target_band(ev(rung=2, e=line - 0.05, real_stay_closed=0, real_drawdown=0.35), p)[0], "paper")
        self.assertEqual(allocator.target_band(ev(rung=2, e=1.0, real_stay_closed=0, real_drawdown=0.36), p)[0], "paper")
        # A swing in its trial below the bunt line is cut to a bunt at once (the swing floor), not sent off real money.
        self.assertEqual(allocator.target_band(ev(rung=3, e=line - 0.05, w_real=0.8, real_stay_closed=0), p)[0], "bunt")
        self.assertEqual(allocator.target_band(ev(rung=3, e=line - 0.05, w_real=0.8, real_stay_closed=3), p)[0], "paper")
        with patch.dict(CONSTITUTION["allocator"], {"hysteresis_after_settled": 0}):  # the old rule, by the key
            self.assertEqual(allocator.target_band(ev(rung=2, e=line - 0.05, real_stay_closed=0), P())[0], "paper")

    def test_huang_l23cdb7s_loss_on_a_probe(self):
        """-$8.51 in 90 minutes on a $30 stake (Sept 23, 2026): W_real 0.716, E under the line on one
        settlement. On a probe it keeps its seat; the stay drawdown (28%) is under 35%."""
        p = P()
        w_real = (30 - 8.51) / 30
        band, _ = allocator.target_band(ev(rung=2, e=1.02 * w_real, w_real=w_real, real_drawdown=1 - w_real,
                                           real_stay_closed=1, real_trades=1), p)
        self.assertEqual(band, "bunt")


class EventPositions(unittest.TestCase):
    """P2: on the event books a real position is at most `position_share_event` of the stake."""

    def test_the_limits(self):
        self.assertEqual(allocator.limits_for(D("30"), "kalshi"), (D("6.00"), D("6.00")))   # a $30 bunt
        self.assertEqual(allocator.limits_for(D("10"), "kalshi"), (D("2.00"), D("2.00")))   # a $10 probe
        self.assertEqual(allocator.limits_for(D("5"), "kalshi"), (D("1.20"), D("1.20")))    # never under the $1 minimum x 1.2
        self.assertEqual(allocator.limits_for(D("400"), "kalshi"), (D("80.00"), D("75")))   # every order within the $75 cap
        self.assertEqual(allocator.limits_for(D("25"), "alpaca"), (D("12.50"), D("12.50")))  # Alpaca keeps its half
        with patch.dict(CONSTITUTION["allocator"], {"position_share_event": "0.5"}):
            self.assertEqual(allocator.limits_for(D("30"), "kalshi"), (D("15.00"), D("15.00")))


class TrialOnTheFloor(KalshiHouse):
    READY = ProbesAndBunts.READY

    def seated_probe(self):
        a = self.agent()
        with self.evidence_of({a.id: self.READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        return a

    def test_a_probe_that_loses_its_first_settlement_stays_and_the_exit_returns_after_three(self):
        a = self.seated_probe()
        line = P()["bunt_at"] * P()["hysteresis"]
        lost = dict(e=line - 0.1, w_paper=1.21, w_real=0.75, paper_trades=6, paper_settled=6, real_trades=1,
                    real_drawdown=0.25, real_stay_closed=1)
        with self.evidence_of({a.id: lost}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertEqual(self.house.books["kalshi"].limits[a.id].max_position_usd, D("2.00"))  # a fifth of $10
        with self.evidence_of({a.id: dict(lost, real_trades=3, real_stay_closed=3)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)

    def test_the_stay_drawdown_still_demotes_at_once(self):
        a = self.seated_probe()
        with self.evidence_of({a.id: dict(self.READY, e=0.9, w_real=0.64, real_drawdown=0.36, real_stay_closed=0)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        demote = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual((demote["band_from"], demote["band_to"]), ("probe", "paper"))

    def test_the_stays_real_results_are_counted_once_an_event(self):
        a = self.seated_probe()
        for ticker in ("KXMLBTOTAL-26SEP231840MILPHI-7", "KXMLBTOTAL-26SEP231840MILPHI-8", "KXHIGHNY-26SEP24-B72.5"):
            self.house.ledger.append("book.settle", {"book": "kalshi", "pnl": "0.10", "cost": "1", "payout": "1", "quantity": "1",
                                                     "instrument": LedgerCase.inst(ticker, venue="kalshi")}, agent=a.id)
        row = allocator.evidence(self.house, self.house.registry.get(a.id))
        self.assertEqual((row.real_stay_closed, row.real_trades), (2, 2))
        self.assertEqual(row.row()["stay_closed"], 2)

    def test_the_trial_counts_this_stays_real_results_not_a_past_stays(self):
        """P2: the exit waits for real results IN THE CURRENT STAY. Review of #224: counting every real
        result the agent ever had passed every other test; an agent back on real money after a stay
        with three real settlements would have no trial at all."""
        a = self.seated_probe()
        for ticker in ("KXHIGHNY-26SEP24-B72.5", "KXHIGHCHI-26SEP24-B70.5", "KXHIGHMIA-26SEP24-B88.5"):
            self.house.ledger.append("book.settle", {"book": "kalshi", "pnl": "0.10", "cost": "1", "payout": "1", "quantity": "1",
                                                     "instrument": LedgerCase.inst(ticker, venue="kalshi")}, agent=a.id)
        agent = self.house.registry.get(a.id)
        self.assertEqual(allocator.evidence(self.house, agent).real_stay_closed, 3)
        self.house.evaluator.demote(a.id, "test: back to practice")
        self.house.evaluator.promote(a.id, 2, "test: a new stay on real money")
        row = allocator.evidence(self.house, agent)
        self.assertEqual((row.real_trades, row.real_stay_closed), (3, 0))

    def test_a_swing_of_an_unproven_family_drops_to_a_probe(self):
        a = self.seated_probe()
        self.house.evaluator.promote(a.id, 3, "test: a swing")
        line = P()["swing_at"] * P()["hysteresis"]
        with self.evidence_of({a.id: dict(self.READY, e=line - 0.01, w_real=1.0, real_trades=8, real_stay_closed=8)}):
            self.house.allocator.rebalance()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        demote = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual((demote["band_from"], demote["band_to"]), ("swing", "probe"))

    def test_a_probe_that_swings_is_on_the_tape_as_a_probe(self):
        """Review of #224 (Sept 24, 2026): the move up from a probe says "probe", as the board and the
        move down say it; it had said "bunt -> swing" for an agent staked and shown as a probe."""
        a = self.seated_probe()
        ready = dict(self.READY, e=1.30, w_paper=1.21, w_real=1.1, real_trades=8, real_stay_closed=8)
        with patch.object(allocator, "audit_standing", return_value="approved"), self.evidence_of({a.id: ready}):
            summary = self.house.allocator.rebalance()
        self.assertEqual(self.house.evaluator.rung(a.id), 3)
        promote = self.promote_row(a)
        self.assertEqual((promote["band_from"], promote["band_to"]), ("probe", "swing"))
        self.assertEqual([(m["from"], m["to"]) for m in summary["moves"] if m["agent"] == a.id], [("probe", "swing")])

    def test_a_probe_whose_stake_could_not_be_lent_is_named_a_probe(self):
        """Review of #224: a probe whose stake does not land goes straight back, and the tape and the
        alert say a probe went back, not a bunt."""
        from league.book import Book, BookError

        a = self.agent()
        stake = Book.stake

        def refuse(book, agent, usd, *args, **kwargs):
            if book.real_money and agent == a.id:
                raise BookError("test: the venue refused the loan")
            return stake(book, agent, usd, *args, **kwargs)

        with patch.object(Book, "stake", refuse), self.evidence_of({a.id: self.READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        demote = [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual((demote["band_from"], demote["band_to"]), ("probe", "paper"))
        self.assertIn("probe's stake could not be lent", demote["reason"])
        alerts = [e.payload.get("message") or e.payload.get("text") or str(e.payload) for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertTrue(any("$10 probe could not be staked" in m for m in alerts), alerts[-3:])

    def test_the_throttle_never_halves_a_probe_under_a_tradable_stake(self):
        a = self.agent()
        alloc = self.house.allocator
        alloc.state["throttle"] = True
        # A position is a fifth of the stake and must hold the $1 minimum x 1.2: $6 is the smallest stake
        # that can trade, so a $10 probe is halved to $6, not $5.
        self.assertEqual(alloc.target_stake(a, "bunt"), D("6.00"))


class RulesText(unittest.TestCase):
    """What every agent reads (`league/rules.py`), in the copy rule's word: practice."""

    def test_the_agents_are_told_probes_proof_events_and_the_trial(self):
        import json
        from league.rules import rules_text

        with open("league/game.json") as f:
            game = json.load(f)
        text = rules_text(game)
        self.assertIn("Real money starts as a PROBE ($10 at Kalshi, $25 at", text)
        self.assertIn("unless your family's pooled record is PROVEN; then it is a BUNT ($30 / $25)", text)
        self.assertIn("10 or more independent", text)
        self.assertIn("practice at 0.5 weight", text)
        self.assertIn("ONCE PER EVENT: strikes stacked on one game are one", text)
        self.assertIn("ONE EARLY LOSS IS NOT A DEMOTION", text)
        self.assertIn("a position up to 20% of the stake on Kalshi, 50% at", text)
        without = {**CONSTITUTION, "allocator": {k: v for k, v in CONSTITUTION["allocator"].items() if k != "probe_bunt_usd"}}
        self.assertNotIn("PROBE (", rules_text(game, without))
