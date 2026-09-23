"""Capital is the ladder (Sept 23, 2026): evidence as wealth, bands, stakes, death and the fee.

The pure rules are tested directly; the House's mechanics (seating a bunt on the real book, sizing
a swing, sending a loser back to paper, the envelope, the throttle) run in a House with a fake
real venue, with the evidence either driven by a real strategy on a price path or set by the test.
"""

import json
import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator
from league.allocator import Evidence, limits_for, swing_stake, target_band
from league.constitution import CONSTITUTION, money_digest
from league.economy import Economy, load_game
from league.house import House, Settings
from league.ledger import Ledger, now_iso
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_house import BUYER, FakeAlpacaData, HouseCase
from league.tests.test_ladder import LADDER, FakeAuditor, InProcessSandbox
from league.venues import instrument_for

D = Decimal
P = allocator._params

IDLE = LADDER.replace("ladder-test", "idle-test").replace('''def decide(ctx):''', '''def decide(ctx):
    return {"intents": [], "thought": "waiting"}


def _unused(ctx):''')


def ev(**kw):
    base = dict(agent="a", venue="alpaca", rung=1, w_paper=1.0, w_real=1.0, e=1.0, paper_trades=0, paper_settled=0,
                real_trades=0, real_pnl=0.0, real_drawdown=0.0, haircut_log=0.0, real_seen=False)
    base.update(kw)
    return Evidence(**base)


