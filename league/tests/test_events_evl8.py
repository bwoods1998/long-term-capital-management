"""PREREG-EVL-8 (release 1019j): the price lane (league/events/px.py), the meta-learners (league/events/meta.py) and this
file's judge (league/events/screen8.py), on invented data only (league/tests/evl8_world.py: no figure here is a
market's). Each class holds one clause of the text (goal-2026-10-19/evl8/PREREG-EVL-8.md, the draft as the captain's
F1-F13 change it) and fails without it: the rows and their pin, ONE CLOCK, PXU and corporate actions, NO STORED ITEM,
the seats' rules, rankings, K 40 and A72, the 200 hash-sampled controls, the pinned grid and its evaluator, the
bar-basis panel and px_basis, the placebos and the canary, the judge (PREREG-EVL-6 with F4's cap), the runs and their
charges, MRL-EB and its state, the one cutoff, F8's secrecy, F9's member outcome, the money row, the House's timing.
The proof of an unchanged lane (every earlier program's intents and real-money picks identical with and without this
file) and the look-ahead and noise tests are league/tests/test_events_evl8_proof.py."""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import itertools
import json
import math
import random
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league import ci, constitution as K
from league.events import bands as BA
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import meta as MT
from league.events import programs as P
from league.events import px as PXL
from league.events import pxstore as PXS
from league.events import report as RP
from league.events import score as SC
from league.events import screen as SN
from league.events import screen8 as S8
from league.events import store as S
from league.tests import equity_design as X
from league.tests import evl8_world as W

UTC = dt.timezone.utc
et = W.et
D_DAY, N_DAY, P_DAY = W.D_DAY, W.N_DAY, W.P_DAY


class Pinned(unittest.TestCase):
    """REGISTERED_AT_8 pinned (before the week) for every test of the class."""

    def setUp(self):
        ctx = W.pinned()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)


class WorldCase(Pinned):
    """A pinned world with the PX store seeded and the morning of D made."""

    def setUp(self):
        super().setUp()
        self.w = W.World8(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.w.births()
        self.w.st.set_meta("equity:2026-10-26", "1900")
        self.w.st.set_meta("equity:2026-10-27", "1900")

    def px(self):
        px = self.w.px()
        self.addCleanup(px.close)
        return px

    def morning(self, day=D_DAY):
        return self.w.at(et(day, 9, 5)).morning(day)

    def intents(self, program: str, day=D_DAY) -> dict[str, dict]:
        return {str(r["cik"]): dict(r) for r in self.w.st.db.execute(
            "SELECT * FROM intents WHERE program=? AND entry_day=?", (program, day.isoformat()))}


# ================================================================================================ the rows and the pin
class TheFreeze(unittest.TestCase):
    def test_the_constant_is_a122s_and_names_the_frozen_file(self):
        """THE FREEZE (A122): REGISTERED_AT_8 is the latest of the commit's 18:43:17Z, GitHub's 18:43:20Z and the
        client's 18:43:24Z after the tag push returned; the tag's file is in the tree byte for byte
        (docs/prereg/PREREG-EVL-8.md, sha256 37150fac, `FROZEN_SHA256_8`) with its calibration record (every file its
        SHA256SUMS lists: A122's 160 files with SHA256SUMS itself), the pinned grid among them equal to the code's
        (league/events/px_grid8.json, canonical sha256 bb0d50e4); PREREG-EVL-6's time is earlier."""
        import hashlib

        self.assertEqual(P.REGISTERED_AT_8, "2026-10-22T18:43:24Z")
        self.assertTrue(P.registers_8())
        self.assertLess(S.parse_iso(P.REGISTERED_AT_6_FOR_8), S.parse_iso(P.REGISTERED_AT_8))
        root = Path(__file__).resolve().parents[2] / "docs" / "prereg"
        text = (root / "PREREG-EVL-8.md").read_bytes()
        self.assertEqual(hashlib.sha256(text).hexdigest(), P.FROZEN_SHA256_8)
        self.assertEqual(P.FROZEN_SHA256_8, "37150facab4ca727ef06ae5522689b81096c156872184f7ebe1e28be09f43ed0")
        self.assertIn(b"REGISTRATION TIME: the latest of three times", text, "the text names the pin's method")
        sums = (root / "evl-8" / "SHA256SUMS").read_text().split("\n")
        listed = {name.strip().lstrip("*"): digest for digest, name in
                  (line.split(None, 1) for line in sums if line.strip())}
        for name, digest in listed.items():
            self.assertEqual(hashlib.sha256((root / "evl-8" / name).read_bytes()).hexdigest(), digest, name)
        files = {f.name for f in (root / "evl-8").iterdir() if f.is_file()}
        self.assertEqual(files, set(listed) | {"SHA256SUMS"}, "every file listed, no other")
        self.assertEqual(len(files), 160, "A122: 160 files (159 listed and SHA256SUMS)")
        self.assertEqual((root / "evl-8" / "px_grid8.json").read_bytes(), PXL.GRID_FILE.read_bytes())
        self.assertEqual(PXL.grid_sha(PXL.grid()), PXL.GRID_SHA256)
        self.assertEqual(PXL.GRID_SHA256, "bb0d50e47d94e73f677a22bb612ef3f1cf7d23b23e5a51375fe965cf57e3e5a1")

    def test_pinned_the_five_seats_follow_prereg_evl_7_and_precede_the_births(self):
        """Section 4.2 and A101: in the registries as pinned, this file's five seats come after every earlier file's
        row (PREREG-EVL-7's learners included, whatever the order of the freezes: A122 froze before A125) and before
        R3's births; a refresh of the learners' registries keeps them (`refresh_7` composed with `refresh_8`)."""
        mine = [p.id for p in P.SEATING if P.is_8(p)]
        self.assertEqual(mine, ["PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1", "EVL-META-O1", "EVL-META-ON"])
        seating = list(P.SEATING)
        last_earlier = max(i for i, p in enumerate(seating) if not P.is_8(p) and p.spec is None)
        first_birth = min((i for i, p in enumerate(seating) if p.spec is not None), default=len(seating))
        first_mine = min(i for i, p in enumerate(seating) if P.is_8(p))
        self.assertLess(last_earlier, first_mine)
        self.assertLess(max(i for i, p in enumerate(seating) if P.is_8(p)), first_birth)
        self.assertTrue(any(P.is_learner(p) for p in seating[:first_mine]))
        P.refresh_7()
        self.assertEqual([p.id for p in P.SEATING if P.is_8(p)], mine, "a learners' refresh keeps this file's rows")


class TheRowsUnpinned(unittest.TestCase):
    """With REGISTERED_AT_8 None nothing of this file decides, trades or is charged: no row, no seat, no task."""

    def setUp(self):
        ctx = W.pinned(None)
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)

    def test_none_ships_and_no_registry_holds_a_row(self):
        self.assertIsNone(P.REGISTERED_AT_8, "None refuses every decision of this file")
        self.assertFalse(P.registers_8())
        self.assertEqual(P.rows_8(), ())
        for table in (P.PROGRAMS, P.PREREG_PROGRAMS, P.SEATING, P.PREREG_SEATING):
            self.assertFalse(any(P.is_8(p) for p in table))
        self.assertFalse(any(P.is_8(p) for p in EB.seatable()))
        self.assertIsNone(EB.program_of("PX-DROP-ON", 1))
        self.assertEqual(S8.seating8(), [])
        with self.assertRaises(RuntimeError):
            P.ROWS_8[0].registered_at

    def test_nothing_decides_or_is_charged_while_unpinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = W.World8(Path(tmp) / "lane", eight=False)
            try:
                px = w.px()
                try:
                    w.at(et(D_DAY, 15, 46, 5))
                    self.assertIn("not pinned", PXL.decide(px, w.st, w.gw, D_DAY, "on", now=lambda: w.now)["skipped"])
                    self.assertIn("not pinned", PXL.morning(px, w.st, w.gw, D_DAY, now=w.now, run="r")["skipped"])
                    self.assertEqual(PXL.redecide(px, w.st, D_DAY, "on", now=w.now), {})
                finally:
                    px.close()
                self.assertIn("not pinned", MT.decide(w.st, D_DAY, "on", now=lambda: w.now)["skipped"])
                self.assertEqual(S8.run(w.st, D_DAY, now=w.now), {"written": [], "waiting": [], "errors": [], "started": []})
                self.assertEqual(S8.charges(w.st), {})
                self.assertEqual(EB.eligible_8(EB.Lane(w.st.root / S.DB_NAME), D_DAY), set())
                self.assertEqual(RP.build(w.st, D_DAY)["eight"], None)
                self.assertIsNone(PXL.mark_release(w.st, w.now))
                self.assertFalse(w.st.db.execute("SELECT 1 FROM intents WHERE program LIKE 'PX%' OR program LIKE "
                                                 "'EVL-META%' OR program LIKE 'CTRL-PX%'").fetchone())
            finally:
                w.close()

    def test_registers_only_after_prereg_evl_6(self):
        with mock.patch.object(P, "REGISTERED_AT_8", "2026-10-22T12:24:49Z"):
            self.assertFalse(P.registers_8(), "a time before REGISTERED_AT_6 registers nothing (fail closed)")
        with mock.patch.object(P, "REGISTERED_AT_8", "not a time"):
            self.assertFalse(P.registers_8())
        self.assertEqual(P.REGISTERED_AT_6_FOR_8, "2026-10-22T12:24:50Z", "A116's REGISTERED_AT_6")
        if hasattr(P, "REGISTERED_AT_6"):
            self.assertEqual(P.REGISTERED_AT_6_FOR_8, P.REGISTERED_AT_6)


