"""The D3 real-fill calibration round trips (`league/live/calibration.py`; the sprint, Sept 26, 2026): 1-lot SPY, QQQ
and IWM debit verticals the House sends at the mid (at 12:00 and 14:00 ET the patient mid of 25 minutes), then one tick
worse, and closes at the mid, one tick under, then the natural; six hourly slots, 10:00 through 15:00 ET; only with real
money on, the grant active and the paper proof passed; at most the constitution's $50 of maximum loss a day; through the
real book's order path; recorded in their own file; never evidence, never on the site; leaving the families two Probe
floors of the day cap and most of the day's legs, and yielding a working open to a family refused on its contracts
(the reviews of #407). With the fakes of `live_fakes` (the venue's shapes, invented numbers)."""

import io
import json
import os
import sqlite3
import unittest
from contextlib import redirect_stdout
from decimal import Decimal as D
from unittest import mock

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.gym import venue as V
    from league.live import calibration as C
    from league.live.__main__ import main as live_main
    from league.live.step import OptionsLive
    from league.live.decider import InlineDecider
    from league.tests.live_fakes import MONDAY, NY, VERTICAL, at, family

#: A probe family's real open of the nearest-the-money $1 call vertical on the nearest expiry a day out -- the patient
#: cell's own contracts -- at the mid, from 12:05 (the review of #407: the rebound mechanism's entry).
REBOUND = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {}
STATE = {"opened": 0}

def decide(ctx):
    if STATE["opened"] or ctx.positions or ctx.orders or ctx.minute < 725:
        return []
    return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "mid", "tag": "t", "note": "rebound",
             "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                      {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
'''

#: A probe family's one real open late in the day (15:20), two days out (never the calibration's contracts).
LATE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {}
STATE = {"opened": 0}

def decide(ctx):
    if STATE["opened"] or ctx.positions or ctx.orders or ctx.minute < 920:
        return []
    STATE["opened"] = 1
    return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural", "tag": "t", "note": "late",
             "legs": [{"side": "long", "right": "C", "dte": 2, "atm": 0},
                      {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
'''

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

    def opens(self):
        return [b for b in self.mine() if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]

    def minute_of(self, t: float) -> int:
        """The New York minute of a clock time."""
        import datetime as dt

        local = dt.datetime.fromtimestamp(t, NY)
        return local.hour * 60 + local.minute

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
    def test_cheap_round_trips_repeat_through_the_day_under_the_bound(self):
        # Filled at the mid both ways, a round trip loses only its fees: each closed one frees its maximum loss, so
        # every one of the six hourly slots sends one -- the 15:00 slot too -- rotating to the symbol with the fewest
        # samples of the slot's cell, the patient mid at 12:00 and 14:00.
        self.venue.fill = "limit"
        live = self.start(real_money=True)
        today = MONDAY.isoformat()
        for slot in C.SLOTS:
            hh, mm = divmod(slot, 60)
            if slot != C.SLOTS[0]:
                self.clock.set(at(MONDAY, hh, mm) - 3 * 60)
            self.run_to(hh, mm + 2)
            self.assertEqual(live.book.positions, {}, f"closed by {hh}:{mm + 2:02d}")
            self.assertLess(live.calibration.day_possible_loss(today), D("3"), "only the fees are realized")
        self.assertEqual(len(self.opens()), 6, "six round trips, one a slot")
        self.assertEqual(live.state.get("calibration")["slots"], {"day": today, "fired": [600, 660, 720, 780, 840, 900]})
        rows = [r for r in self.samples() if r["action"] == "open"]
        self.assertEqual([r["cell"] for r in rows], ["SPY:open:mid", "QQQ:open:mid", "SPY:open:mid25", "IWM:open:mid",
                                                     "QQQ:open:mid25", "SPY:open:mid"])
        self.assertEqual([self.minute_of(r["submitted_at"]) for r in rows], list(C.SLOTS), "each at its slot's minute")
        self.assertEqual(live.state.rows("SELECT tif FROM orders WHERE family=? AND action='open' ORDER BY oid",
                                         (C.FAMILY,)), [{"tif": t} for t in (4, 4, 24, 4, 24, 4)])

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
        self.clock.set(at(MONDAY, 10, 59))
        self.run_to(11, 5)
        self.assertEqual(len(self.opens()), 1, "a second round trip would put more than $50 of the day at risk")
        why = live.state.get("calibration")["why"]
        self.assertIn("the day's calibration bound", why)
        self.assertEqual(live.state.get("calibration")["slots"]["fired"], [600, 660])
        # The patient cell at 12:00 is bounded the same way: its maximum loss would pass the day's room, so it never
        # goes.
        live.state.put("calibration", {**live.state.get("calibration"), "why": None})
        self.clock.set(at(MONDAY, 11, 59))
        self.run_to(12, 5)
        self.assertEqual(len(self.opens()), 1)
        self.assertIn("the day's calibration bound", live.state.get("calibration")["why"])
        self.assertIn("SPY pair 1", live.state.get("calibration")["why"])
        self.assertEqual(live.state.get("calibration")["slots"]["fired"], [600, 660, 720])
        self.assertLessEqual(live.calibration.day_possible_loss(today), D("50"))
        self.assertFalse([r for r in self.samples() if r["cell"].endswith("mid25")])

    def test_one_round_trip_at_a_time(self):
        self.venue.fill = "limit"

        def hook(body):
            if body["legs"][0]["position_intent"] == "sell_to_close":
                self.venue.fill = "none"                                  # its closes never fill

        self.venue.on_submit = hook
        live = self.start(real_money=True)
        self.run_to(10, 2)
        self.assertEqual(len(live.book.positions), 1)
        self.clock.set(at(MONDAY, 10, 59))
        self.run_to(11, 40)
        self.assertEqual(len(self.opens()), 1, "the 11:00 slot waits while a calibration position is held")
        self.assertEqual(len(live.book.positions), 1)
        self.assertNotIn(660, live.state.get("calibration")["slots"]["fired"])

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


