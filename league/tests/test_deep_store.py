"""THE DEEP STORE'S DATA JOB (HISTORY-PLAN.md section 5.3, "equity_deep: the audit fails closed; the receipt carries no
decimals"; league/ops/equity_deep.py): what is asked of the gateway, the staging (DVAL inside a marked owner-only
folder), the audit's every check failing closed (a failed audit writes nothing, and the next runs wait for refetch),
a gap of a DVAL fund failing it, a run that stops at an answer that will not change tonight, the sealed tree as
written, and a receipt of counts and verdicts only.

The gateway here is a stand-in serving synthetic bars on the deep calendar (league/tests/deep_fakes.py `gbm`) and, for
2016-19, the synthetic SIP store's own raw bars: no market row, no token."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import stat
import unittest
from pathlib import Path

import numpy as np

from league.deep import blocks, calendar, config
from league.equity import store as estore
from league.equity import synth
from league.ops import equity_deep
from league.ops.context import Context
from league.tests import deep_fakes as F

NOW = dt.datetime(2026, 10, 25, 23, 0, tzinfo=dt.timezone.utc).timestamp()


def floats(value, path=""):
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return []
    if isinstance(value, float):
        return [path]
    if isinstance(value, dict):
        return [hit for k, v in value.items() for hit in floats(v, f"{path}.{k}")]
    if isinstance(value, (list, tuple)):
        return [hit for i, v in enumerate(value) for hit in floats(v, f"{path}[{i}]")]
    return [path]


class Gateway:
    """The Tiingo route's stand-in: {"symbol", "rows"} for /v1/tiingo/daily/<SYM>/prices, from synthetic series."""

    def __init__(self, sip_root: Path, *, break_with=None, refuse=None):
        self.calls: list[tuple[str, dict]] = []
        self.refuse = refuse
        self.break_with = break_with or (lambda sym, rows: rows)
        days = calendar.deep_sessions()
        self.series = {}
        for sym in config.FETCH_UNIVERSE:
            first = max(config.INCEPTION.get(sym, days[0]), days[0])
            mine = [d for d in days if d >= first]
            self.series[sym] = F.gbm(sym, mine, seed=21, dividends=[(mine[i], 0.2) for i in range(30, len(mine), 63)])
        sip = estore.EquityStore(sip_root)
        self.sip = sip.bars(list(config.FETCH_UNIVERSE), "train", history=0)

    def rows(self, sym: str, start: str, end: str) -> list[dict]:
        out = []
        if start >= "2016-01-04":
            raw = self.sip.raw[sym]
            for d, r in zip(self.sip.days, raw):
                day = estore.from_ordinal(int(d)).isoformat()
                if start <= day <= end and np.isfinite(r[3]):
                    out.append({"date": day, "open": float(r[0]), "high": float(r[1]), "low": float(r[2]),
                                "close": float(r[3]), "volume": float(r[4]), "divCash": 0.0, "splitFactor": 1.0,
                                "factorStep": False})
            return out
        s = self.series[sym]
        for i, d in enumerate(s["days"]):
            day = d.isoformat()
            if start <= day <= end:
                out.append({"date": day, **{blocks.VENDOR[c]: float(s[c][i]) for c in blocks.COLUMNS},
                            "factorStep": bool(s["div"][i] > 0 or s["split"][i] != 1.0)})
        return out

    def get(self, path: str, params=None):
        self.calls.append((path, dict(params or {})))
        if self.refuse is not None:
            raise self.refuse(path)
        sym = re.fullmatch(r"/v1/tiingo/daily/([A-Z]+)/prices", path).group(1)
        rows = self.rows(sym, params["startDate"], params["endDate"])
        return {"symbol": sym, "rows": self.break_with(sym, rows)}


