"""THE EQUITY BOOK'S DAILY STEP after the E1 review (`league/equity/live.py`: the band sync and the seating, the decide and
its catch-up, the failed-decide count, the House's exit rules, the 16:20 bars and their morning audit, the buy-and-hold
beside the sizing-up rule), with its readers (`league/equity/families.py`, `league/swarm/bands.py`'s equity read) and
the decider child's answer (`league/equity/child.py`).

What each class holds, by the review's finding:
- `TheStrictRead`, `OneUnreadableRead`, `RetiredOnEvidence`: one unreadable read of the swarm store never retires a live
  program (the strict read, the store's own word on a family with no row, a retirement that can be taken back);
- `TheSundayDeploy`, `Seating`: a program that passes its look after the day's decision is seated and decided for the
  same close, so its first order goes in the next session (amendment A10.4);
- `OnceASession`: a decide that runs again never records a program's intents, or counts its failure, twice;
- `FailedDecides`, `TheChildsAnswer`: a program's own failed decide counts toward A8.5's exit, as in the Gym;
- `HouseExits`: a House rule due at the next open goes at the open whatever the program planned for the close;
- `LotBars`: the bars of a lot's symbol are read whether or not a live program still needs it;
- `Audit`, `AsOf`: the morning audit judges prices, notes a volume, and marks each symbol on its own verdict;
- `BuyAndHold`: the sizing-up rule's buy-and-hold is priced on one adjustment basis.

The book's tests' harness and fakes are league/tests/test_equity_book.py's; the swarm side is the end-to-end test's
(league/tests/test_equity_e2e.py: a synthetic market, every package's real code). No price here is a market's."""

from __future__ import annotations

import datetime as dt
import sqlite3
import unittest
from decimal import Decimal as D
from unittest import mock

from league.equity import LANES
from league.equity import bands as B
from league.equity import child as CH
from league.equity import live as L
from league.equity.families import GONE, EquityFamilies, MemoryEquityFamilies
from league.live.decider import InlineDecider
from league.swarm import bands
from league.tests import test_equity_book as T
from league.tests import test_equity_e2e as E2E

SUNDAY = dt.date(2026, 10, 11)
FRIDAY, MONDAY, TUESDAY, WEDNESDAY = T.FRIDAY, T.MONDAY, T.TUESDAY, T.WEDNESDAY
#: Money's own band rule (`T.BookTest` stubs it at its interface for the book's plumbing tests).
REAL_NEXT_BAND = B.next_band
SPY, QQQ = "seed-overnight-spy", "seed-overnight-qqq"
#: Programs for the real child (the decider's "equity" kind, in process).
BOOM = ("NEEDS = {'symbols': ['SPY'], 'history': 5, 'max_hold_sessions': 40}\nPARAMS = {}\n\n\n"
        "def decide(ctx):\n    raise ValueError('boom')\n")
QUIET = ("NEEDS = {'symbols': ['SPY'], 'history': 5, 'max_hold_sessions': 40}\nPARAMS = {}\n\n\n"
         "def decide(ctx):\n    return []\n")


def seat(row, record, table, *, seat_free, sticky=None):
    """The swarm's band rule at its interface, enough of it for the seating: a Candidate with a free seat goes to Probe."""
    if row["band"] == "candidate" and seat_free and not sticky:
        return "probe", "passed its lane's sealed look and holds an equity roster seat"
    return row["band"], "unchanged"


def key_of(family: str, version: int = 1) -> str:
    return L.instance_key(family, version)


def errors(h: T.Harness) -> list[str]:
    return [text for level, text in h.alerts if level == "error"]


def warnings(h: T.Harness) -> list[str]:
    return [text for level, text in h.alerts if level == "warning"]


# ------------------------------------------------------------------------------------- the strict read (the store's)
class SwarmCase(E2E.TheEquityLaneEndToEnd):
    """The end-to-end test's swarm (a real store, the three seeds, the pinned screen) with its own test left out."""

    test_a_seeded_program_from_birth_to_the_done_meter = None

    def book(self):
        """The House's book over the real reader, a venue with E in cash, both stages of the stock proof passed."""
        market = T.Market(self.clock)
        official = self.market_from_the_store(market)
        venue = T.Venue(market, self.clock, cash=str(E2E.E))
        state = E2E.LiveState(self.root / "live.sqlite", clock=self.clock)
        self.addCleanup(state.close)
        for key, witnesses in ((E2E.STOCK_BUY_KEY, E2E.STOCK_BUY_WITNESSES), (E2E.STOCK_SELL_KEY, E2E.STOCK_WITNESSES)):
            state.put(key, {"schema": 1, "status": "passed", **{k: True for k in witnesses}})
        self.alerts: list[tuple[str, str]] = []
        book = L.EquityBook(state, venue, market, E2E.M.Table.from_constitution(), EquityFamilies(self.root),
                            decider=InlineDecider(), stock_proof=E2E.StockPaperProof(state, None, clock=self.clock),
                            sizing_equity=lambda: E2E.E, root=self.root, clock=self.clock,
                            alert=lambda level, text: self.alerts.append((level, text)))

        def tick(day, hh, mm, ss=3):
            self.clock.set(T.at(day, hh, mm, ss))
            return book.tick(self.clock(), account_row=venue.account(), positions=None, open_orders=None,
                             real_block=lambda opening=True: None, killed=lambda: False)

        return book, state, venue, market, official, tick

    def unreadable_once(self):
        """`sqlite3.connect` failing for the swarm store (a store that cannot be read within its second)."""
        real = sqlite3.connect

        def connect(*args, **kw):
            if "swarm" in str(args[0]):
                raise sqlite3.OperationalError("database is locked")
            return real(*args, **kw)

        return mock.patch.object(bands.sqlite3, "connect", connect)


@unittest.skipUnless(E2E.HAVE, "numpy not installed")
class TheStrictRead(SwarmCase):
    def test_a_strict_read_raises_where_the_plain_read_answers_nothing(self):
        self.born_validated_and_looked()
        self.assertEqual([r["family"] for r in bands.read(self.root, lanes=LANES, strict=True)], [SPY])
        with self.unreadable_once():
            self.assertEqual(bands.read(self.root, lanes=LANES), [], "the plain read fails closed, silently")
            with self.assertRaises(bands.EquityUnreadable) as raised:
                bands.read(self.root, lanes=LANES, strict=True)
            self.assertIn("database is locked", str(raised.exception))
            with self.assertRaises(bands.EquityUnreadable):
                bands.read(self.root, lanes="all", strict=True)
        with mock.patch.object(bands, "_equity_sha", return_value=None):
            self.assertEqual(bands.read(self.root, lanes=LANES), [])
            with self.assertRaises(bands.EquityUnreadable):
                bands.read(self.root, lanes=LANES, strict=True)
        empty = self.root / "nowhere"
        self.assertEqual(bands.read(empty, lanes=LANES), [])
        with self.assertRaises(bands.EquityUnreadable):
            bands.read(empty, lanes=LANES, strict=True)
        # A store that was read and holds no equity row is no error, and the options read is never strict.
        self.store.retire(SPY, "the test retires it")
        self.assertEqual(bands.read(self.root, lanes=LANES, strict=True), [])
        self.assertEqual(bands.read(empty, strict=True), [])

    def test_the_books_reader_says_why_it_could_not_read(self):
        self.born_validated_and_looked()
        families = EquityFamilies(self.root)
        with self.unreadable_once():
            self.assertEqual(families.read(), [])
        self.assertIn("database is locked", families.last_error)
        with mock.patch.object(bands, "_equity_sha", return_value=None):
            self.assertEqual(families.read(), [])
        self.assertIn("equity identity", families.last_error)
        self.assertEqual([r["family"] for r in families.read()], [SPY])
        self.assertEqual(families.last_error, "")

    def test_a_band_is_not_written_on_a_row_that_cannot_be_read_again(self):
        self.born_validated_and_looked()
        families = EquityFamilies(self.root)
        [row] = families.read()
        with self.unreadable_once():
            self.assertFalse(families.confirm_band(row, "probe", "a seat is free"))
        self.assertEqual(self.store.family(SPY)["band"], "candidate")
        self.assertTrue(families.confirm_band(row, "probe", "a seat is free"))
        self.assertEqual(self.store.family(SPY)["band"], "probe")

    def test_standing_is_the_stores_own_word(self):
        self.born_validated_and_looked()
        families = EquityFamilies(self.root)
        self.assertEqual(families.standing(SPY, 1)[0], "demoted", "a Candidate: its band does not run")
        self.store.set_band(SPY, "probe", reason="the EquityBook")
        self.assertEqual(families.standing(SPY, 1)[0], "live")
        self.assertEqual(families.standing(SPY, 2), ("retired", "superseded by version 1"))
        self.assertEqual(families.standing("no-such-family", 1)[0], "unknown")
        with mock.patch.object(bands, "_equity_sha", return_value=None):
            self.assertEqual(families.standing(SPY, 1)[0], "unknown", "no identity to judge its proof against")
        with mock.patch.object(bands, "_equity_sha", return_value="0" * 64):
            self.assertEqual(families.standing(SPY, 1),
                             ("retired", "its band's proof is not the current equity identity"))
        with mock.patch.object(families, "_db", side_effect=sqlite3.OperationalError("database is locked")):
            code, why = families.standing(SPY, 1)
            self.assertEqual(code, "unknown")
            self.assertIn("database is locked", why)
        self.store.set_band(SPY, "gym", reason="the swarm took it back")
        self.assertEqual(families.standing(SPY, 1), ("demoted", "its band is gym"))
        self.store.retire(SPY, "the test retires it")
        self.assertEqual(families.standing(SPY, 1), ("retired", "its family is retired"))
        self.assertEqual(GONE, ("retired", "demoted"))


