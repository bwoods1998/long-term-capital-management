"""The weather-ensemble founders (K3 of the Kalshi-scale run, Sept 25, 2026): the seed priced on
recorded data, decided through `league.runner.decide` exactly as a box runs it, and its four founder
rows checked against the weather desk.

The fixtures under `fixtures/weather_ensemble/` are real answers: Open-Meteo's ensemble for KNYC
(the recorder's own query, parsed by `ltcm.data.openmeteo.ensemble_climate_days`, the parser the
House's `weather` feed uses), Kalshi's open KXHIGHNY and KXLOWTNYC markets of the same minute (made
into ctx rows by `KalshiMarketData.parse_market` and `KalshiData._live_row`, as a live wake does),
and the station calibration the seed's STATIONS table comes from. The NWS row is the recorded
forecast of `ltcm/tests/fixtures/feeds` through `Weather.issued`."""

import json
import math
import unittest
from datetime import datetime
from pathlib import Path

from league import feeds, niches, parameters, runner, seeds
from league.safety import check_code
from league.tapes import KalshiData
from league.tests.test_house import HouseCase
from league.tests.test_seeds import LIMITS, SeedCase
from ltcm.data import iso
from ltcm.data.kalshi import KalshiMarketData
from ltcm.data.openmeteo import ensemble_climate_days
from ltcm.data.weather import CITIES, POINTS_URL, Weather, city_for_series, standard_offset_hours
from ltcm.tests.fakes import Clock, FakeTransport

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "weather_ensemble"
FEEDS = HERE.parents[1] / "ltcm" / "tests" / "fixtures" / "feeds"
SEED = "weather-ensemble-east"
KEYS = ("weather-ensemble-east", "weather-ensemble-central", "weather-ensemble-texas", "weather-ensemble-west")
NOW = "2026-09-25T06:45:44Z"  # the minute the fixtures were fetched; before New York's 11:00Z high cutoff
DAY = "2026-09-25"


