"""Level-3 structures with defined risk, each held as ONE position (Sept 25, 2026, the options-desk run).

Pins what a structure is (every admitted type and every refusal), how it is held (one long instrument
priced at net value plus collateral, so its cost is its maximum loss), its touch, its value at expiry,
its fee and the venue's legs.
"""

import math
import unittest
from decimal import Decimal

from league import structures
from league.structures import classify, held_limit, instrument, intrinsic, is_structure, parse, quote, spec_of
from league.venues import instrument_for

D = Decimal
V = "options-shadow"


def occ(strike, right="C", expiry="260928", root="SPY"):
    return f"{root}{expiry}{right}{int(D(str(strike)) * 1000):08d}"


def leg(strike, role, right="C", expiry="260928", ratio=None, root="SPY"):
    row = {"occ": occ(strike, right, expiry, root), "role": role}
    if ratio is not None:
        row["ratio"] = ratio
    return row


def intent(structure, legs, *, action="open", limit=0.40, quantity=1, reason="test"):
    return {"structure": structure, "action": action, "quantity": quantity, "limit_price": limit, "legs": legs, "reason": reason}


CONDOR = [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "long", "C")]


class Types(unittest.TestCase):
    def test_every_admitted_type(self):
        cases = {
            "debit_vertical": [leg(580, "long"), leg(581, "short")],
            "credit_vertical": [leg(581, "short", "P"), leg(580, "long", "P")],
            "iron_condor": CONDOR,
            "iron_butterfly": [leg(580, "long", "P"), leg(585, "short", "P"), leg(585, "short", "C"), leg(590, "long", "C")],
            "long_butterfly": [leg(580, "long"), leg(581, "short", ratio=2), leg(582, "long")],
            "calendar": [leg(585, "short", expiry="260928"), leg(585, "long", expiry="261002")],
            "diagonal": [leg(586, "short", expiry="260928"), leg(585, "long", expiry="261002")],
            "long_straddle": [leg(585, "long", "C"), leg(585, "long", "P")],
            "long_strangle": [leg(590, "long", "C"), leg(580, "long", "P")],
        }
        self.assertEqual(set(cases), set(structures.TYPES))
        for type_, legs in cases.items():
            with self.subTest(type_):
                order = parse(V, intent(type_, legs, limit=0.30))
                self.assertEqual(order.spec.type, type_)
                self.assertEqual(order.side, "buy")

    def refused(self, type_, legs, pattern, **kw):
        with self.assertRaisesRegex(ValueError, pattern):
            parse(V, intent(type_, legs, **kw))

    def test_refusals(self):
        self.refused("debit_vertical", [leg(581, "long"), leg(580, "short")], "dearer")  # reversed: a credit vertical
        self.refused("credit_vertical", [leg(581, "short"), leg(580, "long")], "dearer")  # reversed: a debit vertical
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short", ratio=2)], "uncovered")  # a ratio spread
        self.refused("long_butterfly", [leg(580, "long"), leg(581, "short", ratio=2), leg(583, "long")], "equal wings")
        self.refused("diagonal", [leg(585, "short", expiry="260928"), leg(586, "long", expiry="261002")], "favourable")
        self.refused("calendar", [leg(585, "long", expiry="260928"), leg(585, "short", expiry="261002")], "expires first")
        self.refused("iron_condor", [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "short", "C")], "two long")
        self.refused("long_straddle", [leg(585, "long", "C"), leg(585, "short", "P")], "nothing sold")
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short", root="QQQ")], "one underlying")
        self.refused("debit_vertical", [leg(580, "long"), leg(580, "short")], "twice")
        self.refused("naked_put", [leg(580, "short", "P")], "not admitted")
        self.refused("debit_vertical", [leg(580, "long")], "two to four")
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short")], "never pay", limit=1.00)
        self.refused("credit_vertical", [leg(581, "short", "P"), leg(580, "long", "P")], "defined-risk", limit=1.00)
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short")], "whole cents", limit=0.305)
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short")], "reason", reason="")
        self.refused("debit_vertical", [leg(580, "long"), leg(581, "short")], "whole number", quantity=1.5)


