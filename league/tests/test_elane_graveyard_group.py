"""THE EQUITY GRAVEYARD'S UNIVERSE GROUP (Oct 15, 2026; league/swarm/cards.py `universe_group`, `groups_meet`,
`RebirthIndex`; after the captain's A35 widening of `elane.universe` to sixteen ETFs). An equity card's graveyard cell is
(mechanism class, lane-scoped structure family, holding, UNIVERSE GROUP): index (SPY QQQ IWM DIA), sectors (the XL*
ETFs), defensive (TLT, GLD), stocks, or a mixed label ("index+sectors"), the groups of `elane_train.symbols_group` (the
Train map's cells, FWD1-R's mechanism cells and the forward controls' groups). A row binds an equity card only when
their groups MEET (share a group), so a mechanism refuted on the index ETFs no longer closes it on sector, bond or gold
ETFs, and a card naming one extra symbol of another group never escapes a row of its own group.

WHY: the first births pass after the widening (03:43:16Z Oct 15) proposed six sector cards and the index rows refused
every one ("graveyard: its cell (trend_momentum / equity:etf / days_11_plus / underlying_price) holds 1 graveyard
row(s) killed by a mechanism verdict, the newest trend-spy (REFUTED) ...").

GOLDEN: on a fixture store holding options rows (alpha and direction: test_dlane_graveyard's `Graves`) and the equity
index rows the live store holds (every equity row before the widening trades index ETFs), every options reading and every
index card's verdict are pinned to what aec0c8a5 (release U, before this change) computes on the same store
(`GOLDEN_OPTIONS`, `GOLDEN_INDEX`); an index card's refusal text only gains its group's name (`plain`).

Every family, mechanism and date here is invented.
"""

from __future__ import annotations

import copy
import re
import unittest
from unittest import mock

from league.swarm import cards, elane, elane_train
from league.tests.test_dlane_births import GATE, OFF
from league.tests.test_dlane_graveyard import YIELD, Graves, digest

