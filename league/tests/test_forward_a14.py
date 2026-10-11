"""Release E3, package D: `forward_twins.a14_reading`, the A14 reading of a Done checkpoint's counted closes (D13).

A14 as pre-registered (league/ops/dlane_report.py `A14_CONSISTENCY`) and as coded: over the counted equity closes, the
SIZE of the mean fill gap against the official-price model within 15 bp a side AND the live and the shadow intents
agreeing on at least 95% of the counted sessions. With no equity close it does not apply; unmeasured, it never holds.
EVERY BRANCH RETURNS EVERY KEY (the Done meter reads it inside the dlane job, which must never fail for it), now with
`intents.disagreed` and `intents.causes`: a disagreement is counted with its cause and changes nothing of the rule.

Every close, twin record and session row here is invented. `forward_db.open_db` is package A's and a stub on this
branch: the FAKE of it (league/tests/test_forward_twins.py `fake_open_db`, read-only through `guard.connect_ro`)
stands in; the forward store is the real `forward_db.SCHEMA` in a file, its rows written with SQL."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import schedule
from league.ops import forward_db, forward_twins, twins
from league.tests import test_forward_twins as fx

T0 = dt.date(2026, 10, 12)
#: Sessions from the first forward day, oldest first.
DAYS = forward_twins._sessions(T0, dt.date(2027, 4, 30))
A, B = "fake-alpha@1:r", "fake-beta@2:r"


def after(day: str) -> str:
    return schedule.next_session(day).isoformat()


def close(lid: int, instance: str = A, *, opened: str = DAYS[1], day: str = DAYS[20], equity: bool = True) -> dict:
    """A counted close as `dlane_report.equity_closes` shapes it (the keys the reading reads, and a few it does not)."""
    return {"pid": f"eq:{lid}", "lid": lid, "instance": instance, "family": instance.split("@")[0], "equity": equity,
            "house": False, "day": day, "opened_day": opened, "route": "d2_real", "pnl_usd": 1.0}


def priced(gap_bp: float, **over) -> dict:
    return {"status": "priced", "final": True, "gap_bp": gap_bp, **over}


def shape(case: unittest.TestCase, out) -> None:
    """EVERY KEY, ON EVERY BRANCH, with the types the Done meter and the report read."""
    case.assertIsInstance(out, dict)
    case.assertEqual(tuple(out), forward_twins.A14_KEYS)
    case.assertEqual(tuple(out["gap"]), forward_twins.A14_GAP_KEYS)
    case.assertEqual(tuple(out["intents"]), forward_twins.A14_INTENT_KEYS)
    for key in ("applies", "holds", "final"):
        case.assertIsInstance(out[key], bool, key)
    case.assertTrue(out["why"] is None or isinstance(out["why"], str))
    case.assertEqual((out["gap"]["bound_bp"], out["intents"]["bound"]), (forward_db.A14_GAP_BP, forward_db.A14_AGREE))
    case.assertEqual((forward_db.A14_GAP_BP, forward_db.A14_AGREE), (15.0, 0.95))
    for key in ("closes", "priced", "unpriced", "pending"):
        case.assertIsInstance(out["gap"][key], int, key)
    for key in ("instances", "sessions", "agreed", "missing", "unreadable", "disagreed"):
        case.assertIsInstance(out["intents"][key], int, key)
    case.assertEqual(sorted(out["intents"]["causes"]), sorted(forward_db.CAUSES))
    case.assertTrue(all(isinstance(n, int) for n in out["intents"]["causes"].values()))
    case.assertIn(out["gap"]["ok"], (True, False, None))
    case.assertIn(out["intents"]["ok"], (True, False, None))
    case.assertIsInstance(out["by_instance"], list)
    for row in out["by_instance"]:
        case.assertEqual(tuple(row), forward_twins.A14_INSTANCE_KEYS)
    case.assertEqual(out["holds"], out["gap"]["ok"] is True and out["intents"]["ok"] is True if out["applies"] else True)
    json.dumps(out)     # the dlane report is JSON


class Reading(unittest.TestCase):
    def setUp(self):
        fx.install(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.records: dict = {}

    # ------------------------------------------------------------------ fixtures
    def forward(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.root / forward_db.DB)
        self.addCleanup(db.close)
        db.executescript(forward_db.SCHEMA)
        return db

    def rows(self, instance: str, verdicts, *, first: int = 0, cause: str | None = None) -> None:
        """One `fwd_twins` row a session from `DAYS[first]`: each verdict 1 (agreed), 0 (disagreed: `cause`, or the
        cause named as a string), None (unreadable: "split"), "retired", or "-" (no row: missing)."""
        db = self.forward()
        for i, verdict in enumerate(verdicts):
            if verdict == "-":
                continue
            why = None
            named = cause
            if verdict in forward_db.CAUSES:
                verdict, named = 0, verdict
            elif verdict in forward_twins.UNREADABLE:
                verdict, why = None, verdict
            elif verdict is None:
                why = "split"
            db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, "
                       "shadow_bars, cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (instance, DAYS[first + i], 1, "[]", "[]", verdict, why, 1.0, None, "f" * 16,
                        (named or "unknown") if verdict == 0 else None))
        db.commit()
        db.close()

    def twins(self, **records) -> None:
        self.records.update({k.replace("_", ":"): v for k, v in records.items()})
        db = sqlite3.connect(self.root / forward_twins.SWARM_DB)
        db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (twins.EQUITY_TWINS_KEY, json.dumps(self.records)))
        db.commit()
        db.close()

    def read(self, counted):
        out = forward_twins.a14_reading(self.root, counted)
        shape(self, out)
        return out

    def fresh(self) -> None:
        """Both stores gone (the forward store is append-only: a test that reads twice starts each from nothing)."""
        for name in (forward_db.DB, forward_twins.SWARM_DB):
            (self.root / name).unlink(missing_ok=True)
        self.records = {}

    def held(self, gaps=(-3.0,), verdicts=(1,) * 20):
        """A reading, from fresh stores, over one instance's closes: one priced twin a gap, and a row a session from
        its first decision (`DAYS[0]`) through the session before its last counted exit."""
        self.fresh()
        self.twins(**{f"eq_{i + 1}": priced(g) for i, g in enumerate(gaps)})
        self.rows(A, verdicts)
        return self.read([close(i + 1, day=DAYS[len(verdicts)]) for i in range(len(gaps))])


class WhenItApplies(Reading):
    def test_no_equity_close_does_not_apply_and_holds(self):
        for counted in ([], [close(1, equity=False), {"pid": 9, "equity": False}], None, ["junk", 7, None]):
            out = self.read(counted)
            self.assertEqual((out["applies"], out["holds"], out["final"], out["why"]), (False, True, True, None))
            self.assertEqual((out["gap"]["closes"], out["intents"]["sessions"], out["by_instance"]), (0, 0, []))

    def test_only_the_equity_closes_are_read(self):
        out = self.held()
        mixed = self.read([close(1), close(77, equity=False), {"pid": 5, "equity": False, "instance": "x", "day": "bad"}])
        self.assertEqual(close(1)["day"], DAYS[20])
        self.assertEqual(mixed, out)
        self.assertEqual((out["applies"], out["gap"]["closes"]), (True, 1))

    def test_the_whole_reading_when_everything_holds(self):
        out = self.held()
        self.assertEqual((out["applies"], out["holds"], out["final"], out["why"]), (True, True, True, None))
        self.assertEqual(out["gap"], {"closes": 1, "priced": 1, "unpriced": 0, "pending": 0, "mean_gap_bp": -3.0,
                                      "bound_bp": 15.0, "ok": True})
        self.assertEqual(out["intents"], {"instances": 1, "sessions": 20, "agreed": 20, "missing": 0, "unreadable": 0,
                                          "share": 1.0, "bound": 0.95, "ok": True, "disagreed": 0,
                                          "causes": {"bars": 0, "program": 0, "unknown": 0}})
        self.assertEqual(out["by_instance"], [{"instance": A, "sessions": 20, "agreed": 20, "missing": 0, "unreadable": 0}])


class TheGap(Reading):
    """Gap ok iff |mean(gap_bp)| <= 15.0 over the closes whose twin is final and priced: the SIZE, either way."""

    def test_a_mean_gap_of_plus_16_and_of_minus_16_both_fail(self):
        for gap in (16.0, -16.0):
            out = self.held(gaps=(gap,))
            self.assertEqual((out["gap"]["ok"], out["gap"]["mean_gap_bp"], out["holds"]), (False, gap, False), gap)
            self.assertTrue(out["final"], "a failed reading is a reading: final")
            self.assertIn("beyond the bound", out["why"])
            self.assertIs(out["intents"]["ok"], True)

    def test_the_bound_itself_holds_either_way(self):
        for gap in (15.0, -15.0, 0.0, 14.99, -14.99):
            self.assertIs(self.held(gaps=(gap,))["gap"]["ok"], True, gap)
        for gap in (15.01, -15.01):
            self.assertIs(self.held(gaps=(gap,))["gap"]["ok"], False, gap)

    def test_it_is_the_mean_that_is_read_not_each_close(self):
        out = self.held(gaps=(40.0, -20.0, 10.0))               # mean 10: inside, though one close is far outside
        self.assertEqual((out["gap"]["mean_gap_bp"], out["gap"]["ok"], out["gap"]["priced"]), (10.0, True, 3))
        out = self.held(gaps=(-40.0, -20.0, 12.0))              # mean -16
        self.assertEqual((out["gap"]["mean_gap_bp"], out["gap"]["ok"]), (-16.0, False))

    def test_the_mean_is_summed_exactly(self):
        # Ten gaps whose built-in sum is not their exact sum on Python 3.11; the mean is `math.fsum`'s on both.
        gaps = (0.1,) * 10 + (1e16, -1e16)
        self.assertEqual(self.held(gaps=gaps)["gap"]["mean_gap_bp"], round(1.0 / 12.0, 4))

    def test_no_priced_twin_does_not_hold(self):
        self.rows(A, (1,) * 20)
        out = self.read([close(1)])                              # no swarm store at all
        self.assertEqual((out["gap"]["ok"], out["gap"]["mean_gap_bp"], out["gap"]["pending"]), (None, None, 1))
        self.assertEqual((out["holds"], out["final"]), (False, False), "unmeasured never holds")
        self.assertIn("priced twin", out["why"])
        self.twins(eq_1={"status": "priced", "final": False, "gap_bp": 1.0})     # awaiting the morning audit
        out = self.read([close(1)])
        self.assertEqual((out["gap"]["priced"], out["gap"]["pending"], out["holds"], out["final"]), (0, 1, False, False))

    def test_a_final_twin_that_is_not_priced_is_counted_apart_and_is_final(self):
        self.twins(eq_1=priced(2.0), eq_2={"status": "no_bar", "final": True, "gap_bp": None},
                   eq_3={"status": "unpriceable", "final": True})
        self.rows(A, (1,) * 20)
        out = self.read([close(1), close(2), close(3)])
        self.assertEqual((out["gap"]["closes"], out["gap"]["priced"], out["gap"]["unpriced"], out["gap"]["pending"]),
                         (3, 1, 2, 0))
        self.assertEqual((out["gap"]["mean_gap_bp"], out["holds"], out["final"]), (2.0, True, True))

    def test_a_close_without_a_final_twin_is_pending_and_the_reading_is_not_final(self):
        self.twins(eq_1=priced(2.0))
        self.rows(A, (1,) * 20)
        out = self.read([close(1), close(2)])
        self.assertEqual((out["gap"]["priced"], out["gap"]["pending"]), (1, 1))
        self.assertEqual((out["holds"], out["final"]), (True, False), "it holds on what is priced, and is not final")
        self.assertIn("1 equity closes have no final twin yet", out["why"])

    def test_another_lots_record_is_not_this_closes(self):
        self.twins(eq_9=priced(-50.0))
        self.rows(A, (1,) * 20)
        out = self.read([close(1)])
        self.assertEqual((out["gap"]["priced"], out["gap"]["pending"]), (0, 1))


class TheIntents(Reading):
    """share = agreed / the counted sessions, less the unreadable ones; ok iff share >= 0.95."""

    def test_19_of_20_sessions_passes_and_18_of_20_fails(self):
        out = self.held(verdicts=(1,) * 19 + (0,))
        self.assertEqual((out["intents"]["agreed"], out["intents"]["sessions"], out["intents"]["share"],
                          out["intents"]["ok"], out["holds"], out["final"]), (19, 20, 0.95, True, True, True))
        out = self.held(verdicts=(1,) * 18 + (0, 0))
        self.assertEqual((out["intents"]["agreed"], out["intents"]["share"], out["intents"]["ok"], out["holds"]),
                         (18, 0.9, False, False))
        self.assertIn("18 of 20", out["why"])
        self.assertTrue(out["final"])

    def test_the_bound_at_other_counts(self):
        for agreed, total, ok in ((38, 40, True), (37, 40, False), (95, 100, True), (94, 100, False), (1, 1, True),
                                  (0, 1, False), (20, 21, True), (19, 21, False)):
            out = self.held(verdicts=(1,) * agreed + (0,) * (total - agreed))
            self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["ok"]),
                             (total, agreed, ok), (agreed, total))

    def test_the_sessions_run_from_the_first_row_to_the_session_before_the_last_counted_exit(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(1.0))
        self.rows(A, (1,) * 30, first=2)                         # its first decision session is DAYS[2]
        out = self.read([close(1, opened=DAYS[3], day=DAYS[6]), close(2, opened=DAYS[7], day=DAYS[11])])
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"]), (9, 9), "DAYS[2] .. DAYS[10]")
        out = self.read([close(1, opened=DAYS[3], day=DAYS[6])])
        self.assertEqual(out["intents"]["sessions"], 4, "DAYS[2] .. DAYS[5]: a later row is not a counted session")

    def test_a_missing_row_is_not_agreed_and_the_reading_is_not_final(self):
        out = self.held(verdicts=(1,) * 19 + ("-",))
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["missing"],
                          out["intents"]["share"]), (20, 19, 1, 0.95))
        self.assertEqual((out["intents"]["ok"], out["holds"], out["final"]), (True, True, False))
        self.assertIn("1 counted sessions have no twin row yet", out["why"])
        out = self.held(verdicts=(1,) * 17 + ("-", "-", "-"))
        self.assertEqual((out["intents"]["missing"], out["intents"]["ok"], out["holds"], out["final"]),
                         (3, False, False, False))
        self.assertEqual(out["intents"]["disagreed"], 0, "a missing session is not a disagreement: it is not measured")

    def test_a_hole_inside_the_rows_is_missing_too(self):
        out = self.held(verdicts=(1, 1, "-", 1) + (1,) * 16)
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["missing"]), (20, 19, 1))

    def test_unreadable_sessions_are_left_out_of_the_share_and_counted(self):
        out = self.held(verdicts=(1,) * 15 + (None, None, None, "retired", 0))
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["unreadable"],
                          out["intents"]["missing"]), (16, 15, 4, 0))
        self.assertEqual((out["intents"]["share"], out["intents"]["ok"], out["final"]), (0.9375, False, True))
        out = self.held(verdicts=(1,) * 19 + ("retired",))
        self.assertEqual((out["intents"]["sessions"], out["intents"]["share"], out["intents"]["unreadable"],
                          out["holds"], out["final"]), (19, 1.0, 1, True, True))
        self.assertEqual(out["by_instance"][0]["unreadable"], 1)

    def test_a_disagreement_is_counted_with_its_cause_and_the_rule_does_not_change(self):
        out = self.held(verdicts=(1,) * 15 + ("bars", "bars", "program", "unknown", 1))
        self.assertEqual((out["intents"]["disagreed"], out["intents"]["causes"]),
                         (4, {"bars": 2, "program": 1, "unknown": 1}))
        self.assertEqual((out["intents"]["agreed"], out["intents"]["sessions"], out["intents"]["ok"], out["holds"]),
                         (16, 20, False, False), "a session whose bars differed still counts as not agreed")
        one = self.held(verdicts=(1,) * 19 + ("bars",))
        self.assertEqual((one["intents"]["disagreed"], one["intents"]["causes"]["bars"], one["intents"]["ok"],
                          one["holds"]), (1, 1, True, True))
        self.assertEqual(sum(out["intents"]["causes"].values()), out["intents"]["disagreed"])

    def test_a_cause_the_store_does_not_name_is_unknown(self):
        db = self.forward()
        db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, at) VALUES(?,?,1,'[]','[]',0,1.0)",
                   (A, DAYS[0]))
        db.commit()
        db.close()
        self.twins(eq_1=priced(1.0))
        out = self.read([close(1, day=DAYS[1], opened=DAYS[0])])
        self.assertEqual(out["intents"]["causes"], {"bars": 0, "program": 0, "unknown": 1})

    def test_an_instance_with_no_row_yet_has_every_session_missing(self):
        self.twins(eq_1=priced(1.0))
        self.forward().close()                                   # the store is there; no twin night has run
        out = self.read([close(1, opened=DAYS[4], day=DAYS[8])])
        self.assertEqual((out["intents"]["sessions"], out["intents"]["missing"], out["intents"]["agreed"],
                          out["intents"]["share"]), (5, 5, 0, 0.0), "from the session before its first lot's entry")
        self.assertEqual((out["intents"]["ok"], out["holds"], out["final"]), (False, False, False))

    def test_instances_are_pooled_and_listed(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(-1.0))
        self.rows(A, (1,) * 20)
        self.rows(B, (1,) * 8 + (0, 0), first=5)
        out = self.read([close(1), close(2, B, opened=DAYS[6], day=DAYS[15])])
        self.assertEqual(out["by_instance"], [{"instance": A, "sessions": 20, "agreed": 20, "missing": 0, "unreadable": 0},
                                              {"instance": B, "sessions": 10, "agreed": 8, "missing": 0, "unreadable": 0}])
        self.assertEqual((out["intents"]["instances"], out["intents"]["sessions"], out["intents"]["agreed"],
                          out["intents"]["share"], out["intents"]["ok"]), (2, 30, 28, round(28 / 30, 6), False))
        self.assertEqual(out["gap"]["mean_gap_bp"], 0.0)
        only_a = self.read([close(1)])
        self.assertEqual((only_a["intents"]["instances"], only_a["intents"]["ok"]), (1, True),
                         "another instance's rows are not this checkpoint's")

    def test_a_close_whose_days_cannot_be_read_is_unmeasured(self):
        self.twins(eq_1=priced(1.0))
        self.rows(A, (1,) * 20)
        for bad in ({"day": None}, {"day": "soon"}, {"day": ""}, {"day": 7}):
            out = self.read([{**close(1), **bad}])
            self.assertEqual((out["intents"]["missing"], out["holds"], out["final"]), (1, False, False), bad)


class Unmeasured(Reading):
    """A missing or unreadable store is never a raise and never a hold."""

    COUNTED = [close(1), close(2, B, opened=DAYS[3], day=DAYS[9])]

    def assert_unmeasured(self, out, *, sessions: int):
        self.assertEqual((out["applies"], out["holds"], out["final"]), (True, False, False))
        self.assertEqual((out["intents"]["sessions"], out["intents"]["missing"], out["intents"]["agreed"]),
                         (sessions, sessions, 0))
        self.assertIsInstance(out["why"], str)

    def test_no_store_at_all(self):
        out = self.read(self.COUNTED)
        # A: from the session before DAYS[1] through DAYS[19]; B: from DAYS[2] through DAYS[8].
        self.assert_unmeasured(out, sessions=20 + 7)
        self.assertEqual((out["gap"]["pending"], out["gap"]["ok"]), (2, None))
        self.assertIn("cannot be read", out["why"])

    def test_no_forward_store_with_the_twins_priced(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(2.0))
        out = self.read(self.COUNTED)
        self.assert_unmeasured(out, sessions=27)
        self.assertEqual((out["gap"]["ok"], out["gap"]["mean_gap_bp"]), (True, 1.5), "the gap is read; the intents are not")

    def test_no_swarm_store_with_the_sessions_written(self):
        self.rows(A, (1,) * 20)
        self.rows(B, (1,) * 7, first=2)
        out = self.read(self.COUNTED)
        self.assertEqual((out["holds"], out["final"], out["gap"]["pending"], out["intents"]["ok"]), (False, False, 2, True))

    def test_a_forward_store_that_cannot_be_opened_or_read(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(2.0))
        (self.root / forward_db.DB).write_text("this is not a database")
        self.assert_unmeasured(self.read(self.COUNTED), sessions=27)
        (self.root / forward_db.DB).unlink()
        empty = sqlite3.connect(self.root / forward_db.DB)       # a database with no forward table in it
        empty.execute("CREATE TABLE other (x)")
        empty.commit()
        empty.close()
        self.assert_unmeasured(self.read(self.COUNTED), sessions=27)

    def test_package_as_stub_or_any_raise_of_the_opener_is_unmeasured(self):
        self.twins(eq_1=priced(1.0), eq_2=priced(2.0))
        self.rows(A, (1,) * 20)
        for error in (NotImplementedError("A: league/ops/forward_db.py open_db"), sqlite3.OperationalError("locked"),
                      RuntimeError("fake"), PermissionError("fake")):
            with mock.patch.object(forward_db, "open_db", side_effect=error):
                self.assert_unmeasured(self.read(self.COUNTED), sessions=27)

    def test_a_swarm_store_that_cannot_be_read_leaves_every_twin_pending(self):
        self.rows(A, (1,) * 20)
        (self.root / forward_twins.SWARM_DB).write_text("this is not a database")
        out = self.read([close(1)])
        self.assertEqual((out["gap"]["pending"], out["holds"], out["final"]), (1, False, False))
        (self.root / forward_twins.SWARM_DB).unlink()
        self.twins()
        db = sqlite3.connect(self.root / forward_twins.SWARM_DB)
        db.execute("UPDATE kv SET value='[1, 2' WHERE key=?", (twins.EQUITY_TWINS_KEY,))
        db.commit()
        db.close()
        self.assertEqual(self.read([close(1)])["gap"]["pending"], 1)

    def test_the_stores_are_opened_read_only(self):
        from league.ops import guard

        self.twins(eq_1=priced(1.0))
        self.rows(A, (1,) * 20)
        before = [(self.root / name).read_bytes() for name in (forward_db.DB, forward_twins.SWARM_DB)]
        with guard.readonly():                                   # a writable open anywhere would be refused
            out = self.read([close(1)])
        self.assertTrue(out["holds"])
        self.assertEqual([(self.root / name).read_bytes() for name in (forward_db.DB, forward_twins.SWARM_DB)], before)


class WhatTheDoneMeterReads(Reading):
    def test_the_meters_wrapper_reads_holds_final_and_why_as_they_are(self):
        # The spec's 11.5(a) `a14_of` (package C's patch) keeps this reading's keys and reads three of them strictly.
        for out in (self.held(), self.held(gaps=(16.0,)), self.held(verdicts=(1,) * 19 + ("-",)), self.read([close(3)])):
            wrapped = {**out, "applies": out.get("applies") is not False, "holds": out.get("holds") is True,
                       "final": out.get("final") is True, "why": out.get("why")}
            self.assertEqual(wrapped, out)

    def test_no_text_of_the_reading_holds_a_figure(self):
        # The `why` rides the dlane report beside the P&L: ids, counts and dates only (no decimal, no "bp", no "%").
        cases = [self.held(), self.held(gaps=(16.37,)), self.held(verdicts=(1,) * 17 + (0, 0, "-")),
                 self.read([close(1), close(2, B)]), self.read([close(9)])]
        for out in cases:
            for text in filter(None, [out["why"]]):
                self.assertNotRegex(text, r"\d\.\d|bp|%", text)
        self.assertTrue(any(out["why"] for out in cases))

    def test_the_reading_is_the_same_twice(self):
        self.assertEqual(self.held(), self.read([close(1)]))
        self.assertEqual(self.read([close(1)]), self.read([close(1)]))


class FromTheNightToTheReading(fx.WithAStore):
    """D12's rows as `finish` writes them (a fake of B's Shadow on E1's real engine), read back by D13."""

    def setUp(self):
        super().setUp()
        self.db = fx.fake_open_db(self.root)            # the forward store in a file, as the Done meter opens it
        self.addCleanup(self.db.close)
        self.db.execute("INSERT INTO fwd_engines(label, at) VALUES('fake-engine+0+fwd-1', 1.0)")
        self.db.commit()

    def priced_twins(self, lids, gap=-2.0):
        db = sqlite3.connect(self.root / forward_twins.SWARM_DB)
        db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)",
                   (twins.EQUITY_TWINS_KEY, json.dumps({f"eq:{lid}": priced(gap) for lid in lids})))
        db.commit()
        db.close()

    def counted(self, book, iid, *, last: str):
        lots = [dict(zip(("lid", "opened_day", "exit_day"), row)) for row in book.db.execute(
            "SELECT lid, opened_day, exit_day FROM eq_lots WHERE instance=? AND status='closed' AND exit_day<=? "
            "ORDER BY lid", (iid, last))]
        self.priced_twins([lot["lid"] for lot in lots])
        return [close(lot["lid"], iid, opened=lot["opened_day"], day=lot["exit_day"]) for lot in lots]

    def test_a_book_that_decided_as_its_twin_holds(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", fx.OVERNIGHT)
        self.night("2026-10-23")
        counted = self.counted(book, iid, last="2026-10-22")
        out = forward_twins.a14_reading(self.root, counted)
        shape(self, out)
        # The first decision session is Oct 12; the last counted exit is Oct 22: Oct 12 .. Oct 21 is eight sessions.
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["missing"]), (8, 8, 0))
        self.assertEqual((out["holds"], out["final"], out["why"]), (True, True, None))
        self.assertEqual(out["gap"]["priced"], len(counted))

    def test_the_night_has_not_caught_up_with_the_checkpoint(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", fx.OVERNIGHT)
        self.night("2026-10-20")                       # rows through Oct 19
        out = forward_twins.a14_reading(self.root, self.counted(book, iid, last="2026-10-22"))
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["missing"]), (8, 6, 2))
        self.assertEqual((out["holds"], out["final"]), (False, False))
        self.night("2026-10-22")
        out = forward_twins.a14_reading(self.root, self.counted(book, iid, last="2026-10-22"))
        self.assertEqual((out["intents"]["missing"], out["holds"], out["final"]), (0, True, True))

    def test_a_reloaded_clock_fails_the_bound_and_says_how_many(self):
        book, iid, pid, run = self.live_instance("fake-clock@1", fx.CLOCK, reload_at=4)
        self.night("2026-10-30")
        out = forward_twins.a14_reading(self.root, self.counted(book, iid, last="2026-10-29"))
        shape(self, out)
        self.assertGreater(out["intents"]["disagreed"], 0)
        self.assertEqual(out["intents"]["causes"]["unknown"], out["intents"]["disagreed"])
        self.assertEqual((out["intents"]["ok"], out["holds"], out["final"]), (False, False, True))

    def test_a_retired_instances_last_session_is_left_out_and_the_reading_is_final(self):
        book, iid, pid, run = self.live_instance("fake-overnight@1", fx.OVERNIGHT, retired=fx.at("2026-10-20", 16, 22),
                                                 mirror_until="2026-10-19")
        book.db.execute("DELETE FROM eq_lots WHERE opened_day>?", ("2026-10-20",))
        book.db.commit()
        self.night("2026-10-23")
        counted = self.counted(book, iid, last="2026-10-21")     # its last lot: the House's exit at Oct 21's open
        self.assertEqual(max(c["day"] for c in counted), "2026-10-21")
        out = forward_twins.a14_reading(self.root, counted)
        shape(self, out)
        # Oct 12 .. Oct 20 are D13's sessions; Oct 20 is the session it was retired at: unreadable, left out.
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["unreadable"],
                          out["intents"]["missing"]), (6, 6, 1, 0))
        self.assertEqual((out["holds"], out["final"]), (True, True))


if __name__ == "__main__":
    unittest.main()
