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
integrator or, until then, on a copy of its source. Every close, twin and count is invented."""

from __future__ import annotations

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
        self.assertEqual(cp["a14"], a14())
        self.assertTrue(out["done"]["all"]["holds"])
        # It is read over exactly the checkpoint's counted closes, from the state root.
        root, pids = self.asked[0]
        self.assertEqual((root, len(pids)), (self.root, 30))
        self.assertEqual(pids, [c["pid"] for c in out["done"]["all"]["closes"]][:30])

    def test_it_is_read_over_the_checkpoints_first_k_closes_only(self):
        self.thirty()
        for i in range(4):                                    # closes 31-34: after the checkpoint
            self.twin(self.eq_close("p-a", cash="-9.00", posted=True, closed_at=ny("2026-10-15", 15, 56) + i),
                      live_r=-0.09, twin_r=-0.09)
        out = self.report()
        first = [c["pid"] for c in out["done"]["all"]["closes"]][:30]
        self.assertEqual(len(out["done"]["all"]["closes"]), 34)
        self.assertTrue(self.asked)
        self.assertTrue(all(pids == first for _, pids in self.asked), "never the closes after the K-th")
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
        self.assertTrue(meter["running"]["consistent_ok"])

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
        self.steady(skip=("2026-10-12",))                    # research 24/7 fails too: a day with no research
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
        self.assertEqual((cp["holds"], cp["final"], cp["frozen"], cp["a14"]), (True, True, True, a14()))
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
        self.assertEqual(cp["a14"], {"holds": True, "why": None, "applies": True, "final": False})
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
            self.assertEqual(cp["a14"], {"applies": True, "holds": False, "final": False,
                                         "why": f"A14 could not be read ({type(error).__name__})"})
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
        with mock.patch.multiple(forward_db, cfg=FakeA.cfg, mode=FakeA.mode):
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
        self.assertEqual(out["loosened"][-1]["rule"], "the equity Train bar")
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
        self.assertEqual(doc["done"]["all"]["latest"]["a14"], a14())
        self.assertIn({"level": "warning", "text": f"dlane: {row['text']}"}, ctx.alerts)
        facts = stall.dlane_facts(self.root)
        self.assertIn("FW2", [a["id"] for a in facts["alarms"]])
        checks = stall._lane_checks(self.now, facts, True)
        self.assertTrue(checks["dlane"]["stalled"])
        self.assertIn("fw2", checks["dlane"]["numbers"]["alarms"])
        self.assertEqual(checks["done"]["stalled"], True, "the holding final checkpoint is told as before")


if __name__ == "__main__":
    unittest.main()