class TheRowsPinned(Pinned):
    def test_seven_rows_after_every_earlier_row_and_before_the_births(self):
        ids = [p.id for p in P.rows_8()]
        self.assertEqual(ids, ["PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1", "EVL-META-O1", "EVL-META-ON", "CTRL-PX-ALL-ON",
                               "CTRL-PX-ALL-O1"])
        seat = [p.id for p in P.SEATING if not p.born]
        self.assertEqual(seat[-5:], ids[:5], "ROOM's order: after every earlier file's seat (section 4.2)")
        whole = [p.id for p in P.SEATING]
        self.assertEqual(whole[:len(seat)], seat, "R3's births after them (A101)")
        self.assertFalse(any(p.can_seat for p in P.rows_8() if p.id.startswith("CTRL")), "a control never seats")
        for p in P.rows_8():
            self.assertEqual(p.registered_at, S.parse_iso(W.PIN))
            self.assertEqual((p.hold, p.version, p.prereg, p.reads), (1, 1, 8, False))
            self.assertFalse(p.evl6, "PREREG-EVL-6's own run machinery never judges a version of this file (F4's cap)")
        self.assertEqual({p.id: (p.entry_at, p.exit_at) for p in P.rows_8()},
                         {"PX-DROP-ON": ("close", "open"), "PX-SURGE-ON": ("close", "open"), "PX-GAP-O1": ("open", "close"),
                          "EVL-META-O1": ("open", "close"), "EVL-META-ON": ("close", "open"),
                          "CTRL-PX-ALL-ON": ("close", "open"), "CTRL-PX-ALL-O1": ("open", "close")})
        before = [p.id for p in P.PROGRAMS]
        P.refresh_8()
        self.assertEqual([p.id for p in P.PROGRAMS], before, "idempotent: taken out and appended again")

    def test_the_lanes_decisions_never_decide_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = W.World8(Path(tmp) / "lane")
            try:
                W.W5.evl4_rows(w)
                w.at(et(D_DAY, 9, 15, 30)).decide("open", D_DAY)
                w.at(et(D_DAY, 15, 47)).decide("close", D_DAY)
                self.assertIsNone(w.st.db.execute("SELECT 1 FROM intents WHERE program IN (?, ?, ?, ?, ?, ?, ?)",
                                                  tuple(p.id for p in P.rows_8())).fetchone())
                for r in w.st.db.execute("SELECT summary FROM receipts WHERE job LIKE 'decide-%'"):
                    self.assertFalse(any(k.startswith(("PX-", "EVL-META", "CTRL-PX")) for k in json.loads(r[0] or "{}")))
            finally:
                w.close()


# ================================================================================================ the clock and PXU
class TheMorning(WorldCase):
    def test_pxu_is_the_base_less_flagged_with_values_written_once(self):
        got = self.morning()
        self.assertEqual((got["base"], got["pxu"]), (26, 26))
        am = PXL.pxu(self.px().db, D_DAY)
        a = am[W.PX_CIK["PXA"]]
        window = [s.day for s in C.previous(self.w.st, D_DAY, 61)]
        closes = [W.daily("PXA", d)["c"] for d in window]
        import statistics
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, 61)]
        self.assertAlmostEqual(a["sigma60"], statistics.stdev(rets), places=12)
        self.assertAlmostEqual(a["c_star"], W.daily("PXA", P_DAY)["c"])
        self.assertEqual(a["bench"], "IWM", "ADV20 under $50M")
        self.assertAlmostEqual(a["z1"], (a["c_star"] / closes[-2] - a["cb_star"] / W.daily("IWM", window[-2])["c"])
                               / a["sigma60"], places=12)
        again = self.morning()
        self.assertEqual(again["written"], 0, "write-once: the morning's values are never recomputed")

    def test_a_split_effective_d_flags_its_issuer_out(self):
        self.w.gw.adjust[("PXC", P_DAY)] = 0.5      # P's adjusted close read after 09:00 of D: halved (a 2:1 split at D)
        self.morning()
        row = self.px().db.execute("SELECT in_pxu, why FROM px_am WHERE day=? AND cik=?",
                                   (D_DAY.isoformat(), W.PX_CIK["PXC"])).fetchone()
        self.assertEqual((row["in_pxu"], row["why"]), (0, "flagged"))
        self.assertTrue(PXS.PxStore.flag(self.px(), D_DAY, "PXC")["flagged"])
        self.assertTrue(self.px().db.execute("SELECT 1 FROM px_rereads WHERE symbol='PXC' AND day=?",
                                             (D_DAY.isoformat(),)).fetchone(), "the full re-read the House makes")

    def test_a_flagged_session_in_the_window_without_a_reread_is_out(self):
        px = self.px()
        mid = C.previous(self.w.st, D_DAY, 30)[0].day
        px.db.execute("INSERT INTO px_flags(day, symbol, prev_day, c_raw, c_adj, ratio, flagged, read_at, run) VALUES(?, "
                      "'PXD', ?, 20, 10, 0.5, 1, ?, 'r')", (mid.isoformat(), mid.isoformat(), S.iso(et(mid, 9, 1))))
        self.morning()
        row = px.db.execute("SELECT in_pxu, why FROM px_am WHERE day=? AND cik=?",
                            (D_DAY.isoformat(), W.PX_CIK["PXD"])).fetchone()
        self.assertEqual(row["in_pxu"], 0)
        self.assertIn("no full re-read", row["why"])

    def test_refused_before_nine(self):
        with self.assertRaises(ValueError):
            self.w.at(et(D_DAY, 8, 59)).morning(D_DAY)


