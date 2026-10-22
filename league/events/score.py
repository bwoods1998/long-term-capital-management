"""Settling the event lane's intents after their exit (PREREG-EVL-1 section 5): the listing exchange's auction
prints, the cost allowance, r, b and a, and the TRADABLE flag the screen reads.

Built to the frozen text (docs/prereg/PREREG-EVL-1.md, sha256 f8254c19..., registered 2026-10-19T01:08:38Z).
AUCTION PRICES come from Alpaca's SIP historical trades (`GET /v1/alpaca/v2/stocks/<SYM>/trades`, through the
gateway, read once 15 minutes old). The OPEN of session D is the first regular-session trade on D from the stock's
listing exchange carrying condition `O` (searched from the open, page by page, until found or the close), or, when the
listing exchange printed no `O` that day, its `Q` official-open record; the CLOSE is the listing exchange's trade
carrying condition `6`, else its `M` official-close record, searched from 5 seconds before the close to 5 minutes
after. The listing exchange is the universe row's `exchange` for (entry_day, symbol) (the asset's exchange on a live
day, the previous session's closing-print exchange on a backfilled one), coded by `league.events.universe.
EXCHANGE_CODES` (NYSE `N`, NASDAQ `Q`, AMEX `A`, ARCA `P`, BATS `Z`); the benchmarks SPY and IWM list on ARCA. Every
print found (or found absent, once the whole window is readable) is kept in `marks` (label `open`, `close` or `first`;
source `sip:<x>:<conditions>`, or `none`), so a print is read from the tape once. The SIP daily bars of the window
(raw and `adjustment=all`) are fetched beside them: the gap between print and bar is in the store, and a split or
dividend inside the hold applies through each day's ratio of adjusted to raw close.

- NO AUCTION PRINT at entry: the intent is `skipped:no-auction` (no outcome). NO EVENT IS VOIDED AFTER ENTRY: with no
  exit print on the exit day the position exits at the next session's closing cross; with none within 5 sessions, at
  the first SIP trade (any venue) of each next session; with none after 20 sessions, at 0. A later exit than planned
  is kept in meta `exit:<program>:<version>:<event>` ({day, kind, planned}) for the screen.
- The benchmark is priced at its own prints at the same two auctions (at an exit on a first trade: that session's
  opening cross; at 0: that session's closing cross). Its print missing although the tape is readable (never seen) is
  waited for one more session, then replaced by its daily bar (source `bar-fallback`).
- The benchmark's entry print is read first: it shows the day's tape is complete, so a stock print missing beside it
  is a missing print, while a tape not yet readable makes the intent wait.
- COSTS per side: 0.5 bp + 5 bp of impact when the entry day's ADV >= $10,000,000, else 10 bp, + fees at the Probe
  notional N = 5% of the account equity at the previous close: $0.01 / N on each side (CAT) and $0.01 / N more on the
  sale (TAF). With no equity on record the fees are not known and are left out (such an event is not TRADABLE).
- r = exit_px (1 - c_exit) / (entry_px (1 + c_entry)) - 1; b = bench_exit / bench_entry - 1; a = r - b (prices
  adjusted). TRADABLE: 1.25 x the previous SIP close (universe `prev_close`; one share under the real-money limit
  price) <= 10% of the account equity at the previous close (meta `equity:<day>` = the equity at that day's close;
  else the latest earlier record; none: NULL).
The outcome row (`settled`) and the intent's move to `exited` are one transaction, so a rerun changes nothing. The NBBO
stress (`spread_*`, `stress_r`) is left NULL here.

THE BATCHED SCORE (release 1019i, PREREG-EVL-8's harness plan H1, the flywheel's F1: the nightly score settled 15-25
events a minute, A95, while every intent paid two daily-bar requests of its own). A pass first PREFETCHES the daily bars
(raw and `adjustment=all`) of every due intent's symbol and of both benchmarks ONCE over the union window (`prefetch`:
from the earliest due entry session to the pass's own day, `SYMBOLS_PER_REQUEST` (200) symbols a request, page by page,
the very requests `universe.fetch_daily_bars` makes) INTO A CACHE THAT LIVES ONLY FOR THE PASS (`Prefetch`; release
1019i's review: never into `bars`), and then `settle_one(prefetched=...)` skips its own two fetches when the cache holds
every bar its settlement reads (`Prefetch.serves`: the symbol's and the benchmark's, raw and adjusted, at entry and at
exit), reads its ratios from the cache, and writes to `bars` EXACTLY THE ROWS ITS TWO FETCHES WOULD HAVE WRITTEN
(`Prefetch.store_window`: {symbol, benchmark} x {raw, all} x [entry day, exit day], at the pass's time), so `bars` ends
every pass as under release 1019h: no bar of a skipped or waiting intent, none outside an intent's own window, no older
day re-based to today's basis (league/events/done.py `_ratio`, Done's fill gaps, reads those rows). A bar the vendor did
not send (a missing bar), or a chunk that failed, falls back to the intent's own two fetches, exactly as before. Alpaca
adjusts every bar to today's basis whatever the window, so every outcome row and every `bars` row is the same, byte for
byte (league/tests/test_events_score_batch.py's golden tape, with a missing bar and a split, and two nights with a
split between them). Prints stay read once per (symbol, day, label) (`tape_print`, `marks`). THE ORDER (`order_due`):
the seating versions (programs.SEATING) and their controls (screen.control_of) settle first, then every other record,
each group in `due`'s order, so a pass its bound cuts has settled what the looks of real money wait for. THE SWITCH:
league/config.json `events.score_batch` (`batch_on`; a missing key is ON, false restores the per-intent path of release
1019h exactly: `due`'s order and the two fetches an intent). THE PARITY NIGHT (`parity_due`, `parity_window`,
`check_parity`): every night until the first on which a flag is written (meta `PARITY_FIRST`: a night the batched
score settled only from a failed prefetch, or whose sample the cache served none of, tested nothing and is no parity
night), a sample of `PARITY_SHARE` (5%) of each prefetch's intents (`parity_sampled`, by sha256 of the intent's key) is settled TWICE IN
MEMORY BEFORE ANY OF THEM IS WRITTEN, by the batched path (the cache) and by the per-intent path (`Narrow`: the intent's
own two requests, read and never stored), and only an EQUALITY FLAG is written (`score_parity`: 1 when every outcome
field and the late exit are identical, else 0; never a value); an intent the cache does not serve is no test of the
batched path and gets no flag. A FLAG 0 FAILS CLOSED: it sets THE PARITY LATCH (meta `PARITY_LATCH`, `latch`), and that
pass and every later one settle every intent by the per-intent path, whatever `events.score_batch` says, until the
captain clears it (`unlatch`; `python3 -m league.events --state DIR score-unlatch`), while league/ops/evl_health.py
raises `evl_score_parity`, which the gateway mails. `events.score_parity` true runs the check every night, false never.
Each pass's counts (requests by kind, seconds, the parity flags, the latch) go into its receipt for the daily report's
settle-pace line (league/ops/daily_report.py `settle_line`).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import time
import urllib.parse
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from . import calendar as C
from . import store as S
from . import universe as U

BENCH_CODE = U.EXCHANGE_CODES["ARCA"]
#: (the auction print's condition, the official record's that stands in when the listing exchange printed none)
CONDITIONS = {"open": ("O", "Q"), "close": ("6", "M")}
LIMIT_MULTIPLE = 1.25
CLOSE_BEFORE = dt.timedelta(seconds=5)
CLOSE_AFTER = dt.timedelta(minutes=5)
TAPE_DELAY = dt.timedelta(minutes=16)
TRADES_PAGE = 10000
MAX_PAGES = 400
NEXT_CLOSES = 5
ZERO_AFTER = 20
FEE_BP = 0.5
IMPACT_BP = 5.0
IMPACT_BP_THIN = 10.0
LIQUID_ADV = 10_000_000.0
PROBE_SHARE = 0.05
CAT_USD = 0.01
TAF_USD = 0.01
TRADABLE_SHARE = 0.10
ACCOUNT_PATH = "/v1/alpaca/v2/account"
#: THE BATCHED SCORE (release 1019i, the module docstring): its switch's default (league/config.json
#: `events.score_batch`), both benchmarks (PREREG-EVL-1 section 2: IWM under $50,000,000 of ADV, else SPY), the parity
#: night's sample share and its meta key (the first night a parity flag was written), and the outcome fields
#: the parity compares (every column the settlement writes but its time).
BATCH_DEFAULT = True
BENCHMARKS = ("SPY", "IWM")
PARITY_SHARE = 0.05
PARITY_FIRST = "evl:score:batch:first_night"
#: THE PARITY LATCH (release 1019i's review: a flag 0 FAILS CLOSED): set by the first parity flag 0, it turns the
#: batched score off for every later pass, whatever `events.score_batch` says, until the captain clears it (`unlatch`);
#: league/ops/evl_health.py raises `evl_score_parity` while it stands.
PARITY_LATCH = "evl:score:batch:latched"
PARITY_FIELDS = ("entry_px", "exit_px", "bench", "bench_entry", "bench_exit", "cost_entry_bp", "cost_exit_bp", "r", "b",
                 "a", "tradable", "status")
BARS_PATH = "/v1/alpaca/v2/stocks/bars"


class Waiting(Exception):
    """The tape or the calendar is not complete yet: the intent is left as it is for the next run."""


# ----------------------------------------------------------------------------------------------------------- costs
def impact_bp(adv20: float) -> float:
    return IMPACT_BP if float(adv20) >= LIQUID_ADV else IMPACT_BP_THIN


def cost_bp(adv20: float, equity: float | None, side: str) -> float:
    """The per-side cost allowance in basis points: 0.5 + impact + the fees over the Probe notional (5% of equity)."""
    if side not in ("entry", "exit"):
        raise ValueError("side is 'entry' or 'exit'")
    fees = 0.0
    if equity is not None and equity > 0:
        notional = PROBE_SHARE * equity
        fees = (CAT_USD + (TAF_USD if side == "exit" else 0.0)) / notional * 1e4
    return FEE_BP + impact_bp(adv20) + fees


def after_cost_return(entry_px: float, exit_px: float, c_entry_bp: float, c_exit_bp: float) -> float:
    """r = exit_px x (1 - c_exit) / (entry_px x (1 + c_entry)) - 1, the costs in basis points."""
    return exit_px * (1.0 - c_exit_bp / 1e4) / (entry_px * (1.0 + c_entry_bp / 1e4)) - 1.0


# ---------------------------------------------------------------------------------------------------------- equity
def equity_key(day: dt.date) -> str:
    return f"equity:{day.isoformat()}"


def equity_on(store: S.Store, day: dt.date) -> float | None:
    """The account equity at `day`'s close, else the latest earlier record, else None."""
    for row in store.db.execute("SELECT key, value FROM meta WHERE key>=? AND key<=? ORDER BY key DESC",
                                ("equity:", equity_key(day))):
        try:
            dt.date.fromisoformat(str(row["key"])[len("equity:"):])
            value = float(row["value"])
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    return None


