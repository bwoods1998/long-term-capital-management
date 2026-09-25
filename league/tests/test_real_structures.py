"""Real money follows a structure family's own record (G of the options-desk run, Sept 25, 2026).

The owner, 18:15Z Sept 25: "i want rapid recursively learning loop that has paper trading and production trading as soon
as possible based on actual progress made by the agents in the game". The money rows O1-O5 of
docs/goals/LTCM_OPTIONS_DESK.md: O1 `option_spreads_real` (the switch, false in this deploy), O2 `spread_probe_usd` ($150),
O3 `spread_position_share` (1.0 of the stake in maximum loss), O4 `spread_probe_line` (>= 3 closed practice structures at
W_paper >= 1.01, or >= 1 and a passed replay with >= 20 structures and positive out-of-sample growth) and O5
`evidence.alpaca_paper_haircut_bps.option_spread` (60 bps a side). A structure agent's evidence and its family's record
read its ACTUAL practice book (`options-shadow` today); one flat sale of a structure is one closed trade.
"""

import copy
import math
import tempfile
import unittest
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import allocator, ci, families, seeds, structures
from league.constitution import CONSTITUTION
from league.economy import load_game
from league.book import Holding
from league.house import House, Settings
from league.ledger import Ledger, now_iso
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_house import FakeAlpacaData
from league.tests.test_ladder import FakeAuditor, InProcessSandbox
from league.tests.test_options import STRUCTURE_AGENT, THURSDAY_11_NY, condor_row, fake_chain, occ

D = Decimal


def vertical_row(expiry="2026-09-11", *, action="open", limit=0.45, low=585, right="call"):
    """A $1 SPY debit vertical (buy the dearer strike, sell the next)."""
    high = low + 1
    long_strike, short_strike = (low, high) if right == "call" else (high, low)
    legs = [{"occ": occ(expiry, right, long_strike), "role": "long"}, {"occ": occ(expiry, right, short_strike), "role": "short"}]
    return {"structure": "debit_vertical", "action": action, "quantity": 1, "limit_price": limit, "legs": legs, "reason": "a test vertical"}


def structure_code(venue="options-shadow", low=585):
    """The held instrument of a $1 SPY call vertical, as a fill row names it."""
    return structures.instrument(structures.parse(venue, vertical_row(low=low)).spec, venue).to_dict()


def switched(on=True, **rows):
    """The constitution with O1 `on` (and any other allocator rows changed): a patch."""
    return patch.dict(CONSTITUTION["allocator"], {"option_spreads_real": on, **rows})


class Rows(unittest.TestCase):
    """O1-O5 as the constitution carries them, their bounds, and `league.ci`'s one source of truth for the types."""

    def test_the_constitution_carries_the_rows_inside_their_bounds(self):
        r = CONSTITUTION["allocator"]
        self.assertIs(r["option_spreads_real"], False)  # O1: off in this deploy
        self.assertEqual(r["option_spread_real_types"], ["debit_vertical"])
        self.assertEqual(D(r["spread_probe_usd"]), D("150"))  # O2, the top of $80-150
        self.assertEqual(D(r["spread_position_share"]), D("1.0"))  # O3, the top of 0.5-1.0
        self.assertEqual(r["spread_probe_line"], {"min_practice_closed": 3, "min_w_paper": "1.01", "replay_min_practice_closed": 1,
                                                  "replay_min_structures": 20, "replay_min_oos_growth": "0"})  # O4
        self.assertEqual(r["evidence"]["alpaca_paper_haircut_bps"]["option_spread"], 60)  # O5, the top of 24-60
        self.assertEqual(allocator.spread_problems(), [])
        rule = allocator.spread_rule()
        self.assertEqual((rule["on"], rule["types"], rule["probe_usd"], rule["position_share"]), (False, ("debit_vertical",), D("150"), D("1.0")))
        self.assertFalse(allocator.spreads_real())
        self.assertEqual(allocator.spread_types_real(), ())

    def test_a_value_outside_its_bounds_is_a_problem_and_switches_real_structures_off(self):
        bad = [
            {"spread_probe_usd": "151"}, {"spread_probe_usd": "79.99"}, {"spread_position_share": "1.01"},
            {"spread_position_share": "0.4"}, {"option_spreads_real": "yes"}, {"option_spread_real_types": ["credit_vertical"]},
            {"option_spread_real_types": ["debit_vertical", "iron_condor"]}, {"option_spread_real_types": []},
            {"option_spread_real_types": ["debit_vertical", "debit_vertical"]},
            {"spread_probe_line": {**CONSTITUTION["allocator"]["spread_probe_line"], "min_practice_closed": 2}},
            {"spread_probe_line": {**CONSTITUTION["allocator"]["spread_probe_line"], "min_w_paper": "1.0"}},
            {"spread_probe_line": {**CONSTITUTION["allocator"]["spread_probe_line"], "replay_min_structures": 19}},
            {"spread_probe_line": {**CONSTITUTION["allocator"]["spread_probe_line"], "replay_min_oos_growth": "-0.0005"}},
            {"spread_probe_line": {**CONSTITUTION["allocator"]["spread_probe_line"], "replay_min_practice_closed": 0}},
            {"spread_probe_line": {"min_practice_closed": 3}},
        ]
        for change in bad:
            c = copy.deepcopy(CONSTITUTION)
            c["allocator"].update(change)
            c["allocator"]["option_spreads_real"] = change.get("option_spreads_real", True)
            self.assertTrue(allocator.spread_problems(c), change)
            self.assertIsNone(allocator.spread_rule(c), change)
            self.assertFalse(allocator.spreads_real(c), change)
            self.assertEqual(allocator.spread_types_real(c), (), change)
        for rate in (23, 61):
            c = copy.deepcopy(CONSTITUTION)
            c["allocator"]["evidence"]["alpaca_paper_haircut_bps"]["option_spread"] = rate
            self.assertTrue(allocator.spread_problems(c))
        # Stricter than the row is allowed; the rows absent (a rollback's constitution) are no problem and no switch.
        c = copy.deepcopy(CONSTITUTION)
        c["allocator"].update(option_spreads_real=True, spread_probe_usd="80",
                              spread_probe_line={**c["allocator"]["spread_probe_line"], "min_practice_closed": 5, "min_w_paper": "1.05"})
        self.assertEqual(allocator.spread_problems(c), [])
        self.assertEqual(allocator.spread_types_real(c), ("debit_vertical",))
        c = copy.deepcopy(CONSTITUTION)
        for key in ("option_spreads_real", "option_spread_real_types", "spread_probe_usd", "spread_position_share", "spread_probe_line"):
            c["allocator"].pop(key)
        c["allocator"]["evidence"]["alpaca_paper_haircut_bps"].pop("option_spread")
        self.assertEqual(allocator.spread_problems(c), [])
        self.assertIsNone(allocator.spread_rule(c))

    def test_the_rows_come_together(self):
        c = copy.deepcopy(CONSTITUTION)
        c["allocator"].pop("spread_probe_line")
        self.assertIn("missing spread_probe_line", " ".join(allocator.spread_problems(c)))


