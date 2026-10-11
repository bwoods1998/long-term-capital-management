"""STEP -1 of release E4 ("breadth"): the coverage probe. Does Alpaca serve the daily bars of the S&P 500's past members?

    python3 scripts/panel_probe.py --spells sp500_ticker_start_end.csv [--root /workspace/state]
                                   [--release /workspace/current] [--env /workspace/.env] [--list] [--no-write]
                                   [--names T1,T2]

On the House: the box's own Python, the spell file placed beside it, and `--release` the running release (the default
when this file is copied there alone). It writes one file, its receipt, under `--root`. The gateway's token is the
House's own: where this process's environment has none, the release's loader reads it from the House's environment
file, `--env` (default: `.env` beside the release, /workspace/.env on the House, WHEREVER `--root` points). With no
token the probe says so at once and sends nothing.

Owner: package A of release E4 (written at Step 0, because the captain runs it on the House while the packages are
built; `league/tests/test_panel_probe.py` runs it against a recording fake gateway).

WHY. The whole release rests on one unverified fact: that the venue serves the bars of ENDED index spells when asked
with `asof` (a delisted member's history, and a reused ticker resolved to the spell's own company). A free source
measured earlier had 27% of 2016's members missing. Below 97% of member-days with a bar in any Train-era year the
panel lane is not built on free data, and the owner is asked the paid-data question with this probe's numbers.

WHAT IT DOES, AND ALL IT DOES. It is READ-ONLY and its only request is `GET /v1/alpaca/v2/stocks/bars` through the
House's own gateway client (`league.ops.context.Gateway`: the running release's, token and all; this script never
reads, prints or returns a secret). It reads the membership spell file from a LOCAL path (`--spells`: the public
fja05680/sp500 file `sp500_ticker_start_end.csv`, columns ticker,start_date,end_date, which the captain places on the
House; the web reader is not used, by the captain's ruling that the probe GETs bars and nothing else). Then:

1. THE CALENDAR: SPY's raw 1Day bars of the two eras (`ERAS`: 2016-01-04..2019-12-31 and 2022-01-03..2024-12-31). A
   session is a day SPY has a bar.
2. EVERY SPELL WITH A MEMBER SESSION IN THE ERAS (member on d: start <= d, and d < end or no end): its raw 1Day bars
   inside the eras. Open spells go together, `BATCH` symbols a request, with the venue's own `asof` (today: the
   parameter is left out, so no request names today's year). Each ended spell goes alone, one request an era it has
   sessions in, with `asof` = its last member session of the eras: a day INSIDE the spell, so a reused ticker resolves
   to the spell's own company.
3. THE COUNT (E4-SPEC D19). A valid bar is a row with close > 0 and volume > 0. A spell's series is ACCEPTED when its
   valid bars cover at least 95% of its member sessions in the eras and its first valid bar is within 5 sessions of
   its first member session there; else it is "no_bars". A series whose median dollar volume is under $5,000,000 is
   "reused" whatever its coverage (no index member trades so little: the ticker resolved to another company).
   coverage[year] = the member-sessions of that year with a valid bar of an accepted spell / its member-sessions.
4. THE FACTS of E4-SPEC section 19 a bars request can reach.
   FACT 1 (asof resolves an ended spell's ticker to the spell's own company). THE TEST NAMES are, unless `--names`
   gives others, read off the spell file itself: every ticker with an ended spell that has a member session in the
   eras AND a later spell of the same ticker (the ticker was used again: exactly where asof matters). Each ended
   spell of a test name is fetched a second time WITHOUT asof. Two things are then reported APART, because they are
   two questions: `asof_differs`, the test spells that answered differently without asof (the venue honours asof and
   it changes the answer), with `differs_accepted`, how many of those were served as an index member's series; and
   `test_accepted` of `test_spells`, whether the venue has the bars at all. The verdict: "holds" when at least one
   test spell differs and every one that differs is accepted; "fails" when one that differs is not accepted;
   "not_shown" when none differs (nothing here shows asof at work); "not_met" with no test spell.
   FACT 9 (this box's memory and cores, read locally). FACT 10 (how many symbols one bars request takes: a ladder of
   counts over one session, each step tried twice unless the venue refuses it; `reading` says whether the limit was
   FOUND, between the largest count answered and the first refused, or is only KNOWN TO BE AT LEAST the ladder's
   last count). Facts 2, 3 and 4 need the web reader, quotes and assets: they are stated "not probed" and package
   A's jobs verify them.

A REQUEST THAT FAILS AND A REQUEST THAT IS REFUSED ARE TWO THINGS. A failure (a timeout, a 5xx, a 429) is asked again,
up to `TRIES` times with a wait, and a spell whose request still fails is in "error": the verdict may be "incomplete",
and a rerun may cure it. A REFUSAL (HTTP 4xx but 429: the venue or the gateway will not serve that request, now or
later) is never asked again: an ended spell it concerns has no bars from it (a "no_bars" reason, counted in
`requests_refused`), and a refused batch of open spells is asked again one ticker at a time. No rerun is suggested
for what no rerun can change.

NO SEALED YEAR. No request names a day of 2020, 2021, 2025 or 2026: every `start`, `end` and `asof` lies in the seven
probe years, checked before the request is sent (`SealedRequest`: it is not sent). A row the venue returns outside the
calendar is dropped unread.

WHAT COMES OUT: COUNTS AND COVERAGE SHARES, NEVER A PRICE, and no ticker either. The receipt, printed and written to
`<root>/equity-daily/probe.json` (600, atomic): {"version", "at", "by_year": {year: {"member_days", "with_bar",
"share"}}, "sessions": {year: n}, "spells", "open", "ended", "no_bars", "reused", "errors", "requests",
"requests_failed", "requests_refused", "coverage_min", "pass", "verdict", "facts"}. PASS: every probe year at or above
0.97. Verdict "pass" | "fail" | "incomplete" (a request still failed after its tries and a year is under the bar: run
it again).
`--list` prints, on the terminal only and never into the receipt, the tickers of the spells with no bars, reused or
in error (no date and no price beside them).

EXIT CODES: 0 pass; 1 fail; 2 incomplete, and ONLY that (run it again); 3 the probe COULD NOT RUN (the spell file
cannot be read, there is no gateway client or no token, SPY gave no calendar, the request cap was reached, a request
would have named a sealed year): running the same command again changes nothing, so a caller that reruns on 2 never
loops on it.

Standard library only (the House runs Python 3.11), and nothing of league/xs: it must run before any of E4 exists.
About 450 requests, 10 minutes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

VERSION = "xs-probe-1"
BARS = "/v1/alpaca/v2/stocks/bars"
#: The two eras the probe reads: the panel store's Train-era years (2016 is its history-only year).
ERAS: tuple[tuple[dt.date, dt.date], ...] = ((dt.date(2016, 1, 4), dt.date(2019, 12, 31)),
                                             (dt.date(2022, 1, 3), dt.date(2024, 12, 31)))
YEARS = (2016, 2017, 2018, 2019, 2022, 2023, 2024)
#: No request names a day of these years.
SEALED_YEARS = (2020, 2021, 2025, 2026)
COVERAGE_MIN = 0.97
ACCEPT_SHARE = 0.95
ACCEPT_FIRST = 5
REUSED_USD = 5_000_000.0
#: Symbols a request of open spells (39 x 253 bars is one page: the live fetch's chunk).
BATCH = 39
PAGE_LIMIT = 10000
MAX_PAGES = 200
TRIES = 3
BACKOFF_S = (5.0, 20.0)
#: "Too many requests": the one 4xx that is a failure to ask again, never a refusal.
RATE_LIMITED = 429
CALENDAR_SYMBOL = "SPY"
#: Fact 10's ladder: how many symbols one bars request is asked for, over one session; and the tries of a step (a
#: refusal ends it at once; a passing failure must not be recorded as the limit).
LIMIT_LADDER = (39, 100, 200, 400)
LIMIT_TRIES = 2
#: A safety stop: the probe never sends more requests than this.
MAX_REQUESTS = 3000
STORE_DIR = "equity-daily"
RECEIPT = "probe.json"
#: The House's running release, and the command's wait before every request (seconds).
HOUSE_RELEASE = "/workspace/current"
PAUSE_S = 0.15
#: The House's environment file, beside the release (never read by this script: the release's own loader does).
ENV_FILE = ".env"
EXIT_PASS, EXIT_FAIL, EXIT_INCOMPLETE, EXIT_CANNOT_RUN = 0, 1, 2, 3
DATE_PARAMS = ("start", "end", "asof")
NOT_PROBED = "not probed: this script only GETs bars (package A's jobs verify it)"


class SealedRequest(ValueError):
    """A request would name a day outside the probe's years: it is never sent."""


