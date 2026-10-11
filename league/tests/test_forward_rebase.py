"""THE TWIN IS RE-BASED AFTER A DIFFERENCE, SO A MISS COUNTS ONCE (the captain's A29; league/ops/forward_twins.py
`live_seed`, `RebasedTwin`, `finish`, `a14_reading`; league/ops/forward_db.py `ADDED_COLUMNS`; league/ops/
forward_report.py `fills.rebase`).

A14 compares each live session's intent keys with a replay twin that never misses a fill. The rehearsal of the first
real-money session (Oct 11, 2026) measured that ONE missed buy of a program that buys only when flat leaves the live
book a session behind that twin for good: about half its sessions differ from then on, and one such program fails the
pooled 95% bound for every program at the checkpoint. From this release a session whose keys differ is counted as
differing, exactly as registered; THEN the twin's book is set to the live book as it stands after that session, and
the sessions after it are compared from the same state.

What is held here:
- AS REGISTERED: on a path with no difference the rows `a14_reading` reads are byte for byte the rows of the release
  before this one (their sha256, taken on that release's tree, is pinned below); on a path with a difference the rows
  through the differing session are those rows too; and the reading's rule, bounds and keys are as they were.
- THE RULE on the rehearsal's three paths (instance A's shape: one ETF, bought when flat, held to its maximum of 3
  sessions): the buy fills; the first buy is missed; a later rebuy is missed once. And on a difference that comes
  again the next session, a book that is not flat at the re-base (an exit the windows missed), a decide that
  recorded nothing, a program that keeps memory, a retirement, an interrupted night.
- THE STORE: the two columns and the event; a store made before them is migrated without a row rewritten; rows
  written before this release stand and re-base the twin for the sessions not yet written.
- THE REPORT: the re-bases and the un-re-based twins' own agreement, beside, in the reading and in the forward report.

THE LIVE BOOKS are `test_forward_twins.live_path`'s: E1's engine account deciding through the registered program, with
a session's entries or exits taken away, so each book is its own decisions' doing. The patterns asserted (which
sessions differ) are worked out by hand from the program's rule in each test's words, never read from the code under
test. The forward store is the REAL `forward_db` on a file; the market is `league.equity.synth`'s; nothing here is a
market's price."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.equity import schedule, synth
    from league.live.decider import InlineDecider
    from league.ops import forward_db, forward_report, forward_twins, guard, twins
    from league.tests import test_forward_twins as fx
    from league.tests.test_forward_twins import CLOCK, D1, D2, D3, D4, OVERNIGHT, Book, Shadow, at

SETTINGS = {"elane": {"forward": {"mode": "record", "fill_minutes": False}}}
END = "2026-11-20"
#: INSTANCE A's SHAPE (the rehearsal's): one ETF at a share of the sleeve, bought when flat, never sold by the program;
#: the House exits it at its maximum hold of 3 sessions, and it buys again at the close of the session it left in. A
#: cycle of four sessions: decisions 0, 4, 8, ... buy.
HOLD3 = '''NEEDS = {"symbols": ["QQQ"], "history": 5, "max_hold_sessions": 3}
PARAMS = {}


def decide(ctx):
    if ctx.positions or ctx.orders:
        return []
    return [{"buy": "QQQ", "share": 0.4, "at": "open", "tag": "hold3"}]
'''
#: Sells every lot at the next open and buys when flat: a cycle of two sessions (decisions 0, 2, 4, ... buy; 1, 3, ...
#: sell the lot bought that session).
RANGE = '''NEEDS = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    if ctx.positions:
        return [{"sell": p["id"], "at": "open", "tag": "range"} for p in ctx.positions]
    return [{"buy": "SPY", "share": 0.2, "at": "open", "tag": "range"}]
'''
#: THE ROWS OF THE RELEASE BEFORE THIS ONE (main e36c7e3989265acfdb77e6e11c90bfb82cedc8c4), taken on that release's own
#: tree, by its own league/ops/forward_twins.py, with this file's fixtures, on Python 3.11 and 3.14 (`registered_sha`
#: over `REGISTERED`): sha256 of the canonical JSON of each row's registered columns, in (instance, day) order. On
#: that tree the third path's 29 sessions read ".x..xx..xx..xx..xx..xx..xx..x": the line this release keeps beside
#: (`base_agree`).
REGISTERED = ("instance", "day", "pid", "live_keys", "shadow_keys", "agree", "why", "at", "live_bars", "shadow_bars",
              "cause")
#: What `a14_reading` reads of a row (its SELECT's registered columns).
READ = ("instance", "day", "agree", "why", "cause")
PINNED = {
    "overnight, every session agreeing, nine nights": "e297ff9f6cd5b0abfb9ae226a247f0426d8a7edabfe787b24dbaee38944f8251",
    "hold3, every session agreeing, to the store's end": "5be12aa53020404a95a44eb368dc7875bb9603597c3d42d1a90d08bc33ed18f5",
    "hold3, the first buy missed, through the differing session": "390b81b1d5a57153a5b736d808a595b3d3517d1254a616a075e33e4649e1c1dd",
}


def registered_sha(rows, columns=REGISTERED) -> str:
    return hashlib.sha256(json.dumps([[row[c] for c in columns] for row in rows], sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


@unittest.skipUnless(HAVE, "numpy not installed")
class Rebase(unittest.TestCase):
    """A synthetic gated store through `END` (built once a class), the real forward store on a file, a live book."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = Path(cls._tmp.name) / "state"
        cls.state.mkdir()
        cls.store_root = synth.synthetic_store(cls.state / "equity-daily", symbols=("SPY", "QQQ", "IWM"),
                                               start=fx.STORE_START, end=fx.STORE_END, gate=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = forward_db.open_db(self.root)
        self.addCleanup(self.db.close)
        self.decider = InlineDecider()
        self.book = Book(self.root / forward_twins.LIVE_DB)
        self.addCleanup(self.book.close)

    # ------------------------------------------------------------------------------------------------ the fixtures
    def shadow(self, through, **kw) -> "Shadow":
        kw.setdefault("decider", self.decider)
        kw.setdefault("settings", SETTINGS)
        return Shadow(self.store_root, through=through, **kw)

    def live(self, key: str, code: str, *, first: str = D1, base: int = 100, **does):
        """A registered program and its live instance, created in the decide step of `first`, whose book is its own
        decisions' doing through the store's end (`live_path`). (the instance id, the pid, the lots)."""
        pid = fx.register(self.db, key, code)
        iid = self.book.instance(key, code, created=at(first, 16, 25))
        program = forward_db.program(self.db, key)
        bars = self.shadow(END).slice(program, first_day=schedule.next_session(first))
        path = fx.live_path(self.book, iid, program, bars, base=base, **does)
        return iid, pid, path["lots"]

    def night(self, through: str, **kw) -> dict:
        return forward_twins.finish(self.root, self.db, self.shadow(through, **kw), now=at(through, 18, 35))

    def nights(self, first: str = D1, last: str = END) -> list[dict]:
        """Every forward night from `first` to `last`, one at a time, as the House runs them."""
        return [self.night(day) for day in forward_twins._sessions(forward_twins._date(first), forward_twins._date(last))]

    def rows(self, iid: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM fwd_twins" + (" WHERE instance=?" if iid else "") + " ORDER BY instance, day"
        return list(self.db.execute(sql, (iid,) if iid else ()))

    def line(self, iid: str, column: str = "agree") -> str:
        return "".join("." if r[column] == 1 else ("x" if r[column] == 0 else "?") for r in self.rows(iid))

    def rebased(self) -> list[dict]:
        return forward_db.events(self.db, "twin_rebased")

    def closes(self, iid: str, lots, *, base: int = 100, through: str = END) -> list[dict]:
        """The instance's closed lots as the Done meter counts them (`dlane_report.equity_closes`' keys that
        `a14_reading` reads), each with a final priced E1 twin of no gap in the swarm store."""
        counted = [{"equity": True, "pid": twins.equity_key(base + int(lot["lid"])), "instance": iid,
                    "day": lot["exit_day"], "opened_day": lot["entry_day"]}
                   for lot in lots if lot["exit_day"] and lot["exit_day"] <= through]
        db = sqlite3.connect(self.root / forward_twins.SWARM_DB)
        db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        held = db.execute("SELECT value FROM kv WHERE key=?", (twins.EQUITY_TWINS_KEY,)).fetchone()
        records = json.loads(held[0]) if held else {}
        records.update({c["pid"]: {"final": True, "status": "priced", "gap_bp": 0.0} for c in counted})
        db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (twins.EQUITY_TWINS_KEY, json.dumps(records)))
        db.commit()
        db.close()
        return counted


# ============================================================================================ as registered
class AsRegistered(Rebase):
    """THE REGISTERED MEANING OF A DIFFERING SESSION DOES NOT CHANGE BY ONE CHARACTER."""

    def test_a_path_with_no_difference_is_byte_for_byte_the_release_befores(self):
        iid, pid, lots = self.live("fake-overnight@1", OVERNIGHT)
        for through in (D2, D3, D4, "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"):
            self.night(through)
        rows = self.rows(iid)
        self.assertEqual(len(rows), 9)
        self.assertEqual(registered_sha(rows), PINNED["overnight, every session agreeing, nine nights"])
        # What this release adds to such a row says "nothing happened": no re-base behind it, and the un-re-based
        # twin's answer is the row's own.
        self.assertEqual({(r["agree"], r["rebased"], r["base_agree"]) for r in rows}, {(1, 0, 1)})
        self.assertEqual(self.rebased(), [])

    def test_instance_as_shape_with_every_buy_filled_is_byte_for_byte_the_release_befores(self):
        iid, pid, lots = self.live("hold3@1", HOLD3)
        self.night(END)
        rows = self.rows(iid)
        self.assertEqual(len(rows), 29)
        self.assertEqual(registered_sha(rows), PINNED["hold3, every session agreeing, to the store's end"])
        self.assertEqual(self.line(iid), "." * 29)

    def test_the_differing_session_itself_is_the_row_the_release_before_wrote(self):
        """Counted as differing, EXACTLY as registered: the rows through the first differing session are the release
        before's, the differing one among them (its keys, its bars hashes, its cause)."""
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        self.night(END)
        rows = self.rows(iid)
        self.assertEqual([(r["day"], r["agree"], r["cause"]) for r in rows[:2]], [(D1, 1, None), (D2, 0, "unknown")])
        self.assertEqual(registered_sha(rows[:2]),
                         PINNED["hold3, the first buy missed, through the differing session"])

    def test_the_readings_rule_reads_the_same_five_columns(self):
        """`a14_reading`'s inputs on a path with no difference: the registered columns it selects are the release
        before's (the pinned rows hold them), and the reading over them is what that release's reading was."""
        iid, pid, lots = self.live("hold3@1", HOLD3)
        self.night(END)
        counted = self.closes(iid, lots)
        self.assertEqual(len(counted), 7)
        found, read = forward_twins._twin_rows(self.root, [iid])
        self.assertTrue(read)
        self.assertEqual([[row[c] for c in READ] for _, row in sorted(found[iid].items())],
                         [[row[c] for c in READ] for row in self.rows(iid)])
        out = forward_twins.a14_reading(self.root, counted)
        self.assertEqual(tuple(out), forward_twins.A14_KEYS)
        last = schedule.previous_session(forward_twins._date(counted[-1]["day"])).isoformat()
        sessions = len(forward_twins._sessions(forward_twins._date(D1), forward_twins._date(last)))
        self.assertEqual((out["applies"], out["holds"], out["final"], out["why"]), (True, True, True, None))
        self.assertEqual(out["intents"], {"instances": 1, "sessions": sessions, "agreed": sessions, "missing": 0,
                                          "unreadable": 0, "share": 1.0, "bound": 0.95, "ok": True, "disagreed": 0,
                                          "causes": {"bars": 0, "program": 0, "unknown": 0}})
        self.assertEqual(out["by_instance"], [{"instance": iid, "sessions": sessions, "agreed": sessions, "missing": 0,
                                               "unreadable": 0}])
        self.assertEqual(out["rebase"], {"rebases": 0, "sessions": sessions, "agreed": sessions, "share": 1.0,
                                         "by_instance": [{"instance": iid, "rebases": 0, "sessions": sessions,
                                                          "agreed": sessions, "share": 1.0}]})

    def test_the_bounds_are_the_registered_ones(self):
        self.assertEqual((forward_db.A14_AGREE, forward_db.A14_GAP_BP), (0.95, 15.0))
        self.assertEqual(forward_twins.A14_KEYS[:7], ("applies", "holds", "final", "why", "gap", "intents",
                                                      "by_instance"))
        self.assertEqual(forward_twins.A14_INSTANCE_KEYS, ("instance", "sessions", "agreed", "missing", "unreadable"))
        self.assertEqual(forward_twins.keys_of([{"buy": "QQQ", "at": "open"}, {"sell": 3, "at": "close"}], needs=["QQQ"],
                                               held={3: {"symbol": "QQQ", "entry_day": D1}}),
                         ["B|QQQ|open", f"S|QQQ|close|{D1}"])


# ============================================================================================ the rule
class TheThreePaths(Rebase):
    """THE REHEARSAL'S THREE PATHS, 29 sessions from the first decision (decision 0 is `D1`'s close). Instance A buys
    at decisions 0, 4, 8, ...: its lot enters the next session, is held through three closes and leaves at the open
    after them by the House's rule; it buys again at that session's close."""

    def test_the_buy_fills_every_session_agrees_and_nothing_is_re_based(self):
        iid, pid, lots = self.live("hold3@1", HOLD3)
        receipts = self.nights()
        self.assertEqual(self.line(iid), "." * 29)
        self.assertEqual(self.line(iid, "base_agree"), "." * 29)
        self.assertEqual({r["rebased"] for r in self.rows(iid)}, {0})
        self.assertEqual(self.rebased(), [])
        self.assertEqual(sum(r["rebased"] + r["disagreed"] + r["failed"] + r["interrupted"] for r in receipts), 0)

    def test_the_first_buy_missed_one_differing_session_one_re_base_then_agreement(self):
        """The buy decided at decision 0 is missed in `D2`'s open window. At decision 1 the live book is flat and
        buys again; its twin, which never misses, holds and says nothing: THE differing session. As registered the
        live book then runs a session behind its twin for good: it buys at decisions 1, 5, 9, ... where the twin
        buys at 4, 8, 12, ..., so decisions 4, 5, 8, 9, ... differ too."""
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        receipts = self.nights()
        self.assertEqual(self.line(iid), ".x" + "." * 27)
        self.assertEqual(self.line(iid, "base_agree"), ".x" + "..xx" * 6 + "..x")
        rows = self.rows(iid)
        self.assertEqual((json.loads(rows[1]["live_keys"]), json.loads(rows[1]["shadow_keys"])), (["B|QQQ|open"], []))
        self.assertEqual([r["rebased"] for r in rows], [0, 0] + [1] * 27)
        [event] = self.rebased()
        self.assertEqual((event["day"], event["pid"], event["payload"]["instance"]), (D2, pid, iid))
        self.assertEqual((event["payload"]["held"], event["payload"]["unheld"], event["payload"]["planned"]),
                         ([], 0, {"buys": 1, "sells": 0, "exits": 0}), "the live book after it: flat, one buy planned")
        self.assertEqual(sum(r["rebased"] for r in receipts), 1)
        self.assertEqual(sum(r["disagreed"] for r in receipts), 1)
        # THE READING at the last close (the seventh lot leaves at the store's last open: 29 counted sessions): one
        # counted difference holds the 95% bound; as registered before this rule the same book read 15 of 29 (the
        # un-re-based figure, beside).
        counted = self.closes(iid, lots)
        out = forward_twins.a14_reading(self.root, counted)
        self.assertEqual((out["intents"]["sessions"], out["intents"]["agreed"], out["intents"]["disagreed"],
                          out["intents"]["ok"], out["holds"]), (29, 28, 1, True, True))
        self.assertEqual(out["rebase"], {"rebases": 1, "sessions": 29, "agreed": 15, "share": round(15 / 29, 6),
                                         "by_instance": [{"instance": iid, "rebases": 1, "sessions": 29, "agreed": 15,
                                                          "share": round(15 / 29, 6)}]})

    def test_a_later_rebuy_missed_once_is_the_same(self):
        """Every buy fills until the one decided at decision 12, missed in session 13's open window: decision 13
        differs (the live book buys again), and as registered so would 16, 17, 20, 21, 24, 25 and 28."""
        days = forward_twins._sessions(forward_twins._date(D1), forward_twins._date(END))
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={days[13]})
        self.nights()
        self.assertEqual(self.line(iid), "." * 13 + "x" + "." * 15)
        self.assertEqual(self.line(iid, "base_agree"), "." * 13 + "x" + "..xx" * 3 + "..x")
        self.assertEqual([e["day"] for e in self.rebased()], [days[13]])
        self.assertEqual([r["rebased"] for r in self.rows(iid)], [0] * 14 + [1] * 15)

    def test_one_such_program_no_longer_fails_the_pooled_bound_for_the_others(self):
        """Pooled with a program that agrees on every session: as registered the pair read (15 + 28) / 57 = 75%."""
        a, pid_a, lots_a = self.live("hold3@1", HOLD3, missed_buys={D2})
        b, pid_b, lots_b = self.live("range@1", RANGE, base=500)
        self.night(END)
        out = forward_twins.a14_reading(self.root, self.closes(a, lots_a) + self.closes(b, lots_b, base=500))
        self.assertEqual((out["intents"]["instances"], out["intents"]["sessions"], out["intents"]["agreed"]), (2, 57, 56))
        self.assertTrue(out["intents"]["ok"] and out["holds"])
        self.assertEqual((out["rebase"]["rebases"], out["rebase"]["sessions"], out["rebase"]["agreed"]), (1, 57, 43))
        self.assertLess(out["rebase"]["share"], forward_db.A14_AGREE)

    def test_one_night_at_the_end_writes_what_thirty_nights_wrote(self):
        """The twin's book lives nowhere: it is recomputed from the rows, the live book and the store. A store
        filled one night at a time and one filled in a single night hold the same rows."""
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        self.nights()
        nightly = [[r[c] for c in (*REGISTERED[:7], *REGISTERED[8:], "rebased", "base_agree")] for r in self.rows(iid)]
        other = Path(tempfile.mkdtemp(dir=self.root))
        db = forward_db.open_db(other)
        self.addCleanup(db.close)
        fx.register(db, "hold3@1", HOLD3)
        (other / forward_twins.LIVE_DB).write_bytes((self.root / forward_twins.LIVE_DB).read_bytes())
        forward_twins.finish(other, db, self.shadow(END), now=at(END, 18, 35))
        once = [[r[c] for c in (*REGISTERED[:7], *REGISTERED[8:], "rebased", "base_agree")]
                for r in db.execute("SELECT * FROM fwd_twins ORDER BY day")]
        self.assertEqual(once, nightly)


