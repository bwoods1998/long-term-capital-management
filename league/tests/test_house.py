import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.book import Limits
from league.economy import load_game
from league.house import House, Settings, mutate
from league.ledger import now_iso
from league.sandbox import LocalSandbox
from league.tests.fakes import Clock, FakeBroker
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

    def tape(self, symbols, timeframe, *, start, end, horizon="hour", half_spread_bps=None):
        steps = []
        for hour in range(60):
            for minute in range(0, 60, 5):
                # A sawtooth the test strategy profits from: it buys low on even bars and sells high on odd ones.
                price = 80000.0 * (1.0 + (0.01 if (minute // 5) % 2 else -0.01))
                steps.append({"t": f"2026-09-{10 + hour // 24:02d}T{hour % 24:02d}:{minute:02d}:00Z", "bars": {s: {"o": price, "h": price, "l": price, "c": price, "v": 1.0} for s in symbols}})
        return {"venue": "alpaca", "horizon": horizon, "step_seconds": 300, "half_spread_bps": 0.5, "steps": steps, "results": {}}


class HouseCase(unittest.TestCase):
    def setUp(self):
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
        self.assertNotEqual(child["z"], 2.0)


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
