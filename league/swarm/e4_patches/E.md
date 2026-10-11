# E4 patches authored by package E

Package E (xs screen) authors patch 3: `league/swarm/evaluator.py`.

Each patch below: its number in `README.md`, the file, the anchor (a statement, never a line number), the exact
unified diff against the integration head, and the test that holds it.

## Patch 3: `league/swarm/evaluator.py` (E1 core): the xs adoption

WHAT IT DOES. A panel family (structure "panel", lane "equity") binds to THE XS IDENTITY
(`league.xs.identity.xs_fingerprint`), never to the equity one. So:

- `adopt_equity` SKIPS a panel family (after package G's patch 1 the store's equity scope returns it, and its spec's
  lane is "equity": unpatched, an E1 evidence change would archive a panel family's state under the wrong identity
  and clear its `validation_r_sd_by_version`, and an xs evidence change would reset nothing);
- `adopt_xs(store, expected)` mirrors `adopt_equity` for panel families under the kv key `XS_KEY` ("xs_evaluator",
  re-exported from `league.xs.identity`): when the stored identity differs from `expected`
  (`league.xs.identity.xs_identity()`), every alive panel family's selection views are archived and cleared, a live
  panel band whose proof is not current (`league.xs.identity.xs_band_current`) goes back to "gym", its recorded
  Validation verdicts go stale (A16), and the family's `xs_evaluator` names the identity it is now judged under;
- `XS_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_xs_floor")` are what it clears beside `SELECTION_KEYS`,
  AND NOTHING ELSE OF THE PANEL'S. THE LINEAGE RECORDS ARE NEVER CLEARED: both Train series of every program that
  reached the pre-check (`elane_xs_train_x`, `elane_xs_train_u`), the pre-check's record (`elane_xs_precheck`), the
  template, the try and the look (`elane_try`, `elane_xs_look`). The pinned pre-registration's lineage rule reads
  them for every later panel program, looked at OR refused at the pre-check, and nothing can write them again;
- `is_panel_family(fam)`: the structure column is "panel" (`league.xs.STRUCTURE`).

It moves no identity: league/swarm/evaluator.py is in neither fingerprint, and the two new imports
(`league.xs.STRUCTURE`, `league.xs.identity`) are plumbing (a constant and the identity's own module; neither imports
anything of league.swarm, so there is no cycle). With every E4 switch off nothing here runs: `adopt_xs` is called by
package G's patch 9 (league/swarm/loop.py, beside `adopt_equity`), as

    from ..xs.identity import xs_identity
    from .evaluator import adopt_xs
    adopted = adopt_xs(self.store, xs_identity())      # a failure reads as None, as `adopt_equity`'s does

and with no panel family alive it writes the kv mark and touches no family.