class ProbeStopped(RuntimeError):
    """The probe cannot go on (no calendar, the request cap)."""


class NoGateway(RuntimeError):
    """The probe has no gateway client it could use (no release, no token). Its text is this script's own words:
    a variable's name and a path, never a value."""


class Refused(Exception):
    """A bars request the venue or the gateway REFUSED for good (HTTP 4xx but 429): never asked again. `status`."""

    def __init__(self, status: int):
        super().__init__(f"refused (HTTP {int(status)})")
        self.status = int(status)


def refusal(exc: BaseException) -> int | None:
    """The HTTP status of a permanent refusal (the gateway client's `GatewayError.status`: 4xx but 429), else None."""
    status = getattr(exc, "status", None)
    if isinstance(status, bool) or not isinstance(status, int):
        return None
    return status if 400 <= status < 500 and status != RATE_LIMITED else None


@dataclass(frozen=True)
class Spell:
    """One index spell of one ticker: a member on d when start <= d and (end is None or d < end)."""

    ticker: str
    start: dt.date
    end: dt.date | None


# ----------------------------------------------------------------------------------------------------- the spell file
def parse_spells(text: str) -> list[Spell]:
    """The rows of the spell file (ticker,start_date,end_date; a header line; an empty end: still a member). ValueError
    on a row that is not one (its number is named, never its content)."""
    out: list[Spell] = []
    for number, line in enumerate(str(text).splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split(",")]
        if number == 1 and cells and cells[0].lower() in ("ticker", "symbol"):
            continue
        if len(cells) < 2 or len(cells) > 3 or not cells[0]:
            raise ValueError(f"row {number} of the spell file is not ticker,start_date,end_date")
        try:
            start = dt.date.fromisoformat(cells[1][:10])
            end = dt.date.fromisoformat(cells[2][:10]) if len(cells) == 3 and cells[2] else None
        except ValueError:
            raise ValueError(f"row {number} of the spell file has a date that is not one") from None
        if end is not None and end <= start:
            raise ValueError(f"row {number} of the spell file ends before it starts")
        out.append(Spell(cells[0].upper(), start, end))
    if not out:
        raise ValueError("the spell file holds no spell")
    return out