class Rules(unittest.TestCase):
    def test_the_constitution_carries_every_parameter_of_the_plan_within_its_bounds(self):
        r = CONSTITUTION["allocator"]
        self.assertTrue(r["enabled"])
        self.assertTrue(0.25 <= r["evidence"]["paper_weight"] <= 1)
        self.assertTrue(0 <= r["evidence"]["alpaca_paper_haircut_bps"] <= 50)
        self.assertTrue(1.0 <= r["bunt_at"] <= 1.25 and 3 <= r["bunt_min_trades"] <= 20)
        self.assertTrue(1.2 <= r["swing_at"] <= 3 and 5 <= r["swing_min_real_trades"] <= 30)
        self.assertTrue(0.5 <= r["kappa"] <= 2 and 5 <= r["e_cap"] <= 50)
        self.assertTrue(r["max_share_of_venue"] <= 0.8 and 0.25 <= r["position_share"] <= 1)
        self.assertTrue(1 <= r["stars"] <= 10 and 0.7 <= r["hysteresis"] <= 0.95)
        self.assertTrue(0.2 <= r["real_drawdown_demote"] <= 0.5 and 0.6 <= r["die_below"] <= 0.95)
        self.assertTrue(0.05 <= r["performance_fee_share"] <= 0.5)
        for venue, usd in r["bunt_usd"].items():
            self.assertGreaterEqual(D(usd), D(r["venue_minimum_usd"][venue]))
            self.assertLessEqual(D(usd), D("60"))

    def test_bunt_needs_evidence_and_trades_or_settlements_on_an_event_book(self):
        p = P()
        self.assertEqual(target_band(ev(e=1.10, paper_trades=5), p)[0], "bunt")
        self.assertEqual(target_band(ev(e=1.10, paper_trades=4), p)[0], "paper")
        self.assertEqual(target_band(ev(e=p["bunt_at"] - 0.001, paper_trades=50), p)[0], "paper")
        self.assertEqual(target_band(ev(venue="kalshi", e=1.10, paper_trades=2, paper_settled=3), p)[0], "bunt")
        self.assertEqual(target_band(ev(venue="alpaca", e=1.10, paper_trades=2, paper_settled=3), p)[0], "paper")

    def test_bands_cross_both_ways_with_hysteresis(self):
        p = P()
        line = p["bunt_at"] * p["hysteresis"]
        self.assertEqual(target_band(ev(rung=2, e=line + 0.001), p)[0], "bunt")  # below entry, above exit: stays
        self.assertEqual(target_band(ev(rung=2, e=line - 0.001), p)[0], "paper")
        self.assertEqual(target_band(ev(rung=2, e=1.6, w_real=1.1, real_trades=8), p)[0], "swing")
        self.assertEqual(target_band(ev(rung=2, e=1.6, w_real=0.99, real_trades=8), p)[0], "bunt")
        self.assertEqual(target_band(ev(rung=2, e=1.6, w_real=1.1, real_trades=7), p)[0], "bunt")
        swing_exit = p["swing_at"] * p["hysteresis"]
        self.assertEqual(target_band(ev(rung=3, e=swing_exit + 0.01, w_real=0.95), p)[0], "swing")
        self.assertEqual(target_band(ev(rung=3, e=swing_exit - 0.01, w_real=1.0), p)[0], "bunt")
        self.assertEqual(target_band(ev(rung=3, e=2.0, w_real=0.89), p)[0], "bunt")
        self.assertEqual(target_band(ev(rung=3, e=0.5, w_real=0.5), p)[0], "paper")

    def test_a_real_drawdown_sends_a_bunt_or_a_swing_back_to_paper_at_once(self):
        p = P()
        self.assertEqual(target_band(ev(rung=2, e=1.2, real_drawdown=0.36), p)[0], "paper")
        self.assertEqual(target_band(ev(rung=3, e=3.0, w_real=2.0, real_trades=20, real_drawdown=0.35), p)[0], "paper")
        self.assertEqual(target_band(ev(rung=3, e=3.0, w_real=2.0, real_trades=20, real_drawdown=0.34), p)[0], "swing")

    def test_swing_stakes_scale_with_evidence_and_stop_at_the_caps(self):
        p = P()
        capital = D("500")
        self.assertEqual(swing_stake(ev(e=1.5), capital, p), D("37.50"))  # 25 x 1.5
        self.assertEqual(swing_stake(ev(e=4.0), capital, p), D("100.00"))
        self.assertEqual(swing_stake(ev(e=11.9), D("1000"), p), D("297.50"))
        self.assertEqual(swing_stake(ev(e=100.0), D("10000"), p), D("500.00"))  # e_cap 20
        self.assertEqual(swing_stake(ev(e=100.0), capital, p), D("300.00"))  # 0.6 of $500
        self.assertEqual(swing_stake(ev(e=100.0), D("100"), p), D("60.00"))
        self.assertEqual(swing_stake(ev(venue="kalshi", e=3.0), capital, p), D("30.00"))
        self.assertEqual(swing_stake(ev(e=0.5), capital, p), D("25"))  # never under the bunt

    def test_limits_follow_the_stake_and_never_fall_under_the_venue_minimum(self):
        self.assertEqual(limits_for(D("15"), "alpaca"), (D("12.00"), D("12.00")))  # $10 minimum + a fifth
        self.assertEqual(limits_for(D("25"), "alpaca"), (D("12.50"), D("12.50")))
        self.assertEqual(limits_for(D("100"), "alpaca"), (D("50.00"), D("50.00")))
        self.assertEqual(limits_for(D("400"), "alpaca"), (D("200.00"), D("75")))  # every order within the gateway's cap
        self.assertEqual(limits_for(D("10"), "kalshi"), (D("5.00"), D("5.00")))


