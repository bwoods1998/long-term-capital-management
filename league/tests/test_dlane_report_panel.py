"""THE PANEL LANE IN THE REPORT (release E4, package H's patch 13 to league/ops/dlane_report.py): a panel close under its
own label with its distinct close dates and date-clustered t (the captain's A14; E4-SPEC 10.5), XS1's sentence beside
EVERY live panel trade (the pre-registration's duty 3), and every recorded style-open passer with why it holds no seat
(the captain's A22).

Skipped whole while the patch is not applied (`dlane_report.panel_section` absent: league/swarm/e4_patches/H.md).
Package G's lane (`league.swarm.elane_xs`: the sentence its look recorded, the style verdict of its Train record) and
package E's rule (`league.xs.style.seat_refusal`) are stubbed at their interface. Every figure is invented."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal as D
from unittest import mock

from league.ops import dlane_report as R
from league.tests.test_dlane_report import ny
from league.tests.test_dlane_report_equity import EquityFixture
from league.tests.test_equity_twins import lot, put_lot
from league.xs import book

APPLIED = hasattr(R, "panel_section")
FAMILY, KEY = "xs-reversal", "xs-reversal@1:r"
SENTENCE = "XS1 (panel screen): judged on the daily residual ... Bar: holdout t >= 1.42 (an invented line)"


@unittest.skipUnless(APPLIED, "package H's patch 13 is not applied to league/ops/dlane_report.py (e4_patches/H.md)")
class PanelFixture(EquityFixture):
    def setUp(self):
        super().setUp()
        self.live.db.execute(book.INSTANCE_KIND_DDL)
        self.live.db.executescript(book.SCHEMA)

    def panel_family(self, fid: str = FAMILY, *, band: str = "probe", **state) -> None:
        # (Package G's patch 1 admits structure "panel" in `add_family`; until then the fixture writes the column.)
        spec = {"id": fid, "mechanism": "a published cross-sectional prior long enough for the store",
                "structure": "stock", "roots": ["AAPL"], "lane": "equity"}
        self.store.add_family(spec, origin="architect")
        self.store._db.execute("UPDATE families SET structure='panel' WHERE id=?", (fid,))
        if band != "gym":
            self.store.set_band(fid, band, reason="fixture")
        if state:
            self.store.set_state(fid, **state)

    def instance(self, key: str = KEY, kind: str = "panel") -> None:
        family = key.split("@", 1)[0]
        self.live.upsert("eq_instances", {"id": key, "family": family, "version": 1, "lane": "equity", "run_sha": "r",
                                          "code": "c", "params": "{}", "band": "probe", "max_hold": 30,
                                          "created_at": 1.0, "kind": kind}, "id")

    def panel_lot(self, symbol: str, *, exit_day: str | None = "2026-10-13", opened: str = "2026-10-12",
                  cash: str = "1.00", notional: str = "100.00", family: str = FAMILY, tag: str = "xs") -> int:
        self.lid += 1
        row = lot(self.lid, family=family, lane="equity", symbol=symbol, klass="stock", notional=notional, cash=cash,
                  opened_day=opened, exit_day=exit_day or "", status="closed" if exit_day else "open")
        row.update(tag=tag, exit_day=exit_day)
        put_lot(self.live, row)
        return self.lid

    def decision(self, day: str, *, status: str = "planned", audit: str | None = None, called: bool = True) -> None:
        row = book.rebalance_row(instance=KEY, family=FAMILY, version=1, decided_day=day, exec_day=day, at="open",
                                 called=called, targets=[["N001", 0.2]], standing=False, intents=[], skipped=[],
                                 equity="557.25", budget="557.25", cols=None, ctx_sha="c", bars_sha="b", fetch={},
                                 status=status, why=None, now=1.0)
        self.live.upsert("eq_rebalances", {**row, "audit": audit}, "instance, decided_day")

    def golden(self) -> None:
        """Six lots closed on two dates, and one still open."""
        for symbol, day, cash, notional in (("N001", "2026-10-13", "2", "100"), ("N002", "2026-10-13", "-1", "100"),
                                            ("N003", "2026-10-13", "4", "200")):
            self.panel_lot(symbol, exit_day=day, cash=cash, notional=notional, opened="2026-10-12")
        for symbol, cash, notional in (("N004", "-3", "150"), ("N005", "-3", "150"), ("N006", "1", "100")):
            self.panel_lot(symbol, exit_day="2026-10-20", cash=cash, notional=notional, opened="2026-10-13")
        self.panel_lot("N007", exit_day=None, opened="2026-10-19")


class NoPanelNoLines(PanelFixture):
    def test_a_book_without_a_panel_program_has_no_panel_block(self):
        self.eq_family("seed-overnight-spy")
        self.eq_close("seed-overnight-spy", cash="1.25")
        out = self.report()
        self.assertIsNone(out["equity"]["panel"])
        self.assertEqual({c["label"] for c in out["equity"]["closes"]}, {"MARKET BETA"})
        self.assertFalse(any(c.get("panel") for c in out["equity"]["closes"]))
        row = out["fp_beside_trades"]["equity_trades"][0]
        self.assertEqual(row["label"], "MARKET BETA")
        self.assertNotIn("panel", row)

    def test_a_book_from_before_the_panel_lane_reads_as_none(self):
        self.live.db.execute("DROP TABLE eq_rebalances")
        self.live.db.execute("ALTER TABLE eq_instances DROP COLUMN kind")
        self.live.upsert("eq_instances", {"id": "seed@1:r", "family": "seed", "version": 1, "lane": "beta", "run_sha": "r",
                                          "code": "c", "params": "{}", "band": "probe", "max_hold": 20, "created_at": 1.0},
                         "id")
        read = R.read_book(self.root / "live.sqlite")
        self.assertEqual((read["rebalances"], read["spy"]), ([], []))
        self.assertNotIn("kind", read["eq_instances"][0])
        self.assertIsNone(self.report()["equity"]["panel"])
        self.assertEqual(R.read_book(self.root / "absent.sqlite")["rebalances"], [])

    def test_the_words_are_the_adapters(self):
        self.assertEqual((R.PANEL_TAG, R.PANEL_KIND, R.PANEL_LABEL), (book.TAG, book.KIND, book.LABEL))
        self.assertIn("NOT shadowed", R.PANEL_OWED)
        self.assertIn("no live seat on an XS1 pass alone", R.STYLE_OPEN_RULE)


class APanelClose(PanelFixture):
    def setUp(self):
        super().setUp()
        self.panel_family()
        self.instance()
        self.golden()

    def program(self, out=None) -> dict:
        return (out or self.report())["equity"]["panel"]["programs"][KEY]

    def test_its_label_its_close_dates_and_the_date_clustered_t(self):
        out = self.report()
        closes = [c for c in out["equity"]["closes"] if c["family"] == FAMILY]
        self.assertEqual(len(closes), 6)
        self.assertEqual({c["label"] for c in closes}, {"EQUITY (PANEL)"})
        program = self.program(out)
        self.assertEqual((program["label"], program["family"], program["version"]), ("EQUITY (PANEL)", FAMILY, 1))
        self.assertEqual((program["open_lots"], program["closed_lots"], program["close_dates"]), (1, 6, 2),
                         "six closes on two dates are two observations")
        self.assertEqual(program["date_t"], round(book.date_t([0.0125, -0.0125]), 4))
        self.assertEqual(program["pnl_usd"], 0.0)
        self.assertEqual(out["equity"]["panel"]["label"], "EQUITY (PANEL)")
        self.assertEqual(out["equity"]["panel"]["rule"], R.PANEL_BY_DATE)

    def test_the_cost_of_reading_by_date_is_said(self):
        program = self.program()
        self.assertIn("10th close date", program["cost"])
        self.assertIn("-$300", program["cost"])
        self.assertIn("a backstop, not a tight leash", program["cost"])

    def test_what_the_forward_record_owes_is_said_not_invented(self):
        program = self.program()
        self.assertIsNone(program["residual_x"])
        self.assertIsNone(program["rebalance_sessions_agreed"])
        self.assertEqual(program["owed"], R.PANEL_OWED)

    def test_the_buy_and_hold_is_spy_on_one_basis_or_none(self):
        self.assertIsNone(self.program()["bh_spy_usd"])
        self.assertIn("no single SPY series", self.program()["bh_why"])
        closes = {"2026-10-09": "498.51", "2026-10-12": "501.50", "2026-10-13": "505.00", "2026-10-20": "510.05"}
        for day, c in closes.items():
            self.live.upsert("eq_bars", {"day": day, "symbol": "SPY", "adjustment": "all", "o": c, "h": c, "l": c, "c": c,
                                         "v": "1", "fetched_at": 1.0, "sha": "one", "audit": None},
                             "day, symbol, adjustment")
        by_hand = D("400") * (D("505.00") / D("498.51") - 1) + D("400") * (D("510.05") / D("501.50") - 1)
        self.assertEqual(self.program()["bh_spy_usd"], round(float(by_hand), 2))
        self.live.db.execute("UPDATE eq_bars SET sha='older' WHERE day='2026-10-09'")
        self.assertIsNone(self.program()["bh_spy_usd"], "two fetches straddling an ex-date are not one series")

    def test_its_decisions_and_their_morning_re_reads_are_counted(self):
        self.decision("2026-10-09", audit="ok")
        self.decision("2026-10-12", status="hold", audit="mismatch", called=False)
        self.decision("2026-10-13", status="hold", called=False)                 # recorded after 08:30: no re-read
        self.decision("2026-10-14", status="failed", called=False)
        self.decision("2026-10-15", status="late")
        program = self.program()
        self.assertEqual(program["decisions"], {"failed": 1, "hold": 2, "late": 1, "planned": 1})
        self.assertEqual(program["audits"], {"mismatch": 1, "none": 2, "ok": 1})
        read = R.read_book(self.root / "live.sqlite")
        self.assertNotIn("targets", read["rebalances"][0], "counts and verdicts only: never a target or a symbol of one")

    def test_a_lot_is_a_panel_lot_by_its_tag_or_by_its_instances_kind(self):
        self.panel_family("xs-other")
        self.instance("xs-other@1:r")
        self.panel_lot("N020", family="xs-other", tag="")
        programs = self.report()["equity"]["panel"]["programs"]
        self.assertEqual(programs["xs-other@1:r"]["closed_lots"], 1)
        self.assertEqual(sorted(programs), ["xs-other@1:r", KEY])


class XS1BesideEveryLivePanelTrade(PanelFixture):
    def setUp(self):
        super().setUp()
        self.panel_family()
        self.instance()
        self.golden()

    def test_the_sentence_its_look_recorded_rides_beside_every_trade(self):
        from league.swarm import elane_xs

        with mock.patch.object(elane_xs, "beside_line", lambda fam: SENTENCE if fam["id"] == FAMILY else None):
            out = self.report()
        trades = [t for t in out["fp_beside_trades"]["equity_trades"] if t["family"] == FAMILY]
        self.assertEqual(len(trades), 7, "the open lot too: EVERY live panel trade")
        for row in trades + [c for c in out["fp_beside_trades"]["closes"] if c["family"] == FAMILY]:
            self.assertEqual((row["screen"], row["beside"], row["label"]), ("XS1", SENTENCE, "EQUITY (PANEL)"))
            self.assertNotIn("fp_why", row)
        self.assertEqual({c["fp"]["beside"] for c in out["equity"]["closes"] if c["family"] == FAMILY}, {SENTENCE})
        self.assertEqual(out["equity"]["panel"]["programs"][KEY]["xs1"]["beside"], SENTENCE)

    def test_the_looks_own_row_is_read_first(self):
        self.store.add_look(FAMILY, 1, "sha-xs", passed=True, p_value=None,
                            detail={"screen": "XS1", "beside": SENTENCE, "receipt": "r" * 64, "c_used": 1.42})
        row = R.EquityScreens(self.store).of(FAMILY, 1)
        self.assertEqual((row["screen"], row["beside"], row["receipt"], row["c_used"], row["lane_label"]),
                         ("XS1", SENTENCE, "r" * 64, 1.42, "EQUITY (PANEL)"))

    def test_no_sentence_is_said_plainly_and_never_a_crash(self):
        """Package G's lane not landed (its stub raises), or a program that took no look: none is stated."""
        out = self.report()
        rows = [t for t in out["fp_beside_trades"]["equity_trades"] if t["family"] == FAMILY]
        self.assertEqual({r["beside"] for r in rows}, {None})
        self.assertEqual({r["screen"] for r in rows}, {"XS1"})
        self.assertTrue(all("no XS1 sentence is recorded" in r["fp_why"] for r in rows))

    def test_an_etf_programs_line_is_untouched(self):
        self.eq_family("p-s2")
        row = R.EquityScreens(self.store).of("p-s2", 1)
        self.assertNotIn("panel", row)
        self.assertIn("no screen line is recorded at this version's look (league/swarm/elane.py", row["fp_why"])


