"""S1 and S2 of the forward-first run (Sept 25, 2026): the foundry brief `foundry-2026-09-25.1` looks for capacity.

The evidence (docs/goals/LTCM_FORWARD_FIRST.md, gap 1, and the run record): the one proven real family is a five-day
regime (MLB totals), the proven megacaps family earns $0.25-0.51 a day at 1x-2x, real settled profit was $19-21 a day
against $118-122 of compute, and no foundry card named its capacity; 8 of the open Alpaca desk's cards were refused
unreplayed on Sept 23-24 because most of what they named sat on one desk. These tests hold: every card carries a
capacity estimate (stated on its card row, measured by its replay on its evaluation row) and is refused under $5 a day
with the arithmetic; half of the calls go to desks whose pooled 7-day forward record is positive, weighted by measured
capacity, three tenths to model-versus-market targets on recorded feeds, two tenths explore; a card spanning two desks
is replayed on both tapes and born on the first it passes; the open Alpaca desk has twelve seats; the game file's
foundry dials stay inside their bounds.
"""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from league import niches
from league.economy import check_bounds, load_game
from league.hypotheses import (FOUNDRY_BRIEF, PROMPT_VERSION, ROUTES, capacity_usd, default_size, halving_size,
                               replay_measure)
from league.tests.test_hypotheses import ETF, MEGACAP, PASSER, FoundryCase, candidate

#: A program on the open Alpaca desk that names four index ETFs and two coins: `niches.match` places it on the
#: index-ETF desk (four of six), as it placed four of the open desk's cards of Sept 24, 2026.
SPANNING = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["QQQ", "XLE", "XLF", "GLD", "BTC/USD", "SOL/USD"]').replace(
    "sawtooth", "spanner")
#: One that names only the index ETFs, written for the open desk: its markets are the index-ETF desk's alone.
ETFS_ONLY = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["GLD", "TLT", "XLE"]').replace("sawtooth", "etfs")


def reference(n, shares, window=10):
    """The route order `Foundry.allocate` documents when every route always has a desk to offer: each bounded route in
    `ROUTES` order while its calls stay within its share of the last `window`, else evidence (test_hypotheses'
    `reference_routes`, with S1's routes)."""
    routes = []
    for _ in range(n):
        recent = routes[-window:]
        routes.append(next((route for route in ROUTES
                            if shares.get(route) and (recent.count(route) + 1) / (len(recent) + 1) <= shares[route] + 1e-9), "evidence"))
    return routes


def stating(name, mechanism, code, *, markets=40.0, profit=12.0):
    """A card that states its capacity (S1): 40 markets a day x $12 a settlement on a $100 replay position is $60 a
    day at $12.50 on the crypto majors desk."""
    return {**candidate(name, mechanism, code),
            "capacity": {"markets_per_day": markets, "profit_per_settlement_usd": profit, "why": "every hour of every major"}}


