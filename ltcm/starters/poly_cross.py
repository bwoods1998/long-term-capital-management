"""House starter (the arena, Sept 18, 2026): price Kalshi event contracts against Polymarket.

Two liquid books on the same question rarely disagree by more than the fees; when they do, the
cheaper side on Kalshi is a bet that the two converge by settlement. Every run: the busiest
Polymarket markets (`kit.polymarket`) are matched to Kalshi's open single markets settling within
`max_hours` by the words, numbers and dates of their titles (every number in the Kalshi title must
appear in the Polymarket question, at least `min_overlap` of its words must, and the two must end
within `max_day_gap` days of each other). For a match, Polymarket's YES price is the reference:
buy Kalshi's YES when it is `min_edge` cheaper after the taker fee, its NO when the complement is.
`maker` rests a bid a cent over the best bid instead of taking the ask. One position an event,
`max_new` a run, held to settlement. Matching by title is the weak point: the rationale names the
Polymarket question so a wrong match is visible on the tape, and the record decides size.

Params: min_edge, maker, min_volume_24h, max_hours, pages, poly_limit, min_overlap, max_day_gap,
min_words, notional_usd, max_new, yes_min, yes_max, exclude_prefixes.
"""

import math
import re
from datetime import datetime, timezone

DEFAULTS = {
    "min_edge": 0.04,
    "maker": False,
    "min_volume_24h": 5000,
    "max_hours": 120,
    "pages": 6,
    "poly_limit": 100,
    "min_overlap": 0.6,
    "max_day_gap": 2,
    "min_words": 3,
    "notional_usd": None,
    "max_new": 3,
    "yes_min": 0.03,
    "yes_max": 0.97,
    "exclude_prefixes": ["KXMVE", "KXHIGH", "KXLOW"],
}
STOP = {"will", "the", "and", "for", "with", "this", "that", "than", "from", "into", "over", "under", "above", "below", "before", "after",
        "does", "did", "who", "what", "which", "when", "where", "how", "any", "all", "one", "two", "yes", "was", "are", "has", "have", "been",
        "its", "their", "there", "market", "resolve", "resolves", "price", "close", "between", "more", "less", "least", "most", "day", "end",
        "week", "month", "year", "per", "win", "wins", "beat", "beats", "game", "match", "out", "off", "not", "new", "next", "first", "last"}
WORD = re.compile(r"[a-z][a-z']{1,}")
NUMBER = re.compile(r"\$?(\d[\d,]*\.?\d*)\s*([kKmMbB])?")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _num(value, default=None):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _when(text):
    try:
        return datetime.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _fee(price):
    return math.ceil(round(0.07 * price * (1.0 - price) * 10000.0, 6)) / 10000.0


def numbers(text):
    """The numbers in a title, scaled ('80k' -> 80000) and rounded to whole units."""
    out = set()
    for raw, suffix in NUMBER.findall(str(text or "")):
        value = _num(raw)
        if value is None:
            continue
        value *= {"k": 1e3, "m": 1e6, "b": 1e9}.get((suffix or "").lower(), 1.0)
        out.add(round(value, 2))
    return out


def words(text):
    return {w for w in WORD.findall(str(text or "").lower()) if w not in STOP and w not in MONTHS}


def yes_price(row):
    outcomes = [str(x).strip().lower() for x in (row.get("outcomes") or [])]
    prices = [_num(x) for x in (row.get("prices") or [])]
    if "yes" in outcomes and len(prices) > outcomes.index("yes"):
        return prices[outcomes.index("yes")]
    if len(prices) == 2 and prices[0] is not None:
        return prices[0]
    return None


