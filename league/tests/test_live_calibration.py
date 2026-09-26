"""The D3 real-fill calibration round trips (`league/live/calibration.py`; the sprint, Sept 26, 2026): 1-lot SPY debit
verticals the House sends at the mid, then one tick worse, and closes at the mid, one tick under, then the natural; only
with real money on, the grant active and the paper proof passed; at most the constitution's $50 of maximum loss a day;
through the real book's order path; recorded in their own file; never evidence, never on the site. With the fakes of
`live_fakes` (the venue's shapes, invented numbers)."""

import io
import json
import os
import sqlite3
import unittest
from contextlib import redirect_stdout
from decimal import Decimal as D

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.gym import venue as V
    from league.live import calibration as C
    from league.live.__main__ import main as live_main
    from league.live.step import OptionsLive
    from league.live.decider import InlineDecider
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

HOLD_600C = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {}
STATE = {"opened": 0}

def decide(ctx):
    if STATE["opened"] or ctx.positions or ctx.orders:
        return []
    STATE["opened"] = 1
    return [{"open": "long_call", "root": "SPY", "qty": 1, "limit": "natural",
             "legs": [{"side": "long", "right": "C", "dte": 1, "strike": 600.0}]}]
'''


@unittest.skipUnless(HAVE, "numpy not installed")
class CalibrationCase(LiveCase):
    def setUp(self):
        super().setUp()
        self.switch(True)

    def switch(self, on: bool) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": on, "observe": False}}))

    def start(self, rows=(), *, hh=9, mm=59, proof=True, **kw):
        self.clock.set(at(MONDAY, hh, mm))
        live = self.make(list(rows), **kw)
        if proof:
            live.state.put("paper_proof", {"schema": 2, "status": "passed", "open_witness": True, "close_witness": True})
        return live

    def mine(self):
        return [b for b in self.venue.sent if str(b.get("client_order_id") or "").endswith("house-calibration")]

    def samples(self):
        db = sqlite3.connect(self.root / C.FILE)
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM samples ORDER BY oid")]
        finally:
            db.close()

    def mid_of(self, body):
        value = 0.0
        for leg in body["legs"]:
            bid, ask = self.market.quote(leg["symbol"])
            role = 1 if leg["position_intent"] in ("buy_to_open", "sell_to_close") else -1
            value += role * 0.5 * (bid + ask)
        return value


class RoundTrip(CalibrationCase):
    def test_a_round_trip_at_the_slot_at_the_mid_recorded_and_never_evidence(self):
        self.venue.fill = "limit"                                          # a resting order the market comes through
        live = self.start([family("vert", VERTICAL, band="candidate")], real_money=True)
        self.run_to(10, 1)
        opened, closed = self.mine()
        self.assertEqual((opened["order_class"], opened["qty"], opened["time_in_force"]), ("mleg", "1", "day"))
        (a, b) = opened["legs"]
        self.assertEqual(([a["side"], a["position_intent"]], [b["side"], b["position_intent"]]),
                         (["buy", "buy_to_open"], ["sell", "sell_to_open"]))
        self.assertEqual(a["symbol"][:3], "SPY")
        self.assertEqual(int(b["symbol"][-8:]) - int(a["symbol"][-8:]), 1000, "calls one dollar wide")
        mid = self.mid_of(opened)
        self.assertAlmostEqual(float(opened["limit_price"]), V.round_price(mid, 0.01, up=False), places=6)
        self.assertLessEqual(float(opened["limit_price"]) * 100, 50.0, "inside the day's $50")
        self.assertEqual([leg["position_intent"] for leg in closed["legs"]], ["sell_to_close", "buy_to_close"])
        self.assertLess(float(closed["limit_price"]), 0, "a debit structure's close receives a credit")
        self.assertEqual(live.book.positions, {})
        # Recorded: one row an attempt, each ended, with its quotes at submit and the venue's times.
        rows = self.samples()
        self.assertEqual([(r["cell"], r["outcome"], r["filled_qty"]) for r in rows],
                         [("SPY:open:mid", "filled", 1), ("SPY:close:mid", "filled", 1)])
        for r in rows:
            quote = json.loads(r["quote"])
            self.assertEqual(len(quote["legs"]), 2)
            self.assertTrue(all(leg["bid"] is not None and leg["ask"] is not None for leg in quote["legs"]))
            self.assertIsNotNone(r["mid"])
            self.assertIsNotNone(r["natural"])
            self.assertIsNotNone(r["filled_at"])
            self.assertIsNotNone(r["submitted_at"])
            self.assertEqual(r["fees_source"], "book_estimate")
        self.assertEqual(rows[0]["trip"], rows[1]["trip"])
        self.assertEqual(oct(os.stat(self.root / C.FILE).st_mode & 0o777), "0o600")
        # Never evidence, never a family's, never on the site; the ledger's rows are the House's own.
        self.assertEqual(self.families.forward, {})
        [trade] = live.book.closed_trades()
        self.assertEqual(trade["family"], C.FAMILY)
        self.assertEqual(live.state.rows("SELECT pid FROM forward_exports"), [{"pid": trade["pid"]}])
        self.assertTrue(all(a == C.FAMILY for p, a in self.ledger.of("book.fill")))
        self.assertFalse([row for row in live.site_inputs()["structures"] if row["real"] or row["agent"] == C.FAMILY])
        # Counted in the day's order governor: two legs an order.
        self.assertEqual(live.book.count_today(MONDAY.isoformat()), 4)
        # The owner's report, read-only.
        out = io.StringIO()
        with redirect_stdout(out):
            report = live_main(["--root", str(self.root), "--calibration"])
        cell = report["cells"]["SPY:open:mid"]
        self.assertEqual((cell["attempts"], cell["filled"], cell["fill_rate"]), (1, 1, 1.0))
        self.assertIsNotNone(cell["mean_fill_vs_mid_ticks"])
        self.assertIn("SPY:close:mid", json.loads(out.getvalue())["cells"])

    def test_an_unfilled_mid_is_repriced_once_a_tick_worse_then_given_up_across_a_restart(self):
        self.venue.fill = "none"
        live = self.start(real_money=True)
        self.run_to(10, 2)
        [first] = self.mine()
        # A new House process in the middle of the round trip: its state is the live state's.
        live.state.close()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(),
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.clock.set(self.clock() + 60)
        self.run_to(10, 5)
        self.assertEqual(len(self.venue.cancels), 1, "its five minutes (tif 4: the Gym's minutes m+1..m+5) ran out at 10:05")
        self.assertEqual(len(self.mine()), 1)
        self.run_to(10, 6)
        first_, second = self.mine()
        self.assertEqual(second["legs"], first["legs"], "the same contracts")
        at_mid, over = self.samples()
        self.assertAlmostEqual(at_mid["limit_value"], V.round_price(at_mid["mid"], 0.01, up=False), places=6)
        self.assertAlmostEqual(over["limit_value"], min(V.round_price(over["mid"] + 0.01, 0.01, up=False), over["natural"]),
                               places=6, msg="the then mid plus one tick, never past the natural")
        self.assertEqual(over["ticks"], 1)
        self.run_to(10, 40)
        self.assertEqual(len(self.mine()), 2, "once, then nothing more this slot")
        self.assertEqual([(r["cell"], r["outcome"]) for r in self.samples()],
                         [("SPY:open:mid", "cancelled"), ("SPY:open:mid+1", "cancelled")])
        self.assertEqual(self.live.book.positions, {})
        self.assertIsNone(self.live.state.get("calibration")["trip"])

    def test_the_close_goes_at_the_mid_then_a_tick_under_then_the_natural(self):
        modes = ["limit", "none", "none", "natural"]

        def next_mode(body):
            self.venue.fill = modes.pop(0) if modes else "natural"

        self.venue.on_submit = next_mode
        live = self.start(real_money=True)
        self.run_to(10, 14)
        opened, *closes = self.mine()
        self.assertEqual(len(closes), 3)
        at_mid, under, natural = self.samples()[1:]
        # Each at the then quotes, as the Gym's rules price them (rounded passively: a sale asks the tick above).
        self.assertAlmostEqual(at_mid["limit_value"], V.round_price(at_mid["mid"], 0.01, up=True), places=6)
        self.assertAlmostEqual(under["limit_value"], max(V.round_price(under["mid"] - 0.01, 0.01, up=True), under["natural"]),
                               places=6)
        self.assertEqual(under["ticks"], 1)
        self.assertAlmostEqual(natural["limit_value"], natural["natural"], places=6)
        self.assertEqual([float(c["limit_price"]) for c in closes],
                         [-round(r["limit_value"], 2) for r in (at_mid, under, natural)], "a close receives: a credit")
        self.assertEqual(live.book.positions, {})
        self.assertEqual([r["cell"] for r in self.samples()],
                         ["SPY:open:mid", "SPY:close:mid", "SPY:close:mid-1", "SPY:close:natural"])
        self.assertEqual([r["outcome"] for r in self.samples()], ["filled", "cancelled", "cancelled", "filled"])


class Backstop(CalibrationCase):
    def test_a_calibration_position_its_ladder_left_open_is_closed_by_the_house_before_the_close(self):
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        live.calibration._close = lambda *a, **k: None                   # its own ladder broken
        self.run_to(10, 1)
        self.assertEqual(len(live.book.positions), 1)
        self.venue.fill = "natural"
        self.clock.set(at(MONDAY, 15, 45))
        self.run_to(15, 49)
        self.assertEqual(len(live.book.positions), 1, "the House leaves it to the calibration's own ladder until 15:50")
        self.run_to(15, 51)
        self.assertEqual(live.book.positions, {}, "from 15:50 the House closes it as it closes an orphan's")
        self.assertEqual(self.families.forward, {})


class TheReview(CalibrationCase):
    """The review of #390: the closes are budgeted and capped, calibration yields to the families, and it is never
    Profit (a cost instead)."""

    def closes_do(self, **mode):
        """The open fills at its limit; every close then meets the venue as `mode` says."""
        self.venue.fill = "limit"

        def hook(body):
            if body.get("legs") and body["legs"][0]["position_intent"] == "sell_to_close":
                for key, value in mode.items():
                    setattr(self.venue, key, value)

        self.venue.on_submit = hook

    def test_refused_closes_back_off_and_stop_at_six_a_day(self):
        self.closes_do(submit_mode="reject")                               # every close refused by the venue
        live = self.start(real_money=True)
        self.run_to(10, 0)
        self.assertEqual(len(live.book.positions), 1)
        self.run_to(15, 40)
        closes = [b for b in self.mine() if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(len(closes), C.CLOSE_ATTEMPTS_DAY, "six attempts a day, not one a minute")
        times = [r["submitted_at"] for r in self.samples() if r["action"] == "close"]
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertGreaterEqual(gaps[0], 5 * 60 - 1, "five minutes after the first refusal")
        self.assertGreaterEqual(gaps[1], 10 * 60 - 1, "then ten: the back-off doubles")
        self.assertLess(live.book.count_today(MONDAY.isoformat()), 40)

    def test_a_natural_of_a_tick_or_less_is_never_sent(self):
        self.closes_do(fill="none")
        live = self.start(real_money=True)
        self.run_to(10, 0)
        [pos] = live.book.positions.values()
        long_leg, short_leg = pos.legs
        self.market.overrides[long_leg.symbol] = (0.01, 0.02, 10, 10)
        self.market.overrides[short_leg.symbol] = (0.00, 0.01, 10, 10)      # the natural close: 0.01 - 0.01 = 0
        self.run_to(10, 30)
        offsets = [r["offset"] for r in self.samples() if r["action"] == "close"]
        self.assertNotIn("natural", offsets)
        self.assertLessEqual(len(offsets), 2)

    def test_it_yields_a_root_on_which_a_family_works_an_order(self):
        resting = VERTICAL.replace('"limit": "natural", "tag": "t"', '"limit": {"price": 0.01}, "tag": "t"')
        self.venue.fill = "limit"
        live = self.start([family("vert", resting, band="probe", params={"hold": 600})], real_money=True, mm=58)
        self.venue.fill = "none"
        self.run_to(10, 0)
        self.assertTrue([o for o in live.book.orders.values() if o.family == "vert" and o.root == "SPY"])
        self.assertFalse([b for b in self.mine() if b["legs"][0]["symbol"].startswith("SPY")], "SPY left to the family")
        self.assertTrue([b for b in self.mine() if b["legs"][0]["symbol"].startswith("QQQ")], "QQQ goes instead")

    def test_it_is_never_profit_and_never_a_compute_line(self):
        # The review of #390: the site's figure after compute is the equity's change less compute, and equity already
        # carries the calibration's result, so publishing it as compute too would count it twice.
        from league import trading_profit

        self.assertEqual(trading_profit.CALIBRATION_FAMILY, C.FAMILY)
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        self.run_to(10, 1)
        [trade] = live.book.closed_trades()
        self.assertNotEqual(trade["pnl"], 0)
        at = "2026-09-28T14:05:00.000Z"
        self.assertEqual(trading_profit.snapshot(self.root, live, at=at)["pnl_usd"], "0.00", "no family traded")
        self.assertNotIn("compute", live.site_inputs())

    def test_it_requotes_its_contracts_just_before_it_sends(self):
        # The review of #390 (lens 2): it sends after the minute's decider batch, so it prices from a fresh read of its
        # two contracts, never from the minute-start snapshot alone.
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        self.run_to(9, 59)
        reads = len(self.market.contract_reads)
        self.run_to(10, 0)
        opened = self.mine()[0]
        symbols = sorted(leg["symbol"] for leg in opened["legs"])
        self.assertIn(symbols, self.market.contract_reads[reads:])
        for row in self.samples():
            self.assertEqual(json.loads(row["quote"])["source"], "requote", row["cell"])
        del live


class Limits(CalibrationCase):
    def opens(self):
        return [b for b in self.mine() if b["legs"][0]["position_intent"] == "buy_to_open"]

    def test_cheap_round_trips_repeat_through_the_day_under_the_bound(self):
        # Filled at the mid both ways, a round trip loses only its fees: each closed one frees its maximum loss, so
        # every slot of the day sends one.
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        today = MONDAY.isoformat()
        for hh, mm in ((10, 2), (12, 32), (14, 32)):
            if (hh, mm) != (10, 2):
                self.clock.set(at(MONDAY, hh, mm - 3))
            self.run_to(hh, mm)
            self.assertEqual(live.book.positions, {}, f"closed by {hh}:{mm:02d}")
            self.assertLess(live.calibration.day_possible_loss(today), D("2"), "only the fees are realized")
        self.assertEqual(len(self.opens()), 3, "three round trips, one a slot")
        self.assertEqual(live.state.get("calibration")["slots"], {"day": today, "fired": [600, 750, 870]})

    def test_the_next_open_is_refused_once_realized_loss_and_what_is_open_would_pass_fifty(self):
        closes = []

        def hook(body):
            if body["legs"][0]["position_intent"] == "buy_to_open":
                self.venue.fill = "limit"
            else:
                closes.append(body)
                self.venue.fill = "none" if len(closes) == 1 else "limit"   # the first close rests; the second fills

        self.venue.on_submit = hook
        live = self.start(real_money=True)
        self.run_to(10, 2)
        [pos] = live.book.positions.values()
        entry = pos.entry
        long_leg, short_leg = pos.legs
        # The market falls: the round trip closes at a dime, a loss of about $37 on a debit of about $0.47.
        self.market.overrides[long_leg.symbol] = (0.10, 0.12, 20, 20)
        self.market.overrides[short_leg.symbol] = (0.00, 0.02, 20, 20)
        self.run_to(10, 7)
        self.assertEqual(live.book.positions, {})
        today = MONDAY.isoformat()
        realized = live.calibration.day_possible_loss(today)
        self.assertGreater(realized, D("30"))
        self.assertAlmostEqual(float(realized), (entry - 0.10) * 100 + 0.5, delta=1.0)
        # While the position was held, the bound counted its maximum loss; now the realized loss stands in for it.
        del self.market.overrides[long_leg.symbol], self.market.overrides[short_leg.symbol]
        self.clock.set(at(MONDAY, 12, 29))
        self.run_to(12, 35)
        self.assertEqual(len(self.opens()), 1, "a second round trip would put more than $50 of the day at risk")
        why = live.state.get("calibration")["why"]
        self.assertIn("the day's calibration bound", why)
        self.assertEqual(live.state.get("calibration")["slots"]["fired"], [600, 750])

    def test_one_round_trip_at_a_time(self):
        self.venue.fill = "limit"

        def hook(body):
            if body["legs"][0]["position_intent"] == "sell_to_close":
                self.venue.fill = "none"                                  # its closes never fill

        self.venue.on_submit = hook
        live = self.start(real_money=True)
        self.run_to(10, 2)
        self.assertEqual(len(live.book.positions), 1)
        self.clock.set(at(MONDAY, 12, 29))
        self.run_to(12, 40)
        self.assertEqual(len(self.opens()), 1, "the 12:30 slot waits while a calibration position is held")
        self.assertEqual(len(live.book.positions), 1)
        self.assertNotIn(750, live.state.get("calibration")["slots"]["fired"])

    def test_nothing_goes_before_the_paper_proof_and_the_slot_waits_for_it(self):
        self.venue.fill = "limit"
        self.paper.fill = "none"
        live = self.start(real_money=True, proof=False)
        self.run_to(10, 5)
        self.assertEqual(self.mine(), [])
        live.state.put("paper_proof", {"schema": 2, "status": "passed", "open_witness": True, "close_witness": True})
        self.run_to(10, 7)
        self.assertEqual(len(self.mine()), 2, "inside the slot's window: it goes once the proof passed")

    def test_nothing_goes_with_real_money_off(self):
        self.start(real_money=False)
        self.run_to(10, 10)
        self.assertEqual(self.venue.sent, [])

    def test_nothing_goes_with_the_switch_off_or_the_grant_inactive_or_the_kill_switch(self):
        for case in ("switch", "grant", "kill"):
            with self.subTest(case=case):
                self.venue.sent.clear()
                self.switch(case != "switch")
                self.grant.active = case != "grant"
                self.killed = case == "kill"
                live = self.start(real_money=True)
                self.run_to(10, 6)
                self.assertEqual(self.mine(), [], case)
                live.state.close()
                self.live = None
                for name in ("live.sqlite", "live.sqlite-wal", "live.sqlite-shm", "live-shadow.json", C.FILE):
                    try:
                        (self.root / name).unlink()
                    except FileNotFoundError:
                        pass
        self.grant.active, self.killed = True, False

    def test_contracts_an_agent_holds_are_never_used(self):
        self.venue.fill = "limit"
        live = self.start([family("call", HOLD_600C, band="probe", structure="long_call")], real_money=True, mm=58)
        self.run_to(10, 0)
        held = {leg.symbol for p in live.book.positions.values() if p.family == "call" for leg in p.legs}
        self.assertEqual(len(held), 1)
        [opened] = [b for b in self.mine() if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertFalse({leg["symbol"] for leg in opened["legs"]} & held)


class Recorder(CalibrationCase):
    def test_a_recorder_that_cannot_write_never_raises_alerts_once_and_starts_no_round_trip(self):
        (self.root / C.FILE).mkdir()
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        self.run_to(10, 5)
        self.assertEqual(self.mine(), [])
        told = [text for lvl, text in self.alerts if "calibration's samples could not be recorded" in text]
        self.assertEqual(len(told), 1)
        recorder = C.Recorder(self.root, alert=lambda *a: None)
        self.assertFalse(recorder.submitted({"oid": 1}))
        self.assertIsNone(recorder.counts())

    def test_the_outcomes(self):
        self.assertEqual([C.outcome_of(s, q) for s, q in (("filled", 1), ("cancelled", 0), ("expired", 1), ("rejected", 0),
                                                          ("refused", 0), ("working", 0), ("lost", 0))],
                         ["filled", "cancelled", "partial", "rejected", "rejected", None, None])


if __name__ == "__main__":
    unittest.main()
