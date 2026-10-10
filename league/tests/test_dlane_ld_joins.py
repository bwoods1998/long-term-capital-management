"""THE JOINS between release L-D (deployed 09:04Z Oct 9, 2026: the Probe budget read NET, THE ROLLING PROBE BUDGET, DM1)
and releases D-1 and D-1b (the direction lane), checked on the merged tree rather than trusted to a clean merge:

1. THE SIGMA, end to end: the figure `league/swarm/tournament.py` writes (`Tournament.sigma_fields`, D-1's writer:
   `validation_r_sd_by_version` {str(version): sd} and `validation_r_sd` for `validation_version`) is the one
   `league/live/families.py` (`SwarmFamilies.read`, L-D's reader) puts into the band row, and the one DM1 then reads
   (`money.dm1_sigma`); `confirm_band` holds it.
2. THE PROBE ENVELOPE of the `dlane` report (`league/ops/dlane_report.py` `probe_envelope`) reads release L-D's two
   envelopes from the constitution through `money.Table` (`loss_basis`, `loss_budget_usd` over `loss_window_sessions`,
   `loss_total_usd`, `max_open`, `demotion`) and `real.probe_figures` told each basis by name: the window's worst net
   stretch and the total, the room the tighter envelope leaves, the binding one; alarm A4 reads that room. Under the
   CON-only rollback (fast lane v2's rows) it is D-1's single envelope again.

Every figure is invented."""

from __future__ import annotations

import copy
import dataclasses
import math
import types
import unittest
from unittest import mock

from league.constitution import CONSTITUTION
from league.live import money as M
from league.ops import dlane_report as R
from league.swarm import dlane
from league.swarm.tournament import Tournament
from league.tests.money_fakes import FAST_LANE_V2
from league.tests.swarm_fakes import result
from league.tests.test_dlane_report import Fixture, ny
from league.tests.test_swarm_rounds import RoundCase

try:  # the live book's figures need numpy (the Gym's legs), as the House box has
    import numpy  # noqa: F401

    HAVE = True
except ImportError:  # pragma: no cover - CI has numpy
    HAVE = False


# ============================================================================================== 1. the sigma, end to end
class TheSigmaEndToEnd(RoundCase):
    """D-1's writer and L-D's reader agree on the keys, the version and the value, through the real store."""

    def families(self):
        from league.live.families import SwarmFamilies

        fams = SwarmFamilies(self.root)
        self.addCleanup(lambda: fams._store.close() if fams._store is not None else None)
        return fams

    def band_at_probe(self, fid: str, n: int) -> None:
        from league.tests.evaluator_fakes import band_proof

        self.store.set_state(fid, banded_version=n, banded_evaluator=band_proof(self.store.version(fid, n)))
        self.store.set_band(fid, "probe", reason="passed the holdout")

    def test_the_figure_the_tournament_writes_is_the_one_the_band_row_carries_and_dm1_reads(self):
        self.settings = copy.deepcopy(self.settings)
        self.settings["dlane"] = {"mode": "gate"}
        self.family("a", structure="debit_vertical")
        tour = Tournament(self.store, self.pool, self.settings)
        tour.judge("a", 1, self.answer(types.SimpleNamespace(window="validation", name="a", family="a", stress=1.0)),
                   record=True)
        state = self.store.family("a")["state"]
        summary = self.store.version_runs("a", 1, window="validation", stress=1.0, limit=1)[0]["summary"]
        want = abs(summary["mean_return_on_max_loss"]) * math.sqrt(summary["trades"]) / abs(summary["t_stat"])
        written = state["validation_r_sd"]
        self.assertAlmostEqual(written, want, places=5)
        self.assertEqual(state["validation_r_sd_by_version"], {"1": written}, "the writer's keys: str(version) -> sd")
        self.assertEqual(state["validation_version"], 1)
        self.assertIsInstance(written, float)
        self.assertTrue(math.isfinite(written) and written > 0)

        self.band_at_probe("a", 1)
        fams = self.families()
        [row] = [r for r in fams.read() if r["family"] == "a"]
        self.assertEqual((row["band"], row["version"]), ("probe", 1))
        self.assertEqual(row["validation_r_sd"], written, "L-D's reader puts the writer's exact figure in the band row")
        sigma, source = M.dm1_sigma(M.forward_stats([], 0.8, version=1), row["validation_r_sd"])
        self.assertEqual(sigma, written)
        self.assertIn("Validation run", source, "DM1 reads the Validation sd, not the forward record's or the fallback")
        self.assertTrue(fams.confirm_band(row, "probe", "unchanged", fams.forward_rows("a")), "the band confirms on it")

        # A newer version whose Validation sd is not finite and above zero: the writer omits it, and the banded version's
        # own figure is still the one its row carries (the per-version map, never the newer version's scalar).
        v2 = self.store.add_version("a", "# a v2\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n",
                                    {}, author="seed")
        self.store.update_family("a", best_version=v2["n"])
        bad = result("a-v2", window="validation", t=-1.0)
        self.assertIsNone(dlane.validation_r_sd(bad["summary"]))
        tour.judge("a", v2["n"], bad, record=True)
        state = self.store.family("a")["state"]
        self.assertEqual(state["validation_version"], v2["n"])
        self.assertIsNone(state["validation_r_sd"])
        [row] = [r for r in self.families().read() if r["family"] == "a"]
        self.assertEqual((row["version"], row["validation_r_sd"]), (1, written))

    def test_with_the_lane_off_nothing_is_written_and_dm1_reads_its_fallbacks(self):
        self.family("a", structure="debit_vertical")
        tour = Tournament(self.store, self.pool, self.settings)  # dlane.mode "off": the rollback
        tour.judge("a", 1, self.answer(types.SimpleNamespace(window="validation", name="a", family="a", stress=1.0)),
                   record=True)
        state = self.store.family("a")["state"]
        self.assertFalse({"validation_r_sd", "validation_r_sd_by_version"} & set(state))
        self.band_at_probe("a", 1)
        [row] = [r for r in self.families().read() if r["family"] == "a"]
        self.assertIsNone(row["validation_r_sd"])
        self.assertEqual(M.dm1_sigma(M.forward_stats([], 0.8, version=1), row["validation_r_sd"])[0],
                         M.DM1_FALLBACK_SIGMA)


