"""Release E3's seal T10, `TheJudgesDidNotMove` (the spec's section 10): E3 records and measures only, so no identity a
judge binds to may move for it. No E3 file lies in a tree or a list an identity hashes; the options execution
fingerprint and the equity evidence fingerprint read no E3 file (shown on a copy: every E3 file changed, both digests
the same); the equity evidence's import closure is A13's, with nothing of E3 in it; no decider kind was added and the
child's runtime carries no E3 file; the constitution is the pinned one; every E3 file that is code or a declaration is
behind the updater's wall, and no role may change any E3 file; the forward screen's shape is the literal the spec
pre-registered (`FGS_SHA`); and every E3 switch is off in code.

`TheWiringIsWhole` holds the three edits of existing files this release makes for its jobs and settings (the spec's
11.1-11.3: six jobs in league/ops/registry.py, three blocks in league/swarm/policy.json, three paths behind the wall
in league/ci.py) to the spec's tables, and to each other: all three applied, or none of them (the base the packages
were built on). A release with its jobs registered and its settings missing, or its modules unprotected, fails here.
The three paths are in the gateway's merge list too (gateway/lib/protected.mjs `MERGE_FORBIDDEN`, the one list of
gateway/ the release changes: its gateway follow-up, made with it), so nothing of E3's waits in `ci.PENDING_GATEWAY`.
What waits there since release E4 was merged over E3 is E4's own two (`E4_PENDING`), until the gateway's next
follow-up; and E4's six data jobs go after E3's six in the registry, last.

`TheDeclaredReceipts` holds the release's declared receipts (the spec's 7.6: the file league/ops/release_receipts.py
`DECLARATIONS` names) to the spec's text: two receipts, each a count the funnel's `forward_record` carries, read back
after a week."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from league import ci, constitution
from league.equity import kinds, results
from league.gym.driver import LEAGUE_FILES
from league.ops import contam_probe, forward_db, forward_report, registry, release_receipts
from league.ops import schedule as S
from league.swarm import elane_folds, evaluator
from league.swarm.evaluator import (EQUITY_EVIDENCE, EQUITY_GYM_FILES, equity_fingerprint, execution_fingerprint)
from league.tests import REAL_POLICY_PATH
from league.tests import test_equity_identity as A13

REPO = Path(__file__).resolve().parents[2]
HOUR, MINUTE = 3600, 60

#: EVERY FILE THE EQUITY IDENTITY HASHES (league/swarm/evaluator.py `equity_fingerprint`): the evidence modules, the
#: league's own files, the Gym modules the evidence imports and, on a base that lists them (E1's follow-up after step
#: 0), the calendar's files outside league/. Read from the evaluator's own lists, so the seal holds on either base.
EQUITY_HASHED = (*(f"league/equity/{name}.py" for name in EQUITY_EVIDENCE), *LEAGUE_FILES, *EQUITY_GYM_FILES,
                 *getattr(evaluator, "EQUITY_CALENDAR_FILES", ()))
#: Release E3's NEW files that are not tests (league/ops/E3_INTERFACES.md, the ownership map).
E3_OPS = tuple(f"league/ops/{name}.py" for name in (
    "forward_db", "forward_register", "forward_controls", "forward_shadow", "forward_audit", "forward_stats",
    "forward_report", "release_receipts", "fill_minutes", "forward_twins", "contam_probe"))
E3_SWARM = ("league/swarm/elane_folds.py", "league/swarm/elane_effects.py", "league/swarm/elane_memory.py")
#: The release's declared receipts, where the module that reads them looks (league/ops/release_receipts.py).
DECLARATIONS = release_receipts.DECLARATIONS
E3_NEW = (*E3_OPS, "league/ops/E3_INTERFACES.md", *E3_SWARM, DECLARATIONS)
#: The existing files the release edits (the spec's section 11).
E3_PATCHED = ("league/ops/registry.py", "league/swarm/policy.json", "league/ci.py", "league/ops/funnel.py",
              "league/ops/dlane_report.py", "league/ops/stall.py", "league/swarm/elane_train.py",
              "league/swarm/elane_births.py", "league/swarm/elane_seal.py", "docs/operations.md", "CHANGELOG.md")
#: The one E3 path that is documentation and nothing else: no judge, no wall.
DOCUMENTATION = ("docs/operations.md",)
#: What may not be edited at all (the spec's hard rules): trees and files. Of gateway/ the release changes one list
#: and nothing else: `GATEWAY_LIST`'s MERGE_FORBIDDEN gains the three swarm modules (`TheWiringIsWhole`).
UNTOUCHED = ("league/equity/", "league/live/", "league/gym/", "gateway/", "league/constitution.py", *LEAGUE_FILES)
#: The gateway's merge list (its `MERGE_FORBIDDEN`): no identity hashes it and no House process reads it.
GATEWAY_LIST = "gateway/lib/protected.mjs"

#: THE WIRING, as the spec writes it. 8.1: name -> (triggers, grace, cpu, wall, in_pause, paid, retry, owner).
E3_JOBS = {
    "forward_register": ((S.at_start(), S.hourly(25)), 70 * MINUTE, 120, 300, True, False, True, "E3 forward record"),
    "fill_minutes": ((S.at_start(), S.session_close(45)), 3 * HOUR, 120, 300, True, False, True, "E3 forward record"),
    "forward_shadow": ((S.after("equity_data"),), 3 * HOUR, 2700, 3300, True, False, True, "E3 forward record"),
    "forward_report": ((S.after("forward_shadow"), S.session_open(-35)), 3 * HOUR, 300, 600, True, False, True,
                       "E3 forward record"),
    "forward_audit": ((S.session_open(-25),), 40 * MINUTE, 120, 300, True, False, True, "E3 forward record"),
    "contam_probe": ((S.weekly(5, 0, 10),), 6 * HOUR, 300, 3300, False, True, False, "E3 contamination"),
}
#: Section 5's policy.json column: the three blocks inside `elane`, after `e2`.
E3_POLICY = {
    "forward": {"mode": "record", "controls_per_group": 50, "cpu_seconds_night": 1800, "run_budget_seconds": 120,
                "stop_after_sessions": 500, "stop_fail_after_sessions": 250, "neff_max_members": 1500,
                "fill_minutes": True, "twins": True},
    "memory": {"mode": "record"},
    "contam": {"mode": "record", "usd_run": 3.0, "every_days": 28, "batch": 20, "questions_per_cell": 120},
}
#: Section 10: what waited for the gateway's merge list before E3 (release E2's five, in that list since the gateway's
#: follow-up of Oct 11, 2026); E3's three (`E3_SWARM`) joined it with the release.
E2_PENDING = ("league/swarm/elane_births.py", "league/swarm/elane_train.py", "league/swarm/elane_yield.py",
              "league/swarm/elane_seal.py", "league/swarm/elane_review.py")
#: What waits for the gateway's merge list on a tree that carries release E4 (league/ci.py `PENDING_GATEWAY`): the
#: panel's swarm lane and the universe generator. Not E3's: named here so that nothing else is let in beside them.
E4_PENDING = ("league/swarm/elane_xs.py", "scripts/gen_universe.py")
#: FWD1-R's seat path in the swarm (the captain's A33), waiting beside release E4's two for the gateway's follow-up.
FWD1_PENDING = ("league/swarm/elane_forward.py",)
#: Release R0's data plan (league/data_plan.py, Oct 19, 2026: the Basic plan's rules for every market-data read),
#: waiting beside them.
R0_PENDING = ("league/data_plan.py",)
#: Release R1's event-lane judges (league/events/{programs,verdicts,score,screen}.py and docs/prereg/), waiting beside
#: them.
R1_PENDING = ("league/events/programs.py", "league/events/verdicts.py", "league/events/score.py",
              "league/events/screen.py", "docs/prereg/")
#: PREREG-EVL-3's band rules (league/events/bands.py, release 1019b), beside them.
V2_PENDING = ("league/events/bands.py",)
#: Release R2's event kind (league/events/book.py, the rules; league/events/proof.py, the auction paper proof), beside
#: them.
R2_PENDING = ("league/events/book.py", "league/events/proof.py")
#: The event lane's rule inputs (release 1019b's review: eligibility and the benchmark, the windows and decision times,
#: the knowable lag, which program gets which rows, the record's schema), beside them.
LANE_PENDING = ("league/events/universe.py", "league/events/calendar.py", "league/events/edgar.py",
                "league/events/news.py", "league/events/run.py", "league/events/store.py")
#: Release 1019c's verdict line (the lane's House scheduler, which holds its verdicts to the budget's allowance), beside them.
LINE_PENDING = ("league/events/house.py",)
#: The forward screen's shape as the spec's section 4 writes it, and its sha.
FGS_LITERAL = {
    "version": "fgs-prereg-1", "stat": "t_r over the first n counted days", "n": [20, 60, 120, 250], "then_every": 250,
    "pass": "t_r >= c_F and sum_r > 0 and sum_r15 > 0", "row": "the first fwd_checks row written for (pid, n)",
    "null": "N0", "block_sessions": 21, "worlds": 20000, "pools": ["IND22", "IND1622"],
    "c_F": "the smallest c whose pass rate at ANY of the four checkpoints under the null is <= alpha_f, the maximum "
           "over the pools",
    "alpha_e3_rows": "0.03", "alpha_fresh_route_F": "0.12"}
FGS_LITERAL_SHA = "c1eaf140a42c4a5968c60990c514c43fd92c182f6c315ddfb8841d366959e4f1"
#: The release's declared receipts as the spec's 7.6 writes them.
RECEIPTS_LITERAL = {"schema": 1, "receipts": [
    {"id": "E3-forward", "release": "E3", "metric": "forward_record.program_sessions", "direction": "up", "min_delta": 1,
     "window_hours": 168,
     "why": "the forward record accrues program-sessions (a week: the first row of a Thursday or Friday deploy lands "
            "after the weekend)"},
    {"id": "E3-oof", "release": "E3", "metric": "forward_record.oof_rows", "direction": "up", "min_delta": 1,
     "window_hours": 168,
     "why": "every scored version of a hidden-year family leaves an OOF row; it needs equity births on "
            "(elane.birth_share above 0 with elane.mode gate), else it reads flat"}]}


def policy_elane() -> dict:
    """The committed policy.json's `elane` block (the House's; never the empty layer the tests load)."""
    return json.loads(Path(REAL_POLICY_PATH).read_text(encoding="utf-8"))["elane"]


def merge_forbidden() -> set[str]:
    """The gateway's `MERGE_FORBIDDEN`, read off its file as league/tests/test_ci.py reads it (comments dropped)."""
    source = (REPO / GATEWAY_LIST).read_text(encoding="utf-8")
    block = re.search(r"MERGE_FORBIDDEN = Object\.freeze\(\[([\s\S]*?)\]\);", source)
    return set(re.findall(r"'([^']+)'", re.sub(r"//[^\n]*", "", block.group(1)))) if block else set()