def record_equity(store: S.Store, gw: Any, *, now: dt.datetime | None = None, overwrite: bool = False
                  ) -> dict[str, Any]:
    """The account equity at today's close (`GET /v1/alpaca/v2/account` -> `equity`) into meta `equity:<day>`, its
    time into `equity:<day>:at`: the same rule as the CLI's `equity` command (feat/evl-shadow). Run just after the
    close; it refuses before the close or on a day with no session, and keeps the first record unless `overwrite`."""
    now = now or S.utc_now()
    day = now.astimezone(C.NY).date()
    session = C.session(store, day)
    if session is None or now < session.close_at:
        return {"skipped": f"no closed session on {day}"}
    have = store.meta(equity_key(day))
    if have is not None and not overwrite:
        return {"kept": have}
    equity = float((gw.get_json(ACCOUNT_PATH) or {})["equity"])
    if not math.isfinite(equity) or equity < 0:
        raise ValueError(f"not an account equity: {equity!r}")
    store.set_meta(equity_key(day), repr(equity))
    store.set_meta(equity_key(day) + ":at", S.iso(now))
    return {"day": day.isoformat(), "equity": equity}


# ----------------------------------------------------------------------------------------------------------- tape
def _trades(gw: Any, symbol: str, start: dt.datetime, end: dt.datetime, now: dt.datetime,
            limit: int = TRADES_PAGE) -> Iterator[Mapping[str, Any]]:
    """The SIP trades of `symbol` in [start, end), clipped to 16 minutes ago, in time order (page by page)."""
    end = min(end, now - TAPE_DELAY)
    if end <= start:
        return
    path = f"/v1/alpaca/v2/stocks/{urllib.parse.quote(symbol, safe='.')}/trades"
    token = None
    for _ in range(MAX_PAGES):
        page = gw.get_json(path, {"start": S.iso(start), "end": S.iso(end), "feed": "sip", "limit": limit,
                                  "page_token": token}) or {}
        yield from page.get("trades") or []
        token = page.get("next_page_token")
        if not token:
            return
    raise RuntimeError(f"{symbol}: more than {MAX_PAGES} pages of trades")


