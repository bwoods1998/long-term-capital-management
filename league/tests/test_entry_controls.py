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

from league import allocator as allocator_module
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
        self.assertEqual(self.house.idle_run(agent)["barren"], 1)  # held buys are not activity (review of #249, P3)

    def test_a_paused_desk_is_not_called_quiet(self):
        """Review of #249: held buys read as "no agent of the desk wrote an intent ... its rules are not
        firing" to the floor's quiet-desk invariant, a false warning for a desk whose agents paused."""
        agent = self.seated()
        self.apply(agent, "pause_entries")
        for _ in range(13):
            self.house.tick()
            self.clock.advance(301)
        self.house._state.setdefault("invariants", {})["at"] = 0
        self.house._floor_invariants()
        self.assertEqual([e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert")
                          if "no agent of the desk wrote an intent" in str(e.payload.get("text"))], [])

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

    def test_its_resting_buys_are_cancelled_when_the_pause_is_made(self):
        """Review of #249: they waited for its next wake, `wake_minutes` away (a day for a daily agent),
        and a bid that filled meanwhile was an entry after the pause."""
        agent = self.seated("rester", RESTER.replace('"wake_minutes": 5', '"wake_minutes": 1440'))
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        (order,) = book.open_orders(agent.id)
        self.apply(agent, "pause_entries")
        self.assertEqual(book.open_orders(agent.id), [])
        self.assertIn(order.order_id, [e.payload.get("order_id") for e in self.house.ledger.iter(kinds="book.cancel", agent=agent.id)])
        self.assertEqual(book.account(agent.id).holdings, {})

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

    def test_no_edit_is_recorded_while_an_audit_runs_or_a_veto_stands(self):
        agent = self.seated()
        edit = dict(params={**agent.params, "notional": 10.0}, was=agent.params, code_sha256=agent.code_sha256)
        with self.house._state_lock:
            self.house._state.setdefault(self.house.AUDITS, {})[agent.id] = {"generation": [], "since_seq": 0}
        self.assertEqual(self.apply(agent, "edit_params", **edit), [])
        self.assertIn("an audit of your strategy is under way", self.not_applied(agent)[0])
        self.house._drop_audit(agent.id)
        self.house.ledger.append("audit.verdict", {"approve": False, "summary": "a test veto"}, agent=agent.id)
        self.assertEqual(self.apply(agent, "edit_params", session="s2", **edit), [])
        self.assertIn("vetoed", self.not_applied(agent)[1])
        self.assertEqual(self.strategy_rows(agent), [])  # an edit would read as new code and set the veto aside

    def test_a_vetoed_or_audited_agent_can_still_hold_its_entries(self):
        """Review of #249: a pause was refused under a veto, so a real bunt whose swing audit was vetoed
        could never hold its own entries. A pause restates its strategy: the veto still stands after it."""
        agent = self.seated()
        self.house.ledger.append("audit.verdict", {"approve": False, "summary": "a veto of its swing"}, agent=agent.id)
        self.assertEqual(self.apply(agent, "pause_entries"), ["pause_entries"])
        self.assertEqual(allocator_module.audit_standing(self.house, agent), "vetoed")
        with self.house._state_lock:
            self.house._state.setdefault(self.house.AUDITS, {})[agent.id] = {"generation": [], "since_seq": 0}
        self.assertEqual(self.apply(agent, "resume_entries", session="s2"), ["resume_entries"])
        self.assertEqual(self.not_applied(agent), [])

    def test_a_pause_sets_no_approval_aside_and_moves_no_generation(self):
        """Review of #249: a pause or resume row read as new code. It set an audit's approval aside (so an
        approved agent was audited again before its swing) and moved the generation an audit in flight,
        a promotion and a death are keyed to."""
        agent = self.seated()
        self.house.ledger.append("audit.verdict", {"approve": True, "summary": "approved"}, agent=agent.id)
        generation = self.house._generation(agent.id)
        self.apply(agent, "pause_entries")
        self.apply(agent, "resume_entries", session="s2")
        self.assertEqual(len(self.strategy_rows(agent)), 2)
        self.assertEqual(allocator_module.audit_standing(self.house, agent), "approved")
        self.assertEqual(self.house._generation(agent.id), generation)

    def test_a_pause_does_not_cancel_its_own_candidate_waiting_for_a_seat(self):
        """Review of #249: a replay-passed candidate waiting for a seat is admitted only while its author's
        generation stands, and a pause moved it: the admission was cancelled ("parent retired or changed")."""
        from league.admissions import Admissions

        agent = self.seated()
        queue = Admissions(self.house.ledger)
        candidate = {"passed": True, "params": dict(agent.params), "needs": dict(agent.needs), "code": agent.code,
                     "purpose": "a replay-passing candidate waiting for a seat"}
        row = queue.enqueue(agent.id, self.house._generation(agent.id), candidate, "s0")
        queue.record(row, "deferred", "niche is full; waiting for an eligible seat")
        self.apply(agent, "pause_entries")
        (waiting,) = [r for r in queue.pending() if r["session"] == "s0"]
        self.house._admission_gate(waiting)
        (after,) = [r for r in queue.rows() if r["session"] == "s0"]
        self.assertNotEqual(after["status"], "cancelled", after.get("reason"))

    def test_a_sell_decided_before_the_pause_still_goes(self):
        agent = self.seated()
        self.house.tick()  # it buys
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.clock.advance(301)
        out = self.house.wake(agent)  # it decides to sell
        self.assertEqual([i.side for i in out["intents"]], ["sell"])
        self.apply(agent, "pause_entries")
        self.house._submit_wakes("alpaca-paper", [out])
        self.assertEqual(book.account(agent.id).holdings, {})

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

    def test_one_edit_replay_a_day_however_busy_its_record(self):
        """Review of #249: the day's look was sought in the agent's newest 400 research rows. On the T0
        snapshot 26 of 487 agents wrote 400 inside a day (meriwether-37 in 2.8 hours: 515 admission
        rows a day), and a second edit replay ran three hours after the first."""
        self.edit({"notional_usd": 45})
        for n in range(400):
            self.house.ledger.append("agent.research", {"tool": "candidate_admission", "session": f"q{n}", "status": "deferred",
                                                        "reason": f"waiting {n}"}, agent=self.agent.id)
        self.clock.advance(3 * 3600)
        self.assertIn("a day", self.edit({"notional_usd": 20}).get("error", ""))
        self.assertEqual(len(self.replays), 1)
        standing = self.house._research_standing(self.house.registry.get(self.agent.id))["entries"]
        self.assertFalse(standing["last_edit_replay"]["passed"])

    def test_every_edit_look_of_the_line_is_a_try_in_the_deflation(self):
        """Review of #249: each look was deflated as the line's recorded trials plus one, however many
        edit looks came before it."""
        first = self.edit({"notional_usd": 20})
        self.clock.advance(24 * 3600 + 1)
        second = self.edit({"notional_usd": 25})
        self.assertEqual(second["numbers"]["trials"], first["numbers"]["trials"] + 1)

    def test_a_strategy_an_audit_approved_for_real_money_is_not_edited_in_place(self):
        """Review of #249: a swing (its first entry is audited, and the auditor reads the PARAMS) raised
        its notional 30 -> 37 in place and kept the band: nothing audits a seated swing again."""
        result = self.edit({"notional_usd": 20})  # replayed while on paper
        self.assertTrue(result["passed"], result)
        self.house.evaluator.seat(self.agent.id, 3, "test: its swing's first entry was audited meanwhile")
        self.house.ledger.append("audit.verdict", {"approve": True, "summary": "approved at notional 30"}, agent=self.agent.id)
        self.assertEqual(self.apply(self.agent, "edit_params", params=result["params"], was=result["was"],
                                    code_sha256=result["code_sha256"]), [])
        self.assertIn("an audit approved your strategy", self.not_applied(self.agent)[0])
        self.clock.advance(24 * 3600 + 1)
        self.assertIn("an audit approved your strategy", self.edit({"notional_usd": 37}).get("error", ""))
        self.assertEqual(len(self.replays), 1)  # refused before any replay
        self.assertEqual(self.house.registry.get(self.agent.id).params["notional_usd"], 30.0)
        self.assertEqual(self.apply(self.agent, "pause_entries", session="s2"), ["pause_entries"])  # it can still hold its entries

    def test_an_edit_replayed_before_its_strategy_changed_is_not_applied(self):
        result = self.edit({"notional_usd": 20})
        self.apply(self.agent, "pause_entries", n=0)  # a pause does not change the strategy
        self.house.registry.adopt(self.agent.id, code=self.agent.code, needs=self.agent.needs,
                                  params={**self.agent.params, "notional_usd": 25.0}, reason="another change")
        self.assertEqual(self.apply(self.agent, "edit_params", n=1, params=result["params"], was=result["was"],
                                    code_sha256=result["code_sha256"]), [])
        self.assertIn("changed after the edit was replayed", self.not_applied(self.agent)[0])
        self.assertEqual(self.house.registry.get(self.agent.id).params["notional_usd"], 25.0)


