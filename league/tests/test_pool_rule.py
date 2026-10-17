"""POOL1's rule (league/ops/pool_rule.py, the owner's A55 as pre-registered in A55a; the receipt contract
POOL1-RECEIPT-1): the pin, the vendored calibration code and its shas, the receipt's contract shape and every refusal
of it, the conformance vectors CV1-CV12 through P1's own routes, the floor adapter against the calibration's own
`cluster_floor`, the caps and the bar against the calibration's, the forward statistic, the void, the placebo leg, the
demotion, the route and the words.

Every input is invented: the vendored p1conform's generated House export (league/tests/pool_world.py), synthetic numpy
streams, and the calibration's dry-run receipt (an invented market). No market data, no real figure, no POOL1 figure."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.ops import fwd1_rule as F
from league.ops import pool_rule as P
from league.tests import pool_world as W

REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "league" / "swarm" / "policy.json"
CONTRACT_CONSTANTS = {
    "plan": [40, 60, 120], "window": 120, "m_min": 3, "prior": 20, "sigma_floor": 0.0005, "weight_cap": 3.0,
    "group_share": "2/3", "copy_rho": 0.7, "min_exposure": 0.01, "cap": 0.12, "wall": 0.15, "worst": 0.15,
    "n1_offsets": [262, 409, 535, 661, 787], "floor_haircut": 0.0002, "k_stress": 1.5, "k_max": 500,
    "boot_resamples": 2000, "boot_block_mean": 120, "seed_root": 20261026, "bound": "max(q975, point + q975 - mean)",
    "stage1": {"z": -1.0, "lag": 5}, "rho_assign_q": 0.25, "u_counts": [0, 5, 10, 15, 20, 30, 40, 60],
    "u_pin_count": 5, "placebo": {"draws": 999, "count_max": 149}}


def pin_block(sha: str = "a" * 64) -> dict:
    """A pin block carrying every constant as this code holds it."""
    return {"name": P.NAME, "prereg_sha256": P.PREREG_SHA256, "receipt_sha256": sha, **copy.deepcopy(P.CONSTANTS),
            "p1": copy.deepcopy(P.P1_RULE)}


def refusal(doc: dict, B: int = W.B_TEST) -> str | None:
    return P.read_receipt(W.strict(doc), expect_constants=W.constants(B))[1]


# ------------------------------------------------------------------------------------------------------- the pin
class ThePin(unittest.TestCase):
    def test_the_exact_block_loads(self):
        held, why = P.load(pin_block())
        self.assertIsNone(why)
        self.assertEqual(held.receipt_sha256, "a" * 64)

    def test_every_refusal(self):
        self.assertIsNone(P.load({})[0])
        self.assertIsNone(P.load(None)[0])
        for key in P.PIN_KEYS:
            block = pin_block()
            del block[key]
            self.assertIn(key, P.load(block)[1], key)
        self.assertIn("does not read", P.load({**pin_block(), "extra": 1})[1])
        self.assertIsNone(P.load({**pin_block(), "name": "POOL2"})[0])
        self.assertIsNone(P.load({**pin_block(), "prereg_sha256": "b" * 64})[0])
        self.assertIsNone(P.load(pin_block("A" * 64))[0])
        self.assertIsNone(P.load(pin_block("a" * 63))[0])

    def test_no_constant_can_move(self):
        for key, value in P.CONSTANTS.items():
            block = pin_block()
            block[key] = [value] if not isinstance(value, list) else value[:-1]
            with self.subTest(key=key):
                self.assertIsNone(P.load(block)[0])
        for key in P.P1_RULE:
            block = pin_block()
            block["p1"] = {**block["p1"], key: "x"}
            with self.subTest(p1=key):
                self.assertIsNone(P.load(block)[0])

    def test_the_constants_are_the_contracts(self):
        self.assertEqual(P.CONSTANTS, CONTRACT_CONSTANTS)
        self.assertEqual(P.U_COUNTS, tuple(W.calib().cluster.U_COUNTS))
        self.assertEqual(P.CONTRACT, W.calib().cluster.CONTRACT)
        self.assertEqual(P.CONFORMANCE, W.calib().conform.VERSION)
        self.assertEqual(P.EVENT_WORD.pattern, W.calib().cluster.EVENT_WORD.pattern)
        self.assertEqual(P.EVENT_WORD.pattern, W.calib().house_job.EVENT_WORD.pattern)

    def test_policy_ships_record_with_seats_off_and_no_pin_until_the_receipt(self):
        doc = json.loads(POLICY.read_text())
        self.assertEqual(doc["elane"]["pool"]["mode"], "record")
        self.assertEqual(doc["elane"]["pool"]["seats"], "off")
        self.assertNotIn(P.PIN_BLOCK, doc["elane"])               # P12 adds it with the receipt (P1 D1)
        self.assertFalse((REPO / P.RECEIPT_PATH).exists())
        self.assertEqual(P.rule(doc)[0], None)


class TestReceiptPin(unittest.TestCase):
    """THE RECEIPT PIN (the contract's 7; the fwd1_rule practice): once policy.json pins a receipt, sha256 of
    docs/benchmarks/pool_screen_1.json is the pin's, it parses, every conformance vector holds on this interpreter, and
    every vendored file's sha is `CALIB_SHA256`'s and the receipt's. Skipped while no receipt is pinned (P12 adds it)."""

    def test_the_pinned_receipt(self):
        block = P.pin(json.loads(POLICY.read_text()))
        if not block:
            self.skipTest("no POOL1 receipt is pinned yet (P12)")
        held, why = P.load(block)
        self.assertIsNone(why)
        raw = (REPO / P.RECEIPT_PATH).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), held.receipt_sha256)
        rec, why = P.load_receipt(REPO / P.RECEIPT_PATH, held)          # parse, vendored shas, every vector
        self.assertIsNone(why)
        for name in P.CALIB_FILES:
            self.assertEqual(rec.calibration["vendored"][name], P.CALIB_SHA256[name])
            self.assertEqual(P.file_sha256(P.CALIB_DIR / name), P.CALIB_SHA256[name])


