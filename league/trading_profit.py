"""Public real-options P&L: every position on the owner's Brokerage Account since the reset, and what the account adds.

Profit (the site's headline, `trading {as_of, pnl_usd}`) is the complete real-options P&L of the Brokerage Account since
`performance.start_at`, and the site's positions table (the owner, Sept 28, 2026) lists what it is made of, so that the
lines add up to it to the cent:

- **One row per position** of the live book (`<state>/live.sqlite`) opened since the reset, open or closed, an agent's
  or the House's: its cash (every entry and exit cashflow, less its fees) and, while it is open, its remaining
  quantity's marked value. Its fees are the book's estimate until the broker posts the real ones for all of an order's
  legs; then the broker's charged fees replace the estimate in that position's own row (`account_activity.classify`
  `fees_by_pid`). Each row is rounded to the cent (half up) and Profit adds the rounded rows, so the rows add up
  exactly. Every historical position is counted, even after its family leaves the public roster.
- **Other account activity** (`league/account_activity.py`): what the account's own activity record holds outside the
  book's positions: fees no position carries (the broker's pass-through charges, a liquidation's fee true-up, a fee on
  an order the book does not hold), crypto fees, interest and other returns. The leftover crypto dust is not counted.
- **Unreconciled**: anything the account shows that the book cannot account for (a fill on an order the book does not
  hold, fills that differ from the book's, the difference between the broker's cash for an assignment, an exercise or a
  cash settlement and the book's own value for it, an activity of a kind nobody classified). Shown as its own line and
  alerted, never hidden, never left out.

Missing marks, unresolved inventory, an uncertain order, a frozen reconciliation, an account event the book has not
settled yet (shares an assignment left, a broker fill on a contract the book still holds) or no fresh reading of the
account's activity produce an unknown Profit, never an invented zero.

The D3 calibration round trips (`league/live/calibration.py`, family `house:calibration`) ARE Profit, since Sept 28,
2026: they are real money on the owner's account, and the positions table has to add up to the headline. They are
labelled "House calibration" (a row's `source`), never an agent's. They stay what they were everywhere else: never an
agent's structure on the site, never a forward record, never a compute line (`league/live/step.py`). The docstring of
`league/live/calibration.py` and the comment in `league/live/step.py` say so too (a comment-only change there: a file
of `league/ci.py`'s FORBIDDEN, so it ships with the owner's deploy).

No field published here is a price: a row carries what the position is (root, structure kind, right, legs, quantity,
expiry, times to the minute) and its dollar P&L, never a strike, a fill price, a mark or a leg's code. An open row's
P&L is at the House's current value of the position, so read with its maximum loss (published in `structures` and on
the tape since before the table) it implies that value per contract. The table's rules allow a position's dollar P&L
(Sept 28, 2026); valuing open rows from a quote at least fifteen minutes old instead is the owner's decision.
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


#: The calibration round trips' family (`league.live.calibration.FAMILY`, held equal by its test): the House's own.
CALIBRATION_FAMILY = 'house:calibration'
#: The parts of the "Other account activity" line (`league.account_activity.classify`), in the order the site draws them.
OTHER_PARTS = ('fees_usd', 'crypto_usd', 'interest_usd', 'misc_usd')
CENT = Decimal('0.01')
#: A read of the book that a concurrent write invalidated is tried again this many times before it is unknown.
READ_ATTEMPTS = 3


def cents(value: Any) -> Decimal:
    """`value` to the cent, half up, never "-0.00"."""
    out = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    return out if out else Decimal('0.00')


def usd(value: Decimal | None) -> str | None:
    return None if value is None else format(cents(value), '.2f')


def row_value(row: Mapping[str, Any], marks: Mapping[int, Any]) -> Decimal | None:
    """One position's P&L, unrounded: its cash when closed, its cash plus the remaining quantity's marked value when
    open (`marks` are remaining positions' total dollar values, not per-contract prices); None when it cannot be priced
    (unresolved inventory, a broken structure, no mark, a non-finite number)."""
    try:
        cash, qty = Decimal(str(row['cash'])), int(row['qty'])
        if not cash.is_finite() or qty < 0:
            return None
        status = row['status']
        if status == 'closed':
            return cash if qty == 0 else None
        if status != 'open' or qty == 0 or (json.loads(row.get('info') or '{}') or {}).get('broken'):
            return None
        mark = Decimal(str(marks.get(int(row['pid']))))
        return cash + mark if mark.is_finite() else None
    except (ValueError, TypeError, KeyError, InvalidOperation, AttributeError):
        return None


def total(rows: Sequence[Mapping[str, Any]], marks: Mapping[int, Any]) -> str | None:
    """The rows' P&L: each row rounded to the cent (half up), then added, so a table of the rounded rows adds up to it
    exactly. None when any row cannot be priced."""
    result = Decimal(0)
    for row in rows:
        value = row_value(row, marks)
        if value is None:
            return None
        result += cents(value)
    return usd(result)


def marked_value(row: Mapping[str, Any], day: Any) -> tuple[Decimal, str] | None:
    """Copy only this position's quote columns; value the immutable database quantity."""
    import numpy as np

    if day is None:
        return None
    chain = day.chains.get(row['root'])
    if chain is None:
        return None
    legs = json.loads(row['legs'])
    revision = getattr(chain, 'quote_revision', None)
    if not isinstance(revision, int) or revision % 2:
        return None  # record() is updating this chain, or this reader predates coherent snapshots
    generation = chain.generation
    indices = [chain.column(leg['symbol']) for leg in legs]
    if not indices or min(indices) < 0:
        return None
    bids, asks = chain.bid[:, indices].copy(), chain.ask[:, indices].copy()
    if generation != chain.generation or revision != chain.quote_revision:
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


# ------------------------------------------------------------------------------------------- the rows
def _epoch(value: Any) -> float | None:
    """Epoch seconds of an ISO stamp with a zone (or of a number), else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace('Z', '+00:00')
    if '.' in text:  # the broker's nanoseconds: Python reads six digits
        head, _, rest = text.partition('.')
        digits = len(rest) - len(rest.lstrip('0123456789'))
        text = f"{head}.{rest[:digits][:6].ljust(6, '0')}{rest[digits:]}"
    try:
        stamp = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp.timestamp() if stamp.tzinfo is not None else None


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _right(legs: Sequence[Mapping[str, Any]]) -> str | None:
    """"call" or "put" when every leg is one, "both" when it holds both (a condor, a straddle), None when unreadable."""
    kinds = [leg.get('is_call') if isinstance(leg, Mapping) else None for leg in legs]
    if not kinds or any(not isinstance(kind, bool) for kind in kinds):
        return None
    return 'both' if len(set(kinds)) > 1 else 'call' if kinds[0] else 'put'


def _venue_fill_time(order: Mapping[str, Any] | None) -> float | None:
    """When the broker says the order filled (`answer.filled_at`, kept by the live book for the owner's record)."""
    if not order:
        return None
    try:
        answer = json.loads(order.get('answer') or '{}') or {}
    except (TypeError, ValueError):
        return None
    return _epoch(answer.get('filled_at')) if isinstance(answer, Mapping) else None


def source_of(family: Any) -> str:
    """Who a position belongs to on the site: "calibration" (the House's calibration round trips), "house" (any other
    of the House's own families, `house:*`), else "agent" (the family is the agent's id)."""
    family = str(family or '')
    if family == CALIBRATION_FAMILY:
        return 'calibration'
    return 'house' if family.startswith('house:') else 'agent'


def _expiry_close(day: str | None) -> float | None:
    """16:00 New York time on `day`: when a contract left at its expiry ends (an unpriced close keeps no close time)."""
    try:
        return dt.datetime.combine(dt.date.fromisoformat(str(day)), dt.time(16), tzinfo=ZoneInfo('America/New_York')).timestamp()
    except (TypeError, ValueError):
        return None


def _minute(epoch: float | None) -> float | None:
    """Down to the minute: the table shows minutes, and a broker's fill time to the millisecond is a lookup key into the
    public time and sales (the review of #408)."""
    return None if epoch is None else float(int(epoch // 60) * 60)


def position_rows(positions: Sequence[Mapping[str, Any]], orders: Sequence[Mapping[str, Any]],
                  marks: Mapping[int, Any]) -> list[dict[str, Any]]:
    """Each position as the table's row, before the publisher's allowlist: what it is, whose, when, its P&L. The
    opening and closing times are the broker's fill times where the book kept them (`answer.filled_at`), else the
    book's own, down to the minute; a close the broker made at expiry with no fill the book priced (`unpriced_close`)
    closed at 16:00 New York time on its expiry. The legs' contracts and strikes stay here: only their count and their
    right leave."""
    by_oid = {int(o['oid']): o for o in orders if o.get('oid') is not None}
    by_pid: dict[int, list[Mapping[str, Any]]] = {}
    for order in orders:
        if order.get('pid') is not None:
            by_pid.setdefault(int(order['pid']), []).append(order)
    out = []
    for row in positions:
        pid = int(row['pid'])
        try:
            legs = json.loads(row.get('legs') or '[]') or []
        except (TypeError, ValueError):
            legs = []
        info = {}
        try:
            info = json.loads(row.get('info') or '{}') or {}
        except (TypeError, ValueError):
            pass
        mine = by_pid.get(pid, [])
        opening = by_oid.get(int(info['order'])) if isinstance(info, Mapping) and str(info.get('order', '')).isdigit() else None
        opened = _venue_fill_time(opening)
        if opened is None:
            opened = min((t for t in (_venue_fill_time(o) for o in mine if o.get('action') == 'open') if t is not None), default=None)
        opened = opened if opened is not None else _epoch(row.get('opened_at'))
        status = str(row.get('status') or '')
        closed = None
        expiries = [str(leg.get('expiry') or '') for leg in legs if isinstance(leg, Mapping)]
        expiry = min(expiries) if expiries and all(expiries) else None
        if status in ('closed', 'unpriced_close'):
            closes = [t for t in (_venue_fill_time(o) for o in mine if o.get('action') in ('close', 'close_leg')) if t is not None]
            closed = max(closes) if closes else _epoch(row.get('closed_at'))
            if closed is None:
                closed = _expiry_close(max(expiries) if expiries and all(expiries) else None)
        value = row_value(row, marks)
        out.append({
            'pid': pid, 'family': str(row.get('family') or ''), 'source': source_of(row.get('family')),
            'underlying': str(row.get('root') or ''), 'structure': str(row.get('type') or ''), 'right': _right(legs),
            'legs': len(legs), 'quantity': int(row.get('opened_qty') or 0),
            'open_quantity': int(row.get('qty') or 0) if status in ('open', 'awaiting_expiry') else 0,
            # Awaiting the broker's expiry, it still holds its contracts; an unpriced close holds none.
            'status': 'open' if status in ('open', 'awaiting_expiry') else 'closed',
            'expiry': expiry,
            'opened_at': _iso(_minute(opened)), 'closed_at': _iso(_minute(closed)),
            'pnl_usd': usd(value) if value is not None else None,
        })
    return out


def ledger(root: str | Path, live: Any, *, at: str, never_traded: bool = False, start_at: Any = None) -> dict[str, Any]:
    """{as_of, pnl_usd, rows}: the book's part of Profit and its rows, read in one read transaction of the live book
    (read-only: no venue calls and no mutations). `pnl_usd` is the rows' total (`total`), unknown (None) when any row
    cannot be priced, any order (any family's, the calibration's included) is pending or unknown, reconciliation is
    frozen, or the book changed while the marks were copied. `rows` is None when the book cannot be read at all; the
    rows are those opened at or after `start_at` (the performance reset) when it is given."""
    unknown = {'as_of': at, 'pnl_usd': None, 'rows': None}
    path = Path(root) / 'live.sqlite'
    try:
        path.stat()
    except FileNotFoundError:
        # A missing book after a recorded real fill is data loss, not zero profit.
        return {'as_of': at, 'pnl_usd': '0.00', 'rows': []} if never_traded else unknown
    except OSError:
        return unknown
    since = _epoch(start_at)
    try:
        for _ in range(READ_ATTEMPTS):
            read = _read(path, live, at=at, never_traded=never_traded, since=since)
            if read is not None:
                return read
        return unknown  # a fill or a freeze changed the book during every read
    except (OSError, sqlite3.Error, ValueError, TypeError, LookupError, AttributeError, ImportError, InvalidOperation):
        return unknown


def _read(path: Path, live: Any, *, at: str, never_traded: bool, since: float | None) -> dict[str, Any] | None:
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        version = db.execute('PRAGMA data_version').fetchone()[0]
        db.execute('BEGIN')
        everything = [dict(row) for row in db.execute('SELECT * FROM positions')]
        orders = [dict(row) for row in db.execute('SELECT * FROM orders')]
        recon = db.execute("SELECT value FROM kv WHERE key='recon'").fetchone()
        frozen = (json.loads(recon[0]) or {}).get('frozen') if recon else None
        rows = [row for row in everything if since is None or (_epoch(row.get('opened_at')) or 0.0) >= since]
        uncertain = any(order.get('status') in ('pending', 'unknown') for order in orders)
        book = getattr(live, 'book', None)
        certain = not (uncertain or frozen or getattr(book, 'frozen', None) or (not everything and not never_traded))
        marks, valued_at = {}, at
        for row in rows:
            if row.get('status') != 'open':
                continue
            marked = marked_value(row, getattr(live, 'day', None)) if live is not None else None
            if marked is None or marked[1] > at:
                certain = False  # this row is unpriced; the others still show
                continue
            marks[row['pid']], mark_at = marked
            valued_at = min(valued_at, mark_at)
        db.rollback()
        if db.execute('PRAGMA data_version').fetchone()[0] != version:
            return None  # a fill/freeze changed while quote columns were being copied
    pnl = total(rows, marks) if certain else None
    return {'as_of': valued_at, 'pnl_usd': pnl, 'rows': position_rows(rows, orders, marks)}


def snapshot(root: str | Path, live: Any, *, at: str, never_traded: bool = False, start_at: Any = None) -> dict[str, Any]:
    """{as_of, pnl_usd}: the book's part of Profit (`ledger` without its rows)."""
    read = ledger(root, live, at=at, never_traded=never_traded, start_at=start_at)
    return {'as_of': read['as_of'], 'pnl_usd': read['pnl_usd']}


def complete(book: Mapping[str, Any] | None, other: Mapping[str, Any] | None, *,
             at: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """(trading, positions): Profit, and the table's inputs, from the book's `ledger` and the account's activity reading
    (`league.account_activity`: {as_of, fees_usd, crypto_usd, interest_usd, misc_usd, unreconciled_usd, fees_by_pid,
    blocking}, or None when there is no fresh one).

    The broker's posted fee corrections (`fees_by_pid`) go into their positions' rows; one for a position the table
    does not hold, or whose row has no P&L, stays in Other's fees, so nothing is lost. Profit = the rows + Other +
    Unreconciled, each already exact to the cent, so the table adds up to Profit exactly. Unknown when the book's part
    is unknown, there is no fresh reading of the account (Profit is only "complete" with it), or the reading names an
    event the book has not settled yet (`blocking`). The positions input is None only when the book could not be read
    at all."""
    if not book or book.get('rows') is None:
        return {'as_of': (book or {}).get('as_of') or at, 'pnl_usd': None}, None
    as_of = book.get('as_of') or at
    parts: dict[str, Decimal] | None = None
    unreconciled: Decimal | None = None
    corrections: dict[int, Decimal] = {}
    blocking: list[str] = []
    if other is not None:
        try:
            parts = {part: cents(other[part]) for part in OTHER_PARTS}
            unreconciled = cents(other['unreconciled_usd'])
            corrections = {int(pid): cents(value) for pid, value in (other.get('fees_by_pid') or {}).items()}
            blocking = [str(reason) for reason in other.get('blocking') or []]
        except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
            parts = unreconciled = None
            corrections, blocking = {}, []
    rows = []
    for row in book['rows']:
        fix = corrections.pop(int(row['pid']), None) if row.get('pid') is not None else None
        if fix is not None and row.get('pnl_usd') is not None:
            row = {**row, 'pnl_usd': usd(Decimal(str(row['pnl_usd'])) + fix)}
        elif fix is not None and parts is not None:
            parts['fees_usd'] += fix  # its row has no P&L to carry it: Other carries it, never lost
        rows.append(row)
    if parts is not None:
        for fix in corrections.values():  # a position outside the table (opened before the reset): Other's fees
            parts['fees_usd'] += fix
    pnl = None
    if book.get('pnl_usd') is not None and parts is not None and unreconciled is not None and not blocking:
        total_rows = sum((Decimal(str(row['pnl_usd'])) for row in rows), Decimal(0))
        pnl = usd(total_rows + sum(parts.values(), Decimal(0)) + unreconciled)
    positions = {
        'as_of': as_of, 'rows': rows,
        'other': None if parts is None else {'as_of': other.get('as_of'), **{k: usd(v) for k, v in parts.items()}},
        'unreconciled_usd': usd(unreconciled),
    }
    return {'as_of': as_of, 'pnl_usd': pnl}, positions
