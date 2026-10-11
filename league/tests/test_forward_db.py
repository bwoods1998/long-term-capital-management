"""Release E3, the forward record's store (league/ops/forward_db.py): the settings and their bounds; D1 and D2 on
synthetic times (a minute either side of a close, a weekend, a holiday, a half day, a time before the look cap); the
engine label; the store's creation (0600, the schema, the forward screen's shape pinned once and never overwritten);
the registry's hash chain (append, verify, the genesis, a tampered column, code, route or alpha found, a row taken out,
what a row is refused for); the event log's `once`; the kv, the engines, the tags (stopped, resumed, suspect), the
counted and the stored days; and T9, `AppendOnly`: UPDATE and DELETE abort on every forward table but `fwd_kv`.
Every program, family, day and number here is invented; no market data is read."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import EQUITY_ENGINE_VERSION, config, results, schedule
from league.ops import forward_db as F

#: An invented program text (the registry freezes text; nothing here runs it).
CODE = 'NEEDS = {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 2}\nPARAMS = {}\n\n\ndef decide(ctx):\n    return []\n'


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def at(day: dt.date, hour: int, minute: int = 0) -> float:
    """Epoch seconds of a New York wall time."""
    return dt.datetime.combine(day, dt.time(hour, minute), schedule.NY).timestamp()


def sessions_from(first: dt.date, n: int) -> list[dt.date]:
    """`n` sessions from `first` on (the House's calendar; never a literal list)."""
    out, day = [], first
    while len(out) < n:
        if schedule.is_session(day):
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def registry_row(key: str = "fake-family@1", *, created: float | None = None, registered: float | None = None,
                 reason: str = "train_fail", code: str = CODE, evidence: str | None = None, **over) -> dict:
    """A registry row as `append_registry` takes it: an invented program judged on the bar (a control with `reason`
    "control"), its forward window computed from `created` by D2."""
    created = at(F.t0(), 10) if created is None else created
    registered = created + 60.0 if registered is None else registered
    close = F.first_close(created)
    control = reason == "control"
    family, _, version = key.partition("@")
    row = {"key": key, "family": None if control else family, "version": None if control else int(version or 1),
           "lane": "control" if control else "equity", "reason": reason, "ugroup": "index",
           "lineage": key if control else f"equity:{family}", "code": code, "params": {},
           "needs": {"symbols": ["SPY"], "history": 1, "max_hold_sessions": 2}, "program_sha": sha(code),
           "run_sha": sha(code) if control else sha(sha(code) + "{}"), "author": "house" if control else "fake:author",
           "created_at": registered if control else created,
           "evidence": evidence or ("registry" if control else "event:7"), "first_close": close,
           "first_day": F.first_day(close), "registered_at": registered,
           "route": F.CONTROL_ROUTE if control else F.E3_ROUTE, "alpha_f": F.CONTROL_ALPHA_F if control else F.E3_ALPHA_F}
    row.update(over)
    return row


def memory(case: unittest.TestCase) -> sqlite3.Connection:
    """The in-memory database the packages test on (league/ops/E3_INTERFACES.md section 2)."""
    db = sqlite3.connect(":memory:")
    case.addCleanup(db.close)
    db.row_factory = sqlite3.Row
    db.executescript(F.SCHEMA)
    return db


def store(case: unittest.TestCase) -> tuple[Path, sqlite3.Connection]:
    """A forward store on disk, as the House's jobs open it."""
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    db = F.open_db(tmp.name)
    case.addCleanup(db.close)
    return Path(tmp.name), db


def day_row(db: sqlite3.Connection, pid: int, day: str, engine: int, *, status: str = "ok", r: float = 0.0,
            written: float = 1.0) -> None:
    db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) VALUES(?, ?, ?, ?, 0.0, 0.0, "
               "0, 0, ?, ?)", (pid, day, engine, r, status, written))
    db.commit()


class Settings(unittest.TestCase):
    def test_the_code_default_is_off_and_every_key_is_there(self):
        for raw in (None, {}, {"elane": None}, {"elane": {"forward": "record"}}, {"elane": {"forward": []}}, 7, "x"):
            self.assertEqual(F.cfg(raw), F.DEFAULTS, raw)
            self.assertEqual(F.mode(raw), "off", raw)
        self.assertIsNot(F.cfg(None), F.DEFAULTS)

    def test_the_policy_values_are_read(self):
        block = {"mode": "record", "controls_per_group": 50, "cpu_seconds_night": 1800, "run_budget_seconds": 120,
                 "stop_after_sessions": 500, "stop_fail_after_sessions": 250, "neff_max_members": 1500,
                 "fill_minutes": False, "twins": False}
        self.assertEqual(F.cfg({"elane": {"forward": block}}), block)
        self.assertEqual(F.mode({"elane": {"forward": block}}), "record")

    def test_every_value_is_held_inside_its_bound(self):
        for key, (low, high) in F.BOUNDS.items():
            for value in (low, high):
                self.assertEqual(F.cfg({"elane": {"forward": {key: value}}})[key], value, key)
            # Outside its bound it is held at the bound it passed, never past it.
            for value, held in ((low - 1, low), (-1, low), (-10 ** 9, low), (high + 1, high), (10 ** 9, high),
                                (float(high + 7), high)):
                self.assertEqual(F.cfg({"elane": {"forward": {key: value}}})[key], held, (key, value))
            # What is no whole number is malformed: the code default.
            for value in (float("nan"), float("inf"), -float("inf"), "50", None, True, False, [low], {"n": low},
                          low + 0.5):
                self.assertEqual(F.cfg({"elane": {"forward": {key: value}}})[key], F.DEFAULTS[key], (key, value))
            self.assertEqual(F.cfg({"elane": {"forward": {key: float(low)}}})[key], low)
            self.assertIsInstance(F.cfg({"elane": {"forward": {key: float(low)}}})[key], int)

    def test_a_malformed_switch_is_its_default(self):
        for value in ("rank", "route", "on", "RECORD", True, 1, None, ["record"]):
            self.assertEqual(F.mode({"elane": {"forward": {"mode": value}}}), "off", value)
        for key in ("fill_minutes", "twins"):
            for value in (0, 1, "false", None):
                self.assertIs(F.cfg({"elane": {"forward": {key: value}}})[key], True, (key, value))
            self.assertIs(F.cfg({"elane": {"forward": {key: False}}})[key], False)

    def test_the_forward_switch_is_its_own(self):
        # A retired family keeps accruing forward days: the forward mode does not read `elane.mode`.
        self.assertEqual(F.mode({"elane": {"mode": "off", "forward": {"mode": "record"}}}), "record")
        self.assertEqual(F.mode({"elane": {"mode": "gate"}}), "off")


