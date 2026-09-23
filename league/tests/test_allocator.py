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

from league import allocator, seeds
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
        # The learn-and-unblock run's rows (Sept 23, 2026 ~16:00 UTC), inside its table's bounds.
        self.assertIn(r["bunt_daily_loss"], ("book", "stay_drawdown"))
        self.assertIn(r["real_halt"]["basis"], ("staked", "venue_grant_capital"))
        self.assertTrue(D("0.01") <= D(r["real_halt"]["pct"]) <= D("0.08"))
        self.assertIn(r["bunt_growth"], ("flat", "w_real"))
        self.assertTrue(D("40") <= D(r["option_bunt_usd"]) <= D("80"))

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
        """The swing stake is `bunt_usd x E^kappa`; kappa is 2 since the learn-and-unblock run (Sept 23,
        2026 ~17:00 UTC), so winners compound in the square of their evidence, under the venue's 60%."""
        p = P()
        capital = D("500")
        self.assertEqual(p["kappa"], 2.0)
        self.assertEqual(swing_stake(ev(e=1.5), capital, p), D("56.25"))  # 25 x 1.5^2
        self.assertEqual(swing_stake(ev(e=2.0), capital, p), D("100.00"))  # 25 x 4
        self.assertEqual(swing_stake(ev(e=4.0), capital, p), D("300.00"))  # 25 x 16 = 400, capped at 0.6 of $500
        self.assertEqual(swing_stake(ev(e=3.0), D("1000"), p), D("225.00"))  # 25 x 9
        self.assertEqual(swing_stake(ev(e=100.0), D("100000"), p), D("10000.00"))  # e_cap 20: 25 x 400
        self.assertEqual(swing_stake(ev(e=100.0), capital, p), D("300.00"))  # 0.6 of $500
        self.assertEqual(swing_stake(ev(e=100.0), D("100"), p), D("60.00"))
        self.assertEqual(swing_stake(ev(venue="kalshi", e=3.0), capital, p), D("270.00"))  # 30 x 9
        self.assertEqual(swing_stake(ev(e=0.5), capital, p), D("25"))  # never under the bunt
        with patch.dict(CONSTITUTION["allocator"], {"kappa": 1.0}):  # the old rule, by the key
            self.assertEqual(swing_stake(ev(e=4.0), capital, P()), D("100.00"))

    def test_limits_follow_the_stake_and_never_fall_under_the_venue_minimum(self):
        self.assertEqual(limits_for(D("15"), "alpaca"), (D("12.00"), D("12.00")))  # $10 minimum + a fifth
        self.assertEqual(limits_for(D("25"), "alpaca"), (D("12.50"), D("12.50")))
        self.assertEqual(limits_for(D("100"), "alpaca"), (D("50.00"), D("50.00")))
        # Exits are sliced (PR #164): the position follows the stake; every Alpaca order stays within
        # the gateway's $75 on its own pricing (a market order at the ask x 1.10).
        self.assertEqual(limits_for(D("400"), "alpaca"), (D("200.00"), D("68.18")))
        self.assertEqual(limits_for(D("400"), "kalshi"), (D("200.00"), D("75")))
        with patch.object(allocator, "EXITS_SLICED", False):
            self.assertEqual(limits_for(D("400"), "alpaca"), (D("54.54"), D("54.54")))  # one order closes it
        self.assertEqual(limits_for(D("10"), "kalshi"), (D("5.00"), D("5.00")))
        self.assertEqual(limits_for(D("30"), "kalshi"), (D("15.00"), D("15.00")))  # the Kalshi bunt since Sept 23, 2026 ~17:00 UTC


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
            row = dict(table[agent.id])
            if "cooling" not in row:  # the real cooldown, as `allocator.evidence` computes it
                left = allocator.left_real_at(house, agent.id)
                row["cooling"] = rung in (1, 2) and left is not None and house.clock() - left < 3600
            return ev(agent=agent.id, venue=agent.venue, rung=rung, **row)
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
            self.assertAlmostEqual(float(house.books["alpaca"].equity(a.id)), 100.0, delta=0.5)  # 25 x E 2.0 ^ kappa 2
            sizes = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "size"]
            self.assertTrue(sizes and sizes[-1]["band"] == "swing")
            # Evidence doubles: the stake quadruples (kappa 2), to the venue's 60% and the envelope.
            table[a.id] = dict(e=4.0, w_paper=1.21, w_real=3.6, paper_trades=6, real_trades=12)
            with self.evidence_of(table):
                self.tick()
            self.assertAlmostEqual(float(house.books["alpaca"].equity(a.id)), 300.0, delta=0.5)  # 25 x 16 = 400, capped at 0.6 of $500; the stake targets equity
            staked_now = house.books["alpaca"].account(a.id).staked
            self.assertEqual(house.books["alpaca"].limits[a.id].max_position_usd, (max(staked_now, D("100")) / 2).quantize(D("0.01"), rounding="ROUND_DOWN"))
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
            # Halved to $12.50, but never under the smallest stake that can trade Alpaca crypto
            # ($10 minimum x 1.2 / a half-stake position = $24).
            self.assertEqual(alloc.target_stake(a, "bunt"), D("24.00"))
            swing = alloc.target_stake(a, "swing", ev(venue="alpaca", e=4.0))
            self.assertEqual(swing, D("24.00"))  # 30 (0.6 of $50) halved to 15, floored at 24
            with patch.dict(CONSTITUTION["allocator"]["bunt_usd"], {"alpaca": "60"}):
                self.assertEqual(alloc.target_stake(a, "bunt"), D("30.00"))  # a stake above the floor is halved
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
        self.assertEqual(grant["stake_usd"], "25")  # the smallest bunt (Alpaca; Kalshi is $30 since Sept 23, 2026 ~17:00 UTC)
        self.assertEqual(grant["max_agents"], 40)  # floor($1,017.75 / $25)
        with patch.dict(CONSTITUTION["allocator"], {"enabled": False}):
            old = policy({"kalshi": "517.75", "alpaca": "500"})
            self.assertNotEqual(old["constitution_digest"], grant["constitution_digest"])
            self.assertEqual(old["max_agents"], 16)
        self.assertFalse(_grant_matches(old, grant))  # a grant under the old rules is inactive...
        self.assertTrue(_grant_matches(grant, policy({"kalshi": "517.75", "alpaca": "500"})))  # ...until ratified


