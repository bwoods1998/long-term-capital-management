"""The signals group of the Kalshi-scale run's recorders (Sept 25, 2026, workstream I2): Wikipedia
pageviews and alternative.me's Fear & Greed Index as backfilled point-in-time history, GDELT's news
volume, the NHC's active storms, the USGS earthquake feed and mempool.space recorded live.

Held to the three rules of league/feeds.py -- visible only from the moment it became knowable, live and
in replay; a failed poll stores nothing; unchanged content stored once -- and to each stamp: a day's
pageviews at the day's end plus 24 hours, an index value two hours after its day began, the House's
receive time for the rest.
"""

import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from league import feeds  # first: league.feeds imports league.open_feeds and registers its recorders
from league.feeds import FeedRecorder, request_feed, requested
from league.ledger import Ledger
from ltcm.data.chain import DIFFICULTY_URL, FEES_URL, FNG_URL, HASHRATE_URL, MEMPOOL_URL
from ltcm.data.hazards import NHC_URL, USGS_FEED_URL
from ltcm.data.signals import GDELT_DOC_URL, PAGEVIEWS_URL
from ltcm.tests import test_data_chain as chain_fixtures
from ltcm.tests import test_data_hazards as hazard_fixtures
from ltcm.tests import test_data_signals as signal_fixtures
from ltcm.tests.fakes import Clock, FakeTransport, TransportError


def epoch(text: str) -> float:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class RecorderCase(unittest.TestCase):
    START = "2026-09-25T06:40:00Z"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(self.START)
        self.alerts = []
        self.slept = []
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)

    def recorder(self, keys, transports=None, **kw) -> FeedRecorder:
        kw.setdefault("sleep", self.slept.append)
        recorder = FeedRecorder(path=Path(self.dir.name) / "feeds.sqlite", transports=transports, clock=self.clock, ledger=self.ledger,
                                alert=lambda level, text: self.alerts.append((level, text)), keys=keys, **kw)
        self.addCleanup(recorder.close)
        return recorder

    def stamps(self, store, feed, key) -> list:
        return [at for (at,) in store.db.execute("SELECT received FROM snapshots WHERE feed = ? AND key = ? ORDER BY received", (feed, key))]


# ------------------------------------------------------------------------------ pageviews
class Wikimedia:
    """A Wikimedia that serves every day up to yesterday (UTC) for any title, views = the day of the month x 100."""

    def __init__(self, clock):
        self.clock = clock
        self.asked = []

    def answer(self, method, url, body):
        parts = url.split("/")
        title, start, end = urllib.parse.unquote(parts[-4]), parts[-2], parts[-1]
        self.asked.append((title, start, end))
        first = datetime.strptime(start, "%Y%m%d").date()
        last = min(datetime.strptime(end, "%Y%m%d").date(), datetime.fromtimestamp(self.clock(), timezone.utc).date() - timedelta(days=1))
        items, day = [], first
        while day <= last:
            items.append({"project": "en.wikipedia", "article": title, "granularity": "daily", "timestamp": day.strftime("%Y%m%d00"),
                          "access": "all-access", "agent": "user", "views": day.day * 100})
            day += timedelta(days=1)
        if not items:
            return (404, {}, signal_fixtures.pageviews_404())
        return {"items": items}

    def transport(self):
        return FakeTransport({PAGEVIEWS_URL + "/*": self.answer})


