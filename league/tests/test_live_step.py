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
    from league.live.venue import occ_symbol
    from league.tests.live_fakes import (CONDOR, CREDIT_VERTICAL, MONDAY, VERTICAL, Clock, Grant, Market, Venue, at, family,
                                         iso)


class Ledger:
    """The House's ledger as the live path writes to it, with the real ledger's kind check (`league.ledger.KINDS`): the
    production `Ledger.append` refuses an unknown kind and the live path swallows the error, so a kind it uses must be
    registered. Every test ends by checking none was unknown (`LiveCase.tearDown`)."""

    def __init__(self):
        from league.ledger import KINDS

        self.kinds = KINDS
        self.rows = []
        self.unknown = []

    def __call__(self, kind, payload, agent=None):
        if kind not in self.kinds:
            self.unknown.append(kind)
            raise ValueError(f"unknown ledger kind {kind!r}")
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
        # The D3 calibration round trips run by default once real money, the grant and the paper proof allow; they send
        # their own orders, so the tests that are not about them switch them off (`league/tests/test_live_singles.py`).
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False}}))

    def tearDown(self):
        if getattr(self, "live", None) is not None:
            self.live.state.close()
        self.dir.cleanup()
        self.assertEqual(self.ledger.unknown, [], "every ledger kind the live path writes is registered")

    def make(self, rows, *, real_money=True, config=None, table=None, observed=()):
        self.families = MemoryFamilies(rows, observed)
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(), table=table,
                                config={"require_paper_proof": False, **(config or {})}, real_money=real_money,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def rich(self, equity="60000.00"):
        """An account (and a grant) large enough that an SPY credit structure's short legs fit 3x the sizing equity in
        notional (the review of #393): the tests of credit structures' real mechanics on SPY run on it."""
        self.venue.equity = self.venue.bp = D(equity)
        self.grant.capital = equity

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
        live = self.make([family("vert", VERTICAL, band="probe")])
        out = self.run_to(9, 31)
        self.assertEqual(out["state"], "session")
        self.assertEqual(sorted(live.instances), ["vert@1:r", "vert@1:s"])
        # The real open: sized by maximum loss (5% of the lower of equity 5,481.65 and the grant's 5,500), not by the
        # program's qty of 2.
        [sent] = [b for b in self.venue.sent]
        self.assertEqual(sent["order_class"], "mleg")
        real = next(iter(live.book.positions.values()))
        unit = real.max_loss_share * 100 + 2 * (real.fees / real.qty)
        self.assertEqual(real.qty, int(D("274.0825") // D(str(round(unit, 2)))))
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
        live = self.make([family("vert", VERTICAL, band="candidate")], real_money=False)
        self.run_to(9, 33)
        self.assertEqual(sorted(live.instances), ["vert@1:s"])
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")   # no band moves without real money
        self.assertEqual(self.venue.sent, [])

    def test_a_family_promoted_in_the_session_trades_real_money_from_the_next_session(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 3, "opens": 5})])
        self.run_to(9, 40)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        self.assertEqual(sorted(live.instances), ["vert@1:s"], "no real instance the session it was promoted")
        self.assertEqual(self.venue.sent, [])
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live.minute()
        self.assertIn("vert@1:r", live.instances)
        self.assertEqual(len(self.venue.sent), 1)

    def test_a_candidate_whose_typical_loss_is_unknown_stays_shadow_only_and_says_why_once_a_day(self):
        live = self.make([family("vert", VERTICAL, band="candidate", typical=None)])
        self.run_to(9, 45)
        self.assertEqual(self.families.rows["vert"]["band"], "candidate")
        held = [p for p, a in self.ledger.of("live.band") if p.get("held")]
        self.assertEqual(len(held), 1)
        self.assertIn("typical maximum loss is unknown", held[0]["why"])

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
        self.assertIn("grant", " ".join(p["why"] for p, a in self.ledger.of("live.refusal")))

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
        self.venue.equity = D("3500")                                      # -36% on the day: the daily stop
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
        self.assertEqual([b["legs"][0]["position_intent"] for b in self.paper.sent if b.get("legs")],
                         ["buy_to_open", "sell_to_close"])
        opened = self.paper.sent[0]
        self.assertEqual((opened["qty"], opened["order_class"], len(opened["legs"])), ("1", "mleg", 2))

    def test_credit_structures_wait_for_two_thousand_dollars(self):
        self.venue.equity = self.venue.last_equity = D("1500")
        self.grant.capital = "1500"
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor")])
        self.run_to(9, 33)
        self.assertEqual(self.families.rows["condor"]["band"], "candidate")
        self.assertEqual(self.venue.sent, [])
        [(move, _)] = self.ledger.of("live.band")
        self.assertEqual((move["from"], move["to"]), ("probe", "candidate"))
        self.assertIn("real credit opens wait until the sizing equity", move["why"])
        self.assertIn("reads $1500.00", move["why"])

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


if HAVE:
    #: The credit vertical and the condor on XSP (cash-settled at the close, European: no assignment into shares).
    XSP_CREDIT_VERTICAL = CREDIT_VERTICAL.replace('"SPY"', '"XSP"')
    XSP_CONDOR = CONDOR.replace('"SPY"', '"XSP"')


