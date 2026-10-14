"""Synthetic panels for tests: never market data. Every package's tests build their evidence on these.

Owner: package C.

A synthetic panel is a whole `<root>` as the House holds it: E1's store for the REF symbols (through
`league.equity.synth.synthetic_store`: the one call of this package into it), the universe files with a fixed TEST
salt (`store.write_universe`), and the panel through `store.write_panel`. Seeded and deterministic: the same arguments
write the same bytes. No 2020 session exists in any of them. The price paths are seeded pseudo-random numbers on the
true NYSE calendar (`league.equity.store.nyse_sessions`): no real price, return or membership date is in them, and
every member ticker is made up ("ZQAA", "ZQAB", ...; two of them carry the tickers of one pair of
`config.CLASS_PAIRS`, so the class-of-the-month rule has something to choose between).

THE PATHS. The REF columns are E1's synthetic store's own bars (independent random walks). A member asset loads on the
market and on ONE sector fund: each session's overnight and intraday log-moves are beta x SPY's + gamma x its fund's +
its own noise (`vol` a year, split 20/80 between the two legs, each asset from its own seeded stream, so adding an
asset moves no other). So a name's statistical sector (`ctx.derive`) is the fund it was built on, betas spread around
1, and the sectors have unequal sizes (`SECTOR_SHARES`): a panel of 60 names has cells of every small kind and one of
200 or more has the full 3 x 3 cells too. Raw prices are rounded to `raw_places` decimals (4, the venue's precision;
`cent_panel`: 2, the tape's grid); adjustment=all is the raw path times every later event's factor ((1 - dividend /
the previous raw close) / split factor), ROUNDED TO THE CENT as the vendor's is, as of the fetch day `as_of`: two
panels that differ only in `as_of` hold one raw history under two vintages. Every asset has bars on every session,
before it joins the index and after it leaves it, except the names of `vanish`, whose bars end. From a split's ex-day
on the share volume is multiplied by its factor, as a real one's is.

MEMBERSHIP. `n_assets` names are members at the start; each year `churn` of them leave and as many new assets join on
random sessions (never in 2020, which no panel holds). An ended spell's `exit` cycles through `store.EXITS`. The two
class-pair assets never leave.

THE I6 HELPER (`same_ctx_cases`) draws decision days of a window and returns, for each, the Gym's `ctx.Inputs` and the
venue-shaped rows a live fetch of that day would hold for the same columns under the same run key, so a test feeds the
rows to the live builder and compares `ctx.ctx_bytes`.

Evidence module (in the xs identity: `XS_EVIDENCE`'s extra, as `synth` is E1's).
"""

from __future__ import annotations

import datetime as dt
import math
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import synth as _e1_synth
from ..equity.store import ALL_COLUMNS, RAW_COLUMNS, as_date, from_ordinal, nyse_sessions, ordinal
from . import PANELS, config, store
from .ctx import derive, inputs_from_panel
from .program import Needs

#: The fixed salt of every synthetic panel (32 bytes; never the House's).
TEST_SALT = bytes(range(32))
#: The share of a synthetic panel's names built on each fund of `config.FUNDS`, in its order.
SECTOR_SHARES = (0.30, 0.20, 0.14, 0.10, 0.07, 0.06, 0.04, 0.03, 0.03, 0.02, 0.01)
#: The class pair two synthetic assets carry (the first trades more in every other half year: the choice flips).
PAIR = config.CLASS_PAIRS[-1]
#: A planted edge is re-ranked every this many sessions, on the trailing signal, inside each fund's names.
PLANT_SESSIONS = 5
SIGNALS = ("reversal", "momentum", "low_vol")
#: The share of a member's `vol` that is its own noise (the rest comes from its market and fund loadings).
IDIO_SHARE = 0.6


def _ticker(index: int) -> str:
    """The made-up ticker of the `index`-th synthetic asset: ZQAA, ZQAB, ..., ZQZZ, ZQAAA, ..."""
    index, width = int(index), 2
    while index >= 26 ** width:
        index -= 26 ** width
        width += 1
    letters = ""
    for _ in range(width):
        letters = chr(ord("A") + index % 26) + letters
        index //= 26
    return "ZQ" + letters


