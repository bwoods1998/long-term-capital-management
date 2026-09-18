"""Strategies: code a desk deploys to trade for it between sessions (leap: strategies).

A model session is slow, expensive and cautious: on the floor's first day 49 sessions produced
three orders. A strategy is the desk's judgement written down as code and run by the floor
every few minutes in the desk's own sandbox, so the decisions a recursive loop needs arrive by
the hundred at the price of a few sandbox seconds, and the desk's sessions become what they
should be: building, measuring and improving the code that trades.

The contract a strategy honours, in `toolbox/<name>.py`:

    def decide(kit, params) -> list[dict]:
        ...

`kit` reads public data (`kit.bars`, `kit.quote`, `kit.kalshi_series`, `kit.kalshi_market`) and
carries `kit.context` (the clock, the desk's positions, its learning size). Each dict returned is
a `propose_order` call: `instrument`, `side`, `quantity`, `order_type` (limit only),
`limit_price`, `rationale`, and optionally `post_only`, `target_price`, `stop_price`,
`holding_period_hours`, and a venue-side expiry as `expires_at` (an ISO-8601 UTC stamp, clamped
to 120 s..48 h after the run's clock) or `expire_after_seconds`. The floor proposes them exactly
as the desk would in a session -- the same risk engine, the same critic for a live desk, the
same public events -- under a session id of the form `<desk>:<stamp>:strategy:<name>`, so every strategy decision is attributable.

What the floor guarantees:

* A run is a public `desk.code_run` (purpose `strategy <name>`), so the code's own printout is
  on the tape next to the orders it produced. Idle runs are published once an hour per
  strategy; runs that propose or fail are always published.
* A live desk's strategy orders are capped at the learning size until the desk itself raises
  the strategy's `notional_usd` after reading its record; shadow desks run at learning size
  by default and may size up in `params`.
* At most `max_intents_per_run` intents a run, `max_per_desk` strategies a desk,
  `min_cadence_seconds` between runs, and the sandbox's daily fuse on top. A strategy that
  raises is not stopped; its error is on the tape and its next run is one cadence later.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from .events import now_iso
from .manifest import DeskManifest

NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # The arena (Sept 18, 2026): a live book runs every house strategy of its family and up to
    # `foundry.max_explorers_per_desk` Foundry candidates side by side, each on its own record.
    "max_per_desk": 12,
    "min_cadence_seconds": 300,
    "max_cadence_seconds": 86_400,
    "max_intents_per_run": 5,
    "max_runs_per_tick": 2,
    "run_timeout_seconds": 90,
    "idle_publish_seconds": 3600,
    "starters": True,
    # A live strategy's orders stay at learning size until this many of its positions have
    # settled and its record passes the evidence gate (`evidence.passes`); then its size ramps
    # toward the desk's own order limit (`size_cap`), or to this multiple of learning size when
    # that limit cannot be read.
    "earned_settled": 20,
    "earned_multiple": 3,
    # leap: throughput -- with `dispatch_seconds` > 0 a dispatcher thread runs the due strategies
    # every that many seconds, off the floor's tick; the tick only collects results. Sept 17,
    # 2026: dispatch happened once a tick, 24 desks at a time, and a tick took four minutes, so
    # a five-minute strategy on one of 76 desks ran every 25 minutes or more.
    "dispatch_seconds": 0,
}
STARTERS_DIR = Path(__file__).resolve().parent / "starters"
#: How large the strategy runner (code plus the desk's context) may be.
RUNNER_MAX_CHARS = 400_000
#: Family -> starter module name. A desk of the family with no strategy of its own gets the
#: house starter deployed under this name, exactly as a bred desk gets the house playbook.
STARTERS = {"ranges": "hourly_ranges", "crypto": "hourly_reversion", "weather": "daily_temps", "kalshi": "kalshi_favorites"}
#: A second house strategy for a family: the ranges family also quotes the hourly buckets on
#: both legs at a spread, the maker side of the same market its starter takes.
SECOND_STARTERS = {"ranges": "hourly_quotes", "crypto": "spot_quotes"}
#: leap: futures -- a third house strategy for the crypto family: mean reversion on Coinbase's
#: CDE perpetual-style contracts, long and short, where a contract's fee is cents, not percent.
EXTRA_STARTERS: dict[str, list[str]] = {"crypto": ["perp_reversion", "perp_funding"], "kalshi": ["temps_ensemble", "poly_cross"]}
#: House rows a family no longer runs: bootstrap switches an existing row off once, with a note.
#: `daily_temps` on the Kalshi family (Sept 18, 2026): the ensemble strategy prices the same
#: brackets from the same NWS centre with a real spread, so the two doubled every weather bet.
RETIRED_STARTERS: dict[str, tuple[str, ...]] = {"kalshi": ("daily_temps",)}
#: The asset class a desk must trade for an extra starter to be dealt to it (the perps need a
#: futures mandate; the temperature markets are Kalshi events, priced on the Kalshi book since
#: the weather family's chat desks were retired on Sept 18, 2026).
EXTRA_REQUIRES: dict[str, str] = {"perp_reversion": "future", "perp_funding": "future", "daily_temps": "event", "temps_ensemble": "event", "poly_cross": "event"}
#: What the live desks run on the perps (Sept 18, 2026, the owner's call: real Coinbase trades
#: tonight): a lower trigger than the code's default, two entries a run, any contract the desk's
#: whole sleeve can hold. The evidence gate still decides size; the risk engine still binds.
EXTRA_LIVE_PARAMS: dict[str, dict[str, Any]] = {
    "perp_reversion": {"z_entry": 1.5, "max_intents": 2, "max_contract_usd": 300, "max_position_pct": 1.0},
    "perp_funding": {"max_intents": 2, "max_contract_usd": 300, "max_position_pct": 1.0},
}
#: What the shadow desks explore on the perps: the signal's window, threshold and holding time.
#: The live desk runs the code's defaults; each shadow is dealt one of these by its id.
EXTRA_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "temps_ensemble": [
        {"min_edge": 0.0},
        {"min_edge": 0.01, "shrink": 0.3},
        {"min_edge": 0.02, "shrink": 0.5, "min_price": 0.10},
        {"min_edge": 0.01, "maker": True},
        {"min_edge": 0.0, "max_hours": 18},
    ],
    "poly_cross": [
        {"min_edge": 0.03},
        {"min_edge": 0.05, "maker": True},
        {"min_edge": 0.04, "max_hours": 72},
        {"min_edge": 0.02, "min_volume_24h": 20000},
        {"min_edge": 0.06, "max_hours": 240},
    ],
    "perp_funding": [
        {"z_entry": 1.5},
        {"z_entry": 2.5, "holding_hours": 8},
        {"rate_entry": 0.0003},
        {"z_entry": 2.0, "stop_mult": 1.0},
        {"z_entry": 2.0, "holding_hours": 2},
    ],
    "daily_temps": [
        {"min_edge": 0.0},
        {"min_edge": 0.0, "sigma_day_ahead": 3.5},
        {"min_edge": 0.01, "sigma_day_ahead": 2.0},
        {"min_edge": 0.01, "sigma_day_ahead": 1.5, "min_price": 0.10},
        {"min_edge": 0.02, "sigma_day_ahead": 2.0, "min_price": 0.20, "shrink": 0.6},
    ],
    "perp_reversion": [
        {"z_entry": 1.5},
        {"z_entry": 2.5, "lookback": 48},
        {"interval": "15m", "lookback": 32, "holding_hours": 8},
        {"holding_hours": 2, "stop_pct": 0.008},
        {"z_entry": 2.0, "max_intents": 2, "max_contract_usd": 300},
        {"interval": "1h", "lookback": 24, "holding_hours": 12, "stop_pct": 0.02},
    ],
}
#: A shadow desk's starter explores, and each shadow desk of a family explores differently:
#: the variants are dealt round-robin by the desk's id, so the family's record compares
#: settings on the same markets at the same hours. The live desk keeps the code's defaults.
STARTER_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "ranges": [
        # The experiment is the volatility window: five-minute, fifteen-minute and hourly bars.
        {"min_edge": 0.0, "shrink": 0.5, "vol_interval": "5m", "vol_bars": 36},
        {"min_edge": 0.01, "shrink": 0.5, "vol_interval": "15m", "vol_bars": 32, "min_price": 0.10},
        {"min_edge": 0.02, "shrink": 0.7, "vol_interval": "1h", "vol_bars": 24, "max_minutes": 240},
        {"min_edge": 0.01, "shrink": 0.6, "series": ["KXBTCD", "KXETHD", "KXSOLD", "KXXRPD"], "max_minutes": 120},
        {"min_edge": 0.02, "shrink": 0.5, "min_price": 0.15, "max_minutes": 90},
    ],
    "crypto": [
        {"z_entry": 1.5, "symbols": "top:20"},
        {"z_entry": 2.0, "lookback": 48, "symbols": "top:30"},
        {"z_entry": 1.25, "lookback": 12, "holding_hours": 6},
    ],
    "kalshi": [
        # The experiment is the band and the side of the spread: how cheap a longshot is overpriced.
        # Sept 17, 2026: {"yes_min": 0.10, "yes_max": 0.25} was dropped (it bought the NO at 0.76
        # that lost $9.88); counted one position per market over 596 settled markets (Aug 15 -
        # Sep 15), maker NO buys at 0.93-0.96 averaged +1.97c [-0.9, +4.5], so NO >= 0.93 gets its
        # own row, as do a longer final window, the taker side at that price (fee ~0.46c at 0.93)
        # and one bet per cluster.
        {"yes_max": 0.05},
        {"yes_min": 0.05, "yes_max": 0.15},
        {"maker": False, "yes_max": 0.08},
        {"max_hours": 12, "min_volume_24h": 5000},
        {"yes_max": 0.07},
        {"min_hours": 3},
        {"maker": False, "yes_max": 0.07},
        {"max_open_per_cluster": 1},
    ],
    "weather": [
        {"min_edge": 0.0},
        {"min_edge": 0.0, "sigma_day_ahead": 3.5},
        {"min_edge": 0.01, "sigma_day_ahead": 2.0},
        {"min_edge": 0.01, "sigma_day_ahead": 1.5, "min_price": 0.10},
        {"min_edge": 0.02, "sigma_day_ahead": 2.0, "min_price": 0.20, "shrink": 0.6},
    ],
}
QUOTE_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "ranges": [
        {"spread": 0.04, "buckets": 2},
        {"spread": 0.05, "buckets": 2, "min_minutes": 35},  # does leaving the last half hour alone stop the pick-offs?
        {"spread": 0.03, "buckets": 3},
    ],
    "crypto": [
        # Sept 17, 2026: the 0.3-0.6% spreads were retired. At the account's 0.5% maker fee a
        # round trip needs 2 x 0.5% + a 0.2% margin before `spot_quotes` bids at all, so only
        # spreads wide enough to clear it are explored.
        {"spread": 0.015},
        {"spread": 0.02, "requote_seconds": 1800},
        {"spread": 0.03},
    ],
}
#: What the live desk's quoting starter runs with: one bucket on Kalshi; on Coinbase, exit-only
#: on two coins (Sept 17, 2026: a 90-day replay lost at every spread from 0.4% to 2% at the
#: 0.5% maker fee, so the live desk offers what it holds and bids for nothing).
QUOTE_LIVE_PARAMS: dict[str, dict[str, Any]] = {
    "ranges": {"buckets": 1},
    "crypto": {"symbols": ["BTC-USD", "ETH-USD"], "bid": False},
}
#: How often a house starter runs. Hourly markets reprice by the minute; spot reverts slower;
#: a day's temperature forecast moves a few times a day.
#: leap: promotion -- how the family's record moves settings onto the live desk.
#: `foundry_hold_hours`: a shadow row the Foundry dealt a candidate is not re-dealt for this long
#: (its forward record needs the settings it was given; the Foundry expires it after 72 hours).
PROMOTION: dict[str, Any] = {"enabled": True, "interval_seconds": 3600, "min_settled": 12, "jitter": 0.25, "foundry_hold_hours": 72}
STARTER_CADENCE = {"ranges": 300, "crypto": 600, "weather": 1800, "kalshi": 900, "hourly_quotes": 300, "spot_quotes": 300, "perp_reversion": 300, "daily_temps": 1800, "temps_ensemble": 1800, "poly_cross": 1800, "perp_funding": 600}


def starter_params(family: str, manifest: DeskManifest, *, quotes: bool = False) -> dict[str, Any]:
    """The house params for one desk: the code's defaults for a live desk, a dealt variant for
    a shadow desk. The deal is stable per desk id, so a restart changes nothing."""
    if manifest.live:
        return dict(QUOTE_LIVE_PARAMS.get(family) or {}) if quotes else {}
    variants = (QUOTE_VARIANTS.get(family) if quotes else STARTER_VARIANTS.get(family)) or [{}]
    index = sum(ord(ch) for ch in manifest.id) % len(variants)
    return dict(variants[index])

#: Uploaded as `/lab/run/main.py` for every strategy run. It builds the kit, imports the
#: strategy from the toolbox, calls `decide`, and prints one JSON line the floor reads back.
RUNNER = r'''
import json, math, sys, traceback
sys.path.insert(0, "/lab")
sys.path.insert(0, "/lab/floor")
PARAMS = json.loads(%(params)s)
CONTEXT = json.loads(%(context)s)

class Kit:
    """What a strategy may read. Public data only; nothing here can trade."""
    def __init__(self):
        import labkit
        self._lab = labkit
        self.context = CONTEXT
        self.log = []
        self._book_calls = 0
    def say(self, text):
        self.log.append(str(text)[:300])
    def bars(self, symbol, interval="1h", limit=60, asset_class="crypto", venue="coinbase"):
        return self._lab.bars(symbol, interval, limit, asset_class, venue)
    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        return self._lab.quote(symbol, asset_class, venue)
    def _event_source(self):
        # labkit's own kalshi helpers look for a public `source` that the composite never had;
        # the route is `_source`. Try both so a rebuilt image keeps working.
        data = getattr(self._lab, "_data", None)
        for attr in ("_source", "source"):
            getter = getattr(data, attr, None)
            if callable(getter):
                try:
                    return getter("event")
                except Exception:
                    return None
        return None
    def _crypto_source(self):
        data = getattr(self._lab, "_data", None)
        for attr in ("_source", "source"):
            getter = getattr(data, attr, None)
            if callable(getter):
                try:
                    return getter("crypto")
                except Exception:
                    return None
        return None
    def products(self, limit=25, quote="USD", min_volume_usd=250000.0):
        """The most traded spot products on Coinbase, by 24h dollar volume: symbol, price and
        volume. Anything the venue lists is in play; a strategy picks its universe from here."""
        src = self._crypto_source()
        lister = getattr(src, "products", None)
        if not callable(lister):
            return []
        try:
            rows = lister(product_type="SPOT", limit=None)
        except Exception:
            return []
        stable = {"USDT", "USDC", "DAI", "PYUSD", "EURC", "USDS", "GUSD", "TUSD", "USDP", "FDUSD", "RLUSD", "USD1"}
        out = []
        for row in rows:
            try:
                if str(row.get("quote_currency_id") or "").upper() != str(quote).upper():
                    continue
                if str(row.get("base_currency_id") or "").upper() in stable:
                    continue  # a stablecoin against the dollar has no move to trade
                if str(row.get("status") or "online").lower() != "online" or row.get("trading_disabled"):
                    continue
                price = float(row.get("price") or 0)
                volume = float(row.get("volume_24h") or 0) * price
                if price <= 0 or volume < float(min_volume_usd):
                    continue
                increment = float(row.get("quote_increment") or 0) or None
                out.append({"symbol": str(row.get("product_id")), "price": price, "volume_usd": volume, "quote_increment": increment})
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda r: -r["volume_usd"])
        return out[: int(limit)]
    def futures(self, root=None):
        """Coinbase's listed futures (oil, gold, equity baskets, BTC/ETH/SOL perpetual-style):
        symbol, root, expiry, price and dollar volume, nearest expiry first. Read-only prices, a
        reference for Kalshi's commodity markets."""
        src = self._crypto_source()
        lister = getattr(src, "products", None)
        if not callable(lister):
            return []
        try:
            rows = lister(product_type="FUTURE", limit=None)
        except Exception:
            return []
        out = []
        for row in rows:
            try:
                unit = str(row.get("contract_root_unit") or "")
                if root and unit.upper() != str(root).upper():
                    continue
                price = float(row.get("price") or 0)
                if price <= 0 or row.get("trading_disabled"):
                    continue
                size = float(row.get("contract_size") or 0) or None
                out.append({"symbol": str(row.get("product_id")), "root": unit, "expiry": str(row.get("contract_expiry") or ""), "price": price,
                            "volume_usd": float(row.get("volume_24h") or 0) * price * (size or 1.0), "contract_size": size,
                            "contract_usd": (price * size) if size else None, "perpetual": bool(row.get("perpetual")),
                            "funding_rate": float(row.get("funding_rate") or 0) if row.get("funding_rate") is not None else None,
                            "quote_increment": float(row.get("price_increment") or row.get("quote_increment") or 0) or None})
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda r: (r["expiry"] or "9999", -r["volume_usd"]))
        return out
    def kalshi_markets(self, max_close_hours=36, pages=5):
        """Every open single market (combos excluded) settling within `max_close_hours`, across all
        of Kalshi's categories, prices in dollars: the whole board, a page of 1,000 at a time."""
        import time as _time
        src = self._event_source()
        if src is None:
            return []
        until = int(_time.time() + float(max_close_hours) * 3600)
        out, cursor = [], None
        for _ in range(max(1, int(pages))):
            try:
                page = src.markets(status="open", limit=1000, cursor=cursor, max_close_ts=until, mve_filter="exclude")
            except TypeError:
                page = src.markets(status="open", limit=1000, cursor=cursor, max_close_ts=until)
            rows = page.get("markets", []) if isinstance(page, dict) else []
            for row in rows:
                if not str(row.get("ticker") or "").startswith("KXMVE"):
                    out.append(row)
            cursor = page.get("cursor") if isinstance(page, dict) else None
            if not cursor or not rows:
                break
        return out
    def kalshi_market(self, ticker):
        src = self._event_source()
        return src.market(ticker) if src is not None else None
    def kalshi_orderbooks(self, tickers):
        """Live order books for up to 300 markets, read now rather than from the cache:
        {ticker: {yes, no, yes_bid, yes_ask, no_bid, no_ask}}, prices in dollars, levels
        [(price, count)] best first. The kalshi_markets rows can be minutes old; price orders
        from here. At most three calls (100 tickers each) a run; a failed call adds no books,
        stops further calls and never raises. An unknown ticker comes back with empty sides."""
        src = self._event_source()
        reader = getattr(src, "orderbooks", None)
        if not callable(reader):
            return {}
        wanted = []
        for raw in list(tickers or []):
            ticker = str(raw or "").strip().upper()
            if ticker and ticker not in wanted:
                wanted.append(ticker)
        out = {}
        for start in range(0, len(wanted), 100):
            if self._book_calls >= 3:
                self.say(f"kalshi_orderbooks: three calls a run; {len(wanted) - start} ticker(s) not read")
                break
            self._book_calls += 1
            try:
                out.update(reader(wanted[start:start + 100]))
            except Exception as exc:
                self.say(f"kalshi_orderbooks failed: {type(exc).__name__}")
                break
        return out
    def weather(self, city):
        """The NWS forecast for a Kalshi weather city: days (date, day_high, hourly_max), the
        settlement station and the latest observation."""
        from ltcm.data import HttpTransport
        from ltcm.data.weather import Weather
        return Weather(transport=HttpTransport(cache_dir="/lab/cache", ttl=600.0, min_interval=0.2)).forecast(city)
    def _reader(self, module, cls, ttl=120.0):
        from ltcm.data import HttpTransport
        mod = __import__("ltcm.data." + module, fromlist=[cls])
        return getattr(mod, cls)(transport=HttpTransport(cache_dir="/lab/cache", ttl=ttl, min_interval=0.2))
    def polymarket(self, query="", limit=20):
        """Polymarket's active markets matching the words of `query` (empty: the busiest 100):
        {id, question, slug, outcomes, prices, token_ids, volume_24h, end_date}. Another venue's
        price on the same question is the cleanest reference an event contract can have."""
        return self._reader("polymarket", "Polymarket").search(query, limit=limit)
    def polymarket_matches(self, title, limit=5):
        """Polymarket markets whose question shares the words of a Kalshi title, best first,
        each with yes_price and score (token overlap). Check the numbers and dates yourself."""
        return self._reader("polymarket", "Polymarket").matches(title, limit=limit)
    def polymarket_book(self, token_id):
        return self._reader("polymarket", "Polymarket").book(token_id)
    def ensemble(self, city, days=3):
        """open-meteo's GFS and ECMWF ensemble members' daily highs (F) for a Kalshi weather
        city: days[{date, members, mean, sd, p10, p50, p90, n}]. A bracket's probability is the
        share of members inside it (kit.bracket_probability)."""
        from ltcm.data.weather import city_for
        c = city_for(city)
        return self._reader("openmeteo", "OpenMeteo", ttl=900.0).ensemble_daily_high(float(c.latitude), float(c.longitude), days=days, timezone=c.timezone)
    def bracket_probability(self, members, low=None, high=None):
        from ltcm.data.openmeteo import bracket_probability as bp
        return bp(members, low, high)
    def derivs(self, symbols=("BTC", "ETH", "SOL")):
        """Perps funding across OKX, Hyperliquid and Kraken, Deribit's DVOL implied vol and a
        funding z-score against the trailing 30 settlements, one row per symbol."""
        return self._reader("derivs", "Derivatives", ttl=60.0).snapshot(symbols)
    def basis(self, currency="BTC"):
        return self._reader("derivs", "Derivatives", ttl=60.0).basis(currency)
    def scoreboard(self, league):
        """ESPN's scoreboard for nfl, nba, mlb, nhl, ncaaf, ncaab, mls or epl: status, period,
        clock, scores, records and the book's spread, total and moneylines."""
        return self._reader("sports", "Sports", ttl=60.0).scoreboard(league)
    def match_game(self, title, rows):
        from ltcm.data.sports import Sports
        return Sports.match_kalshi(title, rows)
    def macro(self, series=None):
        """BLS series (CPI, unemployment, payrolls by default) newest first, and the next FOMC date."""
        reader = self._reader("macro", "Macro", ttl=3600.0)
        return {"bls": reader.bls_series(series) if series else reader.bls_series(), "next_fomc": reader.next_fomc()}
    def weather_cities(self):
        from ltcm.data.weather import CITIES
        return [
            {"name": c.name, "series": getattr(c, "series_hint", None) or getattr(c, "hint", None), "station": c.station}
            for c in CITIES.values()
        ]
    def kalshi_series(self, series, limit=1000, status="open"):
        """Open markets of one series (KXBTC, KXETH, KXHIGHNY...), prices in dollars. An hourly
        series lists dozens of buckets for several hours at once, so ask for them all."""
        src = self._event_source()
        if src is None:
            return []
        page = src.markets(series_ticker=series, status=status, limit=limit)
        rows = page.get("markets", []) if isinstance(page, dict) else []
        out = []
        for row in rows:
            try:
                # `markets()` already normalizes each row to dollars; parsing a parsed row
                # divides every price by a hundred again (a $0.41 ask became $0.0041 until
                # Sept 16, 2026). Only a raw row (integer cents) is parsed here.
                if type(row.get("yes_bid")).__name__ == "Decimal" or type(row.get("last_price")).__name__ == "Decimal":
                    out.append(row)
                else:
                    out.append(src.parse_market(row))
            except Exception:
                continue
        return out

