"""The engineer and the reviewer (LTCM v3, Phase 4, B5): confined authoring, the static guards, the exact-diff review, the
gateway's pull request / review / merge routes, the deploy, the canary arm, retain or revert, and the global guard."""
import hashlib
import io
import json
import re
import sqlite3
import tarfile
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from league.claude import Answer, ToolUse
from league.ops import author as A
from league.ops import engineer as E
from league.ops import reviewer as R
from league.ops import scoreboard as SB
from league.ops.context import Context, GatewayError
from league.ops.registry import by_name
from league.swarm import canary as gate
from league.swarm import harness_lanes as lanes
from league.swarm.models import ClaudeReply, ModelError
from league.updater import unpack

BASE = "b" * 40
KEY_RE = re.compile(r"GATE KEY: (\S+)")
TOY = '''"""Toy researcher."""


class Researcher:
    def __init__(self, store):
        self.store = store

    def tidy(self, fam, program):
        return len(program) > 0
'''
SAILBOX = '''"""Toy transport."""


def retries(error):
    return 1
'''
FILES = {"league/__init__.py": "", "league/swarm/__init__.py": "", "league/swarm/researcher.py": TOY,
         "league/sailbox.py": SAILBOX, "league/tests/test_toy.py": "import unittest\n", "scripts/tool.py": "x = 1\n"}


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def tarball(sha, files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, text in sorted(files.items()):
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"long-term-capital-management-{sha}/{path}")
            info.size, info.mode = len(data), 0o644
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def reply(blocks, uses, cost=0.2):
    answer = Answer(text="", data=None, usage={}, cost_usd=None, model="claude-opus-5-5",
                    stop_reason="tool_use" if uses else "end_turn", content=tuple(blocks), tool_uses=tuple(uses))
    return ClaudeReply(answer=answer, model="claude-opus-5-5", cost_usd=cost, held_usd=0.0, request_id="r")


def use(n, name, args):
    return ({"type": "tool_use", "id": f"t{n}", "name": name, "input": args}, ToolUse(id=f"t{n}", name=name, input=args))


def gated_author(variant="and \"decide\" in program", test_file=False):
    """A scripted engineer: import the gate, gate a change to `tidy` (and add its own test), finish."""
    def script(kw, n):
        text = kw["messages"][0]["content"][0]["text"]
        key = KEY_RE.search(text).group(1)
        if "REVISION" in text and n == 1:  # the previous change is in the tree: amend it
            b, u = use(1, "edit_file", {"path": "league/swarm/researcher.py", "old_text": 'and "decide" in program',
                                        "new_text": variant})
        elif "REVISION" in text:
            b, u = use(n, "finish", {"title": "Screen programs, revised", "summary": "Amended.",
                                     "predicted_effect": "train_dq_rate falls by a third", "canary_plan": "half"})
        elif n == 1:
            b, u = use(1, "edit_file", {"path": "league/swarm/researcher.py", "old_text": '"""Toy researcher."""\n',
                                        "new_text": '"""Toy researcher."""\nfrom . import canary\n'})
        elif n == 2:
            b, u = use(2, "edit_file", {"path": "league/swarm/researcher.py", "old_text": "        return len(program) > 0\n",
                                        "new_text": f'        if canary.enabled("{key}", fam["id"], root=self.store.root):\n'
                                                    f'            return len(program) > 0 {variant}\n'
                                                    "        return len(program) > 0\n"})
        elif n == 3 and test_file:
            b, u = use(3, "create_file", {"path": "league/tests/test_harness_candidate_tidy.py",
                                          "content": "import unittest\n\n\nclass T(unittest.TestCase):\n    pass\n"})
        else:
            b, u = use(n, "finish", {"title": "Screen programs with no decide before the Gym", "summary": "Refuse early.",
                                     "predicted_effect": "train_dq_rate falls by a third", "canary_plan": "half the families"})
        return reply([b], [u])
    return script


class SelfRunning(unittest.TestCase):
    """The self-running release's rules (Oct 7, 2026): one switch, inside the Claude meter, research-class only."""

    def test_the_job_serves_its_roles_on_the_line_a_swarm_json_that_replaces_the_list_still_holds(self):
        house = {"claude": {"roles": ["architect", "audit", "review", "strategist"], "role_model": {"audit": "claude-opus-5-5"},
                            "role_usd_day": {"review": 5, "strategist": 6, "reviewer": 0.5}, "model": "claude-sonnet-5-5"},
                 "budget": {"source": "budget.json", "claude_usd_day": 10.0}}
        out = E.served(house, usd_day=4.0)
        self.assertEqual(out["claude"]["roles"], ["architect", "audit", "review", "strategist", "engineer", "reviewer"])
        self.assertEqual(out["claude"]["role_model"], {"audit": "claude-opus-5-5", "engineer": E.ROLE_MODEL,
                                                       "reviewer": E.ROLE_MODEL})
        self.assertEqual(out["claude"]["role_usd_day"], {"review": 5, "strategist": 6, "engineer": 4.0, "reviewer": 0.5},
                         "the job's line, never loosening a lower one")
        self.assertEqual(out["budget"], house["budget"], "the budget block is the swarm's own")
        self.assertEqual(house["claude"]["roles"], ["architect", "audit", "review", "strategist"], "the input is not changed")
        self.assertEqual(E.served({}, usd_day=None)["claude"]["roles"], list(E.ROLES))
        for bad in ("lots", None, float("nan"), True, -3):
            self.assertEqual(E._line(bad), 0.0, bad)

    def test_the_line_is_four_dollars_inside_budget_rule_v2s_claude_share(self):
        from league.ops import budget as B

        self.assertEqual(E.DEFAULTS["usd_day"], 4.0)
        self.assertLessEqual(E.AUTHOR_USD_CAP + E.REVIEW_USD_CAP, E.DEFAULTS["usd_day"], "an attempt and its review a day")
        self.assertLessEqual(E.DEFAULTS["usd_day"], B.ceiling_usd_day("claude") - sum(B.GATE_HOLDS_USD.values()),
                             "the gate's holds keep their room in the Claude meter")
        self.assertEqual(E.RELEASE_CLASSES, ("research",))

    def test_the_committed_policy_switches_it_on_and_the_box_can_switch_it_off(self):
        import tempfile as _tmp

        from league.swarm import settings as S

        policy = json.loads((Path(__file__).resolve().parents[2] / "league" / "swarm" / "policy.json").read_text())
        self.assertIs(policy["engineer"]["enabled"], True)
        self.assertEqual(S.policy_layer(policy)[1]["state"], "ok")
        with _tmp.TemporaryDirectory() as tmp:
            loaded = S.load(tmp, config={}, policy=policy)
            self.assertIs(loaded["engineer"]["enabled"], True)
            Path(tmp, "swarm.json").write_text(json.dumps({"engineer": {"enabled": False}}))
            self.assertIs(S.load(tmp, config={}, policy=policy)["engineer"]["enabled"], False, "the box's swarm.json wins")

    def test_the_money_path_is_held_on_the_real_tree(self):
        # On this repository's own tree the live path loads researcher.py and claude_research.py: the engineer may not
        # change them, so its research lane is preflight.py (and a new test) in this release.
        repo = Path(__file__).resolve().parents[2]
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        tmp = Path(scratch.name)
        ctx = Context("engineer", root=tmp / "state", base=tmp, due_at=0.0, config={}, clock=lambda: 0.0, release=repo,
                      gateway=None)
        engineer = E.Engineer(ctx)
        held = engineer.held("research")
        self.assertIn("league/swarm/researcher.py", held)
        self.assertIn("a module the live path loads", held["league/swarm/researcher.py"])
        self.assertEqual(A.writable_paths("research", held), ["league/swarm/preflight.py"])
        self.assertEqual(engineer.held("memory"), {}, "the memory lane's files are research-class")
        ws = A.Workspace(tmp / "tree", "research", held=held)
        tools = A.Tools(ws, "research", None)
        text, error = tools.call("edit_file", {"path": "league/swarm/researcher.py", "old_text": "a", "new_text": "b"})
        self.assertTrue(error)
        self.assertIn("held in this release", text)
        text = E.brief(lane="research", row={"metric": "train_dq_rate", "value": 0.1, "denominator": 10}, key="k",
                       examples=[], held=held)
        self.assertIn("FILES YOU MAY CHANGE: league/swarm/preflight.py;", text)
        self.assertIn("HELD IN THIS RELEASE", text)


