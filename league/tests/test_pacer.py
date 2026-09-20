"""The expedition's pace: $100 of Sail and $100 of the frontier model, used in full over fourteen days."""

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from league.constitution import CONSTITUTION
from league.ledger import Ledger
from league.pacer import Pacer
from league.tests.fakes import Clock
from league.tests.test_house import HouseCase

D = Decimal
RULES = {"start": "2026-09-19", "days": 14, "sail_usd": "100", "openai_usd": "70"}


def epoch(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class PacerCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.clock.now = epoch("2026-09-19T12:00:00")
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.pacer = Pacer(self.ledger, clock=self.clock, expedition=RULES)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def at(self, text):
        self.clock.now = epoch(text)
        self.pacer._cache.clear()

    def sail(self, usd):
        self.ledger.append("ops.budget", {"what": "sail", "spent_usd": str(usd), "balance_usd": "50"})
        self.pacer._cache.clear()

    def merton(self, usd, kind="merton.pass"):
        self.ledger.append(kind, {"role": "architect", "cost_usd": str(usd)}, agent="house" if kind == "merton.pass" else "a1")
        self.pacer._cache.clear()

    def test_the_constitution_funds_a_fortnight_from_the_nineteenth(self):
        self.assertEqual(CONSTITUTION["budgets"]["expedition"], {"start": "2026-09-19", "days": 14, "sail_usd": "100", "openai_usd": "100"})

    def test_the_first_days_allowance_is_the_budget_over_fourteen(self):
        self.assertEqual((self.pacer.day(), self.pacer.days_left(), self.pacer.running()), (0, 14, True))
        self.assertEqual(self.pacer.allowance("openai"), D(5))
        self.assertAlmostEqual(float(self.pacer.allowance("sail")), 100 / 14, places=9)
        self.assertTrue(self.pacer.may_spend("sail"))

    def test_spending_uses_up_todays_room_and_not_tomorrows(self):
        self.merton("3")
        self.assertEqual((self.pacer.room("openai"), self.pacer.allowance("openai")), (D(2), D(5)))  # the allowance does not shrink as it is used
        self.merton("2.5", kind="audit.verdict")
        self.assertFalse(self.pacer.may_spend("openai"))
        self.at("2026-09-20T00:05:00")
        self.assertTrue(self.pacer.may_spend("openai"))

    def test_an_overspent_day_is_paid_back_and_a_quiet_day_rolls_forward(self):
        self.merton("12")  # a dear first day: 7 over
        self.at("2026-09-20T09:00:00")
        self.assertAlmostEqual(float(self.pacer.allowance("openai")), (70 - 12) / 13, places=9)
        self.at("2026-09-25T09:00:00")  # five quiet days later the unspent share has rolled forward
        self.assertAlmostEqual(float(self.pacer.allowance("openai")), (70 - 12) / 8, places=9)

    def test_followed_exactly_the_budget_is_spent_to_the_cent_on_the_last_day(self):
        for day in range(14):
            self.at(f"2026-{'09' if day < 12 else '10'}-{19 + day if day < 12 else day - 11:02d}T10:00:00")
            self.sail(self.pacer.allowance("sail"))
        self.assertAlmostEqual(float(self.pacer.spent("sail")), 100.0, places=6)
        self.assertFalse(self.pacer.may_spend("sail"))

    def test_a_spent_budget_stops_for_good_and_so_does_the_last_day(self):
        self.sail("100")
        self.assertTrue(self.pacer.over("sail"))
        self.assertFalse(self.pacer.over("openai"))
        self.at("2026-10-02T23:00:00")
        self.assertTrue(self.pacer.running())  # the fourteenth day
        self.at("2026-10-03T00:00:01")
        self.assertEqual((self.pacer.running(), self.pacer.over("openai"), self.pacer.may_spend("openai"), self.pacer.allowance("openai")), (False, True, False, D(0)))

    def test_spending_from_before_the_expedition_is_not_the_expeditions(self):
        self.ledger.append("ops.budget", {"what": "sail", "spent_usd": "9"}, at="2026-09-18T23:00:00.000Z")
        self.assertEqual(self.pacer.spent("sail"), D(0))

    def test_the_credit_pool_is_most_of_the_days_sail_allowance(self):
        """Sail alone: what an agent buys with these credits -- sandbox seconds, research tokens --
        is a Sail cost. A consultation with Merton is the frontier's, and paced against it."""
        self.assertEqual(self.pacer.credit_pool(), D("6.07"))  # 85% of 7.142857
        self.at("2026-10-05T00:00:00")
        self.assertEqual(self.pacer.credit_pool(), D(0))

    def test_garbage_on_the_ledger_is_not_money(self):
        self.ledger.append("merton.pass", {"role": "operator", "cost_usd": "not a number"})
        self.ledger.append("merton.pass", {"role": "operator", "cost_usd": "-4"})
        self.ledger.append("merton.pass", {"role": "operator"})
        self.assertEqual(self.pacer.spent("openai"), D(0))


class InTheHouse(HouseCase):
    def test_research_waits_when_todays_sail_allowance_is_spent(self):
        self.house.researcher = object()
        self.house.settings.research = True
        agent = self.seated()
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={"start": "2026-09-10", "days": 14, "sail_usd": "14", "openai_usd": "14"})
        self.assertTrue(self.house.research_due(agent))
        self.house.ledger.append("ops.budget", {"what": "sail", "spent_usd": "1.01"})
        self.house.pacer._cache.clear()
        self.assertFalse(self.house.research_due(agent))

    def test_the_sail_meter_stops_the_house_when_the_expeditions_sail_is_gone(self):
        from league.budget import Budget

        balance = [D("90")]
        budget = Budget(self.house.ledger, lambda: balance[0], clock=self.clock, every_seconds=0)
        budget.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={"start": "2026-09-10", "days": 14, "sail_usd": "3", "openai_usd": "3"})
        self.assertEqual(budget.check(force=True), "open")
        balance[0] = D("88")
        self.assertEqual(budget.check(force=True), "open")
        budget.pacer._cache.clear()
        balance[0] = D("86.9")
        self.assertEqual(budget.check(force=True), "stopped")