class OneSourceOfTruth(unittest.TestCase):
    """`league.ci` (`check_structures`): the gateway's OPTION_STRUCTURES_REAL admits exactly the types the constitution opens
    on real money -- `option_spread_real_types` while O1 is on, none while it is off."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        (self.root / "league").mkdir()
        (self.root / "gateway").mkdir()
        self.constitution = (ci.REPO / "league" / "constitution.py").read_text(encoding="utf-8")
        self.wrangler = (ci.REPO / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")

    def tearDown(self):
        self.dir.cleanup()

    def tree(self, *, on=False, gateway="off", types=None):
        text = self.constitution.replace('"option_spreads_real": False,', f'"option_spreads_real": {on},')
        if types is not None:
            text = text.replace('"option_spread_real_types": ["debit_vertical"],', f'"option_spread_real_types": {types!r},')
        (self.root / "league" / "constitution.py").write_text(text, encoding="utf-8")
        (self.root / "gateway" / "wrangler.jsonc").write_text(
            self.wrangler.replace('"OPTION_STRUCTURES_REAL": "off",', f'"OPTION_STRUCTURES_REAL": "{gateway}",'), encoding="utf-8")
        return ci.check_structures(self.root)

    def test_the_repository_as_it_stands_agrees(self):
        self.assertEqual(ci.check_structures(), [])
        self.assertEqual(ci.gateway_structures(), ([], []))

    def test_the_switch_and_the_gateway_change_together(self):
        self.assertEqual(self.tree(on=False, gateway="off"), [])
        self.assertEqual(self.tree(on=True, gateway="debit_vertical"), [])
        self.assertEqual(self.tree(on=True, gateway=" debit_vertical, "), [])
        refused = self.tree(on=True, gateway="off")
        self.assertEqual(len(refused), 1)
        self.assertIn("admits none on the real account, but the constitution opens ['debit_vertical']", refused[0])
        self.assertIn("admits ['debit_vertical'] on the real account, but the constitution opens none",
                      self.tree(on=False, gateway="debit_vertical")[0])
        self.assertIn("iron_condor", self.tree(on=True, gateway="debit_vertical,iron_condor")[0])
        # A typo would admit none at the gateway, silently: refused whatever the switch says.
        self.assertIn("debit_verticle, not a structure type", self.tree(on=False, gateway="debit_verticle")[0])
        # A credit type in the constitution is refused by the bounds before any comparison.
        self.assertIn("owner's explicit confirmation", " ".join(self.tree(on=True, gateway="credit_vertical", types=["credit_vertical"])))

    def test_the_check_runs_in_league_ci(self):
        with patch.object(ci, "check_structures", return_value=["the structures disagree"]) as check, \
                patch.object(ci, "check_strategies", return_value=[]), patch.object(ci, "check_tools", return_value=[]):
            self.assertIn("the structures disagree", ci.check(None, None, tests=False))
        check.assert_called_once()


class HaircutAndRecord(unittest.TestCase):
    """O5 on a structure's fills, and the family record's closed structures on the options shadow book."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def fill(self, side, price, *, agent="a", book="options-shadow", instrument=None, realized=None, flat=None):
        inst = instrument or structure_code(book if book != "alpaca" else "alpaca")
        cash = D(price) * 100 * (-1 if side == "buy" else 1)
        self.ledger.append("book.fill", {"book": book, "source": "venue", "side": side, "quantity": "1", "price": price,
                                         "instrument": inst, "realized": realized, "flat": flat, "cash_delta": str(cash),
                                         "liquidity": "taker"}, agent=agent)

    def test_a_structure_fill_pays_the_option_spread_rate_and_a_single_contract_its_own(self):
        table = CONSTITUTION["allocator"]["evidence"]["alpaca_paper_haircut_bps"]
        self.ledger.append("book.stake", {"book": "options-shadow", "usd": "200", "note": "t"}, agent="a")
        self.fill("buy", "0.46")  # $46 of maximum loss
        cut = allocator._paper_haircut(SimpleNamespace(ledger=self.ledger), "a", "options-shadow", table)
        self.assertAlmostEqual(cut, 46 * 60 / 10_000 / 200, places=12)
        single = {"asset_class": "option", "symbol": "SPY", "market_id": None, "multiplier": "100"}
        self.fill("buy", "0.40", instrument=single)
        cut = allocator._paper_haircut(SimpleNamespace(ledger=self.ledger), "a", "options-shadow", table)
        self.assertAlmostEqual(cut, (46 * 60 + 40 * 24) / 10_000 / 200, places=12)
        # Without the row a structure pays the table's largest rate, never nothing.
        self.assertEqual(allocator._haircut_rate({"crypto": 4, "option": 24}, "option", structure=True), 24.0)
        self.assertEqual(allocator._haircut_rate(10, "option", structure=True), 10.0)
        self.assertEqual(allocator.HAIRCUT_BOOKS, ("alpaca-paper", "options-shadow"))

    def test_the_family_record_counts_each_closed_structure_once_on_its_practice_book_after_the_haircut(self):
        members = [SimpleNamespace(id="a", family="fam", venue="alpaca", alive=True)]
        house = SimpleNamespace(ledger=self.ledger, registry=SimpleNamespace(agents={m.id: m for m in members}))
        self.ledger.append("book.stake", {"book": "options-shadow", "usd": "200", "note": "t"}, agent="a")
        for low, sold in ((585, "0.66"), (586, "0.36"), (587, "0.61")):
            inst = structure_code(low=low)
            self.fill("buy", "0.46", instrument=inst)
            realized = str((D(sold) - D("0.46")) * 100)
            self.fill("sell", sold, instrument=inst, realized=realized, flat=True)
        record = families.family_record(house, "fam", "alpaca")
        mine = record["structures"]
        self.assertEqual((mine["practice_closed"], mine["real_closed"]), (3, 0))
        # Each close's account growth after its two fills' 60 bps: +20, -10, +15 dollars on a $200 purse.
        expected = 0.0
        for made, buy, sell in ((20.0, 46.0, 66.0), (-10.0, 46.0, 36.0), (15.0, 46.0, 61.0)):
            expected += math.log1p((made - (buy + sell) * 60 / 10_000) / 200)
        self.assertAlmostEqual(mine["practice_log"], expected, places=9)
        self.assertEqual(record["n"], 3, "the practice closes are the family's observations too")
        # A single contract's close is a closed trade of the family, not a closed structure.
        single = {"asset_class": "option", "symbol": "SPY", "market_id": None, "multiplier": "100", "expiry": "2026-09-11",
                  "strike": "590", "right": "call"}
        self.fill("buy", "0.40", instrument=single)
        self.fill("sell", "0.50", instrument=single, realized="10", flat=True)
        again = families.family_record(house, "fam", "alpaca")
        self.assertEqual((again["structures"]["practice_closed"], again["n"]), (3, 4))


