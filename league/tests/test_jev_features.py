"""J1, the move sensor (league/jev_features.py): the features ported from the analysis's reference,
the models' loading and refusal by definition, no back-fill, the lab's exact state and questions,
static labels once per market and a paced sample of states, point-in-time rows, rows when Jev is
unavailable, corrupt, stale and excess snapshots, shutdown, retention, and the held-out evaluation."""
import contextlib
import gzip
import io
import json
import math
import sqlite3
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from league.jev import MODEL, Sensor
from league.jev_features import (DEFINITIONS, FEATURES, HORIZONS, LAB_QUESTIONS, MODEL_PATH, PLACEHOLDER, RECORDED_ONLY,
                                 ROW_COLUMNS, SHADOW_PATH, MoveModel, MoveSensor, _draw, auc_with_interval, category,
                                 evaluate, features, logistic, main, numeric_spec, paired_auc, parse_time)
from league.ledger import canonical
from league.recordings import Recorder
from league.semantic_lab import QUESTION_GUARD, SemanticLab
from league.tests.fakes import Clock

SERVED, SHADOW = MoveModel.load(MODEL_PATH), MoveModel.load(SHADOW_PATH)
STATIC = ["continuous_threshold", "relative_return", "discrete_event", "ambiguous_settlement", "related_exposure",
          "missing_catalyst_context"]
ANSWERS = {"continuous_threshold": 0.9, "relative_return": 0.1, "discrete_event": 0.2, "ambiguous_settlement": 0.3,
           "related_exposure": 0.6, "missing_catalyst_context": 0.4}
NB = 1789962480
#: Computed by the analysis's pure-Python reference (move_model_reference.py, itself checked to 2e-16
#: against numpy on 100 lab states), Sept 25, 2026: the port must reproduce them.
GOLDEN = {
    "weather": ({"observed_minute": NB, "market": {"series": "KXHIGHNY", "yes_bid": 0.22, "yes_ask": 0.23, "open_interest": 2167.22,
                                                   "volume_24h": 2553.15, "hours_to_close": 25.1995, "hours_to_resolve": 39.1995},
                 "earlier_quotes": [{"observed": NB - 120, "bid": 0.22, "ask": 0.23}]},
                [{"observed": NB - 120, "bid": 0.22, "ask": 0.23}],
                {"log_oi": 0.5121107888950636, "hours": 0.5249895833333333, "lvol": 0.523031651084639, "lhrs": 0.49626491568459846,
                 "hres": 0.81665625, "nhist": 0.25, "tchg": 0.20030136065017937, "nochg": 1.0, "tight": 1.0, "cat_weather": 1.0},
                {5: 0.4455601346535518, 15: 0.5934218479924029, 60: 0.7162075830409101},
                {5: 0.31620593658983964, 15: 0.4624737240959367, 60: 0.6486334717116395},
                {5: 0.003685053045979657, 15: 0.01602335468624542, 60: 3.1035174448623146e-05}),
    "crypto": ({"observed_minute": NB, "market": {"series": "KXBTCD", "yes_bid": 0.40, "yes_ask": 0.44, "open_interest": 300,
                                                  "volume_24h": 50, "hours_to_close": 3.0, "hours_to_resolve": 3.0},
                "earlier_quotes": [{"observed": NB - 240, "bid": 0.30, "ask": 0.34}, {"observed": NB - 180, "bid": 0.36, "ask": 0.40},
                                   {"observed": NB - 120, "bid": 0.36, "ask": 0.40}, {"observed": NB - 60, "bid": 0.40, "ask": 0.44}]},
               [{"observed": NB - 7200, "bid": 0.2, "ask": 0.24}, {"observed": NB - 3600, "bid": 0.26, "ask": 0.30},
                {"observed": NB - 3000, "bid": 0.28, "ask": 0.32}, {"observed": NB - 240, "bid": 0.30, "ask": 0.34},
                {"observed": NB - 180, "bid": 0.36, "ask": 0.40}, {"observed": NB - 120, "bid": 0.36, "ask": 0.40},
                {"observed": NB - 60, "bid": 0.40, "ask": 0.44}],
               {"drift": 0.10000000000000003, "absdrift": 0.10000000000000003, "chg4": 0.5, "rng4": 0.10000000000000003,
                "tchg": 0.1263760881150453, "nochg": 0.0, "rng60": 0.14, "nhist": 1.0, "cat_crypto": 1.0, "log_oi": 0.380474017649925},
               {5: 0.9508967422673504, 15: 0.9651369196039095, 60: 0.9882091979612321},
               {5: 0.5196141153883616, 15: 0.48323699680361687, 60: 0.599254151589489},
               {5: 0.08218524551750479, 15: 0.24572926901701253, 60: 0.0011586199666837017}),
    "pinned": ({"observed_minute": NB, "market": {"series": "KXMLBTOTAL", "yes_bid": 0.005, "yes_ask": 0.015, "open_interest": None,
                                                  "hours_to_close": 900.0}, "earlier_quotes": []}, [],
               {"lhrs": 1.0338669414435235, "hres": 1.0, "log_oi": 0.0, "lvol": 0.0, "pinned": 1.0, "tight": 1.0, "ext": 0.98,
                "cat_sports": 1.0, "nochg": 1.0, "tchg": 0.0},
               {5: 0.010465839609961612, 15: 0.018366002747008236, 60: 0.008586445544512942},
               {5: 0.06741480787392516, 15: 0.2012013145125407, 60: 0.4742037303815024},
               {5: 5.1640068435741707e-05, 15: 0.00024850737988122627, 60: 1.454832136801421e-07}),
}


def quote(ago, mid, width=0.02):
    return {"observed": NB - ago, "bid": round(mid - width / 2, 6), "ask": round(mid + width / 2, 6)}


