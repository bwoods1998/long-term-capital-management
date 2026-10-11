"""RELEASE E4, PACKAGE A: the `equity_panel` job (league/ops/equity_panel.py): the panel's bars through the venue's
`asof`, the store's vintage rule within the vendor's cents, D19 (what is a valid bar, what may mask a member, the
second read of a big move, coverage and its verdict), D20's half-spread table, the nightly I6, and SEAL X5: 2020 is
never fetched.

EVERYTHING HERE IS FAKE: a made-up venue (`Market`) of made-up companies with made-up tickers and arithmetic prices
stands for Alpaca behind a recording gateway. No market row, no price of a real year and no membership history is in
this file or read by it.
"""

from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import inspect
import json
import math
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import numpy as np

from league.equity import store as eq_store
from league.ops import equity_data
from league.ops import equity_panel as P
from league.ops import equity_universe as U
from league.ops.context import Context, GatewayError
from league.xs import book as xs_book
from league.xs import config as xs_config
from league.xs import ctx as xs_ctx
from league.xs import program as xs_program
from league.xs import store as xs_store

D = dt.date
NEW_YORK = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]
#: Friday 2022-04-01 01:45Z: Thursday 2022-03-31's session is closed and settled, and no wall is near.
NOW = dt.datetime(2022, 4, 1, 1, 45, tzinfo=dt.timezone.utc).timestamp()
LAST = D(2022, 3, 31)
DAY = 86400.0
VENUE_OK = {"id": "fake", "status": "active", "tradable": True, "fractionable": True, "exchange": "FAKE"}


