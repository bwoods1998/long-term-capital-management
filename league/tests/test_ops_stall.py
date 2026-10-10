"""The self-running release, build A (the owner's goal of Oct 7, 2026, items 3 and 6): the stall alarm (`league/ops/stall.py`)
names each cause from the House's own records, tells the owner through the gateway in one notice listing them all (an
owner step at once and every 12 hours, a stall needing nothing every 24 hours) and never acts; the funnel
(`league/ops/funnel.py`) counts what the swarm did in a window, and the daily page carries it."""
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

    def causes(self, call=-1):
        """The causes one notice told (the last by default)."""
        return [c["cause"] for c in self.calls[call]["causes"]] if self.calls else []

    def entry(self, cause):
        """`cause` as the latest notice that told it said it."""
        return next(c for call in reversed(self.calls) for c in call["causes"] if c["cause"] == cause)


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

    def ctx(self, *, now=NOW, ceiling=20, binds=()):
        ctx = Context("stall", root=self.root, base=self.base, due_at=now, config={}, clock=lambda: now, settings_value={})
        ctx.notify = self.notify
        ctx.population_ceiling = ceiling
        ctx.binds = list(binds)  # the settings that bind research (`settings_binds`), handed in: none unless a test says
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
        facts = self.notify.entry("births")
        self.assertEqual((facts["since"], facts["hours"]), ("2026-10-06T22:26:00Z", "26.0"))

    def test_births_the_architects_passes_are_what_the_house_is_doing(self):
        self.ago(5)
        self.store.event("swarm.architect", None, {"born": [], "skipped": "no_cell", "why": "x"})
        self.store.event("swarm.architect", None, {"born": [], "skipped": "ceiling", "why": "x"})
        self.store.event("swarm.architect", None, {"born": [], "error": "Claude said no"})
        self.store.event("swarm.architect", None, {"born": [], "proposed": 4, "route": "claude"})
        self.assertTrue(self.check("births")["stalled"])
        doing = self.notify.entry("births")["doing"]
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
        self.assertEqual((validations["numbers"]["owed_validation"], validations["numbers"]["last_validation_at"]),
                         (1, "2026-10-06T10:26:00Z"))
        # Every best validated: no Validation is owed, so none in 24 h is no stall.
        self.store.update_family("waiting", validated_version=2)
        self.assertFalse(self.check("validations", now=NOW + 1.3 * HOUR)["stalled"])

    def test_validations_the_train_best_the_researcher_picked_by_score_is_owed_too(self):
        """The candidate the tournament validates (`Tournament.candidate_version`) is the submitted best, else the Train
        best the researcher picked by score (`state.best_train_version`): the path Claude researchers always take."""
        self.ago(30)
        self.family("picked")
        self.store.set_state("picked", best_train_version=2)
        validations = self.check("validations")
        self.assertTrue(validations["stalled"])
        self.assertEqual((validations["numbers"]["train_bests"], validations["numbers"]["owed_validation"]), (1, 1))
        # A robustness failure clears `best_version`; the picked best is still the candidate. Validated, none is owed.
        self.store.update_family("picked", validated_version=2)
        self.assertFalse(self.check("validations")["stalled"])
        self.store.set_state("picked", best_train_version=3)
        self.assertTrue(self.check("validations")["stalled"], "a newer best is owed its own Validation")
        self.assertEqual((ST.candidate(None, '{"best_train_version": 4}'), ST.candidate(5, '{"best_train_version": 4}'),
                          ST.candidate(None, "{}"), ST.candidate(None, "not json"), ST.candidate(0, None)), (4, 5, None, None, None))

    def test_validations_a_family_waiting_on_its_robustness_run_or_the_drift_screen_is_not_owed(self):
        self.family("robust", best_version=1, best_train=0.5)
        self.family("drift", best_version=1, best_train=0.5)
        self.ago(1)
        self.store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {}, "errors": {},
                                                                    "waiting_robustness": ["robust"], "waiting_drift": ["drift"]}})
        validations = self.check("validations")
        self.assertFalse(validations["stalled"])
        self.assertEqual({k: validations["numbers"][k] for k in ("owed_validation", "waiting_robustness", "waiting_drift")},
                         {"owed_validation": 0, "waiting_robustness": 1, "waiting_drift": 1})
        # One more family is owed and not waiting: the round's own words are what the House is doing.
        self.family("owed", best_version=1, best_train=0.5)
        out, _ = self.run_at()
        self.assertIn("validations", out["stalled"])
        self.assertEqual(out["checks"]["validations"]["numbers"]["owed_validation"], 1)
        doing = out["checks"]["validations"]["doing"]
        self.assertIn("queued 0 and judged 0; 1 wait on their 1.5x robustness run, 1 on the drift screen, 0 failed", doing)
        # A round older than the window says nothing of now: every family without a verdict is owed.
        self.assertEqual(self.check("validations", now=NOW + 24 * HOUR)["numbers"]["owed_validation"], 3)

    def test_the_learning_games_wait_for_a_confirm_is_owed_nothing_and_its_children_are_births(self):
        """THE LEARNING GAME (league/swarm/game.py): a game-arm family in "gate" is validated only once a version of it is
        CONFIRMED, so one the round names in `waiting_game` is owed no Validation; the game's children emit no
        `swarm.born`, and their family rows (origin "game") are births all the same."""
        self.healthy(birth_hours=13, validation_hours=30)
        self.family("played", best_version=1, best_train=0.5)
        self.assertTrue(self.check("validations")["stalled"], "by today's reading its Train best is owed a Validation")
        self.ago(1)
        self.store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {}, "errors": {}, "waiting_robustness": [],
                                                                    "waiting_drift": [], "waiting_game": ["played"]}})
        validations = self.check("validations")
        self.assertFalse(validations["stalled"], "a game family waiting for a CONFIRM is owed nothing")
        self.assertEqual(validations["numbers"]["owed_validation"], 0)
        self.assertTrue(self.check("births")["stalled"])
        self.ago(2)
        child = self.store.add_family({**SPEC, "id": "g-0000abcd"}, origin="game", parent="played")
        births = self.check("births")
        self.assertFalse(births["stalled"])
        self.assertEqual((births["numbers"]["births_12h"], births["numbers"]["last_birth_at"]), (1, child["born_at"]))

    def test_a_direction_lineages_spent_try_and_a_refused_put_program_are_owed_nothing(self):
        """Release D-1b: a direction family whose lineage's one try is used or taken this round (`spent_lane`,
        `waiting_lane`), or whose candidate's code names another open than a long call (`calls_refused`, the review's
        finding 3), is owed no Validation."""
        self.healthy(validation_hours=30)
        for fid in ("spent", "waiting", "puts"):
            self.family(fid, best_version=1, best_train=0.5)
        self.assertEqual(self.check("validations")["numbers"]["owed_validation"], 3)
        self.ago(1)
        self.store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {}, "errors": {},
                                                                    "spent_lane": ["spent"], "waiting_lane": ["waiting"],
                                                                    "calls_refused": ["puts"]}})
        validations = self.check("validations")
        self.assertFalse(validations["stalled"])
        self.assertEqual(validations["numbers"]["owed_validation"], 0)

    def test_validations_a_verdict_read_from_an_identical_program_or_judged_in_a_round_is_a_verdict(self):
        self.family("twin", best_version=1, best_train=0.5)
        self.ago(3)
        # F1: an inherited verdict writes rows with no trial; it is no Gym run, but it is a verdict.
        self.store.add_run("twin", 1, {"run_id": "inherited-1", "status": "ok", "trials": 0}, window="validation", stress=1.0,
                           purpose="validation", prune=False)
        validations = self.check("validations")
        self.assertFalse(validations["stalled"])
        self.assertEqual((validations["numbers"]["validation_runs_24h"], validations["numbers"]["verdicts_inherited_rows_24h"]), (0, 1))
        self.assertEqual(self.check("gym_runs")["numbers"]["gym_runs_6h"], 0, "nothing was evaluated")
        # A verdict a round judged from a recorded result (no row of its own) is one too.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = SwarmStore(Path(tmp.name), clock=lambda: NOW - 2 * HOUR)
        self.addCleanup(store.close)
        store.add_family({**SPEC, "id": "judged"}, origin="seed")
        store.update_family("judged", best_version=2)
        store.event("swarm.tournament", None, {"validation": {"queued": 0, "judged": {"judged": {"passed": False}}}})
        from league.ops import guard

        facts = guard.read(Path(tmp.name) / "swarm.sqlite", lambda db: ST.swarm_facts(db, NOW))
        self.assertEqual((facts["judged"], facts["awaiting_ids"]), (1, ["judged"]))
        found = ST.checks(facts, now=NOW, ceiling=None, budget=None, deploy=None, heartbeat=None)
        self.assertFalse(found["validations"]["stalled"])

    def test_refused_failed_and_no_trial_validation_rows_are_no_validation_run(self):
        self.family("broken", best_version=1, best_train=0.5)
        self.runs(2, window="validation", status="refused", fid="broken", hours=2)
        self.runs(2, window="validation", status="error", fid="broken", hours=2)
        validations = self.check("validations")
        self.assertTrue(validations["stalled"], "the Gym refused or failed every Validation: none ran")
        self.assertEqual(validations["numbers"]["validation_runs_24h"], 0)
        self.assertIsNone(validations["numbers"]["last_validation_at"])

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
        # Still braked: the brake's own start is when it began, though only the window's part is counted.
        still = guard.read(Path(self.tmp2.name) / "swarm.sqlite", lambda db: FN.guard_hours(db, NOW - 24 * HOUR, NOW - 12 * HOUR))
        self.assertEqual((still["hours"], still["braked_now"], still["braked_since"]), (12.0, True, "2026-10-06T04:20:00Z"))

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
        self.assertIn("the Sail guard is braked (under_line)", self.notify.entry("gym_runs")["doing"])

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
        facts = self.notify.entry("runway_sail")
        self.assertEqual((facts["owner_step"], facts["numbers"]["runway_days_at_ceiling"]), (step, 2.4))
        self.assertEqual(self.notify.calls[0]["notice_id"], "stall:owner:runway_sail")
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
        # Which side is ahead is not in the record: the step names both ways out, neither as the default.
        self.assertEqual(check["owner_step"], "main's head bbbbbbbbbbbb and the running release differ in league/ops/stall.py, "
                                              ".github/workflows: if main is ahead, deploy it yourself (scripts/floor_box.py "
                                              "deploy); if the running release is ahead, merge it to main instead")
        self.assertEqual(self.notify.entry("owner_deploy")["since"], "2026-10-06T21:00:00Z")
        # The owner deployed: a promotion after the refusals clears it. A refusal for another reason is no owner step.
        self.deploys({"at": "2026-10-06T21:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "a" * 40, "reasons": [owner]},
                     {"at": "2026-10-07T02:00:00.000Z", "stage": "verdict", "verdict": "promoted", "release": "r2"},
                     {"at": "2026-10-07T03:00:00.000Z", "stage": "vet", "verdict": "refused", "sha": "c" * 40,
                      "reasons": ["the trusted checks failed: a strategy did not replay"]})
        self.assertFalse(self.check("owner_deploy")["stalled"])
        self.assertIsNone(ST.owner_deploy(self.base))


class Telling(Base):
    """One notice a run at most, listing every cause standing: an owner step at once (a new one at once again) and at
    most every 12 hours, a stall needing nothing from the owner at most every 24 hours; a notice is told only once the
    gateway SENT it; one House warning a cause at most every 12 hours."""

    def stalled_store(self):
        self.ago(20)  # no birth, no run, nothing for a day: births and gym_runs stall
        self.family("lonely")

    def short_sail(self, days=2.4):
        meters = {"sail": {"card_runway_days": days, "runway_days": 5.0, "research_usd_day": 9.6, "ceiling_usd_day": 15.0,
                           "topup_usd": 112.0, "card_date": "2026-10-05"}}
        (self.root / "budget.json").write_text(json.dumps({"at": NOW + 30 * HOUR, "meters": meters}))

    def test_one_notice_lists_every_cause_and_one_that_needs_nothing_is_told_once_a_day(self):
        self.stalled_store()
        out, ctx = self.run_at()
        self.assertEqual(len(self.notify.calls), 1)
        self.assertEqual(self.notify.causes(), ["births", "gym_runs"])
        facts = self.notify.calls[0]
        self.assertEqual((facts["kind"], facts["notice_id"]), ("stall", "stall:info:births+gym_runs"))
        self.assertEqual(sorted(facts), ["at", "causes", "kind", "notice_id"])
        self.assertEqual(sorted(facts["causes"][0]), sorted(["cause", "what", "numbers", "since", "hours", "doing", "owner_step"]))
        self.assertEqual(len(ctx.alerts), 2)
        self.assertTrue(all(a["level"] == "warning" and a["text"].startswith("stall: ") for a in ctx.alerts))
        self.assertTrue(out["notice"]["sent"])
        for later in (0.5, 6, 12, 23.9):
            out, ctx = self.run_at(now=NOW + later * HOUR)
            self.assertEqual(len(self.notify.calls), 1, later)
            self.assertFalse(out["notice"]["sent"])
            self.assertIn("the rest at most every 24 h", out["notice"]["why"])
            self.assertEqual(len(ctx.alerts), 2 if later == 12 else 0, f"one warning a cause every 12 h ({later})")
        self.run_at(now=NOW + 24 * HOUR)
        self.assertEqual(len(self.notify.calls), 2)

    def test_an_owner_step_is_told_at_once_with_every_other_cause_then_every_12_hours(self):
        self.stalled_store()
        self.run_at()  # births and gym_runs: told, needing nothing
        self.short_sail()
        out, _ = self.run_at(now=NOW + HOUR)  # the runway is short: an owner step, told at once though a notice went an hour ago
        self.assertEqual(len(self.notify.calls), 2)
        facts = self.notify.calls[1]
        self.assertEqual(facts["notice_id"], "stall:owner:runway_sail")
        self.assertEqual(self.notify.causes(), ["runway_sail", "births", "gym_runs"], "owner steps first, then the rest")
        for later in (1.5, 7, 12.9):
            self.run_at(now=NOW + later * HOUR)
            self.assertEqual(len(self.notify.calls), 2, later)
        self.run_at(now=NOW + 13 * HOUR)
        self.assertEqual(len(self.notify.calls), 3, "twelve hours on, the same owner step again")

    def test_a_new_owner_cause_is_told_at_once_and_one_told_is_not_told_again_inside_12_hours(self):
        self.stalled_store()
        self.short_sail()
        self.run_at()
        self.assertEqual(self.notify.calls[0]["notice_id"], "stall:owner:runway_sail")
        self.deploys_refused()
        self.run_at(now=NOW + HOUR)
        self.assertEqual(self.notify.calls[1]["notice_id"], "stall:owner:owner_deploy+runway_sail")
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertEqual(state["mail"]["owner_causes"], ["owner_deploy", "runway_sail"])
        # The runway clears and comes back inside 12 h: it was told, so it waits for the 12 h.
        self.short_sail(5.0)
        self.run_at(now=NOW + 2 * HOUR)
        self.short_sail(2.0)
        out, _ = self.run_at(now=NOW + 3 * HOUR)
        self.assertIn("runway_sail", out["stalled"])
        self.assertEqual(len(self.notify.calls), 2)
        self.run_at(now=NOW + 13 * HOUR)
        self.assertEqual(len(self.notify.calls), 3)

    def deploys_refused(self):
        owner = "league/ops/stall.py: this one is the owner's deploy (scripts/floor_box.py deploy)"
        (self.base / "deploys.jsonl").write_text(json.dumps({"at": "2026-10-07T09:00:00.000Z", "stage": "vet", "verdict": "refused",
                                                             "sha": "b" * 40, "reasons": [owner]}) + "\n")

    def test_a_duplicate_answer_is_not_told_and_is_tried_at_the_next_run(self):
        self.stalled_store()
        self.notify.answer = {"sent": True, "duplicate": True}
        out, ctx = self.run_at()
        self.assertEqual(len(self.notify.calls), 1)
        self.assertFalse(out["notice"]["sent"])
        self.assertEqual(out["errors"], [])  # the gateway's own window: no fault
        self.notify.answer = {"sent": True}
        out, ctx = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual(len(self.notify.calls), 2)
        self.assertTrue(out["notice"]["sent"])
        self.assertEqual(ctx.alerts, [], "warned once, at the first run")

    def test_a_failed_notice_is_an_error_in_the_warning_and_is_tried_again(self):
        self.stalled_store()
        self.notify.answer = OSError("the gateway did not answer")
        out, ctx = self.run_at()
        self.assertEqual(out["errors"], ["stall notice not sent: the notice failed (OSError)"])
        self.assertTrue(all("(notice: the notice failed (OSError))" in a["text"] for a in ctx.alerts))
        self.notify.answer = {"sent": False, "reason": "no mail binding"}
        out, _ = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual(len(self.notify.calls), 2)
        self.assertIn("stall notice not sent: no mail binding", out["errors"])

    def test_no_gateway_is_said_and_nothing_breaks(self):
        self.stalled_store()
        ctx = self.ctx()
        ctx.notify = None
        ctx._config = {}  # no gateway_url, no token
        out = ST.run(ctx)
        self.assertIn("stall notice not sent: no gateway", out["errors"])
        self.assertTrue(all("(notice: no gateway to notify through)" in a["text"] for a in ctx.alerts))
        self.assertEqual(out["checks"]["kill_on"]["numbers"]["kill_switch"], "unknown", "no health read: no kill cause")

    def test_a_cause_that_clears_is_named_and_its_time_starts_again(self):
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
        out, _ = self.run_at(now=NOW + 11 * HOUR)  # gym_runs stalls again
        self.assertIn("gym_runs", out["stalled"])
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertEqual(state["causes"]["gym_runs"]["seen_at"], "2026-10-07T21:20:00Z", "its time starts again")
        self.assertEqual(len(self.notify.calls), 1, "a stall needing nothing: at most one notice a day")

    def test_the_gateway_record_alone_keeps_the_pace_when_the_state_file_is_lost(self):
        self.stalled_store()
        self.run_at()
        (self.root / ST.STATE_FILE).unlink()
        self.notify.answer = {"sent": True, "duplicate": True}
        out, _ = self.run_at(now=NOW + HOUR)
        self.assertFalse(out["notice"]["sent"])

    def test_the_pace_is_pure(self):
        mail = {"owner_at": ST.S.iso(NOW), "owner_causes": ["runway_sail"], "info_at": ST.S.iso(NOW - HOUR)}
        self.assertIsNone(ST.due_notice([], [], {}, NOW))
        self.assertEqual(ST.due_notice(["births"], [], {}, NOW), "info")
        self.assertIsNone(ST.due_notice(["births"], [], mail, NOW + 23 * HOUR), "an owner notice counts for the info pace too")
        self.assertEqual(ST.due_notice(["births"], [], mail, NOW + 24 * HOUR), "info")
        self.assertIsNone(ST.due_notice(["runway_sail"], ["runway_sail"], mail, NOW + 11.9 * HOUR))
        self.assertEqual(ST.due_notice(["runway_sail"], ["runway_sail"], mail, NOW + 12 * HOUR), "owner")
        self.assertEqual(ST.due_notice(["kill_on", "runway_sail"], ["kill_on", "runway_sail"], mail, NOW + HOUR), "owner")
        self.assertEqual(ST.due_notice(["runway_sail"], ["runway_sail"], mail, NOW - HOUR), "owner", "a clock that went back")
        self.assertEqual(ST.notice_id(["runway_sail", "kill_on"]), "stall:owner:kill_on+runway_sail")
        self.assertEqual(ST.notice_id([]), "stall:info")
        self.assertEqual(ST.notice_id([], ["underspend", "births"]), "stall:info:births+underspend")
        self.assertEqual(ST.notice_id(["kill_on"], ["underspend", "kill_on"]), "stall:owner:kill_on")

    def test_a_new_cause_needing_nothing_is_told_at_once_and_the_same_ones_once_a_day(self):
        """The review of the no-captain build: a cause standing for days (the release's class-cap pair under the old
        underspend) kept the 24-hour INFO pace running for good, so every new INFO cause, the early warning of
        `birth_yield` among them, waited up to a day. A cause no notice told in the last 24 hours is told at once."""
        self.stalled_store()
        self.run_at()
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info:births+gym_runs")
        self.ago(1)
        self.store.event("swarm.status", "f", {"action": "incubator_reruns_spent", "alert": True, "text": "spent"})
        out, _ = self.run_at(now=NOW + 2 * HOUR)
        self.assertEqual(len(self.notify.calls), 2)
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info:births+gym_runs+swarm_alerts")
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertEqual(sorted(state["mail"]["told"]), ["births", "gym_runs", "swarm_alerts"])
        for later in (3, 12, 25.9):  # the alert's window ends at NOW + 11 h; the swarm_alerts cause clears and is not new
            self.run_at(now=NOW + later * HOUR)
            self.assertEqual(len(self.notify.calls), 2, later)
        self.run_at(now=NOW + 26 * HOUR)
        self.assertEqual(len(self.notify.calls), 3, "a day after the last notice: the same causes again")
        # Pure: a record kept before the told map (a state file from before this release) keeps the 24-hour pace alone.
        mail = {"info_at": ST.S.iso(NOW), "notice_id": "stall:info"}
        self.assertIsNone(ST.due_notice(["births", "underspend"], [], mail, NOW + HOUR))
        mail["told"] = {"births": ST.S.iso(NOW), "underspend": ST.S.iso(NOW - 25 * HOUR)}
        self.assertEqual(ST.due_notice(["births", "underspend"], [], mail, NOW + HOUR), "info", "told over a day ago")
        self.assertIsNone(ST.due_notice(["births"], [], mail, NOW + HOUR))

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


class OwnerSteps(Base):
    """What only the owner can do that is no shortfall of research: a pause left on, a grant that refused, the kill switch."""

    def test_a_pause_stops_the_research_causes_and_one_left_on_six_hours_is_the_owners_step(self):
        self.ago(20)
        self.family("lonely")  # births and gym_runs would stall
        pause = self.root / "PAUSE"
        pause.write_text("moving the box")
        os.utime(pause, (NOW - 2 * HOUR, NOW - 2 * HOUR))
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], [], "a pause stops research by design")
        self.assertEqual(self.notify.calls, [])
        self.assertTrue(out["checks"]["paused"]["numbers"]["maintenance_pause"])
        out, _ = self.run_at(now=NOW + 4 * HOUR)
        self.assertEqual(out["stalled"], ["paused"])
        facts = self.notify.entry("paused")
        self.assertEqual(facts["owner_step"], "lift the maintenance pause once its work is done (scripts/floor_box.py maintenance off)")
        self.assertEqual((facts["since"], facts["hours"]), ("2026-10-07T08:20:00Z", "6.0"))
        self.assertNotIn("moving the box", json.dumps(self.notify.calls), "the pause's own words stay on the box")
        # The swarm stopped by its file, too; both lifted, the research causes come back.
        (self.root / "swarm.stop").write_text("")
        os.utime(self.root / "swarm.stop", (NOW, NOW))
        self.assertIn("remove state/swarm.stop", self.check("paused", now=NOW + 7 * HOUR)["owner_step"])
        pause.unlink()
        (self.root / "swarm.stop").unlink()
        out, _ = self.run_at(now=NOW + 8 * HOUR)
        self.assertEqual(sorted(out["stalled"]), ["births", "gym_runs"])
        self.assertEqual(out["cleared"], ["paused"])

    def grant_rows(self, *rows):
        from league.ops.store import OpsStore

        ops = OpsStore(self.root)
        for due, status, error in rows:
            ops.record("grant", due, status, due, error=error)
        ops.close()

    def test_a_grant_that_refused_since_its_last_good_run_is_the_owners_step(self):
        self.healthy()
        refused = ("GrantRefused: standing grant refused: the money digest moved with no owner release on record (grant 3, "
                   "triggers digest, policy abc)")
        self.grant_rows(("2026-10-07T06:05:00Z", "ok", None), ("2026-10-07T07:05:00Z", "failed", refused),
                        ("2026-10-07T08:05:00Z", "failed", "GrantRefused: standing grant none: the account's funding cannot be read"),
                        ("2026-10-07T09:05:00Z", "failed", refused), ("2026-10-07T10:05:00Z", "skipped", None))
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["grant_refused"])
        check = out["checks"]["grant_refused"]
        self.assertEqual(check["numbers"]["grant_refusals"], 2)
        self.assertEqual(check["owner_step"], "ratify the grant by hand on the box once you have read why it refused (python3 "
                                              "scripts/live_trading.py --ratify): the money digest moved with no owner release on record")
        self.assertEqual(self.notify.entry("grant_refused")["since"], "2026-10-07T07:05:00Z")
        # A good run clears it; a failure to read is no refusal.
        self.grant_rows(("2026-10-07T11:05:00Z", "ok", None), ("2026-10-07T12:05:00Z", "failed", "GrantRefused: standing grant none: x"))
        self.assertFalse(self.check("grant_refused", now=NOW + 2 * HOUR)["stalled"])

    def test_the_kill_switch_on_is_the_owners_step_and_research_that_needs_claude_names_it(self):
        self.ago(20)
        self.family("lonely")
        ctx = self.ctx()
        ctx.health = {"kill_switch": True, "admin_log": {"last": [{"at": "2026-10-07T09:00:00.000Z", "caller": "owner",
                                                                    "action": "kill"},
                                                                   {"at": "2026-10-06T09:00:00.000Z", "action": "unkill"}]}}
        out = ST.run(ctx)
        self.assertIn("kill_on", out["stalled"])
        self.assertEqual(out["checks"]["kill_on"]["owner_step"], ST.KILL_STEP)
        self.assertEqual(out["checks"]["gym_runs"]["owner_step"], ST.KILL_STEP)
        self.assertEqual(self.notify.entry("kill_on")["since"], "2026-10-07T09:00:00Z")
        self.assertEqual(self.notify.calls[0]["notice_id"], "stall:owner:births+gym_runs+kill_on")
        ctx = self.ctx(now=NOW + HOUR)
        ctx.health = lambda: {"kill_switch": False}
        out = ST.run(ctx)
        self.assertIn("kill_on", out["cleared"])
        self.assertIsNone(out["checks"]["gym_runs"]["owner_step"])
        self.assertIsNone(ST.kill_facts({"kill_switch": "yes"}))
        self.assertIsNone(ST.kill_facts(None))


