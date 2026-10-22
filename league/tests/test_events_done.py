"""THE DONE READER OF THE GOAL V2 (league/events/done.py; docs/goals/DONE-RULE-EVL-2.md), on invented data only.

- what counts: no Probe event counts nothing; learning events are beside, never counted; Probe+ buys before the
  program's promotion (its EARLIEST move to probe) are beside, never counted, and one inside a checkpoint's span fails
  its item 4.3; a demotion and a return to Probe drop nothing (A84);
- the checkpoints: the 100th counted event writes checkpoint 100, over exactly the first 100, and a written checkpoint
  is never rewritten (the history append-only, through done.json and done-history.jsonl; an unreadable record or a lost
  one a receipt names writes nothing);
- each item's pass and fail: events, programs, P&L, the bound, profit against compute, the fills, no captain step
  (never a pass from the House's records alone: Done waits on the captain's attestation, A84);
- the bootstrap is deterministic (10,000 resamples, the fixed seed string, issuers as blocks); the pivot at 400; the
  $800 stop; the rule file pinned by its sha256; the reader opens nothing for writing; the House's nightly screen runs
  it after the band review and keeps a `done` receipt.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from league.events import bands as BA
from league.events import done as DN
from league.events import programs as P
from league.events import screen as SC
from league.events import store as S
from league.ops import guard

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]
SEATING = [(p.id, p.version) for p in P.SEATING]
PROMOTED = "2026-11-01T01:00:00Z"
FIRST_DAY = dt.date(2026, 11, 2)
NOW = dt.datetime(2026, 12, 31, 12, tzinfo=UTC)
MEASURED = {"usd": 1.0, "days": 1, "first": "2026-11-01", "from": "2026-11-01", "partial": False, "missing": [],
            "missing_n": 0}


def at(day: dt.date, hhmm: str) -> str:
    return f"{day.isoformat()}T{hhmm}:00Z"


class Lane:
    """An invented lane store under `<tmp>/state/events` and the House's state root `<tmp>/state`."""

    def __init__(self, tmp: str):
        self.state = Path(tmp) / "state"
        self.root = self.state / "events"
        self.st = S.Store(self.root)
        self.n = 0

    def close(self) -> None:
        self.st.close()

    def promote(self, program: str, version: int, since: str = PROMOTED) -> None:
        BA.set_band(self.st, program, version, "probe", since=since, why="look 1 passed", now=S.parse_iso(since))

    def event(self, program: str, version: int, day: dt.date, *, r: float = 0.01, band: str = "probe", issuer: str | None = None,
              qty: int = 10, buy: float = 10.0, fee: float = 0.0, b: float | None = 0.0, shadow_in: float | None = None,
              shadow_out: float | None = None, minute: int | None = None, target: Any = "full",
              sized: Any = "full") -> str:
        """One settled real-money round trip: bought 13:30Z, sold 20:00Z of `day`, after-cost return `r` (no fees). The buy's
        record of its size (release 1019f: `target_usd`, `sized_usd`): by default a FULL buy, its send's dollars at the
        limit (1.25 x the fill) equal to its target; `target`/`sized` given (None: not recorded) say otherwise."""
        self.n += 1
        event = f"8k:invented-{self.n}"
        minute = self.n % 60 if minute is None else minute
        sell = buy * (1.0 + r)
        cik = issuer or f"{self.n % 97:010d}"
        with self.st.tx() as db:
            db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                       "exit_day, exit_at, mode, status) VALUES(?, ?, ?, 'INVT', ?, ?, ?, 'open', ?, 'close', 'real', "
                       "'exited')", (program, version, event, cik, at(day, "13:15"), day.isoformat(), day.isoformat()))
            db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, r, b, a, tradable, "
                       "settled_at, status) VALUES(?, ?, ?, ?, ?, 'SPY', ?, ?, ?, 1, ?, 'settled')",
                       (program, version, event, buy if shadow_in is None else shadow_in,
                        sell if shadow_out is None else shadow_out, r, b, None if b is None else r - b, at(day, "23:30")))
        full = qty * buy * 1.25
        target = full if target == "full" else target
        sized = full if sized == "full" else sized
        for side, price, hhmm in (("buy", buy, f"13:{30 + minute % 30:02d}"), ("sell", sell, f"20:{minute:02d}")):
            size = {"target_usd": target, "sized_usd": sized} if side == "buy" else {}
            BA.record_fill(self.st, program=program, version=version, event=event, side=side, qty=qty, price=price,
                           fee=fee, filled_at=at(day, hhmm), band=band, **size)
        return event

    def stall_runs(self, first: dt.date, last: dt.date, *, owner_on: dt.date | None = None, skip: dt.date | None = None) -> None:
        """An `ok` stall run at 12:00Z of every UTC day in [first, last] (ops.sqlite `runs`)."""
        self.state.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.state / "ops.sqlite")
        db.execute("CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, job TEXT, due_at TEXT, started_at TEXT, "
                   "finished_at TEXT, status TEXT, summary_json TEXT, error TEXT, pid INTEGER, attempts INTEGER)")
        day = first
        while day <= last:
            if day != skip:
                checks = {"births": {"stalled": False, "owner_step": None},
                          "done": {"stalled": True, "owner_step": "news, never a step"}}
                if day == owner_on:
                    checks["kill_on"] = {"stalled": True, "owner_step": "switch the kill switch off"}
                db.execute("INSERT INTO runs(job, due_at, started_at, finished_at, status, summary_json) VALUES('stall', "
                           "?, ?, ?, 'ok', ?)", (at(day, "12:00"), at(day, "12:00"), at(day, "12:01"),
                                                 json.dumps({"checks": checks})))
            day += dt.timedelta(days=1)
        db.commit()
        db.close()