def stamp(day: dt.date) -> str:
    """A daily bar's time as the venue writes it: New York midnight, in UTC."""
    moment = dt.datetime.combine(day, dt.time(0), NEW_YORK).astimezone(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class Company:
    """One made-up company of the made-up venue: arithmetic prices on the cent grid (a slow sawtooth around `base`),
    listed from `first` to `last`, known under `tickers` [(ticker, from, to | None)]. `dividends` {ex-day: dollars},
    `splits` {day: ratio}, `crash` {day: factor on the raw close from that day}, `volume` shares a session,
    `flat` (sessions without a trade: a flat bar of volume 0), `bad` (sessions whose bar is not sane), `minute_gap`
    {day: how far the minute bars' last price sits from the daily close}."""

    def __init__(self, name: str, tickers, *, base: float = 50.0, first: dt.date = D(2010, 1, 4),
                 last: dt.date | None = None, dividends=None, splits=None, crash=None, volume: float = 1_000_000.0,
                 flat=(), bad=(), minute_gap=None):
        self.name, self.tickers, self.base, self.first, self.last = name, list(tickers), float(base), first, last
        self.dividends, self.splits, self.crash = dict(dividends or {}), dict(splits or {}), dict(crash or {})
        self.volume, self.flat, self.bad, self.minute_gap = float(volume), set(flat), set(bad), dict(minute_gap or {})
        self.seed = sum(ord(c) * (k + 1) for k, c in enumerate(name))

    def known_as(self, ticker: str, day: dt.date) -> bool:
        return any(t == ticker and start <= day and (end is None or day < end) for t, start, end in self.tickers)

    def raw(self, day: dt.date, k: int) -> tuple[float, float, float, float, float]:
        """(o, h, l, c, v) of session number k (the calendar's count), unadjusted, on the cent grid."""
        level = self.base * (1.0 + 0.10 * (((k + self.seed) % 40) / 40.0 - 0.5))
        for at, factor in self.crash.items():
            if day >= at:
                level *= factor
        for at, ratio in self.splits.items():
            if day >= at:
                level /= ratio
        close = round(level, 2)
        if day in self.flat:
            return close, close, close, close, 0.0
        open_ = round(close * (1.0 + 0.002 * ((k + self.seed) % 3 - 1)), 2)
        high, low = round(max(open_, close) + 0.05, 2), round(min(open_, close) - 0.05, 2)
        if day in self.bad:
            low = round(high + 1.0, 2)  # a low above its high: no sane bar
        return open_, high, low, close, self.volume + 1000.0 * ((k + self.seed) % 7)


class Market:
    """The made-up venue behind the gateway: `companies`, and `today` (the day the adjustment=all series is as of:
    every dividend and split with an ex-day on or before it restates all earlier bars, each price ROUNDED TO THE CENT,
    as the real vendor serves them). It answers `GET /v1/alpaca/v2/stocks/bars` like the venue: `symbols`, `start`,
    `end`, `timeframe` 1Day | 1Min, `adjustment`, `asof` (which company a ticker meant on that day; today's with
    none), `limit` and a page token. Every request's parameters are recorded."""

    def __init__(self, companies, *, today: dt.date = LAST, page: int = 10000):
        self.companies = list(companies)
        self.today = today
        self.page = page
        self.requests: list[dict] = []
        self.fail: list[BaseException] = []
        self.fail_when = None
        self.sessions = [d for d, _ in eq_store.nyse_sessions(D(2016, 1, 4), D(2022, 12, 30))]
        self.number = {d: k for k, d in enumerate(self.sessions)}
        self.stamps = [stamp(d) for d in self.sessions]
        self.calls: list[tuple] = []
        self._bars: dict[str, tuple] = {}

    # -- the venue
    def resolve(self, ticker: str, asof: dt.date) -> Company | None:
        for company in self.companies:
            if company.known_as(ticker, asof):
                return company
        return None

    def factor(self, company: Company, day: dt.date) -> float:
        """What adjustment=all multiplies the raw prices of `day` by, as of `today`."""
        out = 1.0
        for at, dollars in company.dividends.items():
            if day < at <= self.today:
                before = company.raw(self.sessions[self.number[at] - 1], self.number[at] - 1)[3]
                out *= 1.0 - dollars / before
        for at, ratio in company.splits.items():
            if day < at <= self.today:
                out /= ratio
        return out

    def tape(self, company: Company) -> list[tuple]:
        """The company's raw bars by session number, built once for the state it is in (a test may change it)."""
        state = (company.base, company.volume, company.first, company.last, tuple(sorted(company.crash.items())),
                 tuple(sorted(company.splits.items())), tuple(sorted(company.flat)), tuple(sorted(company.bad)))
        held = self._bars.get(company.name)
        if held is None or held[0] != state:
            held = (state, [company.raw(day, k) for k, day in enumerate(self.sessions)])
            self._bars[company.name] = held
        return held[1]

    def daily(self, company: Company, start: dt.date, end: dt.date, adjustment: str) -> list[dict]:
        rows = []
        tape = self.tape(company)
        last = min(end, self.today) if company.last is None else min(end, self.today, company.last)
        first = max(start, company.first)
        restated = adjustment == "all" and (company.dividends or company.splits)
        for k in range(bisect.bisect_left(self.sessions, first), bisect.bisect_right(self.sessions, last)):
            o, h, l, c, v = tape[k]
            if restated:
                f = self.factor(company, self.sessions[k])
                o, h, l, c = (round(x * f, 2) for x in (o, h, l, c))
            rows.append({"t": self.stamps[k], "o": o, "h": h, "l": l, "c": c, "v": v, "n": 1, "vw": c})
        return rows

    def minutes(self, company: Company, start: str, end: str) -> list[dict]:
        first = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        last = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
        day = first.astimezone(NEW_YORK).date()
        if day not in self.number or day < company.first or (company.last is not None and day > company.last):
            return []
        close = company.raw(day, self.number[day])[3] * (1.0 + company.minute_gap.get(day, 0.0))
        rows, at = [], first
        while at <= last:
            price = round(close * (1.0 + 0.0001 * ((last - at).seconds // 60 % 5)), 2)
            rows.append({"t": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": price, "h": price, "l": price, "c": price,
                         "v": 100.0})
            at += dt.timedelta(minutes=1)
        return rows

    def get(self, path: str, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path.startswith(U.ASSETS):
            raise GatewayError("GET: HTTP 404", status=404)
        assert path == P.BARS, path
        self.requests.append(params)
        if self.fail:
            raise self.fail.pop(0)
        if self.fail_when is not None and self.fail_when(params):
            raise GatewayError("GET /v1/alpaca/v2/stocks/bars: HTTP 500 a fake outage", status=500)
        asof = D.fromisoformat(params["asof"]) if params.get("asof") else self.today
        rows: list[tuple[str, dict]] = []
        for symbol in params["symbols"].split(","):
            company = self.resolve(symbol, asof)
            if company is None:
                continue
            if params["timeframe"] == "1Min":
                found = self.minutes(company, params["start"], params["end"])
            else:
                found = self.daily(company, D.fromisoformat(params["start"][:10]), D.fromisoformat(params["end"][:10]),
                                   params["adjustment"])
            rows.extend((symbol, row) for row in found)
        size = min(int(params.get("limit", 10000)), self.page)
        at = int(params.get("page_token") or 0)
        out: dict[str, list] = {}
        for symbol, row in rows[at:at + size]:
            out.setdefault(symbol, []).append(row)
        return {"bars": out, "next_page_token": str(at + size) if at + size < len(rows) else None}

    def post(self, path: str, body):
        raise AssertionError("the panel job never asks the reader")

    # -- what the tests read
    def days_named(self) -> list[str]:
        return [str(p[key])[:10] for p in self.requests for key in ("start", "end", "asof") if p.get(key)]


def ref_companies() -> list[Company]:
    out = []
    for k, symbol in enumerate(xs_config.REF):
        first = D(2018, 6, 19) if symbol == "XLC" else D(2010, 1, 4)
        out.append(Company(f"ref-{symbol}", [(symbol, D(2000, 1, 3), None)], base=40.0 + 7 * k, first=first))
    return out


def index(n: int = 24):
    """A made-up index: `n` members from 2010 (QAAA...), their companies, and the spells."""
    names = ["Q" + "".join(chr(ord("A") + (k // 26 ** p) % 26) for p in (2, 1, 0)) for k in range(n)]
    companies = [Company(f"co-{t}", [(t, D(2000, 1, 3), None)], base=30.0 + 3 * k) for k, t in enumerate(names)]
    spells = [(t, D(2010, 1, 4), None) for t in names]
    return names, companies, spells


def reference_writer(root, *, days, early, aids, raw, adj, member, tradable, hs, fetched_through, vintage, audit,
                     masked=None, coverage=None, vanished=None, full_at=None, revisions=0, hs_share=None,
                     live_from=None, i6=None):
    """`league.xs.store.write_panel`'s layout and manifest, for a tree that has not package C's C0 yet (the tests use
    the real writer the day it is there: `writer`)."""
    folder = Path(root) / xs_store.PANEL_DIR
    folder.mkdir(parents=True, exist_ok=True)
    days = list(days)
    if any(d.year in xs_config.RESERVE_YEARS for d in days):
        raise ValueError("2020 is never in the panel store")
    arrays = {"days": np.array([eq_store.ordinal(d) for d in days], dtype=np.int32), "early": np.asarray(early, dtype=bool),
              "aids": np.asarray(aids, dtype=np.int32), "raw": np.asarray(raw, dtype=np.float64),
              "adj": np.asarray(adj, dtype=np.float64), "member": np.asarray(member, dtype=bool),
              "tradable": np.asarray(tradable, dtype=bool), "hs": np.asarray(hs, dtype=np.float64)}
    shas = {}
    for name, array in arrays.items():
        with open(folder / f".{name}.tmp", "wb") as handle:
            np.save(handle, array, allow_pickle=False)
        (folder / f".{name}.tmp").replace(folder / f"{name}.npy")  # renamed over: a reader's map keeps the old file
        shas[f"{name}.npy"] = hashlib.sha256((folder / f"{name}.npy").read_bytes()).hexdigest()
    block = coverage or P.coverage(arrays["member"], arrays["raw"], days, masked=masked)
    valid = P.valid_bars(arrays["raw"])
    gone = []
    for k in range(len(xs_config.REF), len(aids)):
        hits = np.flatnonzero(valid[:, k])
        if hits.size and int(arrays["member"][hits[-1] + 1:, k].sum()) >= xs_config.VANISH_SESSIONS:
            gone.append(int(aids[k]))
    manifest = {"version": "xs-panel-v1", "fetched_through": days[-1].isoformat(),
                "full_at": None if full_at is None else full_at.isoformat(), "sha256": shas, "days": len(days),
                "assets": len(aids), "first": days[0].isoformat(),
                "vintage": {str(int(a)): d.isoformat() for a, d in dict(vintage).items()},
                "coverage": block["coverage"], "train_years_ok": block["train_years_ok"], "verdict": block["verdict"],
                "vanished": gone if vanished is None else sorted(vanished),
                "audit": json.loads(json.dumps(dict(audit), default=str)),
                "i6": None if i6 is None else json.loads(json.dumps(dict(i6), default=str)), "revisions": int(revisions),
                "hs_share": hs_share, "live_from": None if live_from is None else live_from.isoformat()}
    (folder / "PANEL_MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, indent=1))
    return manifest


def writer():
    """The store's writer the job is run against: package C's own once C0 is in the tree (its signature then has the
    manifest keywords), else the reference above."""
    return xs_store.write_panel if "coverage" in inspect.signature(xs_store.write_panel).parameters else reference_writer


def write_universe(root: Path, spells, *, joins=(), exits=None, masks=None) -> dict:
    """A universe on disk as the membership job leaves it (assets.json, tradable.json, SOURCE.json, the manifest, the
    salt), without running that job."""
    venue = {t: dict(VENUE_OK) for t, _, _ in spells}
    table = U.assign(spells, None, joins, exits=exits or {}, venue=venue)
    for aid, mask in (masks or {}).items():
        table[str(aid)]["masked"] = mask
    U.ensure_salt(root)
    U._publish(root, files={U.SOURCE_FILE: U._json_bytes({"commit": "0" * 40}),
                            U.SPELLS_FILE: U._spells_csv(spells, set(spells)), U.ASSETS_FILE: U._json_bytes(table),
                            U.TRADABLE_FILE: U._json_bytes({"as_of": LAST.isoformat(), "stock": U.tradable(table, LAST)})},
               manifest={"version": xs_store.UNIVERSE_VERSION, "audit": {"passed": True}})
    return table


def aid_of(table: dict, ticker: str) -> int:
    return next(int(aid) for aid, row in table.items() if any(s[0] == ticker for s in row["spells"])
                or (row["ref"] and row["symbol"] == ticker))


class Fixture(unittest.TestCase):
    """A state directory, the made-up venue, a universe on disk, the quiet windows open and a store writer."""

    N = 24
    EXTRA_COMPANIES: tuple = ()
    EXTRA_SPELLS: tuple = ()
    JOINS: tuple = ()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        (self.state / "swarm.json").write_text('{"elane": {"panel": {"mode": "train"}}}', encoding="utf-8")   # the lane's switch is up
        self.root = self.state / U.STORE_DIR
        self.names, companies, spells = index(self.N)
        self.spells = [*spells, *self.EXTRA_SPELLS]
        self.market = Market([*ref_companies(), *companies, *self.EXTRA_COMPANIES])
        self.table = write_universe(self.root, self.spells, joins=self.JOINS)
        for target, value in ((xs_config, {"quiet": mock.Mock(return_value=None)}),
                              (xs_store, {"write_panel": writer()})):
            for name, fake in value.items():
                patch = mock.patch.object(target, name, fake)
                patch.start()
                self.addCleanup(patch.stop)

    def ctx(self, now: float = NOW, settings=None) -> Context:
        return Context("equity_panel", root=self.state, due_at=now, clock=lambda: now, gateway=self.market, config={},
                       settings_value=settings or {})

    def run_job(self, now: float = NOW, **kw):
        ctx = self.ctx(now, **kw)
        return P.run(ctx, sleep=lambda s: None), ctx

    def panel(self) -> P.Panel:
        """The store as it is now, its arrays copied out of the files."""
        panel = P.load_panel(self.root)
        for name in ("raw", "adj"):
            setattr(panel, name, np.array(getattr(panel, name)))
        return panel

    def column(self, panel: P.Panel, ticker: str) -> int:
        return panel.aids.index(aid_of(U.read_universe(self.root)["assets"], ticker))


# ================================================================================================ SEAL X5
class NeverFetches2020(Fixture):
    """SEAL X5: `fetch_asof` raises on a span touching 2020; the job's requests name none."""

    ENDED = Company("co-QEND", [("QEND", D(2000, 1, 3), None)], base=44.0)
    ONLY_2020 = Company("co-QRES", [("QRES", D(2000, 1, 3), None)], base=61.0)
    EXTRA_COMPANIES = (ENDED, ONLY_2020)
    EXTRA_SPELLS = (("QEND", D(2012, 5, 1), D(2020, 6, 1)), ("QRES", D(2020, 2, 3), D(2020, 11, 2)),
                    ("QBCK", D(2019, 9, 3), D(2021, 3, 1)))

    def test_fetch_asof_refuses_a_span_or_an_asof_touching_2020_and_sends_nothing(self):
        for start, end, asof in (("2019-12-30", "2021-01-05", None), ("2020-01-02", "2020-01-31", None),
                                 ("2019-06-03", "2020-01-02", None), ("2020-12-31", "2021-02-01", None),
                                 ("2019-06-03", "2019-12-31", "2020-06-01"), ("2020-03-02T13:30:00Z",
                                                                             "2020-03-02T20:00:00Z", None)):
            with self.assertRaises(ValueError) as caught:
                P.fetch_asof(self.market, ["SPY"], start, end, adjustment="raw", asof=asof)
            self.assertIn("2020 is never fetched", str(caught.exception))
        self.assertEqual(self.market.requests, [], "the request is not sent")
        rows = P.fetch_asof(self.market, ["SPY"], "2019-12-30", "2019-12-31", adjustment="raw", asof="2019-12-31")
        self.assertEqual(len(rows["SPY"]), 2)

    def test_no_request_of_a_whole_run_a_daily_run_and_the_i6_names_a_2020_day(self):
        first, _ = self.run_job()
        self.assertTrue(first.get("ok"), first)
        self.assertEqual(first["mode"], "full")
        whole = len(self.market.requests)
        self.market.today = D(2022, 4, 1)
        second, _ = self.run_job(NOW + DAY)
        self.assertEqual((second.get("ok"), second["mode"]), (True, "incremental"))
        self.assertGreater(len(self.market.requests), whole)
        self.assertTrue(self.market.days_named())
        for day in self.market.days_named():
            self.assertNotEqual(day[:4], "2020", day)
        for params in self.market.requests:
            first_year, last_year = int(params["start"][:4]), int(params["end"][:4])
            self.assertFalse(first_year <= 2020 <= last_year, params)
        panel = self.panel()
        self.assertFalse(any(d.year == 2020 for d in panel.days), "and no 2020 row is in the store")

    def test_a_spell_that_lies_only_in_2020_is_never_asked_for_and_one_across_it_is_asked_on_both_sides(self):
        self.run_job()
        asked = {s for p in self.market.requests for s in p["symbols"].split(",")}
        self.assertNotIn("QRES", asked)
        ended = [p for p in self.market.requests if p["symbols"] == "QEND"]
        self.assertTrue(ended)
        self.assertEqual({p["asof"] for p in ended}, {"2019-12-31"}, "its last member session the store can hold")
        self.assertEqual({(p["start"], p["end"]) for p in ended}, {("2016-01-04", "2019-12-31")})
        across = [p for p in self.market.requests if p["symbols"] == "QBCK" and p["adjustment"] == "raw"]
        self.assertEqual([(p["start"][:4], p["end"][:4], p["asof"]) for p in across],
                         [("2018", "2019", "2021-02-26"), ("2021", "2021", "2021-02-26")])

    def test_the_plan_lies_inside_the_spans(self):
        days = [d for d, _ in U.store_sessions(LAST)]
        plan = P.plan(self.table, days)
        self.assertTrue(plan)
        for asof, symbols, start, end in plan:
            self.assertEqual(start[:4] <= "2019", end[:4] <= "2019", (start, end))
            self.assertNotIn("2020", (start[:4], end[:4], str(asof)[:4]))


# ================================================================================================ the gateway
class FetchAsof(Fixture):
    def test_every_page_every_symbol_a_key_and_the_asof_only_when_given(self):
        self.market.page = 7
        rows = P.fetch_asof(self.market, ["SPY", "QAAA", "QNONE"], "2019-12-02", "2019-12-31", adjustment="all", asof=None)
        self.assertEqual({k: len(v) for k, v in rows.items()}, {"SPY": 21, "QAAA": 21, "QNONE": 0})
        self.assertEqual(len(self.market.requests), 6)
        self.assertTrue(all("asof" not in p for p in self.market.requests), "today's asof: the parameter is left out")
        self.assertEqual([p.get("page_token") for p in self.market.requests], [None, "7", "14", "21", "28", "35"])
        self.assertEqual({(p["timeframe"], p["adjustment"], p["feed"], p["limit"]) for p in self.market.requests},
                         {("1Day", "all", "sip", P.PAGE_LIMIT)})
        days = [equity_data.ny_day(r["t"]) for r in rows["QAAA"]]
        self.assertEqual(days, sorted(days))
        self.assertEqual(set(rows["QAAA"][0]), {"t", "o", "h", "l", "c", "v"})
        self.market.requests.clear()
        P.fetch_asof(self.market, ["QAAA"], "2019-12-02", "2019-12-31", adjustment="raw", asof="2019-12-16")
        self.assertEqual(self.market.requests[0]["asof"], "2019-12-16")

    def test_a_call_is_tried_three_times_backing_off_five_then_twenty_seconds(self):
        waits, count = [], {"calls": 0, "failed": 0}
        self.market.fail = [GatewayError("HTTP 429", status=429), GatewayError("HTTP 500", status=500)]
        rows = P.fetch_asof(self.market, ["SPY"], "2019-12-30", "2019-12-31", adjustment="raw", asof=None,
                            sleep=waits.append, count=count)
        self.assertEqual((len(rows["SPY"]), waits, count), (2, [5, 20], {"calls": 3, "failed": 0}))
        self.market.fail = [GatewayError("HTTP 500 a secret-free text", status=500)] * 3
        waits.clear()
        with self.assertRaises(RuntimeError) as caught:
            P.fetch_asof(self.market, ["SPY"], "2019-12-30", "2019-12-31", adjustment="raw", asof=None,
                         sleep=waits.append, count=count)
        self.assertEqual((waits, count), ([5, 20], {"calls": 6, "failed": 1}))
        self.assertIn("failed 3 times", str(caught.exception))

    def test_a_malformed_answer_is_a_value_error(self):
        for answer in ({}, {"bars": []}, {"bars": {"SPY": "rows"}}, {"bars": {"SPY": [{"o": 1}]}},
                       {"bars": {"SPY": [{"t": "2019-12-30T05:00:00Z"}, {"t": "2019-12-30T05:00:00Z"}]}}):
            gateway = mock.Mock()
            gateway.get.return_value = answer
            with self.assertRaises(ValueError):
                P.fetch_asof(gateway, ["SPY"], "2019-12-30", "2019-12-31", adjustment="raw", asof=None)
        gateway = mock.Mock()
        gateway.get.return_value = {"bars": None}
        self.assertEqual(P.fetch_asof(gateway, ["SPY"], "2019-12-30", "2019-12-31", adjustment="raw", asof=None),
                         {"SPY": []})


class ThePlan(Fixture):
    """Open spells together at today's `asof`; each ended spell alone, `asof` inside it."""

    N = 80
    EXTRA_SPELLS = (("QEND", D(2012, 5, 1), D(2018, 6, 5)), ("QLATE", D(2021, 6, 1), D(2021, 9, 20)),
                    ("QOLD", D(2012, 5, 1), D(2019, 6, 3)), ("QNEW", D(2019, 6, 3), D(2021, 12, 1)))
    JOINS = (("QOLD", "QNEW"),)

    def setUp(self):
        super().setUp()
        self.days = [d for d, _ in U.store_sessions(LAST)]

    def test_open_assets_and_ref_go_together_thirty_nine_a_request_a_span(self):
        plan = [p for p in P.plan(self.table, self.days) if p[0] is None]
        self.assertEqual([len(p[1]) for p in plan], [39, 39, 14, 39, 39, 14], "12 REF and 80 members, twice")
        self.assertEqual({(p[2], p[3]) for p in plan}, {("2016-01-04", "2019-12-31"), ("2021-01-04", "2022-03-31")})
        self.assertEqual(plan[0][1][:12], list(xs_config.REF))
        self.assertEqual(sorted(s for p in plan[:3] for s in p[1]), sorted([*xs_config.REF, *self.names]))

    def test_each_ended_asset_goes_alone_at_a_day_inside_its_spell(self):
        ended = {p[1][0]: p for p in P.plan(self.table, self.days) if p[0] is not None and p[2] < "2020"}
        self.assertEqual(set(ended), {"QEND", "QNEW"})
        self.assertEqual(ended["QEND"], ("2018-06-04", ["QEND"], "2016-01-04", "2018-10-03"),
                         "asof its last member session; bars to 120 days after it left")
        late = [p for p in P.plan(self.table, self.days) if p[1] == ["QLATE"]]
        self.assertEqual(late, [("2021-09-17", ["QLATE"], "2021-01-04", "2022-01-18")],
                         "a year of look-back before the spell, cut at the span")

    def test_a_renamed_asset_is_one_request_series_under_its_last_ticker(self):
        joined = [p for p in P.plan(self.table, self.days) if p[1] == ["QNEW"]]
        self.assertEqual([(p[0], p[2], p[3]) for p in joined],
                         [("2021-11-30", "2016-01-04", "2019-12-31"), ("2021-11-30", "2021-01-04", "2022-03-31")])
        self.assertFalse([p for p in P.plan(self.table, self.days) if "QOLD" in p[1]])

    def test_the_daily_window_asks_only_what_can_still_change(self):
        since = self.days[-7]
        wanted = P.requests(self.table, self.days, since=since)
        self.assertEqual({r.start for r in wanted}, {since.isoformat()})
        self.assertEqual([r.symbols for r in wanted if r.asof is not None], [("QNEW",)],
                         "an asset out for less than 120 days still has a bar to come; one long gone has none")
        one = P.requests(self.table, self.days, only={aid_of(self.table, "QEND")})
        self.assertEqual([(r.symbols, r.aids) for r in one], [(("QEND",), (aid_of(self.table, "QEND"),))])


# ================================================================================================ D19
def series(n: int = 300, *, start: int = 0, end: int | None = None, volume: float = 1_000_000.0, price: float = 40.0):
    """A made-up asset's (days, raw) with bars on rows [start, end)."""
    days = [d for d, _ in eq_store.nyse_sessions(D(2017, 1, 3), D(2018, 12, 31))][:n]
    raw = np.full((n, 5), np.nan)
    end = n if end is None else end
    raw[start:end] = [price, price + 1, price - 1, price, volume]
    return days, raw


class Acceptance(unittest.TestCase):
    """D19: valid closes cover at least 95% of the spell's sessions in the store and its first valid bar is within 5
    sessions of its first session there; else "no_bars"; a median dollar volume under $5,000,000 is "reused"; OHLC
    sanity failing on more than 1% of the bars is "insane"."""

    def spell(self, days, first: int = 0, last: int | None = None):
        return ("QAAA", days[first], None if last is None else days[last])

    def test_a_whole_series_is_accepted(self):
        days, raw = series()
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days)))
        self.assertIsNone(P.acceptance({"days": days, "raw": raw, "adj": raw[:, :4]}, self.spell(days, 20, 250)))

    def test_ninety_five_percent_of_the_spells_sessions(self):
        days, raw = series(300, end=285)
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "285 of 300 is 95%")
        days, raw = series(300, end=284)
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "no_bars")
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days, 0, 290)), "the spell's own sessions")

    def test_the_first_valid_bar_within_five_sessions_of_the_spells_first(self):
        days, raw = series(300, start=5)
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days)))
        days, raw = series(300, start=6)
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "no_bars")
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days, 3)), "counted from the spell's first")

    def test_no_bar_at_all_and_a_spell_outside_the_store(self):
        days, raw = series(300, end=0)
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "no_bars")
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, ("QAAA", D(2010, 1, 4), D(2015, 1, 5))))

    def test_a_series_that_trades_too_little_is_a_reused_ticker_whatever_its_coverage(self):
        days, raw = series(300, volume=124_999.0)   # 40 x 124,999 = 4,999,960 dollars a session
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "reused")
        days, raw = series(300, volume=125_000.0)
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "exactly $5,000,000 is a member's")

    def test_a_flat_bar_of_volume_zero_is_no_valid_bar(self):
        days, raw = series(300)
        raw[10:26, 4] = 0.0
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "no_bars", "284 valid of 300")
        self.assertEqual(P.valid_bars(raw).sum(), 284)
        self.assertFalse(P.valid_bars(np.array([[1.0, 1.0, 1.0, 0.0, 5.0], [1.0, 1.0, 1.0, np.nan, 5.0],
                                                [1.0, 1.0, 1.0, 2.0, np.nan]])).any())

    def test_insane_above_one_percent_of_the_bars(self):
        days, raw = series(300)
        raw[5:8, 2] = raw[5:8, 1] + 1.0  # a low above its high on 3 of 300 bars: exactly 1%
        self.assertIsNone(P.acceptance({"days": days, "raw": raw}, self.spell(days)))
        raw[8, 2] = raw[8, 1] + 1.0
        self.assertEqual(P.acceptance({"days": days, "raw": raw}, self.spell(days)), "insane")
        sane = np.array([[10.0, 11.0, 9.0, 10.5], [10.0, 11.0, 10.2, 10.5], [10.0, 10.4, 9.0, 10.5],
                         [10.0, 11.0, 0.0, 10.5], [10.0, np.inf, 9.0, 10.5]])
        self.assertEqual(P.sane_bars(sane).tolist(), [True, False, False, False, False])