class Timing(CalibrationCase):
    """Sept 28, 2026: six hourly slots, 10:00 through 15:00 ET; the patient cell at 12:00 and 14:00; every round trip's
    ladder, at its slowest, sent before the last resort (15:45 ET)."""

    def ladder_at_its_slowest(self):
        """Every open rests unfilled until its re-price's LAST minute; every close rests until the natural."""
        closes = []

        def hook(body):
            if body["legs"][0]["position_intent"] == "buy_to_open":
                self.venue.fill = "none"
            else:
                closes.append(body)
                self.venue.fill = "none" if len(closes) < 3 else "natural"

        self.venue.fill = "none"
        self.venue.on_submit = hook

    def sent_minutes(self):
        return [(r["cell"].split(":", 1)[1], self.minute_of(r["submitted_at"])) for r in self.samples()]

    def test_the_arithmetic(self):
        self.assertEqual(C.SLOTS, (600, 660, 720, 780, 840, 900))
        self.assertEqual(C.SYMBOLS, ("SPY", "QQQ", "IWM"))
        self.assertEqual((C.ladder_minutes(C.WAIT_MINUTES), C.ladder_minutes(C.PATIENT_MINUTES)), (23, 43))
        self.assertEqual((C.OPEN_TIF["mid25"], C.OPEN_TIF["mid"], C.OPEN_TIF["mid+1"]), (24, 4, 4))
        for close in (960, 780):                                          # a full day and a half day
            last = close - C.NO_NEW_MINUTES - 1                           # the last minute a round trip may start
            self.assertTrue(C.fits(last, close, C.ladder_minutes(C.WAIT_MINUTES)), "the plain ladder always fits")
            self.assertTrue(C.fits(last + C.WAIT_MINUTES + 1, close, C.REPRICE_REST), "and so does its re-price")
        # The 15:00 slot starts (it is 60 minutes before the close, and NO_NEW_MINUTES is 45) until 15:14.
        self.assertLess(900, 960 - C.NO_NEW_MINUTES)
        self.assertEqual(960 - C.NO_NEW_MINUTES, 915)
        # The patient cell: its slowest ladder from 15:00 sends the natural at 15:43, inside the slack before 15:45, so
        # it is never at 15:00; at 12:00 and 14:00 it fits to the end of the slot's window.
        self.assertEqual(900 + C.ladder_minutes(C.PATIENT_MINUTES), 943)
        self.assertFalse(C.fits(900, 960, C.ladder_minutes(C.PATIENT_MINUTES)))
        self.assertNotIn(900, C.PATIENT_SLOTS)
        for slot in C.PATIENT_SLOTS:
            self.assertTrue(C.fits(slot + C.SLOT_WINDOW - 1, 960, C.ladder_minutes(C.PATIENT_MINUTES)), slot)
        self.assertEqual([C.open_cell(s, s, 960) for s in C.SLOTS], ["mid", "mid", "mid25", "mid", "mid25", "mid"])
        self.assertEqual(C.open_cell(840, 884, 960), "mid25")
        self.assertEqual(C.open_cell(720, 720, 780), "mid", "a half day (13:00 close): the plain mid")

    def test_the_15_00_slot_starts_at_15_14_and_its_ladder_at_its_slowest_ends_before_the_last_resort(self):
        self.ladder_at_its_slowest()
        live = self.start(real_money=True, hh=15, mm=14)
        self.run_to(15, 24)
        self.venue.fill = "limit"                                         # the re-price fills in its last minute
        self.run_to(15, 44)
        self.assertEqual(self.sent_minutes(), [("open:mid", 914), ("open:mid+1", 920), ("close:mid", 925),
                                               ("close:mid-1", 931), ("close:natural", 937)])
        self.assertEqual(937, 914 + C.ladder_minutes(C.WAIT_MINUTES), "the arithmetic is the order path's")
        self.assertLess(937 + C.LADDER_SLACK, 960 - C.LAST_RESORT_MINUTES)
        self.assertEqual(live.book.positions, {})

    def test_no_round_trip_starts_at_15_15(self):
        self.venue.fill = "limit"
        live = self.start(real_money=True, hh=15, mm=15)
        self.run_to(15, 30)
        self.assertEqual(self.mine(), [])
        self.assertEqual(live.calibration.roots(self.clock()), {}, "nor are chains read for a slot that cannot start")

    def test_the_patient_open_works_25_minutes_at_the_mid_then_reprices_once(self):
        self.venue.fill = "none"
        live = self.start(real_money=True, hh=11, mm=58)
        self.run_to(12, 0)
        [first] = self.mine()
        [row] = self.samples()
        self.assertEqual((row["cell"], row["offset"], row["ticks"]), ("SPY:open:mid25", "mid25", 0))
        self.assertAlmostEqual(row["limit_value"], V.round_price(row["mid"], 0.01, up=False), places=6, msg="at the mid")
        self.assertAlmostEqual(float(first["limit_price"]), row["limit_value"], places=6)
        self.assertEqual(live.state.get("calibration")["trip"]["attempt"], "mid25")
        self.assertEqual(live.calibration.roots(self.clock()), {"SPY": (1, 7, 0.01)}, "only its own root while it works")
        self.run_to(12, 24)
        self.assertEqual((len(self.mine()), self.venue.cancels), (1, []), "it still works at 12:24")
        self.run_to(12, 25)
        self.assertEqual(len(self.venue.cancels), 1, "time in force 24: the market's minutes 12:01 through 12:25")
        self.run_to(12, 26)
        first_, second = self.mine()
        self.assertEqual(second["legs"], first["legs"], "the same contracts")
        self.run_to(12, 45)
        self.assertEqual(len(self.mine()), 2, "once, then nothing more this slot")
        # The re-price after the patient open is its own cell (the review of #407): the same order as mid+1, after 25
        # unfilled minutes at the mid rather than 5.
        self.assertEqual([(r["cell"], r["outcome"], r["ticks"], r["tif"]) for r in self.samples()],
                         [("SPY:open:mid25", "cancelled", 0, 24), ("SPY:open:mid25+1", "cancelled", 1, 4)])
        self.assertTrue(all(r["cancel_reason"].startswith("its time in force") for r in self.samples()))
        self.assertEqual(self.sent_minutes(), [("open:mid25", 720), ("open:mid25+1", 746)])
        self.assertEqual({r["trip"] for r in self.samples()}, {"20260928-720-SPY"})
        self.assertEqual(live.state.rows("SELECT tif FROM orders WHERE family=? ORDER BY oid", (C.FAMILY,)),
                         [{"tif": 24}, {"tif": 4}])
        self.assertIsNone(live.state.get("calibration")["trip"])
        self.assertEqual(live.book.positions, {})

    def test_the_patient_ladder_at_its_slowest_ends_before_the_last_resort(self):
        self.ladder_at_its_slowest()
        live = self.start(real_money=True, hh=13, mm=58)
        self.run_to(14, 30)
        self.venue.fill = "limit"                                         # the re-price fills in its last minute
        self.run_to(14, 50)
        self.assertEqual(self.sent_minutes(), [("open:mid25", 840), ("open:mid25+1", 866), ("close:mid", 871),
                                               ("close:mid-1", 877), ("close:natural", 883)])
        self.assertEqual(883, 840 + C.ladder_minutes(C.PATIENT_MINUTES), "the arithmetic is the order path's")
        self.assertEqual(live.book.positions, {})
        # From the end of the 14:00 slot's window it would still end with the slack in hand before 15:45.
        self.assertLess(884 + C.ladder_minutes(C.PATIENT_MINUTES) + C.LADDER_SLACK, 960 - C.LAST_RESORT_MINUTES)

    def test_a_patient_slot_whose_symbols_all_have_the_patient_target_opens_at_the_mid(self):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": True, "observe": False,
                                                                   "calibration_samples": 1}}))
        recorder = C.Recorder(self.root)
        for oid, symbol in enumerate(C.SYMBOLS, 900):
            self.assertTrue(recorder.submitted({
                "oid": oid, "client_id": f"c{oid}", "trip": "t", "day": "2026-09-25", "symbol": symbol, "legs": "[]",
                "action": "open", "offset": "mid25", "ticks": 0, "cell": C.cell_of(symbol, "open", "mid25"),
                "limit_price": "0.40", "limit_value": 0.4, "qty": 1, "quote": "{}", "submitted_at": 0.0}))
            recorder.finished(oid, {"outcome": "filled", "status": "filled", "filled_qty": 1})
        recorder.close()
        self.venue.fill = "limit"
        self.start(real_money=True, hh=11, mm=58)
        self.run_to(12, 1)
        opened = [r["cell"] for r in self.samples() if r["oid"] < 900 and r["action"] == "open"]
        self.assertEqual(opened, ["SPY:open:mid"], "every symbol has the patient target: the plain mid instead")


