"""Deep replay: development folds walked forward over the history store, and a sealed holdout.

The live replay judges a strategy on the last 21 days (126 for a daily one) read from the API.
`league.history` now keeps a decade. This module turns it into evaluation without turning it into
training data:

**Tapes from the store.** `StoreClient` answers the same bar requests `tapes.AlpacaData` makes, from
the store instead of the venue, so a deep tape is built by the SAME code as a live one (bars
stamped with their close, a daily bar available only after its New York day, warmup before the
window). Nothing is re-implemented, so nothing can drift. Prices are one consistent space:
`all`-adjusted as of the fetch for the signal bars, and the raw 5-minute execution bars scaled by
that day's factor `F = all/raw` into the same space, so a limit price computed from a signal bar
means the same thing to the fill. (Price LEVELS before a split are therefore the adjusted ones; a
rule on an absolute price, a $1 floor, sees them. Labelled on every tape.)

**Chronology.** A development fold's client refuses any bar after the fold's end and any bar in
the holdout, and `AlpacaData`'s clock is the fold's end, so a fold never sees its future.
`folds()` lays them end to end, oldest first, all before the holdout.

**The holdout** is a FIXED window, not a rolling one: a rolling holdout becomes tomorrow's
development data. `HOLDOUT` is the six months that end where the oldest tape ever shown to an
agent begins. Replays began Sept 19, 2026, and a daily-horizon tape reaches back 126 days (to
May 16, 2026); the hourly ones 21. So `[2025-11-14, 2026-05-15)` has never been on a tape, and the
four months after it (studied, and still watched on paper) are not used by this module at all.

Holdout rules (`HoldoutSeal`):
- sealed bars are served only through `HoldoutSeal.evaluate`, never to a development fold, a
  researcher, or `replay_coverage`;
- every access is a `holdout.access` ledger row, written BEFORE the run, so a crash still counts;
- one evaluation per strategy version (code + parameters), and `budget` per lineage, so adaptive
  re-testing cannot fit the holdout;
- the caller gets pass or fail and coarse buckets only (return to the nearest percent, a trade
  count band); the full numbers stay in the ledger row, which is private.

Development replay, the sealed holdout, forward paper and live execution stay separate: this
module writes only `holdout.access`; development folds go through the existing trial path, and
paper and live are the books'.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from .history import NEW_YORK, HistoryStore, _day, _ts
from .tapes import AlpacaData, TapeError, is_crypto, iso, parse_time

#: The sealed window, [start, end). Fixed on purpose; see the module docstring.
HOLDOUT = ("2025-11-14", "2026-05-15")
#: Holdout evaluations one lineage may spend, over its whole life.
LINEAGE_BUDGET = 2
#: A development fold is as long as today's daily tape, so a box receives no larger a tape.
FOLD_DAYS = {"day": 126, "hour": 21}
#: The development window a deep replay walks: the folds just before the holdout, oldest first,
#: as one chronological tape, so the replay's own out-of-sample third is its latest months.
DEV_DAYS = {"day": 252, "hour": 63}
#: The stressed variant of every sealed evaluation: twice the spread (goal section 4).
STRESS = 2.0
ADJUSTMENT_LABEL = "all-adjusted as of the fetch; 5-minute execution bars scaled by the day's all/raw factor"


class SealedData(TapeError):
    """A request reached into data this client may not serve."""


# ------------------------------------------------------------------- folds

def folds(start: "str | date", holdout_start: "str | date" = HOLDOUT[0], *, horizon: str = "day",
          count: "int | None" = None) -> list[tuple[str, str]]:
    """Development folds [start, end), end to end, oldest first, all ending by the holdout.
    The newest `count` when given: the recent past is the better guide to the next test."""
    days = FOLD_DAYS.get(horizon, 126)
    lo, hi = _day(start), _day(holdout_start)
    out = []
    end = hi
    while (end - lo).days >= days:
        out.append((str(end - timedelta(days=days)), str(end)))
        end -= timedelta(days=days)
    out.reverse()
    return out[-count:] if count else out


# ------------------------------------------------------------ store client

class StoreClient:
    """`client.request("GET", url)` for `AlpacaData`, answered from the history store.

    `until` is a fold's end: nothing after it is served (it is also `AlpacaData`'s clock, so no
    request asks past it). `sealed` is a window it must never serve: a request that touches it is
    refused, not clipped, because a clipped answer would read as history that simply ended."""

    def __init__(self, store: HistoryStore, *, feed: str = "sip", until: "float | None" = None,
                 sealed: "tuple[str, str] | None" = HOLDOUT):
        self.store, self.feed, self.until = store, feed, until
        self.sealed = (_ts(_day(sealed[0])), _ts(_day(sealed[1]))) if sealed else None
        self.calls: list[str] = []

    def request(self, method: str, url: str, *, headers: Any = None, body: Any = None, what: str = "venue") -> tuple[int, Any]:
        self.calls.append(url)
        parsed = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if not parsed.path.endswith("/bars"):
            return 404, {"message": "the history store serves bars only"}
        start, end = parse_time(q["start"]), parse_time(q["end"])
        if self.until is not None and end > self.until:
            end = self.until  # AlpacaData asks up to its clock; the clock IS `until`
        if self.sealed and start < self.sealed[1] and end >= self.sealed[0]:
            raise SealedData(f"the range {iso(start)}..{iso(end)} reaches into the sealed holdout")
        timeframe = q["timeframe"]
        out: dict[str, list[dict[str, Any]]] = {}
        for symbol in q["symbols"].split(","):
            crypto = is_crypto(symbol)
            feed = "us" if crypto else self.feed
            if crypto:
                rows = self.store.bars(symbol, timeframe, start, end + 1, feed=feed, adjustment="raw")
            elif timeframe in ("1Day", "1Hour"):
                rows = self.store.bars(symbol, timeframe, start, end + 1, feed=feed, adjustment="all")
            else:
                rows = self._scaled(symbol, timeframe, start, end, feed)
            if rows:
                out[symbol] = [{"t": iso(r["t"]), "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]} for r in rows]
        return 200, {"bars": out, "next_page_token": None}

    def _scaled(self, symbol: str, timeframe: str, start: float, end: float, feed: str) -> list[dict[str, Any]]:
        """Raw intraday bars in the adjusted space: each scaled by its New York day's all/raw."""
        raw = self.store.bars(symbol, timeframe, start, end + 1, feed=feed, adjustment="raw")
        factors = day_factors(self.store, symbol, start, end, feed=feed)
        out = []
        for row in raw:
            factor = factors.get(_ny_day(row["t"]))
            if factor is None:
                continue  # no daily pair for this day: the factor is unknown, so the bar is not served
            out.append({**row, "o": row["o"] * factor, "h": row["h"] * factor, "l": row["l"] * factor, "c": row["c"] * factor})
        return out


