# E4 patches authored by package I

Package I (money and universe) owns `scripts/gen_universe.py` and `league/tests/test_gen_universe.py` outright. This
file is its changes to files that existed before E4: **patch 16** (release R-E4a) and **patch 15** (release R-E4b,
THE UNIVERSE: it moves the money digest and is deployed separately, one commit, clearly marked, made LAST). The
gateway's half of patch 15 is a patch file in the captain's private scratch (`eqe4/gateway-universe.patch`, with its
tests' expected results): no builder edits `gateway/`.

Each patch: the file, the anchor (a statement, never a line number), the exact unified diff against the Step 0 base
(`24a52b11`), and the test that holds it. Every diff here was applied to a scratch copy of the tree and tested there,
on Python 3.14 and 3.11, in the two states that matter: with release E1's 18 stocks, and with a generated universe
of several hundred names (a stand-in list in private scratch: the House's own list does not exist yet, and no list
of real names is ever in a test or in this repository before the UNIVERSE commit). The last section says what was
run.

## How the two releases split (read this first)

**The rule that makes R-E4b one small commit:** every TEST change of patch 15 holds BEFORE the universe grows and
AFTER it. None names a stock but release E1's own 18; a digest pinned for E1 is read with E1's universe put back
(`league.equity.config.UNIVERSE`, which E4 never changes). So the integrator may apply ALL of this file's diffs with
R-E4a, and what remains for the R-E4b commit is **the generator's output and nothing typed by hand**:

| commit | what is in it | who makes it | digests |
|---|---|---|---|
| R-E4a (with the other packages' patches) | patch 16 (16.1-16.5), and patch 15's tests and pre-open check (15.1-15.4) | the integrator | none moves: the constitution is untouched |
| **UNIVERSE (moves the money digest; deployed separately)** | `league/constitution.py` as `scripts/gen_universe.py` writes it (15.5) AND `gateway/lib/caps.mjs` as its patch writes it (15.6), nothing else | the captain, with the House's `tradable.json`; the gateway hunk is the owner's `git apply` | `digest()` and `money_digest()` move once |

If the integrator prefers 15.1-15.4 in the UNIVERSE commit, they apply there as well: they are digest-neutral and
pass in either order. What cannot be done is the UNIVERSE commit WITHOUT its gateway half: `league.ci.check_equity`
(`gateway_stock_problems`) and `test_ci.TheEquityLane.test_the_repository_as_it_stands_agrees` hold the tree's two
lists equal, so a tree with the constitution's list grown and the gateway's not is red. The list itself does not
exist yet: the House's `equity_universe` job writes `universe/tradable.json` only after R-E4a is deployed and its
audit has passed. So the UNIVERSE commit cannot be made at integration; what the integrator lands is everything that
makes it mechanical.

**Three things the split corrects in `README.md`'s rows 15 and 16** (for the integrator, who owns that file):
1. `league/tests/test_constitution.py` and `league/tests/test_live_long_single.py` are in patch 15 too (15.2, 15.3):
   each pins E1's money digest by value. They were found by running the whole suite on a tree with a grown universe:
   eight tests fail there without this patch (one in `test_ci`, one in `test_constitution`, five in
   `test_equity_money`, one in `test_live_long_single`), none with it.
2. `league/ops/preopen.py` has ONE hunk that belongs to R-E4a (16.3: the options population's count), because a panel
   family is born in mode "train", long before the universe.
3. `league/tests/test_ci.py`'s universe test is rewritten in patch 16 (16.2) so that it names no generated stock.

## Patch 16 (release R-E4a)

### 16.1 `league/ci.py`: the protected paths, and a difference that names at most 10 tickers a side

Anchors: the tuple `PENDING_GATEWAY` (its comment and its last entry); the constant `GATEWAY_STOCK_SHARES` (the new
`AGREEMENT_NAMES` and `_named` follow it); in `stock_agreement`, its docstring's last sentence and the one
`problems.append` that names both sides.

- `FORBIDDEN` (through `PENDING_GATEWAY`, until the gateway's merge list names them) gains `league/swarm/elane_xs.py`
  and `scripts/gen_universe.py` (E4-SPEC 2.5). `league/xs/`, `league/ops/` and `docs/benchmarks/` were behind the wall
  already. The gateway's own merge test reads the `FORBIDDEN` literal only, so it is unaffected.
- `stock_agreement` names at most `AGREEMENT_NAMES` (10) tickers a side, in ticker order, and counts the rest
  ("... and 510 more (520 in all)"). A difference of ten or fewer reads exactly as before. Why: the pre-open's check 10
  posts this line as a PUBLIC warning, and between the gateway's deploy and the House's the two lists differ by
  hundreds of names.

```diff
diff --git a/league/ci.py b/league/ci.py
index d540032..44afc96 100644
--- a/league/ci.py
+++ b/league/ci.py
@@ -178,9 +178,17 @@ FORBIDDEN: tuple[str, ...] = (
 #: and the equity review and level rule (elane_review.py): selection constants and secrecy rules, like dlane.py. The
 #: updater never self-deploys a change to them from this release on; the gateway's merge route refuses them once its
 #: own follow-up adds the five to MERGE_FORBIDDEN (gateway/ ships separately, as it did for E1).
+#: THE PANEL LANE (release E4, Oct 2026): its swarm lane (league/swarm/elane_xs.py: the Train bar equity-xs-v1, the one
+#: Validation try, the look under the screen XS1, lineage, the look cap of an agenda cell and the seat rule that keeps
+#: a style-open passer out of a live seat, the captain's A22: selection constants and secrecy rules, like
+#: elane_train.py) and the universe generator (scripts/gen_universe.py: what writes the constitution's and the
+#: gateway's stock lists, so a money rule's author). The rest of the lane is behind the wall above already: league/xs/
+#: (the panel's evidence, its screen and its live adapter), league/ops/ (its data jobs) and docs/benchmarks/ (XS1's
+#: receipt). The two wait here with E2's five for the same gateway follow-up.
 PENDING_GATEWAY: tuple[str, ...] = (
     "league/swarm/elane_births.py", "league/swarm/elane_train.py", "league/swarm/elane_yield.py",
     "league/swarm/elane_seal.py", "league/swarm/elane_review.py",
+    "league/swarm/elane_xs.py", "scripts/gen_universe.py",
 )
 FORBIDDEN += PENDING_GATEWAY
 #: The one path the gateway's merge route refuses (`gateway/lib/protected.mjs` MERGE_FORBIDDEN) that is not FORBIDDEN:
@@ -577,6 +585,17 @@ GATEWAY_STOCK_SWITCH = re.compile(r'^\s*"STOCK_BUYS_REAL"\s*:\s*"([^"\\]*)"\s*,?
 #: The gateway's per-symbol caps as a share of equity, by class (`account.stockCaps`): the House's
 #: `equity_money.position_share` never above them.
 GATEWAY_STOCK_SHARES = {"etf": "STOCK_ETF_EQUITY_SHARE", "stock": "STOCK_SINGLE_EQUITY_SHARE"}
+#: How many tickers a side `stock_agreement` names; the rest are counted. Release E4's universe is hundreds of stocks,
+#: deployed at the gateway before the House: were the two deploys not made between two pre-opens, the pre-open's
+#: warning (PUBLIC) would otherwise print every one of them, each morning.
+AGREEMENT_NAMES = 10
+
+
+def _named(entries: list[str]) -> str:
+    """At most `AGREEMENT_NAMES` of `entries`, and how many more there are and how many in all; "none" for none."""
+    if len(entries) <= AGREEMENT_NAMES:
+        return ", ".join(entries) or "none"
+    return f"{', '.join(entries[:AGREEMENT_NAMES])} and {len(entries) - AGREEMENT_NAMES} more ({len(entries)} in all)"
 
 
 def gateway_stock_universe(root: Path = REPO) -> tuple[dict[str, str], list[str]]:
@@ -609,7 +628,8 @@ def stock_agreement(table: Any, *, universe: Any, buys_on: Any, shares: Any, sou
     ONE comparison, read from the release's files by `gateway_stock_problems` and from the deployed gateway's
     `/v1/health` by the pre-open job (league/ops/preopen.py): the universe is exactly the constitution's, symbol and
     class; `enabled` True requires the gateway's buys on (the gateway may be on while `enabled` is False: that row is the
-    switch, A8); and each class's `position_share` is never above the gateway's share for it."""
+    switch, A8); and each class's `position_share` is never above the gateway's share for it. A difference names at
+    most `AGREEMENT_NAMES` tickers a side, in ticker order, and counts the rest."""
     from decimal import Decimal, InvalidOperation
 
     if not isinstance(table, dict):
@@ -622,8 +642,7 @@ def stock_agreement(table: Any, *, universe: Any, buys_on: Any, shares: Any, sou
         extra = sorted(f"{s} ({k})" for s, k in got.items() if wanted.get(s) != k)
         missing = sorted(f"{s} ({k})" for s, k in wanted.items() if got.get(s) != k)
         problems.append(f"{source}: the gateway's STOCK_UNIVERSE and equity_money.universe differ (gateway only: "
-                        f"{', '.join(extra) or 'none'}; constitution only: {', '.join(missing) or 'none'}): they change "
-                        "together")
+                        f"{_named(extra)}; constitution only: {_named(missing)}): they change together")
     if table.get("enabled") is True and buys_on is not True:
         problems.append(f"{source}: equity_money.enabled is true but the gateway's STOCK_BUYS_REAL admits no buy: switch "
                         "the gateway on first (the House's row is the switch)")
```

Held by: `league.tests.test_ci` (16.2).

### 16.2 `league/tests/test_ci.py`

Anchors: `TheEquityLane.test_the_tree_and_the_swarm_lane_are_protected` (the `PENDING_GATEWAY` tuple it holds); a new
test before `test_every_file_of_the_decider_childs_sealed_runtime_is_protected`; and
`test_the_universe_changes_with_the_gateways_list`, rewritten, with a new test after it.

- `PENDING_GATEWAY` is held to its seven entries; the two new paths, and the files the panel lane adds behind the
  existing wall, are refused for every role and by the updater (`protected_changes`).
- `test_the_universe_changes_with_the_gateways_list` no longer replaces `COST: 'stock',` or uses NFLX as "a stock the
  list lacks": after the universe deploy the stock pairs are generated and NFLX is a member. It puts its entries
  where the list OPENS and uses TQQQ (a leveraged ETF: on neither list, ever). It passes on E1's list and on a
  generated one.
- `test_a_difference_names_at_most_ten_tickers_a_side_and_counts_the_rest`: both directions, both sides at once, ten
  named whole and the eleventh counted, and through the release's own files.

```diff
diff --git a/league/tests/test_ci.py b/league/tests/test_ci.py
index f6e9b29..1205f7c 100644
--- a/league/tests/test_ci.py
+++ b/league/tests/test_ci.py
@@ -280,10 +280,12 @@ class TheEquityLane(unittest.TestCase):
 
     def test_the_tree_and_the_swarm_lane_are_protected(self):
         # E1's four entries are in the gateway's merge list since its follow-up; release E2's five modules (the equity
-        # births, Train bar, route rule, seal and review) wait here for the gateway's next one.
+        # births, Train bar, route rule, seal and review) wait here for the gateway's next one, and with them release
+        # E4's two: the panel's swarm lane and the universe generator.
         self.assertEqual(ci.PENDING_GATEWAY, ("league/swarm/elane_births.py", "league/swarm/elane_train.py",
                                               "league/swarm/elane_yield.py", "league/swarm/elane_seal.py",
-                                              "league/swarm/elane_review.py"))
+                                              "league/swarm/elane_review.py",
+                                              "league/swarm/elane_xs.py", "scripts/gen_universe.py"))
         for entry in ("league/equity/", "league/swarm/elane.py", "league/xs/", "ltcm/broker.py", *ci.PENDING_GATEWAY):
             self.assertIn(entry, ci.FORBIDDEN)
         for path in ("league/equity/sizing.py", "league/equity/live.py", "league/equity/INTERFACES.md",
@@ -308,6 +310,38 @@ class TheEquityLane(unittest.TestCase):
                              ["league/equity/sizing.py", "league/swarm/elane.py", "league/swarm/elane_seal.py",
                               "league/swarm/elane_train.py", "league/xs/child.py", "ltcm/broker.py"])
 
+    def test_the_panel_lane_and_the_universe_generator_are_protected(self):
+        """Release E4 (E4-SPEC 2.5, the fixed judges it adds): the panel's evidence and its screen XS1 (league/xs/), its
+        data jobs (league/ops/) and XS1's receipt (docs/benchmarks/) were behind the wall already; its swarm lane
+        (league/swarm/elane_xs.py: the Train bar, the look, lineage, the seat rule of the captain's A22) and the
+        universe generator (scripts/gen_universe.py: the constitution's and the gateway's stock lists) join it. No role
+        may change one and the updater never self-deploys one."""
+        for entry in ("league/swarm/elane_xs.py", "scripts/gen_universe.py"):
+            self.assertIn(entry, ci.FORBIDDEN)
+            self.assertIn(entry, ci.PENDING_GATEWAY)
+        for path in ("league/swarm/elane_xs.py", "League/Swarm/Elane_XS.py", "scripts/gen_universe.py",
+                     "Scripts/Gen_Universe.py",
+                     # behind the wall before E4, and the files the panel lane adds there
+                     "league/xs/screen.py", "league/xs/placebo.py", "league/xs/style.py", "league/xs/book.py",
+                     "league/xs/identity.py", "league/xs/XS.md", "league/ops/equity_universe.py",
+                     "league/ops/equity_panel.py", "league/ops/equity_spreads.py", "league/ops/xs_zero_edge.py",
+                     "league/ops/forward_xs.py", "docs/benchmarks/equity_screen_xs_1.json", "league/constitution.py",
+                     "league/swarm/policy.json", "gateway/lib/caps.mjs"):
+            self.assertTrue(ci.guard([path], None), path)
+            for role in ci.ROLE_PATHS:
+                self.assertTrue(ci.guard([path], role), (path, role))
+        from league.updater import protected_changes
+
+        with tempfile.TemporaryDirectory() as tmp:
+            running, incoming = Path(tmp) / "running", Path(tmp) / "incoming"
+            for root, text in ((running, "X = 1\n"), (incoming, "X = 2\n")):
+                for rel in ("league/swarm/elane_xs.py", "scripts/gen_universe.py", "league/swarm/pool.py",
+                            "scripts/economics.py", "league/xs/screen.py"):
+                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
+                    (root / rel).write_text(text)
+            self.assertEqual([p.split(":")[0] for p in protected_changes(incoming, running)],
+                             ["league/swarm/elane_xs.py", "league/xs/screen.py", "scripts/gen_universe.py"])
+
     def test_every_file_of_the_decider_childs_sealed_runtime_is_protected(self):
         """What the isolated child may import decides real orders (an options decision, an equity decision, every
         Validation run and look), so no role may change it and the updater never self-deploys it: every file of
@@ -351,21 +385,82 @@ class TheEquityLane(unittest.TestCase):
         gone = self.tree(wrangler={self.SWITCH_LINE: ""})
         self.assertIn("STOCK_BUYS_REAL must be set once", " ".join(gone))
 
+    #: Where the gateway's list begins. The tests below put an entry there and name no stock but BRK.B, which every
+    #: list holds: release E4 generates the stock pairs (scripts/gen_universe.py), and a test that named one of them,
+    #: or a well-known ticker as "not on the list", would be a test of one day's list.
+    LIST_OPENS = "export const STOCK_UNIVERSE = Object.freeze({"
+
     def test_the_universe_changes_with_the_gateways_list(self):
-        refused = self.tree(caps={"COST: 'stock',": "COST: 'stock', NFLX: 'stock',"})
-        self.assertIn("gateway only: NFLX (stock)", " ".join(refused))
+        self.assertEqual(self.caps.count(self.LIST_OPENS), 1)
+        # TQQQ: a leveraged ETF is on neither list, ever (the constitution's `universe` rule).
+        refused = self.tree(caps={self.LIST_OPENS: self.LIST_OPENS + "\n  TQQQ: 'stock',"})
+        self.assertIn("gateway only: TQQQ (stock)", " ".join(refused))
         refused = self.tree(caps={"TLT: 'etf', GLD: 'etf',": "TLT: 'etf',"})
         self.assertIn("constitution only: GLD (etf)", " ".join(refused))
         refused = self.tree(caps={"'BRK.B': 'stock'": "'BRK.B': 'etf'"})
         self.assertIn("gateway only: BRK.B (etf)", " ".join(refused), "a class is part of the list")
         refused = self.tree(constitution={'"TLT", "GLD"],': '"TLT"],'})
         self.assertIn("gateway only: GLD (etf)", " ".join(refused))
-        self.assertIn("STOCK_UNIVERSE has an entry", " ".join(self.tree(caps={"COST: 'stock',": "COST: 'stock', SQQQ,"})))
-        self.assertIn("twice, or not etf or stock", " ".join(self.tree(caps={"COST: 'stock',": "COST: 'stock', SPY: 'etf',"})))
-        self.assertIn("twice, or not etf or stock", " ".join(self.tree(caps={"COST: 'stock',": "COST: 'bond',"})))
+        self.assertIn("STOCK_UNIVERSE has an entry", " ".join(self.tree(caps={self.LIST_OPENS: self.LIST_OPENS + "\n  SQQQ,"})))
+        self.assertIn("twice, or not etf or stock",
+                      " ".join(self.tree(caps={self.LIST_OPENS: self.LIST_OPENS + "\n  SPY: 'etf',"})))
+        self.assertIn("twice, or not etf or stock",
+                      " ".join(self.tree(caps={self.LIST_OPENS: self.LIST_OPENS + "\n  TQQQ: 'bond',"})))
         moved = self.caps.replace("export const STOCK_UNIVERSE", "export const STOCK_LIST")
         self.assertIn("STOCK_UNIVERSE must be declared once", " ".join(self.tree(caps={self.caps: moved})))
 
+    def test_a_difference_names_at_most_ten_tickers_a_side_and_counts_the_rest(self):
+        """Release E4's universe is hundreds of stocks, deployed at the gateway BEFORE the House (a longer list there is
+        inert). Were the two deploys not made between two pre-opens, the pre-open's PUBLIC warning would print every
+        one of them each morning: `stock_agreement` names at most `AGREEMENT_NAMES` a side, in ticker order, and
+        counts the rest. A short difference is named whole, as before. Invented tickers only."""
+        import copy
+
+        from league.constitution import CONSTITUTION
+
+        self.assertEqual(ci.AGREEMENT_NAMES, 10)
+        em = copy.deepcopy(CONSTITUTION["equity_money"])
+        mine = {s: k for k in ("etf", "stock") for s in em["universe"][k]}
+        invented = [f"ZZ{a}{b}" for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRST"]
+        self.assertEqual((len(invented), len(set(invented) & set(mine))), (520, 0))
+        shares = {"etf": "0.5", "stock": "0.2"}
+
+        def agreement(table, universe):
+            return ci.stock_agreement(table, universe=universe, buys_on=True, shares=shares, source="the deployed gateway")
+
+        self.assertEqual(agreement(em, mine), [])
+        # The gateway first (the order of the universe deploy): its list is the longer by 520.
+        [said] = agreement(em, {**mine, **dict.fromkeys(invented, "stock")})
+        self.assertEqual(said, "the deployed gateway: the gateway's STOCK_UNIVERSE and equity_money.universe differ (gateway "
+                               "only: " + ", ".join(f"{s} (stock)" for s in invented[:10]) + " and 510 more (520 in all); "
+                               "constitution only: none): they change together")
+        self.assertLess(len(said), 400)
+        # The House first (never the order, and no wrong order either: its new buys would be refused): the same bound.
+        grown = copy.deepcopy(em)
+        grown["universe"]["stock"] = em["universe"]["stock"] + invented
+        [said] = agreement(grown, mine)
+        self.assertIn("(gateway only: none; constitution only: ZZAA (stock), ZZAB (stock), ", said)
+        self.assertIn("ZZAJ (stock) and 510 more (520 in all)): they change together", said)
+        self.assertNotIn("ZZAK", said)
+        self.assertLess(len(said), 400)
+        # Both sides at once, each bounded on its own; a class that differs is a difference on both sides.
+        [said] = agreement(grown, {**mine, **dict.fromkeys(invented[:300], "etf")})
+        self.assertEqual(said.count(" (etf)"), 10)
+        self.assertEqual(said.count(" (stock)"), 10)
+        self.assertIn("ZZAJ (etf) and 290 more (300 in all); constitution only: ZZAA (stock)", said)
+        self.assertIn("and 510 more (520 in all)): they change together", said)
+        # Ten are named whole; the eleventh is counted.
+        [said] = agreement(em, {**mine, **dict.fromkeys(invented[:10], "stock")})
+        self.assertIn("(gateway only: " + ", ".join(f"{s} (stock)" for s in invented[:10]) + "; constitution only: none)", said)
+        [said] = agreement(em, {**mine, **dict.fromkeys(invented[:11], "stock")})
+        self.assertIn("ZZAJ (stock) and 1 more (11 in all); constitution only: none)", said)
+        # And through the release's own files, as `check_equity` reads them.
+        pairs = " ".join(f"{s}: 'stock'," for s in invented)
+        refused = self.tree(caps={self.LIST_OPENS: self.LIST_OPENS + "\n  " + pairs})
+        self.assertEqual(len(refused), 1)
+        self.assertIn("gateway only: ZZAA (stock), ", refused[0])
+        self.assertIn(" and 510 more (520 in all); constitution only: none)", refused[0])
+
     def test_the_position_shares_stay_within_the_gateways(self):
         self.assertEqual(self.tree(constitution={'"position_share": {"etf": "0.50", "stock": "0.20"}':
                                                  '"position_share": {"etf": "0.40", "stock": "0.10"}'}), [], "tighter")
```

### 16.3 `league/ops/preopen.py`: the options population is counted by the store's own guard

Anchor: in `collect`'s `swarm()`, the statement that reads `alive` (the comment "The options population against its
floor").

Found while building: check 5 holds the OPTIONS population to its floor with its own copy of the structure list
(`structure NOT IN ('etf', 'stock')`). A panel family (structure "panel", born in mode "train") would be counted as an
options family and could hide a population under its floor. The count now reads `league.swarm.store.OPTIONS_ONLY_SQL`,
which package G's patch 1 builds from `EQUITY_STRUCTURES`: at the base the two strings are equal (no behaviour
changes), and the day the store names "panel" the count follows. AT THE INTEGRATION HEAD (`feat/equity-e2-int`
`a4514e83`) `collect`'s `bands()` has a second copy of the same literal (the `live_fams` read, added by E1's review
fixes): it takes the same replacement (the section "At the integration head" below has the hunk).

```diff
diff --git a/league/ops/preopen.py b/league/ops/preopen.py
--- a/league/ops/preopen.py
+++ b/league/ops/preopen.py
@@ -208,9 +208,12 @@
         # heartbeat, or the guard's check inside it, written in between is stamped after `now`.
         read_at = float(clock()) if clock is not None else now
         st = hb.get("status") or {}
-        # The options population against its floor: the equity lanes' families are their own (release E2).
-        alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT count(*) FROM families WHERE retired_at IS "
-                                                                           "NULL AND structure NOT IN ('etf', 'stock')"))[0]
+        # The options population against its floor: the equity lanes' families are their own (release E2), a panel
+        # family among them (release E4): the store's own guard names every equity structure.
+        from ..swarm.store import OPTIONS_ONLY_SQL
+
+        alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(
+            db, f"SELECT count(*) FROM families WHERE retired_at IS NULL AND {OPTIONS_ONLY_SQL}"))[0]
         return {"raw_is_object": isinstance(raw, dict), "raw_live": raw.get("live") if isinstance(raw, dict) else None,
                 "defaults_live": dict(SS.DEFAULTS["live"]),
                 "eff_gym": {k: (eff.get("gym") or {}).get(k) for k in ("enabled", "image_checkpoint", "gate_checkpoint")},
```

Held by: `league.tests.test_equity_money.ThePreopenEquityCheck.test_the_options_population_is_counted_by_the_stores_own_guard`
(in 15.1's diff; it passes with and without package G's patch 1).

### 16.4 `docs/operations.md`: the panel lane

Anchors: a new section before "## The equity lanes' births (release E2, Oct 2026)"; and one sentence of E1's "The
equity identity" paragraph (the panel kind's slot is no longer empty).

The section: what the lane is and why; the two releases and what each moves; the switch and what each mode needs; the
two things that are owed and hold real money back (the forward twin, the probe); the contract; the data and the
quiet windows; the screen XS1 as the receipt fixes it; the three duties the pre-registration gives the House; **the
captain's A22**; a session of a live panel program; **E4-SPEC 10.5's live rules, word for word** (a block quote,
unedited, with the three later amendments stated after it, never inside it); **the universe deploy** (the generator's
run, the one commit, the order of the two deploys, the two-pre-opens rule, verify, rollback, the yearly run); the
lane's stop, one mode down at a time; what moves which identity; the deploy class; the alarms; the cost; verify;
what is not handled. The screen's bar (c_XS) is not restated as a number: the docs name the receipt as its source,
because the captain may replace it.

THE DOCS PASS IS THE INTEGRATOR'S TO FINISH: this section was written from the contract (`league/xs/E4_INTERFACES.md`
and the pinned pre-registration) while the other packages were being built. Where a package's code as landed says
otherwise (an event's name, a kv key, a job's figure), the code wins and this text is corrected.

```diff
diff --git a/docs/operations.md b/docs/operations.md
index 2e9facf..bc04035 100644
--- a/docs/operations.md
+++ b/docs/operations.md
@@ -8,6 +8,351 @@ enabled. This page describes the tree it is in, release V3-A part 1, which is li
 what production runs today. Current direction is in [the goal](goals/LTCM_OPTIONS_SWARM.md); the old operator's page
 is [archive/docs/operations.md](../archive/docs/operations.md).
 
+## The panel lane (release E4, "breadth", Oct 2026): `feat/equity-e4`, not deployed
+
+E1 gave the equity lanes a live path and E2 made the swarm breed share programs for it, on four index ETFs. E4 opens
+the place where independent history is: **the point-in-time S&P 500 PANEL**. A panel program picks 5 to 12 names out
+of the day's index members by a symmetric cross-sectional rule (reversal, momentum, industry momentum, low
+volatility, rotation), sees salted slots with no ticker and no date, and is judged on its daily **RESIDUAL** (its P&L
+after its costs, less the cost-free P&L of the cells its names were picked from) against matched placebo portfolios,
+by the screen **XS1**. The contract between the release's packages is `league/xs/E4_INTERFACES.md`; what an author is
+shown is `league/xs/XS.md`; the lane in the swarm is `league/swarm/E4.md`; what went into E1's and E2's files is
+`league/swarm/e4_patches/` (one file an author; a record once applied).
+
+**Why a panel, and why a residual** (measured the week it was built, rule-level): a raw-P&L screen cannot be opened to
+single stocks or sectors, because an author who knows which symbol won a known year passes it far above the owner's
+15% wall at zero edge (the captain's A19); and four index ETFs hold only about ten independent lineages. A basket
+program closes several lots a week, and its residual does not care which way the index went.
+
+**It ships off, in two releases.**
+- **R-E4a (research; an owner deploy; NO constitution change, so no money-digest move):** the data jobs, `league/xs/`,
+  the swarm hooks, XS1's receipt and its pin. policy.json ships `elane.panel.mode` "off". The panel's own identity is
+  adopted for the first time (no panel band exists yet).
+- **R-E4b (THE UNIVERSE; one commit; deployed separately; the money digest moves ONCE):** the constitution's
+  `equity_money.universe.stock` grows from E1's 18 names to the panel's tradable union, with the same list at the
+  gateway. See **The universe deploy** below.
+- Neither moves the equity evidence identity (A13) or the options execution fingerprint: nothing of E4 is in
+  league/equity's evidence import closure, and no file under `league/live/` or `league/gym/` changes
+  (`league/tests/test_xs_identity.py`; `league/tests/test_gen_universe.py` holds that neither identity reads a file of
+  the universe's). No options evidence and no ETF evidence is reset.
+
+**With every E4 switch off nothing of E4 runs, spends or trades:** no birth, no Train run, no fetch of the live path,
+no model question. The data jobs are registered and read only (through the gateway's data routes and its web reader).
+
+**The switch** is `elane.panel.mode` (policy.json; swarm.json over it; read on the next loop pass, no deploy). On the
+owner's machine: `python3 set_swarm.py elane.panel.mode=train --apply`. Each step is the captain's, and each falls back
+to the one before:
+
+| mode | what it opens | what it needs first (the EFFECTIVE mode, `league/swarm/elane_xs.py` `mode`, reads lower without it) |
+|---|---|---|
+| "off" | nothing | (the shipped value) |
+| "train" | panel births in the equity pass, and the Train bar **equity-xs-v1** | `elane.mode` "gate" (E1's switch); the panel store written (`equity_panel`) with a coverage verdict that is not "insufficient" |
+| "gate" | the one Validation try and the one look under XS1 | XS1's receipt pinned (no receipt, no look); the spreads table covering at least `spreads_min_share` of the eligible names (below it a Train pass is "provisional costs" and the mode reads "train") |
+| "live" | a passer may take one of E1's roster seats | `live_ready`: the universe deploy in force, today's tradable share of eligible names at least `live_min_tradable_share`, the committed universe younger than `universe_max_age_days`, the last nightly I6 equal, AND the forward twin's marker (`xs-twins.json`). Any one missing: the mode reads "gate" |
+
+**Two things are owed, and both hold real money back, by design.** (1) **The forward twin** (package J:
+`league/ops/forward_xs.py`, the registry row and the nightly shadow twin of a panel program) is built on release E3's
+forward modules and waits for E3. While it is not merged, or its nightly run has not written the marker, **mode "live"
+reads as "gate"**: no panel program opens a position the forward record is not shadowing. (2) **No panel look runs
+until release E3's contamination probe has run once with the panel strata** (the captain's A22 (3), below): mode
+"gate" scores Validation and keeps both Train series, and every look waits. So the order to a first live panel trade
+is: R-E4a, the spreads backfill (about nine nights), E3 merged, the probe's panel strata and the twin merged, one
+forward night, the universe deploy, a free seat and room in the loss window.
+
+**What a panel program sees and may do** (the pre-registered contract C-XS-1; `league/xs/ctx.py`, `program.py`,
+`engine.py`): after the close, one slot an eligible name (a member of the index today and for the next two sessions,
+with its history and its three characteristics), each slot a salted number that is stable inside one run and unrelated
+across runs; per slot only SCALE-FREE fields (`ret`, `oret`, `iret`, `range`, `rel_volume`, a salted `sector` code, a
+`beta` to two decimals) and the same fields of the market; four calendar counts. **No ticker, no date, no price
+level, no share count, no dollar volume, no size or liquidity rank, no event flag.** Under them every price is
+dithered by half a cent before any ratio is taken, so the cent grid cannot give a level back. It answers a target
+`{slot: weight}` at the open or the close, long only, each weight at most 0.20, the sum at most 1.00, 5 names or more
+when invested. **The KEEP rule** turns a target into lots: a held name that is still in the target is kept untouched; a
+name that left it is sold whole; a new name is bought as one lot; at most 12 buys and 12 sells, and a target that
+needs more is refused whole. The House's own exits are the same in the Gym and live: a name out of the eligible set
+at any close is sold at the next open, a lot at its maximum hold likewise, and a name whose bars end exits at its last
+close less a 30% haircut (for the lot, its placebo counterparts and its cell's members alike). **The standing
+target:** a buy a session could not make (a sale that filled late, a quote too wide, a budget cut, a venue refusal) is
+planned again at each following close until the next called decision, in the Gym and live by one function.
+
+**The data** (House only; nothing here is ever committed or sent off the House; `<state>/equity-daily/`):
+- `universe/`: point-in-time membership from the public spell file `sp500_ticker_start_end.csv` of
+  github.com/fja05680/sp500 at a pinned commit, extended by the changes table of the English Wikipedia article, read
+  through the gateway's web reader (`league/ops/equity_universe.py`, job `equity_universe`); the House's `SALT` (32
+  random bytes, written once, never in a request, a log, an event or a manifest); `tradable.json`, the dateless
+  36-month union the universe deploy is generated from.
+- `panel/`: raw and adjusted daily bars of every member spell from 2016, fetched with `asof` inside the spell, with the
+  membership and tradable masks and the half-spread table (`league/ops/equity_panel.py`, job `equity_panel`).
+  **2020 is never fetched; 2016 and 2021 are history only** (no run has a session in either): the panel's Train years
+  are 2017-19 and 2022-24, six of them.
+- `spreads.json` (job `equity_spreads`: 2-second quote windows at the instants the book trades, on Train-era sessions
+  only), `neff.json` (job `equity_neff`), `french/` (job `french`: skipped, and no alarm, while the House has no route
+  to the library).
+- `live-bars/<day>.npz`: the 16:20 fetch a live panel decision read, kept for five sessions and audited the next
+  morning; `xs-twins.json`: the twin marker (ids and days only).
+- **Coverage is the fact the release rests on** (member-days with a valid bar; `coverage_min` 0.97): the panel
+  manifest's verdict is "ok", "low_coverage" (one Train year below the line is dropped from the bar, and said on the
+  Train map) or "insufficient" (the lane reads "off"). Any verdict but "ok" is the owner's paid-data question.
+- **The quiet windows.** No E4 job and no panel Train run may be RUNNING at 09:25-09:45 or 15:50-16:35 ET on a session:
+  each asks `league.xs.config.quiet(now, need_s)` with its own wall-clock limit before it starts, and a start that
+  could still be working at a wall is skipped (not lost: it runs at its next trigger). The one exception is the live
+  path's own 16:20 fetch, 16:30 decide and 08:30 re-read of a LIVE panel program, which run in the live process as
+  E1's do.
+
+**The screen XS1** (`league/xs/screen.py`; its receipt `docs/benchmarks/equity_screen_xs_1.json`, the study
+XSCREEN-1's, copied verbatim and pinned by sha256 in policy.json `elane.screens.equity_xs`; CI holds the pin to the
+file). **Every threshold is read from the pinned receipt at runtime; none is written in code.** With no pinned
+receipt the screen refuses every program. The rule, per program:
+- **The pre-check**, on Validation (calendar 2025): 20 lots fully exited or 120 sessions with a lot held, AND the
+  residual's sum above zero. A failed pre-check spends no look, and it spends the lineage's only try: there is no
+  Validation-only retry.
+- **The one look**, on the 194 holdout sessions (2026-01-02 through 2026-10-09), from one run that starts flat at
+  Validation's first session: pass = the pre-check AND the residual's sum above zero AND **the stress residual's sum
+  above zero** (1.5 times the half-spread and every sell fee twice) AND the holdout t at or above **c_used** AND the
+  placebo rank at or under the receipt's `alpha_plac` (ahead of 88% of the receipt's 999 matched placebo portfolios,
+  whose seed is fixed before the look from the receipt's and the program's hashes).
+- **c_used = max(c_XS, the program's own floor + the receipt's margin)**: the screen's bar every program meets, raised
+  by the program's own exact 12% point of the holdout-only t on its own Train-era series when that is higher. The own
+  floor can only raise the bar. A program whose floor cannot be computed, or whose bar is above 5.00, takes no look
+  (nothing spent).
+- **Lineage:** one look a lineage. Same lineage = the same template, or a Train daily correlation of 0.7 or more, IN
+  THE RESIDUAL OR IN THE UNIVERSE EXCESS, with a panel program already looked at OR already refused at the pre-check. A
+  lineage that took an XS1 look takes no S2 look, and the reverse. No Validation, look, placebo-rank or forward
+  outcome of a panel program is ever shown to a generator, a researcher or the diagnostician.
+- **What a pass says, and does not.** It says the picks beat random same-style picks after their costs. It does NOT say
+  the program beats the index or makes money: market, sector, beta and momentum direction are not counted as edge.
+  The receipt's sentence says so beside every live panel trade, with the study's measured false-positive figures and
+  what the screen does not match (sub-industry, size, value).
+- **The receipt may be replaced.** XS1 was adopted at the bar the study registered; the captain may land a rebuilt
+  receipt at a higher bar. That is one file and its pin (a CI test holds the two together); no code changes, and the
+  conformance vectors run under their own bar, so none moves.
+
+**The three duties the pre-registration gives the House** (`league/swarm/elane_xs.py`):
+1. **Both Train series of every program that reaches the pre-check are kept**, passed or refused: the residual and the
+   universe excess, by session (sealed family state; the lineage rule reads them for every later program, and no
+   adoption ever clears them).
+2. **The XS1 looks of each agenda cell are counted.**
+3. **Beside every live panel trade the House states the sentence its receipt fixes**, filled for the program: its bar
+   and own floor, its own in-sample rate, the earlier looks in its mechanism cell, whether its P&L is basket-led or
+   selection-led, its style label and its flags. The `dlane` report prints it under the label EQUITY (PANEL).
+
+**The captain's A22: what the House holds before any real money on an XS1 pass** (from the study's review; House
+rules, the receipt is pinned as built):
+1. **A STYLE-OPEN program takes no live seat on an XS1 pass alone.** The study measured that a no-skill tilt to a
+   style that happened to win the holdout passes far above the owner's wall. So the House computes each panel
+   program's loadings on size, beta, 12-1 momentum and volatility from its Train holdings (`league/xs/style.py`: a
+   lot's rank among the day's eligible names at its decision close; a program's loading is the weighted mean over
+   its Train lots) and marks it style-open by one fixed, tested rule (any loading at or beyond the rule's tilt, or
+   too few lots to read). **A style-open passer is RECORDED AND SHADOWED, NEVER SEATED:** the look says passed with
+   seat "style-open", the family takes no band and no proof, and the report names it and why. Its way to a seat is
+   the forward route. The rule is holdings-based and direction-blind; its cost, stated: a momentum or a low-volatility
+   program is style-open by construction.
+2. **At most 2 XS1 looks an agenda cell** until a forward verdict exists in that cell (the receipt's
+   `family_wise_8_max`: one zero-edge mechanism given eight looks passed at least one in more than half of the
+   study's worlds at its worst). No forward verdict can exist before the forward route is measured, so the cap is
+   flat in this release. A look the cap holds back is not spent: the family waits.
+3. **The equity code review and the contamination probe run BEFORE a panel look.** The review's rubric for a panel
+   program refuses an embedded return table and any recognition of a calendar period (and any use of the slot numbers
+   beyond naming targets, any search for a price level). The probe is release E3's, with the panel strata: until it
+   has a published result for the route that wrote the program, the look waits.
+4. **A ninth conformance vector**, for the 2022-24-alone floor cell, beside the study's eight
+   (`league/tests/fixtures/xs1_conformance_c.json`; `league/tests/test_xs_screen.py`).
+
+**Read it** (read-only, on the box): the swarm log; `swarm.sqlite` events `swarm.status` with
+action `elane_xs_train`, `elane_xs_window` or `xs_evaluator_adopted`, and `swarm.gate` look events with screen "XS1";
+a panel family's state key `elane_xs` (its Train record: each version's verdict, fails and facts); kv
+`elane_xs_cpu`, `elane_xs_zero_edge` (the weekly zero-edge pass rate of the bar: an alarm above 5%) and
+`elane_xs_alerts`; the House's events `equity.universe`, `equity.panel` and `equity.rebalance` (counts and verdicts
+only: never a price, never a ticker list); `<state>/equity-daily/panel/PANEL_MANIFEST.json` (coverage by year, the
+verdict, `hs_share`, the nightly `i6`, `live_from`); in `live.sqlite`, `eq_rebalances` (one row an instance and
+decision session) and `eq_instances.kind`.
+
+**A session of a live panel program.** From 16:20 ET the chunked fetch of the day's columns (about 28 gateway calls
+over two or three ticks; only while a panel program is live), kept as that day's file; at 16:30 the decide in the
+live process's decider (no program code on a hold day; the eligibility of every held name is read every day); at
+08:30 the bars are read again and compared with the kept file (a price that differs cancels that decision's planned
+buys); next session E1's own windows send the intents, sells first. Every buy goes through E1's sizing as a stock:
+at most 20% of the sleeve and of equity, the invested cap, the House's cash rule, **the shared loss budget with a
+stock weighing 0.40**, the $10 minimum. Every wall of E1 holds: long only, cash only, the kill switch and the stops,
+never a forced or hand-placed trade. For a panel program a HOLD-day fetch failure of a held name is an alarm and
+never counts toward the two-failed-decides exit (the captain's A17); a failed decide on a rebalance day still counts.
+
+**The panel's live rules (PRE-REGISTERED before `elane.panel.mode` may be "live").** Goal item 4 asks that live
+results decide sizing up and demotion by a rule fixed before the first live trade. The text below is the build
+spec's section 10.5, copied word for word (its "B10", "8.4", "10.6" and "section 19" are that document's own
+numbers: the book patch that builds the record, the Validation step that writes the sigma, the forward twin, and the
+owner's open decisions; "70948154" is the E1 commit it read). It was written before three of the captain's
+amendments were in force; they change its dollar examples and none of its rules, and are stated after it.
+
+> Goal item 4: live results decide sizing up and demotion by a rule fixed before the first live trade. E1's rules (`league/equity/bands.py` `edm1`,
+> `sized_up`, `sized_sleeve_share`; the constitution's `demotion.*` and `sized.*` numbers) are UNCHANGED, as functions and as numbers. What changes is
+> what a panel program's record feeds them, because they read each lot as an independent trade and a basket's lots are not: five lots bought on one
+> date and sold on another share one market move and one fill minute. Read by lot, (1) the first rebalance's five closes meet `twin_min_closes` 5 with
+> five copies of ONE date's fill gap, and a single 09:32 after a rising open sets the program to exits only for good; (2) two months in which the
+> basket loses 3% a month give ten returns summing below -1.645 x sigma x sqrt(10) and demote the program on beta while its residual x is positive; (3)
+> four weekly rebalances in a rally give twenty closes and a lower bound above zero from four dates. So, for an instance of kind "panel" only (B10,
+> `xs.book.date_record`; plumbing: no evidence identity and no money digest moves, and no constitution number changes):
+> - **One observation a close DATE.** The version's closed ":r" lots are grouped by `exit_day`. `returns` = one a date, in date order: the date's
+>   summed lot cash over its summed entry notional. `n` = the number of close dates. `twin_gaps_bp` = one a date: the entry-notional-weighted mean of
+>   `gap_bp` over that date's lots with a priced twin (a date with none gives none). `pnl` and `realized_net` are dollars, as now.
+> - **Sigma.** `validation_r_sd` = the version's `sd_date_return` (the 2025 k 1.0 run's sd of the same per-date return; 8.4 writes it under E1's
+>   `validation_r_sd_by_version`), so EDM1's sigma is a per-date sd from Validation, never the live lots' own; with none (under 2 close dates in 2025)
+>   E1's fallbacks apply to the per-date returns.
+> - **The same-risk buy-and-hold.** `bh_pnl` = the lots' dollars held in SPY over their own sessions: the sum over closed lots of entry notional x
+>   (SPY's adjustment=all close on the exit day / on the session before the entry day - 1). ONE BASIS, by E1's own rule (`_bh_pnl` at 70948154: two
+>   closes from two fetches straddling an ex-date are not one series): every close comes from ONE fetch of SPY over the lots' whole span
+>   (`adapter.spy_closes`), made only by the daily band sync and only once the record holds the close dates sizing up needs (`sized.min_trades`:
+>   the figure is read by nothing else); None before that and when a close is missing (sizing up then fails `beat_bh`, as E1's does). E1's
+>   per-symbol reading would call a stock picker's benchmark the very stocks it picked.
+> - **What each E1 threshold then means for a panel program:** EDM1's statistical leg acts from 10 close DATES (`demotion.min_trades`), its twin leg
+>   from 5 dates with a priced twin (`twin_min_closes`), sizing up from 20 dates (`sized.min_trades`) with the mean per-date return's lower bound above
+>   zero, P&L above `bh_pnl`, and 5 sessions at Probe.
+> - **THE COST, stated.** EDM1's statistical leg cannot demote a panel program before its 10th close date: 10 weeks for a weekly program, 10 months
+>   for a monthly one (by lot it would have acted after two dates, wrongly). Until then what bounds its loss is unchanged and counts lots in dollars:
+>   the program loss line (`demotion.program_loss_usd` -$300, on realized Probe net), the $400 window and $800 total budgets with open risk at 0.40,
+>   the daily and drawdown stops and the kill switch. On a $557 sleeve -$300 is 54% of the sleeve: it is a backstop, not a tight leash, and the
+>   report says so beside every live panel program.
+> - Done's meter is NOT changed here: a closed lot is one close until the owner decides otherwise (section 19); H's report line shows the distinct
+>   close dates and the date-clustered t beside it (A14's reporting).
+> - Tests (`test_xs_book.py`): the three scenarios above on E1's own `edm1` and `sized_up` (none fires by date; each fires by lot); the per-date
+>   returns and gaps on a golden six-lot, two-date fixture; `bh_pnl` against a hand value across a dividend; an ETF instance's record is byte for
+>   byte what E1 builds today.
+
+Read with the amendments in force when this was integrated, which the text above predates:
+- **The Probe sleeve** is the constitution's `equity_money.probe.sleeve_share` x E, and the captain's A20 set it to
+  0.50 (the text's "$557 sleeve" is 0.25 x E). The rules do not change; the dollar examples scale with the sleeve, and
+  -$300 is then a smaller share of it. One consequence is new and is stated here: a FULL sleeve of stocks at 0.50 x E
+  counts 0.40 x 0.50 x E = 0.20 x E of open risk, which is above the $400 window once E is above $2,000. So the loss
+  budget, not the sleeve, bounds a panel program's invested dollars at that size: sizing cuts the last entries to the
+  window's room, and the standing target buys them the day the room exists. The live package (H) recomputes the
+  spec's feasibility table with E1's own sizing function at the values in force.
+- **Sizing up is parked** (the captain's A21: `equity_money.sized.min_trades` 1000, for every equity program): the
+  text's "sizing up from 20 dates" reads "from `sized.min_trades` close dates", which no program reaches while the
+  step is parked. EDM1's legs, the -$300 program line, the window and the total are as the text says.
+- **Hold days** (the captain's A17, granted): for a panel program a hold-day fetch failure of a held name is an alarm
+  and never counts toward the two-failed-decides exit; a failed decide on a rebalance day still counts.
+
+**The universe deploy (R-E4b): ONE commit, deployed separately, the money digest moves once.** A panel program can
+only buy what the constitution's `equity_money.universe` and the gateway's `STOCK_UNIVERSE` both name, and E1 named 18
+stocks. R-E4b grows the stock list to **the panel's tradable union: every symbol that was an S&P 500 member on any
+session of the 36 months before the generation day and is tradable, fractionable and unmasked that day**, E1's 18
+among them (about 560 names, an estimate). The ETFs do not change; NO bound, share, weight, seat or cap changes.
+- **Why a 36-month union and not the day's members.** A list of today's members, regenerated each quarter in a public
+  repository, IS a point-in-time membership history. A union says only "was a member at some time in three years",
+  carries no date, and needs regenerating about once a year. A name on it that is no member today is simply never
+  eligible; a new member is not eligible live until the next regeneration (the store records that, so the replay of
+  the day agrees); a removed member is sold by the House's own exit, and a sale of any held symbol always passes the
+  gateway, whatever its list.
+- **What is committed** is a ticker allow-list, sorted, between two marker comments in each file: no date, no weight,
+  no history. `league/equity/config.py` `UNIVERSE` (E1's 35, hashed into the equity identity and every ETF run) is
+  NOT changed: it stays inside the constitution's universe (`league/tests/test_equity_money.py`), and the daily ETF
+  job still fetches the 35.
+- **How** (the owner's machine; a clean checkout of main at a head CI is green on):
+  1. On the House the `equity_universe` job writes `<state>/equity-daily/universe/tradable.json` ({"as_of", "stock"})
+     once its audit passes. Copy that ONE file to the owner's machine. It is never committed.
+  2. `python3 scripts/gen_universe.py --from tradable.json --gateway-patch ~/universe.patch`. It rewrites the
+     generated block of `league/constitution.py`, re-pins `PINNED_DIGEST`, prints both digests before and after, and
+     writes the gateway's half as a patch (it never writes into `gateway/`). It REFUSES, and writes nothing: a ticker
+     outside the gateway's `STOCK_SYMBOL` pattern, an ETF, a symbol twice, a list under 450 or over 650 names, a list
+     that lacks one of E1's 18, an input with any key but `as_of` and `stock` or any entry that is not a plain ticker
+     (a date beside a symbol), and its own rewrite unless it changes the stock list and nothing else.
+  3. `git apply ~/universe.patch` (the owner's step: `gateway/` is the owner's), then
+     `python3 scripts/gen_universe.py --from tradable.json --check`, `python3 -m league.ci --no-tests` (the two lists
+     are one list: `gateway_stock_problems`) and `cd gateway && npm run check && npm test`.
+  4. ONE commit holding `league/constitution.py` and `gateway/lib/caps.mjs`, and nothing else, marked **UNIVERSE (moves
+     the money digest; deployed separately)**, with the two digests in this file's entry of CHANGELOG.md. CI green on
+     the exact head.
+- **The order of the two deploys, and when.** FIRST the gateway (`npx wrangler@4.129.1 deploy`; a longer allow-list
+  there is inert: the House still admits only what its own constitution names). THEN the House release
+  (`floor_box.py deploy`), when no order is in flight: `digest()` and `money_digest()` move ONCE and the standing
+  grant re-ratifies at the House's start (job `grant`). The House first would only have its new buys refused, never a
+  wrong order. **BOTH DEPLOYS GO BETWEEN TWO PRE-OPENS** (after 09:30 ET, before the next 08:30): the order is safe
+  but it is not silent, because the pre-open's check 10 holds the DEPLOYED gateway's list equal to the constitution's
+  and raises a public warning when they differ. As a second guard that warning names at most 10 tickers a side and
+  counts the rest (`league.ci.stock_agreement`), so a gateway deployed on a Friday with the House on Monday posts
+  three short lines, not three lists of 540 names.
+- **Verify** (read-only): the gateway's `/v1/health` `stock_buys.symbols.stock` has the list's count; on the box the
+  grant is ratified on the new money digest (`grant` job receipt; pre-open check 2); the next `equity_panel` run
+  records `live_from` in the panel manifest; the next pre-open's check 10 says the deployed gateway's stock list
+  agrees with `equity_money`. The equity identity and the options fingerprint are the ones from before the deploy.
+- **Roll back.** A House release from before R-E4b brings the old money digest back (the grant re-ratifies on the
+  owner's deploy of it) and retires a panel program, whose lots exit at the next open by E1's rule; sells of any held
+  symbol always pass the gateway. **THE GATEWAY IS NEVER ROLLED BACK BEFORE THE HOUSE** (a shorter list under a House
+  that still buys the long one refuses those buys and, at the next pre-open, warns). E1's guard stands (no release
+  older than E1 while an equity lot is open).
+- **Afterwards:** regenerate about YEARLY (`universe_max_age_days` 400 is the alarm), or when `live_ready` fails on
+  `live_min_tradable_share`. Each is this section again: an owner deploy of both, and one more digest move.
+- **Margin, shorts, borrowing:** none. The panel is long only and cash only (A1), inside every wall of the goal.
+
+**Stop it, from the lightest** (each a settings change read on the next loop pass, no deploy; the mode goes DOWN one
+step at a time, and each step is the rollback of the one above it):
+1. `elane.panel.mode=gate`: no panel program takes or keeps a seat. A live panel program is demoted (exits only) and
+   its lots exit at the next open by E1's rule; Validation and looks go on.
+2. `elane.panel.mode=train`: no Validation try and no look; births and Train research go on.
+3. `elane.panel.mode=off`: no panel birth, no Train run, nothing of the panel in any request. The data jobs go on
+   reading (they spend no model dollar and send no order).
+4. E1's switches stand above all of it: `elane.mode=off` stops every equity round, the panel's too; and
+   `equity_money.enabled` false (a constitution change) stops every equity open. Exits never wait on a switch.
+A panel lot is an equity lot: **Roll back: flatten first** (the next section) is the rule for a House rollback while
+one is open.
+
+**What moves what.** A change to an evidence module of `league/xs/` moves the **xs identity**
+(`league/xs/identity.py` `xs_fingerprint`): every live PANEL band goes back to the Gym for fresh qualification (no
+new try, no new look) and no ETF family is touched. A change to an evidence module of `league/equity/` moves both
+identities. `league/xs/book.py` and `identity.py`, `league/equity/live.py` and `kinds.py`, every file of
+`league/swarm/` and `league/ops/`, policy.json and the constitution move NO identity. A panel band is current only
+under the code the running release holds (its proof names the xs fingerprint and the program's hash), read from the
+release's own files, never from a stored value. The constitution's universe moves `digest()` and `money_digest()`,
+and nothing else does in E4.
+
+**Deploy class.** Both releases are owner deploys. Behind `league/ci.py`'s wall (`FORBIDDEN`: no role changes them and
+the updater never self-deploys them): `league/xs/` (the panel's evidence, its screen XS1, its live adapter),
+`league/ops/` (its data jobs), `docs/benchmarks/` (XS1's receipt), `league/swarm/policy.json` (its pin and its
+switch), and from this release `league/swarm/elane_xs.py` (the Train bar, the look, lineage, A22's seat rule) and
+`scripts/gen_universe.py` (the author of a money rule). **One follow-up at the gateway**: its merge list
+(`gateway/lib/protected.mjs` MERGE_FORBIDDEN) gains those two with E2's five in its next deploy; until then they wait
+in `league/ci.py` `PENDING_GATEWAY`.
+
+**The alarms** (House alerts, each with its cause; W warning, C critical): the coverage verdict not "ok" (W; C when
+"insufficient"); the universe audit failed, or the membership pin did not advance for 60 days (W); the changes table
+read cut short (W) and membership staler than `membership_max_stale_days` (W; looks wait); a full refetch failed two
+nights running (W); `equity_panel` failed two days running (C while a panel program is live); the nightly I6 not
+equal (C: the mode reads at most "gate"); a panel decision's morning re-read "mismatch" (C: its buys are cancelled) or
+"unread" (W); the 16:20 fetch decided late and incomplete (W); the spreads table under its bound in mode "gate" or
+above (W); the zero-edge pass rate of the Train bar above 5% (W: the bar is too loose); an E4 job or a Train run
+found RUNNING at a wall (C); the xs identity moved while a panel lineage is in Probe (C, said before the deploy);
+`live_ready` false while a panel program is live (C: its opens stop, exits go on; the leg that failed is named, and
+the pre-open's check 10 says it again each morning); the twin marker a night behind (W) or two (C); a rebalance
+session whose live and twin orders disagree (W); a standing-target buy still unfilled after 5 sessions (W); a
+rebalance recorded late (W); two failed panel decides (C: E1's exit rule fires); the committed universe older than
+`universe_max_age_days` (W: an owner step); the pre-open's gateway and constitution lists differ (W, at most 10 names
+a side: the two deploys were not made between two pre-opens).
+
+**Cost.** Data $0 while the coverage verdict is "ok" (Alpaca SIP through the gateway; the membership sources through
+its web reader); model spend stays inside E2's `elane.e2.usd_day` (a panel brief is about a quarter longer; no new
+cap); House CPU at most `cpu_seconds_day` of panel Train a day (4 h), the jobs a few minutes, the weekly zero-edge run
+under 3 h on Sunday; gateway calls about 45 a day, 56 more a session while a panel program is live, about 1,260 on the
+weekly refetch, and 6,000 a night for about nine nights while the spreads table is first filled.
+
+**Verify after R-E4a** (read-only): policy.json on the box has the `elane.panel` block with `mode` "off" and
+`elane.screens.equity_xs` holding the receipt's sha256; before the switch the swarm log has no panel line and
+`swarm.sqlite` no panel family; `equity_universe` and `equity_panel` have receipts with counts and a coverage
+verdict, and no price or ticker in them; the House's start re-ratifies no grant (the money digest did not move) and
+sends no ETF band and no options band back to the Gym (neither identity moved).
+
+**Not handled, stated.** No panel program is shadowed forward until package J lands, so a style-open passer is
+recorded and not yet shadowed. The screen does not match sub-industry, size or value: A22 (1) is the House's answer,
+and it withholds a seat from every momentum and low-volatility program. A member added to the index after the last
+universe deploy cannot be bought live until the next one (about 5% of names a year); the replay of such a day agrees,
+because the store records which symbols the constitution named that day. Membership is read two sessions ahead in the
+Gym and live knows only the changes the universe job has read by the decision: a change learnt late is a
+live-versus-Gym gap the nightly I6 shows. Entry validity peeks one session ahead in the Gym (data validity, never a
+return); live cannot. French's factor files do not reach the House (no route), so the loadings beside XS1 are on the
+House's own panel factors. `league/equity/config.py` still says in its docstring that the constitution's universe
+equals `UNIVERSE`; since R-E4b it is the other way round (inside it), and the file is not edited because a byte
+changed there moves the equity identity. Done's meter still counts a closed panel lot as one close; whether a panel
+program's closes count by distinct close dates is the owner's open decision, and the report shows both.
+
 ## The equity lanes' births (release E2, Oct 2026): `feat/equity-e2-int`, not deployed
 
 E1 (the next section) gives the equity lanes their live path and three captain-seeded programs. E2 makes the swarm
@@ -334,9 +679,9 @@ binding later programs against every program already looked at, and where a look
 look writes it again from that program's Train-era runs or waits, never passing D3 unjudged. The PLUMBING is out
 (`live`, `actions`, `schedule`, `families`, `bands`, `kinds`): a fix to the EquityBook, its clock, its corporate actions or its band plumbing retires no lineage. The cost
 stated: nothing in the identity then proves the live path matches the Gym after such a fix; the I6 ctx test
-(`test_equity_i6`) and the equity twins police it. `league/xs/` is the panel kind's slot (`kinds.KINDS["panel"]`): its
-`handle` refuses every op today, and a later cross-sectional lane is built there without touching `league/live` (the
-options fingerprint) or the equity evidence modules.
+(`test_equity_i6`) and the equity twins police it. `league/xs/` is the panel kind's slot (`kinds.KINDS["panel"]`): E1
+shipped it with a `handle` that refused every op, and release E4 built the panel lane there (**The panel lane**, above)
+without touching `league/live` (the options fingerprint) or the equity evidence modules; it has its own identity.
 
 **Roll back: flatten first.** In order, each step verified before the next:
 1. `elane.mode` "off" in swarm.json (no seeded birth, no equity look).
```

### 16.5 `CHANGELOG.md`

Anchor: under "## Not yet deployed", a new entry before "### Release E2, integrated on E1". The UNIVERSE commit adds
the two digests (before and after) to this entry: they are the list's, so they are not known before the generator runs.

```diff
diff --git a/CHANGELOG.md b/CHANGELOG.md
index 6b5c72b..71ded49 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -29,6 +29,44 @@ any other deploy.
 The running House release is `20261010T214125Z-d4667186f969` (main `ac6d008b`, the no-captain automations, 21:42Z
 Oct 10), the gateway is `95e7a8d0` (#534, 22:20Z), and the box's updater is on. What is built and not deployed is on branches.
 
+### Release E4, "breadth": the point-in-time S&P 500 panel under the screen XS1, on `feat/equity-e4` (unreleased; two owner deploys: R-E4a research, no digest move, ships switched off; R-E4b the universe, one money-digest move, deployed separately)
+
+- **What it adds** (`league/xs/E4_INTERFACES.md`, `league/swarm/E4.md`): programs that pick 5 to 12 names out of the
+  day's S&P 500 members by a symmetric cross-sectional rule, see salted slots with no ticker, no date and no price
+  level, and are judged on their daily RESIDUAL against matched placebo portfolios by the screen XS1 (the study
+  XSCREEN-1's receipt, `docs/benchmarks/equity_screen_xs_1.json`, pinned in policy.json; every threshold read from it
+  at runtime). The data jobs (membership, the panel's bars with their coverage audit, spreads, N_eff), the panel
+  package `league/xs/` with its own evidence identity, the Train bar equity-xs-v1 with its weekly zero-edge column,
+  the one Validation try and the one look, and the live adapter through E1's EquityBook (a rebalance the book can
+  execute, a standing target that retries a missed buy, the bars a decision read kept and audited).
+- **Ships off.** policy.json `elane.panel.mode` "off": no birth, no run, no fetch of the live path, no model question.
+  The ladder is "train", "gate", "live", each the captain's settings change and each falling back to the one before.
+  **Mode "live" reads as "gate" until the forward twin exists** (package J, owed: it is built on release E3's forward
+  modules), and **no panel look runs until E3's contamination probe has run with the panel strata** (the captain's A22).
+- **Before any real money on an XS1 pass** (A22): a style-open program takes no live seat on a pass alone (recorded
+  and shadowed, never seated); at most 2 XS1 looks an agenda cell; the equity code review and the contamination probe
+  before a look; a ninth conformance vector beside the study's eight.
+- **The live rules read a panel program by close DATE** (pre-registered before mode "live"; word for word in
+  docs/operations.md): one observation a close date for EDM1, for sizing up and for the twin-gap leg. E1's rules are
+  unchanged as functions and as numbers; the cost, stated: EDM1's statistical leg cannot act before the 10th close
+  date, and until then the -$300 program line, the $400 window and the stops bound a panel program's loss.
+- **R-E4a moves no identity and no digest:** nothing under `league/live/` or `league/gym/` and no evidence module of
+  `league/equity/` changes; the constitution is untouched. The xs identity is adopted for the first time.
+- **R-E4b, THE UNIVERSE (one commit, deployed separately):** `equity_money.universe.stock` grows from E1's 18 names to
+  the panel's tradable union (every symbol that was an index member in the 36 months before the generation day and is
+  tradable and fractionable; sorted; no date), written by `scripts/gen_universe.py` with the same list at the gateway
+  (`gateway/lib/caps.mjs`). `digest()` and `money_digest()` move ONCE (the figures are in that commit's entry: they
+  are the list's) and the standing grant re-ratifies at the House's start. No bound, share, weight, seat or cap
+  changes; `league/equity/config.py` `UNIVERSE` stays E1's 35 and inside it. The gateway deploys first; both deploys
+  go between two pre-opens. Regenerated about once a year.
+- **CI:** `league/swarm/elane_xs.py` and `scripts/gen_universe.py` are FORBIDDEN (`PENDING_GATEWAY` until the
+  gateway's merge list names them: a gateway follow-up, with E2's five); the comparison of the gateway's stock list
+  with the constitution's names at most 10 tickers a side and counts the rest; the pre-open's check 5 counts the
+  options population by the store's own guard (a panel family is its own lane's), and its check 10 holds the panel
+  lane ready while a panel program is live.
+- Operations: [docs/operations.md](docs/operations.md), "The panel lane" (the switch, the screen, A22, the live rules,
+  the universe deploy and its rollback, the alarms).
+
 ### Release E2, integrated on E1: the swarm breeds share programs for the BETA and EQUITY lanes, on `feat/equity-e2-int` (unreleased; an owner deploy with or after E1; no identity moves; ships switched off)
 
 - **What it adds** (`league/swarm/ELANE_E2.md`): the architect's equity pass (families with their first program, on
```

## Patch 15 (release R-E4b): THE UNIVERSE (moves the money digest; deployed separately)

### 15.1 `league/tests/test_equity_money.py`: the subset test, the grant, the pre-open check

Anchors: after the helper `problems`; `TheTable.test_the_universe_and_shares_are_the_lanes_constants`;
`TheGrantReRatifies` (a `setUp` between `pre_e1` and `pinned_before`); a new class `TheUniverseReRatifies` before
`ThePreopenEquityCheck`; three tests appended to `ThePreopenEquityCheck`. THIS DIFF APPLIES AS IT IS AT THE
INTEGRATION HEAD (`feat/equity-e2-int` `a4514e83`) too: no hunk's context holds a digest.

- **The subset test** (E4-SPEC 11): the equality `dict(e.universe) == config.UNIVERSE` becomes "`config.UNIVERSE` is
  INSIDE the constitution's universe, classes equal"; the ETFs are E1's exactly; whatever is beyond E1's 35 is stocks;
  and the stock list is E1's 18 in E1's order, or a generated union (450 to 650, sorted).
- **`TheGrantReRatifies`** pins three of E1's money digests by value. They are E1's, so the class reads them with E1's
  universe (`e1_universe()`); nothing else in it changes. AT THE INTEGRATION HEAD the literals differ (the captain's
  A20 and A21 moved them, and a fourth, `QUARTER`, was added): the `setUp` applies there unchanged, because it pins
  the universe and names no digest.
- **`TheUniverseReRatifies`** (new): a grown universe is a money rule and nothing else moves with it; the owner's
  deploy re-ratifies the grant and the updater alone never does; the rollback to E1's list is ratified the same way.
- **The pre-open's check 10** (15.4): a live panel program needs the panel lane ready; `collect` reads nothing of the
  panel while no panel program is live; the options population is counted by the store's guard (16.3).

```diff
diff --git a/league/tests/test_equity_money.py b/league/tests/test_equity_money.py
index c57a52d..78afc08 100644
--- a/league/tests/test_equity_money.py
+++ b/league/tests/test_equity_money.py
@@ -35,6 +35,16 @@ def problems(**rows):
     return equity_money_problems(changed(**rows))
 
 
+def e1_universe():
+    """The constitution's universe as release E1 shipped it, by class and in its order: `league.equity.config.UNIVERSE`,
+    an evidence module's constant that release E4 never changes. E4's universe (scripts/gen_universe.py) grows the
+    stock list around it, which moves the money digest and nothing else: a figure pinned for E1 is read with this put
+    back, and so holds before and after the universe deploy."""
+    from league.equity import config
+
+    return {klass: [s for s, k in config.UNIVERSE.items() if k == klass] for klass in config.CLASSES}
+
+
 class TheTable(unittest.TestCase):
     def test_the_block_as_e1_deploys_it_is_inside_its_bounds_and_switched_on(self):
         self.assertEqual(equity_money_problems(), [])
@@ -64,12 +74,25 @@ class TheTable(unittest.TestCase):
         self.assertTrue(hash(t))
 
     def test_the_universe_and_shares_are_the_lanes_constants(self):
-        """The constitution's universe is `league.equity.config.UNIVERSE` exactly (symbols and classes; `league.ci` holds
-        it to the gateway's STOCK_UNIVERSE), and no position share is above `config.POSITION_SHARE`."""
+        """`league.equity.config.UNIVERSE` (release E1's 35: hashed into the equity identity and into every ETF run, so
+        never changed) is INSIDE the constitution's universe, classes equal: every symbol the lane's own programs name
+        is one the money rule admits. Since release E4 the constitution's STOCK list may be the longer one: the
+        panel's tradable union, generated (scripts/gen_universe.py: 450 to 650 names, E1's 18 among them), which
+        `league.ci` holds to the gateway's STOCK_UNIVERSE. Its ETFs are E1's exactly, in E1's order. No position share
+        is above `config.POSITION_SHARE`."""
         from league.equity import config
 
         e = M.EquityTable.from_constitution()
-        self.assertEqual(dict(e.universe), config.UNIVERSE)
+        self.assertEqual({symbol: e.universe.get(symbol) for symbol in config.UNIVERSE}, config.UNIVERSE)
+        self.assertEqual(CONSTITUTION["equity_money"]["universe"]["etf"], e1_universe()["etf"])
+        beyond = [symbol for symbol in e.universe if symbol not in config.UNIVERSE]
+        self.assertEqual({e.universe[symbol] for symbol in beyond} - {"stock"}, set(), "what E4 adds is stocks")
+        stocks = CONSTITUTION["equity_money"]["universe"]["stock"]
+        if beyond:
+            self.assertTrue(450 <= len(stocks) <= 650, f"{len(stocks)} stocks: a generated union has 450 to 650")
+            self.assertEqual(stocks, sorted(stocks), "generated: sorted")
+        else:
+            self.assertEqual(stocks, e1_universe()["stock"], "release E1's list, in its order")
         for klass in config.CLASSES:
             self.assertLessEqual(e.position_share[klass], config.POSITION_SHARE[klass])
         self.assertEqual((e.min_hold_sessions, e.default_max_hold_sessions, e.max_hold_sessions, e.failed_decides_exit),
@@ -226,6 +249,13 @@ class TheGrantReRatifies(StandingCase):
         CONSTITUTION.pop("equity_money", None)
         return patcher
 
+    def setUp(self):
+        super().setUp()
+        # These digests are release E1's: read with E1's universe (release E4's is a digest of its own, below).
+        pin = patch.dict(CONSTITUTION["equity_money"], universe=e1_universe())
+        pin.start()
+        self.addCleanup(pin.stop)
+
     def pinned_before(self):
         patcher = self.pre_e1()
         try:
@@ -280,6 +310,76 @@ class TheGrantReRatifies(StandingCase):
         self.assertTrue(grant.allows_live(2))
 
 
+class TheUniverseReRatifies(StandingCase):
+    """Release E4's universe (R-E4b: the panel's tradable union in `equity_money.universe.stock`, written by
+    scripts/gen_universe.py) is a money rule and NOTHING ELSE moves with it: a grant ratified on release E1's digest
+    holds nothing under the grown list until the standing grant re-ratifies it at the House's start, on the owner's
+    release change only; with E1's list put back the digest is E1's again, and the rollback to it is ratified the same
+    way. Invented tickers: the list the House generates is never in a test."""
+
+    GROWN = [f"ZZ{a}{b}" for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRST"]
+
+    def grown(self):
+        universe = e1_universe()
+        return {"etf": universe["etf"], "stock": sorted(universe["stock"] + self.GROWN)}
+
+    def ratified_on_e1(self):
+        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
+            e1 = money_digest()
+            grant = self.enabled()
+            self.assertEqual(grant.current()["policy"]["constitution_digest"], e1)
+            self.assertTrue(grant.allows_live(2))
+        return grant, e1
+
+    def test_the_universe_moves_the_money_digest_and_nothing_else_does(self):
+        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
+            e1, e1_full = money_digest(), copy.deepcopy(CONSTITUTION)
+        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
+            self.assertNotEqual(money_digest(), e1)
+            self.assertEqual(equity_money_problems(), [], "538 stocks sit inside the table's bounds")
+            table = M.EquityTable.from_constitution()
+            self.assertEqual(len(table.universe), 17 + 18 + 520)
+            self.assertEqual({table.universe[s] for s in self.GROWN}, {"stock"})
+            back = copy.deepcopy(CONSTITUTION)
+            back["equity_money"]["universe"] = e1_universe()
+            self.assertEqual(back, e1_full, "the list is all that differs")
+            self.assertEqual(money_digest(back), e1)
+        # The tree as it stands: E1's rules but for the stock list (the same figure before and after the deploy).
+        back = copy.deepcopy(CONSTITUTION)
+        back["equity_money"]["universe"] = e1_universe()
+        self.assertEqual(money_digest(back), e1)
+
+    def test_the_owners_deploy_re_ratifies_it_and_the_updater_alone_never_does(self):
+        grant, e1 = self.ratified_on_e1()
+        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
+            universe = money_digest()
+            self.assertFalse(grant.allows_live(2), "a moved universe is a moved money rule: nothing real until ratified")
+            out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
+            self.assertEqual(out["action"], "refused")
+            self.assertFalse(grant.allows_live(2))
+            self.assertEqual(grant.ratifications(), [])
+            out = self.standing(grant, release="r-e4b", rows=owner_deploy(self.clock() - 60, release="r-e4b"))
+            self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
+            self.assertIn(f"money digest {e1[:12]} -> {universe[:12]}", grant.ratifications()[-1]["why"])
+            self.assertEqual(grant.current()["policy"]["constitution_digest"], universe)
+            self.assertTrue(grant.allows_live(2))
+
+    def test_the_rollback_to_e1s_list_is_ratified_on_the_owners_deploy_of_it(self):
+        grant, e1 = self.ratified_on_e1()
+        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
+            self.standing(grant, release="r-e4b", rows=owner_deploy(self.clock() - 60, release="r-e4b"))
+            self.assertTrue(grant.allows_live(2))
+        self.clock.advance(HOUR)
+        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
+            self.assertFalse(grant.allows_live(2))
+            back = [{"ts": self.clock() - 60, "deploy": "rollback@2", "release": "r-e4b", "stage": "rollback", "ok": True,
+                     "from": "r-e4b", "to": "r-e4a"}]
+            out = self.standing(grant, release="r-e4a", rows=back)
+            self.assertEqual(out["action"], "ratified")
+            self.assertEqual(grant.current()["policy"]["constitution_digest"], e1)
+            self.assertTrue(grant.allows_live(2))
+
+
 class ThePreopenEquityCheck(unittest.TestCase):
     """Check 10 (league/ops/preopen.py): cash at or above zero, no us_equity short, the equity book reconciled, the
     deployed gateway's stock route equal to the constitution's; the multiplier and the PDT flag reported, never a bar."""
@@ -400,6 +500,154 @@ class ThePreopenEquityCheck(unittest.TestCase):
             h = PO.collect(root, root, root, Gateway(), now=1789000000.0, config={})
             self.assertEqual(h["money"]["equity_release_gateway"], [])
 
+    def test_a_live_panel_program_needs_the_panel_lane_ready(self):
+        """Release E4: while the equity book holds a panel program (not retired, or with a lot), the lane's own
+        readiness rule must hold; the leg that fails is named. With none, nothing of the panel is a bar."""
+        for h in (self.house(), self.house(panel={"instances": 0}), self.house(panel=None)):
+            ok, headline, info = self.check(h)
+            self.assertTrue(ok, headline)
+            self.assertIn("no live panel program (the panel lane's readiness is not read)", info)
+        from league.ops.preopen import check_equity
+
+        ready = self.house(panel={"instances": 2, "holding": 1, "ready": True, "why": None})
+        self.assertTrue(self.check(ready)[0])
+        self.assertIn((True, "2 live panel program(s), 1 holding a lot: the panel lane is ready (the universe deploy, the "
+                             "tradable share, the universe's age, the nightly I6, the twin marker)"), check_equity(ready).items)
+        ok, headline, _ = self.check(self.house(panel={"instances": 1, "holding": 1, "ready": False,
+                                                       "why": "the twin marker is two sessions behind"}))
+        self.assertEqual((ok, headline), (False, "1 live panel program(s), 1 holding a lot, and the panel lane is NOT ready: the "
+                                                 "twin marker is two sessions behind (its opens stop; exits go on)"))
+        # A reading with no verdict is no pass, and neither is a section that could not be read.
+        ok, headline, _ = self.check(self.house(panel={"instances": 1}))
+        self.assertEqual((ok, headline), (False, "1 live panel program(s), 0 holding a lot, and the panel lane is NOT ready: no "
+                                                 "leg named (its opens stop; exits go on)"))
+        self.assertFalse(self.check(self.house(panel={"instances": 1, "ready": "yes"}))[0], "True, and nothing like it")
+        ok, headline, _ = self.check(self.house(errors={"panel": "OperationalError: database is locked"}))
+        self.assertEqual((ok, headline), (False, "the panel lane could not be read (a live panel program cannot be ruled "
+                                                 "ready): OperationalError: database is locked"))
+
+    def test_collect_reads_the_panel_only_while_a_panel_program_is_live(self):
+        """`collect`'s panel section: no live book, a book from before the panel's live path (E1's own tables: no `kind`
+        column) and a book with no panel program read NOTHING of the panel (`live_ready` is not called: with every
+        E4 switch off nothing of E4 runs). A panel program that is not retired, or a retired one still holding a lot,
+        is live; then the lane's rule is asked once, and a rule that cannot answer is an error, never a pass."""
+        import sqlite3
+
+        from league.equity import live as book
+        from league.ops import preopen as PO
+        from league.swarm import elane_xs
+
+        source = (Path(book.__file__).resolve().parents[1] / "xs" / "book.py").read_text(encoding="utf-8")
+        self.assertIn('KIND = "panel"', source)
+        self.assertIn("INSTANCE_KIND_DDL = \"ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'\"", source)
+        asked = []
+
+        def rule(root, settings):
+            asked.append((root, settings))
+            return False, "the universe deploy is not in force"
+
+        def instance(db, iid, *, kind=None, retired=None):
+            cols = "id, family, version, lane, run_sha, code, params, band, max_hold, created_at, retired_at"
+            row = (iid, iid.split("@")[0], 1, "equity", "sha", "", "{}", "probe", 20, 1.0, retired)
+            if kind is None:
+                db.execute(f"INSERT INTO eq_instances ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
+            else:
+                db.execute(f"INSERT INTO eq_instances ({cols}, kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*row, kind))
+            db.commit()
+
+        def lot(db, iid, status):
+            db.execute("INSERT INTO eq_lots (instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
+                       "entry_notional, entry_at, opened_at, opened_day, status) VALUES (?,?,1,'equity','ZZAA','stock','1',"
+                       "'1','10','10','open',1.0,'2031-03-04',?)", (iid, iid.split("@")[0], status))
+            db.commit()
+
+        with tempfile.TemporaryDirectory() as tmp, patch.object(elane_xs, "live_ready", side_effect=rule):
+            root = Path(tmp)
+
+            def read():
+                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
+                self.assertNotIn("panel", h["errors"], h["errors"])
+                return h["panel"]
+
+            self.assertEqual(read(), {"instances": 0}, "no live book")
+            db = sqlite3.connect(root / "live.sqlite")
+            self.addCleanup(db.close)
+            self.assertEqual(read(), {"instances": 0}, "a book with no equity table")
+            db.executescript(book.SCHEMA)
+            instance(db, "seed-a@1:r")
+            self.assertEqual(read(), {"instances": 0}, "release E1's tables: no kind column, so no panel program")
+            db.execute("ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'")
+            instance(db, "seed-b@1:r", kind="equity")
+            instance(db, "xs-gone@1:r", kind="panel", retired=5.0)
+            lot(db, "xs-gone@1:r", "closed")
+            self.assertEqual(read(), {"instances": 0}, "an equity program, and a panel program retired and flat")
+            self.assertEqual(asked, [], "nothing of the panel was read")
+            instance(db, "xs-a@1:r", kind="panel")
+            self.assertEqual(read(), {"instances": 1, "holding": 0, "ready": False,
+                                      "why": "the universe deploy is not in force"})
+            self.assertEqual([r for r, _ in asked], [root])
+            self.assertIsInstance(asked[0][1], dict, "the swarm's settings as the swarm loads them")
+            lot(db, "xs-gone@1:r", "closing")
+            lot(db, "xs-a@1:r", "open")
+            lot(db, "xs-a@1:r", "open")
+            self.assertEqual(read(), {"instances": 2, "holding": 2, "ready": False,
+                                      "why": "the universe deploy is not in force"}, "a retired program still holding a lot is live")
+            ok, headline, _ = self.check({**self.house(), "panel": read()})
+            self.assertEqual((ok, headline), (False, "2 live panel program(s), 2 holding a lot, and the panel lane is NOT ready: "
+                                                     "the universe deploy is not in force (its opens stop; exits go on)"))
+            # No symbol and no long text leaves the section.
+            self.assertNotIn("ZZAA", repr(read()))
+            with patch.object(elane_xs, "live_ready", return_value=(True, None)):
+                self.assertEqual(read(), {"instances": 2, "holding": 2, "ready": True, "why": None})
+            with patch.object(elane_xs, "live_ready", return_value=(False, "x" * 900)):
+                self.assertEqual(len(read()["why"]), 200)
+            with patch.object(elane_xs, "live_ready", return_value=("ready", None)):
+                self.assertIs(read()["ready"], False, "True, and nothing like it")
+            # The rule itself failing (a release whose panel lane is not built, a store it cannot read).
+            with patch.object(elane_xs, "live_ready", side_effect=NotImplementedError("not built")):
+                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
+            self.assertEqual(h["errors"]["panel"], "NotImplementedError: not built")
+            self.assertNotIn("panel", h)
+            ok, headline, _ = self.check({**self.house(), "errors": h["errors"]})
+            self.assertFalse(ok)
+            self.assertIn("the panel lane could not be read", headline)
+
+    def test_the_options_population_is_counted_by_the_stores_own_guard(self):
+        """Check 5 holds the OPTIONS population to its floor; an equity family is its own lane's, and a panel family
+        is one (release E4). The count reads `league.swarm.store.OPTIONS_ONLY_SQL`, the one guard the store's own
+        readers use, never a list of structures of its own: a panel family is out of it the day the store says so."""
+        import json
+        import sqlite3
+
+        from league.ops import preopen as PO
+        from league.swarm import store as swarm_store
+
+        with tempfile.TemporaryDirectory() as tmp:
+            root = Path(tmp)
+            (root / "swarm.json").write_text(json.dumps({"live": {}, "population": {"floor": 2}}))
+            (root / "swarm.heartbeat").write_text(json.dumps({"at": 1789000000.0, "status": {}}))
+            db = sqlite3.connect(root / "swarm.sqlite")
+            db.execute("CREATE TABLE families (id TEXT PRIMARY KEY, structure TEXT, retired_at TEXT)")
+            db.executemany("INSERT INTO families VALUES (?, ?, ?)",
+                           [("o1", "debit_vertical", None), ("o2", "long_single", None), ("o3", "long_single", "2031-03-04"),
+                            ("e1", "etf", None), ("e2", "stock", None), ("p1", "panel", None), ("p2", "panel", None)])
+            db.commit()
+
+            def alive():
+                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
+                self.assertNotIn("swarm", h["errors"], h["errors"])
+                return h["swarm"]["alive"]
+
+            [(wanted,)] = db.execute(f"SELECT count(*) FROM families WHERE retired_at IS NULL AND "
+                                     f"{swarm_store.OPTIONS_ONLY_SQL}").fetchall()
+            db.close()
+            self.assertEqual(alive(), wanted)
+            with patch.object(swarm_store, "OPTIONS_ONLY_SQL", "structure NOT IN ('etf', 'stock', 'panel')"):
+                self.assertEqual(alive(), 2, "the two options families; neither panel family")
+            with patch.object(swarm_store, "OPTIONS_ONLY_SQL", "structure NOT IN ('etf', 'stock')"):
+                self.assertEqual(alive(), 4)
+
+
 
 if __name__ == "__main__":
     unittest.main()
```

### 15.2 `league/tests/test_constitution.py`: E1's digests are read with E1's universe

Anchor: `test_the_equity_lane_moved_the_money_digest_to_the_one_the_grant_re_ratifies`, from its `import copy` to the
statement `off["equity_money"]["enabled"] = False`.

The test pins E1's money digest, E1's full digest and the stop's digest by value. After the universe deploy the tree's
digests are the list's. The three figures are now read on `e1` (the constitution with `league.equity.config.UNIVERSE`
put back), which makes the test a seal of binding fact 3 as well: were any row but the stock list to move with the
universe, E1's digests would no longer come back. AT THE INTEGRATION HEAD this test has more literals (A20, A21):
the same rule applies to each (`money_digest()` -> `money_digest(e1)`, `PINNED_DIGEST` -> `digest(e1)`,
`copy.deepcopy(CONSTITUTION)` -> `copy.deepcopy(e1)` wherever a figure of the E1 block is derived); the section "At
the integration head" below has the hunk as it applies there.

