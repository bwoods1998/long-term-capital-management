"""STEP -1 of release E4: the coverage probe (scripts/panel_probe.py), against a recording fake gateway.

Every bar and every spell here is invented (weekdays as sessions, round invented prices, invented tickers but the two
the probe's fact 1 names): never market data, never a real membership date. What is held: the probe's ONLY request is
a bars GET and NO request names a sealed year (the seal X5 of the release, for the probe: 2020, 2021, 2025, 2026);
ended spells are asked with `asof` inside the spell and open ones with none; coverage is counted as E4-SPEC D19
defines it; the receipt holds counts and shares, never a price and never a ticker; a failed request is tried again
and then makes the verdict "incomplete", never a silent hole.
"""

from __future__ import annotations

import ast
import datetime as dt
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import panel_probe as P

REPO = Path(__file__).resolve().parents[2]
D = dt.date
#: Invented, distinctive prices: none may appear in anything the probe writes.
PRICES = {"SPY": 431.17, "ZZTA": 123.45, "ZZTB": 67.89, "ZZTC": 55.55, "ZZTD": 91.23, "ZZTE": 44.44, "ZZTF": 33.33,
          "FOX": 38.76, "Q": 77.31}
VOLUME = 2_000_000.0


def weekdays(first: dt.date, last: dt.date) -> list[dt.date]:
    out, day = [], first
    while day <= last:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


SESSIONS = [d for first, last in P.ERAS for d in weekdays(first, last)]


def stamp(day: dt.date) -> str:
    return f"{day.isoformat()}T05:00:00Z"


class FakeGateway:
    """A recording fake of the House's gateway client: `get(path, params)` only. `series[(symbol, regime)]` = the days
    the venue has a bar of that symbol; regime "asof" answers a request that names an asof, "today" one that does not
    (the ticker's holder today); a symbol with one regime only answers both. `page` rows a page; `max_symbols`: more
    are refused; `fail`: {request number: error} raised once."""

    def __init__(self, series: dict, *, page: int = 5000, max_symbols: int = 10_000, fail: dict | None = None,
                 honour_asof: bool = True, volumes: dict | None = None):
        self.series, self.page, self.max_symbols = series, int(page), int(max_symbols)
        self.fail = dict(fail or {})
        self.honour_asof = honour_asof
        self.volumes = dict(volumes or {})
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, path, body):  # the probe never posts
        self.calls.append(("POST", path, dict(body or {})))
        raise AssertionError("the probe sent a POST")

    def _days(self, symbol: str, asof: str | None) -> tuple[list[dt.date], str]:
        regime = "asof" if (asof is not None and self.honour_asof) else "today"
        for key in ((symbol, regime), (symbol, "any")):
            if key in self.series:
                return self.series[key], key[1]
        return [], regime

    def get(self, path, params=None):
        params = dict(params or {})
        self.calls.append(("GET", path, params))
        number = len(self.calls)
        if number in self.fail:
            raise self.fail.pop(number)
        symbols = params["symbols"].split(",")
        if len(symbols) > self.max_symbols:
            raise RuntimeError("HTTP 400 too many symbols")
        start, end = D.fromisoformat(params["start"]), D.fromisoformat(params["end"])
        rows = []
        for symbol in sorted(symbols):
            days, regime = self._days(symbol, params.get("asof"))
            price = PRICES.get(symbol, 50.0)
            volume = self.volumes.get((symbol, regime), VOLUME)
            rows.extend((symbol, {"t": stamp(d), "o": price, "h": price, "l": price, "c": price, "v": volume})
                        for d in days if start <= d <= end)
        at = int(params.get("page_token") or 0)
        chunk = rows[at:at + self.page]
        bars: dict = {s: [] for s in symbols} if at == 0 else {}
        for symbol, row in chunk:
            bars.setdefault(symbol, []).append(row)
        answer = {"bars": bars, "next_page_token": str(at + self.page) if at + self.page < len(rows) else None}
        return answer


