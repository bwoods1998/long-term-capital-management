"""DC1 (the rehearsal of Oct 15, 2026; league/ops/dlane_report.py `dc1_alarms`): A DONE CHECKPOINT THAT IS REACHED
AND DOES NOT HOLD IS TOLD. Before it only a final holding checkpoint was told (A8 and the stall's `done` cause); a
final failing one, or one stuck short of final, passed in silence.

- A meter's LATEST checkpoint that is final and does not hold raises a warning, standing until the next checkpoint.
  The text names the items that do not hold.
- One still not final at the pre-open of the 2nd session after the New York day of its last counted close raises one
  too, holding or not. Before that it raises nothing: a close is final at the next session's pre-open by design (a
  Friday's at Monday's, one before a holiday at the session after it). Counted in sessions, not UTC days (the review
  of Oct 15, 2026).
- A reading that is not final names no verdict: no `holds`, no items not held (item 3 holds the net's sign), in the
  text or in the row. Only the close count, the sessions since and `final_why`.
- A final holding checkpoint raises no DC1 (A8 is its alarm).
- No text holds a dollar sign, a decimal figure, a net, a program row or a buy-and-hold.
- The stall job reads it as a House warning with NO owner step, so it can never fail an item-7 day, and its mail names
  DC1 before the other warnings, the items whole inside its cut.

The meters are the House's own (`meter`) over invented options closes; every figure is invented."""

from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from league.ops import dlane_report as R
from league.ops import stall as ST
from league.swarm import dlane
from league.tests.test_dlane_report import Fixture as ReportFixture

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
ALL = dlane.DONE["routes_all"]
#: What a DC1 text may never hold: a dollar sign or a decimal figure (money, a gap, a share).
MONEY = re.compile(r"\$|\d[.,]\d")


def ep(text: str) -> float:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def nyday(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, NY).date().isoformat()


class Store:
    """The meter's one read of the swarm store with options closes only: the nightly rows (none here)."""

    def __init__(self, root: Path):
        self.root = root

    def forward(self, fid):  # noqa: ARG002
        return []


def options_close(pid: int, family: str, closed: str, *, pnl: str = "1.25", basis: str = "broker") -> dict:
    """An options close as `closes` builds one (route :r)."""
    at = ep(closed)
    return {"pid": pid, "family": family, "instance": f"{family}@1:r", "version": 1, "route": "d2_real", "code": ":r",
            "house": False, "lane": "alpha", "closed_at": at, "day": nyday(at), "opened_day": nyday(at - 3 * 86400),
            "opened_at": at - 3 * 86400, "root": "SPY", "type": "long_call", "legs": [], "entry": 0.5,
            "opened_qty": 1, "max_loss_usd": 50.0, "cash_usd": Decimal(pnl), "pnl_usd": Decimal(pnl),
            "fee_basis": basis, "priced": True, "status": "closed", "bh": {"delta_usd": 7.77, "risk_usd": 8.88}}