class EvidenceOnTheBooks(HouseCase):
    """W from the books themselves: stakes are not profit, the block in progress counts, and Alpaca's
    paper fills are haircut."""

    def test_wealth_excludes_flows_and_counts_the_block_in_progress(self):
        agent = self.seated()
        book = self.house.books["alpaca-paper"]
        self.house.tick()
        self.clock.advance(60)
        self.house.tick()
        before = self.house.evaluator.wealth(agent.id, "alpaca-paper", agent.horizon)
        book.stake(agent.id, "300", note="more money is not more evidence")
        book.mark()
        after = self.house.evaluator.wealth(agent.id, "alpaca-paper", agent.horizon)
        self.assertAlmostEqual(before["log"], after["log"], places=6)
        # The price doubles while it holds: the block in progress shows it before any block finishes.
        held = book.account(agent.id).holdings
        if held:
            self.broker.set_quote(self.btc, "159990", "160010")
            book.mark()
            rising = self.house.evaluator.wealth(agent.id, "alpaca-paper", agent.horizon)
            self.assertGreater(rising["log"], after["log"])
            self.assertEqual(rising["blocks"], 0)
            frozen = self.house.evaluator.wealth(agent.id, "alpaca-paper", agent.horizon, current=False)
            self.assertEqual(frozen["log"], 0.0)

    def test_the_haircut_is_taken_on_alpaca_paper_only(self):
        agent = self.seated()
        for _ in range(4):
            self.house.tick()
            self.clock.advance(300)
        fills = [e for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload.get("source") == "venue"]
        self.assertTrue(fills)
        cut = allocator._paper_haircut(self.house, agent.id, "alpaca-paper", 10)
        notional = sum(float(e.payload["quantity"]) * float(e.payload["price"]) for e in fills)
        self.assertAlmostEqual(cut, notional * 10 / 10_000 / 200.0, places=9)
        self.assertEqual(allocator._paper_haircut(self.house, agent.id, "kalshi-shadow", 10), 0.0)
        row = allocator.evidence(self.house, agent)
        raw = self.house.evaluator.wealth(agent.id, "alpaca-paper", agent.horizon)["log"]
        self.assertAlmostEqual(math.log(row.w_paper), raw - cut, places=9)


class HouseCaseReal(unittest.TestCase):
    """A House with a real (fake) Alpaca venue, sealed boxes and an auditor."""

    real_cash = "800"

    def setUp(self):
        strategies = patch('league.strategies.all_strategies', return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.paper, self.real = FakeBroker("alpaca-paper"), FakeBroker("alpaca", cash=self.real_cash)
        self.data = FakeAlpacaData()
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.auditor = FakeAuditor()
        self.house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.paper, "alpaca": self.real}, sandbox=InProcessSandbox(),
            alpaca_data=self.data, clock=self.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True),
            game=game, auditor=self.auditor)
        self.auditor.ledger = self.house.ledger
        self.price = 80000.0
        self.quote()

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def quote(self):
        for broker in (self.paper, self.real):
            broker.clock_iso = now_iso(self.clock)
            broker.set_quote(instrument_for(broker.venue, {"symbol": "BTC/USD"}), f"{self.price - 2:.2f}", f"{self.price + 2:.2f}")
        self.data.price = self.price

    def agent(self, name="climber", code=LADDER):
        agent = self.house.spawn(name, "alloc-test", code, reason="test", endowment="2.5")
        self.house.evaluator.seat(agent.id, 1, "test: straight to paper")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def tick(self, n=1, seconds=300):
        for _ in range(n):
            self.clock.advance(seconds)
            self.quote()
            self.house.tick()

    def evidence_of(self, table):
        """Patch the allocator's evidence to the test's table {agent_id: kwargs}."""
        real = allocator.evidence

        def fake(house, agent, rung=None):
            rung = house.evaluator.rung(agent.id) if rung is None else rung
            if agent.id not in table:
                return real(house, agent, rung)
            return ev(agent=agent.id, venue=agent.venue, rung=rung, **table[agent.id])
        return patch.object(allocator, "evidence", side_effect=fake)


