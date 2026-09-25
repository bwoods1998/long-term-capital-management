"""J1, the move sensor (league/jev_features.py): no back-fill, the lab's exact state and questions,
per-market vs per-state caching, point-in-time rows, rows when Jev is unavailable, the frozen
model's loading and refusal, pacing, retention, and the held-out evaluation."""
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

from league.jev import MODEL, Sensor
from league.jev_features import (FEATURES, HORIZONS, LAB_QUESTIONS, MODEL_PATH, NUMERIC, PLACEHOLDER, RECORDED_ONLY,
                                 MoveModel, MoveSensor, auc_with_interval, category, evaluate, logistic, main)
from league.ledger import canonical
from league.recordings import Recorder
from league.semantic_lab import QUESTION_GUARD, SemanticLab
from league.tests.fakes import Clock


class FakeStateJev:
    """A gateway stand-in for lab-shaped states: answers every noul question with p (or p(name, state))."""

    def __init__(self, p=0.7, *, fail=False, cost="0.0001"):
        self.p, self.fail, self.cost, self.calls = p, fail, cost, []

    def __call__(self, ident, body):
        request = json.loads(body)
        self.calls.append((ident, request))
        if self.fail:
            raise TimeoutError("gateway timed out")
        answers = {name: {"type": "noul", "noul": self.p(name, request["state"]) if callable(self.p) else self.p}
                   for name in request["questions"]}
        return {"model": MODEL, "answers": answers, "usage": {"input_tokens": 2400}}, Decimal(self.cost)


def market(ticker, bid=0.40, ask=0.44, *, series=None, title="Bitcoin above 60,000 at 5pm EDT?", oi=120.0, hours=3.0):
    return {"market": ticker, "series": series or ticker.split("-")[0], "title": title, "yes_bid": bid, "yes_ask": ask,
            "close_time": "2026-09-10T21:00:00Z", "hours_to_close": hours, "hours_to_resolve": hours, "volume_24h": 50.0,
            "open_interest": oi, "strike": 60000.0}


FITTED = {
    "version": "move-test-1",
    "fitted_on": {"rows": 1000, "events": 40, "split": "chronological"},
    "questions": {"per_market": ["continuous_threshold", "relative_return", "discrete_event", "ambiguous_settlement"],
                  "per_state": ["related_exposure", "missing_catalyst_context", "fragile_liquidity", "recent_reversal"]},
    "numeric": [{"name": n, "definition": d} for n, (d, _) in NUMERIC.items() if n != "drift_oldest"],
    "horizons": {h: {"features": ["mid", "spread", "drift", "continuous_threshold", "fragile_liquidity"],
                     "mean": [0.5, 0.02, 0.0, 0.5, 0.5], "sd": [0.2, 0.01, 0.05, 0.3, 0.3],
                     "weights": [0.1 * int(h) / 15, 0.5, -0.4, 2.0, 1.2, 0.8], "l2": 0.01, "dev_auc": 0.76, "dev_auc_numeric": 0.61}
                 for h in ("5", "15", "60")},
    "numeric_only": {h: {"features": ["mid", "spread", "log_oi", "hours", "drift"], "mean": [0.5, 0.02, 0.3, 0.5, 0.0],
                         "sd": [0.2, 0.01, 0.1, 0.3, 0.05], "weights": [-0.2, 0.3, -0.6, 0.2, -0.1, 1.5], "l2": 0.01,
                         "dev_auc": 0.61, "dev_auc_numeric": 0.61} for h in ("5", "15", "60")},
}