class OwnerDeployGrace(Base):
    """The readiness audit's M12 (Oct 10, 2026): the 16:20Z Oct 9 "owner deploy waiting" mail fired inside the operator's
    own 16:17-16:28Z deploy. A refusal counts once it has stood 45 minutes, and never while a deploy is in flight."""

    OWNER = "league/ops/stall.py: this one is the owner's deploy (scripts/floor_box.py deploy)"

    def refused(self, at, *rows):
        lines = [{"at": at, "stage": "vet", "verdict": "refused", "sha": "b" * 40, "reasons": [self.OWNER]}, *rows]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))

    def test_a_refusal_counts_only_after_45_minutes(self):
        self.healthy()
        self.refused("2026-10-07T09:50:00.000Z")                     # 30 minutes before NOW
        check = self.check("owner_deploy")
        self.assertFalse(check["stalled"])
        self.assertIsNone(check["owner_step"])
        self.assertIn("inside the 45-minute grace", check["what"])
        self.assertEqual(self.notify.calls, [])
        out, _ = self.run_at(now=NOW + 20 * 60)                      # 50 minutes
        self.assertEqual(out["stalled"], ["owner_deploy"])
        self.assertEqual(self.notify.entry("owner_deploy")["since"], "2026-10-07T09:50:00Z")

    def test_a_deploy_in_flight_holds_it_back_and_one_that_died_does_not(self):
        self.healthy()
        start = {"at": "2026-10-07T10:15:00.000Z", "deploy": "r9@1", "release": "r9", "stage": "start"}
        self.refused("2026-10-07T08:00:00.000Z", start, {"at": "2026-10-07T10:16:00.000Z", "deploy": "r9@1", "stage": "watch"})
        check = self.check("owner_deploy")
        self.assertFalse(check["stalled"], "the operator's own deploy is in flight")
        self.assertTrue(check["numbers"]["deploy_in_flight"])
        self.assertIn("a deploy is in flight", check["what"])
        self.assertEqual(ST.deploy_flight(self.base, self.root, NOW)["deploy"], "r9@1")
        # Its verdict (not a promotion: the canary refused it) ends the flight: the refusal stands again.
        self.refused("2026-10-07T08:00:00.000Z", start, {"at": "2026-10-07T10:18:00.000Z", "deploy": "r9@1", "stage": "verdict",
                                                         "verdict": "refused", "reasons": ["canary: x"]})
        self.assertTrue(self.check("owner_deploy")["stalled"])
        # A start with no verdict for over two hours died unjudged: no flight.
        self.refused("2026-10-07T07:00:00.000Z", {**start, "at": "2026-10-07T08:00:00.000Z"})
        self.assertIsNone(ST.deploy_flight(self.base, self.root, NOW))
        self.assertTrue(self.check("owner_deploy")["stalled"])

    def test_the_operators_own_nightly_stop_is_a_deploy_in_flight_for_two_hours(self):
        self.healthy()
        self.refused("2026-10-07T08:00:00.000Z")
        stop = self.root / "data" / "nightly.stop"
        stop.parent.mkdir(parents=True)
        stop.write_text("")                                         # docs/operations.md "Deploy" step 2: a touch
        os.utime(stop, (NOW - 30 * 60, NOW - 30 * 60))
        self.assertFalse(self.check("owner_deploy")["stalled"])
        stop.write_text("operator:deploy wfix")
        os.utime(stop, (NOW - 30 * 60, NOW - 30 * 60))
        self.assertEqual(ST.deploy_flight(self.base, self.root, NOW)["marker"], "operator:deploy wfix")
        # The updater's own stop is the updater's deploy (its start row says so), never the operator's.
        stop.write_text("updater:20261007T101500Z")
        os.utime(stop, (NOW - 30 * 60, NOW - 30 * 60))
        self.assertIsNone(ST.deploy_flight(self.base, self.root, NOW))
        stop.write_text("")
        os.utime(stop, (NOW - 3 * HOUR, NOW - 3 * HOUR))
        self.assertTrue(self.check("owner_deploy")["stalled"], "a stop left over two hours is no deploy in flight")