class Mechanics(HouseCaseReal):
    def test_a_paper_agent_with_evidence_is_bunted_onto_real_money_and_a_loser_goes_back(self):
        house = self.house
        a = self.agent()
        table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 2)
        real = house.books["alpaca"]
        self.assertEqual(real.account(a.id).staked, D("25"))
        self.assertEqual(real.limits[a.id].max_position_usd, D("12.50"))
        self.assertTrue(house.books["alpaca-paper"].account(a.id).swept)
        promote = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "promote"][-1]
        self.assertEqual((promote["band_from"], promote["band_to"], promote["via"]), ("paper", "bunt", "allocator"))
        self.assertEqual(promote["stake_usd"], "25")
        self.assertEqual(house.allocator.board()["agents"][a.id]["band"], "bunt")
        # Its evidence falls below the bunt line with hysteresis: straight back to paper.
        table[a.id] = dict(e=0.80, w_paper=1.21, w_real=0.73, paper_trades=6, real_trades=2)
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 1)
        demote = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual((demote["band_from"], demote["band_to"]), ("bunt", "paper"))
        paper = house.books["alpaca-paper"].account(a.id)
        self.assertTrue(paper.funded and not paper.swept and paper.cash > D("199"))  # staked afresh on paper
        moves = house.allocator.board()["moves"]
        self.assertEqual([(m["from_band"], m["to_band"]) for m in moves if m["agent"] == a.id], [("paper", "bunt"), ("bunt", "paper")])

    def test_the_envelope_is_never_exceeded_and_the_best_evidence_is_seated_first(self):
        house = self.house
        # Without a grant the envelope is the constitution's tuition line ($75 here): three $25 bunts.
        tuition = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "75"})
        tuition.start()
        self.addCleanup(tuition.stop)
        agents = [self.agent(f"a{i}", code=IDLE) for i in range(5)]
        table = {a.id: dict(e=1.05 + 0.01 * i, w_paper=1.2, paper_trades=6) for i, a in enumerate(agents)}
        with self.evidence_of(table):
            self.tick()
        seated = sorted(a.id for a in agents if house.evaluator.rung(a.id) == 2)
        self.assertEqual(seated, sorted(a.id for a in agents[2:]))  # the three best E
        self.assertLessEqual(house.allocator.committed("alpaca"), house.allocator.capital("alpaca"))
        waiting = house._state["promotion_status"][agents[0].id]
        self.assertEqual(waiting["stage"], "envelope")
        # A newcomer with better evidence displaces the weakest FLAT bunt, one a pass.
        star = self.agent("star", code=IDLE)
        table[star.id] = dict(e=1.50, w_paper=2.0, paper_trades=9)
        for a in agents[2:]:
            table[a.id] = {**table[a.id], "w_real": 1.0}
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(house.evaluator.rung(star.id), 2)
        self.assertEqual(house.evaluator.rung(agents[2].id), 1)  # E 1.07, the weakest
        self.assertLessEqual(house.allocator.committed("alpaca"), house.allocator.capital("alpaca"))

    def test_the_first_swing_is_audited_and_its_stake_follows_the_evidence(self):
        house = self.house
        with patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"}):
            a = self.agent()
            table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}
            with self.evidence_of(table):
                self.tick()
            self.assertEqual(house.evaluator.rung(a.id), 2)
            table[a.id] = dict(e=2.0, w_paper=1.21, w_real=1.8, paper_trades=6, real_trades=9)
            with self.evidence_of(table):
                self.tick()
                house.wait(5)
                self.tick()
            self.assertIn(a.id, self.auditor.seen)
            self.assertEqual(house.evaluator.rung(a.id), 3)
            staked = house.books["alpaca"].account(a.id).staked
            self.assertAlmostEqual(float(house.books["alpaca"].equity(a.id)), 50.0, delta=0.5)  # 25 x E 2.0
            sizes = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "size"]
            self.assertTrue(sizes and sizes[-1]["band"] == "swing")
            # Evidence doubles: so does the stake (under the venue's 60% and the envelope).
            table[a.id] = dict(e=4.0, w_paper=1.21, w_real=3.6, paper_trades=6, real_trades=12)
            with self.evidence_of(table):
                self.tick()
            self.assertAlmostEqual(float(house.books["alpaca"].equity(a.id)), 100.0, delta=0.5)  # the stake targets equity
            self.assertEqual(house.books["alpaca"].limits[a.id].max_position_usd, (house.books["alpaca"].account(a.id).staked / 2).quantize(D("0.01"), rounding="ROUND_DOWN"))
            staked = house.books["alpaca"].account(a.id).staked
            # A small change is ignored.
            table[a.id] = dict(e=4.2, w_paper=1.21, w_real=3.8, paper_trades=6, real_trades=12)
            with self.evidence_of(table):
                self.tick()
            self.assertEqual(house.books["alpaca"].account(a.id).staked, staked)

    def test_shrinking_never_forces_a_sale(self):
        house = self.house
        with patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"}):
            a = self.agent()
            table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}
            with self.evidence_of(table):
                self.tick()
            table[a.id] = dict(e=4.0, w_paper=1.21, w_real=3.6, paper_trades=6, real_trades=12)
            self.auditor.approve = True
            with self.evidence_of(table):
                self.tick(3)
                house.wait(5)
                self.tick()
            book = house.books["alpaca"]
            self.assertEqual(house.evaluator.rung(a.id), 3)
            staked_before = book.account(a.id).staked
            holdings = {k: h.quantity for k, h in book.account(a.id).holdings.items()}
            # E falls inside the swing band's hysteresis: the target shrinks, only free cash returns.
            table[a.id] = dict(e=1.3, w_paper=1.21, w_real=1.2, paper_trades=6, real_trades=12)
            submitted = len(self.real.submitted)
            with self.evidence_of(table):
                house.allocator.rebalance()
            sells = [o for o in self.real.submitted[submitted:] if o.side == "sell"]
            self.assertEqual(sells, [])
            self.assertEqual({k: h.quantity for k, h in book.account(a.id).holdings.items()}, holdings)
            self.assertLessEqual(book.account(a.id).staked, staked_before)
            self.assertGreaterEqual(book.account(a.id).cash - book._reserved_cash(a.id), D(0))

    def test_the_floor_throttle_halves_stakes_and_restores_them(self):
        house = self.house
        alloc = house.allocator
        a = self.agent()
        self.assertEqual(alloc.target_stake(a, "bunt"), D("25"))
        with patch.object(type(alloc), "floor_pnl", return_value=D("-16")):  # -32% of the $50 line
            self.assertTrue(alloc._throttle())
            self.assertEqual(alloc.target_stake(a, "bunt"), D("12.50"))  # halved
            swing = alloc.target_stake(a, "swing", ev(venue="alpaca", e=4.0))
            self.assertEqual(swing, D("15.00"))  # 30 (0.6 of $50) halved
        with patch.object(type(alloc), "floor_pnl", return_value=D("-10")):  # -20%: still throttled
            self.assertTrue(alloc._throttle())
        with patch.object(type(alloc), "floor_pnl", return_value=D("-7")):  # -14%: restored
            self.assertFalse(alloc._throttle())
        rows = [e.payload for e in house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "allocator throttle"]
        self.assertEqual([r["active"] for r in rows], [True, False])

    def test_paper_wealth_death(self):
        house = self.house
        a, b = self.agent("loser"), self.agent("young")
        table = {a.id: dict(e=0.87, w_paper=0.76, paper_trades=11), b.id: dict(e=0.87, w_paper=0.76, paper_trades=9)}
        with self.evidence_of(table):
            self.tick()
        self.assertFalse(house.registry.get(a.id).alive)
        self.assertTrue(house.registry.get(b.id).alive)  # too few trades to judge
        died = house.ledger.last("agent.died", agent=a.id).payload
        self.assertEqual(died["cause"], "evidence")

    def test_the_old_ladder_does_not_promote_while_the_allocator_decides(self):
        house = self.house
        a = self.agent()
        # A screen pass is a hold now: nothing but the allocator moves a paper agent to money.
        from league.evaluator import Verdict

        with patch.object(house.evaluator, "judge", return_value=Verdict(a.id, 1, "eligible", "screen", {})):
            with self.evidence_of({a.id: dict(e=1.0, w_paper=1.0, paper_trades=0)}):
                self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 1)
        self.assertEqual(self.auditor.seen, [])