class FakeRouter:
    def __init__(self, script=None, verdicts=("approve",), enabled=True, room=6.0, ceiling=0.5):
        self.script, self.verdicts, self.enabled, self.room, self.ceiling = script, list(verdicts), enabled, room, ceiling
        self.turns, self.asks, self.requests = [], [], []
        self.spent = {}

    def claude_enabled(self, role):
        return self.enabled

    def claude_spent(self, role=None, since=None, family=None):
        return self.spent.get(role, 0.0)

    def claude_role_room(self, role):
        return self.room

    def claude_turn(self, **kw):
        self.turns.append(kw)
        return self.script(kw, sum(1 for t in self.turns if t["key"].rsplit(":", 1)[0] == kw["key"].rsplit(":", 1)[0]))

    def claude_request(self, system, user, **kw):
        self.requests.append(user)
        return {}, self.ceiling

    def ask(self, **kw):
        self.asks.append(kw)
        verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
        if isinstance(verdict, Exception):
            raise verdict
        return {"json": {"verdict": verdict, "reasons": [f"the gate is sound ({verdict})"]}, "text": "", "cost_usd": 0.3}


class FakeGitHub:
    """The gateway's GitHub routes over an in-memory repository: commits are file maps, `main` moves on a merge."""

    def __init__(self):
        self.commits = {BASE: dict(FILES)}
        self.main = BASE
        self.prs, self.posts, self.reviews, self.merges = {}, [], [], []
        self.ci = "pending"
        self.n = 6
        self.refuse = {}
        self.health = {"autonomy": {"engineer_pulls": {"count": 0, "cap": 2, "recent": []}}}

    def fetch(self, sha):
        return tarball(sha, self.commits[sha])

    def post(self, path, body):
        self.posts.append((path, body))
        if path in self.refuse:
            raise self.refuse[path]
        if path == "/v1/github/pr":
            self.n += 1
            files = {f["path"]: f["content"] for f in body["files"]}
            head = hashlib.sha1(json.dumps([self.main, sorted(files.items())]).encode()).hexdigest()
            self.commits[head] = {**self.commits[self.main], **files}
            self.prs[self.n] = {"body": body, "head": head, "state": "open", "merged": False}
            return {"ok": True, "number": self.n, "head": head, "branch": f"engineer/{body['lane']}/{body['slug']}-0000"}
        if path == "/v1/github/review":
            self.reviews.append(body)
            return {"ok": True}
        if path == "/v1/github/merge":
            pr = self.prs[body["pr"]]
            assert body["head_sha"] == pr["head"]
            merged = hashlib.sha1(f"merge{pr['head']}".encode()).hexdigest()
            self.commits[merged] = {**self.commits[self.main], **{f["path"]: f["content"] for f in pr["body"]["files"]}}
            self.main = merged
            pr.update(merged=True, state="closed")
            self.merges.append(body)
            return {"ok": True, "merged": True, "sha": merged}
        raise AssertionError(path)

    def get(self, path, params=None):
        if path == "/v1/health":
            return self.health
        found = re.fullmatch(r"/v1/github/pr/(\d+)(/failures)?", path)
        pr = self.prs[int(found.group(1))]
        if found.group(2):
            return {"failures": [{"name": "tests (3.11)", "conclusion": "failure", "title": "1 failed",
                                  "annotations": [{"title": "test_tidy", "message": "AssertionError: tidy refused a program"}]}]}
        return {"number": int(found.group(1)), "state": pr["state"], "merged": pr["merged"], "head": pr["head"],
                "checks": {"conclusion": self.ci}}


def data_author(kw, n):
    """A scripted engineer in the data lane (a window lane: no gate)."""
    if n == 1:
        b, u = use(1, "edit_file", {"path": "league/sailbox.py", "old_text": "    return 1\n", "new_text": "    return 3\n"})
    else:
        b, u = use(2, "finish", {"title": "Retry a reset read three times", "summary": "More retries.",
                                 "predicted_effect": "slot_failure_rate halves", "canary_plan": "the day after"})
    return reply([b], [u])


def boxes(failed, n=5, slots=100):
    return {f"box{i}": {"slots": slots, "slots_failed": failed, "batches_failed": 1 if failed else 0,
                        "ok_slots": slots - failed, "gym_usd": 1.0, "gym_seconds": 1000.0} for i in range(n)}


def units_for(key, salt, *, canary_dq, control_dq, n=60, runs=20):
    out = {}
    for i in range(n):
        fam = f"f{i:02d}"
        dq = canary_dq if gate.in_arm(salt, key, fam, 0.5) else control_dq
        out[fam] = {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "research_usd": 1.0, "cycles": runs,
                    "cycle_errors": 0, "gym_cycles": runs, "gym_cycles_unmatched": 0, "ok_zero_trade_runs": 0,
                    "wasted_gym_seconds": dq * 100.0, "gym_seconds": runs * 100.0, "births": 1}
    return out