class Coverage(unittest.TestCase):
    """D19: coverage[y] = the member-days of year y with a valid bar of an unmasked asset / the member-days of y."""

    YEARS = (2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)

    def panel(self, missing=None, sessions: int = 100, assets: int = 10):
        """`sessions` made-up sessions a year of `assets` members; `missing` {year: member-days without a bar}."""
        days, rows = [], []
        for year in self.YEARS:
            for k in range(sessions):
                days.append(D(year, 1, 1) + dt.timedelta(days=k))
        member = np.ones((len(days), assets), dtype=bool)
        raw = np.full((len(days), assets, 5), 20.0)
        for year, count in (missing or {}).items():
            base = self.YEARS.index(year) * sessions
            for k in range(count):
                raw[base + k // assets, k % assets, :] = np.nan
        return member, raw, days

    def test_the_formula_by_hand(self):
        member, raw, days = self.panel({2018: 31, 2023: 5})
        member[:100, 0] = False       # one asset is no member in 2016: 900 member-days
        raw[100:110, 1, 4] = 0.0      # ten flat bars of volume 0 in 2017: no valid bar those days
        block = P.coverage(member, raw, days)
        self.assertEqual(block["coverage"]["2016"], {"member_days": 900, "with_bar": 900, "share": 1.0})
        self.assertEqual(block["coverage"]["2017"], {"member_days": 1000, "with_bar": 990, "share": 0.99})
        self.assertEqual(block["coverage"]["2018"], {"member_days": 1000, "with_bar": 969, "share": 0.969})
        self.assertEqual(block["coverage"]["2023"]["share"], 0.995)
        self.assertEqual(sorted(block["coverage"]), [str(y) for y in self.YEARS])
        self.assertEqual((block["train_years_ok"], block["verdict"]), ([2017, 2019, 2022, 2023, 2024], "low_coverage"))

    def test_a_masked_asset_counts_below_the_line_never_above_it(self):
        member, raw, days = self.panel()
        masked = [False] * 10
        masked[3] = True
        block = P.coverage(member, raw, days, masked=masked)
        self.assertTrue(all(row == {"member_days": 1000, "with_bar": 900, "share": 0.9} for row in block["coverage"].values()))
        self.assertEqual((block["train_years_ok"], block["verdict"]), ([], "insufficient"))

    def test_the_verdict(self):
        ok = P.coverage(*self.panel({2019: 30, 2025: 30}))
        self.assertEqual((ok["verdict"], ok["train_years_ok"]), ("ok", list(xs_config.TRAIN_YEARS)), "exactly 97% is at the floor")
        self.assertEqual(P.coverage(*self.panel({2016: 500, 2021: 500}))["verdict"], "ok", "a history year is a warning")
        self.assertEqual(P.coverage(*self.panel({2019: 31}))["verdict"], "low_coverage", "5 of the 6 Train years")
        self.assertEqual(P.coverage(*self.panel({2019: 31, 2022: 31}))["verdict"], "insufficient")
        self.assertEqual(P.coverage(*self.panel({2025: 31}))["verdict"], "insufficient", "2025 is judged")
        self.assertEqual(P.coverage(*self.panel({2026: 31}))["verdict"], "insufficient", "2026 is judged")
        member, raw, days = self.panel()
        short = [k for k, d in enumerate(days) if d.year != 2026]
        self.assertEqual(P.coverage(member[short], raw[short], [days[k] for k in short])["verdict"], "insufficient",
                         "a year the store does not hold is not at the floor")

    def test_the_floor_tightens_only(self):
        member, raw, days = self.panel({2019: 15})
        self.assertEqual(P.coverage(member, raw, days, floor=0.985)["verdict"], "ok")
        self.assertEqual(P.coverage(member, raw, days, floor=0.99)["verdict"], "low_coverage")
        for floor in (0.96, 1.01):
            with self.assertRaises(ValueError):
                P.coverage(member, raw, days, floor=floor)
        with self.assertRaises(ValueError):
            P.coverage(member[:5], raw, days)

    def test_it_is_the_stores_own_formula_once_c0_is_in_the_tree(self):
        member, raw, days = self.panel({2018: 31, 2023: 5, 2025: 12})
        masked = [False] * 9 + [True]
        if hasattr(xs_store, "coverage"):
            self.assertEqual(P.coverage(member, raw, days, masked=masked), xs_store.coverage(member, raw, days, masked=masked))
            self.assertTrue(np.array_equal(P.valid_bars(raw), xs_store.valid_bars(raw)))
        self.assertEqual(P.coverage(member, raw, days, masked=masked)["verdict"], "insufficient")


class Jumps(unittest.TestCase):
    """E1's "splits" rule read per column: a big move is COUNTED, never a mask."""

    def arrays(self, closes, ratio=None):
        days = [d for d, _ in eq_store.nyse_sessions(D(2019, 12, 2), D(2021, 1, 29))
                if d.year != 2020][:len(closes)]
        raw = np.full((len(closes), 1, 5), np.nan)
        adj = np.full((len(closes), 1, 4), np.nan)
        for i, close in enumerate(closes):
            if close is None:
                continue
            raw[i, 0] = [close, close, close, close, 1000.0]
            adj[i, 0] = round(close * (1.0 if ratio is None else ratio[i]), 2)
        return raw, adj, days

    def test_a_raw_move_past_thirty_percent_with_no_ratio_jump_is_a_move(self):
        raw, adj, days = self.arrays([100.0, 100.0, 40.0, 40.0, 40.0])
        self.assertEqual(P.jumps(raw, adj, days), {"moves": [(2, 0, 1)], "unexplained": []})
        raw, adj, days = self.arrays([100.0, 100.0, 71.0, 100.0, 144.0])
        self.assertEqual(P.jumps(raw, adj, days)["moves"], [(4, 0, 3)], "down 29% is no jump; up 44% is one")

    def test_the_bar_before_is_the_assets_last_bar(self):
        raw, adj, days = self.arrays([100.0, None, None, 40.0])
        self.assertEqual(P.jumps(raw, adj, days)["moves"], [(3, 0, 0)])

    def test_a_split_the_raw_close_shows_is_neither(self):
        raw, adj, days = self.arrays([100.0, 100.0, 50.0, 50.0], ratio=[0.5, 0.5, 1.0, 1.0])
        self.assertEqual(P.jumps(raw, adj, days), {"moves": [], "unexplained": []})

    def test_a_ratio_jump_the_raw_close_does_not_show_is_counted(self):
        raw, adj, days = self.arrays([100.0, 100.0, 100.0, 100.0], ratio=[0.5, 0.5, 1.0, 1.0])
        self.assertEqual(P.jumps(raw, adj, days), {"moves": [], "unexplained": [(2, 0, 1)]})

    def test_the_vendors_cents_on_a_low_price_are_no_ratio_jump(self):
        """A 12-cent name: its adjusted close moves by a whole cent of rounding, 8% of the price."""
        raw, adj, days = self.arrays([0.12, 0.12, 0.12, 0.12])
        adj[:2, 0, :] = 0.11
        self.assertEqual(P.jumps(raw, adj, days), {"moves": [], "unexplained": []})

    def test_nothing_is_read_across_the_2020_gap(self):
        days = [d for d, _ in U.store_sessions(D(2021, 1, 8))][-10:]
        self.assertEqual((days[4], days[5]), (D(2019, 12, 31), D(2021, 1, 4)))
        raw = np.full((10, 1, 5), 100.0)
        raw[5:, 0, :4] = 30.0
        adj = raw[:, :, :4] * np.array([0.5] * 5 + [1.0] * 5)[:, None, None]
        self.assertEqual(P.jumps(raw, adj, days), {"moves": [], "unexplained": []})


class SecondRead(Fixture):
    """D19's second read of one daily bar: the session's 1Min bars against the daily close."""

    HALF = D(2021, 11, 26)
    EXTRA_COMPANIES = (Company("co-QODD", [("QODD", D(2000, 1, 3), None)], base=80.0,
                               minute_gap={D(2021, 6, 2): 0.0201, D(2021, 6, 3): -0.0199, D(2021, 6, 4): -0.5}),)

    def test_it_agrees_within_two_percent_and_contradicts_beyond(self):
        count = {"calls": 0, "failed": 0}
        self.assertIs(P.second_read(self.market, "QAAA", D(2021, 6, 2), asof=None, count=count), True)
        self.assertEqual(count["calls"], 2, "the daily bar, then the session's minutes")
        self.assertIs(P.second_read(self.market, "QODD", D(2021, 6, 2), asof=None), False, "2.01% apart")
        self.assertIs(P.second_read(self.market, "QODD", D(2021, 6, 3), asof=None), True, "1.99% apart")
        self.assertIs(P.second_read(self.market, "QODD", D(2021, 6, 4), asof=None), False)

    def test_the_daily_close_it_is_handed_saves_the_call_and_the_asof_goes_with_it(self):
        self.market.requests.clear()
        self.assertIs(P.second_read(self.market, "QAAA", D(2019, 6, 3), asof="2019-06-03", daily=1.0), False)
        (request,) = self.market.requests
        self.assertEqual((request["timeframe"], request["adjustment"], request["asof"]), ("1Min", "raw", "2019-06-03"))
        self.assertEqual((request["start"], request["end"]), ("2019-06-03T13:30:00Z", "2019-06-03T20:00:00Z"),
                         "09:30 through the closing minute, where the closing cross prints")

    def test_a_half_day_closes_at_one(self):
        self.market.requests.clear()
        P.second_read(self.market, "QAAA", self.HALF, asof=None, daily=1.0, early=True)
        self.assertEqual(self.market.requests[0]["end"], "2021-11-26T18:00:00Z")

    def test_minutes_that_cannot_be_read_leave_the_bar_standing(self):
        self.assertIsNone(P.second_read(self.market, "QNONE", D(2021, 6, 2), asof=None), "no bar to read")
        self.market.fail = [GatewayError("HTTP 500", status=500)] * 3
        self.assertIsNone(P.second_read(self.market, "QAAA", D(2021, 6, 2), asof=None, daily=40.0, sleep=lambda s: None))
        self.assertIsNone(P.second_read(self.market, "QAAA", D(2020, 6, 2), asof=None, daily=40.0), "2020 is never asked")


class ABigMoveNeverMasks(Fixture):
    """The review's finding 7: E1's audit read per member would mask exactly the left-tail names for their whole
    history. A member that falls 60% in a session stays in the panel before and after."""

    CRASH = D(2018, 2, 5)
    EXTRA_COMPANIES = (Company("co-QFALL", [("QFALL", D(2000, 1, 3), None)], base=90.0, crash={CRASH: 0.4}),
                       Company("co-QLIE", [("QLIE", D(2000, 1, 3), None)], base=70.0, crash={D(2018, 3, 5): 0.4},
                               minute_gap={D(2018, 3, 5): 1.5}))
    EXTRA_SPELLS = (("QFALL", D(2010, 1, 4), None), ("QLIE", D(2010, 1, 4), None))

    def test_a_member_that_falls_sixty_percent_stays_eligible_before_and_after(self):
        receipt, ctx = self.run_job()
        self.assertTrue(receipt.get("ok"), receipt)
        self.assertEqual(receipt["masked"], {}, "a big move never masks")
        self.assertEqual((receipt["audit"]["jumps"], receipt["audit"]["second_read"], receipt["audit"]["contradicted"]),
                         (2, 4, 1), "two moves, the session of each and the one before read again")
        panel = self.panel()
        k, row = self.column(panel, "QFALL"), panel.days.index(self.CRASH)
        self.assertLess(panel.raw[row, k, 3], 0.45 * panel.raw[row - 1, k, 3])
        self.assertTrue(np.isfinite(panel.raw[:, k, 3]).all(), "every bar of it stands, the crash's too")
        self.assertTrue(panel.member[:, k].all())
        table = U.read_universe(self.root)["assets"]
        self.assertIsNone(table[str(aid_of(table, "QFALL"))]["masked"])
        self.assertIn("QFALL", json.loads((self.root / xs_store.UNIVERSE_DIR / U.TRADABLE_FILE).read_text())["stock"])

    def test_a_daily_bar_the_minute_bars_contradict_is_that_one_bar_missing_and_nothing_else(self):
        self.run_job()
        panel = self.panel()
        k, row = self.column(panel, "QLIE"), panel.days.index(D(2018, 3, 5))
        self.assertTrue(np.isnan(panel.raw[row, k]).all() and np.isnan(panel.adj[row, k]).all())
        self.assertEqual(int(np.isnan(panel.raw[:, k, 3]).sum()), 1, "that one bar, for that one day")
        table = U.read_universe(self.root)["assets"]
        self.assertIsNone(table[str(aid_of(table, "QLIE"))]["masked"])
        audit = panel.manifest["audit"]
        aid = aid_of(table, "QLIE")
        self.assertEqual(audit["blank"], [[aid, "2018-03-05"]])
        self.assertEqual(audit["reads"][f"{aid}:2018-03-05"], False)
        self.assertEqual(audit["reads"][f"{aid}:2018-03-02"], True)

    def test_a_read_is_made_once_and_the_blank_bar_stays_blank_on_the_daily_run(self):
        self.run_job()
        minutes = len([p for p in self.market.requests if p["timeframe"] == "1Min"])
        self.assertEqual(minutes, 4)
        self.market.today = D(2022, 4, 1)
        receipt, _ = self.run_job(NOW + DAY)
        self.assertEqual(receipt["mode"], "incremental")
        self.assertEqual(len([p for p in self.market.requests if p["timeframe"] == "1Min"]), minutes + 1,
                         "only the bar the blank one now stands before is read: the move is between its neighbours")
        panel = self.panel()
        k = self.column(panel, "QLIE")
        self.assertEqual(int(np.isnan(panel.raw[:, k, 3]).sum()), 1)
        self.assertEqual(receipt["audit"]["contradicted"], 1)


class WhatMasksAMember(Fixture):
    """D19's masks, and the bars that are missing for a day without one."""

    FLAT = (D(2018, 4, 3), D(2018, 4, 4))
    EXTRA_COMPANIES = (
        Company("co-QGONE", [("QGONE", D(2000, 1, 3), None)], base=55.0, last=D(2017, 3, 31)),
        Company("co-QRUS-then", [("QRUS", D(2000, 1, 3), D(2018, 1, 2))], base=66.0, last=D(2017, 12, 29)),
        Company("co-QRUS-now", [("QRUS", D(2018, 1, 2), None)], base=3.0, volume=20_000.0),
        Company("co-QTINY", [("QTINY", D(2000, 1, 3), None)], base=4.0, volume=30_000.0),
        Company("co-QHALT", [("QHALT", D(2000, 1, 3), None)], base=35.0, flat=FLAT, bad=(D(2018, 5, 8),)),
        Company("co-QMAD", [("QMAD", D(2000, 1, 3), None)], base=45.0,
                bad=tuple(d for d, _ in eq_store.nyse_sessions(D(2016, 2, 1), D(2016, 3, 31)))))
    EXTRA_SPELLS = (("QGONE", D(2012, 5, 1), D(2018, 6, 5)), ("QRUS", D(2012, 5, 1), D(2017, 9, 18)),
                    ("QTINY", D(2012, 5, 1), D(2019, 3, 1)), ("QHALT", D(2010, 1, 4), None),
                    ("QMAD", D(2012, 5, 1), D(2019, 3, 1)), ("QNOBAR", D(2012, 5, 1), D(2019, 3, 1)))

    def setUp(self):
        super().setUp()
        self.receipt, self.alerts = self.run_job()
        self.assertTrue(self.receipt.get("ok"), self.receipt)
        self.panel_ = self.panel()
        self.assets = U.read_universe(self.root)["assets"]

    def mask(self, ticker: str):
        return self.assets[str(aid_of(self.assets, ticker))]["masked"]

    def test_each_mask(self):
        self.assertEqual(self.receipt["masked"], {"insane": 1, "no_bars": 2, "reused": 1})
        self.assertEqual(self.mask("QGONE"), "no_bars", "its bars end 14 months before its membership")
        self.assertEqual(self.mask("QNOBAR"), "no_bars", "the venue has no bar of it")
        self.assertEqual(self.mask("QTINY"), "reused", "a series that trades $120,000 a session is no index member's")
        self.assertEqual(self.mask("QMAD"), "insane", "its bars fail OHLC sanity on more than 1% of them")
        self.assertIsNone(self.mask("QHALT"))
        self.assertEqual(self.panel_.manifest["audit"]["masked"], self.receipt["masked"])
        self.assertEqual(self.receipt["masked_members"], 0, "none of them is a current member")

    def test_a_reused_ticker_resolves_to_the_spells_own_company_through_its_asof(self):
        self.assertIsNone(self.mask("QRUS"), "asked at a day inside the spell, the venue serves the member's bars")
        k = self.column(self.panel_, "QRUS")
        self.assertGreater(float(np.nanmin(self.panel_.raw[:, k, 3])), 50.0, "the company of then, not today's $3 one")
        asked = [p for p in self.market.requests if p["symbols"] == "QRUS"]
        self.assertEqual({p["asof"] for p in asked}, {"2017-09-15"})

    def test_a_flat_bar_of_volume_zero_is_kept_as_served_and_counted_as_no_bar(self):
        k = self.column(self.panel_, "QHALT")
        for day in self.FLAT:
            row = self.panel_.raw[self.panel_.days.index(day), k]
            self.assertEqual((row[4], row[0] == row[1] == row[2] == row[3]), (0.0, True))
        self.assertEqual(self.receipt["audit"]["zero_volume"], 2)
        year = self.panel_.manifest["coverage"]["2018"]
        self.assertEqual(year["member_days"] - year["with_bar"],
                         2 + 1 + self.unbarred(2018), "the two flat days, the one insane bar, and the masked assets'")

    def unbarred(self, year: int) -> int:
        """The member-days of `year` of the masked assets (none of them counts above the line)."""
        total = 0
        for ticker in ("QGONE", "QTINY", "QMAD", "QNOBAR"):
            k = self.column(self.panel_, ticker)
            total += int(sum(1 for i, d in enumerate(self.panel_.days) if d.year == year and self.panel_.member[i, k]))
        return total

    def test_a_single_insane_bar_is_a_missing_bar_for_that_day_never_a_mask(self):
        k, row = self.column(self.panel_, "QHALT"), self.panel_.days.index(D(2018, 5, 8))
        self.assertTrue(np.isnan(self.panel_.raw[row, k]).all())
        self.assertEqual(self.receipt["audit"]["insane_bars"], 1)
        self.assertIn([aid_of(self.assets, "QHALT"), "2018-05-08"], self.panel_.manifest["audit"]["blank"])

    def test_the_names_whose_bars_end_while_members_are_listed_by_aid(self):
        self.assertEqual(self.panel_.manifest["vanished"], [aid_of(self.assets, "QGONE")])
        self.assertEqual(self.receipt["vanished"], 1)

    def test_the_tradable_list_drops_the_masked(self):
        listed = json.loads((self.root / xs_store.UNIVERSE_DIR / U.TRADABLE_FILE).read_text())["stock"]
        self.assertIn("QHALT", listed)
        self.assertEqual({"QGONE", "QTINY", "QMAD", "QNOBAR", "QRUS"} & set(listed), set(),
                         "masked, or out of the index for more than 36 months")

    def test_over_five_percent_of_current_members_masked_fails_the_run_and_writes_nothing(self):
        state = Path(self.tmp.name) / "second"
        (state / U.STORE_DIR).mkdir(parents=True)
        spells = [*self.spells, ("QNOA", D(2010, 1, 4), None), ("QNOB", D(2010, 1, 4), None)]
        write_universe(state / U.STORE_DIR, spells)
        (state / "swarm.json").write_text((self.state / "swarm.json").read_text(encoding="utf-8"), encoding="utf-8")
        ctx = Context("equity_panel", root=state, due_at=NOW, clock=lambda: NOW, gateway=self.market, config={},
                      settings_value={})
        receipt = P.run(ctx, sleep=lambda s: None)
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("2 of 27 current members are masked", receipt["error"])
        self.assertFalse((state / U.STORE_DIR / xs_store.PANEL_DIR).exists())
        self.assertIsNone(U.read_universe(state / U.STORE_DIR)["assets"][str(aid_of(self.assets, "QAAA"))]["masked"])


# ================================================================================================ 4.2
class TheVintageRule(Fixture):
    """`adj` of one asset is ONE fetch's series: appended while the overlap's ratios agree within the vendor's cents,
    refetched whole when a dividend or split restated its history."""

    DIVIDEND_DAY = D(2022, 4, 1)
    EXTRA_COMPANIES = (Company("co-QDIV", [("QDIV", D(2000, 1, 3), None)], base=60.0, dividends={DIVIDEND_DAY: 0.75}),
                       Company("co-QSPL", [("QSPL", D(2000, 1, 3), None)], base=400.0, splits={D(2022, 4, 4): 4.0}),
                       Company("co-QOUT", [("QOUT", D(2000, 1, 3), None)], base=52.0))
    EXTRA_SPELLS = (("QDIV", D(2010, 1, 4), None), ("QSPL", D(2010, 1, 4), None), ("QOUT", D(2012, 5, 1), D(2018, 6, 5)))

    def test_ratios_equal_within_the_cents(self):
        raw = np.array([[10.0, 10.5, 9.5, 10.0, 1e6], [10.2, 10.6, 9.9, 10.1, 1e6], [np.nan] * 5])
        adj = np.array([[9.0, 9.45, 8.55, 9.0], [9.18, 9.54, 8.91, 9.09], [np.nan] * 4])
        self.assertTrue(P.ratios_equal(raw, adj, raw, adj))
        cent = adj.copy()
        cent[0, 3] += 0.01   # one cent on a $9 close: 0.11%, inside 1.5 x (0.005 / 9.00 + 0.005 / 9.01) = 0.17%
        self.assertTrue(P.ratios_equal(raw, adj, raw, cent))
        cent[0, 3] += 0.01   # two cents: 0.22%, a restatement
        self.assertFalse(P.ratios_equal(raw, adj, raw, cent))
        self.assertLess(abs(xs_config.rounding_bound(9.0, 9.01) - 1.5 * 0.005 * (1 / 9.0 + 1 / 9.01)), 1e-15)
        gone_raw, gone_adj = raw.copy(), adj.copy()
        gone_raw[1], gone_adj[1] = np.nan, np.nan
        self.assertFalse(P.ratios_equal(raw, adj, gone_raw, gone_adj), "a bar the store has is gone from the fetch")
        self.assertTrue(P.ratios_equal(gone_raw, gone_adj, raw, adj), "a bar served late says nothing against the store")
        empty = np.full((3, 5), np.nan)
        self.assertTrue(P.ratios_equal(empty, empty[:, :4], empty, empty[:, :4]), "no bar on either side")
        self.assertFalse(P.ratios_equal(empty, empty[:, :4], raw, adj), "bars, and none of the store's to hold them to")

    def test_the_daily_run_appends_and_keeps_each_vintage(self):
        first, _ = self.run_job()
        self.assertEqual((first["mode"], first["refetched"]), ("full", 12 + self.N + 3))
        before = self.panel()
        self.assertEqual(set(before.manifest["vintage"].values()), {LAST.isoformat()})
        self.assertEqual(before.manifest["full_at"], LAST.isoformat())
        whole = len(self.market.requests)
        self.market.today = D(2022, 4, 1)
        second, _ = self.run_job(NOW + DAY)
        self.assertEqual((second["mode"], second["sessions"], second["refetched"], second["revisions"]),
                         ("incremental", first["sessions"] + 1, 1, 0))
        self.assertEqual(second["appended"], 12 + self.N + 2 - 1, "every open asset but the restated one")
        after = self.panel()
        self.assertEqual(after.days[-1], D(2022, 4, 1))
        k = self.column(after, "QAAA")
        self.assertTrue(np.array_equal(after.raw[:-1, k], before.raw[:, k], equal_nan=True))
        self.assertTrue(np.array_equal(after.adj[:-1, k], before.adj[:, k], equal_nan=True))
        self.assertTrue(np.isfinite(after.raw[-1, k]).all())
        aid = str(after.aids[k])
        self.assertEqual((after.manifest["vintage"][aid], after.manifest["full_at"]), (LAST.isoformat(), LAST.isoformat()))
        daily = self.market.requests[whole:]
        self.assertEqual({p["start"] for p in daily if p["start"] >= "2022"}, {"2022-03-24"}, "the last seven sessions")
        self.assertEqual({p["start"] for p in daily if p["start"] < "2022" and p["symbols"] != "QDIV"},
                         {after.days[-253].isoformat()}, "and the nightly I6's 253")
        self.assertFalse([p for p in daily if p["symbols"] == "QOUT"], "an asset long out of the index is not asked")
        k_out = self.column(after, "QOUT")
        self.assertTrue(np.array_equal(after.raw[:-1, k_out], before.raw[:, k_out], equal_nan=True))

    def test_a_dividend_restates_the_history_and_the_asset_is_refetched_whole(self):
        self.run_job()
        before = self.panel()
        self.market.today = self.DIVIDEND_DAY
        self.run_job(NOW + DAY)
        after = self.panel()
        k = self.column(after, "QDIV")
        aid = str(after.aids[k])
        self.assertEqual(after.manifest["vintage"][aid], self.DIVIDEND_DAY.isoformat())
        row = before.days.index(D(2019, 6, 3))
        ratio = after.adj[row, k, 3] / before.adj[row, k, 3]
        self.assertAlmostEqual(ratio, 1.0 - 0.75 / before.raw[-1, k, 3], delta=3e-4)
        self.assertTrue(np.array_equal(after.raw[:-1, k], before.raw[:, k], equal_nan=True), "the raw tape is the same")
        factor = after.adj[:-1, k, 3] / after.raw[:-1, k, 3]
        self.assertLess(float(np.nanmax(factor) - np.nanmin(factor)), 5e-4, "ONE fetch's series: one basis throughout")
        whole = [p for p in self.market.requests if p["symbols"] == "QDIV"]
        self.assertEqual({(p["start"], p["end"]) for p in whole}, {("2016-01-04", "2019-12-31"), ("2021-01-04", "2022-04-01")})

    def test_a_split_restates_it_too_and_is_no_big_move(self):
        self.run_job()
        self.market.today = D(2022, 4, 4)
        receipt, _ = self.run_job(NOW + 4 * DAY)
        after = self.panel()
        k = self.column(after, "QSPL")
        self.assertEqual(after.manifest["vintage"][str(after.aids[k])], "2022-04-04")
        self.assertAlmostEqual(after.raw[-1, k, 3] / after.raw[-2, k, 3], 0.25, delta=0.02)
        self.assertAlmostEqual(after.adj[-1, k, 3] / after.adj[-2, k, 3], 1.0, delta=0.02)
        self.assertEqual((receipt["audit"]["jumps"], receipt["audit"]["unexplained"], receipt["masked"]), (0, 0, {}))

    def test_a_raw_price_the_vendor_revised_is_counted_and_a_volume_alone_is_not(self):
        self.run_job()
        company = next(c for c in self.market.companies if c.name == "co-QAAA")
        company.volume += 5000.0   # yesterday's consolidated volume, read later
        self.market.today = D(2022, 4, 1)
        receipt, _ = self.run_job(NOW + DAY)
        self.assertEqual(receipt["revisions"], 0)
        held = len(self.panel().days)
        company.base += 0.5        # the tape itself restated
        self.market.today = D(2022, 4, 4)
        receipt, ctx = self.run_job(NOW + 4 * DAY)
        self.assertEqual((receipt["revisions"], receipt["refetched"]), (held, 2),
                         "every bar the store held of it: the asset is fetched whole again (as the one that split is)")
        self.assertEqual(self.panel().manifest["revisions"], held)
        self.assertEqual(len([a for a in ctx.alerts if "raw bars changed" in a["text"]]), 1, "an alarm above 20")
        self.assertEqual(P._revised(np.array([[1.0, 2.0, 0.5, 1.5, 10.0], [np.nan] * 5]),
                                    np.array([[1.0, 2.0, 0.5, 1.5, 99.0], [1.0, 2.0, 0.5, 1.5, 9.0]])), 0)

    def test_a_new_asset_is_fetched_whole_and_the_aids_keep_their_columns(self):
        self.run_job()
        before = self.panel()
        assets = U.read_universe(self.root)["assets"]
        spells = [*self.spells, ("QJOIN", D(2022, 4, 1), None)]
        self.market.companies.append(Company("co-QJOIN", [("QJOIN", D(2000, 1, 3), None)], base=77.0))
        grown = U.assign(spells, assets, [], venue={"QJOIN": dict(VENUE_OK)})
        manifest = U.read_universe(self.root)["manifest"]
        U._publish(self.root, files={U.ASSETS_FILE: U._json_bytes(grown)}, manifest=manifest)
        self.market.today = D(2022, 4, 1)
        receipt, _ = self.run_job(NOW + DAY)
        self.assertEqual((receipt["mode"], receipt["refetched"], receipt["assets"]), ("incremental", 2, self.N + 4))
        after = self.panel()
        self.assertEqual(after.aids[:-1], before.aids)
        k = after.aids.index(aid_of(grown, "QJOIN"))
        self.assertEqual(int(np.isfinite(after.raw[:, k, 3]).sum()), len(after.days), "a year of look-back and more")
        self.assertEqual(after.member[:, k].tolist(), [False] * (len(after.days) - 1) + [True])

    def test_a_bar_served_late_is_taken_without_a_whole_refetch(self):
        """A run just after a close can find a name's bar of the day not yet served: the next run fills it."""
        self.run_job()
        company = next(c for c in self.market.companies if c.name == "co-QAAE")
        self.market.today = D(2022, 4, 1)
        company.last = LAST           # the venue has not its bar of April 1 yet
        receipt, _ = self.run_job(NOW + DAY)
        panel = self.panel()
        k = self.column(panel, "QAAE")
        self.assertTrue(np.isnan(panel.raw[-1, k]).all())
        company.last = None
        whole = len(self.market.requests)
        receipt, _ = self.run_job(NOW + DAY + 3600)
        self.assertEqual((receipt["mode"], receipt["refetched"]), ("incremental", 0))
        self.assertTrue(np.isfinite(self.panel().raw[-1, k]).all())
        self.assertFalse([p for p in self.market.requests[whole:] if p["symbols"] == "QAAE"])

    def test_incremental_needs_a_store_whose_sessions_are_the_calendars_first(self):
        with self.assertRaises(ValueError):
            P.incremental(self.root, self.market, LAST, sleep=lambda s: None)
        self.run_job()
        with self.assertRaises(ValueError):
            P.incremental(self.root, self.market, D(2022, 3, 30), sleep=lambda s: None)

    def test_a_whole_refetch_every_six_and_a_half_days(self):
        self.run_job()
        self.market.today = D(2022, 4, 5)
        early, _ = self.run_job(NOW + 5 * DAY)
        self.assertEqual(early["mode"], "incremental", "6.07 days after the day of the last whole fetch")
        self.market.today = D(2022, 4, 6)
        week, _ = self.run_job(NOW + 6 * DAY)
        self.assertEqual((week["mode"], self.panel().manifest["full_at"]), ("full", "2022-04-06"))
        self.assertEqual(set(self.panel().manifest["vintage"].values()), {"2022-04-06"})

    def test_a_whole_refetch_that_fails_falls_back_to_the_daily_run_and_is_tried_again(self):
        self.run_job()
        self.market.today = D(2022, 4, 7)
        self.market.fail_when = lambda p: p["start"] == "2016-01-04" and "QAAC" in p["symbols"].split(",")
        receipt, ctx = self.run_job(NOW + 7 * DAY)
        self.assertEqual((receipt.get("ok"), receipt["mode"], receipt["full_failed"]), (True, "incremental", True))
        manifest = self.panel().manifest
        self.assertEqual((manifest["full_at"], manifest["audit"]["full_failures"]), (LAST.isoformat(), 1),
                         "full_at does not move")
        self.assertEqual(self.panel().days[-1], D(2022, 4, 7), "and the store still grew")
        self.assertEqual([a for a in ctx.alerts if "whole refetch failed" in a["text"]], [])
        self.market.today = D(2022, 4, 8)
        receipt, ctx = self.run_job(NOW + 8 * DAY)
        self.assertEqual((receipt["mode"], self.panel().manifest["audit"]["full_failures"]), ("incremental", 2))
        self.assertEqual(len([a for a in ctx.alerts if "whole refetch failed 2 nights running" in a["text"]]), 1)
        self.market.fail_when = None
        self.market.today = D(2022, 4, 11)
        receipt, _ = self.run_job(NOW + 11 * DAY)
        self.assertEqual((receipt["mode"], self.panel().manifest["audit"]["full_failures"]), ("full", 0))

    def test_a_first_fetch_that_fails_writes_nothing(self):
        self.market.fail_when = lambda p: "QAAC" in p["symbols"].split(",")
        receipt, _ = self.run_job()
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse((self.root / xs_store.PANEL_DIR).exists())
        self.assertNotIn("QAAC", json.dumps(receipt), "a failed call is said by its kind, never the venue's text")

    def test_failing_two_days_running_is_an_alarm_and_critical_while_a_panel_instance_is_live(self):
        self.market.fail_when = lambda p: True
        first, ctx = self.run_job()
        again, ctx_again = self.run_job(NOW + 600)   # the runner's retry inside the job's grace: the same day
        self.assertEqual((first["status"], again["status"], ctx.alerts, ctx_again.alerts), ("failed", "failed", [], []))
        second, ctx = self.run_job(NOW + DAY)
        self.assertEqual([(a["level"], "2 days running" in a["text"]) for a in ctx.alerts], [("warning", True)])
        db = sqlite3.connect(self.state / P.LIVE_DB)
        db.execute("CREATE TABLE eq_instances (id TEXT PRIMARY KEY, retired_at REAL, kind TEXT NOT NULL DEFAULT 'equity')")
        db.executemany("INSERT INTO eq_instances VALUES (?, ?, ?)", [("a@1:r", None, "equity"), ("b@1:r", 5.0, "panel")])
        db.commit()
        self.assertEqual(P.live_panels(self.state / P.LIVE_DB), 0, "an ETF program, and a retired panel one")
        db.execute("INSERT INTO eq_instances VALUES ('c@1:r', NULL, 'panel')")
        db.commit()
        db.close()
        third, ctx = self.run_job(NOW + 2 * DAY)
        self.assertEqual([(a["level"], "3 days running" in a["text"]) for a in ctx.alerts], [("critical", True)])
        self.market.fail_when = None
        self.market.today = D(2022, 4, 1)
        good, ctx = self.run_job(NOW + 2 * DAY + 600)
        self.assertTrue(good.get("ok"), good)
        self.assertFalse((self.root / P.FAILURES_FILE).exists(), "a good run ends the count")
        self.assertEqual(P.live_panels(self.state / "absent.sqlite"), 0)


# ================================================================================================ D20
class HalfSpreads(unittest.TestCase):
    """D20: max(the floor, the 75th percentile of the name's samples); fewer than 8 samples: the universe's 75th
    percentile; no file: 10 bp at the open and 5 bp at the close."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, names, default=None):
        table = {"version": "xs-spreads-v1", "names": names, "default": default or {}}
        (self.root / P.SPREADS_FILE).write_text(json.dumps(table))

    def test_no_file_is_the_fallback(self):
        self.assertEqual(P.hs_table(self.root, [1, 100, 101]).tolist(), [[0.0010, 0.0005]] * 3)
        self.assertEqual(P.hs_share(self.root, [100, 101]), 0.0)
        self.assertEqual(xs_config.HS_FALLBACK_BP, (10.0, 5.0))

    def test_a_names_own_figure_the_floor_and_the_universes_for_a_thin_name(self):
        self.write({"100": {"open_bp": 7.5, "close_bp": 1.2, "n_open": 8, "n_close": 8},
                    "101": {"open_bp": 99.0, "close_bp": 99.0, "n_open": 7, "n_close": 8},
                    "102": {"open_bp": None, "close_bp": 4.0, "n_open": 0, "n_close": 30}},
                   default={"open_bp": 12.0, "close_bp": 6.0})
        table = P.hs_table(self.root, [100, 101, 102, 103])
        self.assertEqual(table.shape, (4, 2))
        self.assertEqual([[round(v * 1e4, 6) for v in row] for row in table.tolist()],
                         [[7.5, 3.0], [12.0, 99.0], [12.0, 4.0], [12.0, 6.0]],
                         "never under the 3 bp floor; fewer than 8 samples at a point: the universe's figure there")
        self.assertEqual(xs_config.HS_FLOOR_BP, 3.0)
        self.assertEqual(P.hs_share(self.root, [100, 101, 102, 103]), 0.25, "8 samples at BOTH points")

    def test_the_universes_figure_is_the_75th_percentile_of_the_names_with_enough(self):
        names = {str(100 + k): {"open_bp": float(10 + k), "close_bp": float(2 * k + 4), "n_open": 8, "n_close": 8}
                 for k in range(5)}
        names["200"] = {"open_bp": 500.0, "close_bp": 500.0, "n_open": 3, "n_close": 3}
        self.write(names)
        thin = P.hs_table(self.root, [200, 300])
        self.assertEqual([[round(v * 1e4, 6) for v in row] for row in thin.tolist()], [[13.0, 10.0]] * 2)
        self.assertEqual(P._percentile([10, 11, 12, 13, 14], 75.0), float(np.percentile([10, 11, 12, 13, 14], 75)))
        self.assertEqual(P._percentile([4.0, 9.0], 75.0), float(np.percentile([4.0, 9.0], 75)))
        self.assertEqual(P._percentile([5.0], 75.0), 5.0)

    def test_an_unreadable_file_is_no_file(self):
        (self.root / P.SPREADS_FILE).write_text("{not json")
        self.assertEqual(P.hs_table(self.root, [100]).tolist(), [[0.0010, 0.0005]])
        (self.root / P.SPREADS_FILE).write_text(json.dumps({"names": []}))
        self.assertEqual(P.hs_table(self.root, [100]).tolist(), [[0.0010, 0.0005]])


# ================================================================================================ the nightly I6
def two_readings(n: int = 30, m: int = 3):
    """Two identical readings: raw (n, m, 5) on the cent grid and adj = raw x 0.9, rounded to the cent."""
    rows = np.arange(n, dtype=np.float64)[:, None]
    close = np.round(20.0 + 5.0 * np.arange(m)[None, :] + 0.07 * rows, 2)
    raw = np.stack([close, close + 0.5, close - 0.5, close, np.full_like(close, 1e6)], axis=-1)
    adj = np.round(raw[..., :4] * 0.9, 2)
    return raw, adj


class CompareBars(unittest.TestCase):
    """The I6's verdict on two readings of the same bars: E1's morning rule, within the vendor's cents."""

    def test_identical_readings_are_equal(self):
        raw, adj = two_readings()
        mismatch, volume = P.compare_bars(raw, adj, raw.copy(), adj.copy())
        self.assertEqual((mismatch.tolist(), volume.tolist()), ([False] * 3, [False] * 3))

    def test_a_restated_series_rounded_to_the_cent_is_equal_and_a_real_difference_is_not(self):
        """A dividend between the two fetches: every adjusted price is scaled, then rounded to the cent. The as-of
        prices at the decision day are then equal only to that rounding, never byte for byte."""
        raw, adj = two_readings()
        restated = np.round(raw[..., :4] * 0.9 * 0.9931, 2)
        self.assertFalse(np.array_equal(restated * (raw[-1, :, 3] / restated[-1, :, 3])[None, :, None],
                                        adj * (raw[-1, :, 3] / adj[-1, :, 3])[None, :, None]))
        mismatch, _ = P.compare_bars(raw, adj, raw, restated)
        self.assertEqual(mismatch.tolist(), [False] * 3, "within the cents")
        wrong = restated.copy()
        wrong[5, 1, :] = np.round(wrong[5, 1, :] * 1.01, 2)   # one bar's adjusted prices are 1% off
        mismatch, _ = P.compare_bars(raw, adj, raw, wrong)
        self.assertEqual(mismatch.tolist(), [False, True, False])

    def test_a_raw_price_is_exact_and_a_volume_alone_is_a_note(self):
        raw, adj = two_readings()
        later = raw.copy()
        later[-1, 0, 4] += 12345.0
        mismatch, volume = P.compare_bars(raw, adj, later, adj)
        self.assertEqual((mismatch.tolist(), volume.tolist()), ([False] * 3, [True, False, False]))
        later[3, 2, 0] += 0.01
        mismatch, volume = P.compare_bars(raw, adj, later, adj)
        self.assertEqual((mismatch.tolist(), volume.tolist()), ([False, False, True], [True, False, False]))

    def test_a_bar_one_reading_lacks_is_a_mismatch(self):
        raw, adj = two_readings()
        fewer_raw, fewer_adj = raw.copy(), adj.copy()
        fewer_raw[7, 1], fewer_adj[7, 1] = np.nan, np.nan
        self.assertEqual(P.compare_bars(raw, adj, fewer_raw, fewer_adj)[0].tolist(), [False, True, False])
        self.assertEqual(P.compare_bars(fewer_raw, fewer_adj, fewer_raw, fewer_adj)[0].tolist(), [False] * 3)

    def test_the_factor_is_read_at_the_columns_last_bar(self):
        """A name halted on the decision day: its as-of factor is its last bar's (E1's `_factor_row`)."""
        raw, adj = two_readings()
        raw[-1, 0], adj[-1, 0] = np.nan, np.nan
        restated = np.round(raw[..., :4] * 0.9 * 0.9931, 2)
        self.assertEqual(P.compare_bars(raw, adj, raw, restated)[0].tolist(), [False] * 3)
        empty_raw, empty_adj = np.full_like(raw, np.nan), np.full_like(adj, np.nan)
        self.assertEqual(P.compare_bars(empty_raw, empty_adj, empty_raw, empty_adj)[0].tolist(), [False] * 3)


class TheNightlyI6(Fixture):
    """`i6_check`: the reference columns of the store against the fetch a decision read, or a fresh one."""

    def setUp(self):
        super().setUp()
        receipt, _ = self.run_job()
        self.assertTrue(receipt.get("ok"), receipt)
        self.first = receipt
        self.market.requests.clear()

    def check(self, **kw):
        return P.i6_check(self.root, self.market, LAST, sleep=lambda s: None, **kw)

    def test_the_jobs_own_i6_is_in_the_manifest_and_the_receipt(self):
        i6 = self.panel().manifest["i6"]
        self.assertEqual((i6["day"], i6["equal"], i6["source"], i6["columns"], i6["mismatch"], i6["live"]),
                         (LAST.isoformat(), True, "fetch", 12 + self.N, 0, {}))
        self.assertEqual(self.first["i6"]["equal"], True)
        self.assertEqual(set(i6) - {"bytes_equal", "columns", "mismatch", "volume", "blanked", "late", "absent", "why"},
                         {"day", "store_sha", "fetch_sha", "equal", "source", "live"})

    def test_a_fresh_fetch_of_the_253_sessions_in_chunks_of_thirty_nine(self):
        out = self.check()
        self.assertEqual((out["equal"], out["source"], out["mismatch"], out["volume"]), (True, "fetch", 0, 0))
        asked = self.market.requests
        self.assertEqual(len(asked), 2, "36 columns: one chunk, raw then all")
        days = self.panel().days
        self.assertEqual({(p["start"], p["end"]) for p in asked}, {(days[-253].isoformat(), LAST.isoformat())})
        self.assertTrue(all("asof" not in p for p in asked))
        self.assertEqual(sorted(asked[0]["symbols"].split(",")), sorted([*xs_config.REF, *self.names]))

    def test_a_restatement_since_the_stores_vintage_is_equal_within_the_cents(self):
        company = next(c for c in self.market.companies if c.name == "co-QAAB")
        company.dividends[D(2022, 4, 1)] = 0.11   # goes ex tomorrow: the fresh fetch is restated, the store is not
        self.market.today = D(2022, 4, 1)
        out = self.check()
        self.assertEqual((out["equal"], out["mismatch"]), (True, 0))

    def test_a_price_that_differs_is_false(self):
        company = next(c for c in self.market.companies if c.name == "co-QAAB")
        company.base *= 1.01
        out = self.check()
        self.assertEqual((out["equal"], out["mismatch"], out["columns"]), (False, 1, 12 + self.N))
        receipt, ctx = self.run_job(NOW + 3600)
        self.assertEqual((receipt["i6"]["equal"], receipt["refetched"]), (True, 1),
                         "the daily run saw the tape revised and fetched the asset whole: equal again")

    def test_a_false_i6_is_a_critical_alarm(self):
        with mock.patch.object(P, "i6_check", return_value={"day": LAST.isoformat(), "store_sha": None,
                                                            "fetch_sha": None, "equal": False, "bytes_equal": None,
                                                            "source": "fetch", "live": {"a": False}, "columns": 36,
                                                            "mismatch": 3, "volume": 0, "blanked": 0, "why": None}):
            receipt, ctx = self.run_job(NOW + 3600)
        self.assertTrue(receipt["ok"])
        self.assertEqual([a["level"] for a in ctx.alerts if "nightly I6 is False" in a["text"]], ["critical"])
        self.assertEqual(self.panel().manifest["i6"]["equal"], False)

    def test_what_it_cannot_do_is_said_and_is_never_true(self):
        self.assertEqual(P.i6_check(self.root, self.market, D(2022, 4, 1))["why"], "the store does not hold the day")
        early = P.i6_check(self.root, self.market, D(2016, 6, 1))
        self.assertEqual((early["equal"], early["why"]), (None, "the store holds less than the decision's window before the day"))
        across = P.i6_check(self.root, self.market, D(2021, 6, 1), sleep=lambda s: None)
        self.assertIsNone(across["equal"])
        self.assertIn("2020 is never fetched", across["why"])
        self.market.fail_when = lambda p: True
        down = self.check()
        self.assertEqual(down["equal"], None)
        self.assertIn("failed 3 times", down["why"])

    def kept_file(self, panel=None, *, drop=(), extra=()):
        """What `league.xs.book.kept` answers: the day's 16:20 fetch of the union of the instances' columns."""
        panel = panel or self.panel()
        assets = U.read_universe(self.root)["assets"]
        symbols = [assets[str(a)]["symbol"] for a in panel.aids if a < 100 or panel.member[-1, panel.aids.index(a)]]
        symbols = [s for s in symbols if s not in drop] + list(extra)
        cols = [panel.aids.index(aid_of(assets, s)) for s in symbols]
        days = np.array([eq_store.ordinal(d) for d in panel.days[-253:]], dtype=np.int32)
        return tuple(symbols), xs_book.Fetched(days=days, raw=np.array(panel.raw[-253:][:, cols]),
                                               all=np.array(panel.adj[-253:][:, cols]), meta={"fetched_at": 1.0})

    def test_the_kept_1620_fetch_is_the_fetch_side_when_a_decision_kept_one(self):
        kept = self.kept_file()
        with mock.patch.object(xs_book, "kept", return_value=kept) as reader:
            out = self.check()
        reader.assert_called_once_with(self.root, LAST)
        self.assertEqual((out["equal"], out["source"]), (True, "kept"))
        self.assertEqual(self.market.requests, [], "the bytes a real decision read: no call")
        kept[1].raw[-1, :, 4] *= 0.8      # the 16:20 volume is not the day's final one
        kept[1].raw[100, 14, 3] += 0.01   # and one raw close differs
        with mock.patch.object(xs_book, "kept", return_value=kept):
            out = self.check()
        self.assertEqual((out["equal"], out["mismatch"], out["volume"]), (False, 1, 12 + self.N - 1))

    def test_a_kept_file_that_lacks_a_column_is_not_used(self):
        with mock.patch.object(xs_book, "kept", return_value=self.kept_file(drop=("QAAC",))):
            out = self.check()
        self.assertEqual((out["equal"], out["source"]), (True, "fetch"))

    def live_db(self, rows):
        path = self.state / P.LIVE_DB
        db = sqlite3.connect(path)
        db.executescript(xs_book.SCHEMA)
        for instance, extra in rows:
            db.execute("INSERT INTO eq_rebalances (instance, family, version, decided_day, exec_day, at, called, targets, "
                       "n_names, n_sells, n_buys, n_skipped, extra, bars_sha, status, created_at) VALUES (?, 'fam', 1, ?, "
                       "?, 'open', 1, '[]', 0, 0, 0, 0, ?, 'b', 'planned', 0)",
                       (instance, LAST.isoformat(), "2022-04-01", json.dumps(extra)))
        db.execute("INSERT INTO eq_rebalances (instance, family, version, decided_day, exec_day, at, called, targets, "
                   "n_names, n_sells, n_buys, n_skipped, status, created_at) VALUES ('other-day', 'fam', 1, '2022-03-30', "
                   "'2022-03-31', 'open', 1, '[]', 0, 0, 0, 0, 'planned', 0)")
        db.commit()
        db.close()
        return path

    def test_each_live_decision_of_the_day_is_rebuilt_from_the_store_by_e1s_verdict(self):
        """A held name that left the index keeps its column (the row's `extra`)."""
        assets = U.read_universe(self.root)["assets"]
        spells = [(t, s, D(2022, 3, 1) if t == "QAAD" else e) for t, s, e in self.spells]
        left = U.assign(spells, assets, [])
        U._publish(self.root, files={U.ASSETS_FILE: U._json_bytes(left)}, manifest=U.read_universe(self.root)["manifest"])
        self.run_job(NOW + 60)
        panel = self.panel()
        self.assertFalse(panel.member[-1, self.column(panel, "QAAD")])
        path = self.live_db([("fam@1:r", ["QAAD"]), ("fam@2:r", [])])
        kept = self.kept_file(panel, extra=("QAAD",))
        self.market.requests.clear()
        with mock.patch.object(xs_book, "kept", return_value=kept):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["live"], out["source"]), (True, {"fam@1:r": True, "fam@2:r": True}, "kept"))
        self.assertEqual(self.market.requests, [])
        at = kept[0].index("QAAD")
        kept[1].raw[40, at, 1] += 0.01   # the held name's kept bar is not the store's
        with mock.patch.object(xs_book, "kept", return_value=kept):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["live"], out["mismatch"]), (False, {"fam@1:r": False, "fam@2:r": True}, 0))
        with mock.patch.object(xs_book, "kept", return_value=None):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["live"], out["source"]), (True, {"fam@1:r": None, "fam@2:r": None}, "fetch"),
                         "a decision with no kept fetch cannot be shown equal, and is not shown to differ: UNREAD")

    # ------------------------------------------------ what the live book itself tolerates is never a False I6
    def test_a_bar_served_after_the_1620_fetch_is_late_counted_and_never_a_mismatch(self):
        """B13: `xs.book.complete` lets a decide go with one or two names nobody holds lacking the day's bar, and the
        book's own morning audit calls a bar served later a note (`xs.book.same`: "late"). The store at 21:45 has the
        bar. The I6 read that as "sessions differ": False, and a False I6 holds every open of the lane."""
        from league.equity import live as L

        symbols, kept = self.kept_file()
        at = len(xs_config.REF) + 3                       # a member column
        late = xs_book.Fetched(days=kept.days, raw=np.array(kept.raw), all=np.array(kept.all), meta=dict(kept.meta))
        late.raw[-1, at, :] = np.nan                      # no bar of the day at 16:20 ...
        late.all[-1, at, :] = np.nan
        cols = xs_book.Columns(symbols=tuple(symbols), aids=np.zeros(0, dtype=np.int32), ids=np.zeros(0, dtype=np.int32),
                               elig0=np.array([False] * len(xs_config.REF) + [True] * (len(symbols) - len(xs_config.REF))),
                               sector_perm=np.zeros(0, dtype=np.int8), dither_key=b"", extra=())
        self.assertEqual(xs_book.complete(late, cols, [])[0], True, "the book decides on it")
        diff = xs_book.same(late, kept, symbols, verdict=L._bars_verdict)   # ... and the morning's reading has it
        self.assertEqual((diff["mismatch"], diff["late"]), ([], [symbols[at]]), "and its own audit calls it a note")
        path = self.live_db([("fam@1:r", [])])
        with mock.patch.object(xs_book, "kept", return_value=(symbols, late)):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["source"], out["mismatch"], out["late"], out["live"]),
                         (True, "kept", 0, 1, {"fam@1:r": True}))
        # The rest of the late column is still held to the store: a price of an earlier session that differs is False.
        late.raw[40, at, 3] += 0.01
        with mock.patch.object(xs_book, "kept", return_value=(symbols, late)):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["mismatch"], out["late"], out["live"]), (False, 1, 1, {"fam@1:r": False}))
        # A FRESH fetch at night that lacks a bar the store holds is no late bar: it is a session that differs.
        with mock.patch.object(P, "fetch_asof", side_effect=lambda *a, **k: {}):
            none = self.check()                           # the venue serves no bar at all: every column differs
        self.assertEqual((none["source"], none["late"], none["equal"], none["mismatch"]), ("fetch", 0, False, 12 + self.N))

    def test_a_member_the_1620_columns_lacked_is_counted_and_fails_no_decision(self):
        """Tonight's universe run applied a change row dated on or before the day (a row is applied after two reads
        20 hours apart): the store's day has a member the kept 16:20 columns did not. The decision is rebuilt over THE
        COLUMNS IT HAD; the membership gap is a count."""
        path = self.live_db([("fam@1:r", [])])
        with mock.patch.object(xs_book, "kept", return_value=self.kept_file(drop=("QAAC",))):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["source"], out["live"], out["absent"], out["mismatch"]),
                         (True, "fetch", {"fam@1:r": True}, 1, 0))
        # The other way round: a column of the decision's the store's day no longer lists is rebuilt from the store's
        # own column all the same (its asset is known), and one the store knows no asset for is counted.
        symbols, kept = self.kept_file(extra=("QAAC",))
        ghost = (*symbols[:-1], "ZZZZ")
        with mock.patch.object(xs_book, "kept", return_value=(ghost, kept)):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["live"], out["absent"]), (True, {"fam@1:r": True}, 1))
        # And a price of a column it had that differs is still False.
        short = self.kept_file(drop=("QAAC",))
        short[1].raw[40, 14, 3] += 0.01
        with mock.patch.object(xs_book, "kept", return_value=short):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["live"], out["absent"]), (False, {"fam@1:r": False}, 1))

    def test_a_failed_decide_that_read_no_bars_is_no_row_of_the_i6(self):
        """A17: a held name is halted, the fetch is not whole by 17:00, the book writes a "failed" row with no bars
        and keeps no file: a hold day the House could not ask is an alarm and never an exit. The I6 read "a decision
        with no kept fetch cannot be shown equal": False, and the whole basket was sold two opens later."""
        path = self.live_db([])
        db = sqlite3.connect(path)
        db.execute("INSERT INTO eq_rebalances (instance, family, version, decided_day, exec_day, at, called, targets, "
                   "n_names, n_sells, n_buys, n_skipped, status, why, created_at) VALUES ('fam@1:r', 'fam', 1, ?, "
                   "'2022-04-01', 'open', 0, '[]', 0, 0, 0, 0, 'failed', 'the panel''s bars are not whole', 0)",
                   (LAST.isoformat(),))
        db.commit()
        db.close()
        with mock.patch.object(xs_book, "kept", return_value=None):
            out = self.check(live=path)
        self.assertEqual((out["equal"], out["source"], out["live"]), (True, "fetch", {}))

    def test_the_notes_are_a_warning_and_the_receipt_counts_them(self):
        notes = {"day": LAST.isoformat(), "store_sha": None, "fetch_sha": None, "equal": True, "bytes_equal": None,
                 "source": "kept", "live": {"a": True, "b": None}, "columns": 36, "mismatch": 0, "volume": 0,
                 "blanked": 0, "late": 2, "absent": 1, "why": None}
        with mock.patch.object(P, "i6_check", return_value=notes):
            receipt, ctx = self.run_job(NOW + 3600)
        self.assertEqual((receipt["i6"]["equal"], receipt["i6"]["late"], receipt["i6"]["absent"], receipt["i6"]["live"],
                          receipt["i6"]["live_equal"], receipt["i6"]["live_unread"]), (True, 2, 1, 2, 1, 1))
        [note] = [a for a in ctx.alerts if "nightly I6 counted" in a["text"]]
        self.assertEqual(note["level"], "warning")
        self.assertEqual([a for a in ctx.alerts if "nightly I6 is False" in a["text"]], [])

    def test_no_book_no_table_and_no_row_are_no_live_part(self):
        self.assertEqual(self.check(live=self.state / "absent.sqlite")["live"], {})
        empty = self.state / "empty.sqlite"
        sqlite3.connect(empty).close()
        self.assertEqual(self.check(live=empty)["live"], {})
        self.assertEqual(self.check(live=self.live_db([]))["live"], {})

    def test_the_two_ctx_shas_are_built_under_one_run_key_and_one_aid_set(self):
        """With package C's ctx in the tree the two sides' `ctx_bytes(build(...))` are hashed. Here the ctx's
        functions are stand-ins that record what each side was built from."""
        built = []

        def inputs_from_arrays(days, raw, adj, **common):
            built.append({"days": days, "raw": raw, "adj": adj, **common})
            return len(built) - 1

        def ids_for(aids, salt, *, table):
            self.assertEqual(table, sorted(int(a) for a in U.read_universe(self.root)["assets"]))
            return np.array([(int(a) * 7919 + salt[0]) % 1009 for a in aids], dtype=np.int32)
        stand_ins = (
            (xs_store, "read_salt", lambda root: (Path(root) / xs_store.UNIVERSE_DIR / xs_store.SALT_FILE).read_bytes()),
            (xs_store, "run_salt", lambda salt, key: hashlib.sha256(salt + key.encode()).digest()),
            (xs_store, "ids_for", ids_for), (xs_store, "dither_key", lambda salt: b"dither" + salt[:4]),
            (xs_store, "sector_perm", lambda salt: np.arange(11, dtype=np.int8)),
            (xs_program, "parse_needs", lambda raw: dict(raw)), (xs_ctx, "inputs_from_arrays", inputs_from_arrays),
            (xs_ctx, "build", lambda inputs: inputs),
            (xs_ctx, "ctx_bytes", lambda k: np.round(built[k]["raw"], 4).tobytes() + np.round(built[k]["adj"], 4).tobytes()))
        for target, name, fake in stand_ins:
            patch = mock.patch.object(target, name, fake)
            patch.start()
            self.addCleanup(patch.stop)
        out = self.check()
        self.assertEqual((out["equal"], out["bytes_equal"], out["why"]), (True, True, None))
        self.assertRegex(out["store_sha"], r"^[0-9a-f]{64}$")
        self.assertEqual(out["store_sha"], out["fetch_sha"])
        store, fetch = built
        self.assertEqual((store["day"], len(store["days"]), store["raw"].shape), (LAST, 253, (253, 12 + self.N, 5)))
        self.assertEqual(store["days"][-1], eq_store.ordinal(LAST))
        for key in ("ids", "elig0", "sector_perm"):
            self.assertTrue(np.array_equal(store[key], fetch[key]), key)
        self.assertEqual((store["dither_key"], store["needs"]), (fetch["dither_key"], P.I6_NEEDS))
        self.assertEqual(store["ids"].tolist(), sorted(store["ids"].tolist()), "the member columns in ascending id")
        self.assertEqual(store["elig0"].tolist(), [False] * 12 + [True] * self.N)
        self.assertEqual((store["cash"], store["equity"], store["budget"]), (float(xs_config.XS_SLEEVE_USD),) * 3)
        company = next(c for c in self.market.companies if c.name == "co-QAAB")
        company.dividends[D(2022, 4, 1)] = 0.11
        self.market.today = D(2022, 4, 1)
        out = self.check()
        self.assertEqual((out["equal"], out["bytes_equal"]), (True, False),
                         "the vendor's cents: equal bars, and a ctx that is not byte for byte the same")

    def test_the_bars_verdict_stands_alone_until_the_ctx_is_built_and_the_shas_come_with_it(self):
        """In a tree without package C's ctx the I6 is the bars' verdict and says so; with it, the same call hashes
        both sides, and one vintage on both gives the same bytes."""
        out = self.check()
        self.assertIs(out["equal"], True)
        if out["store_sha"] is None:
            self.assertEqual((out["fetch_sha"], out["bytes_equal"]), (None, None))
            self.assertIn("not built", out["why"])
        else:
            self.assertRegex(out["store_sha"], r"^[0-9a-f]{64}$")
            self.assertEqual((out["fetch_sha"], out["bytes_equal"], out["why"]), (out["store_sha"], True, None))