class MoveCase(unittest.TestCase):
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
        kw = {"daily_usd": "1.50", "daily_calls": 25000, "purpose_calls": {"move": 19000}, **kw}
        return Sensor(self.root / "jev.sqlite", client, clock=self.clock, **kw)

    def model_file(self, data, name="model.json"):
        path = self.root / name
        path.write_text(json.dumps(data))
        return path

    def move(self, *, model=None, **settings):
        return MoveSensor(self.root, self.sensor, clock=self.clock, alert=lambda level, text: self.alerts.append(text),
                          settings={"interval_seconds": 300, **settings},
                          model_path=model if model is not None else MODEL_PATH)

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
        cycle = move.run()
        self.assertEqual(cycle["rows"], 1)
        self.assertEqual([r["market"] for r in self.rows(move)], ["KXBTCD-26SEP10-T60000"])
        self.assertEqual(self.rows(move)[0]["snapshot"], last + 1)
        self.assertEqual(move.run()["rows"], 0, "a snapshot is read once")

    def test_the_state_and_questions_are_exactly_the_labs(self):
        move = self.move()
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
        ours = [r for _, r in self.jev.calls if r["state"]["market"]["market"] == "KXBTCD-26SEP10-T60000"][-1]
        self.assertEqual(set(ours), {"model", "state", "questions"})
        self.assertEqual(canonical(ours["state"]), canonical(body["state"]), "byte for byte the lab's state")
        self.assertEqual(len(ours["state"]["earlier_quotes"]), 1)
        self.assertEqual([p["market"] for p in ours["state"]["peers"]], ["KXBTCD-26SEP10-T61000"])
        for name, question in ours["questions"].items():
            if name in FEATURES:
                self.assertEqual(question, body["questions"][name], name)
            else:
                self.assertIn(name, RECORDED_ONLY)
                self.assertTrue(question["instructions"].endswith(QUESTION_GUARD), "the lab's own guard")
        self.assertEqual(ours["questions"]["moves_15m"]["instructions"].split(" Treat")[0],
                         "Will this contract's quoted midpoint change within the next 15 minutes?")

    def test_per_market_questions_are_bought_once_per_market_text(self):
        move = self.move()
        self.started(move)
        ticker = "KXBTCD-26SEP10-T60000"
        for bid in (0.40, 0.41, 0.42):
            self.show(market(ticker, bid, bid + 0.04))
            move.run()
            self.clock.advance(300)
        asked = [sorted(r["questions"]) for _, r in self.jev.calls]
        every = sorted([*LAB_QUESTIONS, *RECORDED_ONLY])
        per_state = sorted([*MoveModel.load(MODEL_PATH).per_state, *RECORDED_ONLY])
        self.assertEqual(asked, [every, per_state, per_state])
        self.assertTrue(all(sorted(json.loads(r["answers"])) == every for r in self.rows(move)), "every row has all ten answers")
        self.show(market(ticker, 0.42, 0.46, title="Bitcoin above 60,000 at 6pm EDT?"))
        move.run()
        self.assertEqual(sorted(self.jev.calls[-1][1]["questions"]), every, "new contract text: the per-market questions again")

    def test_rows_are_point_in_time_and_latest_never_sees_the_future(self):
        move = self.move(model=self.model_file(FITTED))
        self.started(move)
        ticker = "KXBTCD-26SEP10-T60000"
        self.show(market(ticker))
        observed_one = self.clock()
        self.clock.advance(20)  # the cycle runs a little after the snapshot
        move.run()
        one = self.rows(move)[0]
        self.assertGreaterEqual(one["recorded_at"], one["observed"])
        self.assertIsNone(move.latest(ticker, one["recorded_at"] - 0.001), "not before it was written")
        got = move.latest(ticker, one["recorded_at"])
        self.assertEqual(got, {"move_p5": one["move_p5"], "move_p15": one["move_p15"], "move_p60": one["move_p60"],
                               "model_version": "move-test-1", "age_seconds": round(one["recorded_at"] - observed_one, 3)})
        self.clock.advance(300)
        self.show(market(ticker, 0.30, 0.34))
        self.clock.advance(20)
        move.run()
        two = self.rows(move)[1]
        self.assertNotEqual(one["move_p15"], two["move_p15"])
        self.assertEqual(move.latest(ticker, two["recorded_at"] - 1)["move_p15"], one["move_p15"])
        self.assertEqual(move.latest(ticker, two["recorded_at"])["move_p15"], two["move_p15"])
        self.assertIsNone(move.latest("KXBTCD-OTHER", two["recorded_at"]))

    def test_a_fitted_model_scores_rows_beside_the_numeric_model(self):
        self.jev.p = lambda name, state: {"continuous_threshold": 0.9, "fragile_liquidity": 0.2}.get(name, 0.5)
        move = self.move(model=self.model_file(FITTED))
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000", 0.40, 0.44, oi=300.0, hours=10.0))
        move.run()
        row = self.rows(move)[0]
        numeric = json.loads(row["numeric"])
        self.assertAlmostEqual(numeric["mid"], 0.42, places=6)  # stored at 6 places
        self.assertAlmostEqual(numeric["spread"], 0.04, places=6)
        self.assertAlmostEqual(numeric["log_oi"], math.log1p(300) / 15, places=6)
        self.assertAlmostEqual(numeric["hours"], 10 / 48, places=6)
        self.assertEqual(numeric["drift"], 0.0)
        for h in HORIZONS:
            block = FITTED["horizons"][str(h)]
            x = [0.42, 0.04, 0.0, 0.9, 0.2]
            score = block["weights"][0] + sum(w * (v - m) / s for w, v, m, s in zip(block["weights"][1:], x, block["mean"], block["sd"]))
            self.assertAlmostEqual(row[f"move_p{h}"], 1 / (1 + math.exp(-score)), places=5)
            only = FITTED["numeric_only"][str(h)]
            x = [0.42, 0.04, math.log1p(300) / 15, 10 / 48, 0.0]
            score = only["weights"][0] + sum(w * (v - m) / s for w, v, m, s in zip(only["weights"][1:], x, only["mean"], only["sd"]))
            self.assertAlmostEqual(row[f"numeric_p{h}"], 1 / (1 + math.exp(-score)), places=5)
        self.assertIsNone(row["why"])
        self.assertEqual(row["event"], "KXBTCD-26SEP10")
        self.assertEqual(row["series"], "KXBTCD")

    def test_the_placeholder_records_answers_but_no_move_p(self):
        move = self.move()
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"))
        move.run()
        row = self.rows(move)[0]
        self.assertEqual(row["model_version"], PLACEHOLDER)
        self.assertEqual(len(json.loads(row["answers"])), 10)
        self.assertEqual([row[f"move_p{h}"] for h in HORIZONS], [None, None, None])
        self.assertAlmostEqual(row["numeric_p15"], 0.493, places=5)
        self.assertIn("placeholder", row["why"])
        self.assertEqual(self.alerts, [], "a placeholder is expected, not an alert")

    def test_rows_are_written_when_jev_is_unavailable_and_say_why(self):
        self.jev.fail = True
        move = self.move(model=self.model_file(FITTED), workers=1)
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000"))
        cycle = move.run()
        rows = self.rows(move)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(self.jev.calls), 1, "the breaker stops the second call")
        for row in rows:
            self.assertIsNone(row["answers"])
            self.assertEqual([row[f"move_p{h}"] for h in HORIZONS], [None, None, None])
            self.assertTrue(all(row[f"numeric_p{h}"] is not None for h in HORIZONS))
        self.assertEqual(sorted(r["why"] for r in rows), ["jev: Jev breaker open after a failure", "jev: Jev call failed (TimeoutError)"])
        self.assertTrue(cycle["refusal"].startswith("jev:"))
        self.assertEqual(move.stats()["refusal"], cycle["refusal"])
        # The dollar cap: every call refused before it is made.
        self.sensor = self.new_sensor(FakeStateJev(), daily_usd="0.002")
        capped = MoveSensor(self.root / "capped", self.sensor, clock=self.clock, settings={"daily_usd_share": "1"},
                            recordings=self.root / "recordings.sqlite")
        capped.run()
        self.show(market("KXBTCD-26SEP10-T62000"))
        capped.run()
        self.assertIn("daily Jev cap $0.002 reached", self.rows(capped)[0]["why"])

    def test_the_budget_is_paced_over_the_day_and_jev_goes_round(self):
        move = self.move()
        # 19,000 calls, but the dollar share binds: $1.50 x 19,000/25,000 = $1.14 at ~$0.0001 a call,
        # over the 283 five-minute cycles left after 00:26:40 UTC.
        self.assertEqual(move._allowance(self.clock()), math.ceil(11400 / 283))
        self.sensor = self.new_sensor(self.jev, purpose_calls={"move": 3})
        move = self.move()
        self.assertEqual(move._allowance(self.clock()), 1, "the move cap's dollar share: one call at ~$0.0001")
        move = self.move(daily_usd_share="1")
        self.assertEqual(move._allowance(self.clock()), 1)
        self.started(move)
        tickers = ["KXBTCD-26SEP10-T60000", "KXBTCD-26SEP10-T61000", "KXBTCD-26SEP10-T62000"]
        answered = []
        for _ in range(3):
            self.show(*[market(t) for t in tickers])
            move.run()
            rows = self.rows(move)[-3:]
            self.assertEqual(len(rows), 3, "every market shown still gets its row")
            paced = [r for r in rows if r["answers"] is None]
            self.assertEqual(len(paced), 2)
            self.assertTrue(all(r["why"].endswith("paced: this cycle's share of today's move budget is spent") for r in paced))
            answered += [r["market"] for r in rows if r["answers"] is not None]
            self.clock.advance(300)
        self.assertEqual(sorted(answered), tickers, "Jev's turn goes round the markets")

    def test_more_markets_than_a_cycle_takes_go_round(self):
        move = self.move(max_markets_per_cycle=2)
        self.started(move)
        tickers = [f"KXBTCD-26SEP10-T6{n}000" for n in range(5)]
        for _ in range(3):
            self.show(*[market(t) for t in tickers])
            self.assertEqual(move.run()["rows"], 2)
            self.clock.advance(300)
        self.assertEqual({r["market"] for r in self.rows(move)}, set(tickers))

    def test_retention_prunes_quotes_rows_and_the_cached_state_answers(self):
        move = self.move(retention_days=1)
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"))
        move.run()
        self.assertEqual(len(self.rows(move)), 1)
        self.clock.advance(2 * 86400)
        pruned = move.prune()
        self.assertEqual((pruned["rows"], pruned["quotes"], pruned["markets"]), (1, 1, 1))
        self.assertEqual(pruned["answers"], 10, "six per-state answers after a day, four per-market after the retention")
        db = sqlite3.connect(self.root / "jev.sqlite")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM answers").fetchone()[0], 0)
        db.close()

    def test_bad_snapshots_a_replaced_recorder_and_failures_never_crash(self):
        move = self.move()
        self.started(move)
        db = sqlite3.connect(self.root / "recordings.sqlite")
        db.execute("INSERT INTO snapshots(source,started,received,digest,payload) VALUES('markets:X',0,?,'d',?)",
                   (self.clock(), b"not gzip"))
        db.execute("INSERT INTO snapshots(source,started,received,digest,payload) VALUES('markets:Y',0,?,'d',?)",
                   (self.clock(), gzip.compress(b'{"not":"a list"}')))
        db.commit()
        db.close()
        self.show(market("KXBTCD-26SEP10-T60000"), {"market": "bad", "yes_bid": 0.9, "yes_ask": 0.1}, "junk")
        cycle = move.run()
        self.assertEqual((cycle["bad_snapshots"], cycle["rows"]), (1, 1))
        # A replaced recordings store starts again at its newest snapshot.
        self.recorder.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(self.root / "recordings.sqlite") + suffix).unlink(missing_ok=True)
        self.recorder = Recorder(self.root / "recordings.sqlite", clock=self.clock)
        self.show(market("KXBTCD-26SEP10-T61000"))
        self.clock.advance(300)
        self.assertIn("recordings replaced", move.run()["note"])
        self.show(market("KXBTCD-26SEP10-T62000"))
        self.assertEqual(move.run()["rows"], 1)
        # A failing cycle is one alert and None; the same failure again is not a second alert.
        move._observe = lambda *a: 1 / 0
        self.show(market("KXBTCD-26SEP10-T63000"))
        self.assertIsNone(move.run())
        self.show(market("KXBTCD-26SEP10-T64000"))
        self.assertIsNone(move.run())
        self.assertEqual(len([a for a in self.alerts if "cycle failed" in a]), 1)
        self.assertIn("ZeroDivisionError", move.stats()["refusal"])

    def test_stats_for_health(self):
        move = self.move()
        self.started(move)
        self.show(market("KXBTCD-26SEP10-T60000"), market("KXBTCD-26SEP10-T61000"))
        move.run()
        stats = move.stats()
        self.assertEqual((stats["rows"], stats["markets"], stats["labels_bought_today"]), (2, 2, 20))
        self.assertEqual(stats["model_version"], PLACEHOLDER)
        self.assertFalse(stats["model_ready"])
        self.assertEqual(stats["today"]["calls"], 2)
        self.assertEqual(stats["today"]["cost_usd"], "0.0002")
        self.assertIsNotNone(stats["last_cycle_at"])
        self.assertIsInstance(stats["last_cycle_seconds"], float)
        self.assertEqual(stats["last_cycle"]["markets_shown"], 2)
        self.assertIn("labels only", stats["authority"])

    def test_due_follows_the_interval(self):
        move = self.move(interval_seconds=300)
        self.assertTrue(move.due())
        move.run()
        self.assertFalse(move.due())
        self.clock.advance(299)
        self.assertFalse(move.due())
        self.clock.advance(1)
        self.assertTrue(move.due())


