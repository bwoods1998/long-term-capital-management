"""THE PROBE BAND'S SHAPE, A86 (the captain's amendment of Oct 21, 2026, recorded before any Probe event): PROBE MORE,
SMALLER. Cash caps the dollars at Probe, so PREREG-EVL-3's Probe target of 5% of E with at most 6 open a program fits
about 9-11 Probe buys an auction; a Probe target of 3.5% of E with at most 8 open a program, and one share at Probe at
most 5% of E (the learning band's one-share cap), raises the Probe events a session (the count Done needs) at no more
dollars a program (8 x 3.5% = 28% of E against 6 x 5% = 30%) and no more in the worst case (8 one-share lots of at most
5% = 40% of E against 6 of up to the 10% wall = 60%). Learning (2%, 8, one share at most 5%) and Sized (10%, 8) do not
move; no judge, look, alpha or false-positive rate moves (the screen's cost allowance keeps its frozen 5% notional:
league/events/score.py, behind league/ci.py's wall).

Held here, through the REAL book, the REAL `size_entry` and the money table in force (test_events_book's harness: E
$2,000, an invented limit, no market's figure): a Probe buy sizes at 3.5% of E in whole shares; one share at Probe when
that rounds to none and one share at the limit is at most 5% of E, else skipped; at most 8 open a Probe program;
learning and Sized size as before; the rows' bounds hold the new shape as their loose end; and the money and
constitution digests moved once, with these three rows and nothing else."""

from __future__ import annotations

import copy
import json
import unittest
from decimal import Decimal as D

from league.constitution import (CONSTITUTION, EQUITY_MONEY_BOUNDS, PINNED_DIGEST, digest, equity_money_problems,
                                 money_digest)
from league.events import book as EB
from league.tests import equity_design as X
from league.tests.test_events_book import CIK, CIK2, CIK3, EventTest, earnings

#: E in test_events_book's harness, and the share of E each band's target is.
E = D("2000")