class Pageviews(RecorderCase):
    def test_a_day_is_stamped_a_day_after_it_ended_and_never_shown_before(self):
        transport = FakeTransport({PAGEVIEWS_URL + "/*": signal_fixtures.pageviews()})
        store = self.recorder({"pageviews": ["bitcoin"]}, transports={"pageviews": transport})
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "pageviews", "bitcoin")
        self.assertEqual([feeds.stamp(s) for s in (stamps[0], stamps[-1])], ["2026-09-17T00:00:00.000Z", "2026-09-25T00:00:00.000Z"])
        self.assertEqual(len(stamps), 9)  # Sept 15-23: Sept 24's is not shown before Sept 26 00:00Z
        row = store.latest({"pageviews": ["BTC"]}, self.clock())["pageviews"]["bitcoin"]
        self.assertEqual((row["t"], row["date"], row["views"], row["article"]), ("2026-09-25T00:00:00.000Z", "2026-09-23", 7952, "Bitcoin"))
        week = [2332, 2450, 2183, 2379, 2513, 2469, 2769]  # Sept 16-22
        self.assertEqual(row["avg_7d"], round(sum(week) / 7, 2))
        self.assertEqual(row["ratio_7d"], round(7952 / round(sum(week) / 7, 2), 4))
        earlier = store.latest({"pageviews": ["bitcoin"]}, epoch("2026-09-24T23:59:59Z"))["pageviews"]["bitcoin"]
        self.assertEqual((earlier["date"], earlier["avg_7d"]), ("2026-09-22", round(sum([2668] + week[:6]) / 7, 2)))
        first_week = store.latest({"pageviews": ["bitcoin"]}, epoch("2026-09-23T23:59:59Z"))["pageviews"]["bitcoin"]
        self.assertEqual((first_week["date"], first_week["avg_7d"], first_week["ratio_7d"]), ("2026-09-21", None, None))  # Sept 14 is not held

    def test_the_backfill_covers_the_window_in_one_request_and_a_live_pass_asks_only_new_days(self):
        wiki = Wikimedia(self.clock)
        store = self.recorder({"pageviews": ["anthropic"]}, transports={"pageviews": wiki.transport()})
        store.run()
        self.assertEqual(len(wiki.asked), 1)
        stamps = self.stamps(store, "pageviews", "anthropic")
        self.assertLessEqual(stamps[0], self.clock() - 68 * 86400.0 + 86400.0)  # the replay window and the week before it
        self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {86400.0})
        self.assertTrue(store.coverage({"pageviews": ["anthropic"]})["pageviews"]["anthropic"]["backfill"]["complete"])
        self.clock.set("2026-09-26T00:40:00Z")
        store.run()
        self.assertEqual(wiki.asked[-1], ("Anthropic", "20260924", "20260924"))
        row = store.latest({"pageviews": ["KXANTHSHARE"]}, self.clock())["pageviews"]["anthropic"]
        self.assertEqual((row["t"], row["date"], row["views"]), ("2026-09-26T00:00:00.000Z", "2026-09-24", 2400))

    def test_a_failed_request_stores_nothing(self):
        transport = FakeTransport({PAGEVIEWS_URL + "/*": (503, {}, b"upstream busy")})
        store = self.recorder({"pageviews": ["trump"]}, transports={"pageviews": transport})
        out = store.run()
        self.assertTrue(out["failed"] and "HTTP 503" in out["failed"][0][2], out["failed"])
        self.assertEqual(self.stamps(store, "pageviews", "trump"), [])


# ---------------------------------------------------------------------------------- GDELT
class Gdelt(RecorderCase):
    def test_each_subject_is_one_request_six_seconds_apart_stamped_at_receipt_and_stored_once(self):
        transport = FakeTransport({GDELT_DOC_URL: signal_fixtures.timeline()})
        store = self.recorder({"gdelt": ["bitcoin", "fed"]}, transports={"gdelt": transport})
        out = store.run()
        self.assertEqual(out["failed"], [])
        self.assertEqual([c["query"]["query"] for c in transport.calls], ["bitcoin", '"federal reserve"'])
        self.assertEqual(self.slept, [6.0])  # the second waited: GDELT allows one request every five seconds
        row = store.latest({"gdelt": ["BTC"]}, self.clock())["gdelt"]["bitcoin"]
        self.assertEqual((row["t"], row["query"], len(row["points"])), ("2026-09-25T06:40:00.000Z", "bitcoin", 209))
        self.assertEqual(row["articles_24h"], sum(p["articles"] for p in row["points"]))
        self.assertEqual(store.latest({"gdelt": ["bitcoin"]}, self.clock() - 0.001), {})
        self.clock.advance(3 * 3600 + 10)
        store.run()
        self.assertEqual(store.coverage({"gdelt": ["bitcoin"]})["gdelt"]["bitcoin"]["snapshots"], 1)

    def test_a_refusal_holds_every_subject_for_five_minutes_without_asking(self):
        transport = FakeTransport({GDELT_DOC_URL: (429, {"content-type": "text/plain"}, signal_fixtures.gdelt_429())})
        store = self.recorder({"gdelt": ["bitcoin", "trump"]}, transports={"gdelt": transport})
        out = store.run()
        self.assertEqual(len(transport.calls), 1)  # the second subject was not asked
        self.assertEqual(sorted(k for f, k, _ in out["failed"]), ["bitcoin", "trump"])
        self.assertEqual(self.stamps(store, "gdelt", "bitcoin"), [])
        self.assertEqual(self.alerts, [])  # warned only after three failed polls in a row
        transport.route(GDELT_DOC_URL, signal_fixtures.timeline())
        self.clock.advance(301)
        store.run()
        self.assertEqual(len(store.latest({"gdelt": ["bitcoin", "trump"]}, self.clock())["gdelt"]), 2)