@unittest.skipUnless(E2E.HAVE, "numpy not installed")
class OneUnreadableRead(SwarmCase):
    """The review's scenario on the real classes: the seed at Probe holds a lot, and the one sync of the decision day
    meets a swarm store it cannot read (or a family whose row it cannot read)."""

    def at_probe_with_a_lot(self):
        self.born_validated_and_looked()
        book, state, venue, market, official, tick = self.book()
        tick(SUNDAY, 13, 0)
        self.quote(market, official[MONDAY][1])
        tick(MONDAY, 15, 55)
        self.assertEqual([lot.status for lot in book._lots()], ["open"])
        return book, state, tick

    def test_a_store_that_cannot_be_read_once_retires_nobody(self):
        book, state, tick = self.at_probe_with_a_lot()
        inst = key_of(SPY)
        with self.unreadable_once():
            out = tick(MONDAY, 16, 21)
        self.assertIn("unreadable", out["families"])
        self.assertIn("database is locked", out["families"])
        self.assertIsNone(book._instance(inst).retired_at)
        self.assertNotEqual(state.get("eq_synced"), MONDAY.isoformat(), "the sync is owed: it runs again next minute")
        self.assertEqual(state.rows("SELECT iid FROM eq_intents WHERE kind='house_exit'"), [])
        tick(MONDAY, 16, 22)
        self.assertEqual(state.get("eq_synced"), MONDAY.isoformat())
        out = tick(MONDAY, 16, 31)
        self.assertEqual(len(out["decided"]), 1, out)
        kinds = sorted(r["kind"] for r in state.rows("SELECT kind FROM eq_intents WHERE decided_day=?",
                                                     (MONDAY.isoformat(),)))
        self.assertEqual(kinds, ["buy", "sell"], "the program goes on: its own sell at the open, its next buy")
        self.assertEqual(self.store.family(SPY)["band"], "probe")
        self.assertEqual(self.alerts, [])

    def test_a_family_whose_row_cannot_be_read_keeps_running_and_the_owner_is_told_once(self):
        book, state, tick = self.at_probe_with_a_lot()
        inst = key_of(SPY)
        path = self.root / self.store.version(SPY, 1)["path"]
        code = path.read_text()
        path.unlink()                                             # its code file cannot be read: the read leaves it out
        for minute in (21, 22, 23):
            out = tick(MONDAY, 16, minute)
            self.assertIn("nothing retired", out["families"])
        self.assertIsNone(book._instance(inst).retired_at)
        self.assertNotEqual(state.get("eq_synced"), MONDAY.isoformat())
        told = [text for level, text in self.alerts if level == "warning"]
        self.assertEqual(len(told), 1, told)
        self.assertIn(inst, told[0])
        out = tick(MONDAY, 16, 31)                                  # it decides on the program the book holds
        self.assertEqual(len(out["decided"]), 1, out)
        self.assertEqual(state.rows("SELECT iid FROM eq_intents WHERE kind='house_exit'"), [])
        path.write_text(code)
        tick(TUESDAY, 16, 21)
        self.assertEqual(state.get("eq_synced"), TUESDAY.isoformat())
        self.assertIsNone(book._instance(inst).retired_at)

    def test_a_family_the_swarm_retired_is_retired_with_an_alert(self):
        book, state, tick = self.at_probe_with_a_lot()
        inst = key_of(SPY)
        self.store.retire(SPY, "the swarm retires it")
        tick(MONDAY, 16, 21)
        tick(MONDAY, 16, 31)
        retired = book._instance(inst)
        self.assertIsNotNone(retired.retired_at)
        self.assertEqual(retired.why, "retired: its family is retired")
        [(tag, at, day)] = [(r["tag"], r["at"], r["exec_day"]) for r in state.rows(
            "SELECT * FROM eq_intents WHERE kind='house_exit'")]
        self.assertEqual((tag, at, day), ("retired", "open", TUESDAY.isoformat()))
        self.assertTrue(any(inst in text and "lots exit at the next open" in text
                            for level, text in self.alerts if level == "warning"), self.alerts)


# ------------------------------------------------------------------------------------- the Sunday deploy (A10.4)
@unittest.skipUnless(E2E.HAVE, "numpy not installed")
class TheSundayDeploy(SwarmCase):
    def test_a_seed_that_passes_its_look_after_the_deploy_buys_at_mondays_close(self):
        """A10.2's own order: the House is deployed first (no equity family yet: the lane's mode is off), and the seeds
        are born, validated and looked at later on Sunday. The first real close-window buy goes Monday 15:55 ET."""
        book, state, venue, market, official, tick = self.book()
        tick(SUNDAY, 12, 0)                                         # the first minute after the deploy
        first = state.get("eq_decide")
        self.assertEqual((first["day"], first["status"], first["why"], first["instances"]),
                         (FRIDAY.isoformat(), "done", "no live program", []))
        self.clock.set(T.at(SUNDAY, 19, 0))
        self.born_validated_and_looked()                            # the captain sets elane.mode "gate": the look passes
        self.assertEqual(self.store.family(SPY)["band"], "candidate")
        out = tick(SUNDAY, 20, 0)
        self.assertFalse(out.get("errors"), out)
        inst = key_of(SPY)
        self.assertEqual(self.store.family(SPY)["band"], "probe", out)
        self.assertEqual(book._instance(inst).band, "probe")
        [buy] = state.rows("SELECT * FROM eq_intents WHERE instance=?", (inst,))
        self.assertEqual((buy["kind"], buy["at"], buy["decided_day"], buy["exec_day"], buy["status"]),
                         ("buy", "close", FRIDAY.isoformat(), MONDAY.isoformat(), "planned"))
        record = state.get("eq_decide")
        self.assertEqual((record["day"], record["instances"]), (FRIDAY.isoformat(), [inst]))
        self.assertNotIn("why", record)
        tick(SUNDAY, 20, 1)
        self.assertEqual(len(state.rows("SELECT iid FROM eq_intents")), 1, "asked once for the close")
        tick(MONDAY, 8, 31)                                         # the morning audit of the bars it decided on
        self.assertEqual(state.get("eq_decision")["audit"], "ok")
        self.quote(market, official[MONDAY][0])
        tick(MONDAY, 9, 31)
        self.assertEqual(venue.sent, [])
        self.quote(market, official[MONDAY][1])
        tick(MONDAY, 15, 55)
        [sent] = venue.sent
        self.assertEqual((sent["symbol"], sent["side"]), ("SPY", "buy"))
        [lot] = book._lots()
        self.assertEqual((lot.entry_at, lot.opened_day), ("close", MONDAY.isoformat()))
        self.assertEqual([a for a in self.alerts if a[0] == "error"], [])


    def test_every_minute_from_the_deploy_to_tuesdays_open_the_pass_is_quiet(self):
        """The seating pass runs every minute between two decisions: it asks a program once a close, reads the vendor
        only for a decision's bars and their morning audit, and alerts nobody."""
        book, state, venue, market, official, tick = self.book()
        asked, errors = [], []
        real = book.decider.kind

        def kind(name, op, payload, **kw):
            if op == "decide":
                asked.append([job["key"] for job in payload["jobs"]])
            return real(name, op, payload, **kw)

        book.decider.kind = kind
        minutes = [(SUNDAY, hh, mm) for hh in range(12, 24) for mm in range(60)]
        minutes += [(MONDAY, hh, mm) for hh in range(24) for mm in range(60)]
        minutes += [(TUESDAY, hh, mm) for hh in range(10) for mm in range(60)]
        for day, hh, mm in minutes:
            if (day, hh, mm) == (SUNDAY, 19, 0):
                self.clock.set(T.at(day, hh, mm))
                self.born_validated_and_looked()
            if day != SUNDAY and (hh, mm) in ((9, 30), (15, 54)):
                self.quote(market, official[day][0 if hh == 9 else 1])
            out = tick(day, hh, mm)
            if out.get("errors"):
                errors.append((day, hh, mm, out["errors"]))
        inst = key_of(SPY)
        self.assertEqual(errors, [])
        self.assertEqual(asked, [[inst], [inst]], "Friday's close on Sunday evening, Monday's close at 16:30")
        # Two decisions' bars and their two morning audits: raw and adjusted, once each.
        self.assertEqual(len(market.bar_calls), 8, market.bar_calls)
        self.assertEqual([(b["side"], b["symbol"]) for b in venue.sent], [("buy", "SPY"), ("sell", "SPY")])
        self.assertEqual([(lot.opened_day, lot.exit_day, lot.reason) for lot in book._lots(open_only=False)],
                         [(MONDAY.isoformat(), TUESDAY.isoformat(), "program")])
        self.assertEqual(self.alerts, [])
        self.assertEqual(state.get("eq_decide")["instances"], [inst])


