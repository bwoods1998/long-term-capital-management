"""RELEASE 1019m (the independent review of the live code, A139): THE DAILY REPORT COUNTS THE LEARNERS' LIVE PARTS LOST
(league/events/report.py `_parts_lost`), each beside the seconds of the House's own decision it ran after: a learner's
live part runs inside what the House's run leaves of the task's bound, so a slow House decision starves it, the auction is
then decided 'late', and PREREG-EVL-7 section 1.7 keeps a late decision out of the judged record. Receipts' times only,
invented rows only."""
from __future__ import annotations

import datetime as dt
import unittest
from unittest import mock

from league.events import learner as LR
from league.events import report as RP
from league.events import run as R
from league.tests import test_events_evl7 as T7

O1 = T7.O1


class TheLostParts(T7.WorldCase):
    def ctx(self, now: dt.datetime) -> R.Context:
        return R.Context(self.st, T7.FakeGateway(), lambda url: b"", now=lambda: now)

    def house(self, day: dt.date) -> int:
        [rid] = [r[0] for r in self.st.db.execute("SELECT id FROM receipts WHERE job=?", (f"decide-open:{day}",))]
        return rid

    def test_a_failed_and_an_expired_part_are_counted_with_the_houses_seconds(self):
        days = self.days(4)
        self.history(days[:1], 3)
        self.w.open_session(days[1], 3)
        with mock.patch.object(LR, "compute", side_effect=RuntimeError("invented")):
            LR.live_part(self.ctx(T7.et(days[1], 9, 16, 5)), T7.learner(O1), days[1], house_receipt_id=self.house(days[1]))
        self.w.open_session(days[2], 3)
        LR.live_part(self.ctx(T7.et(days[2], 9, 16, 5)), T7.learner(O1), days[2], house_receipt_id=self.house(days[2]),
                     budget=0.0)
        self.w.open_session(days[3], 3)
        rep = RP.build(self.st, days[3], now=T7.et(days[3], 21, 0))
        [o1, on] = rep["learners"]
        lost = o1["parts_lost"]
        self.assertEqual((lost["sessions"], lost["lost"]), (RP.PARTS_SESSIONS, 2), "the last ten sessions, two parts lost")
        self.assertEqual([(p["day"], p["status"]) for p in lost["parts"]],
                         [(days[1].isoformat(), "failed"), (days[2].isoformat(), "expired")])
        for p in lost["parts"]:
            house = dict(self.st.db.execute("SELECT started_at, finished_at FROM receipts WHERE job=? ORDER BY id",
                                            (f"decide-open:{p['day']}",)).fetchone())
            want = round((dt.datetime.fromisoformat(house["finished_at"].replace("Z", "+00:00")) -
                          dt.datetime.fromisoformat(house["started_at"].replace("Z", "+00:00"))).total_seconds())
            self.assertEqual(p["house_s"], want)
        self.assertEqual(on["parts_lost"]["lost"], 0)
        text = RP.render(rep)
        self.assertIn(f"live parts lost 2 of the last 10 sessions, out of the judged record (section 1.7): "
                      f"{days[1].isoformat()} failed (House run", text)
        self.assertNotIn("live parts lost 0", text, "nothing said for a learner with none lost")


if __name__ == "__main__":
    unittest.main()