class TheClock(WorldCase):
    """Section 1.2: a PX value is the value of bars before tau, fetched by the PX part inside its own decision run,
    stored write-once with that run's id, and read by that run's real-money decision."""

    def test_the_close_run_reads_its_own_bars_and_stores_them_with_its_run(self):
        self.morning()
        out = self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        self.assertEqual(out["_status"], "ok")
        tau = C.session(self.w.st, D_DAY).close_decide
        rows = [dict(r) for r in self.px().db.execute("SELECT * FROM px_features WHERE day=? AND kind='on'",
                                                      (D_DAY.isoformat(),))]
        self.assertEqual(len(rows), 26)
        self.assertEqual({r["run"] for r in rows}, {out["run"]})
        self.assertEqual({r["as_of"] for r in rows}, {S.iso(tau)})
        knowable = PXL.knowable(C.session(self.w.st, D_DAY), "on")
        for r in rows:
            self.assertGreaterEqual(S.parse_iso(r["decided_at"]), tau, "fetched after tau: the Basic plan's 16 minutes")
            if r["bar_end"] is not None:
                self.assertLessEqual(S.parse_iso(r["bar_end"]), knowable, "every bar ends by 15:30 ET")
        got = PXL.decided(self.px().db, D_DAY, "on")
        self.assertEqual((got["run"], got["kind"]), (out["run"], "live"))
        picks = PXL.live_picks(self.px().db, P.BY_KEY[("PX-DROP-ON", 1)], D_DAY)
        self.assertEqual([p["symbol"] for p in picks][:3], ["PXG", "PXJ", "PXH"], "(i): its run's ranked names")

    def test_refused_before_tau_and_once_decided(self):
        self.morning()
        with self.assertRaises(ValueError):
            self.w.at(et(D_DAY, 15, 45, 59)).px_decide(D_DAY, "on")
        self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        self.assertIn("decided already", self.w.at(et(D_DAY, 15, 46, 30)).px_decide(D_DAY, "on")["skipped"])

    def test_a_cut_run_trades_nothing_and_its_catch_up_is_never_judged(self):
        """(iv): with the run cut before it wrote D's rows, PX-DROP-ON buys nothing at D's close and its catch-up is
        never a judged block."""
        self.morning()
        out = self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on", late=lambda: True)
        self.assertEqual(out["_status"], "cut")
        self.assertIsNone(PXL.decided(self.px().db, D_DAY, "on"))
        self.assertEqual(PXL.live_picks(self.px().db, P.BY_KEY[("PX-DROP-ON", 1)], D_DAY), [])
        lane = EB.Lane(self.w.st.root / S.DB_NAME)
        try:
            self.assertEqual(EB.picks(lane, P.BY_KEY[("PX-DROP-ON", 1)], D_DAY,
                                      decided_at=C.session(lane, D_DAY).close_decide), [])
        finally:
            lane.close()
        catch = self.w.at(et(D_DAY, 17, 0)).px_decide(D_DAY, "on", kind="catchup")
        self.assertEqual(catch["_status"], "ok")
        self.assertEqual(PXL.decided(self.px().db, D_DAY, "on")["kind"], "catchup")
        self.assertEqual(PXL.live_picks(self.px().db, P.BY_KEY[("PX-DROP-ON", 1)], D_DAY), [], "never traded")
        self.assertNotIn(D_DAY.isoformat(), PXL.judged_days(self.px().db, "on"), "never a judged block")
        kinds = {r["kind"] for r in self.px().db.execute("SELECT DISTINCT kind FROM px_features WHERE day=?",
                                                         (D_DAY.isoformat(),))}
        self.assertEqual(kinds, {"on@c"}, "the catch-up's rows under its own kind; the cut run wrote none")
        self.assertTrue(all(PXL.WHY_CATCHUP == r["why"] for r in self.intents("PX-DROP-ON").values()))

    def test_another_runs_row_or_a_late_bar_is_never_read(self):
        """(iii): a px_features row written by another run, or a bar ending after its knowable time, is never read."""
        self.morning()
        px = self.px()
        cik = W.PX_CIK["PXA"]
        px.db.execute("INSERT INTO px_features(day, cik, kind, symbol, value, decided_at, inputs_at, source, run, as_of, "
                      "bar_end) VALUES(?, ?, 'on@c', 'PXA', ?, '2026-10-27T19:40:00Z', '2026-10-27T19:40:00Z', 'live', "
                      "'another', '2026-10-27T19:46:00Z', '2026-10-27T19:30:00Z')",
                      (D_DAY.isoformat(), cik, json.dumps({"zd": 99.0, "move_d": 0.1, "news": 0})))
        real = W.Gateway8._minutes

        def planted(gw, symbols, start, end):       # a bar after 15:30 in the answer, at a price that would qualify
            out = real(gw, symbols, start, end)
            if start.astimezone(C.NY).time() == dt.time(15, 0):
                for s in symbols:
                    out[s].append({"t": S.iso(end + dt.timedelta(minutes=3)), "o": 1, "h": 1, "l": 1, "c": 1.0, "v": 1})
            return out
        with mock.patch.object(W.Gateway8, "_minutes", planted):
            self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        values = PXL.features(px.db, D_DAY, "on")
        self.assertNotEqual(values[cik].get("zd"), 99.0)
        self.assertAlmostEqual(values[cik]["x"], W.daily("PXA", P_DAY)["c"] * 0.92, places=3,
                               msg="the 15:29 bar's close, never the planted later bar")


class TheSpans(WorldCase):
    def test_no_stored_item_in_the_on_span(self):
        """An item knowable in the ON span and stored before tau keeps its issuer out of the seats at the decision; one
        stored after it does not, and the hourly re-decision removes it and the next name takes its place."""
        self.morning()
        self.w.article("n-pxa", "PXA", knowable=et(D_DAY, 13, 0))                       # stored then: out
        self.w.article("n-pxb", "PXB", knowable=et(D_DAY, 13, 0), stored=et(D_DAY, 16, 0))   # stored after tau
        self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        drop = self.intents("PX-DROP-ON")
        self.assertNotIn(W.PX_CIK["PXA"], drop)
        self.assertEqual(drop[W.PX_CIK["PXB"]]["status"], "planned")
        values = PXL.features(self.px().db, D_DAY, "on")
        self.assertEqual(values[W.PX_CIK["PXA"]]["news"], 1)
        self.assertIsNone(values[W.PX_CIK["PXA"]]["x"], "x_D is read only for the names with no stored item")
        got = self.w.at(et(D_DAY, 16, 40)).redecide(D_DAY, "on")
        self.assertEqual(got["PX-DROP-ON"]["removed"], 1)
        self.assertEqual(self.intents("PX-DROP-ON")[W.PX_CIK["PXB"]]["status"], PXL.WHY_REMOVED)
        self.assertNotIn(W.PX_CIK["PXB"], PXL.features(self.px().db, D_DAY, "on") and
                         {c for c, r in self.intents("CTRL-PX-ALL-ON").items() if r["status"] == "planned"})
        lane = EB.Lane(self.w.st.root / S.DB_NAME)
        try:
            names = [p.symbol for p in EB.picks(lane, P.BY_KEY[("PX-DROP-ON", 1)], D_DAY,
                                                decided_at=C.session(lane, D_DAY).close_decide)]
        finally:
            lane.close()
        self.assertIn("PXB", names, "real money read the items stored before its decision time: the live run's picks")

    def test_the_spans(self):
        sp = PXL.spans(self.w.st, D_DAY)
        p = C.session(self.w.st, P_DAY)
        d = C.session(self.w.st, D_DAY)
        self.assertEqual(sp["on"], (p.close_decide, d.close_decide))
        self.assertEqual(sp["o1"], (p.close_decide, d.open_cutoff))

    def test_an_eight_k_or_an_insider_buy_or_any_symbol_article_counts(self):
        tickers = self.w.ctx.tickers_for(D_DAY)
        lo, hi = PXL.spans(self.w.st, D_DAY)["on"]
        self.w.article("n-many", "AAA", knowable=et(D_DAY, 12, 0), symbols=["AAA", "PXK", "BBB"])
        self.w.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                             "received_at, source, status) VALUES('px-8k', '8-K', ?, 'x', '[\"5.07\"]', ?, ?, ?, 'current', "
                             "'fetched')", (W.PX_CIK["PXM"], S.iso(et(D_DAY, 11, 0)), S.iso(et(D_DAY, 11, 10)),
                                            S.iso(et(D_DAY, 11, 10))))
        got = PXL.item_ciks(self.w.st, lo, hi, tickers=tickers)
        self.assertIn(W.PX_CIK["PXK"], got)
        self.assertIn(W.PX_CIK["PXM"], got)
        self.assertNotIn(W.PX_CIK["PXN"], got)


