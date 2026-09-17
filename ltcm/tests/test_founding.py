"""The firm hires itself: coverage, the venues' digest, a bounded proposal, founding, winding down."""

import copy
import json
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument
from ltcm.events import EventLog, canonical
from ltcm.evolve import Evolution
from ltcm.founding import FOUNDED_KIND, WIND_DOWN_REASON, Founding, FoundingError, instrument_target, parse_reply
from ltcm.manifest import DeskManifest, load_all
from ltcm.tests.test_manifest import SAMPLE
from ltcm.tests.test_service import DESK, ServiceCase, moment

REPO = Path(__file__).resolve().parents[2]
FOUNDERS = ("haghani", "hilibrand", "mullins", "scholes")
NIGHT = "2026-09-17T01:30:00.000Z"
HARD = {"max_position_pct": ["0.01", "0.50"], "max_order_notional_pct": ["0.01", "0.50"],
        "max_daily_loss_pct": ["0.01", "0.15"], "max_orders_per_day": [1, 480]}


# --------------------------------------------------------------------------- fakes


class FakeKalshi:
    """Pages of open markets and one series at a time, like `KalshiMarketData`."""

    def __init__(self, markets=None, categories=None, fail=False):
        self.markets_rows = markets if markets is not None else default_markets()
        self.categories = categories if categories is not None else dict(CATEGORIES)
        self.fail = fail
        self.market_calls = []
        self.series_calls = []

    def markets(self, *, status=None, limit=100, cursor=None, **kwargs):
        self.market_calls.append(dict(kwargs, status=status, limit=limit))
        if self.fail:
            raise RuntimeError("kalshi down")
        start = int(cursor or 0)
        page = self.markets_rows[start : start + limit]
        more = start + limit < len(self.markets_rows)
        return {"markets": page, "cursor": str(start + limit) if more else None}

    def series(self, ticker):
        self.series_calls.append(ticker)
        if ticker not in self.categories:
            raise RuntimeError("kalshi series: HTTP 404")
        return {"ticker": ticker, "category": self.categories[ticker], "title": f"{ticker} series"}


class FakeCoinbase:
    def __init__(self, rows=None, fail=False):
        self.rows = rows if rows is not None else default_products()
        self.fail = fail

    def products(self, *, product_type="SPOT", limit=None):
        if self.fail:
            raise RuntimeError("coinbase down")
        return list(self.rows)


class FakeProvider:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        if self.error is not None:
            raise self.error
        body = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return SimpleNamespace(output_text=body, cost_usd=Decimal("0.20"), incomplete=False)

    def spent_today(self, desk_id=None):
        return Decimal("0")


def market(ticker, event, volume, oi, price="0.40", title=None):
    return {"ticker": ticker, "event_ticker": event, "title": title or ticker, "volume_24h": Decimal(volume),
            "open_interest": Decimal(oi), "last_price": Decimal(price)}


def default_markets():
    return [
        market("KXNFLGAME-26SEP20KCBUF-KC", "KXNFLGAME-26SEP20KCBUF", 90000, 150000, "0.55", "Chiefs at Bills: winner?"),
        market("KXNFLGAME-26SEP20KCBUF-BUF", "KXNFLGAME-26SEP20KCBUF", 80000, 140000, "0.45"),
        market("KXFED-26OCT-H25", "KXFED-26OCT", 40000, 400000, "0.20", "Fed decision in October?"),
        market("KXHIGHNY-26SEP17-B72", "KXHIGHNY-26SEP17", 5000, 9000, "0.30"),
        market("KXOSCAR-27-BEST", "KXOSCAR-27", 10, 50, "0.10"),
        # a multivariate combo: huge open interest spread over parlays nobody trades
        market("KXMVECROSSCATEGORY-S1-ABC", "KXMVECROSSCATEGORY-S1", 900000, 9000000, "0.01"),
    ]


CATEGORIES = {"KXNFLGAME": "Sports", "KXFED": "Economics", "KXHIGHNY": "Climate and Weather",
              "KXMVECROSSCATEGORY": "Exotics"}


def product(pid, price, volume, **extra):
    base, quote = pid.split("-")
    return {"product_id": pid, "price": Decimal(price), "volume_24h": Decimal(volume), "base_currency_id": base,
            "quote_currency_id": quote, "status": "online", "trading_disabled": False, **extra}


def default_products():
    return [
        product("BTC-USD", "60000", "1000"),
        product("PEPE-USD", "0.00001", "90000000000000"),
        product("USDC-USD", "1", "900000000"),
        product("ETH-EUR", "2400", "5000"),
        product("DEAD-USD", "3", "100000", status="delisted"),
        product("BONK-USD", "0.00002", "100000000"),
    ]


def playbook(extra=""):
    return (
        "# Leahy playbook\n\n## Edge thesis\n\nKalshi NFL winner prices lag the sportsbook consensus by more "
        "than the fee for the first hour after an injury report. Proven wrong if the first twenty trades "
        "lose money after fees.\n\n## Session routine\n\n1. Read the injury report.\n" + extra
    )