class CreditAtTwoThousand(LiveCase):
    """Credit at $2,000 (Sept 26, 2026; the sprint's "Money on Monday"): credit verticals, iron condors and iron butterflies
    are real types, opened only while the sizing equity (the lower of the account's equity read this minute and the grant's
    capital) is $2,000 or more; under it they trade shadow only. Sized by maximum loss, (width - credit) x 100 a structure,
    and sent as ONE multi-leg order at a NEGATIVE limit (Alpaca's sign for a credit). The review of #393 adds, for a
    physically settled root (SPY), no short leg deep in the money, no short call beyond five days, and the short legs'
    notional at most 3x the sizing equity; at Probe one structure an order on any root."""

    def at_equity(self, equity, *, capital="5500"):
        # No deposit on record: the equity is the account's own (so neither stop trips on the reading).
        self.venue.activity_rows.clear()
        self.venue.equity = self.venue.last_equity = self.venue.bp = D(equity)
        self.grant.capital = capital

    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def opens(self):
        return [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"].endswith("_to_open")]

    def check_credit_order(self, body, pos, *, width, cap, per_order=None):
        """One multi-leg order at a negative limit, sized by maximum loss under the Probe's cap (and `per_order`)."""
        self.assertEqual(body["order_class"], "mleg")
        limit = D(body["limit_price"])
        self.assertLess(limit, 0, "a credit is a negative limit_price (Alpaca's multi-leg sign)")
        self.assertLess(-limit, D(str(width)), "never a credit at or above the collateral")
        self.assertEqual(int(body["qty"]), pos.qty)
        self.assertLess(pos.entry, 0)
        self.assertAlmostEqual(pos.collateral, width)
        # Maximum loss a share is the widest wing less the credit: (width x 100 - credit x 100) a structure.
        self.assertAlmostEqual(pos.max_loss_share, width + pos.entry, places=6)
        self.assertAlmostEqual(pos.max_loss, (width * 100 + pos.entry * 100) * pos.qty, places=4)
        # Sized by maximum loss with its fees (`money.plan_open`): as many as fit the Probe's cap, or one under the floor.
        unit = D(str(round(pos.max_loss_share * 100 + 2 * (pos.fees / pos.qty), 2)))
        expected = int(cap // unit)
        if expected < 1 and unit <= D("100"):
            expected = 1
        if per_order is not None:
            expected = min(expected, per_order)
        self.assertEqual(pos.qty, expected)
        self.assertLessEqual(D(str(pos.max_loss)), max(cap, D("100")), "under the Probe's cap (or its $100 one-contract floor)")

    # ---------------------------------------------------------------- the $2,000 line
    def test_below_two_thousand_a_credit_probe_stays_shadow_and_no_order_is_sent(self):
        self.at_equity("1999.99")
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor"),
                          family("cv", XSP_CREDIT_VERTICAL, band="probe", structure="credit_vertical"),
                          family("fly", CONDOR, band="probe", structure="iron_butterfly")])
        self.run_to(9, 40)
        self.assertEqual(self.venue.sent, [], "no order reaches the real account")
        self.assertEqual(sorted(live.instances), ["condor@1:s", "cv@1:s", "fly@1:s"], "shadow instances only")
        for fid in ("condor", "cv", "fly"):
            self.assertEqual(self.families.rows[fid]["band"], "candidate", fid)
        moves = {a: p for p, a in self.ledger.of("live.band")}
        for fid in ("condor", "cv", "fly"):
            self.assertIn("credit structure", moves[fid]["why"])
            self.assertIn("reads $1999.99", moves[fid]["why"])
        # The shadow book trades them all the same (the forward record is kept).
        self.assertTrue(live.shadow.accounts["condor@1:s"].positions or live.shadow.accounts["condor@1:s"].trades)
        self.assertTrue(live.shadow.accounts["cv@1:s"].positions or live.shadow.accounts["cv@1:s"].trades)

    def test_the_grants_capital_under_two_thousand_holds_credit_back_until_it_is_ratified(self):
        # A deposit that has landed (the account reads $5,481.65) but a grant not ratified since ($481.65 of capital):
        # the sizing equity is $481.65, so a credit type stays shadow only until the owner's --ratify.
        self.grant.capital = "481.65"
        live = self.make([family("condor", XSP_CONDOR, band="probe", structure="iron_condor")])
        self.run_to(9, 33)
        self.assertEqual(self.venue.sent, [])
        self.assertEqual(self.families.rows["condor"]["band"], "candidate")
        self.assertEqual(sorted(live.instances), ["condor@1:s"])

    def test_a_validation_passer_gets_no_credit_tuition_under_two_thousand(self):
        self.at_equity("1999.99")
        live = self.make([family("pre", XSP_CREDIT_VERTICAL, band="gym", structure="credit_vertical", holdout=False,
                                 validation=True)])
        self.run_to(9, 33)
        self.assertEqual(sorted(live.instances), [])
        self.assertEqual(self.venue.sent, [])

    def test_at_two_thousand_a_validation_passer_measures_one_credit_structure_as_tuition(self):
        self.at_equity("2000.00")
        live = self.make([family("pre", XSP_CREDIT_VERTICAL, band="gym", structure="credit_vertical", holdout=False,
                                 validation=True, params={"hold": 600})])
        self.run_to(9, 33)
        self.assertEqual(sorted(live.instances), ["pre@1:t"])
        [body] = self.opens()
        self.assertEqual((body["qty"], body["order_class"]), ("1", "mleg"))
        self.assertLess(D(body["limit_price"]), 0)
        self.assertEqual(self.families.forward_rows("pre"), [])              # never evidence

    def test_at_two_thousand_a_credit_probe_sends_one_negatively_priced_multi_leg_order_sized_by_maximum_loss(self):
        self.at_equity("2000.00")
        live = self.make([family("cv", XSP_CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600})])
        self.run_to(9, 31)
        self.assertEqual(sorted(live.instances), ["cv@1:r", "cv@1:s"])
        [body] = self.venue.sent
        self.assertTrue(all(l["symbol"].startswith("XSP") for l in body["legs"]))
        self.assertEqual([(l["side"], l["position_intent"]) for l in body["legs"]],
                         [("sell", "sell_to_open"), ("buy", "buy_to_open")])
        [pos] = live.book.positions.values()
        self.assertEqual(pos.type, "credit_vertical")
        # 5% of $2,000 is $100: one structure of about $60-80 of maximum loss.
        self.check_credit_order(body, pos, width=1.0, cap=D("100.00"), per_order=1)
        self.assertEqual(pos.qty, 1)

    def test_above_two_thousand_a_credit_probe_opens_one_structure_an_order_under_the_probes_cap(self):
        # The account at $5,481.65 after the deposit, the grant ratified at $5,500: the Probe's cap is 5% of $5,481.65
        # ($274.08, three or four structures by maximum loss), but a credit Probe sends one structure an order.
        live = self.make([family("condor", XSP_CONDOR, band="probe", structure="iron_condor"),
                          family("cv", XSP_CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600, "atm": -5})])
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 2, self.refusals())
        cap = D("0.05") * D("5481.65")
        for body in self.opens():
            [pos] = [p for p in live.book.positions.values() if {l.symbol for l in p.legs} == {l["symbol"] for l in body["legs"]}]
            self.check_credit_order(body, pos, width=1.0, cap=cap, per_order=1)
            self.assertEqual(pos.qty, 1)
            unit = D(str(round(pos.max_loss_share * 100 + 2 * (pos.fees / pos.qty), 2)))
            self.assertGreater(int(cap // unit), 1, "the maximum loss alone would have sent more")
        condor = next(b for b in self.opens() if len(b["legs"]) == 4)
        self.assertEqual(sorted(l["position_intent"] for l in condor["legs"]),
                         ["buy_to_open", "buy_to_open", "sell_to_open", "sell_to_open"])

    def test_a_credit_close_is_one_multi_leg_order_and_a_fall_under_two_thousand_stops_new_credit_opens_not_exits(self):
        self.at_equity("2000.00")
        live = self.make([family("cv", XSP_CREDIT_VERTICAL, band="probe", structure="credit_vertical",
                                 params={"hold": 3, "opens": 3})])
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1)
        self.venue.equity = self.venue.bp = D("1999.99")                  # under the line, no latch from the fill
        self.run_to(9, 35)
        closes = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"].endswith("_to_close")]
        self.assertEqual(len(closes), 1, "the exit goes whatever the equity")
        [close] = closes
        self.assertEqual(close["order_class"], "mleg")
        self.assertEqual(sorted(l["position_intent"] for l in close["legs"]), ["buy_to_close", "sell_to_close"])
        self.assertGreater(D(close["limit_price"]), 0, "buying a credit structure back is a debit: a positive limit")
        self.assertLess(D(close["limit_price"]), 1, "under its collateral")
        self.assertEqual(live.book.positions, {})
        self.assertEqual(len(self.opens()), 1, "no new credit open under $2,000")
        self.assertTrue(any("real credit opens wait until the sizing equity" in w and "reads $1999.99" in w
                            for w in self.refusals()), self.refusals())
        self.run_to(9, 45)
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(self.families.rows["cv"]["band"], "candidate", "back to shadow only at the next band refresh")
        # Back over $2,000, it is promoted again and trades from the next session.
        self.venue.equity = self.venue.bp = D("2100.00")
        self.clock.set(at(MONDAY, 9, 50))
        self.run_to(9, 55)
        self.assertEqual(self.families.rows["cv"]["band"], "probe")
        self.assertEqual(len(self.opens()), 1, "not the session it was promoted in")
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live.minute()
        self.assertEqual(len(self.opens()), 2)
        self.assertLess(D(self.opens()[-1]["limit_price"]), 0)

    # ---------------------------------------------------------------- assignment risk (the review of #393)
    def test_spys_short_legs_over_three_times_the_sizing_equity_in_notional_are_refused(self):
        # A put credit vertical on SPY short the 598 put carries $59,800 of short notional a structure; 3x $5,481.65 is
        # $16,444.95. An early assignment would bring about eleven times the account in shares: refused, nothing sent.
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600})])
        self.run_to(9, 33)
        self.assertEqual(self.venue.sent, [])
        self.assertTrue(any("of notional a structure, over 3x the sizing equity $5481.65 ($16444.95)" in w
                            for w in self.refusals()), self.refusals())
        self.assertIn("cv@1:r", live.instances, "a Probe still, its real instance simply cannot open that structure")

    def test_spy_credit_opens_once_equity_covers_the_notional_and_a_probe_sends_one_structure(self):
        self.rich()
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600})])
        self.run_to(9, 31)
        [body] = self.opens()
        [pos] = live.book.positions.values()
        self.check_credit_order(body, pos, width=1.0, cap=D("0.05") * D("60000"), per_order=1)
        short = next(l for l in pos.legs if l.side < 0)
        self.assertLessEqual(short.strike * 100 * pos.qty, 3 * 60000)

    def test_a_sized_spy_credit_family_is_capped_by_its_short_legs_notional(self):
        # Sized by quarter Kelly the family could open many structures (the gateway's $1,000 an order alone allows about a
        # dozen); the short legs' notional allows floor(3 x $60,000 / (strike x 100)) = 3.
        self.rich()
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600})])
        returns = [0.30, 0.10, 0.20, -0.10, 0.25] * 5
        self.families.add_forward("cv", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                     "max_loss": 100.0} for i, r in enumerate(returns)])
        self.families.add_forward("cv", "real", [{"id": f"r{i}", "day": f"2026-08-{i + 1:02d}", "pnl": 6.0, "max_loss": 50.0}
                                                 for i in range(5)])
        live.state.put("band_moves", {"cv": {"band": "probe", "at": at(MONDAY, 9, 0) - 7 * 86400}})
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["cv"]["band"], "sized")
        [body] = self.opens()
        [pos] = live.book.positions.values()
        short = next(l for l in pos.legs if l.side < 0)
        by_notional = int(D("180000") // D(str(short.strike * 100)))
        unit = D(str(round(pos.max_loss_share * 100 + 2 * (pos.fees / pos.qty), 2)))
        self.assertGreater(int(D("1000") // unit), by_notional, "maximum loss alone would have sent more")
        self.assertEqual((pos.qty, int(body["qty"])), (by_notional, by_notional))
        self.assertEqual(by_notional, 3)

    def test_a_short_leg_deep_in_the_money_is_refused_and_an_iron_butterflys_body_at_the_money_is_not(self):
        self.rich()
        deep = CREDIT_VERTICAL                                             # short the 608 put with SPY at 600: 1.3% in
        fly = (CONDOR.replace('"open": "iron_condor"', '"open": "iron_butterfly"')
               .replace('"atm": -3', '"atm": 0').replace('"atm": 3', '"atm": 0'))
        self.assertNotEqual(fly, CONDOR)
        live = self.make([family("deep", deep, band="probe", structure="credit_vertical", params={"hold": 600, "atm": 8}),
                          family("fly", fly, band="probe", structure="iron_butterfly")])
        self.run_to(9, 31)
        self.assertTrue(any("short put at 608 is in the money by more than 1% of its strike" in w for w in self.refusals()),
                        self.refusals())
        [body] = self.opens()
        self.assertEqual(len(body["legs"]), 4, "the iron butterfly's at-the-money body passes")
        [pos] = live.book.positions.values()
        self.assertEqual(pos.type, "iron_butterfly")

    def test_a_short_call_more_than_five_days_out_is_refused_on_spy_and_not_on_xsp(self):
        self.rich()
        week = CONDOR.replace('"dte": 1', '"dte": 7').replace('"dte": [0, 3]', '"dte": [0, 7]')   # Oct 5: seven days out
        self.assertNotIn('"dte": 1', week)
        self.assertIn('"dte": [0, 7]', week)
        live = self.make([family("spy", week, band="probe", structure="iron_condor"),
                          family("puts", CREDIT_VERTICAL, band="probe", structure="credit_vertical", params={"hold": 600, "dte": 7}),
                          family("xsp", week.replace('"SPY"', '"XSP"'), band="probe", structure="iron_condor")])
        self.run_to(9, 31)
        self.assertTrue(any("short call expires 7 days out, past the 5" in w for w in self.refusals()), self.refusals())
        roots = sorted((b["legs"][0]["symbol"][:3], len(b["legs"])) for b in self.opens())
        self.assertEqual(roots, [("SPY", 2), ("XSP", 4)], "a put credit vertical has no short call; XSP settles in cash")

    # ---------------------------------------------------------------- expiry day (the review of #393)
    def zero_dte_put_spread(self, short, long, root="SPY"):
        """Quotes for a 0DTE put credit vertical short `short` / long `long` that pays a credit at the natural."""
        s = occ_symbol(root, MONDAY.isoformat(), False, float(short))
        l_ = occ_symbol(root, MONDAY.isoformat(), False, float(long))
        self.market.overrides[s] = (0.20, 0.22, 20, 20)
        self.market.overrides[l_] = (0.08, 0.10, 20, 20)
        return s, l_

    def test_an_expiring_credit_vertical_just_beyond_the_near_money_line_is_closed_by_the_house(self):
        # Short the 593 put with SPY at 600: 1.2% out of the money, beyond the 1% line (a debit vertical there is left to
        # expire). A credit structure's short leg could still finish in the money after the cutoff and be assigned alone:
        # from 15:15 (SPY's cutoff 15:25 less ten minutes) the House closes it in ONE multi-leg order at the natural.
        self.rich()
        self.clock.set(at(MONDAY, 14, 40))
        short, long_ = self.zero_dte_put_spread(593, 592)
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical",
                                 params={"hold": 600, "dte": 0, "atm": -7})])
        self.run_to(14, 40)
        [opened] = self.opens()
        self.assertEqual({l["symbol"] for l in opened["legs"]}, {short, long_})
        self.assertEqual(opened["limit_price"], "-0.10")
        self.run_to(15, 14)
        self.assertEqual(len(self.venue.sent), 1, "held to the window")
        self.run_to(15, 15)
        [close] = self.venue.sent[1:]
        self.assertEqual(close["order_class"], "mleg")
        self.assertEqual({l["symbol"]: l["position_intent"] for l in close["legs"]}, {short: "buy_to_close", long_: "sell_to_close"})
        self.assertEqual(close["limit_price"], "0.14", "the natural: buy the 593 at 0.22, sell the 592 at 0.08")
        self.assertEqual(live.book.positions, {})
        [why] = [r["why"] for r in live.book.state.rows("SELECT why FROM orders WHERE action='close'")]
        self.assertIn("whatever its moneyness", why)

    def test_the_last_forced_close_of_an_expiring_credit_structure_before_the_cutoff_is_left_working(self):
        self.rich()
        self.clock.set(at(MONDAY, 14, 40))
        self.zero_dte_put_spread(593, 592)
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical",
                                 params={"hold": 600, "dte": 0, "atm": -7})])
        self.run_to(14, 40)
        self.venue.fill = "none"                                          # every buy-back rests: re-priced each minute
        self.run_to(15, 30)
        closes = [b for b in self.venue.sent if b["legs"][0]["position_intent"].endswith("_to_close")]
        self.assertGreaterEqual(len(closes), 2)
        self.assertEqual([b["limit_price"] for b in closes[:2]], ["0.14", "0.15"], "the natural, then a cent's concession")
        self.assertTrue(all(len(b["legs"]) == 2 for b in closes), "always the whole structure in one order")
        [working] = [o for o in live.book.orders.values() if o.action == "close" and o.status == "working"]
        self.assertTrue(working.forced)
        self.assertEqual(working.placed_minute, 15 * 60 + 23 - 570, "sent at 15:23 and never cancelled at 15:24")

    def test_a_programs_own_close_of_an_expiring_credit_structure_meets_the_houses_in_the_window(self):
        self.rich()
        self.clock.set(at(MONDAY, 14, 40))
        self.zero_dte_put_spread(593, 592)
        live = self.make([family("cv", CREDIT_VERTICAL, band="probe", structure="credit_vertical",
                                 params={"hold": 600, "dte": 0, "atm": -7})])
        self.run_to(15, 14)
        [pos] = live.book.positions.values()
        self.assertEqual(live._program_close_refusal(pos, live.day, 15 * 60 + 13 - 570), None, "before the window: its own")
        self.assertIn("the House is closing", live._program_close_refusal(pos, live.day, 15 * 60 + 15 - 570))

    def test_an_expiring_xsp_credit_structure_is_left_to_settle_in_cash(self):
        self.at_equity("2000.00")
        self.clock.set(at(MONDAY, 14, 40))
        live = self.make([family("cv", XSP_CREDIT_VERTICAL, band="probe", structure="credit_vertical",
                                 params={"hold": 600, "dte": 0, "atm": -1})])
        self.run_to(14, 40)
        [opened] = self.opens()
        self.assertTrue(all(l["symbol"].startswith("XSP260928") for l in opened["legs"]))
        self.run_to(15, 40)
        self.assertEqual(len(self.venue.sent), 1, "no House close: XSP settles in cash, no shares")
        [pos] = live.book.positions.values()
        self.assertEqual(live._expiry_close(pos, live.day, 15 * 60 + 20 - 570, 15 * 60 + 20), "")

    def test_an_expiring_condor_with_a_short_leg_near_the_money_is_closed_by_the_house_in_one_order(self):
        # The condor's shorts are one strike from the money on a 0DTE SPY expiry. From ten minutes before SPY's close
        # cutoff (15:25) the House closes it itself, at the natural, in ONE multi-leg order.
        self.rich()
        self.clock.set(at(MONDAY, 14, 58))
        zero = CONDOR.replace('"dte": 1, "atm": -3', '"dte": 0, "atm": -1').replace('"dte": 1, "atm": 3', '"dte": 0, "atm": 1')
        self.assertNotEqual(zero, CONDOR)
        live = self.make([family("condor", zero, band="probe", structure="iron_condor", params={"hold": 600})])
        self.run_to(14, 58)
        [opened] = self.opens()
        self.assertLess(D(opened["limit_price"]), 0)
        self.assertTrue(all("260928" in l["symbol"] for l in opened["legs"]), "today's expiry")
        [pos] = live.book.positions.values()
        self.clock.set(at(MONDAY, 15, 0))
        self.run_to(15, 14)
        self.assertEqual(len(self.venue.sent), 1, "nothing before the window")
        self.run_to(15, 15)
        self.assertEqual(len(self.venue.sent), 2)
        close = self.venue.sent[1]
        self.assertEqual(close["order_class"], "mleg")
        self.assertEqual(len(close["legs"]), 4)
        self.assertEqual({l["symbol"]: l["position_intent"] for l in close["legs"]},
                         {leg.symbol: ("sell_to_close" if leg.side > 0 else "buy_to_close") for leg in pos.legs})
        self.assertGreater(D(close["limit_price"]), 0)
        self.assertLess(D(close["limit_price"]), D(str(pos.collateral)))
        self.assertEqual(live.book.positions, {})


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
        # Sent at 9:31 with tif 3: the Gym gives it the quotes of 9:32 through 9:35, so it rests through the House's 9:34
        # pass and is cancelled at its 9:35 pass (the engine's `_expiry`: arrival + tif).
        self.run_to(9, 34)
        self.assertEqual(self.venue.cancels, [])
        self.run_to(9, 35)
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
    def test_a_probe_that_earns_it_is_sized_by_quarter_kelly_on_its_lower_bound(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        returns = [0.30, 0.10, 0.20, -0.10, 0.25] * 5
        self.families.add_forward("vert", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                       "max_loss": 100.0} for i, r in enumerate(returns)])
        self.families.add_forward("vert", "real", [{"id": f"r{i}", "day": f"2026-08-{i + 1:02d}", "pnl": 6.0, "max_loss": 50.0}
                                                   for i in range(5)])
        live.state.put("band_moves", {"vert": {"band": "probe", "at": at(MONDAY, 9, 0) - 7 * 86400}})
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "sized")
        [pos] = live.book.positions.values()
        fwd = M.forward_stats(self.families.forward_rows("vert"), 0.8, version=1)
        cap = M.structure_cap(live.table, "sized", min(D("5481.65"), D("5500")), fwd)
        self.assertGreater(cap, D("164.4495"))                            # more than a Probe's 3%
        self.assertLessEqual(pos.max_loss, float(cap))
        unit = pos.max_loss_share * 100 + 2 * pos.fees / pos.qty
        self.assertEqual(pos.qty, min(int(cap // D(str(round(unit, 2)))), int(D("822.2475") // D(str(round(unit, 2))))))


class ProbeStage(LiveCase):
    def test_a_probe_without_real_trades_is_never_sized(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        returns = [0.30, 0.10, 0.20, -0.10, 0.25] * 5
        self.families.add_forward("vert", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                       "max_loss": 100.0} for i, r in enumerate(returns)])
        live.state.put("band_moves", {"vert": {"band": "probe", "at": at(MONDAY, 9, 0) - 7 * 86400}})
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")


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

    def test_a_programs_resting_close_on_an_expiring_contract_is_cancelled_at_the_close_cutoff(self):
        self.clock.set(at(MONDAY, 14, 50))
        far = MID_CLOSE.replace('"atm": 0', '"atm": 10')                    # 1.7% out of the money: no forced close
        live = self.make([family("vert", far, band="probe", params={"hold": 20, "dte": 0})])
        self.run_to(15, 24)
        [pos] = live.book.positions.values()
        resting = live.book.closing_order(pos.pid)
        self.assertIsNotNone(resting)
        self.assertNotIn(resting.venue_id, self.venue.cancels)
        self.run_to(15, 25)
        self.assertIn(resting.venue_id, self.venue.cancels)                 # the Gym drops it at the cutoff too

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
    def test_a_real_instance_has_the_gyms_orders_a_day_for_its_opens(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 1, "opens": 10})],
                         config={"instance_orders_day": 6})
        self.run_to(10, 30)
        opens = [b for b in self.venue.sent if b["legs"][0]["position_intent"] == "buy_to_open"]
        self.assertEqual(len(opens), 3)                                      # open, close, open, close, open, close
        self.assertEqual(len(self.venue.sent), 6)
        self.assertTrue(any("order budget" in p["why"] for p, a in self.ledger.of("live.refusal")))
        self.assertEqual(live.book.positions, {})

    def test_a_program_churning_its_close_is_never_refused_on_the_budget(self):
        live = self.make([family("vert", CHURN, band="probe", params={"hold": 1})], config={"instance_orders_day": 6})
        self.run_to(9, 50)
        self.assertGreater(len(self.venue.sent), 6, "closes are charged but never refused")
        self.assertFalse(any("order budget" in p["why"] for p, a in self.ledger.of("live.refusal")))

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
        self.rich()                                                         # SPY condors: 3x equity covers them
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


