"""THE DIRECTION LANE's births (release D-1, Oct 9, 2026; PLAN D2, HARNESS C2, C3, C4 and C8; tests 6.4 items 5 and 6): the
card's lane and the lane's box (league/swarm/cards.py), the DRIFT rows that bind no direction card, the lane's birth
cells, the architect's lane-aware system prompt, its LANES block, its direction quota (league/swarm/dlane.py
`DirectionQuota`, re-exported by allocation.py), the `lane_only` request and the pass's event, and the strategist's lane
counts. With `dlane.mode` "off" (THE ROLLBACK, and the code's default) every one of them is the release before's: alpha
card shas are pinned to the values ccfa48d5 computes.

Every family, mechanism, figure and date here is invented.
"""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from league.swarm import allocation, cards, dlane, mechanism
from league.swarm import settings as S
from league.swarm.architect import LANE_LAST_KEY, LANE_SYSTEM, SYSTEM, Architect, system_text
from league.swarm.researcher import idle_cause
from league.swarm.strategist import Strategist
from league.tests.test_swarm_cards import CARD, GOOD, MECH, Case, proposal

GATE = {"mode": "gate"}
OFF = {"mode": "off"}
DRIFT = idle_cause("drift")
#: A direction card inside the lane's box (an equity_premium call program on the index).
DIR = {**CARD, "lane": "direction", "mechanism_class": "equity_premium", "holding": "days_4_10",
       "hypothesis": "Index holders are paid to bear market risk, so a cheap out-of-the-money call held a week rents the "
                     "index's drift whenever its decay is below that drift.",
       "inputs": ["implied_vol", "underlying_price"], "ablation": {"param": "gate_on", "off": 0},
       "comparison": "the same call bought at the same minute every session with the regime gate switched off"}
TREND = {**DIR, "mechanism_class": "trend_momentum",
         "hypothesis": "Slow capital extends the index's trend for several sessions, so a call held through it is paid by the "
                       "continuation."}
#: The alpha card's sha at ccfa48d5 (`cards.card_sha(cards.validate(CARD)[0])` on that tree): the lane never moves it.
ALPHA_SHA = "3d4e29c9ded03ad6e02fc35c"
#: Direction-shaped cards validated by ccfa48d5 (which ignores `lane`): the rollback reads them the same way. The first is
#: CARD as a trend_momentum days_4_10 card, the second TREND.
TREND_CARD_OFF_SHA = "d6b49c9f5a272603b17ee0fc"
TREND_OFF_SHA = "013323e7cfbb23baa992364a"
#: A year an agent may never read (the hidden years, Validation, the holdout).
LEAK = re.compile(r"(?<![\d.$,])20(?:20|21|25|26)(?![\d])")
DMECH = "Rent the index's drift with a cheap call held a week while implied vol sits calm against its own trailing year."


class Router:
    """A model that proposes `families` on every ask and records what it was asked."""

    def __init__(self, families=()):
        self.families, self.calls = list(families), []

    def ask(self, **kw):
        self.calls.append(kw)
        return {"json": {"families": self.families}, "text": json.dumps({"families": self.families}), "route": "sail",
                "model": "fake", "cost_usd": 0.0, "usage": {}}


def lane(settings: dict, block: dict) -> dict:
    """`settings` with the `dlane` block (a copy)."""
    out = copy.deepcopy(settings)
    out["dlane"] = dict(block)
    return out


class LaneCase(Case):
    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(GATE)

    def arch(self, router=None) -> Architect:
        return Architect(self.store, router, self.settings, clock=self.clock)

    def born(self) -> list[dict]:
        return [e for e in self.store.events_after(0, limit=10_000) if e["kind"] == "swarm.born"]

    def passes(self) -> list[dict]:
        return [e["payload"] for e in self.store.events_after(0, limit=10_000) if e["kind"] == "swarm.architect"]

    def direction(self, n: int, *, roots=("SPY",), card=DIR, structure="long_single") -> list[dict]:
        return [proposal(f"dir-{n}-{i}", card=card, structure=structure, roots=list(roots),
                         mechanism=f"Variant {i} of pass {n}: {DMECH}") for i in range(10)]

    def alpha(self, n: int) -> list[dict]:
        out = []
        for i in range(10):
            card = {**CARD, "mechanism_class": "skew", "inputs": ["iv_skew"],
                    "hypothesis": f"Put skew overprices crash protection after calm weeks, variant {i}, so the wing seller "
                                  "is paid for bearing it."}
            out.append(proposal(f"alpha-{n}-{i}", card=card, roots=["QQQ"],
                                mechanism=f"Skew richness after calm weeks pays the wing seller, variant {i} of pass {n}."))
        return out