class ForwardDays(unittest.TestCase):
    """D1 and D2, on the House's own calendar."""

    def test_t0_is_the_session_after_the_look_cap(self):
        self.assertEqual(F.t0(), schedule.next_session(config.LOOK_CAP))
        self.assertGreater(F.t0(), config.LOOK_CAP)
        self.assertTrue(schedule.is_session(F.t0()))

    def test_a_minute_either_side_of_the_close(self):
        day = sessions_from(F.t0(), 3)[1]
        self.assertFalse(schedule.moments(day).early)
        self.assertEqual(F.first_close(at(day, 15, 59)), day)
        self.assertEqual(F.first_day(F.first_close(at(day, 15, 59))), schedule.next_session(day))
        after = F.first_close(at(day, 16, 1))
        self.assertEqual(after, schedule.next_session(day))
        self.assertEqual(F.first_day(after), schedule.next_session(after))
        # The close itself is not after the code existed: a program written at 16:00:00 first decides a session later.
        self.assertEqual(F.first_close(schedule.moments(day).close_at), schedule.next_session(day))
        self.assertEqual(F.first_close(schedule.moments(day).close_at - 0.001), day)

    def test_a_weekend(self):
        saturday = next(d for d in (F.t0() + dt.timedelta(days=i) for i in range(1, 9)) if d.weekday() == 5)
        monday = schedule.next_session(saturday)
        for when in (at(saturday, 3), at(saturday, 12), at(saturday + dt.timedelta(days=1), 23, 59)):
            self.assertEqual(F.first_close(when), monday)
            self.assertEqual(F.first_day(F.first_close(when)), schedule.next_session(monday))

    def test_a_holiday(self):
        holiday = next(d for d in (F.t0() + dt.timedelta(days=i) for i in range(1, 400))
                       if d.weekday() < 5 and not schedule.is_session(d))
        self.assertEqual(F.first_close(at(holiday, 10)), schedule.next_session(holiday))

    def test_a_half_day_closes_at_one(self):
        half = next(d for d in (F.t0() + dt.timedelta(days=i) for i in range(1, 400))
                    if schedule.is_session(d) and schedule.moments(d).early)
        self.assertEqual(F.first_close(at(half, 12, 59)), half)
        self.assertEqual(F.first_close(at(half, 13, 1)), schedule.next_session(half))
        self.assertEqual(F.first_close(at(half, 15, 59)), schedule.next_session(half))

    def test_no_window_opens_before_the_look_cap(self):
        # A version written long before E3 first decides at the look cap's close and trades the session after: t0.
        for when in (0.0, at(dt.date(2020, 3, 16), 10), at(config.LOOK_CAP, 9)):
            self.assertEqual(F.first_close(when), config.LOOK_CAP)
            self.assertEqual(F.first_day(F.first_close(when)), F.t0())
        self.assertGreater(F.first_close(at(config.LOOK_CAP, 16, 1)), config.LOOK_CAP)
        for n, day in enumerate(sessions_from(F.t0(), 30)):
            for hour in (3, 10, 17, 23):
                close = F.first_close(at(day, hour))
                self.assertGreater(schedule.moments(close).close_at, at(day, hour), (day, hour))
                self.assertGreaterEqual(F.first_day(close), F.t0(), (day, hour))
                self.assertGreater(F.first_day(close), close)

    def test_a_time_that_is_no_time_is_refused(self):
        for bad in (None, "2026-10-12", float("nan"), float("inf"), True, 1e18, 1e300, -1e300):
            with self.assertRaises(ValueError, msg=bad):
                F.first_close(bad)

    def test_the_engine_label(self):
        from league.swarm import evaluator

        label = F.fwd_engine()
        self.assertEqual(label, f"{EQUITY_ENGINE_VERSION}+{evaluator.equity_fingerprint()[:12]}+{F.FWD_SERIES}")
        with mock.patch.object(evaluator, "equity_fingerprint", lambda: "f" * 64):
            self.assertEqual(F.fwd_engine(), f"{EQUITY_ENGINE_VERSION}+{'f' * 12}+fwd-1")
            self.assertNotEqual(F.fwd_engine(), label, "a change to an evidence module opens a new labelled series")


