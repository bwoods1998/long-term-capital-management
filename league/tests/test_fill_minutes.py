"""Release E3, package D: league/ops/fill_minutes.py, the send-minute 1Min bars (D10's live-like price).

The windows on a normal and a half day in both seasons; the first whole minute at or after each send; the paging; the
VWAP and its hlc3 fallback; the file (atomic, 0600, its directories 0700); the job's backfill, its two switches, the
days it never fetches and what a gateway error leaves behind. Every bar here is invented (a fake gateway); no market
data. `forward_db.cfg` and `forward_db.t0` are package A's and are stubs on this branch: the job's tests use FAKES of
them, written to the stubs' docstrings (`fake_cfg`, `fake_t0`)."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import config, schedule
from league.ops import equity_data, fill_minutes, forward_db
from league.ops.context import Context, GatewayError

NY = schedule.NY
EDT_DAY = dt.date(2026, 10, 12)      # a full session in daylight time (the first forward day)
EST_DAY = dt.date(2026, 12, 1)       # a full session in standard time
EDT_HALF = dt.date(2025, 7, 3)       # a 13:00 close in daylight time
EST_HALF = dt.date(2026, 11, 27)     # a 13:00 close in standard time


def fake_cfg(settings):
    """A FAKE of package A's `forward_db.cfg`, to its stub's docstring: every key of `DEFAULTS`, each value inside its
    bound, a malformed value its code default, an unreadable block the defaults (mode "off")."""
    out = dict(forward_db.DEFAULTS)
    try:
        raw = settings["elane"]["forward"]
        items = dict(raw).items()
    except Exception:  # noqa: BLE001 - an unreadable block is "off"
        return out
    for key, value in items:
        if key == "mode" and value in forward_db.MODES:
            out[key] = value
        elif key in ("fill_minutes", "twins") and isinstance(value, bool):
            out[key] = value
        elif key in forward_db.BOUNDS and not isinstance(value, bool) and isinstance(value, (int, float)) \
                and forward_db.BOUNDS[key][0] <= value <= forward_db.BOUNDS[key][1]:
            out[key] = value
    return out


def fake_t0():
    """A FAKE of package A's `forward_db.t0` (D1): the session after the look cap."""
    return schedule.next_session(config.LOOK_CAP)


def at(day: dt.date, hour: int, minute: int = 0) -> float:
    """Epoch seconds of a New York wall time."""
    return dt.datetime.combine(day, dt.time(hour, minute), NY).timestamp()