# ------------------------------------------------------------------------------------------------ 5. cards
class CardsInTheLane(unittest.TestCase):
    def test_a_direction_card_keeps_its_lane_and_the_box_names_every_reason(self):
        card, errors = cards.validate(DIR, "long_single", roots=["SPY", "QQQ"], settings={"dlane": GATE})
        self.assertEqual(errors, [])
        self.assertEqual((card["lane"], card["mechanism_class"]), ("direction", "equity_premium"))
        self.assertEqual(dlane.lane_value(card)[0], "direction")
        bad = {**DIR, "mechanism_class": "skew", "holding": "intraday", "ablation": {"flat": True}}
        card, errors = cards.validate(bad, "iron_condor", roots=["SPY", "XSP"], settings={"dlane": GATE})
        self.assertIsNone(card)
        named = [e.split(":")[0] for e in errors]
        for field in ("mechanism_class", "structure", "roots", "holding", "ablation"):
            self.assertIn(field, named, errors)
        self.assertIn("XSP", " ".join(errors))
        self.assertIn("never flat", " ".join(errors), "a flat comparison is refused for a direction card")
        card, errors = cards.validate({**DIR, "lane": "beta"}, "long_single", roots=["SPY"], settings={"dlane": GATE})
        self.assertIsNone(card)
        self.assertEqual(errors[0], "lane: 'beta' is not one of alpha, direction")

    def test_the_lanes_class_is_a_direction_cards_only_and_only_while_the_lane_is_on(self):
        alpha = {**CARD, "mechanism_class": "equity_premium"}
        _, errors = cards.validate(alpha, "debit_vertical", roots=["SPY"], settings={"dlane": GATE})
        self.assertEqual(errors, ["mechanism_class: equity_premium is the direction lane's class: a card that names it "
                                  "declares \"lane\": \"direction\""])
        for settings in ({}, {"dlane": OFF}):
            _, errors = cards.validate(DIR, "long_single", roots=["SPY"], settings=settings)
            self.assertEqual(errors, ["mechanism_class: 'equity_premium' is not one of " + ", ".join(cards.MECHANISM_CLASSES)],
                             "off: the release before's word for word (`lane` ignored, the class unknown)")
            self.assertIs(cards.mechanism_classes(settings), cards.MECHANISM_CLASSES)
            self.assertEqual(cards.vocabulary_text(settings), cards.vocabulary_text())
        self.assertNotIn("equity_premium", cards.MECHANISM_CLASSES, "the eleven classes every other reader keeps")
        self.assertNotIn("equity_premium", cards.vocabulary_text())
        on = cards.vocabulary_text({"dlane": GATE})
        self.assertIn(f"- equity_premium: {dlane.EQUITY_PREMIUM} (a direction card's class only)", on)
        self.assertNotIn("equity_premium", cards.vocabulary_text({"dlane": {**GATE, "classes": ["trend_momentum"]}}),
                         "a class the lane's settings leave out is no word")

    def test_alpha_card_shas_are_byte_identical_and_legacy_cards_read_as_alpha(self):
        for settings in (None, {}, {"dlane": OFF}, {"dlane": GATE}, {"dlane": {"mode": "shadow"}}):
            card, errors = cards.validate(CARD, "debit_vertical", roots=["SPY"], settings=settings)
            self.assertEqual((errors, cards.card_sha(card)), ([], ALPHA_SHA), settings)
            self.assertNotIn("lane", card)
            card, _ = cards.validate({**CARD, "lane": "alpha"}, "debit_vertical", roots=["SPY"], settings=settings)
            self.assertEqual(cards.card_sha(card), ALPHA_SHA, "an alpha card never stores its lane")
        off, errors = cards.validate({**CARD, "mechanism_class": "trend_momentum", "holding": "days_4_10", "lane": "direction"},
                                     "long_single", roots=["SPY"], settings={"dlane": OFF})
        self.assertEqual((errors, cards.card_sha(off)), ([], TREND_CARD_OFF_SHA), "off: `lane` is ignored as at ccfa48d5")
        self.assertIsNone(cards.lane_of_card(off))
        self.assertEqual(dlane.lane_value(off)[0], "alpha", "a card without a lane is alpha")
        on, _ = cards.validate(TREND, "long_single", roots=["SPY"], settings={"dlane": GATE})
        self.assertEqual(cards.canonical(on), cards.canonical({**cards.validate(TREND, "long_single")[0], "lane": "direction"}),
                         "a direction card is the alpha reading of its fields plus its lane")
        self.assertNotEqual(cards.card_sha(on), cards.card_sha(cards.validate(TREND, "long_single")[0]))

    def test_the_card_brief_names_the_lane_only_while_it_is_on(self):
        on, _ = cards.validate(DIR, "long_single", roots=["SPY"], settings={"dlane": GATE})
        entry = {"card": on}
        self.assertNotIn("Lane:", cards.brief_text(entry))
        self.assertNotIn("Lane:", cards.brief_text(entry, {"dlane": OFF}), "the rollback: judged as alpha, told nothing else")
        text = cards.brief_text(entry, {"dlane": GATE})
        self.assertIn("- Lane: DIRECTION (fixed at birth)", text.splitlines()[1])
        self.assertIn(dlane.ALWAYS_IN_NOTE, text)
        alpha, _ = cards.validate(CARD)
        self.assertEqual(cards.brief_text({"card": alpha}, {"dlane": GATE}), cards.brief_text({"card": alpha}))


