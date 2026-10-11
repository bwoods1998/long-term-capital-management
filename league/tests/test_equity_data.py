"""THE EQUITY LANE's data job (release E1; league/ops/equity_data.py): the gateway's paging, the store's audit (the
calendar, sane bars, splits seen in the raw/all ratio, volumes, the regular-session check of the design's fact 1), the
job's write through the core store and its registry row.

Every bar here is synthetic (a few invented prices on the true NYSE calendar of early 2025), never market data. Core's
`league.equity.store.nyse_sessions` and `write_store` are mocked at the interface (league/equity/INTERFACES.md 4.3): this
package tests what it hands them, and core's own tests hold the store itself."""

from __future__ import annotations

import datetime as dt
import json
import math
import unittest
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

from league.ops import equity_data as ED

NY = ZoneInfo("America/New_York")


def calendar(first: dt.date, last: dt.date) -> list[tuple[dt.date, bool]]:
    """The NYSE sessions of `ltcm.data` (2022 on), as `store.nyse_sessions` answers them."""
    from ltcm.data import us_equity_session

    out, day = [], first
    while day <= last:
        session = us_equity_session(day)
        if session is not None:
            out.append((day, bool(session.early_close)))
        day += dt.timedelta(days=1)
    return out


CAL = calendar(dt.date(2025, 1, 2), dt.date(2025, 3, 31))
DAYS = [d for d, _ in CAL]


def stamp(day: dt.date, hh: int = 0, mm: int = 0) -> str:
    return dt.datetime.combine(day, dt.time(hh, mm), NY).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bars(symbols=("SPY", "QQQ"), days=DAYS, *, splits=None, base=100.0):
    """(raw, all) rows per symbol: a gentle invented wave; `splits[sym]` = (day, factor): raw prices from that day on are
    divided by the factor, and the all series (as of the last day) divides every earlier price by it too."""
    raw, adj = {}, {}
    for k, symbol in enumerate(symbols):
        split_day, factor = (splits or {}).get(symbol, (None, 1.0))
        r_rows, a_rows = [], []
        prev = base + 10 * k
        for i, day in enumerate(days):
            close = base + 10 * k + 2.0 * math.sin(i / 3.0)
            o, c = prev, close
            h, l = max(o, c) * 1.002, min(o, c) * 0.998
            prev = close
            scale = factor if split_day is not None and day >= split_day else 1.0
            r = {"t": stamp(day), "o": o / scale, "h": h / scale, "l": l / scale, "c": c / scale, "v": 1_000_000 + i}
            back = factor if split_day is not None and day < split_day else 1.0
            a = {"t": r["t"], **{f: r[f] / back for f in ("o", "h", "l", "c")}, "v": r["v"] * back}
            r_rows.append(r)
            a_rows.append(a)
        raw[symbol], adj[symbol] = r_rows, a_rows
    return raw, adj


def minutes(day: dt.date, early: bool, *, base: float = 100.0):
    """A few invented SPY minute bars of `day`: one before the open, three in the session, one after the close."""
    close_h = 13 if early else 16
    rows = [{"t": stamp(day, 8, 0), "o": base - 3, "h": base - 2, "l": base - 4, "c": base - 3, "v": 500},
            {"t": stamp(day, 9, 30), "o": base, "h": base + 1, "l": base - 1, "c": base + 0.5, "v": 1000},
            {"t": stamp(day, 11, 0), "o": base + 0.5, "h": base + 2, "l": base, "c": base + 1, "v": 2000},
            {"t": stamp(day, close_h - 1, 59), "o": base + 1, "h": base + 1.5, "l": base + 0.5, "c": base + 1.25,
             "v": 3000},
            {"t": stamp(day, 17, 0), "o": base + 5, "h": base + 6, "l": base + 4, "c": base + 5, "v": 400}]
    return rows


def session_bar(day: dt.date, early: bool, *, base: float = 100.0):
    """SPY's 1Day bar of `day` built from its session minutes (the regular session exactly)."""
    rows = minutes(day, early, base=base)[1:4]
    return {"t": stamp(day), "o": rows[0]["o"], "h": max(r["h"] for r in rows), "l": min(r["l"] for r in rows),
            "c": rows[-1]["c"], "v": sum(r["v"] for r in rows)}