class EndToEnd(HouseCaseReal):
    """Real evidence from a real strategy on a price path: it earns on paper, is bunted, and trades
    real money within its bunt's limits."""

    def test_a_winning_strategy_earns_a_bunt_and_trades_real_money(self):
        house = self.house
        a = self.agent()
        step = 0
        bunted_at = None
        for _ in range(12 * 30):
            step += 1
            holds = any(book.account(a.id).holdings for book in house.books.values() if a.id in book.accounts)
            favourable = (step * 7) % 100 < 80
            if holds:
                self.price *= 1.02 if favourable else 0.985
            else:
                self.price *= 1 + (80000.0 / self.price - 1) * 0.5
            self.tick()
            if house.evaluator.rung(a.id) >= 2 and bunted_at is None:
                bunted_at = step
            if bunted_at and step > bunted_at + 24:
                break
        self.assertIsNotNone(bunted_at, "the paper record never crossed the bunt line")
        row = allocator.evidence(house, house.registry.get(a.id))
        fills = [e.payload for e in house.ledger.iter(kinds="book.fill", agent=a.id) if e.payload["book"] == "alpaca" and e.payload["source"] == "venue"]
        self.assertTrue(fills, "a bunt trades real money")
        limit = house.books["alpaca"].limits[a.id]
        self.assertTrue(all(D(f["quantity"]) * D(f["price"]) <= limit.max_order_usd + D("0.01") for f in fills))
        self.assertTrue(house.books["alpaca"].reconcile().ok)
        self.assertGreater(row.real_trades + len(fills), 0)


