"""The options money table, read and applied: bands, sizing by maximum loss, and the stops.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan `docs/goals/LTCM_OPTIONS_SWARM.md`, "Money"). The table itself
is the constitution's `options_money` (`league/constitution.py`, inside `OPTIONS_MONEY_BOUNDS`); this module is its one
reader, and nothing here holds a number of its own. Money is Decimal; the forward record's statistics are floats.

THE SIZING EQUITY `E` is the lower of the Brokerage Account's equity now and the grant's capital (`live_trading.policy`:
the lower of equity and the owner's ceiling at the last ratification), so a deposit that has not been ratified yet never
enlarges a stake. Every share in the table is a share of `E`.

BANDS (the live path owns candidate <-> probe <-> sized; the swarm owns gym <-> candidate and retirement):

- PROBE: a Candidate that passed the holdout, whose structure is one of the real types (credit types only while credit
  opens are allowed), and whose typical maximum loss (one structure, with its round-trip fees) fits the Probe's cap at
  `E`: `probe.max_loss_share x E`, or `probe.floor_usd` for one contract. Otherwise it stays a Candidate, shadow only,
  with the reason recorded. A family's structure is what it DECLARED; `long_single` (Sept 29, 2026: one program whose
  every open is a `long_call` or a `long_put`, the side chosen by its rule) is real only while BOTH are real types
  (`order_types`, `Table.family_allowed`). The table's `real_types` stay concrete types, and every real order is still
  checked by its own type (`Table.type_allowed`), at the real book and at the gateway.
- SIZED: a PROBE (never a Candidate at once) whose forward record has at least `sized.min_trades` trades with a mean
  return on maximum loss above zero and its one-sided `sized.confidence` lower bound above zero. The record
  (`one_record`) is the program version's own, one source a market day (real, else shadow, else nightly).
- A family whose REAL trades alone lose (`REAL_MIN_TRADES` or more, mean at or below zero) is held at Probe, and a
  Sized one goes back to Probe.
- A Probe or Sized family whose forward record turns negative (the swarm's `forward.negative`, or this record's own:
  20 trades and a mean below zero) loses its band: back to Candidate, its real instance on exits only.

SIZING a real open (`plan_open`), by maximum loss, never premium. `unit` is one structure's maximum loss at its limit
plus its open and close fees, from the ORDER's own type and legs (a `long_single` family's call and put are each sized
by their own unit):

- Probe: the per-structure cap is `probe.max_loss_share x E`; quantity = floor(cap / unit); a structure that fits none
  but whose unit is at most `probe.floor_usd` trades ONE (the floor). At most `probe.open_per_family` open structures,
  and the family's open maximum loss at most max(`probe.family_share x E`, `probe.floor_usd`).
- Sized: `sized.kelly_fraction` of Kelly on the LOWER bound (`stats.quarter_kelly`: fraction x lcb / variance of the
  per-trade return on maximum loss) of `E` a structure, never above `sized.max_loss_share x E`; the family at most
  `sized.family_share x E`. A Sized family whose Kelly stake is under the Probe's cap is sized under the Probe's limits
  (`probe.max_loss_share` a structure, `probe.open_per_family` open, `probe.family_share` the family): Sized limits never
  apply at a Probe-sized stake.
- Tuition: exactly one structure, only while the day's and the week's tuition maximum loss has room.
- The House live test (`league/live/house_test.py`, not a family): one structure of at most `house_test.structure_usd`,
  at most `house_test.open` held or working, its realized loss plus what is held or working at most
  `house_test.envelope_usd`, no new open once its realized loss reaches `house_test.stop_usd`, after `house_test.sessions`
  sessions or `house_test.round_trips` round trips; its own module applies them.
- The incubator (`league/live/incubator.py`, the owner's terms of Sept 29-30, 2026; `plan_incubator`): exactly
  `incubator.contracts` (one) lot of a structure whose unit is at most `incubator.max_loss_usd`; the family's held and
  working incubator maximum loss plus the new unit at most that too; at most `incubator.max_open` held or working; the
  weekly ENVELOPE (this ISO week's net realized incubator loss R, plus what is held H, plus what is working W, plus the
  new unit, at most `incubator.week_loss_usd`: once the week's net realized loss has reached it at any close, the route
  stops for the rest of the ISO week, a later gain notwithstanding); at most
  `INCUBATOR_DAY_LEGS` order legs a day and `INCUBATOR_DAY_OPEN_SHARE` of the gateway's day cap; and it keeps room in
  the book's and the day's caps for the families' Probe floors and the House live test. Its eligibility is the practice
  rule (`practice_ok`: the first look, pre-registered). Never evidence, never a band, never a promotion.
- Every open: the book's open maximum loss at most `book_share x E`; the gateway's caps (one order's maximum loss at
  most min(`gateway.order_max_loss_usd`, `gateway.order_equity_share x E`), today's opening maximum loss at most
  `gateway.day_equity_share x E`) are checked here first so the House refuses before the gateway does. Today's opening
  maximum loss counts every open that reached the venue, filled or not, exactly as the gateway reserves it (it cannot
  see fills): the cap bounds what is sent; each real instance's orders a day and the gateway's 250 opens bound churn.

THE STOPS (`Stops`), with deposits and withdrawals netted out:

- The daily stop: start-of-day equity is the previous session's last clean reading, or the first clean reading when
  the House has no earlier one (persisted, so a restart keeps it). The day's P&L = equity now - that reading - the
  change in executed funding observed with those readings; a request timestamp cannot move a flow across this base. At or below
  -`daily_stop_share` x (start-of-day equity + those flows), no new real entry that day (exits go on). The venue's
  own `last_equity` is not used: whether it already carries a deposit that landed after the close is not documented,
  and reading it wrongly would trip the stop on a deposit.
- The drawdown stop: profit P = equity - net flows since the reset - the reset's equity; M is the highest P seen on a
  SETTLED observation (one whose flows were read after it, so a deposit not yet read can never pose as profit and
  raise the peak); the peak equity is H = reset equity + flows now + M, and a drawdown (M - P) / H at or above
  `drawdown_stop_share` pauses real money (latched until the owner releases it; exits go on; the owner told).
- A breach seen on an UNSETTLED observation blocks new entries at once (provisionally) and asks for a flows read; only
  a settled observation latches it, so an unread withdrawal cannot latch the pause by itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal
from typing import Any, Mapping, Sequence

from .. import stats

ZERO = Decimal(0)
CENT = Decimal("0.01")
BANDS_REAL = ("probe", "sized")


def D(value: Any) -> Decimal:
    """A Decimal from a table string, an int or a float (its shortest repr); a bool is refused."""
    if isinstance(value, bool):
        raise ValueError("a bool is not money")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"not finite: {value!r}")
        return Decimal(repr(value))
    out = Decimal(str(value))
    if not out.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return out


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


#: A family's DECLARED structure that is not itself an order type, and the order types its orders may be (Sept 29, 2026).
#: `long_single`: one program whose every open is ONE long call or ONE long put (one leg, long), the side chosen by its
#: rule, in place of a call/put twin pair (two one-sided families). Every other declared structure is its own one order
#: type. The money table and the gateway name order types only; none of these is ever one. The live path refuses a real
#: open of any other type from a family that declared one of these (`OptionsLive._real_intent`); the Gym and the shadow
#: book judge each order by its own type, as for every family.
DECLARED_TYPES: dict[str, tuple[str, ...]] = {"long_single": ("long_call", "long_put")}


def order_types(structure: str) -> tuple[str, ...]:
    """The order types a family that declared `structure` may send: its own type, or the declared set."""
    return DECLARED_TYPES.get(structure, (structure,))


@dataclass(frozen=True)
class Table:
    """The constitution's `options_money`, parsed (Decimals for money and shares)."""

    real_types: tuple[str, ...]
    credit_types: tuple[str, ...]
    credit_min_equity: Decimal
    probe_share: Decimal
    probe_open: int
    probe_family_share: Decimal
    probe_floor: Decimal
    sized_min_trades: int
    sized_confidence: float
    kelly_fraction: float
    sized_share: Decimal
    sized_family_share: Decimal
    min_probe_real_trades: int
    min_probe_sessions: int
    book_share: Decimal
    daily_stop_share: Decimal
    drawdown_stop_share: Decimal
    tuition_day: Decimal
    tuition_week: Decimal
    calibration_day: Decimal
    house_test_structure: Decimal
    house_test_open: int
    house_test_envelope: Decimal
    house_test_stop: Decimal
    house_test_sessions: int
    house_test_round_trips: int
    incubator_max_loss: Decimal
    incubator_contracts: int
    incubator_max_open: int
    incubator_week_loss: Decimal
    incubator_min_sessions: int
    incubator_min_trades: int
    incubator_min_coverage: Decimal
    max_orders_day: int
    max_requests_minute: int
    bp_buffer: Decimal
    near_money_share: Decimal
    expiry_close_lead_minutes: int
    gateway_order_max_loss: Decimal
    gateway_order_share: Decimal
    gateway_day_share: Decimal
    gateway_max_orders: int

    @classmethod
    def from_constitution(cls, constitution: Mapping[str, Any] | None = None) -> "Table":
        """The table in force; ValueError when it is missing or outside its bounds (nothing trades on a bad table)."""
        from ..constitution import CONSTITUTION, options_money_problems

        rules = dict(constitution or CONSTITUTION)
        problems = options_money_problems(rules)
        if problems:
            raise ValueError("the options money table is refused: " + "; ".join(problems))
        t = rules["options_money"]
        probe, sized, path, gate, house = t["probe"], t["sized"], t["order_path"], t["gateway"], t["house_test"]
        inc = t["incubator"]
        return cls(
            real_types=tuple(t["real_types"]), credit_types=tuple(t["credit_types"]),
            credit_min_equity=D(t["credit_min_equity_usd"]),
            probe_share=D(probe["max_loss_share"]), probe_open=int(probe["open_per_family"]),
            probe_family_share=D(probe["family_share"]), probe_floor=D(probe["floor_usd"]),
            sized_min_trades=int(sized["min_trades"]), sized_confidence=float(D(sized["confidence"])),
            kelly_fraction=float(D(sized["kelly_fraction"])), sized_share=D(sized["max_loss_share"]),
            sized_family_share=D(sized["family_share"]), min_probe_real_trades=int(sized["min_probe_real_trades"]),
            min_probe_sessions=int(sized["min_probe_sessions"]),
            book_share=D(t["book_share"]), daily_stop_share=D(t["daily_stop_share"]),
            drawdown_stop_share=D(t["drawdown_stop_share"]),
            tuition_day=D(t["tuition"]["day_usd"]), tuition_week=D(t["tuition"]["week_usd"]),
            calibration_day=D(t["calibration"]["day_usd"]),
            house_test_structure=D(house["structure_usd"]), house_test_open=int(house["open"]),
            house_test_envelope=D(house["envelope_usd"]), house_test_stop=D(house["stop_usd"]),
            house_test_sessions=int(house["sessions"]), house_test_round_trips=int(house["round_trips"]),
            incubator_max_loss=D(inc["max_loss_usd"]), incubator_contracts=int(inc["contracts"]),
            incubator_max_open=int(inc["max_open"]), incubator_week_loss=D(inc["week_loss_usd"]),
            incubator_min_sessions=int(inc["min_sessions"]), incubator_min_trades=int(inc["min_trades"]),
            incubator_min_coverage=D(inc["min_coverage"]),
            max_orders_day=int(path["max_orders_day"]), max_requests_minute=int(path["max_requests_minute"]),
            bp_buffer=D(path["bp_buffer"]), near_money_share=D(path["near_money_share"]),
            expiry_close_lead_minutes=int(path["expiry_close_lead_minutes"]),
            gateway_order_max_loss=D(gate["order_max_loss_usd"]), gateway_order_share=D(gate["order_equity_share"]),
            gateway_day_share=D(gate["day_equity_share"]), gateway_max_orders=int(gate["max_day_orders"]),
        )

    def credit_allowed(self, equity: Decimal) -> bool:
        """Credit structures on real money: while the account reads `credit_min_equity`. Equity alone, as the gateway
        judges it (the plan's "or a real credit order is accepted" can only happen at that equity, since the gateway
        refuses a credit open under it; a latch kept past a fall under it would only send refused orders)."""
        return equity >= self.credit_min_equity

    def type_allowed(self, type_: str, equity: Decimal) -> str | None:
        """Why real money may not open `type_` now, or None."""
        if type_ in self.credit_types and type_ not in self.real_types:
            return (f"a {type_} is a credit structure: credit opens are not among the types real money opens "
                    f"({', '.join(self.real_types)}) until a deposit takes equity to ${self.credit_min_equity} and the "
                    "grant is ratified again (limited margin under it); shadow only until then")
        if type_ not in self.real_types:
            return (f"a {type_} is not one of the types real money opens ({', '.join(self.real_types)}): "
                    "it closes in more than one order at the venue; shadow only until a paper round trip proves it")
        if type_ in self.credit_types and not self.credit_allowed(equity):
            return (f"a {type_} is a credit structure: real credit opens wait until the account reads "
                    f"${self.credit_min_equity} of equity (it reads ${cents(equity)}; debit structures only until then)")
        return None

    def family_real(self, structure: str) -> bool:
        """Whether a family that declared `structure` trades real types only: every order type it may send
        (`order_types`) is one of `real_types`. `long_single` is real only while both `long_call` and `long_put` are."""
        return bool(structure) and all(t in self.real_types for t in order_types(structure))

    def family_credit(self, structure: str) -> bool:
        """Whether any order type a family that declared `structure` may send is a credit type."""
        return any(t in self.credit_types for t in order_types(structure))

    def family_allowed(self, structure: str, equity: Decimal) -> str | None:
        """Why real money may not trade a family that declared `structure` now, or None: `type_allowed` of EVERY order type
        it may send (a declared type's own; each of a `long_single`'s two). Its orders are still checked one by one."""
        types = order_types(structure)
        for type_ in types:
            why = self.type_allowed(type_, equity)
            if why:
                return why if types == (structure,) else f"a {structure} family sends {' and '.join(types)} orders: {why}"
        return None