class Flow(unittest.TestCase):
    """The whole loop on fakes: the House's journal, the gateway's routes, the updater's deploys, the canary file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.gh = FakeGitHub()
        self.router = FakeRouter(gated_author())
        self.release = self.deploy(BASE, "main-aaaaaaaaaaaa", at("2026-10-05T22:00:00Z"))
        self.capture = at("2026-10-06T03:30:00Z")
        self.write_capture()
        self.measured = []
        self.window = None

    def deploy(self, sha, name, when):
        release = self.base / "releases" / name
        unpack(tarball(sha, self.gh.commits[sha]), release, sha=sha)
        with (self.base / "deploys.jsonl").open("a") as handle:
            for stage, extra in (("start", {}), ("promote", {"ok": True}), ("verdict", {"verdict": "promoted"})):
                handle.write(json.dumps({"deploy": f"{name}@{int(when)}", "release": name, "stage": stage, "sha": sha,
                                         "at": E.S.iso(when + (60 if stage != "start" else 0)), **extra}) + "\n")
        return release

    def write_capture(self, lane="research", metric="train_dq_rate"):
        row = {"lane": lane, "metric": metric, "value": 0.14, "denominator": 2400.0, "captured": True, "threshold": 0.05,
               "min_effect": 0.25, "direction": "lower", "rank": 1, "examples": []}
        doc = {"until": self.capture, "since": self.capture - 86400, "lanes": {lane: {
            "units": units_for("k", "s", canary_dq=3, control_dq=3),
            "population": {"unattributed_usd": 0.0, "hours": 24.0},
            "examples": [{"signature": "NameError: name '<text>' is not defined", "n": 9, "families": ["f00", "f01"]}]}}}
        E.write_json(self.root / E.RANKED, {"at": self.capture, "policy": lanes.POLICY, "candidates": [row],
                                            "source": {"release": str(self.release), "digest": "x"}})
        E.write_json(self.root / E.MEASUREMENT, doc)

    def measure(self, root, **kw):
        self.measured.append(kw)
        if self.window is None:
            raise AssertionError(f"unexpected measurement {kw}")
        return self.window(kw)

    def go(self, when, *, release=None, settings=None, router=None):
        ctx = Context("engineer", root=self.root, base=self.base, due_at=at(when), config={}, clock=lambda: at(when),
                      release=release or self.release, gateway=self.gh)
        engineer = E.Engineer(ctx, router_factory=lambda: router or self.router, fetch=self.gh.fetch,
                              resolve_head=lambda: self.gh.main, measure=self.measure,
                              swarm_settings=settings if settings is not None else {"engineer": {"enabled": True}})
        out = engineer.run()
        out["alerts"] = ctx.alerts
        return out

    def journal(self):
        j = E.Journal(self.root)
        try:
            return j.all()
        finally:
            j.close()

    def only(self):
        rows = self.journal()
        self.assertEqual(len(rows), 1)
        return rows[0]

    def to_merged(self):
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "success"
        self.go("2026-10-06T05:40:00Z")
        return self.only()

    # ---------------------------------------------------------------------------------------------- tests
    def test_off_unless_the_settings_say_so(self):
        out = self.go("2026-10-06T04:00:00Z", settings={})
        self.assertEqual(out["status"], "skipped")
        self.assertFalse((self.root / E.FILE).exists())

    def test_authoring_opens_one_public_safe_pull_request_through_the_engineer_role(self):
        out = self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "pr_open", out)
        self.assertEqual(cand["base_sha"], BASE)
        self.assertTrue(cand["key"].startswith("harness:research:train_dq_rate:"))
        (path, body), = [p for p in self.gh.posts if p[0] == "/v1/github/pr"]
        self.assertEqual((body["role"], body["lane"]), ("engineer", "research"))
        self.assertEqual([f["path"] for f in body["files"]], ["league/swarm/researcher.py"])
        self.assertIn(f'canary.enabled("{cand["key"]}", fam["id"]', body["files"][0]["content"])
        for part in ("## Measurement", "## Predeclared metric", "## Predicted effect", "## Canary plan", cand["key"], BASE):
            self.assertIn(part, body["body"])
        self.assertEqual(E.public_problems(body["body"] + body["title"]), [])
        # The brief: ASCII, the gate key and the files, no family id, no figure the brief may not carry.
        brief = self.router.turns[0]["messages"][0]["content"][0]["text"]
        self.assertTrue(brief.isascii())
        self.assertIn("league/swarm/researcher.py", brief)
        self.assertNotIn("f00", brief)
        self.assertEqual(self.router.turns[0]["role"], "engineer")
        self.assertAlmostEqual(cand["record"]["author_usd"], 0.6)
        # Nothing new the same day, and nothing at an hourly occurrence.
        self.go("2026-10-06T05:00:00Z")
        self.assertEqual(len(self.journal()), 1)

    def test_a_full_day_at_the_gateway_waits_for_the_next_run(self):
        self.gh.refuse["/v1/github/pr"] = GatewayError("POST /v1/github/pr: HTTP 429 cap", status=429)
        self.go("2026-10-06T04:00:00Z")
        self.assertEqual(self.only()["state"], "pr_pending")
        del self.gh.refuse["/v1/github/pr"]
        self.go("2026-10-06T04:40:00Z")
        self.assertEqual(self.only()["state"], "pr_open")

    def test_a_gateway_refusal_of_the_pull_request_closes_the_candidate(self):
        # A gateway that still caps a file at 64 KiB (before WP8b) refuses the request.
        self.gh.refuse["/v1/github/pr"] = GatewayError("POST /v1/github/pr: HTTP 413 too large", status=413)
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "closed_failed")
        self.assertIn("refused the pull request", cand["record"]["closed_why"])

    def test_no_attested_commit_no_candidate(self):
        # An owner deploy of a commit that is not main's head: no attestation, no observer policy, and main's head's
        # release trees are not the running tree. Nothing is authored.
        (self.base / "deploys.jsonl").write_text("")
        moved = "c" * 40
        self.gh.commits[moved] = {**FILES, "scripts/tool.py": "x = 2\n"}
        self.gh.main = moved
        out = self.go("2026-10-06T04:00:00Z")
        self.assertEqual(self.journal(), [])
        self.assertTrue(any("no attested commit" in a and "not its tree" in a for a in out["actions"]), out)

    def test_an_owner_deploy_of_mains_head_is_the_base_checked_once_a_release(self):
        # Self-running (Oct 7): an owner deploy carries no attestation. Main's head whose release trees ARE the running
        # tree is the base, remembered for the release in the journal, so the engineer is not idle until a hand edit.
        (self.base / "deploys.jsonl").write_text("")
        fetched = []
        fetch = self.gh.fetch
        self.gh.fetch = lambda sha: fetched.append(sha) or fetch(sha)
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual((cand["base_sha"], cand["state"]), (BASE, "pr_open"))
        self.assertIn("main's head", cand["record"]["base_how"])
        j = E.Journal(self.root)
        try:
            self.assertEqual(j.kv_get(f"base:{self.release.name}")["sha"], BASE)
        finally:
            j.close()
        self.assertFalse((self.root / E.WORK / "base-probe").exists(), "the probe tree is removed")
        probes = len(fetched)
        engineer = E.Engineer(Context("engineer", root=self.root, base=self.base, due_at=at("2026-10-07T04:00:00Z"),
                                      config={}, clock=lambda: at("2026-10-07T04:00:00Z"), release=self.release,
                                      gateway=self.gh), fetch=self.gh.fetch, resolve_head=lambda: "d" * 40)
        j = E.Journal(self.root)
        try:
            self.assertEqual(engineer.base_of_running(j), (BASE, cand["record"]["base_how"]), "remembered: main moved on")
        finally:
            j.close()
        self.assertEqual(len(fetched), probes, "no second download for the same release")

    def test_a_change_that_classifies_as_the_money_path_is_closed_before_its_pull_request(self):
        # Defense in depth behind the held paths: whatever the tools let through, a tree whose change the live path
        # loads is never a pull request in this release.
        from unittest import mock

        money = {"release_class": "money_path", "paths": {"money_path": ["league/swarm/researcher.py"]}}
        with mock.patch.object(E.Engineer, "held", return_value={}), mock.patch.object(lanes, "classify", return_value=money):
            self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "closed_failed")
        self.assertIn("money_path (league/swarm/researcher.py)", cand["record"]["closed_why"])
        self.assertEqual([p for p, _ in self.gh.posts if p == "/v1/github/pr"], [])

    def test_roles_not_configured_no_candidate(self):
        out = self.go("2026-10-06T04:00:00Z", router=FakeRouter(gated_author(), enabled=False))
        self.assertEqual(self.journal(), [])
        self.assertTrue(any("claude.roles" in a for a in out["actions"]), out)

    def test_green_ci_review_approve_then_merge_of_the_exact_head(self):
        self.go("2026-10-06T04:00:00Z")
        self.go("2026-10-06T04:40:00Z")
        self.assertEqual(self.only()["state"], "pr_open")
        self.assertEqual(self.gh.reviews, [])
        cand = self.to_merged()
        self.assertEqual(cand["state"], "merged")
        pr = self.gh.prs[cand["record"]["pr"]]
        self.assertEqual(self.gh.reviews, [{"pr": cand["record"]["pr"], "head_sha": pr["head"], "verdict": "approve",
                                            "reasons": ["the gate is sound (approve)"]}])
        self.assertEqual(self.gh.merges, [{"pr": cand["record"]["pr"], "head_sha": pr["head"]}])
        # The reviewer read the exact diff and the contract.
        user = self.router.asks[0]["user"]
        self.assertIn("+++ b/league/swarm/researcher.py", user)
        self.assertIn(cand["key"], user)
        self.assertEqual(self.router.asks[0]["role"], "reviewer")

    def test_a_review_with_no_room_waits_and_three_billed_failures_end_it(self):
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "success"
        self.router.verdicts = [ModelError("claude: no room", kind="no_room")]
        self.go("2026-10-06T05:40:00Z")
        self.assertEqual(self.only()["state"], "pr_open")
        self.assertEqual(self.gh.reviews, [])
        self.router.verdicts = [ModelError("claude: refused", kind="refusal", billed=[{"cost_usd": 0.4}])]
        for hour in ("06", "07"):
            self.go(f"2026-10-06T{hour}:40:00Z")
            self.assertEqual(self.only()["state"], "pr_open")
        self.go("2026-10-06T08:40:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "closed_failed")
        self.assertAlmostEqual(cand["record"]["review_usd"], 1.2)
        self.assertEqual(self.gh.merges, [])

    def test_a_pull_request_carrying_other_bytes_is_rejected_by_code_without_a_model(self):
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        head = self.gh.prs[cand["record"]["pr"]]["head"]
        self.gh.commits[head]["scripts/tool.py"] = "x = 2\n"
        self.gh.ci = "success"
        self.go("2026-10-06T14:40:00Z")
        self.assertEqual(self.router.asks, [])
        self.assertEqual(self.gh.reviews[0]["verdict"], "reject")
        self.assertIn("files the candidate did not", self.gh.reviews[0]["reasons"][0])
        self.assertEqual(self.only()["state"], "revise")

    def test_a_rejection_goes_back_once_then_is_final(self):
        self.router.verdicts = ["reject"]
        self.router.script = gated_author('and "decide(" in program')
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "success"
        self.go("2026-10-06T14:40:00Z")  # in the session: the review runs, the revision waits for the close
        self.assertEqual(self.only()["state"], "revise")
        self.go("2026-10-06T15:40:00Z")
        self.assertEqual(self.only()["state"], "revise")
        self.gh.ci = "pending"
        self.go("2026-10-06T21:40:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "pr_open")
        self.assertEqual(len(self.gh.prs), 2)
        files = self.gh.prs[cand["record"]["pr"]]["body"]["files"]
        self.assertIn('and "decide(" in program', files[0]["content"])
        revision = [t for t in self.router.turns if t["key"].startswith(f"engineer:{cand['key']}:2")][0]
        text = revision["messages"][0]["content"][0]["text"]
        self.assertIn("REVISION", text)
        self.assertIn("the gate is sound (reject)", text)
        self.gh.ci = "success"
        self.go("2026-10-06T22:40:00Z")
        self.assertEqual(self.only()["state"], "closed_rejected")
        self.assertEqual(self.gh.merges, [])
        self.assertEqual([r["verdict"] for r in self.gh.reviews], ["reject", "reject"])
        # The gateway closes no pull request: both are listed for the owner.
        self.assertEqual(cand_prs := self.only()["record"]["leftover_prs"], sorted(self.gh.prs))
        summary = E.public_summary(self.root)
        self.assertEqual(summary["leftover_prs"], cand_prs)
        page = SB.build(day="2026-10-06", release="r", economics=None, deploys={}, budget=None, ladder={}, jobs={},
                        written_at="23:30Z", engineer=summary)
        self.assertIn(", ".join(f"#{n}" for n in cand_prs), page)
        self.assertEqual(SB.public_problems(page), [])

    def test_a_ci_failure_revises_with_the_annotations(self):
        self.router.script = gated_author('and "decide(" in program')
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "failure"
        self.go("2026-10-06T14:40:00Z")
        self.assertEqual(self.only()["state"], "revise")
        self.gh.ci = "pending"
        self.go("2026-10-06T20:40:00Z")  # outside the session (and its half hour) the revision runs and opens its own PR
        cand = self.only()
        self.assertEqual(cand["state"], "pr_open")
        self.assertEqual(self.gh.reviews, [])
        texts = [t["messages"][0]["content"][0]["text"] for t in self.router.turns if ":2:" in t["key"]]
        self.assertIn("AssertionError: tidy refused a program", texts[0])

    def test_main_moving_a_touched_file_drops_the_candidate(self):
        moved = "c" * 40
        self.gh.commits[moved] = {**FILES, "league/swarm/researcher.py": TOY + "\n# moved\n"}
        self.gh.main = moved
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "closed_failed")
        self.assertIn("main moved", cand["record"]["closed_why"])
        self.assertEqual([p for p in self.gh.posts if p[0] == "/v1/github/pr"], [])

    def test_deploy_canary_retain_and_the_global_guard(self):
        cand = self.to_merged()
        self.go("2026-10-06T07:40:00Z")
        self.assertEqual(self.only()["state"], "merged")  # the updater has not shipped it yet
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "canary")
        arms = gate.read(self.root / gate.FILE)
        arm = arms[cand["key"]]
        self.assertEqual((arm["state"], arm["fraction"], arm["lane"]), ("canary", 0.5, "research"))
        self.assertEqual(cand["record"]["canary"]["until"] - cand["record"]["canary"]["since"], 12 * 3600)
        self.go("2026-10-06T12:40:00Z", release=new)
        self.assertEqual(self.only()["state"], "canary")
        key, salt = cand["key"], arm["salt"]
        self.window = lambda kw: {"since": kw["since"], "until": kw["now"], "deploys": [], "start_releases": [],
                                  "lanes": {"research": {"units": units_for(key, salt, canary_dq=1, control_dq=5),
                                                         "population": {"unattributed_usd": 0.0, "hours": 12.0}}}}
        self.go("2026-10-07T00:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["record"]["decision"]["decision"], "retained", cand["record"]["decision"])
        self.assertEqual(cand["state"], "retained")
        self.assertEqual(gate.read(self.root / gate.FILE)[key]["state"], "retained")
        self.assertNotIn("f00", json.dumps(self.measured))  # motivating units are excluded by the decision, not the read
        # Twenty sessions later with no promoted programs' trades: the guard holds and the change is closed retained.
        self.go("2026-11-10T04:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "closed_retained")
        self.assertEqual(cand["record"]["guard"]["breach"], False)

    def test_a_canary_that_does_not_beat_its_metric_flips_back_and_reverts_through_the_same_route(self):
        cand = self.to_merged()
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        key = self.only()["key"]
        salt = gate.read(self.root / gate.FILE)[key]["salt"]
        self.window = lambda kw: {"since": kw["since"], "until": kw["now"], "deploys": [], "start_releases": [],
                                  "lanes": {"research": {"units": units_for(key, salt, canary_dq=3, control_dq=3),
                                                         "population": {"unattributed_usd": 0.0, "hours": 12.0}}}}
        self.gh.ci = "pending"
        self.go("2026-10-07T00:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "reverting")
        self.assertEqual(gate.read(self.root / gate.FILE)[key]["state"], "reverted")
        revert = self.gh.prs[cand["record"]["revert"]["pr"]]["body"]
        self.assertEqual(revert["files"], [{"path": "league/swarm/researcher.py", "content": TOY}])
        self.assertTrue(revert["slug"].startswith("revert-research-"))
        self.gh.ci = "success"
        self.go("2026-10-07T01:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "closed_reverted")
        self.assertEqual(self.gh.reviews[-1]["verdict"], "approve")
        self.assertIn("mechanical revert", self.gh.reviews[-1]["reasons"][0])
        self.assertEqual(self.gh.commits[self.gh.main]["league/swarm/researcher.py"], TOY)
        self.assertEqual(len(self.router.asks), 1)  # the revert's review cost no model call

    def test_a_revert_empties_the_candidates_own_test(self):
        self.router = FakeRouter(gated_author(test_file=True))
        self.to_merged()
        self.assertIn("league/tests/test_harness_candidate_tidy.py", self.gh.commits[self.gh.main])
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        self.go("2026-10-06T10:40:00Z", release=self.release)  # rolled back: revert
        cand = self.only()
        files = dict((f["path"], f["content"]) for f in self.gh.prs[cand["record"]["revert"]["pr"]]["body"]["files"])
        self.assertEqual(files["league/swarm/researcher.py"], TOY)
        self.assertTrue(files["league/tests/test_harness_candidate_tidy.py"].startswith('"""Reverted by the engineer'))
        compile(files["league/tests/test_harness_candidate_tidy.py"], "t", "exec")

    def test_the_data_lane_waits_for_a_fresh_control_window_then_judges_the_window(self):
        self.write_capture(lane="data", metric="slot_failure_rate")
        self.router = FakeRouter(data_author)
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual((cand["lane"], cand["state"]), ("data", "pr_open"))
        self.assertNotIn("GATE KEY", self.router.turns[0]["messages"][0]["content"][0]["text"])
        self.gh.ci = "success"
        self.go("2026-10-06T05:40:00Z")
        self.assertEqual(self.only()["state"], "pr_open")  # approved; the merge waits a day past the capture
        self.assertEqual(self.gh.merges, [])
        self.go("2026-10-07T04:40:00Z")
        self.assertEqual(self.only()["state"], "merged")
        new = self.deploy(self.gh.main, "main-dddddddddddd", at("2026-10-07T06:00:00Z"))
        self.window = lambda kw: {"since": kw["since"], "until": kw["now"], "window": {}, "starts": [], "deploys": [],
                                  "start_releases": [], "lanes": {"data": {
                                      "units": boxes(10 if kw["now"] <= at("2026-10-07T06:00:00Z") else 1),
                                      "run_totals": {"runs": 100.0, "error_runs": 1.0}}}}
        self.go("2026-10-07T06:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "canary")
        control = self.measured[-1]
        self.assertEqual((control["since"], control["now"]), (at("2026-10-06T06:00:00Z"), at("2026-10-07T06:00:00Z")))
        self.assertFalse((self.root / gate.FILE).exists())  # a window lane installs no arm
        self.go("2026-10-08T06:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["record"]["decision"]["decision"], "retained", cand["record"]["decision"])
        self.assertEqual(cand["state"], "retained")

    def test_a_watchdog_rollback_during_the_canary_reverts(self):
        self.to_merged()
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        self.go("2026-10-06T10:40:00Z", release=self.release)  # the base release is running again
        cand = self.only()
        self.assertEqual(cand["state"], "reverting")
        self.assertIn("rolled", cand["record"]["revert"]["why"])

    def test_the_global_guard_reverts_a_retained_change_that_lowered_the_forward_record(self):
        cand = self.to_merged()
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        key = self.only()["key"]
        salt = gate.read(self.root / gate.FILE)[key]["salt"]
        self.window = lambda kw: {"since": kw["since"], "until": kw["now"], "deploys": [], "start_releases": [],
                                  "lanes": {"research": {"units": units_for(key, salt, canary_dq=1, control_dq=5),
                                                         "population": {"unattributed_usd": 0.0, "hours": 12.0}}}}
        self.go("2026-10-07T00:40:00Z", release=new)
        self.assertEqual(self.only()["state"], "retained")
        db = sqlite3.connect(self.root / "swarm.sqlite")
        db.executescript("CREATE TABLE families(id TEXT, band TEXT); CREATE TABLE forward(family TEXT, source TEXT, "
                         "trade_id TEXT, day TEXT, pnl REAL, max_loss REAL, at TEXT, version INTEGER);")
        db.execute("INSERT INTO families VALUES('p1','probe')")
        days = E.trading_days(datetime(2026, 9, 1).date(), datetime(2026, 10, 30).date())
        for n, day in enumerate(days):
            pnl = (40.0 + n % 3) if day < "2026-10-06" else (-30.0 - n % 3)
            db.execute("INSERT INTO forward VALUES('p1','shadow',?,?,?,100.0,'',1)", (f"t{n}", day, pnl))
        db.commit()
        db.close()
        self.go("2026-10-29T04:40:00Z", release=new)
        cand = self.only()
        self.assertEqual(cand["state"], "reverting")
        self.assertTrue(cand["record"]["guard"]["breach"])
        self.assertIn("global guard", cand["record"]["revert"]["why"])

    def test_no_authoring_without_the_gateways_engineer_route_or_the_day_line(self):
        self.gh.health = {"autonomy": {"docs": {"commits": 0, "cap": 4}}}  # a gateway before WP8b
        out = self.go("2026-10-06T04:00:00Z")
        self.assertEqual((self.journal(), self.router.turns), ([], []))
        self.assertTrue(any("engineer_pulls" in a for a in out["actions"]), out)
        self.gh.health = {"autonomy": {"engineer_pulls": {"count": 2, "cap": 2}}}
        out = self.go("2026-10-06T04:00:00Z")
        self.assertEqual(self.journal(), [])
        self.assertTrue(any("are used" in a for a in out["actions"]), out)
        self.gh.health = {"autonomy": {"engineer_pulls": {"count": 0, "cap": 2}}}
        self.router.spent = {"engineer": 2.0, "reviewer": 1.5}  # $0.50 left of the $4 day
        out = self.go("2026-10-06T04:00:00Z")
        self.assertEqual((self.journal(), self.router.turns), ([], []))
        self.assertTrue(any("left of their $4.00" in a for a in out["actions"]), out)

    def test_an_attempt_is_capped_at_what_the_day_line_has_left(self):
        def costly(kw, n):
            b, u = use(n, "read_file", {"path": "league/swarm/researcher.py"})
            return reply([b], [u], cost=0.5)
        self.router = FakeRouter(costly)
        self.router.spent = {"reviewer": 2.5}  # $1.50 left of the $4 day
        self.go("2026-10-06T04:00:00Z")
        cand = self.only()
        self.assertEqual(cand["state"], "closed_failed")
        self.assertLessEqual(cand["record"]["author_usd"], 1.5)
        self.assertIn("past its $1.50", cand["record"]["attempts"][0]["why"])

    def test_a_review_waits_when_the_day_line_cannot_cover_it(self):
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "success"
        self.router.spent = {"engineer": 3.5}  # $0.50 left of the $4 day: under the review's $1
        self.go("2026-10-06T05:40:00Z")
        self.assertEqual((self.only()["state"], self.router.asks), ("pr_open", []))
        self.router.spent = {}
        self.go("2026-10-07T00:40:00Z")
        self.assertEqual(self.only()["state"], "merged")

    def test_a_revert_on_its_way_holds_the_next_authoring(self):
        self.to_merged()
        new = self.deploy(self.gh.main, "main-cccccccccccc", at("2026-10-06T08:00:00Z"))
        self.go("2026-10-06T08:40:00Z", release=new)
        self.gh.refuse["/v1/github/pr"] = GatewayError("POST /v1/github/pr: HTTP 429 cap", status=429)  # the revert waits
        self.go("2026-10-06T10:40:00Z", release=self.release)  # rolled back: reverting
        cand = self.only()
        self.assertEqual(cand["state"], "reverting")
        self.write_capture()
        out = self.go("2026-10-07T04:00:00Z", release=self.release)
        self.assertEqual(len(self.journal()), 1)
        self.assertTrue(any("in flight" in a and "reverting" in a for a in out["actions"]), out)
        # A revert that never lands is handed over after `deploy_days`, not waited on forever.
        self.go("2026-10-14T05:00:00Z", release=self.release)
        cand = self.only()
        self.assertEqual(cand["state"], "closed_reverted")
        self.assertIn("did not land in time", cand["record"]["closed_why"])

    def test_a_window_lane_with_no_promote_row_for_its_release_fails_closed(self):
        self.write_capture(lane="data", metric="slot_failure_rate")
        self.router = FakeRouter(data_author)
        self.go("2026-10-06T04:00:00Z")
        self.gh.ci = "success"
        self.go("2026-10-06T05:40:00Z")
        self.go("2026-10-07T04:40:00Z")
        self.assertEqual(self.only()["state"], "merged")
        owner = self.base / "releases" / "main-eeeeeeeeeeee"  # an owner deploy: no watchdog rows
        unpack(tarball(self.gh.main, self.gh.commits[self.gh.main]), owner, sha=self.gh.main)
        self.window = lambda kw: self.fail(f"no control window may be measured: {kw}")
        self.go("2026-10-07T06:40:00Z", release=owner)
        cand = self.only()
        self.assertEqual(cand["state"], "reverting")
        self.assertIn("no promote row", cand["record"]["revert"]["why"])

    def test_the_scoreboard_counts_the_engineer_publicly(self):
        self.to_merged()
        summary = E.public_summary(self.root)
        self.assertEqual((summary["authored"], summary["merged"]), (1, 1))
        self.assertEqual(summary["in_flight"], "research (merged)")
        page = SB.build(day="2026-10-06", release="r", economics=None, deploys={}, budget=None, ladder={}, jobs={},
                        written_at="23:30Z", engineer=summary)
        self.assertIn("## The engineer (harness changes)", page)
        self.assertEqual(SB.public_problems(page), [])


class Authoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = Path(self.tmp.name)
        for path, text in FILES.items():
            (self.tree / path).parent.mkdir(parents=True, exist_ok=True)
            (self.tree / path).write_text(text)
        self.key = "harness:research:train_dq_rate:0123456789abcdef"
        self.ws = A.Workspace(self.tree, "research")
        self.tools = A.Tools(self.ws, "research", self.key)

    def test_the_tools_are_confined_to_the_tree_the_surface_and_new_tests(self):
        self.assertTrue(self.tools.call("read_file", {"path": "../../etc/passwd"})[1])
        self.assertTrue(self.tools.call("list_dir", {"path": "/etc"})[1])
        text, error = self.tools.call("edit_file", {"path": "league/swarm/store.py", "old_text": "a", "new_text": "b"})
        self.assertTrue(error)
        self.assertTrue(self.tools.call("edit_file", {"path": "league/tests/test_toy.py", "old_text": "import", "new_text": "x"})[1])
        self.assertTrue(self.tools.call("edit_file", {"path": "league/sailbox.py", "old_text": "1", "new_text": "2"})[1])
        self.assertTrue(self.tools.call("create_file", {"path": "league/swarm/new.py", "content": "x = 1\n"})[1])
        self.assertTrue(self.tools.call("create_file", {"path": "league/tests/test_toy.py", "content": "x\n"})[1])
        self.assertFalse(self.tools.call("create_file", {"path": "league/tests/test_harness_candidate_tidy.py",
                                                         "content": "import unittest\n"})[1])
        self.assertTrue(self.tools.call("edit_file", {"path": "league/swarm/researcher.py", "old_text": "    ",
                                                      "new_text": "  "})[1])  # not unique
        self.assertIn("league/swarm/researcher.py:9:", self.tools.call("grep", {"pattern": "len\\(program\\)"})[0])
        self.assertTrue(self.tools.call("read_file", {"path": "league/swarm/researcher.py", "start_line": "x"})[1])
        self.assertTrue(self.tools.call("grep", {"pattern": "("})[1])
        self.assertTrue(self.tools.call("no_such_tool", {})[1])
        self.assertEqual(sorted(self.ws.files()), ["league/tests/test_harness_candidate_tidy.py"])

    def test_the_static_guards_refuse_ungated_and_dangerous_changes_and_pass_a_gated_one(self):
        self.tools.call("edit_file", {"path": "league/swarm/researcher.py", "old_text": "        return len(program) > 0\n",
                                      "new_text": "        return len(program) > 1\n"})
        problems = A.static_guards("research", self.ws, key=self.key)
        self.assertTrue(any("not every change is gated" in p for p in problems), problems)
        (self.tree / "league/swarm/researcher.py").write_text(TOY.replace('"""Toy researcher."""\n',
                                                                          '"""Toy researcher."""\nimport subprocess\n'))
        self.assertTrue(any("subprocess" in p for p in A.static_guards("research", self.ws, key=self.key)))
        gated = TOY.replace('"""Toy researcher."""\n', '"""Toy researcher."""\nfrom . import canary\n').replace(
            "        return len(program) > 0\n",
            f'        if canary.enabled("{self.key}", fam["id"], root=self.store.root):\n            return False\n'
            "        return len(program) > 0\n")
        (self.tree / "league/swarm/researcher.py").write_text(gated)
        self.assertEqual(A.static_guards("research", self.ws, key=self.key), [])
        # A window lane needs no gate; the gateway's limits hold in every lane.
        data = A.Workspace(self.tree, "data")
        A.Tools(data, "data", None).call("edit_file", {"path": "league/sailbox.py", "old_text": "    return 1\n",
                                                       "new_text": "    return 2\n"})
        self.assertEqual(A.static_guards("data", data, key=None), [])
        self.assertIn("league/sailbox.py", A.writable_paths("data"))
        self.assertFalse(A.writable("data", "scripts/data/nightly.py"))  # in the lane's surface, not the gateway's

    def run_loop(self, router, cap=3.0, turns=24):
        return A.run_loop(router, ws=self.ws, lane="research", key=self.key, system="s",
                          brief=f"GATE KEY: {self.key}\n", request_key="engineer:x:1", usd_cap=cap, max_turns=turns,
                          deadline=1e12)

    def test_the_loop_finishes_with_the_files_and_its_spend(self):
        router = FakeRouter(gated_author())
        out = self.run_loop(router)
        self.assertEqual(out.status, "finished", out)
        self.assertEqual(list(out.files), ["league/swarm/researcher.py"])
        self.assertEqual(out.originals["league/swarm/researcher.py"], TOY)
        self.assertAlmostEqual(out.usd, 0.6)
        self.assertEqual(out.title, "Screen programs with no decide before the Gym")
        # Every turn after the first sends the whole conversation back, tool results answering their calls.
        last = router.turns[-1]["messages"]
        self.assertEqual(last[2]["content"][0]["tool_use_id"], "t1")
        self.assertEqual(sum(1 for m in last for b in m["content"] if "cache_control" in b), 1)

    def test_the_loop_stops_before_the_attempts_cap_and_on_a_model_failure(self):
        def costly(kw, n):
            b, u = use(n, "read_file", {"path": "league/swarm/researcher.py"})
            return reply([b], [u], cost=1.2)
        out = self.run_loop(FakeRouter(costly))
        self.assertEqual(out.status, "failed")
        self.assertIn("past its $3.00", out.why)
        self.assertLessEqual(out.usd, 3.0)

        def broken(kw, n):
            raise ModelError("claude: the engineer line for today has no room", kind="line")
        out = self.run_loop(FakeRouter(broken))
        self.assertEqual((out.status, out.usd), ("failed", 0.0))
        self.assertIn("(line)", out.why)

    def test_nothing_after_finish_in_the_same_reply_reaches_the_change(self):
        author = gated_author()

        def script(kw, n):
            if n < 3:
                return author(kw, n)
            fb, fu = use(3, "finish", {"title": "t", "summary": "s", "predicted_effect": "p", "canary_plan": "c"})
            eb, eu = use(4, "edit_file", {"path": "league/swarm/researcher.py", "old_text": "    def tidy(self, fam, program):\n",
                                          "new_text": "    def tidy(self, fam, program):\n        import subprocess\n"})
            cb, cu = use(5, "create_file", {"path": "league/tests/test_harness_candidate_late.py", "content": "x = 1\n"})
            return reply([fb, eb, cb], [fu, eu, cu])
        out = self.run_loop(FakeRouter(script))
        self.assertEqual(out.status, "finished", out)
        self.assertEqual(list(out.files), ["league/swarm/researcher.py"])
        self.assertNotIn("subprocess", out.files["league/swarm/researcher.py"])
        self.assertEqual(A.static_guards("research", self.ws, key=self.key), [])

    def test_a_finished_tree_that_fails_the_guards_is_not_submitted(self):
        router = FakeRouter(gated_author())
        real = A.Tools.t_finish

        def finish_then_tamper(tools, **kw):  # whatever route changes the tree after the finish passed the guards
            result = real(tools, **kw)
            path = tools.ws.root / "league/swarm/researcher.py"
            path.write_text(path.read_text().replace("    def tidy", "    import subprocess\n\n    def tidy"))
            return result
        A.Tools.t_finish = finish_then_tamper
        try:
            out = self.run_loop(router)
        finally:
            A.Tools.t_finish = real
        self.assertEqual(out.status, "failed")
        self.assertTrue(any("subprocess" in g for g in out.guards), out.guards)

    def test_new_test_names_follow_the_gateways_rule(self):
        for bad in ("league/tests/test_harness_candidate_Tidy-v2.py", "league/tests/test_harness_candidate_x/y.py",
                    "league/tests/test_harness_candidate_.py", "league/tests/test_harness_candidate_a.pyc"):
            self.assertFalse(A.is_new_test(bad), bad)
            self.assertFalse(A.writable("research", bad), bad)
            self.assertTrue(self.tools.call("create_file", {"path": bad, "content": "x = 1\n"})[1], bad)
        self.assertTrue(A.is_new_test("league/tests/test_harness_candidate_tidy_2.py"))
        self.assertEqual(self.ws.files(), {})

    def test_the_tools_survive_hostile_arguments(self):
        for pattern in ("(a+)+$", "(\\w+\\s?)*x", "(?:ab*)*", "(a)\\1", "x" * 201):
            text, error = self.tools.call("grep", {"pattern": pattern})
            self.assertTrue(error, pattern)
            self.assertIn("bad pattern", text)
        self.assertFalse(self.tools.call("grep", {"pattern": "def (tidy|__init__)\\(", "path": "league"})[1])
        text, error = self.tools.call("read_file", {"path": "league/swarm/researcher.py", "start_line": float("inf")})
        self.assertTrue(error)
        self.assertTrue(self.tools.call("read_file", {"path": "league/swarm/researcher.py", "lines": float("inf")})[1])

    def test_finish_with_a_failing_guard_comes_back_to_fix(self):
        def script(kw, n):
            if n == 1:
                b, u = use(1, "edit_file", {"path": "league/swarm/researcher.py", "old_text": "> 0", "new_text": "> 1"})
            else:
                b, u = use(n, "finish", {"title": "t", "summary": "s", "predicted_effect": "p", "canary_plan": "c"})
            return reply([b], [u])
        router = FakeRouter(script)
        out = self.run_loop(router, turns=4)
        self.assertEqual(out.status, "failed")
        self.assertIn("not submitted", router.turns[-1]["messages"][-1]["content"][0]["content"])
        self.assertTrue(out.guards)


class Reviewing(unittest.TestCase):
    def test_the_exact_diff_is_checked_by_code(self):
        main = tarball("m", FILES)
        head = tarball("h", {**FILES, "league/swarm/researcher.py": TOY + "# x\n"})
        (main_h, _), (head_h, texts) = R.tar_index(main), R.tar_index(head, want=["league/swarm/researcher.py"])
        changed = R.tree_changes(main_h, head_h)
        self.assertEqual(changed, ["league/swarm/researcher.py"])
        self.assertEqual(R.mechanical(changed, texts, {"league/swarm/researcher.py": TOY + "# x\n"}), [])
        self.assertIn("bytes are not the candidate's", R.mechanical(changed, texts, {"league/swarm/researcher.py": TOY})[0])
        self.assertIn("does not carry", R.mechanical([], {}, {"league/swarm/researcher.py": TOY})[0])

    def test_a_review_is_a_verdict_or_fails_closed(self):
        files = {"league/swarm/researcher.py": (TOY, TOY + "# x\n")}
        contract = R.contract_text(lane="research", metric="train_dq_rate", key="harness:research:train_dq_rate:00",
                                   release_class="money_path")
        self.assertTrue(contract.isascii())
        self.assertIn("canary.enabled('harness:research:train_dq_rate:00'", contract)
        router = FakeRouter(verdicts=("approve",))
        got = R.review(router, request_key="k", contract=contract, files=files, claims={"title": "t"}, guards="ok",
                       second=True)
        self.assertEqual((got["ok"], got["verdict"]), (True, "approve"))
        self.assertIn("SECOND of two", router.asks[0]["user"])
        self.assertEqual(router.asks[0]["sail_profile"], None)

        class Garbled(FakeRouter):
            def ask(self, **kw):
                return {"json": None, "text": "looks fine to me", "cost_usd": 0.2}
        self.assertEqual(R.review(Garbled(), request_key="k", contract=contract, files=files, claims={}, guards="")["verdict"],
                         "reject")
        failing = FakeRouter(verdicts=(ModelError("no room", kind="no_room", held_usd=0.0),))
        self.assertFalse(R.review(failing, request_key="k", contract=contract, files=files, claims={}, guards="")["ok"])
        dear = FakeRouter(ceiling=5.0)
        got = R.review(dear, request_key="k", contract=contract, files=files, claims={}, guards="")
        self.assertEqual(got["verdict"], "reject")
        self.assertEqual(dear.asks, [])


class Helpers(unittest.TestCase):
    def test_the_attested_commit_is_the_updaters_promoted_deploy(self):
        rows = [{"release": "main-1", "stage": "start", "sha": "a" * 40},
                {"release": "main-1", "stage": "verdict", "verdict": "rolled_back", "sha": "a" * 40},
                {"release": "main-1", "stage": "promote", "ok": True, "sha": "b" * 40, "deploy": "d", "at": "2026-10-06T08:01:00Z"},
                {"release": "owner", "stage": "promote", "ok": True, "deploy": "o"}]
        self.assertEqual(E.attested_sha(rows, "main-1"), "b" * 40)
        self.assertIsNone(E.attested_sha(rows, "owner"))
        rows[2]["deploy"] = "d"
        rows.insert(0, {"release": "main-1", "stage": "start", "deploy": "d", "at": "2026-10-06T07:58:00Z"})
        began, promoted = E.deploy_window(rows, "main-1")
        self.assertEqual(promoted - began, 180)

    def test_carries_and_revert_follow_main(self):
        base = "a\nb\nc\nd\ne\nf\ng\nh\n"
        cand = base.replace("d\n", "d\nNEW\n")
        self.assertTrue(E.carries(base, cand, cand))
        self.assertFalse(E.carries(base, cand, base))
        self.assertEqual(E.revert_text(base, cand, cand), base)
        moved = cand.replace("a\n", "a0\n")
        self.assertEqual(E.revert_text(base, cand, moved), base.replace("a\n", "a0\n"))
        self.assertEqual(E.revert_text(base, cand, base), base)
        # main edited the change's context and added beside it: a three-way revert takes out only the candidate's line
        both = moved.replace("NEW\n", "NEW\nNEW2\n").replace("c\n", "c2\n")
        self.assertEqual(E.revert_text(base, cand, both), "a0\nb\nc2\nd\nNEW2\ne\nf\ng\nh\n")
        # main rewrote the candidate's own line: it cannot be taken out exactly
        two = base.replace("d\n", "d\nNEW\nNEW-B\n")
        self.assertIsNone(E.revert_text(base, two, two.replace("NEW-B\n", "NEW-B changed\n")))
        # main holds none of it any more
        self.assertEqual(E.revert_text(base, cand, base.replace("h\n", "h2\n")), base.replace("h\n", "h2\n"))

    def test_the_canary_file_keeps_other_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            E.write_arm(tmp, "harness:a", {"lane": "research", "fraction": 0.5, "salt": "s", "state": "canary"})
            E.write_arm(tmp, "harness:b", {"lane": "memory", "fraction": 0.5, "salt": "t", "state": "canary"})
            E.write_arm(tmp, "harness:a", None)
            self.assertEqual(sorted(gate.read(Path(tmp) / gate.FILE)), ["harness:b"])
            self.assertEqual((Path(tmp) / gate.FILE).stat().st_mode & 0o777, 0o600)
            # A file that does not read as schema 1 is never overwritten: every other arm would be lost.
            E.write_arm(tmp, "harness:c", {"lane": "research", "fraction": 0.5, "salt": "u", "state": "retained"})
            good = (Path(tmp) / gate.FILE).read_text()
            for broken in ("{\"schema\": 1, \"arms\": {", "[]", "{\"schema\": 2, \"arms\": {}}"):
                (Path(tmp) / gate.FILE).write_text(broken)
                with self.assertRaises(RuntimeError):
                    E.write_arm(tmp, "harness:d", {"lane": "memory", "fraction": 0.5, "salt": "v", "state": "canary"})
                self.assertEqual((Path(tmp) / gate.FILE).read_text(), broken)
            (Path(tmp) / gate.FILE).write_text(good)
            self.assertEqual(sorted(gate.read(Path(tmp) / gate.FILE)), ["harness:b", "harness:c"])

    def test_the_guard_needs_enough_trades_and_a_significant_fall(self):
        self.assertFalse(E.guard_verdict([0.1] * 5, [-0.5] * 5)["breach"])
        self.assertTrue(E.guard_verdict([0.3, 0.4, 0.5] * 5, [-0.3, -0.2, -0.1] * 5)["breach"])
        self.assertFalse(E.guard_verdict([0.3, 0.4, 0.5] * 5, [0.3, 0.5, 0.4] * 5)["breach"])

    def test_examples_and_text_are_model_and_public_safe(self):
        rows = E.scrub_examples("memory", [{"family": "fam-abc", "graveyard_row": "fam-old", "structure": "long_call",
                                            "similarity": 1.2, "mechanism": "fam-abc restates fam-old on a pin"}])
        self.assertEqual(rows[0]["mechanism"], "<family> restates <family> on a pin")
        self.assertEqual(E.scrub_examples("research", [{"signature": "x", "n": 3, "families": ["f1"]}]),
                         [{"signature": "x", "count": 3}])
        self.assertTrue(E.public_problems("account equity is 1300"))
        self.assertEqual(E.public_problems(f"base {BASE}, key harness:research:train_dq_rate:0123456789abcdef"), [])

    def test_the_memory_lanes_brief_names_its_only_gate(self):
        text = E.brief(lane="memory", row={"metric": "graveyard_rebirth_rate", "value": 0.2, "denominator": 40},
                       key="harness:memory:graveyard_rebirth_rate:00", examples=[])
        self.assertTrue(text.isascii())
        self.assertIn("inside Architect.admit", text)
        self.assertNotIn("researcher.py", text)

    def test_the_engineer_is_authored_daily_and_moved_hourly(self):
        job = by_name()["engineer"]
        self.assertEqual(sorted(t.kind for t in job.triggers), ["daily", "hourly"])
        self.assertEqual([(t.at.hour, t.at.minute) for t in job.triggers if t.kind == "daily"], [E.AUTHOR_AT])
        self.assertLessEqual(job.wall, 3600)
        self.assertTrue(E.AUTHOR_SYSTEM.isascii() and R.SYSTEM.isascii())


if __name__ == "__main__":
    unittest.main()
