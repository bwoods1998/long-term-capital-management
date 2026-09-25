"""mempool.space and alternative.me's Fear & Greed Index (Sept 25, 2026), read from payloads recorded that day."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from ltcm.data import DataError
from ltcm.data.chain import (DIFFICULTY_URL, FEES_URL, FNG_URL, HASHRATE_URL, MEMPOOL_URL, Chain, parse_difficulty, parse_fear_greed,
                             parse_fees, parse_hashrate, parse_mempool)
from ltcm.tests.fakes import FakeTransport

FIXTURES = Path(__file__).parent / "fixtures" / "feeds"


def mempool():
    """mempool.space's /api/v1/fees/recommended, /api/mempool (histogram cut to 12 buckets), /api/v1/difficulty-adjustment and
    /api/v1/mining/hashrate/3d, recorded Sept 25, 2026 06:59Z."""
    return json.loads((FIXTURES / "mempool_space.json").read_text(encoding="utf-8"))


def fear_greed():
    """api.alternative.me/fng/?limit=10&format=json, recorded Sept 25, 2026 06:59Z."""
    return json.loads((FIXTURES / "alternative_fng_limit10.json").read_text(encoding="utf-8"))


def transport() -> FakeTransport:
    found = mempool()
    return FakeTransport({FEES_URL: found["fees"], MEMPOOL_URL: found["mempool"], DIFFICULTY_URL: found["difficulty"],
                          HASHRATE_URL: found["hashrate"], FNG_URL: fear_greed()})


class Mempool(unittest.TestCase):
    def test_the_recorded_answers(self):
        found = mempool()
        self.assertEqual(parse_fees(found["fees"]), {"fastest": 3.0, "half_hour": 1.0, "hour": 1.0, "economy": 1.0, "minimum": 1.0})
        self.assertEqual(parse_mempool(found["mempool"]), {"count": 81868.0, "vsize": 41816960.0, "total_fee_sats": 10216491.0})
        difficulty = parse_difficulty(found["difficulty"])
        self.assertEqual((difficulty["remaining_blocks"], difficulty["retarget_height"], difficulty["block_seconds"]), (1180.0, 969696.0, 619.4))
        self.assertAlmostEqual(difficulty["change_pct"], -3.0099365566789382)
        self.assertEqual(parse_hashrate(found["hashrate"])["hashrate_ehs"], 936.188)
        with self.assertRaises(DataError):
            parse_fees({"error": "rate limited"})

    def test_asked_with_the_contact_user_agent(self):
        from ltcm.data import CONTACT_USER_AGENT

        fake = transport()
        chain = Chain(fake)
        chain.fees(), chain.mempool(), chain.difficulty()
        self.assertEqual([c["url"] for c in fake.calls], [FEES_URL, MEMPOOL_URL, DIFFICULTY_URL])
        self.assertEqual(fake.calls[0]["headers"]["User-Agent"], CONTACT_USER_AGENT)


class FearGreed(unittest.TestCase):
    def test_the_recorded_days_oldest_first(self):
        rows = parse_fear_greed(fear_greed())
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[-1], {"t": 1790294400.0, "date": "2026-09-25", "value": 71, "classification": "Greed"})
        self.assertEqual(rows[0]["date"], "2026-09-16")
        with self.assertRaises(DataError):
            parse_fear_greed({"data": [], "metadata": {"error": "limit"}})

    def test_asked_for_limit_days(self):
        fake = transport()
        Chain(fake).fear_greed(60)
        self.assertEqual(fake.calls[0]["query"], {"limit": "60", "format": "json"})


if __name__ == "__main__":
    unittest.main()
