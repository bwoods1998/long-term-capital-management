# E4 patches authored by package G

Package G (swarm) authors patches 1, 2, 4, 5, 6, 7, 8 and 9 of `README.md`'s table, the two test edits patch 9 needs,
and proposes one more (1b: two league/ops files no E4 package owns).

HOW THESE DIFFS WERE MADE AND CHECKED. Package G's own branch (`feat/equity-e4-g`) holds its owned files only. A second
branch, `feat/equity-e4-g-int` (worktree `~/Work/ltcm-v3/eqe4-g-int`), is that branch with every edit below APPLIED to
the existing files: each diff here is `git diff feat/equity-e4-g feat/equity-e4-g-int -- <file>`, so it applies
exactly on the step 0 files (base 24a52b11) and the whole of it is `git diff feat/equity-e4-g feat/equity-e4-g-int`.
On that branch the E1 and E2 suites pass unchanged but for the two test statements of "9 (tests)", and every test of
package G runs with none skipped (on package G's own branch the tests that hold a PATCHED file are skipped and say
which patch they hold: `league/tests/elane_xs_fakes.py` `PATCHED`). E1 and E2 were still receiving review fixes: the
ANCHORS of each patch are statements, named in words, and the diff's line numbers are the base's.

ORDER: 1 first (2, 4, 6 and 7 read `store.EQUITY_ONLY_SQL` or `store.EQUITY_STRUCTURES`); then any order. Every
patched file imports `elane_xs` INSIDE the function that forwards (no import cycle, and nothing of league.xs is
imported at a module's top). WITH `elane.panel.mode` "off" no patched statement changes what E1 or E2 does: no panel
family exists, `elane_xs.is_panel` is False for every family, the quota's panel share is 0 and the PANEL block is "".

WHAT PACKAGE G NEEDS OF THE OTHER PACKAGES' PATCHES: package E's patch 3 (`evaluator.adopt_xs`; `adopt_equity` skips
structure "panel": WITHOUT IT `adopt_equity`, at the first start after the EQUITY identity moves, would send a panel
Candidate back to the Gym and clear its selection, judging its proof against the wrong identity) and package H's
patch 12 (`kinds.kind_of`, the book's panel path).

## Patch 1: `league/swarm/store.py`

`store.EQUITY_STRUCTURES` gains "panel"; the scopes are built from the tuple; a panel family names no root.

ANCHORS: the three constants `EQUITY_STRUCTURES`, `EQUITY_LANES`, `OPTIONS_ONLY_SQL`; in `add_family` the statement
`if parent and lane_of_spec((self.family(parent) or {}).get("spec")) != lane:` and the statement `if not roots:`; in
`families` the statement `scope = " AND structure IN ('etf', 'stock')"`; `__all__`.
WHAT: `EQUITY_STRUCTURES = ("etf", "stock", "panel")`, `PANEL_STRUCTURE`, and TWO built scopes: `EQUITY_ONLY_SQL` (new)
and `OPTIONS_ONLY_SQL`, both made from the tuple, so no reader spells the structures out. `add_family` admits "panel"
only with lane "equity", and ONLY a panel family may name no root (the spec's `roots` []; a panel family that names a
root is refused: it trades salted slots, never a symbol). `families(lanes=...)` reads `EQUITY_ONLY_SQL`.
WHY THE ROOTS: at the base `add_family` refuses a family with no root; without this the spec's panel family cannot be
stored. Two panel families with identical code are joined into one lineage by the store's own `link_lineages` (same
structure, same roots): one Validation try and one look between them, which is the lineage rule's "same template".
HELD BY: `test_elane_xs.NoStructureLiteralOutsideTheStore` (the tuple, the two scopes, a panel family is an equity
family with no root, only in the equity lane, and no options reader sees it).
```diff
diff --git a/league/swarm/store.py b/league/swarm/store.py
index 52942313..1bc73235 100644
--- a/league/swarm/store.py
+++ b/league/swarm/store.py
@@ -248,10 +248,15 @@ CLOSEABLE = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly
 #: one of `EQUITY_STRUCTURES` (`add_family` holds the two together), so the options readers below tell the lanes apart
 #: by the structure column alone. `families(lanes=None)` (the default every options consumer calls) leaves equity
 #: families out; `lanes=EQUITY_LANES` returns them alone; `lanes="all"` everything (reports).
-EQUITY_STRUCTURES = ("etf", "stock")
+#: RELEASE E4: "panel" (a cross-sectional program on the point-in-time S&P 500; league/swarm/elane_xs.py), lane "equity"
+#: only, and the one structure whose family names no root (it sees salted slots, never a symbol).
+EQUITY_STRUCTURES = ("etf", "stock", "panel")
+PANEL_STRUCTURE = "panel"
 EQUITY_LANES = ("beta", "equity")
-#: The options readers' SQL guard: a families row that is no equity family.
-OPTIONS_ONLY_SQL = "structure NOT IN ('etf', 'stock')"
+#: The equity readers' SQL scope, and the options readers' guard (a families row that is no equity family): both built
+#: from `EQUITY_STRUCTURES`, so no reader spells the structures out (league/tests/test_elane_xs.py holds it).
+EQUITY_ONLY_SQL = "structure IN (" + ", ".join(f"'{name}'" for name in EQUITY_STRUCTURES) + ")"
+OPTIONS_ONLY_SQL = "structure NOT IN (" + ", ".join(f"'{name}'" for name in EQUITY_STRUCTURES) + ")"
 _SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
 
 
@@ -502,6 +507,8 @@ class SwarmStore:
             if spec.get("structure") not in EQUITY_STRUCTURES:
                 raise ValueError(f"an equity-lane family's structure is one of {', '.join(EQUITY_STRUCTURES)}, "
                                  f"not {spec.get('structure')!r}")
+            if spec.get("structure") == PANEL_STRUCTURE and lane != "equity":
+                raise ValueError(f"a panel family's lane is \"equity\" (release E4), not {spec.get('lane')!r}")
             if parent and lane_of_spec((self.family(parent) or {}).get("spec")) != lane:
                 raise ValueError("an equity-lane family forks only from a family of its own lane (A8.12)")
         elif spec.get("structure") not in STRUCTURES:
@@ -509,7 +516,10 @@ class SwarmStore:
         elif parent and equity_family(self.family(parent)):
             raise ValueError("an options family never forks from an equity-lane family (A8.12)")
         roots = [str(r).upper() for r in (spec.get("roots") or []) if str(r).strip()]
-        if not roots:
+        panel = lane is not None and spec.get("structure") == PANEL_STRUCTURE
+        if panel and roots:
+            raise ValueError("a panel family names no root (it trades salted slots of its panel, never a symbol)")
+        if not roots and not panel:
             raise ValueError("a family names at least one root")
         mechanism = " ".join(str(spec.get("mechanism") or "").split())
         if len(mechanism) < 20:
@@ -561,7 +571,7 @@ class SwarmStore:
             unknown = sorted(wanted - set(EQUITY_LANES))
             if unknown:
                 raise ValueError(f"lanes: {', '.join(unknown)} is no equity lane (None is the options lanes, 'all' every family)")
-            scope = " AND structure IN ('etf', 'stock')"
+            scope = f" AND {EQUITY_ONLY_SQL}"
         if alive is None:
             rows = self._all(f"SELECT * FROM families WHERE 1=1{scope} ORDER BY born_at, id")
         elif alive:
@@ -1295,4 +1305,5 @@ class SwarmStore:
 
 __all__ = ["SwarmStore", "ALIVE", "BANDS", "STRUCTURES", "LONG_SINGLE", "SINGLE_SIDES", "same_slice", "slice_priors",
            "priors_of", "structure_text", "structure_query", "CLOSEABLE", "slugify", "code_sha", "dumps", "loads", "iso",
-           "EQUITY_STRUCTURES", "EQUITY_LANES", "OPTIONS_ONLY_SQL", "lane_of_spec", "equity_family"]
+           "EQUITY_STRUCTURES", "PANEL_STRUCTURE", "EQUITY_LANES", "EQUITY_ONLY_SQL", "OPTIONS_ONLY_SQL", "lane_of_spec",
+           "equity_family"]
```

## Patch 1b (proposed; no E4 package owns these two files): `league/ops/stall.py`, `league/ops/preopen.py`

The ops' two copies of the options scope know the panel.

ANCHORS: `OPTIONS_FAMILIES` and `OPTIONS_RUNS` in stall.py; in preopen.py the statement that counts the options
population (`"NULL AND structure NOT IN ('etf', 'stock')"`).
WHAT: both spell the equity structures out to keep the options population, births and Gym runs apart from the equity
lanes'. With a panel family alive, unpatched, both would count it as an OPTIONS family (the stall monitor's population
and run counts; the pre-open's population against its floor). They are league/ops files and import nothing of
league.swarm at module level, so the literal is extended in place, not imported.
HELD BY: `test_elane_xs.NoStructureLiteralOutsideTheStore.test_the_ops_two_copies_of_the_scope_know_the_panel` (each
held equal to `store.OPTIONS_ONLY_SQL` / `EQUITY_ONLY_SQL`). THE INTEGRATOR'S CALL: apply it with patch 1, or hand it to
the files' owner; without it nothing trades wrongly, two ops counts are off by the panel families.
```diff
diff --git a/league/ops/preopen.py b/league/ops/preopen.py
index 67e3b833..467d94ac 100644
--- a/league/ops/preopen.py
+++ b/league/ops/preopen.py
@@ -208,9 +208,10 @@ def collect(root: Path, base: Path, release: Path, gateway: Any, *, now: float,
         # heartbeat, or the guard's check inside it, written in between is stamped after `now`.
         read_at = float(clock()) if clock is not None else now
         st = hb.get("status") or {}
-        # The options population against its floor: the equity lanes' families are their own (release E2).
+        # The options population against its floor: the equity lanes' families are their own (release E2; a panel
+        # family, release E4, among them: league/swarm/store.py `OPTIONS_ONLY_SQL`).
         alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT count(*) FROM families WHERE retired_at IS "
-                                                                           "NULL AND structure NOT IN ('etf', 'stock')"))[0]
+                                                                           "NULL AND structure NOT IN ('etf', 'stock', 'panel')"))[0]
         return {"raw_is_object": isinstance(raw, dict), "raw_live": raw.get("live") if isinstance(raw, dict) else None,
                 "defaults_live": dict(SS.DEFAULTS["live"]),
                 "eff_gym": {k: (eff.get("gym") or {}).get(k) for k in ("enabled", "image_checkpoint", "gate_checkpoint")},
diff --git a/league/ops/stall.py b/league/ops/stall.py
index f2e95ba6..ac6614e1 100644
--- a/league/ops/stall.py
+++ b/league/ops/stall.py
@@ -249,11 +249,12 @@ PAUSE_FILES = {"PAUSE": ("maintenance", "lift the maintenance pause once its wor
 CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "runway_sail", "runway_claude", "owner_deploy",
           "paused", "grant_refused", "kill_on", "dlane", "done", "preopen", "forward", "swarm_alerts", "underspend")
 #: THE EQUITY LANES (release E2): their births (a `swarm.born` whose payload's lane is "beta" or "equity"), their families
-#: (structure "etf" or "stock": league/swarm/store.py `OPTIONS_ONLY_SQL`) and their Train runs on the House are their own:
-#: none masks a stalled options architect, population or Gym here.
+#: (structure "etf", "stock" or, since release E4, "panel": league/swarm/store.py `OPTIONS_ONLY_SQL`, held equal by
+#: league/tests/test_elane_xs.py) and their Train runs on the House are their own: none masks a stalled options
+#: architect, population or Gym here.
 OPTIONS_BIRTHS = "COALESCE(json_extract(payload, '$.lane'), '') NOT IN ('beta', 'equity')"
-OPTIONS_FAMILIES = "structure NOT IN ('etf', 'stock')"
-OPTIONS_RUNS = "family NOT IN (SELECT id FROM families WHERE structure IN ('etf', 'stock'))"
+OPTIONS_FAMILIES = "structure NOT IN ('etf', 'stock', 'panel')"
+OPTIONS_RUNS = "family NOT IN (SELECT id FROM families WHERE structure IN ('etf', 'stock', 'panel'))"
 #: The causes a pause stops by design: not raised while the floor is paused.
 RESEARCH_CAUSES = ("births", "birth_yield", "gym_runs", "validations", "braked", "underspend")
 #: The causes that are news to the owner, not a stall nor a step WAITING (Oct 10, 2026): a Done checkpoint that holds is
```

## Patch 2: `league/swarm/bands.py`

The two SQL scopes read the store's; band currency from the running code; the seat rule by root.

ANCHORS: the import of `EQUITY_STRUCTURES, OPTIONS_ONLY_SQL` from `.store`; `_families` (its `where +=` statement);
`_banded` (its `scope =` statement); `equity_seating`; `roster` (its `seat =` statement); `current_equity_evaluator`
(the new functions go before it); `equity_proof_current`; in `_read_equity` the `try:` that opens the store, and the
statement `if not current_equity_evaluator(state, sha, equity_sha):`; the module docstring's EQUITY LANES paragraph.
WHAT: (a) both scopes read `store.EQUITY_ONLY_SQL`. (b) BAND CURRENCY FROM THE RUNNING CODE: `_xs_sha()` computes
`league.xs.identity.xs_fingerprint()` from the release's files (cached as `_equity_sha` is, never from the kv
`xs_evaluator`); `current_xs_evaluator(state, sha, xs_sha)` requires the proof's engine `XS_ENGINE_VERSION`, its
`xs_sha256` and its `run_sha`. `_read_equity` judges a row of structure "panel" by it, returns NO panel row when the
fingerprint cannot be computed, and with `strict` raises `EquityUnreadable` while a panel family is in a running band
(the book must tell "no row" from "could not read": it retires on the first). (c) `equity_proof_current` answers BY
THE PROOF'S ENGINE: a proof naming the panel engine is judged by the xs identity (None when it cannot be computed:
unknown, nothing retired). (d) `equity_seating(fams, seats, *, seatable=equity_seatable)`; `_read_equity` and `roster`
pass `elane_xs.seatable(root)` (a panel Candidate is seatable only while the effective mode is "live"; when that rule
cannot be built a panel Candidate is seatless). (e) a panel row's `beside` is XS1's sentence (`elane_xs_look`).
HELD BY: `test_elane_xs.TheBandIsCurrentOnlyUnderTheRunningCode` (X17: six tests), `test_elane_xs.TheSeatRule`.
```diff
diff --git a/league/swarm/bands.py b/league/swarm/bands.py
index 743f3caf..a7d3df1c 100644
--- a/league/swarm/bands.py
+++ b/league/swarm/bands.py
@@ -93,6 +93,15 @@ answers [] for a store it could not read (no store, a read that failed within it
 must tell "no equity row" from "could not read", because it retires an instance whose family is gone and a retirement
 sells its lots (A8.5; league/equity/live.py `_sync_instances`).
 
+THE PANEL (release E4; league/swarm/elane_xs.py). A family of structure "panel" is an equity-lane family (every scope
+here reads `store.EQUITY_STRUCTURES`), and its band proof binds to ITS OWN identity: `banded_evaluator` {"engine":
+`league.xs.XS_ENGINE_VERSION`, "xs_sha256": `league.xs.identity.xs_fingerprint()`, "run_sha"}, checked against the
+fingerprint of the RUNNING release's files (`_xs_sha`, `current_xs_evaluator`), never against the store's kv
+`xs_evaluator`. No panel row is returned when that fingerprint cannot be computed (`strict`: `EquityUnreadable` while
+a panel family is in a running band), and `equity_proof_current` judges a proof by the engine it names. A panel
+Candidate is seatable only while the panel lane's effective mode is "live" (`elane_xs.seatable(root)`, handed to
+`equity_seating`); its row's `beside` is XS1's sentence, stated beside every live panel trade.
+
 `read(root, family=f)` and `observe(root, family=f)` read one family only (the live path's per-minute admissions). The
 Gym bundle's version is built once per `BUNDLE_TTL` seconds a process, not once per call (it reads and hashes every file
 of the Gym's code).
@@ -121,7 +130,7 @@ from pathlib import Path
 from typing import Any, Mapping, Sequence
 
 from . import DB_NAME, settings
-from .store import EQUITY_LANES, EQUITY_STRUCTURES, OPTIONS_ONLY_SQL, lane_of_spec, loads
+from .store import EQUITY_LANES, EQUITY_ONLY_SQL, EQUITY_STRUCTURES, OPTIONS_ONLY_SQL, lane_of_spec, loads
 
 LIVE_BANDS = ("candidate", "probe", "sized")
 #: The gate's outcomes (`gate_outcome.result` naming the program) that end its execution tuition (`read`) and refuse it
@@ -179,7 +188,7 @@ def _families(db: sqlite3.Connection, family: str | None, *, gym_only: bool = Fa
     """The living families (the Gym band's alone with `gym_only`; one with `family`): the options lanes' by default, the
     equity lanes' alone with `equity` (THE EQUITY LANES: no options reader here ever sees an equity family)."""
     where = "retired_at IS NULL" + (" AND band='gym'" if gym_only else "") + (" AND id=?" if family is not None else "")
-    where += " AND structure IN ('etf', 'stock')" if equity else f" AND {OPTIONS_ONLY_SQL}"
+    where += f" AND {EQUITY_ONLY_SQL}" if equity else f" AND {OPTIONS_ONLY_SQL}"
     return [dict(r) for r in db.execute(f"SELECT id, band, band_since, structure, roots, state, lineage, best_version, "
                                         f"best_train, spec, born_at FROM families WHERE {where} ORDER BY id",
                                         (() if family is None else (str(family),)))]
@@ -285,9 +294,24 @@ def equity_seats(seats: int) -> int:
     return int(seats) if int(seats) > 0 else ROSTER_CLOSED
 
 
-def equity_seating(fams: Sequence[Mapping[str, Any]], seats: int) -> dict[str, list[str]]:
-    """THE EQUITY ROSTER's `seating` over the equity Candidate and Probe families (`seats`: `elane.roster_seats`)."""
-    return seating(fams, equity_seats(seats), seatable=equity_seatable)
+def equity_seating(fams: Sequence[Mapping[str, Any]], seats: int, *,
+                   seatable: Any = equity_seatable) -> dict[str, list[str]]:
+    """THE EQUITY ROSTER's `seating` over the equity Candidate and Probe families (`seats`: `elane.roster_seats`).
+    `seatable` (RELEASE E4): the seat rule by structure; the callers that hold the state root pass
+    `elane_xs.seatable(root)`, under which a PANEL Candidate is seatable only while the panel lane's effective mode is
+    "live" (otherwise it is seatless: no row, so no instance and no order)."""
+    return seating(fams, equity_seats(seats), seatable=seatable)
+
+
+def _equity_seatable(root: str | Path) -> Any:
+    """The equity roster's seat rule for a state root: `elane_xs.seatable(root)` (RELEASE E4), and E1's own rule less the
+    panel when that cannot be built (a panel Candidate is then seatless: fail closed)."""
+    try:
+        from . import elane_xs
+
+        return elane_xs.seatable(root)
+    except Exception:  # noqa: BLE001 - no panel rule: no panel seat
+        return lambda structure: equity_seatable(structure) and str(structure or "") != "panel"
 
 
 def roster(root: str | Path, *, lanes: Any = None) -> dict[str, Any] | None:
@@ -312,7 +336,7 @@ def roster(root: str | Path, *, lanes: Any = None) -> dict[str, Any] | None:
             db.close()
     except (sqlite3.Error, OSError):
         return None
-    seat = equity_seating(fams, seats) if equity else seating(fams, seats)
+    seat = equity_seating(fams, seats, seatable=_equity_seatable(root)) if equity else seating(fams, seats)
     return {"seats": max(seats, 0), "closed": seats == ROSTER_CLOSED, "probe": seat["probe"],
             "seated": sorted(seat["probe"] + seat["seated"]), "waiting": seat["waiting"], "seatless": seat["seatless"]}
 
@@ -355,7 +379,7 @@ def _banded(db: sqlite3.Connection, *, equity: bool = False) -> list[dict[str, A
     """The alive Candidate and Probe families, their state parsed (the roster's input): the options lanes' (THE PROBE
     ROSTER), or with `equity` the equity lanes' (THE EQUITY ROSTER), never both."""
     out = []
-    scope = "structure IN ('etf', 'stock')" if equity else OPTIONS_ONLY_SQL
+    scope = EQUITY_ONLY_SQL if equity else OPTIONS_ONLY_SQL
     for r in db.execute("SELECT id, band, band_since, structure, state FROM families WHERE retired_at IS NULL AND band IN "
                         f"('candidate', 'probe') AND {scope} ORDER BY id"):
         row = dict(r)
@@ -481,6 +505,44 @@ def _equity_sha() -> str | None:
     return value
 
 
+#: THE XS IDENTITY (release E4) as `read(lanes=...)` checks a PANEL band against it (`league.xs.identity
+#: .xs_fingerprint`, computed from the running release's own files), reused for `BUNDLE_TTL` seconds a process.
+_xs_cache: tuple[float, str] | None = None
+
+
+def _xs_sha() -> str | None:
+    """The current xs fingerprint, or None when it cannot be computed (no panel row is then current). FROM THE RUNNING
+    CODE, never from the store's kv `xs_evaluator` (written only when the swarm loop starts): with the loop stopped
+    after a release that changed an xs evidence module, a kv check would let the book go on opening positions under
+    code no look judged."""
+    global _xs_cache
+    now = time.monotonic()
+    with _bundle_lock:
+        cached = _xs_cache
+    if cached is not None and 0.0 <= now - cached[0] < BUNDLE_TTL:
+        return cached[1]
+    try:
+        from ..xs.identity import xs_fingerprint
+
+        value = str(xs_fingerprint())
+    except Exception:  # noqa: BLE001 - not cached: the next read tries again
+        return None
+    with _bundle_lock:
+        _xs_cache = (now, value)
+    return value
+
+
+def current_xs_evaluator(state: Mapping[str, Any], sha: str, xs_sha: str | None) -> bool:
+    """A PANEL band's proof (`banded_evaluator`, written by `elane_xs.look` when its one look passed and the style rule
+    let it be seated) names the panel engine, the xs identity of the running release and the exact program
+    (`run_sha`)."""
+    from ..xs import XS_ENGINE_VERSION
+
+    proof = state.get("banded_evaluator") if isinstance(state.get("banded_evaluator"), Mapping) else {}
+    return (xs_sha is not None and proof.get("engine") == XS_ENGINE_VERSION
+            and proof.get("xs_sha256") == xs_sha and proof.get("run_sha") == sha)
+
+
 def current_equity_evaluator(state: Mapping[str, Any], sha: str, equity_sha: str | None) -> bool:
     """An equity band's proof (`banded_evaluator`, written by `elane.look` when its one look passed) names the engine,
     the equity identity in force and the exact program (`run_sha`): an equity release that moves the identity sends the
@@ -496,13 +558,30 @@ def equity_proof_current(state: Mapping[str, Any], version: Mapping[str, Any]) -
     """Whether an equity family's band proof (`current_equity_evaluator`) is the CURRENT equity identity for the program
     of `version` (its versions row: `sha`, `params`); None when the identity cannot be computed (no answer either way).
     The EquityBook's reader asks it about a family that has no row (league/equity/families.py `standing`)."""