def day_factors(store: HistoryStore, symbol: str, start: float, end: float, *, feed: str) -> dict[str, float]:
    """New York day -> all/raw of that day's daily close: what turns a raw price into the
    adjusted space the signal bars are in."""
    days = {r["t"]: r["c"] for r in store.bars(symbol, "1Day", start - 5 * 86400, end + 86400, feed=feed, adjustment="raw")}
    adjusted = {r["t"]: r["c"] for r in store.bars(symbol, "1Day", start - 5 * 86400, end + 86400, feed=feed, adjustment="all")}
    return {_ny_day(t): adjusted[t] / c for t, c in days.items() if t in adjusted and c > 0}


def _ny_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, NEW_YORK).strftime("%Y-%m-%d")


def coverage_gaps(store: HistoryStore, symbols: Sequence[str], timeframe: str, signal_start: str, start: str, end: str, *,
                  feed: str = "sip") -> list[str]:
    """Why a deep tape cannot be built honestly: each series the store has not fetched. The signal
    bars are needed from `signal_start` (the warmup); the execution bars, and the daily pairs that
    scale them, only over [start, end). Empty means every input was fetched (some may be
    unavailable: a symbol that listed later simply has no bars before it)."""
    problems = []
    execution = "5Min" if timeframe == "1Day" else timeframe
    for symbol in symbols:
        crypto = is_crypto(symbol)
        wanted = [(timeframe, "raw" if crypto else "all", signal_start)]
        if execution != timeframe:
            wanted.append((execution, "raw", start))
        if not crypto and execution not in ("1Day", "1Hour"):
            wanted += [("1Day", "raw", start), ("1Day", "all", start)]
        for frame, adjustment, first in dict.fromkeys(wanted):
            cover = store.coverage(symbol, frame, first, end, feed="us" if crypto else feed, adjustment=adjustment)
            if cover["status"] == "unfetched":
                problems.append(f"{symbol} {frame} {adjustment}: unfetched {cover['unfetched'][:2]}")
    return problems


