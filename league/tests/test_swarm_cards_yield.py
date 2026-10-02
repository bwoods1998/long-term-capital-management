"""THE CELL'S YIELD (league/swarm/cards.py `architect.cell_yield`, H2 of the Oct 1 edge study) and the claimable rows
(`architect.claimable_rows`): off by default, the card check is exactly as before; switched on, an open cell's
self-refuted and drift rows alone need no rebirth claim, every other mechanism verdict still does, an exhausted cell
needs one for every row, and the budgets, the same-slice and same-idea refusals, lineage and card completeness are
unchanged. Synthetic families, mechanisms, runs and figures only."""

from __future__ import annotations

import json
import math
import unittest
from unittest.mock import patch

from league.swarm import cards, mechanism
from league.swarm import settings as S
from league.swarm.architect import CLAIMABLE_NOTE, YIELD_CELLS_NOTE, Architect
from league.swarm.researcher import SELF_REFUTED, idle_cause
from league.tests.swarm_fakes import drift_block, result
from league.tests.test_swarm_cards import CARD, GOOD, MECH, Case, proposal

DRIFT = idle_cause("drift")
SELF = f"{SELF_REFUTED}: the late-day rebound did not survive the second root."
REFUTED = "The dip-bounce mechanism is conclusively refuted on every root tested"
STRESS = idle_cause("stress")
#: Today's REFUTED CELLS header, word for word (the request with both settings off is unchanged).
HEADER = ("REFUTED CELLS (mechanism_class / structure family / holding: graveyard rows killed by a mechanism verdict; a card "
          "in one needs \"rebirth\" naming one of its rows with an input that row did not read, and the cell's rebirth room; "
          "carded rows count when your inputs, declared or named in your mechanism and hypothesis, overlap theirs, declared "
          "or named in their own words):\n")
WIDER = {**CARD, "inputs": ["clock", "open_interest", "underlying_price"]}
OTHER = "Dealer inventory imbalance after late selling predicts which rebounds complete over the next session."


class Router:
    """A model that proposes `families` once (the pass's event is what is read)."""

    def __init__(self, families):
        self.families = families

    def ask(self, **_):
        return {"json": {"families": self.families}, "text": json.dumps({"families": self.families}), "route": "sail",
                "model": "fake", "cost_usd": 0.0, "usage": {}}


class YieldCase(Case):
    def setUp(self):
        super().setUp()
        self.card, _ = cards.validate(CARD)
        self.n = 0

    def bury(self, fid, card=None, **kw):
        """`Case.bury` a minute after the last (the graveyard's order is the burial order)."""
        self.clock.t += 60
        return super().bury(fid, card, **kw)

    def read(self, row) -> str:
        """What a row read, as the REFUTED CELLS print it."""
        return "+".join(self.index().by_id[row]["inputs"])

    def on(self, **cfg):
        self.settings["architect"] = {**self.settings["architect"], "cell_yield": cfg or True}

    def index(self) -> cards.RebirthIndex:
        return cards.RebirthIndex(self.store, self.settings)

    def train(self, fid, *, passing=True, eligible=True, figures=True):
        """An eligible Train run of `fid` at the normal spread, its drift block passing the screen (t 2) or not (t 0.2)."""
        self.n += 1
        res = result(f"{fid}-{self.n}")
        res["summary"]["train_eligible"] = eligible
        if figures:
            res["drift"] = drift_block() if passing else drift_block(t=0.2)
        else:
            res.pop("drift", None)
        self.store.add_run(fid, 1, res, window="train", stress=1.0, purpose="train")

    def soft_rows(self):
        """A DRIFT row and a SELF-REFUTED row in the card's cell (reversal_liquidity / directional / days_1_3)."""
        return [self.bury("drift-row", self.card, reason=DRIFT), self.bury("self-row", self.card, reason=SELF)]