def world():
    """Invented spells and what the fake venue holds of them."""
    spells = [
        P.Spell("ZZTA", D(2010, 1, 4), None),                    # open, every bar
        P.Spell("ZZTB", D(2012, 3, 1), D(2018, 6, 15)),          # ended in era A, every bar
        P.Spell("ZZTC", D(2014, 1, 2), D(2017, 9, 1)),           # ended, the venue has nothing: no_bars
        P.Spell("ZZTD", D(2019, 6, 3), D(2023, 3, 1)),           # spans the reserve: both eras, asof in era B
        P.Spell("ZZTE", D(2023, 2, 1), None),                    # open, joined in era B
        P.Spell("ZZTF", D(2005, 1, 3), D(2015, 12, 31)),         # ended before the eras: never asked for
        P.Spell("FOX", D(2013, 7, 1), D(2019, 3, 19)),           # the old company under a reused ticker
        P.Spell("FOX", D(2019, 3, 19), None),                    # today's holder of the ticker
        P.Spell("Q", D(2017, 8, 29), D(2017, 11, 15)),           # a short ended spell of a ticker reused since
    ]
    series = {
        ("SPY", "any"): SESSIONS,
        ("ZZTA", "any"): SESSIONS,
        ("ZZTB", "any"): [d for d in SESSIONS if d < D(2018, 6, 15)],
        ("ZZTD", "any"): [d for d in SESSIONS if D(2019, 6, 3) <= d < D(2023, 3, 1)],
        ("ZZTE", "any"): [d for d in SESSIONS if d >= D(2023, 2, 1)],
        ("FOX", "asof"): [d for d in SESSIONS if d < D(2019, 3, 19)],
        ("FOX", "today"): [d for d in SESSIONS if d >= D(2019, 3, 19)],
        ("Q", "asof"): [d for d in SESSIONS if D(2017, 8, 29) <= d < D(2017, 11, 15)],
        ("Q", "today"): [],
    }
    return spells, series


def run(spells, series, **kwargs):
    fake_kwargs = {k: kwargs.pop(k) for k in ("page", "max_symbols", "fail", "honour_asof", "volumes") if k in kwargs}
    gateway = FakeGateway(series, **fake_kwargs)
    waits: list[float] = []
    receipt, listing = P.run(gateway, spells, sleep=waits.append, clock=lambda: 1_760_000_000.0, **kwargs)
    return receipt, listing, gateway, waits


class TheSeal(unittest.TestCase):
    def test_no_request_names_a_sealed_year_and_every_request_is_a_bars_get(self):
        spells, series = world()
        _, _, gateway, _ = run(spells, series)
        self.assertTrue(gateway.calls)
        for method, path, params in gateway.calls:
            self.assertEqual((method, path), ("GET", P.BARS))
            for key in ("start", "end", "asof"):
                if key in params:
                    year = D.fromisoformat(params[key]).year
                    self.assertIn(year, P.YEARS, f"a request's {key} names {year}")
                    self.assertNotIn(year, P.SEALED_YEARS)
            self.assertLessEqual(set(params), {"symbols", "timeframe", "start", "end", "adjustment", "feed", "limit",
                                               "asof", "page_token"})
            self.assertEqual((params["timeframe"], params["adjustment"], params["feed"]), ("1Day", "raw", "sip"))

    def test_a_request_that_would_name_a_sealed_year_is_never_sent(self):
        gateway = FakeGateway({})
        probe = P.Probe(gateway, sleep=lambda s: None)
        for start, end, asof in ((D(2019, 12, 30), D(2020, 1, 3), None), (D(2021, 1, 4), D(2021, 6, 1), None),
                                 (D(2024, 12, 30), D(2025, 1, 3), None), (D(2024, 1, 2), D(2024, 6, 3), D(2026, 10, 9)),
                                 (D(2015, 12, 28), D(2016, 1, 8), None)):
            with self.assertRaises(P.SealedRequest):
                probe.bars(["ZZTA"], start, end, asof=asof)
        self.assertEqual(gateway.calls, [])
        self.assertEqual(probe.requests, 0)

    def test_ended_spells_are_asked_as_of_a_day_inside_them_and_open_spells_name_no_asof(self):
        spells, series = world()
        _, _, gateway, _ = run(spells, series, limit_probe=False)
        ended = {s.ticker: s for s in spells if s.end is not None and s.ticker.startswith("ZZT")}
        asked = {}
        for _, _, params in gateway.calls:
            for symbol in params["symbols"].split(","):
                asked.setdefault(symbol, []).append(params)
        self.assertNotIn("ZZTF", asked, "a spell with no member session in the eras is never asked for")
        for ticker in ("ZZTB", "ZZTC", "ZZTD"):
            for params in asked[ticker]:
                asof = D.fromisoformat(params["asof"])
                self.assertTrue(ended[ticker].start <= asof < ended[ticker].end)
                self.assertEqual(params["symbols"], ticker, "an ended spell goes alone")
        self.assertEqual(len(asked["ZZTD"]), 2, "one request an era for a spell that spans the reserve")
        self.assertEqual({D.fromisoformat(p["start"]).year for p in asked["ZZTD"]}, {2019, 2022})
        for ticker in ("ZZTA", "ZZTE", "SPY"):
            self.assertTrue(all("asof" not in params for params in asked[ticker]))


