import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.book import Limits
from league.economy import load_game
from league.house import House, Settings, mutate
from league.ledger import now_iso
from league.sandbox import LocalSandbox
from league.tests.fakes import Clock, FakeBroker, old_ladder
from league.venues import instrument_for

D = Decimal

BUYER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-buyer", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {"notional": 20.0}

def decide(ctx):
    held = [p for p in ctx["positions"] if p["symbol"] == "BTC/USD"]
    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "take it off"}],
                "thought": "holding, so selling", "memory": {"sold": True}}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": ctx["params"]["notional"], "type": "market", "reason": "test buy"}],
            "thought": "flat, so buying", "memory": {"bought": True}}
'''

SELLER_FIRST = BUYER.replace("test-buyer", "test-other")


class FakeAlpacaData:
    def __init__(self):
        self.price = 80000.0

    def bars(self, symbols, timeframe, *, start=None, end=None, limit=120):
        return {s: [{"t": f"2026-09-10T00:{i:02d}:00Z", "o": self.price, "h": self.price, "l": self.price, "c": self.price, "v": 1.0} for i in range(0, 50, 5)] for s in symbols}

    def quotes(self, symbols):
        return {s: {"bid": self.price - 5, "ask": self.price + 5} for s in symbols}

    def tape(self, symbols, timeframe, *, start, end, horizon="hour", half_spread_bps=None, warmup_bars=0):
        steps = []
        for hour in range(60):
            for minute in range(0, 60, 5):
                # A sawtooth the test strategy profits from: it buys low on even bars and sells high on odd ones.
                price = 80000.0 * (1.0 + (0.01 if (minute // 5) % 2 else -0.01))
                steps.append({"t": f"2026-09-{10 + hour // 24:02d}T{hour % 24:02d}:{minute:02d}:00Z", "bars": {s: {"o": price, "h": price, "l": price, "c": price, "v": 1.0} for s in symbols}})
        return {"venue": "alpaca", "horizon": horizon, "step_seconds": 300, "half_spread_bps": 0.5, "steps": steps, "results": {}}


class HouseCase(unittest.TestCase):
    def setUp(self):
        # Each mechanics test supplies its own population. Shipping the first architect
        # strategy must not silently add a real strategy to every unrelated fake-book test.
        strategies = patch('league.strategies.all_strategies', return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.broker = FakeBroker("alpaca-paper")
        self.btc = instrument_for("alpaca-paper", {"symbol": "BTC/USD"})
        self.broker.set_quote(self.btc, "79995", "80005")
        self.data = FakeAlpacaData()
        self.house = self.new_house()

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def new_house(self, **kw):
        game = load_game()
        game["economy"]["min_population"] = 0  # these tests bring their own agents, not the seeds
        game["economy"]["newcomer_seconds"] = 10 ** 9  # and no newcomer joins unless a test asks for one
        kw.setdefault("game", game)
        return House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker, "alpaca": FakeBroker("alpaca", cash="500")},
            sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock,
            settings=Settings(mark_every_seconds=0, research=False), **kw,
        )

    def seated(self, name="buyer", code=BUYER):
        agent = self.house.spawn(name, "test-family", code, reason="a test agent")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent


class Lessons(HouseCase):
    """Sept 23, 2026: corrected lessons never reached the ledger (loaded once by title), and an agent
    declined a replay over a threshold that had been removed an hour before."""

    def test_a_lesson_is_loaded_once_and_again_when_its_text_changes(self):
        import league.house as house_module

        folder = Path(self.dir.name) / "league"
        (folder / "playbook").mkdir(parents=True)
        lesson = folder / "playbook" / "2026-09-23-a-lesson.md"
        lesson.write_text("# A lesson\n\nThe bar is 20 trades.\n", encoding="utf-8")
        with patch.object(house_module, "__file__", str(folder / "house.py")):
            self.assertEqual(self.house.learn(), 1)
            self.assertEqual(self.house.learn(), 0)
            lesson.write_text("# A lesson\n\nThe bar is 10 trades.\n", encoding="utf-8")
            self.assertEqual(self.house.learn(), 1)
        latest = self.house.commons.playbook_read("lesson")["entries"][-1]
        self.assertIn("10 trades", latest["text"])

    def test_the_current_rules_lesson_matches_the_constitution(self):
        from league.constitution import CONSTITUTION

        text = (Path(__file__).resolve().parents[1] / "playbook" / "2026-09-23-the-ladder-as-it-stands.md").read_text(encoding="utf-8")
        replay, paper = CONSTITUTION["ladder"]["replay"], CONSTITUTION["ladder"]["paper"]
        self.assertIn(f"**{replay['min_trades']} closed trades**", text)
        self.assertIn(f"**{paper['min_active_blocks']} active hourly blocks**", text)
        self.assertIn(f"**{paper['min_active_blocks_day']} finished active day", text)
        self.assertIn(f"above {replay['min_oos_growth']:+.2%} a block", text)
        self.assertIn(f"under **{paper['max_drawdown']:.0%}**", text)
        self.assertEqual(replay["min_deflated_sharpe"], 0.0)
        self.assertIn("No deflated-Sharpe minimum", text)
        self.assertEqual(paper["audit"], "after")


class HouseTest(HouseCase):
    def test_practice_only_unless_the_owner_turns_real_money_on(self):
        self.assertEqual(sorted(self.house.books), ["alpaca-paper"])
        with self.assertRaises(RuntimeError):
            House(Path(self.dir.name) / "h2", brokers={"alpaca": FakeBroker("alpaca")}, sandbox=LocalSandbox(), settings=Settings(real_money=True), clock=self.clock)

    def test_spawn_reads_needs_in_the_box_endows_and_charges(self):
        agent = self.house.spawn("buyer", "test-family", BUYER, reason="test")
        self.assertEqual((agent.specialty, agent.niche), ("alpaca-crypto-majors", "alpaca-crypto-majors"))  # placed by what its NEEDS ask to see
        self.assertEqual(agent.wake_minutes, 5)
        self.assertEqual(agent.params, {"notional": 20.0})
        balance = self.house.economy.balance(agent.id)
        self.assertLess(balance, D("1.00"))  # the endowment, less the box seconds its NEEDS probe used
        self.assertGreater(balance, D("0.98"))
        with self.assertRaises(ValueError):
            self.house.spawn("broken", "test-family", "import os\ndef decide(ctx):\n    return {}\n")

    def test_a_wake_runs_the_strategy_in_its_box_and_trades_through_the_book(self):
        agent = self.seated()
        summary = self.house.tick()
        self.assertEqual(summary["woke"], [agent.id])
        self.assertEqual(summary["orders"], 1)
        book = self.house.books["alpaca-paper"]
        holding = book.account(agent.id).holdings[self.btc.key]
        self.assertEqual(holding.reason, "test buy")
        self.assertEqual(book.account(agent.id).staked, D("200"))
        self.assertTrue(summary["reconciled"]["alpaca-paper"])
        thoughts = [e.payload["text"] for e in self.house.ledger.iter(kinds="agent.thought", agent=agent.id)]
        self.assertEqual(thoughts, ["flat, so buying"])
        self.assertEqual(self.house._state["memory"][agent.id], {"bought": True})
        # Not due again until its wake interval has passed.
        self.assertEqual(self.house.tick()["woke"], [])
        self.clock.advance(301)
        self.assertEqual(self.house.tick()["woke"], [agent.id])
        self.assertEqual(book.account(agent.id).holdings, {})  # it sold what it held

    def test_opposite_agents_in_one_tick_are_netted(self):
        first = self.seated("buyer")
        self.house.tick()  # buyer now holds
        second = self.seated("other", SELLER_FIRST)
        self.clock.advance(301)
        sent_before = len(self.broker.submitted)
        self.house.tick()  # buyer sells what it holds, other buys $20: crossed inside the House
        sent = self.broker.submitted[sent_before:]
        self.assertEqual(len(sent), 1)
        crosses = [e for e in self.house.ledger.iter(kinds="book.fill") if e.payload.get("source") == "cross"]
        self.assertEqual({e.agent for e in crosses}, {first.id, second.id})
        self.assertTrue(self.house.books["alpaca-paper"].reconcile().ok)

    def test_a_rung_zero_agent_gets_one_replay_and_climbs_if_it_passes(self):
        agent = self.house.spawn("sawtooth", "test-family", SAWTOOTH, reason="test")
        self.assertEqual(self.house.wake(agent), {"agent": agent.id, "skipped": "in replay"})
        self.house.wait()  # the replay runs beside the tick, in the agent's box
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        trial = self.house.ledger.last("eval.trial", agent=agent.id).payload
        self.assertTrue(trial["passed"])
        self.assertEqual(trial["trials"], 1)
        self.assertEqual(self.house.books["alpaca-paper"].account(agent.id).staked, D("200"))

    def test_a_failed_replay_is_a_counted_trial_and_is_not_repeated(self):
        agent = self.house.spawn("idle", "test-family", IDLE, reason="test")
        self.house.wake(agent)
        self.house.wait()
        trial = self.house.ledger.last("eval.trial", agent=agent.id).payload
        self.assertFalse(trial["passed"])
        self.assertIn("0 closed trades", " ".join(trial["reasons"]))
        self.assertEqual(self.house.evaluator.rung(agent.id), 0)
        self.clock.advance(301)
        self.house.wake(agent)
        self.house.wait()
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=agent.id), 1)

    def test_a_founder_starts_on_paper_and_its_replay_still_counts(self):
        born = self.house.found(["crypto-reversion"])  # by the founder's role key; its id is its desk's
        self.assertEqual([(a.id, a.founder, a.specialty) for a in born], [("rosenfeld", "crypto-reversion", "alpaca-crypto-majors")])
        self.assertEqual(self.house.evaluator.rung("rosenfeld"), 1)
        self.assertEqual(self.house.books["alpaca-paper"].account("rosenfeld").staked, D("200"))
        self.assertEqual(self.house.found(["crypto-reversion"]), [])  # idempotent
        self.house.tick()
        self.house.wait()
        # Seen failing once on a slow CI runner (Sept 19, 2026) and never locally: if it does again, say why.
        alerts = [e.payload.get("text") for e in self.house.ledger.iter(kinds="ops.alert")]
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent="rosenfeld"), 1, alerts)

    def test_an_agent_that_never_qualifies_is_retired(self):
        agent = self.house.spawn("idle", "test-family", IDLE, reason="test")
        self.house.tick()
        self.house.wait()
        self.assertTrue(self.house.registry.get(agent.id).alive)
        self.clock.advance(3 * 86400 + 60)
        self.house.tick()
        self.assertEqual(self.house.registry.get(agent.id).cause, "never qualified")

    def test_death_at_zero_credits_winds_down_and_leaves_a_postmortem(self):
        agent = self.seated()
        self.house.tick()
        self.house.economy.charge(agent.id, "5", "a test bill")
        self.clock.advance(60)
        summary = self.house.tick()
        self.assertEqual(summary["deaths"], [agent.id])
        dead = self.house.registry.get(agent.id)
        self.assertFalse(dead.alive)
        self.assertEqual(dead.cause, "credits")
        book = self.house.books["alpaca-paper"]
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(book.account(agent.id).staked, book.account(agent.id).staked.min(D("200")))
        self.assertIn(agent.id, self.house.sandbox.retired)
        playbook = self.house.commons.playbook_read()["entries"]
        self.assertIn("died on rung 1 of credits", playbook[-1]["text"])
        self.assertTrue(book.reconcile().ok)

    def test_a_dead_agents_exit_after_a_restart_is_not_refused_for_want_of_a_seat(self):
        """Sept 22, 2026: after the night's deploys four dead agents' exits were refused as
        'has no seat on the alpaca-paper book' on every mark pass."""
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.assertTrue(book.account(agent.id).holdings)
        # A death whose exit did not finish before the House restarted (an unfilled order, a venue
        # outage): recorded dead, still holding.
        self.house.registry.died(agent.id, "credits", "a test death")
        self.assertTrue(book.account(agent.id).holdings)
        self.house.close(wait=None)
        self.house = self.new_house()  # a restart: only the living are seated
        book = self.house.books["alpaca-paper"]
        self.assertNotIn(agent.id, book.limits)
        self.clock.advance(301)
        self.house.tick()
        refused = [e.payload for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)
                   if "has no seat" in str(e.payload.get("reasons"))]
        self.assertEqual(refused, [])
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_a_death_during_a_venue_outage_is_recorded_and_its_exit_retried(self):
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.broker.raise_on_submit = ConnectionError("venue down while it dies")
        self.house.kill(agent, "credits", "a test death")
        self.assertFalse(self.house.registry.get(agent.id).alive)
        self.assertTrue(book.account(agent.id).holdings)
        self.assertIn("could not finish winding down", self.house.ledger.last("ops.alert").payload["text"])
        self.broker.raise_on_submit = None
        self.clock.advance(301)
        self.house.tick()  # the mark pass hears the venue has no such order: remembered, not yet believed
        self.clock.advance(61)
        self.house.tick()  # heard twice a minute apart, the lost exit is closed and the mark pass retries it
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_a_few_cents_short_on_paper_is_a_warning_and_real_money_stays_an_error(self):
        agent = self.seated()
        self.house.tick()  # it buys; the paper book reconciles
        self.broker.cash -= Decimal("0.06")  # the venue's fee activity has not posted yet
        self.clock.advance(301)
        self.house.tick()
        alerts = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "does not reconcile" in e.payload["text"]]
        self.assertTrue(alerts)
        self.assertEqual({a["level"] for a in alerts}, {"warning"})
        self.broker.cash -= Decimal("5.00")  # more than cents: an error
        self.clock.advance(301)
        self.house.tick()
        alerts = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "does not reconcile" in e.payload["text"]]
        self.assertEqual(alerts[-1]["level"], "error")

    def test_a_dead_agents_option_is_sold_at_the_bid_not_refused_as_a_market_order(self):
        """Sept 22, 2026: dead options agents' exits were refused twelve times in eight minutes as
        'an option order must be a limit order'. Since Sept 23 the sale also waits for the regular
        session, as a stock's does (`WindDownAtTheOpen`): an option's bid is stale or gone at night."""
        from league.book import Intent
        agent = self.seated()
        self.house.seat(agent)  # its stake, as its first wake would give it
        book = self.house.books["alpaca-paper"]
        option = instrument_for("alpaca-paper", {"occ": "F271015C00013000"})
        self.clock.now = WindDownAtTheOpen.IN_SESSION
        self.broker.clock_iso = now_iso(self.clock)
        self.broker.set_quote(option, "0.40", "0.44")
        book.limits[agent.id] = Limits(D("100"), D("75"), asset_classes=("option",))
        out = book.submit([Intent.new(agent=agent.id, instrument=option, side="buy", quantity=D("1"), order_type="limit",
                                      limit_price=D("0.44"), reason="test", created_at=now_iso(self.clock), nonce="opt")])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.clock.now = WindDownAtTheOpen.NIGHT
        self.broker.clock_iso = now_iso(self.clock)
        self.house.kill(agent, "credits", "a test death")
        refused = [e.payload for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]
        self.assertEqual(refused, [])
        self.assertTrue(book.account(agent.id).holdings)  # held for the open, not sent into a shut session
        self.clock.now = WindDownAtTheOpen.NEXT_OPEN
        self.broker.clock_iso = now_iso(self.clock)
        self.house._release_wind_downs()
        refused = [e.payload for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]
        self.assertEqual(refused, [])
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_a_wind_down_that_would_meet_the_houses_own_bid_rests_at_the_ask(self):
        """haghani-2, Sept 21, 2026: its market exit was refused on every wake because another
        agent rested a bid on the same coin."""
        from league.book import Intent
        seller = self.seated("seller")
        bidder = self.seated("bidder")
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.assertTrue(book.account(seller.id).holdings)
        now = now_iso(self.clock)
        out = book.submit([Intent.new(agent=bidder.id, instrument=self.btc, side="buy", quantity=D("0.0001"), order_type="limit",
                                      limit_price=D("79500"), reason="a resting dip bid", created_at=now, nonce="bid")])
        self.assertTrue(book.open_orders(bidder.id), out)
        self.house._wind_down(seller, book)
        sells = [w for w in book.open_orders(seller.id) if w.side == "sell"]
        refused = [e for e in self.house.ledger.iter(kinds="book.refused", agent=seller.id)]
        self.assertTrue(sells or not book.account(seller.id).holdings, refused)
        if sells:
            self.assertEqual(sells[0].limit_price, D("80005"))

    def test_a_rich_agent_forks_a_mutated_child_and_endows_it(self):
        agent = self.seated()
        self.house.economy.grant(agent.id, "3", "a windfall for the test")
        before = self.house.economy.balance(agent.id)
        self.house.tick()
        children = [a for a in self.house.registry.living() if a.parent == agent.id]
        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertEqual(child.generation, 2)
        self.assertNotEqual(child.params, agent.params)
        self.assertEqual(self.house.evaluator.rung(child.id), 0)  # a mutation answers for itself from replay up
        self.assertGreaterEqual(self.house.economy.balance(child.id), D(self.house.game["economy"]["fork_endowment_usd"]) - D("0.01"))
        transfer = self.house.ledger.last("credit.transfer", agent=agent.id).payload
        self.assertEqual((transfer["to"], D(transfer["usd"])), (child.id, D(self.house.game["economy"]["fork_endowment_usd"])))
        self.assertIn((agent.id, child.id), self.house.sandbox.forks)
        self.assertEqual(self.house.ledger.last("agent.forked", agent=agent.id).payload["child"], child.id)
        self.house.tick()
        self.assertEqual(len([a for a in self.house.registry.living() if a.parent == agent.id]), 1)  # once an epoch

    def test_a_fleet_windfall_spreads_child_launches_across_ticks(self):
        parents = [self.seated(name) for name in ('first', 'second')]
        for agent in parents:
            self.house.economy.grant(agent.id, '4', 'burst payout')
        for count in range(1, 3):
            self.house.keep_population()
            children = [a for a in self.house.registry.living() if a.parent]
            self.assertEqual(len(children), count)
            self.assertEqual(len({a.parent for a in children}), count)

    def test_stopped_population_can_cull_without_buying_child_launches(self):
        rich, broke = self.seated('rich'), self.seated('broke')
        self.house.economy.grant(rich.id, '4', 'a windfall')
        self.house.economy.charge(broke.id, '100', 'exhausted')
        self.house.keep_population(refill=False)
        self.assertFalse(broke.alive)
        self.assertEqual([a.id for a in self.house.registry.living()], [rich.id])
        self.assertEqual(self.house.sandbox.forks, [])

    def test_the_epoch_payout_reaches_the_living(self):
        agent = self.seated()
        before = self.house.economy.balance(agent.id)
        self.house.tick()
        # Nobody has a record yet. Before the expedition's first day the pool is the game file's $2; the
        # unearned performance share follows the floors (the owner wants the budget used), so all of it is paid.
        gained = self.house.economy.balance(agent.id) - before
        self.assertGreater(gained, D(self.house.game["economy"]["daily_pool_usd"]) - D("0.01"))
        self.assertLess(gained, D("2.01"))

    def test_during_the_expedition_the_days_pool_is_drawn_from_both_budgets(self):
        from league.pacer import Pacer

        agent = self.seated()
        today = now_iso(self.clock)[:10]
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={"start": today, "days": 10, "sail_usd": "50", "openai_usd": "50"})
        self.house.tick()
        payout = [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "payout"][-1]
        # 85% of Sail's $5 a day and 70% of the frontier's, because an agent buys research with
        # one and Merton's time with the other, all of it paid out
        # a quarter of the day, because the league pays four times a day now
        self.assertEqual((D(payout["pool_usd"]), D(payout["paid_usd"]).quantize(D("0.01"))), (D("1.94"), D("1.94")))
        report = self.house.ledger.last("ops.budget").payload
        self.assertEqual((report["what"], report["day"], report["of"], report["sail"]["budget_usd"]), ("expedition", 1, 10, "50"))

    def test_a_restart_resumes_the_same_floor(self):
        agent = self.seated()
        self.house.tick()
        self.house.close()
        self.house = self.new_house()
        self.assertEqual([a.id for a in self.house.registry.living()], [agent.id])
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.house.tick()["woke"], [])  # its next wake was remembered
        self.assertIn(self.btc.key, self.house.books["alpaca-paper"].account(agent.id).holdings)
        self.assertEqual(self.house.ledger.verify(), self.house.ledger.head()[0])

    def test_malformed_intents_are_dropped_not_fatal(self):
        agent = self.seated("junk", JUNK)
        out = self.house.wake(agent)
        self.assertEqual(len(out["intents"]), 1)
        self.assertEqual(len(out["dropped"]), 2)

    def test_mutate_is_deterministic_and_keeps_types(self):
        params = {"lookback": 24, "z": 2.0, "maker": True, "symbols": ["BTC/USD"]}
        self.assertEqual(mutate(params, seed="a"), mutate(params, seed="a"))
        child = mutate(params, seed="a")
        self.assertIsInstance(child["lookback"], int)
        self.assertIs(child["maker"], True)
        self.assertEqual(child["symbols"], ["BTC/USD"])
        self.assertNotEqual(child, params)
        self.assertEqual(child["z"], 2.0)  # unknown units stay frozen until explicitly bounded


IDLE = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "idle", "symbols": ["BTC/USD"], "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "nothing to do"}
'''