class Job(unittest.TestCase):
    def setUp(self):
        self.root = F.tmpdir(self)
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "report"}}}))
        synth.synthetic_store(self.root / "equity-daily", symbols=config.FETCH_UNIVERSE, start=dt.date(2016, 1, 4),
                              end=dt.date(2019, 12, 31), seed=3)
        self.deep = self.root / config.STORE_DIR

    def ctx(self, gateway, **job):
        return Context("equity_deep", root=self.root, due_at=NOW, clock=lambda: NOW, config={}, gateway=gateway,
                       settings_value={"equity_deep": {"pause_s": 0, "max_requests": 200, **job}})

    def assertNothingWritten(self):
        for name in (config.OPEN_DIR, config.SEALED_DIR, config.MANIFEST, config.STAGING_DIR):
            self.assertFalse((self.deep / name).exists(), name)

    def test_with_the_mode_off_nothing_runs(self):
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "off"}}}))
        gw = Gateway(self.root / "equity-daily")
        self.assertEqual(equity_deep.run(self.ctx(gw))["status"], "skipped")
        self.assertEqual(gw.calls, [])
        self.assertFalse(self.deep.exists())

    def test_what_is_asked_of_the_gateway(self):
        asked = equity_deep.plan()
        self.assertEqual({sym for sym, *_ in asked}, set(config.FETCH_UNIVERSE))
        for sym, span, first, last in asked:
            self.assertLess(last, dt.date(2020, 1, 1), "never a day of 2020 on")
            self.assertGreaterEqual(last, config.INCEPTION.get(sym, first))
        self.assertNotIn(("XLRE", "dval"), {(s, span) for s, span, *_ in asked})
        self.assertNotIn(("GLD", "history"), {(s, span) for s, span, *_ in asked})
        self.assertIn(("GLD", "dval"), {(s, span) for s, span, *_ in asked})

    def test_a_clean_fetch_writes_the_store_seals_dval_and_reports_counts_only(self):
        gw = Gateway(self.root / "equity-daily")
        out = equity_deep.run(self.ctx(gw))
        self.assertTrue(out.get("written"), out.get("error"))
        self.assertEqual(floats(out), [], "the receipt carries no decimal")
        self.assertTrue(out["audit"]["ok"])
        self.assertEqual(len(gw.calls), len(equity_deep.plan()))
        for path, params in gw.calls:
            self.assertRegex(path, r"^/v1/tiingo/daily/[A-Z]+/prices$")
            self.assertLess(params["endDate"], "2020-01-01")
        self.assertFalse((self.deep / config.STAGING_DIR).exists(), "the staging is removed")
        self.assertEqual(stat.S_IMODE(os.stat(self.deep / config.SEALED_DIR).st_mode), 0o700)
        self.assertTrue((self.deep / config.SEALED_DIR / config.GATE_MARK).is_file())
        self.assertEqual(sorted(os.listdir(self.deep / config.SEALED_DIR)), [config.GATE_MARK, "dval"])
        self.assertEqual(sorted(os.listdir(self.deep / config.OPEN_DIR)), ["history", "traind"])
        manifest = json.loads((self.deep / config.MANIFEST).read_text())
        self.assertNotIn("overlap", manifest["spans"], "the SIP overlap is counted, never kept")
        self.assertEqual(floats(manifest), [], "the manifest is counts, days and verdicts")
        self.assertEqual(manifest["spans"]["dval"]["SPY"]["rows"], 1944)
        store = blocks.DeepStore(self.deep)
        with self.assertRaises(blocks.DeepRefused):
            store.block("dval", "SPY")
        self.assertTrue(equity_deep.complete(self.deep))
        self.assertEqual(equity_deep.run(self.ctx(gw))["status"], "skipped", "a complete store is not fetched again")

    def test_a_run_stops_at_its_request_bound_and_the_next_goes_on(self):
        gw = Gateway(self.root / "equity-daily")
        first = equity_deep.run(self.ctx(gw, max_requests=10))
        self.assertEqual((first["fetched"], first["left"]), (10, len(equity_deep.plan()) - 10))
        self.assertEqual(stat.S_IMODE(os.stat(self.deep / config.STAGING_DIR).st_mode), 0o700)
        self.assertFalse((self.deep / config.MANIFEST).exists())
        second = equity_deep.run(self.ctx(gw))
        self.assertTrue(second.get("written"))
        self.assertEqual(len(gw.calls), len(equity_deep.plan()), "no request is asked twice")

    def failing(self, break_with) -> dict:
        gw = Gateway(self.root / "equity-daily", break_with=break_with)
        out = equity_deep.run(self.ctx(gw))
        self.assertEqual(out.get("status"), "failed", out)
        self.assertNothingWritten()
        self.assertEqual(floats(out), [])
        marker = self.deep / config.AUDIT_FAILED
        self.assertTrue(marker.is_file(), "a failed audit leaves its marker")
        self.assertEqual(floats(json.loads(marker.read_text())), [], "counts and verdicts only")
        asked = len(gw.calls)
        again = equity_deep.run(self.ctx(gw))
        self.assertEqual(again["status"], "skipped", "a deterministic failure is not fetched again every night")
        self.assertIn("refetch", again["why"])
        self.assertEqual(len(gw.calls), asked, "no request")
        marker.unlink()
        return out

    def test_the_audit_fails_closed(self):
        def spy_missing(sym, rows):
            return [r for r in rows if not (sym == "SPY" and r["date"] == "2003-05-05")]

        def off_calendar(sym, rows):
            if sym == "QQQ" and rows and rows[0]["date"] <= "2001-09-10" <= rows[-1]["date"]:
                at = next(i for i, r in enumerate(rows) if r["date"] > "2001-09-10")
                rows = rows[:at] + [{**rows[at - 1], "date": "2001-09-12"}] + rows[at:]
            return rows

        def insane(sym, rows):
            return [{**r, "high": r["close"] * 0.5} if sym == "XLF" and r["date"] == "2006-03-01" else r for r in rows]

        def unexplained(sym, rows):
            return [{**r, "factorStep": True} if sym == "DIA" and r["date"] == "2007-03-01" else r for r in rows]

        def sip_off(sym, rows):
            return [{**r, "close": r["close"] * 1.01} if sym == "IWM" and r["date"] >= "2016-01-04" else r for r in rows]

        def qqq_gap(sym, rows):   # one missing session of a DVAL fund in dval: S3's look would fail on the data
            return [r for r in rows if not (sym == "QQQ" and r["date"] == "2006-06-06")]

        def xlk_stops(sym, rows):   # a DVAL fund whose traind bars stop a session early: a gap too
            return rows[:-1] if sym == "XLK" and rows and rows[-1]["date"] == "2015-12-31" else rows

        cases = {"SPY's dval sessions are not the calendar's": spy_missing, "bars off the calendar": off_calendar,
                 "fail the OHLC sanity check": insane, "factor steps with no listed event": unexplained,
                 "do not agree with the House's SIP store": sip_off, "QQQ dval: 1 sessions missing": qqq_gap,
                 "XLK traind: 1 sessions missing": xlk_stops}
        for why, broken in cases.items():
            with self.subTest(why):
                out = self.failing(broken)
                self.assertIn(why, out["error"])

    def test_a_look_back_gap_is_kept_and_unscores_segment_a_only(self):
        def history_gap(sym, rows):
            return [r for r in rows if not (sym == "XLF" and r["date"] == "2000-03-01")]

        out = equity_deep.run(self.ctx(Gateway(self.root / "equity-daily", break_with=history_gap)))
        self.assertTrue(out.get("written"), out.get("error"))
        self.assertEqual(out["audit"]["gaps"], {"history": {"XLF": 1}})
        self.assertEqual((equity_deep.gap_max("XLF", "history"), equity_deep.gap_max("XLF", "dval"),
                          equity_deep.gap_max("XLRE", "traind")), (equity_deep.GAP_MAX, 0, equity_deep.GAP_MAX))
        from league.deep import gate, screen3

        gaps = gate._gaps(blocks.DeepStore(self.deep))
        self.assertEqual(gaps, {"XLF": {"history": 1}})
        first = {s: dt.date(1999, 1, 4) for s in config.DEEP_UNIVERSE}
        laid = screen3.layout(["SPY", "XLF"], 20, first, {}, gaps)
        self.assertEqual((laid["segments"]["A"], bool(laid["segments"]["B"])), (None, True))

    def test_dval_is_staged_inside_a_marked_owner_only_folder(self):
        gw = Gateway(self.root / "equity-daily")
        equity_deep.run(self.ctx(gw, max_requests=4))   # SPY: history, dval, traind, overlap
        sealed = self.deep / config.STAGING_DIR / config.SEALED_DIR
        self.assertTrue((sealed / "dval" / "SPY.npz").is_file())
        self.assertFalse((self.deep / config.STAGING_DIR / "dval").exists(), "never beside the open spans")
        self.assertTrue((sealed / config.GATE_MARK).is_file())
        for path in (sealed, sealed / "dval"):
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)
        self.assertTrue(equity_deep.run(self.ctx(gw)).get("written"))
        self.assertFalse((self.deep / config.STAGING_DIR).exists())

    def test_a_run_stops_at_an_answer_that_will_not_change_tonight(self):
        from league.ops.context import GatewayError

        for status in (503, 403, 401):
            gw = Gateway(self.root / "equity-daily", refuse=lambda path, status=status: GatewayError(
                f"GET {path}: HTTP {status} {{\"cap\": \"setup\"}}", status=status))
            out = equity_deep.run(self.ctx(gw))
            self.assertEqual((out["status"], len(gw.calls)), ("failed", 1), status)
            self.assertIn(f"HTTP {status}", out["error"])
        gw = Gateway(self.root / "equity-daily", refuse=lambda path: GatewayError(f"GET {path}: HTTP 502", status=502))
        out = equity_deep.run(self.ctx(gw))
        self.assertEqual(len(gw.calls), equity_deep.CONSECUTIVE_MAX, "a passing upstream fault: three in a row")
        self.assertIn("in a row", out["error"])

    def test_no_sip_store_fails_closed(self):
        gw = Gateway(self.root / "equity-daily")
        import shutil

        shutil.rmtree(self.root / "equity-daily")
        out = equity_deep.run(self.ctx(gw))
        self.assertEqual(out["status"], "failed")
        self.assertNothingWritten()

    def test_a_late_spdr_with_stale_closes_is_not_clean_and_the_open_audit_is_reported(self):
        def stale(sym, rows):
            if sym != "XLP":
                return rows
            out, prev = [], None
            for r in rows:
                if prev is not None and r["date"].startswith("2006-0") and int(r["date"][8:]) % 3 == 0:
                    r = {**r, "close": prev["close"], "low": min(r["low"], prev["close"]),
                         "high": max(r["high"], prev["close"])}
                out.append(r)
                prev = r
            return out

        out = equity_deep.run(self.ctx(Gateway(self.root / "equity-daily", break_with=stale)))
        self.assertTrue(out.get("written"), out.get("error"))
        self.assertFalse(out["audit"]["stale"]["XLP"]["clean"])
        self.assertTrue(out["audit"]["stale"]["XLB"]["clean"])
        self.assertEqual(out["audit"]["open_audit"], "agree")
        self.assertFalse(blocks.DeepStore(self.deep).audit()["stale"]["XLP"]["clean"])


if __name__ == "__main__":
    unittest.main()