def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return str(value)

kit = Kit()
result = {"intents": [], "notes": "", "log": kit.log}
try:
    from toolbox import %(name)s as strategy
    out = strategy.decide(kit, PARAMS)
    if isinstance(out, dict):
        result["intents"] = list(out.get("intents") or [])
        result["notes"] = str(out.get("notes") or "")[:600]
        result["cancels"] = [str(c) for c in (out.get("cancels") or []) if isinstance(c, str)][:20]
    elif isinstance(out, (list, tuple)):
        result["intents"] = list(out)
    elif out is not None:
        result["notes"] = str(out)[:600]
    result["intents"] = [_plain(i) for i in result["intents"] if isinstance(i, dict)][:%(max_intents)d]
    for intent in result["intents"]:
        if "rationale" in intent:
            intent["rationale"] = str(intent["rationale"])[:400]
except Exception:
    result["error"] = traceback.format_exc()[-1200:]
result["log"] = kit.log[-12:]
line = json.dumps(result, default=str, separators=(",", ":"))
if len(line) > 3600:
    result["log"] = result["log"][-3:]
    for intent in result["intents"]:
        intent["rationale"] = str(intent.get("rationale") or "")[:160]
    line = json.dumps(result, default=str, separators=(",", ":"))[:3600]
print("STRATEGY-RESULT " + line)
'''


def _dec(value: Any) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


class StrategyStore:
    """`.data/ltcm/strategies.json`: what is deployed, and each strategy's running counters."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        desks = data.get("desks") if isinstance(data, dict) else None
        return desks if isinstance(desks, dict) else {}

    def write(self, desks: Mapping[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}")
            tmp.write_text(json.dumps({"schema_version": 1, "desks": desks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.chmod(0o600)
            tmp.replace(self.path)

    def for_desk(self, desk_id: str) -> dict[str, dict[str, Any]]:
        return dict(self.read().get(desk_id) or {})

    def update(self, desk_id: str, name: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            desks = self.read()
            row = dict((desks.get(desk_id) or {}).get(name) or {})
            row.update(fields)
            desks.setdefault(desk_id, {})[name] = row
            self.write(desks)
            return row

    def patch(self, desk_id: str, name: str, expect: Mapping[str, Any] | None = None, **fields: Any) -> dict[str, Any] | None:
        """`update`, but only on a row that still exists and still holds `expect`; None otherwise.
        A run that finished after its strategy was undeployed wrote the row back, enabled, every
        300s, with no params (Sept 16, 2026 audit)."""
        with self._lock:
            row = (self.read().get(desk_id) or {}).get(name)
            if row is None or any(row.get(key) != value for key, value in (expect or {}).items()):
                return None
            return self.update(desk_id, name, **fields)

    def remove(self, desk_id: str, name: str) -> bool:
        with self._lock:
            desks = self.read()
            if name not in (desks.get(desk_id) or {}):
                return False
            del desks[desk_id][name]
            if not desks[desk_id]:
                del desks[desk_id]
            self.write(desks)
            return True


class Strategies:
    """The runner. Owned by the service; `tick(at)` runs what is due."""

    def __init__(
        self,
        service: Any,
        *,
        path: str | Path,
        config: Mapping[str, Any] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.service = service
        self.config = {**DEFAULTS, **dict(config or {})}
        self.store = StrategyStore(path)
        self.clock = clock
        self._bootstrapped = False
        self._bootstrapped_ids: set[str] = set()
        #: leap: throughput -- desk id -> the run in flight for it, when runs are parallel.
        self._inflight: dict[str, Future] = {}
        self._pool: ThreadPoolExecutor | None = None

    # ------------------------------------------------------------------ helpers
    def sandboxes(self) -> Any:
        return getattr(self.service, "sandboxes", None)

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True)) and self.sandboxes() is not None

    def learning_usd(self, manifest: DeskManifest) -> Decimal:
        policy = dict(getattr(self.service, "config", {}).get("learning") or {})
        if manifest.live:
            venue = manifest.venues[0] if manifest.venues else "kalshi"
            key = "live_coinbase_usd" if venue == "coinbase" else "live_kalshi_usd"
            return _dec(policy.get(key)) or Decimal("10")
        return _dec(policy.get("shadow_notional_usd")) or Decimal("15")

    def context_for(self, manifest: DeskManifest, at: str) -> dict[str, Any]:
        positions: list[dict[str, Any]] = []
        try:
            ctx = self.service.context(manifest)
            for position in ctx.positions():
                inst = getattr(position, "instrument", None)
                positions.append(
                    {
                        "symbol": getattr(inst, "symbol", None),
                        "market_id": getattr(inst, "market_id", None),
                        "right": getattr(inst, "right", None),
                        "asset_class": getattr(inst, "asset_class", None),
                        "quantity": str(getattr(position, "quantity", "")),
                        "average_cost": str(getattr(position, "average_cost", "") or ""),
                    }
                )
        except Exception:
            positions = []
        equity = None
        try:
            ledger = (getattr(self.service, "ledgers", None) or {}).get(manifest.id)
            state = ledger.state(self.service.now()) if ledger is not None else None
            equity = str(state.equity) if state is not None and state.equity is not None else None
        except Exception:
            equity = None
        return {
            "now": at,
            "desk_id": manifest.id,
            "live": bool(manifest.live),
            "learning_usd": str(self.learning_usd(manifest)),
            "equity_usd": equity,
            "positions": positions,
            "open_orders": self.open_orders_for(manifest),
            "venues": list(manifest.venues),
            # Live microstructure is forward-only; historical tests must tolerate its absence.
            "market_depth": self.service.feeds.depth("coinbase") if getattr(self.service, "feeds", None) is not None else {},
            "fee_rates": self.service.venue_fee_rates() if callable(getattr(self.service, "venue_fee_rates", None)) else {},
            # leap: pooled evidence -- the family's verdict on each of the desk's strategies, by
            # market group, so the code can stop betting where the record says there is no edge.
            "evidence": self.evidence_for(manifest),
            # The floor's clock: no event buy may settle later than this many hours out.
            "max_holding_hours": self.config.get("max_holding_hours"),
        }

    def open_orders_for(self, manifest: DeskManifest) -> list[dict[str, Any]]:
        """The desk's resting orders, as a strategy sees them: enough to cancel and replace."""
        gateway = getattr(self.service, "gateway", None)
        getter = getattr(gateway, "open_orders", None)
        if not callable(getter):
            return []
        out: list[dict[str, Any]] = []
        try:
            rows = getter(manifest.id)
        except Exception:
            return []
        if not rows:
            return []
        # An order row carries its intent id; the intent event carries the session id that
        # names the strategy. One read of the desk's intents serves every row.
        sessions: dict[str, str] = {}
        reader = getattr(getattr(self.service, "log", None), "read", None)
        if callable(reader):
            try:
                for event in reader(stream=manifest.stream, kind="desk.intent", limit=10_000, newest=True):
                    sessions[str(event.payload.get("intent_id"))] = str(event.payload.get("session_id") or "")
            except Exception:
                sessions = {}
        for row in rows[:200]:
            inst = row.get("instrument") if isinstance(row, Mapping) else None
            inst = inst if isinstance(inst, Mapping) else {}
            out.append(
                {
                    "order_id": row.get("order_id"),
                    "intent_id": row.get("intent_id"),
                    "market_id": inst.get("market_id"),
                    "symbol": inst.get("symbol"),
                    "right": inst.get("right"),
                    "asset_class": inst.get("asset_class"),
                    "venue": inst.get("venue") or row.get("venue"),
                    "purpose": row.get("purpose") or "entry",
                    "side": row.get("side"),
                    "quantity": str(row.get("quantity") or ""),
                    "limit_price": str(row.get("limit_price") or ""),
                    "submitted_at": row.get("submitted_at"),
                    "status": row.get("status"),
                    "strategy": _strategy_of(sessions.get(str(row.get("intent_id")), "") or str(row.get("session_id") or "")),
                }
            )
        return out

    # ------------------------------------------------------------------ deployment
    def deploy(self, manifest: DeskManifest, name: str, cadence_seconds: int, params: Mapping[str, Any] | None, *, note: str = "", house: bool = False) -> dict[str, Any]:
        """Register a toolbox module as a strategy after one dry run. Raises ValueError on refusal."""
        if not self.family_enabled(manifest):
            raise ValueError("family retired from execution; only its designated shadow control may run")
        if not isinstance(name, str) or not NAME.match(name):
            raise ValueError("a strategy name is lowercase letters, digits and underscores, 40 at most")
        manager = self.sandboxes()
        if manager is None:
            raise ValueError("no sandbox is available on this floor")
        low, high = int(self.config["min_cadence_seconds"]), int(self.config["max_cadence_seconds"])
        try:
            cadence = int(cadence_seconds)
        except (TypeError, ValueError):
            raise ValueError(f"cadence_seconds must be an integer between {low} and {high}") from None
        if not low <= cadence <= high:
            raise ValueError(f"cadence_seconds must be between {low} and {high}")
        existing = self.store.for_desk(manifest.id)
        if name not in existing and len(existing) >= int(self.config["max_per_desk"]):
            raise ValueError(f"a desk may run at most {self.config['max_per_desk']} strategies; undeploy one first")
        files = manager.toolbox_files(manifest.id) if hasattr(manager, "toolbox_files") else {}
        if f"{name}.py" not in files:
            raise ValueError(f"toolbox/{name}.py does not exist: save it first with run_code(save_as='{name}')")
        code = files[f"{name}.py"]
        if "def decide(" not in code:
            raise ValueError("the module must define decide(kit, params)")
        clean_params = _plain_params(params)
        at = self.service.now()
        run = self._execute(manifest, name, clean_params, at, dry=True)
        if run.get("error"):
            raise ValueError(f"the dry run failed: {str(run['error'])[-400:]}")
        if not isinstance(run.get("intents"), list):
            raise ValueError("decide() must return a list of intents (it may be empty)")
        row = self.store.update(
            manifest.id,
            name,
            cadence_seconds=cadence,
            params=clean_params,
            deployed_at=at,
            note=str(note or "")[:200],
            house=bool(house),
            enabled=True,
            code_sha256=_sha(code),
            last_run_at=None,
            runs=int(existing.get(name, {}).get("runs") or 0),
            intents=int(existing.get(name, {}).get("intents") or 0),
            approved=int(existing.get(name, {}).get("approved") or 0),
            errors=int(existing.get(name, {}).get("errors") or 0),
            last_error=None,
        )
        self._publish_run(manifest, name, run, at, f"strategy {name} deployed every {cadence}s" + (" (house starter)" if house else ""), always=True)
        return self.describe(manifest.id, name, row)

    def install(self, manifest: DeskManifest, spec: Mapping[str, Any], *, note: str = "") -> dict[str, Any]:
        """leap: lab -- save a strategy the lab wrote into the desk's toolbox and deploy it.
        Raises ValueError with the reason when the dry run refuses it."""
        manager = self.sandboxes()
        if manager is None or not hasattr(manager, "toolbox_save"):
            raise ValueError("no sandbox is available on this floor")
        name = str(spec.get("name") or "")
        code = str(spec.get("code") or "")
        manager.toolbox_save(manifest.id, name, code, (note or "lab strategy")[:200])
        return self.deploy(manifest, name, int(spec.get("cadence_seconds", 600)), spec.get("params") or {}, note=note)

    def house_sources(self, family: str) -> dict[str, str]:
        """The source of the family's house starters, by name."""
        out: dict[str, str] = {}
        for name in (STARTERS.get(family), SECOND_STARTERS.get(family)):
            if not name:
                continue
            path = STARTERS_DIR / f"{name}.py"
            if path.is_file():
                out[name] = path.read_text(encoding="utf-8")
        return out

    def _genome_strategies(self, family: str) -> list[Mapping[str, Any]]:
        """Strategies the family's adopted experiments carry (leap: lab), oldest first."""
        evolution = getattr(self.service, "evolution", None)
        genome = getattr(evolution, "genome", None)
        if not callable(genome):
            return []
        try:
            records = genome(family)
        except Exception:
            return []
        out = []
        for record in records:
            change = record.get("change") if isinstance(record, Mapping) else None
            spec = change.get("strategy") if isinstance(change, Mapping) else None
            if isinstance(spec, Mapping) and spec.get("name") and spec.get("code"):
                out.append({**spec, "experiment_id": record.get("experiment_id")})
        return out

    def undeploy(self, manifest: DeskManifest, name: str) -> dict[str, Any]:
        if not self.store.remove(manifest.id, name):
            raise ValueError(f"no strategy named {name!r} is deployed")
        return {"undeployed": name}

    def report(self, manifest: DeskManifest, name: str | None = None) -> dict[str, Any]:
        rows = self.store.for_desk(manifest.id)
        if name:
            if name not in rows:
                raise ValueError(f"no strategy named {name!r} is deployed")
            return self.describe(manifest.id, name, rows[name])
        return {"strategies": [self.describe(manifest.id, n, r) for n, r in sorted(rows.items())], "max_per_desk": self.config["max_per_desk"]}

    def describe(self, desk_id: str, name: str, row: Mapping[str, Any]) -> dict[str, Any]:
        keys = ("cadence_seconds", "params", "deployed_at", "note", "house", "enabled", "last_run_at", "runs", "intents", "approved", "errors", "last_error", "last_notes")
        record = self.record(desk_id, name)
        # The returns feed the gate; a desk reads the gate's verdict, not 500 numbers.
        verdict = {k: v for k, v in self.assess(record).items() if k in ("passes", "reason", "n_needed", "kind")} if record else {}
        shown = {k: v for k, v in record.items() if k != "returns"}
        family: dict[str, Any] = {}
        if bool(self.config.get("pooled_evidence", True)):
            manifests = getattr(self.service, "manifests", None)
            manifest = manifests.get(desk_id) if isinstance(manifests, Mapping) else None
            if manifest is not None:
                try:
                    pooled = self.family_record(manifest.family, name)
                except Exception:
                    pooled = {}
                if pooled:
                    pv = self.assess(pooled)
                    family = {"family_evidence": {
                        "settled": pooled.get("independent_settled", 0), "real_settled": pooled.get("real_settled", 0),
                        "desks": pooled.get("desks", 0), "settled_pnl_usd": pooled.get("settled_pnl_usd"),
                        "passes": bool(pv.get("passes")), "reason": pv.get("reason"), "lower": pv.get("lower"),
                        "groups": pooled.get("groups") or {},
                    }}
        return {"name": name, "desk_id": desk_id, **{k: row.get(k) for k in keys}, **shown, **({"evidence": verdict} if verdict else {}), **family}

    def _broker_index(self, reader: Callable[..., Any]) -> tuple[dict[str, set[str]], dict[str, list[Any]]]:
        """intent id -> its order ids, and order id -> its fills, over the newest 20,000 orders
        and fills. Kept for `record_cache_seconds`: a checkpoint asks for every strategy's
        record, and reading 40,000 events per strategy made publishing take minutes (Sept 16,
        2026). With the cache at 0 (the default) every call reads the log afresh."""
        ttl = float(self.config.get("record_cache_seconds") or 0)
        cached = getattr(self, "_index_cache", None)
        now = time.monotonic()
        if ttl > 0 and cached is not None and now - cached[0] < ttl:
            return cached[1], cached[2]
        orders_by_intent: dict[str, set[str]] = {}
        for e in reader(kind="broker.order", limit=20_000, newest=True):
            intent_id, order_id = e.payload.get("intent_id"), e.payload.get("order_id")
            if intent_id and order_id:
                orders_by_intent.setdefault(intent_id, set()).add(order_id)
        fills_by_order: dict[str, list[Any]] = {}
        for e in reader(kind="broker.fill", limit=20_000, newest=True):
            order_id = e.payload.get("order_id")
            if order_id:
                fills_by_order.setdefault(order_id, []).append(e)
        if ttl > 0:
            self._index_cache = (now, orders_by_intent, fills_by_order)
        return orders_by_intent, fills_by_order

    def record(self, desk_id: str, name: str, since: str | None = None, *, opened_since: bool = False) -> dict[str, Any]:
        """What the strategy's orders did: fills, fees and the settled P&L of the positions it
        opened, read from the desk's own tape (the `[strategy <name>]` prefix on its rationales).
        `since` limits the record to events at or after that instant, so a setting promoted at
        noon is judged on the trades it made after noon.

        A settlement is dated when it settles, so a position opened before `since` still counts
        after it. With `opened_since` (the Foundry's forward record, leap: foundry) a settlement
        counts only when its position opened at or after `since` by its `held_for_hours`, taken
        against it for the rounding, and the strategy filled that instrument since then; one
        whose opening is unknown is left out. Until Sept 16, 2026 the Foundry read the plain
        record, and a live desk could adopt settings on the settlements of positions the old
        settings had opened."""
        gathered = self._gather(desk_id, name, since, opened_since=opened_since)
        if gathered is None:
            return {}
        return _summarize(*gathered)

    def _gather(self, desk_id: str, name: str, since: str | None = None, *, opened_since: bool = False) -> tuple[list[Any], list[Any]] | None:
        """The strategy's fills and settled outcomes on one desk's tape; None when the tape
        cannot be read. `record` and `family_record` both read through here."""
        log = getattr(self.service, "log", None)
        reader = getattr(log, "read", None)
        if not callable(reader):
            return None
        stream = f"desk:{desk_id}"
        prefix = f"[strategy {name}]"
        start = _epoch(since) if since else 0.0

        def fresh(event: Any) -> bool:
            at = getattr(event, "at", None)
            return not since or not at or str(at) >= str(since)

        try:
            intents = {
                e.payload.get("intent_id")
                for e in reader(stream=stream, kind="desk.intent", limit=10_000, newest=True)
                if _strategy_of(str(e.payload.get("session_id") or "")) == name and fresh(e)
            }
            # Orders and fills live in `broker:<venue>` streams (kalshi, coinbase, shadow), never
            # in a desk's own stream: read every broker stream and match on the intent and order ids.
            # Until Sept 16, 2026 this read `broker:<desk>` and every record showed zero fills, so
            # no variant ever had a return on notional and the promotion loop had nothing to compare.
            orders_by_intent, fills_by_order = self._broker_index(reader)
            orders = set().union(*(orders_by_intent.get(i, set()) for i in intents)) if intents else set()
            fills = [e for order in orders for e in fills_by_order.get(order, ()) if fresh(e)]
            filled = {_instrument_key(f.payload.get("instrument")) for f in fills} - {None} if opened_since else set()

            def opened_after(event: Any) -> bool:
                if not opened_since or not since:
                    return True
                held = _dec(event.payload.get("held_for_hours"))
                at = _epoch(getattr(event, "at", None))
                if held is None or held < 0 or not at or not start:
                    return False
                # `held_for_hours` is rounded to a tenth of an hour: the earliest it can have opened.
                if at - float(held) * 3600.0 - 180.0 < start:
                    return False
                return str(event.payload.get("instrument") or "") in filled

            outcomes = [
                e for e in reader(stream=stream, kind="desk.outcome", limit=10_000, newest=True)
                if str(e.payload.get("rationale_excerpt") or "").startswith(prefix) and fresh(e) and opened_after(e)
            ]
        except Exception:
            return None
        return fills, outcomes

    # ------------------------------------------------------------------ pooled evidence
    def family_desks(self, family: str) -> list[str]:
        """Every desk id the strategy store or the roster has ever placed in `family`: the live
        desk, its shadow variants, and retired variants whose settlements are still evidence."""
        from .mind import family_of

        manifests = getattr(self.service, "manifests", None)
        families = {m.id: m.family for m in manifests.values()} if isinstance(manifests, Mapping) else {}
        ids = set(families) | set(self.store.read().keys())
        return sorted(d for d in ids if family_of(d, families) == family)

    def family_record(self, family: str, name: str) -> dict[str, Any]:
        """leap: pooled evidence -- one record for a strategy across every desk of its family.

        Until Sept 17, 2026 each desk's strategy earned size on its own settlements alone: a
        live favorites desk needed 43-300 of its own to prove a 1:13 payoff, at three a run,
        while eight shadow variants of the same code settled the same kind of bet on the same
        board and none of it counted. The family record pools them: the same strategy name on
        every desk the family has held, fills and settled outcomes together, summarized exactly
        like a desk's own record, plus `desks` (how many contributed), `real_settled` (outcomes
        marked real money), `groups` (the record split by market group, each with the gate's
        verdict, so the code learns where the edge lives) and `series_groups` (series -> group).

        Shadow settlements come from the shadow book's print-driven fills, not the venue, so
        `size_cap` asks for `pooled_min_real` real settlements before a pooled pass lifts a
        live desk's size. Cached for `record_cache_seconds` like the broker index."""
        ttl = float(self.config.get("record_cache_seconds") or 0)
        cache = getattr(self, "_family_cache", None)
        if cache is None:
            cache = self._family_cache = {}
        key = (family, name)
        hit = cache.get(key)
        now = time.monotonic()
        if ttl > 0 and hit is not None and now - hit[0] < ttl:
            return dict(hit[1])
        fills: list[Any] = []
        outcomes: list[Any] = []
        desks = 0
        for desk_id in self.family_desks(family):
            gathered = self._gather(desk_id, name)
            if gathered is None:
                continue
            if gathered[0] or gathered[1]:
                desks += 1
            fills.extend(gathered[0])
            outcomes.extend(gathered[1])
        outcomes.sort(key=lambda e: str(getattr(e, "at", "") or ""))
        record = _summarize(fills, outcomes)
        record["desks"] = desks
        record["real_settled"] = sum(1 for o in outcomes if o.payload.get("real_money") is True)
        groups, series_groups = _group_outcomes(outcomes)
        record["series_groups"] = series_groups
        record["groups"] = {}
        for group, rows in sorted(groups.items()):
            summary = _summarize([], rows)
            verdict = self.assess(summary)
            record["groups"][group] = {
                "n": summary.get("independent_settled", 0),
                "losses": summary.get("losses", 0),
                "avg_entry_price": summary.get("avg_entry_price"),
                "settled_pnl_usd": summary.get("settled_pnl_usd"),
                "passes": bool(verdict.get("passes")),
                "lower": verdict.get("lower"),
                "n_needed": verdict.get("n_needed"),
            }
        if ttl > 0:
            cache[key] = (now, dict(record))
        return record

    def evidence_for(self, manifest: DeskManifest) -> dict[str, Any]:
        """What a strategy run reads as `kit.context["evidence"]`: for each strategy on the desk,
        the family record's verdict and its per-group verdicts, small enough for the sandbox."""
        if not bool(self.config.get("pooled_evidence", True)):
            return {}
        out: dict[str, Any] = {}
        for name in sorted(self.store.for_desk(manifest.id)):
            try:
                record = self.family_record(manifest.family, name)
            except Exception:
                continue
            if not record:
                continue
            verdict = self.assess(record)
            out[name] = {
                "n": record.get("independent_settled", 0),
                "real_settled": record.get("real_settled", 0),
                "desks": record.get("desks", 0),
                "passes": bool(verdict.get("passes")),
                "lower": verdict.get("lower"),
                "n_needed": verdict.get("n_needed"),
                "groups": record.get("groups") or {},
                "series_groups": record.get("series_groups") or {},
                "group_prefixes": {k: list(v) for k, v in EVIDENCE_GROUPS.items()},
            }
        return out

    def evidence_config(self) -> dict[str, Any]:
        """`strategies.evidence` from config.json (z, min_n, skew_price, min_days)."""
        from . import evidence

        return evidence.settings(self.config.get("evidence"))

    def assess(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """leap: evidence -- the gate's whole verdict on a record, at the floor's settings."""
        from . import evidence

        return evidence.assess(record, **self.evidence_config())

    # ------------------------------------------------------------------ the tick
    def bootstrap(self, manifests: Mapping[str, DeskManifest]) -> list[str]:
        """Give every desk of a family with a house starter one, when it has no strategy yet."""
        if not self.config.get("starters", True) or not self.enabled():
            return []
        manager = self.sandboxes()
        deployed: list[str] = []
        for desk_id, manifest in sorted(manifests.items()):
            if not self.family_enabled(manifest):
                continue
            wanted: list[tuple[str, dict[str, Any], int]] = []
            starter = STARTERS.get(manifest.family)
            if starter:
                wanted.append((starter, starter_params(manifest.family, manifest), int(STARTER_CADENCE.get(manifest.family, 600))))
            second = SECOND_STARTERS.get(manifest.family)
            if second:
                wanted.append((second, starter_params(manifest.family, manifest, quotes=True), int(STARTER_CADENCE.get(second, 600))))
            for extra in EXTRA_STARTERS.get(manifest.family, []):
                if EXTRA_REQUIRES.get(extra, "future") in tuple(getattr(manifest.instruments, "asset_classes", ()) or ()):
                    variants = EXTRA_VARIANTS.get(extra) or [{}]
                    dealt = dict(EXTRA_LIVE_PARAMS.get(extra) or {}) if manifest.live else dict(variants[sum(ord(ch) for ch in manifest.id) % len(variants)])
                    wanted.append((extra, dealt, int(STARTER_CADENCE.get(extra, 600))))
            existing = self.store.for_desk(desk_id)
            allow = self.live_allow()
            if manifest.live and allow is not None:
                # Real money follows evidence (Sept 18, 2026, 16:45 UTC: a day of learning-size
                # bets by unproven strategies cost 13% of the account and produced little evidence
                # the shadow desks were not producing for free). A live book runs only the
                # strategies named in `strategies.live_allow`; everything else proves itself in
                # shadow and reaches real money through promotion or the Foundry's fast track.
                for name, row in existing.items():
                    if name not in allow and row.get("enabled", True):
                        self.store.update(desk_id, name, enabled=False, note="real money follows evidence: proving itself in shadow first (Sept 18, 2026)")
                    elif name in allow and row.get("house") and not row.get("enabled", True) and str(row.get("note") or "").startswith("explorers book"):
                        self.store.update(desk_id, name, enabled=True, note="house starter (the explorers books were retired on Sept 18, 2026)")
            if manifest.live and self.book_role(manifest) == "explorers":
                # An explorers book runs the Foundry's candidates and nothing else.
                for name, row in existing.items():
                    if not row.get("foundry_explorer") and row.get("enabled", True):
                        self.store.update(desk_id, name, enabled=False, note="explorers book (Sept 18, 2026): only Foundry candidates trade here")
                continue
            for retired in RETIRED_STARTERS.get(manifest.family, ()):
                row = existing.get(retired)
                if row is not None and row.get("house") and row.get("enabled", True):
                    self.store.update(desk_id, retired, enabled=False, note="retired house starter (Sept 18, 2026): temps_ensemble prices these brackets")
            # leap: lab -- an adopted strategy is house genome: every desk of the family runs it,
            # the live desk included, until the desk replaces it with its own.
            for spec in self._genome_strategies(manifest.family):
                if spec["name"] in existing or len(self.store.for_desk(desk_id)) >= int(self.config["max_per_desk"]):
                    continue
                try:
                    self.install(manifest, spec, note=f"house genome: experiment {spec.get('experiment_id')}")
                    deployed.append(f"{desk_id}/{spec['name']}")
                except Exception as exc:
                    self.service.alert("warning", f"genome strategy {spec['name']} for {desk_id} not deployed: {str(exc)[:160]}")
                    self.store.update(desk_id, spec["name"], enabled=False, last_error=str(exc)[:300], deployed_at=self.service.now(), cadence_seconds=int(spec.get("cadence_seconds", 600)), params=dict(spec.get("params") or {}))
            for name, params, cadence in wanted:
                if manifest.live and allow is not None and name not in allow:
                    continue  # dealt to the shadow desks only
                row = existing.get(name)
                if row is not None and row.get("house") and not row.get("enabled", True) and not int(row.get("runs") or 0):
                    # A house starter whose dry run failed on an earlier build: the code may be
                    # fixed now, so it is tried again from the repo (and stays off if it fails).
                    path = STARTERS_DIR / f"{name}.py"
                    if path.is_file() and hasattr(manager, "toolbox_save"):
                        try:
                            manager.toolbox_save(desk_id, name, path.read_text(encoding="utf-8"), f"house starter for the {manifest.family} family")
                            self.deploy(manifest, name, cadence, params, note="house starter", house=True)
                            deployed.append(f"{desk_id}/{name}")
                        except Exception as exc:
                            self.store.update(desk_id, name, last_error=str(exc)[:300])
                    continue
                if row is not None:
                    # A house starter follows the house params, cadence and code until the desk
                    # changes the file or redeploys it as its own.
                    if row.get("house"):
                        changes: dict[str, Any] = {}
                        # A promoted or dealt setting (leap: promotion) is the desk's own until the
                        # next promotion; only an untouched house row follows the house params.
                        # A house code refresh stamps promoted_at too (its record starts over),
                        # but the row is still the house's: its params follow the house. Until
                        # Sept 18, 2026 that stamp froze every house row's params after the
                        # first refresh, so a changed house setting never reached a desk.
                        # A Foundry candidate's settings on a house row are the candidate's until
                        # its trial ends, whatever the row's last stamp says.
                        untouched = (not row.get("promoted_at") or row.get("promoted_from") == "house code refresh") and not row.get("foundry_id")
                        if untouched and dict(row.get("params") or {}) != params:
                            changes["params"] = params
                        if int(row.get("cadence_seconds") or 0) != cadence:
                            changes["cadence_seconds"] = cadence
                        if changes:
                            self.store.update(desk_id, name, **changes)
                        self._refresh_house_code(desk_id, name, row, manager)
                    continue
                path = STARTERS_DIR / f"{name}.py"
                if not path.is_file():
                    continue
                if len(self.store.for_desk(desk_id)) >= int(self.config["max_per_desk"]):
                    continue  # the desk's own strategies come first
                try:
                    code = path.read_text(encoding="utf-8")
                    if hasattr(manager, "toolbox_save"):
                        manager.toolbox_save(desk_id, name, code, f"house starter for the {manifest.family} family")
                    self.deploy(manifest, name, cadence, params, note="house starter", house=True)
                    deployed.append(f"{desk_id}/{name}")
                except Exception as exc:
                    self.service.alert("warning", f"starter strategy {name} for {desk_id} not deployed: {str(exc)[:160]}")
                    # Remember the attempt so a broken starter is not retried every tick.
                    self.store.update(desk_id, name, enabled=False, last_error=str(exc)[:300], deployed_at=self.service.now(), cadence_seconds=cadence, params=params, house=True)
        return deployed

    def _refresh_house_code(self, desk_id: str, starter: str, row: Mapping[str, Any], manager: Any) -> None:
        """Ship a newer house starter to a desk that has not touched its copy."""
        path = STARTERS_DIR / f"{starter}.py"
        if not path.is_file() or not hasattr(manager, "toolbox_files"):
            return
        try:
            house = path.read_text(encoding="utf-8")
            current = manager.toolbox_files(desk_id).get(f"{starter}.py")
        except Exception:
            return
        if current is None or current == house:
            return
        if _sha(current) != str(row.get("code_sha256") or ""):
            return  # the desk edited its copy; it is the desk's now
        try:
            manager.toolbox_save(desk_id, starter, house, "house starter (updated)")
            # New code must earn its own forward record; the previous version's fills are
            # not evidence for it. Also invalidate any old-version run still in flight.
            at = self.service.now()
            self.store.update(desk_id, starter, code_sha256=_sha(house), deployed_at=at,
                              promoted_at=at, promoted_from="house code refresh")
        except Exception:
            return

    def live_allow(self) -> "set[str] | None":
        """The strategies a live book may run (`strategies.live_allow`), or None for any."""
        allow = self.config.get("live_allow")
        if allow is None:
            return None
        return {str(x) for x in (allow if isinstance(allow, (list, tuple, set)) else [allow])}

    def book_role(self, manifest: DeskManifest) -> str:
        """The arena (Sept 18, 2026): a live book is a `house` book (the family's house
        strategies and their promotions) or an `explorers` book (only the Foundry's candidates),
        from `strategies.book_roles`. Explorers then never drain the cash the proven code earns
        with, and every dollar of the explorers' record is theirs. Shadow desks have no role."""
        roles = dict(self.config.get("book_roles") or {})
        return str(roles.get(manifest.id) or "house")

    def family_enabled(self, manifest: DeskManifest) -> bool:
        policy = dict(getattr(self.service, "config", {}).get("strategy_lifecycle") or {})
        if manifest.family not in policy.get("retired_families", ()):
            return True
        return not manifest.live and manifest.id in policy.get("controls", ())

    def due(self, manifests: Mapping[str, DeskManifest], at: str) -> list[tuple[DeskManifest, str, dict[str, Any]]]:
        now = _epoch(at)
        found: list[tuple[float, DeskManifest, str, dict[str, Any]]] = []
        for desk_id, rows in self.store.read().items():
            manifest = manifests.get(desk_id)
            if manifest is None:
                continue
            if not self.family_enabled(manifest):
                continue
            for name, row in rows.items():
                if not row.get("enabled", True):
                    continue
                last = _epoch(row.get("last_run_at")) if row.get("last_run_at") else None
                cadence = int(row.get("cadence_seconds") or self.config["min_cadence_seconds"])
                if last is None or now - last >= cadence:
                    found.append((last or 0.0, manifest, name, row))
        found.sort(key=lambda item: (item[0], item[1].id, item[2]))
        return [(m, n, r) for _, m, n, r in found]

    def tick(self, manifests: Mapping[str, DeskManifest], at: str) -> list[dict[str, Any]]:
        """Run the strategies that are due, a bounded number per tick. Never raises."""
        if not self.enabled():
            return []
        for desk_id, manifest in manifests.items():
            if self.family_enabled(manifest):
                continue
            try:
                for order in self.service.gateway.open_orders(desk_id):
                    if order.get("purpose") != "exit":
                        self.service.gateway.cancel(desk_id, str(order["order_id"]), at)
            except Exception as exc:
                self.service.alert("warning", f"{desk_id}: lifecycle cancellation will retry: {type(exc).__name__}")
            for name, row in self.store.for_desk(desk_id).items():
                if row.get("enabled", True):
                    self.store.update(desk_id, name, enabled=False, note="retired family: execution disabled by lifecycle policy")
                    self.service.alert("info", f"{desk_id}/{name}: retired by family lifecycle policy")
        # Every desk is dealt its starters once, the ones bred tonight included: until Sept 16,
        # 2026 this ran once per process, so a child spawned by the evolution loop had no strategy
        # until the next restart and its whole first day was a blank record.
        fresh = {desk_id: m for desk_id, m in manifests.items() if desk_id not in self._bootstrapped_ids}
        if fresh:
            self._bootstrapped = True
            self._bootstrapped_ids.update(fresh)
            try:
                self.bootstrap(fresh)
            except Exception as exc:
                self.service.alert("warning", f"strategy starters failed: {type(exc).__name__}")
        out: list[dict[str, Any]] = []
        workers = int(self.config.get("parallel_runs") or 1)
        dispatcher = getattr(self, "_dispatcher", None)
        if dispatcher is not None and dispatcher.is_alive() and threading.current_thread() is not dispatcher:
            # The dispatcher thread runs the due strategies; the tick collects and promotes.
            out.extend(self._collect())
            try:
                self.promote(manifests, at)  # leap: promotion
            except Exception as exc:
                self.service.alert("warning", f"strategy promotion failed: {type(exc).__name__}")
            return out
        if workers <= 1:
            for manifest, name, row in self.due(manifests, at)[: int(self.config["max_runs_per_tick"])]:
                result = self._run_guarded(manifest, name, row, at)
                if result is not None:
                    out.append(result)
        else:
            # leap: throughput -- each desk has its own sandbox, so desks run side by side, one
            # run per desk at a time, off the tick. Until Sept 16, 2026 at most four runs a tick
            # ran one after another (3 to 13 seconds each) and five-minute strategies ran every
            # 17 to 32 minutes: a third to a sixth of the rules the desks deployed.
            out.extend(self._collect())
            if self._pool is None:
                self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="strategy")
            busy = {desk_id for desk_id, future in self._inflight.items() if not future.done()}
            for manifest, name, row in self.due(manifests, at):
                if len(busy) >= workers:
                    break
                if manifest.id in busy:
                    continue
                self._inflight[manifest.id] = self._pool.submit(self._run_guarded, manifest, name, row, at)
                busy.add(manifest.id)
        try:
            self.promote(manifests, at)  # leap: promotion
        except Exception as exc:
            self.service.alert("warning", f"strategy promotion failed: {type(exc).__name__}")
        return out

    # ------------------------------------------------------------------ the dispatcher
    def start_dispatcher(self, manifests: Callable[[], Mapping[str, DeskManifest]], now: Callable[[], str]) -> bool:
        """Run the due strategies every `dispatch_seconds` on a thread of their own (leap:
        throughput). False when the config keeps dispatch on the tick."""
        seconds = float(self.config.get("dispatch_seconds") or 0)
        if seconds <= 0 or int(self.config.get("parallel_runs") or 1) <= 1:
            return False
        if getattr(self, "_dispatcher", None) is not None and self._dispatcher.is_alive():
            return True
        self._dispatch_stop = threading.Event()

        def loop() -> None:
            while not self._dispatch_stop.is_set():
                try:
                    self.tick(manifests(), now())
                except Exception as exc:
                    try:
                        self.service.alert("warning", f"strategy dispatcher: {type(exc).__name__}: {str(exc)[:120]}")
                    except Exception:
                        pass
                self._dispatch_stop.wait(seconds)

        self._dispatcher = threading.Thread(target=loop, name="strategy-dispatcher", daemon=True)
        self._dispatcher.start()
        return True

    def stop_dispatcher(self) -> None:
        stop = getattr(self, "_dispatch_stop", None)
        if stop is not None:
            stop.set()
        thread = getattr(self, "_dispatcher", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)

    def _run_guarded(self, manifest: DeskManifest, name: str, row: Mapping[str, Any], at: str) -> dict[str, Any] | None:
        if not self.family_enabled(manifest):
            return None
        try:
            return self.run_one(manifest, name, row, at)
        except Exception as exc:
            self.service.alert("warning", f"strategy {manifest.id}/{name} failed: {type(exc).__name__}")
            self.store.patch(manifest.id, name, {"deployed_at": row.get("deployed_at")}, last_run_at=at, errors=int(row.get("errors") or 0) + 1, last_error=f"{type(exc).__name__}")
            return None

    def _collect(self) -> list[dict[str, Any]]:
        """The results of the parallel runs that finished since the last tick."""
        out: list[dict[str, Any]] = []
        for desk_id, future in list(self._inflight.items()):
            if not future.done():
                continue
            self._inflight.pop(desk_id, None)
            try:
                result = future.result()
            except Exception:
                result = None
            if result is not None:
                out.append(result)
        return out

    def wait(self, timeout: float = 120.0) -> list[dict[str, Any]]:
        """Block until the runs in flight finish (tests, shutdown); returns their results."""
        deadline = time.time() + timeout
        for future in list(self._inflight.values()):
            remaining = max(0.0, deadline - time.time())
            try:
                future.result(timeout=remaining)
            except Exception:
                pass
        return self._collect()

    # ------------------------------------------------------------------ promotion
    def promote(self, manifests: Mapping[str, DeskManifest], at: str) -> list[dict[str, Any]]:
        """leap: promotion -- the family's record chooses the live desk's settings.

        Once an hour, for every house strategy a live desk runs: read each shadow variant of the
        same strategy in the family since it was last dealt, and the live desk's own setting the
        same way. A variant is a candidate when it has at least `min_settled` settlements and its
        record passes the evidence gate (`evidence.passes`, config `strategies.evidence`). The
        candidate with the highest per-dollar lower bound wins when that bound beats the live
        setting's return on notional (or the live setting has too few settlements to say): the
        live desk adopts the variant's params, the winning shadow keeps them as the control, and
        every other shadow is dealt a jittered copy, so the search continues around the new best.
        Everything is written to the tape as a `desk.code_run` on the live desk and an `ops.alert`.

        Sept 17, 2026: the gate was a minimum count with a positive return and a 0.01 margin on the
        point estimate. At an average price of 0.93 a breakeven favorites variant passed a 6-settled
        gate 65% of the time, so the live desk followed whichever shadow was luckiest that day."""
        from . import evidence

        policy = {**PROMOTION, **dict(self.config.get("promotion") or {})}
        if not bool(policy.get("enabled", True)) or not self.enabled():
            return []
        last = getattr(self, "_last_promotion_at", None)
        if last is not None and _epoch(at) - _epoch(last) < float(policy.get("interval_seconds", 3600)):
            return []
        self._last_promotion_at = at
        min_settled = int(policy.get("min_settled", 12))
        jitter = float(policy.get("jitter", 0.25))
        gate = self.evidence_config()
        promoted: list[dict[str, Any]] = []
        for live in [m for m in manifests.values() if m.live]:
            for name, row in sorted(self.store.for_desk(live.id).items()):
                if not row.get("house") or not row.get("enabled", True):
                    continue
                live_record = self.record(live.id, name, since=row.get("promoted_at") or row.get("deployed_at"))
                live_score = _return_on_notional(live_record) if int(live_record.get("settled") or 0) >= min_settled else None
                if live_score is None and row.get("foundry_id"):
                    # leap: foundry -- settings the Foundry moved here cleared a backtest and a
                    # forward record; they are replaced on the live desk's own evidence, not before.
                    # Until Sept 16, 2026 the reset evidence let any shadow take them within the hour.
                    continue
                shadows = [m for m in manifests.values() if not m.live and m.family == live.family and m.id != live.id]
                scored: list[tuple[Decimal, Decimal, str, dict[str, Any], dict[str, Any], str]] = []
                for shadow in shadows:
                    srow = self.store.for_desk(shadow.id).get(name)
                    if not srow or not srow.get("enabled", True):
                        continue
                    record = self.record(shadow.id, name, since=srow.get("promoted_at") or srow.get("deployed_at"))
                    score = _return_on_notional(record)
                    # `min_settled` stays as a floor under the evidence gate.
                    if score is None or int(record.get("settled") or 0) < min_settled:
                        continue
                    verdict = evidence.assess(record, **gate)
                    if not verdict["passes"] or verdict.get("lower") is None:
                        continue
                    scored.append((Decimal(str(verdict["lower"])), score, shadow.id, srow, record, str(verdict["reason"])))
                if not scored:
                    continue
                scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
                lower, best_score, winner, wrow, wrecord, _ = scored[0]
                if live_score is not None and lower <= live_score:
                    continue
                params = _plain_params(wrow.get("params"))
                if params == _plain_params(row.get("params")):
                    continue
                note = f"promoted from {winner}: {wrecord.get('settled')} settled, lower bound {lower:+.3f} per $ vs live {'n/a' if live_score is None else f'{live_score:+.3f}'}"
                # Only onto the house row it scored: a desk that redeployed the strategy as its own
                # while the record was read keeps its own params.
                if self.store.patch(live.id, name, {"house": row.get("house"), "deployed_at": row.get("deployed_at"), "params": row.get("params")}, params=params, promoted_at=at, promoted_from=winner, note=note[:200], foundry_id=None) is None:
                    continue
                run = {
                    "intents": [], "notes": note, "code_sha256": row.get("code_sha256"),
                    "log": [f"live {live.id}: {live_record.get('settled', 0)} settled since {row.get('promoted_at') or row.get('deployed_at')}",
                            *[f"{sid}: {rec.get('settled')} settled, {sc:+.3f} per $ filled, lower bound {lb:+.3f} ({why})"[:300] for lb, sc, sid, _, rec, why in scored[:6]],
                            f"new params: {json.dumps(params, sort_keys=True)}"],
                }
                self._publish_run(live, name, run, at, f"strategy {name} promoted: {winner}'s settings take the live desk", always=True)
                self.service.alert("info", f"promotion: {live.id}/{name} adopts {winner}'s settings ({note})")
                hold = float(policy.get("foundry_hold_hours", 72)) * 3600.0
                for shadow in shadows:
                    srow = self.store.for_desk(shadow.id).get(name)
                    if shadow.id == winner or not srow:
                        continue  # the winner stays as the control
                    if srow.get("foundry_id") and _epoch(at) - _epoch(srow.get("promoted_at")) < hold:
                        continue  # a Foundry candidate still earning its forward record keeps its settings
                    dealt = _jitter_params(params, f"{shadow.id}:{name}:{at}", jitter)
                    self.store.update(shadow.id, name, params=dealt, promoted_at=at, note=f"dealt around {winner} at {at[:16]}")
                promoted.append({"desk_id": live.id, "strategy": name, "from": winner, "params": params, "score": str(best_score), "lower_bound": str(lower)})
        return promoted

    def run_one(self, manifest: DeskManifest, name: str, row: Mapping[str, Any], at: str) -> dict[str, Any]:
        params = dict(row.get("params") or {})
        run = self._execute(manifest, name, params, at)
        intents = run.get("intents") if isinstance(run.get("intents"), list) else []
        cancels = [str(c) for c in (run.get("cancels") or []) if isinstance(c, str)][:20] if not run.get("error") else []
        decisions: list[dict[str, Any]] = []
        # The desk may have undeployed or redeployed the strategy while this run was in the sandbox.
        current = self.store.for_desk(manifest.id).get(name)
        if current is None or current.get("deployed_at") != row.get("deployed_at"):
            intents = []
            cancels = []
        elif not current.get("enabled", True):
            intents = [intent for intent in intents if intent.get("reduce_only") is True]
        requested_cancels = {o["order_id"] for o in self.open_orders_for(manifest)
                             if o.get("strategy") == name and o["order_id"] in cancels} if cancels else set()
        cancelled = self._cancel(manifest, name, list(requested_cancels), at) if requested_cancels else 0
        if cancelled < len(requested_cancels):
            # A cancellation request is not a cancelled order. It may still be working or
            # have filled in the race; rerun with fresh inventory before any replacement.
            intents = []
            run["notes"] = "Replacement deferred: cancellation not confirmed; refresh orders and inventory. " + str(run.get("notes") or "")
        if not run.get("error") and intents:
            decisions = self._propose(manifest, name, intents, at)
        approved = sum(1 for d in decisions if d.get("approved"))
        refused = [", ".join(str(r) for r in (d.get("reasons") or [])[:2])[:160] for d in decisions if not d.get("approved")]
        if refused:
            # The reason an intent went nowhere belongs on the tape next to the intent (Sept 17,
            # 2026: the first perps intents were refused and nothing recorded why).
            run["log"] = list(run.get("log") or []) + [f"refused: {why}" for why in refused[:3]]
            run["notes"] = f"{len(refused)} refused ({refused[0]}); " + str(run.get("notes") or "")
        if cancelled:
            run["notes"] = f"{cancelled} cancelled; " + str(run.get("notes") or "")
        self.store.patch(
            manifest.id,
            name,
            {"deployed_at": row.get("deployed_at")},
            last_run_at=at,
            runs=int(row.get("runs") or 0) + 1,
            intents=int(row.get("intents") or 0) + len(intents),
            approved=int(row.get("approved") or 0) + approved,
            errors=int(row.get("errors") or 0) + (1 if run.get("error") else 0),
            last_error=(str(run["error"])[-300:] if run.get("error") else None),
            last_notes=(str(run.get("notes") or "") + " | " + " / ".join(str(x) for x in (run.get("log") or [])[-3:]))[:400],
        )
        purpose = f"strategy {name}: " + (
            f"error" if run.get("error") else f"{len(intents)} intent(s), {approved} approved"
        )
        self._publish_run(manifest, name, run, at, purpose, always=bool(intents or run.get("error")), row=row)
        return {"desk_id": manifest.id, "strategy": name, "intents": len(intents), "approved": approved, "error": bool(run.get("error"))}

    # ------------------------------------------------------------------ execution
    def _execute(self, manifest: DeskManifest, name: str, params: Mapping[str, Any], at: str, *, dry: bool = False) -> dict[str, Any]:
        manager = self.sandboxes()
        context = self.context_for(manifest, at)
        context["dry_run"] = bool(dry)
        code = RUNNER % {
            "params": json.dumps(json.dumps(dict(params))),
            "context": json.dumps(json.dumps(context)),
            "name": name,
            "max_intents": int(self.config["max_intents_per_run"]),
        }
        # The runner carries the desk's context; with the depth books and the pooled evidence a
        # run passed the model-code cap of 40,000 characters on Sept 18, 2026 and every deploy
        # to that desk failed its dry run.
        try:
            run = manager.run(manifest.id, code, purpose=f"strategy {name}", timeout=int(self.config["run_timeout_seconds"]), max_chars=RUNNER_MAX_CHARS)
        except TypeError:
            run = manager.run(manifest.id, code, purpose=f"strategy {name}", timeout=int(self.config["run_timeout_seconds"]))
        result: dict[str, Any] = {"exit_code": run.exit_code, "seconds": str(run.seconds), "stdout": run.stdout, "code_sha256": run.code_sha256, "sandbox": run.sandbox}
        parsed = _parse_result(run.stdout)
        if parsed is None:
            result["error"] = f"exit {run.exit_code}: no result line ({(run.stdout or '')[-300:]})" if run.exit_code else "no result line in the output"
            result["intents"] = []
            return result
        result.update(parsed)
        if run.exit_code and not parsed.get("error"):
            result["error"] = f"exit {run.exit_code}"
        return result

    def size_cap(self, manifest: DeskManifest, name: str) -> Decimal:
        """How much one of the strategy's orders may commit on a live desk.

        Learning size until the strategy has earned more: at least `earned_settled` settled
        positions and a record that passes the evidence gate (`evidence.passes`, config
        `strategies.evidence`) start a ramp. At the `n_needed` settlements the gate asked for the
        cap is still learning size; it grows linearly with each settlement after that and reaches
        the desk's own order limit (`limit_fit_usd`) at `full_size_multiple` (3) times `n_needed`.
        When the desk's limit cannot be read the ramp's top is `earned_multiple` times learning
        size. A record that stops passing goes back to learning size on the next run. This is
        the floor's capital following the strategies that earn it, one settlement at a time.

        Sept 17, 2026: the earned path was 6 settled with a positive P&L. At an average price of
        0.93 a favorites strategy with no edge cleared that 65% of the time and tripled its size
        on luck. The gate that replaced it passes a breakeven favorite about a fifth of the time
        at the settlements it needs, so passing is not proof: size follows the evidence as it
        accumulates instead of jumping to the desk's full limit the run the gate first passes."""
        from . import evidence

        learning = self.learning_usd(manifest)
        fit = self.limit_fit_usd(manifest)
        if manifest.live:
            gate = self.evidence_config()
            top = fit if fit is not None else learning * Decimal(str(self.config.get("earned_multiple", 3)))
            ramps: list[Decimal] = []
            record = self.record(manifest.id, name)
            settled = int(record.get("independent_settled", record.get("settled")) or 0)
            ok, _, needed = evidence.passes(record, **gate) if record else (False, "", 1)
            if settled >= int(self.config.get("earned_settled", 20)) and ok:
                ramps.append(earned_ramp(settled, needed, gate.get("full_size_multiple", 3)))
            # leap: pooled evidence -- the family's settlements of the same strategy count too,
            # once enough of them were real money (the shadow book's fills are modelled from
            # prints). A live desk born yesterday sizes on what its family has already proved.
            if bool(self.config.get("pooled_evidence", True)):
                try:
                    pooled = self.family_record(manifest.family, name)
                except Exception:
                    pooled = {}
                pooled_n = int(pooled.get("independent_settled", pooled.get("settled")) or 0)
                real = int(pooled.get("real_settled") or 0)
                if pooled and real >= int(self.config.get("pooled_min_real", 5)) and pooled_n >= int(self.config.get("earned_settled", 20)):
                    pooled_ok, _, pooled_needed = evidence.passes(pooled, **gate)
                    if pooled_ok:
                        ramps.append(earned_ramp(pooled_n, pooled_needed, gate.get("full_size_multiple", 3)))
            if ramps:
                # Compounding: a strategy that keeps earning ramps toward the desk's own order
                # limit, a share of the desk's equity, so its bets grow as the book grows. The
                # desk's position, daily-loss and floor limits, and the firm's event rules, still
                # bind above it.
                earned = (learning + (top - learning) * max(ramps)).quantize(Decimal("0.01"))
                learning = max(learning, earned)
        return min(learning, fit) if fit is not None else learning

    def free_cash_usd(self, manifest: DeskManifest) -> Decimal | None:
        """The desk's cash less what its resting buys already commit, or None when unknown."""
        ledgers = getattr(self.service, "ledgers", None)
        ledger = ledgers.get(manifest.id) if isinstance(ledgers, Mapping) else None
        if ledger is None:
            return None
        try:
            cash = ledger.state(self.service.now()).cash
        except Exception:
            return None
        committed = Decimal(0)
        for row in self.open_orders_for(manifest):
            try:
                if str(row.get("side")) == "buy" and row.get("purpose") != "exit":
                    committed += (_dec(row.get("quantity")) or Decimal(0)) * (_dec(row.get("limit_price")) or Decimal(0))
            except Exception:
                continue
        return (cash - committed).quantize(Decimal("0.01"))

    def limit_fit_usd(self, manifest: DeskManifest) -> Decimal | None:
        """The largest order the desk's own limits allow now: the smaller of the order and the
        position caps, times desk equity, with a little headroom for the reference moving.

        A fixed learning size is a trap for a desk that loses: on Sept 16, 2026 Scholes fell to
        $33 and Haghani to $83, a $10 order broke their 15% and 10% caps, and every order was
        refused, so neither could trade, learn, or earn its way back. Sizing to fit keeps a
        shrinking desk producing evidence at a size its limits accept; the committee decides
        how much capital it deserves. None when the desk's equity cannot be read."""
        ledgers = getattr(self.service, "ledgers", None)
        ledger = ledgers.get(manifest.id) if isinstance(ledgers, Mapping) else None
        if ledger is None:
            return None
        try:
            equity = ledger.state(self.service.now()).equity
        except Exception:
            return None
        if equity is None or equity <= 0:
            return None
        limits = manifest.limits
        pct = min(limits.max_order_notional_pct, limits.max_position_pct)
        headroom = Decimal(str(self.config.get("limit_headroom", "0.9")))
        return (equity * pct * headroom).quantize(Decimal("0.01"))

    def _cancel(self, manifest: DeskManifest, name: str, order_ids: list[str], at: str) -> int:
        """Cancel the desk's own resting orders a strategy asked to replace. A strategy may only
        cancel orders it placed itself, so two strategies on one desk never fight."""
        mine = {o["order_id"] for o in self.open_orders_for(manifest) if o.get("strategy") == name}
        ctx = self.service.context(manifest)
        done = 0
        for order_id in order_ids:
            if order_id not in mine:
                continue
            try:
                result = ctx.cancel_order(order_id)
                if isinstance(result, Mapping) and result.get("status") == "cancelled":
                    done += 1
            except Exception as exc:
                self.service.alert("warning", f"strategy {manifest.id}/{name} could not cancel {order_id}: {type(exc).__name__}")
        return done

    def _propose(self, manifest: DeskManifest, name: str, intents: list[dict[str, Any]], at: str) -> list[dict[str, Any]]:
        """Propose each intent as the desk would: same tools path, same risk engine, same events."""
        from . import tools as tools_module

        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        session_id = f"{manifest.id}:{stamp}:strategy:{name}"
        ctx = self.service.context(manifest, session_id=session_id)
        if hasattr(ctx, "bind_session"):
            try:
                ctx.bind_session(session_id)
            except Exception:
                pass
        session = tools_module.ToolSession(session_id=session_id, desk_id=manifest.id, now=at)
        # A live desk: learning size, earned size, and the desk's own limits. A shadow desk sizes
        # itself (a variant's params may explore size); only its limits bind, so it is never
        # refused into silence. The mode is the one the floor holds as each order goes, not the
        # one at dispatch: a promotion during the run once sent shadow-sized orders to real money.
        caps: dict[bool, Decimal | None] = {}
        out: list[dict[str, Any]] = []
        for raw in intents[: int(self.config["max_intents_per_run"])]:
            live = self._live_now(manifest)
            if live not in caps:
                current = self._manifest_now(manifest)
                caps[live] = self.size_cap(current, name) if live else self.limit_fit_usd(current)
            cap = caps[live]
            if live and cap is not None and not raw.get("reduce_only"):
                # No bigger than the cash the book has: a $40 order against $6 of cash was refused
                # hundreds of times an hour on Sept 18, 2026, and a smaller one trades.
                free = self.free_cash_usd(manifest)
                if free is not None:
                    if free < Decimal("2"):
                        out.append({"approved": False, "reasons": [f"desk cash exhausted ({free:.2f}); nothing proposed"], "rationale": str(raw.get("rationale") or "")[:200]})
                        continue
                    cap = min(cap, free)
            args = dict(raw)
            args.setdefault("order_type", "limit")
            # The arena's clock (Sept 18, 2026, 21:15 UTC, the owner's rule): an agent buys only
            # what settles soon. A position that pays out in weeks teaches nothing for weeks; a
            # strategy earns its record from settlements, and six of them move it to real money.
            # Every strategy on every desk, shadow included: the shadow desks are the evidence.
            horizon = _dec(self.config.get("max_holding_hours"))
            hold = _dec(args.get("holding_period_hours"))
            if horizon is not None and horizon > 0 and str((args.get("instrument") or {}).get("asset_class") or "") == "event" \
                    and args.get("side") == "buy" and not args.get("reduce_only") and hold is not None and hold > horizon:
                out.append({"approved": False, "reasons": [f"settles in {hold:.0f}h; the floor buys nothing that settles more than {horizon:.0f}h out (learning speed)"], "rationale": str(raw.get("rationale") or "")[:200]})
                continue
            if args.get("order_type") != "limit" or _dec(args.get("limit_price")) is None:
                out.append({"approved": False, "reasons": ["a strategy proposes limit orders with a limit_price"], "rationale": str(args.get("rationale") or "")[:200]})
                continue
            if cap is not None and not args.get("reduce_only"):
                args["quantity"] = _capped_quantity(args, cap)
            args["rationale"] = f"[strategy {name}] " + str(args.get("rationale") or "no rationale given")[:1800]
            try:
                result = tools_module.execute("propose_order", args, ctx, manifest, session)
                data = json.loads(result) if isinstance(result, str) else result
            except Exception as exc:
                data = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            if isinstance(data, dict) and "error" in data:
                out.append({"approved": False, "reasons": [str(data["error"])[:300]]})
            else:
                out.append({"approved": bool(data.get("approved")), "reasons": list(data.get("reasons") or []), "intent_id": data.get("intent_id")})
        return out

    def _manifest_now(self, manifest: DeskManifest) -> DeskManifest:
        manifests = getattr(self.service, "manifests", None)
        current = manifests.get(manifest.id) if isinstance(manifests, Mapping) else None
        return current if isinstance(current, DeskManifest) else manifest

    def _live_now(self, manifest: DeskManifest) -> bool:
        live_desk = getattr(getattr(self.service, "gateway", None), "live_desk", None)
        if callable(live_desk):
            try:
                return bool(live_desk(manifest.id))
            except Exception:
                pass
        return self._manifest_now(manifest).live

    def _publish_run(self, manifest: DeskManifest, name: str, run: Mapping[str, Any], at: str, purpose: str, *, always: bool, row: Mapping[str, Any] | None = None) -> None:
        """A `desk.code_run` for the run: always for a deploy, an error or an intent; hourly when idle."""
        if not always:
            last = _epoch(row.get("last_published_at")) if row and row.get("last_published_at") else None
            if last is not None and _epoch(at) - last < int(self.config["idle_publish_seconds"]):
                return
        stdout = str(run.get("stdout") or "")
        parsed_line = stdout.rfind("STRATEGY-RESULT ")
        shown = stdout[:parsed_line].rstrip() if parsed_line > 0 else ""
        summary = {
            "intents": len(run.get("intents") or []),
            "notes": str(run.get("notes") or "")[:600],
            "log": list(run.get("log") or [])[-8:],
            **({"error": str(run["error"])[-600:]} if run.get("error") else {}),
        }
        text = (shown[-1200:] + "\n" if shown else "") + json.dumps(summary, separators=(",", ":"))[:2400]
        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        payload = {
            "session_id": f"{manifest.id}:{stamp}:strategy:{name}",
            "code_sha256": str(run.get("code_sha256") or "")[:64] or "0" * 64,
            "language": "python",
            "stdout": text[:4000],
            "exit_code": int(run.get("exit_code") or 0),
            "seconds": str(run.get("seconds") or "0"),
            "sandbox": None if not run.get("sandbox") else str(run["sandbox"])[-12:],
            "purpose": purpose[:200],
        }
        try:
            self.service.log.append(manifest.stream, "desk.code_run", payload, id=f"strategy:{manifest.id}:{name}:{at}", at=at)
            self.store.patch(manifest.id, name, last_published_at=at)
        except Exception as exc:
            self.service.alert("warning", f"strategy run not published: {type(exc).__name__}")


# ---------------------------------------------------------------------- helpers
#: The newest settled returns a record carries for the day-block bootstrap (leap: evidence).
RECORD_RETURNS = 500


def earned_ramp(settled: int, needed: int, full_size_multiple: Any = 3) -> Decimal:
    """How far a passing record is along its size ramp, 0 to 1: 0 at the `needed` settlements
    the evidence gate asked for, 1 at `full_size_multiple` x `needed`, linear between. A multiple
    of 1 or less is full size as soon as the gate passes (the step this replaced; Sept 17, 2026)."""
    needed = max(1, int(needed))
    try:
        multiple = Decimal(str(full_size_multiple))
    except (ArithmeticError, ValueError, TypeError):
        multiple = Decimal(3)
    if not multiple.is_finite():
        multiple = Decimal(3)
    if multiple <= 1:
        return Decimal(1)
    span = (multiple - 1) * needed
    return min(Decimal(1), max(Decimal(0), Decimal(int(settled) - needed) / span))


def _independent_outcomes(outcomes: list[Any]) -> list[Any]:
    """Aggregate every leg and partial exit of the same independent outcome, including
    losing legs. A group is never represented by a cherry-picked first winner."""
    from .mind import parse_outcome
    groups: dict[str, list[Any]] = {}
    for index, event in enumerate(outcomes):
        parsed = parse_outcome(event)
        key = parsed.group if parsed is not None and (parsed.asset_class == "event" or getattr(event, "seq", 0) or event.payload.get("opened_at")) else f"row:{index}"
        groups.setdefault(key, []).append(event)
    out = []
    for rows in groups.values():
        if len(rows) == 1:
            out.append(rows[0])
            continue
        size = sum((_dec(e.payload.get("quantity")) or Decimal(0)) for e in rows)
        cost = sum((_dec(e.payload.get("entry_price")) or Decimal(0)) * (_dec(e.payload.get("quantity")) or Decimal(0)) for e in rows)
        payload = dict(rows[0].payload)
        payload.update(quantity=str(size), entry_price=str(cost / size) if size else "0",
                       pnl=str(sum((_dec(e.payload.get("pnl")) or Decimal(0)) for e in rows)),
                       entry_fees=str(sum((_dec(e.payload.get("entry_fees")) or Decimal(0)) for e in rows)))
        if len({e.payload.get("instrument") for e in rows}) > 1:
            # A multi-strike payoff is not a binary Bernoulli bet. Use the day-block bootstrap.
            payload["instrument"] = "mixed:cluster"
        out.append(SimpleNamespace(payload=payload, at=max(str(e.at) for e in rows)))
    return out


def _summarize(fills: list[Any], outcomes: list[Any]) -> dict[str, Any]:
    """A strategy record from its fills and settled outcomes (the shape `record` returns)."""
    notional = sum((_dec(f.payload.get("price")) or Decimal(0)) * (_dec(f.payload.get("quantity")) or Decimal(0)) for f in fills)
    fees = sum(_dec(f.payload.get("fee") or f.payload.get("fees")) or Decimal(0) for f in fills)
    pnl = sum(_dec(o.payload.get("pnl")) or Decimal(0) for o in outcomes)
    wins = sum(1 for o in outcomes if (_dec(o.payload.get("pnl")) or Decimal(0)) > 0)
    return {
        "fills": len(fills),
        "filled_notional_usd": format(notional, "f"),
        "fees_usd": format(fees, "f"),
        "settled": len(outcomes),
        "wins": wins,
        "settled_pnl_usd": format(pnl, "f"),
        **_evidence_fields(outcomes),
    }


#: Market groups for pooled evidence: bets in one group fail together and share an edge. A series
#: outside every prefix list is its own group. Kept in step with `kalshi_favorites.GROUPS`.
EVIDENCE_GROUPS: dict[str, tuple[str, ...]] = {
    "crypto": ("KXBTC", "KXETH", "KXSOL", "KXXRP", "KXDOGE"),
    "commod": ("KXGOLD", "KXSILVER", "KXBRENT", "KXWTI", "KXCOPPER", "KXNATGAS", "KXGAS"),
    "weather": ("KXHIGH", "KXLOW", "KXRAIN", "KXSNOW"),
    "sports": ("KXMLB", "KXNFL", "KXNBA", "KXNHL", "KXNCAA", "KXUFC", "KXATP", "KXWTA", "KXPGA", "KXMLS", "KXEPL", "KXUCL", "KXLALIGA", "KXSERIEA", "KXBUNDESLIGA", "KXLIGUE", "KXF1", "KXNASCAR", "KXWNBA", "KXCFB"),
    "mentions": ("KXFEDMENTION", "KXMENTION", "KXTRUMPMENTION", "KXSAY"),
    "econ": ("KXFED", "KXCPI", "KXJOBS", "KXGDP", "KXUNRATE", "KXPAYROLL", "KXPCE", "KXPPI", "KXRETAIL", "KXTREASURY", "KXECB", "KXBOE", "KXBOJ"),
    "politics": ("KXTRUMP", "KXPRES", "KXSENATE", "KXHOUSE", "KXGOV", "KXAPPROV", "KXDJT", "KXCONGRESS", "KXSCOTUS", "KXELECTION"),
}


def group_of(series: str) -> str:
    """The evidence group of a Kalshi series (`KXBTCD` -> `crypto`); the series itself otherwise."""
    root = str(series or "").upper()
    for group, prefixes in EVIDENCE_GROUPS.items():
        if root.startswith(prefixes):
            return group
    return root or "other"


def _group_outcomes(outcomes: list[Any]) -> tuple[dict[str, list[Any]], dict[str, str]]:
    """Outcomes by evidence group, and the series -> group map the strategies read."""
    from .mind import parse_outcome

    groups: dict[str, list[Any]] = {}
    series_groups: dict[str, str] = {}
    for event in outcomes:
        parsed = parse_outcome(event)
        series = parsed.series if parsed is not None else ""
        if not series:
            key = str(event.payload.get("instrument") or "")
            parts = key.split(":")
            series = str(event.payload.get("market_id") or (parts[1] if len(parts) > 1 else "")).split("-", 1)[0].upper()
        group = group_of(series)
        if series:
            series_groups[series] = group
        groups.setdefault(group, []).append(event)
    return groups, series_groups


def _evidence_fields(outcomes: list[Any]) -> dict[str, Any]:
    """What `evidence.passes` reads from a strategy's settled outcomes (Sept 17, 2026: the old
    gate read only the count and the sign of the P&L).

    * `losses`: positions whose P&L after their entry fees is below zero. A `desk.outcome`'s `pnl`
      is net of a selling fill's fee but not of the opening fills' fees (`entry_fees`).
    * `asset_class`: the one asset class the outcomes that name an instrument traded, "mixed", or
      None when none does. An outcome with no instrument does not make the record unknown: a
      favorites record with one such outcome read as None, and None is judged by the bootstrap,
      a looser test for a lopsided payoff than the loss-rate rule.
    * `avg_entry_price`, weighted by quantity, and `avg_fee_per_contract`, the entry fees per
      contract, for the lopsided-payoff rule.
    * `returns`: the newest `RECORD_RETURNS` of `[settle day, P&L after entry fees / (entry price x
      quantity + entry fees)]`, oldest first.
    """
    outcomes = _independent_outcomes(outcomes)
    losses = 0
    classes: set[str | None] = set()
    quantity_total = Decimal(0)
    priced = Decimal(0)
    entry_fees_total = Decimal(0)
    returns: list[list[Any]] = []
    for event in outcomes:
        payload = event.payload
        entry_fees = _dec(payload.get("entry_fees")) or Decimal(0)
        net = (_dec(payload.get("pnl")) or Decimal(0)) - entry_fees
        if net < 0:
            losses += 1
        key = str(payload.get("instrument") or "")
        classes.add(key.split(":", 1)[0] if ":" in key else None)
        price, quantity = _dec(payload.get("entry_price")), _dec(payload.get("quantity"))
        if price is None or quantity is None or price <= 0 or quantity <= 0:
            continue
        quantity_total += quantity
        priced += price * quantity
        entry_fees_total += entry_fees
        cost = price * quantity + entry_fees
        returns.append([str(getattr(event, "at", None) or "")[:10], float(net / cost)])
    known = classes - {None}
    asset_class = None if not known else (next(iter(known)) if len(known) == 1 else "mixed")
    return {
        "independent_settled": len(outcomes),
        "losses": losses,
        "asset_class": asset_class,
        "avg_entry_price": format((priced / quantity_total).quantize(Decimal("0.0001")), "f") if quantity_total > 0 else None,
        "avg_fee_per_contract": format((entry_fees_total / quantity_total).quantize(Decimal("0.000001")), "f") if quantity_total > 0 else None,
        "returns": returns[-RECORD_RETURNS:],
    }


def _return_on_notional(record: Mapping[str, Any]) -> Decimal | None:
    """Settled P&L per dollar of filled notional, or None without fills."""
    notional = _dec(record.get("filled_notional_usd"))
    pnl = _dec(record.get("settled_pnl_usd"))
    if notional is None or pnl is None or notional <= 0:
        return None
    return (pnl / notional).quantize(Decimal("0.0001"))


def _jitter_params(params: Mapping[str, Any], seed: str, jitter: float) -> dict[str, Any]:
    """A copy of `params` with every number moved by up to `jitter` of itself, decided by the
    seed so a restart deals the same hand. Integers stay integers and at least 1; strings,
    booleans and lists are kept, because they are choices, not dials."""
    import hashlib

    out: dict[str, Any] = {}
    for index, (key, value) in enumerate(sorted(params.items())):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out[key] = value
            continue
        digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
        unit = int.from_bytes(digest[:8], "big") / float(2**64)  # 0..1
        factor = 1.0 + (unit * 2.0 - 1.0) * jitter
        if isinstance(value, int):
            out[key] = max(1, int(round(value * factor)))
        else:
            out[key] = round(value * factor, 6)
    return out


def _instrument_key(instrument: Any) -> str | None:
    """The `Instrument.key` of a logged instrument dict (a fill's), or None."""
    if isinstance(instrument, str):
        return instrument or None
    if not isinstance(instrument, Mapping):
        return None
    try:
        from .broker import Instrument

        return Instrument.from_dict(dict(instrument)).key
    except Exception:
        return None


def _strategy_of(session_id: str) -> str | None:
    """`<desk>:<stamp>:strategy:<name>` -> name, else None."""
    parts = session_id.split(":strategy:", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _epoch(at: Any) -> float:
    from datetime import datetime, timezone

    text = str(at or "").strip()
    for pattern in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return 0.0


def _plain_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be an object")
    text = json.dumps(dict(params), default=str)
    if len(text) > 4000:
        raise ValueError("params must be under 4000 characters as JSON")
    return json.loads(text)


def _parse_result(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None
    marker = stdout.rfind("STRATEGY-RESULT ")
    if marker < 0:
        return None
    line = stdout[marker + len("STRATEGY-RESULT "):].split("\n", 1)[0].strip()
    try:
        data = json.loads(line)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("intents", [])
    if not isinstance(data["intents"], list):
        data["intents"] = []
    return data


def _capped_quantity(args: Mapping[str, Any], cap_usd: Decimal) -> str:
    """The learning-size cap for a live desk's strategy: notional at the limit at most `cap_usd`."""
    price = _dec(args.get("limit_price")) or Decimal(0)
    quantity = _dec(args.get("quantity")) or Decimal(0)
    if price <= 0 or quantity <= 0:
        return str(args.get("quantity"))
    notional = quantity * price
    if notional <= cap_usd:
        return str(quantity)
    allowed = cap_usd / price
    instrument = args.get("instrument") or {}
    asset_class = str(instrument.get("asset_class") or "")
    if asset_class == "event":
        allowed = Decimal(int(allowed))
        return str(max(allowed, Decimal(1)))
    if asset_class == "future":
        # leap: futures -- contracts are whole, and one contract is the smallest learning size
        # there is (Sept 18, 2026: a $25 cap made Hilibrand III's first live perps entry 0.01
        # contracts and the risk engine refused it as fractional). The notional per contract is
        # price x contract size, read through the same resolver the tools use.
        from . import tools as tools_module

        size = Decimal(1)
        resolver = getattr(tools_module, "contract_size_resolver", None)
        if callable(resolver):
            try:
                size = Decimal(str(resolver(str(instrument.get("market_id") or instrument.get("symbol") or ""))))
            except Exception:
                size = Decimal(1)
        contracts = int(cap_usd / (price * size)) if price * size > 0 else 1
        return str(max(1, min(int(quantity), contracts)))
    return format(allowed.quantize(Decimal("0.00000001")), "f")


__all__ = ["DEFAULTS", "STARTERS", "Strategies", "StrategyStore"]
