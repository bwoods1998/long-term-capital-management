"""Dividends, splits and the other corporate actions of held symbols, from the venue's account activities (A8.10).

Owner: book. The EquityBook reads `GET v2/account/activities` for `TYPES` (through `league.live.venue.Account.activities`)
and books each activity once (`eq_activities`, keyed by the venue's activity id):

- DIV, DIVCGL, DIVCGS, DIVROC, DIVNRA, DIVTW: cash allocated to the lots held on the ex-date, pro rata by qty, booked
  to each lot's `div` (and its `cash`); DIVNRA and DIVTW are withholdings (negative);
- SSP, SSO (stock split, spin-off), REORG, NC (name change), MA (merger/acquisition), and cash in lieu: the lots' qty
  and entry price adjusted (a split keeps the notional), the cash in lieu booked;
- ANY OTHER activity type touching a held symbol FREEZES equity entries (`EquityBook.frozen`) and alarms;
- an unexplained quantity change is a reconciliation mismatch (two readings freeze entries; exits go on).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

#: The activity types the book reads and books.
DIVIDENDS = ("DIV", "DIVCGL", "DIVCGS", "DIVROC", "DIVNRA", "DIVTW")
ACTIONS = ("SSP", "SSO", "REORG", "NC", "MA")
TYPES = DIVIDENDS + ACTIONS


@dataclass(frozen=True)
class Booking:
    """What one activity does to the book: `kind` ("dividend" | "split" | "cash_in_lieu" | "rename" | "freeze"),
    `symbol`, `day` (ISO ex or effective day), `per_lot` ({lid: {"div": Decimal, "qty": Decimal, "entry_px": Decimal,
    "cash": Decimal}} changes), `why` (a sentence)."""

    kind: str
    symbol: str
    day: str | None
    per_lot: Mapping[int, Mapping[str, Decimal]]
    why: str


def book_activity(activity: Mapping[str, Any], lots: Sequence[Mapping[str, Any]]) -> Booking:
    """The booking of one venue activity row against the open lots (eq_lots rows as dicts) of its symbol held on its
    ex-date. Pure; the book writes it in one transaction with the `eq_activities` row."""
    raise NotImplementedError("book: league/equity/actions.py book_activity")


__all__ = ["DIVIDENDS", "ACTIONS", "TYPES", "Booking", "book_activity"]