if __name__ == "__main__":
    unittest.main()


class Catching(HouseCase):
    def expedition(self, **kw):
        today = __import__("league.ledger", fromlist=["now_iso"]).now_iso(self.clock)[:10]
        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={"start": today, "days": 10, "sail_usd": "50", "openai_usd": "50", **kw})

    def test_research_comes_round_twice_as_often_while_the_day_is_underspent(self):
        """Research is a Sail cost, so it is the Sail allowance that decides its pace."""
        self.expedition()
        self.clock.now = self.clock.now - self.clock.now % 86400 + 3 * 3600  # 03:00: too early to call the day behind
        self.assertEqual(self.house.research_interval_hours(), 3.0)
        self.clock.now += 12 * 3600  # 15:00 and nothing spent
        self.house.pacer._cache.clear()
        self.assertEqual(self.house.research_interval_hours(), 1.5)
        self.house.ledger.append("ops.budget", {"what": "sail", "spent_usd": "3.00"})  # 60% of the day's $5 by 15:00: on pace
        self.house.pacer._cache.clear()
        self.assertEqual(self.house.research_interval_hours(), 3.0)

    def test_research_is_a_sail_cost_and_is_not_billed_to_the_frontier_budget(self):
        """A research pass runs on Sail's own inference, not on the frontier model, and the Sail
        meter reads it from the credit balance. Counting it twice would stop Merton and the audits
        -- the calls that really are the frontier's -- on a bill they did not run up."""
        self.expedition()
        self.house.ledger.append("merton.pass", {"role": "architect", "cost_usd": "1.05"})
        self.house.ledger.append("agent.research", {"tool": "summary", "cost_usd": "2.16"}, agent="a1")
        self.house.pacer._cache.clear()
        self.assertEqual(self.house.pacer.spent("openai"), D("1.05"))

    def test_outside_the_expedition_the_game_files_number_stands(self):
        self.assertEqual(self.house.research_interval_hours(), 3.0)