class DriftRows(Case):
    """A DRIFT row binds no direction card; every other verdict binds both lanes (HARNESS 2.1, 7.4)."""

    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(GATE)
        self.trend, _ = cards.validate(TREND, "long_single", roots=["SPY"], settings=self.settings)
        self.alpha_trend, _ = cards.validate({k: v for k, v in TREND.items() if k != "lane"}, "long_single")
        self.drift = self.bury("drift-trend", self.alpha_trend, reason=DRIFT, structure="long_single",
                               mechanism="Index trend continuation calls held a week after a breakout.")

    def index(self) -> cards.RebirthIndex:
        return cards.RebirthIndex(self.store, self.settings)

    def test_a_drift_row_binds_no_direction_card_and_still_binds_an_alpha_card(self):
        index = self.index()
        self.assertEqual([r["tag"] for r in index.rows], ["DRIFT"])
        verdict = index.check(self.trend, "long_single", "Index trend continuation calls held a week.")
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual((verdict["drift_lane"], verdict["matched"]), (True, [self.drift]))
        self.assertNotIn("open", verdict, "the lane excused it, not a cell's yield")
        refused = index.check(self.alpha_trend, "long_single", "Index trend continuation calls held a week.")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["tag"], "DRIFT")

    def test_every_other_verdict_binds_a_direction_card(self):
        self.bury("stress-trend", self.alpha_trend, reason=idle_cause("stress"), structure="long_single",
                  mechanism="Index trend continuation calls held a week after a breakout, again.")
        refused = self.index().check(self.trend, "long_single", "Index trend continuation calls held a week.")
        self.assertFalse(refused["ok"])
        self.assertEqual((refused["tag"], refused["need"]), ("STRESS", 1))
        self.assertIn("(a DRIFT row binds no direction card)", refused["reason"])
        ep, _ = cards.validate(DIR, "long_single", roots=["SPY"], settings=self.settings)
        self.bury("mech-ep", {**ep, "inputs": ["implied_vol", "underlying_price"]},
                  reason=mechanism.MECHANISM_CAUSE.format(n=3), structure="long_single", mechanism=DMECH)
        self.assertFalse(self.index().check(ep, "long_single", DMECH)["ok"], "a failed mechanism test binds the lane")

    def test_a_claim_on_a_drift_row_is_a_rebirth_only_when_it_holds_and_spends_the_budgets(self):
        wider = {**self.trend, "inputs": ["implied_vol", "open_interest", "underlying_price"]}
        index = self.index()
        good = index.check({**wider, "rebirth": {"row": self.drift, **GOOD}}, "long_single", "Trend calls held a week.")
        self.assertEqual((good["ok"], good.get("rebirth"), good.get("drift_lane")), (True, True, True))
        vague = index.check({**wider, "rebirth": {"row": self.drift, **GOOD, "evidence": "e" * 50}}, "long_single",
                            "Trend calls held a week.")
        self.assertTrue(vague["ok"])
        self.assertIn("cites nothing checkable", vague["dropped"], "stripped before the card is stored")
        index.note_birth({**wider, "rebirth": {"row": self.drift, **GOOD}}, "long_single")
        self.assertEqual(index.backed[self.drift], 1, "such an idea returns once each, within the row's budget")

    def test_the_birth_cells_gain_the_lanes_cells_and_a_drift_only_cell_bears_a_direction_card(self):
        index = self.index()
        lane_cells = {("equity_premium", "directional", "days_1_3"), ("equity_premium", "directional", "days_4_10")}
        self.assertTrue(lane_cells <= {cell for cell, _ in index.grid(["directional"])})
        self.assertEqual(len(index.grid(["directional"])), 46)
        self.assertFalse(lane_cells & {cell for cell, _ in index.grid(["short_premium"])})
        off = cards.RebirthIndex(self.store, lane(self.settings, OFF))
        self.assertEqual(len(off.grid(["directional"])), 44, "off: the eleven classes' cells, as before")
        rows = [r for r in index.rows if r["row"] == self.drift]
        cell = cards.cell_of(rows[0]["key"])
        self.settings["architect"].update(max_rebirths_per_cell=0)
        index = self.index()
        self.assertFalse(index.bearable(cell, rows), "an alpha card needs a claim and the cell has no room")
        self.assertTrue(index.bearable(cell, rows, "direction"))