def _ref_bars(root: Path, days: Sequence[dt.date]) -> tuple[np.ndarray, np.ndarray]:
    """E1's synthetic store's REF bars on `days`: raw (n, 12, 5) and adj (n, 12, 4), read as the store's writer (the
    files this very call wrote; no window is opened)."""
    ordinals = np.array([ordinal(d) for d in days], dtype=np.int32)
    raw = np.full((len(days), len(config.REF), 5), np.nan)
    adj = np.full((len(days), len(config.REF), 4), np.nan)
    for col, symbol in enumerate(config.REF):
        with np.load(root / "bars" / f"{symbol}.npz", allow_pickle=False) as series:
            own = np.asarray(series["days"], dtype=np.int32)
            at = np.searchsorted(own, ordinals)
            hit = (at < own.shape[0]) & (own[np.minimum(at, own.shape[0] - 1)] == ordinals)
            for k, name in enumerate(RAW_COLUMNS):
                raw[hit, col, k] = np.asarray(series[name], dtype=np.float64)[at[hit]]
            for k, name in enumerate(ALL_COLUMNS):
                adj[hit, col, k] = np.asarray(series[name], dtype=np.float64)[at[hit]]
    return raw, adj


def _membership(n_assets: int, days: Sequence[dt.date], seed: int, churn: float, pair: bool) -> list[dict[str, Any]]:
    """The synthetic assets with their spells, in aid order: the starters by ticker, then the joiners by their day."""
    rng = random.Random(f"xs-synth-members|{int(seed)}")
    names = [_ticker(i) for i in range(n_assets - (2 if pair else 0))]
    starters = sorted([*(PAIR if pair else ()), *names])
    assets = [{"ticker": t, "start": days[0], "end": None, "exit": None, "fixed": t in PAIR} for t in starters]
    made = len(names)
    leavers = max(1, round(churn * n_assets)) if churn > 0 else 0
    changes: list[dt.date] = []
    for year in sorted({d.year for d in days}):
        own = [d for d in days[5:] if d.year == year]
        if own and leavers:
            changes += sorted(rng.sample(own, min(leavers, len(own))))
    exits = 0
    for day in changes:
        inside = [a for a in assets if a["end"] is None and not a["fixed"] and a["start"] < day]
        if not inside:
            continue
        gone = rng.choice(inside)
        gone["end"], gone["exit"] = day, store.EXITS[exits % len(store.EXITS)]
        exits += 1
        assets.append({"ticker": _ticker(made), "start": day, "end": None, "exit": None, "fixed": False})
        made += 1
    return assets