# ================================================================================================ the job
class TheJob(Fixture):
    def test_the_first_run_fetches_everything_and_writes_the_store(self):
        receipt, ctx = self.run_job()
        self.assertTrue(receipt.get("ok"), receipt)
        days = [d for d, _ in U.store_sessions(LAST)]
        self.assertEqual((receipt["mode"], receipt["sessions"], receipt["assets"], receipt["members"],
                          receipt["fetched_through"]), ("full", len(days), self.N, self.N, LAST.isoformat()))
        panel = self.panel()
        self.assertEqual((panel.days, panel.aids), (days, [*range(1, 13), *range(100, 100 + self.N)]))
        self.assertEqual((panel.raw.shape, panel.adj.shape), ((len(days), 12 + self.N, 5), (len(days), 12 + self.N, 4)))
        self.assertEqual(panel.early.tolist(), [e for _, e in U.store_sessions(LAST)])
        company = next(c for c in self.market.companies if c.name == "co-QAAC")
        k, row = self.column(panel, "QAAC"), days.index(D(2019, 6, 3))
        self.assertEqual(panel.raw[row, k].tolist(), list(company.raw(D(2019, 6, 3), self.market.number[D(2019, 6, 3)])))
        xlc = panel.aids.index(aid_of(self.table, "XLC"))
        self.assertTrue(np.isnan(panel.raw[days.index(D(2018, 6, 18)), xlc]).all(), "NaN where no bar")
        self.assertTrue(np.isfinite(panel.raw[days.index(D(2018, 6, 19)), xlc]).all())
        self.assertFalse(panel.member[:, :12].any())
        self.assertTrue(panel.member[:, 12:].all())
        self.assertTrue(panel.tradable[:, 12:].all() and not panel.tradable[:, :12].any())
        self.assertEqual(panel.hs.tolist(), [[0.0010, 0.0005]] * (12 + self.N), "no spreads file: the fallback")
        manifest = panel.manifest
        self.assertEqual((manifest["fetched_through"], manifest["full_at"], manifest["live_from"], manifest["revisions"],
                          manifest["hs_share"]), (LAST.isoformat(), LAST.isoformat(), None, 0, 0.0))
        self.assertEqual(manifest["vanished"], [])
        self.assertEqual(manifest["audit"]["mode"], "full")

    def test_the_verdict_fails_closed_on_a_store_that_holds_no_judged_year(self):
        receipt, ctx = self.run_job()
        self.assertEqual((receipt["verdict"], receipt["train_years_ok"]), ("insufficient", [2017, 2018, 2019, 2022]))
        self.assertEqual(receipt["coverage"], {str(y): 1.0 for y in (2016, 2017, 2018, 2019, 2021, 2022)})
        self.assertEqual(self.panel().manifest["verdict"], "insufficient")
        self.assertEqual([a["level"] for a in ctx.alerts if "coverage verdict" in a["text"]], ["critical"])

    def test_the_receipt_holds_counts_and_verdicts_never_a_price_or_a_ticker(self):
        receipt, ctx = self.run_job()
        text = json.dumps(receipt) + json.dumps(ctx.alerts)
        for ticker in (*self.names, *xs_config.REF):
            self.assertIsNone(re.search(rf"\b{ticker}\b", text), ticker)

        def numbers(value):
            if isinstance(value, dict):
                for item in value.values():
                    yield from numbers(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    yield from numbers(item)
            elif isinstance(value, float) and not isinstance(value, bool):
                yield value
        self.assertTrue(all(0.0 <= v <= 1.0 for v in numbers(receipt)), "every float is a share: no price, no return")

    def test_the_first_statement_is_the_quiet_window(self):
        xs_config.quiet.return_value = "a wall"
        receipt, _ = self.run_job()
        self.assertEqual(receipt, {"status": "skipped", "why": "a wall"})
        xs_config.quiet.assert_called_once_with(NOW, float(P.WALL_S))
        self.assertEqual(self.market.calls, [])
        self.assertFalse((self.root / xs_store.PANEL_DIR).exists())

    def test_without_c0_the_job_is_skipped_never_a_crash(self):
        xs_config.quiet.side_effect = NotImplementedError("a stub")
        self.assertEqual(self.run_job()[0]["status"], "skipped")
        self.assertEqual(self.market.calls, [])
        xs_config.quiet.side_effect = None
        with mock.patch.object(xs_store, "write_panel", side_effect=NotImplementedError("a stub")):
            receipt, _ = self.run_job()
        self.assertEqual(receipt["status"], "skipped")
        self.assertIn("write_panel is not built", receipt["why"])

    def test_no_universe_is_a_skip_and_a_damaged_one_a_failure(self):
        state = Path(self.tmp.name) / "bare"
        state.mkdir()
        ctx = Context("equity_panel", root=state, due_at=NOW, clock=lambda: NOW, gateway=self.market, config={},
                      settings_value={})
        self.assertEqual(P.run(ctx)["status"], "skipped")
        (self.root / xs_store.UNIVERSE_DIR / U.ASSETS_FILE).write_text("{}")
        self.assertEqual(self.run_job()[0]["status"], "failed")
        self.assertEqual(self.market.calls, [])

    def test_a_ref_column_that_fails_e1s_audit_fails_the_run_and_writes_nothing(self):
        spy = next(c for c in self.market.companies if c.name == "ref-SPY")
        spy.last = D(2019, 6, 28)    # the calendar symbol's bars end: sessions with no SPY bar
        receipt, _ = self.run_job()
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("a REF column fails E1's audit (calendar (2016-2019), calendar (2021-2022))", receipt["error"])
        self.assertFalse((self.root / xs_store.PANEL_DIR).exists())
        spy.last = None
        self.assertEqual(P.ref_audit(*self.ref_arrays()), [])
        spy.bad = {D(2021, 6, 2)}
        self.assertEqual(P.ref_audit(*self.ref_arrays()), ["ohlc (2021-2022)"])

    def ref_arrays(self):
        calendar = U.store_sessions(LAST)
        days = [d for d, _ in calendar]
        grid = P.Grid(days, list(range(1, 13)))
        wanted = P.requests({a: r for a, r in self.table.items() if r["ref"]}, days)
        P._fetch_into(grid, self.market, wanted, sleep=lambda s: None, count={})
        return days, [e for _, e in calendar], grid.raw, grid.adj

    def test_a_ref_fund_is_read_span_by_span_so_a_year_of_dividends_across_2020_is_no_split(self):
        """SPY's own adjustment ratio steps over the 2020 gap by a year of dividends: E1's audit run across the gap
        would call it a split the raw close does not show."""
        xle = next(c for c in self.market.companies if c.name == "ref-XLE")
        for day in (D(2021, 3, 22), D(2021, 6, 21), D(2021, 9, 20), D(2021, 12, 20)):
            xle.dividends[day] = 1.2
        days, early, raw, adj = self.ref_arrays()
        k, gap = xs_config.REF.index("XLE"), days.index(D(2021, 1, 4))
        step = (raw[gap - 1, k, 3] / adj[gap - 1, k, 3]) / (raw[gap, k, 3] / adj[gap, k, 3])
        self.assertAlmostEqual(step, 1.0, delta=1e-3)
        xle.dividends = {D(2021, 1, 4): 4.0}   # the whole year's, on the first session after the gap
        days, early, raw, adj = self.ref_arrays()
        step = (raw[gap - 1, k, 3] / adj[gap - 1, k, 3]) / (raw[gap, k, 3] / adj[gap, k, 3])
        self.assertGreater(abs(step - 1.0), equity_data.SPLIT_JUMP, "a jump E1's rule would refuse across the gap")
        self.assertEqual(P.ref_audit(days, early, raw, adj), [])

    def test_tradable_is_true_until_the_universe_deploy_then_the_constitutions_list_a_row_a_session(self):
        with mock.patch.object(P, "_stock_universe", return_value={"QAAA", "QAAB"}):
            receipt, _ = self.run_job()
        self.assertIsNone(receipt["live_from"], "2 of 24 members: the 18-name universe of E1 is not the deploy")
        self.assertTrue(self.panel().tradable[:, 12:].all())
        deployed = set(self.names) - {"QAAC"}
        self.market.today = D(2022, 4, 1)
        with mock.patch.object(P, "_stock_universe", return_value=deployed):
            receipt, _ = self.run_job(NOW + DAY)
        self.assertEqual(receipt["live_from"], "2022-04-01", "the first run that reads the grown universe")
        panel = self.panel()
        k = self.column(panel, "QAAC")
        self.assertTrue(panel.tradable[:-1, 12:].all(), "every session before it stays True")
        self.assertEqual(panel.tradable[-1, 12:].tolist(), [a != panel.aids[k] for a in panel.aids[12:]])
        self.market.today = D(2022, 4, 4)
        with mock.patch.object(P, "_stock_universe", return_value=set(self.names) - {"QAAD"}):
            receipt, _ = self.run_job(NOW + 4 * DAY)
        panel = self.panel()
        self.assertEqual(receipt["live_from"], "2022-04-01")
        self.assertFalse(panel.tradable[-2, k], "a row once written is never rewritten")
        self.assertTrue(panel.tradable[-1, k])
        self.assertFalse(panel.tradable[-1, self.column(panel, "QAAD")])
        self.assertFalse(panel.tradable[:, :12].any())

    def test_the_spreads_file_becomes_the_stores_half_spreads_and_hs_share(self):
        aids = [aid_of(self.table, t) for t in self.names]
        names = {str(a): {"open_bp": 6.0, "close_bp": 4.0, "n_open": 9, "n_close": 9} for a in aids[:18]}
        (self.root / P.SPREADS_FILE).write_text(json.dumps({"version": "xs-spreads-v1", "names": names,
                                                            "default": {"open_bp": 11.0, "close_bp": 7.0}}))
        receipt, _ = self.run_job()
        panel = self.panel()
        self.assertEqual(receipt["hs_share"], 0.75)
        self.assertEqual(panel.manifest["hs_share"], 0.75)
        self.assertEqual(panel.hs[self.column(panel, self.names[0])].tolist(), [0.0006, 0.0004])
        self.assertEqual(panel.hs[self.column(panel, self.names[20])].tolist(), [0.0011, 0.0007])

    def test_the_coverage_floor_is_the_lanes_own_setting_inside_its_bound(self):
        """The review's spec-5: `elane.panel.coverage_min` (the lane's block, its bounds, its documents) was read by
        nothing; the job read ops.json's `equity_panel.coverage_min`, so tightening the lane's key changed no
        verdict."""
        def switch(value) -> None:
            (self.state / "swarm.json").write_text(json.dumps({"elane": {"panel": {"mode": "train", "coverage_min": value}}}),
                                                   encoding="utf-8")

        with mock.patch.object(P, "coverage", wraps=P.coverage) as spy:
            self.run_job()
            self.assertEqual(spy.call_args.kwargs["floor"], 0.97, "the default")
            switch(0.99)
            self.run_job(NOW + 60)
            self.assertEqual(spy.call_args.kwargs["floor"], 0.99, "the captain's tighter floor is the job's")
            switch(0.5)
            self.run_job(NOW + 120)
            self.assertEqual(spy.call_args.kwargs["floor"], 0.97, "a value outside its bound reads as its default")
            switch(0.99)
            self.run_job(NOW + 180, settings={"equity_panel": {"coverage_min": 0.98}})
            self.assertEqual(spy.call_args.kwargs["floor"], 0.99, "ops.json holds no second copy of the lane's setting")
        self.assertEqual(P.coverage_floor(self.state), 0.99)
        self.assertEqual(P.coverage_floor(self.state / "nowhere"), 0.97)

    def test_a_store_that_does_not_match_its_manifest_is_fetched_whole_again(self):
        self.run_job()
        (self.root / xs_store.PANEL_DIR / "member.npy").write_bytes(b"not the file")
        with self.assertRaises(ValueError):
            P.load_panel(self.root)
        receipt, ctx = self.run_job(NOW + 60)
        self.assertEqual((receipt.get("ok"), receipt["mode"]), (True, "full"))
        self.assertEqual(len([a for a in ctx.alerts if "cannot be read" in a["text"]]), 1)
        self.assertIsNotNone(P.load_panel(self.root))

    def test_the_store_is_read_back_as_written(self):
        self.assertIsNone(P.load_panel(self.root))
        self.run_job()
        panel = self.panel()
        again = P.load_panel(self.root)
        for name in ("raw", "adj", "member", "tradable", "hs", "early"):
            self.assertTrue(np.array_equal(getattr(panel, name), getattr(again, name), equal_nan=True), name)
        self.assertEqual(panel.manifest["version"], "xs-panel-v1")


class TheRegistryRows(unittest.TestCase):
    """Patch 10 (league/swarm/e4_patches/A.md): the six job rows of E4-SPEC 13. The rows are read from the patch file
    itself, so what is held is what the integrator applies; once it is applied, the registry's own rows are held to it."""

    PATCH = REPO / "league" / "swarm" / "e4_patches" / "A.md"
    #: E4-SPEC 13: name -> (triggers, grace seconds, cpu, wall).
    SPEC = {
        "equity_universe": ((("start",), ("daily", 1, 40)), 3 * 3600, 120, 900),
        "equity_panel": ((("after", "equity_universe"),), 3 * 3600, 600, 3300),
        "equity_spreads": ((("daily", 6, 30),), 6 * 3600, 300, 3000),
        "equity_neff": ((("monthly", 5, 10, 0),), 6 * 3600, 600, 900),
        "french": ((("monthly", 5, 11, 0),), 6 * 3600, 60, 300),
        "xs_zero_edge": ((("weekly", 6, 6, 0), ("weekly", 6, 8, 0), ("weekly", 6, 10, 0), ("weekly", 6, 12, 0)),
                         100 * 60, 2400, 3000),
    }
    #: THE REVIEW'S TWO TRIGGERS (the registry differs from the patch's record in these and nothing else).
    #: `equity_universe` has no at-start trigger (live-9: at a House start before an open the chain's whole fetch held
    #: the one ops child past the pre-open's grace); `equity_panel` has its own daily time, fifteen minutes after the
    #: universe job's (live-4: its only trigger was `after("equity_universe")`, so a night the universe job failed
    #: fetched no bars, ran no I6 and raised none of the panel job's own alarms).
    REVIEWED = {"equity_universe": (("daily", 1, 40),), "equity_panel": (("daily", 1, 55),)}

    @classmethod
    def setUpClass(cls):
        from league.ops import registry

        cls.registry = registry
        blocks = re.findall(r"```diff\n(.*?)```", cls.PATCH.read_text(encoding="utf-8"), flags=re.S)
        cls.diff = next(b for b in blocks if b.startswith("--- a/league/ops/registry.py"))
        lines = cls.diff.splitlines()
        cls.added = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
        cls.context = [line[1:] for line in lines if line.startswith(" ")]
        scope = {name: getattr(registry, name) for name in ("Job", "S", "HOUR", "MINUTE")}
        cls.rows = eval("(\n" + "\n".join(cls.added) + "\n)", scope)  # noqa: S307 - the repository's own patch file

    @staticmethod
    def trigger(t) -> tuple:
        return {"start": ("start",), "after": ("after", t.job), "daily": ("daily", t.at.hour, t.at.minute)}.get(
            t.kind, (t.kind, t.weekday, t.at.hour, t.at.minute))

    def test_the_six_rows_are_the_specs_table(self):
        self.assertEqual([job.name for job in self.rows], list(self.SPEC))
        for job in self.rows:
            triggers, grace, cpu, wall = self.SPEC[job.name]
            self.assertEqual(job.module, f"league.ops.{job.name}")
            self.assertEqual(tuple(self.trigger(t) for t in job.triggers), triggers, job.name)
            self.assertEqual((job.grace, job.cpu, job.wall), (grace, cpu, wall), job.name)
            self.assertEqual((job.in_pause, job.paid, job.retry), (True, False, True), job.name)
            self.assertTrue(job.what and job.owner, job.name)

    def test_each_wall_is_the_figure_its_job_asks_the_quiet_windows_with(self):
        import importlib

        for job in self.rows:
            self.assertEqual(importlib.import_module(job.module).WALL_S, job.wall, job.name)
        self.assertEqual((P.WALL_S, U.WALL_S), (self.SPEC["equity_panel"][3], self.SPEC["equity_universe"][3]))

    def test_no_row_is_due_inside_a_session_of_either_season_and_every_wall_is_under_the_grants_grace(self):
        grant = self.registry.by_name()["grant"]
        for job in self.rows:
            self.assertLessEqual(job.wall + 5 * 60, grant.grace, f"{job.name}: an hourly grant waits behind it")
            for t in job.triggers:
                minutes = t.at.hour * 60 + t.at.minute
                inside = 12 * 60 + 55 <= minutes <= 21 * 60 + 5
                if t.kind == "daily":
                    self.assertFalse(inside, job.name)
                elif t.kind in ("weekly", "monthly"):
                    self.assertGreaterEqual(t.weekday, 5, f"{job.name}: a weekend job")
                elif t.kind == "after":
                    self.assertIn(t.job, self.SPEC)

    def test_the_patch_fits_the_registry_and_the_registry_holds_it_once_applied(self):
        source = Path(self.registry.__file__).read_text(encoding="utf-8").splitlines()
        at = 0
        for line in self.context:   # the diff's context is the registry's own text, in order: the anchor
            at = source.index(line, at) + 1
        self.assertIn(")", [line.strip() for line in self.context], "the rows end the JOBS tuple")
        have = self.registry.by_name()
        present = [name for name in self.SPEC if name in have]
        if present:   # applied: all six, exactly these, and last; the review's two triggers and nothing else differ
            import dataclasses

            self.assertEqual(present, list(self.SPEC))
            for row in self.rows:
                mine = have[row.name]
                self.assertEqual(tuple(self.trigger(t) for t in mine.triggers),
                                 self.REVIEWED.get(row.name, self.SPEC[row.name][0]), row.name)
                self.assertEqual(dataclasses.replace(mine, triggers=row.triggers), row, row.name)
            self.assertEqual([job.name for job in self.registry.JOBS][-6:], list(self.SPEC))
            starts = [job.name for job in self.registry.JOBS if job.name in self.SPEC
                      and any(t.kind in ("start", "after") for t in job.triggers)]
            self.assertEqual(starts, [], "no E4 job starts with the House or behind another job's success")
        else:         # not yet: no name is taken, and the rows go after every job the registry has
            self.assertEqual(set(self.SPEC) & set(have), set())
            self.assertIn("dlane", have)
        names = [job.name for job in self.registry.JOBS]
        self.assertEqual(len(names), len(set(names)))


class TheJobFitsItsMemory(unittest.TestCase):
    """The review's live-5, AT THE REAL PANEL'S SIZE (700 assets x 2,455 sessions) UNDER THE OPS CHILD'S OWN LIMIT
    (`league.ops.__main__.limit`: the address space is capped 500 MB above the child's start, before the job's first
    import). The daily run mapped the old store twice (`run`, and `incremental` again) beside the grid being built:
    three copies of about 120 MB, 14 to 24 MB of room for a night's refetches, and a night with 25 names ex-dividend
    failed with a MemoryError, left its restatements to the next night, and failed again. The world is
    `league/tests/equity_panel_budget.py`'s (a formula, cheap to build); the job runs in a child of this test."""

    EXTRA_MB = 500          # the registry row's default: `league.ops.runner` starts the child with it
    RESTATED = 60           # open names ex-dividend on the night (a quarter-end's worth)
    #: Of the cap, the daily run leaves at least this much address space unused (measured on the desk's Python 3.14 and
    #: 3.11: about 140 MB, whatever the number of names restated). Mapped twice it left under 25 at best, and none on
    #: this night.
    HEADROOM_MB = 100

    def test_a_daily_run_with_sixty_names_ex_dividend_fits_with_room_to_spare(self):
        import subprocess
        import sys

        from league.ops import registry, runner
        from league.tests import equity_panel_budget as B

        self.assertEqual(runner.EXTRA_MB, self.EXTRA_MB, "the address space the runner gives every job's child")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name) / "state"
        built = B.build(state)
        self.assertEqual((built["sessions"], built["assets"]), (2454, B.N_OPEN + B.N_ENDED))
        env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1",
               "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}    # (as `league.ops.runner` starts its child)
        done = subprocess.run([sys.executable, "-c", B.BOOT, str(state), str(self.EXTRA_MB), str(self.RESTATED)],
                              cwd=REPO, env=env, capture_output=True, text=True, timeout=registry.by_name()["equity_panel"].wall)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        out = json.loads(done.stdout.strip().splitlines()[-1])
        receipt = out["receipt"]
        self.assertEqual((receipt.get("ok"), receipt.get("mode"), receipt.get("sessions"), receipt.get("assets")),
                         (True, "incremental", 2455, B.N_OPEN + B.N_ENDED), out)
        self.assertEqual((receipt["refetched"], receipt["fetched_through"], receipt["verdict"], receipt["revisions"]),
                         (self.RESTATED, B.LAST.isoformat(), "ok", 0), out)
        self.assertEqual((out["i6"]["equal"], out["i6"]["mismatch"]), (True, 0), out)
        self.assertGreater(out["cap_mb"], 0, "the limit was set before the job's imports")
        self.assertLessEqual(out["vm_peak_mb"], out["cap_mb"] - self.HEADROOM_MB,
                             f"the daily run peaked at {out['vm_peak_mb']} MB of a cap of {out['cap_mb']} MB")
        self.assertEqual(out["alerts"], [])

    def test_one_reader_maps_the_old_store_at_a_time_and_a_whole_history_is_asked_eight_names_a_request(self):
        fixture = Fixture("ctx")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        receipt, _ = fixture.run_job()
        self.assertTrue(receipt.get("ok"), receipt)
        held: list[P.Panel] = []
        load = P.load_panel

        def loading(root):
            for panel in held:
                self.assertEqual(panel.raw.shape[0], 0, "a second reader mapped the store while the first still held it")
            panel = load(root)
            if panel is not None:
                held.append(panel)
            return panel

        company = next(c for c in fixture.market.companies if c.name == "co-QAAB")
        company.dividends[LAST] = 0.11                         # restated tonight: fetched again whole
        fixture.market.requests.clear()
        asked_while_mapped = []
        get = fixture.market.get

        def watched(path, params=None):
            asked_while_mapped.append(any(panel.raw.shape[0] for panel in held))
            return get(path, params)

        with mock.patch.object(P, "load_panel", loading), mock.patch.object(fixture.market, "get", watched):
            receipt, _ = fixture.run_job(NOW + 3600)
        self.assertEqual((receipt["ok"], receipt["mode"], receipt["refetched"]), (True, "incremental", 1), receipt)
        self.assertEqual(len(held), 2, "the job's own reading of the manifest and masks, and the daily run's bars")
        self.assertEqual(asked_while_mapped.count(True), 0, "no answer is asked for while the old store is mapped")
        self.assertEqual(P.WHOLE_BATCH, 8)
        whole = P.requests(fixture.table, fixture.panel().days, batch=P.WHOLE_BATCH)
        self.assertEqual(max(len(r.symbols) for r in whole), 8)
        with mock.patch.object(P, "requests", wraps=P.requests) as planned:
            P.full(fixture.root, fixture.market, LAST, sleep=lambda s: None)
        self.assertEqual(planned.call_args.kwargs.get("batch"), P.WHOLE_BATCH)