def under(path: str, entries) -> bool:
    return any(path == entry or (entry.endswith("/") and path.startswith(entry)) for entry in entries)


class TheJudgesDidNotMove(unittest.TestCase):
    """T10 (the spec's section 9)."""

    def tearDown(self):
        equity_fingerprint.cache_clear()
        execution_fingerprint.cache_clear()

    def test_every_new_file_exists_and_none_lies_where_an_identity_reads(self):
        hashed = set(EQUITY_HASHED)
        for path in (*E3_NEW, *E3_PATCHED):
            self.assertTrue((REPO / path).is_file(), path)
            self.assertFalse(under(path, UNTOUCHED), f"{path} lies where release E3 edits nothing")
            self.assertNotIn(path, hashed)
            self.assertFalse(path.startswith(("league/gym/", "league/live/", "league/equity/", "ltcm/")), path)

    def test_the_fingerprints_read_no_e3_file(self):
        # On a copy: the files both identities hash, and every E3 file beside them. Each E3 file is then changed.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in (*EQUITY_HASHED, "league/gym/engine.py", "league/live/step.py", "league/live/decider.py",
                         *E3_NEW, *E3_PATCHED):
                A13.write(repo, name)
            options, equity = execution_fingerprint(repo), equity_fingerprint(repo)
            for name in (*E3_NEW, *E3_PATCHED):
                A13.write(repo, name, "VALUE = 2  # release E3\n")
                execution_fingerprint.cache_clear()
                equity_fingerprint.cache_clear()
                self.assertEqual(execution_fingerprint(repo), options, f"{name} moved the options identity")
                self.assertEqual(equity_fingerprint(repo), equity, f"{name} moved the equity identity")
            # The copy does tell a change: a file an identity hashes moves it.
            A13.write(repo, "league/equity/engine.py", "VALUE = 3\n")
            A13.write(repo, "league/live/step.py", "VALUE = 3\n")
            execution_fingerprint.cache_clear()
            equity_fingerprint.cache_clear()
            self.assertNotEqual(equity_fingerprint(repo), equity)
            self.assertNotEqual(execution_fingerprint(repo), options)

    def test_the_real_fingerprints_hash_exactly_the_files_they_always_did(self):
        files = sorted(set(EQUITY_HASHED))
        self.assertEqual(len(files), len(EQUITY_HASHED))
        digest = hashlib.sha256()
        for name in files:
            digest.update(name.encode() + b"\0" + (REPO / name).read_bytes() + b"\0")
        equity_fingerprint.cache_clear()
        self.assertEqual(equity_fingerprint(), digest.hexdigest())
        self.assertEqual(forward_db.fwd_engine().split("+")[1], digest.hexdigest()[:12],
                         "the forward engine label carries that same identity")
        options = sorted({*(REPO / name for name in LEAGUE_FILES), *(REPO / "league" / "gym").rglob("*.py"),
                          *(REPO / "league" / "live").rglob("*.py")})
        digest = hashlib.sha256()
        for path in options:
            digest.update(path.relative_to(REPO).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        execution_fingerprint.cache_clear()
        self.assertEqual(execution_fingerprint(), digest.hexdigest())
        self.assertFalse({p.relative_to(REPO).as_posix() for p in options} & {*E3_NEW, *E3_PATCHED})

    def test_nothing_of_e3_is_in_the_evidence_import_closure(self):
        """A13: the evidence modules' import closure is what it was, and A13's own closure test still passes."""
        closure = A13.evidence_closure(EQUITY_EVIDENCE)
        self.assertFalse(closure & {*E3_NEW, *E3_PATCHED}, "an evidence module came to import a file of release E3")
        self.assertFalse({f for f in closure if f.startswith(("league/ops/", "league/swarm/"))},
                         "the evidence reaches neither ops nor the swarm")
        inside = {Path(f).stem for f in A13.evidence_closure() if f.startswith("league/equity/")}
        self.assertEqual(inside | {"synth"}, set(EQUITY_EVIDENCE))
        A13.Boundaries("test_the_evidence_list_is_the_import_closure_of_the_runner_the_child_the_screen_and_the_engine"
                       ).debug()

    def test_no_decider_kind_was_added_and_the_childs_runtime_carries_no_e3_file(self):
        self.assertEqual(kinds.KINDS, {"equity": "league.equity.child", "panel": "league.xs.child"})
        runtime = set(kinds.runtime_files(REPO))
        self.assertTrue(runtime)
        self.assertFalse(runtime & {*E3_NEW, *E3_PATCHED})
        self.assertFalse([entry for entry in kinds.RUNTIME if entry.startswith(("league/ops", "league/swarm"))])

    def test_the_constitution_is_the_pinned_one(self):
        self.assertEqual(constitution.digest(), constitution.PINNED_DIGEST)
        self.assertNotIn("league/constitution.py", (*E3_NEW, *E3_PATCHED))
        self.assertTrue(ci.guard(["league/constitution.py"], None))

    def test_no_role_may_change_an_e3_file(self):
        for path in (*E3_NEW, *E3_PATCHED):
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([path], role), (path, role))

    def test_every_e3_file_that_is_code_or_a_declaration_is_behind_the_wall(self):
        # `ci.guard(path, None)` is the wall itself (`FORBIDDEN`, what the updater never self-deploys). The three
        # swarm modules join it with the spec's 11.3 (`TheWiringIsWhole` holds that edit, and the gateway's list).
        waits = () if TheWiringIsWhole.wired() else E3_SWARM
        for path in (*E3_NEW, *E3_PATCHED):
            if path in DOCUMENTATION or path in waits:
                continue
            self.assertTrue(ci.guard([path], None), path)
        for entry in ("league/ops/", "docs/benchmarks/", "league/swarm/policy.json", "CHANGELOG.md"):
            self.assertIn(entry, ci.FORBIDDEN)
        from league.updater import protected_changes

        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            for root, text in ((running, "RULE = 1\n"), (incoming, "RULE = 2\n")):
                for path in E3_OPS:
                    A13.write(root, path, text)
            self.assertEqual([line.split(":")[0] for line in protected_changes(incoming, running)], sorted(E3_OPS),
                             "the updater never self-deploys a change to an E3 ops module")

    def test_the_forward_screens_shape_is_the_literal_the_spec_pre_registered(self):
        self.assertEqual(forward_db.FGS, FGS_LITERAL)
        self.assertEqual(hashlib.sha256(results.canonical(FGS_LITERAL).encode()).hexdigest(), FGS_LITERAL_SHA)
        self.assertEqual(forward_db.FGS_SHA, FGS_LITERAL_SHA)
        self.assertEqual((forward_db.E3_ROUTE, forward_db.E3_ALPHA_F, forward_db.FGS["alpha_e3_rows"]),
                         ("S2", "0.03", "0.03"))
        self.assertEqual(tuple(forward_db.FGS["n"]), forward_db.CHECKPOINTS)

    def test_every_switch_is_off_in_code(self):
        # E3 writes no verdict, gates nothing and moves no money: with no setting at all, none of it runs.
        self.assertEqual((forward_db.DEFAULTS["mode"], contam_probe.DEFAULTS["mode"]), ("off", "off"))
        self.assertEqual((forward_db.mode(None), forward_db.mode({}), forward_db.mode({"elane": {"mode": "gate"}})),
                         ("off", "off", "off"))
        self.assertEqual((forward_db.MODES, elane_folds.MODES), (("off", "record"), ("off", "record")))
        self.assertEqual(elane_folds.FALLBACK["hidden_year"], None)