def recorded(name, folder=FIXTURES):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def seconds(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def module():
    """The seed's module namespace, for its pricing functions (the box runs only `decide`)."""
    namespace = {"__name__": "strategy"}
    exec(compile(seeds.load(SEED), "weather_ensemble.py", "exec"), namespace)  # noqa: S102 - our own seed, in a test
    return namespace


SEEDNS = module()
PARAMS = dict(SEEDNS["PARAMS"])


def raw_markets():
    return recorded("kalshi_knyc_open_20260925.json")["markets"]


def fixture_markets(now=NOW, hours=30.0):
    """The fixture's markets as a live wake shows them: two-sided rows closing within `hours`."""
    at = seconds(now)
    out = []
    for raw in raw_markets():
        row = KalshiData._live_row(KalshiMarketData.parse_market(raw), raw["event_ticker"].split("-")[0], at, at + hours * 3600)
        if row is not None:
            out.append(row[1])
    return out


def ensemble_row(runs_at=None):
    """The House's `weather` row for KNYC, built as `WeatherEnsemble.poll` builds it."""
    payload = recorded("openmeteo_ensemble_knyc_20260925.json")
    runs = {name: {"model": r["model"], "init": iso(r["last_run_initialisation_time"]), "available": iso(r["last_run_availability_time"]),
                   "modified": iso(r["last_run_modification_time"])} for name, r in payload["_runs"].items()}
    if runs_at is not None:
        runs = {name: {**r, "init": runs_at} for name, r in runs.items()}
    days = ensemble_climate_days(payload["hourly"], standard_offset_hours(CITIES["new york"]))
    return {"station": "KNYC", "city": "New York", "unit": "F", "precip_unit": "in", "runs": runs,
            "dates": {d["date"]: {k: d[k] for k in ("high", "low", "precip_in")} for d in days[:3]}, "t": "2026-09-25T06:40:02.000Z"}


def nws_row():
    """The House's `nws` row for KNYC from the recorded forecast (issued 2026-09-23T21:46:15Z)."""
    city = CITIES["new york"]
    routes = {POINTS_URL.format(lat=format(city.latitude, "f"), lon=format(city.longitude, "f")): recorded("nws_points_knyc.json", FEEDS),
              "https://api.weather.gov/gridpoints/OKX/34,45/forecast": recorded("nws_forecast_knyc.json", FEEDS),
              "https://api.weather.gov/gridpoints/OKX/34,45/forecast/hourly": recorded("nws_hourly_knyc.json", FEEDS)}
    answer = Weather(FakeTransport(routes), clock=Clock("2026-09-24T03:16:37Z")).issued(city)
    return {k: v for k, v in answer.items() if k != "source"}


def make_ctx(markets=None, weather=None, nws=None, params=None, now=NOW, positions=(), orders=(), cash=200.0, equity=200.0,
             limits=None, outcomes=None, memory=None, risk=None, feeds_absent=False):
    ctx = {"now": now, "venue": "kalshi", "rung": 1, "params": dict(params or {}), "memory": dict(memory or {}), "cash": cash,
           "equity": equity, "limits": dict(limits or LIMITS), "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07},
           "positions": list(positions), "open_orders": list(orders), "markets": fixture_markets(now) if markets is None else markets}
    if not feeds_absent:
        ctx["feeds"] = {"weather": {"KNYC": ensemble_row() if weather is None else weather}, **({"nws": {"KNYC": nws}} if nws else {})}
    if outcomes is not None:
        ctx["recent_order_outcomes"] = outcomes
    if risk is not None:
        ctx["event_risk"] = {"remaining_by_market_usd": risk}
    return ctx


def market(ticker, yes_bid, yes_ask, title, strike, hours=22.0, series=None):
    return {"market": ticker, "series": series or ticker.split("-")[0], "title": title, "yes_bid": yes_bid, "yes_ask": yes_ask,
            "close_time": "2026-09-26T05:00:00Z", "hours_to_close": hours, "hours_to_resolve": hours + 14.0,
            "volume_24h": 3000.0, "open_interest": 1000.0, "strike": strike}


def priced(p=None, row=None, nws=None, kind="high", day=DAY, now=NOW):
    return SEEDNS["model"]({**PARAMS, **(p or {})}, ensemble_row() if row is None else row, nws, day, kind, "KNYC",
                           SEEDNS["when"](now))


def fair_of(ticker, p=None, markets=None, nws=None):
    """The seed's fair YES for one fixture market, before and after the shrink toward the mid."""
    p = {**PARAMS, **(p or {})}
    rows = markets or fixture_markets()
    row = next(m for m in rows if m["market"] == ticker)
    info = SEEDNS["parse_market"](row, [m["strike"] for m in rows if "-B" in m["market"]])
    points, kernel, point, floor = priced(p, nws=nws, kind=info[1])
    model = SEEDNS["mass"](points, kernel, info[3], info[4])
    if point is not None:
        model = (1 - p["nws_weight"]) * model + p["nws_weight"] * SEEDNS["mass"]([point], floor, info[3], info[4])
    mid = (row["yes_bid"] + row["yes_ask"]) / 2
    return model, min(0.995, max(0.005, mid + p["model_weight"] * (model - mid)))


# --------------------------------------------------------------------------------------- pricing
class HowKalshiStrikesThem(unittest.TestCase):
    def test_every_fixture_market_parses_to_the_set_kalshis_strike_fields_name(self):
        """`greater` pays above floor_strike, `less` below cap_strike, `between` inside both, all on the
        whole-degree report: a report k covers the continuous reading [k - 0.5, k + 0.5)."""
        siblings = {}
        for raw in raw_markets():
            if "-B" in raw["ticker"]:
                siblings.setdefault(raw["event_ticker"], []).append(float(raw["ticker"].rsplit("B", 1)[1]))
        for raw in raw_markets():
            with self.subTest(raw["ticker"]):
                row = {"market": raw["ticker"], "title": raw["title"]}
                station, kind, day, low, high, tail = SEEDNS["parse_market"](row, siblings[raw["event_ticker"]])
                self.assertEqual((station, day), ("KNYC", DAY))
                self.assertEqual(kind, "high" if raw["ticker"].startswith("KXHIGH") else "low")
                if raw["strike_type"] == "greater":
                    self.assertEqual((low, high, tail), (raw["floor_strike"] + 0.5, None, True))
                elif raw["strike_type"] == "less":
                    self.assertEqual((low, high, tail), (None, raw["cap_strike"] - 0.5, True))
                else:
                    self.assertEqual((low, high, tail), (raw["floor_strike"] - 0.5, raw["cap_strike"] + 0.5, False))
                # and the rules say the same in words: "greater than 74", "less than 67", "between 73-74"
                self.assertIn({"greater": "greater than", "less": "less than", "between": "between"}[raw["strike_type"]], raw["rules_primary"])

    def test_a_threshold_without_a_title_is_read_from_its_brackets(self):
        parse = SEEDNS["parse_market"]
        brackets = [67.5, 69.5, 71.5, 73.5]
        self.assertEqual(parse({"market": "KXHIGHNY-26SEP25-T74"}, brackets)[3:], (74.5, None, True))
        self.assertEqual(parse({"market": "KXHIGHNY-26SEP25-T67"}, brackets)[3:], (None, 66.5, True))
        self.assertIsNone(parse({"market": "KXHIGHNY-26SEP25-T70"}, brackets), "inside the brackets and no title: not guessed")
        self.assertIsNone(parse({"market": "KXHIGHNY-26SEP25-T74"}, []))
        for junk in ("KXBTCD-26SEP2517-T80999.99", "KXHIGHXYZ-26SEP25-B70.5", "KXHIGHNY-26FOO25-B70.5", "KXHIGHNY-26FEB30-B70.5", "", None):
            self.assertIsNone(parse({"market": junk}, brackets), junk)
        self.assertEqual(parse({"market": "KXLOWTPHIL-26SEP25-B55.5", "title": "be 55-56°"}, [])[:3], ("KPHL", "low", DAY))
        self.assertEqual(parse({"market": "KXHIGHTSATX-26OCT01-B90.5"}, [])[:3], ("KSAT", "high", "2026-10-01"))

    def test_one_events_markets_partition_the_line(self):
        points, kernel, _, _ = priced()
        edges = [None, 66.5, 68.5, 70.5, 72.5, 74.5, None]  # T67 less, B67.5, B69.5, B71.5, B73.5, T74 greater
        total = sum(SEEDNS["mass"](points, kernel, edges[i] if i else None, edges[i + 1]) for i in range(6))
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_no_bracket_is_ever_zero_or_one(self):
        points, kernel, _, _ = priced()
        far = SEEDNS["mass"](points, kernel, 89.5, 91.5)
        self.assertTrue(0.0 < far < 1e-6, far)
        near = SEEDNS["mass"](points, kernel, None, 90.5)
        self.assertTrue(1 - 1e-6 < near < 1.0 or near == 1.0)
        _, fair = fair_of("KXHIGHNY-26SEP25-T67")
        self.assertTrue(0.005 <= fair <= 0.995)

    def test_the_station_bias_and_the_bias_knob_move_the_members(self):
        payload = ensemble_row()["dates"][DAY]["high"]["members"]
        mean = sum(payload) / len(payload)
        points, _, _, _ = priced()
        self.assertAlmostEqual(sum(points) / len(points), mean + SEEDNS["STATIONS"]["KNYC"][1], places=9)  # New York's highs: -1.0 F
        warmer, _, _, _ = priced({"bias_high_f": 2.0})
        self.assertAlmostEqual(sum(warmer) / len(warmer) - sum(points) / len(points), 2.0, places=9)
        low, _, _, _ = priced(kind="low")
        lows = ensemble_row()["dates"][DAY]["low"]["members"]
        self.assertAlmostEqual(sum(low) / len(low), sum(lows) / len(lows) + SEEDNS["STATIONS"]["KNYC"][3], places=9)
        base, _ = fair_of("KXHIGHNY-26SEP25-T67", {"model_weight": 1.0})      # under 67 F
        hot, _ = fair_of("KXHIGHNY-26SEP25-T67", {"model_weight": 1.0, "bias_high_f": 2.0})
        self.assertLess(hot, base - 0.03)

    def test_spread_and_kernel_widen_and_the_station_error_is_the_floor(self):
        points, kernel, _, floor = priced()
        wide, _, _, _ = priced({"spread_mult": 2.0})
        sd = lambda xs: math.sqrt(sum((x - sum(xs) / len(xs)) ** 2 for x in xs) / (len(xs) - 1))
        self.assertAlmostEqual(sd(wide) / sd(points), 2.0 / 1.1, places=6)
        self.assertEqual(floor, SEEDNS["STATIONS"]["KNYC"][2])
        self.assertGreaterEqual(kernel, PARAMS["kernel_f"])
        self.assertGreaterEqual(math.sqrt(sd(points) ** 2 + kernel ** 2), floor - 1e-9, "the predictive sd is never under the station's")
        tight = ensemble_row()
        tight["dates"][DAY]["high"] = {**tight["dates"][DAY]["high"], "members": [70.0] * 82}
        _, kernel, _, _ = priced(row=tight)
        self.assertAlmostEqual(kernel, 2.2, places=9)  # all members agree: the kernel is New York's measured 2.2 F

    def test_the_nws_forecast_of_the_climate_day_is_blended_in(self):
        nws = nws_row()
        stale = {"max_run_age_hours": 18.0}
        self.assertIsNone(priced(stale, nws=nws)[2], "issued 33 hours before NOW: stale")
        fresh = {"max_run_age_hours": 36.0}
        self.assertEqual(priced(fresh, nws=nws)[2], 68.0)                 # Friday's high
        self.assertEqual(priced(fresh, nws=nws, kind="low")[2], 55.0)     # Thursday night's low, ending Sept 25
        without, _ = fair_of("KXHIGHNY-26SEP25-B67.5", {**fresh, "model_weight": 1.0})
        blended, _ = fair_of("KXHIGHNY-26SEP25-B67.5", {**fresh, "model_weight": 1.0}, nws=nws)
        self.assertGreater(blended, without, "a 68 F NWS high adds weight to 67-68")

    def test_a_stale_missing_or_thin_ensemble_is_not_priced(self):
        self.assertEqual(priced(row=ensemble_row(runs_at="2026-09-24T06:00:00Z")), "a stale ensemble")
        self.assertEqual(priced(row={}), "a stale ensemble")
        self.assertEqual(priced(row=None if False else "x"), "no ensemble row")
        self.assertEqual(priced(day="2026-09-30"), "too few members")
        thin = ensemble_row()
        thin["dates"][DAY]["high"] = {"members": [70.0] * 5}
        self.assertEqual(priced(row=thin), "too few members")


# -------------------------------------------------------------------------------------- decisions
class Decisions(SeedCase):
    SEED = SEED

    def test_the_recorded_wake_rests_one_maker_bid_and_skips_the_lows_past_their_cutoff(self):
        out = self.run_seed(make_ctx())
        self.assertEqual(out["intents"], [{
            "market": "KXHIGHNY-26SEP25-B71.5", "leg": "no", "side": "buy", "quantity": 17, "type": "limit", "limit_price": 0.57,
            "post_only": True, "reason": out["intents"][0]["reason"]}])
        model, fair = fair_of("KXHIGHNY-26SEP25-B71.5")
        self.assertLess(model, 0.30)             # the ensemble: 71-72 F about one in four
        self.assertGreater(1 - fair - 0.57 - 0.0175 * 0.57 * 0.43, PARAMS["min_edge"])
        self.assertEqual(int(10.0 / (0.57 * (1 + 0.0175 * 0.43))), 17)
        self.assertIn("past the cutoff", out["thought"])  # New York's low of Sept 25: its cutoff was 04:00Z
        self.assertEqual(out["cancels"], [])
        self.assertEqual(out["memory"], {"taker_off_until": None})

    def test_a_low_is_priced_before_its_cutoff(self):
        out = self.run_seed(make_ctx(params={"cutoff_hour_low": 4}))
        self.assertEqual({i["market"].split("-")[0] for i in out["intents"]}, {"KXHIGHNY", "KXLOWTNYC"})
        low = next(i for i in out["intents"] if i["market"].startswith("KXLOWTNYC"))
        self.assertTrue(low["post_only"] and low["limit_price"] >= 0.30)

    def test_the_edge_clears_the_maker_fee_plus_min_edge_to_the_cent(self):
        p = {"model_weight": 1.0, "min_edge": 0.05}
        model, _ = fair_of("KXHIGHNY-26SEP25-B69.5", p)
        edge = lambda price: (1 - model) - price - 0.0175 * price * (1 - price)
        price = math.floor((1 - model - 0.05) * 100) / 100
        while edge(price) < 0.05:
            price = round(price - 0.01, 2)
        self.assertGreaterEqual(edge(price), 0.05)
        self.assertLess(edge(round(price + 0.01, 2)), 0.05)
        for no_price, wanted in ((price, True), (round(price + 0.01, 2), False)):
            yes_ask = round(1 - (no_price - 0.01), 2)  # the NO bid one tick under the price, bettered by one tick
            rows = [market("KXHIGHNY-26SEP25-B69.5", round(yes_ask - 0.05, 2), yes_ask, "be 69-70°", 69.5)]
            out = self.run_seed(make_ctx(markets=rows, params=p))
            with self.subTest(no_price=no_price):
                self.assertEqual([(i["leg"], i["limit_price"]) for i in out["intents"]], [("no", no_price)] if wanted else [])

    def test_a_taker_only_above_take_edge_after_the_taker_fee(self):
        p = {"model_weight": 1.0, "take_edge": 0.10}
        model, _ = fair_of("KXHIGHNY-26SEP25-B69.5", p)
        ask = math.floor((1 - model - 0.12) * 100) / 100   # NO asked well under its fair
        self.assertGreater((1 - model) - ask - 0.07 * ask * (1 - ask), 0.10)
        rows = [market("KXHIGHNY-26SEP25-B69.5", round(1 - ask, 2), round(1 - ask + 0.01, 2), "be 69-70°", 69.5)]
        out = self.run_seed(make_ctx(markets=rows, params=p))
        self.assertEqual(len(out["intents"]), 1)
        intent = out["intents"][0]
        self.assertEqual((intent["leg"], intent["limit_price"], intent["type"]), ("no", ask, "limit"))
        self.assertNotIn("post_only", intent)
        fee = math.ceil(100 * 0.07 * intent["quantity"] * ask * (1 - ask)) / 100
        self.assertLessEqual(intent["quantity"] * ask + fee, 10.0 + 1e-9)
        # The same edge under take_edge 0.25 rests a maker bid instead (inside the one-tick spread it joins the bid).
        out = self.run_seed(make_ctx(markets=rows, params={**p, "take_edge": 0.25}))
        self.assertEqual([(i["leg"], i.get("post_only"), i["limit_price"]) for i in out["intents"]], [("no", True, round(ask - 0.01, 2))])

    def test_after_a_real_book_liquidity_refusal_it_rests_instead_for_a_day(self):
        p = {"model_weight": 1.0, "take_edge": 0.10}
        model, _ = fair_of("KXHIGHNY-26SEP25-B69.5", p)
        ask = math.floor((1 - model - 0.12) * 100) / 100
        rows = [market("KXHIGHNY-26SEP25-B69.5", round(1 - ask, 2), round(1 - ask + 0.01, 2), "be 69-70°", 69.5)]
        refusal = {"status": "refused", "submitted_to_venue": False, "market": "KXHIGHNY-26SEP24-B70.5",
                   "reason": ("a real entry on weather-ensemble-east must be a post-only limit until the family's pooled taker record is "
                              "positive (no pooled taker record is measured for this agent's family): send a limit with post_only, which "
                              "rests or is refused (constitution allocator.real_entry_liquidity)")}
        out = self.run_seed(make_ctx(markets=rows, params=p, outcomes=[refusal]))
        self.assertEqual([i.get("post_only") for i in out["intents"]], [True])
        self.assertEqual(out["memory"], {"taker_off_until": "2026-09-26T06:45:44Z"})
        self.assertIn("takers off", out["thought"])
        later = make_ctx(markets=rows, params=p, memory=out["memory"], now="2026-09-25T09:00:00Z")
        self.assertEqual([i.get("post_only") for i in self.run_seed(later)["intents"]], [True], "remembered across wakes")
        other = dict(refusal, reason="the venue is shut")
        self.assertNotIn("post_only", self.run_seed(make_ctx(markets=rows, params=p, outcomes=[other, None, "x"]))["intents"][0])

    def test_one_market_per_event(self):
        rows = fixture_markets()
        out = self.run_seed(make_ctx(markets=rows, params={"model_weight": 1.0, "min_edge": 0.02, "min_edge_tail": 0.03}))
        events = ["-".join(i["market"].split("-")[:2]) for i in out["intents"]]
        self.assertEqual(events, ["KXHIGHNY-26SEP25"], "several markets clear the edge; one is taken")
        held = [{"market": "KXHIGHNY-26SEP25-B73.5", "leg": "no", "quantity": 3, "average_cost": 0.9, "mark": 0.9}]
        self.assertEqual(self.run_seed(make_ctx(markets=rows, positions=held))["intents"], [])
        resting = [{"order_id": "ord-9", "market": "KXHIGHNY-26SEP25-B71.5", "leg": "no", "side": "buy", "quantity": 5,
                    "limit_price": 0.57, "filled": 0.0, "submitted_at": "2026-09-25T06:30:00Z"}]
        out = self.run_seed(make_ctx(markets=rows, orders=resting))
        self.assertEqual((out["intents"], out["cancels"]), ([], []))

    def test_absent_or_stale_feeds_trade_nothing_and_never_crash(self):
        for label, ctx in (("no feeds", make_ctx(feeds_absent=True)), ("no weather", {**make_ctx(), "feeds": {"nws": {}}}),
                           ("feeds junk", {**make_ctx(), "feeds": ["x"]}), ("station absent", {**make_ctx(), "feeds": {"weather": {"KMIA": ensemble_row()}}}),
                           ("stale", make_ctx(weather=ensemble_row(runs_at="2026-09-24T10:00:00Z"))),
                           ("no members", make_ctx(weather={**ensemble_row(), "dates": {}}))):
            with self.subTest(label):
                out = self.run_seed(ctx)
                self.assertEqual(out["intents"], [])
                self.assertTrue(out["thought"])

    def test_resting_bids_are_cancelled_when_the_edge_goes_or_the_day_cannot_be_priced(self):
        def bid(order_id, ticker, leg, price, at="2026-09-25T06:30:00Z"):
            return {"order_id": order_id, "market": ticker, "leg": leg, "side": "buy", "quantity": 10, "limit_price": price,
                    "filled": 0.0, "submitted_at": at}
        keep = bid("ord-keep", "KXHIGHNY-26SEP25-B71.5", "no", 0.57)
        flipped = bid("ord-flip", "KXHIGHNY-26SEP25-B69.5", "yes", 0.33)       # the model puts 69-70 under a third
        outbid = bid("ord-old", "KXLOWTNYC-26SEP25-B55.5", "no", 0.30, at="2026-09-25T03:00:00Z")
        out = self.run_seed(make_ctx(orders=[keep, flipped]))
        self.assertEqual(out["cancels"], ["ord-flip"])
        self.assertEqual(out["intents"], [], "a cancel is not confirmed by asking: the event waits for the next wake")
        # Past New York's high cutoff (11:00Z) every resting bid of that day is cancelled; so is one on a stale ensemble.
        late = make_ctx(orders=[keep], now="2026-09-25T11:30:00Z")
        self.assertEqual(self.run_seed(late)["cancels"], ["ord-keep"])
        stale = make_ctx(orders=[keep], weather=ensemble_row(runs_at="2026-09-24T10:00:00Z"))
        self.assertEqual(self.run_seed(stale)["cancels"], ["ord-keep"])
        # Outbid and older than requote_minutes: cancelled, to be bid again at the new touch next wake.
        out = self.run_seed(make_ctx(orders=[outbid], params={"cutoff_hour_low": 4, "min_edge": 0.02}))
        self.assertEqual(out["cancels"], ["ord-old"])
        fresh = dict(outbid, submitted_at="2026-09-25T06:40:00Z")
        self.assertEqual(self.run_seed(make_ctx(orders=[fresh], params={"cutoff_hour_low": 4, "min_edge": 0.02}))["cancels"], [])

    def test_never_under_the_real_books_longshot_floor(self):
        # 69-70 F: the model's likeliest bracket, offered at 10 cents. The YES would be a huge edge, and costs under 30.
        rows = [market("KXHIGHNY-26SEP25-B69.5", 0.08, 0.10, "be 69-70°", 69.5)]
        model, _ = fair_of("KXHIGHNY-26SEP25-B69.5", {"model_weight": 1.0}, markets=rows)
        self.assertGreater(model, 0.20)
        for p in ({"model_weight": 1.0, "min_edge": 0.02}, {"model_weight": 1.0, "take_edge": 0.08}):
            self.assertEqual(self.run_seed(make_ctx(markets=rows, params=p))["intents"], [])
        out = self.run_seed(make_ctx(params={"model_weight": 1.0, "min_edge": 0.02, "min_edge_tail": 0.03}))
        self.assertTrue(out["intents"])
        for intent in out["intents"]:
            self.assertGreaterEqual(intent["limit_price"], 0.30)
        needs = runner.needs_of(seeds.load(SEED))["needs"]
        self.assertFalse(parameters.inspect({**PARAMS, "bid_min": 0.20}, needs)["valid"], "a mutation cannot go under 30 cents")

    def test_sizing_takes_the_tightest_of_ticket_cash_limits_event_and_event_risk(self):
        ticker = "KXHIGHNY-26SEP25-B71.5"
        cases = (({}, 17), ({"limits": {"max_order_usd": 3.0, "max_position_usd": 100.0}}, 5), ({"cash": 5.0}, 8),
                 ({"equity": 12.0}, 5), ({"risk": {ticker: 2.5}}, 4), ({"risk": {ticker: 0.4}}, None),
                 ({"params": {"notional_usd": 50.0}}, 87))
        for extra, wanted in cases:
            with self.subTest(extra):
                out = self.run_seed(make_ctx(**extra))
                got = [i["quantity"] for i in out["intents"] if i["market"] == ticker]
                self.assertEqual(got, [wanted] if wanted else [])

    def test_markets_paying_after_the_horizon_or_closing_now_are_skipped(self):
        rows = [dict(m, hours_to_resolve=48.5) for m in fixture_markets()]
        self.assertEqual(self.run_seed(make_ctx(markets=rows))["intents"], [])
        rows = [dict(m, hours_to_close=0.2) for m in fixture_markets()]
        self.assertEqual(self.run_seed(make_ctx(markets=rows))["intents"], [])

    def test_a_full_wake_is_fast(self):
        needs = runner.needs_of(seeds.load(SEED))["needs"]
        rows, weather = [], {}
        base = ensemble_row()
        for series in needs["series"]:
            kind = "high" if series.startswith("KXHIGH") else "low"
            center = 70 if kind == "high" else 55
            for b in range(center - 4, center + 5, 2):
                rows.append(market(f"{series}-26SEP25-B{b + 0.5}", 0.30, 0.33, f"be {b}-{b + 1}°", b + 0.5))
            rows.append(market(f"{series}-26SEP25-T{center + 5}", 0.04, 0.06, f">{center + 5}°", center + 5))
            rows.append(market(f"{series}-26SEP25-T{center - 4}", 0.04, 0.06, f"<{center - 4}°", center - 4))
        for station in needs["feeds"]["weather"]:
            weather[station] = base
        ctx = {**make_ctx(markets=rows, params={"cutoff_hour_low": 4}), "feeds": {"weather": weather, "nws": {"KNYC": nws_row()}}}
        out = self.run_seed(ctx)
        self.assertLess(out["seconds"], 1.0, "72 markets on six stations: far inside the box's 5 seconds")
        self.assertLessEqual(len(out["intents"]), PARAMS["max_new"])
        self.assertEqual(len({"-".join(i["market"].split("-")[:2]) for i in out["intents"]}), len(out["intents"]))

    def test_it_never_sells(self):
        held = [{"market": "KXHIGHNY-26SEP25-B71.5", "leg": "no", "quantity": 17, "average_cost": 0.57, "mark": 0.2}]
        out = self.run_seed(make_ctx(positions=held, now="2026-09-25T15:00:00Z"))
        self.assertEqual(self.sells(out), [])


# --------------------------------------------------------------------------------------- founders
class Founders(unittest.TestCase):
    def setUp(self):
        self.desk = niches.load()["kalshi-weather"]
        self.rows = [f for f in self.desk.founders if f["key"] in KEYS]

    def test_four_founders_seat_the_seed_across_the_desk_in_the_full_league(self):
        self.assertEqual([f["key"] for f in self.rows], list(KEYS))
        self.assertEqual(self.desk.max_members, 21)  # 17 before K3, one seat a founder
        by_name = {row["name"]: row for row in seeds.SEEDS}
        for founder in self.rows:
            with self.subTest(founder["key"]):
                self.assertIs(founder["seat_full_league"], True)
                self.assertEqual(founder["seed"], founder["key"])  # key == seed: the family is the seed row's own
                self.assertEqual(by_name[founder["seed"]]["family"], founder["key"])
                self.assertEqual(by_name[founder["seed"]]["file"], "weather_ensemble.py")
        self.assertEqual([row["name"] for row in seeds.SEEDS[-4:]], list(KEYS), "appended at the end of SEEDS")

    def test_each_founder_is_safe_valid_and_names_its_own_stations_highs_lows_and_feeds(self):
        stations = []
        for founder in self.rows:
            with self.subTest(founder["key"]):
                code = niches.founder_code(seeds.load(founder["seed"]), self.desk, founder)
                check_code(code)
                info = runner.needs_of(code)
                self.assertTrue(info["ok"], info)
                needs, params = info["needs"], info["params"]
                self.assertTrue(parameters.inspect(params, needs)["valid"], parameters.inspect(params, needs)["errors"])
                self.assertEqual(sorted(parameters.inspect(params, needs)["mutable"]), sorted(params), "every knob is bounded")
                self.assertEqual((needs["venue"], needs["horizon"], needs["style"]), ("kalshi", "day", "model-versus-market"))
                self.assertEqual(needs["series"], founder["needs"]["series"], "nothing cut: every series is on the desk")
                self.assertLessEqual(len(needs["series"]), niches.MAX_UNIVERSE)
                self.assertLessEqual(needs["max_hours_to_close"] + 14, 48, "a market closing within 30 h pays within 48 (settles ~14 h on)")
                self.assertTrue(20 <= needs["wake_minutes"] <= 30)
                self.assertEqual(feeds.requested(needs["feeds"]), needs["feeds"], "every feed key is recorded and kept")
                self.assertEqual(needs["feeds"]["weather"], needs["feeds"]["nws"])
                self.assertLessEqual(len(needs["feeds"]["weather"]), feeds.MAX_KEYS)
                named = [city_for_series(s).station for s in needs["series"]]
                self.assertEqual(list(dict.fromkeys(named)), needs["feeds"]["weather"], "the feeds are the series' own stations")
                for station in needs["feeds"]["weather"]:
                    kinds = {s[:6] for s in needs["series"] if city_for_series(s).station == station}
                    self.assertEqual(kinds, {"KXHIGH", "KXLOWT"}, station)
                self.assertTrue(set(needs["feeds"]["weather"]) <= set(runner.needs_of(code) and SEEDNS["STATIONS"]))
                stations += needs["feeds"]["weather"]
                self.assertEqual(code.split("def decide(ctx):", 1)[1], seeds.load(founder["seed"]).split("def decide(ctx):", 1)[1])
        self.assertEqual(len(stations), len(set(stations)), "the groups are disjoint")

    def test_the_founders_cover_every_station_whose_high_and_low_the_desk_lists(self):
        covered = {s for f in self.rows for s in f["needs"]["feeds"]["weather"]}
        highs = {city_for_series(s).station for s in self.desk.listed if s.startswith("KXHIGH")}
        lows = {city_for_series(s).station for s in self.desk.listed if s.startswith("KXLOW")}
        self.assertEqual(highs, lows)
        self.assertEqual(covered, highs)
        self.assertEqual(len(covered), 20)
        self.assertEqual(set(SEEDNS["STATIONS"]), covered)
        listed = {s for s in self.desk.listed if s.startswith(("KXHIGH", "KXLOW"))}
        self.assertEqual({s for f in self.rows for s in f["needs"]["series"]}, listed, "every high and low series the desk lists")
        self.assertEqual(feeds.weather_stations({"kalshi-weather": self.desk})[:3], ["KLAX", "KMIA", "KNYC"])

    def test_the_station_table_is_the_calibration_fixture(self):
        cal = recorded("station_calibration_20260924.json")["stations"]
        for station, (offset, hb, hs, lb, ls) in SEEDNS["STATIONS"].items():
            row = cal[station]
            with self.subTest(station):
                self.assertEqual(offset, row["utc_offset_standard"])
                self.assertEqual((hb, hs, lb, ls), (round(row["high"]["bias"], 1), round(row["high"]["sd"], 1),
                                                    round(row["low"]["bias"], 1) or 0.0, round(row["low"]["sd"], 1)))
                self.assertGreaterEqual(min(row["high"]["n"], row["low"]["n"]), 54)
                self.assertEqual(SEEDNS["CODES"][row["high"]["series"].replace("KXHIGHT", "KXHIGH").replace("KXHIGH", "")], station)
                self.assertEqual(city_for_series(row["low"]["series"]).station, station)

    def test_mutations_stay_valid(self):
        info = runner.needs_of(seeds.load(SEED))
        for trial in range(40):
            child = parameters.mutate(info["params"], seed=f"k3-{trial}", needs=info["needs"])
            self.assertTrue(parameters.inspect(child, info["needs"])["valid"])
            self.assertGreaterEqual(child["bid_min"], 0.30)


class InTheHouse(HouseCase):
    def test_the_house_gives_each_founder_its_own_family_on_the_weather_desk(self):
        rows = {r["key"]: r for r in self.house.founders() if r["key"] in KEYS}
        self.assertEqual({k: (r["family"], r["niche"], r["name"]) for k, r in rows.items()},
                         {k: (k, "kalshi-weather", "mullins") for k in KEYS})


if __name__ == "__main__":
    unittest.main()