def member_sessions(spell: Spell, sessions: Sequence[dt.date]) -> list[dt.date]:
    """The sessions the spell is a member on (D3: the end day itself is no member day)."""
    return [d for d in sessions if spell.start <= d and (spell.end is None or d < spell.end)]


def test_names(spells: Sequence[Spell], sessions: Sequence[dt.date]) -> list[str]:
    """FACT 1's test names, read off the spell file: every ticker with an ENDED spell that has a member session in
    the eras and a LATER spell of the same ticker (one that starts at or after that spell's end). Sorted. A ticker
    used once is no test: with or without asof the venue has one company to serve."""
    by_ticker: dict[str, list[Spell]] = {}
    for spell in spells:
        by_ticker.setdefault(spell.ticker, []).append(spell)
    out = []
    for ticker, mine in by_ticker.items():
        if any(spell.end is not None and member_sessions(spell, sessions)
               and any(other.start >= spell.end for other in mine if other is not spell) for spell in mine):
            out.append(ticker)
    return sorted(out)


# --------------------------------------------------------------------------------------------------------- the gateway
def guard(params: Mapping[str, Any]) -> None:
    """THE SEAL: every date a request names lies in `YEARS`, else `SealedRequest` (the request is not sent)."""
    for key in DATE_PARAMS:
        value = params.get(key)
        if value is None:
            continue
        try:
            year = dt.date.fromisoformat(str(value)[:10]).year
        except ValueError:
            raise SealedRequest(f"the request's {key} is not a day") from None
        if year not in YEARS:
            raise SealedRequest(f"the request's {key} names {year}: the probe reads {YEARS[0]}-{YEARS[3]} and "
                                f"{YEARS[4]}-{YEARS[-1]} only")