class RealStructuresHouse(unittest.TestCase):
    """A House with the options shadow book, a real (fake) Alpaca account and real money on, in the session."""

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch("league.strategies.all_strategies", return_value=[]))
        # The Alpaca envelope: the tuition line stands in for the grant's $500 when no grant is read.
        stack.enter_context(patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "1000"}))
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.clock.now = THURSDAY_11_NY
        self.paper, self.shadow = FakeBroker("alpaca-paper"), FakeBroker("options-shadow")
        # Track P's adapter says it sends a structure as ONE multi-leg order (`mleg`, g/trackp's ltcm/adapters/alpaca.py).
        self.real = FakeBroker("alpaca", cash="800", caps={"equity", "option", "crypto", "limit", "gtc", "ioc", "fractional", "mleg"})
        for broker in (self.paper, self.shadow, self.real):
            broker.clock_iso = now_iso(self.clock)
        self.data = FakeAlpacaData()
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.auditor = FakeAuditor()
        self.house = House(Path(self.dir.name) / "house",
                           brokers={"alpaca-paper": self.paper, "alpaca": self.real, "options-shadow": self.shadow},
                           sandbox=InProcessSandbox(), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game, auditor=self.auditor)
        self.addCleanup(self.house.close, wait=None)
        self.house.structure_book_name = "options-shadow"
        self.auditor.ledger = self.house.ledger

    def structure_agent(self, style, structure="debit_vertical"):
        """A structure agent whose PARAMS open `structure` (a debit vertical unless named: the one type real money may open)."""
        code = STRUCTURE_AGENT.replace("test-structures", style).replace('"structure": "iron_condor"', f'"structure": "{structure}"')
        agent = self.house.spawn(style, style, code, reason="test", specialty="alpaca-options")
        self.house.seat(agent)  # its practice stake, as its first wake lends it
        self.assertTrue(self.house.is_structure_agent(agent))
        self.assertEqual((self.house.evaluator.rung(agent.id), self.house.book_of(agent).name), (1, "options-shadow"))
        return agent

    def close_structures(self, agent, sold, *, low=585):
        """Closed practice structures on the options shadow book, as its fills write them: each bought at 0.46 and
        sold flat at `sold`."""
        for i, price in enumerate(sold):
            inst = structure_code(low=low + i)
            for side, px, realized, flat in (("buy", "0.46", None, None), ("sell", price, str((D(price) - D("0.46")) * 100), True)):
                cash = D(px) * 100 * (-1 if side == "buy" else 1)
                self.house.ledger.append("book.fill", {"book": "options-shadow", "source": "venue", "side": side, "quantity": "1",
                                                       "price": px, "instrument": inst, "realized": realized, "flat": flat,
                                                       "cash_delta": str(cash), "liquidity": "taker"}, agent=agent.id)
        self.mark(agent)

    def mark(self, agent, book="options-shadow"):
        """The book's mark of the agent's equity after its closes, as the book writes one (what `Evaluator.wealth`, and so
        the agent's evidence, reads): its stake plus what its closes on the book realized, nothing held."""
        realized = sum((D(e.payload["realized"]) for e in self.house.ledger.iter(kinds="book.fill", agent=agent.id)
                        if e.payload.get("book") == book and e.payload.get("realized") is not None), D(0))
        staked = self.house.books[book].account(agent.id).staked
        self.house.ledger.append("book.mark", {"book": book, "equity": str(staked + realized), "cash": str(staked + realized),
                                               "staked": str(staked), "realized": str(realized), "fees": "0", "holdings": 0,
                                               "real_money": False}, agent=agent.id)

    def passed_replay(self, agent, *, trades=24, oos=0.0012, passed=True, code=None, params=None):
        """A House replay's `eval.trial`, of the agent's own program (its code and PARAMS) unless told otherwise."""
        self.house.ledger.append("eval.trial", {"family": agent.family, "code_sha256": code or agent.code_sha256, "trades": trades,
                                                "blocks": 40, "oos_mean_log_growth": oos, "passed": passed, "reasons": [],
                                                "params": dict(agent.params) if params is None else params},
                                 agent=agent.id)

    def rung(self, agent):
        return self.house.evaluator.rung(agent.id)

    def on_real_money(self, agent):
        """The agent on rung 2, where only the allocator's seat puts it: no structure order of a rung-1 agent goes to a real
        book (`House._structure_refusal`, the review of Deploy G, Sept 25, 2026)."""
        self.house.evaluator.seat(agent.id, 2, "a test: seated on real money")
        return agent

    def promoted(self, agent):
        return [e.payload for e in self.house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "promote"]


