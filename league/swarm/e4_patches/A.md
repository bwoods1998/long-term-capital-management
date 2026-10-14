# E4 patches authored by package A

Package A (data) authors patch 10: `league/ops/registry.py`.

Each patch below: its number in `README.md`, the file, the anchor (a statement, never a line number), the exact
unified diff against the integration head, and the test that holds it.

Package A's own files need NO other edit of an existing file: `league/ops/equity_universe.py` and
`league/ops/equity_panel.py` are whole, and their jobs answer `skipped` (never a crash) while their registry rows,
package C's C0 (`league.xs.config.quiet`, `league.xs.store.write_panel`) or the universe are not there.

## Patch 10: `league/ops/registry.py`, the six job rows (E4-SPEC 13)

**Anchor:** the END of the `JOBS` tuple: after the `dlane` row's last line (`"<state>/dlane-report.json; the program
loss line (A1.3), the lane off too"),`) and before the tuple's closing parenthesis. The six rows go LAST, so at a
House start every older job due at the same instant still goes first (`runner.due` starts them in this order). If
release E3 has added rows there first, these six go after E3's.

**The rows** are E4-SPEC 13's table to the figure: `equity_universe` at the start and daily 01:40Z (120 / 900);
`equity_panel` after it (600 / 3300); `equity_spreads` daily 06:30Z (300 / 3000); `equity_neff` the month's first
Saturday 10:00Z (600 / 900); `french` the month's first Saturday 11:00Z (60 / 300); `xs_zero_edge` Sundays 06:00,
08:00, 10:00 and 12:00Z (2400 / 3000, grace 100 minutes); every one `in_pause=True` (they read the gateway and
write their own files) and none `paid`. Each `wall` is the figure its module asks `league.xs.config.quiet` with
(`WALL_S`), and every wall is under the grant's 70-minute grace.

```diff
--- a/league/ops/registry.py
+++ b/league/ops/registry.py
@@ -141,6 +141,35 @@ JOBS: tuple[Job, ...] = (
         what="the direction lane's report (operator-only): the funnel per lane, the Probe envelope, the DONE meter of the "
              "pinned rule (done_screen, done_all) beside the same-risk buy-and-hold, alarms A1-A9, PL1 and K5, into "
              "<state>/dlane-report.json; the program loss line (A1.3), the lane off too"),
+    # THE PANEL LANE's data and measurement jobs (release E4, "breadth"; league/xs/E4_INTERFACES.md). Each one's first
+    # statement is `league.xs.config.quiet(now, its own wall)`: a start that could still be working at a wall of the
+    # session (09:25-09:45 and 15:50-16:35 ET) is a `skipped` receipt, and the occurrence is not lost (the at-start one
+    # of `equity_universe` runs at its next daily time, and `equity_panel` after it). They read the gateway and write
+    # their own files under <state>/equity-daily/, so they run in a pause too; with `elane.panel.mode` "off" nothing
+    # else of the lane runs. They go last: at a House start every older job that is due at the same instant goes first.
+    Job("equity_universe", "league.ops.equity_universe", (S.at_start(), S.daily(1, 40)), grace=3 * HOUR, cpu=120,
+        wall=900, in_pause=True, owner="breadth",
+        what="the point-in-time S&P 500 membership from a pinned public file and the changes table (the gateway's "
+             "reader), the assets and their aids, the audit, into <state>/equity-daily/universe/ (counts only out)"),
+    Job("equity_panel", "league.ops.equity_panel", (S.after("equity_universe"),), grace=3 * HOUR, cpu=600, wall=3300,
+        in_pause=True, owner="breadth",
+        what="the panel's daily bars through the venue's asof (never 2020), the store's vintage rule, the coverage "
+             "audit and its verdict, the nightly I6, into <state>/equity-daily/panel/"),
+    Job("equity_spreads", "league.ops.equity_spreads", (S.daily(6, 30),), grace=6 * HOUR, cpu=300, wall=3000,
+        in_pause=True, owner="breadth",
+        what="the panel's half-spreads: quote samples at the instants the book trades, on Train-segment sessions, "
+             "resumable, into <state>/equity-daily/spreads.json"),
+    Job("equity_neff", "league.ops.equity_neff", (S.monthly_first(5, 10, 0),), grace=6 * HOUR, cpu=600, wall=900,
+        in_pause=True, owner="breadth",
+        what="the panel's independent names (N_eff on Train segment 2) into <state>/equity-daily/neff.json"),
+    Job("french", "league.ops.french", (S.monthly_first(5, 11, 0),), grace=6 * HOUR, cpu=60, wall=300,
+        in_pause=True, owner="breadth",
+        what="the French library's daily factors where a route to them exists (none today: a skipped receipt)"),
+    Job("xs_zero_edge", "league.ops.xs_zero_edge",
+        (S.weekly(6, 6, 0), S.weekly(6, 8, 0), S.weekly(6, 10, 0), S.weekly(6, 12, 0)), grace=100 * MINUTE, cpu=2400,
+        wall=3000, in_pause=True, owner="breadth",
+        what="the panel Train bar's zero-edge expected column: seeded random-score programs through the whole bar, "
+             "25 a run, into the swarm store's kv elane_xs_zero_edge"),
 )
 
 
```

