"""K2, capacity at size, measured: what each positive Kalshi family could earn a day at 1x, 2x, 4x and 8x.

    python3 scripts/kalshi_capacity.py [--days 7] [--until ...] [--family NAME ...] [--json]

docs/goals/LTCM_KALSHI_SCALE.md, workstream K2 and scoreboard rows 2 and 3 (Sept 25, 2026). Read-only
everywhere: a snippet runs on the House box through `scripts.floor_box.client().exec` with sqlite
opened `mode=ro` (as `scripts/floor_watch.py` and `scripts/kalshi_watch.py` do) and returns the
families' orders, settlements and board records; everything heavy happens HERE, against Kalshi's
public, key-free market data (`api.elections.kalshi.com`), rate-limited to a few requests a second
and cached for the run. Nothing is written on the box, and no order is placed or cancelled.

Which families: every Kalshi family on the allocator's board that is proven or has a positive pooled
`mean_log`, plus any named with `--family` (`--family '*'` takes every Kalshi family on the board).

## What each number is, and its weakness

- **Orders** (the ledger's `book.order` buys on `kalshi` real and `kalshi-shadow` practice, owner
  `shares[0].agent`, a member being an agent born into the family): counted, real and practice apart
  and pooled, over `--days` (default 7) by the time the order was placed. A post-only order is a maker
  order; anything else (a crossing limit or a market order) a taker order. A rejected order never
  rested and is only counted. **Size** is contracts and dollars (quantity x limit, or x the reference
  price for a market order); the **price band** is the prices the family bid (maker) or took (taker),
  on the leg it bought (a NO order is priced in NO dollars). **Fill fraction per order** is the
  contracts `book.fill` rows gave the order (the House's `source: dust` reconciliations are not fills)
  over its quantity. **Time resting** is from the order's first row to its last (filled, cancelled,
  expired), or to now while it rests. Practice fills are simulated: all or nothing when the leg's ask
  goes strictly under the bid (`league/paper.py`), so a practice fill fraction says nothing about size.
- **Markets a day** are the distinct markets the family's orders named over the window's span (from
  its first order in the window): the ledger keeps only the COUNT of markets a wake is offered
  (`agent.woke` `offered`, shown for the last day as context), so the markets in a family's band are
  the ones its own rules chose to bid, as in `league/families.py` `capacity`.
- **Settlements a day** are the distinct markets its members settled (`book.settle`), real and practice.
- **Profit per dollar** is the board's `edge_per_dollar` (the family record's pooled return per dollar
  at risk, real and practice by their weights); the settlements' own P&L over cost in the window is
  shown beside it and used only when the board has none.
- **Size at 1x** is the family's current REAL position size: the board's `capacity.size_usd` (its
  stake x `allocator.position_share_event`, 20% a position on Kalshi), else the median real order, else
  the median order. Every order, real or practice, is re-sized to k x that many dollars at its own price,
  so the curve is in the family's real dollars whatever size its practice members bid.
- **The maker fill curve** is read from Kalshi's public trade prints (`GET /markets/trades`, newest
  first, paged by cursor). Per market (a family re-quotes a market several times; one market is one
  observation, as in the family record), the family's maker orders on it make a resting presence: at
  each print, the highest price any of its orders on that leg was resting at. A print is flow that
  would have met that bid when it printed at or under the bid on the bid's leg, whichever side took:
  a taker selling the leg at or under the bid would have hit the bid first, and a taker buying the leg
  under the bid shows a seller who would have crossed it. Block trades are left out. The flow is capped
  at k x size contracts and taken over k x size: that market's fill fraction at k. A market the family
  got filled on stops being watched at the fill, but a bid k times the size would have gone on resting,
  so its presence is extended, at its last price, to how long the family's bids on a market that never
  filled stayed (the median over those markets; else the median order's life; else an hour).
  Two readings are kept: the **estimate** (at or through, windows extended) and a **floor** (strictly
  through, the observed windows only, and never under what the real book actually filled there).
  Weaknesses: prints are flow that DID trade, not what a larger resting bid would have attracted (a
  bigger bid can draw more sellers, or scare them); a print AT the bid is shared with the queue ahead of
  it, which the estimate ignores and the floor excludes (a real NO bid at 0.97 on KXRAIN-26SEP21-CHI sat
  behind about 700 contracts printed at 0.97 for 84 minutes before its own 7 filled); a print under
  the bid is a lower bound on the seller behind it; windows extended past a fill are the family's
  typical patience, not its own; and a practice order's window ends where the simulator filled it, not
  where a real one would have. **The real-book check** reads each market the family bid on REAL money
  against the same prints at the bids' own size: the share its bids actually filled beside what the
  prints at or through, and strictly through, say they could have. Where the estimate runs above the
  real fills the queue is the difference, and the floor is the reading to plan on.
- **The taker fill curve** is the order book NOW (`GET /markets/orderbooks`, a snapshot: Kalshi's public
  API keeps no history of books, so no past taker order's depth can be read back): the markets now open
  in the family's series whose ask on its leg is inside its taken price band, soonest to close first
  (`--taker-markets`, default 30), and the contracts offered at or under the family's limit (the ask
  plus its usual allowance over the reference price, capped at the band's top), capped at k x size over
  k x size, averaged over those markets. When no market is inside the band now (a fifteen-minute crypto
  series has one market open at a time), the open markets of its series nearest the band are read at
  their touch instead, and the output says so. Beside it, the share of its past taker fills that were
  partial. Weaknesses: a snapshot at one hour (a game's book at 06:00Z is not its book an hour before the
  first pitch), liquidity that refills after a take is not seen, and the markets in band now need not be
  the ones it would take.
- **The family's fill rate at k** is the maker and taker rates weighted by the share of its markets each
  kind of order was placed on (a side with no measurement leaves the other alone, and the output says so).
- **Dollars a day at k** = markets a day x fill rate at k x k x size x profit per dollar. It is an
  expected value; the record's uncertainty (`bound`, `n`) is on the board and printed beside it.
- **Halves at** is the multiple where the fill rate falls under half the 1x rate (found by bisection
  on the monotone curve, up to 256x; `>256x` when it never does in that range).
- **The envelope that would use it**: the stake a position of k x size implies (k x size /
  `position_share_event`), times the members on disjoint events (C7) it would take to hold the family's
  positions: by Little's law its open positions are markets a day x fill rate x the median days from a
  fill to its settlement, a member holds 1 / `position_share_event` of them, so the members are that
  count x the share, rounded up (the family's active members, those with an order in the window, when
  nothing settled to measure the holding time by). Beside it, the capital in use: those open positions
  x k x size.
- **Totals**: capacity a day at 1x and 4x summed over the proven families and over every positive one,
  against the Kalshi envelope's committed and capital dollars on the board.

Times with no zone (the ledger's `at`, `--until`) are UTC. The box's `/workspace/.venv/bin/python` runs the
snippet in about two seconds; the public reads take a few minutes for a week (one paged prints read per
maker market and window, one listing per taker series, one batch of books per family), and `--cache DIR`
keeps closed windows' prints for the next run. `--box-json FILE` renders a snippet output saved earlier
(for instance by running `BOX_SNIPPET` through another checkout's `floor_box` client).
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MULTIPLES = (1, 2, 4, 8)
DAY = 86400.0
#: How far the halving search looks.
MAX_MULTIPLE = 256.0
#: The window a filled market is watched for when the family never left a bid unfilled to measure it by.
DEFAULT_PRESENCE_SECONDS = 3600.0
#: The fields of one order in the snippet's output, in order.
ORDER_FIELDS = ("real", "market", "leg", "limit", "reference", "quantity", "post_only", "placed", "end", "status", "filled",
                "first_fill", "liquidity", "fill_price", "agent", "settled")

BOX_SNIPPET = r'''
import sqlite3, pathlib, json, sys, time, statistics, collections
from datetime import datetime, timezone
since = sys.argv[1]
until = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
root = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else '/workspace/state')  # a third argument: the tests' state
wanted = [f for f in (sys.argv[4] if len(sys.argv) > 4 else '').split(',') if f]
def epoch(at):
    try:
        t = datetime.fromisoformat(str(at).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()  # a time with no zone is UTC, as the ledger's
def load(name):
    p = root / name
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}
db = sqlite3.connect((root / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True)
board = load('allocator-board.json')
health = load('health.json')
now = time.time()
newest = db.execute('select max(at) from ledger').fetchone()[0]
fams = (board.get('families') or {}).get('kalshi') or {}
chosen = [n for n, f in fams.items() if isinstance(f, dict) and (f.get('proven') or (f.get('mean_log') or 0) > 0)]
if '*' in wanted:
    chosen = list(fams)
chosen += [n for n in wanted if n != '*' and n not in chosen]
family_of = {}
for agent, payload in db.execute("select agent, payload from ledger where kind='agent.born'"):
    p = json.loads(payload)
    if p.get('venue') in ('kalshi', 'kalshi-shadow') and p.get('family') in chosen:
        family_of[agent] = p['family']
BOOKS = ('kalshi', 'kalshi-shadow')
orders = {}
def dec(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
for kind, agent, at, payload in db.execute("select kind, agent, at, payload from ledger where kind in ('book.order', 'book.fill', 'book.cancel') "
                                           "and at >= ? order by seq", (since,)):
    p = json.loads(payload)
    if p.get('book') not in BOOKS:
        continue
    oid = p.get('order_id')
    if kind == 'book.order':
        if oid not in orders:
            placed = epoch(p.get('submitted_at')) or epoch(at)
            if p.get('side') != 'buy' or placed is None or placed < epoch(since) or (until and placed >= epoch(until)):
                continue  # a sell, or an order placed outside the window (its later rows can fall inside it)
            shares = p.get('shares') or []
            who = (shares[0] or {}).get('agent') if shares else None
            if who not in family_of:
                continue
            inst = p.get('instrument') or {}
            orders[oid] = {'real': p['book'] == 'kalshi', 'market': inst.get('market_id') or inst.get('symbol'),
                           'leg': (inst.get('right') or 'yes').lower(), 'limit': dec(p.get('limit_price')),
                           'reference': dec(p.get('reference_price')), 'quantity': dec(p.get('quantity')),
                           'post_only': bool(p.get('post_only')), 'placed': placed, 'end': None, 'status': p.get('status'),
                           'filled': 0.0, 'first_fill': None, 'liquidity': None, 'fill_usd': 0.0, 'agent': who, 'settled': None}
        o = orders.get(oid)
        if o is None:
            continue
        o['status'] = p.get('status') or o['status']
        if o['status'] in ('filled', 'cancelled', 'canceled', 'expired', 'rejected'):
            o['end'] = o['end'] or epoch(at)
    elif kind == 'book.fill':
        o = orders.get(oid)
        if o is None or p.get('source') == 'dust' or p.get('side') not in (None, 'buy'):
            continue
        q = dec(p.get('quantity')) or 0.0
        o['filled'] += q
        o['fill_usd'] += q * (dec(p.get('price')) or 0.0)
        o['first_fill'] = o['first_fill'] or epoch(at)
        o['liquidity'] = o['liquidity'] or p.get('liquidity')
    elif kind == 'book.cancel':
        o = orders.get(oid)
        if o is not None and o['status'] not in ('filled',):
            o['end'] = o['end'] or epoch(at)
settles = collections.defaultdict(lambda: {'kalshi': {'n': 0, 'markets': set(), 'events': set(), 'pnl': 0.0, 'cost': 0.0, 'payout': 0.0, 'wins': 0},
                                           'kalshi-shadow': {'n': 0, 'markets': set(), 'events': set(), 'pnl': 0.0, 'cost': 0.0, 'payout': 0.0, 'wins': 0}})
settled_at = {}
sql = "select agent, at, payload from ledger where kind='book.settle' and at >= ?" + (" and at < ?" if until else "") + " order by seq"
for agent, at, payload in db.execute(sql, (since, until) if until else (since,)):
    fam = family_of.get(agent)
    if fam is None:
        continue
    p = json.loads(payload)
    if p.get('book') not in BOOKS:
        continue
    inst = p.get('instrument') or {}
    market = inst.get('market_id') or inst.get('symbol') or ''
    s = settles[fam][p['book']]
    s['n'] += 1
    s['markets'].add(market)
    s['events'].add('-'.join(market.split('-')[:2]))
    s['pnl'] += dec(p.get('pnl')) or 0.0
    s['cost'] += dec(p.get('cost')) or 0.0
    s['payout'] += dec(p.get('payout')) or 0.0
    s['wins'] += 1 if (dec(p.get('pnl')) or 0.0) > 0 else 0
    settled_at.setdefault((agent, p['book'], market), epoch(at))
wake_since = datetime.fromtimestamp((epoch(until) if until else (epoch(newest) or now)) - 86400, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
wakes = collections.defaultdict(lambda: collections.defaultdict(list))
for agent in family_of:
    sql = ("select json_extract(payload, '$.book'), json_extract(payload, '$.offered'), json_extract(payload, '$.intents') from ledger "
           "where agent = ? and kind = 'agent.woke' and at >= ?" + (" and at < ?" if until else ""))
    for book, offered, intents in db.execute(sql, (agent, wake_since, until) if until else (agent, wake_since)):
        if book in BOOKS:
            wakes[family_of[agent]][book].append((int(offered or 0), int(intents or 0)))
agents = board.get('agents') or {}
out = {'since': since, 'until': until, 'now': now, 'newest': newest, 'board_at': board.get('at'), 'health_at': health.get('at'),
       'release': health.get('release'), 'envelope': (board.get('envelope') or {}).get('kalshi') or {}, 'families': {}}
BOARD_KEYS = ('state', 'proven', 'n', 'n_eff', 'mean_log', 'bound', 'edge_per_dollar', 'stake_usd', 'members', 'members_living', 'members_real', 'capacity')
FIELDS = ('real', 'market', 'leg', 'limit', 'reference', 'quantity', 'post_only', 'placed', 'end', 'status', 'filled', 'first_fill', 'liquidity',
          'fill_price', 'agent', 'settled')
for fam in chosen:
    f = fams.get(fam) or {}
    row = {k: f.get(k) for k in BOARD_KEYS}
    row['real'] = {k: (f.get('real') or {}).get(k) for k in ('n', 'mean_log', 'bound')}
    row['on_board'] = fam in fams
    row['orders'] = []
    for oid, o in orders.items():
        if family_of.get(o['agent']) != fam:
            continue
        o = dict(o)
        o['fill_price'] = round(o.pop('fill_usd') / o['filled'], 4) if o['filled'] else None
        o['settled'] = settled_at.get((o['agent'], 'kalshi' if o['real'] else 'kalshi-shadow', o['market']))
        row['orders'].append([o[k] for k in FIELDS])
    row['settles'] = {book: dict(s, markets=len(s['markets']), events=len(s['events']), pnl=round(s['pnl'], 4), cost=round(s['cost'], 4),
                                 payout=round(s['payout'], 4)) for book, s in settles.get(fam, {}).items() if s['n']}
    row['wakes'] = {book: {'n': len(w), 'offered_median': statistics.median(o for o, _ in w), 'offered_max': max(o for o, _ in w),
                           'intents': sum(i for _, i in w)} for book, w in wakes.get(fam, {}).items() if w}
    row['agents_on_board'] = sorted([a, r.get('band'), r.get('stake_usd')] for a, r in agents.items()
                                    if isinstance(r, dict) and r.get('family') == fam and r.get('venue') == 'kalshi')
    out['families'][fam] = row
print(json.dumps(out, default=str))
'''


# ----------------------------------------------------------------------------------------- the box
def box_read(since: str, until: str | None, families: Sequence[str] = ()) -> dict:
    """Run the snippet on the House box (read-only) and return what it printed."""
    from scripts.floor_box import client, read_state, require_box

    run = client().exec(require_box(read_state()), ["/workspace/.venv/bin/python", "-c", BOX_SNIPPET, since, until or "", "",
                                                     ",".join(families)], timeout=300, on_output=None)
    text = (run.stdout or "").strip().splitlines()
    if not text:
        raise SystemExit(f"the box returned nothing: {(run.stderr or '')[-2000:]}")
    return json.loads(text[-1])


# ------------------------------------------------------------------------------- Kalshi's public data
def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _epoch(at: Any) -> float | None:
    """An ISO time as Unix seconds; one with no zone is UTC (the ledger's and `--since`'s form)."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()


