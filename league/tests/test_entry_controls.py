"""X1: agents can pause and size down (Sept 24, 2026, the close-the-gaps run; W2-house, never built).

Evidence. meriwether-h2d625d, a real bunt still adding 20-contract NO positions with $0.22 of cash,
three research sessions on Sept 23: "available tools cannot pause this active rule ... Escalate to
House/operator to halt new entries". huang-l23cdb7, $8.89 above its death line: "halving notional
(16->8) ... FAILED the gate, so I cannot adopt a smaller size", and its 16-contract taker fade kept
trading. On the T0 snapshot 555 research texts (95 agents) were about sizing, minimums and caps.

`pause_entries`, `resume_entries` and `edit_params` (league/researcher.py) record a request; the
House applies it when the pass ends (`House._apply_controls`) as an `agent.strategy` row with what it
replaced (`was`). A paused agent's buys are held at every wake and its resting buys cancelled, while
its sells, cancels and settlements go on. An edit changes numeric PARAMS inside their bounds, in
place, after the House's replay of the edit at half notional passes; that replay is no trial against
the line and never touches the holdout. Neither raises a limit, a stake or a band.
"""

from decimal import Decimal

from league.tests.test_house import BUYER, HouseCase
from league.tests.test_order_guards import RESTER

D = Decimal

#: The House tests' sawtooth, sized by a knob, with a frozen window and a knob that is not a number.
SIZED = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "sized-sawtooth", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 5}, "wake_minutes": 5,
         "parameter_rules": {"frozen": ["lookback"]}}
PARAMS = {"notional_usd": 30.0, "lookback": 5, "mode": "sawtooth"}

def decide(ctx):
    p = ctx["params"]
    bars = ctx["bars"].get("BTC/USD") or []
    if not bars:
        return {"intents": [], "thought": "no bars"}
    low = bars[-1]["c"] < 80000
    held = [x for x in ctx["positions"] if x["symbol"] == "BTC/USD"]
    if low and not held:
        return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": p["notional_usd"], "type": "market", "reason": "low"}],
                "thought": "buy low"}
    if held and not low:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "high"}],
                "thought": "sell high"}
    return {"intents": [], "thought": "wait"}