def bare(mid=0.42, width=0.02, earlier=()):
    return {"observed_minute": NB, "market": {"series": "KXBTCD", "yes_bid": mid - width / 2, "yes_ask": mid + width / 2,
                                              "hours_to_close": 5.0}, "earlier_quotes": list(earlier)}


class FeatureTest(unittest.TestCase):
    def test_the_port_reproduces_the_reference(self):
        for name, (state, history, some, served, baseline, shadow) in GOLDEN.items():
            with self.subTest(case=name):
                x = features(state, history)
                self.assertEqual(sorted(x), sorted(DEFINITIONS))
                for key, value in some.items():
                    self.assertAlmostEqual(x[key], value, places=12, msg=key)
                for h in HORIZONS:
                    self.assertAlmostEqual(SERVED.predict(x)[h], served[h], places=12)
                    self.assertAlmostEqual(SERVED.baseline_p(x)[h], baseline[h], places=12)
                    self.assertAlmostEqual(SHADOW.predict({**x, **ANSWERS})[h], shadow[h], places=12)
                self.assertIsNone(SHADOW.predict(x)[15], "no prediction without the static answers")

    def test_minutes_since_the_mid_last_changed(self):
        log240 = math.log1p(240)
        x = features(bare(), [])
        self.assertEqual((x["tchg"], x["nochg"], x["rng60"]), (0.0, 1.0, 0.0), "no history: no change seen, T = 0")
        x = features(bare(), [quote(60, 0.40)])
        self.assertEqual((x["tchg"], x["nochg"]), (0.0, 0.0), "it changed at the newest quote: T = 0")
        x = features(bare(), [quote(1200, 0.40), quote(600, 0.42)])
        self.assertAlmostEqual(x["tchg"], math.log1p(10) / log240)
        self.assertEqual(x["nochg"], 0.0)
        # No change inside the four-hour walk; the older, different quote is beyond it.
        x = features(bare(), [quote(20000, 0.30), quote(7200, 0.42)])
        self.assertAlmostEqual(x["tchg"], math.log1p(120) / log240)
        self.assertEqual(x["nochg"], 1.0)
        x = features(bare(), [quote(14400, 0.42), quote(600, 0.42)])
        self.assertAlmostEqual(x["tchg"], 1.0, msg="the oldest visited quote exactly 240 minutes back")
        self.assertEqual(features(bare(), [quote(20000, 0.42)])["tchg"], 0.0, "none visited: T = 0")
        self.assertEqual(features(bare(), [quote(-60, 0.10)])["nochg"], 1.0, "a quote at or after observed_minute is not history")

    def test_the_hour_range_and_the_state_quotes(self):
        x = features(bare(), [quote(3600, 0.30), quote(3660, 0.10)])
        self.assertAlmostEqual(x["rng60"], 0.12, msg="exactly an hour back counts; a minute more does not")
        earlier = [quote(240, 0.30), quote(180, 0.36), quote(120, 0.36), quote(60, 0.42), quote(0, 0.9)]
        x = features(bare(earlier=earlier), None)
        self.assertEqual(x["nhist"], 1.0, "the quote at observed_minute is dropped, four remain")
        self.assertAlmostEqual(x["drift"], 0.42 - 0.30, msg="drift is against the OLDEST of the last four")
        self.assertAlmostEqual(x["chg4"], 2 / 4)
        self.assertAlmostEqual(x["rng4"], 0.12)
        self.assertAlmostEqual(x["rng60"], 0.12, msg="history None: the earlier quotes stand in")
        self.assertEqual(features(bare(), [quote(60, 0.30)])["drift"], 0.0, "drift reads the state, not the history")

    def test_where_the_model_does_not_apply(self):
        self.assertIsNone(features({**bare(), "market": {"yes_bid": 0.5, "yes_ask": 0.4}}))
        self.assertIsNone(features({**bare(), "market": {"yes_bid": None, "yes_ask": 0.4}}))
        self.assertIsNone(features({**bare(), "market": {"yes_bid": 0.4, "yes_ask": 1.2}}))
        self.assertIsNone(features({**bare(), "market": {"yes_bid": 0.4, "yes_ask": 0.5, "hours_to_close": 0}}))
        self.assertIsNotNone(features({**bare(), "market": {"yes_bid": 0.4, "yes_ask": 0.5}}), "missing hours are 1")

    def test_categories(self):
        cases = {"KXBTCD": "crypto", "KXETH15M": "crypto", "KXHIGHNY": "weather", "KXLOWTNYC": "weather", "KXMLBTOTAL": "sports",
                 "KXVALORANTGAME": "sports", "KXEPLGAME": "sports", "KXWTI": "finance", "KXEURUSD": "finance",
                 "KXFEDDECISION": "finance", "KXTRUMPSAY": "other", "kxbtcd": "crypto", None: "other", "": "other"}
        self.assertEqual({s: category(s) for s in cases}, cases)
        x = features({**bare(), "market": {**bare()["market"], "series": "KXTRUMPSAY"}})
        self.assertEqual([x[f"cat_{c}"] for c in ("crypto", "weather", "sports", "finance", "other")], [0, 0, 0, 0, 1])


