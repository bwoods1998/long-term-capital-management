"""The harness loop's lanes: the protected boundary, read-only House observers, ranking, the canary gate, the offline
judges' decision, the arms comparison, and one full lane cycle through the persistent journal."""
from __future__ import annotations

import ast
import dataclasses
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from league.swarm import canary as gate
from league.swarm import harness_lanes as lanes
from league.swarm import improvement as labmod
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

REPO = Path(__file__).resolve().parents[2]
try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False


#: TEST FIXTURES shaped like the judges' held-out pools. The real pools are private (outside this repo, pinned by hash in
#: `harness_lanes.HELDOUT_POOLS`); these only exercise the machinery and share no class with them.
TEST_POOLS = {
    "research": {"schema": 1, "judge": "research",
                 "misuse": {"fixture_attr": ['{a} = ctx.fixture_attribute'], "fixture_call": ['{a} = ctx.minute()']},
                 "wraps": {"fixture_late": ['if ctx.minutes_to_close <= 60:']},
                 "load": {"fixture_load": {"extra": "{a} = [][1]\n"}},
                 "valid": {"fixture_valid": ['{a} = ctx.minute', 'STATE["{b}"] = {a}']}},
    "memory": {"schema": 1, "judge": "memory",
               "bank": ["Fixture funds rally into the fixture window and fall back once the fixture event passes.",
                        "Fixture volatility spikes before fixture announcements and collapses after the fixture print.",
                        "Fixture options on the test root misprice fixture risk around fixture holidays every season.",
                        "The fixture index drifts toward fixture strikes on fixture afternoons with heavy test interest.",
                        "Fixture skew widens after fixture selloffs and narrows over the following fixture week.",
                        "Fixture spreads between the two test funds close within a fixture month of opening wide.",
                        "Fixture gaps at the open fill within the first fixture hour on light test volume.",
                        "Fixture premium is rich into fixture reports and cheap after the fixture results.",
                        "Fixture calls in crowded test names lose value once fixture attention moves elsewhere.",
                        "Fixture breakouts on heavy test volume continue through the fixture lunch hour."],
               "novel": ["A test-only claim about lunch hours and nothing else at all in fixture land.",
                         "Another test-only claim about closing auctions in a fixture market.",
                         "A third test-only claim about roll weeks in fixture commodity funds.",
                         "A fourth test-only claim about fixture inflows and implied volatility."],
               "synonyms": {"rally": "climb", "spikes": "jumps", "drifts": "moves", "widens": "grows"},
               "seconds": ["The fixture entry waits a session.", "The fixture exit moves to the close."],
               "hedges": ["The fixture idea is unchanged."],
               "slices": [["debit_vertical", ["SPY"]], ["credit_vertical", ["QQQ"]], ["long_straddle", ["IWM"]],
                          ["iron_condor", ["SPY"]], ["long_strangle", ["QQQ"]], ["debit_vertical", ["IWM"]],
                          ["credit_vertical", ["SPY"]], ["long_butterfly", ["QQQ"]]],
               "elsewhere_roots": ["DIA"], "buried": 8, "novel_count": 4, "moved_count": 2},
    "data": {"schema": 1, "judge": "data",
             "transient": {"fixture_http599": {"type": "http", "code": 599},
                           "fixture_reset": {"type": "os", "errno": "ECONNRESET", "wrap": "url"},
                           "fixture_read": {"type": "exc", "cls": "http.client.IncompleteRead", "args": ["x", 3],
                                            "at": "read"}},
             "permanent": {"fixture_http418": {"type": "http", "code": 418},
                           "fixture_denied": {"type": "exc", "cls": "PermissionError", "args": [13, "fixture"]}}},
    "execution": {"schema": 1, "judge": "execution", "salt": "fixture", "scenarios": 2, "invalid": []},
}


def commit(repo: Path, message: str) -> str:
    labmod.git(repo, "add", ".")
    labmod.git(repo, "-c", "user.name=Harness Test", "-c", "user.email=harness@example.invalid", "commit", "-qm", message)
    return labmod.git(repo, "rev-parse", "HEAD")


def run(fid: str, status: str, n: int) -> dict:
    return {"run_id": f"{fid[:8]}{status[:4]}{n:012d}"[:24], "status": status, "trials": 1, "summary": {"train_score": 9.9}}


class Boundary(unittest.TestCase):
    def test_fingerprint_files_match_the_gym_driver(self):
        tree = ast.parse((REPO / "league/gym/driver.py").read_text())
        value = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", None) == "LEAGUE_FILES" for t in n.targets))
        self.assertEqual(tuple(value), lanes.LEAGUE_FILES)

    def test_objective_sealed_spend_capital_and_release_paths_are_protected_for_every_lane(self):
        for path, why in (("league/swarm/harness_lanes.py", "objective"), ("league/swarm/harness_judges/research.py", "objective"),
                          ("league/tests/test_swarm_store.py", "objective"), ("league/gym/fills.py", "sealed"),
                          ("league/swarm/gate.py", "sealed"), ("league/swarm/guard.py", "spend"), ("gateway/src/index.ts", "spend"),
                          ("league/live/money.py", "capital"), ("league/constitution.py", "capital"), (".github/workflows/ci.yml", "release")):
            self.assertEqual(lanes.protected_reason(path), why, path)
        self.assertIsNone(lanes.protected_reason("league/tests/test_harness_candidate_preflight.py"))
        for lane in lanes.LANES.values():
            for pattern in lane.surface:
                if "*" not in pattern:
                    self.assertIsNone(lanes.protected_reason(pattern), f"{lane.id} surface {pattern} is protected")
        for path in ("league/live/real.py", "league/live/venue.py", "league/live/state.py", "league/live/paper.py"):
            self.assertEqual(lanes.protected_reason(path), "capital", "the real-money order path and the real book")
            self.assertNotIn(path, lanes.LANES["execution"].surface)
        self.assertNotIn("league/CONTRACT.md", lanes.LANES["research"].surface, "prose cannot be gated per family")
        self.assertNotIn("league/swarm/pool.py", lanes.LANES["data"].surface, "the pool writes the data lane's own metric")
        with self.assertRaisesRegex(labmod.ImprovementError, "protected"):
            lanes.surface_check(lanes.LANES["research"], ["league/swarm/researcher.py", "league/swarm/guard.py"])
        with self.assertRaisesRegex(labmod.ImprovementError, "outside"):
            lanes.surface_check(lanes.LANES["research"], ["league/swarm/architect.py"])
        lanes.surface_check(lanes.LANES["memory"], ["league/swarm/architect.py", "league/tests/test_harness_candidate_x.py"])

    def test_content_guard_refuses_new_processes_network_reflection_and_protected_imports(self):
        before = "import json\n\ndef f(x):\n    return json.dumps(x).replace('a', 'b')\n"
        lanes.content_guard("league/swarm/researcher.py", before, before + "\ndef g(y):\n    return sorted(y)\n")
        for added, pattern in (("import subprocess\n", "subprocess"), ("from . import guard\n", "guard"),
                               ("from ..live import money\n", "money"), ("x = eval('1')\n", "eval"),
                               ("open('/tmp/x', 'w')\n", "open"), ("import atexit\n", "atexit"),
                               ("import builtins\n", "builtins"), ("import inspect\n", "inspect"),
                               ("print('{}')\n", "print"), ("import sys\n", "sys")):
            with self.assertRaisesRegex(labmod.ImprovementError, pattern):
                lanes.content_guard("league/swarm/researcher.py", before, before + added)
        lanes.content_guard("league/CONTRACT.md", None, "import subprocess")  # prose is not code

    def test_content_guard_counts_calls_and_refuses_forgery_routes(self):
        path = "league/sailbox.py"
        before = "import os\nimport sys\n\ndef f(o, p):\n    setattr(o, 'a', 1)\n    return open(p).read()\n"
        lanes.content_guard(path, before, before.replace("def f(o, p):", "def f(o, p):\n    x = 1"))  # moved, not added
        for added, pattern in (("\ndef g(o, p):\n    setattr(o, 'b', 2)\n", "setattr"),
                               ("\ndef g(p):\n    return open(p, 'w')\n", "open"),
                               ("\ndef g():\n    return sys.modules\n", "plumbing"),
                               ("\ndef g():\n    return sys.argv\n", "plumbing"),
                               ("\ndef g():\n    return os.environ\n", "plumbing"),
                               ("\ndef g(o):\n    return o.__dict__\n", "reflective"),
                               ("\ndef g():\n    return sys.exc_info()\n", "plumbing"),
                               ("\ndef g(e):\n    return e.tb_frame.f_back.f_locals\n", "reflective"),
                               ("\nclass C:\n    def g(self):\n        self.settings['gym'] = {}\n", "another object"),
                               ("\nclass C:\n    def g(self):\n        self.settings.update(gym={})\n", "another object"),
                               ("\ndef g(m):\n    m.value = 3\n", "another object"),
                               ("\nclass C:\n    def run(self):\n        return 1\n    def swap(self):\n        self.run = None\n",
                                "another object"),
                               ("\ndef g(c):\n    c._FORCED['k'] = True\n", "override"),
                               ("\nfrom league.swarm import canary\n\ndef g():\n    return canary.decide({}, 'k', 'u')\n", "canary"),
                               ("\nfrom league.swarm.canary import _CACHE\n", "canary"),
                               ("\nimport league.swarm.canary\n", "canary")):
            with self.assertRaisesRegex(labmod.ImprovementError, pattern, msg=added):
                lanes.content_guard(path, before, before + added)
        lanes.content_guard(path, before, before + "\nfrom league.swarm import canary\n\ndef g(u):\n"
                            "    return canary.enabled('k', canary.mechanism_unit(u), root='.')\n")
        with self.assertRaisesRegex(labmod.ImprovementError, "fingerprint"):
            lanes.content_guard("league/live/shadow.py", "X = 1\n", "from league.swarm import canary\nX = 1\n")

    def test_content_guard_counts_every_use_of_a_name_so_aliases_and_members_cannot_hide_one(self):
        """The second review's probes: aliased imports, a reference kept for later, dynamic attribute access, file moves,
        process replacement, a process module's members, store writes, sealed reads, raw SQL, a collaborator's internals."""
        path = "league/swarm/researcher.py"
        before = ("import json\nimport os\nimport subprocess\n\n\nclass R:\n    def f(self, fam, text):\n"
                  "        self.store.note(fam['id'], text.replace('a', 'b'))\n        rows = self.store._all('SELECT 1')\n"
                  "        return os.path.join('a', json.dumps(rows))\n")
        lanes.content_guard(path, before, before.replace("text.replace('a', 'b')", "text.replace('b', 'c')"))
        for added, pattern in (
                ("from os import system as _sh, write as _emit\n", "system"),
                ("from os import environ as _env\n", "plumbing"),
                ("from operator import attrgetter as _ag\n", "attrgetter"),
                ("import operator\nX = operator.attrgetter('_FOR' + 'CED')\n", "attrgetter"),
                ("F = os.system\n", "system"),
                ("def g(p, q):\n    return os.remove(p)\n", "members"),
                ("def g(p, q):\n    return os.replace(p, q)\n", "members"),
                ("def g(p, q):\n    return p.replace(q)\n", "replace/1"),
                ("def g(p):\n    return p.rename('x')\n", "rename"),
                ("def g(p):\n    return p.touch()\n", "touch"),
                ("def g(p):\n    return p.mkdir()\n", "mkdir"),
                ("def g(a):\n    return os.execv('/bin/sh', a)\n", "execv"),
                ("def g(a):\n    return os.posix_spawn('/bin/sh', a, {})\n", "posix_spawn"),
                ("def g(a):\n    return subprocess.run(a)\n", "members"),
                ("import os as o\n", "alias"),
                ("class S:\n    def g(self, fid):\n        self.store.set_state(fid, robust_failed=[], drift_failed={})\n",
                 "store writes"),
                ("class S:\n    def g(self, fid):\n        self.store.update_family(fid, lineage=None, parent=None)\n",
                 "store writes"),
                ("class S:\n    def g(self, fid):\n        self.store.bump(fid, trials=-1)\n", "store writes"),
                ("class S:\n    def g(self, fid):\n        return self.store.looks()\n", "holdout"),
                ("class S:\n    def g(self):\n        return self.store._db\n", "private"),
                ("class S:\n    def g(self):\n        return self.store._all('DELETE FROM runs')\n", "SQL"),
                ("def g(db):\n    return db.execute('SELECT * FROM looks')\n", "SQL")):
            with self.assertRaisesRegex(labmod.ImprovementError, pattern, msg=added):
                lanes.content_guard(path, before, before + "\n" + added)
        reworded = ("def reject(why):\n    return {'reason': 'no chain for the leg'}\n", "def reject(why):\n    return "
                    "{'reason': 'the leg is absent'}\n")
        with self.assertRaisesRegex(labmod.ImprovementError, "reject reasons"):
            lanes.content_guard("league/live/chains.py", *reworded)
        lanes.content_guard("league/live/chains.py", reworded[0], reworded[0] + "\nX = 'no quote yet'\n")

    def test_live_path_follows_live_imports_and_module_level_closures(self):
        modules = lanes.live_path_modules(REPO)
        for path in ("league/live/step.py", "league/gym/engine.py", "league/swarm/gate.py", "league/swarm/bands.py",
                     "league/constitution.py", "league/swarm/researcher.py"):
            self.assertIn(path, modules)
        self.assertNotIn("league/live/__main__.py", modules)
        self.assertNotIn("league/swarm/architect.py", modules)
        found = lanes.classify(["league/swarm/architect.py"], modules)
        self.assertEqual(found["release_class"], "research")
        self.assertEqual(lanes.classify(["league/swarm/researcher.py", "league/swarm/architect.py"], modules)["release_class"],
                         "money_path")
        self.assertEqual(lanes.classify(["league/live/shadow.py"], modules)["release_class"], "evidence_reset")