INDEX = ["SPY", "QQQ", "IWM", "DIA"]
SECTORS = ["XLB", "XLC", "XLE", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
DEFENSIVE = ["TLT", "GLD"]
#: The lanes on at A35's universe (SPY first, XLF out).
ELANE = {"mode": "gate", "universe": [*INDEX, *SECTORS, *DEFENSIVE], "structures": ["etf"], "birth_share": 0.5}
ELANE_OFF = {"mode": "off"}
#: sha256 (first 16 hex) of `GroupGraves.options_dump` and `GroupGraves.index_dump`, computed by aec0c8a5 (release U)
#: on this fixture.
GOLDEN_OPTIONS = "ebb56294c7322d2e"
GOLDEN_INDEX = "a98297e5214d6543"

#: The six mechanisms of the 03:43Z pass: (slug, lane, class, holding, inputs, agenda, the dead index row's mechanism,
#: the dead row's symbols, the sector proposal's mechanism, the sector proposal's symbols).
SIX = (
    ("trend", "equity", "trend_momentum", "days_11_plus", ["underlying_price"], "trend",
     "Index trend: hold SPY while it closes above its 200-session average and step aside below it.", ["SPY"],
     "Industry momentum: the sector ETFs with the best twelve-month return keep outperforming for months.",
     ["XLE", "XLI", "XLK", "XLV", "XLY"]),
    ("rotation", "equity", "relative_value", "days_11_plus", ["cross_asset", "underlying_price"], "rotation",
     "Rotate monthly into the index ETF with the strongest relative strength over three months.", INDEX,
     "Sector rotation: hold the three sector ETFs with the strongest relative strength, rebalanced monthly.", SECTORS),
    ("low-vol", "equity", "equity_premium", "days_11_plus", ["realized_vol", "underlying_price"], "low_vol",
     "Hold the index ETFs only while their realized volatility is below its yearly median.", ["SPY", "QQQ"],
     "Low volatility: the calmest sector ETFs earn the market's return with less risk than the rest.",
     ["XLP", "XLU", "XLV"]),
    ("reversal", "equity", "reversal_liquidity", "days_1_3", ["underlying_price"], "reversal",
     "Buy QQQ or IWM after a sharp one-session drop and sell two sessions later as it rebounds.", ["IWM", "QQQ"],
     "Short-term reversal: a sector ETF's sharp one-session drop rebounds over the next two sessions.", ["XLE", "XLK"]),
    ("overnight-down", "beta", "calendar_flow", "days_1_3", ["clock", "underlying_price"], "overnight",
     "Hold SPY overnight only after a down session, when holders demand more to carry the gap.", ["SPY"],
     "Hold sector ETFs overnight only after a down session, when holders demand more to carry the gap.",
     ["XLK", "XLY"]),
    ("turn-of-month", "beta", "calendar_flow", "days_4_10", ["clock"], "turn_of_month",
     "Hold DIA over the last session and first three sessions of each month, when pay flows arrive.", ["DIA"],
     "Hold sector ETFs over the turn of the month, when pay and pension flows arrive.", ["XLB", "XLI"]),
)


def ecard(lane: str, cls: str, holding: str, inputs: list[str], symbols: list[str], **over) -> dict:
    """A raw equity card (validated by `GroupGraves.valid`)."""
    out = {"lane": lane, "structure": "etf", "symbols": list(symbols),
           "hypothesis": f"Invented test card for {cls}: holders on these ETFs are paid by a {holding} flow that the "
                         "comparison does not hold.",
           "mechanism_class": cls, "inputs": list(inputs), "holding": holding,
           "cost": {"hurdle": 0.0006, "why": "two half-spreads and the SEC and TAF fees on the sale"},
           "comparison": "the same-exposure buy-and-hold of the same ETFs over the same sessions (S1-X)",
           "falsification": "refuted when its Train record fails the equity-v1 bar (net P&L at or below zero)"}
    out.update(over)
    return out


def plain(obj):
    """An index card's verdict as the release before wrote it: the cell text without its universe group's name."""
    if isinstance(obj, str):
        return re.sub(r" / universe group [a-z+]+", "", obj)
    if isinstance(obj, list):
        return [plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    return obj


class GroupGraves(Graves):
    """`Graves`' options rows and, beside them, the six mechanisms refuted on the index ETFs (carded, lanes equity and
    beta, a minute apart), as the live store held them at 03:43Z Oct 15."""

    def setUp(self):
        super().setUp()
        self.settings["elane"] = dict(ELANE)
        self.index_rows = {}
        for slug, lane, cls, holding, inputs, _, dead_text, dead_symbols, _, _ in SIX:
            self.index_rows[slug] = self.equity_grave(f"{slug}-index", ecard(lane, cls, holding, inputs, dead_symbols),
                                                      mechanism=dead_text)

    def valid(self, raw: dict, symbols=None) -> dict:
        got, errors = cards.validate(raw, "etf", roots=list(symbols or raw["symbols"]), settings={"elane": ELANE})
        self.assertEqual(errors, [], raw)
        return got

    def equity_grave(self, fid: str, raw: dict, *, mechanism: str, reason: str = "REFUTED on Train (equity-v1): an "
                     "invented Train lesson.") -> str:
        """A dead equity family a minute after the last: its card stored, retired and buried as E2 retires a Train
        refutation."""
        self.clock.t += 60
        card = self.valid(raw)
        spec = {"id": fid, "mechanism": mechanism, "structure": "etf", "roots": list(card["symbols"]),
                "symbols": list(card["symbols"]), "lane": card["lane"], "card_sha": cards.card_sha(card)}
        fam = self.store.add_family(spec, origin="architect")
        cards.put(self.store, fam["id"], card, "etf")
        self.assertTrue(self.store.retire(fam["id"], reason))
        self.store.bury(fam["id"], reason)
        return fam["id"]

    def with_e(self, *, dlane=None, architect=None, elane_block=None) -> dict:
        out = self.with_(dlane=dlane, architect=architect)
        out["elane"] = dict(ELANE if elane_block is None else elane_block)
        return out

    def proposals(self, which: str) -> list[tuple]:
        """(slug, card, mechanism, symbols): the six cards on the index ETFs ("index") or on the sectors ("sectors")."""
        out = []
        for slug, lane, cls, holding, inputs, _, dead_text, dead_symbols, text, symbols in SIX:
            names = dead_symbols if which == "index" else symbols
            words = dead_text if which == "index" else text
            out.append((f"{slug}-{which}", self.valid(ecard(lane, cls, holding, inputs, names)), words, names))
        return out

    @staticmethod
    def equity_verdicts(index, items) -> list:
        return [[slug, index.check(card, "etf", text, None, roots=symbols)] for slug, card, text, symbols in items]

    def options_cards(self) -> list:
        """Every options card of the fixtures (alpha and direction proposals, and the rows' cards)."""
        return [[slug, card, structure] for slug, card, structure, _, _ in
                self.alpha_proposals() + self.direction_proposals()] + [
            ["rebound", self.rebound, "debit_vertical"], ["skew", self.skew, "iron_condor"],
            ["alpha-trend", self.alpha_trend, "long_single"], ["dir-trend", self.dir_trend, "long_single"],
            ["dir-ep", self.dir_ep, "long_single"], ["dir-short", self.dir_short, "long_single"]]

    def options_dump(self) -> list:
        """Every options reading with the equity lanes on and off, the direction lane off and on, the cell's yield off
        and on: alpha and direction verdicts, the cells, the grid, what a birth bears, the rows listed for an options
        card; and every options card's key and key text."""
        out = []
        for eb in (ELANE, ELANE_OFF):
            for dl in (OFF, GATE):
                for arch in ({}, YIELD):
                    index = cards.RebirthIndex(self.store, self.with_e(dlane=dl, architect=arch, elane_block=eb))
                    row = [eb["mode"], dl["mode"], bool(arch), self.verdicts(index, self.alpha_proposals()),
                           self.readings(index), [r["row"] for r in index.rows]]
                    if dl is GATE:
                        row.append(self.verdicts(index, self.direction_proposals()))
                    out.append(row)
        keys = [[slug, cards.key_of(card, structure), cards.key_text(cards.key_of(card, structure))]
                for slug, card, structure in self.options_cards()]
        return [out, keys]

    def index_dump(self) -> list:
        """Every index card's verdict (the yield off and on, the direction lane off and on) and the equity rows read."""
        out = []
        for dl in (OFF, GATE):
            for arch in ({}, YIELD):
                index = cards.RebirthIndex(self.store, self.with_e(dlane=dl, architect=arch))
                out.append([dl["mode"], bool(arch), plain(self.equity_verdicts(index, self.proposals("index"))),
                            sorted(r["row"] for r in index.equity_rows)])
        return out


class TheGolden(GroupGraves):
    def test_options_readings_are_release_us(self):
        self.assertEqual(digest(self.options_dump()), GOLDEN_OPTIONS)

    def test_index_cards_are_bound_as_release_u_bound_them(self):
        self.assertEqual(digest(self.index_dump()), GOLDEN_INDEX)

    def test_options_cards_carry_no_group(self):
        for slug, card, structure in self.options_cards():
            self.assertIsNone(cards.universe_group(card, structure), slug)
            self.assertEqual(cards.graveyard_key(card, structure), cards.key_of(card, structure), slug)
            key = cards.key_of(card, structure)
            self.assertEqual(cards.budget_cells(key, cards.universe_group(card, structure)), [cards.cell_of(key)], slug)
            self.assertNotIn("universe group", cards.key_text(cards.key_of(card, structure)), slug)
        index = cards.RebirthIndex(self.store, self.with_e(dlane=GATE))
        self.assertFalse(any("group" in r["key"] for r in index.rows), "no options row's key gains a group")


class TheSixCards(GroupGraves):
    """The six sector cards of 03:43Z: in their index row's cell by class, family, holding and inputs (so release U
    refused each), and free of it by universe group."""

    def test_no_index_row_binds_a_sector_card(self):
        for dl in (OFF, GATE):
            for arch in ({}, YIELD):
                index = cards.RebirthIndex(self.store, self.with_e(dlane=dl, architect=arch))
                for (slug, card, text, symbols), (dead_slug, *_) in zip(self.proposals("sectors"), SIX):
                    row = index.by_id[self.index_rows[dead_slug]]
                    keys, _ = cards.match_keys(card, "etf", text)
                    self.assertTrue(cards.matches(keys[0], row["key"]), f"{slug}: the index row's cell, but for the group")
                    self.assertEqual(row["key"]["group"], "index")
                    verdict = index.check(card, "etf", text, None, roots=symbols)
                    self.assertEqual(verdict, {"ok": True, "matched": []}, (slug, dl["mode"], bool(arch)))

    def test_each_index_card_is_still_refused_by_its_row(self):
        index = cards.RebirthIndex(self.store, self.with_e(dlane=GATE))
        for (slug, card, text, symbols), (dead_slug, *_) in zip(self.proposals("index"), SIX):
            verdict = index.check(card, "etf", text, None, roots=symbols)
            self.assertFalse(verdict["ok"], slug)
            self.assertEqual((verdict["matched"], verdict["row"], verdict["tag"]),
                             ([self.index_rows[dead_slug]], self.index_rows[dead_slug], "REFUTED"))
            self.assertTrue(verdict["key"].endswith(" / universe group index"), verdict["key"])
            self.assertIn("a birth there needs card.rebirth naming one of them", verdict["reason"])

    def test_the_stored_keys_and_key_of_never_carry_the_group(self):
        """`put` stores `key_of`'s key (the born payload, the cell yields and the researcher read it): unchanged."""
        for r in self.store._all("SELECT family, key FROM family_cards"):
            self.assertNotIn("group", r["key"], r["family"])
        for slug, card, _, symbols in self.proposals("sectors"):
            self.assertNotIn("group", cards.key_of(card, "etf"))
            self.assertEqual(cards.graveyard_key(card, "etf", symbols)["group"], "sectors", slug)


TREND = SIX[0]


class TheGroupRule(GroupGraves):
    """A row binds an equity card only when their universe groups meet."""

    def trend(self, symbols, **over) -> dict:
        _, lane, cls, holding, inputs, *_ = TREND
        return self.valid(ecard(lane, cls, holding, over.pop("inputs", inputs), symbols, **over))

    def verdict(self, symbols, settings=None, card=None):
        index = cards.RebirthIndex(self.store, settings or self.with_e(dlane=GATE))
        return index.check(card or self.trend(symbols), "etf", TREND[8], None, roots=symbols)

    def test_a_sector_row_binds_sector_cards_and_no_index_card(self):
        dead = self.equity_grave("trend-xlk", self.trend(["XLK"]), mechanism="Hold XLK while it closes above its "
                                                                              "200-session average.")
        self.assertEqual(self.verdict(["XLE", "XLV"])["matched"], [dead], "a sector row binds every sector card")
        self.assertEqual(self.verdict(["SPY"])["matched"], [self.index_rows["trend"]], "and no index card")
        self.assertEqual(self.verdict(["TLT"]), {"ok": True, "matched": []}, "nor a defensive one")

    def test_a_mixed_card_never_escapes_a_row_of_either_group(self):
        dead = self.equity_grave("trend-xlk", self.trend(["XLK"]), mechanism="Hold XLK while it closes above its "
                                                                              "200-session average.")
        for symbols in (["SPY", "XLE"], ["XLE", "XLK", "XLV", "DIA"]):
            got = self.verdict(symbols)
            self.assertFalse(got["ok"])
            self.assertEqual(got["matched"], [self.index_rows["trend"], dead], "one extra symbol escapes no row")
            self.assertIn("universe group index+sectors", got["key"])

    def test_a_mixed_row_binds_each_group_it_traded(self):
        dead = self.equity_grave("trend-mixed", self.trend(["QQQ", "XLV"]), mechanism="Hold QQQ and XLV while each "
                                                                                       "closes above its average.")
        self.assertEqual(self.verdict(["XLB"])["matched"], [dead])
        self.assertEqual(self.verdict(["SPY"])["matched"], [self.index_rows["trend"], dead])
        self.assertEqual(self.verdict(["GLD"]), {"ok": True, "matched": []})

    def test_the_defensive_group_is_its_own(self):
        dead = self.equity_grave("trend-gld", self.trend(["GLD"]), mechanism="Hold GLD while it closes above its "
                                                                              "200-session average.")
        self.assertEqual(self.verdict(["TLT"])["matched"], [dead])
        self.assertEqual(self.verdict(["XLU"]), {"ok": True, "matched": []})
        self.assertEqual(self.verdict(["SPY", "TLT"])["matched"], [self.index_rows["trend"], dead])

    def test_a_row_whose_symbols_cannot_be_read_binds_every_group(self):
        """FAIL CLOSED: a row with no readable group binds as release U bound it."""
        with mock.patch.object(cards, "row_group", lambda *a: None):
            self.assertEqual(self.verdict(["XLE"])["matched"], [self.index_rows["trend"]])
        self.assertIsNone(cards.row_group({"structure": "etf", "roots": "not json"}, {"spec": {}}, None))
        self.assertIsNone(cards.row_group({"structure": "etf", "roots": '["SPY", "EFA"]'}, {"spec": {}}, None))
        self.assertEqual(cards.row_group({"structure": "etf", "roots": '["SPY"]'}, {"spec": {"symbols": ["XLK"]}}, None),
                         "index+sectors", "every symbol the row is known by")

    def test_the_groups_are_the_train_maps(self):
        from league.ops import forward_controls

        self.assertEqual([cards.symbols_group(x) for x in (INDEX, SECTORS, DEFENSIVE, ["DIA", "XLRE", "GLD"])],
                         ["index", "sectors", "defensive", "index+sectors+defensive"])
        for group in ("index", "sectors", "defensive"):
            names = forward_controls.group_symbols(group, ELANE["universe"])
            self.assertTrue(names)
            self.assertEqual(cards.symbols_group(names), group)
            self.assertEqual(cards.symbols_group(names), elane_train.symbols_group(names))
        for unread in ([], ["EFA"], ["SPY", "EFA"]):
            self.assertIsNone(cards.symbols_group(unread), unread)
        self.assertTrue(cards.groups_meet("index+sectors", "sectors"))
        self.assertFalse(cards.groups_meet("index", "sectors"))
        self.assertTrue(cards.groups_meet(None, "sectors") and cards.groups_meet("index", None))

    def test_options_panel_and_unread_cards_have_no_group(self):
        panel = {"lane": "equity", "structure": "panel", "panel": "p1", "mechanism_class": "trend_momentum"}
        self.assertIsNone(cards.universe_group(panel, "panel"))
        self.assertIsNone(cards.universe_group({**panel, "structure": "etf", "symbols": ["XLK"]}, "panel"))
        self.assertIsNone(cards.universe_group({"lane": "equity", "structure": "etf"}, "etf"), "no symbols: none")
        self.assertIsNone(cards.universe_group({"lane": "equity", "symbols": ["XLK"]}, "etf", "XLK"), "unread roots")
        self.assertIsNone(cards.universe_group({**self.rebound, "symbols": ["XLK"]}, "debit_vertical"), "options")
        self.assertEqual(cards.universe_group({"lane": "beta", "symbols": ["XLK"]}, "etf", ["SPY"]), "index+sectors")
        self.assertIsNone(cards.row_group({"structure": "panel", "roots": '["SPY"]'}, {"spec": {}}, None))

    def test_each_group_of_a_cell_has_its_own_rebirth_budget(self):
        claim = {"different": "conditions entries on abnormal turnover confirming institutional accumulation, which the "
                              "refuted family never measured",
                 "evidence": "share_volume: turnover above its yearly median preceded the continuation on Train"}
        wider = {"inputs": ["share_volume", "underlying_price"]}
        dead = self.equity_grave("trend-xlk", self.trend(["XLK"]), mechanism="Hold XLK while it closes above its "
                                                                              "200-session average.")
        self.clock.t += 60
        reborn = self.trend(["QQQ"], **wider, rebirth={"row": self.index_rows["trend"], **claim})
        fam = self.store.add_family({"id": "trend-qqq-reborn", "mechanism": "Hold QQQ on rising turnover.",
                                     "structure": "etf", "roots": ["QQQ"], "symbols": ["QQQ"], "lane": "equity",
                                     "card_sha": cards.card_sha(reborn)}, origin="architect")
        cards.put(self.store, fam["id"], reborn, "etf")
        settings = self.with_e(dlane=GATE, architect={"max_rebirths_per_cell": 1})
        index = cards.RebirthIndex(self.store, settings)
        self.assertEqual(index.cell_births, {("trend_momentum", "equity:etf", "days_11_plus", "index"): 1})
        again = self.trend(["IWM"], **wider, rebirth={"row": self.index_rows["trend"], **claim})
        got = index.check(again, "etf", TREND[8], None, roots=["IWM"])
        self.assertFalse(got["ok"])
        self.assertIn("the cell trend_momentum / equity:etf / days_11_plus / index has had 1 rebirth(s)", got["reason"])
        sector = self.trend(["XLE"], **wider, rebirth={"row": dead, **claim})
        got = index.check(sector, "etf", TREND[8], None, roots=["XLE"])
        self.assertTrue(got["ok"] and got["rebirth"], got)
        index.note_birth(sector, "etf")
        self.assertEqual(index.cell_births[("trend_momentum", "equity:etf", "days_11_plus", "sectors")], 1)

    def test_a_claim_on_a_row_of_another_group_is_dropped(self):
        """The 03:43Z refusals told the architect to name the index row: a sector card that does so is born without the
        claim (`dropped`), so it spends none of the index row's or cell's rebirth budgets."""
        claim = {"different": "conditions entries on abnormal turnover confirming institutional accumulation, which the "
                              "refuted family never measured",
                 "evidence": "share_volume: turnover above its yearly median preceded the continuation on Train"}
        card = self.trend(["XLE"], inputs=["share_volume", "underlying_price"],
                          rebirth={"row": self.index_rows["trend"], **claim})
        got = self.verdict(["XLE"], card=card)
        self.assertEqual((got["ok"], got["matched"]), (True, []))
        self.assertIn(f"card.rebirth names {self.index_rows['trend']}, a row of the index group", got["dropped"])
        plain_card = {k: v for k, v in card.items() if k != "rebirth"}
        self.assertEqual(self.verdict(["XLE"], card=plain_card), {"ok": True, "matched": []})
        index_card = self.trend(["SPY"], inputs=["share_volume", "underlying_price"],
                                rebirth={"row": self.index_rows["trend"], **claim})
        got = self.verdict(["SPY"], card=index_card)
        self.assertTrue(got["ok"] and got["rebirth"] and "dropped" not in got, "its own group's claim is checked as before")


CLAIM = {"different": "conditions entries on abnormal turnover confirming institutional accumulation, which the refuted "
                      "family never measured",
         "evidence": "share_volume: turnover above its yearly median preceded the continuation on Train"}
WIDER = {"inputs": ["share_volume", "underlying_price"]}
CELL = ("trend_momentum", "equity:etf", "days_11_plus")


class TheRebirthBudget(GroupGraves):
    """A rebirth is charged to EVERY SINGLE GROUP ITS CARD TRADES (`budget_cells`), never to the claimed row's label: a
    card that names one extra symbol of another group reaches no other budget, and a mixed label is no budget of its own
    (the adversarial review of 92c6f5be: with the budget charged to the row's label, an XLE+SPY card claiming an index
    row, or an XLE card claiming a QQQ+XLV row, was born with the sectors budget spent; release U refused both)."""

    def trend(self, symbols, **over) -> dict:
        _, lane, cls, holding, inputs, *_ = TREND
        return self.valid(ecard(lane, cls, holding, over.pop("inputs", inputs), symbols, **over))

    def born_rebirth(self, fid, symbols, row) -> dict:
        """A rebirth of `row` on `symbols`, born a minute after the last (its card stored, as the architect stores it)."""
        self.clock.t += 60
        card = self.trend(symbols, **WIDER, rebirth={"row": row, **CLAIM})
        fam = self.store.add_family({"id": fid, "mechanism": "Hold on rising turnover.", "structure": "etf",
                                     "roots": list(symbols), "symbols": list(symbols), "lane": "equity",
                                     "card_sha": cards.card_sha(card)}, origin="architect")
        cards.put(self.store, fam["id"], card, "etf")
        return card

    def sector_row(self) -> str:
        return self.equity_grave("trend-xlk", self.trend(["XLK"]), mechanism="Hold XLK while it closes above its "
                                                                              "200-session average.")

    def index(self, per_cell=1):
        return cards.RebirthIndex(self.store, self.with_e(dlane=GATE, architect={"max_rebirths_per_cell": per_cell}))

    def check(self, index, symbols, row):
        return index.check(self.trend(symbols, **WIDER, rebirth={"row": row, **CLAIM}), "etf", TREND[8], None,
                           roots=symbols)

    def test_widening_a_card_reaches_no_other_groups_budget(self):
        dead = self.sector_row()
        self.born_rebirth("trend-xlv-reborn", ["XLV"], dead)  # the sectors budget (1) is spent
        index = self.index()
        self.assertEqual(index.cell_births, {(*CELL, "sectors"): 1})
        got = self.check(index, ["XLE"], dead)
        self.assertFalse(got["ok"])
        self.assertIn("the cell trend_momentum / equity:etf / days_11_plus / sectors has had 1 rebirth(s)", got["reason"])
        got = self.check(index, ["XLE", "SPY"], self.index_rows["trend"])
        self.assertFalse(got["ok"], "adding SPY moves no rebirth onto the index budget")
        self.assertEqual(got["matched"], [self.index_rows["trend"], dead])
        self.assertIn("the cell trend_momentum / equity:etf / days_11_plus / sectors has had 1 rebirth(s)", got["reason"])
        got = self.check(index, ["SPY"], self.index_rows["trend"])
        self.assertTrue(got["ok"] and got["rebirth"], "the index budget is the index cards' own, unspent")

    def test_a_mixed_row_is_no_second_budget(self):
        dead = self.sector_row()
        mixed = self.equity_grave("trend-mixed", self.trend(["QQQ", "XLV"]), mechanism="Hold QQQ and XLV while each "
                                                                                        "closes above its average.")
        self.born_rebirth("trend-xlv-reborn", ["XLV"], dead)
        index = self.index()
        got = self.check(index, ["XLE"], mixed)
        self.assertFalse(got["ok"], "a mixed row's label is no budget of its own")
        self.assertEqual(got["matched"], [dead, mixed])
        self.assertIn("the cell trend_momentum / equity:etf / days_11_plus / sectors has had 1 rebirth(s)", got["reason"])
        got = self.check(index, ["SPY"], mixed)
        self.assertTrue(got["ok"] and got["rebirth"], "an index card's claim on it spends the index budget")

    def test_a_mixed_rebirth_spends_every_group_it_trades(self):
        self.born_rebirth("trend-wide-reborn", ["XLE", "SPY"], self.index_rows["trend"])
        index = self.index(per_cell=3)
        self.assertEqual(index.cell_births, {(*CELL, "index"): 1, (*CELL, "sectors"): 1}, "counted in both at start")
        wide = self.trend(["XLK", "QQQ"], **WIDER, rebirth={"row": self.index_rows["trend"], **CLAIM})
        got = index.check(wide, "etf", TREND[8], None, roots=["XLK", "QQQ"])
        self.assertTrue(got["ok"] and got["rebirth"], got)
        index.note_birth(wide, "etf")
        self.assertEqual(index.cell_births, {(*CELL, "index"): 2, (*CELL, "sectors"): 2}, "and in both within a pass")
        self.assertNotIn((*CELL, "index+sectors"), index.cell_births)

    def test_a_card_without_a_group_is_charged_to_its_rows_groups(self):
        """FAIL CLOSED: a card whose symbols cannot be read (no group, bound by every row of its cell) spends the budget of
        every group the row it claims traded."""
        dead = self.sector_row()
        mixed = self.equity_grave("trend-mixed", self.trend(["QQQ", "XLV"]), mechanism="Hold QQQ and XLV while each "
                                                                                        "closes above its average.")
        self.born_rebirth("trend-xlv-reborn", ["XLV"], dead)
        with mock.patch.object(cards, "universe_group", lambda *a, **k: None):
            index = self.index()
            self.assertEqual(index.cell_births, {(*CELL, "sectors"): 1}, "the claimed row's group")
            got = self.check(index, ["XLE"], mixed)
            self.assertFalse(got["ok"])
            self.assertIn("days_11_plus / sectors has had 1 rebirth(s)", got["reason"])
        self.assertEqual(cards.budget_cells({**cards.key_of(self.trend(["XLK"]), "etf"), "group": "index+sectors"}),
                         [(*CELL, "index"), (*CELL, "sectors")])
        self.assertEqual(cards.budget_cells({**cards.key_of(self.trend(["XLK"]), "etf"), "group": "index+sectors"},
                                            "defensive"), [(*CELL, "defensive")], "the card's groups, not the row's")
        self.assertEqual(cards.budget_cells(cards.key_of(self.trend(["XLK"]), "etf")), [CELL], "no group at all")


class TheReaders(unittest.TestCase):
    """No judge reads the graveyard's key: FWD1-R's one-seat-a-mechanism-cell rule, the screens, the Train bar and the
    sealed data read their own cells, unchanged."""

    def test_fwd1rs_mechanism_cell_is_the_train_maps(self):
        from league.ops import forward_screen

        fam = {"spec": {"lane": "equity", "agenda": "trend"}}
        for symbols, group in ((["SPY"], "index"), (["XLK", "XLE"], "sectors"), (["SPY", "TLT"], "index+defensive")):
            self.assertEqual(forward_screen.cell_of("ETF", {"needs": {"symbols": symbols}, "lane": "equity"}, fam),
                             f"equity / trend / {group}")

    def test_no_judge_names_the_graveyards_group(self):
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        names = ("graveyard_key", "universe_group", "groups_meet", "budget_cells", "row_group", "cards.symbols_group")
        for rel in ("league/swarm/elane_forward.py", "league/ops/forward_screen.py", "league/ops/forward_register.py",
                    "league/swarm/elane_train.py", "league/swarm/elane_seal.py", "league/swarm/elane.py",
                    "league/swarm/mechanism.py", "league/swarm/researcher.py", "league/swarm/tournament.py"):
            text = (repo / rel).read_text()
            self.assertFalse([n for n in names if n in text], rel)


class TheBirthsPass(unittest.TestCase):
    """The equity births pass (league/swarm/elane_births.py `EquityPass.admit`) over the six index rows E2 refuted: the
    six sector proposals are born, an index proposal of the same idea is refused by its row."""

    def setUp(self):
        from league.swarm.architect import Architect
        from league.tests import elane_e2_fakes as fx

        self.fx = fx
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(max_per_pass=8)
        self.answers: list = []
        self.router = fx.FakeRouter(lambda call: self.answers.pop(0) if self.answers else fx.answer([]))
        self.arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        for i in range(60):
            self.store.event("swarm.born", f"opt-{i}", {"structure": "debit_vertical", "roots": ["SPY"]})

    def refuted(self, fid, lane, cls, holding, inputs, agenda, symbols, mechanism) -> str:
        fx = self.fx
        fam = fx.e2_family(self.store, fid, lane=lane, agenda=agenda, symbols=tuple(symbols), mechanism=mechanism,
                           record={"status": "refuted", "versions": {"1": {"fails": ["Y2"]}},
                                   "refuted": {"at": "2026-10-10T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        cards.put(self.store, fam["id"], fx.card(lane, tuple(symbols), mechanism_class=cls, holding=holding,
                                                 inputs=list(inputs)), "etf")
        self.store.bury(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        self.store.retire(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        self.clock.advance(60)
        return fam["id"]

    def test_the_six_sector_proposals_are_born_and_an_index_one_is_refused(self):
        from league.swarm.elane_births import LAST_KEY

        fx = self.fx
        slices = (("XLE", "XLF", "XLK"), ("XLE", "XLF"), ("XLF",), ("XLE",), ("XLK",), ("XLF", "XLK"))
        rows = []
        for (slug, lane, cls, holding, inputs, agenda, dead_text, dead_symbols, text, _), symbols in zip(SIX, slices):
            self.refuted(f"{slug}-index", lane, cls, holding, inputs, agenda, dead_symbols, dead_text)
            rows.append(fx.proposal(f"{slug}-sectors", lane=lane, agenda=agenda, symbols=symbols, mechanism=text,
                                    code=fx.program(symbols[0]),
                                    card=fx.card(lane, symbols, mechanism_class=cls, holding=holding, inputs=list(inputs))))
        _, lane, cls, holding, inputs, agenda, dead_text, *_ = SIX[0]
        rows.append(fx.proposal("trend-spy-again", lane=lane, agenda=agenda, symbols=("SPY",), code=fx.program("SPY"),
                                mechanism="Index trend again: hold SPY while it closes above a slower average.",
                                card=fx.card(lane, ("SPY",), mechanism_class=cls, holding=holding, inputs=list(inputs))))
        self.answers.append(fx.answer(rows))
        out = self.arch.equity_pass()
        self.assertEqual(out["born"], [f"{s[0]}-sectors" for s in SIX], self.store.get(LAST_KEY))
        refused = self.store.get(LAST_KEY)["refused"]
        self.assertEqual([(r["n"], r["cls"]) for r in refused], [(7, "graveyard")])
        self.assertTrue(refused[0]["why"].startswith("graveyard: its cell (trend_momentum / equity:etf / days_11_plus / "
                                                     "underlying_price / universe group index)"), refused[0]["why"])
        self.assertIn("trend-index", refused[0]["why"])

    def test_a_sector_birth_naming_an_index_row_is_born_without_the_claim(self):
        fx = self.fx
        _, lane, cls, holding, inputs, agenda, dead_text, dead_symbols, text, _ = SIX[0]
        dead = self.refuted("trend-index", lane, cls, holding, inputs, agenda, dead_symbols, dead_text)
        claim = {"row": dead, "different": "conditions entries on abnormal turnover confirming institutional "
                                           "accumulation, which the refuted family never measured",
                 "evidence": "share_volume: turnover above its yearly median preceded the continuation on Train"}
        card = fx.card(lane, ("XLK",), mechanism_class=cls, holding=holding, inputs=["share_volume", "underlying_price"],
                       rebirth=claim)
        self.answers.append(fx.answer([fx.proposal("trend-xlk", lane=lane, agenda=agenda, symbols=("XLK",),
                                                   mechanism=text, code=fx.program("XLK"), card=card)]))
        self.assertEqual(self.arch.equity_pass()["born"], ["trend-xlk"])
        self.assertNotIn("rebirth", cards.card_of(self.store, "trend-xlk")["card"])
        self.assertNotEqual(self.store.family("trend-xlk")["parent"], dead, "no lineage is continued through it")
        self.assertEqual(cards.RebirthIndex(self.store, self.settings).backed, {}, "no budget is spent")


if __name__ == "__main__":
    unittest.main()