class LaneAndNightly(Base):
    """The readiness audit's M6 (Oct 10, 2026): the direction lane's alarms (K5 an owner step), a Done checkpoint (told at
    once), a pre-open FAIL and a late or stopped nightly reach the owner through the same one notice."""

    def report(self, *alarms, at="2026-10-07T01:30:00Z", k5=None, mode="gate", done=None):
        doc = {"at": at, "lane": {"mode": mode}, "k5": k5 or {"tripped": False, "cleared": False}, "alarms": list(alarms)}
        if done is not None:
            doc["done"] = done
        (self.root / "dlane-report.json").write_text(json.dumps(doc))

    @staticmethod
    def done(*checkpoints, meter="screen"):
        """A report's `done` block: `checkpoints` (at_close, holds, final) on `meter`, none on the other."""
        rows = [{"at_close": k, "holds": holds, "final": final, "items": {"3": holds, "4": holds, "7": holds}}
                for k, holds, final in checkpoints]
        return {meter: {"checkpoints": rows}, ("all" if meter == "screen" else "screen"): {"checkpoints": []}}

    def run_lane(self, now=NOW, lane_on=True):
        ctx = self.ctx(now=now)
        ctx.lane_on = lane_on
        return ST.run(ctx)

    def test_a_warning_alarm_is_the_dlane_cause_and_an_info_one_is_not(self):
        self.healthy()
        self.report({"id": "A9", "level": "info", "text": "A9: every live direction program has opened nothing"})
        out = self.run_lane()
        self.assertEqual(out["stalled"], [])
        self.report({"id": "A4", "level": "warning", "text": "A4: the Probe loss budget has under one unit of room"},
                    {"id": "PL1", "level": "warning", "text": "PL1: retired swarm-side 1 programs"})
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["dlane"])
        check = out["checks"]["dlane"]
        self.assertEqual(check["numbers"]["alarms"], "a4,pl1")
        self.assertIn("A4: the Probe loss budget", check["what"])
        self.assertIsNone(check["owner_step"], "the House acts on these by its own rules")
        self.assertEqual(self.notify.causes(), ["dlane"])
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info:dlane")

    def test_k5_holding_or_disarmed_is_the_owners_step(self):
        self.healthy()
        self.report({"id": "K5", "level": "warning", "new": True, "text": "K5 tripped: ..."},
                    k5={"tripped": True, "cleared": False, "at": "2026-10-07T01:30:00Z", "net": -612.0})
        out = self.run_lane()
        self.assertEqual(out["checks"]["dlane"]["owner_step"], ST.K5_STEP)
        self.assertEqual(out["checks"]["dlane"]["numbers"]["k5"], "tripped")
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:owner:dlane")
        self.report({"id": "K5", "level": "warning", "disarmed": True, "text": "K5 is disarmed"},
                    k5={"tripped": False, "cleared": True})
        self.assertEqual(self.run_lane(now=NOW + HOUR)["checks"]["dlane"]["owner_step"], ST.K5_DISARMED_STEP)

    def test_a_stale_report_is_a_stopped_job_while_the_lane_is_on(self):
        self.healthy()
        self.report(at="2026-10-05T01:30:00Z")                       # 57 hours old
        self.assertEqual(self.run_lane()["stalled"], ["dlane"])
        self.assertIn("has not written it since", self.run_lane()["checks"]["dlane"]["what"])
        self.assertEqual(self.run_lane(lane_on=False)["stalled"], [], "a lane switched off writes no report")

    def test_a_done_checkpoint_is_told_at_once_as_an_owner_line(self):
        self.healthy()
        a8 = {"id": "A8", "level": "info", "meter": "done_screen", "at_close": 30, "text": "A8: Done criteria hold"}
        # A provisional holding reading may still flip: nothing is told (DONE-RULE-A1 A1.4).
        self.report(a8, done=self.done((30, True, False)))
        self.assertEqual(self.run_lane()["stalled"], [])
        self.report(a8, done=self.done((30, True, True)))
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["done"])
        self.assertIn("done_screen at close 30", out["checks"]["done"]["owner_step"])
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:owner:done")
        self.assertEqual(self.notify.entry("done")["numbers"]["checkpoints"], "done_screen:30")
        self.assertEqual(json.loads((self.root / "stall.json").read_text())["done_told"], ["done_screen:30"])
        # The next day's report no longer carries A8 (said once) but keeps the final reading (frozen): told, it clears.
        self.report(done=self.done((30, True, True)))
        self.assertEqual(self.run_lane(now=NOW + HOUR)["cleared"], ["done"])
        self.assertEqual(len(self.notify.calls), 1)

    def test_an_untold_done_claim_stands_until_a_notice_is_sent(self):
        """The review of the weekend fixes (Oct 10, 2026): the cause read the report's A8, which one report says once. A
        House start (the dlane job's at-start run rewrites the report without it) or a notice the gateway did not send
        before the next dlane run left the claim in a ledger row only."""
        self.healthy()
        # The report the stall run first reads has no A8 at all (a restart rewrote it): the final reading is the record.
        self.report(done=self.done((30, True, True), meter="all"))
        self.notify.answer = OSError("the gateway did not answer")
        out = self.run_lane()
        self.assertEqual((out["stalled"], out["notice"]["sent"]), (["done"], False))
        self.assertEqual(json.loads((self.root / "stall.json").read_text())["done_told"], [], "not told until SENT")
        self.notify.answer = {"sent": False, "reason": "400 unknown stall cause"}             # an old gateway
        self.assertEqual(self.run_lane(now=NOW + HOUR)["stalled"], ["done"])
        self.notify.answer = {"sent": True}
        out = self.run_lane(now=NOW + 2 * HOUR)
        self.assertEqual((out["stalled"], out["notice"]["sent"]), (["done"], True))
        self.assertEqual(self.notify.entry("done")["numbers"]["checkpoints"], "done_all:30")
        self.assertEqual(self.run_lane(now=NOW + 3 * HOUR)["stalled"], [], "told once")
        # The next checkpoint that holds is a new claim; inside the owner notice's 12 h it waits for the pace, standing.
        self.report(done=self.done((30, True, True), (40, True, True), meter="all"))
        out = self.run_lane(now=NOW + 4 * HOUR)
        self.assertEqual((out["stalled"], out["notice"]["sent"]), (["done"], False))
        self.assertEqual(out["checks"]["done"]["numbers"]["checkpoints"], "done_all:40")
        out = self.run_lane(now=NOW + 15 * HOUR)
        self.assertTrue(out["notice"]["sent"])
        self.assertEqual(json.loads((self.root / "stall.json").read_text())["done_told"], ["done_all:30", "done_all:40"])

    def test_with_the_lane_off_its_last_report_is_not_read(self):
        """The review of the weekend fixes (Oct 10, 2026): `dlane.mode` "off" writes no report, so the last one stayed:
        its K5 mailed an owner step for a lane that is off, and its A8 a Done claim, at every run for good."""
        self.healthy()
        self.report({"id": "K5", "level": "warning", "new": True, "text": "K5 tripped: ..."},
                    {"id": "A8", "level": "info", "meter": "done_all", "at_close": 30, "text": "A8: Done criteria hold"},
                    k5={"tripped": True, "cleared": False}, done=self.done((30, True, True), meter="all"))
        out = self.run_lane(lane_on=False)
        self.assertEqual(out["stalled"], [])
        self.assertEqual(self.notify.calls, [])
        late = self.run_lane(now=NOW + 90 * 24 * HOUR, lane_on=False)       # births and Gym runs stall by then
        self.assertFalse({"dlane", "done"} & set(late["stalled"]), "never, however long the lane stays off")
        self.assertEqual(out["checks"]["dlane"]["what"], ST.LANE_OFF_WHAT)
        self.assertEqual((out["checks"]["dlane"]["numbers"]["lane_mode"], out["checks"]["dlane"]["owner_step"]), ("off", None))
        self.assertEqual(out["checks"]["done"]["what"], ST.LANE_OFF_WHAT)
        # The lane back on: the same report is read again (and is stale by then).
        out = self.run_lane(now=NOW, lane_on=True)
        self.assertEqual(out["stalled"], ["dlane", "done"])
        self.assertEqual(out["checks"]["dlane"]["owner_step"], ST.K5_STEP)

    def preopen(self, due, status="ok", failed=(), error=None):
        from league.ops.store import OpsStore

        ops = OpsStore(self.root)
        checks = [{"n": int(f.split()[0]), "name": f.split()[1], "ok": False, "headline": f"{f} headline"} for f in failed]
        ops.record("preopen", due, status, due, summary={"failed": list(failed), "checks": checks}, error=error)
        ops.close()

    def test_a_preopen_fail_of_the_last_day_is_a_stall_and_an_older_one_is_not(self):
        self.healthy()
        self.preopen("2026-10-06T12:30:00Z", failed=["9 compute"])
        self.preopen("2026-10-07T09:30:00Z", failed=["6 bands", "9 compute"])
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["preopen"])
        check = out["checks"]["preopen"]
        self.assertEqual(check["numbers"]["failed_checks"], "6_bands,9_compute")
        self.assertIn("6 bands: 6 bands headline", check["what"])
        self.assertIsNone(check["owner_step"])
        self.assertEqual(self.run_lane(now=NOW + 26 * HOUR)["checks"]["preopen"]["stalled"], False, "a day old: not read")
        self.preopen("2026-10-08T09:30:00Z", status="failed", error="KeyError: x")
        self.assertIn("did not run", self.run_lane(now=NOW + 26 * HOUR)["checks"]["preopen"]["what"])

    def nightly(self, *, day=None, error=None, stop=None, stop_age=None):
        if day is not None:
            (self.root / "gym-forward.json").write_text(json.dumps({"day": day, "ready_at": f"{day}T06:14:21.81+00:00"}))
        data = self.root / "data"
        data.mkdir(exist_ok=True)
        (data / "nightly.json").write_text(json.dumps({"day": day, "error": error, "retry_at": 0}))
        if stop is not None:
            (data / "nightly.stop").write_text(stop)
            os.utime(data / "nightly.stop", (NOW - stop_age, NOW - stop_age))

    def test_a_late_ready_file_is_the_forward_cause_once_the_day_is_ten_hours_in(self):
        self.healthy()
        self.nightly(day="2026-10-06")                                # Wed Oct 7 10:20Z: Tue Oct 6 is the last session
        self.assertEqual(self.run_lane()["stalled"], [])
        self.nightly(day="2026-10-05")
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["forward"])
        numbers = out["checks"]["forward"]["numbers"]
        self.assertEqual((numbers["ready_day"], numbers["expected_day"]), ("2026-10-05", "2026-10-06"))
        self.assertEqual(numbers["ready_at"], "2026-10-05T06:14:21Z")
        self.assertIsNone(out["checks"]["forward"]["owner_step"])
        # Before 10:00Z the night before's session is the one due: a Monday morning waits on Friday's, not Sunday's.
        self.assertFalse(self.run_lane(now=at("2026-10-07T09:00:00Z"))["checks"]["forward"]["stalled"])
        self.assertEqual(ST.last_session_before("2026-10-12"), "2026-10-09")

    def test_a_nightly_error_counts_from_the_first_run_that_saw_it(self):
        self.healthy()
        self.nightly(day="2026-10-06", error="sip_gaps: 503")
        self.assertFalse(self.run_lane()["checks"]["forward"]["stalled"])
        self.assertFalse(self.run_lane(now=NOW + 5 * HOUR)["checks"]["forward"]["stalled"])
        out = self.run_lane(now=NOW + 6 * HOUR)
        self.assertTrue(out["checks"]["forward"]["stalled"])
        self.assertIn("carried an error for 6.0 h", out["checks"]["forward"]["what"])
        self.nightly(day="2026-10-06")                               # it cleared: the clock starts again
        self.run_lane(now=NOW + 7 * HOUR)
        self.nightly(day="2026-10-06", error="again")
        self.assertFalse(self.run_lane(now=NOW + 8 * HOUR)["checks"]["forward"]["stalled"])

    def test_a_nightly_stop_left_two_hours_is_the_owners_step(self):
        self.healthy()
        self.nightly(day="2026-10-06", stop="", stop_age=1 * HOUR)
        self.assertFalse(self.run_lane()["checks"]["forward"]["stalled"])
        self.nightly(day="2026-10-06", stop="operator:deploy", stop_age=3 * HOUR)
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["forward"])
        self.assertIn("remove /workspace/state/data/nightly.stop (it is the operator's)", out["checks"]["forward"]["owner_step"])
        self.assertEqual(self.notify.entry("forward")["since"], "2026-10-07T07:20:00Z")
        self.nightly(day="2026-10-06", stop="updater:x", stop_age=3 * HOUR)
        self.assertIn("automation wrote it", self.run_lane(now=NOW + HOUR)["checks"]["forward"]["owner_step"])

    def test_a_done_checkpoint_is_news_never_a_stall_on_the_daily_page(self):
        from league.ops import dlane_report as R

        self.assertEqual(ST.NEWS_CAUSES, R.NEWS_CAUSES)
        stalls = {"causes": {"done": {"standing": True, "seen_at": "2026-10-07T01:50:00Z"},
                             "forward": {"standing": True, "seen_at": "2026-10-07T10:20:00Z"}}}
        lines = SB.funnel_lines({"day": {}}, stalls)
        self.assertIn("Stalls standing now: forward (since 2026-10-07T10:20:00Z).", lines)

    def test_every_new_cause_is_in_the_gateways_words(self):
        source = (Path(__file__).resolve().parents[2] / "gateway" / "lib" / "email.mjs").read_text()
        for cause in ("dlane", "done", "preopen", "forward", "birth_yield", "swarm_alerts", "underspend"):
            self.assertIn(cause, ST.CAUSES)
            self.assertIn(f"  {cause}: '", source)