class TheSeats(WorldCase):
    def setUp(self):
        super().setUp()
        self.morning()

    def test_the_three_rules_and_rankings(self):
        self.w.at(et(D_DAY, 9, 16)).px_decide(D_DAY, "o1")
        self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        values = PXL.features(self.px().db, D_DAY, "on")
        drop = sorted(((r["rank_key"], c) for c, r in self.intents("PX-DROP-ON").items()), reverse=True)
        want = sorted(PXL.ranked(P.BY_KEY[("PX-DROP-ON", 1)], values), key=lambda x: (-x[1],
                                                                                     -float(values[x[0]]["adv20"]), x[0]))
        self.assertEqual([c for _, c in drop], [c for c, _ in want])
        names = {self.intents("PX-DROP-ON")[c]["symbol"] for c in self.intents("PX-DROP-ON")}
        self.assertEqual(names, {"PXA", "PXB", "PXC", "PXD", "PXG", "PXH", "PXJ"})
        for c, r in self.intents("PX-DROP-ON").items():
            v = values[c]
            self.assertLessEqual(v["zd"], -2.0)
            self.assertTrue(-0.35 <= v["move_d"] <= -0.03)
            self.assertAlmostEqual(r["rank_key"], -v["zd"])
        self.assertEqual({r["symbol"] for r in self.intents("PX-SURGE-ON").values()}, {"PXE", "PXF"},
                         "PXI's V_D 1.2 is under 1.5")
        self.assertEqual({r["symbol"] for r in self.intents("PX-GAP-O1").values()}, {"PXK", "PXL"},
                         "PXM's premarket has one bar with volume, under 3")
        for r in self.intents("PX-GAP-O1").values():
            self.assertEqual(r["event"], f"px:PX-GAP-O1:{D_DAY}:{r['cik']}")
            self.assertEqual((r["entry_at"], r["exit_at"], r["exit_day"]), ("open", "close", D_DAY.isoformat()))
        for r in self.intents("PX-DROP-ON").values():
            self.assertEqual((r["entry_at"], r["exit_at"], r["exit_day"]), ("close", "open", N_DAY.isoformat()))

    def test_qualifies_at_the_edges(self):
        drop = P.BY_KEY[("PX-DROP-ON", 1)]
        self.assertEqual(PXL.qualifies(drop, {"zd": -2.0, "move_d": -0.03, "news": 0}), 2.0)
        self.assertIsNone(PXL.qualifies(drop, {"zd": -1.999, "move_d": -0.05, "news": 0}))
        self.assertIsNone(PXL.qualifies(drop, {"zd": -5.0, "move_d": -0.351, "news": 0}))
        self.assertIsNone(PXL.qualifies(drop, {"zd": -5.0, "move_d": -0.05, "news": 1}))
        surge = P.BY_KEY[("PX-SURGE-ON", 1)]
        self.assertEqual(PXL.qualifies(surge, {"zd": 2.0, "move_d": 0.20, "vd": 1.5, "news": 0}), 2.0)
        self.assertIsNone(PXL.qualifies(surge, {"zd": 3.0, "move_d": 0.201, "vd": 2.0, "news": 0}))
        gap = P.BY_KEY[("PX-GAP-O1", 1)]
        self.assertIsNone(PXL.qualifies(gap, {"zg": -3.0, "move_g": -0.05, "adv20": 19_999_999.0, "news": 0}))
        self.assertEqual(PXL.qualifies(gap, {"zg": -3.0, "move_g": -0.02, "adv20": 2e7, "news": 0}), 3.0)

    def test_k_40_after_a72s_skips(self):
        drop = P.BY_KEY[("PX-DROP-ON", 1)]
        values = {str(i).zfill(10): {"zd": -3.0 - i / 100, "move_d": -0.05, "news": 0, "adv20": 1e7} for i in range(60)}
        held = str(59).zfill(10)       # the best ranked, held by an intent of the last 5 sessions
        prev = C.previous(self.w.st, D_DAY, 2)[0].day
        self.w.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                             "exit_day, exit_at, rank_key, mode, status, why) VALUES('PX-DROP-ON', 1, 'px:old', 'Z', ?, "
                             "'x', ?, 'close', ?, 'open', 1, 'shadow', 'exited', NULL)",
                             (held, prev.isoformat(), P_DAY.isoformat()))
        order = [c for c, _ in PXL.ranked(drop, values)]
        self.assertEqual(order[0], held)
        got, skipped = PXL.take(self.w.st, drop, D_DAY, order, PXL.K)
        self.assertEqual(len(got), 40)
        self.assertEqual(skipped, [held])
        self.assertEqual(got, order[1:41], "the next qualifying names take the held one's place")


class TheControls(WorldCase):
    def test_the_200_smallest_hashes_of_the_no_news_population(self):
        values = {str(i).zfill(10): {"news": int(i % 7 == 0), "adv20": 3e7 if i % 3 else 1e7} for i in range(400)}
        pop = PXL.control_population("on", values)
        self.assertEqual(len(pop), sum(1 for v in values.values() if not v["news"]))
        o1 = PXL.control_population("o1", values)
        self.assertTrue(all(values[c]["adv20"] >= 2e7 for c in o1), "PX-GAP-O1's events-of-D population")
        order = sorted(pop, key=lambda c: PXL.control_hash("on", D_DAY, c))
        got, _ = PXL.take(self.w.st, P.BY_KEY[("CTRL-PX-ALL-ON", 1)], D_DAY, order, PXL.CONTROL_N)
        self.assertEqual(len(got), 200)
        want = sorted(pop, key=lambda c: hashlib.sha256(f"PX-CTRL|ON|{D_DAY}|{c}".encode()).hexdigest())[:200]
        self.assertEqual(got, want)
        self.assertNotEqual(sorted(pop, key=lambda c: PXL.control_hash("o1", D_DAY, c))[:200], want, "|O1| differs")

    def test_the_controls_never_seat_and_are_the_seats_control_condition(self):
        self.assertEqual(S8.CONTROL_OF, {"PX-DROP-ON": "CTRL-PX-ALL-ON", "PX-SURGE-ON": "CTRL-PX-ALL-ON",
                                         "PX-GAP-O1": "CTRL-PX-ALL-O1"})
        self.assertIsNone(EB.program_of("CTRL-PX-ALL-ON", 1))


# ================================================================================================ the grid and the panel
class TheGrid(unittest.TestCase):
    def test_pinned_by_its_canonical_sha256(self):
        rows = PXL.grid()
        self.assertEqual(PXL.GRID_SHA256, "bb0d50e47d94e73f677a22bb612ef3f1cf7d23b23e5a51375fe965cf57e3e5a1")
        self.assertEqual(PXL.grid_sha(rows), PXL.GRID_SHA256)
        self.assertEqual(len(rows), 528)
        self.assertEqual({w: len(PXL.records(w)) for w in ("O1", "ON", "C1")}, {"O1": 184, "ON": 173, "C1": 171})
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "g.json"
            tampered = copy.deepcopy(rows)
            tampered[0]["side"] = "HI"
            bad.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, "not the pinned"):
                PXL.grid(bad)

    def test_the_evaluator(self):
        values = {str(i).zfill(10): {"z1": float(i), "news": int(i % 2), "bench": "IWM" if i < 10 else "SPY",
                                     "v": float(100 - i), "drift": {"EVL-CTRL-NEWS-ALL-O1|1": (1.5 if i == 3 else -2.0)}}
                  for i in range(30)}
        rec = next(r for r in PXL.grid() if r["id"] == "PXR-REV1-LO-ANY-ALL-O1")
        self.assertEqual(PXL.select_record(rec, values), {"0000000000", "0000000001", "0000000002"},
                         "the bottom decile, floor(30 / 10) names")
        none = next(r for r in PXL.grid() if r["id"] == "PXR-REV1-LO-NONE-ALL-O1")
        self.assertEqual(PXL.select_record(none, values), {"0000000000", "0000000002"}, "the decile, then the news filter")
        hi_small = next(r for r in PXL.grid() if r["id"] == "PXR-REV1-HI-ANY-SMALL-O1")
        self.assertEqual(PXL.select_record(hi_small, values), set(), "the decile, then the tier")
        up = next(r for r in PXL.grid() if r["id"] == "PXR-DRIFT-NEWS-ALL-O1-K1-UP-O1")
        dn = next(r for r in PXL.grid() if r["id"] == "PXR-DRIFT-NEWS-ALL-O1-K1-DN-O1")
        self.assertEqual(PXL.select_record(up, values), {"0000000003"})
        self.assertEqual(len(PXL.select_record(dn, values)), 29)
        hiup = next(r for r in PXL.grid() if r["id"] == "PXR-VOL-HIUP-ANY-ALL-O1")
        self.assertEqual(PXL.select_record(hiup, values), {"0000000001", "0000000002"}, "top decile of v, z1 > 0")
        univ = next(r for r in PXL.grid() if r["id"] == "PXR-UNIV-SOME-ALL-O1")
        self.assertEqual(len(PXL.select_record(univ, values)), 15)
        seat = next(r for r in PXL.grid() if r["id"] == "PXR-SEAT-DROP-ON")
        self.assertEqual(PXL.select_record(seat, values, seat_events={"PX-DROP-ON": {"0000000004"}}), {"0000000004"})
        self.assertEqual(PXL.select_record(seat, values, seat_events={"PX-DROP-ON": {"0000000005"}}), set(),
                         "SEAT records carry the NONE filter")
        self.assertEqual(PXL.select_record(seat, values, seat_events={"PX-DROP-ON": {"0000000004", "0000000006"}}),
                         {"0000000004", "0000000006"})
        fewer = {k: v for k, v in list(values.items())[:9]}
        self.assertEqual(PXL.select_record(rec, fewer), set(), "under 10 names: no decile")