SAWTOOTH = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "sawtooth", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 5}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    bars = ctx["bars"].get("BTC/USD") or []
    if not bars:
        return {"intents": [], "thought": "no bars"}
    low = bars[-1]["c"] < 80000
    held = [p for p in ctx["positions"] if p["symbol"] == "BTC/USD"]
    if low and not held:
        return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": 50, "type": "market", "reason": "low"}], "thought": "buy low"}
    if held and not low:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "high"}], "thought": "sell high"}
    return {"intents": [], "thought": "wait"}
'''

JUNK = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "junk", "symbols": ["BTC/USD"], "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    return {"intents": [
        {"symbol": "BTC/USD", "side": "buy", "notional_usd": 20, "type": "market", "reason": "fine"},
        {"symbol": "", "side": "buy", "notional_usd": 20, "type": "market", "reason": "no symbol"},
        {"symbol": "BTC/USD", "side": "buy", "notional_usd": 0.0000001, "type": "market", "reason": "rounds to nothing"},
    ], "thought": "two of these are junk"}
'''



class ResearchPace(HouseCase):
    """Winners run, losers wait: the owner's direction of Sept 21, 2026."""

    def test_a_winner_researches_more_often_and_a_loser_less(self):
        self.house.game["research"]["min_hours_between"] = 0.25
        winner, loser, fresh = self.seated("winner"), self.seated("loser"), self.seated("fresh")
        for agent, growth in ((winner, 0.003), (loser, -0.002)):
            for n in range(6):
                self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                        "book": "alpaca-paper", "block": f"b{n}"}, agent=agent.id)
        pace = self.house.game["research"]["pace"]
        self.assertAlmostEqual(self.house.research_interval_hours(winner), 0.25 * pace["winner_share"])
        self.assertAlmostEqual(self.house.research_interval_hours(loser), 0.25 * pace["loser_multiple"])
        # Sept 23, 2026: an agent with no earned record waits `unproven_multiple` intervals (6 since
        # the 16:41Z pacing of the September OpenAI line; 3 before).
        self.assertAlmostEqual(self.house.research_interval_hours(fresh), 0.25 * pace["unproven_multiple"])
        self.assertEqual((pace["winner_share"], pace["loser_multiple"], pace["unproven_multiple"]), (0.1, 8, 6))
        # An idle agent's research is pulled forward, never put off for having no record.
        self.house.idle_reason = lambda agent: "ten barren wakes" if agent.id == fresh.id else ""
        idle_hours = float(self.house.game["research"]["idle"]["min_hours_between"])
        self.assertAlmostEqual(self.house.research_interval_hours(fresh), min(0.25, idle_hours))


