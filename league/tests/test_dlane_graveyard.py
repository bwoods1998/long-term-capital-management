"""THE DIRECTION LANE AND THE GRAVEYARD (Oct 9, 2026; league/swarm/cards.py `RebirthIndex`, the operator's decision, a
reported loosening): a DIRECTION card is bound only by the graveyard rows of DIRECTION families. An alpha family's row
(every family born outside the lane: its verdict judged a timing edge under the alpha rules) never needs a claim from a
direction card, and a DRIFT row never did (D-1). A direction family's row with any other mechanism verdict still binds
direction cards through the rebirth claim, and every row still binds alpha cards. The architect's view follows: the
LANES block says so, and the BIRTH CELLS say for each of the lane's cells how many of its rows bind a direction card.

GOLDEN: the alpha cards' verdicts on a fixture store, and every reading with `dlane.mode` "off", are pinned to what
2b60d94a (release D-1, deployed 10:37Z Oct 9) computes on the same store (`GOLDEN_ALPHA`, `GOLDEN_OFF`).

Every family, mechanism and date here is invented.
"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest

from league.swarm import cards, dlane, mechanism
from league.swarm.architect import BIRTH_CELLS_CHARS, LANE_CELLS_NOTE, Architect
from league.swarm.researcher import SELF_REFUTED, idle_cause
from league.tests.test_dlane_births import DIR, GATE, OFF, TREND, lane
from league.tests.test_swarm_cards import CARD, GOOD, Case, proposal

REFUTED = "Refuted: it loses after costs on every root tested."
MECH_DEAD = mechanism.MECHANISM_CAUSE.format(n=3)
DRIFT = idle_cause("drift")
STRESS = idle_cause("stress")
SELF = f"{SELF_REFUTED}: the wing seller was not paid after calm weeks."
TREND_TEXT = "Index trend continuation calls held a week after a breakout."
SESSION_TEXT = "Index trend continuation calls held to the next session."
PREMIUM_TEXT = "Rent the index's premium with a cheap call held to the next session."
#: The live refusal of 11:32Z Oct 9 (low-iv-drift-call): an equity_premium card whose own words read as trend_momentum.
LOW_IV_TEXT = "Low implied vol drift call: a calm trend's continuation rents the index's drift for a week."
YIELD = {"cell_yield": True}
#: sha256 (first 16 hex) of `Graves.alpha_dump` and `Graves.off_dump`, computed by 2b60d94a on this fixture.
GOLDEN_ALPHA = "567a42e489a0504b"
GOLDEN_OFF = "8cf23ded66632317"


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Graves(Case):
    """A store whose graveyard holds alpha and direction rows side by side:
    - trend_momentum / directional / days_4_10: alpha rows only (REFUTED, MECHANISM, DRIFT, a legacy REFUTED put, an
      alpha fork read by its text);
    - trend_momentum / directional / days_1_3: an alpha STRESS row and a direction fork's REFUTED row (its lane read
      through its parent's card sha);
    - equity_premium / directional / days_1_3: a direction REFUTED row (lane in its spec and its card);
    - equity_premium / directional / days_4_10: a direction DRIFT row (lane in its card only);
    - reversal_liquidity / directional / days_1_3 and skew / short_premium / days_4_10: alpha rows."""

    def setUp(self):
        super().setUp()
        self.settings["dlane"] = dict(GATE)
        gate = {"dlane": GATE}
        self.alpha_trend = cards.validate({k: v for k, v in TREND.items() if k != "lane"}, "long_single")[0]
        self.dir_trend = cards.validate(TREND, "long_single", roots=["SPY"], settings=gate)[0]
        self.dir_ep = cards.validate(DIR, "long_single", roots=["SPY"], settings=gate)[0]
        short = {**TREND, "holding": "days_1_3"}
        self.alpha_short = cards.validate({k: v for k, v in short.items() if k != "lane"}, "long_single")[0]
        self.dir_short = cards.validate(short, "long_single", roots=["SPY"], settings=gate)[0]
        self.dir_ep_short = cards.validate({**DIR, "holding": "days_1_3"}, "long_single", roots=["SPY"],
                                           settings=gate)[0]
        self.rebound = cards.validate(CARD)[0]
        self.skew = cards.validate({**CARD, "mechanism_class": "skew", "inputs": ["iv_skew"], "holding": "days_4_10",
                                    "hypothesis": "Put skew overprices crash protection after calm weeks, so the wing "
                                                  "seller is paid for bearing it through the week."}, "iron_condor")[0]
        g = self.grave
        self.a_refuted = g("alpha-trend-refuted", self.alpha_trend, reason=REFUTED, mechanism=TREND_TEXT)
        self.a_mech = g("alpha-trend-mech", {**self.alpha_trend, "inputs": ["clock", "underlying_price"]},
                        reason=MECH_DEAD, mechanism="Morning trend continuation calls held a week.")
        self.a_drift = g("alpha-trend-drift", self.alpha_trend, reason=DRIFT,
                         mechanism="Index trend continuation calls held a week, again.")
        self.a_legacy = g("persistent-ceiling-rejection-put", None, reason=REFUTED, structure="long_put",
                          mechanism="Persistent ceiling rejection: the index fails to extend its trend past "
                                    "resistance and a put held a week is paid.")
        self.a_fork = g("alpha-trend-fork", self.alpha_trend, reason=REFUTED, own=False,
                        mechanism="Trend continuation calls on QQQ held a week.")
        self.a_stress = g("alpha-trend-short-stress", self.alpha_short, reason=STRESS, mechanism=SESSION_TEXT,
                          dte=(1, 3))
        parent = self.store.add_family({"id": "dir-trend-parent", "mechanism": "Trend calls to the next session.",
                                        "structure": "long_single", "roots": ["SPY"], "dte": [1, 3],
                                        "lane": "direction", "card_sha": cards.card_sha(self.dir_short)},
                                       origin="architect")
        cards.put(self.store, parent["id"], self.dir_short, "long_single")
        self.d_fork = g("dir-trend-fork", self.dir_short, reason=REFUTED, own=False, dte=(1, 3),
                        mechanism="Index trend continuation: a call bought after a breakout and held to the next "
                                  "session.")
        self.d_refuted = g("dir-ep-refuted", self.dir_ep_short, reason=REFUTED, spec_lane="direction", dte=(1, 3),
                           mechanism=PREMIUM_TEXT)
        self.d_drift = g("dir-ep-drift", self.dir_ep, reason=DRIFT,
                         mechanism="Rent the index's premium with a cheap call held a week.")
        self.a_rebound = g("alpha-rebound", self.rebound, reason=REFUTED, structure="debit_vertical", dte=(0, 5),
                           mechanism="Late-day liquidity-demanding selling rebounds over the next session.")
        self.a_skew = g("alpha-skew-self", self.skew, reason=SELF, structure="iron_condor",
                        mechanism="Put skew richness after calm weeks pays the wing seller.")

    def grave(self, fid, card, *, reason, mechanism, structure="long_single", dte=(4, 10), own=True, spec_lane=None):
        """A dead family a minute after the last: carded (its own card, or with `own` False a fork's: its spec's
        card_sha only), `spec_lane` written in its spec as the architect writes a direction birth's."""
        self.clock.t += 60
        spec = {"id": fid, "mechanism": mechanism, "structure": structure, "roots": ["SPY"], "dte": list(dte)}
        if spec_lane:
            spec["lane"] = spec_lane
        if card is not None:
            spec["card_sha"] = cards.card_sha(card)
        fam = self.store.add_family(spec, origin="architect")
        if card is not None and own:
            cards.put(self.store, fam["id"], card, structure)
        self.assertEqual(self.store.retire_gym(fam["id"], reason, floor=0, source="test")["status"], "retired")
        return fam["id"]

    def index(self, settings=None) -> cards.RebirthIndex:
        return cards.RebirthIndex(self.store, self.settings if settings is None else settings)

    def with_(self, *, dlane=None, architect=None) -> dict:
        out = copy.deepcopy(self.settings)
        if dlane is not None:
            out = lane(out, dlane)
        if architect:
            out["architect"] = {**out["architect"], **architect}
        return out

    # ------------------------------------------------------------------------------------------------ the proposals
    def alpha_proposals(self) -> list[tuple]:
        """(slug, card, structure, mechanism, dte): alpha cards, as every pass before the lane wrote them."""
        wider = {**self.alpha_trend, "inputs": ["implied_vol", "open_interest", "underlying_price"]}
        calendar = {**self.alpha_trend, "mechanism_class": "calendar_flow"}
        dispersion = {**self.skew, "mechanism_class": "dispersion", "inputs": ["cross_asset"],
                      "holding": "days_11_plus",
                      "hypothesis": "Index volatility against its members' prices implied correlation too high into "
                                    "the month, so selling it is paid."}
        return [
            ("trend-week", self.alpha_trend, "long_single", TREND_TEXT, [4, 10]),
            ("trend-session", self.alpha_short, "long_single", SESSION_TEXT, [1, 3]),
            ("rebound", self.rebound, "debit_vertical", "Late-day selling rebounds over the next session.", [0, 5]),
            ("skew-week", self.skew, "iron_condor", "Put skew richness after calm weeks pays the wing seller.",
             [4, 10]),
            ("trend-week-reborn", {**wider, "rebirth": {"row": self.a_refuted, **GOOD}}, "long_single", TREND_TEXT,
             [4, 10]),
            ("dispersion", dispersion, "iron_condor", "Implied correlation rich into the month.", [11, 30]),
            ("calendar-reads-trend", calendar, "debit_vertical", TREND_TEXT, [4, 10]),
            ("trend-week-vague", {**wider, "rebirth": {"row": self.a_refuted, **GOOD, "evidence": "e" * 50}},
             "long_single", TREND_TEXT, [4, 10]),
            ("trend-week-names-a-direction-row", {**wider, "rebirth": {"row": self.d_fork, **GOOD}}, "long_single",
             TREND_TEXT, [4, 10]),
        ]

    def direction_proposals(self) -> list[tuple]:
        """Direction cards (validated with the lane on, so each carries "lane": "direction")."""
        wider = {**self.dir_trend, "inputs": ["implied_vol", "open_interest", "underlying_price"]}
        wider_short = {**self.dir_short, "inputs": ["implied_vol", "open_interest", "underlying_price"]}
        return [
            ("low-iv-drift-call", self.dir_ep, "long_single", LOW_IV_TEXT, [4, 10]),
            ("calm-trend-drift-call", self.dir_trend, "long_single", TREND_TEXT, [4, 10]),
            ("trend-session-call", self.dir_short, "long_single", SESSION_TEXT, [1, 3]),
            ("premium-session-call", self.dir_ep_short, "long_single", PREMIUM_TEXT, [1, 3]),
            ("trend-session-reborn", {**wider_short, "rebirth": {"row": self.d_fork, **GOOD}}, "long_single",
             SESSION_TEXT, [1, 3]),
            ("trend-week-claims-alpha", {**wider, "rebirth": {"row": self.a_refuted, **GOOD}}, "long_single",
             TREND_TEXT, [4, 10]),
            ("trend-week-vague", {**wider, "rebirth": {"row": self.a_refuted, **GOOD, "evidence": "e" * 50}},
             "long_single", TREND_TEXT, [4, 10]),
        ]

    @staticmethod
    def verdicts(index, items) -> list:
        return [[slug, index.check(card, structure, text, dte)] for slug, card, structure, text, dte in items]

    def readings(self, index) -> dict:
        """The cells and what each bears (an alpha birth's, and a direction birth's)."""
        families = ("directional", "short_premium")
        grid = index.grid(families)
        return {"cells": index.cells(claimable=3), "cells_f1": index.cells(claimable=3, families=families,
                                                                           chars=BIRTH_CELLS_CHARS),
                "grid": [[list(cell), [r["row"] for r in rows]] for cell, rows in grid],
                "bearable": [[list(cell), index.bearable(cell, rows), index.bearable(cell, rows, "direction")]
                             for cell, rows in grid]}

    def alpha_dump(self) -> list:
        """Every alpha card's verdict, the lane off and on, the cell's yield off and on, and what an alpha birth
        bears."""
        out = []
        for dl in (OFF, GATE):
            for arch in ({}, YIELD):
                index = self.index(self.with_(dlane=dl, architect=arch))
                grid = index.grid(("directional", "short_premium"))
                out.append([dl["mode"], bool(arch), self.verdicts(index, self.alpha_proposals()),
                            [[list(cell), index.bearable(cell, rows)] for cell, rows in grid]])
        return out

    def off_dump(self) -> list:
        """Every reading with the lane off: alpha and direction-shaped cards' verdicts, the cells, the grid, what a
        birth bears, the architect's card section, LANES block and closed pass."""
        out = []
        for arch in ({}, YIELD, {"structures": ["debit_vertical", "long_single"], "max_rebirths_per_cell": 0}):
            settings = self.with_(dlane=OFF, architect=arch)
            index = self.index(settings)
            a = Architect(self.store, None, settings, clock=self.clock)
            # A claim's verdict at a cell budget of 0 is left out: 2b60d94a raises KeyError there (`_claim` reads
            # `cell_births[cell]` for a cell with no rebirth yet); no deployed setting reaches it (policy.json: 12).
            judged = (self.verdicts(index, self.alpha_proposals() + self.direction_proposals())
                      if "max_rebirths_per_cell" not in arch else None)
            out.append([sorted(arch), judged, self.readings(index), a.card_block(), a.lanes_block(), a.closed()])
        return out