def bar_day(stamp: Any) -> dt.date | None:
    """The session day of a daily bar's `t` (stamped at New York midnight, whose UTC date is the same day), or None."""
    text = str(stamp or "")
    try:
        if len(text) == 10:
            return dt.date.fromisoformat(text)
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.timezone.utc).date()
    except ValueError:
        return None


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


class Probe:
    """The probe's one way out: bars GETs through `gateway` (an object with `get(path, params)`), each guarded, tried
    up to `TRIES` times, counted. `sleep` waits between tries (the tests pass a no-op)."""

    def __init__(self, gateway: Any, *, sleep: Callable[[float], None] = time.sleep, max_requests: int = MAX_REQUESTS,
                 pause: float = 0.0):
        self.gateway = gateway
        self.sleep = sleep
        self.max_requests = int(max_requests)
        #: Seconds waited before every request (the venue's and the gateway's rate limits are not this probe's to test).
        self.pause = max(0.0, float(pause))
        self.requests = 0
        self.failed = 0
        self.refused = 0

    def _get(self, params: Mapping[str, Any], *, tries: int, counted: bool = True) -> Any:
        """One guarded request. A FAILURE is asked again up to `tries` times, then RuntimeError (its kind and its
        HTTP status, never the venue's text). A REFUSAL (`refusal`: 4xx but 429) is `Refused` at once: asking again
        cannot change it, and each try would cost its wait."""
        guard(params)
        last: BaseException | None = None
        for attempt in range(max(1, tries)):
            if self.requests >= self.max_requests:
                raise ProbeStopped(f"the probe's cap of {self.max_requests} requests is reached")
            self.requests += 1
            if self.pause:
                self.sleep(self.pause)
            try:
                return self.gateway.get(BARS, dict(params))
            except Exception as exc:  # noqa: BLE001 - the gateway's own error: refused, or tried again
                status = refusal(exc)
                if status is not None:
                    if counted:
                        self.refused += 1
                    raise Refused(status) from None
                last = exc
                if attempt + 1 < max(1, tries):
                    self.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
        if counted:
            self.failed += 1
        status = getattr(last, "status", None)
        raise RuntimeError(f"a bars request failed {max(1, tries)} times: {type(last).__name__}"
                           f"{'' if not isinstance(status, int) else f' (HTTP {status})'}") from None

    def bars(self, symbols: Sequence[str], start: dt.date, end: dt.date, *, asof: dt.date | None = None,
             tries: int = TRIES, counted: bool = True) -> dict[str, dict[dt.date, tuple[float, float]]]:
        """{symbol: {session day: (close, volume)}} of the VALID raw 1Day bars (close > 0 and volume > 0) of every
        page; every symbol asked for is a key. RuntimeError when a page still fails after its tries or the answer is
        not a bars answer; `Refused` when the venue or the gateway refused it for good (`counted` False: either is
        the caller's datum, not a failed or a refused request of the count)."""
        out: dict[str, dict[dt.date, tuple[float, float]]] = {str(s): {} for s in symbols}
        token = None
        for _ in range(MAX_PAGES):
            params: dict[str, Any] = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start.isoformat(),
                                      "end": end.isoformat(), "adjustment": "raw", "feed": "sip", "limit": PAGE_LIMIT}
            if asof is not None:
                params["asof"] = asof.isoformat()
            if token:
                params["page_token"] = token
            answer = self._get(params, tries=tries, counted=counted)
            if not isinstance(answer, Mapping):
                raise RuntimeError("the bars answer is not an object")
            rows_by = answer.get("bars")
            if rows_by is None and "bars" in answer:
                rows_by = {}  # the venue's answer for a span with no bar at all
            if not isinstance(rows_by, Mapping):
                raise RuntimeError("the bars answer has no bars")
            for symbol, rows in rows_by.items():
                seen = out.setdefault(str(symbol), {})
                for row in rows if isinstance(rows, list) else ():
                    if not isinstance(row, Mapping):
                        continue
                    day = bar_day(row.get("t"))
                    close, volume = _positive(row.get("c")), _positive(row.get("v"))
                    if day is not None and start <= day <= end and close is not None and volume is not None:
                        seen[day] = (close, volume)
            token = answer.get("next_page_token")
            if not token:
                return out
        raise RuntimeError(f"the bars did not end within {MAX_PAGES} pages")


