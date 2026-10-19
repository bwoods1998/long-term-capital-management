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
"""

from __future__ import annotations

import datetime as dt
import json
import math
import urllib.parse
from typing import Any, Iterator, Mapping

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


def _skip(store: S.Store, intent: Mapping[str, Any], why: str) -> str:
    with store.tx():
        store.move_intent(intent["program"], intent["version"], intent["event"], f"skipped:{why}")
    return f"skipped:{why}"


def settle_one(store: S.Store, gw: Any, intent: Mapping[str, Any], *, now: dt.datetime) -> str:
    """Settle one due intent. Returns 'settled', 'skipped:<why>' or 'waiting:<why>' (then nothing is written but the
    tape prints read so far)."""
    try:
        return _settle(store, gw, intent, now)
    except Waiting as wait:
        return f"waiting:{wait}"


def _settle(store: S.Store, gw: Any, intent: Mapping[str, Any], now: dt.datetime) -> str:
    entry_day, exit_day = dt.date.fromisoformat(intent["entry_day"]), dt.date.fromisoformat(intent["exit_day"])
    symbol = str(intent["symbol"]).upper()
    uni = _universe(store, intent["entry_day"], symbol)
    if uni is None or not uni.get("bench") or uni.get("adv20") is None:
        return _skip(store, intent, "no-universe-row")
    code = U.EXCHANGE_CODES.get(str(uni.get("exchange") or "").upper())
    if code is None:
        return _skip(store, intent, "no-listing-exchange")
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
        return _skip(store, intent, "no-auction")

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

    # One fetch of the window's daily bars, raw and adjusted, so entry and exit share one adjustment.
    for adj in ("raw", "all"):
        U.fetch_daily_bars(store, gw, [symbol, bench], entry_day, exit_s.day, adj=adj, now=now)
    entry_px = stock_in * _ratio(store, symbol, entry_day)
    exit_px = stock_out * _ratio(store, symbol, exit_s.day) if stock_out else 0.0
    b_in = bench_in * _ratio(store, bench, entry_day)
    b_out = bench_out * _ratio(store, bench, exit_s.day)

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
    with store.tx() as db:
        db.execute("INSERT OR IGNORE INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                   "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) VALUES(?, ?, ?, ?, ?, "
                   "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled')",
                   (intent["program"], intent["version"], intent["event"], entry_px, exit_px, bench, b_in, b_out, c_in,
                    c_out, r, b, r - b, tradable, S.iso(now)))
        if moved:
            db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                       (f"exit:{intent['program']}:{intent['version']}:{intent['event']}",
                        json.dumps({"day": exit_s.day.isoformat(), "kind": exit_kind, "planned": exit_day.isoformat()},
                                   sort_keys=True)))
        store.move_intent(intent["program"], intent["version"], intent["event"], "exited",
                          None if not moved else f"exit {exit_kind} {exit_s.day.isoformat()}")
    return "settled"


def settle(store: S.Store, gw: Any, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """The score job: every due intent settled, skipped (no entry print) or left waiting. Returns counts and the
    failures (an intent's failure is its own; the job goes on). Writes a `score` receipt (release R1: the House's stall
    job reads it, `evl_score`): `ok` unless every due intent failed (`failed`), its summary the counts alone."""
    now = now or S.utc_now()
    rid = store.start_receipt("score", now=now)
    summary: dict[str, Any] = {"due": 0, "settled": 0, "skipped": 0, "waiting": 0, "errors": [], "waits": []}
    try:
        for intent in due(store, now):
            summary["due"] += 1
            try:
                status = settle_one(store, gw, intent, now=now)
            except Exception as exc:  # noqa: BLE001 - one intent's failure is reported, never the job's
                summary["errors"].append(f"{intent['program']}:{intent['event']}: {type(exc).__name__}: {str(exc)[:160]}")
                summary["waiting"] += 1
                continue
            key = status.split(":")[0]
            summary[key] += 1
            if key == "waiting":
                summary["waits"].append(f"{intent['program']}:{intent['event']}: {status[len('waiting:'):]}")
    except BaseException as exc:
        store.finish_receipt(rid, "failed", {"error": type(exc).__name__}, now=now)
        raise
    failed = bool(summary["errors"]) and len(summary["errors"]) >= summary["due"]
    store.finish_receipt(rid, "failed" if failed else "ok",
                         {k: summary[k] for k in ("due", "settled", "skipped", "waiting")} | {"errors": len(summary["errors"])},
                         now=now)
    return summary


__all__ = ["cost_bp", "impact_bp", "after_cost_return", "equity_on", "equity_key", "record_equity", "tape_print",
           "bench_print", "exit_ladder", "due", "settle_one", "settle", "Waiting"]