class Settings(unittest.TestCase):
    def test_it_ships_off_and_reads_only_true_or_a_mapping(self):
        self.assertIsNone(S.DEFAULTS["architect"]["cell_yield"])
        self.assertEqual(S.DEFAULTS["architect"]["claimable_rows"], 0)
        self.assertIsNone(cards.cell_yield_settings(S.DEFAULTS))
        for raw in (None, False, 0, 1, "on", [], "true"):
            self.assertIsNone(cards.cell_yield_settings({"architect": {"cell_yield": raw}}), raw)
        self.assertEqual(cards.cell_yield_settings({"architect": {"cell_yield": True}}), cards.CELL_YIELD_DEFAULTS)
        self.assertEqual(cards.cell_yield_settings({"architect": {"cell_yield": {}}}), cards.CELL_YIELD_DEFAULTS)
        got = cards.cell_yield_settings({"architect": {"cell_yield": {"min_births": 12, "floor": 0.2, "lookback_days": 3}}})
        self.assertEqual(got, {"min_births": 12, "floor": 0.2, "lookback_days": 3.0})
        bad = cards.cell_yield_settings({"architect": {"cell_yield": {"min_births": 2.5, "floor": 1.5, "lookback_days": -1}}})
        self.assertEqual(bad, cards.CELL_YIELD_DEFAULTS, "a misstated key takes its default, never no threshold")
        self.assertEqual(cards.MECHANISM_VERDICTS, ("OPERATOR", "REFUTED", "SELF-REFUTED", "DIAGNOSED", "TRIALS", "DRIFT",
                                                    "STRESS", "MECHANISM"), "the memory lane's judge reads these")

    def test_the_wilson_upper_bound(self):
        self.assertEqual(cards.wilson_upper(0, 0), 1.0)
        self.assertAlmostEqual(cards.wilson_upper(0, 30), 0.1135, places=4)
        self.assertAlmostEqual(cards.wilson_upper(0, 35), 0.0989, places=4)
        self.assertAlmostEqual(cards.wilson_upper(5, 30), 0.3356, places=4)
        self.assertAlmostEqual(cards.wilson_upper(10, 10), 1.0)
        z = cards.WILSON_Z
        self.assertAlmostEqual(cards.wilson_upper(0, 50), z * z / (50 + z * z))


class OffByDefault(YieldCase):
    def test_the_check_the_cells_and_admission_are_as_before(self):
        drift_row, self_row = self.soft_rows()
        statements: list[str] = []
        self.store._db.set_trace_callback(statements.append)
        index = self.index()
        verdict = index.check(self.card, "debit_vertical", MECH, [0, 5])
        lines = index.cells(claimable=0)
        self.store._db.set_trace_callback(None)
        self.assertEqual(verdict, {
            "ok": False, "matched": [drift_row, self_row], "count": 2, "row": self_row, "lesson": verdict["lesson"],
            "tag": "SELF-REFUTED", "key": "reversal_liquidity / directional / days_1_3 / clock+underlying_price",
            "reason": "its cell (reversal_liquidity / directional / days_1_3 / clock+underlying_price) holds 2 graveyard row(s) "
                      f"killed by a mechanism verdict, the newest {self_row} (SELF-REFUTED): a birth there needs card.rebirth "
                      "naming one of them, what is different, an input the dead row did not read and the new evidence"})
        self.assertEqual(lines, [f"reversal_liquidity / directional / days_1_3: 2 rows (2 carded), rebirth room 3, newest "
                                 f"{drift_row}, {self_row}"])
        self.assertFalse(any("json_extract" in s or "FROM runs" in s for s in statements), "off: no yield is read")
        self.assertIsNone(index.yields)
        self.assertIsNone(index.yield_view())
        for raw in (None, False, "on", 0):
            self.settings["architect"]["cell_yield"] = raw
            again = self.index()
            self.assertEqual(again.check(self.card, "debit_vertical", MECH, [0, 5]), verdict, raw)
            self.assertEqual(again.cells(), lines)
        self.settings["architect"]["cell_yield"] = None
        a = self.arch()
        block = a.card_block()
        self.assertIn(HEADER + lines[0], block)
        for word in ("open", "exhausted", "claimable"):
            self.assertNotIn(word, block.split("REFUTED CELLS")[1])
        self.assertEqual(a.admit([proposal("rebound-new", mechanism=OTHER)]), [])
        self.assertIn("needs card.rebirth", a.card_refused[0]["why"])
        self.assertIsNone(a.cell_yield_seen)