class TheCount(unittest.TestCase):
    def test_coverage_is_member_sessions_with_a_bar_of_an_accepted_spell(self):
        spells, series = world()
        receipt, listing, _, _ = run(spells, series)
        members = {year: 0 for year in P.YEARS}
        with_bar = {year: 0 for year in P.YEARS}
        for spell in spells:
            for d in P.member_sessions(spell, SESSIONS):
                members[d.year] += 1
                with_bar[d.year] += spell.ticker != "ZZTC"
        for year in P.YEARS:
            row = receipt["by_year"][str(year)]
            self.assertEqual((row["member_days"], row["with_bar"]), (members[year], with_bar[year]), year)
            self.assertAlmostEqual(row["share"], with_bar[year] / members[year], places=6)
            self.assertEqual(receipt["sessions"][str(year)], sum(1 for d in SESSIONS if d.year == year))
        self.assertEqual((receipt["spells"], receipt["open"], receipt["ended"]), (8, 3, 5))
        self.assertEqual((receipt["accepted"], receipt["no_bars"], receipt["reused"], receipt["errors"]), (7, 1, 0, 0))
        self.assertEqual(listing, {"no_bars": ["ZZTC"], "reused": [], "error": []})
        self.assertFalse(receipt["pass"])
        self.assertEqual(receipt["verdict"], "fail", "2016 and 2017 hold a member with no bar")
        self.assertEqual(receipt["facts"]["1"]["verdict"], "holds")
        self.assertEqual(receipt["facts"]["1"]["asof_differs"], 2, "both test names answer differently without asof")
        self.assertEqual((receipt["facts"]["1"]["test_spells"], receipt["facts"]["1"]["test_accepted"]), (2, 2))

    def test_a_full_panel_passes(self):
        spells, series = world()
        spells = [s for s in spells if s.ticker != "ZZTC"]
        receipt, _, _, _ = run(spells, series)
        self.assertTrue(receipt["pass"])
        self.assertEqual(receipt["verdict"], "pass")
        self.assertTrue(all(row["share"] == 1.0 for row in receipt["by_year"].values()))

    def test_the_end_day_is_no_member_day_and_a_bar_needs_a_close_and_a_volume(self):
        spell = P.Spell("ZZTB", D(2018, 6, 11), D(2018, 6, 15))
        self.assertEqual(P.member_sessions(spell, SESSIONS), weekdays(D(2018, 6, 11), D(2018, 6, 14)))
        gateway = FakeGateway({("ZZTA", "any"): SESSIONS[:3]}, volumes={("ZZTA", "any"): 0.0})
        self.assertEqual(P.Probe(gateway).bars(["ZZTA"], SESSIONS[0], SESSIONS[9]), {"ZZTA": {}},
                         "the vendor's flat bar of volume 0 is no valid bar")

    def test_the_acceptance_rule(self):
        members = SESSIONS[:100]
        bar = (50.0, VOLUME)
        self.assertEqual(P.judge(members, {d: bar for d in members}), "ok")
        self.assertEqual(P.judge(members, {d: bar for d in members[5:]}), "ok", "exactly 95%, first bar 5 sessions in")
        self.assertEqual(P.judge(members, {d: bar for d in members[6:]}), "no_bars", "94%")
        self.assertEqual(P.judge(members, {d: bar for d in members[:94]}), "no_bars")
        late = {d: bar for d in members[6:]} | {d: bar for d in SESSIONS[100:140]}
        self.assertEqual(P.judge(SESSIONS[:140], late), "no_bars", "its first bar is more than 5 sessions late")
        self.assertEqual(P.judge(members, {}), "no_bars")
        self.assertEqual(P.judge(members, {d: (2.0, 1000.0) for d in members}), "reused",
                         "a full series that trades $2,000 a day is another company's")

    def test_a_venue_that_ignores_asof_shows_as_a_reused_ticker_and_fact_1_fails(self):
        spells, series = world()
        series[("Q", "today")] = series[("Q", "asof")]
        receipt, listing, _, _ = run(spells, series, honour_asof=False, volumes={("Q", "today"): 1000.0})
        self.assertIn("Q", listing["reused"])
        self.assertIn("FOX", listing["no_bars"], "today's holder has no bar in the old spell")
        self.assertEqual(receipt["facts"]["1"]["verdict"], "fails")
        self.assertEqual(receipt["facts"]["1"]["asof_differs"], 0)

    def test_no_test_name_in_the_file_is_said_so(self):
        spells, series = world()
        receipt, _, _, _ = run([s for s in spells if s.ticker.startswith("ZZT")], series)
        self.assertEqual(receipt["facts"]["1"]["verdict"], "not_met")


