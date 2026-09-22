"""The pre-audit: a cheap look at a paper agent's code and first wakes that REPORTS a broken
strategy (repair.reported, strategy_defect, source audit) and never judges it."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from league.agents import Agent
from league.ledger import Ledger
from league.preaudit import PREAUDIT_STATE_KEY, PreAudit, cent_roundings, mark_of
from league.tests.fakes import Clock

#: What haghani ran on paper when the auditor vetoed it (audit.verdict seq 123905, Sept 22, 2026):
#: the buy target and the exit are rounded to cents on a desk that trades DOGE and XRP.
HAGHANI = '''
NEEDS = {'venue': 'alpaca', 'horizon': 'hour', 'style': 'maker-reversion',
 'symbols': ['SOL/USD', 'XRP/USD', 'DOGE/USD'], 'bars': {'timeframe': '15Min', 'limit': 64}}

def decide(ctx):
    intents = []
    for symbol in NEEDS["symbols"]:
        mean, atr, k, edge_pct = 0.1, 0.01, 1.0, 0.8
        position = ctx["positions"].get(symbol)
        if position:
            intents.append({"symbol": symbol, "side": "sell", "quantity": position["quantity"], "type": "limit", "limit_price": round(mean, 2)})
            continue
        target = round(min(mean - k * atr, mean * (1.0 - edge_pct / 100.0)), 2)
        intents.append({"symbol": symbol, "side": "buy", "quantity": 10, "type": "limit", "limit_price": target})
    return {"intents": intents}
'''

PRECISE = '''
NEEDS = {'venue': 'alpaca', 'horizon': 'hour', 'style': 'maker-reversion', 'symbols': ['DOGE/USD']}

def decide(ctx):
    quantity = round(ctx["cash"] / 0.1, 2)
    target = round(0.1 * 0.99, 6)
    qty = round(3.14159, 2)
    return {"intents": [{"symbol": "DOGE/USD", "side": "buy", "quantity": qty, "type": "limit", "limit_price": target}]}
'''

CLEAN = '''
NEEDS = {'venue': 'alpaca', 'horizon': 'hour', 'style': 'momentum', 'symbols': ['SPY']}

def decide(ctx):
    return {"intents": []}
'''


def agent(agent_id: str, code: str, *, venue: str = "alpaca", symbols=("DOGE/USD", "XRP/USD")) -> Agent:
    return Agent(id=agent_id, name=agent_id, family=agent_id, venue=venue, horizon="hour", style="maker-reversion", generation=1,
                 parent=None, code=code, params={}, wake_minutes=15, born_at="2026-09-20T00:00:00Z",
                 needs={"venue": venue, "horizon": "hour", "symbols": list(symbols)})


class Registry:
    def __init__(self, agents):
        self.agents = {a.id: a for a in agents}
        self.killed = []

    def living(self):
        return [a for a in self.agents.values() if a.alive]

    def kill(self, *args, **kwargs):  # the pre-audit must never call it
        self.killed.append(args)


class Evaluator:
    def __init__(self, rungs, entered):
        self.rungs, self.entered = dict(rungs), dict(entered)
        self.calls = []

    def rung(self, agent_id):
        if self.rungs.get(agent_id) == "boom":
            raise RuntimeError("an unreadable record")
        return self.rungs.get(agent_id, 0)

    def _rung_entered(self, agent_id):
        return self.entered.get(agent_id, 0)

    def __getattr__(self, name):  # promote, demote, judge, record_trial ...: any of them is a failure
        def called(*args, **kwargs):
            self.calls.append(name)
        return called


class Book:
    name = "alpaca-paper"


class House:
    def __init__(self, ledger, agents, rungs=None, entered=None):
        self.ledger = ledger
        self.registry = Registry(agents)
        self.evaluator = Evaluator(rungs or {a.id: 1 for a in agents}, entered or {})
        self._state = {"promotion_status": {}}
        self._state_lock = threading.RLock()

    def book_of(self, agent):
        return Book()


class PreAuditTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.ledger.append("ops.started", {"release": "test"})

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def woke(self, agent_id, n, **payload):
        for _ in range(n):
            self.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "dropped": [], "cancels": 0, "offered": 3, **payload},
                               agent=agent_id)

    def reports(self):
        return list(self.ledger.iter(kinds="repair.reported"))

    # ------------------------------------------------------------------ the code
    def test_the_haghani_cent_rounding_is_found_by_line(self):
        found = cent_roundings(HAGHANI)
        self.assertEqual([line for line, _ in found], [11, 13])
        self.assertIn("round(mean, 2)", found[0][1])
        self.assertIn("target = round(", found[1][1])

    def test_quantities_and_instrument_precision_are_not_cent_rounding(self):
        self.assertEqual(cent_roundings(PRECISE), [])
        self.assertEqual(cent_roundings("x = Decimal(q).quantize(Decimal('0.000001'))\nprice = p.quantize(Decimal('0.0001'))"), [])
        self.assertEqual([line for line, _ in cent_roundings("limit = p.quantize(Decimal('0.01'))")], [1])
        self.assertEqual(cent_roundings("def broken(:\n"), [])

    def test_a_cent_rounding_desk_is_reported_at_rung_entry_without_a_wake(self):
        haghani = agent("haghani", HAGHANI)
        house = House(self.ledger, [haghani])
        house._state["promotion_status"]["haghani"] = {"stage": "evidence", "code_sha256": haghani.code_sha256}
        results = PreAudit(self.ledger, clock=self.clock).run(house)
        self.assertEqual(results[0]["flags"], ["cent_rounding"])
        rows = self.reports()
        self.assertEqual(len(rows), 1)
        payload = rows[0].payload
        self.assertEqual(set(payload), {"key", "kind", "summary", "evidence", "agents", "source", "severity"})
        self.assertEqual((payload["kind"], payload["source"], payload["severity"]), ("strategy_defect", "audit", "high"))
        self.assertEqual(payload["key"], f"strategy_defect:haghani:{haghani.code_sha256[:12]}")
        self.assertEqual(payload["agents"], ["haghani"])
        self.assertEqual(rows[0].agent, "haghani")
        self.assertTrue(all(set(e) == {"seq", "at", "agent", "excerpt"} for e in payload["evidence"]))
        self.assertIn("line 13", " ".join(e["excerpt"] for e in payload["evidence"]))
        mark = mark_of(house._state, haghani)
        self.assertEqual((mark["verdict"], mark["final"], mark["repair_key"]), ("red", False, payload["key"]))
        self.assertEqual(house._state["promotion_status"]["haghani"]["pre_audit"]["verdict"], "red")

    def test_kalshi_cents_are_the_tick_and_not_a_defect(self):
        maker = agent("wti", "def decide(ctx):\n    price = round(ctx['bid'] + 0.01, 2)\n    return {}\n", venue="kalshi", symbols=())
        house = House(self.ledger, [maker])
        self.assertEqual(PreAudit(self.ledger, clock=self.clock).run(house)[0]["flags"], [])
        self.assertEqual(self.reports(), [])

    def test_cent_rounding_on_dollar_stocks_is_left_alone_unless_it_fills_under_a_dollar(self):
        spy = agent("spy", "def decide(ctx):\n    target = round(ctx['mean'] * 0.99, 2)\n    return {}\n", symbols=("SPY",))
        house = House(self.ledger, [spy])
        audit = PreAudit(self.ledger, clock=self.clock)
        self.assertEqual(audit.run(house)[0]["flags"], [])
        house._state.pop(PREAUDIT_STATE_KEY)
        self.ledger.append("book.fill", {"book": "alpaca-paper", "side": "buy", "price": "0.42", "quantity": "10",
                                         "instrument": {"asset_class": "equity", "symbol": "PENNY"}}, agent="spy")
        self.assertEqual(audit.run(house)[0]["flags"], ["cent_rounding"])

    def test_an_option_premium_under_a_dollar_is_priced_in_cents_and_not_a_defect(self):
        calls = agent("calls", "def decide(ctx):\n    price = round(ctx['mark'], 2)\n    return {}\n", symbols=("SPY",))
        self.ledger.append("book.fill", {"book": "alpaca-paper", "side": "buy", "price": "0.45", "quantity": "1",
                                         "instrument": {"asset_class": "option", "symbol": "SPY260930C00650000"}}, agent="calls")
        self.assertEqual(PreAudit(self.ledger, clock=self.clock).run(House(self.ledger, [calls]))[0]["flags"], [])

    # -------------------------------------------------------------- the behaviour
    def test_errors_and_dropped_intents_after_the_first_wakes_are_reported_and_nobody_dies(self):
        broken = agent("broken", CLEAN, symbols=("SPY",))
        house = House(self.ledger, [broken])
        audit = PreAudit(self.ledger, clock=self.clock)
        self.woke("broken", 2)
        self.assertEqual(audit.run(house)[0]["final"], False)  # too few wakes to judge the behaviour yet
        self.assertEqual(self.reports(), [])
        for _ in range(3):
            self.ledger.append("agent.woke", {"ok": False, "error": "KeyError: 'bars'", "book": "alpaca-paper"}, agent="broken")
        self.woke("broken", 1, intents=1, dropped=["ValueError: no price to size the order at"])
        head = self.ledger.head()[0]
        result = audit.run(house)[0]
        self.assertTrue(result["final"])
        self.assertEqual(result["flags"], ["errors", "dropped_intents"])
        rows = self.reports()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].payload["severity"], "high")
        self.assertIn("KeyError", " ".join(e["excerpt"] for e in rows[0].payload["evidence"]))
        self.assertIn("3 raised (50%)", rows[0].payload["summary"])
        # A report, never a verdict: nothing but the one report was written, and nobody was judged.
        self.assertEqual([e.kind for e in self.ledger.iter(after=head)], ["repair.reported"])
        self.assertEqual(house.registry.killed, [])
        self.assertEqual(house.evaluator.calls, [])
        self.assertTrue(broken.alive)

    def test_refusals_count_only_when_they_are_the_strategys_doing(self):
        refused = agent("refused", CLEAN, symbols=("SPY",))
        house = House(self.ledger, [refused])
        self.woke("refused", 6, intents=1)
        for n in range(4):
            self.ledger.append("book.refused", {"book": "alpaca-paper", "intent_id": f"p{n}", "reasons": ["the House is paused for maintenance: exits and cancels only"]},
                               agent="refused")
        audit = PreAudit(self.ledger, clock=self.clock)
        self.assertEqual(audit.run(house)[0]["flags"], [])
        house._state.pop(PREAUDIT_STATE_KEY)
        for n in range(4):
            self.ledger.append("book.refused", {"book": "alpaca-paper", "intent_id": f"r{n}", "reasons": ["the order is above the $10 entry cap"]},
                               agent="refused")
        self.assertEqual(audit.run(house)[0]["flags"], ["refusals"])

    def test_a_desk_that_never_acts_on_a_live_market_is_barren_but_a_trader_is_not(self):
        idle, trader = agent("idle", CLEAN, symbols=("SPY",)), agent("trader", CLEAN, symbols=("SPY",))
        house = House(self.ledger, [idle, trader])
        for n in range(1, 7):
            self.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "dropped": [], "cancels": 0, "offered": 5, "barren": n}, agent="idle")
            self.ledger.append("agent.woke", {"ok": True, "book": "alpaca-paper", "intents": 0, "dropped": [], "cancels": 0, "offered": 5, "barren": n}, agent="trader")
        self.ledger.append("book.fill", {"book": "alpaca-paper", "side": "buy", "price": "650", "quantity": "0.01",
                                         "instrument": {"asset_class": "equity", "symbol": "SPY"}}, agent="trader")
        results = {r["agent"]: r for r in PreAudit(self.ledger, clock=self.clock).run(house)}
        self.assertEqual(results["idle"]["flags"], ["barren"])
        self.assertEqual(results["trader"]["flags"], [])
        self.assertEqual([r.payload["severity"] for r in self.reports()], ["medium"])

    def test_a_clean_agent_is_marked_clear_and_reported_nowhere(self):
        clean = agent("clean", CLEAN, symbols=("SPY",))
        house = House(self.ledger, [clean])
        self.woke("clean", 6, offered=0)
        result = PreAudit(self.ledger, clock=self.clock).run(house)[0]
        self.assertEqual((result["verdict"], result["final"], result["repair_key"]), ("clear", True, None))
        self.assertEqual(mark_of(house._state, clean)["verdict"], "clear")
        self.assertEqual(self.reports(), [])

    # ------------------------------------------------------------ once, and again
    def test_running_twice_reports_once_and_a_final_look_adds_only_new_findings(self):
        haghani = agent("haghani", HAGHANI)
        house = House(self.ledger, [haghani])
        audit = PreAudit(self.ledger, clock=self.clock)
        audit.run(house)
        audit.run(house)
        self.assertEqual(len(self.reports()), 1)
        self.woke("haghani", 6, offered=0)
        self.assertTrue(audit.run(house)[0]["final"])
        self.assertEqual(len(self.reports()), 1)  # the same finding at the final look is not reported twice
        self.assertEqual(audit.run(house), [])  # a final mark is not looked at again until the recheck is due
        # A restart that lost the mark cannot duplicate the report either: the ledger rows hold it.
        house._state.pop(PREAUDIT_STATE_KEY)
        audit.run(house)
        self.assertEqual(len(self.reports()), 1)

    def test_a_final_look_is_repeated_and_reports_only_what_is_new(self):
        """The first behaviour look can come before any market was open: six wakes with nothing on
        offer cannot show a barren desk. Measured on the review of PR #93, Sept 22, 2026: without a
        second look such a desk was never flagged, however many barren wakes followed."""
        idle = agent("idle", CLEAN)
        house = House(self.ledger, [idle])
        audit = PreAudit(self.ledger, clock=self.clock)
        self.woke("idle", 6, offered=0)
        self.assertEqual(audit.run(house)[0]["flags"], [])
        self.woke("idle", 8, offered=3, barren=True)
        self.assertEqual(audit.run(house), [])  # not before the recheck is due
        self.clock.advance(6 * 3600)
        result = audit.run(house)[0]
        self.assertEqual(result["flags"], ["barren"])
        self.assertEqual(len(self.reports()), 1)
        self.clock.advance(6 * 3600)
        audit.run(house)
        self.assertEqual(len(self.reports()), 1)  # the same finding again is not a new report

    def test_new_code_is_checked_again_under_its_own_key(self):
        haghani = agent("haghani", HAGHANI)
        house = House(self.ledger, [haghani])
        audit = PreAudit(self.ledger, clock=self.clock)
        audit.run(house)
        old_key = self.reports()[0].payload["key"]
        haghani.code = HAGHANI.replace("0.8", "1.2")
        self.assertIsNone(mark_of(house._state, haghani))
        audit.run(house)
        keys = [r.payload["key"] for r in self.reports()]
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[1], old_key)
        self.assertEqual(keys[1], f"strategy_defect:haghani:{haghani.code_sha256[:12]}")

    # -------------------------------------------------------------- the bounds
    def test_only_paper_agents_are_looked_at_the_pass_is_bounded_and_one_bad_record_is_skipped(self):
        agents = [agent(f"a{n}", CLEAN, symbols=("SPY",)) for n in range(5)]
        rungs = {"a0": 0, "a1": 2, "a2": "boom", "a3": 1, "a4": 1}
        house = House(self.ledger, agents, rungs=rungs)
        results = PreAudit(self.ledger, clock=self.clock, settings={"max_agents_per_run": 1}).run(house)
        self.assertEqual([r["agent"] for r in results], ["a2", "a3"])
        self.assertIn("skipped", results[0])
        self.assertEqual(sorted(house._state[PREAUDIT_STATE_KEY]), ["a3"])

    def test_due_follows_the_interval_and_the_switch(self):
        audit = PreAudit(self.ledger, clock=self.clock, settings={"every_seconds": 600})
        self.assertTrue(audit.due())
        audit.run(House(self.ledger, []))
        self.assertFalse(audit.due())
        self.clock.advance(600)
        self.assertTrue(audit.due())
        off = PreAudit(self.ledger, clock=self.clock, settings={"enabled": False})
        self.assertFalse(off.due())
        self.assertEqual(off.run(House(self.ledger, [agent("x", HAGHANI)])), [])

    def test_the_model_check_is_off_unless_handed_in(self):
        haghani = agent("haghani", HAGHANI)
        asked = []
        audit = PreAudit(self.ledger, clock=self.clock, escalate=lambda a, flags: asked.append(flags) or {"note": "confirmed"})
        audit.run(House(self.ledger, [haghani]))
        self.assertEqual(asked, [["cent_rounding"]])
        self.assertIn("Model check: confirmed", self.reports()[0].payload["summary"])
        self.assertIsNone(PreAudit(self.ledger).escalate)


if __name__ == "__main__":
    unittest.main()
