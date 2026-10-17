"""THE DEEP CALENDAR, THE FIXTURES AND THE PUBLIC-REPO GUARD (HISTORY-PLAN.md sections 5.3 and 7; PREREG-H "Calendar",
"Mask"; league/deep/calendar.py): the repo's pre-2022 rules plus the four closures are the pinned fixture, session for
session; the plan's era and segment counts hold; the mask is PREREG-H's nine windows, 235 sessions, one-sided inside
DVAL; the pseudo-dates are the Train window's first sessions; and the public repository holds no market data (no csv,
npz, parquet or npy but the one synthetic fixture it has always held) and the two fixtures are dates only."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unittest
from pathlib import Path

from league.deep import calendar, config
from league.equity import store as estore
from league.ops import french

REPO = Path(__file__).resolve().parents[2]
#: The repository's one tracked array file before R1 (synthetic conformance inputs of release E4).
KNOWN_ARRAYS = {"league/tests/fixtures/xs1_conformance_inputs.npz"}
DATA_SUFFIXES = (".csv", ".npz", ".npy", ".parquet", ".pq", ".feather", ".h5", ".hdf5", ".zip")
SKIP = {".git", "node_modules", "__pycache__", ".venv"}


class TheCalendar(unittest.TestCase):
    def test_the_rules_are_the_pinned_fixture(self):
        self.assertEqual(tuple(calendar.deep_sessions()), calendar.fixture())
        self.assertEqual(len(calendar.fixture()), 4277)
        self.assertTrue(config.CLOSURES.isdisjoint(calendar.fixture()))
        by_year = {}
        for day in calendar.fixture():
            by_year[day.year] = by_year.get(day.year, 0) + 1
        self.assertEqual((by_year[2001], by_year[2012], by_year[2008], by_year[2006]), (248, 250, 253, 251))

    def test_the_eras_and_segments(self):
        self.assertEqual({k: len(calendar.era(k)) for k in config.ERAS}, config.ERA_SESSIONS)
        self.assertEqual({k: tuple(map(len, calendar.segment(k))) for k in config.SEGMENTS}, config.SEGMENT_SESSIONS)
        for name, (back, scored) in config.SEGMENT_SESSIONS.items():
            self.assertLessEqual(back + scored, len(estore.nyse_sessions(dt.date(2016, 1, 4), dt.date(2024, 12, 31))))
        self.assertEqual(len(estore.nyse_sessions(*config.RESERVE)), config.RECENT_LENGTHS["R"])

    def test_the_mask(self):
        mask = calendar.mask()
        self.assertEqual(tuple(mask), calendar.mask_fixture())
        self.assertEqual(len(mask), config.MASK_SESSIONS)
        self.assertEqual(tuple(len(calendar.sessions(a, b)) for a, b in config.MASK_WINDOWS), config.MASK_BY_WINDOW)
        dval = set(calendar.era("dval"))
        self.assertTrue(set(mask) <= dval)
        self.assertEqual(len(dval) - len(mask), config.DVAL_MASKED)

    def test_the_mask_windows_are_prereg_hs(self):
        # PREREG-H's mask, as its text writes it (the pre-registration itself is pinned in the captain's scratch)
        written = ["2001-09-10..10-12", "2002-07-01..07-31", "2002-10-01..10-31", "2003-03-10..03-31",
                   "2007-02-26..03-09", "2007-07-23..08-31", "2008-01-14..01-31", "2008-03-10..03-31",
                   "2008-09-01..12-31"]
        for (a, b), words in zip(config.MASK_WINDOWS, written):
            first, last = words.split("..")
            self.assertEqual(a.isoformat(), first)
            self.assertEqual(b.isoformat()[5:], last)

    def test_from_2016_it_is_the_stores_calendar_and_before_1999_it_refuses(self):
        a, b = dt.date(2015, 12, 1), dt.date(2016, 2, 29)
        joined = calendar.sessions_with_flags(a, b)
        self.assertEqual([r for r in joined if r[0].year == 2016], estore.nyse_sessions(dt.date(2016, 1, 1), b))
        with self.assertRaises(ValueError):
            calendar.sessions(dt.date(1998, 12, 31), dt.date(1999, 1, 8))
        with self.assertRaises(ValueError):  # the equity store itself still refuses the deep years
            estore.nyse_sessions(dt.date(2015, 1, 2), dt.date(2015, 1, 9))

    def test_the_pseudo_dates(self):
        rows = calendar.pseudo(1762)
        self.assertEqual(rows[0][0], config.PSEUDO_FIRST)
        self.assertEqual(rows, estore.nyse_sessions(config.PSEUDO_FIRST, rows[-1][0]))
        with self.assertRaises(ValueError):
            calendar.pseudo(3000)


class TheFrenchSealCoversDval(unittest.TestCase):
    def test_every_dval_year_is_dropped_by_the_french_job(self):
        first, last = config.ERAS["dval"]
        for year in range(first.year, last.year + 1):
            self.assertIn(str(year), french.DROPPED_YEARS)
        self.assertEqual(french.DEEP_YEARS, tuple(str(y) for y in range(2001, 2009)))


class ThePublicRepository(unittest.TestCase):
    def walk(self):
        for path in REPO.rglob("*"):
            if path.is_file() and not (set(path.relative_to(REPO).parts) & SKIP):
                yield path

    def test_no_market_data_is_committed(self):
        found = {p.relative_to(REPO).as_posix() for p in self.walk() if p.suffix.lower() in DATA_SUFFIXES}
        self.assertEqual(found - KNOWN_ARRAYS, set(), "no csv, npz or parquet market data in the public repository")

    def test_the_fixtures_are_dates_only_and_pinned(self):
        for name, sha in ((config.CALENDAR_FIXTURE, config.CALENDAR_SHA256), (config.MASK_FIXTURE, config.MASK_SHA256)):
            data = (REPO / "league" / "deep" / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), sha, name)
            for line in data.decode("ascii").splitlines():
                self.assertRegex(line, r"^\d{4}-\d{2}-\d{2}$", name)

    def test_the_candidate_receipt_is_synthetic_and_holds_no_series(self):
        doc = json.loads((REPO / config.RECEIPT_PATH).read_text())
        self.assertIn("SYNTHETIC", doc["study"])
        self.assertIn("No market row", doc["study"])

        def longest(value) -> int:
            if isinstance(value, dict):
                return max([0, *(longest(v) for v in value.values())])
            if isinstance(value, list):
                numeric = sum(1 for v in value if isinstance(v, (int, float)) and not isinstance(v, bool))
                return max([numeric, *(longest(v) for v in value)])
            return 0

        self.assertLess(longest(doc), 64, "aggregates only: no per-world or per-session row")


if __name__ == "__main__":
    unittest.main()
