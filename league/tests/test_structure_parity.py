"""The House's structures and the replay's structures are one thing (Sept 25, 2026, the options-desk run).

`league/structures.py` (the House, over `ltcm.broker.Instrument`) delegates every rule to
`league/structure_core.py` (standard library only, uploaded beside `replay.py` into the agent's box and
imported there by `options_replay.py`). These tests pin the two to the same answers for every admitted
type and every refusal, so a strategy's structure is parsed, priced, held, valued at expiry and charged
the same way in a replay as in the House, whoever edits either file next.
"""

import math
import unittest
from decimal import Decimal

from league import structure_core as core
from league import structures

D = Decimal
V = "options-shadow"


def occ(strike, right="C", expiry="260928", root="SPY"):
    return f"{root}{expiry}{right}{int(D(str(strike)) * 1000):08d}"


def leg(strike, role, right="C", expiry="260928", ratio=None, root="SPY"):
    row = {"occ": occ(strike, right, expiry, root), "role": role}
    if ratio is not None:
        row["ratio"] = ratio
    return row


def intent(structure, legs, *, action="open", limit=0.30, quantity=1, reason="parity", **extra):
    return {"structure": structure, "action": action, "quantity": quantity, "limit_price": limit, "legs": legs, "reason": reason, **extra}


CONDOR = [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "long", "C")]
ADMITTED = {
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
REFUSED = [
    intent("debit_vertical", [leg(581, "long"), leg(580, "short")]),
    intent("credit_vertical", [leg(581, "short"), leg(580, "long")]),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short", ratio=2)]),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short", ratio=3)]),
    intent("long_butterfly", [leg(580, "long"), leg(581, "short", ratio=2), leg(583, "long")]),
    intent("long_butterfly", [leg(580, "long"), leg(581, "short"), leg(582, "long")]),
    intent("diagonal", [leg(585, "short", expiry="260928"), leg(586, "long", expiry="261002")]),
    intent("diagonal", [leg(585, "short", expiry="260928"), leg(585, "long", expiry="261002")]),
    intent("calendar", [leg(585, "long", expiry="260928"), leg(585, "short", expiry="261002")]),
    intent("calendar", [leg(585, "short", expiry="260928"), leg(586, "long", expiry="261002")]),
    intent("iron_condor", [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "short", "C")]),
    intent("iron_condor", [leg(580, "long", "P"), leg(585, "short", "P"), leg(585, "short", "C"), leg(590, "long", "C")]),
    intent("iron_butterfly", CONDOR),
    intent("iron_condor", [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "long", "C", expiry="261002")]),
    intent("long_straddle", [leg(585, "long", "C"), leg(585, "short", "P")]),
    intent("long_straddle", [leg(585, "long", "C"), leg(586, "long", "P")]),
    intent("long_strangle", [leg(585, "long", "C"), leg(585, "long", "P")]),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short", root="QQQ")]),
    intent("debit_vertical", [leg(580, "long"), leg(580, "short")]),
    intent("naked_put", [leg(580, "short", "P")]),
    intent("debit_vertical", [leg(580, "long")]),
    intent("iron_condor", CONDOR + [leg(600, "long")]),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], limit=1.00),
    intent("credit_vertical", [leg(581, "short", "P"), leg(580, "long", "P")], limit=1.00),
    intent("iron_condor", CONDOR, action="close", limit=1.00),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], limit=0.305),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], limit=-0.10),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], reason=""),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], quantity=1.5),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], quantity=0),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], action="hold"),
    intent("debit_vertical", [leg(580, "long"), leg(581, "short")], type="market"),
    intent("debit_vertical", [leg(580, "long"), {"occ": occ(581), "role": "writer"}]),
    intent("debit_vertical", [leg(580, "long"), {"occ": "SPY-581", "role": "short"}]),
    intent("debit_vertical", [leg(580, "long"), {"symbol": "SPY", "expiry": "2026-09-28", "strike": 581.0, "right": "call", "role": "short"}]),
    intent("debit_vertical", [leg(580, "long"), {"symbol": "SPY", "expiry": "2026-09-28", "strike": "581", "role": "short"}]),
    intent("debit_vertical", "legs"),
    # a leg spelled out with a malformed expiry (review of Sept 25, 2026: RejectedOrder in the House, ValueError in the box)
    intent("debit_vertical", [{"symbol": "SPY", "expiry": "2026-9-28", "strike": "580", "right": "call", "role": "long"}, leg(581, "short")]),
    {"action": "open", "quantity": 1, "limit_price": 0.3, "legs": [leg(580, "long"), leg(581, "short")], "reason": "no type"},
    {"structure": "debit_vertical", "action": "open", "quantity": 1, "legs": [leg(580, "long"), leg(581, "short")], "reason": "no limit"},
]