def _window(session: C.Session, kind: str) -> tuple[dt.datetime, dt.datetime]:
    if kind == "close":
        return session.close_at - CLOSE_BEFORE, session.close_at + CLOSE_AFTER
    return session.open_at, session.close_at  # the opening cross, or the session's first trade




def _mark(store: S.Store, symbol: str, day: dt.date, label: str, px: float | None, t: str | None, source: str,
          now: dt.datetime) -> None:
    store.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, ?, ?, ?, ?) "
                     "ON CONFLICT(symbol, day, label) DO UPDATE SET px=excluded.px, t=excluded.t, source=excluded.source, "
                     "fetched_at=excluded.fetched_at", (symbol, day.isoformat(), label, px, t, source, S.iso(now)))


def tape_print(store: S.Store, gw: Any, symbol: str, code: str, session: C.Session, kind: str, now: dt.datetime
               ) -> tuple[float | None, bool]:
    """(price, known): the session's opening cross ('open') or closing cross ('close') from listing exchange `code`
    (its `Q` / `M` official record when it printed no `O` / `6`), or its first trade on any venue ('first'). `known`
    is False while the window is not yet readable in full; (None, True) means there was none. Kept in `marks` (source
    `sip:<x>:<conditions>`, or `none`), so the tape is read once."""
    symbol = symbol.upper()
    row = store.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=?",
                           (symbol, session.day.isoformat(), kind)).fetchone()
    if row is not None:
        return (None if row["px"] is None else float(row["px"])), True
    start, end = _window(session, kind)
    complete = now - TAPE_DELAY >= end
    stand_in = None
    for trade in _trades(gw, symbol, start, end, now, limit=1 if kind == "first" else TRADES_PAGE):
        if kind == "first":
            return _keep(store, symbol, session.day, kind, trade, now), True
        if trade.get("x") != code:
            continue
        conds = trade.get("c") or []
        if CONDITIONS[kind][0] in conds:
            return _keep(store, symbol, session.day, kind, trade, now), True
        if stand_in is None and CONDITIONS[kind][1] in conds:
            stand_in = trade
    if not complete:
        return None, False
    if stand_in is not None:
        return _keep(store, symbol, session.day, kind, stand_in, now), True
    _mark(store, symbol, session.day, kind, None, None, "none", now)
    return None, True


def _keep(store: S.Store, symbol: str, day: dt.date, kind: str, trade: Mapping[str, Any], now: dt.datetime) -> float:
    px = float(trade["p"])
    conds = ",".join(str(c).strip() for c in (trade.get("c") or []) if str(c).strip())
    _mark(store, symbol, day, kind, px, str(trade.get("t")), f"sip:{trade.get('x')}:{conds}", now)
    return px


def _bar(store: S.Store, symbol: str, day: dt.date, adj: str) -> Mapping[str, Any] | None:
    return U.bars(store, symbol, [day], adj).get(day.isoformat())