class HouseStakedChildren(HouseCase):
    CANDIDATE = None

    def test_a_candidate_that_passed_replay_is_staked_by_the_house_when_its_parent_cannot_pay(self):
        from league.tests.test_house import BUYER

        parent = self.seated()
        self.assertFalse(self.house.economy.can_fork(parent.id))
        before = self.house.economy.balance(parent.id)
        child = self.house.fork(parent, code=BUYER.replace("20.0", "21.0"), params={"notional": 21.0}, reason="research: a larger clip", passed_replay=True, staked_by_house=True)
        self.assertIsNotNone(child)
        self.assertEqual(self.house.economy.balance(parent.id), before)  # the parent paid nothing
        self.assertGreater(self.house.economy.balance(child.id), D("0.9"))
        self.assertEqual((child.parent, child.specialty, self.house.evaluator.rung(child.id)), (parent.id, parent.specialty, 1))
        forked = self.house.ledger.last("agent.forked", agent=parent.id).payload
        self.assertEqual((forked["staked_by"], forked["new_code"]), ("house", True))
        # One a parent a day, and never for code that did not pass or for a mere mutation.
        self.assertIsNone(self.house.fork(parent, code=BUYER.replace("20.0", "22.0"), passed_replay=True, staked_by_house=True))
        self.clock.advance(86401)
        self.assertIsNone(self.house.fork(parent, code=BUYER.replace("20.0", "22.0"), passed_replay=False, staked_by_house=True))
        self.assertIsNone(self.house.fork(parent, staked_by_house=True))
        self.assertIsNotNone(self.house.fork(parent, code=BUYER.replace("20.0", "22.0"), passed_replay=True, staked_by_house=True))


class LostWork(HouseCase):
    def expedition(self):
        from league.ledger import now_iso

        self.house.pacer = Pacer(self.house.ledger, clock=self.clock, expedition={"start": now_iso(self.clock)[:10], "days": 10, "sail_usd": "50", "openai_usd": "50"})

    def test_a_research_pass_lost_to_a_restart_is_due_again_at_once(self):
        # Regression (the first production day): every agent was stamped as researched when its pass was
        # QUEUED; the queue was lost to a restart and nobody researched for an hour and a half.
        import threading

        self.house.researcher = type("R", (), {"research": lambda self, agent, standing, session: type("P", (), {"candidate": None})()})()
        self.house.settings.research = True
        agent = self.seated()
        self.expedition()
        self.house._lanes["research"] = threading.Semaphore(0)  # the pass is queued and never runs
        self.house._background(f"research:{agent.id}", self.house.research, agent)
        try:
            self.assertTrue(self.house.research_due(agent))  # queued is not done
            self.assertFalse(self.house._background(f"research:{agent.id}", self.house.research, agent))  # and is not queued twice
        finally:
            self.house._lanes["research"].release()
        self.house._jobs[f"research:{agent.id}"].join(5)
        self.assertFalse(self.house.research_due(agent))  # done is done, until the interval has passed

    def test_a_failed_pass_is_not_retried_every_tick(self):
        def boom(agent, standing, session):
            raise RuntimeError("the provider is down")

        self.house.researcher = type("R", (), {"research": staticmethod(boom)})()
        self.house.settings.research = True
        agent = self.seated()
        self.expedition()
        self.assertTrue(self.house.research_due(agent))
        with self.assertRaises(RuntimeError):
            self.house.research(agent)
        self.assertFalse(self.house.research_due(agent))

    def test_a_league_that_has_never_been_surveyed_tries_every_half_hour_not_once_a_day(self):
        self.house.kalshi_data = type("K", (), {"market_data": type("M", (), {"markets": lambda self, **kw: {"markets": []}})()})()
        self.assertTrue(self.house.survey_due())
        self.house.survey_niches()  # nothing trading: no live universe came of it
        self.assertFalse(self.house.survey_due())
        self.clock.advance(1801)
        self.assertTrue(self.house.survey_due())


