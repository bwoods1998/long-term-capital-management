"""THE PRICE LANE'S RECORDERS (release 1019i; PREREG-EVL-8's harness plan H2, goal-2026-10-19/evl8/GUSHER-RESULT.json and
PREREG-EVL-8's draft sections 1 and 7): what every PX value will be made of, read from SIP and stored in px.sqlite
(league/events/pxstore.py) BEFORE any decision that could read it, and never moved afterwards.

ONE ROUTE, THE BASIC PLAN'S CLAMP, A SHARED BUCKET. Every read is the gateway's existing `GET /v1/alpaca/v2/stocks/bars`
(multi-symbol, `feed=sip`, `SYMBOLS_PER_REQUEST` (200) symbols a request, page by page): `PxGateway` refuses any other
path or feed. Daily bars end at league/events/universe.py `sip_end` (the day after the last wanted session, or 16
minutes ago, whichever is earlier: the Basic plan admits nothing newer); a minute span is read only once it is WHOLE on
that tape (its end at least 16 minutes old), else nothing is written and it is read later. Every request takes a token
of THE LANE'S BUCKET (`TokenBucket`: `RATE_PER_MINUTE` (150) a minute, shared with the lane's own market-data reads,
league/events/house.py `throttle`): the lane takes its token whenever it reads (never refused, at most a wait), a PX read
only while `LANE_RESERVE` tokens stay for the lane (THE LANE FIRST), waiting no later than its job's bound
(`PxCut` past it).

THE RECORDERS (each a function of explicit inputs; league/events/house.py schedules them as isolated, bounded,
failure-tolerant jobs behind league/config.json `events.px_data`, default OFF):
- `backfill`: THE 270-SESSION DAILY BACKFILL on the first night: raw and adjusted daily bars of every listed ticker of
  the admitted exchanges and both benchmarks over the `BACKFILL_SESSIONS` sessions before today, chunk by chunk,
  resumable (`px_meta` `px:backfill:<adj>:<chunk>`; `px:backfill:done` once every chunk is in).
- `daily`: the nightly read of the last `NIGHTLY_SESSIONS` sessions' daily bars of the same names (raw and adjusted:
  a late correction or an adjustment is upserted, its old close kept in `px_bar_moves`).
- `flags`: FLAGGED(D) (`px_flags`, write-once): P's adjusted close read AT OR AFTER 09:00 ET of D against P's raw close
  (|ratio - 1| > 0.001, or either missing: a split, a dividend or a correction effective D); refused before 09:00 ET.
- `operating_fill`: THE OPERATING-COMPANY CACHE (px.sqlite `cik_info`, league/events/universe.py `operating`'s own
  rule and cache, 30 days): every CIK with a listed ticker, through the lane's SEC reader (SEC's pacing), resumable,
  cut at the job's bound.
- `universe`: PXU(D)'s base (`px_eligibility`, `px_universe`, write-once per (D, CIK, rule)): every CIK of SEC's
  `company_tickers.json` copy D's decision reads whose stock is eligible under PREREG-EVL-1 section 2 (league/events/
  universe.py `eligible_row`, the lane's own pure core, on px.sqlite's bars and cache: THE LANE'S `eligibility` AND
  `universe` ARE NEVER WRITTEN), with P's raw close >= $5.00, ADV20 >= $10,000,000 and adjusted daily bars on each of
  the 61 sessions before D; FLAGGED(D) is the flag table's, read at the decision. A CIK whose operating test is not
  cached yet, or a session whose bars are not current, is left undecided (read again), never judged on missing data.
- `minutes`: the minute values (`px_minutes`, write-once): THE PX1530 MARK (`px1530`), THE PREMARKET INDICATION (`pm`,
  for names with ADV20 >= $20,000,000) and the volume through 15:30 (`v1530`, for the names asked), each once its
  span is whole on the tape.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import math
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import pxstore as PS
from . import store as S
from . import universe as U

BARS_PATH = "/v1/alpaca/v2/stocks/bars"
SYMBOLS_PER_REQUEST = U.SYMBOLS_PER_REQUEST
PAGE_LIMIT = 10000
MAX_PAGES = 200
SIP_DELAY = U.SIP_DELAY
#: THE LANE'S BUCKET (the module docstring): requests a minute in all, the tokens a PX read always leaves the lane.
RATE_PER_MINUTE = 150
LANE_RESERVE = 50
#: The recorders' reaches and the PX universe's own bars (PREREG-EVL-8 draft section 1).
BACKFILL_SESSIONS = 270
NIGHTLY_SESSIONS = 5
ADJUSTED_SESSIONS = 61
PX_MIN_PRICE = 5.0
PX_MIN_ADV = 10_000_000.0
PM_MIN_ADV = 20_000_000.0
PM_MIN_BARS = 3
BENCHMARKS = ("SPY", "IWM")
FLAG_FROM = dt.time(9, 0)


class PxCut(Exception):
    """A PX read refused before it went: the job's bound passed, or the bucket would not leave the lane its reserve
    before it. The job stops; what it stored stays, and the next run goes on from there."""


# ------------------------------------------------------------------------------------------------- the bucket
class TokenBucket:
    """`rate_per_minute` tokens a minute, at most `capacity` held (THE LANE'S BUCKET, the module docstring). `take_lane`
    never refuses (it waits for a token when none is left); `take_px` takes one only while `reserve` tokens stay after
    it, waiting no later than `until` (a `clock` time), else refuses (False). Thread-safe."""

    def __init__(self, rate_per_minute: float = RATE_PER_MINUTE, *, capacity: float | None = None,
                 reserve: float = LANE_RESERVE, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rate = float(rate_per_minute) / 60.0
        self.capacity = float(capacity if capacity is not None else rate_per_minute)
        self.reserve = float(reserve)
        self.tokens = self.capacity
        self._clock, self._sleep = clock, sleep
        self._at = clock()
        self._lock = threading.Lock()
        self.taken = {"lane": 0, "px": 0}

    def _refill(self) -> None:
        now = self._clock()
        self.tokens = min(self.capacity, self.tokens + max(0.0, now - self._at) * self.rate)
        self._at = now

    def level(self) -> float:
        with self._lock:
            self._refill()
            return self.tokens

    def take_lane(self) -> None:
        """The lane's own read: a token now, or the wait for one (never refused)."""
        with self._lock:
            self._refill()
            if self.tokens < 1.0:
                self._sleep((1.0 - self.tokens) / self.rate)
                self._refill()
            self.tokens -= 1.0
            self.taken["lane"] += 1

    def take_px(self, until: float | None = None) -> bool:
        """A PX read's token while `reserve` stay for the lane, waiting at most until `until`; False when it cannot."""
        with self._lock:
            self._refill()
            need = 1.0 + self.reserve
            if self.tokens < need:
                wait = (need - self.tokens) / self.rate
                if until is not None and self._clock() + wait > until:
                    return False
                self._sleep(wait)
                self._refill()
                if self.tokens < need - 1e-9:      # (a clock that did not move as asked)
                    return False
            self.tokens = max(0.0, self.tokens - 1.0)
            self.taken["px"] += 1
            return True


class PxGateway:
    """The gateway as a PX recorder reads it: the SIP bars route only (any other path or feed raises ValueError), each
    request a PX token of `bucket` (`take_px`, no later than `until`) and refused once `late()` says the job's bound
    passed (`PxCut` either way); counted (`requests`)."""

    def __init__(self, inner: Any, bucket: TokenBucket, *, until: float | None = None,
                 late: Callable[[], bool] | None = None):
        self.inner, self.bucket, self.until, self.late = inner, bucket, until, late
        self.requests = 0

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        params = dict(params or {})
        if path != BARS_PATH:
            raise ValueError(f"the PX recorders read only {BARS_PATH}, not {path}")
        if params.get("feed") != "sip":
            raise ValueError("the PX recorders read SIP only")
        if self.late is not None and self.late():
            raise PxCut("the job's bound passed")
        if not self.bucket.take_px(self.until):
            raise PxCut("the lane's bucket keeps its reserve past the job's bound")
        self.requests += 1
        return self.inner.get_json(path, params)


# ------------------------------------------------------------------------------------------------- the reads
def _day_of(stamp: str) -> str:
    return S.parse_iso(stamp).astimezone(C.NY).date().isoformat()


def _pages(gw: Any, params: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    token = None
    for _ in range(MAX_PAGES):
        page = gw.get_json(BARS_PATH, {**params, "page_token": token}) or {}
        yield page
        token = page.get("next_page_token")
        if not token:
            return
    raise RuntimeError(f"more than {MAX_PAGES} pages of bars")


def daily_bars(px: PS.PxStore, gw: Any, symbols: Iterable[str], first: dt.date, last: dt.date, *, adj: str,
               now: dt.datetime, run: str) -> dict[str, int]:
    """SIP daily bars of `symbols` over [first, last] (adjustment `adj`) into px.sqlite, 200 symbols a request, `end` at
    `sip_end` (the Basic plan's clamp). Returns {requests, rows, moved}."""
    names = sorted({str(s).upper() for s in symbols if s})
    out = {"requests": 0, "rows": 0, "moved": 0}
    for i in range(0, len(names), SYMBOLS_PER_REQUEST):
        chunk = names[i:i + SYMBOLS_PER_REQUEST]
        params = {"symbols": ",".join(chunk), "timeframe": "1Day", "start": first.isoformat(),
                  "end": U.sip_end(last, now), "feed": "sip", "adjustment": adj, "limit": PAGE_LIMIT}
        for page in _pages(gw, params):
            out["requests"] += 1
            rows = [{"symbol": sym, "day": _day_of(str(b["t"])), **{k: b.get(k) for k in ("t", "o", "h", "l", "c", "v",
                                                                                         "n", "vw")}}
                    for sym, bars in ((page.get("bars") or {}).items()) for b in bars or []]
            stored, moved = px.put_bars(rows, adj=adj, run=run, now=now)
            out["rows"] += stored
            out["moved"] += moved
    return out


def minute_bars(gw: Any, symbols: Sequence[str], start: dt.datetime, end: dt.datetime, *,
                now: dt.datetime) -> dict[str, list[Mapping[str, Any]]] | None:
    """Raw SIP 1Min bars of `symbols` starting in [start, end), 200 symbols a request; None while the span is not whole
    on the Basic plan's tape (`end` not yet 16 minutes old): nothing is read then."""
    if now - SIP_DELAY < end:
        return None
    out: dict[str, list[Mapping[str, Any]]] = {str(s).upper(): [] for s in symbols}
    names = sorted(out)
    for i in range(0, len(names), SYMBOLS_PER_REQUEST):
        chunk = names[i:i + SYMBOLS_PER_REQUEST]
        params = {"symbols": ",".join(chunk), "timeframe": "1Min", "start": S.iso(start), "end": S.iso(end),
                  "feed": "sip", "adjustment": "raw", "limit": PAGE_LIMIT}
        for page in _pages(gw, params):
            for sym, bars in (page.get("bars") or {}).items():
                out.setdefault(str(sym).upper(), []).extend(bars or [])
    return out


# ------------------------------------------------------------------------------------------------- the minute values
def span_1530(session: C.Session) -> tuple[dt.datetime, dt.datetime]:
    """THE PX1530 MARK's span: bars starting in [15:00, 15:29] ET and ending by 15:30 ([close - 60, close - 31] min on
    an early close), as [start, end) of bar starts."""
    if session.early:
        return session.close_at - dt.timedelta(minutes=60), session.close_at - dt.timedelta(minutes=30)
    day = session.day
    return (dt.datetime.combine(day, dt.time(15, 0), tzinfo=C.NY).astimezone(dt.timezone.utc),
            dt.datetime.combine(day, dt.time(15, 30), tzinfo=C.NY).astimezone(dt.timezone.utc))


def span_pm(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """THE PREMARKET INDICATION's span: bars starting in [08:00, 08:58] ET, as [start, end) of bar starts."""
    return (dt.datetime.combine(day, dt.time(8, 0), tzinfo=C.NY).astimezone(dt.timezone.utc),
            dt.datetime.combine(day, dt.time(8, 59), tzinfo=C.NY).astimezone(dt.timezone.utc))


def span_v1530(session: C.Session) -> tuple[dt.datetime, dt.datetime]:
    """V_D's span: the session's regular minute bars through the bar ending at 15:30 ET (close - 30 on an early close)."""
    return session.open_at, span_1530(session)[1]


def _in(bars: Iterable[Mapping[str, Any]], start: dt.datetime, end: dt.datetime) -> list[Mapping[str, Any]]:
    got = []
    for b in bars:
        try:
            t = S.parse_iso(str(b["t"]))
        except (KeyError, ValueError):
            continue
        if start <= t < end:
            got.append(b)
    return sorted(got, key=lambda b: S.parse_iso(str(b["t"])))


def _positive(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def last_close(bars: Sequence[Mapping[str, Any]]) -> float | None:
    return _positive(bars[-1].get("c")) if bars else None


def pm_value(bars: Sequence[Mapping[str, Any]]) -> float | None:
    """pm_D: the last bar's close when at least `PM_MIN_BARS` bars of the span have volume, else None."""
    if sum(1 for b in bars if (_positive(b.get("v")) or 0) > 0) < PM_MIN_BARS:
        return None
    return last_close(bars)


def volume(bars: Sequence[Mapping[str, Any]]) -> float:
    return math.fsum(float(b.get("v") or 0) for b in bars)


def minutes(px: PS.PxStore, gw: Any, symbols: Sequence[str], session: C.Session, label: str, *, now: dt.datetime,
            run: str) -> dict[str, Any]:
    """One minute value (`label`: px1530 | pm | v1530) of every symbol of `symbols` not yet stored for the session,
    once its span is whole on the tape (else {"waiting": ...}, nothing written): WRITE-ONCE, a symbol with no bar in
    the span stored as no value (read once). Returns {written, kept, waiting}."""
    span = {"px1530": lambda: span_1530(session), "pm": lambda: span_pm(session.day),
            "v1530": lambda: span_v1530(session)}[label]()
    todo = [s for s in sorted({str(x).upper() for x in symbols}) if px.minute(s, session.day, label) is None]
    if not todo:
        return {"written": 0, "kept": len(set(symbols)), "waiting": None}
    got = minute_bars(gw, todo, span[0], span[1], now=now)
    if got is None:
        return {"written": 0, "kept": 0, "waiting": f"the span ends {S.iso(span[1])}: not 16 minutes old"}
    written = 0
    for sym in todo:
        bars = _in(got.get(sym) or [], *span)
        value = {"px1530": last_close, "pm": pm_value, "v1530": volume}[label](bars)
        written += px.put_minute(sym, session.day, label, value if bars else None, bars=len(bars),
                                 first_t=str(bars[0]["t"]) if bars else None, last_t=str(bars[-1]["t"]) if bars else None,
                                 run=run, now=now)
    return {"written": written, "kept": len(todo) - written, "waiting": None}


# ------------------------------------------------------------------------------------------------- the daily recorders
def sessions_before(store: Any, day: dt.date, n: int) -> list[C.Session]:
    """The `n` sessions before `day` on the lane's calendar (league/events/calendar.py `previous`)."""
    return list(C.previous(store, day, n))


def backfill(px: PS.PxStore, gw: Any, symbols: Iterable[str], calendar: Any, today: dt.date, *, now: dt.datetime,
             run: str, late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """THE 270-SESSION DAILY BACKFILL (the module docstring): raw then adjusted, chunk by chunk of 200 symbols over the
    `BACKFILL_SESSIONS` sessions before `today` (the lane's calendar), each chunk once (`px:backfill:<adj>:<n>`);
    `px:backfill:done` once all are in. Stops between chunks once `late()` says so (resumed by the next run)."""
    if px.meta("px:backfill:done"):
        return {"done": True, "requests": 0, "rows": 0, "chunks": 0}
    prior = sessions_before(calendar, today, BACKFILL_SESSIONS)
    if not prior:
        return {"done": False, "requests": 0, "rows": 0, "chunks": 0, "why": "no sessions on the lane's calendar"}
    names = sorted({str(s).upper() for s in symbols if s} | set(BENCHMARKS))
    first, last = prior[0].day, prior[-1].day
    out: dict[str, Any] = {"done": False, "requests": 0, "rows": 0, "chunks": 0, "first": first.isoformat(),
                           "last": last.isoformat(), "symbols": len(names)}
    for adj in ("raw", "all"):
        for n, i in enumerate(range(0, len(names), SYMBOLS_PER_REQUEST)):
            key = f"px:backfill:{adj}:{n}"
            if px.meta(key) == "done":
                continue
            if late is not None and late():
                return out
            got = daily_bars(px, gw, names[i:i + SYMBOLS_PER_REQUEST], first, last, adj=adj, now=now, run=run)
            px.set_meta(key, "done")
            out["requests"] += got["requests"]
            out["rows"] += got["rows"]
            out["chunks"] += 1
    px.set_meta("px:backfill:done", S.iso(now))
    px.set_meta("px:backfill:range", f"{first.isoformat()}..{last.isoformat()}")
    out["done"] = True
    return out


def daily(px: PS.PxStore, gw: Any, symbols: Iterable[str], calendar: Any, night: dt.date, *, now: dt.datetime,
          run: str) -> dict[str, Any]:
    """THE NIGHTLY READ: raw and adjusted daily bars of the last `NIGHTLY_SESSIONS` sessions through `night` (its own
    session included), so a correction or an adjustment published since is upserted (its old close kept); the night is
    marked (`px:bars:<night>`) once both are in."""
    reach = sessions_before(calendar, night + dt.timedelta(days=1), NIGHTLY_SESSIONS)
    if not reach:
        return {"requests": 0, "rows": 0, "moved": 0, "why": "no sessions on the lane's calendar"}
    names = sorted({str(s).upper() for s in symbols if s} | set(BENCHMARKS))
    out = {"requests": 0, "rows": 0, "moved": 0}
    for adj in ("raw", "all"):
        got = daily_bars(px, gw, names, reach[0].day, reach[-1].day, adj=adj, now=now, run=run)
        for k in out:
            out[k] += got[k]
    px.set_meta(f"px:bars:{night.isoformat()}", S.iso(now))
    return out


def flags(px: PS.PxStore, gw: Any, symbols: Iterable[str], calendar: Any, day: dt.date, *, now: dt.datetime,
          run: str) -> dict[str, Any]:
    """FLAGGED(`day`) of every symbol not flagged yet (the module docstring): P's adjusted close READ NOW, at or after
    09:00 ET of `day` (refused before), against P's raw close as stored (read now too when it is not). Write-once."""
    if now < dt.datetime.combine(day, FLAG_FROM, tzinfo=C.NY):
        raise ValueError(f"FLAGGED({day}) reads P's adjusted close at or after 09:00 ET of {day}")
    prior = sessions_before(calendar, day, 1)
    if not prior:
        return {"written": 0, "why": "no session before it on the lane's calendar"}
    prev = prior[-1].day
    todo = sorted(s for s in {str(x).upper() for x in symbols if x} if px.flag(day, s) is None)
    if not todo:
        return {"written": 0, "flagged": 0, "requests": 0}
    out = {"requests": 0, "written": 0, "flagged": 0}
    missing_raw = [s for s in todo if not px.bars(s, [prev], "raw")]
    if missing_raw:
        out["requests"] += daily_bars(px, gw, missing_raw, prev, prev, adj="raw", now=now, run=run)["requests"]
    out["requests"] += daily_bars(px, gw, todo, prev, prev, adj="all", now=now, run=run)["requests"]
    for sym in todo:
        raw = (px.bars(sym, [prev], "raw").get(prev.isoformat()) or {}).get("c")
        adj_row = px.bars(sym, [prev], "all").get(prev.isoformat())
        fresh = adj_row is not None and str(adj_row["fetched_at"]) >= S.iso(now)
        adj = adj_row.get("c") if fresh else None
        if px.put_flag(day, sym, prev, _positive(raw), _positive(adj), run=run, now=now):
            out["written"] += 1
            out["flagged"] += int(bool((px.flag(day, sym) or {}).get("flagged")))
    return out


# ------------------------------------------------------------------------------------------------- the universe
def listed_tickers(tickers: Mapping[str, list[tuple[str, str]]], assets: Mapping[str, Mapping[str, Any]], *,
                   live: bool = True) -> dict[str, list[str]]:
    """{cik: [its tickers the asset list lists on an admitted exchange]} (league/events/universe.py `_listed`), every
    CIK of SEC's copy with at least one."""
    out: dict[str, list[str]] = {}
    for cik, rows in tickers.items():
        mine = [t for t, _ in rows if U._listed(assets.get(t), live)]
        if mine:
            out[cik] = mine
    return out


def operating_fill(px: PS.PxStore, ciks: Iterable[str], day: dt.date, get_sec: Callable[[str], bytes], *,
                   now: dt.datetime, late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """THE OPERATING-COMPANY CACHE (the module docstring): every CIK of `ciks` with no row in px.sqlite's `cik_info`,
    or one older than league/events/universe.py `CIK_TTL`, read through `get_sec` (the lane's SEC reader and its pacing)
    by universe.py's own `operating`; stops once `late()` says so. Returns {read, cached, left}."""
    out = {"read": 0, "cached": 0, "left": 0}
    for cik in sorted(set(ciks)):
        row = px.db.execute("SELECT checked_at FROM cik_info WHERE cik=?", (cik,)).fetchone()
        if row is not None and now - S.parse_iso(row["checked_at"]) <= U.CIK_TTL:
            out["cached"] += 1
            continue
        if late is not None and late():
            out["left"] += 1
            continue
        U.operating(px, get_sec, cik, day, now=now)
        out["read"] += 1
    return out


def cached_operating(px: PS.PxStore, cik: str, day: dt.date, *, now: dt.datetime) -> bool | None:
    """The operating test of `cik` for `day` from the cache alone (None when it is not cached, or stale): no SEC read."""
    row = px.db.execute("SELECT checked_at FROM cik_info WHERE cik=?", (cik,)).fetchone()
    if row is None or now - S.parse_iso(row["checked_at"]) > U.CIK_TTL:
        return None
    return U.operating(px, _cache_only, cik, day, now=now)


def _cache_only(url: str) -> bytes:
    """`cached_operating`'s SEC reader: never called for a fresh cache row (league/events/universe.py `operating`)."""
    raise RuntimeError(f"the operating cache alone is read here, not {url[:60]}")


def universe(px: PS.PxStore, calendar: Any, day: dt.date, *, tickers: Mapping[str, list[tuple[str, str]]],
             assets: Mapping[str, Mapping[str, Any]], now: dt.datetime, run: str, rule: str = S.LIVE_RULE,
             late: Callable[[], bool] | None = None) -> dict[str, Any]:
    """PXU(`day`)'s base (the module docstring) into px.sqlite, write-once per (day, CIK, rule): each CIK with a listed
    ticker not judged yet under `rule`, by the lane's own pure core (league/events/universe.py `eligible_row`) on
    px.sqlite's raw bars and its operating cache, then P's raw close >= $5, ADV20 >= $10M and adjusted bars on each of
    the 61 sessions before `day`. Refuses while the bars are not current (the backfill not done, or no nightly read of
    the session before `day`); a CIK with no cached operating test is left undecided. Never writes the lane's store."""
    prior = sessions_before(calendar, day, ADJUSTED_SESSIONS)
    if len(prior) < ADJUSTED_SESSIONS:
        return {"written": 0, "why": "the lane's calendar holds fewer than 61 sessions before it"}
    prev = prior[-1].day
    if not px.meta("px:backfill:done") or px.meta(f"px:bars:{prev.isoformat()}") is None:
        return {"written": 0, "why": f"the bars are not current through {prev.isoformat()}"}
    live = rule == S.LIVE_RULE
    listed = listed_tickers(tickers, assets, live=live)
    judged = px.judged(day, rule)
    out = {"written": 0, "eligible": 0, "uncached": 0, "left": 0, "candidates": len(listed)}
    last20 = [s.day for s in prior[-U.ADV_SESSIONS:]]
    for cik in sorted(listed):
        if cik in judged:
            continue
        if late is not None and late():
            out["left"] += 1
            continue
        ok = cached_operating(px, cik, day, now=now)
        if ok is None:
            out["uncached"] += 1
            continue
        base = U.eligible_row(calendar, cik, day, tickers=tickers, assets=assets, operating_ok=ok, live=live,
                              bars_of=lambda sym, days: px.bars(sym, days, "raw"))
        row, why = None, None
        if base is None:
            why = "not-operating" if not ok else "ineligible"
        else:
            sym = str(base["symbol"])
            raw = px.bars(sym, last20, "raw")
            adjusted = px.bars(sym, [s.day for s in prior], "all")
            have_adj = sum(1 for s in prior if (adjusted.get(s.day.isoformat()) or {}).get("c") is not None)
            if float(base["prev_close"]) < PX_MIN_PRICE:
                why = "price"
            elif float(base["adv20"]) < PX_MIN_ADV:
                why = "adv"
            elif have_adj < ADJUSTED_SESSIONS:
                why = "adjusted-bars"
            else:
                shares = [float(raw[d.isoformat()].get("v") or 0) for d in last20]
                fetched = [str(r["fetched_at"]) for r in list(raw.values()) + list(adjusted.values())]
                row = {**base, "adv20sh": math.fsum(shares) / len(shares), "adjusted61": have_adj,
                       "inputs_at": max(fetched) if fetched else None}
        if px.put_result(day, cik, rule, row, why=why, run=run, now=now):
            out["written"] += 1
            out["eligible"] += int(row is not None)
    return out


def pm_names(px: PS.PxStore, day: dt.date, rule: str = S.LIVE_RULE) -> list[str]:
    """PX-GAP-O1's premarket names: PXU(day)'s symbols with ADV20 >= $20,000,000."""
    return sorted(str(r["symbol"]) for r in px.universe(day, rule).values() if float(r["adv20"] or 0) >= PM_MIN_ADV)


def names(px: PS.PxStore, day: dt.date, rule: str = S.LIVE_RULE) -> list[str]:
    """PXU(day)'s symbols."""
    return sorted(str(r["symbol"]) for r in px.universe(day, rule).values())


__all__ = ["TokenBucket", "PxGateway", "PxCut", "daily_bars", "minute_bars", "span_1530", "span_pm", "span_v1530",
           "pm_value", "last_close", "volume", "minutes", "backfill", "daily", "flags", "listed_tickers",
           "operating_fill", "cached_operating", "universe", "pm_names", "names", "BARS_PATH", "RATE_PER_MINUTE",
           "LANE_RESERVE", "BACKFILL_SESSIONS", "NIGHTLY_SESSIONS", "ADJUSTED_SESSIONS", "PX_MIN_PRICE", "PX_MIN_ADV",
           "PM_MIN_ADV", "PM_MIN_BARS", "BENCHMARKS"]