def proposal(**overrides):
    manifest = json.loads((REPO / "ltcm" / "desks" / "mullins.json").read_text())
    manifest.update(
        id="leahy", family="sports", name="Leahy", capital={"mode": "shadow", "usd": "150"},
        persona="A sports trader who prices games from the consensus line.",
        mandate="Trade Kalshi NFL game-winner markets (series KXNFLGAME) against the sportsbook consensus.",
    )
    manifest["cadence"] = {"sessions": ["10:00", "13:00", "19:30"], "timezone": "America/New_York",
                           "triggers": ["event_resolution"], "weekdays_only": False}
    data = {
        "family": "sports",
        "id": "leahy",
        "name": "Leahy",
        "rationale": "Nothing on the floor prices sports, and NFL winners are Kalshi's deepest markets <today>.",
        "universe": "Kalshi NFL game winners (KXNFLGAME)",
        "targets": ["KXNFLGAME"],
        "manifest": manifest,
        "playbook_markdown": playbook(),
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------- the case


class FoundingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.desks = self.root / "desks"
        self.playbooks = self.root / "playbooks"
        self.desks.mkdir()
        self.playbooks.mkdir()
        for desk_id in FOUNDERS:  # the four the owner wrote, exactly as they ship
            shutil.copy(REPO / "ltcm" / "desks" / f"{desk_id}.json", self.desks / f"{desk_id}.json")
            shutil.copy(REPO / "playbooks" / f"{desk_id}.md", self.playbooks / f"{desk_id}.md")
        self.log = EventLog(self.root / "events.sqlite")
        self.evolution = Evolution(self.log, self.desks, self.playbooks, config={"target_variants": 2, "max_variants": 6})
        self.provider = FakeProvider(proposal())
        self.kalshi = FakeKalshi()
        self.coinbase = FakeCoinbase()
        self.founding = self.build()

    def tearDown(self):
        self.founding.wait(5)
        self.log.close()
        self.tmp.cleanup()

    def build(self, **config):
        return Founding(
            self.log,
            self.evolution,
            provider=self.provider,
            config={"live_venues": ["kalshi", "coinbase"], "hard_limits": HARD, "sweep_retry_pause_seconds": 0, **config},
            kalshi=self.kalshi,
            coinbase=self.coinbase,
        )

    def fill(self, desk, side, quantity, price, at, instrument):
        seq = self.log.latest_seq() + 1
        self.log.append(
            "broker:shadow", "broker.fill",
            {"fill_id": f"f{seq}", "order_id": f"o{seq}", "desk_id": desk, "instrument": instrument.to_dict(),
             "side": side, "quantity": str(quantity), "price": str(price), "fee": "0", "at": at},
            at=at,
        )

    def allocate(self, allocations, at):
        self.log.append(
            "committee", "committee.allocation",
            {"allocations": {k: str(v) for k, v in allocations.items()}, "reasons": {}}, at=at,
        )


class KalshiListingTests(unittest.TestCase):
    """The two reads the digest needs from `KalshiMarketData`: combos excluded, one series."""

    def test_markets_can_exclude_the_combos_and_a_series_is_read_whole(self):
        from ltcm.data import DataError
        from ltcm.data.kalshi import BASE, KalshiMarketData
        from ltcm.tests.fakes import Clock, FakeTransport

        transport = FakeTransport({
            f"{BASE}/markets*": {"markets": [], "cursor": None},
            f"{BASE}/series/KXMLBGAME": {"series": {"ticker": "KXMLBGAME", "category": "Sports", "title": "Baseball"}},
        })
        source = KalshiMarketData(transport, clock=Clock())
        source.markets(status="open", limit=1000, mve_filter="exclude")
        self.assertEqual(transport.last["query"]["mve_filter"], "exclude")
        with self.assertRaises(DataError):
            source.markets(mve_filter="sometimes")
        self.assertEqual(source.series("kxmlbgame")["category"], "Sports")
        with self.assertRaises(DataError):
            source.series("../portfolio")


class HelperTests(unittest.TestCase):
    def test_an_instrument_names_its_series_or_its_product(self):
        self.assertEqual(instrument_target({"asset_class": "event", "symbol": "x", "market_id": "kxfed-26oct-h25"}), ("kalshi", "KXFED"))
        self.assertEqual(instrument_target({"asset_class": "crypto", "symbol": "SOL-USD"}), ("coinbase", "SOL-USD"))
        self.assertEqual(instrument_target({"asset_class": "crypto", "symbol": "SOL"}), ("coinbase", "SOL-USD"))
        self.assertIsNone(instrument_target({"asset_class": "equity", "symbol": "AAPL"}))
        self.assertIsNone(instrument_target("nope"))

    def test_the_reply_is_read_out_of_prose_and_fences(self):
        self.assertEqual(parse_reply('Here:\n```json\n{"decline": "no edge"}\n```'), {"decline": "no edge"})
        self.assertIsNone(parse_reply("no json at all"))
        self.assertIsNone(parse_reply("{broken"))


class CoverageTests(FoundingCase):
    def test_coverage_is_the_floor_by_family_with_what_it_actually_traded(self):
        fed = Instrument("event", "KXFED-26OCT-H25", "kalshi", market_id="KXFED-26OCT-H25", right="yes")
        self.fill("mullins", "buy", 5, "0.20", "2026-09-16T12:00:00.000Z", fed)
        self.log.append(
            "desk:hilibrand", "desk.intent",
            {"intent_id": "i1", "instrument": Instrument("crypto", "SOL-USD", "coinbase").to_dict(), "side": "buy",
             "quantity": "1", "order_type": "limit", "rationale": "r"},
            at="2026-09-16T12:00:00.000Z",
        )
        coverage = self.founding.coverage(NIGHT)
        self.assertEqual(sorted(coverage["families"]), ["crypto", "kalshi", "ranges", "weather"])
        kalshi = coverage["families"]["kalshi"]
        self.assertEqual(kalshi["founder"], "mullins")
        self.assertFalse(kalshi["founded"])
        self.assertEqual(kalshi["venues"], ["kalshi"])
        self.assertEqual(kalshi["asset_classes"], ["event"])
        self.assertEqual(kalshi["traded"], {"kalshi": [["KXFED", 1]]})
        self.assertEqual(kalshi["best_desk"], "mullins")
        self.assertIn("pnl_usd", kalshi)
        self.assertEqual(coverage["families"]["crypto"]["traded"], {"coinbase": [["SOL-USD", 1]]})
        self.assertEqual(coverage["covered"], {"kalshi": ["KXFED"], "coinbase": ["SOL-USD"]})

    def test_trades_older_than_the_window_do_not_count(self):
        fed = Instrument("event", "KXFED-26OCT-H25", "kalshi", market_id="KXFED-26OCT-H25")
        self.fill("mullins", "buy", 5, "0.20", "2026-07-01T12:00:00.000Z", fed)
        self.assertEqual(self.founding.coverage(NIGHT)["covered"]["kalshi"], [])


class UniverseTests(FoundingCase):
    def test_the_digest_groups_kalshi_by_category_and_series_and_ranks_coinbase_by_dollars(self):
        fed = Instrument("event", "KXFED-26OCT-H25", "kalshi", market_id="KXFED-26OCT-H25")
        self.fill("mullins", "buy", 5, "0.20", "2026-09-16T12:00:00.000Z", fed)
        universe = self.founding.universe(NIGHT, coverage=self.founding.coverage(NIGHT))
        body = universe["text"]
        self.assertIn("## Kalshi: 5 open markets in 4 series", body)
        self.assertIn("- Sports: 2 / 1 / 170.0k", body)
        self.assertIn("- KXNFLGAME, Sports: 2 mkts, 170.0k ct", body)
        lines = {line.split(",")[0]: line for line in body.splitlines() if line.startswith("- KX")}
        self.assertTrue(lines["- KXFED"].endswith("[floor: kalshi]"), "KXFED is Mullins' already")
        self.assertEqual(lines["- KXNFLGAME"], '- KXNFLGAME, Sports: 2 mkts, 170.0k ct, ~$85.5k, OI 290.0k. "KXNFLGAME series"')
        self.assertIn("KXOSCAR, uncategorized", body)  # a series the venue would not describe is still listed
        self.assertNotIn("KXMVE", body, "the combos are not a line of business")
        self.assertEqual(self.kalshi.market_calls[0]["mve_filter"], "exclude")
        self.assertIn("## Coinbase: 3 USD spot products online", body)
        self.assertLess(body.index("PEPE-USD"), body.index("BTC-USD"), "ranked by dollar volume, not coins")
        self.assertNotIn("USDC-USD", body)
        self.assertNotIn("ETH-EUR", body)
        self.assertNotIn("DEAD-USD", body)
        self.assertEqual(universe["kalshi_series"], ["KXFED", "KXHIGHNY", "KXNFLGAME", "KXOSCAR"])
        self.assertEqual(universe["series_category"]["KXNFLGAME"], "Sports")
        self.assertEqual(universe["coinbase_products"], ["BONK-USD", "BTC-USD", "PEPE-USD"])

    def test_a_big_venue_still_fits_in_the_digest(self):
        self.kalshi.markets_rows = [
            market(f"KXS{i:04d}LONGNAME-26SEP-{j}", f"KXS{i:04d}LONGNAME-26SEP", 1000 + i, 10, "0.5",
                   "A long market title that goes on and on about what it settles on")
            for i in range(500) for j in range(2)
        ]
        self.kalshi.categories = {f"KXS{i:04d}LONGNAME": f"Category {i % 30}" for i in range(500)}
        self.coinbase.rows = [product(f"C{i:03d}-USD", "1.2345", str(1000 + i)) for i in range(300)]
        universe = self.founding.universe(NIGHT)
        self.assertLessEqual(len(universe["text"]), 6000)
        self.assertIn("KXS0499LONGNAME", universe["text"], "the most traded series survives the trim")
        self.assertIn("C299-USD", universe["text"])
        self.assertEqual(len(universe["kalshi_series"]), 500, "validation still knows every series")
        self.assertEqual(len(self.kalshi.series_calls), 60, "categories are looked up for the top of the ranking only")
        self.assertEqual(self.kalshi.series_calls[0], "KXS0499LONGNAME")

    def test_the_index_the_floor_holds_is_the_fallback_when_the_sweep_reads_nothing(self):
        self.kalshi.fail = True
        founding = Founding(self.log, self.evolution, provider=self.provider, kalshi=self.kalshi,
                            market_rows=lambda: default_markets()[:1])
        universe = founding.universe(NIGHT)
        self.assertEqual(universe["kalshi_series"], ["KXNFLGAME"])
        self.assertIn("kalshi markets: RuntimeError", universe["errors"])
        self.kalshi.fail = False
        self.assertEqual(len(founding.universe(NIGHT)["kalshi_series"]), 4, "a sweep that reads wins over the index")

    def test_one_venue_down_leaves_the_other_and_both_down_leaves_nothing(self):
        self.kalshi.fail = True
        universe = self.founding.universe(NIGHT)
        self.assertNotIn("Kalshi", universe["text"])
        self.assertIn("Coinbase", universe["text"])
        self.assertIn("kalshi markets: RuntimeError", universe["errors"])
        self.coinbase.fail = True
        self.assertEqual(self.founding.universe(NIGHT)["text"], "")
        outcome = self.founding.run(NIGHT)
        self.assertEqual(outcome["status"], "skipped")
        self.assertEqual(self.provider.calls, [], "no digest, no model call, no founding")


class ValidationTests(FoundingCase):
    def validate(self, data, **kwargs):
        universe = self.founding.universe(NIGHT)
        return self.founding.validate(data, universe=universe, now=NIGHT, **kwargs)

    def refused(self, data, message):
        with self.assertRaises(FoundingError) as caught:
            self.validate(data)
        self.assertIn(message, str(caught.exception))

    def test_a_valid_proposal_is_normalized_into_a_shadow_founder(self):
        data = proposal()
        data["manifest"]["capital"] = {"usd": "100"}
        data["manifest"]["instruments"]["allow"] = ["KXNFLGAME"]
        out = self.validate(data)
        manifest = DeskManifest.from_dict(out["manifest"])
        self.assertEqual((manifest.id, manifest.family, manifest.generation, manifest.parent_id), ("leahy", "sports", 1, None))
        self.assertEqual((manifest.capital_mode, manifest.capital_usd), ("shadow", Decimal("100")))
        self.assertEqual(manifest.playbook, "playbooks/leahy.md")
        self.assertEqual(manifest.instruments.allow, (), "a Kalshi allow list would refuse every market ticker")
        self.assertIn("founded", manifest.tags)
        self.assertEqual(out["targets"], ["KXNFLGAME"])
        self.assertNotIn("<", out["rationale"])

    def test_a_coinbase_family_is_held_to_its_targets(self):
        manifest = json.loads((REPO / "ltcm" / "desks" / "hilibrand.json").read_text())
        manifest.update(id="mcentee", family="memes", capital={"mode": "shadow", "usd": "150"})
        # Hilibrand holds futures at a 60% position cap since Sept 17, 2026; a founded desk is
        # bound to the lab's limits and to a spot-only, long-only mandate.
        manifest["limits"] = {**manifest["limits"], "max_position_pct": "0.50", "max_order_notional_pct": "0.50"}
        manifest["instruments"] = {**manifest["instruments"], "asset_classes": ["crypto"], "allow_short": False}
        data = proposal(family="memes", id="mcentee", name="McEntee", targets=["pepe-usd", "BONK-USD"], manifest=manifest)
        out = self.validate(data)
        self.assertEqual(out["manifest"]["instruments"]["allow"], ["BONK-USD", "PEPE-USD"])
        self.assertEqual(out["venues"], ["coinbase"])

    def test_names_already_taken_are_refused(self):
        self.refused(proposal(id="mullins"), "already taken")
        self.refused(proposal(id="meriwether"), "already taken")  # the committee signs as Meriwether
        self.refused(proposal(family="weather"), "already exists")
        self.refused(proposal(id="mullins-9"), "lineage")
        parked = self.desks / "pending-alpaca"
        parked.mkdir()
        data = copy.deepcopy(SAMPLE)
        data.update(id="merton", family="earnings")
        (parked / "merton.json").write_text(json.dumps(data))
        self.refused(proposal(id="merton"), "already taken")
        self.refused(proposal(family="earnings"), "already exists")
        self.refused(proposal(id="Bad Id"), "lowercase slug")
        self.refused(proposal(id="a" * 30), "lowercase slug")

    def test_a_founded_desk_is_never_born_live(self):
        data = proposal()
        data["manifest"]["capital"] = {"mode": "live", "usd": "150"}
        self.refused(data, "born shadow")
        data["manifest"]["capital"] = {"mode": "shadow", "usd": "5000"}
        self.refused(data, "at most 150")

    def test_limits_outside_the_hard_bounds_are_refused(self):
        cases = [
            ({"max_position_pct": "0.9"}, "limits.max_position_pct must be between"),
            ({"max_orders_per_day": 5000}, "max_orders_per_day must be an integer between 1 and 480"),
            ({"max_daily_loss_pct": "0.5"}, "limits.max_daily_loss_pct"),
            ({"max_gross_pct": "2"}, "limits.max_gross_pct"),
            ({"max_limit_deviation_pct": "0.9"}, "limits.max_limit_deviation_pct"),
            ({"leverage": "3"}, "unknown limits"),
        ]
        for change, message in cases:
            with self.subTest(change=change):
                data = proposal()
                data["manifest"]["limits"].update(change)
                self.refused(data, message)

    def test_unknown_venues_and_tools_are_refused(self):
        data = proposal()
        data["manifest"]["venues"] = ["alpaca"]
        self.refused(data, "venues not open to the floor: alpaca")
        data = proposal()
        data["manifest"]["tools"] = data["manifest"]["tools"] + ["filing"]
        self.refused(data, "tools no founder carries: filing")
        data = proposal()
        data["manifest"]["tools"] = ["memo", "news"]
        self.refused(data, "needs propose_order")
        data = proposal()
        data["manifest"]["instruments"]["asset_classes"] = ["crypto"]
        self.refused(data, "must name the event asset class")
        data = proposal()
        data["manifest"]["instruments"]["allow_short"] = True
        self.refused(data, "may not short")

    def test_the_playbook_must_fit_and_state_a_thesis(self):
        self.refused(proposal(playbook_markdown=playbook("x" * 13_000)), "at most 12000 bytes")
        self.refused(proposal(playbook_markdown="   "), "non-empty")
        self.refused(proposal(playbook_markdown="# Leahy\n\nBuy low, sell high.\n"), "Edge thesis")

    def test_targets_must_be_listed_and_untouched_by_the_floor(self):
        self.refused(proposal(targets=["KXNOTLISTED"]), "not listed on kalshi tonight")
        kept = self.validate(proposal(targets=["KXNOTLISTED", "KXNFLGAME"]))
        self.assertEqual(kept["targets"], ["KXNFLGAME"], "a partly listed proposal trades what is listed")
        self.refused(proposal(targets=[]), "targets must list")
        fed = Instrument("event", "KXFED-26OCT-H25", "kalshi", market_id="KXFED-26OCT-H25")
        self.fill("mullins", "buy", 5, "0.20", "2026-09-16T12:00:00.000Z", fed)
        kept = self.validate(proposal(targets=["KXFED", "KXNFLGAME"]))
        self.assertEqual(kept["targets"], ["KXNFLGAME"], "overlapping targets are dropped, not the family")
        self.refused(proposal(targets=["KXFED"]), "the floor already trades KXFED")

    def test_the_cadence_and_the_model_are_bounded(self):
        data = proposal()
        data["manifest"]["cadence"]["sessions"] = ["10:00", "10:10"]
        self.refused(data, "at least 30 minutes apart")
        data = proposal()
        data["manifest"]["cadence"]["sessions"] = [f"{h:02d}:00" for h in range(24)] + ["00:30"]
        self.refused(data, "1 to 24 times")
        data = proposal()
        data["manifest"]["cadence"]["timezone"] = "Mars/Olympus"
        self.refused(data, "not a timezone")
        data = proposal()
        data["manifest"]["model"]["profile"] = "gpt-9"
        self.refused(data, "model.profile")
        data = proposal()
        data["manifest"]["model"]["max_turns"] = 150
        self.refused(data, "model.max_turns")
        data = proposal()
        data["manifest"]["budget"] = {"usd_per_day": "250"}
        self.refused(data, "budget.usd_per_day")


class FoundTests(FoundingCase):
    def test_a_valid_proposal_is_written_published_loaded_and_bred(self):
        validated = self.founding.validate(proposal(), universe=self.founding.universe(NIGHT), now=NIGHT)
        action = self.founding.found(validated, NIGHT)
        self.assertEqual(action["action"], "founded")
        self.assertTrue((self.desks / "leahy.json").exists())
        self.assertIn("## Edge thesis", (self.playbooks / "leahy.md").read_text())
        events = self.log.read(kind=FOUNDED_KIND)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.stream, "evolution")
        self.assertTrue(event.public)
        self.assertEqual(
            sorted(event.payload),
            ["as_of", "asset_classes", "desk_id", "family", "model", "name", "rationale", "universe", "venues"],
        )
        self.assertEqual(event.payload["model"], "moonshotai/Kimi-K3")
        self.assertEqual(event.payload["venues"], ["kalshi"])
        self.assertNotIn("<", canonical(event.payload))
        self.assertLess(len(canonical(event.payload).encode()), 4000)

        roster = {m.id: m for m in load_all(self.desks)}
        self.assertEqual(roster["leahy"].capital_mode, "shadow")
        self.assertIn("sports", self.evolution.families())
        self.assertEqual(self.founding.founded_families(), {"sports"})
        self.assertEqual({m.id for m in self.founding.human_founders()}, set(FOUNDERS))
        bred = self.evolution.seed(NIGHT)
        self.assertIn("leahy-2", {a["desk_id"] for a in bred}, "evolution breeds the new family like any other")

    def test_a_long_rationale_is_clipped_for_the_tape(self):
        validated = self.founding.validate(
            proposal(rationale="Why. " * 1000), universe=self.founding.universe(NIGHT), now=NIGHT
        )
        payload = self.founding.found(validated, NIGHT)
        self.assertLessEqual(len(payload["rationale"]), 1500)
        self.assertLess(len(canonical(self.log.read(kind=FOUNDED_KIND)[0].payload).encode()), 4000)

    def test_an_unvalidated_proposal_cannot_be_founded(self):
        data = proposal()
        data["manifest"]["capital"] = {"mode": "live", "usd": "150"}
        with self.assertRaises(FoundingError):
            self.founding.found({**data, "playbook": "x", "venues": [], "asset_classes": []}, NIGHT)
        self.assertFalse((self.desks / "leahy.json").exists())


