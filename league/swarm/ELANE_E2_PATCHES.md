# Release E2: the patches E2 needs in files it does not own

Branch `feat/equity-e2` (from the skeleton df86ed45). E2 creates `league/swarm/elane_births.py`, `elane_train.py`,
`elane_yield.py`, `elane_seal.py` and their tests, and adds small branches to `league/swarm/architect.py` and
`league/swarm/researcher.py`. Everything else it needs is below, for the integrator, in merge order after E1. Patches
1-4 are exact unified diffs against df86ed45: each was applied to a copy of this branch, and the affected test modules
passed (test_swarm_allocation, test_dlane_births, test_dlane, test_game, test_swarm_rounds, test_swarm_diagnostician
and E2's own). Patch 7's FORBIDDEN hunk is exact against df86ed45 and must land WITH its PENDING_GATEWAY hunk (E1's
tuple): alone, test_ci's one-list test fails, as it should. Patches 5, 6 and 8 are written against the code E1's
packages are writing now (INTERFACES.md fixes their names), so they name the exact lines to add and where.

| # | file | owner | what | without it |
|---|---|---|---|---|
| 1 | `league/swarm/loop.py` | swarm (E1) | the two rounds: `elane` (`Architect.equity_pass`) and `elane_train` (`EquityResearcher.run`) | E2 never runs |
| 2 | `league/swarm/dlane.py` | swarm (E1, lane scoping A8.12) | `_born` skips equity births | an equity birth counts as an ALPHA birth in the direction quota's window |
| 3 | `league/swarm/allocation.py` | unowned (integrator) | `BirthQuota` skips equity births | equity births dilute the options structure families' window shares |
| 4 | `league/swarm/game.py` | unowned (integrator; protected) | `visible_graveyard` drops equity rows | the diagnostician can read an equity row whose lesson tells a Validation or look outcome (A9 D3) |
| 5 | `league/swarm/tournament.py` | swarm (E1) | an E2 family is validated only at `elane_train.awaiting_validation` | an E2 family could spend its lineage's one try on a version that never passed Train |
| 6 | `league/swarm/policy.json` | swarm (E1) | the `elane.e2` block (E2's settings, every value its code default) | the code defaults apply (the same values) |
| 7 | `league/ci.py` | money (E1) | the four E2 modules protected (FORBIDDEN and PENDING_GATEWAY) | E2's bar, quota, route rule and seal are editable by a merge route |
| 8 | `league/ops/dlane_report.py` | ops (E1) | the operator's yield-per-dollar record (`elane_yield.report`) | the record exists in the store but no report prints it |

Requirements on E1 (no patch: E1 builds them by INTERFACES, E2 depends on them):
- `SwarmStore.add_family` accepts the structures "etf" and "stock" for a spec whose `lane` is "beta" or "equity" (E1's
  seeds need it too); E2's tests stand in for it by patching `store.STRUCTURES`.
- `SwarmStore.families(*, alive=None, lanes=None)` with INTERFACES 2.5's semantics (E2 falls back to filtering by the
  spec's lane when the keyword is missing; its tests patch the method with the contract's semantics).
- `elane.on`, `elane.cfg` (with `universe`, `structures`, `birth_share`), `elane.LABELS`, `elane.BETA_NOTE`,
  `elane.SEEDS_KEY`, `elane.isolated_runner(root)` returning `league.equity.runner.Isolated` whose `train(code, params,
  *, name, start, end, k)` returns a `Run` (or raises `RunFailed`, or a `CodeRefused` / `NeedsRefused` / `*Refused` for a
  program the child will not load). An `elane.cfg` or `elane.on` that raises reads as OFF in E2 (fail closed).
- `cards.validate(card, structure, roots=symbols, settings=...)` admits an equity card (its `lane`, `structure`,
  `symbols`) through `elane.card_errors`; E2 always passes those three inside the card.
- `isolated_runner` is shared by E1's tournament thread and E2's `elane_train` round: `Isolated` (or its decider) must
  serialize calls, or `elane.isolated_runner` must hand each caller its own child.

## 1. league/swarm/loop.py: the rounds

```diff
--- a/league/swarm/loop.py
+++ b/league/swarm/loop.py
@@ -61,6 +61,7 @@
 from . import game
 from . import HEARTBEAT, LOCK_FILE, LOG_FILE, PID_FILE, settings as settings_mod
 from .architect import AGENDA_KEY, Architect, GraveyardDigest, allowed_structures
+from .elane_train import EquityResearcher
 from .diagnostician import Diagnostician
 from .funding import FundingWatch
 from .gate import Gate
@@ -503,6 +504,9 @@
         # two Claude calls send the same bytes, so the second reads the first's cache entry.
         self.digest = GraveyardDigest(self.store, self.settings, clock=clock)
         self.architect = Architect(self.store, self.router, self.settings, clock=clock, digest=self.digest)
+        # THE EQUITY TRAIN (release E2; league/swarm/elane_train.py): the equity researcher on E1's isolated runner
+        # (`elane.isolated_runner`, built on its first Train run).
+        self.elane_train = EquityResearcher(self.store, self.router, self.settings, root=self.root, clock=clock)
         self.strategist = Strategist(self.store, self.router, self.settings, digest=self.digest, clock=clock,
                                      architect=self.architect)
         self.diagnostician = Diagnostician(self.store, self.router, self.settings, pool=self.pool, researcher=self.researcher,
@@ -1001,6 +1005,13 @@
                 born = self.reseed()
                 if born:
                     log(f"reseeded {len(born)}: {', '.join(born)}")
+            # THE EQUITY LANES' BIRTHS AND TRAIN (release E2; league/swarm/elane_births.py, elane_train.py): their own
+            # rounds, never inside the options architect's pass (its ceiling and its closed cells stop neither). Each
+            # is off unless `elane.mode` is "gate" (births also need `elane.birth_share` above zero).
+            if research and self.architect.equity_due():
+                self._round("elane", self.architect.equity_pass)
+            if research and self.elane_train.due():
+                self._round("elane_train", self.elane_train.run)
             if research and self.diagnostician.due():  # Claude's own funded line and daily budget, not the researchers' pace
                 self._round("diagnostician", self.diagnostician.run)
             if not self.over_pace():
```

## 2. league/swarm/dlane.py: an equity birth is no options birth

```diff
--- a/league/swarm/dlane.py
+++ b/league/swarm/dlane.py
@@ -2242,6 +2242,8 @@
     for row in store._all(sql + " ORDER BY at, seq", tuple(args)):
         payload = loads(row.get("payload"), {}) or {}
         lane = payload.get("lane") if isinstance(payload, Mapping) else None
+        if lane in ("beta", "equity"):  # THE EQUITY LANES (league.equity.LANES): never an options lane's birth (A8.12)
+            continue
         out.append({"at": row.get("at"), "lane": lane if lane in LANES else ALPHA})
     return out
```

## 3. league/swarm/allocation.py: the structure families' window leaves the equity births out

```diff
--- a/league/swarm/allocation.py
+++ b/league/swarm/allocation.py
@@ -853,7 +853,10 @@
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

## 4. league/swarm/game.py: no reader of the graveyard sees an equity row (A9 D3)

E2 already guards the readers it may edit (league/swarm/architect.py: the digest's rows, `graves`, `unseen` (so the
rebirth index, the cited ids and the lane counts), `graveyard_ids`; league/swarm/researcher.py: the `graveyard` tool).
This one line covers the diagnostician (`diagnostician.py` reads `game.visible_graveyard`), and every other reader with
it. `elane_seal` imports only `league.equity` (its constants) and the standard library; game.py's import wall
(test_game) allows `from . import ...`.

```diff
--- a/league/swarm/game.py
+++ b/league/swarm/game.py
@@ -1442,14 +1442,21 @@
     kinds of row, ranked over the rows that are left: a family born before T0 and retired since `SWITCH_AT` (it learned
     on the hidden years), and a game-arm family (its reasons and notes tell its SELECT outcomes). A store that never had a
     T0: exactly the store's read."""
+    from . import elane_seal
+
+    # THE SEAL OF THE EQUITY LANES (release E2, A9 D3; league/swarm/elane_seal.py): no reader here (the researchers'
+    # tool, the architect, the strategist, the diagnostician) reads an equity-lane row; with none, the read as before.
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

## 5. league/swarm/tournament.py: an E2 family is validated only at its first Train pass

At E1's equity Validation dispatch (INTERFACES 8.3: "Validation dispatches by lane (equity -> `elane.validate`)"), before
the version is chosen and before `elane.try_open`:

```diff
+from . import elane_train
@@ (E1's equity dispatch, for each living equity family `fam`)
+            if elane_train.e2_family(fam):
+                # RELEASE E2: a family the equity pass bore meets Validation only with the first version that passed
+                # equity-v1 on Train (league/swarm/elane_train.py); with none, it is not validated (its Train research
+                # goes on, or E2 refutes it on Train).
+                n = elane_train.awaiting_validation(fam)
+                if n is None:
+                    continue
+                version = self.store.version(fam["id"], n)
+            else:
+                version = <E1's own choice for the seeds, unchanged>
             if not elane.try_open(self.store, fam, version["n"], self.settings):
                 continue
             elane.validate(self, fam, version)
```

`awaiting_validation` returns None once `fam["validated_version"]` is that version, and for a retired family. E2 sets
the family's `best_version` and `best_train` to the passing version too, so a dispatch that reads `best_version` finds
the same number; the guard above is what keeps a non-passing E2 family out.

## 6. league/swarm/policy.json: the `elane.e2` block

Against E1's `elane` block exactly as INTERFACES 8.1 writes it. Every value is its code default (league/swarm/
elane_births.py, elane_train.py, elane_yield.py `DEFAULTS`), so the patch changes no behaviour; it puts the dials where
the owner reviews them. `elane.birth_share` stays E1's 0.0: THE SWITCH for E2's births is the captain's (swarm.json
`elane.birth_share`, with `elane.mode` "gate").