class Seating(T.BookTest):
    """The seating pass at its interfaces (the swarm's band rule stubbed: `seat`)."""

    def deployed(self) -> T.Harness:
        """A House whose first minute on the release is Sunday 14:00: no equity family, no decision handled yet."""
        h = self.harness()
        h.state.execute("DELETE FROM kv WHERE key='eq_decide'")
        for symbol in ("SPY", "QQQ"):
            h.market.make_bars(symbol, WEDNESDAY, n=20, price=float(sum(h.market.quote(symbol)) / 2))
        patcher = mock.patch.object(B, "next_band", seat)
        patcher.start()
        self.addCleanup(patcher.stop)
        h.tick(14, 0, day=SUNDAY)
        self.assertEqual(h.state.get("eq_decide"), {"day": "2026-10-09", "status": "done", "at": T.at(SUNDAY, 14, 0),
                                                     "instances": [], "why": "no live program"})
        return h

    def passes(self, h: T.Harness, family: str, symbol: str = "SPY", **plan) -> str:
        """The family passes its look: its row is a Candidate holding a seat. Returns its instance key."""
        h.families.rows[family] = T.family_row(family, band="candidate", symbols=(symbol,))
        key = key_of(family)
        h.decider.needs[key] = {"symbols": [symbol], "history": 5, "max_hold_sessions": 2}
        h.decider.plans[key] = [{"buy": symbol, "share": 0.5, "at": "close", **plan}]
        return key

    def test_a_program_seated_after_the_decision_is_decided_for_the_same_close(self):
        h = self.deployed()
        key = self.passes(h, SPY)
        out = h.tick(20, 0, day=SUNDAY)
        self.assertEqual(out["decided"], [f"{key}: 1"])
        self.assertEqual(h.families.rows[SPY]["band"], "probe")
        inst = h.book._instance(key)
        self.assertEqual((inst.band, inst.last_decided_day, inst.failed_decides), ("probe", "2026-10-09", 0))
        self.assertEqual(h.state.get("eq_band_since")[key], {"band": "probe", "day": "2026-10-09"})
        self.assertEqual([(i.kind, i.at, i.decided_day, i.exec_day, i.status) for i in h.intents()],
                         [("buy", "close", "2026-10-09", "2026-10-12", "planned")])
        record = h.state.get("eq_decide")
        self.assertEqual((record["day"], record["status"], record["instances"]), ("2026-10-09", "done", [key]))
        self.assertNotIn("why", record)
        h.tick(20, 1, day=SUNDAY)
        self.assertEqual(len(h.decider.jobs), 1, "once a close")
        h.tick(15, 55, day=MONDAY)
        self.assertEqual([(b["symbol"], b["side"]) for b in h.venue.sent], [("SPY", "buy")])

    def test_a_second_program_the_same_evening_and_the_first_is_not_asked_again(self):
        h = self.deployed()
        first = self.passes(h, SPY)
        h.tick(18, 0, day=SUNDAY)
        second = self.passes(h, QQQ, "QQQ")
        out = h.tick(22, 0, day=SUNDAY)
        self.assertEqual(out["decided"], [f"{second}: 1"])
        self.assertEqual([[j["key"] for j in call["jobs"]] for call in h.decider.jobs], [[first], [second]])
        self.assertEqual(sorted((i.instance, i.symbol, i.exec_day) for i in h.intents()),
                         [(second, "QQQ", "2026-10-12"), (first, "SPY", "2026-10-12")])
        self.assertEqual(h.state.get("eq_decide")["instances"], sorted([first, second]))
        # One fetch holds the day's bars for both, and the morning audit reads every symbol decided on.
        self.assertEqual(h.state.get("eq_decision")["symbols"], ["QQQ", "SPY"])
        h.tick(8, 31, day=MONDAY)
        self.assertEqual(h.state.get("eq_decision")["audit"], "ok")
        self.assertEqual(errors(h), [])

    def test_the_seating_pass_moves_nothing_else(self):
        """No demotion, no retirement and no update between two decisions: those are the decision's own."""
        h = self.deployed()
        key = self.passes(h, SPY)
        h.tick(20, 0, day=SUNDAY)
        h.lot(h.book._instance(key), "SPY", "0.4", "590")
        h.families.rows[SPY].update(band="retired")                 # the swarm retires it on Sunday night
        h.tick(21, 0, day=SUNDAY)
        h.tick(9, 0, day=MONDAY)
        self.assertIsNone(h.book._instance(key).retired_at, "not before Monday's decision")
        self.assertEqual(h.intents(kind="house_exit"), [])
        h.tick(16, 31, day=MONDAY)
        self.assertTrue(h.book._instance(key).why.startswith("retired"))
        self.assertEqual([e.tag for e in h.intents(kind="house_exit")], ["retired"])

    def test_a_record_that_names_no_instances_is_closed(self):
        """An idle or failed day, and a record written by hand (the workaround before this pass existed)."""
        h = self.harness()
        patcher = mock.patch.object(B, "next_band", seat)
        patcher.start()
        self.addCleanup(patcher.stop)
        h.decide_setup(FRIDAY)
        for record in ({"day": "2026-10-09", "status": "done"}, {"day": "2026-10-09", "status": "idle", "instances": []},
                       {"day": "2026-10-09", "status": "failed", "instances": []}):
            h.state.put("eq_decide", record)
            self.passes(h, SPY)
            h.tick(20, 0, day=SUNDAY)
            self.assertEqual((h.book._instances(), h.decider.jobs, h.families.rows[SPY]["band"]), ([], [], "candidate"))

    def test_no_seating_once_the_next_sessions_close_window_is_a_minute_away(self):
        h = self.deployed()
        self.passes(h, SPY)
        h.tick(15, 54, day=MONDAY)                                  # 15:54:03: the close window's sends start at 15:55
        self.assertEqual((h.book._instances(), h.decider.jobs), ([], []))
        h.tick(15, 55, day=MONDAY)
        self.assertEqual(h.venue.sent, [])
        h.tick(16, 31, day=MONDAY)                                  # Monday's own decision seats it
        self.assertEqual(h.book._instance(key_of(SPY)).last_decided_day, "2026-10-12")

    def test_seated_a_minute_before_the_cut_off_still_buys_at_that_close(self):
        h = self.deployed()
        self.passes(h, SPY)
        h.tick(15, 53, day=MONDAY)
        self.assertEqual([i.exec_day for i in h.intents(status="planned")], ["2026-10-12"])
        h.tick(15, 55, day=MONDAY)
        self.assertEqual([(b["symbol"], b["side"]) for b in h.venue.sent], [("SPY", "buy")])

    def test_a_lane_that_is_off_seats_nobody(self):
        h = self.deployed()
        h.table = T.dataclasses.replace(h.table, equity=T.equity_table(enabled=False))
        h.book = h.new_book()
        self.passes(h, SPY)
        h.tick(20, 0, day=SUNDAY)
        self.assertEqual((h.book._instances(), h.decider.jobs), ([], []))

    def test_an_unreadable_store_seats_nobody_and_says_so(self):
        h = self.deployed()
        self.passes(h, SPY)
        h.families.last_error = "EquityUnreadable: OperationalError: database is locked"
        out = h.tick(20, 0, day=SUNDAY)
        self.assertIn("unreadable", out["families"])
        self.assertEqual(h.book._instances(), [])
        h.families.last_error = ""
        h.tick(20, 1, day=SUNDAY)
        self.assertEqual(len(h.intents(status="planned")), 1)

    def test_an_instance_the_house_could_not_ask_is_asked_again_and_its_failure_counted_once(self):
        h = self.deployed()
        key = self.passes(h, SPY)
        h.decider.fail = True
        h.tick(20, 0, day=SUNDAY)
        self.assertEqual((h.book._instance(key).failed_decides, h.book._instance(key).last_decided_day), (1, None))
        self.assertEqual(h.state.get("eq_decide")["instances"], [])
        self.assertEqual(h.state.get("eq_failed"), {key: "2026-10-09"})
        self.assertEqual(len(warnings(h)), 1)
        h.tick(20, 5, day=SUNDAY)
        self.assertEqual(len(h.decider.jobs), 1, "not every minute")
        h.tick(20, 10, 4, day=SUNDAY)                                # `SEAT_RETRY_S` later: asked again, still failing
        self.assertEqual(len(h.decider.jobs), 2)
        self.assertEqual(h.book._instance(key).failed_decides, 1, "one failed decide a session")
        self.assertEqual(len(warnings(h)), 1, "and one alert")
        h.decider.fail = False
        h.tick(20, 21, day=SUNDAY)
        inst = h.book._instance(key)
        self.assertEqual((inst.failed_decides, inst.last_decided_day, inst.why), (0, "2026-10-09", ""))
        self.assertEqual(h.state.get("eq_decide")["instances"], [key])
        self.assertEqual(len(h.intents(status="planned")), 1)

    def test_the_retries_stop_at_the_next_sessions_pre_open(self):
        """After it the book an instance holds is no longer the close's (lots sold and bought since): a program that
        could not be asked overnight waits for the session's own decision; one seated now holds nothing and is asked."""
        h = self.deployed()
        key = self.passes(h, SPY)
        h.decider.fail = True
        h.tick(20, 0, day=SUNDAY)
        h.tick(9, 24, day=MONDAY)                                   # still before the 09:25 pre-open: asked again
        self.assertEqual(len(h.decider.jobs), 2)
        h.decider.fail = False
        h.tick(9, 40, day=MONDAY)
        self.assertEqual(len(h.decider.jobs), 2, "not asked again once the session has begun")
        self.assertEqual(h.book._instance(key).failed_decides, 1)
        other = self.passes(h, QQQ, "QQQ")
        h.tick(10, 0, day=MONDAY)
        self.assertEqual([j["key"] for j in h.decider.jobs[-1]["jobs"]], [other])
        self.assertEqual(h.state.get("eq_decide")["instances"], [other])

    def test_a_new_version_of_a_running_family_waits_for_the_decision(self):
        """The seating pass never runs two versions of one family in a session: the decision retires the old version
        and starts the new one."""
        h = self.deployed()
        key = self.passes(h, SPY)
        h.tick(20, 0, day=SUNDAY)
        h.families.rows[SPY].update(version=2, band="probe", run_sha="r2")
        h.decider.plans[key_of(SPY, 2)] = [{"buy": "SPY", "share": 0.5}]
        h.tick(21, 0, day=SUNDAY)
        self.assertEqual([i.id for i in h.book._instances()], [key])
        self.assertEqual(len(h.decider.jobs), 1)
        h.tick(16, 31, day=MONDAY)
        self.assertEqual({i.id: i.retired_at is None for i in h.book._instances()}, {key: False, key_of(SPY, 2): True})
        self.assertTrue(h.book._instance(key).why.startswith("retired: superseded by version 2"))

    def test_a_bar_read_again_for_a_later_decide_is_held_against_the_earlier_one(self):
        """The seating pass reads the day's bars again when a program seated since needs a symbol the day's fetch did
        not hold, and that read writes the day's rows again: a price that changed under a program that already decided
        costs it what the morning audit would have (its buys canceled, a failed decide); a volume does not."""
        h = self.deployed()
        first = self.passes(h, SPY)
        h.tick(18, 0, day=SUNDAY)
        h.market.bar_rows["raw"]["SPY"][-4]["v"] += 4321            # Friday's volume, then...
        second = self.passes(h, QQQ, "QQQ")
        h.tick(19, 0, day=SUNDAY)
        self.assertEqual(sorted(i.instance for i in h.intents(status="planned")), sorted([first, second]))
        self.assertEqual(errors(h), [])
        third = self.passes(h, "seed-third", "IWM")
        h.market.make_bars("IWM", WEDNESDAY, n=20, price=220.0)
        h.market.bar_rows["raw"]["SPY"][-4]["c"] += 1.0             # ...Friday's close
        h.tick(20, 0, day=SUNDAY)
        self.assertEqual({i.instance: i.status for i in h.intents(kind="buy")},
                         {first: "canceled", second: "planned", third: "planned"})
        self.assertEqual((h.book._instance(first).failed_decides, h.book._instance(second).failed_decides), (1, 0))
        self.assertEqual(len(errors(h)), 1)
        self.assertIn("read again for a later decide differ for SPY", errors(h)[0])