def fills_days(lane: Lane, programs: list[tuple[str, int]], per_program: int, *, per_day: int = 10, **kw) -> dt.date:
    """`per_program` events of each program, `per_day` a program a day from FIRST_DAY; returns the last day."""
    day = FIRST_DAY
    for i in range(per_program):
        day = FIRST_DAY + dt.timedelta(days=i // per_day)
        for program, version in programs:
            lane.event(program, version, day, **kw)
    return day


def attestation(doc, c: int, **kw) -> dict:
    """The captain's attestation of checkpoint c's item-4.8 span (rule item 4.8), steps 0 unless `kw` says otherwise."""
    q = next(h for h in doc["checkpoints"] if h["c"] == c)["items"]["no_captain"]
    to = S.parse_iso(q["to"])
    return {"c": c, "from": q["from"], "to": q["to"], "steps": 0, "execs": 12, "sha256": "ab" * 32,
            "at": S.iso(to + dt.timedelta(hours=6)), **kw}


class DoneCase(unittest.TestCase):
    #: Fewer resamples for speed where the test is not about the bootstrap (the rule's 10,000 is DN.DRAWS itself).
    draws = 400

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lane = Lane(self.tmp.name)
        self.addCleanup(self.lane.close)
        patcher = mock.patch.object(DN, "DRAWS", self.draws)
        patcher.start()
        self.addCleanup(patcher.stop)
        # A file's change times are its mtime and an invented ctime (`self.ctimes`, by name; else its mtime): a file
        # this test makes has a real ctime of the wall clock, which the invented dates of Nov 2026 would meet.
        self.ctimes: dict[str, dt.datetime] = {}

        def moments(path):
            try:
                mtime = dt.datetime.fromtimestamp(Path(path).stat().st_mtime, UTC)
            except OSError:
                return None
            return [mtime, self.ctimes.get(Path(path).name, mtime)]
        patcher = mock.patch.object(DN, "_moments", side_effect=moments)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, *, measured=MEASURED, loss=None, history=(), root="state", attestations=()):
        root = self.lane.state if root == "state" else root
        with mock.patch("league.ops.metered.since", return_value=dict(measured)):
            return DN.read(self.lane.st, now=NOW, root=root, ledger={}, loss=loss, history=history,
                           attestations=attestations)

    def run_night(self, now=NOW, measured=MEASURED):
        with mock.patch("league.ops.metered.since", return_value=dict(measured)), \
                mock.patch("league.ops.metered.load", return_value={}):
            return DN.run(self.lane.st, now=now)