# ------------------------------------------------------------------------------------------------------- the counting
def era_of(day: dt.date) -> int | None:
    for k, (first, last) in enumerate(ERAS):
        if first <= day <= last:
            return k
    return None


def judge(members: Sequence[dt.date], bars: Mapping[dt.date, tuple[float, float]]) -> str:
    """One spell's series against D19's acceptance: "ok", "no_bars" or "reused" (the module docstring, 3)."""
    valid = [d for d in members if d in bars]
    if not valid:
        return "no_bars"
    if statistics.median(bars[d][0] * bars[d][1] for d in valid) < REUSED_USD:
        return "reused"
    covered = len(valid) >= ACCEPT_SHARE * len(members)
    return "ok" if covered and members.index(valid[0]) <= ACCEPT_FIRST else "no_bars"


def house_facts() -> dict[str, Any]:
    """Fact 9, read locally: this box's memory (MB) and cores. None where it cannot be read."""
    total = available = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, _, rest = line.partition(":")
            if name in ("MemTotal", "MemAvailable"):
                mb = int(rest.split()[0]) // 1024
                total, available = (mb, available) if name == "MemTotal" else (total, mb)
    except (OSError, ValueError, IndexError):
        pass
    return {"mem_total_mb": total, "mem_available_mb": available, "cpus": os.cpu_count()}


def symbols_limit(probe: Probe, symbols: Sequence[str], day: dt.date) -> dict[str, Any]:
    """Fact 10: one bars request of one session for 39, 100, 200 and 400 symbols (as many as the open spells give):
    which counts answered, the largest that did, the first that was REFUSED (the datum: the venue or the gateway
    will not take that many) and the first that FAILED `LIMIT_TRIES` times for another reason (no datum: the limit
    was not measured there). `reading`: "found" (the limit lies from `largest_ok` to under `first_refused`), "at
    least" (every count asked was answered: the limit is `largest_ok` or more and was NOT found) or "not measured" (a
    step failed, or no count could be asked)."""
    asked: list[int] = []
    answered: list[int] = []
    refused = failed = None
    for count in LIMIT_LADDER:
        if count > len(symbols):
            break
        asked.append(count)
        try:
            probe.bars(list(symbols[:count]), day, day, tries=LIMIT_TRIES, counted=False)
        except ProbeStopped:
            raise
        except Refused:
            refused = count
            break
        except Exception:  # noqa: BLE001 - not a refusal: a failure that outlasted its tries says nothing of the limit
            failed = count
            break
        answered.append(count)
    reading = "found" if refused is not None else ("not measured" if failed is not None or not answered else "at least")
    return {"asked": asked, "answered": answered, "largest_ok": answered[-1] if answered else None,
            "first_refused": refused, "first_failed": failed, "reading": reading}