if __name__ == "__main__":
    unittest.main()


class ReviewRegressions(unittest.TestCase):
    """The Sept 23, 2026 adversarial review of the allocator, each defect as a test."""

    def setUp(self):
        from league.evaluator import Evaluator

        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.ev = Evaluator(self.ledger, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def mark(self, equity, book="alpaca", agent="a", holdings=0):
        self.ledger.append("book.mark", {"book": book, "equity": str(equity), "cash": str(equity), "holdings": holdings}, agent=agent)

    def stake(self, usd, book="alpaca", agent="a"):
        self.ledger.append("book.stake", {"book": book, "usd": str(usd), "note": "t", "real_money": book == "alpaca"}, agent=agent)

    def test_a_withdrawal_inside_the_first_funded_block_is_a_flow_not_a_smaller_start(self):
        self.mark(0)
        self.stake(25)
        self.mark(30)
        self.stake(-12.5)
        self.mark(17.5)
        self.assertAlmostEqual(self.ev.wealth("a", "alpaca")["log"], math.log(1.2), places=6)

    def test_a_loss_then_a_sweep_in_the_first_block_is_that_loss_not_ruin(self):
        self.mark(0)
        self.stake(25)
        self.mark(18)
        self.stake(-18)
        self.mark(0)
        self.assertAlmostEqual(self.ev.wealth("a", "alpaca")["log"], math.log(0.72), places=6)

    def test_a_re_seated_account_shows_its_new_loss_before_its_first_block_ends(self):
        # Stay 1: staked, flat, swept; its zero-equity block finishes; stay 2 then loses 30%.
        self.stake(25)
        self.mark(25)
        self.clock.advance(3600)
        self.mark(25)
        self.stake(-25)
        self.mark(0)
        self.clock.advance(3600)
        self.mark(0)
        self.ev.observe("a", "alpaca", "hour")
        self.clock.advance(3600)
        self.mark(0)
        self.ev.observe("a", "alpaca", "hour")
        self.stake(25)
        self.mark(17.5)
        w = self.ev.wealth("a", "alpaca")
        self.assertAlmostEqual(w["log"], math.log(0.7), places=6)
        self.assertAlmostEqual(w["drawdown"], 0.3, places=6)

    def test_the_demotion_drawdown_is_the_current_stays(self):
        self.stake(25)
        self.mark(25)
        for equity in (45, 40):  # stay 1 peaks at 1.8x and gives some back
            self.clock.advance(3600)
            self.mark(equity)
        self.clock.advance(3600)
        self.mark(40)
        self.ev.observe("a", "alpaca", "hour")
        head = self.ledger.head()[0]
        self.clock.advance(3600)
        self.mark(29)  # the new stay begins at 40 and has lost 27.5% of it... from its own start
        whole = self.ev.wealth("a", "alpaca")
        stay = self.ev.wealth("a", "alpaca", drawdown_since=head)
        self.assertGreater(whole["drawdown"], 0.35)
        self.assertAlmostEqual(stay["drawdown"], 1 - 29 / 40, places=6)

    def test_counts_survive_a_net_stake_at_or_below_zero_and_settlements_respect_the_cutoff(self):
        house = SimpleNamespace(ledger=self.ledger)
        self.stake(200, book="alpaca-paper")
        for _ in range(3):
            self.ledger.append("book.fill", {"book": "alpaca-paper", "realized": "40", "flat": True, "source": "venue",
                                             "side": "sell", "quantity": "1", "price": "40"}, agent="a")
        self.stake(-330, book="alpaca-paper")  # swept with its profit: the net stake is now negative
        self.assertEqual(allocator.closed_trades(house, "a", "alpaca-paper"), (3, 0))
        for _ in range(4):
            self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1"}, agent="a")
        self.ledger.append("book.fill_correction", {"book": "kalshi-shadow", "cash_delta": "0", "fees_delta": "0",
                                                    "realized_delta": "0", "holding_cost_deltas": {}}, agent="a")
        self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1"}, agent="a")
        self.assertEqual(allocator.closed_trades(house, "a", "kalshi-shadow"), (1, 1))  # only after the cutoff

    def test_the_haircut_survives_a_cutoff_and_each_stay_pays_its_own(self):
        house = SimpleNamespace(ledger=self.ledger)
        fill = {"book": "alpaca-paper", "source": "venue", "side": "buy", "quantity": "1", "price": "80"}
        self.stake(200, book="alpaca-paper")
        self.ledger.append("book.fill", fill, agent="a")
        self.stake(-200, book="alpaca-paper")
        self.stake(200, book="alpaca-paper")
        self.ledger.append("book.fill", fill, agent="a")
        both = allocator._paper_haircut(house, "a", "alpaca-paper", 10)
        self.assertAlmostEqual(both, 2 * 80 * 10 / 10_000 / 200, places=12)
        self.ledger.append("book.fill_correction", {"book": "alpaca-paper", "cash_delta": "0", "fees_delta": "0",
                                                    "realized_delta": "0", "holding_cost_deltas": {}}, agent="a")
        self.ledger.append("book.fill", fill, agent="a")
        self.assertAlmostEqual(allocator._paper_haircut(house, "a", "alpaca-paper", 10), 80 * 10 / 10_000 / 200, places=12)


class NoFlapping(HouseCaseReal):
    def test_a_demoted_bunt_waits_out_the_cooldown_before_it_may_bunt_again(self):
        house = self.house
        a = self.agent()

        def fake(h, ag, rung=None):
            rung = h.evaluator.rung(ag.id) if rung is None else rung
            left = allocator.left_real_at(h, ag.id)
            cooling = rung == 1 and left is not None and h.clock() - left < 3600
            # A record that would flap: good enough for a bunt on paper, a loser on real money.
            return ev(agent=ag.id, venue=ag.venue, rung=rung, e=1.10 if rung == 1 else 0.70, w_paper=1.21,
                      w_real=1.0 if rung == 1 else 0.64, paper_trades=6, cooling=cooling)

        rungs = []
        with patch.object(allocator, "evidence", side_effect=fake):
            for _ in range(8):  # 40 minutes of mark passes
                self.tick()
                rungs.append(house.evaluator.rung(a.id))
            self.assertEqual(rungs[:2], [2, 1])
            self.assertTrue(all(r == 1 for r in rungs[1:]), rungs)
            self.clock.advance(3600)
            self.tick()
            self.assertEqual(house.evaluator.rung(a.id), 2)  # after the cooldown it may try again

    def test_real_evidence_persists_on_paper(self):
        house = self.house
        a = self.agent()
        real = house.books["alpaca"]
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 2)
        for _ in range(4):  # it buys on the real book (the strategy buys when flat, sells when it holds)
            self.tick()
            if real.account(a.id).holdings:
                break
        self.assertTrue(real.account(a.id).holdings)
        self.price *= 0.6
        self.tick()  # marked down: its real evidence falls, it is sent back to paper
        row = allocator.evidence(house, house.registry.get(a.id))
        self.assertEqual(house.evaluator.rung(a.id), 1)
        self.assertLess(row.w_real, 0.9)  # the loss is still in its evidence on paper


