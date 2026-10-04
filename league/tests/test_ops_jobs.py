"""The House's jobs: the venue clock, hygiene, the public scoreboard, the pre-open checks, the receipts, the wiring."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from ltcm.data import us_equity_session

from league.ops import clock as C
from league.ops import hygiene as HY
from league.ops import preopen as PO
from league.ops import receipts as R
from league.ops import scoreboard as SB
from league.ops.context import Context, GatewayError
from league.ops.store import OpsStore
from league.sailbox import SailboxError
from league.tests.test_swarm_store import SPEC

NY = ZoneInfo("America/New_York")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ops_economics"


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def venue_calendar(start, days=30):
    """Alpaca's calendar rows as the House's own calendar would give them."""
    rows, day = [], start
    for _ in range(days):
        s = us_equity_session(day)
        if s is not None:
            hhmm = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(NY).strftime("%H:%M")  # noqa: E731
            rows.append({"date": day.isoformat(), "open": hhmm(s.open_at), "close": hhmm(s.close_at)})
        day += timedelta(days=1)
    return rows


class FakeGateway:
    def __init__(self, answers=None, post_error=None):
        self.answers = answers or {}
        self.gets, self.posts = [], []
        self.post_error = post_error

    def get(self, path, params=None):
        self.gets.append((path, params))
        value = self.answers.get(path)
        if isinstance(value, Exception):
            raise value
        return value

    def post(self, path, body):
        self.posts.append((path, body))
        if self.post_error is not None:
            raise self.post_error
        return {"commit": "c0ffee"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.now = at("2026-10-06T02:00:00Z")

    def ctx(self, job, *, gateway=None, sail=None, settings=None, due=None):
        return Context(job, root=self.root, base=self.base, due_at=due if due is not None else self.now, config={},
                       clock=lambda: self.now, gateway=gateway, sail=sail, settings_value=settings or {})


class Clock(Base):
    def test_a_calendar_that_agrees_has_no_mismatch(self):
        start = date(2026, 10, 5)
        result = C.compare(venue_calendar(start), start)
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(len([r for r in result["sessions"] if r["house"]]), 10)

    def test_a_holiday_and_an_early_close_the_house_gets_wrong_are_mismatches(self):
        start = date(2026, 11, 23)
        rows = venue_calendar(start)
        rows.append({"date": "2026-11-26", "open": "09:30", "close": "16:00"})  # the venue trades Thanksgiving
        for row in rows:
            if row["date"] == "2026-11-27":
                row["close"] = "16:00"  # and the day after closes late
        why = {m["day"]: m["why"] for m in C.compare(rows, start)["mismatches"]}
        self.assertEqual(why["2026-11-26"], "the venue trades and the House does not")
        self.assertEqual(why["2026-11-27"], "the session's hours differ")

    def test_run_reads_the_venue_through_the_gateway_writes_the_calendar_and_warns(self):
        self.now = at("2026-10-05T11:00:00Z")
        rows = venue_calendar(date(2026, 10, 5))
        rows = [r for r in rows if r["date"] != "2026-10-07"]  # the venue says closed on a day the House trades
        gateway = FakeGateway({"/v1/alpaca/v2/clock": {"is_open": False, "next_open": "x"}, "/v1/alpaca/v2/calendar": rows})
        ctx = self.ctx("clock", gateway=gateway)
        out = C.run(ctx)
        self.assertFalse(out["ok"])
        self.assertEqual([p for p, _ in gateway.gets], ["/v1/alpaca/v2/clock", "/v1/alpaca/v2/calendar"])
        saved = json.loads((self.root / "calendar.json").read_text())
        self.assertEqual(saved["mismatches"][0]["day"], "2026-10-07")
        self.assertEqual(ctx.alerts[0]["level"], "warning")
        self.assertEqual(os.stat(self.root / "calendar.json").st_mode & 0o777, 0o600)


class FakeSail:
    def __init__(self, rows):
        self.rows = rows

    def get(self, box):
        value = self.rows[box]
        if isinstance(value, Exception):
            raise value
        return value


class Hygiene(Base):
    def setUp(self):
        super().setUp()
        from league.live.observe import ObserveStore
        from league.swarm.store import SwarmStore

        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.observe = ObserveStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.addCleanup(self.observe.close)
        db = self.observe._connect()
        for fid in ("barred", "retired", "alive"):
            self.store.add_family({**SPEC, "id": fid}, origin="seed")
            db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES(?,?,?,?,?)",
                       (fid, 1, self.now, "2026-10-01", json.dumps({"run_sha": f"sha-{fid}"})))
        self.store.set_state("barred", incubator_barred={"sha-barred": {"why": "its audit failed", "at": 1.0}})
        self.store.retire("retired", "a test retirement of this family")

    def statuses(self):
        db = self.observe._connect()
        return {r[0]: (r[1], r[2]) for r in db.execute("SELECT family, status, reason FROM cohorts")}

    def test_barred_cohorts_end_and_retired_family_cohorts_are_kept_unless_the_owner_says(self):
        out = HY.end_cohorts(self.ctx("hygiene"), "2026-10-06", end_retired=False, store=self.observe)
        self.assertEqual([e["cohort"] for e in out["ended"]], ["barred@1"])
        self.assertEqual(out["retired_family_kept"], ["retired@1"])
        status = self.statuses()
        self.assertEqual(status["barred"][0], "failed")
        self.assertTrue(status["barred"][1].startswith("hygiene: its program is barred from the incubator (its audit failed)"))
        self.assertEqual((status["retired"][0], status["alive"][0]), ("active", "active"))
        HY.end_cohorts(self.ctx("hygiene"), "2026-10-06", end_retired=True, store=self.observe)
        self.assertEqual(self.statuses()["retired"], ("failed", "hygiene: its research family retired"))
        self.assertEqual(self.statuses()["alive"][0], "active")

    def test_a_cohort_that_ended_since_it_was_read_keeps_its_own_ending(self):
        """The sweep reads the active cohorts and writes later, on another connection than the House's: a cohort the
        ladder promoted (or that ended) in between is not failed over it, and is not listed as ended."""
        from unittest import mock

        read = HY.cohorts(self.root)
        self.assertEqual(sorted(r["family"] for r in read), ["alive", "barred", "retired"])
        db = self.observe._connect()
        db.execute("UPDATE cohorts SET status='promoted', completed_day='2026-10-05', reason='ladder: promoted to Probe "
                   "(receipt 7)' WHERE family='barred'")
        db.execute("UPDATE cohorts SET status='complete', completed_day='2026-10-05', reason='ladder: its practice window "
                   "ended' WHERE family='retired'")
        with mock.patch.object(HY, "cohorts", return_value=read):
            out = HY.end_cohorts(self.ctx("hygiene"), "2026-10-06", end_retired=True, store=self.observe)
        self.assertEqual(out["ended"], [])
        self.assertEqual(self.statuses(), {"barred": ("promoted", "ladder: promoted to Probe (receipt 7)"),
                                           "retired": ("complete", "ladder: its practice window ended"),
                                           "alive": ("active", None)})

    def test_failed_pool_rows_become_terminated_only_when_sail_says_the_box_is_gone(self):
        for box in ("sb_00000001", "sb_00000002", "sb_00000003", "sb_00000004"):
            self.store.upsert_box(box, kind="gym", version="v", state="failed")
        sail = FakeSail({"sb_00000001": {"status": "terminated"}, "sb_00000002": SailboxError("gone", status=404),
                         "sb_00000003": {"status": "running"}, "sb_00000004": SailboxError("bad gateway", status=502)})
        out = HY.clean_pool(self.ctx("hygiene", sail=sail), store=self.store)
        self.assertEqual(out["failed_rows"], 4)
        self.assertEqual(sorted(out["terminated"]), ["sb_00000001 (terminated)", "sb_00000002 (absent)"])
        self.assertEqual(out["still_running_at_sail"], ["sb_00000003 (running)"])
        self.assertEqual(len(out["errors"]), 1)
        states = {b["id"]: b["state"] for b in self.store.boxes(live=False)}
        self.assertEqual(states["sb_00000003"], "failed")
        self.assertEqual(states["sb_00000001"], "terminated")

    def test_idle_families_retire_by_the_tournament_rule_sparing_busy_ones_and_the_floor(self):
        from league.swarm import settings as swarm_settings

        settings = swarm_settings.load(self.root, config={})
        settings["population"]["floor"] = 0
        for fid in ("dormant-a", "dormant-b"):
            self.store.add_family({**SPEC, "id": fid}, origin="seed")
            self.store.set_state(fid, dormant_cycles=10_000)
        self.store.event("swarm.cycle", "dormant-b", {"cycle": 1})
        out = HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)
        self.assertEqual(out["retired"], ["dormant-a"])
        self.assertEqual(out["busy"], 1)
        settings["population"].update(floor=100, floor_researching=False)  # the floor counting every family, as before F1
        self.now += 3600
        self.assertEqual(HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)["retired"], [])
        # THE FLOOR COUNTS RESEARCH (F1, the default): a dormant family is a dead slot, which no floor holds.
        settings["population"]["floor_researching"] = True
        self.assertEqual(HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)["retired"], ["dormant-b"])

    def test_a_family_the_swarms_heartbeat_names_in_a_cycle_is_spared_until_the_heartbeat_is_stale(self):
        from league.swarm import HEARTBEAT, settings as swarm_settings

        settings = swarm_settings.load(self.root, config={})
        settings["population"]["floor"] = 0
        for fid in ("dormant-a", "dormant-b"):
            self.store.add_family({**SPEC, "id": fid}, origin="seed")
            self.store.set_state(fid, dormant_cycles=10_000)
        # dormant-b's cycle started a minute ago: no `swarm.cycle` event yet (it is written when the cycle ends).
        beat = self.root / HEARTBEAT
        beat.write_text(json.dumps({"at": self.now - 20, "status": {"running": 1, "running_families": ["dormant-b"]}}))
        out = HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)
        self.assertEqual((out["retired"], out["busy"]), (["dormant-a"], 1))
        # A fresh heartbeat that counts running cycles but names none (an older swarm): the part judges no family.
        beat.write_text(json.dumps({"at": self.now - 20, "status": {"running": 2}}))
        self.assertIn("skipped", HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings))
        self.assertIsNone(self.store.family("dormant-b").get("retired_at"))
        # A stale heartbeat: no swarm loop is taking turns, and the backstop judges every family.
        beat.write_text(json.dumps({"at": self.now - 3600, "status": {"running": 1, "running_families": ["dormant-b"]}}))
        self.assertEqual(HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)["retired"], ["dormant-b"])

    def test_stale_live_instances_are_reported(self):
        (self.root / "health.json").write_text(json.dumps({"options_live": {"instances": {
            "retired@1:o": {"family": "retired", "mode": "observe"}, "alive@1:o": {"family": "alive", "mode": "observe"},
            "alive@1:r": {"family": "alive", "mode": "real", "error": "decider down"},
            "house:calibration": {"family": "house:calibration"}, "ghost@2:o": {"family": "ghost"}}}}))
        out = HY.stale_instances(self.ctx("hygiene"))
        self.assertEqual({r["instance"]: r["why"] for r in out["stale"]},
                         {"retired@1:o": "its family retired", "alive@1:r": "it errors: decider down",
                          "ghost@2:o": "its family is unknown to the swarm"})

    def test_never_inside_a_session(self):
        self.now = at("2026-10-05T15:00:00Z")
        self.assertEqual(HY.run(self.ctx("hygiene"))["status"], "skipped")

    def test_one_part_failing_leaves_the_others_and_a_warning(self):
        sail = FakeSail({})
        self.store.upsert_box("sb_00000009", kind="gym", version="v", state="failed")
        out = HY.run(self.ctx("hygiene", sail=sail, settings={"hygiene": {"retire_idle": False}}))
        self.assertIn("error", out["pool"])
        self.assertEqual([e["cohort"] for e in out["cohorts"]["ended"]], ["barred@1"])
        self.assertEqual(out["idle"], {"off": True})


class Scoreboard(Base):
    def economics(self):
        summary = json.loads((FIXTURES / "expected-summary.json").read_text())
        for c in summary["costs"]:
            c["basis"] = "a long private basis naming SPY261009C00600000 and an equity of 1300"
        summary["p30"] = {"usd": "4.67", "days": 30, "from_day": "2026-09-07", "to_day": "2026-10-06", "closed_positions": 3}
        return summary

    def test_the_public_filter_catches_what_a_public_page_may_not_carry(self):
        for text, problem in (("long SPY261009C00600000", "an option contract symbol"), ("equity 1300", "account equity"),
                              ("the bid was 4.10", "a quote"), ("def decide(ctx):", "program text"),
                              ("PARAMS = {}", "program text"), ("box sb_1d99c4a7 died", "a Sail box or checkpoint id"),
                              ("holdout t 2.4", "a Validation or holdout figure"), ("cash balance 12", "an account balance")):
            self.assertIn(problem, SB.public_problems(text), text)
        self.assertEqual(SB.public_problems("Net -165.66; realized 4.67; 3 closes"), [])

    def test_the_page_is_built_from_figures_only_and_passes_the_filter(self):
        text = SB.build(day="2026-10-06", release="20261006T010000Z-x", economics=self.economics(),
                        deploys={"self_promoted": 3, "self_rolled_back": 1}, budget={"state": "no forward edge; research at floor",
                        "direction": "cut", "meters": {"sail": {"research_usd_day": "3.00", "balance_usd": "999"}},
                        "next_card_action": {"sail": "2027-01-04"}},
                        ladder={"binding": False, "entrants": 61, "in_practice": 12, "would_promote": 2, "promoted": 0,
                                "demoted": 0, "failed": 7},
                        jobs={"ok": 5, "missed": 1}, written_at="23:30Z")
        self.assertEqual(SB.public_problems(text), [])
        self.assertIn("The ladder is RECORDING", text)
        self.assertIn("It promotes nothing.", text)
        self.assertIn("| 61 | 12 | 2 | 0 | 0 | 7 |", text)
        self.assertIn("**Net on priced inputs (incomplete)** | **-165.41**", text)
        self.assertIn("| Realized options P&L, trailing 30 days | 4.67 |", text)
        # THE BUDGET IN WORDS (release F1): a meter's research cap is never printed (the rule's constants are public, so
        # a tapered cap gives its balance); its state is said in words (a file that names none: n/a) beside its dates.
        self.assertIn("| sail | n/a | n/a | 2027-01-04 |", text)
        self.assertNotIn("3.00", text[text.index("## Budget"):text.index("## Releases")])
        self.assertIn("Self-deployed releases since T0: 3", text)
        self.assertNotIn("999", text)
        self.assertNotIn("SPY2610", text)

    def test_deploy_counts_tell_the_updater_from_the_owner(self):
        rows = [{"at": "2026-10-06T21:00:00.000Z", "stage": "verdict", "verdict": "promoted", "sha": "a" * 40},
                {"at": "2026-10-06T22:00:00.000Z", "stage": "verdict", "verdict": "rolled_back", "sha": "b" * 40},
                {"at": "2026-10-05T22:00:00.000Z", "stage": "verdict", "verdict": "promoted"},
                {"at": "2026-10-06T22:00:00.000Z", "stage": "promote", "ok": True, "sha": "a" * 40},
                {"at": "2026-09-01T00:00:00.000Z", "stage": "verdict", "verdict": "promoted", "sha": "c" * 40}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        got = SB.deploy_counts(self.base, day="2026-10-06")
        self.assertEqual((got["self_promoted"], got["self_rolled_back"], got["owner_promoted"]), (1, 1, 1))
        self.assertEqual((got["self_promoted_today"], got["self_rolled_back_today"]), (1, 1))

    def test_the_rollback_drills_verdicts_are_neither_the_owners_nor_the_updaters(self):
        rows = [{"at": "2026-10-03T15:05:00.000Z", "stage": "verdict", "verdict": "rolled_back", "release": "drill-20261003T150000Z"},
                {"at": "2026-10-03T15:05:01.000Z", "stage": "drill", "outcome": "rolled_back", "release": "drill-20261003T150000Z"},
                {"at": "2026-10-03T16:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "20261003T160000Z-abc"}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        got = SB.deploy_counts(self.base, day="2026-10-03")
        self.assertEqual((got["drill_rolled_back"], got["owner_rolled_back"], got["owner_promoted"], got["self_rolled_back"]), (1, 0, 1, 0))

    def test_a_rollback_drill_is_counted_as_a_drill_never_as_an_owner_deploy(self):
        rows = [{"at": "2026-10-10T15:20:00.000Z", "stage": "verdict", "verdict": "rolled_back",
                 "release": "drill-20261010T150000Z", "deploy": "drill-20261010T150000Z@1"},
                {"at": "2026-10-10T15:21:00.000Z", "stage": "drill", "outcome": "passed", "ok": True,
                 "release": "drill-20261010T150000Z"},
                {"at": "2026-10-10T16:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "20261010-owner"}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        got = SB.deploy_counts(self.base, day="2026-10-10")
        self.assertEqual((got["drill_rolled_back"], got["drill_promoted"]), (1, 0))
        self.assertEqual((got["owner_promoted"], got["owner_rolled_back"], got["self_rolled_back"]), (1, 0, 0))
        text = SB.build(day="2026-10-10", release="r", economics=None, deploys=got, budget=None,
                        ladder={"binding": "n/a", **{key: "n/a" for key in SB.LADDER_COUNTS}},
                        jobs={"ok": 0, "failed": 0, "missed": 0, "skipped": 0}, written_at="2026-10-10T23:30:00Z")
        self.assertIn("Owner deploys: 1 promoted, 0 rolled back. Rollback drills: 1 rolled back as intended, 0 not caught.", text)
        self.assertEqual(SB.public_problems(text), [])

    def test_ladder_counts_are_na_until_the_ladder_tables_exist(self):
        from league.live.ladder import Rules

        na = {"binding": Rules.from_constitution().binding, **{key: "n/a" for key in SB.LADDER_COUNTS}}
        self.assertEqual(SB.ladder_counts(self.root, self.now), na, "no practice record: the table's boolean alone")
        db = sqlite3.connect(self.root / "observe.sqlite")       # a record from before the ladder: cohorts, no entrants
        db.execute("CREATE TABLE cohorts (family TEXT, version INTEGER, status TEXT)")
        db.execute("INSERT INTO cohorts VALUES ('a', 1, 'active'), ('b', 1, 'failed')")
        db.commit()
        db.close()
        self.assertEqual(SB.ladder_counts(self.root, self.now), na, "its cohorts are no ladder cohorts")
        with sqlite3.connect(self.root / "observe.sqlite") as db: # tables the ladder's own read cannot read: n/a, never a guess
            db.execute("CREATE TABLE entrants (family TEXT, entered_at REAL)")
        self.assertEqual(SB.ladder_counts(self.root, self.now), na)

    def test_the_ladders_own_counts_are_read_from_its_record(self):
        """`league.live.ladder.counts` through the practice record's own store: one entrant a cohort inside the trailing
        90 days, the cohorts practising, what it would promote, a promotion by its receipt (a pending one is none), a
        demotion and a failure. Counts only."""
        from league.live import ladder as L
        from league.live.observe import ObserveStore

        store = ObserveStore(self.root, clock=lambda: self.now)
        self.addCleanup(store.close)
        store.evaluator = "bundle:fills:exec"
        for fid in ("fx-up", "fx-down", "fx-would", "fx-out", "fx-busy", "fx-pending", "fx-long-ago"):
            store.freeze({"family": fid, "version": 1, "band": "gym", "observe": True, "tier": "validated", "lineage": fid,
                          "code": "NEEDS = {'roots': ['SPY'], 'dte': [0, 3]}\n", "params": {}, "run_sha": f"sha-{fid}"},
                         day="2026-09-21")
        store._connect().execute("UPDATE entrants SET entered_day='2026-06-01' WHERE family='fx-long-ago'")
        receipt = {"day": "2026-10-02", "version": 1, "inputs": "x", "stats": {}, "binding": True}
        for fid in ("fx-up", "fx-down"):
            store.settle_answer(store.add_decision({**receipt, "family": fid, "verdict": L.PROMOTE_PENDING}), "promote",
                                day="2026-10-02", close="promoted", reason="ladder: promoted to Probe")
        store.close_cohort("fx-down", 1, status="demoted", day="2026-10-05", reason="ladder: its forward record",
                           was=("promoted",))
        store.add_decision({**receipt, "family": "fx-pending", "verdict": L.PROMOTE_PENDING})
        store.add_decision({**receipt, "family": "fx-would", "verdict": "would_promote", "binding": False})
        store.fail_cohort("fx-out", 1, day="2026-10-02", reason="ladder: its family retired")
        counts = SB.ladder_counts(self.root, self.now)
        self.assertEqual(counts, {"binding": L.Rules.from_constitution().binding, "entrants": 6, "in_practice": 4,
                                  "would_promote": 1, "promoted": 2, "demoted": 1, "failed": 1})
        text = "\n".join(SB.ladder_lines(counts))
        self.assertIn("| 6 | 4 | 1 | 2 | 1 | 1 |", text)
        self.assertEqual(SB.public_problems(text), [])
        for name in ("fx-", "sha-", "bundle"):
            self.assertNotIn(name, text)

    def test_the_page_says_whether_the_ladder_binds_or_only_records(self):
        counts = {key: 0 for key in SB.LADDER_COUNTS}
        recording = SB.ladder_lines({"binding": False, **counts})
        binding = SB.ladder_lines({"binding": True, **counts})
        unread = SB.ladder_lines({"binding": "n/a", **counts})
        self.assertTrue(recording[0].startswith("The ladder is RECORDING"))
        self.assertTrue(binding[0].startswith("The ladder BINDS"))
        self.assertEqual(unread[0], "Whether the ladder binds could not be read.")
        self.assertEqual(len({recording[0], binding[0], unread[0]}), 3)
        for lines in (recording, binding, unread):
            self.assertEqual(lines[1:], recording[1:], "the same counts under each")
            self.assertEqual(SB.public_problems("\n".join(lines)), [])
        self.assertEqual(SB.ladder_lines({})[-1], "| n/a | n/a | n/a | n/a | n/a | n/a |")

    def write_economics(self):
        folder = self.root / "economics" / "20261006-close"
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps(self.economics()))

    def test_run_posts_through_the_docs_route_and_keeps_a_local_copy(self):
        self.write_economics()
        gateway = FakeGateway()
        out = SB.run(self.ctx("scoreboard", gateway=gateway, due=at("2026-10-06T23:30:00Z")))
        path, body = gateway.posts[0]
        self.assertEqual((path, body["path"]), ("/v1/github/docs", "docs/runs/desk/2026-10-06.md"))
        self.assertTrue(body["message"].startswith("desk:"))
        self.assertEqual(SB.public_problems(body["content"]), [])
        self.assertEqual(out["posted"], "docs/runs/desk/2026-10-06.md")
        self.assertTrue((self.root / "scoreboard" / "2026-10-06.md").exists())

    def test_without_the_docs_route_the_page_is_kept_and_the_run_is_skipped(self):
        gateway = FakeGateway(post_error=GatewayError("POST /v1/github/docs: HTTP 404", status=404))
        out = SB.run(self.ctx("scoreboard", gateway=gateway, due=at("2026-10-06T23:30:00Z")))
        self.assertEqual(out["status"], "skipped")
        self.assertIn("No close economics yet", (self.root / "scoreboard" / "2026-10-06.md").read_text())

    def test_a_page_that_fails_the_filter_is_never_posted(self):
        (self.root / "budget.json").write_text(json.dumps({"state": "the Sail balance is low"}))
        gateway = FakeGateway()
        with self.assertRaises(ValueError):
            SB.run(self.ctx("scoreboard", gateway=gateway, due=at("2026-10-06T23:30:00Z")))
        self.assertEqual(gateway.posts, [])


def passing_house(now):
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
    return {
        "at": now,
        "errors": {},
        "release": {"current": "/workspace/releases/r1", "running": "r1", "health_age_s": 20, "release": "r1", "real_money": True,
                    "failures": [], "fill_model": {"version": "fm-1", "cells": 40}, "fill_model_file_sha256": "ab" * 32,
                    "live": {"summary": {"state": "idle"}, "blocked": None, "frozen": None, "stops": {}, "instances": 3}},
        "grant": {"latest": "g", "revoked": None, "active": True, "holds": True, "running_money_digest": "d" * 64,
                  "policy": {"capital_usd": "1200", "ceiling_usd": "5500", "constitution_digest": "d" * 64}, "ratifications": 2},
        "money": {"real_types": ["debit_vertical"], "credit_min_equity_usd": "2000",
                  "gateway": {"order_equity_share": "0.25", "order_max_loss_usd": "1000", "day_equity_share": "1"}},
        "gateway": {"kill_switch": False, "max_loss": {"order_equity_share": "0.25", "max_order_max_loss_usd": "1000.00",
                                                       "day_equity_share": "1", "credit_min_equity_usd": "2000.00"},
                    "frontier": {"spent_usd": "0.00", "cap_usd": "0.00"}, "claude": {"spent_usd": "10", "cap_usd": "150"},
                    "sail": {"balance_usd": "300"},
                    "account": {"status": "ACTIVE", "equity": "1200", "options_buying_power": "1100", "options_trading_level": 3},
                    "orders": [], "positions": []},
        "swarm": {"raw_is_object": True, "raw_live": {"observe": True, "observe_max": 24, "calibration": True},
                  "defaults_live": {"observe": True, "observe_max": 48, "calibration": False},
                  "eff_gym": {"enabled": True, "image_checkpoint": "img", "gate_checkpoint": "gate"}, "eff_guard": {"house_burn_usd_day": 1.0},
                  "eff_claude": {"usd_cap": 150}, "floor": 8, "alive": 12, "read_at": now, "heartbeat_age_s": 15,
                  "heartbeat_release": "/workspace/releases/r1", "status": {"spend_last_hour": {"sail_model": 0.1}, "braked": False},
                  "guard": {"balance": 300, "line": 32, "braked": False}},
        "bands": {"observe": 10, "read": [{"family": "f", "band": "probe", "version": 2, "typical_max_loss_usd": 50, "fits_probe": True}],
                  "live_missing_from_read": []},
        "backup": {"latest": {"at": stamp, "age_h": 3.0, "ok": True}},
        "mirror": {"cursor": 100, "events_top_seq": 120, "lag": 20},
    }


class Preopen(Base):
    def test_a_healthy_house_passes_all_nine(self):
        now = at("2026-10-05T12:30:00Z")
        done = PO.checks(passing_house(now), now)
        self.assertEqual([(c.n, c.ok) for c in done], [(n, True) for n in range(1, 10)], [c.headline() for c in done if not c.ok])

    def test_each_fault_fails_its_own_check(self):
        now = at("2026-10-05T12:30:00Z")
        h = passing_house(now)
        h["gateway"]["kill_switch"] = True
        h["swarm"]["heartbeat_age_s"] = 900
        h["backup"]["latest"]["age_h"] = 40
        h["gateway"]["max_loss"]["order_equity_share"] = "0.5"
        h["mirror"]["lag"] = 5000
        failed = {c.name: c.headline() for c in PO.checks(h, now) if not c.ok}
        self.assertEqual(sorted(failed), ["account", "backup", "gateway", "mirror", "swarm"])
        self.assertIn("kill switch true", failed["account"])
        self.assertIn("order_equity_share 0.5", failed["gateway"])

    def test_a_house_that_cannot_be_read_fails_every_check_and_warns_for_each(self):
        self.now = at("2026-10-05T12:30:00Z")
        ctx = self.ctx("preopen", gateway=FakeGateway({"/v1/health": GatewayError("down")}))
        out = PO.run(ctx)
        self.assertEqual((out["passed"], out["of"]), (0, 9))
        self.assertEqual(len(ctx.alerts), 9)
        self.assertTrue(all(a["level"] == "warning" and a["text"].startswith("preopen ") for a in ctx.alerts))

    def test_the_bands_line_says_it_counts_rows_on_offer_and_passes_as_before(self):
        now = at("2026-10-05T12:30:00Z")

        def bands(h):
            return next(c for c in PO.checks(h, now) if c.name == "bands")

        h = passing_house(now)
        c = bands(h)
        self.assertTrue(c.ok)
        self.assertEqual(c.items[0], (True, "observe rows the swarm offers: 10 (a count of rows on offer, not of cohorts the live "
                                            "path has pinned or practises); the live path pins up to 24"))
        h["bands"]["observe"] = 0
        self.assertFalse(bands(h).ok, "observe on and no row on offer")
        h["swarm"]["raw_live"]["observe"] = False
        c = bands(h)
        self.assertEqual((c.ok, c.items[0]), (True, (True, "observe is off for the live path")))


BUDGET_SPENT = "today's Sail research budget is spent (5.00 of 5.00; budget.json)"


class PreopenBrake(Base):
    """Check 5 and a braked Sail guard: THE BUDGET's daily stop alone passes and is said; every other cause, a cause not
    named, a balance not read or not above the line, a reading that is not fresh, FAILS as it always did. A FAIL's line
    is the House's public warning: the guard's reason (the account's numbers, bare) is on a line only the receipt holds."""

    def setUp(self):
        super().setUp()
        self.now = at("2026-10-05T12:30:00Z")

    def braked(self, **over):
        """A passing House whose swarm is braked: the heartbeat's `braked`, and its `guard` as `SailGuard.last` writes it."""
        h = passing_house(self.now)
        h["swarm"]["status"]["braked"] = True
        h["swarm"]["guard"] = {"balance": 300, "line": 32, "braked": True, "reason": BUDGET_SPENT, "causes": ["research_budget"],
                               "at": self.now - 100, **over}
        return h

    def swarm(self, h):
        c = next(c for c in PO.checks(h, self.now) if c.name == "swarm")
        return c.ok, [text for ok, text in c.items if ok is not None][-1]  # the guard's line is the last one judged

    def kept(self, h):
        """The guard's reason on its own line (a FAIL's): never judged, so never a warning's text. None when the judged
        line says it (a pass) or there is none."""
        c = next(c for c in PO.checks(h, self.now) if c.name == "swarm")
        own = [text for ok, text in c.items if ok is None]
        if not own:
            return None
        self.assertEqual((len(own), c.items[-1]), (1, (None, own[0])), "one line, after the guard's")
        return own[0]

    def test_an_unbraked_guard_reads_as_before(self):
        h = passing_house(self.now)
        self.assertEqual(self.swarm(h), (True, "the Sail guard: balance vs line $300.00 / $32.00; braked False"))
        h["swarm"]["guard"]["causes"] = []  # as the guard now writes an unbraked reading
        self.assertEqual(self.swarm(h), (True, "the Sail guard: balance vs line $300.00 / $32.00; braked False"))
        for balance in (32, 31, None):
            h["swarm"]["guard"]["balance"] = balance
            self.assertFalse(self.swarm(h)[0], balance)

    def test_a_brake_by_the_days_budget_alone_passes_and_says_so(self):
        # Research at its cap is the day as designed. Sail's own meter at the account's cap is the budget's stop too, and no
        # ordinary day (the account was billed its research and fixed dollars with the swarm's booked research under its
        # cap): it passes, said as what it is and never as designed.
        meter = "Sail's own meter is at the day's cap for the whole account"
        for causes, said in ((["research_budget"], "the day's research budget alone, as designed"),
                             (["account_budget"], f"the day's account budget alone: {meter}"),
                             (["research_budget", "account_budget"], f"the day's research budget and account budget alone: {meter}")):
            h = self.braked(causes=causes)
            self.assertEqual(self.swarm(h), (True, f"the Sail guard: balance vs line $300.00 / $32.00; braked by {said} "
                                                   f"({BUDGET_SPENT})"), causes)
            self.assertEqual("as designed" in self.swarm(h)[1], causes == ["research_budget"], causes)
            self.assertIsNone(self.kept(h), "a pass says the reason on the guard's own line")
            self.assertEqual([c.ok for c in PO.checks(h, self.now)], [True] * 9)

    def test_the_days_brake_is_no_warning_and_a_real_one_still_is(self):
        from unittest import mock

        for causes, failed in ((["research_budget"], []), (["under_line", "research_budget"], ["5 swarm"])):
            ctx = self.ctx("preopen", gateway=FakeGateway())
            with mock.patch.object(PO, "collect", return_value=self.braked(causes=causes)):
                out = PO.run(ctx)
            self.assertEqual((out["passed"], out["failed"]), (9 - len(failed), failed), causes)
            self.assertEqual([a["text"].split(": ")[0] for a in ctx.alerts], [f"preopen {name} FAIL" for name in failed])

    def test_every_other_cause_fails(self):
        for cause in ("balance_unreadable", "under_line", "budget_unreadable", "disk", "no_reading", "a_cause_not_yet_named"):
            h = self.braked(causes=[cause])
            self.assertEqual(self.swarm(h), (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True, causes "
                                                    + cause), cause)
            self.assertEqual(self.kept(h), f"the guard's reason: {BUDGET_SPENT}", cause)

    def test_a_budget_cause_beside_any_other_fails(self):
        for causes in (["under_line", "research_budget"], ["research_budget", "disk"], ["balance_unreadable", "account_budget"],
                       ["research_budget", "account_budget", "disk"], ["research_budget", "a_cause_not_yet_named"],
                       ["research_budget", "budget_unreadable"], ["budget_unreadable", "account_budget"]):
            ok, line = self.swarm(self.braked(causes=causes))
            self.assertFalse(ok, causes)
            self.assertIn("braked True, causes " + ", ".join(causes), line)

    def test_a_cause_not_named_fails_and_the_reasons_words_are_never_read(self):
        h = self.braked()
        del h["swarm"]["guard"]["causes"]  # a record from before the list was kept: its reason reads like the budget's
        self.assertEqual(self.swarm(h), (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True, cause unknown"))
        self.assertEqual(self.kept(h), f"the guard's reason: {BUDGET_SPENT}")
        for bad in (None, [], "research_budget", ["research_budget", 3], {"research_budget": True}):
            ok, line = self.swarm(self.braked(causes=bad))
            self.assertFalse(ok, bad)
            self.assertIn("cause unknown", line)
        # The names decide: the budget's name passes whatever the words beside it say.
        self.assertTrue(self.swarm(self.braked(reason="the day's stop, in words no reader was written for"))[0])

    def test_a_brake_only_the_swarms_status_says_fails(self):
        # `allows()` is false with no good reading for `stale_seconds` while the guard's own record is not braked.
        for guard in ({"balance": 300, "line": 32, "braked": False, "causes": [], "at": self.now - 100},
                      {"balance": 300, "line": 32, "braked": False, "causes": ["research_budget"], "at": self.now - 100},
                      {"balance": 300, "line": 32, "braked": False}, {}):
            h = self.braked()
            h["swarm"]["guard"] = guard
            ok, line = self.swarm(h)
            self.assertFalse(ok, guard)
            self.assertIn("braked True, cause unknown", line)

    def test_a_budget_brake_still_needs_the_balance_read_and_above_the_line(self):
        self.assertTrue(self.swarm(self.braked(balance=32.01))[0])
        for over in ({"balance": None}, {"balance": 32}, {"balance": 31.99}, {"balance": 0}, {"line": None}):
            ok, line = self.swarm(self.braked(**over))
            self.assertFalse(ok, over)
            self.assertIn("braked True by the day's research budget, and no balance read above the line", line)

    def test_a_budget_brake_needs_a_fresh_reading_by_the_guards_own_stale_seconds(self):
        self.assertTrue(self.swarm(self.braked(at=self.now - 599))[0])
        for stamp, said in ((self.now - 600, "on a reading 10m old"), (self.now - 9 * 3600, "on a reading 9.0h old"),
                            (self.now + 30, "on a reading -30s old"), (None, "on a reading ? old")):
            ok, line = self.swarm(self.braked(at=stamp))
            self.assertFalse(ok, stamp)
            self.assertIn(f"braked True by the day's research budget, {said} (no fresh reading of the balance)", line)
        h = self.braked()
        del h["swarm"]["read_at"]  # the time of the heartbeat's read unknown: nothing is fresh (the job's `now` is not it)
        self.assertEqual(self.swarm(h), (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True by the day's research "
                                                "budget, on a reading ? old (no fresh reading of the balance)"))
        h = self.braked(at=self.now - 200)
        h["swarm"]["eff_guard"]["stale_seconds"] = 120
        self.assertFalse(self.swarm(h)[0], "the guard's own setting")

    def test_a_fails_public_warning_never_carries_the_guards_reason(self):
        """`ops.alert` is public and the runner's scrub replaces only what carries a `$`: the guard's reason holds the Sail
        balance, the line and the day's dollars bare."""
        import re
        from unittest import mock

        from league.ops.runner import public_text

        under = "the Sail balance 31.00 is under the House's line 37.00 (2 x 1.00 a day + 30)"
        unread = "today's Sail research budget is spent (0.00 of 0.00; unavailable)"
        cases = (({"balance": 31.0, "causes": ["under_line"], "reason": under}, "braked True, causes under_line"),
                 ({"causes": ["under_line", "research_budget"], "reason": under + "; " + BUDGET_SPENT},
                  "braked True, causes under_line, research_budget"),
                 ({"causes": ["budget_unreadable"], "reason": unread}, "braked True, causes budget_unreadable"),
                 ({"causes": None}, "braked True, cause unknown"),
                 ({"balance": 31.0}, "braked True by the day's research budget, and no balance read above the line"),
                 ({"at": self.now - 9 * 3600}, "braked True by the day's research budget, on a reading 9.0h old (no fresh "
                                               "reading of the balance)"))
        for over, said in cases:
            h = self.braked(**over)
            reason = h["swarm"]["guard"]["reason"]
            ctx = self.ctx("preopen", gateway=FakeGateway())
            with mock.patch.object(PO, "collect", return_value=h):
                out = PO.run(ctx)
            self.assertEqual(out["failed"], ["5 swarm"], over)
            self.assertEqual(len(ctx.alerts), 1, over)
            public = public_text(ctx.alerts[0]["text"])  # as the runner hands it to the House's alert
            self.assertEqual(public, f"preopen 5 swarm FAIL: the Sail guard: balance vs line $<amount> / $<amount>; {said}", over)
            self.assertNotIn(reason, ctx.alerts[0]["text"], over)
            figures = set(re.findall(r"\d+(?:\.\d+)?", reason))
            self.assertTrue(figures, over)
            self.assertFalse(figures & set(re.findall(r"\d+(?:\.\d+)?", public)), over)
            row = next(c for c in out["checks"] if c["name"] == "swarm")
            self.assertEqual(row["headline"], ctx.alerts[0]["text"].split("FAIL: ", 1)[1], over)
            self.assertEqual(row["items"][-1], {"ok": None, "text": f"the guard's reason: {reason}"}, "the receipt keeps it")

    def test_a_budget_rule_that_could_not_be_read_fails_through_the_guards_own_reading(self):
        """The guard FAILS CLOSED to no research when the rule could not run, its block is malformed or it cannot be read:
        the same arithmetic as the day's cap, on a healthy balance, and never the designed stop."""
        import contextlib
        import copy
        from unittest import mock

        from league.ops import budget as B
        from league.swarm import settings as SS
        from league.swarm.guard import SailGuard
        from league.swarm.store import SwarmStore

        store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(store.close)

        def check(settings, patch=None):
            self.now += 180
            g = SailGuard(store, settings, lambda: (300.0, 1.0), clock=lambda: self.now, disk_free=lambda: 100.0 * 2 ** 30)
            with patch or contextlib.nullcontext():
                g.check()
            h = passing_house(self.now)
            h["swarm"].update(eff_guard=settings["guard"], guard=json.loads(json.dumps(g.last)))  # the heartbeat is JSON
            h["swarm"]["status"]["braked"] = not g.allows()
            return self.swarm(h), self.kept(h)

        failed = (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True, causes budget_unreadable")
        with mock.patch.object(B, "overlay", side_effect=RuntimeError("boom")):
            could_not_run = SS.load(self.root, config={})  # the block `settings.load` writes when the rule cannot run
        self.assertEqual(check(could_not_run), (failed, "the guard's reason: today's Sail research budget is spent (0.00 of 0.00; "
                                                        "unavailable)"))
        malformed = copy.deepcopy(SS.DEFAULTS)
        malformed["budget"] = {"source": "budget.json", "sail_usd_day": "lots"}
        self.assertEqual(check(malformed), (failed, "the guard's reason: today's Sail research budget is spent (0.00 of 0.00; "
                                                    "malformed budget block: no research)"))
        good = copy.deepcopy(SS.DEFAULTS)
        good["budget"] = {"source": "budget.json", "sail_usd_day": 5.0, "claude_usd_day": 0.0, "fixed_sail_usd_day": None}
        self.assertEqual(check(good, mock.patch.object(B, "sail_caps", side_effect=RuntimeError("boom"))),
                         (failed, "the guard's reason: today's Sail research budget is spent (0.00 of 0.00; the budget rule could "
                                  "not be read (RuntimeError))"))
        self.assertEqual(check(good), ((True, "the Sail guard: balance vs line $300.00 / $32.00; braked False"), None))
        # A budget of zero the rule itself gives is the budget's own: the day as designed, said with its dollars.
        zero = copy.deepcopy(good)
        zero["budget"]["sail_usd_day"] = 0.0
        self.assertEqual(check(zero), ((True, "the Sail guard: balance vs line $300.00 / $32.00; braked by the day's research budget "
                                              "alone, as designed (today's Sail research budget is spent (0.00 of 0.00; budget.json))"),
                                       None))

    def test_the_guards_own_reading_is_what_the_check_reads(self):
        import copy

        from league.swarm import settings as SS
        from league.swarm.guard import SailGuard
        from league.swarm.store import SwarmStore

        store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(store.close)
        settings = copy.deepcopy(SS.DEFAULTS)
        settings["budget"] = {"source": "budget.json", "sail_usd_day": 5.0, "claude_usd_day": 0.0, "fixed_sail_usd_day": None}
        reading, free = [(300.0, 1.0)], [100.0]
        g = SailGuard(store, settings, lambda: reading[0], clock=lambda: self.now, disk_free=lambda: free[0] * 2 ** 30)

        def check():
            self.now += 180
            g.check()
            h = passing_house(self.now)
            h["swarm"].update(eff_guard=settings["guard"], guard=json.loads(json.dumps(g.last)))  # the heartbeat is JSON
            h["swarm"]["status"]["braked"] = not g.allows()
            return self.swarm(h)

        self.assertEqual(check(), (True, "the Sail guard: balance vs line $300.00 / $32.00; braked False"))
        store.add_spend("sail_model", 5.0)
        ok, line = check()
        self.assertTrue(ok, line)
        self.assertIn("braked by the day's research budget alone, as designed (today's Sail research budget is spent (5.00 of 5.00", line)
        reading[0] = (35.0, 1.0)  # over the $32 line, under the $37 a braked guard releases at: the guard names the line too
        self.assertEqual(check()[0], False)
        reading[0] = (None, None)
        self.assertEqual(check()[0], False)
        reading[0] = (300.0, 1.0)
        self.assertEqual(check()[0], True)
        free[0] = 2.0
        self.assertEqual(check()[0], False)
        free[0] = 100.0
        self.assertEqual(check()[0], True)
        self.now += 601  # the guard stops checking: its last reading goes stale while the heartbeat still carries it
        h = passing_house(self.now)
        h["swarm"].update(eff_guard=settings["guard"], guard=json.loads(json.dumps(g.last)))
        h["swarm"]["status"]["braked"] = not g.allows()
        self.assertEqual(self.swarm(h)[0], False)

    def on_disk(self):
        """A state root as the swarm leaves it, for `collect` itself: swarm.json, the swarm's store, health.json and a real
        guard on the settings the root loads (no budget.json: the floor). Returns (the guard, the store, `beat`), where
        `beat()` writes the heartbeat as `league/swarm/loop.py` does, the guard's `last` under `status.guard`."""
        from league.swarm import settings as SS
        from league.swarm.guard import SailGuard
        from league.swarm.store import SwarmStore

        (self.root / "swarm.json").write_text(json.dumps({
            "live": {"observe": True, "observe_max": 24, "calibration": False}, "population": {"floor": 0},
            "gym": {"enabled": True, "image_checkpoint": "img", "gate_checkpoint": "gate"}}))
        (self.root / "health.json").write_text(json.dumps({"at": datetime.fromtimestamp(self.now, timezone.utc).isoformat()}))
        store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(store.close)
        reading = [(300.0, 1.0)]
        g = SailGuard(store, SS.load(self.root, config={}), lambda: reading[0], clock=lambda: self.now,
                      disk_free=lambda: 100.0 * 2 ** 30)

        def beat():
            (self.root / "swarm.heartbeat").write_text(json.dumps({
                "pid": 1, "at": self.now, "release": os.path.realpath(self.base / "current"),
                "status": {"spend_last_hour": {}, "guard": g.last, "braked": not g.allows()}}))

        return g, store, reading, beat

    def collected(self, **kw):
        """Check 5 on what `collect` reads from the root: (ok, the guard's line)."""
        h = PO.collect(self.root, self.base, self.base / "releases" / "r1", FakeGateway(), now=self.now, config={}, **kw)
        self.assertNotIn("swarm", h["errors"])
        c = PO.check_swarm(h)
        return c.ok, [text for ok, text in c.items if ok is not None][-1]

    def test_through_collect_a_real_guards_heartbeat_passes_on_the_days_brake_alone_and_fails_once_stale(self):
        g, store, reading, beat = self.on_disk()
        g.check()
        beat()
        self.assertEqual(self.collected(), (True, "the Sail guard: balance vs line $300.00 / $32.00; braked False"))
        store.add_spend("sail_model", 3.0)  # the floor's Sail research dollars a day
        self.now += 180
        self.assertEqual(g.check()["causes"], ["research_budget"])
        beat()
        self.assertEqual(self.collected(), (True, "the Sail guard: balance vs line $300.00 / $32.00; braked by the day's research "
                                                  "budget alone, as designed (today's Sail research budget is spent (3.00 of 3.00; "
                                                  "floor))"))
        # The swarm goes on beating while its guard stops checking: the heartbeat is fresh, the reading in it is not.
        self.now += 599
        beat()
        self.assertTrue(self.collected()[0])
        self.now += 1
        beat()
        self.assertEqual(self.collected(), (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True by the day's "
                                                   "research budget, on a reading 10m old (no fresh reading of the balance)"))
        # A cause that is not the budget's, read the same way.
        reading[0] = (None, None)
        self.assertEqual(g.check()["causes"], ["balance_unreadable", "research_budget"])
        beat()
        self.assertEqual(self.collected(), (False, "the Sail guard: balance vs line ? / $32.00; braked True, causes "
                                                   "balance_unreadable, research_budget"))

    def test_through_collect_sails_own_meter_at_the_accounts_cap_passes_and_is_never_said_as_designed(self):
        g, store, reading, beat = self.on_disk()
        g.check()
        reading[0] = (296.0, 1.0)  # the account billed the day's research and fixed dollars; the swarm booked none of it
        self.now += 180
        self.assertEqual(g.check()["causes"], ["account_budget"])
        beat()
        ok, line = self.collected()
        self.assertTrue(ok, line)
        self.assertIn("braked by the day's account budget alone: Sail's own meter is at the day's cap for the whole account "
                      "(today's Sail budget is spent by Sail's meter (4.00 of 4.00 for the account", line)
        self.assertNotIn("as designed", line)

    def test_a_guard_check_between_the_jobs_now_and_the_heartbeats_read_is_a_fresh_reading(self):
        """The job reads its clock, then the gateway (four GETs), then the heartbeat: a guard check and a heartbeat written
        in between are stamped after the job's `now`. They are aged on the clock as read once the heartbeat was."""
        g, store, reading, beat = self.on_disk()
        store.add_spend("sail_model", 3.0)
        started = self.now
        self.now = started + 3
        self.assertEqual(g.check()["causes"], ["research_budget"])
        self.now = started + 4
        beat()
        ticks = iter([started])  # the job's `now`; every later read is after the gateway's GETs
        ctx = Context("preopen", root=self.root, base=self.base, release=self.base / "releases" / "r1", due_at=started, config={},
                      clock=lambda: next(ticks, started + 5), gateway=FakeGateway(), settings_value={})
        out = PO.run(ctx)
        self.assertEqual(out["at"], "2026-10-05T12:30:00Z")
        row = next(c for c in out["checks"] if c["name"] == "swarm")
        self.assertTrue(row["ok"], row)
        self.assertIn({"ok": True, "text": "heartbeat 1s old"}, row["items"])
        self.assertIn("braked by the day's research budget alone, as designed", row["items"][-1]["text"])
        self.assertNotIn("5 swarm", out["failed"])
        # A reading stamped after the heartbeat's read is still no reading, near or far.
        self.now = started + 5
        for ahead, said in ((1, "-1s"), (30, "-30s"), (86400, "-86400s")):
            body = json.loads((self.root / "swarm.heartbeat").read_text())
            body["status"]["guard"]["at"] = started + 5 + ahead
            (self.root / "swarm.heartbeat").write_text(json.dumps(body))
            self.assertEqual(self.collected(clock=lambda: started + 5),
                             (False, "the Sail guard: balance vs line $300.00 / $32.00; braked True by the day's research budget, "
                                     f"on a reading {said} old (no fresh reading of the balance)"), ahead)
        # With no clock handed in, the job's `now` is the only read there is: the same reading is after it, and fails.
        beat()
        self.assertTrue(self.collected(clock=lambda: started + 5)[0])
        self.now = started
        self.assertFalse(self.collected()[0])


class Receipts(Base):
    def test_the_days_receipts_carry_jobs_health_deploys_spend_and_budget(self):
        store = OpsStore(self.root)
        store.record("hygiene", "2026-10-06T02:00:00Z", "skipped", "2026-10-06T02:00:05Z", summary={"why": "x"})
        store.record("clock", "2026-10-05T11:00:00Z", "missed", "2026-10-05T13:00:00Z")
        store.close()
        (self.root / "health.json").write_text(json.dumps({"at": "2026-10-06T02:00:00Z", "release": "r1", "ops": {"late": []},
                                                           "options_live": {"summary": {"state": "idle"}, "instances": {"a": {}}},
                                                           "agents_table": ["big"]}))
        (self.base / "deploys.jsonl").write_text(json.dumps({"at": "2026-10-06T01:00:00.000Z", "stage": "verdict"}) + "\n"
                                                 + json.dumps({"at": "2026-10-05T01:00:00.000Z", "stage": "verdict"}) + "\n")
        (self.root / "budget.json").write_text(json.dumps({"direction": "same"}))
        db = sqlite3.connect(self.root / "swarm.sqlite")
        db.execute("CREATE TABLE spend (seq INTEGER, epoch REAL, kind TEXT, usd REAL, detail TEXT)")
        db.execute("INSERT INTO spend VALUES (1, ?, 'sail_model', 0.25, NULL)", (self.now - 60,))
        db.execute("INSERT INTO spend VALUES (2, ?, 'sail_model', 9.0, NULL)", (self.now - 86400,))
        db.commit()
        db.close()
        path = R.write(self.root, self.base, self.now)
        value = json.loads(Path(path).read_text())
        self.assertEqual(Path(path).name, "2026-10-06.json")
        self.assertEqual([(j["job"], j["status"]) for j in value["jobs"]], [("hygiene", "skipped")])
        self.assertEqual(value["jobs"][0]["summary"], {"why": "x"})
        self.assertEqual(len(value["deploys"]), 1)
        self.assertEqual(value["spend"], {"sail_model": {"n": 1, "usd": 0.25}})
        self.assertEqual(value["budget"], {"direction": "same"})
        self.assertEqual(value["health"]["options_live"]["instances"], 1)
        self.assertNotIn("agents_table", value["health"])
        self.assertEqual(json.loads((self.root / "receipts" / "latest.json").read_text()), value)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class Wiring(unittest.TestCase):
    def test_the_house_step_calls_the_runner_and_a_failure_is_a_warning(self):
        from league.house import House

        alerts, ticks = [], []
        fake = SimpleNamespace(ops=SimpleNamespace(tick=lambda house: ticks.append(house), health=lambda: {"late": []}),
                               alert=lambda level, text, **k: alerts.append((level, text)))
        House._ops_step(fake)
        self.assertEqual(ticks, [fake])
        self.assertEqual(House._ops_health(fake), {"late": []})

        def broken(house):
            raise RuntimeError("store locked")

        fake.ops.tick = broken
        House._ops_step(fake)
        self.assertEqual(alerts, [("warning", "the House's jobs step failed (RuntimeError: store locked)")])
        fake.ops = None
        House._ops_step(fake)
        self.assertIsNone(House._ops_health(fake))

    def test_attach_gives_the_house_a_runner_on_its_clock(self):
        from league.ops import attach, health, tick

        with tempfile.TemporaryDirectory() as tmp:
            house = SimpleNamespace(clock=lambda: at("2026-10-05T01:00:00Z"), alert=lambda *a, **k: None)
            runner = attach(house, Path(tmp) / "state", base=Path(tmp))
            self.assertIs(house.ops, runner)
            self.assertEqual(health(house)["day"], "2026-10-05")  # read only: a tick here could start a real job child
            runner.store.close()
        self.assertIsNone(tick(SimpleNamespace(ops=None)))


    def test_a_runner_that_cannot_be_built_is_a_warning_never_a_house_that_does_not_start(self):
        from unittest import mock

        from league import ops

        alerts = []
        house = SimpleNamespace(clock=lambda: at("2026-10-05T01:00:00Z"), alert=lambda level, text, **k: alerts.append((level, text)))
        with tempfile.TemporaryDirectory() as tmp, mock.patch("league.ops.runner.OpsStore", side_effect=OSError("read-only file system")):
            self.assertIsNone(ops.start(house, Path(tmp) / "state", base=Path(tmp)))
        self.assertIsNone(house.ops)
        self.assertEqual(alerts[0][0], "warning")
        self.assertIn("the House's jobs are off this run: the runner could not start (OSError: read-only file system)", alerts[0][1])

    def test_only_the_houses_own_loop_builds_the_job_runner(self):
        """A `status`, `verify` or `tick` beside the running House never builds a runner: its start would kill the
        House's job child as an orphan."""
        from unittest import mock

        import league.__main__ as M

        for command, jobs in (("verify", False), ("status", False), ("tick", False), ("run", True)):
            house = mock.MagicMock()
            house.ledger.verify.return_value, house.books, house.tick.return_value = 0, {}, {}
            built = mock.MagicMock(return_value=house) if command != "run" else mock.MagicMock(side_effect=RuntimeError("built"))
            with tempfile.TemporaryDirectory() as tmp, mock.patch.object(M, "build", built), \
                    mock.patch.object(M, "load_config", return_value={}), mock.patch.object(M, "table", return_value={}), \
                    mock.patch("builtins.print"):
                if command == "run":
                    with self.assertRaises(RuntimeError):
                        M.main([command, "--root", tmp])
                else:
                    M.main([command, "--root", tmp])
            self.assertIs(built.call_args.kwargs["jobs"], jobs, command)

    def test_the_house_box_is_the_configs_pin_before_the_environment(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SAILBOX_ID": "sb_aaaaaaaa-0000"}):
            pinned = Context("economics", root=Path(tmp), due_at=0.0, settings_value={},
                             config={"backup": {"box_id": "sb_bbbbbbbb-1111", "box_name": "house"}})
            self.assertEqual(pinned.house_box(), "sb_bbbbbbbb-1111")
            self.assertEqual(Context("economics", root=Path(tmp), due_at=0.0, settings_value={}, config={}).house_box(),
                             "sb_aaaaaaaa-0000")


class DeskReceipts(unittest.TestCase):
    def test_the_laptop_reads_one_file_through_the_files_api_and_summarizes_it(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("desk_receipts", Path(__file__).resolve().parents[2] / "scripts" / "desk_receipts.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        receipts = {"day": "2026-10-06", "written_at": "2026-10-06T02:10:00Z", "jobs_by_status": {"ok": 1},
                    "jobs": [{"due_at": "2026-10-06T02:00:00Z", "job": "hygiene", "status": "ok", "summary": {"pool": {"x": 1}}}],
                    "health": {"at": "t", "release": "r1", "ops": {"running": None}}, "deploys": [], "spend": {"sail_model": {"usd": 0.25}}}
        calls = []

        class Client:
            def download(self, box, path, timeout=None):
                calls.append((box, path))
                return json.dumps(receipts).encode()

        got = module.fetch(Client(), "sb_12345678", "2026-10-06")
        self.assertEqual(calls, [("sb_12345678", "/workspace/state/receipts/2026-10-06.json")])
        text = module.summary(got)
        self.assertIn("hygiene", text)
        self.assertIn("sail_model $0.25", text)
        with self.assertRaises(SystemExit):
            module.fetch(Client(), "sb_12345678", "../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