class TheLadder(RealStructuresHouse):
    def test_with_o1_off_nothing_is_promoted_and_with_o1_on_the_first_family_to_meet_o4_is_within_one_pass(self):
        house, alloc = self.house, self.house.allocator
        winner = self.structure_agent("test-winner")  # 3 closed practice structures, +$45: meets O4 by its record
        short = self.structure_agent("test-short")  # 2 closed winners: one short of the line
        loser = self.structure_agent("test-loser")  # 3 closed, down: W_paper under 1.01
        near = self.structure_agent("test-near")  # 1 closed and a passed replay whose out of sample is NOT positive
        self.assertEqual(len({a.family for a in (winner, short, loser, near)}), 4)
        self.close_structures(winner, ["0.66", "0.56", "0.61"])
        self.close_structures(short, ["0.76", "0.76"])
        self.close_structures(loser, ["0.36", "0.56", "0.41"])
        self.close_structures(near, ["0.50"])
        self.passed_replay(near, oos=-0.00024)  # options-gap-drift's own number: inside the replay floor, not positive
        everyone = (winner, short, loser, near)

        # O1 off (this deploy): no structure agent reaches real money by any route, however good its record or its E.
        table = {a.id: dict(e=1.5, w_paper=2.25, paper_trades=10) for a in everyone}
        real_evidence = allocator.evidence

        def high_e(h, agent, rung=None):
            row = real_evidence(h, agent, rung)
            if agent.id in table:
                for key, value in table[agent.id].items():
                    setattr(row, key, value)
            return row
        with patch.object(allocator, "evidence", side_effect=high_e):
            for _ in range(3):
                alloc.rebalance()
        self.assertEqual([self.rung(a) for a in everyone], [1, 1, 1, 1])
        status = house._state["promotion_status"][winner.id]
        self.assertEqual(status["stage"], "spread_line")
        self.assertIn("owner's switch", status["reason"])
        self.assertFalse(alloc.board()["spread"]["on"])
        self.assertTrue(alloc.board()["spread"]["families"][winner.family]["meets"])

        # O1 on: the family that meets O4 has its best member seated as a probe, staked O2, in one pass.
        with switched(True):
            alloc.rebalance()
            self.assertEqual(self.rung(winner), 2)
            promote = self.promoted(winner)[-1]
            self.assertEqual((promote["band_from"], promote["band_to"], promote["stake_usd"], promote["rule"]),
                             ("paper", "probe", "150", "allocator.spread_probe_line"))
            self.assertEqual((promote["spread_line"]["route"], promote["spread_line"]["practice_closed"]), ("practice", 3))
            real = house.books["alpaca"]
            self.assertEqual(real.account(winner.id).staked, D("150"))
            # O3: a position of the whole stake in maximum loss, every order within the gateway's $75.
            limits = real.limits[winner.id]
            self.assertEqual((limits.max_position_usd, limits.max_order_usd, limits.asset_classes), (D("150.00"), D("75"), ("option",)))
            # No family that does not meet the line is ever promoted, pass after pass, even on an E far over the bunt line.
            with patch.object(allocator, "evidence", side_effect=high_e):
                for _ in range(3):
                    alloc.rebalance()
            self.assertEqual([self.rung(a) for a in (short, loser, near)], [1, 1, 1])
            self.assertEqual([self.promoted(a) for a in (short, loser, near)], [[], [], []])
            lines = alloc.board()["spread"]["families"]
            self.assertEqual({f: row["meets"] for f, row in lines.items()},
                             {winner.family: True, short.family: False, loser.family: False, near.family: False})
            self.assertLess(lines[loser.family]["w_paper"], 1.01)
            self.assertIn("2 closed practice debit_vertical structures", house._state["promotion_status"][short.id]["reason"])

            # The first family to meet the line is promoted at the very next pass: its third closed structure ...
            self.close_structures(short, ["0.70"], low=595)
            alloc.rebalance()
            self.assertEqual(self.rung(short), 2)
            # ... and the replay route: one closed practice structure and a passed replay with positive growth out of sample.
            self.passed_replay(near, trades=19, oos=0.002)  # too few structures
            alloc.rebalance()
            self.assertEqual(self.rung(near), 1)
            self.passed_replay(near, oos=0.0005, code="another-program")  # not a program the family ran
            alloc.rebalance()
            self.assertEqual(self.rung(near), 1)
            self.passed_replay(near, oos=0.0005)
            alloc.rebalance()
            self.assertEqual(self.rung(near), 2)
            self.assertEqual(self.promoted(near)[-1]["spread_line"]["route"], "replay")
            self.assertEqual(self.rung(loser), 1)

    def test_one_probe_a_family_its_best_member_and_r5_unchanged(self):
        house, alloc = self.house, self.house.allocator
        first = self.structure_agent("test-pair")
        second = house.spawn("test-pair", first.family, first.code, reason="a second member", specialty="alpaca-options")
        house.seat(second)
        self.assertEqual(second.family, first.family)
        self.close_structures(first, ["0.66", "0.56"])
        self.close_structures(second, ["0.61"], low=590)  # the family's pooled record: 3 closed structures
        with switched(True), patch.object(allocator, "evidence", side_effect=self.w_paper({first.id: 1.02, second.id: 1.04})):
            alloc.rebalance()
            self.assertEqual((self.rung(first), self.rung(second)), (1, 2))  # the best W_paper of the family
            alloc.rebalance()
            self.assertEqual(self.rung(first), 1, "one structure probe a family at a time")
        # R5: a family whose pooled forward record is losing seats no probe, whatever its structures.
        third = self.structure_agent("test-losing")
        self.close_structures(third, ["0.66", "0.56", "0.61"], low=600)
        with switched(True), patch.object(type(alloc), "family_forward", return_value={third.family: (8, -0.05)}):
            alloc.rebalance()
        self.assertEqual(self.rung(third), 1)
        self.assertEqual(house._state["promotion_status"][third.id]["stage"], "family_losing")

    def w_paper(self, table):
        real_evidence = allocator.evidence

        def fake(h, agent, rung=None):
            row = real_evidence(h, agent, rung)
            if agent.id in table:
                row.w_paper = table[agent.id]
            return row
        return fake

    def test_o1_off_again_sends_a_flat_structure_probe_back_and_lends_it_nothing(self):
        house, alloc = self.house, self.house.allocator
        agent = self.structure_agent("test-back")
        self.close_structures(agent, ["0.66", "0.56", "0.61"])
        with switched(True):
            alloc.rebalance()
        self.assertEqual(self.rung(agent), 2)
        ev = allocator.evidence(house, agent)
        with patch.object(type(alloc), "target_stake", return_value=D("400")):
            self.assertIsNone(alloc._size(agent, ev, "bunt", allocator._params()), "O1 off: nothing more is lent")
        alloc.rebalance()
        self.assertEqual(self.rung(agent), 1)
        demote = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual(demote["rule"], "allocator.option_spreads_real")
        self.assertEqual(house.book_of(agent).name, "options-shadow")

    def test_a_seated_structure_agent_that_rewrites_itself_to_another_type_goes_back_once_flat(self):
        """The review of g/money (Sept 25, 2026): a seat whose program opens a type real money does not admit is idle money."""
        house, alloc = self.house, self.house.allocator
        agent = self.structure_agent("test-rewrites")
        self.close_structures(agent, ["0.66", "0.56", "0.61"])
        with switched(True):
            alloc.rebalance()
            self.assertEqual(self.rung(agent), 2)
            self.assertTrue(alloc.structure_real_ok(agent))
            agent.params = {**agent.params, "structure": "iron_condor"}  # its rewrite, as `agent.strategy` sets it
            self.assertFalse(alloc.structure_real_ok(agent))
            self.assertFalse(alloc.swing_allowed(agent))
            with patch.object(type(alloc), "target_stake", return_value=D("400")):
                self.assertIsNone(alloc._size(agent, allocator.evidence(house, agent), "bunt", allocator._params()))
            alloc.rebalance()
        self.assertEqual(self.rung(agent), 1)
        demote = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "demote"][-1]
        self.assertEqual(demote["rule"], "allocator.option_spread_real_types")

    def test_a_structure_agents_evidence_and_verdicts_read_its_structure_book(self):
        agent = self.structure_agent("test-evidence")
        self.close_structures(agent, ["0.66", "0.56"])
        ev = allocator.evidence(self.house, agent)
        self.assertEqual((ev.paper_book, ev.paper_trades), ("options-shadow", 2))
        self.assertGreater(ev.haircut_log, 0.0, "the O5 haircut is taken on the options shadow book")
        self.assertEqual(allocator._verdict(agent.id, 1, "test", ev).numbers["book"], "options-shadow")
        self.assertEqual(allocator.practice_book(self.house, agent), "options-shadow")
        self.assertIs(self.house.practice_book(agent), self.house.books["options-shadow"])
        single = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"),
                                  reason="test", specialty="alpaca-options")
        self.assertEqual(allocator.practice_book(self.house, single), "alpaca-paper")

    def test_a_structure_agents_evidence_pools_every_practice_book_it_was_staked_on(self):
        """The review of g/money (Sept 25, 2026, the coordination with Track P): a structure agent moving between practice
        books keeps its whole record -- its evidence reads each practice book of its venue it was ever staked on, as its
        family's record does -- and an agent never staked on a second book reads its one book as before."""
        agent = self.structure_agent("test-two-books")
        self.close_structures(agent, ["0.66", "0.56"])  # on options-shadow, its structure book now
        alone = allocator.evidence(self.house, agent)
        self.assertEqual(alone.paper_trades, 2)
        # A stretch on alpaca-paper: staked there, one structure closed there, marked.
        self.house.ledger.append("book.stake", {"book": "alpaca-paper", "usd": "200", "note": "t"}, agent=agent.id)
        inst = structure_code("alpaca-paper", low=600)
        for side, px, realized, flat in (("buy", "0.46", None, None), ("sell", "0.66", "20", True)):
            self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue", "side": side, "quantity": "1",
                                                   "price": px, "instrument": inst, "realized": realized, "flat": flat,
                                                   "cash_delta": str(D(px) * 100 * (-1 if side == "buy" else 1)),
                                                   "liquidity": "taker"}, agent=agent.id)
        self.house.ledger.append("book.mark", {"book": "alpaca-paper", "equity": "220", "cash": "220", "staked": "200",
                                               "realized": "20", "fees": "0", "holdings": 0, "real_money": False}, agent=agent.id)
        both = allocator.evidence(self.house, agent)
        self.assertEqual((both.paper_trades, both.paper_book), (3, "options-shadow"))
        self.assertAlmostEqual(math.log(both.w_paper) + both.haircut_log,
                               math.log(alone.w_paper) + alone.haircut_log + math.log(220 / 200), places=9)
        self.assertGreater(both.haircut_log, alone.haircut_log, "the O5 haircut is paid on both books")

    def test_a_structure_agent_is_shown_its_familys_spread_line_not_the_bunt_line(self):
        agent = self.structure_agent("test-line")
        self.close_structures(agent, ["0.66", "0.56"])
        self.house.allocator.rebalance()
        line = self.house.bunt_line(agent)
        self.assertEqual((line["route"], line["option_spreads_real"]), ("allocator.spread_probe_line", False))
        self.assertEqual((line["family"]["practice_closed"], line["family"]["meets"]), (2, False))
        self.assertEqual(line["line"]["min_practice_closed"], 3)

    def test_an_audited_seat_is_committed_only_while_o1_and_o4_still_hold(self):
        house, alloc = self.house, self.house.allocator
        agent = self.structure_agent("test-audit")
        self.close_structures(agent, ["0.66", "0.56", "0.61"])
        ev = allocator.evidence(house, agent)
        verdict = allocator._verdict(agent.id, 1, "test", ev)
        alloc._begin_pass()
        alloc._evidence = {agent.id: ev}  # the last pass's evidence, as an audit finishing after it reads it
        self.assertTrue(alloc.refuses_probe(agent, verdict), "O1 off")
        self.assertIn("owner's switch", house._state["promotion_status"][agent.id]["reason"])
        with switched(True):
            self.assertFalse(alloc.refuses_probe(agent, verdict))


