"""PREREG-EVL-6 (release 1019i): one money-weighted session-block screen for every seat, on invented data only.

The frozen text (docs/prereg/PREREG-EVL-6.md, tag prereg-evl-6, sha256 0f67f94e..., REGISTERED_AT_6
2026-10-22T12:24:50Z, A116) as built, each requirement with a test that fails without it:

- THE NEW VERSIONS (section 1.1): version 3 of PREREG-EVL-3's nine, version 2 of PREREG-EVL-4's and -5's three and of
  every seatable birth registered before REGISTERED_AT_6, each its superseded version's row word for word, registered
  at REGISTERED_AT_6, SEATING in the ids' order; every superseded version a shadow record that seats no more; a birth
  registered after REGISTERED_AT_6 judged by PREREG-EVL-6 at its version 1.
- THE D7 GUARD: no PREREG-EVL-3 look of a superseded version moves a band from REGISTERED_AT_6, written all the same.
- THE RECORD BEFORE THE RELEASE (D8) and THE ISSUER RULE (D12, section 1.1's TEST sentence).
- THE SCREEN (sections 1.2-2): values, the exact and Monte Carlo p, seeds and tags, alpha(S), RETIRE before PASS, every
  guard, looks at the record's own S keyed by their tag, merged thresholds, minimums; league/tests/
  test_events_evl6_calib.py reproduces calib_v2.py and demotion_v2.py on their own synthetic arrays.
- RUNS (sections 2-3): the 60th block ends the run; run n + 1 with its own tag, charged 0.13 when it starts, only when
  the lane's budget (3.9) holds it, in registration order; a waiting version has no look; births after waiting runs.
- STAYS (section 3): the fixed reads at p <= 0.15 at every 100th Probe+ event, the 10% money stop over the whole stay,
  the order at a close once its own real-money events have settled (final or not: only the look waits), an older
  unsettled event never holding a later close, one unsettled past the ladder judged without, the stay's lower tail,
  Sized's real-money conditions.
- THE MONEY (section 6): `event.max_open_v6.probe` 14 for these versions alone, the under-bar skip before a slot, the
  fewest whole shares that reach Done's bar (a cap's cut under it skips the buy), a Probe lot unsold past the ladder
  holding the version's Probe buys, the seat's room and issuers with the superseded version's open lots, a superseded
  seat's instance retired.
- THE COUNT (section 5): 0.13 a version or run of 3.9, three ways, per version beside; R3's validator.
- THE PROOF: an invented week's real-money picks are identical with and without the change, no superseded band moves.
- THE REPORT AND THE SITE; release 1019h's re-review minors in births.py and house.py; the docs and the wall.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import itertools
import json
import math
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league import ci
from league import constitution as K
from league.events import bands as BA
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import programs as P
from league.events import report as RP
from league.events import screen as SC
from league.events import store as S
from league.tests import equity_design as X
from league.tests import evl6_fakes as F6

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]
R6 = S.parse_iso(P.REGISTERED_AT_6)
NINE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1", "EVL-ERN-REACT-ON",
        "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON")
FOUR = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON")
FIVE = ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON")


def et(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=NY).astimezone(UTC)


def seat(program: str) -> P.Program:
    """The seating version of an id (its PREREG-EVL-6 version)."""
    return next(p for p in P.SEATING if p.id == program)


class Lane6:
    """An invented lane store with weekday sessions from Sept 1, 2026 to Mar 31, 2027 (09:30-16:00 ET), and the means to
    write settled shadow events, filings for their knowable times, real fills and the release's mark."""

    def __init__(self, root: Path):
        self.st = S.Store(root)
        day = dt.date(2026, 9, 1)
        with self.st.tx() as db:
            while day <= dt.date(2027, 3, 31):
                if day.weekday() < 5:
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, 0)",
                               (day.isoformat(), S.iso(et(day, 9, 30)), S.iso(et(day, 16, 0))))
                day += dt.timedelta(days=1)
        self.n = 0

    def close(self) -> None:
        self.st.close()

    def days(self, first: dt.date, n: int) -> list[dt.date]:
        return [s.day for s in C.sessions(self.st, first, first + dt.timedelta(days=3 * n + 10))][:n]

    def filing(self, accession: str, knowable: dt.datetime, cik: str = "1") -> None:
        self.st.db.execute("INSERT OR IGNORE INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, status) VALUES(?, '8-K', ?, 'Invented', '[\"2.02\"]', ?, ?, ?, 'current', "
                           "'fetched')", (accession, cik, S.iso(knowable - dt.timedelta(minutes=10)), S.iso(knowable),
                                          S.iso(knowable)))

    def intent(self, prog: P.Program, event: str, day: dt.date, cik: str, *, status: str = "planned",
               rank: float | None = None, exit_day: dt.date | None = None, why: str | None = None) -> None:
        session = C.session(self.st, day)
        decided = session.open_decide if prog.entry_at == "open" else session.close_decide
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, 'INVT', ?, ?, ?, ?, ?, ?, ?, "
                           "'shadow', ?, ?)", (prog.id, prog.version, event, cik, S.iso(decided), day.isoformat(),
                                               prog.entry_at, (exit_day or day).isoformat(), prog.exit_at, rank, status,
                                               why))

    def settled(self, prog: P.Program, day: dt.date, events: list[tuple[str, float, float]], *,
                ranks: list[float] | None = None) -> list[str]:
        """Settled shadow events of `prog` entering `day` (each (issuer, a, r), TRADABLE), knowable after its
        registration; returns their ids."""
        out = []
        for i, (cik, a, r) in enumerate(events):
            self.n += 1
            event = f"8k:inv-{self.n}"
            self.filing(event[3:], et(day, 8, 0) if prog.entry_at == "open" else et(day, 12, 0), cik)
            self.intent(prog, event, day, cik, status="exited", rank=None if ranks is None else ranks[i])
            self.st.db.execute("INSERT INTO outcomes(program, version, event, r, b, a, tradable, settled_at, status) "
                               "VALUES(?, ?, ?, ?, ?, ?, 1, ?, 'settled')",
                               (prog.id, prog.version, event, r, r - a, a, S.iso(et(day, 20, 0))))
            out.append(event)
        return out

    def real(self, prog: P.Program, day: dt.date, event: str, *, r: float, band: str = "probe", qty: int = 10,
             buy: float = 10.0, target: float | None = 100.0, sized: float | None = 100.0, gap_bp: float = 0.0) -> None:
        """A settled real-money round trip of `event` (bought at the day's open, sold at its close), the shadow's auction
        prices `gap_bp` from the fills."""
        sell = buy * (1.0 + r)
        BA.record_fill(self.st, program=prog.id, version=prog.version, event=event, side="buy", qty=qty, price=buy,
                       fee=0.0, filled_at=S.iso(et(day, 9, 30)), band=band, target_usd=target, sized_usd=sized)
        BA.record_fill(self.st, program=prog.id, version=prog.version, event=event, side="sell", qty=qty, price=sell,
                       fee=0.0, filled_at=S.iso(et(day, 16, 0)), band=band)
        self.st.db.execute("UPDATE outcomes SET entry_px=?, exit_px=? WHERE program=? AND version=? AND event=?",
                           (buy / (1 + gap_bp / 1e4), sell * (1 + gap_bp / 1e4), prog.id, prog.version, event))

    def mark(self, moment: dt.datetime) -> None:
        P.mark_release(self.st, moment)


class LaneCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(P.load_births, None)
        self.lane = Lane6(Path(self.tmp.name) / "events")
        self.addCleanup(self.lane.close)
        self.st = self.lane.st


def final(day: dt.date):
    """`screen.final_until` read as every close through `day` final (the looks' own finality is release 1019b's and
    its tests'; these hold PREREG-EVL-6's rules on a final record)."""
    return mock.patch.object(SC, "final_until", lambda store, program, version, today, now: (day, "final (test)"))


def birth(st: S.Store, ident: str, registered: str, *, seq: int = 0, family: str = "8k", rule: dict | None = None,
          entry: str = "open", exit_: str = "close", rank: str = "none", seatable: bool = True) -> None:
    sp = {"id": ident, "version": 1, "family": family, "rule": rule or {"items": ["5.02"]}, "entry": entry, "exit": exit_,
          "hold": 1, "rank": rank, "seatable": seatable}
    text = BI.canonical(sp)
    st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
                  "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, ?, ?, ?, ?, 'docs/births/x.jsonl', ?, ?, "
                  "'{}', 'invented', 'captain', ?)",
                  (ident, BI.sha(sp), text, int(seatable), registered, registered, registered, "c" * 40, seq,
                   registered[:10]))


# =============================================================================================== 1.1 the new versions
class TheNewVersions(unittest.TestCase):
    def test_fifteen_new_versions_each_its_superseded_row_word_for_word_registered_at_r6(self):
        self.assertEqual(P.REGISTERED_AT_6, "2026-10-22T12:24:50Z", "A116")
        self.assertEqual(len(P.SEATING), 15)
        old = F6.table_1019h()["SEATING"]
        self.assertEqual([p.id for p in P.SEATING], [p.id for p in old], "the ids' order: ROOM's order unchanged")
        for new, before in zip(P.SEATING, old):
            self.assertEqual((new.regfile, new.version), (P.FILE_6, before.version + 1), new.id)
            self.assertEqual(new.registered_at, R6, new.id)
            self.assertTrue(new.evl6 and new.can_seat and not new.superseded6, new.id)
            sup = P.superseded_of(new)
            self.assertEqual(sup.key, before.key)
            self.assertTrue(sup.superseded6 and not sup.can_seat, sup.key)
            self.assertEqual(dataclasses.replace(sup, version=new.version, regfile=P.FILE_6), new,
                             "word for word: family, windows, rule, ranking, hold, exit and its file's real-money rules")
            self.assertIs(P.successor_of(sup), new)
        self.assertEqual({p.id: p.version for p in P.SEATING}, {**{i: 3 for i in NINE}, **{i: 2 for i in FOUR + FIVE}})
        self.assertEqual([p.key for p in EB.seatable()], [p.key for p in P.SEATING])
        for pid in NINE:
            self.assertIsNone(EB.program_of(pid, 2), "a superseded version never trades again")
            self.assertIsNone(EB.program_of(pid, 1))
        for pid in FOUR + FIVE:
            self.assertIsNone(EB.program_of(pid, 1))
        self.assertEqual([EB.order_of(p.id) for p in P.SEATING], list(range(15)))

    def test_a_birth_before_r6_seats_at_its_version_2_and_one_after_at_its_version_1_judged_by_preregevl6(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp))
            self.addCleanup(st.close)
            self.addCleanup(P.load_births, None)
            birth(st, "EVL-B-EARLY", "2026-10-22T02:00:00Z", seq=0)
            birth(st, "EVL-B-LATE", "2026-10-23T01:20:00Z", seq=1, rule={"items": ["1.02"]})
            born = P.load_births(st)
            self.assertEqual([(p.id, p.version, p.regfile) for p in born],
                             [("EVL-B-EARLY", 1, None), ("EVL-B-EARLY", 2, 6), ("EVL-B-LATE", 1, None)])
            early1, early2, late = born
            self.assertTrue(early1.superseded6 and not early1.can_seat and not early1.evl6)
            self.assertEqual((early2.spec, early2.family, early2.registered_at), (early1.spec, early1.family, R6),
                             "same id and spec, registered at REGISTERED_AT_6")
            self.assertTrue(early2.evl6 and early2.can_seat)
            self.assertTrue(late.evl6 and late.can_seat and not late.superseded6, "section 1.1's LATER VERSIONS")
            self.assertEqual(late.registered_at, S.parse_iso("2026-10-23T01:20:00Z"), "its own registration time")
            self.assertEqual([p.key for p in P.SEATING[15:]], [("EVL-B-EARLY", 2), ("EVL-B-LATE", 1)],
                             "the births after every PREREG row, in registration order")


