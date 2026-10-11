"""THE EQUITY LANE END TO END (release E1, integration): one captain-seeded BETA program from its birth to the Done meter,
through every package's real code, with only the venue and its market data faked.

The path (league/equity/INTERFACES.md section 11's flows, in order):
1. birth: `elane.birth_seeds` (swarm) writes the three A4 seeds as beta-lane families;
2. Validation: `elane.validate` (swarm) runs seed-overnight-spy on 2025 through `runner.Isolated` (core) in the decider's
   "equity" kind (hooks: `InlineDecider`, the child's own `_handle`, its pickle and JSON round trips), the screen's
   pre-check on its `series`;
3. the one sealed look: `elane.look` mints the gate's capability (core's store), runs the Train-era segments, the floor,
   the holdout and `screen.verdict` under the receipt pinned in the repository's policy.json (A11: receipt 2, the S2
   screen: its exact program floor, no pooled-t bar, t_H >= c_H,used), and makes the family a Candidate proven on the
   equity identity (core's evaluator);
4. the band decision: the EquityBook (book) reads the swarm's equity row (`bands.read(lanes=LANES)` through
   league/equity/families.py) and `bands.next_band` (swarm, money's `edm1` and `sized_up`) seats it at Probe;
5. a live session: the 16:30 decide on Friday's close (the bars through `MarketData.bars`, `ctx.inputs_from_fetch`, the
   decider's "decide"), Monday's 15:55 close-window buy sized by `sizing.size_entry` on `money.available_cash` and the
   shared budget's room (`real.probe_figures`, which counts the lot's open risk through the hook), Monday's decide, and
   Tuesday's 09:30:30 open sale; the closed lot exported to the forward record;
6. the morning audits, the twin (ops: `twins.equity_round` with the engine's `fill_price`) and the Done meter (ops:
   `dlane_report.report` over `eq_lots`), and the broker's fees posted by the book.

The market is synthetic (league/equity/synth.py: invented prices with a strong drift, so the seed passes its look and the
path goes on); no figure here is a market result. The live prices are the store's own official opens and closes (and two
invented sessions after it), quoted a half-spread wide, so the twin's gap is the book's rounding alone."""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.equity import LANES, config, screen, synth
    from league.equity import live as L
    from league.equity import schedule as S
    from league.equity.families import EquityFamilies
    from league.equity.runner import Isolated
    from league.equity.store import LOOK, EquityStore, mint_equity_gate_capability
    from league.live import money as M
    from league.live import real as R
    from league.live.decider import InlineDecider
    from league.live.paper import STOCK_BUY_KEY, STOCK_BUY_WITNESSES, STOCK_SELL_KEY, STOCK_WITNESSES, StockPaperProof
    from league.live.state import LiveState
    from league.ops import dlane_report as DR
    from league.ops import twins as TW
    from league.swarm import elane
    from league.swarm import settings as settings_mod
    from league.swarm.evaluator import equity_identity
    from league.swarm.gate import Gate, run_sha
    from league.swarm.store import SwarmStore
    from league.swarm.tournament import Tournament
    from league.tests import REAL_POLICY_PATH
    from league.tests.test_equity_book import Clock, Market, Venue, at

ON = {"elane": {"mode": "gate"}, "dlane": {"mode": "gate"}}
SEED = "seed-overnight-spy"
FRIDAY, MONDAY, TUESDAY, WEDNESDAY = (dt.date(2026, 10, 9), dt.date(2026, 10, 12), dt.date(2026, 10, 13),
                                      dt.date(2026, 10, 14))
E = D("2229")
#: The synthetic market (invented): a drift strong enough that the overnight seed passes the screen, a calm volatility.
MARKET = {"seed": 11, "drift": 0.9, "vol": 0.10}
#: The two sessions after the store's last (invented): (open, close) as multiples of the session before's close.
NEXT = {MONDAY: (1.001, 1.002), TUESDAY: (1.003, 0.999)}


def stamp(day: dt.date) -> str:
    """An Alpaca 1Day bar's `t` (the session's New York midnight in UTC), as league/equity/synth.py writes them."""
    return f"{day.isoformat()}T04:00:00Z"