def flat(table: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in table.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


class TheRows(unittest.TestCase):
    def test_probe_is_three_and_a_half_percent_eight_open_one_share_at_most_five_percent(self):
        s = EB.settings()
        self.assertIs(s.enabled, True)
        self.assertEqual({band: s.share(band) for band in EB.LIVE_BANDS},
                         {"learning": D("0.02"), "probe": D("0.035"), "sized": D("0.10")})
        self.assertEqual({band: s.max_open(band) for band in EB.LIVE_BANDS}, {"learning": 8, "probe": 8, "sized": 8})
        self.assertEqual({band: s.one_share_cap(band) for band in EB.LIVE_BANDS},
                         {"learning": D("0.05"), "probe": D("0.05"), "sized": None})
        self.assertEqual((s.per_name, s.limit_ratio), (D("0.10"), D("1.25")), "the walls do not move")

    def test_no_more_dollars_a_program_at_probe_than_before_typical_or_worst(self):
        s = EB.settings()
        target, worst = s.max_open("probe") * s.share("probe"), s.max_open("probe") * s.one_share_cap("probe")
        self.assertEqual((target, worst), (D("0.280"), D("0.40")))
        self.assertLessEqual(target, 6 * D("0.05"), "8 x 3.5% at target is under the old 6 x 5%")
        self.assertLessEqual(worst, 6 * s.per_name, "8 one-share lots at 5% are under the old 6 at up to the 10% wall")
        # ... and the bounds hold it: no value inside them gives a Probe program more than the old shape could hold.
        top = lambda path: D(EQUITY_MONEY_BOUNDS[path][1])  # noqa: E731
        self.assertLessEqual(top("event.max_open.probe") * top("event.position_share.probe"), 6 * D("0.05"))
        self.assertLessEqual(top("event.max_open.probe") * top("event.one_share_max.probe"), 6 * D("0.10"))

    def test_the_bounds_take_the_new_shape_as_their_loose_end_and_refuse_past_it(self):
        self.assertEqual((EQUITY_MONEY_BOUNDS["event.position_share.probe"], EQUITY_MONEY_BOUNDS["event.max_open.probe"],
                          EQUITY_MONEY_BOUNDS["event.one_share_max.probe"]), (("0", "0.035"), ("0", "8"), ("0", "0.05")))
        self.assertEqual((EQUITY_MONEY_BOUNDS["event.position_share.learning"], EQUITY_MONEY_BOUNDS["event.max_open.learning"],
                          EQUITY_MONEY_BOUNDS["event.one_share_max.learning"], EQUITY_MONEY_BOUNDS["event.position_share.sized"],
                          EQUITY_MONEY_BOUNDS["event.max_open.sized"]),
                         (("0", "0.02"), ("0", "8"), ("0", "0.05"), ("0", "0.10"), ("0", "8")), "learning and Sized as before")
        self.assertEqual(equity_money_problems(), [])
        for path, value, why in ((("position_share", "probe"), "0.036", "position_share.probe = '0.036' is outside [0, 0.035]"),
                                 (("position_share", "probe"), "0.05", "position_share.probe = '0.05' is outside [0, 0.035]"),
                                 (("max_open", "probe"), 9, "max_open.probe = 9 is outside [0, 8]"),
                                 (("one_share_max", "probe"), "0.051", "one_share_max.probe = '0.051' is outside [0, 0.05]"),
                                 (("one_share_max", "probe"), "0.10", "one_share_max.probe = '0.10' is outside [0, 0.05]")):
            bad = json.loads(json.dumps(CONSTITUTION))
            bad["equity_money"]["event"][path[0]][path[1]] = value
            self.assertIn(why, " ".join(equity_money_problems(bad)), path)
            self.assertEqual(EB.settings(bad), EB.FALLBACK, f"{path}: a table outside its bounds opens nothing")
        missing = json.loads(json.dumps(CONSTITUTION))
        del missing["equity_money"]["event"]["one_share_max"]["probe"]
        self.assertIn("equity_money.event.one_share_max.probe is missing", " ".join(equity_money_problems(missing)))
        self.assertEqual(EB.settings(missing), EB.FALLBACK, "a Probe one-share rule nobody reads opens nothing")
        tighter = json.loads(json.dumps(CONSTITUTION))
        tighter["equity_money"]["event"]["position_share"]["probe"] = "0.03"
        tighter["equity_money"]["event"]["max_open"]["probe"] = 6
        tighter["equity_money"]["event"]["one_share_max"]["probe"] = "0.04"
        self.assertEqual(equity_money_problems(tighter), [], "a tightening inside the bounds is a constitution-only change")
        self.assertEqual(equity_money_problems(X.before_r2()), [], "R2's rollback (no event block) stays valid")

    def test_the_digests_moved_once_with_the_three_rows_and_nothing_else(self):
        pair = X.in_force()
        self.assertEqual((money_digest(), digest()), X.DIGESTS[pair])
        self.assertEqual(digest(), PINNED_DIGEST)
        before = X.before_a86()
        self.assertEqual((money_digest(before), digest(before)), X.DIGESTS_1019C[pair], "release 1019c's pair, exactly")
        self.assertEqual((money_digest(before)[:8], digest(before)[:8]), ("055e5313", "a8d4cbd9"))
        moved = {k for k, v in flat(CONSTITUTION).items() if flat(before).get(k, "absent") != v}
        self.assertEqual(moved, {"equity_money.event.position_share.probe", "equity_money.event.max_open.probe",
                                 "equity_money.event.one_share_max.probe"})
        self.assertEqual(set(flat(before)) - set(flat(CONSTITUTION)), set(), "no row left out")
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS[candidate], candidate)
            back = X.before_a86(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_1019C[candidate], candidate)
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_1019C.values()), set())
        off = copy.deepcopy(CONSTITUTION)
        off["equity_money"]["event"]["enabled"] = False
        self.assertEqual((money_digest(off)[:8], digest(off)[:8]), X.A86_ROLLBACK,
                         "the rollback: every event buy stopped, the rows kept")
        off_1019c = X.before_a86(off)
        self.assertEqual((money_digest(off_1019c)[:8], digest(off_1019c)[:8]), ("1b7a5c22", "50e951c9"),
                         "release 1019c's rollback pair, with A86's rows set back")