# =============================================================================================== 1.1 D7's guard
class TheD7Guard(LaneCase):
    def look(self, program: str, version: int, *, passed: bool, retire: bool = False) -> dict:
        at = S.iso(et(dt.date(2026, 10, 28), 16, 0))
        return {"program": program, "version": version, "k": 1, "at": at, "sessions": 8, "n": 60, "issuers": 40,
                "blocks": 8, "mean_a": 0.01, "mean_r": 0.01, "mean_a_tradable": 0.01, "p": 0.001, "alpha": 0.018,
                "fp_check": 0.0, "held": 1, "passed": int(passed), "why": "pass" if passed else "fail",
                "retirement": {"retire": retire, "p_below": 0.01}}

    def test_no_preregevl3_look_of_a_superseded_version_moves_a_band_and_each_is_written(self):
        now = et(dt.date(2026, 10, 28), 20, 30)
        for pid, version in [(p.id, p.version) for p in F6.table_1019h()["SEATING"]]:
            for passed, retire in ((True, False), (False, True)):
                look = self.look(pid, version, passed=passed, retire=retire)
                look["k"] = 1 if passed else 2
                self.assertTrue(BA.superseded_guard(look, now), pid)
                moved = []
                self.assertTrue(SC.write_look(self.st, look, apply=lambda db, look=look: moved.append(
                    BA.on_look(self.st, look, now=now, db=db)), now=now), "the look is written")
                self.assertEqual(moved, [None], (pid, version, passed))
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM bands").fetchone()[0], 0)
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM looks").fetchone()[0], 30, "every look on record")

    def test_the_guard_is_whatever_the_release_date_and_the_new_versions_are_not_guarded(self):
        look = self.look("EVL-ERN-READ-O1", 2, passed=True)
        for release in (None, et(dt.date(2026, 11, 30), 20, 5)):     # no mark, or a release long after the look
            if release is not None:
                self.lane.mark(release)
            self.assertIsNone(BA.on_look(self.st, look, now=et(dt.date(2026, 10, 28), 20, 30)))
        self.assertFalse(BA.superseded_guard(dict(look, version=3)), "a new version is PREREG-EVL-6's")
        with F6.before_evl6():
            self.assertFalse(BA.superseded_guard(look), "release 1019h's table: nothing superseded")

    def test_the_superseded_shadow_keeps_preregevl3s_looks_and_the_new_versions_preregevl6s(self):
        keys = [("EVL-ERN-READ-O1", 2), ("EVL-8K-REACT-ON", 1), ("EVL-ERN-READ-O1", 3), ("EVL-8K-REACT-ON", 2),
                ("EVL-ERN-READ-O1", 1)]
        with mock.patch.object(SC, "_run_v2", return_value={"written": [], "waiting": []}) as v2, \
                mock.patch.object(SC, "_run_v6", return_value={"written": [], "waiting": []}) as v6, \
                mock.patch.object(SC, "_run_v1", return_value={"written": [], "waiting": []}) as v1:
            SC.run(self.st, dt.date(2026, 11, 20), programs=keys, now=et(dt.date(2026, 11, 20), 20, 30))
        self.assertEqual([c.args[1:3] for c in v2.call_args_list], keys[:2])
        self.assertEqual([c.args[1:3] for c in v6.call_args_list], keys[2:4])
        self.assertEqual([c.args[1:3] for c in v1.call_args_list], keys[4:])