# ------------------------------------------------------------------------------------- retired on evidence only
class RetiredOnEvidence(T.BookTest):
    def running(self, h: T.Harness) -> L.Instance:
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        h.decide_setup(MONDAY)
        return inst

    def test_a_family_missing_from_a_good_read_keeps_its_instance(self):
        h = self.harness()
        inst = self.running(h)
        h.lot(inst, "SPY", "0.4", "590")
        h.families.hidden.add(SPY)                                  # the read left it out; the store shows it running
        out = h.tick(16, 21)
        self.assertIn("nothing retired", out["families"])
        self.assertIsNone(h.state.get("eq_synced"))
        h.tick(16, 22)
        self.assertEqual(len(warnings(h)), 1, "told once a decision day")
        h.tick(16, 31)
        self.assertIsNone(h.book._instance(inst.id).retired_at)
        self.assertEqual(h.intents(kind="house_exit"), [])
        self.assertEqual([j["key"] for j in h.decider.jobs[0]["jobs"]], [inst.id], "and it decides")
        h.families.hidden.clear()
        h.decide_setup(TUESDAY)
        h.tick(16, 21, day=TUESDAY)
        self.assertEqual(h.state.get("eq_synced"), "2026-10-13")

    def test_a_sync_the_decide_never_got_is_said_once(self):
        h = self.harness()
        inst = self.running(h)
        h.families.last_error = "EquityUnreadable: OperationalError: database is locked"
        for minute in (21, 25, 31, 32):
            h.tick(16, minute)
        self.assertIsNone(h.state.get("eq_synced"))
        self.assertEqual(h.book._instance(inst.id).last_decided_day, "2026-10-12", "it decides as the book holds it")
        [told] = warnings(h)
        self.assertIn("the band sync of 2026-10-12", told)
        self.assertIn("database is locked", told)

    def test_a_family_the_store_does_not_know_keeps_its_instance(self):
        """A swarm store that lost the family (a half-restored state) is no evidence that it stopped."""
        h = self.harness()
        inst = self.running(h)
        h.lot(inst, "SPY", "0.4", "590")
        h.families.rows.pop(SPY)
        h.tick(16, 31)
        self.assertIsNone(h.book._instance(inst.id).retired_at)
        self.assertEqual(h.intents(kind="house_exit"), [])
        self.assertIn("no such family", warnings(h)[0])

    def test_a_reader_that_cannot_say_retires_nobody(self):
        h = self.harness()
        inst = self.running(h)
        h.families.rows.pop(SPY)
        with mock.patch.object(MemoryEquityFamilies, "standing", side_effect=RuntimeError("the store broke")):
            h.tick(16, 31)
        self.assertIsNone(h.book._instance(inst.id).retired_at)
        self.assertIn("RuntimeError", warnings(h)[0])

    def test_the_stores_word_retires_or_demotes(self):
        for band, code in (("retired", "retired"), ("gym", "demoted"), ("candidate", "demoted")):
            with self.subTest(band=band):
                h = T.Harness(self.root / band)
                self.addCleanup(h.state.close)
                inst = self.running(h)
                lot = h.lot(inst, "SPY", "0.4", "590")
                h.families.rows[SPY]["band"] = band
                h.families.hidden.add(SPY)                          # no row either way: the store's word decides
                h.tick(16, 31)
                gone = h.book._instance(inst.id)
                self.assertIsNotNone(gone.retired_at)
                self.assertTrue(gone.why.startswith(code), gone.why)
                self.assertEqual([(e.lid, e.tag) for e in h.intents(kind="house_exit")], [(lot.lid, code)])
                self.assertEqual(h.decider.drops, [inst.id])
                self.assertTrue(any(inst.id in text for text in warnings(h)))

    def test_a_retired_instance_runs_again_when_its_row_is_back(self):
        h = self.harness()
        inst = self.running(h)
        h.families.rows[SPY]["band"] = "gym"                        # the swarm took the family back...
        h.tick(16, 31)
        self.assertTrue(h.book._instance(inst.id).why.startswith("demoted"))
        h.families.rows[SPY]["band"] = "probe"                      # ...and banded the same version again
        h.decide_setup(TUESDAY)
        h.tick(16, 31, day=TUESDAY)
        back = h.book._instance(inst.id)
        self.assertEqual((back.retired_at, back.band, back.why, back.last_decided_day), (None, "probe", "", "2026-10-13"))
        self.assertTrue(any("runs again" in text for text in warnings(h)))

    def test_a_sticky_demotion_and_another_program_never_run_again(self):
        h = self.harness()
        inst = self.running(h)
        with mock.patch.object(B, "next_band", lambda row, record, table, *, seat_free, sticky=None:
                               ("candidate", "EDM1: the summed returns crossed the band")):
            h.tick(16, 31)
        self.assertIn(inst.id, h.state.get("eq_sticky"))
        h.families.rows[SPY]["band"] = "probe"                      # by hand, against the rule
        h.decide_setup(TUESDAY)
        h.tick(16, 31, day=TUESDAY)
        self.assertIsNotNone(h.book._instance(inst.id).retired_at, "EDM1 is sticky for the version")
        # Another program under the same version number (a row that names another run sha) is not this instance.
        g = T.Harness(self.root / "other")
        self.addCleanup(g.state.close)
        other = self.running(g)
        g.families.rows[SPY]["band"] = "gym"
        g.tick(16, 31)
        g.families.rows[SPY].update(band="probe", run_sha="r2")
        g.decide_setup(TUESDAY)
        g.tick(16, 31, day=TUESDAY)
        self.assertIsNotNone(g.book._instance(other.id).retired_at)