class ThePanel(WorldCase):
    def test_bar_basis_rows_record_days_and_basis(self):
        self.morning()
        self.w.at(et(D_DAY, 9, 16)).px_decide(D_DAY, "o1")
        self.w.at(et(D_DAY, 15, 46, 5)).px_decide(D_DAY, "on")
        px = self.px()
        for d in (D_DAY, N_DAY):
            for sym in (*W.PX_NAMES, "SPY", "IWM"):
                b = W.daily(sym, d)
                for adj in ("raw", "all"):
                    px.db.execute("INSERT OR REPLACE INTO px_bars(symbol, day, adj, o, h, l, c, v, n, vw, t, fetched_at, "
                                  "run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 't', ?, 'n')",
                                  (sym, d.isoformat(), adj, b["o"], b["h"], b["l"], b["c"] * (2.0 if adj == "all" and
                                                                                            sym == "PXA" else 1.0),
                                   b["v"], S.iso(et(d, 20))))
        out = PXL.settle_panel(px, self.w.st, D_DAY, now=et(N_DAY, 21))
        self.assertEqual(out["panel"], 3 * 26)
        row = px.db.execute("SELECT * FROM px_panel WHERE day=? AND window='ON' AND cik=?",
                            (D_DAY.isoformat(), W.PX_CIK["PXB"])).fetchone()
        c, o = W.daily("PXB", D_DAY)["c"], W.daily("PXB", N_DAY)["o"]
        cin, cout = SC.cost_bp(row["cost_entry_bp"] and 4e7, 1900.0, "entry"), None
        self.assertAlmostEqual(row["entry_px"], c)
        self.assertAlmostEqual(row["exit_px"], o)
        self.assertAlmostEqual(row["r"], SC.after_cost_return(c, o, row["cost_entry_bp"], row["cost_exit_bp"]))
        self.assertAlmostEqual(row["b"], W.daily(row["bench"], N_DAY)["o"] / W.daily(row["bench"], D_DAY)["c"] - 1)
        a = px.db.execute("SELECT * FROM px_panel WHERE day=? AND window='O1' AND cik=?",
                          (D_DAY.isoformat(), W.PX_CIK["PXA"])).fetchone()
        self.assertAlmostEqual(a["entry_px"], W.daily("PXA", D_DAY)["o"] * 2.0, msg="the adjusted ratio of the day")
        days = px.db.execute("SELECT COUNT(*) FROM px_record_days WHERE day=?", (D_DAY.isoformat(),)).fetchone()[0]
        self.assertEqual(days, 528, "every record's day once: O1, ON and C1")
        self.assertEqual(PXL.settle_panel(px, self.w.st, D_DAY, now=et(N_DAY, 22))["panel"], 0, "write-once")


# ================================================================================================ the judge
def ev(day: dt.date, n: int, a: float, *, issuer0: int = 0, rank: bool = True) -> list[dict]:
    return [{"event": f"e:{day}:{i}", "entry_day": day, "exit_day": day, "issuer": f"i{issuer0 + i}", "a": a + 0.001 * i,
             "r": a + 0.002 + 0.001 * i, "tradable": True, "rank_key": (float(n - i) if rank else None),
             "adv20": 1e7} for i in range(n)]


class TheJudge(unittest.TestCase):
    """PREREG-EVL-6 sections 1.3-1.4 as frozen, with F4's cap (`screen8.judge_blocks`, the one narrow interface)."""

    def days(self, n: int) -> list[dt.date]:
        start = dt.date(2026, 11, 2)
        return [start + dt.timedelta(days=i) for i in range(n)]

    def test_the_exact_count_is_every_sign_vector(self):
        vals = [0.3, -0.1, 0.2, 0.05, -0.02]
        p = S8.count_p(vals, "x")
        total = sum(vals)
        count = sum(1 for signs in itertools.product((1, -1), repeat=5)
                    if sum(s * v for s, v in zip(signs, vals)) >= total - 5 * 1e-12)
        self.assertEqual(p, count / 32)

    def test_the_monte_carlo_is_the_seed_strings(self):
        vals = [0.01 * ((-1) ** i) + 0.002 for i in range(22)]
        p = S8.count_p(vals, "PX-DROP-ON|v1|evl6|S22")
        self.assertEqual(p, (1 + SN._count(vals, SN._flips(SN.seed_of("PX-DROP-ON|v1|evl6|S22"), 22, SN.B))) / (1 + SN.B))
        self.assertEqual(S8.seed_string("PX-DROP-ON", 1, "run2|", 25), "PX-DROP-ON|v1|evl6|run2|S25")
        self.assertEqual((S8.tag("run", 1), S8.tag("run", 2), S8.tag("stay", 1)), ("", "run2|", "stay1|"))

    def test_alpha_and_the_looks(self):
        self.assertEqual(S8.LOOKS, (22, 25, 30, 35, 40, 50, 60), "F1: the frozen 22nd block is the PX seats' first look")
        self.assertEqual([S8.alpha(s) for s in (21, 22, 30, 31, 40, 41, 60, 61)],
                         [None, 0.020, 0.020, 0.006, 0.006, 0.001, 0.001, None])

    def test_f4s_cap_weighs_each_block_by_what_its_band_can_buy(self):
        blks = S8.blocks([e for d in self.days(3) for e in ev(d, 10, 0.004)])
        self.assertEqual([round(v, 10) for v in S8.values(blks, 4)], [round(4 * (b.value - 0.001), 10) for b in blks])
        self.assertEqual([round(v, 10) for v in S8.values(blks, 14)], [round(10 * (b.value - 0.001), 10) for b in blks])
        self.assertEqual(S8.CAP, {"px": {"run": 4, "probe": 14, "sized": 8}, "meta": {"run": 8, "probe": 14, "sized": 8}})
        self.assertEqual(S8.cap_of(P.ROWS_8[0], "run"), 4)
        self.assertEqual(S8.cap_of(P.ROWS_8[3], "run"), 8)
        self.assertEqual(S8.cap_of(P.ROWS_8[0], "stay", "probe"), 14)
        self.assertEqual(S8.cap_of(P.ROWS_8[0], "stay", "sized"), 8)

    def test_the_top_cap_guard_reads_the_seats_ranking(self):
        rows = []
        for d in self.days(22):
            for i in range(10):     # the top 4 by rank lose, the rest win: the event-weighted mean is positive
                rows.append({"event": f"e:{d}:{i}", "entry_day": d, "exit_day": d, "issuer": f"i{d}{i}",
                             "a": (-0.02 if i < 4 else 0.03), "r": (-0.02 if i < 4 else 0.03), "tradable": True,
                             "rank_key": float(10 - i), "adv20": 1e7})
        got = S8.judge_blocks(S8.blocks(rows), cap=4, program="PX-DROP-ON", version=1)
        self.assertFalse(got["guards"]["top_a"], "the top 4 of each block lose")
        self.assertIsNone(got["decision"])
        loose = S8.judge_blocks(S8.blocks(rows), cap=14, program="PX-DROP-ON", version=1)
        self.assertTrue(loose["guards"]["top_a"], "at 14 the whole block is the money's")

    def test_retire_first_and_pass(self):
        lose = S8.blocks([e for d in self.days(22) for e in ev(d, 3, -0.03, issuer0=0)])
        got = S8.judge_blocks(lose, cap=4, program="X", version=1)
        self.assertEqual(got["decision"], "retire")
        self.assertEqual(got["guards"], {}, "nothing else is checked")
        win_rows = []
        for k, d in enumerate(self.days(30)):
            win_rows += ev(d, 3, 0.02, issuer0=3 * k)
        got = S8.judge_blocks(S8.blocks(win_rows), cap=4, program="X", version=1, control_rows=[], control="C")
        self.assertFalse(got["guards"]["control"], "no control block: the condition fails")
        got = S8.judge_blocks(S8.blocks(win_rows), cap=4, program="X", version=1)
        self.assertEqual(got["decision"], "pass", got["why"])
        few = S8.judge_blocks(S8.blocks(win_rows[:3 * 21]), cap=4, program="X", version=1)
        self.assertIsNone(few["decision"], "no look below the 22nd block")

    def test_equal_to_prereg_evl_6s_own_judge_at_cap_14(self):
        judge = getattr(SN, "v6_judge", None)
        if judge is None:
            self.skipTest("PREREG-EVL-6's code is not in this tree (feat/evl-6): the reproduction runs where it is")
        rows = []
        rng = random.Random(8)
        for k, d in enumerate(self.days(30)):
            for i in range(rng.randrange(1, 18)):
                rows.append({"event": f"e:{d}:{i}", "entry_day": d, "exit_day": d, "issuer": f"i{rng.randrange(80)}",
                             "a": rng.gauss(0.001, 0.02), "r": rng.gauss(0.002, 0.02), "tradable": True,
                             "rank_key": rng.random(), "adv20": 1e7})
        mine = S8.judge_blocks(S8.blocks(rows), cap=14, program="X", version=1, tag="", draws=999)
        theirs = judge(SN.blocks6(rows), program="X", version=1, tag="", draws=999)
        for k in ("S", "alpha", "p", "q", "p_issuer", "decision", "mean_a", "mean_r", "money_a"):
            self.assertEqual(mine[k], theirs[k], k)