class EditInTheSeatMarket(ControlCase):
    """Review of #249: `_displaceable` read an in-place edit as a new program. The edit bought a fresh
    grace (a shield against the House's refill), and cleared "traded since its program's opportunity",
    so a trader lost its protection and an evidenced newcomer could take its seat at once. An edit
    keeps the seat and the record: the program's clock runs on."""

    def edit_in_place(self, agent, changes, session="s1"):
        """A passing edit replay on record (`_edit_replay` writes it), then the pass's request."""
        agent = self.house.registry.get(agent.id)
        was = dict(agent.params)
        params = {**was, **changes}
        self.house.ledger.append("agent.research", {"tool": "edit_replay", "session": session, "passed": True, "reasons": [],
                                                    "params": params, "was": was}, agent=agent.id)
        return self.apply(agent, "edit_params", session=session, params=params, was=was, code_sha256=agent.code_sha256)

    def displaceable(self, **kw):
        return [row[-1].id for row in self.house._displaceable(self.house.game["economy"], **kw)]

    def test_an_edit_buys_no_fresh_grace(self):
        agent = self.seated("sized", SIZED)
        self.clock.advance(13 * 3600)  # past the 12-hour grace, never traded
        self.assertEqual(self.displaceable(), [agent.id])
        self.assertEqual(self.edit_in_place(agent, {"notional_usd": 20.0}), ["edit_params"])
        self.assertEqual(self.displaceable(), [agent.id])

    def test_an_edit_keeps_a_traders_protection(self):
        agent = self.seated("sized", SIZED)
        self.data.price = 79000.0  # under its line: it buys
        self.broker.set_quote(self.btc, "78995", "79005")
        self.house.tick()
        self.assertIsNotNone(self.house.ledger.last("book.fill", agent=agent.id))
        self.assertEqual(self.displaceable(evidenced=True), [])  # a trader short of its record keeps its seat
        self.assertEqual(self.edit_in_place(agent, {"notional_usd": 20.0}), ["edit_params"])
        self.assertEqual(self.displaceable(evidenced=True), [])

