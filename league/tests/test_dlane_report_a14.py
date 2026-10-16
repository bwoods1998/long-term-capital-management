"""THE DONE METER'S A14 AND THE FORWARD RECORD IN THE DLANE REPORT (release E3; the spec's 11.5, J6 as A14
pre-registered it): a Done checkpoint that holds an equity close also needs A14 over its counted closes (the size of
the mean fill gap within 15 bp a side AND the intents agreeing on 95% of the counted sessions, as
league/ops/forward_twins.py `a14_reading` reads them). A checkpoint that held without it can only stop holding, none
can start; one with no equity close is read as before; a frozen final reading is carried as it was; unmeasured,
unreadable or misshapen, A14 does not hold, the reading is not final, and `meter` and `report` are whole. The report
carries the forward record's section and its alarms, and never fails for them.

`a14_reading` is package D's: A FAKE HERE (`A14Fixture.fake`, a scripted answer in the shape its contract states), as
are the forward report's `read_section` and `alarms` where a test scripts them. The dlane report read here is
`integrated("dlane_report")` (league/tests/test_forward_patches.py): the module with package C's edits, applied by the
integrator or, until then, on a copy of its source. Every close, twin and count is invented.

ON BOTH BASES (test_forward_patches.py, TWO BASES). On a tree whose `dlane_report` carries E1's own reader
(`a14_consistency`), a checkpoint's `a14` is the forward record's reading with the fill-gap half of the counted rows
beside it, so these tests read the forward record's own keys of it (`own`) and hold either way."""

from __future__ import annotations

import importlib
import json
import unittest
from pathlib import Path
from unittest import mock

from league.ops import forward_db, forward_report, forward_twins
from league.ops import schedule as S
from league.ops.context import write_json
from league.swarm import dlane
from league.tests.test_dlane_report import GATE, NIGHTLY, Fixture, ny
from league.tests.test_dlane_report_equity import EquityFixture
from league.tests.test_forward_patches import integrated

R = integrated("dlane_report")
RECORD = {**GATE, "elane": {"forward": {"mode": "record"}}}


def a14(holds: bool = True, final: bool = True, why: str | None = None) -> dict:
    """An `a14_reading` answer in its contract's shape (`forward_twins.A14_KEYS`), every count invented."""
    return {"applies": True, "holds": holds, "final": final, "why": why,
            "gap": {"closes": 30, "priced": 30, "unpriced": 0, "pending": 0, "mean_gap_bp": -5.0 if holds else -16.0,
                    "bound_bp": 15.0, "ok": holds},
            "intents": {"instances": 2, "sessions": 20, "agreed": 20, "missing": 0, "unreadable": 0, "share": 1.0,
                        "bound": 0.95, "ok": True, "disagreed": 0, "causes": {}},
            "by_instance": [{"instance": "p-a@1:r", "sessions": 10, "agreed": 10, "missing": 0, "unreadable": 0}]}


def own(reading: dict, like: dict) -> dict:
    """The keys of `like` as a checkpoint's `a14` carries them (ON BOTH BASES, the module docstring)."""
    return {key: reading.get(key, "absent") for key in like}