class Held(unittest.TestCase):
    def test_a_credit_structure_is_held_at_its_collateral_less_its_credit(self):
        order = parse(V, intent("iron_condor", CONDOR, limit=0.38))
        self.assertEqual(order.spec.collateral, D(1))
        self.assertEqual((order.side, order.held_limit, order.max_loss_usd), ("buy", D("0.62"), D("62")))
        close = parse(V, intent("iron_condor", CONDOR, action="close", limit=0.10))
        self.assertEqual((close.side, close.held_limit, close.max_loss_usd), ("sell", D("0.90"), D(0)))
        # realized a share: sold at 0.90, paid 0.62 = 0.28 = the 0.38 credit less the 0.10 buy-back
        self.assertEqual(close.held_limit - order.held_limit, D("0.28"))
        self.assertEqual(structures.natural_price(order.spec, D("0.62")), D("0.38"))

    def test_a_debit_structure_is_held_at_its_debit(self):
        order = parse(V, intent("debit_vertical", [leg(580, "long"), leg(581, "short")], limit=0.45, quantity=2))
        self.assertEqual((order.held_limit, order.max_loss_usd, structures.max_gain(order.spec, D("0.45"))), (D("0.45"), D("90"), D("0.55")))
        self.assertIsNone(structures.max_gain(parse(V, intent("long_strangle", [leg(590, "long", "C"), leg(580, "long", "P")])).spec, D("0.40")))

    def test_the_instrument_round_trips_and_keys_apart(self):
        spec = parse(V, intent("iron_condor", CONDOR)).spec
        inst = instrument(spec)
        self.assertEqual((inst.asset_class, inst.symbol, inst.venue, inst.expiry, inst.multiplier), ("option", "SPY", V, "2026-09-28", D(100)))
        self.assertTrue(is_structure(inst))
        self.assertFalse(is_structure(instrument_for(V, {"occ": occ(580, "P")})))
        self.assertEqual(spec_of(inst), spec)
        self.assertEqual(inst.market_id, "iron_condor|-1SPY260928C00590000|+1SPY260928C00591000|+1SPY260928P00580000|-1SPY260928P00581000")
        other = instrument(parse(V, intent("iron_condor", [leg(579, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(592, "long", "C")])).spec)
        self.assertNotEqual(inst.key, other.key)
        # the legs in any order are one structure
        shuffled = parse(V, intent("iron_condor", list(reversed(CONDOR)))).spec
        self.assertEqual(instrument(shuffled).key, inst.key)

    def test_a_tampered_code_can_never_be_traded(self):
        inst = instrument(parse(V, intent("debit_vertical", [leg(580, "long"), leg(581, "short")])).spec)
        forged = type(inst)("option", "SPY", V, multiplier=100, expiry=inst.expiry, strike=inst.strike, right="call",
                            market_id=inst.market_id.replace("+1", "#").replace("-1", "+1").replace("#", "-1"))
        with self.assertRaisesRegex(ValueError, "dearer"):
            spec_of(forged)

    def test_the_verticals_schema_is_an_alias(self):
        order = parse(V, {"spread": "debit_vertical", "side": "sell", "quantity": 1, "type": "limit", "limit_price": 0.5,
                          "legs": [leg(580, "long"), leg(581, "short")], "reason": "take profit"})
        self.assertEqual((order.spec.type, order.action, order.side), ("debit_vertical", "close", "sell"))


class Touch(unittest.TestCase):
    def test_quote_is_what_every_leg_trades_at_at_once(self):
        spec = parse(V, intent("iron_condor", CONDOR)).spec
        touches = {occ(580, "P"): ("0.10", "0.12"), occ(581, "P"): ("0.30", "0.33"), occ(590, "C"): ("0.28", "0.31"), occ(591, "C"): ("0.09", "0.11")}
        # bid (close): 1 + 0.10 + 0.09 - 0.33 - 0.31 = 0.55 ; ask (open): 1 + 0.12 + 0.11 - 0.30 - 0.28 = 0.65 (a 0.35 credit)
        self.assertEqual(quote(spec, touches), (D("0.55"), D("0.65")))
        touches.pop(occ(591, "C"))
        self.assertEqual(quote(spec, touches), (None, None))
        fly = parse(V, intent("long_butterfly", [leg(580, "long"), leg(581, "short", ratio=2), leg(582, "long")])).spec
        self.assertEqual(quote(fly, {occ(580): ("2.00", "2.05"), occ(581): ("1.40", "1.44"), occ(582): ("0.95", "1.00")}), (D("0.07"), D("0.25")))

    def test_intrinsic(self):
        condor = parse(V, intent("iron_condor", CONDOR)).spec
        self.assertEqual([intrinsic(condor, x) for x in (585, "580.40", 575, "590.25", 600)], [D(1), D("0.40"), D(0), D("0.75"), D(0)])
        fly = parse(V, intent("long_butterfly", [leg(580, "long"), leg(581, "short", ratio=2), leg(582, "long")])).spec
        self.assertEqual([intrinsic(fly, x) for x in (579, "580.5", 581, "581.75", 583)], [D(0), D("0.5"), D(1), D("0.25"), D(0)])
        cal = parse(V, intent("calendar", [leg(585, "short", expiry="260928"), leg(585, "long", expiry="261002")])).spec
        with self.assertRaisesRegex(ValueError, "close it before"):
            intrinsic(cal, 585)
        self.assertEqual(cal.expiry, "2026-09-28")

    def test_fees_and_venue_legs(self):
        condor = parse(V, intent("iron_condor", CONDOR)).spec
        self.assertEqual(structures.fee_per_unit(condor), D("0.20"))
        opening = structures.mleg_legs(condor, "open")
        self.assertEqual({(r["symbol"], r["side"], r["position_intent"]) for r in opening},
                         {(occ(580, "P"), "buy", "buy_to_open"), (occ(581, "P"), "sell", "sell_to_open"),
                          (occ(590, "C"), "sell", "sell_to_open"), (occ(591, "C"), "buy", "buy_to_open")})
        closing = structures.mleg_legs(condor, "close")
        self.assertEqual({(r["side"], r["position_intent"]) for r in closing}, {("sell", "sell_to_close"), ("buy", "buy_to_close")})
        fly = parse(V, intent("long_butterfly", [leg(580, "long"), leg(581, "short", ratio=2), leg(582, "long")])).spec
        self.assertEqual([r["ratio_qty"] for r in structures.mleg_legs(fly, "open")], ["1", "2", "1"])
        self.assertEqual(structures.fee_per_unit(fly), D("0.20"))


class Candidates(unittest.TestCase):
    def chain(self):
        rows = []
        # SPY at 585.40; $1 strikes 580-591; calls and puts with plausible 0DTE prices
        for k in range(580, 592):
            extrinsic = 1.2 * math.exp(-abs(k - 585.40) / 2.0)  # time value decays away from the money
            call_mid = max(0.0, 585.40 - k) + extrinsic
            put_mid = max(0.0, k - 585.40) + extrinsic
            for right, mid in (("C", call_mid), ("P", put_mid)):
                rows.append({"occ": occ(k, right), "symbol": occ(k, right), "underlying": "SPY", "expiry": "2026-09-28",
                             "strike": float(k), "right": "call" if right == "C" else "put", "bid": round(mid - 0.02, 2),
                             "ask": round(mid + 0.02, 2), "underlying_price": 585.40,
                             "delta": round((1 if right == "C" else -1) * math.exp(-max(0.0, (k - 585.40) if right == "C" else (585.40 - k)) / 3) / 2, 3)})
        return rows

    def test_every_candidate_parses_fits_and_opens_at_its_touch(self):
        rows = structures.candidates(self.chain(), max_loss_usd=75, today="2026-09-25", venue=V)
        kinds = {r["structure"] for r in rows}
        self.assertTrue({"debit_vertical", "credit_vertical", "iron_condor"} <= kinds, kinds)
        for row in rows:
            order = parse(V, {"structure": row["structure"], "action": "open", "quantity": 1, "limit_price": row["open_limit"],
                              "legs": row["legs"], "reason": "candidate"})
            self.assertLessEqual(order.max_loss_usd, 75)
            self.assertAlmostEqual(float(order.max_loss_usd), row["max_loss_usd"], places=6)
            self.assertEqual(row["days_to_expiry"], 3)
        credit = [r for r in rows if r["structure"] == "credit_vertical"]
        for row in credit:  # out of the money only: the short strike on the far side of spot
            short = [leg for leg in row["legs"] if leg["role"] == "short"][0]["occ"]
            strike = int(short[-8:]) / 1000
            self.assertTrue(strike >= 585.40 if short[-9] == "C" else strike <= 585.40)
        self.assertEqual(structures.candidates(self.chain(), max_loss_usd=10, today="2026-09-25"), [r for r in structures.candidates(self.chain(), max_loss_usd=10, today="2026-09-25")])
        self.assertTrue(all(r["max_loss_usd"] <= 10 for r in structures.candidates(self.chain(), max_loss_usd=10, today="2026-09-25")))


if __name__ == "__main__":
    unittest.main()