class TheWiringIsWhole(unittest.TestCase):
    """The spec's 11.1-11.3, held to its tables and to each other."""

    @staticmethod
    def applied() -> dict[str, int]:
        """How many of each edit's parts the tree holds: the six jobs, the three policy blocks, the three walled paths."""
        return {"jobs": sum(1 for name in E3_JOBS if name in registry.by_name()),
                "policy": sum(1 for name in E3_POLICY if name in policy_elane()),
                "wall": sum(1 for path in E3_SWARM if path in ci.FORBIDDEN)}

    @classmethod
    def wired(cls) -> bool:
        return cls.applied() == {"jobs": len(E3_JOBS), "policy": len(E3_POLICY), "wall": len(E3_SWARM)}

    def test_all_three_edits_or_none(self):
        applied = self.applied()
        self.assertIn(applied, ({"jobs": 0, "policy": 0, "wall": 0},
                                {"jobs": len(E3_JOBS), "policy": len(E3_POLICY), "wall": len(E3_SWARM)}),
                      "release E3 is wired whole or not at all: its jobs, its settings and its wall go together")

    def test_the_spec_tables_agree_with_the_code(self):
        # Whatever the tree holds, the tables above are the spec's and the modules' own constants agree with them.
        for name, (triggers, grace, cpu, wall, in_pause, paid, retry, owner) in E3_JOBS.items():
            self.assertTrue((REPO / "league" / "ops" / f"{name}.py").is_file(), name)
            self.assertLessEqual(wall, 3600, "no wall over an hour: the grant's hourly grace waits behind the longest")
            self.assertLess(cpu, wall)
            self.assertNotEqual(in_pause, paid, "a paid job never runs in a pause; the record's jobs all do")
        self.assertEqual({**E3_POLICY["forward"], "mode": "off"}, forward_db.DEFAULTS)
        self.assertEqual({**E3_POLICY["contam"], "mode": "off"}, contam_probe.DEFAULTS)
        self.assertEqual(forward_db.cfg({"elane": E3_POLICY}), E3_POLICY["forward"])
        for key, (low, high) in {**forward_db.BOUNDS, **contam_probe.BOUNDS}.items():
            value = E3_POLICY["forward"].get(key, E3_POLICY["contam"].get(key))
            self.assertTrue(low <= value <= high, key)
        # The shadow's own budget of child seconds fits inside the job's CPU limit, the parent's work beside it.
        self.assertGreaterEqual(E3_JOBS["forward_shadow"][2] - forward_db.BOUNDS["cpu_seconds_night"][1], 300)
        self.assertLess(contam_probe.ASK_SECONDS, E3_JOBS["contam_probe"][3])
        self.assertEqual(S.weekly(5, 0, 10).describe(), "weekly Sat 00:10Z")
        self.assertEqual(set(E2_PENDING) & set(E3_SWARM), set())

    def test_the_six_jobs(self):
        names = [job.name for job in registry.JOBS]
        if not self.wired():
            self.assertFalse(set(E3_JOBS) & set(names))
            self.assertEqual(names[-1], "dlane", "the base: the six rows go after the dlane job")
            return
        # A later release's jobs go after them (release E4's six data jobs: "they go last", league/ops/registry.py).
        self.assertEqual(names[names.index("dlane") + 1:][:len(E3_JOBS)], list(E3_JOBS), "after dlane, in the spec's order")
        jobs = registry.by_name()
        for name, (triggers, grace, cpu, wall, in_pause, paid, retry, owner) in E3_JOBS.items():
            job = jobs[name]
            self.assertEqual((job.module, job.triggers, job.grace, job.cpu, job.wall, job.in_pause, job.paid, job.retry,
                              job.owner), (f"league.ops.{name}", triggers, grace, cpu, wall, in_pause, paid, retry, owner),
                             name)
            self.assertGreater(len(job.what), 40, f"{name} says what it is")
        self.assertLessEqual(max(job.wall for job in registry.JOBS), 3600)
        self.assertGreaterEqual(jobs["grant"].grace, max(job.wall for job in registry.JOBS) + 5 * MINUTE)
        self.assertEqual(len(names), len(set(names)))
        # Each job is its module's `run`, and its trigger names a job that exists.
        import importlib

        for name in E3_JOBS:
            self.assertTrue(callable(importlib.import_module(f"league.ops.{name}").run), name)
        for name in E3_JOBS:
            for trigger in jobs[name].triggers:
                if trigger.kind == "after":
                    self.assertIn(trigger.job, jobs, f"{name} follows a job that exists")
        # The shadow has no clock trigger of its own: it follows the daily store, and the report follows the shadow.
        self.assertEqual([t.kind for t in jobs["forward_shadow"].triggers], ["after"])
        self.assertEqual((jobs["forward_shadow"].triggers[0].job, jobs["forward_report"].triggers[0].job),
                         ("equity_data", "forward_shadow"))

    def test_the_three_policy_blocks(self):
        elane = policy_elane()
        if not self.wired():
            self.assertFalse(set(E3_POLICY) & set(elane))
            self.assertEqual(list(elane)[-1], "e2", "the base: the three blocks go after e2")
            return
        self.assertEqual(list(elane)[list(elane).index("e2") + 1:], list(E3_POLICY), "after e2, in the spec's order")
        for name, block in E3_POLICY.items():
            self.assertEqual(elane[name], block, name)
            self.assertEqual(list(elane[name]), list(block), f"{name}: section 5's keys, in its order")
        # As the House reads them (DEFAULTS under the committed policy; the test package itself reads an empty layer:
        # league/tests/__init__.py): the forward record on, its values the policy's.
        from league.swarm import settings

        loaded = settings.load(config={}, policy=json.loads(Path(REAL_POLICY_PATH).read_text(encoding="utf-8")))
        self.assertEqual(loaded["_policy"]["state"], "ok")
        self.assertEqual(forward_db.cfg(loaded), E3_POLICY["forward"])
        self.assertEqual(forward_db.mode(loaded), "record")
        if _built(contam_probe.cfg):
            self.assertEqual(contam_probe.cfg(loaded), E3_POLICY["contam"])
        self.assertEqual(settings.policy_shape({"elane": dict(elane)}), [], "no settings.py change is needed")

    def test_the_three_paths_behind_the_wall(self):
        # Release E2's five left the waiting list with the gateway's follow-up of Oct 11, 2026, and E3's three never
        # wait there: the gateway's merge list gains them with the release. FORBIDDEN names all eight, or the five.
        # What may wait is release E4's two and, beside them, FWD1-R's seat path, and nothing else (none on a tree
        # without E4).
        gateway = merge_forbidden()
        self.assertIn(ci.PENDING_GATEWAY, ((), E4_PENDING, E4_PENDING + FWD1_PENDING,
                                           E4_PENDING + FWD1_PENDING + R0_PENDING,
                                           E4_PENDING + FWD1_PENDING + R0_PENDING + R1_PENDING,
                                           E4_PENDING + FWD1_PENDING + R0_PENDING + R1_PENDING + V2_PENDING
                                           + R2_PENDING,
                                           E4_PENDING + FWD1_PENDING + R0_PENDING + R1_PENDING + V2_PENDING
                                           + R2_PENDING + LANE_PENDING,
                                           E4_PENDING + FWD1_PENDING + R0_PENDING + R1_PENDING + V2_PENDING
                                           + R2_PENDING + LANE_PENDING + LINE_PENDING),
                      "nothing of E2's or E3's waits for the gateway")
        self.assertFalse(set(ci.PENDING_GATEWAY) & {*E2_PENDING, *E3_SWARM})
        self.assertEqual(set(ci.FORBIDDEN) - gateway, set(ci.PENDING_GATEWAY), "beyond the gateway's list: what waits")
        for path in E2_PENDING:
            self.assertIn(path, ci.FORBIDDEN)
            self.assertIn(path, gateway)
        if not self.wired():
            self.assertFalse(set(E3_SWARM) & (set(ci.FORBIDDEN) | gateway), "the base: neither list names them")
            return
        for path in E3_SWARM:
            self.assertIn(path, ci.FORBIDDEN)
            self.assertIn(path, gateway, "the gateway's merge route refuses it too")
            self.assertTrue(ci.guard([path], None), path)
            self.assertTrue(ci.guard([path.replace("league/swarm", "League/Swarm")], None), "whatever its case")
        from league.updater import protected_changes

        with tempfile.TemporaryDirectory() as tmp:
            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
            for root, text in ((running, "RULE = 1\n"), (incoming, "RULE = 2\n")):
                for path in (*E3_SWARM, "league/swarm/pool.py"):
                    A13.write(root, path, text)
            self.assertEqual([line.split(":")[0] for line in protected_changes(incoming, running)], sorted(E3_SWARM))