def run(gateway: Any, spells: Sequence[Spell], *, names: Sequence[str] | None = None, batch: int = BATCH,
        limit_probe: bool = True, sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time, max_requests: int = MAX_REQUESTS,
        pause: float = 0.0) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """The probe (the module docstring): (the receipt: counts only, the listing: {"no_bars" | "reused" | "error":
    [tickers]} for the terminal's `--list`, never written). `names`: fact 1's test tickers (None: `test_names` of the
    spell file). `ProbeStopped` when SPY gives no calendar."""
    probe = Probe(gateway, sleep=sleep, max_requests=max_requests, pause=pause)
    batch = max(1, int(batch))
    # 1. the calendar
    sessions: list[dt.date] = []
    for first, last in ERAS:
        try:
            sessions.extend(sorted(probe.bars([CALENDAR_SYMBOL], first, last)[CALENDAR_SYMBOL]))
        except Refused as exc:
            raise ProbeStopped(f"no calendar: the calendar's request was {exc}") from None
        except RuntimeError as exc:
            raise ProbeStopped(f"no calendar: {exc}") from None
    if not sessions:
        raise ProbeStopped("no calendar: the calendar symbol has no bar in the eras")
    by_era = [[d for d in sessions if era_of(d) == k] for k in range(len(ERAS))]

    # 2. the spells that have a member session in the eras
    probed: list[tuple[Spell, list[dt.date]]] = []
    for spell in spells:
        members = member_sessions(spell, sessions)
        if members:
            probed.append((spell, members))
    series: dict[int, dict[dt.date, tuple[float, float]]] = {i: {} for i in range(len(probed))}
    errors: set[int] = set()
    open_ix = [i for i, (spell, _) in enumerate(probed) if spell.end is None]
    ended_ix = [i for i, (spell, _) in enumerate(probed) if spell.end is not None]

    # open spells: together, the venue's own asof (today: not named). A REFUSED batch is asked again one ticker at
    # a time (one name the venue will not serve must not cost its 38 neighbours their bars); a ticker refused alone
    # has no bars.
    for k in range(len(ERAS)):
        wanted = [i for i in open_ix if any(era_of(d) == k for d in probed[i][1])] if by_era[k] else []
        for at in range(0, len(wanted), batch):
            group = wanted[at:at + batch]
            tickers = sorted({probed[i][0].ticker for i in group})
            got: dict[str, dict[dt.date, tuple[float, float]]] = {}
            try:
                got = probe.bars(tickers, by_era[k][0], by_era[k][-1])
            except ProbeStopped:
                raise
            except Refused:
                for ticker in tickers if len(tickers) > 1 else ():
                    try:
                        got.update(probe.bars([ticker], by_era[k][0], by_era[k][-1]))
                    except ProbeStopped:
                        raise
                    except Refused:
                        continue
                    except RuntimeError:
                        errors.update(i for i in group if probed[i][0].ticker == ticker)
            except RuntimeError:
                errors.update(group)
                continue
            for i in group:
                series[i].update(got.get(probed[i][0].ticker, {}))

    # ended spells: each alone, asof inside the spell
    differs: set[int] = set()
    tested: set[int] = set()
    given = names is not None
    test = {str(n).strip().upper() for n in (names if given else test_names(spells, sessions)) if str(n).strip()}
    for i in ended_ix:
        spell, members = probed[i]
        asof = members[-1]
        again: dict[dt.date, tuple[float, float]] = {}
        again_ok = spell.ticker in test
        for k in range(len(ERAS)):
            mine = [d for d in members if era_of(d) == k]
            if not mine:
                continue
            try:
                series[i].update(probe.bars([spell.ticker], mine[0], mine[-1], asof=asof).get(spell.ticker, {}))
            except ProbeStopped:
                raise
            except Refused:
                pass  # the venue will not serve this spell as of then: no bars from it, and no rerun changes that
            except RuntimeError:
                errors.add(i)
                continue
            if spell.ticker in test:
                # FACT 1's test: the same window without asof (today's holder of the ticker, if any; a ticker nobody
                # holds today may be refused: that is an answer of no bars).
                try:
                    again.update(probe.bars([spell.ticker], mine[0], mine[-1]).get(spell.ticker, {}))
                except ProbeStopped:
                    raise
                except Refused:
                    pass
                except RuntimeError:
                    again_ok = False
        if spell.ticker in test and i not in errors:
            tested.add(i)
            if again_ok and again != {d: v for d, v in series[i].items()}:
                differs.add(i)

    # 3. the count
    verdicts = {i: ("error" if i in errors else judge(members, series[i])) for i, (_, members) in enumerate(probed)}
    by_year = {year: {"member_days": 0, "with_bar": 0} for year in YEARS}
    for i, (_, members) in enumerate(probed):
        for d in members:
            row = by_year[d.year]
            row["member_days"] += 1
            if verdicts[i] == "ok" and d in series[i]:
                row["with_bar"] += 1
    for row in by_year.values():
        row["share"] = round(row["with_bar"] / row["member_days"], 6) if row["member_days"] else None
    shares = [row["share"] for row in by_year.values()]
    passed = all(s is not None and s >= COVERAGE_MIN for s in shares)
    count = {name: sum(1 for v in verdicts.values() if v == name) for name in ("ok", "no_bars", "reused", "error")}
    ended_count = {name: sum(1 for i in ended_ix if verdicts[i] == name) for name in ("ok", "no_bars", "reused")}
    test_spells, asof_differs = len(tested), len(differs)
    test_ok = sum(1 for i in tested if verdicts[i] == "ok")
    differs_ok = sum(1 for i in differs if verdicts[i] == "ok")
    # TWO QUESTIONS, REPORTED APART. Does asof resolve the ticker? Of the test spells that answer differently without
    # asof (`asof_differs`: the venue honours it and it changes the answer), `differs_accepted` were served as an
    # index member's series: "holds" when there is at least one and all of them were. Does the venue have the bars?
    # `test_accepted` of `test_spells`, its own line: a test spell with no bars is a coverage fact, not a verdict on
    # asof.
    if not test_spells:
        fact1 = "not_met"
    elif not asof_differs:
        fact1 = "not_shown"
    else:
        fact1 = "holds" if differs_ok == asof_differs else "fails"

    # 4. the facts
    limit = None
    if limit_probe:
        open_symbols = sorted({probed[i][0].ticker for i in open_ix if verdicts[i] == "ok"})
        limit = symbols_limit(probe, open_symbols, sessions[-1])
    receipt = {
        "version": VERSION,
        "at": dt.datetime.fromtimestamp(float(clock()), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by_year": {str(year): by_year[year] for year in YEARS},
        "sessions": {str(year): sum(1 for d in sessions if d.year == year) for year in YEARS},
        "spells": len(probed), "open": len(open_ix), "ended": len(ended_ix),
        "accepted": count["ok"], "no_bars": count["no_bars"], "reused": count["reused"], "errors": count["error"],
        "requests": probe.requests, "requests_failed": probe.failed, "requests_refused": probe.refused,
        "coverage_min": COVERAGE_MIN, "pass": passed,
        "verdict": "pass" if passed else ("incomplete" if count["error"] else "fail"),
        "facts": {
            "1": {"what": "asof resolves an ended spell's ticker to the spell's own company, and ended members "
                          "have bars",
                  "ended_spells": len(ended_ix), "ended_accepted": ended_count["ok"],
                  "ended_no_bars": ended_count["no_bars"], "ended_reused": ended_count["reused"],
                  "test_names": len(test), "test_names_from": "--names" if given else "the spell file",
                  "test_spells": test_spells, "test_accepted": test_ok,
                  "asof_differs": asof_differs, "differs_accepted": differs_ok, "verdict": fact1},
            "2": NOT_PROBED, "3": NOT_PROBED, "4": NOT_PROBED,
            "9": house_facts(),
            "10": limit if limit is not None else "not probed (--no-limit-probe)",
        },
    }
    listing = {name: sorted({probed[i][0].ticker for i, v in verdicts.items() if v == name})
               for name in ("no_bars", "reused", "error")}
    return receipt, listing


# ------------------------------------------------------------------------------------------------------ the command
def write_receipt(root: str | Path, receipt: Mapping[str, Any]) -> Path:
    """`<root>/equity-daily/probe.json`, atomic, owner-only."""
    path = Path(root) / STORE_DIR / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, indent=1) + "\n")
    os.replace(tmp, path)
    return path


