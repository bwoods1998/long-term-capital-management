from datetime import datetime
from decimal import Decimal
import re

NEEDS = {'venue': 'kalshi', 'horizon': 'day', 'style': 'late-pregame-strikeout-no-maker', 'series': ['KXMLBKS'], 'max_hours_to_close': 12, 'wake_minutes': 30, 'parameter_rules': {'bounds': {'min_hours': [0.0, 12.0], 'max_hours': [1.0, 48.0], 'yes_floor': [0.20, 0.90], 'yes_ceiling': [0.30, 0.98], 'max_spread': [0.01, 0.20], 'min_volume': [1, 10000], 'notional_usd': [1.0, 25.0], 'max_open': [1, 8], 'stale_minutes': [15, 180]}, 'ordered': [['min_hours', 'max_hours'], ['yes_floor', 'yes_ceiling']]}}
PARAMS = {'max_hours': 3.907668, 'max_open': 3, 'max_spread': 0.062729, 'min_hours': 1.0, 'min_volume': 40, 'notional_usd': 14.211247, 'stale_minutes': 45, 'yes_ceiling': 0.9, 'yes_floor': 0.512115}


def n(x, d=0):
    try:
        y = float(x)
        return y if y == y and abs(y) < 1e100 else d
    except (TypeError, ValueError):
        return d


def decide(ctx):
    p = dict(PARAMS)
    p.update(ctx.get('params') or {})
    orders = ctx.get('open_orders') or []
    busy = {str(x.get('market')) for x in (ctx.get('positions') or []) + orders}
    cancel = []
    for o in orders:
        if o.get('side') == 'buy' and o.get('order_id'):
            try:
                age = (datetime.fromisoformat(str(ctx['now']).replace('Z', '+00:00')) - datetime.fromisoformat(str(o['submitted_at']).replace('Z', '+00:00'))).total_seconds() / 60
                if age > p['stale_minutes']:
                    cancel.append(o['order_id'])
            except (ValueError, TypeError, KeyError):
                pass

    entry_floor = Decimal('0.30') if n(ctx.get('rung')) >= 2 else Decimal('0.15')
    rows = []
    for m in ctx.get('markets') or []:
        t = m.get('market')
        if not isinstance(t, str) or re.fullmatch(r'KXMLBKS-[A-Z0-9]+(?:-[A-Z0-9]+(?:\.[0-9]+)?)*', t) is None:
            continue
        b = n(m.get('yes_bid'), -1)
        a = n(m.get('yes_ask'), 2)
        h = n(m.get('hours_to_close'), -1)
        if 0 < b < a < 1 and p['yes_floor'] <= b and a <= p['yes_ceiling'] and a - b <= p['max_spread'] and p['min_hours'] <= h <= p['max_hours'] and n(m.get('volume_24h')) >= p['min_volume']:
            # Check the leg actually bought, without lifting an inadmissible bid.
            price = Decimal('1') - Decimal(str(a))
            if price >= entry_floor:
                rows.append((h, t, float(price)))
    rows.sort()
    lim = ctx.get('limits') or {}
    cash = max(0, n(ctx.get('cash')) - sum(n(o.get('quantity')) * n(o.get('limit_price')) for o in orders if o.get('side') == 'buy'))
    cap = min(p['notional_usd'], n(lim.get('max_order_usd'), 10), n(lim.get('max_position_usd'), 10))
    out = []
    for h, t, price in rows:
        if len(out) >= max(0, min(8, p['max_open'] - len(busy))) or t in busy:
            continue
        q = int(min(cash, cap) / price) if price > 0 else 0
        if q:
            out.append({'market': t, 'leg': 'no', 'side': 'buy', 'quantity': q, 'type': 'limit', 'limit_price': price, 'post_only': True, 'reason': 'Late-pregame NO maker entry above the applicable longshot floor; avoid maintaining a bid into live play.'})
            cash -= q * price
            busy.add(t)
    return {'intents': out, 'cancels': cancel, 'thought': 'Only considers the short pregame window and NO bids meeting the applicable longshot floor; all entries rest post-only.', 'memory': {}}