class TheRuns(Pinned):
    def test_the_budget_is_the_seating_sum_and_runs_start_in_registration_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp) / "lane")
            try:
                b = S8.budget(st)
                self.assertEqual(b["versions"], len(P.SEATING))
                self.assertEqual(b["used"], 13 * len(P.SEATING), "0.13 a version: this file's five charged at the pin")
                self.assertEqual(S8.BUDGET_HUNDREDTHS, 390)
                ch = S8.charges(st)
                self.assertEqual(ch["count"], 0.65)
                self.assertEqual((ch["base"], ch["stress"]), (0.08, 0.53))
                # every PX seat's run 1 ended at its 60th block: the fresh runs start while the budget holds 0.13 each
                for p in S8.seating8():
                    st.set_meta(S8.END_KEY.format(program=p.id, version=1, n=1),
                                json.dumps({"at": "2026-12-01T21:00:00Z", "last_day": "2026-12-01", "n": 1}))
                room = (390 - S8.budget(st)["used"]) // 13
                started = S8.start_runs(st, S.parse_iso("2026-12-02T01:00:00Z"))
                self.assertEqual(len(started), min(room, 5))
                self.assertEqual([x["program"] for x in started],
                                 sorted(p.id for p in S8.seating8())[:len(started)], "registration order, then the id")
                self.assertEqual(S8.budget(st)["used"], 13 * (len(P.SEATING) + len(started)), "charged when it starts")
                self.assertEqual(S8.start_runs(st, S.parse_iso("2026-12-02T02:00:00Z")), [] if room <= 5 else [])
            finally:
                st.close()


# ================================================================================================ the meta-learners
class TheMetaConstants(unittest.TestCase):
    def test_the_registered_constants_and_the_grid(self):
        self.assertEqual((MT.K, MT.H, MT.TAU, MT.SF, MT.Z, MT.HURDLE, MT.MINB, MT.WARM),
                         (16, 60.0, 0.0030, 0.0020, 3.0, 0.0, 3, 10))
        self.assertEqual((MT.VAR_FLOOR, MT.WINSOR, MT.IMPUTE_AFTER, MT.IMPUTE_A, MT.FAMILY_CAP),
                         (0.015 ** 2, 0.10, 3, -0.30, 1535))
        self.assertEqual(len(MT.grid_rules(MT.GROUPS_O1)), 720)
        self.assertEqual(len(MT.grid_rules(MT.GROUPS_ON)), 969)
        self.assertEqual(sum(len(v) for v in MT.GROUPS_O1.values()), 39)
        self.assertEqual(sum(len(v) for v in MT.GROUPS_ON.values()), 45)

    def test_the_features_port(self):
        m = {"fam": "news-on", "score": 3, "source": "Benzinga", "hour_et": (6, 15), "cov72": 2, "adv20": 2.5e7,
             "prev_close": 14.2, "closes20": [10 + 0.1 * i for i in range(20)]}
        f = MT.features(m, "o1")
        self.assertTrue({"news-on", "s>=1", "s>=2", "s=3", "bz", "h04-08", "c1-3", "adv10-100M", "px10-50", "r5mid",
                         "r20>=+10%"} <= f)
        rl = MT.rules_of(f, ["EVL-NEWS-READ-O1:2"], MT.group_of(MT.GROUPS_ON))
        self.assertIn("g:s=3", rl)
        self.assertIn("g:adv10-100M&s>=2", rl)
        self.assertIn("p:EVL-NEWS-READ-O1:2", rl)
        self.assertNotIn("g:s>=1&s>=2", rl, "same group: never a pair")
        self.assertIn("smiss", MT.features({}, "o1"))
        self.assertEqual(MT.features({"react": 0.95, "gap": 1.03}, "on") & {"re<=0.96", "gap>=1.02"},
                         {"re<=0.96", "gap>=1.02"})
        self.assertFalse(MT.features({"react": 0.95}, "o1") & {"re<=0.96"}, "REACT and GAP are ON only")

    def test_warm_and_the_walk(self):
        gof = MT.group_of(MT.GROUPS_O1)
        rng = random.Random(8)
        feats = [MT.features({"fam": rng.choice(["news-on", "8k", "ern"]), "score": rng.choice([None, 1, 2, 3]),
                              "adv20": rng.choice([5e6, 5e7, 5e8]), "prev_close": 20.0}, "o1") for _ in range(200)]
        true = "g:adv>=100M&s>=2"
        sessions = []
        for _ in range(30):
            mem = []
            for fs in feats:
                rules = MT.rules_of(fs, [], gof)
                mem.append({"rules": rules, "a": rng.gauss(0, 0.03) + (0.006 if true in rules else -0.0014),
                            "tradable": True})
            sessions.append(MT.session_stats(mem))
        st = MT.state(sessions)
        today = [{"event": f"e{i}", "cik": str(i), "adv20": 1e6 * i, "rules": MT.rules_of(fs, [], gof), "eligible": True}
                 for i, fs in enumerate(feats)]
        self.assertEqual(MT.walk(today, st, 0.0014, session_index=10), [], "no pick while the state holds 10 or fewer")
        picks = MT.walk(today, st, 0.0014, session_index=11)
        self.assertTrue(0 < len(picks) <= 16)
        self.assertTrue(all(true in today[int(e[1:])]["rules"] for e, _, _ in picks[:5]))
        lcbs = [l for _, _, l in picks]
        self.assertEqual(lcbs, sorted(lcbs, reverse=True) if len(set(r for _, r, _ in picks)) > 1 else lcbs)

    def test_the_state_is_pool_relative(self):
        shifted = [{"rules": {"g:x"}, "a": 0.05 + 0.001 * i, "tradable": True} for i in range(10)] + \
                  [{"rules": {"g:y"}, "a": 0.05, "tradable": True} for _ in range(10)]
        stats, n, Pm, var = MT.session_stats(shifted)
        self.assertEqual(n, 20)
        self.assertAlmostEqual(Pm, math.fsum(m["a"] for m in shifted) / 20)
        st = MT.state([MT.session_stats(shifted)] * 5)
        flat = [dict(m, a=m["a"] - 0.05) for m in shifted]
        st2 = MT.state([MT.session_stats(flat)] * 5)
        for j in ("g:x", "g:y"):
            self.assertAlmostEqual(st[j][1], st2[j][1], places=9, msg="the pool's level is never learned (V1)")

    def test_f8_a_rule_is_kept_only_hashed(self):
        self.assertEqual(MT.rule_hash("g:s=3"), hashlib.sha256(b"EVL8-MRL|g:s=3").hexdigest()[:16])
        self.assertLessEqual(MT.TABLES, BI.FACTS_DENY)
        self.assertLessEqual(PXL.TABLES_8, BI.FACTS_DENY)
        self.assertLessEqual(PXS.TABLES, BI.FACTS_DENY)


