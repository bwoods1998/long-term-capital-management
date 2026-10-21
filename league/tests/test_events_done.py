"""THE DONE READER OF THE GOAL V2 (league/events/done.py; docs/goals/DONE-RULE-EVL-2.md), on invented data only.

- what counts: no Probe event counts nothing; learning events are beside, never counted; Probe+ buys before the
  program's latest move to probe are beside, never counted;
- the checkpoints: the 100th counted event writes checkpoint 100, over exactly the first 100, and a written checkpoint
  is never rewritten (the history append-only, through done.json);
- each item's pass and fail: events, programs, P&L, the bound, profit against compute, the fills, no captain step;
- the bootstrap is deterministic (10,000 resamples, the fixed seed string, issuers as blocks); the pivot at 400; the
  $800 stop; the rule file pinned by its sha256; the reader opens nothing for writing; the House's nightly screen runs
  it after the band review and keeps a `done` receipt.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
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
              shadow_out: float | None = None, minute: int | None = None) -> str:
        """One settled real-money round trip: bought 13:30Z, sold 20:00Z of `day`, after-cost return `r` (no fees)."""
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
        for side, price, hhmm in (("buy", buy, f"13:{30 + minute % 30:02d}"), ("sell", sell, f"20:{minute:02d}")):
            BA.record_fill(self.st, program=program, version=version, event=event, side=side, qty=qty, price=price,
                           fee=fee, filled_at=at(day, hhmm), band=band)
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

    def read(self, *, measured=MEASURED, loss=None, history=(), root="state"):
        root = self.lane.state if root == "state" else root
        with mock.patch("league.ops.metered.since", return_value=dict(measured)):
            return DN.read(self.lane.st, now=NOW, root=root, ledger={}, loss=loss, history=history)


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

    def test_a_program_never_moved_to_probe_counts_nothing_even_at_a_probe_band(self):
        program, version = SEATING[1]
        self.lane.event(program, version, FIRST_DAY)
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (0, 1))

    def test_after_a_demotion_and_a_return_only_the_current_stay_counts(self):
        program, version = SEATING[0]
        self.lane.promote(program, version)
        self.lane.event(program, version, FIRST_DAY)
        BA.set_band(self.lane.st, program, version, "learning", since="2026-11-03T01:00:00Z", why="demoted",
                    now=S.parse_iso("2026-11-03T01:00:00Z"))
        self.lane.promote(program, version, since="2026-11-04T01:00:00Z")
        self.lane.event(program, version, dt.date(2026, 11, 4))
        doc = self.read()
        self.assertEqual((doc["counted"], doc["before_promotion"]["n"]), (1, 1))
        self.assertEqual(doc["first_promotion"], PROMOTED, "the first promotion is the earliest move to probe")


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
        with mock.patch("league.ops.metered.since", return_value=dict(MEASURED)), \
                mock.patch("league.ops.metered.load", return_value={}):
            first = DN.run(self.lane.st, now=NOW)
            path = self.lane.root / DN.FILE
            self.assertTrue(path.exists())
            written = json.loads(path.read_text())["checkpoints"]
            # The data move after the checkpoint (a posted fee): the checkpoint stays as written.
            with self.lane.st.tx() as db:
                db.execute("UPDATE real_fills SET fee=5.0 WHERE side='sell'")
            again = DN.run(self.lane.st, now=NOW + dt.timedelta(days=1))
        self.assertEqual(again["new_checkpoints"], [])
        self.assertEqual(json.loads(path.read_text())["checkpoints"], written)
        self.assertEqual(first["checkpoints"][0]["figures"]["pnl_usd"], again["checkpoints"][0]["figures"]["pnl_usd"])
        self.assertLess(again["current"]["figures"]["pnl_usd"], first["current"]["figures"]["pnl_usd"],
                        "the current reading moves; the checkpoint does not")
        self.assertEqual(again["rule"]["sha256"], DN.RULE_SHA256)


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

    def test_done_holds_at_300_when_every_item_passes(self):
        passing(self.lane)
        doc = self.read()
        cp = self.at300(doc)
        self.assertEqual({k: v["pass"] for k, v in cp["items"].items()}, {k: True for k in DN.ITEMS}, cp["items"])
        self.assertTrue(cp["done"])
        self.assertEqual(doc["done"], {"holds": True, "checkpoint": 300})
        self.assertEqual([h["c"] for h in doc["checkpoints"]], [100, 200, 300])
        self.assertFalse(doc["checkpoints"][1]["done"], "200 < 300")
        self.assertEqual(cp["items"]["programs"]["value"], 3)

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
        import os

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
        self.assertIn("owner step", cp["items"]["no_captain"]["value"])
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

    def test_the_benchmark_net_figure_rides_beside_and_never_decides(self):
        passing(self.lane, b=0.01)       # the market explains the whole return: a is about zero
        cp = self.at300(self.read())
        self.assertTrue(cp["done"], "the Done test is on r, the after-cost return, as the goal states")
        a = cp["figures"]["a"]
        self.assertEqual(a["n"], 300)
        self.assertLess(a["bound"]["lower"], 0)


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

    def test_a_reader_that_fails_never_fails_the_screen(self):
        case = self.night()
        with mock.patch.object(DN, "run", side_effect=RuntimeError("invented")):
            self.assertEqual(case.turn()["task"], "screen")
        self.assertEqual(len(case.receipts("screen")), 1)
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
