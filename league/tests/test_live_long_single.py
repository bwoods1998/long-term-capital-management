"""`long_single` on the live path (Sept 29, 2026): a family DECLARED two-sided, whose program's every open is one long call or
one long put. Its real eligibility (tuition, Probe, Sized) needs BOTH singles among the money table's real types; the table,
its digest and the gateway still name order types only; every real order carries its own type (`long_call` or `long_put`)
and is checked and sized by it, and a real open of any other type from it is refused (review of #425, F3; a one-sided
family is unchanged). The venue's shapes come from `live_fakes` with invented numbers."""

import copy
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.constitution import CONSTITUTION, OPTIONS_REAL_TYPES, OPTIONS_SINGLE_TYPES, digest, money_digest, options_money_problems
from league.live import money as M
from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.real import SINGLE_TYPES
    from league.tests.live_fakes import CONDOR, VERTICAL, family

REPO = Path(__file__).resolve().parents[2]
#: The money digest the grant is pinned to: `long_single` is no money rule and must not move it. R10's (Sept 29, 2026)
#: was a3e2aa7c; the incubator's row (release B, Oct 1, 2026: `options_money.incubator`) moved it to this one.
MONEY_DIGEST = "e1f151b48d9fffa6502b2d6d6a0bf47ea019e4d376430eb2acbd07ba849e9910"

#: One program, two sides: a long call first, then (once the call is held) a long put. The side rule here is a clock so the
#: numbers are by hand; a family's own rule is its mechanism's.
TWO_SIDED = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 600, "call": 603.0, "put": 597.0}
STATE = {"sent": 0}

def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_minutes"] >= ctx.params["hold"]:
            out.append({"close": p["id"], "limit": "natural", "note": "held long enough"})
    if STATE["sent"] == 0:
        STATE["sent"] = 1
        out.append({"open": "long_call", "root": "SPY", "qty": 1, "limit": "natural", "tag": "up",
                    "legs": [{"side": "long", "right": "C", "dte": 1, "strike": ctx.params["call"]}]})
    elif STATE["sent"] == 1 and ctx.positions and not ctx.orders:
        STATE["sent"] = 2
        out.append({"open": "long_put", "root": "SPY", "qty": 1, "limit": "natural", "tag": "down",
                    "legs": [{"side": "long", "right": "P", "dte": 1, "strike": ctx.params["put"]}]})
    return out