class Envelope(HouseCaseReal):
    def test_realized_profit_opens_room_once_and_held_profit_stays_at_risk(self):
        house, alloc = self.house, self.house.allocator
        with patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "100"}):
            a = self.agent()
            with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
                self.tick()
                for _ in range(8):  # it buys on one wake and sells on the next, into a rising price
                    self.price *= 1.03
                    self.tick()
            book = house.books["alpaca"]
            account = book.account(a.id)
            realized = alloc.realized("alpaca")
            self.assertGreater(realized, 0)
            held = sum((h.cost for h in account.holdings.values()), D(0))
            self.assertEqual(alloc.at_risk("alpaca"), max(account.cash, D(0)) + held)
            self.assertEqual(alloc.headroom("alpaca"), D("100") + realized - alloc.at_risk("alpaca"))
            # Whatever the allocator returned or kept, what can be lost never exceeds the capital.
            self.assertLessEqual(alloc.at_risk("alpaca"), alloc.capital("alpaca"))

    def test_a_stake_the_book_cannot_lend_promotes_nobody(self):
        house = self.house
        agents = [self.agent(f"s{i}", code=IDLE) for i in range(3)]
        table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6) for a in agents}
        with patch.object(type(house.allocator), "can_fund", return_value=False), self.evidence_of(table):
            self.tick()
        self.assertTrue(all(house.evaluator.rung(a.id) == 1 for a in agents))
        self.assertEqual(house._state["promotion_status"][agents[0].id]["stage"], "venue_cash")

    def test_a_stake_that_fails_on_the_book_sends_the_agent_straight_back(self):
        from league.book import Book, BookError

        house = self.house
        a = self.agent(code=IDLE)
        real = house.books["alpaca"]
        original = Book.stake

        def refuse(book, agent, usd, *, note=""):
            if book is real and float(usd) > 0:
                raise BookError("the venue's cash moved")
            return original(book, agent, usd, note=note)

        with patch.object(Book, "stake", refuse), self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 1)
        self.assertLessEqual(house.allocator.at_risk("alpaca"), house.allocator.capital("alpaca"))


