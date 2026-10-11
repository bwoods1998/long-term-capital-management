"""THE DONE METER WITH EQUITY ROWS (release E1; league/ops/dlane_report.py, the captain's design 6d and A8.6, A8.12, A9;
the goal of Oct 10, 2026): an equity close is one EquityBook lot fully closed, its net cash with fees and dividends,
counted on both meters from Oct 10, 2026 with every earlier close reported beside; it is matched to its own closed-form
twin; beside every close and checkpoint ride its lane's label, the same-risk buy-and-hold, MTE, the screen's line and
"profit from market direction"; Done is read with and without the three seeded programs; A8.6's statement about the
options Probe lane's room. The Done rule itself is unchanged.

Every figure is invented. The equity tables are league/equity/live.py's `SCHEMA` (the book's); the twin records are the
shape league/ops/twins.py `equity_twin` writes (its own tests hold how they are made)."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from league.ops import dlane_report as R
from league.ops import twins as TW
from league.swarm import dlane, elane
from league.tests.test_dlane_report import GATE, Fixture, ny
from league.tests.test_equity_twins import add_tables, lot, put_lot

SESSIONS_AFTER = ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]


class EquityFixture(Fixture):
    def setUp(self):
        super().setUp()
        add_tables(self.live)
        self.lid = 0

    def eq_family(self, fid: str, *, lane: str = "beta", band: str = "probe") -> None:
        # An equity-lane family declares its lane and an equity structure together (the swarm's add_family).
        spec = {"id": fid, "mechanism": "a published overnight prior long enough for the store", "structure": "etf",
                "roots": ["SPY"], "lane": lane}
        self.store.add_family(spec, origin="architect")
        if band != "gym":
            self.store.set_band(fid, band, reason="fixture")

    def eq_close(self, family: str, *, day: str = "2026-10-13", exit_day: str = "2026-10-14", cash: str = "1.00",
                 notional: str = "100.00", lane: str = "beta", version: int = 1, posted: bool = False,
                 closed_at: float | None = None, **kw) -> int:
        self.lid += 1
        row = lot(self.lid, family=family, version=version, lane=lane, notional=notional, cash=cash, opened_day=day,
                  exit_day=exit_day, closed_at=closed_at, info=json.dumps({"fee_basis": "broker"} if posted else {}), **kw)
        put_lot(self.live, row)
        return self.lid

    def twin(self, lid: int, *, live_r: float, twin_r: float, notional: float = 100.0, bh: float = 0.5,
             status: str = "priced") -> None:
        records = TW.equity_records(self.store)
        records[f"eq:{lid}"] = {"key": f"eq:{lid}", "lid": lid, "status": status, "final": True,
                                "live_return": live_r, "twin_return": twin_r,
                                "gap_bp": round((live_r - twin_r) / 2 * 1e4, 2),
                                "twin": {"pnl": round(twin_r * notional, 2), "max_loss": notional, "r": twin_r,
                                         "exit": "close"} if status == "priced" else None,
                                "live": {"exit": "close"}, "exit_agrees": True,
                                "bh": {"usd": bh, "return": round(bh / notional, 6)} if status == "priced" else None}
        self.store.put(TW.EQUITY_TWINS_KEY, records)

    def report(self, settings=GATE, previous=None) -> dict:
        return R.report(self.root, settings=settings, now=self.now, previous=previous)


class TheCount(EquityFixture):
    def test_equity_closes_count_on_both_meters_from_oct_10_and_earlier_closes_ride_beside(self):
        self.fam("dir-a", lane="direction")
        self.close("dir-a", route=":t", pnl=-157.10, day="2026-10-06", closed_at=ny("2026-10-08", 15, 0))
        self.close("dir-a", route=":r", pnl=4.0, day="2026-10-13", closed_at=ny("2026-10-15", 11, 0))
        self.eq_family("seed-overnight-spy")
        a = self.eq_close("seed-overnight-spy", cash="1.25")
        self.eq_close("seed-overnight-spy", cash="-0.40", day="2026-10-14", exit_day="2026-10-15")
        out = self.report()
        done = out["done"]
        self.assertEqual(done["counted_from"], R.DONE_FROM)
        self.assertEqual(done["counted_from"], "2026-10-10T04:00:00Z", "00:00 New York, the goal's Oct 10")
        run_all, run_screen = done["all"]["running"], done["screen"]["running"]
        self.assertEqual((run_all["closes"], run_screen["closes"]), (3, 3))
        self.assertEqual(run_all["net_usd"], round(4.0 + 1.25 - 0.40, 2))
        # The tuition close of Oct 8 is reported beside, never counted.
        self.assertEqual([c["pnl_usd"] for c in done["earlier"]["closes"]], [-157.10])
        self.assertEqual(done["earlier"]["net_usd"], -157.10)
        rows = {c["pid"]: c for c in done["all"]["closes"]}
        eq = rows[f"eq:{a}"]
        self.assertEqual((eq["route"], eq["lane"], eq["label"], eq["fee_basis"]), (":r", "beta", "MARKET BETA", "estimate"))
        # The program's row carries its lane's label; the rule is the pinned one.
        programs = {p["family"]: p for p in run_all["by_program"]}
        self.assertEqual((programs["seed-overnight-spy"]["lane"], programs["seed-overnight-spy"]["label"]),
                         ("beta", elane.LABELS["beta"]))
        self.assertEqual(out["rule"]["sha256"], dlane.DONE["rule_sha256"])
        self.assertEqual(done["all"]["next_checkpoint"], dlane.DONE["first_checkpoint"])

    def test_a_lot_still_open_or_closing_is_no_close_and_another_route_is_listed_apart(self):
        self.eq_family("seed-overnight-spy")
        self.eq_close("seed-overnight-spy")
        self.lid += 1
        put_lot(self.live, lot(self.lid, family="seed-overnight-spy", status="closing", cash="0"))
        self.lid += 1
        put_lot(self.live, lot(self.lid, family="seed-overnight-spy", route=":p"))
        out = self.report()
        self.assertEqual(out["done"]["all"]["running"]["closes"], 1)
        self.assertEqual([c["pid"] for c in out["done"]["other_routes"]], [f"eq:{self.lid}"])
        self.assertEqual(out["equity"]["open_lots"], 1)

    def test_a_frozen_reading_is_carried_only_from_the_same_count_start(self):
        old = {"done": {"all": {"checkpoints": [{"at_close": 30, "final": True, "holds": True}]},
                        "screen": {"checkpoints": [{"at_close": 30, "final": True, "holds": True}]}}}
        self.eq_family("p")
        for _ in range(31):
            self.eq_close("p")
        out = self.report(previous=old)
        self.assertNotIn("frozen", out["done"]["all"]["checkpoints"][0], "a report from before the move is not carried")
        again = self.report(previous=out)
        self.assertEqual(again["done"]["counted_from"], out["done"]["counted_from"])


class TheTwinsAndFinality(EquityFixture):
    def test_each_close_is_matched_to_its_own_twin_and_final_only_once_it_and_its_fees_are(self):
        self.eq_family("p-a")
        self.eq_family("p-b")
        lids = [self.eq_close(f, cash="1.00", posted=True) for f in ("p-a", "p-b") for _ in range(5)]
        for lid in lids:
            self.twin(lid, live_r=0.01, twin_r=0.012)
        out = self.report()
        programs = {p["family"]: p for p in out["done"]["all"]["running"]["by_program"]}
        self.assertEqual((programs["p-a"]["replay"]["matched"], programs["p-a"]["replay"]["twinned"]), (5, 5))
        self.assertAlmostEqual(programs["p-a"]["replay"]["gap"], 0.01 - 0.012, places=4)
        self.assertTrue(programs["p-a"]["replay"]["consistent"])
        fin = R.finality([c for c in self.closes_of(out)], replay_days={}, fees_as_of=None,
                         twins=TW.equity_records(self.store))
        self.assertTrue(fin["final"], fin)
        # With no twin record an equity close's replay has not landed (no nightly replay to fall back on), whatever the
        # options twins' switch says; with its fees not marked posted by the book, they are pending too.
        rows = [{"pid": "eq:99", "equity": True, "fees_posted": False, "pnl_usd": Decimal("1"), "day": "2026-10-14",
                 "family": "p-a"}]
        fin = R.finality(rows, replay_days={}, fees_as_of="2026-10-20", twins={}, twins_on=False)
        self.assertEqual((fin["final"], fin["pending_twin"], fin["pending_fees"]), (False, 1, 1))

    def test_a_final_unpriced_twin_is_counted_apart_never_matched(self):
        self.eq_family("p-a")
        lid = self.eq_close("p-a")
        self.twin(lid, live_r=0.01, twin_r=0.0, status="no_bar")
        out = self.report()
        replay = out["done"]["all"]["running"]["by_program"][0]["replay"]
        self.assertEqual((replay["matched"], replay["twin_unpriced"]), (0, {"no_bar": 1}))

    @staticmethod
    def closes_of(out):
        return [{"pid": c["pid"], "equity": True, "fees_posted": c["fee_basis"] == "broker", "pnl_usd": c["pnl_usd"],
                 "day": "2026-10-14", "family": c["family"]} for c in out["done"]["all"]["closes"]]


class WhatRidesBeside(EquityFixture):
    def test_buy_and_hold_mte_label_screen_and_direction_ride_beside_every_close_and_checkpoint(self):
        self.eq_family("p-a")
        self.eq_family("p-b", lane="equity")
        self.store.add_look("p-a", 1, "sha-a", passed=True, p_value=None,
                            detail={"screen": "S1", "lane": "beta", "c_used": 1.23, "own_fp": 0.11, "label": "beta",
                                    "beside": "S1-R per-program FP at zero edge 11% (invented line)"})
        lids = []
        for i in range(30):
            fam = "p-a" if i % 2 == 0 else "p-b"
            lids.append(self.eq_close(fam, cash="2.00", lane="beta" if fam == "p-a" else "equity",
                                      closed_at=ny("2026-10-14", 15, 56) + i))
        for lid in lids:
            self.twin(lid, live_r=0.02, twin_r=0.021, bh=1.5)
        out = self.report()
        close = out["done"]["all"]["closes"][0]
        self.assertEqual(close["bh"]["delta_usd"], 1.5)
        self.assertEqual(close["mte"], round(0.02 - 0.015, 6))
        self.assertEqual((close["label"], close["seeded"]), ("MARKET BETA", False))
        self.assertEqual(close["fp"]["beside"], "S1-R per-program FP at zero edge 11% (invented line)")
        self.assertEqual(close["fp"]["own_fp"], 0.11)
        other = next(c for c in out["done"]["all"]["closes"] if c["family"] == "p-b")
        self.assertIsNone(other["fp"]["beside"])
        self.assertIn("no screen line", other["fp"]["fp_why"])
        self.assertIsNone(other["fp"]["screen"], "no look recorded: no screen is assumed")
        checkpoint = out["done"]["all"]["latest"]
        self.assertEqual(checkpoint["at_close"], 30)
        beside = checkpoint["equity"]
        self.assertEqual(beside["direction"], R.EQUITY_DIRECTION)
        self.assertIn("Profit from market direction", beside["direction"])
        self.assertEqual(set(beside["by_lane"]), {"beta", "equity"})
        self.assertEqual((beside["by_lane"]["beta"]["label"], beside["by_lane"]["equity"]["label"]),
                         ("MARKET BETA", "EQUITY"))
        self.assertEqual((beside["by_lane"]["beta"]["bh_usd"], beside["by_lane"]["beta"]["mte_mean"]), (22.5, 0.005))
        self.assertIn("equity_basis", checkpoint["bh"])
        self.assertEqual(out["done"]["all"]["running"]["equity"]["closes"], 30)
        # The equity section lists each close and the twins' gaps; the FP line rides beside each trade too.
        section = out["equity"]
        self.assertEqual(len(section["closes"]), 30)
        self.assertTrue(all(c["counted"] for c in section["closes"]))
        self.assertEqual(section["twins"]["by_status"], {"priced": 30})
        self.assertEqual(section["twins"]["mean_gap_bp"]["p-a"], round((0.02 - 0.021) / 2 * 1e4, 2))
        rows = out["fp_beside_trades"]["closes"]
        self.assertEqual({r["screen"] for r in rows if r["family"] == "p-a"}, {"S1"})
        self.assertEqual(len(out["fp_beside_trades"]["equity_trades"]), 30)

    def test_a_look_judged_by_s2_rides_beside_as_s2s(self):
        """A11: the House screen is S2. The row beside a trade names the screen that judged its program's look and
        carries that verdict's figures (c_H = c_H,used, c_pF1, the own FP, the holdout-only and drift-kept rates)."""
        self.eq_family("p-s2")
        line = "S2, c_R = 0 (no pooled-t bar), c_H,used = 1.07; this program's FP at zero edge = 3.10% (invented line)"
        self.store.add_look("p-s2", 1, "sha-s2", passed=True, p_value=None,
                            detail={"screen": "S2", "lane": "beta", "receipt": "r" * 64, "c_pF1": 1.02, "c_H": 1.07,
                                    "s1x": "beta", "beside": line, "passed": True})
        self.store.set_state("p-s2", elane_look={"version": 1, "at": "2026-10-11T12:00:00Z", "beside": line,
                                                 "verdict": {"screen": "S2", "passed": True, "c_R": 0.0, "c_pF1": 1.02,
                                                             "c_H": 1.07, "own_fp": 0.031, "holdout_only": 0.094,
                                                             "drift_kept": 0.21, "label": "beta", "fp_x": 0.04}})
        row = R.EquityScreens(self.store).of("p-s2", 1)
        self.assertEqual((row["screen"], row["beside"], row["receipt"]), ("S2", line, "r" * 64))
        self.assertEqual((row["c_R"], row["c_pF1"], row["c_H"], row["own_fp"], row["holdout_only"], row["drift_kept"],
                          row["s1x"], row["fp_x"]), (0.0, 1.02, 1.07, 0.031, 0.094, 0.21, "beta", 0.04))
        self.assertNotIn("label", row, "S1-X's label is `s1x`; the lane's is `lane_label` (never one ambiguous `label`)")
        self.assertEqual((row["c_used"], row["c_p"]), (None, None), "S2 has no pooled-t bar")
        self.assertNotIn("fp_why", row)
        self.assertIn("no screen line", R.EquityScreens(self.store).of("p-s2", 2)["fp_why"], "another version: no look")

    def test_a14s_pre_registered_text_rides_in_every_report_and_in_the_operators_page(self):
        """A14 (the captain's pre-registration, before the first equity close): Done's "fills consistent" reading (15
        bp a side AND 95% of the counted sessions, at each checkpoint), the close-date figures beside every reading
        and the inactive forward seat rule are in the report, verbatim, and in docs/operations.md in the same words;
        the status says plainly what is computed (the fill-gap half) and what is not (the intents half, the
        close-date figures, the seat rule)."""
        import re
        from pathlib import Path

        self.eq_family("seed-overnight-spy")
        self.eq_close("seed-overnight-spy")
        pre = self.report()["done"]["preregistered"]
        self.assertEqual(pre, R.PREREGISTERED)
        self.assertEqual((pre["id"], pre["registered"], pre["consistency"], pre["beside_done"], pre["forward_seat_rule"]),
                         ("A14", "2026-10-10", R.A14_CONSISTENCY, R.A14_BESIDE_DONE, R.A14_SEAT_RULE))
        for words in ("live fills consistent with their replay", "at each Done checkpoint", "at most 15 bp a side",
                      "official-price model", "at least 95% of the counted sessions", "not consistent"):
            self.assertIn(words, R.A14_CONSISTENCY)
        for words in ("distinct close dates", "date-clustered t"):
            self.assertIn(words, R.A14_BESIDE_DONE)
        for words in ("written and inactive", "fewer than 5 real closes", "never unseated", "except by EDM1"):
            self.assertIn(words, R.A14_SEAT_RULE)
        for words in ("partly computed", "fill-gap half is computed", "intents-agreement half has no reader yet",
                      "does not hold", "No reading carries the close-date figures"):
            self.assertIn(words, pre["status"])
        page = re.sub(r"\s+", " ", (Path(R.__file__).resolve().parents[2] / "docs" / "operations.md").read_text())
        for sentence in (R.A14_CONSISTENCY, R.A14_BESIDE_DONE, R.A14_SEAT_RULE):
            self.assertIn(sentence, page)
        self.assertIn("A14", page)
        # The pinned Done rule is not this text's to change.
        self.assertEqual(self.report()["rule"]["sha256"], dlane.DONE["rule_sha256"])

    def test_done_is_read_with_and_without_the_three_seeded_programs(self):
        for fid in ("seed-overnight-spy", "agent-one"):
            self.eq_family(fid)
        self.store.put(elane.SEEDS_KEY, {"seed-overnight-spy": "seed-overnight-spy"})
        for _ in range(3):
            self.eq_close("seed-overnight-spy", cash="5.00")
        self.eq_close("agent-one", cash="-1.00")
        out = self.report()
        self.assertEqual(out["done"]["all"]["running"]["closes"], 4)
        without = out["done"]["without_seeded"]
        self.assertEqual(without["seeded"], ["seed-overnight-spy"])
        self.assertEqual(without["note"], elane.SEEDED_NOTE)
        self.assertEqual((without["all"]["running"]["closes"], without["all"]["running"]["net_usd"]), (1, -1.0))
        self.assertTrue(next(c for c in out["done"]["all"]["closes"] if c["family"] == "seed-overnight-spy")["seeded"])
        # The book's own mark counts as seeded too.
        self.live.upsert("eq_instances", {"id": "agent-one@1:r", "family": "agent-one", "version": 1, "lane": "beta",
                                          "run_sha": "r", "code": "", "params": "{}", "band": "probe", "seeded": 1,
                                          "max_hold": 20, "created_at": self.now}, "id")
        out = self.report()
        self.assertEqual(out["done"]["without_seeded"]["all"]["running"]["closes"], 0)


