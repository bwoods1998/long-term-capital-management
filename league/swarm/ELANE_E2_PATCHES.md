# Release E2: the patches E2 needs in files it does not own

Branch `feat/equity-e2` (from the skeleton df86ed45). E2 creates `league/swarm/elane_births.py`, `elane_train.py`,
`elane_yield.py`, `elane_seal.py`, `elane_review.py` and their tests, and adds small branches to
`league/swarm/architect.py` and `league/swarm/researcher.py` (E1 never touched either file, so they merge as they are).
Everything else it needs is below, for the integrator, in merge order after E1.

EVERY PATCH IS AN EXACT UNIFIED DIFF AGAINST E1's HEAD aa50c2aa (feat/equity-e1, "equity E1 integration: the end-to-end
test, and the seams it found"). Each was checked with `git apply --check` on that head, and all of them were applied
together to a tree of aa50c2aa plus this branch's files, where these modules pass: test_elane_e2_* (E2's own, with
test_elane_e2_e1: E2 on E1's real code), test_ci, test_game, test_swarm_allocation, test_swarm_rounds,
test_swarm_diagnostician, test_ops_stall, test_dlane*, test_elane, test_elane_gate, test_elane_seeds, test_equity_e2e,
test_equity_identity, test_swarm_store, test_swarm_settings_policy, test_swarm_loop, test_loop_joints, test_researcher,
test_swarm_gate_*, test_gate_contract. Apply them with `git apply` in the order below (they touch different files).

| # | file | owner | what | without it |
|---|---|---|---|---|
| 1 | `league/swarm/loop.py` | swarm (E1) | the two rounds: `elane` (`Architect.equity_pass`) and `elane_train` (`EquityResearcher.run`) | E2 never runs |
| 2 | (none) | | E1's `dlane._born` already skips equity births (A8.12) | |
| 3 | `league/swarm/allocation.py` | unowned (integrator) | `BirthQuota` skips equity births | equity births dilute the options structure families' window shares |
| 4 | `league/swarm/game.py` | unowned (integrator; protected) | `visible_graveyard` drops equity rows (E1's aa50c2aa already counts the learning game's ceiling over options families) | the diagnostician can read an equity row whose lesson tells a Validation or look outcome (A9 D3) |
| 5 | `league/swarm/tournament.py` | swarm (E1) | after `n = elane.next_try(...)`, an E2 family is validated only where `elane_train.may_validate` allows | E1's `next_try` offers a brand-new E2 family's v1 (its candidate is the newest version): the lineage's one try is spent on a program that never met Train or the review |
| 6 | `league/swarm/policy.json` | swarm (E1) | the `elane.e2` block (E2's settings, every value its code default) | the code defaults apply (the same values) |
| 7 | `league/ci.py`, `league/tests/test_ci.py` | money (E1) | the five E2 modules in `PENDING_GATEWAY` (so in `FORBIDDEN`), and the test's pin | E2's bar, quota, route rule, seal and review are editable by a merge route |
| 8 | `league/ops/dlane_report.py` | ops (E1) | the operator's yield-per-dollar record (`elane_yield.report`) | the record exists in the store but no report prints it |
| 9 | `league/swarm/store.py` | swarm (E1) | `retire_gym`'s population floor counts the options families only | with E2's families alive (up to 24 in research, passes waiting), the options floor never binds and the diagnostician can retire the options population toward zero |
| 10 | `league/ops/stall.py`, `league/ops/preopen.py` | ops (E1) | the owner's alarms count the options lanes only: births (a `swarm.born` with an equity lane), the living population, the Gym runs (E2's Train runs on the House), the dry-births tally, and the pre-open population check | E2's births every two hours hide a dead options architect for the 12 h window, its alive families hide a population under its floor, and its Train runs (up to ~72 an hour since A15: two spans at two stresses a version) hide a stalled Gym |

## A15 (the reserve and the restart check): no patch added, no diff changed

