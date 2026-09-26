import tempfile
import unittest
from pathlib import Path

from league.tests.fakes import Clock
from league.commons import Commons
from league.ledger import Ledger


class FakeNews:
    def search(self, query, limit=5):
        return [{"title": f"headline about {query}", "url": "https://news.example/x", "published": None, "source": "News"}]


class CommonsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite")

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_web_search_uses_the_backend_and_falls_back_to_news(self):
        ok = Commons(self.ledger, search=lambda q, n: [{"title": "t", "url": "u", "published": None, "excerpt": "e"}])
        self.assertEqual(ok.web_search("kalshi fees")["source"], "web")

        def broken(query, limit):
            raise OSError("down")

        fallback = Commons(self.ledger, search=broken, news=FakeNews())
        out = fallback.web_search("kalshi fees")
        self.assertEqual(out["source"], "news")
        self.assertIn("kalshi fees", out["results"][0]["title"])
        self.assertIn("error", Commons(self.ledger).web_search("x"))
        self.assertIn("error", ok.web_search("   "))

    def test_the_library_is_shared_searchable_and_permanent(self):
        commons = Commons(self.ledger)
        self.assertIn("error", commons.library_write("a1", "x", "too short"))
        commons.library_write("a1", "Kalshi maker fees by series", "Crypto, weather and index series charge a resting order nothing; sports and Fed series charge a quarter of the taker rate.", ["kalshi", "fees"])
        commons.library_write("a2", "Overnight drift in SPY", "Most of the index's return since 1993 accrued between the close and the next open, not during the day.", ["equities"])
        found = commons.library_search("maker fees kalshi")
        self.assertEqual(found["results"][0]["title"], "Kalshi maker fees by series")
        self.assertEqual(found["results"][0]["by"], "a1")
        note = Commons(self.ledger).library_read("overnight drift in spy")  # another reader, by title
        self.assertIn("close and the next open", note["text"])
        self.assertIn("error", commons.library_read("nothing"))

    def test_tool_requests_queue_until_fulfilled(self):
        commons = Commons(self.ledger)
        self.assertIn("error", commons.request_tool("a1", "x", "short"))
        queued = commons.request_tool("a1", "Option Chains!", "I need option chain quotes for SPY to price defined-risk spreads around events.")
        self.assertEqual([r["name"] for r in commons.open_requests()], ["option_chains"])
        commons.fulfil(queued["queued"], "built as ctx['chains']", change="merton/toolsmith-1")
        self.assertEqual(commons.open_requests(), [])

    def test_the_playbook_keeps_the_graveyards_lessons(self):
        commons = Commons(self.ledger)
        commons.playbook_add("Post-mortem: crypto-trend", "Died of fees: 41 round trips at 0.5% each against a 0.2% average move.", source="graveyard")
        commons.playbook_add("Lesson: favourites", "Resting bids above 90 cents earned; taking the offer did not.", source="teacher")
        self.assertEqual(len(commons.playbook_read()["entries"]), 2)
        self.assertEqual(commons.playbook_read("fees")["entries"][0]["title"], "Post-mortem: crypto-trend")


if __name__ == "__main__":
    unittest.main()