class ModelTest(unittest.TestCase):
    def test_the_shipped_models_load_and_define_features_as_the_registry_does(self):
        for path, questions in ((MODEL_PATH, []), (SHADOW_PATH, STATIC)):
            data = json.loads(path.read_text())
            model = MoveModel.load(path)
            self.assertEqual(model.problems, [], path.name)
            self.assertTrue(model.ready)
            self.assertEqual(model.per_market, questions)
            self.assertEqual({n["name"]: n["definition"] for n in data["numeric"]}, DEFINITIONS)
            self.assertEqual(data["fitted_on"]["to"], "2026-09-22T06:57:00Z")
        self.assertEqual(SERVED.version, "move-v1-20260924")
        self.assertEqual(SERVED.baseline[15]["features"], ["mid", "spread", "log_oi", "hours", "drift"])
        self.assertEqual(numeric_spec(["mid"]), [{"name": "mid", "definition": "(yes_bid+yes_ask)/2"}])

    def test_definitions_are_compared_ignoring_whitespace_and_case(self):
        data = json.loads(MODEL_PATH.read_text())
        for row in data["numeric"]:
            row["definition"] = "  " + row["definition"].upper().replace(" ", "\n  ")
        self.assertEqual(MoveModel(data).problems, [])

    def test_a_model_that_defines_a_feature_otherwise_is_refused(self):
        data = json.loads(MODEL_PATH.read_text())
        next(r for r in data["numeric"] if r["name"] == "drift")["definition"] = \
            "mid minus the mid of earlier_quotes[-1] (the newest prior minute bucket), 0 if none"
        model = MoveModel(data)
        self.assertIn("'drift'", model.problems[0])
        self.assertFalse(model.ready)
        self.assertIsNone(model.baseline, "every block would compute what it was not fitted on")
        self.assertEqual(model.predict({}), dict.fromkeys(HORIZONS))
        unknown = json.loads(MODEL_PATH.read_text())
        unknown["numeric"].append({"name": "velocity", "definition": "?"})
        self.assertIn("unknown feature 'velocity'", MoveModel(unknown).problems[0])
        undeclared = json.loads(MODEL_PATH.read_text())
        undeclared["numeric"] = [r for r in undeclared["numeric"] if r["name"] != "rng60"]
        model = MoveModel(undeclared)
        self.assertFalse(model.ready)
        self.assertIsNotNone(model.baseline, "the lab-5 baseline does not use rng60")
        recorded = json.loads(SHADOW_PATH.read_text())
        recorded["questions"]["per_state"] = ["moves_15m"]
        self.assertFalse(MoveModel(recorded).ready, "the recorded-only questions never enter a model")
        shape = json.loads(MODEL_PATH.read_text())
        shape["horizons"]["5"]["sd"][0] = 0
        self.assertFalse(MoveModel(shape).ready)
        placeholder = {**json.loads(MODEL_PATH.read_text()), "version": PLACEHOLDER}
        self.assertFalse(MoveModel(placeholder).ready)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.json").write_text("{")
            self.assertIn("unreadable", MoveModel.load(Path(tmp) / "bad.json").why_not)

    def test_a_model_is_its_version_and_digest_with_a_training_window(self):
        import hashlib
        self.assertEqual(SERVED.digest, hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest())
        self.assertEqual(SERVED.fitted_to, parse_time("2026-09-22T06:57:00Z"))
        self.assertEqual(len(SERVED.fit_events), 1059, "every event of the fit's rows")
        self.assertEqual(SERVED.fit_events, SHADOW.fit_events)
        for to in (None, "not a time"):
            data = json.loads(MODEL_PATH.read_text())
            data["fitted_on"].pop("to")
            if to is not None:
                data["fitted_on"]["to"] = to
            model = MoveModel(data)
            self.assertFalse(model.ready)
            self.assertIsNone(model.baseline)
            self.assertIn("fitted_on.to", model.why_not)

    def test_logistic_clips_and_needs_every_input(self):
        block = {"features": ["mid"], "mean": [0.0], "sd": [1.0], "weights": [0.0, 1000.0]}
        self.assertAlmostEqual(logistic(block, {"mid": 1.0}), 1 / (1 + math.exp(-30)))
        self.assertIsNone(logistic(block, {}))
        self.assertIsNone(logistic(block, {"mid": float("nan")}))


class FakeStateJev:
    """A gateway stand-in for lab-shaped states: answers every noul question with p (or p(name, state))."""

    def __init__(self, p=0.7, *, fail=False, cost="0.0001", on_call=None):
        self.p, self.fail, self.cost, self.calls, self.on_call, self.timeouts = p, fail, cost, [], on_call, []

    def __call__(self, ident, body, timeout=None):
        request = json.loads(body)
        self.calls.append((ident, request))
        self.timeouts.append(timeout)
        if self.on_call is not None:
            self.on_call()
        if self.fail:
            raise TimeoutError("gateway timed out")
        answers = {name: {"type": "noul", "noul": self.p(name, request["state"]) if callable(self.p) else self.p}
                   for name in request["questions"]}
        return {"model": MODEL, "answers": answers, "usage": {"input_tokens": 2400}}, Decimal(self.cost)


def market(ticker, bid=0.40, ask=0.44, *, title="Bitcoin above 60,000 at 5pm EDT?", oi=120.0, hours=3.0):
    return {"market": ticker, "series": ticker.split("-")[0], "title": title, "yes_bid": bid, "yes_ask": ask,
            "close_time": "2026-09-10T21:00:00Z", "hours_to_close": hours, "hours_to_resolve": hours, "volume_24h": 50.0,
            "open_interest": oi, "strike": 60000.0}


class MoveCase(unittest.TestCase):
    NO_SAMPLE = {"new_markets_per_day": 10 ** 9}  # the whole budget held for static labels: no state is sampled

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()  # 00:26:40 UTC
        self.recorder = Recorder(self.root / "recordings.sqlite", clock=self.clock)
        self.jev = FakeStateJev()
        self.alerts = []
        self.sensor = self.new_sensor(self.jev)

    def tearDown(self):
        self.recorder.close()
        self.dir.cleanup()

    def new_sensor(self, client, **kw):
        kw = {"daily_usd": "1.50", "daily_calls": 25000, "purpose_calls": {"move": 7500}, **kw}
        return Sensor(self.root / "jev.sqlite", client, clock=self.clock, **kw)

    def move(self, **settings):
        # min_free_bytes 0: the tests' temporary directory may be a small tmpfs (the guard has its own test).
        return MoveSensor(self.root, self.sensor, clock=self.clock, alert=lambda level, text: self.alerts.append(text),
                          settings={"interval_seconds": 300, "daily_usd": "0.75", "min_free_bytes": 0, **settings})

    def show(self, *markets, source="markets:KXBTCD:24"):
        return self.recorder.record(source, list(markets), started=self.clock())

    def rows(self, move):
        db = sqlite3.connect(move.path)
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM move_rows ORDER BY id")]
        finally:
            db.close()

    def started(self, move):
        """The first run: the cursor at the newest snapshot, nothing read."""
        move.run()
        self.clock.advance(300)


class RecorderTest(MoveCase):
    def test_first_run_sets_the_cursor_and_never_back_fills(self):
        self.show(market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000"))
        self.clock.advance(60)
        last = self.show(market("KXBTCD-26SEP10-T62000"))
        move = self.move()
        cycle = move.run()
        self.assertEqual(cycle["rows"], 0)
        self.assertIn("started", cycle["note"])
        self.assertEqual(move.stats()["cursor"], last)
        self.assertEqual(self.jev.calls, [])
        db = sqlite3.connect(move.path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM move_quotes").fetchone()[0], 0, "no quote from before the cursor")
        db.close()
        self.clock.advance(300)
        self.show(market("KXBTCD-26SEP10-T60000", 0.41, 0.45))
        self.assertEqual(move.run()["rows"], 1)
        self.assertEqual([(r["market"], r["snapshot"]) for r in self.rows(move)], [("KXBTCD-26SEP10-T60000", last + 1)])
        self.assertEqual(move.run()["rows"], 0, "a snapshot is read once")

    def test_every_market_gets_the_served_model_and_rows_match_it(self):
        move = self.move(**self.NO_SAMPLE)
        self.started(move)
        tickers = [f"KXBTCD-26SEP10-T6{n}000" for n in range(5)]
        self.show(*[market(t) for t in tickers])
        self.clock.advance(300)
        self.show(*[market(t, 0.30 + 0.02 * n, 0.34 + 0.02 * n) for n, t in enumerate(tickers)])
        move.run()
        rows = self.rows(move)
        self.assertEqual(len(rows), 5, "one row a market, from its latest snapshot")
        for row in rows:
            x = json.loads(row["numeric"])
            self.assertEqual(sorted(x), sorted(DEFINITIONS))
            self.assertAlmostEqual(row["move_p15"], logistic(SERVED.blocks[15], x), places=7)
            self.assertAlmostEqual(row["numeric_p60"], logistic(SERVED.baseline[60], x), places=7)
            self.assertAlmostEqual(row["jev_p5"], logistic(SHADOW.blocks[5], {**x, **json.loads(row["answers"])}), places=7)
            self.assertEqual((row["model_version"], row["shadow_version"]), (SERVED.version, SHADOW.version))
            self.assertIsNone(row["why"])
        second = [r for r in rows if r["market"] == tickers[1]][0]
        self.assertAlmostEqual(json.loads(second["numeric"])["rng60"], 0.08, places=6, msg="its own history, not only the state")
        self.assertTrue(all(r["lag_seconds"] == round(r["recorded_at"] - r["observed"], 3) for r in rows))
        self.assertEqual({r["model_digest"] for r in rows}, {SERVED.digest})
        # A market at its close: a row that says the model does not apply, and no Jev ask for it.
        calls = len(self.jev.calls)
        self.clock.advance(300)
        self.show(market("KXBTCD-26SEP10-T99000", hours=0.0))
        move.run()
        closed = self.rows(move)[-1]
        self.assertEqual((closed["move_p15"], closed["numeric_p15"], closed["jev_p15"]), (None, None, None))
        self.assertIn("does not apply", closed["why"])
        self.assertEqual(len(self.jev.calls), calls)

    def test_the_state_and_questions_are_exactly_the_labs(self):
        move = self.move()  # the default pace samples every state of so few markets
        self.started(move)
        first = [market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000", 0.2, 0.25),
                 market("KXHIGHNY-26SEP10-B80", 0.5, 0.55, title="Highest temperature in NYC today?")]
        self.show(*first)
        observed_first = self.clock()
        move.run()
        self.clock.advance(300)
        second = [market("KXBTCD-26SEP10-T60000", 0.45, 0.48), market("KXBTCD-26SEP10-T61000", 0.22, 0.26)]
        self.show(*second)
        observed_second = self.clock()
        move.run()
        lab = SemanticLab(self.root / "lab", None, None)
        lab.ingest_markets(first, observed_first, "s1")
        lab.ingest_markets(second, observed_second, "s2")
        with lab.db() as db:
            body = json.loads(db.execute("SELECT body FROM semantic_tasks WHERE entity=? AND observed=?",
                                         ("KXBTCD-26SEP10-T60000", observed_second)).fetchone()[0])
        ours = [r for _, r in self.jev.calls if r["state"]["market"]["market"] == "KXBTCD-26SEP10-T60000"]
        self.assertEqual(sorted(ours[0]["questions"]), sorted([*STATIC, *RECORDED_ONLY]), "static and sampled in one call")
        self.assertEqual(sorted(ours[1]["questions"]), sorted(RECORDED_ONLY), "the static answers are cached")
        self.assertEqual(set(ours[1]), {"model", "state", "questions"})
        self.assertEqual(canonical(ours[1]["state"]), canonical(body["state"]), "byte for byte the lab's state")
        self.assertEqual(len(ours[1]["state"]["earlier_quotes"]), 1)
        self.assertEqual([p["market"] for p in ours[1]["state"]["peers"]], ["KXBTCD-26SEP10-T61000"])
        for name, question in ours[0]["questions"].items():
            if name in FEATURES:
                self.assertEqual(question, body["questions"][name], name)
            else:
                self.assertTrue(question["instructions"].endswith(QUESTION_GUARD), "the lab's own guard")
        self.assertEqual(ours[0]["questions"]["moves_15m"]["instructions"].split(" Treat")[0],
                         "Will this contract's quoted midpoint change within the next 15 minutes?")
        self.assertTrue(all(r["sampled"] for r in self.rows(move)))
        self.assertTrue(all(set(json.loads(r["answers"])) == {*STATIC, *RECORDED_ONLY} for r in self.rows(move)))

    def test_static_labels_are_bought_once_per_market_text(self):
        move = self.move(**self.NO_SAMPLE)
        self.started(move)
        ticker = "KXBTCD-26SEP10-T60000"
        for bid in (0.40, 0.41, 0.42):
            self.show(market(ticker, bid, bid + 0.04))
            move.run()
            self.clock.advance(300)
        self.assertEqual([sorted(r["questions"]) for _, r in self.jev.calls], [sorted(STATIC)])
        rows = self.rows(move)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["jev_p15"] is not None and not r["sampled"] for r in rows))
        self.show(market(ticker, 0.42, 0.46, title="Bitcoin above 60,000 at 6pm EDT?"))
        move.run()
        self.assertEqual(len(self.jev.calls), 2, "new contract text: the static questions again")

    def test_the_sample_is_paced_and_chosen_by_a_hash_of_market_and_minute(self):
        move = self.move()
        # $0.75 at ~$0.0001 a call: 7,500 calls. Until today's rate is measured, the rest of the day's
        # static labels are reserved at 4,500 new markets a day: 4,417 for the 98% of the day left.
        # The other 3,083 go over the 283 cycles left after 00:26:40 UTC: 11 a cycle.
        self.assertEqual(move._allowance(self.clock(), 0), (400, 11, 7500))
        # Measured: 300 static asks in the 13,600 s watched since midnight is ~1,906 a day.
        self.clock.advance(12000)
        self.assertEqual(move._allowance(self.clock(), 300), (400, math.ceil((7500 - math.ceil(300 / 13600 * 72800)) / 243), 7500))
        # Never more than twice an even share: a late start with the whole budget left.
        self.clock.advance(86400 - 13600 - 600)
        self.assertEqual(move._allowance(self.clock(), 0)[1], math.ceil(2 * (7500 - 32) / 288))
        self.clock.advance(-(86400 - 600 - 1600))
        move = self.move(max_static_per_cycle=1, new_markets_per_day=7400)
        self.assertEqual(move._allowance(self.clock(), 0)[:2], (1, 1))
        self.started(move)
        tickers = [f"KXBTCD-26SEP10-T6{n}000" for n in range(4)]
        self.show(*[market(t) for t in tickers])
        move.run()
        rows = {r["market"]: r for r in self.rows(move)}
        sampled = [m for m, r in rows.items() if r["sampled"]]
        self.assertEqual(sampled, [min(tickers, key=lambda m: (_draw(m, rows[m]["minute"]), m))],
                         "one state, the smallest hash of (market, minute)")
        labelled = {tickers[0], *sampled}  # the one static ask this cycle allows, and the sample (with its static)
        self.assertEqual({m for m, r in rows.items() if r["jev_p15"] is not None}, labelled)
        self.assertTrue(all("paced" in r["why"] for r in rows.values() if r["jev_p15"] is None))
        self.assertTrue(all(r["move_p15"] is not None for r in rows.values()), "the served model needs no Jev")

    def test_rows_are_point_in_time_and_latest_never_sees_the_future(self):
        move = self.move(**self.NO_SAMPLE)
        self.started(move)
        ticker = "KXBTCD-26SEP10-T60000"
        self.show(market(ticker))
        observed_one = self.clock()
        self.clock.advance(20)
        move.run()
        one = self.rows(move)[0]
        self.assertGreaterEqual(one["recorded_at"], one["observed"])
        self.assertIsNone(move.latest(ticker, one["recorded_at"] - 0.001), "not before it was written")
        self.assertEqual(move.latest(ticker, one["recorded_at"]),
                         {"move_p5": one["move_p5"], "move_p15": one["move_p15"], "move_p60": one["move_p60"],
                          "model_version": SERVED.version, "age_seconds": round(one["recorded_at"] - observed_one, 3)})
        self.clock.advance(300)
        self.show(market(ticker, 0.30, 0.34))
        self.clock.advance(20)
        move.run()
        two = self.rows(move)[1]
        self.assertNotEqual(one["move_p15"], two["move_p15"])
        self.assertEqual(move.latest(ticker, two["recorded_at"] - 1)["move_p15"], one["move_p15"])
        self.assertEqual(move.latest(ticker, two["recorded_at"])["move_p15"], two["move_p15"])
        self.assertIsNone(move.latest("KXBTCD-OTHER", two["recorded_at"]))

    def test_rows_are_written_when_jev_is_unavailable_and_say_why(self):
        self.jev.fail = True
        move = self.move(workers=1, **self.NO_SAMPLE)
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000"))
        cycle = move.run()
        rows = self.rows(move)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(self.jev.calls), 1, "the move breaker stops the second call")
        for row in rows:
            self.assertIsNone(row["answers"])
            self.assertIsNone(row["jev_p15"])
            self.assertTrue(all(row[f"{kind}_p{h}"] is not None for kind in ("move", "numeric") for h in HORIZONS))
        self.assertEqual(sorted(r["why"] for r in rows), ["shadow: jev: Jev call failed (TimeoutError)",
                                                          "shadow: jev: Jev move breaker open after a failure"])
        self.assertTrue(cycle["refusal"].startswith("jev:"))
        self.assertEqual(self.sensor.refusal("gate"), "", "a move failure does not silence the research gate")

    def test_a_closing_house_or_a_spent_time_budget_starts_no_more_asks(self):
        closing = {"now": False}
        self.jev.on_call = lambda: closing.update(now=True)
        move = MoveSensor(self.root, self.sensor, clock=self.clock, closing=lambda: closing["now"],
                          settings={"workers": 1, "daily_usd": "0.75", "min_free_bytes": 0, **self.NO_SAMPLE})
        self.started(move)
        self.show(*[market(f"KXBTCD-26SEP10-T6{n}000") for n in range(4)])
        move.run()
        rows = self.rows(move)
        self.assertEqual(len(self.jev.calls), 1, "no ask starts after the House begins to close")
        self.assertLessEqual(self.jev.timeouts[0], 60, "an ask waits at most what the cycle has left")
        self.assertEqual(len(rows), 4, "the rows are still written, numeric")
        self.assertEqual(sum("the House is closing" in (r["why"] or "") for r in rows), 3)
        self.jev.on_call = None
        spent = self.move(max_seconds_per_cycle=0, **self.NO_SAMPLE)
        self.clock.advance(300)
        self.show(market("KXBTCD-26SEP10-T70000"))
        spent.run()
        self.assertEqual(len(self.jev.calls), 1)
        self.assertIn("time budget", self.rows(spent)[-1]["why"])
        self.assertEqual(MoveSensor(self.root, self.sensor, clock=self.clock, settings={"workers": 16}).workers, 4)

    def test_more_markets_than_a_cycle_takes_go_round(self):
        move = self.move(max_markets_per_cycle=2, **self.NO_SAMPLE)
        self.started(move)
        tickers = [f"KXBTCD-26SEP10-T6{n}000" for n in range(5)]
        for _ in range(3):
            self.show(*[market(t) for t in tickers])
            self.assertEqual(move.run()["rows"], 2)
            self.clock.advance(300)
        self.assertEqual({r["market"] for r in self.rows(move)}, set(tickers))

    def test_every_snapshot_gives_quotes_but_only_fresh_ones_make_rows(self):
        move = self.move(max_snapshots_per_cycle=3, **self.NO_SAMPLE)
        self.started(move)
        db = sqlite3.connect(self.root / "recordings.sqlite")
        bad = [b"not gzip", b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + b"garbage!" * 4,  # a gzip header, then zlib.error
               gzip.compress(b"[" * 200000 + b"]" * 200000)]  # RecursionError
        for payload in bad:
            db.execute("INSERT INTO snapshots(source,started,received,digest,payload) VALUES('markets:X',0,?,'d',?)",
                       (self.clock(), payload))
        db.execute("INSERT INTO snapshots(source,started,received,digest,payload) VALUES('markets:Y',0,?,'d',?)",
                   (self.clock() - 601, gzip.compress(json.dumps([market("KXBTCD-26SEP10-T10000")]).encode())))  # stale
        db.commit()
        db.close()
        self.show(market("KXBTCD-26SEP10-T60000"))
        last = self.show(market("KXBTCD-26SEP10-T61000"), {"market": "bad", "yes_bid": 0.9, "yes_ask": 0.1}, "junk")
        cycle = move.run()
        self.assertEqual((cycle["corrupt_snapshots"], cycle["backlog_snapshots"], cycle["rows"]), (3, 3, 0),
                         "the oldest three first: all corrupt; the rest wait for the next cycle")
        self.assertEqual(move.stats()["cursor"], last - 3)
        cycle = move.run()
        self.assertEqual((cycle["stale_snapshots"], cycle["backlog_snapshots"], cycle["rows"]), (1, 0, 2))
        self.assertEqual({r["market"] for r in self.rows(move)}, {"KXBTCD-26SEP10-T60000", "KXBTCD-26SEP10-T61000"})
        db = sqlite3.connect(move.path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM move_quotes WHERE market='KXBTCD-26SEP10-T10000'").fetchone()[0], 1,
                         "a stale snapshot still gives its quotes: the history keeps the lab's cadence")
        db.close()
        self.assertEqual(move.stats()["cursor"], last, "the cursor moves past everything considered")
        # A replaced recordings store starts again at its newest snapshot.
        self.recorder.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.root / "recordings.sqlite") + suffix).unlink(missing_ok=True)
        self.recorder = Recorder(self.root / "recordings.sqlite", clock=self.clock)
        self.show(market("KXBTCD-26SEP10-T62000"))
        self.assertIn("recordings replaced", move.run()["note"])
        self.show(market("KXBTCD-26SEP10-T63000"))
        self.assertEqual(move.run()["rows"], 1)
        # A failing cycle is one alert and None; the same failure again is not a second alert.
        move._observe = lambda *a: 1 / 0
        self.show(market("KXBTCD-26SEP10-T64000"))
        self.assertIsNone(move.run())
        self.show(market("KXBTCD-26SEP10-T65000"))
        self.assertIsNone(move.run())
        self.assertEqual(len([a for a in self.alerts if "cycle failed" in a]), 1)
        self.assertIn("ZeroDivisionError", move.stats()["refusal"])

    def test_a_short_disk_skips_the_cycle_with_one_alert(self):
        move = self.move(min_free_bytes=2 * 1024 ** 3)
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"))
        cursor = move.stats()["cursor"]
        with patch("league.jev_features.shutil.disk_usage", return_value=type("U", (), {"free": 1024 ** 3})()):
            self.assertIn("1.0 GB free", move.run()["refusal"])
            move.run()
        self.assertEqual(len([a for a in self.alerts if "GB free" in a]), 1)
        self.assertEqual((self.rows(move), move.stats()["cursor"]), ([], cursor))

    def test_retention_prunes_quotes_rows_answers_and_old_calls(self):
        move = self.move(retention_days=1)
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"))
        move.run()
        self.assertEqual(len(self.rows(move)), 1)
        self.clock.advance(2 * 86400)
        pruned = move.prune()
        self.assertEqual((pruned["rows"], pruned["quotes"], pruned["markets"]), (1, 1, 1))
        self.assertEqual(pruned["answers"], 8, "two sampled per-state answers after a day, six static after the retention")
        self.assertEqual(pruned["calls"], 0, "calls are kept 35 days")
        self.clock.advance(40 * 86400)
        self.assertEqual(move.prune()["calls"], 1)
        self.assertEqual(self.sensor.stats()["calls_lifetime"], 1, "the day totals outlive the pruned calls")

    def test_stats_for_health(self):
        move = self.move()
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000"))
        move.run()
        stats = move.stats()
        self.assertEqual((stats["rows"], stats["markets"], stats["labels_bought_today"]), (2, 2, 16))
        self.assertEqual((stats["model_version"], stats["shadow_version"]), (SERVED.version, SHADOW.version))
        self.assertTrue(stats["model_ready"] and stats["shadow_ready"])
        self.assertEqual({k: stats["today"][k] for k in ("calls", "cost_usd", "rows", "move_rows", "jev_rows", "sampled_rows")},
                         {"calls": 2, "cost_usd": "0.0002", "rows": 2, "move_rows": 2, "jev_rows": 2, "sampled_rows": 2})
        self.assertEqual(stats["daily_usd"], "0.75")
        self.assertIsNotNone(stats["last_cycle_at"])
        self.assertEqual(stats["last_cycle"]["markets_shown"], 2)
        self.assertIn("labels only", stats["authority"])

    def test_a_changed_model_under_a_known_version_is_refused(self):
        move = self.move(**self.NO_SAMPLE)
        self.started(move)
        data = json.loads(MODEL_PATH.read_text())
        data["horizons"]["15"]["weights"][0] += 0.5  # the same version, other contents
        (self.root / "changed.json").write_text(json.dumps(data, indent=1))
        changed = self.move(model_path=str(self.root / "changed.json"), **self.NO_SAMPLE)
        self.assertFalse(changed.served.ready)
        self.assertTrue(any("was recorded as" in a for a in self.alerts))
        self.assertTrue(any("is not ready" in a for a in self.alerts))
        self.show(market("KXBTCD-26SEP10-T60000"))
        changed.run()
        row = self.rows(changed)[0]
        self.assertEqual((row["move_p15"], row["numeric_p15"]), (None, None))
        self.assertIn("a changed model needs a new version", row["why"])
        self.assertIsNotNone(row["jev_p15"], "the shadow is its own identity")
        db = sqlite3.connect(move.path)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM move_models WHERE version=?", (SERVED.version,)).fetchone()[0], 1)
        db.close()

    def test_due_follows_the_interval(self):
        move = self.move()
        self.assertTrue(move.due())
        move.run()
        self.assertFalse(move.due())
        self.clock.advance(299)
        self.assertFalse(move.due())
        self.clock.advance(1)
        self.assertTrue(move.due())