class Incentives(HouseCase):
    """Performance must buy things, and idleness must cost. The owner's rule for the expedition."""

    def test_an_agent_with_no_record_rewrites_itself_instead_of_waiting_to_afford_a_child(self):
        # Measured on the first evening: the six agents of the sports desk each saw 126 to 200 live
        # markets, found none inside the band they were born with, and so could not trade at all.
        from league.tests.test_house import BUYER

        agent = self.seated()
        self.assertTrue(self.house.record_is_empty(agent))
        better = BUYER.replace('"notional": 20.0', '"notional": 30.0')
        self.house.researcher = type("R", (), {"research": staticmethod(lambda agent, standing, session: type("P", (), {
            "candidate": {"code": better, "needs": agent.needs, "params": {"notional": 30.0}, "purpose": "the band was empty", "numbers": {}},
            "consulted": "", "cost_usd": D(0)})())})()
        self.house.research(agent)
        self.assertEqual(self.house.registry.get(agent.id).params["notional"], 30.0)
        self.assertEqual([a.id for a in self.house.registry.living()], [agent.id], "it rewrote itself, it did not breed")
        row = self.house.ledger.last("agent.strategy", agent=agent.id).payload
        self.assertIn("no record to protect", row["reason"])

    def test_once_it_has_a_record_a_candidate_is_a_child(self):
        from league.tests.test_house import BUYER

        agent = self.seated()
        self.house.tick()  # it buys, so its record is no longer empty
        self.assertFalse(self.house.record_is_empty(agent))
        better = BUYER.replace('"notional": 20.0', '"notional": 30.0')
        self.house.researcher = type("R", (), {"research": staticmethod(lambda agent, standing, session: type("P", (), {
            "candidate": {"code": better, "needs": agent.needs, "params": {"notional": 30.0}, "purpose": "a change", "numbers": {}},
            "consulted": "", "cost_usd": D(0)})())})()
        self.house.research(agent)
        self.assertEqual(self.house.registry.get(agent.id).params["notional"], 20.0, "its own file is untouched")
        self.assertEqual(len(self.house.registry.living()), 2)

    def test_an_idle_agent_earns_no_niche_floor(self):
        agent = self.seated()
        epoch = float(self.house.game["economy"]["epoch_seconds"])
        self.assertTrue(self.house.standings()[0].working, "too new to have had the chance")
        self.clock.advance(epoch + 1)
        self.assertFalse(self.house.standings()[0].working)
        self.assertEqual(self.house.economy.shares(self.house.standings(), "2.00"), {agent.id: D(0)})

    def test_a_resting_order_is_work_and_so_is_a_fill(self):
        agent = self.seated()
        self.house.tick()  # it buys
        self.clock.advance(float(self.house.game["economy"]["epoch_seconds"]) + 1)
        self.assertFalse(self.house.standings()[0].working, "a fill an epoch ago is not work now")
        self.house.books["alpaca-paper"].stake(agent.id, "0", note="touch")
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue", "side": "buy", "realized": None,
                                               "cash_delta": "-1.00", "position_delta": "0", "quantity": "0", "price": "1"}, agent=agent.id)
        self.assertTrue(self.house.standings()[0].working)


class CrashedReplays(HouseCase):
    """A replay the box could not run is a broken tool, not a hypothesis tested.

    Sept 19, 2026: three agents of the sports desk had their replays KILLED (exit 137) on a
    seven-week tape that exhausted the box, and each was charged a trial for it, which deflates
    every later replay in its line. Merton, hired by one of them, named it: "Exit 137 indicates
    process termination; it does not identify the cause."
    """

    def crashed(self, error):
        return {"ok": False, "error": error, "blocks": [], "trades": 0}

    def test_a_killed_or_timed_out_run_is_not_a_trial(self):
        for error in ("no result line (exit 137): Killed\n", "the box timed out after 600s", "no result line (exit 1): Traceback"):
            self.assertEqual(self.house._crashed(self.crashed(error)), error, error)

    def test_a_clean_exit_with_no_result_and_a_strategy_that_raised_are_the_strategys_own(self):
        self.assertEqual(self.house._crashed(self.crashed("no result line (exit 0): ")), "")
        self.assertEqual(self.house._crashed({"ok": True, "error": None}), "")
        self.assertEqual(self.house._crashed(self.crashed("decide raised ZeroDivisionError")), "")

    def test_the_agent_is_told_and_charged_nothing(self):
        agent = self.seated()
        self.house._state["tried"].pop(agent.id, None)  # it has not had its replay yet
        self.house._run_replay = lambda a, code, needs, params: (self.crashed("no result line (exit 137): Killed\n"), "tape")
        out = self.house._replay_own(agent)
        self.assertIn("could not be run", out["skipped"])
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=agent.id), 0)
        self.assertIn("not counted as a trial", self.house.ledger.last("ops.alert").payload["text"])
        answer = self.house._candidate_replay(agent, self.house.registry.get(agent.id).code)
        self.assertEqual((answer["passed"], self.house.ledger.count(kinds="eval.trial", agent=agent.id)), (False, 0))
        self.assertIn("NOT a trial against you", answer["error"])

    def test_a_daily_kalshi_tape_steps_by_the_half_hour_and_carries_fewer_markets(self):
        asked = {}

        class Kalshi:
            def tape(self, series, *, start, end, horizon, max_markets, step_seconds):
                asked.update(series=series, horizon=horizon, max_markets=max_markets, step_seconds=step_seconds)
                return {"venue": "kalshi", "horizon": horizon, "steps": [], "results": {}}

        self.house.kalshi_data = Kalshi()
        needs = {"venue": "kalshi", "horizon": "day", "style": "t", "series": ["KXNFLGAME"], "max_hours_to_close": 30}
        self.house.tape_for(needs)
        self.assertEqual((asked["step_seconds"], asked["max_markets"]), (1800, 500))
        self.house.tape_for({**needs, "horizon": "hour"})
        self.assertEqual((asked["step_seconds"], asked["max_markets"]), (300, 2000))