```diff
--- a/league/swarm/policy.json
+++ b/league/swarm/policy.json
@@ "elane": { (INTERFACES 8.1)
   "val_tries": 1,
   "looks_per_lineage": 1,
-  "program_loss_usd": -300
+  "program_loss_usd": -300,
+  "e2": {
+    "births_every_seconds": 7200,
+    "births_refill_seconds": 1800,
+    "start": 8,
+    "max_alive": 24,
+    "min_per_pass": 1,
+    "max_per_pass": 6,
+    "window_hours": 24,
+    "births_max_output_tokens": 24000,
+    "births_effort": "medium",
+    "families_shown": 30,
+    "train_budget": 4,
+    "train_max_attempts": 7,
+    "train_max_errors": 3,
+    "train_every_seconds": 600,
+    "train_per_round": 3,
+    "train_max_output_tokens": 12000,
+    "train_effort": "medium",
+    "refuted_cell_cap": 3,
+    "routes": ["sail:pro_asap", "sail:glm_asap", "sail:k3"],
+    "min_births": 10,
+    "explore_every": 3,
+    "usd_day": 8.0
+  }
 }
```

`settings.DEFAULTS["elane"]` stays E1's `{"mode": "off"}`: `policy_shape` checks only keys the defaults hold, so the
nested `e2` object is accepted, and the settings' deep merge lets swarm.json override any one key of it.