class TheFamily(Pinned):
    def test_never_above_the_cap(self):
        at = S.parse_iso("2026-10-27T13:15:00Z")
        for auction, grid, recs in (("o1", 720, 184), ("on", 969, 173)):
            rules, fam = MT.family(auction, at)
            self.assertEqual(len([r for r in rules if r.startswith("g:")]), grid)
            self.assertEqual(len([r for r in rules if r.startswith("x:")]), recs)
            progs = [r for r in rules if r.startswith("p:")]
            self.assertEqual(len(progs), len(MT.sources(auction, at)))
            self.assertLessEqual(len(rules), MT.FAMILY_CAP)
        many = [dataclasses.replace(P.ROWS_8[5], id=f"CTRL-X-{i}") for i in range(900)]
        with mock.patch.object(MT, "sources", lambda auction, at: many):
            rules, _ = MT.family("on", at)
        self.assertEqual(len(rules), MT.FAMILY_CAP, "a program expert beyond the cap never joins")

    def test_the_sources(self):
        at = S.parse_iso("2026-10-27T19:46:00Z")
        on = {p.id for p in MT.sources("on", at)}
        o1 = {p.id for p in MT.sources("o1", at)}
        self.assertIn("PX-DROP-ON", on)
        self.assertIn("CTRL-PX-ALL-ON", on)
        self.assertIn("EVL-CTRL-NEWS-DAY-ON", on)
        self.assertIn("PX-GAP-O1", o1)
        self.assertIn("EVL-CTRL-ERN-ALL-O1", o1)
        self.assertNotIn("EVL-META-ON", on)
        self.assertNotIn("EVL-ERN-READ-O3", o1, "hold 3 is no source")
        self.assertNotIn("EVL-ERN-REACT-C1", on | o1, "a C1 row is no source")
        early = S.parse_iso("2026-10-21T00:00:00Z")
        self.assertFalse({p.id for p in MT.sources("on", early)} & {"PX-DROP-ON", "EVL-ERN-DROP-ON"},
                         "only programs registered before the decision")


# ================================================================================================ the money row
class TheMoneyRow(unittest.TestCase):
    def test_one_row_bounded_zero_to_four_and_the_digests_moved_once(self):
        """Section 4.1 (A122): ONE money row, `event.max_open_v8.learning` 4 with bounds 0-4 (the frozen text's: no value
        above 4 exists for the PX seats), in one commit; the pair moved once, from release 1019l's 1687e4e3 / 3feab26d
        to 77c3cfed / 138ee8eb, and with the row left out every candidate is back on release 1019l's pins."""
        e = K.CONSTITUTION["equity_money"]["event"]
        self.assertEqual(e["max_open_v8"], {"learning": 4})
        self.assertEqual(K.EQUITY_MONEY_BOUNDS["event.max_open_v8.learning"], ("0", "4"))
        self.assertEqual((K.money_digest()[:8], K.digest()[:8]), ("77c3cfed", "138ee8eb"))
        self.assertEqual(K.digest(), K.PINNED_DIGEST)
        before = X.before_1019n()
        self.assertEqual((K.money_digest(before)[:8], K.digest(before)[:8]), ("1687e4e3", "3feab26d"),
                         "release 1019l's pair with the row left out")
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((K.money_digest(at), K.digest(at)), X.DIGESTS[candidate])
            back = X.before_1019n(at)
            self.assertEqual((K.money_digest(back), K.digest(back)), X.DIGESTS_1019L[candidate])
            self.assertEqual((K.money_digest(X.before_1019i(at)), K.digest(X.before_1019i(at))),
                             X.DIGESTS_1019H[candidate], "every older table's helper leaves the row out too")
        for bad in ("5", "-1", "x", 4.0):
            c = copy.deepcopy(K.CONSTITUTION)
            c["equity_money"]["event"]["max_open_v8"]["learning"] = bad
            self.assertTrue(K.equity_money_problems(c), bad)
            self.assertIs(EB.settings(c), EB.FALLBACK, bad)
        off = copy.deepcopy(K.CONSTITUTION)
        off["equity_money"]["event"]["max_open_v8"]["learning"] = 0
        self.assertEqual(K.equity_money_problems(off), [])
        self.assertEqual((K.money_digest(off)[:8], K.digest(off)[:8]), X.V8_SLOTS_OFF)

    def test_read_for_the_px_seats_alone(self):
        s = EB.settings()
        with W.pinned():
            self.assertEqual(EB.max_open_8(s, "learning", P.BY_KEY[("PX-DROP-ON", 1)]), 4)
            self.assertEqual(EB.max_open_8(s, "learning", P.BY_KEY[("EVL-META-ON", 1)]), 8)
            probe = EB.max_open_8(s, "probe", P.BY_KEY[("PX-DROP-ON", 1)])
            want = K.CONSTITUTION["equity_money"]["event"].get("max_open_v6", {}).get("probe", 6)
            self.assertEqual(probe, want, "PREREG-EVL-6's 14 where the table carries it, else 6 (trades less)")
            self.assertEqual(EB.max_open_8(s, "sized", P.BY_KEY[("PX-GAP-O1", 1)]), 8)
        self.assertEqual(s.max_open("learning"), 8, "every other program keeps 8")


class TheRoom(Pinned):
    def test_after_every_earlier_row_whatever_its_band_and_before_births_at_learning(self):
        earlier_learning = EB.room_key("EVL-NEWS-NIGHT2-ON", "learning")
        for band in ("sized", "probe", "learning"):
            mine = EB.room_key("PX-DROP-ON", band)
            self.assertGreater(mine, earlier_learning, band)
            self.assertLess(mine[0], EB.BIRTH_ROOM)
            promoted = band in ("sized", "probe")
            # (section 4.2's last bullet: AT THE OTHER AUCTION a promoted version is among the Probe and Sized programs
            # A85's reservation keeps room for, and its buys never leave it; at learning neither, as a PREREG learning
            # row's)
            self.assertIs(EB.reserved_for("PX-DROP-ON", band), promoted, band)
            self.assertIs(EB.leaves_room("PX-DROP-ON", band), not promoted, band)
            self.assertIs(EB.reserved_for("EVL-META-ON", band), promoted, band)
        self.assertLess(EB.room_key("PX-DROP-ON", "probe"), EB.room_key("PX-DROP-ON", "learning"))
        order = [EB.room_key(p, "learning") for p in ("PX-DROP-ON", "PX-SURGE-ON", "PX-GAP-O1", "EVL-META-O1",
                                                      "EVL-META-ON")]
        self.assertEqual(order, sorted(order), "the tables' order: PX-DROP-ON, PX-SURGE-ON, PX-GAP-O1, META-O1, META-ON")
        self.assertEqual(EB.send_key("PX-DROP-ON", "probe", 1)[1], 1, "round-robin inside this file's Probe tier")
        self.assertEqual(EB.send_key("PX-DROP-ON", "learning", 3)[1], 0)
        self.assertEqual(EB.line_keep_8("PX-GAP-O1"), 32)
        self.assertEqual(EB.line_keep_8("EVL-ERN-READ-O1"), 0)