def fold_tape(store: HistoryStore, needs: Mapping[str, Any], start: str, end: str, *, feed: str = "sip",
              sealed: "tuple[str, str] | None" = HOLDOUT) -> dict[str, Any]:
    """One tape over [start, end) for a strategy's NEEDS, built by `AlpacaData.tape` from the store.
    Raises `TapeError` naming the unfetched inputs rather than build a tape with holes."""
    symbols = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
    timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
    warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
    horizon = str(needs.get("horizon") or "hour")
    lookback = AlpacaData.default_lookback(timeframe, warmup, crypto=False)
    signal_start = str(datetime.fromtimestamp(_ts(_day(start)) - lookback, timezone.utc).date())
    gaps = coverage_gaps(store, symbols, timeframe, signal_start, start, end, feed=feed)
    if gaps:
        raise TapeError("unsupported input: history not yet fetched -- " + "; ".join(gaps[:6]))
    until = _ts(_day(end)) - 1
    data = AlpacaData(StoreClient(store, feed=feed, until=until, sealed=sealed), feed=feed, clock=lambda: until)
    tape = data.tape(symbols, timeframe, start=iso(_ts(_day(start))), end=iso(until), horizon=horizon, warmup_bars=warmup)
    tape["source"] = {"store": "history", "window": [start, end], "adjustment": ADJUSTMENT_LABEL,
                      "survivorship": "today's niche symbols; delisted names absent"}
    return tape


def attach_quotes(store: HistoryStore, tape: dict[str, Any], *, feed: str = "sip") -> dict[str, int]:
    """Put each stored quote probe on the step whose time is its bar close, in the tape's price
    space (an equity's raw quote times its day's all/raw factor). `age` is how old the quote was
    at the moment asked about (close + latency). Steps with no probe keep the assumed spread."""
    steps = tape.get("steps") or []
    if not steps:
        return {"steps": 0, "quoted": 0}
    first, last = parse_time(steps[0]["t"]), parse_time(steps[-1]["t"])
    index = {parse_time(step["t"]): step for step in steps}
    quoted = 0
    for symbol in tape.get("symbols") or []:
        crypto = is_crypto(symbol)
        rows = store.probes(symbol, first, last + 1, feed="us" if crypto else feed)
        if not rows:
            continue
        factors = {} if crypto else day_factors(store, symbol, first, last, feed=feed)
        for row in rows:
            step = index.get(float(row["t"]))
            if step is None or row["quote_ns"] is None or row["bp"] is None or row["ap"] is None:
                continue
            factor = 1.0 if crypto else factors.get(_ny_day(row["t"]))
            if factor is None:
                continue
            step.setdefault("quotes", {})[symbol] = {"bid": row["bp"] * factor, "ask": row["ap"] * factor,
                                                     "age": round(float(row["at"]) - row["quote_ns"] / 1e9, 6)}
            quoted += 1
    tape["quote_source"] = {"quoted_touches": quoted, "rule": "NBBO prevailing at the step's close plus latency, from league.history probes"}
    return {"steps": len(steps), "quoted": quoted}


def _symbols_of(needs: Mapping[str, Any]) -> list[str]:
    """The tape's symbols as `House.tape_for` picks them: its own and what it watches."""
    watched = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
    own = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
    return sorted(set(own) | {str(s) for s in (watched.get("symbols") or [])[:6]})


def dev_window(horizon: str, *, days: "int | None" = None, holdout: tuple[str, str] = HOLDOUT) -> tuple[str, str]:
    """The development window: `DEV_DAYS` of history ending where the holdout begins."""
    end = _day(holdout[0])
    return str(end - timedelta(days=int(days or DEV_DAYS.get(horizon, 252)))), str(end)


def dev_tape(store: HistoryStore, needs: Mapping[str, Any], *, feed: str = "sip", days: "int | None" = None,
             holdout: tuple[str, str] = HOLDOUT) -> tuple[str, dict[str, Any]]:
    """(tape id, tape): the development window's tape, quotes attached where they were fetched."""
    horizon = str(needs.get("horizon") or "hour")
    start, end = dev_window(horizon, days=days, holdout=holdout)
    wanted = {**dict(needs), "symbols": _symbols_of(needs)}
    tape = fold_tape(store, wanted, start, end, feed=feed, sealed=holdout)
    attach_quotes(store, tape, feed=feed)
    timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
    key = f"deep:alpaca:{','.join(wanted['symbols'])}:{timeframe}:{horizon}:{start}:{end}:{feed}"
    return key, tape