# ========================================================================================== 2. the dlane report's envelope
@unittest.skipUnless(HAVE, "numpy not installed")
class TheProbeEnvelope(Fixture):
    """`probe_envelope` on a live book (the fixture's clock: Tue Oct 20, 2026)."""

    TODAY = "2026-10-20"
    UNIT = 50.0

    def setUp(self):
        super().setUp()
        from league.live.real import probe_window_start

        self.since = probe_window_start(self.TODAY, 20)
        self.assertEqual(self.since, "2026-09-23", "20 NYSE sessions through Oct 20 (Columbus Day trades)")

    def probe_close(self, pnl: float, day: str, **kw) -> int:
        return self.close("dir-a", route=":r", pnl=pnl, day=day, closed_at=ny(day, 15, 0), probe=True, **kw)

    def held(self) -> None:
        """An open Probe position: $40 maximum loss with fees of $0.13 twice: $40.26 at risk."""
        self.close("dir-a", route=":r", pnl=-40.13, max_loss=40.0, day="2026-10-19", status="open", qty=1, probe=True)

    def noise(self) -> None:
        """Closes no Probe budget ever counts: a Sized gain (no mark) and a tuition loss."""
        self.close("siz-b", route=":r", pnl=500.0, day="2026-10-15", closed_at=ny("2026-10-15", 15, 0))
        self.close("dir-a", route=":t", pnl=-90.0, day="2026-10-15", closed_at=ny("2026-10-15", 15, 0), probe=True)

    def envelope(self) -> dict:
        positions = R.read_book(self.root / R.LIVE_DB)["positions"]
        return R.probe_envelope(self.root / R.LIVE_DB, positions, today=self.TODAY, unit_usd=self.UNIT)

    def expected(self, basis: str) -> tuple:
        """`real.probe_figures` with the table in force told `basis`: what `RealBook.exposure` gives `plan_open`."""
        from league.live.real import probe_figures
        from league.ops import guard

        table = dataclasses.replace(M.Table.from_constitution(), probe_loss_basis=basis)
        return guard.read(self.root / R.LIVE_DB, lambda db: probe_figures(
            lambda sql, params=(): guard.rows(db, sql, params), day=self.TODAY, table=table))

    def check_constitution(self, env: dict) -> None:
        probe = CONSTITUTION["options_money"]["probe"]
        self.assertEqual(env["constitution"], {
            "loss_basis": probe["loss_basis"], "loss_budget_usd": float(probe["loss_budget_usd"]),
            "loss_window_sessions": probe["loss_window_sessions"], "loss_total_usd": float(probe["loss_total_usd"]),
            "max_open": probe["max_open"], "demotion": probe["demotion"]})
        self.assertEqual((env["basis_in_force"], env["budget_usd"], env["window_sessions"], env["total_budget_usd"],
                          env["max_open"]),
                         (probe["loss_basis"], float(probe["loss_budget_usd"]), probe["loss_window_sessions"],
                          float(probe["loss_total_usd"]), probe["max_open"]))

    def test_the_constitution_in_force_is_release_lds_with_the_800_total(self):
        """Release L-D's rows, the total at the owner's $800 since THE PROBE TOTAL AT $800 (Oct 10, 2026; $400
        before)."""
        env = self.envelope()
        self.check_constitution(env)
        self.assertEqual(env["constitution"], {"loss_basis": "net", "loss_budget_usd": 400.0, "loss_window_sessions": 20,
                                               "loss_total_usd": 800.0, "max_open": 8, "demotion": "dm1"})

    def test_the_window_binds_when_an_old_gain_hides_a_recent_loss_from_the_total(self):
        """+$300 closed Aug 3 (outside the 20 sessions) and -$350 on Oct 14: NET in total is $50, the window's worst net
        stretch $350. D-1's single envelope (NET from inception against the $400) left $309.74 (6.19 units) and no
        alarm; the window's envelope leaves $9.74 and A4 names it (the $800 total leaves $709.74)."""
        self.fam("dir-a", lane="direction", band="probe")
        self.probe_close(300.0, "2026-08-03")
        self.probe_close(-350.0, "2026-10-14")
        self.held()
        self.noise()
        env = self.envelope()
        self.check_constitution(env)
        net, gross = env["by_basis"]["net"], env["by_basis"]["gross"]
        self.assertEqual((net["window_usd"], net["total_usd"]), (350.0, 50.0))
        self.assertEqual((gross["window_usd"], gross["total_usd"]), (350.0, 350.0))
        self.assertEqual((env["at_risk_usd"], env["open"], env["window_start"]), (40.26, 1, self.since))
        self.assertEqual((net["room_window_usd"], net["room_total_usd"], net["room_usd"], net["binding"]),
                         (9.74, 709.74, 9.74, "window"))
        self.assertEqual((env["room_net_usd"], env["room_net_units"], env["binding"]), (9.74, 0.19, "window"))
        self.assertEqual((env["window_net_usd"], env["realized_net_usd"]), (350.0, 50.0))
        self.assertEqual(env["probe_closes"], 2)
        for basis in ("gross", "net"):
            open_n, window, total, at_risk, since = self.expected(basis)
            self.assertEqual((env["by_basis"][basis]["window_usd"], env["by_basis"][basis]["total_usd"]),
                             (round(float(window), 2), round(float(total), 2)), basis)
        # The code in force's own figure (the fast lane report's) says the same.
        in_force = env["in_force"]
        self.assertEqual((in_force["realized_usd"], in_force["realized_total_usd"], in_force["room_usd"],
                          in_force["binding"], in_force["window_start"]), ("350.00", "50.00", "9.74", "window", self.since))
        a4 = self.alarm(env)
        self.assertEqual((a4["basis"], a4["binding"]), ("net", "window"))
        self.assertIn("$400.00 in any 20 sessions binds", a4["text"])

    def test_the_total_binds_and_the_window_is_its_worst_net_stretch(self):
        """-$700 closed Aug 3 (the total only), +$40 Oct 13 then -$60 Oct 14: the window's plain net is $20 but its
        worst net stretch $60 (a gain offsets only the losses before it); NET in total $720. The $800 total binds:
        $39.74 left (under L-D's $400 total, -$300 on Aug 3 left the same)."""
        self.fam("dir-a", lane="direction", band="probe")
        self.probe_close(-700.0, "2026-08-03")
        self.probe_close(40.0, "2026-10-13")
        self.probe_close(-60.0, "2026-10-14")
        self.held()
        self.noise()
        env = self.envelope()
        net, gross = env["by_basis"]["net"], env["by_basis"]["gross"]
        self.assertEqual((net["window_usd"], net["total_usd"]), (60.0, 720.0))
        self.assertEqual((gross["window_usd"], gross["total_usd"]), (60.0, 760.0))
        self.assertEqual((net["room_window_usd"], net["room_total_usd"], net["room_usd"], net["binding"]),
                         (299.74, 39.74, 39.74, "total"))
        self.assertEqual((gross["room_total_usd"], gross["room_usd"], gross["binding"]), (-0.26, 0.0, "total"))
        self.assertEqual((env["room_net_units"], env["room_gross_units"]), (0.79, 0.0))
        self.assertEqual((env["in_force"]["room_usd"], env["in_force"]["binding"]), ("39.74", "total"))
        a4 = self.alarm(env)
        self.assertEqual(a4["binding"], "total")
        self.assertIn("$800.00 in total binds", a4["text"])

    def test_under_the_con_only_rollback_it_is_d1s_single_envelope_again(self):
        """Fast lane v2's rows (gross, a 2000-session window that holds every close, $400 in total): the window is the
        total, and the room is D-1's 400 - gross from inception - at risk."""
        self.fam("dir-a", lane="direction", band="probe")
        self.probe_close(300.0, "2026-08-03")
        self.probe_close(-350.0, "2026-10-14")
        self.held()
        with mock.patch.dict(CONSTITUTION["options_money"]["probe"], FAST_LANE_V2):
            env = self.envelope()
            self.check_constitution(env)
        gross = env["by_basis"]["gross"]
        self.assertEqual((env["basis_in_force"], env["window_sessions"], env["window_start"]), ("gross", 2000, None))
        self.assertEqual((gross["window_usd"], gross["total_usd"]), (350.0, 350.0))
        self.assertEqual(gross["room_usd"], round(400.0 - 350.0 - 40.26, 2))
        self.assertEqual(env["room_gross_usd"], gross["room_usd"])
        self.assertEqual(env["constitution"]["demotion"], "dm0")

    def test_an_absent_book_has_the_constitution_and_no_figure(self):
        env = R.probe_envelope(self.root / "absent.sqlite", [], today=self.TODAY, unit_usd=self.UNIT)
        self.check_constitution(env)
        self.assertIsNone(env["by_basis"])
        self.assertIsNone(env["in_force"])
        self.assertTrue(all(env[f"room_{b}_units"] is None for b in M.LOSS_BASES))

    def alarm(self, env: dict) -> dict:
        lanes = R.Lanes(self.store)
        out = R.alarms(self.store, {"dlane": {"mode": "gate"}}, lanes, {"positions": [], "instances": []}, [], env,
                       {"all": {"checkpoints": []}, "screen": {"checkpoints": []}}, {"tripped": False},
                       {"cap_usd": self.UNIT}, None, now=self.now, today=self.TODAY)
        [a4] = [a for a in out if a["id"] == "A4"]
        return a4


