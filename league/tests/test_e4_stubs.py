"""RELEASE E4, STEP 0: the contract its packages build against (league/xs/E4_INTERFACES.md).

Step 0 gave every NEW module of the release its public names, its shared dataclasses and constants and the DDL of its
one table, so each package can import the others' names from day one. This file holds that contract still: every
module imports and has the names it publishes, the DDL creates, and the shared shapes are the ones every package was
told. It is the INTEGRATOR'S file: a package that needs one of these shapes changed says so to the integrator and
changes nothing here. It never asserts that a function is unbuilt, so it keeps passing as the packages land.

It also holds the study's conformance fixtures (synthetic inputs; XSCREEN-1's vectors, byte for byte, and the inputs
they were computed from) to each other, so packages D and E reproduce ONE set of vectors.

Nothing here reads market data: there is none in the repository.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import hashlib
import importlib
import inspect
import json
import math
import sqlite3
import unittest
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
#: The study's conformance vectors (XSCREEN-1's work/conformance_xs1.json), committed byte for byte.
VECTORS = FIXTURES / "xs1_conformance.json"
VECTORS_SHA256 = "386995d8d8c86baec17f1c378b7c067be43ef39653c3879f71d059d0beae7e3c"
#: The synthetic inputs of V1-V6 and the plain reference's series (written at Step 0 from the study's own generator).
INPUTS = FIXTURES / "xs1_conformance_inputs.npz"

#: Every module release E4 adds, by the package that owns it (league/xs/E4_INTERFACES.md's table). J is owed.
MODULES = {
    "A": ("league.ops.equity_universe", "league.ops.equity_panel"),
    "B": ("league.ops.equity_spreads", "league.ops.equity_neff", "league.ops.french"),
    "C": ("league.xs", "league.xs.config", "league.xs.store", "league.xs.ctx", "league.xs.program",
          "league.xs.synth"),
    "D": ("league.xs.engine", "league.xs.results", "league.xs.placebo", "league.xs.runner", "league.xs.child"),
    "E": ("league.xs.screen", "league.xs.identity", "league.xs.style"),
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
                                                     "placebo_draws", "rung", "fp_cap", "owner_wall",
                                                     "validation_tries", "holdout_looks", "retry", "flags",
                                                     "screen_flags", "beside", "fp"))
        # every pinned value but the file's own sha has its place in the receipt, and the pin is the dataclass
        self.assertEqual(set(screen.PIN_SOURCES), set(screen.PIN_KEYS) - {"receipt_sha256"})
        self.assertLessEqual({source.split(".")[0] for source in screen.PIN_SOURCES.values()}, set(screen.RECEIPT_KEYS))
        self.assertLessEqual(set(screen.PIN_KEYS) - {"name", "screen"}, set(fields(screen.ReceiptXS)))
        self.assertEqual(screen.FLOOR_CELLS, ("both", "D", "C"))
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

    def test_the_captains_a22_is_in_the_contract(self):
        """Before any real money on an XS1 pass: a style-open program takes no seat on the pass alone; at most 2 looks
        an agenda cell; the review and the contamination probe before a look."""
        from league.swarm import elane_xs
        from league.xs import engine, identity, runner, style

        self.assertEqual(style.CHARACTERISTICS, ("size", "beta", "mom", "vol"))
        self.assertEqual((style.TILT, style.MIN_LOTS), (1.0 / 3.0, 40))
        self.assertEqual((style.SIZE_SESSIONS, style.SIZE_MIN_VALID, style.VOL_SESSIONS, style.VOL_MIN_VALID),
                         (63, 55, 60, 55), "the study's own definitions (its arm STYLE)")
        self.assertEqual(elane_xs.SEAT_STYLE, style.OPEN)
        self.assertIn("style", identity.XS_EVIDENCE, "the style rule is evidence: the engine imports it")
        for function in (engine.run, engine.run_isolated, runner.run_bars, runner.Isolated.train):
            parameter = inspect.signature(function).parameters["style"]
            self.assertIs(parameter.default, False, f"{function.__qualname__}: no style block unless asked")
        self.assertEqual(elane_xs.MAX_CELL_LOOKS, 2)
        self.assertNotIn("cell_looks", elane_xs.DEFAULTS, "the cap on a cell's looks is a House rule, never a setting")
        self.assertEqual(elane_xs.PROBE_STRATA, ("P4", "P5", "P6"))
        # The swarm reads the probe's PERMIT (two words a stratum and era, written by the probe's job), never the
        # probe's own file: release E3's seal lets no module of league/swarm name that one.
        self.assertEqual((elane_xs.PROBE_FILE, elane_xs.PROBE_VERSION), ("xs-look-permit.json", "xs-look-permit-1"))
        rubric = " ".join(elane_xs.REVIEW_XS)
        for words in ("embedded return table", "calendar recognition"):
            self.assertIn(words, rubric)
        # the style verdict is a Train fact (the record's own field), never one of the sealed keys
        self.assertNotIn(elane_xs.STYLE_FIELD, elane_xs.SEALED)

    def test_each_jobs_wall_is_stated_once(self):
        """E4-SPEC 13: every E4 job asks `quiet` with its own wall; package A's registry rows are held to these."""
        walls = {"equity_universe": 900, "equity_panel": 3300, "equity_spreads": 3000, "equity_neff": 900,
                 "french": 300, "xs_zero_edge": 3000}
        for name, wall in walls.items():
            self.assertEqual(importlib.import_module(f"league.ops.{name}").WALL_S, wall, name)