**The existing test this row set moves** (`league/tests/test_ops_int_ops.py`,
`RunnerHolds.test_the_registry_marks_what_runs_in_a_pause`: it holds the exact set of jobs that run in a pause; anchor:
the set literal that ends `"equity_data", "equity_twins"})`):

```diff
--- a/league/tests/test_ops_int_ops.py
+++ b/league/tests/test_ops_int_ops.py
@@ -184,10 +184,13 @@ class RunnerHolds(unittest.TestCase):
         jobs = by_name()
         # The read-only checks (the stall alarm among them: a pause left on is one of its causes), the close economics,
         # the budget and its hourly refresh, the fast lane's direction closes and report, the learning game's report and
-        # the direction lane's; and (release E1) the equity lane's daily store and its twins' measurement records.
+        # the direction lane's; (release E1) the equity lane's daily store and its twins' measurement records; and
+        # (release E4) the panel lane's data and measurement jobs, which read the gateway and write their own files.
         self.assertEqual({j.name for j in JOBS if j.in_pause}, {"budget", "budget_refresh", "clock", "preopen", "economics",
                                                                 "stall", "direction", "fast_lane", "game", "dlane",
-                                                                "equity_data", "equity_twins"})
+                                                                "equity_data", "equity_twins", "equity_universe",
+                                                                "equity_panel", "equity_spreads", "equity_neff",
+                                                                "french", "xs_zero_edge"})
         self.assertEqual({j.name for j in JOBS if j.paid}, {"postmortem", "agenda", "engineer"})
         longest = max(j.wall for j in JOBS)
         self.assertGreaterEqual(jobs["grant"].grace, longest + 5 * 60, "an hourly grant waits behind the longest job, never missed")
```

**The test that holds the patch:** `league/tests/test_equity_panel.py` `TheRegistryRows`. It reads THIS file: the
added lines of the first diff above are evaluated as `Job` rows against `league.ops.registry`'s own names, and held to
E4-SPEC 13 (the names in order, each module, its triggers, grace, `cpu` and `wall`, `in_pause`, never `paid`; each
`wall` equal to its module's `WALL_S`; no daily trigger inside a session window of either season; every wall under
the grant's grace). Before the patch is applied it holds that the diff's context lines are the registry's own and
that no row's name is taken; once it is applied it holds the registry's six rows equal to these. So the same test
passes on package A's branch and on the integrated head, and fails if the patch is applied with a figure changed.

Checked on a scratch merge of this branch with package C's head and both diffs applied: the whole league suite on
Python 3.14 (the log is named in package A's report).

## What the integrator does NOT need to do for package A

- No edit of `league/ops/equity_data.py`, `league/ops/context.py` or any E1 file: the panel job imports
  `equity_data.last_closed`, `ny_day`, `ny_moment`, `NEW_YORK`, `audit`, `RAW_JUMP`, `SPLIT_JUMP` and
  `SPLIT_RAW_TOLERANCE` as they are, and `league.equity.live._bars_verdict` inside `i6_check` for a live decision
  (the spec's own rule: no second verdict for "the same bars").
- No gateway change: `GET /v1/alpaca/v2/stocks/bars` (with `asof`), `GET /v1/alpaca/v2/assets/<SYM>` and
  `POST /v1/web/fetch` are routes the gateway already allows.

**After the review (the fix pass; the diff above is the record of what was applied).** The registry now differs from
it in two triggers and nothing else, and `TheRegistryRows.REVIEWED` names them: `equity_universe` runs daily at 01:40Z
with NO at-start trigger (at a House start before an open the chain's whole fetch, 55 minutes of wall, held the one
ops child past the pre-open's grace), and `equity_panel` has ITS OWN daily time, 01:55Z, in place of
`after("equity_universe")` (a night the universe job failed fetched no bars, ran no I6 and raised none of the panel
job's alarms; one child runs at a time, so on a normal night it still starts when the universe job has ended). Every
data job's first statement is now the lane's switch (`league.ops.equity_universe.lane_off`): with
`elane.panel.mode` "off" it answers `skipped` before its first gateway call.