# --------------------------------------------------------------------------------------------- the forward record
#: The real subset of a forward record read on its own once it has this many trades: losing, it holds the family at
#: Probe (never Sized) and takes a Sized family back to Probe.
REAL_MIN_TRADES = 10
#: Per market day, the one source counted: real fills first, then the live shadow book, then the nightly replay.
SOURCE_ORDER = ("real", "shadow", "nightly")


@dataclass(frozen=True)
class Forward:
    """A family's forward record, as returns on maximum loss (r = pnl / max_loss, one per trade)."""

    n: int
    mean: float | None
    sd: float | None
    lcb: float | None
    pnl: float
    negative: bool
    real_n: int = 0
    real_mean: float | None = None

    @property
    def variance(self) -> float | None:
        return None if self.sd is None else self.sd * self.sd

    @property
    def real_bad(self) -> bool:
        """The real fills alone lose: at least `REAL_MIN_TRADES` real trades with a mean return at or below zero."""
        return self.real_n >= REAL_MIN_TRADES and self.real_mean is not None and self.real_mean <= 0


def one_record(rows: Sequence[Mapping[str, Any]], *, version: Any = None) -> list[Mapping[str, Any]]:
    """The forward record the money table reads: the program version's own (a new version starts its own record;
    rows written without a version count only while no row carries one), and each market day counted ONCE, from one
    source, preferring REAL fills, then the live SHADOW book, then the NIGHTLY replay. The three trade the same
    program's decisions on the same day, so counting them all counts one decision two or three times; real first, so
    real losses are never hidden behind a winning shadow day. The swarm's `league/swarm/evidence.py` reads the same
    record by the same rule (the review of #362, Sept 26, 2026: one rule for both sides). Returns are per dollar of
    maximum loss, scale-free across the shadow's notional and the real stake."""
    rows = list(rows)
    if version is not None and any(r.get("version") is not None for r in rows):
        rows = [r for r in rows if r.get("version") is not None and str(r.get("version")) == str(version)]
    by_day: dict[str, dict[str, list]] = {}
    for row in rows:
        by_day.setdefault(str(row.get("day") or ""), {}).setdefault(str(row.get("source") or ""), []).append(row)
    out: list[Mapping[str, Any]] = []
    for day in sorted(by_day):
        sources = by_day[day]
        for source in SOURCE_ORDER + ("",):
            if sources.get(source):
                out.extend(sources[source])
                break
    return out