ANCHORS (by statement; E1 was still moving when this was written):
1. the module's imports: after `from typing import Any, Mapping`;
2. after the statement `EQUITY_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_floor")`;
3. after the function `is_equity_family`;
4. in `adopt_equity`: its docstring's first paragraph, and the loop's first statement `if not is_equity_family(fam):`;
5. before the function `identity(image, bundle)` (that is, after `adopt_equity`'s `return`);
6. the module's `__all__`.

THE TESTS THAT HOLD IT: `league/tests/test_xs_identity.py`, already in the tree: `ThePatch` (always on: a swarm that
calls `adopt_xs`, or a store that admits the panel structure, needs this patch; this file carries the diff) and
`Adoption` (seven tests; they are SKIPPED until package G's patch 1 and this patch are both applied, and run from
then on: an xs change resets panel families only and keeps tries, looks and every sealed key but the floor; a current
proof keeps its band; `adopt_equity` and `adopt` never touch a panel family; A16's stale verdicts; a retired family
is left alone). Checked on Python 3.14 and 3.11 against this diff and a three-line stand-in for G's patch 1
(`EQUITY_STRUCTURES` and the two SQL scopes gaining "panel"). `league/tests/test_equity_identity.py` (E1's own
adoption tests) passes unchanged with the diff applied.

```diff
--- a/league/swarm/evaluator.py
+++ b/league/swarm/evaluator.py
@@ -13,6 +13,9 @@
 from pathlib import Path
 from typing import Any, Mapping
 
+from ..xs import STRUCTURE as XS_STRUCTURE
+from ..xs.identity import XS_KEY, xs_band_current
+
 KEY = "research_evaluator"
 SELECTION_KEYS = (
     "best_train_version", "best_train_run", "train_candidates", "submitted_run", "submitted_note",
@@ -90,6 +93,17 @@
 #: reads it for every later program of either equity lane, and nothing can write it again (the look is spent), so an
 #: adoption that cleared it would hand a re-coded copy of a program already looked at a second sealed look.
 EQUITY_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_floor")
+#: THE PANEL LANE (release E4; owner: package E). A panel family (structure "panel", lane "equity") binds to THE XS
+#: IDENTITY (`league.xs.identity.xs_fingerprint`; its store kv key is `XS_KEY`, re-exported here), never to the equity
+#: one: `adopt_equity` leaves it alone and `adopt_xs` is its adoption. A panel family's state keys an xs adoption
+#: archives and clears beside `SELECTION_KEYS`: the Validation runs' spread and the screen's floor, both run again
+#: before any look, AND NOTHING ELSE OF THE PANEL'S. Its tries and its look (`elane_try`, `elane_xs_look`) are never
+#: cleared: a lineage's spent try and look stay spent. Nor are THE LINEAGE RECORDS: both Train series of every
+#: program that reached the pre-check (`elane_xs_train_x`, `elane_xs_train_u`), the pre-check's own record
+#: (`elane_xs_precheck`) and the template. The pinned pre-registration's lineage rule reads them for every later panel
+#: program, looked at or refused, and nothing can write them again (the try and the look are spent), so an adoption
+#: that cleared one would hand a re-coded copy of a program already judged a second try or a second sealed look.
+XS_SELECTION_KEYS = ("validation_r_sd_by_version", "elane_xs_floor")
 
 
 def _equity_lanes() -> tuple[str, ...]:
@@ -104,6 +118,13 @@
     return isinstance(spec, Mapping) and str(spec.get("lane") or "") in _equity_lanes()
 
 
+def is_panel_family(fam: Mapping[str, Any] | None) -> bool:
+    """Whether a family row is a PANEL family (release E4): its structure is "panel" (`league.xs.STRUCTURE`; the store
+    admits it in the equity lane only). It is an equity-lane family (`is_equity_family`) that binds to the xs identity,
+    never to the equity one."""
+    return isinstance(fam, Mapping) and str(fam.get("structure") or "") == XS_STRUCTURE
+
+
 @lru_cache(maxsize=4)
 def equity_fingerprint(repo: Path | None = None) -> str:
     """THE EQUITY LANE's evidence identity (A8.8 as amended by A13; owner: core): sha256 over the EVIDENCE modules of
@@ -143,7 +164,8 @@
     """`adopt` mirrored for the equity lanes (owner: core): at process start, when the stored `EQUITY_KEY` differs from
     `expected`, every alive equity-lane family's selection views are archived and cleared and a live equity band goes
     back to "gym" for fresh qualification (its frozen lots keep their exits), in one transaction; options families are
-    never touched. {adopted, families, previous, current}.
+    never touched, NOR IS A PANEL FAMILY (release E4: it binds to the xs identity; `adopt_xs`). {adopted, families,
+    previous, current}.
 
     A missing identity cannot authorize adoption. Runs, trials, the lineage's tries and its look with its lineage record
     (`EQUITY_SELECTION_KEYS`: the Train series and the template D3 reads are kept), refusals, forward records and the
@@ -163,8 +185,8 @@
             rows = store.families(alive=True)
         count = 0
         for fam in rows:
-            if not is_equity_family(fam):
-                continue
+            if not is_equity_family(fam) or is_panel_family(fam):
+                continue  # a panel family binds to the xs identity (`adopt_xs`), never to this one
             state = fam.get("state") or {}
             if fam["band"] in LIVE_BANDS and not equity_band_current(state, expected):
                 # The House keeps the lots for their exits; the band must be earned again under the new engine.
@@ -200,6 +222,70 @@
     return {"adopted": True, "families": count, "previous": previous, "current": expected}
 
 
+def adopt_xs(store: Any, expected: Mapping[str, Any] | None) -> dict[str, Any]:
+    """`adopt_equity` mirrored for THE PANEL LANE (release E4; owner: package E): at process start, when the stored
+    `XS_KEY` differs from `expected` (`league.xs.identity.xs_identity()`: {"xs", "engine"}), every alive PANEL family's
+    selection views are archived and cleared and a live panel band goes back to "gym" for fresh qualification (its
+    frozen lots keep their exits), in one transaction. An ETF or stock family and an options family are never
+    touched: a change to an xs evidence module retires no share lineage. {adopted, families, previous, current}.
+
+    A missing identity cannot authorize adoption. Cleared: `SELECTION_KEYS` and `XS_SELECTION_KEYS`, and nothing else
+    of the panel's. Kept: runs, trials, the lineage's try and its look, THE LINEAGE RECORDS (both Train series, the
+    pre-check's record, the template: `XS_SELECTION_KEYS`' note), the Train record, refusals, forward records and the
+    band's history; the family's `xs_evaluator` names the identity it is now judged under. The store's kv `XS_KEY` is
+    this adoption's own mark and no band reads it: a live band's currency is read from the running release's files
+    (`bands.current_xs_evaluator`)."""
+    if expected is None:
+        return {"adopted": False, "families": 0, "reason": "xs identity unavailable"}
+    from .bands import LIVE_BANDS
+
+    expected = dict(expected)
+    with store.atomic():
+        previous = store.get(XS_KEY)
+        if previous == expected:
+            return {"adopted": False, "families": 0}
+        try:
+            rows = store.families(alive=True, lanes=_equity_lanes())
+        except TypeError:  # a store before the swarm's lane filter: every family, the panel ones picked here
+            rows = store.families(alive=True)
+        count = 0
+        for fam in rows:
+            if not is_panel_family(fam):
+                continue
+            state = fam.get("state") or {}
+            if fam["band"] in LIVE_BANDS and not xs_band_current(state, expected):
+                # The House keeps the lots for their exits; the band must be earned again under the new evidence.
+                store.set_band(fam["id"], "gym", reason="panel evidence semantics changed; fresh qualification is "
+                                                       "required")
+            keys = (*SELECTION_KEYS, *XS_SELECTION_KEYS)
+            archived = {key: state[key] for key in keys if key in state}
+            archived.update({key: fam.get(key) for key in ("best_train", "best_version", "best_validation",
+                                                           "validated_version")})
+            store.event("swarm.status", fam["id"], {"action": "xs_evaluator_adopted", "from": previous,
+                                                    "to": expected, "_previous_selection": archived})
+            store.update_family(fam["id"], best_train=None, best_version=None, best_validation=None,
+                                validated_version=None, stall=0, since_val_revisions=0, since_val_trials=0)
+            cleared: dict[str, Any] = {key: None for key in keys}
+            cleared.update(gate_ready=False, xs_evaluator=expected, previous_evaluator_selection=archived)
+            # A16, as `adopt_equity`: a version validated under the old evidence and not yet looked at is owed its
+            # Validation again (the same try: no look was spent), so its recorded verdicts go stale.
+            from .elane import VALIDATION_KEY, VERDICTS_KEY
+
+            verdicts = state.get(VERDICTS_KEY)
+            if isinstance(verdicts, Mapping) and verdicts:
+                cleared[VERDICTS_KEY] = {str(k): ({**dict(v), "stale": True} if isinstance(v, Mapping) else v)
+                                         for k, v in verdicts.items()}
+            if isinstance(state.get(VALIDATION_KEY), Mapping):
+                cleared[VALIDATION_KEY] = {**dict(state[VALIDATION_KEY]), "stale": True}
+            store.set_state(fam["id"], **cleared)
+            store.note(fam["id"], "The panel's evidence code changed. Historical runs, the lineage's Validation try and "
+                       "its sealed look remain counted, and so do both Train series the lineage rule reads. Validation "
+                       "evidence is owed under the current code; this does not grant another try or another look.")
+            count += 1
+        store.put(XS_KEY, expected)
+    return {"adopted": True, "families": count, "previous": previous, "current": expected}
+
+
 def identity(image: Any, bundle: Any) -> dict[str, str] | None:
     return {"image": str(image), "bundle": str(bundle), "execution": execution_fingerprint()} if image and bundle else None
 
@@ -321,4 +407,5 @@
 __all__ = ["KEY", "SELECTION_KEYS", "HOLD_KEYS", "identity", "matches", "row_matches", "gym_changed", "adopt",
            "execution_fingerprint", "EQUITY_KEY", "EQUITY_GYM_FILES", "EQUITY_EVIDENCE", "EQUITY_EVIDENCE_ROOTS",
            "EQUITY_EVIDENCE_EXTRA", "EQUITY_CALENDAR_FILES", "EQUITY_SELECTION_KEYS", "equity_fingerprint",
-           "equity_identity", "equity_band_current", "is_equity_family", "adopt_equity"]
+           "equity_identity", "equity_band_current", "is_equity_family", "adopt_equity",
+           "XS_KEY", "XS_STRUCTURE", "XS_SELECTION_KEYS", "is_panel_family", "adopt_xs"]
```

## What the integrator does for package E beside the patch (no diff: values copied by one call)

THE RECEIPT AND ITS PIN, in ONE commit (`league/xs/E4_INTERFACES.md`, the integrator's row): copy the study's
receipt VERBATIM to `docs/benchmarks/equity_screen_xs_1.json`, then fill policy.json `elane.screens.equity_xs` from
it by the one call that reads every pinned value from its `screen.PIN_SOURCES` place (no figure is typed):

    import json
    from pathlib import Path
    from league.xs import screen

    policy = Path("league/swarm/policy.json")
    doc = json.loads(policy.read_text())
    doc["elane"]["screens"]["equity_xs"] = screen.pin(screen.RECEIPT_PATH)      # PIN_KEYS, in order
    policy.write_text(json.dumps(doc, indent=2) + "\n")                         # as the file is written today
    assert screen.pinned_receipt(doc["elane"]["screens"]["equity_xs"]) is not None

`league/tests/test_xs_screen.py` `TheCommittedPin` then holds the committed block equal to `screen.pin` of the
file (sha, c_XS and every other value) and that the loader reads the file to the same receipt; until then it holds
that the tree has no receipt without its pin. A rebuilt receipt at another c_XS lands the same way: no line of
league/xs changes (the xs identity does not move), and a floor cached under the old figures is run again
(`screen.floor_fits`).