class TheHouseOnRealMoney(RealStructuresHouse):
    """The House's structure hooks on the real book: an OPEN only while O1 is on and of an admitted type; a close always."""

    def refusals(self, agent):
        return [r for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id) for r in e.payload["reasons"]]

    def test_opens_wait_for_the_switch_and_closes_always_go(self):
        agent = self.on_real_money(self.structure_agent("test-real"))
        real = self.house.books["alpaca"]
        intents, dropped = self.house._intents(agent, real, [vertical_row(), vertical_row(action="close", limit=0.40)])
        self.assertEqual(dropped, [])
        self.assertEqual([(i.side, i.instrument.venue) for i in intents], [("sell", "alpaca")], "the close goes")
        self.assertIn("owner's switch (O1: allocator.option_spreads_real is off)", self.refusals(agent)[0])

    def test_with_o1_on_a_debit_vertical_goes_to_the_real_book_and_a_credit_type_is_refused(self):
        agent = self.on_real_money(self.structure_agent("test-real-on"))
        real = self.house.books["alpaca"]
        with switched(True):
            intents, dropped = self.house._intents(agent, real, [vertical_row(), condor_row()])
        self.assertEqual(dropped, [])
        self.assertEqual(len(intents), 1)
        opened = intents[0]
        spec = structures.parse("alpaca", vertical_row()).spec
        self.assertEqual(opened.instrument, structures.instrument(spec, "alpaca"))
        self.assertEqual((opened.side, opened.order_type, opened.limit_price), ("buy", "limit", D("0.45")))
        self.assertIn("an iron_condor is not admitted on real money: allocator.option_spread_real_types admits debit_vertical",
                      self.refusals(agent)[0])
        # The structure book is still the one place its practice goes; a real intent on the practice book is refused as before.
        shadow = self.house.books["options-shadow"]
        with switched(True):
            intents, _ = self.house._intents(agent, shadow, [vertical_row()])
        self.assertEqual(len(intents), 1)

    def test_no_real_structure_order_open_or_close_through_an_adapter_that_cannot_send_one_multi_leg_order(self):
        """Without `mleg` the adapter would spell the held instrument as its first leg's OCC code: one leg alone. On a close
        that is legging OUT, which leaves the short leg naked (the review of g/money, Sept 25, 2026, MINOR: until then the
        close went). The agent's close, the House's expiry close and its wind-down all hold back, with one error a day."""
        house = self.house
        agent = self.on_real_money(self.structure_agent("test-real-legs"))
        real = house.books["alpaca"]
        self.real.caps.discard("mleg")
        with switched(True):
            intents, _ = house._intents(agent, real, [vertical_row(), vertical_row(action="close", limit=0.40)])
        self.assertEqual(intents, [], "neither the open nor the close is sent")
        refused = self.refusals(agent)
        self.assertEqual(len(refused), 2)
        for reason in refused:
            self.assertIn("cannot send a structure as one multi-leg order (no `mleg` capability)", reason)
        errors = [e.payload["text"] for e in house.ledger.iter(kinds="ops.alert") if e.payload.get("level") == "error"]
        self.assertEqual(len(errors), 1, "the close is an error on the record, once")
        self.assertIn("cannot be closed", errors[0])
        # The House's own sales of a held real structure: its expiry close and its wind-down send nothing either.
        inst = structures.instrument(structures.parse("alpaca", vertical_row(expiry="2026-09-10")).spec, "alpaca")
        real.account(agent.id).holdings[inst.key] = Holding(inst, D(1), D("46"))
        holding = real.account(agent.id).holdings[inst.key]
        self.assertIsNone(house._structure_expiry_close(real, agent.id, holding, "2026-09-10", 15.6, now_iso(self.clock)))
        with patch.object(house, "_structure_sale", wraps=house._structure_sale) as sale:
            house._wind_down(agent, real)
        sale.assert_not_called()
        self.assertEqual(self.real.submitted, [], "nothing reached the venue")
        # With the capability back, the expiry close is priced again (the unsendable check is the only thing that changed).
        self.real.caps.add("mleg")
        self.assertEqual(house._structure_unsendable(real, agent.id, inst, "close"), "")

    def test_a_structure_agent_is_shown_only_what_real_money_admits(self):
        agent = self.structure_agent("test-real-ctx")
        real = self.house.books["alpaca"]
        ctx = {"quotes": {"SPY": {"bid": 585.4, "ask": 585.6}}}
        chain = fake_chain()("SPY", expiry_from="2026-09-10", expiry_to="2026-09-14")
        with patch.object(self.house, "_chain", return_value=chain):
            self.house._structure_context(agent, ctx, ["SPY"], D("75"), D("150"), book=real)
            self.assertEqual(ctx["structures"], [])
            self.assertIn("off", ctx["structure_rules"]["real_money_opens"])
            self.assertEqual(ctx["structure_rules"]["book"], "alpaca")
            with switched(True):
                self.house._structure_context(agent, ctx, ["SPY"], D("75"), D("150"), book=real)
        self.assertTrue(ctx["structures"])
        self.assertEqual({row["structure"] for row in ctx["structures"]}, {"debit_vertical"})
        self.assertEqual(ctx["structure_rules"]["real_money_opens"], ["debit_vertical"])

    def test_a_structure_agents_real_limits_are_the_allocators(self):
        agent = self.structure_agent("test-limits")
        limits = self.house._limits(2, agent, D("150"))
        self.assertEqual((limits.max_position_usd, limits.max_order_usd), (D("150.00"), D("75")))
        single = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"),
                                  reason="test", specialty="alpaca-options")
        limits = self.house._limits(2, single, D("80"))
        self.assertEqual((limits.max_position_usd, limits.max_order_usd), (D("40.00"), D("40.00")))  # a single contract: unchanged
        self.assertEqual(self.house.allocator.target_stake(agent, "bunt"), D("150"))
        self.assertEqual(self.house.allocator.target_stake(single, "bunt"), D("80"))