class TheStore(unittest.TestCase):
    def test_a_new_store_is_private_and_pins_the_forward_screens_shape(self):
        root, db = store(self)
        path = root / F.DB
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual({r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name "
                                                        "LIKE 'fwd_%'")}, set(F.TABLES))
        self.assertEqual(F.kv_get(db, "fgs_prereg"), F.FGS_SHA)
        (prereg,) = F.events(db, "prereg")
        self.assertEqual(prereg["payload"]["fgs_sha"], F.FGS_SHA)
        self.assertEqual(prereg["payload"]["fgs"], json.loads(results.canonical(F.FGS)))
        self.assertEqual(hashlib.sha256(results.canonical(prereg["payload"]["fgs"]).encode()).hexdigest(), F.FGS_SHA)
        self.assertEqual(F.verify_chain(db), {"ok": True, "rows": 0, "head": F.GENESIS, "first_bad": None})

    def test_the_shape_is_written_once_and_never_overwritten(self):
        root, db = store(self)
        for _ in range(3):
            again = F.open_db(root)
            again.close()
        self.assertEqual(len(F.events(db, "prereg")), 1)
        # A later release with another shape: the pinned sha stands, and the new one is one event, once.
        with mock.patch.object(F, "FGS_SHA", "e" * 64):
            for _ in range(3):
                later = F.open_db(root)
                later.close()
        self.assertEqual(F.kv_get(db, "fgs_prereg"), F.FGS_SHA)
        first, second = F.events(db, "prereg")
        self.assertEqual((second["payload"]["fgs_sha"], second["payload"]["pinned"]), ("e" * 64, F.FGS_SHA))
        self.assertFalse(F.kv_first(db, "fgs_prereg", "e" * 64))
        self.assertEqual(F.kv_get(db, "fgs_prereg"), F.FGS_SHA)

    def test_the_literal_of_the_spec(self):
        # FGS as the spec's section 4 writes it; its sha is what the store pins.
        literal = {"version": "fgs-prereg-1", "stat": "t_r over the first n counted days", "n": [20, 60, 120, 250],
                   "then_every": 250, "pass": "t_r >= c_F and sum_r > 0 and sum_r15 > 0",
                   "row": "the first fwd_checks row written for (pid, n)", "null": "N0", "block_sessions": 21,
                   "worlds": 20000, "pools": ["IND22", "IND1622"],
                   "c_F": "the smallest c whose pass rate at ANY of the four checkpoints under the null is <= alpha_f, "
                          "the maximum over the pools", "alpha_e3_rows": "0.03", "alpha_fresh_route_F": "0.12"}
        self.assertEqual(F.FGS, literal)
        self.assertEqual(F.FGS_SHA, hashlib.sha256(results.canonical(literal).encode()).hexdigest())

    def test_a_read_only_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sqlite3.OperationalError):
                F.open_db(tmp, readonly=True)
            self.assertFalse((Path(tmp) / F.DB).exists(), "a read-only open creates nothing")
            db = F.open_db(tmp)
            F.append_registry(db, registry_row())
            db.close()
            ro = F.open_db(tmp, readonly=True)
            try:
                self.assertEqual(F.program(ro, "fake-family@1").pid, 1)
                self.assertTrue(F.verify_chain(ro)["ok"])
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute("INSERT INTO fwd_kv(key, value) VALUES('k', '1')")
            finally:
                ro.close()

    def test_a_write_of_this_module_commits_itself(self):
        root, db = store(self)
        F.append_registry(db, registry_row())
        F.tag(db, 1, "try", at=1.0)
        F.event(db, "stopped", pid=1, payload={"why": "an invented stop"}, at=2.0)
        F.kv_put(db, "scored_seq", 7)
        F.engine_id(db, "an-invented-engine", at=3.0)
        self.assertFalse(db.in_transaction)
        other = F.open_db(root, readonly=True)
        try:
            self.assertEqual(len(F.programs(other)), 1)
            self.assertEqual(set(F.tags(other, 1)), {"try"})
            self.assertEqual(len(F.events(other, "stopped")), 1)
            self.assertEqual(F.kv_get(other, "scored_seq"), 7)
            self.assertEqual(F.engine_now(other), 1)
        finally:
            other.close()

    def test_inside_the_callers_transaction_it_is_the_callers_to_commit(self):
        _, db = store(self)
        F.append_registry(db, registry_row())
        with self.assertRaises(RuntimeError):
            with db:                                   # one transaction a program, as the forward shadow writes
                day_row_sql = "INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) VALUES(1, " \
                              "'2026-10-13', 1, 0.0, 0.0, 0.0, 0, 0, 'ok', 1.0)"
                db.execute(day_row_sql)
                F.event(db, "restated", pid=1, day="2026-10-13", payload={"why": "invented"}, at=1.0, once="1|abc")
                F.tag(db, 1, "suspect", "2026-10-13", at=1.0)
                self.assertTrue(db.in_transaction, "the module's writes did not commit the caller's transaction")
                raise RuntimeError("the program's write failed half way")
        self.assertEqual(F.events(db, "restated"), [])
        self.assertEqual(F.tags(db, 1), {})
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd_days").fetchone()[0], 0)