class ControlsAcrossAStop(ControlCase):
    """Review of #249: a pass's controls were applied after its research job was marked done, and a
    restart resumes only an unfinished job, so a stop between the two lost them for good."""

    def test_a_stop_after_the_pass_ends_keeps_what_it_asked(self):
        from league.researcher import Pass

        agent = self.seated()
        house = self.house

        class Researcher:
            def research(self, agent, standing, *, session):
                house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": "pause_entries",
                                                       "session": session, "note": "the live rule keeps adding losing positions"},
                                    agent=agent.id, id=f"control-request:{session}:0")
                return Pass(agent.id, reason="finished", calls=["pause_entries"])

        class Stopped(RuntimeError):
            pass

        house.researcher = Researcher()
        finish = house.research_jobs.finish

        def finish_then_stop(session, reason="", **kw):
            finish(session, reason, **kw)
            raise Stopped("the process stops here")

        house.research_jobs.finish = finish_then_stop
        with self.assertRaises(Stopped):
            house.research(agent)
        self.assertIsNotNone(house.registry.entries_paused(agent.id))

    def test_a_pass_applied_late_still_finds_what_it_asked(self):
        """The pass's requests and its edit's replay were sought in the agent's newest 400 research rows,
        which a busy agent writes in under three hours; a pass resumed after a restart is applied late."""
        agent = self.seated("sized", SIZED)
        was = dict(agent.params)
        params = {**was, "notional_usd": 20.0}
        self.house.ledger.append("agent.research", {"tool": "edit_replay", "session": "s1", "passed": True, "reasons": [],
                                                    "params": params, "was": was}, agent=agent.id)
        self.request(agent, "edit_params", session="s1", n=0, params=params, was=was, code_sha256=agent.code_sha256)
        self.request(agent, "pause_entries", session="s1", n=1)
        for n in range(400):
            self.house.ledger.append("agent.research", {"tool": "candidate_admission", "session": f"q{n}", "status": "deferred",
                                                        "reason": f"waiting {n}"}, agent=agent.id)
        self.assertEqual(self.house._apply_controls(agent.id, "s1"), ["edit_params", "pause_entries"])

    def test_a_restart_between_an_edit_and_a_pause_of_one_pass_makes_the_pause(self):
        from dataclasses import asdict
        from league.researcher import Pass, pass_state

        agent = self.seated("sized", SIZED)
        jobs = self.house.research_jobs
        session = jobs.enqueue(agent.id, self.house._generation(agent.id))["session"]
        jobs.start(session, {"agent": asdict(agent), "standing": {}})
        jobs.ready(session, pass_state(Pass(agent.id, reason="finished")))
        was = dict(agent.params)
        params = {**was, "notional_usd": 20.0}
        self.house.ledger.append("agent.research", {"tool": "edit_replay", "session": session, "passed": True, "reasons": [],
                                                    "params": params, "was": was}, agent=agent.id)
        self.request(agent, "edit_params", session=session, n=0, params=params, was=was, code_sha256=agent.code_sha256)
        self.assertEqual(self.house._apply_controls(agent.id, session), ["edit_params"])  # the process stops here
        self.request(agent, "pause_entries", session=session, n=1)  # asked in the same pass, not yet made
        self.house.research(self.house.registry.get(agent.id))  # the restart resumes the job
        self.assertIsNotNone(self.house.registry.entries_paused(agent.id))
        self.assertEqual(jobs.get(session)["status"], "cancelled")

