"""Release E3, package B (league/ops/forward_audit.py): the morning marks of the forward record and the registry's
chain check. A bar the equity book's morning re-fetch found different (`eq_bars.audit` "mismatch") marks that day for
every program whose NEEDS hold the symbol and whose forward days hold the day, once; a marked day leaves the counted
days and its row stays; a control is never marked; the chain is read whole each morning, and a broken one is an event
and a warning that names ids and counts only; a book that cannot be read marks nobody.

The live book here is an empty SQLite file made from E1's own DDL (league/equity/live.py `SCHEMA`) with invented rows;
every program, registry row and day is invented. The `forward_db` functions (package A's) are faked only while they
are still step 0's stubs: league/tests/test_forward_shadow.py, THE FAKES."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from league.equity import live as eq_live
from league.equity import schedule
from league.ops import forward_audit, forward_db
from league.ops.context import Context
from league.tests import test_forward_shadow as fx

FWD, BEFORE = fx.FWD, fx.BEFORE
ON_QQQ = fx.ALWAYS.replace('"SPY"', '"QQQ"')


def morning(day: dt.date) -> float:
    """09:05 New York time on `day`: when the job runs (after the book's 08:30 re-fetch, before the open)."""
    return dt.datetime.combine(day, dt.time(9, 5), schedule.NY).timestamp()


class Audit(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="eqe3-audit-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        fx.install(self)
        self.t = morning(FWD[5])
        self.mode("record")
        self.db = forward_db.open_db(self.root)
        self.addCleanup(self.db.close)

    def mode(self, mode: str) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"forward": {"mode": mode}}}))

    def ctx(self) -> Context:
        return Context("forward_audit", root=self.root, due_at=self.t, clock=lambda: self.t, config={},
                       settings_value={})

    def book(self, *bars: tuple[dt.date, str, str, str | None]) -> None:
        """The live book with these `eq_bars` rows: (day, symbol, adjustment, audit)."""
        db = sqlite3.connect(self.root / forward_audit.LIVE_DB)
        try:
            db.executescript(eq_live.SCHEMA)
            for day, symbol, adjustment, audit in bars:
                db.execute("INSERT OR REPLACE INTO eq_bars(day, symbol, adjustment, o, h, l, c, v, fetched_at, sha, "
                           "audit) VALUES (?,?,?,'1','1','1','1','1',?,'an invented sha',?)",
                           (day.isoformat(), symbol, adjustment, self.t, audit))
            db.commit()
        finally:
            db.close()

    def marks(self, pid: int | None = None) -> list[tuple[int, str]]:
        return [(e["pid"], e["day"]) for e in forward_db.events(self.db, "audit_mismatch", pid=pid)]

    def count(self, kind: str) -> int:
        return len(forward_db.events(self.db, kind))