# ------------------------------------------------------------------------------------- once a session
class OnceASession(T.BookTest):
    def two(self, h: T.Harness) -> tuple[L.Instance, L.Instance]:
        h.families.rows = {"fam-a": T.family_row("fam-a"), "fam-b": T.family_row("fam-b")}
        a, b = h.instance("fam-a"), h.instance("fam-b")
        h.decide_setup(MONDAY)
        for inst in (a, b):
            h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5, "at": "close"}]
        return a, b

    def test_a_decide_that_runs_again_records_no_intent_twice(self):
        """The step failed (or the House died) after the programs' intents were committed and before the day was
        recorded done: the next minute asks nobody again."""
        h = self.harness()
        a, b = self.two(h)
        with mock.patch.object(h.book, "_house_exits", side_effect=RuntimeError("the House's exits broke")):
            out = h.tick(16, 31)
        self.assertTrue(out.get("errors"))
        self.assertEqual(h.state.get("eq_decide")["day"], "2026-10-09", "not recorded done")
        self.assertEqual(len(h.intents(kind="buy")), 2)
        h.tick(16, 32)
        self.assertEqual(len(h.decider.jobs), 1, "nobody asked twice")
        self.assertEqual(sorted((i.instance, i.status) for i in h.intents(kind="buy")),
                         [(a.id, "planned"), (b.id, "planned")])
        self.assertEqual(h.state.get("eq_decide")["instances"], sorted([a.id, b.id]))

    def test_a_restart_between_two_instances_commits_asks_only_the_one_not_yet_asked(self):
        h = self.harness()
        a, b = self.two(h)
        real = h.book._record_intents
        calls = []

        def dies_at_the_second(inst, *args, **kw):
            calls.append(inst.id)
            if len(calls) == 2:
                raise KeyboardInterrupt("the House is killed")
            return real(inst, *args, **kw)

        with mock.patch.object(h.book, "_record_intents", side_effect=dies_at_the_second):
            with self.assertRaises(KeyboardInterrupt):
                h.tick(16, 31)
        self.assertEqual([i.instance for i in h.intents(kind="buy")], [a.id])
        h.book = h.new_book()                                       # the restart
        h.tick(16, 32)
        self.assertEqual([[j["key"] for j in call["jobs"]] for call in h.decider.jobs], [[a.id, b.id], [b.id]])
        self.assertEqual(sorted(i.instance for i in h.intents(kind="buy")), [a.id, b.id])

    def test_a_failure_is_counted_once_a_session(self):
        h = self.harness()
        a, _ = self.two(h)
        h.decider.fail = True
        with mock.patch.object(h.book, "_house_exits", side_effect=RuntimeError("the House's exits broke")):
            h.tick(16, 31)
        h.tick(16, 32)                                              # the same close again: still failing
        self.assertEqual(h.book._instance(a.id).failed_decides, 1)
        self.assertEqual(len(warnings(h)), 1)
        # The cut-off's own count (no decide ran before the next close window) reads the same mark.
        h.state.put("eq_decide", {"day": "2026-10-09", "status": "done"})
        h.tick(15, 54, 30, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decide")["status"], "failed")
        self.assertEqual(h.book._instance(a.id).failed_decides, 1, "Monday's failure was already counted")


# ------------------------------------------------------------------------------------- A8.5's failed decides
class Answers(T.Decider):
    """The decider kind answering each job what the test set for its key (default: the planned intents)."""

    def __init__(self):
        super().__init__()
        self.answers: dict[str, dict] = {}

    def kind(self, kind, op, payload, *, budget_seconds=None):
        answer = super().kind(kind, op, payload, budget_seconds=budget_seconds)
        for key in answer["results"]:
            if key in self.answers:
                answer["results"][key] = dict(self.answers[key])
        return answer


class FailedDecides(T.BookTest):
    def test_what_the_child_says_failed_is_a_failed_decide(self):
        h = self.harness()
        h.decider = Answers()
        h.book = h.new_book()
        rows = {name: T.family_row(name) for name in ("raises", "missing", "no-ctx", "fine")}
        h.families.rows = rows
        insts = {name: h.instance(name) for name in rows}
        lots = {name: h.lot(inst, "SPY", "0.1", "590") for name, inst in insts.items()}
        stats = {"calls": 1, "errors": 1, "timeouts": 0, "seconds": 0.0, "messages": ["decide: ValueError: boom"],
                 "disqualified": None}
        h.decider.answers = {
            insts["raises"].id: {"intents": [], "stats": stats, "ctx_sha": "c" * 64, "failed": True,
                                 "why": "decide: ValueError: boom"},
            insts["missing"].id: {"intents": [], "stats": None, "missing": True, "failed": True},
            insts["no-ctx"].id: {"intents": [], "stats": stats, "failed": True, "error": "ctx: ValueError: no bar"}}
        h.decide_setup(MONDAY)
        out = h.tick(16, 31)
        self.assertEqual(out["decided"], [f"{insts['fine'].id}: 0"])
        got = {name: h.book._instance(inst.id) for name, inst in insts.items()}
        self.assertEqual({name: i.failed_decides for name, i in got.items()},
                         {"raises": 1, "missing": 1, "no-ctx": 1, "fine": 0})
        # The program's own failure spends the session, as in the Gym; one the House could not ask may be asked again.
        self.assertEqual({name: i.last_decided_day for name, i in got.items()},
                         {"raises": "2026-10-12", "missing": None, "no-ctx": None, "fine": "2026-10-12"})
        self.assertIn("its own decide failed: decide: ValueError: boom", got["raises"].why)
        self.assertIn("holds no loaded program", got["missing"].why)
        self.assertIn("ctx: ValueError", got["no-ctx"].why)
        self.assertNotIn(insts["missing"].id, h.book._loaded, "loaded again before its next decide")
        self.assertEqual(h.state.get("eq_decide")["instances"], sorted([insts["raises"].id, insts["fine"].id]))
        self.assertEqual(len(warnings(h)), 1)
        self.assertEqual(h.intents(kind="house_exit"), [])
        h.decide_setup(TUESDAY)
        h.tick(16, 31, day=TUESDAY)
        self.assertEqual({name: h.book._instance(inst.id).failed_decides for name, inst in insts.items()},
                         {"raises": 2, "missing": 2, "no-ctx": 2, "fine": 0})
        self.assertEqual(sorted((e.lid, e.tag, e.exec_day, e.at) for e in h.intents(kind="house_exit")),
                         sorted((lots[name].lid, "house", "2026-10-14", "open") for name in ("raises", "missing", "no-ctx")))
        self.assertEqual(sum(1 for load in h.decider.loads if load[0] == insts["missing"].id), 2)

    def test_one_failed_decide_a_session_whatever_failed(self):
        """The program's own decide failed on Monday, and Tuesday's morning audit finds Monday's bars changed: one
        failed decide for that session, not two (two SESSIONS of failed decides exit a program's lots)."""
        h = self.harness()
        h.decider = Answers()
        h.book = h.new_book()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        h.decider.answers = {inst.id: {"intents": [], "stats": {}, "ctx_sha": "c" * 64, "failed": True, "why": "boom"}}
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        h.market.bar_rows["raw"]["SPY"][-1]["c"] += 1.0
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["audit"], "mismatch")
        self.assertEqual(h.book._instance(inst.id).failed_decides, 1)
        self.assertEqual(h.intents(kind="house_exit"), [])

    def test_a_failed_answers_intents_are_never_recorded(self):
        h = self.harness()
        h.decider = Answers()
        h.book = h.new_book()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        h.decider.answers = {inst.id: {"intents": [{"buy": "SPY", "share": 0.5}], "stats": {}, "ctx_sha": "c" * 64,
                                       "failed": True}}
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        self.assertEqual(h.intents(), [])
        self.assertIn("it raised, ran past its limit or is disqualified", h.book._instance(inst.id).why)