class DailyEvidence(HouseCase):
    def test_a_daily_block_counts_as_the_screen_counts_it(self):
        """A daily block is as many observations as the screen's hourly blocks per daily one."""
        from league.constitution import CONSTITUTION
        paper = CONSTITUTION["ladder"]["paper"]
        per_day = paper["min_active_blocks"] / paper["min_active_blocks_day"]
        agent = self.seated("daily")
        for n in range(2):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": 0.007, "active": True, "horizon": "day",
                                                    "book": "alpaca-paper", "block": f"d{n}"}, agent=agent.id)
        row = self.house.standing_of(agent.id)
        self.assertEqual(row["earned_observations"], 2 * per_day)
        self.assertAlmostEqual(row["earned_growth"], 0.014 / 48)


@old_ladder()
class FastLane(HouseCase):
    def test_a_live_micro_agent_down_twenty_percent_goes_back_to_paper(self):
        agent = self.seated("live", code=BUYER)
        self.house.evaluator.promote(agent.id, 2, "test: real money")
        book = self.house.book_of(agent)
        for n in range(2):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": -0.12, "active": True,
                                                    "book": book.name, "block": f"b{n}"}, agent=agent.id)
        verdict = self.house.judge(agent)
        self.assertEqual(verdict.decision, "demote")
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.assertIn("back to paper", verdict.reason)