class OpenCells(YieldCase):
    def test_an_open_cell_admits_a_card_matching_only_self_refuted_and_drift_rows_without_a_claim(self):
        self.soft_rows()
        self.on(min_births=30, floor=0.10, lookback_days=7)
        index = self.index()
        verdict = index.check(self.card, "debit_vertical", MECH, [0, 5])
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual((verdict["open"], verdict["count"], verdict.get("rebirth")), (True, 2, None))
        self.assertFalse(index.exhausted(("reversal_liquidity", "directional", "days_1_3")))
        self.assertEqual(index.yields[("reversal_liquidity", "directional", "days_1_3")],
                         {"births": 2, "passed": 0, "pending": 0, "unknown": 0})
        a = self.arch()
        born = a.admit([proposal("rebound-new", mechanism=OTHER, roots=["IWM"])])
        self.assertEqual(born, ["rebound-new"])
        self.assertNotIn("rebirth", cards.card_of(self.store, "rebound-new")["card"])
        payload = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]["payload"]["card"]
        self.assertEqual((payload["open_cell"], payload["rebirth"]), (True, None))
        self.assertEqual(a.cell_yield_seen["open_born"], ["rebound-new"])
        self.assertIsNone(self.store.family("rebound-new")["parent"])

    def test_refuted_and_every_other_verdict_still_need_a_claim(self):
        drift_row, _ = self.soft_rows()
        self.on(min_births=30)
        for reason, tag in ((REFUTED, "REFUTED"), (mechanism.MECHANISM_CAUSE.format(n=3), "MECHANISM"), (STRESS, "STRESS")):
            with self.subTest(tag=tag):
                hard = self.bury(f"hard-{tag.lower()}", self.card, reason=reason)
                index = self.index()
                self.assertEqual(index.by_id[hard]["tag"], tag)
                refused = index.check(self.card, "debit_vertical", MECH, [0, 5])
                self.assertFalse(refused["ok"])
                self.assertEqual((refused["row"], refused["tag"], refused["need"]), (hard, tag, len(index.rows) - 2))
                self.assertIn("needs card.rebirth", refused["reason"])
                self.assertIn("that need a claim (an open cell's self-refuted and drift rows alone need none)", refused["reason"])
                self.assertTrue(index.check({**WIDER, "rebirth": {"row": hard, **GOOD}}, "debit_vertical", MECH, [0, 5])["ok"])
                named_soft = index.check({**WIDER, "rebirth": {"row": drift_row, **GOOD}}, "debit_vertical", MECH, [0, 5])
                self.assertTrue(named_soft["ok"], "a claim may name any row the card matches, as before")
                wrong = index.check({**WIDER, "rebirth": {"row": "nobody", **GOOD}}, "debit_vertical", MECH, [0, 5])
                self.assertIn("not one of the rows its cell matches", wrong["reason"])
        a = self.arch()
        self.assertEqual(a.admit([proposal("rebound-new", mechanism=OTHER, roots=["IWM"])]), [])
        self.assertIn("needs card.rebirth", a.card_refused[0]["why"])

    def test_a_valid_claim_in_an_open_cell_is_a_rebirth_and_an_invalid_one_is_dropped(self):
        drift_row, _ = self.soft_rows()
        self.on(min_births=30)
        a = self.arch()
        born = a.admit([proposal("reborn", card={**WIDER, "rebirth": {"row": drift_row, **GOOD}}, roots=["IWM"],
                                 mechanism=OTHER)])
        self.assertEqual(born, ["reborn"])
        self.assertEqual(cards.card_of(self.store, "reborn")["card"]["rebirth"]["row"], drift_row)
        payload = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]["payload"]["card"]
        self.assertEqual((payload["rebirth"], payload["open_cell"]), (drift_row, True))
        self.assertEqual(a.cell_yield_seen["open_born"], [], "a rebirth is not an unclaimed open-cell birth")
        self.assertEqual(self.store.family("reborn")["spec"]["prior_lineage"], self.store.family(drift_row)["lineage"],
                         "a rebirth on another slice counts the named row's lineage, as before")
        self.assertEqual(self.index().backed[drift_row], 1, "a kept claim spends the row's budget")
        wrong = {**WIDER, "rebirth": {"row": "nobody", **GOOD}}
        born = a.admit([proposal("dropped", card=wrong, roots=["QQQ"], mechanism="Dealer inventory after the late sell-off "
                                                                                 "sorts which rebounds finish on QQQ.")])
        self.assertEqual(born, ["dropped"])
        stored = cards.card_of(self.store, "dropped")
        self.assertNotIn("rebirth", stored["card"])
        self.assertEqual(stored["sha"], self.store.family("dropped")["spec"]["card_sha"])
        self.assertEqual(stored["sha"], cards.card_sha({k: v for k, v in cards.validate(wrong)[0].items() if k != "rebirth"}))
        payload = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"][-1]["payload"]["card"]
        self.assertEqual(payload["rebirth"], None)
        self.assertIn("not one of the rows its cell matches", payload["claim_dropped"])
        self.assertIsNone(self.store.family("dropped")["spec"].get("prior_lineage"), "an unchecked claim links no lineage")
        self.assertNotIn("nobody", self.index().backed, "and spends no budget")
        self.assertEqual([d["family"] for d in a.cell_yield_seen["claims_dropped"]], ["dropped"])


