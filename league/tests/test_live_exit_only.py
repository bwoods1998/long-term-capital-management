"""Exit-only instances (v3): a real instance on exits only still closes what it holds, and its program's opens are dropped
before the order path, silently (no reject told to the program, no `live.refusal` row) and counted in the minute's
summary as `exit_only_opens_dropped`. Anything that is not a real instance still meets the order path's belt. With the
fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import unittest

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.step import Instance
    from league.tests.live_fakes import family

#: Asks for a new vertical at every decision while no order of its own works, and closes what it has held two minutes.
OPENER = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {"hold": 2}

def decide(ctx):
    out = [{"close": p["id"], "limit": "natural", "note": "held long enough"}
           for p in ctx.positions if p["held_minutes"] >= ctx.params["hold"]]
    if not ctx.orders:
        out.append({"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural", "tag": "t",
                    "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                             {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]})
    return out
'''

OPEN = {"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural",
        "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0}, {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}


def opens_sent(venue):
    return [b for b in venue.sent if any(str(leg.get("position_intent", "")).endswith("open") for leg in b.get("legs") or [])]


@unittest.skipUnless(HAVE, "numpy not installed")
class ExitOnly(LiveCase):
    def demote(self, live):
        """The family's forward record turns negative: its real instance goes to exits only at the next minute's pass
        (under `probe.demotion` "dm0", release L-D's rollback, on which these tests run: under "dm1" a negative record
        no longer ends a Probe band, `test_ld_release`)."""
        self.families.rows["opener"]["forward"] = {"trades": 25, "negative": True}
        live._families_at = float("-inf")

    def test_its_opens_are_dropped_silently_and_counted_while_its_closes_go(self):
        from league.tests.money_fakes import rollback_table

        live = self.make([family("opener", OPENER, band="probe", params={"hold": 2})], table=rollback_table())
        self.run_to(9, 31)
        self.assertEqual(len(opens_sent(self.venue)), 1, "the live instance opened")
        told = []
        reject = live.book._reject
        live.book._reject = lambda instance, why: (told.append((instance, why)), reject(instance, why))
        refusals = len(self.ledger.of("live.refusal"))
        self.demote(live)
        out = self.run_to(9, 32)
        self.assertEqual(live.instances["opener@1:r"].mode, "exit_only")
        self.assertEqual(out.get("exit_only_opens_dropped"), 1, "the minute's one open, counted")
        out = self.run_to(9, 33)                                             # held two minutes: a close and an open
        self.assertEqual(out.get("exit_only_opens_dropped"), 1)
        self.assertEqual(len(opens_sent(self.venue)), 1, "no open after the demotion")
        closes = [o for o in out.get("orders") or [] if o["action"] == "close"]
        self.assertEqual(len(closes), 1, "its close went the same minute its open was dropped")
        self.assertEqual(len(self.ledger.of("live.refusal")), refusals, "no live.refusal for a dropped open")
        self.assertFalse([w for _, w in told if "closes only" in w], "nothing told to the program")
        self.assertFalse([t for _, t in self.alerts if "not a real instance" in t])

    def test_a_live_instance_is_not_dropped_and_its_refused_opens_are_still_recorded(self):
        live = self.make([family("opener", OPENER, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        self.killed = True                                                   # entries shut: the open is refused, recorded
        out = self.run_to(9, 32)
        self.assertEqual(live.instances["opener@1:r"].mode, "live")
        self.assertNotIn("exit_only_opens_dropped", out)
        self.assertTrue([p for p, _ in self.ledger.of("live.refusal") if "kill switch" in p["why"]])

    def test_a_non_real_instance_still_meets_the_belt_whatever_its_mode(self):
        live = self.make([family("opener", OPENER, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        rogue = Instance("rogue@1:o", "rogue", 1, "shadow", OPENER, {}, observe=True, mode="wind_down")
        out = {}
        live._real_intents(rogue, live.day, 1, [dict(OPEN)], out)
        self.assertNotIn("exit_only_opens_dropped", out, "never dropped quietly: the belt refuses it, alerted")
        self.assertTrue([t for lvl, t in self.alerts if lvl == "error" and "not a real instance" in t])
        self.assertTrue([p for p, _ in self.ledger.of("live.refusal") if p["instance"] == "rogue@1:o"])

    def test_a_cancel_or_close_that_also_names_open_is_not_taken_for_an_open(self):
        live = self.make([family("opener", OPENER, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        inst = live.instances["opener@1:r"]
        inst.mode = "exit_only"
        out = {}
        live._real_intents(inst, live.day, 1, [{"cancel": 999, "open": "x"}, {"close": 999, "open": "x"}, dict(OPEN)], out)
        self.assertEqual(out.get("exit_only_opens_dropped"), 1)
        whys = [p["why"] for p, _ in self.ledger.of("live.refusal") if p["instance"] == "opener@1:r"]
        self.assertIn("cancel: no such working order", whys)
        self.assertIn("close: no such open position", whys)


if __name__ == "__main__":
    unittest.main()