class Frozen(unittest.TestCase):
    """The multiple-testing control, eligibility, the screens and the records the lanes measure are no lane's lever."""

    def source(self, path):
        return (REPO / path).read_text()

    def test_the_reviewers_probes_are_refused(self):
        architect = self.source("league/swarm/architect.py")
        researcher = self.source("league/swarm/researcher.py")
        with self.assertRaisesRegex(labmod.ImprovementError, "SAME_IDEA is frozen"):
            lanes.symbol_guard("league/swarm/architect.py", architect, architect.replace("SAME_IDEA = 0.5", "SAME_IDEA = 0.99", 1))
        loosened = researcher.replace("        if verdict is not None and verdict[\"known\"] and not verdict[\"passed\"]:\n"
                                      "            return False, f\"its version fails the drift screen: {verdict['why']}\"\n", "", 1)
        self.assertNotEqual(loosened, researcher)
        with self.assertRaisesRegex(labmod.ImprovementError, "eligible_run is frozen"):
            lanes.symbol_guard("league/swarm/researcher.py", researcher, loosened)
        skipped = researcher.replace("        recorded, robust = self._with_score(result, stress)  # the run's row keeps its score (`submit` reads it)\n",
                                     "        recorded, robust = self._with_score(result, stress)  # the run's row keeps its score (`submit` reads it)\n"
                                     "        if result.get(\"status\") == \"disqualified\":\n            return {}\n", 1)
        self.assertNotEqual(skipped, researcher)
        with self.assertRaisesRegex(labmod.ImprovementError, "_gym_run writes trial"):
            lanes.symbol_guard("league/swarm/researcher.py", researcher, skipped)
        shadowed = researcher + "\n\ndef same_idea(a, b):\n    return False\n"
        lanes.symbol_guard("league/swarm/researcher.py", researcher, shadowed)  # researcher has no same_idea to shadow
        with self.assertRaisesRegex(labmod.ImprovementError, "frozen"):
            lanes.symbol_guard("league/swarm/architect.py", architect, architect + "\n\ndef same_idea(a, b):\n    return False\n")

    def test_the_stores_general_writers_raw_sql_and_the_programs_path_are_frozen(self):
        """The third review's probes: a gated `_admit` that detaches a lineage, zeroes or lowers trial counters, clears
        the robustness and drift marks eligibility reads, or deletes runs with raw SQL; a tool call's program rewritten
        on its way to the Gym (its decide wrapped so runtime errors never disqualify it)."""
        researcher = self.source("league/swarm/researcher.py")
        anchor = "        why = check_code(code)\n"
        self.assertEqual(researcher.count(anchor), 1)
        for write in ('self.store.update_family(fam["id"], lineage=fam["id"], parent=None)',
                      'self.store.update_family(fam["id"], trials=0, since_val_trials=0)',
                      'self.store.bump(fam["id"], trials=-1)',
                      'self.store.set_state(fam["id"], robust_failed=[], drift_failed={})',
                      'self.store._exec("DELETE FROM runs WHERE family=? AND status=\'disqualified\'", (fam["id"],))'):
            probe = researcher.replace(anchor, "        if canary.enabled('k', canary.mechanism_unit(fam['mechanism']), "
                                       f"root=self.store.root):\n            {write}\n" + anchor, 1)
            with self.assertRaisesRegex(labmod.ImprovementError, "new writer", msg=write):
                lanes.symbol_guard("league/swarm/researcher.py", researcher, probe)
            with self.assertRaisesRegex(labmod.ImprovementError, "store writes|private|SQL", msg=write):
                lanes.content_guard("league/swarm/researcher.py", researcher, probe)
        call = 'result = self._execute(fam, tool, pending.get("arguments") or {}, out, author=pending.get("author") or "model")'
        self.assertEqual(researcher.count(call), 1)
        armored = researcher.replace(call, call.replace('pending.get("arguments") or {}',
                                                        '_armored(pending.get("arguments") or {})'), 1)
        with self.assertRaisesRegex(labmod.ImprovementError, "_model_cycle"):
            lanes.symbol_guard("league/swarm/researcher.py", researcher, armored)
        claude = self.source("league/swarm/claude_research.py")
        old = "            args, error = validate(schemas[name], use.input)\n"
        self.assertEqual(claude.count(old), 1)
        with self.assertRaisesRegex(labmod.ImprovementError, "tool_calls is frozen"):
            lanes.symbol_guard("league/swarm/claude_research.py", claude,
                               claude.replace(old, old + "            args = _armored(args)\n", 1))
        shadow = self.source("league/live/shadow.py")
        old = '        self.practice_event("rejected", {"reason": str(why)[:1000]})\n'
        self.assertEqual(shadow.count(old), 1)
        with self.assertRaisesRegex(labmod.ImprovementError, "_reject"):
            lanes.symbol_guard("league/live/shadow.py", shadow,
                               shadow.replace(old, old.replace("str(why)", "str(why).replace('no chain', 'absent')"), 1))

    def test_admission_may_refuse_more_but_never_change_what_it_admits(self):
        architect = self.source("league/swarm/architect.py")
        anchor = "            cited = self.differs(row, known)\n"
        self.assertIn(anchor, architect)
        refusing = architect.replace(anchor, "            if len(mechanism) > 590:\n                continue\n" + anchor, 1)
        lanes.symbol_guard("league/swarm/architect.py", architect, refusing)
        for old, new in (("            prior = slice_priors(dead, structure) if dead and not parent else None\n",
                          "            prior = None\n"),
                         ("            mechanism = \" \".join(str(row.get(\"mechanism\") or \"\").split())[:600]\n",
                          "            mechanism = \" \".join(str(row.get(\"mechanism\") or \"\").split())[:600] + \" v2\"\n"),
                         (anchor, "            row[\"parent\"] = None\n" + anchor),
                         (anchor, "            spec_extra = spec.update\n            spec.update({})\n" + anchor)):
            self.assertIn(old, architect)
            with self.assertRaisesRegex(labmod.ImprovementError, "admits"):
                lanes.symbol_guard("league/swarm/architect.py", architect, architect.replace(old, new, 1))
        wrapped = architect.replace("                fam = self.store.add_family(spec, origin=\"architect\", parent=parent, prior_lineage=prior)\n",
                                    "                if parent:\n"
                                    "                    fam = self.store.add_family(spec, origin=\"architect\", parent=parent, prior_lineage=prior)\n", 1)
        with self.assertRaisesRegex(labmod.ImprovementError, "writes"):
            lanes.symbol_guard("league/swarm/architect.py", architect, wrapped)
        with self.assertRaisesRegex(labmod.ImprovementError, "new writer"):
            lanes.symbol_guard("league/swarm/architect.py", architect,
                               architect + "\n\ndef extra(store, fid):\n    store.bury(fid, 'x')\n")


class GateCoverage(unittest.TestCase):
    KEY = "harness:research:train_dq_rate:0123456789abcdef"
    BASE = "import json\n\nLIMIT = 3\n\n\nclass R:\n    def admit(self, fam, code):\n        why = None\n        return why\n"

    def gated(self, new_branch="            why = 'refused'\n", orelse=""):
        return self.BASE.replace("        why = None\n", "        why = None\n"
                                 f"        if canary.enabled('{self.KEY}', fam['id'], root=self.store.root):\n"
                                 + new_branch + orelse)

    def test_a_gated_change_with_new_definitions_passes_and_counts_its_gates(self):
        head = ("from league.swarm import canary\n" + self.gated("            why = _screen(code)\n")
                + "\n\nNEW_TEXT = 'a new prompt line'\n\n\ndef _screen(code):\n    return None if code else 'empty'\n")
        self.assertEqual(lanes.gate_coverage("league/swarm/researcher.py", self.BASE, head, self.KEY), 1)
        old_branch = self.BASE.replace("        why = None\n", f"        if canary.enabled('{self.KEY}', fam['id'], root=self.store.root):\n"
                                       "            why = 'refused'\n        else:\n            why = None\n")
        self.assertEqual(lanes.gate_coverage("league/swarm/researcher.py", self.BASE, old_branch, self.KEY), 1)
        expression = self.BASE.replace("        why = None\n", f"        why = 'r' if canary.enabled('{self.KEY}', fam['id'], "
                                       "root=self.store.root) else None\n")
        self.assertEqual(lanes.gate_coverage("league/swarm/researcher.py", self.BASE, expression, self.KEY), 1)

    def test_ungated_changes_are_refused(self):
        for head in (self.BASE.replace("LIMIT = 3", "LIMIT = 4"),
                     self.BASE.replace("        return why\n", "        return why or 'x'\n"),
                     self.gated() + "\n\n@register\ndef hook():\n    return 1\n",
                     self.gated() + "\n\nREGISTRY = dict(a=1)\n",
                     self.gated().replace(self.KEY, "harness:other:key:0123456789abcdef")):
            with self.assertRaisesRegex(labmod.ImprovementError, "not every change is gated"):
                lanes.gate_coverage("league/swarm/researcher.py", self.BASE, head, self.KEY)
        with self.assertRaisesRegex(labmod.ImprovementError, "Python"):
            lanes.gate_coverage("league/CONTRACT.md", "a", "b", self.KEY)
        self.assertEqual(lanes.gate_coverage("league/swarm/researcher.py", self.BASE, self.gated(), self.KEY, "family"), 1)
        by_code = self.gated().replace("fam['id']", "code")
        with self.assertRaisesRegex(labmod.ImprovementError, "unit"):
            lanes.gate_coverage("league/swarm/researcher.py", self.BASE, by_code, self.KEY, "family")
        with self.assertRaisesRegex(labmod.ImprovementError, "mechanism_unit"):
            lanes.gate_coverage("league/swarm/researcher.py", self.BASE, self.gated(), self.KEY, "mechanism")

    def test_a_new_definition_may_not_rebind_a_name_existing_code_uses(self):
        """The third review's probes: a new top-level def or constant under an imported, builtin or used name changes
        what existing code (a frozen function included) calls, with the gate closed."""
        base = ("from .store import LONG_SINGLE, same_slice\n\n\nclass A:\n    def admit(self, fam, a, b):\n"
                "        why = None\n        return same_slice(a, b) and round(fam['x']) and LONG_SINGLE and why\n")
        gated = base.replace("        why = None\n", "        why = None\n"
                             f"        if canary.enabled('{self.KEY}', fam['id'], root=self.store.root):\n"
                             "            why = _helper(a)\n")
        self.assertEqual(lanes.gate_coverage("league/swarm/architect.py", base,
                                             gated + "\n\ndef _helper(a):\n    return a\n", self.KEY), 1)
        for extra in ("LONG_SINGLE = 'none'\n", "def same_slice(a, b):\n    return a == b\n",
                      "def round(x, n=0):\n    return x\n", "from .fake import same_slice\n", "import json as same_slice\n",
                      "def admit(x):\n    return x\n"):
            with self.assertRaisesRegex(labmod.ImprovementError, "not every change is gated", msg=extra):
                lanes.gate_coverage("league/swarm/architect.py", base, gated + "\n\n" + extra
                                    + "\n\ndef _helper(a):\n    return a\n", self.KEY)

    def test_the_mechanism_unit_is_the_admitted_text_or_a_familys(self):
        base = "class Architect:\n    def admit(self, row):\n        mechanism = row['m']\n        return mechanism\n\n" \
               "    def brief(self, mechanism):\n        return mechanism\n"
        key = "harness:memory:graveyard_rebirth_rate:0123456789abcdef"

        def gate(arg, where="admit"):
            anchor = f"    def {where}(self, " + ("row):\n        mechanism = row['m']\n" if where == "admit" else "mechanism):\n")
            return base.replace(anchor, anchor + f"        if canary.enabled('{key}', canary.mechanism_unit({arg}), "
                                "root=self.store.root):\n            return None\n", 1)

        path = "league/swarm/architect.py"
        self.assertEqual(lanes.gate_coverage(path, base, gate("mechanism"), key, "mechanism"), 1)
        for head in (gate("row['m']"), gate("mechanism", where="brief"), gate("mechanism + 'x'")):
            with self.assertRaisesRegex(labmod.ImprovementError, "unit"):
                lanes.gate_coverage(path, base, head, key, "mechanism")
        family = "def f(fam):\n    return fam\n"
        head = family.replace("    return fam\n", f"    if canary.enabled('{key}', canary.mechanism_unit(fam['mechanism']), "
                              "root='.'):\n        return None\n    return fam\n")
        self.assertEqual(lanes.gate_coverage("league/swarm/researcher.py", family, head, key, "mechanism"), 1)