class TheChildsAnswer(unittest.TestCase):
    """The real child (`league/equity/child.py` through `InlineDecider`) under the real book: a program whose decide
    raises every session leaves its lot by A8.5's rule, as it does in its replay (league/equity/engine.py `decide`)."""

    def setUp(self):
        self.tmp = T.tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def harness(self, code: str) -> tuple[T.Harness, L.Instance, list]:
        h = T.Harness(T.Path(self.tmp.name))
        self.addCleanup(h.state.close)
        h.decider = InlineDecider()
        said = []
        real = h.decider.kind

        def kind(name, op, payload, **kw):
            answer = real(name, op, payload, **kw)
            said.append(answer)
            return answer

        h.decider.kind = kind
        h.book = h.new_book()
        inst = h.instance()
        h.families.rows[SPY]["code"] = code
        inst.code = code
        h.book._save_instance(inst)
        return h, inst, said

    def test_a_program_that_raises_every_session_leaves_at_the_open_after_the_second(self):
        h, inst, said = self.harness(BOOM)
        lot = h.lot(inst, "SPY", "0.5", "590")
        seen = []
        for day in (MONDAY, TUESDAY):
            h.decide_setup(day)
            h.tick(16, 21, day=day)
            out = h.tick(16, 31, day=day)
            self.assertFalse(out.get("errors"), out)
            got = h.book._instance(inst.id)
            seen.append((got.failed_decides, got.last_decided_day, len(h.intents(kind="house_exit"))))
        self.assertEqual(seen, [(1, "2026-10-12", 0), (2, "2026-10-13", 1)])
        answer = said[-1]["results"][inst.id]
        self.assertIs(answer["failed"], True)
        self.assertIn("ValueError: boom", answer["why"])
        self.assertEqual((answer["intents"], answer["stats"]["errors"]), ([], 2))
        [exit_] = h.intents(kind="house_exit")
        self.assertEqual((exit_.lid, exit_.tag, exit_.exec_day, exit_.at), (lot.lid, "house", "2026-10-14", "open"))
        self.assertEqual(len(warnings(h)), 2, "an alert each session it failed")

    def test_a_program_that_answers_is_not_failed(self):
        h, inst, said = self.harness(QUIET)
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        self.assertIs(said[-1]["results"][inst.id]["failed"], False)
        self.assertNotIn("why", said[-1]["results"][inst.id])
        got = h.book._instance(inst.id)
        self.assertEqual((got.failed_decides, got.last_decided_day), (0, "2026-10-12"))

    def test_the_child_marks_a_missing_runner_and_a_broken_ctx_failed(self):
        state: dict = {}
        answer = CH.handle("decide", {"jobs": [{"key": "gone@1:r", "inputs": None}]}, state)
        self.assertEqual(answer["results"]["gone@1:r"], {"intents": [], "stats": None, "missing": True, "failed": True})
        self.assertTrue(CH.handle("load", {"key": "k@1:r", "code": QUIET, "params": {}, "name": "k"}, state)["ok"])
        broken = CH.handle("decide", {"jobs": [{"key": "k@1:r", "inputs": object()}]}, state)["results"]["k@1:r"]
        self.assertTrue(broken["failed"])
        self.assertTrue(broken["error"].startswith("ctx: "))


class Marks(T.BookTest):
    def test_a_late_decide_marks_only_the_lots_held_at_its_close(self):
        """A catch-up for Monday's close that runs on Tuesday morning: a lot bought since is not marked with a price
        from before it was bought (its open risk stays on its entry price)."""
        h = self.harness()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        held = h.lot(inst, "SPY", "0.2", "590", opened=FRIDAY)
        since = h.lot(inst, "SPY", "0.2", "601", opened=TUESDAY)
        h.decide_setup(MONDAY)
        h.tick(10, 0, day=TUESDAY)
        self.assertEqual(h.book._instance(inst.id).last_decided_day, "2026-10-12")
        self.assertEqual(h.book._lot(held.lid).mark, D(str(h.market.bar_rows["raw"]["SPY"][-1]["c"])))
        self.assertIsNone(h.book._lot(since.lid).mark)


# ------------------------------------------------------------------------------------- the House's exit rules
class HouseExits(T.BookTest):
    def test_a_rule_due_at_the_open_takes_the_place_of_the_programs_close_sell(self):
        h = self.harness()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        h.decider.needs[inst.id] = {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 2}
        due = h.lot(inst, "SPY", "0.2", "590", opened=FRIDAY)       # held its 2 sessions by Tuesday's open
        mine = h.lot(inst, "SPY", "0.2", "590", opened=FRIDAY)
        young = h.lot(inst, "SPY", "0.2", "590", opened=MONDAY)
        h.decider.plans[inst.id] = [{"sell": due.lid, "at": "close"}, {"sell": mine.lid, "at": "open"},
                                    {"sell": young.lid, "at": "close"}]
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        by_lot = {(i.lid, i.kind): i for i in h.intents()}
        superseded = by_lot[(due.lid, "sell")]
        self.assertEqual(superseded.status, "refused")
        self.assertIn(f"lot {due.lid} leaves at the open by the House's rule (max_hold", superseded.why)
        house = by_lot[(due.lid, "house_exit")]
        self.assertEqual((house.status, house.at, house.exec_day, house.tag), ("planned", "open", "2026-10-13", "max_hold"))
        # The program's own sell at the open goes first in the Gym too; a lot no rule is due on keeps its close sell.
        self.assertEqual(by_lot[(mine.lid, "sell")].status, "planned")
        self.assertNotIn((mine.lid, "house_exit"), by_lot)
        self.assertEqual(by_lot[(young.lid, "sell")].status, "planned")
        self.assertNotIn((young.lid, "house_exit"), by_lot)
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual((h.book._lot(due.lid).reason, h.book._lot(due.lid).exit_at), ("max_hold", "open"))
        self.assertEqual(h.book._lot(mine.lid).reason, "program")
        self.assertEqual(h.book._lot(young.lid).status, "open", "its close sell waits for 15:55")
        # The program reads why its close sell did not go, as the Gym's rejects tell it.
        h.decide_setup(TUESDAY)
        h.decider.plans[inst.id] = []
        h.tick(16, 31, day=TUESDAY)
        self.assertTrue(any("by the House's rule" in r for r in h.decider.jobs[-1]["jobs"][0]["inputs"]["rejects"]))

    def test_a_retired_programs_close_sell_yields_too_and_a_house_exit_already_planned_stands(self):
        h = self.harness()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        selling = h.lot(inst, "SPY", "0.2", "590")
        carried = h.lot(inst, "SPY", "0.2", "590")
        sell = h.intent(inst, "sell", symbol="SPY", lid=selling.lid, at_="close", exec_day=TUESDAY, decided=MONDAY)
        h.intent(inst, "house_exit", symbol="SPY", lid=carried.lid, exec_day=TUESDAY, decided=MONDAY, tag="carried")
        h.families.rows[SPY]["band"] = "retired"
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        self.assertEqual(h.get_intent(sell.iid).status, "refused")
        self.assertEqual(sorted((e.lid, e.tag, e.at) for e in h.intents(kind="house_exit", status="planned")),
                         sorted([(selling.lid, "retired", "open"), (carried.lid, "carried", "open")]))