class OneAtATime(CalibrationCase):
    def test_at_most_one_round_trip_at_any_minute_of_the_day(self):
        n = {"open": 0, "close": 0}

        def hook(body):
            if body["legs"][0]["position_intent"] == "buy_to_open":
                n["open"] += 1
                self.venue.fill = "limit" if n["open"] % 2 == 0 else "none"   # every other open rests unfilled
            else:
                n["close"] += 1
                self.venue.fill = "natural" if n["close"] % 3 == 0 else "none"  # a close fills at its natural rung

        self.venue.on_submit = hook
        live = self.start(real_money=True)
        seen = set()
        while self.minute_of(self.clock()) <= 15 * 60 + 50:
            live.minute()
            opens = [o for o in live.book.orders.values() if o.working and o.family == C.FAMILY and o.action == "open"]
            held = live.calibration.positions()
            self.assertLessEqual(len(opens) + len(held), 1, f"one round trip at a time ({self.minute_of(self.clock())})")
            seen |= {p.root for p in held}
            self.clock.set(self.clock() + 60)
        self.assertGreaterEqual(len({r["trip"] for r in self.samples()}), 4)
        self.assertEqual(seen, {"SPY", "QQQ", "IWM"}, "every symbol held once in the day")


class Iwm(CalibrationCase):
    def iwm_trip(self):
        self.venue.fill = "limit"
        with mock.patch.object(C, "SYMBOLS", ("IWM",)):
            live = self.start(real_money=True)
            self.run_to(10, 2)
        opened, closed = self.mine()[:2]
        strikes = [int(leg["symbol"][-8:]) / 1000 for leg in opened["legs"]]
        return live, opened, closed, strikes

    def test_its_verticals_are_one_dollar_wide_nearest_the_money(self):
        live, opened, closed, strikes = self.iwm_trip()
        spot = self.market.level("IWM")                                  # 281.28: between the 281 and 282 strikes
        self.assertTrue(all(leg["symbol"].startswith("IWM") for leg in opened["legs"]))
        self.assertEqual(strikes, [281.0, 282.0], "the pair whose centre is nearest the underlying")
        self.assertLess(abs(sum(strikes) / 2 - spot), 0.5)
        self.assertLessEqual(float(opened["limit_price"]) * 100, 50.0)
        self.assertEqual([r["cell"] for r in self.samples()], ["IWM:open:mid", "IWM:close:mid"])
        self.assertEqual(live.book.positions, {})

    def test_a_pair_whose_one_lot_and_fees_would_pass_the_days_room_yields_to_the_next_nearest(self):
        # IWM at 281.46: the nearest pair (281/282) costs about $0.50 at the mid, $50 of maximum loss before its fees,
        # over the day's $50 room once they are counted; the next nearest that fits goes, never it.
        self.market.spot = 281.46 / self.market.IWM_SHARE
        live, opened, closed, strikes = self.iwm_trip()
        nearest = [self.market.quote(f"IWM260929C00{k}000") for k in (281, 282)]
        debit = sum(b + a for b, a in nearest[:1]) / 2 - sum(b + a for b, a in nearest[1:]) / 2
        self.assertGreaterEqual(debit * 100, 49.9, "the nearest pair is at the edge of the bound")
        self.assertEqual(strikes, [282.0, 283.0])
        self.assertLess(float(opened["limit_price"]) * 100 + 2 * 0.1, 50.0)
        self.assertLessEqual(float(live.state.get("calibration")["day_possible_loss_usd"]["usd"]), 50.0)

    def test_on_a_half_dollar_grid_a_pair_half_a_dollar_off_the_whole_strikes(self):
        self.market.steps["IWM"] = 0.5
        self.market.spot = 280.85 / self.market.IWM_SHARE                # IWM 280.85: 280.5/281.5 is centred at 281.0
        live, opened, closed, strikes = self.iwm_trip()
        self.assertEqual(strikes, [280.5, 281.5])
        self.assertEqual([leg["symbol"][-9:] for leg in opened["legs"]], ["C00280500", "C00281500"])
        self.assertEqual(live.book.positions, {})