class Gate(unittest.TestCase):
    def test_arm_split_is_deterministic_and_near_its_fraction(self):
        units = [f"family-{n}" for n in range(4000)]
        chosen = [u for u in units if gate.in_arm("salt", "key", u, 0.25)]
        self.assertEqual(chosen, [u for u in units if gate.in_arm("salt", "key", u, 0.25)])
        self.assertLess(abs(len(chosen) / len(units) - 0.25), 0.03)
        self.assertNotEqual(chosen, [u for u in units if gate.in_arm("other", "key", u, 0.25)])
        self.assertFalse(gate.in_arm("salt", "key", "x", 0))
        self.assertFalse(gate.in_arm("salt", "key", "x", "nan"))

    def test_gate_fails_closed_and_follows_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(gate.enabled("k", "u", root=root))
            (root / "harness").mkdir()
            (root / gate.FILE).write_text("{not json")
            gate._CACHE.entries.clear()
            self.assertFalse(gate.enabled("k", "u", root=root))
            for state, expected in (("retained", True), ("reverted", False), ("bogus", False)):
                (root / gate.FILE).write_text(json.dumps({"schema": 1, "arms": {"k": {"state": state, "salt": "s", "fraction": 1.0}}}))
                gate._CACHE.entries.clear()
                self.assertEqual(gate.enabled("k", "u", root=root), expected, state)
            (root / gate.FILE).write_text(json.dumps({"schema": 1, "arms": {"k": {"state": "canary", "salt": "s", "fraction": 1.0}}}))
            gate._CACHE.entries.clear()
            self.assertTrue(gate.enabled("k", "u", root=root))
            self.assertFalse(gate.enabled("other", "u", root=root))
        self.assertEqual(gate.mechanism_unit("A  claim.\nMore"), gate.mechanism_unit("a claim. more"))
        long = "word " * 200
        self.assertEqual(gate.mechanism_unit(long), gate.mechanism_unit(" ".join(long.split())[:600]),
                         "the gate at proposal time and the observer after the birth agree on a long mechanism")

    def test_only_the_judges_override_forces_a_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(gate.enabled("k", "u", root=temp))
            gate._FORCED["k"] = True
            self.addCleanup(gate._FORCED.clear)
            with patch.object(gate, "_JUDGED", False):
                # On the House (no judges' sandbox marker) nothing a candidate does to the override counts.
                self.assertFalse(gate.enabled("k", "u", root=temp))
            patcher = patch.object(gate, "_JUDGED", True)
            patcher.start()
            self.addCleanup(patcher.stop)
            self.assertTrue(gate.enabled("k", "u", root=temp))
            gate._FORCED["k"] = False
            (Path(temp) / "harness").mkdir()
            (Path(temp) / gate.FILE).write_text(json.dumps({"schema": 1, "arms": {"k": {"state": "retained"}}}))
            gate._CACHE.entries.clear()
            self.assertFalse(gate.enabled("k", "u", root=temp), "forced closed beats a retained file")