class EvaluateTest(unittest.TestCase):
    """A synthetic store whose AUCs are known. Served move_p15 scores positives 0.9, 0.8, 0.3 and
    negatives 0.7, 0.2, 0.1 (8 of 9 pairs ordered); numeric_p is its mirror (1 of 9). The served
    model's fit includes the event KXBTCD-26SEP27; KXBTCD-26SEP26 was observed before the cutoff."""

    def setUp(self):
        import hashlib
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        data = json.loads(MODEL_PATH.read_text())
        data["version"] = "move-test-1"
        data["fitted_on"]["events_sha256"] = [hashlib.sha256(b"KXBTCD-26SEP27").hexdigest()[:16]]
        (self.root / "model.json").write_text(json.dumps(data))
        self.model = MoveModel.load(self.root / "model.json")
        # Registers both models' identities and fitted_on, as the recorder does.
        self.path = MoveSensor(self.root, None, clock=self.clock, model_path=self.root / "model.json").path
        self.cutoff = parse_time("2026-09-26T00:00:00Z")
        db = sqlite3.connect(self.path)
        rows = [  # (market, offset, move_p, moves, jev_p, moves_15m, lag)
            ("KXBTCD-26SEP26-T1", 0, 0.9, 1, 0.6, 0.9, 30), ("KXBTCD-26SEP26-T2", 60, 0.7, 0, 0.8, 0.1, 30),
            ("KXBTCD-26SEP27-T1", 120, 0.8, 1, 0.7, 0.8, 30), ("KXHIGHNY-26SEP26-B80", 180, 0.2, 0, 0.2, None, 30),
            ("KXHIGHNY-26SEP26-B81", 240, 0.3, 1, None, None, 30), ("KXHIGHNY-26SEP27-B80", 300, 0.1, 0, None, None, 200),
        ]
        for n, (ticker, offset, score, moves, jev, answer, lag) in enumerate(rows):
            self.insert(db, n, ticker, self.cutoff + offset, score, jev, answer, moves, lag=lag)
        self.insert(db, 90, "KXBTCD-26SEP26-T9", self.cutoff - 3600, 0.99, None, None, 0)  # before the cutoff
        self.insert(db, 91, "KXBTCD-26SEP28-T1", self.cutoff + 30, 0.05, None, None, 1, lag=2000)  # read after its outcome
        # The same version with other contents: its own group, never pooled.
        self.insert(db, 92, "KXETHD-26SEP26-T1", self.cutoff, 0.6, None, None, 1, digest="0" * 64)
        self.insert(db, 93, "KXETHD-26SEP26-T2", self.cutoff + 60, 0.4, None, None, 0, digest="0" * 64)
        db.commit()
        db.close()
        self.key = f"move-test-1@{self.model.digest[:12]} / {SHADOW.version}@{SHADOW.digest[:12]}"

    def tearDown(self):
        self.dir.cleanup()

    def insert(self, db, n, ticker, observed, score, jev, answer, moves, *, lag=30, digest=None):
        row = dict.fromkeys(ROW_COLUMNS)
        row.update(market=ticker, event=ticker.rsplit("-", 1)[0], series=ticker.split("-")[0], observed=observed,
                   minute=int(observed // 60) * 60, bid=0.40, ask=0.44, numeric="{}", model_version="move-test-1",
                   model_digest=digest or self.model.digest, shadow_version=SHADOW.version, shadow_digest=SHADOW.digest,
                   sampled=int(answer is not None), snapshot=n,
                   answers=json.dumps({"moves_15m": answer}) if answer is not None else None,
                   move_p15=score, numeric_p15=1 - score, jev_p15=jev)
        db.execute(f"INSERT INTO move_rows({','.join(ROW_COLUMNS)},recorded_at,lag_seconds) "
                   f"VALUES({','.join('?' * (len(ROW_COLUMNS) + 2))})", (*row.values(), observed + lag, lag))
        db.execute("INSERT OR IGNORE INTO move_quotes VALUES(?,?,?,?)",
                   (ticker, int(observed // 60) * 60 + 960, 0.40 + 0.02 * moves, 0.44))

    def test_known_aucs_per_model_identity_population_and_pairing(self):
        report = evaluate(self.path, self.cutoff, (15,), reps=100)
        self.assertEqual(report["rows_after_cutoff"], 9)
        self.assertEqual(len(report["models"]), 2, "one group per (version, digest)")
        entry = report["models"][self.key]
        self.assertEqual(entry["served"]["fitted_on"]["to"], "2026-09-22T06:57:00Z")
        self.assertEqual(entry["served"]["fitted_on"]["events"], 1)
        self.assertEqual(entry["lag_seconds"], {"p50": 30.0, "p90": 920.0, "p99": 1892.0, "max": 2000.0, "share_le_120s": 0.7143})
        overall = entry["populations"]["all_after_cutoff"]["15"]["overall"]
        self.assertEqual((overall["rows"], overall["events"], overall["base_rate"]), (6, 4, 0.5))
        self.assertEqual(overall["served"]["auc"], round(8 / 9, 4))
        self.assertEqual(overall["baseline"]["auc"], round(1 / 9, 4))
        self.assertEqual(overall["served_vs_baseline"]["difference"]["diff"], round(7 / 9, 4))
        # The Jev increment on the four rows with a jev_p: shadow 2 of 4 pairs, served 4 of 4.
        increment = overall["jev_increment"]
        self.assertEqual((increment["rows"], increment["shadow"]["auc"], increment["served"]["auc"]), (4, 0.5, 1.0))
        self.assertEqual((increment["difference"]["of"], increment["difference"]["diff"]), ("shadow - served", -0.5))
        low, high = increment["difference"]["ci95"]
        self.assertLessEqual(low, -0.5)
        self.assertGreaterEqual(high, -0.5)
        self.assertEqual(overall["recorded_only"]["moves_15m"]["alone"]["auc"], 1.0)
        self.assertEqual(overall["recorded_only"]["moves_15m"]["vs_served"]["rows"], 3)
        self.assertTrue(overall["meets_ship_rule"])
        # Unseen: not KXBTCD-26SEP26 (seen before the cutoff), not KXBTCD-26SEP27 (in the fit).
        unseen = entry["populations"]["unseen_events"]["15"]["overall"]
        self.assertEqual((unseen["rows"], unseen["events"], unseen["served"]["auc"]), (3, 2, 1.0))
        fresh = entry["populations"]["lag_le_120s"]["15"]["overall"]
        self.assertEqual((fresh["rows"], fresh["served"]["auc"]), (5, round(5 / 6, 4)))
        self.assertEqual(sorted(entry["populations"]["all_after_cutoff"]["15"]["by_category"]), ["crypto", "weather"])
        other = report["models"][f"move-test-1@{'0' * 12} / {SHADOW.version}@{SHADOW.digest[:12]}"]
        self.assertIsNone(other["served"]["fitted_on"])
        self.assertEqual(other["populations"]["all_after_cutoff"]["15"]["overall"]["served"]["auc"], 1.0)
        self.assertEqual(evaluate(self.path, self.cutoff, (15,), reps=100), report, "seeded: the same intervals twice")

    def test_a_cutoff_inside_the_training_window_is_refused(self):
        with self.assertRaisesRegex(ValueError, "fitted_on.to"):
            evaluate(self.path, parse_time("2026-09-22T00:00:00Z"), (15,))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["evaluate", "--store", str(self.path), "--cutoff", "2026-09-22T00:00:00Z"]), 2)
        self.assertIn("refused", err.getvalue())

    def test_the_cli_reads_the_store_without_writing(self):
        before = self.path.read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["evaluate", "--store", str(self.path), "--cutoff", "2026-09-26T00:00:00Z", "--json",
                                   "--reps", "20", "--horizons", "15"]), 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["models"][self.key]["populations"]["all_after_cutoff"]["15"]["overall"]["served"]["auc"],
                         round(8 / 9, 4))
        self.assertEqual(self.path.read_bytes(), before)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["evaluate", "--store", str(self.path), "--cutoff", str(self.cutoff), "--horizons", "15", "--reps", "0"])
        self.assertIn("served=0.889", out.getvalue())
        self.assertIn("jev increment=-0.500", out.getvalue())

    def test_intervals_resample_whole_events(self):
        # Two events of ten identical rows: resampling events loses one in half the draws.
        scores, labels, events = [0.9] * 10 + [0.1] * 10, [1] * 10 + [0] * 10, ["A"] * 10 + ["B"] * 10
        out = auc_with_interval(scores, labels, events, reps=50, seed=3)
        self.assertEqual((out["auc"], out["rows"], out["events"], out["ci95"]), (1.0, 20, 2, [1.0, 1.0]))
        paired = paired_auc(scores, [1 - s for s in scores], labels, events, names=("x", "y"), reps=50, seed=3)
        self.assertEqual((paired["x"]["auc"], paired["y"]["auc"], paired["difference"]["diff"]), (1.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