+    from .gate import run_sha
+
+    sha = run_sha({"sha": version["sha"], "params": version.get("params") or {}})
+    proof = state.get("banded_evaluator") if isinstance(state.get("banded_evaluator"), Mapping) else {}
+    if _panel_proof(proof):
+        # RELEASE E4: a proof naming the panel engine is judged by the xs identity (judged against the equity identity
+        # it would always read "not current", and the book would retire a healthy panel program the first time its
+        # row could not be read). None when that identity cannot be computed: unknown, nothing retired.
+        xs_sha = _xs_sha()
+        return None if xs_sha is None else current_xs_evaluator(state, sha, xs_sha)
     equity_sha = _equity_sha()
     if equity_sha is None:
         return None
-    from .gate import run_sha
+    return current_equity_evaluator(state, sha, equity_sha)
 
-    return current_equity_evaluator(state, run_sha({"sha": version["sha"], "params": version.get("params") or {}}),
-                                    equity_sha)
+
+def _panel_proof(proof: Mapping[str, Any]) -> bool:
+    """Whether a band proof names the panel engine (`league.xs.XS_ENGINE_VERSION`): the proof's engine says which
+    identity judges it."""
+    try:
+        from ..xs import XS_ENGINE_VERSION
+    except Exception:  # noqa: BLE001 - no panel package: no panel proof
+        return False
+    return proof.get("engine") == XS_ENGINE_VERSION
 
 
 class EquityUnreadable(RuntimeError):