'''


class ControlCase(HouseCase):
    def request(self, agent, control, *, session="s1", n=0, note="the live rule keeps adding losing positions", **payload):
        """What the researcher's tool writes (`Researcher._request_control`)."""
        self.house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": control, "session": session,
                                                    "note": note, **payload}, agent=agent.id, id=f"control-request:{session}:{n}")

    def apply(self, agent, control, **kw):
        self.request(agent, control, **kw)
        return self.house._apply_controls(agent.id, kw.get("session", "s1"))

    def strategy_rows(self, agent):
        return [e.payload for e in self.house.ledger.iter(kinds="agent.strategy", agent=agent.id)]

    def not_applied(self, agent):
        return [e.payload["reason"] for e in self.house.ledger.iter(kinds="agent.research", agent=agent.id)
                if e.payload.get("tool") == "control" and e.payload.get("status") == "not_applied"]


class PauseAndResume(ControlCase):
    def test_the_pause_is_an_agent_strategy_row_with_what_it_replaced(self):
        agent = self.seated()
        self.assertEqual(self.apply(agent, "pause_entries"), ["pause_entries"])
        (row,) = self.strategy_rows(agent)
        self.assertEqual({k: row[k] for k in ("control", "entries", "was", "note", "session", "code_sha256", "params", "needs")},
                         {"control": "pause_entries", "entries": "paused", "was": {"entries": "open"},
                          "note": "the live rule keeps adding losing positions", "session": "s1", "code_sha256": agent.code_sha256,
                          "params": agent.params, "needs": agent.needs})
        current = self.house.registry.get(agent.id)
        self.assertEqual((current.code, current.params), (agent.code, agent.params))  # the strategy in force is unchanged
        self.assertEqual(self.house.registry.entries_paused(agent.id)["note"], "the live rule keeps adding losing positions")

    def test_a_paused_agents_buys_are_held_and_nothing_is_refused(self):
        agent = self.seated()  # buys when flat
        self.apply(agent, "pause_entries")
        self.house.tick()
        self.assertEqual(self.broker.submitted, [])
        self.assertIsNone(self.house.ledger.last("book.refused", agent=agent.id))  # a refusal row would buy a research pass
        woke = self.house.ledger.last("agent.woke", agent=agent.id).payload
        self.assertEqual((woke["intents"], woke["held"]), (0, 1))
        self.assertEqual(self.house.idle_run(agent)["barren"], 0)  # its rules fired: it is not idle

    def test_its_exits_go_on(self):
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.apply(agent, "pause_entries")
        self.clock.advance(301)
        self.house.tick()  # it sells what it holds
        self.assertEqual(book.account(agent.id).holdings, {})

    def test_its_resting_buys_are_cancelled_at_its_next_wake(self):
        agent = self.seated("rester", RESTER)
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        (order,) = book.open_orders(agent.id)
        self.apply(agent, "pause_entries")
        self.clock.advance(301)
        self.house.tick()
        self.assertEqual(book.open_orders(agent.id), [])
        cancel = self.house.ledger.last("book.cancel", agent=agent.id)
        self.assertIsNotNone(cancel)

    def test_resume_lets_its_entries_through_again(self):
        agent = self.seated()
        self.apply(agent, "pause_entries")
        self.house.tick()
        self.assertEqual(self.broker.submitted, [])
        self.assertEqual(self.apply(agent, "resume_entries", session="s2"), ["resume_entries"])
        self.assertIsNone(self.house.registry.entries_paused(agent.id))
        self.assertEqual(self.strategy_rows(agent)[-1]["was"]["entries"], "paused")
        self.clock.advance(301)
        self.house.tick()
        self.assertIn(self.btc.key, self.house.books["alpaca-paper"].account(agent.id).holdings)

    def test_a_wake_decided_before_the_pause_is_not_submitted_after_it(self):
        agent = self.seated()
        out = self.house.wake(agent)
        self.assertEqual(len(out["intents"]), 1)
        self.apply(agent, "pause_entries")
        self.assertEqual(self.house._submit_wakes("alpaca-paper", [out]), [])

    def test_applying_again_changes_nothing_and_a_pause_while_paused_is_said_so(self):
        agent = self.seated()
        self.apply(agent, "pause_entries")
        self.assertEqual(self.house._apply_controls(agent.id, "s1"), [])  # after a restart: already applied
        self.assertEqual(self.apply(agent, "pause_entries", session="s2"), [])
        self.assertEqual(len(self.strategy_rows(agent)), 1)
        self.assertIn("already paused", self.not_applied(agent)[0])

    def test_no_control_is_recorded_while_an_audit_runs_or_a_veto_stands(self):
        agent = self.seated()
        with self.house._state_lock:
            self.house._state.setdefault(self.house.AUDITS, {})[agent.id] = {"generation": [], "since_seq": 0}
        self.assertEqual(self.apply(agent, "pause_entries"), [])
        self.assertIn("an audit of your strategy is under way", self.not_applied(agent)[0])
        self.house._drop_audit(agent.id)
        self.house.ledger.append("audit.verdict", {"approve": False, "summary": "a test veto"}, agent=agent.id)
        self.assertEqual(self.apply(agent, "pause_entries", session="s2"), [])
        self.assertIn("vetoed", self.not_applied(agent)[1])
        self.assertEqual(self.strategy_rows(agent), [])  # a control row would read as new code and set the veto aside

    def test_a_control_row_keeps_the_reason_the_strategy_was_adopted(self):
        agent = self.seated()
        self.house.registry.adopt(agent.id, code=agent.code, needs=agent.needs, params=agent.params, reason="favourites above 90 cents")
        self.apply(agent, "pause_entries")
        row = self.strategy_rows(agent)[-1]
        self.assertEqual((row["reason"], row["note"]), ("favourites above 90 cents", "the live rule keeps adding losing positions"))

    def test_the_standing_shows_the_pause_and_what_it_held(self):
        agent = self.seated()
        self.apply(agent, "pause_entries")
        self.house.tick()
        entries = self.house._research_standing(agent)["entries"]
        self.assertEqual((entries["state"], entries["held_since_pause"], entries["note"]),
                         ("paused", 1, "the live rule keeps adding losing positions"))


class InPlaceEdit(ControlCase):
    def setUp(self):
        super().setUp()
        self.agent = self.seated("sized", SIZED)
        self.replays = []
        replay = self.house.sandbox.replay

        def counted(agent, code, params, tape, *, stake, limits, timeout=600):
            self.replays.append({"params": dict(params), "stake": stake, "limits": dict(limits)})
            return replay(agent, code, params, tape, stake=stake, limits=limits, timeout=timeout)

        self.house.sandbox.replay = counted

    def edit(self, changes, **kw):
        return self.house._edit_replay(self.house.registry.get(self.agent.id), changes, session=kw.get("session", "s1"))

    def test_an_edit_is_replayed_at_half_notional_and_is_no_trial(self):
        trials = self.house.ledger.count(kinds="eval.trial", agent=self.agent.id)
        result = self.edit({"notional_usd": 20})
        self.assertTrue(result["passed"], result)
        self.assertEqual((result["params"], result["was"]), ({"notional_usd": 20.0, "lookback": 5, "mode": "sawtooth"},
                                                             {"notional_usd": 30.0, "lookback": 5, "mode": "sawtooth"}))
        (replay,) = self.replays
        self.assertEqual((replay["params"]["notional_usd"], replay["stake"], replay["limits"]),
                         (20.0, 100.0, {"max_position_usd": 50.0, "max_order_usd": 37.5}))
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=self.agent.id), trials)
        look = self.house.ledger.last("agent.research", agent=self.agent.id).payload
        self.assertEqual((look["tool"], look["passed"], look["session"]), ("edit_replay", True, "s1"))

    def test_a_passed_edit_takes_effect_when_the_pass_ends(self):
        result = self.edit({"notional_usd": 20})
        self.assertEqual(self.apply(self.agent, "edit_params", params=result["params"], was=result["was"],
                                    code_sha256=result["code_sha256"], replay=result["numbers"]), ["edit_params"])
        (row,) = self.strategy_rows(self.agent)
        self.assertEqual({k: row[k] for k in ("control", "params", "was", "code_sha256")},
                         {"control": "edit_params", "params": result["params"], "was": {"params": result["was"]},
                          "code_sha256": self.agent.code_sha256})
        current = self.house.registry.get(self.agent.id)
        self.assertEqual((current.params["notional_usd"], current.code), (20.0, self.agent.code))
        self.assertEqual(self.house.snapshot(current, self.house.books["alpaca-paper"])["params"]["notional_usd"], 20.0)
        self.assertEqual(self.house.evaluator.rung(self.agent.id), 1)  # the seat is kept

    def test_an_edit_whose_replay_fails_is_not_made(self):
        result = self.edit({"notional_usd": 45})  # over the half-notional order cap: nothing trades
        self.assertFalse(result["passed"])
        self.assertTrue(result["reasons"])
        # Asked for anyway, it is not made: only the House's record of a PASSING replay makes an edit.
        self.assertEqual(self.apply(self.agent, "edit_params", params=result["params"], was=result["was"],
                                    code_sha256=result["code_sha256"]), [])
        forged = {**self.agent.params, "notional_usd": 5.0}
        self.assertEqual(self.apply(self.agent, "edit_params", n=1, params=forged, was=self.agent.params,
                                    code_sha256=self.agent.code_sha256), [])
        self.assertEqual([reason[:36] for reason in self.not_applied(self.agent)], ["no passing replay of this edit is on"] * 2)
        self.assertEqual(self.house.registry.get(self.agent.id).params["notional_usd"], 30.0)

    def test_what_an_edit_may_not_touch(self):
        for changes, words in (({"unknown": 1}, "not one of your PARAMS"), ({"lookback": 4}, "not a bounded, unfrozen numeric knob"),
                               ({"mode": "trend"}, "not a bounded, unfrozen numeric knob"), ({"notional_usd": -5}, "outside"),
                               ({"notional_usd": True}, "must be a number"), ({"notional_usd": 30}, "nothing changed")):
            self.assertIn(words, self.edit(changes).get("error", ""), changes)
        self.assertEqual(self.replays, [])  # refused before any replay

    def test_rung_zero_edits_by_replay_not_in_place(self):
        self.house.evaluator.seat(self.agent.id, 0, "test")
        self.assertIn("rung 0", self.edit({"notional_usd": 20})["error"])

    def test_one_edit_replay_a_day_passed_or_not(self):
        self.edit({"notional_usd": 45})
        self.assertIn("a day", self.edit({"notional_usd": 20})["error"])
        self.clock.advance(24 * 3600 + 1)
        self.assertIn("passed", self.edit({"notional_usd": 20}))

    def test_an_edit_replayed_before_its_strategy_changed_is_not_applied(self):
        result = self.edit({"notional_usd": 20})
        self.apply(self.agent, "pause_entries", n=0)  # a pause does not change the strategy
        self.house.registry.adopt(self.agent.id, code=self.agent.code, needs=self.agent.needs,
                                  params={**self.agent.params, "notional_usd": 25.0}, reason="another change")
        self.assertEqual(self.apply(self.agent, "edit_params", n=1, params=result["params"], was=result["was"],
                                    code_sha256=result["code_sha256"]), [])
        self.assertIn("changed after the edit was replayed", self.not_applied(self.agent)[0])
        self.assertEqual(self.house.registry.get(self.agent.id).params["notional_usd"], 25.0)


if __name__ == "__main__":
    import unittest

    unittest.main()