class House(unittest.TestCase):
    """A synthetic House state: the observers read only operational counts and never write."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "state"
        self.clock = Clock(1_790_000_000.0)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)

    def family(self, fid, mechanism, structure="debit_vertical", roots=("SPY",)):
        return self.store.add_family({"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots)},
                                     origin="architect")["id"]

    def research(self):
        for n in range(3):
            fid = self.family(f"fam-{n}", f"A distinct mechanism number {n} about opening drives and fades.")
            for k in range(10):
                status = "disqualified" if k < 3 + n else "ok"
                result = run(fid, status, k)
                if status == "disqualified":
                    result = {**result, "runtime": {"disqualified": "25 errors (first: line 7: AttributeError: 'list' object "
                                                                    "has no attribute 'items')", "messages": []}}
                row = self.store.add_run(fid, 1, result, window="train", stress=1.0, purpose="train")
                # the store may suffix a worker id; the observer still joins the cycle to its run
                self.store.event("swarm.cycle", fid, {"run_id": result["run_id"], "gym_seconds": 100.0, "cost_usd": 0.01,
                                                      "trials": 1, "model_calls": 1, "score": 7.7, "note": "private words"})
                self.assertTrue(row["run_id"])
                self.clock.advance(5)
            self.store.add_spend("sail_model", 1.0, family=fid)
        self.store.add_spend("gym_box", 0.5, detail={"box": "sb_1", "seconds": 600.0, "jobs": 8})
        self.store.event("swarm.pool", None, {"action": "batch_failed", "box": "sb_1", "jobs": 8,
                                              "error": "GymError: download failed on sb_1: sailbox transport failed: TimeoutError"})

    def test_research_and_data_counts_join_cycles_to_runs_and_hide_scores(self):
        self.research()
        self.clock.advance(60)
        doc = lanes.measure(self.root, now=self.clock(), seconds=3600)
        metrics = doc["lanes"]["research"]["metrics"]
        self.assertEqual(metrics["tallies"]["train_runs"], 30)
        self.assertEqual(metrics["tallies"]["dq_runs"], 12)
        self.assertAlmostEqual(metrics["train_dq_rate"], 0.4)
        self.assertEqual(metrics["tallies"]["wasted_gym_seconds"], 1200.0)
        self.assertEqual(doc["lanes"]["research"]["join"]["unmatched"], 0)
        self.assertIn("'list' object has no attribute 'items'", doc["lanes"]["research"]["examples"][0]["signature"])
        data = doc["lanes"]["data"]["metrics"]
        self.assertEqual((data["tallies"]["slots"], data["tallies"]["slots_failed"]), (8.0, 8.0))
        text = json.dumps(doc)
        for secret in ("7.7", "9.9", "private words", "train_score"):
            self.assertNotIn(secret, text)

    def test_zero_trade_ok_runs_are_counted_and_odd_results_never_lose_the_measurement(self):
        self.research()
        fid = self.family("fam-armored", "Another distinct mechanism about closing auctions and imbalances.")
        for k in range(4):
            self.store.add_run(fid, 1, {**run(fid, "ok", k), "summary": {"trades": 0 if k < 3 else 5, "train_score": 1.0}},
                               window="train", stress=1.0, purpose="train")
        # Every kept result's deflate data corrupted: an invalid block raises zlib.error, which is no OSError.
        kept = sorted(self.store.runs_dir.glob("*.json.gz"))
        self.assertTrue(kept)
        for path in kept:
            path.write_bytes(path.read_bytes()[:10] + b"\xff\xff\xff\xff\xff")
        self.assertIsNone(lanes._read_runtime(kept[0]))
        self.clock.advance(60)
        doc = lanes.measure(self.root, now=self.clock(), seconds=3600)
        self.assertEqual(doc["errors"], {})
        tallies = doc["lanes"]["research"]["metrics"]["tallies"]
        self.assertEqual(tallies["ok_zero_trade_runs"], 3.0)
        self.assertAlmostEqual(doc["lanes"]["research"]["metrics"]["zero_trade_ok_rate"], 3 / (18 + 4), places=5)
        with patch.object(lanes, "_read_runtime", side_effect=AssertionError("examples=0 reads no result")):
            quiet = lanes.measure(self.root, now=self.clock(), seconds=3600, examples=0)
        self.assertEqual((quiet["lanes"]["research"]["sampled_disqualified"], quiet["lanes"]["research"]["examples"]), (0, []))
        with patch.object(lanes, "_research", side_effect=RuntimeError("odd data")):
            partial = lanes.measure(self.root, now=self.clock(), seconds=3600)
        self.assertIn("RuntimeError", partial["errors"]["research"])
        self.assertIn("memory", partial["lanes"], "one lane's failure never loses the others")

    def test_measure_opens_every_database_read_only(self):
        self.research()
        self.store.close()
        before = {p.name: p.stat().st_mtime_ns for p in self.root.iterdir()}
        real = sqlite3.connect
        opened = []

        def guarded(database, *args, **kwargs):
            opened.append(str(database))
            if not (kwargs.get("uri") and "mode=ro" in str(database)):
                raise PermissionError(f"writable open of {database}")
            return real(database, *args, **kwargs)

        with patch.object(lanes.sqlite3, "connect", side_effect=guarded):
            lanes.measure(self.root, now=self.clock() + 60, seconds=3600)
        self.assertTrue(opened)
        self.assertEqual(before, {p.name: p.stat().st_mtime_ns for p in self.root.iterdir()}, "no file written or created")

    def test_rebirths_follow_the_frozen_first_sentence_detector_on_the_same_slice(self):
        dead = self.family("dead-one", "SMH implied vol is bid through the weeks when the leaders report. Sell the premium after.")
        self.store.retire(dead, "refuted")
        self.store.bury(dead, "refuted")
        self.clock.advance(7200)
        self.family("reborn", "SMH implied vol is bid through the weeks when leaders report. Buy the wings instead now.")
        self.family("other-slice", "SMH implied vol is bid through the weeks when leaders report. Buy the wings.",
                    roots=("QQQ",))
        self.family("new-idea", "Treasury auctions with weak demand push long yields up into the close of the day.")
        doc = lanes.measure(self.root, now=self.clock() + 60, seconds=3600, lanes=["memory"])
        tallies = doc["lanes"]["memory"]["metrics"]["tallies"]
        self.assertEqual((tallies["births"], tallies["rebirths"]), (3.0, 1.0))
        self.assertEqual(doc["lanes"]["memory"]["examples"][0]["family"], "reborn")
        self.assertGreaterEqual(lanes.same_idea("A claim about vol. X.", "A claim about vol. Y."), 1.0)

    def test_execution_counts_practice_rejects_by_cause_and_restart_recovery(self):
        now = self.clock()
        obs = sqlite3.connect(self.root / "observe.sqlite")
        obs.execute("CREATE TABLE events (instance TEXT, account TEXT, event_id INTEGER, family TEXT, version INTEGER, day TEXT,"
                    " minute INTEGER, kind TEXT, body TEXT, recorded_at REAL)")
        rows = [("f1", "intent", "{}")] * 10 + [("f1", "rejected", json.dumps({"reason": "no quote for the leg now"})),
                                               ("f1", "rejected", json.dumps({"reason": "max_loss 150 buys none"}))]
        obs.executemany("INSERT INTO events VALUES ('i','a',?,?,1,'d',0,?,?,?)",
                        [(n, fam, kind, body, now + n) for n, (fam, kind, body) in enumerate(rows)])
        obs.commit()
        obs.close()
        live = sqlite3.connect(self.root / "live.sqlite")
        live.execute("CREATE TABLE orders (status TEXT, placed_at REAL)")
        live.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, at REAL, kind TEXT, payload TEXT)")
        live.execute("INSERT INTO events(at, kind, payload) VALUES (?, 'live.instance', ?)", (now + 30, json.dumps({"state": "live"})))
        live.execute("INSERT INTO events(at, kind, payload) VALUES (?, 'live.error', '{}')", (now + 4000,))
        live.commit()
        live.close()
        ledger = sqlite3.connect(self.root / "ledger.sqlite")
        ledger.execute("CREATE TABLE ledger (seq INTEGER PRIMARY KEY, kind TEXT, at TEXT, payload TEXT)")
        for at in (now, now + 3900):
            ledger.execute("INSERT INTO ledger(kind, at, payload) VALUES ('ops.started', ?, ?)", (lanes.iso(at), json.dumps({"release": "r"})))
        ledger.commit()
        ledger.close()
        doc = lanes.measure(self.root, now=now + 7200, seconds=7200 + 1, lanes=["execution"])
        tallies = doc["lanes"]["execution"]["metrics"]["tallies"]
        self.assertEqual((tallies["intents"], tallies["rejects"], tallies["harness_rejects"], tallies["feasibility_rejects"]),
                         (10.0, 2.0, 1.0, 1.0))
        self.assertEqual((tallies["restarts"], tallies["restart_failures"]), (2.0, 1.0))
        self.assertEqual([s["release"] for s in doc["start_releases"]], ["r", "r"], "each start names its release")
        self.assertEqual(lanes.reject_class("a malformed intent: TypeError"), "program")


class Ranking(unittest.TestCase):
    def measurement(self, **research):
        units = {"a": {"train_runs": 400.0, "dq_runs": 60.0, "ok_runs": 340.0, "gym_seconds": 4000.0,
                       "wasted_gym_seconds": 900.0, "births": 2.0, **research}}
        return {"schema": 1, "policy": lanes.POLICY, "since": 0.0, "until": 86400.0,
                "window": {"since": "x", "until": "y", "seconds": 86400}, "source": {"digest": "d" * 64},
                "lanes": {"research": {"units": units, "spend": {"sail_model": 10.0}, "examples": []},
                          "data": {"units": {"sb": {"gym_usd": 40.0, "gym_seconds": 1000.0, "slots": 1000.0, "slots_failed": 1.0,
                                                    "ok_slots": 999.0}}, "run_totals": {"runs": 10.0, "error_runs": 0.0},
                                   "examples": []}}}

    def test_thresholds_rank_and_explain(self):
        ranked = lanes.rank(self.measurement())
        self.assertEqual(ranked[0]["lane"], "research")
        self.assertTrue(ranked[0]["captured"])
        self.assertAlmostEqual(ranked[0]["value"], 0.15)
        self.assertEqual(ranked[0]["stake"]["usd_per_day"], round(40.0 * 900 / 4000, 2))
        self.assertTrue(ranked[0]["payback"]["pays"])
        data = next(r for r in ranked if r["lane"] == "data")
        self.assertFalse(data["captured"])
        self.assertIn("not past", data["why_not"])
        few = lanes.rank(self.measurement(train_runs=100.0, dq_runs=50.0))
        self.assertFalse(next(r for r in few if r["lane"] == "research")["captured"], "under the minimum denominator")
        cheap = self.measurement(wasted_gym_seconds=40.0)
        research = next(r for r in lanes.rank(cheap) if r["lane"] == "research")
        self.assertFalse(research["captured"], "a bottleneck that cannot repay a cycle is not one")
        self.assertIn("pay back", research["why_not"])


class Decisions(unittest.TestCase):
    lane = lanes.LANES["research"]
    bottleneck = lane.bottlenecks[0]

    def units(self, n, dq, *, prefix, runs=20, usd=1.0, cycles=50, errors=0):
        return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "research_usd": usd, "births": 1,
                                 "wasted_gym_seconds": dq * 100.0, "cycles": cycles, "cycle_errors": errors} for k in range(n)}

    def test_a_clear_canary_improvement_is_retained(self):
        out = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t"), self.units(20, 4, prefix="c"), seed="s")
        self.assertEqual(out["decision"], "retained", out)
        self.assertLess(out["primary"]["p_value"], 0.05)

    def test_no_effect_guard_breach_and_thin_arms(self):
        same = lanes.retention(self.lane, self.bottleneck, self.units(20, 3, prefix="t"), self.units(20, 3, prefix="c"), seed="s")
        self.assertEqual(same["decision"], "revert_recommended")
        costly = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t", usd=5.0),
                                 self.units(20, 4, prefix="c"), seed="s")
        self.assertEqual(costly["decision"], "revert_recommended")
        self.assertFalse(next(c for c in costly["checks"] if c["metric"] == "ok_runs_per_usd")["ok"])
        noisy = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t", errors=5), self.units(20, 4, prefix="c"),
                                seed="s")
        self.assertEqual(noisy["decision"], "revert_recommended", "a guard rising from zero is a breach")
        thin = lanes.retention(self.lane, self.bottleneck, self.units(2, 0, prefix="t", runs=2), self.units(2, 1, prefix="c", runs=2),
                               seed="s")
        self.assertEqual(thin["decision"], "insufficient_activity")

    def test_group_counts_use_an_exact_test(self):
        restart = lanes.LANES["execution"].bottleneck("restart_failure_rate")
        good = lanes.compare(restart.metric, {}, {}, seed="s", extra_treated={"restart_failures": 0, "restarts": 12},
                             extra_control={"restart_failures": 6, "restarts": 12})
        self.assertEqual(good["test"], "fisher_exact_one_sided")
        self.assertLess(good["p_value"], 0.05)
        self.assertAlmostEqual(lanes.fisher_less(0, 3, 1, 3), 0.5)

    def trees(self, base, head, *, base_exit=0, head_exit=0, closed=None):
        def tree(metrics, exit):
            return {"regressions": {"exit": exit}, "splits": {s: {"metrics": dict(metrics)} for s in ("dev", "heldout")}}

        return {"base": tree(base, base_exit), "closed": tree(base if closed is None else closed, head_exit),
                "open": tree(head, head_exit)}

    def research(self, reaching, screen):
        return {"gym_seconds_wasted": reaching * 130.0, "broken_reaching_gym": reaching, "broken_cases": 31, "cases": 45,
                "false_refusals": 0, "screen_cpu_seconds": screen}

    def test_offline_verdict_needs_heldout_improvement_safety_and_cost(self):
        base = self.research(29, 0.1)
        ok = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, self.research(20, 5.6)))
        self.assertTrue(ok["passed"], ok)
        slow = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, self.research(20, 45 * 0.3)))
        self.assertIn("cap", " ".join(slow["reasons"]), "above 0.25 s a program")
        costly = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, self.research(28, 5.6)))
        self.assertFalse(costly["passed"], "one more program caught does not pay 0.12 s a program")
        unsafe = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, {**self.research(0, 1.0), "false_refusals": 1}))
        self.assertIn("false_refusals", " ".join(unsafe["reasons"]))
        broken = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, self.research(0, 1.0), head_exit=1))
        self.assertFalse(broken["passed"])
        leaky = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, self.research(20, 5.6),
                                                                           closed=self.research(25, 5.6)))
        self.assertIn("gate closed", " ".join(leaky["reasons"]), "a closed gate must be the baseline exactly")
        heldout_only = self.trees(base, self.research(20, 5.6))
        heldout_only["open"]["splits"]["dev"]["metrics"] = dict(base)
        tuned = lanes.judge_verdict(self.lane, self.bottleneck, heldout_only)
        self.assertIn("dev split", " ".join(tuned["public_reasons"]), "the motivating failures must fall too")
        floor = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(self.research(3, 0.1), self.research(0, 1.0)))
        self.assertIn("floor", " ".join(floor["reasons"]))
        self.assertTrue(all("heldout" not in r or "private" in r for r in floor["public_reasons"]))
        self.assertTrue(any("private" in r for r in floor["public_reasons"]), "held-out failures show no figures")
        memory = lanes.LANES["memory"]
        hold = memory.bottleneck("validation_attempts_per_usd")
        base = {"rebirths_admitted": 8, "novel_refused": 0, "sqlite_statements": 240, "trials_uncounted": 0,
                "mechanism_rewritten": 0, "rebirths_fresh_lineage": 3}
        self.assertTrue(lanes.judge_verdict(memory, hold, self.trees(base, base))["passed"])
        self.assertFalse(lanes.judge_verdict(memory, memory.bottleneck("graveyard_rebirth_rate"), self.trees(base, base))["passed"])
        for field in ("trials_uncounted", "mechanism_rewritten"):
            bad = lanes.judge_verdict(memory, hold, self.trees(base, {**base, field: 1}))
            self.assertIn(field, " ".join(bad["reasons"]))
        data = lanes.LANES["data"]
        window = {"base": self.trees({}, {})["base"], "head": self.trees({}, {})["open"]}
        window["base"]["splits"] = {s: {"metrics": {"failed_transient": 9, "retried_permanent": 0, "requests": 200}}
                                    for s in ("dev", "heldout")}
        window["head"]["splits"] = {s: {"metrics": {"failed_transient": 0, "retried_permanent": 0, "requests": 210}}
                                    for s in ("dev", "heldout")}
        self.assertTrue(lanes.judge_verdict(data, data.bottlenecks[0], window)["passed"], "a window lane has no gate runs")

    def test_memory_arms_need_births_balance_and_population_cost(self):
        memory = lanes.LANES["memory"]
        b = memory.bottleneck("graveyard_rebirth_rate")

        def units(n, rebirths, prefix, births=1):
            return {f"{prefix}{k}": {"births": births, "rebirths": 1 if k < rebirths else 0, "units": 1,
                                     "validation_runs": 1, "research_usd": 0.1} for k in range(n)}

        treated, control = units(60, 0, "t"), units(60, 12, "c")
        good = lanes.retention(memory, b, treated, control, seed="s", fraction=0.5,
                               population=({"unattributed_usd": 10.0, "hours": 12.0}, {"unattributed_usd": 20.0, "hours": 24.0}))
        self.assertEqual(good["decision"], "retained", good)
        refusing = lanes.retention(memory, b, units(30, 0, "t"), units(90, 18, "c"), seed="s", fraction=0.5)
        self.assertFalse(next(c for c in refusing["checks"] if c["metric"] == "birth_balance")["ok"], "over-refusal")
        self.assertEqual(refusing["decision"], "revert_recommended")
        pricey = lanes.retention(memory, b, treated, control, seed="s", fraction=0.5,
                                 population=({"unattributed_usd": 30.0, "hours": 12.0}, {"unattributed_usd": 20.0, "hours": 24.0}))
        self.assertEqual(pricey["decision"], "revert_recommended", "unbooked architect dollars count")
        canary_arm, control_arm = lanes.split_arms({"a": {"births": 1}, "old": {"validation_runs": 3}, "swarm": {"births": 1}},
                                                   key="k", salt="s", fraction=0.5, exclude=["swarm"], needs="births")
        self.assertEqual(sorted({**canary_arm, **control_arm}), ["a"], "only families born in the window, no pseudo-unit")

    def test_payback_and_reachable_samples(self):
        research = lanes.LANES["research"]
        self.assertTrue(lanes.payback(research, {"usd_per_day_at_effect": 1.88})["pays"])
        self.assertFalse(lanes.payback(research, {"usd_per_day_at_effect": 0.5}, "money_path")["pays"])
        self.assertIsNone(lanes.payback(lanes.LANES["execution"], {"basis": "not priced"})["pays"])
        restart = lanes.LANES["execution"].bottleneck("restart_failure_rate").metric
        self.assertIsNone(lanes.required_units({"restart_failures": 1, "restarts": 30}, restart, alpha=0.05))
        self.assertEqual(lanes.required_units({"restart_failures": 6, "restarts": 12}, restart, alpha=0.05), 6)
        # One failed restart of one needs 19 clean ones on the exact test: more than the five-day window's deliberate
        # restarts (`max_units`), so it is never captured (and a control like it voids the canary at its start).
        self.assertEqual(lanes.required_units({"restart_failures": 1, "restarts": 1}, restart, alpha=0.05), 19)
        cap = lanes.LANES["execution"].canary_for(lanes.LANES["execution"].bottleneck("restart_failure_rate"))["max_units"]
        self.assertIsNone(lanes.required_units({"restart_failures": 1, "restarts": 1}, restart, alpha=0.05, cap=cap))
        doc = {"schema": 1, "policy": lanes.POLICY, "since": 0.0, "until": 86400.0, "source": {},
               "lanes": {"execution": {"units": {}, "restart_totals": {"restarts": 1.0, "restart_failures": 1.0,
                                                                        "live_errors": 0.0, "restarts_or_one": 1.0}}}}
        row = next(r for r in lanes.rank(doc) if r["metric"] == "restart_failure_rate")
        self.assertFalse(row["captured"])
        self.assertIn("cannot reach alpha", row["why_not"])
        execution = lanes.LANES["execution"]
        b = execution.bottleneck("restart_failure_rate")
        families = {f"f{n}": {"intents": 10, "rejects": 0} for n in range(20)}  # practice units carry no restarts
        few = lanes.retention(execution, b, families, families, seed="s", extra_treated={"restarts": 2, "restart_failures": 0},
                              extra_control={"restarts": 12, "restart_failures": 6}, min_units=6)
        self.assertEqual(few["decision"], "insufficient_activity", "two restarts are not six, whatever the families")
        enough = lanes.retention(execution, b, families, families, seed="s", extra_treated={"restarts": 6, "restart_failures": 0},
                                 extra_control={"restarts": 12, "restart_failures": 6}, min_units=6)
        self.assertEqual(enough["decision"], "retained", enough)


SOURCE = "import json\n\n\ndef preflight(code, family=None):\n    return {'status': 'passed'}\n"
SAILBOX = "RETRIES = 2\n\n\ndef retries():\n    return RETRIES\n"


class LaneCycle(unittest.TestCase):
    """One research-lane candidate through the journal: capture, brief, stage, evaluate, canary, reconcile."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "repo"
        (self.repo / "league" / "swarm").mkdir(parents=True)
        (self.repo / "league" / "live").mkdir(parents=True)
        (self.repo / "league" / "swarm" / "preflight.py").write_text(SOURCE)
        (self.repo / "league" / "swarm" / "guard.py").write_text("CAP = 1\n")
        (self.repo / "league" / "sailbox.py").write_text(SAILBOX)
        labmod.git(self.repo, "init", "-q")
        self.base = commit(self.repo, "baseline")
        self.clock = Clock(1_790_000_000.0)
        # Private held-out pools in a directory outside the repo, pinned by hash (the real ones never reach a test).
        self.heldout = self.temp / "heldout"
        self.heldout.mkdir(mode=0o700)
        pinned = {}
        for name in ("research", "data"):
            raw = json.dumps({"schema": 1, "judge": name, "private": f"test pool {name}"}).encode()
            (self.heldout / f"{name}.json").write_bytes(raw)
            pinned[name] = dataclasses.replace(lanes.LANES[name], heldout_pool=labmod.sha(raw))
        patcher = patch.dict(lanes.LANES, pinned)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.lab = labmod.HarnessImprovement(self.temp / "journal", repo=self.repo, clock=self.clock, heldout=self.heldout)
        self.addCleanup(lambda: self.lab.close())
        with tempfile.TemporaryDirectory() as t:
            tree = Path(t) / "base"
            labmod.archive(self.repo, self.base, tree)
            self.digest = labmod.release_digest(tree)
        self.key = f"harness:research:train_dq_rate:{self.base[:16]}"

    def measurement(self, units, *, since=0.0, until=86400.0, digest=None, deploys=(), current=None, lane="research", starts=None,
                    start_releases=None, taken_at=None):
        doc = {"schema": 1, "policy": lanes.POLICY, "since": since, "until": until,
               "taken_at": self.clock() if taken_at is None else taken_at,
               "window": {"since": lanes.iso(since), "until": lanes.iso(until), "seconds": until - since},
               "source": {"digest": digest or self.digest, "release": "/r/base", "started_at": since - 10,
                          "heartbeat_age": 5.0},
               "current": current, "deploys": list(deploys),
               "lanes": {lane: {"units": units, "spend": {"sail_model": 5.0},
                                "examples": [{"signature": "AttributeError", "n": 3, "families": ["motive-1"],
                                              "boxes": ["sb_motive"], "first_at": "2026-09-30T00:00:00Z"}]}}}
        if starts is not None:
            doc["starts"] = list(starts)
        if start_releases is not None:
            doc["start_releases"] = [{"at": a, "release": r} for a, r in start_releases]
            doc["starts"] = [a for a, _ in start_releases]
        return doc

    def units(self, n, dq, prefix, runs=20):
        return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "research_usd": 1.0, "births": 1,
                                 "wasted_gym_seconds": dq * 100.0, "gym_seconds": runs * 100.0, "cycles": 40,
                                 "cycle_errors": 0, "gym_cycles": runs, "gym_cycles_unmatched": 0} for k in range(n)}

    def gated(self):
        return SOURCE.replace("    return {'status': 'passed'}\n",
                              "    from league.swarm import canary\n"
                              f"    if canary.enabled('{self.key}', family, root='.'):\n"
                              "        return {'status': 'refused'}\n    return {'status': 'passed'}\n")

    def capture(self):
        # The stake must repay a research-side cycle: 20% of the wasted Gym dollars a day.
        measured = self.measurement(self.units(30, 3, "f"))
        measured["lanes"]["data"] = {"units": {"sb": {"gym_usd": 100.0, "gym_seconds": 60000.0, "slots": 1000.0,
                                                      "slots_failed": 0.0, "ok_slots": 1000.0}}, "examples": []}
        return self.lab.capture_lanes(measured, base=self.base)

    def test_capture_is_ranked_durable_and_deduplicated(self):
        ranked = self.capture()
        self.assertEqual(ranked[0]["key"], self.key)
        self.assertTrue(ranked[0]["payback"]["pays"], ranked[0]["payback"])
        head = self.lab.ledger.head()
        self.lab.close()
        self.lab = labmod.HarnessImprovement(self.temp / "journal", repo=self.repo, clock=self.clock)
        self.capture()
        self.assertEqual(self.lab.ledger.head(), head, "the same evidence buys no second report")
        job = self.lab.worklist.get(self.key)
        self.assertEqual(job.details["motivating"], ["motive-1", "sb_motive"])
        with self.assertRaisesRegex(labmod.ImprovementError, "digest"):
            self.lab.capture_lanes({**self.measurement({}), "source": {}}, base=self.base)
        cheap = self.lab.capture_lanes(self.measurement(self.units(30, 3, "g")), base="b" * 40)
        self.assertFalse(next(r for r in cheap if r["lane"] == "research")["captured"], "unpriced waste is not a cycle")
        # A stale document (another release may run since) or one of a swarm without a fresh heartbeat binds nothing.
        with self.assertRaisesRegex(labmod.ImprovementError, "not taken in the last"):
            self.lab.capture_lanes(self.measurement(self.units(30, 3, "h"), taken_at=self.clock() - 2 * 3600), base="c" * 40)
        silent = self.measurement(self.units(30, 3, "h"))
        silent["source"]["heartbeat_age"] = 900.0
        with self.assertRaisesRegex(labmod.ImprovementError, "heartbeat"):
            self.lab.capture_lanes(silent, base="c" * 40)

    def test_brief_hides_the_heldout_split_and_stage_enforces_the_boundary(self):
        self.capture()
        proposal = self.lab.prepare(self.key, self.temp / "wt")
        brief = proposal["brief"]
        self.assertIn("pass or fail", brief["heldout"])
        self.assertNotIn(self.lab.secret(), json.dumps(brief))
        self.assertIn("canary.enabled", brief["canary"]["gate"])
        self.assertIn("league/swarm/researcher.py", brief["frozen"]["symbols"])
        worktree = Path(proposal["worktree"])
        (worktree / "league" / "swarm" / "guard.py").write_text("CAP = 100\n")
        with self.assertRaisesRegex(labmod.ImprovementError, "protected"):
            self.lab.stage(self.key, commit(worktree, "raise a spend cap"))
        labmod.git(worktree, "checkout", "-q", "HEAD~1", "--", "league/swarm/guard.py")
        (worktree / "league" / "swarm" / "preflight.py").write_text(SOURCE.replace("'passed'", "'refused'"))
        with self.assertRaisesRegex(labmod.ImprovementError, "gated"):
            self.lab.stage(self.key, commit(worktree, "ungated"))
        self.assertEqual(self.lab.worklist.get(self.key).state, "revising")
        (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated())
        staged = self.lab.stage(self.key, commit(worktree, "gated"), authoring_usd=1.25)
        self.assertEqual(staged["classification"]["release_class"], "research")
        self.assertEqual((staged["canary_mode"], staged["gates"]), ("arms", 1))
        job = self.lab.worklist.get(self.key)
        self.assertEqual(job.attempt, 3)
        self.assertEqual(str(job.cost_usd), "1.25")
        steps = self.lab.next_steps(root="J", repo="R")
        self.assertIn("evaluate", steps[0]["next"])

    def test_renames_deletes_modes_and_test_file_gates_are_refused(self):
        for n, change in enumerate(("rename", "delete", "mode", "fake gate", "edit test")):
            key = self.key
            if n:
                # a fresh capture on a fresh base for each attempt budget
                (self.repo / "league" / "swarm" / f"note{n}.py").write_text("X = 1\n")
                if change == "edit test":
                    # an earlier candidate's retained test, now in the base
                    (self.repo / "league" / "tests").mkdir(parents=True, exist_ok=True)
                    (self.repo / "league" / "tests" / "test_harness_candidate_old.py").write_text("X = 1\n")
                base = commit(self.repo, f"base {n}")
                with tempfile.TemporaryDirectory() as t:
                    labmod.archive(self.repo, base, Path(t) / "b")
                    digest = labmod.release_digest(Path(t) / "b")
                measured = self.measurement(self.units(30, 3, "f"), digest=digest)
                measured["lanes"]["data"] = {"units": {"sb": {"gym_usd": 100.0, "gym_seconds": 60000.0, "slots": 1000.0}}}
                self.lab.capture_lanes(measured, base=base)
                key = f"harness:research:train_dq_rate:{base[:16]}"
            else:
                self.capture()
                base = self.base
            worktree = Path(self.lab.prepare(key, self.temp / f"wt{n}")["worktree"])
            if change == "rename":
                (worktree / "league" / "tests").mkdir(parents=True, exist_ok=True)
                labmod.git(worktree, "mv", "league/swarm/guard.py", "league/tests/test_harness_candidate_x.py")
                pattern = "only modifies or adds"
            elif change == "delete":
                labmod.git(worktree, "rm", "-q", "league/sailbox.py")
                pattern = "only modifies or adds"
            elif change == "mode":
                (worktree / "league" / "swarm" / "preflight.py").chmod(0o755)
                pattern = "mode"
            elif change == "edit test":
                (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated().replace(self.key, key))
                (worktree / "league" / "tests" / "test_harness_candidate_old.py").write_text("X = 2\n")
                pattern = "never edits an existing"
            else:
                (worktree / "league" / "swarm" / "preflight.py").write_text(SOURCE.replace("'passed'", "'refused'"))
                (worktree / "league" / "tests").mkdir(parents=True, exist_ok=True)
                (worktree / "league" / "tests" / "test_harness_candidate_gate.py").write_text(
                    f"from league.swarm import canary\n\nX = canary.enabled('{key}', 'u', root='.')\n")
                pattern = "gated"
            with self.assertRaisesRegex(labmod.ImprovementError, pattern, msg=change):
                self.lab.stage(key, commit(worktree, change))

    def evaluated(self, head_wasted=1000.0, closed_wasted=None, forge=False):
        self.capture()
        worktree = Path(self.lab.prepare(self.key, self.temp / "wt")["worktree"])
        (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated())
        self.lab.stage(self.key, commit(worktree, "gated"))
        calls = []

        def judge(tree, _judge, command, **kwargs):
            calls.append((tree.name, command))
            if command[0] == "-m" or command[0].endswith("_regress.py"):
                return {"exit": 0, "stdout": "", "stderr": "", "seconds": 0.1, "cpu_seconds": 0.1, "error": None}
            split = command[command.index("--split") + 1]
            gate_state = command[command.index("--gate") + 1] if "--gate" in command else "none"
            if tree.name == "base" or gate_state == "closed":
                wasted = 2600.0 if closed_wasted is None or tree.name == "base" else closed_wasted
                screen = 0.1
            else:
                # a held-out figure the author must never see, distinct from the dev one
                wasted, screen = head_wasted + (7.0 if split == "heldout" else 0.0), 3.0
            lines = kwargs["stdin"].decode().splitlines()
            # The private pool rides on standard input for held-out runs only, never on the command line.
            self.assertEqual(len(lines), 2 if split == "heldout" else 1)
            self.assertEqual("--pool-stdin" in command, split == "heldout")
            self.assertFalse(any("test pool" in c for c in command))
            if split == "heldout":
                self.assertIn("test pool research", lines[1])
            body = {"protocol": "research-workflow-v3", "split": split, "provider_calls": 0, "gym_seconds_wasted": wasted,
                    "broken_reaching_gym": wasted / 130.0, "broken_cases": 31, "cases": 45, "false_refusals": 0,
                    "screen_cpu_seconds": screen, "gate": gate_state, "nonce": lines[0],
                    "missed": {"secret_class/after_ten": 1}}
            # A line the tree's own code printed after the judge's answer (an exit hook): it cannot know the nonce.
            forged = "\n" + json.dumps({**body, "nonce": "guessed", "gym_seconds_wasted": 0.0}) if forge and gate_state == "open" else ""
            return {"exit": 0, "stdout": json.dumps(body) + forged, "stderr": "printed by the tree", "seconds": 0.1,
                    "cpu_seconds": 0.1, "error": None}

        with patch.object(labmod, "sandbox", side_effect=judge):
            receipt = self.lab.evaluate(self.key, python=Path(sys.executable))
        seeds = {c[1][c[1].index("--seed") + 1] for c in calls if "--seed" in c[1]}
        self.assertEqual(len(seeds), 1, "every tree, gate and split shares one held-out seed")
        self.assertEqual(receipt["heldout_seed"], seeds.pop())
        self.assertEqual(sorted(receipt["trees"]), ["base", "closed", "open"])
        gates = {c[1][c[1].index("--gate") + 1] for c in calls if "--gate" in c[1]}
        self.assertEqual(gates, {"open", "closed"})
        return receipt

    def test_offline_failure_leaves_attempts_then_rejects(self):
        receipt = self.evaluated(head_wasted=2500.0)
        self.assertFalse(receipt["passed"])
        self.assertEqual(self.lab.worklist.get(self.key).state, "revising")
        note = self.lab.worklist.get(self.key).note
        self.assertIn("private", note)
        self.assertNotIn("2507", note, "held-out figures never reach the author")
        self.assertIn("2500", note, "dev figures are the author's to see")
        held = receipt["trees"]["open"]["splits"]["heldout"]
        self.assertNotIn("stdout", held["benchmark"])
        self.assertNotIn("stderr", held["benchmark"], "nothing a held-out run printed is kept")
        self.assertNotIn("missed", held["metrics"], "no per-class detail of the held-out split is kept")
        self.assertIn("missed", receipt["trees"]["open"]["splits"]["dev"]["metrics"])

    def test_a_forged_answer_line_is_no_answer(self):
        receipt = self.evaluated(forge=True)
        self.assertFalse(receipt["passed"])
        self.assertIn("no valid answer", " ".join(receipt["verdict"]["reasons"]))

    def test_a_gate_that_leaks_when_closed_is_refused(self):
        self.assertFalse(self.evaluated(closed_wasted=1500.0)["passed"])

    def deploy_rows(self, release="cand-release", promoted_at=90000.0, digest=None):
        digest = digest or self.lab.worklist.get(self.key).carry["_proposal"]["release_digest"]
        common = {"deploy": f"{release}@1", "release": release}
        return [{**common, "stage": "start", "watch_seconds": 600, "at": lanes.iso(promoted_at - 900)},
                {**common, "stage": "stage", "ok": True, "digest": digest, "at": lanes.iso(promoted_at - 800)},
                {**common, "stage": "canary", "ok": True, "ticks": 3}, {**common, "stage": "watch", "ok": True, "grace": False},
                {**common, "stage": "verdict", "verdict": "promoted", "at": lanes.iso(promoted_at)}]

    def started(self):
        self.assertTrue(self.evaluated()["passed"])
        self.assertEqual(self.lab.worklist.get(self.key).state, "canary")
        digest = self.lab.worklist.get(self.key).carry["_proposal"]["release_digest"]
        waiting = self.lab.canary_start(self.key, measurement=self.measurement({}, since=89000, until=90100, digest=digest))
        self.assertIn("waiting", waiting)
        started = self.lab.canary_start(self.key, measurement=self.measurement(
            {}, since=89000, until=90100, digest=digest, deploys=self.deploy_rows(), current="cand-release"))
        arm = started["started"]
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "canary")
        return arm, digest

    def arms(self, arm, treated_dq, control_dq):
        units = {}
        for n in range(400):
            fid = f"u{n}"
            dq = treated_dq if gate.in_arm(arm["salt"], self.key, fid, arm["fraction"]) else control_dq
            units[fid] = {"train_runs": 20, "dq_runs": dq, "ok_runs": 20 - dq, "research_usd": 1.0, "births": 1,
                          "wasted_gym_seconds": dq * 100.0, "cycles": 40, "cycle_errors": 0, "gym_cycles": 20,
                          "gym_cycles_unmatched": 0}
        units["motive-1"] = {"train_runs": 20, "dq_runs": 20, "ok_runs": 0, "research_usd": 1.0, "births": 1,
                             "wasted_gym_seconds": 2000.0, "cycles": 40, "cycle_errors": 0}
        return units

    def test_canary_beats_the_control_and_is_retained_once(self):
        arm, digest = self.started()
        since, until = arm["since"], arm["since"] + 6 * 3600
        early = self.lab.reconcile_lane(self.key, measurement=self.measurement(
            self.arms(arm, 1, 4), since=since, until=since + 600, digest=digest, deploys=self.deploy_rows(), current="cand-release"))
        self.assertIn("waiting", early)
        long = self.measurement(self.arms(arm, 1, 4), since=since, until=until + 3 * 86400, digest=digest,
                                deploys=self.deploy_rows(), current="cand-release")
        self.assertIn("exactly", self.lab.reconcile_lane(self.key, measurement=long)["waiting"], "no optional stopping")
        stale = self.measurement(self.arms(arm, 1, 4), since=since, until=until, digest=digest, deploys=self.deploy_rows(),
                                 current="cand-release")
        stale["taken_at"] = until - 3600
        self.assertIn("taken", self.lab.reconcile_lane(self.key, measurement=stale)["waiting"])
        final = self.measurement(self.arms(arm, 1, 4), since=since, until=until, digest=digest, deploys=self.deploy_rows(),
                                 current="cand-release")
        result = self.lab.reconcile_lane(self.key, measurement=final)
        self.assertEqual(result["decision"], "retained", result)
        self.assertEqual(result["motivating_excluded"], 2)
        self.assertEqual(self.lab.worklist.get(self.key).state, "verified")
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "retained")
        rows = self.lab.ledger.head()
        worse = self.measurement(self.arms(arm, 4, 1), since=since, until=until, digest=digest, deploys=self.deploy_rows(),
                                 current="cand-release")
        self.assertEqual(self.lab.reconcile_lane(self.key, measurement=worse), result, "no second look")
        self.assertEqual(self.lab.ledger.head(), rows)
        self.assertGreater(self.lab.ledger.verify(), 5)
        self.assertEqual(self.lab.gates()["retained_not_graduated"], [self.key])
        self.assertIn("graduate", self.lab.next_steps()[0]["next"])
        with self.assertRaisesRegex(labmod.ImprovementError, "full main commit"):
            self.lab.canary_stop(self.key, state="graduated", commit="abc")
        self.lab.canary_stop(self.key, state="graduated", commit="c" * 40)
        self.assertNotIn(self.key, gate.read(self.temp / "journal" / "canary.json"))
        self.assertEqual(self.lab.gates()["retained_not_graduated"], [])

    def test_a_canary_that_does_not_beat_the_control_is_flipped_back_and_stays_back(self):
        arm, digest = self.started()
        since = arm["since"]
        result = self.lab.reconcile_lane(self.key, measurement=self.measurement(
            self.arms(arm, 3, 3), since=since, until=since + 6 * 3600, digest=digest, deploys=self.deploy_rows(),
            current="cand-release"))
        self.assertEqual(result["decision"], "reverted")
        self.assertEqual(self.lab.worklist.get(self.key).state, "rejected")
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "reverted")
        with self.assertRaisesRegex(labmod.ImprovementError, "only the registered decision retains"):
            self.lab.canary_stop(self.key, state="retained")
        self.assertEqual(self.lab.worklist.get(self.key).state, "rejected")

    def test_another_release_inside_the_window_voids_the_comparison(self):
        arm, digest = self.started()
        since = arm["since"]
        other = [{"deploy": "other@1", "release": "other", "stage": "verdict", "verdict": "promoted",
                  "at": lanes.iso(since + 3600)}]
        result = self.lab.reconcile_lane(self.key, measurement=self.measurement(
            self.arms(arm, 1, 4), since=since, until=since + 6 * 3600, digest=digest,
            deploys=self.deploy_rows() + other, current="other"))
        self.assertEqual(result["decision"], "voided", result)
        self.assertEqual(self.lab.worklist.get(self.key).state, "rejected")
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "reverted")
        self.assertIn("voided", self.lab.next_steps()[0]["next"])
        attempts = self.lab.worklist.get(self.key).attempt
        again = self.measurement(self.units(30, 3, "f"), since=86400.0 * 2, until=86400.0 * 3)
        again["lanes"]["data"] = {"units": {"sb": {"gym_usd": 100.0, "gym_seconds": 60000.0, "slots": 1000.0}}}
        self.lab.capture_lanes(again, base=self.base)
        job = self.lab.worklist.get(self.key)
        self.assertEqual((job.state, job.attempt), ("proposed", attempts - 1), "a void reopens and does not use an attempt")
        self.assertIn("prepare", self.lab.next_steps()[0]["next"])

    def test_evaluation_needs_the_pinned_private_pool(self):
        self.capture()
        worktree = Path(self.lab.prepare(self.key, self.temp / "wt")["worktree"])
        (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated())
        self.lab.stage(self.key, commit(worktree, "gated"))
        self.lab.heldout = None
        with patch.object(labmod, "sandbox", side_effect=AssertionError("no judge runs without its pool")):
            with self.assertRaisesRegex(labmod.ImprovementError, "held-out pools"):
                self.lab.evaluate(self.key, python=Path(sys.executable))
            self.lab.heldout = self.heldout
            (self.heldout / "research.json").write_text(json.dumps({"schema": 1, "regenerated": True}))
            with self.assertRaisesRegex(labmod.ImprovementError, "not the pinned one"):
                self.lab.evaluate(self.key, python=Path(sys.executable))
        self.assertEqual(self.lab.worklist.get(self.key).state, "testing", "a missing pool uses no attempt")

    def test_a_deploy_over_a_newer_release_or_changed_rules_voids_the_canary(self):
        self.assertTrue(self.evaluated()["passed"])
        digest = self.lab.worklist.get(self.key).carry["_proposal"]["release_digest"]
        newer = [{"deploy": "newer@1", "release": "newer", "stage": "stage", "ok": True, "digest": "e" * 64,
                  "at": lanes.iso(80000.0)}]
        rows = self.deploy_rows()
        rows[0] = {**rows[0], "current": "newer"}
        result = self.lab.canary_start(self.key, measurement=self.measurement(
            {}, since=89000, until=90100, digest=digest, deploys=newer + rows, current="cand-release"))
        self.assertEqual(result["decision"], "voided", result)
        self.assertIn("roll back to newer", result["reason"])
        self.assertEqual(self.lab.worklist.get(self.key).state, "rejected")
        self.assertIn("roll back to newer", self.lab.next_steps()[0]["next"])

    def test_the_lane_rules_changing_mid_canary_voids_it(self):
        arm, digest = self.started()
        since = arm["since"]
        with patch.dict(lanes._RULES, {"sha": "a changed rebirth detector"}):
            result = self.lab.reconcile_lane(self.key, measurement=self.measurement(
                self.arms(arm, 1, 4), since=since, until=since + 6 * 3600, digest=digest, deploys=self.deploy_rows(),
                current="cand-release"))
        self.assertEqual(result["decision"], "voided", result)
        self.assertIn("rules changed", result["reason"])
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "reverted")

    def test_the_watch_measures_a_registered_window_once(self):
        arm, digest = self.started()
        end = arm["since"] + 6 * 3600
        (self.temp / "deploys.jsonl").write_text("\n".join(json.dumps(r) for r in self.deploy_rows()) + "\n")
        window = self.measurement(self.arms(arm, 1, 4), since=arm["since"], until=end, digest=digest)
        with patch.object(lanes, "measure", return_value=window) as measured, \
                patch.object(self.lab, "reconcile_lane", return_value={"waiting": "the close"}):
            for _ in range(3):
                self.lab.reconcile(self.key, deploy_log=self.temp / "deploys.jsonl", current_release="cand-release",
                                   swarm=self.temp / "state")
        self.assertEqual(measured.call_count, 1, "a waiting decision re-reads the journal's copy, never the House")
        self.assertEqual(measured.call_args.kwargs["examples"], 0)

    def test_a_money_path_gate_never_turns_on_in_session(self):
        self.assertTrue(labmod.in_session(lanes.epoch_of("2026-10-01T15:00:00Z")))
        self.assertFalse(labmod.in_session(lanes.epoch_of("2026-10-01T20:10:00Z")))
        self.assertFalse(labmod.in_session(lanes.epoch_of("2026-10-03T15:00:00Z")), "a Saturday")
        self.assertTrue(labmod.in_session(lanes.epoch_of("2026-11-02T20:30:00Z")), "New York winter: the session ends 21:05Z")

    def window_started(self):
        """A data-lane candidate captured, staged, judged, deployed and started against a fresh control day."""
        key = f"harness:data:slot_failure_rate:{self.base[:16]}"
        boxes = {f"sb{n}": {"gym_usd": 10.0, "gym_seconds": 10000.0, "slots": 200.0, "slots_failed": 4.0, "ok_slots": 196.0}
                 for n in range(5)}
        measured = self.measurement(boxes, lane="data")
        measured["lanes"]["data"]["run_totals"] = {"runs": 100.0, "error_runs": 0.0}
        self.lab.capture_lanes(measured, base=self.base)
        self.assertIsNotNone(self.lab.worklist.get(key), "the data lane's bottleneck is captured")
        worktree = Path(self.lab.prepare(key, self.temp / "wt-data")["worktree"])
        (worktree / "league" / "sailbox.py").write_text(SAILBOX.replace("RETRIES = 2", "RETRIES = 3"))
        staged = self.lab.stage(key, commit(worktree, "retry more"))
        self.assertEqual(staged["canary_mode"], "window")

        def judge(tree, _judge, command, **kwargs):
            if command[0] == "-m":
                return {"exit": 0, "stdout": "", "stderr": "", "seconds": 0.1, "cpu_seconds": 0.1, "error": None}
            split = command[command.index("--split") + 1]
            body = {"protocol": "data-retry-v3", "split": split, "provider_calls": 0, "gate": "none",
                    "nonce": kwargs["stdin"].decode().splitlines()[0], "failed_transient": 9 if tree.name == "base" else 0,
                    "retried_permanent": 0, "requests": 200}
            return {"exit": 0, "stdout": json.dumps(body), "stderr": "", "seconds": 0.1, "cpu_seconds": 0.1, "error": None}

        with patch.object(labmod, "sandbox", side_effect=judge):
            self.assertTrue(self.lab.evaluate(key, python=Path(sys.executable))["passed"])
        digest = self.lab.worklist.get(key).carry["_proposal"]["release_digest"]
        promoted = 86400.0 * 3
        rows = [{**r, "digest": digest} if r.get("stage") == "stage" else r
                for r in self.deploy_rows(promoted_at=promoted, digest=digest)]
        now = self.measurement({}, since=promoted, until=promoted + 900, digest=digest, deploys=rows, current="cand-release",
                               lane="data")
        self.assertIn("control", self.lab.canary_start(key, measurement=now)["waiting"])
        with self.assertRaisesRegex(labmod.ImprovementError, "overlaps"):
            self.lab.canary_start(key, measurement=now, control=self.measurement(boxes, since=0.0, until=86400.0, lane="data"))
        with self.assertRaisesRegex(labmod.ImprovementError, "just before the deploy"):
            self.lab.canary_start(key, measurement=now, control=self.measurement(boxes, since=promoted, until=promoted + 86400,
                                                                                 lane="data"))
        control = self.measurement(boxes, since=promoted - 900 - 86400, until=promoted - 900, lane="data", starts=[])
        control["lanes"]["data"]["run_totals"] = {"runs": 100.0, "error_runs": 0.0}
        started = self.lab.canary_start(key, measurement=now, control=control)
        self.assertEqual(started["started"]["mode"], "window")
        return key, promoted, rows, digest

    def after(self, key, promoted, rows, digest, *, failed=0.0, slots=200.0, **starts):
        end = promoted + 86400
        boxes = {f"sb{n}": {"gym_usd": 10.0, "gym_seconds": 10000.0, "slots": slots, "slots_failed": failed,
                            "ok_slots": slots - failed} for n in range(5)}
        doc = self.measurement(boxes, since=promoted, until=end, digest=digest, deploys=rows, current="cand-release",
                               lane="data", **starts)
        doc["lanes"]["data"]["run_totals"] = {"runs": 100.0, "error_runs": 0.0}
        return self.lab.reconcile_lane(key, measurement=doc)

    def test_a_window_lane_restart_of_its_own_release_decides_and_asks_to_merge(self):
        key, promoted, rows, digest = self.window_started()
        result = self.after(key, promoted, rows, digest, start_releases=[(promoted + 7200, "cand-release")])
        self.assertEqual(result["decision"], "retained", result)
        step = next(s for s in self.lab.next_steps() if s["key"] == key)
        self.assertIn("merge", step["next"], "a retained window change reaches main or the next release drops it")
        self.assertEqual(self.lab.gates()["retained_not_graduated"], [key])
        self.lab.canary_stop(key, state="graduated", commit="d" * 40)
        self.assertEqual(self.lab.gates()["retained_not_graduated"], [])

    def test_a_window_lane_voids_when_another_release_ran_inside_it(self):
        key, promoted, rows, digest = self.window_started()
        self.assertEqual(self.after(key, promoted, rows, digest, start_releases=[(promoted + 7200, "other")])["decision"],
                         "voided")
        self.assertIn("roll it back", next(s for s in self.lab.next_steps() if s["key"] == key)["next"])

    def test_an_older_measurement_without_start_releases_voids_on_any_restart(self):
        key, promoted, rows, digest = self.window_started()
        self.assertEqual(self.after(key, promoted, rows, digest, starts=[promoted + 7200])["decision"], "voided")

    def test_a_window_lane_without_enough_activity_is_rolled_back(self):
        key, promoted, rows, digest = self.window_started()
        result = self.after(key, promoted, rows, digest, slots=10.0, start_releases=[])
        self.assertEqual(result["decision"], "insufficient_activity", result)
        self.assertIn("roll back", next(s for s in self.lab.next_steps() if s["key"] == key)["next"])
        rollback = rows + [{"deploy": "cand-release@1", "release": "cand-release", "stage": "rollback", "ok": True,
                            "from": "cand-release", "to": "base"}]
        undone = self.lab.reconcile_lane(key, measurement={"since": 0.0, "until": 1.0, "deploys": rollback})
        self.assertEqual(undone["decision"], "reverted")
        self.assertEqual(self.lab.worklist.get(key).state, "rejected")