class PerformanceFee(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        game = load_game()
        self.economy = Economy(self.ledger, game, clock=self.clock)
        self.house = SimpleNamespace(ledger=self.ledger, economy=self.economy, _lifecycle_lock=__import__("threading").RLock())
        self.alloc = allocator.Allocator.__new__(allocator.Allocator)
        self.alloc.house = self.house
        self.alloc.state = {"fee_cursor": None}

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_twenty_percent_of_realized_real_profit_once_and_nothing_for_losses_or_paper(self):
        summary = {"fees": 0}
        self.alloc._pay_fees(P(), summary)  # arms the cursor: nothing before the allocator is back-paid
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "5.00"}, agent="w")
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "-3.00"}, agent="w")
        self.ledger.append("book.fill", {"book": "alpaca", "realized": "2.50", "source": "venue"}, agent="w")
        self.ledger.append("book.fill", {"book": "alpaca-paper", "realized": "9.00", "source": "venue"}, agent="w")
        self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "4.00"}, agent="w")
        self.alloc._pay_fees(P(), summary)
        self.assertEqual(self.economy.balance("w"), D("1.5"))  # 20% of 5.00 + 2.50
        self.alloc.state["fee_cursor"] = 1  # a replay from an old cursor pays nothing twice
        self.alloc._pay_fees(P(), summary)
        self.assertEqual(self.economy.balance("w"), D("1.5"))
        grants = [e for e in self.ledger.iter(kinds="credit.grant", agent="w")]
        self.assertEqual(len(grants), 2)
        self.assertTrue(all(g.id.startswith("perf:") for g in grants))


class GrantAndDigest(unittest.TestCase):
    def test_the_money_digest_changes_and_the_grant_needs_ratifying(self):
        from league.campaigns import CampaignBudget, _grant_matches
        from league.live_trading import policy

        grant = policy({"kalshi": "517.75", "alpaca": "500"})
        self.assertEqual(grant["constitution_digest"], money_digest())
        self.assertEqual(grant["stake_usd"], "10")  # the smallest bunt
        self.assertEqual(grant["max_agents"], 101)
        with patch.dict(CONSTITUTION["allocator"], {"enabled": False}):
            old = policy({"kalshi": "517.75", "alpaca": "500"})
            self.assertNotEqual(old["constitution_digest"], grant["constitution_digest"])
            self.assertEqual(old["max_agents"], 16)
        self.assertFalse(_grant_matches(old, grant))  # a grant under the old rules is inactive...
        self.assertTrue(_grant_matches(grant, policy({"kalshi": "517.75", "alpaca": "500"})))  # ...until ratified


if __name__ == "__main__":
    unittest.main()
