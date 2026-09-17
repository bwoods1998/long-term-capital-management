import tempfile
import unittest
from pathlib import Path
from ltcm.research_cache import ResearchCache


class CacheTests(unittest.TestCase):
    def test_failed_experiments_are_remembered_but_never_cached_as_successes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "cache.sqlite"
            cache = ResearchCache(path, engine="a")
            candidate = {"id": "c1", "subject": "reversion", "kind": "code", "code": "return []", "params": {}, "error": "history request failed", "hypothesis": "fade large moves"}
            cache.remember(candidate, {"end": "2026-01-01"})
            restarted = ResearchCache(path, engine="a")
            self.assertEqual(restarted.lessons("reversion")[0]["error"], "history request failed")
            self.assertEqual(restarted.lessons("different"), [])
            self.assertIsNone(restarted.get("c1"))

    def test_restart_key_invalidation_expiry_and_failure(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "cache.sqlite"
            clock = [100.0]
            cache = ResearchCache(path, engine="a", ttl_seconds=60, clock=lambda: clock[0])
            spec = {"code": "a", "params": {"x": 1}, "end": "2026-01-01", "fill_model": "conservative"}
            key = cache.key(spec, .66)
            report = {"errors": 0, "trades": 5, "pnl_usd": 1}
            cache.put(key, report)
            other = ResearchCache(path, engine="a", clock=lambda: clock[0])
            self.assertEqual(other.get(key), report)
            for changed in [dict(spec, code="b"), dict(spec, end="2026-01-02"), dict(spec, params={"x": 2}), dict(spec, fill_model="optimistic")]:
                self.assertIsNone(cache.get(cache.key(changed, .66)))
            self.assertNotEqual(key, cache.key(spec, .5))
            self.assertNotEqual(key, ResearchCache(path, engine="b").key(spec, .66))
            cache.put("failed", {"errors": 1})
            cache.put("unsupported", {"errors": 0, "unsupported": "no history"})
            self.assertIsNone(cache.get("failed"))
            self.assertIsNone(cache.get("unsupported"))
            clock[0] += 61
            self.assertIsNone(cache.get(key))