```diff
diff --git a/league/tests/test_constitution.py b/league/tests/test_constitution.py
index ec71cf4..169f772 100644
--- a/league/tests/test_constitution.py
+++ b/league/tests/test_constitution.py
@@ -148,13 +148,24 @@ class ConstitutionTest(unittest.TestCase):
         import copy
 
         from league.constitution import RISK_FREE, money_digest
+        from league.equity import config
 
-        self.assertEqual(money_digest(), "ad8c761bccc49033c3fdeca78c7b962f58272d192a2dd6e0626682ccdf6ac367")
-        self.assertEqual(PINNED_DIGEST, "65b0e025a08d4c3a8f78e487eb1a0f83ad9bfed307563c02acbd50ac4a6308bb")
+        # RELEASE E4's UNIVERSE (R-E4b; scripts/gen_universe.py) grows `equity_money.universe.stock` around E1's 18 names
+        # and moves both digests again, AND NOTHING ELSE MOVES WITH IT: E1's figures below are read on the constitution
+        # with E1's universe put back (`league.equity.config.UNIVERSE`, which E4 never changes), so they hold before
+        # the universe deploy and after it, and a row that moved with the list would fail them.
+        e1 = copy.deepcopy(CONSTITUTION)
+        e1["equity_money"]["universe"] = {klass: [s for s, k in config.UNIVERSE.items() if k == klass]
+                                          for klass in config.CLASSES}
+        self.assertEqual(money_digest(e1), "ad8c761bccc49033c3fdeca78c7b962f58272d192a2dd6e0626682ccdf6ac367")
+        self.assertEqual(digest(e1), "65b0e025a08d4c3a8f78e487eb1a0f83ad9bfed307563c02acbd50ac4a6308bb")
+        self.assertEqual(PINNED_DIGEST, digest())
+        if CONSTITUTION["equity_money"]["universe"] != e1["equity_money"]["universe"]:
+            self.assertNotEqual(money_digest(), money_digest(e1), "the universe is a money rule: the grant re-ratifies")
         before = copy.deepcopy(CONSTITUTION)
         del before["equity_money"]
         self.assertEqual(money_digest(before), "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7")
-        off = copy.deepcopy(CONSTITUTION)
+        off = copy.deepcopy(e1)
         off["equity_money"]["enabled"] = False
         self.assertEqual(money_digest(off), "ea97607c87a5e6d144a9577f0f3118397f7ca1d5eff073f75b022d8e79749ab9")
         self.assertFalse(any(path[0] == "equity_money" for path in RISK_FREE))
```

