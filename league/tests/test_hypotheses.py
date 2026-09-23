"""The hypothesis foundry (league/hypotheses.py): cards, replay admission, evidence allocation,
exploration, retirement, repair reports, budget refusals and restarts -- all against a fake frontier."""

import json
import unittest
from decimal import Decimal
from pathlib import Path

from league.frontier import Answer
from league.hypotheses import Foundry, card_id
from league.tests.test_house import IDLE, HouseCase

D = Decimal

#: A strategy that profits from the fake tape's sawtooth, on the crypto majors desk: it passes replay.
PASSER = '''
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

UNSAFE = "import os\n\ndef decide(ctx):\n    return {}\n"


def candidate(name, mechanism, code):
    return {"name": name, "mechanism": mechanism, "data": ["BTC/USD 5Min bars"], "edge_after_costs": "2% a round trip less 0.5% fees",
            "horizon": "five minutes, hour blocks", "rejection": "fewer than 20 trades or negative out-of-sample growth", "code": code}


class FakeFrontier:
    model = "gpt-6-astra"

    def __init__(self, candidates=(), cost="0.50"):
        self.candidates = list(candidates)
        self.cost = D(cost)
        self.asked = []

    def ask(self, *, system, user, agent, max_output_tokens=6000, effort="medium"):
        self.asked.append({"system": system, "user": json.loads(user), "agent": agent})
        return Answer(json.dumps({"summary": "three sawtooth ideas", "candidates": self.candidates}), self.cost,
                      {"input_tokens": 1000, "output_tokens": 1000}, self.model)


class FoundryCase(HouseCase):
    DESK = "alpaca-crypto-majors"

    def setUp(self):
        super().setUp()
        self.house.pacer.may_spend = lambda kind: True  # the test clock is outside the expedition's calendar
        self.frontier = FakeFrontier([
            candidate("sawtooth", "buy the low leg of the recorded five-minute sawtooth and sell the high leg", PASSER),
            candidate("idle", "a mechanism that never finds a trade worth its fee", IDLE),
            candidate("unsafe", "a mechanism whose file reaches for the operating system", UNSAFE),
        ])
        self.foundry = Foundry(self.house, self.frontier)
        self.house.hypotheses = self.foundry
        self.rules = self.house.game["economy"]

    def call(self, desk=None):
        out = self.foundry.run(desk or self.DESK, "evidence", "test")
        self.house.wait()
        return out

    def card_of(self, name):
        return next(c for c in self.foundry.cards().values() if c["name"] == name)

    def trial(self, agent, family, passed, *, blocks=24, reasons=("0 closed trades, 20 needed",)):
        self.house.ledger.append("eval.trial", {"family": family, "passed": passed, "blocks": blocks, "trades": 0 if not passed else 30,
                                                "sharpe": 0.1, "reasons": [] if passed else list(reasons)}, agent=agent)

    def earn(self, agent, growth=0.004, n=3):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{i}"}, agent=agent.id)


class Cards(FoundryCase):
    def test_a_call_records_each_card_and_books_its_cost_like_a_merton_pass(self):
        out = self.call()
        self.assertEqual(len(out["cards"]), 3)
        cards = self.foundry.cards()
        sawtooth = self.card_of("sawtooth")
        self.assertEqual(sawtooth["id"], card_id(sawtooth["mechanism"], self.DESK))
        for key in ("mechanism", "data", "edge_after_costs", "horizon", "rejection", "niche", "venue", "author", "lineage", "parent_card", "created_for"):
            self.assertIn(key, sawtooth)
        self.assertEqual((sawtooth["author"], sawtooth["niche"], sawtooth["venue"]), ("merton", self.DESK, "alpaca"))
        self.assertNotIn("_code", sawtooth)  # the fold never carries code; the private ledger row does
        self.assertIn("_code", self.house.ledger.get(f"hypothesis.card:{sawtooth['id']}").payload)
        passes = [e.payload for e in self.house.ledger.iter(kinds="merton.pass") if e.payload.get("role") == "foundry"]
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["cost_usd"], "0.50")
        self.assertEqual(sorted(passes[0]["cards"]), sorted(cards))
        self.assertEqual(passes[0]["allocation"]["desk"], self.DESK)
        # What Merton was shown: the desk, the data, the fees and the gate -- never a tape.
        shown = self.frontier.asked[0]["user"]
        for key in ("desk", "data", "fees", "replay_gate", "replay_view", "failed_on_this_desk", "retired_on_this_desk", "horizon_rule"):
            self.assertIn(key, shown)
        self.assertNotIn("steps", json.dumps(shown))
        self.assertIn("THE STRATEGY CONTRACT", self.frontier.asked[0]["system"])

    def test_every_card_is_replayed_before_it_can_take_a_seat(self):
        self.call()
        outcomes = {c["name"]: self.foundry.evaluations()[c["id"]]["outcome"] for c in self.foundry.cards().values()}
        self.assertEqual(outcomes, {"sawtooth": "passed", "idle": "failed", "unsafe": "invalid"})
        idle = self.card_of("idle")
        # The failure is a counted trial on the card's own line, and no agent ever existed for it.
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=idle["line_id"]), 1)
        self.assertIsNone(self.house.registry.get(idle["line_id"]))
        # Invalid code is refused before a sandbox is bought: not a trial.
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=self.card_of("unsafe")["line_id"]), 0)
        self.assertEqual(self.house.registry.living(), [])  # nothing is born by being replayed

    def test_only_a_replay_passer_is_born_and_it_starts_on_paper_on_its_own_line(self):
        self.call()
        self.rules.update(newcomer_seconds=600, max_population=10)
        seed = self.seated()  # the league is never empty in production
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        card = self.card_of("sawtooth")
        self.assertEqual((child.id, child.founder, child.parent, child.specialty), (card["line_id"], f"card:{card['id']}", None, self.DESK))
        self.assertEqual(self.house.evaluator.rung(child.id), 1)
        self.assertEqual(self.house.books["alpaca-paper"].account(child.id).staked, D("200"))
        # Its admission replay is the first trial of its own lineage, and it is not replayed again.
        self.assertEqual(self.house.registry.lineage(child.id), [child.id])
        self.assertEqual(len(self.house.evaluator.family_trials(child.family, self.house.registry.lineage(child.id))), 1)
        self.assertEqual(self.house._state["tried"][child.id], child.code_sha256)
        born = self.house.ledger.last("agent.born", agent=child.id).payload
        self.assertIn(card["id"], born["reason"])
        route = self.house.ledger.get(f"birth-route:{child.id}").payload
        self.assertEqual((route["route"], route["evidence"]["card"], route["evidence"]["replay_passed"]), ("hypothesis", card["id"], True))
        self.assertEqual(self.foundry.inventory(), [])
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules), "the failed and the invalid cards are never born")
        self.assertNotEqual(seed.id, child.id)

    def test_a_card_that_names_another_desks_markets_is_refused_before_its_replay(self):
        self.frontier.candidates = self.frontier.candidates[:1]
        self.call("alpaca-megacaps")  # the BTC sawtooth sent to the megacaps desk
        card = self.card_of("sawtooth")
        outcome = self.foundry.evaluations()[card["id"]]
        self.assertEqual(outcome["outcome"], "invalid")
        self.assertIn("alpaca-crypto-majors", outcome["detail"])
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=card["line_id"]), 0)

    def test_the_packet_shows_ingested_coverage_for_this_desk_only(self):
        self.house.ledger.append("data.coverage", {"source": "alpaca-history", "status": "finished", "series": [
            {"kind": "bars", "symbol": "BTC/USD", "timeframe": "1Hour", "rows": 900, "first_day": "2024-01-01", "last_day": "2026-09-21"},
            {"kind": "bars", "symbol": "SPY", "timeframe": "1Hour", "rows": 900, "first_day": "2016-01-04", "last_day": "2026-09-21"}],
            "limitations": ["no depth"]})
        shown = self.foundry.packet(self.DESK)["data"]["recorded_coverage"]
        self.assertEqual([row["symbol"] for row in shown["series"]], ["BTC/USD"])
        self.assertEqual(shown["limitations"], ["no depth"])

    def test_replays_that_fail_to_fetch_data_are_infrastructure_not_invalid_code(self):
        from league.hypotheses import classify_error
        self.assertEqual(classify_error("TapeError: alpaca stock bars: TransportError: GET https://gateway/v1/alpaca-paper/v2/stocks/bars"), "blocked_infra")
        self.assertEqual(classify_error("TapeError: kalshi candles: HTTP 503 upstream"), "blocked_infra")
        self.assertEqual(classify_error("ValueError: unsupported input: required observed bars are missing for BTC/USD"), "blocked_data")
        self.assertEqual(classify_error("NameError: name 'foo' is not defined"), "invalid")

    def test_a_closed_allowance_leaves_a_card_pending_without_using_an_attempt(self):
        card, _ = self.foundry._card(candidate("late", "a card the allowance holds back", PASSER), self.DESK, "c", None, {}, {}, {})
        self.foundry._state().setdefault("attempts", {})[card["id"]] = [1, 0]
        self.house._candidate_replay = lambda agent, code: {"counted_as_trial": False, "passed": False,
                                                            "error": "ValueError: campaign allowance is closed", "numbers": {}}
        self.foundry.evaluate(card["id"])
        self.assertNotIn(card["id"], self.foundry.evaluations())
        self.assertEqual(self.foundry._state()["attempts"][card["id"]][0], 0)

    def test_an_exact_mechanism_is_not_carded_twice(self):
        self.call()
        again = self.foundry.run(self.DESK, "evidence", "test")
        self.house.wait()
        self.assertEqual(again["cards"], [])
        self.assertEqual(len(again["refused"]), 3)
        self.assertEqual(len(self.foundry.cards()), 3)


class Allocation(FoundryCase):
    def test_allocation_follows_evidence_and_ignores_how_empty_a_desk_is(self):
        etf_code = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]').replace("sawtooth", "etf")
        etfs = [self.house.spawn("scholes", "etf-family", etf_code, reason="test") for _ in range(4)]  # 1 open seat of 5
        crypto = self.house.spawn("rosenfeld", "crypto-family", PASSER, reason="test")                  # 4 open seats of 5
        for n, agent in enumerate(etfs * 3):
            self.trial(agent.id, "etf-family", passed=n % 3 == 0)
        for _ in range(20):
            self.trial(crypto.id, "crypto-family", passed=False)
        scores = {d.niche: d for d in self.foundry.desk_scores(fresh=True)}
        self.assertGreater(scores[self.DESK].open_seats, scores["alpaca-index-etfs"].open_seats)
        self.assertGreater(scores["alpaca-index-etfs"].score, scores[self.DESK].score)
        desk, route, reason = self.foundry.allocate(fresh=True)
        self.assertEqual((desk.niche, route), ("alpaca-index-etfs", "evidence"))
        self.assertIn("evidence score", reason)
        # A desk with no replay is never offered to the foundry: it could not admit by replay.
        self.assertFalse(scores["alpaca-options"].eligible)

    def test_the_exploration_share_holds(self):
        self.trial("nobody", "x", passed=False)
        routes = []
        for n in range(20):
            desk, route, _ = self.foundry.allocate(fresh=True)
            routes.append(route)
            self.house.ledger.append("merton.pass", {"role": "foundry", "at_epoch": self.clock(), "cost_usd": "0",
                                                     "allocation": {"desk": desk.niche, "route": route}})
        self.assertIn("exploration", routes)
        self.assertLessEqual(routes.count("exploration") / len(routes), 0.2)
        self.assertEqual(routes[:4], ["evidence"] * 4)

    def test_no_seat_means_no_call(self):
        self.rules.update(max_population=1)
        self.seated()  # too young to be displaced: the league is full and nobody may leave
        self.assertFalse(self.foundry.due())
        self.assertIn("no seat", self.foundry.refusal)


class FastEvidence(FoundryCase):
    """Sept 23, 2026: half the foundry's calls go to hourly, around-the-clock desks, cards may queue
    for replay, other Merton roles no longer hold it up, and its packet says why hourly is faster."""

    def settings(self, **kw):
        self.house.game["hypotheses"] = {**self.house.game.get("hypotheses", {}), **kw}
        self.foundry = Foundry(self.house, self.frontier)
        self.house.hypotheses = self.foundry

    def test_the_fast_share_sends_calls_to_fast_desks_the_evidence_route_would_never_pick(self):
        etf_code = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]').replace("sawtooth", "etf")
        etfs = [self.house.spawn("scholes", "etf-family", etf_code, reason="test") for _ in range(4)]
        crypto = self.house.spawn("rosenfeld", "crypto-family", PASSER, reason="test")
        for n, agent in enumerate(etfs * 3):
            self.trial(agent.id, "etf-family", passed=n % 3 == 0)
        for _ in range(20):
            self.trial(crypto.id, "crypto-family", passed=False)
        self.settings(fast_desks=[self.DESK], fast_share=0.5, exploration_share=0)
        routes = []
        for _ in range(10):
            desk, route, reason = self.foundry.allocate(fresh=True)
            routes.append((desk.niche, route))
            self.house.ledger.append("merton.pass", {"role": "foundry", "at_epoch": self.clock(), "cost_usd": "0",
                                                     "allocation": {"desk": desk.niche, "route": route}})
        self.assertEqual(sum(1 for _, r in routes if r == "fast"), 5)
        self.assertEqual({d for d, r in routes if r == "fast"}, {self.DESK})
        self.assertEqual({d for d, r in routes if r == "evidence"}, {"alpaca-index-etfs"})

    def test_cards_may_queue_for_replay_and_another_role_does_not_hold_the_foundry(self):
        import threading

        self.settings(max_pending_cards=8)
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        busy = threading.Event()
        worker = threading.Thread(target=busy.wait, args=(5,))
        worker.start()
        self.addCleanup(lambda: (busy.set(), worker.join(5)))
        self.house._jobs["merton:teacher"] = worker
        self.house._jobs["replay:hypothesis:pending"] = worker
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        self.house._jobs["merton:foundry"] = worker
        self.assertFalse(self.foundry.due())
        self.assertIn("foundry call is still running", self.foundry.refusal)

    def test_the_packet_says_why_hourly_is_faster_and_what_made_money_forward(self):
        self.settings(prefer_horizon="hour")
        winner = self.seated("rosenfeld", code=PASSER)
        self.earn(winner)
        packet = self.foundry.packet(self.DESK)
        self.assertEqual(packet["horizon_guidance"]["prefer"], "hour")
        self.assertIn("4 active hourly blocks", packet["horizon_guidance"]["paper_screen"]["hour"])
        rows = packet["forward_on_this_desk"]
        self.assertEqual((rows[0]["members"], rows[0]["on_paper"], rows[0]["earning"]), (1, 1, 1))
        self.assertIn("quarter of the taker", packet["fees"]["kalshi_maker"])
        self.assertEqual(packet["fees"]["alpaca_crypto"]["round_trip"]["taker_taker"], 0.005)


class Retirement(FoundryCase):
    def test_fifteen_failures_without_a_pass_retire_a_family_and_it_gets_no_mutation(self):
        self.rules.update(newcomer_seconds=600, max_population=10)
        earner = self.seated("earner")
        self.earn(earner)
        self.clock.advance(601)
        child = self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None)
        self.assertEqual(child.parent, earner.id, "an earning parent may have an evidence-driven child")
        route = self.house.ledger.get(f"birth-route:{child.id}").payload
        self.assertEqual(route["route"], "evidence_mutation")
        for _ in range(15):
            self.trial(earner.id, earner.family, passed=False)
        rows = self.foundry.retire_exhausted()
        self.assertEqual([(r["id"], r["reason"]) for r in rows], [(f"family:{earner.family}", "disproven")])
        self.assertIn(f"family:{earner.family}", self.foundry.retired())
        self.clock.advance(601)
        self.foundry._state()["last_mutation_look"] = 0
        self.assertIsNone(self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None))
        self.assertEqual(self.foundry.retire_exhausted(), [], "retired once")

    def test_a_loser_is_never_the_parent_of_a_house_mutation(self):
        loser = self.seated("loser")
        self.earn(loser, growth=-0.004)
        self.assertIsNone(self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None))

    def test_a_blocked_family_becomes_a_repair_report_not_more_births(self):
        agent = self.seated("empty")
        for _ in range(15):
            self.trial(agent.id, agent.family, passed=False, blocks=0)
        rows = self.foundry.retire_exhausted()
        self.assertEqual(rows[0]["reason"], "blocked_data")
        report = self.house.ledger.last("repair.reported").payload
        self.assertEqual((report["kind"], report["source"]), ("missing_data", "triage"))
        self.assertTrue(report["key"].startswith("missing_data:"))
        self.assertTrue(report["evidence"] and {"seq", "at", "agent", "excerpt"} <= set(report["evidence"][0]))

    def test_cards_that_cannot_run_close_their_desk_with_a_shared_defect_report(self):
        for n in range(3):
            card = {"id": f"c{n}", "niche": self.DESK, "line_id": f"rosenfeld-hc{n}", "model": "m", "code_sha256": "x"}
            self.house.ledger.append("hypothesis.card", {**card, "mechanism": f"m{n}", "created_epoch": self.clock()}, id=f"hypothesis.card:c{n}")
            self.foundry._outcome(card, "blocked_infra", "sandbox: SandboxError")
        self.foundry.retire_exhausted()
        report = self.house.ledger.last("repair.reported").payload
        self.assertEqual((report["key"], report["kind"]), (f"shared_defect:hypothesis-replay:{self.DESK}", "shared_defect"))
        self.assertIn(self.DESK, self.foundry._blocked_desks())
        picked = self.foundry.allocate(fresh=True)
        self.assertNotEqual(picked[0].niche, self.DESK)
        self.house.ledger.append("repair.status", {"key": report["key"], "state": "verified"})
        self.assertNotIn(self.DESK, self.foundry._blocked_desks())

    def test_rewordings_share_failure_history_but_never_trial_counts(self):
        self.house.game["hypotheses"] = {**self.house.game.get("hypotheses", {}), "retire_after_failures": 3}
        ids = []
        for n in range(3):
            ident = card_id(f"reworded {n}", self.DESK)
            card = {"id": ident, "niche": self.DESK, "line_id": f"rosenfeld-hr{n}", "model": "m", "code_sha256": "x"}
            self.house.ledger.append("hypothesis.card", {**card, "mechanism": f"reworded {n}", "created_epoch": self.clock()}, id=f"hypothesis.card:{ident}")
            self.trial(card["line_id"], f"fam-{n}", passed=False)
            self.foundry._outcome(card, "failed", "0 closed trades")
            ids.append(card["id"])
        self.assertEqual(self.foundry.retire_exhausted(), [], "three separate ideas, one failure each")
        for a, b in zip(ids, ids[1:]):
            self.house.ledger.append("hypothesis.link", {"a": a, "b": b, "relation": "rewording", "confidence": 0.93, "method": "jev"})
        retired = self.foundry.retire_exhausted()
        self.assertEqual(sorted(r["id"] for r in retired), sorted(ids))
        self.assertEqual([len(self.house.evaluator.family_trials(f"fam-{n}", [f"rosenfeld-hr{n}"])) for n in range(3)], [1, 1, 1])
        # A retired mechanism gets no new card.
        card, problem = self.foundry._card(candidate("again", "Reworded, 0!", PASSER), self.DESK, "c", None,
                                           self.foundry.cards(), self.foundry.retired(), self.foundry.links())
        self.assertIsNone(card)
        self.assertIn("already has a card", problem)
        fresh_id = card_id("an unrelated mechanism", self.DESK)
        card, problem = self.foundry._card(candidate("other", "an unrelated mechanism", PASSER), self.DESK, "c", None,
                                           {}, self.foundry.retired(), {fresh_id: {fresh_id, ids[0]}})
        self.assertIsNone(card)
        self.assertIn("retired mechanism", problem)


class Gates(FoundryCase):
    def test_tier_budget_pause_and_cadence_refusals(self):
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        self.house.frontier_tier = lambda: "audits"
        self.assertFalse(self.foundry.due())
        self.assertIn("tier", self.foundry.refusal)
        self.house.frontier_tier = lambda: "earned"  # code work still runs under "earned"
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        self.house.pacer.may_spend = lambda kind: False
        self.assertFalse(self.foundry.due())
        self.assertIn("allowance", self.foundry.refusal)
        self.house.pacer.may_spend = lambda kind: True
        self.house.ledger.append("merton.pass", {"role": "foundry", "at_epoch": self.clock() - 7200,
                                                 "cost_usd": str(self.foundry.settings["budget_usd"])})
        self.assertFalse(self.foundry.due())
        self.assertIn("budget", self.foundry.refusal)
        self.clock.advance(25 * 3600)  # outside the budget window
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        (Path(self.house.root) / "PAUSE").write_text("maintenance")
        self.assertFalse(self.foundry.due())
        self.assertIn("pause", self.foundry.refusal)

    def test_a_tick_calls_once_then_waits_out_the_cadence(self):
        self.frontier.candidates = []
        self.house.tick()
        self.house.wait()
        self.assertEqual(len(self.frontier.asked), 1)
        self.house.tick()
        self.house.wait()
        self.assertEqual(len(self.frontier.asked), 1)
        self.assertIn("cadence", self.foundry.refusal)

    def test_the_cadence_and_pending_cards_survive_a_restart(self):
        self.frontier.candidates = []
        self.call()
        self.house._save_state()
        restarted = self.new_house(game=self.house.game)
        try:
            restarted.pacer.may_spend = lambda kind: True
            foundry = Foundry(restarted, FakeFrontier())
            restarted._state.pop("hypotheses", None)  # even a lost state file cannot buy an early call
            self.assertFalse(foundry.due())
            self.assertIn("cadence", foundry.refusal)
            self.clock.advance(31 * 60)
            self.assertTrue(foundry.due(), foundry.refusal)
            # A card written before the restart and never evaluated is replayed after it.
            foundry._card(candidate("late", "a card the old process never replayed", PASSER), self.DESK, "c", None, {}, {}, {})
            self.assertEqual(len(foundry.pending()), 1)
            foundry.tick(open_for_business=True)
            restarted.wait()
            self.assertEqual(foundry.pending(), [])
            self.assertEqual(foundry.evaluations()[foundry.cards().popitem()[0]]["outcome"], "passed")
        finally:
            restarted.close(wait=None)


class Labels(FoundryCase):
    def test_founders_and_earner_forks_keep_their_exceptions_explicit(self):
        founder = self.house.found(["crypto-reversion"])[0]
        self.foundry.annotate_births()
        row = self.house.ledger.get(f"birth-route:{founder.id}").payload
        self.assertEqual((row["route"], row["evidence"]["exception"]), ("founder", "founder_paper_start"))
        self.house.economy.grant(founder.id, "10", "test: earned")
        child = self.house.fork(founder)
        self.foundry.annotate_births()
        row = self.house.ledger.get(f"birth-route:{child.id}").payload
        self.assertEqual((row["route"], row["evidence"]["replay_passed"]), ("earner_fork", False))


class Compatibility(FoundryCase):
    def test_a_line_retired_by_the_refill_guard_is_not_bred_either(self):
        """The House's v0 refill guard writes `line:<line>` with a text `evidence`."""
        earner = self.seated("earner")
        self.earn(earner)
        self.house.ledger.append("hypothesis.retired", {"id": f"line:{earner.line}", "reason": "disproven", "failures": 15,
                                                        "evidence": "15 replay trials and 0 passes; House mutations stop"})
        self.assertIsNone(self.foundry._evidence_mutation(self.rules, living=self.house.registry.living(), loser=None))
        shown = self.foundry.packet(self.DESK)["retired_on_this_desk"]
        self.assertEqual([row["id"] for row in shown], [f"line:{earner.line}"])

    def test_replays_that_cannot_run_retire_a_family_for_repair_not_for_disproof(self):
        agent = self.seated("boxless")
        for hour in range(5):
            self.house.alert("warning", f"{agent.id}: replay could not run (SandboxError: {agent.id}: the box would not start)")
            self.house.alert("warning", f"{agent.id}: replay could not run (ValueError: campaign allowance is closed)")
            self.clock.advance(3600)
        self.house.alert("warning", f"{agent.id}: replay could not run (SandboxError: the same hour twice)")
        self.house.alert("warning", f"{agent.id}: replay could not run (SandboxError: and again)")
        rows = self.foundry.retire_exhausted()
        self.assertEqual([(r["id"], r["reason"], r["failures"]) for r in rows], [(f"family:{agent.family}", "blocked_infra", 6)])
        report = self.house.ledger.last("repair.reported").payload
        self.assertEqual(report["kind"], "shared_defect")
        self.assertTrue(report["key"].startswith("shared_defect:replay-harness:"))
        self.assertEqual(self.foundry.retire_exhausted(), [])
        # A verified repair lifts a blocked retirement; a disproof it would not.
        self.house.ledger.append("repair.status", {"key": report["key"], "state": "verified"})
        self.assertNotIn(f"family:{agent.family}", self.foundry.retired())

    def test_a_card_linked_to_a_retired_mechanism_before_its_replay_is_not_replayed(self):
        card, _ = self.foundry._card(candidate("late", "a card linked to a retired idea", PASSER), self.DESK, "c", None, {}, {}, {})
        self.house.ledger.append("hypothesis.retired", {"id": "old-card", "reason": "disproven", "failures": 15, "evidence": {"niche": self.DESK}})
        self.house.ledger.append("hypothesis.link", {"a": card["id"], "b": "old-card", "relation": "rewording", "confidence": 0.95, "method": "jev"})
        self.foundry.evaluate(card["id"])
        self.assertEqual(self.foundry.evaluations()[card["id"]]["outcome"], "retired_mechanism")
        self.assertEqual(self.house.ledger.count(kinds="eval.trial", agent=card["line_id"]), 0)
        # An uncertain label is not a rewording.
        other, _ = self.foundry._card(candidate("near", "a card only related to a retired idea", PASSER), self.DESK, "c", None, {}, {}, {})
        self.house.ledger.append("hypothesis.link", {"a": other["id"], "b": "old-card", "relation": "related", "confidence": 0.7, "method": "jev"})
        self.foundry.evaluate(other["id"])
        self.assertEqual(self.foundry.evaluations()[other["id"]]["outcome"], "passed")


class WaitingCards(FoundryCase):
    def test_a_card_waiting_on_a_full_desk_does_not_stop_calls_for_other_desks(self):
        """Sept 22, 2026: a weather card passed replay at 15:50Z, its desk was full of young agents,
        and the foundry refused every call, for every desk, for two hours."""
        self.call()  # the sawtooth card passes replay on the crypto majors desk
        self.assertEqual(len(self.foundry.inventory()), 1)
        for _ in range(self.house.niches[self.DESK].max_members):  # the desk fills with young agents that may not be displaced yet
            self.house.spawn("rosenfeld", "crypto-family", PASSER, reason="test")
        self.clock.advance(31 * 60)
        self.assertTrue(self.foundry.due(), self.foundry.refusal)
        desk, _, _ = self.foundry.allocate(fresh=True)
        self.assertNotEqual(desk.niche, self.DESK, "no more cards for a desk that already has one waiting")


class EndToEnd(FoundryCase):
    def test_the_tick_calls_replays_and_seats_a_passer_through_the_house_refill(self):
        self.rules.update(newcomer_seconds=600, max_population=10)
        seed = self.seated()
        for _ in range(3):  # the crypto majors desk has the best replay record, so the call goes there
            self.trial(seed.id, seed.family, passed=True)
        self.house.tick()
        self.house.wait()   # the call
        self.house.wait()   # its cards' replays
        self.assertEqual(len(self.foundry.inventory()), 1)
        self.clock.advance(31 * 60)
        self.assertFalse(self.foundry.due())
        self.assertIn("waiting for a seat", self.foundry.refusal)  # no new call while a passer waits
        self.house.tick()
        card = self.card_of("sawtooth")
        child = self.house.registry.get(card["line_id"])
        self.assertIsNotNone(child)
        self.assertEqual(self.house.evaluator.rung(child.id), 1)
        health = json.loads((Path(self.house.root) / "health.json").read_text())
        self.assertEqual(health["hypotheses"]["cards"], 3)
        self.assertEqual(health["hypotheses"]["outcomes"], {"passed": 1, "failed": 1, "invalid": 1})


if __name__ == "__main__":
    unittest.main()