class Research:
    """DONE-RULE item 7 a UTC day: every day holds but `failed`."""

    def __init__(self, failed=()):
        self.failed = set(failed)

    def __call__(self, first: str, last: str) -> dict:
        d, days = dt.date.fromisoformat(first), []
        while d <= dt.date.fromisoformat(last):
            days.append({"day": d.isoformat(), "holds": d.isoformat() not in self.failed})
            d += dt.timedelta(days=1)
        bad = [x["day"] for x in days if not x["holds"]]
        return {"first_day": first, "last_day": last, "holds": bool(days) and not bad,
                "why": "; ".join(f"{day}: no Validation" for day in bad) or None, "days": days}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))

    def closes(self, n: int = 30, *, last: str = "2026-11-03T14:31:00Z", start: str = "2026-10-13T13:31:00Z",
               pnl: str = "1.25") -> list[dict]:
        """`n` closes, half of program A then half of program B, one every 12 hours from `start`, the last at `last`."""
        rows, t = [], ep(start)
        for i in range(n - 1):
            family = "prog-a" if i < n // 2 else "prog-b"
            rows.append(options_close(100 + i, family, dt.datetime.fromtimestamp(t + i * 43200, UTC).isoformat(),
                                      pnl=pnl))
        rows.append(options_close(100 + n - 1, "prog-b", last, pnl=pnl))
        return sorted(rows, key=R._order)

    def meter(self, rows, *, now: str, research=None, fees_as_of: str = "2026-12-31", previous=None) -> dict:
        twins = {str(c["pid"]): {"status": "priced", "final": True,
                                 "twin": {"pnl": float(c["pnl_usd"]), "max_loss": c["max_loss_usd"], "r": 0.0}}
                 for c in rows}
        return R.meter(rows, ALL, self.store, previous=previous, research=research or Research(), replay_days={},
                       fees_as_of=fees_as_of, now=ep(now), twins=twins, twins_on=False)

    def done(self, meter: dict) -> dict:
        return {"all": meter, "screen": {"checkpoints": []}}

    def assert_no_money(self, row: dict) -> None:
        self.assertEqual((row["id"], row["level"]), ("DC1", "warning"))
        self.assertNotIn("$", row["text"])
        self.assertIsNone(MONEY.search(row["text"]), row["text"])
        for word in ("net", "by_program", "bh", "buy-and-hold", "pnl", "usd"):
            self.assertNotIn(word, row["text"].lower().replace("not held", "").replace("not final", ""), word)
        self.assertFalse({"net_usd", "by_program", "bh", "programs", "by_route"} & set(row), "no money key beside it")


class AFinalCheckpointThatDoesNotHold(Base):
    def test_is_told_with_the_items_that_do_not_hold(self):
        m = self.meter(self.closes(), now="2026-11-04T14:00:00Z", research=Research(failed={"2026-11-01"}))
        self.assertEqual((m["latest"]["final"], m["latest"]["holds"]), (True, False))
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-04T14:00:00Z"))
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is final and does not hold. Not held: item "
                                      "7 (research 24/7). A House warning: nothing is paused or stopped")
        self.assertEqual((row["meter"], row["at_close"], row["final"], row["holds"], row["not_held"]),
                         ("done_all", 30, True, False, ["item 7 (research 24/7)"]))
        self.assert_no_money(row)

    def test_a_losing_checkpoint_names_the_item_never_the_net(self):
        m = self.meter(self.closes(pnl="-3.75"), now="2026-11-04T14:00:00Z")
        self.assertEqual((m["latest"]["final"], m["latest"]["holds"]), (True, False))
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-04T14:00:00Z"))
        self.assertIn("Not held: item 3 (the bar)", row["text"])
        self.assert_no_money(row)
        self.assertNotIn("3.75", row["text"])
        self.assertNotIn("112", row["text"], "the summed net of the thirty closes")

    def test_it_stands_while_it_is_the_latest_and_is_frozen(self):
        rows = self.closes()
        first = self.meter(rows, now="2026-11-04T14:00:00Z", research=Research(failed={"2026-11-01"}))
        # The next report carries the final reading frozen, whatever research says now: still told.
        again = self.meter(rows, now="2026-11-06T01:30:00Z", previous=first)
        self.assertTrue(again["latest"].get("frozen"))
        self.assertEqual([r["at_close"] for r in R.dc1_alarms(self.done(again), now=ep("2026-11-06T01:30:00Z"))], [30])

    def test_a_final_holding_checkpoint_is_a8s_never_dc1(self):
        m = self.meter(self.closes(), now="2026-11-04T14:00:00Z")
        self.assertEqual((m["latest"]["final"], m["latest"]["holds"]), (True, True))
        self.assertEqual(R.dc1_alarms(self.done(m), now=ep("2026-11-04T14:00:00Z")), [])

    def test_only_the_latest_checkpoint_of_each_meter_is_read(self):
        # The owner's checkpoints (A50, Oct 16, 2026: the 15th close, then every 5th; the 30th and the 40th before).
        # The 15th and the 20th hold program A's closes alone (item 3), and the 20th (Oct 20 01:31Z) also failed its
        # research window, Oct 18-20; the later ones read the days after it and hold, so the latest (the 40th) raises
        # nothing.
        rows = self.closes(40, start="2026-10-10T13:31:00Z", last="2026-11-10T14:31:00Z")
        m = self.meter(rows, now="2026-11-11T14:00:00Z", research=Research(failed={"2026-10-20"}))
        self.assertEqual([(cp["at_close"], cp["final"], cp["holds"]) for cp in m["checkpoints"]],
                         [(15, True, False), (20, True, False), (25, True, True), (30, True, True), (35, True, True),
                          (40, True, True)])
        self.assertEqual([(cp["items"]["3"], cp["items"]["7"]) for cp in m["checkpoints"][:2]], [(False, True), (False, False)])
        self.assertEqual((m["checkpoints"][1]["research_247"]["first_day"], m["checkpoints"][1]["research_247"]["last_day"]),
                         ("2026-10-18", "2026-10-20"))
        self.assertEqual(R.dc1_alarms(self.done(m), now=ep("2026-11-11T14:00:00Z")), [])

    def test_both_meters_are_read(self):
        m = self.meter(self.closes(), now="2026-11-04T14:00:00Z", research=Research(failed={"2026-11-01"}))
        rows = R.dc1_alarms({"all": m, "screen": m}, now=ep("2026-11-04T14:00:00Z"))
        self.assertEqual([r["meter"] for r in rows], ["done_all", "done_screen"])
        self.assertEqual(R.dc1_alarms({"all": {"checkpoints": []}, "screen": {}}, now=ep("2026-11-04T14:00:00Z")), [])
        self.assertEqual(R.dc1_alarms(None, now=0.0), [])