def replayed(*, passed=True, trades=2100, pnl=2100.0, needs=None):
    """What `House._candidate_replay` answers for a counted trial: over the 21-day live window 2,100 closed trades are
    100 markets a day, and $1 a settlement on a $100 replay position is $12.50 a day at the $12.50 default size."""
    return {"counted_as_trial": True, "passed": passed, "needs": needs, "params": {},
            "numbers": {"trades": trades, "blocks": 504, "sharpe": 1.0, "deflated_sharpe": 0.99, "trials": 1, "passed": passed,
                        "reasons": [] if passed else ["out-of-sample growth -0.001 is not above 0"]},
            "digest": {"all": {"trades": trades, "wins": trades // 2, "losses": trades - trades // 2, "pnl_usd": pnl}}}


class CapacityCase(FoundryCase):
    """The foundry with S1 on: the game file's routes and floor."""

    def setUp(self):
        super().setUp()
        game = load_game()["hypotheses"]
        self.settings(**{k: deepcopy(game[k]) for k in ("capacity_share", "model_share", "exploration_share", "transfer_share",
                                                         "fast_share", "min_capacity_usd", "capacity_days", "capacity_min_blocks",
                                                         "capacity_weight_floor_usd", "replay_position_usd", "model_targets")})

    def settings(self, **kw):
        from league.hypotheses import Foundry

        self.house.game["hypotheses"] = {**self.house.game.get("hypotheses", {}), **kw}
        self.foundry = Foundry(self.house, self.frontier)
        self.house.hypotheses = self.foundry

    def member(self, name, family, code, specialty):
        agent = self.house.spawn(name, family, code, reason=f"{family}: a program of the capacity tests", specialty=specialty)
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def blocks(self, agent, growth, n, *, start=0):
        for i in range(start, start + n):
            self.house.ledger.append("eval.block", {"log_growth": growth, "active": True, "book": "alpaca-paper",
                                                    "key": f"{agent.id}-{i}"}, agent=agent.id)

    def evaluation(self, name):
        return self.foundry.evaluations()[self.card_of(name)["id"]]


class TheRule(CapacityCase):
    def test_the_size_before_fills_halve_is_read_from_the_family_curve(self):
        curve = [{"multiple": 1, "size_usd": 6.0, "fill_rate": 1.0}, {"multiple": 2, "size_usd": 12.0, "fill_rate": 0.9},
                 {"multiple": 4, "size_usd": 24.0, "fill_rate": 0.3}]
        size, why = halving_size(curve)
        self.assertEqual(size, 12.0)
        self.assertIn("halve at $24.00", why)
        size, why = halving_size(curve[:2])  # never halves: its largest measured size, never a size not bid
        self.assertEqual(size, 12.0)
        self.assertIn("hold to $12.00", why)
        unmeasured = [{"multiple": 1, "size_usd": 6.0, "fill_rate": None}, {"multiple": 2, "size_usd": 12.0, "fill_rate": 0.5}]
        self.assertEqual(halving_size(unmeasured)[0], 12.0)
        self.assertIsNone(halving_size([{"multiple": 1, "size_usd": 6.0, "fill_rate": None}]))
        self.assertIsNone(halving_size([{"multiple": 1, "size_usd": 6.0, "fill_rate": 0.0}]))
        # The default is the position a proven family's bunt holds, the 1x size every family's capacity row is read at.
        self.assertEqual((default_size("kalshi"), default_size("alpaca")), (6.0, 12.5))
        self.assertAlmostEqual(capacity_usd(100, 1.0, 12.5, 100), 12.5)
        measured = replay_measure(replayed(), 21.0)
        self.assertEqual((measured["markets_per_day"], measured["profit_per_settlement_usd"]), (100.0, 1.0))
        # A Kalshi day tape keeps a seeded sample of whole events (at most 500 markets in 49 days): the trades a day are
        # scaled by what the series listed over what the tape kept, over the span of its steps.
        sampled = {**replayed(trades=147, pnl=114.3),
                   "tape_shape": {"first": "2026-08-06T00:00:00Z", "last": "2026-09-24T00:00:00Z", "meta": {"listed": 2000, "kept": 500}}}
        measured = replay_measure(sampled, 7.0)
        self.assertEqual((measured["days"], measured["tape_sample"], measured["markets_per_day"]), (49.0, 0.25, 12.0))

    def test_the_desk_size_is_its_best_measured_family_curve(self):
        weather = self.member("mullins", "majors-maker", PASSER, self.DESK)
        self.blocks(weather, 0.01, 6)
        curve = [{"multiple": 1, "size_usd": 12.5, "fill_rate": 0.8, "markets_bid": 30},
                 {"multiple": 2, "size_usd": 25.0, "fill_rate": 0.7, "markets_bid": 12},
                 {"multiple": 4, "size_usd": 50.0, "fill_rate": 0.2, "markets_bid": 6}]
        record = {"state": "unproven", "capacity": {"usd_per_day": 3.0, "markets_per_day": 20.0, "size_usd": 12.5, "curve": curve}}
        with patch.object(self.house.allocator, "family", return_value=record):
            rule = self.foundry.capacity_rule(self.DESK)
        self.assertEqual((rule["size_usd"], rule["size_family"], rule["floor_usd"], rule["replay_position_usd"]),
                         (25.0, "majors-maker", 5.0, 100.0))
        self.assertIn("fills halve at $50.00", rule["size_basis"])
        self.assertEqual(self.foundry.capacity_rule("alpaca-megacaps")["size_usd"], 12.5)  # no curve there: the default
        self.assertIn("no family active", self.foundry.capacity_rule("alpaca-megacaps")["size_basis"])

    def test_the_brief_asks_for_capacity_and_every_packet_carries_the_rule(self):
        self.assertEqual(PROMPT_VERSION, "foundry-2026-09-25.1")
        for words in ("CAPACITY IS THE POINT", "profit_per_settlement_usd", "capacity_call", "`model` section"):
            self.assertIn(words, FOUNDRY_BRIEF)
        rule = self.foundry.packet(self.DESK)["capacity_rule"]
        self.assertEqual((rule["floor_usd"], rule["size_usd"], rule["replay_position_usd"]), (5.0, 12.5, 100.0))
        self.assertIn("markets_per_day x profit_per_settlement_usd x size_usd / replay_position_usd", rule["formula"])


class CardsCarryCapacity(CapacityCase):
    def test_a_card_that_states_no_capacity_is_refused_before_it_is_written(self):
        self.frontier.candidates = [candidate("silent", "a sawtooth that names no capacity", PASSER),
                                    stating("stated", "the recorded sawtooth, every hour, capacity stated", PASSER)]
        with patch.object(self.house, "_candidate_replay", return_value=replayed()):
            out = self.call()
        self.assertEqual(len(out["cards"]), 1)
        self.assertIn("does not state its capacity", out["refused"][0])
        card = self.card_of("stated")
        self.assertEqual(card["capacity"]["basis"], "stated")
        # 40 markets a day x $12 a settlement on the $100 replay position, at the $12.50 default size: $60 a day.
        self.assertAlmostEqual(card["capacity"]["usd_per_day"], 60.0)
        self.assertEqual(self.house.ledger.get(f"hypothesis.card:{card['id']}").payload["capacity"]["usd_per_day"], 60.0)

    def test_a_card_stated_under_five_dollars_a_day_is_refused_with_the_arithmetic_before_any_replay(self):
        self.frontier.candidates = [stating("pennies", "a sawtooth of pennies", PASSER, markets=2.0, profit=1.0)]
        replays = []
        with patch.object(self.house, "_candidate_replay", side_effect=lambda agent, code: replays.append(agent) or replayed()):
            self.call()
        outcome = self.evaluation("pennies")
        self.assertEqual(outcome["outcome"], "under_capacity")
        self.assertIn("$0.25 a day, under the $5 floor: 2.00 markets a day x $1.00", outcome["detail"])
        self.assertEqual(replays, [])  # no replay was bought and no trial counted
        self.assertEqual(self.house.ledger.count(kinds="eval.trial"), 0)

    def test_a_replay_passer_under_five_dollars_a_day_measured_is_never_born(self):
        self.frontier.candidates = [stating("claims", "a sawtooth that claims more than its replay trades", PASSER)]
        # 70 closed trades in 21 days at $0.50 a settlement: 3.33 markets a day, $0.21 a day at $12.50.
        with patch.object(self.house, "_candidate_replay", return_value=replayed(trades=70, pnl=35.0)):
            self.call()
        outcome = self.evaluation("claims")
        self.assertEqual(outcome["outcome"], "under_capacity")
        self.assertIn("passed replay", outcome["detail"])
        self.assertIn("$0.21 a day, under the $5 floor", outcome["detail"])
        self.assertEqual((outcome["capacity"]["basis"], outcome["capacity"]["trades"], outcome["capacity"]["days"]), ("replay", 70, 21.0))
        self.assertEqual(self.foundry.inventory(), [])
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.seated()
        self.clock.advance(601)
        self.assertIsNone(self.house._refill(self.rules))

    def test_a_passer_with_capacity_is_born_and_its_evaluation_carries_the_measure(self):
        self.frontier.candidates = [stating("deep", "a sawtooth on every hour of the majors", PASSER)]
        with patch.object(self.house, "_candidate_replay", return_value=replayed()):
            self.call()
        outcome = self.evaluation("deep")
        self.assertEqual(outcome["outcome"], "passed")
        self.assertEqual(outcome["desk"], self.DESK)
        self.assertAlmostEqual(outcome["capacity"]["usd_per_day"], 12.5)
        self.assertEqual(self.foundry.inventory()[0]["desk"], self.DESK)

    def test_the_real_replay_measures_the_sawtooth_over_its_own_tape(self):
        """The House's own replay of the test tape's sawtooth (PASSER passes every gate), through `_candidate_replay`: its
        closed trades over the span of the tape's steps (`tape_shape`, not the 21-day window it was asked for) and their
        mean profit, through the rule: 360 trades in 2.5 days at $0.75 is $13.56 a day at $12.50, over the floor."""
        self.frontier.candidates = [stating("sawtooth", "buy the low leg of the recorded sawtooth", PASSER)]
        self.call()
        outcome = self.evaluation("sawtooth")
        capacity = outcome["capacity"]
        self.assertEqual((outcome["outcome"], capacity["basis"], capacity["trades"], capacity["tape_sample"]), ("passed", "replay", 360, 1.0))
        self.assertLess(capacity["days"], 3.0)
        self.assertAlmostEqual(capacity["usd_per_day"],
                               capacity["markets_per_day"] * capacity["profit_per_settlement_usd"] * 12.5 / 100, places=2)
        self.assertGreater(capacity["usd_per_day"], 5.0)

    def test_a_merged_repair_is_measured_but_not_held_to_the_floor(self):
        row = {"name": "repaired-sawtooth", "code": PASSER, "why": "the engineer's fix", "repair": {"key": "k1", "parent": "p1"}}
        self.assertTrue(self.foundry.takes_strategy(row))
        card = self.foundry.strategy_cards()["repaired-sawtooth"]
        with patch.object(self.house, "_candidate_replay", return_value=replayed(trades=70, pnl=35.0)):
            self.foundry.evaluate(card["id"])
        outcome = self.foundry.evaluations()[card["id"]]
        self.assertEqual(outcome["outcome"], "passed")
        self.assertLess(outcome["capacity"]["usd_per_day"], 5.0)


class Routes(CapacityCase):
    def record_call(self, desk, route):
        self.house.ledger.append("merton.pass", {"role": "foundry", "at_epoch": self.clock(), "cost_usd": "0",
                                                 "allocation": {"desk": desk, "route": route}})

    def test_the_game_file_splits_calls_half_three_tenths_and_two_tenths(self):
        game = load_game()["hypotheses"]
        self.assertEqual(ROUTES, ("capacity", "model", "transfer", "fast", "exploration"))
        self.assertEqual((game["capacity_share"], game["model_share"], game["exploration_share"], game["transfer_share"],
                          game["fast_share"], game["min_capacity_usd"], game["capacity_days"]), (0.5, 0.3, 0.2, 0, 0, 5, 7))
        self.assertEqual([t["desk"] for t in game["model_targets"]],
                         ["kalshi-weather", "alpaca-megacaps", "alpaca-crypto-majors", "kalshi-sports"])
        self.assertEqual(game["model_targets"][2]["feeds"], ["vol", "funding"])
        # With a positive desk and every target able to take a call, the window rule of `allocate` (each bounded route
        # within its share of the last ten calls, in order; the first call of an empty window is the evidence route's).
        earner = self.member("rosenfeld", "majors-carry", PASSER, self.DESK)
        self.blocks(earner, 0.01, 6)
        routes = []
        for _ in range(40):
            desk, route, _ = self.foundry.allocate(fresh=True)
            routes.append(route)
            self.record_call(desk.niche, route)
        self.assertEqual(routes, reference(40, {"capacity": 0.5, "model": 0.3, "exploration": 0.2}))
        # Over 2,000 such calls: capacity 45%, model 27%, exploration 18%, evidence 9% (the window rule's arithmetic).
        long = reference(2000, {"capacity": 0.5, "model": 0.3, "exploration": 0.2})
        self.assertEqual([round(long.count(r) / 2000, 2) for r in ("capacity", "model", "exploration", "evidence")], [0.45, 0.27, 0.18, 0.09])

    def test_capacity_calls_go_to_positive_desks_in_proportion_to_measured_capacity(self):
        self.settings(capacity_share=1.0, model_share=0, exploration_share=0)
        big = self.member("rosenfeld", "majors-carry", PASSER, self.DESK)
        small = self.member("scholes", "etf-drift", ETF, "alpaca-index-etfs")
        loser = self.member("mcentee", "chip-relay", MEGACAP, "alpaca-megacaps")
        self.blocks(big, 0.01, 6)
        self.blocks(small, 0.01, 6)
        self.blocks(loser, -0.01, 12)
        capacity = {"majors-carry": 9.0, "etf-drift": 1.0, "chip-relay": 50.0}

        def family(name, venue):
            return {"state": "unproven", "capacity": {"usd_per_day": capacity.get(name), "curve": []}}

        picks = []
        with patch.object(self.house.allocator, "family", side_effect=family):
            for _ in range(10):
                desk, route, reason = self.foundry.allocate(fresh=True)
                self.assertEqual(route, "capacity")
                picks.append(desk.niche)
                self.record_call(desk.niche, route)
        self.assertEqual(picks.count(self.DESK), 9)
        self.assertEqual(picks.count("alpaca-index-etfs"), 1)
        self.assertNotIn("alpaca-megacaps", picks)  # the most capacity, on a desk whose pooled record is negative
        self.assertIn("positive forward record", reason)
        self.assertNotIn("majors-carry", reason)  # a desk is chosen, never a family's mechanism by name
        packet = self.foundry.packet(self.DESK, capacity=self.foundry.capacity_for(self.DESK))
        self.assertEqual(packet["capacity_call"]["blocks"], 6)
        self.assertIn("do not", packet["capacity_call"]["ask"])

    def test_the_record_is_seven_days_of_active_blocks_one_a_block_key(self):
        self.settings(model_share=0, exploration_share=0)
        stale = self.member("rosenfeld", "majors-carry", PASSER, self.DESK)
        self.blocks(stale, 0.01, 6)
        self.clock.advance(8 * 86400)  # a week and a day later its blocks are out of the window
        self.foundry._week = None
        self.assertFalse(self.foundry.desk_week().get(self.DESK, {}).get("positive"))
        self.assertNotEqual(self.foundry.allocate(fresh=True)[1], "capacity")
        siblings = [self.member(f"sib-{n}", "majors-sibs", PASSER, self.DESK) for n in range(3)]
        for agent in siblings:  # three members active in the same five blocks are five blocks of their family
            for i in range(5):
                self.house.ledger.append("eval.block", {"log_growth": 0.01, "active": True, "book": "alpaca-paper",
                                                        "key": f"2026-09-10T0{i}"}, agent=agent.id)
        self.foundry._week = None
        self.assertEqual(self.foundry.desk_week()[self.DESK]["blocks"], 5)
        self.assertFalse(self.foundry.desk_week()[self.DESK]["positive"])  # under capacity_min_blocks (6)

    def test_model_calls_rotate_over_the_recorded_feeds_and_leave_founded_leagues_to_their_founders(self):
        self.settings(capacity_share=0, model_share=1.0, exploration_share=0)
        sports = self.house.niches["kalshi-sports"]
        sports.founders = tuple(sports.founders) + (
            {"seed": "sports-consensus", "key": "consensus-nfl", "needs": {"series": ["KXNFLGAME"], "feeds": {"odds": ["nfl"], "sports": ["nfl"]}}},
            {"seed": "sports-consensus", "key": "consensus-mlb", "needs": {"series": ["KXMLBGAME"], "feeds": {"odds": ["mlb"], "sports": ["mlb"]}}})
        picks = []
        for _ in range(8):
            desk, route, reason = self.foundry.allocate(fresh=True)
            self.assertEqual(route, "model")
            picks.append(desk.niche)
            self.record_call(desk.niche, route)
        self.assertEqual(picks, ["kalshi-weather", "alpaca-megacaps", "alpaca-crypto-majors", "kalshi-sports"] * 2)
        model = self.foundry.model_for("kalshi-sports")
        self.assertEqual(model["leagues_with_founders"], ["mlb", "nfl"])
        self.assertIn("already trade mlb, nfl", model["ask"])
        self.assertIn("consensus", model["feeds"])
        self.frontier.candidates = [stating("dvol", "price the majors off DVOL and funding", PASSER)]
        with patch.object(self.house, "_candidate_replay", return_value=replayed()):
            self.foundry.run(self.DESK, "model", "test")
            self.house.wait()
        shown = self.frontier.asked[-1]["user"]
        self.assertEqual(shown["model"]["feeds"], ["vol", "funding"])
        call = [e.payload for e in self.house.ledger.iter(kinds="merton.pass") if e.payload.get("role") == "foundry"][-1]
        self.assertEqual(call["allocation"]["model"], {"feeds": ["vol", "funding"]})

    def test_a_closed_desk_gets_no_capacity_or_model_call(self):
        self.settings(closed_desks=[self.DESK], model_share=0, exploration_share=0)
        earner = self.member("rosenfeld", "majors-carry", PASSER, self.DESK)
        self.blocks(earner, 0.01, 2)  # positive over two blocks: the desk stays closed (three reopen it)
        self.foundry._week = None
        self.settings(closed_reopen_blocks=6, capacity_min_blocks=2)
        self.assertIn(self.DESK, self.foundry._closed_desks())
        picked = self.foundry.allocate(fresh=True)
        self.assertNotEqual(picked[0].niche, self.DESK)


class SpanningCards(CapacityCase):
    """S2: a card whose markets span the desk it was written for and the one its NEEDS match is replayed on both."""

    def by_desk(self, verdicts, seen):
        def replay(agent, code):
            seen.append(agent.specialty)
            return replayed(passed=verdicts[agent.specialty])
        return replay

    def test_a_card_spanning_two_desks_is_replayed_on_both_and_born_where_it_passes(self):
        self.assertEqual(niches.match({"venue": "alpaca", "horizon": "hour", "symbols": ["QQQ", "XLE", "XLF", "GLD", "BTC/USD", "SOL/USD"]},
                                      self.house.niches).id, "alpaca-index-etfs")
        self.frontier.candidates = [stating("spanner", "crypto overnight leads the sector ETFs at the open", SPANNING)]
        seen = []
        with patch.object(self.house, "_candidate_replay",
                          side_effect=self.by_desk({"alpaca-index-etfs": False, "alpaca-open": True}, seen)):
            self.call("alpaca-open")
        self.assertEqual(seen, ["alpaca-index-etfs", "alpaca-open"])  # both tapes, its home desk's first
        outcome = self.evaluation("spanner")
        self.assertEqual((outcome["outcome"], outcome["desk"]), ("passed", "alpaca-open"))
        self.assertEqual([(t["desk"], t["passed"]) for t in outcome["tapes"]], [("alpaca-index-etfs", False), ("alpaca-open", True)])
        self.assertIn("on the alpaca-open tape", outcome["detail"])
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.seated()
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual((child.specialty, child.founder), ("alpaca-open", f"card:{self.card_of('spanner')['id']}"))

    def test_a_card_passing_on_its_home_desk_is_born_there(self):
        self.frontier.candidates = [stating("spanner", "crypto overnight leads the sector ETFs at the open", SPANNING)]
        seen = []
        with patch.object(self.house, "_candidate_replay",
                          side_effect=self.by_desk({"alpaca-index-etfs": True, "alpaca-open": True}, seen)):
            self.call("alpaca-open")
        outcome = self.evaluation("spanner")
        self.assertEqual((outcome["outcome"], outcome["desk"], seen), ("passed", "alpaca-index-etfs", ["alpaca-index-etfs", "alpaca-open"]))
        self.assertEqual(self.foundry.inventory()[0]["desk"], "alpaca-index-etfs")
        self.rules.update(newcomer_seconds=600, max_population=10)
        self.seated()
        self.clock.advance(601)
        child = self.house._refill(self.rules)
        self.assertEqual(child.specialty, "alpaca-index-etfs")
        route = self.house.ledger.get(f"birth-route:{child.id}").payload
        self.assertEqual(route["evidence"]["written_for"], "alpaca-open")

    def test_one_desks_markets_written_for_the_open_desk_are_still_refused_before_any_replay(self):
        """Both desks would show it the same three ETFs: it spans nothing, and the foundry never re-homes a card (six of
        the eight open-desk cards of Sept 23-24 span two desks; the other two named index ETFs only)."""
        self.frontier.candidates = [stating("etfs", "real assets rotate on the rates day", ETFS_ONLY)]
        seen = []
        with patch.object(self.house, "_candidate_replay", side_effect=self.by_desk({}, seen)):
            self.call("alpaca-open")
        outcome = self.evaluation("etfs")
        self.assertEqual((outcome["outcome"], seen), ("invalid", []))
        self.assertIn("alpaca-index-etfs desk", outcome["detail"])

    def test_a_card_for_a_desk_that_also_names_another_desks_markets_is_replayed_on_the_open_tape_too(self):
        """The reverse: written for the index-ETF desk, two ETFs against two coins spans desks, so `match` gives it the open
        desk; it is replayed there (every market it names) and on its own desk's tape (the ETFs)."""
        code = PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY", "QQQ", "BTC/USD", "ETH/USD"]').replace("sawtooth", "lead")
        self.frontier.candidates = [stating("lead", "coins lead the index ETFs into the open", code)]
        seen = []
        with patch.object(self.house, "_candidate_replay",
                          side_effect=self.by_desk({"alpaca-open": False, "alpaca-index-etfs": True}, seen)):
            self.call("alpaca-index-etfs")
        self.assertEqual(seen, ["alpaca-open", "alpaca-index-etfs"])
        self.assertEqual((self.evaluation("lead")["outcome"], self.evaluation("lead")["desk"]), ("passed", "alpaca-index-etfs"))

    def test_a_card_naming_nothing_of_its_own_desk_is_still_refused_before_any_replay(self):
        self.frontier.candidates = [stating("sawtooth", "the BTC sawtooth sent to the megacaps desk", PASSER)]
        seen = []
        with patch.object(self.house, "_candidate_replay", side_effect=self.by_desk({}, seen)):
            self.call("alpaca-megacaps")
        outcome = self.evaluation("sawtooth")
        self.assertEqual((outcome["outcome"], seen), ("invalid", []))
        self.assertIn("alpaca-crypto-majors", outcome["detail"])

    def test_a_card_whose_home_desk_the_search_closed_is_refused(self):
        self.settings(closed_desks=["alpaca-index-etfs"])
        self.frontier.candidates = [stating("spanner", "crypto overnight leads the sector ETFs at the open", SPANNING)]
        seen = []
        with patch.object(self.house, "_candidate_replay", side_effect=self.by_desk({}, seen)):
            self.call("alpaca-open")
        self.assertEqual((self.evaluation("spanner")["outcome"], seen), ("invalid", []))

    def test_the_open_alpaca_desk_has_twelve_seats(self):
        self.assertEqual(niches.load()["alpaca-open"].max_members, 12)
        self.assertIn("Twelve seats", niches.load()["alpaca-open"].brief)


class Bounds(CapacityCase):
    def test_the_foundry_dials_stay_inside_their_bounds(self):
        game = load_game()
        check_bounds(game)
        for key, value in (("min_capacity_usd", 30), ("capacity_days", 1), ("capacity_share", 1.5),
                           ("replay_position_usd", {"kalshi": 5, "alpaca": 100})):
            bad = deepcopy(game)
            bad["hypotheses"][key] = value
            with self.assertRaises(ValueError, msg=key):
                check_bounds(bad)
        over = deepcopy(game)
        over["hypotheses"].update(capacity_share=0.6, model_share=0.3, exploration_share=0.2)
        with self.assertRaisesRegex(ValueError, "route shares add up to 1.1"):
            check_bounds(over)


if __name__ == "__main__":
    import unittest

    unittest.main()
