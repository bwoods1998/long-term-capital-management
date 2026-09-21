"""Receipt-backed correction of the pre-v2 Kalshi acknowledgement parsing defect.

Only the known 100x price error in a single full allocation can be repaired automatically.
Read-only order receipts must confirm identity, quantity, cost and fees. Ambiguous histories
remain subject to reconciliation. Original rows, quantities, stakes and baselines never change.
"""
from decimal import Decimal

ZERO = Decimal(0)


def evidence_cutoffs(ledger, agent):
    """Old marks/derived outcomes remain in the audit trail, outside subsequent scoring."""
    result = {}
    for entry in ledger.iter(kinds='book.fill_correction', agent=agent):
        result[entry.payload['book']] = entry.seq
    return result


def apply_correction(account, payload):
    account.cash += Decimal(payload['cash_delta'])
    account.fees += Decimal(payload['fees_delta'])
    account.realized += Decimal(payload['realized_delta'])
    for key, delta in payload['holding_cost_deltas'].items():
        account.holdings[key].cost += Decimal(delta)


def _replay(account, entry, payload):
    from .book import Book
    from ltcm.broker import Instrument
    if entry.kind == 'book.stake':
        account.staked += Decimal(payload['usd'])
        account.cash += Decimal(payload['usd'])
    elif entry.kind == 'book.fill':
        Book._apply_account_fill(account, payload, entry.at)
    elif entry.kind == 'book.fill_correction':
        apply_correction(account, payload)
    elif entry.kind == 'book.settle':
        key = Instrument.from_dict(payload['instrument']).key
        holding = account.holdings.pop(key, None)
        payout = Decimal(payload['payout'])
        account.cash += payout
        if holding is not None:
            account.realized += payout - holding.cost


def _state(account):
    return (account.cash, account.fees, account.realized, account.staked,
            {k: (h.quantity, h.cost) for k, h in account.holdings.items()})


def _correction(book, original, replacement, receipt):
    from .book import Account
    before, after = Account(original.agent), Account(original.agent)
    kinds = ('book.stake', 'book.fill', 'book.settle', 'book.fill_correction')
    for entry in book.ledger.iter(kinds=kinds, agent=original.agent):
        if entry.payload.get('book') != book.name:
            continue
        _replay(before, entry, entry.payload)
        _replay(after, entry, replacement if entry.id == original.id else entry.payload)
    if _state(before) != _state(book.account(original.agent)):
        raise ValueError('receipt repair cannot reproduce the current account')
    if {k: h.quantity for k, h in before.holdings.items()} != {k: h.quantity for k, h in after.holdings.items()}:
        raise ValueError('receipt repair would change positions')
    p = original.payload
    return {'book': book.name, 'order_id': p['order_id'], 'original_fill_id': original.id,
            'original_fill_seq': original.seq, 'reason': 'Kalshi V2 dollars parsed as cents and per-contract fee omitted',
            'original': {k: p[k] for k in ('price', 'cash_delta', 'fee_usd', 'venue_fee')},
            'corrected': {k: replacement[k] for k in ('price', 'cash_delta', 'fee_usd', 'venue_fee')},
            'cash_delta': str(after.cash - before.cash), 'fees_delta': str(after.fees - before.fees),
            'realized_delta': str(after.realized - before.realized),
            'holding_cost_deltas': {k: str(h.cost - before.holdings[k].cost) for k, h in after.holdings.items()
                                   if h.cost != before.holdings[k].cost},
            'notional_delta': str(Decimal(p['quantity']) * (Decimal(replacement['price']) - Decimal(p['price']))),
            'venue_fee_delta': str(Decimal(replacement['venue_fee']) - Decimal(p.get('venue_fee') or 0)),
            'receipt': receipt, 'real_money': book.real_money,
            'evidence': 'exclude prior marks and derived results; new evidence starts after this correction'}


def repair_legacy_kalshi_fills(book):
    """Run inside the book's reconciliation lock. GET only; append corrections atomically."""
    from .book import _split_cash, q_cash
    from ltcm.broker import BrokerError
    if not book.real_money or book.fees.family != 'kalshi':
        return 0
    candidates = {}
    for entry in book.ledger.iter(kinds='book.fill'):
        p = entry.payload
        order_id = p.get('order_id')
        if (p.get('book') == book.name and p.get('source') == 'venue' and order_id
                and p.get('venue_accounting_version', 0) < 2 and order_id not in book._receipt_checked):
            candidates.setdefault(order_id, []).append(entry)
    count = 0
    for order_id, entries in list(candidates.items())[:8]:
        working = book.orders.get(order_id)
        if working is None or working.open or working.status != 'filled' or not working.broker_order_id:
            continue
        # Multiple partial allocations have distinct execution prices. A cumulative receipt
        # does not establish those prices, so it cannot retrospectively assign them.
        if len({e.payload.get('intent_id') for e in entries}) != len(entries):
            book._receipt_checked.add(order_id)
            continue
        try:
            order = book.broker.get_order(working.broker_order_id)
        except BrokerError:
            continue
        verified = getattr(order, '_raw', {}).get('receipt_accounting')
        if not verified:
            book._receipt_checked.add(order_id)
            continue
        quantities = [Decimal(e.payload['quantity']) for e in entries]
        if not (order.broker_order_id == working.broker_order_id and order.side == working.side
                and order.instrument.key == working.instrument.key and order.status == 'filled'
                and order.filled_quantity == working.filled == working.quantity == sum(quantities, ZERO)
                and order.average_price is not None and ZERO < order.average_price <= 1
                and order.fees is not None and order.fees >= ZERO
                and all(Decimal(e.payload['price']) * 100 == order.average_price
                        and Decimal(e.payload.get('fee_usd') or 0) == ZERO
                        and Decimal(e.payload.get('fee_quantity') or 0) == ZERO for e in entries)):
            book._receipt_checked.add(order_id)
            continue
        receipt = {'broker_order_id': order.broker_order_id, 'client_order_id': order.intent_id,
                   'instrument': order.instrument.to_dict(), 'side': order.side,
                   'filled_quantity': str(order.filled_quantity), 'average_price': str(order.average_price),
                   'fees': str(order.fees), 'source': 'GET /portfolio/orders/{order_id}',
                   'venue_updated_at': order.updated_at}
        rows = []
        # Single allocation: each participating agent gets the same price and its exact
        # pro-rata fee. Repeated intents by the same agent need sequential replay, so defer.
        if len({e.agent for e in entries}) != len(entries):
            book._receipt_checked.add(order_id)
            continue
        for entry, quantity, fee in zip(entries, quantities, _split_cash(order.fees, quantities)):
            gross = quantity * order.average_price * working.instrument.multiplier
            cash = (gross if working.side == 'sell' else -gross) - fee
            replacement = {**entry.payload, 'price': str(order.average_price), 'cash_delta': str(q_cash(cash)),
                           'fee_usd': str(fee), 'venue_fee': str(fee)}
            payload = _correction(book, entry, replacement, receipt)
            rows.append({'kind': 'book.fill_correction', 'agent': entry.agent, 'payload': payload,
                         'id': 'kalshi-v2-receipt:' + entry.id})
        for entry in book.ledger.append_many(rows):
            book._apply(entry.kind, entry.agent, entry.payload, entry.at)
            count += 1
        book._receipt_checked.add(order_id)
    return count