class ProposeTests(FoundingCase):
    def test_one_call_to_the_configured_model_with_the_whole_packet(self):
        reply = self.founding.propose(NIGHT)
        self.assertEqual(len(self.provider.calls), 1)
        call = self.provider.calls[0]
        self.assertEqual(call["profile"], "k3")
        self.assertEqual(call["reasoning_effort"], "high")
        self.assertEqual(call["desk_id"], "founding")
        self.assertEqual(call["request_key"], "founding:2026-09-17")
        self.assertIsNone(call["tools"])
        system, user = call["items"][0]["content"], call["items"][1]["content"]
        self.assertIn("Edge thesis", system)
        self.assertIn("max_orders_per_day 1 to 480", system)
        self.assertIn("## Kalshi:", user)
        self.assertIn("## Names already taken", user)
        for desk_id in FOUNDERS:
            self.assertIn(f"({desk_id}, family", user)
        self.assertEqual(reply["proposal"]["family"], "sports")
        self.assertIsNone(reply["decline"])

    def test_a_night_runs_to_a_founding_once_and_the_cap_holds(self):
        outcome = self.founding.run(NIGHT)
        self.assertEqual(outcome["status"], "founded", outcome)
        self.assertEqual(outcome["desk_id"], "leahy")
        again = self.founding.run("2026-09-17T02:30:00.000Z", key="founding:again")
        self.assertEqual(again["status"], "skipped")
        self.assertIn("last 24 hours", again["reason"])
        self.assertEqual(len(self.provider.calls), 1)

    def test_the_founded_family_ceiling_holds(self):
        self.founding.run(NIGHT)
        founding = self.build(max_founded_families=1, max_per_day=5)
        self.assertEqual(founding.refusal("2026-09-17T03:00:00.000Z"), "the floor is at its founded-family ceiling")

    def test_a_decline_a_refusal_and_a_provider_error_found_nothing(self):
        self.provider.reply = {"decline": "Nothing listed has a testable edge tonight."}
        self.assertEqual(self.founding.run(NIGHT)["status"], "declined")
        self.provider.reply = proposal(targets=["KXNOPE"])
        refused = self.founding.run(NIGHT, key="k2")
        self.assertEqual(refused["status"], "refused")
        self.assertIn("not listed", refused["reason"])
        self.provider.error = RuntimeError("provider_poll_timeout")
        failed = self.founding.run(NIGHT, key="k3")
        self.assertEqual(failed["status"], "failed")
        self.assertIn("provider_poll_timeout", failed["reason"])
        self.provider.error, self.provider.reply = None, "I would rather not say."
        self.assertEqual(self.founding.run(NIGHT, key="k4")["status"], "refused")
        self.assertEqual(self.log.read(kind=FOUNDED_KIND), [])
        self.assertFalse((self.desks / "leahy.json").exists())

    def test_a_refused_proposal_gets_one_correction_with_the_reason(self):
        good = proposal()
        bad = proposal(id="meriwether")
        replies = [bad, good]

        def respond(profile, items, **kwargs):
            self.provider.calls.append({"profile": profile, "items": items, **kwargs})
            body = json.dumps(replies.pop(0))
            return SimpleNamespace(output_text=body, cost_usd=Decimal("0.20"), incomplete=False)

        self.provider.respond = respond
        outcome = self.founding.run(NIGHT)
        self.assertEqual(outcome["status"], "founded")
        self.assertEqual(len(self.provider.calls), 2)
        retry = self.provider.calls[1]
        self.assertTrue(retry["request_key"].endswith(":retry"))
        self.assertIn("meriwether is already taken", retry["items"][-1]["content"])
        self.assertEqual(retry["items"][-2]["role"], "assistant")

    def test_the_step_never_blocks_on_the_model(self):
        first = self.founding.step(NIGHT, day="2026-09-16")
        self.assertEqual(first, {"status": "pending"})
        self.founding.wait(5)
        done = self.founding.step(NIGHT, day="2026-09-16")
        self.assertEqual(done["status"], "founded")
        self.assertEqual(self.provider.calls[0]["request_key"], "founding:2026-09-16")