@unittest.skipUnless(HAVE, "numpy not installed")
class TheReportCarriesIt(Fixture):
    def test_the_report_and_the_fast_lane_report_read_one_table(self):
        """The `dlane` report's envelope and the fast lane report's `probe_budget` are one reading of one table."""
        from league.ops import fast_lane

        self.fam("dir-a", lane="direction", band="probe")
        self.close("dir-a", route=":r", pnl=-25.0, day="2026-10-14", closed_at=ny("2026-10-14", 15, 0), probe=True)
        env = R.report(self.root, settings={"dlane": {"mode": "gate"}}, now=self.now)["probe_envelope"]
        budget = fast_lane.probe_budget(self.root / R.LIVE_DB, "2026-10-20")
        self.assertEqual(env["in_force"], budget)
        self.assertEqual((env["budget_usd"], env["total_budget_usd"], env["window_sessions"], env["basis_in_force"]),
                         (float(budget["budget_usd"]), float(budget["total_budget_usd"]), budget["window_sessions"], "net"))
        self.assertEqual(env["room_net_usd"], float(budget["room_usd"]))
        self.assertEqual(env["binding"], budget["binding"])


class TheLoosenedRowsNameTheRollingBudget(unittest.TestCase):
    def test_the_report_header_states_release_lds_two_envelopes(self):
        text = " ".join([*[" ".join(r.values()) for r in R.LOOSENED], *R.TIGHTENED])
        self.assertIn("$400 of worst net stretch in any 20 sessions and $800 net in total", text)
        self.assertIn("rolling Probe budget (L9", text)
        self.assertTrue(text.isascii())
        for year in ("2020", "2021", "2025", "2026"):
            self.assertNotIn(year, text)


if __name__ == "__main__":
    unittest.main()