class TheFunnelAndTheBudget(EquityFixture):
    def test_the_funnel_and_the_bands_have_equity_rows(self):
        self.eq_family("born-beta")
        self.store.event("swarm.born", "born-beta", {"lane": "beta"})
        self.eq_close("born-beta", closed_at=self.now - 3600)
        self.lid += 1
        put_lot(self.live, {**lot(self.lid, family="born-beta", status="open", cash="0"), "opened_at": self.now - 7200})
        out = self.report()
        day = out["funnel"]["24h"]
        self.assertEqual(day["beta"]["births"], 1)
        self.assertEqual(day["beta"]["real_closes"][":r"], 1)
        self.assertEqual(day["beta"]["real_opens"][":r"], 1)
        self.assertEqual(day["alpha"]["births"], 0, "an equity birth is not the alpha lane's")
        self.assertEqual(out["bands_now"]["beta"]["probe"], 1)

    def test_the_shared_budget_leaves_the_options_probe_lane_little_room_a8_6(self):
        """The lane holds the LOWER of its Probe sleeves and the invested cap. Since the captain's A20 (the sleeves at
        0.50 x E) three whole sleeves ask for 1.50 x E, so the invested cap's 1.00 x E is the bound: 0.20 x E of open
        risk at most (three one-ETF programs, a lot of 0.25 x E each, hold 0.15 x E of it; the note says both)."""
        from league.constitution import CONSTITUTION

        constitution = {"options_money": {"probe": {"loss_budget_usd": "400"}},
                        "equity_money": {"probe": {"sleeve_share": "0.50", "max_programs": 3}, "invested_share": "1.00",
                                         "open_risk_weight": {"etf": "0.20", "stock": "0.40"}}}
        em, probe = CONSTITUTION["equity_money"], CONSTITUTION["options_money"]["probe"]
        self.assertEqual((em["probe"]["sleeve_share"], em["probe"]["max_programs"], em["invested_share"],
                          em["open_risk_weight"]["etf"], probe["loss_budget_usd"]), ("0.50", 3, "1.00", "0.20", "400"),
                         "the fixture is the table in force")
        room = R.options_probe_room(2000, constitution)
        self.assertEqual(room, R.options_probe_room(2000), "and the table in force is read when none is passed")
        self.assertEqual((room["open_risk_share_of_e"], room["invested_share_of_e"], room["bound"]),
                         (0.2, 1.0, "invested_cap"))
        self.assertEqual((room["equity_open_risk_usd"], room["options_window_room_usd"]), (400.0, 0.0))
        room = R.options_probe_room(1000, constitution)
        self.assertEqual((room["equity_open_risk_usd"], room["options_window_room_usd"], room["bound"]),
                         (200.0, 200.0, "invested_cap"))
        # Past E = $2,000 the window itself is the bound: every equity entry is cut to the budget's room.
        room = R.options_probe_room(3000, constitution)
        self.assertEqual((room["open_risk_share_of_e"], room["equity_open_risk_usd"], room["options_window_room_usd"],
                          room["bound"]), (0.2, 400.0, 0.0, "budget"))
        # Sleeves that fit under the invested cap bind by themselves (the quarter of E the block carried before A20).
        quarter = {**constitution, "equity_money": {**constitution["equity_money"],
                                                     "probe": {"sleeve_share": "0.25", "max_programs": 3}}}
        room = R.options_probe_room(2000, quarter)
        self.assertEqual(room["open_risk_share_of_e"], 0.15)
        self.assertEqual((room["equity_open_risk_usd"], room["options_window_room_usd"], room["bound"]),
                         (300.0, 100.0, "sleeves"))
        # A table with no invested_share row is read by its sleeves alone: the larger risk, never a smaller one.
        bare = {**constitution, "equity_money": {k: v for k, v in constitution["equity_money"].items()
                                                  if k != "invested_share"}}
        room = R.options_probe_room(1000, bare)
        self.assertEqual((round(room["open_risk_share_of_e"], 6), room["equity_open_risk_usd"],
                          room["options_window_room_usd"], room["bound"], room["invested_share"]),
                         (0.3, 300.0, 100.0, "sleeves", None))
        self.assertEqual(room["statement"], R.EQUITY_PROBE_NOTE)
        self.assertIn("effectively off", R.EQUITY_PROBE_NOTE)
        self.assertIn("3 x 0.50 E", R.EQUITY_PROBE_NOTE)
        self.assertIn("at most 0.20 x E", R.EQUITY_PROBE_NOTE)
        self.assertIn("three one-ETF programs hold a lot of 0.25 x E each, 0.15 x E of open risk", R.EQUITY_PROBE_NOTE)
        self.assertIn("$400 less its realized loss less 0.20 x the equity lots", R.EQUITY_PROBE_NOTE)
        self.assertIn("why", R.options_probe_room(2000, {"options_money": {"probe": {"loss_budget_usd": "400"}}}))
        self.assertIn("why", R.options_probe_room(None, constitution))
        self.assertEqual(self.report()["equity"]["options_probe_room"]["statement"], R.EQUITY_PROBE_NOTE)

    def test_a_book_from_before_e1_reads_as_no_equity(self):
        from league.live.state import LiveState

        self.live.close()
        (self.root / "live.sqlite").unlink()
        for suffix in ("-wal", "-shm"):
            (self.root / f"live.sqlite{suffix}").unlink(missing_ok=True)
        old = LiveState(self.root / "live.sqlite")
        self.addCleanup(old.close)
        book = R.read_book(self.root / "live.sqlite")
        self.assertEqual((book["lots"], book["eq_instances"]), ([], []))
        out = self.report()
        self.assertEqual((out["equity"]["closes"], out["equity"]["open_lots"]), ([], 0))
        self.assertIsNone(out["done"]["all"]["running"]["equity"])