# ------------------------------------------------------------------------------------- the bars of the lots
class LotBars(T.BookTest):
    def test_a_held_symbol_is_read_with_no_live_program(self):
        h = self.harness()
        gone = h.instance(QQQ)
        gone.retired_at, gone.why = T.at(FRIDAY, 16, 31), "demoted: its band is candidate"
        h.book._save_instance(gone)
        h.families.rows = {}
        h.lot(gone, "QQQ", "0.4", "490")
        h.decide_setup(MONDAY, symbols=("QQQ",))
        h.tick(16, 21)
        days = {r["day"] for r in h.state.rows("SELECT day FROM eq_bars WHERE symbol='QQQ' AND adjustment='raw'")}
        self.assertIn("2026-10-12", days)
        self.assertEqual(h.state.get("eq_decision")["symbols"], ["QQQ"])
        record = h.state.get("eq_decide")
        self.assertEqual((record["status"], record["why"], record["instances"]), ("done", "no live program", []))
        self.assertEqual(h.decider.jobs, [])
        h.tick(8, 31, day=TUESDAY)                                  # and audited, for its twin
        self.assertEqual({r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day='2026-10-12'")}, {"ok"})

    def test_a_lot_closed_in_the_session_and_a_symbol_no_live_program_needs(self):
        h = self.harness()
        h.families.rows = {SPY: T.family_row()}
        live = h.instance()
        gone = h.instance(QQQ)
        gone.retired_at, gone.why = T.at(FRIDAY, 16, 31), "retired: its family is retired"
        h.book._save_instance(gone)
        h.families.rows.pop(QQQ)
        closed = h.lot(gone, "QQQ", "0.4", "490")
        closed.status, closed.qty, closed.exit_day, closed.closed_at = "closed", D(0), "2026-10-12", T.at(MONDAY, 9, 31)
        h.book._save_lot(closed)
        h.venue.held.pop("QQQ")
        h.decide_setup(MONDAY, symbols=("SPY", "QQQ"))
        h.tick(16, 21)
        h.tick(16, 31)
        self.assertEqual(h.state.get("eq_decision")["symbols"], ["QQQ", "SPY"])
        self.assertEqual([j["key"] for j in h.decider.jobs[0]["jobs"]], [live.id])
        self.assertEqual(h.book._lot_symbols("2026-10-13"), set(), "a lot closed on Monday is not Tuesday's")

    def test_a_missing_bar_of_a_held_symbol_waits_for_its_grace_then_goes_without(self):
        h = self.harness()
        gone = h.instance(QQQ)
        gone.retired_at = T.at(FRIDAY, 16, 31)
        h.book._save_instance(gone)
        h.families.rows = {}
        h.lot(gone, "QQQ", "0.4", "490")
        h.decide_setup(MONDAY, symbols=("QQQ",))
        for name in ("raw", "all"):
            h.market.bar_rows[name]["QQQ"] = h.market.bar_rows[name]["QQQ"][:-1]     # no bar for Monday yet
        out = h.tick(16, 31)
        self.assertIn("waiting for the bars of QQQ", out["decide"])
        self.assertEqual(h.state.get("eq_decide")["day"], "2026-10-09")
        h.tick(17, 1)
        self.assertEqual(h.state.get("eq_decide")["day"], "2026-10-12")


# ------------------------------------------------------------------------------------- the morning audit (A8.11)
class Audit(T.BookTest):
    def decided(self, symbols=("SPY",)) -> tuple[T.Harness, dict[str, L.Intent]]:
        h = self.harness()
        buys = {}
        h.families.rows = {}
        for symbol in symbols:
            family = f"reads-{symbol.lower()}"
            h.families.rows[family] = T.family_row(family, symbols=(symbol,))
            inst = h.instance(family)
            h.decider.needs[inst.id] = {"symbols": [symbol], "history": 5, "max_hold_sessions": 20}
            h.decider.plans[inst.id] = [{"buy": symbol, "share": 0.5}]
        h.decide_setup(MONDAY, symbols=symbols)
        h.tick(16, 31)
        for intent in h.intents(kind="buy"):
            buys[intent.symbol] = intent
        return h, buys

    def test_a_volume_that_moved_after_the_close_is_a_note_and_cancels_nothing(self):
        h, buys = self.decided()
        h.market.bar_rows["raw"]["SPY"][-1]["v"] += 1234            # late and after-hours prints counted in the 1Day bar
        out = h.tick(8, 31, day=TUESDAY)
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"], decision["volume"]), ("ok", [], ["SPY"]))
        self.assertIn("volume of SPY", out["bars_volume"])
        self.assertEqual(h.get_intent(buys["SPY"].iid).status, "planned")
        self.assertEqual(h.book._instance(key_of("reads-spy")).failed_decides, 0)
        self.assertEqual({r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day='2026-10-12'")}, {"ok"})
        self.assertEqual(h.alerts, [])
        self.assertEqual(h.state.get("eq_bars_audit"),
                         {"2026-10-12": {"symbols": [], "volume": ["SPY"], "at": T.at(TUESDAY, 8, 31)}})
        noted = [payload for kind, payload in h.events if kind == "equity.bars_audit"]
        self.assertEqual(noted, [{"day": "2026-10-12", "mismatch": [], "volume": ["SPY"], "programs": []}])
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"])
        # The stored row is still the one the decision read (the 16:20 volume).
        [stored] = h.state.rows("SELECT v FROM eq_bars WHERE day='2026-10-12' AND symbol='SPY' AND adjustment='raw'")
        self.assertEqual(D(stored["v"]), D(str(h.market.bar_rows["raw"]["SPY"][-1]["v"])) - 1234)

    def test_an_older_days_volume_is_a_note_too_and_a_price_is_still_a_mismatch(self):
        h, buys = self.decided()
        h.market.bar_rows["raw"]["SPY"][-3]["v"] += 10
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["audit"], "ok")
        g, buys = self.decided()
        g.market.bar_rows["raw"]["SPY"][-1]["v"] += 10
        g.market.bar_rows["raw"]["SPY"][-1]["h"] += 0.01
        g.tick(8, 31, day=TUESDAY)
        decision = g.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"], decision["volume"]), ("mismatch", ["SPY"], []))
        self.assertEqual(g.get_intent(buys["SPY"].iid).status, "canceled")

    def test_each_symbol_is_marked_on_its_own_verdict(self):
        h, buys = self.decided(symbols=("SPY", "QQQ"))
        h.market.bar_rows["raw"]["QQQ"][-1]["c"] += 1.0
        h.market.bar_rows["raw"]["SPY"][-1]["v"] += 99
        h.tick(8, 31, day=TUESDAY)
        marks = {(r["symbol"], r["audit"]) for r in h.state.rows(
            "SELECT symbol, audit FROM eq_bars WHERE day='2026-10-12'")}
        self.assertEqual(marks, {("SPY", "ok"), ("QQQ", "mismatch")})
        decision = h.state.get("eq_decision")
        self.assertEqual((decision["audit"], decision["mismatch"], decision["volume"]), ("mismatch", ["QQQ"], ["SPY"]))
        self.assertEqual((h.get_intent(buys["SPY"].iid).status, h.get_intent(buys["QQQ"].iid).status),
                         ("planned", "canceled"))
        self.assertEqual((h.book._instance(key_of("reads-spy")).failed_decides,
                          h.book._instance(key_of("reads-qqq")).failed_decides), (0, 1))
        self.assertEqual(h.state.get("eq_bars_audit")["2026-10-12"]["symbols"], ["QQQ"])
        self.assertEqual(h.state.get("eq_bars_audit")["2026-10-12"]["volume"], ["SPY"])
        self.assertEqual(len(errors(h)), 1)

    def test_a_symbol_the_decision_did_not_read_is_not_marked(self):
        h, _ = self.decided()
        h.state.execute("INSERT INTO eq_bars(day, symbol, adjustment, c, fetched_at, sha) VALUES(?,?,?,?,0,'x')",
                        ("2026-10-12", "DIA", "raw", "450"))
        h.tick(8, 31, day=TUESDAY)
        marks = dict((r["symbol"], r["audit"]) for r in h.state.rows(
            "SELECT symbol, audit FROM eq_bars WHERE day='2026-10-12' AND adjustment='raw'"))
        self.assertEqual(marks, {"SPY": "ok", "DIA": None})


class AsOf(unittest.TestCase):
    """Two readings of one adjustment=all series, the second rescaled by an event after t: the same as-of prices, to
    the vendor's rounding. The bound is the cent's (`config.rounding_bound`: the rehearsal on real bars found the
    adjusted series rounded to the cent, league/tests/test_equity_rehearsal.py), so the finer grid here agrees too."""

    def readings(self, price: float, factor: float, rescale: float):
        days = [f"2026-10-{d:02d}" for d in (5, 6, 7, 8, 9)]
        raw = {d: (round(price + 0.37 * i, 4),) * 4 + (1000,) for i, d in enumerate(days)}
        old_all = {d: tuple(round(x * factor, 4) for x in raw[d][:4]) for d in days}
        fresh_raw = {d: dict(zip("ohlcv", raw[d])) for d in days}
        fresh_all = {d: dict(zip("ohlc", (round(x * factor * rescale, 4) for x in raw[d][:4]))) for d in days}
        return raw, old_all, fresh_raw, fresh_all, days[-1]

    def test_a_rescaled_series_agrees_at_every_price_level(self):
        for price in (600.0, 220.0, 87.13, 41.07, 12.31):
            for rescale in (1.0, 0.9925, 0.25):
                raw, old_all, fresh_raw, fresh_all, day = self.readings(price, 0.9871, rescale)
                self.assertTrue(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), (price, rescale))
                self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "ok")

    def test_a_price_that_really_changed_does_not(self):
        # A cent on one adjusted close is the vendor's own rounding (two cent-rounded prices on either side of a
        # restatement differ by that much); a move of a fifth of a percent is not, at any of these prices.
        for price in (600.0, 41.07):
            raw, old_all, fresh_raw, fresh_all, day = self.readings(price, 0.9871, 0.9925)
            first = sorted(fresh_all)[0]
            fresh_all[first]["c"] = round(fresh_all[first]["c"] * 1.002, 4)
            self.assertFalse(L._as_of_equal(raw, old_all, fresh_raw, fresh_all, day), price)
            self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")

    def test_the_verdicts(self):
        raw, old_all, fresh_raw, fresh_all, day = self.readings(41.07, 0.9871, 1.0)
        fresh_raw[day]["v"] = 1001
        self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "volume")
        fresh_raw[day]["l"] = round(fresh_raw[day]["l"] - 0.0001, 4)           # one vendor step on a raw price: exact
        self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")
        raw, old_all, fresh_raw, fresh_all, day = self.readings(41.07, 0.9871, 1.0)
        fresh_raw.pop(sorted(fresh_raw)[0])                                     # another set of sessions
        self.assertEqual(L._bars_verdict(raw, old_all, fresh_raw, fresh_all, day), "mismatch")