# --------------------------------------------------------------------------------------- the vendored calibration
class TheVendoredCode(unittest.TestCase):
    def test_every_file_is_byte_for_byte_its_pinned_sha_and_the_fixtures(self):
        names = sorted(p.name for p in P.CALIB_DIR.iterdir() if p.is_file())
        self.assertEqual(names, sorted(P.CALIB_FILES))           # no __init__.py, nothing else
        raw, rec = W.dryrun()
        for name in P.CALIB_FILES:
            with self.subTest(name=name):
                self.assertEqual(P.file_sha256(P.CALIB_DIR / name), P.CALIB_SHA256[name])
                self.assertEqual(rec.calibration["vendored"][name], P.CALIB_SHA256[name])
        for name in ("p1const.py", "p1stat.py", "p1members.py", "p1units.py", "p1engine.py"):
            self.assertIn(P.CALIB_SHA256[name], {             # the PREP files at CODE PIN 1
                "e2bd332870afece7fd2e420c15f1f71b4d944cfff1e6d4835273b9097f54f549",
                "2dc117dfec825609b531a6075c067320d4a9cc78a104c6f5e88cf2c54fbfa986",
                "c6e61f896d5c3fcc88f0500316c9d6837e4e9eb237dc2ad09dd6a7e9839bbe9a",
                "3ca473f68017366c559d3c2d09a7dd35d3793f523133f0e7dccb47ff9309066e",
                "d9fdf13eff203557f65c44eaff30ee029e2e5b7f68e1c80ae0b270d1cc60e920"})
        self.assertEqual(P.CALIB_SHA256["pool1_house_job.py"],
                         "9f6ab090b3e06226ccedd28ec99b3317c81138bd656d425e156c216045ccadc9")

    def test_it_loads_once_and_refuses_any_difference(self):
        cal, why = P.calib()
        self.assertIsNone(why)
        self.assertIs(P.calib()[0], cal)
        self.assertIs(cal.K.FAKE, False)
        self.assertEqual(cal.K.B_BOOT, 2000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "c"
            shutil.copytree(P.CALIB_DIR, root)
            (root / "p1cluster.py").write_bytes((root / "p1cluster.py").read_bytes() + b"\n")
            self.assertIn("not the pinned file", P.calib(root=root)[1])
            gone = Path(tmp) / "g"
            shutil.copytree(P.CALIB_DIR, gone)
            (gone / "p1cluster.py").unlink()
            self.assertIn("missing", P.calib(root=gone)[1])
            self.assertIn("not pinned yet", P.calib(shas={**P.CALIB_SHA256, "p1conform.py": None})[1])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fake"
            shutil.copytree(P.CALIB_DIR, root)
            with mock.patch.dict(os.environ, {"POOL1_DATA": "/nowhere"}):
                self.assertIn("does not load", P.calib(root=root)[1])      # a dry run's p1const refuses itself

    def test_the_shared_modules_are_pure(self):
        allowed = {"numpy", "datetime", "re", "math", "hashlib", "json", "dataclasses", "typing", "__future__", "os",
                   "pathlib", "p1const", "p1stat", "p1members", "p1units", "p1engine", "p1cluster"}
        for name in ("p1cluster.py", "p1conform.py", "p1stat.py", "p1members.py", "p1units.py", "p1engine.py"):
            tree = ast.parse((P.CALIB_DIR / name).read_text())
            mods = {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
                a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            with self.subTest(name=name):
                self.assertLessEqual(mods, allowed)
                calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
                self.assertNotIn("open", calls)

    def test_loading_touches_no_search_path(self):
        before = list(__import__("sys").path)
        P.calib()
        self.assertEqual(before, list(__import__("sys").path))


# -------------------------------------------------------------------------------------------------- the receipt
class TheReceipt(unittest.TestCase):
    def test_the_calibrations_dry_run_receipt_parses_under_its_own_constants_only(self):
        raw, rec = W.dryrun()
        self.assertEqual(rec.rule.floor_def, "POOLED")
        self.assertEqual(rec.B, 40)
        self.assertEqual(W.strict(json.loads(raw)), raw)              # the strict writer's bytes
        why = P.read_receipt(raw)[1]                                  # the code's own constants: B 2000, a CODE PIN
        self.assertIsNotNone(why)
        doc = json.loads(raw)
        doc["constants"]["boot_resamples"] = 2000
        self.assertIn("CODE PIN", P.read_receipt(W.strict(doc))[1])

    def test_a_pinned_receipts_code_is_code_pin_3s_every_file(self):
        """The conformance review's finding 6: a receipt whose code is not exactly CODE PIN 3's (a file reverted to an
        earlier pin's sha, which the calibration's preconditions accept, or another pin's label) is refused."""
        raw, rec = W.dryrun()
        self.assertEqual({k: rec.calibration["code_sha256"].get(k) for k in P.CODE_PIN_SHA256}, P.CODE_PIN_SHA256)
        doc = json.loads(raw)
        doc["calibration"]["code_pin"], doc["calibration"]["code_pin_utc"] = P.CODE_PIN, "2026-10-16T22:23:50Z"
        cal = doc["calibration"]
        self.assertIsNone(P._check_calibration(doc))                  # the dry run's code is CODE PIN 3's
        cal["code_sha256"] = {**cal["code_sha256"],
                              "p1house.py": "ddb4dd5b267cca5049beafda6bb18fd4e25986e42c2901428a719e4765e3ae29"}
        with self.assertRaises(P.ReceiptRefused) as caught:
            P._check_calibration(doc)
        self.assertIn("p1house.py", str(caught.exception))
        del cal["code_sha256"]["p1house.py"]
        with self.assertRaises(P.ReceiptRefused):
            P._check_calibration(doc)
        cal["code_sha256"] = dict(rec.calibration["code_sha256"])
        cal["code_pin"] = "CODE PIN 1"
        with self.assertRaises(P.ReceiptRefused) as caught:
            P._check_calibration(doc)
        self.assertIn(P.CODE_PIN, str(caught.exception))
        self.assertIsNone(P._check_calibration(doc, test=True))      # a test's own constants: unpinned code allowed

    def test_the_test_world_receipt_parses(self):
        rec = W.receipt()
        self.assertEqual(set(rec.units), {W.TM_I, W.TM_S, W.RL_I})
        self.assertEqual(set(rec.clusters), {"trend_momentum", "reversal_liquidity"})
        self.assertEqual(rec.founders["equity:rl_copy"].status, "merged")
        self.assertEqual(rec.founders["equity:rl_copy"].merged_into, "equity:rl_i1")
        self.assertEqual(rec.founders["equity:tm_s3"].ticket, "FWD1")      # a sector founder with no FWD1 row (C3)
        self.assertEqual(rec.founders["equity:eq1"].status, "out")
        self.assertEqual(rec.u_at("trend_momentum", 0), (0.0, 0.0))
        self.assertEqual(rec.u_at("trend_momentum", 3), (0.0, 0.0))
        self.assertIsNone(rec.u_at("trend_momentum", 61))                 # above the table: report-only
        self.assertEqual(rec.matched("sectors", "trend_momentum", 3), 150)
        self.assertIsNone(rec.matched("sectors", "trend_momentum", 61))   # no bar: the look waits
        self.assertEqual(rec.cuts().shape, (4, 2))

    def test_refused_whole_on_any_defect(self):
        def mutate(fn):
            doc = W.doc()
            fn(doc)
            return refusal(doc)

        tm = "trend_momentum"
        cases = {
            "unknown top-level key": lambda d: d.__setitem__("extra", 1),
            "missing key": lambda d: d.pop("market"),
            "nothing pinned": lambda d: d.__setitem__("status", "NOTHING PINNED"),
            "another contract": lambda d: d.__setitem__("contract", "POOL1-RECEIPT-0"),
            "another prereg": lambda d: d.__setitem__("prereg_sha256", "f" * 64),
            "a second run with no amendment": lambda d: d["run"].__setitem__("index", 2),
            "a margin off the menu": lambda d: d["rule"].update(margin_k=4, margin=0.04),
            "a c_G off the range": lambda d: d["rule"].update(c_G_k=139, c_G=1.39),
            "a constant moved": lambda d: d["constants"].__setitem__("cap", 0.13),
            "descending cuts": lambda d: d["regimes"].__setitem__("vol", [0.02, 0.01]),
            "a correlation above one": lambda d: d.__setitem__("rho_assign", 1.5),
            "a founder's unknown key": lambda d: d["founders"]["equity:tm_i1"].__setitem__("k_used", 170),
            "an out founder with a ticket": lambda d: d["founders"]["equity:eq1"].__setitem__("ticket", "S2"),
            "merged into a non-member": lambda d: d["founders"]["equity:rl_copy"].__setitem__("merged_into",
                                                                                           "equity:eq1"),
            "a member with no why rule": lambda d: d["founders"]["equity:tm_i1"].__setitem__("why", "x"),
            "a unit's flags not its cluster's": lambda d: d["units"][W.TM_S].__setitem__("refuted", True),
            "a unit missing a member": lambda d: d["units"][W.TM_S]["members"].pop(),
            "U bound below its point": lambda d: d["clusters"][tm]["U"].__setitem__("10", [0.05, 0.04]),
            "U missing a count": lambda d: d["clusters"][tm]["U"].pop("0"),
            "caps not the caps rule's": lambda d: d["clusters"][tm]["caps_at_pin"].__setitem__("cap", 0.1),
            "c_own not the largest null": lambda d: d["clusters"][tm]["c_own_at_pin"]["R-REG"].__setitem__("c_own", 1),
            "k_used not the bar": lambda d: d["clusters"][tm]["c_own_at_pin"]["R-REG"].__setitem__("k_used", 171),
            "a cluster's unknown key": lambda d: d["clusters"][tm].__setitem__("z", [0.1]),
            "a matched row missing m 60": lambda d: d["matched_floor"]["sectors"]["trend_momentum"]["R-REG"].pop("60"),
            "a vector missing": lambda d: d["conformance"]["vectors"].pop("CV12"),
            "a vendored file unnamed": lambda d: d["calibration"]["vendored"].pop("p1cluster.py"),
            "a market era missing its sha": lambda d: d["market"]["e0"].pop("sha256"),
            "a beside figure not a share": lambda d: d["clusters"][tm]["beside"].__setitem__("fp_point", 2.0),
            "expected passes falling": lambda d: d["clusters"][tm]["expected"].__setitem__("passes", [0.3, 0.2, 0.1]),
        }
        self.assertIsNone(refusal(W.doc()))
        for name, fn in cases.items():
            with self.subTest(name=name):
                self.assertIsNotNone(mutate(fn))
        raw = W.receipt_bytes().replace(b'"rho_assign": ', b'"rho_assign": NaN, "x": ', 1)
        self.assertIn("NaN", P.read_receipt(raw, expect_constants=W.constants())[1])
        self.assertIn("not JSON", P.read_receipt(b"{", expect_constants=W.constants())[1])

    def test_a_null_beside_figure_is_allowed(self):
        doc = W.doc()
        doc["clusters"]["trend_momentum"]["beside"] = {k: None for k in P.BESIDE_KEYS}
        self.assertIsNone(refusal(doc))

    def test_read_only_at_the_pins_sha_with_the_vendored_code_and_its_vectors(self):
        raw = W.receipt_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_bytes(raw)
            kw = {"expect_constants": W.constants()}
            self.assertIn("not the pin's", P.load_receipt(path, P.Pin("0" * 64), **kw)[1])
            rec, why = P.load_receipt(path, P.Pin(sha), **kw)
            self.assertIsNone(why)
            self.assertEqual(rec.sha256, sha)
            doc = json.loads(raw)
            doc["calibration"]["vendored"]["p1stat.py"] = "0" * 64
            bad = W.strict(doc)
            path.write_bytes(bad)
            self.assertIn("vendored", P.load_receipt(path, P.Pin(hashlib.sha256(bad).hexdigest()), **kw)[1])
            doc = json.loads(raw)
            doc["conformance"]["vectors"]["CV12"]["outputs"]["k_used"][1] = 171
            bad = W.strict(doc)
            path.write_bytes(bad)
            self.assertIn("conformance", P.load_receipt(path, P.Pin(hashlib.sha256(bad).hexdigest()), **kw)[1])
            self.assertIn("no receipt", P.load_receipt(Path(tmp) / "none.json", P.Pin(sha))[1])


# ---------------------------------------------------------------------------------------------- the conformance
class TheConformance(unittest.TestCase):
    def test_every_vector_holds_through_p1s_routes(self):
        for raw, rec in (W.dryrun(), (W.receipt_bytes(), W.receipt())):
            ok, why, results = P.conform(rec, W.calib())
            self.assertTrue(ok, why)
            self.assertEqual(set(results), set(P.CV_IDS))
            self.assertTrue(all(v is None for v in results.values()))

    def test_a_tampered_output_or_input_fails_its_vector(self):
        raw, rec = W.dryrun()
        doc = json.loads(raw)
        doc["conformance"]["vectors"]["CV10"]["outputs"]["caps"][0]["cap"] += 1e-6
        doc["conformance"]["vectors"]["CV9"]["inputs"]["sha256"] = "0" * 64
        doc["conformance"]["vectors"]["CV1"]["outputs"]["a"][0][1] += 1e-6
        rec2, why = P.read_receipt(W.strict(doc), expect_constants=W.constants(40))
        self.assertIsNone(why)
        ok, why, results = P.conform(rec2, W.calib())
        self.assertFalse(ok)
        self.assertEqual({k for k, v in results.items() if v is not None}, {"CV1", "CV9", "CV10"})
        self.assertIn("sha256", results["CV9"])

    def test_p1s_own_routes_are_the_calibrations(self):
        C = W.calib().cluster
        rng = np.random.default_rng(5)
        for p, b in list(rng.random((200, 2)) * 0.2) + [(0.12, 0.0), (0.0, 0.15), (0.11999, 0.1499), (math.nan, 0.0),
                                                       (0.05, math.inf), (None, 0.1)]:
            for dropped in ((), [{"lineage": "x"}]):
                mine, theirs = P.caps(p, b, dropped), C.caps_rule(p, b, dropped)
                self.assertEqual((mine.cap, mine.wall, mine.u_worst, mine.report_only, mine.why),
                                 (theirs["cap"], theirs["wall"], theirs["u_worst"], theirs["report_only"], theirs["why"]))
        for c_own in (None, 0, 120, 160, 495, 498, 500):
            for minimum in (None, 0, 150, 300, 501):
                for c_G in (140, 170, 250):
                    for margin in P.MARGINS_K:
                        self.assertEqual(P.k_used(c_G, margin, c_own, minimum), C.k_used_for(c_own, minimum, c_G, margin))
        texts = ["x = ctx.events", "y = ctx.events_next", "# events", "eventsx = 1", "my_events = 2", "ctx['events']",
                 "def f(:", "getattr(ctx, 'events')", "a = 1", None, 'z = "the events"']
        for t in texts:
            if C.event_word(t):
                self.assertTrue(P.reads_events(t), t)
        self.assertTrue(P.reads_events("getattr(ctx, 'events')"))
        self.assertFalse(P.reads_events("my_events = 2\n"))
        S = W.calib().stat
        for _ in range(50):
            sig = list(np.abs(rng.normal(0.004, 0.003, int(rng.integers(1, 6)))))
            self.assertAlmostEqual(P.sigma_tilde(sig), S.sigma_tilde(sig), places=15)
            one = float(abs(rng.normal(0.003, 0.003)))
            self.assertEqual(P.sigma_used(one, S.sigma_tilde(sig)),
                             float(S.sigma_used(np.array([one]), S.sigma_tilde(sig))[0]))


# --------------------------------------------------------------------------------------------- the floor adapter
class TheFloorAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal = W.calib()
        C = cls.cal.cluster
        h = W.house()
        cls.cuts = np.array(h["cuts"])
        cls.hc = C.house_context(h["prices"], cls.cuts)
        members = []
        for m in W.metas():
            _, mm = P.house_member(cls.cal, m, W.records(m["pid"]), cls.hc)
            if mm is not None:
                members.append(mm)
        cls.members = members
        with P.quiet():
            cls.kept, cls.merged = C.merge_copies(list(members), cls.hc)
            cls.cc = C.cells_and_clusters(cls.kept, cls.hc)

    def test_house_floor_is_cluster_floor(self):
        C = self.cal.cluster
        for ci, (cid, keys) in enumerate(sorted(self.cc["clusters"].items())):
            for joins in (None, {self.cc["cells"][keys[-1]][0].name: 25}):
                caps_ = P.caps(0.03, 0.05)
                with P.quiet():
                    want = C.cluster_floor(cid, keys, self.cc["cells"], self.hc, self.cuts, 20, ci, caps_.cap,
                                           caps_.wall, joins=joins)
                got = P.house_floor(self.cal, cid=cid, keys=keys, judged=self.cc["cells"], hc=self.hc, B=20,
                                    boot_seed=ci, caps_=caps_, joins=joins)
                with self.subTest(cid=cid, joins=joins):
                    self.assertEqual(got["floor"], want["floor"])
                    self.assertEqual(got["span"], want["span"])
                    self.assertEqual(sorted(got["point"]), sorted(want["point"]))

    def test_resamples_spread_over_calls_equal_one_call(self):
        cid, keys = sorted(self.cc["clusters"].items())[0]
        caps_ = P.caps(0.0, 0.0)
        whole = P.house_floor(self.cal, cid=cid, keys=keys, judged=self.cc["cells"], hc=self.hc, B=20, boot_seed=0,
                              caps_=caps_)
        kept: dict = {}
        state = {"left": 3}

        class Later(Exception):
            pass

        def hook(null, e, key, compute):
            if (null, e, key) in kept:
                return kept[(null, e, key)]
            if state["left"] <= 0:
                raise Later
            state["left"] -= 1
            kept[(null, e, key)] = compute()
            return kept[(null, e, key)]

        nights = 0
        while True:
            nights += 1
            state["left"] = 3
            try:
                parts = P.house_floor(self.cal, cid=cid, keys=keys, judged=self.cc["cells"], hc=self.hc, B=20,
                                      boot_seed=0, caps_=caps_, boot=hook)
                break
            except Later:
                continue
        self.assertGreater(nights, 2)
        self.assertEqual(parts["floor"], whole["floor"])

    def test_the_pins_floors_are_reproduced(self):
        """THE CLOCK-START CONFORMANCE, pure (the contract's 6.4): the receipt's members on the export, joins 0, its
        boot seed, the pin's caps and its B give every value of `c_own_at_pin`; for the calibration's own dry-run
        receipt (its own invented House export, in the calibration's directory) and for the test world's."""
        rec = W.receipt()
        for cid, cl in rec.clusters.items():
            judged = {P.cell_key(c): [m for m in self.members if m.family in rec.units[c].members] for c in cl.cells}
            fl = P.house_floor(self.cal, cid=cid, keys=[P.cell_key(c) for c in cl.cells], judged=judged, hc=self.hc,
                               B=rec.B, boot_seed=cl.boot_seed, caps_=P.caps(*cl.U[5], cl.dropped))
            got = P.pin_floors(fl, rec, P.minimum_of(rec, {c: rec.units[c].m for c in cl.cells}))
            self.assertEqual(got, {fd: dict(cl.c_own_at_pin[fd]) for fd in P.FLOORS}, cid)
        moved = W.receipt(matched=200)
        cl = moved.clusters["reversal_liquidity"]
        self.assertEqual(cl.c_own_at_pin["R-REG"]["minimum"], 200)

    def test_the_merge_the_assignment_and_the_member_rule_are_the_calibrations(self):
        C = self.cal.cluster
        kept, merged = [], {}
        for mm in self.members:
            into = P.merge_copy(self.cal, mm, kept, self.hc)
            if into is None:
                kept.append(mm)
            else:
                merged[mm.name] = into
        self.assertEqual(merged, self.merged)
        self.assertEqual([m.name for m in kept], [m.name for m in self.kept])
        later = W.later_meta()
        _, mm = P.house_member(self.cal, later, W.records(later["pid"]), self.hc)
        z = P.train_z(self.cal, mm, self.hc)
        cand = {f"{k[0]}/{k[1]}": [P.train_z(self.cal, x, self.hc) for x in v] for k, v in self.cc["cells"].items()
                if k[1] == mm.group}
        got = P.assign(self.cal, z, cand, self.cc["rho_assign"])
        with P.quiet():
            want = C.assign_cell(z, {c: np.array(v) for c, v in cand.items()}, self.cc["rho_assign"])
        self.assertEqual(got[0], want[0])
        self.assertIsNone(P.assign(self.cal, z, cand, None)[0])
        clusters = {cid: list(keys) for cid, keys in self.cc["clusters"].items()}
        by_class: dict = {}
        for k in self.cc["cells"]:
            by_class.setdefault(k[0], []).append(k)
        joined, joins = P.cluster(self.cal, by_class, self.cc["cells"], self.hc)
        self.assertEqual({c: sorted(v) for c, v in joined.items()}, {c: sorted(v) for c, v in clusters.items()})

    def test_the_minimum_and_the_seed_of_a_join(self):
        rec = W.receipt(matched=170)
        self.assertEqual(P.minimum_of(rec, {W.TM_I: 3, W.TM_S: 4}), {"R-REG": 170, "POOLED": 170})
        self.assertEqual(P.minimum_of(rec, {W.TM_I: 3, W.TM_S: 61}), {"R-REG": None, "POOLED": None})
        self.assertEqual(P.joined_seed("a+b", "x:40"), int(hashlib.sha256(b"a+b|x:40").hexdigest()[:8], 16))
        self.assertEqual(P.joined_u([(0.03, 0.05), (0.04, 0.06)]), (0.07, 0.11))
        self.assertEqual(P.joined_u([(0.8, 0.9), (0.4, 0.5)]), (1.0, 1.0))
        rows = [{"type": "ETF", "case_": "N", "judged": 1, "k_read": 10}, {"status": "pass", "k_read": 20},
                {"type": "ETF", "case_": "N", "judged": 0, "k_read": 40}, None]
        self.assertEqual(P.u_count(rows), 20)


# --------------------------------------------------------------------------------------------------- the statistic
def loop_alpha(rg, gap, ws, R, mu, wbar, include=None, prior=20):
    """The PREREG's formula, one day at a time."""
    S, n = ws.shape
    inc = [True] * n if include is None else list(include)
    a, a15 = [], []
    for t in range(n):
        cnt = sum(1 for u in range(t) if inc[u])
        what = [(prior * wbar[s] + sum(ws[s, u] for u in range(t) if inc[u])) / (prior + cnt) for s in range(S)]
        v = rg[t] - sum(ws[s, t] * mu[s] for s in range(S)) - sum(what[s] * (R[s, t] - mu[s]) for s in range(S))
        a.append(v)
        a15.append(v - gap[t])
    return np.array(a), np.array(a15)


class TheStatistic(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng([7, 1016])
        self.S, self.n = 3, 60
        self.ws = np.abs(rng.normal(0.2, 0.1, (self.S, self.n))) * (rng.random((self.S, self.n)) < 0.5)
        self.R = rng.normal(0.0003, 0.01, (self.S, self.n))
        self.mu, self.wbar = self.R.mean(axis=1), self.ws.mean(axis=1)
        self.rg = (self.ws * self.R).sum(axis=0) - 1e-4 * rng.random(self.n)
        self.gap = 1e-5 * rng.random(self.n)

    def test_the_per_symbol_alpha_against_a_direct_loop_and_alpha_windows(self):
        include = np.arange(self.n) % 7 != 3
        a, a15 = P.alpha(self.rg, self.gap, self.ws, self.R, self.mu, self.wbar, include=include)
        la, la15 = loop_alpha(self.rg, self.gap, self.ws, self.R, self.mu, self.wbar, include=include)
        np.testing.assert_allclose(a, la, rtol=0, atol=1e-15)
        np.testing.assert_allclose(a15, la15, rtol=0, atol=1e-15)
        S = W.calib().stat
        base = self.rg - (self.ws * self.mu[:, None]).sum(0)
        A = S.alpha_windows(base, self.ws, self.R - self.mu[:, None], self.wbar, np.array([0, 5, 30]), 25)
        for i, J in enumerate((0, 5, 30)):
            mine = P.alpha(self.rg[J:], self.gap[J:], self.ws[:, J:], self.R[:, J:], self.mu, self.wbar)[0]
            np.testing.assert_allclose(mine[:25], A[i], rtol=0, atol=1e-15)

    def test_a_static_tilt_and_a_padded_needs_list_score_zero(self):
        tilt = np.tile(np.array([[0.4], [0.1], [0.0]]), (1, self.n))
        rg = (tilt * self.R).sum(axis=0)
        a, _ = P.alpha(rg, np.zeros(self.n), tilt, self.R, self.mu, tilt[:, 0])
        self.assertLess(float(np.abs(a).max()), 1e-15)
        a2, _ = P.alpha(rg, np.zeros(self.n), tilt[:2], self.R[:2], self.mu[:2], tilt[:2, 0])
        np.testing.assert_allclose(a, a2, atol=1e-16)

    def test_the_cell_day_the_look_and_t(self):
        z = np.array([[1.0, 0.0, 2.0], [3.0, 4.0, 0.0]])
        active = np.array([[True, True, True], [False, True, True]])
        np.testing.assert_allclose(P.cell_day(z, active), [1.0, 2.0, 1.0])
        x = list(np.random.default_rng(3).normal(0.1, 1.0, 120))
        self.assertEqual(P.t_stat(x), F.t_stat(x))
        point = P.look(x, x, 40)
        self.assertEqual(point["T"], F.t_stat(x[:40]))
        self.assertEqual([P.look_t(x, x, k) for k in P.PLAN], W.calib().stat.t_direct(x, x))
        self.assertTrue(P.legs_pass({"T": 1.71, "S15": 1e-9}, 1.70))
        self.assertFalse(P.legs_pass({"T": 1.71, "S15": 1e-13}, 1.70))
        self.assertFalse(P.legs_pass({"T": None, "S15": 1.0}, 1.70))
        with self.assertRaises(ValueError):
            P.look(x[:39], x[:39], 40)

    def test_the_series_sha_names_one_series(self):
        a = P.series_sha(["2026-10-26"], [0.1], [0.05])
        self.assertEqual(a, P.series_sha(["2026-10-26"], [0.1], [0.05]))
        self.assertNotEqual(a, P.series_sha(["2026-10-26"], [0.1 + 1e-16], [0.05]))


class TheCellKey(unittest.TestCase):
    def test_the_event_code_scan_is_the_union(self):
        self.assertTrue(P.reads_events("def decide(ctx):\n    return ctx.events['fomc']\n"))
        self.assertTrue(P.reads_events("def decide(ctx):\n    return getattr(ctx, 'events_next')\n"))
        self.assertTrue(P.reads_events("def decide(ctx:\n"))                 # does not parse: an event reader
        self.assertTrue(P.reads_events(None))
        self.assertTrue(P.reads_events("x = 1  # events in a comment\n"))   # the House job's word scan (D18)
        self.assertFalse(P.reads_events("def decide(ctx):\n    return ctx.bars['SPY']\n"))

    def test_what_is_out_at_the_first_reading(self):
        card = {"mechanism_class": "trend_momentum", "inputs": ["underlying_price"]}
        self.assertIsNone(P.excluded(panel=False, symbols=["SPY"], card=card, code="x = 1\n"))
        self.assertIn("panel", P.excluded(panel=True, symbols=["SPY"], card=card, code="x = 1\n"))
        self.assertIn("stocks", P.excluded(panel=False, symbols=["SPY", "AAPL"], card=card, code="x = 1\n"))
        self.assertIn("equity_premium", P.excluded(panel=False, symbols=["SPY"], code="x = 1\n",
                                                   card={"mechanism_class": "equity_premium"}))
        self.assertIn("event reader", P.excluded(panel=False, symbols=["SPY"], code="x = 1\n",
                                                 card={"mechanism_class": "x", "inputs": ["event_calendar"]}))
        self.assertIn("event reader", P.excluded(panel=False, symbols=["SPY"], card=card, code="y = ctx.events\n"))
        self.assertIn("no declared class", P.excluded(panel=False, symbols=["SPY"], card=None, code="x = 1\n"))

    def test_the_member_is_the_first_passing_pid(self):
        rows = [{"pid": 7, "reason": "train_fail"}, {"pid": 9, "reason": "train_pass"}, {"pid": 8, "reason": "seed"}]
        self.assertEqual(P.member_pid(rows), 8)
        self.assertIsNone(P.member_pid([{"pid": 3, "reason": "train_fail"}]))


# ------------------------------------------------------------------------------------------- void, placebo, words
class TheVoidAndPlacebo(unittest.TestCase):
    def test_the_zeroed_days_void(self):
        k = 40
        b = [0.001 * (i + 1) for i in range(k)]
        clustered = [(b[i], 3 if i >= 36 else 0, 5) for i in range(k)]
        self.assertTrue(P.mar_void(clustered)["void"])
        spread = [(b[i], 1 if i % 4 == 0 else 0, 5) for i in range(k)]
        self.assertFalse(P.mar_void(spread)["void"])
        one = [(b[i], 1 if i == 39 else 0, 5) for i in range(k)]
        out = P.mar_void(one)
        self.assertFalse(out["void"])
        self.assertAlmostEqual(out["p"], 0.1)
        self.assertAlmostEqual(P.binom_tail(2, 2, 0.1), 0.01)

    def test_the_placebo_leg(self):
        seed = P.placebo_seed("e" * 64, "trend_momentum/sectors", 40)
        self.assertEqual(seed, int.from_bytes(hashlib.sha256(f"{'e' * 64}|trend_momentum/sectors|40".encode()).digest()[:16],
                                              "big"))
        draws = P.placebo_draws(50, 4, seed)
        self.assertEqual(len(draws), 999)
        self.assertTrue(all(len(set(d)) == 4 and all(0 <= i < 50 for i in d) for d in draws))
        pseudo = list(np.random.default_rng(2).normal(0, 1, 999)) + [None]
        self.assertEqual(P.placebo_count(1.5, pseudo), sum(1 for v in pseudo if v is not None and v >= 1.5))
        self.assertTrue(P.placebo_holds(149, 999))
        self.assertFalse(P.placebo_holds(150, 999))
        with self.assertRaises(ValueError):
            P.placebo_draws(3, 4, seed)
        self.assertEqual(P.control_wbar({"symbols": ["XLK", "XLE"], "f": 0.5}), {"XLK": 0.25, "XLE": 0.25})


class TheDemotionRouteAndWords(unittest.TestCase):
    def test_the_demotion(self):
        rng = np.random.default_rng(9)
        good = list(rng.normal(0.3, 1, 20))
        bad = list(rng.normal(-1.0, 1, 20))
        every = list(rng.normal(0.3, 1, 60)) + good
        self.assertIsNone(P.demote(good, good, every))
        self.assertIn("post-pass T", P.demote(bad, bad, every))
        self.assertIsNone(P.demote(good[:19], good[:19], every))
        self.assertIn("all cell sessions", P.demote(good, good, [-abs(v) for v in every]))

    def test_the_pool_route(self):
        row = {"type": "ETF", "case_": "N", "judged": 1, "status": "fail"}
        self.assertTrue(P.on_pool_route(row, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "status": "pass"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "status": "void"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "judged": 0}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route(row, unit_judged=True, refuted=True, report_only=False))
        self.assertFalse(P.on_pool_route(row, unit_judged=True, refuted=False, report_only=True))
        self.assertFalse(P.on_pool_route(None, unit_judged=True, refuted=False, report_only=False))

    def test_the_words_carry_no_figure(self):
        self.assertEqual(P.words("trend_momentum/sectors", "PASS"), "POOL1 unit trend_momentum/sectors: PASS")
        self.assertEqual(P.words("x/index", P.NONCONFORMING), "POOL1 unit x/index: nonconforming")
        with self.assertRaises(ValueError):
            P.words("x/index", "not passed at 40")
        self.assertEqual(P.figure_free({"version": 1, "a": "b", "c": [None, True, "2026-10-26"]}), [])
        self.assertEqual(P.figure_free({"t": 1.7}), ["t"])
        self.assertEqual(P.figure_free({"w": "12% at zero edge"}), ["w"])

    def test_ids_are_not_figures_and_free_text_is_mended(self):
        """The conformance review's finding 1: a lineage slug with "bp" in it is an id (a key or an id field); a number
        at an id field still is a figure; the free text is mended to a fixed word, never refusing the document."""
        doc = {"version": 1, "routes": {"equity:gap-50-bp-fade": {"cell": "a/b", "cluster": "a"}},
               "holds": ["equity:spy-10-bp-fade", "equity:x-1.5-pct"], "units": {"a/b": {"cluster": "a", "word": "PASS"}},
               "eligible": [{"lineage": "equity:gap-50-bp-fade", "version": 3, "run_sha": "ab12"}], "why": "no_receipt"}
        ids, keys = ("cell", "cluster", "lineage", "run_sha", "holds"), ("routes", "units")
        self.assertEqual(sorted(P.figure_free(doc)), ["eligible[0].lineage", "holds[0]", "holds[1]",
                                                      "routes.equity:gap-50-bp-fade"])
        self.assertEqual(P.figure_free(doc, ids=ids, id_keys=keys), [])
        self.assertEqual(P.figure_free({"cell": 1.5}, ids=ids), ["cell"])                  # a number is a figure
        self.assertEqual(P.figure_free({"units": {"a": {"word": "t 1.83"}}}, ids=ids, id_keys=keys),
                         ["units.a.word"])
        bad = {**doc, "why": "the cap is 0.12", "units": {"a/b": {"cluster": "a", "word": "passed at 1.83"}},
               "t": 1.7, "n": 4}
        mended, places, stuck = P.scrub_figures(bad, word="withheld", ids=ids, id_keys=keys)
        self.assertEqual(sorted(places), ["n", "t", "units.a/b.word", "why"])
        self.assertEqual(stuck, [])
        self.assertEqual((mended["why"], mended["t"], mended["units"]["a/b"]["word"]), ("withheld",) * 3)
        self.assertEqual(mended["routes"], doc["routes"])
        self.assertEqual(P.figure_free(mended, ids=ids, id_keys=keys), [])
        self.assertEqual(bad["why"], "the cap is 0.12")                                  # a copy: the input is kept
        _, _, stuck = P.scrub_figures({"weird": {"0.5": "x"}}, word="withheld", ids=ids, id_keys=keys)
        self.assertEqual(stuck, ["weird.0.5"])                       # a key it cannot mend: the caller fails closed

    def test_the_floor_wide_expected_passes_count_a_cluster_once(self):
        rec = W.receipt()
        # the P1 review's F12: a 2-cell cluster's two cells read at 40 are one entry (its curve covers both cells)
        two_cells = [("trend_momentum", 40), ("trend_momentum", 40), ("reversal_liquidity", 120)]
        self.assertEqual(P.expected_passes(two_cells, rec), round(0.02 + 0.05, 4))
        self.assertEqual(P.expected_passes([("trend_momentum", 40), ("trend_momentum", 60)], rec), 0.03)
        self.assertEqual(P.expected_passes([("unknown", 40)], rec), 0.0)
        text = P.beside(rec, cell=W.TM_S, cluster="trend_momentum", k=40, T=1.9, c_used_value=1.83, own_t=0.5,
                        passes=1, judged=5, expected=0.2, u_point=0.04, u_bound=0.06)
        for needle in ("WEAK", "no bound", "N1", "1 passes of 5 units", "contamination", "close-rate key",
                       "worst Train-era regime cell n/a%"):
            self.assertIn(needle.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