def _positive(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def bench_print(store: S.Store, gw: Any, bench: str, session: C.Session, kind: str, now: dt.datetime) -> float:
    """The benchmark's own print at this auction ('open' or 'close'); missing on a readable tape, its daily bar once
    one more session has closed (source `bar-fallback`). Raises Waiting until then."""
    px, known = tape_print(store, gw, bench, BENCH_CODE, session, kind, now)
    if px is not None:
        return px
    if not known:
        raise Waiting(f"{bench} {kind} {session.day}: tape not complete")
    after = C.sessions(store, session.day + dt.timedelta(days=1), session.day + dt.timedelta(days=10))
    if not after or after[0].close_at + TAPE_DELAY > now:
        raise Waiting(f"{bench} {kind} {session.day}: no print; a session's wait before its bar")
    U.fetch_daily_bars(store, gw, [bench], session.day, session.day, adj="raw", now=now)
    bar = _bar(store, bench, session.day, "raw")
    value = _positive(bar.get("o" if kind == "open" else "c")) if bar else None
    if value is None:
        raise Waiting(f"{bench} {kind} {session.day}: no print and no bar")
    _mark(store, bench, session.day, kind, value, None, "bar-fallback", now)
    return value


def _ratio(store: S.Store, symbol: str, day: dt.date) -> float:
    """Alpaca's adjusted / raw daily close for `day` (1.0 when either bar is missing)."""
    raw, adj = _bar(store, symbol, day, "raw"), _bar(store, symbol, day, "all")
    rc, ac = (_positive(raw.get("c")) if raw else None), (_positive(adj.get("c")) if adj else None)
    return ac / rc if rc and ac else 1.0


# -------------------------------------------------------------------------------------------------------- settle
def due(store: S.Store, now: dt.datetime) -> list[dict[str, Any]]:
    """Intents (planned or entered) whose planned exit session closed at least 16 minutes before `now`."""
    out = []
    for row in store.db.execute("SELECT i.*, s.close_at AS exit_close FROM intents i JOIN sessions s ON s.day=i.exit_day "
                                "WHERE i.status IN ('planned', 'entered') ORDER BY i.exit_day, i.entry_day, i.program, "
                                "i.version, i.event"):
        if S.parse_iso(row["exit_close"]) + TAPE_DELAY <= now:
            out.append(dict(row))
    return out


def _universe(store: S.Store, day: str, symbol: str) -> Mapping[str, Any] | None:
    row = store.db.execute("SELECT * FROM universe WHERE day=? AND symbol=?", (day, symbol)).fetchone()
    return None if row is None else dict(row)


def exit_ladder(store: S.Store, exit_day: dt.date, exit_at: str) -> list[tuple[C.Session | None, str]]:
    """The exits in order: the planned auction, the closing cross of each of the next 5 sessions, the first trade of
    each of sessions 6..20 after it, then 0 at the 20th ('zero'). A session missing from the calendar is None."""
    planned = C.session(store, exit_day)
    after: list[C.Session | None] = list(C.sessions(store, exit_day + dt.timedelta(days=1),
                                                    exit_day + dt.timedelta(days=45))[:ZERO_AFTER])
    after += [None] * (ZERO_AFTER - len(after))
    ladder: list[tuple[C.Session | None, str]] = [(planned, exit_at)]
    ladder += [(s, "close") for s in after[:NEXT_CLOSES]]
    ladder += [(s, "first") for s in after[NEXT_CLOSES:ZERO_AFTER]]
    ladder.append((after[ZERO_AFTER - 1], "zero"))
    return ladder


def _above_limit(intent: Mapping[str, Any], uni: Mapping[str, Any], stock_in: float) -> bool:
    """PREREG-EVL-2's LIMIT AT ENTRY, for that file's programs and every later one's (PREREG-EVL-3's, -4's and R3's
    births, which take PREREG-EVL-3's limit at entry): an entry auction above 1.25 x the raw SIP close of the session
    before the entry session is not filled (real money's limit, PREREG-EVL-1 section 8). With no such close on the
    universe row the event is not filled either (the reading that trades less). A program this process does not know
    takes the limit too (release 1019e's review, FAIL CLOSED): every PREREG program is always known, so only a
    registered birth can be unknown (its rows not loaded), and every birth takes the limit."""
    from .programs import BY_KEY

    program = BY_KEY.get((str(intent["program"]), int(intent.get("version") or 1)))
    if program is not None and program.prereg < 2:
        return False
    prev = uni.get("prev_close")
    return prev is None or stock_in > LIMIT_MULTIPLE * float(prev)


def _skip(store: S.Store, intent: Mapping[str, Any], why: str) -> str:
    with store.tx():
        store.move_intent(intent["program"], intent["version"], intent["event"], f"skipped:{why}")
    return f"skipped:{why}"


def settle_one(store: S.Store, gw: Any, intent: Mapping[str, Any], *, now: dt.datetime,
               prefetched: "Prefetch | bool | None" = False) -> str:
    """Settle one due intent. Returns 'settled', 'skipped:<why>' or 'waiting:<why>' (then nothing is written but the
    tape prints read so far). `prefetched` (release 1019i, the batched score): the pass's prefetch (`prefetch`), A CACHE
    THAT LIVES ONLY FOR THE PASS: when it holds every bar the settlement reads (`Prefetch.serves`) the settlement's own
    two fetches are skipped, its ratios are read from the cache, and exactly the rows those two fetches would have
    stored are written to `bars` (`Prefetch.store_window`); else (or with anything but a `Prefetch`) the two fetches
    are made as before."""
    try:
        got = _compute(store, gw, intent, now, prefetched)
    except Waiting as wait:
        return f"waiting:{wait}"
    if isinstance(got, str):
        return _skip(store, intent, got)
    row, moved = got
    with store.tx() as db:
        db.execute("INSERT OR IGNORE INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                   "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) VALUES(?, ?, ?, ?, ?, "
                   "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled')",
                   (intent["program"], intent["version"], intent["event"], row["entry_px"], row["exit_px"], row["bench"],
                    row["bench_entry"], row["bench_exit"], row["cost_entry_bp"], row["cost_exit_bp"], row["r"], row["b"],
                    row["a"], row["tradable"], S.iso(now)))
        if moved is not None:
            db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                       (f"exit:{intent['program']}:{intent['version']}:{intent['event']}",
                        json.dumps(moved, sort_keys=True)))
        store.move_intent(intent["program"], intent["version"], intent["event"], "exited",
                          None if moved is None else f"exit {moved['kind']} {moved['day']}")
    return "settled"


def _compute(store: S.Store, gw: Any, intent: Mapping[str, Any], now: dt.datetime, source: Any = None, *,
             dry: bool = False) -> str | tuple[dict[str, Any], dict[str, str] | None]:
    """The settlement of one intent, computed and not written: the skip's why (a str), or (the outcome row's fields,
    the late exit's meta {day, kind, planned} or None). Raises Waiting. Prints read are kept in `marks` as they are
    read (the tape is read once). THE DAILY BARS by `source` (release 1019i): a `Prefetch` that serves the intent
    (the pass's cache: ratios from it, and, unless `dry`, the per-intent path's rows written to `bars`); a `Narrow`
    (the parity's per-intent path in memory: the intent's own two requests, never written); else release 1019h's two
    fetches into `bars`, read back. `dry` (the parity check, `check_parity`) writes no bar: a `Prefetch` that does not
    serve the intent raises `_Missed` instead of fetching."""
    entry_day, exit_day = dt.date.fromisoformat(intent["entry_day"]), dt.date.fromisoformat(intent["exit_day"])
    symbol = str(intent["symbol"]).upper()
    uni = _universe(store, intent["entry_day"], symbol)
    if uni is None or not uni.get("bench") or uni.get("adv20") is None:
        return "no-universe-row"
    code = U.EXCHANGE_CODES.get(str(uni.get("exchange") or "").upper())
    if code is None:
        return "no-listing-exchange"
    bench = str(uni["bench"]).upper()
    entry_s = C.session(store, entry_day)
    if entry_s is None:
        raise Waiting(f"no session {entry_day} in the calendar")
    entry_kind = "close" if intent["entry_at"] == "close" else "open"

    bench_in = bench_print(store, gw, bench, entry_s, entry_kind, now)  # the day's tape is readable from here on
    stock_in, known = tape_print(store, gw, symbol, code, entry_s, entry_kind, now)
    if stock_in is None:
        if not known:
            raise Waiting(f"{symbol} {entry_kind} {entry_day}: tape not complete")
        return "no-auction"
    if _above_limit(intent, uni, stock_in):
        return "limit"

    exit_s: C.Session | None = None
    exit_kind, stock_out = "", 0.0
    for session, kind in exit_ladder(store, exit_day, str(intent["exit_at"])):
        if session is None:
            raise Waiting(f"the calendar does not reach the exit ladder of {exit_day}")
        if kind == "zero":
            exit_s, exit_kind, stock_out = session, kind, 0.0
            break
        if session.close_at + TAPE_DELAY > now:
            raise Waiting(f"{symbol}: the {kind} of {session.day} is not on the tape yet")
        px, known = tape_print(store, gw, symbol, code, session, kind, now)
        if px is not None:
            exit_s, exit_kind, stock_out = session, kind, px
            break
        if not known:
            raise Waiting(f"{symbol} {kind} {session.day}: tape not complete")
    if exit_s is None:
        raise Waiting("no exit found")  # unreachable: the ladder ends at 'zero'
    bench_kind = {"open": "open", "close": "close", "first": "open", "zero": "close"}[exit_kind]
    bench_out = bench_print(store, gw, bench, exit_s, bench_kind, now)

    # One fetch of the window's daily bars, raw and adjusted, so entry and exit share one adjustment. Release 1019i
    # (the batched score): from the pass's cache when it holds every bar read below (and then exactly the rows the two
    # fetches would have stored are written: `bars` ends the pass as under release 1019h), else the two fetches.
    ratio: Callable[[str, dt.date], float]
    if isinstance(source, Prefetch) and source.serves((symbol, bench), entry_day, exit_s.day):
        ratio = source.ratio
        source.hits.add(_key(intent))
        if not dry:
            source.store_window(store, (symbol, bench), entry_day, exit_s.day, now)
    elif isinstance(source, Narrow):
        ratio = source.read(store, gw, (symbol, bench), entry_day, exit_s.day, now)
    elif dry:
        raise _Missed(f"{symbol}: the pass's cache does not hold every bar")
    else:
        for adj in ("raw", "all"):
            U.fetch_daily_bars(store, gw, [symbol, bench], entry_day, exit_s.day, adj=adj, now=now)

        def ratio(sym: str, day: dt.date) -> float:
            return _ratio(store, sym, day)
    entry_px = stock_in * ratio(symbol, entry_day)
    exit_px = stock_out * ratio(symbol, exit_s.day) if stock_out else 0.0
    b_in = bench_in * ratio(bench, entry_day)
    b_out = bench_out * ratio(bench, exit_s.day)

    prev = C.previous(store, entry_day, 1)
    equity = equity_on(store, prev[0].day) if prev else None
    adv = float(uni["adv20"])
    c_in, c_out = cost_bp(adv, equity, "entry"), cost_bp(adv, equity, "exit")
    r = after_cost_return(entry_px, exit_px, c_in, c_out)
    b = b_out / b_in - 1.0
    prev_close = uni.get("prev_close")
    tradable = (None if equity is None or prev_close is None
                else int(LIMIT_MULTIPLE * float(prev_close) <= TRADABLE_SHARE * equity))
    moved = (exit_s.day != exit_day) or (exit_kind != intent["exit_at"])
    row = {"entry_px": entry_px, "exit_px": exit_px, "bench": bench, "bench_entry": b_in, "bench_exit": b_out,
           "cost_entry_bp": c_in, "cost_exit_bp": c_out, "r": r, "b": b, "a": r - b, "tradable": tradable,
           "status": "settled"}
    late = {"day": exit_s.day.isoformat(), "kind": exit_kind, "planned": exit_day.isoformat()} if moved else None
    return row, late