### 15.3 `league/tests/test_live_long_single.py`: the same figure, the same reading

Anchors: the comment above `MONEY_DIGEST`; `TheDeclaredType.test_the_money_table_and_its_digest_are_unchanged` (its
first assertion).

`MONEY_DIGEST` is E1's money digest ("`long_single` is no money rule and must not move it"). It is read with E1's
universe put back, as in 15.2. AT THE INTEGRATION HEAD the literal and the comment's last line differ (A20, A21); the
test's hunk is the same (below).

```diff
diff --git a/league/tests/test_live_long_single.py b/league/tests/test_live_long_single.py
index 483dc67..8e1f2d8 100644
--- a/league/tests/test_live_long_single.py
+++ b/league/tests/test_live_long_single.py
@@ -21,7 +21,9 @@ REPO = Path(__file__).resolve().parents[2]
 #: The money digest the grant is pinned to: `long_single` is no money rule and must not move it. R10's (Sept 29, 2026)
 #: was a3e2aa7c; the incubator's row (release B, Oct 1, 2026: `options_money.incubator`) moved it, then the incubator
 #: cap (Oct 8) to 1665c385, release L-D (Oct 9) to 0310779c, the Probe total at $800 (Oct 10, 2026) to fdf2ac7c, and
-#: release E1's `equity_money` (the equity lane) to this one.
+#: release E1's `equity_money` (the equity lane) to this one. Release E4's universe (the panel's tradable union in
+#: `equity_money.universe.stock`, scripts/gen_universe.py) moves it once more and is the only row that does: the test
+#: below reads this figure with E1's universe put back, so it holds before that deploy and after it.
 MONEY_DIGEST = "ad8c761bccc49033c3fdeca78c7b962f58272d192a2dd6e0626682ccdf6ac367"
 
 #: One program, two sides: a long call first, then (once the call is held) a long put. The side rule here is a clock so the
@@ -77,7 +79,12 @@ class TheDeclaredType(unittest.TestCase):
             self.assertTrue(set(types) <= set(OPTIONS_REAL_TYPES))
 
     def test_the_money_table_and_its_digest_are_unchanged(self):
-        self.assertEqual(money_digest(), MONEY_DIGEST)
+        from league.equity import config
+
+        e1 = copy.deepcopy(CONSTITUTION)
+        e1["equity_money"]["universe"] = {klass: [s for s, k in config.UNIVERSE.items() if k == klass]
+                                          for klass in config.CLASSES}
+        self.assertEqual(money_digest(e1), MONEY_DIGEST)
         self.assertEqual(CONSTITUTION["options_money"]["real_types"], ["debit_vertical", "long_butterfly", "long_call", "long_put"])
         self.assertEqual(M.Table.from_constitution().real_types, ("debit_vertical", "long_butterfly", "long_call", "long_put"))
         self.assertTrue(digest())
```