class LifecycleRegressions(HouseCaseReal):
    def test_the_swing_audit_reads_the_real_record_and_a_known_defect_bunt_the_paper_one(self):
        self.assertEqual(allocator._verdict("a", 2, "why", ev(venue="kalshi")).numbers["book"], "kalshi")
        self.assertEqual(allocator._verdict("a", 1, "why", ev(venue="alpaca")).numbers["book"], "alpaca-paper")

    def test_a_veto_holds_a_bunt_through_its_cooldown(self):
        house = self.house
        a = self.agent(code=IDLE)
        house.ledger.append("audit.verdict", {"approve": False, "summary": "look-ahead in the entry"}, agent=a.id)
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 1)
        self.assertEqual(house._state["promotion_status"][a.id]["stage"], "audit_cooldown")

    def test_an_approval_of_older_code_does_not_skip_the_swing_audit(self):
        house = self.house
        a = self.agent(code=IDLE)
        house.ledger.append("audit.verdict", {"approve": True, "summary": "old code"}, agent=a.id)
        self.assertEqual(allocator.audit_standing(house, a), "approved")
        house.ledger.append("agent.strategy", {"code_sha256": "new", "generation": 2}, agent=a.id)
        self.assertEqual(allocator.audit_standing(house, a), "none")
        house.ledger.append("audit.verdict", {"approve": False, "error": "HTTP 502"}, agent=a.id)
        self.assertEqual(allocator.audit_standing(house, a), "none")  # an error is not a verdict

    def test_a_drifting_swing_keeps_its_positions_and_is_not_swung_again_at_once(self):
        house = self.house
        with patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"}):
            a = self.agent()
            table = {a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}
            with self.evidence_of(table):
                self.tick()
            table[a.id] = dict(e=3.0, w_paper=1.21, w_real=2.7, paper_trades=6, real_trades=10)
            with self.evidence_of(table):
                for _ in range(4):
                    self.tick()
                    house.wait(5)
            self.assertEqual(house.evaluator.rung(a.id), 3)
            from league.evaluator import Verdict

            def drifted(agent_id, book, horizon="hour"):
                return house.evaluator.demote(agent_id, "test drift", {})
            submitted = len(self.real.submitted)
            with self.evidence_of(table), patch.object(house.evaluator, "drift", side_effect=drifted):
                self.tick()
            self.assertEqual(house.evaluator.rung(a.id), 2)
            forced = [o for o in self.real.submitted[submitted:] if "closing this account" in (o.rationale or "")]
            self.assertEqual(forced, [])  # no wind-down sale
            with self.evidence_of({a.id: {**table[a.id], "cooling": True}}):
                self.tick()
            self.assertEqual(house.evaluator.rung(a.id), 2)  # the cooldown keeps it a bunt