class TheMarks(Audit):
    def test_a_mismatched_bar_marks_every_program_that_holds_it_once(self):
        on_spy = fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)             # in from FWD[0]
        both = fx.register(self.db, "flip@1", fx.FLIPPER, first_close=FWD[3])                # SPY and QQQ, from FWD[4]
        on_qqq = fx.register(self.db, "qqq@1", ON_QQQ, first_close=BEFORE, reason="train_fail")
        stopped = fx.register(self.db, "stopped@1", fx.ALWAYS, first_close=BEFORE)
        forward_db.tag(self.db, stopped, "stopped", f"cap:{FWD[1].isoformat()}", at=self.t)
        self.db.commit()
        self.book((FWD[3], "SPY", "raw", "mismatch"), (FWD[3], "SPY", "all", "mismatch"),     # one bar, two rows
                  (FWD[3], "QQQ", "raw", "ok"), (FWD[3], "QQQ", "all", "ok"),
                  (FWD[4], "QQQ", "all", "mismatch"), (FWD[2], "IWM", "raw", "mismatch"),     # nobody holds IWM
                  (FWD[2], "SPY", "raw", None))
        receipt = forward_audit.run(self.ctx())
        self.assertEqual((receipt["marked"], receipt["marks"], receipt["mismatched"]), (4, "ok", 3))
        # SPY of FWD[3]: its holders whose forward days hold the day (the one in from FWD[4] has none there), stopped
        # or not. QQQ of FWD[4]: both of its holders.
        self.assertEqual(sorted(self.marks()), sorted([(on_spy, FWD[3].isoformat()), (stopped, FWD[3].isoformat()),
                                                       (both, FWD[4].isoformat()), (on_qqq, FWD[4].isoformat())]))
        (event,) = forward_db.events(self.db, "audit_mismatch", pid=on_spy)
        self.assertEqual((event["payload"]["symbol"], "why" in event["payload"]), ("SPY", True))
        # The next mornings read the same rows again: an event is written once a (pid, day).
        self.t = morning(FWD[6])
        self.assertEqual(forward_audit.run(self.ctx())["marked"], 0)
        self.book((FWD[5], "SPY", "raw", "mismatch"))
        self.t = morning(FWD[7])
        self.assertEqual(forward_audit.run(self.ctx())["marked"], 3)
        self.assertEqual(len(self.marks()), 7)
        self.assertEqual(self.ctx().alerts, [])

    def test_a_marked_day_leaves_the_counted_days_and_its_row_stays(self):
        pid = fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        engine, _ = forward_db.engine_id(self.db, "an invented engine", at=self.t)
        for day in FWD[:5]:
            self.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, entries, exits, status, at, bars) "
                            "VALUES (?,?,?,0.001,0.5,0.0,0.0005,0,0,'ok',?,?)",
                            (pid, day.isoformat(), engine, self.t, "0" * 16))
        self.db.commit()
        self.book((FWD[2], "SPY", "raw", "mismatch"))
        self.assertEqual(forward_audit.run(self.ctx())["marked"], 1)
        counted = [row["day"] for row in forward_db.counted_days(self.db, pid, engine=engine)]
        self.assertEqual(counted, [d.isoformat() for d in FWD[:5] if d != FWD[2]])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0], 5)

    def test_a_program_is_marked_before_its_row_comes(self):
        # A program left stale the night before has no row for the day yet: the mark is there when the row is written.
        pid = fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        self.book((FWD[4], "SPY", "all", "mismatch"))
        self.assertEqual(forward_audit.run(self.ctx())["marked"], 1)
        self.assertEqual(self.marks(pid), [(pid, FWD[4].isoformat())])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_days").fetchone()[0], 0)

    def test_a_control_is_never_marked(self):
        control = fx.register_control(self.db, "index", 40, fx.SYMBOLS, first_close=BEFORE)
        self.book((FWD[3], "SPY", "raw", "mismatch"), (FWD[3], "QQQ", "raw", "mismatch"))
        receipt = forward_audit.run(self.ctx())
        self.assertEqual((receipt["marked"], receipt["mismatched"], self.marks(control)), (0, 2, []))


class TheChain(Audit):
    def test_a_chain_that_holds_is_one_chain_ok_a_morning(self):
        fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        last = fx.register(self.db, "flip@1", fx.FLIPPER, first_close=FWD[1])
        head = self.db.execute("SELECT row_hash FROM fwd_registry WHERE pid=?", (last,)).fetchone()[0]
        ctx = self.ctx()
        receipt = forward_audit.run(ctx)
        self.assertEqual((receipt["chain_ok"], receipt["rows"], receipt["head"], receipt["marks"]),
                         (True, 2, head, "no book"))
        (event,) = forward_db.events(self.db, "chain_ok")
        self.assertEqual((event["pid"], event["payload"]["rows"], event["payload"]["head"]), (None, 2, head))
        self.assertEqual((self.count("chain_broken"), ctx.alerts), (0, []))
        self.t = morning(FWD[6])
        forward_audit.run(self.ctx())
        self.assertEqual(self.count("chain_ok"), 2)

    def test_an_empty_registry_holds(self):
        receipt = forward_audit.run(self.ctx())
        self.assertEqual((receipt["chain_ok"], receipt["rows"], receipt["head"]), (True, 0, forward_db.GENESIS))

    def test_a_tampered_alpha_is_chain_broken_and_a_warning_that_names_ids_only(self):
        first = fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        fx.register(self.db, "flip@1", fx.FLIPPER, first_close=FWD[1])
        # Someone with the file drops the trigger and gives an E3 row the larger alpha (D2 forbids exactly this).
        self.db.execute("DROP TRIGGER fwd_registry_no_update")
        self.db.execute("UPDATE fwd_registry SET alpha_f='0.12' WHERE pid=?", (first,))
        self.db.commit()
        ctx = self.ctx()
        receipt = forward_audit.run(ctx)
        self.assertEqual((receipt["chain_ok"], receipt["rows"]), (False, 2))
        (event,) = forward_db.events(self.db, "chain_broken")
        self.assertEqual((event["payload"]["first_bad"], event["payload"]["rows"]), (first, 2))
        self.assertEqual(self.count("chain_ok"), 0)
        (alert,) = ctx.alerts
        self.assertEqual(alert["level"], "warning")
        self.assertIn(f"pid {first}", alert["text"])
        self.assertIn("2 rows", alert["text"])
        self.assertNotRegex(alert["text"], r"\d+\.\d+|%|\bbp\b")              # ids, counts and dates only (T8)


