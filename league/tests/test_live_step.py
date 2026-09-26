"""The live path end to end (`league/live/step.py`): live chains -> the decider -> the shadow book and the real route,
with the fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import datetime as dt
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

try:
    import numpy as np
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.live import money as M
    from league.live.decider import InlineDecider
    from league.live.families import MemoryFamilies
    from league.live.step import OptionsLive
    from league.tests.live_fakes import CONDOR, MONDAY, VERTICAL, Clock, Grant, Market, Venue, at, family, iso


class Ledger:
    def __init__(self):
        self.rows = []

    def __call__(self, kind, payload, agent=None):
        self.rows.append((kind, payload, agent))

    def of(self, kind):
        return [(p, a) for k, p, a in self.rows if k == kind]


@unittest.skipUnless(HAVE, "numpy not installed")
class LiveCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock(at(MONDAY, 9, 31))
        self.market = Market(self.clock)
        self.venue = Venue(self.market, equity="5481.65", last_equity="481.65")
        self.venue.activity_rows.append({"id": "a1", "activity_type": "CSD", "net_amount": "5000", "status": "executed",
                                         "transaction_time": "2026-09-27T15:00:00Z"})
        self.paper = Venue(self.market, venue="alpaca-paper", equity="100000")
        self.ledger = Ledger()
        self.alerts = []
        self.notices = []
        self.grant = Grant()
        self.killed = False

    def tearDown(self):
        if getattr(self, "live", None) is not None:
            self.live.state.close()
        self.dir.cleanup()

    def make(self, rows, *, real_money=True, config=None):
        self.families = MemoryFamilies(rows)
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(),
                                config={"require_paper_proof": False, **(config or {})}, real_money=real_money,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def run_to(self, hh, mm):
        """Step the live path minute by minute up to hh:mm (inclusive)."""
        out = None
        while True:
            local = dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
            out = self.live.minute()
            if (local.hour, local.minute) >= (hh, mm):
                return out
            self.clock.set(self.clock() + 60)


class RoundTrip(LiveCase):
    def test_a_probe_family_trades_its_shadow_and_real_books_and_both_reach_the_forward_record(self):
        live = self.make([family("vert", VERTICAL, band="candidate")])
        out = self.run_to(9, 31)
        self.assertEqual(out["state"], "session")
        # The live path moved the Candidate to Probe (it passed the holdout, trades a real type, fits the cap).
        self.assertEqual(self.families.moves[0][:2], ("vert", "probe"))
        self.assertEqual(sorted(live.instances), ["vert@1:r", "vert@1:s"])
        # The real open: sized by maximum loss (3% of the lower of equity 5,481.65 and the grant's 5,500), not by the
        # program's qty of 2.
        [sent] = [b for b in self.venue.sent]
        self.assertEqual(sent["order_class"], "mleg")
        real = next(iter(live.book.positions.values()))
        unit = real.max_loss_share * 100 + 2 * (real.fees / real.qty)
        self.assertEqual(real.qty, int(D("164.4495") // D(str(round(unit, 2)))))
        self.assertGreater(real.qty, 2)
        [(buy, agent)] = self.ledger.of("book.fill")
        self.assertEqual((agent, buy["side"], buy["real_money"], buy["source"]), ("vert", "buy", True, "venue"))
        self.assertTrue(buy["instrument"]["market_id"].startswith("debit_vertical|+1SPY"))
        # The shadow book steps one minute behind the wall clock (the engine judges a passive fill by the minute after
        # it): at 09:32 it decides on 09:31's row, and its order meets the NEXT minute's quotes, 09:32's, at 09:33.
        shadow = live.shadow.accounts["vert@1:s"]
        self.assertEqual((len(shadow.positions), len(shadow.orders)), (0, 0))
        self.run_to(9, 32)
        self.assertEqual((len(shadow.positions), len(shadow.orders)), (0, 1))
        self.run_to(9, 33)
        self.assertEqual(len(shadow.positions), 1)
        self.run_to(9, 40)
        # Both closed after the program's hold: one shadow trade and one real trade on the forward record.
        rows = self.families.forward_rows("vert")
        self.assertEqual(sorted(r["source"] for r in rows), ["real", "shadow"])
        self.assertEqual(live.book.positions, {})
        sells = [p for p, a in self.ledger.of("book.fill") if p["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertIsInstance(sells[0]["realized"], float)
        self.assertEqual(self.live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False), [])

    def test_a_candidate_trades_shadow_only_while_real_money_is_off(self):
        live = self.make([family("vert", VERTICAL, band="probe")], real_money=False)
        self.run_to(9, 33)
        self.assertEqual(sorted(live.instances), ["vert@1:s"])
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")   # no Probe without real money
        self.assertEqual(self.venue.sent, [])

    def test_the_site_sees_structures_and_never_a_price(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 30})])
        self.run_to(9, 33)
        rows = live.site_inputs()["structures"]
        self.assertEqual(sorted(r["real"] for r in rows), [False, True])
        for r in rows:
            self.assertEqual(set(r), {"id", "agent", "underlying", "structure", "legs", "expiry", "quantity", "real", "opened_at",
                                      "max_loss_usd", "pnl_usd"})
            self.assertNotIn("SPY2", json.dumps(r))                             # no contract code, no strike


class Gates(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def test_no_grant_no_real_entry(self):
        self.grant.active = False
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 32)
        self.assertEqual(self.venue.sent, [])
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")

    def test_the_kill_switch_stops_entries_and_exits(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 2})])
        self.run_to(9, 31)
        self.assertEqual(len(self.venue.sent), 1)
        self.killed = True
        self.run_to(9, 36)
        self.assertEqual(len(self.venue.sent), 1)
        self.assertIn("kill switch", " ".join(self.refusals()))
        self.killed = False
        self.run_to(9, 37)
        self.assertEqual(len(self.venue.sent), 2)                          # the exit goes once the switch is off

    def test_a_tripped_stop_shuts_entries_but_not_exits(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 2})])
        self.run_to(9, 31)
        self.venue.equity = D("4000")                                      # -27% on the day: the daily stop
        self.run_to(9, 45)
        self.assertTrue(live.stops.daily_tripped)
        self.assertIn("daily stop", " ".join(self.refusals()))
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"])
        self.assertEqual(self.notices[0]["kind"], "live_stop")

    def test_the_paper_proof_comes_first(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 60})], config={"require_paper_proof": True})
        self.run_to(9, 34)
        self.assertEqual(self.venue.sent, [])
        self.assertIn("paper account has not yet proved", " ".join(self.refusals()))
        self.run_to(9, 45)
        self.assertEqual(live.proof.status()["status"], "passed")
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.paper.sent], ["buy_to_open", "sell_to_close"])
        opened = self.paper.sent[0]
        self.assertEqual((opened["qty"], opened["order_class"], len(opened["legs"])), ("1", "mleg", 2))

    def test_credit_structures_wait_for_two_thousand_dollars(self):
        self.venue.equity = self.venue.last_equity = D("1500")
        self.grant.capital = "1500"
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor")])
        self.run_to(9, 33)
        self.assertEqual(self.families.rows["condor"]["band"], "candidate")
        self.assertEqual(self.venue.sent, [])

    def test_reconciliation_freezes_entries_on_the_second_reading_and_exits_still_go(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 2, "opens": 3})])
        self.venue.held["SPY261016C00600000"] = D(1)                      # something the book does not hold
        self.run_to(9, 31)
        self.assertEqual(live.book.frozen, "")                             # one reading: perhaps a fill in flight
        self.run_to(9, 40)
        self.assertIn("SPY261016C00600000", live.book.frozen)
        self.assertIn("reconciliation", " ".join(self.refusals()))
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.venue.sent], ["buy_to_open", "sell_to_close"])
        self.assertTrue(any(n["stop"] == "reconciliation" for n in self.notices))


class OrderPathInTheLoop(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def test_buying_power_is_reserved_before_sending(self):
        self.venue.bp = D("50")                                           # far less than the Probe's structures need
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 32)
        self.assertEqual(self.venue.sent, [])
        self.assertTrue(any(w.startswith("buying power: it reserves") for w in self.refusals()), self.refusals())

    def test_a_working_order_is_cancelled_when_its_time_in_force_runs_out(self):
        timed = VERTICAL.replace('"limit": "natural", "tag": "t"', '"limit": {"price": 0.01}, "tif": 3, "tag": "t"')
        self.venue.fill = "none"
        live = self.make([family("vert", timed, band="probe", params={"hold": 600})])
        self.run_to(9, 33)
        self.assertEqual(self.venue.cancels, [])
        self.run_to(9, 34)
        self.assertEqual(len(self.venue.cancels), 1)
        self.assertEqual(self.venue.book[0]["status"], "canceled")

    def test_a_working_open_on_an_expiring_contract_is_cancelled_at_three(self):
        self.clock.set(at(MONDAY, 14, 57))
        resting = VERTICAL.replace('"limit": "natural", "tag": "t"', '"limit": {"price": 0.01}, "tag": "t"')
        self.venue.fill = "none"
        live = self.make([family("vert", resting, band="probe", params={"hold": 600, "dte": 0})])
        self.run_to(14, 59)
        self.assertEqual(self.venue.cancels, [])
        self.run_to(15, 0)
        self.assertEqual(len(self.venue.cancels), 1)

    def test_tuition_is_one_structure_and_never_evidence(self):
        live = self.make([family("pre", VERTICAL, band="gym", holdout=False, validation=True, params={"hold": 2})])
        self.run_to(9, 36)
        self.assertEqual(sorted(live.instances), ["pre@1:t"])
        opens = [b for b in self.venue.sent if b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual([b["qty"] for b in opens], ["1"])
        self.assertEqual(self.families.forward_rows("pre"), [])              # never evidence
        self.assertTrue(live.book.state.rows("SELECT tuition FROM orders WHERE action='open'")[0]["tuition"])


class Sized(LiveCase):
    def test_a_forward_record_that_earns_it_sizes_by_quarter_kelly_on_its_lower_bound(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        returns = [0.30, 0.10, 0.20, -0.10, 0.25] * 5
        self.families.add_forward("vert", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                       "max_loss": 100.0} for i, r in enumerate(returns)])
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "sized")
        [pos] = live.book.positions.values()
        fwd = M.forward_stats(self.families.forward_rows("vert"), 0.8)
        cap = M.structure_cap(live.table, "sized", min(D("5481.65"), D("5500")), fwd)
        self.assertGreater(cap, D("164.4495"))                            # more than a Probe's 3%
        self.assertLessEqual(pos.max_loss, float(cap))
        unit = pos.max_loss_share * 100 + 2 * pos.fees / pos.qty
        self.assertEqual(pos.qty, min(int(cap // D(str(round(unit, 2)))), int(D("822.2475") // D(str(round(unit, 2))))))


class ExpiryDay(LiveCase):
    def test_no_new_open_on_an_expiring_contract_from_three_and_the_near_money_close(self):
        self.clock.set(at(MONDAY, 14, 58))
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600, "dte": 0, "opens": 3})])
        self.run_to(14, 58)
        [first] = self.venue.sent
        self.assertIn("260928", first["legs"][0]["symbol"])
        self.clock.set(at(MONDAY, 15, 0))
        self.run_to(15, 14)
        # SPY's close cutoff is 15:25; the forced close starts ten minutes before it, at the natural.
        self.assertEqual(len(self.venue.sent), 1)
        self.run_to(15, 15)
        self.assertEqual(len(self.venue.sent), 2)
        self.assertEqual(self.venue.sent[1]["legs"][0]["position_intent"], "sell_to_close")
        self.assertEqual(live.book.positions, {})
        refused = [p["why"] for p, a in self.ledger.of("live.refusal")]
        self.assertTrue(any("expiry cutoff" in w for w in refused))


class Assignment(LiveCase):
    def test_an_assignment_freezes_entries_closes_the_shares_and_the_other_leg_and_books_the_trade(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        [pos] = live.book.positions.values()
        long_leg, short_leg = pos.legs
        # The short call is assigned early: the account holds its shares short instead of the contracts.
        contracts = self.venue.held[short_leg.symbol]
        self.assertLess(contracts, 0)
        self.venue.held[short_leg.symbol] = D(0)
        self.venue.held["SPY"] = contracts * 100
        self.venue.activity_rows.append({"id": "asn1", "activity_type": "OPASN", "symbol": short_leg.symbol,
                                         "qty": str(-contracts), "date": "2026-09-28"})
        live._activities_at = float("-inf")
        self.run_to(9, 33)
        stock = [b for b in self.venue.sent if b.get("symbol") == "SPY"]
        self.assertEqual([(b["side"], b["type"], b["qty"]) for b in stock], [("buy", "market", str(-contracts * 100))])
        self.assertTrue(any(n["stop"] == "assignment" for n in self.notices))
        legs_alone = [b for b in self.venue.sent if b.get("symbol") == long_leg.symbol]
        self.assertEqual([(b["side"], b["position_intent"]) for b in legs_alone], [("sell", "sell_to_close")])
        self.assertEqual(live.book.positions, {})
        sells = [p for p, a in self.ledger.of("book.fill") if p["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual(sells[0]["reason"], "broken: legs closed alone")
        self.assertIn("assign", " ".join(p["why"] for p, a in self.ledger.of("live.refusal")) or "assign")
        live._activities_at = float("-inf")
        self.run_to(9, 36)
        self.assertIsNone(live.state.get("assignment_latch"), "resolved: the latch lifts itself")


class TheClose(LiveCase):
    def test_index_structures_settle_in_cash_at_the_close_and_the_shadow_book_ends_its_day(self):
        self.clock.set(at(MONDAY, 14, 50))
        xsp = VERTICAL.replace('"SPY"', '"XSP"')
        live = self.make([family("xsp", xsp, band="probe", params={"hold": 600, "dte": 0})])
        self.run_to(14, 52)
        [pos] = live.book.positions.values()
        self.assertEqual((pos.root, pos.expiry), ("XSP", "2026-09-28"))
        self.run_to(15, 59)
        self.assertEqual(len(self.venue.sent), 1, "an index structure is held into its cash settlement")
        self.clock.set(at(MONDAY, 16, 0))
        out = live.minute()
        self.assertEqual(out["state"], "after the close")
        self.assertEqual(live.book.positions, {})
        [closed] = live.book.closed_trades()
        self.assertEqual(closed["family"], "xsp")
        level = live.day.chains["XSP"].underlying.price
        self.assertTrue(np.isfinite(level[389]))
        settled = live.state.rows("SELECT reason FROM positions")[0]["reason"]
        self.assertEqual(settled, "settled")
        shadow = live.shadow.accounts["xsp@1:s"]
        self.assertEqual(shadow.ended_day, live.day.ordinal)
        self.assertEqual({t["exit_reason"] for t in shadow.trades}, {"settled"})
        self.assertEqual(sorted(r["source"] for r in self.families.forward_rows("xsp")), ["real", "shadow"])
        # After the close the account's expiring contracts are the venue's to settle: no freeze for them.
        live.state.put("quiet_at", 0)
        self.clock.set(at(MONDAY, 16, 20))
        live.minute()
        live.state.put("quiet_at", 0)
        self.clock.set(at(MONDAY, 16, 40))
        live.minute()
        self.assertEqual(live.book.frozen, "")


class Owner(LiveCase):
    def test_the_owners_command_releases_the_drawdown_pause_through_the_live_state(self):
        import contextlib
        import io

        from league.live.__main__ import main

        live = self.make([family("vert", VERTICAL, band="probe")])
        live.stops.drawdown_tripped, live.stops.drawdown_why = True, "a test's drawdown"
        self.assertIn("real money paused", live.real_block())
        with contextlib.redirect_stdout(io.StringIO()):
            main(["--root", str(self.root), "--release-drawdown"])
        live.minute()
        self.assertFalse(live.stops.drawdown_tripped)
        self.assertIsNone(live.state.get("owner_release_drawdown"))
        self.assertTrue(any(p.get("released") for p, a in self.ledger.of("live.stop")))

    def test_a_program_that_dies_leaves_its_real_positions_to_the_house_to_close(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        self.assertEqual(len(live.book.positions), 1)
        inst = live.instances["vert@1:r"]
        inst.error, inst.fatal = "disqualified: 25 errors", True
        self.run_to(9, 33)
        self.assertEqual(live.book.positions, {})
        self.assertEqual(self.venue.sent[-1]["legs"][0]["position_intent"], "sell_to_close")


class AMissedClose(LiveCase):
    def test_an_index_structure_whose_close_the_house_missed_settles_at_its_last_recorded_level(self):
        self.clock.set(at(MONDAY, 15, 40))
        xsp = VERTICAL.replace('"SPY"', '"XSP"')
        live = self.make([family("xsp", xsp, band="probe", params={"hold": 600, "dte": 0})])
        live.state.put("paper_proof", {"status": "passed"})
        self.clock.set(at(MONDAY, 14, 55))
        self.run_to(14, 56)
        [pos] = live.book.positions.values()
        level = live.state.get("levels")["XSP"][0]
        # The House is away from 14:56 Monday to 09:31 Tuesday: it never saw the close.
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live.minute()
        self.assertEqual(live.book.positions, {})
        row = live.state.rows("SELECT reason, cash FROM positions WHERE pid=?", (pos.pid,))[0]
        self.assertIn("the House missed the close", row["reason"])
        self.assertEqual(sorted(r["source"] for r in self.families.forward_rows("xsp")), ["real"])
        self.assertTrue(level > 0)


class ExpiryDayWithoutData(LiveCase):
    def test_the_near_money_close_goes_on_the_last_quoted_minute_when_the_chain_read_fails(self):
        self.clock.set(at(MONDAY, 14, 58))
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600, "dte": 0})])
        self.run_to(14, 58)
        self.assertEqual(len(live.book.positions), 1)
        self.run_to(15, 14)
        self.market.dead.add("SPY")                                       # the 15:15 read fails
        self.run_to(15, 15)
        self.assertEqual(self.venue.sent[-1]["legs"][0]["position_intent"], "sell_to_close")


BAD = """
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0}
PARAMS = {}