class ACheckpointThatStaysProvisional(Base):
    def provisional(self, closed_at: str, *, holds: bool = True) -> dict:
        return {"all": {"checkpoints": [{
            "at_close": 30, "closed_at": closed_at, "final": False, "holds": holds,
            "items": {"3": True, "4": True, "7": holds},
            "final_why": "the per-close twin of 1 closes has not landed (none yet, or failed and to be asked again)"}]}}

    def test_not_final_at_the_second_sessions_preopen_is_told(self):
        # Tue Nov 3's close. The broker's fees have not posted (the activity reading is of the day before its exit).
        m = self.meter(self.closes(), now="2026-11-04T01:30:00Z", fees_as_of="2026-11-02")
        self.assertTrue(m["provisional"], "it holds, and it is not final")
        for now in ("2026-11-04T01:30:00Z", "2026-11-04T14:00:00Z", "2026-11-05T01:30:00Z", "2026-11-05T13:59:59Z"):
            self.assertEqual(R.dc1_alarms(self.done(m), now=ep(now)), [], now)
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-05T14:00:00Z"))     # Thu Nov 5's pre-open (EST)
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is not final 2 sessions after its last "
                                      "close. Not final because: the broker's fees have not posted for 1 closes (the "
                                      "activity reading is of 2026-11-02). A House warning: nothing is paused or "
                                      "stopped")
        self.assertEqual((row["meter"], row["at_close"], row["final"], row["sessions"]), ("done_all", 30, False, 2))
        self.assert_no_money(row)

    def test_a_reading_that_is_not_final_names_no_verdict(self):
        # Item 3 at a checkpoint is the count, every close priced AND net above zero: "holds" would say the sign.
        for holds in (True, False):
            (row,) = R.dc1_alarms(self.provisional("2026-11-03T14:31:00Z", holds=holds), now=ep("2026-11-06T01:30:00Z"))
            self.assertNotIn("hold", row["text"].lower(), row["text"])
            self.assertNotIn("item", row["text"], row["text"])
            self.assertFalse({"holds", "not_held", "items"} & set(row), "no verdict beside it either")
            self.assert_no_money(row)

    def test_one_that_does_not_hold_and_is_not_final_is_told_too(self):
        m = self.meter(self.closes(), now="2026-11-05T01:30:00Z", fees_as_of="2026-11-02",
                       research=Research(failed={"2026-11-01"}))
        self.assertEqual((m["latest"]["final"], m["latest"]["holds"]), (False, False))
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-05T14:00:00Z"))
        self.assertTrue(row["text"].startswith("DC1: done_all checkpoint at close 30 is not final 2 sessions after its "
                                               "last close. Not final because: "), row["text"])
        self.assertNotIn("item 7", row["text"], "not final: no verdict")
        self.assert_no_money(row)

    def test_a_friday_close_waiting_for_mondays_twin_is_not_told(self):
        # Fri Nov 6's 16:00 ET close: its twin lands at Monday's morning audit, final at Monday's 14:00Z pre-open.
        done = self.provisional("2026-11-06T21:00:00Z")
        for now in ("2026-11-07T01:30:00Z", "2026-11-08T01:30:00Z", "2026-11-09T01:30:00Z", "2026-11-09T14:00:00Z",
                    "2026-11-10T01:30:00Z"):
            self.assertEqual(R.dc1_alarms(done, now=ep(now)), [], now)
        (row,) = R.dc1_alarms(done, now=ep("2026-11-10T14:00:00Z"))            # Tue: the 2nd session's pre-open
        self.assertIn("is not final 2 sessions after its last close", row["text"])

    def test_a_close_before_a_holiday_waits_for_the_session_after_it(self):
        # Wed Nov 25; Thu Nov 26 is Thanksgiving: Fri Nov 27 is the 1st session after it, Mon Nov 30 the 2nd.
        done = self.provisional("2026-11-25T21:00:00Z")
        for now in ("2026-11-26T01:30:00Z", "2026-11-27T01:30:00Z", "2026-11-27T14:00:00Z", "2026-11-30T01:30:00Z"):
            self.assertEqual(R.dc1_alarms(done, now=ep(now)), [], now)
        self.assertEqual(len(R.dc1_alarms(done, now=ep("2026-11-30T14:00:00Z"))), 1)

    def test_an_evening_utc_close_counts_from_its_new_york_day(self):
        # 00:30Z Wed Nov 4 is Tue Nov 3 in New York: the sessions after it are Wed and Thu.
        done = self.provisional("2026-11-04T00:30:00Z")
        self.assertEqual(R.dc1_alarms(done, now=ep("2026-11-05T13:59:00Z")), [])
        self.assertEqual(len(R.dc1_alarms(done, now=ep("2026-11-05T14:00:00Z"))), 1)

    def test_a_clause_of_final_why_with_a_figure_is_left_out(self):
        cp = {"at_close": 30, "closed_at": "2026-11-03T14:31:00Z", "final": False, "holds": False,
              "items": {"3": False, "4": True, "7": True}, "net_usd": -12.5, "by_program": [{"net_usd": -12.5}],
              "bh": {"delta_usd": 7.77}, "why": "net -$12.50 is not above zero",
              "final_why": "the net is -$12.50 so far; the per-close twin of 2 closes has not landed; a gap of 0.25"}
        (row,) = R.dc1_alarms({"all": {"checkpoints": [cp]}}, now=ep("2026-11-06T14:00:00Z"))
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is not final 3 sessions after its last "
                                      "close. Not final because: the per-close twin of 2 closes has not landed; 2 "
                                      "clauses with a figure left out. A House warning: nothing is paused or stopped")
        self.assert_no_money(row)

    def test_a_checkpoint_with_no_readable_close_day_is_told_once_not_final(self):
        cp = {"at_close": 30, "closed_at": None, "final": False, "holds": True, "items": {"3": True, "4": True, "7": True},
              "final_why": "the broker's fees have not posted for 1 closes (the activity reading is of no day)"}
        (row,) = R.dc1_alarms({"all": {"checkpoints": [cp]}}, now=ep("2026-11-04T01:30:00Z"))
        self.assertTrue(row["text"].startswith("DC1: done_all checkpoint at close 30 is not final, and the sessions since "
                                               "its last close cannot be counted. Not final because: "), row["text"])
        self.assertIsNone(row["sessions"])
        self.assert_no_money(row)