def minute_row(stamp: str, **over) -> dict:
    return {"t": stamp, "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.25, "v": 1200, "vw": 100.125, "n": 14, **over}


class Gateway:
    """A fake of the gateway's bars route: one invented bar a minute from `start` THROUGH `end` (the venue's `end` is
    inclusive) for every symbol asked for and not `absent`; `fail` (a day's ISO prefix) raises as the gateway does;
    `pages` cuts each answer into pages of that many symbols; `unready` (a day's ISO prefix) answers no bar at all."""

    def __init__(self, *, absent=(), fail=None, pages=None, unready=None, row=minute_row):
        self.absent, self.fail, self.pages, self.unready, self.row = set(absent), fail, pages, unready, row
        self.calls: list[dict] = []

    def get(self, path, params):
        self.calls.append({"path": path, **params})
        if self.fail and params["start"].startswith(self.fail):
            raise GatewayError(f"GET {path}: HTTP 503 fake", status=503)
        if self.unready and params["start"].startswith(self.unready):
            return {"bars": {}, "next_page_token": None}
        symbols = [s for s in params["symbols"].split(",") if s not in self.absent]
        first = int(params.get("page_token") or 0)
        size = self.pages or len(symbols) or 1
        start = dt.datetime.fromisoformat(params["start"].replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(params["end"].replace("Z", "+00:00"))
        bars = {}
        for symbol in symbols[first:first + size]:
            rows, t = [], start
            while t <= end:
                rows.append(self.row(t.strftime("%Y-%m-%dT%H:%M:%SZ")))
                t += dt.timedelta(minutes=1)
            bars[symbol] = rows
        more = first + size < len(symbols)
        return {"bars": bars, "next_page_token": str(first + size) if more else None}


class TheWindows(unittest.TestCase):
    def test_the_days_are_what_the_test_says_they_are(self):
        self.assertEqual([schedule.moments(d).early for d in (EDT_DAY, EST_DAY, EDT_HALF, EST_HALF)],
                         [False, False, True, True])

    def test_a_full_session_in_both_seasons(self):
        self.assertEqual(fill_minutes.windows(EDT_DAY), (("2026-10-12T13:30:00Z", "2026-10-12T13:35:00Z"),
                                                         ("2026-10-12T19:50:00Z", "2026-10-12T20:00:00Z")))
        self.assertEqual(fill_minutes.windows("2026-12-01"), (("2026-12-01T14:30:00Z", "2026-12-01T14:35:00Z"),
                                                              ("2026-12-01T20:50:00Z", "2026-12-01T21:00:00Z")))

    def test_a_half_day_moves_the_second_window(self):
        self.assertEqual(fill_minutes.windows(EDT_HALF), (("2025-07-03T13:30:00Z", "2025-07-03T13:35:00Z"),
                                                          ("2025-07-03T16:50:00Z", "2025-07-03T17:00:00Z")))
        self.assertEqual(fill_minutes.windows(EST_HALF), (("2026-11-27T14:30:00Z", "2026-11-27T14:35:00Z"),
                                                          ("2026-11-27T17:50:00Z", "2026-11-27T18:00:00Z")))

    def test_the_widths_are_the_constants(self):
        (o0, o1), (c0, c1) = fill_minutes.windows(EDT_DAY)
        parse = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
        self.assertEqual((parse(o1) - parse(o0)).total_seconds(), fill_minutes.OPEN_MINUTES * 60)
        self.assertEqual((parse(c1) - parse(c0)).total_seconds(), fill_minutes.CLOSE_MINUTES * 60)
        self.assertEqual((fill_minutes.OPEN_MINUTES, fill_minutes.CLOSE_MINUTES), (5, 10))

    def test_a_day_that_is_not_a_session_has_no_window(self):
        for day in (dt.date(2026, 10, 10), "2026-12-25"):          # a Saturday; Christmas
            with self.assertRaises(ValueError):
                fill_minutes.windows(day)
            with self.assertRaises(ValueError):
                fill_minutes.bar_start(day, "open")


class TheSendMinute(unittest.TestCase):
    """D10: the first whole minute at or after the send instant."""

    def ny(self, day, at_):
        return fill_minutes.bar_start(day, at_).astimezone(NY).strftime("%H:%M:%S")

    def test_the_open_send_reads_0931_and_the_close_send_1555(self):
        self.assertEqual(self.ny(EDT_DAY, "open"), "09:31:00")
        self.assertEqual(self.ny(EDT_DAY, "close"), "15:55:00")
        self.assertEqual(self.ny(EST_DAY, "open"), "09:31:00")
        self.assertEqual(self.ny(EST_DAY, "close"), "15:55:00")
        self.assertEqual(fill_minutes.bar_start(EDT_DAY, "open"),
                         dt.datetime(2026, 10, 12, 13, 31, tzinfo=dt.timezone.utc))
        self.assertEqual(fill_minutes.bar_start(EST_DAY, "close"),
                         dt.datetime(2026, 12, 1, 20, 55, tzinfo=dt.timezone.utc))

    def test_a_half_day_sends_its_close_at_1255(self):
        self.assertEqual(self.ny(EDT_HALF, "close"), "12:55:00")
        self.assertEqual(self.ny(EST_HALF, "close"), "12:55:00")
        self.assertEqual(self.ny(EST_HALF, "open"), "09:31:00")

    def test_it_is_the_minute_at_or_after_the_send_never_before(self):
        for day in (EDT_DAY, EST_DAY, EDT_HALF, EST_HALF):
            m = schedule.moments(day)
            for at_, send in (("open", m.open_send), ("close", m.close_send)):
                start = fill_minutes.bar_start(day, at_).timestamp()
                self.assertEqual(start % 60, 0)
                self.assertTrue(0 <= start - send < 60, (day, at_))

    def test_both_send_minutes_lie_inside_the_fetched_windows(self):
        for day in (EDT_DAY, EST_DAY, EDT_HALF, EST_HALF):
            (o0, o1), (c0, c1) = fill_minutes.windows(day)
            self.assertTrue(o0 <= fill_minutes.bar_start(day, "open").strftime("%Y-%m-%dT%H:%M:%SZ") < o1)
            self.assertTrue(c0 <= fill_minutes.bar_start(day, "close").strftime("%Y-%m-%dT%H:%M:%SZ") < c1)

    def test_another_fill_point_is_refused(self):
        for bad in ("noon", "", None, "OPEN"):
            with self.assertRaises(ValueError):
                fill_minutes.bar_start(EDT_DAY, bad)

    def test_the_constitutions_order_path_sends_at_the_designs_instants(self):
        # The live book sends at the constitution's `equity_money.order_path` offsets; D10 reads `schedule.DEFAULTS`.
        # The two are held equal for every instant the forward record reads (the sends, and D12's 16:20 bars moment).
        from league.constitution import CONSTITUTION

        path = CONSTITUTION["equity_money"]["order_path"]
        for key in ("open_send_after_open_s", "close_send_before_close_s", "bars_after_close_s"):
            self.assertEqual(path[key], schedule.DEFAULTS[key], key)
        self.assertEqual((schedule.DEFAULTS["open_send_after_open_s"], schedule.DEFAULTS["close_send_before_close_s"]),
                         (30, 300))


class ThePaging(unittest.TestCase):
    def test_one_request_carries_the_contracts_parameters(self):
        gw = Gateway()
        start, end = fill_minutes.windows(EDT_DAY)[0]
        out = fill_minutes.fetch_minutes(gw, ["SPY", "BRK.B"], start, end)
        self.assertEqual(gw.calls, [{"path": equity_data.BARS, "symbols": "SPY,BRK.B", "timeframe": "1Min",
                                     "start": start, "end": end, "adjustment": "raw", "feed": "sip",
                                     "limit": fill_minutes.PAGE_LIMIT}])
        self.assertEqual(fill_minutes.BARS, equity_data.BARS)
        self.assertEqual(sorted(out), ["BRK.B", "SPY"])
        self.assertEqual(out["SPY"][0], ["2026-10-12T13:30:00Z", 100.0, 100.5, 99.5, 100.25, 1200.0, 100.125, 14])
        self.assertEqual(len(out["SPY"][0]), len(fill_minutes.FIELDS) + 1)
        self.assertEqual(fill_minutes.FIELDS, ("o", "h", "l", "c", "v", "vw", "n"))

    def test_every_page_is_read_and_every_symbol_is_a_key(self):
        gw = Gateway(pages=2, absent={"QQQ"})
        start, end = fill_minutes.windows(EDT_DAY)[1]
        out = fill_minutes.fetch_minutes(gw, ["SPY", "QQQ", "IWM", "DIA", "TLT"], start, end)
        self.assertEqual([c.get("page_token") for c in gw.calls], [None, "2"])
        self.assertEqual(sorted(out), ["DIA", "IWM", "QQQ", "SPY", "TLT"])
        self.assertEqual(out["QQQ"], [], "a symbol the venue has no bar of is an empty list")
        self.assertEqual(len(out["TLT"]), fill_minutes.CLOSE_MINUTES + 1, "the venue's end is inclusive")

    def test_the_rows_come_in_time_order_whatever_order_the_venue_sent(self):
        class Shuffled:
            def get(self, path, params):
                rows = [minute_row("2026-10-12T13:33:00Z"), minute_row("2026-10-12T09:31:00-04:00"),
                        minute_row("2026-10-12T13:32:00+00:00")]
                return {"bars": {"SPY": rows}}

        out = fill_minutes.fetch_minutes(Shuffled(), ["SPY"], "a", "b")
        self.assertEqual([r[0] for r in out["SPY"]],
                         ["2026-10-12T13:31:00Z", "2026-10-12T13:32:00Z", "2026-10-12T13:33:00Z"])

    def test_a_missing_or_malformed_field_is_null_never_a_guess(self):
        class Thin:
            def get(self, path, params):
                return {"bars": {"SPY": [{"t": "2026-10-12T13:31:00Z", "o": 1.0, "h": "2", "l": float("nan"), "c": True}]}}

        self.assertEqual(fill_minutes.fetch_minutes(Thin(), ["SPY"], "a", "b")["SPY"],
                         [["2026-10-12T13:31:00Z", 1.0, None, None, None, None, None, None]])

    def test_a_malformed_answer_is_refused(self):
        def answers(value):
            return type("G", (), {"get": lambda self, path, params: value})()

        for bad in (None, {}, [], {"bars": []}, {"bars": {"SPY": {}}}, {"bars": {"SPY": ["row"]}},
                    {"bars": {"SPY": [{"o": 1.0}]}}, {"bars": {"SPY": [{"t": "yesterday"}]}},
                    {"bars": {"SPY": [{"t": "2026-10-12T13:31:00"}]}},       # no zone
                    {"bars": {"SPY": [minute_row("2026-10-12T13:31:00Z"), minute_row("2026-10-12T09:31:00-04:00")]}}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                fill_minutes.fetch_minutes(answers(bad), ["SPY"], "a", "b")
        self.assertEqual(fill_minutes.fetch_minutes(answers({"bars": None}), ["SPY"], "a", "b"), {"SPY": []})

    def test_a_cursor_that_never_ends_is_refused(self):
        class Endless:
            calls = 0

            def get(self, path, params):
                Endless.calls += 1
                return {"bars": {}, "next_page_token": "again"}

        with self.assertRaises(ValueError):
            fill_minutes.fetch_minutes(Endless(), ["SPY"], "a", "b")
        self.assertEqual(Endless.calls, fill_minutes.MAX_PAGES)

    def test_inside_keeps_the_bars_that_start_in_the_half_open_window(self):
        start, end = fill_minutes.windows(EDT_DAY)[0]
        rows = fill_minutes.fetch_minutes(Gateway(), ["SPY"], start, end)["SPY"]
        kept = fill_minutes.inside(rows, start, end)
        self.assertEqual([r[0][11:16] for r in kept], ["13:30", "13:31", "13:32", "13:33", "13:34"])
        self.assertEqual(len(rows), 6)


class TheFile(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "state"
        self.root.mkdir()

    def bars(self, **over):
        return {"SPY": [["2026-10-12T13:31:00Z", 100.0, 100.5, 99.5, 100.25, 1200.0, 100.125, 14],
                        ["2026-10-12T19:55:00Z", 101.0, 101.5, 100.5, 101.25, 900.0, 101.125, 9]], **over}

    def test_it_is_written_where_and_as_the_contract_says(self):
        path = fill_minutes.write_day(self.root, EDT_DAY, self.bars(), fetched_at=1760000000.0)
        self.assertEqual(path, self.root / "equity-fill-minutes" / "2026" / "2026-10-12.json")
        self.assertEqual(path, fill_minutes.path_of(self.root, "2026-10-12"))
        doc = json.loads(path.read_text())
        self.assertEqual(sorted(doc), ["bars", "day", "fetched_at", "source", "version", "windows"])
        self.assertEqual((doc["version"], doc["day"], doc["source"], doc["fetched_at"]),
                         (1, "2026-10-12", "alpaca-sip-1Min", 1760000000.0))
        self.assertEqual(doc["windows"], [list(w) for w in fill_minutes.windows(EDT_DAY)])
        self.assertEqual(doc["bars"], self.bars())
        self.assertEqual(fill_minutes.read_day(self.root, EDT_DAY), doc)
        self.assertEqual(fill_minutes.days_on_disk(self.root), ["2026-10-12"])

    def test_the_file_is_owner_only_and_so_are_its_directories(self):
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        path = fill_minutes.write_day(self.root, EDT_DAY, self.bars(), fetched_at=1.0)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(path.parent.parent.stat().st_mode), 0o700)

    def test_the_write_is_atomic(self):
        path = fill_minutes.write_day(self.root, EDT_DAY, self.bars(), fetched_at=1.0)
        first = path.read_bytes()
        self.assertEqual([p.name for p in path.parent.iterdir()], ["2026-10-12.json"], "no temporary name is left")
        with mock.patch("league.ops.context.os.replace", side_effect=OSError("fake: the disk went away")):
            with self.assertRaises(OSError):
                fill_minutes.write_day(self.root, EDT_DAY, {"SPY": []}, fetched_at=2.0)
        self.assertEqual(path.read_bytes(), first, "a write that dies leaves the file it would have replaced")
        self.assertEqual(fill_minutes.read_day(self.root, EDT_DAY)["fetched_at"], 1.0)

    def test_rows_are_kept_in_time_order_and_a_field_that_is_not_a_number_is_null(self):
        late = ["2026-10-12T19:55:00Z", 1.0, 1.0, 1.0, 1.0, 1.0, float("nan"), None]
        early = ["2026-10-12T13:31:00Z", 2.0, 2.0, 2.0, 2.0, 2.0, float("inf"), 3]
        fill_minutes.write_day(self.root, EDT_DAY, {"QQQ": [late, early]}, fetched_at=1.0)
        rows = fill_minutes.read_day(self.root, EDT_DAY)["bars"]["QQQ"]
        self.assertEqual([r[0] for r in rows], [early[0], late[0]])
        self.assertEqual([r[6] for r in rows], [None, None])
        with self.assertRaises(ValueError):
            fill_minutes.write_day(self.root, EDT_DAY, {"QQQ": [["2026-10-12T13:31:00Z", 1.0]]}, fetched_at=1.0)

    def test_an_absent_or_unreadable_file_reads_none(self):
        self.assertIsNone(fill_minutes.read_day(self.root, EDT_DAY))
        self.assertEqual(fill_minutes.days_on_disk(self.root), [])
        path = fill_minutes.path_of(self.root, EDT_DAY)
        path.parent.mkdir(parents=True)
        for text in ("{not json", "[]", json.dumps({"version": 2, "day": "2026-10-12", "bars": {}}),
                     json.dumps({"version": 1, "day": "2026-10-13", "bars": {}}),
                     json.dumps({"version": 1, "day": "2026-10-12", "bars": []})):
            path.write_text(text)
            self.assertIsNone(fill_minutes.read_day(self.root, EDT_DAY), text)
        self.assertIsNone(fill_minutes.read_day(self.root, "not a day"))


class TheLiveLikePrice(unittest.TestCase):
    """D10: the send-minute bar's `vw` when finite and above zero, else (h + l + c) / 3, else None."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, rows):
        fill_minutes.write_day(self.root, EDT_DAY, rows, fetched_at=1.0)

    def test_the_vwap_of_the_send_minute(self):
        self.write({"SPY": [["2026-10-12T13:30:00Z", 9.0, 9.0, 9.0, 9.0, 1.0, 9.0, 1],          # the opening cross
                            ["2026-10-12T13:31:00Z", 100.0, 100.5, 99.5, 100.25, 1200.0, 100.125, 14],
                            ["2026-10-12T19:55:00Z", 101.0, 101.5, 100.5, 101.25, 900.0, 101.375, 9]]})
        self.assertEqual(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"), (100.125, "vw"))
        self.assertEqual(fill_minutes.livelike(self.root, "2026-10-12", "SPY", "close"), (101.375, "vw"))
        self.assertEqual(fill_minutes.LIVELIKE_FIELDS, ("vw", "hlc3"))

    def test_a_missing_vwap_falls_back_to_hlc3(self):
        for vw in (None, 0.0, -1.0, float("nan")):
            self.write({"SPY": [["2026-10-12T13:31:00Z", 100.0, 102.0, 99.0, 101.0, 1200.0, vw, 14]]})
            price, field = fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open")
            self.assertEqual(field, "hlc3", vw)
            self.assertAlmostEqual(price, (102.0 + 99.0 + 101.0) / 3.0, places=12)

    def test_a_missing_bar_is_none(self):
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"), "no file")
        self.write({"SPY": [["2026-10-12T13:32:00Z", 100.0, 100.5, 99.5, 100.25, 1200.0, 100.125, 14]], "QQQ": []})
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"), "no bar at 09:31")
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "close"), "no bar at 15:55")
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "QQQ", "open"), "a symbol with no bar")
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "IWM", "open"), "a symbol not in the file")

    def test_a_bar_with_no_usable_price_is_none(self):
        self.write({"SPY": [["2026-10-12T13:31:00Z", 100.0, None, 99.5, 100.25, 1200.0, None, 14]]})
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"))
        self.write({"SPY": [["2026-10-12T13:31:00Z", 100.0, 100.5, 0.0, 100.25, 1200.0, 0.0, 14]]})
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"))

    def test_another_fill_point_is_refused(self):
        with self.assertRaises(ValueError):
            fill_minutes.livelike(self.root, EDT_DAY, "SPY", "noon")


class TheJob(unittest.TestCase):
    """`run`: the backfill, the switches, the days never fetched, a gateway error."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "state"
        self.root.mkdir()
        self.settings({"mode": "record"})
        for name, fake in (("cfg", fake_cfg), ("t0", fake_t0)):
            patch = mock.patch.object(forward_db, name, fake)
            patch.start()
            self.addCleanup(patch.stop)

    def settings(self, forward):
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"forward": forward}}))

    def run_job(self, now: float, gateway: Gateway | None = None):
        gateway = gateway if gateway is not None else Gateway()
        ctx = Context("fill_minutes", root=self.root, due_at=now, config={}, clock=lambda: now, gateway=gateway,
                      settings_value={})
        return fill_minutes.run(ctx), gateway, ctx

    def test_the_fake_reads_the_settings_file(self):
        from league.swarm import settings as settings_mod

        self.assertEqual(fake_cfg(settings_mod.load(self.root, config={}))["mode"], "record")
        self.assertEqual(fake_cfg(None)["mode"], "off")
        self.assertEqual(fake_t0(), dt.date(2026, 10, 12))

    def test_the_first_forward_day_is_fetched_once_its_close_has_settled(self):
        out, gw, _ = self.run_job(at(EDT_DAY, 16, 39))
        self.assertEqual((out["days"], gw.calls), ([], []), "39 minutes after the close is too early")
        out, gw, ctx = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual(out["days"], ["2026-10-12"])
        self.assertEqual(out["symbols"], len(equity_data.universe()))
        self.assertEqual(out["bars"], len(equity_data.universe()) * (5 + 10))
        self.assertEqual(len(gw.calls), 2, "two requests a session")
        self.assertEqual([(c["start"], c["end"]) for c in gw.calls], list(fill_minutes.windows(EDT_DAY)))
        self.assertEqual(gw.calls[0]["symbols"].split(","), list(equity_data.universe()))
        self.assertEqual(ctx.alerts, [])
        doc = fill_minutes.read_day(self.root, EDT_DAY)
        self.assertEqual(sorted(doc["bars"]), sorted(equity_data.universe()))
        self.assertEqual([r[0][11:16] for r in doc["bars"]["SPY"]],
                         ["13:30", "13:31", "13:32", "13:33", "13:34",
                          "19:50", "19:51", "19:52", "19:53", "19:54", "19:55", "19:56", "19:57", "19:58", "19:59"])
        self.assertEqual(doc["fetched_at"], at(EDT_DAY, 16, 45))
        self.assertEqual(fill_minutes.livelike(self.root, EDT_DAY, "SPY", "open"), (100.125, "vw"))

    def test_nothing_is_fetched_for_a_day_before_t0(self):
        # Friday Oct 9 is the look cap, the session before the first forward day: its close has settled and it has no
        # file, and it is never asked for.
        out, gw, _ = self.run_job(at(dt.date(2026, 10, 13), 16, 45))
        self.assertEqual(out["days"], ["2026-10-12", "2026-10-13"])
        self.assertTrue(all(c["start"] >= "2026-10-12" for c in gw.calls))
        out, gw, _ = self.run_job(at(dt.date(2026, 10, 9), 18, 0))
        self.assertEqual((out["days"], gw.calls), ([], []))
        out, gw, _ = self.run_job(at(dt.date(2026, 10, 11), 12, 0))       # the Sunday of the deploy
        self.assertEqual((out["days"], gw.calls), ([], []))

    def test_the_backfill_fetches_the_last_ten_sessions_that_have_no_file(self):
        now = at(dt.date(2026, 10, 27), 16, 45)                           # twelve forward days have closed
        out, gw, _ = self.run_job(now)
        want = ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
                "2026-10-23", "2026-10-26", "2026-10-27"]
        self.assertEqual(out["days"], want)
        self.assertEqual(len(want), fill_minutes.BACKFILL_SESSIONS)
        self.assertEqual(fill_minutes.days_on_disk(self.root), want)
        out, gw, _ = self.run_job(now)
        self.assertEqual((out["days"], gw.calls), ([], []), "a day that has a file is never fetched again")
        fill_minutes.path_of(self.root, "2026-10-20").unlink()
        out, gw, _ = self.run_job(now)
        self.assertEqual(out["days"], ["2026-10-20"])
        self.assertEqual(len(gw.calls), 2)

    def test_a_half_day_is_fetched_after_its_own_close(self):
        out, gw, _ = self.run_job(at(EST_HALF, 13, 30))
        self.assertNotIn("2026-11-27", out["days"])
        out, gw, _ = self.run_job(at(EST_HALF, 13, 45))
        self.assertIn("2026-11-27", out["days"])
        self.assertEqual(fill_minutes.livelike(self.root, EST_HALF, "SPY", "close"), (100.125, "vw"))
        self.assertEqual([r[0][11:16] for r in fill_minutes.read_day(self.root, EST_HALF)["bars"]["SPY"]][-10:],
                         ["17:50", "17:51", "17:52", "17:53", "17:54", "17:55", "17:56", "17:57", "17:58", "17:59"])

    def test_the_two_switches_skip_the_job(self):
        self.settings({"mode": "off"})
        out, gw, _ = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual((out["status"], gw.calls), ("skipped", []))
        self.settings({"mode": "record", "fill_minutes": False})
        out, gw, _ = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual((out["status"], gw.calls), ("skipped", []))
        self.assertIn("fill_minutes", out["why"])
        (self.root / "swarm.json").unlink()
        with mock.patch("league.swarm.settings.read_policy", return_value=({}, {})):
            out, gw, _ = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual((out["status"], gw.calls), ("skipped", []), "the code default of the forward mode is off")

    def test_settings_that_cannot_be_read_are_off_never_a_crash(self):
        with mock.patch.object(forward_db, "cfg", side_effect=NotImplementedError("A: not landed")):
            out, gw, _ = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual((out["status"], gw.calls), ("skipped", []))

    def test_a_gateway_error_fails_the_receipt_and_keeps_the_days_already_written(self):
        now = at(dt.date(2026, 10, 14), 16, 45)
        out, gw, _ = self.run_job(now, Gateway(fail="2026-10-13"))
        self.assertEqual((out["status"], out["ok"], out["days"], out["day"]),
                         ("failed", False, ["2026-10-12"], "2026-10-13"))
        self.assertIn("GatewayError", out["error"])
        self.assertEqual(fill_minutes.days_on_disk(self.root), ["2026-10-12"])
        out, gw, _ = self.run_job(now)                                    # the retry inside its grace
        self.assertEqual(out["days"], ["2026-10-13", "2026-10-14"])
        self.assertNotIn("status", out)

    def test_a_day_the_venue_has_not_settled_is_not_written(self):
        now = at(dt.date(2026, 10, 13), 16, 45)
        out, gw, _ = self.run_job(now, Gateway(unready="2026-10-13"))
        self.assertEqual((out["status"], out["days"]), ("failed", ["2026-10-12"]))
        self.assertIn("not ready", out["error"])
        self.assertFalse(fill_minutes.path_of(self.root, "2026-10-13").exists())
        # The same when only the marker's send minute is missing (the venue is part way through the day).
        out, gw, _ = self.run_job(now, Gateway(absent={equity_data.CALENDAR_SYMBOL}))
        self.assertEqual((out["status"], out["days"]), ("failed", []))
        out, gw, _ = self.run_job(now)
        self.assertEqual(out["days"], ["2026-10-13"])

    def test_a_day_that_is_not_ready_never_holds_up_the_days_after_it(self):
        # The oldest day goes first: were the run to stop at a day the venue never settles, every newer day of the
        # backfill would wait behind it for ten sessions.
        now = at(dt.date(2026, 10, 15), 16, 45)
        out, gw, ctx = self.run_job(now, Gateway(unready="2026-10-13"))
        self.assertEqual((out["status"], out["ok"], out["day"], out["unready"]), ("failed", False, "2026-10-13", 1))
        self.assertEqual(out["days"], ["2026-10-12", "2026-10-14", "2026-10-15"])
        self.assertEqual(fill_minutes.days_on_disk(self.root), ["2026-10-12", "2026-10-14", "2026-10-15"])
        self.assertIn("2026-10-13", out["error"])
        self.assertIn("not ready", out["error"])
        self.assertEqual(len(gw.calls), 8, "two requests a session, the unready one included")
        self.assertEqual(ctx.alerts, [])
        out, gw, _ = self.run_job(now, Gateway(unready="2026-10-13"))      # the retry inside its grace: that day alone
        self.assertEqual((out["status"], out["days"], len(gw.calls)), ("failed", [], 2))
        out, gw, _ = self.run_job(now)                                     # the venue has settled it
        self.assertEqual(out["days"], ["2026-10-13"])
        self.assertNotIn("status", out)

    def test_several_days_that_are_not_ready_are_counted_and_the_text_holds_dates_only(self):
        now = at(dt.date(2026, 10, 19), 16, 45)                            # six forward days have closed
        out, gw, _ = self.run_job(now, Gateway(absent={equity_data.CALENDAR_SYMBOL}))
        self.assertEqual((out["status"], out["days"], out["day"], out["unready"]), ("failed", [], "2026-10-12", 6))
        self.assertIn("2026-10-12, 2026-10-13, 2026-10-14 ...", out["error"])
        self.assertNotIn("2026-10-15", out["error"], "the text names the first three")
        self.assertNotRegex(out["error"].replace("2026-10-", ""), r"\d+\.\d|%|bp", "ids, counts and dates only")
        # A gateway error is the venue's own: the run stops at it, as before.
        out, gw, _ = self.run_job(now, Gateway(unready="2026-10-12", fail="2026-10-14"))
        self.assertEqual((out["status"], out["days"], out["day"]), ("failed", ["2026-10-13"], "2026-10-14"))
        self.assertIn("GatewayError", out["error"])
        self.assertNotIn("unready", out)

    def test_a_symbol_with_no_bar_is_its_own_gap_not_the_days(self):
        out, gw, _ = self.run_job(at(EDT_DAY, 16, 45), Gateway(absent={"XLC"}))
        self.assertEqual(out["days"], ["2026-10-12"])
        self.assertEqual(fill_minutes.read_day(self.root, EDT_DAY)["bars"]["XLC"], [])
        self.assertIsNone(fill_minutes.livelike(self.root, EDT_DAY, "XLC", "open"))
        self.assertIsNotNone(fill_minutes.livelike(self.root, EDT_DAY, "XLE", "open"))

    def test_the_receipt_holds_counts_never_a_price(self):
        out, _, _ = self.run_job(at(EDT_DAY, 16, 45))
        self.assertEqual(sorted(out), ["bars", "days", "ok", "symbols"])
        self.assertTrue(all(isinstance(out[k], int) for k in ("bars", "symbols")))
        self.assertNotIn("100.", json.dumps(out))

    def test_due_days_is_the_calendars(self):
        days = fill_minutes.due_days(at(dt.date(2026, 11, 30), 9, 0), first=fake_t0())
        self.assertEqual(len(days), fill_minutes.BACKFILL_SESSIONS)
        self.assertEqual(days, sorted(days))
        self.assertEqual(days[-1], EST_HALF, "Friday's half day; Monday has not closed at 09:00")
        self.assertNotIn(dt.date(2026, 11, 26), days, "Thanksgiving is not a session")
        self.assertTrue(all(schedule.is_session(d) for d in days))
        self.assertEqual(fill_minutes.due_days(at(EDT_DAY, 16, 40), first=fake_t0()), [EDT_DAY])
        self.assertEqual(fill_minutes.due_days(at(EDT_DAY, 16, 40) - 1, first=fake_t0()), [])
        self.assertEqual(fill_minutes.SETTLE_SECONDS, 40 * 60)
        self.assertTrue(math.isclose(at(EDT_DAY, 16, 40) - schedule.moments(EDT_DAY).close_at, 2400.0))


if __name__ == "__main__":
    unittest.main()