class WindDownTests(FoundingCase):
    FOUNDED_AT = "2026-09-10T01:30:00.000Z"
    LATER = "2026-09-16T01:30:00.000Z"

    def found(self, **overrides):
        validated = self.founding.validate(proposal(**overrides), universe=self.founding.universe(self.FOUNDED_AT), now=self.FOUNDED_AT)
        return self.founding.found(validated, self.FOUNDED_AT)

    def lose(self, desk_id, *, fills=21, price="0.50", exit_price="0.05", start="2026-09-10T02:00:00.000Z"):
        """Fund a desk and have it lose on every decision."""
        self.allocate({desk_id: "150"}, start)
        contract = Instrument("event", "KXNFLGAME-26SEP20KCBUF-KC", "kalshi", market_id="KXNFLGAME-26SEP20KCBUF-KC", right="yes")
        for i in range(fills - 1):
            self.fill(desk_id, "buy", 10, price, f"2026-09-11T0{i % 10}:00:00.000Z", contract)
        self.fill(desk_id, "sell", 10 * (fills - 1), exit_price, "2026-09-15T12:00:00.000Z", contract)

    def test_a_failing_founded_family_is_retired_whole(self):
        self.found()
        (self.desks / "leahy-2.json").write_text(
            json.dumps({**json.loads((self.desks / "leahy.json").read_text()), "id": "leahy-2", "generation": 2,
                        "parent_id": "leahy", "playbook": "playbooks/leahy-2.md"})
        )
        self.lose("leahy")
        preview = self.founding.wind_down(self.LATER, apply=False)
        self.assertEqual(sorted(a["desk_id"] for a in preview), ["leahy", "leahy-2"])
        self.assertEqual(self.log.read(kind="evolution.retired"), [], "a preview retires nothing")
        actions = self.founding.wind_down(self.LATER)
        self.assertEqual(sorted(a["desk_id"] for a in actions), ["leahy", "leahy-2"])
        self.assertTrue(all(a["reason"] == WIND_DOWN_REASON for a in actions))
        self.assertNotIn("sports", self.evolution.families())
        self.assertEqual(self.founding.wind_down(self.LATER), [], "idempotent")
        self.assertEqual(self.founding.active_founded(), set())

    def test_the_human_founders_are_never_wound_down(self):
        self.log.append(  # even a record that names a human family cannot make it founded
            "evolution", FOUNDED_KIND, {"desk_id": "haghani-x", "family": "weather"}, at=self.FOUNDED_AT,
        )
        self.lose("haghani")
        self.lose("mullins")
        self.assertEqual(self.founding.founded_families(), set())
        self.assertEqual(self.founding.wind_down(self.LATER), [])
        self.assertIn("weather", self.evolution.families())

    def test_a_young_a_live_or_a_passing_family_is_kept(self):
        self.found()
        self.lose("leahy")
        self.assertEqual(self.founding.wind_down("2026-09-12T01:30:00.000Z"), [], "too young to judge")
        self.log.append(
            "evolution", "evolution.promoted", {"desk_id": "leahy", "from": "shadow", "to": "live"},
            at="2026-09-15T13:00:00.000Z",
        )
        self.assertEqual(self.founding.wind_down(self.LATER), [], "a live desk keeps its family")

    def test_a_desk_above_the_bar_keeps_the_family(self):
        self.found()
        self.lose("leahy", exit_price="0.49")  # a small loss, about -1.3 percent: above -5
        self.assertEqual(self.founding.wind_down(self.LATER), [])
        founding = self.build(retire_below="0")
        self.assertEqual([a["desk_id"] for a in founding.wind_down(self.LATER)], ["leahy"])

    def test_a_family_that_never_decides_is_wound_down_after_idle_days(self):
        self.found()
        self.assertEqual(self.founding.wind_down("2026-09-16T01:30:00.000Z"), [], "six days: still waiting")
        self.assertEqual(self.build(idle_days=0).wind_down("2026-09-30T01:30:00.000Z"), [], "the rule can be off")
        actions = self.founding.wind_down("2026-09-21T01:30:00.000Z")
        self.assertEqual([a["desk_id"] for a in actions], ["leahy"])