def _paths(assets: Sequence[Mapping[str, Any]], sessions: Sequence[dt.date], ref_raw: np.ndarray, *, seed: int,
           drift: float, vol: float, raw_places: int, events: Mapping[int, tuple[np.ndarray, np.ndarray]],
           planted: tuple[float, str] | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The members' raw bars over EVERY session of the calendar (the reserve's too: a path does not stop for it):
    raw (n, N, 5), the dividend and split of each session (n, N) each. `ref_raw`: the REF bars on the same sessions."""
    n, count = len(sessions), len(assets)
    shape = np.random.default_rng([int(seed), 20261011, 1])
    shares = np.cumsum(SECTOR_SHARES)
    fund = np.minimum(np.searchsorted(shares, (np.arange(count) * 0.6180339887498949) % 1.0, side="right"),
                      len(config.FUNDS) - 1)
    beta = shape.uniform(0.5, 1.5, count)
    gamma = shape.uniform(0.6, 1.2, count)
    start = 20.0 + shape.uniform(0.0, 280.0, count)
    base_volume = shape.uniform(2e5, 2e7, count)
    paired = [i for i, asset in enumerate(assets) if asset["ticker"] in PAIR]
    if len(paired) == 2:
        base_volume[paired[1]] = base_volume[paired[0]]      # one company: the classes differ by the swing below
    sd = float(vol) * IDIO_SHARE / math.sqrt(252.0)
    mu = float(drift) / 252.0 - 0.5 * sd * sd

    def legs(col: int) -> tuple[np.ndarray, np.ndarray]:
        with np.errstate(invalid="ignore", divide="ignore"):
            over = np.zeros(n)
            over[1:] = np.log(ref_raw[1:, col, 0] / ref_raw[:-1, col, 3])
            intra = np.log(ref_raw[:, col, 3] / ref_raw[:, col, 0])
        return np.nan_to_num(over), np.nan_to_num(intra)

    market = legs(config.MARKET_COLUMN)
    funds = [legs(col) for col in config.FUND_COLUMNS]
    overnight, intraday = np.empty((n, count)), np.empty((n, count))
    wicks, volume = np.empty((n, count, 2)), np.empty((n, count))
    for i in range(count):
        rng = np.random.default_rng([int(seed), 20261011, 2, i])
        overnight[:, i] = beta[i] * market[0] + gamma[i] * funds[fund[i]][0] + rng.normal(0.2 * mu, sd * math.sqrt(0.2), n)
        intraday[:, i] = beta[i] * market[1] + gamma[i] * funds[fund[i]][1] + rng.normal(0.8 * mu, sd * math.sqrt(0.8), n)
        wicks[:, i] = np.abs(rng.normal(0.0, 0.3 * sd, (n, 2)))
        volume[:, i] = np.floor(base_volume[i] * np.exp(rng.normal(0.0, 0.3, n)))
        if assets[i]["ticker"] == PAIR[0]:
            volume[:, i] = np.floor(volume[:, i] * np.where((np.arange(n) // 126) % 2 == 0, 4.0, 0.25))
    overnight[0] = 0.0
    if planted is not None:
        edge, signal = float(planted[0]) / 252.0, planted[1]
        level = np.zeros((n, count))            # the cumulative log path, with what was planted so far
        for first in range(0, n, PLANT_SESSIONS):
            last = min(first + PLANT_SESSIONS, n)
            if first >= 2:
                if signal == "reversal":
                    score = -(level[first - 1] - level[max(0, first - 1 - PLANT_SESSIONS)])
                elif signal == "momentum":
                    back = max(0, first - 1 - config.MOM_BACK)
                    score = level[max(0, first - 1 - config.MOM_SKIP)] - level[back]
                else:
                    moves = np.diff(level[max(0, first - 61):first], axis=0)
                    score = -moves.std(axis=0) if moves.shape[0] > 1 else np.zeros(count)
                for g in range(len(config.FUNDS)):
                    names = np.flatnonzero(fund == g)
                    if names.size >= 3:
                        top = names[np.argsort(-score[names], kind="stable")[:max(1, names.size // 3)]]
                        intraday[first:last, top] += edge
            before = level[first - 1] if first else np.zeros(count)
            level[first:last] = before + np.cumsum(overnight[first:last] + intraday[first:last], axis=0)
    raw = np.empty((n, count, 5))
    dividend, split = np.zeros((n, count)), np.ones((n, count))
    for i, (div, ratio) in events.items():
        dividend[:, i], split[:, i] = div, ratio
        volume[:, i] = np.floor(volume[:, i] * np.cumprod(ratio))    # after a split the same dollars are more shares
    plain = [i for i in range(count) if i not in events]
    if plain:
        close = start[plain] * np.exp(np.cumsum(overnight[:, plain] + intraday[:, plain], axis=0))
        before = np.vstack([start[plain][None, :], close[:-1]])
        raw[:, plain, 0] = before * np.exp(overnight[:, plain])
        raw[:, plain, 3] = close
    for i in events:                                    # an event moves the level: these few walk session by session
        price = float(start[i])
        for s in range(n):
            opened = max((price - dividend[s, i]) / split[s, i], 0.01) * math.exp(overnight[s, i])
            price = opened * math.exp(intraday[s, i])
            raw[s, i, 0], raw[s, i, 3] = opened, price
    grid = 10.0 ** -raw_places
    raw[:, :, 0] = np.maximum(np.round(raw[:, :, 0], raw_places), grid)
    raw[:, :, 3] = np.maximum(np.round(raw[:, :, 3], raw_places), grid)
    raw[:, :, 1] = np.round(np.maximum(raw[:, :, 0], raw[:, :, 3]) * (1.0 + wicks[:, :, 0]), raw_places)
    raw[:, :, 2] = np.maximum(np.round(np.minimum(raw[:, :, 0], raw[:, :, 3]) * (1.0 - wicks[:, :, 1]), raw_places),
                              grid)
    raw[:, :, 4] = np.maximum(volume, 1.0)
    return raw, dividend, split


def _adjusted(raw: np.ndarray, dividend: np.ndarray, split: np.ndarray, applied: np.ndarray) -> np.ndarray:
    """adjustment=all of raw o h l c (n, N, 4) as of a fetch: every price before an applied event's ex-day times (1 -
    dividend / the previous raw close) / split, ROUNDED TO THE CENT (the vendor's)."""
    n, count = raw.shape[:2]
    factor = np.ones((n, count))
    step = np.ones(count)
    for s in range(n - 1, 0, -1):
        if applied[s]:
            event = (dividend[s] != 0.0) | (split[s] != 1.0)
            if bool(event.any()):
                step = np.where(event, step * (1.0 - dividend[s] / raw[s - 1, :, 3]) / split[s], step)
        factor[s - 1] = step
    return np.round(raw[:, :, :4] * factor[:, :, None], 2)


def synthetic_panel(root: str | Path, *, n_assets: int = 60, start: dt.date = dt.date(2016, 1, 4),
                    end: dt.date = dt.date(2026, 10, 9), seed: int = 7, drift: float = 0.0, vol: float = 0.25,
                    churn: float = 0.05, splits: Mapping[int, tuple[dt.date, float]] | None = None,
                    dividends: Mapping[int, Sequence[tuple[dt.date, float]]] | None = None,
                    vanish: Sequence[tuple[int, dt.date]] = (), gate: bool = False,
                    as_of: dt.date | None = None, raw_places: int = 4, masked: Mapping[int, str] | None = None,
                    live_from: dt.date | None = None, _planted: tuple[float, str] | None = None) -> Path:
    """Write a synthetic panel at `root` and return it: `n_assets` member assets (aids from 100) with sector structure
    (each loads on one REF fund), `churn` of them leaving and joining the index a year, `splits` {aid: (day, factor)},
    `dividends` {aid: [(ex day, dollars)]}, `vanish` [(aid, last bar day)] (bars end while still a member). `gate`:
    write E1's GATE mark (so a capability can be minted on it). `as_of`: the day the adjustment=all series is fetched
    (default `end`): two panels that differ only in it hold the same history under two vintages, each rounded to the
    cent as the vendor's is. `raw_places`: the raw prices' decimals (the REF columns' too). `masked` {aid: one of
    `store.MASKS`}. `live_from`: the manifest's (None: every member is tradable on every day)."""
    root = Path(root)
    if n_assets < 2 or raw_places not in (2, 3, 4):
        raise ValueError("a synthetic panel has at least two assets and raw prices of 2 to 4 decimals")
    sessions = [d for d, _ in nyse_sessions(start, end)]
    if not sessions:
        raise ValueError(f"no session from {start} to {end}")
    through = sessions[-1] if as_of is None else max((d for d in sessions if d <= as_date(as_of)), default=None)
    if through is None:
        raise ValueError(f"no session on or before {as_of}")
    _e1_synth.synthetic_store(root, symbols=config.REF, start=start, end=end, seed=seed, drift=drift, gate=gate,
                              as_of=through)
    held = [d for d in sessions if d <= through]
    panel_days = [d for d in held if d.year not in config.RESERVE_YEARS]
    pair = n_assets >= 12
    assets = _membership(n_assets, panel_days, seed, churn, pair)
    aid_of = {i: store.FIRST_MEMBER_AID + i for i in range(len(assets))}
    index_of = {aid: i for i, aid in aid_of.items()}
    position = {d: i for i, d in enumerate(sessions)}
    events: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def event(aid: Any) -> tuple[np.ndarray, np.ndarray]:
        if int(aid) not in index_of:
            raise ValueError(f"the synthetic panel has no aid {aid}")
        return events.setdefault(index_of[int(aid)], (np.zeros(len(sessions)), np.ones(len(sessions))))

    for aid, rows in (dividends or {}).items():
        for day, amount in rows:
            if as_date(day) not in position:
                raise ValueError(f"aid {aid}'s dividend ex-day {day} is not a session")
            event(aid)[0][position[as_date(day)]] += float(amount)
    for aid, (day, factor) in (splits or {}).items():
        if as_date(day) not in position:
            raise ValueError(f"aid {aid}'s split ex-day {day} is not a session")
        event(aid)[1][position[as_date(day)]] *= float(factor)
    ref_all = _ref_bars(root, sessions)[0]
    ref_all = np.where(np.isfinite(ref_all), ref_all, 1.0)        # the sessions after `through` move no kept row
    raw_all, dividend, split = _paths(assets, sessions, ref_all, seed=seed, drift=drift, vol=vol,
                                      raw_places=raw_places, events=events, planted=_planted)
    applied = np.array([d <= through for d in sessions], dtype=bool)
    adj_all = _adjusted(raw_all, dividend, split, applied)
    keep = np.array([position[d] for d in panel_days], dtype=np.int64)
    ref_raw, ref_adj = _ref_bars(root, panel_days)
    if raw_places < 4:
        ref_raw[:, :, :4] = np.round(ref_raw[:, :, :4], raw_places)
    ref_adj = np.round(ref_adj if raw_places == 4 else ref_raw[:, :, :4], 2)
    raw = np.concatenate([ref_raw, raw_all[keep]], axis=1)
    adj = np.concatenate([ref_adj, adj_all[keep]], axis=1)
    ref, n, m = len(config.REF), len(panel_days), len(config.REF) + len(assets)
    for aid, last in vanish:
        if int(aid) not in index_of:
            raise ValueError(f"the synthetic panel has no aid {aid}")
        gone = np.array([d > as_date(last) for d in panel_days], dtype=bool)
        raw[gone, ref + index_of[int(aid)], :] = np.nan
        adj[gone, ref + index_of[int(aid)], :] = np.nan
    member = np.zeros((n, m), dtype=bool)
    for i, asset in enumerate(assets):
        member[:, ref + i] = [asset["start"] <= d and (asset["end"] is None or d < asset["end"]) for d in panel_days]
    tradable = np.zeros((n, m), dtype=bool)
    tradable[:, ref:] = True
    costs = np.random.default_rng([int(seed), 20261011, 3])
    hs = np.full((m, 2), config.HS_FLOOR_BP / 10_000.0)
    hs[ref:, 0] = costs.uniform(3.0, 12.0, len(assets)) / 10_000.0
    hs[ref:, 1] = costs.uniform(3.0, 6.0, len(assets)) / 10_000.0
    masks = {int(aid): str(why) for aid, why in (masked or {}).items()}
    if set(masks) - set(index_of):
        raise ValueError("masked names an aid the synthetic panel does not have")
    book: dict[int, dict[str, Any]] = {
        aid: {"spells": [], "symbol": symbol, "alpaca": None, "ref": True, "renames": [], "masked": None}
        for aid, symbol in zip(store.REF_AIDS, config.REF)}
    spells = []
    for i, asset in enumerate(assets):
        aid = aid_of[i]
        book[aid] = {"spells": [[asset["ticker"], asset["start"], asset["end"], asset["exit"]]],
                     "symbol": asset["ticker"],
                     "alpaca": {"id": f"synthetic-{aid}", "status": "active", "tradable": True, "fractionable": True,
                                "exchange": "SYNTH"},
                     "ref": False, "renames": [], "masked": masks.get(aid)}
        spells.append((asset["ticker"], asset["start"], asset["end"], "fja"))
    today = sorted(a["ticker"] for i, a in enumerate(assets)
                   if a["start"] <= through and (a["end"] is None or through < a["end"]) and aid_of[i] not in masks)
    store.write_universe(
        root, assets=book, salt=TEST_SALT, spells=spells,
        source={"repo": "synthetic", "commit": "0" * 40, "path": "synthetic", "sha256": None, "rows": len(spells),
                "known_through": through, "fetched_at": through,
                "wiki": {"revid": 0, "changes_applied": 0, "known_through": through, "verdict": "ok"}},
        tradable={"as_of": through, "stock": today}, audit={"source": "synthetic", "passed": True},
        wiki_reach=panel_days[0])
    calendar = dict(nyse_sessions(panel_days[0], panel_days[-1]))
    store.write_panel(
        root, days=panel_days, early=[calendar[d] for d in panel_days], aids=[*store.REF_AIDS, *aid_of.values()],
        raw=raw, adj=adj, member=member, tradable=tradable, hs=hs, fetched_through=through,
        vintage={aid: through for aid in (*store.REF_AIDS, *aid_of.values())}, audit={"source": "synthetic"},
        masked=[False] * ref + [aid_of[i] in masks for i in range(len(assets))], full_at=through, hs_share=1.0,
        live_from=live_from)
    return root


def planted_panel(root: str | Path, *, edge_year: float = 0.08, signal: str = "reversal", **kwargs: Any) -> Path:
    """A `synthetic_panel` with a KNOWN residual edge: names ranked by `signal` ("reversal" | "momentum" | "low_vol")
    earn `edge_year` a year more than their cell-mates. `kwargs`: `synthetic_panel`'s.

    Every `PLANT_SESSIONS` sessions the names built on one fund are ranked on the trailing signal (reversal: minus
    the last `PLANT_SESSIONS` sessions' return; momentum: the 12-1 return; low_vol: minus the last 60 sessions'
    volatility), and the top third earn `edge_year` / 252 more log-return on each of the next sessions' intraday
    legs: a rule that buys them at the open keeps it, and their fund-mates do not have it."""
    if signal not in SIGNALS:
        raise ValueError(f"a planted signal is one of {', '.join(SIGNALS)}")
    return synthetic_panel(root, _planted=(float(edge_year), signal), **kwargs)


def cent_panel(root: str | Path, *, n_assets: int = 50, **kwargs: Any) -> Path:
    """A `synthetic_panel` whose RAW prices sit exactly on the cent grid, with dividends: the panel the seal's
    adversary searches for a price level (`test_xs_seal.TheLevelCannotBeSearched`). Every fourth asset pays a
    dividend each quarter of the panel's last three years (unless `dividends` is handed in)."""
    kwargs.setdefault("raw_places", 2)
    if "dividends" not in kwargs:
        end = as_date(kwargs.get("as_of") or kwargs.get("end") or dt.date(2026, 10, 9))
        start = as_date(kwargs.get("start") or dt.date(2016, 1, 4))
        days = [d for d, _ in nyse_sessions(max(start, end - dt.timedelta(days=3 * 366)), end)]
        payers = {}
        for i in range(0, n_assets, 4):
            payers[store.FIRST_MEMBER_AID + i] = [(d, 0.25 + 0.05 * (i % 5)) for d in days[20 + i % 30::63]]
        kwargs["dividends"] = payers
    return synthetic_panel(root, n_assets=n_assets, **kwargs)


def _stamp(day: dt.date) -> str:
    """The venue's stamp of a 1Day bar: the session's New York midnight, in UTC."""
    return dt.datetime.combine(day, dt.time(0), config.NEW_YORK).astimezone(dt.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def bar_rows(days: np.ndarray, raw: np.ndarray, adj: np.ndarray, *, adjustment: str) -> list[dict[str, Any]]:
    """The venue's 1Day rows ({t, o, h, l, c, v}) a fetch of ONE column holds: `days` int32 ordinals, `raw` (n, 5) and
    `adj` (n, 4) its bars, for adjustment "raw" or "all" (the all rows' v is the raw volume, as the venue's); a
    session with no bar has no row."""
    if adjustment not in ("raw", "all"):
        raise ValueError("adjustment is raw or all")
    out = []
    for i in range(int(days.shape[0])):
        if not np.isfinite(raw[i, 3]):
            continue
        prices = raw[i, :4] if adjustment == "raw" else adj[i, :4]
        out.append({"t": _stamp(from_ordinal(int(days[i]))), "o": float(prices[0]), "h": float(prices[1]),
                    "l": float(prices[2]), "c": float(prices[3]), "v": float(raw[i, 4])})
    return out


def same_ctx_cases(root: str | Path, *, history: int, count: int = 20, seed: int = 0, window: str = "validation",
                   gate: Any = None) -> list[dict[str, Any]]:
    """THE I6 HELPER: `count` random decision days of `window`, each {day, index, gym (the Gym's `ctx.Inputs`),
    raw_rows, all_rows (the venue-shaped 1Day rows a live fetch of that day would return), columns (symbols), common
    (the keywords `ctx.inputs_from_fetch` needs: elig0, ids, dither_key, sector_perm, needs, the book facts)}, so that
    `ctx_bytes(build(case["gym"]))` equals `ctx_bytes(build(inputs_from_fetch(case["raw_rows"], case["all_rows"],
    day=case["day"], columns=case["columns"], **case["common"])))`. BOTH SIDES OF A CASE ARE BUILT UNDER ONE RUN KEY
    AND ONE AID SET (the live side's columns are REF, that day's members and two held names that have left the index),
    and at least one case straddles an index change.

    Each case also carries `aids` (the columns' aids, the parent's), `run_key`, `slice` (the Gym's `store.Slice`) and
    `straddles` (whether the index changed within two sessions of the day). The Gym's slice runs from the day through
    the two sessions after it, so its `elig0` row reads the membership ahead as a live decision's does. THE BOOK of
    every case: lots 1 and 2 are the two held names that left the index (they keep a column, an id and a mark, and
    `ctx.ineligible` names them), lot 3 a name of U(t); one closed lot; one reject."""
    panel = store.PanelStore(root, gate=gate)
    universe = panel.universe()
    sessions = panel.sessions(window)
    if not sessions:
        raise ValueError(f"the panel holds no session of {window}")
    needs = Needs(PANELS[0], int(history), 12, "weekly", 0, config.MAX_HOLD_CAP)

    def members(day: dt.date) -> set[int]:
        return {aid for aid, _ in universe.members(day)}

    changed = [i for i in range(1, len(sessions) - 2) if members(sessions[i + 1]) != members(sessions[i])]
    rng = random.Random(f"xs-i6|{int(seed)}")
    picks = set(rng.sample(range(len(sessions)), min(int(count), len(sessions))))
    if changed and not picks & set(changed):
        picks.discard(max(picks))
        picks.add(rng.choice(changed))
    cases = []
    for index in sorted(picks):
        day = sessions[index]
        inside = sorted(members(day))
        held = universe.left(day)[-2:]
        run_key = f"i6|{day.isoformat()}"
        ahead = [d for d in sessions[index + 1:index + 1 + config.MEMBER_AHEAD] if (d - day).days <= 7]
        last = ahead[-1] if ahead else day
        if window == "train":
            piece = panel.train(day, last, history=int(history), run_key=run_key, aids=[*inside, *held])
        else:
            piece = panel.bars(window, history=int(history), run_key=run_key, start=day, end=last,
                               aids=[*inside, *held])
        bars, t = piece.bars, piece.bars.first
        column = {int(aid): i for i, aid in enumerate(piece.aids.tolist())}
        # the book: lots 1 and 2 are the held names that left the index (outside U: the House's exits), lot 3 a name
        # of U(t) (the lowest aid that is eligible that day; with none, the day's first member)
        blank = inputs_from_panel(bars, t, needs=needs, cash=0.0, equity=0.0, budget=0.0, params={})
        eligible = np.asarray(derive(blank).elig, dtype=bool)
        chosen = next((aid for aid in inside if eligible[column[aid]]), inside[0] if inside else None)
        lots = [*zip((1, 2), held), *([(3, chosen)] if chosen is not None else [])]
        positions = []
        for lid, aid in lots:
            col = column[aid]
            mark = float(bars.raw[t, col, 3])
            qty = 1.5 * lid
            positions.append({"lid": lid, "col": col, "qty": qty, "value": round(qty * mark, 4),
                              "entry_value": round(qty * mark * 0.97, 4), "held_sessions": 2 + lid, "at": "open",
                              "tag": "i6"})
        closed = [{"lid": 9, "col": column[inside[-1]], "net_ret": 0.0123, "held_sessions": 5, "reason": "program",
                   "tag": "i6"}] if inside else []
        book = {"positions": positions, "closed": closed, "rejects": ["order cap"], "cash": 412.5, "equity": 1000.0,
                "budget": 1000.0, "params": {"theta": 0.02}}
        lo = max(0, t + 1 - config.DERIVE_SESSIONS)
        symbols = [universe.symbol(int(aid), day) for aid in piece.aids.tolist()]
        rows = {"raw": {}, "all": {}}
        for col, symbol in enumerate(symbols):
            for adjustment in rows:
                rows[adjustment][symbol] = bar_rows(bars.days[lo:t + 1], bars.raw[lo:t + 1, col],
                                                    bars.adj[lo:t + 1, col], adjustment=adjustment)
        common = {"elig0": np.array(bars.elig0[t]), "ids": np.array(bars.ids), "dither_key": bars.dither_key,
                  "sector_perm": np.array(bars.sector_perm), "needs": needs, **book}
        cases.append({"day": day, "index": index, "gym": inputs_from_panel(bars, t, needs=needs, **book),
                      "raw_rows": rows["raw"], "all_rows": rows["all"], "columns": symbols, "common": common,
                      "aids": np.array(piece.aids), "run_key": run_key, "slice": piece,
                      "straddles": index in changed or index - 1 in changed or index + 1 in changed})
    return cases


__all__ = ["TEST_SALT", "SECTOR_SHARES", "PAIR", "PLANT_SESSIONS", "SIGNALS", "IDIO_SHARE", "synthetic_panel",
           "planted_panel", "cent_panel", "bar_rows", "same_ctx_cases"]