# -------------------------------------------------------------------------------------------- the batched score
#: The upsert of a daily bar, exactly as league/events/universe.py `fetch_daily_bars` writes one (the batched score
#: writes the rows the per-intent path's two fetches would have written, `Prefetch.store_window`).
_BAR_UPSERT = ("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?) "
               "ON CONFLICT(symbol, day, adj) DO UPDATE SET o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c, "
               "v=excluded.v, fetched_at=excluded.fetched_at")
#: One bar as the cache keeps it: (o, h, l, c, v), the vendor's values as sent.
Bar = tuple[Any, Any, Any, Any, Any]
CLOSE = 3


class _Missed(Exception):
    """A dry settlement (the parity check) whose pass's cache does not hold every bar it reads: nothing batched to test."""


def _key(intent: Mapping[str, Any]) -> tuple[str, int, str]:
    return (str(intent["program"]), int(intent["version"]), str(intent["event"]))


def _read_bars(gw: Any, symbols: Sequence[str], first: dt.date, last: dt.date, adj: str, now: dt.datetime
               ) -> list[tuple[str, str, Bar]]:
    """SIP 1Day bars of `symbols` from `first` to `last` (adjustment `adj`), READ AND NOT STORED: the very requests
    league/events/universe.py `fetch_daily_bars` makes (the same parameters, `sip_end`'s clamp, 200 symbols a request,
    page by page), as [(symbol, New York day, (o, h, l, c, v))] in the order the vendor sent them."""
    names = sorted({s.upper() for s in symbols if s})
    out: list[tuple[str, str, Bar]] = []
    for i in range(0, len(names), U.SYMBOLS_PER_REQUEST):
        chunk = names[i:i + U.SYMBOLS_PER_REQUEST]
        token = None
        for _ in range(200):
            page = gw.get_json(BARS_PATH, {
                "symbols": ",".join(chunk), "timeframe": "1Day", "start": first.isoformat(), "end": U.sip_end(last, now),
                "feed": "sip", "adjustment": adj, "limit": 10000, "page_token": token})
            for sym, rows in ((page or {}).get("bars") or {}).items():
                for b in rows or []:
                    day = S.parse_iso(str(b["t"])).astimezone(C.NY).date().isoformat()
                    out.append((sym.upper(), day, (b.get("o"), b.get("h"), b.get("l"), b.get("c"), b.get("v"))))
            token = (page or {}).get("next_page_token")
            if not token:
                break
    return out


def _close_ratio(raw: Bar | Mapping[str, Any] | None, adj: Bar | Mapping[str, Any] | None) -> float:
    """`_ratio`'s rule on two bars however kept (a cached tuple or a stored row): adjusted / raw close, 1.0 when either
    is missing or not a positive number."""
    def close(bar: Any) -> float | None:
        if bar is None:
            return None
        return _positive(bar.get("c") if isinstance(bar, Mapping) else bar[CLOSE])
    rc, ac = close(raw), close(adj)
    return ac / rc if rc and ac else 1.0


