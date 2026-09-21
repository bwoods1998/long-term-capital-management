"""Completed, non-overlapping portfolio exposures from recorded cash and position changes.

Ten partial sells or overlapping contracts are not ten episodes. An episode closes only when
every position opened during it is flat. Payouts, fees and losses remain in its cash result;
stake transfers are never profit. This reduces mechanical duplication, not all market dependence.
"""
import math
from decimal import Decimal, InvalidOperation


def completed(ledger, agent, book, *, since_seq=0, until_seq=None):
    positions, episodes = {}, []
    cash_balance = Decimal(0)
    known_balance = True
    cycle = None
    for entry in ledger.iter(kinds=('book.stake', 'book.fill', 'book.settle'), agent=agent):
        if until_seq is not None and entry.seq > until_seq:
            break
        p = entry.payload
        if p.get('book') != book:
            continue
        if entry.kind == 'book.stake':
            try:
                flow = Decimal(str(p['usd']))
                if not flow.is_finite():
                    raise ValueError('nonfinite flow')
                cash_balance += flow
                if cycle is not None:
                    # Deposits are capital, never profit; withdrawals cannot shrink the
                    # denominator after risk was taken. Accrued profits are capital too.
                    cycle['flows'] += flow
                    cycle['capital'] = max(cycle['capital'], cycle['opening'] + cycle['flows'])
            except (KeyError, ValueError, InvalidOperation, TypeError):
                known_balance = False
                if cycle is not None:
                    cycle['valid'] = False
            continue
        inst = p.get('instrument') or {}
        key = tuple(str(inst.get(k) or '') for k in ('market_id', 'symbol', 'right', 'expiry', 'strike'))
        buy = entry.kind == 'book.fill' and p.get('side') == 'buy'
        if buy and not positions and p.get('source') != 'dust':
            cycle = {'start_seq': entry.seq, 'opened_at': entry.at, 'cash': Decimal(0),
                     'opening': cash_balance, 'capital': cash_balance, 'flows': Decimal(0),
                     'peak_risk': Decimal(0), 'valid': known_balance and cash_balance > 0, 'trades': 0}
        try:
            raw = p.get('cash_delta') if entry.kind == 'book.fill' else p.get('payout')
            if raw is None or not any(key):
                raise ValueError('missing recorded cash or instrument')
            cash = Decimal(str(raw))
            if not cash.is_finite():
                raise ValueError('nonfinite cash')
            cash_balance += cash
            held = positions.get(key, Decimal(0))
            if entry.kind == 'book.settle' or p.get('flat') is True:
                if held <= 0 or buy:
                    raise ValueError('no recorded position to close')
                closing = Decimal(str(p['quantity'])) if entry.kind == 'book.settle' else -Decimal(str(p['position_delta']))
                if not closing.is_finite() or closing != held:
                    raise ValueError('flat flag contradicts recorded quantity')
                positions.pop(key, None)
                if cycle is not None:
                    cycle['trades'] += 1
            else:
                delta = p.get('position_delta')
                if delta is None:
                    raise ValueError('missing recorded position change')
                quantity = Decimal(str(delta))
                if not quantity.is_finite():
                    raise ValueError('nonfinite position')
                if buy and quantity <= 0 or p.get('side') == 'sell' and quantity > 0:
                    raise ValueError('position change contradicts side')
                positions[key] = held + quantity
                if positions[key] < 0:
                    raise ValueError('unrecorded short position')
                if positions[key] <= 0:
                    positions.pop(key, None)
                    if cycle is not None and held > 0:
                        cycle['trades'] += 1
            if cycle is not None:
                cycle['cash'] += cash
                cycle['peak_risk'] = max(cycle['peak_risk'], -cycle['cash'])
        except (KeyError, ValueError, InvalidOperation, TypeError):
            # Missing cash cannot be repaired by a later favorable round trip.
            known_balance = False
            if cycle is not None:
                cycle['valid'] = False
            # An incomplete legacy row is not reconstructed into favorable evidence.
            if entry.kind == 'book.settle' or p.get('flat') is True:
                positions.pop(key, None)
            elif buy:
                positions[key] = Decimal(1)
        if cycle is not None and not positions:
            if (cycle['valid'] and cycle['start_seq'] > since_seq and cycle['trades'] > 0
                    and cycle['capital'] > 0 and entry.at > cycle['opened_at']):
                rate = float(cycle['cash'] / cycle['capital'])
                episodes.append({'first_seq': cycle['start_seq'], 'last_seq': entry.seq,
                    'opened_at': cycle['opened_at'], 'closed_at': entry.at, 'trades': cycle['trades'],
                    'return': rate, 'log_growth': math.log1p(max(rate, -1 + 1e-15)),
                    'risk_fraction': float(cycle['peak_risk'] / cycle['capital'])})
            cycle = None
    return episodes