class TheResearchFunnel(EquityFixture):
    """league/ops/funnel.py: the equity lanes' counts apart (`equity`), which the daily page's table does not read."""

    def test_births_validations_looks_moves_bands_and_the_book_by_equity_lane(self):
        from league.equity import LANES
        from league.ops import funnel as FN

        self.assertEqual(FN.EQUITY_LANES, LANES)
        self.eq_family("born-beta")
        self.eq_family("born-equity", lane="equity", band="candidate")
        self.fam("dir-a", lane="direction")
        self.store.event("swarm.born", "born-beta", {"lane": "beta"})
        self.store.event("swarm.born", "born-equity", {})
        self.store.event("swarm.born", "dir-a", {"lane": "direction"})
        # An equity verdict is the equity rounds' own event (`elane.validate`); the hourly tournament row holds options
        # families only, so an equity id in it is never read as an equity verdict.
        self.store.event("swarm.tournament", None, {"validation": {"judged": {"born-equity": {"passed": True},
                                                                              "dir-a": {"passed": False}}}})
        self.store.event("swarm.status", "born-beta", {"action": "elane_validation", "version": 1, "lane": "beta",
                                                       "entered": True})
        self.store.event("swarm.status", "born-beta", {"action": "elane_validation_error", "version": 1, "lane": "beta"})
        self.store.add_look("born-beta", 1, "sha-1", passed=True, p_value=None, detail={"screen": "S1"})
        self.eq_close("born-beta", closed_at=self.now - 600)
        self.lid += 1
        put_lot(self.live, {**lot(self.lid, family="born-beta", status="open", cash="0"), "opened_at": self.now - 300})
        self.live.upsert("eq_orders", {"eid": 1, "client_id": "lq-1-born-beta", "instance": "born-beta@1:r",
                                       "family": "born-beta", "side": "buy", "symbol": "SPY", "class": "etf", "at": "open",
                                       "qty": "0.5", "limit_px": "100", "collar_bp": 10, "status": "filled",
                                       "placed_at": self.now - 900, "day": "2026-10-20", "filled_qty": "0.5",
                                       "updated_at": self.now - 800}, "eid")
        out = FN.window(self.root, self.now - 86400, self.now + 1)
        self.assertEqual(out["errors"], {})
        eq = out["equity"]
        self.assertEqual((eq["beta"]["births"], eq["equity"]["births"]), (1, 1))
        self.assertEqual(eq["beta"]["validations"], {"judged": 1, "passed": 1})
        self.assertEqual(eq["equity"]["validations"], {"judged": 0, "passed": 0})
        self.assertEqual(eq["beta"]["looks"], {"taken": 1, "passed": 1})
        self.assertEqual((eq["beta"]["band_moves"]["probe"], eq["equity"]["band_moves"]["candidate"]), (1, 1),
                         "the fixture's band moves (`set_band`)")
        self.assertEqual(out["births"], 3, "every birth is still in the funnel's own count")
        book = out["book"]["equity"]
        self.assertEqual((book["orders"], book["filled"], book["programs_holding"]), (1, 1, 1))
        self.assertEqual((book["opens"]["beta"], book["closes"]["beta"]), (1, 1))
        bands = FN.guard.read(self.root / FN.SWARM_DB, FN.bands_now)
        self.assertEqual((bands["equity"]["beta"]["probe"], bands["equity"]["equity"]["candidate"]), (1, 1))

    def test_a_book_from_before_e1_has_no_equity_counts(self):
        from league.ops import funnel as FN

        self.live.db.execute("DROP TABLE eq_lots")
        self.assertNotIn("equity", FN.book_counts(self.root, self.now - 86400, self.now))


if __name__ == "__main__":
    unittest.main()
