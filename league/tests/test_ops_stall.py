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
        self.assertEqual((facts["kind"], facts["notice_id"]), ("stall", "stall:info"))
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

    def report(self, *alarms, at="2026-10-07T01:30:00Z", k5=None, mode="gate"):
        doc = {"at": at, "lane": {"mode": mode}, "k5": k5 or {"tripped": False, "cleared": False}, "alarms": list(alarms)}
        (self.root / "dlane-report.json").write_text(json.dumps(doc))

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
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info")

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
        self.report({"id": "A8", "level": "info", "meter": "done_screen", "at_close": 30, "text": "A8: Done criteria hold"})
        out = self.run_lane()
        self.assertEqual(out["stalled"], ["done"])
        self.assertIn("done_screen at close 30", out["checks"]["done"]["owner_step"])
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:owner:done")
        self.assertEqual(self.notify.entry("done")["numbers"]["checkpoints"], "done_screen:30")
        # The next day's report no longer carries it (A8 is said once): the cause clears.
        self.report()
        self.assertEqual(self.run_lane(now=NOW + HOUR)["cleared"], ["done"])

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
        for cause in ("dlane", "done", "preopen", "forward"):
            self.assertIn(cause, ST.CAUSES)
            self.assertIn(f"  {cause}: '", source)


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
