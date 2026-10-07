"""The self-running release, build A (the owner's goal of Oct 7, 2026, items 3 and 6): the stall alarm (`league/ops/stall.py`)
names each cause from the House's own records, tells the owner through the gateway at most once a cause every 12 hours
and never acts; the funnel (`league/ops/funnel.py`) counts what the swarm did in a window, and the daily page carries it."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from league.ops import funnel as FN
from league.ops import scoreboard as SB
from league.ops import stall as ST
from league.ops.__main__ import run_job
from league.ops.context import Context
from league.ops.registry import by_name
from league.swarm.store import SwarmStore
from league.tests.test_swarm_store import SPEC

HOUR = 3600.0


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


NOW = at("2026-10-07T10:20:00Z")


class Notify:
    """The gateway's /v1/notify as the House sees it: each call recorded, the answer scripted."""

    def __init__(self, answer=None):
        self.answer = answer if answer is not None else {"sent": True}
        self.calls = []

    def __call__(self, facts):
        self.calls.append(json.loads(json.dumps(facts)))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def causes(self):
        return [c["cause"] for c in self.calls]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.t = NOW - 48 * HOUR
        self.store = SwarmStore(self.root, clock=lambda: self.t)
        self.addCleanup(self.store.close)
        self.notify = Notify()

    def ago(self, hours):
        """Move the store's clock to `hours` before NOW (what it writes next is dated so)."""
        self.t = NOW - hours * HOUR

    def family(self, fid, **fields):
        fam = self.store.add_family({**SPEC, "id": fid}, origin="seed")
        if fields:
            self.store.update_family(fam["id"], **fields)
        return fam["id"]

    def runs(self, n, *, window="train", status="ok", fid="busy", hours=1.0):
        if self.store.family(fid) is None:
            self.family(fid)
        self.ago(hours)
        for i in range(n):
            self.store.add_run(fid, 1, {"run_id": f"{fid}-{window}-{status}-{hours}-{i}", "status": status, "trials": 1},
                               window=window, stress=1.0, purpose=window, prune=False)

    def healthy(self, *, birth_hours=1.0, train_runs=10, validation_hours=2.0):
        """A store where nothing stalls: a birth an hour ago, ten Gym runs, a Validation run, a clear guard."""
        self.ago(30)
        self.store.event("swarm.guard", None, {"action": "release", "causes": []})
        self.ago(birth_hours)
        fid = self.family("fresh")
        self.store.event("swarm.born", fid, {"origin": "architect"})
        self.runs(train_runs, hours=1)
        self.runs(1, window="validation", hours=validation_hours)

    def ctx(self, *, now=NOW, ceiling=20):
        ctx = Context("stall", root=self.root, base=self.base, due_at=now, config={}, clock=lambda: now, settings_value={})
        ctx.notify = self.notify
        ctx.population_ceiling = ceiling
        return ctx

    def run_at(self, now=NOW, **kw):
        ctx = self.ctx(now=now, **kw)
        return ST.run(ctx), ctx

    def check(self, cause, **kw):
        out, _ = self.run_at(**kw)
        return out["checks"][cause]