# ---------------------------------------------------------------------------------- hazards
class Storms(RecorderCase):
    def test_one_request_answers_every_basin_and_a_quiet_basin_is_a_row(self):
        answer = hazard_fixtures.storms()
        transport = FakeTransport({NHC_URL: answer})
        store = self.recorder({"storms": ["atlantic", "central_pacific", "all"]}, transports={"storms": transport})
        store.run()
        self.assertEqual(len(transport.calls), 1)
        rows = store.latest({"storms": ["atlantic", "cp", "hurricanes"]}, self.clock())["storms"]
        self.assertEqual([s["name"] for s in rows["atlantic"]["storms"]], ["Fay", "Gonzalo"])
        self.assertEqual((rows["central_pacific"]["count"], rows["all"]["count"]), (1, 5))
        self.assertEqual(rows["atlantic"]["t"], "2026-09-25T06:40:00.000Z")
        transport.route(NHC_URL, {"activeStorms": []})
        self.clock.advance(1800)
        store.run()
        quiet = store.latest({"storms": ["atlantic"]}, self.clock())["storms"]["atlantic"]
        self.assertEqual((quiet["count"], quiet["storms"]), (0, []))  # known to be quiet, not unavailable
        self.clock.advance(1800)
        store.run()
        self.assertEqual(store.coverage({"storms": ["atlantic"]})["storms"]["atlantic"]["snapshots"], 2)  # the same list: stored once


class Quakes(RecorderCase):
    def test_a_feed_is_stored_when_its_events_change_not_when_it_is_regenerated(self):
        answer = hazard_fixtures.quakes()
        transport = FakeTransport({USGS_FEED_URL.format(feed="4.5_day"): answer})
        store = self.recorder({"quakes": ["m4.5_day"]}, transports={"quakes": transport})
        store.run()
        row = store.latest({"quakes": ["earthquakes"]}, self.clock())["quakes"]["m4.5_day"]
        self.assertEqual((row["count"], len(row["events"]), row["t"]), (12, 12, "2026-09-25T06:40:00.000Z"))
        self.assertNotIn("generated", row)
        regenerated = hazard_fixtures.quakes()
        regenerated["metadata"]["generated"] += 900000
        transport.route(USGS_FEED_URL.format(feed="4.5_day"), regenerated)
        self.clock.advance(900)
        store.run()
        self.assertEqual(store.coverage({"quakes": ["m4.5_day"]})["quakes"]["m4.5_day"]["snapshots"], 1)

    def test_a_feed_that_fails_is_a_failed_poll(self):
        transport = FakeTransport({USGS_FEED_URL.format(feed="significant_week"): TransportError("GET https://earthquake.usgs.gov/... failed: timed out")})
        store = self.recorder({"quakes": ["significant_week"]}, transports={"quakes": transport})
        out = store.run()
        self.assertEqual([(f, k) for f, k, _ in out["failed"]], [("quakes", "significant_week")])
        self.assertEqual(store.latest({"quakes": ["significant_week"]}, self.clock()), {})


# ------------------------------------------------------------------------------ crypto network
class Mempool(RecorderCase):
    def test_three_requests_a_pass_and_the_hashrate_every_six_hours(self):
        transport = chain_fixtures.transport()
        store = self.recorder({"mempool": ["BTC"]}, transports={"mempool": transport})
        store.run()
        self.assertEqual([c["url"] for c in transport.calls], [FEES_URL, MEMPOOL_URL, DIFFICULTY_URL, HASHRATE_URL])
        row = store.latest({"mempool": ["bitcoin"]}, self.clock())["mempool"]["BTC"]
        self.assertEqual((row["t"], row["fees"]["fastest"], row["mempool"]["count"], row["hashrate"]["asked"]),
                         ("2026-09-25T06:40:00.000Z", 3.0, 81868.0, "2026-09-25T06:40:00Z"))
        self.clock.advance(900)
        store.run()
        self.assertEqual([c["url"] for c in transport.calls[4:]], [FEES_URL, MEMPOOL_URL, DIFFICULTY_URL])
        self.assertEqual(store.coverage({"mempool": ["BTC"]})["mempool"]["BTC"]["snapshots"], 1)  # nothing moved

    def test_a_refusal_is_a_failed_poll_with_nothing_stored(self):
        transport = FakeTransport({FEES_URL: (429, {}, b"Too Many Requests")})
        store = self.recorder({"mempool": ["BTC"]}, transports={"mempool": transport})
        out = store.run()
        self.assertTrue(out["failed"] and "HTTP 429" in out["failed"][0][2], out["failed"])
        self.assertEqual(store.latest({"mempool": ["BTC"]}, self.clock()), {})


