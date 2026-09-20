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
