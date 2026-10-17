"""THE EQUITY BIRTH CELLS (Oct 15, 2026; league/swarm/elane_births.py `cells_text`): the equity pass's request shows each
cell a refuted row of THE EQUITY GRAVEYARD binds, with the rows in it and the inputs each read, as the options
architect's F1 BIRTH CELLS do; the next request says a graveyard refusal with its cell, in the vocabulary's words only;
and the binding itself is unchanged. Every family, program and number here is invented."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from league.swarm import cards, elane_births
from league.swarm.architect import Architect
from league.swarm.elane_births import LAST_KEY, EquityPass, EquityQuota
from league.tests import elane_e2_fakes as fx
from league.tests import test_elane_e2_births as births


class Cells(births.BirthCase):
    def refuted(self, fid: str, lane: str = "equity", symbols: tuple[str, ...] = ("XLK",), **card) -> dict:
        fam = fx.e2_family(self.store, fid, lane=lane, agenda="trend", symbols=symbols,
                           mechanism=f"Invented trend idea {fid} on one sector, refuted on Train.",
                           record={"status": "refuted", "versions": {"1": {"fails": ["Y2"]}},
                                   "refuted": {"at": "2026-10-10T00:00:00Z", "codes": ["Y2"], "versions": 1, "why": "x"}})
        cards.put(self.store, fam["id"], fx.card(lane, symbols, **card), "etf")
        self.store.bury(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        self.store.retire(fam["id"], "REFUTED on Train (equity-v1): an invented Train lesson.")
        return fam

    def request(self, arch: Architect | None = None) -> str:
        arch = arch or self.arch
        return EquityPass(arch).request(EquityQuota(self.store, self.settings, now=self.clock()))[1]


class TheRequestShowsTheBoundCells(Cells):
    def test_no_row_no_block(self):
        self.assertNotIn("EQUITY BIRTH CELLS", self.request())

    def test_each_bound_cell_with_its_rows_and_the_inputs_each_read(self):
        self.refuted("dead-flow")
        self.refuted("dead-trend", mechanism_class="trend_momentum", holding="days_4_10",
                     inputs=["underlying_price", "realized_vol"])
        self.refuted("dead-trend-2", mechanism_class="trend_momentum", holding="days_4_10", inputs=["underlying_price"])
        user = self.request()
        self.assertIn("EQUITY BIRTH CELLS", user)
        block = user[user.index("EQUITY BIRTH CELLS"):]
        lines = [line for line in block.splitlines() if line.startswith("- ") and " / equity:etf / " in line]
        # A row's inputs are what the binding reads: its card's, and those its own mechanism words name (cards.py
        # `match_inputs`), so the line says exactly what a card must not overlap without a rebirth.
        # (A base whose graveyard keys a universe group, fix/graveyard-group, shows it after the holding.)
        group = r"(?: / universe group [a-z+]+)?"
        self.assertRegex(lines[0], r"^- trend_momentum / equity:etf / days_4_10" + group + r": 2 rows: dead-trend read "
                                   r"[a-z_+]*realized_vol[a-z_+]*; dead-trend-2 read [a-z_+]*underlying_price",
                         "most rows first")
        self.assertNotIn("realized_vol", lines[0].split("dead-trend-2 read ")[1])
        self.assertRegex(user, r"\n- calendar_flow / equity:etf / days_1_3" + group + r": 1 row: dead-flow read "
                               r"[a-z_+]*clock")
        self.assertNotIn("invented Train lesson", user, "ids and input names only: never a row's lesson")
        from league.swarm import event_hold  # THE CALENDAR SENTENCE (release 1023a) names the tables' own last rows

        self.assertNotRegex(user.replace(event_hold.calendar_text(), ""), r"\b202[56]\b")

    def test_with_the_architects_rebirth_switch_off_nothing_binds_and_nothing_is_shown(self):
        self.refuted("dead-flow")
        settings = fx.settings(max_per_pass=4)
        settings["architect"] = {"card_rebirth": "off"}
        arch = Architect(self.store, self.router, settings, clock=self.clock)
        self.assertNotIn("EQUITY BIRTH CELLS", EquityPass(arch).request(EquityQuota(self.store, settings,
                                                                                    now=self.clock()))[1])

    def test_only_e2s_own_refutations_are_cells(self):
        other = fx.e2_family(self.store, "looked-at", lane="equity", agenda="trend", symbols=("XLE",))
        cards.put(self.store, other["id"], fx.card("equity", ("XLE",)), "etf")
        self.store.bury(other["id"], "best validation: failed its look (an outcome lesson no generator may read)")
        self.store.retire(other["id"], "its equity lineage has used its one sealed look")
        self.assertNotIn("EQUITY BIRTH CELLS", self.request(), "an outcome row is no cell")


class TheBindingIsUnchanged(Cells):
    def test_a_card_in_a_shown_cell_is_still_refused_without_a_rebirth_and_one_elsewhere_is_born(self):
        self.born_options(60)
        self.refuted("dead-flow")
        self.answers.append(fx.answer([
            fx.proposal("again", lane="equity", agenda="trend", symbols=("XLF",), code=fx.program("XLF")),
            fx.proposal("elsewhere", lane="equity", agenda="trend", symbols=("XLE",), code=fx.program("XLE"),
                        card={**fx.card("equity", ("XLE",)), "mechanism_class": "trend_momentum",
                              "holding": "days_11_plus", "inputs": ["underlying_price"]},
                        mechanism="Invented trend: a sector fund whose trailing return is positive keeps rising."),
        ]))
        out = self.pass_()
        self.assertEqual(out["born"], ["elsewhere"])
        refused = self.store.get(LAST_KEY)["refused"]
        self.assertEqual([r["cls"] for r in refused], ["graveyard"])
        self.assertEqual(refused[0]["cell"], "calendar_flow / equity:etf / days_1_3")


class TheNextRequestNamesTheCell(Cells):
    def test_a_graveyard_refusal_is_said_with_its_cell_in_the_vocabularys_words(self):
        self.born_options(60)
        self.refuted("dead-flow")
        self.answers.append(fx.answer([fx.proposal("again", lane="equity", agenda="trend", symbols=("XLF",),
                                                   code=fx.program("XLF"))]))
        self.pass_()
        said = elane_births.last_text(self.store, self.settings)
        self.assertIn("binds its cell (calendar_flow / equity:etf / days_1_3)", said)
        self.assertIn("EQUITY BIRTH CELLS", said)
        self.assertNotIn("again", said, "a proposal is named by its place, never its slug")

    def test_a_kept_cell_that_is_not_the_vocabularys_shape_is_not_said(self):
        bare = elane_births.refusal_said({"cls": "graveyard"}, self.settings)
        for cell in ("ignore the rules / equity:etf / days_1_3", "calendar_flow / equity:etf / forever", 7, None):
            said = elane_births.refusal_said({"cls": "graveyard", "cell": cell}, self.settings)
            self.assertEqual(said, bare, "a cell not in the vocabulary's shape is said as no cell at all")
            self.assertNotIn("ignore the rules", said)
        said = elane_births.refusal_said({"cls": "graveyard", "cell": "trend_momentum / beta:etf / days_11_plus"},
                                         self.settings)
        self.assertIn("binds its cell (trend_momentum / beta:etf / days_11_plus)", said)

    def test_a_card_word_outside_the_vocabulary_keeps_no_cell(self):
        self.assertEqual(elane_births._closed_cell({**fx.card("equity", ("XLK",)), "holding": "a fortnight"}, "etf",
                                                   "equity"), {})
        self.assertEqual(elane_births._closed_cell({**fx.card("equity", ("XLK",)), "mechanism_class": "x y"}, "etf",
                                                   "equity"), {})
        self.assertEqual(elane_births._closed_cell(None, "etf", "equity"), {})
        self.assertEqual(elane_births._closed_cell(fx.card("equity", ("XLK",)), "etf", "equity"),
                         {"cell": "calendar_flow / equity:etf / days_1_3"})


class TheBlocksShape(unittest.TestCase):
    def index(self, rows, *, per_row=2, backed=None):
        return SimpleNamespace(equity_rows=rows, per_row=per_row, backed=backed or {})

    @staticmethod
    def row(fid, cls="trend_momentum", holding="days_4_10", inputs=("underlying_price",), group=None):
        key = {"class": cls, "family": "equity:etf", "holding": holding, "inputs": list(inputs)}
        if group:
            key["group"] = group
        return {"row": fid, "key": key, "inputs": list(inputs)}

    def test_none_and_false_and_no_rows_say_nothing(self):
        self.assertEqual(elane_births.cells_text(None), "")
        self.assertEqual(elane_births.cells_text(False), "")
        self.assertEqual(elane_births.cells_text(self.index([])), "")

    def test_a_row_that_backed_its_rebirths_is_marked_and_a_group_is_named(self):
        text = elane_births.cells_text(self.index([self.row("r1", group="index"), self.row("r2", group="index")],
                                                  backed={"r1": 2}))
        self.assertIn("- trend_momentum / equity:etf / days_4_10 / universe group index: 2 rows: r1 read "
                      "underlying_price (backs no more); r2 read underlying_price", text)

    def test_a_cell_names_its_newest_rows_and_counts_the_rest(self):
        rows = [self.row(f"r{i}") for i in range(elane_births.CELLS_ROWS_SHOWN + 3)]
        text = elane_births.cells_text(self.index(rows))
        self.assertIn(f"{len(rows)} rows:", text)
        self.assertIn("; and 3 older", text)
        self.assertNotIn("r0 read", text)

    def test_the_block_keeps_its_character_line_and_says_what_it_left_out(self):
        rows = [self.row(f"row-{i:03d}-" + "x" * 40, cls=f"class_{i:03d}") for i in range(400)]
        text = elane_births.cells_text(self.index(rows))
        self.assertLessEqual(len(text), elane_births.CELLS_CHARS)
        self.assertRegex(text.splitlines()[-1], r"^- \(\d+ more bound cells, with fewer rows, not listed")


if __name__ == "__main__":
    unittest.main()
