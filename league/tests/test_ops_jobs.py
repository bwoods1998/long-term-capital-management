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
        settings["population"]["floor"] = 100
        self.now += 3600
        self.assertEqual(HY.retire_idle(self.ctx("hygiene"), store=self.store, settings=settings)["retired"], [])

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
                        ladder={"entrants": "n/a", "in_practice": 12, "promoted": "n/a", "bh_family_size": "n/a"},
                        jobs={"ok": 5, "missed": 1}, written_at="23:30Z")
        self.assertEqual(SB.public_problems(text), [])
        self.assertIn("**Net (realized - costs)** | **-165.66**", text)
        self.assertIn("| Realized options P&L, trailing 30 days | 4.67 |", text)
        self.assertIn("| sail | 3.00 | 2027-01-04 |", text)
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

    def test_ladder_counts_are_na_until_the_ladder_tables_exist(self):
        self.assertEqual(SB.ladder_counts(self.root, self.now)["entrants"], "n/a")
        db = sqlite3.connect(self.root / "observe.sqlite")
        db.execute("CREATE TABLE cohorts (family TEXT, version INTEGER, status TEXT)")
        db.execute("INSERT INTO cohorts VALUES ('a', 1, 'active'), ('b', 1, 'failed')")
        db.execute("CREATE TABLE entrants (family TEXT, entered_at REAL)")
        db.executemany("INSERT INTO entrants VALUES (?, ?)", [("a", self.now - 86400), ("b", self.now - 200 * 86400)])
        db.execute("CREATE TABLE ladder_decisions (family TEXT, verdict TEXT)")
        db.execute("INSERT INTO ladder_decisions VALUES ('a', 'hold'), ('a', 'promote')")
        db.commit()
        db.close()
        self.assertEqual(SB.ladder_counts(self.root, self.now),
                         {"entrants": 2, "in_practice": 1, "promoted": 1, "bh_family_size": 1})

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
                  "eff_claude": {"usd_cap": 150}, "floor": 8, "alive": 12, "heartbeat_age_s": 15,
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