def _returns(rows: Sequence[Mapping[str, Any]]) -> tuple[list[float], float]:
    returns, pnl = [], 0.0
    for row in rows:
        try:
            p, m = float(row["pnl"]), float(row.get("max_loss") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(p):
            continue
        pnl += p
        if math.isfinite(m) and m > 0:
            returns.append(p / m)
    return returns, pnl


def forward_stats(rows: Sequence[Mapping[str, Any]], confidence: float, *, negative: bool | None = None,
                  version: Any = None) -> Forward:
    """The forward record's statistics (`one_record`: the version's own, one source a day). A trade without a positive
    maximum loss is not a return and is left out of the returns (it still counts in the P&L). Negative: the swarm's own
    verdict OR this record's (at least 20 trades and a mean return below zero)."""
    record = one_record(rows, version=version)
    returns, pnl = _returns(record)
    n = len(returns)
    bounds = stats.mean_bounds(returns, 1.0 - confidence) if n >= 2 else None
    mean = bounds["mean"] if bounds else (returns[0] if n == 1 else None)
    real, _ = _returns([r for r in record if str(r.get("source") or "") == "real"])
    own_negative = n >= 20 and mean is not None and mean < 0
    return Forward(n=n, mean=mean, sd=bounds["sd"] if bounds else None, lcb=bounds["lcb"] if bounds else None, pnl=pnl,
                   negative=bool(negative) or own_negative, real_n=len(real),
                   real_mean=(sum(real) / len(real)) if real else None)


# --------------------------------------------------------------------------------------------------------- bands
def sized_ok(table: Table, fwd: Forward) -> bool:
    return (fwd.n >= table.sized_min_trades and fwd.mean is not None and fwd.mean > 0 and fwd.lcb is not None
            and fwd.lcb > 0)


def probe_cap(table: Table, equity: Decimal) -> Decimal:
    """What one Probe structure may lose (the floor is separate: `fits_probe`)."""
    return table.probe_share * max(ZERO, equity)


def fits_probe(table: Table, equity: Decimal, unit: Decimal) -> bool:
    """Whether a structure whose maximum loss with fees is `unit` can be a Probe's (the share, or the floor's one contract)."""
    return unit > 0 and (unit <= probe_cap(table, equity) or unit <= table.probe_floor)


def band_for(table: Table, row: Mapping[str, Any], equity: Decimal, fwd: Forward, *, probe_sessions: int = 0) -> tuple[str, str]:
    """The money band a live family should be in now, and why: "candidate" (shadow only), "probe" or "sized". Only for
    a family the swarm has at candidate, probe or sized. `probe_sessions`: whole sessions it has spent at Probe."""
    band = str(row.get("band") or "")
    if band not in ("candidate", "probe", "sized"):
        return band, "not a Candidate"
    if not row.get("holdout_passed"):
        return "candidate", "has not passed the holdout"
    if fwd.negative:
        return "candidate", f"its forward record turned negative ({fwd.n} trades, ${fwd.pnl:.2f})"
    why = table.family_allowed(str(row.get("structure") or ""), equity)
    if why:
        return "candidate", why
    typical = row.get("typical_max_loss_usd")
    try:
        unit = D(typical) if typical is not None else None
    except (ValueError, ArithmeticError):
        unit = None
    if (unit is None or unit <= 0) and band == "candidate":
        # The plan's Probe needs its typical maximum loss to fit the cap: unknown, it cannot be shown to fit.
        return "candidate", "its typical maximum loss is unknown (no structure in the banded version's validation run)"
    if unit is not None and unit > 0 and not fits_probe(table, equity, unit):
        return "candidate", (f"its typical structure risks ${cents(unit)}, over the Probe's cap of "
                             f"${cents(probe_cap(table, equity))} ({table.probe_share:%} of ${cents(equity)}) and the "
                             f"one-contract floor of ${table.probe_floor}")
    if band in ("probe", "sized") and fwd.real_bad:
        return "probe", (f"its {fwd.real_n} real trades lose (mean {fwd.real_mean:.4f} a dollar of maximum loss): held at "
                         "Probe")
    probe_done = band == "sized" or (fwd.real_n >= table.min_probe_real_trades and probe_sessions >= table.min_probe_sessions)
    if band in ("probe", "sized") and sized_ok(table, fwd) and probe_done:
        return "sized", (f"a forward record of {fwd.n} trades, mean {fwd.mean:.4f} a dollar of maximum loss, "
                         f"{table.sized_confidence:.0%} lower bound {fwd.lcb:.4f}, after {fwd.real_n} real Probe trades")
    if band == "candidate":
        return "probe", "passed the holdout and trades a real type that fits the Probe's cap (Sized only from Probe)"
    return "probe", "passed the holdout and trades a real type that fits the Probe's cap"


# ------------------------------------------------------------------------------------------------------- sizing
@dataclass(frozen=True)
class Exposure:
    """What is already at risk (dollars of maximum loss, reserved working opens included)."""

    family_open: int = 0             # the family's open real structures and working real opens
    family_loss: Decimal = ZERO      # their maximum loss
    book_loss: Decimal = ZERO        # every real structure's and working open's maximum loss
    day_opened: Decimal = ZERO       # today's opening maximum loss sent (the gateway's day cap counts it)
    tuition_day: Decimal = ZERO      # tuition maximum loss opened today / this week
    tuition_week: Decimal = ZERO


@dataclass(frozen=True)
class Plan:
    qty: int
    cap: Decimal                     # the per-structure cap it was sized against
    reason: str                      # why this size (or why none)


def kelly_cap(table: Table, equity: Decimal, fwd: Forward | None) -> Decimal:
    """`kelly_fraction` of Kelly on the forward record's LOWER bound, as dollars of maximum loss a structure, never
    above `sized.max_loss_share` (0 when the record cannot size anything)."""
    if fwd is None or fwd.lcb is None or not fwd.variance:
        return ZERO
    share = D(stats.quarter_kelly(fwd.lcb, fwd.variance, fraction=table.kelly_fraction, cap=float(table.sized_share)))
    return min(share, table.sized_share) * max(ZERO, equity)


def sizing_band(table: Table, band: str, equity: Decimal, fwd: Forward | None) -> str:
    """The limits a real open is sized under: a Sized family whose Kelly stake is under the Probe's cap keeps the
    Probe's limits (its share a structure, its open count, its family share): the Sized family and count limits never
    apply at a Probe-sized stake (the review of #362, C3)."""
    if band == "sized" and kelly_cap(table, equity, fwd) < probe_cap(table, equity):
        return "probe"
    return band


def structure_cap(table: Table, band: str, equity: Decimal, fwd: Forward | None) -> Decimal:
    if sizing_band(table, band, equity, fwd) == "sized":
        return kelly_cap(table, equity, fwd)
    return probe_cap(table, equity)


def family_cap(table: Table, band: str, equity: Decimal) -> Decimal:
    if band == "sized":
        return table.sized_family_share * equity
    return max(table.probe_family_share * equity, table.probe_floor)


def plan_open(table: Table, *, band: str, tuition: bool, equity: Decimal, unit: Decimal, fwd: Forward | None,
              exposure: Exposure) -> Plan:
    """How many of a structure whose maximum loss with fees is `unit` dollars a real open may send (qty 0: none, and
    why). `band` is the family's money band; `tuition` a validation-passing family's 1-lot fill measurement."""
    if equity <= 0:
        return Plan(0, ZERO, "no sizing equity")
    if unit <= 0:
        return Plan(0, ZERO, "the structure's maximum loss is not positive")
    if tuition:
        cap = unit
        if exposure.tuition_day + unit > table.tuition_day:
            return Plan(0, cap, f"tuition: ${cents(unit)} would pass the day's ${table.tuition_day} "
                                f"(${cents(exposure.tuition_day)} used)")
        if exposure.tuition_week + unit > table.tuition_week:
            return Plan(0, cap, f"tuition: ${cents(unit)} would pass the week's ${table.tuition_week} "
                                f"(${cents(exposure.tuition_week)} used)")
        qty, why = 1, "tuition: one structure, to measure the venue's fills"
    elif band in BANDS_REAL:
        band = sizing_band(table, band, equity, fwd)
        cap = structure_cap(table, band, equity, fwd)
        qty = int((cap / unit).to_integral_value(rounding=ROUND_FLOOR))
        why = f"{band}: ${cents(cap)} of maximum loss a structure"
        if qty < 1 and band in BANDS_REAL and unit <= table.probe_floor:
            qty, why = 1, f"{band}: one contract under the ${table.probe_floor} floor"
        if qty < 1:
            return Plan(0, cap, f"{band}: one structure risks ${cents(unit)}, over its cap of ${cents(cap)} and the "
                                f"${table.probe_floor} floor")
        if band == "probe":
            room = table.probe_open - exposure.family_open
            if room < 1:
                return Plan(0, cap, f"probe: {exposure.family_open} structures open, the most a Probe family holds is {table.probe_open}")
        fam = family_cap(table, band, equity)
        room_loss = fam - exposure.family_loss
        qty = min(qty, int((room_loss / unit).to_integral_value(rounding=ROUND_FLOOR)) if room_loss > 0 else 0)
        if qty < 1:
            return Plan(0, cap, f"{band}: the family's open maximum loss ${cents(exposure.family_loss)} leaves no room under "
                                f"its ${cents(fam)}")
    else:
        return Plan(0, ZERO, f"band {band or '?'} trades shadow only")
    book = table.book_share * equity
    room = book - exposure.book_loss
    qty = min(qty, int((room / unit).to_integral_value(rounding=ROUND_FLOOR)) if room > 0 else 0)
    if qty < 1:
        return Plan(0, cap, f"the book's open maximum loss ${cents(exposure.book_loss)} leaves no room under "
                            f"{table.book_share:%} of equity (${cents(book)})")
    order_cap = min(table.gateway_order_max_loss, table.gateway_order_share * equity)
    qty = min(qty, int((order_cap / unit).to_integral_value(rounding=ROUND_FLOOR)) if order_cap > 0 else 0)
    if qty < 1:
        return Plan(0, cap, f"the gateway's per-order cap ${cents(order_cap)} is under one structure's ${cents(unit)}")
    day_cap = table.gateway_day_share * equity
    room = day_cap - exposure.day_opened
    qty = min(qty, int((room / unit).to_integral_value(rounding=ROUND_FLOOR)) if room > 0 else 0)
    if qty < 1:
        return Plan(0, cap, f"today's opening maximum loss ${cents(exposure.day_opened)} leaves no room under the "
                            f"gateway's day cap ${cents(day_cap)}")
    return Plan(qty, cap, why)


# ---------------------------------------------------------------------------------------------------- the incubator
#: The incubator's own day limits (code constants, not table rows: they only tighten what the table allows): at most this
#: many order legs and cancels of its own a day, and at most this share of the gateway's day cap opened by it a day.
INCUBATOR_DAY_LEGS = 40
INCUBATOR_DAY_OPEN_SHARE = Decimal("0.25")


@dataclass(frozen=True)
class IncubatorTally:
    """The incubator's own numbers, read from the live state's rows (`RealBook.incubator_tally`): dollars of maximum loss
    and realized loss, with fees. `realized_loss` R is this ISO week's net realized loss (floored at zero);
    `week_peak_loss` the most this week's net realized loss has been at any close so far (the running net over the week's
    closes in their order, floored at zero: the weekly stop's LATCH, so a later gain in the same week never re-opens the
    route); `held` H and `working` W every held position's and working open's possible loss; `family_held` and
    `family_working` the same for one family; `open_n` the structures held or working; `legs_today` today's order legs
    and cancels; `opened_today` today's dispatched opens' maximum loss."""

    realized_loss: Decimal = ZERO
    held: Decimal = ZERO
    working: Decimal = ZERO
    family_held: Decimal = ZERO
    family_working: Decimal = ZERO
    open_n: int = 0
    legs_today: int = 0
    opened_today: Decimal = ZERO
    week_peak_loss: Decimal = ZERO

    @property
    def possible(self) -> Decimal:
        """R + H + W: what the week could already have lost."""
        return self.realized_loss + self.held + self.working

    @property
    def week_loss_seen(self) -> Decimal:
        """The weekly stop's reading: the most the week's net realized loss has been (never less than R now)."""
        return max(self.realized_loss, self.week_peak_loss)

    def as_dict(self) -> dict[str, Any]:
        return {"realized_loss_usd": str(cents(self.realized_loss)), "week_peak_loss_usd": str(cents(self.week_peak_loss)),
                "held_usd": str(cents(self.held)),
                "working_usd": str(cents(self.working)), "possible_usd": str(cents(self.possible)), "open": self.open_n,
                "legs_today": self.legs_today, "opened_today_usd": str(cents(self.opened_today))}


def _positive(value: Any) -> bool:
    """Above $0 (to the millionth: a float sum's noise is not a profit)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(x) and round(x, 6) > 0


def practice_ok(table: Table, record: Mapping[str, Any] | None, *, exit_check: bool = False) -> tuple[bool, str]:
    """THE PRACTICE RULE (pre-registered; `league/live/incubator.py`): whether a practice cohort's record (`observe.
    practice_record`) is positive live practice, and why. P1 at least `incubator.min_sessions` completed sessions; P2 at
    least `incubator.min_trades` program-closed trades; P3 decision coverage at least `incubator.min_coverage`; P4 program
    P&L above $0; P5 all closes' P&L above $0; P6 all closes' P&L plus the open mark above $0. `exit_check`: the re-check
    of a cohort that passed its first look, on its extended record (P3-P6 only: it can only refuse)."""
    if not isinstance(record, Mapping):
        return False, "no practice record"
    if not exit_check:
        sessions = record.get("sessions")
        if sessions is None:
            return False, "P1: its practice record began before its cohort (ineligible)"
        if int(sessions) < table.incubator_min_sessions:
            return False, f"P1: {int(sessions)} completed sessions, under {table.incubator_min_sessions}"
        closes = int(record.get("closes_program") or 0)
        if closes < table.incubator_min_trades:
            return False, f"P2: {closes} program-closed trades, under {table.incubator_min_trades}"
    due, made = record.get("decisions_due"), record.get("decisions_made")
    coverage = record.get("coverage")
    if isinstance(due, int) and isinstance(made, int) and not isinstance(due, bool) and due > 0:
        covered = D(made) >= table.incubator_min_coverage * D(due)
        shown = f"{made}/{due}"
    elif coverage is not None:
        try:
            covered = D(coverage) >= table.incubator_min_coverage
        except (ValueError, ArithmeticError):
            covered = False
        shown = str(coverage)
    else:
        return False, "P3: no decision was due (coverage unknown)"
    if not covered:
        return False, f"P3: decision coverage {shown}, under {table.incubator_min_coverage}"
    if not _positive(record.get("pnl_program")):
        return False, f"P4: program-closed P&L {record.get('pnl_program')} is not above $0"
    if not _positive(record.get("pnl_all")):
        return False, f"P5: all closes' P&L {record.get('pnl_all')} is not above $0"
    try:
        marked = float(record.get("pnl_all") or 0.0) + float(record.get("open_mark") or 0.0)
    except (TypeError, ValueError):
        marked = float("nan")
    if not _positive(marked):
        return False, f"P6: all closes' P&L with the open mark {round(marked, 2)} is not above $0"
    return True, "positive live practice (P1-P6)" if not exit_check else "still positive (P3-P6)"


def plan_incubator(table: Table, *, unit: Decimal, equity: Decimal | None, tally: IncubatorTally, exposure: Exposure,
                   room: Decimal) -> Plan:
    """One lot of an incubator open whose maximum loss with its open and close fees is `unit`, or none and why: the first
    of these that fails refuses (the module docstring): (1) equity and unit, (2) the unit cap, (3) the family's held and
    working, (4) the open count, (5) the weekly envelope, (6) its day's legs, (7) its day's dispatch, (8) the book's cap
    less `room`, (9) the gateway's per-order cap, (10) the gateway's day cap less `room`. `room` is what it leaves the
    families' Probe floors and the House live test."""
    cap = table.incubator_max_loss
    if equity is None or equity <= 0:
        return Plan(0, cap, "incubator: no sizing equity")
    if unit <= 0:
        return Plan(0, cap, "incubator: the structure's maximum loss is not positive")
    if unit > cap:
        return Plan(0, cap, f"incubator: one lot risks ${cents(unit)} with fees, over its ${cap} cap")
    fam = tally.family_held + tally.family_working
    if fam + unit > cap:
        return Plan(0, cap, f"incubator: the family already holds or works ${cents(fam)}; with this ${cents(unit)} it "
                            f"would pass its ${cap}")
    if tally.open_n >= table.incubator_max_open:
        return Plan(0, cap, f"incubator: {tally.open_n} structures held or working, the most it holds is "
                            f"{table.incubator_max_open}")
    if tally.week_loss_seen >= table.incubator_week_loss:
        # THE LATCH: once the week's net realized loss has reached the row at any close, the route stays stopped for the
        # rest of the ISO week, whatever a later gain does to R (the owner's "stops for the week").
        return Plan(0, cap, f"incubator: stopped for the week (its net realized loss reached "
                            f"${cents(tally.week_loss_seen)} this week, at or over ${table.incubator_week_loss}; now "
                            f"${cents(tally.realized_loss)})")
    if tally.possible + unit > table.incubator_week_loss:
        return Plan(0, cap, f"incubator: the week's envelope: ${cents(tally.possible)} could already be lost (realized "
                            f"${cents(tally.realized_loss)}, held ${cents(tally.held)}, working ${cents(tally.working)}) "
                            f"and this risks ${cents(unit)}, over ${table.incubator_week_loss}")
    if tally.legs_today >= INCUBATOR_DAY_LEGS:
        return Plan(0, cap, f"incubator: {tally.legs_today} order legs today, its most is {INCUBATOR_DAY_LEGS}")
    day_cap = table.gateway_day_share * equity
    own = INCUBATOR_DAY_OPEN_SHARE * day_cap
    if tally.opened_today + unit > own:
        return Plan(0, cap, f"incubator: ${cents(tally.opened_today)} opened today; with this ${cents(unit)} it would "
                            f"pass its ${cents(own)} ({INCUBATOR_DAY_OPEN_SHARE:%} of the day cap)")
    book = table.book_share * equity
    if exposure.book_loss + unit + room > book:
        return Plan(0, cap, f"the book's cap: ${cents(exposure.book_loss)} of ${cents(book)} open maximum loss, and "
                            f"${cents(room)} is kept for the families' Probe floors and the House live test")
    order_cap = min(table.gateway_order_max_loss, table.gateway_order_share * equity)
    if unit > order_cap:
        return Plan(0, cap, f"the gateway's per-order cap ${cents(order_cap)} is under one structure's ${cents(unit)}")
    if exposure.day_opened + unit + room > day_cap:
        return Plan(0, cap, f"the gateway's day cap: ${cents(exposure.day_opened)} of ${cents(day_cap)} opened today, and "
                            f"${cents(room)} is kept for the families' Probe floors and the House live test")
    return Plan(table.incubator_contracts, cap, "incubator: one lot (never evidence)")


# -------------------------------------------------------------------------------------------------------- stops
@dataclass
class Stops:
    """The daily and drawdown stops, flows netted (the module docstring). Its state is a plain dict the live path
    persists (`as_state` / `from_state`); `observe` is called with each reading of the account."""

    start_equity: Decimal
    peak_profit: Decimal = ZERO          # M: the highest settled profit since the reset
    day: str = ""                        # the New York session day the daily figures are for
    day_base: Decimal | None = None      # start-of-day equity + the day's net flows, at the last reading
    sod_equity: Decimal | None = None    # previous clean session close, or first reading without an earlier baseline
    sod_at: float | None = None
    sod_flows: Decimal | None = None     # executed flow total observed with the day's baseline, not its request time
    day_pnl: Decimal | None = None
    daily_tripped: bool = False
    daily_why: str = ""
    drawdown: Decimal | None = None
    drawdown_tripped: bool = False
    drawdown_why: str = ""
    drawdown_at: float | None = None
    provisional: str = ""                # a breach seen on an unsettled observation (blocks entries; latches nothing)
    last_profit: Decimal | None = None   # the profit at the latest settled reading (where a release restarts the peak)
    last_reading: list | None = None     # [time, equity, day] of the latest reading (the next session's base)
    last_reading_flows: Decimal | None = None
    flow_rows: tuple | None = None       # executed funding snapshot previously observed
    flow_transition_at: float | None = None  # new snapshot still needs equity bracketed by matching funding reads
    tainted: bool = False                # a funding read showed a pending flow: readings before the next clean read drop
    pending: list = field(default_factory=list)  # [(time, equity, last_equity, day)]: flows not read after them yet

    def as_state(self) -> dict[str, Any]:
        return {"start_equity": str(self.start_equity), "peak_profit": str(self.peak_profit), "day": self.day,
                "day_base": None if self.day_base is None else str(self.day_base),
                "day_pnl": None if self.day_pnl is None else str(self.day_pnl), "daily_tripped": self.daily_tripped,
                "sod_equity": None if self.sod_equity is None else str(self.sod_equity), "sod_at": self.sod_at,
                "sod_flows": None if self.sod_flows is None else str(self.sod_flows),
                "last_reading_flows": None if self.last_reading_flows is None else str(self.last_reading_flows),
                "flow_rows": None if self.flow_rows is None else [[t, str(a)] for t, a in self.flow_rows],
                "flow_transition_at": self.flow_transition_at,
                "daily_why": self.daily_why, "drawdown": None if self.drawdown is None else str(self.drawdown),
                "drawdown_tripped": self.drawdown_tripped, "drawdown_why": self.drawdown_why,
                "drawdown_at": self.drawdown_at, "provisional": self.provisional,
                "last_profit": None if self.last_profit is None else str(self.last_profit), "tainted": self.tainted,
                "last_reading": None if self.last_reading is None else [self.last_reading[0], str(self.last_reading[1]), self.last_reading[2]],
                "pending": [[t, str(e), str(last), d] for t, e, last, d in self.pending[-50:]]}

    @classmethod
    def from_state(cls, row: Mapping[str, Any] | None, start_equity: Decimal) -> "Stops":
        if not row:
            return cls(start_equity=start_equity)
        out = cls(start_equity=D(row.get("start_equity") or start_equity))
        out.peak_profit = D(row.get("peak_profit") or 0)
        out.day = str(row.get("day") or "")
        out.day_base = None if row.get("day_base") is None else D(row["day_base"])
        out.day_pnl = None if row.get("day_pnl") is None else D(row["day_pnl"])
        out.sod_equity = None if row.get("sod_equity") is None else D(row["sod_equity"])
        out.sod_at = row.get("sod_at")
        out.sod_flows = None if row.get("sod_flows") is None else D(row["sod_flows"])
        out.last_reading_flows = None if row.get("last_reading_flows") is None else D(row["last_reading_flows"])
        out.flow_rows = None if row.get("flow_rows") is None else tuple((float(t), D(a)) for t, a in row["flow_rows"])
        out.flow_transition_at = row.get("flow_transition_at")
        out.daily_tripped = bool(row.get("daily_tripped"))
        out.daily_why = str(row.get("daily_why") or "")
        out.drawdown = None if row.get("drawdown") is None else D(row["drawdown"])
        out.drawdown_tripped = bool(row.get("drawdown_tripped"))
        out.drawdown_why = str(row.get("drawdown_why") or "")
        out.drawdown_at = row.get("drawdown_at")
        out.provisional = str(row.get("provisional") or "")
        out.last_profit = None if row.get("last_profit") is None else D(row["last_profit"])
        out.tainted = bool(row.get("tainted"))
        last = row.get("last_reading")
        out.last_reading = None if not last else [float(last[0]), D(last[1]), str(last[2])]
        out.pending = [(float(t), D(e), D(last), str(d)) for t, e, last, d in row.get("pending") or []]
        return out

    def blocked(self) -> str | None:
        """Why no new real entry may go now, or None."""
        if self.drawdown_tripped:
            return f"the drawdown stop: {self.drawdown_why} (real money paused until the owner releases it)"
        if self.daily_tripped:
            return f"the daily stop: {self.daily_why} (no new entry today)"
        if self.provisional:
            if self.flow_transition_at is not None:
                return f"funding transition not verified: {self.provisional}"
            return f"a stop's line is crossed on a reading whose deposits are not read yet: {self.provisional}"
        return None

    def observe(self, table: Table, *, at: float, day: str, equity: Decimal, last_equity: Decimal,
                flows: "FlowBook | None", funding_confirmed: bool = False) -> None:
        """One reading of the account at `at` (epoch seconds) on New York session day `day`, with the account's
        `last_equity` (its equity at the previous session's close). `flows` is the funding history as last read
        (None: never read)."""
        if day != self.day:
            self.day, self.daily_tripped, self.daily_why, self.day_base, self.day_pnl = day, False, "", None, None
            # The day's base is the previous session's last reading (flows since then are netted), so losses before a
            # House that started late in the session are still the day's; with no previous reading, this one.
            if self.last_reading is not None and self.last_reading[2] != day and self.last_reading_flows is not None:
                self.sod_at, self.sod_equity = float(self.last_reading[0]), D(self.last_reading[1])
                self.sod_flows = self.last_reading_flows
            else:
                self.sod_equity, self.sod_at = equity, at
                self.sod_flows = flows.net_until(at) if flows is not None else None
        self.pending.append((at, equity, last_equity, day))
        del self.pending[:-50]
        self.provisional = ""
        if flows is None:
            self.provisional = "the account's funding history has not been read"
            return
        changed = self.flow_rows != flows.rows if self.flow_rows is not None else bool(flows.rows)
        self.flow_rows = flows.rows
        if changed:
            # Funding can execute after account() but before activities() returns, with the old request timestamp.
            # No earlier equity reading can be permanently judged against this newly observed funding snapshot.
            self.pending = [(at, equity, last_equity, day)]
            self.flow_transition_at = flows.read_at
            self.tainted = True
        if self.flow_transition_at is not None:
            bracketed = (not changed and self.flow_transition_at < at <= flows.read_at)
            if not funding_confirmed and not bracketed:
                self.pending.clear()
                self._judge(table, at, equity, last_equity, day, flows, settled=False)
                self.provisional = self.provisional or "funding changed; awaiting equity between matching funding histories"
                return
            self.flow_transition_at = None
        if flows.unsettled:
            # Pending requests are not profit or capital. Judge contemporaneous readings without them; do not later
            # replay these readings against executed rows whose timestamps may still be their request timestamps.
            # A withdrawal might already have reached equity before its status updates. Latch only a breach that
            # survives every pending withdrawal having landed; deposits cannot explain a fall in equity.
            settled = [row for row in self.pending if row[0] <= flows.read_at]
            self.pending = [row for row in self.pending if row[0] > flows.read_at]
            for t, e, last, d in settled:
                self._judge(table, t, e, last, d, flows, settled=False)
                if flows.pending_amounts is not None:
                    withdrawal = sum((a for a in flows.pending_amounts if a < 0), ZERO)
                    conservative = FlowBook(flows.read_at, flows.rows + ((t, withdrawal),), flows.closes,
                                            flows.unsettled, flows.pending_amounts)
                    self._judge(table, t, e, last, d, conservative, settled=True)
            if self.pending:
                self._judge(table, *self.pending[-1], flows, settled=False)
            if self.provisional:
                self.provisional += f"; pending funding: {'; '.join(flows.unsettled)[:200]}"
            self.tainted = True
            return
        if self.tainted:
            # Only the current reading is known to belong to the newly executed flow snapshot. Older readings in the
            # gap between the last pending read and this one cannot be placed on either side of its execution.
            self.pending = [row for row in self.pending if row[0] >= at]
            if self.last_reading is None:
                # A House first started during an ambiguous funding transition has no observed clean daily base.
                # Establish it now; the since-reset drawdown remains judged throughout the transition.
                self.sod_equity, self.sod_at, self.sod_flows = equity, at, flows.net_until(at)
            self.tainted = False
        # Settled observations: their flows were read after them, so every deposit that was in their equity is known.
        settled = [row for row in self.pending if row[0] <= flows.read_at]
        self.pending = [row for row in self.pending if row[0] > flows.read_at]
        for t, e, last, d in settled:
            self._judge(table, t, e, last, d, flows, settled=True)
        if self.pending:
            t, e, last, d = self.pending[-1]
            self._judge(table, t, e, last, d, flows, settled=False)
        if at <= flows.read_at:
            self.last_reading = [at, equity, day]
            self.last_reading_flows = flows.net_until(at)

    def _judge(self, table: Table, t: float, equity: Decimal, last_equity: Decimal, day: str, flows: "FlowBook", *,
               settled: bool) -> None:
        since_reset = flows.net_until(t)
        profit = equity - since_reset - self.start_equity
        if settled and not flows.unsettled:
            self.last_profit = profit
            if profit > self.peak_profit:
                self.peak_profit = profit
        peak_equity = self.start_equity + since_reset + self.peak_profit
        drawdown = (self.peak_profit - profit) / peak_equity if peak_equity > 0 else Decimal(1)
        self.drawdown = drawdown
        breaches = []
        if drawdown >= table.drawdown_stop_share:
            why = (f"equity ${cents(equity)} is {drawdown:.1%} below the peak of ${cents(peak_equity)} since the reset "
                   f"(deposits and withdrawals netted); the line is {table.drawdown_stop_share:.0%}")
            if settled:
                if not self.drawdown_tripped:
                    self.drawdown_tripped, self.drawdown_why, self.drawdown_at = True, why, t
            else:
                breaches.append(why)
        if day == self.day and self.sod_equity is not None and self.sod_at is not None:
            if self.sod_flows is None:
                self.sod_flows = flows.net_until(self.sod_at)
            today = since_reset - self.sod_flows
            base = self.sod_equity + today
            day_pnl = equity - self.sod_equity - today
            self.day_base, self.day_pnl = base, day_pnl
            if (base > 0 and day_pnl <= -table.daily_stop_share * base) or (base <= 0 and equity <= 0):
                why = (f"the day's P&L ${cents(day_pnl)} is at or past {table.daily_stop_share:.0%} of the day's base "
                       f"${cents(base)} (start-of-day equity plus today's net deposits)")
                if settled:
                    if not self.daily_tripped:
                        self.daily_tripped, self.daily_why = True, why
                else:
                    breaches.append(why)
        if breaches and not settled:
            self.provisional = "; ".join(breaches)

    def release_drawdown(self) -> None:
        """The owner's release of the drawdown pause: the peak starts again from the latest settled reading."""
        self.drawdown_tripped, self.drawdown_why, self.drawdown_at = False, "", None
        if self.last_profit is not None:
            self.peak_profit = self.last_profit


@dataclass(frozen=True)
class FlowBook:
    """The owner's deposits and withdrawals since the reset, as read at `read_at` (epoch seconds): [(time, amount)]
    signed (a deposit positive), and the session closes the daily stop nets from (`previous_close_of`)."""

    read_at: float
    rows: tuple[tuple[float, Decimal], ...]
    closes: tuple[float, ...] = ()   # epoch seconds of recent session closes, ascending
    unsettled: tuple[str, ...] = ()  # funding activities not executed yet (queued, pending): nothing settles on them
    pending_amounts: tuple[Decimal, ...] | None = None  # signed amounts, None when unavailable (no definite latch)

    def net_until(self, t: float) -> Decimal:
        return sum((amount for when, amount in self.rows if when <= t), ZERO)

    def net_between(self, after: float, until: float) -> Decimal:
        """Flows with after < time <= until."""
        return sum((amount for when, amount in self.rows if after < when <= until), ZERO)

    def previous_close_of(self, t: float) -> float | None:
        before = [c for c in self.closes if c < t]
        return before[-1] if before else None


__all__ = ["Table", "DECLARED_TYPES", "order_types", "Forward", "forward_stats", "one_record", "kelly_cap", "sizing_band", "REAL_MIN_TRADES", "band_for", "fits_probe", "probe_cap", "structure_cap", "family_cap",
           "Exposure", "Plan", "plan_open", "Stops", "FlowBook", "D", "cents", "sized_ok", "IncubatorTally", "practice_ok",
           "plan_incubator", "INCUBATOR_DAY_LEGS", "INCUBATOR_DAY_OPEN_SHARE"]