class ItCountsAgainAndReBasesAgain(Rebase):
    def test_a_buy_missed_two_sessions_running_differs_twice(self):
        """The buy is missed in `D2`'s window and again in `D3`'s. Decision 1: the live book buys again, the twin
        holds (differs; re-based on a flat book with one buy planned). The re-based twin's buy fills in `D3`, the
        live one is missed again: decision 2 differs again, and the twin is re-based again. Then agreement."""
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2, D3})
        self.nights()
        self.assertEqual(self.line(iid), ".xx" + "." * 26)
        self.assertEqual([e["day"] for e in self.rebased()], [D2, D3])
        self.assertEqual([r["rebased"] for r in self.rows(iid)], [0, 0, 1] + [2] * 26)
        self.assertEqual(lots[0]["entry_day"], D4)

    def test_a_decide_that_recorded_nothing_differs_once(self):
        """`RANGE` buys at decision 0 and sells at decision 1; the decide of decision 1 records nothing (the House
        could not ask). The twin sold: THE differing session. As registered the live book, still holding, then sells
        where its twin buys, on every session after. Re-based, the twin holds the lot the live book holds (bought by
        the engine in its own entry session) and both sell it at decision 2."""
        iid, pid, lots = self.live("range@1", RANGE, drop={D2})
        self.nights()
        self.assertEqual(self.line(iid), ".x" + "." * 27)
        self.assertEqual(self.line(iid, "base_agree"), "." + "x" * 28)
        [event] = self.rebased()
        self.assertEqual((event["payload"]["held"], event["payload"]["unheld"], event["payload"]["planned"]),
                         ([["SPY", D2, "open"]], 0, {"buys": 0, "sells": 0, "exits": 0}))
        rows = self.rows(iid)
        self.assertEqual((json.loads(rows[2]["live_keys"]), rows[2]["shadow_keys"]),
                         ([f"S|SPY|open|{D2}"], rows[2]["live_keys"]), "the seeded lot keeps the live lot's entry day")


