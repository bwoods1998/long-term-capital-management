"""The store-v1 Parquet writers and the image pruning (scripts/data/frames.py, backfill.py).

Needs polars and pyarrow (the data box has them); skipped cleanly where they are absent (CI)."""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

try:
    import polars as pl
    import pyarrow  # noqa: F401
except ImportError:  # pragma: no cover - CI has neither
    pl = None

import storelib as sl  # noqa: E402

DAY = dt.date(2024, 3, 13)


def ts(hh, mm, ss=0):
    from zoneinfo import ZoneInfo

    return dt.datetime(2024, 3, 13, hh, mm, ss, tzinfo=ZoneInfo("America/New_York"))


def raw_quotes():
    rows = [
        # expiration, strike, right, time, bid, ask, bid_size, ask_size
        ("2024-03-13", 515.0, "CALL", ts(9, 30), float("nan"), float("nan"), 0, 0),  # no quote yet
        ("2024-03-13", 515.0, "CALL", ts(9, 31), 1.10, 1.12, 10, 20),
        ("2024-03-13", 515.0, "CALL", ts(9, 32), 0.0, 0.05, 0, 30),  # zero bid: kept
        ("2024-03-13", 515.0, "CALL", ts(9, 33), 1.20, 1.10, 5, 5),  # crossed: dropped
        ("2024-03-13", 515.0, "PUT", ts(9, 31), -0.01, 0.40, 1, 1),  # negative: dropped
        ("2024-03-13", 515.0, "PUT", ts(9, 32), 0.30, 0.0, 1, 0),  # no offer: dropped
        ("2024-03-13", 515.0, "PUT", ts(9, 33), 0.30, 0.30, 7, 8),  # locked: kept
        ("2024-03-20", 510.0, "PUT", ts(16, 0), 2.0, 2.02, 3, 4),
        ("2024-03-28", 510.0, "PUT", ts(10, 0), 2.0, 2.02, 3, 4),  # 15 DTE: outside 0-14
        ("2024-03-14", 512.0, "CALL", ts(16, 5), 2.0, 2.02, 3, 4),  # after the close
    ]
    return pl.DataFrame({
        "symbol": ["SPY"] * len(rows), "expiration": [r[0] for r in rows], "strike": [r[1] for r in rows],
        "right": [r[2] for r in rows], "timestamp": [r[3] for r in rows], "bid": [r[4] for r in rows],
        "ask": [r[5] for r in rows], "bid_size": [r[6] for r in rows], "ask_size": [r[7] for r in rows],
        "bid_exchange": [1] * len(rows), "ask_exchange": [1] * len(rows),
    })


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class Normalize(unittest.TestCase):
    def test_nbbo_keeps_the_schema_and_drops_only_bad_quotes(self):
        import frames as fr

        frame, stats = fr.nbbo(raw_quotes(), DAY, open_min=570, close_min=960, max_dte=14)
        self.assertEqual(dict(frame.schema), fr.NBBO_SCHEMA)
        self.assertEqual(stats["no_quote"], 1)
        self.assertEqual(stats["crossed"], 1)
        self.assertEqual(stats["negative"], 1)
        self.assertEqual(stats["no_offer"], 1)
        self.assertEqual(frame.height, 4)
        self.assertEqual(frame["minute"].to_list(), [571, 572, 573, 960])
        self.assertEqual(frame["right"].to_list(), ["C", "C", "P", "P"])
        self.assertEqual(frame.filter(pl.col("minute") == 572)["bid"][0], 0.0)
        self.assertEqual(frame.sort(["expiration", "strike", "right", "minute"]).to_dicts(), frame.to_dicts())
        self.assertNotIn("date", frame.columns)

    def test_underlying_is_one_price_a_minute(self):
        import frames as fr

        raw = pl.DataFrame({"timestamp": [ts(9, 31), ts(9, 31), ts(9, 32), ts(16, 1)],
                            "underlying_price": [500.0, 500.2, float("nan"), 501.0]})
        frame = fr.underlying(raw, open_min=570, close_min=960)
        self.assertEqual(dict(frame.schema), fr.UNDERLYING_SCHEMA)
        self.assertEqual(frame.to_dicts(), [{"minute": 571, "price": 500.1}])

    def test_open_interest_and_expirations_filter_to_the_window(self):
        import frames as fr

        raw = pl.DataFrame({"expiration": ["2024-03-12", "2024-03-15", "2024-04-30"], "strike": [1.0, 2.0, 3.0],
                            "right": ["CALL", "PUT", "CALL"], "open_interest": [5, 6, 7]})
        frame = fr.open_interest(raw, DAY, max_dte=14)
        self.assertEqual(frame.to_dicts(), [{"expiration": dt.date(2024, 3, 15), "strike": 2.0, "right": "P", "open_interest": 6}])
        self.assertEqual(fr.expirations(raw, DAY, max_dte=45), [dt.date(2024, 3, 15)])

    def test_trade_quote_keeps_its_schema(self):
        import frames as fr

        raw = pl.DataFrame({"expiration": ["2024-03-13"], "strike": [515.0], "right": ["C"],
                            "trade_timestamp": [ts(10, 0, 1)], "price": [1.1], "size": [2], "condition": [18],
                            "exchange": [4], "bid": [1.05], "ask": [1.15], "bid_size": [3], "ask_size": [4]})
        frame = fr.trade_quote(raw, DAY, max_dte=7)
        self.assertEqual(dict(frame.schema), fr.TQ_SCHEMA)
        self.assertEqual(frame["ms_of_day"][0], 36_001_000)

    def test_write_is_atomic_and_checksummed_and_merge_dedupes(self):
        import frames as fr

        frame, _ = fr.nbbo(raw_quotes(), DAY, open_min=570, close_min=960, max_dte=14)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nbbo" / "SPY" / "2024-03-13.parquet"
            rows, digest, size = fr.write(frame, target)
            self.assertEqual((rows, size), (frame.height, target.stat().st_size))
            self.assertEqual(digest, sl.sha256_file(target)[0])
            self.assertEqual(list(target.parent.glob(".*")), [])
            back = pl.read_parquet(target)
            self.assertEqual(back.to_dicts(), frame.to_dicts())
            merged = fr.merge_nbbo(back, frame.head(2))
            self.assertEqual(merged.height, frame.height)

    def test_manifest_expiries_calendar_schemas(self):
        import frames as fr

        record = sl.file_record("nbbo", "SPY", DAY, rows=3, sha256="ab", size=9, source="s",
                                fetched_at="2026-09-26T06:50:00.123456Z")
        manifest = fr.manifest_frame([record])
        self.assertEqual(dict(manifest.schema), {"kind": pl.Utf8, "root": pl.Utf8, "date": pl.Date, "rows": pl.Int64,
                                                 "sha256": pl.Utf8, "bytes": pl.Int64, "window": pl.Utf8,
                                                 "fetched_at": pl.Datetime("us", "UTC"), "source": pl.Utf8})
        self.assertEqual(dict(fr.expiries_frame([("SPY", DAY, DAY)]).schema),
                         {"root": pl.Utf8, "date": pl.Date, "expiration": pl.Date})
        self.assertEqual(dict(fr.calendar_frame([(DAY, 570, 960)]).schema),
                         {"date": pl.Date, "open_min": pl.Int16, "close_min": pl.Int16})


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class ImagesPrune(unittest.TestCase):
    def build(self, tmp):
        import backfill as bf
        import frames as fr

        store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
        cal = sl.Calendar({})
        store.work.mkdir(parents=True, exist_ok=True)
        (store.work / "calendar.json").write_text(json.dumps({"years": ["2024"], "exceptions": {}}))
        frame, _ = fr.nbbo(raw_quotes(), DAY, open_min=570, close_min=960, max_dte=14)
        for day in (dt.date(2024, 3, 13), dt.date(2025, 6, 11), dt.date(2026, 3, 11), dt.date(2026, 9, 28)):
            rows, digest, size = fr.write(frame, store.path("nbbo", "SPY", day))
            store.journal.append(sl.file_record("nbbo", "SPY", day, rows=rows, sha256=digest, size=size,
                                                source="t", fetched_at="2026-09-26T00:00:00Z"))
            store.save_expiries("SPY", day, [day])
        orphan = store.path("nbbo", "QQQ", dt.date(2024, 3, 13))
        fr.write(frame, orphan)  # renamed but never journaled
        return bf, store, cal, orphan

    def test_gym_prune_keeps_train_and_validation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal, orphan = self.build(tmp)
            (Path(tmp) / "secrets").mkdir()
            result = bf.prune(store, ["train", "validation"], drop_key=False, drop_work=True, calendar=cal)
            self.assertEqual((result["removed"], result["orphans"]), (2, 1))
            self.assertFalse(orphan.exists())
            left = sorted(p.stem for p in store.root.glob("nbbo/*/*.parquet"))
            self.assertEqual(left, ["2024-03-13", "2025-06-11"])
            manifest = pl.read_parquet(store.root / "manifest.parquet")
            self.assertEqual(sorted(set(manifest["window"].to_list())), ["train", "validation"])
            self.assertLessEqual(pl.read_parquet(store.root / "expiries.parquet")["date"].max(), dt.date(2025, 12, 31))
            self.assertLessEqual(pl.read_parquet(store.root / "calendar.parquet")["date"].max(), dt.date(2025, 12, 31))
            self.assertFalse(store.work.exists())

    def test_a_roots_filter_keeps_only_complete_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal, orphan = self.build(tmp)
            import frames as fr

            frame, _ = fr.nbbo(raw_quotes(), DAY, open_min=570, close_min=960, max_dte=14)
            rows, digest, size = fr.write(frame, store.path("nbbo", "META", DAY))
            store.journal.append(sl.file_record("nbbo", "META", DAY, rows=rows, sha256=digest, size=size,
                                                source="t", fetched_at="2026-09-26T00:00:00Z"))
            store.save_expiries("META", DAY, [DAY])
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, roots=["SPY"])
            self.assertEqual(sorted({p.parent.name for p in store.root.glob("nbbo/*/*.parquet")}), ["SPY"])
            self.assertEqual(set(pl.read_parquet(store.root / "manifest.parquet")["root"].to_list()), {"SPY"})
            self.assertEqual(set(pl.read_parquet(store.root / "expiries.parquet")["root"].to_list()), {"SPY"})

    def test_gate_prune_keeps_everything_and_a_consistent_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal, orphan = self.build(tmp)
            (store.work / "universe.json").write_text("{}")
            result = bf.prune(store, ["train", "validation", "holdout", "forward"], drop_key=False, drop_work=False,
                              calendar=cal, keep_journal=True)
            self.assertEqual((result["removed"], result["orphans"]), (0, 1))
            self.assertEqual(sorted(p.name for p in store.work.iterdir()), ["calendar.json", "expiries", "journal.jsonl"])
            self.assertEqual(len(store.journal.files()), 4)

    def test_adopt_checks_every_file_and_recompiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal, _ = self.build(tmp)
            records = bf.day_records(store, dt.date(2026, 9, 28))
            self.assertEqual([r.get("type") for r in records], ["file", "expiries", "calendar"])
            path = Path(tmp) / "records.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in records))
            result = bf.adopt(store, str(path), cal)
            self.assertEqual(result["adopted"], 1)
            store.path("nbbo", "SPY", dt.date(2026, 9, 28)).write_bytes(b"tampered")
            with self.assertRaises(SystemExit):
                bf.adopt(store, str(path), cal)

    def test_a_sample_never_carries_the_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal, _ = self.build(tmp)
            out = Path(tmp) / "sample"
            got = bf.export_subset(store, out, ["SPY"], [dt.date(2024, 3, 13)], cal)
            self.assertEqual(got["files"], 1)
            self.assertEqual((out / "VERSION").read_text().strip(), sl.STORE_VERSION)
            with self.assertRaises(SystemExit):
                bf.export_subset(store, Path(tmp) / "bad", ["SPY"], [dt.date(2026, 3, 11)], cal)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class GroupedListings(unittest.TestCase):
    def test_one_request_per_day_for_the_group_and_a_fallback_for_a_missing_root(self):
        import threading

        import backfill as bf

        calls = []

        class Theta:
            def call(self, method, kind, day, symbol, max_dte):
                calls.append(symbol)
                roots = symbol if isinstance(symbol, list) else [symbol]
                rows = [(r, "2024-03-15") for r in roots if r != "QQQ" or not isinstance(symbol, list)]
                return pl.DataFrame({"symbol": [r[0] for r in rows], "expiration": [r[1] for r in rows],
                                     "strike": [1.0] * len(rows), "right": ["C"] * len(rows)})

        listings = bf.Listings(lambda t: ["SPY", "QQQ", "IWM"])
        tasks = [sl.Task(1, "day", root, DAY) for root in ("SPY", "QQQ", "IWM", "SPY")]
        results = {}
        threads = [threading.Thread(target=lambda t=t: results.__setitem__(t.root, listings.expiries(t, Theta(), 45)))
                   for t in tasks]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results["SPY"], [dt.date(2024, 3, 15)])
        self.assertEqual(results["QQQ"], [dt.date(2024, 3, 15)])  # not in the group answer: fetched alone
        self.assertEqual(sum(1 for c in calls if isinstance(c, list)), 1)
        self.assertEqual([c for c in calls if not isinstance(c, list)], ["QQQ"])


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class Invalidate(unittest.TestCase):
    def test_invalidate_removes_files_and_requeues(self):
        import backfill as bf
        import frames as fr

        with tempfile.TemporaryDirectory() as tmp:
            store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
            frame, _ = fr.nbbo(raw_quotes(), DAY, open_min=570, close_min=960, max_dte=14)
            days = [dt.date(2022, 1, 7), dt.date(2022, 6, 10)]
            for day in days:
                rows, digest, size = fr.write(frame, store.path("nbbo", "META", day))
                store.journal.append(sl.file_record("nbbo", "META", day, rows=rows, sha256=digest, size=size,
                                                    source="t", fetched_at="2026-09-26T00:00:00Z"))
                store.journal.append({"type": "task", "stage": 4, "task": f"day:META:{day.isoformat()}", "status": "ok"})
                store.save_expiries("META", day, [day])
            got = bf.invalidate(store, "META", dt.date(2022, 6, 9), "wrong underlying")
            self.assertEqual(got, {"files_removed": 1, "tasks_invalidated": 1})
            self.assertFalse(store.path("nbbo", "META", days[0]).exists())
            self.assertTrue(store.path("nbbo", "META", days[1]).exists())
            self.assertEqual(list(store.journal.files()), ["nbbo/META/2022-06-10.parquet"])
            self.assertNotIn("4:day:META:2022-01-07", store.journal.done())
            self.assertIsNone(store.load_expiries("META", days[0]))
