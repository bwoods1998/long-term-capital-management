"""THE OWNER'S GOAL V3's money rows (release 1019l, the captain's A138), on the table in force.

"I accept losing my entire Alpaca balance. Use it. ... every seatable program trades real money from its first event at
up to 5% of equity a position ... a bug stop that pauses new entries after a 25% loss in one session". Release 1019l
moved five rows and three bounds and the Done reader's total, nothing else: a learning position 0.02 -> 0.05 of E and
a Probe one 0.035 -> 0.05 (a learning position is never larger than a Probe one), the shared loss budget $400 a window
and $800 in total -> $1,900 each, the daily stop 0.35 -> 0.25. The name's wall stays 0.10 here and at the gateway.
The earlier releases' tests of the same mechanisms run on release 1019i's table (league/tests/v2_walls.py)."""
from __future__ import annotations

import datetime as dt
import json
import unittest
from decimal import Decimal as D

from league import constitution as K
from league.events import book as EB
from league.equity import live as L
from league.events import done as DN
from league.events import programs as P
from league.live import money as M
from league.swarm.evaluator import equity_fingerprint, execution_fingerprint
from league.tests import equity_design as X
from league.tests import test_events_book as TB
from league.tests.evl6_fakes import on_1019h

NOW = dt.datetime(2026, 10, 23, 12, 0, tzinfo=dt.timezone.utc)


class TheRows(unittest.TestCase):
    def test_the_five_rows_and_three_bounds_in_force(self):
        ev = K.CONSTITUTION["equity_money"]["event"]
        self.assertEqual(ev["position_share"], {"learning": "0.05", "probe": "0.05", "sized": "0.10"})
        self.assertEqual((ev["one_share_max"]["learning"], ev["per_name_share"]), ("0.05", "0.10"))
        om = K.CONSTITUTION["options_money"]
        self.assertEqual((om["probe"]["loss_budget_usd"], om["probe"]["loss_total_usd"], om["daily_stop_share"],
                          om["drawdown_stop_share"]), ("1900", "1900", "0.25", "0.60"))
        self.assertEqual(K.EQUITY_MONEY_BOUNDS["event.position_share.learning"], ("0", "0.05"))
        self.assertEqual(K.EQUITY_MONEY_BOUNDS["event.per_name_share"], ("0", "0.10"), "the name's wall is unchanged")
        self.assertEqual((K.OPTIONS_MONEY_BOUNDS["probe.loss_budget_usd"], K.OPTIONS_MONEY_BOUNDS["probe.loss_total_usd"]),
                         (("0", "1900"), ("0", "1900")))
        self.assertEqual((K.equity_money_problems(), K.options_money_problems()), ([], []))
        self.assertEqual(DN.LOSS_TOTAL_USD, 1900.0)

    def test_the_digests_moved_once_with_the_rows_and_nothing_else(self):
        self.assertEqual((K.money_digest()[:8], K.digest()[:8]), ("1687e4e3", "3feab26d"))
        self.assertEqual(K.digest(), K.PINNED_DIGEST)
        self.assertEqual((K.money_digest(), K.digest()), X.DIGESTS[X.in_force()])
        before = X.before_1019l()
        self.assertEqual((K.money_digest(before)[:8], K.digest(before)[:8]), ("d52a5af5", "9c8b2221"), "release 1019i's")
        self.assertEqual((execution_fingerprint()[:8], equity_fingerprint()[:8]), ("b60410ad", "78022ca6"),
                         "the options execution fingerprint and the equity identity do not move")

        def flat(c, prefix=""):
            out = {}
            for k, v in c.items():
                out.update(flat(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}": v})
            return out
        moved = {k for k, v in flat(K.CONSTITUTION).items() if flat(before).get(k, "absent") != v}
        self.assertEqual(moved, {"equity_money.event.position_share.learning", "equity_money.event.position_share.probe",
                                 "options_money.probe.loss_budget_usd", "options_money.probe.loss_total_usd",
                                 "options_money.daily_stop_share"})
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((K.money_digest(at), K.digest(at)), X.DIGESTS[candidate])
            self.assertEqual((K.money_digest(X.before_1019l(at)), K.digest(X.before_1019l(at))), X.DIGESTS_1019I[candidate])

    def test_the_book_and_the_options_table_read_them(self):
        s = EB.settings()
        self.assertEqual((s.share("learning"), s.share("probe"), s.share("sized")), (D("0.05"), D("0.05"), D("0.10")))
        t = M.Table.from_constitution()
        self.assertEqual((t.probe_loss_budget, t.probe_loss_total, t.daily_stop_share), (D("1900"), D("1900"), D("0.25")))


class TheDoneStop(unittest.TestCase):
    def test_the_stop_is_the_balance_not_800(self):
        self.assertFalse(DN._stop({"realized_total_usd": "800", "at_risk_usd": "0", "total_budget_usd": "1900"}, NOW)["spent"])
        spent = DN._stop({"realized_total_usd": "1800", "at_risk_usd": "100", "total_budget_usd": "1900"}, NOW)
        self.assertTrue(spent["spent"])
        self.assertIn("the $1900 loss budget is spent", spent["why"])
        self.assertTrue(DN._stop({"realized_total_usd": "1900", "at_risk_usd": "0", "total_budget_usd": "5000"}, NOW)["spent"],
                        "never above V3's total, whatever the table says")


@on_1019h
class TheLearningBuy(TB.EventTest):
    def test_a_learning_buy_takes_five_percent_of_e_in_whole_shares(self):
        """The same day as league/tests/test_events_book.py `TheDay` (E $2,000, limit $20.00), at V3's 5%: 5 shares
        ($100.00), where V2's 2% took 2."""
        h = self.harness()
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
        h.lane.intent(TB.V2("EVL-ERN-READ-O1"), "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.ready(h)
        h.symbol("ACME", last=17.0, sd=0.02)
        h.tick(9, 15)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["status"], buy["band"]), ("planned", "learning"))
        h.tick(9, 16)
        [body] = h.bodies()
        self.assertEqual((body["symbol"], body["qty"], body["limit_price"]), ("ACME", "5", "20.00"), "5% of $2,000 at $20")