@@ -533,12 +612,21 @@ def _read_equity(root: str | Path, *, family: str | None, lanes: Any, strict: bo
         return []
     from . import elane
 
+    xs_sha: str | None = None
     try:
         db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
         db.row_factory = sqlite3.Row
         try:
             fams = [f for f in _families(db, family, equity=True) if f["band"] in LIVE_BANDS]
-            seat = equity_seating(_banded(db, equity=True), elane.roster_seats(root)) \
+            if any(f["structure"] == "panel" for f in fams):
+                # RELEASE E4: a panel family is in a running band. Its proof is judged by the xs identity of THIS
+                # release's files; where that cannot be computed no panel row is current, and the strict reader is told
+                # "could not read" (it retires an instance on "no row").
+                xs_sha = _xs_sha()
+                if xs_sha is None and strict:
+                    raise EquityUnreadable("the xs identity could not be computed while a panel family is in a running "
+                                           "band")
+            seat = equity_seating(_banded(db, equity=True), elane.roster_seats(root), seatable=_equity_seatable(root)) \
                 if any(f["band"] == "candidate" for f in fams) else {"probe": [], "seated": [], "waiting": [], "seatless": []}
             hidden = set(seat["waiting"]) | set(seat["seatless"])
             versions = {}
@@ -574,11 +662,13 @@ def _read_equity(root: str | Path, *, family: str | None, lanes: Any, strict: bo
         state, spec = fam["state"], fam["spec"]
         params = loads(v["params"], {}) or {}
         sha = run_sha({"sha": v["sha"], "params": params})
-        if not current_equity_evaluator(state, sha, equity_sha):
+        panel = fam["structure"] == "panel"
+        if not (current_xs_evaluator(state, sha, xs_sha) if panel else current_equity_evaluator(state, sha, equity_sha)):
             continue  # its lots keep their exits (the EquityBook's), but no new entry under an unqualified identity
         lane = lane_of_spec(spec)
         symbols = [str(r).upper() for r in loads(fam["roots"], []) or []]
-        looked = state.get(elane.LOOK_KEY) if isinstance(state.get(elane.LOOK_KEY), Mapping) else {}
+        look_key = "elane_xs_look" if panel else elane.LOOK_KEY  # `elane_xs.LOOK_KEY`: XS1's sentence beside its trades
+        looked = state.get(look_key) if isinstance(state.get(look_key), Mapping) else {}
         out.append({
             "family": fam["id"], "band": fam["band"], "structure": fam["structure"], "roots": symbols, "symbols": symbols,
             "lane": lane, "label": elane.label(lane), "seeded": spec.get("seeded") is True,
```

## Patch 4: `league/swarm/elane.py`

`STRUCTURES` is the store's tuple; `_members` reads every equity structure; the dispatches.

ANCHORS: the import of `config as econfig`; `STRUCTURES = ("etf", "stock")`; in `cfg` the statement
`mode = raw.get("mode", DEFAULTS["mode"])` and the returned dict's `"screens"` entry; in `card_errors` the statement
`c = cfg(settings)` after `if lane is None: return []`; in `_members` the query's `AND structure IN ('etf', 'stock')`;
in `lineage_spent` the statement `c = cfg(settings)`; the first statements of `validate`, `look` and `view`; in
`same_lineage` the loop `for other in store.families(lanes=LANES):`.
WHAT: `STRUCTURES = EQUITY_STRUCTURES` (imported from `.store`: standard library only, no cycle). `_members` reads
`store.EQUITY_ONLY_SQL` (THE RATION: with the literal a panel lineage has no members, no try is counted for it, and
every fork takes a fresh Validation try). `card_errors` forwards a card of structure "panel" to
`elane_xs.card_errors`; `validate`, `look`, `view` and `lineage_spent` forward a panel family to `elane_xs`; `cfg`
returns the panel block (`"panel"`: `elane_xs.cfg`) and `screens["equity_xs"]` as it is. `same_lineage` (E1's, for an
S2 look) skips a panel family: a panel program is judged on its residual under XS1 with its own lineage rule, and a
panel look in flight must not make an ETF look wait on a Train series a panel family never keeps under E1's key.
`lineage_spent` IS NOT IN THE SPEC'S LIST and is needed: a style-open passer is not spent (A22), and a program the
lineage rule refused before its try has no Validation run for E1's count to find.
HELD BY: `test_elane_xs.ThePanelLineageHasOneTry` (X16: a fork of a tried panel family gets no second Validation run;
the tournament and the gate forward; E1's lineage rule never reads a panel program; `elane.cfg` carries the block).
```diff
diff --git a/league/swarm/elane.py b/league/swarm/elane.py
index c8d7f115..8cad8538 100644
--- a/league/swarm/elane.py
+++ b/league/swarm/elane.py
@@ -113,9 +113,13 @@ from typing import Any, Mapping, Sequence
 
 from ..equity import BETA, EQUITY, EQUITY_ENGINE_VERSION, LANES
 from ..equity import config as econfig
+from .store import EQUITY_STRUCTURES
 
 MODES = ("off", "gate")
-STRUCTURES = ("etf", "stock")
+#: The equity structures (`store.EQUITY_STRUCTURES`, the one place they are spelled out). RELEASE E4 adds "panel"
+#: (league/swarm/elane_xs.py), whose own switch is `elane.panel.mode`: `elane.structures` stays ["etf"] and a panel
+#: card, family, Validation, look and view are forwarded to that module.
+STRUCTURES = EQUITY_STRUCTURES
 LABELS = {BETA: "MARKET BETA", EQUITY: "EQUITY"}
 #: The plain statement beside every beta figure (the goal's item 2: a BETA lane, labelled as market beta).
 BETA_NOTE = "MARKET BETA: profit from market direction, reported beside the same-risk buy-and-hold; not alpha"
@@ -281,6 +285,9 @@ def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
 
     mode = raw.get("mode", DEFAULTS["mode"])
     screens = raw.get("screens") if isinstance(raw.get("screens"), Mapping) else {}
+    from . import elane_xs  # RELEASE E4: the panel's block and its screen's pin pass through, each held by its owner
+
+    panel = elane_xs.cfg(settings)
     return {
         "mode": mode if mode in MODES else "off",
         "universe": words("universe", tuple(econfig.UNIVERSE), upper=True),
@@ -288,7 +295,9 @@ def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
         "birth_share": number("birth_share", 0.0, 0.5),
         # The roster's bound is its default (== equity_money.probe.max_programs, 3): a setting may only lower it.
         "roster": int(number("roster", 0, float(DEFAULTS["roster"]), count=True)),
-        "screens": {lane: _screen_block(screens.get(lane)) for lane in LANES},
+        "screens": {**{lane: _screen_block(screens.get(lane)) for lane in LANES},
+                    elane_xs.SCREEN_KEY: dict(panel.pop("screen"))},
+        elane_xs.SETTINGS_KEY: panel,
         "val_tries": int(number("val_tries", 1, 1, count=True)),
         "looks_per_lineage": int(number("looks_per_lineage", 1, 1, count=True)),
         # The line's bound is its default (-300): a setting can only raise it toward zero.
@@ -343,6 +352,10 @@ def card_errors(card: Any, structure: Any, symbols: Any, settings: Mapping[str,
     lane = card_lane(card)
     if lane is None:
         return []
+    if _token(structure) == "panel":  # RELEASE E4: a panel card's box is the panel lane's own
+        from . import elane_xs
+
+        return elane_xs.card_errors(card, settings)
     c = cfg(settings)
     errors: list[str] = []
     if c["mode"] == "off":
@@ -537,8 +550,11 @@ def _members(store: Any, fid: str) -> list[str]:
     lines = store._connected_lineages(row["lineage"])
     if not lines:
         return []
+    from .store import EQUITY_ONLY_SQL  # every equity structure, the panel's too: with a literal here a panel lineage
+
+    # has no members, no try is ever counted for it, and every fork and rebirth of it takes a fresh Validation try.
     return [r["id"] for r in store._all(f"SELECT id FROM families WHERE lineage IN ({','.join('?' * len(lines))}) "
-                                        "AND structure IN ('etf', 'stock')", tuple(lines))]
+                                        f"AND {EQUITY_ONLY_SQL}", tuple(lines))]
 
 
 def lineage_tries(store: Any, fid: str) -> list[dict[str, Any]]:
@@ -668,6 +684,10 @@ def lineage_spent(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any
     try:
         if lane_of(store, fam) is None:
             return None
+        from . import elane_xs
+
+        if elane_xs.is_panel(fam):  # RELEASE E4: the panel's own rule (a style-open passer is not spent: A22)
+            return elane_xs.lineage_spent(store, fam, settings)
         c = cfg(settings)
         fid = str(fam["id"])
         if store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
@@ -848,6 +868,10 @@ def validate(tournament: Any, fam: Mapping[str, Any], version: Mapping[str, Any]
     return sd), the screen's pre-check (`league.equity.screen.precheck`: S1's and S2's one rule) as its line, the lineage's
     try recorded (`TRY_KEY`). `screen` in its answer, its state and its event is the lane's pinned screen
     (`screen_name`). Returns the tournament's verdict dict."""
+    from . import elane_xs
+
+    if elane_xs.is_panel(fam):  # RELEASE E4: a panel family's Validation is the panel lane's (screen XS1)
+        return elane_xs.validate(tournament, fam, version)
     store, settings = tournament.store, tournament.settings
     fid, n = str(fam["id"]), int(version["n"])
     lane = lane_of(store, fam)
@@ -1020,10 +1044,12 @@ def same_lineage(store: Any, fam: Mapping[str, Any], lane: str, template: str,
 
     from ..equity import screen as S
 
+    from . import elane_xs
+
     mine = dict(zip(train.get("days") or [], train.get("r") or []))
     for other in store.families(lanes=LANES):
-        if str(other["id"]) == str(fam["id"]):
-            continue
+        if str(other["id"]) == str(fam["id"]) or elane_xs.is_panel(other):
+            continue  # RELEASE E4: a panel program is judged on its residual under XS1, with its own lineage rule
         state = other.get("state") or {}
         looked = isinstance(state.get(LOOK_KEY), Mapping)
         if not looked and not (state.get("look_inflight") or {}).get("sha"):
@@ -1139,6 +1165,10 @@ def look(gate: Any, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str
     refuses the floor; a holdout run that did is a look spent and failed, never judged; a sealed run sent and not
     answered is owed once, then the look is spent and failed (`LOOK_SENDS`). True passed (the family becomes a
     Candidate), False failed, None not run (no look spent)."""
+    from . import elane_xs
+
+    if elane_xs.is_panel(fam):  # RELEASE E4: a panel family's one look is the panel lane's (screen XS1)
+        return elane_xs.look(gate, fam, version, sha)
     store, settings = gate.store, gate.settings
     fid, n = str(fam["id"]), int(version["n"])
     lane = lane_of(store, fam)
@@ -1374,6 +1404,10 @@ def birth_seeds(store: Any, settings: Mapping[str, Any] | None) -> list[str]:
 def view(fam: Mapping[str, Any], *, lane: str | None) -> dict[str, Any]:
     """The lane's line in a status or report: {lane, label, seeded, screen (the screen that judged its recorded look;
     None before it), try, look, beside} (labels always; figures only where the reader may see them)."""
+    from . import elane_xs
+
+    if elane_xs.is_panel(fam):  # RELEASE E4: the panel's line (screen XS1, its seat, its sentence)
+        return elane_xs.view(fam, lane=lane)
     state = fam.get("state") if isinstance(fam.get("state"), Mapping) else {}
     spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
     held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else None
```

## Patch 5: `league/swarm/cards.py`, `league/swarm/dlane.py`

A card may declare structure "panel"; `declared_lane` reads the store's tuple.

ANCHORS: in `cards.validate`, inside `if equity_lane is not None:`, the three statements that set `card["lane"]`,
`card["structure"]` and `card["symbols"]`; the module docstring's EQUITY LANES paragraph; in `dlane.declared_lane` the
statement holding `in ("etf", "stock")`.
WHAT: a panel card keeps `panel`, `max_names`, `rebalance` and `weekday` (part of its canonical JSON, so of its sha) and
NO `symbols`; its box is `elane_xs.card_errors`, reached through `elane.card_errors` (patch 4); its cell's structure
family is "equity:panel". `dlane.declared_lane` reads `store.EQUITY_STRUCTURES` (a panel family is never read as a
direction family).
HELD BY: `test_elane_xs.ThePanelBirths` (the stored card), `test_elane_xs.NoStructureLiteralOutsideTheStore`.
```diff
diff --git a/league/swarm/cards.py b/league/swarm/cards.py
index a3557e5b..0bd24fe9 100644
--- a/league/swarm/cards.py
+++ b/league/swarm/cards.py
@@ -162,7 +162,9 @@ reads it and checks it against the equity lanes' box (`elane.card_errors`: a str
 only, symbols inside `elane.universe`, the inputs a daily bar carries, never a flat comparison), every reason named. Its
 class may be any of `MECHANISM_CLASSES` or the lanes' `equity_premium` (`elane.CLASSES`); it needs no ablation (its
 comparison is the same-exposure buy-and-hold, the screen's S1-X label). The card stores its `lane`, `structure` and
-`symbols` (inside its canonical JSON and so its sha). ITS CELL IS LANE-SCOPED (A8.12): an equity card's structure family
+`symbols` (inside its canonical JSON and so its sha). A PANEL card (release E4: `structure` "panel", lane "equity";
+league/swarm/elane_xs.py `card_errors`) stores `panel`, `max_names`, `rebalance` and `weekday` in their place and names
+no symbol; its cell is "equity:panel". ITS CELL IS LANE-SCOPED (A8.12): an equity card's structure family
 is "<lane>:<structure>" (`key_of`, `elane.lineage_key`), so no options row shares its cell, and THE GRAVEYARD IS
 LANE-SCOPED: `RebirthIndex` keeps each equity lane's rows apart (`equity_rows`, by `row_lane`), a REFUTED row of an
 equity lane binds only that lane's cards, and no equity row ever binds, or is listed for, an options card (the options
@@ -503,7 +505,16 @@ def validate(raw: Any, structure: Any = None, *, roots: Any = None,
         errors = [e for e in errors if e.split(":", 1)[0] not in fields] + boxed
         card["lane"] = equity_lane
         card["structure"] = _token(given)
-        card["symbols"] = sorted({str(x).strip().upper() for x in symbols}) if isinstance(symbols, (list, tuple)) else []
+        if card["structure"] == "panel":
+            # RELEASE E4 (league/swarm/elane_xs.py `card_errors`, reached through `elane.card_errors`): a panel card
+            # declares its panel, how many names it holds and its rebalance schedule, and NO symbol (a panel program
+            # sees salted slots). They are part of the card, and so of its sha.
+            for name in ("panel", "max_names", "rebalance", "weekday"):
+                if raw.get(name) is not None:
+                    card[name] = raw[name]
+        else:
+            card["symbols"] = (sorted({str(x).strip().upper() for x in symbols})
+                               if isinstance(symbols, (list, tuple)) else [])
     return (card, []) if not errors else (None, errors)
 
 
diff --git a/league/swarm/dlane.py b/league/swarm/dlane.py
index 40cc05d4..4f9e5b1c 100644
--- a/league/swarm/dlane.py
+++ b/league/swarm/dlane.py
@@ -614,8 +614,11 @@ def declared_lane(store: Any, fam: Mapping[str, Any] | None) -> str:
     spec = fam.get("spec")
     if isinstance(spec, Mapping) and spec.get("lane") in LANES:
         return str(spec["lane"])
-    if isinstance(spec, Mapping) and spec.get("lane") is not None and str(fam.get("structure") or "") in ("etf", "stock"):
-        return ALPHA  # LANE SCOPING (A8.12): an equity-lane family is never a direction family (its card is not read)
+    if isinstance(spec, Mapping) and spec.get("lane") is not None:
+        from .store import EQUITY_STRUCTURES  # every equity structure, the panel's too (release E4)
+
+        if str(fam.get("structure") or "") in EQUITY_STRUCTURES:
+            return ALPHA  # LANE SCOPING (A8.12): an equity-lane family is never a direction family (its card is not read)
     fid = str(fam.get("id") or "")
     if not fid or store is None:
         return ALPHA
```

## Patch 6: `league/swarm/elane_births.py`

The PANEL block of the request; a panel proposal is admitted by `elane_xs.admit`; the quota splits by structure.

ANCHORS: `researching`; `EquityQuota.__init__` (after `self.refused = 0`), `why_not`, `admits`, `born`, `event`;
`families_text` (its loop); `EquityPass.request` (the `parts = [...]` list); `EquityPass.admit` (its imports, and the
statement `if structure not in allowed:`).
WHAT: `researching` skips a panel family (the panel has its own ceiling, `elane.panel.max_alive`). `EquityQuota` gains
`by_structure`, `panel` (`elane_xs.quota`: how many of the pass's births may be panel families; 0 while the lane bears
nothing, and the pass is then E2's own, event included) and `born_panel`; `why_not`, `admits` and `born` take an
optional `structure`. `request` adds `elane_xs.request_text` (the PANEL block; the panel Train map follows E2's own
through patch 7). `admit` forwards a row of structure "panel" to `elane_xs.admit`, which stamps `hidden_year` through
`elane_xs.assign` (never `elane_folds.birth_fields`). `families_text` skips panel families.
NOT TAKEN FROM THE SPEC: `EquityPass.birth` is not patched (the panel's birth is `elane_xs.birth`, called by
`elane_xs.admit`). The equity graveyard's rebirth index does not bind a panel card in this release: what binds it is
its CLOSED cells, the same idea in research in its cell, and a lineage that has its try.
HELD BY: `test_elane_xs.ThePanelBirths` (five tests), `test_elane_xs_seal.NothingAfterTrainReachesAGenerator
.test_e2s_own_request_and_brief_are_as_blind`.
```diff
diff --git a/league/swarm/elane_births.py b/league/swarm/elane_births.py
index 266ac8d9..e53d8dc6 100644
--- a/league/swarm/elane_births.py
+++ b/league/swarm/elane_births.py
@@ -130,8 +130,12 @@ def universe(settings: Mapping[str, Any] | None) -> dict[str, list[str]]:
 def researching(store: Any) -> int:
     """E2 families in Train research (E2's record: neither passed nor refuted nor closed). Outcome-free (A9 D3): a
     family that passed Train leaves this count whatever happens to it after."""
+    from . import elane_xs
+
     n = 0
     for fam in elane_seal.equity_families(store):
+        if elane_xs.is_panel(fam):
+            continue  # RELEASE E4: a panel family is counted by the panel's own ceiling (`elane.panel.max_alive`)
         if elane_train.e2_family(fam) and elane_train.record_of(fam).get("status", "researching") == "researching":
             n += 1
     return n
@@ -182,33 +186,52 @@ class EquityQuota:
                      if self.on and self.room else 0)
         self.passed = {BETA: 0, EQUITY: 0}
         self.refused = 0
+        # RELEASE E4, THE QUOTA BY STRUCTURE (league/swarm/elane_xs.py `quota`): `panel` of the pass's births may be
+        # panel families (0 while the panel lane bears nothing: the pass is then E2's own), the rest share programs; a
+        # share one structure leaves unfilled is not handed to the other.
+        from . import elane_xs
 
-    def why_not(self, lane: str) -> str | None:
-        """Why one more equity birth may not be born in this pass, or None."""
+        self.by_structure = True
+        self.panel = elane_xs.quota(store, settings, self.want) if self.on else 0
+        self.born_panel = 0
+
+    def why_not(self, lane: str, structure: str | None = None) -> str | None:
+        """Why one more equity birth (of `structure`: "panel" for a panel family) may not be born in this pass, or
+        None."""
         if not self.on:
             return "the equity lanes' births are off (elane.mode, elane.birth_share)"
         if lane not in LANES:
             return f"{lane!r} is not an equity lane"
         if sum(self.passed.values()) >= self.want:
             return f"the pass's {self.want} equity births are born"
+        if structure == "panel":
+            if self.born_panel >= self.panel:
+                return f"the pass's {self.panel} panel births are born (elane.panel.birth_share)"
+        elif sum(self.passed.values()) - self.born_panel >= self.want - self.panel:
+            return (f"the pass's {self.want - self.panel} share-program births are born (its other {self.panel} are the "
+                    "panel's)")
         return None
 
-    def admits(self, lane: str) -> bool:
-        why = self.why_not(lane)
+    def admits(self, lane: str, structure: str | None = None) -> bool:
+        why = self.why_not(lane, structure)
         if why is not None:
             self.refused += 1
         return why is None
 
-    def born(self, lane: str) -> None:
+    def born(self, lane: str, structure: str | None = None) -> None:
         if lane in self.passed:
             self.passed[lane] += 1
+            self.born_panel += int(structure == "panel")
 
     def short(self) -> int:
         return max(0, self.want - sum(self.passed.values()))
 
     def event(self) -> dict[str, Any]:
-        return {"equity_births": dict(self.passed), "equity_refused_by_quota": self.refused, "equity_short": self.short(),
-                "equity_want": self.want, "window": dict(self.window), "researching": self.researching}
+        out = {"equity_births": dict(self.passed), "equity_refused_by_quota": self.refused, "equity_short": self.short(),
+               "equity_want": self.want, "window": dict(self.window), "researching": self.researching}
+        if self.panel or self.born_panel:
+            out["panel"] = {"want": self.panel, "born": self.born_panel}  # RELEASE E4
+        return out
 
     def text(self) -> str:
         """The request's quota lines ("" while off)."""
@@ -357,9 +380,11 @@ def families_text(store: Any, settings: Mapping[str, Any] | None) -> str:
     """The E2 families in Train research or refuted, the newest `families_shown`, Train facts only ("" for none)."""
     shown = cfg(settings)["families_shown"]
     rows = []
+    from . import elane_xs
+
     for fam in elane_seal.equity_families(store):
-        if not elane_train.e2_family(fam) or elane_train.passed_version(fam) is not None:
-            continue
+        if not elane_train.e2_family(fam) or elane_train.passed_version(fam) is not None or elane_xs.is_panel(fam):
+            continue  # (a panel family's Train facts are the PANEL block's: `elane_xs.request_text`)
         facts = elane_seal.train_facts(fam, STATE_KEY)
         rec = facts["record"]
         versions = elane_train.versions_of(rec)
@@ -451,9 +476,15 @@ class EquityPass:
         if isinstance(last, Mapping) and int(last.get("short") or 0):
             lead = (f"YOUR LAST EQUITY PASS LEFT {int(last['short'])} OF ITS BIRTHS UNFILLED: propose families that fit "
                     "the lanes' box, the agenda and the bar below.\n\n")
+        from . import elane_xs
+
         parts = [f"{lead}Propose {want} new EQUITY-LANE families (\"lane\": \"beta\" or \"equity\"), each with its card "
                  "and its first program; propose both lanes when you propose two or more.",
                  lanes_text(self.settings), agenda_text(), quota.text(),
+                 # RELEASE E4, THE PANEL BLOCK ("" while the panel lane bears nothing): what a panel program is, its
+                 # contract in brief, the panel agenda, the panel quota and the closed panel cells; the panel Train
+                 # map, with its ZERO-EDGE EXPECTED column, follows the equity one (`elane_train.train_map_text`).
+                 elane_xs.request_text(self.store, self.settings, want),
                  elane_train.train_map_text(self.store, self.settings), graveyard_text(self.store, self.settings),
                  tried_text(self.store), families_text(self.store, self.settings), vocabulary_text(self.settings),
                  last_text(self.store)]
@@ -534,7 +565,7 @@ class EquityPass:
 
     def admit(self, rows: Sequence[Any], quota: EquityQuota, route: elane_yield.Route) -> list[str]:
         """Birth the proposals the admission admits (the module docstring); every refusal named."""
-        from . import cards
+        from . import cards, elane_xs
         from .architect import family_slug, same_idea
 
         allowed = universe(self.settings)
@@ -558,6 +589,16 @@ class EquityPass:
                 self.refuse(slug, "lane: the proposal and its card declare different lanes")
                 continue
             structure = str(row.get("structure") or (raw_card or {}).get("structure") or "").strip().lower()
+            if structure == elane_xs.STRUCTURE:
+                # RELEASE E4: a panel proposal's admission is the panel lane's (its box, its cells, its hidden year
+                # stamped by `elane_xs.assign`, never `elane_folds.birth_fields`); refused there while the lane is closed.
+                fid = elane_xs.admit(self, row, slug=slug, lane=lane, mechanism=mechanism, quota=quota, route=route,
+                                     fams=fams)
+                if fid is not None:
+                    quota.born(lane, structure)
+                    born.append(fid)
+                    fams.append(self.store.family(fid) or {"id": fid})
+                continue
             if structure not in allowed:
                 self.refuse(slug, f"structure: {structure or 'none'!r} is not one of {', '.join(allowed) or 'none'} "
                                   "(elane.structures)")
```

## Patch 7: `league/swarm/elane_train.py`

E2's researcher forwards a panel family; the record's readers read the panel's own record.

ANCHORS: `record_of`; `pass_current` and `may_validate` (first statements); `_update` (its `set_state`); `train_map`
and `refuted_rows` (their loops); `train_map_text` (its docstring, its `rows = train_map(store)` and its `return`);
`EquityResearcher.queue` (its loop); `EquityResearcher.step`, `brief`, `restart`, `score` and `review_step` (first
statements).
WHAT: `record_key(fam)` (new): `elane_xs.STATE_KEY` for a panel family, else E2's own; `record_of` and `_update` read
it, so the queue, the upkeep, the backoff and `close_retired` work on a panel family's record (it has E2's shape).
`pass_current` and `may_validate` forward a panel family (`elane_xs.pass_current`: the xs identity and the costs'
standing; `elane_xs.may_validate`: its pass, the review under the panel rubric, the mode "gate"). `step`, `score`,
`brief`, `review_step` and `restart` forward a panel family to `elane_xs` (`step` asks `may_run` before any run; THE
REVIEW of a panel program carries `elane_xs.REVIEW_XS`, the captain's A22 (3)). `queue` asks `elane_xs.blocked(self)`
ONCE a round, when it meets a panel family: while the panel lane is closed (the rollback) or no panel run may start
(a wall is near, the day's panel CPU is spent) a panel family takes no place in the round, so it never slows the ETF
families' research (E2's queue takes the least recently worked `train_per_round` families). `train_map`, `closed_cells` (through
it) and `refuted_rows` skip a panel family; `train_map_text` is followed by `elane_xs.train_map_text` (the panel's
cells, each with its ZERO-EDGE EXPECTED column).
HELD BY: `test_elane_xs_bar.E2sResearcherForwardsAPanelFamily` (five tests).
```diff
diff --git a/league/swarm/elane_train.py b/league/swarm/elane_train.py
index bc76727b..86bc056e 100644
--- a/league/swarm/elane_train.py
+++ b/league/swarm/elane_train.py
@@ -573,9 +573,17 @@ def bar_text() -> str:
 
 
 # ----------------------------------------------------------------------------------------------------------- the record
+def record_key(fam: Mapping[str, Any] | None) -> str:
+    """The family-state key of a family's Train record: E2's own (`STATE_KEY`), or, for a PANEL family (release E4),
+    the panel's (`elane_xs.STATE_KEY`: the same shape, so the queue, the upkeep and the guard below read either)."""
+    from . import elane_xs
+
+    return elane_xs.STATE_KEY if elane_xs.is_panel(fam) else STATE_KEY
+
+
 def record_of(fam: Mapping[str, Any] | None) -> dict[str, Any]:
-    """E2's Train record of a family ({} for a family E2 did not bear)."""
-    return elane_seal.e2_record(fam, STATE_KEY)
+    """E2's Train record of a family ({} for a family E2 did not bear); a panel family's own record (`record_key`)."""
+    return elane_seal.e2_record(fam, record_key(fam))
 
 
 def e2_family(fam: Mapping[str, Any] | None) -> bool:
@@ -622,6 +630,10 @@ def tried(store: Any, fid: str, n: int) -> bool:
 def pass_current(store: Any, fam: Mapping[str, Any] | None) -> bool:
     """THE IDENTITY (the module docstring): the family's pass was judged under the equity identity in force, or its
     version has had its Validation try (E1 owns it from there), or no identity can be read."""
+    from . import elane_xs
+
+    if elane_xs.is_panel(fam):  # RELEASE E4: a panel pass is judged under the xs identity (and its costs' standing)
+        return elane_xs.pass_current(store, fam)
     n = passed_version(fam)
     if n is None:
         return False
@@ -637,6 +649,10 @@ def may_validate(store: Any, fam: Mapping[str, Any] | None, n: Any) -> bool:
     E2 did not bear; for an E2 family, only when `n` is its pass (the first version that passed equity-v1 AND the equity
     review), the review E1's look reads is in its state for that exact program, and the pass is current (`pass_current`).
     E1's `next_try` keeps its own due, stale and retry logic: a Validation gone stale is validated again through here."""
+    from . import elane_xs
+
+    if elane_xs.is_panel(fam):  # RELEASE E4: the panel's guard (its record, its rubric's review, the mode "gate")
+        return elane_xs.may_validate(store, fam, n)
     if not e2_family(fam):
         return True
     fam = fam or {}
@@ -963,17 +979,19 @@ def _update(store: Any, fid: str, change: Callable[[dict[str, Any]], None]) -> d
         rec.setdefault("versions", {})
         change(rec)
         rec["last_at"] = store.now()
-        store.set_state(fid, **{STATE_KEY: rec})
+        store.set_state(fid, **{record_key(fam): rec})
     return rec
 
 
 # ----------------------------------------------------------------------------------------------------------- the map
 def train_map(store: Any) -> list[dict[str, Any]]:
     """THE EQUITY TRAIN MAP's rows, one a cell (the module docstring), the cells with a pass first, then by births."""
+    from . import elane_xs
+
     cells: dict[tuple[str, str, str], dict[str, Any]] = {}
     for fam in elane_seal.equity_families(store):
-        if not e2_family(fam):
-            continue
+        if not e2_family(fam) or elane_xs.is_panel(fam):
+            continue  # (RELEASE E4: a panel family is on the panel's own map, `elane_xs.train_map`, never in a cell here)
         facts = elane_seal.train_facts(fam, STATE_KEY)
         rec = facts["record"]
         cell = cell_of(facts["lane"], facts["agenda"], facts["symbols"])
@@ -1004,10 +1022,15 @@ def closed_cells(store: Any, settings: Mapping[str, Any] | None) -> list[tuple[s
 
 
 def train_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int = 40) -> str:
-    """THE EQUITY TRAIN MAP for the architect's equity request ("" with no E2 family yet). Train facts only."""
+    """THE EQUITY TRAIN MAP for the architect's equity request ("" with no E2 family yet). Train facts only. RELEASE
+    E4: the PANEL Train map follows it (`elane_xs.train_map_text`: the panel's cells, each with its ZERO-EDGE EXPECTED
+    column; "" with no panel family)."""
+    from . import elane_xs
+
+    panel = elane_xs.train_map_text(store, settings, limit=limit)
     rows = train_map(store)
     if not rows:
-        return ""
+        return panel
     closed = set(closed_cells(store, settings))
     lines = [f"EQUITY TRAIN MAP (lane / mechanism / universe group; {MAP_LABEL}). Each cell: births, families "
              "Train-scored, passed equity-v1 and the equity review (the best passing pooled daily t at 1.0x), refuted on "
@@ -1019,17 +1042,19 @@ def train_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int
                      f"refuted {r['refuted']}, stalled {r['stalled']}{shut}")
     if len(rows) > limit:
         lines.append(f"- ... and {len(rows) - limit} more cells")
-    return "\n".join(lines)
+    return "\n".join(lines) + (f"\n\n{panel}" if panel else "")
 
 
 def refuted_rows(store: Any, *, limit: int = 30) -> list[dict[str, Any]]:
     """E2's equity graveyard: the families it refuted on Train with a version the bar judged (from its record, newest
     first): {id, lane, agenda, symbols, mechanism, codes, versions, why}. The rows that bind the equity cards
     (`closed_cells`); a stalled family is none."""
+    from . import elane_xs
+
     out = []
     for fam in elane_seal.equity_families(store):
-        if not e2_family(fam):
-            continue
+        if not e2_family(fam) or elane_xs.is_panel(fam):
+            continue  # (RELEASE E4: a panel family's refutation binds its own cells: `elane_xs.closed_cells`)
         facts = elane_seal.train_facts(fam, STATE_KEY)
         refuted = facts["record"].get("refuted")
         if facts["record"].get("status") != "refuted" or not isinstance(refuted, Mapping) or not judged(facts["record"]):
@@ -1273,10 +1298,17 @@ class EquityResearcher:
     def queue(self) -> list[dict[str, Any]]:
         """The living E2 families with a step to take (researching, or a pass to re-score under a new equity identity),
         none waiting out a backoff, the least recently worked first, at most `train_per_round`."""
+        from . import elane_xs
+
         rows = []
+        held: Any = False  # RELEASE E4: why no panel family may step now, asked once a round and only when one is met
         for fam in elane_seal.equity_families(self.store, alive=True):
             if not e2_family(fam):
                 continue
+            if elane_xs.is_panel(fam):
+                held = elane_xs.blocked(self) if held is False else held
+                if held is not None:
+                    continue  # the panel lane is closed, or no panel run may start: it takes no place in the round
             rec = record_of(fam)
             status = rec.get("status", "researching")
             if self.waiting(rec):
@@ -1350,6 +1382,10 @@ class EquityResearcher:
     def step(self, fam: Mapping[str, Any]) -> dict[str, Any]:
         """One step of a family (the module docstring): re-score a stale pass; review a bar pass; score its newest
         unscored version; else, with budget left, ask for a program (its first, or a revision); else retire it."""
+        from . import elane_xs
+
+        if elane_xs.is_panel(fam):  # RELEASE E4: a panel family's step is the panel lane's (`may_run` first)
+            return elane_xs.step(self, fam)
         c = cfg(self.settings)
         fid = str(fam["id"])
         rec = record_of(fam)
@@ -1375,8 +1411,10 @@ class EquityResearcher:
     def brief(self, fam: Mapping[str, Any]) -> str:
         """The question's user turn: the family's card, its agenda prior, the bar and its own Train versions (Train
         facts and the review's reasons only: league/swarm/elane_seal.py)."""
-        from . import cards, elane
+        from . import cards, elane, elane_xs
 
+        if elane_xs.is_panel(fam):  # RELEASE E4: the panel's brief (its contract, its bar, `elane_xs.train_facts`)
+            return elane_xs.brief(self, fam)
         c = cfg(self.settings)
         facts = elane_seal.train_facts(fam, STATE_KEY)
         rec = facts["record"]
@@ -1478,6 +1516,11 @@ class EquityResearcher:
     def restart(self, fid: str, code: str, params: Mapping[str, Any], runs: Sequence[Any]) -> dict[str, Any]:
         """THE RESTART CHECK of a version on its uninterrupted 1.0x Train runs (`restart_check` over `state_inputs`),
         through the isolated runner's decider (E1's `Isolated.decider`)."""
+        from . import elane_xs
+
+        if elane_xs.is_panel(self.store.family(fid)):
+            # RELEASE E4: the panel's restart check, by CALL, through the panel kind and the panel's own decider.
+            return elane_xs.restart(self, code, params, name=fid, runs=runs)
         decider = getattr(self.runner(), "decider", None)
         if decider is None:
             raise StateCheckInterrupted("the isolated runner has no decider: the restart check cannot run")
@@ -1534,6 +1577,10 @@ class EquityResearcher:
         (the module docstring, WHAT A VERDICT IS); once Y1-R1 hold, THE RESTART CHECK on the 1.0x runs. A bar pass goes
         to the equity review (`review_step`); `rescore` (a pass judged under another equity identity): passed again it
         stands, else the pass is withdrawn."""
+        from . import elane_xs
+
+        if elane_xs.is_panel(fam):  # RELEASE E4: the panel's Train bar (equity-xs-v1), its runs and its record
+            return elane_xs.score(self, fam, version, rescore=rescore)
         c = cfg(self.settings)
         fid, n = str(fam["id"]), int(version["n"])
         code, params = str(version.get("code") or ""), dict(version.get("params") or {})
@@ -1641,8 +1688,13 @@ class EquityResearcher:
         two different models. Both pass: the version is the family's pass (its lineage's one Validation try). A failure
         (or `review_max_unclear` unclear reads of one stage) is a Train failure of the version ("REVIEW"). A question no
         route answered counts nothing and is asked again next round."""
+        from . import elane_xs
         from .gate import run_sha
 
+        if elane_xs.is_panel(fam):
+            # RELEASE E4 (the captain's A22 (3)): the review of a panel program carries the panel rubric
+            # (`elane_xs.REVIEW_XS`: no embedded return table, no calendar recognition, and the spec's three).
+            return elane_xs.review_step(self, fam, n)
         fid = str(fam["id"])
         rec = record_of(fam)
         pending = dict(rec.get("review") or {}) if isinstance(rec.get("review"), Mapping) else {"version": n}
```

## Patch 8: `league/swarm/elane_seal.py`, `league/swarm/elane_yield.py`

`SEALED_KEYS` gains the panel's eight; `train_counts` counts panel passes.

ANCHORS: the closing lines of the `SEALED_KEYS` frozenset; in `elane_yield.train_counts` the statement
`rec = elane_seal.e2_record(fam, train_key)`; in `report` the statement that reads `LOOK_KEY`.
WHAT: the eight keys of `elane_xs.SEALED` written out in the frozenset (league/swarm/elane_seal.py imports nothing of
the lane it seals; a test holds the two equal). `train_counts` reads a panel family's own record, so its Train passes
count on its birth route's row and steer the route choice as an ETF family's do; `report` reads the panel's look.
HELD BY: `test_elane_xs.NoStructureLiteralOutsideTheStore.test_the_sealed_keys_are_the_seals`,
`test_elane_xs_bar.E2sResearcherForwardsAPanelFamily.test_e2s_maps_never_count_a_panel_family`.
```diff
diff --git a/league/swarm/elane_seal.py b/league/swarm/elane_seal.py
index 450116a0..6b477b93 100644
--- a/league/swarm/elane_seal.py
+++ b/league/swarm/elane_seal.py
@@ -59,6 +59,11 @@ SEALED_KEYS = frozenset({
     "elane_try", "elane_look", "elane_floor", "elane_train_r", "validation_r_sd_by_version", "validation_r_sd",
     "banded_evaluator", "validation_line", "validation_numbers", "validation_view", "validation", "gate_ready",
     "gate_hold", "look_inflight", "look", "holdout", "forward", "band_reason", "submitted_run",
+    # RELEASE E4, THE PANEL (league/swarm/elane_xs.py `SEALED`; a test holds the two equal): the program's floor, its
+    # two Train series (the lineage rule's), the pre-check's record, the Train placebo ranks, the halves' figures, the
+    # hidden run and the look. A panel family's Train record is read through `elane_xs.train_facts` only.
+    "elane_xs_floor", "elane_xs_train_x", "elane_xs_train_u", "elane_xs_precheck", "elane_xs_placebo",
+    "elane_xs_halves", "elane_xs_oof", "elane_xs_look",
 })
 #: The family columns no generator reads of an equity family.
 SEALED_COLUMNS = frozenset({"band", "band_since", "retired_at", "retire_reason", "validated_version", "best_validation",
diff --git a/league/swarm/elane_yield.py b/league/swarm/elane_yield.py
index ee13e20a..8e71dd4e 100644
--- a/league/swarm/elane_yield.py
+++ b/league/swarm/elane_yield.py
@@ -239,7 +239,9 @@ def train_counts(store: Any, train_key: str) -> dict[str, dict[str, int]]:
         key = spec.get(ROUTE_KEY) if isinstance(spec, Mapping) else None
         if not key:
             continue
-        rec = elane_seal.e2_record(fam, train_key)
+        # RELEASE E4: a panel family's Train record is its own key (league/swarm/elane_xs.py `STATE_KEY`), of the same
+        # shape: its Train passes count on its birth route's row as an ETF family's do.
+        rec = elane_seal.e2_record(fam, "elane_xs" if fam.get("structure") == "panel" else train_key)
         row = out.setdefault(str(key), {"families": 0, "train_scored": 0, "train_passes": 0})
         row["families"] += 1
         versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
@@ -317,7 +319,8 @@ def report(store: Any, settings: Mapping[str, Any] | None, *, train_key: str) ->
         row = later.setdefault(str(key), {"validation_entries": 0, "looks": 0, "looks_passed": 0, "live": 0})
         tried = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
         row["validation_entries"] += int(bool(tried.get("entered")))
-        look = state.get(LOOK_KEY) if isinstance(state.get(LOOK_KEY), Mapping) else None
+        look_key = "elane_xs_look" if fam.get("structure") == "panel" else LOOK_KEY  # the panel's look (release E4)
+        look = state.get(look_key) if isinstance(state.get(look_key), Mapping) else None
         if look is not None:
             row["looks"] += 1
             verdict = look.get("verdict")
```

## Patch 9: `league/swarm/settings.py`, `league/swarm/policy.json`, `league/swarm/loop.py`

The `elane.panel` block and `screens.equity_xs` (nulls); `adopt_xs` at the start.

ANCHORS: settings.py: the comment above `"elane": {"mode": "off"},` (the value itself is NOT changed: E1's
`test_elane` holds `DEFAULTS["elane"] == {"mode": "off"}`, and `elane_xs.cfg` reads a block that is no object as its
defaults). policy.json: `elane.screens` gains `equity_xs` after the two lanes' blocks, and `elane` gains `panel` after
`program_loss_usd`. loop.py: the statement `self.adopt_equity()` in `run`, a new method `adopt_xs` before `run`, and
the module docstring's EQUITY LANES paragraph.
WHAT: policy.json ships `elane.panel` at the code's defaults (mode "off") and `elane.screens.equity_xs` AS NULLS IN
`league.xs.screen.PIN_KEYS`' ORDER: THE INTEGRATOR FILLS THE PIN from the receipt (`screen.PIN_SOURCES`) in the commit
that lands docs/benchmarks/equity_screen_xs_1.json. `Swarm.adopt_xs` calls package E's `evaluator.adopt_xs` with
`league.xs.identity.xs_identity()` beside `adopt_equity`; an error (E's patch 3 not merged, an identity that cannot be
read) is logged and never stops the start, and `bands.read` judges a panel band against the running files whatever
was adopted.
HELD BY: `test_elane_xs.NoReceiptNoLook.test_the_committed_policy_ships_the_pin_as_nulls_in_the_pins_own_order` (it
also holds a filled pin's sha256 to the receipt file's bytes, once the integrator lands them).
```diff
diff --git a/league/swarm/loop.py b/league/swarm/loop.py
index 389699be..c5d0f1e3 100644
--- a/league/swarm/loop.py
+++ b/league/swarm/loop.py
@@ -38,7 +38,8 @@ hidden year (`agenda_alert`); the operator's tool `scripts/agenda_install.py` re
 
 THE EQUITY LANES (release E1, Oct 2026; league/swarm/elane.py). At each start, beside the options evaluator's adoption,
 the equity identity's (`evaluator.adopt_equity` with `evaluator.equity_identity()`: equity families only; a failure is
-logged and never stops the start, and `bands.read` then reads no equity band as current). While `elane.mode` is "gate",
+logged and never stops the start, and `bands.read` then reads no equity band as current), and the xs identity's
+(`adopt_xs`, release E4: panel families only, the same way). While `elane.mode` is "gate",
 each main-loop pass births the three captain-seeded programs not yet born (`equity_births`: `elane.birth_seeds`, once
 each, ever). THE EQUITY ROUNDS (`equity_rounds`, on their own thread every `elane.ROUND_SECONDS`): the tournament's
 equity step (Validation, the retirements), then the gate's (the one sealed look), so a version validated in a round
@@ -1113,6 +1114,23 @@ class Swarm:
             log(f"equity evaluator adopted: {adopted.get('families')} equity families owe fresh evidence")
         return adopted
 
+    def adopt_xs(self) -> dict[str, Any] | None:
+        """THE XS IDENTITY's adoption at the start (`evaluator.adopt_xs` with `league.xs.identity.xs_identity()`,
+        release E4): panel families only. None on an error (logged, never stopping the start; `bands.read` judges a
+        panel band against the running release's own files whatever was adopted, so nothing of the panel trades on a
+        stale band)."""
+        try:
+            from ..xs.identity import xs_identity
+            from .evaluator import adopt_xs
+
+            adopted = adopt_xs(self.store, xs_identity())
+        except Exception:  # noqa: BLE001 - never keeps the swarm from starting
+            log(f"xs evaluator adoption failed: {traceback.format_exc()[-600:]}")
+            return None
+        if adopted.get("adopted"):
+            log(f"xs evaluator adopted: {adopted.get('families')} panel families owe fresh evidence")
+        return adopted
+
     def run(self, *, once: bool = False) -> int:
         """The process: seed, start the workers, loop until asked to stop."""
         try:
@@ -1191,6 +1209,7 @@ class Swarm:
         if adopted_evaluator["adopted"]:
             log(f"evaluator adopted: {adopted_evaluator['families']} families owe fresh evidence")
         self.adopt_equity()  # THE EQUITY IDENTITY (release E1): equity families only, beside `adopt`
+        self.adopt_xs()  # THE XS IDENTITY (release E4): panel families only, beside `adopt_equity`
         adopted = self.pool.adopt() if hasattr(self.pool, "adopt") else 0
         self.store.event("swarm.status", None, {"action": "started", "pid": os.getpid(), "release": str(CODE_DIR), "adopted": adopted,
                                                 "families": len(self.store.families(alive=True))})
diff --git a/league/swarm/policy.json b/league/swarm/policy.json
index c00d192f..20e96b83 100644
--- a/league/swarm/policy.json
+++ b/league/swarm/policy.json
@@ -177,11 +177,53 @@
           "A6": []
         },
         "beside": "S2, c_R = 0 (no pooled-t bar), c_H,used = {c_H}; this program's FP at zero edge = {own_fp}% (cap 12%; owner's wall 15%); its holdout-only rate at c_H,used = {honly}% (the bound when 2025 is fully known); drift-kept pass rate = {n1}% (not a false positive: the goal counts direction); S1-X: {alpha|beta} (FP {fpx}%); a pass under S2 is weaker evidence of edge than under S1+F1; contamination: 2025 (all of Validation) and part of the 2026 holdout can be known to the authoring models, so the FP is a property of the procedure over 2010-19 and 2022-24 history, not a guarantee in this one world"
+      },
+      "equity_xs": {
+        "name": "XS1",
+        "screen": "XS1",
+        "receipt_sha256": null,
+        "c_XS": null,
+        "c_margin": null,
+        "alpha_plac": null,
+        "placebo_draws": null,
+        "rung": null,
+        "fp_cap": null,
+        "owner_wall": null,
+        "validation_tries": null,
+        "holdout_looks": null,
+        "retry": false,
+        "flags": {},
+        "screen_flags": [],
+        "beside": null
       }
     },
     "val_tries": 1,
     "looks_per_lineage": 1,
     "program_loss_usd": -300,
+    "panel": {
+      "mode": "off",
+      "panels": [
+        "sp500"
+      ],
+      "birth_share": 0.5,
+      "max_alive": 12,
+      "max_names": 12,
+      "rebalance": [
+        "weekly",
+        "monthly"
+      ],
+      "train_budget": 4,
+      "placebos_train": 200,
+      "cpu_seconds_day": 14400,
+      "run_budget_seconds": 600,
+      "zero_edge_programs": 100,
+      "coverage_min": 0.97,
+      "spreads_min_share": 0.9,
+      "membership_max_stale_days": 45,
+      "universe_max_age_days": 400,
+      "live_min_tradable_share": 0.95,
+      "census_notes": {}
+    },
     "e2": {
       "births_every_seconds": 7200,
       "births_refill_seconds": 1800,
diff --git a/league/swarm/settings.py b/league/swarm/settings.py
index c5808a86..b25a8799 100644
--- a/league/swarm/settings.py
+++ b/league/swarm/settings.py
@@ -524,6 +524,11 @@ DEFAULTS: dict[str, Any] = {
     # carries the code's defaults; `elane.e2.usd_day` is its dollars a UTC day, held to 0-100). The layers merge deep,
     # so swarm.json sets one key of the block at a time, and each key is held inside its bound where it is read
     # (elane_births.py, elane_train.py, elane_review.py, elane_yield.py `cfg`: a malformed value is its default).
+    # RELEASE E4 (the panel lane; league/swarm/elane_xs.py `cfg`, which holds every key inside its bound and reads a
+    # block that is no object as its defaults: "off"): the nested `elane.panel` block, whose switch is
+    # `elane.panel.mode` ("off" | "train" | "gate" | "live"; policy.json ships "off" and the code's defaults), and the
+    # panel screen's pin `elane.screens.equity_xs`, read from the repository's policy.json alone (nulls until the
+    # receipt is landed: with nulls every panel look waits). swarm.json sets one key of `elane.panel` at a time.
     "elane": {"mode": "off"},
     "heartbeat_seconds": 20,
     "stale_heartbeat_seconds": 240,     # the House restarts a swarm whose heartbeat is older than this
```

## Patch 9 (tests): `league/tests/test_elane.py`, `league/tests/test_elane_e2_switch.py`

Two tests of E1 and E2 that iterate every block of `elane.screens`.

WHY: with `elane.screens.equity_xs` in policy.json, `test_elane.Settings
.test_the_policy_layer_holds_the_block_and_the_defaults_hold_its_shape` (it holds the block's keys equal to the two
lanes) and `test_elane_e2_switch.TheScreensName.test_the_text_tells_no_threshold_of_the_screen` (it reads S2's figures
from every block) fail. Each is changed by one statement to read the two lanes' blocks; the panel's pin has its own
tests (`test_elane_xs.NoReceiptNoLook`, `NoThresholdReachesAGenerator`).
```diff
diff --git a/league/tests/test_elane.py b/league/tests/test_elane.py
index 634083f1..703215e2 100644
--- a/league/tests/test_elane.py
+++ b/league/tests/test_elane.py
@@ -103,7 +103,8 @@ class Settings(StoreCase):
         block = layer["elane"]
         self.assertEqual((block["mode"], block["structures"], block["birth_share"], block["roster"], block["val_tries"],
                           block["looks_per_lineage"], block["program_loss_usd"]), ("off", ["etf"], 0.0, 3, 1, 1, -300))
-        self.assertEqual(sorted(block["screens"]), sorted(LANES))
+        # RELEASE E4: beside the two lanes' blocks, the panel screen's pin (league/swarm/elane_xs.py `SCREEN_KEY`).
+        self.assertEqual(sorted(block["screens"]), sorted([*LANES, "equity_xs"]))
         self.assertEqual(elane.cfg({"elane": block})["roster"], 3)
 
     def test_the_roster_equals_the_constitutions_probe_programs(self):
diff --git a/league/tests/test_elane_e2_switch.py b/league/tests/test_elane_e2_switch.py
index 830b9e69..561f3db6 100644
--- a/league/tests/test_elane_e2_switch.py
+++ b/league/tests/test_elane_e2_switch.py
@@ -213,7 +213,9 @@ class TheScreensName(unittest.TestCase):
         # threshold in a prompt would be a target to fit). No sentence that speaks of the screen, Validation or the
         # look holds one of the pinned block's figures, and no text anywhere names one of the receipt's quantities.
         block = policy()["elane"]["screens"]
-        figures = {str(block[lane][key]) for lane in block for key in ("c_H_floor", "c_H_margin", "c_X", "fp_cap", "owner_wall")}
+        # (the two lanes' blocks: the panel screen's pin beside them, release E4, has its own test in test_elane_xs.py)
+        figures = {str(block[lane][key]) for lane in elane.LANES
+                   for key in ("c_H_floor", "c_H_margin", "c_X", "fp_cap", "owner_wall")}
         figures.discard("0.0")
         self.assertEqual(len(figures), 5, figures)
         spoken = 0
```