class Report(CalibrationCase):
    def test_the_report_shows_the_plan_and_every_cell_the_patient_cell_among_them(self):
        out = io.StringIO()
        with redirect_stdout(out):
            report = live_main(["--root", str(self.root), "--calibration"])
        self.assertEqual(report["plan"]["slots_et"], ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00"])
        self.assertEqual(report["plan"]["patient_slots_et"], ["12:00", "14:00"])
        self.assertEqual(report["plan"]["symbols"], ["SPY", "QQQ", "IWM"])
        self.assertEqual(report["plan"]["works_minutes"]["open"], {"mid": 5, "mid+1": 5, "mid25": 25, "mid25+1": 5})
        self.assertEqual(report["plan"]["repriced_as"], {"mid": "mid+1", "mid25": "mid25+1"})
        self.assertEqual(report["plan"]["leaves_families"], {"day_cap_probe_floors": 2, "no_new_trip_from_legs": 80})
        self.assertEqual(len(report["cells"]), 21, "3 symbols x (4 open + 3 close cells)")
        for symbol in C.SYMBOLS:
            cell = report["cells"][f"{symbol}:open:mid25"]
            self.assertEqual((cell["works_minutes"], cell["attempts"], cell["fill_rate"], cell["interrupted"]),
                             (25, 0, None, 0))
            self.assertEqual(report["cells"][f"{symbol}:open:mid25+1"]["works_minutes"], 5)
        self.assertIn("IWM:open:mid25", json.loads(out.getvalue())["cells"])
        # Once sampled, the patient cell counts its own.
        self.venue.fill = "limit"
        self.start(real_money=True, hh=11, mm=58)
        self.run_to(12, 2)
        report = C.report(self.root)
        patient = report["cells"]["SPY:open:mid25"]
        self.assertEqual((patient["attempts"], patient["filled"], patient["fill_rate"]), (1, 1, 1.0))
        self.assertEqual(report["cells"]["SPY:open:mid"]["attempts"], 0)


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


class TheReviewOf407(CalibrationCase):
    """The reviews of #407: what the calibration leaves the families (the day cap's room and the day's legs), yielding a
    working open to a family refused on its contracts, an open cut short never a sample and never re-priced, each row's
    own time in force, and the half day through the order path."""

    def is_mine(self, body) -> bool:
        return str(body.get("client_order_id") or "").endswith("house-calibration")

    def cancel_reasons(self, live):
        return [json.loads(r["answer"]).get("cancel") for r in
                live.state.rows("SELECT answer FROM orders WHERE family=? ORDER BY oid", (C.FAMILY,))]

    def test_it_leaves_the_families_two_probe_floors_of_the_day_cap(self):
        # The live account's sizing equity: the grant pins $481.63, so the account-wide day cap (1.0 x equity) is
        # $481.63, and every dispatched open counts its whole maximum loss toward it, filled or not. A heavy day (every
        # calibration mid unfilled, every re-price filled) once took $426 of it; now the calibration leaves $200.
        self.grant.capital = "481.63"
        n = {"cal_open": 0}

        def hook(body):
            if not self.is_mine(body):
                self.venue.fill = "natural"                             # the family's open
            elif body["legs"][0]["position_intent"] == "buy_to_open":
                n["cal_open"] += 1
                self.venue.fill = "none" if n["cal_open"] % 2 else "limit"
            else:
                self.venue.fill = "limit"

        self.venue.on_submit = hook
        live = self.start([family("late", LATE, band="probe")], real_money=True)
        whys = set()
        while self.minute_of(self.clock()) <= 15 * 60 + 25:
            live.minute()
            whys.add((live.state.get("calibration") or {}).get("why"))
            self.clock.set(self.clock() + 60)
        today = MONDAY.isoformat()
        cap = live.table.gateway_day_share * live.sizing_equity()
        self.assertEqual(cap, D("481.63"))
        room = 2 * live.table.probe_floor                               # two Probe floors: $200
        self.assertEqual(room, D("200"))
        rows = live.state.rows("SELECT max_loss, answer FROM orders WHERE family=? AND action='open'", (C.FAMILY,))
        dispatched = sum(D(str(r["max_loss"])) for r in rows if json.loads(r["answer"]).get("dispatched"))
        self.assertGreater(dispatched, D("180"), "a heavy day: the calibration used what it may")
        self.assertLessEqual(dispatched + room, cap, "never past the cap less the families' room")
        self.assertTrue(any(w and "kept for the families' opens" in w for w in whys), whys)
        # The family's late open still goes: the day cap has room for it.
        [fam] = live.state.rows("SELECT status, max_loss FROM orders WHERE family='late' AND action='open'")
        self.assertEqual(fam["status"], "filled")
        self.assertLessEqual(live.book.exposure("late", day=today, week_start=today).day_opened, cap)
        self.assertEqual(C.FAMILY_ROOM_PROBES, 2)

    def test_no_round_trip_starts_once_its_own_legs_today_reach_the_cap(self):
        # The day's count is 250 legs, a cancel's counted too; the calibration's own are counted as the House counts
        # them and no round trip starts from `DAY_LEGS`.
        n = {"open": 0}

        def hook(body):
            if body["legs"][0]["position_intent"] == "buy_to_open":
                n["open"] += 1
                self.venue.fill = "none" if n["open"] == 1 else "limit"  # the mid rests and is cancelled; the re-price
            else:
                self.venue.fill = "limit"

        self.venue.on_submit = hook
        today = MONDAY.isoformat()
        with mock.patch.object(C, "DAY_LEGS", 8):
            live = self.start(real_money=True)
            self.run_to(10, 8)
            self.assertEqual(live.book.positions, {})
            # The mid and its cancel, the re-price, the close: 2 + 2 + 2 + 2, exactly the House's own count.
            self.assertEqual(live.calibration.day_legs(today), 8)
            self.assertEqual(live.book.count_today(today), 8)
            self.clock.set(at(MONDAY, 10, 59))
            self.run_to(11, 5)
        self.assertEqual(len(self.opens()), 2, "no round trip at 11:00")
        cal = live.state.get("calibration")
        self.assertIn(660, cal["slots"]["fired"])
        self.assertIn("8 legs today", cal["why"])
        self.assertEqual(C.DAY_LEGS, 80)

    def test_a_working_open_yields_to_a_family_refused_on_its_contracts(self):
        # The patient open holds the rebound mechanism's own contracts for 25 minutes; a family's real open of them is
        # refused ("one order stream per contract"). The calibration cancels its open the minute it sees the refusal
        # and ends the round trip without its re-price; the family's open goes the next minute.
        def hook(body):
            self.venue.fill = "none" if self.is_mine(body) else "limit"

        self.venue.on_submit = hook
        self.venue.fill = "none"
        live = self.start([family("reb", REBOUND, band="probe")], real_money=True, hh=11, mm=58)
        self.run_to(12, 4)
        [row] = self.samples()
        self.assertEqual(row["cell"], "SPY:open:mid25")
        self.run_to(12, 5)
        self.assertEqual(len(self.venue.cancels), 1, "cancelled at 12:05, the minute the family was refused")
        self.run_to(12, 40)
        fam = live.state.rows("SELECT status, placed_minute, legs FROM orders WHERE family='reb' AND action='open'")
        self.assertEqual(len(fam), 1)
        self.assertEqual(fam[0]["status"], "filled")
        self.assertLessEqual(fam[0]["placed_minute"] + live.day.open_min, 12 * 60 + 7, "the family's open went at once")
        cal_legs = {leg["symbol"] for leg in json.loads(live.state.rows(
            "SELECT legs FROM orders WHERE family=? ORDER BY oid", (C.FAMILY,))[0]["legs"])}
        self.assertTrue(cal_legs & {leg["symbol"] for leg in json.loads(fam[0]["legs"])}, "the same contracts")
        # Interrupted: never a sample, never counted, never re-priced.
        [row] = [r for r in self.samples() if r["action"] == "open"]
        self.assertEqual((row["cell"], row["outcome"]), ("SPY:open:mid25", "interrupted"))
        self.assertTrue(row["cancel_reason"].startswith("yielded"))
        self.assertEqual(live.calibration.recorder.counts(), {})
        self.assertIsNone(live.state.get("calibration")["trip"])
        self.assertIn("yielded", live.state.get("calibration")["why"])
        cell = C.report(self.root)["cells"]["SPY:open:mid25"]
        self.assertEqual((cell["attempts"], cell["interrupted"], cell["ended"], cell["fill_rate"]), (1, 1, 0, None))

    def test_a_refusal_naming_other_contracts_is_not_a_yield(self):
        self.venue.fill = "none"
        live = self.start(real_money=True, hh=11, mm=58)
        self.run_to(12, 1)
        order = next(o for o in live.book.orders.values() if o.family == C.FAMILY)
        mine = sorted(leg.symbol for leg in order.legs)
        other = mine[0][:-8] + f"{int(mine[0][-8:]) + 50000:08d}"             # 50 strikes away
        live.book.rejects_since["ghost@1:r"] = [f"one order stream per contract: {other} already has a working order",
                                                 f"the day's order count: 10 legs sent of 250 ({mine[0]})"]
        self.run_to(12, 10)
        self.assertEqual(self.venue.cancels, [], "a refusal naming other contracts, or another refusal, is not a yield")
        live.book.rejects_since["ghost@1:r"] = [f"positions net across the account: this open takes the other side of "
                                                 f"{mine[1]}, which the account holds"]
        self.run_to(12, 11)
        self.assertEqual(len(self.venue.cancels), 1, "the account's net guard naming its contract: it yields")
        self.run_to(12, 40)
        self.assertEqual([(r["cell"], r["outcome"]) for r in self.samples()], [("SPY:open:mid25", "interrupted")])

    def test_an_open_cut_short_by_a_real_entry_block_is_interrupted_and_never_repriced(self):
        # The review of #407 (review 2): the kill switch at 12:07 during the patient open. It was recorded as a full
        # 25-minute "cancelled" sample (and re-priced); now it is interrupted: never counted, never in the fill rate.
        self.venue.fill = "none"
        live = self.start(real_money=True, hh=11, mm=58)
        self.run_to(12, 6)
        self.killed = True
        self.run_to(12, 8)
        self.killed = False
        self.run_to(12, 45)
        self.assertEqual(len(self.opens()), 1, "no re-price after an open cut short")
        [row] = self.samples()
        self.assertEqual((row["cell"], row["outcome"], row["tif"]), ("SPY:open:mid25", "interrupted", 24))
        self.assertEqual(row["cancel_reason"], "real entries are shut: the gateway's kill switch is engaged")
        self.assertEqual(live.calibration.recorder.counts(), {})
        self.assertIn("cut short", live.state.get("calibration")["why"])
        cell = C.report(self.root)["cells"]["SPY:open:mid25"]
        self.assertEqual((cell["interrupted"], cell["ended"], cell["cancelled"]), (1, 0, 0))

    def test_every_row_records_its_time_in_force_and_an_older_file_gains_the_columns(self):
        # A file the first release wrote (no `tif`, no `cancel_reason`): the recorder adds both, its row kept.
        db = sqlite3.connect(self.root / C.FILE)
        db.executescript(C.SCHEMA.replace(", tif INTEGER, cancel_reason TEXT", ""))
        db.execute("INSERT INTO samples(oid, client_id, trip, day, symbol, legs, action, offset, ticks, cell, "
                   "limit_price, limit_value, qty, quote, submitted_at, outcome) VALUES(9000, 'c9000', 't', "
                   "'2026-09-25', 'SPY', '[]', 'open', 'mid', 0, 'SPY:open:mid', '0.40', 0.4, 1, '{}', 0.0, 'filled')")
        db.commit()
        self.assertNotIn("tif", {r[1] for r in db.execute("PRAGMA table_info(samples)")})
        db.close()
        modes = ["none", "limit", "none", "none", "natural"]

        def hook(body):
            self.venue.fill = modes.pop(0) if modes else "natural"

        self.venue.on_submit = hook
        self.start(real_money=True)
        self.run_to(10, 30)
        *rows, older = self.samples()
        self.assertEqual((older["oid"], older["tif"], older["cancel_reason"]), (9000, None, None),
                         "the older row kept: its time in force is its offset's")
        # SPY has the older sample, so QQQ goes first.
        self.assertEqual([(r["cell"], r["tif"]) for r in rows],
                         [("QQQ:open:mid", 4), ("QQQ:open:mid+1", 4), ("QQQ:close:mid", 4), ("QQQ:close:mid-1", 4),
                          ("QQQ:close:natural", 0)])
        self.assertEqual([r["outcome"] for r in rows], ["cancelled", "filled", "cancelled", "cancelled", "filled"])
        self.assertEqual(C.report(self.root)["cells"]["SPY:open:mid"]["ended"], 1)


@unittest.skipUnless(HAVE, "numpy not installed")
class HalfDay(CalibrationCase):
    """A half day (a 13:00 close) through the order path: the patient slot opens at the plain mid, the last round trip
    starts at 12:14 and its slowest ladder sends its natural by 12:37, before the 12:45 last resort."""

    def setUp(self):
        super().setUp()
        patch = mock.patch("league.live.step.session_minutes", lambda day: (570, 780))
        patch.start()
        self.addCleanup(patch.stop)

    def test_the_patient_slot_opens_at_the_plain_mid_and_the_last_ladder_ends_before_the_last_resort(self):
        closes = []

        def hook(body):
            if body["legs"][0]["position_intent"] == "buy_to_open":
                self.venue.fill = "none"
            else:
                closes.append(body)
                self.venue.fill = "none" if len(closes) < 3 else "natural"

        self.venue.fill = "none"
        self.venue.on_submit = hook
        live = self.start(real_money=True, hh=12, mm=14)
        self.assertEqual(live.day.close_min if live.day else 780, 780)
        self.run_to(12, 24)
        self.venue.fill = "limit"                                         # the re-price fills in its last minute
        self.run_to(12, 44)
        self.assertEqual(live.day.close_min, 780)
        self.assertEqual([(r["cell"].split(":", 1)[1], self.minute_of(r["submitted_at"])) for r in self.samples()],
                         [("open:mid", 734), ("open:mid+1", 740), ("close:mid", 745), ("close:mid-1", 751),
                          ("close:natural", 757)])
        self.assertLess(757 + C.LADDER_SLACK, 780 - C.LAST_RESORT_MINUTES)
        self.assertEqual(live.state.rows("SELECT tif FROM orders WHERE family=? AND action='open' ORDER BY oid",
                                         (C.FAMILY,)), [{"tif": 4}, {"tif": 4}])
        self.assertEqual(live.book.positions, {})

    def test_no_round_trip_starts_from_12_15(self):
        self.venue.fill = "limit"
        live = self.start(real_money=True, hh=12, mm=15)
        self.run_to(12, 40)
        self.assertEqual(self.mine(), [])
        self.assertEqual(live.calibration.roots(self.clock()), {})


if __name__ == "__main__":
    unittest.main()