class TheStyleOpenPassers(PanelFixture):
    """The captain's A22 (1)."""

    def setUp(self):
        super().setUp()
        self.panel_family("xs-momentum", band="gym",
                          elane_xs_look={"version": 2, "passed": True, "seat": "style-open", "at": "2026-11-02T21:40:00Z"})
        self.panel_family("xs-seated", band="candidate",
                          elane_xs_look={"version": 1, "passed": True, "seat": "candidate"})
        self.panel_family("xs-failed", band="gym", elane_xs_look={"version": 1, "passed": False, "seat": None})
        self.panel_family("xs-fresh", band="gym")

    def test_every_recorded_passer_is_named_with_why_it_holds_no_seat(self):
        from league.swarm import elane_xs
        from league.xs import style

        asked = []

        def style_of(fam, version=None):
            asked.append((fam["id"], version))
            return {"open": True, "tilts": [["mom", 1]]}

        with mock.patch.object(elane_xs, "style_of", style_of), \
                mock.patch.object(style, "seat_refusal", lambda verdict: "style-open: mom +"):
            panel = self.report()["equity"]["panel"]
        self.assertEqual(panel["style_open"], [{"family": "xs-momentum", "version": 2, "passed": True, "seat": None,
                                                "why": "style-open: mom +", "look_at": "2026-11-02T21:40:00Z",
                                                "shadow": R.PANEL_OWED}])
        self.assertEqual(asked, [("xs-momentum", 2)])
        self.assertEqual(panel["style_open_rule"], R.STYLE_OPEN_RULE)
        self.assertEqual(panel["programs"], {}, "it holds no seat: it has no instance and no lot")

    def test_a_rule_that_cannot_be_read_here_leaves_the_looks_own_word(self):
        from league.swarm import elane_xs

        def unreadable(fam, version=None):
            raise RuntimeError("the Train record's style verdict cannot be read here")

        # The rule is made unreadable HERE (with packages E and G in the tree it reads: a family with no style verdict
        # is "style-open: unmeasured", the next test).
        with mock.patch.object(elane_xs, "style_of", unreadable):
            passers = R.style_open_passers(self.store)
            self.assertEqual([(p["family"], p["why"]) for p in passers], [("xs-momentum", "style-open")])
            self.store.set_state("xs-momentum", elane_xs_look={"1": {"passed": True, "seat": "style-open",
                                                                     "why": "style-open: its own word"},
                                                               "2": {"passed": False}})
            self.assertEqual([(p["version"], p["why"]) for p in R.style_open_passers(self.store)],
                             [(1, "style-open: its own word")], "a record kept by version reads the same")

    def test_a_passer_with_no_style_verdict_is_read_by_the_rule_as_unmeasured(self):
        """The built lane and rule (`elane_xs.style_of`, `league.xs.style.seat_refusal`): a passer whose Train record
        carries no style verdict is style-open because it is UNMEASURED, and the report says so."""
        passers = R.style_open_passers(self.store)
        self.assertEqual([(p["family"], p["why"]) for p in passers], [("xs-momentum", "style-open: unmeasured")])

    def test_an_unreadable_store_is_no_passer(self):
        class Broken:
            def families(self, **kw):
                raise RuntimeError("locked")

        self.assertEqual(R.style_open_passers(Broken()), [])
        self.assertEqual(R._look_records("junk"), [])
        self.assertEqual(json.dumps(R.style_open_passers(self.store))[:1], "[")


if __name__ == "__main__":
    unittest.main()