class ABookThatIsNotFlat(Rebase):
    def test_a_missed_exit_is_carried_and_the_twin_follows_the_live_book(self):
        """`RANGE`'s sale of its first lot, decided at decision 1 for `D3`'s open, is missed all of `D3` and carried
        to `D4`'s open by the House. Decision 2: the live book still holds the lot and sells it again; its twin sold
        and buys: THE differing session. The live book after it: one lot, one sell of the program's, one exit of the
        House's planned for the next open. The re-based twin sells it there, and both buy at decision 3."""
        iid, pid, lots = self.live("range@1", RANGE, missed_exits={D3})
        self.nights()
        self.assertEqual(self.line(iid), "..x" + "." * 26)
        [event] = self.rebased()
        self.assertEqual((event["day"], event["payload"]["held"], event["payload"]["unheld"], event["payload"]["planned"]),
                         (D3, [["SPY", D2, "open"]], 0, {"buys": 0, "sells": 1, "exits": 1}))
        self.assertEqual((lots[0]["entry_day"], lots[0]["exit_day"]), (D2, D4))
        rows = {r["day"]: r for r in self.rows(iid)}
        self.assertEqual(json.loads(rows[D4]["shadow_keys"]), ["B|SPY|open"])
        # As registered the book stayed a session behind for good: every later session differs.
        self.assertEqual(self.line(iid, "base_agree"), ".." + "x" * 27)

    def test_the_seed_is_read_from_rows_the_book_never_rewrites(self):
        iid, pid, lots = self.live("range@1", RANGE, missed_exits={D3})
        book = forward_twins.read_book(self.root / forward_twins.LIVE_DB)
        seed = forward_twins.live_seed(book, iid, D3)
        self.assertEqual((seed["after"], seed["next"]), (D3, D4))
        self.assertEqual(seed["lots"], [{"lid": 101, "symbol": "SPY", "entry_day": D2, "entry_at": "open", "tag": "",
                                         "size": {"share": 0.2}}])
        self.assertEqual((seed["buys"], seed["sells"], seed["exits"]),
                         ([], [{"lid": 101, "at": "open", "tag": "range"}], [{"lid": 101, "reason": "program"}]))
        # Every status and every later day of the book may move: the seed of a past session does not.
        self.book.db.execute("UPDATE eq_intents SET status='missed', why='moved', updated_at=9")
        self.book.db.execute("UPDATE eq_lots SET status='closed', qty='0', mark='1'")
        self.book.db.commit()
        self.assertEqual(forward_twins.live_seed(forward_twins.read_book(self.root / forward_twins.LIVE_DB), iid, D3), seed)
        flat = forward_twins.live_seed(book, iid, D1)
        self.assertEqual((flat["lots"], flat["sells"], flat["exits"]), ([], [], []))
        self.assertEqual(flat["buys"], [{"symbol": "SPY", "at": "open", "tag": "range", "size": {"share": 0.2}}])

    def test_the_book_is_only_read(self):
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        self.book.close()
        before = (self.root / forward_twins.LIVE_DB).read_bytes()
        with guard.readonly():
            book = forward_twins.read_book(self.root / forward_twins.LIVE_DB)
        self.assertEqual(sorted(book), ["decision_day", "exits", "instances", "intents", "lots", "since"])
        self.night(END)
        self.assertEqual((self.root / forward_twins.LIVE_DB).read_bytes(), before)