# ================================================================================================ secrecy and the report
class TheSecrecy(WorldCase):
    def test_no_lcb_rule_or_figure_in_an_intent_a_receipt_or_the_report(self):
        patch = mock.patch.object(MT, "STATE_FROM", dt.date(2026, 10, 1))     # (13 entered sessions before D)
        patch.start()
        self.addCleanup(patch.stop)
        self.morning()
        self.w.at(et(D_DAY, 9, 15, 30)).decide("open", D_DAY)
        self.w.at(et(D_DAY, 9, 16)).px_decide(D_DAY, "o1")
        mt = MT.learner("o1")
        # a state with a qualifying rule: 12 entered sessions in which the PX controls' members earned
        self._seed_state(mt)
        self.w.at(et(D_DAY, 9, 16, 20)).meta_decide(D_DAY, "o1")
        intents = [dict(r) for r in self.w.st.db.execute("SELECT * FROM intents WHERE program='EVL-META-O1'")]
        self.assertTrue(intents, "the seeded rule qualifies: the walk picks")
        for r in intents:
            self.assertEqual(r["why"], "mrl")
            self.assertEqual(r["rank_key"], float(int(r["rank_key"])))
            self.assertTrue(1 <= r["rank_key"] <= MT.K)
        walk = [dict(r) for r in self.w.st.db.execute("SELECT * FROM mrl_walk WHERE program='EVL-META-O1'")]
        self.assertEqual(len(walk), len(intents))
        hashes = {r["rule_h"] for r in walk}
        text = json.dumps([dict(r) for r in self.w.st.db.execute("SELECT job, summary FROM receipts")])
        report = RP.render(RP.build(self.w.st, D_DAY, now=et(D_DAY, 21)))
        for h in hashes:
            self.assertNotIn(h, text)
            self.assertNotIn(h, report)
        for word in ("lcb", "LCB", "g:", "x:PXR", "rule_h"):
            self.assertNotIn(word, report)
            self.assertNotIn(word, json.dumps([r["why"] for r in intents]))
        self.assertIn("META: EVL-META-O1 live/ok", report)

    def _seed_state(self, prog):
        MT.ensure(self.w.st)
        days = [s.day for s in C.previous(self.w.st, D_DAY, 13)]
        for k, day in enumerate(days):
            for i in range(20):
                event = f"news:seed-{k}-{i}"
                cik = str(5000 + i)
                good = i < 5
                self.w.st.db.execute("INSERT INTO mrl_pool(program, version, day, cik, symbol, event, knowable_at, tags, "
                                     "features, xrules, eligible, adv20, prev_close, cost_rt) VALUES(?, 1, ?, ?, ?, ?, ?, "
                                     "?, ?, '[]', 1, 1e8, 20, 0.0014)",
                                     (prog.id, day.isoformat(), cik, f"S{i}", event, S.iso(et(day, 7, 0)),
                                      json.dumps(["EVL-CTRL-NEWS-ALL-O1:1"]),
                                      json.dumps(["news-on", "adv>=100M"] if good else ["news-on", "adv<10M"])))
                self.w.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                                     "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES("
                                     "'EVL-CTRL-NEWS-ALL-O1', 1, ?, ?, ?, 'x', ?, 'open', ?, 'close', NULL, 'shadow', "
                                     "'exited', NULL)", (event, f"S{i}", cik, day.isoformat(), day.isoformat()))
                self.w.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, 'open', "
                                     "20, 't', 'sip', 'x')", (f"S{i}", day.isoformat()))
                self.w.st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, "
                                     "sigma60) VALUES(?, ?, ?, 'n', 'NASDAQ', 20, 1e8, 'SPY', NULL)",
                                     (day.isoformat(), f"S{i}", cik))
                self.w.st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                                     "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) "
                                     "VALUES('EVL-CTRL-NEWS-ALL-O1', 1, ?, 20, 21, 'SPY', 1, 1, 7, 7, ?, 0, ?, 1, ?, "
                                     "'settled')", (event, 0.03 if good else -0.01, 0.03 if good else -0.01,
                                                     S.iso(et(day, 20, 30))))
        # today's members whose features match the good rule: articles stored before tau that the lane's news control
        # takes at D's open by its real-money reading (book.picks at tau, the members rule), eligible
        for i in range(5):
            cik, sym = str(6000 + i), f"T{i}"
            event = f"news:today-{i}"
            self.w.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                                 "summary, symbols, live) VALUES(?, ?, ?, ?, ?, 'benzinga', 'h', 's', ?, 1)",
                                 (f"today-{i}", S.iso(et(D_DAY, 6, 58)), S.iso(et(D_DAY, 6, 58)), S.iso(et(D_DAY, 7, 0)),
                                  S.iso(et(D_DAY, 7, 0)), json.dumps([sym])))
            self.w.st.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) "
                                 "VALUES(?, ?, ?, 'n', 'NASDAQ', 20, 1e8, 'SPY', NULL)", (D_DAY.isoformat(), sym, cik))
            self.w.st.db.execute("INSERT INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, 'live', "
                                 "1, ?, ?)", (D_DAY.isoformat(), cik, sym, S.iso(et(D_DAY, 9, 15, 10))))


class TheReportsCounts(WorldCase):
    """Section 10's lines beside the PX and META blocks: the late passes that did not come (the book's own rows), the
    one-mechanism pairs (from band_history and intents only) and the auctions lost to a late morning pass."""

    def test_the_late_passes_from_the_books_rows(self):
        import sqlite3

        self.assertIsNone(RP.late_passes_8(self.w.st, D_DAY), "no live.sqlite: no book on this House")
        path = Path(self.w.st.root).parent / "live.sqlite"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE eq_event_decisions(day TEXT, at TEXT, decided_at TEXT, status TEXT, summary TEXT, "
                   "created_at REAL, PRIMARY KEY(day, at))")
        db.execute("INSERT INTO eq_event_decisions VALUES(?, 'open-px8', 'x', 'done', '{}', 0)", (D_DAY.isoformat(),))
        db.execute("INSERT INTO eq_event_decisions VALUES(?, 'close-px8', 'x', 'failed', '{}', 0)", (D_DAY.isoformat(),))
        db.commit()
        db.close()
        self.assertEqual(RP.late_passes_8(self.w.st, D_DAY),
                         {"open-px8": "planned", "close-px8": "failed", "close-meta8": "not come"})

    def test_one_mechanism_pairs(self):
        st = self.w.st
        days = [s.day for s in C.sessions(st, dt.date(2026, 8, 3), N_DAY)]
        self.assertGreater(len(days), 60)

        def promote(pid, day):
            st.db.execute("INSERT INTO band_history(program, version, band, since, why, written_at) VALUES(?, 1, 'probe', "
                          "?, 'x', ?)", (pid, S.iso(et(day, 21, 0)), S.iso(et(day, 21, 0))))
        self.assertEqual(S8.one_mechanism(st), {"pairs": [], "count": 0})
        promote("PX-DROP-ON", days[30])
        promote("PX-SURGE-ON", days[45])
        promote("PX-GAP-O1", days[60])
        self.assertEqual(S8.one_mechanism(st)["pairs"], [["PX-DROP-ON", "PX-SURGE-ON"], ["PX-SURGE-ON", "PX-GAP-O1"]])
        promote("EVL-META-ON", days[35])
        for i, day in enumerate(days[:20]):
            for pid in ("EVL-META-ON",) + (("PX-DROP-ON",) if i < 11 else ()):
                st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                              "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 1, ?, 'S', '77', 'x', ?, 'close', "
                              "?, 'open', 1, 'shadow', 'exited', NULL)", (pid, f"e:{pid}:{day}", day.isoformat(),
                                                                          day.isoformat()))
        pairs = S8.one_mechanism(st)["pairs"]
        self.assertIn(["EVL-META-ON", "PX-DROP-ON"], pairs, "11 of 20 picks PX-sourced: one mechanism with PX-DROP-ON")
        self.assertIn(["EVL-META-ON", "PX-SURGE-ON"], pairs)
        st.db.execute("DELETE FROM intents WHERE program='PX-DROP-ON' AND entry_day=?", (days[0].isoformat(),))
        self.assertNotIn(["EVL-META-ON", "PX-DROP-ON"], S8.one_mechanism(st)["pairs"], "10 of 20: not more than half")

    def test_auctions_lost_to_a_late_morning_pass(self):
        px = self.px()
        PXL.morning(px, self.w.st, self.w.gw, D_DAY, now=et(D_DAY, 11, 0), run="am", clock=lambda: et(D_DAY, 11, 0, 5))
        self.assertEqual(PXL.report_lines(self.w.st, self.w.st.root, D_DAY)["auctions_lost_am"], 1)
        self.assertEqual(PXL.report_lines(self.w.st, self.w.st.root, N_DAY)["auctions_lost_am"], 2)
        self.morning(N_DAY)
        self.assertEqual(PXL.report_lines(self.w.st, self.w.st.root, N_DAY)["auctions_lost_am"], 0)


# ================================================================================================ the wall and the docs
class TheWall(unittest.TestCase):
    def test_behind_the_updaters_wall(self):
        for path in ("league/events/px.py", "league/events/px_grid8.json", "league/events/meta.py",
                     "league/events/screen8.py"):
            self.assertIn(path, ci.FORBIDDEN)
            self.assertIn(path, ci.PENDING_GATEWAY)

    def test_standard_library_only(self):
        import ast
        root = Path(__file__).resolve().parents[1] / "events"
        allowed = set(__import__("sys").stdlib_module_names)
        for name in ("px.py", "meta.py", "screen8.py"):
            tree = ast.parse((root / name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name.split(".")[0], allowed, name)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(str(node.module).split(".")[0], allowed, name)


if __name__ == "__main__":
    unittest.main()