class TheDeclaredReceipts(unittest.TestCase):
    """The spec's 7.6 and D17: what release E3 declares it will move, read back by the stall job after its window."""

    def declared(self) -> dict:
        return json.loads((REPO / DECLARATIONS).read_text(encoding="utf-8"))

    def test_the_file_is_the_specs_text(self):
        self.assertEqual(self.declared(), RECEIPTS_LITERAL)
        self.assertEqual([r["id"] for r in self.declared()["receipts"]], ["E3-forward", "E3-oof"])

    def test_each_declares_a_count_the_funnel_carries_read_after_a_week(self):
        for receipt in self.declared()["receipts"]:
            self.assertEqual(sorted(receipt), sorted(("id", "release", "metric", "direction", "min_delta",
                                                      "window_hours", "why")), receipt["id"])
            section, _, key = receipt["metric"].partition(".")
            self.assertEqual(section, "forward_record", "league/ops/funnel.py `window` carries it under that name")
            self.assertIn(key, forward_report.FUNNEL_KEYS, "an integer count, never a figure")
            self.assertIn(receipt["direction"], release_receipts.DIRECTIONS)
            self.assertEqual((receipt["release"], receipt["min_delta"]), ("E3", 1))
            # A week, not the default 72 h: the first row of a Thursday or Friday deploy lands after the weekend.
            self.assertEqual(receipt["window_hours"], 168)
            self.assertGreater(receipt["window_hours"], release_receipts.READ_AFTER_HOURS)
            self.assertGreater(len(receipt["why"]), 40, "it says why the metric should move")

    def test_the_declarations_reach_the_house(self):
        # The stall job reads `<release>/DECLARATIONS` on the House box, whose release is made of these trees only
        # (scripts/floor_box.py `UPLOAD_TREES`; league/updater.py `TREES` for a self-deploy): a declaration kept
        # anywhere else is never at hand there, and no receipt would ever be declared or read, in silence.
        from league import updater
        from league.tests.test_floor_box_equity import FB as floor_box

        tree = DECLARATIONS.split("/")[0]
        self.assertIn(tree, floor_box.UPLOAD_TREES, f"{DECLARATIONS} is not in a tree the release carries to the House")
        self.assertIn(tree, updater.TREES)
        self.assertIn(DECLARATIONS, {path.as_posix() for path in floor_box.code_files()},
                      "the deploy's own file list holds it")
        self.assertTrue(ci.guard([DECLARATIONS], None), "and it is behind the wall there")

    def test_the_module_that_reads_them_keeps_both(self):
        if not _built(release_receipts.declarations, REPO):
            self.skipTest("league/ops/release_receipts.py is another package's and not built on this tree")
        kept = release_receipts.declarations(REPO)
        self.assertEqual([(r["id"], r["metric"], r["direction"], r["min_delta"], r["window_hours"]) for r in kept],
                         [("E3-forward", "forward_record.program_sessions", "up", 1.0, 168.0),
                          ("E3-oof", "forward_record.oof_rows", "up", 1.0, 168.0)], "none dropped as malformed")


def _built(fn, *args) -> bool:
    """Whether another package's function is built yet (its stub raises NotImplementedError)."""
    try:
        fn(*(args or (None,)))
    except NotImplementedError:
        return False
    return True


if __name__ == "__main__":
    unittest.main()