class TheTwinsOwnMemory(Rebase):
    def test_only_the_book_is_set_the_programs_instance_goes_on(self):
        """`CLOCK` keeps a count in memory and buys on every third decide (decisions 0, 3, 6, ...), selling each lot
        at the next open. Its buy of decision 3 is missed in the next session's close window: at decision 4 the twin
        sells the lot it bought and the live book has none (THE differing session). The re-based twin is the SAME
        instance, asked every session since its load: its count is the twin's own, so it buys at decision 6 as the
        live program does. (A fresh instance would start its count again at the re-base and buy at decision 5.)"""
        days = forward_twins._sessions(forward_twins._date(D1), forward_twins._date(END))
        iid, pid, lots = self.live("fake-clock@1", CLOCK, missed_buys={days[4]})
        self.nights()
        self.assertEqual(self.line(iid), "....x" + "." * 24)
        self.assertEqual(self.line(iid, "base_agree"), "....x" + "." * 24, "this program is back in step by itself")
        self.assertEqual([e["day"] for e in self.rebased()], [days[4]])
        rows = self.rows(iid)
        self.assertEqual([json.loads(r["shadow_keys"]) for r in rows[5:8]],
                         [[], ["B|SPY|close"], [f"S|SPY|open|{days[7]}"]])


class WhatDoesNotReBase(Rebase):
    def test_a_retired_instance_is_unreadable_and_re_bases_nothing(self):
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        self.book.db.execute("UPDATE eq_instances SET retired_at=? WHERE id=?", (at("2026-10-16", 16, 25), iid))
        self.book.db.commit()
        self.night("2026-10-30")
        rows = self.rows(iid)
        self.assertEqual([(r["day"], r["agree"], r["why"]) for r in rows if r["why"]][0], ("2026-10-16", None, "retired"))
        self.assertEqual({r["base_agree"] for r in rows if r["why"] == "retired"}, {None})
        self.assertEqual([e["day"] for e in self.rebased()], [D2], "the one difference before it; none after")

    def test_a_night_whose_re_base_is_interrupted_keeps_the_rows_before_it_and_the_next_night_goes_on(self):
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        self.night(D3)                                              # the rows of D1 and D2, the second differing
        self.assertEqual(self.line(iid), ".x")
        self.assertEqual(self.rebased(), [], "nothing to compare after it yet: no re-based twin was made")

        class Failing(InlineDecider):
            """A child that fails every decide asked of a re-based twin's instance."""

            def kind(self, kind, op, payload, **kw):
                if op == "decide" and payload["jobs"][0]["key"].startswith(forward_twins.REBASED_KEY):
                    raise RuntimeError("the child failed")
                return super().kind(kind, op, payload, **kw)

        out = self.night("2026-10-20", decider=Failing())
        self.assertEqual((out["interrupted"], out["failed"], out["twins"]), (1, 0, 0))
        self.assertEqual(self.line(iid), ".x")
        [event] = forward_db.events(self.db, "twin_interrupted")
        self.assertEqual((event["day"], event["payload"]["instance"]), ("2026-10-20", iid))
        out = self.night("2026-10-20")
        self.assertEqual((out["interrupted"], out["twins"], out["rebased"]), (0, 4, 1))
        self.assertEqual(self.line(iid), ".x....")

    def test_no_program_text_runs_in_the_jobs_own_process(self):
        """Every decide of a re-based twin is asked of the night's decider child, as the twin run's are."""
        asked = []

        class Counting(InlineDecider):
            def kind(self, kind, op, payload, **kw):
                if op == "decide":
                    asked.append(payload["jobs"][0]["key"])
                return super().kind(kind, op, payload, **kw)

        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        # The engine account is handed a runner that is the re-based twin itself: it never starts the program.
        with mock.patch.object(forward_twins.RebasedTwin, "decide", autospec=True,
                               side_effect=forward_twins.RebasedTwin.decide) as engine_asks:
            self.night(END, decider=Counting())
        self.assertEqual(engine_asks.call_count, 27, "the engine's own account asked every decide after the re-base")
        twin, again = "e3-twin:hold3@1", f"{forward_twins.REBASED_KEY}hold3@1"
        self.assertEqual(set(asked), {twin, again})
        self.assertEqual((asked.count(twin), asked.count(again)), (29, 29),
                         "the twin run's pass, and one instance asked every session in order")


