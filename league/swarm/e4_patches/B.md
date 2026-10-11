# E4 patches authored by package B

Package B (costs and counts) authors patch 11 (`league/ops/funnel.py`, `league/ops/twins.py`) and, AFTER release E3 is merged and never before, patch 18 (`league/ops/contam_probe.py`).

Each patch below: its number in `README.md`, the file, the anchor (a statement, never a line number), the exact
unified diff against the integration head, and the test that holds it.

HOW THEY WERE CHECKED. The four diffs below are ONE change: applied together on package B's branch
(`feat/equity-e4-b`) they are the commit at the head of `feat/equity-e4-b-trial` (a trial branch, kept only as the
proof and never merged as a branch; its one commit can be cherry-picked instead of applying the diffs). On that tree
`test_equity_neff`, `test_equity_spreads`, `test_french`, `test_equity_twins`, `test_close_twins`, `test_ops_stall`,
`test_dlane_report`, `test_dlane_report_equity`, `test_dlane_gate_entries`, `test_dlane_integration`,
`test_equity_fx_swarm`, `test_swarm_f1_research`, `test_site_window`, `test_equity_isolation`, `test_ci` and
`test_e4_stubs` pass on Python 3.14 and on Python 3.11. To apply by hand: `git apply` each block (or all four at once).
THE LOGIC LIVES IN PACKAGE B'S OWN MODULES (`league/ops/equity_neff.py` `funnel_rows`, `league/ops/equity_spreads.py`
`panel_half_spread`), which are tested on the package's branch without these patches; each patch is the few lines
that call them, and each degrades to "as before release E4" without the panel's files.

The tests that hold the patches are ADDED TO PACKAGE B'S OWN TEST FILES BY THE PATCH (they cannot pass before the
patched file exists, so they are not on the package's branch): apply a patch's test diff with its code diff, never one
without the other.

---

## Patch 11a. `league/ops/funnel.py`: independent asset-years beside simulated program-years

**What changes.** `funnel.window(root, start, end)` gains ONE section, `asset_years`: per equity lane and structure
("etf", "stock", "panel"), the Gym's Train runs of the window as simulated program-years, the independent asset-years
they read (their Train years, never more than the structure's Train era holds, x the N_eff of their data) and the
ratio of the two, the replay multiple. The panel's N_eff is `neff_pr` of `<state>/equity-daily/neff.json` (the
`equity_neff` job); an ETF program's is release E3's figure when its report's file under `<state>`
(`forward_report.FILE`; release E3's seal lets no text of league/swarm spell that name) carries one (`cey.hist_iy`
over the history's years), else 2.3; a structure with no N_eff reads None for it, never a zero.
Nothing the funnel carried before moves; rows that cannot be read are `errors["asset_years"]` and take no other
section with them. The daily page (`scoreboard.funnel_lines`) prints from its own allowlist and shows none of it.

**Anchors (by statement).** (1) The module docstring: the new paragraph stands before the paragraph that begins
"READ-ONLY: every SQLite open is `mode=ro`". (2) In `window`: the new `try` block stands after the `book` section's
`except` and before `return out`. Release E3's own funnel patch (its 11.4: a `forward_record` block at the same
place) is independent of this one: the two blocks may stand in either order.

```diff
diff --git a/league/ops/funnel.py b/league/ops/funnel.py
index 20ad1c1a..c7dfe97a 100644
--- a/league/ops/funnel.py
+++ b/league/ops/funnel.py
@@ -36,6 +36,12 @@ THE EQUITY LANES (release E1, Oct 2026), apart, under `equity` (the daily page's
 - from the live book (`book_counts`'s `equity`): the EquityBook's orders placed and filled, lots opened and closed (a
   close is one lot fully closed), and the programs holding a lot now.
 
+INDEPENDENT ASSET-YEARS (release E4), apart, under `asset_years` (the daily page's table reads none of them): per
+equity lane and structure ("etf", "stock", "panel"), the Gym's Train runs in the window as simulated program-years
+beside the independent asset-years they read (their Train years x the N_eff of their data: the panel's `neff_pr` of
+neff.json, an ETF program's from release E3's report when it carries one, else 2.3) and the ratio, the replay multiple
+(league/ops/equity_neff.py `funnel_rows`). Simulated years are compute, never evidence; N_eff is a count, never a return.
+
 READ-ONLY: every SQLite open is `mode=ro` (`guard.read`); each section that cannot be read is an `errors` entry and its
 counts None, never a zero. Standard library only.
 """
@@ -380,6 +386,12 @@ def window(root: str | Path, start: float, end: float) -> dict[str, Any]:
         out["book"] = book_counts(root, start, end)
     except Exception as exc:  # noqa: BLE001
         out["errors"]["book"] = f"{type(exc).__name__}: {str(exc)[:200]}"
+    try:  # RELEASE E4: independent asset-years beside simulated program-years (league/ops/equity_neff.py)
+        from . import equity_neff
+
+        out["asset_years"] = guard.read(root / SWARM_DB, lambda db: equity_neff.funnel_rows(root, db, start, end))
+    except Exception as exc:  # noqa: BLE001 - unread is never zero
+        out["errors"]["asset_years"] = f"{type(exc).__name__}: {str(exc)[:200]}"
     return out
 
 
```