class DirectionCards(Graves):
    def proposals(self) -> dict:
        return {slug: (card, structure, text, dte) for slug, card, structure, text, dte in self.direction_proposals()}

    def check(self, slug, index=None):
        card, structure, text, dte = self.proposals()[slug]
        return (index or self.index()).check(card, structure, text, dte)

    def test_each_row_carries_its_familys_lane_read_as_d1_stores_it(self):
        lanes = {r["row"]: r["lane"] for r in self.index().rows}
        self.assertEqual({k for k, v in lanes.items() if v == "direction"},
                         {self.d_fork, self.d_refuted, self.d_drift}, "the sha, the spec and the card each read")
        for row in self.index().rows:
            fam = self.store.family(row["row"])
            self.assertEqual(row["lane"], dlane.declared_lane(self.store, fam), row["row"])
        self.assertTrue(all("lane" not in r for r in self.index(self.with_(dlane=OFF)).rows), "off: rows as before")
        sha = {"s1": "direction"}
        self.assertEqual(cards.row_lane({"spec": json.dumps({"lane": "alpha"})}, self.dir_trend, sha), "alpha",
                         "the spec's lane first, as dlane.declared_lane reads it")
        self.assertEqual(cards.row_lane({"spec": json.dumps({"card_sha": "s1"})}, None, sha), "direction")
        self.assertEqual(cards.row_lane({"spec": json.dumps({"card_sha": "s2"})}, None, sha), "alpha")
        self.assertEqual(cards.row_lane({"spec": "{not json"}, None, sha), "alpha")
        self.assertEqual(cards.row_lane(None, None, sha), "alpha", "a row whose family is gone is alpha")

    def test_a_direction_card_among_alpha_rows_only_is_admitted(self):
        live = self.check("low-iv-drift-call")
        self.assertTrue(live["ok"], live)
        self.assertEqual((live["drift_lane"], live["alpha_rows"], live["text_class"], live["count"]),
                         (True, 5, "trend_momentum", 6), "the trend cell's five alpha rows and the lane's DRIFT row")
        self.assertNotIn("open", live)
        calm = self.check("calm-trend-drift-call")
        self.assertTrue(calm["ok"], calm)
        self.assertEqual(sorted(calm["matched"]), sorted([self.a_refuted, self.a_mech, self.a_drift, self.a_legacy,
                                                          self.a_fork]))
        self.assertEqual(calm["alpha_rows"], 5)
        # D-1 (2b60d94a) refused both: the alpha REFUTED and MECHANISM rows bound them (the live refusal of 11:32Z).
        for slug in ("low-iv-drift-call", "calm-trend-drift-call"):
            before = self.check(slug, self.index(self.with_(dlane=OFF)))
            self.assertFalse(before["ok"])
            self.assertEqual((before["row"], before["need"]), (self.a_fork, 4))
            self.assertIn("(a DRIFT row binds no direction card)", before["reason"])
        with_yield = self.check("calm-trend-drift-call", self.index(self.with_(architect=YIELD)))
        self.assertTrue(with_yield["ok"])
        self.assertEqual(with_yield["drift_lane"], True, "the lane, not the cell's yield, excused the REFUTED rows")

    def test_a_direction_familys_row_still_needs_a_claim(self):
        index = self.index()
        refused = self.check("trend-session-call", index)
        self.assertFalse(refused["ok"])
        self.assertEqual((refused["row"], refused["tag"], refused["need"], refused["alpha_rows"]),
                         (self.d_fork, "REFUTED", 1, 1), "a fork's row: its lane read through its parent's card")
        self.assertIn("the newest dir-trend-fork (REFUTED) of the 1 that need a claim (only a direction family's row "
                      "binds a direction card, and never a DRIFT row): a birth there needs card.rebirth",
                      refused["reason"])
        own = self.check("premium-session-call", index)
        self.assertFalse(own["ok"])
        self.assertEqual((own["row"], own["count"]), (self.d_refuted, 1))
        self.assertNotIn("alpha_rows", own)
        reborn = self.check("trend-session-reborn", index)
        self.assertEqual((reborn["ok"], reborn.get("rebirth"), reborn["row"], reborn["new_inputs"]),
                         (True, True, self.d_fork, ["implied_vol", "open_interest"]))
        index.note_birth(self.proposals()["trend-session-reborn"][0], "long_single")
        self.assertEqual(index.backed[self.d_fork], 1, "the row's and the cell's budgets are spent as before")
        self.assertEqual(index.cell_births[("trend_momentum", "directional", "days_1_3")], 1)
        yielded = self.check("trend-session-call", self.index(self.with_(architect=YIELD)))
        self.assertFalse(yielded["ok"])
        self.assertIn("never a DRIFT row; an open cell's self-refuted and drift rows need none)", yielded["reason"])

    def test_a_claim_on_an_alpha_row_is_checked_as_on_a_drift_row(self):
        index = self.index()
        good = self.check("trend-week-claims-alpha", index)
        self.assertEqual((good["ok"], good.get("rebirth"), good.get("drift_lane"), good["row"], good["alpha_rows"]),
                         (True, True, True, self.a_refuted, 5))
        vague = self.check("trend-week-vague", index)
        self.assertTrue(vague["ok"])
        self.assertIn("cites nothing checkable", vague["dropped"], "stripped before the card is stored")
        self.assertNotIn("rebirth", vague)

    def test_alpha_cards_are_still_bound_by_every_row(self):
        index = self.index()
        verdicts = dict(self.verdicts(index, self.alpha_proposals()))
        self.assertEqual({k: (v["ok"], v.get("row")) for k, v in verdicts.items() if not v["ok"]},
                         {"trend-week": (False, self.a_fork), "trend-session": (False, self.d_fork),
                          "rebound": (False, self.a_rebound), "skew-week": (False, self.a_skew),
                          "calendar-reads-trend": (False, self.a_fork), "trend-week-vague": (False, self.a_refuted),
                          "trend-week-names-a-direction-row": (False, self.a_fork)})
        self.assertTrue(all("alpha_rows" not in v and "drift_lane" not in v for v in verdicts.values()))
        self.assertEqual(verdicts, dict(self.verdicts(self.index(self.with_(dlane=OFF)), self.alpha_proposals())),
                         "the lane on or off, an alpha card's verdicts are the same")


