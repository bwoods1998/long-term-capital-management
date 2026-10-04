"""THE LADDER'S JUDGE (`scripts/ladder_judge.py`): the file that alone says whether the forward ladder may bind. It is
frozen: byte for byte the file whose sha256 was pinned before the confirmation run (a changed judge is another judge, and
this test fails). And its verdict on synthetic desks built here: every item of its rule met, and each of the three
missed alone; only the first 32 entrants of a desk counted, whatever their outcome; an input it cannot judge refused.
Standard library only, as the judge is."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ladder_judge.py"
#: The frozen judge (pinned before the confirmation run; the benchmark's module docstring names the file).
SHA256 = "38efdb1b83233a7eb1a475c01d600ec43cb0187368cb90a6f511665de0cd8f77"
REPLICATIONS = 30
NEGATIVE = ("absent", "absent_fat", "absent_sparse", "cost_erased", "drift_only", "fading", "skewed_null")
MET = "VERDICT: rule v2 is met on every item: ladder.binding may be true."


def judge():
    spec = importlib.util.spec_from_file_location("ladder_judge_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entrants(kind, world, promoted, n, *, first=0):
    """`n` entrants of one kind, ids from `first`: `promoted` = (ladder, sealed with holds, sealed bare), how many of
    them each design promoted (the first so many, spread over the desks by `desks`)."""
    return [{"id": first + i, "world": world, "kind": kind, "ladder": i < promoted[0], "sealed": i < promoted[1],
             "sealed_bare": i < promoted[2], "ladder_outcome": "promoted" if i < promoted[0] else "window"}
            for i in range(n)]


def desks(single=None, mixed_negative=(0, 0, 0), mixed_positive=(300, 290, 280), replications=REPLICATIONS):
    """A run's desks, `replications` of each judged world, 32 counted entrants a desk and 4 more that are not counted.
    `single`: {negative world: (ladder, sealed, bare) false promotions over its 960 counted entrants} (none unnamed).
    The mixed desks: 16 negatives and 16 positives a desk, 480 of each: `mixed_negative` false promotions and
    `mixed_positive` promotions (so 480 less it are missed)."""
    single = dict(single or {})
    out = []
    for world in NEGATIVE:
        pool = entrants("negative", world, single.get(world, (0, 0, 0)), 32 * replications)
        for r in range(replications):
            rows = [dict(row, id=i) for i, row in enumerate(pool[32 * r:32 * r + 32])]
            # A third generation: promoted by every design, or still running. Never counted.
            late = [{"id": 32 + i, "world": world, "kind": "negative", "ladder": i < 2, "sealed": True, "sealed_bare": True,
                     "ladder_outcome": "promoted" if i < 2 else "running"} for i in range(4)]
            out.append({"world": world, "replication": r, "rows": rows + late})
    negatives = entrants("negative", "fading", mixed_negative, 16 * replications)
    positives = entrants("positive", "planted_dense", mixed_positive, 16 * replications)
    for r in range(replications):
        rows = [dict(row, id=i) for i, row in enumerate(negatives[16 * r:16 * r + 16])]
        rows += [dict(row, id=16 + i) for i, row in enumerate(positives[16 * r:16 * r + 16])]
        late = [{"id": 32 + i, "world": "planted_dense", "kind": "positive", "ladder": False, "sealed": False,
                 "sealed_bare": False, "ladder_outcome": "running"} for i in range(4)]
        out.append({"world": "mixed", "replication": r, "rows": rows + late})
    return out


class TheFrozenJudge(unittest.TestCase):
    def test_the_file_is_the_pinned_one_byte_for_byte(self):
        self.assertEqual(hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), SHA256)

    def test_it_stands_on_the_standard_library_alone_and_explains_itself_without_input(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        nodes = list(ast.walk(tree))
        imported = {alias.name.split(".")[0] for node in nodes if isinstance(node, ast.Import) for alias in node.names}
        imported |= {str(node.module).split(".")[0] for node in nodes if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imported, {"__future__", "collections", "json", "math", "sys"})
        self.assertLessEqual(imported, set(sys.stdlib_module_names) | {"__future__"})
        # Run as the operator runs it, away from the repository (isolated: neither it nor its directory on the path).
        done = subprocess.run([sys.executable, "-I", str(SCRIPT)], cwd=tempfile.gettempdir(), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn("THE LADDER'S BINDING VERDICT", done.stdout)
        self.assertIn("THE COUNT (primary)", done.stdout)


class ItsVerdict(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.judge = judge()
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_judge(self, *parts):
        """(exit code, printed lines) of the judge on parts, each a list of desks written as one file."""
        paths = []
        for k, part in enumerate(parts):
            path = Path(self.tmp.name) / f"{self.id()}-{k}.json"
            path.write_text(json.dumps({"desks": part}))
            paths.append(str(path))
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = self.judge.main(paths)
        return code, printed.getvalue().splitlines()

    def item(self, lines, text):
        """The judge printed this item's line, to the character."""
        self.assertIn("  item " + text, lines)

    def not_met(self, *items):
        return f"VERDICT: rule v2 is NOT met ({', '.join(items)}): ladder.binding stays false; the ladder records."

    def test_every_item_met_the_ladder_may_bind(self):
        code, lines = self.run_judge(desks({"absent": (1, 2, 3), "fading": (9, 9, 12)}, mixed_negative=(4, 5, 4)))
        self.assertEqual(code, 0)
        self.assertEqual(lines[0], "rule v2, the first 32 entrants a desk; replications a world: 30")
        self.assertEqual(lines[-1], MET)
        # Item 1: every world's rate at or under 1.0% (9 of 960 is 0.938%) and no Fisher rejection against the sealed
        # look with holds. The 60 promotions of each world's third generation are nowhere in the counts.
        self.item(lines, "1  absent         ladder    1/  960 =  0.104%  sealed    2  bare    3  Fisher p 0.8752  ok")
        self.item(lines, "1  fading         ladder    9/  960 =  0.938%  sealed    9  bare   12  Fisher p 0.5932  ok")
        self.item(lines, "1  skewed_null    ladder    0/  960 =  0.000%  sealed    0  bare    0  Fisher p 1.0000  ok")
        self.item(lines, "1  mixed          ladder    4/  480 =  0.833%  sealed    5  bare    4  Fisher p 0.7471  ok")
        # Item 2: at or under the FEWER of the sealed look with and without its holds, in each pool (10 <= 11; 4 <= 4).
        self.item(lines, "2  single-world negatives: ladder 10/6720  sealed 11  bare 15  ok")
        self.item(lines, "2  mixed negatives:        ladder 4/480  sealed 5  bare 4  ok")
        # Item 3: the mixed desks' positives missed, against the fewer of the sealed look's two.
        self.item(lines, "3  mixed positives missed: ladder 180/480 = 0.3750  sealed 190 = 0.3958  bare 200 = 0.4167  "
                      "margin +10  ok")
        self.assertEqual(sum(1 for line in lines if line.startswith("  item ")), 8 + 2 + 1)
        self.assertFalse(any("FAIL" in line for line in lines))

    def test_item_1_missed_on_the_cap_alone(self):
        # 10 of 960 is 1.042%: over the cap, though the sealed look promoted more (no Fisher rejection, item 2 met).
        code, lines = self.run_judge(desks({"fading": (10, 12, 12)}))
        self.assertEqual(code, 1)
        self.item(lines, "1  fading         ladder   10/  960 =  1.042%  sealed   12  bare   12  Fisher p 0.7395  FAIL")
        self.assertEqual(lines[-1], self.not_met("1 cap fading"))
        self.assertEqual(sum(1 for line in lines if line.endswith("FAIL")), 1)

    def test_item_1_missed_on_the_fisher_test_alone(self):
        # 6 of 960 against the sealed look's 0 of 960: under the cap, but more than the sealed look beyond chance. The
        # pool still holds: another world's sealed promotions keep the ladder's total under the sealed look's.
        code, lines = self.run_judge(desks({"cost_erased": (6, 0, 0), "drift_only": (0, 20, 20)}))
        self.assertEqual(code, 1)
        self.item(lines, "1  cost_erased    ladder    6/  960 =  0.625%  sealed    0  bare    0  Fisher p 0.0155  FAIL")
        self.item(lines, "2  single-world negatives: ladder 6/6720  sealed 20  bare 20  ok")
        self.assertEqual(lines[-1], self.not_met("1 fisher cost_erased"))
        p = math.comb(960, 6) / math.comb(1920, 6)
        self.assertAlmostEqual(self.judge.fisher_greater(6, 960, 0, 960), p, places=12)
        self.assertLess(p, 0.05)

    def test_item_2_missed_alone_in_each_pool_and_on_the_sealed_look_without_its_holds(self):
        # One false promotion where the sealed look made none: item 1 holds (0.104%, Fisher p 0.5), the pool does not.
        code, lines = self.run_judge(desks({"absent": (1, 0, 0)}))
        self.assertEqual(code, 1)
        self.item(lines, "1  absent         ladder    1/  960 =  0.104%  sealed    0  bare    0  Fisher p 0.5000  ok")
        self.item(lines, "2  single-world negatives: ladder 1/6720  sealed 0  bare 0  FAIL")
        self.assertEqual(lines[-1], self.not_met("2 pooled single"))
        # Under the sealed look with its holds, over the one without: the fewer of the two is the bar.
        code, lines = self.run_judge(desks({"absent": (2, 3, 1)}))
        self.assertEqual(code, 1)
        self.item(lines, "2  single-world negatives: ladder 2/6720  sealed 3  bare 1  FAIL")
        self.assertEqual(lines[-1], self.not_met("2 pooled single"))
        # The mixed desks' negatives are a pool of their own.
        code, lines = self.run_judge(desks(mixed_negative=(1, 0, 0)))
        self.assertEqual(code, 1)
        self.item(lines, "1  mixed          ladder    1/  480 =  0.208%  sealed    0  bare    0  Fisher p 0.5000  ok")
        self.item(lines, "2  mixed negatives:        ladder 1/480  sealed 0  bare 0  FAIL")
        self.assertEqual(lines[-1], self.not_met("2 pooled mixed"))

    def test_item_3_missed_alone(self):
        # One more missed signal than the sealed look with its holds (the fewer of its two).
        code, lines = self.run_judge(desks(mixed_positive=(289, 290, 280)))
        self.assertEqual(code, 1)
        self.item(lines, "3  mixed positives missed: ladder 191/480 = 0.3979  sealed 190 = 0.3958  bare 200 = 0.4167  "
                      "margin -1  FAIL")
        self.assertEqual(lines[-1], self.not_met("3 missed"))
        # A tie is met; the sealed look without its holds can be the bar too.
        self.assertEqual(self.run_judge(desks(mixed_positive=(290, 290, 280)))[1][-1], MET)
        code, lines = self.run_judge(desks(mixed_positive=(285, 280, 290)))
        self.item(lines, "3  mixed positives missed: ladder 195/480 = 0.4062  sealed 200 = 0.4167  bare 190 = 0.3958  "
                      "margin -5  FAIL")
        self.assertEqual((code, lines[-1]), (1, self.not_met("3 missed")))

    def test_every_missed_item_is_named(self):
        code, lines = self.run_judge(desks({"fading": (10, 0, 0)}, mixed_negative=(5, 0, 0), mixed_positive=(0, 1, 1)))
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], self.not_met("1 cap fading", "1 fisher fading", "1 cap mixed", "1 fisher mixed",
                                                 "2 pooled single", "2 pooled mixed", "3 missed"))

    def test_the_parts_of_a_run_are_judged_together_and_the_single_world_positive_desks_only_read(self):
        run = desks({"absent": (1, 2, 3)})
        premium = [{"world": "planted_premium", "replication": r,
                    "rows": entrants("positive", "planted_premium", (0, 32, 32), 32)} for r in range(REPLICATIONS)]
        whole = self.run_judge(run + premium)
        split = self.run_judge([d for d in run if d["world"] != "mixed"], [d for d in run if d["world"] == "mixed"],
                               premium)
        self.assertEqual(whole, split)
        self.assertEqual((whole[0], whole[1][-1]), (0, MET), "a single-world positive desk is a secondary reading")
        self.assertIn("    planted_premium      missed: ladder 960/960  sealed 0", whole[1])

    def test_an_input_the_design_does_not_pin_is_refused_never_judged(self):
        def refused(part, why):
            printed = io.StringIO()
            path = Path(self.tmp.name) / f"{self.id()}.json"
            path.write_text(json.dumps({"desks": part}))
            with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(printed):
                self.judge.main([str(path)])
            self.assertIn(why, str(caught.exception.code))
            self.assertNotIn("VERDICT", printed.getvalue())

        good = desks()
        running = json.loads(json.dumps(good))
        running[3]["rows"][31]["ladder_outcome"] = "running"
        refused(running, "judge: absent replication 3: counted entrants [31] are still running")
        short = json.loads(json.dumps(good))
        short[0]["rows"] = short[0]["rows"][:31]
        refused(short, "judge: absent replication 0 has not its first 32 entrants")
        refused(good + [good[0]], "judge: absent replication 0 appears twice")
        refused([d for d in good if d["world"] != "fading"], "judge: no desks of ['fading']")
        refused([d for d in good if not (d["world"] == "mixed" and d["replication"] == 29)],
                "judge: every judged world needs the same number of replications, at least 30")
        refused(desks(replications=29), "at least 30")
        refused([dict(d, replication=30) if d["replication"] == 7 else d for d in good], "replications are not 0..29")

    def test_the_verdict_is_the_printed_line_and_never_the_exit_status_alone(self):
        """As an operator runs it (a process, its own interpreter): "met" exits 0 and "NOT met" exits 1, each with its
        `VERDICT:` line; an input the judge refuses ALSO exits 1, with its message and no `VERDICT:` line (the frozen
        docstring says 2, which only a call without arguments returns). An exit 1 without the line is never "not met"."""
        def process(name, part):
            path = Path(self.tmp.name) / f"process-{name}.json"
            path.write_text(json.dumps({"desks": part}))
            done = subprocess.run([sys.executable, "-I", str(SCRIPT), str(path)], cwd=tempfile.gettempdir(),
                                  capture_output=True, text=True, timeout=120)
            return done.returncode, [line for line in done.stdout.splitlines() if line.startswith("VERDICT")], done.stderr

        self.assertEqual(process("met", desks())[:2], (0, [MET]))
        code, verdict, _ = process("missed", desks(mixed_positive=(279, 290, 280)))
        self.assertEqual((code, verdict), (1, [self.not_met("3 missed")]))
        code, verdict, said = process("refused", [d for d in desks() if d["world"] != "fading"])
        self.assertEqual((code, verdict), (1, []), "the same status as a rule not met, and no verdict")
        self.assertIn("judge: no desks of ['fading']", said)


if __name__ == "__main__":
    unittest.main()