def pause(house, agent, session="pause-1", note="its live rule keeps adding losing positions"):
    """What a research pass's `pause_entries` asks and the House applies when the pass ends."""
    house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": "pause_entries", "session": session,
                                           "note": note}, agent=agent.id, id=f"control-request:{session}:0")
    return house._apply_controls(agent.id, session)


class PausedEntriesAndCapital:
    """Review of #249, P2 and P3 (the main session's decisions): a paused agent is promoted to no real
    band; on real money it keeps its band and its positions, but after 24 hours paused its stake is
    held to its venue's probe, by free cash only; held buys are not activity, and a resident paused
    past the grace is displaceable like an idle one."""


from league.tests.test_allocator import HouseCaseReal, P as allocator_params, ev as evidence_row  # noqa: E402


class PausedAndTheAllocator(HouseCaseReal):
    __doc__ = PausedEntriesAndCapital.__doc__

    def test_a_paused_agent_is_promoted_to_no_real_band_and_the_reason_is_recorded(self):
        house = self.house
        a = self.agent()
        self.assertEqual(pause(house, a), ["pause_entries"])
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
            self.assertEqual(house.evaluator.rung(a.id), 1)
            status = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=a.id) if e.payload.get("decision") == "progress"][-1]
            self.assertEqual(status["stage"], "paused")
            self.assertIn("a paused agent is promoted to no real band", status["reason"])
            self.assertIsNotNone(house.allocator.board()["agents"][a.id]["entries_paused_since"])
            house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": "resume_entries", "session": "resume-1",
                                                   "note": "the settlements came back"}, agent=a.id, id="control-request:resume-1:0")
            self.assertEqual(house._apply_controls(a.id, "resume-1"), ["resume_entries"])
            self.tick()
        self.assertEqual(house.evaluator.rung(a.id), 2)

    def bunted(self):
        a = self.agent()
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6)}):
            self.tick()
        book = self.house.books["alpaca"]
        self.assertEqual((self.house.evaluator.rung(a.id), book.account(a.id).staked), (2, D("25")))
        return a, book

    def sized(self, a, book, w_real, equity):
        """One sizing pass with the agent's real equity read as `equity` (as `test_allocator.BuntGrowth`)."""
        from unittest.mock import patch

        real = book.equity
        with patch.object(book, "equity", side_effect=lambda agent: D(equity) if agent == a.id else real(agent)):
            return self.house.allocator._size(a, evidence_row(agent=a.id, venue="alpaca", rung=2, w_real=w_real, e=w_real, real_trades=3),
                                              "bunt", allocator_params())

    def test_a_day_paused_on_real_money_holds_the_stake_to_the_probe_by_free_cash_only(self):
        a, book = self.bunted()
        self.assertIsNone(self.sized(a, book, 1.2, "30"))  # its target is $30 (25 x 1.2): the $5 it made is kept
        pause(self.house, a)
        self.clock.advance(23 * 3600)
        self.assertIsNone(self.sized(a, book, 1.2, "30"))  # a pause younger than a day moves nothing
        self.clock.advance(3600)
        row = self.sized(a, book, 1.2, "30")
        self.assertEqual((row["stake_usd"], row["moved_usd"]), ("25", "-5.00"))
        self.assertIn("held to the probe: its entries have been paused since", row["reason"])
        self.assertEqual(book.account(a.id).staked, D("20"))
        self.assertEqual(self.house.evaluator.rung(a.id), 2)  # it keeps its band