class A14Fixture(EquityFixture):
    """Thirty equity closes of two programs that hold the pinned rule and are final, and a scripted `a14_reading`."""

    def setUp(self):
        super().setUp()
        self.answer: object = a14()
        self.asked: list[tuple[Path, list]] = []
        patcher = mock.patch.object(forward_twins, "a14_reading", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake(self, root, counted):
        self.asked.append((Path(root), [c["pid"] for c in counted]))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def thirty(self) -> None:
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        lids = [self.eq_close("p-a" if i % 2 == 0 else "p-b", cash="2.00", lane="beta" if i % 2 == 0 else "equity",
                              posted=True, closed_at=ny("2026-10-14", 15, 56) + i) for i in range(30)]
        for lid in lids:
            self.twin(lid, live_r=0.02, twin_r=0.021, bh=1.5)
        self.steady()

    def report(self, settings=GATE, previous=None) -> dict:
        return R.report(self.root, settings=settings, now=self.now, previous=previous)

    def latest(self, **kw) -> dict:
        return self.report(**kw)["done"]["all"]["latest"]


class TheCheckpointNeedsA14(A14Fixture):
    def test_a_checkpoint_that_holds_with_a14_carries_it(self):
        self.thirty()
        out = self.report()
        cp = out["done"]["all"]["latest"]
        self.assertEqual((cp["at_close"], cp["holds"], cp["final"], cp["why"], cp["final_why"]), (30, True, True, None, None))
        self.assertEqual((cp["items"], cp["consistent_ok"]), ({"3": True, "4": True, "7": True}, True))
        self.assertEqual(own(cp["a14"], a14()), a14())
        self.assertTrue(out["done"]["all"]["holds"])
        # It is read over exactly each checkpoint's counted closes, from the state root: since the owner's change (A50,
        # Oct 16, 2026) thirty closes are four checkpoints, the 15th, 20th, 25th and 30th (one, the 30th, before).
        order = [c["pid"] for c in out["done"]["all"]["closes"]]
        self.assertEqual({root for root, _ in self.asked}, {self.root})
        self.assertEqual([pids for _, pids in self.asked[:4]], [order[:k] for k in (15, 20, 25, 30)])

    def test_it_is_read_over_the_checkpoints_first_k_closes_only(self):
        self.thirty()
        for i in range(4):                                    # closes 31-34: after the checkpoint
            self.twin(self.eq_close("p-a", cash="-9.00", posted=True, closed_at=ny("2026-10-15", 15, 56) + i),
                      live_r=-0.09, twin_r=-0.09)
        out = self.report()
        order = [c["pid"] for c in out["done"]["all"]["closes"]]
        self.assertEqual(len(out["done"]["all"]["closes"]), 34)
        self.assertTrue(self.asked)
        # A50's checkpoints (the 15th close, then every 5th): each reads its own first K, never a close after it.
        self.assertTrue(all(pids == order[:len(pids)] and len(pids) in (15, 20, 25, 30) for _, pids in self.asked),
                        "never the closes after the K-th")
        self.assertEqual(out["done"]["all"]["latest"]["at_close"], 30)

    def test_a_checkpoint_that_held_stops_holding_when_a14_fails(self):
        self.thirty()
        held = self.report()["done"]["all"]
        self.answer = a14(holds=False, why="the mean fill gap over 30 priced twins is beyond 15 bp a side")
        out = self.report()
        meter = out["done"]["all"]
        cp = meter["latest"]
        self.assertEqual((cp["holds"], cp["consistent_ok"], cp["items"]), (False, False, {"3": True, "4": False, "7": True}))
        self.assertEqual(cp["why"], "A14 (live fills consistent with their replay): the mean fill gap over 30 priced twins "
                                    "is beyond 15 bp a side")
        self.assertEqual((cp["a14"]["holds"], cp["a14"]["gap"]["ok"]), (False, False))
        self.assertEqual((meter["holds"], meter["provisional"]), (False, False))
        self.assertTrue(cp["final"], "a final reading that A14 does not hold: it is read, and it says no")
        self.assertNotIn("A8", [a["id"] for a in out["alarms"]], "no Done claim on a checkpoint A14 does not hold")
        # Nothing else of the reading moved, and the running figures are untouched.
        same = ("at_close", "closes", "programs", "net_usd", "by_program", "research_247", "by_route", "bh",
                "measured_programs", "replay_coverage", "final", "final_why")
        self.assertEqual({k: cp[k] for k in same}, {k: held["latest"][k] for k in same})
        self.assertEqual(meter["running"], held["running"])
        # They are what this tree's module reads without the edits (A14's reading is a checkpoint's): every figure but
        # the words of E1's own fill-gap half, where the tree has one.
        base = importlib.import_module("league.ops.dlane_report").report(self.root, settings=GATE, now=self.now)
        words = ("why", "a14", "holds")
        self.assertEqual({k: v for k, v in meter["running"].items() if k not in words},
                         {k: v for k, v in base["done"]["all"]["running"].items() if k not in words})
        self.assertEqual(self.asked and max(len(pids) for _, pids in self.asked), 30, "no A14 is read for the running figures")

    def test_a14_can_only_take_a_holding_away_never_give_one(self):
        # Twenty-nine closes of one program and one of another: the pinned rule's own item 3 fails.
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        lids = [self.eq_close("p-a" if i else "p-b", cash="2.00", posted=True, closed_at=ny("2026-10-14", 15, 56) + i)
                for i in range(30)]
        for lid in lids:
            self.twin(lid, live_r=0.02, twin_r=0.021)
        self.steady()
        cp = self.latest()
        self.assertEqual((cp["holds"], cp["a14"]["holds"], cp["items"]["3"], cp["items"]["4"]), (False, True, False, False))
        self.assertNotIn("A14", cp["why"])

    def test_an_a14_that_is_not_final_makes_the_reading_provisional(self):
        self.thirty()
        self.answer = a14(final=False)
        meter = self.report()["done"]["all"]
        cp = meter["latest"]
        self.assertEqual((cp["holds"], cp["final"], cp["final_why"]),
                         (True, False, "A14: a twin or a shadow session has not landed"))
        self.assertEqual((meter["holds"], meter["provisional"]), (False, True), "a Done claim waits for a final reading")

    def test_the_whys_ride_together(self):
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        for i in range(30):
            self.twin(self.eq_close("p-a" if i % 2 == 0 else "p-b", cash="2.00", posted=True,
                                    closed_at=ny("2026-10-14", 15, 56) + i), live_r=0.02, twin_r=0.021)
        # Research 24/7 fails too: a day with no research. The closes' own day, Oct 14, since the owner's change (A50):
        # the 30th close's window is every day after the 25th's, that same day (Oct 12 was in the 7-day window before).
        self.steady(skip=("2026-10-14",))
        self.answer = a14(holds=False, final=False, why="19 of 21 counted sessions agree")
        cp = self.latest()
        self.assertEqual((cp["holds"], cp["items"]), (False, {"3": True, "4": False, "7": False}))
        self.assertIn("research 24/7 (item 7)", cp["why"])
        self.assertTrue(cp["why"].endswith("A14 (live fills consistent with their replay): 19 of 21 counted sessions agree"))
        self.assertEqual(cp["final_why"], "A14: a twin or a shadow session has not landed")


class WithNoEquityClose(Fixture):
    """An options checkpoint (the direction lane's own fixture): A14 does not apply, and nothing of it moves."""

    def report(self, module, settings=NIGHTLY, previous=None) -> dict:
        return module.report(self.root, settings=settings, now=self.now, previous=previous, count_from=module.inception())

    def thirty(self) -> None:
        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        for _ in range(15):
            self.close("dir-a", pnl=5.0)
            self.close("dir-b", pnl=5.0)
        for fid in ("dir-a", "dir-b"):
            self.replays(fid, ["2026-10-05"])
        self.steady()
        self.posted()

    def test_the_checkpoint_is_what_it_was_with_a14_beside_it(self):
        import importlib

        self.thirty()
        with mock.patch.object(forward_twins, "a14_reading", side_effect=AssertionError("not asked")) as asked:
            out = self.report(R)
        asked.assert_not_called()
        cp = out["done"]["screen"]["latest"]
        self.assertEqual((cp["holds"], cp["final"], cp["items"]), (True, True, {"3": True, "4": True, "7": True}))
        self.assertEqual(cp["a14"], {"applies": False, "holds": True, "final": True, "why": None})
        base = self.report(importlib.import_module("league.ops.dlane_report"))["done"]["screen"]["latest"]
        self.assertEqual({k: v for k, v in cp.items() if k != "a14"}, {k: v for k, v in base.items() if k != "a14"})
        self.assertTrue(out["done"]["screen"]["holds"])

    def test_a14_of_by_itself(self):
        with mock.patch.object(forward_twins, "a14_reading", side_effect=AssertionError("not asked")):
            self.assertEqual(R.a14_of(self.store, []), {"applies": False, "holds": True, "final": True, "why": None})
            self.assertEqual(R.a14_of(self.store, [{"pid": 1}, {"pid": 2, "equity": False}]),
                             {"applies": False, "holds": True, "final": True, "why": None})
        with mock.patch.object(forward_twins, "a14_reading", return_value=a14()) as asked:
            self.assertEqual(R.a14_of(self.store, [{"pid": 1}, {"pid": "eq:2", "equity": True}]), a14())
        self.assertEqual(asked.call_args.args[0], Path(self.store.root))


class AFrozenFinalReading(A14Fixture):
    def test_it_is_carried_as_it_was(self):
        self.thirty()
        first = self.report()
        self.assertTrue(first["done"]["all"]["latest"]["final"])
        # The twins' record says otherwise later (a restated day, a store that cannot be read): the frozen reading stands.
        self.asked.clear()
        self.answer = RuntimeError("the forward store is gone")
        later = self.report(previous=first)
        cp = later["done"]["all"]["latest"]
        self.assertEqual((cp["holds"], cp["final"], cp["frozen"], own(cp["a14"], a14())), (True, True, True, a14()))
        self.assertTrue(later["done"]["all"]["holds"])
        self.assertEqual(self.asked, [], "a frozen checkpoint is not read again")

    def test_a_reading_frozen_before_e3_is_carried_without_an_a14(self):
        self.thirty()
        old = self.report()
        for name in ("all", "screen"):
            for cp in old["done"][name]["checkpoints"]:
                del cp["a14"]                               # as a report written before release E3 holds it
            for cp in old["done"]["without_seeded"][name]["checkpoints"]:
                del cp["a14"]
        self.answer = a14(holds=False, why="beyond the bound")
        cp = self.latest(previous=old)
        self.assertEqual((cp["holds"], cp["final"], cp["frozen"]), (True, True, True))
        self.assertNotIn("a14", cp)

    def test_a_provisional_reading_is_read_again(self):
        self.thirty()
        self.answer = a14(final=False)
        first = self.report()
        self.answer = a14(holds=False, why="beyond the bound")
        cp = self.latest(previous=first)
        self.assertEqual((cp["holds"], cp["final"], cp.get("frozen")), (False, True, None))


class WhateverA14ReadingAnswers(A14Fixture):
    """An `a14_reading` that returns a dict without `final`, a list, or raises leaves `meter` and `report` whole."""

    def whole(self, out: dict) -> dict:
        self.assertEqual(out["schema"], R.SCHEMA)
        self.assertEqual(out["done"]["all"]["running"]["closes"], 30)
        self.assertEqual(len(out["done"]["all"]["closes"]), 30)
        self.assertEqual(out["equity"]["twins"]["by_status"], {"priced": 30})
        self.assertIn("alarms", out)
        return out["done"]["all"]["latest"]

    def test_a_dict_without_final(self):
        self.thirty()
        self.answer = {"holds": True, "why": None}
        cp = self.whole(self.report())
        self.assertEqual((cp["holds"], cp["final"]), (True, False))
        said = {"holds": True, "why": None, "applies": True, "final": False}
        self.assertEqual(own(cp["a14"], said), said)
        self.assertFalse(self.report()["done"]["all"]["holds"], "never a Done claim on an A14 that does not say it is final")

    def test_a_dict_whose_flags_are_not_true(self):
        self.thirty()
        for answer in ({"holds": "yes", "final": 1}, {"holds": None, "final": None}, {}):
            self.answer = answer
            cp = self.whole(self.report())
            self.assertEqual((cp["holds"], cp["final"], cp["a14"]["holds"], cp["a14"]["final"]), (False, False, False, False))
            self.assertIn("A14 (live fills consistent with their replay): not held", cp["why"])

    def test_a_list(self):
        self.thirty()
        self.answer = [a14()]
        cp = self.whole(self.report())
        self.assertEqual((cp["holds"], cp["final"]), (False, False))
        self.assertEqual(cp["a14"]["applies"], True)
        self.assertRegex(cp["a14"]["why"], r"^A14 could not be read \((TypeError|AttributeError)\)$")

    def test_it_raises(self):
        self.thirty()
        for error in (RuntimeError("boom"), NotImplementedError("D: league/ops/forward_twins.py a14_reading"),
                      FileNotFoundError("forward.sqlite"), KeyError("pid")):
            self.answer = error
            cp = self.whole(self.report())
            said = {"applies": True, "holds": False, "final": False, "why": f"A14 could not be read ({type(error).__name__})"}
            self.assertEqual(own(cp["a14"], said), said)
            self.assertEqual((cp["holds"], cp["final"], cp["items"]["4"]), (False, False, False))

    def test_the_program_loss_line_and_k5_are_untouched(self):
        self.thirty()
        held = self.report()
        self.answer = RuntimeError("boom")
        out = self.report()
        for key in ("program_loss", "k5", "probe_envelope", "direction_net", "equity", "funnel"):
            self.assertEqual(json.dumps(out[key], sort_keys=True, default=str),
                             json.dumps(held[key], sort_keys=True, default=str), key)


class TheForwardRecordInTheReport(A14Fixture):
    ROW = {"id": "FW2", "level": "warning", "text": "FW2 stale: programs were left stale two nights running", "new": True}

    def test_the_section_and_its_alarms_ride_the_report(self):
        self.eq_family("p-a")
        section = {"at": S.iso(self.now), "mode": "record", "through": "2026-10-19", "alarms": [self.ROW]}
        with mock.patch.object(forward_report, "read_section", return_value=section) as read, \
                mock.patch.object(forward_report, "alarms", return_value=[self.ROW]) as alarms:
            out = self.report()
        read.assert_called_once_with(self.root)
        self.assertEqual(alarms.call_args.kwargs["now"], self.now)
        self.assertIs(alarms.call_args.kwargs["settings"], GATE)
        self.assertEqual(out["forward_record"], section)
        self.assertEqual(out["alarms"][-1], self.ROW)
        self.assertIn("PT1", [a["id"] for a in out["alarms"]], "the report's own alarms are before it, as they were")

    def test_an_alarm_row_without_a_level_is_dropped(self):
        self.eq_family("p-a")
        rows = [{"id": "FW1", "text": "no level"}, self.ROW, "junk", None, {"id": 7, "level": "warning", "text": "t"},
                {"id": "FW3", "level": "loud", "text": "t"}, {"id": "FW4", "level": "info", "text": None},
                {"id": "CP1", "level": "info", "text": "CP1 route sail:fake_a: t"}]
        with mock.patch.object(forward_report, "alarms", return_value=rows):
            out = self.report()
        forward = [a for a in out["alarms"] if isinstance(a, dict) and str(a.get("id"))[:2] in ("FW", "CP")]
        self.assertEqual(forward, [self.ROW, {"id": "CP1", "level": "info", "text": "CP1 route sail:fake_a: t"}])
        # What the dlane job does with every row it carries: `alarm["level"]`, `alarm["text"]`, `alarm["id"]`.
        self.assertTrue(all(isinstance(a["id"], str) and a["level"] in ("info", "warning") and isinstance(a["text"], str)
                            for a in out["alarms"]))

    def test_with_the_forward_mode_off_no_forward_alarm_is_added(self):
        from league.tests.test_forward_report import FakeA

        self.eq_family("p-a")
        write_json(self.root / forward_report.FILE, {"at": S.iso(self.now), "mode": "record", "alarms": [self.ROW]})
        # `read_section` reads the file's age against the WALL clock (it takes no `now`): held to the fixture's own
        # instant here, or this test would start failing 36 hours after the fixture's date.
        with mock.patch.multiple(forward_db, cfg=FakeA.cfg, mode=FakeA.mode), \
                mock.patch.object(forward_report.time, "time", lambda: self.now):
            base = [a["id"] for a in self.report(settings=GATE)["alarms"]]
            off = self.report(settings={**GATE, "elane": {"forward": {"mode": "off"}}})
            on = self.report(settings=RECORD)
        self.assertEqual([a["id"] for a in off["alarms"]], base)
        self.assertNotIn("FW2", base, "the code default is off")
        self.assertEqual([a["id"] for a in on["alarms"]], [*base, "FW2"])
        self.assertEqual(off["forward_record"]["mode"], "record", "the section is the file as last written")

    def test_the_report_goes_on_without_the_forward_record(self):
        self.thirty()
        held = self.report()
        with mock.patch.object(forward_report, "read_section", side_effect=RuntimeError("torn")):
            out = self.report()
        self.assertIsNone(out["forward_record"])
        self.assertEqual([a["id"] for a in out["alarms"]], [a["id"] for a in held["alarms"]])
        section = {"at": S.iso(self.now), "mode": "record"}
        with mock.patch.object(forward_report, "read_section", return_value=section), \
                mock.patch.object(forward_report, "alarms", side_effect=RuntimeError("boom")):
            out = self.report()
        self.assertEqual(out["forward_record"], section, "what was read before the failure is kept")
        self.assertEqual([a["id"] for a in out["alarms"]], [a["id"] for a in held["alarms"]])
        self.assertEqual(out["done"]["all"]["latest"]["holds"], held["done"]["all"]["latest"]["holds"])

    def test_no_file_no_section(self):
        self.eq_family("p-a")
        out = self.report(settings=RECORD)
        self.assertIsNone(out["forward_record"])
        self.assertEqual(out["done"]["preregistered"]["status"], R.PREREGISTERED["status"])
        self.assertIn("computed since release E3", out["done"]["preregistered"]["status"])
        # Release E3's loosening, now followed by the owner's four of A50 (Oct 16, 2026) and the captain's A50a(2) (A1.1
        # at 3), the last row since the reviews' fix (the owner's research window was the last before it).
        self.assertIn("the equity Train bar", [row["rule"] for row in out["loosened"]])
        self.assertEqual(out["loosened"][-2]["rule"], "Done's research 24/7 window (A50, the owner's goal of Oct 16)")
        self.assertEqual(out["loosened"][-1]["rule"], "A1.1's matched replay closes (the captain's A50a(2), Oct 16)")
        self.assertIn("either way (release E3)", out["tightened"][-1])
        self.assertEqual(out["rule"]["sha256"], dlane.DONE["rule_sha256"], "the pinned Done rule is not this release's")


class TheJobCarriesThem(A14Fixture):
    """`run`: the report written with the forward section, each forward warning a House alert of the dlane job too,
    and the stall job's `dlane` cause reading them from the file."""

    def test_the_file_the_alerts_and_the_stall_cause(self):
        from league.ops import stall
        from league.ops.context import Context, read_json

        self.thirty()
        row = TheForwardRecordInTheReport.ROW
        section = {"at": S.iso(self.now), "mode": "record", "alarms": [row]}
        ctx = Context("dlane", root=self.root, due_at=self.now, config={}, clock=lambda: self.now)
        (self.root / "swarm.json").write_text(json.dumps(GATE))
        with mock.patch.object(forward_report, "read_section", return_value=section), \
                mock.patch.object(forward_report, "alarms", return_value=[row]):
            out = R.run(ctx)
        self.assertTrue(out["ok"])
        self.assertIn("FW2", out["alarms"])
        doc = read_json(self.root / R.FILE)
        self.assertEqual(doc["forward_record"], section)
        self.assertEqual(own(doc["done"]["all"]["latest"]["a14"], a14()), a14())
        self.assertIn({"level": "warning", "text": f"dlane: {row['text']}"}, ctx.alerts)
        facts = stall.dlane_facts(self.root)
        self.assertIn("FW2", [a["id"] for a in facts["alarms"]])
        checks = stall._lane_checks(self.now, facts, True)
        self.assertTrue(checks["dlane"]["stalled"])
        self.assertIn("fw2", checks["dlane"]["numbers"]["alarms"])
        self.assertEqual(checks["done"]["stalled"], True, "the holding final checkpoint is told as before")


if __name__ == "__main__":
    unittest.main()


class DoneCountsAPanelProgramByDate(A14Fixture):
    """DONE COUNTS A PANEL PROGRAM'S CLOSES BY DATE (release E4 step two; the review of step two, its major): a panel
    program's lots closed on one New York day are ONE of Done's counts, for the 15th close (the 30th before the owner's
    A50), every later checkpoint and its program's 3 (5 before A50); the lots stand beside. An ETF close is one count as
    ever. Every close invented."""

    def panel_lots(self, family: str, day: str, n: int = 8, *, cash: str = "0.02") -> list[int]:
        from league.tests.test_equity_twins import lot, put_lot

        lids = []
        for i in range(n):
            self.lid += 1
            row = lot(self.lid, family=family, lane="equity", symbol=f"N{i:03d}", klass="stock", notional="25.00",
                      cash=cash, opened_day="2026-10-12", exit_day=day, closed_at=ny(day, 9, 35) + i,
                      info=json.dumps({"fee_basis": "broker"}))
            row["tag"] = R.PANEL_TAG
            put_lot(self.live, row)
            self.twin(self.lid, live_r=0.001, twin_r=0.001, notional=25.0, bh=0.01)
            lids.append(self.lid)
        return lids

    def etf_closes(self, family: str, n: int, *, day: str = "2026-10-14") -> None:
        for i in range(n):
            self.twin(self.eq_close(family, cash="2.00", posted=True, closed_at=ny(day, 15, 56) + i),
                      live_r=0.02, twin_r=0.021, bh=1.5)

    def test_the_counts_by_hand(self):
        rows = [{"pid": "eq:1", "family": "a", "day": "d1"}, {"pid": "eq:2", "family": "x", "day": "d1", "panel": True},
                {"pid": "eq:3", "family": "x", "day": "d1", "panel": True}, {"pid": "eq:4", "family": "a", "day": "d1"},
                {"pid": "eq:5", "family": "x", "day": "d1", "panel": True}, {"pid": "eq:6", "family": "x", "day": "d2",
                                                                              "panel": True},
                {"pid": "eq:7", "family": "y", "day": "d1", "panel": True}, {"pid": "o:8", "family": "a", "day": "d1"}]
        self.assertEqual(R.done_counts(rows), [1, 2, 2, 3, 2, 4, 5, 6])
        self.assertEqual([c["pid"] for c in R.first_counts(rows, 2)], ["eq:1", "eq:2", "eq:3", "eq:5"],
                         "the second count's later lot of its day goes with it")
        plain = [r for r in rows if not r.get("panel")]
        self.assertEqual(R.done_counts(plain), [1, 2, 3])
        self.assertEqual(R.first_counts(plain, 2), plain[:2], "with no panel close: the first k closes")

    def test_a_basket_rotation_is_one_close_and_no_checkpoint_comes_early(self):
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        self.eq_family("xs-a", lane="equity")
        # A50's first checkpoint is the 15th count (the 30th before): 13 ETF closes and one basket date are 14 counts,
        # where 21 lots counted a close each would have passed the 15th and the 20th.
        for i in range(13):
            self.twin(self.eq_close("p-a" if i % 2 == 0 else "p-b", cash="2.00", posted=True,
                                    closed_at=ny("2026-10-14", 15, 56) + i), live_r=0.02, twin_r=0.021, bh=1.5)
        self.panel_lots("xs-a", "2026-10-15")
        self.steady()
        meter = self.report()["done"]["all"]
        self.assertEqual(len(meter["closes"]), 21, "every lot is listed")
        self.assertEqual((meter["running"]["closes"], meter["running"]["lots"]), (14, 21))
        program = next(p for p in meter["running"]["by_program"] if p["family"] == "xs-a")
        self.assertEqual((program["closes"], program["lots"]), (1, 8))
        self.assertEqual((meter["checkpoints"], meter["next_checkpoint"]), ([], 15), "14 counts: no checkpoint yet")

    def test_one_rotation_date_does_not_meet_a_second_programs_three(self):
        # A50 (the owner's goal of Oct 16, 2026): the 15th count and 3 a program (the 30th and 5 before). The basket's
        # 8 lots of one date are one count: they would meet the 3 counted a close each.
        self.eq_family("p-a")
        self.eq_family("xs-a", lane="equity")
        self.panel_lots("xs-a", "2026-10-13")
        self.etf_closes("p-a", 15)
        self.steady()
        meter = self.report()["done"]["all"]
        cp = meter["checkpoints"][0]
        self.assertEqual((cp["at_close"], cp["closes"], cp["lots"]), (15, 15, 22), "the basket's date and 14 ETF closes")
        self.assertEqual((cp["programs_with_min_closes"], cp["items"]["3"]), (1, False))
        self.assertIn("1 programs with 3+ closes of the 2 needed", cp["why"])
        self.assertEqual(cp["close_dates"]["closes"], 22, "the close dates beside read the lots")
        self.assertEqual(cp["closed_at"], R._iso(R._epoch("2026-10-14T19:56:13Z") or 0), "the 14th ETF close")

    def test_five_rebalance_dates_are_a_programs_five(self):
        self.eq_family("p-a")
        self.eq_family("xs-a", lane="equity")
        for day in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"):
            self.panel_lots("xs-a", day)
        self.etf_closes("p-a", 25, day="2026-10-16")
        self.steady()
        cp = self.report()["done"]["all"]["latest"]
        self.assertEqual((cp["at_close"], cp["closes"], cp["lots"], cp["programs_with_min_closes"]), (30, 30, 65, 2))
        self.assertTrue(cp["items"]["3"])
        program = next(p for p in cp["by_program"] if p["family"] == "xs-a")
        self.assertEqual(program["closes"], 5)


class TheCloseDatesBesideEveryCheckpoint(A14Fixture):
    """A14_BESIDE_DONE (release E4 step two; `close_dates`): each checkpoint carries the distinct close dates among
    its counted closes, all programs, and the date-clustered t of their P&L, beside and never a rule. Eight lots of a
    basket sold at one open are eight closes and ONE date. Every close invented."""

    def test_thirty_closes_of_one_date_read_one_date_and_no_t(self):
        self.thirty()
        cp = self.latest()
        self.assertEqual({k: cp["close_dates"][k] for k in ("closes", "dates", "date_t", "unpriced")},
                         {"closes": 30, "dates": 1, "date_t": None, "unpriced": 0})
        self.assertEqual((cp["holds"], cp["items"]), (True, {"3": True, "4": True, "7": True}), "no rule reads it")

    def test_the_figures_by_hand(self):
        def close(day, pnl):
            return {"day": day, "pnl_usd": None if pnl is None else R.Decimal(pnl), "closed_at": 0.0}

        rows = [close("2026-10-14", "2.00")] * 8 + [close("2026-10-15", "-1.00"), close("2026-10-16", "3.00"),
                                                    close("2026-10-16", None)]
        got = R.close_dates(rows)
        sums = [16.0, -1.0, 3.0]
        mean = sum(sums) / 3
        sd = (sum((v - mean) ** 2 for v in sums) / 2) ** 0.5
        self.assertEqual((got["closes"], got["dates"], got["unpriced"]), (11, 3, 1))
        self.assertAlmostEqual(got["date_t"], round(mean / sd * 3 ** 0.5, 4))
        self.assertEqual(R.close_dates([])["dates"], 0)
        self.assertIsNone(R.close_dates([close("2026-10-14", "1.00"), close("2026-10-15", "1.00")])["date_t"],
                          "no spread: no t")

    def test_the_preregistration_says_the_figures_are_computed(self):
        self.assertIn("close-date figures are computed since release E4's step two", R.PREREGISTERED["status"])
        self.assertNotIn("not computed yet", R.PREREGISTERED["status"])
        self.assertEqual(R.PREREGISTERED["beside_done"], R.A14_BESIDE_DONE, "the registered sentence is unchanged")