class TheStudysVectors(unittest.TestCase):
    """XSCREEN-1's conformance vectors and their synthetic inputs: one set, for packages D and E alike."""

    @classmethod
    def setUpClass(cls):
        import numpy as np

        cls.np = np
        cls.vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        cls.inputs = np.load(INPUTS)
        cls.manifest = json.loads(bytes(cls.inputs["manifest"]).decode("utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.inputs.close()

    def looks(self):
        for key, vector in self.vectors["vectors"].items():
            if "look" in vector:
                yield key.split()[0], vector

    def test_the_vectors_are_the_studys_file_byte_for_byte(self):
        self.assertEqual(hashlib.sha256(VECTORS.read_bytes()).hexdigest(), VECTORS_SHA256)
        self.assertEqual(self.manifest["vectors_sha256"], VECTORS_SHA256, "the inputs were made for these vectors")
        self.assertEqual(sorted(self.vectors["vectors"]),
                         ["CH", "H", "V1 pass", "V2 fail", "V3 pre-check", "V4 stress", "V5 own floor",
                          "V6 ineligible"])
        self.assertEqual((self.vectors["world"]["validation"], self.vectors["world"]["holdout"]),
                         ([0, 249], [250, 443]))
        self.assertEqual({v["look"]["verdict"] for _, v in self.looks()},
                         {"PASS", "FAIL", "REFUSED AT THE PRE-CHECK", "INELIGIBLE"})

    def test_no_vector_has_the_second_segments_floor_cell_alone(self):
        """Why the captain's A22 (4) asks package E for a ninth, derived by hand: the House's own third floor cell."""
        cells = {name for _, v in self.looks() for name in v["floor"]["cells"]}
        self.assertEqual(cells, {"both", "D"})

    def test_the_inputs_give_the_vectors_own_sums_and_counts(self):
        np = self.np
        for tag, vector in self.looks():
            with self.subTest(vector=tag):
                row = self.manifest["vectors"][tag]
                self.assertEqual(row["vector"].split()[0], tag)
                x, x15 = self.inputs[f"{tag}/x"], self.inputs[f"{tag}/x15"]
                self.assertEqual(len(x), 444)
                series = vector["series"]
                self.assertEqual(math.fsum(x[:250].tolist()), series["sum_V_x"])
                self.assertEqual(math.fsum(x[250:].tolist()), series["sum_H_x"])
                self.assertEqual(math.fsum(x15[250:].tolist()), series["sum_H_x15"])
                for name, key in (("w", "sum_H_w"), ("s", "sum_H_s"), ("f", "sum_H_f"), ("B", "sum_H_B")):
                    self.assertEqual(math.fsum(self.inputs[f"{tag}/{name}"][250:].tolist()), series[key], name)
                exits, invested = self.inputs[f"{tag}/exits"], self.inputs[f"{tag}/invested"]
                self.assertEqual((int(exits[:250].sum()), int(invested[:250].sum())), (series["RT_V"], series["ID_V"]))
                self.assertEqual((int(exits[250:].sum()), int(invested[250:].sum())),
                                 (series["exits_H"], series["invested_H"]))
                # x = r - B and x15 = x - 0.5 s - f, session by session
                r, bench = self.inputs[f"{tag}/r"], self.inputs[f"{tag}/B"]
                self.assertTrue(np.array_equal(x, r - bench))
                self.assertTrue(np.array_equal(x15, x - 0.5 * self.inputs[f"{tag}/s"] - self.inputs[f"{tag}/f"]))
                # the holdings log
                lots = vector["lots"]
                rows = [[int(n), float(w), int(d), int(e), int(q)] for n, w, d, e, q in zip(
                    self.inputs[f"{tag}/lot_name"], self.inputs[f"{tag}/lot_weight"], self.inputs[f"{tag}/lot_d"],
                    self.inputs[f"{tag}/lot_e"], self.inputs[f"{tag}/lot_q"])]
                self.assertEqual(rows, lots["rows_name_weight_d_e_q"])
                self.assertEqual(self.inputs[f"{tag}/lot_cell"].tolist(), lots["cell"])
                start = self.inputs[f"{tag}/member_start"]
                self.assertEqual(np.diff(start).tolist(), lots["members_count"])
                members = self.inputs[f"{tag}/member"]
                self.assertEqual((int(start[-1]), int(members.sum())), (len(members), lots["members_sum"]))
                self.assertEqual(members[:start[1]].tolist(), lots["first_lot_members"])
                self.assertEqual(self.inputs[f"{tag}/member_leave"].shape, members.shape)
                placebos = vector["placebos"]
                self.assertEqual(self.inputs[f"{tag}/pos_draw_0"].tolist(), placebos["counterpart_position_draw_0"])
                self.assertEqual(self.inputs[f"{tag}/pos_draw_998"].tolist(),
                                 placebos["counterpart_position_draw_998"])
                # the prices, the eligible set and the pools (a vector may read another's world: the manifest says)
                world = row["world"]
                for name in ("O", "C", "U", "entry_ok"):
                    self.assertEqual(self.inputs[f"{world}/{name}"].shape, (444, 24), name)
                pools = vector["inputs"]["train_pools"]
                for label, length in (("pool_d", pools["n_2016_19"]), ("pool_c", pools["n_2022_24"])):
                    if length is None:
                        self.assertNotIn(f"{tag}/{label}_x", self.inputs.files)
                    else:
                        self.assertEqual((len(self.inputs[f"{tag}/{label}_x"]), len(self.inputs[f"{tag}/{label}_w"])),
                                         (length, length))

    def test_the_placebo_ts_give_each_looks_count(self):
        """The 999 placebo t's on the holdout are the reference's: counted against the vector's own t they give its
        placebo count (an undefined t counts as not above), so 119 passes and 120 fails is read on the study's draws."""
        np = self.np
        spent = 0
        for tag, vector in self.looks():
            look = vector["look"]
            ts = self.inputs[f"{tag}/placebo_t_H"]
            self.assertEqual(ts.shape, (999,))
            if not look.get("look_spent"):
                continue
            spent += 1
            with self.subTest(vector=tag):
                with np.errstate(invalid="ignore"):
                    self.assertEqual(int(np.sum(ts >= look["t_H"])), look["placebo_count"])
                self.assertEqual(look["p_plac_thousandths"], 1 + look["placebo_count"])
        self.assertEqual(spent, 4)


if __name__ == "__main__":
    unittest.main()