class WhatCounts(DoneCase):
    def test_no_probe_event_counts_nothing(self):
        doc = self.read()
        self.assertEqual((doc["counted"], doc["checkpoints"], doc["next_checkpoint"]), (0, [], 100))
        self.assertFalse(doc["done"]["holds"])
        self.assertFalse(doc["current"]["items"]["events"]["pass"])
        self.assertIsNone(doc["first_promotion"])
        self.assertEqual(doc["profit_vs_compute"]["why"], "no promotion yet")

    def test_learning_events_are_reported_beside_and_never_counted(self):
        program, version = SEATING[0]
        self.lane.promote(program, version)
        for i in range(120):
            self.lane.event(program, version, FIRST_DAY + dt.timedelta(days=i // 20), band="learning", r=0.02)
        doc = self.read()
        self.assertEqual(doc["counted"], 0)
        self.assertEqual(doc["learning"]["n"], 120)
        self.assertGreater(doc["learning"]["pnl_usd"], 0)
        self.assertEqual(doc["checkpoints"], [])
        # Learning money is real money: it is in the lane's profit since the first promotion (rule item 4.6).
        self.assertEqual(doc["profit_vs_compute"]["profit_usd"], doc["learning"]["pnl_usd"])

    def test_probe_events_before_the_promotion_never_count(self):
        program, version = SEATING[0]
        self.lane.promote(program, version, since="2026-11-10T01:00:00Z")
        for i in range(50):     # Probe-band buys from Nov 2 to Nov 6: before the move to probe on Nov 10
            self.lane.event(program, version, FIRST_DAY + dt.timedelta(days=i // 10))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (0, 50))
        self.lane.event(program, version, dt.date(2026, 11, 10))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (1, 50))

    def test_probe_size_is_the_sends_dollars_against_the_target_never_the_fills_cost(self):
        """Release 1019f (rule item 1, AT PROBE SIZE OR ABOVE): a Probe+ buy counts when its `sized_usd` (the shares its
        send asked x the limit) is at least 0.8 x its `target_usd`. A full buy whose fill near the previous close cost
        0.8 of its target counts (the open's gap moves the fill, never the size); a buy cut under 0.8 by a wall or the
        cash does not, nor one with no record; those are `under_size`, beside and never counted."""
        program, version = SEATING[0]
        self.lane.promote(program, version)
        day = FIRST_DAY
        full = self.lane.event(program, version, day, qty=7, buy=10.0, target=87.5,
                               sized=87.5)                     # 7 x $12.50 limit = $87.50 of an $87.50 target: cost $70
        edge = self.lane.event(program, version, day, qty=6, buy=10.0, target=75.0, sized=60.0)      # exactly 0.8
        cut = self.lane.event(program, version, day, qty=2, buy=10.0, target=75.0, sized=25.0)       # the cash cut it
        floor = self.lane.event(program, version, day, qty=1, buy=50.0, target=100.0, sized=62.5)    # 1 share: 0.625
        unrecorded = self.lane.event(program, version, day, target=None, sized=None)               # sized before 1019f
        doc = self.read()
        self.assertEqual((doc["counted"], doc["under_size"]["n"], doc["probe_size_share"]), (2, 3, DN.PROBE_SIZE_SHARE))
        ev = DN.counted(self.lane.st)
        self.assertEqual(sorted(r["event"] for r in ev["counted"]), sorted([full, edge]))
        self.assertEqual(sorted(r["event"] for r in ev["under_size"]), sorted([cut, floor, unrecorded]))
        self.assertEqual(DN.PROBE_SIZE_SHARE, 0.8)
        self.assertEqual([DN.at_size(*x) for x in ((100, 80), (100, 79.99), (None, 80), (100, None), (0, 0), ("x", 80))],
                         [True, False, False, False, False, False])
        rule = (REPO / DN.RULE_FILE).read_text(encoding="utf-8")
        self.assertIn("`sized_usd` (the whole shares its send asked x its limit", rule)
        self.assertIn("at least `PROBE_SIZE_SHARE` (0.8) x its `target_usd`", rule)

    def test_the_guard_is_read_before_the_size(self):
        program, version = SEATING[0]
        self.lane.promote(program, version, since="2026-11-10T01:00:00Z")
        self.lane.event(program, version, FIRST_DAY, target=75.0, sized=25.0)     # before the promotion and under size
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"], doc["under_size"]["n"]), (0, 1, 0))

    def test_a_program_never_moved_to_probe_counts_nothing_even_at_a_probe_band(self):
        program, version = SEATING[1]
        self.lane.event(program, version, FIRST_DAY)
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (0, 1))

    def test_after_a_demotion_and_a_return_every_probe_stay_counts(self):
        """A84: the promotion is the EARLIEST move to probe; the stay a demotion ended stays in the count."""
        program, version = SEATING[0]
        self.lane.promote(program, version)
        self.lane.event(program, version, FIRST_DAY)
        BA.set_band(self.lane.st, program, version, "learning", since="2026-11-03T01:00:00Z", why="demoted",
                    now=S.parse_iso("2026-11-03T01:00:00Z"))
        self.lane.promote(program, version, since="2026-11-04T01:00:00Z")
        self.lane.event(program, version, dt.date(2026, 11, 4))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (2, 0))
        self.assertEqual(doc["first_promotion"], PROMOTED, "the first promotion is the earliest move to probe")
        self.assertEqual(next(p for p in doc["programs"] if p["id"] == program)["promoted_at"], PROMOTED)
        self.assertEqual(DN.promoted_at(self.lane.st, program, version), S.parse_iso(PROMOTED))
        self.assertEqual(BA.probe_since(self.lane.st, program, version), S.parse_iso("2026-11-04T01:00:00Z"),
                         "the band review's current stay is its own (bands.py), never the count's")

    def test_a_demoted_stays_losers_stay_in_the_count_and_done_does_not_hold(self):
        """The review's case: A's first Probe stay (50 losers at -5%) is demoted by the House's own review, a passed
        look returns A to Probe, then A, B and C win 100 each. Checkpoint 300 reads the 50 losers first."""
        lane = self.lane
        a, b, c = SEATING[:3]
        for prog in (a, b, c):
            lane.promote(*prog)
        for i in range(50):
            lane.event(*a, FIRST_DAY + dt.timedelta(days=i // 10), r=-0.05)
        moved = BA.review(lane.st, now=dt.datetime(2026, 11, 7, 1, tzinfo=UTC))
        self.assertEqual([m["program"] for m in moved], [a[0]], "the House's own review demotes A")
        lane.promote(*a, since="2026-11-08T01:00:00Z")
        start, last = dt.date(2026, 11, 9), dt.date(2026, 11, 9)
        for i in range(100):
            last = start + dt.timedelta(days=i // 10)
            for j, prog in enumerate((a, b, c)):
                lane.event(*prog, last, r=0.012 + 0.004 * ((i * 7 + j * 3) % 5 - 2))
        lane.stall_runs(FIRST_DAY - dt.timedelta(days=1), last + dt.timedelta(days=1))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (350, 0))
        cp = next(h for h in doc["checkpoints"] if h["c"] == 300)
        self.assertEqual(cp["figures"]["n"], 300)
        self.assertEqual(sum(1 for r in DN.counted(lane.st)["counted"][:300] if r["r"] < 0), 50,
                         "the demoted stay's 50 losers are the first 50 of the 300")
        self.assertFalse(cp["items"]["bound"]["pass"], cp["items"]["bound"])
        self.assertIsNone(cp["pending"], "an item but item 4.8 fails: no attestation can make it Done")
        doc = self.read(attestations=[attestation(doc, 300)])
        self.assertFalse(doc["done"]["holds"])

    def test_a_probe_buy_with_no_promotion_on_record_inside_the_span_fails_after_promotion(self):
        last = passing(self.lane)
        stray = SEATING[3]     # never moved to probe, yet bought at a probe band (a hand write to the bands table)
        self.lane.event(*stray, last - dt.timedelta(days=2))
        cp = next(h for h in self.read()["checkpoints"] if h["c"] == 300)
        self.assertFalse(cp["items"]["after_promotion"]["pass"])
        self.assertEqual(cp["items"]["after_promotion"]["excluded"], 1)
        self.assertIsNone(cp["pending"])


class Checkpoints(DoneCase):
    def test_the_100th_event_writes_checkpoint_100_over_exactly_the_first_100(self):
        program, version = SEATING[0]
        self.lane.promote(program, version)
        for i in range(99):
            self.lane.event(program, version, FIRST_DAY + dt.timedelta(days=i // 20))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["checkpoints"], doc["next_checkpoint"]), (99, [], 100))
        for i in range(3):
            self.lane.event(program, version, dt.date(2026, 11, 20))
        doc = self.read()
        self.assertEqual(doc["counted"], 102)
        self.assertEqual([h["c"] for h in doc["checkpoints"]], [100])
        self.assertEqual(doc["new_checkpoints"], [100])
        self.assertEqual(doc["checkpoints"][0]["figures"]["n"], 100, "a checkpoint reads exactly its first c events")
        self.assertEqual(doc["next_checkpoint"], 200)
        self.assertFalse(doc["checkpoints"][0]["done"], "100 < 300")

    def test_a_written_checkpoint_is_never_rewritten(self):
        program, version = SEATING[0]
        self.lane.promote(program, version)
        for i in range(100):
            self.lane.event(program, version, FIRST_DAY + dt.timedelta(days=i // 20))
        first = self.run_night()
        path = self.lane.root / DN.FILE
        self.assertTrue(path.exists())
        written = json.loads(path.read_text())["checkpoints"]
        log = (self.lane.root / DN.HISTORY).read_text().splitlines()
        self.assertEqual([json.loads(line)["c"] for line in log], [100], "each new checkpoint is appended once")
        # The data move after the checkpoint (a posted fee): the checkpoint stays as written.
        with self.lane.st.tx() as db:
            db.execute("UPDATE real_fills SET fee=5.0 WHERE side='sell'")
        again = self.run_night(NOW + dt.timedelta(days=1))
        self.assertEqual(again["new_checkpoints"], [])
        self.assertEqual(json.loads(path.read_text())["checkpoints"], written)
        self.assertEqual((self.lane.root / DN.HISTORY).read_text().splitlines(), log, "nothing appended again")
        self.assertEqual(first["checkpoints"][0]["figures"]["pnl_usd"], again["checkpoints"][0]["figures"]["pnl_usd"])
        self.assertLess(again["current"]["figures"]["pnl_usd"], first["current"]["figures"]["pnl_usd"],
                        "the current reading moves; the checkpoint does not")
        self.assertEqual(again["rule"]["sha256"], DN.RULE_SHA256)

    def failed_300(self):
        """Checkpoint 300 written failed (compute above profit that night): the record every test below protects."""
        passing(self.lane)
        first = self.run_night(measured={**MEASURED, "usd": 10_000.0})
        self.assertEqual([h["c"] for h in first["checkpoints"]], [100, 200, 300])
        self.assertFalse(next(h for h in first["checkpoints"] if h["c"] == 300)["items"]["profit_vs_compute"]["pass"])
        return first

    def test_an_unreadable_done_json_is_never_written_over(self):
        """The review's case: done.json at another schema (a restore, a later release rolled back) read as no history
        rewrote checkpoint 300 with the next night's figures. Now nothing is written and the file stays."""
        self.failed_300()
        path = self.lane.root / DN.FILE
        for text in (json.dumps({**json.loads(path.read_text()), "schema": DN.SCHEMA + 1}), '{"schema": 1, "checkp'):
            path.write_text(text)
            with self.assertRaises(DN.Unreadable):
                self.run_night(NOW + dt.timedelta(days=1))
            self.assertEqual(path.read_text(), text, "left as it is")

    def test_a_lost_done_json_is_rebuilt_from_the_append_only_history(self):
        first = self.failed_300()
        (self.lane.root / DN.FILE).unlink()
        again = self.run_night(NOW + dt.timedelta(days=1))
        self.assertEqual(again["new_checkpoints"], [], "no checkpoint written again")
        self.assertEqual(again["checkpoints"], first["checkpoints"])
        self.assertEqual(json.loads((self.lane.root / DN.FILE).read_text())["checkpoints"], first["checkpoints"])

    def test_a_cut_history_line_or_a_checkpoint_a_receipt_names_in_no_history_writes_nothing(self):
        self.failed_300()
        log = self.lane.root / DN.HISTORY
        good = log.read_text()
        log.write_text(good + '{"c": 400, "fig')
        with self.assertRaises(DN.Unreadable):
            self.run_night(NOW + dt.timedelta(days=1))
        log.write_text(good)
        # Both files lost (a restore of the JSON alone), but the House's receipt says checkpoint 300 was written.
        rid = self.lane.st.start_receipt(DN.JOB, now=NOW)
        self.lane.st.finish_receipt(rid, "ok", {"new_checkpoints": [100, 200, 300]}, now=NOW)
        log.unlink()
        (self.lane.root / DN.FILE).unlink()
        with self.assertRaises(DN.Unreadable) as raised:
            self.run_night(NOW + dt.timedelta(days=1))
        self.assertIn("[100, 200, 300]", str(raised.exception))
        self.assertFalse((self.lane.root / DN.FILE).exists(), "nothing written")


def passing(lane: Lane, programs=None, per_program=100, **kw) -> dt.date:
    """300 Probe+ events of three promoted programs, each about +1% after cost, issuers spread, fills at the shadow's
    prices; the stall job ran every day with no owner step."""
    programs = programs or SEATING[:3]
    for program, version in programs:
        lane.promote(program, version)
    rs = kw.pop("rs", None)
    last = FIRST_DAY
    for i in range(per_program):
        day = FIRST_DAY + dt.timedelta(days=i // 10)
        last = day
        for j, (program, version) in enumerate(programs):
            r = rs[(i * len(programs) + j) % len(rs)] if rs else 0.01 + 0.004 * ((i * 7 + j * 3) % 5 - 2)
            lane.event(program, version, day, r=r, **kw)
    lane.stall_runs(FIRST_DAY - dt.timedelta(days=1), last + dt.timedelta(days=1))
    return last


class TheItems(DoneCase):
    def at300(self, doc):
        return next(h for h in doc["checkpoints"] if h["c"] == 300)

    def test_done_holds_at_300_when_every_item_passes_and_the_captain_attests_the_last_100(self):
        """A84: item 4.8 is never a pass from the House's records alone; with every other item passing, checkpoint 300
        waits on the captain's attestation of its span, and Done holds once one with no step is read."""
        passing(self.lane)
        doc = self.read()
        cp = self.at300(doc)
        self.assertEqual({k: v["pass"] for k, v in cp["items"].items()},
                         {k: k != "no_captain" for k in DN.ITEMS}, cp["items"])
        self.assertEqual(cp["items"]["no_captain"]["status"], DN.UNVERIFIABLE)
        self.assertIn("attestation", cp["items"]["no_captain"]["value"])
        self.assertTrue(cp["items"]["no_captain"]["attestation"])
        self.assertFalse(cp["done"])
        self.assertEqual(cp["pending"], "attestation")
        self.assertEqual((doc["done"]["holds"], doc["done"]["pending"]), (False, [300]))
        self.assertEqual([h["c"] for h in doc["checkpoints"]], [100, 200, 300])
        self.assertIsNone(doc["checkpoints"][1]["pending"], "200 < 300")
        self.assertEqual(cp["items"]["programs"]["value"], 3)
        attested = self.read(history=doc["checkpoints"], attestations=[attestation(doc, 300)])
        self.assertEqual({k: attested["done"][k] for k in ("holds", "checkpoint", "by", "pending")},
                         {"holds": True, "checkpoint": 300, "by": "attestation", "pending": []})
        self.assertEqual(attested["new_checkpoints"], [], "the attestation rewrites no checkpoint")

    def test_an_attestation_with_a_step_another_span_or_no_record_is_no_attestation(self):
        passing(self.lane)
        doc = self.read()
        good = attestation(doc, 300)
        for bad in ({"steps": 1}, {"steps": True}, {"steps": None}, {"from": "2026-11-01T00:00:00Z"}, {"sha256": ""},
                    {"at": good["from"]}, {"c": 200}, {"execs": None}, {"execs": -1}):
            got = self.read(history=doc["checkpoints"], attestations=[{**good, **bad}])
            self.assertFalse(got["done"]["holds"], bad)
        got = self.read(history=doc["checkpoints"], attestations=[good, {**good, "steps": 2}])
        self.assertFalse(got["done"]["holds"], "one attestation of the span with a step: no Done")
        # The House's own file: a line that cannot be read gives no attestation at all.
        path = self.lane.root / DN.ATTEST
        path.write_text(json.dumps(good) + "\n{not json\n")
        night = self.run_night()
        self.assertFalse(night["done"]["holds"])
        self.assertIn("cannot be read", night["attestations"]["why"])
        path.write_text(json.dumps(good) + "\n")
        self.assertTrue(self.run_night(NOW + dt.timedelta(days=1))["done"]["holds"])

    def test_fewer_than_three_programs_with_50_each_fails(self):
        passing(self.lane, programs=SEATING[:2], per_program=150)
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["programs"]["pass"])
        self.assertEqual(cp["items"]["programs"]["value"], 2)
        self.assertFalse(cp["done"])

    def test_a_loss_fails_the_pnl_and_the_bound(self):
        passing(self.lane, rs=[-0.01, -0.012, -0.008])
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["pnl"]["pass"])
        self.assertFalse(cp["items"]["bound"]["pass"])
        self.assertLess(cp["items"]["pnl"]["value"], 0)

    def test_a_positive_pnl_whose_bound_is_not_above_zero_fails_the_bound_only(self):
        passing(self.lane, rs=[0.05, -0.0495, 0.051, -0.05])
        cp = self.at300(self.read())
        self.assertTrue(cp["items"]["pnl"]["pass"], cp["items"]["pnl"])
        self.assertFalse(cp["items"]["bound"]["pass"])
        self.assertLessEqual(cp["items"]["bound"]["value"], 0)

    def test_compute_above_profit_or_partly_measured_fails(self):
        passing(self.lane)
        cp = self.at300(self.read(measured={**MEASURED, "usd": 1e6}))
        self.assertFalse(cp["items"]["profit_vs_compute"]["pass"])
        self.assertEqual(cp["items"]["profit_vs_compute"]["compute_usd"], 1e6)
        self.assertFalse(cp["done"])
        cp = self.at300(self.read(measured={**MEASURED, "partial": True}))
        self.assertFalse(cp["items"]["profit_vs_compute"]["pass"])
        self.assertIn("partly measured", cp["items"]["profit_vs_compute"]["why"])
        cp = self.at300(self.read(measured={**MEASURED, "usd": None}))
        self.assertIn("not measured", cp["items"]["profit_vs_compute"]["why"])

    def test_fills_more_than_15bp_worse_than_the_shadow_fail(self):
        passing(self.lane, shadow_in=10.0 / 1.003)     # the real buy 30 bp above the shadow's opening print
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["fills"]["pass"])
        self.assertAlmostEqual(cp["items"]["fills"]["value"]["entry"], 30.0, places=1)
        self.assertAlmostEqual(cp["items"]["fills"]["value"]["exit"], 0.0, places=6)

    def test_fills_are_made_raw_again_against_an_adjusted_shadow_price(self):
        """A dividend after the entry adjusts the shadow's entry price down; the reader divides the adjustment out."""
        passing(self.lane, shadow_in=10.0 * 0.99)
        with self.lane.st.tx() as db:
            for day in range(40):
                d = (FIRST_DAY + dt.timedelta(days=day)).isoformat()
                for adj, c in (("raw", 10.0), ("all", 9.9)):
                    db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('INVT', ?, ?, ?, ?, ?, "
                               "?, 1, ?)", (d, adj, c, c, c, c, PROMOTED))
        cp = self.at300(self.read())
        self.assertAlmostEqual(cp["items"]["fills"]["value"]["entry"], 0.0, places=6)

    def test_no_fill_gap_on_a_side_fails(self):
        passing(self.lane, shadow_out=0.0)
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["fills"]["pass"])
        self.assertEqual(cp["items"]["fills"]["n"]["exit"], 0)

    def test_an_operator_edit_while_the_last_100_settled_fails(self):
        last = passing(self.lane)
        stamp = (last - dt.timedelta(days=1)).strftime("%Y%m%dT120000Z")
        (self.lane.state / f"swarm.json.before-set-{stamp}").write_text("{}")
        (self.lane.state / "swarm.json.before-set-20200101T000000Z").write_text("{}")   # long before: not in the span
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["no_captain"]["pass"])
        self.assertIn("operator edit", cp["items"]["no_captain"]["value"])

    def test_a_hand_edit_of_swarm_json_without_a_before_copy_is_seen_by_its_time(self):
        last = passing(self.lane)
        path = self.lane.state / "swarm.json"
        path.write_text("{}")
        moment = dt.datetime.combine(last, dt.time(15), UTC).timestamp()
        os.utime(path, (moment, moment))
        steps = DN.captain_steps(self.lane.state, dt.datetime.combine(last, dt.time(0), UTC),
                                 dt.datetime.combine(last, dt.time(23), UTC))
        self.assertFalse(steps["holds"])
        self.assertEqual(steps["edits"][0]["file"], "swarm.json")

    def test_an_owner_step_waiting_or_a_day_nobody_looked_fails(self):
        last = passing(self.lane)
        self.lane.stall_runs(last, last, owner_on=last)
        cp = self.at300(self.read())
        self.assertFalse(cp["items"]["no_captain"]["pass"])
        self.assertEqual(cp["items"]["no_captain"]["status"], DN.FAIL)
        self.assertIn("captain step", cp["items"]["no_captain"]["value"])
        self.assertIsNone(cp["pending"], "a step the House saw: no attestation can make it Done")
        steps = DN.captain_steps(self.lane.state, dt.datetime.combine(last, dt.time(0), UTC),
                                 dt.datetime.combine(last, dt.time(23), UTC))
        self.assertEqual(steps["owner"][0]["causes"], ["kill_on"], "the done cause is news, never a step")

    def test_a_utc_day_with_no_stall_run_is_not_held(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        lane = Lane(tmp.name)
        self.addCleanup(lane.close)
        lane.stall_runs(FIRST_DAY, FIRST_DAY + dt.timedelta(days=5), skip=FIRST_DAY + dt.timedelta(days=2))
        steps = DN.captain_steps(lane.state, dt.datetime.combine(FIRST_DAY, dt.time(13), UTC),
                                 dt.datetime.combine(FIRST_DAY + dt.timedelta(days=5), dt.time(20), UTC))
        self.assertFalse(steps["holds"])
        self.assertEqual(steps["unlooked"], [(FIRST_DAY + dt.timedelta(days=2)).isoformat()])
        self.assertFalse(DN.captain_steps(None, NOW, NOW)["holds"], "records not read: not held")

    def test_no_captain_is_never_a_pass_from_the_houses_records_alone(self):
        """The review's case: an edit of swarm.json inside the span hidden by a later touch, and an unstamped
        before-copy (`swarm.json.before-train2020` is on the House), read as no captain step. Now item 4.8 is never a
        pass from the House's records; the later change is named; an unstamped copy made inside the span is an edit."""
        last = passing(self.lane)
        st = self.lane.state
        (st / "swarm.json").write_text("{}")
        (st / "swarm.json.before-train2020").write_text("{}")
        after = dt.datetime.combine(last, dt.time(23, 0), UTC).timestamp()
        os.utime(st / "swarm.json", (after, after))
        q = self.at300(self.read())["items"]["no_captain"]
        self.assertFalse(q["pass"])
        self.assertEqual(q["status"], DN.UNVERIFIABLE)
        self.assertIn("changed after the span", q["value"])
        # The copy's own making (its ctime: a copy keeps the original's mtime) inside the span: an edit.
        self.ctimes["swarm.json.before-train2020"] = dt.datetime.combine(last, dt.time(15), UTC)
        q = self.at300(self.read())["items"]["no_captain"]
        self.assertEqual(q["status"], DN.FAIL)
        self.assertIn("swarm.json.before-train2020", q["value"])
        steps = DN.captain_steps(st, dt.datetime.combine(last, dt.time(0), UTC), dt.datetime.combine(last, dt.time(22), UTC))
        self.assertEqual([(e["file"], e["what"]) for e in steps["edits"]], [("swarm.json", "train2020")])

    def test_a_pause_or_the_kill_switch_seen_at_a_stall_run_is_a_step(self):
        last = passing(self.lane)
        day = last - dt.timedelta(days=3)
        span = (dt.datetime.combine(day, dt.time(0), UTC), dt.datetime.combine(day, dt.time(23), UTC))
        self.assertEqual(DN.captain_steps(self.lane.state, *span)["status"], DN.UNVERIFIABLE)
        for check, numbers in (("paused", {"maintenance_pause": True, "swarm_stopped": False}),
                               ("kill_on", {"kill_switch": True})):
            db = sqlite3.connect(self.lane.state / "ops.sqlite")
            db.execute("DELETE FROM runs")
            db.execute("INSERT INTO runs(job, due_at, status, summary_json) VALUES('stall', ?, 'ok', ?)",
                       (at(day, "12:00"), json.dumps({"checks": {check: {"stalled": False, "owner_step": None,
                                                                         "numbers": numbers}}})))
            db.commit()
            db.close()
            steps = DN.captain_steps(self.lane.state, *span)
            self.assertEqual((steps["status"], steps["owner"][0]["causes"]), (DN.FAIL, [check]), check)
        (self.lane.state / "PAUSE").write_text("")
        self.ctimes["PAUSE"] = dt.datetime.combine(day, dt.time(9), UTC)
        self.assertEqual(DN.captain_steps(self.lane.state, *span)["edits"][0]["file"], "PAUSE")

    def test_an_owner_deploy_in_the_span_is_listed_for_the_attestation(self):
        last = passing(self.lane)
        when = dt.datetime.combine(last - dt.timedelta(days=2), dt.time(21), UTC)
        rows = [{"at": S.iso(when), "stage": "promote", "ok": True, "release": "r-owner", "current": "r-owner"},
                {"at": S.iso(when), "stage": "promote", "ok": True, "release": "r-upd", "sha": "abc"},
                {"at": "2020-01-01T00:00:00Z", "stage": "promote", "ok": True, "release": "r-old"}]
        (self.lane.state.parent / DN.DEPLOYS).write_text("".join(json.dumps(r) + "\n" for r in rows))
        q = self.at300(self.read())["items"]["no_captain"]
        self.assertEqual(q["status"], DN.UNVERIFIABLE)
        self.assertIn("1 owner deploy(s) in the span", q["value"])
        self.assertIn("hand steps", q["value"])
        steps = DN.captain_steps(self.lane.state, S.parse_iso(q["from"]), S.parse_iso(q["to"]))
        self.assertEqual([d["release"] for d in steps["deploys"]], ["r-owner"], "the updater's own deploy is not one")

    def test_the_benchmark_net_figure_rides_beside_and_never_decides(self):
        passing(self.lane, b=0.01)       # the market explains the whole return: a is about zero
        cp = self.at300(self.read())
        self.assertEqual(cp["pending"], "attestation", "the Done test is on r, the after-cost return, as the goal states")
        a = cp["figures"]["a"]
        self.assertEqual(a["n"], 300)
        self.assertLess(a["bound"]["lower"], 0)


class TheChangeTimes(unittest.TestCase):
    def test_a_files_change_times_are_its_mtime_and_its_ctime(self):
        """A copy that keeps the original's mtime (shutil.copy2), or a file touched back in time, still shows its
        ctime: the moment it was made or touched, which no `touch` can move back."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "swarm.json.before-train2020"
            path.write_text("{}")
            made = dt.datetime.now(UTC) - dt.timedelta(seconds=5)
            os.utime(path, (1_600_000_000, 1_600_000_000))
            moments = DN._moments(path)
            self.assertEqual(moments[0], dt.datetime.fromtimestamp(1_600_000_000, UTC))
            self.assertGreaterEqual(max(moments), made)
            self.assertIsNone(DN._moments(Path(tmp) / "absent"))


class TheBootstrap(unittest.TestCase):
    def test_it_is_deterministic_with_10000_resamples_issuers_as_blocks_and_the_fixed_seed(self):
        self.assertEqual((DN.DRAWS, DN.LEVEL, DN.SEED_DONE), (10_000, 0.95, "DONE-RULE-EVL-2|done|issuer"))
        rows = [{"issuer": f"c{i % 40}", "r": 0.01 * ((i * 37) % 11 - 4), "entry_day": "2026-11-02"} for i in range(120)]
        one, two = DN._bound(rows, DN.SEED_DONE), DN._bound(rows, DN.SEED_DONE)
        self.assertEqual(one, two)
        ref = SC.bootstrap_bounds(rows, "issuer", 0.95, 10_000, SC.seed_of(DN.SEED_DONE))
        self.assertEqual((one["lower"], one["issuers"], one["n"]), (ref["lower"], 40, 120))
        self.assertNotEqual(one["lower"], DN._bound(rows, "another seed")["lower"])


class PivotAndStop(DoneCase):
    def test_the_pivot_is_read_from_400_and_retires_a_losing_lane(self):
        passing(self.lane, per_program=134, rs=[-0.01, -0.012, -0.008, -0.011])
        doc = self.read()
        cps = {h["c"]: h for h in doc["checkpoints"]}
        self.assertEqual(sorted(cps), [100, 200, 300, 400])
        self.assertFalse(cps[300]["pivot"]["read"])
        self.assertTrue(cps[400]["pivot"]["read"])
        self.assertTrue(cps[400]["pivot"]["retire"])
        self.assertLess(cps[400]["pivot"]["upper"], 0)
        self.assertTrue(doc["pivot"]["retire"])

    def test_a_winning_lane_is_not_retired_at_400(self):
        passing(self.lane, per_program=134)
        cps = {h["c"]: h for h in self.read()["checkpoints"]}
        self.assertFalse(cps[400]["pivot"]["retire"])

    def test_the_800_stop(self):
        spent = DN._stop({"realized_total_usd": "700.00", "at_risk_usd": "100.00", "total_budget_usd": "800"}, NOW)
        self.assertTrue(spent["spent"])
        self.assertIn("stop all spend", spent["why"])
        room = DN._stop({"realized_total_usd": "560.51", "at_risk_usd": "95.63", "total_budget_usd": "800"}, NOW)
        self.assertEqual((room["spent"], room["used_usd"]), (False, 656.14))
        unread = DN._stop(None, NOW)
        self.assertIsNone(unread["spent"])
        self.assertTrue(unread["why"])
        # Never above the owner's $800, whatever the table says.
        self.assertTrue(DN._stop({"realized_total_usd": "800", "at_risk_usd": "0", "total_budget_usd": "900"}, NOW)["spent"])
        doc = self.read(loss={"realized_total_usd": "700.00", "at_risk_usd": "100.00", "total_budget_usd": "800"})
        self.assertTrue(doc["stop"]["spent"])


class ThePin(unittest.TestCase):
    def test_the_rule_file_is_pinned_by_its_sha256(self):
        digest = hashlib.sha256((REPO / DN.RULE_FILE).read_bytes()).hexdigest()
        self.assertEqual(digest, DN.RULE_SHA256, "DONE-RULE-EVL-2.md changed: a new rule is an amendment and a new pin")
        self.assertEqual(DN.rule_sha256(REPO), DN.RULE_SHA256)
        text = (REPO / DN.RULE_FILE).read_text()
        for words in ("read every 100 settled real-money events at Probe size or above", ">= 300 such events",
                      "from >= 3 programs with >= 50 each", "fills within 15 bp of replay",
                      "the last 100 of those events with no captain step", "below zero at 400 events",
                      "when the $800 loss budget is spent, stop all spend and report"):
            self.assertIn(words, text)


class ReadOnly(DoneCase):
    def test_the_reader_opens_nothing_for_writing(self):
        passing(self.lane, per_program=40)
        from league.ops.daily_report import ReadOnlyStore

        with guard.readonly():
            store = ReadOnlyStore(self.lane.root)
            try:
                with mock.patch("league.ops.metered.since", return_value=dict(MEASURED)):
                    doc = DN.read(store, now=NOW, root=self.lane.state, ledger={}, loss=None)
            finally:
                store.close()
        self.assertEqual(doc["counted"], 120)
        self.assertEqual([h["c"] for h in doc["checkpoints"]], [100])


class OnTheHouse(unittest.TestCase):
    def night(self):
        """The lane of league/tests/test_events_house.py at Tue Oct 20, 20:31 ET with the day decided and scored."""
        from league.events import score as SCO
        from league.tests import test_events_house as TH

        case = type("Night", (TH.LaneCase,), {"runTest": lambda self: None})()
        case.setUp()
        self.addCleanup(case.doCleanups)
        with case.store() as st:
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=TH.et("2026-10-20", t))
                st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", t))
            st.set_meta(SCO.equity_key(dt.date(2026, 10, 20)), repr(2000.0))
        case.lane._redecide_next = TH.et("2026-10-21", "00:00")
        case.at(TH.et("2026-10-20", "20:31"))
        case.mark_recorded()
        self.assertEqual(case.turn()["task"], "score")
        case.mark_recorded()
        return case

    def test_the_nightly_screen_runs_the_reader_after_the_band_review(self):
        case = self.night()
        self.assertEqual(case.turn()["task"], "screen")
        path = case.root / DN.FILE
        self.assertTrue(path.exists())
        doc = json.loads(path.read_text())
        self.assertEqual((doc["counted"], doc["rule"]["sha256"]), (0, DN.RULE_SHA256))
        receipts = case.receipts(DN.JOB)
        self.assertEqual(len(receipts), 1)
        summary = json.loads(receipts[0]["summary"])
        self.assertEqual((summary["counted"], summary["next_checkpoint"], summary["done"]), (0, 100, False))
        self.assertEqual(json.loads(case.receipts("screen")[-1]["summary"])["review"], [])
        self.assertLess(case.receipts("screen")[-1]["id"], receipts[0]["id"], "after the screen and its band review")

    def test_an_unreadable_done_json_warns_and_is_left_as_it_is(self):
        case = self.night()
        path = case.root / DN.FILE
        path.write_text('{"schema": 99}')
        self.assertEqual(case.turn()["task"], "screen")
        self.assertEqual(path.read_text(), '{"schema": 99}')
        self.assertEqual(case.receipts(DN.JOB), [])
        self.assertIn("warning", case.house.levels())

    def test_a_reader_that_fails_never_fails_the_screen(self):
        case = self.night()
        before = len(case.receipts("screen"))      # (release 1019f's harness holds Monday night's screen receipt too)
        with mock.patch.object(DN, "run", side_effect=RuntimeError("invented")):
            self.assertEqual(case.turn()["task"], "screen")
        self.assertEqual(len(case.receipts("screen")), before + 1)
        self.assertEqual(case.receipts(DN.JOB), [])
        self.assertIn("warning", case.house.levels())


class TheDailyReport(DoneCase):
    def test_the_report_carries_one_done_line_from_the_nights_done_json(self):
        from league.ops import daily_report as DR

        line = DR.done_line(self.lane.state)
        self.assertIsNone(line["counted"], "no done.json: not read yet")
        self.assertEqual(len(line["by_program"]), len(SEATING))
        passing(self.lane, per_program=40)
        with mock.patch("league.ops.metered.since", return_value=dict(MEASURED)), \
                mock.patch("league.ops.metered.load", return_value={}):
            doc = DN.run(self.lane.st, now=NOW)
        line = DR.done_line(self.lane.state)
        self.assertEqual((line["counted"], line["next_checkpoint"], line["toward"]), (120, 200, 300))
        self.assertEqual(line["lower_bp"], round(doc["current"]["figures"]["bound"]["lower"] * 1e4, 1))
        self.assertIsNotNone(line["lower_a_bp"])
        self.assertEqual({(r["id"], r["n"]) for r in line["by_program"] if r["n"]},
                         {(p, 40) for p, _ in SEATING[:3]})
        self.assertEqual((line["holds"], line["pivot"], line["stop"]), (False, False, None))


if __name__ == "__main__":
    unittest.main()
