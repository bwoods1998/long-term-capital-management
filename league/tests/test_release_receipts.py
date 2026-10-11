"""RELEASE RECEIPTS (release E3, D17; league/ops/release_receipts.py): a deploy declares the funnel metric it expects to
move, and the stall job reads it back after its window. Held here: a declaration is declared once, with the metric
before the deploy and the sample sd of the four windows before it; it is read at its own window and not before (72 and
168 hours), once; each verdict of D17's rule and its edges; a path that names nothing reads "unreadable"; a receipt not
read 24 hours after its window closed is unread; the funnel's own failure is asked again and never decides a receipt;
nothing raises into the stall job; the store is append-only and owner-only.

The funnel is a FAKE here (a function of the window's two ends, patched over `funnel.window`), except in
`TheRealFunnel`, which reads a synthetic swarm store through the real one. Every count is invented."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.ops import funnel
from league.ops import release_receipts as RR
from league.ops import schedule as S

HOUR = 3600.0
#: The deploy, and the release's directory name as `funnel.release_start` reads it from the deploy record.
DEPLOYED = S.epoch("2026-10-12T20:00:00Z")
RELEASE = "20261012-2000-e3"
#: The declarations release E3 ships (the spec's 7.6), as package A's file holds them.
E3 = {"schema": 1, "receipts": [
    {"id": "E3-forward", "release": "E3", "metric": "forward_record.program_sessions", "direction": "up", "min_delta": 1,
     "window_hours": 168, "why": "the forward record accrues program-sessions"},
    {"id": "E3-oof", "release": "E3", "metric": "forward_record.oof_rows", "direction": "up", "min_delta": 1,
     "window_hours": 168, "why": "every scored version of a hidden-year family leaves an OOF row"}]}


def receipt(rid: str = "fake-up", **kw) -> dict:
    return {"id": rid, "release": "E3", "metric": "forward_record.program_sessions", "direction": "up", "min_delta": 5,
            "why": "a fake receipt", **kw}


class Fixture(unittest.TestCase):
    """A state root, a base with a deploy record, a release directory with a declarations file, and a fake funnel:
    `self.rate` program-sessions an hour before the deploy and `self.after` an hour after it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.release = self.base / "releases" / RELEASE
        self.rate, self.after = 0.0, 1.0
        self.errors: dict = {}
        self.asked: list[tuple[float, float]] = []
        self.record(DEPLOYED)
        patcher = mock.patch.object(funnel, "window", self.window)
        patcher.start()
        self.addCleanup(patcher.stop)

    def record(self, at: float, release: str = RELEASE) -> None:
        with (self.base / "deploys.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"stage": "verdict", "verdict": "promoted", "release": release, "at": S.iso(at)}) + "\n")

    def declare(self, *receipts: dict, schema: int = 1) -> None:
        path = self.release / RR.DECLARATIONS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": schema, "receipts": list(receipts)}), encoding="utf-8")

    def window(self, root, start: float, end: float) -> dict:
        """THE FAKE FUNNEL: hours before the deploy count `rate` each, hours after it `after` each."""
        self.asked.append((start, end))
        before = max(0.0, min(end, DEPLOYED) - min(start, DEPLOYED)) / HOUR
        after = max(0.0, max(end, DEPLOYED) - max(start, DEPLOYED)) / HOUR
        out = {"from": S.iso(start), "to": S.iso(end), "errors": dict(self.errors)}
        if not self.errors:
            out["forward_record"] = {"program_sessions": int(round(before * self.rate + after * self.after)),
                                     "oof_rows": 0, "ok": True, "nan": float("nan")}
        return out

    def step(self, hours: float) -> dict:
        return RR.step(self.root, self.base, self.release, now=DEPLOYED + hours * HOUR)

    def rows(self, kind: str | None = None) -> list[dict]:
        return [r for r in RR.rows(self.root) if kind is None or r["kind"] == kind]


class TheDeclarations(Fixture):
    def test_the_file_is_read_with_the_default_window(self):
        self.declare(receipt(), receipt("fake-week", window_hours=168, direction="down"))
        found = RR.declarations(self.release)
        self.assertEqual([(d["id"], d["window_hours"], d["direction"]) for d in found],
                         [("fake-up", 72.0, "up"), ("fake-week", 168.0, "down")])
        self.assertEqual(RR.READ_AFTER_HOURS, 72)
        self.assertEqual(set(found[0]), {"id", "release", "metric", "direction", "min_delta", "window_hours", "why"})

    def test_release_e3s_two_receipts_read_back_after_a_week(self):
        self.declare(*E3["receipts"])
        self.assertEqual([(d["id"], d["metric"], d["window_hours"], d["min_delta"]) for d in RR.declarations(self.release)],
                         [("E3-forward", "forward_record.program_sessions", 168.0, 1.0),
                          ("E3-oof", "forward_record.oof_rows", 168.0, 1.0)])

    def test_a_malformed_entry_is_dropped_and_named(self):
        self.declare(receipt("good"), receipt("sideways", direction="sideways"), receipt("negative", min_delta=-1),
                     receipt("good"), "not an object", receipt("no-window", window_hours=0),
                     receipt("flag", min_delta=True), {"id": "bare"}, receipt("bad path", metric="a b"),
                     receipt("words", why=3))
        self.assertEqual([d["id"] for d in RR.declarations(self.release)], ["good"])
        out = self.step(1)
        self.assertEqual(out["declared"], ["good"])
        text = " | ".join(out["errors"])
        for name in ("sideways", "negative", "good dropped: its id is declared twice", "#4", "no-window", "flag", "bare",
                     "words"):
            self.assertIn(name, text)
        self.assertEqual(len(out["errors"]), 9)
        self.assertEqual([r["id"] for r in self.rows()], ["good"], "a dropped entry is never declared")

    def test_an_absent_or_unreadable_file_declares_nothing(self):
        self.assertEqual(RR.declarations(self.release), [])
        self.assertEqual(self.step(1), {"declared": [], "read": [], "unread": [], "errors": []})
        self.assertFalse((self.root / RR.DB).exists(), "no declaration and no receipt: no store is made")
        self.assertEqual(self.asked, [], "and the funnel is not read")
        (self.release / RR.DECLARATIONS).parent.mkdir(parents=True)
        (self.release / RR.DECLARATIONS).write_text("{not json", encoding="utf-8")
        self.assertEqual(RR.declarations(self.release), [])
        self.assertIn("unreadable", self.step(1)["errors"][0])
        self.declare(receipt(), schema=2)
        self.assertEqual(RR.declarations(self.release), [])
        self.assertIn("schema 1", self.step(1)["errors"][0])


class TheMetric(unittest.TestCase):
    def test_a_dotted_path_to_a_number(self):
        window = {"births": 3, "forward_record": {"program_sessions": 40, "deep": {"x": 1.5}}, "equity": {"beta": {"births": 2}}}
        self.assertEqual(RR.metric(window, "births"), 3.0)
        self.assertEqual(RR.metric(window, "forward_record.program_sessions"), 40.0)
        self.assertEqual(RR.metric(window, "forward_record.deep.x"), 1.5)
        self.assertEqual(RR.metric(window, "equity.beta.births"), 2.0)
        self.assertIsInstance(RR.metric(window, "births"), float)

    def test_none_when_it_names_no_finite_number(self):
        window = {"flag": True, "text": "7", "none": None, "nan": float("nan"), "inf": float("inf"), "a": {"b": 1}}
        for path in ("flag", "text", "none", "nan", "inf", "a", "a.c", "a.b.c", "missing", ""):
            self.assertIsNone(RR.metric(window, path), path)


class TheVerdict(unittest.TestCase):
    def test_each_verdict_in_the_declared_direction(self):
        self.assertEqual(RR.verdict(10, 16, "up", 5), "moved")
        self.assertEqual(RR.verdict(10, 15, "up", 5), "moved", "the delta itself moves it")
        self.assertEqual(RR.verdict(10, 14, "up", 5), "flat")
        self.assertEqual(RR.verdict(10, 6, "up", 5), "flat")
        self.assertEqual(RR.verdict(10, 5, "up", 5), "wrong_way")
        self.assertEqual(RR.verdict(10, 4, "down", 5), "moved")
        self.assertEqual(RR.verdict(10, 16, "down", 5), "wrong_way")
        self.assertEqual(RR.verdict(10, 12, "down", 5), "flat")

    def test_unreadable_when_either_side_is_no_number(self):
        self.assertEqual(RR.verdict(None, 16, "up", 5), "unreadable")
        self.assertEqual(RR.verdict(10, None, "up", 5), "unreadable")
        self.assertEqual(RR.verdict(10, 16, "sideways", 5), "unreadable")
        self.assertEqual(RR.VERDICTS, ("moved", "flat", "wrong_way", "unreadable"))


class DeclaredOnce(Fixture):
    def test_the_first_sighting_declares_with_the_metric_before_and_its_sd(self):
        self.rate = 2.0
        self.declare(receipt())
        out = self.step(0.5)
        self.assertEqual((out["declared"], out["read"], out["unread"], out["errors"]), (["fake-up"], [], [], []))
        (row,) = self.rows()
        self.assertEqual((row["kind"], row["release"], row["metric"], row["direction"], row["min_delta"], row["window_hours"]),
                         ("declared", "E3", "forward_record.program_sessions", "up", 5.0, 72.0))
        self.assertEqual(row["deployed_at"], DEPLOYED, "the deploy record's promoted verdict, not the sighting")
        self.assertEqual(row["at"], DEPLOYED + 0.5 * HOUR)
        self.assertEqual(row["value"], 144.0, "the metric over the 72 hours before the deploy")
        self.assertEqual(row["sd"], 0.0, "four equal windows")
        self.assertIsNone(row["verdict"])
        # The four windows before the deploy, each one window long.
        self.assertEqual(sorted(self.asked), [(DEPLOYED - (k + 1) * 72 * HOUR, DEPLOYED - k * 72 * HOUR) for k in (3, 2, 1, 0)])

    def test_a_second_pass_and_a_second_release_declare_nothing_more(self):
        self.declare(receipt())
        self.step(0.5)
        self.assertEqual(self.step(1.0)["declared"], [])
        # A later release still carries the id, rewritten: the receipt declared first stands as it was.
        self.record(DEPLOYED + 30 * HOUR, "20261014-0200-e4")
        later = self.base / "releases" / "20261014-0200-e4"
        (later / RR.DECLARATIONS).parent.mkdir(parents=True)
        (later / RR.DECLARATIONS).write_text(json.dumps({"schema": 1, "receipts": [
            receipt(direction="down", min_delta=99, window_hours=1), receipt("fake-new")]}), encoding="utf-8")
        out = RR.step(self.root, self.base, later, now=DEPLOYED + 31 * HOUR)
        self.assertEqual(out["declared"], ["fake-new"])
        rows = {r["id"]: r for r in self.rows("declared")}
        self.assertEqual((rows["fake-up"]["direction"], rows["fake-up"]["min_delta"], rows["fake-up"]["deployed_at"]),
                         ("up", 5.0, DEPLOYED))
        self.assertEqual(rows["fake-new"]["deployed_at"], DEPLOYED + 30 * HOUR, "its own release's start")

    def test_the_sample_sd_of_the_four_windows_before(self):
        self.declare(receipt(window_hours=1))
        counts = {3: 10, 2: 14, 1: 12, 0: 20}        # k windows back: the hour ending k hours before the deploy

        def window(root, start, end):
            k = int(round((DEPLOYED - end) / HOUR))
            return {"errors": {}, "forward_record": {"program_sessions": counts.get(k, 0)}}

        with mock.patch.object(funnel, "window", window):
            self.step(0.1)
        (row,) = self.rows()
        mean = (10 + 14 + 12 + 20) / 4
        self.assertEqual(row["value"], 20.0)
        self.assertAlmostEqual(row["sd"], math.sqrt(((10 - mean) ** 2 + (14 - mean) ** 2 + (12 - mean) ** 2 + (20 - mean) ** 2) / 3),
                               places=12)

    def test_with_no_deploy_on_record_the_sighting_is_the_deploy(self):
        (self.base / "deploys.jsonl").unlink()
        self.declare(receipt())
        self.step(3.0)
        (row,) = self.rows()
        self.assertEqual(row["deployed_at"], DEPLOYED + 3 * HOUR)
        self.assertEqual(self.step(74.9)["read"], [], "its window runs from the sighting")
        self.assertEqual([r["id"] for r in self.step(75.0)["read"]], ["fake-up"])


class ReadAtItsOwnWindow(Fixture):
    def test_seventy_two_and_a_hundred_and_sixty_eight_hours_and_not_before(self):
        self.rate, self.after = 1.0, 1.5
        self.declare(receipt(), receipt("fake-week", window_hours=168, min_delta=80))
        self.step(0.5)
        self.assertEqual(self.step(71.99)["read"], [])
        out = self.step(72.0)
        self.assertEqual(out["read"], [{"id": "fake-up", "verdict": "moved"}])   # 72 -> 108
        self.assertEqual(self.step(167.99)["read"], [], "a receipt is read once, and the week's is not due")
        self.assertEqual(self.step(168.0)["read"], [{"id": "fake-week", "verdict": "moved"}])   # 168 -> 252
        self.assertEqual(self.step(400.0), {"declared": [], "read": [], "unread": [], "errors": []})
        read = {r["id"]: r for r in self.rows("read")}
        self.assertEqual((read["fake-up"]["value"], read["fake-up"]["at"]), (108.0, DEPLOYED + 72 * HOUR))
        self.assertEqual((read["fake-week"]["value"], read["fake-week"]["verdict"]), (252.0, "moved"))
        self.assertEqual(len(self.rows()), 4, "one declaration and one read an id")
        # The read asks the funnel for exactly the window after the deploy.
        self.assertIn((DEPLOYED, DEPLOYED + 72 * HOUR), self.asked)
        self.assertIn((DEPLOYED, DEPLOYED + 168 * HOUR), self.asked)

    def test_flat_and_wrong_way(self):
        self.rate, self.after = 1.0, 1.0
        self.declare(receipt("fake-flat"), receipt("fake-down", direction="down"), receipt("fake-zero", min_delta=0))
        self.step(0.1)
        said = {r["id"]: r["verdict"] for r in self.step(72.0)["read"]}
        self.assertEqual(said, {"fake-flat": "flat", "fake-down": "flat", "fake-zero": "moved"})
        self.rate, self.after = 1.0, 0.5
        self.declare(receipt("fake-fell"), receipt("fake-fell-down", direction="down"))
        self.step(73.0)   # sighted late: declared from the deploy record all the same, and read in the same pass
        said = {r["id"]: r["verdict"] for r in self.rows("read")}
        self.assertEqual((said["fake-fell"], said["fake-fell-down"]), ("wrong_way", "moved"))

    def test_an_unknown_path_is_unreadable(self):
        self.declare(receipt("fake-nowhere", metric="forward_record.no_such_count"), receipt("fake-flag", metric="forward_record.ok"),
                     receipt("fake-nan", metric="forward_record.nan"))
        self.step(0.1)
        self.assertEqual([r["value"] for r in self.rows("declared")], [None, None, None])
        out = self.step(72.0)
        self.assertEqual({r["id"]: r["verdict"] for r in out["read"]},
                         {"fake-nowhere": "unreadable", "fake-flag": "unreadable", "fake-nan": "unreadable"})
        self.assertEqual(out["errors"], [], "the funnel answered: the path names no number")
        self.assertIsNone(self.rows("read")[0]["value"])


class TheFunnelsOwnFailure(Fixture):
    def test_it_is_asked_again_and_does_not_decide_the_receipt(self):
        self.rate, self.after = 1.0, 2.0
        self.declare(receipt())
        self.step(0.1)
        self.errors = {"forward_record": "OperationalError: database is locked"}
        out = self.step(72.0)
        self.assertEqual((out["read"], out["unread"]), ([], []))
        self.assertIn("fake-up not read yet", out["errors"][0])
        self.errors = {}
        self.assertEqual(self.step(72.5)["read"], [{"id": "fake-up", "verdict": "moved"}])

    def test_a_day_of_it_reads_unreadable(self):
        self.declare(receipt())
        self.step(0.1)
        self.errors = {"swarm": "OperationalError: database is locked"}
        self.assertEqual(self.step(95.9)["read"], [])
        self.assertEqual(self.step(96.0)["read"], [{"id": "fake-up", "verdict": "unreadable"}])

    def test_a_declaration_waits_a_day_for_its_before_then_stands_without_one(self):
        self.declare(receipt())
        self.errors = {"swarm": "OperationalError: database is locked"}
        out = self.step(0.1)
        self.assertEqual(out["declared"], [])
        self.assertIn("fake-up not declared yet", out["errors"][0])
        self.assertEqual(self.rows(), [])
        out = self.step(24.0)
        self.assertEqual(out["declared"], ["fake-up"])
        self.assertIsNone(self.rows()[0]["value"])
        self.assertIsNone(self.rows()[0]["sd"], "no sd unless all four windows gave a number")
        self.errors = {}
        self.assertEqual(self.step(72.0)["read"], [{"id": "fake-up", "verdict": "unreadable"}])

    def test_a_funnel_that_raises_is_an_error_never_a_zero(self):
        self.declare(receipt())

        def broken(root, start, end):
            raise RuntimeError("no funnel")

        with mock.patch.object(funnel, "window", broken):
            out = self.step(30.0)
        self.assertEqual(out["declared"], ["fake-up"])
        self.assertIn("the funnel could not be read (RuntimeError)", out["errors"])
        self.assertIsNone(self.rows()[0]["value"])


class Unread(Fixture):
    def test_a_receipt_is_unread_a_day_after_its_window_closed(self):
        self.declare(receipt())
        self.step(0.1)
        # The stall job did not run (or could not write): no read row.
        by = {r["id"]: r for r in RR.summary(self.root, now=DEPLOYED + 95.9 * HOUR)}
        self.assertFalse(by["fake-up"]["unread"])
        by = {r["id"]: r for r in RR.summary(self.root, now=DEPLOYED + 96 * HOUR)}
        self.assertTrue(by["fake-up"]["unread"])
        self.assertEqual((by["fake-up"]["closes_at"], by["fake-up"]["verdict"], by["fake-up"]["after"]),
                         (DEPLOYED + 72 * HOUR, None, None))
        self.assertEqual(RR.UNREAD_GRACE_HOURS, 24)

    def test_a_read_that_fails_is_listed_unread_only_after_the_day(self):
        self.declare(receipt())
        self.step(0.1)
        with mock.patch.object(RR, "verdict", side_effect=RuntimeError("boom")):
            early = self.step(80.0)
            late = self.step(96.0)
        self.assertEqual((early["read"], early["unread"]), ([], []))
        self.assertIn("fake-up could not be read (RuntimeError)", early["errors"][0])
        self.assertEqual((late["read"], late["unread"]), ([], ["fake-up"]))
        # Once it can be read it is, and it is unread no more.
        self.assertEqual(self.step(97.0)["read"], [{"id": "fake-up", "verdict": "moved"}])
        by = {r["id"]: r for r in RR.summary(self.root, now=DEPLOYED + 200 * HOUR)}
        self.assertEqual((by["fake-up"]["unread"], by["fake-up"]["verdict"], by["fake-up"]["read_at"]),
                         (False, "moved", DEPLOYED + 97 * HOUR))

    def test_the_summary_of_a_read_receipt(self):
        self.rate, self.after = 1.0, 2.0
        self.declare(receipt())
        self.step(0.1)
        self.step(72.0)
        (row,) = RR.summary(self.root, now=DEPLOYED + 500 * HOUR)
        self.assertEqual((row["before"], row["after"], row["verdict"], row["unread"], row["deployed_at"]),
                         (72.0, 144.0, "moved", False, DEPLOYED))
        self.assertEqual(RR.summary(self.base / "nowhere", now=1.0), [])


class NeverRaises(Fixture):
    def test_a_state_root_that_cannot_hold_a_store(self):
        self.declare(receipt())
        blocked = self.base / "a-file"
        blocked.write_text("not a directory")
        out = RR.step(blocked, self.base, self.release, now=DEPLOYED)
        self.assertEqual((out["declared"], out["read"], out["unread"]), ([], [], []))
        self.assertEqual(len(out["errors"]), 1)

    def test_a_context_without_a_base_or_a_release(self):
        self.assertEqual(RR.step(self.root, None, None, now=DEPLOYED),
                         {"declared": [], "read": [], "unread": [], "errors": []})
        self.declare(receipt())
        out = RR.step(self.root, None, self.release, now=DEPLOYED)
        self.assertEqual(out["declared"], ["fake-up"])
        self.assertEqual(self.rows()[0]["deployed_at"], DEPLOYED, "no base: the sighting's time")

    def test_a_torn_store(self):
        (self.root / RR.DB).write_bytes(b"not a database, not at all")
        self.declare(receipt())
        out = self.step(1.0)
        self.assertEqual(out["declared"], [])
        self.assertIn("DatabaseError", out["errors"][0])


class TheStore(Fixture):
    def test_it_is_owner_only_and_append_only(self):
        self.declare(receipt())
        self.step(0.1)
        path = self.root / RR.DB
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        db = sqlite3.connect(str(path))
        self.addCleanup(db.close)
        for statement in ("UPDATE l3_receipts SET verdict='moved'", "DELETE FROM l3_receipts"):
            with self.assertRaises(sqlite3.DatabaseError) as raised:
                db.execute(statement)
            self.assertIn(RR.APPEND_ONLY_ERROR, str(raised.exception))

    def test_rows_are_read_only_and_empty_without_a_store(self):
        self.assertEqual(RR.rows(self.root), [])
        self.assertFalse((self.root / RR.DB).exists(), "reading creates nothing")
        self.declare(receipt())
        self.step(0.1)
        (row,) = RR.rows(self.root)
        self.assertEqual(set(row), {"seq", "id", "kind", "release", "metric", "direction", "min_delta", "window_hours",
                                    "deployed_at", "value", "sd", "verdict", "at"})

    def test_nothing_is_written_under_the_release_directory(self):
        self.declare(receipt())
        before = sorted(p.relative_to(self.release) for p in self.release.rglob("*"))
        self.step(0.1)
        self.step(100.0)
        self.assertEqual(sorted(p.relative_to(self.release) for p in self.release.rglob("*")), before)


class TheRealFunnel(unittest.TestCase):
    """The real `funnel.window` over a synthetic swarm store: a metric the funnel has today (the swarm's births)."""

    def test_births_before_and_after_a_deploy(self):
        from league.swarm.store import SwarmStore

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "state"
            clock = [DEPLOYED - 10 * HOUR]
            store = SwarmStore(root, clock=lambda: clock[0])
            try:
                store.event("swarm.born", "fake-a", {"lane": "alpha"})
                for hours in (1, 2, 3):
                    clock[0] = DEPLOYED + hours * HOUR
                    store.event("swarm.born", f"fake-{hours}", {"lane": "alpha"})
            finally:
                store.close()
            (base / "deploys.jsonl").write_text(json.dumps({"stage": "verdict", "verdict": "promoted", "release": RELEASE,
                                                            "at": S.iso(DEPLOYED)}) + "\n")
            release = base / "releases" / RELEASE
            (release / RR.DECLARATIONS).parent.mkdir(parents=True)
            (release / RR.DECLARATIONS).write_text(json.dumps({"schema": 1, "receipts": [
                {"id": "fake-births", "release": "fake", "metric": "births", "direction": "up", "min_delta": 2,
                 "window_hours": 24}]}))
            first = RR.step(root, base, release, now=DEPLOYED + 5 * HOUR)
            self.assertEqual((first["declared"], first["errors"]), (["fake-births"], []))
            second = RR.step(root, base, release, now=DEPLOYED + 24 * HOUR)
            self.assertEqual(second["read"], [{"id": "fake-births", "verdict": "moved"}])
            (row,) = RR.summary(root, now=DEPLOYED + 25 * HOUR)
            self.assertEqual((row["before"], row["after"]), (1.0, 3.0))


if __name__ == "__main__":
    unittest.main()
