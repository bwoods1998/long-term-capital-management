"""Two money-path guards (#427, Sept 29, 2026; on main's practice league, Sept 30, 2026):

1. A restored real instance is a real instance. After a House restart, every real instance the live state holds comes
   back real, in its saved mode, with its program in the REAL decider child and its chains read in the real phase. Before
   #429 the saved mode landed in `Instance.observe` (a positional shift), so the House live test (and any restored Probe
   or Sized family) loaded in the observe child, decided nothing and had its real opens refused. `Instance.__post_init__`
   now makes `observe` True only for a shadow, non-tuition instance under a `:o` key, whatever it is given.
2. The order path's belt. `_real_intent` refuses, alerted, any instance that is not real or whose `observe` is not
   False: the practice league's `:o` shadows (validated and Train tier alike) can never reach a real order, even if a
   bug put one in the real batch.

With the fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import unittest

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live import calibration as C
    from league.live import house_test as HT
    from league.live.decider import InlineDecider
    from league.live.step import Instance, OptionsLive
    from league.tests.live_fakes import VERTICAL, family
    from league.tests.test_live_house_test import HouseCase
    from league.tests.test_live_practice import PracticeCase, trained, validated
else:  # pragma: no cover - the classes below are skipped
    HouseCase = PracticeCase = LiveCase

BELT = "not a real instance"                                 # the belt's alert
REFUSED = "not a real one"                                   # the belt's refusal


@unittest.skipUnless(HAVE, "numpy not installed")
class RestoredRealInstances(LiveCase):
    def restart(self):
        """A new House process on the same state root, with its two decider children apart."""
        self.live.close()
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
        self.assertFalse([t for _, t in self.alerts if BELT in t])

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
        self.assertEqual(len(self.venue.sent), 2, "one open before the restart, one close after; no new open")
        self.assertFalse([t for _, t in self.alerts if BELT in t])

    def test_an_observe_key_is_only_ever_a_shadow_instance(self):
        self.assertIs(Instance("obs@1:o", "obs", 1, "real", VERTICAL, {}, observe=True).observe, False,
                      "a real instance is never an observe one, whatever its key")
        for flag in ("live", "exit_only", 1, "observe"):
            self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=flag).observe, False, flag)
        self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=True).observe, True)
        self.assertIs(Instance("vert@1:s", "vert", 1, "shadow", VERTICAL, {}, observe=True).observe, False, "not an observe key")
        self.assertIs(Instance("vert@1:r", "vert", 1, "real", VERTICAL, {}, observe=True).observe, False)
        self.assertIs(Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, tuition=True, observe=True).observe, False)
        self.assertIs(Instance("vert@1:t", "vert", 1, "real", VERTICAL, {}, tuition=True, observe=True).observe, False)
        # The House's own real routes: never an observe one, whatever a row says.
        self.assertIs(Instance(HT.INSTANCE, HT.FAMILY, 0, "real", VERTICAL, {}, observe=True).observe, False)
        self.assertIs(Instance(HT.INSTANCE, HT.FAMILY, 0, "real", VERTICAL, {}, observe="live").observe, False)
        self.assertIs(Instance(C.INSTANCE, C.FAMILY, 0, "real", VERTICAL, {}, observe=True).observe, False)

    def test_a_restored_incubator_instance_stays_real_and_tuition_with_its_mode(self):
        """Release B: an incubator row (`:i`) restores real, tuition-flagged, incubator and never observe, whatever its row's
        tuition column or the arguments say, and keeps its saved mode."""
        live = self.make([])
        live.state.upsert("instances", {"id": "inc@1:i", "family": "inc", "version": 1, "run_sha": "s", "code": VERTICAL,
                                        "params": "{}", "band": "gym", "tuition": 0, "mode": "exit_only",
                                        "created_at": 1.0, "retired_at": None, "why": None}, "id")
        live = self.restart()
        inst = live.instances["inc@1:i"]
        self.assertEqual((inst.kind, inst.tuition, inst.incubator, inst.observe, inst.mode),
                         ("real", True, True, False, "exit_only"))
        self.assertIn("inc@1:i", self.main.loaded, "its program is in the real child")
        self.assertIs(Instance("inc@1:i", "inc", 1, "real", VERTICAL, {}, incubator=False).incubator, True)
        self.assertIs(Instance("inc@1:t", "inc", 1, "real", VERTICAL, {}, tuition=True, incubator=True).incubator, False)

    def test_the_order_path_refuses_any_instance_that_is_not_real(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 31)
        sent = len(self.venue.sent)
        shadow = Instance("obs@1:o", "obs", 1, "shadow", VERTICAL, {}, observe=True)
        shadow.needs = live.instances["vert@1:r"].needs
        forged = Instance("vert@1:r", "vert", 1, "real", VERTICAL, {})
        forged.observe = "live"                                          # anything but False after construction
        forged.needs = shadow.needs
        candidate = Instance("vert@1:s", "vert", 1, "shadow", VERTICAL, {})
        candidate.needs = shadow.needs
        for inst in (shadow, forged, candidate):
            why = live._real_intent(inst, live.day, 1, {"open": {"type": "debit_vertical"}}, {})
            self.assertIn(REFUSED, why)
        self.assertEqual(len(self.venue.sent), sent, "no order reached the venue")
        self.assertEqual(len([t for lvl, t in self.alerts if lvl == "error" and BELT in t]), 3)


@unittest.skipUnless(HAVE, "numpy not installed")
class PracticeNeverReal(PracticeCase):
    """Main's practice league (#431): its validated and Train-tier `:o` shadows run beside a Probe family's real
    instance with real money on. They are observe instances in their own child; the real one is never an observe one,
    before a restart or after; and none of them can put a real order through the order path."""

    def league(self):
        return self.build([family("vert", VERTICAL, band="probe")],
                          [validated("obs", params={"hold": 3, "opens": 3}), trained("tr", params={"hold": 3, "opens": 3})],
                          real_money=True)

    def test_practice_instances_are_observe_shadows_and_the_real_one_never_is_across_a_restart(self):
        live = self.league()
        self.run_to(9, 33)
        for key in ("obs@1:o", "tr@1:o"):
            inst = live.instances[key]
            self.assertEqual((inst.observe, inst.kind, inst.tuition), (True, "shadow", False), key)
            self.assertIn(key, self.other.loaded, "a practice program is in the observe child")
            self.assertNotIn(key, self.main.loaded)
        real = live.instances["vert@1:r"]
        self.assertEqual((real.observe, real.kind), (False, "real"))
        self.assertIn("vert@1:r", self.main.loaded)
        self.assertNotIn("vert@1:r", self.other.loaded)
        live = self.restart()
        real = live.instances["vert@1:r"]
        self.assertEqual((real.observe, real.kind, real.mode), (False, "real", "live"), "restored real, never observe")
        self.assertIn("vert@1:r", self.main.loaded)
        self.assertNotIn("vert@1:r", self.other.loaded)
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        for key in ("obs@1:o", "tr@1:o"):
            self.assertIs(live.instances[key].observe, True, key)
            self.assertIn(key, self.other.loaded, "back in the observe child after the restart")
            self.assertNotIn(key, self.main.loaded)
        health = live.health()["instances"]
        self.assertEqual({k: health[k]["observe"] for k in ("vert@1:r", "obs@1:o", "tr@1:o")},
                         {"vert@1:r": False, "obs@1:o": True, "tr@1:o": True})
        self.assertTrue(all(o.family == "vert" for o in live.book.orders.values()))
        self.assertTrue(all(p.family == "vert" for p in live.book.positions.values()))
        self.assertFalse([t for _, t in self.alerts if BELT in t])

    def test_a_practice_instance_cannot_produce_a_real_intent(self):
        live = self.league()
        self.run_to(9, 33)
        sent, orders, positions = len(self.venue.sent), dict(live.book.orders), dict(live.book.positions)
        pid = next(iter(positions), 1)                                  # the Probe's own real position, when it holds one
        intents = ({"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural",
                    "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                             {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]},
                   {"close": pid, "limit": "natural"}, {"cancel": 1})
        for key in ("obs@1:o", "tr@1:o"):
            inst = live.instances[key]
            for intent in intents:
                self.assertIn(REFUSED, live._real_intent(inst, live.day, 3, dict(intent), {}), (key, intent))
            live._real_intents(inst, live.day, 3, intents, {})           # the path the minute takes: each one recorded
        self.assertEqual(len(self.venue.sent), sent, "no order reached the venue")
        self.assertEqual((dict(live.book.orders), dict(live.book.positions)), (orders, positions),
                         "the Probe's own position was never closed by a practice program")
        self.assertEqual(len([t for lvl, t in self.alerts if lvl == "error" and BELT in t]), 12)
        refused = [p for p, _ in self.ledger.of("live.refusal") if p["instance"] in ("obs@1:o", "tr@1:o")]
        self.assertEqual(len(refused), 6)
        self.assertTrue(all(REFUSED in p["why"] for p in refused))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheBeltInTheMinute(LiveCase):
    def test_a_practice_instance_forced_into_the_real_batch_is_refused_and_alerted(self):
        """A bug that made a practice instance real (here: its kind changed after it was built) puts it in the minute's
        real batch; its program's opens meet the belt, never the venue. One decider child for both, so the practice
        program answers the real batch."""
        live = self.make([family("vert", VERTICAL, band="probe")],
                         observed=[validated("obs", params={"hold": 3, "opens": 50})])
        self.run_to(9, 33)
        inst = live.instances["obs@1:o"]
        self.assertTrue(inst.observe and inst.loaded and inst.needs is not None)
        self.assertFalse([t for _, t in self.alerts if BELT in t])
        inst.kind = "real"
        self.run_to(9, 38)
        self.assertTrue([t for lvl, t in self.alerts if lvl == "error" and "obs@1:o" in t and BELT in t])
        refused = [p for p, _ in self.ledger.of("live.refusal") if p["instance"] == "obs@1:o"]
        self.assertTrue(refused)
        self.assertTrue(all(REFUSED in p["why"] for p in refused))
        self.assertTrue(all(o.family == "vert" for o in live.book.orders.values()))
        self.assertTrue(all(p.family == "vert" for p in live.book.positions.values()))
        for table, column in (("orders", "instance"), ("positions", "instance")):
            self.assertFalse(live.state.rows(f"SELECT {column} FROM {table} WHERE family='obs'"), table)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheHouseTestStaysReal(HouseCase):
    def restart_apart(self):
        """A new House process on the same state root, with its two decider children apart."""
        self.live.close()
        self.live.state.close()
        self.main, self.other = InlineDecider(), InlineDecider()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=self.main,
                                observe_decider=self.other, config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def test_the_house_test_restores_real_in_the_real_child_and_still_trades_through_the_belt(self):
        self.install(hold=3)
        live = self.start()
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(len(live.book.positions), 1)
        live = self.restart_apart()
        inst = live.instances[HT.INSTANCE]
        self.assertEqual((inst.observe, inst.kind, inst.mode, inst.tuition), (False, "real", "live", False))
        self.assertIs(live._decider_of(inst), self.main, "the real child, never the observe one")
        self.assertIn(HT.INSTANCE, self.main.loaded)
        self.assertNotIn(HT.INSTANCE, self.other.loaded)
        self.assertIn("SPY", live._roots("real"))
        self.assertEqual(live.health()["instances"][HT.INSTANCE]["observe"], False)
        asked = []
        real_intent = live._real_intent

        def spy(inst, day, mi, intent, out):
            why = real_intent(inst, day, mi, intent, out)
            asked.append((inst.key, next((k for k in ("open", "close", "cancel") if k in intent), "?"), why))
            return why

        live._real_intent = spy
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        self.assertIn((HT.INSTANCE, "close", None), asked, "its program's own close passed the belt and was sent")
        closes = [b for b in self.mine() if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertTrue(closes, "its program's close went through the order path after the restart")
        self.assertFalse([w for w in self.refusals() if REFUSED in w])
        self.assertFalse([t for _, t in self.alerts if BELT in t])


if __name__ == "__main__":
    unittest.main()