class Refill(HouseCase):
    """A death is only useful if something new sits in the empty seat."""

    def test_the_house_fills_up_to_the_ceiling_not_only_off_the_floor(self):
        agent = self.seated()
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=3, min_population=0)
        self.assertIsNone(self.house._refill(rules), "a House that has just started breeds nobody")
        self.clock.advance(601)
        first = self.house._refill(rules)
        self.assertIsNotNone(first)
        self.assertEqual((first.parent, first.line, first.specialty), (agent.id, agent.line, agent.specialty))
        self.assertNotEqual(first.params, agent.params)  # a mutation, not a copy
        self.assertIsNone(self.house._refill(rules))  # one at a time
        self.clock.advance(601)
        self.assertIsNotNone(self.house._refill(rules))
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(rules), "the ceiling holds")

    def test_a_newcomer_is_bred_from_an_agent_that_is_making_money(self):
        """Not from the richest purse: purses were paid to the least-bad LOSERS for a day."""
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=5, min_population=0)
        rich = self.seated("rich")
        earner = self.seated("earner")
        self.house.economy.grant(rich.id, "100", "test: a purse from least-bad payouts")
        for agent, growth in ((rich, -0.002), (earner, 0.003)):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": "b0"}, agent=agent.id)
        self.clock.advance(601)
        child = self.house._refill(rules)
        self.assertEqual(child.parent, earner.id)

    def test_the_wait_for_a_newcomer_outlives_a_restart(self):
        """Sept 20, 2026: the interval was anchored on this process's start, which moves on every
        deploy, and a floor that rewrites itself deploys every half hour. In six hours the hour
        never elapsed once and the league sat at its founding size with seven seats empty."""
        self.seated()
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=3, min_population=0)
        self.clock.advance(400)
        self.house._save_state()  # as a tick does, within a minute of the first start
        restarted = self.new_house(game=self.house.game)  # the same state directory, a new process
        try:
            self.clock.advance(400)  # 800s since the floor first ran, 400s since this process did
            self.assertIsNotNone(restarted._refill(rules))
        finally:
            restarted.close(wait=None)

    def test_a_full_league_gives_the_last_seat_to_a_newcomer_over_its_worst_agent(self):
        """Thirty-three born in twelve hours and not one dead: a ceiling with nothing dying under
        it is a floor that has stopped searching."""
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=2, min_population=0, displace_after_epochs=2)
        good = self.seated("winner")
        weak = self.seated("loser")
        self.house.evaluator.seat(weak.id, 1, "test")
        self.clock.advance(2 * float(rules["epoch_seconds"]) + 601)
        self.house._state["last_newcomer"]["at"] = self.clock() - 601
        for agent, growth in ((good, 0.01), (weak, -0.01)):
            for n in range(3):
                self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                        "book": "alpaca-paper", "block": f"b{n}"}, agent=agent.id)
        joined = self.house._refill(rules)
        self.assertIsNotNone(joined)
        living = [a.id for a in self.house.registry.living()]
        self.assertNotIn(weak.id, living)   # the worst with a fair chance behind it
        self.assertIn(good.id, living)      # the profitable one is never displaced
        died = self.house.ledger.last("agent.died", agent=weak.id).payload
        self.assertEqual(died["cause"], "displaced")

    def test_an_agent_that_has_never_traded_goes_before_one_that_is_trading_badly(self):
        """Ranking by growth alone did the opposite of what it was for: an agent that has never
        placed an order has a mean growth of exactly 0.0, which sorts above every negative number,
        so the agents that never traded were the SAFEST on the floor. It killed hilibrand at 09:46
        on Sept 20, 2026 -- twelve of the fifteen active blocks the screen wants -- while
        twenty-six agents that had never traded sat untouched."""
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=2, min_population=0, displace_after_epochs=2)
        working = self.seated("worker")     # trading, and losing
        idle = self.seated("idler")         # has never placed an order
        for a in (working, idle):
            self.house.evaluator.seat(a.id, 1, "test")
        for n in range(12):
            self.house.ledger.append("eval.block", {"agent": working.id, "log_growth": -0.01, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{n}"}, agent=working.id)
        self.clock.advance(2 * float(rules["epoch_seconds"]) + 601)
        self.assertEqual(self.house._weakest(rules).id, idle.id)

    def test_nobody_young_or_profitable_or_on_real_money_is_displaced(self):
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=1, min_population=0, displace_after_epochs=2)
        fresh = self.seated("newish")
        self.house.evaluator.seat(fresh.id, 1, "test")
        self.clock.advance(601)
        self.assertIsNone(self.house._weakest(rules))  # too young to have had a chance
        self.assertIsNone(self.house._refill(rules))   # so the league stays full and adds nobody
        self.clock.advance(2 * float(rules["epoch_seconds"]))
        self.house.evaluator.promote(fresh.id, 2, "test: real money")
        self.assertIsNone(self.house._weakest(rules))  # real money is the auditor's and the tuition's

    def test_a_newcomer_joins_the_desk_with_the_most_room(self):
        crypto = self.seated()  # alpaca-crypto-majors
        rules = self.house.game["economy"]
        rules.update(newcomer_seconds=600, max_population=9, min_population=0)
        self.house.niches["alpaca-crypto-majors"].max_members = 1  # full
        self.house.niches["alpaca-index-etfs"].max_members = 9
        etf = self.house.spawn("scholes", "etf", BUYER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]').replace("test-buyer", "etf"), reason="test")
        self.assertEqual(etf.specialty, "alpaca-index-etfs")
        self.clock.advance(601)
        joined = self.house._refill(rules)
        self.assertEqual((joined.specialty, joined.parent), ("alpaca-index-etfs", etf.id))
        self.assertNotEqual(joined.parent, crypto.id)


class Lanes(HouseCase):
    def test_housekeeping_and_research_never_queue_behind_replays(self):
        # Regression: on the first production start (Sept 19, 2026) one two-slot queue held 28 founders'
        # replays, and research, the daily backup and the niche survey all waited behind them.
        import threading

        release, done = threading.Event(), []
        for i in range(self.house.settings.slow_workers + 2):
            self.house._background(f"replay:{i}", release.wait)
        self.house._background("backup", lambda: done.append("backup"))
        self.house._background("research:a1", lambda: done.append("research"))
        for key in ("backup", "research:a1"):
            self.house._jobs[key].join(5)
        try:
            self.assertEqual(sorted(done), ["backup", "research"])
        finally:
            release.set()
            self.house.wait(5)


if __name__ == "__main__":
    unittest.main()


class StandingsMemo(HouseCase):
    """Sept 23, 2026: the production tick spent about 80% of its main thread re-ranking every living
    agent several times a tick (displacement, the refill, the foundry). One table a tick now."""

    def test_the_tick_builds_the_standings_once_and_other_callers_build_them_fresh(self):
        self.seated("alpha")
        self.seated("beta")
        calls = []
        real = self.house._standing

        def counted(agent, epoch):
            calls.append(agent.id)
            return real(agent, epoch)

        with patch.object(self.house, "_standing", side_effect=counted):
            self.house._standings_memo = {"thread": __import__("threading").get_ident(), "living": None, "rows": None}
            first = self.house.standings()
            second = self.house.standings()
            self.assertEqual([s.agent for s in first], [s.agent for s in second])
            self.assertEqual(len(calls), 2)  # built once for two agents
            self.house.registry.born(name="gamma", family="test-family", code=BUYER,
                                     needs={"venue": "alpaca", "horizon": "hour", "style": "test"})
            self.house.standings()
            self.assertEqual(len(calls), 5)  # a birth rebuilds it
            self.house._standings_memo = None
            self.house.standings()
            self.assertEqual(len(calls), 8)  # outside a tick: fresh every time
        self.house.tick()
        self.assertIsNone(self.house._standings_memo)  # the memo never outlives its tick


class WindDownAtTheOpen(HouseCase):
    """Sept 22-23, 2026: 576 'market orders outside regular hours' and 116 'an option order must
    be a limit order' refusals in a day, every one the House winding down a dead agent's stock or
    option on every mark pass through the night. A stock's or an option's wind-down sale now waits
    for its market to open; a coin's is placed at once, as before."""

    STOCK = BUYER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]').replace("test-buyer", "test-stock")
    IN_SESSION = 1789047300.0  # 2026-09-10T13:35:00Z, a Thursday, the regular session open
    NIGHT = 1789092000.0  # 2026-09-11T02:00:00Z
    NEXT_OPEN = 1789133405.0  # 2026-09-11T13:30:05Z

    def at(self, moment):
        """Move the clock, and the venue's quote stamps with it (the book refuses a stale quote)."""
        self.clock.now = moment
        self.broker.clock_iso = now_iso(self.clock)

    def holding_stock(self):
        from league.book import Intent
        agent = self.seated("stock", self.STOCK)
        self.house.seat(agent)
        book = self.house.books["alpaca-paper"]
        spy = instrument_for("alpaca-paper", {"symbol": "SPY"})
        self.broker.set_quote(spy, "50.00", "50.10")
        book.limits[agent.id] = Limits(D("100"), D("75"), asset_classes=("equity",))
        self.at(self.IN_SESSION)
        out = book.submit([Intent.new(agent=agent.id, instrument=spy, side="buy", quantity=D("1"), order_type="limit",
                                      limit_price=D("50.10"), reason="test", created_at=now_iso(self.clock), nonce="spy")])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertTrue(book.account(agent.id).holdings)
        return agent, book, spy

    def refusals(self, agent):
        return [e.payload["reasons"] for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]

    def held_alerts(self):
        return [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "for the open" in e.payload["text"]]

    def test_a_dead_stock_agents_position_waits_for_the_open_and_is_sold_at_the_bell(self):
        agent, book, spy = self.holding_stock()
        self.at(self.NIGHT)
        self.house.kill(agent, "credits", "a test death")
        self.assertFalse(self.house.registry.get(agent.id).alive)
        self.assertTrue(book.account(agent.id).holdings)  # not sold: the session is shut
        self.assertEqual(self.refusals(agent), [])  # and no refused order says so on every pass
        self.assertEqual(self.house._state["wind_down_held"][agent.id]["alpaca-paper"][spy.key]["quantity"], "1")
        self.assertEqual([a["level"] for a in self.held_alerts()], ["info"])
        self.at(self.NIGHT + 301)
        self.house.tick()  # a mark pass in the night: still held, still nothing refused, told once
        self.assertTrue(book.account(agent.id).holdings)
        self.assertEqual(self.refusals(agent), [])
        self.assertEqual(len(self.held_alerts()), 1)
        self.at(self.NEXT_OPEN)
        self.house.tick()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(self.refusals(agent), [])
        self.assertNotIn(agent.id, self.house._state.get("wind_down_held") or {})
        self.assertTrue(book.reconcile().ok)

    def test_the_held_sale_is_placed_at_the_bell_not_at_the_next_mark_pass(self):
        agent, book, spy = self.holding_stock()
        self.at(self.NIGHT)
        self.house.kill(agent, "credits", "a test death")
        self.at(self.NEXT_OPEN)
        self.house._release_wind_downs()  # what the tick calls before the mark pass
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(self.refusals(agent), [])
        self.house._release_wind_downs()  # once a session: nothing left to place, nothing raised

    def test_the_hold_survives_a_restart(self):
        agent, book, spy = self.holding_stock()
        self.at(self.NIGHT)
        self.house.kill(agent, "credits", "a test death")
        self.house.close(wait=None)
        self.house = self.new_house()
        book = self.house.books["alpaca-paper"]
        self.assertIn(spy.key, self.house._state["wind_down_held"][agent.id]["alpaca-paper"])
        self.assertTrue(book.account(agent.id).holdings)
        self.at(self.NEXT_OPEN)
        self.house.tick()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(self.refusals(agent), [])
        self.assertEqual(len(self.held_alerts()), 1)  # told once, before the restart

    def test_a_dead_crypto_agents_position_is_sold_at_once_at_night(self):
        agent = self.seated()
        self.at(self.NIGHT)
        self.house.tick()  # it buys BTC/USD
        book = self.house.books["alpaca-paper"]
        self.assertTrue(book.account(agent.id).holdings)
        self.house.kill(agent, "credits", "a test death")
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(self.house._state.get("wind_down_held") or {}, {})
        self.assertEqual(self.held_alerts(), [])