@unittest.skipUnless(HAVE, "numpy not installed")
class TheEquityLaneEndToEnd(unittest.TestCase):
    def setUp(self):
        # The repository's committed policy.json, as the House reads it (the test package reads an empty one by
        # default, league/tests/__init__.py): its pinned receipt (A11: receipt 2, the S2 screen) and `elane.roster`.
        patcher = mock.patch.object(settings_mod, "POLICY_PATH", REAL_POLICY_PATH)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(at(dt.date(2026, 10, 11), 12, 0))       # Sunday Oct 11: the deploy, the data, the looks
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.store_root = synth.synthetic_store(self.root / elane.STORE_DIR, gate=True, **MARKET)
        self.runner = Isolated(InlineDecider(), self.store_root)

    # ------------------------------------------------------------------------------------------- the swarm's part
    def born_validated_and_looked(self) -> dict:
        born = elane.birth_seeds(self.store, ON)
        # Born in the declared order of the looks (league/swarm/seeds.py says why). This test follows SPY's seed, the
        # one that buys at every close, through the lane's parts by asking for its look directly; in a round the look
        # order is the declared one (league/tests/test_equity_rehearsal.py `TheSeedsDeclaredOrder`).
        self.assertEqual(born, ["seed-overnight-qqq", "seed-reversal-index", "seed-overnight-spy"])
        fam = self.store.family(SEED)
        version = self.store.version(SEED, fam["best_version"])
        self.assertEqual((fam["structure"], fam["spec"]["lane"], fam["band"]), ("etf", "beta", "gym"))

        tournament = Tournament(self.store, None, ON, clock=self.clock)
        tournament.equity_runner = self.runner
        # THE DECLARED ORDER IS STRICT WITHIN A LINEAGE (A18; `elane.seed_wait`): SPY's look is never taken while
        # QQQ's seed, declared before it in the overnight lineage, is alive without a verdict. On this invented
        # market QQQ's seed FAILS its Validation pre-check (no retry owed), so the lineage's one look is SPY's.
        ahead = self.store.family("seed-overnight-qqq")
        self.assertEqual(elane.seed_ahead(self.store, fam, ON), ahead["id"], "before the earlier seed's verdict")
        early = elane.validate(tournament, ahead, self.store.version(ahead["id"], ahead["best_version"]))
        self.assertFalse(early["entered"], early)
        self.assertIsNone(elane.seed_ahead(self.store, fam, ON))
        verdict = elane.validate(tournament, fam, version)
        self.assertTrue(verdict["entered"], verdict)
        state = self.store.family(SEED)["state"]
        self.assertTrue(state["gate_ready"])
        self.assertGreater(state[elane.SIGMA_KEY]["1"], 0, "EDM1's sigma recorded from the 1.0x run")
        runs = self.store.runs(SEED, window="validation")
        self.assertEqual(sorted(r["stress"] for r in runs), [config.K_BASE, config.K_STRESS])

        gate = Gate(self.store, None, None, ON, clock=self.clock)
        gate.equity_runner = self.runner
        sha = run_sha(version)
        self.assertTrue(elane.look(gate, self.store.family(SEED), version, sha))
        fam = self.store.family(SEED)
        self.assertEqual(fam["band"], "candidate")
        look = fam["state"][elane.LOOK_KEY]
        self.assertTrue(look["verdict"]["passed"], look)
        pinned = elane.screen_effective(ON, "beta")
        detail, verdict = self.store.looks()[-1]["detail"], look["verdict"]
        self.assertEqual(detail["receipt"], pinned["receipt"], "judged under the pinned receipt")
        # THE HOUSE SCREEN IS S2 (A11): no pooled-t bar (c_R 0, so no c_used); the look is the pre-check, the holdout's
        # sum above zero and t_H >= c_H,used = max(c_H_floor, c_pF1 + c_H_margin), the receipt's floor and margin and the
        # program's own exact floor.
        self.assertEqual((pinned["screen"], detail["screen"], verdict["screen"]), ("S2", "S2", "S2"))
        self.assertEqual((verdict["c_R"], pinned["c_R"], pinned["c_H_floor"], pinned["c_H_margin"]), (0.0, 0.0, 0.95, 0.05))
        self.assertNotIn("c_used", verdict)
        self.assertNotIn("c_used", detail)
        self.assertEqual(round(verdict["c_H"] * 100),
                         max(round(pinned["c_H_floor"] * 100), round((verdict["c_pF1"] + pinned["c_H_margin"]) * 100)))
        self.assertGreaterEqual(verdict["t_H"], verdict["c_H"])
        self.assertGreater(verdict["sum_h"], 0)
        self.assertEqual((detail["c_H"], detail["c_pF1"]), (verdict["c_H"], verdict["c_pF1"]))
        self.assertTrue(look["beside"].startswith(f"S2, c_R = 0 (no pooled-t bar), c_H,used = {verdict['c_H']:.2f}; "),
                        look["beside"])
        self.assertNotIn("{", look["beside"], "every placeholder of the receipt's line is filled")
        # S1-X's rate beside the S2 line is measured (an S1 floor of the same Train-era series), not "unmeasured".
        self.assertIsNotNone(verdict["fp_x"])
        self.assertNotIn("unmeasured", look["beside"])
        # The windows the receipt was calibrated for: Validation is calendar 2025's 250 sessions, and the holdout read
        # 2026-01-02 through the look cap, Friday Oct 9 (A12): exactly the 194 sessions.
        self.assertEqual(verdict["windows"], {"validation": screen.V_LENGTH, "holdout": screen.H_LENGTHS[0],
                                              "ok": True, "why": None})
        # The program floor is S2's own (the exact enumeration under receipt 2), the one the verdict was judged on.
        floor = fam["state"][elane.FLOOR_KEY]["1"]
        self.assertTrue(floor["eligible"])
        self.assertEqual((floor["screen"], floor["method"], sorted(floor["sets"])),
                         ("S2", screen.S2_METHOD, sorted(screen.S2_SETS)))
        self.assertEqual((floor["fp_cap"], floor["c_H_floor"], floor["c_H_margin"], floor["c_H_used"], floor["c_pF1"]),
                         (0.12, 0.95, 0.05, verdict["c_H"], verdict["c_pF1"]))
        self.assertTrue(screen.floor_fits(floor, screen.pinned_receipt(pinned["block"])))
        self.assertLessEqual(floor["holdout_only"], 0.12, "the holdout-only rate at c_H,used holds the cap by construction")
        identity = equity_identity()
        self.assertEqual(fam["state"]["banded_evaluator"],
                         {"engine": identity["engine"], "equity_sha256": identity["equity"], "run_sha": sha})
        return fam

    # ------------------------------------------------------------------------------------------- the venue's part
    def market_from_the_store(self, market: Market) -> dict[dt.date, tuple[float, float]]:
        """The fake market data's SPY bars: the store's own raw and adjusted rows through its last session (the venue
        knows the prices: the test reads the sealed days with a capability of its own), then the two invented sessions.
        Returns {day: (official open, official close)}."""
        capability = mint_equity_gate_capability(self.store_root, reason="the test plays the market")
        bars = EquityStore(self.store_root, gate=capability).bars(["SPY"], LOOK, history=30)
        raw = synth.bar_rows(bars, "SPY", bars.n - 1, adjustment="raw")
        adj = synth.bar_rows(bars, "SPY", bars.n - 1, adjustment="all")
        official = {FRIDAY: (raw[-1]["o"], raw[-1]["c"])}
        close = raw[-1]["c"]
        for day, (o, c) in NEXT.items():
            o, c = round(close * o, 4), round(close * o * c, 4)
            row = {"t": stamp(day), "o": o, "h": round(max(o, c) * 1.002, 4), "l": round(min(o, c) * 0.998, 4), "c": c,
                   "v": 25_000_000.0}
            raw.append(dict(row))
            adj.append(dict(row))       # no event after the store's last day: the adjusted rows are the raw ones
            official[day] = (o, c)
            close = c
        market.bar_rows["raw"]["SPY"], market.bar_rows["all"]["SPY"] = raw, adj
        return official

    @staticmethod
    def quote(market: Market, official: float) -> None:
        """SPY quoted a half-spread (`config.half_spread`) either side of an official price."""
        hs = D(str(config.half_spread("SPY")))
        px = D(str(official))
        market.quotes["SPY"] = ((px * (1 - hs)).quantize(D("0.01")), (px * (1 + hs)).quantize(D("0.01")))

    def test_a_seeded_program_from_birth_to_the_done_meter(self):
        self.born_validated_and_looked()

        # ---------------------------------------------------------------------------- the House's book
        market = Market(self.clock)
        official = self.market_from_the_store(market)
        venue = Venue(market, self.clock, cash=str(E))
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        self.addCleanup(state.close)
        for key, witnesses in ((STOCK_BUY_KEY, STOCK_BUY_WITNESSES), (STOCK_SELL_KEY, STOCK_WITNESSES)):
            state.put(key, {"schema": 1, "status": "passed", **{k: True for k in witnesses}})   # its own tests prove it
        table = M.Table.from_constitution()
        self.assertTrue(table.equity.enabled, "A10.2: the switch ships on")
        events, alerts = [], []
        book = L.EquityBook(state, venue, market, table, EquityFamilies(self.root), decider=InlineDecider(),
                            stock_proof=StockPaperProof(state, None, clock=self.clock), sizing_equity=lambda: E,
                            root=self.root, clock=self.clock, record=lambda kind, payload, agent=None:
                            events.append((kind, payload)), alert=lambda level, text: alerts.append((level, text)))

        def tick(day, hh, mm, ss=3):
            self.clock.set(at(day, hh, mm, ss))
            out = book.tick(self.clock(), account_row=venue.account(), positions=None, open_orders=None,
                            real_block=lambda opening=True: None, killed=lambda: False)
            self.assertFalse(out.get("errors"), out)
            return out

        # Friday's close, decided on the Sunday deploy (the catch-up decide for the last close): the band decision
        # seats the Candidate at Probe, and the program buys SPY at Monday's close.
        out = tick(dt.date(2026, 10, 11), 13, 0)
        self.assertEqual(self.store.family(SEED)["band"], "probe", out)
        inst = L.instance_key(SEED, 1)
        self.assertTrue(inst.endswith(L.REAL_SUFFIX))
        [buy] = [i for i in book.state.rows("SELECT * FROM eq_intents WHERE instance=?", (inst,))]
        self.assertEqual((buy["kind"], buy["symbol"], buy["at"], buy["decided_day"], buy["exec_day"]),
                         ("buy", "SPY", "close", FRIDAY.isoformat(), MONDAY.isoformat()))
        self.assertEqual(state.get("eq_decision")["day"], FRIDAY.isoformat())

        # Monday: nothing at the open; the close window's buy, sized on the House-wide cash and the shared budget.
        self.quote(market, official[MONDAY][0])
        tick(MONDAY, 9, 31)
        self.assertEqual(venue.sent, [])
        self.quote(market, official[MONDAY][1])
        tick(MONDAY, 15, 54)
        self.assertEqual(venue.sent, [], "not before 15:55")
        tick(MONDAY, 15, 55)
        [sent] = venue.sent
        self.assertTrue(sent["client_order_id"].startswith("lq-"))
        self.assertEqual((sent["symbol"], sent["side"], sent["type"], sent["time_in_force"]), ("SPY", "buy", "limit", "day"))
        [lot] = [L.Lot.of(r) for r in state.rows("SELECT * FROM eq_lots")]
        sleeve = table.equity.probe_sleeve_share * E
        self.assertEqual((lot.status, lot.entry_at, lot.opened_day, lot.probe), ("open", "close", MONDAY.isoformat(), True))
        self.assertLessEqual(lot.entry_notional, sleeve * D("0.5"), "the intent's half of a Probe sleeve, at most")
        [order] = state.rows("SELECT why, qty, limit_px FROM eq_orders")
        self.assertTrue(order["why"].startswith("entry (intent:"), order["why"])   # the intent bound, no cap cut it
        # THE PROBE SLEEVE IN FORCE (one of release E5-S's two numbers, read from the table's row): the seed asks for
        # half its sleeve, which is also the sleeve's own cap on one ETF, so its lot is `sleeve_share` x 0.5 x E AT
        # ITS LIMIT (the ask and the entry collar above it, to the cent), its shares floored to six places; it fills
        # at the ask, under it.
        from league.tests.equity_design import in_force

        self.assertEqual(table.equity.probe_sleeve_share, D(in_force()[1]))
        half = table.equity.probe_sleeve_share * D("0.5") * E
        self.assertEqual(table.equity.position_share["etf"], D("0.50"), "the sleeve's own cap on one ETF is that half")
        limit = D(order["limit_px"])
        self.assertEqual(D(order["qty"]), (half / limit).quantize(D("0.000001"), rounding="ROUND_DOWN"))
        self.assertEqual(lot.qty, D(order["qty"]))
        self.assertLessEqual(lot.qty * limit, half)
        self.assertGreater(lot.qty * limit, half - limit * D("0.000001"))
        self.assertEqual(lot.entry_px, market.quotes["SPY"][1], "a marketable limit filled at the ask")
        # The shared loss budget counts the lot's open risk at the ETF weight (both lanes, one budget).
        _, _, _, at_risk, _ = R.probe_figures(state.rows, day=MONDAY.isoformat(), table=table)
        self.assertEqual(at_risk, table.equity.open_risk_weight["etf"] * lot.qty * lot.entry_px)

        # Monday's decide: the lot bought at the close is sold at the next open (and SPY bought again at its close).
        out = tick(MONDAY, 16, 31)
        intents = {r["kind"]: r for r in state.rows("SELECT * FROM eq_intents WHERE decided_day=?", (MONDAY.isoformat(),))}
        self.assertEqual((intents["sell"]["lid"], intents["sell"]["at"], intents["sell"]["exec_day"]),
                         (lot.lid, "open", TUESDAY.isoformat()))
        self.assertEqual(intents["buy"]["at"], "close")

        # Tuesday: the morning audit of Monday's bars, then the open window's sale (never in the session it was bought).
        tick(TUESDAY, 8, 31)
        self.quote(market, official[TUESDAY][0])
        tick(TUESDAY, 9, 30, 33)
        self.assertEqual([b["side"] for b in venue.sent], ["buy", "sell"])
        closed = book._lot(lot.lid)
        self.assertEqual((closed.status, closed.exit_at, closed.exit_day, closed.reason),
                         ("closed", "open", TUESDAY.isoformat(), "program"))
        self.assertEqual(closed.exit_px, market.quotes["SPY"][0], "sold at the bid")
        self.assertEqual(venue.held["SPY"], D(0))
        self.assertEqual(closed.cash, closed.opened_qty * closed.exit_px - closed.entry_notional - closed.fees + closed.div)
        forward = self.store.forward(SEED)
        self.assertEqual([(r["trade_id"], r["source"]) for r in forward], [(f"eq-{lot.lid}", "real")])
        tick(TUESDAY, 16, 31)                                    # Tuesday's bars kept (the twin's exit day)
        tick(WEDNESDAY, 8, 31)                                   # and audited the next morning
        audits = {(r["day"], r["adjustment"]): r["audit"] for r in state.rows(
            "SELECT day, adjustment, audit FROM eq_bars WHERE symbol='SPY' AND day IN (?, ?)",
            (MONDAY.isoformat(), TUESDAY.isoformat()))}
        self.assertEqual(set(audits.values()), {"ok"}, audits)

        # The twin, in closed form from the official prices with the engine's fill function: the same fills.
        now = at(WEDNESDAY, 12, 0)
        judged = TW.equity_round(self.root, now=now, store=self.store)
        self.assertEqual(judged["judged"], {"priced": 1}, judged)
        twin = TW.equity_records(self.store)[f"eq:{lot.lid}"]
        self.assertTrue(twin["final"])
        self.assertEqual((twin["entry_official"], twin["exit_official"]), (official[MONDAY][1], official[TUESDAY][0]))
        self.assertLess(abs(twin["gap_bp"]), 0.5, twin)

        # The Done meter reads the close from eq_lots, counted from Oct 10, matched to its twin, labelled MARKET BETA.
        report = DR.report(self.root, settings=ON, now=now)
        done = report["done"]
        self.assertEqual((done["all"]["running"]["closes"], done["screen"]["running"]["closes"]), (1, 1))
        row = {c["pid"]: c for c in done["all"]["closes"]}[f"eq:{lot.lid}"]
        self.assertEqual((row["lane"], row["label"], row["fee_basis"]), ("beta", "MARKET BETA", "estimate"))
        self.assertEqual(D(str(row["pnl_usd"])), closed.cash.quantize(D("0.01")))
        self.assertEqual(done["without_seeded"]["all"]["running"]["closes"], 0, "Done read without the three seeds")

        # The broker's REG and TAF rows of Tuesday post the lot's fees: the close is then final on its fees.
        proceeds = closed.opened_qty * closed.exit_px
        venue.activity_rows = [
            {"id": "fee-1", "activity_type": "FEE", "date": TUESDAY.isoformat(), "net_amount": "-0.02",
             "description": f"REG fee for proceed of ${proceeds} of 1 trades"},
            {"id": "fee-2", "activity_type": "FEE", "date": TUESDAY.isoformat(), "net_amount": "-0.01",
             "description": "TAF fee for proceed of 1 trades"}]
        tick(WEDNESDAY, 9, 50)
        posted = book._lot(lot.lid)
        self.assertEqual((posted.info["fee_basis"], posted.fees), ("broker", D("0.03")))
        row = {c["pid"]: c for c in DR.report(self.root, settings=ON, now=now)["done"]["all"]["closes"]}[f"eq:{lot.lid}"]
        self.assertEqual(row["fee_basis"], "broker")
        self.assertEqual([a for a in alerts if a[0] == "error"], [])
        self.assertTrue(set(LANES) >= {row["lane"]})


if __name__ == "__main__":
    unittest.main()