# ============================================================================================ the engine's own account
class TheEnginesOwnAccount(Rebase):
    def test_a_twin_re_based_on_its_own_runs_book_is_that_run(self):
        """THE SEAM (league/equity/engine.py `_Account` is the engine's own, and private): set to the book the twin
        run itself holds after any session, with what that run had decided for the next, the re-based twin answers
        the run's own keys on every later session, bars hash for bars hash. A change of the engine that breaks the
        seam fails here by name."""
        pid = fx.register(self.db, "fake-overnight@1", OVERNIGHT)
        program = forward_db.program(self.db, "fake-overnight@1")
        run = self.shadow(END).run_from(program, schedule.next_session(forward_twins._date(D1)))
        decisions = forward_twins._twin(self.decider, run)
        answered = dict(fx.decide_loop(self.decider, run)[i][:2] for i in range(len(decisions)))
        lots = run.result["lots"]
        for cut in (0, 1, 7):
            after = decisions[cut][0]
            nxt = schedule.next_session(forward_twins._date(after)).isoformat()
            held = [lot for lot in lots if lot["entry_day"] <= after and not (lot["exit_day"] and lot["exit_day"] <= after)]
            ids = {int(lot["lid"]) for lot in held}
            seed = {"after": after, "next": nxt,
                    "lots": [{"lid": int(lot["lid"]), "symbol": lot["symbol"], "entry_day": lot["entry_day"],
                              "entry_at": lot["entry_at"], "tag": "", "size": {"share": 0.4}} for lot in held],
                    "buys": [{"symbol": i["buy"], "at": i["at"], "tag": i.get("tag") or "", "size": {"share": i["share"]}}
                             for i in answered[after] if "buy" in i],
                    "sells": [{"lid": int(i["sell"]), "at": i["at"], "tag": i.get("tag") or ""}
                              for i in answered[after] if "sell" in i and int(i["sell"]) in ids],
                    "exits": []}
            twin = forward_twins.RebasedTwin(self.decider, run)
            try:
                self.assertEqual(twin.rebase(seed), {"held": len(held), "unheld": 0})
                later = [(day, *twin.step(day)) for day, _keys, _bars in decisions[cut + 1:]]
            finally:
                twin.close()
            self.assertEqual(later, decisions[cut + 1:], f"re-based after {after}")
        self.assertIsNone(twin.step(END), "no decision at the bars' last session")

    def test_a_lot_the_gym_cannot_hold_is_counted_and_not_held(self):
        pid = fx.register(self.db, "hold3@1", HOLD3)
        run = self.shadow(END).run_from(forward_db.program(self.db, "hold3@1"),
                                        schedule.next_session(forward_twins._date(D1)))
        seed = {"after": D3, "next": D4, "buys": [], "sells": [], "exits": [], "lots": [
            {"lid": 1, "symbol": "QQQ", "entry_day": D2, "entry_at": "open", "tag": "", "size": {"share": 0.4}},
            {"lid": 2, "symbol": "QQQ", "entry_day": D3, "entry_at": "open", "tag": "", "size": None},          # no buy
            {"lid": 3, "symbol": "IWM", "entry_day": D3, "entry_at": "open", "tag": "", "size": {"share": 0.1}},  # NEEDS
            {"lid": 4, "symbol": "QQQ", "entry_day": "2026-09-01", "entry_at": "open", "tag": "", "size": {"usd": 50.0}}]}
        twin = forward_twins.RebasedTwin(self.decider, run)
        self.addCleanup(twin.close)
        self.assertEqual(twin.rebase(seed), {"held": 1, "unheld": 3})
        self.assertEqual([(lot.symbol, twin.days[lot.entry_index]) for lot in twin.account.lots.values()], [("QQQ", D2)])
        with self.assertRaises(ValueError):
            twin.rebase({**seed, "after": "2026-10-20"})            # never out of the order of its sessions