def default_release() -> str:
    """The release whose gateway client is used when `--release` names none: the checkout this script sits in when it
    has one, else the House's running release (the script copied alone onto the box)."""
    here = Path(__file__).resolve().parents[1]
    if (here / "league" / "ops" / "context.py").is_file():
        return str(here)
    return HOUSE_RELEASE


def env_file(release: str | Path, env: str | Path | None = None) -> Path:
    """The House's environment file: `env` when given, else `.env` BESIDE THE RELEASE (/workspace/.env for the House's
    /workspace/current; the release's path as given, a link not followed). Never beside `--root`: the receipt may be
    written anywhere, and the token is the House's wherever that is."""
    return Path(env) if env else Path(release).parent / ENV_FILE


def house_gateway(release: str | Path, root: str | Path, env: str | Path | None = None) -> Any:
    """The running release's own gateway client (`league.ops.context`), built as a House job's is. Where the token is
    not in this process's environment, the release's own loader reads the House's environment file into it
    (`league.service.load_env`, as every House process starts; the file is `env_file`'s). Then the release's own check
    is asked ONCE whether a token is set, and `NoGateway` says so at once when none is: before, the probe counted
    three requests it never sent, waited 25 seconds and stopped on "no calendar". This script never reads, keeps,
    prints or returns the token: the loader and the check are the release's, and the check's answer is dropped."""
    release = str(Path(release))
    if release not in sys.path:
        sys.path.insert(0, release)
    from league.ops.context import Context, token_from_env  # noqa: PLC0415 - the running release's, found only now

    where = env_file(release, env)
    if "GATEWAY_TOKEN" not in os.environ:
        if env:
            os.environ["LEAGUE_ENV"] = str(where)
        else:
            os.environ.setdefault("LEAGUE_ENV", str(where))
        where = Path(os.environ["LEAGUE_ENV"])
        try:
            from league.service import load_env  # noqa: PLC0415

            load_env()
        except Exception:  # noqa: BLE001 - no loader, no file, or one it refuses: the check below says what is missing
            pass
    try:
        token_from_env()
    except Exception:  # noqa: BLE001 - its own text is not repeated
        raise NoGateway(f"GATEWAY_TOKEN is not set in this process and was not found in the House's environment "
                        f"file ({where}): give the file with --env, or run the probe as the House's processes "
                        "run") from None
    return Context("panel_probe", root=root, due_at=time.time(), release=release).gateway


