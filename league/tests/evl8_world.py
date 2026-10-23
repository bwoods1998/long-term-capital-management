"""A synthetic week of the event lane for PREREG-EVL-8's tests (league/tests/test_events_evl8.py and
test_events_evl8_proof.py): release 1019e's and PREREG-EVL-5's invented week (league/tests/evl5_world.py: every family
of PREREG-EVL-1, -2, -4 and -5 and two registered births), with the PRICE LANE's invented issuers beside them (PXA..PXZ
and their benchmarks' daily bars, minute bars and premarket bars from `Gateway8`), decided the way the House decides
them: the lane's decisions at their times, PREREG-EVL-8's runs by themselves at section 4.6's times (`decide_week8`),
the hourly re-decisions as backfills. No figure here is a market's: every price is a deterministic function of the
symbol and the day (`daily`).

`pinned()` pins REGISTERED_AT_8 (before the week: Fri Oct 23, 2026, 12:00Z) and refreshes the registries;
`pinned(None)` holds it None for the block (no row of this file in any registry), whatever the tree pins (A122's
2026-10-22T18:43:24Z, release 1019n). The week with PREREG-EVL-8 off and on, the same rows and the
same calls otherwise, is the proof's pair (`run_week`)."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from league.tests import evl4_world as W4
from league.tests import evl5_world as W5

UTC = dt.timezone.utc
et = W4.et
P_DAY, D_DAY, N_DAY = W5.P_DAY, W5.D_DAY, W5.N_DAY
PIN = "2026-10-23T12:00:00Z"
RELEASE = "2026-10-23T13:00:00Z"
#: The price lane's invented issuers (CIKs from 1001), their benchmark by ADV (all above $50M: SPY; the last four IWM).
PX_NAMES = tuple(f"PX{chr(65 + i)}" for i in range(26))
PX_CIK = {t: str(1001 + i).zfill(10) for i, t in enumerate(PX_NAMES)}
SMALL = set(PX_NAMES[-4:])
#: What D's 15:30 mark is against c*_P, by symbol (a symbol not here: 1.000): drops, surges, a news drop.
X1530 = {"PXA": 0.92, "PXB": 0.93, "PXC": 0.94, "PXD": 0.95, "PXE": 1.07, "PXF": 1.08, "PXG": 0.80, "PXH": 0.91,
         "PXI": 1.06, "PXJ": 0.90}
#: The surge names' volume through 15:30 against ADV20sh (V_D): PXE 2.0, PXF 1.6, PXI 1.2 (too thin).
VOLUME = {"PXE": 2.0, "PXF": 1.6, "PXI": 1.2}
#: The premarket indication against c*_P (PX-GAP-O1): PXK and PXL gap down, PXM has too few bars.
PM = {"PXK": 0.94, "PXL": 0.95, "PXM": 0.93}
PM_THIN = {"PXM"}


def unit(*parts: Any) -> float:
    """A deterministic number in [-1, 1) of its parts (no market's figure)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / float(1 << 63) - 1.0


def daily(symbol: str, day: dt.date) -> dict[str, float]:
    """Symbol `symbol`'s invented daily bar of `day` (raw = adjusted): close about 20 (SPY 500, IWM 200) moving 1.5% a
    day, open 0.5% off the previous close, volume 2,000,000 (the benchmarks 50,000,000)."""
    base = {"SPY": 500.0, "IWM": 200.0}.get(symbol, 20.0 + PX_NAMES.index(symbol) if symbol in PX_NAMES else 20.0)
    c = base * (1.0 + 0.015 * unit(symbol, day, "c"))
    o = base * (1.0 + 0.015 * unit(symbol, day - dt.timedelta(days=1), "c")) * (1.0 + 0.005 * unit(symbol, day, "o"))
    vol = 50_000_000.0 if symbol in ("SPY", "IWM") else (600_000.0 if symbol in SMALL else 2_000_000.0)
    return {"o": round(o, 4), "h": round(max(o, c) * 1.01, 4), "l": round(min(o, c) * 0.99, 4), "c": round(c, 4),
            "v": vol}


class Gateway8(W5.Gateway):
    """evl5_world's gateway, and for the price lane's names and both benchmarks: daily bars (`daily`), the 15:00-15:30
    minute bars (the last one's close `X1530` x P's close), the day's minute volumes (`VOLUME` x ADV20sh, the rest
    0.5 x), the premarket bars (08:00-08:58: `PM` x P's close, three bars with volume, PXM one) and the 09:30 minute
    (open 1.001 x P's close). `adjust` {(symbol, day): factor}: the vendor's adjusted bars of a day differ by it (a
    split read after the morning's c*_P)."""

    def __init__(self, **kw: Any):
        super().__init__(**kw)
        self.adjust: dict[tuple[str, dt.date], float] = {}
        self.px_gets: list[tuple[str, dict[str, Any]]] = []

    def prev_close(self, symbol: str, day: dt.date) -> float:
        prev = day - dt.timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= dt.timedelta(days=1)
        return daily(symbol, prev)["c"]

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        from league.events import store as S

        params = dict(params or {})
        if path.endswith("/v2/stocks/bars"):
            symbols = [x for x in str(params["symbols"]).split(",") if x]
            px = [s for s in symbols if s in PX_NAMES or s in ("SPY", "IWM")]
            if px and len(px) == len(symbols):
                self.px_gets.append((path, params))
                end = S.parse_iso(params["end"])
                if params.get("timeframe") == "1Min":
                    start = S.parse_iso(params["start"])
                    return {"bars": self._minutes(px, start, end), "next_page_token": None}
                first = dt.date.fromisoformat(str(params["start"])[:10])
                last = (end - dt.timedelta(minutes=1)).date()
                out = {}
                for s in px:
                    rows = []
                    for d in W4.weekdays(first, last):
                        b = daily(s, d)
                        f = self.adjust.get((s, d), 1.0) if params.get("adjustment") == "all" else 1.0
                        rows.append({"t": f"{d}T04:00:00Z", "o": b["o"] * f, "h": b["h"] * f, "l": b["l"] * f,
                                     "c": round(b["c"] * f, 4), "v": b["v"], "n": 100, "vw": b["c"]})
                    out[s] = rows
                return {"bars": out, "next_page_token": None}
        return super().get_json(path, params)

    def _minutes(self, symbols: list[str], start: dt.datetime, end: dt.datetime) -> dict[str, list[dict[str, Any]]]:
        from league.events import calendar as C
        from league.events import store as S

        day = start.astimezone(C.NY).date()
        local = start.astimezone(C.NY).time()
        n = int((end - start).total_seconds() // 60)
        out: dict[str, list[dict[str, Any]]] = {}
        for s in symbols:
            prev = self.prev_close(s, day)
            bars = []
            for k in range(n):
                t = start + dt.timedelta(minutes=k)
                if local == dt.time(15, 0):        # the px1530 span
                    c = prev * (X1530.get(s, 1.0) if k == n - 1 else 1.0)
                    bars.append({"t": S.iso(t), "o": c, "h": c, "l": c, "c": round(c, 4), "v": 100})
                elif local == dt.time(8, 0):       # the premarket span: the last three minutes trade (PXM's last one)
                    if k < n - (1 if s in PM_THIN else 3):
                        continue
                    c = prev * PM.get(s, 1.0)
                    bars.append({"t": S.iso(t), "o": c, "h": c, "l": c, "c": round(c, 4), "v": 500})
                elif local == dt.time(9, 30) and n > 5:      # the day's volumes through 15:30
                    adv = 600_000.0 if s in SMALL else (50_000_000.0 if s in ("SPY", "IWM") else 2_000_000.0)
                    share = VOLUME.get(s, 0.5) * adv / n
                    bars.append({"t": S.iso(t), "o": prev, "h": prev, "l": prev, "c": prev, "v": share})
                else:                                         # the 09:30 minute
                    o = prev * 1.001
                    bars.append({"t": S.iso(t), "o": round(o, 4), "h": o, "l": o, "c": round(o, 4), "v": 100})
            out[s] = bars
        return out


def sec8(url: str) -> bytes:
    """evl5_world's SEC with the price lane's names in the tickers file."""
    if url.endswith("company_tickers.json"):
        rows = {str(i): {"cik_str": i + 1, "ticker": t, "title": f"{t} Inc."} for i, t in enumerate(W5.TICKERS)}
        rows.update({str(1000 + i): {"cik_str": int(PX_CIK[t]), "ticker": t, "title": f"{t} Corp."}
                     for i, t in enumerate(PX_NAMES)})
        return json.dumps(rows).encode()
    return W5.sec(url)


@contextlib.contextmanager
def pinned(at: str = PIN) -> Iterator[None]:
    """REGISTERED_AT_8 pinned for the body (the registries refreshed), set back to None after."""
    from league.events import programs as P

    was = P.REGISTERED_AT_8
    P.REGISTERED_AT_8 = at
    P.refresh_8()
    try:
        yield
    finally:
        P.REGISTERED_AT_8 = was
        P.refresh_8()


class World8(W5.World):
    """evl5_world's lane store with the price lane's names in a later tickers copy (Oct 20) and, with `eight`, px.sqlite
    seeded as the recorders leave it before the week (the 270-session backfill's bars, each night's bars, the cache)
    and THE RELEASE marked (Oct 23, 13:00Z)."""

    def __init__(self, root: str | Path, gateway: Gateway8 | None = None, *, eight: bool = True):
        super().__init__(root, gateway or Gateway8())
        from league.events import run as R

        self.ctx = R.Context(self.st, self.gw, sec8, now=lambda: self.now)
        self.st.set_meta("tickers@2026-10-20T01:05:00Z", self.st.put_document(sec8("x/company_tickers.json"), "t8"))
        self.eight = eight
        if eight:
            from league.events import store as S
            self.st.set_meta("evl8:release", RELEASE)
            self.seed_px()

    def close(self) -> None:
        """The store closed and R3's births the week loaded UNLOADED (`programs.load_births(None)`, as PREREG-EVL-5's
        tests clean up after `births`), so no later test of the process reads them in the registries."""
        from league.events import programs as P

        try:
            super().close()
        finally:
            P.load_births(None)

    def px(self) -> Any:
        from league.events import px as PXL

        return PXL.open_px(self.root)

    def seed_px(self) -> None:
        """px.sqlite as the PX recorders leave it: every name's and benchmark's raw and adjusted bars from Aug 3, 2026 to
        Mon Oct 26 (fetched on the night of each), each night marked, the backfill done, the operating cache, and PXU's
        base of Tue Oct 27 and Wed Oct 28 (px_universe, the live rule) written by the 07:40 recorder."""
        from league.events import calendar as C
        from league.events import store as S

        px = self.px()
        try:
            days = [s.day for s in C.sessions(self.st, dt.date(2026, 8, 3), N_DAY)]
            with px.tx() as db:
                for sym in (*PX_NAMES, "SPY", "IWM"):
                    for d in days:
                        if d >= D_DAY:
                            continue
                        b = daily(sym, d)
                        fetched = S.iso(et(d, 20, 0))
                        for adj in ("raw", "all"):
                            db.execute("INSERT OR REPLACE INTO px_bars(symbol, day, adj, o, h, l, c, v, n, vw, t, fetched_at, "
                                       "run) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 100, ?, ?, ?, 'seed')",
                                       (sym, d.isoformat(), adj, b["o"], b["h"], b["l"], b["c"], b["v"], b["c"],
                                        f"{d}T04:00:00Z", fetched))
                for d in days:
                    db.execute("INSERT OR REPLACE INTO px_meta(key, value) VALUES(?, ?)",
                               (f"px:bars:{d.isoformat()}", S.iso(et(d, 20, 5))))
                db.execute("INSERT OR REPLACE INTO px_meta(key, value) VALUES('px:backfill:done', '2026-10-20T03:00:00Z')")
                for t in PX_NAMES:
                    db.execute("INSERT OR REPLACE INTO cik_info(cik, sic, periodic_form, periodic_at, operating, "
                               "checked_at) VALUES(?, ?, '10-Q', '2026-08-01', 1, '2026-10-20T03:00:00Z')",
                               (PX_CIK[t], "2834" if PX_NAMES.index(t) % 2 else "3571"))
            for day in (D_DAY, N_DAY):
                self.seed_universe(px, day)
        finally:
            px.close()

    def seed_universe(self, px: Any, day: dt.date) -> None:
        """PXU's base of `day` (px_universe's live rows), as league/events/pxdata.py `universe` writes them at 07:40 ET."""
        from league.events import calendar as C

        prior = C.previous(self.st, day, 20)
        for t in PX_NAMES:
            adv = sum(daily(t, s.day)["c"] * daily(t, s.day)["v"] for s in prior) / len(prior)
            row = {"symbol": t, "name": f"{t} Corp.", "exchange": "NASDAQ", "prev_close": daily(t, prior[-1].day)["c"],
                   "adv20": adv, "adv20sh": daily(t, prior[-1].day)["v"], "bench": "IWM" if adv < 50_000_000 else "SPY",
                   "adjusted61": 61, "inputs_at": "2026-10-20T03:00:00Z"}
            px.put_result(day, PX_CIK[t], "live", row, why=None, run="seed-universe", now=et(day, 7, 40))

    # -- the House's runs of PREREG-EVL-8 ---------------------------------------------------------------------------
    def morning(self, day: dt.date) -> dict[str, Any]:
        from league.events import px as PXL

        px = self.px()
        try:
            return PXL.morning(px, self.st, self.gw, day, now=self.now, run=f"px8-am:{day}",
                               tickers=self.ctx.tickers_for(day), assets=self.ctx.assets(True), clock=lambda: self.now)
        finally:
            px.close()

    def mid(self, day: dt.date) -> dict[str, Any]:
        from league.events import px as PXL

        px = self.px()
        try:
            return PXL.mid(px, self.gw, self.st, day, now=self.now, run=f"px8-mid:{day}")
        finally:
            px.close()

    def px_decide(self, day: dt.date, auction: str, *, kind: str = "live",
                  late: Callable[[], bool] | None = None) -> dict[str, Any]:
        from league.events import px as PXL

        px = self.px()
        try:
            return PXL.decide(px, self.st, self.gw, day, auction, now=lambda: self.now, kind=kind,
                              tickers=self.ctx.tickers_for(day), late=late)
        finally:
            px.close()

    def meta_decide(self, day: dt.date, auction: str, *, kind: str = "live") -> dict[str, Any]:
        from league.events import meta as MT

        return MT.decide(self.st, day, auction, now=lambda: self.now, kind=kind)

    def ran(self, key: str, day: dt.date) -> None:
        """The House's mark that a run behind a late pass of the book finished (league/events/px.py `RAN_KEY`)."""
        from league.events import px as PXL
        from league.events import store as S

        self.st.set_meta(PXL.RAN_KEY.format(key=key, day=day.isoformat()), json.dumps({"at": S.iso(self.now)}))

    def redecide(self, day: dt.date, auction: str) -> dict[str, Any]:
        from league.events import px as PXL

        px = self.px()
        try:
            return PXL.redecide(px, self.st, day, auction, now=self.now, tickers=self.ctx.tickers_for(day))
        finally:
            px.close()


def decide_week8(w: World8, *, late: bool = True) -> None:
    """The House's week with PREREG-EVL-8's runs at section 4.6's times when `w.eight`: each session's morning pass at
    09:05 ET, the lane's live open decision at 09:15:30 and on its receipt PX-GAP-O1's run and EVL-META-O1's part, the
    09:30 opens at 10:00, PX-DROP-ON's and PX-SURGE-ON's run at 15:46:05, the lane's live close decision at 15:47 and on
    its receipt EVL-META-ON's part, then the re-decisions as backfills (PX's with them)."""
    w.at(et(P_DAY, 15, 47)).decide("close", P_DAY)
    for day in (D_DAY, N_DAY):
        w.at(et(day, 7, 31)).decide("open", day, ask_only=True)
        w.at(et(day, 7, 32)).decide("close", day, ask_only=True)
        if w.eight:
            w.at(et(day, 9, 5)).morning(day)
        w.at(et(day, 9, 15, 30)).decide("open", day)
        if w.eight:
            w.at(et(day, 9, 16, 0)).px_decide(day, "o1")
            w.at(et(day, 9, 16, 20)).meta_decide(day, "o1")
            w.ran("open", day)
            w.at(et(day, 10, 0)).mid(day)
        w.at(et(day, 12, 30)).decide("close", day, ask_only=True)
        w.at(et(day, 15, 17)).decide("close", day, ask_only=True)
        if w.eight:
            w.at(et(day, 15, 46, 5)).px_decide(day, "on")
        w.at(et(day, 15, 47)).decide("close", day)
        if w.eight:
            w.at(et(day, 15, 48, 10)).meta_decide(day, "on")
            w.ran("close-meta", day)
        if day == D_DAY and late:
            w.filing("0000000008-26-000002", "HHH", accepted=et(D_DAY, 14, 0), items=("2.02",), stored=et(D_DAY, 16, 30))
            w.article("n-aac-2", "AAC", knowable=et(D_DAY, 14, 0), stored=et(D_DAY, 16, 30))
            w.article("n-pxb-late", "PXB", knowable=et(D_DAY, 14, 30), stored=et(D_DAY, 16, 30))
            w.at(et(D_DAY, 16, 40)).decide("open", D_DAY, live=False)
            w.at(et(D_DAY, 16, 41)).decide("close", D_DAY, live=False)
            if w.eight:
                w.at(et(D_DAY, 16, 42)).redecide(D_DAY, "on")
    w.at(et(N_DAY, 16, 40)).decide("open", D_DAY, live=False)
    w.at(et(N_DAY, 16, 41)).decide("close", D_DAY, live=False)
    w.at(et(N_DAY, 16, 42)).decide("open", N_DAY, live=False)
    w.at(et(N_DAY, 16, 43)).decide("close", N_DAY, live=False)


def the_week8(w: World8) -> None:
    w.births()
    W5.evl4_rows(w)
    W5.evl5_rows(w)
    # the price lane's own rows: an article on PXH in D's ON span stored before tau (PXH has no PX event at D's close),
    # a two-symbol article naming PXJ (a ticker the tickers copy maps), an 8-K of PXL in D's O1 span
    w.article("n-pxh-1", "PXH", knowable=et(D_DAY, 11, 0))
    w.article("n-pxj-1", "AAA", knowable=et(D_DAY, 12, 0), symbols=["AAA", "PXJ"])
    w.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, "
                    "source, status) VALUES('0000001012-26-000001', '8-K', ?, 'PXL Corp.', '[\"8.01\"]', ?, ?, ?, "
                    "'current', 'fetched')", (PX_CIK["PXL"], "2026-10-27T11:00:00Z", "2026-10-27T11:10:00Z",
                                              "2026-10-27T11:10:00Z"))
    decide_week8(w)


def earlier(program: str, version: int) -> bool:
    """A program of PREREG-EVL-1 to -7 or R3's births (not this file's)."""
    from league.events import programs as P

    return not P.is_8(program)


def run_week(root: str | Path, *, eight: bool) -> dict[str, Any]:
    """The week decided with PREREG-EVL-8 on (pinned, its runs made) or off (UNPINNED: REGISTERED_AT_8 None for the
    block, whatever the tree pins, so no row of it is in any registry and no run of it is made): every intent and every
    earlier seatable program's real-money picks (`W5.picks`)."""
    ctx = pinned() if eight else pinned(None)
    with ctx:
        world = World8(root, eight=eight)
        try:
            the_week8(world)
            return {"intents": [list(r) for r in world.intents()],
                    "picks": W5.picks(world, lambda p: earlier(p.id, p.version)), "births": births_view(world),
                    "world": None}
        finally:
            world.close()


#: A births proposal the validator judges in the proof (an open-entry 8-K rule; its Jaccard against every registered
#: program is what the proof compares).
PROPOSAL = {"spec": {"id": "EVL-B-8K-801", "version": 1, "family": "8k", "rule": {"items": ["8.01"]}, "entry": "open",
                     "exit": "close", "hold": 1, "rank": "none", "seatable": False}, "why": "invented", "by": "test"}


def births_view(world: World8) -> dict[str, Any]:
    """R3's births job's FACTS of the week's last session and its validator's verdict on `PROPOSAL` (its Jaccard against
    every registered program), as the births job reads them (league/events/births.py `Facts`, `validate`)."""
    from league.events import births as BI

    facts = BI.Facts(world.st, N_DAY)
    sheet = facts.facts()
    checked = BI.validate(world.st, facts, [PROPOSAL], night=N_DAY)
    return {"facts": json.loads(json.dumps(sheet, sort_keys=True, default=str)),
            "validate": [{k: c.get(k) for k in ("ok", "reasons", "selected", "per_session", "jaccard")} for c in checked]}


__all__ = ["PIN", "RELEASE", "PX_NAMES", "PX_CIK", "X1530", "VOLUME", "PM", "unit", "daily", "Gateway8", "sec8",
           "pinned", "World8", "decide_week8", "the_week8", "earlier", "run_week", "PROPOSAL", "births_view"]
