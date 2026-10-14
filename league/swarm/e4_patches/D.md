# E4 patches authored by package D

Package D (xs engine) authors patch 14: `league/tests/test_equity_decider.py`.

Each patch below: its number in `README.md`, the file, the anchor (a statement, never a line number), the exact
unified diff against the integration head, and the test that holds it.

## Patch 14: `league/tests/test_equity_decider.py` (the panel kind now serves five ops)

WHY. Step 0's `league/xs/child.py` was the captain's A13 slot: `handle` refused every op, and two tests of
`test_equity_decider.py` held it to that. Package D builds the kind (`OPS = ("load", "drop", "decide", "needs",
"run")`), so the slot test becomes the ops test. Until this patch is applied those two tests FAIL on package D's
branch, and only those two: `TheEquityKindInProcess.test_the_panel_kind_is_a_slot_that_refuses_every_op` and
`TheTable.test_the_childs_runtime_holds_every_kind_module_and_what_it_imports`.

APPLY AFTER PACKAGE C IS MERGED (the merge order has C before D): the new test loads a panel program through the
real `league.xs.program.load_program`, which was a stub at the base.

ANCHORS (by statement):
1. in `class TheEquityKindInProcess`, the whole method `test_the_panel_kind_is_a_slot_that_refuses_every_op`
   (between `test_needs_and_run_keep_nothing` and `test_unknown_ops_and_kinds_and_the_remembered_routes`) is
   replaced by `test_the_panel_kind_serves_five_ops`;
2. in `class TheTable`, `test_the_childs_runtime_holds_every_kind_module_and_what_it_imports`: the docstring's last
   sentence; the message of the assertion that the runtime holds `league/xs/__init__.py` and `league/xs/child.py`;
   and, in the child's script, the two lines that begin `"panel = kinds.module_for('panel').handle('run', {}, {})`
   and `"assert panel['ok'] is False and panel['refused'] is True`, which become the seven lines that check the
   kind's ops, import the modules it imports per op and ask it a panel program's NEEDS.

Nothing else of the file changes (`TheTable.test_module_for` already holds `KINDS["panel"]` and the runtime entry).

THE DIFF (against 24a52b11, the base of every E4 package; `git apply` takes it as it is):