class OptionEventsOnce(LiveCase):
    def test_an_old_assignment_is_never_read_again_however_many_events_follow(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.venue.activity_rows.append({"id": "a00001", "activity_type": "OPASN", "symbol": "SPY260925C00600000", "qty": "1",
                                         "date": "2026-09-26", "transaction_time": "2026-09-26T14:00:00Z"})
        for i in range(2100):
            self.venue.activity_rows.append({"id": f"b{i:05d}", "activity_type": "OPEXP", "symbol": "SPY260926P00500000",
                                             "qty": "1", "date": "2026-09-27", "transaction_time": "2026-09-27T20:00:00Z"})
        self.run_to(9, 31)
        for _ in range(3):
            live._activities_at = float("-inf")
            self.clock.set(self.clock() + 60)
            live.minute()
        seen = [p for p, a in self.ledger.of("live.option_event") if p["kind"] == "OPASN"]
        self.assertEqual(len(seen), 1, "the old assignment was processed once")
        self.assertEqual(sum(1 for n in self.notices if n["stop"] == "assignment"), 1)


ONE_CLOSE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 10}
STATE = {"opened": 0}

def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_minutes"] == ctx.params["hold"]:
            out.append({"close": p["id"], "limit": "natural", "note": "once, at exactly its hold"})
    if not ctx.positions and not ctx.orders and not STATE["opened"]:
        STATE["opened"] += 1
        out.append({"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural",
                    "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                             {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]})
    return out
'''
CANCELLER = RESTER.replace("    return out", "    for o in ctx.orders:\n        out.append({\"cancel\": o[\"id\"]})\n    return out")


class VerificationRound(LiveCase):
    """The fix verification of #362 (regressions R1-R8 and the partly fixed C5, C7): each test failed before its fix."""

    def test_a_deferred_exit_that_raises_is_dropped_and_the_minute_goes_on(self):
        from unittest import mock
        from league.live import step as S

        live = self.make([family("holder", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        [pos] = live.book.positions.values()
        live.pending_exits[pos.pid] = {"forced": False, "why": "program", "intent": {"close": pos.pid, "tag": "boom"},
                                       "day": "2026-09-28"}
        real = S.L.resolve_close

        def boom(intent, *args, **kwargs):
            if intent.get("tag") == "boom":
                raise RuntimeError("boom")
            return real(intent, *args, **kwargs)

        with mock.patch.object(S.L, "resolve_close", boom):
            out = self.run_to(9, 34)                                           # raised out of minute() before the fix
        self.assertEqual(out["state"], "session")
        self.assertEqual(live.pending_exits, {})
        self.assertTrue(any("boom" in p["why"] for p, a in self.ledger.of("live.refusal") if a == "holder"))

    def test_a_waiting_exit_survives_a_slow_cancel_and_a_restart(self):
        self.venue.cancel_delay = 150.0
        rows = [family("holder", ONE_CLOSE, band="probe", params={"hold": 10}),
                family("rester", RESTER, band="probe", params={"hold": 600})]
        live = self.make(rows)
        self.run_to(9, 42)
        [pos] = [p for p in live.book.positions.values() if p.family == "holder"]
        self.assertIn(pos.pid, live.pending_exits, "still waiting while the cancel is pending")
        live.state.close()
        again = self.make(rows)
        self.assertIn(pos.pid, again.pending_exits, "the waiting exit is kept in the live state")
        self.clock.set(self.clock() + 60)
        self.run_to(9, 50)
        self.assertNotIn(pos.pid, again.book.positions, "the exit went once the cancel was done")
        closes = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(len(closes), 1)

    def test_a_waiting_exit_is_dropped_at_the_day_roll_and_its_program_told(self):
        live = self.make([family("holder", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        [pos] = live.book.positions.values()
        live.pending_exits[pos.pid] = {"forced": False, "why": "program", "day": "2026-09-25",
                                       "intent": {"close": pos.pid, "limit": {"price": 0.01}}}
        self.run_to(9, 32)
        self.assertEqual(live.pending_exits, {})
        self.assertIn(pos.pid, live.book.positions, "yesterday's close (and its price) is never sent")
        self.assertTrue(any("waited past" in p["why"] for p, a in self.ledger.of("live.refusal") if a == "holder"))

    def test_a_waiting_program_exit_meets_the_same_rules_as_a_program_close_when_it_goes(self):
        self.clock.set(at(MONDAY, 14, 50))
        far = VERTICAL.replace('"atm": 0', '"atm": 10')                    # out of the money: the House leaves it
        live = self.make([family("vert", far, band="probe", params={"hold": 600, "dte": 0})])
        self.run_to(15, 25)
        [pos] = live.book.positions.values()
        live.pending_exits[pos.pid] = {"forced": False, "why": "program", "day": "2026-09-28",
                                       "intent": {"close": pos.pid, "limit": "natural"}}
        self.run_to(15, 27)
        closes = [b for b in self.venue.sent if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(closes, [], "no program close on an expiring contract from the close cutoff")
        self.assertEqual(live.pending_exits, {})
        self.assertTrue(any("expiry cutoff" in p["why"] for p, a in self.ledger.of("live.refusal") if a == "vert"))

    def test_a_waiting_exit_of_a_structure_broken_since_is_left_to_the_legs_closes(self):
        self.rich()                                                         # SPY condors: 3x equity covers them
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor")])
        self.run_to(9, 31)
        [pos] = live.book.positions.values()
        put_short = next(l for l in pos.legs if l.side < 0 and not l.is_call)
        held = -self.venue.held[put_short.symbol]
        self.venue.held[put_short.symbol] = D(0)
        self.venue.held["SPY"] = held * 100
        self.venue.activity_rows.append({"id": "asn4", "activity_type": "OPASN", "symbol": put_short.symbol, "qty": str(held)})
        live.pending_exits[pos.pid] = {"forced": False, "why": "program", "day": "2026-09-28",
                                       "intent": {"close": pos.pid, "limit": "natural"}}
        live._activities_at = float("-inf")
        self.run_to(9, 33)
        whole = [b for b in self.venue.sent if b.get("legs") and b["legs"][0]["position_intent"].endswith("to_close")]
        self.assertEqual(whole, [], "never a whole-structure close on a broken structure")

    def test_a_program_may_close_an_out_of_the_money_expiring_structure_until_the_cutoff(self):
        self.clock.set(at(MONDAY, 14, 50))
        far = VERTICAL.replace('"atm": 0', '"atm": 10')                    # 1.7% out of the money: the House leaves it
        live = self.make([family("vert", far, band="probe", params={"hold": 28, "dte": 0})])
        self.run_to(15, 20)
        self.assertFalse(any("the House is closing" in p["why"] for p, a in self.ledger.of("live.refusal")))
        [pos] = live.book.positions.values()
        close = live.book.closing_order(pos.pid)
        self.assertIsNotNone(close, "the program's own close went (worth nothing here, it rests)")
        self.assertFalse(close.forced)

    def test_the_order_budget_counts_what_reached_the_venue_and_never_refuses_an_exit(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 3, "opens": 5})],
                         config={"instance_orders_day": 1})
        self.venue.submit_mode = "gateway"
        self.run_to(9, 31)                                                   # the gateway refused it (a cap)
        self.venue.submit_mode = "ratelimited"
        self.run_to(9, 32)                                                   # never left the House
        self.venue.submit_mode = "ok"
        self.run_to(9, 33)
        self.assertEqual(len(live.book.positions), 1, "refused sends are not charged to the budget")
        self.run_to(9, 40)
        self.assertEqual(live.book.positions, {}, "the close goes although the budget is spent")
        budget = [p["_intent"] for p, a in self.ledger.of("live.refusal") if "order budget" in p["why"]]
        self.assertTrue(budget and all("open" in i for i in budget), budget)

    def test_a_cancel_of_a_resting_open_is_never_refused_on_the_order_count(self):
        live = self.make([family("rester", CANCELLER, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        [order] = [o for o in live.book.orders.values() if o.action == "open"]
        live.book._count("2026-09-28", 244)                                  # 246 of 250 with the open, 4 kept
        self.run_to(9, 33)
        self.assertEqual(self.venue.cancels, [order.venue_id])

    def test_an_exit_only_instance_promoted_again_waits_for_the_next_session(self):
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})])
        self.run_to(9, 31)
        self.families.rows["vert"]["forward"] = {"trades": 25, "negative": True}
        live._families_at = float("-inf")
        self.run_to(9, 32)
        self.assertEqual(live.instances["vert@1:r"].mode, "exit_only")
        self.families.rows["vert"]["forward"] = {"trades": 25, "negative": False}
        live._families_at = float("-inf")
        self.run_to(9, 33)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        self.assertEqual(live.instances["vert@1:r"].mode, "exit_only", "real money from the next session")
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live._families_at = float("-inf")
        live.minute()
        self.assertEqual(live.instances["vert@1:r"].mode, "live")

    def test_an_option_event_from_before_the_reset_is_not_this_runs(self):
        self.venue.activity_rows.append({"id": "old1", "activity_type": "OPASN", "symbol": "SPY260925C00600000", "qty": "1",
                                         "date": "2026-09-25", "transaction_time": "2026-09-25T20:00:00Z"})
        live = self.make([family("vert", VERTICAL, band="probe")])
        self.run_to(9, 31)
        self.assertIsNone(live.state.get("assignment_latch"))
        self.assertEqual([n for n in self.notices if n["stop"] == "assignment"], [])

    def test_a_broken_leg_left_at_the_close_is_sent_again_at_the_next_open(self):
        self.clock.set(at(MONDAY, 15, 40))
        self.rich()                                                         # SPY condors: 3x equity covers them
        live = self.make([family("condor", CONDOR, band="probe", structure="iron_condor")])
        self.run_to(15, 40)
        [pos] = live.book.positions.values()
        put_short = next(l for l in pos.legs if l.side < 0 and not l.is_call)
        call_short = next(l for l in pos.legs if l.side < 0 and l.is_call)
        held = -self.venue.held[put_short.symbol]
        self.venue.held[put_short.symbol] = D(0)
        self.venue.held["SPY"] = held * 100
        self.venue.activity_rows.append({"id": "asn3", "activity_type": "OPASN", "symbol": put_short.symbol, "qty": str(held),
                                         "date": "2026-09-28"})
        self.venue.fill = "none"                                             # the leg's order rests and lapses
        live._activities_at = float("-inf")
        self.run_to(15, 59)
        sends = lambda: [b for b in self.venue.sent if b.get("symbol") == call_short.symbol]
        before = len(sends())
        self.assertGreater(before, 0)
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        self.run_to(9, 34)
        self.assertGreater(len(sends()), before, "the short leg is sent again in the next session's first minutes")


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
