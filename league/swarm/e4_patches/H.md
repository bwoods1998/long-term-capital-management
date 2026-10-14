# E4 patches authored by package H

Package H (live) authors patches 12 (`league/equity/kinds.py`, `league/equity/live.py`: plumbing since A13, no identity
moves) and 13 (`league/ops/dlane_report.py`). Patch 12 also adds ONE row to `league/ledger.py` (below: the House's
ledger refuses a kind it does not know, and the book swallows the refusal).

Each diff is exact against the integration head these files had at Step 0 (24a52b11; for these four files that is
0e8bbaa7's bytes). E1 was still moving: EVERY HUNK IS ANCHORED BY A STATEMENT, listed in the tables, so a hunk that no
longer applies is re-made at its statement, never at a line number.

**How to apply.** `git apply` the four fenced diffs in the order kinds.py, live.py, ledger.py, dlane_report.py (each
block is one file's `git diff`). The same bytes are the branch `feat/equity-e4-h-applied` (worktree
`~/Work/ltcm-v3/eqe4-h-applied`, VERIFICATION ONLY, never to be merged as it is): `git diff feat/equity-e4-h
feat/equity-e4-h-applied -- league/equity/kinds.py league/equity/live.py league/ledger.py league/ops/dlane_report.py`
reproduces the blocks below byte for byte. ONE PATCH: kinds.py's `BOOKS` never lands without live.py's hunks
(`test_equity_book_panel.ThePatchIsWhole` fails a tree that has `BOOKS["panel"]` without B8 and B9).

**The tests that hold it** (each SKIPS WHOLE while its patch is absent; after applying, each module must report 0
skipped): `league/tests/test_equity_book_panel.py` (patch 12: 52 tests), `league/tests/test_dlane_report_panel.py` (patch
13: 16 tests); `league/tests/test_xs_book.py` (the adapter, 67 tests) runs with or without the patches. With the patches
applied E1's own book tests pass unchanged (`test_equity_book`, `test_equity_fx_orders`, `test_equity_fx_hooks`,
`test_equity_fx_daily`, `test_equity_e2e`, `test_equity_hooks`, `test_equity_isolation`, `test_equity_identity`,
`test_equity_decider`, `test_ledger`, `test_dlane_report`, `test_dlane_report_equity`): no E1 test was changed.

**What moves.** No identity: `league/equity/live.py`, `kinds.py`, `league/ledger.py` and `league/ops/dlane_report.py`
are in no evidence list and under no `league/live/` or `league/gym/` path (`test_equity_identity` passes on the
patched tree). No money digest. No constitution number.

**With every E4 switch off** the patched book does this and nothing more: at its start it imports `league.xs.book`
(guarded: a failure leaves the panel kind off and the book whole), creates the empty table `eq_rebalances` and adds the
column `eq_instances.kind`; in a minute it calls no function of the adapter, reads no bar and writes no file
(`test_equity_book_panel.NoPanelNoWork`).

## Patch 12: `league/equity/kinds.py`, `league/equity/live.py` (and one row of `league/ledger.py`)

E4-SPEC 10.2's B1-B15, less B7 and B12 (E1 has both since 70948154; `TheCloseRotation` holds E1 to B7 for a basket).