**The test that holds it** (`TheFunnelCarriesTheRows`, added to `league/tests/test_equity_neff.py`; the rows
themselves are held by `TheFunnelsRows` in that file, already on the package's branch):

```diff
diff --git a/league/tests/test_equity_neff.py b/league/tests/test_equity_neff.py
index 82a0d2b6..777f4095 100644
--- a/league/tests/test_equity_neff.py
+++ b/league/tests/test_equity_neff.py
@@ -710,5 +710,66 @@ class TheFunnelsRows(unittest.TestCase):
         self.assertEqual(top, {"__future__", "datetime", "json", "math", "sqlite3", "pathlib", "typing"})
 
 
+class TheFunnelCarriesTheRows(unittest.TestCase):
+    """Package B's patch 11: `league.ops.funnel.window` carries the rows under `asset_years`, beside every count it
+    carried before; rows it cannot read are an `errors` entry, never a zero, and take no other section with them."""
+
+    def setUp(self):
+        from league.swarm.store import SwarmStore
+
+        self.tmp = tempfile.TemporaryDirectory()
+        self.addCleanup(self.tmp.cleanup)
+        self.root = Path(self.tmp.name)
+        store = SwarmStore(self.root, clock=lambda: NOW - 3600.0)
+        self.addCleanup(store.close)
+        store.add_family({**SPEC, "id": "etf-eq", "structure": "etf", "lane": "equity"}, origin="seed")
+        store.add_family({**SPEC, "id": "panel-a", "structure": "etf", "lane": "equity"}, origin="seed")
+        db = sqlite3.connect(self.root / "swarm.sqlite")
+        db.execute("UPDATE families SET structure='panel' WHERE id='panel-a'")
+        db.commit()
+        db.close()
+        for i, (fid, days) in enumerate((("etf-eq", 1764), ("panel-a", 754), ("panel-a", 753))):
+            store.add_run(fid, 1, {"run_id": f"r{i}", "status": "ok", "trials": 1, "summary": {"days": days}},
+                          window="train", stress=1.0, purpose="elane_train", prune=False)
+        (self.root / EN.STORE_DIR).mkdir()
+        (self.root / EN.STORE_DIR / EN.FILE).write_text(json.dumps({"sp500": {"neff_pr": 80.0}}))
+
+    def test_the_window_carries_the_rows_beside_what_it_carried(self):
+        from league.ops import funnel
+
+        out = funnel.window(self.root, NOW - 86400.0, NOW)
+        self.assertEqual(out["errors"], {})
+        self.assertEqual(out["asset_years"], guard.read(
+            self.root / "swarm.sqlite", lambda db: EN.funnel_rows(self.root, db, NOW - 86400.0, NOW)))
+        panel = out["asset_years"]["equity"]["panel"]
+        self.assertEqual((panel["train_runs"], panel["program_years"], panel["train_years"], panel["neff"]),
+                         (2, 5.98, 5.98, 80.0))
+        self.assertEqual(panel["independent_asset_years"], round(1507 / 252 * 80.0, 2))
+        self.assertEqual(out["asset_years"]["equity"]["etf"]["replay_multiple"], round(7.0 / 16.1, 2))
+        for key in ("births", "versions", "gym_runs", "gym_runs_total", "validations", "looks", "band_moves",
+                    "spend_usd", "equity", "braked", "book"):
+            self.assertIn(key, out, f"the funnel lost {key}")
+        self.assertEqual(out["gym_runs"]["train"], 3)
+        self.assertEqual(funnel.read(self.root, self.root, "r1", NOW)["day"]["asset_years"], out["asset_years"])
+
+    def test_rows_that_cannot_be_read_are_an_error_never_a_zero(self):
+        from league.ops import funnel
+
+        with mock.patch.object(EN, "funnel_rows", side_effect=RuntimeError("no rows today")):
+            out = funnel.window(self.root, NOW - 86400.0, NOW)
+        self.assertNotIn("asset_years", out)
+        self.assertEqual(out["errors"], {"asset_years": "RuntimeError: no rows today"})
+        self.assertEqual((out["gym_runs"]["train"], out["looks"]), (3, {"taken": 0, "passed": 0}))
+        self.assertIn("book", out)
+
+    def test_the_funnel_still_imports_the_standard_library_alone(self):
+        from league.ops import funnel
+
+        tree = ast.parse(Path(funnel.__file__).read_text())
+        top = {alias.name for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
+        self.assertNotIn("equity_neff", top)
+        self.assertNotIn("numpy", top)
+
+
 if __name__ == "__main__":
     unittest.main()
```

---

## Patch 11b. `league/ops/twins.py`: a panel lot's half-spread

**What changes.** `equity_twin` prices a lot whose symbol is outside E1's universe (`config.half_spread` raises
KeyError: a panel lot) at the PANEL'S half-spreads, by the lot's fill points: the open's figure for a fill at the
open, the close's for a fill at the close (`panel/hs.npy`, through `league.xs.store.Universe.aid` on the lot's entry
day: `league.ops.equity_spreads.panel_half_spread`). The record of such a lot carries `hs_bp` (its entry's),
`hs_exit_bp` and `hs_source` "panel"; a lot of E1's universe never asks the panel and its record is, key for key,
what E1 builds today. With no panel store, or no figure for the symbol, the lot is "unpriceable" and final, in E1's
own words, as before. ONE THING IS NEW AND NOT IN THE SPEC'S SENTENCE: a panel store that IS there and cannot be
read (a file that does not match its manifest while the nightly job rewrites it, no universe) leaves the lot WAITING
(`final` False, counted in the round's `pending_why`), because an "unpriceable" verdict is final and a twin lost for
good is a session E3's meter reads as not agreed. `equity_round` builds the reader the FIRST time a lot outside E1's
universe asks, so a book of E1 lots alone never opens the panel store.

**Anchors (by statement).** (1) The module docstring: after the sentence ending "and is FINAL once judged
(`EQUITY_STATUSES`; never asked again)." (2) `equity_twin`'s signature gains the keyword `panel_hs` and its docstring
the keyword's meaning. (3) The statement `hs = config.half_spread(symbol)` and its `except KeyError`: `hs` becomes
`hs_entry` and `hs_exit`; the two `fill_price` calls read one each. (4) A new function `panel_reader` before
`equity_round`. (5) In `equity_round`: `panel_hs = panel_reader(root)` after `known = equity_records(store)`, and
the keyword in its one `equity_twin` call. (6) `__all__` gains "panel_reader".

```diff
diff --git a/league/ops/twins.py b/league/ops/twins.py
index dae3eda0..491834a5 100644
--- a/league/ops/twins.py
+++ b/league/ops/twins.py
@@ -72,7 +72,11 @@ exit_official, judged_at, ...}: `equity_twin`) carries:
   lot is delta one, so this is its market direction; the lot's net minus it is its excess (MTE).
 A verdict is "priced", "no_bar" (the House holds no official price of the symbol on the entry or the exit day) or
 "unpriceable" (the lot's row cannot be read, or its symbol is outside the universe), and is FINAL once judged
-(`EQUITY_STATUSES`; never asked again). A priced twin is judged once both bars are audited by the morning re-fetch, or
+(`EQUITY_STATUSES`; never asked again). A PANEL LOT (release E4: a name outside E1's universe) is priced at the panel's
+own half-spreads, the open's for a fill at the open and the close's for a fill at the close (panel/hs.npy, read through
+league/ops/equity_spreads.py `panel_half_spread`); a panel store that is there and cannot be read leaves the lot waiting,
+never a final verdict; with no panel store, or no figure for the symbol, the lot stays unpriceable.
+A priced twin is judged once both bars are audited by the morning re-fetch, or
 once the exit day is `EQUITY_SETTLE_SESSIONS` sessions past (then judged on the bars as they are, said in `note`); a
 missing bar is "no_bar" only from then on (until then the lot waits: the bars land at 16:20 ET of the exit day). A bar
 the re-fetch found different (`audit` "mismatch") is a twin `note` (the book raises the alarm). The records are the
@@ -688,12 +692,16 @@ def _round(value: Decimal | float | None, places: int) -> float | None:
 
 
 def equity_twin(lot: Mapping[str, Any], bars: Mapping[str, Mapping[str, Any]], *, k: float = 1.0, settled: bool = True,
-                at: float | None = None) -> dict[str, Any]:
+                at: float | None = None,
+                panel_hs: Callable[[str, str], Sequence[float] | None] | None = None) -> dict[str, Any]:
     """THE EQUITY TWIN of one closed lot (the module docstring), in closed form. `lot`: its `eq_lots` row. `bars`: {ISO day:
     the `eq_bars` raw row of the lot's symbol} ({o, h, l, c, v, audit, sha}; Decimal strings as the book writes them).
     `k`: the half-spread multiple (`config.K_BASE`; `K_STRESS` for the robustness twin). `settled`: the exit day is
     `EQUITY_SETTLE_SESSIONS` sessions past (the round says; a missing bar is then final "no_bar" and an unaudited one is
-    judged as it is). `at`: the judging time (epoch; `judged_at`). Pure. {"key": "eq:<lid>", "status": "priced" |
+    judged as it is). `at`: the judging time (epoch; `judged_at`). `panel_hs` (release E4): asked ONLY for a symbol
+    outside E1's universe, `(symbol, entry day) -> (half-spread at the open, at the close)`, None when the panel has no
+    figure for it (final "unpriceable", as without a reader), LookupError when the panel's figures cannot be read now
+    (the lot waits). Pure. {"key": "eq:<lid>", "status": "priced" |
     "no_bar" | "unpriceable", "final", "live_return", "twin_return", "gap_bp" (a side), "entry_official",
     "exit_official", "judged_at", ...}."""
     from ..equity import config
@@ -737,10 +745,19 @@ def equity_twin(lot: Mapping[str, Any], bars: Mapping[str, Mapping[str, Any]], *
     except ValueError:
         return unpriceable("the lot's entry or exit day cannot be read")
     try:
-        hs = config.half_spread(symbol)
+        hs_entry = hs_exit = config.half_spread(symbol)
     except KeyError:
-        return unpriceable(f"{symbol or 'its symbol'} is not in the universe (no half-spread)")
-    rec["hs_bp"] = round(hs * 1e4, 4)
+        # RELEASE E4: a panel lot. Its half-spread is the panel's, by fill point; none: unpriceable, as before.
+        try:
+            pair = panel_hs(symbol, opened_day) if panel_hs is not None else None
+        except LookupError as exc:
+            return unpriceable(f"the panel's half-spreads cannot be read ({str(exc)[:120]})", final=False)
+        sides = [_num(v) for v in pair] if isinstance(pair, (list, tuple)) and len(pair) == len(FILL_POINTS) else []
+        if not sides or any(v is None or v <= 0 for v in sides):
+            return unpriceable(f"{symbol or 'its symbol'} is not in the universe (no half-spread)")
+        hs_entry, hs_exit = sides[FILL_POINTS.index(entry_at)], sides[FILL_POINTS.index(exit_at)]
+        rec.update(hs_exit_bp=round(hs_exit * 1e4, 4), hs_source="panel")
+    rec["hs_bp"] = round(hs_entry * 1e4, 4)
     # THE SPLIT between entry and exit: the shares sold over the shares bought (the lot's qty when the book keeps it at the
     # sale; else from its proceeds: a factor within 1% of one is no split).
     if qty is not None and qty > 0:
@@ -769,8 +786,8 @@ def equity_twin(lot: Mapping[str, Any], bars: Mapping[str, Mapping[str, Any]], *
                        "(A8.11): " + ", ".join(k_ for k_, v in audits.items() if v == "mismatch"))
     elif unaudited and settled:
         rec["note"] = f"judged on bars the morning re-fetch never audited ({', '.join(unaudited)})"
-    entry_fill = Decimal(str(fill_price(entry_official, "buy", hs, float(k))))
-    exit_fill = Decimal(str(fill_price(exit_official, "sell", hs, float(k))))
+    entry_fill = Decimal(str(fill_price(entry_official, "buy", hs_entry, float(k))))
+    exit_fill = Decimal(str(fill_price(exit_official, "sell", hs_exit, float(k))))
     places = Decimal(1).scaleb(-config.QTY_PLACES)
     shares = (notional / entry_fill).quantize(places, rounding=ROUND_FLOOR)
     if shares <= 0:
@@ -857,6 +874,30 @@ def settled_after(exit_day: Any, now: float) -> bool:
     return len(begun) >= EQUITY_SETTLE_SESSIONS
 
 
+def panel_reader(root: str | Path) -> Callable[[str, str], Sequence[float] | None]:
+    """RELEASE E4: `equity_twin`'s `panel_hs` over the House's panel store (league/ops/equity_spreads.py
+    `panel_half_spread`), built the FIRST time a lot outside E1's universe asks: a book of E1 lots alone never opens the
+    panel store. With no panel store it answers None (the lot is unpriceable, as before E4); with one that cannot be
+    read it raises LookupError (the lot waits for a round that can read it)."""
+    built: list[Any] = []
+
+    def ask(symbol: str, day: str) -> Sequence[float] | None:
+        if not built:
+            try:
+                from . import equity_spreads
+                from .equity_data import STORE_DIR
+
+                built.append(equity_spreads.panel_half_spread(Path(root) / STORE_DIR))
+            except Exception as exc:  # noqa: BLE001 - a panel store that cannot be read: the lot waits, the job goes on
+                built.append(exc if isinstance(exc, LookupError)
+                             else LookupError(f"{type(exc).__name__}: {str(exc)[:120]}"))
+        if isinstance(built[0], LookupError):
+            raise built[0]
+        return None if built[0] is None else built[0](symbol, day)
+
+    return ask
+
+
 def equity_round(root: str | Path, *, now: float, store: Any, k: float = 1.0,
                  book: Mapping[str, Any] | None = None) -> dict[str, Any]:
     """Judge every closed equity lot without a final record (`equity_twin`) and keep the final ones in the swarm store's
@@ -864,6 +905,7 @@ def equity_round(root: str | Path, *, now: float, store: Any, k: float = 1.0,
     "notes": [key...]}. A record already final is never judged again."""
     book = book if book is not None else read_equity(Path(root) / LIVE_DB)
     known = equity_records(store)
+    panel_hs = panel_reader(root)
     judged: dict[str, dict[str, Any]] = {}
     pending: dict[str, int] = {}
     for lot in book.get("lots") or []:
@@ -875,7 +917,7 @@ def equity_round(root: str | Path, *, now: float, store: Any, k: float = 1.0,
             continue
         exit_day = lot.get("exit_day") or ny_day(lot.get("closed_at"))
         rec = equity_twin(lot, (book.get("bars") or {}).get(str(lot.get("symbol") or ""), {}), k=k,
-                          settled=settled_after(exit_day, now), at=now)
+                          settled=settled_after(exit_day, now), at=now, panel_hs=panel_hs)
         if rec["final"]:
             judged[key] = rec
         else:
@@ -925,4 +967,4 @@ def run(ctx: Any) -> dict[str, Any]:
 __all__ = ["Twins", "PUPPET", "PUPPET_SHA", "TWINS_KEY", "ATTEMPT_KEY", "GATE_REASON", "FINAL", "plan", "judge", "job_for",
            "read_live", "records", "cfg", "twin_exit", "live_exit", "expiry_close", "sessions", "agent",
            "EQUITY_TWINS_KEY", "EQUITY_STATUSES", "EQUITY_SETTLE_SESSIONS", "EQUITY_BH_BASIS", "equity_key",
-           "equity_twin", "equity_records", "read_equity", "settled_after", "equity_round", "run"]
+           "equity_twin", "equity_records", "read_equity", "settled_after", "equity_round", "run", "panel_reader"]
```

**The test that holds it** (`APanelLotsTwin`, added to `league/tests/test_equity_spreads.py`; the reader itself is
held by `ThePanelHalfSpread` in that file, already on the package's branch):

```diff
diff --git a/league/tests/test_equity_spreads.py b/league/tests/test_equity_spreads.py
index c9d62216..ca35a1f0 100644
--- a/league/tests/test_equity_spreads.py
+++ b/league/tests/test_equity_spreads.py
@@ -751,5 +751,143 @@ class ThePanelHalfSpread(unittest.TestCase):
         self.assertEqual(len(SP.POINTS), len(SP.TIMES_ET))
 
 
+# ------------------------------------------------------------------------------------------------- a panel lot's twin
+def panel_lot(lid: int = 7, *, symbol: str = "QAZ", entry_at: str = "open", exit_at: str = "close",
+              opened_day: str = "2027-02-01", exit_day: str = "2027-02-03") -> dict:
+    """An invented closed `eq_lots` row of a name outside E1's universe (league/equity/live.py SCHEMA)."""
+    return {"lid": lid, "instance": "panel-fam@1:r", "family": "panel-fam", "version": 1, "lane": "equity",
+            "symbol": symbol, "class": "stock" if symbol != "SPY" else "etf", "qty": "2.500000",
+            "opened_qty": "2.500000", "entry_px": "40.06", "entry_notional": "100.15", "entry_at": entry_at,
+            "fees": "0.02", "div": "0", "mark": None, "marked_at": None, "opened_at": 1.0, "opened_day": opened_day,
+            "status": "closed", "exit_px": "42.90", "exit_at": exit_at, "exit_day": exit_day, "closed_at": 2.0,
+            "cash": "7.08", "reason": "program", "probe": 1, "tag": "xs", "iid": None, "info": "{}"}
+
+
+def official(o: float, c: float) -> dict:
+    return {"o": str(o), "h": str(max(o, c) + 1), "l": str(min(o, c) - 1), "c": str(c), "v": "1000000", "audit": "ok",
+            "sha": "x" * 64}
+
+
+BARS = {"2027-02-01": official(40.0, 41.0), "2027-02-03": official(42.0, 43.0)}
+
+
+class APanelLotsTwin(unittest.TestCase):
+    """Package B's patch 11 to league/ops/twins.py: a lot of a name outside E1's universe is priced at the panel's
+    half-spreads, the open's figure for a fill at the open and the close's for a fill at the close; with none it stays
+    unpriceable; a lot of E1's universe never asks."""
+
+    PAIR = (0.0010, 0.0005)
+
+    def twin(self, row=None, **kw):
+        from league.ops import twins
+
+        return twins.equity_twin(row or panel_lot(), BARS, at=NOW, **kw)
+
+    def test_an_open_entry_pays_the_opens_figure_and_a_close_exit_the_closes(self):
+        asked = []
+
+        def reader(symbol, day):
+            asked.append((symbol, day))
+            return self.PAIR
+
+        rec = self.twin(panel_hs=reader)
+        self.assertEqual((rec["status"], rec["final"], rec["why"]), ("priced", True, None))
+        self.assertEqual(asked, [("QAZ", "2027-02-01")])
+        self.assertEqual((rec["hs_bp"], rec["hs_exit_bp"], rec["hs_source"]), (10.0, 5.0, "panel"))
+        self.assertEqual((rec["entry_official"], rec["exit_official"]), (40.0, 43.0))
+        self.assertEqual(rec["twin"]["entry_px"], round(40.0 * (1 + 0.0010), 6))
+        self.assertEqual(rec["twin"]["exit_px"], round(43.0 * (1 - 0.0005), 6))
+        stress = self.twin(panel_hs=reader, k=1.5)
+        self.assertEqual(stress["twin"]["entry_px"], round(40.0 * (1 + 0.0015), 6))
+        self.assertEqual(stress["twin"]["exit_px"], round(43.0 * (1 - 0.00075), 6))
+
+    def test_a_close_entry_pays_the_closes_figure_and_an_open_exit_the_opens(self):
+        rec = self.twin(panel_lot(entry_at="close", exit_at="open"), panel_hs=lambda symbol, day: self.PAIR)
+        self.assertEqual((rec["entry_official"], rec["exit_official"]), (41.0, 42.0))
+        self.assertEqual((rec["hs_bp"], rec["hs_exit_bp"]), (5.0, 10.0))
+        self.assertEqual(rec["twin"]["entry_px"], round(41.0 * (1 + 0.0005), 6))
+        self.assertEqual(rec["twin"]["exit_px"], round(42.0 * (1 - 0.0010), 6))
+
+    def test_with_no_figure_the_lot_is_unpriceable_as_before(self):
+        want = ("unpriceable", True, "QAZ is not in the universe (no half-spread)")
+        rec = self.twin()
+        self.assertEqual((rec["status"], rec["final"], rec["why"]), want)
+        for answer in (None, (), (0.001,), (0.001, 0.0), (0.001, float("nan")), ("x", 0.001), (0.001, 0.001, 0.001),
+                       {"open": 0.001, "close": 0.001}):
+            rec = self.twin(panel_hs=lambda symbol, day, a=answer: a)
+            self.assertEqual((rec["status"], rec["final"], rec["why"]), want, answer)
+            self.assertNotIn("hs_source", rec)
+
+    def test_a_panel_store_that_cannot_be_read_leaves_the_lot_waiting(self):
+        def unread(symbol, day):
+            raise LookupError("panel/hs.npy does not match its manifest")
+
+        rec = self.twin(panel_hs=unread)
+        self.assertEqual((rec["status"], rec["final"]), ("unpriceable", False))
+        self.assertIn("cannot be read", rec["why"])
+        self.assertIn("does not match its manifest", rec["why"])
+
+    def test_a_lot_of_e1s_universe_never_asks_the_panel(self):
+        def boom(symbol, day):
+            raise AssertionError("an E1 lot asked the panel for a half-spread")
+
+        row = panel_lot(symbol="SPY")
+        rec = self.twin(row, panel_hs=boom)
+        self.assertEqual(rec, self.twin(row))
+        self.assertEqual(rec["status"], "priced")
+        self.assertNotIn("hs_source", rec)
+        self.assertNotIn("hs_exit_bp", rec)
+
+    def round(self, lots, reader):
+        """`equity_round` over a book of `lots`, `panel_half_spread` answering `reader` (an exception: raised)."""
+        from league.equity.live import SCHEMA
+        from league.live.state import LiveState
+        from league.ops import twins
+        from league.swarm.store import SwarmStore
+
+        tmp = tempfile.TemporaryDirectory()
+        self.addCleanup(tmp.cleanup)
+        root = Path(tmp.name)
+        store = SwarmStore(root)
+        self.addCleanup(store.close)
+        live = LiveState(root / "live.sqlite")
+        self.addCleanup(live.close)
+        live.db.executescript(SCHEMA)
+        for row in lots:
+            live.upsert("eq_lots", row, "lid")
+            for day, b in BARS.items():
+                live.upsert("eq_bars", {"day": day, "symbol": row["symbol"], "adjustment": "raw", "o": b["o"],
+                                        "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "fetched_at": 0.0,
+                                        "sha": b["sha"], "audit": b["audit"]}, "day, symbol, adjustment")
+        opened = mock.Mock(side_effect=reader if isinstance(reader, Exception) else None, return_value=reader)
+        with mock.patch.object(SP, "panel_half_spread", opened):
+            out = twins.equity_round(root, now=NOW, store=store)
+        return out, twins.equity_records(store), opened, root
+
+    def test_the_round_never_opens_the_panel_store_for_a_book_of_e1_lots(self):
+        out, records, opened, _ = self.round([panel_lot(1, symbol="SPY")], lambda symbol, day: self.PAIR)
+        self.assertEqual((out["judged"], records["eq:1"]["status"]), ({"priced": 1}, "priced"))
+        opened.assert_not_called()
+
+    def test_the_round_prices_a_panel_lot_from_the_panel_store_opened_once(self):
+        out, records, opened, root = self.round([panel_lot(1, symbol="SPY"), panel_lot(2), panel_lot(3, symbol="QBZ")],
+                                                lambda symbol, day: self.PAIR if symbol == "QAZ" else None)
+        opened.assert_called_once_with(root / SP.STORE_DIR)
+        self.assertEqual(out["judged"], {"priced": 2, "unpriceable": 1})
+        self.assertEqual((records["eq:2"]["status"], records["eq:2"]["hs_source"], records["eq:2"]["hs_bp"]),
+                         ("priced", "panel", 10.0))
+        self.assertEqual((records["eq:3"]["status"], records["eq:3"]["final"]), ("unpriceable", True))
+
+    def test_with_no_panel_store_a_panel_lot_is_unpriceable_and_with_an_unreadable_one_it_waits(self):
+        out, records, opened, _ = self.round([panel_lot(2)], None)
+        self.assertEqual((out["judged"], records["eq:2"]["status"], records["eq:2"]["final"]),
+                         ({"unpriceable": 1}, "unpriceable", True))
+        for fail in (LookupError("panel/hs.npy does not match its manifest"), RuntimeError("anything else")):
+            out, records, opened, _ = self.round([panel_lot(1, symbol="SPY"), panel_lot(2), panel_lot(4)], fail)
+            self.assertEqual((out["judged"], out["pending"], sorted(records)), ({"priced": 1}, 2, ["eq:1"]))
+            self.assertTrue(all("cannot be read" in why for why in out["pending_why"]))
+            opened.assert_called_once()
+
+
 if __name__ == "__main__":
     unittest.main()
```

---

## Patch 18 (OWED: after release E3 is merged, never before). `league/ops/contam_probe.py`: the panel strata

NOT WRITTEN, on purpose: the file is release E3's and does not exist at this build's base, and a diff against a
branch that is still moving would be a diff against nothing. It is owed with release E4's first release after E3,
and until it lands NO PANEL LOOK RUNS (the captain's A22 (3): `league.swarm.elane_xs.probed` holds every look back
until the route that wrote the program has a published probe result with the panel strata).

What it adds, so its author starts from a decided shape (E4-SPEC 15, row 18; the names are the ones
`elane_xs.PROBE_STRATA` already reads):
- **P4** a random index member against its sector fund, a month ("Did X return more or less than <its sector's
  fund> in <Month YYYY>?"); **P5** the same, a week; **P6** the House panel factors, a month (the run's `factors`:
  momentum, short-term reversal and beta, each a top-minus-bottom tercile: "Did the highest-momentum third of the
  index return more or less than the lowest third in <Month YYYY>?").
- Truth stays on the House and comes from the PANEL STORE by era (`league.xs.store.PanelStore`: Train-era periods
  with no capability; a 2025 or 2026 period only under E1's gate capability, minted under the probe's own reason, as
  E3's S1-S4 mint theirs); the questions are built from names and the calendar only, as E3's are. The members asked
  about are drawn by E3's own grid rule (`sha256("contam-1|<stratum>|<era>|<symbol>")`) over the era's members
  (`Universe.members`), so the same questions are asked of every route.
- The cells are written under the keys "P4", "P5" and "P6" of `routes[route].cells` in the probe's own file
  under `<state>` (`contam_probe.FILE`: aggregates only, E3's own shape).
- AND THE PROBE'S JOB WRITES THE PERMIT (decided when E4 was merged over E3: release E3's seal lets no module of
  league/swarm name the probe's file or import the probe, so the swarm cannot read it, and must not: the file holds
  counts and rates of the eras programs are judged on). Each time it publishes a route's result the job rewrites
  `<state>/xs-probe.json` (`elane_xs.PROBE_FILE`; atomic, 600): {"version": "xs-probe-1" (`elane_xs.PROBE_VERSION`),
  "routes": {route: {"at", "model", "cells": {"P4" | "P5" | "P6": {era: {"readable": bool, "recalled": bool}}}}}},
  one row for every route with a published result that carries all three panel strata, and NOTHING ELSE of a cell
  (no n, no accuracy, no base rate, no p). That file is what `elane_xs.probed` reads; a file of another version, or
  none, is no permit and every panel look waits.
- Its test: the three strata's questions are pure of prices; a period of 2020 or 2021 is never asked about and never
  read; truth for a 2025 period is refused without the capability; a route's published result carries the three
  cells; E3's own S1-S4 cells are byte for byte what they were; the permit holds the two words a cell and no figure,
  and `elane_xs.probed` reads None on it for a route with all three strata.

---

## What package B offers other packages' patches (no diff of B's own)

- **Package H's report patch (13).** `league.ops.equity_neff.funnel_lines(rows)` turns the funnel's `asset_years`
  rows into lines for the operator's report (one a lane and structure that ran: simulated program-years, the
  independent asset-years under them, the replay multiple; counts and N_eff only). One call where the report prints
  its funnel, if the integrator wants the figure seen; nothing reads it otherwise.
- **Package I's docs pass (patch 16).** Text for `docs/operations.md`, to copy or rewrite:

  > **The panel's costs and counts (release E4).** Three House jobs, read-only but for their own files under
  > `<state>/equity-daily/`, each asking the quiet windows first with its own wall. `equity_spreads` (daily 06:30Z)
  > samples each index member's quoted half-spread at 09:32:00 and 15:55:00 New York time on eight sessions of each
  > Train year (2017-19, 2022-24; never another year), one two-second window a request, at most 6,000 requests a run
  > (about nine nights in all, then a monthly look for new assets), into `spreads.json`; a sample above 100 bp is
  > dropped and counted, and a dropped share above 10% at a fill point is a House warning. A failed receipt names why
  > a run was ended (ten errors in a row; or the venue refusing more than a fifth of at least 50 requests, whose
  > refusals are then not kept); the next run goes on from the file. `equity_neff` (first Saturday, 10:00Z) writes
  > `neff.json`: how many independent names the panel holds on 2022-24, on monthly sector residuals. `french` (first
  > Saturday, 11:00Z) is "skipped: no route to the French library from the House" until an operator places the
  > library's daily files (its own zips, or their one member as text, named as the library names them) under
  > `<state>/equity-daily/french/inbox/`: the next run keeps the days of 1926-2019 and 2022-2024 under `french/`,
  > drops every line of 2020 and 2021 unparsed, counts the lines of 2025 on without writing them, and REMOVES the
  > inbox file. The funnel carries `asset_years` (simulated program-years beside independent asset-years and the
  > replay multiple, per equity lane and structure). A panel lot's replay twin is priced at the panel's own
  > half-spreads by its fill points; while the panel store cannot be read such a lot waits and is not judged.

  And for `CHANGELOG.md` ("Not yet deployed"): "Release E4, package B: the panel's half-spread table
  (`equity_spreads`), its independent-name count (`equity_neff`), the French library's factor files when a route
  exists (`french`: the line filter that drops 2020 and 2021 unparsed), independent asset-years in the funnel, and a
  panel lot's half-spread in its replay twin. Proof: `test_equity_spreads`, `test_equity_neff`, `test_french`."

---

## What package B needs of other packages (no diff: said here so the integrator can check it)

- **Package A's registry rows** (patch 10) name `league.ops.equity_spreads`, `league.ops.equity_neff` and
  `league.ops.french`, each `run(ctx)`, with the walls the modules ask `league.xs.config.quiet` with (`WALL_S`:
  3000, 900, 300; `test_e4_stubs` holds them).
- **Package A's `equity_panel.hs_table`** writes D20's reading of spreads.json into panel/hs.npy.
  `league.ops.equity_spreads.name_bp(table, aid)` IS that reading (the floor, eight samples, the universe's figure,
  the fallback), tested as D20's formula: the two must agree, and the integrator may make `hs_table` call it.
- **Package C's `league.xs.store.Universe`** (`members`, `aid`), `PanelStore` (`verdict`, `train`) and
  `league.xs.ctx` (`inputs_from_panel`, `derive`) are called through their Step 0 signatures only; while one is a
  stub the job that needs it answers a failed or skipped receipt, never a crash. `league.xs.config.quiet` (C0) is
  each job's first statement; a `quiet` that raises is "skipped" with a House warning (a job that cannot learn
  whether it stands at a wall does not start).
- **Facts for the captain to verify on the House** (E4-SPEC 19, fact 3): `v2/stocks/quotes` answers a two-second
  historical window of one symbol with `limit` 50, `feed=sip`, `sort=asc` and `asof`, from 2017. The first night's
  receipt shows it (`sampled` against `empty`, `refused` and `errors`), and its `early` block is fact 3's second half
  (the median half-spread of 20 fixed names at 09:30:30 beside 09:32:00).
- **No gateway change is needed.** The quotes route is already allowed. The French library's data route (`GET
  /v1/data/french/<file>`, answering {"text": the file's one member}) is the owner's option of E4-SPEC 19 and is not
  built: until it or an inbox file exists the job is skipped.