## 7. league/ci.py: E2's modules are protected

Against df86ed45 (FORBIDDEN):

```diff
--- a/league/ci.py
+++ b/league/ci.py
@@ -150,6 +150,11 @@
     # TRAIN MAP (Oct 9, 2026; league/swarm/dlane_map.json): what the architect and the direction researchers are shown
     # of the operator's census, held to the lane's secrecy rules; an edit could steer births or leak a hidden figure.
     "league/swarm/dlane.py", "league/swarm/dlane_map.json",
+    # THE EQUITY LANES' BIRTHS AND TRAIN (release E2): the Train bar equity-v1 and the Train map (elane_train.py), the
+    # equity quota and admission (elane_births.py), the route choice by yield per dollar (elane_yield.py) and the seal
+    # of Validation and look outcomes (elane_seal.py, A9 D3): selection constants and a secrecy rule, like dlane.py.
+    "league/swarm/elane_births.py", "league/swarm/elane_train.py", "league/swarm/elane_yield.py",
+    "league/swarm/elane_seal.py",
     # How the House is deployed and the House itself (its tick calls the updater).
     "scripts/floor_box.py", "league/house.py", "CHANGELOG.md",
 )
```

and E1's `PENDING_GATEWAY` (INTERFACES 7.2) names them too, so test_ci's one-list test still holds until the gateway
follow-up adds them to `MERGE_FORBIDDEN`:

```diff
-PENDING_GATEWAY: tuple[str, ...] = ("league/equity/", "league/swarm/elane.py")
+PENDING_GATEWAY: tuple[str, ...] = ("league/equity/", "league/swarm/elane.py", "league/swarm/elane_births.py",
+                                    "league/swarm/elane_train.py", "league/swarm/elane_yield.py",
+                                    "league/swarm/elane_seal.py")
```

## 8. league/ops/dlane_report.py: the yield per dollar, for the operator only

Beside the equity rows E1's ops package adds to the report (INTERFACES section 10), one block from the swarm store:

```diff
+from league.swarm import elane_train, elane_yield
@@ (E1's equity section of the report, with `store` the swarm store and `settings` the swarm settings)
+    # RELEASE E2: births, Train passes, Validation entries, looks passed and live programs per model route, and each per
+    # dollar (league/swarm/elane_yield.py `report`). The operator's: never shown to an agent (A9 D3).
+    out["equity_yield"] = elane_yield.report(store, settings, train_key=elane_train.STATE_KEY)
```

The funnel (league/ops/funnel.py, E1's "births by lane") counts E2's births from their `swarm.born` events, whose
payload carries `lane` ("beta" or "equity"), `agenda` and `route`.