IDLER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-idler", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "nothing meets my rules"}
'''


class IdleHands(HouseCase):
    """An agent that cannot act is not learning, and the House should not leave it there."""

    def setUp(self):
        super().setUp()
        self.house.researcher = object()
        self.house.settings.research = True
        self.agent = self.seated("idler", IDLER)
        self.house.economy.grant(self.agent.id, D("5"), "a purse to research from")

    def wakes(self, n):
        for _ in range(n):
            self.house._state["next_wake"][self.agent.id] = 0
            self.house.wake(self.house.registry.get(self.agent.id))

    def test_a_wake_records_what_it_was_offered_and_what_it_did_with_it(self):
        self.wakes(1)
        woke = self.house.ledger.last("agent.woke").payload
        self.assertEqual((woke["intents"], woke["offered"], woke["barren"]), (0, 1, 1))
        self.assertEqual(self.house.idle_run(self.agent), {"barren": 1, "shut": 0, "offered": 1})

    def test_looking_at_a_live_market_and_doing_nothing_ten_times_brings_research_forward(self):
        self.wakes(9)
        self.assertEqual(self.house.research_interval_hours(self.agent), 3.0)
        self.assertEqual(self.house.idle_reason(self.agent), "")
        self.wakes(1)
        self.assertIn("not meeting this market", self.house.idle_reason(self.agent))
        self.assertEqual(self.house.research_interval_hours(self.agent), 1.0)
        self.assertEqual(self.house.research_interval_hours(), 3.0)  # only for the agent that is stuck

    def test_a_shut_market_is_bench_time_not_the_strategys_fault(self):
        """Friday night to Monday morning is sixty hours in which no equity desk can act. The run
        is counted apart from a barren one -- nothing was offered -- and it still buys a pass."""
        agent = self.seated("closed", IDLER.replace("test-idler", "test-closed"))
        self.house.economy.grant(agent.id, D("5"), "a purse")
        self.data.quotes = lambda symbols: {}
        for _ in range(6):
            self.house._state["next_wake"][agent.id] = 0
            self.house.wake(self.house.registry.get(agent.id))
        self.assertEqual(self.house.idle_run(agent), {"barren": 0, "shut": 6, "offered": 0})
        self.assertIn("bench time", self.house.idle_reason(agent))

    def test_an_equity_desk_out_of_hours_is_offered_nothing_however_stale_the_quote(self):
        """A quote still comes back at midnight; the session is what decides whether it can be hit."""
        import dataclasses

        agent = dataclasses.replace(self.seated("etfs", IDLER.replace("BTC/USD", "SPY")), specialty="alpaca-index-etfs")
        ctx = {"now": "2026-09-19T23:00:00Z", "quotes": {"SPY": {"bid": 1.0, "ask": 1.1}}}
        self.assertEqual(self.house._offered(agent, ctx), 0)
        self.assertEqual(self.house._offered(agent, {**ctx, "now": "2026-09-18T17:00:00Z"}), 1)

    def test_acting_clears_the_count(self):
        from league.tests.test_house import BUYER

        self.wakes(3)
        self.assertEqual(self.house.idle_run(self.agent)["barren"], 3)
        needs = {"venue": "alpaca", "horizon": "hour", "style": "test-buyer", "symbols": ["BTC/USD"], "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
        self.house.registry.adopt(self.agent.id, code=BUYER, needs=needs, params={"notional": 20.0}, reason="it found a rule that fires")
        self.house._state["tried"][self.agent.id] = self.house.registry.get(self.agent.id).code_sha256
        self.wakes(1)
        self.assertEqual(self.house.idle_run(self.agent), {"barren": 0, "shut": 0, "offered": 1})

    def test_the_brief_tells_a_stuck_agent_why_it_is_awake(self):
        from types import SimpleNamespace

        from league.researcher import Researcher

        state = Researcher._state(SimpleNamespace(journal=lambda _: [], specialty=None),
                                  SimpleNamespace(id="a1", family="f", niche="n", generation=1, code="x", params={}),
                                  {"idle": {"barren": 12, "why_now": "twelve wakes in a row and nothing done"}})
        self.assertIn("WHY YOU ARE AWAKE NOW: twelve wakes in a row and nothing done", state)
        self.assertNotIn("no record to protect", state)  # this one has a record; a change costs it a fork
        free = Researcher._state(SimpleNamespace(journal=lambda _: [], specialty=None),
                                 SimpleNamespace(id="a1", family="f", niche="n", generation=1, code="x", params={}),
                                 {"idle": {"why_now": "nine wakes and nothing done"}, "rewrites_in_place": True})
        self.assertIn("A pass that only reads and reasons has bought you nothing", free)
        self.assertNotIn("WHY YOU ARE AWAKE", Researcher._state(SimpleNamespace(journal=lambda _: [], specialty=None),
                                                                SimpleNamespace(id="a1", family="f", niche="n", generation=1, code="x", params={}), {}))

    def test_a_shut_market_does_not_starve_the_desk_that_trades_it(self):
        """Idleness costs; the calendar must not. A desk that would trade if its market were open
        keeps its niche floor over the weekend, and that floor is what pays for the weekend's work."""
        epoch = float(self.house.game["economy"]["epoch_seconds"])
        self.clock.advance(epoch * 2)
        self.assertFalse(self.house._working(self.agent, epoch))  # never traded, nothing offered yet
        self.house._note_wake(self.agent, acted=False, offered=3)
        self.assertFalse(self.house._working(self.agent, epoch))  # it looked at a live market and sat there
        self.house._note_wake(self.agent, acted=False, offered=0)
        self.assertFalse(self.house._working(self.agent, epoch))  # a barren run does not wash out
        self.house._note_wake(self.agent, acted=True, offered=0)
        self.house._note_wake(self.agent, acted=False, offered=0)
        self.assertTrue(self.house._working(self.agent, epoch))  # its market is simply shut

    def test_the_stuck_and_the_long_waiting_are_asked_before_the_comfortable(self):
        """The day's allowance, not the cadence, decides who researches; birth order must not."""
        others = [self.seated(name, IDLER) for name in ("aye", "bee", "cee")]
        self.house._state["last_research"] = {self.agent.id: 900.0, others[0].id: 100.0, others[1].id: 500.0, others[2].id: 300.0}
        self.assertEqual([a.id for a in self.house.research_order()],
                         [others[0].id, others[2].id, others[1].id, self.agent.id])
        self.wakes(10)  # now the one that researched most recently is the one that cannot act
        self.assertEqual(self.house.research_order()[0].id, self.agent.id)


    def test_an_agent_that_can_neither_trade_nor_afford_a_new_idea_dies(self):
        """Research stops at twice the minimum credits, so a barren agent would otherwise sit at
        that balance for as long as the floor runs: unable to act, unable to change, holding a seat
        on its desk. A shut market is the calendar, not the agent, and never counts here."""
        self.house.economy.charge(self.agent.id, self.house.economy.balance(self.agent.id) - D("0.15"), "test")
        self.wakes(29)
        self.house.keep_population()
        self.assertIn(self.agent.id, [a.id for a in self.house.registry.living()])
        self.wakes(1)
        self.house.keep_population()
        self.assertNotIn(self.agent.id, [a.id for a in self.house.registry.living()])
        self.assertIn("nothing done", self.house.ledger.last("agent.died", agent=self.agent.id).payload["detail"])

    def test_a_desk_whose_market_is_shut_is_not_killed_for_being_poor(self):
        rich = self.seated("bench", IDLER)
        self.house.economy.grant(rich.id, D("0.15"), "a thin purse")
        self.data.quotes = lambda symbols: {}
        for _ in range(40):
            self.house._state["next_wake"][rich.id] = 0
            self.house.wake(self.house.registry.get(rich.id))
        self.house.keep_population()
        self.assertIn(rich.id, [a.id for a in self.house.registry.living()])
