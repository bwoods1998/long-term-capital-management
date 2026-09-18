"""House starter for the Kalshi events family: rest maker bids on the favorite (NO) side of
liquid markets in every category, where the longshot is overpriced: a few-cent contract resolves
YES less often than its price says (Bürgi, Deng and Whelan, "Makers and Takers: The Economics of
the Kalshi Prediction Market", 2025). The edge is a few cents, which a taker's fee would eat.

Every run: open single markets settling in `min_hours`..`max_hours` with the YES ask in
`yes_min`..`yes_max` and `min_volume_24h` traded today get a post-only NO bid a cent over the
best NO bid, never at the NO ask, at learning size. One position per event, `max_open_per_series`
per series, `max_new` a run; a bid older than `requote_seconds` is replaced. Held to settlement.
`maker` false takes the NO ask; `no_max` caps the price (a 99-cent bid risks 99 to make one).
Version 2 (Sept 17, 2026; rules and evidence in ltcm/README.md), each off until set so an unset
desk trades as before: book_pricing, max_open_per_cluster, expire_seconds, keep_queue, band_exit.
Version 3 (Sept 17, 2026 evening): the code reads the family's pooled evidence the floor hands it
in `kit.context["evidence"]["kalshi_favorites"]` (`Strategies.family_record`): the settled record
of this strategy on every desk of the family, split by market group. A group whose record has
reached the settlements the gate asks for and is net negative is skipped (`learn_groups`, on by
default; `explore_losing` keeps betting there, for a shadow variant that tests the verdict), and
candidates in groups that pass the gate are placed first. Without evidence in the context the
code behaves exactly as version 2.
"""

import math
from datetime import datetime, timedelta, timezone

# Set from a 14-day study of 14,000 settled Kalshi markets (Sept 2-16, 2026): below 5 cents
# the maker's fills are adverse and the edge vanishes; with a 10,000-contract daily volume floor
# and 24 hours to close, maker NO bids returned +3.6% per dollar [+0.9, +5.9] with a trade-based
# fill model, though a walk-forward test was mixed. Learning size until live fills confirm it.
DEFAULTS = {
    "yes_min": 0.05,
    "yes_max": 0.10,
    "min_hours": 1.0,
    "max_hours": 24.0,
    "min_volume_24h": 10000,
    "max_new": 5,
    "max_open_per_series": 2,
    "requote_seconds": 1800,
    "maker": True,
    "no_max": 0.96,
    "exclude_prefixes": ["KXMVE"],
    "pages": 8,
    "notional_usd": None,
    "book_pricing": False, "max_open_per_cluster": 3, "expire_seconds": None, "keep_queue": False, "band_exit": False,
    "learn_groups": True, "explore_losing": False,
    # Avoiding needs less evidence than trusting (Sept 18, 2026: the crypto brackets' pooled
    # record read 22 settled, 9 losses, -$25 while the live books kept buying them at 0.93-0.95
    # because the gate's count for a favorite is ~43). A group net negative after `avoid_min_n`
    # settlements is skipped; passing still needs the gate. `max_open_per_cluster` caps the bets
    # that fail together (same group, same close hour) at 3.
    "avoid_min_n": 15,
}
GROUPS = {"crypto": ("KXBTC", "KXETH", "KXSOL", "KXXRP", "KXDOGE"), "commod": ("KXGOLD", "KXSILVER", "KXBRENT", "KXWTI", "KXCOPPER"), "weather": ("KXHIGH",)}


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
    """Kalshi's taker fee on one contract: 0.07 x P x (1 - P), rounded up to $0.0001.

    Sept 17, 2026: the venue charges fees to the $0.0001, not the cent. Rounded to the cent this
    said a NO taken at 0.93 cost a full cent a contract when it costs $0.0046."""
    return math.ceil(round(0.07 * price * (1.0 - price) * 10000.0, 6)) / 10000.0


def _event(ticker):
    return "-".join(str(ticker or "").split("-")[:2])


def _series(ticker):
    return str(ticker or "").split("-")[0]


def _cluster(ticker, close):
    """(group, close hour): bets that fail together."""
    series = _series(ticker).upper()
    group = next((name for name, roots in GROUPS.items() if series.startswith(roots)), series)
    return group, (close.strftime("%Y-%m-%dT%H") if close is not None else None)