### 15.4 `league/ops/preopen.py`: while a panel program is live, the panel lane is ready

Anchors: the module docstring's check 10 (its last clause); in `collect`, a new section `panel()` before `mirror()`
and its name in the loop's tuple; in `check_equity`, after the `equity_release_gateway` item.

`collect` gains a section `panel`: how many of the equity book's programs of kind "panel" are not retired or still
hold a lot (`live.sqlite`, read-only) and, ONLY WHEN THERE IS ONE, `league.swarm.elane_xs.live_ready(root, settings)`.
No live book, a book from before the panel's live path (no `kind` column: package H's patch 12 adds it) or a book
with no panel program: `{"instances": 0}` and nothing of the panel is read or imported (with every E4 switch off
nothing of E4 runs). Check 10 then says "N live panel program(s) ... the panel lane is ready", or FAILS naming the
leg (`why`, cut to 200 characters; counts and a leg's name, never a symbol: the warning is public). A section that
could not be read, or a rule that raises (a stub, a store it cannot open), is a FAIL, never a pass. It degrades
safely without the other packages: until H lands there is no `kind` column, so the rule is never called.

```diff
diff --git a/league/ops/preopen.py b/league/ops/preopen.py
--- a/league/ops/preopen.py
+++ b/league/ops/preopen.py
@@ -30,7 +30,11 @@
              its switch, its per-symbol shares) agreeing with the constitution's `equity_money`, by the one comparison
              `league.ci` makes of the release's files (`ci.stock_agreement`; the release's own gateway/ files too when
              it carries them); the account's margin multiplier and its pattern-day-trader flag and day-trade count
-             REPORTED, never a bar (the venue may still flag pattern day traders: the design's fact 7)
+             REPORTED, never a bar (the venue may still flag pattern day traders: the design's fact 7); and THE PANEL
+             LANE (release E4): while the equity book holds a panel program that is not retired, or a lot of one, the
+             lane's own readiness rule holds (`league.swarm.elane_xs.live_ready`: the universe deploy in force, the
+             tradable share, the universe's age, the nightly I6, the twin marker; the leg that fails is named). With no
+             panel program nothing of the panel is read
 
 Read-only (`guard.readonly()`; GET only). Each FAIL is one House warning ("preopen 5 swarm FAIL: ..."); the receipt
 holds every line. The warning is PUBLIC (`ops.alert`) and the runner scrubs only what carries a `$`
@@ -260,6 +264,33 @@
         return {"latest": {"at": rows[0]["at"], "age_h": round((now - epoch(rows[0]["at"])) / 3600, 2), "ok": p.get("ok"),
                            "error": p.get("error")}}
 
+    def panel() -> dict:
+        """THE PANEL LANE (release E4): how many of the equity book's panel programs are not retired or still hold a
+        lot (live.sqlite `eq_instances` of kind "panel", read-only) and, ONLY WHEN THERE IS ONE, what the lane's own
+        rule says of it (`elane_xs.live_ready`). A book from before the panel's live path (no table, no `kind`
+        column) holds none. Counts and the failing leg's name: never a symbol."""
+        live = root / "live.sqlite"
+        if not live.exists():
+            return {"instances": 0}
+
+        def read(db: Any) -> list[dict[str, Any]]:
+            if "kind" not in [r["name"] for r in guard.rows(db, "PRAGMA table_info(eq_instances)")]:
+                return []
+            return guard.rows(db, "SELECT i.id, (SELECT count(*) FROM eq_lots l WHERE l.instance = i.id AND l.status IN "
+                                  "('open', 'closing')) AS lots FROM eq_instances i WHERE i.kind = 'panel' AND "
+                                  "(i.retired_at IS NULL OR EXISTS (SELECT 1 FROM eq_lots l WHERE l.instance = i.id AND "
+                                  "l.status IN ('open', 'closing'))) ORDER BY i.id")
+
+        rows = guard.read(live, read)
+        if not rows:
+            return {"instances": 0}
+        from ..swarm import elane_xs
+        from ..swarm import settings as SS
+
+        ready, why = elane_xs.live_ready(root, SS.load(root, config=config))
+        return {"instances": len(rows), "holding": sum(1 for r in rows if r["lots"]), "ready": ready is True,
+                "why": None if why is None else str(why)[:200]}
+
     def mirror() -> dict:
         cursor = read_json(root / "swarm-mirror.json", None)
         top = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT max(seq) FROM events"))[0]
@@ -268,7 +299,7 @@
                 "lag": None if seq is None or top is None else max(0, int(top) - int(seq))}
 
     for name, fn in (("release", release_), ("grant", grant), ("money", money), ("gateway", gateway_), ("swarm", swarm),
-                     ("bands", bands), ("backup", backup), ("mirror", mirror)):
+                     ("bands", bands), ("backup", backup), ("mirror", mirror), ("panel", panel)):
         section(name, fn)
     return out
 
@@ -570,6 +601,20 @@
     files = m.get("equity_release_gateway")
     if files is not None:
         c.req(not files, "the release's gateway files agree with equity_money" if not files else "; ".join(files))
+    # THE PANEL LANE (release E4): a live panel program trades only while the lane's own readiness rule holds. The
+    # book and the swarm hold that themselves (opens stop, exits go on); this is the morning's second look at it.
+    panel, unread = h.get("panel"), (h.get("errors") or {}).get("panel")
+    if unread:
+        c.req(False, f"the panel lane could not be read (a live panel program cannot be ruled ready): {unread}")
+    elif isinstance(panel, Mapping) and panel.get("instances"):
+        count = f"{panel['instances']} live panel program(s), {panel.get('holding') or 0} holding a lot"
+        c.req(panel.get("ready") is True,
+              f"{count}: the panel lane is ready (the universe deploy, the tradable share, the universe's age, the nightly "
+              "I6, the twin marker)" if panel.get("ready") is True
+              else f"{count}, and the panel lane is NOT ready: {panel.get('why') or 'no leg named'} (its opens stop; "
+                   "exits go on)")
+    else:
+        c.info("no live panel program (the panel lane's readiness is not read)")
     if acct:
         c.info(f"margin multiplier {acct.get('multiplier')} (reported, never a bound: E1 trades cash only); "
                f"pattern_day_trader {acct.get('pattern_day_trader')}, daytrade_count {acct.get('daytrade_count')}")
```

Held by: `league.tests.test_equity_money.ThePreopenEquityCheck.test_a_live_panel_program_needs_the_panel_lane_ready`
and `test_collect_reads_the_panel_only_while_a_panel_program_is_live` (15.1).

### 15.5 `league/constitution.py`: generated, never typed

No diff is given, on purpose: the list is the House's (`<state>/equity-daily/universe/tradable.json`, written by
package A's `equity_universe` job after R-E4a is deployed) and no builder has it. The change is exactly what this
command writes, on the owner's machine, in a clean checkout of the integration head:

    python3 scripts/gen_universe.py --from tradable.json --gateway-patch ~/universe.patch
    git apply ~/universe.patch                          # the owner's step: gateway/ is the owner's (15.6)
    python3 scripts/gen_universe.py --from tradable.json --check
    python3 -m league.ci --no-tests
    (cd gateway && npm run check && npm test)

What it writes in `league/constitution.py`, and nothing else (it refuses its own rewrite otherwise):

- the `"stock": [...]` literal that closes `equity_money.universe` becomes the generated block, between
  `# --- generated by scripts/gen_universe.py: do not edit by hand ---` and `# --- end of the generated universe ---`
  (a comment saying what the list is, the count, the sorted tickers at most 120 columns wide, then the `},` that
  closes `universe` on its own line). `universe.etf` and every other row are byte for byte what they were;
- `PINNED_DIGEST` re-pinned to the new `digest()`. It prints both digests and both money digests, before and after:
  they go into the commit message and CHANGELOG.md's entry.

The commit: `league/constitution.py` and `gateway/lib/caps.mjs`, marked **UNIVERSE (moves the money digest; deployed
separately)**. Held by `league.tests.test_gen_universe` (`TheTreeAsItStands`: the tree's two lists are E1's 18 or
byte for byte what the generator writes for the list they hold, sorted, with no date; `TheConstitution`: nothing but
the list and the pin moves), `test_constitution` (`digest() == PINNED_DIGEST`; 15.2), `test_equity_money` (15.1) and
`test_ci.TheEquityLane` (the two lists are one list).

### 15.6 `gateway/lib/caps.mjs` and `gateway/test/stock-buys.test.mjs`: a patch file, never an edit here

`~/Work/.ltcm-main/scratch/eqe4/gateway-universe.patch` (the captain's private scratch). It is the STATIC half, written
once and applicable today (it changes no list): the two markers around `STOCK_UNIVERSE`'s stock pairs; the refusal of
an unlisted symbol names the 17 ETFs and COUNTS the stocks instead of spelling out every symbol (hundreds since E4);
the gateway's stock tests no longer use a well-known ticker as "unlisted" (TSLA would be listed) nor pin the stock
list (the ETFs stay pinned; the stocks are E1's 18 as they stood, or a generated list: 450 to 650, sorted, E1's among
them); two comments (README, wrangler.jsonc). Its header carries the gateway suite's expected results before and
after a generated list. THE LIST ITSELF is the second, GENERATED patch (`--gateway-patch`, above), which rewrites only
the lines between the markers. The generator also works on a `caps.mjs` that has no markers yet (it puts them in),
but the gateway's own tests are green on a grown list only with the static half applied, so the static half goes
first (it may be deployed at any time: a marker comment and a shorter refusal text change no order's fate).

## At the integration head (`feat/equity-e2-int` `a4514e83`, 44 commits past the Step 0 base's parent)

Checked on a scratch copy of that head with Step 0 and package I's branch on it. Of this file's diffs, 16.1, 16.2,
16.3, 16.4, 16.5, 15.1 and 15.4 apply there AS THEY ARE (`git apply --check`), and so does the gateway's patch file
(`gateway/` did not move). Three hunks need the head's own lines, because the captain's A20 and A21 moved E1's
digests after the base and E1's review added a line to the pre-open job. They are given here as they apply there,
and the same tests pass there (the last section).

`league/tests/test_constitution.py` (15.2 at the head):

```diff
diff --git a/league/tests/test_constitution.py b/league/tests/test_constitution.py
index c799981..91621c9 100644
--- a/league/tests/test_constitution.py
+++ b/league/tests/test_constitution.py
@@ -152,17 +152,28 @@ class ConstitutionTest(unittest.TestCase):
         import copy
 
         from league.constitution import RISK_FREE, money_digest
+        from league.equity import config
 
-        self.assertEqual(money_digest(), "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a")
-        self.assertEqual(PINNED_DIGEST, "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895")
+        # RELEASE E4's UNIVERSE (R-E4b; scripts/gen_universe.py) grows `equity_money.universe.stock` around E1's 18 names
+        # and moves both digests again, AND NOTHING ELSE MOVES WITH IT: E1's figures below are read on the constitution
+        # with E1's universe put back (`league.equity.config.UNIVERSE`, which E4 never changes), so they hold before
+        # the universe deploy and after it, and a row that moved with the list would fail them.
+        e1 = copy.deepcopy(CONSTITUTION)
+        e1["equity_money"]["universe"] = {klass: [s for s, k in config.UNIVERSE.items() if k == klass]
+                                          for klass in config.CLASSES}
+        self.assertEqual(money_digest(e1), "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a")
+        self.assertEqual(digest(e1), "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895")
+        self.assertEqual(PINNED_DIGEST, digest())
+        if CONSTITUTION["equity_money"]["universe"] != e1["equity_money"]["universe"]:
+            self.assertNotEqual(money_digest(), money_digest(e1), "the universe is a money rule: the grant re-ratifies")
         before = copy.deepcopy(CONSTITUTION)
         del before["equity_money"]
         self.assertEqual(money_digest(before), "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7")
-        off = copy.deepcopy(CONSTITUTION)
+        off = copy.deepcopy(e1)
         off["equity_money"]["enabled"] = False
         self.assertEqual(money_digest(off), "23f17a1467610f8d252b55c6d6748f8fb1311a0142e3f92c43d4bff710886579")
         # A20's rollback: the sleeve back at a quarter of E, the sizing-up step still parked, is a pair of its own...
-        quarter = copy.deepcopy(CONSTITUTION)
+        quarter = copy.deepcopy(e1)
         quarter["equity_money"]["probe"]["sleeve_share"] = "0.25"
         self.assertEqual(money_digest(quarter), "3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2")
         self.assertEqual(digest(quarter), "6d19fddd271cc46682e48e09ae14364976b76077ca084198874f47dbf4340b43")
@@ -171,7 +182,7 @@ class ConstitutionTest(unittest.TestCase):
         self.assertEqual(money_digest(quarter), "ad8c761bccc49033c3fdeca78c7b962f58272d192a2dd6e0626682ccdf6ac367")
         self.assertEqual(digest(quarter), "65b0e025a08d4c3a8f78e487eb1a0f83ad9bfed307563c02acbd50ac4a6308bb")
         # The row alone (the sleeve at 0.50, sizing up as pre-registered) is the digest of the commit before the park.
-        unparked = copy.deepcopy(CONSTITUTION)
+        unparked = copy.deepcopy(e1)
         unparked["equity_money"]["sized"]["min_trades"] = 20
         self.assertEqual(money_digest(unparked), "d8c96f66d556c2123b9e797c901075f43af34ad182de3b965fceeca0a7c97f14")
         self.assertFalse(any(path[0] == "equity_money" for path in RISK_FREE))
```

`league/tests/test_live_long_single.py` (15.3 at the head):

```diff
diff --git a/league/tests/test_live_long_single.py b/league/tests/test_live_long_single.py
index ba079b8..254d7ba 100644
--- a/league/tests/test_live_long_single.py
+++ b/league/tests/test_live_long_single.py
@@ -22,7 +22,9 @@ REPO = Path(__file__).resolve().parents[2]
 #: was a3e2aa7c; the incubator's row (release B, Oct 1, 2026: `options_money.incubator`) moved it, then the incubator
 #: cap (Oct 8) to 1665c385, release L-D (Oct 9) to 0310779c, the Probe total at $800 (Oct 10, 2026) to fdf2ac7c, and
 #: release E1's `equity_money` (the equity lane, its Probe sleeve at 0.50 x E and its sizing-up step parked: one move)
-#: to this one.
+#: to this one. Release E4's universe (the panel's tradable union in `equity_money.universe.stock`,
+#: scripts/gen_universe.py) moves it once more and is the only row that does: the test below reads this figure with
+#: E1's universe put back, so it holds before that deploy and after it.
 MONEY_DIGEST = "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a"
 
 #: One program, two sides: a long call first, then (once the call is held) a long put. The side rule here is a clock so the
@@ -78,7 +80,12 @@ class TheDeclaredType(unittest.TestCase):
             self.assertTrue(set(types) <= set(OPTIONS_REAL_TYPES))
 
     def test_the_money_table_and_its_digest_are_unchanged(self):
-        self.assertEqual(money_digest(), MONEY_DIGEST)
+        from league.equity import config
+
+        e1 = copy.deepcopy(CONSTITUTION)
+        e1["equity_money"]["universe"] = {klass: [s for s, k in config.UNIVERSE.items() if k == klass]
+                                          for klass in config.CLASSES}
+        self.assertEqual(money_digest(e1), MONEY_DIGEST)
         self.assertEqual(CONSTITUTION["options_money"]["real_types"], ["debit_vertical", "long_butterfly", "long_call", "long_put"])
         self.assertEqual(M.Table.from_constitution().real_types, ("debit_vertical", "long_butterfly", "long_call", "long_put"))
         self.assertTrue(digest())
```

`league/ops/preopen.py` (16.3's second literal, in `collect`'s `bands()`; applied after 16.3):

```diff
diff --git a/league/ops/preopen.py b/league/ops/preopen.py
--- a/league/ops/preopen.py
+++ b/league/ops/preopen.py
@@ -235,9 +235,11 @@
         rows = B.read(root)
         # The options lanes' families only, as `B.read(root)` and the options roster above are: an equity family in a live
         # band has its row in the equity lanes' own read (`B.read(root, lanes=LANES)`) and is check 10's (release E2).
+        from ..swarm.store import OPTIONS_ONLY_SQL
+
         live_fams = guard.read(root / "swarm.sqlite", lambda db: guard.rows(
             db, "SELECT id, band FROM families WHERE retired_at IS NULL AND band IN ('candidate','probe','sized') "
-                "AND structure NOT IN ('etf', 'stock') ORDER BY id"))
+                f"AND {OPTIONS_ONLY_SQL} ORDER BY id"))
         acct = (out.get("gateway") or {}).get("account") or {}
         cap = ((out.get("grant") or {}).get("policy") or {}).get("capital_usd")
         E = min(M.D(acct["equity"]), M.D(cap)) if acct.get("equity") is not None and cap is not None else None
```

## Found while building, outside package I's files (for the integrator)

- `league/ops/stall.py` has the same two structure literals as 16.3 (`OPTIONS_FAMILIES = "structure NOT IN ('etf',
  'stock')"` and `OPTIONS_RUNS`): the stall alarm would count a panel family and its runs as the options lanes'. No
  E4 package authors that file. The same replacement fits (`OPTIONS_FAMILIES = OPTIONS_ONLY_SQL`, and `OPTIONS_RUNS`
  built from `store.EQUITY_STRUCTURES`); E4-SPEC 8.2 asks it of every scope that spells the two structures out, and
  package G's `test_elane_xs.NoStructureLiteralOutsideTheStore` reads league/swarm only.
- `league/equity/config.py`'s docstring says the constitution's universe EQUALS `UNIVERSE`. Since R-E4b it is inside
  it. The file is an evidence module: a byte changed there moves the equity identity, so it is left as it is and
  docs/operations.md says so.
- The gateway's merge list (`gateway/lib/protected.mjs` MERGE_FORBIDDEN) owes seven entries now (E2's five and E4's
  two): one gateway follow-up, after which `PENDING_GATEWAY` empties into `FORBIDDEN`.

## What was run (scratch copies of the tree; nothing here was pushed, deployed or sent anywhere)

- **The generator** (`league.tests.test_gen_universe`, 48 tests): Python 3.14 and 3.11 (with numpy and without), on
  the base, at the integration head, with E1's list and with a generated one. 21 single-line faults put into
  `scripts/gen_universe.py` one at a time (an ETF let through, a size bound moved, E1's stocks not kept, another
  rule allowed to move, the pin not re-pinned, the read-back skipped, a write without the gateway's patch, a patch
  into gateway/, `--check` writing, a date in the block, ...): each fails the tests.
- **The base (`24a52b11`) with this file's diffs and the gateway's static patch** (the R-E4a state): `test_ci`,
  `test_equity_money`, `test_constitution`, `test_live_long_single`, `test_gen_universe`, `test_ops_jobs`,
  `test_swarm_roster`, `test_e4_stubs`, `test_standing_grant`, `test_ld_release`, `test_equity_book`, `test_ops_stall`:
  459 tests OK on 3.14 and on 3.11. `python3 -m league.ci --no-tests` passes. THE WHOLE LEAGUE SUITE on 3.14: 9048
  tests OK, 29 skipped (two tests of `test_gen_universe` were added after that run and are in the 9050 below).
- **The same tree with the UNIVERSE commit simulated** (the generator run on a stand-in list of 524 names, its
  gateway patch applied: exactly two files change, `league/constitution.py` and `gateway/lib/caps.mjs`): the same
  modules, 459 tests OK on 3.14 and on 3.11; `--check` holds; `league.ci --no-tests` passes; THE WHOLE LEAGUE SUITE on
  3.14: 9050 tests OK, 29 skipped.
- **A grown universe WITHOUT this file's test changes:** the whole suite, 9040 tests, 8 failures:
  `test_ci.TheEquityLane.test_the_universe_changes_with_the_gateways_list`;
  `test_constitution...test_the_equity_lane_moved_the_money_digest_to_the_one_the_grant_re_ratifies`;
  `test_equity_money.TheGrantReRatifies` (four) and `TheTable.test_the_universe_and_shares_are_the_lanes_constants`;
  `test_live_long_single.TheDeclaredType.test_the_money_table_and_its_digest_are_unchanged`. That list is what patch
  15 is made of.
- **The gateway's suite** (`node --test test/*.test.mjs`, node 26): the base 455 of 455; with the static patch 457 of
  457; with the static patch and a generated list 457 of 457; a generated list without the static patch fails 5.
- **At the integration head** (`feat/equity-e2-int` `a4514e83` + Step 0 + package I's branch + the diffs as given for
  that head): the same modules, 463 tests OK on 3.14 and on 3.11, with E1's list and with a generated one;
  `league.ci --no-tests` passes; the gateway's suite 457 of 457 with a generated list; THE WHOLE LEAGUE SUITE on 3.14
  with the UNIVERSE commit simulated: 9189 tests OK, 29 skipped.
- Every diff of this file was written to a plain file, applied with `git apply` to a clean copy of the base (and the
  head's to a clean copy of the head), and the result compared byte for byte with the tree the tests ran on.
