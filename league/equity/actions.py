"""Dividends, splits and the other corporate actions of held symbols, from the venue's account activities (A8.10).

Owner: book. The EquityBook reads `GET v2/account/activities` for `TYPES` (through `league.live.venue.Account.activities`)
and books each activity once (`eq_activities`, keyed by the venue's activity id):

- DIV, DIVCGL, DIVCGS, DIVROC, DIVNRA, DIVTW: cash allocated to the lots held on the ex-date, pro rata by qty, booked
  to each lot's `div` (and its `cash`); DIVNRA and DIVTW are withholdings (negative);
- SSP, SSO (stock split, spin-off), REORG, NC (name change), MA (merger/acquisition), and cash in lieu: the lots' qty
  and entry price adjusted (a split keeps the notional), the cash in lieu booked;
- ANY OTHER activity type touching a held symbol FREEZES equity entries (`EquityBook.frozen`) and alarms; a rename
  moves the lots to the new symbol and freezes entries too (the programs' NEEDS and the universe name the old one,
  so the owner reviews it);
- an unexplained quantity change is a reconciliation mismatch (two readings freeze entries; exits go on).

WHAT A ROW MUST SAY. Alpaca's non-trade activity row is {id, activity_type, date, net_amount, symbol, qty,
per_share_amount, description, status}; the shapes of the corporate-action types were not seen on this account yet
(the design's facts to verify), so every rule below books only what the row states and FREEZES when it does not say
enough (kind "freeze": the owner books it by hand and clears `eq_freeze`). A split's ratio is the row's `ratio` or
`split_ratio`, else its `new_rate` / `old_rate` (the corporate-actions API's names), else the `ratio` the book infers
from the account's own quantity (the caller adds it to the row, `EquityBook._activity`). A dividend's lots are the ones
held on its ex-date (the caller selects them: the row's `ex_date` when it has one, else the session whose held quantity
equals the row's `qty`); a dividend no lot held is booked to nobody and alarmed (the reconciliation is not touched).

THE BOOKING (`Booking.per_lot`, {lid: changes}): "div" and "cash" are dollars ADDED to the lot (Decimal); "qty",
"opened_qty" and "entry_px" are the lot's NEW values (a split: qty x ratio floored to nine places, the venue's
precision; entry price / ratio, so the entry notional is unchanged). A lot whose new qty is 0 (a cash-out) is closed by
the book at the cash it received.

`lots` given to `book_activity` are eq_lots rows as dicts whose "qty" is the quantity the activity applies to (for a
dividend, what the lot held on the ex-date: a lot closed since then carries its opened quantity there).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

#: The activity types the book reads and books.
DIVIDENDS = ("DIV", "DIVCGL", "DIVCGS", "DIVROC", "DIVNRA", "DIVTW")
ACTIONS = ("SSP", "SSO", "REORG", "NC", "MA")
TYPES = DIVIDENDS + ACTIONS
#: Cash in lieu of a fractional share, when the venue posts it as its own row (it may instead ride on the action's row).
CASH_IN_LIEU = ("CIL",)
#: Types read beside `TYPES`, each in its own request, best effort (a type the venue refuses with HTTP 422 is skipped
#: from then on): cash in lieu is booked; any other of them touching a held symbol freezes (A8.10).
WATCH = CASH_IN_LIEU + ("SC", "DIVFEE", "DIVFT", "DIVTXEX", "MISC", "JNLS", "ACATS")
#: The kinds of a booking.
KINDS = ("dividend", "split", "cash_in_lieu", "spinoff", "rename", "freeze", "none")
SHARE_PLACES = Decimal("1e-9")
PRICE_PLACES = Decimal("1e-6")
CASH_PLACES = Decimal("1e-6")


@dataclass(frozen=True)
class Booking:
    """What one activity does to the book: `kind` ("dividend" | "split" | "cash_in_lieu" | "spinoff" | "rename" |
    "freeze" | "none"), `symbol`, `day` (ISO ex or effective day), `per_lot` ({lid: {"div": Decimal, "qty": Decimal,
    "entry_px": Decimal, "cash": Decimal}} changes: the module docstring), `why` (a sentence). `unattributed`: dollars
    of the activity no lot took (shares outside the book, an assignment's); `new_symbol`: a rename's new symbol."""

    kind: str
    symbol: str
    day: str | None
    per_lot: Mapping[int, Mapping[str, Decimal]]
    why: str
    unattributed: Decimal = Decimal(0)
    new_symbol: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe (Decimals as strings): what `eq_activities.booked` keeps."""
        return {"kind": self.kind, "symbol": self.symbol, "day": self.day, "why": self.why,
                "unattributed": str(self.unattributed), "new_symbol": self.new_symbol,
                "per_lot": {str(lid): {k: str(v) for k, v in changes.items()} for lid, changes in self.per_lot.items()},
                **({"extra": dict(self.extra)} if self.extra else {})}


def dec(value: Any) -> Decimal | None:
    """A finite Decimal from a venue string or number, else None (never a float's binary noise: str first)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return out if out.is_finite() else None


def activity_day(activity: Mapping[str, Any]) -> str | None:
    """The row's ISO day: its `date`, else the day of its `transaction_time`."""
    text = str(activity.get("date") or activity.get("transaction_time") or "")[:10]
    return text if len(text) == 10 and text[4] == "-" and text[7] == "-" else None


def ex_date(activity: Mapping[str, Any]) -> str | None:
    """The row's ex-date when it states one (`ex_date` or `exdate`), else None."""
    text = str(activity.get("ex_date") or activity.get("exdate") or "")[:10]
    return text if len(text) == 10 else None


def ratio_of(activity: Mapping[str, Any]) -> Decimal | None:
    """A split's (or a reorganisation's) shares-after per share-before, when the row says it (the module docstring)."""
    for key in ("ratio", "split_ratio"):
        r = dec(activity.get(key))
        if r is not None and r > 0:
            return r
    new, old = dec(activity.get("new_rate")), dec(activity.get("old_rate"))
    if new is not None and old is not None and new > 0 and old > 0:
        return new / old
    return None


def _held(lots: Sequence[Mapping[str, Any]], symbol: str) -> list[tuple[int, Decimal, Mapping[str, Any]]]:
    out = []
    for lot in lots:
        if str(lot.get("symbol") or "").upper() != symbol:
            continue
        qty = dec(lot.get("qty"))
        if qty is not None and qty > 0:
            out.append((int(lot["lid"]), qty, lot))
    return sorted(out, key=lambda x: x[0])


def _pro_rata(amount: Decimal, held: Sequence[tuple[int, Decimal, Mapping[str, Any]]],
              entitled: Decimal | None) -> tuple[dict[int, Decimal], Decimal]:
    """`amount` split over `held` by qty, each share floored to `CASH_PLACES`: over `entitled` shares when the row
    names more than the book holds (the rest is unattributed), else over the book's own; (shares, unattributed)."""
    total = sum((q for _, q, _ in held), Decimal(0))
    base = entitled if entitled is not None and entitled > total else total
    if base <= 0:
        return {}, amount
    shares = {lid: (amount * q / base).quantize(CASH_PLACES, rounding=ROUND_DOWN) for lid, q, _ in held}
    if base == total and shares:
        # The book holds every entitled share: the rounding remainder goes to the largest lot, so nothing is lost.
        rest = amount - sum(shares.values(), Decimal(0))
        biggest = max(held, key=lambda x: (x[1], -x[0]))[0]
        shares[biggest] += rest
    return shares, amount - sum(shares.values(), Decimal(0))


def _split(kind: str, symbol: str, day: str | None, ratio: Decimal, net: Decimal,
           held: Sequence[tuple[int, Decimal, Mapping[str, Any]]], why: str, entitled: Decimal | None) -> Booking:
    per_lot: dict[int, dict[str, Decimal]] = {}
    for lid, qty, lot in held:
        opened = dec(lot.get("opened_qty")) or qty
        notional = dec(lot.get("entry_notional"))
        new_opened = (opened * ratio).quantize(SHARE_PLACES, rounding=ROUND_DOWN)
        changes = {"qty": (qty * ratio).quantize(SHARE_PLACES, rounding=ROUND_DOWN), "opened_qty": new_opened}
        if notional is not None and new_opened > 0:
            changes["entry_px"] = (notional / new_opened).quantize(PRICE_PLACES)
        else:
            px = dec(lot.get("entry_px"))
            if px is not None:
                changes["entry_px"] = (px / ratio).quantize(PRICE_PLACES)
        per_lot[lid] = changes
    unattributed = Decimal(0)
    if net:
        shares, unattributed = _pro_rata(net, held, entitled)
        for lid, cash in shares.items():
            per_lot[lid]["cash"] = cash
    return Booking(kind, symbol, day, per_lot, why, unattributed=unattributed)


def book_activity(activity: Mapping[str, Any], lots: Sequence[Mapping[str, Any]]) -> Booking:
    """The booking of one venue activity row against the open lots (eq_lots rows as dicts) of its symbol held on its
    ex-date. Pure; the book writes it in one transaction with the `eq_activities` row."""
    kind = str(activity.get("activity_type") or "").upper()
    symbol = str(activity.get("symbol") or "").upper()
    day = ex_date(activity) or activity_day(activity)
    net = dec(activity.get("net_amount")) or Decimal(0)
    qty = dec(activity.get("qty"))
    held = _held(lots, symbol)
    if kind in DIVIDENDS:
        if not held:
            return Booking("dividend", symbol, day, {}, f"{kind} of ${net} on {symbol}: no lot of the book held it on its "
                                                        "ex-date (booked to nobody)", unattributed=net)
        shares, rest = _pro_rata(net, held, abs(qty) if qty is not None else None)
        per_lot = {lid: {"div": cash, "cash": cash} for lid, cash in shares.items()}
        withheld = " (a withholding)" if kind in ("DIVNRA", "DIVTW") else ""
        return Booking("dividend", symbol, day, per_lot, f"{kind}{withheld} of ${net} on {symbol} over {len(per_lot)} "
                                                         f"lot(s), pro rata by quantity", unattributed=rest)
    if not held:
        # Nothing the book holds: recorded, nothing changes (the account's own reconciliation still sees the symbol).
        return Booking("none", symbol, day, {}, f"{kind} on {symbol}: no lot of the book holds it")
    entitled = abs(qty) if qty is not None and qty != 0 else None
    if kind == "SSP":
        ratio = ratio_of(activity)
        if ratio is None or ratio == 1:
            return Booking("freeze", symbol, day, {}, f"a stock split on {symbol} whose ratio the row does not state: "
                                                      "equity entries frozen until the owner books it")
        return _split("split", symbol, day, ratio, net, held, f"a {ratio.normalize()}:1 split on {symbol}"
                      + (f", ${net} cash in lieu" if net else ""), None)
    if kind in CASH_IN_LIEU:
        shares, rest = _pro_rata(net, held, entitled)
        return Booking("cash_in_lieu", symbol, day, {lid: {"cash": cash} for lid, cash in shares.items()},
                       f"${net} cash in lieu on {symbol}", unattributed=rest)
    if kind == "SSO":
        # The parent's lots keep their quantity; the spun-off shares are another symbol, outside the book (the House
        # sells an unattributed long after two readings, `_close_shares`); a cash part is booked to the lots.
        shares, rest = _pro_rata(net, held, entitled) if net else ({}, Decimal(0))
        return Booking("spinoff", symbol, day, {lid: {"cash": cash} for lid, cash in shares.items()},
                       f"a spin-off from {symbol}: the new shares are outside the book" + (f", ${net} in cash" if net else ""),
                       unattributed=rest)
    if kind in ("REORG", "MA"):
        ratio = ratio_of(activity)
        name = "a reorganisation" if kind == "REORG" else "a merger"
        if ratio is not None and ratio > 0:
            return _split("split", symbol, day, ratio, net, held, f"{name} of {symbol} at {ratio.normalize()} for 1"
                          + (f", ${net} in cash" if net else ""), None)
        total = sum((q for _, q, _ in held), Decimal(0))
        if net > 0 and qty is not None and qty < 0 and abs(qty) >= total:
            # A cash-out: every share the book held is gone for cash.
            shares, rest = _pro_rata(net, held, entitled)
            per_lot = {lid: {"cash": shares.get(lid, Decimal(0)), "qty": Decimal(0)} for lid, _, _ in held}
            return Booking("cash_in_lieu", symbol, day, per_lot, f"{name} of {symbol} for ${net} in cash: its lots close",
                           unattributed=rest)
        return Booking("freeze", symbol, day, {}, f"{name} of {symbol} the row does not describe (no ratio, no cash-out): "
                                                  "equity entries frozen until the owner books it")
    if kind == "NC":
        new = str(activity.get("new_symbol") or activity.get("to_symbol") or "").upper()
        if new and new != symbol:
            return Booking("rename", symbol, day, {}, f"{symbol} renamed {new}", new_symbol=new)
        return Booking("freeze", symbol, day, {}, f"a name change of {symbol} without the new symbol: equity entries "
                                                  "frozen until the owner books it")
    return Booking("freeze", symbol, day, {}, f"a {kind or 'nameless'} activity touches {symbol}, which the book holds: "
                                              "equity entries frozen until the owner books it (A8.10)")


__all__ = ["DIVIDENDS", "ACTIONS", "TYPES", "CASH_IN_LIEU", "WATCH", "KINDS", "Booking", "book_activity", "dec",
           "activity_day", "ex_date", "ratio_of"]