Amendment A15 (Train on 2016-19 and 2022-24 only; the Train bar's STATE restart check) is inside E2's own files. For the
integrator:

- NO NEW PATCH. Everything the restart check needs, E1 already provides (read at E1's head 4baf7c10): the isolated
  runner's `decider` and its `Run` (the result with the `store.Bars` it ran on), the decider kinds `kind_load`,
  `kind(..., "decide", ...)` and `kind_drop`, the child's decide answer (`intents`, `stats.calls`,
  `stats.disqualified`, `missing`, `error`), `ctx.inputs_from_bars`, `ctx.lot_row` and `ctx.closed_row`. The list is
  under "What E2 reads of E1" below.
- NO DIFF CHANGED. Patches 1 and 3-10 are as they were (A15 changes no signature a patch calls: patch 1's
  `EquityResearcher(store, router, settings, root=, clock=)`, patch 5's `may_validate`, patch 8's `STATE_KEY`; patch
  6's `elane.e2` block gains no key: `state_every` and `state_match` are rules in `elane_train.BAR`, not settings; patch
  7 protects the same five modules). All nine diffs still pass `git apply --check` on E1's head 4baf7c10 (its
  later edits of tournament.py, policy.json and dlane_report.py sit clear of the hunks); regenerate them as before if
  E1 moves again.
- ONE DESCRIPTION CHANGED, patch 10's: a version's Train run is now four runs (two spans at two stresses), so E2's Train
  runs on the House are up to ~72 an hour, not ~36. The diff is the same (it counts the options lanes only).
- IF A HOOK IS MISSING, E2 FAILS SAFE with no patch: a runner without `decider`, a decider without the kinds, or a
  decide answer without `stats.calls` makes the restart check the House's failure (the version is not scored and
  cannot pass; the third failure in a row raises the `elane_train_state` alert), never a pass.
- NOT NEEDED, ONLY NOTED: E1's `Decider._ask` reloads a kind's instances into a child that died between two requests
  without counting it in `restarts` (it counts only a request that failed). E2 does not rely on `restarts` for that
  case: it reads each instance's `stats.calls` (league/tests/test_elane_e2_e1.py kills a real child mid-check).