class Causes(Base):
    def test_a_healthy_floor_raises_nothing_and_mails_nothing(self):
        self.healthy()
        out, ctx = self.run_at()
        self.assertEqual(out["stalled"], [])
        self.assertEqual((self.notify.calls, ctx.alerts), ([], []))
        self.assertFalse(out["warning"])

    def test_births_no_birth_in_12_hours_under_the_ceiling(self):
        self.healthy(birth_hours=13)
        births = self.check("births", ceiling=20)
        self.assertTrue(births["stalled"])
        self.assertEqual(births["numbers"]["births_12h"], 0)
        self.assertEqual((births["numbers"]["population"], births["numbers"]["ceiling"]), (2, 20))  # fresh, busy
        self.assertIsNone(births["owner_step"])
        # At the ceiling, no birth is owed; an unknown ceiling raises nothing.
        self.assertFalse(self.check("births", ceiling=2)["stalled"])
        unknown = ST.checks({"alive": 2, "births": 0}, now=NOW, ceiling=None, budget=None, deploy=None, heartbeat=None)
        self.assertFalse(unknown["births"]["stalled"])

    def test_births_a_birth_inside_12_hours_is_no_stall_and_how_long_runs_from_the_last_birth(self):
        self.healthy(birth_hours=11.9)
        self.assertFalse(self.check("births")["stalled"])
        self.assertEqual(self.notify.calls, [])
        out, _ = self.run_at(now=NOW + 14.1 * HOUR)
        self.assertIn("births", out["stalled"])
        facts = next(c for c in self.notify.calls if c["cause"] == "births")
        self.assertEqual((facts["since"], facts["hours"]), ("2026-10-06T22:26:00Z", "26.0"))

    def test_births_the_architects_passes_are_what_the_house_is_doing(self):
        self.ago(5)
        self.store.event("swarm.architect", None, {"born": [], "skipped": "no_cell", "why": "x"})
        self.store.event("swarm.architect", None, {"born": [], "skipped": "ceiling", "why": "x"})
        self.store.event("swarm.architect", None, {"born": [], "error": "Claude said no"})
        self.store.event("swarm.architect", None, {"born": [], "proposed": 4, "route": "claude"})
        self.assertTrue(self.check("births")["stalled"])
        doing = next(c for c in self.notify.calls if c["cause"] == "births")["doing"]
        self.assertIn("The architect passed 4 times in the last 12 h: 1 found no cell a birth may land in, 1 met the ceiling, "
                      "1 failed, 1 asked a model and proposed 4 families (0 born)", doing)

    def test_gym_runs_fewer_than_ten_evaluated_in_six_hours(self):
        self.healthy(train_runs=8)  # eight Train runs and the Validation run: nine
        runs = self.check("gym_runs")
        self.assertTrue(runs["stalled"])
        self.assertEqual(runs["numbers"]["gym_runs_6h"], 9)
        self.assertIn("The Gym evaluated 9 programs in the last 6 h (fewer than 10).", runs["what"])
        self.runs(1, window="probe", hours=0.2)
        self.assertFalse(self.check("gym_runs")["stalled"])

    def test_gym_runs_counts_evaluations_only_and_only_the_last_six_hours(self):
        self.healthy(train_runs=9, validation_hours=7)
        self.runs(5, status="refused", hours=1)
        self.runs(3, status="error", hours=1)
        self.runs(20, hours=7)  # outside the window
        runs = self.check("gym_runs")
        self.assertTrue(runs["stalled"])
        self.assertEqual((runs["numbers"]["gym_runs_6h"], runs["numbers"]["refused_or_failed_6h"]), (9, 8))
        self.runs(1, window="forward", hours=0.5)
        self.assertFalse(self.check("gym_runs")["stalled"])

    def test_validations_none_in_24_hours_while_a_train_best_waits(self):
        self.healthy(validation_hours=23.9)
        self.family("waiting", best_version=2, best_train=1.2)
        self.assertFalse(self.check("validations")["stalled"])  # a Validation run 23.9 h ago
        validations = self.check("validations", now=NOW + 1.3 * HOUR)
        self.assertTrue(validations["stalled"])
        self.assertEqual((validations["numbers"]["awaiting_validation"], validations["numbers"]["last_validation_at"]),
                         (1, "2026-10-06T10:26:00Z"))
        # Every best validated: no Validation is owed, so none in 24 h is no stall.
        self.store.update_family("waiting", validated_version=2)
        self.assertFalse(self.check("validations", now=NOW + 1.3 * HOUR)["stalled"])

    def test_validations_the_last_tournament_round_is_what_the_house_is_doing(self):
        self.family("waiting", best_version=1, best_train=0.5)
        self.ago(1)
        self.store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {}, "errors": {},
                                                                    "waiting_robustness": ["waiting"], "waiting_drift": []}})
        out, _ = self.run_at()
        self.assertIn("validations", out["stalled"])
        doing = next(c for c in self.notify.calls if c["cause"] == "validations")["doing"]
        self.assertIn("queued 0 and judged 0; 1 wait on their 1.5x robustness run, 0 on the drift screen, 0 failed", doing)

    def test_braked_twelve_of_the_last_24_hours(self):
        self.healthy()
        self.ago(13)
        self.store.event("swarm.guard", None, {"action": "brake", "causes": ["research_budget"]})
        braked = self.check("braked")
        self.assertTrue(braked["stalled"])
        self.assertEqual(braked["numbers"]["braked_hours_24h"], 13.0)
        self.assertEqual(braked["numbers"]["braked_hours_research_budget"], 13.0)
        self.assertIsNone(braked["owner_step"])  # the budget's own daily stop: nothing the owner must do

    def test_braked_eleven_hours_is_no_stall_and_a_brake_released_inside_the_window_counts_its_part(self):
        self.healthy()
        self.ago(11)
        self.store.event("swarm.guard", None, {"action": "brake", "causes": ["research_budget"]})
        self.assertFalse(self.check("braked")["stalled"])
        # A brake from 30 h ago released 10 h ago: 14 of the last 24 hours, under the line, and the owner step is a top-up.
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        store = SwarmStore(Path(self.tmp2.name), clock=lambda: self.t)
        self.addCleanup(store.close)
        self.ago(30)
        store.event("swarm.guard", None, {"action": "brake", "causes": ["under_line"]})
        self.ago(20)
        store.event("swarm.guard", None, {"action": "research_hold"})
        self.ago(10)
        store.event("swarm.guard", None, {"action": "release", "causes": []})
        from league.ops import guard

        hours = guard.read(Path(self.tmp2.name) / "swarm.sqlite", lambda db: FN.guard_hours(db, NOW - 24 * HOUR, NOW))
        self.assertEqual((hours["hours"], hours["by_cause"], hours["braked_now"]), (14.0, {"under_line": 14.0}, False))
        self.assertTrue(hours["known"])

    def test_braked_under_the_line_names_the_top_up(self):
        self.healthy()
        self.ago(20)
        self.store.event("swarm.guard", None, {"action": "brake", "causes": ["under_line"]})
        self.store.put("guard", {"braked": True, "causes": ["under_line"]})
        out, _ = self.run_at()
        self.assertIn("top up Sail", out["checks"]["braked"]["owner_step"])
        # A stall the brake causes names the same step: only the owner can lift it.
        self.runs(5, status="refused", hours=0.5)
        db = sqlite3.connect(self.root / "swarm.sqlite")
        db.execute("DELETE FROM runs WHERE status='ok'")
        db.commit()
        db.close()
        out, _ = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertIn("gym_runs", out["stalled"])
        self.assertIn("top up Sail", out["checks"]["gym_runs"]["owner_step"])
        self.assertIn("the Sail guard is braked (under_line)", next(c for c in self.notify.calls if c["cause"] == "gym_runs")["doing"])

    def budget(self, sail_days, *, at_=NOW - HOUR):
        meters = {"sail": {"card_runway_days": sail_days, "runway_days": 5.0, "research_usd_day": 9.6, "ceiling_usd_day": 15.0,
                           "topup_usd": 112.0, "card_date": "2026-10-05"},
                  "claude": {"card_runway_days": 20.0, "runway_days": 20.0, "research_usd_day": 10.0, "ceiling_usd_day": 10.0,
                             "topup_usd": 0.0, "card_date": None}}
        (self.root / "budget.json").write_text(json.dumps({"at": at_, "meters": meters}))

    def test_runway_under_three_days_at_the_ceiling_is_an_owner_step_with_the_budgets_amount(self):
        self.healthy()
        self.budget(2.4)
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["runway_sail"])
        step = out["checks"]["runway_sail"]["owner_step"]
        self.assertEqual(step, "top up Sail: about $112.00 buys 7 more days of research at the ceiling (the taper starts 2026-10-05)")
        facts = self.notify.calls[0]
        self.assertEqual((facts["cause"], facts["owner_step"], facts["numbers"]["runway_days_at_ceiling"]), ("runway_sail", step, 2.4))
        self.assertFalse(out["checks"]["runway_claude"]["stalled"])

    def test_runway_three_days_is_no_stall_and_a_stale_budget_is_not_read(self):
        self.healthy()
        self.budget(3.0)
        self.assertFalse(self.check("runway_sail")["stalled"])
        self.budget(1.0, at_=NOW - 40 * HOUR)
        out, _ = self.run_at()
        self.assertFalse(out["checks"]["runway_sail"]["stalled"])
        self.assertIn("budget.json is stale or undated: the runway is not read", out["errors"])

    def deploys(self, *rows):
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_owner_deploy_main_refused_as_the_owners_deploy_since_the_last_promotion(self):
        self.healthy()
        owner = "league/ops/stall.py: the release's judges and money rules do not change by an automatic update; this one is the owner's deploy (scripts/floor_box.py deploy)"
        self.deploys({"at": "2026-10-06T20:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r1"},
                     {"at": "2026-10-06T21:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "a" * 40, "reasons": [owner]},
                     {"at": "2026-10-07T01:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "b" * 40,
                      "reasons": [owner, ".github/workflows differ from the ones this release trusts (sha256 x, trusted y): the "
                                         "workflows decide what a passing check means, so a change to them is the owner's deploy"]})
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["owner_deploy"])
        check = out["checks"]["owner_deploy"]
        self.assertEqual(check["numbers"]["sha"], "b" * 12)
        self.assertIn("deploy main at bbbbbbbbbbbb yourself (scripts/floor_box.py deploy): it changes league/ops/stall.py, "
                      ".github/workflows", check["owner_step"])
        self.assertEqual(self.notify.calls[0]["since"], "2026-10-06T21:00:00Z")
        # The owner deployed: a promotion after the refusals clears it. A refusal for another reason is no owner step.
        self.deploys({"at": "2026-10-06T21:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "a" * 40, "reasons": [owner]},
                     {"at": "2026-10-07T02:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r2"},
                     {"at": "2026-10-07T03:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "c" * 40,
                      "reasons": ["the trusted checks failed: a strategy did not replay"]})
        self.assertFalse(self.check("owner_deploy")["stalled"])
        self.assertIsNone(ST.owner_deploy(self.base))


class Telling(Base):
    """One notice and one House warning a cause at most every 12 hours; a cause is told only once the gateway SENT it."""

    def stalled_store(self):
        self.ago(20)  # no birth, no run, nothing for a day: births and gym_runs stall
        self.family("lonely")

    def test_one_notice_a_cause_every_12_hours(self):
        self.stalled_store()
        out, ctx = self.run_at()
        self.assertEqual(sorted(self.notify.causes()), ["births", "gym_runs"])
        self.assertEqual(len(ctx.alerts), 2)
        self.assertTrue(all(a["level"] == "warning" and a["text"].startswith("stall: ") for a in ctx.alerts))
        facts = self.notify.calls[0]
        self.assertEqual((facts["kind"], facts["notice_id"]), ("stall", f"stall:{facts['cause']}"))
        self.assertEqual(sorted(facts), sorted(["kind", "notice_id", "cause", "what", "numbers", "since", "hours", "doing",
                                                "owner_step", "at"]))
        for later in (0.5, 6, 11.9):
            out, ctx = self.run_at(now=NOW + later * HOUR)
            self.assertEqual(len(self.notify.calls), 2, later)
            self.assertEqual(ctx.alerts, [], later)
            self.assertTrue(all("at most once every 12 h" in n["why"] for n in out["notices"]), later)
        out, ctx = self.run_at(now=NOW + 12 * HOUR)
        self.assertEqual(len(self.notify.calls), 4)
        self.assertEqual(len(ctx.alerts), 2)

    def test_a_duplicate_answer_is_not_told_and_is_tried_at_the_next_run(self):
        self.stalled_store()
        self.notify.answer = {"sent": True, "duplicate": True}
        out, ctx = self.run_at()
        self.assertEqual(len(self.notify.calls), 2)
        self.assertFalse(any(n["sent"] for n in out["notices"]))
        self.assertEqual(out["errors"], [])  # the gateway's own 12 h: no fault
        self.notify.answer = {"sent": True}
        out, ctx = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual(len(self.notify.calls), 4)
        self.assertTrue(all(n["sent"] for n in out["notices"]))
        self.assertEqual(ctx.alerts, [], "warned once, at the first run")

    def test_a_failed_notice_is_an_error_in_the_warning_and_is_tried_again(self):
        self.stalled_store()
        self.notify.answer = OSError("the gateway did not answer")
        out, ctx = self.run_at()
        self.assertEqual(len(out["errors"]), 2)
        self.assertTrue(all("(notice: the notice failed (OSError))" in a["text"] for a in ctx.alerts))
        self.notify.answer = {"sent": False, "reason": "no mail binding"}
        out, _ = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual(len(self.notify.calls), 4)
        self.assertIn("stall notice for births not sent: no mail binding", out["errors"])

    def test_no_gateway_is_said_and_nothing_breaks(self):
        self.stalled_store()
        ctx = self.ctx()
        ctx.notify = None
        ctx._config = {}  # no gateway_url, no token
        out = ST.run(ctx)
        self.assertIn("stall notice for births not sent: no gateway", out["errors"])
        self.assertTrue(all("(notice: no gateway to notify through)" in a["text"] for a in ctx.alerts))

    def test_a_cause_that_clears_is_named_and_a_recurrence_inside_12_hours_is_not_mailed_again(self):
        self.stalled_store()
        self.run_at()
        self.t = NOW + HOUR
        self.store.event("swarm.born", "lonely", {})
        for i in range(10):
            self.store.add_run("lonely", 1, {"run_id": f"r{i}", "status": "ok", "trials": 1}, window="train", stress=1.0,
                               purpose="train", prune=False)
        out, _ = self.run_at(now=NOW + 1.5 * HOUR)
        self.assertEqual(sorted(out["cleared"]), ["births", "gym_runs"])
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertFalse(state["causes"]["births"]["standing"])
        calls = len(self.notify.calls)
        out, _ = self.run_at(now=NOW + 11 * HOUR)  # gym_runs stalls again inside 12 h of its notice: not mailed again
        self.assertIn("gym_runs", out["stalled"])
        self.assertEqual(len(self.notify.calls), calls)
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertEqual(state["causes"]["gym_runs"]["seen_at"], "2026-10-07T21:20:00Z", "its time starts again")
        out, _ = self.run_at(now=NOW + 13.5 * HOUR)  # births too, past 12 h: both are told
        self.assertEqual(sorted(self.notify.causes()[calls:]), ["births", "gym_runs"])

    def test_the_gateway_record_alone_keeps_the_12_hours_when_the_state_file_is_lost(self):
        self.stalled_store()
        self.run_at()
        (self.root / ST.STATE_FILE).unlink()
        self.notify.answer = {"sent": True, "duplicate": True}
        out, _ = self.run_at(now=NOW + HOUR)
        self.assertFalse(any(n["sent"] for n in out["notices"]))

    def test_never_acts_it_writes_only_its_own_state_file(self):
        self.stalled_store()
        self.store.close()
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        db = self.root / "swarm.sqlite"
        size = db.stat().st_size
        self.run_at()
        after = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(sorted(set(after) - set(before)), [self.root / ST.STATE_FILE])
        self.assertEqual({p: after[p] for p in before if p.name.startswith("swarm.sqlite")},
                         {p: before[p] for p in before if p.name.startswith("swarm.sqlite")})
        self.assertEqual(db.stat().st_size, size)
        self.assertEqual(os.stat(self.root / ST.STATE_FILE).st_mode & 0o777, 0o600)

    def test_no_swarm_store_is_a_skipped_run(self):
        empty = self.base / "empty"
        empty.mkdir()
        ctx = Context("stall", root=empty, base=self.base, due_at=NOW, config={}, clock=lambda: NOW, settings_value={})
        self.assertEqual(ST.run(ctx)["status"], "skipped")


class Wiring(Base):
    def test_registered_every_half_hour_round_the_clock_off_in_a_pause_and_unpaid(self):
        job = by_name()["stall"]
        self.assertEqual(job.module, "league.ops.stall")
        self.assertEqual(sorted((t.kind, t.minute) for t in job.triggers), [("hourly", 20), ("hourly", 50)])
        self.assertFalse(job.in_pause)
        self.assertFalse(job.paid)
        self.assertGreaterEqual(job.grace, 3600 + 5 * 60, "an occurrence behind the longest job waits and runs")

    def test_the_runners_child_runs_it_and_its_warnings_ride_out(self):
        self.ago(20)
        self.family("lonely")
        ctx = self.ctx()
        result = run_job("stall", root=self.root, due_at=NOW, base=self.base, ctx=ctx)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(sorted(result["summary"]["stalled"]), ["births", "gym_runs"])
        self.assertEqual(len(result["alerts"]), 2)

    def test_the_population_ceiling_is_read_from_the_swarms_own_settings_when_not_handed_in(self):
        (self.root / "swarm.json").write_text(json.dumps({"population": {"floor": 4, "ceiling": 30, "start": 10}}))
        ctx = self.ctx()
        del ctx.population_ceiling
        ceiling, why = ST._ceiling(ctx, self.root)
        self.assertIsNone(why)
        self.assertIsInstance(ceiling, int)
        self.assertLessEqual(ceiling, 30)


class Funnel(Base):
    def live_book(self):
        db = sqlite3.connect(self.root / "live.sqlite")
        db.execute("CREATE TABLE orders (oid INTEGER PRIMARY KEY, family TEXT, instance TEXT, tuition INTEGER, filled_qty INTEGER, "
                   "placed_at REAL)")
        db.execute("CREATE TABLE positions (pid INTEGER PRIMARY KEY, family TEXT, instance TEXT, tuition INTEGER, status TEXT, "
                   "closed_at REAL)")
        rows = [("fam-a", "fam-a:r", 0, 1, NOW - HOUR), ("fam-b", "fam-b:i", 0, 0, NOW - 2 * HOUR),
                ("house:test", "house:test:h", 0, 1, NOW - 3 * HOUR), ("fam-a", "fam-a:r", 0, 1, NOW - 30 * HOUR)]
        db.executemany("INSERT INTO orders(family, instance, tuition, filled_qty, placed_at) VALUES(?,?,?,?,?)", rows)
        db.executemany("INSERT INTO positions(family, instance, tuition, status, closed_at) VALUES(?,?,?,?,?)",
                       [("fam-a", "fam-a:r", 0, "closed", NOW - HOUR), ("cal", "cal:c", 0, "closed", NOW - 2 * HOUR),
                        ("fam-b", "fam-b:t", 1, "open", None), ("fam-a", "fam-a:r", 0, "closed", NOW - 40 * HOUR)])
        db.commit()
        db.close()

    def populate(self):
        self.ago(30)
        old = self.family("old")
        self.store.event("swarm.born", old, {})
        self.store.add_version(old, "def decide(ctx):\n    return []\n", {}, author="seed")
        self.store.add_spend("sail_model", 1.0)
        self.ago(5)
        fid = self.family("new")
        self.store.event("swarm.born", fid, {})
        self.store.add_version(fid, "def decide(ctx):\n    return None\n", {}, author="researcher")
        self.store.add_version(fid, "def decide(ctx):\n    return ()\n", {}, author="researcher")
        for window, status in (("train", "ok"), ("train", "ok"), ("train", "disqualified"), ("validation", "ok"),
                               ("validation", "ok"), ("holdout", "ok"), ("forward", "ok"), ("train", "refused"),
                               ("train", "error"), ("weird", "ok")):
            self.store.add_run(fid, 1, {"run_id": f"{window}-{status}-{self.t}-{len(window)}-{status}", "status": status,
                                        "trials": 1}, window=window, stress=1.0, purpose=window, prune=False)
            self.t += 1
        self.store.event("swarm.tournament", None, {"validation": {"judged": {"new": {"passed": True}, "old": {"passed": False}}},
                                                    "board": [{"family": "x"}] * 50})
        self.store.add_look(fid, 1, "sha-look-1", passed=True, p_value=0.01, detail={})
        self.store.add_look(fid, 1, "sha-look-2", passed=False, p_value=0.4, detail={})
        self.store.set_band(fid, "candidate", reason="passed")
        self.store.set_band(fid, "probe", reason="a passed look")
        for kind, usd in (("sail_model", 0.5), ("gym_box", 0.25), ("claude", 2.0), ("openai", 0.0)):
            self.store.add_spend(kind, usd)
        self.store.event("swarm.guard", None, {"action": "brake", "causes": ["research_budget"]})
        self.ago(2)
        self.store.event("swarm.guard", None, {"action": "release", "causes": []})
        self.live_book()

    def test_the_window_counts_what_happened_and_nothing_older(self):
        self.populate()
        day = FN.window(self.root, NOW - 24 * HOUR, NOW)
        self.assertEqual(day["errors"], {})
        self.assertEqual((day["births"], day["versions"]), (1, 2))
        self.assertEqual(day["gym_runs"], {"train": 3, "validation": 2, "holdout": 1, "forward": 1, "probe": 0, "mechanism": 0,
                                           "other": 1})
        self.assertEqual((day["gym_runs_total"], day["gym_not_run"]), (8, 2))
        self.assertEqual(day["validations"], {"judged": 2, "passed": 1})
        self.assertEqual(day["looks"], {"taken": 2, "passed": 1})
        self.assertEqual(day["band_moves"], {"candidate": 1, "probe": 1, "sized": 0})
        self.assertEqual(day["spend_usd"], {"sail": 0.75, "claude": 2.0, "openai": 0.0})
        self.assertEqual(day["braked"]["hours"], 3.0)
        self.assertEqual(day["book"], {"orders": {"agent": 2, "house": 1}, "filled": {"agent": 1, "house": 1},
                                       "closes": {"agent": 1, "house": 1}})
        longer = FN.window(self.root, NOW - 48 * HOUR, NOW)
        self.assertEqual((longer["births"], longer["versions"], longer["spend_usd"]["sail"]), (2, 3, 1.75))
        self.assertEqual((longer["book"]["orders"]["agent"], longer["book"]["closes"]["agent"]), (3, 2))

    def test_an_unreadable_store_is_an_error_never_a_zero(self):
        empty = self.base / "nothing"
        empty.mkdir()
        out = FN.window(empty, NOW - HOUR, NOW)
        self.assertIn("swarm", out["errors"])
        self.assertNotIn("births", out)
        self.assertEqual(out["book"]["orders"], {"agent": 0, "house": 0})  # no book is nothing traded

    def test_the_release_starts_at_its_latest_promotion(self):
        rows = [{"at": "2026-10-05T10:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r1"},
                {"at": "2026-10-06T10:00:00.000Z", "stage": "verdict", "verdict": "rolled_back", "release": "r1"},
                {"at": "2026-10-06T12:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r1"},
                {"at": "2026-10-06T13:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r2"}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.assertEqual(FN.release_start(self.base, "r1"), at("2026-10-06T12:00:00Z"))
        self.assertIsNone(FN.release_start(self.base, "r3"))

    def page(self, funnel, stalls=None):
        return SB.build(day="2026-10-07", release="r1", economics=None, deploys={}, budget=None,
                        ladder={"entrants": "n/a", "in_practice": "n/a", "promoted": "n/a", "bh_family_size": "n/a"},
                        jobs={"ok": 1}, written_at="23:30Z", funnel=funnel, stalls=stalls)

    def test_the_daily_page_carries_the_funnel_and_passes_the_public_filter(self):
        self.populate()
        (self.base / "deploys.jsonl").write_text(json.dumps({"at": "2026-10-05T10:20:00.000Z", "stage": "verdict",
                                                             "verdict": "promoted", "release": "r1"}) + "\n")
        funnel = FN.read(self.root, self.base, "r1", NOW)
        text = self.page(funnel, {"causes": {"births": {"standing": True, "seen_at": "2026-10-07T01:20:00Z"},
                                             "gym_runs": {"standing": False}, "Bad Cause": {"standing": True}}})
        self.assertEqual(SB.public_problems(text), [])
        for row in ("| Births | 1 | 2 |", "| Program versions written | 2 | 3 |", "| Gym runs: train | 3 | 3 |",
                    "| Gym runs: validations (two a program: the 1.5x twin) | 2 | 2 |", "| Gym runs: looks | 1 | 1 |",
                    "| Gym runs: other windows | 1 | 1 |", "| Gym runs refused or failed | 2 | 2 |",
                    "| Validations judged (passed) | 2 (1) | 2 (1) |", "| Looks taken (passed) | 2 (1) | 2 (1) |",
                    "| Moves to Probe | 1 | 1 |", "| Real orders, agent routes (filled) | 2 (1) | 3 (2) |",
                    "| Real orders, House routes (filled) | 1 (1) | 1 (1) |", "| Real closes, agent routes | 1 | 2 |",
                    "| Research spend, Sail (USD) | 0.75 | 1.75 |", "| Research spend, Claude (USD) | 2.0 | 2.0 |",
                    "| Hours the Sail guard braked | 3.0 | 3.0 |"):
            self.assertIn(row, text)
        self.assertIn("Since the release: from 2026-10-05T10:20:00Z.", text)
        self.assertIn("Bands now: Candidate 0, Probe 1, Sized 0 (of 2 living families).", text)
        self.assertIn("Stalls standing now: births (since 2026-10-07T01:20:00Z).", text)
        self.assertNotIn("Bad Cause", text)

    def test_with_no_release_start_its_column_is_na_and_no_funnel_is_said(self):
        self.populate()
        text = self.page(FN.read(self.root, self.base, "r9", NOW), {"causes": {}})
        self.assertIn("The running release's start is not on record: its column is n/a.", text)
        self.assertIn("| Births | 1 | n/a |", text)
        self.assertIn("Stalls standing now: none.", text)
        self.assertIn("The funnel could not be read.", self.page({}))
        self.assertNotIn("## Funnel", self.page(None))

    def test_the_scoreboard_job_posts_the_funnel(self):
        self.populate()

        class Gateway:
            posts = []

            def post(self, path, body):
                self.posts.append((path, body))
                return {"commit": "c0ffee"}

        gateway = Gateway()
        ctx = Context("scoreboard", root=self.root, base=self.base, due_at=NOW, config={}, clock=lambda: NOW, gateway=gateway,
                      settings_value={})
        SB.run(ctx)
        content = gateway.posts[0][1]["content"]
        self.assertIn("## Funnel (last 24 h / since the release)", content)
        self.assertIn("| Births | 1 | n/a |", content)
        self.assertEqual(SB.public_problems(content), [])


if __name__ == "__main__":
    unittest.main()