class Public:
    """Kalshi's public, key-free market data for one run: trade prints, open markets by series, and books,
    through `ltcm.data.kalshi.KalshiMarketData` (its transport throttles each request `min_interval` apart
    and a 429 or a 5xx is retried after a pause). Every read is kept for the run, so a market's prints are
    read once however many orders name it; `cache_dir`, when given, keeps prints of windows that closed
    over ten minutes ago on disk for the next run (they cannot change)."""

    def __init__(self, data: Any = None, *, min_interval: float = 0.3, max_pages: int = 25, cache_dir: str | Path | None = None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        if data is None:
            from ltcm.data import HttpTransport
            from ltcm.data.kalshi import KalshiMarketData

            data = KalshiMarketData(HttpTransport(min_interval=min_interval), timeout=20.0)
        self.data = data
        self.max_pages = int(max_pages)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.sleep = sleep
        self.requests = 0
        self.truncated: list[str] = []
        self._trades: dict[tuple[str, int, int], list[dict]] = {}
        self._series: dict[str, list[dict]] = {}

    def _json(self, path: str, params: Mapping[str, Any] | None = None, *, what: str) -> Any:
        from ltcm.data import DataError, read_json

        url = self.data.url(path, dict(params or {}))
        for attempt in range(4):
            self.requests += 1
            try:
                return read_json(self.data.transport, url, headers={"Accept": "application/json"}, timeout=20.0, what=what)
            except DataError as exc:
                text = str(exc)
                if attempt == 3 or not any(f"HTTP {code}" in text for code in (429, 500, 502, 503, 504)):
                    raise
                self.sleep(2.0 * (attempt + 1))
        raise AssertionError("unreachable")

    def trades(self, ticker: str, min_ts: float, max_ts: float) -> list[dict]:
        """Every print on `ticker` from `min_ts` to `max_ts` (Unix seconds), newest first, as Kalshi sends them."""
        key = (ticker, int(min_ts), int(max_ts) + 1)
        if key in self._trades:
            return self._trades[key]
        cached = self._cache_path(key)
        if cached is not None and cached.exists():
            try:
                self._trades[key] = json.loads(cached.read_text())
                return self._trades[key]
            except ValueError:
                pass
        rows: list[dict] = []
        cursor = None
        for _ in range(self.max_pages):
            payload = self._json("/markets/trades", {"ticker": ticker, "min_ts": key[1], "max_ts": key[2], "limit": 1000, "cursor": cursor},
                                 what=f"kalshi trades {ticker}")
            rows += [row for row in payload.get("trades") or [] if isinstance(row, dict)]
            cursor = payload.get("cursor")
            if not cursor or not payload.get("trades"):
                break
        else:
            self.truncated.append(ticker)
        rows = [json.loads(json.dumps(row, default=str)) for row in rows]  # Decimals to plain JSON
        self._trades[key] = rows
        if cached is not None and key[2] < self.clock() - 600:
            cached.write_text(json.dumps(rows))
        return rows

    def _cache_path(self, key: tuple[str, int, int]) -> Path | None:
        return None if self.cache_dir is None else self.cache_dir / f"trades-{key[0]}-{key[1]}-{key[2]}.json"

    def open_markets(self, series: str, *, pages: int = 3) -> list[dict]:
        """The markets open now in one series (parsed by `KalshiMarketData.parse_market`)."""
        if series not in self._series:
            rows, cursor = [], None
            for _ in range(pages):
                self.requests += 1
                page = self.data.markets(series_ticker=series, status="open", limit=1000, cursor=cursor)
                rows += page["markets"]
                cursor = page.get("cursor")
                if not cursor or not page["markets"]:
                    break
            self._series[series] = rows
        return self._series[series]

    def books(self, tickers: Iterable[str]) -> dict[str, dict]:
        wanted = sorted(set(tickers))
        if not wanted:
            return {}
        self.requests += (len(wanted) + 99) // 100
        return self.data.orderbooks(wanted)


# ------------------------------------------------------------------------------------ the arithmetic
def print_price(trade: Mapping[str, Any], leg: str) -> float | None:
    """A print's price on `leg` in dollars (`yes_price_dollars`/`no_price_dollars`, or the integer-cent fields)."""
    for key, scale in ((f"{leg}_price_dollars", 1.0), (f"{leg}_price", 0.01)):
        value = _num(trade.get(key))
        if value is not None:
            return value * scale
    other = "no" if leg == "yes" else "yes"
    value = _num(trade.get(f"{other}_price_dollars"))
    if value is None and _num(trade.get(f"{other}_price")) is not None:
        value = _num(trade.get(f"{other}_price")) * 0.01
    return None if value is None else 1.0 - value


def print_count(trade: Mapping[str, Any]) -> float:
    value = _num(trade.get("count_fp"))
    if value is None:
        value = _num(trade.get("count"))
    return max(value or 0.0, 0.0)


def prints_of(trades: Iterable[Mapping[str, Any]]) -> list[tuple[float, float, float, float]]:
    """(time, yes price, no price, contracts) for each print that is not a block trade, oldest first."""
    out = []
    for t in trades:
        if t.get("is_block_trade"):
            continue
        at = _epoch(t.get("created_time"))
        yes, no, count = print_price(t, "yes"), print_price(t, "no"), print_count(t)
        if at is None or yes is None or no is None or count <= 0:
            continue
        out.append((at, yes, no, count))
    out.sort()
    return out


def order_rows(family: Mapping[str, Any]) -> list[dict]:
    return [dict(zip(ORDER_FIELDS, row)) for row in family.get("orders") or []]


def price_of(order: Mapping[str, Any]) -> float | None:
    """The price an order bid or took on its leg: its limit, or a market order's reference price."""
    for key in ("limit", "reference", "fill_price"):
        value = _num(order.get(key))
        if value is not None and 0 < value < 1:
            return value
    return None


def presences(orders: Sequence[Mapping[str, Any]], now: float) -> dict[tuple[str, str], dict]:
    """The family's maker orders by (market, leg): each order's resting window [placed, end or now] at its limit,
    what the real book filled there, and when the first fill came."""
    out: dict[tuple[str, str], dict] = {}
    for o in orders:
        if not o.get("post_only") or o.get("status") == "rejected" or _num(o.get("limit")) is None or not o.get("market"):
            continue
        key = (str(o["market"]), str(o.get("leg") or "yes"))
        p = out.setdefault(key, {"windows": [], "filled": 0.0, "real_filled": 0.0, "first_fill": None, "prices": [], "quantity": 0.0})
        start = float(o["placed"])
        end = float(o["end"]) if o.get("end") is not None else now
        p["windows"].append((start, max(end, start), float(o["limit"])))
        p["prices"].append(float(o["limit"]))
        p["quantity"] = max(p["quantity"], float(o.get("quantity") or 0.0))
        filled = float(o.get("filled") or 0.0)
        p["filled"] += filled
        if o.get("real"):
            p["real_filled"] += filled
        if filled > 0 and o.get("first_fill") is not None:
            p["first_fill"] = min(p["first_fill"] or float(o["first_fill"]), float(o["first_fill"]))
    for p in out.values():
        p["windows"].sort()
        p["start"] = p["windows"][0][0]
        p["end"] = max(w[1] for w in p["windows"])
        p["price"] = statistics.median(p["prices"])
        p["last_price"] = p["windows"][-1][2]
    return out


def typical_presence(pres: Mapping[Any, Mapping[str, Any]], orders: Sequence[Mapping[str, Any]]) -> tuple[float, str]:
    """How long the family keeps a bid on a market that does not fill: the median presence over such markets
    (at least three), else the median life of its maker orders that ended, else an hour."""
    unfilled = [p["end"] - p["start"] for p in pres.values() if p["filled"] <= 0]
    if len(unfilled) >= 3:
        return float(statistics.median(unfilled)), f"median of {len(unfilled)} unfilled markets"
    lives = [float(o["end"]) - float(o["placed"]) for o in orders if o.get("post_only") and o.get("end") is not None
             and o.get("status") != "rejected"]
    if lives:
        return float(statistics.median(lives)), f"median life of {len(lives)} maker orders"
    return DEFAULT_PRESENCE_SECONDS, "an hour (nothing to measure it by)"


def market_flow(presence: Mapping[str, Any], prints: Sequence[tuple[float, float, float, float]], leg: str, *,
                extend_to: float | None) -> dict[str, float]:
    """The contracts that printed at or under the family's resting bid while it rested: `estimate` (its window
    extended at its last price to `extend_to`), `at_or_through` and `through` (strictly under the bid) in the
    observed windows, and `floor` (the strictly-through flow, never under what the real book filled there)."""
    windows = presence["windows"]
    last_end = presence["end"]
    estimate = observed_flow = through = 0.0
    for at, yes, no, count in prints:
        price = yes if leg == "yes" else no
        bid = max((w[2] for w in windows if w[0] <= at <= w[1]), default=None)
        observed = bid is not None
        if bid is None and extend_to is not None and last_end < at <= extend_to:
            bid = presence["last_price"]
        if bid is None:
            continue
        if price <= bid + 1e-9:
            estimate += count
            observed_flow += count if observed else 0.0
        if observed and price < bid - 1e-9:
            through += count
    return {"estimate": estimate, "at_or_through": observed_flow, "through": through,
            "floor": max(through, float(presence.get("real_filled") or 0.0))}


def fraction(flow: float, contracts: float) -> float:
    """The share of an order of `contracts` that `flow` contracts would have filled."""
    if contracts <= 0:
        return 0.0
    return min(max(flow, 0.0), contracts) / contracts


def curve_rate(capacities: Sequence[float], multiple: float) -> float | None:
    """The mean fill fraction at `multiple` x size of markets whose flow fills `capacities[i]` x size (a
    market's capacity is its flow over its contracts at 1x)."""
    if not capacities:
        return None
    return sum(min(c / multiple, 1.0) for c in capacities) / len(capacities)


def halving(rate: Callable[[float], float | None], *, top: float = MAX_MULTIPLE) -> float | None:
    """The multiple (to 0.01) where `rate` first falls under half its 1x value, or None when it does not by `top`
    (and when there is no 1x rate). `rate` is non-increasing, so bisection finds it."""
    base = rate(1.0)
    if not base:
        return None
    half = base / 2.0
    if (rate(top) or 0.0) >= half:
        return None
    lo, hi = 1.0, top
    while hi - lo > 0.005:
        mid = (lo + hi) / 2.0
        if (rate(mid) or 0.0) < half:
            hi = mid
        else:
            lo = mid
    return round(hi, 2)


def book_depth(book: Mapping[str, Any], leg: str, limit: float) -> tuple[float | None, float]:
    """(the leg's ask, the contracts offered on `leg` at `limit` or better) in a book from
    `KalshiMarketData.parse_book`: the leg's asks are the other leg's bids at the complement."""
    other = "no" if leg == "yes" else "yes"
    levels = [(1.0 - float(price), float(count)) for price, count in book.get(other) or []]
    if not levels:
        return None, 0.0
    ask = min(price for price, _ in levels)
    return round(ask, 4), sum(count for price, count in levels if price <= limit + 1e-9)


def taker_band(orders: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The series, leg and price band a family's taker orders took, and its usual allowance over the reference."""
    takers = [o for o in orders if not o.get("post_only") and o.get("status") != "rejected" and price_of(o) is not None]
    if not takers:
        return None
    legs = [str(o.get("leg") or "yes") for o in takers]
    leg = max(set(legs), key=legs.count)
    series: dict[str, int] = {}
    for o in takers:
        s = str(o.get("market") or "").split("-")[0]
        series[s] = series.get(s, 0) + 1
    prices = [price_of(o) for o in takers if str(o.get("leg") or "yes") == leg]
    allowances = [float(o["limit"]) - float(o["reference"]) for o in takers
                  if _num(o.get("limit")) is not None and _num(o.get("reference")) is not None]
    return {"leg": leg, "series": sorted(series, key=lambda s: -series[s]), "lo": min(prices), "hi": max(prices),
            "allowance": max(statistics.median(allowances), 0.0) if allowances else 0.0}


def taker_markets(public: Public, band: Mapping[str, Any], *, now: float, limit: int, max_series: int = 6) -> list[dict]:
    """The markets open now in the band's series whose ask on its leg is inside its band, soonest to close first."""
    ask_key = f"{band['leg']}_ask"
    rows = []
    for series in band["series"][:max_series]:
        for m in public.open_markets(series):
            ask = _num(m.get(ask_key))
            close = _epoch(m.get("close_time"))
            resolves = _epoch(m.get("expected_expiration_time") or m.get("expiration_time")) or close
            if ask is None or close is None or close <= now:
                continue
            if band["lo"] - 1e-9 <= ask <= band["hi"] + 1e-9:
                rows.append({"ticker": m["ticker"], "ask": ask, "close": resolves})
    rows.sort(key=lambda r: (r["close"], r["ticker"]))
    return rows[:limit]


def nearest_markets(public: Public, band: Mapping[str, Any], *, now: float, limit: int, max_series: int = 6) -> list[dict]:
    """When no market is inside the band now: the open markets of its series whose ask on its leg is nearest the band,
    so the book at the touch is still read (the fifteen-minute crypto desks have one market open at a time)."""
    ask_key, mid = f"{band['leg']}_ask", (band["lo"] + band["hi"]) / 2.0
    rows = []
    for series in band["series"][:max_series]:
        for m in public.open_markets(series):
            ask, close = _num(m.get(ask_key)), _epoch(m.get("close_time"))
            if ask is not None and 0 < ask < 1 and close is not None and close > now:
                rows.append({"ticker": m["ticker"], "ask": ask, "close": close, "distance": abs(ask - mid)})
    rows.sort(key=lambda r: (r["distance"], r["close"], r["ticker"]))
    return rows[:limit]


def taker_capacities(books: Mapping[str, Mapping[str, Any]], markets: Sequence[Mapping[str, Any]], band: Mapping[str, Any],
                     size_usd: float) -> list[dict]:
    """For each market in band now: its ask, the family's limit there (the ask plus its allowance, at most the band's
    top), the contracts offered at or under it, and its capacity (that depth over the contracts of one 1x order)."""
    out = []
    for m in markets:
        book = books.get(m["ticker"])
        if not book:
            continue
        ask, _ = book_depth(book, band["leg"], 1.0)
        if ask is None:
            continue
        limit = min(max(ask + band["allowance"], ask), max(band["hi"], ask))
        _, depth = book_depth(book, band["leg"], limit)
        contracts = size_usd / limit if limit > 0 else 0.0
        out.append({"ticker": m["ticker"], "ask": ask, "limit": round(limit, 4), "depth": depth,
                    "capacity": depth / contracts if contracts > 0 else 0.0})
    return out


def _median(values: Iterable[float | None]) -> float | None:
    values = [float(v) for v in values if v is not None]
    return float(statistics.median(values)) if values else None


def describe(orders: Sequence[Mapping[str, Any]], settles: Mapping[str, Any] | None, *, since: float, end: float) -> dict[str, Any]:
    """One group's orders (real, practice or pooled) as counts, sizes, band, fills and time resting."""
    placed = [o for o in orders if o.get("status") != "rejected"]
    out: dict[str, Any] = {"orders": len(placed), "rejected": len(orders) - len(placed)}
    if not placed:
        return out
    first = min(float(o["placed"]) for o in placed)
    span = max((end - max(first, since)) / DAY, 1.0 / 24.0)
    markets = {o["market"] for o in placed}
    makers = [o for o in placed if o.get("post_only")]
    takers = [o for o in placed if not o.get("post_only")]
    fractions = [min(float(o.get("filled") or 0.0) / float(o["quantity"]), 1.0) for o in placed if float(o.get("quantity") or 0) > 0]
    prices = [price_of(o) for o in placed if price_of(o) is not None]
    rests = [((float(o["end"]) if o.get("end") is not None else end) - float(o["placed"])) / 60.0 for o in makers]
    taker_filled = [o for o in takers if float(o.get("filled") or 0) > 0]
    holds = [(float(o["settled"]) - float(o["first_fill"])) / DAY for o in placed
             if o.get("settled") is not None and o.get("first_fill") is not None and float(o["settled"]) >= float(o["first_fill"])]
    legs: dict[str, int] = {}
    for o in placed:
        legs[str(o.get("leg"))] = legs.get(str(o.get("leg")), 0) + 1
    settled = settles or {}
    out.update(days=round(span, 3), markets=len(markets), markets_per_day=round(len(markets) / span, 3),
               orders_per_market=round(len(placed) / len(markets), 2),
               contracts_median=_median(o.get("quantity") for o in placed),
               usd_median=_median(float(o["quantity"]) * price_of(o) for o in placed if price_of(o) is not None and o.get("quantity")),
               price_min=min(prices) if prices else None, price_median=_median(prices), price_max=max(prices) if prices else None,
               legs=legs, maker_orders=len(makers), taker_orders=len(takers),
               maker_markets=len({o["market"] for o in makers}), taker_markets=len({o["market"] for o in takers}),
               maker_fills=sum(1 for o in placed if o.get("liquidity") == "maker"),
               taker_fills=sum(1 for o in placed if o.get("liquidity") == "taker"),
               fill_fraction_mean=round(sum(fractions) / len(fractions), 4) if fractions else None,
               any_fill_share=round(sum(1 for f in fractions if f > 0) / len(fractions), 4) if fractions else None,
               full_fill_share=round(sum(1 for f in fractions if f >= 0.999) / len(fractions), 4) if fractions else None,
               rest_minutes_median=round(_median(rests), 1) if rests else None,
               taker_partial_share=(round(sum(1 for o in taker_filled if float(o["filled"]) < float(o["quantity"]) - 1e-9)
                                          / len(taker_filled), 4) if taker_filled else None),
               hold_days_median=round(_median(holds), 3) if holds else None,
               settled=int(settled.get("n") or 0), settled_markets=int(settled.get("markets") or 0),
               settlements_per_day=round(int(settled.get("markets") or 0) / span, 3),
               settled_pnl=settled.get("pnl"), settled_cost=settled.get("cost"),
               profit_per_dollar=(round(float(settled["pnl"]) / float(settled["cost"]), 4) if settled.get("cost") else None))
    return out


def family_capacity(name: str, family: Mapping[str, Any], public: Public | None, *, since: float, now: float, share: float,
                    multiples: Sequence[float] = MULTIPLES, taker_limit: int = 30, max_markets: int = 400) -> dict[str, Any]:
    """One family's capacity curve (see the module docstring for every number and its weakness)."""
    orders = order_rows(family)
    settles = family.get("settles") or {}
    groups = {"real": [o for o in orders if o.get("real")], "practice": [o for o in orders if not o.get("real")], "pooled": orders}
    books = {"real": settles.get("kalshi"), "practice": settles.get("kalshi-shadow")}
    pooled_settles = {k: (books["real"] or {}).get(k, 0) + (books["practice"] or {}).get(k, 0) for k in ("n", "markets", "pnl", "cost")}
    stats = {g: describe(rows, books.get(g) if g != "pooled" else pooled_settles, since=since, end=now) for g, rows in groups.items()}
    cap = family.get("capacity") or {}
    real_sizes = [float(o["quantity"]) * price_of(o) for o in groups["real"] if price_of(o) is not None and o.get("quantity")]
    size, size_basis = _num(cap.get("size_usd")), "the board's position size at its stake"
    if not size:
        size, size_basis = _median(real_sizes), "the median real order"
    if not size:
        size, size_basis = stats["pooled"].get("usd_median"), "the median order"
    edge_board = _num(family.get("edge_per_dollar"))
    edge, edge_basis = (edge_board, "board") if edge_board is not None else (stats["pooled"].get("profit_per_dollar"), "settlements")
    out: dict[str, Any] = {"family": name, "state": family.get("state"), "proven": bool(family.get("proven")), "n": family.get("n"),
                           "mean_log": family.get("mean_log"), "bound": family.get("bound"), "real_record": family.get("real"),
                           "stake_usd": family.get("stake_usd"), "board_capacity": cap, "size_usd": size, "size_basis": size_basis,
                           "edge_per_dollar": edge, "edge_basis": edge_basis, "stats": stats, "wakes": family.get("wakes") or {},
                           "members_living": family.get("members_living"), "notes": []}
    if not orders:
        out["notes"].append(f"no order by a member since {datetime.fromtimestamp(since, timezone.utc):%Y-%m-%dT%H:%MZ}")
        out.update(curve={}, halves_at=None, markets_per_day=0.0)
        return out
    # ---- makers: prints during each market's resting presence
    pres = presences(orders, now)
    if len(pres) > max_markets:
        keep = sorted(pres, key=lambda k: -pres[k]["start"])[:max_markets]
        out["notes"].append(f"maker markets sampled: the newest {max_markets} of {len(pres)}")
        pres = {k: pres[k] for k in keep}
    patience, patience_basis = typical_presence(pres, orders)
    # The real book's own markets, read on the same prints: what its bids got against what the prints say they could.
    real_pres = presences([o for o in orders if o.get("real")], now)
    maker_rows, checks, unread = [], [], []
    for (market, leg), p in sorted(pres.items()):
        filled = p["filled"] > 0
        extend_to = min(max(p["end"], p["start"] + patience), now) if filled else None
        top = extend_to if extend_to is not None else p["end"]
        if public is None:
            continue
        try:
            prints = prints_of(public.trades(market, p["start"] - 1, top + 1))
        except Exception as exc:  # noqa: BLE001 - a market whose prints cannot be read is left out and counted
            unread.append(f"{market}: {type(exc).__name__}: {str(exc)[:80]}")
            continue
        flow = market_flow(p, prints, leg, extend_to=extend_to)
        contracts = size / p["price"] if size and p["price"] > 0 else 0.0
        maker_rows.append({"market": market, "leg": leg, "price": p["price"], "prints": len(prints), "flow": flow["estimate"],
                           "floor_flow": flow["floor"], "filled": p["filled"],
                           "capacity": flow["estimate"] / contracts if contracts else 0.0,
                           "floor_capacity": flow["floor"] / contracts if contracts else 0.0})
        rp = real_pres.get((market, leg))
        if rp is not None and rp["quantity"] > 0:
            real_flow = market_flow(rp, prints, leg, extend_to=None)
            checks.append({"filled": fraction(rp["real_filled"], rp["quantity"]),
                           "at_or_through": fraction(real_flow["at_or_through"], rp["quantity"]),
                           "through": fraction(real_flow["through"], rp["quantity"])})
    if unread:
        out["notes"].append(f"prints unread on {len(unread)} maker markets, left out (first: {unread[0]})")
    # ---- takers: the book now in the family's band, and its past partial fills
    band = taker_band(orders)
    taker_rows: list[dict] = []
    if band is not None and public is not None and size:
        try:
            markets = taker_markets(public, band, now=now, limit=taker_limit)
            if not markets:
                markets = nearest_markets(public, band, now=now, limit=taker_limit)
                if markets:
                    band = dict(band, basis="nearest the band (none inside it now), at the touch plus the allowance")
                    out["notes"].append(f"no market open now in the taker band {band['leg']} {band['lo']:.2f}-{band['hi']:.2f}: "
                                        f"{len(markets)} of its series' open markets nearest it read at their touch instead")
            wide = dict(band, hi=1.0) if band.get("basis") else band
            taker_rows = taker_capacities(public.books(m["ticker"] for m in markets), markets, wide, size)
        except Exception as exc:  # noqa: BLE001 - one family's public read failing is a note, not the run
            out["notes"].append(f"taker books unread: {type(exc).__name__}: {str(exc)[:160]}")
        if not taker_rows:
            out["notes"].append(f"no market open now in the series {', '.join(band['series'][:4])} of the taker band "
                                f"{band['leg']} {band['lo']:.2f}-{band['hi']:.2f}")
    if public is None:
        out["notes"].append("offline: no public reads, so no fill curve")
    maker_caps = [r["capacity"] for r in maker_rows]
    floor_caps = [r["floor_capacity"] for r in maker_rows]
    taker_caps = [r["capacity"] for r in taker_rows]
    pooled = stats["pooled"]
    w_maker = pooled.get("maker_markets", 0)
    w_taker = pooled.get("taker_markets", 0)
    if maker_caps and w_taker and not taker_caps:
        out["notes"].append("taker side unmeasured: the curve is the maker side's alone")
    if taker_caps and w_maker and not maker_caps:
        out["notes"].append("maker side unmeasured: the curve is the taker side's alone")

    def blend(maker: Sequence[float], k: float) -> float | None:
        parts = [(w_maker, curve_rate(maker, k)), (w_taker, curve_rate(taker_caps, k))]
        parts = [(w, r) for w, r in parts if w and r is not None]
        total = sum(w for w, _ in parts)
        return sum(w * r for w, r in parts) / total if total else None

    mpd = float(pooled.get("markets_per_day") or 0.0)
    active = len({o["agent"] for o in orders if o.get("status") != "rejected"})
    hold = pooled.get("hold_days_median")
    curve = {}
    for k in multiples:
        rate, low = blend(maker_caps, k), blend(floor_caps, k)
        usd = mpd * rate * k * size * edge if rate is not None and size and edge is not None else None
        usd_floor = mpd * low * k * size * edge if low is not None and size and edge is not None else None
        stake = k * size / share if size and share else None
        # Little's law: positions open at once = positions a day x the days each is held.
        concurrent = mpd * rate * hold if rate is not None and hold is not None else None
        members = max(1, math.ceil(concurrent * share - 1e-9)) if concurrent is not None and share else max(active, 1)
        curve[f"{k:g}x"] = {"size_usd": round(k * size, 2) if size else None, "fill_rate": _round(rate, 4), "fill_floor": _round(low, 4),
                            "maker_fill": _round(curve_rate(maker_caps, k), 4), "taker_fill": _round(curve_rate(taker_caps, k), 4),
                            "usd_per_day": _round(usd, 2), "usd_per_day_floor": _round(usd_floor, 2),
                            "stake_usd": _round(stake, 2), "members": members,
                            "envelope_usd": _round(stake * members, 2) if stake else None,
                            "open_positions": _round(concurrent, 2),
                            "capital_in_use_usd": _round(concurrent * k * size, 2) if concurrent is not None and size else None}
    out.update(markets_per_day=mpd, active_members=active, patience_minutes=round(patience / 60.0, 1), patience_basis=patience_basis,
               taker_band=band, curve=curve, halves_at=halving(lambda k: blend(maker_caps, k)),
               halves_at_floor=halving(lambda k: blend(floor_caps, k)), maker_markets_read=len(maker_rows),
               maker_prints=sum(r["prints"] for r in maker_rows), taker_markets_read=len(taker_rows),
               real_check={"markets": len(checks), "filled": _round(_mean(c["filled"] for c in checks), 4),
                           "at_or_through": _round(_mean(c["at_or_through"] for c in checks), 4),
                           "through": _round(_mean(c["through"] for c in checks), 4)},
               maker_markets=maker_rows, taker_books=taker_rows)
    return out


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def totals(rows: Sequence[Mapping[str, Any]], envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Capacity a day at 1x and 4x, and the envelopes they would use, over the proven families and over every
    positive one, against the Kalshi envelope's committed and capital dollars."""
    def total(chosen: Sequence[Mapping[str, Any]], k: str, key: str) -> float:
        return round(sum(float(((r.get("curve") or {}).get(k) or {}).get(key) or 0.0) for r in chosen), 2)

    proven = [r for r in rows if r.get("proven") or r.get("state") in ("proven", "swing")]
    positive = [r for r in rows if r.get("proven") or float(r.get("mean_log") or 0.0) > 0]
    out = {"committed_usd": _num(envelope.get("committed_usd")), "capital_usd": _num(envelope.get("capital_usd"))}
    for label, chosen in (("proven", proven), ("positive", positive)):
        out[label] = {"families": len(chosen)}
        for k in ("1x", "4x"):
            out[label][k] = {"usd_per_day": total(chosen, k, "usd_per_day"), "usd_per_day_floor": total(chosen, k, "usd_per_day_floor"),
                             "envelope_usd": total(chosen, k, "envelope_usd"), "capital_in_use_usd": total(chosen, k, "capital_in_use_usd")}
    return out


def position_share(box: Mapping[str, Any]) -> tuple[float, str]:
    """`allocator.position_share_event` as the board applies it (a family's position size over its stake), else the
    local constitution's."""
    ratios = []
    for f in (box.get("families") or {}).values():
        size, stake = _num((f.get("capacity") or {}).get("size_usd")), _num(f.get("stake_usd"))
        if size and stake:
            ratios.append(round(size / stake, 4))
    if ratios:
        return float(statistics.median(ratios)), "the board (position size over stake)"
    from league.families import position_share as constitution_share

    return constitution_share("kalshi"), "the constitution"


def run(box: Mapping[str, Any], public: Public | None, *, taker_limit: int = 30, max_markets: int = 400,
        progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The whole study from the snippet's output and the public reads."""
    now = float(box.get("now") or time.time())
    since = _epoch(box.get("since")) or now - 7 * DAY
    end = _epoch(box.get("until")) or now
    share, share_basis = position_share(box)
    rows = []
    for name, family in sorted((box.get("families") or {}).items()):
        if progress:
            progress(f"{name}: {len(family.get('orders') or [])} orders")
        rows.append(family_capacity(name, family, public, since=since, now=end, share=share, taker_limit=taker_limit,
                                    max_markets=max_markets))
    rows.sort(key=lambda r: -float(((r.get("curve") or {}).get("1x") or {}).get("usd_per_day") or 0.0))
    return {"since": box.get("since"), "until": box.get("until"), "box_now": box.get("newest"), "board_at": box.get("board_at"),
            "release": box.get("release"), "position_share": share, "position_share_basis": share_basis,
            "envelope": box.get("envelope") or {}, "families": rows, "totals": totals(rows, box.get("envelope") or {}),
            "public_requests": getattr(public, "requests", 0), "truncated": getattr(public, "truncated", [])}


# ------------------------------------------------------------------------------------------ the text
def _fmt(value: Any, spec: str = "") -> str:
    if value is None:
        return "-"
    try:
        return format(value, spec)
    except (TypeError, ValueError):
        return str(value)


def render(result: Mapping[str, Any]) -> str:
    env = result.get("envelope") or {}
    lines = [f"# Kalshi capacity at size, {result.get('since')} .. {result.get('until') or 'now'} (ledger to {result.get('box_now')}, "
             f"board {result.get('board_at')}, release {result.get('release')})",
             f"position share {result.get('position_share')} ({result.get('position_share_basis')}); "
             f"Kalshi envelope committed ${_fmt(_num(env.get('committed_usd')), '.2f')} of ${_fmt(_num(env.get('capital_usd')), '.2f')}; "
             f"{result.get('public_requests')} public reads" + (f"; prints truncated on {result['truncated']}" if result.get("truncated") else "")]
    for r in result.get("families") or []:
        real = r.get("real_record") or {}
        lines.append("")
        lines.append(f"## {r['family']}  {r.get('state')}  n={r.get('n')} mean_log={_fmt(r.get('mean_log'), '.4f')} "
                     f"bound={_fmt(r.get('bound'), '.4f')} real n={real.get('n')} bound={_fmt(real.get('bound'), '.4f')}  "
                     f"stake ${r.get('stake_usd')}  size ${_fmt(r.get('size_usd'), '.2f')} ({r.get('size_basis')})  "
                     f"edge/$ {_fmt(r.get('edge_per_dollar'), '.4f')} ({r.get('edge_basis')})")
        board = r.get("board_capacity") or {}
        lines.append(f"   board: ${_fmt(board.get('usd_per_day'))}/day at fill {_fmt(board.get('fill_rate_at_size'))} on "
                     f"{_fmt(board.get('markets_per_day'))} markets/day; members living {r.get('members_living')}, active {r.get('active_members', 0)}")
        lines.append("   book      orders mkts mkts/d ord/mkt contracts   $/order price(min/med/max)  maker/taker fills m/t "
                     "fill/order any  full rest-min partial hold-d settled/d P&L/$")
        for g in ("real", "practice", "pooled"):
            s = (r.get("stats") or {}).get(g) or {}
            if not s.get("orders"):
                lines.append(f"   {g:9} {s.get('orders', 0):6} (rejected {s.get('rejected', 0)})")
                continue
            lines.append(f"   {g:9} {s['orders']:6} {s['markets']:4} {_fmt(s['markets_per_day'], '6.2f')} {_fmt(s['orders_per_market'], '7.2f')} "
                         f"{_fmt(s['contracts_median'], '9.1f')} {_fmt(s['usd_median'], '9.2f')} "
                         f"{_fmt(s['price_min'], '.2f')}/{_fmt(s['price_median'], '.2f')}/{_fmt(s['price_max'], '.2f')}      "
                         f"{s['maker_orders']:5}/{s['taker_orders']:<5} {s['maker_fills']:4}/{s['taker_fills']:<4} "
                         f"{_fmt(s['fill_fraction_mean'], '10.2f')} {_fmt(s['any_fill_share'], '.2f')} {_fmt(s['full_fill_share'], '.2f')} "
                         f"{_fmt(s['rest_minutes_median'], '8.1f')} {_fmt(s['taker_partial_share'], '7.2f')} {_fmt(s['hold_days_median'], '6.2f')} "
                         f"{_fmt(s['settlements_per_day'], '9.2f')} {_fmt(s['profit_per_dollar'], '.3f')}")
        wakes = r.get("wakes") or {}
        if wakes:
            lines.append("   wakes (last day): " + "; ".join(f"{b} {w['n']} wakes, offered median {w['offered_median']} max {w['offered_max']}, "
                                                             f"{w['intents']} intents" for b, w in sorted(wakes.items())))
        if r.get("curve"):
            band = r.get("taker_band")
            check = r.get("real_check") or {}
            lines.append(f"   maker: {r.get('maker_markets_read')} markets, {r.get('maker_prints')} prints, patience {r.get('patience_minutes')} min "
                         f"({r.get('patience_basis')})" + (
                             f"; real-book check on {check['markets']} markets at their own size: filled {_fmt(check['filled'], '.2f')}, "
                             f"prints at or through say {_fmt(check['at_or_through'], '.2f')}, strictly through {_fmt(check['through'], '.2f')}"
                             if check.get("markets") else ""))
            if band:
                lines.append(f"   taker: band {band['leg']} {band['lo']:.2f}-{band['hi']:.2f} +{band['allowance']:.2f} in "
                             f"{', '.join(band['series'][:4])}; {r.get('taker_markets_read')} books read now")
            lines.append("   multiple  size$  fill (floor)   maker  taker   $/day (floor)   stake$  envelope$  capital-in-use$")
            for k, c in r["curve"].items():
                lines.append(f"   {k:>8} {_fmt(c['size_usd'], '6.2f')}  {_fmt(c['fill_rate'], '.2f')} ({_fmt(c['fill_floor'], '.2f')})  "
                             f"{_fmt(c['maker_fill'], '6.2f')} {_fmt(c['taker_fill'], '6.2f')}  {_fmt(c['usd_per_day'], '7.2f')} "
                             f"({_fmt(c['usd_per_day_floor'], '.2f')})  {_fmt(c['stake_usd'], '7.2f')} {_fmt(c['envelope_usd'], '9.2f')} "
                             f"{_fmt(c['capital_in_use_usd'], '9.2f')}")
            halves = r.get("halves_at")
            floor = r.get("halves_at_floor")
            lines.append(f"   fills halve at {f'{halves:g}x' if halves else f'>{MAX_MULTIPLE:g}x'} "
                         f"(floor {f'{floor:g}x' if floor else f'>{MAX_MULTIPLE:g}x'})")
        for note in r.get("notes") or []:
            lines.append(f"   note: {note}")
    t = result.get("totals") or {}
    lines.append("")
    for label in ("proven", "positive"):
        row = t.get(label) or {}
        a, b = row.get("1x") or {}, row.get("4x") or {}
        lines.append(f"TOTAL {label} ({row.get('families', 0)} families): ${a.get('usd_per_day')}/day at 1x (floor ${a.get('usd_per_day_floor')}), "
                     f"${b.get('usd_per_day')}/day at 4x (floor ${b.get('usd_per_day_floor')}); envelope ${a.get('envelope_usd')} at 1x, "
                     f"${b.get('envelope_usd')} at 4x (capital in use ${a.get('capital_in_use_usd')} / ${b.get('capital_in_use_usd')}); "
                     f"Kalshi committed ${_fmt(t.get('committed_usd'), '.2f')} of ${_fmt(t.get('capital_usd'), '.2f')}")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------- the CLI
def parser() -> argparse.ArgumentParser:
    from scripts.floor_watch import normalize_since

    out = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_argument("--days", type=float, default=7.0, help="the window, in days back from --until (default 7)")
    out.add_argument("--until", type=normalize_since, default=None, help="the window's end, an ISO time (default now)")
    out.add_argument("--family", action="append", default=[], help="a family to add (repeatable); '*' for every Kalshi family on the board")
    out.add_argument("--taker-markets", type=int, default=30, help="books read now per taker family (default 30)")
    out.add_argument("--max-markets", type=int, default=400, help="maker markets read per family, newest first (default 400)")
    out.add_argument("--min-interval", type=float, default=0.3, help="seconds between public requests (default 0.3)")
    out.add_argument("--cache", default=None, help="a directory to keep closed windows' prints in between runs")
    out.add_argument("--box-json", default=None, help="read the snippet's output from this file instead of the box")
    out.add_argument("--offline", action="store_true", help="no public reads: the ledger's side only")
    out.add_argument("--json", action="store_true")
    return out


def main(argv: Sequence[str] | None = None) -> None:
    args = parser().parse_args(argv)
    end = _epoch(args.until) if args.until else time.time()
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(end - args.days * DAY))
    if args.box_json:
        box = json.loads(Path(args.box_json).read_text())
    else:
        box = box_read(since, args.until, args.family)
    public = None if args.offline else Public(min_interval=args.min_interval, cache_dir=args.cache)
    result = run(box, public, taker_limit=args.taker_markets, max_markets=args.max_markets,
                 progress=lambda text: print(text, file=sys.stderr, flush=True))
    print(json.dumps(result, default=str, indent=1) if args.json else render(result))


if __name__ == "__main__":
    main()