| what | anchor (the statement the hunk sits at) | the change |
|---|---|---|
| kinds | `def module_for(kind: str)` and `__all__` | `BOOKS = {"panel": "league.xs.book"}`, `book_for(kind)`, `kind_of(structure)`; the module names no module of league/xs but by that string |
| B1 | `class Instance` (`why: str = ""`, `row`, `of`); `EquityBook.__init__` after the `SCHEMA` loop; `_sync_instances` where a new `Instance(...)` is made | `Instance.kind` (default "equity"); `eq_instances.kind` by ALTER guarded by PRAGMA table_info (`INSTANCE_KIND_DDL`, the adapter's words: a test holds the two equal); the kind from the row's `structure` through `kinds.kind_of`; the adapter's own table `eq_rebalances` made by `_adapter` |
| B2 | `_drop` (`kind_drop("equity", ...)`), `_ensure_loaded` (`kind_load("equity", ...)`), `_decide` (the jobs, `self.decider.kind("equity", "decide", ...)`, the results loop) | each names `inst.kind`; ONE `decider.kind(kind, "decide", {"jobs": ...})` a kind; the panel answer's `failed`, `missing` and `error` are read by the same lines as the equity kind's |
| B3 | `_decide_step` after `bars = self._day_bars(...)` and at `if live: self._decide(...)`; `_seat_step` at its `fresh` list and its `self._decide(...)` | `_panel_bars` beside the book's own read from 16:20: ONE chunked fetch for the union of the live panel instances' columns; an instance whose fetch is being read (or read again inside the grace) is not asked in that pass and the seating pass asks it for the same close, on the day's kept fetch; with the lane at exits only (no seating pass) the day's decision waits for it instead |
| B4, B15 | new method `_panel_job` | the job `{"key", "inputs", "called", "standing"}` from the adapter; every open lot of the instance marked at session t's raw close BEFORE its inputs are built |
| B5 | `_record_intents` (signature, its `needs`, its `MAX_INTENTS` slice); new method `_panel_record` | `symbols=` and `cap=` (a panel instance's candidates and the adapter's `MAX_INTENTS`); one `eq_rebalances` row a session; the event `equity.rebalance` (counts only) |
| B6, B14 | new method `_panel_ineligible` | the lots the child's answer names `ineligible` exit at the next open, tag "ineligible"; `_house_exits`' own displacement rule, word for word |
| B8 | `_work_entry`, between the `sized.qty <= 0` block and `self._send(...)` | a buy sized with any binding but "intent" while an exit of ITS OWN instance is due waits and is sized again next minute. **EVERY instance, ETF programs too** (E4-SPEC decision 27, for E1's owner): the seeds have no sale in a buy's window, so nothing changes for them; no E1 test changed. AMENDED AT THE SHIP CHECK (after this patch was applied; the diff below is the patch as it was): B8 is the panel kind's alone (`EquityBook._cut_waits`), and a share program's orders are held to main's by a recorded week (`league/xs/E4_INTERFACES.md` section 17) |
| B9 | new method `_panel_record` | a decide recorded after `entry_until` of its exec day plans nothing for the OPEN: status "late", an alarm, one failed decide on a called day; a late row never stands; a CLOSE target is planned as usual; the House's exits as ever |
| B10 | `_record_of`, after its `lots = [...]` | an instance of a kind that is not the book's own: `_panel_record_of` -> the adapter's `date_record` (one observation a close date; SPY on one fetch, only at the daily sync and only once the record holds `sized.min_trades` close dates) |
| B11 | `_audit` after its window check; `_mismatch`'s instance loop; new methods `_panel_audit`, `_panel_mismatch` | the kept file read again at 08:30 by E1's own `_bars_verdict`; a mismatch's cost; E1's own `_mismatch` no longer charges a panel instance for a lot symbol's bars (its bars are judged by its own audit) |
| B13 | new method `_panel_bars` | `adapter.complete`; read again each minute inside `BARS_GRACE_S`, then every `SEAT_RETRY_S`; `last_ask` from `SEAT_RETRY_S` before the next pre-open |
| A17 | `_decide`'s failure branch; `_decide_failed`; new methods `_decide_counts`, `_hold_failed` | a HOLD day the House could not ask is an alarm (critical on the second in a row; kv `eq_hold_failed`) and counts toward no exit; **and a hold day that WAS asked does not reset the count either** (as the Gym: only CALLED decides are counted, failed or not; said in the report as an open point) |
| ledger | `"equity.bars_audit": False,` in `KINDS` | `"equity.rebalance": False` (private). The panel's morning re-read is recorded under the book's own kind `equity.bars_audit` with `"panel": True` and counts only |

Statuses and keys this patch adds to live.sqlite: table `eq_rebalances` (the adapter's `SCHEMA`), column
`eq_instances.kind`, kv `eq_hold_failed` {instance: {day, run}}, intents and closed lots tagged "ineligible" (a House
exit; `_ctx_reason` already reads every reason but "program" and "max_hold" as "house"). Under `<state>/equity-daily/`:
`live-bars/<day>.npz` (the adapter's `keep`, five sessions).

WHAT THE ADAPTER NEEDS OF OTHER PACKAGES, at their Step 0 signatures (the tests stub these at their interface):
package C `store.Universe` (`members`, `aid`, `tradable`, `table`), `store.read_salt`, `run_salt`, `ids_for`,
`dither_key`, `sector_perm`, `ctx.rows_to_arrays`, `ctx.inputs_from_arrays`, `config.decision_due`,
`program.Needs`; package D's child answering "decide" with {hold, target, at, orders, rejects, ineligible, stats,
ctx_sha, failed} per job and reading a job's `called` and `standing` {target {id: w}, at, exited [id]}.

## Patch 13: `league/ops/dlane_report.py`

| what | anchor | the change |
|---|---|---|
| the words | above `EQUITY_DIRECTION` | `PANEL_TAG`, `PANEL_KIND`, `PANEL_LABEL` ("EQUITY (PANEL)": held equal to the adapter's by a test), `PANEL_BY_DATE`, `PANEL_OWED`, `STYLE_OPEN_RULE` |
| the book's rows | `read_book` | `eq_instances.kind` when the column exists; `rebalances` (counts and verdicts of `eq_rebalances`: never a target or a symbol); `spy` (SPY's adjustment=all closes of `eq_bars`) |
| a panel close's label | `equity_closes` | `panel`, and the label "EQUITY (PANEL)" for a lot of a panel program |
| the section | the end of `equity_section`; new `panel_section`, `style_open_passers` | `equity.panel`: per program its distinct close dates, the date-clustered t, P&L, the SPY buy-and-hold on one basis, XS1's sentence, its decisions and their morning re-reads, 10.5's cost sentence; EVERY recorded style-open passer and why it holds no seat (the captain's A22 (1)); its residual and 10.6's rebalance sessions agreed are said OWED (package J), never invented |
| XS1's sentence beside EVERY live panel trade | `EquityScreens.__init__`, `.of`; `trade_screens`' `equity_screen` | for a panel family the screen is "XS1" and the line is the one its look recorded (the look row's detail, else `elane_xs.beside_line`), under the panel's label; none recorded is said, never a crash (package G's lane may not have landed) |

## The diffs

### Patch 12 (1 of 3): `league/equity/kinds.py`

```diff
diff --git a/league/equity/kinds.py b/league/equity/kinds.py
index a45e0715..42219274 100644
--- a/league/equity/kinds.py
+++ b/league/equity/kinds.py
@@ -16,6 +16,11 @@ it may import (`league.live.decider` `runtime_files`): the options decision's ow
 `LEAGUE_FILES`, league/gym's modules, every module of this package and of league/xs). A kind whose module imports
 anything else names it in `RUNTIME`, or the child cannot import it there (league/tests/test_equity_decider.py imports
 every kind's module from such a copy).
+
+THE PARENT SIDE (release E4): `BOOKS` names, for a kind the EquityBook does not run itself, the module the book asks
+on the House's side for that kind's columns, bars, decide jobs, intents and live record (league/equity/live.py
+`_adapter`; "panel" -> league/xs/book.py). It is imported by the book alone, never by the decider or its child, and
+only by name from here: league/equity names no module of league/xs. `kind_of` reads a family's structure as its kind.
 """
 
 from __future__ import annotations
@@ -23,6 +28,7 @@ from __future__ import annotations
 import importlib
 from pathlib import Path
 from types import ModuleType
+from typing import Any
 
 #: kind -> the importable module whose `handle(op, payload, state) -> dict` the child calls. "panel" is a slot (A13):
 #: league/xs/child.py refuses every op until the panel lane is built there.
@@ -38,6 +44,24 @@ RUNTIME: tuple[str, ...] = ("league/__init__.py", "league/safety.py", "league/st
                             "ltcm/data/__init__.py")
 
 
+#: kind -> the importable module of its PARENT side (`book_for`): what the EquityBook asks for a kind that is not its
+#: own. The "equity" kind has none: the book runs it itself.
+BOOKS: dict[str, str] = {"panel": "league.xs.book"}
+
+
+def book_for(kind: str) -> ModuleType | None:
+    """The parent-side module of `kind` (imported once a process), or None for a kind that has none ("equity", and
+    any kind `BOOKS` does not name)."""
+    name = BOOKS.get(kind) if isinstance(kind, str) else None
+    return importlib.import_module(name) if name is not None else None
+
+
+def kind_of(structure: Any) -> str:
+    """The decider kind that runs a family of `structure` (league/swarm/store.py `EQUITY_STRUCTURES`): "panel" for
+    "panel", else "equity"."""
+    return "panel" if structure == "panel" else "equity"
+
+
 def module_for(kind: str) -> ModuleType:
     """The module of `kind` (imported once per child); ValueError for a kind not in `KINDS`."""
     name = KINDS.get(kind) if isinstance(kind, str) else None
@@ -58,4 +82,4 @@ def runtime_files(repo: str | Path) -> list[str]:
     return sorted(out)
 
 
-__all__ = ["KINDS", "RUNTIME", "module_for", "runtime_files"]
+__all__ = ["KINDS", "BOOKS", "RUNTIME", "module_for", "book_for", "kind_of", "runtime_files"]
```

### Patch 12 (2 of 3): `league/equity/live.py`

```diff
diff --git a/league/equity/live.py b/league/equity/live.py
index b26a0255..7b2b10ce 100644
--- a/league/equity/live.py
+++ b/league/equity/live.py
@@ -81,6 +81,19 @@ on); two clean readings lift it. The freeze also blocks options opens (league/li
 EXPORTS: a closed lot goes to the forward record (league/equity/families.py `add_forward`) with net cash, fees,
 dividends, notional, hold and its twin key `eq:<lid>`. A dividend paid after a lot was exported reaches `eq_lots` (which
 the Done meter and the band rules read) but not that forward row.
+
+THE PANEL KIND (release E4, package H; plumbing: no identity moves). An instance's `kind` (`eq_instances.kind`, from its
+family's structure through `kinds.kind_of`) names the decider kind that runs it and, for a kind that is not the book's
+own, the parent-side adapter the book asks (`kinds.BOOKS`: "panel" -> league/xs/book.py, `_adapter`). A panel program
+trades through EVERY rule above (the windows, the sizing, the budget, the day count, reconciliation, the exports); what
+differs is how its decision is made, in the `_panel_*` methods: its columns and ONE chunked fetch for every live panel
+instance from 16:20, read again while a bar is missing (`_panel_bars`); its job, the lots marked first (`_panel_job`);
+its answer recorded as intents with one `eq_rebalances` row a session, a rebalance recorded after the open window's
+entry cut-off planning nothing at the open (`_panel_record`); the lots its child names ineligible exited at the next
+open (`_panel_ineligible`); the bars it read kept and read again at 08:30 (`_panel_audit`); and its record for the band
+rules read one observation a close DATE (`_panel_record_of`). The captain's A17: a HOLD day the House could not ask is
+an alarm and counts toward no exit (`_decide_counts`), nor does a hold day that was asked reset the count. With no
+instance of such a kind none of it runs: no fetch, no file, no call of the adapter but its import and its table.
 """
 
 from __future__ import annotations
@@ -107,9 +120,11 @@ from . import actions as A
 from . import bands as B
 from . import config
 from . import ctx as C
+from . import kinds as K
 from . import program as P
 from . import schedule as S
 from . import sizing as Z
+from .store import STORE_DIR
 
 #: The book's tables (created by `EquityBook.__init__`, one statement at a time through `LiveState.execute`).
 SCHEMA = """
@@ -222,6 +237,20 @@ SEAT_RETRY_S = 600.0
 #: A program's decide: its per-call limit and error budget (the Gym runner's).
 DECIDE_TIMEOUT = 1.0
 DECIDE_MAX_ERRORS = 25
+#: RELEASE E4. The book's own decider kind (league/equity/child.py); an instance of another kind is asked through its
+#: parent-side adapter (`kinds.BOOKS`).
+EQUITY_KIND = "equity"
+#: `eq_instances.kind`, added to a state from before release E4 by this statement, guarded by PRAGMA table_info
+#: (league/xs/book.py `INSTANCE_KIND_DDL` says the same words; a test holds the two equal).
+INSTANCE_KIND = "kind"
+INSTANCE_KIND_DDL = "ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'"
+#: A panel decide first ready this many seconds after `decide_at` is said (a warning: 16:40 ET).
+PANEL_LATE_S = 600.0
+#: A hold day's buys from the standing target that have gone on for this many sessions are said (a warning).
+STANDING_WARN_SESSIONS = 5
+#: A rebalance with more than this share of its orders skipped is said (a warning).
+SKIPPED_WARN_SHARE = 0.10
+_SQL_COMMENT = re.compile(r"--[^\n]*")
 #: How many sessions before a dividend's date the book looks for the holding its quantity names.
 DIVIDEND_LOOKBACK_SESSIONS = 70
 #: Closed lots exported a minute, at most.
@@ -597,6 +626,7 @@ class Instance:
     created_at: float = 0.0
     retired_at: float | None = None
     why: str = ""
+    kind: str = EQUITY_KIND
 
     @property
     def live(self) -> bool:
@@ -607,14 +637,14 @@ class Instance:
                 "run_sha": self.run_sha, "code": self.code, "params": dumps(self.params), "band": self.band,
                 "seeded": int(self.seeded), "max_hold": int(self.max_hold), "failed_decides": int(self.failed_decides),
                 "last_decided_day": self.last_decided_day, "created_at": self.created_at, "retired_at": self.retired_at,
-                "why": self.why[:400]}
+                "why": self.why[:400], "kind": self.kind}
 
     @classmethod
     def of(cls, r: Mapping[str, Any]) -> "Instance":
         return cls(r["id"], r["family"], int(r["version"]), r["lane"], r["run_sha"], r["code"],
                    loads(r["params"], {}) or {}, r["band"], bool(r["seeded"]), int(r["max_hold"]),
                    int(r["failed_decides"] or 0), r["last_decided_day"], float(r["created_at"]), r["retired_at"],
-                   r["why"] or "")
+                   r["why"] or "", str(r.get("kind") or EQUITY_KIND))
 
 
 def instance_key(family: str, version: int) -> str:
@@ -668,6 +698,18 @@ class EquityBook:
             for statement in SCHEMA.split(";"):
                 if statement.strip():
                     self.state.execute(statement)
+            # B1 (release E4): an instance's decider kind. A state from before it gains the column; every row reads
+            # "equity".
+            if INSTANCE_KIND not in {str(r["name"]) for r in self.state.rows("PRAGMA table_info(eq_instances)")}:
+                self.state.execute(INSTANCE_KIND_DDL)
+        #: RELEASE E4: the parent-side adapters by kind (`_adapter`: None for one that cannot be imported), and the
+        #: panel's own memory in this process: the day's columns and fetch (`_panel_bars`), the morning's re-read
+        #: (`_panel_audit`).
+        self._adapters: dict[str, Any] = {}
+        self._panel: dict[str, Any] = {}
+        self._panel_again: dict[str, Any] = {}
+        for kind in K.BOOKS:
+            self._adapter(kind)
         #: instance -> (code sha, params) loaded in the decider child this process; its NEEDS as the child read them.
         self._loaded: dict[str, tuple[str, str]] = {}
         self._needs: dict[str, dict[str, Any]] = {}
@@ -1758,6 +1800,21 @@ class EquityBook:
                 return
             self._finish(intent, "done" if filled_qty > 0 else "refused", f"sizing ({sized.binding}): {sized.reason}")
             return
+        if sized.binding != "intent":
+            # B8 (release E4; EVERY instance, an ETF program's too): A CUT SIZE IS NOT FINAL WHILE AN EXIT OF ITS OWN
+            # PROGRAM MAY STILL FILL. Sent now, the cut size would be the intent's whole target (a re-price sends target
+            # minus filled of the FIRST order): with $40 idle in the sleeve and a $111 sale still working, a $111 buy
+            # would go for $40 and stay there. Any binding but "intent": the sleeve's cash, the House-wide cash, the
+            # invested cap and the budget's room all free up on the same sale. It is sized again each minute and goes
+            # whole once its own program's exits have filled; its cut-off records it missed with this reason.
+            own = [r for r in self._exits_due(today, now, m) if r["instance"] == intent.instance]
+            if own:
+                why = (f"sizing cut ({sized.binding}): {sized.reason}; it waits for {len(own)} exit(s) of its own "
+                       "program still working and is sized again when they fill")
+                if intent.why != why:
+                    intent.why = why
+                    self._save_intent(intent)
+                return
         self._send(intent, side="buy", symbol=symbol, klass=klass, qty=sized.qty, limit=limit, collar=collar, day=today,
                    lid=intent.lid, replaces=current.eid if current is not None else None, probe=inst.band == "probe",
                    why=f"entry ({sized.binding}: {sized.reason})"[:300], tick=now, until=deadline)
@@ -1923,6 +1980,10 @@ class EquityBook:
             self.state.put("eq_synced", day)
         live = [i for i in self._instances(alive=True) if i.live]
         bars = self._day_bars(now, t, mt, live, live, out)
+        # B3 (release E4): the panel instances' own bars, read beside the book's from 16:20. While their fetch is
+        # being read, or read again for a missing bar inside the grace, they are not asked in this pass (the seating
+        # pass asks them for the same close once it is whole); the book's own programs do not wait for it.
+        panel = self._panel_bars(now, t, mt, mn, [i for i in live if i.kind != EQUITY_KIND], out)
         if bars is None:
             return
         if (self.state.get("eq_synced") or "") != day and self._unconfirmed_day != day:
@@ -1931,8 +1992,11 @@ class EquityBook:
             self.alert("warning", f"equity: the families could not be read for the band sync of {day} "
                                   f"({out.get('families') or 'no reading'}): no band moved and nobody was retired; the "
                                   "programs the book holds decide as they are")
-        if live:
-            self._decide(t, live, bars, now, out)
+        if (panel or {}).get("wait") and not et.enabled:
+            return      # (exits only: no seating pass will ask them later, so the day's decision waits for their bars)
+        ask = [i for i in live if i.kind == EQUITY_KIND or not (panel or {}).get("wait")]
+        if ask:
+            self._decide(t, ask, bars, now, out, panel=panel)
         self._house_exits(t, now)
         record = {"day": day, "status": "done", "at": now,
                   "instances": sorted(i.id for i in live if i.last_decided_day == day)}
@@ -1959,17 +2023,24 @@ class EquityBook:
         live = [i for i in self._instances(alive=True) if i.live]
         day = t.isoformat()
         counted = self.state.get("eq_failed", {}) or {}
+        # (A17: a hold day the House could not ask is tried again on the same clock, though it is counted nowhere.)
+        tried = {**{k: (v or {}).get("day") for k, v in (self.state.get("eq_hold_failed", {}) or {}).items()}, **counted}
         again = mn is None or now < mn.preopen
-        fresh = [i for i in live if i.id not in handled and (again or counted.get(i.id) != day)]
+        fresh = [i for i in live if i.id not in handled and (again or tried.get(i.id) != day)]
         if not fresh:
             return
-        if all(counted.get(i.id) == day for i in fresh) and now - self._seat_tried < SEAT_RETRY_S:
+        if all(tried.get(i.id) == day for i in fresh) and now - self._seat_tried < SEAT_RETRY_S:
             return
         bars = self._day_bars(now, t, mt, live, fresh, out, held=False)
+        panel = self._panel_bars(now, t, mt, mn, [i for i in fresh if i.kind != EQUITY_KIND], out)
         if bars is None:
             return
+        if (panel or {}).get("wait"):
+            fresh = [i for i in fresh if i.kind == EQUITY_KIND]
+            if not fresh:
+                return
         self._seat_tried = now
-        self._decide(t, fresh, bars, now, out)
+        self._decide(t, fresh, bars, now, out, panel=panel)
         asked = sorted(set(handled) | {i.id for i in fresh if i.last_decided_day == day})
         if asked != sorted(handled):
             record = {k: v for k, v in done.items() if k != "why"}
@@ -2083,7 +2154,8 @@ class EquityBook:
             if inst is None:
                 inst = Instance(key, str(row["family"]), int(row["version"]), str(row.get("lane") or ""),
                                 str(row.get("run_sha") or ""), str(row.get("code") or ""), params, str(row["band"]),
-                                bool(row.get("seeded")), holds[1], created_at=now)
+                                bool(row.get("seeded")), holds[1], created_at=now,
+                                kind=K.kind_of(row.get("structure")))
                 since.setdefault(key, {"band": inst.band, "day": day})
                 self.record("equity.instance", {"instance": key, "band": inst.band, "lane": inst.lane}, agent=inst.family)
             elif late:
@@ -2159,7 +2231,7 @@ class EquityBook:
         self._loaded.pop(inst.id, None)
         self._needs.pop(inst.id, None)
         try:
-            self.decider.kind_drop("equity", inst.id)
+            self.decider.kind_drop(inst.kind, inst.id)
         except Exception:  # noqa: BLE001 - a dropped program is never asked again either way
             pass
 
@@ -2169,9 +2241,9 @@ class EquityBook:
         if self._loaded.get(inst.id) == sig:
             return True
         try:
-            answer = self.decider.kind_load("equity", inst.id, {"code": inst.code, "params": inst.params,
-                                                                 "name": inst.family, "timeout": DECIDE_TIMEOUT,
-                                                                 "max_errors": DECIDE_MAX_ERRORS})
+            answer = self.decider.kind_load(inst.kind, inst.id, {"code": inst.code, "params": inst.params,
+                                                                  "name": inst.family, "timeout": DECIDE_TIMEOUT,
+                                                                  "max_errors": DECIDE_MAX_ERRORS})
         except Exception as exc:  # noqa: BLE001 - refused or the child failed: this decide fails
             self._needs.pop(inst.id, None)
             inst.why = f"load: {type(exc).__name__}: {str(exc)[:200]}"
@@ -2254,8 +2326,10 @@ class EquityBook:
         if changed:
             self._mismatch(day, changed, now, where="read again for a later decide")
 
-    def _decide(self, t: dt.date, live: Sequence[Instance], bars: Mapping[str, Any], now: float, out: dict) -> None:
-        """One "decide" request for every live instance whose bars and program are ready; its intents recorded.
+    def _decide(self, t: dt.date, live: Sequence[Instance], bars: Mapping[str, Any], now: float, out: dict, *,
+                panel: Mapping[str, Any] | None = None) -> None:
+        """One "decide" request a kind for every live instance whose bars and program are ready; its intents recorded.
+        `panel`: the day's panel bars (`_panel_bars`), for the instances of a kind that is not the book's own.
 
         ONCE A SESSION: an instance already asked for the day (`last_decided_day`, written in its intents' own
         transaction) is skipped, so a decide that runs again (an error or a restart after one instance's commit and
@@ -2267,7 +2341,13 @@ class EquityBook:
         (`missing`) or could not build the ctx (`error`): the instance may be asked again for the same close
         (`_seat_step`). THE PROGRAM FAILED: its answer says `failed` (league/equity/child.py: the runner's
         `last_failed`: it raised, ran past its limit or is disqualified), which is exactly what the Gym engine counts
-        (league/equity/engine.py `decide`); the session is spent as in the Gym (`last_decided_day` moves, no intent)."""
+        (league/equity/engine.py `decide`); the session is spent as in the Gym (`last_decided_day` moves, no intent).
+
+        A PANEL INSTANCE (release E4) is asked through its own kind with the job its adapter builds (`_panel_job`), and
+        its answer's `failed`, `missing` and `error` are read exactly as the equity kind's. The captain's A17: on a HOLD
+        day (its program is not called) a decide the House could not make is an alarm and counts toward no exit
+        (`_decide_counts`, `_hold_failed`), and a hold day that was asked does not reset the count either: as in the
+        Gym, only CALLED decides are counted, failed or not."""
         day = t.isoformat()
         jobs, failed, meta = [], {}, {}
         asked = [inst for inst in live if inst.last_decided_day != day]
@@ -2276,6 +2356,14 @@ class EquityBook:
                 failed[inst.id] = inst.why or "the program did not load"
                 continue
             needs = self._needs[inst.id]
+            if inst.kind != EQUITY_KIND:
+                try:
+                    job, meta[inst.id] = self._panel_job(inst, t, needs, panel, now)
+                except Exception as exc:  # noqa: BLE001 - its bars, its columns or its ctx: the House could not ask
+                    failed[inst.id] = f"ctx: {type(exc).__name__}: {str(exc)[:200]}"
+                    continue
+                jobs.append((inst.kind, job))
+                continue
             symbols = [str(s).upper() for s in needs.get("symbols") or []]
             missing = [s for s in symbols if s not in set(bars.get("present") or ())]
             if missing:
@@ -2286,19 +2374,20 @@ class EquityBook:
             except Exception as exc:  # noqa: BLE001 - the bars or the book cannot make its ctx: a failed decide
                 failed[inst.id] = f"ctx: {type(exc).__name__}: {str(exc)[:200]}"
                 continue
-            jobs.append({"key": inst.id, "inputs": inputs})
+            jobs.append((EQUITY_KIND, {"key": inst.id, "inputs": inputs}))
             meta[inst.id] = bars_sha
         results: dict[str, Any] = {}
-        if jobs:
+        for kind in sorted({k for k, _ in jobs}):
+            batch = [job for k, job in jobs if k == kind]
             try:
-                answer = self.decider.kind("equity", "decide", {"jobs": jobs})
+                answer = self.decider.kind(kind, "decide", {"jobs": batch})
                 if answer.get("ok"):
-                    results = dict(answer.get("results") or {})
+                    results.update(answer.get("results") or {})
                 else:
-                    for job in jobs:
+                    for job in batch:
                         failed[job["key"]] = f"the decider: {str(answer.get('error') or 'failed')[:200]}"
             except Exception as exc:  # noqa: BLE001
-                for job in jobs:
+                for job in batch:
                     failed[job["key"]] = f"the decider: {type(exc).__name__}: {str(exc)[:200]}"
         counted = dict(self.state.get("eq_failed", {}) or {})
         decided, spent, fresh = [], {}, []
@@ -2317,9 +2406,11 @@ class EquityBook:
                     said = result.get("why") or "it raised, ran past its limit or is disqualified"
                     spent[inst.id] = f"its own decide failed: {str(said)[:200]}"
             why = failed.get(inst.id) or spent.get(inst.id)
+            other = inst.kind != EQUITY_KIND
             if why is not None:
+                counts = self._decide_counts(inst, t)
                 with self.state.transaction():
-                    if counted.get(inst.id) != day:
+                    if counts and counted.get(inst.id) != day:
                         inst.failed_decides += 1
                         counted[inst.id] = day
                         fresh.append(inst.id)
@@ -2328,13 +2419,35 @@ class EquityBook:
                         inst.last_decided_day = day
                     inst.why = f"decide {day}: {why}"[:400]
                     self._save_instance(inst)
+                    if other:
+                        self._panel_failed(inst, t, why, result if inst.id in spent else None, meta.get(inst.id), now,
+                                           counts=counts)
                 failed[inst.id] = why
                 continue
+            late = None
             with self.state.transaction():
-                n = self._record_intents(inst, t, list(result.get("intents") or []), result.get("ctx_sha"),
-                                         meta.get(inst.id))
-                inst.failed_decides, inst.last_decided_day, inst.why = 0, day, ""
+                if other:
+                    n, late = self._panel_record(inst, t, result, meta[inst.id], now)
+                else:
+                    n = self._record_intents(inst, t, list(result.get("intents") or []), result.get("ctx_sha"),
+                                             meta.get(inst.id))
+                if late is not None:
+                    # B9: a called rebalance recorded after the open window's entry cut-off planned nothing: one failed
+                    # decide, and the session is spent.
+                    if counted.get(inst.id) != day:
+                        inst.failed_decides += 1
+                        counted[inst.id] = day
+                        fresh.append(inst.id)
+                        self.state.put("eq_failed", counted)
+                    inst.last_decided_day, inst.why = day, f"decide {day}: {late}"[:400]
+                elif other and not meta[inst.id]["called"]:
+                    inst.last_decided_day, inst.why = day, ""      # a hold day neither counts nor resets (A17)
+                else:
+                    inst.failed_decides, inst.last_decided_day, inst.why = 0, day, ""
                 self._save_instance(inst)
+            if late is not None:
+                failed[inst.id] = late
+                continue
             decided.append(f"{inst.id}: {n}")
         out["decided"] = decided
         if failed:
@@ -2401,11 +2514,16 @@ class EquityBook:
         shas = (bars.get("shas") or {})
         return inputs, _sha({s: shas.get(s) for s in symbols})
 
-    def _record_intents(self, inst: Instance, t: dt.date, intents: Sequence[Any], ctx_sha: Any, bars_sha: Any) -> int:
+    def _record_intents(self, inst: Instance, t: dt.date, intents: Sequence[Any], ctx_sha: Any, bars_sha: Any, *,
+                        symbols: Sequence[str] | None = None, cap: int | None = None) -> int:
         """The program's intents as `eq_intents` rows for the next session (each checked here again: a malformed one
-        is recorded refused, the program reads why in its next ctx's rejects)."""
+        is recorded refused, the program reads why in its next ctx's rejects). `symbols` and `cap` (B5, release E4): what
+        a panel instance may buy that day (its columns' candidates, where an equity program's are its NEEDS symbols) and
+        its adapter's cap on a session's intents."""
         day, exec_day, now = t.isoformat(), S.next_session(t).isoformat(), self.clock()
         needs = [str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []]
+        if symbols is not None:
+            needs = [str(s).upper() for s in symbols]
         lots = {lot.lid: lot for lot in self._lots(instance=inst.id)}
         selling: set[int] = set()
         n = 0
@@ -2419,7 +2537,7 @@ class EquityBook:
                                      bars_sha=bars_sha, created_at=now, updated_at=now, **values))
             n += 1
 
-        for raw in list(intents)[:config.MAX_INTENTS]:
+        for raw in list(intents)[:config.MAX_INTENTS if cap is None else int(cap)]:
             if not isinstance(raw, Mapping):
                 add("buy", "refused", "an intent that is not a dict")
                 continue
@@ -2514,7 +2632,8 @@ class EquityBook:
         day = t.isoformat()
         counted = dict(self.state.get("eq_failed", {}) or {})
         for inst in self._instances(alive=True):
-            if inst.live and inst.last_decided_day != day and counted.get(inst.id) != day:
+            if inst.live and inst.last_decided_day != day and counted.get(inst.id) != day \
+                    and self._decide_counts(inst, t):
                 inst.failed_decides += 1
                 counted[inst.id] = day
                 inst.why = f"decide {day}: {why}"[:400]
@@ -2524,6 +2643,490 @@ class EquityBook:
         self.state.put("eq_decide", {"day": day, "status": "failed", "at": now, "why": why})
         self.alert("warning", f"equity: the decide of {day} failed: {why}")
 
+    # ------------------------------------------------------------------ the panel kind (release E4, package H)
+    def _adapter(self, kind: str) -> Any:
+        """The parent-side adapter of a decider kind that is not the book's own (`kinds.BOOKS`: "panel" ->
+        league/xs/book.py), imported once and its table made beside the book's (`adapter.SCHEMA`: `eq_rebalances`).
+        None for a kind that has none, or whose adapter cannot be imported: its instances then fail their decides (the
+        House could not ask) and nothing else of the book is touched."""
+        if kind not in self._adapters:
+            adapter = None
+            try:
+                adapter = K.book_for(kind)
+                if adapter is not None:
+                    with self.state.lock:
+                        for statement in _SQL_COMMENT.sub("", adapter.SCHEMA).split(";"):
+                            if statement.strip():
+                                self.state.execute(statement)
+            except Exception as exc:  # noqa: BLE001 - that kind stays off; the book itself goes on
+                adapter = None
+                self._error(f"adapter {kind}", exc, {})
+            self._adapters[kind] = adapter
+        return self._adapters[kind]
+
+    def _rebalances(self, instance: str) -> list[dict]:
+        return self.state.rows("SELECT * FROM eq_rebalances WHERE instance=? ORDER BY decided_day, rid", (instance,))
+
+    def _decide_counts(self, inst: Instance, t: dt.date) -> bool:
+        """THE CAPTAIN'S A17: whether a decide of session t that failed counts toward A8.5's exit for this instance.
+        Always for the book's own kind. For a panel program only a CALLED decide counts (a failed decide on a rebalance
+        day); a HOLD day the House could not ask is an alarm (`_hold_failed`) and counts toward no exit. A program
+        whose schedule cannot be read (it did not load) counts, as before."""
+        if inst.kind == EQUITY_KIND:
+            return True
+        adapter = self._adapter(inst.kind)
+        if adapter is None or getattr(adapter, "HOLD_DAY_FAILS_EXIT", True):
+            return True
+        if inst.id not in self._needs:
+            self._ensure_loaded(inst)
+        needs = self._needs.get(inst.id)
+        if not needs:
+            return True
+        try:
+            return bool(adapter.called(t, needs))
+        except Exception:  # noqa: BLE001 - a schedule that cannot be read is read as a called day
+            return True
+
+    def _hold_failed(self, inst: Instance, day: str, why: str) -> None:
+        """A hold day the House could not ask (A17): said once a day, critical on the second session in a row, and kept
+        (kv `eq_hold_failed` {instance: {day, run}}) so the seating pass asks again on its own clock. Its lots stay:
+        the max-hold exits still run, and nothing else is sold."""
+        notes = dict(self.state.get("eq_hold_failed", {}) or {})
+        last = notes.get(inst.id) or {}
+        if last.get("day") == day:
+            return
+        try:
+            row = last.get("day") == S.previous_session(day).isoformat()
+        except ValueError:
+            row = False
+        run = int(last.get("run") or 0) + 1 if row else 1
+        notes[inst.id] = {"day": day, "run": run}
+        self.state.put("eq_hold_failed", notes)
+        self.alert("error" if run >= 2 else "warning",
+                   f"equity: {inst.id} could not be asked on the hold day {day} ({why[:200]}): its lots stay as they are "
+                   f"and no failed decide is counted (A17){'; the second session in a row' if run >= 2 else ''}")
+
+    def _panel_held(self, inst: Instance, adapter: Any, day: str) -> dict[str, str]:
+        """{symbol: the day its lot was opened} of the instance's lots open now, or closed since its last called
+        decision: the names that keep a column whatever the index says of them today."""
+        last = adapter.last_called(self._rebalances(inst.id), before=day)
+        return {lot.symbol: lot.opened_day for lot in self._lots(instance=inst.id, open_only=False)
+                if lot.status != LOT_CLOSED or (lot.exit_day or "") > last}
+
+    def _panel_bars(self, now: float, t: dt.date, mt: S.Moments, mn: S.Moments | None, asked: Sequence[Instance],
+                    out: dict) -> dict[str, Any] | None:
+        """THE PANEL'S BARS OF SESSION t (B3, B11, B13), for a decide of `asked` (None when it asks no panel instance:
+        nothing is read). Each asked instance's columns (`adapter.columns`: the day's members and the names its lots
+        hold), then ONE chunked fetch for the union of every panel instance's columns seen that day, a few chunks a
+        minute (`adapter.fetch`); the day's kept file is used instead when it holds them (a restart, a program seated
+        since). The answer: {adapter, cols {instance: Columns}, union, fetched, sha, failed {instance: why}} and
+        - `ready`: the fetch may be decided on (`adapter.complete`); it is KEPT then (`adapter.keep`: the bytes a
+          decision read; the morning re-read and the nightly I6 compare it);
+        - `wait`: it is still being read, or a bar is missing inside `BARS_GRACE_S` of `decide_at`: read again each
+          minute, the panel instances are not asked this pass;
+        - else `why`: past the grace the instances fail (the House could not ask) and the seating pass asks again every
+          `SEAT_RETRY_S` until the next pre-open. FROM THE LAST ASK BEFORE IT (`SEAT_RETRY_S` before the pre-open) a
+          held name may be among the adapter's few missing names: it is then read as the Gym reads a store with no bar."""
+        if not asked:
+            return None
+        day = t.isoformat()
+        if self._panel.get("day") != day:
+            self._panel = {"day": day, "cols": {}, "failed": {}, "progress": {}, "union": None, "fetched": None,
+                           "ok": False, "missing": [], "kept": False, "sha": None, "told": set()}
+        state = self._panel
+        state.update(wait=False, ready=False, why=None)
+        adapter = state["adapter"] = self._adapter(asked[0].kind)
+        if adapter is None or self.root is None:
+            state["why"] = ("the panel adapter cannot be imported" if adapter is None
+                            else "the book has no state root: the panel's universe cannot be read")
+            return state
+        root = self.root / STORE_DIR
+        for inst in asked:
+            if inst.id in state["cols"] or not self._ensure_loaded(inst):
+                continue
+            try:
+                state["cols"][inst.id] = adapter.columns(root, inst.id, t, held=self._panel_held(inst, adapter, day))
+                state["failed"].pop(inst.id, None)
+            except Exception as exc:  # noqa: BLE001 - that instance's decide fails; the others go on
+                state["failed"][inst.id] = f"columns: {type(exc).__name__}: {str(exc)[:200]}"
+        if not state["cols"]:
+            state["why"] = "no panel instance's columns could be built"
+            return state
+        union = adapter.union(list(state["cols"].values()))
+        if state["union"] is None or state["union"].symbols != union.symbols:
+            state.update(union=union, fetched=None, ok=False, kept=False, sha=None, progress={})
+            kept = adapter.kept(root, t)
+            if kept is not None and set(union.symbols) <= set(kept[0]):
+                state.update(fetched=adapter.view(kept[1], kept[0], union), kept=True)
+        state["union"] = union
+        held = [lot for lot in self._lots() if lot.instance in state["cols"]]
+        last_ask = mn is not None and now >= mn.preopen - SEAT_RETRY_S
+        if state["fetched"] is not None:
+            state["ok"], state["missing"] = adapter.complete(state["fetched"], union, held, last_ask=last_ask)
+        reading = False
+        if not state["ok"]:
+            try:
+                got = adapter.fetch(self.market, union, t, progress=state["progress"], now=self.clock)
+            except Exception as exc:  # noqa: BLE001 - read again next minute from the chunk it stopped at
+                got = None
+                self._error("panel bars", exc, out)
+            if got is None:
+                reading = bool(state["progress"])
+            else:
+                state.update(fetched=got, kept=False, sha=None, progress={})
+                state["ok"], state["missing"] = adapter.complete(got, union, held, last_ask=last_ask)
+        if not state["ok"]:
+            missing = list(state["missing"])
+            if reading or now < mt.decide_at + BARS_GRACE_S:
+                state["wait"] = True
+                out["panel_bars"] = ("reading the panel's bars" if reading or state["fetched"] is None else
+                                     f"waiting for {len(missing)} of the panel's bars")
+            else:
+                state["why"] = (f"the panel's bars of {day} are not whole: {len(missing)} missing"
+                                f" ({', '.join(missing[:5])}{', ...' if len(missing) > 5 else ''})")
+            return state
+        fetched, missing = state["fetched"], list(state["missing"])
+        late = bool(last_ask and missing)
+        fetched = adapter.Fetched(fetched.days, fetched.raw, fetched.all,
+                                  {**dict(fetched.meta), "missing": len(missing), "late": late})
+        state["fetched"] = fetched
+        if not state["kept"]:
+            try:
+                adapter.keep(root, t, fetched, union.symbols)
+                state["kept"] = True
+            except Exception as exc:  # noqa: BLE001 - a decision whose bars cannot be kept is not made
+                state["why"] = f"the panel's bars of {day} could not be kept: {type(exc).__name__}: {str(exc)[:160]}"
+                return state
+            state["sha"] = None
+        if state["sha"] is None:
+            state["sha"] = adapter.bars_sha(fetched, union)
+        state["ready"] = True
+        if late and "late" not in state["told"]:
+            state["told"].add("late")
+            self.alert("warning", f"equity: the panel's bars of {day} were decided on late and incomplete at the last ask: "
+                                  f"{len(missing)} names had no bar and are read as not eligible")
+        if now >= mt.decide_at + PANEL_LATE_S and "slow" not in state["told"]:
+            state["told"].add("slow")
+            if any(i.last_decided_day != day for i in asked):
+                self.alert("warning", f"equity: the panel's bars of {day} were ready more than "
+                                      f"{int(PANEL_LATE_S // 60)} minutes after the decide's moment")
+        return state
+
+    def _panel_job(self, inst: Instance, t: dt.date, needs: Mapping[str, Any], panel: Mapping[str, Any] | None,
+                   now: float) -> tuple[dict[str, Any], dict[str, Any]]:
+        """A panel instance's decide job (B4) and what its record needs: {"key", "inputs", "called", "standing"}. EVERY
+        OPEN LOT OF THE INSTANCE IS MARKED FIRST at session t's raw close (B15: on a day only panel programs decide
+        nothing else would mark it, and the sleeve's free cash, the invested cap and the loss budget's open risk read
+        the mark; as the book's own, a late decide never marks a lot bought since the close). `called`: its program is
+        asked today (D9); on every other close no program code runs and `standing` carries the last planned target's
+        names still to buy (absent: a hold). Raises when the panel's bars are not ready or its columns are not built."""
+        if panel is None or not panel.get("ready"):
+            raise RuntimeError((panel or {}).get("why") or "the panel's bars are not ready")
+        adapter, cols = panel["adapter"], panel["cols"].get(inst.id)
+        if cols is None:
+            raise RuntimeError(panel["failed"].get(inst.id) or "its columns were not built")
+        day = t.isoformat()
+        fetched = adapter.view(panel["fetched"], panel["union"].symbols, cols)
+        clock = self.clock()
+        with self.state.transaction():
+            lots = {lot.lid: lot for lot in self._lots(instance=inst.id)}
+            for lid, close in adapter.marks(fetched, cols, list(lots.values()), t).items():
+                lots[lid].mark, lots[lid].marked_at = close, clock
+                self._save_lot(lots[lid])
+        lots = self._lots(instance=inst.id)
+        every = self._lots(instance=inst.id, open_only=False)
+        rows = self._rebalances(inst.id)
+        last = adapter.last_called(rows, before=day)
+        closed = [lot for lot in every if lot.status == LOT_CLOSED and (lot.exit_day or "") > last]
+        rejects: list[str] = []
+        if last:
+            for r in rows:
+                if last <= str(r["decided_day"]) < day:
+                    rejects.extend(str(why) for _, why in (loads(r["skipped"], []) or []) if why)
+            rejects.extend(r["why"] for r in self.state.rows(
+                "SELECT why FROM eq_intents WHERE instance=? AND status IN ('refused', 'missed') AND decided_day>=? "
+                "AND decided_day<? ORDER BY iid", (inst.id, last, day)) if r["why"])
+        E = self.sizing_equity() or ZERO
+        budget = self._sleeve_share(inst) * E if self._et() is not None else ZERO
+        own_value = sum((lot.value for lot in lots), ZERO)
+        cash = max(ZERO, budget - own_value)
+        is_called = bool(adapter.called(t, needs))
+        standing = None
+        if not is_called:
+            pending = [r["symbol"] for r in self.state.rows(
+                "SELECT symbol FROM eq_intents WHERE instance=? AND kind='buy' AND status IN ('planned', 'sent')",
+                (inst.id,)) if r["symbol"]]
+            standing = adapter.standing(rows, cols, every, t, pending=pending)
+        params = needs.get("_params") if needs.get("_params") is not None else inst.params
+        job = {"key": inst.id, "called": is_called,
+               "inputs": adapter.inputs(cols, fetched, day=t, needs=needs, lots=lots, closed=closed,
+                                        rejects=rejects[:20], cash=cash, equity=cash + own_value, budget=budget,
+                                        params=params)}
+        if standing is not None:
+            job["standing"] = standing
+        info = {"cols": cols, "called": is_called, "standing": standing, "equity": cash + own_value, "budget": budget,
+                "bars_sha": adapter.bars_sha(fetched, cols), "fetch": {**dict(fetched.meta), "sha": panel.get("sha")},
+                "lots": {lot.lid: lot for lot in lots}}
+        return job, info
+
+    def _panel_ineligible(self, inst: Instance, t: dt.date, answer: Mapping[str, Any] | None, adapter: Any) -> int:
+        """B6, B14: the open lots of the instance its child's answer names `ineligible` (their name is not in the
+        eligible set at session t's close: it left the index, lost its bar, or cannot be traded; `league.xs.ctx
+        .ineligible`, read at EVERY close, called or not, exactly as the Gym's engine reads it) exit at the next open,
+        tagged `adapter.INELIGIBLE`. `_house_exits`' own rule applies as it stands: an exit of the House at the open
+        displaces the program's planned close sell of the lot, and the program's own open sell or an exit already
+        planned stands."""
+        day, nxt = t.isoformat(), S.next_session(t).isoformat()
+        n = 0
+        for lid in (answer or {}).get("ineligible") or []:
+            try:
+                lot = self._lot(int(lid))
+            except (TypeError, ValueError):
+                continue
+            if lot is None or lot.instance != inst.id or lot.status == LOT_CLOSED:
+                continue
+            pending = [Intent.of(r) for r in self.state.rows(
+                "SELECT * FROM eq_intents WHERE lid=? AND kind IN ('sell', 'house_exit') AND status IN "
+                "('planned', 'sent') ORDER BY iid", (int(lot.lid),))]
+            yields = [i for i in pending if i.kind == "sell" and i.status == "planned" and i.at == "close"]
+            if len(yields) != len(pending):
+                continue
+            why = f"its name is not eligible at the close of {day} (it left the index, lost its bar or cannot be traded)"
+            for intent in yields:
+                self._finish(intent, "refused", f"lot {lot.lid} leaves at the open by the House's rule "
+                                                f"({adapter.INELIGIBLE}: {why})"[:300])
+            self._plan_exit(lot, exec_day=nxt, at="open", reason=adapter.INELIGIBLE, why=why, decided_day=day)
+            n += 1
+        return n
+
+    def _panel_record(self, inst: Instance, t: dt.date, answer: Mapping[str, Any], info: Mapping[str, Any],
+                      now: float) -> tuple[int, str | None]:
+        """A panel instance's answer recorded (B5): its child's orders as intents (`adapter.intents`, at most
+        `adapter.MAX_INTENTS`, a buy only of one of the day's candidates), the lots it names ineligible exited at the
+        next open (`_panel_ineligible`), and ONE `eq_rebalances` row for the session, its `equity.rebalance` event
+        counts only. Returns (the intents recorded, why it is a failed decide or None).
+
+        B9, A REBALANCE RECORDED LATE: when session t's decide is recorded after `entry_until` (09:45 ET) of its exec
+        day (the House was down overnight), a target for the OPEN, called or standing, plans no sell and no buy: its
+        sells would go all day and every buy would be missed at a cut-off already past, leaving the sleeve in cash for
+        a week or a month. The row's status is "late", the owner is told, it is one failed decide when it was a called
+        day, and the standing target is the one before (a late row never stands). A target for the CLOSE is planned as
+        usual, and the House's own exits are planned as ever."""
+        adapter = self._adapter(inst.kind)
+        cols, lots = info["cols"], list(info["lots"].values())
+        day, nxt = t.isoformat(), S.next_session(t)
+        called, standing = bool(info["called"]), info.get("standing")
+        hold = bool(answer.get("hold")) or not isinstance(answer.get("target"), Mapping)
+        at = str(answer.get("at") or (standing or {}).get("at") or "open")
+        orders = adapter.intents(answer, cols, lots)
+        skipped = adapter.skipped(answer, cols, lots)
+        status = "planned" if called and not hold else "hold"
+        target = answer.get("target") if called and not hold else (None if called else (standing or {}).get("target"))
+        mn = S.moments(nxt, self._offsets())
+        why, failed = None, None
+        if mn is not None and self.clock() >= mn.entry_until and at == "open" and (status == "planned" or orders):
+            status = "late"
+            why = (f"recorded after the open window's entry cut-off of {nxt.isoformat()}: a target for the open plans "
+                   "nothing, and the standing target is the one before")
+            failed = why if called else None
+            skipped = skipped + [["", "the rebalance was recorded late: nothing planned at the open"]] * bool(orders)
+            orders = []
+            self.alert("warning", f"equity: {inst.id}'s {'rebalance' if called else 'standing target'} of {day} was {why}")
+        n = 0
+        if orders:
+            ref = len(cols.symbols) - len(cols.ids)
+            candidates = [s for s in cols.symbols[ref:] if s not in cols.extra]
+            n = self._record_intents(inst, t, orders, answer.get("ctx_sha"), info.get("bars_sha"), symbols=candidates,
+                                     cap=adapter.MAX_INTENTS)
+        n += self._panel_ineligible(inst, t, answer, adapter)
+        row = adapter.rebalance_row(
+            instance=inst.id, family=inst.family, version=inst.version, decided_day=day, exec_day=nxt.isoformat(), at=at,
+            called=called, targets=adapter.target_pairs(target, cols), standing=bool(not called and orders),
+            intents=orders, skipped=skipped, equity=info.get("equity"), budget=info.get("budget"), cols=cols,
+            ctx_sha=answer.get("ctx_sha"), bars_sha=info.get("bars_sha"), fetch=info.get("fetch") or {}, status=status,
+            why=why, now=now)
+        self.state.upsert("eq_rebalances", row, "instance, decided_day")
+        self.record("equity.rebalance", adapter.event(row), agent=inst.family)
+        notes = dict(self.state.get("eq_hold_failed", {}) or {})
+        if notes.pop(inst.id, None) is not None:
+            self.state.put("eq_hold_failed", notes)
+        planned = row["n_sells"] + row["n_buys"]
+        if row["n_skipped"] and row["n_skipped"] > SKIPPED_WARN_SHARE * (planned + row["n_skipped"]) and status != "late":
+            self.alert("warning", f"equity: {inst.id}'s decision of {day} skipped {row['n_skipped']} of "
+                                  f"{planned + row['n_skipped']} orders")
+        if row["standing"]:
+            run = 0
+            for r in reversed(self._rebalances(inst.id)):
+                if not int(r["standing"] or 0):
+                    break
+                run += 1
+            if run == STANDING_WARN_SESSIONS:
+                self.alert("warning", f"equity: {inst.id}'s standing target has had a buy still to make for {run} "
+                                      "sessions in a row")
+        return n, failed
+
+    def _panel_failed(self, inst: Instance, t: dt.date, why: str, answer: Mapping[str, Any] | None,
+                      info: Mapping[str, Any] | None, now: float, *, counts: bool) -> None:
+        """A panel decide that failed, for the record: its `eq_rebalances` row ("failed"; a later ask of the same close
+        that succeeds writes over it), the lots its child still named ineligible exited (a program whose own decide
+        failed was asked: the House's exits do not wait on it), the hold day's alarm when it counts toward no exit
+        (A17), and the critical word when its failed called decides reach the exit rule."""
+        adapter = self._adapter(inst.kind)
+        if adapter is None:
+            return
+        day = t.isoformat()
+        info = info or {}
+        try:
+            if answer is not None:
+                self._panel_ineligible(inst, t, answer, adapter)
+            row = adapter.rebalance_row(
+                instance=inst.id, family=inst.family, version=inst.version, decided_day=day,
+                exec_day=S.next_session(t).isoformat(), at="open", called=bool(info.get("called", counts)), targets=[],
+                standing=False, intents=[], skipped=[], equity=info.get("equity"), budget=info.get("budget"),
+                cols=info.get("cols"), ctx_sha=(answer or {}).get("ctx_sha"), bars_sha=info.get("bars_sha"),
+                fetch=info.get("fetch") or {}, status="failed", why=why, now=now)
+            self.state.upsert("eq_rebalances", row, "instance, decided_day")
+        except Exception as exc:  # noqa: BLE001 - the record's trouble never undoes the count
+            self._error(f"panel failed {inst.id}", exc, {})
+        if not counts:
+            self._hold_failed(inst, day, why)
+        elif inst.failed_decides >= self._holds()[3]:
+            self.alert("error", f"equity: {inst.id} has failed {inst.failed_decides} called decides in a row: its lots "
+                                "exit at the next open")
+
+    def _panel_audit(self, now: float, m: S.Moments, out: dict) -> None:
+        """B11, THE BARS A PANEL DECISION READ ARE READ AGAIN before the next open, beside the book's own audit: for
+        the last session's `eq_rebalances` rows that read bars and have no verdict, the day's kept symbols are fetched
+        again (ONE chunked fetch for every instance, a few chunks a minute) and compared with the kept file
+        (`adapter.same`, by `_bars_verdict`: the book's own rule and tolerance). No price differs: "ok" (a volume that
+        went on counting and a bar served late are notes). A PRICE DIFFERS in a symbol among a row's columns:
+        "mismatch", and that decision pays what the book's own pays (`_panel_mismatch`). Not read by the pre-open, no
+        kept file, or a kept file that is not the one a row read: "unread", a warning. A decision recorded after the
+        audit's moment (a late ask) has no morning re-read: its `audit` stays NULL, and the report counts it."""
+        if not _has_table(self.state.rows, "eq_rebalances"):
+            return
+        t = S.previous_session(m.day)
+        day = t.isoformat()
+        rows = self.state.rows("SELECT * FROM eq_rebalances WHERE decided_day=? AND audit IS NULL AND bars_sha IS NOT NULL "
+                               "AND created_at<? ORDER BY rid", (day, m.audit_at))
+        if not rows:
+            self._panel_again = {}
+            return
+        inst = self._instance(rows[0]["instance"])
+        adapter = self._adapter(inst.kind if inst is not None and inst.kind != EQUITY_KIND else next(iter(K.BOOKS)))
+
+        def unread(some: Sequence[Mapping[str, Any]], why: str) -> None:
+            for r in some:
+                self.state.execute("UPDATE eq_rebalances SET audit='unread' WHERE rid=?", (r["rid"],))
+            self.alert("warning", f"equity: the panel's bars of {day} were not read again for {len(some)} decisions ({why})")
+
+        kept = adapter.kept(self.root / STORE_DIR, t) if adapter is not None and self.root is not None else None
+        if kept is None:
+            unread(rows, "no kept fetch can be read")
+            return
+        symbols, old = kept
+        if self._panel_again.get("day") != day:
+            self._panel_again = {"day": day, "progress": {}}
+        try:
+            again = adapter.fetch(self.market, symbols, t, progress=self._panel_again["progress"], now=self.clock)
+        except Exception as exc:  # noqa: BLE001 - again next minute; unread at the pre-open is a warning only
+            again = None
+            out["panel_audit"] = f"{type(exc).__name__}: {str(exc)[:120]}"
+        if again is None:
+            if now >= m.preopen:
+                unread(rows, out.get("panel_audit") or "the read was not finished by the pre-open")
+                self._panel_again = {}
+            return
+        self._panel_again = {}
+        sha = adapter.bars_sha(old, symbols)
+        diff = adapter.same(old, again, symbols, verdict=_bars_verdict)
+        bad, drift, late = list(diff.get("mismatch") or []), list(diff.get("volume") or []), list(diff.get("late") or [])
+        extras = {r["rid"]: set(loads(r["extra"], []) or []) for r in rows}
+        every_extra = set().union(*extras.values()) if extras else set()
+        stale, hit, clean = [], [], 0
+        for r in rows:
+            if (loads(r["fetch"], {}) or {}).get("sha") != sha:
+                stale.append(r)
+                continue
+            mine = [s for s in bad if s not in every_extra or s in extras[r["rid"]]]
+            if mine:
+                hit.append(r["instance"])
+                self._panel_mismatch(r, mine, now)
+            else:
+                clean += 1
+                self.state.execute("UPDATE eq_rebalances SET audit='ok' WHERE rid=?", (r["rid"],))
+        if stale:
+            unread(stale, "the kept fetch is not the one they read")
+        if drift or late:
+            out["panel_bars_volume"] = f"{len(drift)} volumes and {len(late)} late bars differ (notes: the prices agree)"
+        # (Counts only, under the book's own kind: a panel event names no symbol.)
+        self.record("equity.bars_audit", {"day": day, "panel": True, "symbols": len(symbols), "mismatch": len(bad),
+                                          "volume": len(drift), "late": len(late), "ok": clean, "hit": len(hit),
+                                          "unread": len(stale)})
+
+    def _panel_mismatch(self, row: Mapping[str, Any], bad: Sequence[str], now: float) -> None:
+        """What it costs when the bars a panel decision read differ, in a price, from the morning's reading: the book's
+        own cost of a mismatch (A8.11, A8.5: the alarm, that decision's planned buys cancelled, one failed decide a
+        session) and one thing of the panel's: its planned `ineligible` exits of the differing symbols are cancelled
+        too (the lot stays; the next close judges it again). A17: on a hold day's row it is the hold day's alarm and
+        counts toward no exit. A row marked so never stands as the standing target (`adapter.standing`)."""
+        day, key = str(row["decided_day"]), str(row["instance"])
+        inst = self._instance(key)
+        adapter = self._adapter(inst.kind if inst is not None and inst.kind != EQUITY_KIND else next(iter(K.BOOKS)))
+        names = f"{', '.join(list(bad)[:5])}{', ...' if len(bad) > 5 else ''}"
+        with self.state.transaction():
+            self.state.execute("UPDATE eq_rebalances SET audit='mismatch' WHERE rid=?", (row["rid"],))
+            for r in self.state.rows("SELECT * FROM eq_intents WHERE instance=? AND decided_day=? AND status='planned' "
+                                     "AND (kind='buy' OR (kind='house_exit' AND tag=?))",
+                                     (key, day, getattr(adapter, "INELIGIBLE", "ineligible"))):
+                intent = Intent.of(r)
+                if intent.kind == "buy" or intent.symbol in set(bad):
+                    self._finish(intent, "canceled", f"the bars of {day} read again differ ({len(bad)} symbols)")
+            if inst is not None and inst.retired_at is None:
+                counts = bool(int(row["called"] or 0)) or getattr(adapter, "HOLD_DAY_FAILS_EXIT", True)
+                counted = dict(self.state.get("eq_failed", {}) or {})
+                if counts and counted.get(key) != day:
+                    inst.failed_decides += 1
+                    counted[key] = day
+                    self.state.put("eq_failed", counted)
+                inst.why = f"bars audit {day}: {len(bad)} symbols differ"
+                self._save_instance(inst)
+        self.alert("error", f"equity: the bars {key}'s decision of {day} read differ when read again for {len(bad)} "
+                            f"symbols ({names}): that decision's buys are canceled")
+
+    def _panel_record_of(self, kind: str, key: str, lots: Sequence[Lot], row: Mapping[str, Any] | None,
+                         refetch: bool) -> Any:
+        """B10, THE LIVE RULES READ A PANEL PROGRAM BY CLOSE DATE (league/xs/book.py `date_record`; pre-registered in
+        docs/operations.md before any panel program trades): `bands.edm1` and `bands.sized_up` are unchanged, as
+        functions and as numbers; what they are fed is one return and one twin gap a close DATE (five lots bought on
+        one date and sold on another share one market move and one fill minute), EDM1's sigma the Validation run's sd
+        per close date, and the same-risk buy-and-hold the lots' dollars held in SPY, every close from ONE fetch, read
+        only by the daily band sync (`refetch`) and only once the record holds the close dates sizing up needs. Raises
+        when the adapter cannot be imported (no band moves on a record that cannot be read)."""
+        adapter = self._adapter(kind)
+        if adapter is None:
+            raise RuntimeError(f"the {kind} adapter cannot be imported: its record cannot be read")
+        et = self._et()
+        since = (self.state.get("eq_band_since", {}) or {}).get(key) or {}
+        probe_sessions = 0
+        if since.get("band") in LIVE_BANDS and since.get("day"):
+            probe_sessions = S.sessions_between(since["day"], S.ny_day(self.clock()).isoformat())
+        try:
+            twins = self.families.twins() if hasattr(self.families, "twins") else {}
+        except Exception:  # noqa: BLE001
+            twins = {}
+        spy = None
+        dates = {lot.exit_day for lot in lots if lot.exit_day and lot.entry_notional > 0}
+        if refetch and et is not None and len(dates) >= int(et.sized_min_trades):
+            span = adapter.spy_span(lots)
+            if span is not None:
+                spy = adapter.spy_closes(self.market, *span)
+        rec = adapter.date_record(lots, twins or {}, spy)
+        return B.EquityRecord(n=int(rec["n"]), returns=tuple(rec["returns"]), pnl=rec["pnl"], bh_pnl=rec["bh_pnl"],
+                              probe_sessions=probe_sessions, realized_net=rec["realized_net"],
+                              twin_gaps_bp=tuple(rec["twin_gaps_bp"]),
+                              validation_r_sd=(row or {}).get("validation_r_sd"))
+
     # ------------------------------------------------------------------ the morning audit (A8.11)
     def _audit(self, now: float, m: S.Moments | None, out: dict) -> None:
         """The last decision's bars fetched again before the next open and compared (`_bars_verdict`): the raw open,
@@ -2538,6 +3141,10 @@ class EquityBook:
         marked."""
         if m is None or not (m.audit_at <= now < m.open_send):
             return
+        try:
+            self._panel_audit(now, m, out)      # B11 (release E4): the bars the panel decisions read, beside the book's
+        except Exception as exc:  # noqa: BLE001 - the book's own audit goes on
+            self._error("panel audit", exc, out)
         decision = dict(self.state.get("eq_decision") or {})
         if not decision or decision.get("audit") or decision.get("day") != S.previous_session(m.day).isoformat():
             return
@@ -2618,7 +3225,8 @@ class EquityBook:
                             "are canceled")
         hit = []
         for inst in self._instances(alive=True):
-            if inst.last_decided_day != day:
+            # (A panel instance read none of these bars: its own are judged by `_panel_audit`.)
+            if inst.last_decided_day != day or inst.kind != EQUITY_KIND:
                 continue
             symbols_of = {str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []}
             planned = [Intent.of(r) for r in self.state.rows(
@@ -2980,6 +3588,11 @@ class EquityBook:
         key = instance_key(family, version)
         lots = [Lot.of(r) for r in self.state.rows(
             "SELECT * FROM eq_lots WHERE instance=? AND status='closed' ORDER BY closed_at, lid", (key,))]
+        inst = self._instance(key)
+        kind = inst.kind if inst is not None else K.kind_of((row or {}).get("structure"))
+        if kind != EQUITY_KIND:
+            # B10 (release E4): a panel program's record is read ONE OBSERVATION A CLOSE DATE.
+            return self._panel_record_of(kind, key, lots, row, refetch)
         returns = tuple(float(lot.cash / lot.entry_notional) for lot in lots if lot.entry_notional > 0)
         et = self._et()
         refetch = bool(refetch and et is not None and len(returns) >= int(et.sized_min_trades))
@@ -3133,7 +3746,8 @@ def _as_of_equal(old_raw: Mapping[str, tuple], old_all: Mapping[str, tuple], fre
     return True
 
 
-__all__ = ["SCHEMA", "WORKING", "TERMINAL", "LOT_OPEN", "LOT_CLOSING", "LOT_CLOSED", "REAL_SUFFIX", "SHARE_TOLERANCE",
+__all__ = ["SCHEMA", "EQUITY_KIND", "INSTANCE_KIND", "INSTANCE_KIND_DDL", "WORKING", "TERMINAL", "LOT_OPEN", "LOT_CLOSING",
+           "LOT_CLOSED", "REAL_SUFFIX", "SHARE_TOLERANCE",
            "CLIENT_PREFIX", "client_id", "ProbeFigures", "probe_figures", "expected_shares_rows", "working_buys_worst",
            "orders_today", "invested", "EquityBook", "Lot", "Order", "Intent", "Instance", "instance_key", "order_body",
            "limit_for", "collar_for", "export_row", "qty_text", "HOUSE_REASONS", "EXIT_KINDS"]
```

### Patch 12 (3 of 3): `league/ledger.py`

```diff
diff --git a/league/ledger.py b/league/ledger.py
index be83023f..1b291c76 100644
--- a/league/ledger.py
+++ b/league/ledger.py
@@ -176,6 +176,7 @@ KINDS: dict[str, bool] = {
     "equity.decide": False,     # a session's decide: the programs decided and the ones that failed
     "equity.bars": False,       # the bars a decision read (their provenance sha in eq_bars)
     "equity.bars_audit": False,  # the morning re-fetch of a decision's bars agreed or did not
+    "equity.rebalance": False,  # a panel program's decision of a session: counts and its status, never a name (E4)
     "equity.band": False,       # the book moved an equity family between candidate, probe and sized
     "equity.instance": False,   # an equity program instance started, updated or retired
     "equity.house_exits": False,  # the House's exit rules planned lots out (max hold, demotion, failed decides)
```

### Patch 13: `league/ops/dlane_report.py`

```diff
diff --git a/league/ops/dlane_report.py b/league/ops/dlane_report.py
index 362f54c8..65d6dbf4 100644
--- a/league/ops/dlane_report.py
+++ b/league/ops/dlane_report.py
@@ -165,6 +165,12 @@ THE GOAL OF OCT 10, 2026 AND THE EQUITY LANES (release E1; the captain's design
 - P(DONE | ZERO EDGE) IS THE OPTIONS RULES' FIGURE (`ZERO_EDGE_EQUITY_NOTE`): it was never measured for share closes,
   and a delta-one lane's is far higher. A report that holds an equity close says so on the figure and in each
   checkpoint's `equity` block; no figure for the equity lanes is stated.
+- THE PANEL LANE (release E4; `panel_section`, `equity.panel`): a panel program's close is an equity close under the
+  label EQUITY (PANEL); beside EVERY live panel trade rides XS1's sentence, the line its program's one look recorded
+  (`EquityScreens.xs1`); beside its closes the distinct close dates and the date-clustered t (A14: one observation a
+  close date), its same-risk buy-and-hold in SPY, its decisions and their morning re-reads, and what reading by date
+  costs; and every recorded style-open passer with why it holds no seat (the captain's A22, `style_open_passers`). Its
+  residual and its twin's agreement are the forward record's, owed (`PANEL_OWED`). None of it is a rule.
 
 Standard library only, except the Probe envelope's figures (`fast_lane.probe_budget` and `real.probe_figures` read
 `league.live.real`, whose Gym legs need numpy, as the House box has): they are an `error` entry where that cannot load.
@@ -215,6 +221,28 @@ ZERO_EDGE_LABEL = "P(Done | zero edge), simulation"
 DONE_FROM = "2026-10-10T04:00:00Z"
 #: An equity close's key: `eq:<lid>` (league/ops/twins.py `equity_key`, the book's export `twin_key`).
 EQUITY_PREFIX = "eq:"
+#: RELEASE E4, THE PANEL LANE: a panel program's lots carry the panel decision's tag (league/xs/book.py `TAG`), its
+#: instance the kind "panel" (`eq_instances.kind`), and every figure of it the label `PANEL_LABEL` (that module's `LABEL`;
+#: a test holds the three equal, so this module imports nothing of league/xs to say them).
+PANEL_TAG = "xs"
+PANEL_KIND = "panel"
+PANEL_LABEL = "EQUITY (PANEL)"
+#: What rides beside a panel program's close dates (the captain's A14; E4-SPEC 10.5).
+PANEL_BY_DATE = (
+    "A panel program is read ONE OBSERVATION A CLOSE DATE: five lots bought on one date and sold on another share one "
+    "market move and one fill minute. Done's meter counts a closed lot as one close; the distinct close dates and the "
+    "date-clustered t ride beside it.")
+#: What the forward record owes a panel program (package J, after release E3), said wherever a figure of it is missing.
+PANEL_OWED = (
+    "owed: a panel program's residual against its matched cells and its shadow twin (the rebalance sessions agreed) are "
+    "the forward record's, which does not read a panel program yet (package J, after release E3). Until it does a panel "
+    "program is recorded and NOT shadowed, and none takes a live seat (the lane's mode \"live\" reads as \"gate\").")
+#: THE CAPTAIN'S A22 (1), said beside every recorded style-open passer.
+STYLE_OPEN_RULE = (
+    "A22: a STYLE-OPEN program takes no live seat on an XS1 pass alone. The House reads each panel program's loadings on "
+    "size, beta, 12-1 momentum and volatility from its Train holdings by one fixed rule; a no-skill tilt to a style that "
+    "won the holdout passes XS1 far above the owner's wall, so such a passer is recorded and shadowed, never seated. The "
+    "forward route is its way to a seat.")
 #: PROFIT FROM MARKET DIRECTION, said plainly beside every equity close and checkpoint (the goal of Oct 10, item 4).
 EQUITY_DIRECTION = (
     "Profit from market direction counts and is said plainly: a long ETF or stock lot earns what its symbol did over the "
@@ -616,7 +644,7 @@ def read_book(live_path: str | Path) -> dict[str, list[dict[str, Any]]]:
 
     path = Path(live_path)
     if not path.exists():
-        return {"positions": [], "instances": [], "lots": [], "eq_instances": []}
+        return {"positions": [], "instances": [], "lots": [], "eq_instances": [], "rebalances": [], "spy": []}
 
     def read(db: Any) -> dict[str, list[dict[str, Any]]]:
         tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
@@ -631,7 +659,19 @@ def read_book(live_path: str | Path) -> dict[str, list[dict[str, Any]]]:
                           ) if "eq_lots" in tables else []
         eq_instances = guard.rows(db, "SELECT id, family, version, lane, band, seeded, created_at, retired_at FROM "
                                       "eq_instances") if "eq_instances" in tables else []
-        return {"positions": positions, "instances": instances, "lots": lots, "eq_instances": eq_instances}
+        # RELEASE E4 (the panel lane; a book from before it has neither): each instance's decider kind, the panel
+        # decisions' COUNTS and verdicts (never a target or a symbol of one), and SPY's adjustment=all closes as the
+        # book fetched them (the same-risk buy-and-hold of a panel program).
+        if eq_instances and guard.rows(db, "SELECT 1 FROM pragma_table_info('eq_instances') WHERE name='kind'"):
+            kinds = {r["id"]: r["kind"] for r in guard.rows(db, "SELECT id, kind FROM eq_instances")}
+            eq_instances = [{**r, "kind": kinds.get(r["id"])} for r in eq_instances]
+        rebalances = guard.rows(db, "SELECT instance, decided_day, called, standing, status, audit, n_sells, n_buys, "
+                                    "n_skipped FROM eq_rebalances ORDER BY decided_day, rid"
+                                ) if "eq_rebalances" in tables else []
+        spy = guard.rows(db, "SELECT day, c, sha FROM eq_bars WHERE symbol='SPY' AND adjustment='all' ORDER BY day"
+                         ) if "eq_bars" in tables else []
+        return {"positions": positions, "instances": instances, "lots": lots, "eq_instances": eq_instances,
+                "rebalances": rebalances, "spy": spy}
 
     return guard.read(path, read)
 
@@ -718,10 +758,12 @@ def equity_closes(lots: Sequence[Mapping[str, Any]], *, since: float, seeded: It
         posted = isinstance(info, Mapping) and info.get("fee_basis") == "broker"
         priced = cash is not None and notional is not None and notional > 0
         lane = str(lot.get("lane") or "") or None
+        panel = _is_panel_lot(lot)
         out.append({"pid": f"{EQUITY_PREFIX}{lid}", "lid": lid, "family": family, "instance": instance,
                     "version": version_of(instance) if version_of(instance) is not None else _int(lot.get("version")),
                     "route": "d2_real" if real else "agent_other", "code": ROUTE_CODES["d2_real"] if real else None,
-                    "house": False, "equity": True, "lane": lane, "label": lane_label(lane), "seeded": family in seeded,
+                    "house": False, "equity": True, "lane": lane, "panel": panel,
+                    "label": PANEL_LABEL if panel else lane_label(lane), "seeded": family in seeded,
                     "closed_at": closed_at, "day": str(lot.get("exit_day") or "") or _ny_day(closed_at),
                     "opened_day": str(lot.get("opened_day") or ""), "opened_at": _num(lot.get("opened_at")),
                     "root": str(lot.get("symbol") or "").upper(), "symbol": str(lot.get("symbol") or "").upper(),
@@ -844,9 +886,150 @@ def equity_section(book: Mapping[str, Any], every: Sequence[Mapping[str, Any]],
                            "EDM1 demotes past 15 bp a side over 5 priced closes"},
         "seeded": sorted(seeded), "seeded_note": elane.SEEDED_NOTE,
         "options_probe_room": options_probe_room((unit or {}).get("equity_usd")),
+        # RELEASE E4: the panel lane's own lines (None while no panel program exists).
+        "panel": panel_section(book, twins, screens, unit=unit),
     }
 
 
+# ------------------------------------------------------------------------------------------------- the panel lane
+def _panel_instances(book: Mapping[str, Any]) -> set[str]:
+    return {str(r.get("id")) for r in book.get("eq_instances") or [] if str(r.get("kind") or "") == PANEL_KIND}
+
+
+def _is_panel_lot(lot: Mapping[str, Any], instances: Iterable[str] = ()) -> bool:
+    """Whether an `eq_lots` row is a panel program's: its instance is of the panel kind, or its buy carried the panel
+    decision's tag (league/xs/book.py `TAG`: a lot keeps its intent's tag)."""
+    return str(lot.get("tag") or "") == PANEL_TAG or str(lot.get("instance") or "") in set(instances)
+
+
+def _look_records(look: Any) -> list[Mapping[str, Any]]:
+    """A family state's recorded look as rows: the record itself, or one a version when it is kept by version."""
+    if not isinstance(look, Mapping):
+        return []
+    if "passed" in look or "seat" in look:
+        return [look]
+    return [{**v, "version": v.get("version", k)} for k, v in look.items() if isinstance(v, Mapping)]
+
+
+def style_open_passers(store: Any) -> list[dict[str, Any]]:
+    """THE CAPTAIN'S A22 (1), reported: every panel program that PASSED its XS1 look and holds no seat because the
+    House reads it style-open (the look's record says `seat` "style-open": league/swarm/elane_xs.py `look`), each with
+    why (`league.xs.style.seat_refusal` of its Train record's style verdict, `elane_xs.style_of`; the look's own word
+    when the rule cannot be read here). Read-only; an unreadable store or lane is an empty list."""
+    try:
+        from ..swarm import elane_xs
+    except Exception:  # noqa: BLE001 - no panel lane in this tree: nobody passed
+        return []
+    out = []
+    try:
+        families = every_family(store)
+    except Exception:  # noqa: BLE001
+        return []
+    for fam in families:
+        if not isinstance(fam, Mapping) or str(fam.get("structure") or "") != PANEL_KIND:
+            continue
+        for rec in _look_records((fam.get("state") or {}).get(elane_xs.LOOK_KEY)):
+            if not rec.get("passed") or rec.get("seat") != elane_xs.SEAT_STYLE:
+                continue
+            why = None
+            try:
+                from ..xs import style
+
+                why = style.seat_refusal(elane_xs.style_of(fam, _int(rec.get("version"))))
+            except Exception:  # noqa: BLE001 - the look's own word stands
+                why = None
+            out.append({"family": str(fam.get("id")), "version": _int(rec.get("version")), "passed": True, "seat": None,
+                        "why": str(why or rec.get("why") or rec.get("seat_why") or "style-open"),
+                        "look_at": rec.get("at"), "shadow": PANEL_OWED})
+    return sorted(out, key=lambda r: (r["family"], r["version"] or 0))
+
+
+def _one_basis(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal] | None:
+    """{day: SPY's adjustment=all close} from the book's `eq_bars` rows of ONE fetch (the latest day's series `sha`:
+    two fetches straddling an ex-date are not one series); None when there is none."""
+    rows = [r for r in rows if r.get("day") and r.get("sha")]
+    if not rows:
+        return None
+    sha = max(rows, key=lambda r: str(r["day"]))["sha"]
+    out = {str(r["day"]): _dec(r.get("c")) for r in rows if r["sha"] == sha}
+    return {d: c for d, c in out.items() if c is not None and c > 0} or None
+
+
+def panel_section(book: Mapping[str, Any], twins: Mapping[str, Mapping[str, Any]], screens: "EquityScreens", *,
+                  unit: Mapping[str, Any] | None = None, constitution: Mapping[str, Any] | None = None
+                  ) -> dict[str, Any] | None:
+    """THE PANEL LANE in the report (release E4; E4-SPEC 10.5 and 10.6, the captain's A14 and A22): None while no
+    panel program has a lot, an instance or a recorded style-open pass. Else, under the label `PANEL_LABEL`:
+    - `programs`: per live or traded panel instance: its lots open and closed, THE DISTINCT CLOSE DATES and THE
+      DATE-CLUSTERED t beside them (A14: `league.xs.book.date_record`, `date_t`: one observation a close date, as the
+      book's band rules read it), its net P&L, the same-risk buy-and-hold IN SPY over its lots' own sessions on one
+      basis (`bh_spy_usd`; None with `bh_why` while the book holds no single SPY series over them), XS1's sentence
+      (`xs1`: the line its look recorded, stated beside EVERY live panel trade), its decisions by status and their
+      morning re-reads by verdict (`audits`: "none" counts the decisions recorded after 08:30, which have none), and
+      10.5's cost sentence (`cost`);
+    - `residual_x` and `rebalance_sessions_agreed`: its residual against its matched cells and its twin's agreement on
+      rebalance sessions are the forward record's (package J, owed): None, with `PANEL_OWED` said;
+    - `style_open`: every recorded style-open passer and why it holds no seat (`style_open_passers`), under A22's rule.
+    Never a rule: nothing here is read by a band, a seat or the Done meter."""
+    instances = _panel_instances(book)
+    lots = [lot for lot in book.get("lots") or [] if _is_panel_lot(lot, instances)]
+    passers = style_open_passers(screens.store)
+    keys = sorted(instances | {str(lot.get("instance") or "") for lot in lots})
+    if not keys and not passers:
+        return None
+    if constitution is None:
+        from ..constitution import CONSTITUTION as constitution  # noqa: N811
+    em = (constitution or {}).get("equity_money") or {}
+    demotion = em.get("demotion") or {} if isinstance(em, Mapping) else {}
+    share = _dec(((em.get("probe") or {}) if isinstance(em, Mapping) else {}).get("sleeve_share"))
+    e = _dec((unit or {}).get("equity_usd"))
+    sleeve = share * e if share is not None and e is not None else None
+    try:
+        from ..xs import book as xs_book
+    except Exception as exc:  # noqa: BLE001 - a laptop without numpy: the lane's figures are not read, and it is said
+        xs_book, unread = None, f"the panel adapter cannot be imported here ({type(exc).__name__}): figures not read"
+    else:
+        unread = None
+    spy = _one_basis(book.get("spy") or [])
+    by_instance: dict[str, dict[str, dict[str, int]]] = {}
+    for r in book.get("rebalances") or []:
+        slot = by_instance.setdefault(str(r.get("instance")), {"decisions": {}, "audits": {}})
+        status = str(r.get("status") or "none")
+        slot["decisions"][status] = slot["decisions"].get(status, 0) + 1
+        if r.get("status") != "failed":
+            audit = str(r.get("audit") or "none")
+            slot["audits"][audit] = slot["audits"].get(audit, 0) + 1
+    programs = {}
+    for key in keys:
+        mine = [lot for lot in lots if str(lot.get("instance") or "") == key]
+        family = str(mine[0].get("family") if mine else key.split("@", 1)[0])
+        version = version_of(key)
+        row: dict[str, Any] = {
+            "family": family, "version": version, "label": PANEL_LABEL,
+            "open_lots": sum(1 for lot in mine if str(lot.get("status") or "") in ("open", "closing")),
+            "closed_lots": sum(1 for lot in mine if str(lot.get("status") or "") == "closed"),
+            "close_dates": None, "date_t": None, "pnl_usd": None, "bh_spy_usd": None, "bh_why": None,
+            "residual_x": None, "rebalance_sessions_agreed": None, "owed": PANEL_OWED,
+            "xs1": screens.of(family, version),
+            "decisions": dict(sorted((by_instance.get(key) or {}).get("decisions", {}).items())),
+            "audits": dict(sorted((by_instance.get(key) or {}).get("audits", {}).items())), "cost": None}
+        if xs_book is None:
+            row["why"] = unread
+        else:
+            rec = xs_book.date_record(mine, twins, spy)
+            t = xs_book.date_t(rec["returns"])
+            row.update(close_dates=rec["n"], date_t=None if t is None else round(t, 4), pnl_usd=_usd(rec["pnl"]),
+                       bh_spy_usd=_usd(rec["bh_pnl"]) if rec["bh_pnl"] is not None else None,
+                       bh_why=None if rec["bh_pnl"] is not None else
+                       "the book holds no single SPY series over its lots' sessions yet (the band sync reads one once "
+                       "sizing up needs it: 10.5)",
+                       cost=xs_book.cost_sentence(min_dates=demotion.get("min_trades", 10),
+                                                  loss_usd=demotion.get("program_loss_usd", "-300"), sleeve_usd=sleeve))
+        programs[key] = row
+    return {"label": PANEL_LABEL, "rule": PANEL_BY_DATE, "programs": programs, "style_open": passers,
+            "style_open_rule": STYLE_OPEN_RULE, "owed": PANEL_OWED}
+
+
 def equity_yield(store: Any, settings: Mapping[str, Any] | None) -> dict[str, Any]:
     """RELEASE E2: the equity lanes' model routes (league/swarm/elane_yield.py `report`): births, Train passes, Validation
     entries, looks passed and live programs per route, each per dollar, and the equity review's own rows. The operator's
@@ -1905,8 +2088,10 @@ def trade_screens(store: Any, lanes: Lanes, settings: Mapping[str, Any] | None,
     screens = screens if screens is not None else EquityScreens(store)
 
     def equity_screen(family: str, version: int | None, lane: Any) -> dict[str, Any]:
-        # AN EQUITY TRADE (release E1, A9 and A11): beside it, the screen's line its program's one look recorded.
-        return {**screens.of(family, version), "lane": lane, "label": lane_label(lane)}
+        # AN EQUITY TRADE (release E1, A9 and A11): beside it, the screen's line its program's one look recorded. A
+        # PANEL TRADE (release E4): XS1's sentence, under the panel's own label.
+        row = screens.of(family, version)
+        return {**row, "lane": lane, "label": PANEL_LABEL if row.get("panel") else lane_label(lane)}
 
     closes_rows = [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "version": c["version"],
                     "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
@@ -1950,6 +2135,21 @@ class EquityScreens:
         self.store = store
         self.looks: dict[tuple[str, int], Mapping[str, Any]] | None = None
         self.states: dict[str, Mapping[str, Any]] = {}
+        self.panels: dict[str, Mapping[str, Any] | None] = {}
+
+    def xs1(self, family: str) -> str | None:
+        """RELEASE E4: XS1's sentence of a panel family (the pinned pre-registration's 10.2, filled for the program and
+        recorded with its one look: league/swarm/elane_xs.py `beside_line`), or None when it took no look or the lane
+        cannot be read here."""
+        fam = self.panels.get(family)
+        if fam is None:
+            return None
+        try:
+            from ..swarm import elane_xs
+
+            return elane_xs.beside_line(fam) or None
+        except Exception:  # noqa: BLE001 - none is stated, and the row says so
+            return None
 
     def of(self, family: str, version: Any) -> dict[str, Any]:
         if self.looks is None:
@@ -1966,6 +2166,8 @@ class EquityScreens:
             except Exception:  # noqa: BLE001 - an unreadable family has no recorded look
                 fam = None
             self.states[family] = ((fam or {}).get("state") or {}) if isinstance(fam, Mapping) else {}
+            self.panels[family] = fam if isinstance(fam, Mapping) and str(fam.get("structure") or "") == PANEL_KIND \
+                else None
         from ..swarm import elane
 
         lane_labels = set(elane.LABELS.values())
@@ -1986,6 +2188,15 @@ class EquityScreens:
                # `label` is the lane's.
                "s1x": detail.get("s1x") if detail.get("s1x") is not None else verdict.get("label"),
                "lane_label": detail.get("label") if detail.get("label") in lane_labels else None}
+        if self.panels.get(family) is not None:
+            # A PANEL PROGRAM (release E4): the screen is XS1 and the line is its receipt's sentence, stated beside
+            # EVERY live panel trade (the pre-registration's duty 3), under the panel's own label.
+            beside = beside or self.xs1(family)
+            out.update(screen=out.get("screen") or "XS1", beside=beside, lane_label=PANEL_LABEL, panel=True)
+            if not beside:
+                out["fp_why"] = ("no XS1 sentence is recorded at this panel program's look (league/swarm/elane_xs.py "
+                                 "records it with the look): none is stated")
+            return out
         if not beside:
             out["fp_why"] = ("no screen line is recorded at this version's look (league/swarm/elane.py records it with the "
                              "look): none is stated")
```