# ============================================================================================ the store
OLD_TWINS = """CREATE TABLE IF NOT EXISTS fwd_twins (
  instance TEXT NOT NULL, day TEXT NOT NULL, pid INTEGER NOT NULL, live_keys TEXT NOT NULL, shadow_keys TEXT NOT NULL,
  agree INTEGER, why TEXT, at REAL NOT NULL, live_bars TEXT, shadow_bars TEXT,
  cause TEXT CHECK (cause IS NULL OR cause IN ('bars','program','unknown')),
  PRIMARY KEY (instance, day));"""


def old_schema() -> str:
    """`forward_db.SCHEMA` with `fwd_twins` as the release before this one declared it."""
    schema = forward_db.SCHEMA
    start = schema.index("CREATE TABLE IF NOT EXISTS fwd_twins (")
    end = schema.index("CREATE TABLE IF NOT EXISTS fwd_part")
    return schema[:start] + OLD_TWINS + "\n" + schema[end:]


def old_row(db, instance: str, day: str, agree, *, pid: int = 1, cause=None, why=None) -> None:
    db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, shadow_bars, "
               "cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (instance, day, pid, "[]", "[]", agree, why, 1.0, None, "f" * 16,
                                                         cause))


@unittest.skipUnless(HAVE, "numpy not installed")
class AStoreFromBeforeTheRelease(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        db = sqlite3.connect(self.root / forward_db.DB)
        db.executescript(old_schema())
        old_row(db, "a@1:r", D1, 1)
        old_row(db, "a@1:r", D2, 0, cause="program")
        old_row(db, "a@1:r", D3, None, why="split")
        db.commit()
        self.before = [tuple(r) for r in db.execute("SELECT * FROM fwd_twins ORDER BY day")]
        self.declared = db.execute("SELECT sql FROM sqlite_master WHERE name='fwd_twins'").fetchone()[0]
        db.close()

    def test_a_reader_asks_before_it_selects_and_reads_the_old_rows_as_they_were(self):
        db = forward_db.open_db(self.root, readonly=True)
        self.addCleanup(db.close)
        self.assertFalse(forward_db.has_column(db, "fwd_twins", "rebased"))
        with self.assertRaises(ValueError):
            forward_db.has_column(db, "eq_lots", "rebased")
        rows, read = forward_twins._twin_rows(self.root, ["a@1:r"])
        self.assertTrue(read, "an unmigrated store is read, never unmeasured")
        self.assertEqual({day: (r["agree"], r["rebased"], r["base_agree"]) for day, r in rows["a@1:r"].items()},
                         {D1: (1, None, None), D2: (0, None, None), D3: (None, None, None)})
        fills = forward_report._fills(db)
        self.assertEqual(fills["rebase"], {"rebases": 0, "sessions": 2, "agreed": 1, "share": 0.5, "by_instance": []})

    def test_the_first_writable_open_adds_the_columns_and_rewrites_no_row(self):
        db = forward_db.open_db(self.root)
        self.addCleanup(db.close)
        self.assertTrue(forward_db.has_column(db, "fwd_twins", "rebased") and forward_db.has_column(db, "fwd_twins",
                                                                                                  "base_agree"))
        fresh = sqlite3.connect(":memory:")
        self.addCleanup(fresh.close)
        fresh.executescript(forward_db.SCHEMA)
        columns = [tuple(r)[1:3] for r in db.execute("PRAGMA table_info(fwd_twins)")]
        self.assertEqual(columns, [tuple(r)[1:3] for r in fresh.execute("PRAGMA table_info(fwd_twins)")],
                         "the columns, in the order a new store declares them")
        after = [tuple(r) for r in db.execute("SELECT * FROM fwd_twins ORDER BY day")]
        self.assertEqual([row[:11] for row in after], self.before, "every old column of every old row as it was")
        self.assertEqual({row[11:] for row in after}, {(None, None)})
        # NO ROW WAS REWRITTEN: the table's pages are the bytes they were (the declaration alone changed).
        declared = db.execute("SELECT sql FROM sqlite_master WHERE name='fwd_twins'").fetchone()[0]
        self.assertNotEqual(declared, self.declared)
        self.assertIn("rebased INTEGER", declared)
        # The store is append-only still, the new columns included, and a second open changes nothing.
        for statement in ("UPDATE fwd_twins SET rebased=1", "DELETE FROM fwd_twins"):
            with self.assertRaises(sqlite3.DatabaseError) as raised:
                db.execute(statement)
            self.assertIn(forward_db.APPEND_ONLY_ERROR, str(raised.exception))
        self.assertEqual(forward_db._migrate(db), 0)
        db.close()
        again = forward_db.open_db(self.root)
        self.addCleanup(again.close)
        self.assertEqual([tuple(r) for r in again.execute("SELECT * FROM fwd_twins ORDER BY day")], after)

    def test_two_writers_adding_the_same_column_is_no_error(self):
        """Four jobs open the store for writing on the first night after a deploy: the one that looks, finds a column
        missing and loses the race to add it must read the column as there, not fail its open."""
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(forward_db.SCHEMA)
        with mock.patch.object(forward_db, "has_column", return_value=False):  # the look came before the other's ALTER
            self.assertEqual(forward_db._migrate(db), 0)
        self.assertTrue(all(forward_db.has_column(db, t, c) for t, c, _ in forward_db.ADDED_COLUMNS))

    def test_the_tables_pages_are_untouched_by_the_migration(self):
        """The rows' own bytes: every page of the store's file that holds a `fwd_twins` row is identical before and
        after (SQLite adds a nullable column by changing the declaration in its schema page; the rows keep their
        records, and read NULL in the columns they do not hold)."""
        path = self.root / forward_db.DB
        size = sqlite3.connect(path).execute("PRAGMA page_size").fetchone()[0]
        marker = b"a@1:r"
        before = path.read_bytes()
        held = [i for i in range(0, len(before), size) if marker in before[i:i + size]]
        self.assertTrue(held)
        db = forward_db.open_db(self.root)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        after = path.read_bytes()
        for i in held:
            self.assertEqual(after[i:i + size], before[i:i + size], f"page {i // size + 1}")

    def test_only_a_nullable_column_with_no_default_is_ever_added(self):
        for table, column, declaration in forward_db.ADDED_COLUMNS:
            self.assertIn(table, forward_db.TABLES)
            self.assertIn(declaration, ("INTEGER", "REAL", "TEXT"))
        self.assertEqual(forward_db.ADDED_COLUMNS, (("fwd_twins", "rebased", "INTEGER"),
                                                    ("fwd_twins", "base_agree", "INTEGER")))
        self.assertIn("twin_rebased", forward_db.ONCE_KINDS)
        self.assertEqual(forward_db.EVENT_KINDS["twin_rebased"], "D")


class RowsWrittenBeforeTheRelease(Rebase):
    """THE FIRST NIGHT AFTER THIS RELEASE, on the missed-first-buy book. The release before it compared every session
    with the un-re-based twin: decision 1 differs, and so do 4 and 5 (the book a session behind)."""

    def written_before(self, n: int):
        """The first `n` rows as the release before this one wrote them (its eleven columns, the twin run's keys)."""
        iid, pid, lots = self.live("hold3@1", HOLD3, missed_buys={D2})
        program = forward_db.program(self.db, "hold3@1")
        run = self.shadow(END).run_from(program, schedule.next_session(forward_twins._date(D1)))
        book = forward_twins.read_book(self.root / forward_twins.LIVE_DB)
        live = forward_twins._live_keys(book["intents"][iid], ["QQQ"])
        for day, keys, bars in forward_twins._twin(self.decider, run)[:n]:
            mine = live.get(day, [])
            agreed = forward_twins.agree(mine, keys)
            self.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, "
                            "shadow_bars, cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (iid, day, pid, json.dumps(mine), json.dumps(keys), int(agreed), None, 1.0, None, bars,
                             forward_twins.cause(agreed, None, bars)))
        self.db.commit()
        return iid, pid, lots, [tuple(r) for r in self.rows(iid)]

    def test_they_stand_and_the_latest_stored_differing_session_re_bases_the_sessions_not_yet_written(self):
        """Decisions 0 to 5 are stored. Tonight those six rows stand as written; the twin is set to the live book
        after the LATEST of them that differs (decision 5), and decisions 6 on are compared from there: they agree.
        No event is written for a session whose re-base never was (1 and 4: the session after each was written
        against the un-re-based twin)."""
        iid, pid, lots, before = self.written_before(6)
        days = forward_twins._sessions(forward_twins._date(D1), forward_twins._date(END))
        self.assertEqual(self.line(iid), ".x..xx")
        out = self.night(END)
        self.assertEqual([tuple(r) for r in self.rows(iid)][:6], before, "append-only: not a byte of them moved")
        self.assertEqual(self.line(iid), ".x..xx" + "." * 23)
        self.assertEqual([e["day"] for e in self.rebased()], [days[5]])
        self.assertEqual((out["rebased"], out["disagreed"]), (1, 0))
        rows = self.rows(iid)
        self.assertEqual([(r["rebased"], r["base_agree"]) for r in rows[:6]], [(None, None)] * 6)
        self.assertEqual([r["rebased"] for r in rows[6:]], [1] * 23)
        # The reading takes an old row's un-re-based answer from its `agree` (it was compared with that twin).
        reading = forward_twins.a14_reading(self.root, self.closes(iid, lots))
        self.assertEqual((reading["intents"]["sessions"], reading["intents"]["agreed"]), (29, 26))
        self.assertEqual((reading["rebase"]["rebases"], reading["rebase"]["sessions"], reading["rebase"]["agreed"]),
                         (1, 29, 15))

    def test_stored_sessions_that_agreed_after_it_are_gone_through_in_order(self):
        """Decisions 0 to 3 are stored (the differing one is decision 1; 2 and 3 agreed with the un-re-based twin).
        Tonight the twin is set to the live book after decision 1 and goes through the stored sessions 2 and 3 in
        order (their rows stand; nothing of them is compared again), and decisions 4 on, which as registered would
        differ at 4 and 5, agree. One night at a time gives the same rows."""
        iid, pid, lots, before = self.written_before(4)
        self.assertEqual(self.line(iid), ".x..")
        out = self.night("2026-10-20")
        self.assertEqual((out["twins"], out["rebased"], out["disagreed"], out["interrupted"]), (2, 1, 0, 0))
        self.nights("2026-10-21")
        self.assertEqual([tuple(r) for r in self.rows(iid)][:4], before)
        self.assertEqual(self.line(iid), ".x.." + "." * 25)
        self.assertEqual(self.line(iid, "base_agree")[4:], "xx" + "..xx" * 5 + "..x")
        self.assertEqual([e["day"] for e in self.rebased()], [D2])
        self.assertEqual([r["rebased"] for r in self.rows(iid)[4:]], [1] * 25)


# ============================================================================================ the report
class TheReport(Rebase):
    def test_the_forward_report_says_the_re_bases_and_the_un_re_based_agreement_beside_each_live_instance(self):
        a, pid_a, lots_a = self.live("hold3@1", HOLD3, missed_buys={D2})
        b, pid_b, lots_b = self.live("range@1", RANGE, base=500)
        self.night(END)
        forward_db.tag(self.db, pid_a, "live", "", at=1.0)
        fills = forward_report._fills(self.db)
        self.assertEqual(fills["intents"]["sessions"], 58)
        self.assertEqual((fills["intents"]["agreed"], fills["intents"]["disagreed"]), (57, 1))
        self.assertEqual(fills["rebase"], {"rebases": 1, "sessions": 58, "agreed": 44, "share": 44 / 58, "by_instance": [
            {"instance": a, "pid": pid_a, "rebases": 1, "sessions": 29, "agreed": 15, "share": 15 / 29}]})
        row = fills["by_instance"][0]
        self.assertEqual((row["instance"], row["sessions"], row["agreed"], row["disagreed"]), (a, 29, 28, 1))


if __name__ == "__main__":
    unittest.main()
