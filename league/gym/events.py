"""The static event and rate tables the ENGINE consults. A program sees booleans only.

`ctx.events` says whether today is an FOMC decision day, a CPI release day, a jobs-report day, the
monthly options expiry, a quarter's last trading day or a half day, and `ctx.events_next` says the
same of the next session (a trader knows the calendar in advance). The dates below are public macro
calendars, not market data. Entries marked "unverified" are the best known at build time (Sept 26,
2026) and should be checked against the BLS and Federal Reserve archives; the 2025 government
shutdown moved several releases. The rate table is the Federal Reserve's target range (upper bound)
by effective date, less 0.10 for the effective rate; it only enters Black-Scholes (a 0-14 day option
barely feels it), so the 2026 entries simply hold the last known level.

2020-2021 (the Train extension, Sept 27, 2026) were checked against the Federal Reserve's 2020 meeting page and
calendar and the BLS 2020 and 2021 release schedules. Only SCHEDULED FOMC days are flags: the unscheduled actions of
March 3 and March 15, 2020 were not on any calendar in advance (a program would otherwise learn of them the day
before through `events_next`), and the scheduled March 17-18, 2020 meeting was cancelled. Those two cuts are in the
rate table from their effective dates.

2017-2019 (Train from 2017, Sept 29, 2026) were checked against the Federal Reserve's 2017, 2018 and 2019 meeting
pages (eight scheduled meetings a year; the unscheduled conference call of October 4, 2019 is no flag), its table of
target range changes (the steps from December 17, 2015 on, so no 2016-2019 day falls back to the table's first row),
and the BLS archives of the CPI and Employment Situation releases (the December 2016 figures came out on January 18
and January 6, 2017). The CPI of April 14, 2017 came out on Good Friday, a market holiday, like April 10, 2020's:
listed as released.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from typing import Callable, Iterable, Sequence

D = dt.date.fromisoformat

#: FOMC statement days (the second day of each scheduled meeting).
FOMC = frozenset(map(D, (
    "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14", "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
    "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13", "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
    "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19", "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
    "2020-01-29", "2020-04-29", "2020-06-10", "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
    "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16", "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
    "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
)))

#: CPI release days (08:30 ET). 2025 Oct-Dec and 2026: unverified (the shutdown moved them).
CPI = frozenset(map(D, (
    "2017-01-18", "2017-02-15", "2017-03-15", "2017-04-14", "2017-05-12", "2017-06-14", "2017-07-14", "2017-08-11",
    "2017-09-14", "2017-10-13", "2017-11-15", "2017-12-13",
    "2018-01-12", "2018-02-14", "2018-03-13", "2018-04-11", "2018-05-10", "2018-06-12", "2018-07-12", "2018-08-10",
    "2018-09-13", "2018-10-11", "2018-11-14", "2018-12-12",
    "2019-01-11", "2019-02-13", "2019-03-12", "2019-04-10", "2019-05-10", "2019-06-12", "2019-07-11", "2019-08-13",
    "2019-09-12", "2019-10-10", "2019-11-13", "2019-12-11",
    "2020-01-14", "2020-02-13", "2020-03-11", "2020-04-10", "2020-05-12", "2020-06-10", "2020-07-14", "2020-08-12",
    "2020-09-11", "2020-10-13", "2020-11-12", "2020-12-10",
    "2021-01-13", "2021-02-10", "2021-03-10", "2021-04-13", "2021-05-12", "2021-06-10", "2021-07-13", "2021-08-11",
    "2021-09-14", "2021-10-13", "2021-11-10", "2021-12-10",
    "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11", "2022-06-10", "2022-07-13", "2022-08-10",
    "2022-09-13", "2022-10-13", "2022-11-10", "2022-12-13",
    "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10", "2023-06-13", "2023-07-12", "2023-08-10",
    "2023-09-13", "2023-10-12", "2023-11-14", "2023-12-12",
    "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15", "2024-06-12", "2024-07-11", "2024-08-14",
    "2024-09-11", "2024-10-10", "2024-11-13", "2024-12-11",
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13", "2025-06-11", "2025-07-15", "2025-08-12",
    "2025-09-11", "2025-10-24", "2025-12-18",
    "2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-12",
    "2026-09-11",
)))

#: Employment Situation release days (08:30 ET). 2025 Oct-Dec and 2026: unverified.
JOBS = frozenset(map(D, (
    "2017-01-06", "2017-02-03", "2017-03-10", "2017-04-07", "2017-05-05", "2017-06-02", "2017-07-07", "2017-08-04",
    "2017-09-01", "2017-10-06", "2017-11-03", "2017-12-08",
    "2018-01-05", "2018-02-02", "2018-03-09", "2018-04-06", "2018-05-04", "2018-06-01", "2018-07-06", "2018-08-03",
    "2018-09-07", "2018-10-05", "2018-11-02", "2018-12-07",
    "2019-01-04", "2019-02-01", "2019-03-08", "2019-04-05", "2019-05-03", "2019-06-07", "2019-07-05", "2019-08-02",
    "2019-09-06", "2019-10-04", "2019-11-01", "2019-12-06",
    "2020-01-10", "2020-02-07", "2020-03-06", "2020-04-03", "2020-05-08", "2020-06-05", "2020-07-02", "2020-08-07",
    "2020-09-04", "2020-10-02", "2020-11-06", "2020-12-04",
    "2021-01-08", "2021-02-05", "2021-03-05", "2021-04-02", "2021-05-07", "2021-06-04", "2021-07-02", "2021-08-06",
    "2021-09-03", "2021-10-08", "2021-11-05", "2021-12-03",
    "2022-01-07", "2022-02-04", "2022-03-04", "2022-04-01", "2022-05-06", "2022-06-03", "2022-07-08", "2022-08-05",
    "2022-09-02", "2022-10-07", "2022-11-04", "2022-12-02",
    "2023-01-06", "2023-02-03", "2023-03-10", "2023-04-07", "2023-05-05", "2023-06-02", "2023-07-07", "2023-08-04",
    "2023-09-01", "2023-10-06", "2023-11-03", "2023-12-08",
    "2024-01-05", "2024-02-02", "2024-03-08", "2024-04-05", "2024-05-03", "2024-06-07", "2024-07-05", "2024-08-02",
    "2024-09-06", "2024-10-04", "2024-11-01", "2024-12-06",
    "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04", "2025-05-02", "2025-06-06", "2025-07-03", "2025-08-01",
    "2025-09-05", "2025-11-20", "2025-12-16",
    "2026-01-09", "2026-02-11", "2026-03-06", "2026-04-03", "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
    "2026-09-04",
)))

#: (effective date, annualized continuously-compounded rate) steps: the target's upper bound less 0.10.
RATES: tuple[tuple[dt.date, float], ...] = tuple((D(day), (upper - 0.10) / 100.0) for day, upper in (
    ("2015-12-17", 0.50), ("2016-12-15", 0.75), ("2017-03-16", 1.00), ("2017-06-15", 1.25), ("2017-12-14", 1.50),
    ("2018-03-22", 1.75), ("2018-06-14", 2.00), ("2018-09-27", 2.25), ("2018-12-20", 2.50), ("2019-08-01", 2.25),
    ("2019-09-19", 2.00),
    ("2019-10-31", 1.75), ("2020-03-04", 1.25), ("2020-03-16", 0.25),
    ("2021-01-01", 0.25), ("2022-03-17", 0.50), ("2022-05-05", 1.00), ("2022-06-16", 1.75), ("2022-07-28", 2.50),
    ("2022-09-22", 3.25), ("2022-11-03", 4.00), ("2022-12-15", 4.50), ("2023-02-02", 4.75), ("2023-03-23", 5.00),
    ("2023-05-04", 5.25), ("2023-07-27", 5.50), ("2024-09-19", 5.00), ("2024-11-08", 4.75), ("2024-12-19", 4.50),
    ("2025-09-18", 4.25), ("2025-10-30", 4.00), ("2025-12-11", 3.75),
))
_RATE_DAYS = [d for d, _ in RATES]

#: Stock splits of the Gym's roots: (root, ex-date, factor), the ex-date being the first session the shares trade split
#: and the factor new shares per old (3.0 for a 3-for-1, 0.1 for a 1-for-10 reverse split). Public: each was announced
#: weeks before, so a trader knew it on the eve, as the macro calendars above. The ENGINE uses it (`engine.split_eves`:
#: a root's positions close on the eve, since the OCC's adjusted contracts are not in the chain under the old keys); a
#: program never sees it. Only this table closes anything: the price cross-check (`engine.split_check`, the prior
#: session's last price over the next session's first near a whole factor) only raises an alert, because read on its
#: own it would take an overnight crash of about half for a 2-for-1 split, a look into the next session. The eight of
#: 2022-25 were found by that cross-check in the Gym image's underlying for all 25 roots, 2022-01-03..2025-12-31, and
#: confirmed against the issuers' announcements (the review of #406, Sept 28, 2026). The five of 2020-21 are the Train
#: extension's: the 2020-24 image holds those years for the core five only (SPY, QQQ, IWM, XSP, SPXW), whose prices
#: show no split there (the cross-check over its Train and Validation, Sept 28, 2026), so these names' rows come from
#: the issuers' announcements and a public split history, and act only once an image holds their 2020-21 days. None
#: of the 25 roots split in 2026 to Sept 28 (the public history; the holdout's prices are sealed and were not read).
#: Add a split the same way before a run covers its day (the cross-check flags a split-like gap with no entry in the
#: result).
SPLITS: tuple[tuple[str, dt.date, float], ...] = (
    ("AAPL", D("2020-08-31"), 4.0),
    ("TSLA", D("2020-08-31"), 5.0),
    ("TQQQ", D("2021-01-21"), 2.0),
    ("SOXL", D("2021-03-02"), 15.0),
    ("NVDA", D("2021-07-20"), 4.0),
    ("TQQQ", D("2022-01-13"), 2.0),
    ("AMZN", D("2022-06-06"), 20.0),
    ("GOOGL", D("2022-07-18"), 20.0),
    ("TSLA", D("2022-08-25"), 3.0),
    ("SMH", D("2023-05-05"), 2.0),
    ("NVDA", D("2024-06-10"), 10.0),
    ("SMCI", D("2024-10-01"), 10.0),
    ("TQQQ", D("2025-11-20"), 2.0),
)

EVENT_NAMES =("fomc", "cpi", "jobs", "monthly_opex", "quarter_end", "half_day")


def rate_on(day: dt.date) -> float:
    """The day's risk-free rate (annual, continuous) for Black-Scholes. A day before the table's first step
    (December 17, 2015; before any Train day) takes that first step's rate."""
    i = bisect_right(_RATE_DAYS, day) - 1
    return RATES[max(0, i)][1]