def decide(ctx):
    return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": {"price": float("nan")},
             "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0}, {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
"""


class Isolation(LiveCase):
    def test_one_programs_malformed_intent_costs_its_own_intent_only(self):
        live = self.make([family("bad", BAD, band="probe"), family("vert", VERTICAL, band="probe", params={"hold": 4})])
        self.run_to(9, 40)
        closes = [b for b in self.venue.sent if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(len(closes), 1, "the other family's exit still goes")
        self.assertTrue(any("bad" == a for p, a in self.ledger.of("live.refusal")))
        self.assertFalse([e for e in live.state.events(kinds=["live.error"])])
        self.assertTrue(live.shadow.accounts["bad@1:s"].counts["rejected"] > 0)


MID_CLOSE = VERTICAL.replace('out.append({"close": p["id"], "limit": "natural", "note": "held long enough"})',
                             'out.append({"close": p["id"], "limit": "mid", "note": "held long enough"})')
RESTER = VERTICAL.replace('"limit": "natural", "tag": "t"', '"limit": {"price": 0.01}, "tag": "t"').replace(
    '"rel": 0, "offset": 1.0', '"rel": 0, "offset": 2.0')


class ExitsFirst(LiveCase):
    def test_a_programs_resting_close_never_blocks_the_forced_expiry_close(self):
        self.clock.set(at(MONDAY, 14, 50))
        live = self.make([family("vert", MID_CLOSE, band="probe", params={"hold": 10, "dte": 0})])
        self.run_to(14, 50)
        [pos] = live.book.positions.values()
        self.run_to(15, 14)
        # The program's own mid close rests from 15:00 (the fake fills only at the natural).
        mid = [b for b in self.venue.sent if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(len(mid), 1)
        self.run_to(15, 17)
        self.assertIn(self.venue.book[1]["id"], self.venue.cancels)         # the House cancelled it
        self.assertEqual(live.book.positions, {}, "the forced close at the natural took it before 15:25")
        self.assertEqual(live.state.rows("SELECT reason FROM positions WHERE pid=?", (pos.pid,))[0]["reason"], "forced")

    def test_a_program_close_inside_the_forced_window_is_the_houses(self):
        self.clock.set(at(MONDAY, 14, 50))
        live = self.make([family("vert", MID_CLOSE, band="probe", params={"hold": 26, "dte": 0})])
        self.run_to(15, 13)
        self.killed = True                                                  # the House's own close cannot go yet
        self.run_to(15, 16)
        self.assertTrue(any("the House is closing" in p["why"] for p, a in self.ledger.of("live.refusal")))
        self.killed = False
        self.run_to(15, 18)
        self.assertEqual(live.book.positions, {})
        pos = live.book.state.rows("SELECT reason FROM positions")[0]
        self.assertEqual(pos["reason"], "forced")

    def test_an_exit_cancels_another_familys_resting_open_on_its_contract(self):
        live = self.make([family("holder", VERTICAL, band="probe", params={"hold": 10}),
                          family("rester", RESTER, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        self.assertEqual(len(live.book.positions), 1)                       # the holder's vertical filled
        resting = [o for o in live.book.orders.values() if o.family == "rester"]
        self.assertEqual(len(resting), 1)
        self.run_to(9, 45)
        self.assertEqual([p.family for p in live.book.positions.values()], [])
        self.assertIn(resting[0].venue_id, self.venue.cancels)
        rejects = [p["why"] for p, a in self.ledger.of("live.refusal") if a == "rester"]
        self.assertTrue(any("an exit needs" in w for w in rejects) or live.book.state.rows(
            "SELECT answer FROM orders WHERE oid=?", (resting[0].oid,))[0]["answer"].find("an exit needs") >= 0)


CHURN = VERTICAL.replace('out.append({"close": p["id"], "limit": "natural", "note": "held long enough"})',
                         'out.append({"close": p["id"], "limit": {"price": 9.99}, "tif": 1, "note": "work it"})')


class OrderBudget(LiveCase):
    def test_a_real_instance_has_the_gyms_orders_a_day(self):
        self.venue.fill = "natural"
        live = self.make([family("vert", CHURN, band="probe", params={"hold": 1})], config={"instance_orders_day": 6})
        self.run_to(10, 30)
        sent = len(self.venue.sent)
        self.assertLessEqual(sent, 6)
        self.assertTrue(any("order budget" in p["why"] for p, a in self.ledger.of("live.refusal")))

    def test_program_closes_leave_the_room_forced_exits_need(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3})])
        self.run_to(9, 31)
        live.book._count("2026-09-28", 247)                                  # 249 with the open: no room for a program close
        self.run_to(9, 36)
        self.assertEqual(len(live.book.positions), 1)
        self.assertTrue(any("the day's order count" in p["why"] for p, a in self.ledger.of("live.refusal")))


class ShadowHeldLegs(LiveCase):
    def test_a_shadow_positions_legs_are_read_after_they_leave_the_programs_band(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 12})], real_money=False)
        self.run_to(9, 34)
        shadow = live.shadow.accounts["vert@1:s"]
        [pos] = shadow.positions.values()
        self.market.spot = 640.0                                              # +6.7%: the legs leave band 3% + 1%
        self.run_to(9, 50)
        self.assertEqual(shadow.positions, {}, "its close filled on the held legs' own quotes")
        self.assertEqual(shadow.trades[-1]["exit_reason"], "program")


class BrokenLegs(LiveCase):
    def test_long_legs_are_never_sold_while_a_short_leg_is_still_held(self):
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor")])
        self.run_to(9, 31)
        [pos] = live.book.positions.values()
        lp, sp, sc, lc = sorted(pos.legs, key=lambda l: (not l.is_call, l.strike))[::-1][::-1] if False else (None, None, None, None)
        shorts = [l for l in pos.legs if l.side < 0]
        put_short = next(l for l in shorts if not l.is_call)
        call_short = next(l for l in shorts if l.is_call)
        held = -self.venue.held[put_short.symbol]
        self.venue.held[put_short.symbol] = D(0)
        self.venue.held["SPY"] = held * 100
        self.venue.activity_rows.append({"id": "asn2", "activity_type": "OPASN", "symbol": put_short.symbol, "qty": str(held)})
        self.market.overrides[call_short.symbol] = (float("nan"), float("nan"), 0, 0)   # the short call cannot be priced
        live._activities_at = float("-inf")
        self.run_to(9, 40)
        singles = [b for b in self.venue.sent if b.get("symbol") and b.get("position_intent")]
        self.assertEqual(singles, [], "no long leg sold while the short call is held")
        del self.market.overrides[call_short.symbol]
        self.run_to(9, 50)
        intents = [(b["symbol"], b["position_intent"]) for b in self.venue.sent if b.get("position_intent")]
        self.assertEqual(intents[0], (call_short.symbol, "buy_to_close"), "the short leg first")
        per_leg = {}
        for b in self.venue.sent:
            if b.get("position_intent"):
                per_leg[b["symbol"]] = per_leg.get(b["symbol"], 0) + 1
        self.assertTrue(all(n <= 4 for n in per_leg.values()), per_leg)          # a leg is re-sent at most every 3 minutes
        self.assertEqual(live.book.positions, {})


class Restart(LiveCase):
    def test_a_restart_resumes_the_books(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 33)
        shadow_before = {k: len(a.positions) for k, a in live.shadow.accounts.items()}
        real_before = {p.pid: p.qty for p in live.book.positions.values()}
        live.state.close()
        again = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.assertEqual({p.pid: p.qty for p in again.book.positions.values()}, real_before)
        self.assertEqual({k: len(a.positions) for k, a in again.shadow.accounts.items()}, shadow_before)
        self.clock.set(self.clock() + 60)
        again.minute()
        self.assertEqual(len(self.venue.sent), 1)                          # nothing sent twice


if __name__ == "__main__":
    unittest.main()