def match(kalshi, poly_rows, p):
    """The best Polymarket row for one Kalshi market, or None."""
    title = f"{kalshi.get('title') or ''} {kalshi.get('yes_sub_title') or ''}"
    kw, kn = words(title), numbers(title)
    if len(kw) < int(p["min_words"]):
        return None
    close = _when(kalshi.get("close_time"))
    best, best_score = None, 0.0
    for row in poly_rows:
        question = str(row.get("question") or "")
        pw = words(question)
        if not pw:
            continue
        overlap = len(kw & pw) / float(len(kw))
        if overlap < float(p["min_overlap"]):
            continue
        if kn and not kn <= numbers(question):
            continue
        end = _when(str(row.get("end_date") or "").replace("Z", ""))
        if close is not None and end is not None and abs((end - close).total_seconds()) > float(p["max_day_gap"]) * 86400.0:
            continue
        if yes_price(row) is None:
            continue
        if overlap > best_score:
            best, best_score = row, overlap
    return (best, best_score) if best is not None else None


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    held = {str(x.get("market_id")) for x in (ctx.get("positions") or [])}
    held_events = {"-".join(m.split("-")[:2]) for m in held}
    working = {str(x.get("market_id")) for x in (ctx.get("open_orders") or [])}
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    try:
        poly = kit.polymarket("", int(p["poly_limit"])) or []
    except Exception as exc:
        kit.say(f"polymarket failed ({type(exc).__name__})")
        return {"intents": [], "notes": "no Polymarket page"}
    board = kit.kalshi_markets(max_close_hours=float(p["max_hours"]), pages=int(p["pages"])) or []
    excluded = tuple(str(x) for x in (p.get("exclude_prefixes") or []))
    matched = []
    for market in board:
        ticker = str(market.get("ticker") or "")
        if not ticker or ticker.startswith(excluded) or ticker in held or ticker in working or "-".join(ticker.split("-")[:2]) in held_events:
            continue
        if (_num(market.get("volume_24h"), 0) or 0) < float(p["min_volume_24h"]):
            continue
        yes = _num(market.get("yes_ask"))
        if yes is None or yes < float(p["yes_min"]) or yes > float(p["yes_max"]):
            continue
        found = match(market, poly, p)
        if found is None:
            continue
        row, score = found
        matched.append((ticker, market, row, score))
    kit.say(f"{len(board)} Kalshi markets, {len(poly)} Polymarket rows, {len(matched)} matched")
    books = kit.kalshi_orderbooks([t for t, _, _, _ in matched[:100]]) if matched else {}
    candidates = []
    for ticker, market, row, score in matched:
        book = books.get(ticker) or {}
        yes_ask = _num(book.get("yes_ask")) or _num(market.get("yes_ask"))
        yes_bid = _num(book.get("yes_bid")) if _num(book.get("yes_bid")) is not None else _num(market.get("yes_bid"))
        if yes_ask is None or yes_bid is None or yes_ask <= 0 or yes_ask >= 1:
            continue
        ref = yes_price(row)
        no_ask, no_bid = 1.0 - yes_bid, 1.0 - yes_ask
        if p.get("maker"):
            yes_px, no_px = min(yes_ask - 0.01, yes_bid + 0.01), min(no_ask - 0.01, no_bid + 0.01)
            edge_yes, edge_no = ref - yes_px, (1.0 - ref) - no_px
        else:
            yes_px, no_px = yes_ask, no_ask
            edge_yes, edge_no = ref - yes_ask - _fee(yes_ask), (1.0 - ref) - no_ask - _fee(no_ask)
        side, price, edge = ("yes", yes_px, edge_yes) if edge_yes >= edge_no else ("no", no_px, edge_no)
        if edge < float(p["min_edge"]) or price < 0.02 or price > 0.98:
            continue
        close = _when(market.get("close_time"))
        hours = (close - now).total_seconds() / 3600.0 if close else float(p["max_hours"])
        candidates.append((edge, ticker, side, price, ref, yes_ask, yes_bid, score, row, hours, str(market.get("title") or "")))
    candidates.sort(key=lambda c: -c[0])
    intents, events = [], set()
    for edge, ticker, side, price, ref, yes_ask, yes_bid, score, row, hours, title in candidates:
        event = "-".join(ticker.split("-")[:2])
        if event in events:
            continue
        events.add(event)
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": side},
                "side": "buy",
                "quantity": str(max(1, int(notional / price))),
                "order_type": "limit",
                "limit_price": f"{price:.2f}",
                **({"post_only": True} if p.get("maker") else {}),
                "rationale": (
                    f"Cross-venue: Polymarket prices \"{str(row.get('question') or '')[:90]}\" at {ref:.2f} YES (${_num(row.get('volume_24h'), 0):,.0f} today); "
                    f"Kalshi's \"{title[:80]}\" quotes {yes_bid:.2f}/{yes_ask:.2f}. {side.upper()} at {price:.2f} has {edge:.3f} of edge "
                    f"{'as a maker' if p.get('maker') else 'after fees'} (title match {score:.2f}). Holds to settlement in {hours:.0f}h."
                ),
                "holding_period_hours": max(1, int(hours) + 1),
            }
        )
        if len(intents) >= int(p["max_new"]):
            break
    return {"intents": intents, "notes": f"{len(matched)} matched across venues, {len(candidates)} with edge >= {p['min_edge']}, {len(intents)} proposed"}