class ModelTest(unittest.TestCase):
    def test_the_shipped_placeholder_loads_cleanly_and_is_no_jev_model(self):
        model = MoveModel.load(MODEL_PATH)
        data = json.loads(MODEL_PATH.read_text())
        self.assertEqual(model.version, PLACEHOLDER)
        self.assertEqual(model.problems, [])
        self.assertFalse(model.ready)
        self.assertEqual(sorted(model.per_market + model.per_state), sorted(FEATURES))
        self.assertTrue(set(n["name"] for n in data["numeric"]) <= set(NUMERIC))
        self.assertEqual(sorted(data["horizons"]), ["15", "5", "60"])
        self.assertEqual(model.move_p({n: 0.5 for n in [*NUMERIC, *FEATURES]}), {5: None, 15: None, 60: None})
        self.assertAlmostEqual(model.numeric_p({n: 0.1 for n in NUMERIC})[60], 0.624, places=5)
        self.assertTrue(data["fitted_on"]["placeholder"])

    def test_an_unknown_feature_refuses_the_model_and_leaves_the_numeric_p(self):
        bad = json.loads(json.dumps(FITTED))
        bad["horizons"]["15"]["features"][1] = "vibes"
        model = MoveModel(bad)
        self.assertFalse(model.ready)
        self.assertIn("unknown feature 'vibes'", model.problems[0])
        self.assertIsNotNone(model.numeric_p({n: 0.1 for n in NUMERIC})[15])
        recorded = json.loads(json.dumps(FITTED))
        recorded["horizons"]["60"]["features"][4] = "moves_60m"
        self.assertFalse(MoveModel(recorded).ready, "the recorded-only questions never enter a model")
        numeric = json.loads(json.dumps(FITTED))
        numeric["numeric_only"]["5"]["features"][0] = "fragile_liquidity"
        model = MoveModel(numeric)
        self.assertIsNone(model.numeric)
        self.assertTrue(model.ready)
        self.assertEqual(model.numeric_p({}), {5: None, 15: None, 60: None})
        for broken in ({**FITTED, "numeric": [{"name": "velocity", "definition": "?"}]},
                       {**FITTED, "questions": {"per_market": ["discrete_event"], "per_state": ["discrete_event"]}}):
            self.assertTrue(MoveModel(broken).problems)
        shape = json.loads(json.dumps(FITTED))
        shape["horizons"]["5"]["sd"][0] = 0
        self.assertFalse(MoveModel(shape).ready)

    def test_a_refused_model_is_an_alert_and_rows_carry_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = Clock()
            recorder = Recorder(root / "recordings.sqlite", clock=clock)
            alerts = []
            bad = json.loads(json.dumps(FITTED))
            bad["horizons"]["15"]["features"][1] = "vibes"
            (root / "model.json").write_text(json.dumps(bad))
            sensor = Sensor(root / "jev.sqlite", FakeStateJev(), clock=clock, daily_calls=25000, purpose_calls={"move": 19000},
                            daily_usd="1.50")
            move = MoveSensor(root, sensor, clock=clock, alert=lambda level, text: alerts.append(text), model_path=root / "model.json")
            self.assertEqual(len(alerts), 1)
            self.assertIn("vibes", alerts[0])
            move.run()
            clock.advance(300)
            recorder.record("markets:KXBTCD:24", [market("KXBTCD-26SEP10-T60000")], started=clock())
            move.run()
            recorder.close()
            db = sqlite3.connect(move.path)
            why, p15, n15 = db.execute("SELECT why, move_p15, numeric_p15 FROM move_rows").fetchone()
            db.close()
            self.assertIn("Jev model refused", why)
            self.assertIsNone(p15)
            self.assertIsNotNone(n15)
            (root / "unreadable.json").write_text("{")
            unreadable = MoveModel.load(root / "unreadable.json")
            self.assertIsNone(unreadable.numeric)
            self.assertFalse(unreadable.ready)
            self.assertIn("unreadable", unreadable.why_not)

    def test_logistic_clips_and_needs_every_input(self):
        block = {"features": ["mid"], "mean": [0.0], "sd": [1.0], "weights": [0.0, 1000.0]}
        self.assertAlmostEqual(logistic(block, {"mid": 1.0}), 1 / (1 + math.exp(-30)))
        self.assertIsNone(logistic(block, {}))
        self.assertIsNone(logistic(block, {"mid": float("nan")}))