RESTATES = '''

def _restates(a, b):
    """The first sentences share at least 0.3 of their content words."""
    x, y = words(str(a).split(".")[0]), words(str(b).split(".")[0])
    return bool(x and y) and len(x & y) / len(x | y) >= 0.3
'''


@unittest.skipUnless(shutil.which("bwrap"), "credential-free network namespace requires bwrap")
class GatedMemoryCandidate(unittest.TestCase):
    """A real memory-lane candidate, gated as the brief says, through stage and the real sandboxed judge: with its gate
    closed it is the baseline exactly, with it open it refuses restated ideas and keeps every lineage's trials."""

    def test_the_judge_sees_the_gated_change_open_and_the_baseline_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root, repo = Path(td), Path(td) / "repo"
            repo.mkdir()
            for name in ("league", "ltcm", "scripts", "playbooks", "deploy"):
                if (labmod.REPO / name).is_dir():
                    shutil.copytree(labmod.REPO / name, repo / name,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".data"))
            labmod.git(repo, "init", "-q")
            base = commit(repo, "baseline")
            with tempfile.TemporaryDirectory() as t:
                labmod.archive(repo, base, Path(t) / "b")
                digest = labmod.release_digest(Path(t) / "b")
            # The lane as defined (its real regression list, the tests its lever supersedes), with a TEST pool pinned.
            heldout = root / "heldout"
            heldout.mkdir(mode=0o700)
            raw = json.dumps(TEST_POOLS["memory"]).encode()
            (heldout / "memory.json").write_bytes(raw)
            quick = dataclasses.replace(lanes.LANES["memory"], heldout_pool=labmod.sha(raw))
            self.assertEqual(quick.regressions, lanes.LANES["memory"].regressions)
            with patch.dict(lanes.LANES, {"memory": quick}):
                clock = Clock(1_790_000_000.0)
                lab = labmod.HarnessImprovement(root / "journal", repo=repo, clock=clock, heldout=heldout)
                self.addCleanup(lab.close)
                units = {f"m{n}": {"births": 1, "rebirths": 1 if n < 8 else 0, "units": 1, "research_usd": 0.1}
                         for n in range(40)}
                measured = {"schema": 1, "policy": lanes.POLICY, "since": 0.0, "until": 86400.0, "taken_at": clock(),
                            "window": {"since": lanes.iso(0), "until": lanes.iso(86400), "seconds": 86400},
                            "source": {"digest": digest, "release": "/r/base", "started_at": 0.0, "heartbeat_age": 5.0},
                            "lanes": {"memory": {"units": units, "spend": {"claude": 100.0}, "examples": []}}}
                lab.capture_lanes(measured, base=base)
                key = f"harness:memory:graveyard_rebirth_rate:{base[:16]}"
                self.assertIsNotNone(lab.worklist.get(key))
                worktree = Path(lab.prepare(key, root / "wt")["worktree"])
                source = worktree / "league" / "swarm" / "architect.py"
                text = source.read_text()
                anchor = "            cited = self.differs(row, known)\n"
                self.assertEqual(text.count(anchor), 1)
                gated = (f'            if canary.enabled("{key}", canary.mechanism_unit(mechanism), root=self.store.root):\n'
                         "                if any(_restates(f[\"mechanism\"], mechanism) for f in self.store.families(alive=False)\n"
                         "                       if f[\"structure\"] == structure and sorted(f[\"roots\"]) == sorted(roots)):\n"
                         "                    continue\n")
                text = text.replace(anchor, gated + anchor, 1)
                text = text.replace("from . import diagnostics, inputs\n", "from . import canary, diagnostics, inputs\n", 1)
                source.write_text(text + RESTATES)
                with self.assertRaisesRegex(labmod.ImprovementError, "gate"):
                    # `canary` joined an existing import line: the gate must come in by its own import
                    lab.stage(key, commit(worktree, "gate import on a shared line"))
                text = text.replace("from . import canary, diagnostics, inputs\n", "from . import diagnostics, inputs\nfrom . import canary\n", 1)
                source.write_text(text + RESTATES)
                staged = lab.stage(key, commit(worktree, "refuse restated buried ideas, gated per mechanism"))
                self.assertEqual((staged["canary_mode"], staged["gates"], staged["classification"]["release_class"]),
                                 ("arms", 1, "research"))
                receipt = lab.evaluate(key, python=Path(sys.executable))
                trees = receipt["trees"]
                for split in ("dev", "heldout"):
                    base_m, closed, opened = (trees[t]["splits"][split]["metrics"] for t in ("base", "closed", "open"))
                    for name in lanes.judge_counts(quick):
                        self.assertEqual(closed[name], base_m[name], f"{split} {name}: the closed gate is the baseline")
                    self.assertLess(opened["rebirths_admitted"], base_m["rebirths_admitted"], split)
                    self.assertEqual((opened["trials_uncounted"], opened["mechanism_rewritten"], opened["novel_refused"]),
                                     (0, 0, 0), split)
                self.assertTrue(receipt["passed"], json.dumps(receipt["verdict"], indent=1))
                # Every regression passes the three ways; open, the superseded tests (which pin the admission of a
                # restated dead idea) are the only ones not run.
                self.assertEqual({t["regressions"]["exit"] for t in trees.values()}, {0},
                                 {k: t["regressions"].get("stderr", "")[-1500:] for k, t in trees.items()})