'''


def table(real_types=None):
    c = copy.deepcopy(CONSTITUTION)
    if real_types is not None:
        c["options_money"]["real_types"] = list(real_types)
    return M.Table.from_constitution(c)


def row(**kw):
    base = {"family": "two-sided", "band": "candidate", "structure": "long_single", "holdout_passed": True,
            "typical_max_loss_usd": 60.0}
    base.update(kw)
    return base


NO_PUT = ("debit_vertical", "long_butterfly", "long_call")
NO_CALL = ("debit_vertical", "long_butterfly", "long_put")


class TheDeclaredType(unittest.TestCase):
    def test_long_single_sends_the_two_singles_and_is_never_an_order_type(self):
        self.assertEqual(M.order_types("long_single"), ("long_call", "long_put"))
        self.assertEqual(M.order_types("long_single"), OPTIONS_SINGLE_TYPES)
        self.assertEqual(M.order_types("debit_vertical"), ("debit_vertical",), "every other structure is its own order type")
        self.assertEqual(M.order_types("iron_condor"), ("iron_condor",))
        for declared, types in M.DECLARED_TYPES.items():
            self.assertNotIn(declared, OPTIONS_REAL_TYPES, "a declared structure is never a type the money table names")
            self.assertTrue(set(types) <= set(OPTIONS_REAL_TYPES))

    def test_the_money_table_and_its_digest_are_unchanged(self):
        self.assertEqual(money_digest(), MONEY_DIGEST)
        self.assertEqual(CONSTITUTION["options_money"]["real_types"], ["debit_vertical", "long_butterfly", "long_call", "long_put"])
        self.assertEqual(M.Table.from_constitution().real_types, ("debit_vertical", "long_butterfly", "long_call", "long_put"))
        self.assertTrue(digest())

    def test_the_money_table_may_never_name_long_single(self):
        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["real_types"] = ["debit_vertical", "long_single"]
        self.assertTrue(any("real_types" in p for p in options_money_problems(c)))
        with self.assertRaises(ValueError):
            M.Table.from_constitution(c)

    def test_the_gateway_names_the_concrete_singles_only(self):
        from league import ci

        caps = (REPO / "gateway" / "lib" / "caps.mjs").read_text(encoding="utf-8")
        wrangler = (REPO / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
        self.assertNotIn("long_single", caps)
        self.assertNotIn("long_single", wrangler)
        self.assertEqual(ci.check_structures(), [])
        real, _ = ci.gateway_structures()
        self.assertTrue(set(OPTIONS_SINGLE_TYPES) <= set(real))


class RealEligibility(unittest.TestCase):
    """`Table.family_real` / `family_allowed`: true only while BOTH singles are real types."""

    def test_real_only_when_both_singles_are_real(self):
        self.assertTrue(table().family_real("long_single"))
        self.assertFalse(table(NO_PUT).family_real("long_single"))
        self.assertFalse(table(NO_CALL).family_real("long_single"))
        self.assertTrue(table(NO_PUT).family_real("long_call"), "a one-sided family keeps its own type's answer")
        self.assertFalse(table(NO_PUT).family_real("long_put"))
        self.assertFalse(table().family_real(""))
        self.assertFalse(table().family_real("long_twin"))
        self.assertFalse(table().family_credit("long_single"))
        self.assertTrue(table().family_credit("iron_condor"))

    def test_family_allowed_checks_every_type_the_family_sends(self):
        equity = D("5481.65")
        self.assertIsNone(table().family_allowed("long_single", equity))
        why = table(NO_PUT).family_allowed("long_single", equity)
        self.assertIn("a long_single family sends long_call and long_put orders", why)
        self.assertIn("a long_put is not one of the types real money opens", why)
        # Every other structure's answer is its type's, word for word.
        for structure in ("debit_vertical", "iron_condor", "calendar", "long_call"):
            self.assertEqual(table().family_allowed(structure, equity), table().type_allowed(structure, equity))

    def test_the_band_follows_both_singles(self):
        fwd = M.forward_stats([], 0.8)
        equity = D("5481.65")
        self.assertEqual(M.band_for(table(), row(), equity, fwd)[0], "probe")
        band, why = M.band_for(table(NO_PUT), row(), equity, fwd)
        self.assertEqual(band, "candidate")
        self.assertIn("long_single family sends long_call and long_put orders", why)
        self.assertEqual(M.band_for(table(NO_CALL), row(band="probe"), equity, fwd)[0], "candidate",
                         "a Probe whose other side stops being real loses real money")
        self.assertEqual(M.band_for(table(), row(structure="long_twin"), equity, fwd)[0], "candidate",
                         "an unknown structure is never real")

    def test_sizing_is_each_orders_own_unit(self):
        # The same family's call and put are sized apart: each by its own maximum loss with fees, under the same caps.
        t, equity, fwd = table(), D("5481.65"), M.forward_stats([], 0.8)
        call = M.plan_open(t, band="probe", tuition=False, equity=equity, unit=D("60.00"), fwd=fwd, exposure=M.Exposure())
        put = M.plan_open(t, band="probe", tuition=False, equity=equity, unit=D("130.00"), fwd=fwd,
                          exposure=M.Exposure(family_open=1, family_loss=D("240.00"), book_loss=D("240.00"),
                                              day_opened=D("240.00")))
        self.assertEqual((call.qty, put.qty), (4, 2), "274.08 of cap: 4 calls at 60, 2 puts at 130")


@unittest.skipUnless(HAVE, "numpy not installed")
class OnTheLivePath(LiveCase):
    def refusals(self):
        return [p["why"] for p, a in self.ledger.of("live.refusal")]

    def test_a_probe_sends_a_real_long_call_and_a_real_long_put_each_sized_by_its_own_unit(self):
        live = self.make([family("two-sided", TWO_SIDED, band="probe", structure="long_single", typical=60.0)])
        self.run_to(9, 33)
        self.assertIn("two-sided@1:r", live.instances)
        opens = [b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"]
        self.assertEqual([b["symbol"][-9] for b in opens], ["C", "P"], "a call, then a put, each a single-leg order")
        for body in opens:
            self.assertNotIn("legs", body)
            self.assertNotIn("long_single", str(body))
        positions = sorted(live.book.positions.values(), key=lambda p: p.type)
        self.assertEqual([p.type for p in positions], ["long_call", "long_put"], "each real position keeps its concrete type")
        self.assertTrue(all(p.type in SINGLE_TYPES for p in positions))
        # Each sized by its own maximum loss: 5% of $5,481.65 = $274.08 of premium and fees a structure.
        for pos in positions:
            unit = D(str(round(pos.entry * 100 + 2 * pos.fees / pos.qty, 2)))
            self.assertEqual(pos.qty, int(D("274.0825") // unit), pos.type)
        orders = live.book.state.rows("SELECT type FROM orders WHERE action='open' ORDER BY oid")
        self.assertEqual([o["type"] for o in orders], ["long_call", "long_put"])
        # The site's open structures show each position's own type, never the declared one.
        shown = {r["structure"] for r in live.site_inputs()["structures"] if r["agent"] == "two-sided"}
        self.assertEqual(shown, {"long_call", "long_put"})

    def test_both_sides_reach_the_forward_record_each_with_its_own_maximum_loss(self):
        live = self.make([family("two-sided", TWO_SIDED, band="probe", structure="long_single", typical=60.0,
                                 params={"hold": 2})])
        self.run_to(9, 40)
        self.assertEqual(live.book.positions, {})
        trades = sorted(live.book.closed_trades(), key=lambda t: t["max_loss"])
        self.assertEqual(len(trades), 2)
        real = sorted((r for r in self.families.forward_rows("two-sided") if r["source"] == "real"), key=lambda r: r["max_loss"])
        self.assertEqual([round(r["max_loss"], 2) for r in real], [t["max_loss"] for t in trades])
        self.assertEqual(len({r["max_loss"] for r in real}), 2, "the call's and the put's own maximum losses")
        self.assertEqual({r["source"] for r in self.families.forward_rows("two-sided")}, {"real", "shadow"})

    def test_without_both_singles_real_the_family_stays_shadow_only(self):
        live = self.make([family("two-sided", TWO_SIDED, band="probe", structure="long_single", typical=60.0)],
                         table=table(NO_PUT))
        self.run_to(9, 33)
        self.assertNotIn("two-sided@1:r", live.instances)
        self.assertIn("two-sided@1:s", live.instances)
        self.assertEqual([b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"], [])

    def tuition(self, **kw):
        return self.make([family("pre", TWO_SIDED, band="gym", structure="long_single", holdout=False, validation=True)], **kw)

    def test_tuition_when_both_singles_are_real(self):
        live = self.tuition()
        self.run_to(9, 32)
        self.assertEqual(sorted(live.instances), ["pre@1:t"])
        opens = [b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"]
        self.assertEqual([(b["symbol"][-9], b["qty"]) for b in opens], [("C", "1")], "tuition: one structure, one lot")
        rows = live.book.state.rows("SELECT type, qty, max_loss, tuition FROM orders WHERE action='open'")
        self.assertEqual([(r["type"], r["qty"], r["tuition"]) for r in rows], [("long_call", 1, 1)])
        # The put is judged by ITS OWN unit against the day's tuition left, never by the call's or a declared type's.
        [why] = [p["why"] for p, a in self.ledger.of("live.refusal")]
        self.assertRegex(why, r"^tuition: \$\d+\.\d\d would pass the day's \$200 \(\$137\.00 used\)$")
        self.assertNotEqual(why.split("$")[1].split(" ")[0], "137.00", "the put's own unit")
        self.assertEqual(self.families.forward_rows("pre"), [], "never evidence")

    def test_no_tuition_unless_both_singles_are_real(self):
        live = self.tuition(table=table(NO_CALL))
        self.run_to(9, 32)
        self.assertEqual(sorted(live.instances), [], "a long_single needs long_call and long_put real for tuition")
        self.assertEqual(self.venue.sent, [])

    def test_a_long_single_family_opens_no_other_type_for_real(self):
        # Review of #425 (F3): its declared type is enforced on real opens. A debit vertical is a real type, and a
        # debit_vertical family sends it (`test_live_step`); from a long_single family it is refused before any check.
        live = self.make([family("stray", VERTICAL, band="probe", structure="long_single", typical=60.0)])
        self.run_to(9, 33)
        self.assertIn("stray@1:r", live.instances)
        self.assertEqual(live.instances["stray@1:r"].structure, "long_single", "the instance carries the declared structure")
        self.assertEqual([b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"], [])
        self.assertIn("a long_single family opens only long_call or long_put for real, never debit_vertical", self.refusals())

    def test_a_credit_structure_from_it_is_refused_by_the_declared_type_first(self):
        live = self.make([family("stray", CONDOR, band="probe", structure="long_single", typical=60.0)])
        self.run_to(9, 33)
        self.assertIn("stray@1:r", live.instances)
        self.assertEqual([b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"], [])
        self.assertIn("a long_single family opens only long_call or long_put for real, never iron_condor", self.refusals())

    def test_each_real_order_is_still_checked_by_its_own_type(self):
        # Every other family is judged by each order's own type, as before: a debit_vertical family's condor is refused as a
        # credit structure under $2,000 of equity, never by a declared type.
        live = self.make([family("condor", CONDOR, band="probe", structure="debit_vertical", typical=60.0)])
        self.run_to(9, 33)
        self.assertEqual([b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"], [])
        self.assertTrue(any("iron_condor" in w and "credit structure" in w for w in self.refusals()), self.refusals())
        self.assertFalse(any("opens only" in w for w in self.refusals()))

    def test_a_one_sided_single_family_is_left_as_it_was(self):
        # A long_call family's program may open a long_put (the long_call starter does): each is judged by its own type.
        live = self.make([family("calls", TWO_SIDED, band="probe", structure="long_call", typical=60.0)])
        self.run_to(9, 33)
        opens = [b for b in self.venue.sent if b.get("position_intent") == "buy_to_open"]
        self.assertEqual([b["symbol"][-9] for b in opens], ["C", "P"])
        self.assertEqual(sorted(p.type for p in live.book.positions.values()), ["long_call", "long_put"])


if __name__ == "__main__":
    unittest.main()