class PausedIsNotActive(ControlCase):
    __doc__ = PausedEntriesAndCapital.__doc__

    def test_held_buys_are_not_activity(self):
        agent = self.seated()  # buys when flat: every wake it is shown a live market and its buy is held
        pause(self.house, agent)
        for _ in range(3):
            self.house.tick()
            self.clock.advance(301)
        self.assertEqual(self.house.idle_run(agent)["barren"], 3)

    def test_a_paused_resident_that_is_broke_dies_stuck_like_an_idle_one(self):
        """Neither trading nor able to buy the research that would resume it: the stuck rule's case."""
        agent = self.seated()
        pause(self.house, agent)
        self.house.game["economy"]["idle_broke_wakes"] = 3
        self.house.tick()  # the first tick pays the epoch's floor
        self.clock.advance(301)
        self.house.economy.charge(agent.id, self.house.economy.balance(agent.id) - D("0.10"), "spent to the floor", id="test-broke")
        for _ in range(3):
            self.house.tick()  # its buy is held at every wake; `keep_population` runs at the end of each tick
            self.clock.advance(301)
        self.assertEqual(self.house.registry.get(agent.id).cause, "stuck")

    def test_a_trader_paused_past_the_grace_is_displaceable_like_an_idle_one(self):
        agent = self.seated("sized", SIZED)
        self.data.price = 79000.0  # under its line: it buys, and is a trader short of its record
        self.broker.set_quote(self.btc, "78995", "79005")
        self.house.tick()
        self.assertIsNotNone(self.house.ledger.last("book.fill", agent=agent.id))
        rules = self.house.game["economy"]
        self.assertEqual(self.house._displaceable(rules, evidenced=True), [])
        pause(self.house, agent)
        grace = float(rules.get("displace_after_epochs", 2)) * float(rules["epoch_seconds"])
        self.clock.advance(grace - 60)
        self.assertEqual(self.house._displaceable(rules, evidenced=True), [])  # paused, but not past the grace
        self.clock.advance(120)
        (row,) = self.house._displaceable(rules, evidenced=True)
        self.assertEqual((row[-1].id, row[0]), (agent.id, False))  # ranked with the idle
        (row,) = self.house._displaceable(rules)
        self.assertEqual(row[-1].id, agent.id)  # and the House's own refill may take its seat too

if __name__ == "__main__":
    import unittest

    unittest.main()