class TheChain(unittest.TestCase):
    def setUp(self):
        self.db = memory(self)

    def fill(self, n: int = 4) -> list[int]:
        return [F.append_registry(self.db, registry_row(f"fake-{i}@1", reason="train_pass" if i % 2 else "train_fail"))
                for i in range(1, n + 1)]

    def tamper(self, sql: str, params: tuple = ()) -> None:
        """What only someone who removed the store's triggers could do."""
        self.db.execute("DROP TRIGGER fwd_registry_no_update")
        self.db.execute("DROP TRIGGER fwd_registry_no_delete")
        self.db.execute(sql, params)
        self.db.commit()

    def test_the_genesis_and_the_links(self):
        self.assertEqual(F.head(self.db), F.GENESIS)
        self.assertEqual(self.fill(), [1, 2, 3, 4])
        rows = self.db.execute("SELECT * FROM fwd_registry ORDER BY pid").fetchall()
        self.assertEqual(rows[0]["prev_hash"], F.GENESIS)
        for before, row in zip(rows, rows[1:]):
            self.assertEqual(row["prev_hash"], before["row_hash"])
        for row in rows:
            self.assertEqual(row["row_hash"], F.row_hash(row["prev_hash"], dict(row)))
        self.assertEqual(F.head(self.db), rows[-1]["row_hash"])
        self.assertEqual(F.verify_chain(self.db), {"ok": True, "rows": 4, "head": rows[-1]["row_hash"], "first_bad": None})

    def test_the_link_is_the_formula(self):
        self.fill(2)
        row = dict(self.db.execute("SELECT * FROM fwd_registry WHERE pid=2").fetchone())
        by_hand = hashlib.sha256((row["prev_hash"] + "\n" + results.canonical({k: row[k] for k in F.HASHED}) + "\n"
                                  + hashlib.sha256(row["code"].encode()).hexdigest()).encode()).hexdigest()
        self.assertEqual(row["row_hash"], by_hand)

    def test_every_row_carries_the_forward_route_and_alpha(self):
        self.fill(3)
        F.append_registry(self.db, registry_row("control:index:0", reason="control"))
        rows = self.db.execute("SELECT reason, route, alpha_f FROM fwd_registry").fetchall()
        for row in rows:
            want = ("none", "0") if row["reason"] == "control" else ("S2", "0.03")
            self.assertEqual((row["route"], row["alpha_f"]), want)
        for program in F.programs(self.db):
            self.assertEqual((program.route, program.alpha_f) == ("none", "0"), program.reason == "control")

    def test_another_route_or_alpha_is_refused(self):
        for over in ({"route": "F"}, {"alpha_f": "0.12"}, {"route": "F", "alpha_f": "0.12"}, {"alpha_f": 0.12},
                     {"route": "none", "alpha_f": "0"}, {"route": "S2", "alpha_f": "0"}, {"route": ""}):
            with self.assertRaises(ValueError, msg=over):
                F.append_registry(self.db, registry_row(**over))
        with self.assertRaises(ValueError):   # a control never carries a program's alpha
            F.append_registry(self.db, registry_row("control:index:0", reason="control", route="S2", alpha_f="0.03"))
        self.assertEqual(F.verify_chain(self.db)["rows"], 0)
        self.assertEqual(F.events(self.db, "registered"), [])

    def test_a_tampered_column_is_found(self):
        values = {"key": "other@1", "family": "other", "version": 9, "lane": "beta", "reason": "train_pass",
                  "ugroup": "stocks", "lineage": "equity:other", "program_sha": "0" * 64, "run_sha": "0" * 64,
                  "params": '{"x":1}', "needs": '{"symbols":["QQQ"]}', "author": "someone", "created_at": 1.0,
                  "evidence": "event:1", "first_close": "2026-10-09", "first_day": "2026-10-12", "registered_at": 2.0,
                  "route": "F", "alpha_f": "0.12"}
        self.assertEqual(set(values), set(F.HASHED) - {"pid"})
        for column, value in values.items():
            db = self.db = memory(self)
            self.fill()
            self.tamper(f"UPDATE fwd_registry SET {column}=? WHERE pid=2", (value,))
            self.assertEqual({k: v for k, v in F.verify_chain(db).items() if k != "head"},
                             {"ok": False, "rows": 4, "first_bad": 2}, column)

    def test_a_tampered_route_or_alpha_is_found(self):
        for column, value in (("route", "F"), ("alpha_f", "0.12")):
            self.db = memory(self)
            self.fill()
            self.tamper(f"UPDATE fwd_registry SET {column}=? WHERE pid=3", (value,))
            answer = F.verify_chain(self.db)
            self.assertEqual((answer["ok"], answer["first_bad"]), (False, 3), column)

    def test_changed_code_a_changed_link_and_a_missing_row_are_found(self):
        self.fill()
        self.tamper("UPDATE fwd_registry SET code=code || '# one more line' WHERE pid=1")
        self.assertEqual(F.verify_chain(self.db)["first_bad"], 1)
        for sql in ("UPDATE fwd_registry SET row_hash=? WHERE pid=2", "UPDATE fwd_registry SET prev_hash=? WHERE pid=4"):
            self.db = memory(self)
            self.fill()
            self.tamper(sql, ("0" * 64,))
            self.assertFalse(F.verify_chain(self.db)["ok"], sql)
        self.db = memory(self)
        self.fill()
        self.tamper("DELETE FROM fwd_registry WHERE pid=2")
        self.assertEqual({k: v for k, v in F.verify_chain(self.db).items() if k != "head"},
                         {"ok": False, "rows": 3, "first_bad": 3})
        # A rewritten row with its own hash recomputed breaks the next link.
        self.db = memory(self)
        self.fill()
        row = dict(self.db.execute("SELECT * FROM fwd_registry WHERE pid=2").fetchone())
        row["alpha_f"] = "0.12"
        self.tamper("UPDATE fwd_registry SET alpha_f='0.12', row_hash=? WHERE pid=2", (F.row_hash(row["prev_hash"], row),))
        self.assertEqual(F.verify_chain(self.db)["first_bad"], 3)

    def test_a_row_taken_out_is_found_even_when_every_link_left_was_made_to_hold(self):
        # The pid is in the hashed row and the registry numbers its rows 1, 2, 3, ...: whoever takes a row out and
        # links the next one to the row before it, its own hash recomputed, still leaves a hole in the numbering.
        self.fill(3)
        rows = [dict(row) for row in self.db.execute("SELECT * FROM fwd_registry ORDER BY pid").fetchall()]
        third = {**rows[2], "prev_hash": rows[0]["row_hash"]}
        third["row_hash"] = F.row_hash(third["prev_hash"], third)
        self.tamper("DELETE FROM fwd_registry WHERE pid=2")
        self.db.execute("UPDATE fwd_registry SET prev_hash=?, row_hash=? WHERE pid=3", (third["prev_hash"], third["row_hash"]))
        self.db.commit()
        left = self.db.execute("SELECT * FROM fwd_registry ORDER BY pid").fetchall()
        self.assertEqual([(row["prev_hash"], row["row_hash"]) for row in left],
                         [(F.GENESIS, rows[0]["row_hash"]), (rows[0]["row_hash"], F.row_hash(rows[0]["row_hash"], dict(left[1])))],
                         "every link of what is left holds")
        answer = F.verify_chain(self.db)
        self.assertEqual((answer["ok"], answer["rows"], answer["first_bad"]), (False, 2, 3))

    def test_a_known_key_is_refused_and_leaves_nothing(self):
        self.fill(2)
        before = F.verify_chain(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            F.append_registry(self.db, registry_row("fake-1@1", reason="train_pass"))
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(F.verify_chain(self.db), before)
        self.assertEqual(len(F.events(self.db, "registered")), 2)
        self.assertEqual(F.append_registry(self.db, registry_row("fake-3@1")), 3)

    def test_each_row_is_one_event_with_its_reason(self):
        self.fill(2)
        F.append_registry(self.db, registry_row("control:index:0", reason="control"))
        got = [(e["pid"], e["payload"]["key"], e["payload"]["reason"], e["day"]) for e in F.events(self.db, "registered")]
        day = F.first_day(F.first_close(at(F.t0(), 10))).isoformat()
        self.assertEqual(got, [(1, "fake-1@1", "train_pass", day), (2, "fake-2@1", "train_fail", day),
                               (3, "control:index:0", "control", day)])
        for e in F.events(self.db, "registered"):
            self.assertTrue(e["payload"]["why"])

    def test_what_a_row_is_refused_for(self):
        good = registry_row()
        created = good["created_at"]
        for why, over in (
                ("a reason outside the vocabulary", {"reason": "passed"}),
                ("a lane outside the vocabulary", {"lane": "options"}),
                ("a program_sha that is not the code's", {"program_sha": sha("another program")}),
                ("code that is not text", {"code": None}),
                ("an evidence outside the vocabulary", {"evidence": "event"}),
                ("an evidence that names no event", {"evidence": "event:0"}),
                ("a time that is no time", {"created_at": float("nan")}),
                ("a window opening at the close before the code existed",
                 {"first_close": schedule.previous_session(good["first_close"]), "first_day": good["first_close"]}),
                ("a first day that is not the session after the first close", {"first_day": good["first_close"]}),
                ("a first day two sessions on", {"first_day": schedule.next_session(good["first_day"])}),
                ("params that are not an object", {"params": "[1]"}),
                ("needs that are not JSON", {"needs": "{"}),
                ("a program without a family", {"family": None}),
                ("a program without a version", {"version": None}),
                ("no row claims a time before its evidence",
                 {"evidence": "registry", "created_at": created, "registered_at": created + 1.0})):
            with self.assertRaises(ValueError, msg=why):
                F.append_registry(self.db, {**good, **over})
        with self.assertRaises(ValueError):
            F.append_registry(self.db, registry_row("control:index:0", reason="control", family="a-family"))
        self.assertEqual(F.verify_chain(self.db)["rows"], 0)
        # With no event the registry's own sighting is the time, and a later first close than D2's is only less claimed.
        self.assertEqual(F.append_registry(self.db, {**good, "evidence": "registry", "created_at": created,
                                                     "registered_at": created}), 1)
        later = schedule.next_session(good["first_close"])
        self.assertEqual(F.append_registry(self.db, registry_row("fake-late@1", first_close=later,
                                                                 first_day=schedule.next_session(later))), 2)

    def test_a_row_hashes_the_same_whatever_shape_it_arrived_in(self):
        # Dates or ISO days, mappings or canonical text, an integer time: one stored row, one hash.
        created = float(int(at(F.t0(), 10)))
        a = registry_row(created=created)
        b = {**a, "first_close": a["first_close"].isoformat(), "first_day": a["first_day"].isoformat(),
             "params": "{}", "needs": results.canonical(a["needs"]), "created_at": int(created),
             "registered_at": int(a["registered_at"]), "version": 1.0}
        one, two = memory(self), memory(self)
        F.append_registry(one, a)
        F.append_registry(two, b)
        self.assertEqual(F.head(one), F.head(two))
        self.assertTrue(F.verify_chain(two)["ok"])
        program = F.program(two, "fake-family@1")
        self.assertEqual((program.first_close, program.first_day), (a["first_close"], a["first_day"]))
        self.assertEqual((program.params, program.needs, program.version, program.created_at),
                         ({}, a["needs"], 1, created))


class TheEventLog(unittest.TestCase):
    def setUp(self):
        self.db = memory(self)

    def test_once_the_same_key_writes_one_row(self):
        first = F.event(self.db, "restated", pid=3, day="2026-10-13", payload={"why": "a recompute differed"}, at=1.0,
                        once="1|abcd1234")
        self.assertGreater(first, 0)
        for night in range(2, 6):   # night after night, the same standing fact
            self.assertEqual(F.event(self.db, "restated", pid=3, day="2026-10-13", payload={"why": "again"},
                                     at=float(night), once="1|abcd1234"), 0)
        (row,) = F.events(self.db, "restated")
        self.assertEqual((row["seq"], row["pid"], row["day"], row["at"]), (first, 3, "2026-10-13", 1.0))
        self.assertEqual(row["payload"], {"why": "a recompute differed", "once": "1|abcd1234"})

    def test_another_key_pid_day_or_kind_is_another_event(self):
        base = dict(pid=3, day="2026-10-13", once="k")
        self.assertTrue(F.event(self.db, "data_failed", at=1.0, **base))
        for over in ({"once": "k2"}, {"pid": 4}, {"day": "2026-10-14"}, {"pid": None}, {"day": None}):
            self.assertTrue(F.event(self.db, "data_failed", at=2.0, **{**base, **over}), over)
            self.assertEqual(F.event(self.db, "data_failed", at=3.0, **{**base, **over}), 0, over)
        self.assertTrue(F.event(self.db, "run_failed", at=2.0, **base))
        self.assertEqual(len(F.events(self.db, "data_failed")), 6)
        self.assertEqual(len(F.events(self.db, "run_failed")), 1)

    def test_a_standing_fact_names_its_key(self):
        for kind in F.ONCE_KINDS:
            with self.assertRaises(ValueError, msg=kind):
                F.event(self.db, kind, pid=1, day="2026-10-13", at=1.0)
        with self.assertRaises(ValueError):
            F.event(self.db, "an_invented_kind", at=1.0)
        with self.assertRaises(ValueError):
            F.event(self.db, "stopped", payload=["not a mapping"], at=1.0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fwd_events").fetchone()[0], 0)

    def test_a_kind_that_is_not_a_standing_fact_repeats_unless_keyed(self):
        self.assertTrue(F.event(self.db, "stopped", pid=1, at=1.0))
        self.assertTrue(F.event(self.db, "stopped", pid=1, at=2.0))
        self.assertTrue(F.event(self.db, "chain_ok", at=3.0, once="2026-10-13"))
        self.assertEqual(F.event(self.db, "chain_ok", at=4.0, once="2026-10-13"), 0)

    def test_the_reader(self):
        F.event(self.db, "stopped", pid=1, day=dt.date(2026, 10, 13), payload={"why": "cap", "n": 500}, at=10.0)
        F.event(self.db, "stopped", pid=2, payload={"why": "disqualified"}, at=20.0)
        F.event(self.db, "resumed", pid=1, at=30.0)
        self.assertEqual([e["pid"] for e in F.events(self.db, "stopped")], [1, 2])
        self.assertEqual([e["pid"] for e in F.events(self.db, "stopped", pid=2)], [2])
        self.assertEqual([e["pid"] for e in F.events(self.db, "stopped", since=20.0)], [2])
        self.assertEqual(F.events(self.db, "stopped", since=20.5), [])
        self.assertEqual(F.events(self.db, "suspect"), [])
        (one, _two) = F.events(self.db, "stopped")
        self.assertEqual(one, {"seq": 1, "at": 10.0, "kind": "stopped", "pid": 1, "day": "2026-10-13",
                               "payload": {"why": "cap", "n": 500}})

    def test_once_reads_the_payloads_itself_without_the_json_functions(self):
        # An SQLite built without its JSON functions: the same answer, read from the payloads.
        F.event(self.db, "no_minute", pid=1, day="2026-10-13", at=1.0, once="a")

        class NoJson:
            def __init__(self, db):
                self.db = db

            def execute(self, sql, params=()):
                if "json_extract" in sql:
                    raise sqlite3.OperationalError("no such function: json_extract")
                return self.db.execute(sql, params)

        self.assertTrue(F._once_seen(NoJson(self.db), "no_minute", 1, "2026-10-13", "a"))
        self.assertFalse(F._once_seen(NoJson(self.db), "no_minute", 1, "2026-10-13", "b"))
        self.assertFalse(F._once_seen(NoJson(self.db), "no_minute", 2, "2026-10-13", "a"))


class KvAndEngines(unittest.TestCase):
    def setUp(self):
        self.db = memory(self)

    def test_the_kv(self):
        self.assertIsNone(F.kv_get(self.db, "scored_seq"))
        self.assertEqual(F.kv_get(self.db, "scored_seq", 0), 0)
        F.kv_put(self.db, "scored_seq", 41)
        F.kv_put(self.db, "scored_seq", 42)
        self.assertEqual(F.kv_get(self.db, "scored_seq"), 42)
        self.assertTrue(F.kv_first(self.db, "equity_sha", "a" * 64))
        self.assertFalse(F.kv_first(self.db, "equity_sha", "b" * 64))
        self.assertEqual(F.kv_get(self.db, "equity_sha"), "a" * 64)
        F.kv_put(self.db, "equity_sha", {"nested": [1, "two"]})
        self.assertEqual(F.kv_get(self.db, "equity_sha"), {"nested": [1, "two"]})

    def test_an_engine_label_gets_a_small_id_once(self):
        self.assertIsNone(F.engine_now(self.db))
        self.assertEqual(F.engine_id(self.db, "engine-a", at=1.0), (1, True))
        self.assertEqual(F.engine_id(self.db, "engine-a", at=2.0), (1, False))
        self.assertEqual(F.engine_id(self.db, "engine-b", at=3.0), (2, True))
        self.assertEqual(F.engine_id(self.db, "engine-a", at=4.0), (1, False), "an old label keeps its id")
        self.assertEqual(F.engine_now(self.db), 2)
        self.assertEqual((F.engine_label(self.db, 1), F.engine_label(self.db, 2), F.engine_label(self.db, 3)),
                         ("engine-a", "engine-b", None))
        self.assertEqual(self.db.execute("SELECT at FROM fwd_engines WHERE id=1").fetchone()[0], 1.0)
        with self.assertRaises(ValueError):
            F.engine_id(self.db, "", at=5.0)


class Programs(unittest.TestCase):
    def setUp(self):
        self.db = memory(self)
        for key, reason in (("alpha@1", "train_pass"), ("beta@2", "train_fail"), ("gamma@1", "seed"),
                            ("control:index:0", "control")):
            F.append_registry(self.db, registry_row(key, reason=reason))

    def test_the_rows_as_programs(self):
        got = F.programs(self.db)
        self.assertEqual([(p.pid, p.key, p.family, p.version, p.reason) for p in got],
                         [(1, "alpha@1", "alpha", 1, "train_pass"), (2, "beta@2", "beta", 2, "train_fail"),
                          (3, "gamma@1", "gamma", 1, "seed"), (4, "control:index:0", None, None, "control")])
        self.assertEqual([p.pid for p in F.programs(self.db, reasons=("seed", "train_pass"))], [1, 3])
        self.assertEqual(F.programs(self.db, reasons=()), [])
        self.assertEqual(F.program(self.db, "beta@2"), got[1])
        self.assertIsNone(F.program(self.db, "beta@3"))
        first = got[0]
        self.assertEqual((first.lane, first.ugroup, first.lineage, first.code, first.program_sha),
                         ("equity", "index", "equity:alpha", CODE, sha(CODE)))
        self.assertIsInstance(first.first_close, dt.date)
        self.assertEqual(first.first_day, F.first_day(first.first_close))

    def test_a_listing_holds_every_field_but_the_text_and_no_row_it_does_not_answer_with(self):
        """The review's finding: the night's queue was the whole registry fetched at once with every row's text, the
        stopped rows too: about 6 KB of the ops child's address space a row, for rows the night never runs."""
        import dataclasses

        whole, listed = F.programs(self.db), F.programs(self.db, code=False)
        self.assertEqual([dataclasses.replace(p, code="") for p in whole], listed)
        self.assertEqual({p.code for p in listed}, {""})
        self.assertTrue(all(p.code for p in whole))
        self.assertEqual([p.pid for p in F.programs(self.db, reasons=("seed",), code=False)], [3])
        self.assertTrue(F.tag(self.db, 2, "stopped", "cap:2026-10-20", at=100.0))

        # One row in hand at a time, and a stopped row is never kept: the rows are read from the cursor.
        class Watched:
            def __init__(self, db):
                self.db, self.fetched_all = db, 0

            def execute(self, sql, params=()):
                cursor, outer = self.db.execute(sql, params), self

                class Cursor:
                    def __iter__(self):
                        return iter(cursor)

                    def fetchall(self):
                        outer.fetched_all += sql.count("fwd_registry")
                        return cursor.fetchall()

                    def fetchone(self):
                        return cursor.fetchone()
                return Cursor()
        watched = Watched(self.db)
        self.assertEqual([p.pid for p in F.programs(watched, code=False)], [1, 3, 4])
        self.assertEqual([p.pid for p in F.programs(watched)], [1, 3, 4])
        self.assertEqual(watched.fetched_all, 0, "the registry is never fetched whole")

    def test_a_stop_and_its_undo(self):
        self.assertTrue(all(F.active(self.db, pid) for pid in (1, 2, 3, 4, 99)))
        self.assertTrue(F.tag(self.db, 2, "stopped", "cap:2026-10-20", at=100.0))
        self.assertFalse(F.active(self.db, 2))
        self.assertEqual([p.pid for p in F.programs(self.db)], [1, 3, 4])
        self.assertEqual([p.pid for p in F.programs(self.db, active=False)], [1, 2, 3, 4])
        self.assertEqual([p.pid for p in F.programs(self.db, reasons=("train_fail",))], [])
        self.assertTrue(F.tag(self.db, 2, "resumed", "200.0|the operator's undo", at=200.0))
        self.assertTrue(F.active(self.db, 2))
        self.assertEqual([p.pid for p in F.programs(self.db)], [1, 2, 3, 4])
        # Stopped again after the resume: the newest of the two decides.
        self.assertTrue(F.tag(self.db, 2, "stopped", "disqualified:2026-11-03", at=300.0))
        self.assertFalse(F.active(self.db, 2))
        # A resume is the undo of the stops before it, never of one after it.
        self.assertTrue(F.tag(self.db, 3, "resumed", "50.0|early", at=50.0))
        self.assertTrue(F.tag(self.db, 3, "stopped", "cap:2026-10-20", at=60.0))
        self.assertFalse(F.active(self.db, 3))
        # Only a stop NEWER than the latest resume stops: an undo written at the stop's own instant undoes it.
        self.assertTrue(F.tag(self.db, 1, "stopped", "cap:2026-10-20", at=400.0))
        self.assertTrue(F.tag(self.db, 1, "resumed", "400.0|the same instant", at=400.0))
        self.assertTrue(F.active(self.db, 1))
        self.assertEqual([p.pid for p in F.programs(self.db)], [1, 4])

    def test_the_tags(self):
        self.assertEqual(F.tags(self.db, 1), {})
        self.assertTrue(F.tag(self.db, 1, "live", "alpha@1:r", at=5.0))
        self.assertFalse(F.tag(self.db, 1, "live", "alpha@1:r", at=9.0), "the first row stands")
        self.assertTrue(F.tag(self.db, 1, "suspect", "2026-10-14", at=7.0))
        self.assertTrue(F.tag(self.db, 1, "suspect", "2026-10-13", at=6.0))
        self.assertTrue(F.tag(self.db, 1, "review_pass", at=1.0))
        self.assertEqual(F.tags(self.db, 1), {"review_pass": [{"value": "", "at": 1.0}],
                                              "live": [{"value": "alpha@1:r", "at": 5.0}],
                                              "suspect": [{"value": "2026-10-13", "at": 6.0},
                                                          {"value": "2026-10-14", "at": 7.0}]})
        self.assertEqual(F.tags(self.db, 2), {})
        with self.assertRaises(ValueError):
            F.tag(self.db, 1, "verdict", at=1.0)

    def test_a_suspect_until_it_stores_a_later_day(self):
        self.assertFalse(F.suspect(self.db, 1))
        F.tag(self.db, 1, "suspect", "2026-10-14", at=1.0)
        self.assertTrue(F.suspect(self.db, 1), "no stored day at all")
        day_row(self.db, 1, "2026-10-13", 1)
        self.assertTrue(F.suspect(self.db, 1), "its last stored day is before the night it was tagged on")
        day_row(self.db, 1, "2026-10-14", 1)
        self.assertTrue(F.suspect(self.db, 1), "on the night itself")
        day_row(self.db, 1, "2026-10-15", 1)
        self.assertFalse(F.suspect(self.db, 1), "a later night completed: suspect no more")
        self.assertEqual(F.last_stored_day(self.db, 1), "2026-10-15")
        self.assertIsNone(F.last_stored_day(self.db, 2))
        self.assertTrue(F.active(self.db, 1), "a suspect is not stopped")

    def test_the_counted_and_the_stored_days(self):
        self.assertEqual((F.counted_days(self.db, 1), F.stored_days(self.db, 1)), ([], 0), "before any engine")
        one, _ = F.engine_id(self.db, "engine-a", at=1.0)
        for day, status in (("2026-10-13", "ok"), ("2026-10-12", "ok"), ("2026-10-14", "disqualified"),
                            ("2026-10-15", "ok")):
            day_row(self.db, 1, day, one, status=status, r=0.01)
        day_row(self.db, 2, "2026-10-12", one)
        F.event(self.db, "audit_mismatch", pid=1, day="2026-10-13", payload={"why": "the morning re-fetch"}, at=9.0,
                once="2026-10-13")
        F.event(self.db, "audit_mismatch", pid=2, day="2026-10-15", at=9.0, once="2026-10-15")   # another program's
        counted = F.counted_days(self.db, 1)
        self.assertEqual([d["day"] for d in counted], ["2026-10-12", "2026-10-15"])
        self.assertEqual(set(counted[0]), {"pid", "day", "engine", "r", "w", "b", "r15", "r0", "entries", "exits",
                                           "status", "at", "bars"})
        self.assertEqual(F.stored_days(self.db, 1), 4, "any status, an audited day too")
        # A new engine label opens a new series: the newest is read unless one is named.
        two, _ = F.engine_id(self.db, "engine-b", at=2.0)
        self.assertEqual((F.counted_days(self.db, 1), F.stored_days(self.db, 1)), ([], 0))
        self.assertEqual(len(F.counted_days(self.db, 1, engine=one)), 2)
        self.assertEqual(F.stored_days(self.db, 1, engine=one), 4)
        day_row(self.db, 1, "2026-10-12", two)
        day_row(self.db, 1, "2026-10-13", two)
        self.assertEqual([d["day"] for d in F.counted_days(self.db, 1)], ["2026-10-12"], "the audit mark is the day's")
        self.assertEqual(F.stored_days(self.db, 1), 2)
        self.assertEqual(F.last_stored_day(self.db, 1), "2026-10-15")


class AppendOnly(unittest.TestCase):
    """T9: UPDATE and DELETE abort on every forward table but `fwd_kv`, and so does a replace (SQLite deletes a
    replaced row without firing a delete trigger unless recursive triggers are on: the schema turns them on)."""

    VALUES = {"INTEGER": 7, "REAL": 1.0, "TEXT": "x"}   # 7: the store's own first rows (its prereg event) are 1

    def insert(self, db: sqlite3.Connection, table: str) -> None:
        columns = db.execute(f"PRAGMA table_info({table})").fetchall()
        values = {c["name"]: self.VALUES[c["type"]] for c in columns}
        if table == "fwd_twins":
            values["cause"] = "bars"
        db.execute(f"INSERT INTO {table}({', '.join(values)}) VALUES({', '.join('?' * len(values))})",
                   list(values.values()))
        db.commit()

    def check(self, db: sqlite3.Connection) -> None:
        self.assertEqual(set(F.APPEND_ONLY), set(F.TABLES) - {"fwd_kv"})
        for table in F.TABLES:
            self.insert(db, table)
            first = db.execute(f"PRAGMA table_info({table})").fetchall()[-1]["name"]
            before = [tuple(r) for r in db.execute(f"SELECT * FROM {table}")]
            self.assertTrue(before, table)
            for statement in (f"UPDATE {table} SET {first}={first}", f"DELETE FROM {table}",
                              f"DELETE FROM {table} WHERE rowid IS NOT NULL" if table not in (
                                  "fwd_days", "fwd_ll", "fwd_checks") else f"DELETE FROM {table} WHERE pid=7",
                              f"REPLACE INTO {table} SELECT * FROM {table}"):
                if table == "fwd_kv":
                    db.execute(statement)
                    db.commit()
                    continue
                with self.assertRaises(sqlite3.DatabaseError, msg=statement) as raised:
                    db.execute(statement)
                    db.commit()
                db.rollback()
                self.assertIn(F.APPEND_ONLY_ERROR, str(raised.exception), statement)
            if table != "fwd_kv":
                self.assertEqual([tuple(r) for r in db.execute(f"SELECT * FROM {table}")], before, table)

    def test_on_the_in_memory_database_the_packages_test_on(self):
        self.check(memory(self))

    def test_on_the_houses_store_and_through_another_connection(self):
        root, db = store(self)
        self.check(db)
        other = sqlite3.connect(str(root / F.DB))
        self.addCleanup(other.close)
        for table in F.APPEND_ONLY:
            for statement in (f"UPDATE {table} SET rowid=rowid" if table not in ("fwd_days", "fwd_ll", "fwd_checks")
                              else f"UPDATE {table} SET pid=pid", f"DELETE FROM {table}"):
                with self.assertRaises(sqlite3.DatabaseError, msg=statement) as raised:
                    other.execute(statement)
                self.assertIn(F.APPEND_ONLY_ERROR, str(raised.exception))
                other.rollback()

    def test_the_first_value_written_for_a_key_stands(self):
        # A later different value cannot replace a row: the insert is refused by the key, the update by the trigger.
        db = memory(self)
        F.append_registry(db, registry_row())
        F.tag(db, 1, "try", at=1.0)
        self.assertFalse(F.tag(db, 1, "try", at=2.0))
        self.assertEqual(F.tags(db, 1)["try"], [{"value": "", "at": 1.0}])
        day_row(db, 1, "2026-10-13", 1, r=0.01)
        with self.assertRaises(sqlite3.IntegrityError):
            day_row(db, 1, "2026-10-13", 1, r=0.02)
        db.rollback()
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("INSERT OR REPLACE INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) "
                       "VALUES(1, '2026-10-13', 1, 0.02, 0.0, 0.0, 0, 0, 'ok', 2.0)")
        db.rollback()
        self.assertEqual(db.execute("SELECT r FROM fwd_days").fetchone()[0], 0.01)


if __name__ == "__main__":
    unittest.main()