class TheGateway(unittest.TestCase):
    def test_every_page_is_read(self):
        spells, series = world()
        whole, _, one, _ = run(spells, series, limit_probe=False)
        paged, _, many, _ = run(spells, series, limit_probe=False, page=700)
        self.assertGreater(len(many.calls), len(one.calls))
        self.assertTrue(any("page_token" in params for _, _, params in many.calls))
        self.assertEqual(paged["by_year"], whole["by_year"])

    def test_a_failed_request_is_tried_again_with_a_wait(self):
        spells, series = world()
        receipt, _, gateway, waits = run(spells, series, limit_probe=False, fail={4: RuntimeError("HTTP 502")})
        clean, _, _, _ = run(spells, series, limit_probe=False)
        self.assertEqual(waits, [P.BACKOFF_S[0]])
        self.assertEqual(receipt["by_year"], clean["by_year"])
        self.assertEqual((receipt["errors"], receipt["requests_failed"]), (0, 0))
        self.assertEqual(receipt["requests"], clean["requests"] + 1)

    def test_a_request_that_keeps_failing_makes_the_verdict_incomplete(self):
        spells, series = world()
        spells = [s for s in spells if s.ticker != "ZZTC"]
        clean, _, calm, _ = run(spells, series, limit_probe=False)
        first = next(i for i, (_, _, p) in enumerate(calm.calls, start=1) if p["symbols"] == "ZZTB")
        fail = {first + k: RuntimeError("HTTP 502") for k in range(P.TRIES)}
        receipt, listing, _, waits = run(spells, series, limit_probe=False, fail=fail)
        self.assertEqual(waits, list(P.BACKOFF_S))
        self.assertEqual((receipt["errors"], receipt["requests_failed"]), (1, 1))
        self.assertEqual(listing["error"], ["ZZTB"])
        self.assertEqual((clean["verdict"], receipt["verdict"]), ("pass", "incomplete"))
        self.assertLess(receipt["by_year"]["2016"]["share"], 1.0, "a spell in error counts as no bar, never as covered")

    def test_fact_10_reads_how_many_symbols_a_request_takes(self):
        spells = [P.Spell(f"ZZ{i:03d}", D(2010, 1, 4), None) for i in range(120)]
        series = {("SPY", "any"): SESSIONS, **{(s.ticker, "any"): SESSIONS[-30:] for s in spells}}
        spells = [P.Spell(s.ticker, SESSIONS[-30], None) for s in spells]
        receipt, _, gateway, _ = run(spells, series, max_symbols=60)
        self.assertEqual(receipt["facts"]["10"], {"asked": [39, 100], "answered": [39], "largest_ok": 39,
                                                  "first_refused": 100})
        self.assertEqual(receipt["requests_failed"], 0, "a refused ladder step is the datum, not a failed request")
        self.assertTrue(all(len(p["symbols"].split(",")) <= P.BATCH for _, _, p in gateway.calls[:-1]),
                        "the probe's own requests never depend on the limit it is measuring")
        self.assertEqual(run(spells, series, limit_probe=False)[0]["facts"]["10"], "not probed (--no-limit-probe)")

    def test_no_calendar_stops_the_probe(self):
        spells, series = world()
        with self.assertRaises(P.ProbeStopped):
            run(spells, {k: v for k, v in series.items() if k[0] != "SPY"})

    def test_the_request_cap_stops_the_probe(self):
        spells, series = world()
        with self.assertRaises(P.ProbeStopped):
            run(spells, series, max_requests=3)