class TheArchitectsView(Graves):
    def arch(self, settings=None) -> Architect:
        return Architect(self.store, None, self.settings if settings is None else settings, clock=self.clock)

    def test_the_live_refusals_are_born(self):
        a = self.arch()
        born = a.admit([proposal("low-iv-drift-call", card=DIR, structure="long_single", mechanism=LOW_IV_TEXT,
                                 dte=[4, 10]),
                        proposal("calm-trend-drift-call", card=TREND, structure="long_single", mechanism=TREND_TEXT,
                                 dte=[4, 10])])
        self.assertEqual((born, a.card_refused), (["low-iv-drift-call", "calm-trend-drift-call"], []))
        events = {e["family"]: e["payload"] for e in self.store.events_after(0, limit=10_000)
                  if e["kind"] == "swarm.born"}
        for fid in born:
            card = events[fid]["card"]
            self.assertEqual((events[fid]["lane"], card["drift_lane"], card["alpha_rows"], card["rebirth"]),
                             ("direction", True, 5, None))
            self.assertEqual(self.store.family(fid)["spec"]["lane"], "direction")

    def test_off_the_same_proposals_meet_the_release_before(self):
        a = self.arch(self.with_(dlane=OFF))
        born = a.admit([proposal("calm-trend-drift-call", card=TREND, structure="long_single", mechanism=TREND_TEXT,
                                 dte=[4, 10])])
        self.assertEqual(born, [])
        self.assertIn("the newest alpha-trend-fork (REFUTED): a birth there needs card.rebirth",
                      a.card_refused[0]["why"])

    def test_the_lanes_block_and_the_birth_cells_say_what_binds_a_direction_card(self):
        self.settings["architect"].update(structures=["debit_vertical", "long_single"], claimable_rows=2)
        a = self.arch()
        lanes = a.lanes_block()
        self.assertIn("a direction card is bound only by the graveyard rows of DIRECTION families. An alpha "
                      "family's row (every family born outside the direction lane: its verdict judged a timing edge "
                      "under the alpha rules) never binds a direction card, and neither does a DRIFT row (its versions "
                      "failed the drift screen", lanes)
        self.assertNotIn("every other verdict binds both lanes", lanes)
        block = a.card_block()
        self.assertIn(LANE_CELLS_NOTE + ":\n", block)
        lines = {line.split(":")[0]: line for line in block.splitlines() if " / " in line.split(":")[0]}
        for cell, note in (("trend_momentum / directional / days_4_10",
                            "no row binds one (alpha families' and DRIFT rows"),
                           ("trend_momentum / directional / days_1_3", "1 of its rows binds one (direction families')"),
                           ("equity_premium / directional / days_1_3", "1 of its rows binds one"),
                           ("equity_premium / directional / days_4_10", "no row binds one")):
            self.assertIn("; a direction card: " + note, lines[cell])
        self.assertNotIn("a direction card", lines["reversal_liquidity / directional / days_1_3"],
                         "not a direction cell")
        self.assertTrue(lines["trend_momentum / directional / days_4_10"].startswith(
            "trend_momentum / directional / days_4_10: 5 rows (3 carded), rebirth room 3, newest alpha-trend-drift"),
            "the alpha reading of the line is kept, word for word")
        off = self.arch(self.with_(dlane=OFF)).card_block()
        self.assertNotIn("a direction card", off.lower().replace("a direction card's class", ""))

    def test_no_paid_pass_is_skipped_for_alpha_rows_a_direction_card_ignores(self):
        self.settings["architect"].update(structures=["debit_vertical", "long_single"], max_rebirths_per_cell=0)
        self.settings["dlane"] = {**GATE, "classes": ["trend_momentum"]}
        for c in cards.MECHANISM_CLASSES:
            for h in cards.HOLDING:
                if c != "trend_momentum":
                    filler = cards.validate({**CARD, "mechanism_class": c, "holding": h})[0]
                    self.grave(f"fill-{c}-{h}".replace("_", "-"), filler, reason=REFUTED, structure="debit_vertical",
                               mechanism=f"Filler {c} {h} edge refuted.")
        for h in ("intraday", "days_11_plus"):
            self.grave(f"fill-trend-{h}".replace("_", "-"), cards.validate({**TREND, "holding": h})[0], reason=REFUTED,
                       mechanism=f"Filler trend {h} edge refuted.")
        self.assertIsNotNone(self.arch(self.with_(dlane=OFF)).closed(), "off: every cell needs a claim at room 0")
        self.assertIsNone(self.arch().closed(),
                          "the trend days_4_10 cell holds alpha rows only: a direction card bears it")
        self.grave("dir-trend-week-dead", self.dir_trend, reason=REFUTED, spec_lane="direction",
                   mechanism="Index trend continuation calls held a week, refuted in the lane.")
        self.assertEqual(self.arch().closed(), {"cells": 44, "full": 44, "spent": 0},
                         "a direction family's REFUTED row closes the lane's last open cell")


class Golden(Graves):
    def test_alpha_cards_are_judged_as_before(self):
        self.assertEqual(digest(self.alpha_dump()), GOLDEN_ALPHA)

    def test_the_lane_off_is_the_release_before_byte_for_byte(self):
        self.assertEqual(digest(self.off_dump()), GOLDEN_OFF)


if __name__ == "__main__":
    unittest.main()