# ------------------------------------------------------------------- release 1019m: V3's behaviour on the table in force
class TheBoundsInForce(unittest.TestCase):
    """The rows' bounds refuse a table past V3's walls (release 1019m, the independent review: the earlier releases'
    refusal checks run on release 1019i's bounds)."""

    def test_a_table_past_the_balance_or_the_bug_stop_is_refused(self):
        import copy

        for path, value in ((("probe", "loss_budget_usd"), "1900.01"), (("probe", "loss_total_usd"), "1900.01"),
                            (("daily_stop_share",), "0.2501"), (("daily_stop_share",), "0.35")):
            changed = copy.deepcopy(K.CONSTITUTION)
            node = changed["options_money"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            self.assertTrue(any(path[-1] in p for p in K.options_money_problems(changed)), (path, value))
        for path, value in ((("probe", "loss_budget_usd"), "1900"), (("daily_stop_share",), "0.25"),
                            (("daily_stop_share",), "0.15")):
            changed = copy.deepcopy(K.CONSTITUTION)
            node = changed["options_money"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            self.assertEqual(K.options_money_problems(changed), [], (path, value))
        changed = copy.deepcopy(K.CONSTITUTION)
        changed["equity_money"]["event"]["position_share"]["learning"] = "0.0501"
        self.assertTrue(K.equity_money_problems(changed), "learning past V3's 5% is refused")

    def test_the_options_probe_room_is_its_slots_under_the_balance(self):
        """STATED EFFECT (the review's minor, A139): at the $1,900 budget `money.probe_room` is 8 x 10% x E again
        (release L-D's $400 cap no longer binds below E $2,375): the room the options lane keeps for Probe families."""
        t = M.Table.from_constitution()
        self.assertEqual(M.probe_room(t, D("1906")), D("1524.80"))
        self.assertEqual(M.probe_room(t, D("3000")), D("1900"), "the budget caps it from E $2,375")


class TheBugStop(TB.EventTest):
    """GOAL V3's BUG STOP (wall 1: "a bug stop that pauses new entries after a 25% loss in one session until you have
    read why"), on the table in force: the options path's daily stop trips at 25% of the day's base and clears at the
    next session (league/live/money.py `Stops`); the equity book latches it (league/equity/bugstop.py) and holds every
    new real entry until the captain's release."""

    def stops(self, day: dt.date, equity: str, *, start: str = "2000", base: M.Stops | None = None) -> M.Stops:
        t = M.Table.from_constitution()
        s = base or M.Stops(start_equity=D(start))
        at = TB.at(day, 10, 0)
        s.observe(t, at=at, day=day.isoformat(), equity=D(equity), last_equity=D(start), flows=M.FlowBook(at + 1, ()))
        return s

    def buy_ready(self, h) -> None:
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
        h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", 3)], "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.ready(h)
        h.symbol("ACME", last=17.0, sd=0.02)

    def release(self, why: str) -> None:
        import contextlib
        import io

        from league.equity import bugstop as BUG

        with contextlib.redirect_stdout(io.StringIO()):
            BUG.main(["--root", str(self.root), "--release", why])

    def test_the_daily_stop_trips_at_25_percent_and_clears_at_the_next_session(self):
        prior = self.stops(TB.PRIOR, "2000")
        tripped = self.stops(TB.PRIOR, "1490", base=prior)           # -$510 of a $2,000 base: 25.5%
        self.assertIn("the daily stop", tripped.blocked() or "")
        self.assertIn("25%", tripped.daily_why)
        untouched = self.stops(TB.PRIOR, "1510", base=self.stops(TB.PRIOR, "2000"))     # -24.5%: no trip
        self.assertIsNone(untouched.blocked())
        nxt = self.stops(TB.DAY, "1490", base=tripped)
        self.assertEqual((nxt.daily_tripped, nxt.blocked()), (False, None), "the stop alone clears next session")

    def test_the_latch_holds_every_new_entry_until_the_captains_release(self):
        from league.equity import bugstop as BUG

        h = self.harness()
        self.buy_ready(h)
        tripped = self.stops(TB.PRIOR, "1490", base=self.stops(TB.PRIOR, "2000"))
        h.state.put(BUG.STOPS, tripped.as_state())
        h.tick(9, 10, day=TB.PRIOR)
        latch = h.state.get(BUG.LATCH)
        self.assertEqual((latch["day"], latch["released"]), (TB.PRIOR.isoformat(), None))
        self.assertIn("THE BUG STOP (goal V3)", h.book.frozen)
        self.assertTrue(any(level == "error" and "THE BUG STOP" in text for level, text in h.alerts))
        # THE NEXT SESSION: the options path's stop has cleared; the latch has not
        h.state.put(BUG.STOPS, self.stops(TB.DAY, "1490", base=tripped).as_state())
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(h.bodies(), [], "no new real entry while the latch stands")
        [buy] = h.event_intents("buy")
        self.assertIn("THE BUG STOP (goal V3)", buy["why"])
        self.assertIn("equity reconciliation: THE BUG STOP", L.EquityBook._open_block(h.book, lambda opening=True: None,
                                                                                      h.book._instance(buy["instance"])))
        with self.assertRaises(SystemExit):
            self.release("  ")                                          # what was read is required
        self.release("read: an invented feed bug, fixed in release 1019z")
        h.tick(9, 17)
        released = h.state.get(BUG.LATCH)["released"]
        self.assertIn("an invented feed bug", released["why"])
        self.assertEqual(h.book.frozen, "")
        self.assertIsNone(h.state.get(BUG.RELEASE))
        self.assertEqual([b["symbol"] for b in h.bodies()], ["ACME"], "after the release the buy goes")
        self.assertTrue(any(kind == "equity.freeze" and payload.get("cleared") == BUG.LATCH for kind, payload in h.events))
        self.assertTrue(any(kind == "equity.freeze" and payload.get("bug_stop") == TB.PRIOR.isoformat()
                            and payload.get("frozen") for kind, payload in h.events), "the latch is in the ledger")

    def test_a_released_session_never_latches_again_and_a_later_trip_does(self):
        from league.equity import bugstop as BUG

        h = self.harness()
        tripped = self.stops(TB.PRIOR, "1490", base=self.stops(TB.PRIOR, "2000"))
        h.state.put(BUG.STOPS, tripped.as_state())
        h.tick(9, 10, day=TB.PRIOR)
        self.release("read why")
        h.tick(9, 11, day=TB.PRIOR)
        h.tick(9, 12, day=TB.PRIOR)                                     # the same session's stop still tripped
        self.assertEqual(h.book.frozen, "", "the same session's trip is not latched twice")
        again = self.stops(TB.DAY, "1000", base=self.stops(TB.DAY, "1490", base=tripped))
        h.state.put(BUG.STOPS, again.as_state())
        h.tick(9, 10)
        self.assertEqual((h.state.get(BUG.LATCH)["day"], h.state.get(BUG.LATCH)["released"]), (TB.DAY.isoformat(), None))
        self.assertIn("THE BUG STOP", h.book.frozen)

    def test_with_no_standing_latch_there_is_nothing_to_release(self):
        from league.equity import bugstop as BUG

        h = self.harness()
        with self.assertRaises(SystemExit):
            self.release("read why")
        self.assertIsNone(h.state.get(BUG.RELEASE))


class TheLossWindow(TB.EventTest):
    """The shared loss budget at the balance ($1,900 a window and in total, options_money.probe): an event buy is sized
    against it with every event lot's close of the window (league/equity/live.py `size_entry`'s budget cap)."""

    def world(self, loss: str):
        return self.world_on(self.harness(), loss)

    def world_on(self, h, loss: str):
        inst = L.Instance(TB.key("EVL-ERN-READ-O1"), "EVL-ERN-READ-O1", 3, L.EVENT_LANE, "", "", {}, "learning", False,
                          1, created_at=h.clock(), kind=L.EVENT_KIND)
        h.book._save_instance(inst)
        lot = L.Lot(h.book._next("eq_lots", "lid"), inst.id, inst.family, inst.version, L.EVENT_LANE, "OLDX", "stock",
                    D(0), D(2), D("40"), D("80"), "open", opened_at=TB.at(TB.PRIOR, 9, 30),
                    opened_day=TB.PRIOR.isoformat(), cash=D(loss), probe=False, status="closed", exit_px=D("1"),
                    exit_at="close", exit_day=TB.PRIOR.isoformat(), closed_at=TB.at(TB.PRIOR, 16, 0))
        h.book._save_lot(lot)
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME")
        h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", 3)], "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        h.lane.decided(TB.DAY, "open")
        h.lane.decided(TB.DAY, "close")
        h.symbol("ACME", last=17.0, sd=0.02)
        h.tick(9, 15)
        h.tick(9, 16)
        return h

    def test_a_realized_loss_past_v2s_window_still_lets_a_buy_go(self):
        h = self.world("-1000")
        self.assertEqual({b["symbol"]: b["qty"] for b in h.bodies()}, {"ACME": "5"}, "$1,000 lost: V2's $400 window "
                                                                                    "would refuse it")

    def test_the_balance_window_cuts_a_buy_to_its_room_and_refuses_one_past_it(self):
        h = self.world("-1895")                          # $5 left: 2 shares ($40 at weight 0.10, $4 of open risk)
        [buy] = h.event_intents("buy")
        self.assertEqual(({b["symbol"]: b["qty"] for b in h.bodies()}, buy["binding"], D(buy["sized_usd"])),
                         ({"ACME": "2"}, "budget", D("40")))
        h2 = self.world_on(TheV6ProbeBuys.fresh(self), "-1905")
        [buy] = h2.event_intents("buy")
        self.assertEqual((h2.bodies(), buy["status"], buy["binding"]), ([], "refused", "budget"))
        self.assertIn("the shared loss budget has $-5.00 of room", buy["why"])


class TheV6ProbeBuys(TB.EventTest):
    """PREREG-EVL-6 section 6, clause 2 (frozen) on the table in force: a version's Probe buy is the fewest whole shares
    whose value at the limit reaches 0.8 of the band's target (5% of E), never above 5% of E. STATED EFFECT (the
    independent review, A139): a promoted lot is never larger than a learning one at 5%, and a limit with no whole count
    inside [4%, 5%] of E is skipped where learning buys."""

    def pick(self, h, *, band: str, prev_close: float) -> None:
        TB.earnings(h.lane, "a-1", TB.CIK, "ACME", prev_close=prev_close)
        h.lane.band("EVL-ERN-READ-O1", band, version=3)
        h.lane.intent(P.BY_KEY[("EVL-ERN-READ-O1", 3)], "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
        self.ready(h)
        h.symbol("ACME", last=prev_close, sd=0.02)

    def summary(self, h) -> dict:
        row = h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at='open'", (TB.DAY.isoformat(),))
        return json.loads(row[0]["summary"])["programs"]["EVL-ERN-READ-O1"]

    def test_a_probe_buy_takes_the_fewest_shares_reaching_four_percent(self):
        """E $1,898, a $5.00 limit: the target $94.90, the bar $75.92: 16 shares ($80.00); learning takes 18 ($90.00)."""
        h = self.harness(cash="1898", E="1898")
        self.pick(h, band="probe", prev_close=4.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual({b["symbol"]: b["qty"] for b in h.bodies()}, {"ACME": "16"})
        [row] = h.event_intents("buy")
        self.assertEqual((D(row["target_usd"]), D(row["sized_usd"])), (D("94.900"), D("80")))

    def test_a_learning_buy_of_the_same_pick_is_larger(self):
        h = self.harness(cash="1898", E="1898")
        self.pick(h, band="learning", prev_close=4.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual({b["symbol"]: b["qty"] for b in h.bodies()}, {"ACME": "18"}, "floor($94.90 / $5.00)")

    def test_a_limit_with_no_count_inside_the_window_is_skipped_at_probe(self):
        """E $2,000, a $60.00 limit: one share ($60) is under the $80 bar, two ($120) above the $100 envelope."""
        h = self.harness()
        self.pick(h, band="probe", prev_close=48.0)
        h.tick(9, 15)
        mine = self.summary(h)
        self.assertEqual((mine["picks"], mine.get("planned"), mine.get("skipped")), (1, 0, {"under_bar": 1}))
        self.assertEqual(h.event_intents("buy"), [])
        h2 = TheV6ProbeBuys.fresh(self)
        self.pick(h2, band="learning", prev_close=48.0)
        h2.tick(9, 15)
        h2.tick(9, 16)
        self.assertEqual({b["symbol"]: b["qty"] for b in h2.bodies()}, {"ACME": "1"}, "learning buys one share")

    def fresh(self):
        case = TB.EventTest("run")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case.harness()


from league.tests import test_standing_grant as SG  # noqa: E402
from league.tests.v2_walls import v2_walls  # noqa: E402


class TheV3Pair(SG.StandingCase):
    """The standing grant on the pair in force: a grant pinned on release 1019i's money digest holds every real entry
    after release 1019l's deploy until the owner's deploy re-ratifies it on 1687e4e3 (the updater alone never does)."""

    def pinned_on_1019i(self):
        with v2_walls():
            self.assertEqual(K.money_digest()[:8], "d52a5af5")
            grant = self.enabled()
        self.assertEqual(K.money_digest()[:8], "1687e4e3")
        return grant

    def test_the_owners_deploy_re_ratifies_v3s_rows(self):
        grant = self.pinned_on_1019i()
        self.assertFalse(grant.allows_live(2), "real entries are held until it is ratified")
        out = self.standing(grant, release="r-1019l", rows=SG.owner_deploy(self.clock() - 60, release="r-1019l"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertEqual(grant.current()["policy"]["constitution_digest"], K.money_digest())
        self.assertTrue(grant.allows_live(2))

    def test_the_updater_alone_never_ratifies_them(self):
        grant = self.pinned_on_1019i()
        out = self.standing(grant, release="main-abcdef123456", rows=SG.updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))


from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
