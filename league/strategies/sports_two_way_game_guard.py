# Child of meriwether-20, family sports-favorites.
# Reserve CFB/NFL exposure by game, not by its opposing outcome tickers.
NEEDS = {
    'venue': 'kalshi',
    'horizon': 'day',
    'style': 'favorites-anywhere',
    'series': ['KXNCAAFGAME', 'KXNFLGAME', 'KXEPLGAME', 'KXLALIGAGAME',
               'KXSERIEAGAME', 'KXBUNDESLIGAGAME', 'KXLIGUE1GAME',
               'KXLIGAMXGAME', 'KXLIGAPORTUGALGAME', 'KXBRASILEIROGAME',
               'KXARGPREMDIVGAME', 'KXMLSGAME'],
    'max_hours_to_close': 30,
    'wake_minutes': 30,
}

PARAMS = {
    'bid_min': 0.9,
    'bid_max': 0.97,
    'no_bid_min': 0.88,
    'underdog_ask_max': 0.140162,
    'max_spread': 0.03,
    'min_hours': 7.0,
    'max_hours': 30.0,
    'min_volume_24h': 5000,
    'notional_usd': 9.19668,
    'max_open': 5,
}
EPS = 1e-9
MAX_MARKET_SHARE = 0.30
TWO_WAY = ('KXNCAAFGAME', 'KXNFLGAME')


def _num(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float('inf') else default


def _touch(market):
    bid, ask = _num(market.get('yes_bid')), _num(market.get('yes_ask'))
    if bid is None or ask is None or not 0.0 < bid < ask < 1.0:
        return None
    return round(bid, 4), round(ask, 4)


def _entry_key(ticker):
    parts = str(ticker).split('-')
    if parts[0] in TWO_WAY:
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return None
        return parts[0] + '-' + parts[1]
    return str(ticker)


def decide(ctx):
    p = {**PARAMS, **(ctx.get('params') or {})}
    knob = lambda name: _num(p.get(name), float(PARAMS[name]))
    markets = [m for m in ctx.get('markets') or [] if isinstance(m, dict) and m.get('market')]
    positions = [x for x in ctx.get('positions') or [] if isinstance(x, dict) and (_num(x.get('quantity'), 0.0) or 0.0) > 0]
    orders = [o for o in ctx.get('open_orders') or [] if isinstance(o, dict)]
    busy = {_entry_key(x.get('market')) for x in positions} | {_entry_key(o.get('market')) for o in orders}
    # An unparseable existing football exposure cannot safely be matched to a game.
    unknown_game = None in busy
    initial_busy = len(busy)

    bid_min, bid_max = knob('bid_min'), knob('bid_max')
    no_bid_min, underdog_ask_max = knob('no_bid_min'), knob('underdog_ask_max')
    found = []
    for market in markets:
        ticker = str(market['market'])
        key = _entry_key(ticker)
        if key is None:
            continue
        if unknown_game and ticker.split('-')[0] in TWO_WAY:
            continue
        touch = _touch(market)
        hours, volume = _num(market.get('hours_to_close')), _num(market.get('volume_24h'), 0.0)
        if touch is None or hours is None:
            continue
        yes_bid, yes_ask = touch
        spread = yes_ask - yes_bid
        if not knob('min_hours') <= hours <= knob('max_hours') or volume < knob('min_volume_24h'):
            continue
        if spread > knob('max_spread') + EPS:
            continue
        if bid_min - EPS <= yes_ask <= bid_max + EPS:
            found.append((-volume, ticker, 'yes', yes_ask, hours))
            continue
        no_ask = round(1.0 - yes_bid, 4)
        if yes_ask <= underdog_ask_max + EPS and no_bid_min - EPS <= no_ask <= bid_max + EPS:
            found.append((-volume, ticker, 'no', no_ask, hours))
    found.sort()

    limits = ctx.get('limits') or {}
    want = knob('notional_usd')
    free = _num(ctx.get('cash'), 0.0) * 0.98
    per_market = min(want, _num(limits.get('max_order_usd'), want), _num(limits.get('max_position_usd'), want))
    equity = _num(ctx.get('equity'))
    if equity is not None and equity > 0:
        per_market = min(per_market, MAX_MARKET_SHARE * equity)
    slots = min(int(knob('max_open')) - len(busy), 8)

    intents = []
    for minus_volume, ticker, leg, price, hours in found:
        if len(intents) >= slots:
            break
        key = _entry_key(ticker)
        if key in busy:
            continue
        quantity = int(min(per_market, free) / price + EPS)
        if quantity < 1 or quantity * price < 1.0:
            continue
        free -= quantity * price
        intents.append({
            'market': ticker, 'leg': leg, 'side': 'buy', 'quantity': quantity,
            'type': 'limit', 'limit_price': price,
            'reason': (f'Marketable {leg.upper()} buy of {quantity} at {price:.2f} on {ticker}: '
                       f'deep-favourite entry, {hours:.1f}h to close, {-minus_volume:.0f} contracts today. '
                       'Held to settlement; two-way football exposure reserved by game.'),
        })
        busy.add(key)

    thought = (f'Saw {len(markets)} moneyline markets, {len(found)} qualifying deep favourites. '
               f'Selected {len(intents)} marketable buys; {initial_busy} exposure slots already occupied, '
               'with CFB/NFL counted by game.')
    return {'intents': intents, 'cancels': [], 'thought': thought, 'memory': {}}