class ClosedPass(Case):
    """NO PAID PASS WITHOUT A CELL reads a DRIFT-only cell of the lane's as one a direction card can bear."""

    def setUp(self):
        super().setUp()
        self.settings["architect"].update(structures=["debit_vertical", "long_single"], max_rebirths_per_cell=0)

    def fill(self, drift_cell):
        for c in [*cards.MECHANISM_CLASSES, "equity_premium"]:
            for h in cards.HOLDING:
                if c == "equity_premium" and h not in ("days_1_3", "days_4_10"):
                    continue
                raw = {**CARD, "mechanism_class": c, "holding": h}
                card = (cards.validate(raw)[0] if c in cards.MECHANISM_CLASSES
                        else {**cards.validate({**raw, "mechanism_class": "skew"})[0], "mechanism_class": c,
                              "lane": "direction"})
                reason = DRIFT if (c, h) == drift_cell else "Refuted: it loses after costs."
                self.bury(f"{c}-{h}".replace("_", "-")[:36], card, reason=reason)

    def test_a_drift_only_trend_cell_keeps_the_pass_open_for_direction_only(self):
        self.fill(("trend_momentum", "days_4_10"))
        self.assertIsNotNone(Architect(self.store, None, self.settings, clock=self.clock).closed(), "off: closed as before")
        self.settings["dlane"] = dict(GATE)
        self.assertIsNone(Architect(self.store, None, self.settings, clock=self.clock).closed())
        self.settings["dlane"] = {**GATE, "classes": ["equity_premium"]}
        self.assertEqual(Architect(self.store, None, self.settings, clock=self.clock).closed(),
                         {"cells": 46, "full": 46, "spent": 0}, "a cell outside the lane's classes bears no direction card")


# ------------------------------------------------------------------------------------------------ 6. the architect
class SystemPrompt(unittest.TestCase):
    def test_each_lane_aware_sentence_is_systems_own_and_off_is_system_itself(self):
        for old, new in LANE_SYSTEM:
            self.assertEqual(SYSTEM.count(old), 1, old)
            self.assertEqual(set(re.findall(r"\w+", old)) - set(re.findall(r"\w+", new)), set(), "the alpha lane's words stay")
        self.assertIs(system_text({}), SYSTEM)
        self.assertIs(system_text({"dlane": OFF}), SYSTEM)
        text = system_text({"dlane": GATE})
        for _, new in LANE_SYSTEM:
            self.assertIn(new, text)
        self.assertIn("An ALPHA family's\nTrain score is its WORST Train year", text)
        self.assertIn("a DIRECTION long_single buys calls only", text)
        self.assertIn('"card": {"lane": "alpha (the default) or direction", "hypothesis"', text)
        self.assertIsNone(LEAK.search(text.replace("Validation 2025", "")), "no hidden year added")