class ExhaustedCells(YieldCase):
    def test_an_exhausted_cell_refuses_as_today(self):
        rows = self.soft_rows() + [self.bury(f"dead-{i}", self.card, reason=DRIFT, roots=(r,))
                                   for i, r in enumerate(("QQQ", "IWM"))]
        off = self.index().check(self.card, "debit_vertical", MECH, [0, 5])
        self.on(min_births=4, floor=0.5, lookback_days=7)
        index = self.index()
        cell = ("reversal_liquidity", "directional", "days_1_3")
        self.assertEqual(index.yields[cell]["births"], 4)
        self.assertLess(cards.wilson_upper(0, 4), 0.5)
        self.assertTrue(index.exhausted(cell))
        self.assertEqual(index.check(self.card, "debit_vertical", MECH, [0, 5]), off, "exactly today's refusal")
        self.assertTrue(index.cells()[0].endswith("; exhausted: every row needs a claim"))
        self.assertEqual(index.yield_view()["exhausted"], [" / ".join(cell)])
        # One of the four passes the drift screen: 1 of 4 has an upper bound above the floor, and the cell opens.
        self.train(rows[0], passing=True)
        reopened = self.index()
        self.assertEqual(reopened.yields[cell], {"births": 4, "passed": 1, "pending": 0, "unknown": 0})
        self.assertFalse(reopened.exhausted(cell))
        self.assertTrue(reopened.check(self.card, "debit_vertical", MECH, [0, 5])["ok"])

    def test_only_settled_births_in_the_lookback_with_a_screened_record_count(self):
        rows = self.soft_rows()
        self.on(min_births=2, floor=0.9, lookback_days=7)
        cell = ("reversal_liquidity", "directional", "days_1_3")
        self.assertTrue(self.index().exhausted(cell))
        # A failing run (known, not passed) keeps a death a failure; a run with no drift figures makes it unknown;
        # an ineligible passing run does not pass; an alive family without a pass is pending.
        self.train(rows[0], passing=False)
        self.train(rows[1], figures=False)
        self.train(rows[1], passing=True, eligible=False)
        alive = self.store.add_family({"id": "alive", "mechanism": MECH, "structure": "debit_vertical", "roots": ["SPY"],
                                       "dte": [0, 5], "card_sha": cards.card_sha(self.card)}, origin="architect")
        cards.put(self.store, alive["id"], self.card, "debit_vertical")
        fork = self.store.add_family({"id": "fork", "mechanism": OTHER, "structure": "debit_vertical", "roots": ["QQQ"],
                                      "dte": [0, 5], "card_sha": cards.card_sha(self.card)}, origin="fork", parent="alive")
        self.train(fork["id"], passing=True)
        tally = self.index().yields[cell]
        self.assertEqual(tally, {"births": 2, "passed": 1, "pending": 1, "unknown": 1},
                         "the fork reads its parent's card: a pass; the alive parent is pending; self-row is unknown")
        self.clock.t += 8 * 86400
        late = self.index()
        self.assertIsNone(late.yields.get(cell), "births older than the lookback leave it")
        self.assertFalse(late.exhausted(cell))

    def test_a_yield_that_cannot_be_read_leaves_every_cell_as_today(self):
        self.soft_rows()
        self.on(min_births=30)
        with patch.object(cards, "cell_yields", side_effect=RuntimeError("no runs table")):
            index = self.index()
            self.assertFalse(index.check(self.card, "debit_vertical", MECH, [0, 5])["ok"])
            self.assertIn("RuntimeError: no runs table", index.yield_view()["error"])