def condor_code(low=570):
    """The held instrument of a $1-winged SPY iron condor on the options shadow book, its strikes shifted by `low`."""
    row = condor_row()
    for leg, k in zip(row["legs"], (low, low + 1, low + 10, low + 11)):
        leg["occ"] = leg["occ"][:-8] + f"{int(k * 1000):08d}"
    return structures.instrument(structures.parse("options-shadow", row).spec, "options-shadow").to_dict()


class TheReviewOfGMoney(RealStructuresHouse):
    """The adversarial review of g/money (Sept 25, 2026): its demonstrations, fixed. O4 is the line of the types real money
    may open, judged on programs the family ran; a probe is staked O2 at most; closes hide no held losers; no real open nets
    against a contract the real book holds on the other side."""

    def close_condors(self, agent, sold, *, low=570):
        for i, price in enumerate(sold):
            inst = condor_code(low=low + 12 * i)
            for side, px, realized, flat in (("buy", "0.62", None, None), ("sell", price, str((D(price) - D("0.62")) * 100), True)):
                cash = D(px) * 100 * (-1 if side == "buy" else 1)
                self.house.ledger.append("book.fill", {"book": "options-shadow", "source": "venue", "side": side, "quantity": "1",
                                                       "price": px, "instrument": inst, "realized": realized, "flat": flat,
                                                       "cash_delta": str(cash), "liquidity": "taker"}, agent=agent.id)
        self.mark(agent)

    def test_a_condor_only_family_is_never_seated_on_debit_vertical_money(self):
        """MAJOR 1, the reviewer's first demonstration: three closed practice iron condors and no vertical seated a $150 real
        probe. Now the line counts only the types real money may open, and only a member whose program opens one is seated."""
        house, alloc = self.house, self.house.allocator
        condors = self.structure_agent("test-condor-only", structure="iron_condor")
        self.close_condors(condors, ["0.82", "0.72", "0.77"])  # three winning condors: W_paper far over 1.01
        # A vertical program whose family's record is condors only (its PARAMS changed since, say), and a condor program
        # whose family's record is verticals.
        rewritten = self.structure_agent("test-rewritten")
        self.close_condors(rewritten, ["0.82", "0.72", "0.77"], low=400)
        mismatched = self.structure_agent("test-mismatched", structure="iron_condor")
        self.close_structures(mismatched, ["0.66", "0.56", "0.61"])
        with switched(True):
            for _ in range(2):
                alloc.rebalance()
            lines = alloc.board()["spread"]["families"]
        self.assertEqual([self.rung(a) for a in (condors, rewritten, mismatched)], [1, 1, 1])
        self.assertEqual(house.books["alpaca"].account(condors.id).staked, D("0"))
        for agent in (condors, rewritten):
            line = lines[agent.family]
            self.assertEqual((line["meets"], line["practice_closed"], line["all_types_closed"], line["types"]),
                             (False, 0, 3, ["debit_vertical"]))
        self.assertTrue(lines[mismatched.family]["meets"], "its record is verticals ...")
        self.assertIn("opens iron_condor (PARAMS \"structure\"), not a type real money may open (debit_vertical",
                      house._state["promotion_status"][mismatched.id]["reason"])  # ... but its program opens condors
        self.assertIn("0 closed practice debit_vertical structures", house._state["promotion_status"][rewritten.id]["reason"])
        record = alloc.family(condors.family, "alpaca")["structures"]
        self.assertEqual(record["by_type"]["iron_condor"]["practice_closed"], 3)
        self.assertNotIn("debit_vertical", record["by_type"])

    def test_the_replay_route_takes_only_a_trial_of_a_program_a_member_ran_of_an_admitted_type(self):
        """MAJOR 1, the reviewer's second demonstration: a passed trial of the family's code with PARAMS no member runs (a
        condor variant, a research candidate never adopted) seated the family's best member."""
        agent = self.structure_agent("test-params")
        self.close_structures(agent, ["0.50"])  # one closed practice vertical
        alloc = self.house.allocator
        for params in ({"structure": "iron_condor", "width": 5.0}, {**agent.params, "width": 5.0}, None):
            self.passed_replay(agent, oos=0.001, params=params if params is not None else {})
            if params is None:  # a trial that names no PARAMS at all is no program the family ran
                self.house.ledger.append("eval.trial", {"family": agent.family, "code_sha256": agent.code_sha256, "trades": 24,
                                                        "blocks": 40, "oos_mean_log_growth": 0.001, "passed": True, "reasons": []},
                                         agent=agent.id)
            with switched(True):
                alloc.rebalance()
            self.assertEqual(self.rung(agent), 1, params)
            self.assertIsNone(alloc.board()["spread"]["families"][agent.family]["replay"])
        self.passed_replay(agent, oos=0.001)  # its own program: code and PARAMS
        with switched(True):
            alloc.rebalance()
        self.assertEqual(self.rung(agent), 2)
        promote = self.promoted(agent)[-1]
        self.assertEqual((promote["spread_line"]["route"], promote["spread_line"]["replay"]["structure"]), ("replay", "debit_vertical"))
        # PARAMS compare as JSON would write them, keys in any order.
        self.assertEqual(allocator._params_key({"width": 1.0, "structure": "x"}), allocator._params_key({"structure": "x", "width": 1.0}))

    def test_a_probe_reseat_is_staked_at_o2_at_most(self):
        """MINOR, the reviewer's demonstration: `bunt_stake` grew the O2 base by W_real, so a probe re-seated after a winning
        real stay was staked $180 at tier probe."""
        agent = self.structure_agent("test-restake")
        alloc = self.house.allocator
        ev = allocator.evidence(self.house, agent)
        ev.w_real = 1.2
        with switched(True):
            self.assertEqual(alloc.tier(agent), "probe")
            self.assertEqual(alloc.target_stake(agent, "bunt", ev), D("150"))
            self.assertEqual(alloc.target_stake(agent, "probe", ev), D("150"))

    def test_closes_that_hide_losers_still_held_seat_nothing(self):
        """MINOR: O4 reads closed structures; at seating the members' practice records marked to market must not be losing."""
        house, alloc = self.house, self.house.allocator
        agent = self.structure_agent("test-marked")
        self.close_structures(agent, ["0.66", "0.56", "0.61"])  # three closed winners
        with switched(True), patch.object(allocator, "evidence", side_effect=TheLadder.w_paper(self, {agent.id: 0.95})):
            alloc.rebalance()  # ... and a loser held: its record marked to market is down 5%
            line = alloc.board()["spread"]["families"][agent.family]
        self.assertEqual(self.rung(agent), 1)
        self.assertEqual((line["meets"], line["held_back"], line["practice_closed"]), (False, "practice", 3))
        self.assertAlmostEqual(line["marked"]["log_w_paper"], math.log(0.95), places=6)
        self.assertIn("marked to market are losing", house._state["promotion_status"][agent.id]["reason"])
        with switched(True), patch.object(allocator, "evidence", side_effect=TheLadder.w_paper(self, {agent.id: 1.02})):
            alloc.rebalance()
        self.assertEqual(self.rung(agent), 2)

    def test_no_real_open_nets_against_a_contract_held_on_the_other_side(self):
        """MINOR (the review's DEMO 4): the venue nets one account's contracts, so a structure whose leg meets another's
        opposite leg, or a single contract bought on a structure's short leg, left each close refused at the gateway (a leg
        not held) into expiry. The House opens none of them."""
        house = self.house
        real = house.books["alpaca"]
        holder = self.structure_agent("test-holder")
        held = structures.instrument(structures.parse("alpaca", vertical_row(low=580)).spec, "alpaca")  # long 580C, short 581C
        real.account(holder.id).holdings[held.key] = Holding(held, D(1), D("46"))
        opener = self.on_real_money(self.structure_agent("test-opener"))
        with switched(True):
            intents, _ = house._intents(opener, real, [vertical_row(low=581), vertical_row(low=579), vertical_row(low=582)])
        # 581/582 buys the 581C held short; 579/580 sells the 580C held long; 582/583 touches neither.
        self.assertEqual([i.instrument.market_id for i in intents],
                         [structures.instrument(structures.parse("alpaca", vertical_row(low=582)).spec, "alpaca").market_id])
        refused = [e.payload["reasons"][0] for e in house.ledger.iter(kinds="book.refused", agent=opener.id)]
        self.assertEqual(len(refused), 2)
        self.assertIn(f"{occ('2026-09-11', 'call', 581)} is held or bid on the other side on alpaca", refused[0])
        self.assertIn(f"{occ('2026-09-11', 'call', 580)} is held or bid on the other side on alpaca", refused[1])
        # A single contract bought on the structure's short leg is dropped for the same reason; on its long leg it is not.
        self.assertIn(occ("2026-09-11", "call", 581), house._real_netting_refusal(real, [(occ("2026-09-11", "call", 581), 1)]))
        self.assertEqual(house._real_netting_refusal(real, [(occ("2026-09-11", "call", 580), 1)]), "")
        single = house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        intents, dropped = house._intents(single, real, [{"occ": occ("2026-09-11", "call", 581), "side": "buy", "quantity": 1,
                                                          "type": "limit", "limit_price": 0.5}])
        self.assertEqual(intents, [])
        self.assertIn("is held or bid on the other side", " ".join(dropped))
        # A practice book never asks: the options shadow book and alpaca-paper net nothing at a real venue here.
        self.assertEqual(house._real_netting_refusal(house.books["options-shadow"], [(occ("2026-09-11", "call", 581), 1)]), "")
        # Nor does one decision net against itself: of two verticals sharing 591C on opposite sides, the second is refused.
        with switched(True):
            intents, _ = house._intents(opener, real, [vertical_row(low=590), vertical_row(low=591), vertical_row(low=595)])
        self.assertEqual([i.instrument.market_id for i in intents],
                         [structures.instrument(structures.parse("alpaca", vertical_row(low=low)).spec, "alpaca").market_id for low in (590, 595)])
        self.assertIn(f"{occ('2026-09-11', 'call', 591)} is opened on the other side by this same decision on alpaca",
                      [e.payload["reasons"][0] for e in house.ledger.iter(kinds="book.refused", agent=opener.id)][-1])