class Quota(LaneCase):
    """The quota's floor, cap and per-pass minimum through `admit` (want 10: start 10, nothing alive)."""

    def setUp(self):
        super().setUp()
        self.settings["population"].update(start=10, ceiling=60)

    def test_the_floor_is_never_filled_with_alpha(self):
        a = self.arch()
        a.pass_lane_quota = quota = a.lane_quota()
        self.assertEqual((quota.floor, quota.pass_cap), (5, 6))
        born = a.admit(self.alpha(1)[:8] + self.direction(1)[:2])
        self.assertEqual(len(born), 7)
        lanes = [e["payload"]["lane"] for e in self.born()]
        self.assertEqual((lanes.count("alpha"), lanes.count("direction")), (5, 2))
        self.assertEqual(quota.event(), {"lane_births": {"alpha": 5, "direction": 2},
                                         "lane_refused": {"alpha": 3, "direction": 0}, "lane_short": 3})
        self.assertIn("never filled with alpha", quota.reasons[-1])

    def test_a_pass_of_direction_proposals_stops_at_the_pass_cap(self):
        a = self.arch()
        a.pass_lane_quota = a.lane_quota()
        born = a.admit(self.direction(2)[:8])
        self.assertEqual(len(born), 6, "max(floor 5, floor(0.6 x 10))")
        self.assertEqual(a.pass_lane_quota.refused["direction"], 2)
        self.assertIn("direction cap of 6", a.pass_lane_quota.reasons[-1])

    def test_the_per_pass_minimum_while_behind_and_the_window_cap_at_its_share(self):
        for _ in range(20):
            self.store.event("swarm.born", "x", {"structure": "debit_vertical", "lane": "alpha"})
        self.settings["population"].update(start=1, ceiling=60)  # want 1
        a = self.arch()
        self.assertEqual(a.admit(self.alpha(3)[:1]), [], "the one birth of a want-1 pass while behind is direction's")
        self.assertEqual(len(a.admit(self.direction(3)[:1])), 1)
        for _ in range(30):
            self.store.event("swarm.born", "x", {"structure": "long_single", "lane": "direction"})
        a = self.arch()
        a.pass_lane_quota = a.lane_quota()
        self.assertEqual(a.pass_lane_quota.floor, 0, "past its share: nothing reserved")
        self.assertEqual(a.admit(self.direction(4)[:1]), [], "the 60% window cap binds even the per-pass minimum")
        self.assertIn("dlane.max_share", a.pass_lane_quota.reasons[-1])

    def test_the_lane_quota_is_allocations_too(self):
        self.assertIs(allocation.DirectionQuota, dlane.DirectionQuota)


class Admission(LaneCase):
    def test_a_direction_birth_its_spec_card_payload_and_the_pass_event(self):
        router = Router(self.direction(1)[:2] + self.alpha(1)[:2])
        out = self.arch(router).run()
        self.assertEqual(len(out["born"]), 4)
        self.assertEqual(out["lane_births"], {"alpha": 2, "direction": 2})
        self.assertEqual((out["lane_refused"], out["lane_short"]), ({"alpha": 0, "direction": 0}, 0))
        self.assertNotIn("lane_only", out)
        for e in self.born():
            fam = self.store.family(e["family"])
            entry = cards.card_of(self.store, e["family"])
            if e["family"].startswith("dir-"):
                self.assertEqual((e["payload"]["lane"], fam["spec"]["lane"], entry["card"]["lane"]), ("direction",) * 3)
                self.assertEqual(dlane.lane_of(self.store, fam, self.settings), "direction")
            else:
                self.assertEqual(e["payload"]["lane"], "alpha")
                self.assertNotIn("lane", fam["spec"])
                self.assertNotIn("lane", entry["card"])
                self.assertEqual(dlane.lane_of(self.store, fam, self.settings), "alpha")
        last = self.store.get(LANE_LAST_KEY)
        self.assertEqual((last["lane_births"], last["lane_short"]), ({"alpha": 2, "direction": 2}, 0))

    def test_refusals_name_every_reason(self):
        bad = {**DIR, "mechanism_class": "skew", "holding": "intraday", "ablation": {"flat": True}}
        a = self.arch()
        self.assertEqual(a.admit([proposal("dir-bad", card=bad, structure="debit_vertical", roots=["SPY", "XSP"],
                                           mechanism=DMECH)]), [])
        why = a.card_refused[0]["why"]
        self.assertTrue(why.startswith("incomplete card: "))
        for field in ("mechanism_class: a direction card", "roots: a direction card trades only SPY, QQQ, IWM (XSP given)",
                      "holding: a direction card holds", "never flat"):
            self.assertIn(field, why)

    def test_off_is_the_release_before(self):
        self.settings["dlane"] = dict(OFF)
        router = Router([proposal("dir-trend", card=TREND, structure="long_single", mechanism=DMECH)])
        out = self.arch(router).run()
        self.assertEqual(out["born"], ["dir-trend"], "`lane` ignored: born as at ccfa48d5")
        for key in ("lane_births", "lane_refused", "lane_short", "lane_only"):
            self.assertNotIn(key, out)
        [event] = self.born()
        self.assertNotIn("lane", event["payload"])
        self.assertNotIn("lane", self.store.family("dir-trend")["spec"])
        self.assertEqual(cards.card_of(self.store, "dir-trend")["sha"], TREND_OFF_SHA)
        self.assertEqual(router.calls[0]["system"], SYSTEM)
        for key in (LANE_LAST_KEY, dlane.STARTED_KEY, dlane.LANE_ONLY_KEY):
            self.assertIsNone(self.store.get(key), key)
        self.assertNotIn("LANES.", router.calls[0]["user"])
        self.assertEqual(self.arch().prompt(), Architect(self.store, None, lane(self.settings, {}), clock=self.clock).prompt())