class Unchanged(YieldCase):
    def test_both_budgets_still_bind(self):
        rows = [self.bury(f"rebound-{i}", self.card, reason=mechanism.MECHANISM_CAUSE.format(n=3), roots=(r,))
                for i, r in enumerate(("SPY", "QQQ"))]
        self.on(min_births=30)
        a = self.arch()
        born = a.admit([proposal(f"reborn-{i}", card={**WIDER, "rebirth": {"row": rows[i // 2], **GOOD}}, roots=["IWM"],
                                 mechanism=f"Dealer inventory imbalance after late selling predicts rebound {i} next session.")
                        for i in range(4)])
        self.assertEqual(len(born), 3, "three rebirths a cell a week")
        self.assertIn("rebirth(s) in the last 7 days", a.card_refused[-1]["why"])
        index = self.index()
        index.cell_births.clear()
        self.assertIn("already backed 2", index.check({**WIDER, "rebirth": {"row": rows[0], **GOOD}}, "debit_vertical",
                                                      MECH)["reason"])

    def test_an_open_cells_claim_past_its_budget_is_dropped_not_spent(self):
        drift_row, self_row = self.soft_rows()
        self.on(min_births=30)
        a = self.arch()
        props = [proposal(f"reborn-{i}", card={**WIDER, "rebirth": {"row": (drift_row, self_row)[i % 2], **GOOD}},
                          roots=[("IWM", "QQQ", "SPY", "IWM")[i]],
                          mechanism=f"Dealer inventory imbalance after late selling predicts rebound {i} the next session.")
                 for i in range(4)]
        self.assertEqual(len(a.admit(props)), 4, "no claim was needed: the fourth is born without its claim")
        kept = [cards.card_of(self.store, f"reborn-{i}")["card"].get("rebirth") for i in range(4)]
        self.assertEqual(sum(1 for k in kept if k), 3)
        self.assertIn("rebirth(s) in the last 7 days", a.cell_yield_seen["claims_dropped"][0]["why"])
        self.assertEqual(sum(self.index().cell_births.values()), 3)

    def test_same_slice_same_idea_lineage_and_completeness_are_as_before(self):
        dead = self.bury("rebound-old", self.card, reason=DRIFT)
        self.store.bump(dead, trials=7)
        self.on(min_births=30)
        a = self.arch()
        born = a.admit([proposal("rebound-again"), proposal("no-card", card=None, mechanism=OTHER),
                        proposal("half", card={"hypothesis": CARD["hypothesis"]}, roots=["QQQ"])])
        self.assertEqual(born, ["rebound-again"])
        self.assertEqual(self.store.family("rebound-again")["parent"], dead, "the same idea on its slice continues its lineage")
        self.assertEqual(self.store.lineage_trials("rebound-again"), 7)
        self.assertEqual([r["slug"] for r in a.card_refused], ["no-card", "half"])
        self.assertTrue(all(r["why"].startswith("incomplete card") for r in a.card_refused))
        self.assertEqual(a.admit([proposal("rebound-twin")]), [], "a living family's same idea on its slice is not born")
        single = {**CARD, "mechanism_class": "reversal_liquidity"}
        self.assertEqual(a.admit([proposal("both-sides", card=single, structure="long_single", roots=["QQQ"],
                                           mechanism=OTHER)]), ["both-sides"])
        self.assertEqual(a.admit([proposal("call-side", card=single, structure="long_call", roots=["QQQ"], mechanism=OTHER)]),
                         [], "a one-sided single beside its living long_single twin is not born")

    def test_the_memory_judges_rows_are_the_same(self):
        self.soft_rows()
        self.bury("hard", self.card, reason=REFUTED)
        off = [r["row"] for r in self.index().rows]
        self.on(min_births=30)
        self.assertEqual([r["row"] for r in self.index().rows], off)


class TheRequest(YieldCase):
    def test_the_cells_say_open_or_exhausted_and_list_claimable_rows(self):
        drift_row, self_row = self.soft_rows()
        hard = self.bury("hard", self.card, reason=REFUTED)
        trend = {**CARD, "mechanism_class": "trend_momentum", "holding": "days_4_10"}
        soft_only = self.bury("trend-drift", cards.validate(trend)[0], reason=DRIFT)
        self.settings["architect"].update(claimable_rows=2)
        off_block = self.arch().card_block()
        self.assertIn(HEADER[:-2] + CLAIMABLE_NOTE + ":\n", off_block, "claimable rows alone: every cell needs claims")
        read = self.read(hard)
        self.assertEqual(read, "clock+option_liquidity+underlying_price", "declared, and named by its own words")
        self.assertIn(f"claimable: {hard} (read {read}, carded), {self_row} (read {read}, carded)", off_block)
        self.on(min_births=30)
        lines = self.index().cells(claimable=2)
        self.assertEqual(lines[0], f"reversal_liquidity / directional / days_1_3: 3 rows (3 carded), rebirth room 3, newest "
                                   f"{drift_row}, {self_row}, {hard}; open: 1 of its rows need a claim; claimable: {hard} (read "
                                   f"{read}, carded), {self_row} (read {read}, carded)")
        self.assertEqual(lines[1], f"trend_momentum / directional / days_4_10: 1 rows (1 carded), rebirth room 3, newest "
                                   f"{soft_only}; open: no row needs a claim", "nothing to claim in a cell that needs none")
        block = self.arch().card_block()
        self.assertIn(HEADER[:-2] + YIELD_CELLS_NOTE + CLAIMABLE_NOTE + ":\n" + lines[0], block)
        # A row that has backed its two rebirths is not offered; a cell without rebirth room lists none.
        index = self.index()
        index.backed[hard] = 2
        self.assertIn(f"claimable: {self_row} (read {read}, carded), {drift_row} (read {read}, carded)",
                      index.cells(claimable=2)[0])
        index.cell_births[("reversal_liquidity", "directional", "days_1_3")] = 3
        self.assertNotIn("claimable", index.cells(claimable=2)[0])
        self.settings["architect"].update(claimable_rows=99)
        self.assertEqual(self.arch().claimable_rows(), 12)
        for raw in (0, -1, 2.5, True, "3", None, float("inf"), float("-inf"), float("nan"), 1e309):
            self.settings["architect"].update(claimable_rows=raw)
            self.assertEqual(self.arch().claimable_rows(), 0, raw)

    def test_no_yield_or_validation_figure_reaches_the_request(self):
        rows = self.soft_rows()
        self.train(rows[0], passing=True)
        figures = {"t_daily": 738.6417, "mean_return_on_max_loss_daily": 612.9483, "dsr": 853.7129, "pnl": 6174.29}
        val = result("sentinel-validation", window="validation")
        val["summary"].update(figures)
        self.store.add_run(rows[0], 1, val, window="validation", stress=1.0, purpose="validation")
        self.store.set_state(rows[0], validation_numbers={"t": 738.6417, "dsr": 853.7129})
        self.on(min_births=2, floor=0.9, lookback_days=7)
        self.settings["architect"].update(claimable_rows=6)
        a = self.arch()
        view = self.index().yield_view()
        self.assertEqual((view["cells"][0]["births"], view["cells"][0]["passed"]), (2, 1), "the figures exist to leak")
        upper = view["cells"][0]["upper"]
        texts = {"card_block": a.card_block(), "prompt": a.prompt()}
        for where, text in texts.items():
            self.assertIn("REFUTED CELLS", text)
            self.assertIn("; open: no row needs a claim", text)
            for value in figures.values():
                for form in {f"{value:.{d}f}" for d in range(1, 5)} | {str(value), str(math.trunc(value))}:
                    self.assertNotIn(form, text, f"{where} shows a Validation figure ({form}): D2a")
            for form in (f"{upper:.4f}", f"{upper:.3f}", str(upper)):
                self.assertNotIn(form, text, f"{where} shows the cell's bound ({form})")
            cells = text.split("REFUTED CELLS")[1].split("\n\n")[0].split(":\n", 1)[1]  # the cells' lines, not the header
            for word in ("births", "passed", "pending", "upper", "%"):
                self.assertNotIn(word, cells)


class ThePass(YieldCase):
    def test_the_pass_event_carries_the_cells_yield(self):
        drift_row, _ = self.soft_rows()
        self.on(min_births=30)
        self.settings["architect"]["openai_model"] = None
        a = Architect(self.store, Router([proposal("open-birth", mechanism=OTHER, roots=["IWM"]),
                                          proposal("dropped", card={**WIDER, "rebirth": {"row": "nobody", **GOOD}},
                                                   roots=["QQQ"], mechanism="Dealer inventory after the late sell-off "
                                                                            "sorts which rebounds finish on QQQ.")]),
                      self.settings, clock=self.clock)
        with patch.object(cards, "cell_yields", wraps=cards.cell_yields) as reads:
            out = a.run()
        self.assertEqual(reads.call_count, 1, "the request's reading of the cells is the admission's")
        self.assertIsNone(a.pass_yields, "and it is used once")
        self.assertEqual(sorted(out["born"]), ["dropped", "open-birth"])
        event = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.architect"][-1]
        cy = event["cell_yield"]
        self.assertEqual((cy["open_born"], [d["family"] for d in cy["claims_dropped"]]), (2, ["dropped"]))
        self.assertEqual(cy["settings"], {"min_births": 30, "floor": 0.1, "lookback_days": 7.0})
        self.assertEqual(cy["exhausted"], [])
        self.assertEqual(cy["cells"][0]["cell"], "reversal_liquidity / directional / days_1_3")

    def test_the_pass_event_has_no_yield_while_off(self):
        self.soft_rows()
        self.settings["architect"]["openai_model"] = None
        out = Architect(self.store, Router([proposal("refused", mechanism=OTHER)]), self.settings, clock=self.clock).run()
        self.assertEqual(out["born"], [])
        self.assertNotIn("cell_yield", out)


if __name__ == "__main__":
    unittest.main()