class TheReviewOfDeployG(RealStructuresHouse):
    """The adversarial review of Deploy G (Sept 25, 2026), MINOR 1 and 2: a structure order of a rung-1 agent never goes to
    the real book, and `options_structures.book` names a practice book or none (its demonstration: named `alpaca`, a rung-1
    agent was staked $150 on the real book and, with O1 on, its open filled there); a moving stamp goes at a promotion."""

    def test_a_rung_1_structure_agent_sends_nothing_to_the_real_book_open_or_close(self):
        agent = self.structure_agent("test-rung-1")
        real = self.house.books["alpaca"]
        with switched(True):
            intents, dropped = self.house._intents(agent, real, [vertical_row(), vertical_row(action="close", limit=0.40)])
        self.assertEqual((intents, dropped), ([], []))
        refused = [r for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id) for r in e.payload["reasons"]]
        self.assertEqual(len(refused), 2)
        for reason in refused:
            self.assertIn("a structure agent on rung 1 trades on practice, never on the real alpaca book", reason)
        self.on_real_money(agent)
        with switched(True):
            intents, _ = self.house._intents(agent, real, [vertical_row()])
        self.assertEqual([(i.side, i.instrument.venue) for i in intents], [("buy", "alpaca")])

    def test_a_book_named_alpaca_stakes_no_real_money(self):
        self.house.structure_book_name = "alpaca"  # the review's MisnamedBook
        agent = self.structure_agent("test-misnamed")  # book_of: options-shadow, and seated there
        self.assertEqual([e.payload["book"] for e in self.house.ledger.iter(kinds="book.stake", agent=agent.id)], ["options-shadow"])
        self.assertNotIn(agent.id, self.house.books["alpaca"].accounts)

    def test_a_moving_stamp_goes_when_it_is_promoted(self):
        agent = self.structure_agent("test-moving")
        with self.house._state_lock:  # as `_structure_move` stamps an agent holding on the book it is leaving
            self.house._state.setdefault("structure_moving", {})[agent.id] = self.clock()
        self.on_real_money(agent)
        self.house.seat(agent)  # its real book: not moving between practice books
        self.assertNotIn(agent.id, self.house._state["structure_moving"])


if __name__ == "__main__":
    unittest.main()
