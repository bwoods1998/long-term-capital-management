"""SEC reads retry EDGAR's 429/5xx answers a few times before they raise (Oct 19: one browse-edgar 503 failed the
first live open decision). Synthetic transport only."""

import unittest

from league.events import gw as G


class _Transport:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0

    def get(self, url, headers, timeout):
        self.calls += 1
        status = self.answers.pop(0)
        return status, {}, b"ok" if status == 200 else b""


class SecRetryTest(unittest.TestCase):
    def test_a_503_then_200_reads(self):
        waits = []
        t = _Transport([503, 503, 200])
        get = G.sec_getter(t, sleep=waits.append)
        self.assertEqual(get("https://www.sec.gov/x"), b"ok")
        self.assertEqual((t.calls, waits), (3, [1.0, 2.0]))

    def test_persistent_503_raises_after_the_waits(self):
        waits = []
        t = _Transport([503] * 4)
        get = G.sec_getter(t, sleep=waits.append)
        with self.assertRaises(G.GatewayError) as e:
            get("https://www.sec.gov/x")
        self.assertEqual(e.exception.status if hasattr(e.exception, "status") else 503, 503)
        self.assertEqual((t.calls, waits), (4, list(G.SEC_RETRY_WAITS)))

    def test_a_404_raises_at_once(self):
        waits = []
        t = _Transport([404])
        get = G.sec_getter(t, sleep=waits.append)
        with self.assertRaises(G.GatewayError):
            get("https://www.sec.gov/x")
        self.assertEqual((t.calls, waits), (1, []))

    def test_only_sec_urls(self):
        with self.assertRaises(ValueError):
            G.sec_getter(_Transport([200]), sleep=lambda s: None)("https://example.com/")


if __name__ == "__main__":
    unittest.main()