def holdout_tape(store: HistoryStore, needs: Mapping[str, Any], *, feed: str = "sip", stress: float = 1.0,
                 holdout: tuple[str, str] = HOLDOUT) -> dict[str, Any]:
    """The sealed window's tape. Only `HoldoutSeal.evaluate`'s runner may call this."""
    wanted = {**dict(needs), "symbols": _symbols_of(needs)}
    tape = fold_tape(store, wanted, holdout[0], holdout[1], feed=feed, sealed=None)
    attach_quotes(store, tape, feed=feed)
    if stress != 1.0:
        tape["spread_stress"] = float(stress)
    return tape


# ------------------------------------------------------------------ holdout

def version_of(code: str, params: Mapping[str, Any]) -> str:
    """A strategy version: its code and its parameters. A new version is a new evaluation."""
    text = code + "\n" + json.dumps(dict(params or {}), sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


#: What the private ledger row keeps of each sealed run (never shown to a researcher).
DETAIL_KEYS = ("ok", "error", "return_pct", "trades", "max_drawdown", "steps", "fees_usd", "final_equity", "out_of_sample", "execution")


def _number(value: Any) -> "float | None":
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _band(trades: int) -> str:
    return "0" if trades <= 0 else "1-9" if trades < 10 else "10-49" if trades < 50 else "50+"


class HoldoutSeal:
    """The only door to the sealed window. See the module docstring for the rules."""

    def __init__(self, ledger: Any, *, budget: int = LINEAGE_BUDGET, window: tuple[str, str] = HOLDOUT,
                 clock: Callable[[], float] | None = None):
        self.ledger, self.budget, self.window = ledger, int(budget), window
        self.clock = clock

    def _rows(self) -> list[Any]:
        return list(self.ledger.iter(kinds="holdout.access"))

    def used(self, lineage: str) -> int:
        return sum(1 for e in self._rows() if e.payload.get("lineage") == lineage and e.payload.get("state") == "opened")

    def prior(self, version: str) -> "dict[str, Any] | None":
        """This version's evaluated row, else any access it already spent, else None."""
        found = None
        for entry in self._rows():
            if entry.payload.get("version") != version:
                continue
            if entry.payload.get("state") == "evaluated":
                return entry.payload
            found = entry.payload
        return found

    def evaluate(self, *, agent: str, lineage: str, code: str, params: Mapping[str, Any],
                 run: Callable[[tuple[str, str]], Mapping[str, Any]], passed: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
        """Run `run(window)` once for this version, if the lineage has budget; return coarse numbers.

        `run` gets the sealed window and returns the replay result; `passed` is the existing gate
        applied to it. Neither the tape nor the result's detail is returned."""
        version = version_of(code, params)
        earlier = self.prior(version)
        if earlier is not None:
            return {"evaluated": False, "refused": "this version has had its holdout evaluation",
                    "passed": earlier.get("coarse", {}).get("passed")}
        if self.used(lineage) >= self.budget:
            return {"evaluated": False, "refused": f"the lineage has spent its {self.budget} holdout evaluations"}
        self.ledger.append("holdout.access", {"agent": agent, "lineage": lineage, "version": version, "state": "opened",
                                              "window": list(self.window)}, agent=agent, id=f"holdout:{version}:opened")
        try:
            result = dict(run(self.window))
        except Exception as exc:  # noqa: BLE001 - the access is spent either way; the reason is kept
            self.ledger.append("holdout.access", {"agent": agent, "lineage": lineage, "version": version, "state": "failed",
                                                  "error": f"{type(exc).__name__}: {str(exc)[:200]}"}, agent=agent,
                               id=f"holdout:{version}:failed")
            return {"evaluated": False, "refused": "the holdout replay could not be run; the access is spent"}
        ok = bool(passed(result))
        base = result.get("base") if isinstance(result.get("base"), Mapping) else result
        pct = _number(base.get("return_pct"))
        coarse = {"passed": ok, "return_pct": None if pct is None else round(pct),
                  "trades": _band(int(base.get("trades") or 0))}
        detail = {name: {k: run_result.get(k) for k in DETAIL_KEYS if k in run_result}
                  for name, run_result in (result.items() if "base" in result else [("base", result)]) if isinstance(run_result, Mapping)}
        self.ledger.append("holdout.access", {"agent": agent, "lineage": lineage, "version": version, "state": "evaluated",
                                              "window": list(self.window), "coarse": coarse, "_detail": detail},
                           agent=agent, id=f"holdout:{version}:evaluated")
        return {"evaluated": True, **coarse}