@dataclasses.dataclass
class Prefetch:
    """ONE PASS'S CACHE OF DAILY BARS (`prefetch`), never written to the store by itself: its time (`at`), the union
    window (`first`, `last`), the symbols, the requests and the rows kept, whether every chunk was read whole (`done`)
    and the failures; the bars by (symbol, adjustment) for each symbol whose chunk was read whole (`bars`; a symbol
    absent here was not), each symbol's earliest entry day (`since`: no bar before it is kept), and the intents it
    served (`hits`). Always truthy."""

    at: str
    first: dt.date | None = None
    last: dt.date | None = None
    symbols: int = 0
    requests: int = 0
    rows: int = 0
    done: bool = True
    errors: list[str] = dataclasses.field(default_factory=list)
    bars: dict[tuple[str, str], dict[str, Bar]] = dataclasses.field(default_factory=dict, repr=False)
    since: dict[str, dt.date] = dataclasses.field(default_factory=dict, repr=False)
    hits: set[tuple[str, int, str]] = dataclasses.field(default_factory=set, repr=False)

    def __bool__(self) -> bool:
        return True

    def bar(self, symbol: str, day: dt.date, adj: str) -> Bar | None:
        return (self.bars.get((symbol.upper(), adj)) or {}).get(day.isoformat())

    def serves(self, symbols: Iterable[str], first: dt.date, last: dt.date) -> bool:
        """Whether the cache holds every bar a settlement of the window [first, last] reads: each symbol's chunk read
        whole in both adjustments, the window inside the union window and after the symbol's earliest entry, and the
        symbol's raw and adjusted bars on both days (the 8 bars of a symbol and its benchmark). A bar the vendor did
        not send (a missing bar) is a miss: that intent fetches its own two, as before."""
        if self.first is None or self.last is None or first < self.first or last > self.last:
            return False
        for symbol in {str(s).upper() for s in symbols}:
            start = self.since.get(symbol)
            if start is None or first < start:
                return False
            for adj in ("raw", "all"):
                if (symbol, adj) not in self.bars:
                    return False
                if self.bar(symbol, first, adj) is None or self.bar(symbol, last, adj) is None:
                    return False
        return True

    def ratio(self, symbol: str, day: dt.date) -> float:
        """`_ratio` read from the cache."""
        return _close_ratio(self.bar(symbol, day, "raw"), self.bar(symbol, day, "all"))

    def store_window(self, store: S.Store, symbols: Iterable[str], first: dt.date, last: dt.date,
                     now: dt.datetime) -> int:
        """THE PER-INTENT PATH'S WRITES, FROM THE CACHE: every cached bar of `symbols` (raw and adjusted) on the days
        [first, last], upserted into `bars` at `now` as its two fetches would have (one transaction): the bars of
        other days and of the intents that never reach the bar step are never written, so `bars` ends the pass as under
        release 1019h. Returns the rows written."""
        lo, hi = first.isoformat(), last.isoformat()
        rows = [(symbol, day, adj, *bar, S.iso(now))
                for symbol in sorted({str(s).upper() for s in symbols}) for adj in ("raw", "all")
                for day, bar in sorted((self.bars.get((symbol, adj)) or {}).items()) if lo <= day <= hi]
        with store.tx() as db:
            db.executemany(_BAR_UPSERT, rows)
        return len(rows)

    def summary(self) -> dict[str, Any]:
        return {"first": None if self.first is None else self.first.isoformat(),
                "last": None if self.last is None else self.last.isoformat(), "symbols": self.symbols,
                "requests": self.requests, "rows": self.rows, "done": self.done, "errors": self.errors[:3]}


class Narrow:
    """THE PARITY'S PER-INTENT PATH, IN MEMORY (`check_parity`): the intent's own two requests (raw and adjusted over
    its window, as release 1019h's path makes them, `_read_bars`) read into a cache of its own and NEVER written to
    `bars`; a bar they did not get is read from `bars` as it stands, which is what release 1019h's path reads after
    its upsert. Counts its requests."""

    def __init__(self) -> None:
        self.requests = 0

    def read(self, store: S.Store, gw: Any, symbols: Iterable[str], first: dt.date, last: dt.date,
             now: dt.datetime) -> Callable[[str, dt.date], float]:
        names = sorted({str(s).upper() for s in symbols})
        got: dict[tuple[str, str, str], Bar] = {}
        counted = Counted(gw)
        for adj in ("raw", "all"):
            for symbol, day, bar in _read_bars(counted, names, first, last, adj, now):
                got[(symbol, day, adj)] = bar
        self.requests += counted.counts["bars"]

        def ratio(symbol: str, day: dt.date) -> float:
            sym, d = symbol.upper(), day.isoformat()
            pair = [got.get((sym, d, adj)) or _bar(store, sym, day, adj) for adj in ("raw", "all")]
            return _close_ratio(pair[0], pair[1])
        return ratio


class Counted:
    """A gateway that counts its GETs by kind ('bars', 'trades', 'other') and passes each on unchanged."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.counts: dict[str, int] = {"bars": 0, "trades": 0, "other": 0}

    @property
    def last_headers(self) -> Mapping[str, str]:
        return getattr(self.inner, "last_headers", {}) or {}

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        kind = "bars" if path == BARS_PATH else "trades" if path.endswith("/trades") else "other"
        self.counts[kind] += 1
        return self.inner.get_json(path, params)

    def __getattr__(self, name: str) -> Any:
        inner = self.__dict__.get("inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)


def batch_on(settings: Mapping[str, Any] | None) -> bool:
    """league/config.json `events.score_batch` (the module docstring): a missing key is ON (`BATCH_DEFAULT`); only false
    turns it off. (The parity latch, `latched`, turns it off too, from the store.)"""
    value = (settings or {}).get("score_batch", BATCH_DEFAULT)
    return value is not False


def order_due(intents: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """THE ORDER OF THE BATCHED SCORE: the seating versions (programs.SEATING: what real money trades) and the controls
    their screens compare them with (screen.control_of) first, then every other record, each group in `due`'s order."""
    from .programs import SEATING
    from .screen import control_of

    seats = {(p.id, int(p.version)) for p in SEATING}
    controls = {c for p in SEATING for c in (control_of(p.id),) if c}

    def first(intent: Mapping[str, Any]) -> bool:
        return (str(intent["program"]), int(intent["version"])) in seats or str(intent["program"]) in controls
    return [i for i in intents if first(i)] + [i for i in intents if not first(i)]


