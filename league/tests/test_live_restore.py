"""A restored real instance is a real instance (Sept 29, 2026): after a House restart, every real instance the live state
holds comes back real, in its saved mode, with its program in the REAL decider child and its chains read in the real
phase. Before the fix the saved mode landed in `Instance.observe` (a positional shift), so the House live test (and any
restored Probe or Sized family) loaded in the observe child, decided nothing and had its real opens refused.
With the fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import unittest

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.decider import InlineDecider
    from league.live.step import Instance, OptionsLive
    from league.tests.live_fakes import VERTICAL, family


@unittest.skipUnless(HAVE, "numpy not installed")
class RestoredRealInstances(LiveCase):
    def restart(self):
        """A new House process on the same state root, with its two decider children apart."""
        self.live.state.close()
        self.main, self.other = InlineDecider(), InlineDecider()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=self.main,
                                observe_decider=self.other, config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def test_a_restored_real_instance_is_real_loads_in_the_real_child_and_trades(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 31)
        self.assertEqual(len(self.venue.sent), 1, "the real open went before the restart")
        self.assertTrue(live.book.positions)
        live = self.restart()
        inst = live.instances["vert@1:r"]
        self.assertIs(inst.observe, False, "never the saved mode in the observe field")
        self.assertEqual((inst.kind, inst.mode), ("real", "live"))
        self.assertIn("vert@1:r", self.main.loaded, "its program is in the real child")
        self.assertNotIn("vert@1:r", self.other.loaded)
        self.assertIn("SPY", live._roots("real"), "its chains are read in the real phase")
        self.assertNotIn("SPY", live._roots("observe"))
        self.assertEqual(live.health()["instances"]["vert@1:r"]["observe"], False)
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        self.assertEqual(live.book.positions, {}, "the restored program decided: its close went")
        self.assertTrue([p for p, _ in self.ledger.of("book.fill") if p["side"] == "sell"])
        self.assertFalse([t for _, t in self.alerts if "not a real instance" in t])

    def test_a_restored_exit_only_instance_stays_exit_only(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 31)
        self.assertTrue(live.book.positions)
        del self.families.rows["vert"]                                   # the family left the real band
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["vert@1:r"].mode, "exit_only")
        live = self.restart()
        inst = live.instances["vert@1:r"]
        self.assertEqual((inst.mode, inst.observe, inst.kind), ("exit_only", False, "real"),
                         "its saved mode, not 'live', and never an observe instance")
        self.assertIn("vert@1:r", self.main.loaded)
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        self.assertEqual(live.book.positions, {}, "it still closes what it holds")
        self.assertEqual(len([b for b in self.venue.sent]), 2, "one open before the restart, one close after; no new open")

    def test_an_observe_key_is_only_ever_a_shadow_instance(self):
        with self.assertRaises(ValueError):
            Instance("obs@1:o", "obs", 1, "real", VERTICAL, {})
        for flag in ("live", "exit_only", 1, "observe"):
            self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=flag).observe, False, flag)
        self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=True).observe, True)
        self.assertIs(Instance("vert@1:s", "vert", 1, "shadow", VERTICAL, {}, observe=True).observe, False, "not an observe key")
        self.assertIs(Instance("vert@1:r", "vert", 1, "real", VERTICAL, {}, observe=True).observe, False)
        self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, tuition=True, observe=True).observe, False)

    def test_the_order_path_refuses_any_instance_that_is_not_real(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 31)
        sent = len(self.venue.sent)
        shadow = Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=True)
        shadow.needs = live.instances["vert@1:r"].needs
        forged = Instance("vert@1:r", "vert", 1, "real", VERTICAL, {})
        forged.observe = "live"                                          # anything but False after construction
        forged.needs = shadow.needs
        for inst in (shadow, forged):
            why = live._real_intent(inst, live.day, 1, {"open": {"type": "debit_vertical"}}, {})
            self.assertIn("not a real one", why)
        self.assertEqual(len(self.venue.sent), sent, "no order reached the venue")
        self.assertEqual(len([t for lvl, t in self.alerts if lvl == "error" and "not a real instance" in t]), 2)


if __name__ == "__main__":
    unittest.main()