```diff
diff --git a/league/tests/test_equity_decider.py b/league/tests/test_equity_decider.py
index 89eb2103..11891741 100644
--- a/league/tests/test_equity_decider.py
+++ b/league/tests/test_equity_decider.py
@@ -204,26 +204,50 @@ class TheEquityKindInProcess(unittest.TestCase):
         args, kw = self.runs[-1]
         self.assertEqual((args, kw), (("C", {"h": 8}, {"n": 3}), {"name": "r", "k": 1.5, "capital": "1000"}))
 
-    def test_the_panel_kind_is_a_slot_that_refuses_every_op(self):
-        """A13: "panel" -> league/xs/child.py, whose `handle` refuses whatever is asked: nothing loads, decides or
-        runs, and the House's side reads a refusal (a load raises ProgramRefused and is not remembered)."""
+    def test_the_panel_kind_serves_five_ops(self):
+        """Release E4 (the captain's A13 slot, now built): "panel" -> league/xs/child.py serves the equity kind's five
+        ops for panel programs through the same generic dispatch: a load is remembered for a restarted child, NEEDS
+        and a refusal come back as the equity kind's do, a job the House could not ask is a failed decide that is
+        never the program's, and an unknown op is an error, never a refusal. The kind's own semantics (the KEEP
+        rule's orders, the standing target, the ineligible lots, a run) are held by league/tests/test_xs_runner.py
+        and test_xs_i6.py."""
         from league.xs import child as panel
 
-        self.assertEqual(panel.OPS, ())
-        for op in ("load", "drop", "decide", "needs", "run", "train", "", None):
-            state: dict = {}
-            answer = panel.handle(op, {"key": "k", "code": "raise SystemExit", "jobs": [{"key": "k"}]}, state)
-            self.assertEqual((answer["ok"], answer["refused"]), (False, True), op)
-            self.assertIn("not built", answer["error"])
-            self.assertEqual(state, {}, "the slot keeps nothing")
-        for op in ("decide", "needs", "run"):
-            answer = self.decider.kind("panel", op, {"jobs": [{"key": "a"}], "code": "C"})
-            self.assertEqual((answer["ok"], answer["refused"]), (False, True), op)
+        code = ("NEEDS = {'panel': 'sp500', 'history': 20, 'max_names': 5, 'rebalance': 'weekly'}\n"
+                "PARAMS = {'w': 0.2}\n"
+                "def decide(ctx):\n"
+                "    return {'hold': True}\n")
+        self.assertEqual(panel.OPS, ("load", "drop", "decide", "needs", "run"))
+        info = self.decider.kind_load("panel", "p@1:r", {"code": code, "params": {"w": 0.1}, "name": "p"})
+        self.assertEqual(info["needs"], {"panel": "sp500", "history": 20, "max_names": 5, "rebalance": "weekly",
+                                         "weekday": 0, "max_hold_sessions": 60})
+        self.assertEqual((info["params"], len(info["sha"]), len(info["run_sha"])), ({"w": 0.1}, 64, 64))
+        self.assertIn(("panel", "p@1:r"), self.decider.kind_loaded, "remembered for a restarted child")
+        self.assertEqual(set(self.decider._kinds["panel"]["runners"]), {"p@1:r"})
+        needs = self.decider.kind("panel", "needs", {"code": code, "params": {}, "name": "n"})
+        self.assertEqual((needs["ok"], needs["needs"]["panel"], needs["params"]), (True, "sp500", {"w": 0.2}))
+        self.assertEqual(set(self.decider._kinds["panel"]["runners"]), {"p@1:r"}, "learning NEEDS keeps nothing")
+        jobs = [{"key": "ghost", "inputs": None, "called": True}, {"key": "p@1:r", "inputs": None, "called": True}]
+        answer = self.decider.kind("panel", "decide", {"jobs": jobs})
+        self.assertTrue(answer["ok"])
+        ghost, mine = answer["results"]["ghost"], answer["results"]["p@1:r"]
+        self.assertEqual((ghost["missing"], ghost["failed"], ghost["orders"]), (True, True, []))
+        self.assertEqual((mine["failed"], mine["orders"], mine["hold"]), (True, [], True))
+        self.assertTrue(mine["error"].startswith("ctx: "), "inputs no ctx can be built from: the House's failure")
+        self.assertEqual(mine["stats"]["calls"], 0, "no program code ran")
+        unknown = self.decider.kind("panel", "train", {})
+        self.assertFalse(unknown["ok"])
+        self.assertIn("unknown panel op", unknown["error"])
+        self.assertNotIn("refused", unknown)
         with self.assertRaises(D.ProgramRefused):
-            self.decider.kind_load("panel", "p@1:r", {"code": "C", "params": {}, "name": "p"})
-        self.assertEqual(self.decider.kind_loaded, {}, "a refused load is not remembered for a restarted child")
+            self.decider.kind_load("panel", "bad@1:r", {"code": "import os\n" + code, "params": {}, "name": "bad"})
+        self.assertNotIn(("panel", "bad@1:r"), self.decider.kind_loaded,
+                         "a refused load is not remembered for a restarted child")
+        refused = self.decider.kind("panel", "needs", {"code": "import os\n" + code, "params": {}, "name": "bad"})
+        self.assertEqual((refused["ok"], refused["refused"]), (False, True))
         self.decider.kind_drop("panel", "p@1:r")
-        self.assertNotIn("runners", self.decider._kinds.get("panel", {}))
+        self.assertEqual(self.decider._kinds["panel"]["runners"], {})
+        self.assertEqual(self.decider.kind_loaded, {})
 
     def test_unknown_ops_and_kinds_and_the_remembered_routes(self):
         self.assertIn("unknown equity op", self.decider.kind("equity", "train", {})["error"])
@@ -274,7 +298,9 @@ class TheTable(unittest.TestCase):
         """A root House's child runs from a copy of `runtime_files()` alone: from such a copy, with the House's empty
         environment and -E -s, the child imports the decider, the kind table, every kind's module and the modules the
         "equity" kind imports per op (the program, the ctx, the runner), and answers a "run" (the engine over a store
-        slice: its calendar is `ltcm.data`'s, imported only when a run reads it)."""
+        slice: its calendar is `ltcm.data`'s, imported only when a run reads it); and the "panel" kind's module with
+        the modules it imports per op, which answers a panel program's NEEDS (a panel run from such a copy is
+        league/tests/test_xs_runner.py's)."""
         files = D.runtime_files()
         repo = D.REPO
         for name in D.RUNTIME_FILES:
@@ -282,14 +308,19 @@ class TheTable(unittest.TestCase):
         for directory in ("league/equity", "league/gym", "league/xs"):
             for path in (repo / directory).glob("*.py"):
                 self.assertIn(path.relative_to(repo).as_posix(), files)
-        self.assertLessEqual({"league/xs/__init__.py", "league/xs/child.py"}, set(files), "the panel kind's slot (A13)")
+        self.assertLessEqual({"league/xs/__init__.py", "league/xs/child.py"}, set(files), "the panel kind (A13)")
         self.assertFalse([f for f in files if not f.endswith(".py")], "documentation is never copied")
         script = ("import league.live.decider\n"
                   "from league.equity import kinds\n"
                   "for kind in kinds.KINDS:\n"
                   "    kinds.module_for(kind)\n"
-                  "panel = kinds.module_for('panel').handle('run', {}, {})\n"
-                  "assert panel['ok'] is False and panel['refused'] is True, panel\n"
+                  "panel = kinds.module_for('panel')\n"
+                  "assert panel.OPS == ('load', 'drop', 'decide', 'needs', 'run'), panel.OPS\n"
+                  "import league.xs.program, league.xs.ctx, league.xs.runner, league.xs.store, league.xs.engine\n"
+                  "needs = panel.handle('needs', {'code': \"NEEDS = {'panel': 'sp500', 'rebalance': 'weekly'}\\n\"\n"
+                  "                               \"PARAMS = {}\\ndef decide(ctx):\\n    return {'hold': True}\\n\",\n"
+                  "                               'params': {}, 'name': 'n'}, {})\n"
+                  "assert needs['ok'] is True and needs['needs']['panel'] == 'sp500', needs\n"
                   "import league.equity.program, league.equity.ctx, league.equity.runner, league.equity.store\n"
                   "import tempfile\n"
                   "from league.equity import child, synth\n"
```

