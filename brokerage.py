"""Offline, synthetic brokerage accounting exercise. No API or credentials.

This is our normalized internal adapter contract, NOT Schwab's API schema.
Version 1 covers USD book cash, long positions, executed fills, and external
deposits/withdrawals. Orders describe intent; only fills move cash/positions.
Snapshots include decimal-string marks for equity accounting. Book cash is
not settled cash or buying power. Dividends, splits, tax lots, settlement,
FX, and broker-specific rounding are outside this deliberately small fixture.
"""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re


FIXTURE = Path(__file__).resolve().parent / 'data/fixtures/brokerage-demo.json'
DECIMAL = re.compile(r'-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?\Z')


def number(value, field, *, minimum=None):
    """Reject floats, non-finite values, and unbounded decimal representations."""
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        raise ValueError(f'{field} must be a bounded plain decimal string')
    result = Decimal(value)
    if minimum is not None and result < minimum:
        raise ValueError(f'{field} must be at least {minimum}')
    return result


def identifier(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', value):
        raise ValueError(f'{field} must be a short identifier')
    return value


def snapshot(value, field):
    if not isinstance(value, dict) or not isinstance(value.get('positions'), dict):
        raise ValueError(f'{field} must contain cash and positions')
    cash = number(value.get('cash'), f'{field}.cash', minimum=0)
    positions, equity = {}, cash
    for symbol, position in value['positions'].items():
        identifier(symbol, 'symbol')
        if not isinstance(position, dict):
            raise ValueError('Each position must contain quantity and price')
        quantity = number(position.get('quantity'), 'position.quantity', minimum=0)
        price = number(position.get('price'), 'position.price', minimum=0)
        positions[symbol] = quantity
        equity += quantity * price
    return cash, positions, equity


def rows(case, field):
    values = case.get(field)
    if not isinstance(values, list) or not all(isinstance(v, dict) for v in values):
        raise ValueError(f'{field} must be a list of objects')
    return values


def unique_id(value, seen, field):
    identifier(value, field)
    if value in seen:
        raise ValueError(f'Duplicate {field}: {value}')
    seen.add(value)
    return value


def decimal_text(value):
    return format(value.normalize(), 'f') if value else '0'


def reconcile(case):
    """Return exact accounting differences; malformed records raise ValueError.

    Cashflows are signed external funding only. Fees belong to individual
    fills. The exercise uses exact decimal notionals without broker rounding.
    It reconciles a period, not transaction ordering or settlement eligibility.
    P&L is equity change less external funding, never a time-weighted return.
    """
    if not isinstance(case, dict) or case.get('schema_version') != 1:
        raise ValueError('Expected internal schema_version 1')
    if case.get('synthetic') is not True or case.get('currency') != 'USD':
        raise ValueError('Only explicitly synthetic USD exercises are supported')
    # Bounded input decimal lengths above keep arithmetic exact in this context.
    with localcontext() as context:
        context.prec = 60
        return _reconcile(case)


def _reconcile(case):
    cash, holdings, opening_equity = snapshot(case.get('opening'), 'opening')
    reported_cash, reported_holdings, closing_equity = snapshot(case.get('closing'), 'closing')
    orders, order_ids = {}, set()
    for order in rows(case, 'orders'):
        oid = unique_id(order.get('id'), order_ids, 'order id')
        symbol = identifier(order.get('symbol'), 'order.symbol')
        side = order.get('side')
        quantity = number(order.get('quantity'), 'order.quantity', minimum=0)
        if side not in ('buy', 'sell') or quantity <= 0:
            raise ValueError('Orders require buy/sell and positive quantity')
        orders[oid] = {'symbol': symbol, 'side': side, 'quantity': quantity,
                       'filled': Decimal(0)}

    net_funding, flow_ids = Decimal(0), set()
    for flow in rows(case, 'cashflows'):
        unique_id(flow.get('id'), flow_ids, 'cashflow id')
        amount = number(flow.get('amount'), 'cashflow.amount')
        kind = flow.get('kind')
        if not ((kind == 'deposit' and amount > 0) or
                (kind == 'withdrawal' and amount < 0)):
            raise ValueError('Deposit must be positive; withdrawal must be negative')
        net_funding += amount
    cash += net_funding

    fees, fill_ids = Decimal(0), set()
    for fill in rows(case, 'fills'):
        unique_id(fill.get('id'), fill_ids, 'fill id')
        oid = identifier(fill.get('order_id'), 'fill.order_id')
        if oid not in orders:
            raise ValueError('Fill references an unknown order')
        order = orders[oid]
        quantity = number(fill.get('quantity'), 'fill.quantity', minimum=0)
        price = number(fill.get('price'), 'fill.price', minimum=0)
        fee = number(fill.get('fee'), 'fill.fee', minimum=0)
        if quantity <= 0 or price <= 0:
            raise ValueError('Executed quantity and price must be positive')
        order['filled'] += quantity
        if order['filled'] > order['quantity']:
            raise ValueError('Executed quantity exceeds the order quantity')
        sign = 1 if order['side'] == 'buy' else -1
        symbol = order['symbol']
        holdings[symbol] = holdings.get(symbol, Decimal(0)) + sign * quantity
        cash -= sign * quantity * price + fee
        fees += fee

    if cash < 0 or any(quantity < 0 for quantity in holdings.values()):
        raise ValueError('This exercise supports nonnegative closing cash and positions')
    cash_difference = reported_cash - cash
    position_differences = {
        symbol: decimal_text(reported_holdings.get(symbol, Decimal(0)) - holdings.get(symbol, Decimal(0)))
        for symbol in sorted(holdings.keys() | reported_holdings.keys())
        if reported_holdings.get(symbol, Decimal(0)) != holdings.get(symbol, Decimal(0))
    }
    matched = cash_difference == 0 and not position_differences
    return {
        'mode': 'synthetic offline exercise', 'currency': 'USD',
        'reconciled': matched,
        'expected_cash': decimal_text(cash), 'reported_cash': decimal_text(reported_cash),
        'cash_difference': decimal_text(cash_difference),
        'expected_positions': {s: decimal_text(q) for s, q in sorted(holdings.items())},
        'position_differences': position_differences,
        'unfilled_quantities': {oid: decimal_text(o['quantity'] - o['filled'])
                                for oid, o in orders.items() if o['quantity'] != o['filled']},
        'opening_equity': decimal_text(opening_equity),
        'reported_closing_equity': decimal_text(closing_equity),
        'net_external_cashflow': decimal_text(net_funding), 'fees': decimal_text(fees),
        'investment_pnl': decimal_text(closing_equity - opening_equity - net_funding) if matched else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['demo'])
    parser.parse_args()
    try:
        result = reconcile(json.loads(FIXTURE.read_text()))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Invalid synthetic fixture: {error}\n')
    print(json.dumps(result, indent=2))
    return 0 if result['reconciled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