def third_friday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)


class EventCalendar:
    """Event flags by date over a store's trading calendar (so the monthly expiry moves to the
    Thursday when its Friday is a holiday, and the quarter's end is its last TRADING day)."""

    def __init__(self, trading_days: Iterable[dt.date], session: Callable[[dt.date], tuple[int, int]] | None = None):
        self.days = sorted(set(trading_days))
        self._set = set(self.days)
        self._session = session

    def monthly_opex(self, day: dt.date) -> bool:
        target = third_friday(day.year, day.month)
        while target not in self._set and target.day > 14:
            target -= dt.timedelta(days=1)
        return day == target

    def quarter_end(self, day: dt.date) -> bool:
        if day.month not in (3, 6, 9, 12):
            return False
        later = [d for d in self.days if d > day and d.month == day.month and d.year == day.year]
        return not later and day in self._set

    def half_day(self, day: dt.date) -> bool:
        if self._session is None:
            return False
        try:
            open_min, close_min = self._session(day)
        except Exception:
            return False
        return close_min - open_min < 390

    def flags(self, day: dt.date | None) -> dict[str, bool]:
        """The booleans a program sees for `day` (all False for None: no next session known)."""
        if day is None:
            return {name: False for name in EVENT_NAMES}
        return {
            "fomc": day in FOMC,
            "cpi": day in CPI,
            "jobs": day in JOBS,
            "monthly_opex": self.monthly_opex(day),
            "quarter_end": self.quarter_end(day),
            "half_day": self.half_day(day),
        }

    def next_day(self, day: dt.date) -> dt.date | None:
        i = bisect_right(self.days, day)
        return self.days[i] if i < len(self.days) else None


def flags_for(day: dt.date, trading_days: Sequence[dt.date], session: Callable[[dt.date], tuple[int, int]] | None = None) -> tuple[dict[str, bool], dict[str, bool]]:
    """(today's flags, the next session's flags): the live path's one call."""
    cal = EventCalendar(trading_days, session)
    return cal.flags(day), cal.flags(cal.next_day(day))