class ProbeBuys(EventTest):
    """Through the real book: an 8-K item 8.01 is EVL-8K-READ-O1's event, an earnings 8-K (item 2.02) EVL-ERN-READ-O1's;
    the default previous close $16.00 puts the limit at $20.00."""

    def test_a_probe_buy_sizes_at_three_and_a_half_percent_and_learning_and_sized_do_not_move(self):
        h = self.harness()
        earnings(h.lane, "a-1", CIK, "ACME")                                   # READ-O1, learning: $40 at $20, 2 shares
        earnings(h.lane, "o-1", CIK2, "OTHR", items=("8.01",))                 # 8K-READ-O1 at Probe: $70 at $20, 3 shares
        h.lane.band("EVL-8K-READ-O1", "probe")
        self.ready(h)
        for symbol in ("ACME", "OTHR"):
            h.symbol(symbol, last=17.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual({b["symbol"]: b["qty"] for b in h.bodies()}, {"OTHR": "3", "ACME": "2"},
                         "Probe 3.5% of E (floor($70 / $20) = 3; at the old 5%, 5), learning 2%")
        probe = [r for r in h.event_intents("buy") if r["symbol"] == "OTHR"]
        self.assertEqual([r["band"] for r in probe], ["probe"])

    def test_sized_still_sizes_at_ten_percent(self):
        h = self.harness()
        earnings(h.lane, "o-1", CIK2, "SIZD", items=("8.01",))                 # 8K-READ-O1 at Sized: $200 at $20
        h.lane.band("EVL-8K-READ-O1", "sized")
        self.ready(h)
        h.symbol("SIZD", last=17.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual({b["symbol"]: b["qty"] for b in h.bodies()}, {"SIZD": "10"}, "Sized 10% of E, the name's wall")

    def test_one_share_at_probe_when_it_is_at_most_five_percent_of_e(self):
        h = self.harness()
        earnings(h.lane, "o-1", CIK, "ONEP", prev_close=64.0, items=("8.01",))     # limit $80: 4% of E, over the $70
        earnings(h.lane, "o-2", CIK2, "OVER", prev_close=96.0, items=("8.01",))    # limit $120: 6% of E, over 5%
        earnings(h.lane, "o-3", CIK3, "WALL", prev_close=170.0, items=("8.01",))   # limit $212.50: over the 10% wall
        earnings(h.lane, "a-1", "0000000004", "LERN", prev_close=64.0)             # learning, limit $80: one share
        h.lane.band("EVL-8K-READ-O1", "probe")
        self.ready(h)
        for symbol in ("ONEP", "OVER", "WALL", "LERN"):
            h.symbol(symbol, last=50.0)
        h.tick(9, 15)
        h.tick(9, 16)
        sent = {b["symbol"]: (b["qty"], b["limit_price"]) for b in h.bodies()}
        self.assertEqual(sent, {"ONEP": ("1", "80.00"), "LERN": ("1", "80.00")},
                         "one share at Probe up to 5% of E (the target rounds to none), as at learning")
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='open'")[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-8K-READ-O1"]["skipped"], {"one_share": 1, "name_wall": 1},
                         "one share above 5% of E is skipped at Probe (the shadow keeps the event); the wall as before")

    def test_a_probe_program_holds_at_most_eight_open(self):
        h = self.harness()
        for i in range(10):
            earnings(h.lane, f"o-{i}", f"{i + 100:010d}", f"P{i:03d}", prev_close=1.0 + i / 100, items=("8.01",))
        h.lane.band("EVL-8K-READ-O1", "probe")
        self.ready(h)
        for i in range(10):
            h.symbol(f"P{i:03d}", last=1.0)
        h.tick(9, 15)
        buys = [r for r in h.event_intents("buy") if r["program"] == "EVL-8K-READ-O1"]
        self.assertEqual(len(buys), 8, "at most 8 open Probe positions a program (6 before A86)")
        self.assertEqual({r["band"] for r in buys}, {"probe"})
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='open'")[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-8K-READ-O1"]["room"], 8, summary["programs"]["EVL-8K-READ-O1"])


if __name__ == "__main__":
    unittest.main()
