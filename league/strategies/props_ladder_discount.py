import datetime
import json
import math
import re


NEEDS = {
    'venue': 'kalshi',
    'horizon': 'day',
    'style': 'same-player-ladder-relative-value',
    'series': [
        'KXNFLPASSYDS', 'KXNFLRSHYDS', 'KXNFLRECYDS',
        'KXNFLREC', 'KXMLBKS', 'KXMLBOUTS'
    ],
    'max_hours_to_close': 48,
    'wake_minutes': 5,
    'parameter_rules': {
        'bounds': {'edge_min': [0.02, 0.06]},
        'frozen': ['notional_usd', 'bid_min', 'bid_max', 'max_spread']
    }
}

PARAMS = {
    'edge_min': 0.03,
    'notional_usd': 2.0,
    'bid_min': 0.70,
    'bid_max': 0.95,
    'max_spread': 0.08
}


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def question_template(title, strike):
    # Require a single explicit numeric threshold and preserve all other text.
    # In particular, never group different players just because dates match.
    if not isinstance(title, str):
        return None
    text = ' '.join(title.lower().split())
    values = list(re.finditer(r'\d+(?:\.\d+)?', text))
    if len(values) != 1:
        return None
    token = values[0]
    value = number(token.group())
    if value is None or abs(value - strike) > 0.000001:
        return None
    if re.search(r'\b(under|below|between|exactly)\b|less than|or fewer|at most', text):
        return None
    prefix = text[:token.start()]
    suffix = text[token.end():]
    increasing = bool(re.search(r'\b(over|above)\s*$|(?:at least|more than)\s*$', prefix))
    increasing = increasing or bool(re.match(r'\s*\+|\s+or more\b', suffix))
    if not increasing:
        return None
    return prefix + '<threshold>' + suffix


def fee_unit(price, rate):
    # Reserve at least the full taker fee, even though entry is post-only.
    return math.ceil(rate * price * (1.0 - price) * 10000.0) / 10000.0


def collect_candidates(ctx, params, rate, diagnostics):
    groups = {}
    for market in ctx.get('markets', []):
        series = market.get('series')
        ticker = market.get('market')
        if series not in NEEDS['series'] or not isinstance(ticker, str) or '-' not in ticker:
            continue
        strike = number(market.get('strike'))
        bid = number(market.get('yes_bid'))
        ask = number(market.get('yes_ask'))
        close_hours = number(market.get('hours_to_close'))
        resolve_hours = number(market.get('hours_to_resolve'))
        close_stamp = stamp(market.get('close_time'))
        if None in (strike, bid, ask, close_hours, resolve_hours, close_stamp):
            continue
        if strike < 0 or not 0.0 < bid < ask < 1.0:
            continue
        if not 0.5 <= close_hours <= resolve_hours <= 48.0:
            continue
        if ask - bid > params['max_spread'] + 0.000001:
            continue
        template = question_template(market.get('title'), strike)
        if template is None:
            continue
        group_key = (series, ticker.rsplit('-', 1)[0], template, close_stamp)
        volume = number(market.get('volume_24h')) or 0.0
        interest = number(market.get('open_interest')) or 0.0
        row = {
            'market': ticker, 'strike': strike, 'bid': bid, 'ask': ask,
            'resolve': resolve_hours,
            'reference_ok': ask - bid <= 0.030001 and volume >= 100 and interest >= 10
        }
        groups.setdefault(group_key, []).append(row)
        diagnostics['usable_rows'] += 1

    candidates = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        # Ambiguous duplicate thresholds are not independent corroboration.
        strikes = [row['strike'] for row in rows]
        if len(set(strikes)) != len(strikes):
            continue
        diagnostics['ladders'] += 1
        rows.sort(key=lambda row: row['strike'])
        for leg in ('yes', 'no'):
            ordered = list(reversed(rows)) if leg == 'yes' else rows
            reference = None
            reference_bid = -1.0
            for row in ordered:
                own_bid = row['bid'] if leg == 'yes' else 1.0 - row['ask']
                own_ask = row['ask'] if leg == 'yes' else 1.0 - row['bid']
                if reference is not None and abs(reference['resolve'] - row['resolve']) <= 0.01:
                    price = min(
                        math.floor((own_bid + 0.01) * 100.0 + 0.00000001),
                        math.floor((own_ask - 0.01) * 100.0 + 0.00000001),
                        math.floor(params['bid_max'] * 100.0 + 0.00000001)
                    ) / 100.0
                    if params['bid_min'] <= price < own_ask:
                        reserve = fee_unit(price, rate)
                        # Require an inversion at the ask, not merely a cheap hypothetical bid.
                        margin = reference_bid - own_ask - reserve
                        if margin >= params['edge_min']:
                            candidates.append({
                                'market': row['market'], 'leg': leg, 'price': price,
                                'fee': reserve, 'reference': reference['market'],
                                'margin': margin,
                                'key': row['market'] + '|' + leg + '|' + reference['market']
                            })
                if row['reference_ok'] and own_bid > reference_bid:
                    reference = row
                    reference_bid = own_bid
    diagnostics['dislocations'] = len(candidates)
    candidates.sort(key=lambda item: (-item['margin'], item['market'], item['leg']))
    return candidates