- Checked on a tree of E1's 4baf7c10 plus the nine diffs plus this branch's files: test_elane_e2_* (with
  test_elane_e2_e1: A15 on E1's real runner, ctx builder and decider), test_researcher, test_dlane*, test_ci,
  test_elane, test_elane_gate, test_equity_e2e, test_swarm_loop, test_loop_joints, test_ops_stall and
  test_swarm_settings_policy pass.

## Patch 5 in words

`elane_train.may_validate(store, fam, n)` is True for a family E2 did not bear (the seeds are E1's alone). For an E2
family it is True only when `n` is the family's pass (the first version that passed equity-v1 AND the equity review),
the review record E1's look reads (`state["review"]`, the gate's shape) is in its state for that exact program, and the
pass was judged under the equity identity in force (or its version has had its Validation try). E1's `next_try` keeps
its own due, stale and retry logic: a Validation that went stale (the look found the recorded run did not reproduce,
e.g. after a daily refetch) is validated again, because `n` is still the pass. league/tests/test_elane_e2_e1.py runs E1's
real `Tournament.equity_round` on E2 families and fails without this patch.

## 1. league/swarm/loop.py

```diff
diff --git c/league/swarm/loop.py w/league/swarm/loop.py
index a7985a74..cf3a8e91 100644
--- c/league/swarm/loop.py
+++ w/league/swarm/loop.py
@@ -68,6 +68,7 @@ from . import elane, game
 from . import HEARTBEAT, LOCK_FILE, LOG_FILE, PID_FILE, settings as settings_mod
 from .architect import AGENDA_KEY, Architect, GraveyardDigest, allowed_structures
 from .diagnostician import Diagnostician
+from .elane_train import EquityResearcher
 from .funding import FundingWatch
 from .gate import Gate
 from .guard import SailGuard, provider_reader
@@ -509,6 +510,9 @@ class Swarm:
         # two Claude calls send the same bytes, so the second reads the first's cache entry.
         self.digest = GraveyardDigest(self.store, self.settings, clock=clock)
         self.architect = Architect(self.store, self.router, self.settings, clock=clock, digest=self.digest)
+        # THE EQUITY TRAIN (release E2; league/swarm/elane_train.py): the equity researcher and the equity review, on E1's
+        # isolated runner (`elane.isolated_runner`, built on its first Train run).
+        self.elane_train = EquityResearcher(self.store, self.router, self.settings, root=self.root, clock=clock)
         self.strategist = Strategist(self.store, self.router, self.settings, digest=self.digest, clock=clock,
                                      architect=self.architect)
         self.diagnostician = Diagnostician(self.store, self.router, self.settings, pool=self.pool, researcher=self.researcher,
@@ -1008,6 +1012,13 @@ class Swarm:
                 born = self.reseed()
                 if born:
                     log(f"reseeded {len(born)}: {', '.join(born)}")
+            # THE EQUITY LANES' BIRTHS AND TRAIN (release E2; league/swarm/elane_births.py, elane_train.py): their own
+            # rounds, never inside the options architect's pass (its ceiling and its closed cells stop neither). Each is
+            # off unless `elane.mode` is "gate" (births also need `elane.birth_share` above zero).
+            if research and self.architect.equity_due():
+                self._round("elane", self.architect.equity_pass)
+            if research and self.elane_train.due():
+                self._round("elane_train", self.elane_train.run)
             if research and self.diagnostician.due():  # Claude's own funded line and daily budget, not the researchers' pace
                 self._round("diagnostician", self.diagnostician.run)
             if not self.over_pace():
```

## 3. league/swarm/allocation.py

```diff
diff --git c/league/swarm/allocation.py w/league/swarm/allocation.py
index 4515f449..96f21a17 100644
--- c/league/swarm/allocation.py
+++ w/league/swarm/allocation.py
@@ -853,7 +853,10 @@ class BirthQuota:
         from .store import iso, loads
 
         for row in store._all("SELECT payload FROM events WHERE kind='swarm.born' AND at>=?", (iso(now - self.window_hours * 3600.0),)):
-            b = bucket_of((loads(row["payload"], {}) or {}).get("structure"))
+            payload = loads(row["payload"], {}) or {}
+            if isinstance(payload, Mapping) and payload.get("lane") in ("beta", "equity"):
+                continue  # THE EQUITY LANES (release E2): their own quota (league/swarm/elane_births.py `EquityQuota`)
+            b = bucket_of(payload.get("structure") if isinstance(payload, Mapping) else None)
             self.window[b] = self.window.get(b, 0) + 1
         self.passed: dict[str, int] = {}
         self.refused: dict[str, int] = {}
```

## 4. league/swarm/game.py

```diff
diff --git c/league/swarm/game.py w/league/swarm/game.py
index e8bddf54..b5f54d2a 100644
--- c/league/swarm/game.py
+++ w/league/swarm/game.py
@@ -1459,14 +1459,21 @@ def visible_graveyard(store: Any, query: str = "", limit: int = 8, *, settings:
     kinds of row, ranked over the rows that are left: a family born before T0 and retired since `SWITCH_AT` (it learned
     on the hidden years), and a game-arm family (its reasons and notes tell its SELECT outcomes). A store that never had a
     T0: exactly the store's read."""
+    from . import elane_seal
+
+    # THE SEAL OF THE EQUITY LANES (release E2, A9 D3; league/swarm/elane_seal.py): no reader here (the researchers' tool,
+    # the architect, the strategist, the diagnostician) reads an equity-lane row; with none, the read as before.
+    sealed = elane_seal.equity_ids(store)
     start, played = _hidden(store, settings)
     if start is None:
-        return store.graveyard(query, limit=limit)
+        if not sealed:
+            return store.graveyard(query, limit=limit)
+        return [r for r in store.graveyard(query, limit=limit + len(sealed)) if r["family"] not in sealed][:limit]
     from .store import rank_graveyard
 
     rows = store._all("SELECT g.*, f.born_at AS _born, f.retired_at AS _retired, f.id AS _id FROM graveyard g "
                       "LEFT JOIN families f ON f.id=g.family ORDER BY g.at DESC, g.family")
-    kept = [r for r in rows if not _quarantined(r, start, played)]
+    kept = [r for r in rows if not _quarantined(r, start, played) and r["family"] not in sealed]
     out = []
     for r in rank_graveyard(kept, query)[:limit]:
         r["roots"] = _loads(r["roots"], [])
```

## 5. league/swarm/tournament.py

```diff
diff --git c/league/swarm/tournament.py w/league/swarm/tournament.py
index 8ca8ad18..a77f2403 100644
--- c/league/swarm/tournament.py
+++ w/league/swarm/tournament.py
@@ -169,7 +169,7 @@ import random
 import time
 from typing import Any, Callable, Mapping
 
-from . import diagnostics, dlane, elane, evidence, game, incubator, practice
+from . import diagnostics, dlane, elane, elane_train, evidence, game, incubator, practice
 from .architect import allowed_structures
 from .pool import GymJob, PoolError
 from .researcher import (IDLE_CAUSE, MAX_ROOTS, VALIDATED_CYCLES_KEY, awaiting_validation, dormant_count, dormant_limit,
@@ -1336,6 +1336,11 @@ class Tournament:
                         out["retired"].append(fid)
                     continue
                 n = elane.next_try(self.store, fam, self.settings)
+                if not elane_train.may_validate(self.store, fam, n):
+                    # RELEASE E2 (league/swarm/elane_train.py): a family the equity pass bore takes its lineage's one try
+                    # only with its pass (the first version that passed equity-v1 AND the equity review, under the equity
+                    # identity in force); `next_try` keeps its due, stale and retry logic.
+                    continue
                 version = self.store.version(fid, n) if n is not None else None
                 if version is None or not version.get("code"):
                     continue
```

## 6. league/swarm/policy.json

`settings.DEFAULTS["elane"]` stays E1's: `policy_shape` checks only keys the defaults hold, so the nested `e2` object is
accepted, and the settings' deep merge lets swarm.json override any one key of it. `elane.birth_share` stays E1's 0.0:
THE SWITCH for E2's births is the captain's (swarm.json `elane.birth_share`, with `elane.mode` "gate").

```diff
diff --git c/league/swarm/policy.json w/league/swarm/policy.json
index 705b9095..e4884825 100644
--- c/league/swarm/policy.json
+++ w/league/swarm/policy.json
@@ -175,7 +175,36 @@
     },
     "val_tries": 1,
     "looks_per_lineage": 1,
-    "program_loss_usd": -300
+    "program_loss_usd": -300,
+    "e2": {
+      "births_every_seconds": 7200,
+      "births_refill_seconds": 1800,
+      "start": 8,
+      "max_alive": 24,
+      "min_per_pass": 1,
+      "max_per_pass": 6,
+      "window_hours": 24,
+      "births_max_output_tokens": 24000,
+      "births_effort": "medium",
+      "families_shown": 30,
+      "train_budget": 4,
+      "train_max_attempts": 7,
+      "train_max_errors": 3,
+      "train_every_seconds": 600,
+      "train_per_round": 3,
+      "train_max_output_tokens": 12000,
+      "train_effort": "medium",
+      "refuted_cell_cap": 3,
+      "review_routes": ["sail:pro_balanced", "sail:k3_balanced", "sail:glm_balanced"],
+      "review_max_output_tokens": 6000,
+      "review_effort": "medium",
+      "review_max_unclear": 3,
+      "routes": ["sail:pro_asap", "sail:glm_asap", "sail:k3"],
+      "min_births": 10,
+      "sample_requests": 30,
+      "explore_every": 3,
+      "usd_day": 8.0
+    }
   },
   "engineer": {
     "enabled": true
```

## 7. league/ci.py and league/tests/test_ci.py

```diff
diff --git c/league/ci.py w/league/ci.py
index ef28c663..679ce905 100644
--- c/league/ci.py
+++ w/league/ci.py
@@ -162,7 +162,15 @@ FORBIDDEN: tuple[str, ...] = (
 #: MERGE_FORBIDDEN, which gateway/test/merge.test.mjs holds to that list as written) cannot change in E1: gateway/ ships
 #: separately. A gateway follow-up adds both to MERGE_FORBIDDEN and moves them into the list above, leaving this empty;
 #: until then league/tests/test_ci.py allows exactly these in `FORBIDDEN` beyond the gateway's list.
-PENDING_GATEWAY: tuple[str, ...] = ("league/equity/", "league/swarm/elane.py")
+PENDING_GATEWAY: tuple[str, ...] = ("league/equity/", "league/swarm/elane.py",
+                                    # THE EQUITY LANES' BIRTHS, TRAIN AND REVIEW (release E2): the Train bar equity-v1 and
+                                    # the Train map (elane_train.py), the equity quota and admission (elane_births.py), the
+                                    # route choice by yield per dollar (elane_yield.py), the seal of Validation and look
+                                    # outcomes (elane_seal.py, A9 D3) and the equity review and level rule
+                                    # (elane_review.py): selection constants and secrecy rules, like dlane.py.
+                                    "league/swarm/elane_births.py", "league/swarm/elane_train.py",
+                                    "league/swarm/elane_yield.py", "league/swarm/elane_seal.py",
+                                    "league/swarm/elane_review.py")
 FORBIDDEN += PENDING_GATEWAY
 #: The one path the gateway's merge route refuses (`gateway/lib/protected.mjs` MERGE_FORBIDDEN) that is not FORBIDDEN:
 #: the House's configuration. The operator role proposes its dials (`CONFIG_DIALS`), and the updater ships a change to
diff --git c/league/tests/test_ci.py w/league/tests/test_ci.py
index b5a9db34..0ba85dcf 100644
--- c/league/tests/test_ci.py
+++ w/league/tests/test_ci.py
@@ -279,11 +279,14 @@ class TheEquityLane(unittest.TestCase):
         return ci.check_equity(self.root)
 
     def test_the_tree_and_the_swarm_lane_are_protected(self):
-        self.assertEqual(ci.PENDING_GATEWAY, ("league/equity/", "league/swarm/elane.py"))
+        self.assertEqual(ci.PENDING_GATEWAY, ("league/equity/", "league/swarm/elane.py", "league/swarm/elane_births.py",
+                                              "league/swarm/elane_train.py", "league/swarm/elane_yield.py",
+                                              "league/swarm/elane_seal.py", "league/swarm/elane_review.py"))
         for entry in ci.PENDING_GATEWAY:
             self.assertIn(entry, ci.FORBIDDEN)
         for path in ("league/equity/sizing.py", "league/equity/live.py", "league/equity/INTERFACES.md",
-                     "League/Equity/bands.py", "league/swarm/elane.py"):
+                     "League/Equity/bands.py", "league/swarm/elane.py", "league/swarm/elane_review.py",
+                     "league/swarm/elane_train.py"):
             self.assertTrue(ci.guard([path], None), path)
             for role in ci.ROLE_PATHS:
                 self.assertTrue(ci.guard([path], role), (path, role))
```

## 8. league/ops/dlane_report.py

```diff
diff --git c/league/ops/dlane_report.py w/league/ops/dlane_report.py
index 77b19b16..98064689 100644
--- c/league/ops/dlane_report.py
+++ w/league/ops/dlane_report.py
@@ -792,6 +792,18 @@ def equity_section(book: Mapping[str, Any], every: Sequence[Mapping[str, Any]],
     }
 
 
+def equity_yield(store: Any, settings: Mapping[str, Any] | None) -> dict[str, Any]:
+    """RELEASE E2: the equity lanes' model routes (league/swarm/elane_yield.py `report`): births, Train passes, Validation
+    entries, looks passed and live programs per route, each per dollar, and the equity review's own rows. The operator's
+    alone: never shown to an agent (A9 D3). An error is named, never raised."""
+    from ..swarm import elane_train, elane_yield
+
+    try:
+        return elane_yield.report(store, settings, train_key=elane_train.STATE_KEY)
+    except Exception as exc:  # noqa: BLE001 - the report goes on without it
+        return {"error": type(exc).__name__}
+
+
 def _order(close: Mapping[str, Any]) -> tuple:
     """Close order across both books: the close time, then an options close before an equity close, then its id."""
     pid = close["pid"]
@@ -2501,6 +2513,7 @@ def report(root: str | Path, *, settings: Mapping[str, Any] | None = None, now:
                                               lots=book.get("lots") or (), screens=screens),
             "equity": equity_section(book, every, eq_twins, count_from=count_from, unit=unit, seeded=seeded,
                                      screens=screens),
+            "equity_yield": equity_yield(store, settings),
             "direction_net": lane_net,
             "account": account(root, every, activity, previous, now=now),
             "costs": costs(store, since=start, lane_since=_epoch(started) if isinstance(started, str) else None),
```

## 9. league/swarm/store.py

```diff
diff --git c/league/swarm/store.py w/league/swarm/store.py
index 17399bab..52942313 100644
--- c/league/swarm/store.py
+++ w/league/swarm/store.py
@@ -683,7 +683,9 @@ class SwarmStore:
                         "reason": "the operator holds this family's validated version at the gate; it retires only once the "
                                   "hold is cleared"}
             if counts is None:
-                alive, counted = self._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL")["n"], True
+                # The options population's floor: the equity lanes' families are their own (release E2).
+                alive = self._one(f"SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL AND {OPTIONS_ONLY_SQL}")["n"]
+                counted = True
             else:
                 alive, counted = sum(1 for f in self.families(alive=True) if counts(f)), bool(counts(fam))
             if counted and int(alive) <= max(0, int(floor)):
```

## 10. league/ops/stall.py and league/ops/preopen.py

```diff
diff --git c/league/ops/stall.py w/league/ops/stall.py
index c19d2406..f2e95ba6 100644
--- c/league/ops/stall.py
+++ w/league/ops/stall.py
@@ -248,6 +248,12 @@ PAUSE_FILES = {"PAUSE": ("maintenance", "lift the maintenance pause once its wor
                "swarm.stop": ("swarm_stop", "remove state/swarm.stop once the swarm should run again (the House starts it then)")}
 CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "runway_sail", "runway_claude", "owner_deploy",
           "paused", "grant_refused", "kill_on", "dlane", "done", "preopen", "forward", "swarm_alerts", "underspend")
+#: THE EQUITY LANES (release E2): their births (a `swarm.born` whose payload's lane is "beta" or "equity"), their families
+#: (structure "etf" or "stock": league/swarm/store.py `OPTIONS_ONLY_SQL`) and their Train runs on the House are their own:
+#: none masks a stalled options architect, population or Gym here.
+OPTIONS_BIRTHS = "COALESCE(json_extract(payload, '$.lane'), '') NOT IN ('beta', 'equity')"
+OPTIONS_FAMILIES = "structure NOT IN ('etf', 'stock')"
+OPTIONS_RUNS = "family NOT IN (SELECT id FROM families WHERE structure IN ('etf', 'stock'))"
 #: The causes a pause stops by design: not raised while the floor is paused.
 RESEARCH_CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "underspend")
 #: The causes that are news to the owner, not a stall nor a step WAITING (Oct 10, 2026): a Done checkpoint that holds is
@@ -466,11 +472,14 @@ def swarm_facts(db: Any, now: float) -> dict[str, Any]:
     iso = lambda hours: S.iso(now - hours * 3600)  # noqa: E731
     one = lambda sql, params=(): (guard.ids(db, sql, params) or [None])[0]  # noqa: E731
     marks = ",".join("?" * len(F.NOT_RUN))
-    #: A Gym evaluation: a row with a trial the Gym neither refused nor failed (an F1 verdict's rows carry no trial).
-    evaluated = f"status NOT IN ({marks}) AND trials > 0"
+    #: A Gym evaluation: a row with a trial the Gym neither refused nor failed (an F1 verdict's rows carry no trial). RELEASE
+    #: E2: the equity lanes' runs (their Train runs on the House) are no Gym evaluation; their Validations still count.
+    evaluated_all = f"status NOT IN ({marks}) AND trials > 0"
+    evaluated = f"{evaluated_all} AND {OPTIONS_RUNS}"
     out: dict[str, Any] = {}
-    out["births"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=?", (iso(BIRTH_HOURS),)) or 0)
-    out["last_birth_at"] = one("SELECT max(at) FROM events WHERE kind='swarm.born'")
+    out["births"] = int(one(f"SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=? AND {OPTIONS_BIRTHS}",
+                            (iso(BIRTH_HOURS),)) or 0)
+    out["last_birth_at"] = one(f"SELECT max(at) FROM events WHERE kind='swarm.born' AND {OPTIONS_BIRTHS}")
     # THE LEARNING GAME's children (league/swarm/game.py `ORIGIN`) are births too, though they emit no `swarm.born`.
     children = int(one("SELECT count(*) FROM families WHERE origin=? AND born_at>=?", (GAME_ORIGIN, iso(BIRTH_HOURS))) or 0)
     if children:
@@ -478,7 +487,7 @@ def swarm_facts(db: Any, now: float) -> dict[str, Any]:
     last_child = one("SELECT max(born_at) FROM families WHERE origin=?", (GAME_ORIGIN,))
     if last_child and (out["last_birth_at"] is None or str(last_child) > str(out["last_birth_at"])):
         out["last_birth_at"] = last_child
-    out["alive"] = int(one("SELECT count(*) FROM families WHERE retired_at IS NULL") or 0)
+    out["alive"] = int(one(f"SELECT count(*) FROM families WHERE retired_at IS NULL AND {OPTIONS_FAMILIES}") or 0)
     passes = {"passes": 0, "no_cell": 0, "ceiling": 0, "failed": 0, "asked": 0, "proposed": 0, "born": 0}
     for text in guard.ids(db, "SELECT payload FROM events WHERE kind='swarm.architect' AND at>=? ORDER BY seq",
                           (iso(BIRTH_HOURS),)):
@@ -499,15 +508,15 @@ def swarm_facts(db: Any, now: float) -> dict[str, Any]:
             passes["proposed"] += int(_finite(row.get("proposed")) or 0)
         passes["born"] += len(row.get("born") or []) if isinstance(row.get("born"), list) else 0
     out["architect"] = passes
-    runs = guard.rows(db, "SELECT status, trials > 0 AS trial, count(*) AS n FROM runs WHERE at>=? GROUP BY status, trials > 0",
-                      (iso(GYM_HOURS),))
+    runs = guard.rows(db, f"SELECT status, trials > 0 AS trial, count(*) AS n FROM runs WHERE at>=? AND {OPTIONS_RUNS} "
+                          "GROUP BY status, trials > 0", (iso(GYM_HOURS),))
     out["gym_runs"] = sum(int(r["n"] or 0) for r in runs if r["status"] not in F.NOT_RUN and r["trial"])
     out["gym_not_run"] = sum(int(r["n"] or 0) for r in runs if r["status"] in F.NOT_RUN)
     out["gym_no_trial"] = sum(int(r["n"] or 0) for r in runs if r["status"] not in F.NOT_RUN and not r["trial"])
     out["last_gym_run_at"] = one(f"SELECT max(at) FROM runs WHERE {evaluated}", F.NOT_RUN)
     out["cycles"] = int(one("SELECT count(*) FROM events WHERE kind='swarm.cycle' AND at>=?", (iso(GYM_HOURS),)) or 0)
     since_v = iso(VALIDATION_HOURS)
-    out["validation_runs"] = int(one(f"SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=? AND {evaluated}",
+    out["validation_runs"] = int(one(f"SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=? AND {evaluated_all}",
                                      (since_v, *F.NOT_RUN)) or 0)
     out["validation_inherited"] = int(one(f"SELECT count(*) FROM runs WHERE \"window\"='validation' AND at>=? AND status NOT IN "
                                           f"({marks}) AND trials = 0", (since_v, *F.NOT_RUN)) or 0)
@@ -594,7 +603,7 @@ def _yield_facts(db: Any, now: float) -> dict[str, Any]:
         if isinstance(payload, Mapping):
             passes.append((S.epoch(row["at"]), payload))
     since = S.iso(now - DRY_HOURS * 3600)
-    born = guard.ids(db, "SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=?", (since,))
+    born = guard.ids(db, f"SELECT count(*) FROM events WHERE kind='swarm.born' AND at>=? AND {OPTIONS_BIRTHS}", (since,))
     children = guard.ids(db, "SELECT count(*) FROM families WHERE origin=? AND born_at>=?", (GAME_ORIGIN, since))
     return {"yield": {"jam": architect_tally(passes, now - JAM_HOURS * 3600),
                       "low": architect_tally(passes, now - YIELD_HOURS * 3600),
diff --git c/league/ops/preopen.py w/league/ops/preopen.py
index d6b054e8..67e3b833 100644
--- c/league/ops/preopen.py
+++ w/league/ops/preopen.py
@@ -208,7 +208,9 @@ def collect(root: Path, base: Path, release: Path, gateway: Any, *, now: float,
         # heartbeat, or the guard's check inside it, written in between is stamped after `now`.
         read_at = float(clock()) if clock is not None else now
         st = hb.get("status") or {}
-        alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT count(*) FROM families WHERE retired_at IS NULL"))[0]
+        # The options population against its floor: the equity lanes' families are their own (release E2).
+        alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT count(*) FROM families WHERE retired_at IS "
+                                                                           "NULL AND structure NOT IN ('etf', 'stock')"))[0]
         return {"raw_is_object": isinstance(raw, dict), "raw_live": raw.get("live") if isinstance(raw, dict) else None,
                 "defaults_live": dict(SS.DEFAULTS["live"]),
                 "eff_gym": {k: (eff.get("gym") or {}).get(k) for k in ("enabled", "image_checkpoint", "gate_checkpoint")},
```

## What E2 reads of E1 (built by E1; no patch)

- `SwarmStore.add_family` accepts "etf" and "stock" for a spec whose `lane` is "beta" or "equity"; `families(alive=,
  lanes=)` with INTERFACES 2.5's semantics (E2 falls back to the spec's lane on a store without the keyword).