class TheReceipt(unittest.TestCase):
    def _main(self, extra=(), **kwargs):
        spells, series = world()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "spells.csv"
            source.write_text("ticker,start_date,end_date\n" + "".join(
                f"{s.ticker},{s.start.isoformat()},{s.end.isoformat() if s.end else ''}\n" for s in spells))
            out = io.StringIO()
            gateway = FakeGateway(series, **kwargs)
            code = P.main(["--spells", str(source), "--root", str(Path(tmp) / "state"), "--pause", "0", *extra],
                          gateway=gateway,
                          sleep=lambda s: None, clock=lambda: 1_760_000_000.0, out=out)
            path = Path(tmp) / "state" / P.STORE_DIR / P.RECEIPT
            written = path.read_text() if path.exists() else None
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
            return code, out.getvalue(), written, mode, spells

    def test_counts_and_shares_out_never_a_price_and_never_a_ticker(self):
        code, printed, written, mode, spells = self._main()
        self.assertEqual(code, 1, "the invented panel has a member with no bars: fail")
        self.assertEqual(mode, 0o600)
        receipt = json.loads(written)
        self.assertEqual(receipt["version"], P.VERSION)
        self.assertEqual(json.loads(printed)["by_year"], receipt["by_year"])
        tickers = {s.ticker for s in spells} | {"SPY"}

        def walk(value, path="receipt"):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertNotIn(key, tickers, f"{path} names a ticker")
                    walk(item, f"{path}.{key}")
            elif isinstance(value, list):
                for item in value:
                    walk(item, path)
            elif isinstance(value, str):
                self.assertNotIn(value, tickers, f"{path} names a ticker")
            elif isinstance(value, float):
                self.assertTrue(0.0 <= value <= 1.0, f"{path} holds a float that is no share: {value}")

        walk(receipt)
        for text in (printed, written):
            for price in PRICES.values():
                self.assertNotIn(str(price), text)
            self.assertNotIn(str(int(VOLUME)), text)

    def test_the_listing_is_asked_for_and_stays_on_the_terminal(self):
        code, printed, written, _, _ = self._main(["--list"])
        self.assertEqual(code, 1)
        self.assertIn("no_bars (1): ZZTC", printed)
        self.assertNotIn("ZZTC", written)

    def test_no_write_writes_nothing(self):
        code, printed, written, _, _ = self._main(["--no-write", "--no-limit-probe"])
        self.assertIsNone(written)
        self.assertEqual(json.loads(printed)["verdict"], "fail")

    def test_an_unreadable_spell_file_is_refused(self):
        self.assertEqual(P.main(["--spells", "/nonexistent/spells.csv", "--no-write"], gateway=FakeGateway({})), 2)
        for bad in ("ticker,start_date,end_date\n", "ZZTA\n", "ZZTA,2016-13-01,\n", "ZZTA,2018-01-02,2017-01-03\n",
                    "ZZTA,2016-01-04,,x,y\n"):
            with self.assertRaises(ValueError):
                P.parse_spells(bad)
        self.assertEqual(P.parse_spells("ticker,start_date,end_date\nzzta,2016-01-04,\n\nZZTB,2012-03-01,2018-06-15\n"),
                         [P.Spell("ZZTA", D(2016, 1, 4), None), P.Spell("ZZTB", D(2012, 3, 1), D(2018, 6, 15))])


class TheScript(unittest.TestCase):
    def test_standard_library_only_and_nothing_of_the_panel_package(self):
        tree = ast.parse((REPO / "scripts" / "panel_probe.py").read_text())
        top, inner = set(), set()
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            (top if getattr(node, "col_offset", 1) == 0 else inner).update(names)
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        self.assertLessEqual({n.split(".")[0] for n in top}, stdlib, "a module-level import outside the standard library")
        self.assertEqual(inner, {"league.ops.context", "league.service"},
                         "the running release's gateway client and its own environment loader, and nothing else")
        self.assertFalse(any(n.startswith("league.xs") or n.startswith("numpy") for n in top | inner))

    def test_the_gateway_client_is_the_running_releases_own_and_building_it_asks_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"LEAGUE_ENV": str(Path(tmp) / ".env")}):
            os.environ.pop("GATEWAY_TOKEN", None)  # no token here: the client is built, and asked nothing
            gateway = P.house_gateway(REPO, Path(tmp) / "state")
            from league.ops.context import Gateway

            self.assertIsInstance(gateway, Gateway)
            self.assertEqual(gateway.calls, [])
            self.assertNotIn("GATEWAY_TOKEN", os.environ)

    def test_the_command_waits_before_every_request(self):
        spells, series = world()
        gateway = FakeGateway(series)
        waits: list[float] = []
        receipt, _ = P.run(gateway, spells, sleep=waits.append, clock=lambda: 0.0, pause=0.25, limit_probe=False)
        self.assertEqual(waits, [0.25] * receipt["requests"])
        self.assertEqual(P.default_release(), str(REPO), "in a checkout the release is the checkout")

    def test_the_probe_years_are_the_panels_train_era_and_no_sealed_year(self):
        self.assertEqual(P.YEARS, (2016, 2017, 2018, 2019, 2022, 2023, 2024))
        self.assertFalse(set(P.YEARS) & set(P.SEALED_YEARS))
        self.assertEqual({d.year for era in P.ERAS for d in era}, {2016, 2019, 2022, 2024})
        from league.xs import config

        self.assertEqual(set(P.YEARS), set(config.TRAIN_YEARS) | {2016})
        self.assertEqual(P.COVERAGE_MIN, 0.97)


if __name__ == "__main__":
    unittest.main()
