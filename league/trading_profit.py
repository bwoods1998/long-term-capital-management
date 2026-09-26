"""Public real-options P&L, independent of account funding, dust, paper and compute.

The live book's position cash includes entry/exit cashflows and recorded trading fees.
Adding the remaining position's marked value gives its whole P&L, including partial closes.
Every historical position is counted, even after its family leaves the public roster.
Missing marks or unresolved inventory produce an unknown result, never an invented zero.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence


def total(rows: Sequence[Mapping[str, Any]], marks: Mapping[int, Any]) -> str | None:
    """`marks` are remaining positions' total dollar values, not per-contract prices."""
    result = Decimal(0)
    try:
        for row in rows:
            cash, qty = Decimal(str(row['cash'])), int(row['qty'])
            if not cash.is_finite() or qty < 0:
                return None
            status = row['status']
            if status == 'closed':
                if qty != 0:
                    return None
                result += cash
                continue
            if status != 'open' or qty == 0 or (json.loads(row.get('info') or '{}') or {}).get('broken'):
                return None
            mark = Decimal(str(marks.get(int(row['pid']))))
            if not mark.is_finite():
                return None
            result += cash + mark
        value = result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return format(value if value else Decimal('0.00'), '.2f')
    except (ValueError, TypeError, KeyError, InvalidOperation, AttributeError):
        return None


def snapshot(root: str | Path, live: Any, *, at: str, never_traded: bool = False) -> dict[str, Any]:
    """Read the options run's state only. No venue calls and no mutations."""
    unknown = {'as_of': at, 'pnl_usd': None}
    path = Path(root) / 'live.sqlite'
    try:
        path.stat()
    except FileNotFoundError:
        # A missing book after a recorded real fill is data loss, not zero profit.
        return {'as_of': at, 'pnl_usd': '0.00'} if never_traded else unknown
    except OSError:
        return unknown
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            rows = [dict(row) for row in db.execute('SELECT pid,qty,entry,cash,status,info FROM positions')]
            uncertain = db.execute("SELECT 1 FROM orders WHERE status IN ('pending','unknown') LIMIT 1").fetchone()
        if uncertain or (not rows and not never_traded):
            return unknown
        marks = {}
        book = getattr(live, 'book', None)
        if getattr(book, 'frozen', None):
            return unknown
        for row in rows:
            if row['status'] == 'closed':
                continue
            position = (getattr(book, 'positions', {}) or {}).get(row['pid'])
            if position is None or any(getattr(position, key) != row[key] for key in ('qty','entry','cash')):
                return unknown
            # Use precisely the live book's existing mark; never mix a stale in-memory
            # quantity with a newly persisted partial close.
            from .live.step import _pnl

            unrealized = _pnl(position, live.day)
            if unrealized is None:
                return unknown
            marks[row['pid']] = (Decimal(str(row['entry'])) * int(row['qty']) * 100
                                 + Decimal(str(unrealized)))
        return {'as_of': at, 'pnl_usd': total(rows, marks)}
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, AttributeError, ImportError):
        return unknown