def incomplete(*fields):
    """An incomplete card's refusal as the architect writes it (league/swarm/architect.py `admit`)."""
    return {"slug": "x", "why": "incomplete card: " + "; ".join(f"{f}: at least 30 characters (9 given)" for f in fields)}


def refusal(row="dir-spy-3", why="a card in a refuted cell needs a rebirth that names its row"):
    return {"slug": "y", "why": why, "row": row, "matched": 4}


class NoCaptain(Base):
    """THE NO-CAPTAIN CAUSES (Oct 10, 2026; the no-captain audit): the architect's birth yield and its jam, the swarm's own
    alerts, and research under its budget or bound by a setting. Each reproduces a captain's hand intervention."""

    def architect(self, hours, *, proposed=6, born=0, items=(), incomplete_n=0, rebirth_n=0, **extra):
        self.ago(hours)
        payload = {"born": [f"b{hours}-{i}" for i in range(born)], "proposed": proposed, "route": "sail",
                   "card_refused": {"incomplete": incomplete_n, "rebirth": rebirth_n, "items": list(items)}, **extra}
        self.store.event("swarm.architect", None, payload)

    def test_the_tally_reads_every_kind_of_pass_and_the_fields_a_card_lacked(self):
        passes = [(NOW - 60, {"skipped": "no_cell"}), (NOW - 50, {"skipped": "ceiling"}), (NOW - 40, {"error": "x"}),
                  (NOW - 30, {"born": ["a"], "proposed": 5, "truncated": {"salvaged": 2}, "class_capped": {"c": 2},
                              "lane_refused": {"alpha": 1, "direction": 0},
                              "card_refused": {"incomplete": 2, "rebirth": 1, "spent_lineage": 1,
                                               "items": [incomplete("comparison", "falsification"), incomplete("comparison"),
                                                         refusal("r1"), refusal("r1"), {"why": None}, "junk"]}}),
                  (NOW - 20, {"born": [], "proposed": 0}), (NOW - 10 * HOUR, {"born": ["old"], "proposed": 9}),
                  (None, {"proposed": 3}), (NOW - 5, "junk")]
        tally = ST.architect_tally(passes, NOW - HOUR)
        self.assertEqual({k: tally[k] for k in ("passes", "asked", "no_cell", "ceiling", "failed", "proposed", "born",
                                                "incomplete", "rebirth", "spent_lineage", "capped", "cut", "empty")},
                         {"passes": 5, "asked": 2, "no_cell": 1, "ceiling": 1, "failed": 1, "proposed": 5, "born": 1,
                          "incomplete": 2, "rebirth": 1, "spent_lineage": 1, "capped": 3, "cut": 1, "empty": 1})
        self.assertEqual((tally["fields"], tally["rebirth_rows"]), ({"comparison": 2, "falsification": 1}, 1))
        self.assertEqual((ST.wanting(tally), ST.card_refusals(tally)), (4, 4))
        self.assertEqual(ST.card_fields("incomplete card: cost.hurdle: a fraction (2 given); inputs: a list; inputs: at most 3"),
                         ["cost.hurdle", "inputs"])
        self.assertEqual((ST.card_fields("a card in a refuted cell"), ST.card_fields(None)), ([], []))
        # The main way the passes bore nothing, and its lever.
        self.assertEqual(ST.jam_kind({"asked": 0, "no_cell": 3, "failed": 1}), "no_cell")
        self.assertEqual(ST.jam_kind({"asked": 0, "no_cell": 0, "failed": 2}), "failed")
        self.assertEqual(ST.jam_kind({"asked": 3, "proposed": 0, "cut": 2}), "cut")
        self.assertEqual(ST.jam_kind({"asked": 3, "proposed": 0}), "empty")
        self.assertEqual(ST.jam_kind({"asked": 3, "proposed": 18, "rebirth": 9, "incomplete": 4}), "rebirth")
        self.assertEqual(ST.jam_kind({"asked": 3, "proposed": 18}), "other")
        self.assertIn("(most often comparison 2x, falsification 1x)", ST.lever({**tally, "rebirth": 0, "spent_lineage": 0,
                                                                                  "capped": 0}))

    def test_birth_yield_a_wall_of_incomplete_cards_is_said_with_the_fields_they_lack(self):
        """Oct 10, 13:21Z and 14:22Z: always-in cards refused 'incomplete' pass after pass (comparison 9 characters of 30,
        falsification under 40), found by the captain's floor check, fixed by agenda v21.6."""
        self.healthy(birth_hours=1.0)
        for hours in (2.8, 2.1, 1.4, 0.7):
            self.architect(hours, proposed=6, born=1 if hours == 2.8 else 0, incomplete_n=5,
                           items=[incomplete("comparison", "falsification")] * 4 + [incomplete("comparison")])
        out, ctx = self.run_at()
        check = out["checks"]["birth_yield"]
        self.assertTrue(check["stalled"])
        self.assertIsNone(check["owner_step"], "INFO: the births cause carries the step once the jam stands")
        self.assertEqual({k: check["numbers"][k] for k in ("asked_3h", "proposed_3h", "born_3h", "refused_share",
                                                           "refused_incomplete", "top_fields", "kind")},
                         {"asked_3h": 4, "proposed_3h": 24, "born_3h": 1, "refused_share": 0.83, "refused_incomplete": 20,
                          "top_fields": "comparison:20,falsification:16", "kind": "incomplete"})
        self.assertIn("The incomplete cards most often lacked comparison (20x), falsification (16x).", check["what"])
        self.assertIn("install an agenda whose card section the model can fill", check["doing"])
        self.assertFalse(out["checks"]["births"]["stalled"], "a birth an hour ago")
        self.assertTrue(any(a["text"].startswith("stall: birth_yield: The architect bore 1 of 24 proposals")
                            for a in ctx.alerts), "a House warning")
        # Three passes are too few to read a yield; at the ceiling no birth is owed.
        self.assertFalse(self.check("birth_yield", ceiling=2)["stalled"])

    def test_birth_yield_two_dry_hours_while_the_architect_keeps_asking(self):
        """Oct 9, 23:15Z: a pass proposed 6 and bore 0 (the rebirth claims failed `cards._cites`), and the next ones too."""
        self.healthy(birth_hours=2.5)
        for hours in (1.9, 1.2, 0.5):
            self.architect(hours, proposed=6, rebirth_n=6, items=[refusal(f"r{hours}")] * 6)
        check = self.check("birth_yield")
        self.assertTrue(check["stalled"])
        self.assertIn("No family was born in the last 2 h while the architect wanted births in 3 passes.", check["what"])
        self.assertEqual((check["numbers"]["births_2h"], check["numbers"]["kind"], check["numbers"]["rebirth_rows"]),
                         (0, "rebirth", 3))
        self.assertEqual(self.notify.entry("birth_yield")["since"], "2026-10-07T07:50:00Z", "since the last birth")
        # A birth inside the two hours, and passes that bear: no cause.
        self.ago(0.2)
        self.store.event("swarm.born", self.family("born-now"), {"origin": "architect"})
        self.assertFalse(self.check("birth_yield")["stalled"])

    def test_a_bearing_architect_raises_no_yield_cause(self):
        self.healthy(birth_hours=0.5)
        for hours in (2.5, 1.8, 1.1, 0.4):
            self.architect(hours, proposed=8, born=3, rebirth_n=4, items=[refusal()] * 4)
        check = self.check("birth_yield")
        self.assertFalse(check["stalled"])
        self.assertEqual((check["numbers"]["born_3h"], check["numbers"]["refused_share"]), (12, 0.5))
        # The ceiling's skips are no passes that want births.
        unknown = ST.checks({"alive": 2, "births": 0, "yield": {"low": {"asked": 9, "born": 0}, "dry": {}}}, now=NOW,
                            ceiling=None, budget=None, deploy=None, heartbeat=None)
        self.assertFalse(unknown["birth_yield"]["stalled"], "an unknown ceiling raises nothing")

    def test_births_a_six_hour_jam_is_the_owners_step_naming_its_lever(self):
        """Oct 10, 15:41-16:22Z: births 0/0/0 under agenda v21.4 (a graveyard wall), reverted by the captain at 16:24:59Z.
        Without a captain the 12-hour births cause was INFO: nobody was asked. Now a jam of `JAM_HOURS` with passes that
        kept wanting births is the owner's step, at once."""
        self.healthy(birth_hours=6.5)
        for hours in (5.5, 4.0, 2.5, 1.0):
            self.architect(hours, proposed=10, rebirth_n=8, items=[refusal()] * 8, class_capped={"long_single x etf": 2})
        out, _ = self.run_at()
        births = out["checks"]["births"]
        self.assertTrue(births["stalled"])
        self.assertTrue(births["owner_step"].startswith("the architect wanted births in 4 passes over the last 6 h and none "
                                                        "was born: the cards land in refuted cells"))
        self.assertIn("raise architect.max_rebirths_per_cell only if the evidence warrants", births["owner_step"])
        self.assertEqual((births["numbers"]["jam_kind"], births["numbers"]["wanting_passes_6h"],
                          births["numbers"]["card_refused_6h"]), ("rebirth", 4, 32))
        self.assertIn("No family was born in the last 6.5 h while the population is", births["what"])
        self.assertIn("the card checks refused 32 (0 incomplete, 32 by the rebirth rule, 0 into a spent lineage); 8 met a "
                      "cap", births["what"])
        self.assertIn("births", self.notify.calls[-1]["notice_id"], "an owner notice, mailed at once")
        # Three passes in six hours are no jam: a birth in the last 12 h and three wanting passes raise nothing.
        three = {"passes": 3, "asked": 3, "proposed": 30, "rebirth": 24}
        swarm = {"alive": 2, "births": 1, "last_birth_at": ST.S.iso(NOW - 6.5 * HOUR), "yield": {"jam": three}}
        quiet = ST.checks(swarm, now=NOW, ceiling=20, budget=None, deploy=None, heartbeat=None)["births"]
        self.assertEqual((quiet["stalled"], quiet["owner_step"], quiet["numbers"]["jam_kind"]), (False, None, "none"))
        swarm["yield"]["jam"] = {**three, "passes": 4, "asked": 4}
        self.assertTrue(ST.checks(swarm, now=NOW, ceiling=20, budget=None, deploy=None, heartbeat=None)["births"]["owner_step"])

    def test_births_too_few_passes_or_a_pause_is_no_jam(self):
        self.healthy(birth_hours=7)
        for hours in (5.0, 3.0, 1.0):
            self.architect(hours, proposed=10, rebirth_n=10, items=[refusal()] * 10)
        births = self.check("births")
        self.assertFalse(births["stalled"], "a birth 7 h ago and three passes: neither the 12 h nor the jam")
        self.architect(0.5, proposed=0, skipped="ceiling")
        self.assertFalse(self.check("births")["stalled"], "a pass at the ceiling wants no birth")
        self.architect(0.4, proposed=0, error="Sail said no")
        jammed = self.check("births")
        self.assertTrue(jammed["stalled"])
        self.assertIsNotNone(jammed["owner_step"])
        (self.root / "PAUSE").write_text("maintenance")
        os.utime(self.root / "PAUSE", (NOW - HOUR, NOW - HOUR))
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], [], "a pause stops research by design: no jam, no yield")

    def test_a_jam_of_failed_calls_is_no_owner_step(self):
        """A provider's outage (the architect's calls fail: a Sail error after its fallback, a poll's timeout) heals when
        the route answers again; the owner can do nothing about it, so six hours of it is the jam's INFO, never an owner
        step that would fail DONE-RULE item 7 (the review of the no-captain build)."""
        self.healthy(birth_hours=7)
        for hours in (5.5, 4.0, 2.5, 1.0):
            self.architect(hours, proposed=0, error="SailError: the window did not answer")
        out, _ = self.run_at()
        births = out["checks"]["births"]
        self.assertTrue(births["stalled"])
        self.assertIsNone(births["owner_step"])
        self.assertEqual(births["numbers"]["jam_kind"], "failed")
        self.assertIn("4 failed. No owner step: the architect's model calls fail", births["what"])
        self.assertNotIn("births", self.notify.calls[-1]["notice_id"].partition("owner:")[2])
        # A cut answer is the owner's (a setting clears it): the effort or the output cap.
        self.architect(0.5, proposed=0, truncated=True)
        self.architect(0.4, proposed=0, truncated=True)
        self.architect(0.3, proposed=0, truncated=True)
        self.architect(0.2, proposed=0, truncated=True)
        cut = self.check("births")
        self.assertEqual(cut["numbers"]["jam_kind"], "cut")
        self.assertIn("lower architect.sail_effort or raise architect.max_output_tokens", cut["owner_step"])

    def alert(self, when, action, family=None, **payload):
        self.t = at(when)
        self.store.event("swarm.status", family, {"action": action, "alert": True, "text": f"{action} text", **payload})

    def test_swarm_alerts_an_alert_before_midnight_is_no_owner_step_the_next_day(self):
        """The review of the no-captain build: `reader_cut` fired at 22:00Z (today's cut cap reached; the version is asked
        again tomorrow) carried its owner step on every run of the next morning for twelve hours, so the next UTC day
        failed DONE-RULE item 7 though the owner raised the cap at 22:05Z. Its condition is read now: the UTC day it
        fired, and the cap it met."""
        self.alert("2026-10-06T22:00:00Z", "reader_cut", "fam-1", stage="review", max_output_tokens=6000)
        late = self.check("swarm_alerts", now=at("2026-10-06T22:20:00Z"))
        self.assertEqual((late["stalled"], late["owner_step"]), (True, ST.ALERT_STEPS["reader_cut"]))
        morning, _ = self.run_at(now=at("2026-10-07T00:20:00Z"))
        alerts = morning["checks"]["swarm_alerts"]
        self.assertEqual((alerts["stalled"], alerts["owner_step"], alerts["numbers"]["cleared_kinds"]), (False, None, 1))
        self.assertIn("cleared since their alert: reader_cut", alerts["what"])
        # The owner raises the cap the same evening: cleared at the next run, though the alert is in the window.
        (self.root / "swarm.json").write_text(json.dumps({"gate": {"review_max_output_tokens": 12000}}))
        fixed = self.check("swarm_alerts", now=at("2026-10-06T22:50:00Z"))
        self.assertEqual((fixed["stalled"], fixed["owner_step"]), (False, None))
        # A kind whose condition is not read (`look_failed_three_times`): the owner's step on its own UTC day only.
        self.alert("2026-10-06T23:00:00Z", "look_failed_three_times", "fam-2", version=3, tries=3)
        same = self.check("swarm_alerts", now=at("2026-10-06T23:20:00Z"))
        self.assertEqual(same["owner_step"], ST.ALERT_STEPS["look_failed_three_times"])
        next_day = self.check("swarm_alerts", now=at("2026-10-07T00:20:00Z"))
        self.assertEqual((next_day["stalled"], next_day["owner_step"]), (True, None))
        self.assertIn("look_failed_three_times x1 (last 2026-10-06T23:00:00Z; an earlier UTC day's, no owner step now)",
                      next_day["what"])
        # Unread states (no settings): every owner kind by the day rule.
        pure = ST._alerts_check(at("2026-10-07T00:20:00Z"), {"reader_cut": {"n": 1, "first_at": "2026-10-06T22:00:00Z",
                                                                             "last_at": "2026-10-06T22:00:00Z", "text": "x"}})
        self.assertEqual((pure["stalled"], pure["owner_step"]), (True, None))

    def test_swarm_alerts_a_one_shot_alert_stands_while_its_condition_does(self):
        """The swarm raises `gate_coverage` once per lacking set, `agenda_guard` at its start, `train_span_mismatch` once a
        key: twelve hours on the alert's window dropped them while the condition held. Read from the swarm's settings
        and store, each stands until it is fixed, and clears at the next run once it is."""
        self.healthy()
        self.ago(20)
        self.store.event("swarm.status", None, {"action": "gate_coverage", "alert": True, "image": "sbcp_gate-1",
                                                "missing": ["QQQ"], "text": "the gate image sbcp_gate-1 holds no holdout"})
        self.store.event("swarm.status", None, {"action": "train_span_mismatch", "alert": True, "image": "sbcp_gym-1",
                                                "span": "2022-01-03", "image_train_first": "2020-01-02",
                                                "text": "the Gym image starts Train at 2020-01-02"})
        self.store.put("gate_coverage", {"sbcp_gate-1": {"roots": ["SPY", "IWM", "XSP", "SPXW"], "missing": []}})
        settings = {"gym": {"gate_checkpoint": "sbcp_gate-1", "image_checkpoint": "sbcp_gym-1"},
                    "dlane": {"mode": "gate"}, "architect": {"agenda_locked": "an agenda \u00e9"}}
        (self.root / "swarm.json").write_text(json.dumps(settings))
        out, _ = self.run_at()
        alerts = out["checks"]["swarm_alerts"]
        self.assertTrue(alerts["stalled"])
        for kind in ("gate_coverage", "train_span_mismatch", "agenda_guard"):
            self.assertIn(ST.ALERT_STEPS[kind], alerts["owner_step"], kind)
        self.assertIn("gate_coverage (stands now): the gate image sbcp_gate-1 holds no holdout for QQQ (gym.roots)",
                      alerts["what"])
        self.assertIn("train_span_mismatch (stands now; last alert 2026-10-06T14:20:00Z)", alerts["what"])
        self.assertEqual(alerts["numbers"]["owner_kinds"], 3)
        self.assertIn("swarm_alerts", self.notify.calls[-1]["notice_id"])
        # Fixed: another gate image, the image built for the span, an ASCII agenda: nothing stands at the next run.
        settings = {"gym": {"gate_checkpoint": "sbcp_gate-2", "image_checkpoint": "sbcp_gym-2"},
                    "dlane": {"mode": "gate"}, "architect": {"agenda_locked": "an agenda"}}
        (self.root / "swarm.json").write_text(json.dumps(settings))
        self.ago(0.5)
        self.store.event("swarm.status", None, {"action": "agenda_guard", "alert": True, "text": "the agenda guard"})
        alerts = self.check("swarm_alerts", now=NOW + 0.5 * HOUR)
        self.assertEqual((alerts["stalled"], alerts["owner_step"], alerts["numbers"]["cleared_kinds"]), (False, None, 1))
        # The state readers, pure.
        from league.swarm import settings as SS

        loaded = SS.load(self.root, config={})
        loaded["gym"]["train_from"] = "2022-01-03"
        facts = {"latest": {}, "kv": {"train_objective": "worst-train-year-v1@2020-01-02", "game_t0": None}}
        states = ST.alert_states(loaded, facts, NOW)
        self.assertTrue(states["train_span_pending"]["stands"], "gym.train_from asks 2022 while the swarm runs 2020")
        self.assertFalse(states["reader_cut"]["stands"])
        loaded["_policy"] = {"state": "ok", "ignored": ["enabled"]}
        self.assertTrue(ST.alert_states(loaded, facts, NOW)["policy_layer"]["stands"])
        from league.swarm import game

        self.assertEqual((ST.GAME_T0_KEY, ST.GAME_SEEN_FROM, ST.GAME_HIDDEN_END), (game.T0_KEY, game.SEEN_FROM, game.HIDDEN[1]))
        # The learning game waits (on, no T0, the running span shows its hidden years) as `game.cfg` reads it.
        loaded["game"] = {"enabled": True, "seen_from": "2019-01-01"}
        self.assertTrue(ST.alert_states(loaded, facts, NOW)["game_waits"]["stands"], "a seen span in the hidden years: 2022")
        self.assertIn("set gym.train_from to 2022-01-03", ST.alert_states(loaded, facts, NOW)["game_waits"]["text"])
        self.assertFalse(ST.alert_states(loaded, {**facts, "kv": {**facts["kv"], "game_t0": "2026-10-01T00:00:00Z"}},
                                         NOW)["game_waits"]["stands"], "after T0 it is the void, not the wait")
        loaded["game"]["enabled"] = "yes"
        self.assertFalse(ST.alert_states(loaded, facts, NOW)["game_waits"]["stands"], "a malformed switch is off")

    def test_swarm_alerts_reach_the_owner(self):
        """Oct 9, 20:32Z: the Sail reviewer cut 4 of 6 gate reviews and a lineage's one try was lost; the `reader_cut`
        alert ("Raise gate.review_max_output_tokens") reached the ledger only, and the captain found it by hand."""
        self.healthy()
        self.ago(3)
        self.store.event("swarm.status", "fam-1", {"action": "reader_cut", "alert": True, "stage": "review",
                                                   "text": "the review of fam-1 v3 was cut short at 6000 output tokens 6 times "
                                                           "today: Raise gate.review_max_output_tokens in swarm.json"})
        self.ago(2)
        self.store.event("swarm.status", None, {"action": "sail_window_stall", "alert": True, "text": "x"})
        self.store.event("swarm.status", None, {"action": "sail_window_stall", "alert": True, "text": "y"})
        self.store.event("swarm.status", None, {"action": "heartbeat_note", "text": "not an alert"})
        self.ago(13)
        self.store.event("swarm.status", None, {"action": "agenda_guard", "alert": True, "text": "too old"})
        out, _ = self.run_at()
        alerts = out["checks"]["swarm_alerts"]
        self.assertTrue(alerts["stalled"])
        self.assertEqual(alerts["owner_step"], ST.ALERT_STEPS["reader_cut"])
        self.assertEqual(alerts["numbers"], {"alert_kinds": 2, "sail_window_stall": 2, "reader_cut": 1, "standing_kinds": 1,
                                             "owner_kinds": 1, "cleared_kinds": 0})
        self.assertIn("reader_cut x1 (last 2026-10-07T07:20:00Z): the review of fam-1 v3 was cut short", alerts["what"])
        self.assertEqual(self.notify.entry("swarm_alerts")["owner_step"], ST.ALERT_STEPS["reader_cut"])

    def test_swarm_alerts_the_self_healing_ones_alone_are_no_cause_and_an_info_kind_has_no_step(self):
        self.healthy()
        self.ago(1)
        self.store.event("swarm.status", None, {"action": "sail_window_stall", "alert": True, "text": "x"})
        self.assertFalse(self.check("swarm_alerts")["stalled"])
        self.store.event("swarm.status", "f", {"action": "incubator_reruns_spent", "alert": True, "text": "spent"})
        info = self.check("swarm_alerts")
        self.assertTrue(info["stalled"])
        self.assertIsNone(info["owner_step"])
        self.store.event("swarm.status", None, {"action": "Gym Unavailable!", "alert": True, "text": "boxes"})
        self.assertIn("gym_unavailable_", self.check("swarm_alerts")["numbers"])

    def budget(self, sail=20.0, claude=5.0, *, day="2026-10-07", raised=None):
        meters = {}
        for meter, usd in (("sail", sail), ("claude", claude)):
            figure = {"day": day, "usd_day": usd, "limited_by": "ceiling", "set_at": "2026-10-07T00:30:00Z"}
            if raised and meter == "sail":
                figure.update(raised)
            meters[meter] = {"research_usd_day": usd, "day_figure": figure}
        (self.root / "budget.json").write_text(json.dumps({"at": NOW - HOUR, "meters": meters}))

    def spend(self, kind, usd, hours):
        self.ago(hours)
        self.store.add_spend(kind, usd)

    def test_underspend_names_the_settings_that_bind_research(self):
        """Oct 9, 16:55Z: swarm.json pinned gym.max_boxes 2 under the budget's 7: half the paid Gym sat idle, and nothing
        alarmed (DONE-RULE item 7 reads a day with no taper as at budget)."""
        self.healthy()
        self.budget()
        self.spend("gym_box", 2.0, 8)
        self.spend("sail_model", 1.5, 4)
        self.spend("claude", 3.0, 2)
        self.spend("sail_model", 9.0, 30)  # yesterday's
        binds = [{"kind": "cap", "text": "gym.max_boxes 2 < 7 the budget buys"},
                 {"kind": "drift", "text": "researcher.dormant_cycles 6 < the release's 12"}]
        out, _ = self.run_at(binds=binds)
        check = out["checks"]["underspend"]
        self.assertTrue(check["stalled"])
        due = round(20.0 * (10 + 20 / 60) / 24, 2)
        self.assertEqual((check["numbers"]["sail_booked_today"], check["numbers"]["sail_due_by_now"]), (3.5, due))
        self.assertIn(f"Sail research booked 3.50 of the {due:.2f} its 20.00 a day buys by now (41%)", check["what"])
        self.assertIn("Settings tighter than what the budget buys: gym.max_boxes 2 < 7 the budget buys.", check["what"])
        self.assertIn("Settings under the release's own values: researcher.dormant_cycles 6 < the release's 12",
                      check["what"])
        self.assertEqual(check["numbers"]["claude_share"], 1.39, "Claude books what it buys")
        self.assertIsNone(check["owner_step"])
        # Booked at pace, no conflict: no cause. A day the guard braked two hours: the spend is the guard's doing.
        self.spend("gym_box", 5.0, 1)
        self.assertFalse(self.check("underspend", binds=binds)["stalled"])

    def test_underspend_reads_the_day_once_six_hours_in_and_a_raise_from_its_hour(self):
        self.healthy()
        self.spend("sail_model", 1.0, 2)
        self.budget()
        early = self.check("underspend", now=at("2026-10-07T05:00:00Z"))
        self.assertFalse(early["stalled"], "under six hours of the day")
        # A top-up raise at 09:00Z from 8 to 20: what is due by 10:20Z is 9 h at 8 and 1 h 20 at 20.
        self.budget(raised={"raised_from": 8.0, "raised_at": "2026-10-07T09:00:00Z"})
        check = self.check("underspend")
        self.assertEqual(check["numbers"]["sail_due_by_now"], round((8.0 * 9 + 20.0 * (80 / 60)) / 24, 2))
        # Yesterday's figure (no run of today yet) is not read.
        self.budget(day="2026-10-06")
        self.assertNotIn("sail_share", self.check("underspend")["numbers"])

    def test_underspend_a_conflict_stands_by_itself_only_while_it_binds(self):
        """The review of the no-captain build: the release's own settings are a class-cap pair (12 x 1 < 24), so a
        conflict that stood by itself stood at every run, and the 24-hour INFO pace then held every new INFO cause back
        up to a day. The class cap stands by itself only while the architect's passes meet it (`lane_class_capped`);
        an architect line no call can use, always."""
        self.healthy()
        conflict = {"kind": "conflict", "key": "class_cap",
                    "text": "architect.max_alive_per_class 16 x 1 direction class (long_single x etf) < dlane.max_alive 24"}
        check = self.check("underspend", binds=[conflict])
        self.assertFalse(check["stalled"], "the class cap has not met a direction card")
        self.assertIn("(not binding now: no direction card met the class cap in the last 6 h)", check["what"])
        self.assertEqual((check["numbers"]["conflicts"], check["numbers"]["conflicts_binding"]), (1, 0))
        self.architect(2.0, proposed=6, born=0, lane_class_capped={"cards": 3, "full": ["long_single x etf"]})
        check = self.check("underspend", binds=[conflict])
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["lane_class_capped_6h"], check["numbers"]["conflicts_binding"]), (3, 1))
        self.assertIn("Settings that cannot both hold: architect.max_alive_per_class 16 x 1", check["what"])
        self.assertNotIn("not binding now", check["what"])
        line = {"kind": "conflict", "key": "architect_line", "text": "claude.role_usd_day.architect 1.50 < the 2.00"}
        self.ago(0)
        self.assertTrue(self.check("underspend", binds=[line], now=NOW + 7 * HOUR)["stalled"], "a line no call can use")

    def test_underspend_a_brake_of_two_hours_is_the_guards_doing_and_claude_is_not_paced(self):
        """The guard's brake of the day (`UNDERSPEND_BRAKE_HOURS`) explains a short day; Claude's figure is spent by its
        roles' calls as work comes (the release sets the architect's and the researchers' lines to 0): said, never a
        cause by itself (Oct 9, 01:58Z: the captain found Claude's meter far under its line on a normal day)."""
        self.healthy()
        self.budget()
        self.spend("gym_box", 2.0, 8)
        self.spend("claude", 0.5, 2)
        lines = [{"kind": "line", "text": "claude.role_usd_day is 0 for architect, researcher"}]
        check = self.check("underspend", binds=lines)
        self.assertTrue(check["stalled"], "Sail booked 2.00 of 8.61 with no brake")
        self.assertIn("Claude (Anthropic) research booked 0.50 of the 2.15 its 5.00 a day buys by now (23%) (not paced: "
                      "its calls come with the gate's and the strategist's work; claude.role_usd_day is 0 for architect, "
                      "researcher)", check["what"])
        # A brake from 05:20Z to 07:50Z today: 2.5 h, the guard's doing.
        self.ago(5)
        self.store.event("swarm.guard", None, {"action": "brake", "causes": ["research_budget"]})
        self.ago(2.5)
        self.store.event("swarm.guard", None, {"action": "release", "causes": []})
        check = self.check("underspend", binds=lines)
        self.assertFalse(check["stalled"], "2.5 h braked today: the guard's doing")
        self.assertEqual(check["numbers"]["braked_hours_today"], 2.5)
        self.assertIn("but the guard braked 2.5 h today.", check["what"])
        # No brake and Sail at pace: Claude's short day alone is no cause.
        budget = json.loads((self.root / "budget.json").read_text())
        swarm = {"spent_today": {"sail": 8.0, "claude": 0.5}, "day_start": at("2026-10-07T00:00:00Z"),
                 "brake_today": {"hours": 0.0}}
        check = ST._underspend_check(NOW, swarm, budget, lines)
        self.assertEqual((check["stalled"], check["numbers"]["sail_share"], check["numbers"]["claude_share"]),
                         (False, 0.93, 0.23))
        self.assertIn("Claude (Anthropic) research booked 0.50", check["what"])

    def test_underspend_reads_the_swarms_own_settings_when_no_binds_are_handed_in(self):
        """The real read (`_binds`: the settings as the swarm loads them, the release's policy.json among them): the
        release's class-cap pair is named and does not stand by itself; a swarm.json cap under what the budget buys is
        named as a cap."""
        from unittest import mock

        from league.ops import budget as B
        from league.swarm import settings as SS
        from league.tests import REAL_POLICY_PATH

        patch = mock.patch.object(SS, "POLICY_PATH", REAL_POLICY_PATH)
        patch.start()
        self.addCleanup(patch.stop)
        self.healthy()
        doc = B.compute({"p30_usd": 0.0, "p30_source": "test", "edge": {"stop": False},
                         "meters": {"sail": {"balance_usd": 900.0, "fixed_usd_day": 1.0, "need_usd": 0.0},
                                    "claude": {"balance_usd": 200.0, "fixed_usd_day": 0.0, "need_usd": 0.0}}},
                        now=at("2026-10-07T00:30:00Z"))
        doc["at"] = NOW - HOUR
        (self.root / "budget.json").write_text(json.dumps(doc))
        self.spend("gym_box", 8.0, 2)
        ctx = self.ctx()
        del ctx.binds
        out = ST.run(ctx)
        check = out["checks"]["underspend"]
        self.assertEqual(out["errors"], [])
        self.assertFalse(check["stalled"], "Sail at pace; the release's class-cap pair does not bind")
        self.assertIn("architect.max_alive_per_class 12 x 1 direction class (long_single x etf) < dlane.max_alive 24",
                      check["what"])
        self.assertIn("(not binding now", check["what"])
        self.assertIn("claude.role_usd_day is 0 for architect, diagnostician, researcher, rewrite", check["what"])
        self.assertEqual(check["numbers"]["under_release"], 0, "the release's own dormancy and refill are no drift")
        # swarm.json is read: a class cap that holds the lane is no conflict; a dormancy under the release's is drift.
        (self.root / "swarm.json").write_text(json.dumps({"architect": {"max_alive_per_class": 24},
                                                          "researcher": {"dormant_cycles": 6}}))
        ctx = self.ctx()
        del ctx.binds
        check = ST.run(ctx)["checks"]["underspend"]
        self.assertEqual((check["numbers"]["conflicts"], check["numbers"]["under_release"]), (0, 1))
        self.assertIn("researcher.dormant_cycles 6 < the release's 12", check["what"])

    def test_underspend_prices_each_hour_at_the_figure_that_held_then(self):
        """Two raises in a day (the hourly refresh raises each time a reading rises): the hours before the first at the
        day's first figure, not at the middle one (the review of the no-captain build)."""
        figure = {"day": "2026-10-07", "usd_day": 20.0, "raised_from": 17.5, "raised_at": "2026-10-07T10:00:00Z",
                  "set_usd_day": 12.5, "raises": [{"at": "2026-10-07T09:00:00Z", "from": 12.5, "to": 17.5},
                                                  {"at": "2026-10-07T10:00:00Z", "from": 17.5, "to": 20.0}]}
        day = at("2026-10-07T00:00:00Z")
        self.assertAlmostEqual(ST._expected(20.0, figure, day, NOW), (12.5 * 9 + 17.5 * 1 + 20.0 * 20 / 60) / 24)
        last_only = {k: v for k, v in figure.items() if k not in ("raises", "set_usd_day")}
        self.assertAlmostEqual(ST._expected(20.0, last_only, day, NOW), (17.5 * 10 + 20.0 * 20 / 60) / 24, msg="one step")
        self.assertAlmostEqual(ST._expected(20.0, {}, day, NOW), 20.0 * (10 + 20 / 60) / 24)

    def test_the_settings_that_bind_research(self):
        import copy
        from unittest import mock

        from league.ops import budget as B
        from league.swarm import settings as SS
        from league.tests import REAL_POLICY_PATH

        patch = mock.patch.object(SS, "POLICY_PATH", REAL_POLICY_PATH)  # the release's own policy.json (drift reads it)
        patch.start()
        self.addCleanup(patch.stop)

        loaded = copy.deepcopy(SS.DEFAULTS)
        loaded["budget"] = {"knobs": B.knobs(20.0, 5.0)}
        loaded["population"].update(start=25, ceiling=25)  # as the budget's overlay leaves them at $25 a day
        loaded["architect"]["every_seconds"] = 2880
        loaded["gym"]["max_boxes"] = 7
        self.assertEqual(ST.settings_binds(loaded), [])
        loaded["gym"]["max_boxes"] = 2
        loaded["population"].update(start=16, ceiling=25)
        loaded["architect"].update(max_alive_per_class=16, every_seconds=7200, max_refill=3)
        loaded["researcher"]["dormant_cycles"] = 6
        loaded["claude"]["role_usd_day"] = {"architect": 1.5, "researcher": 0, "rewrite": 0}
        loaded["dlane"] = {"mode": "gate", "roots": ["SPY", "QQQ", "IWM"], "structures": ["long_single"], "max_alive": 24}
        found = ST.settings_binds(loaded)
        self.assertEqual([b["kind"] for b in found], ["cap", "cap", "cap", "conflict", "conflict", "drift", "drift", "line"])
        self.assertEqual([b.get("key") for b in found if b["kind"] == "conflict"], ["class_cap", "architect_line"])
        texts = " | ".join(b["text"] for b in found)
        for part in ("gym.max_boxes 2 < 7 the budget buys", "architect.every_seconds 7200 > 2880 the budget buys",
                     "population.start 16 < population.ceiling 25",
                     "architect.max_alive_per_class 16 x 1 direction class (long_single x etf) < dlane.max_alive 24",
                     "claude.role_usd_day.architect 1.50 < the 2.00 one architect call holds",
                     "researcher.dormant_cycles 6 < the release's 12", "architect.max_refill 3 < the release's 6",
                     "claude.role_usd_day is 0 for researcher, rewrite"):
            self.assertIn(part, texts)
        # DRIFT IS AGAINST THE RELEASE (the review of the no-captain build): policy.json itself sets dormancy 12 and a
        # refill of 6, so those are no drift; against the code's DEFAULTS alone (a release with no policy layer) they are.
        release = ST.release_settings()
        self.assertEqual((release["researcher"]["dormant_cycles"], release["architect"]["max_refill"]), (12, 6))
        loaded["researcher"]["dormant_cycles"], loaded["architect"]["max_refill"] = 12, 6
        self.assertNotIn("drift", [b["kind"] for b in ST.settings_binds(loaded)])
        self.assertEqual([b["text"] for b in ST.settings_binds(loaded, SS.DEFAULTS) if b["kind"] == "drift"],
                         ["researcher.dormant_cycles 12 < the release's 40", "architect.max_refill 6 < the release's 12"])
        # A class cap that holds the lane, a line of 0 or of a full hold, and the lane off: no conflict.
        loaded["architect"]["max_alive_per_class"] = 24
        loaded["claude"]["role_usd_day"] = {"architect": 0}
        self.assertNotIn("conflict", [b["kind"] for b in ST.settings_binds(loaded)])
        loaded["architect"]["max_alive_per_class"] = 8
        loaded["dlane"]["mode"] = "off"
        self.assertNotIn("conflict", [b["kind"] for b in ST.settings_binds(loaded)])
        self.assertEqual(ST.settings_binds(None), [])