class BuntGrowth(HouseCaseReal):
    """U5 (Sept 23, 2026): a bunt keeps what it makes. Its target is `bunt_usd x clamp(W_real, 1,
    swing_at)`, so profit inside the envelope's headroom is not swept, and a bunt whose W_real is below
    1 is never topped back up. Losses still shrink by free cash only; the throttle, the stay drawdown
    and hysteresis are unchanged (`Mechanics` covers them)."""

    def bunted(self):
        a = self.agent()
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        book = self.house.books["alpaca"]
        self.assertEqual((self.house.evaluator.rung(a.id), book.account(a.id).staked), (2, D("25")))
        return a, book

    def sized(self, a, book, w_real, equity):
        """One sizing pass with the agent's real equity read as `equity`: the row the allocator wrote, or None."""
        real = book.equity
        with patch.object(book, "equity", side_effect=lambda agent: D(equity) if agent == a.id else real(agent)):
            return self.house.allocator._size(a, ev(agent=a.id, venue="alpaca", rung=2, w_real=w_real, e=w_real, real_trades=3), "bunt", P())

    def test_a_winning_bunt_keeps_its_profit_up_to_the_swing_line(self):
        a, book = self.bunted()
        self.assertIsNone(self.sized(a, book, 1.2, "30"))  # target $30: the $5 made is not swept
        self.assertEqual(book.account(a.id).staked, D("25"))
        with patch.dict(CONSTITUTION["allocator"], {"bunt_growth": "flat"}):  # the old rule, by the key
            row = self.sized(a, book, 1.2, "30")
            self.assertEqual((row["stake_usd"], row["moved_usd"]), ("25", "-5.00"))
        self.assertEqual(book.account(a.id).staked, D("20"))
        row = self.sized(a, book, 1.2, "20")  # under its target after that sweep: the winner is lent back to it
        self.assertEqual((row["stake_usd"], row["moved_usd"]), ("30.00", "10.00"))
        self.assertEqual(book.account(a.id).staked, D("30"))
        row = self.sized(a, book, 1.8, "45")  # above `swing_at` (1.25) the target caps at 25 x 1.25 and the rest is swept
        self.assertEqual((row["stake_usd"], row["moved_usd"]), ("31.25", "-13.75"))
        self.assertEqual(book.account(a.id).staked, D("16.25"))

    def test_a_losing_bunt_is_not_refilled(self):
        a, book = self.bunted()
        self.assertIsNone(self.sized(a, book, 0.9, "22.50"))  # 11% under its $25: the flat rule would have topped it up
        self.assertEqual(book.account(a.id).staked, D("25"))
        self.assertEqual([e for e in self.house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "size"], [])

    def test_a_bunt_lent_less_than_todays_base_is_lent_up_to_it_once(self):
        """Deploy A raised the Kalshi base $10 -> $30 and `_size` lent nothing to a bunt under W_real 1, so
        a bunt seated at $10 before the raise stayed at $10 (meriwether-h2d625d on the 21:31Z board,
        W_real 0.9978, stake $10, target $30). It is lent up to the base, net of what it was lent."""
        a, book = self.bunted()
        with patch.dict(CONSTITUTION["allocator"]["bunt_usd"], {"alpaca": "40"}):  # the base raised under it
            row = self.sized(a, book, 0.9978, "24.95")
            self.assertEqual((row["stake_usd"], row["moved_usd"]), ("40", "15.00"))  # 40 - 25 lent, not 40 - 24.95
            self.assertEqual(book.account(a.id).staked, D("40"))
            self.assertIsNone(self.sized(a, book, 0.95, "36.00"))  # lent the base, down $4: not refilled

    def test_a_throttle_halved_bunt_is_restored_to_the_base_less_its_own_losses(self):
        """The #198 review, item 4: a bunt halved by the throttle stayed halved when it lifted."""
        a, book = self.bunted()
        alloc = self.house.allocator
        with patch.dict(CONSTITUTION["allocator"]["bunt_usd"], {"alpaca": "60"}), \
                patch.object(type(alloc), "headroom", return_value=D("1000")):  # the test House's $50 envelope aside
            self.sized(a, book, 0.95, "24")  # lent up to the $60 base
            self.assertEqual(book.account(a.id).staked, D("60"))
            alloc.state["throttle"] = True
            row = self.sized(a, book, 0.95, "59")  # $1 lost; the throttle halves the target to $30
            self.assertEqual((row["stake_usd"], row["moved_usd"]), ("30.00", "-29.00"))
            self.assertEqual(book.account(a.id).staked, D("31"))
            self.assertIsNone(self.sized(a, book, 0.95, "25"))  # $5 more lost under the throttle: not refilled
            alloc.state["throttle"] = False
            row = self.sized(a, book, 0.95, "25")
            self.assertEqual((row["stake_usd"], row["moved_usd"]), ("60", "29.00"))  # $54: the base less its $6 of losses
            self.assertEqual(book.account(a.id).staked, D("60"))

    def test_lending_up_to_the_base_stays_inside_the_envelope(self):
        a, book = self.bunted()
        alloc = self.house.allocator
        with patch.dict(CONSTITUTION["allocator"]["bunt_usd"], {"alpaca": "40"}), \
                patch.object(type(alloc), "headroom", return_value=D("6.50")):
            row = self.sized(a, book, 0.99, "25")
            self.assertEqual(row["moved_usd"], "6.50")  # 15 owed to the base, 6.50 of room
        self.assertEqual(book.account(a.id).staked, D("31.50"))

    def test_the_seat_the_limits_the_audit_packet_and_the_board_show_the_same_target(self):
        a, book = self.bunted()
        alloc = self.house.allocator
        evidence = ev(agent=a.id, venue="alpaca", rung=2, w_real=1.2, e=1.2, real_trades=3)
        alloc._evidence = {a.id: evidence}
        self.assertEqual(alloc.seat_stake(a), D("30.00"))
        self.assertEqual(alloc.limits(a, D("25")), limits_for(D("30"), "alpaca"))
        self.assertEqual(D(alloc.context(evidence, "bunt")["stake_usd"]), D("30"))
        with self.evidence_of({a.id: dict(e=1.2, w_paper=1.0, w_real=1.2, paper_trades=6, real_trades=3)}):
            alloc.rebalance()
        self.assertEqual(alloc.board()["agents"][a.id]["target_usd"], "30.00")
        self.assertEqual(alloc.target_stake(a, "bunt"), D("25"))  # no evidence in hand: the stake at seating

    def test_the_envelope_reserves_for_an_unfunded_seat_what_seat_will_lend(self):
        """Review of #198 (Sept 23, 2026): `at_risk` reserved the flat base for a seat not yet funded while
        `House.seat` lends `seat_stake` (base x W_real on a re-seat, a swing's stake on rung 3): $5 of a
        $30 re-seat was not reserved. The reservation is what the seat will lend."""
        a, book = self.bunted()
        alloc, house = self.house.allocator, self.house
        alloc._move_down(a, ev(agent=a.id, venue="alpaca", rung=2, e=0.5, w_real=1.2, real_trades=3), "paper", "test", {"moves": []})
        self.assertTrue(book.account(a.id).swept)
        alloc._evidence = {a.id: ev(agent=a.id, venue="alpaca", rung=2, e=1.1, w_real=1.2, real_trades=3)}
        house.evaluator.promote(a.id, 2, "test: seated, its stake not yet lent")
        others = alloc.at_risk("alpaca", exclude=a.id)
        self.assertEqual(alloc.seat_stake(a), D("30.00"))
        self.assertEqual(alloc.at_risk("alpaca") - others, D("30.00"))
        alloc._evidence = {a.id: ev(agent=a.id, venue="alpaca", rung=2, e=1.1, w_real=0.8, real_trades=3)}
        self.assertEqual(alloc.at_risk("alpaca") - others, alloc.seat_stake(a))  # the base: a loser's re-seat is unchanged

    def test_an_options_bunt_is_staked_eighty_dollars_with_a_forty_dollar_contract_limit(self):
        """A2a (Sept 23, 2026): at $40 the book's 50% rules held a contract to $20; at $80 one $40 contract fits."""
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        alloc = self.house.allocator
        self.assertEqual(alloc.target_stake(agent, "bunt"), D("80"))
        self.assertEqual(limits_for(D("80"), "alpaca"), (D("40.00"), D("40.00")))
        limits = self.house._limits(2, agent)
        self.assertEqual((limits.max_position_usd, limits.max_order_usd, limits.asset_classes), (D("40.00"), D("40.00"), ("option",)))
        with patch.dict(CONSTITUTION["allocator"], {"option_bunt_usd": "40"}):
            self.assertEqual(alloc.target_stake(agent, "bunt"), D("40"))
        self.assertEqual(alloc.target_stake(self.agent(), "bunt"), D("25"))  # a stock bunt is unchanged