# ------------------------------------------------------------------------------------- the buy-and-hold's basis
class BuyAndHold(T.BookTest):
    def closed(self, h: T.Harness, inst: L.Instance) -> None:
        for cash in ("6", "-3"):
            lot = h.lot(inst, "SPY", "0.5", "600", opened=FRIDAY)
            lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), D(cash), "2026-10-12", \
                T.at(MONDAY, 9, 31)
            h.book._save_lot(lot)

    def bars(self, h: T.Harness, before: str, last: str, shas=("a", "a")) -> None:
        for (day, close), sha in zip((("2026-10-08", before), ("2026-10-12", last)), shas):
            h.state.execute("INSERT OR REPLACE INTO eq_bars(day, symbol, adjustment, c, fetched_at, sha) "
                            "VALUES(?,?,?,?,0,?)", (day, "SPY", "all", close, sha))

    def test_two_closes_of_one_fetch_are_one_series(self):
        h = self.harness()
        inst = h.instance()
        self.closed(h, inst)
        self.bars(h, "100", "102")
        self.assertEqual(h.book._record_of(inst.family, inst.version, None).bh_pnl, D("300") * (D("102") / D("100") - 1))
        self.assertEqual(h.market.bar_calls, [], "nothing read from the vendor")

    def test_two_fetches_are_read_again_in_one_or_not_priced(self):
        """The first close was stored weeks before the last, and an ex-date lies between: the stored `before` is not
        adjusted for it, so its ratio to `last` would lose the dividend. Never mixed: read again in one fetch (the daily
        band sync, once the record has the closes the sizing-up rule needs) or left unpriced (a sizing at send time)."""
        h = self.harness(table=T.equity_table(sized_min_trades=2))
        inst = h.instance()
        self.closed(h, inst)
        self.bars(h, "100", "102", shas=("a", "b"))
        self.assertIsNone(h.book._record_of(inst.family, inst.version, None).bh_pnl)
        self.assertEqual(h.market.bar_calls, [])
        early = T.dataclasses.replace(h.table, equity=T.equity_table(sized_min_trades=3))
        with mock.patch.object(h.book, "table", early):             # a record the rule cannot size up yet: no read
            self.assertIsNone(h.book._record_of(inst.family, inst.version, None, refetch=True).bh_pnl)
        self.assertEqual(h.market.bar_calls, [])
        h.market.bar_rows["all"]["SPY"] = [{"t": "2026-10-08T04:00:00Z", "c": 99.25}, {"t": "2026-10-09T04:00:00Z", "c": 7.0},
                                           {"t": "2026-10-12T04:00:00Z", "c": 102.0}]
        record = h.book._record_of(inst.family, inst.version, None, refetch=True)
        self.assertEqual(record.bh_pnl, D("300") * (D("102.0") / D("99.25") - 1))
        self.assertEqual(h.market.bar_calls, [(("SPY",), "1Day", "2026-10-08", "2026-10-13", "all")])
        h.market.bar_rows["all"]["SPY"] = h.market.bar_rows["all"]["SPY"][1:]   # the vendor lacks the first day
        self.assertIsNone(h.book._record_of(inst.family, inst.version, None, refetch=True).bh_pnl)
        with mock.patch.object(h.market, "bars", side_effect=RuntimeError("the vendor is down")):
            self.assertIsNone(h.book._record_of(inst.family, inst.version, None, refetch=True).bh_pnl)

    def test_only_the_daily_band_sync_reads_the_vendor(self):
        h = self.harness()
        h.families.rows = {SPY: T.family_row()}
        inst = h.instance()
        seen = []
        real = h.book._record_of

        def record_of(*args, **kw):
            seen.append(kw.get("refetch", False))
            return real(*args, **kw)

        h.decide_setup(MONDAY)
        with mock.patch.object(h.book, "_record_of", side_effect=record_of):
            h.tick(16, 31)                                           # the decision's own sync
            h.families.rows[QQQ] = T.family_row(QQQ, band="candidate")
            h.tick(16, 40)                                           # the seating pass
        self.assertEqual(seen, [True, False])
        sized = h.instance("sized-one", band="sized")
        self.closed(h, sized)
        self.bars(h, "100", "102", shas=("a", "b"))
        calls = len(h.market.bar_calls)
        self.assertEqual(h.book._sleeve_share(sized), D("0.50"))
        self.assertEqual(len(h.market.bar_calls), calls, "a sizing at send time reads no bar")


# ------------------------------------------------------------------------------------- the sizing-up step, parked
class TheSizingUpStepIsParked(T.BookTest):
    """The captain's decision on the review of A20's study (Oct 11, 2026): `equity_money.sized.min_trades` is 1000 at
    the table in force. The owner's loss budget covers all real money, and a Sized program's lots carry no Probe mark
    (their closes would join neither the window, the total nor the program's -$300 line), so no equity program is
    Sized: every real equity close stays inside the budget's tallies. The rule itself stays as pre-registered."""

    def winner(self, equity_table):
        """A Probe program with 999 winning real closes (a spread among them, the buy-and-hold priced and beaten, long
        at Probe) in the real book under `equity_table`; (the harness, its instance, its families row)."""
        h = self.harness(table=equity_table)
        h.families.rows = {SPY: T.family_row(band="probe")}
        inst = h.instance()
        h.state.put("eq_band_since", {inst.id: {"band": "probe", "day": "2026-01-02"}})
        with h.state.transaction():
            for i in range(999):
                lot = h.lot(inst, "SPY", "0.5", "600", opened=FRIDAY)
                lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), D("3" if i % 2 else "1"), \
                    MONDAY.isoformat(), T.at(MONDAY, 9, 31)
                h.book._save_lot(lot)
        h.venue.held.clear()
        for day, close in (("2026-10-08", "100"), ("2026-10-12", "100.001")):   # one fetch: one series
            h.state.execute("INSERT OR REPLACE INTO eq_bars(day, symbol, adjustment, c, fetched_at, sha) "
                            "VALUES(?,?,?,?,0,?)", (day, "SPY", "all", close, "a"))
        return h, inst, h.families.rows[SPY]

    def synced(self, h):
        """The decision's own band sync, with money's real rule (the base class stubs it)."""
        h.decide_setup(MONDAY)
        with mock.patch.object(B, "next_band", REAL_NEXT_BAND):
            h.tick(16, 31)
        return h.families.moves

    def test_a_program_with_999_winning_real_closes_is_still_probe_and_its_closes_are_in_the_tallies(self):
        from league.live import money as M
        from league.live import real as R

        in_force = M.EquityTable.from_constitution()                # the table in force, not the harness's invented one
        h, inst, row = self.winner(in_force)
        et = h.table.equity
        self.assertEqual((et.sized_min_trades, h.table.probe_loss_basis), (1000, "net"))
        record = h.book._record_of(inst.family, inst.version, row)
        self.assertEqual((record.n, record.pnl, record.realized_net), (999, D("1997"), D("1997")))
        self.assertEqual(REAL_NEXT_BAND(row, record, et, seat_free=True),
                         ("probe", "999 real closes, under the 1000 sizing up needs"))
        self.assertEqual(self.synced(h), [], "no band move")
        self.assertEqual((h.families.rows[SPY]["band"], h.book._instance(inst.id).band), ("probe", "probe"))
        # Its closes are in the Probe tallies, every one: a Sized lot (no mark) would be in none of them.
        figures = L.probe_figures(h.state.rows, weights=et.open_risk_weight)
        self.assertEqual((len(figures.closes), sum(cash for _, cash in figures.closes)), (999, D("1997")))
        self.assertEqual(h.state.rows("SELECT COUNT(*) AS n FROM eq_lots WHERE status='closed' AND probe=1")[0]["n"], 999)
        # And so in the shared loss budget: a later loss is read against them (the net basis), from inception.
        loss = h.lot(inst, "SPY", "0.5", "600", opened=FRIDAY)
        loss.status, loss.qty, loss.cash, loss.exit_day, loss.closed_at = "closed", D(0), D("-2500"), \
            MONDAY.isoformat(), T.at(MONDAY, 9, 32)
        h.book._save_lot(loss)
        _, _, total, _, _ = R.probe_figures(h.state.rows, day=MONDAY.isoformat(), table=h.table)
        self.assertEqual(total, D("503"), "2,500 lost less the 1,997 its Probe closes had made")

    def test_what_the_park_holds_back(self):
        """The same program under the rule's own 20 closes: the book's sync moves it to Sized. Parking is the row."""
        from league.live import money as M

        pre_registered = T.dataclasses.replace(M.EquityTable.from_constitution(), sized_min_trades=20)
        h, inst, row = self.winner(pre_registered)
        moves = self.synced(h)
        self.assertEqual([(family, band) for family, band, _ in moves], [(SPY, "sized")])
        self.assertIn("999 real closes", moves[0][2])
        self.assertEqual(h.families.rows[SPY]["band"], "sized")

if __name__ == "__main__":
    unittest.main()