def outcome(parse, row):
    try:
        order = parse(row)
    except Exception as exc:  # noqa: BLE001 - any refusal, so a different KIND of error is a difference too
        return ("refused", type(exc).__name__, str(exc))
    spec = order.spec
    return ("admitted", spec.type, spec.code, order.action, order.side, order.quantity, order.limit_price, order.held_limit,
            order.max_loss_usd, order.reason, spec.collateral, spec.max_value, spec.contracts, spec.expiry, spec.underlying,
            spec.credit, spec.intent_legs())


def both(row):
    return outcome(lambda r: structures.parse(V, r), row), outcome(lambda r: core.parse(r, venue=V), row)


class Parity(unittest.TestCase):
    def test_every_admitted_type_parses_to_the_same_structure(self):
        for type_, legs in ADMITTED.items():
            for action, limit in (("open", 0.30), ("close", 0.20)):
                with self.subTest(type_, action=action):
                    house, box = both(intent(type_, legs, action=action, limit=limit))
                    self.assertEqual(house[0], "admitted", house)
                    self.assertEqual(house, box)
        self.assertEqual(set(ADMITTED), set(core.TYPES))
        # the legs spelled out rather than as OCC codes, and the verticals alias, read the same
        spelled = [{"symbol": "SPY", "expiry": "2026-09-28", "strike": "580", "right": "call", "role": "long"},
                   {"symbol": occ(581), "role": "short"}]
        house, box = both(intent("debit_vertical", spelled))
        self.assertEqual(house, box)
        self.assertEqual(house[2], "debit_vertical|+1SPY260928C00580000|-1SPY260928C00581000")
        # an expiry spelled without dashes is the contract its OCC code names, in both (never a second expiry)
        compact = [leg(580, "long"), {"symbol": "SPY", "expiry": "20260928", "strike": "581", "right": "call", "role": "short"}]
        house, box = both(intent("debit_vertical", compact))
        self.assertEqual(house, box)
        self.assertEqual(house[2], "debit_vertical|+1SPY260928C00580000|-1SPY260928C00581000")
        alias = {"spread": "debit_vertical", "side": "sell", "quantity": 2, "type": "limit", "limit_price": 0.55,
                 "legs": ADMITTED["debit_vertical"], "reason": "take profit"}
        self.assertEqual(*both(alias))

    def test_every_refusal_is_the_same_refusal(self):
        for row in REFUSED:
            with self.subTest(row=str(row)[:120]):
                house, box = both(row)
                self.assertEqual(house[0], "refused", house)
                self.assertEqual(house, box)

    def test_the_same_malformed_leg_is_the_same_error_in_both(self):
        """The review's ParseParity (Sept 25, 2026): the House read a leg with a malformed expiry as the venue's
        RejectedOrder, which `_intents` drops as a crash, where the box's core refuses it as a ValueError."""
        row = {"structure": "debit_vertical", "action": "open", "quantity": 1, "limit_price": 0.3, "reason": "x",
               "legs": [{"symbol": "SPY", "expiry": "2026-9-28", "strike": "580", "right": "call", "role": "long"},
                        {"occ": "SPY260928C00581000", "role": "short"}]}
        with self.assertRaises(ValueError):
            core.parse(row, venue=V)
        with self.assertRaises(ValueError):
            structures.parse(V, row)
        house, box = both(row)
        self.assertEqual(house, box)
        self.assertEqual(house, ("refused", "ValueError", "a long leg: alpaca: option expiry '2026-9-28' is not YYYY-MM-DD"))
        malformed = structures.Leg(structures.instrument_for(V, {"symbol": "SPY", "expiry": "2026-9-28", "strike": "580", "right": "call"}), 1)
        with self.assertRaisesRegex(ValueError, "is not YYYY-MM-DD"):  # a Leg built by hand is refused the same way
            structures.classify("debit_vertical", [malformed, structures.Leg(structures.instrument_for(V, {"occ": occ(581)}), -1)])

    def test_the_held_code_round_trips_the_same_way(self):
        for type_, legs in ADMITTED.items():
            with self.subTest(type_):
                spec = structures.parse(V, intent(type_, legs)).spec
                inst = structures.instrument(spec)
                box = core.spec_of_code(inst.market_id, venue=V)
                self.assertEqual(box.code, inst.market_id)
                self.assertEqual(structures.spec_of(inst).code, box.code)
                self.assertTrue(core.is_code(inst.market_id) and structures.is_structure(inst))
        forged = "debit_vertical|-1SPY260928C00580000|+1SPY260928C00581000"
        with self.assertRaisesRegex(ValueError, "dearer"):
            core.spec_of_code(forged)
        self.assertFalse(core.is_code("debit_vertical|+3SPY260928C00580000|-1SPY260928C00581000"))

    def test_prices_values_fees_and_venue_legs_agree(self):
        touches = {}
        for i, strike in enumerate(range(575, 596)):
            for right in ("C", "P"):
                for expiry in ("260928", "261002"):
                    mid = 0.05 + abs(math.sin(i + (right == "C") + (expiry == "261002"))) * 3
                    touches[occ(strike, right, expiry)] = (f"{mid - 0.03:.2f}", f"{mid + 0.03:.2f}")
        for type_, legs in ADMITTED.items():
            with self.subTest(type_):
                spec = structures.parse(V, intent(type_, legs)).spec
                box = core.parse(intent(type_, legs), venue=V).spec
                self.assertEqual(structures.quote(spec, touches), core.quote(box, touches))
                self.assertEqual(structures.fee_per_unit(spec), core.fee_per_unit(box))
                for action in ("open", "close"):
                    self.assertEqual(structures.mleg_legs(spec, action), core.mleg_legs(box, action))
                for held in ("0.10", "0.62", D("0.95")):
                    self.assertEqual(structures.natural_price(spec, held), core.natural_price(box, held))
                    self.assertEqual(structures.max_gain(spec, held), core.max_gain(box, held))
                for spot in (570, "580.40", D("585"), "590.25", 600):
                    if type_ in core.TWO_EXPIRIES:
                        with self.assertRaises(ValueError):
                            structures.intrinsic(spec, spot)
                        with self.assertRaises(ValueError):
                            core.intrinsic(box, spot)
                    else:
                        self.assertEqual(structures.intrinsic(spec, spot), core.intrinsic(box, spot))
        with self.assertRaisesRegex(ValueError, "floats"):
            core.intrinsic(core.parse(intent("iron_condor", CONDOR)).spec, 585.0)

    def test_the_candidates_are_one_function(self):
        rows = []
        for k in range(578, 594):
            extrinsic = 1.2 * math.exp(-abs(k - 585.40) / 2.0)
            for right in ("C", "P"):
                mid = (max(0.0, 585.40 - k) if right == "C" else max(0.0, k - 585.40)) + extrinsic
                rows.append({"occ": occ(k, right), "symbol": occ(k, right), "underlying": "SPY", "expiry": "2026-09-28", "strike": float(k),
                             "right": "call" if right == "C" else "put", "bid": round(mid - 0.02, 2), "ask": round(mid + 0.02, 2),
                             "underlying_price": 585.40, "delta": round((0.5 if right == "C" else -0.5) * math.exp(-abs(k - 585.4) / 3), 3)})
        for cap in (10, 75, 100):
            house = structures.candidates(rows, max_loss_usd=cap, today="2026-09-25", venue=V)
            box = core.candidates(rows, max_loss_usd=cap, today="2026-09-25", venue=V)
            self.assertEqual(house, box)
            self.assertTrue(house)
            for row in house:  # and every candidate parses the same way on both sides
                sent = {"structure": row["structure"], "action": "open", "quantity": 1, "limit_price": row["open_limit"],
                        "legs": row["legs"], "reason": "candidate"}
                self.assertEqual(*both(sent))


if __name__ == "__main__":
    unittest.main()