THE TEST THAT HOLDS IT: the file itself. With packages C and D merged and this patch applied,
`python -m unittest league.tests.test_equity_decider` runs 14 tests, all passing (checked on Python 3.14 and 3.11
in a throwaway tree that merged package C's branch into package D's). The panel kind's own semantics are held by
`league/tests/test_xs_runner.py` (the five ops through the real `InlineDecider`; a "run" in a subprocess from a copy
of the child's runtime files alone) and `league/tests/test_xs_i6.py` (seal X3).

## Not a patch: what package D added beside the stubs (for `league/xs/E4_INTERFACES.md`, the integrator's file)

Additive names and keywords in package D's OWN modules; no other package's stub or signature changed.
- `engine.plan_orders(..., eligible=None)`: with `standing=True`, the ids of U at this close (the engine and the
  child pass them); `engine.refused_whole(rejects)` and `engine.ORDER_CAP` (how a caller reads "refused whole");
  `engine.build_ctx(inputs, derived)` (the one call of `ctx.build`: it hands package C the decision's own `Derived`
  when `ctx.build` takes a `derived` keyword, as package C's does); `engine.ratio_tolerance`, `engine.split_of`
  (the vendor's cents); `engine.look_spans(bars)`; `engine.Log.decision(t)`. A `Log` holds ONE decision row A CLOSE
  (called or not), and its lot rows also carry `id` (the salted id; never an aid).
- `placebo.validity`, `prices`, `entry_validity`, `vanish_sessions` (what the bars say: the engine's fills, entry
  validity and vanish rule and the residual read these); `placebo.VANISHED`. `placebo.run`'s block also carries
  `lots` and, per span, `t_x` and `count`.
- `results.nw_t`, `close_dates`, `pick_counts`; `results.summarize(..., beside=)`. The summary also carries
  `realized`, `costs`, `refused {no_bar, ahead, last}` and `open_lots`; `vanished` is `{deal, other}` (a slice's
  `exit` flag tells a deal from every other way, an unknown one included); a result also carries `universe` (24 hex
  over the slice's ids, `elig0`, half-spreads and exits: what tells a half run's identity from the whole run's) and
  `actions`; a lot row also carries `tag` ("ineligible" on that House exit) and `hs_exit`.
- `runner.gym_key(run_sha, window, first)` (D8's run key); a decide answer also says `called` and `standing`; a
  hold-day job's `standing` may carry `pending` (ids with a buy working).