def prefetch(store: S.Store, gw: Any, intents: Iterable[Mapping[str, Any]], *, now: dt.datetime,
             late: Callable[[], bool] | None = None) -> Prefetch:
    """THE BATCHED SCORE'S ONE READ OF DAILY BARS (the module docstring), INTO THE PASS'S CACHE AND NEVER THE STORE: the
    raw and adjusted SIP daily bars of every symbol of `intents` that has its universe row (one without is skipped by
    the settlement before any bar is read) and of both benchmarks, over the union window (the earliest entry session to
    the day 16 minutes ago), 200 symbols a request (`_read_bars`, the requests `universe.fetch_daily_bars` makes); a
    symbol's bars before its own earliest entry are not kept. Stops between chunks once `late()` says so; a chunk that
    fails is counted and left out whole: either way the intents it left out fetch their own bars, as before. Never
    raises."""
    out = Prefetch(at=S.iso(now))
    since: dict[str, dt.date] = {}
    for intent in intents:
        symbol, entry_day = str(intent.get("symbol") or "").upper(), intent.get("entry_day")
        if not symbol or not entry_day:
            continue
        uni = _universe(store, str(entry_day), symbol)
        if uni is None or not uni.get("bench") or uni.get("adv20") is None:
            continue
        entry = dt.date.fromisoformat(str(entry_day))
        since[symbol] = min(since.get(symbol, entry), entry)
    if not since:
        return out
    first = min(since.values())
    for bench in BENCHMARKS:
        since[bench] = first
    names = sorted(since)
    last = (now - TAPE_DELAY).astimezone(C.NY).date()
    out.first, out.last, out.symbols, out.since = first, max(first, last), len(names), since
    counted = Counted(gw)
    for adj in ("raw", "all"):
        for i in range(0, len(names), U.SYMBOLS_PER_REQUEST):
            if late is not None and late():
                out.done = False
                break
            chunk = names[i:i + U.SYMBOLS_PER_REQUEST]
            try:
                got = _read_bars(counted, chunk, out.first, out.last, adj, now)
            except Exception as exc:  # noqa: BLE001 - its intents fetch their own bars
                out.done = False
                out.errors.append(f"{adj} {chunk[0]}..{chunk[-1]}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            for symbol in chunk:
                out.bars[(symbol, adj)] = {}
            for symbol, day, bar in got:
                held = out.bars.get((symbol, adj))
                if held is not None and day >= since[symbol].isoformat():
                    held[day] = bar
            out.rows += sum(len(out.bars[(symbol, adj)]) for symbol in chunk)
    out.requests = counted.counts["bars"]
    return out


# ------------------------------------------------------------------------------------------------ the parity night
def parity_sampled(intent: Mapping[str, Any], share: float = PARITY_SHARE) -> bool:
    """Whether an intent is in the parity night's sample: the first 8 hex digits of sha256("<program>|<version>|<event>")
    over 2^32 below `share` (about 5% of intents, the same ones on every run)."""
    key = f"{intent['program']}|{int(intent['version'])}|{intent['event']}".encode("utf-8")
    return int(hashlib.sha256(key).hexdigest()[:8], 16) / float(1 << 32) < share


def parity_due(store: S.Store, night: dt.date, settings: Mapping[str, Any] | None = None) -> bool:
    """Whether this night's batched passes run THE PARITY CHECK: `events.score_parity` true every night, false never;
    else every night until the first on which a flag is written, and all of that night (meta `PARITY_FIRST`, written
    by `note_first_night` with the first flag, `check_parity`): a night whose prefetch failed, whose sample was empty or
    whose sampled intents the cache did not serve tested nothing batched, so the next night is a parity night still."""
    forced = (settings or {}).get("score_parity")
    if forced is True or forced is False:
        return forced
    first = store.meta(PARITY_FIRST)
    return first is None or first == night.isoformat()


def note_first_night(store: S.Store, night: dt.date) -> None:
    """Keep the first night a parity flag was written (meta `PARITY_FIRST`, once; `check_parity` calls it)."""
    store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (PARITY_FIRST, night.isoformat()))


def latched(store: Any) -> dict[str, Any] | None:
    """THE PARITY LATCH (meta `PARITY_LATCH`): {night, program, version, event, at} of the first parity flag 0 (never a
    value), or None. While it stands the batched score is OFF whatever `events.score_batch` says: every pass settles by
    release 1019h's per-intent path, until the captain clears it (`unlatch`)."""
    row = store.db.execute("SELECT value FROM meta WHERE key=?", (PARITY_LATCH,)).fetchone()
    if row is None:
        return None
    try:
        got = json.loads(str(row[0]))
    except ValueError:
        got = None
    return got if isinstance(got, dict) else {"value": str(row[0])[:80]}


def latch(store: S.Store, night: dt.date, intent: Mapping[str, Any], now: dt.datetime) -> None:
    """Set THE PARITY LATCH (once: the first flag 0 stands until it is cleared)."""
    program, version, event = _key(intent)
    store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                     (PARITY_LATCH, json.dumps({"night": night.isoformat(), "program": program, "version": version,
                                                "event": event, "at": S.iso(now)}, sort_keys=True)))


def unlatch(store: S.Store) -> dict[str, Any] | None:
    """THE CAPTAIN'S CLEARING OF THE PARITY LATCH (`python3 -m league.events --state DIR score-unlatch`, once the flag 0
    is explained): the latch removed, and what it held returned (None when none stood). The next pass is batched again
    while `events.score_batch` is not false; nothing else is touched."""
    held = latched(store)
    store.db.execute("DELETE FROM meta WHERE key=?", (PARITY_LATCH,))
    return held


def _check(store: S.Store, gw: Any, intent: Mapping[str, Any], night: dt.date, now: dt.datetime,
           prefetched: Prefetch) -> tuple[int | None, str | None]:
    """`check_parity`'s work: (the flag or None, the why of a wait or None)."""
    try:
        mine = _compute(store, gw, intent, now, prefetched, dry=True)
    except Waiting as wait:
        return None, str(wait)
    except _Missed:
        return None, None
    if isinstance(mine, str):
        return None, None
    try:
        theirs: Any = _compute(store, gw, intent, now, Narrow(), dry=True)
    except Waiting:
        theirs = None
    if isinstance(theirs, tuple):
        equal = int(all(_same(mine[0][f], theirs[0][f]) for f in PARITY_FIELDS) and mine[1] == theirs[1])
    else:
        equal = 0
    store.db.execute("INSERT OR REPLACE INTO score_parity(program, version, event, night, equal, checked_at) VALUES(?, ?, ?, "
                     "?, ?, ?)", (intent["program"], int(intent["version"]), intent["event"], night.isoformat(), equal,
                                  S.iso(now)))
    note_first_night(store, night)      # (the parity night is the first night a flag is written: one was)
    if not equal:
        latch(store, night, intent, now)
    return equal, None