class DC1RidesTheReportsAlarms(ReportFixture):
    def test_the_alarms_carry_it_beside_a8(self):
        cp = {"at_close": 30, "closed_at": "2026-10-16T14:31:00Z", "final": True, "holds": False,
              "items": {"3": True, "4": False, "7": True}, "final_why": None}
        out = R.alarms(self.store, {"dlane": {"mode": "gate"}}, R.Lanes(self.store), {"positions": [], "instances": []},
                       [], {"basis_in_force": "gross", "room_gross_units": 3.0},
                       {"all": {"checkpoints": [cp]}, "screen": {"checkpoints": []}}, {"tripped": False},
                       {"cap_usd": 128.9}, None, now=self.now, today="2026-10-20")
        (row,) = [a for a in out if a["id"] == "DC1"]
        self.assertIn("Not held: item 4 (consistent with replay)", row["text"])
        self.assertNotIn("A8", [a["id"] for a in out])


class TheStallTellsItAsAHouseWarning(unittest.TestCase):
    NOW = ep("2026-11-04T14:20:00Z")

    def lane(self, alarms: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / R.FILE).write_text(json.dumps({"at": "2026-11-04T14:00:00Z", "lane": {"mode": "gate"},
                                                        "alarms": alarms, "k5": {}, "done": {}}))
            facts = ST.dlane_facts(tmp)
        return ST._lane_checks(self.NOW, facts, True, done_told=())

    def final_failing(self, items: dict) -> dict:
        cp = {"at_close": 30, "closed_at": "2026-11-03T14:31:00Z", "final": True, "holds": False, "items": items,
              "final_why": None}
        (row,) = R.dc1_alarms({"all": {"checkpoints": [cp]}, "screen": {"checkpoints": [cp]}},
                              now=ep("2026-11-04T14:00:00Z"))[1:]
        return row      # done_screen's: the longer head

    def test_no_owner_step_so_no_item_7_day_fails_for_it(self):
        row = self.final_failing({"3": True, "4": True, "7": False})
        checks = self.lane([row])
        self.assertTrue(checks["dlane"]["stalled"], "a warning of the report: the dlane cause stands, told")
        self.assertIn("DC1: DC1: done_screen checkpoint at close 30 is final and does not hold",
                      checks["dlane"]["what"])
        self.assertEqual(checks["dlane"]["numbers"]["alarms"], "dc1")
        # Research247 fails a UTC day for a stalled cause WITH an owner step only (dlane_report `Research247`): none.
        self.assertIsNone(checks["dlane"]["owner_step"])
        self.assertFalse(checks["done"]["stalled"])
        self.assertNotIn("dlane", R.NEWS_CAUSES)

    def test_the_mail_names_every_item_that_does_not_hold(self):
        row = self.final_failing({"3": False, "4": False, "7": False})
        what = self.lane([row])["dlane"]["what"]
        self.assertIn("Not held: item 3 (the bar), item 4 (consistent with replay), item 7 (research 24/7)", what)

    def test_dc1_and_k5_come_before_four_standing_warnings(self):
        earlier = [{"id": i, "level": "warning", "text": f"{i}: a standing warning"} for i in ("A1", "A2", "A4", "A5")]
        k5 = {"id": "K5", "level": "warning", "text": "K5: the lane reads shadow"}
        checks = self.lane(earlier + [self.final_failing({"3": True, "4": False, "7": True}), k5])
        what = checks["dlane"]["what"]
        self.assertIn("raised 6 warnings (K5: K5: the lane reads shadow; DC1: DC1: done_screen checkpoint", what)
        self.assertIn("A1: A1: a standing warning; A2: A2: a standing warning)", what, "then the report's order")
        self.assertEqual(checks["dlane"]["numbers"]["alarms"], "k5,dc1,a1,a2,a4,a5")


if __name__ == "__main__":
    unittest.main()