def _tick(ranges, no_price):
    """The step of the `price_ranges` band holding a NO price (bands are on the YES scale)."""
    for band in ranges if isinstance(ranges, list) else []:
        start, end, step = (_num(band.get(k + "_dollars", band.get(k))) for k in ("start", "end", "step"))
        if start is not None and end and step and start - 1e-9 <= 1.0 - no_price <= end + 1e-9:
            return step
    return 0.01


def _text(price, tick):
    return f"{price:.2f}" if tick >= 0.00999 else f"{price:.4f}"


def _touch(book):
    """(best NO bid, best YES bid or None), whatever order the levels arrive in."""
    best = []
    for side in ("no", "yes"):
        prices = [_num(x[0]) for x in book.get(side) or [] if x] + [_num(book.get(side + "_bid"))]
        best.append(max([x for x in prices if x and 0.0 < x < 1.0] or [None]))
    return tuple(best) if best[0] else None


def _tally(items):
    return ", ".join(f"{items.count(k)} {k}" for k in sorted(set(items))) or "none"


def _evidence_group(series, evidence):
    """The pooled-evidence group of a series: the floor's series map first, then its prefix
    table, then the series itself (unknown to the record, so never judged)."""
    root = str(series or "").upper()
    known = (evidence.get("series_groups") or {}).get(root)
    if known:
        return str(known)
    for group, prefixes in (evidence.get("group_prefixes") or {}).items():
        if root.startswith(tuple(str(x).upper() for x in prefixes)):
            return str(group)
    return root


def _rank_by_evidence(candidates, evidence, explore_losing, avoid_min_n=15):
    """(kept candidates in evidence order, skipped tickers, verdict tally). A group net
    negative after `avoid_min_n` settlements is skipped (avoiding needs less evidence than
    trusting); a passing group goes first once it has the settlements the gate asked for; the
    rest keep their volume order."""
    groups = evidence.get("groups") or {}
    kept, skipped, tally = [], [], []
    for cand in candidates:
        verdict = groups.get(_evidence_group(_series(cand[1]), evidence)) or {}
        n, need = _num(verdict.get("n"), 0) or 0, _num(verdict.get("n_needed"), 0) or 0
        pnl = _num(verdict.get("settled_pnl_usd"))
        judged = bool(verdict) and need > 0 and n >= need
        avoid = bool(verdict) and n >= float(avoid_min_n or 0) and avoid_min_n
        if (judged or avoid) and pnl is not None and pnl < 0 and not verdict.get("passes"):
            tally.append("losing group")
            if not explore_losing:
                skipped.append(cand[1])
                continue
        if verdict.get("passes"):
            tally.append("passing group")
            order = (0, -(_num(verdict.get("lower"), 0.0) or 0.0))
        elif judged:
            tally.append("judged, unproven")
            order = (2, 0.0)
        else:
            tally.append("unjudged")
            order = (1, 0.0)
        kept.append((order, len(kept), cand))
    kept.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in kept], skipped, tally