- `elane.on`, `elane.cfg`, `elane.LABELS`, `elane.BETA_NOTE`, `elane.SEEDS_KEY`, `elane.INPUTS`, `elane.CLASSES`,
  `elane.isolated_runner(root)` (`league.equity.runner.Isolated.train`: `RunFailed`, `ProgramRefused`, the store's
  `MissingData`), `elane.reviewed` (the record E2 writes), `elane.next_try` (patch 5 runs after it).
- `cards.validate` for equity cards (`elane.card_errors`) and `cards.RebirthIndex` with its lane-scoped equity rows.
- `evaluator.equity_identity` (each E2 verdict's stamp) and `evaluator.adopt_equity` (which clears `best_version` and
  `review`: E2's round restores both for a pass that stands).
- The isolated runner is shared by E1's tournament and E2's Train round: E1 hooks' `decider.kind` holds `self.lock`.
- A15, the Train spans: `Isolated.train(code, params, name=, start=, end=, k=)` cut to each span, each run starting flat
  (a fresh runner and sleeve a call), its result's `by_year`, `daily`, `trades`, `lots`, `entry_days`, `actions`,
  `start` and `end` (every dated row is held to the span), `summary` (trades, days, days_traded, pnl, fees, dividends,
  mean_pnl_daily, t_daily, win_rate, exposure_mean, max_drawdown, mean_net_return), `bh.pnl` and `mte` (summed by
  `elane_train.combine`).
- A15, the restart check: `Isolated.decider` (the swarm's own child, never the live book's) with `kind_load("equity",
  key, {code, params, name, timeout, max_errors})`, `kind("equity", "decide", {jobs: [{key, inputs}]})`,
  `kind_drop`, `restarts`; the decide answer's per-key `intents`, `stats.calls` and `stats.disqualified`
  (`EquityRunner.stats`), `missing` and `error`; `Run.bars` (`n`, `first`, `days`, `raw`) and the result's `needs`,
  `params`, `capital`, `lots`, `trades` and `daily`; `ctx.inputs_from_bars`, `ctx.lot_row`, `ctx.closed_row`,
  `program.parse_needs`, `store.from_ordinal`, `config.POSITION_SHARE`, `class_of`, `SLEEVE_USD`. E2's instances are
  keyed "e2-state:<family>:<span>:<a|bN>" and dropped when the check ends, whatever ends it.