def entry_quantity(ctx, candidate, params):
    limits = ctx.get('limits', {})
    cash = max(0.0, (number(ctx.get('cash')) or 0.0) - 0.01)
    equity = max(0.0, number(ctx.get('equity')) or 0.0)
    budget = min(
        params['notional_usd'], cash, 0.5 * equity,
        max(0.0, number(limits.get('max_order_usd')) or 0.0),
        max(0.0, number(limits.get('max_position_usd')) or 0.0)
    )
    remaining = ctx.get('event_risk', {}).get('remaining_by_market_usd', {})
    if candidate['market'] in remaining:
        budget = min(budget, max(0.0, number(remaining[candidate['market']]) or 0.0))
    quantity = int(math.floor(budget / (candidate['price'] + candidate['fee'])))
    if quantity < 1 or quantity * candidate['price'] < 1.0:
        return 0
    return quantity


def decide(ctx):
    params = dict(PARAMS)
    params.update(ctx.get('params', {}))
    previous = ctx.get('memory', {})
    orders = ctx.get('open_orders', [])
    buy_cancels = [order['order_id'] for order in orders
                   if order.get('side') == 'buy' and order.get('order_id')]
    now = stamp(ctx.get('now'))
    memory = {}
    result = {'intents': [], 'cancels': [], 'thought': '', 'memory': memory}
    if now is None:
        result['cancels'] = buy_cancels[:20]
        result['thought'] = 'The decision clock is unavailable; cancel resting entries.'
        return result

    memory['last_refusal'] = previous.get('last_refusal', '')
    memory['cool_until'] = number(previous.get('cool_until')) or 0.0
    for outcome in reversed(ctx.get('recent_order_outcomes', [])):
        if outcome.get('status') != 'refused':
            continue
        fingerprint = json.dumps(outcome, sort_keys=True, separators=(',', ':'))[-700:]
        if fingerprint != memory['last_refusal']:
            memory['last_refusal'] = fingerprint
            memory['cool_until'] = now + 1800.0
        break

    holdings = [position for position in ctx.get('positions', [])
                if (number(position.get('quantity')) or 0.0) > 0.0]
    if holdings:
        result['cancels'] = buy_cancels[:20]
        result['thought'] = 'An exposure is already held for settlement; cancel entries and do not add to it.'
        return result
    if now < memory['cool_until']:
        result['cancels'] = buy_cancels[:20]
        result['thought'] = 'A recent order refusal triggered a thirty-minute entry cooldown.'
        return result

    rate = max(0.07, number(ctx.get('fees', {}).get('kalshi_taker_rate')) or 0.07)
    diagnostics = {'usable_rows': 0, 'ladders': 0, 'dislocations': 0}
    candidates = collect_candidates(ctx, params, rate, diagnostics)
    memory['diagnostics'] = diagnostics

    if orders:
        current = {(item['market'], item['leg']): item for item in candidates}
        cancels = []
        for order in orders:
            if order.get('side') != 'buy' or not order.get('order_id'):
                continue
            candidate = current.get((order.get('market'), order.get('leg')))
            submitted = stamp(order.get('submitted_at'))
            price = number(order.get('limit_price'))
            valid = candidate is not None and submitted is not None and price is not None
            if valid:
                valid = 0.0 <= now - submitted < 600.0
                valid = valid and params['bid_min'] <= price <= candidate['price'] + 0.00000001
            if not valid:
                cancels.append(order['order_id'])
        result['cancels'] = cancels[:20]
        result['thought'] = 'Manage existing orders before any replacement; cancel expired or invalid ladder bids.'
        return result

    selected = None
    quantity = 0
    for candidate in candidates:
        quantity = entry_quantity(ctx, candidate, params)
        if quantity > 0:
            selected = candidate
            break
    if selected is None:
        result['thought'] = 'No coherent same-player ladder discount clears both the fee reserve and the available entry budget.'
        return result

    last_seen = number(previous.get('last_seen'))
    first_seen = number(previous.get('first_seen'))
    continuous = previous.get('candidate') == selected['key']
    continuous = continuous and last_seen is not None and first_seen is not None
    if continuous:
        continuous = 0.0 <= now - last_seen <= 900.0 and first_seen <= last_seen
    if not continuous:
        first_seen = now
    memory['candidate'] = selected['key']
    memory['first_seen'] = first_seen
    memory['last_seen'] = now
    if not continuous or now <= last_seen or now - first_seen < 240.0:
        result['thought'] = 'A ladder discount is present; wait for a separate observation before risking a maker fill.'
        return result

    result['intents'] = [{
        'market': selected['market'], 'leg': selected['leg'], 'side': 'buy',
        'quantity': quantity, 'type': 'limit', 'limit_price': selected['price'],
        'post_only': True,
        'reason': 'Persistent same-player ladder discount versus stricter ' + selected['reference']
                  + '; full-taker fee reserved, one exposure held to settlement, not a locked arbitrage.'
    }]
    result['thought'] = 'The same-player discount persisted across observations; submit one fee-reserved passive entry.'
    return result