class TheToolsmithQueue(unittest.TestCase):
    """It was plain ledger order -- oldest first -- and the toolsmith saw the first ten. With
    eighteen open on the floor's first night the newest eight could never be seen, and the oldest
    ten were ones he had already looked at and could not build, so the window was clogged with the
    same rows for ever. Found by the stall audit, Sept 20, 2026."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.commons = Commons(self.ledger, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def ask(self, agent, name, *, after=0.0):
        self.clock.advance(after)
        return self.ledger.append("tool.request", {"name": name, "description": f"{agent} wants {name}"}, agent=agent).id

    def test_what_most_agents_ask_for_comes_first_then_the_newest(self):
        self.ask("a1", "old_and_lonely")
        for agent in ("b1", "b2", "b3"):
            self.ask(agent, "the_underlier", after=60)
        newest = self.ask("c1", "brand_new", after=60)
        rows = self.commons.open_requests(limit=3)
        self.assertEqual([r["name"] for r in rows[:3]], ["the_underlier", "the_underlier", "the_underlier"])
        self.assertEqual(rows[0]["asked_by_agents"], 3)
        self.assertIn(newest, [r["id"] for r in self.commons.open_requests()])   # and the newest is never crowded out
        self.assertLess([r["id"] for r in self.commons.open_requests()].index(newest),
                        [r["name"] for r in self.commons.open_requests()].index("old_and_lonely"))

    def test_a_request_nothing_closes_falls_out_of_the_queue(self):
        stale = self.ask("a1", "forgotten")
        self.assertIn(stale, [r["id"] for r in self.commons.open_requests()])
        self.clock.advance(4 * 86400)
        self.assertNotIn(stale, [r["id"] for r in self.commons.open_requests()])
        fresh = self.ask("a1", "forgotten")                 # asking again is the signal that it matters
        self.assertIn(fresh, [r["id"] for r in self.commons.open_requests()])

    def test_a_fulfilled_request_still_leaves_the_queue(self):
        one = self.ask("a1", "buildable")
        self.commons.fulfil(one, "built it")
        self.assertEqual(self.commons.open_requests(), [])

    def test_blocked_requests_survive_age_and_restart_without_being_rebought(self):
        one = self.ask('a1', 'positioning_feed')
        self.ledger.append('tool.blocked', {'request': one, 'outcome': 'requires a source adapter',
                                          'owner': 'house-engineering'})
        self.clock.advance(10 * 86400)
        restarted = Commons(self.ledger, clock=self.clock)
        self.assertEqual(restarted.open_requests(), [])
        self.assertEqual(restarted.blocked_requests()[0]['id'], one)
        reply = restarted.request_tool('a1', 'positioning_feed', 'Still need the point-in-time observations for the hypothesis.')
        self.assertEqual(reply['queued'], one)
        self.assertTrue(reply['existing'])
        self.assertEqual(self.ledger.count(kinds='tool.request'), 1)

    def test_legacy_cannot_build_answer_is_recovered_until_a_real_resolution(self):
        one = self.ask('a1', 'observed_bars')
        self.ledger.append('tool.fulfilled', {'request': one, 'status': 'answered',
            'outcome': 'cannot be a pure tool: needs an engine change'})
        row = self.commons.blocked_requests()[0]
        self.assertTrue(row['legacy_advice'])
        self.assertEqual(self.commons.open_requests(), [])
        self.commons.fulfil(one, 'deployed and verified', change='verified-change')
        self.assertEqual(self.commons.blocked_requests(), [])

    def test_repeating_the_same_name_does_not_count_as_more_agents(self):
        for _ in range(3):
            self.ask('a1', 'same_feed')
        self.ask('a2', 'same_feed')
        self.assertTrue(all(r['asked_by_agents'] == 2 for r in self.commons.open_requests()))


class WebFetchThroughTheGateway(unittest.TestCase):
    """I1 (Sept 25, 2026): `web_fetch` asks the gateway for one page; every failure is an answer."""

    TOKEN = "gateway-token-that-is-long-enough-1234567890"

    class Reply:
        def __init__(self, status, body):
            self.status, self.body = status, body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit=-1):
            return self.body if limit < 0 else self.body[:limit]

    def opener(self, status=200, body=b"{}", raises=None):
        sent = []

        def open_(request, timeout=None):
            sent.append((request, timeout))
            if raises is not None:
                raise raises
            return self.Reply(status, body)
        return open_, sent

    def test_the_gateway_is_asked_with_the_token_and_a_json_body(self):
        import json
        from league.commons import gateway_fetch

        page = {"url": "https://example.com/", "final_url": "https://example.com/", "status": 200, "text": "hi"}
        open_, sent = self.opener(body=json.dumps(page).encode())
        fetch = gateway_fetch("https://gw.example.workers.dev/", lambda: self.TOKEN, opener=open_)
        self.assertEqual(fetch("https://example.com/", "nfl-model-2"), (200, page))
        request, timeout = sent[0]
        self.assertEqual((request.full_url, request.get_method(), timeout), ("https://gw.example.workers.dev/v1/web/fetch", "POST", 40.0))
        self.assertEqual(request.get_header("Authorization"), "Bearer " + self.TOKEN)
        self.assertEqual(json.loads(request.data), {"url": "https://example.com/", "agent": "nfl-model-2"})

    def test_an_http_error_is_returned_with_its_status_and_an_oversized_answer_raises(self):
        import io
        import urllib.error
        from league.commons import MAX_FETCH_ANSWER_BYTES, gateway_fetch

        refused = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b'{"error": "The url names a loopback address.", "url": "http://127.0.0.1/"}'))
        open_, _ = self.opener(raises=refused)
        self.assertEqual(gateway_fetch("https://gw", lambda: self.TOKEN, opener=open_)("http://127.0.0.1/", "a")[0], 403)
        worker = urllib.error.HTTPError("u", 500, "Error", {}, io.BytesIO(b"error code: 1101"))
        open_, _ = self.opener(raises=worker)
        self.assertEqual(gateway_fetch("https://gw", lambda: self.TOKEN, opener=open_)("https://example.com/", "a"), (500, {}))
        open_, _ = self.opener(body=b"x" * (MAX_FETCH_ANSWER_BYTES + 1))
        with self.assertRaises(ValueError):
            gateway_fetch("https://gw", lambda: self.TOKEN, opener=open_)("https://example.com/", "a")

    def test_web_fetch_answers_every_outcome_and_says_whether_the_gateway_judged_the_url(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ledger = Ledger(Path(directory.name) / "l.sqlite")
        self.addCleanup(ledger.close)
        page = {"url": "https://example.com/", "final_url": "https://example.com/", "status": 404, "content_type": "text/html",
                "title": "Not Found", "text": "No such page", "truncated": False, "bytes": 40, "fetched_at": "2026-09-26T16:00:00.000Z", "extra": 1}
        answers = iter([(200, page), (403, {"error": "The url names a private address.", "url": "http://10.0.0.1/", "refused": "url"}),
                        (429, {"error": "Today's cap is reached.", "cap": "web_fetch_day"}), (500, {}), OSError("down")])

        def fetch(url, agent):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return answer

        commons = Commons(ledger, fetch=fetch)
        ok = commons.web_fetch("https://example.com/", "a1")
        self.assertEqual((ok["judged"], ok["status"], ok["text"]), (True, 404, "No such page"))
        self.assertNotIn("extra", ok)
        refused = commons.web_fetch("http://10.0.0.1/", "a1")
        self.assertEqual((refused["judged"], refused["refused"], refused["gateway_status"]), (True, "url", 403))
        capped = commons.web_fetch("https://example.com/", "a1")
        self.assertEqual((capped["judged"], capped["cap"]), (False, "web_fetch_day"))
        self.assertEqual(commons.web_fetch("https://example.com/", "a1"),
                         {"error": "the gateway answered HTTP 500", "gateway_status": 500, "judged": False, "reached": True})
        self.assertEqual(commons.web_fetch("https://example.com/", "a1"),
                         {"error": "the gateway could not be reached: OSError", "judged": False, "reached": True})
        self.assertEqual((ok["reached"], refused["reached"], capped["reached"]), (True, True, False))
        for url in ("", "ftp://example.com/", "https://example.com/" + "a" * 2100):
            answer = commons.web_fetch(url, "a1")
            self.assertEqual((answer["judged"], answer["reached"]), (False, False))
        self.assertIn("not configured", Commons(ledger).web_fetch("https://example.com/", "a1")["error"])

    def test_what_may_have_been_read_is_told_from_what_never_was(self):
        """Review (i1/review): a Worker that died on a page (5xx naming no url) or a call that timed
        out may have read it, and is charged; a request refused before reading, or a connection
        never made, is not."""
        import socket
        import urllib.error

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ledger = Ledger(Path(directory.name) / "l.sqlite")
        self.addCleanup(ledger.close)
        outcomes = [
            ((503, {}), True),  # Cloudflare's "Worker exceeded resource limits" page
            ((502, {}), True),
            ((429, {"error": "busy", "busy": True}), False),
            ((429, {"error": "cap", "cap": "web_fetch_day"}), False),
            ((401, {"error": "Unauthorized."}), False),
            ((400, {"error": "bad body"}), False),
            (TimeoutError("timed out"), True),
            (urllib.error.URLError(TimeoutError("timed out")), True),
            (ValueError("the gateway's answer is larger than a page can be"), True),
            (urllib.error.URLError(ConnectionRefusedError(111, "refused")), False),
            (urllib.error.URLError(socket.gaierror(-2, "Name or service not known")), False),
        ]
        queue = [outcome for outcome, _ in outcomes]

        def fetch(url, agent):
            outcome = queue.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        commons = Commons(ledger, fetch=fetch)
        for outcome, reached in outcomes:
            answer = commons.web_fetch("https://example.com/", "a1")
            self.assertEqual(answer["reached"], reached, repr(outcome))
            self.assertIn("error", answer)

    def test_a_page_is_kept_only_as_bounded_fields_of_the_right_types(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        ledger = Ledger(Path(directory.name) / "l.sqlite")
        self.addCleanup(ledger.close)
        page = {"url": "https://example.com/", "final_url": "https://example.com/" + "p" * 5000, "status": "200", "content_type": "text/" + "x" * 9000,
                "title": "T" * 5000, "text": "body", "truncated": "yes", "bytes": True, "fetched_at": "2026-09-26T16:00:00.000Z" + "z" * 500}
        error = {"error": "e" * 5000, "url": "https://example.com/", "refused": {"nested": ["x"] * 1000}, "status": [1, 2], "content_type": "c" * 5000}
        answers = iter([(200, page), (403, error)])
        commons = Commons(ledger, fetch=lambda url, agent: next(answers))
        ok = commons.web_fetch("https://example.com/", "a1")
        self.assertEqual((len(ok["final_url"]), len(ok["content_type"]), len(ok["title"]), len(ok["fetched_at"])), (2048, 127, 300, 40))
        self.assertEqual((ok["status"], ok["bytes"], ok["truncated"], ok["text"]), (None, None, False, "body"))
        bad = commons.web_fetch("https://example.com/", "a1")
        self.assertEqual((len(bad["error"]), len(bad["content_type"])), (400, 400))
        self.assertNotIn("refused", bad)
        self.assertNotIn("status", bad)