class TheWalls(unittest.TestCase):
    def test_each_jobs_own_wall_and_the_constants_of_the_contract(self):
        self.assertEqual((P.WALL_S, U.WALL_S), (3300, 900))
        self.assertEqual((P.TRIES, P.BACKOFF_S, P.INCREMENTAL_SESSIONS, P.FULL_EVERY_DAYS), (3, (5, 20), 7, 6.5))
        self.assertEqual((P.ACCEPT_SHARE, P.ACCEPT_FIRST, P.REUSED_USD, P.INSANE_SHARE, P.SECOND_READ_GAP,
                          P.MASKED_MEMBERS_MAX, P.REVISIONS_ALARM), (0.95, 5, 5_000_000.0, 0.01, 0.02, 0.05, 20))
        self.assertEqual(P.I6_NEEDS, {"panel": "sp500", "history": 252, "max_names": 12, "rebalance": "weekly",
                                      "weekday": 0, "max_hold_sessions": 60})
        self.assertEqual(P.BATCH, xs_book.FETCH_CHUNK)
        self.assertLessEqual(P.BATCH * xs_config.DERIVE_SESSIONS, P.PAGE_LIMIT, "a chunk of the I6's fetch is one page")
        self.assertEqual(math.ceil(xs_config.MAX_HOLD_CAP * 7 / 5), 84)
        self.assertGreater(P.KEEP_ENDED_DAYS, 84, "a lot of a name that left keeps a bar until its hold cap")


if __name__ == "__main__":
    unittest.main()
