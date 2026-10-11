"""RELEASE E4, STEP 0: the contract its packages build against (league/xs/E4_INTERFACES.md).

Step 0 gave every NEW module of the release its public names, its shared dataclasses and constants and the DDL of its
one table, so each package can import the others' names from day one. This file holds that contract still: every
module imports and has the names it publishes, the DDL creates, and the shared shapes are the ones every package was
told. It is the INTEGRATOR'S file: a package that needs one of these shapes changed says so to the integrator and
changes nothing here. It never asserts that a function is unbuilt, so it keeps passing as the packages land.

Nothing here reads market data: there is none in the repository.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import importlib
import sqlite3
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Every module release E4 adds, by the package that owns it (league/xs/E4_INTERFACES.md's table). J is owed.
MODULES = {
    "A": ("league.ops.equity_universe", "league.ops.equity_panel"),
    "B": ("league.ops.equity_spreads", "league.ops.equity_neff", "league.ops.french"),
    "C": ("league.xs", "league.xs.config", "league.xs.store", "league.xs.ctx", "league.xs.program",
          "league.xs.synth"),
    "D": ("league.xs.engine", "league.xs.results", "league.xs.placebo", "league.xs.runner", "league.xs.child"),
    "E": ("league.xs.screen", "league.xs.identity"),
    "G": ("league.swarm.elane_xs", "league.ops.xs_zero_edge"),
    "H": ("league.xs.book",),
    "J": ("league.ops.forward_xs",),
}
SCRIPTS = {"A": "scripts/panel_probe.py", "I": "scripts/gen_universe.py"}
PATCH_AUTHORS = ("A", "B", "D", "E", "G", "H", "I", "J")


def fields(cls) -> tuple[str, ...]:
    return tuple(f.name for f in dataclasses.fields(cls))


def script(path: str):
    return importlib.import_module(path[:-3].replace("/", "."))


class EveryStubImports(unittest.TestCase):
    def test_every_module_imports_and_has_the_names_it_publishes(self):
        for key, names in MODULES.items():
            for name in names:
                module = importlib.import_module(name)
                self.assertTrue((module.__doc__ or "").strip(), f"{name} has no docstring")
                published = getattr(module, "__all__", None)
                self.assertIsNotNone(published, f"{name} publishes no __all__")
                for attr in published:
                    self.assertTrue(hasattr(module, attr), f"package {key}: {name}.{attr} is published and missing")

    def test_the_scripts_load(self):
        for key, path in SCRIPTS.items():
            module = script(path)
            self.assertTrue(callable(module.main), f"package {key}: {path} has no main")

    def test_one_patch_file_an_author(self):
        folder = REPO / "league" / "swarm" / "e4_patches"
        self.assertEqual(sorted(p.name for p in folder.glob("*.md")),
                         sorted(["README.md", *(f"{key}.md" for key in PATCH_AUTHORS)]))

    def test_the_panel_package_stays_flat_and_imports_no_plumbing_of_the_house(self):
        """The decider child's runtime copies league/xs/*.py only; nothing of league.live, league.swarm or league.ops
        is importable there, at any depth of a function."""
        folder = REPO / "league" / "xs"
        self.assertFalse([p for p in folder.rglob("*.py") if p.parent != folder], "league/xs has a sub-package")
        for path in sorted(folder.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.level:
                    target = "league." + ".".join(filter(None, ["xs" if node.level == 1 else "", node.module or ""]))
                elif isinstance(node, ast.ImportFrom):
                    target = node.module or ""
                elif isinstance(node, ast.Import):
                    target = " ".join(a.name for a in node.names)
                else:
                    continue
                for banned in ("league.live", "league.swarm", "league.ops"):
                    self.assertNotIn(banned, target, f"{path.name} imports {target}")


class TheTable(unittest.TestCase):
    def setUp(self):
        from league.equity import live
        from league.xs import book

        self.book = book
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(live.SCHEMA)

    def tearDown(self):
        self.db.close()

    def columns(self, table: str) -> list[str]:
        return [row[1] for row in self.db.execute(f"PRAGMA table_info({table})")]

    def test_the_ddl_creates_beside_e1s_and_twice(self):
        self.db.executescript(self.book.SCHEMA)
        self.db.executescript(self.book.SCHEMA)
        self.assertEqual(self.columns("eq_rebalances"), [
            "rid", "instance", "family", "version", "decided_day", "exec_day", "at", "called", "targets", "standing",
            "n_names", "n_sells", "n_buys", "n_skipped", "skipped", "equity", "budget", "extra", "ctx_sha", "bars_sha",
            "fetch", "audit", "status", "why", "created_at"])

    def test_one_row_an_instance_and_decision_day(self):
        self.db.executescript(self.book.SCHEMA)
        row = ("fam@1:r", "fam", 1, "2027-01-04", "2027-01-05", "open", 1, "[]", 0, 0, 0, 0, "planned", 1.0)
        insert = ("INSERT INTO eq_rebalances (instance, family, version, decided_day, exec_day, at, called, targets, "
                  "n_names, n_sells, n_buys, n_skipped, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
        self.db.execute(insert, row)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(insert, row)
        got = self.db.execute("SELECT standing, skipped, extra, fetch, audit FROM eq_rebalances").fetchone()
        self.assertEqual(got, (0, "[]", "[]", "{}", None))

    def test_an_e1_instance_reads_as_the_equity_kind(self):
        self.assertNotIn(self.book.INSTANCE_KIND_COLUMN, self.columns("eq_instances"))
        self.db.execute("INSERT INTO eq_instances (id, family, version, lane, run_sha, code, params, band, max_hold, "
                        "created_at) VALUES ('f@1:r', 'f', 1, 'beta', 's', 'c', '{}', 'probe', 20, 1.0)")
        self.db.execute(self.book.INSTANCE_KIND_DDL)
        self.assertIn(self.book.INSTANCE_KIND_COLUMN, self.columns("eq_instances"))
        self.assertEqual(self.db.execute("SELECT kind FROM eq_instances").fetchone(), ("equity",))


class TheSharedShapes(unittest.TestCase):
    def test_what_a_run_is_sent_holds_no_aid_and_no_symbol(self):
        from league.xs import store

        self.assertEqual(fields(store.PanelBars), ("days", "early", "first", "raw", "adj", "elig0", "ref", "ids",
                                                    "exit", "hs", "sector_perm", "dither_key", "window",
                                                    "data_version"))
        self.assertEqual(fields(store.Slice), ("bars", "aids", "run_key"))
        for name in fields(store.PanelBars):
            self.assertNotIn("aid", name)
            self.assertNotIn("symbol", name)

    def test_the_ctx_is_the_pre_registered_contract(self):
        """XSCREEN-1's C1: slots, scale-free fields, the calendar's four counts; no ticker, no date, no price level, no
        event flag, no size or liquidity handle."""
        from league.xs import ctx

        self.assertEqual(ctx.XsCtx.__slots__, (
            "n", "ids", "ret", "oret", "iret", "range", "rel_volume", "sector", "beta", "mkt", "positions", "closed",
            "rejects", "cash", "equity", "budget", "weekday", "session_of_month", "sessions_left_in_month",
            "last_session_of_week", "max_names", "params"))
        self.assertEqual(ctx.FIELDS, ("ret", "oret", "iret", "range", "rel_volume"))
        self.assertEqual(ctx.Fields.__slots__, ctx.FIELDS)
        for banned in ("open", "high", "low", "close", "price", "prices", "volume", "symbols", "symbol", "day", "date",
                       "year", "month", "events", "events_next", "dv_decile", "aids", "caps"):
            self.assertNotIn(banned, ctx.XsCtx.__slots__, f"the ctx carries {banned}")
        self.assertEqual(fields(ctx.Inputs), ("days", "raw", "adj", "elig0", "ref", "ids", "dither_key", "sector_perm",
                                              "history", "max_names", "trading_days", "early", "positions", "closed",
                                              "rejects", "cash", "equity", "budget", "params"))
        self.assertEqual(fields(ctx.Derived), ("elig", "beta", "mom", "sector", "bg", "mg", "cell", "rung"))

    def test_the_program_the_engine_and_the_runner(self):
        from league.equity import runner as e1
        from league.xs import engine, program, results, runner

        self.assertEqual(fields(program.Needs), program.NEEDS_KEYS)
        needs = program.Needs("sp500", 252, 10, "weekly", 0, 60)
        self.assertEqual(tuple(needs.as_dict()), program.NEEDS_KEYS)
        self.assertEqual(fields(engine.EngineConfig), ("capital", "k", "timeout", "max_errors", "budget_seconds",
                                                       "haircut"))
        self.assertEqual(engine.EngineConfig().identity(), {"capital": "1000", "k": 1.0, "timeout": 1.0,
                                                            "max_errors": 25, "haircut": 0.3})
        self.assertEqual(fields(runner.Run), ("result", "slice"))
        self.assertIs(runner.RunFailed, e1.RunFailed)
        self.assertIs(runner.RunLost, e1.RunLost)
        self.assertIs(runner.ProgramRefused, e1.ProgramRefused)
        self.assertIs(runner.SENT_NOT_ANSWERED, e1.SENT_NOT_ANSWERED)
        self.assertEqual(results.DAILY, ("day", "r", "x", "x15", "u", "w", "bench", "exits", "invested", "equity"))

    def test_the_screen_is_the_pre_registered_gate(self):
        from league.equity import screen as s2
        from league.xs import placebo, screen

        self.assertEqual(fields(screen.ReceiptXS), ("receipt_sha256", "c_XS", "c_margin", "alpha_plac",
                                                     "placebo_draws", "rung", "fp_cap", "owner_wall", "retry", "flags",
                                                     "screen_flags", "beside", "fp"))
        self.assertEqual(screen.BESIDE_FIELDS, ("c_used", "c_p", "own_fp", "n_cell", "basket", "label", "flags"))
        self.assertEqual((screen.SCREEN, screen.RECEIPT_PATH), ("XS1", "docs/benchmarks/equity_screen_xs_1.json"))
        self.assertEqual((screen.FP_CAP, screen.OWNER_WALL, screen.ALPHA_PLAC, screen.C_MARGIN), (0.12, 0.15, 0.12, 0.05))
        self.assertEqual((screen.PLACEBO_DRAWS, placebo.DRAWS), (999, 999))
        # the placebo bar in integers: (1 + count) x 100 <= 12 x 1000, so 119 passes and 120 fails
        self.assertLessEqual((1 + screen.PLACEBO_COUNT_MAX) * 100, 12 * (screen.PLACEBO_DRAWS + 1))
        self.assertGreater((2 + screen.PLACEBO_COUNT_MAX) * 100, 12 * (screen.PLACEBO_DRAWS + 1))
        self.assertEqual((screen.H_LENGTH, screen.V_LENGTH), (194, s2.V_LENGTH))
        self.assertEqual(screen.SAME_LINEAGE_CORR, s2.SAME_LINEAGE_CORR)
        self.assertEqual((screen.VALIDATION_TRIES, screen.LOOKS_PER_LINEAGE, screen.LINEAGE_SERIES), (1, 1, ("x", "u")))
        self.assertEqual((screen.CHECKPOINTS, screen.ALPHA_F), ((20, 60, 120, 250), {"fresh": 0.12, "looked": 0.03}))
        self.assertIs(screen.ScreenRefused, s2.ScreenRefused)
        self.assertIs(screen.Series, s2.Series)

    def test_the_book_adapters_shapes_and_the_captains_a17(self):
        from league.xs import book

        self.assertEqual(fields(book.Columns), ("symbols", "aids", "ids", "elig0", "sector_perm", "dither_key", "extra"))
        self.assertEqual(fields(book.Fetched), ("days", "raw", "all", "meta"))
        self.assertIs(book.HOLD_DAY_FAILS_EXIT, False, "A17: a hold day's fetch failure counts toward no exit")
        self.assertEqual((book.FETCH_CHUNK, book.MAX_INTENTS, book.TWINS_FILE), (39, 24, "xs-twins.json"))


class TheConstants(unittest.TestCase):
    def test_the_spans_never_hold_2020_and_the_train_segments_lie_inside_e1s(self):
        from league.equity import config as e1
        from league.xs import config

        self.assertEqual(config.TRAIN_YEARS, (2017, 2018, 2019, 2022, 2023, 2024))
        self.assertEqual((config.HISTORY_YEARS, config.RESERVE_YEARS), ((2016, 2021), (2020,)))
        for _, first, last in config.SPANS:
            years = range(first.year, (last or dt.date(2030, 1, 1)).year + 1)
            self.assertNotIn(2020, years)
        for (first, last), (era_first, era_last) in zip(config.TRAIN_SEGMENTS, e1.TRAIN_ERA_SEGMENTS):
            self.assertTrue(era_first <= first <= last <= era_last)

    def test_the_contracts_limits(self):
        from league.equity import config as e1
        from league.xs import config

        self.assertEqual(config.XS_SLEEVE_USD, e1.SLEEVE_USD, "the pre-registration's E0 is E1's Gym sleeve")
        self.assertEqual(config.MIN_NAME_USD, e1.MIN_ORDER_USD)
        self.assertEqual(config.POSITION_SHARE, e1.POSITION_SHARE[e1.STOCK])
        self.assertEqual(config.MAX_HOLD_CAP, e1.MAX_HOLD_CAP)
        self.assertEqual((config.MIN_NAMES, config.MAX_NAMES, config.MAX_WEIGHT), (5, 40, 0.20))
        self.assertEqual((config.MAX_BUYS, config.MAX_SELLS, config.MAX_ORDERS), (12, 12, 24))
        self.assertEqual((config.MIN_VALID, config.WINDOW, config.DERIVE_SESSIONS, config.MEMBER_AHEAD), (200, 252, 253, 2))
        self.assertEqual(config.HS_FLOOR_BP, 3.0, "never under the registered contract's 3 bp a fill")
        self.assertEqual(config.HS_FALLBACK_BP, (10.0, 5.0))
        self.assertEqual((config.STRESS_SPREAD, config.STRESS_FEES, config.VANISH_HAIRCUT), (0.5, 1.0, 0.30))
        self.assertIsInstance(config.XS_SLEEVE_USD, Decimal)

    def test_the_funds_and_the_cells(self):
        from league.xs import config

        self.assertEqual(config.FUNDS, ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"))
        self.assertEqual(sorted([*config.FUNDS, "SPY"]), sorted(config.REF))
        self.assertEqual([config.REF[i] for i in config.FUND_COLUMNS], list(config.FUNDS))
        self.assertEqual(config.REF[config.MARKET_COLUMN], "SPY")
        self.assertEqual(config.RUNGS["R0"], ((45, (3, 3)), (20, (2, 2)), (10, (1, 2)), (5, (1, 1))))
        self.assertEqual(config.RUNGS["R1"], ((20, (2, 2)), (10, (1, 2)), (5, (1, 1))))
        cells = {config.CELL_SECTOR * s + config.CELL_BETA * b + m for s in range(11) for b in range(3) for m in range(3)}
        self.assertEqual(len(cells), 99)
        self.assertNotIn(config.SMALL_CELL, cells)
        self.assertTrue(config.VANISH_DEAL.search("Acquired by a rival"))
        self.assertFalse(config.VANISH_DEAL.search("market capitalization change"))

    def test_the_vendors_cents_one_bound(self):
        from league.xs import config

        self.assertAlmostEqual(config.rounding_bound(100.0, 50.0), 1.5 * 0.005 * (1 / 100 + 1 / 50), places=15)
        for bad in ((), (0.0,), (-1.0,), (float("nan"),), (float("inf"), 10.0)):
            with self.assertRaises(ValueError):
                config.rounding_bound(*bad)

    def test_the_identitys_lists_are_e1s_where_they_must_be(self):
        from league.swarm import evaluator
        from league.xs import identity

        self.assertEqual(identity.XS_GYM_FILES, evaluator.EQUITY_GYM_FILES)
        self.assertEqual(identity.XS_CALENDAR_FILES, evaluator.EQUITY_CALENDAR_FILES)
        self.assertEqual(identity.XS_EVIDENCE_ROOTS, evaluator.EQUITY_EVIDENCE_ROOTS)
        self.assertLessEqual(set(identity.XS_EQUITY_DEPS), set(evaluator.EQUITY_EVIDENCE))
        for name in identity.XS_EVIDENCE:
            self.assertTrue((REPO / "league" / "xs" / f"{name}.py").is_file(), name)
        self.assertFalse(set(identity.XS_PLUMBING) & set(identity.XS_EVIDENCE))
        from league.equity import ctx as e1ctx

        for private in identity.XS_PRIVATE_E1:
            self.assertTrue(hasattr(e1ctx, private), f"league.equity.ctx.{private} is gone")

    def test_the_swarm_lanes_names_and_its_switch_ships_off(self):
        from league.swarm import elane_xs
        from league.xs import screen

        self.assertEqual(elane_xs.MODES, ("off", "train", "gate", "live"))
        self.assertEqual(elane_xs.DEFAULTS["mode"], "off")
        self.assertEqual(elane_xs.STRUCTURE, "panel")
        self.assertEqual(len(set(elane_xs.SEALED)), 8)
        self.assertIn(elane_xs.TRAIN_X_KEY, elane_xs.SEALED)
        self.assertIn(elane_xs.TRAIN_U_KEY, elane_xs.SEALED, "the House keeps BOTH Train series (the lineage rule)")
        self.assertIn(elane_xs.PRECHECK_KEY, elane_xs.SEALED)
        self.assertEqual(tuple(elane_xs.SCREEN_NULLS), screen.PIN_KEYS)
        self.assertIsNone(elane_xs.SCREEN_NULLS["receipt_sha256"], "no receipt is pinned: every panel look waits")
        for key, (low, high) in elane_xs.BOUNDS.items():
            self.assertTrue(low <= elane_xs.DEFAULTS[key] <= high, key)
        self.assertEqual(set(elane_xs.JUDGED_XS) - set(elane_xs.FAILS_XS), set())

    def test_each_jobs_wall_is_stated_once(self):
        """E4-SPEC 13: every E4 job asks `quiet` with its own wall; package A's registry rows are held to these."""
        walls = {"equity_universe": 900, "equity_panel": 3300, "equity_spreads": 3000, "equity_neff": 900,
                 "french": 300, "xs_zero_edge": 3000}
        for name, wall in walls.items():
            self.assertEqual(importlib.import_module(f"league.ops.{name}").WALL_S, wall, name)


if __name__ == "__main__":
    unittest.main()