class Gateway:
    """The gateway's bars route over in-memory rows, paged `page` rows at a time (a page token is the offset)."""

    def __init__(self, raw=None, adj=None, minute=None, *, page=10_000, error=None):
        self.data = {"raw": raw or {}, "all": adj or {}}
        self.minute = minute or {}
        self.page = page
        self.error = error
        self.calls = []

    def get(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error
        assert path == ED.BARS
        symbols = params["symbols"].split(",")
        if params["timeframe"] == "1Min":
            lo = dt.datetime.fromisoformat(params["start"].replace("Z", "+00:00"))
            hi = dt.datetime.fromisoformat(params["end"].replace("Z", "+00:00"))
            rows = [(s, r) for s in symbols for r in self.minute.get(s, [])
                    if lo <= dt.datetime.fromisoformat(r["t"].replace("Z", "+00:00")) <= hi]
        else:
            lo, hi = dt.date.fromisoformat(params["start"][:10]), dt.date.fromisoformat(params["end"][:10])
            rows = [(s, r) for s in symbols for r in self.data[params["adjustment"]].get(s, [])
                    if lo <= ED.ny_day(r["t"]) <= hi]
        start = int(params.get("page_token") or 0)
        chunk = rows[start:start + self.page]
        out = {}
        for s, r in chunk:
            out.setdefault(s, []).append(dict(r))
        nxt = start + self.page
        return {"bars": out, "next_page_token": str(nxt) if nxt < len(rows) else None}


def fake_sessions(cal):
    def nyse_sessions(start, end):
        return [(d, e) for d, e in cal if start <= d <= end]
    return nyse_sessions


# ================================================================================================== the gateway
class TheFetch(unittest.TestCase):
    def test_it_pages_to_the_end_and_orders_each_symbols_rows(self):
        raw, _ = bars()
        gw = Gateway(raw=raw, page=7)
        out = ED.fetch(gw, ["SPY", "QQQ"], "2016-01-04", "2025-03-31", adjustment="raw")
        self.assertEqual([len(out["SPY"]), len(out["QQQ"])], [len(DAYS), len(DAYS)])
        self.assertEqual([ED.ny_day(r["t"]) for r in out["SPY"]], DAYS)
        self.assertGreater(len(gw.calls), 2)
        first = gw.calls[0][1]
        self.assertEqual((first["timeframe"], first["feed"], first["adjustment"], first["start"]),
                         ("1Day", "sip", "raw", "2016-01-04"))
        self.assertNotIn("page_token", first)
        self.assertEqual(gw.calls[1][1]["page_token"], "7")

    def test_a_malformed_answer_or_a_cursor_that_never_ends_is_an_error(self):
        class NoBars:
            def get(self, path, params=None):
                return {"error": "nope"}

        class Twice:
            def get(self, path, params=None):
                row = {"t": stamp(DAYS[0]), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
                return {"bars": {"SPY": [row, dict(row)]}}

        class Forever:
            def get(self, path, params=None):
                return {"bars": {}, "next_page_token": "again"}

        for gw in (NoBars(), Twice(), Forever()):
            with self.assertRaises(ValueError):
                ED.fetch(gw, ["SPY"], "2025-01-02", "2025-01-03", adjustment="raw")
        self.assertEqual(ED.fetch(Gateway(), ["SPY"], "2025-01-02", "2025-01-03", adjustment="all"), {"SPY": []})


# ================================================================================================== the audit
class TheAudit(unittest.TestCase):
    REGULAR = {"verdict": "regular", "days": [], "mismatches": []}

    def check(self, raw, adj, cal=CAL, regular=REGULAR):
        return ED.audit(cal, raw, adj, regular=regular)

    def test_a_clean_store_passes_every_check(self):
        raw, adj = bars()
        out = self.check(raw, adj)
        self.assertTrue(out["passed"], out)
        self.assertEqual(set(out["checks"]), {"calendar", "ohlc", "splits", "volume", "regular"})
        self.assertEqual(out["checks"]["splits"]["found"], {})
        self.assertEqual((out["sessions"], out["symbols"]), (len(DAYS), 2))

    def test_a_gap_an_extra_day_or_disagreeing_series_fail_the_calendar(self):
        raw, adj = bars()
        gap = DAYS[10]
        raw["SPY"] = [r for r in raw["SPY"] if ED.ny_day(r["t"]) != gap]
        adj["SPY"] = [r for r in adj["SPY"] if ED.ny_day(r["t"]) != gap]
        out = self.check(raw, adj)
        self.assertFalse(out["passed"])
        self.assertFalse(out["checks"]["calendar"]["passed"])
        self.assertIn(str(gap), out["checks"]["calendar"]["problems"][0])
        # Another symbol's gap inside its own span fails too; its listing after the first session does not.
        raw, adj = bars()
        raw["QQQ"], adj["QQQ"] = raw["QQQ"][5:], adj["QQQ"][5:]
        self.assertTrue(self.check(raw, adj)["passed"], "a symbol listed later is no gap")
        raw["QQQ"] = [r for r in raw["QQQ"] if ED.ny_day(r["t"]) != DAYS[20]]
        adj["QQQ"] = [r for r in adj["QQQ"] if ED.ny_day(r["t"]) != DAYS[20]]
        self.assertFalse(self.check(raw, adj)["checks"]["calendar"]["passed"])
        # A bar on a Saturday, and raw and all on different days.
        raw, adj = bars()
        raw["SPY"].append({**raw["SPY"][-1], "t": stamp(dt.date(2025, 3, 29))})
        adj["SPY"].append({**adj["SPY"][-1], "t": stamp(dt.date(2025, 3, 29))})
        self.assertIn("not sessions", " ".join(self.check(raw, adj)["checks"]["calendar"]["problems"]))
        raw, adj = bars()
        adj["QQQ"] = adj["QQQ"][:-1]
        self.assertIn("disagree", " ".join(self.check(raw, adj)["checks"]["calendar"]["problems"]))

    def test_an_insane_bar_fails_ohlc(self):
        raw, adj = bars()
        raw["QQQ"][7] = {**raw["QQQ"][7], "h": raw["QQQ"][7]["c"] * 0.9}
        out = self.check(raw, adj)
        self.assertFalse(out["checks"]["ohlc"]["passed"])
        self.assertIn("QQQ raw", out["checks"]["ohlc"]["problems"][0])
        raw, adj = bars()
        adj["SPY"][3] = {**adj["SPY"][3], "l": float("nan")}
        self.assertFalse(self.check(raw, adj)["checks"]["ohlc"]["passed"])
        raw, adj = bars()
        raw["SPY"][2] = {**raw["SPY"][2], "o": 0.0, "l": 0.0}
        self.assertFalse(self.check(raw, adj)["passed"])

    def test_a_split_is_seen_in_the_ratio_and_must_show_in_the_raw_close(self):
        split = DAYS[30]
        raw, adj = bars(splits={"QQQ": (split, 2.0)})
        out = self.check(raw, adj)
        self.assertTrue(out["passed"], out["checks"]["splits"])
        self.assertEqual(out["checks"]["splits"]["found"], {"QQQ": [[split.isoformat(), 2.0]]})
        # The all series adjusted for a split the raw close never shows: an adjustment nothing explains.
        raw, adj = bars()
        adj["QQQ"] = [{**a, **{f: a[f] / 2.0 for f in ("o", "h", "l", "c")}} if ED.ny_day(a["t"]) < split else a
                      for a in adj["QQQ"]]
        unexplained = self.check(raw, adj)
        self.assertFalse(unexplained["checks"]["splits"]["passed"])
        self.assertIn("does not show it", unexplained["checks"]["splits"]["problems"][0])
        # A raw close that halves while the all series follows it: a split the all series did not adjust.
        raw, _ = bars(splits={"SPY": (split, 2.0)})
        out = self.check(raw, {"SPY": [dict(r) for r in raw["SPY"]], "QQQ": bars()[1]["QQQ"]})
        self.assertFalse(out["checks"]["splits"]["passed"])
        self.assertIn("did not adjust", out["checks"]["splits"]["problems"][0])

    def test_a_missing_volume_fails(self):
        raw, adj = bars()
        raw["SPY"][4] = {**raw["SPY"][4], "v": 0}  # a bar of volume 0 that shows a range: prints with no volume
        raw["QQQ"][9] = {**raw["QQQ"][9], "v": None}
        out = self.check(raw, adj)
        self.assertFalse(out["checks"]["volume"]["passed"])
        self.assertEqual(out["checks"]["volume"]["count"], 2)
        self.assertEqual(out["checks"]["volume"]["zero"], {}, "neither is the flat bar of a session without a trade")
        raw, adj = bars()
        flat = raw["QQQ"][9]["c"]
        raw["QQQ"][9] = {**raw["QQQ"][9], "o": flat, "h": flat, "l": flat, "c": flat, "v": -1}
        self.assertEqual(self.check(raw, adj)["checks"]["volume"]["count"], 1, "a flat bar must say volume 0 exactly")

    def test_a_flat_bar_of_volume_zero_is_a_session_without_a_trade_and_passes_listed(self):
        """rehearsal-1: the real history holds such bars, and history never changes, so refusing them failed the
        audit on every run: no store, no Validation, no look, no trade."""
        raw, adj = bars()
        for i in (4, 9):
            flat = raw["QQQ"][i]["c"]
            raw["QQQ"][i] = {**raw["QQQ"][i], "o": flat, "h": flat, "l": flat, "c": flat, "v": 0}
            adj["QQQ"][i] = {**adj["QQQ"][i], "o": flat, "h": flat, "l": flat, "c": flat}
        out = self.check(raw, adj)
        self.assertTrue(out["passed"], out["checks"])
        volume = out["checks"]["volume"]
        self.assertEqual((volume["passed"], volume["count"], volume["problems"]), (True, 0, []))
        self.assertEqual(volume["zero"], {"QQQ": [DAYS[4].isoformat(), DAYS[9].isoformat()]}, "listed, never hidden")

    def test_the_regular_verdict_extended_fails_and_unverified_passes_recorded(self):
        raw, adj = bars()
        extended = {"verdict": "extended", "days": ["2025-03-31"], "compared": 1,
                    "mismatches": [{"day": "2025-03-31", "field": "o", "matches": "extended"}]}
        out = self.check(raw, adj, regular=extended)
        self.assertFalse(out["passed"])
        self.assertEqual(out["checks"]["regular"]["verdict"], "extended")
        out = self.check(raw, adj, regular=None)
        self.assertTrue(out["passed"])
        self.assertEqual(out["checks"]["regular"]["verdict"], "unverified")
        self.assertEqual(out["checks"]["regular"]["count"], 1, "the unverified verdict is recorded as a problem")

    def test_problems_are_listed_at_most_twenty_and_all_counted(self):
        raw, adj = bars()
        for i in range(30):
            raw["SPY"][i] = {**raw["SPY"][i], "v": 0}
        out = self.check(raw, adj)["checks"]["volume"]
        self.assertEqual((len(out["problems"]), out["count"]), (ED.PROBLEMS_LISTED, 30))


# ================================================================================================== fact 1
class TheRegularSession(unittest.TestCase):
    def gateway(self, days, *, daily=None):
        early = dict(CAL)
        mins = {"SPY": [r for d in days for r in minutes(d, early[d])]}
        rows = daily or {"SPY": [session_bar(d, early[d]) for d in days]}
        return Gateway(raw=rows, minute=mins)

    def run_check(self, gw, days):
        with mock.patch("league.equity.store.nyse_sessions", fake_sessions(CAL)):
            return ED.regular_session_check(gw, "SPY", days)

    def test_a_daily_bar_built_from_the_session_is_regular(self):
        days = DAYS[-20:]
        out = self.run_check(self.gateway(days), days)
        self.assertEqual(out["verdict"], "regular", out)
        self.assertEqual((out["compared"], out["mismatches"]), (20, []))

    def cross(self, day, *, base=100.0, low=-0.5, high=2.6):
        """The closing minute of `day` (16:00; 13:00 on a half day), where the closing cross prints."""
        hour = 13 if dict(CAL)[day] else 16
        return {"t": stamp(day, hour, 0), "o": base + 1.25, "h": base + high, "l": base + low, "c": base + 1.3, "v": 9000}

    def test_the_two_crosses_and_the_days_own_volume_are_the_regular_session(self):
        """rehearsal-2: the first rule ended the session before the closing minute and compared the volume, so on real
        bars "regular" could never be the verdict and a close-set high was "extended", which fails the audit."""
        days = DAYS[-20:]
        early = dict(CAL)
        daily, mins = [], []
        for d in days:
            rows = minutes(d, early[d]) + [self.cross(d)]
            mins += sorted(rows, key=lambda r: r["t"])
            bar = session_bar(d, early[d])
            # The open inside the 09:30 minute's range (the opening cross), the close inside the closing minute's and
            # the day's high (a close-set high no earlier minute shows), a volume no sum of minutes gives.
            daily.append({**bar, "o": bar["o"] + 0.4, "c": bar["c"] + 1.2, "h": bar["c"] + 1.2, "v": bar["v"] * 3 + 17})
        gw = Gateway(raw={"SPY": daily}, minute={"SPY": mins})
        out = self.run_check(gw, days)
        self.assertEqual((out["verdict"], out["compared"], out["mismatches"]), ("regular", 20, []), out)
        self.assertEqual((out["extended_days"], out["mismatch_days"]), (0, 0))
        # A close that happens to equal an after-hours print is still the closing minute's: never "extended".
        daily[3] = {**daily[3], "c": 100.0 + 2.6, "h": 100.0 + 2.6}
        after = {"t": stamp(days[3], 17, 30), "o": 102.6, "h": 102.6, "l": 102.6, "c": 102.6, "v": 10}
        gw = Gateway(raw={"SPY": daily}, minute={"SPY": sorted(mins + [after], key=lambda r: r["t"])})
        self.assertEqual(self.run_check(gw, days)["verdict"], "regular")

    def extended_bar(self, bar, day):
        """`bar` with the pre-market's open and low: what a 1Day bar built from the whole day would hold."""
        before = minutes(day, False)[0]
        return {**bar, "o": before["o"], "l": before["l"]}

    def test_more_than_two_days_of_twenty_with_the_extended_days_prices_are_extended(self):
        days = DAYS[-20:]
        early = dict(CAL)
        daily = [session_bar(d, early[d]) for d in days]
        for i in (5, 9, 14):
            daily[i] = self.extended_bar(daily[i], days[i])
        out = self.run_check(self.gateway(days, daily={"SPY": daily}), days)
        self.assertEqual((out["verdict"], out["extended_days"], out["mismatch_days"]), ("extended", 3, 3))
        fields = {(m["field"], m["matches"]) for m in out["mismatches"]}
        self.assertEqual(fields, {("o", "extended"), ("l", "extended")})
        self.assertIn("a stop for E1", out["why"])

    def test_one_or_two_such_days_are_never_regular_and_a_short_reading_allows_none(self):
        days = DAYS[-20:]
        early = dict(CAL)
        daily = [session_bar(d, early[d]) for d in days]
        for n, i in enumerate((5, 9), start=1):
            daily[i] = self.extended_bar(daily[i], days[i])
            out = self.run_check(self.gateway(days, daily={"SPY": daily}), days)
            self.assertEqual((out["verdict"], out["extended_days"]), ("unverified", n), "listed and warned, not a stop")
            self.assertIn(f"{n} of them the extended day's", out["why"])
        # Fewer than REGULAR_DAYS days: one extended day is the verdict (the allowance is the job's full reading).
        short = days[4:9]
        out = self.run_check(self.gateway(short, daily={"SPY": daily[4:9]}), short)
        self.assertEqual((out["verdict"], out["extended_days"]), ("extended", 1))

    def test_a_print_no_minute_shows_is_a_stray_day_two_pass_and_a_missing_day_never(self):
        days = DAYS[-20:]
        early = dict(CAL)
        daily = [session_bar(d, early[d]) for d in days]
        daily[0] = {**daily[0], "c": daily[0]["c"] + 0.07}  # a late print: not the last minute's, no closing minute
        out = self.run_check(self.gateway(days, daily={"SPY": daily}), days)
        self.assertEqual((out["verdict"], out["mismatch_days"], out["extended_days"]), ("regular", 1, 0))
        self.assertEqual((out["mismatches"][0]["field"], out["mismatches"][0]["matches"]), ("c", "neither"))
        self.assertIn("1 of 20 days hold a print no minute bar shows", out["why"])
        daily[7] = {**daily[7], "h": daily[7]["h"] + 0.5}   # a high above every minute, and not the extended day's
        self.assertEqual(self.run_check(self.gateway(days, daily={"SPY": daily}), days)["verdict"], "regular")
        daily[11] = {**daily[11], "l": daily[11]["l"] - 0.5}
        out = self.run_check(self.gateway(days, daily={"SPY": daily}), days)
        self.assertEqual((out["verdict"], out["mismatch_days"]), ("unverified", 3), "a third stray day is not regular")
        gw = self.gateway(days[1:])
        out = self.run_check(gw, days)
        self.assertEqual((out["verdict"], out["compared"]), ("unverified", 19))

    def test_a_high_that_is_only_the_after_hours_high_is_extended(self):
        days = DAYS[-20:]
        early = dict(CAL)
        daily = [session_bar(d, early[d]) for d in days]
        for i in (1, 2, 3):
            daily[i] = {**daily[i], "h": minutes(days[i], False)[-1]["h"]}  # 17:00's high, above every session print
        out = self.run_check(self.gateway(days, daily={"SPY": daily}), days)
        self.assertEqual((out["verdict"], out["extended_days"]), ("extended", 3))
        self.assertEqual({(m["field"], m["matches"]) for m in out["mismatches"]}, {("h", "extended")})

    def test_a_half_days_session_ends_at_13_00(self):
        late = calendar(dt.date(2025, 11, 24), dt.date(2025, 12, 1))
        half = dt.date(2025, 11, 28)
        self.assertTrue(dict(late)[half])
        # An after-hours print at 14:30 with a new high: inside a 16:00 window, outside the half day's session.
        after = {"t": stamp(half, 14, 30), "o": 104.0, "h": 109.0, "l": 103.0, "c": 104.0, "v": 50}
        gw = Gateway(raw={"SPY": [session_bar(half, True)]}, minute={"SPY": sorted(minutes(half, True) + [after],
                                                                                   key=lambda r: r["t"])})
        with mock.patch("league.equity.store.nyse_sessions", fake_sessions(late)):
            out = ED.regular_session_check(gw, "SPY", [half])
        self.assertEqual((out["verdict"], out["compared"]), ("regular", 1))

    def test_a_gateway_error_is_unverified_with_its_reason(self):
        from league.ops.context import GatewayError

        out = self.run_check(Gateway(error=GatewayError("gateway 503", status=503)), DAYS[-3:])
        self.assertEqual(out["verdict"], "unverified")
        self.assertIn("503", out["error"])

    def test_the_days_are_the_last_twenty_with_a_half_day_standing_in(self):
        late = calendar(dt.date(2025, 11, 3), dt.date(2025, 12, 31))
        days = ED.regular_days(late)
        self.assertEqual(len(days), 20)
        self.assertIn(dt.date(2025, 12, 24), days, "a half day among the last twenty stays")
        late = calendar(dt.date(2025, 11, 3), dt.date(2026, 2, 27))
        days = ED.regular_days(late)
        self.assertEqual(days[0], dt.date(2025, 12, 24), "the latest half day stands in for the oldest")
        self.assertEqual(days[1:], [d for d, _ in late][-19:])


# ================================================================================================== the job
class TheJob(unittest.TestCase):
    NOW = dt.datetime(2025, 3, 31, 22, 30, tzinfo=dt.timezone.utc).timestamp()

    def setUp(self):
        import tempfile
        from pathlib import Path

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.alerts = []
        self.written = []

    def ctx(self, gateway):
        return SimpleNamespace(root=self.root, now=lambda: self.NOW, gateway=gateway,
                               alert=lambda level, text: self.alerts.append((level, text)))

    def write_store(self, root, **kwargs):
        self.written.append((root, kwargs))
        return {"version": "equity-store-v1"}

    def data(self, *, spoil=None):
        raw, adj = bars(("SPY", "QQQ"), DAYS + [dt.date(2025, 4, 1)])
        if spoil:
            spoil(raw, adj)
        early = dict(CAL)
        mins = {"SPY": [r for d in DAYS[-20:] for r in minutes(d, early[d])]}
        daily_spy = {ED.ny_day(r["t"]): r for r in raw["SPY"]}
        for d in DAYS[-20:]:
            daily_spy[d] = {**session_bar(d, early[d])}
        raw["SPY"] = [daily_spy[ED.ny_day(r["t"])] for r in raw["SPY"]]
        adj["SPY"] = [dict(r) for r in raw["SPY"]]
        return Gateway(raw=raw, adj=adj, minute=mins, page=50)

    def run_job(self, gw, universe=None):
        with mock.patch("league.equity.store.nyse_sessions", fake_sessions(CAL)), \
                mock.patch("league.equity.store.write_store", self.write_store), \
                mock.patch.object(ED, "universe", lambda constitution=None: universe or {"SPY": "etf", "QQQ": "etf"}):
            return ED.run(self.ctx(gw))

    def test_it_writes_the_audited_store_through_the_core_writer_cut_to_the_last_closed_session(self):
        out = self.run_job(self.data())
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["symbols"], out["sessions"], out["fetched_through"], out["regular"]),
                         (2, len(DAYS), "2025-03-31", "regular"))
        (root, kwargs), = self.written
        self.assertEqual(root, self.root / ED.STORE_DIR)
        self.assertEqual((kwargs["gate"], kwargs["source"], kwargs["fetched_through"]),
                         (True, "alpaca-sip-1Day", dt.date(2025, 3, 31)))
        self.assertEqual(kwargs["calendar"], CAL)
        self.assertEqual(kwargs["classes"], {"SPY": "etf", "QQQ": "etf"})
        spy = kwargs["series"]["SPY"]
        self.assertEqual(spy["days"], DAYS, "the partial bar of a session not closed is dropped")
        self.assertEqual(set(spy), {"days", "raw_o", "raw_h", "raw_l", "raw_c", "raw_v", "all_o", "all_h", "all_l",
                                    "all_c"})
        self.assertTrue(all(len(v) == len(DAYS) for v in spy.values()))
        self.assertTrue(kwargs["audit"]["passed"])
        self.assertEqual(self.alerts, [])
        # The receipt carries counts and verdicts, never a price.
        self.assertEqual(set(out["audit"]["ohlc"]), {"passed", "count"})
        self.assertNotIn(str(round(spy["raw_c"][-1], 2)), json.dumps(out))
        # Both adjustments were fetched from the first day, and the regular check read SPY's minutes.
        gw = self.data()
        self.run_job(gw)
        kinds = {(p["timeframe"], p["adjustment"]) for _, p in gw.calls}
        self.assertEqual(kinds, {("1Day", "raw"), ("1Day", "all"), ("1Min", "raw")})
        self.assertTrue(all(p["start"] == ED.FIRST_DAY for _, p in gw.calls if p["timeframe"] == "1Day"
                            and p["symbols"] == "SPY,QQQ"))

    def test_a_failed_audit_writes_nothing(self):
        def gap(raw, adj):
            raw["QQQ"].pop(12)
            adj["QQQ"].pop(12)

        out = self.run_job(self.data(spoil=gap))
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("calendar", out["error"])
        self.assertEqual(self.written, [])
        # rehearsal-7: the receipt names what failed (the real failure's said a count and nothing else).
        self.assertEqual(set(out["problems"]), {"calendar"})
        self.assertIn("QQQ", out["problems"]["calendar"][0])
        self.assertIn(str(DAYS[12]), " ".join(out["problems"]["calendar"]))

    def test_a_failed_receipt_lists_five_problems_a_check_and_no_figure(self):
        def spoil(raw, adj):
            for i in range(8):
                raw["QQQ"][i] = {**raw["QQQ"][i], "v": None}
            # An adjustment no split explains: its problem text holds the ratio's jump.
            for i in range(30):
                adj["QQQ"][i] = {**adj["QQQ"][i], **{f: adj["QQQ"][i][f] / 2.0 for f in ("o", "h", "l", "c")}}

        out = self.run_job(self.data(spoil=spoil))
        self.assertEqual(out["status"], "failed")
        self.assertEqual(set(out["problems"]), {"volume", "splits"}, "the failed checks, no other")
        self.assertEqual((len(out["problems"]["volume"]), out["audit"]["volume"]["count"]), (ED.RECEIPT_PROBLEMS, 8))
        self.assertIn("QQQ raw 2025-01-02: no volume", out["problems"]["volume"])
        (split,) = out["problems"]["splits"]
        self.assertIn("jumps by #", split, "the ratio is masked")
        self.assertNotRegex(json.dumps(out["problems"]), r"\d\.\d", "symbols, days and verdict words: never a figure")
        self.assertEqual(self.written, [])

    def test_a_gateway_error_writes_nothing(self):
        from league.ops.context import GatewayError

        out = self.run_job(Gateway(error=GatewayError("gateway 503: unavailable", status=503)))
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("unavailable", out["error"])
        self.assertEqual(self.written, [])

    def test_an_unverified_regular_session_is_written_and_warned(self):
        gw = self.data()
        gw.minute = {}
        out = self.run_job(gw)
        self.assertTrue(out["ok"])
        self.assertEqual(out["regular"], "unverified")
        self.assertEqual(len(self.written), 1)
        self.assertEqual(self.alerts[0][0], "warning")
        self.assertIn("fact 1", self.alerts[0][1])

    def test_the_universe_is_the_configs_bounded_by_the_constitution(self):
        from league.equity import config

        self.assertEqual(ED.universe({}), dict(config.UNIVERSE))
        bounded = ED.universe({"equity_money": {"universe": {"etf": ["SPY", "QQQ", "NOPE"], "stock": ["AAPL", "SPY"]}}})
        self.assertEqual(bounded, {"SPY": "etf", "QQQ": "etf", "AAPL": "stock"})

    def test_the_last_closed_session_waits_for_the_close_to_settle(self):
        friday = dt.datetime(2025, 3, 28, 20, 5, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(ED.last_closed(friday), dt.date(2025, 3, 27), "five minutes after the close: not settled")
        self.assertEqual(ED.last_closed(friday + 20 * 60), dt.date(2025, 3, 28))
        self.assertEqual(ED.last_closed(dt.datetime(2025, 3, 30, 12, tzinfo=dt.timezone.utc).timestamp()),
                         dt.date(2025, 3, 28), "a Sunday reads Friday's")


class TheRegistry(unittest.TestCase):
    def test_it_runs_at_start_and_daily_after_the_close_in_a_pause_too(self):
        from league.ops.registry import JOBS, by_name

        self.assertEqual([j.name for j in JOBS].count("equity_data"), 1)
        job = by_name()["equity_data"]
        self.assertEqual((job.module, job.in_pause, job.paid), ("league.ops.equity_data", True, False))
        self.assertEqual([t.kind for t in job.triggers], ["start", "daily"])
        daily = job.triggers[1].at
        self.assertGreater(daily.hour * 60 + daily.minute, 21 * 60 + 5, "after the close and its settling, both seasons")
        names = [j.name for j in JOBS]
        self.assertLess(names.index("direction"), names.index("equity_data"), "the grant and direction still go first")


if __name__ == "__main__":
    unittest.main()