class TheJob(Audit):
    def test_it_skips_when_off_and_with_no_forward_store(self):
        self.mode("off")
        self.assertEqual(forward_audit.run(self.ctx()), {"status": "skipped", "why": "elane.forward.mode is off"})
        self.assertEqual(self.count("chain_ok"), 0)
        other = Path(tempfile.mkdtemp(prefix="eqe3-audit-none-"))
        self.addCleanup(shutil.rmtree, other, True)
        (other / "swarm.json").write_text(json.dumps({"elane": {"forward": {"mode": "record"}}}))
        ctx = Context("forward_audit", root=other, due_at=self.t, clock=lambda: self.t, config={}, settings_value={})
        self.assertEqual(forward_audit.run(ctx)["status"], "skipped")
        self.assertFalse((other / forward_db.DB).exists())                     # a morning job never makes the store

    def test_a_book_that_cannot_be_read_marks_nobody_and_the_chain_is_still_checked(self):
        pid = fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        (self.root / forward_audit.LIVE_DB).write_bytes(b"not a database, " * 64)
        ctx = self.ctx()
        receipt = forward_audit.run(ctx)
        self.assertEqual((receipt["marked"], receipt["marks"], receipt["chain_ok"], receipt["rows"]),
                         (0, "unread", True, 1))
        self.assertEqual((self.marks(pid), self.count("chain_ok")), ([], 1))
        (alert,) = ctx.alerts
        self.assertEqual(alert["level"], "warning")
        self.assertNotRegex(alert["text"], r"\d+\.\d+|%|\bbp\b")

    def test_a_book_with_no_bars_table_has_nothing_to_mark(self):
        fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        sqlite3.connect(self.root / forward_audit.LIVE_DB).close()
        db = sqlite3.connect(self.root / forward_audit.LIVE_DB)
        db.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY)")
        db.commit()
        db.close()
        ctx = self.ctx()
        receipt = forward_audit.run(ctx)
        self.assertEqual((receipt["marked"], receipt["marks"], receipt["mismatched"], ctx.alerts), (0, "ok", 0, []))

    def test_the_book_is_read_and_never_written(self):
        fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        self.book((FWD[3], "SPY", "raw", "mismatch"))
        before = (self.root / forward_audit.LIVE_DB).read_bytes()
        self.assertEqual(forward_audit.mismatches(self.root / forward_audit.LIVE_DB), [(FWD[3].isoformat(), "SPY")])
        forward_audit.run(self.ctx())
        self.assertEqual((self.root / forward_audit.LIVE_DB).read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith("live.sqlite")),
                         ["live.sqlite"])                                       # no journal left beside it

    def test_the_receipt_is_counts_and_verdicts(self):
        fx.register(self.db, "always@1", fx.ALWAYS, first_close=BEFORE)
        self.book((FWD[3], "SPY", "raw", "mismatch"))
        receipt: dict[str, Any] = forward_audit.run(self.ctx())
        self.assertEqual(set(receipt), {"marked", "marks", "mismatched", "chain_ok", "rows", "head"})
        self.assertFalse([v for v in receipt.values() if isinstance(v, float)])
        json.dumps(receipt)


if __name__ == "__main__":
    unittest.main()