# =============================================================================================== 1.1 D8 and D12
class TheRecordBeforeTheRelease(LaneCase):
    OCT22, OCT23, OCT26 = dt.date(2026, 10, 22), dt.date(2026, 10, 23), dt.date(2026, 10, 26)

    def test_the_copy_is_the_superseded_intents_knowable_after_r6_with_their_skips_and_a_later_skip_follows(self):
        v2, v3 = P.BY_KEY[("EVL-ERN-READ-O1", 2)], seat("EVL-ERN-READ-O1")
        lane = self.lane
        lane.filing("early", R6 - dt.timedelta(minutes=5))       # knowable before REGISTERED_AT_6: never copied
        lane.filing("late", R6 + dt.timedelta(minutes=1))
        lane.filing("held", R6 + dt.timedelta(minutes=2))
        lane.intent(v2, "8k:early", self.OCT22, "1")
        lane.intent(v2, "8k:late", self.OCT22, "2", why=None)
        lane.intent(v2, "8k:held", self.OCT22, "3", status="skipped:issuer-held")
        lane.mark(et(self.OCT22, 16, 10))
        self.assertTrue(P.before_release(self.st, v3, self.OCT22))
        self.assertFalse(P.before_release(self.st, v3, self.OCT23))
        self.assertEqual(sorted(P.uncopied(self.st, v3, self.OCT26)), ["8k:held", "8k:late"])
        got = P.copy_before_release(self.st, v3, self.OCT22)
        self.assertEqual(got, {"copied": 2, "moved": 0, "known": 0})
        rows = {r["event"]: dict(r) for r in self.st.db.execute("SELECT * FROM intents WHERE program=? AND version=3",
                                                                (v3.id,))}
        self.assertEqual(sorted(rows), ["8k:held", "8k:late"], "only events knowable after REGISTERED_AT_6")
        self.assertEqual((rows["8k:late"]["status"], rows["8k:held"]["status"]), ("planned", "skipped:issuer-held"))
        self.assertIn("copied from v2", rows["8k:late"]["why"])
        self.assertEqual(P.uncopied(self.st, v3, self.OCT26), [])
        self.assertEqual(P.copy_before_release(self.st, v3, self.OCT22), {"copied": 0, "moved": 0, "known": 2})
        self.st.move_intent(v2.id, 2, "8k:late", "skipped:excluded", "a later row")
        self.assertEqual(P.uncopied(self.st, v3, self.OCT26), ["8k:late"], "a look waits for the skip to follow")
        self.assertEqual(P.copy_before_release(self.st, v3, self.OCT22)["moved"], 1)
        self.assertEqual(self.st.db.execute("SELECT status FROM intents WHERE program=? AND version=3 AND event='8k:late'",
                                            (v3.id,)).fetchone()[0], "skipped:excluded")

    def test_without_a_mark_every_session_is_before_the_release_and_the_catchup_copies_them(self):
        v2, v3 = P.BY_KEY[("EVL-INS-BUY-O1", 2)], seat("EVL-INS-BUY-O1")
        self.lane.filing("a", R6 + dt.timedelta(hours=1))
        self.lane.intent(v2, "8k:a", self.OCT26, "1")
        self.assertIsNone(P.release_at(self.st))
        self.assertTrue(P.before_release(self.st, v3, dt.date(2027, 1, 4)), "no mark: records only, copied")
        got = P.copy_all_before_release(self.st)
        self.assertEqual(got["copied"], 1)
        self.lane.mark(et(self.OCT26, 20, 0))
        self.assertEqual(P.mark_release(self.st, et(dt.date(2026, 12, 1), 20, 0)), et(self.OCT26, 20, 0),
                         "written once, never moved")

    def test_a_decision_before_the_release_copies_and_names_the_new_version_and_one_after_decides_it(self):
        from league.tests import evl5_world as W

        world = W.World(Path(self.tmp.name) / "world")
        self.addCleanup(world.close)
        W.evl4_rows(world)
        P.mark_release(world.st, et(W.D_DAY, 20, 10))       # Tue Oct 27, after its close decision
        W.decide_week(world)
        rows = {}
        for r in world.st.db.execute("SELECT program, version, event, entry_day, status FROM intents"):
            rows.setdefault((r["program"], r["entry_day"]), {}).setdefault(int(r["version"]), {})[r["event"]] = r["status"]
        checked = 0
        for (pid, day), by in rows.items():
            prog = P.BY_KEY.get((pid, max(by)))
            if prog is None or prog.regfile != P.FILE_6:
                continue
            sup, new = by.get(prog.version - 1, {}), by.get(prog.version, {})
            self.assertEqual(new, sup, (pid, day, "copied before the release, decided by itself after it: the same"))
            checked += 1
        self.assertGreater(checked, 5)
        receipt = json.loads(world.st.db.execute("SELECT summary FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                                 (f"decide-open:{W.D_DAY.isoformat()}",)).fetchone()[0])
        self.assertIn("copied_from", receipt["EVL-ERN-READ-O1@v3"], "a session decided before the release: its copy")
        after = json.loads(world.st.db.execute("SELECT summary FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                               (f"decide-open:{W.N_DAY.isoformat()}",)).fetchone()[0])
        self.assertNotIn("copied_from", after["EVL-ERN-READ-O1@v3"], "from the release on: decided by itself")


class TheFinalRecordOfANewVersion(LaneCase):
    """A new version's session before the release is read as its superseded version's decision; one from the release on
    is made for it only when its own receipt names it (a release without it, a rollback, decided it for nothing)."""

    def receipt(self, kind: str, day: dt.date, names: dict) -> None:
        rid = self.st.start_receipt(f"decide-{kind}:{day.isoformat()}", now=et(day, 9, 16))
        self.st.finish_receipt(rid, "ok", names, now=et(day, 9, 17))

    def test_before_the_release_the_superseded_key_from_it_its_own(self):
        prog = seat("EVL-INS-BUY-O1")
        days = self.lane.days(dt.date(2026, 10, 22), 12)
        self.lane.mark(et(days[3], 20, 10))
        for day in days[:4]:            # release 1019h's receipts: they name the superseded version alone
            self.receipt("open", day, {"EVL-INS-BUY-O1@v2": {"planned": 0}})
        for day in days[4:8]:
            self.receipt("open", day, {"EVL-INS-BUY-O1@v2": {}, "EVL-INS-BUY-O1@v3": {}})
        self.receipt("open", days[8], {"EVL-INS-BUY-O1@v2": {}})        # (a rollback's decision: v3 unnamed)
        horizon, why = SC.final_until(self.st, prog.id, 3, days[-1], et(days[-1], 20, 0))
        self.assertLess(horizon, days[8], why)
        self.assertIn(days[8].isoformat(), why)
        self.assertIn("made without its rows", why)


class TheIssuerRule(LaneCase):
    """Section 1.1's TEST sentence (D12), on the release's first session."""
    MON, TUE, WED = dt.date(2026, 10, 26), dt.date(2026, 10, 27), dt.date(2026, 10, 28)

    def candidate(self, event: str, cik: str) -> P.Candidate:
        self.lane.filing(event[3:], et(self.WED, 8, 0), cik)
        return P.Candidate(event, cik, "XXX", et(self.WED, 8, 0), 3.0, 3, {})

    def setUp(self):
        super().setUp()
        self.v2, self.v3 = P.BY_KEY[("EVL-ERN-READ-O1", 2)], seat("EVL-ERN-READ-O1")
        self.lane.mark(et(self.TUE, 20, 10))     # the release: Wed Oct 28 is its first session

    def decide(self, order):
        for prog in order:
            P.write_intents(self.st, prog, self.WED, [self.candidate("8k:x-wed", "777")],
                            decided_at=C.session(self.st, self.WED).open_decide)
        return self.st.db.execute("SELECT status FROM intents WHERE program=? AND version=3 AND event='8k:x-wed'",
                                  (self.v3.id,)).fetchone()[0]

    def test_both_select_x_and_neither_holds_it_the_new_version_writes_it_whichever_is_decided_first(self):
        self.assertEqual(self.decide((self.v2, self.v3)), "planned", "never skipped:issuer-held")

    def test_the_same_with_the_new_version_decided_first(self):
        self.assertEqual(self.decide((self.v3, self.v2)), "planned")
        self.assertEqual(self.st.db.execute("SELECT status FROM intents WHERE version=2 AND event='8k:x-wed'").fetchone()[0],
                         "planned", "the superseded version's own record, apart")

    def test_the_superseded_version_held_x_before_the_release_within_the_cooldown_so_the_new_version_skips_it(self):
        self.lane.filing("x-mon", R6 - dt.timedelta(minutes=30), "777")    # knowable BEFORE REGISTERED_AT_6: counts too
        self.lane.intent(self.v2, "8k:x-mon", self.MON, "777")
        self.assertEqual(self.decide((self.v3,)), "skipped:issuer-held")
        book = EB.Lane(self.st.root / S.DB_NAME)
        self.addCleanup(book.close)
        self.assertTrue(EB.held_recently(book, self.v3, "777", self.WED),
                        "real money's one position per issuer counts it the same (the book's reader)")

    def test_a_superseded_intent_of_a_session_from_the_release_on_never_counts(self):
        self.lane.intent(self.v2, "8k:x-wed0", self.WED, "777")
        self.assertIsNone(P.superseded_held(self.st, self.v3, "777", self.MON.isoformat(), "2026-11-10"))
        self.assertEqual(self.decide((self.v3,)), "planned")


# =============================================================================================== 1.2-1.4 the statistic
class TheStatistic(unittest.TestCase):
    def blocks(self, spec: list[tuple[int, float]]) -> list[SC.Block6]:
        rows, n = [], 0
        for i, (count, a) in enumerate(spec):
            for j in range(count):
                n += 1
                rows.append({"event": f"e{n:05d}", "entry_day": dt.date(2026, 11, 2) + dt.timedelta(days=i), "a": a,
                             "r": a + 0.001, "issuer": f"{n:05d}", "tradable": True, "rank_key": float(-j)})
        return SC.blocks6(rows)

    def test_the_values_are_money_weighted_with_the_10bp_margin_and_the_lower_tail_has_none(self):
        b = self.blocks([(20, 0.004), (3, -0.002), (14, 0.0)])
        self.assertEqual([x.n for x in b], [20, 3, 14])
        self.assertEqual(SC.v6_values(b), [14 * (0.004 - 0.0010), 3 * (-0.002 - 0.0010), 14 * (0.0 - 0.0010)])
        self.assertEqual(SC.v6_lower(b), [-14 * 0.004, -3 * -0.002, -14 * 0.0])
        self.assertEqual((SC.V6_CAP, SC.V6_MARGIN), (14, 0.0010))

    def test_exact_below_17_blocks_over_every_vector_and_the_seeded_monte_carlo_above(self):
        rng = random.Random(5)
        for S_ in (6, 11, 16):
            y = [rng.gauss(0.0005, 0.01) for _ in range(S_)]
            want = sum(1 for signs in itertools.product((-1, 1), repeat=S_)
                       if math.fsum(s * v for s, v in zip(signs, y)) >= math.fsum(y) - S_ * 1e-12) / 2 ** S_
            self.assertEqual(SC.v6_count_p(y, "x", 1), want, S_)
        y = [rng.gauss(0.001, 0.01) for _ in range(23)]
        text = SC.v6_seed_string("EVL-ERN-READ-O1", 3, "", 23)
        gen = random.Random(int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big"))
        count = 0
        for _ in range(999):
            bits = gen.getrandbits(23)
            total = math.fsum((v if bits >> j & 1 else -v) for j, v in enumerate(y))
            count += total >= math.fsum(y) - 23 * 1e-12
        self.assertEqual(SC.v6_count_p(y, text, 999), (1 + count) / 1000, "PREREG-EVL-1 section 7's Monte Carlo")
        self.assertEqual(SC.v6_count_p([0.01] * 20, text, 999), 1 / 1000, "the observed vector alone: the floor")
        self.assertEqual(SC.B, 99_999)

    def test_the_seed_strings_tags_keys_and_alpha(self):
        self.assertEqual([SC.v6_tag("run", 1), SC.v6_tag("run", 2), SC.v6_tag("stay", 1)], ["", "run2|", "stay1|"])
        self.assertEqual(SC.v6_seed_string("EVL-X", 3, "run2|", 25), "EVL-X|v3|evl6|run2|S25")
        self.assertEqual(SC.v6_seed_string("EVL-X", 2, "stay1|", 22) + "|issuer", "EVL-X|v2|evl6|stay1|S22|issuer")
        keys = {SC.look_key6("run", 1, 22), SC.look_key6("run", 2, 22), SC.look_key6("stay", 1, 22)}
        self.assertEqual(len(keys), 3, "a later run's or a stay's look is never a duplicate of an earlier one")
        for kind, n, S_ in (("run", 1, 22), ("run", 3, 60), ("stay", 2, 35)):
            self.assertEqual(SC.key_of6(SC.look_key6(kind, n, S_)), (kind, n, S_))
        self.assertEqual([SC.v6_alpha(s) for s in (21, 22, 30, 31, 40, 41, 60, 61)],
                         [None, 0.020, 0.020, 0.006, 0.006, 0.001, 0.001, None])
        self.assertEqual(SC.V6_LOOKS, (22, 25, 30, 35, 40, 50, 60))

    def test_the_moneys_events_are_book_picks_order(self):
        rows = [{"event": "b", "rank_key": None, "adv20": 9e9}, {"event": "a", "rank_key": 1.0, "adv20": None},
                {"event": "c", "rank_key": 2.0, "adv20": 1.0}, {"event": "d", "rank_key": 2.0, "adv20": 5.0},
                {"event": "e", "rank_key": 2.0, "adv20": 5.0}]
        self.assertEqual([r["event"] for r in sorted(rows, key=SC.rank_order)], ["d", "e", "c", "a", "b"],
                         "rank_key descending, a missing key last; then adv20 descending (missing as 0); then the id")


class TheJudge(unittest.TestCase):
    def rows(self, n_blocks=22, per=2, a=0.03, r=None, issuers=None, top=None) -> list[dict]:
        out, k = [], 0
        for i in range(n_blocks):
            for j in range(per):
                k += 1
                aa = a if top is None else (top if j < 14 else a)
                out.append({"event": f"e{k:05d}", "entry_day": dt.date(2026, 11, 2) + dt.timedelta(days=i), "a": aa,
                            "r": aa + 0.002 if r is None else r, "tradable": True, "rank_key": float(per - j),
                            "issuer": f"{(k if issuers is None else k % issuers):05d}"})
        return out

    def judge(self, rows, **kw):
        return SC.v6_judge(SC.blocks6(rows), program="EVL-X", version=3, tag="", draws=999, **kw)

    def test_a_clear_edge_passes_with_every_guard(self):
        got = self.judge(self.rows(a=0.03))
        self.assertEqual(got["decision"], "pass", got["why"])
        self.assertTrue(all(got["guards"].values()))
        self.assertEqual((got["S"], got["alpha"], got["seed"]), (22, 0.020, "EVL-X|v3|evl6|S22"))

    def test_each_guard_alone_fails_the_pass(self):
        self.assertIn("mean_r", self.judge(self.rows(a=0.03, r=-0.001))["why"])
        got = self.judge(self.rows(per=20, a=0.05, top=-0.01))   # every block's top 14 lose, its other six win more
        self.assertGreater(got["mean_a"], 0)
        self.assertIn("top14_a", got["why"], "the money's events: what Probe would buy")
        self.assertIn("issuers", self.judge(self.rows(a=0.03, issuers=20))["why"])
        ctl = [{"entry_day": dt.date(2026, 11, 2) + dt.timedelta(days=i), "a": 0.05, "tradable": True} for i in range(22)]
        got = self.judge(self.rows(a=0.03), control="EVL-CTRL", control_rows=ctl)
        self.assertIn("control", got["why"], "a READ version beats its control or fails")
        self.assertEqual(self.judge(self.rows(a=0.03), control="EVL-CTRL", control_rows=[])["decision"], None,
                         "no control block in these sessions: fails")

    def test_retire_comes_first_and_nothing_else_is_checked(self):
        got = self.judge(self.rows(a=-0.03))
        self.assertEqual(got["decision"], "retire")
        self.assertEqual(got["guards"], {}, "nothing else is checked at that look")

    def test_pass_has_no_tolerance_and_retire_its_1e12(self):
        rows = SC.blocks6(self.rows(a=0.03))
        with mock.patch.object(SC, "v6_count_p", side_effect=[0.020, 0.9] * 2):
            self.assertEqual(SC.v6_judge(rows, program="X", version=3, tag="", draws=9, beside=False)["decision"], "pass")
        with mock.patch.object(SC, "v6_count_p", side_effect=[0.020 + 5e-13, 0.9]):
            self.assertIsNone(SC.v6_judge(rows, program="X", version=3, tag="", draws=9, beside=False)["decision"])
        neg = SC.blocks6(self.rows(a=-0.001))
        with mock.patch.object(SC, "v6_count_p", side_effect=[0.9, 0.020 + 5e-13]):
            self.assertEqual(SC.v6_judge(neg, program="X", version=3, tag="", draws=9, beside=False)["decision"],
                             "retire")


# =============================================================================================== 2-3 looks and runs
class TheRuns(LaneCase):
    """Section 2's looks and section 3's runs, on the store, for EVL-INS-BUY-O1 v3 (open entry, no control)."""

    def setUp(self):
        super().setUp()
        self.prog = seat("EVL-INS-BUY-O1")
        self.lane.mark(et(dt.date(2026, 10, 22), 20, 10))
        self.first = dt.date(2026, 10, 26)

    def sessions(self, n: int, *, per: int = 2, a: float = 0.0, start: int = 0, first: dt.date | None = None,
                 swing: float = 0.02) -> list[dt.date]:
        days = self.lane.days(first or self.first, n)
        for i, day in enumerate(days):
            sign = 1 if (i * 7 + 3) % 5 < 3 else -1
            self.lane.settled(self.prog, day, [(f"{start + i * per + j:05d}", a + sign * swing * (1 if j % 2 else -0.5),
                                                a + sign * swing * (1 if j % 2 else -0.5) + 0.001) for j in range(per)])
        return days

    def screen(self, today: dt.date, **kw):
        with final(today):
            return SC.run(self.st, today, programs=[self.prog.key], now=et(today, 20, 30), **kw)

    def test_the_first_look_is_at_the_22nd_block_merged_thresholds_are_one_look_and_a_look_is_written_once(self):
        days = self.sessions(21, per=2, a=0.0)
        out = self.screen(days[-1])
        self.assertEqual(out["written"], [], "no look before the 22nd block")
        days += self.sessions(4, per=2, a=0.0, start=1000, first=days[-1] + dt.timedelta(days=1))
        out = self.screen(days[-1])
        look = min(SC.look_rows(self.st, *self.prog.key), key=lambda r: r["k"])
        self.assertEqual(SC.key_of6(look["k"]), ("run", 1, 22))
        self.assertEqual(look["at"], S.iso(C.session(self.st, days[21]).close_at), "as of the 22nd block's close")
        detail = SC.look_detail(self.st, *self.prog.key, look["k"])
        self.assertEqual((detail["v6"]["look"], detail["v6"]["S"], detail["v6"]["tag"]), (1, 22, ""))
        self.assertEqual(len([w for w in out["written"] if w.get("k")]), 2, "22 and 25: two looks")
        self.assertEqual(self.screen(days[-1])["written"], [], "written once, never again")

    def test_minimums_reached_late_merge_the_thresholds_they_passed(self):
        days = self.lane.days(self.first, 30)
        for i, day in enumerate(days):         # one event a session: 30 events and 30 issuers only at the 30th block
            self.lane.settled(self.prog, day, [(f"{i:05d}", 0.0, 0.001)])
        self.screen(days[-1])
        [look] = SC.look_rows(self.st, *self.prog.key)
        detail = SC.look_detail(self.st, *self.prog.key, look["k"])
        self.assertEqual((SC.key_of6(look["k"]), detail["v6"]["look"], detail["merged"]), (("run", 1, 30), 1, [2, 3]))
        self.assertEqual(detail["v6"]["alpha"], 0.020, "alpha(S) at the record's own S")

    def test_a_pass_moves_learning_to_probe_in_the_looks_transaction_and_a_retire_retires(self):
        days = self.sessions(22, per=2, a=0.02, swing=0.002)
        self.screen(days[-1])
        self.assertEqual(BA.bands(self.st)[self.prog.key], "probe")
        hist = self.st.db.execute("SELECT why FROM band_history WHERE program=? AND version=?", self.prog.key).fetchone()
        self.assertIn("PREREG-EVL-6 section 1.4", hist[0])
        other = seat("EVL-ERN-REACT-C1")
        days = self.lane.days(self.first, 22)
        for i, day in enumerate(days):
            self.lane.settled(other, day, [(f"9{i:04d}", -0.02 + 0.001 * (i % 3), -0.02), (f"8{i:04d}", -0.03, -0.03)])
        with final(days[-1] + dt.timedelta(days=7)):
            SC.run(self.st, days[-1] + dt.timedelta(days=7), programs=[other.key], now=et(days[-1], 23, 0))
        self.assertEqual(BA.bands(self.st)[other.key], "retired")

    def test_the_60th_block_ends_the_run_and_run_2_starts_with_its_own_tag_charged_when_the_budget_holds_it(self):
        days = self.sessions(60, per=1, a=0.0)
        before = SC.expected_false_passes(self.st)
        self.screen(days[-1])
        runs = SC.runs6(self.st, *self.prog.key)
        self.assertEqual([r["n"] for r in runs], [1, 2], "the end at the 60th block, then run 2 started at once")
        self.assertEqual(runs[0]["ended"]["why"], "horizon")
        self.assertEqual(runs[1]["after_day"], days[59].isoformat(), "run 2 starts with the 61st block")
        self.assertIsNone(runs[1]["after"], "the room held at the very close of the end")
        self.assertEqual(BA.bands(self.st)[self.prog.key], "learning", "a run's end is never a retirement")
        after = SC.expected_false_passes(self.st)
        self.assertEqual((after["runs"], round(after["expected"] - before["expected"], 2)), (1, 0.13), "charged 0.13")
        more = self.sessions(22, per=2, a=0.0, start=5000, first=days[-1] + dt.timedelta(days=1))
        self.screen(more[-1])
        tags = {SC.key_of6(r["k"])[:2] for r in SC.look_rows(self.st, *self.prog.key)}
        self.assertIn(("run", 2), tags, "run 2's looks under its own tag")
        k22 = SC.look_key6("run", 2, 22)
        self.assertEqual((SC.look_detail(self.st, *self.prog.key, k22) or {}).get("v6", {}).get("seed"),
                         f"{self.prog.id}|v3|evl6|run2|S22")

    def test_a_run_the_budget_cannot_hold_waits_with_no_look_and_births_after_the_waiting_runs(self):
        days = self.sessions(60, per=1, a=0.0)
        with mock.patch.object(SC, "V6_BUDGET_HUNDREDTHS", 195):     # (the fifteen new versions use it all)
            self.screen(days[-1])
            looks = len(SC.look_rows(self.st, *self.prog.key))
            self.assertEqual(looks, 5, "one event a session: 22, 25 and 30 merged at the 30th block, then 35-60")
            self.assertEqual([r["n"] for r in SC.runs6(self.st, *self.prog.key)], [1])
            [waits] = SC.waiting_runs(self.st)
            self.assertEqual((waits["program"], waits["n"]), (self.prog.id, 2))
            more = self.sessions(25, per=2, a=0.0, start=5000, first=days[-1] + dt.timedelta(days=1))
            out = self.screen(more[-1])
            self.assertEqual(len(SC.look_rows(self.st, *self.prog.key)), looks, "no look of the waiting version")
            self.assertTrue(any("waits for the budget" in w["why"] for w in out["waiting"]))
            self.assertEqual(BI.budget_waiting_hundredths(self.st), 13, "a birth waits behind it")
        started = SC.start_runs(self.st, et(more[-1], 21, 0))
        self.assertEqual([(r["program"], r["n"]) for r in started], [(self.prog.id, 2)])
        self.assertEqual(started[0]["after"], S.iso(C.session(self.st, more[-1]).close_at),
                         "started at a later close: only the entries decided after it")

    def test_waiting_runs_start_in_registration_order(self):
        early, late = seat("EVL-ERN-READ-O1"), seat("EVL-INS-BUY-O1")
        with mock.patch.object(SC, "runs6", lambda st, pid, v: [{"n": 1, "ended": {"why": "horizon", "at": None,
                                                                                    "last_day": "2026-12-01"}}]):
            order = [(w["program"], w["n"]) for w in SC.waiting_runs(self.st)]
        self.assertEqual(order, sorted(order), "every new version is registered at REGISTERED_AT_6: then the id")
        self.assertLess(order.index((early.id, 2)), order.index((late.id, 2)))


# =============================================================================================== 3 the stays
class TheStays(LaneCase):
    """Section 3's demotion and Sized for a version at Probe (league/events/bands.py `review6`), in its order."""

    def setUp(self):
        super().setUp()
        self.prog = seat("EVL-INS-BUY-O1")
        self.lane.mark(et(dt.date(2026, 10, 22), 20, 10))
        self.since = et(dt.date(2026, 11, 2), 1, 0)
        BA.set_band(self.st, self.prog.id, 3, "probe", since=S.iso(self.since), why="invented", now=self.since)
        self.days = self.lane.days(dt.date(2026, 11, 2), 40)

    def stay_day(self, day: dt.date, rs: list[float], *, real: bool = True, base: int = 0, gap_bp: float = 0.0) -> None:
        events = self.lane.settled(self.prog, day, [(f"{base + i:05d}", r - 0.001, r) for i, r in enumerate(rs)])
        if real:
            for event, r in zip(events, rs):
                self.lane.real(self.prog, day, event, r=r, gap_bp=gap_bp)

    def review(self, today: dt.date):
        with final(today):
            return BA.review(self.st, now=et(today, 20, 40))

    def test_a_fixed_read_at_the_100th_event_demotes_at_p_015(self):
        for i, day in enumerate(self.days[:10]):
            self.stay_day(day, [-0.02] * 10, base=100 * i)
        [moved] = self.review(self.days[9])
        self.assertEqual(moved["band"], "learning")
        self.assertIn("100th real-money Probe+ event", moved["why"])
        self.assertEqual(json.loads(self.st.meta(BA.STAY_KEY.format(program=self.prog.id, version=3, n=1)))["read"], 100)

    def test_the_money_stop_over_the_whole_stay_demotes_at_10_percent_of_the_buy_cost(self):
        self.stay_day(self.days[0], [-0.05] * 5, base=0)
        self.assertEqual(self.review(self.days[0]), [], "5% lost: inside the stop")
        self.stay_day(self.days[1], [-0.16] * 5, base=100)
        [moved] = self.review(self.days[1])
        self.assertIn("the money stop", moved["why"])
        self.assertIn("10%", moved["why"])

    def test_the_reads_go_before_the_money_stop_at_one_close(self):
        for i, day in enumerate(self.days[:9]):
            self.stay_day(day, [-0.05] * 10, base=100 * i)
        self.stay_day(self.days[9], [-0.9] * 10, base=900)
        [moved] = self.review(self.days[9])
        self.assertIn("fixed read", moved["why"], "the fixed reads first, then the money stop (section 3's order)")

    def stay_looks(self) -> list[dict]:
        return [r for r in SC.look_rows(self.st, *self.prog.key) if SC.key_of6(int(r["k"]))[0] == "stay"]

    def test_a_stay_look_due_at_a_close_not_final_never_holds_back_that_closes_reads_and_money_stop(self):
        """Section 3's order runs at each close once its real-money events have settled; only the stay's look waits
        for the close to be final (release 1019i's review, the judges' lens)."""
        for i, day in enumerate(self.days[:21]):
            self.stay_day(day, [0.002, 0.001], base=100 * i)
        self.stay_day(self.days[21], [-0.9] * 10, base=2100)    # the 22nd block: a stay look falls due at its close
        with final(self.days[20]):                              # (that close is not final yet: the fast path waits)
            [moved] = BA.review(self.st, now=et(self.days[21], 20, 40))
        self.assertEqual(moved["band"], "learning")
        self.assertIn("the money stop: the stay's 52 real-money Probe+ events", moved["why"])
        self.assertEqual(self.stay_looks(), [], "the look waited for its record; the stop did not wait for the look")
        self.assertEqual(BA.bands(self.st)[self.prog.key], "learning")
        self.assertGreaterEqual(SC.stays6(self.st, *self.prog.key)[-1]["until"], et(self.days[21], 16, 0))

    def test_only_the_look_waits_for_finality_and_it_is_held_as_of_its_close_once_final(self):
        for i, day in enumerate(self.days[:23]):
            self.stay_day(day, [0.002, -0.001], base=100 * i)
        state = lambda: json.loads(self.st.meta(BA.STAY_KEY.format(program=self.prog.id, version=3, n=1)))
        with final(self.days[20]):
            self.assertEqual(BA.review(self.st, now=et(self.days[21], 20, 40)), [])
        self.assertEqual(self.stay_looks(), [])
        self.assertEqual((state()["through"], state()["looked"]), (self.days[21].isoformat(), self.days[20].isoformat()),
                         "the reads and the stop judged the 22nd close; its look waits")
        with final(self.days[20]):
            BA.review(self.st, now=et(self.days[22], 20, 40))
        self.assertEqual(self.stay_looks(), [], "still not final: the look waits, the next close's reads and stop go on")
        self.assertEqual(state()["through"], self.days[22].isoformat())
        with final(self.days[22]):
            BA.review(self.st, now=et(self.days[22], 21, 40))
        [look] = self.stay_looks()
        self.assertEqual(S.parse_iso(look["at"]), et(self.days[21], 16, 0), "the look is as of the close it fell due at")
        self.assertEqual(SC.key_of6(int(look["k"]))[2], 22)

    def test_a_block_that_reaches_its_close_late_still_gets_the_s22_look_as_of_that_close(self):
        """Whether a look falls due at a close is decided only on its final record (section 2: late data delays a
        look, never its as-of close; release 1019i's re-review): a close judged before its block arrived is not
        marked looked."""
        for i, day in enumerate(self.days[:21]):
            self.stay_day(day, [0.002, -0.001], base=100 * i)
        state = lambda: json.loads(self.st.meta(BA.STAY_KEY.format(program=self.prog.id, version=3, n=1)))
        with final(self.days[20]):                              # (the 22nd close's block is not in yet)
            self.assertEqual(BA.review(self.st, now=et(self.days[21], 20, 40)), [])
        self.assertEqual(state()["looked"], self.days[20].isoformat(), "the 22nd close is not marked looked")
        self.stay_day(self.days[21], [0.002, -0.001], base=2100)     # (its block reaches the record a night late)
        self.stay_day(self.days[22], [0.002, -0.001], base=2200)
        with final(self.days[22]):
            BA.review(self.st, now=et(self.days[22], 20, 40))
        [look] = self.stay_looks()
        self.assertEqual(S.parse_iso(look["at"]), et(self.days[21], 16, 0), "the S 22 look is as of the 22nd close")
        self.assertEqual(SC.key_of6(int(look["k"]))[2], 22)

    def test_an_older_probe_lot_on_the_ladder_holds_the_look_and_past_it_sized_is_refused(self):
        """Sized's conditions are judged over every real-money event of the stay due by the look's close (section 3;
        release 1019i's re-review, the money lens): a lot bought before the look's close and still unsold waits as
        the close's own lots do; past the ladder the look runs and Sized waits for the next look."""
        for i, day in enumerate(self.days[:22]):
            self.stay_day(day, [0.03, 0.028], base=100 * i)
        [event] = self.lane.settled(self.prog, self.days[18], [("08888", 0.0, 0.0)])
        BA.record_fill(self.st, program=self.prog.id, version=3, event=event, side="buy", qty=10, price=10.0, fee=0.0,
                       filled_at=S.iso(et(self.days[18], 9, 30)), band="probe", target_usd=100.0, sized_usd=100.0)
        for day in self.days[21:18 + BA.STUCK_AFTER]:
            self.review(day)
            self.assertEqual(self.stay_looks(), [], "the older lot is still on the ladder: the look waits")
            self.assertEqual(BA.bands(self.st)[self.prog.key], "probe")
        self.review(self.days[18 + BA.STUCK_AFTER])
        [look] = self.stay_looks()
        self.assertEqual(S.parse_iso(look["at"]), et(self.days[21], 16, 0))
        sized = SC.look_detail(self.st, *self.prog.key, look["k"])["v6"]["sized"]
        self.assertEqual((sized["n"], sized["ok"], sized["unsettled"]), (44, False, [event]))
        self.assertEqual(BA.bands(self.st)[self.prog.key], "probe", "a pass never moves to Sized over an unsold lot")

    def test_one_lot_whose_sale_never_fills_never_holds_a_later_closes_reads_and_money_stop(self):
        """A real-money event still unsettled holds only its own close; the stop counts the stay's settled events
        (release 1019i's review, the money lens)."""
        [event] = self.lane.settled(self.prog, self.days[0], [("09999", 0.0, 0.0)])
        BA.record_fill(self.st, program=self.prog.id, version=3, event=event, side="buy", qty=10, price=10.0, fee=0.0,
                       filled_at=S.iso(et(self.days[0], 9, 30)), band="probe", target_usd=100.0, sized_usd=100.0)
        self.stay_day(self.days[0], [-0.4] * 5, base=100)
        self.assertEqual(self.review(self.days[0]), [], "its own close waits for its sale (the ladder may still sell it)")
        for i, day in enumerate(self.days[1:6]):
            self.stay_day(day, [-0.4] * 5, base=200 + 100 * i)
        [moved] = self.review(self.days[1])
        self.assertEqual(moved["band"], "learning")
        self.assertIn("the money stop: the stay's 10 real-money Probe+ events lost $400.00 net, more than 10% of their "
                      "$1000.00 buy cost", moved["why"], "the next close is judged on every settled event so far")

    def test_a_close_still_to_come_is_never_judged(self):
        self.stay_day(self.days[0], [-0.01] * 5, base=0)
        state = lambda: json.loads(self.st.meta(BA.STAY_KEY.format(program=self.prog.id, version=3, n=1)))
        with final(self.days[0]):
            self.assertEqual(BA.review(self.st, now=et(self.days[1], 0, 30)), [])     # (after midnight: day 1 is open)
        self.assertEqual(state()["through"], self.days[0].isoformat())
        with final(self.days[0]):
            BA.review(self.st, now=et(self.days[1], 12, 0))
        self.assertEqual(state()["through"], self.days[0].isoformat(), "its close has not passed")

    def test_a_close_whose_own_lot_is_unsettled_past_the_ladder_is_judged_without_it(self):
        self.assertEqual(BA.STUCK_AFTER, EB.LADDER_CLOSES + 1, "the ladder's closing crosses, then its first day sale")
        for i, day in enumerate(self.days[:22]):
            self.stay_day(day, [0.002, -0.001], base=100 * i)
        [event] = self.lane.settled(self.prog, self.days[21], [("08888", 0.0, 0.0)])
        BA.record_fill(self.st, program=self.prog.id, version=3, event=event, side="buy", qty=10, price=10.0, fee=0.0,
                       filled_at=S.iso(et(self.days[21], 9, 30)), band="probe", target_usd=100.0, sized_usd=100.0)
        state = lambda: json.loads(self.st.meta(BA.STAY_KEY.format(program=self.prog.id, version=3, n=1)))
        for wait in range(BA.STUCK_AFTER):
            self.review(self.days[21 + wait])
            self.assertEqual(self.stay_looks(), [], f"{wait} sessions after: the look at its close waits for its lot")
            self.assertEqual(state()["unsettled"], [])
        self.review(self.days[21 + BA.STUCK_AFTER])
        [look] = self.stay_looks()
        self.assertEqual(S.parse_iso(look["at"]), et(self.days[21], 16, 0))
        self.assertEqual(state()["unsettled"], [event], "past the ladder: judged without it, and named")

    def test_the_stays_lower_tail_at_a_stay_look_demotes_and_a_fresh_run_follows(self):
        early = self.lane.days(dt.date(2026, 10, 1), 22)
        base = seat("EVL-INS-BUY-O1")
        BA.set_band(self.st, base.id, 3, "learning", since=S.iso(et(early[0], 1)), why="reset", now=et(early[0], 1))
        for i, day in enumerate(early):      # run 1 passes at its 22nd block: the stay begins with the move
            self.lane.settled(base, day, [(f"7{i:04d}", 0.03, 0.031), (f"6{i:04d}", 0.025, 0.026)])
        with final(early[-1]):
            SC.run(self.st, early[-1], programs=[base.key], now=et(early[-1], 20, 30))
        self.assertEqual(BA.bands(self.st)[base.key], "probe")
        stays = SC.stays6(self.st, *base.key)
        self.assertEqual(stays[-1]["n"], 2, "the second move to probe is stay 2")
        for i, day in enumerate(self.days[:22]):
            self.stay_day(day, [-0.03, -0.035], real=False, base=2000 + 10 * i)
        [moved] = self.review(self.days[21])
        self.assertEqual(moved["band"], "learning")
        self.assertIn("demotion 2", moved["why"])
        runs = SC.runs6(self.st, *base.key)
        self.assertEqual([r["n"] for r in runs], [1, 2], "a fresh run starts at the first decision after the demotion")
        self.assertIsNotNone(runs[1]["after"])

    def sized(self, gap: float) -> dict:
        for i, day in enumerate(self.days[:22]):
            self.stay_day(day, [0.03, 0.028], base=100 * i, gap_bp=gap)
        self.review(self.days[21])
        look = max(SC.look_rows(self.st, *self.prog.key), key=lambda r: r["k"])
        return SC.look_detail(self.st, *self.prog.key, look["k"])["v6"]["sized"]

    def test_sized_needs_a_stay_pass_30_real_events_at_size_with_pnl_and_fills_within_15bp(self):
        sized = self.sized(0.0)
        self.assertEqual(BA.bands(self.st)[self.prog.key], "sized")
        self.assertEqual((sized["n"], sized["fills_ok"], sized["ok"]), (44, True, True))

    def test_a_stay_pass_with_fills_beyond_15bp_stays_at_probe(self):
        sized = self.sized(20.0)
        self.assertEqual(BA.bands(self.st)[self.prog.key], "probe")
        self.assertEqual((sized["n"], sized["fills_ok"], sized["ok"]), (44, False, False))

    def test_the_reads_seed_string_and_the_review_never_runs_preregevl3s_stop_for_these_versions(self):
        events = [{"entry_day": f"2026-11-{2 + i // 10:02d}", "r": 0.001 * ((i % 3) - 1)} for i in range(200)]
        p = BA.read_p6(events, f"{self.prog.id}|v3|evl6|stay1|read200", 999)
        self.assertGreater(p, 0)
        self.assertEqual(len(BA.read_values6(events)), 20)
        self.stay_day(self.days[0], [-0.0001] * 60, base=0)     # $150 net over 50: PREREG-EVL-3's stop is not theirs
        with mock.patch.object(BA, "DEMOTE_NET_USD", -0.000001):
            self.assertEqual(self.review(self.days[0]), [])


# =============================================================================================== 6 the money
class TheMoney(unittest.TestCase):
    def test_the_row_and_its_bound_read_only_for_preregevl6s_versions(self):
        event = K.CONSTITUTION["equity_money"]["event"]
        self.assertEqual((event["max_open_v6"], event["max_open"]["probe"]), ({"probe": 14}, 6))
        self.assertEqual((K.EQUITY_MONEY_BOUNDS["event.max_open_v6.probe"], K.EQUITY_MONEY_BOUNDS["event.max_open.probe"]),
                         (("0", "14"), ("0", "6")))
        s = EB.settings()
        self.assertEqual((s.max_open("probe", seat("EVL-ERN-READ-O1")), s.max_open("probe"),
                          s.max_open("probe", P.BY_KEY[("EVL-ERN-READ-O1", 2)])), (14, 6, 6))
        self.assertEqual([s.max_open(b, seat("EVL-NEWS-READ-O1")) for b in ("learning", "sized")], [8, 8])
        for value in (15, -1, "x"):
            bad = json.loads(json.dumps(K.CONSTITUTION))
            bad["equity_money"]["event"]["max_open_v6"]["probe"] = value
            self.assertTrue(K.equity_money_problems(bad), value)
            self.assertIs(EB.settings(bad), EB.FALLBACK, value)
        gone = json.loads(json.dumps(K.CONSTITUTION))
        del gone["equity_money"]["event"]["max_open_v6"]
        self.assertIn("equity_money.event.max_open_v6.probe is missing", " ".join(K.equity_money_problems(gone)))

    def test_the_digests_moved_once_with_the_row_and_nothing_else(self):
        pair = X.in_force()
        self.assertEqual((K.money_digest()[:8], K.digest()[:8]), ("d52a5af5", "9c8b2221"))
        self.assertEqual(K.digest(), K.PINNED_DIGEST)
        self.assertEqual((K.money_digest(), K.digest()), X.DIGESTS[pair])
        before = X.before_1019i()
        self.assertEqual((K.money_digest(before)[:8], K.digest(before)[:8]), ("8e63ce64", "c3026eba"), "release 1019h's")

        def flat(c, prefix=""):
            out = {}
            for k, v in c.items():
                out.update(flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}": v})
            return out
        moved = {k for k, v in flat(K.CONSTITUTION).items() if flat(before).get(k, "absent") != v}
        self.assertEqual(moved, {"equity_money.event.max_open_v6.probe"})
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((K.money_digest(X.before_1019i(at)), K.digest(X.before_1019i(at))), X.DIGESTS_1019H[candidate])
        off = json.loads(json.dumps(K.CONSTITUTION))
        off["equity_money"]["event"]["enabled"] = False
        self.assertEqual((K.money_digest(off)[:8], K.digest(off)[:8]), X.ROLLBACK_1019I)
        none = json.loads(json.dumps(K.CONSTITUTION))
        none["equity_money"]["event"]["max_open_v6"]["probe"] = 0
        self.assertEqual(K.equity_money_problems(none), [], "0 stops every PREREG-EVL-6 Probe buy: inside the bound")
        self.assertEqual((K.money_digest(none)[:8], K.digest(none)[:8]), X.V6_SLOTS_OFF)

    def test_no_whole_share_count_reaching_the_bar_inside_the_envelope_is_under_bar(self):
        E = D("1898")
        target = D("0.035") * E
        for limit, want in (("40", False), ("47.45", False), ("50", True), ("53.14", True), ("90", False), ("96", True)):
            self.assertEqual(EB.under_bar("probe", target, D(limit), E), want, limit)
        self.assertFalse(EB.under_bar("probe", target, D("50"), E, bar="0"), "S2's switch off: no at-size buy")
        self.assertFalse(EB.under_bar("learning", D("0.02") * E, D("50"), E))
        self.assertTrue(EB.under_bar("sized", D("0.10") * E, D("150"), E), "one share under $151.84, two above 10% of E")
        self.assertFalse(EB.under_bar("sized", D("0.10") * E, D("160"), E))


class TheMoneyInTheBook(unittest.TestCase):
    """The House's book (league/equity/live.py) on PREREG-EVL-6's seats: the under-bar skip before a slot, 14 Probe
    slots, the seat's room and issuers with the superseded version's open lot, the superseded seat's instance retired."""

    def setUp(self):
        from league.tests import test_events_book as TB

        self.TB = TB
        self.case = TB.EventTest("run")
        self.case.setUp()
        self.addCleanup(self.case.tmp.cleanup)
        self.addCleanup(P.load_births, None)

    def summary(self, h, at: str = "open") -> dict:
        row = h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at=?", (self.TB.DAY.isoformat(), at))
        return json.loads(row[0]["summary"])

    def probe_pick(self, h, *, version: int, prev_close: float) -> None:
        TB = self.TB
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME", prev_close=prev_close)
        h.lane.band("EVL-ERN-READ-O1", "probe", version=version)
        h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", version)], "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.case.ready(h)
        h.symbol("ACME", last=prev_close, sd=0.02)

    def test_a_probe_pick_no_count_brings_to_dones_bar_is_skipped_before_a_slot_where_s2_alone_buys_it(self):
        h = self.case.harness()
        self.probe_pick(h, version=3, prev_close=41.6)       # limit $52.00: one share $52 < 0.8 x $70, two $104 > $100
        h.tick(9, 15)
        mine = self.summary(h)["programs"]["EVL-ERN-READ-O1"]
        self.assertEqual((mine["picks"], mine.get("planned"), mine.get("skipped"), mine["room"]),
                         (1, 0, {"under_bar": 1}, 14), "skipped as under_bar; 14 Probe slots")
        self.assertEqual(h.event_intents("buy"), [])
        with F6.before_evl6():
            h2 = TheMoneyInTheBook.fresh(self)
            self.probe_pick(h2, version=2, prev_close=41.6)
            h2.tick(9, 15)
            mine = self.summary(h2)["programs"]["EVL-ERN-READ-O1"]
            self.assertEqual((mine["planned"], mine["room"]), (1, 6), "release 1019h's S2: bought under the bar, 6 slots")

    def test_the_reach_bar_row_below_0_8_switches_a_v6_probe_buy_off_and_never_sizes_it_under_the_bar(self):
        """Section 6, clause 2 is literal (A123, A134): a PREREG-EVL-6 version's Probe and Sized buys are sized and
        gated on Done's own 0.8 (`V6_SIZE_BAR` = done.PROBE_SIZE_SHARE, the row in force), and the `reach_bar` row can
        only switch them OFF: at the row's "0" (S2's switch) or anything under 0.8 nothing is bought (release 1019h's
        S2 would floor the buy under the bar: the reading that trades more)."""
        from league.events import done as DN

        self.assertEqual(L.V6_SIZE_BAR, D(str(DN.PROBE_SIZE_SHARE)))
        self.assertEqual(EB.settings().reach_bar("probe"), L.V6_SIZE_BAR, "the row in force is the bar")
        for row in ("0", "0.5"):
            off = dataclasses.replace(EB.settings(), reach_bars={"probe": D(row), "sized": D(row)})
            with mock.patch.object(EB, "settings", lambda *a, **k: off):
                h = self.fresh()
                self.probe_pick(h, version=3, prev_close=48.0)      # limit $60: one share reaches 0.8 x $70 at 0.8
                h.tick(9, 15)
                mine = self.summary(h)["programs"]["EVL-ERN-READ-O1"]
                self.assertEqual((mine["picks"], mine.get("planned"), mine.get("skipped")), (1, 0, {"reach_bar_off": 1}),
                                 f"row {row}: switched off, not floored")
                self.assertEqual(h.event_intents("buy"), [], row)

    def fresh(self):
        case = self.TB.EventTest("run")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        return case.harness()

    def sent(self, h) -> dict[str, str]:
        return {b["symbol"]: b["qty"] for b in h.bodies() if b["side"] == "buy"}

    def test_a_probe_buy_takes_the_fewest_whole_shares_that_reach_dones_bar(self):
        """Section 6, clause 2's words (release 1019i's review, the money lens): at E $1,898 the Probe target is
        $66.43 and Done's bar $53.144; at a $5.00 limit the floor of the target is 13 shares ($65.00), the fewest
        that reach the bar 11 ($55.00)."""
        h = self.case.harness(cash="1898", E="1898")
        self.probe_pick(h, version=3, prev_close=4.0)            # limit $5.00
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {"ACME": "11"})
        [row] = h.event_intents("buy")
        self.assertEqual((D(row["target_usd"]), D(row["sized_usd"]), row["binding"]), (D("66.430"), D("55"), None),
                         "the target stays the band's; the dollars sent reach the bar")
        self.assertTrue(EB.at_size(D(row["target_usd"]), D(row["sized_usd"])))
        self.assertEqual(EB.at_size_count("probe", D("66.43"), D("5"), D("1898")), 11)
        self.assertEqual(EB.at_size_count("sized", D("189.80"), D("5"), D("1898")), 31, "Sized: 0.8 x 10% of E")
        self.assertIsNone(EB.at_size_count("probe", D("66.43"), D("50"), D("1898")), "under the bar: no count fits")
        self.assertIsNone(EB.at_size_count("learning", D("37.96"), D("5"), D("1898")))
        with F6.before_evl6():
            h2 = self.fresh()
            h2.E = D("1898")
            self.probe_pick(h2, version=2, prev_close=4.0)
            h2.tick(9, 15)
            h2.tick(9, 16)
            self.assertEqual(self.sent(h2), {"ACME": "13"}, "release 1019h's S2 for its versions: the floor of the target")

    def test_a_cap_that_cuts_the_at_size_ask_under_the_bar_skips_the_buy(self):
        h = self.case.harness(cash="1898", E="1898")
        h.options.reserved_usd = 1798.0          # available: $1,898 - $1,798 - the $50 reserve = $50 < 11 x $5.00
        self.probe_pick(h, version=3, prev_close=4.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(self.sent(h), {}, "10 shares ($50) would be under Done's bar: skipped, the shadow keeps it")
        [row] = h.event_intents("buy")
        self.assertEqual((row["status"], D(row["sized_usd"]), row["binding"]), ("refused", D("0"), "cash"))
        self.assertIn("cut under Done's size bar", row["why"])

    def pick_on(self, h, day: dt.date, accession: str, cik: str, symbol: str, prev_close: float = 16.0) -> None:
        """A Probe pick of EVL-ERN-READ-O1 v3 on `day`: its 8-K after the previous session's close, its verdict, its
        universe row and the lane's intent."""
        TB = self.TB
        prior = TB.ES.previous_session(day)
        h.lane.filing(accession, cik, accepted=TB.iso(prior, 16, 30), received=TB.iso(prior, 16, 31))
        h.lane.verdict(accession, 3, answered=TB.iso(prior, 16, 35))
        h.lane.universe(day, symbol, cik, prev_close)
        h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", 3)], f"8k:{accession}", symbol, cik, day, day)
        self.case.ready(h, day)
        h.symbol(symbol, last=prev_close, sd=0.02)

    def test_a_probe_lot_unsold_past_the_ladder_holds_the_versions_new_probe_buys_with_an_alarm(self):
        """Section 3 with a real-money event that never settles (release 1019i's review, the money lens): from the
        session `LADDER_CLOSES` + 1 after its planned exit the version's Probe and Sized buys are held (the reading that
        trades less) and an error alarm is said once a session; the lane judges its stay without the lot."""
        TB, ES = self.TB, self.TB.ES
        h = self.case.harness()
        self.probe_pick(h, version=3, prev_close=16.0)           # limit $20.00
        h.venue.prints[("ACME", TB.DAY.isoformat(), "open")] = D("20.00")     # bought at the open, no close print
        h.venue.fill = "none"                                                 # and no day trade: its sale never fills
        h.day(TB.DAY)
        [lot] = h.lots()
        self.assertEqual((lot.version, lot.info["evl"]["band"]), (3, "probe"))
        self.assertIn(lot.status, ("open", "closing"))
        day = TB.DAY
        for _ in range(EB.LADDER_CLOSES):
            day = ES.next_session(day)
        self.pick_on(h, day, "b-1", "0000000101", "BETA")
        h.tick(9, 15, day=day)
        mine = self.summary_of(h, day)["programs"]["EVL-ERN-READ-O1"]
        self.assertEqual((mine["planned"], mine.get("held")), (1, None), "inside the ladder: the buys go on")
        day = ES.next_session(day)
        self.pick_on(h, day, "b-2", "0000000102", "GAMA")
        h.tick(9, 15, day=day)
        mine = self.summary_of(h, day)["programs"]["EVL-ERN-READ-O1"]
        self.assertEqual((mine["picks"], mine["room"], mine["held"]), (None, 0, "unsettled"))
        self.assertNotIn("GAMA", {r["symbol"] for r in h.event_intents("buy")})
        said = [text for level, text in h.alerts if level == "error" and "holds EVL-ERN-READ-O1 v3's Probe" in text]
        self.assertEqual(len(said), 1)
        self.assertIn(f"{lot.lid} (ACME)", said[0])
        h.tick(9, 16, day=day)
        self.assertEqual(len([t for _, t in h.alerts if "holds EVL-ERN-READ-O1 v3's Probe" in t]), 1, "once a session")

    def summary_of(self, h, day: dt.date, at: str = "open") -> dict:
        row = h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at=?", (day.isoformat(), at))
        return json.loads(row[0]["summary"])

    def test_the_seat_counts_the_superseded_versions_open_lot_and_its_instance_is_retired_at_the_sync(self):
        TB = self.TB
        with F6.before_evl6():
            h = self.case.harness()
            TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
            h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", 2)], "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
            self.case.ready(h)
            h.symbol("ACME", last=17.0, sd=0.02)
            h.venue.prints[("ACME", TB.DAY.isoformat(), "open")] = D("17.00")
            for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
                h.tick(hh, mm)
            [lot] = h.lots()
            self.assertEqual((lot.version, lot.status), (2, "open"))
        h.book.state.put("eq_event_synced", "")              # (the release: the next decision syncs the bands)
        h.tick(15, 46)
        old = h.book._instance(L.instance_key("EVL-ERN-READ-O1", 2))
        new = h.book._instance(L.instance_key("EVL-ERN-READ-O1", 3))
        self.assertIsNotNone(old.retired_at, "the superseded seat's instance is retired: it decides no more")
        self.assertIn("PREREG-EVL-6", old.why)
        self.assertTrue(new is not None and new.live)
        adapter = h.book._event_adapter()
        self.assertEqual(h.book._event_seat_count(new, adapter), 1, "the superseded version's open lot is in its seat")
        self.assertIn(TB.CIK, h.book._event_held(new, TB.DAY, adapter))
        self.assertTrue(any(s["lid"] == lot.lid for s in h.event_intents("sell")), "its open lot exits by its rules")


L = __import__("league.equity.live", fromlist=["instance_key"])


# =============================================================================================== 5 the count
class TheCount(LaneCase):
    def test_013_a_version_or_run_of_the_restated_39_three_ways_and_per_version_beside(self):
        efp = SC.expected_false_passes(self.st)
        self.assertEqual({k: efp[k] for k in ("versions", "runs", "charge", "expected", "budget", "left", "base", "stress",
                                              "per_version")},
                         {"versions": 15, "runs": 0, "charge": 0.13, "expected": 1.95, "budget": 3.9, "left": 1.95,
                          "base": 0.45, "stress": 2.55, "per_version": 0.24})
        sup = P.BY_KEY[("EVL-ERN-READ-O1", 2)]
        self.lane.intent(sup, "8k:z", dt.date(2026, 11, 2), "1")
        self.assertEqual(SC.expected_false_passes(self.st)["expected"], 1.95, "a superseded version is charged 0")
        later = dataclasses.replace(seat("EVL-ERN-READ-O1"), version=4)
        self.lane.intent(later, "8k:y", dt.date(2026, 11, 2), "1")
        self.assertEqual(SC.expected_false_passes(self.st)["expected"], 2.08, "a later version the store holds: 0.13")

    def test_r3s_validator_reads_the_restated_charge_and_the_budget_after_every_waiting_run(self):
        self.assertEqual((BI.CHARGE_HUNDREDTHS, BI.BUDGET_HUNDREDTHS), (13, 390))
        with mock.patch.object(SC, "waiting_runs", lambda store, now=None: [{}] * 3):
            got = BI.budget(self.st)
        self.assertEqual((got["used"], got["waiting_runs"], got["left_for_births"], got["seatable_left_tonight"]),
                         (1.95, 0.39, 1.56, 3))
        with mock.patch.object(SC, "waiting_runs", lambda store, now=None: [{}] * 15):
            self.assertEqual(BI.budget(self.st)["seatable_left_tonight"], 0, "the waiting runs hold the whole room")


# =============================================================================================== the proof
class TheProof(unittest.TestCase):
    """ON AN INVENTED WEEK (league/tests/evl5_world.py: every family of PREREG-EVL-1, -2, -4 and -5 and two births
    registered before REGISTERED_AT_6, decided as the House decides), every real-money pick is the same with this change
    and without it (release 1019h's program table), while no version is promoted: the new versions copy the superseded
    rule word for word; and no superseded version moves a band after REGISTERED_AT_6."""

    def week(self, *, evl6: bool, release: dt.datetime | None) -> tuple[dict, object]:
        from league.tests import evl5_world as W

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(P.load_births, None)
        world = W.World(Path(tmp.name) / "lane")
        self.addCleanup(world.close)
        if release is not None:
            P.mark_release(world.st, release)
        world.births()
        W.evl4_rows(world)
        W.evl5_rows(world)
        W.decide_week(world)
        picks = W.picks(world, lambda p: True)
        return {k.split("@v")[0] + "@" + k.rsplit("@", 1)[1]: v for k, v in picks.items()}, world

    def test_every_real_money_pick_is_the_same_with_and_without_the_change_and_no_superseded_band_moves(self):
        from league.tests import evl5_world as W

        for release in (et(dt.date(2026, 10, 23), 20, 10), et(W.D_DAY, 20, 10)):
            with self.subTest(release=release):
                with_change, world = self.week(evl6=True, release=release)
                with F6.before_evl6():
                    without, _ = self.week(evl6=False, release=None)
                self.assertEqual(set(with_change), set(without))
                self.assertEqual(with_change, without)
                self.assertTrue(any(with_change.values()), "the week has real-money picks")
                self.assertEqual({BA.bands(world.st)[p.key] for p in P.SEATING}, {"learning"}, "no version promoted")
                for p in P.SEATING:
                    sup = P.superseded_of(p)
                    if sup is None:
                        continue
                    look = {"program": sup.id, "version": sup.version, "k": 9, "held": 1, "passed": 1,
                            "at": S.iso(et(W.N_DAY, 16)), "retirement": {"retire": False}}
                    self.assertIsNone(BA.on_look(world.st, look, now=et(W.N_DAY, 20, 30)), sup.key)
                self.assertEqual(world.st.db.execute("SELECT COUNT(*) FROM band_history").fetchone()[0], 0)


class TheAlarmsWatchTheNewVersions(unittest.TestCase):
    def test_the_final_record_alarm_still_watches_a_version_after_its_first_preregevl6_look(self):
        from league.ops import evl_health as EV

        with tempfile.TemporaryDirectory() as tmp:
            self.addCleanup(P.load_births, None)
            lane = Lane6(Path(tmp) / "events")
            prog = seat("EVL-INS-BUY-O1")
            day = dt.date(2026, 11, 30)
            look = {"program": prog.id, "version": 3, "k": SC.look_key6("run", 1, 22), "at": S.iso(et(day, 16)),
                    "sessions": 22, "n": 44, "issuers": 44, "blocks": 22, "mean_a": 0.0, "mean_r": 0.0,
                    "mean_a_tradable": 0.0, "p": 0.5, "alpha": 0.02, "fp_check": None, "held": 1, "passed": 0,
                    "why": "fail", "v6": {"look": 1, "kind": "run", "n": 1, "S": 22}}
            SC.write_look(lane.st, look, now=et(day, 20, 30))
            self.assertIsNone(SC.written_v2(lane.st, prog.id, 3)["next"], "PREREG-EVL-3's counter reads it as all used")
            lane.close()
            lags = {(r["program"], r["version"]) for r in EV.final_lags(tmp, et(dt.date(2026, 12, 2), 12).timestamp())}
            self.assertIn(prog.key, lags, "the record of a PREREG-EVL-6 version is watched while it has runs")


# =============================================================================================== the report and the site
class TheReportAndTheSite(LaneCase):
    def test_the_report_names_the_new_versions_their_runs_and_a_superseded_shadow(self):
        v3, v2 = seat("EVL-INS-BUY-O1"), P.BY_KEY[("EVL-INS-BUY-O1", 2)]
        day = dt.date(2026, 11, 2)
        self.lane.settled(v3, day, [("1", 0.01, 0.011)])
        self.lane.settled(v2, day, [("1", 0.01, 0.011)])
        rep = RP.build(self.st, day, now=et(day, 21, 5))
        mine = {(p["program"], p["version"]): p for p in rep["programs"]}
        self.assertEqual(mine[v3.key]["v6"], {"runs": 1, "fresh_runs": 0, "stays": 0, "per_run": 0.13, "per_version": 0.13})
        self.assertEqual((mine[v3.key]["next_look"]["kind"], mine[v3.key]["next_look"]["blocks_needed"]), ("run", 22))
        self.assertEqual(mine[v2.key]["superseded_by"], 3)
        text = RP.render(rep)
        self.assertIn("EVL-INS-BUY-O1 v3", text)
        self.assertIn("run 1 look 1 at 22 blocks (now 1, events 1, issuers 1)", text)
        self.assertIn("runs 1 (each 0.13 worst plausible), per version 0.13", text)
        self.assertIn("superseded by v3 (PREREG-EVL-6", text)
        self.assertIn("Expected false passes: 1.95 (0.13 x 15 versions and 0 fresh runs; base 0.45, stresses' worst 2.55)",
                      text)

    def test_lane_v1_rows_are_the_seats_their_real_money_both_versions_and_no_ring_in_the_wrong_unit(self):
        from league import site_lane as SL

        v3, v2 = seat("EVL-INS-BUY-O1"), P.BY_KEY[("EVL-INS-BUY-O1", 2)]
        day = dt.date(2026, 11, 2)
        [e2] = self.lane.settled(v2, day, [("1", 0.01, 0.011)])
        self.lane.real(v2, day, e2, r=0.011, band="learning")
        [e3] = self.lane.settled(v3, dt.date(2026, 11, 3), [("2", 0.01, 0.011)])
        self.lane.real(v3, dt.date(2026, 11, 3), e3, r=0.011, band="learning")
        got = SL.read_programs(self.st, dt.date(2026, 11, 4))
        row = next(r for r in got["programs"] if r["id"] == SL.slug_of(v3.id))
        self.assertEqual(set(row), {"id", "name", "band", "real", "shadow", "look"}, "lane_v1's contract unchanged")
        self.assertEqual((row["real"], row["shadow"], row["look"]), (2, 1, None))
        self.assertEqual(len([r for r in got["programs"] if r["id"] == SL.slug_of(v3.id)]), 1, "one row a seat")
        self.assertEqual(got["funnel"]["learning"], 15)


# =============================================================================================== release 1019h's minors
class TheBirthsMinors(unittest.TestCase):
    """Release 1019h's re-review (minors, fixed here): the call's row ahead of the call and an UPDATE; any exception
    after the send a LOST call at worst; a stored lost (or asked) call is unanswered; the room is the limit and two gaps
    inside a 300 s bound; the reconciliation after the call."""

    def setUp(self):
        from league.tests import test_events_births as TB

        self.TB = TB
        self.v = TB.Validation("run")
        self.v.setUp()
        self.addCleanup(self.v.doCleanups)
        self.st = self.v.s.st
        self.now = lambda: dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC)

    def test_the_row_is_written_ahead_of_the_call_at_its_worst_case_and_an_error_after_the_send_is_lost(self):
        st = self.st
        seen = []

        class Boom(self.TB.FakeArchitect):
            def post_stream(inner, path, body, headers=None, *, limit, gap=None):
                seen.append(dict(st.db.execute("SELECT status, usd, answered_at FROM birth_calls").fetchone()))
                raise RuntimeError("a reply the code could not read, after the send")
        sheet = BI.Facts(st, self.v.AS_OF).facts()
        got = BI.propose(st, Boom("{}"), sheet, night=self.v.AS_OF, now=self.now)
        worst = BI.worst_usd(BI.render(sheet, BI.budget(st, self.v.AS_OF)))
        self.assertEqual(seen[0]["status"], BI.ASKED)
        self.assertAlmostEqual(seen[0]["usd"], worst, places=9)
        self.assertIsNotNone(seen[0]["answered_at"], "counted on the asking day by every reader of the day's spend")
        self.assertEqual(got["status"], BI.LOST)
        row = dict(st.db.execute("SELECT status, usd FROM birth_calls").fetchone())
        self.assertEqual(row["status"], BI.LOST)
        self.assertAlmostEqual(row["usd"], worst, places=9)
        again = BI.propose(st, self.TB.FakeArchitect("{}"), sheet, night=self.v.AS_OF, now=self.now)
        self.assertEqual(again["status"], "stored:lost", "never asked again that night")

    def test_a_restart_mid_call_leaves_the_asked_row_counted_and_never_asked_again(self):
        st = self.st
        sheet = BI.Facts(st, self.v.AS_OF).facts()
        with st.tx() as db:
            db.execute("INSERT INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, status, "
                       "user_sha, facts_sha, answer, usd) VALUES(?, ?, ?, 'r', 'x', 'x', ?, 'u', 'f', NULL, 0.15)",
                       (self.v.AS_OF.isoformat(), BI.prompt_sha(), BI.MODEL, BI.ASKED))
        gw = self.TB.FakeArchitect("{}")
        got = BI.propose(st, gw, sheet, night=self.v.AS_OF, now=self.now)
        self.assertEqual((got["status"], gw.calls, got["usd"]), ("stored:asked", [], 0.15))
        self.assertEqual(BI.spent(st, self.v.AS_OF), 0.15, "never $0")
        out = BI.night(st, gw, today=self.v.AS_OF, now=self.now)
        self.assertEqual(out["_status"], "unanswered", "a stored call with no answer is unanswered")

    def test_a_stored_lost_call_is_unanswered_and_the_reconciliation_runs_after_the_call(self):
        st = self.st
        order = []

        class Order(self.TB.FakeArchitect):
            def post_stream(inner, path, body, headers=None, *, limit, gap=None):
                order.append("call")
                return super().post_stream(path, body, headers, limit=limit, gap=gap)

            def post_json(inner, path, body, headers=None):
                if path == BI.DOCS_ROUTE:
                    order.append("docs")
                return super().post_json(path, body, headers)
        st.db.execute("INSERT INTO birth_candidates(night, seq, sha, id, spec, why, by, status, reasons, figures, line, "
                      "at) VALUES('2026-11-05', 0, 's', 'EVL-B-X', '{}', 'w', 'b', 'unknown', '[]', '{}', '{}', 'x')")
        gw = Order(json.dumps({"specs": []}), docs=lambda body: (503, {"refused": "no_answer"}))
        BI.night(st, gw, today=self.v.AS_OF, now=self.now)
        self.assertEqual(order[:2], ["call", "docs"], "the call first, the earlier night's lines after it")
        st.db.execute("UPDATE birth_calls SET status=?", (BI.LOST,))
        out = BI.night(st, gw, today=self.v.AS_OF, now=self.now)
        self.assertEqual((out["call"]["status"], out["_status"]), ("stored:lost", "unanswered"))


# =============================================================================================== the docs and the wall
class TheDocs(unittest.TestCase):
    def test_the_frozen_file_and_its_calibration_are_the_tags_byte_for_byte(self):
        text = (REPO / "docs" / "prereg" / "PREREG-EVL-6.md").read_bytes()
        self.assertEqual(hashlib.sha256(text).hexdigest(),
                         "0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057")
        folder = REPO / "docs" / "prereg" / "evl-6"
        sums = [line.split("  ", 1) for line in (folder / "SHA256SUMS").read_text().splitlines() if line.strip()]
        self.assertEqual(len(sums), 126)
        for sha, name in sums:
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), sha, name)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted([name for _, name in sums] + ["SHA256SUMS"]))
        for pid in NINE + FOUR + FIVE:
            self.assertIn(pid, text.decode())

    def test_the_wall_holds_the_frozen_files_and_the_judges(self):
        for path in ("docs/prereg/PREREG-EVL-6.md", "docs/prereg/evl-6/calib_v2.py", "docs/prereg/evl-6/SHA256SUMS",
                     "league/events/programs.py", "league/events/screen.py", "league/events/bands.py",
                     "league/events/book.py", "league/events/run.py", "league/events/house.py",
                     "league/events/births.py", "league/constitution.py"):
            self.assertTrue(ci.guard([path], None), path)
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([path], role), (path, role))


# (release 1019j's merge: PREREG-EVL-6's rules on its own table, written before PREREG-EVL-7's learners registered;
# the lane's count with them is league/tests/test_events_evl7*.py's)
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