class FearGreed(RecorderCase):
    def test_a_value_is_shown_two_hours_after_its_day_began_and_backfilled_until_the_index_ends(self):
        transport = FakeTransport({FNG_URL: chain_fixtures.fear_greed()})
        store = self.recorder({"fear_greed": ["crypto"]}, transports={"fear_greed": transport})
        out = store.run()
        self.assertEqual(out["failed"], [])
        stamps = self.stamps(store, "fear_greed", "crypto")
        self.assertEqual([feeds.stamp(s) for s in (stamps[0], stamps[-1])], ["2026-09-16T02:00:00.000Z", "2026-09-25T02:00:00.000Z"])
        row = store.latest({"fear_greed": ["fng"]}, self.clock())["fear_greed"]["crypto"]
        self.assertEqual((row["t"], row["date"], row["value"], row["classification"], row["change_1d"]),
                         ("2026-09-25T02:00:00.000Z", "2026-09-25", 71, "Greed", 0.0))
        self.assertEqual(row["avg_7d"], round((71 + 71 + 71 + 78 + 70 + 71 + 71) / 7, 2))  # Sept 19-25
        before = store.latest({"fear_greed": ["crypto"]}, epoch("2026-09-25T01:59:59Z"))["fear_greed"]["crypto"]
        self.assertEqual(before["date"], "2026-09-24")
        state = store.coverage({"fear_greed": ["crypto"]})["fear_greed"]["crypto"]["backfill"]
        self.assertTrue(state["complete"] and state["exhausted"], state)  # ten days is all the recorded answer holds
        self.assertGreaterEqual(int(transport.calls[0]["query"]["limit"]), 60)


# ------------------------------------------------------------------------------ vocabulary
class WhatIsDeclared(unittest.TestCase):
    def test_needs_accept_the_new_keys_in_their_own_spellings(self):
        self.assertEqual(requested({"pageviews": ["BTC", "KXANTHSHARE", "Donald Trump", "Claude (language model)", "rotten tomatoes"],
                                    "gdelt": ["bitcoin", "claude", "KXFED"], "storms": ["hurricanes", "Atlantic"],
                                    "quakes": ["4.5_day", "significant"], "mempool": ["XBT"], "fear_greed": ["crypto"]}),
                         {"pageviews": ["bitcoin", "anthropic", "trump", "claude"], "gdelt": ["bitcoin", "fed"],
                          "storms": ["all", "atlantic"], "quakes": ["m4.5_day", "significant_week"], "mempool": ["BTC"],
                          "fear_greed": ["crypto"]})
        self.assertIn("pageviews", feeds.HISTORY_FEEDS)
        self.assertIn("fear_greed", feeds.HISTORY_FEEDS)
        self.assertNotIn("gdelt", feeds.HISTORY_FEEDS)

    def test_requests_name_the_feeds_in_their_own_words_and_leave_the_others_alone(self):
        self.assertEqual({name: request_feed(name) for name in (
            "wikipedia_pageviews_bitcoin", "gdelt_news_volume", "news_tone_trump", "hurricane_tracks", "earthquake_feed",
            "btc_mempool_fees", "bitcoin_hashrate", "crypto_fear_greed_index", "attention_underlying_value_feed",
            "rotten_tomatoes_point_in_time_feed", "underlying_value_feed", "attention_observations", "live_sports_scores",
            "gdelt_news_volume_history")},
            {"wikipedia_pageviews_bitcoin": "pageviews", "gdelt_news_volume": "gdelt", "news_tone_trump": "gdelt",
             "hurricane_tracks": "storms", "earthquake_feed": "quakes", "btc_mempool_fees": "mempool", "bitcoin_hashrate": "mempool",
             "crypto_fear_greed_index": "fear_greed", "attention_underlying_value_feed": None,
             "rotten_tomatoes_point_in_time_feed": None, "underlying_value_feed": None, "attention_observations": None,
             "live_sports_scores": "sports", "gdelt_news_volume_history": None})

    def test_every_host_is_on_record(self):
        from league import open_feeds_signals

        hosts = feeds.league_hosts()
        for source in open_feeds_signals.SOURCES:
            self.assertIn(source.host, hosts, source.name)
            self.assertIs(feeds.RECORDERS[source.name], source)


if __name__ == "__main__":
    unittest.main()
