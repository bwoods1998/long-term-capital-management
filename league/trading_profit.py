"""Public real-options P&L, independent of account funding, dust, paper and compute.

The live book's position cash includes entry/exit cashflows and recorded trading fees.
Adding the remaining position's marked value gives its whole P&L, including partial closes.
Every historical position is counted, even after its family leaves the public roster.
Missing marks or unresolved inventory produce an unknown result, never an invented zero.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from contextlib import closing
import datetime as dt
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


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


def marked_value(row: Mapping[str, Any], day: Any) -> tuple[Decimal, str] | None:
    """Copy only this position's quote columns; value the immutable database quantity."""
    import numpy as np

    if day is None:
        return None
    chain = day.chains.get(row['root'])
    if chain is None:
        return None
    legs = json.loads(row['legs'])
    generation = chain.generation
    indices = [chain.column(leg['symbol']) for leg in legs]
    if not indices or min(indices) < 0:
        return None
    bids, asks = chain.bid[:, indices].copy(), chain.ask[:, indices].copy()
    if generation != chain.generation:
        return None
    good = np.flatnonzero((np.isfinite(bids) & np.isfinite(asks) & (bids >= 0) & (asks >= bids)).all(axis=1))
    if not len(good):
        return None
    minute = int(good[-1])
    mark = sum(Decimal(str(leg['side'])) * Decimal(str(leg['ratio']))
               * (Decimal(str(bids[minute, i])) + Decimal(str(asks[minute, i]))) / 2 for i, leg in enumerate(legs))
    mark_at = (dt.datetime.combine(chain.day, dt.time(), tzinfo=ZoneInfo('America/New_York'))
               + dt.timedelta(minutes=chain.open_min + minute)).astimezone(dt.timezone.utc)
    return mark * int(row['qty']) * 100, mark_at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


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
            version = db.execute('PRAGMA data_version').fetchone()[0]
            db.execute('BEGIN')
            rows = [dict(row) for row in db.execute('SELECT * FROM positions')]
            uncertain = db.execute("SELECT 1 FROM orders WHERE status IN ('pending','unknown') LIMIT 1").fetchone()
            recon = db.execute("SELECT value FROM kv WHERE key='recon'").fetchone()
            frozen = (json.loads(recon[0]) or {}).get('frozen') if recon else None
            if uncertain or frozen or (not rows and not never_traded):
                return unknown
            marks, valued_at = {}, at
            book = getattr(live, 'book', None)
            if getattr(book, 'frozen', None):
                return unknown
            for row in rows:
                if row['status'] == 'closed':
                    continue
                marked = marked_value(row, getattr(live, 'day', None))
                if marked is None:
                    return unknown
                marks[row['pid']], mark_at = marked
                if mark_at > at:
                    return unknown
                valued_at = min(valued_at, mark_at)
            db.rollback()
            if db.execute('PRAGMA data_version').fetchone()[0] != version:
                return unknown  # a fill/freeze changed while quote columns were being copied
        return {'as_of': valued_at, 'pnl_usd': total(rows, marks)}
    except (OSError, sqlite3.Error, ValueError, TypeError, LookupError, AttributeError, ImportError, InvalidOperation):
        return unknown