class Request(LaneCase):
    def test_the_lanes_block_sits_after_the_birth_quotas_and_says_the_rules(self):
        prompt = self.arch().prompt()
        lanes = prompt.index("LANES. Two research lanes")
        self.assertLess(prompt.index("BIRTH QUOTAS"), lanes)
        self.assertLess(lanes, prompt.index("In LIVING FAMILIES"))
        for text in ("DIRECTION BAR on Train", dlane.ALWAYS_IN_NOTE, "a DRIFT row (its versions failed the drift screen",
                     "equity_premium / directional / days_4_10", "DIRECTION QUOTA (the last 24 h of births)",
                     "This pass: at least 2 of its 4 births are DIRECTION"):
            self.assertIn(text, prompt)
        self.assertTrue(prompt.startswith("Propose "), "no shortfall, no lane_only: the request opens as before")
        self.assertIn("equity_premium: the equity risk premium", prompt, "the vocabulary carries the lane's class")
        self.assertIsNone(LEAK.search(prompt[lanes:prompt.index("In LIVING FAMILIES")]))

    def test_a_short_pass_opens_the_next_request_with_its_shortfall_and_the_top_failures(self):
        router = Router(self.alpha(1)[:3])
        out = self.arch(router).run()
        self.assertEqual((out["lane_short"], out["lane_births"], out["lane_refused"]),
                         (2, {"alpha": 2, "direction": 0}, {"alpha": 1, "direction": 0}), "want 4: two reserved")
        fam = self.store.add_family({"id": "dir-old", "mechanism": DMECH, "structure": "long_single", "roots": ["SPY"],
                                     "lane": "direction"}, origin="architect")
        self.store.set_state(fam["id"], **{dlane.STATE_KEY: {"objective": dlane.OBJECTIVE, "versions": {
            "1": {"at": self.store.now(), "train": {"fails": ["E5"], "eligible": False}},
            "2": {"at": self.store.now(), "train": {"fails": ["E5", "E1"], "eligible": False}}}}})
        root = Path(self.store.root)
        (root / dlane.HEALTH_FILE).write_text(json.dumps({"options_live": {"stops": {"sod_equity": "1000.00",
                                                                                       "last_reading": [0, "990.00", "x"]}}}))
        prompt = self.arch().prompt()
        self.assertTrue(prompt.startswith("THE DIRECTION LANE WAS SHORT: the last pass"), prompt[:200])
        self.assertIn("left 2 of its reserved direction births unfilled", prompt)
        self.assertIn("top failures (48 h): E5 one lot over the unit cap at today's prices (2); E1 in the market in too few "
                      "Train years (1)", prompt)
        self.assertIn("DIRECTION FAILURES (the last 48 h; counts only, the lane's own families): 1 families, 2 scored "
                      "versions, 0 eligible. Train bars: E1 1, E3 0, E4 0, E5 2 (E5 alone: 1)", prompt)
        self.assertIn("THE UNIT (E5): one lot's maximum loss with fees at today's index prices within the unit cap (at most "
                      "10% of the account's equity)", prompt)
        self.assertNotIn("$99", prompt, "the review of Oct 9: never today's cap (a share of the account's equity)")
        self.assertIn("THE LAST PASS (", prompt)
        self.assertIn("reserved direction births left unfilled: 2.", prompt)

    def test_lane_only_after_twelve_hours_without_a_direction_birth(self):
        router = Router(self.alpha(1)[:2])
        first = self.arch(router).run()
        self.assertNotIn("lane_only", first, "the lane's clock starts with its first pass")
        self.assertIsNotNone(self.store.get(dlane.STARTED_KEY))
        self.clock.advance(13 * 3600)
        router = Router(self.direction(2)[:3])
        out = self.arch(router).run()
        self.assertEqual(out["lane_only"], "no direction birth in 12 h")
        user = router.calls[0]["user"]
        self.assertTrue(user.startswith("THIS PASS ASKS FOR THE DIRECTION LANE ONLY (lane_only: no direction birth in 12 h)"))
        self.assertIn("Propose 1 new DIRECTION-lane families (\"lane\": \"direction\"), on these roots only (the Gym holds "
                      "their data): SPY, QQQ, IWM.", user, "as many as the pass's direction cap (want 2: 1)")
        self.assertEqual((out["lane_births"], out["lane_refused"]), ({"alpha": 0, "direction": 1}, {"alpha": 0, "direction": 2}))
        self.assertEqual(self.store.get(dlane.LANE_ONLY_KEY), self.store.now())
        self.clock.advance(60)
        router = Router(self.alpha(3)[:1])
        self.assertNotIn("lane_only", self.arch(router).run(), "a direction family was born: none again")

    def test_no_lane_only_at_the_lanes_ceiling(self):
        self.settings["dlane"] = {**GATE, "max_alive": 0}
        self.arch(Router(self.alpha(1)[:1])).run()
        self.clock.advance(13 * 3600)
        out = self.arch(Router(self.alpha(2)[:1])).run()
        self.assertNotIn("lane_only", out)
        self.assertIsNone(self.store.get(dlane.LANE_ONLY_KEY))