def check_parity(store: S.Store, gw: Any, intent: Mapping[str, Any], night: dt.date, *, now: dt.datetime,
                 prefetched: Prefetch) -> int | None:
    """THE PARITY CHECK of one sampled intent, BEFORE ANYTHING OF IT IS WRITTEN: settled twice, dry, in memory, by the
    batched path (the pass's cache `prefetched`) and by the per-intent path (`Narrow`: its own two requests, never
    written to `bars`), both from the same prints (read once, kept in `marks`), and compared field by field (and the
    late exit). ONLY THE FLAG is written (`score_parity`: 1 equal, 0 not; never a value), and a 0 sets THE PARITY LATCH
    (`latch`): the batched score is off from that intent on. Returns the flag, or None when there is nothing batched
    to compare: the intent waits, is skipped before any bar, or the cache does not serve it (it settles by its own
    fetches, the per-intent path itself). A per-intent path that waits or skips where the batched one settles is a 0."""
    return _check(store, gw, intent, night, now, prefetched)[0]


def parity_window(store: S.Store, gw: Any, intents: Iterable[Mapping[str, Any]], prefetched: Prefetch,
                  night: dt.date, *, now: dt.datetime, late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """THE PARITY CHECK OF ONE PREFETCH'S INTENTS, BEFORE ANY OF THEM SETTLES: each sampled one (`parity_sampled`) is
    checked (`check_parity`) until `late()` or a flag 0 (the latch: the caller settles the rest by the per-intent
    path). Returns {sampled, checked, equal, waits}: `waits` the sampled intents that waited ({key: why}), which the
    caller leaves waiting without computing them again (a tape window is read once a pass)."""
    out: dict[str, Any] = {"sampled": 0, "checked": 0, "equal": 0, "waits": {}}
    for intent in intents:
        if not parity_sampled(intent):
            continue
        if late is not None and late():
            break
        out["sampled"] += 1
        try:
            flag, waited = _check(store, gw, intent, night, now, prefetched)
        except Exception:  # noqa: BLE001 - a flag not written is a flag not counted; the intent settles as any
            continue
        if waited is not None:
            out["waits"][_key(intent)] = waited
        if flag is None:
            continue
        out["checked"] += 1
        out["equal"] += flag
        if not flag:
            break
    return out


def _same(a: Any, b: Any) -> bool:
    """Byte-identical as the store keeps it: the same type of value and the same value (floats by their repr)."""
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, float) and isinstance(b, float) and repr(a) == repr(b)
    return a == b


def parity_counts(store: S.Store, night: dt.date) -> dict[str, int]:
    """The parity night's flags of `night`: {checked, equal} (counts only)."""
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='score_parity'").fetchone() is None:
        return {"checked": 0, "equal": 0}
    row = store.db.execute("SELECT COUNT(*), COALESCE(SUM(equal), 0) FROM score_parity WHERE night=?",
                           (night.isoformat(),)).fetchone()
    return {"checked": int(row[0] or 0), "equal": int(row[1] or 0)}


# ------------------------------------------------------------------------------------------------------- the pass
def settle(store: S.Store, gw: Any, *, now: dt.datetime | None = None, batch: bool | None = None,
           parity: bool | None = None) -> dict[str, Any]:
    """The score job: every due intent settled, skipped (no entry print) or left waiting. Returns counts and the
    failures (an intent's failure is its own; the job goes on). `batch` (release 1019i; None: `BATCH_DEFAULT`): the
    batched score (`order_due`, `prefetch`, `settle_one(prefetched=...)`); False: the per-intent path of release 1019h.
    THE PARITY LATCH (`latched`) makes it False whatever is asked. `parity` (None: `parity_due`): the parity check of the
    sampled intents (`parity_window`), before any of them settles; a flag 0 latches and the whole pass settles by the
    per-intent path."""
    now = now or S.utc_now()
    batch = (BATCH_DEFAULT if batch is None else bool(batch)) and latched(store) is None
    began = time.monotonic()
    night = now.astimezone(C.NY).date()
    counted = Counted(gw)
    summary: dict[str, Any] = {"due": 0, "settled": 0, "skipped": 0, "waiting": 0, "errors": [], "waits": []}
    intents: Sequence[Mapping[str, Any]] = due(store, now)
    pre: Prefetch | None = None
    if batch and intents:
        intents = order_due(intents)
        pre = prefetch(store, counted, intents, now=now)
    check = batch and (parity_due(store, night) if parity is None else bool(parity))
    flags: dict[str, Any] = {"sampled": 0, "checked": 0, "equal": 0, "waits": {}}
    if check and pre is not None and pre.symbols:
        flags = parity_window(store, counted, intents, pre, night, now=now)
    use = pre if pre is not None and pre.symbols and latched(store) is None else None
    served = 0
    for intent in intents:
        summary["due"] += 1
        try:
            waited = flags["waits"].get(_key(intent))
            if waited is not None:
                status = f"waiting:{waited}"
            else:
                status = settle_one(store, counted, intent, now=now, prefetched=use if use is not None else False)
        except Exception as exc:  # noqa: BLE001 - one intent's failure is reported, never the job's
            summary["errors"].append(f"{intent['program']}:{intent['event']}: {type(exc).__name__}: {str(exc)[:160]}")
            summary["waiting"] += 1
            continue
        key = status.split(":")[0]
        summary[key] += 1
        if key == "waiting":
            summary["waits"].append(f"{intent['program']}:{intent['event']}: {status[len('waiting:'):]}")
        if key == "settled" and use is not None:
            served += int(_key(intent) in use.hits)
    summary.update(batched=batch, requests=dict(counted.counts), seconds=round(time.monotonic() - began, 3))
    if pre is not None:
        summary["prefetch"] = {**pre.summary(), "served": served}
    if check:
        summary["parity"] = {k: flags[k] for k in ("sampled", "checked", "equal")}
    if latched(store) is not None:
        summary["latched"] = True
    return summary


__all__ = ["cost_bp", "impact_bp", "after_cost_return", "equity_on", "equity_key", "record_equity", "tape_print",
           "bench_print", "exit_ladder", "due", "settle_one", "settle", "Waiting", "Prefetch", "Narrow", "Counted",
           "prefetch", "order_due", "batch_on", "parity_sampled", "parity_due", "note_first_night", "check_parity",
           "parity_window", "parity_counts", "latched", "latch", "unlatch", "BATCH_DEFAULT", "BENCHMARKS",
           "PARITY_SHARE", "PARITY_FIRST", "PARITY_LATCH", "PARITY_FIELDS"]