class ScriptTests(FoundingCase):
    """`scripts/found_family.py`, driven with this case's fakes in place of the venues and Sail."""

    def main(self, *argv):
        import contextlib
        import importlib.util
        import io
        from unittest import mock

        spec = importlib.util.spec_from_file_location("found_family", REPO / "scripts" / "found_family.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out = io.StringIO()
        closing_log = SimpleNamespace(close=lambda: None)
        with mock.patch.object(module, "build", lambda root, with_provider: (self.founding, closing_log, {"timezone": "UTC"})), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = module.main(list(argv))
        return code, out.getvalue()

    def test_packet_dry_run_apply_and_wind_down(self):
        code, out = self.main("--packet")
        self.assertEqual((code, self.provider.calls), (0, []))
        self.assertIn("## Names already taken", out)
        code, out = self.main("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn('"status": "valid"', out)
        self.assertIn("## Edge thesis", out)
        self.assertTrue(self.provider.calls[0]["request_key"].endswith(":manual"))
        self.assertEqual(self.log.read(kind=FOUNDED_KIND), [])
        code, out = self.main("--apply")
        self.assertEqual(code, 0)
        self.assertIn('"status": "founded"', out)
        self.assertTrue((self.desks / "leahy.json").exists())
        code, out = self.main("--apply")
        self.assertEqual(code, 1, "the 24-hour cap holds for a manual run too")
        code, out = self.main("--wind-down")
        self.assertEqual(json.loads(out)["founded_families"], ["sports"])


# --------------------------------------------------------------------------- the service slot


class FoundingServiceTests(ServiceCase):
    """The slot: once a day after 21:30 New York, off the tick, and never fatal."""

    def reply(self):
        manifest = copy.deepcopy(SAMPLE)
        manifest.update(id="leahy", family="sports", venues=["kalshi"],
                        model={**SAMPLE["model"], "profile": "pro_asap"}, capital={"mode": "shadow", "usd": "150"},
                        instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": [], "min_price": "0",
                                     "min_adv_usd": "0"},
                        tools=["news", "memo", "memory_read", "memory_write", "propose_order", "playbook_read"])
        manifest["cadence"] = {"sessions": ["10:00", "16:00"], "timezone": "America/New_York", "weekdays_only": False}
        return json.dumps(proposal(manifest=manifest))

    def setUp(self):
        super().setUp()
        self.service.close()
        self.service = self.build(live_venues=["kalshi", "coinbase"])
        self.service.founding.kalshi = FakeKalshi()
        self.provider.reply = self.reply()

    def tearDown(self):
        if getattr(self.service, "founding", None) is not None:
            self.service.founding.wait(5)
        super().tearDown()

    def founding_calls(self):
        return [key for key in self.provider.calls if str(key).startswith("founding:")]

    def test_the_slot_founds_once_a_day_and_the_desk_loads_without_a_restart(self):
        self.tick(moment(2026, 9, 15, 1, 0))  # 21:00 New York: not yet
        self.assertIsNone(self.service.state().get("founding_pending_day"))
        self.assertEqual(self.founding_calls(), [])
        result = self.tick(moment(2026, 9, 15, 1, 35))  # 21:35: the slot; the worker thinks
        self.assertEqual(result["founding"], {"status": "pending"})
        self.assertEqual(self.service.state()["founding_pending_day"], "2026-09-14")
        self.service.founding.wait(5)
        result = self.tick(moment(2026, 9, 15, 1, 36))
        self.assertEqual(result["founding"]["status"], "founded", result["founding"])
        self.assertIn("leahy", self.service.manifests)
        self.assertEqual(self.service.manifests["leahy"].capital_mode, "shadow")
        self.assertIn("leahy", self.service.shadow_books)
        state = self.service.state()
        self.assertEqual(state["last_founding_day"], "2026-09-14")
        self.assertIsNone(state.get("founding_pending_day"))
        self.assertEqual(state["last_founding"]["desk_id"], "leahy")
        self.assertEqual(self.service.status()["last_founding"]["status"], "founded")
        self.assertEqual(self.founding_calls(), ["founding:2026-09-14"])
        self.tick(moment(2026, 9, 15, 2, 30))  # the same evening again: nothing more
        self.assertEqual(self.founding_calls(), ["founding:2026-09-14"])
        self.assertEqual(len(self.service.log.read(kind=FOUNDED_KIND)), 1)

    def test_a_provider_error_is_one_alert_and_the_night_is_over(self):
        def broken(profile, items, **kwargs):
            if str(kwargs.get("request_key", "")).startswith("founding:"):
                raise RuntimeError("provider_http_503")
            return SimpleNamespace(output_text="memo body", cost_usd=Decimal("0.01"))

        self.provider.respond = broken
        self.tick(moment(2026, 9, 15, 1, 35))
        self.service.founding.wait(5)
        result = self.tick(moment(2026, 9, 15, 1, 36))
        self.assertEqual(result["founding"]["status"], "failed")
        self.tick(moment(2026, 9, 15, 1, 40))
        alerts = [e for e in self.service.log.read(kind="ops.alert") if "founding" in e.payload["text"]]
        self.assertEqual(len(alerts), 1)
        self.assertIn("provider_http_503", alerts[0].payload["text"])
        self.assertEqual(self.service.state()["last_founding_day"], "2026-09-14")
        self.assertEqual(self.service.log.read(kind=FOUNDED_KIND), [])

    def test_no_listings_no_founding_and_no_noise(self):
        self.service.close()
        self.service = self.build(live_venues=["kalshi", "coinbase"])  # sources.event is off in this case
        self.assertIsNone(self.service.founding.kalshi_source())
        self.assertIsNone(self.service.founding.coinbase_source())
        result = self.tick(moment(2026, 9, 15, 1, 35))
        self.assertEqual(result["founding"]["status"], "skipped")
        self.assertEqual(self.founding_calls(), [])
        self.assertEqual([e for e in self.service.log.read(kind="ops.alert") if "founding" in e.payload["text"]], [])
        self.assertEqual(self.service.state()["last_founding_day"], "2026-09-14")

    def test_the_founder_desk_the_owner_wrote_is_not_touched_by_the_slot(self):
        self.tick(moment(2026, 9, 15, 1, 35))
        self.service.founding.wait(5)
        self.tick(moment(2026, 9, 15, 1, 36))
        self.assertIn(DESK, self.service.active_manifests())
        self.assertEqual(self.service.founding.founded_families(), {"sports"})


if __name__ == "__main__":
    unittest.main()