class Wiring(Base):
    def test_registered_every_half_hour_round_the_clock_in_a_pause_too_and_unpaid(self):
        job = by_name()["stall"]
        self.assertEqual(job.module, "league.ops.stall")
        self.assertEqual(sorted((t.kind, t.minute) for t in job.triggers), [("hourly", 20), ("hourly", 50)])
        self.assertTrue(job.in_pause, "read-only like preopen and clock: a pause left on is itself reported")
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
        self.assertEqual(day["validations"], {"judged": 2, "passed": 1, "entered": 1, "by_screen": {}})  # M5's two keys
        self.assertEqual(day["looks"], {"taken": 2, "passed": 1})
        self.assertEqual(day["band_moves"], {"candidate": 1, "probe": 1, "sized": 0})
        self.assertEqual(day["spend_usd"], {"sail": 0.75, "claude": 2.0, "openai": 0.0})
        self.assertEqual(day["braked"]["hours"], 3.0)
        self.assertEqual(day["book"], {"orders": {"agent": 2, "house": 1}, "filled": {"agent": 1, "house": 1},
                                       "closes": {"agent": 1, "house": 1}})
        longer = FN.window(self.root, NOW - 48 * HOUR, NOW)
        self.assertEqual((longer["births"], longer["versions"], longer["spend_usd"]["sail"]), (2, 3, 1.75))
        self.assertEqual((longer["book"]["orders"]["agent"], longer["book"]["closes"]["agent"]), (3, 2))

    def test_rows_with_no_trial_are_counted_apart_never_as_gym_runs(self):
        fid = self.family("twin")
        self.ago(2)
        for i, (status, trials) in enumerate((("ok", 1), ("ok", 0), ("ok", 0), ("refused", 0))):
            self.store.add_run(fid, 1, {"run_id": f"v{i}", "status": status, "trials": trials}, window="validation", stress=1.0,
                               purpose="validation", prune=False)
        day = FN.window(self.root, NOW - 24 * HOUR, NOW)
        self.assertEqual((day["gym_runs"]["validation"], day["gym_no_trial"], day["gym_not_run"], day["gym_runs_total"]),
                         (1, 2, 1, 1))
        self.assertIn("| Rows copied from an identical program's verdict (no Gym run) | 2 | n/a |",
                      self.page(FN.read(self.root, self.base, "r9", NOW)))

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
