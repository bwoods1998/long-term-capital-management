"""Offline synthetic valuation-boundary returns. No account or market-data access."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import json
from pathlib import Path
import re

FIXTURE = Path(__file__).resolve().parent / 'data/performance/synthetic.json'
NUMBER = re.compile(r'-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?\Z')
MAX_FLOWS = 32


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('Unexpected or missing record fields')


def stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value):
        raise ValueError('Use canonical UTC timestamps to whole seconds')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def amount(value, unit='USD', dated=False):
    keys(value, ['value', 'unit', 'at'] if dated else ['value', 'unit'])
    if value['unit'] != unit:
        raise ValueError('Explicit units must match; no implicit currency or scale conversion')
    if not isinstance(value['value'], str) or not NUMBER.fullmatch(value['value']):
        raise ValueError('Amounts require bounded plain decimal strings')
    if dated:
        stamp(value['at'])
    return Decimal(value['value'])


def text(value):
    raw = format(value, 'f')
    return raw.rstrip('0').rstrip('.') if '.' in raw and value else raw if value else '0'


def percentage(numerator, denominator):
    if denominator <= 0:
        raise ValueError('A return denominator must be positive')
    # Products/cash arithmetic are exact; repeating ratios have declared rounding.
    return text((100 * numerator / denominator).quantize(Decimal('0.000000000001'), rounding=ROUND_HALF_EVEN))


def calculate(case):
    """Chain exact growth-factor products; report percentages to 12 decimals.

    Every flow must have supplied before/after valuations at the identical instant.
    Fees are already in equity. Declared research expenses were paid outside it.
    """
    keys(case, ['schema_version', 'synthetic', 'id', 'currency', 'opening', 'closing',
                'external_flows', 'fees_in_equity', 'research_expense_outside_portfolio', 'benchmark'])
    if type(case['schema_version']) is not int or case['schema_version'] != 1 or case['synthetic'] is not True:
        raise ValueError('Only explicit synthetic schema version 1 is supported')
    if case['currency'] != 'USD' or not isinstance(case['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', case['id']):
        raise ValueError('Use an identified synthetic USD exercise')
    if not isinstance(case['external_flows'], list) or len(case['external_flows']) > MAX_FLOWS:
        raise ValueError('Use at most 32 explicitly valued flows')
    # <=33 factors with <=20 input digits; cross-products fit well below 2048.
    with localcontext() as context:
        context.prec = 2048
        return _calculate(case)


def _calculate(case):
    opening, closing = amount(case['opening'], dated=True), amount(case['closing'], dated=True)
    start, end = stamp(case['opening']['at']), stamp(case['closing']['at'])
    if start >= end or opening <= 0 or closing < 0:
        raise ValueError('Require an ordered period, positive initial equity and nonnegative ending equity')
    fees = amount(case['fees_in_equity'])
    research = amount(case['research_expense_outside_portfolio'])
    if fees < 0 or research < 0:
        raise ValueError('Reported expense amounts must be nonnegative')
    intervals, funding, seen = [], Decimal(0), set()
    previous, previous_at = opening, case['opening']['at']
    for flow in case['external_flows']:
        keys(flow, ['id', 'kind', 'at', 'amount', 'before', 'after'])
        if not isinstance(flow['id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', flow['id']) or flow['id'] in seen:
            raise ValueError('External flows require unique IDs')
        seen.add(flow['id'])
        at = stamp(flow['at'])
        if not stamp(previous_at) < at < end:
            raise ValueError('Flow instants must be unique, ordered and strictly inside the measurement period')
        cash = amount(flow['amount'])
        before, after = amount(flow['before'], dated=True), amount(flow['after'], dated=True)
        if flow['before']['at'] != flow['at'] or flow['after']['at'] != flow['at']:
            raise ValueError('Both valuation phases must identify the exact flow instant')
        if not ((flow['kind'] == 'deposit' and cash > 0) or (flow['kind'] == 'withdrawal' and cash < 0)):
            raise ValueError('Deposits are positive and withdrawals negative')
        if before < 0 or after <= 0 or after != before + cash:
            raise ValueError('Flow boundary must reconcile exactly and leave a positive next denominator')
        intervals.append((previous_at, flow['at'], previous, before))
        previous, previous_at = after, flow['at']
        funding += cash
    intervals.append((previous_at, case['closing']['at'], previous, closing))
    benchmark = case['benchmark']
    keys(benchmark, ['kind', 'currency', 'observations'])
    if benchmark['kind'] != 'synthetic_total_return_index' or benchmark['currency'] != 'USD':
        raise ValueError('Require an explicitly synthetic total-return index in the same currency')
    points = benchmark['observations']
    if not isinstance(points, list) or len(points) != len(intervals) + 1:
        raise ValueError('Benchmark must cover every exact portfolio boundary')
    expected_times = [case['opening']['at']] + [item[1] for item in intervals]
    values = [amount(point, 'index_points', dated=True) for point in points]
    if [point['at'] for point in points] != expected_times or any(value <= 0 for value in values[:-1]) or values[-1] < 0:
        raise ValueError('Benchmark timestamps must align exactly and denominators must be positive')
    pn = pd = bn = bd = Decimal(1)
    periods = []
    for index, (left, right, before, after) in enumerate(intervals):
        if before <= 0:
            raise ValueError('Every subperiod denominator must be positive')
        pn *= after; pd *= before; bn *= values[index + 1]; bd *= values[index]
        periods.append({'start': left, 'end': right,
            'portfolio_return_pct': percentage(after - before, before),
            'benchmark_return_pct': percentage(values[index + 1] - values[index], values[index])})
    return {'schema_version': 1, 'synthetic': True, 'mode': 'offline valuation exercise',
        'id': case['id'], 'currency': 'USD', 'start': case['opening']['at'], 'end': case['closing']['at'],
        'opening_equity': text(opening), 'closing_equity': text(closing),
        'net_external_funding': text(funding), 'investment_pnl': text(closing - opening - funding),
        'reported_fees_already_in_equity': text(fees), 'research_expense_outside_portfolio': text(research),
        'time_weighted_return_pct': percentage(pn - pd, pd),
        'benchmark_return_pct': percentage(bn - bd, bd),
        'difference_percentage_points': percentage(pn * bd - bn * pd, pd * bd),
        'exact_portfolio_growth_ratio': {'numerator': text(pn), 'denominator': text(pd)},
        'exact_benchmark_growth_ratio': {'numerator': text(bn), 'denominator': text(bd)},
        'percentage_rounding': '12 decimal places, half even; chain unrounded factors', 'subperiods': periods}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['demo'])
    parser.add_argument('--case', default='growth-and-funding')
    args = parser.parse_args()
    cases = json.loads(FIXTURE.read_text(), object_pairs_hook=unique)
    selected = [case for case in cases if case['id'] == args.case]
    if len(selected) != 1:
        parser.error('Choose one authored synthetic case ID')
    print(json.dumps(calculate(selected[0]), indent=2))


if __name__ == '__main__':
    main()