# ------------------------------------------------------------------------------------------------ the strategist (C8)
class StrategistLanes(LaneCase):
    def test_the_packet_counts_each_lane_and_asks_for_each_lanes_advice(self):
        self.arch(Router(self.direction(1)[:2] + self.alpha(1)[:1])).run()
        st = Strategist(self.store, None, self.settings, clock=self.clock)
        packet = st.packet(sample=True)
        self.assertIn("Two lanes, alpha and direction: give each lane its own advice.", packet)
        counts = st.lanes(st.architect.visible())
        self.assertEqual((counts["alpha"]["alive"], counts["direction"]["alive"]), (1, 2))
        self.assertEqual((counts["alpha"]["born_24h"], counts["direction"]["born_24h"]), (1, 2))
        self.assertEqual(sorted(counts["direction"]["alive_ids"]), ["dir-1-0", "dir-1-1"])
        self.assertEqual(counts["direction"]["train_48h"]["versions"], 0)
        self.assertIn(dlane.ALWAYS_IN_NOTE, counts["direction_lane"])
        self.assertIsNone(LEAK.search(json.dumps(counts)))
        off = Strategist(self.store, None, lane(self.settings, OFF), clock=self.clock).packet(sample=True)
        self.assertNotIn("THE TWO LANES", off)
        self.assertEqual(off, Strategist(self.store, None, lane(self.settings, {}), clock=self.clock).packet(sample=True))

    def test_the_failure_counts_leave_out_what_the_architect_may_not_read(self):
        fam = self.store.add_family({"id": "dir-hidden", "mechanism": DMECH, "structure": "long_single", "roots": ["SPY"],
                                     "lane": "direction"}, origin="architect")
        self.store.set_state(fam["id"], **{dlane.STATE_KEY: {"objective": dlane.OBJECTIVE, "versions": {
            "1": {"at": self.store.now(), "train": {"fails": ["E1"], "eligible": False}}}}})
        self.assertEqual(dlane.failure_counts(self.store, 48, now=self.clock())["versions"], 1)
        self.assertEqual(dlane.failure_counts(self.store, 48, now=self.clock(), exclude={"dir-hidden"})["versions"], 0)


if __name__ == "__main__":
    unittest.main()