def main(argv: Sequence[str] | None = None, *, gateway: Any = None, sleep: Callable[[float], None] = time.sleep,
         clock: Callable[[], float] = time.time, out: Any = None) -> int:
    """The command (the module docstring). `gateway`, `sleep`, `clock`, `out`: the tests'."""
    parser = argparse.ArgumentParser(description="E4 step -1: the panel's coverage probe (read-only; counts only)")
    parser.add_argument("--spells", required=True, help="the membership spell file (ticker,start_date,end_date)")
    parser.add_argument("--root", default="/workspace/state", help="the House's state directory")
    parser.add_argument("--release", default=default_release(),
                        help="the running release (its league.ops.context is the gateway client)")
    parser.add_argument("--env", default=None,
                        help="the House's environment file (default: .env beside the release, wherever --root is)")
    parser.add_argument("--pause", type=float, default=PAUSE_S, help="seconds waited before every request")
    parser.add_argument("--names", default=None,
                        help="fact 1's test tickers, comma-separated (default: read off the spell file: every ticker "
                             "with an ended spell in the eras and a later spell)")
    parser.add_argument("--batch", type=int, default=BATCH, help="symbols a request of open spells")
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--no-limit-probe", action="store_true", help="skip fact 10's ladder")
    parser.add_argument("--no-write", action="store_true", help="print the receipt, write no file")
    parser.add_argument("--list", action="store_true",
                        help="also print the tickers with no bars, reused or in error (terminal only)")
    args = parser.parse_args(argv)
    out = out or sys.stdout
    try:
        spells = parse_spells(Path(args.spells).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"panel_probe: the spell file cannot be read: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if gateway is None:
        try:
            gateway = house_gateway(args.release, args.root, args.env)
        except NoGateway as exc:  # this script's own words: a variable's name and a path
            print(f"panel_probe: no gateway client: {exc}", file=sys.stderr)
            return EXIT_CANNOT_RUN
        except Exception as exc:  # noqa: BLE001 - no release: said by its type, never its text
            print(f"panel_probe: no gateway client: {type(exc).__name__}", file=sys.stderr)
            return EXIT_CANNOT_RUN
    try:
        receipt, listing = run(gateway, spells, names=None if args.names is None else args.names.split(","),
                               batch=args.batch, limit_probe=not args.no_limit_probe, sleep=sleep, clock=clock,
                               max_requests=args.max_requests, pause=args.pause)
    except (ProbeStopped, SealedRequest) as exc:
        print(f"panel_probe: stopped (running it again will not help): {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    if not args.no_write:
        receipt["written"] = str(write_receipt(args.root, receipt))
    print(json.dumps(receipt, sort_keys=True, indent=1), file=out)
    if args.list:
        for name in ("no_bars", "reused", "error"):
            print(f"{name} ({len(listing[name])}): {' '.join(listing[name])}", file=out)
    return {"pass": EXIT_PASS, "fail": EXIT_FAIL}.get(receipt["verdict"], EXIT_INCOMPLETE)


if __name__ == "__main__":
    raise SystemExit(main())