def decide(kit, params):
    p = {**DEFAULTS, **(params or {})}
    ctx = kit.context or {}
    now = _when(ctx.get("now")) or datetime.now(timezone.utc)
    notional = _num(p.get("notional_usd")) or _num(ctx.get("learning_usd"), 10.0)
    use_book, keep_queue, band_exit, cap = bool(p.get("book_pricing")), bool(p.get("keep_queue")), bool(p.get("band_exit")), p.get("max_open_per_cluster")
    expire = max(0.0, _num(p.get("expire_seconds"), 0.0) or 0.0)
    v2 = use_book or keep_queue or band_exit or cap is not None or expire > 0
    min_hours, yes_min, yes_max, series_cap = float(p["min_hours"]), float(p["yes_min"]), float(p["yes_max"]), int(p["max_open_per_series"])
    # The floor's clock (Sept 18, 2026): `kit.context["max_holding_hours"]` is the longest a
    # settlement may be away on this floor (12 hours: a result within the trading day, so the
    # record, the size ramp and the avoid rule turn over daily); the params never exceed it.
    horizon = _num((kit.context or {}).get("max_holding_hours"))
    if horizon and horizon > 0:
        p["max_hours"] = min(float(p["max_hours"]), horizon)
    held_events, per_series, held = set(), {}, set()
    for x in ctx.get("positions") or []:
        ticker = str(x.get("market_id") or x.get("symbol") or "")
        if str(x.get("asset_class") or "event") != "event" or not ticker:
            continue
        held.add(ticker)
        held_events.add(_event(ticker))
        per_series[_series(ticker)] = per_series.get(_series(ticker), 0) + 1
    resting = [o for o in (ctx.get("open_orders") or []) if o.get("strategy") == "kalshi_favorites"]
    try:
        markets = kit.kalshi_markets(max_close_hours=float(p["max_hours"]), pages=int(p["pages"]))
    except Exception as exc:
        kit.say(f"market listing failed: {type(exc).__name__}")
        markets = []
    excluded = tuple(str(x) for x in (p.get("exclude_prefixes") or []))
    rows = {str(m.get("ticker") or ""): m for m in markets} if v2 else {}
    candidates = []
    for market in markets:
        ticker = str(market.get("ticker") or "")
        if not ticker or ticker in held or (excluded and ticker.startswith(excluded)):
            continue
        if str(market.get("status") or "open") not in ("open", "active"):
            continue
        close = _when(market.get("close_time"))
        if close is None:
            continue
        hours = (close - now).total_seconds() / 3600.0
        if not min_hours <= hours <= float(p["max_hours"]):
            continue
        yes_ask, yes_bid = _num(market.get("yes_ask")), _num(market.get("yes_bid"))
        volume = _num(market.get("volume_24h"), 0.0) or 0.0
        if yes_ask is None or yes_bid is None or volume < float(p["min_volume_24h"]):
            continue
        if not yes_min <= yes_ask <= yes_max:
            continue
        candidates.append((volume, ticker, market, hours, yes_ask, yes_bid))
    candidates.sort(key=lambda c: -c[0])
    evidence = (ctx.get("evidence") or {}).get("kalshi_favorites") or {}
    learned = None
    if p.get("learn_groups", True) and evidence.get("groups"):
        candidates, dropped, learned = _rank_by_evidence(candidates, evidence, bool(p.get("explore_losing")), _num(p.get("avoid_min_n"), 15))
    books, skipped, why = {}, [], []
    if use_book or keep_queue or band_exit:
        # Resting bids' books first, then the band's candidates by volume; the kit reads 300 a run.
        wanted = [o.get("market_id") for o in resting if keep_queue or band_exit] + [c[1] for c in candidates if use_book and _event(c[1]) not in held_events]
        try:
            books = kit.kalshi_orderbooks(list(dict.fromkeys(t for t in wanted if t))[:300]) or {}
        except Exception as exc:
            kit.say(f"order books failed: {type(exc).__name__}")
    cancels, kept, kept_tickers = [], set(), []
    for order in resting:
        placed = _when(order.get("submitted_at"))
        age = (now - placed).total_seconds() if placed else 0.0
        ticker = str(order.get("market_id") or "")
        reason = "duplicate" if _event(ticker) in kept else ("stale" if age > float(p["requote_seconds"]) else None)
        if v2 and reason != "duplicate":
            row = rows.get(ticker) or {}
            close, touch, price = _when(row.get("close_time")), _touch(books.get(ticker) or {}), _num(order.get("limit_price"))
            # keep_queue must not keep what v1's requote pulled: a stale bid into the final window.
            if (expire > 0 or keep_queue and reason) and close is not None and (close - now).total_seconds() <= min_hours * 3600.0:
                reason = "final window"
            elif band_exit and touch and touch[1] is not None and touch[1] >= yes_max + 0.02 - 1e-9:
                reason = "band exit"
            elif keep_queue and touch and price is not None:
                behind = round((touch[0] - price) / _tick(row.get("price_ranges"), price))
                reason = "behind" if behind >= 2 else (reason if behind >= 1 else None)
        if reason:
            why.append(reason)
            if order.get("order_id"):
                cancels.append(order["order_id"])
            continue
        kept.add(_event(ticker))
        kept_tickers.append(ticker)
        per_series[_series(ticker)] = per_series.get(_series(ticker), 0) + 1
    clusters, unknown, lookups = {}, {}, 0
    for ticker in sorted(held) + kept_tickers if cap is not None else []:
        close = _when((rows.get(ticker) or {}).get("close_time"))
        if close is None and lookups < 10:
            lookups += 1
            try:
                close = _when((kit.kalshi_market(ticker) or {}).get("close_time"))
            except Exception:
                pass
        group, hour = _cluster(ticker, close)
        # A close that cannot be read counts against every hour of its group.
        (clusters.setdefault((group, hour), set()) if hour else unknown.setdefault(group, set())).add(ticker)
    intents, joined, places = [], 0, 4 if use_book else 2
    for volume, ticker, market, hours, yes_ask, yes_bid in candidates:
        if len(intents) >= int(p["max_new"]):
            break
        event, series = _event(ticker), _series(ticker)
        if event in held_events or event in kept or per_series.get(series, 0) >= series_cap:
            continue
        close = _when(market.get("close_time"))
        cluster = _cluster(ticker, close)
        if cap is not None and len(clusters.get(cluster, set()) | unknown.get(cluster[0], set())) >= float(cap):
            skipped.append("cluster cap")
            continue
        tick, no_bid, no_ask = 0.01, 1.0 - yes_ask, 1.0 - yes_bid
        if use_book:
            touch = _touch(books.get(ticker) or {})
            if touch is None:
                skipped.append("no book")
                continue
            no_bid, no_ask, yes_ask = touch[0], 1.0 - (touch[1] or 0.0), 1.0 - touch[0]  # no YES bid: a NO ask of 1.00, as the row shows
            if no_bid >= no_ask - 1e-9 or not yes_min - 1e-9 <= yes_ask <= yes_max + 1e-9:
                skipped.append("book crossed or out of band")
                continue
            tick = _tick(market.get("price_ranges"), no_bid)
        if p.get("maker", True):
            price = round(min(no_bid + tick, no_ask - tick), places)
            if price < no_bid - 1e-9 or price >= no_ask - 1e-9:
                skipped.append("no room inside the spread")
                continue  # never under the best bid, never at the ask; a one-tick spread joins the bid
            joined += price <= no_bid + 1e-9
            where = f"on the live book (NO {_text(no_bid, tick)}/{_text(no_ask, tick)})" if use_book else "a cent over the best NO bid"
            how = f"resting a post-only NO bid at {_text(price, tick)}, {where}, as a maker (no fee)"
        else:
            price = round(no_ask, places)
            if price >= 0.99:
                continue
            how = f"taking the NO ask at {_text(price, tick)} (fee {_fee(price):.4f} a contract)"
        if price > float(p.get("no_max") or 0.98):
            continue
        expires = None
        if expire > 0:
            expires = min(now + timedelta(seconds=expire), close - timedelta(hours=min_hours))
            if (expires - now).total_seconds() < 120:
                skipped.append("final window")
                continue
            how += f", expiring {expires.strftime('%H:%MZ')}"
        quantity = max(1, int(notional / price))
        intents.append(
            {
                "instrument": {"asset_class": "event", "symbol": ticker, "market_id": ticker, "right": "no"},
                "side": "buy",
                "quantity": str(quantity),
                "order_type": "limit",
                "limit_price": _text(price, tick),
                **({"post_only": True} if p.get("maker", True) else {}),
                **({"expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ")} if expires else {}),
                "rationale": (
                    f"Favorite: {ticker} ({str(market.get('title') or '')[:80]}) has YES at {yes_ask:.2f} with "
                    f"{volume:,.0f} contracts traded today and settles in {hours:.0f}h. Kalshi longshots resolve YES less "
                    f"often than their price implies (Bürgi, Deng and Whelan 2025), so the NO side is the favorite with the "
                    f"edge; {how}. One position per event. Holds to settlement; wrong if this band's settled NO record "
                    f"returns less than the fees it saved."
                ),
                "holding_period_hours": max(1, int(hours) + 1),
            }
        )
        held_events.add(event)
        per_series[series] = per_series.get(series, 0) + 1
        clusters.setdefault(cluster, set()).add(ticker)
    kit.say(f"{len(markets)} markets listed, {len(candidates)} in the band, {len(intents)} bid(s), {len(cancels)} requoted")
    if learned is not None:
        kit.say(f"family evidence over {evidence.get('n', 0)} settled on {evidence.get('desks', 0)} desk(s): {_tally(learned)}; skipped {len(dropped)} in losing groups")
    if v2:
        kit.say(f"{len(books)} book(s) read, {joined} bid(s) joined the best NO bid; skipped: {_tally(skipped)}; cancelled: {_tally(why)}")
    return {"intents": intents, "cancels": cancels, "notes": f"{len(candidates)} favorites in band, {len(intents)} placed, {len(cancels)} cancelled"}
