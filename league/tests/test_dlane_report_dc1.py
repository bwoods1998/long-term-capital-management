"""DC1 (the rehearsal of Oct 15, 2026; league/ops/dlane_report.py `dc1_alarms`): A DONE CHECKPOINT THAT IS REACHED
AND DOES NOT HOLD IS TOLD. Before it only a final holding checkpoint was told (A8 and the stall's `done` cause); a
final failing one, or one stuck short of final, passed in silence.

- A meter's LATEST checkpoint that is final and does not hold raises a warning, standing until the next checkpoint.
- One that is not final 2 or more UTC days after the UTC day of its last counted close raises one too, holding or
  not; under 2 days it raises nothing (the Nov 4 01:30Z reading is provisional by design).
- A final holding checkpoint raises no DC1 (A8 is its alarm).
- The text holds the close count, final, holds, the items that do not hold and `final_why`: no dollar sign, no
  decimal figure, no net, no program row, no buy-and-hold.
- The stall job reads it as a House warning with NO owner step, so it can never fail an item-7 day.

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
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is final and does not hold (final true, "
                                      "holds false). Not held: item 7 (research 24/7). A House warning: nothing is "
                                      "paused or stopped")
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
        # The 30th failed on its research window; the 40th reads the days after it and holds.
        rows = self.closes(40, start="2026-10-10T13:31:00Z", last="2026-11-10T14:31:00Z")
        m = self.meter(rows, now="2026-11-11T14:00:00Z", research=Research(failed={"2026-10-20"}))
        self.assertEqual([(cp["at_close"], cp["final"], cp["holds"]) for cp in m["checkpoints"]],
                         [(30, True, False), (40, True, True)])
        self.assertEqual(R.dc1_alarms(self.done(m), now=ep("2026-11-11T14:00:00Z")), [])

    def test_both_meters_are_read(self):
        m = self.meter(self.closes(), now="2026-11-04T14:00:00Z", research=Research(failed={"2026-11-01"}))
        rows = R.dc1_alarms({"all": m, "screen": m}, now=ep("2026-11-04T14:00:00Z"))
        self.assertEqual([r["meter"] for r in rows], ["done_all", "done_screen"])
        self.assertEqual(R.dc1_alarms({"all": {"checkpoints": []}, "screen": {}}, now=ep("2026-11-04T14:00:00Z")), [])
        self.assertEqual(R.dc1_alarms(None, now=0.0), [])


class ACheckpointThatStaysProvisional(Base):
    def test_two_utc_days_without_final_is_told(self):
        # The broker's fees of the 30th close have not posted (the activity reading is of the day before its exit).
        m = self.meter(self.closes(), now="2026-11-04T01:30:00Z", fees_as_of="2026-11-02")
        self.assertTrue(m["provisional"], "it holds, and it is not final")
        self.assertEqual(R.dc1_alarms(self.done(m), now=ep("2026-11-04T01:30:00Z")), [], "one UTC day: by design")
        self.assertEqual(R.dc1_alarms(self.done(m), now=ep("2026-11-04T23:59:59Z")), [])
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-05T00:00:00Z"))
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is not final 2 UTC days after its last "
                                      "close (final false, holds true). Not held: none. Not final because: the "
                                      "broker's fees have not posted for 1 closes (the activity reading is of "
                                      "2026-11-02). A House warning: nothing is paused or stopped")
        self.assert_no_money(row)

    def test_one_that_does_not_hold_and_is_not_final_is_told_too(self):
        m = self.meter(self.closes(), now="2026-11-05T01:30:00Z", fees_as_of="2026-11-02",
                       research=Research(failed={"2026-11-01"}))
        self.assertEqual((m["latest"]["final"], m["latest"]["holds"]), (False, False))
        (row,) = R.dc1_alarms(self.done(m), now=ep("2026-11-05T01:30:00Z"))
        self.assertIn("is not final 2 UTC days after its last close (final false, holds false). Not held: item 7 "
                      "(research 24/7). Not final because: ", row["text"])
        self.assert_no_money(row)

    def test_a_clause_of_final_why_with_a_figure_is_left_out(self):
        cp = {"at_close": 30, "closed_at": "2026-11-03T14:31:00Z", "final": False, "holds": False,
              "items": {"3": False, "4": True, "7": True}, "net_usd": -12.5, "by_program": [{"net_usd": -12.5}],
              "bh": {"delta_usd": 7.77}, "why": "net -$12.50 is not above zero",
              "final_why": "the net is -$12.50 so far; the per-close twin of 2 closes has not landed; a gap of 0.25"}
        (row,) = R.dc1_alarms({"all": {"checkpoints": [cp]}}, now=ep("2026-11-06T14:00:00Z"))
        self.assertEqual(row["text"], "DC1: done_all checkpoint at close 30 is not final 3 UTC days after its last "
                                      "close (final false, holds false). Not held: item 3 (the bar). Not final "
                                      "because: the per-close twin of 2 closes has not landed; 2 clauses with a "
                                      "figure left out. A House warning: nothing is paused or stopped")
        self.assert_no_money(row)

    def test_a_checkpoint_with_no_readable_close_day_is_told_once_not_final(self):
        cp = {"at_close": 30, "closed_at": None, "final": False, "holds": True, "items": {"3": True, "4": True, "7": True},
              "final_why": "the broker's fees have not posted for 1 closes (the activity reading is of no day)"}
        (row,) = R.dc1_alarms({"all": {"checkpoints": [cp]}}, now=ep("2026-11-04T01:30:00Z"))
        self.assertTrue(row["text"].startswith("DC1: done_all checkpoint at close 30 is not final (final false"))
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
    def test_no_owner_step_so_no_item_7_day_fails_for_it(self):
        now = ep("2026-11-04T14:20:00Z")
        row = {"id": "DC1", "level": "warning", "meter": "done_all", "at_close": 30, "final": True, "holds": False,
               "not_held": ["item 7 (research 24/7)"],
               "text": "DC1: done_all checkpoint at close 30 is final and does not hold (final true, holds false). Not "
                       "held: item 7 (research 24/7). A House warning: nothing is paused or stopped"}
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / R.FILE).write_text(json.dumps({"at": "2026-11-04T14:00:00Z", "lane": {"mode": "gate"},
                                                        "alarms": [row], "k5": {}, "done": {}}))
            facts = ST.dlane_facts(tmp)
        checks = ST._lane_checks(now, facts, True, done_told=())
        self.assertTrue(checks["dlane"]["stalled"], "a warning of the report: the dlane cause stands, told")
        self.assertIn("DC1: DC1: done_all checkpoint at close 30 is final and does not hold", checks["dlane"]["what"])
        self.assertEqual(checks["dlane"]["numbers"]["alarms"], "dc1")
        # Research247 fails a UTC day for a stalled cause WITH an owner step only (dlane_report `Research247`): none.
        self.assertIsNone(checks["dlane"]["owner_step"])
        self.assertFalse(checks["done"]["stalled"])
        self.assertNotIn("dlane", R.NEWS_CAUSES)


if __name__ == "__main__":
    unittest.main()