class FloorInvariants(HouseCase):
    """Workstream B, Sept 23, 2026: the floor finds the next blocker itself. Two cheap checks over
    the ledger's new rows, each an ops warning once per condition."""

    def wake(self, agent, *, offered, intents=0, ago=0.0):
        at = now_iso(lambda: self.clock() - ago)
        self.house.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": intents, "dropped": [],
                                                "cancels": 0, "offered": offered}, agent=agent.id, at=at)

    def warnings(self, text):
        return [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if e.payload["level"] == "warning" and text in e.payload["text"]]

    def test_a_desk_offered_markets_for_an_hour_with_no_intent_is_told_once_an_hour(self):
        agent = self.seated()
        other = self.seated("other", SELLER_FIRST)
        for ago in (3000, 1800, 600):
            self.wake(agent, offered=3, ago=ago)
        self.house._floor_invariants()
        told = self.warnings("alpaca-crypto-majors: offered markets on 3 wakes")
        self.assertEqual(len(told), 1)
        self.assertIn(agent.id, told[0]["text"])
        self.assertNotIn(other.id, told[0]["text"])  # it did not wake; the wakes that saw markets are named
        self.clock.advance(301)
        self.wake(agent, offered=4)
        self.house._floor_invariants()
        self.assertEqual(len(self.warnings("alpaca-crypto-majors: offered markets")), 1)  # once an hour
        self.clock.advance(3600)
        for ago in (3000, 1800, 600):
            self.wake(other, offered=2, ago=ago)
        self.house._floor_invariants()
        self.assertEqual(len(self.warnings("alpaca-crypto-majors: offered markets")), 2)
        state = self.house._state["invariants"]
        self.assertGreater(state["cursor"], 0)  # the next pass starts where this one stopped
        self.assertTrue(all(self.clock() - row[0] <= 3600 for rows in state["wakes"].values() for row in rows))  # older than an hour is dropped

    def test_a_desk_that_wrote_an_intent_or_saw_nothing_is_not_quiet(self):
        agent = self.seated()
        for ago in (3000, 1800):
            self.wake(agent, offered=3, ago=ago)
        self.wake(agent, offered=3, intents=1, ago=600)
        self.house._floor_invariants()
        self.assertEqual(self.warnings("offered markets"), [])
        self.clock.advance(3601)
        for ago in (3000, 1800, 600):
            self.wake(agent, offered=0, ago=ago)  # a shut market: doing nothing was right
        self.house._floor_invariants()
        self.assertEqual(self.warnings("offered markets"), [])
        self.clock.advance(3601)
        for ago in (3000, 1800, 600):
            self.wake(agent, offered=3, ago=ago)
        self.house.ledger.append("agent.intent", {"book": "alpaca-paper", "symbol": "BTC/USD", "side": "buy"}, agent=agent.id)
        self.house._floor_invariants()
        self.assertEqual(self.warnings("offered markets"), [])

    def test_a_real_money_bunt_frozen_by_a_daily_loss_rule_is_told_once_a_day(self):
        agent = self.seated()
        self.house.evaluator.seat(agent.id, 2, "a bunt")
        reason = "desk daily loss 12.0% reached limit 10%; only risk-reducing orders allowed"
        refused = {"book": "alpaca", "intent_id": "x", "reasons": [reason]}
        self.house.ledger.append("book.refused", refused, agent=agent.id)
        self.house._floor_invariants()
        told = self.warnings("frozen by a daily-loss rule")
        self.assertEqual(len(told), 1)
        self.assertIn(agent.id, told[0]["text"])
        self.assertIn(reason, told[0]["text"])
        self.assertIn("on alpaca", told[0]["text"])
        self.clock.advance(301)
        self.house.ledger.append("book.refused", refused, agent=agent.id)
        self.house.ledger.append("book.refused", {**refused, "book": "alpaca-paper"}, agent=agent.id)  # practice: not a bunt
        self.house._floor_invariants()
        self.assertEqual(len(self.warnings("frozen by a daily-loss rule")), 1)  # once a day
        self.clock.advance(86400)
        self.house.ledger.append("book.refused", refused, agent=agent.id)
        self.house._floor_invariants()
        self.assertEqual(len(self.warnings("frozen by a daily-loss rule")), 2)

    def test_a_paper_agents_daily_loss_refusal_is_not_a_frozen_bunt(self):
        agent = self.seated()  # rung 1: the book's daily rule is its rule
        self.house.ledger.append("book.refused", {"book": "alpaca", "intent_id": "x", "reasons": ["desk daily loss 12.0% reached limit 10%"]}, agent=agent.id)
        self.house._floor_invariants()
        self.assertEqual(self.warnings("frozen by a daily-loss rule"), [])

    def test_the_checks_run_off_the_tick_from_a_saved_cursor(self):
        agent = self.seated()
        self.house.tick()
        first = self.house._state["invariants"]["cursor"]
        self.assertGreater(first, 0)
        self.clock.advance(301)
        self.house.tick()
        self.assertGreaterEqual(self.house._state["invariants"]["cursor"], first)