class Judges(unittest.TestCase):
    """The fixed judges run as the sandbox runs them: a script importing the tree from PYTHONPATH, the pool on stdin."""

    ENV = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1", "LTCM_HARNESS_JUDGE": "1"}

    def judge(self, name, split="dev", seed="dev"):
        command = [sys.executable, str(REPO / "league/swarm/harness_judges" / f"{name}.py"), "--split", split, "--seed", seed]
        stdin = None
        if split == "heldout":
            command.append("--pool-stdin")
            stdin = json.dumps(TEST_POOLS[name]) + "\n"
        out = subprocess.run(command, input=stdin, capture_output=True, text=True, env=self.ENV, cwd=str(REPO), timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_memory_judge_labels_by_construction(self):
        dev = self.judge("memory")
        self.assertEqual((dev["rebirths_proposed"], dev["novel_proposed"], dev["provider_calls"]), (8, 8, 0))
        self.assertEqual(dev["novel_refused"], 0)
        self.assertEqual((dev["trials_uncounted"], dev["mechanism_rewritten"]), (0, 0))
        held = self.judge("memory", "heldout", "00aa11bb22cc33dd")
        self.assertEqual(held, {**held, "rebirths_proposed": 8, "novel_proposed": 6, "trials_uncounted": 0})
        self.assertEqual(held["seed"], "00aa11bb22cc33dd")
        self.assertGreaterEqual(held["rebirths_admitted"], lanes.LANES["memory"].bottlenecks[0].judge_floor)

    def test_the_heldout_split_needs_its_private_pool(self):
        for name in ("research", "memory", "data", "execution"):
            out = subprocess.run([sys.executable, str(REPO / "league/swarm/harness_judges" / f"{name}.py"), "--split",
                                  "heldout", "--seed", "s1"], capture_output=True, text=True, env=self.ENV, cwd=str(REPO),
                                 timeout=300)
            self.assertNotEqual(out.returncode, 0, name)
            self.assertIn("pool", out.stderr + out.stdout, name)
        for name in ("research", "memory", "data", "execution"):
            self.assertRegex(lanes.LANES[name].heldout_pool, r"^[0-9a-f]{64}$", "every lane pins its private pool")

    def test_heldout_cases_follow_the_seed_and_the_pool_and_differ_from_dev(self):
        sys.path.insert(0, str(REPO / "league/swarm/harness_judges"))
        self.addCleanup(sys.path.remove, str(REPO / "league/swarm/harness_judges"))
        import data as data_judge
        import research as research_judge

        import memory as memory_judge

        pool = TEST_POOLS["research"]
        a, b = research_judge.cases("heldout", "s1", pool), research_judge.cases("heldout", "s2", pool)
        self.assertEqual(a, research_judge.cases("heldout", "s1", pool))
        self.assertNotEqual([c["code"] for c in a], [c["code"] for c in b])
        dev = research_judge.cases("dev", "dev")
        self.assertFalse({c["code"] for c in dev} & {c["code"] for c in a})
        self.assertEqual(sorted({(c["class"], c["wrap"]) for c in a if c["label"] == "broken"}),
                         [("fixture_attr", "always"), ("fixture_attr", "fixture_late"), ("fixture_call", "always"),
                          ("fixture_call", "fixture_late"), ("fixture_load", "load")], "every class in every placement")
        self.assertIn("fixture_valid", {c["class"] for c in a if c["label"] == "valid"})
        with self.assertRaises(ValueError):
            research_judge.cases("heldout", "s1", None)
        held, faults, permanent = data_judge.cases("heldout", "s1", TEST_POOLS["data"])
        self.assertNotEqual(held, data_judge.cases("heldout", "s2", TEST_POOLS["data"])[0])
        self.assertEqual(permanent, {"fixture_http418", "fixture_denied"})
        self.assertFalse({k for c in data_judge.cases("dev", "dev")[0] for k in c} & {k for c in held for k in c})
        dev_buried = {b["mechanism"] for b in memory_judge.cases("dev", "dev")[0]}
        self.assertFalse(dev_buried & {b["mechanism"] for b in memory_judge.cases("heldout", "s1", TEST_POOLS["memory"])[0]})

    def test_data_judge_faults_and_their_labels(self):
        dev = self.judge("data")
        self.assertEqual(dev["retried_permanent"], 0)
        self.assertGreaterEqual(dev["failed_transient"], 1, "the truncated read the Sept 30 judge found is a dev case")
        held = self.judge("data", "heldout", "s1")
        self.assertEqual(held["retried_permanent"], 0)
        self.assertGreater(held["failed_transient"], 0, "an HTTP 599 is not retried by the Sept 30 driver")

    def test_a_forced_gate_needs_its_key_the_override_and_the_sandbox_marker(self):
        script = str(REPO / "league/swarm/harness_judges/data.py")
        out = subprocess.run([sys.executable, script, "--split", "dev", "--gate", "open", "--key", "harness:data:k:0",
                              "--nonce-stdin"], input="n0nce\n", capture_output=True, text=True, env=self.ENV,
                             cwd=str(REPO), timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        answer = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual((answer["gate"], answer["nonce"]), ("open", "n0nce"))
        missing = subprocess.run([sys.executable, script, "--split", "dev", "--gate", "open"], capture_output=True, text=True,
                                 env=self.ENV, cwd=str(REPO), timeout=300)
        self.assertNotEqual(missing.returncode, 0)
        unmarked = {k: v for k, v in self.ENV.items() if k != "LTCM_HARNESS_JUDGE"}
        ignored = subprocess.run([sys.executable, script, "--split", "dev", "--gate", "open", "--key", "harness:data:k:0"],
                                 capture_output=True, text=True, env=unmarked, cwd=str(REPO), timeout=300)
        self.assertNotEqual(ignored.returncode, 0, "outside the judges' sandbox the override is ignored, so it is refused")
        self.assertIn("LTCM_HARNESS_JUDGE", ignored.stderr + ignored.stdout)

    @unittest.skipUnless(HAVE_NUMPY, "the research and execution judges need numpy")
    def test_research_and_execution_judges_keep_their_safety_counts(self):
        research = self.judge("research")
        self.assertEqual(research["false_refusals"], 0)
        self.assertGreater(research["cases"], 20)
        self.assertIn("screen_cpu_seconds", research)
        execution = self.judge("execution")
        self.assertEqual(execution["invalid_accepted"], 0)
        held = self.judge("execution", "heldout", "s1")
        self.assertEqual((held["scenarios"], held["invalid_accepted"]), (2, 0))


@unittest.skipUnless(shutil.which("git"), "git is required")
class Cli(unittest.TestCase):
    def test_measure_and_lanes_need_no_journal_and_rank_writes_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SwarmStore(root / "state", clock=Clock(1_790_000_000.0))
            store.close()
            script = REPO / "scripts" / "harness_improve.py"
            lanes_out = subprocess.run([sys.executable, str(script), "lanes"], capture_output=True, text=True, timeout=120)
            self.assertEqual(sorted(json.loads(lanes_out.stdout)["lanes"]), ["data", "execution", "memory", "research"])
            measured = subprocess.run([sys.executable, str(script), "measure", "--swarm", str(root / "state"), "--seconds", "3600",
                                       "--until", "1790000100", "--out", str(root / "m.json")], capture_output=True, text=True,
                                      timeout=120)
            self.assertEqual(measured.returncode, 0, measured.stdout + measured.stderr)
            self.assertEqual(oct((root / "m.json").stat().st_mode & 0o777), "0o600")
            doc = json.loads((root / "m.json").read_text())
            self.assertEqual(sorted(doc["lanes"]), ["data", "execution", "memory", "research"])
            base = "a" * 40
            refused = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "rank", "--measurement",
                                      str(root / "m.json"), "--base", base], capture_output=True, text=True, timeout=120)
            self.assertIn("digest", json.loads(refused.stdout)["error"])
            doc["source"].update(digest="d" * 64, heartbeat_age=5.0)
            (root / "m.json").write_text(json.dumps(doc))
            ranked = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "rank", "--measurement",
                                     str(root / "m.json"), "--base", base, "--out", str(root / "c.json")],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(ranked.returncode, 0, ranked.stdout + ranked.stderr)
            self.assertFalse(any(c["captured"] for c in json.loads((root / "c.json").read_text())["candidates"]))
            self.assertEqual(len(list((root / "j" / "measurements").iterdir())), 1)
            steps = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "next"], capture_output=True,
                                   text=True, timeout=120)
            self.assertEqual(json.loads(steps.stdout), {"next": []})

    def test_the_observer_writes_its_ranked_lanes_to_its_own_directory_only(self):
        from scripts import harness_improve as cli

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SwarmStore(root / "state", clock=Clock(1_790_000_000.0))
            store.close()
            before = sorted(p.name for p in (root / "state").iterdir())
            (root / "harness").mkdir()
            state = cli.lanes_snapshot(root / "harness", root / "state", now=1_790_000_100.0)
            self.assertEqual(state["lanes_captured"], 0)
            ranked = json.loads((root / "harness" / "lanes-ranked.json").read_text())
            self.assertEqual(ranked["policy"], lanes.POLICY)
            self.assertTrue(all(not c["captured"] for c in ranked["candidates"]))
            self.assertEqual(oct((root / "harness" / "lanes-measurement.json").stat().st_mode & 0o777), "0o600")
            self.assertEqual(before, sorted(p.name for p in (root / "state").iterdir()))


if __name__ == "__main__":
    unittest.main()