class EvaluateTest(unittest.TestCase):
    """A synthetic store whose AUC is known: positives score 0.9, 0.8, 0.3 and negatives 0.7, 0.2,
    0.1, so 8 of 9 pairs are ordered: AUC 0.8889."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()
        move = MoveSensor(self.root, None, clock=self.clock, model_path=MODEL_PATH)
        self.path = move.path
        self.cutoff = 1789000000.0
        rows = [  # (market, observed, score, moves)
            ("KXBTCD-26SEP10-T1", 0, 0.9, 1), ("KXBTCD-26SEP10-T2", 60, 0.7, 0), ("KXBTCD-26SEP11-T1", 120, 0.8, 1),
            ("KXHIGHNY-26SEP10-B80", 180, 0.2, 0), ("KXHIGHNY-26SEP10-B81", 240, 0.3, 1), ("KXHIGHNY-26SEP11-B80", 300, 0.1, 0),
        ]
        db = sqlite3.connect(self.path)
        for n, (ticker, offset, score, moves) in enumerate(rows):
            observed = self.cutoff + offset
            self.insert(db, n, ticker, observed, score, 1 - score, {"moves_15m": score if moves else score / 10, "moves_60m": 0.5})
            db.execute("INSERT INTO move_quotes VALUES(?,?,?,?)", (ticker, int(observed // 60) * 60 + 960, 0.40 + 0.02 * moves, 0.44))
        # Before the cutoff: excluded (it would have been a misordered pair).
        self.insert(db, 90, "KXBTCD-26SEP09-T1", self.cutoff - 3600, 0.99, 0.5, None)
        db.execute("INSERT INTO move_quotes VALUES(?,?,?,?)", ("KXBTCD-26SEP09-T1", int((self.cutoff - 2640) // 60) * 60, 0.4, 0.44))
        # No outcome quote in [t + 15 min, t + 25 min]: excluded.
        self.insert(db, 91, "KXBTCD-26SEP12-T1", self.cutoff + 30, 0.05, 0.5, None)
        db.execute("INSERT INTO move_quotes VALUES(?,?,?,?)", ("KXBTCD-26SEP12-T1", int(self.cutoff // 60) * 60 + 3600, 0.9, 0.95))
        db.commit()
        db.close()

    def tearDown(self):
        self.dir.cleanup()

    @staticmethod
    def insert(db, n, ticker, observed, score, numeric_score, answers):
        db.execute("INSERT INTO move_rows(market,event,series,observed,minute,bid,ask,numeric,answers,move_p5,move_p15,move_p60,"
                   "numeric_p5,numeric_p15,numeric_p60,model_version,snapshot,recorded_at,why) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (ticker, ticker.rsplit("-", 1)[0], ticker.split("-")[0], observed, int(observed // 60) * 60, 0.40, 0.44, "{}",
                    json.dumps(answers) if answers else None, None, score, None, None, numeric_score, None, "move-test-1", n,
                    observed + 30, None))

    def test_a_known_auc_on_held_out_rows_with_a_seeded_interval(self):
        report = evaluate(self.path, self.cutoff, (15,), reps=100)
        overall = report["horizons"]["15"]["overall"]
        self.assertEqual(report["rows_after_cutoff"], 7)
        self.assertEqual((overall["rows"], overall["events"], overall["base_rate"]), (6, 4, 0.5))
        self.assertEqual(overall["auc"]["move_p"]["auc"], round(8 / 9, 4))
        self.assertEqual(overall["auc"]["numeric_p"]["auc"], round(1 / 9, 4))
        self.assertEqual(overall["auc"]["moves_15m"]["auc"], 1.0)
        self.assertEqual(overall["auc"]["moves_60m"]["auc"], 0.5, "ties count half")
        low, high = overall["auc"]["move_p"]["ci95"]
        self.assertLessEqual(low, 8 / 9)
        self.assertGreaterEqual(high, 8 / 9)
        self.assertTrue(overall["meets_ship_rule"])
        self.assertEqual(sorted(report["horizons"]["15"]["by_category"]), ["crypto", "weather"])
        self.assertEqual(report["horizons"]["15"]["by_category"]["crypto"]["auc"]["move_p"]["auc"], 1.0)
        self.assertEqual(evaluate(self.path, self.cutoff, (15,), reps=100), report, "seeded: the same interval twice")
        self.assertEqual(report["model_versions"], ["move-test-1"])

    def test_the_cli_reads_the_store_without_writing(self):
        before = self.path.read_bytes()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["evaluate", "--store", str(self.path), "--cutoff",
                                   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.cutoff)), "--json", "--reps", "20"]), 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["horizons"]["15"]["overall"]["auc"]["move_p"]["auc"], round(8 / 9, 4))
        self.assertEqual(self.path.read_bytes(), before)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["evaluate", "--store", str(self.path), "--cutoff", str(self.cutoff), "--horizons", "15", "--reps", "0"])
        self.assertIn("move_p=0.889", out.getvalue())

    def test_the_interval_resamples_whole_events(self):
        # Two events with ten identical rows each: resampling rows would never lose an event,
        # resampling events loses one in half the draws (and then the AUC is undefined).
        scores = [0.9] * 10 + [0.1] * 10
        labels = [1] * 10 + [0] * 10
        events = ["A"] * 10 + ["B"] * 10
        out = auc_with_interval(scores, labels, events, reps=50, seed=3)
        self.assertEqual((out["auc"], out["rows"], out["events"]), (1.0, 20, 2))
        self.assertEqual(out["ci95"], [1.0, 1.0])

    def test_categories(self):
        self.assertEqual([category(s) for s in ("KXBTCD", "KXETH15M", "KXHIGHNY", "KXRAIN", "KXNFLGAME", "KXMLBTOTAL",
                                                "KXWTI", "KXFEDDECISION", "KXTRUMPSAY", None)],
                         ["crypto", "crypto", "weather", "weather", "sports", "sports", "finance", "finance", "other", "other"])
        self.assertEqual(category(None, "KXEPLGAME-26SEP10-ARS"), "sports")


if __name__ == "__main__":
    unittest.main()
