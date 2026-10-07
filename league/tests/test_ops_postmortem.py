"""The weekly post-mortem (league/ops/postmortem.py): the week's receipts read by code from the House's own files, the
monthly cost review and its D6 proposal, the model-safe prompt, one Claude call through the swarm's real ModelRouter
(its role line, its run cap, the reserve kept for it, a rerun paid once), the private report and the public page."""
import contextlib
import json
import sqlite3
import time
import unittest
from unittest import mock

from league.claude import Claude
from league.live import calibration as CAL
from league.live import observe as OBS
from league.live import state as LS
from league.ops import budget as B
from league.ops import postmortem as PM
from league.ops import registry
from league.ops import scoreboard as SB
from league.ops.context import GatewayError
from league.ops.runner import module_present
from league.ops.store import OpsStore
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from league.tests.test_claude import message
from league.tests.test_frontier import GATEWAY, FakeOpener
from league.tests.test_ops_jobs import Base, FakeGateway, at
from league.tests.test_swarm_claude_routing import FakeClaudeMeter

DUE = "2026-10-10T14:00:00Z"   # the second Saturday of October: no cost review
FIRST = "2026-10-03T14:00:00Z"  # the first Saturday: the cost review
IN_1, IN_2, BEFORE = "2026-10-05T15:00:00Z", "2026-10-08T18:00:00Z", "2026-10-02T15:00:00Z"
ANSWER = {"headline": "Real opens paid two dollars a contract more than the Gym assumed.",
          "findings": ["Calibration opens at the midpoint filled half the time.", "One order was rejected by the venue for a cap."],
          "actions": ["Price opens one tick through the midpoint and measure the fill rate next week."],
          "cost_note": "The week cost far more than it earned."}


def order(db, oid, placed, status, *, instance="fam-alpha@3:r", family="fam-alpha", answer=None):
    db.execute("INSERT INTO orders(oid, client_id, instance, family, action, type, root, legs, qty, limit_value, limit_price, "
               "placed_at, day, placed_minute, status, answer, updated_at) VALUES(?,?,?,?,'open','debit_vertical','SPY','[]',1,"
               "0.5,'0.50',?,'d',600,?,?,?)", (oid, f"c{oid}", instance, family, at(placed), status,
                                                 json.dumps(answer) if answer else None, at(placed)))


def sample(db, oid, submitted, cell, action, outcome, fill, mid):
    db.execute("INSERT INTO samples(oid, client_id, trip, day, symbol, legs, action, offset, cell, limit_price, limit_value, qty, "
               "quote, mid, submitted_at, outcome, fill_value, filled_qty) VALUES(?,?,'t','d','SPY','[]',?,'mid',?,'0.45',0.45,1,"
               "'{}',?,?,?,?,?)", (oid, f"k{oid}", action, cell, mid, at(submitted), outcome, fill,
                                  1 if outcome in ("filled", "partial") else 0))


def event(db, n, day, kind, body):
    db.execute("INSERT INTO events VALUES('fam-alpha@3:o', 'acct', ?, 'fam-alpha', 3, ?, 600, ?, ?, 0)",
               (n, day, kind, json.dumps({"kind": kind, **body})))


@contextlib.contextmanager
def fixture(path):
    """A fixture database: one transaction, no fsync, closed after."""
    db = sqlite3.connect(path)
    db.execute("PRAGMA synchronous=OFF")
    try:
        with db:
            yield db
    finally:
        db.close()


def summary(cutoff, costs, days, p30=None):
    return {"cutoff": cutoff, "costs": [{"service": k, "usd": v} for k, v in costs.items()],
            "realized": {"by_close_day": [{"day": d, "closed_positions": n, "total_usd": usd} for d, n, usd in days]},
            "p30": p30}


class House(Base):
    """A House's state with one week of receipts in every file the post-mortem reads."""

    def setUp(self):
        super().setUp()
        self.now = at(DUE) + 60
        self.clock = Clock(at("2026-09-28T12:00:00Z"))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        spec = {"mechanism": "Index options price more movement than follows on average.", "dte": [0, 2]}
        self.alpha = self.store.add_family({**spec, "id": "fam-alpha", "structure": "debit_vertical", "roots": ["SPY"]},
                                           origin="architect")["id"]
        self.condor = self.store.add_family({**spec, "id": "condor-vrp", "structure": "iron_condor", "roots": ["SPY"]},
                                            origin="architect")["id"]
        self.clock.t = at(IN_1)
        self.store.set_band(self.alpha, "probe", reason="the ladder's Probe line")
        self.clock.t = at(IN_2)
        self.store.set_band(self.alpha, "candidate", reason="demoted: fam-alpha's forward record is negative over 20 trades")
        self.store.retire(self.condor, "idle: no improvement in 48 hours")
        self.store.add_spend("sail_model", 3.5, family=self.alpha, detail={})
        self.store.add_spend("claude", 0.4, detail={"role": "strategist"})
        self.clock.t = self.now
        with fixture(self.root / "live.sqlite") as db:
            db.executescript(LS.SCHEMA)
            order(db, 1, IN_1, "filled")
            order(db, 2, IN_1, "cancelled", instance=CAL.INSTANCE, family=CAL.FAMILY)
            order(db, 3, IN_2, "rejected", answer={"final": "rejected", "reject_reason":
                                                   "insufficient buying power for SPY261009C00600000 on 2026-10-08 (fam-alpha)"})
            order(db, 4, IN_2, "refused", answer={"error": "over the gateway's order cap", "gateway": True})
            order(db, 5, BEFORE, "filled")
            db.executemany("INSERT INTO fills(oid, qty, value, fees, at) VALUES(?, 1, 0.5, 0.65, ?)",
                           [(1, at(IN_1)), (2, at(IN_2)), (5, at(BEFORE))])
        with fixture(self.root / "calibration.sqlite") as db:
            db.executescript(CAL.SCHEMA)
            sample(db, 1, IN_1, "SPY:open:mid", "open", "filled", 0.47, 0.45)
            sample(db, 2, IN_1, "SPY:open:mid", "open", "cancelled", None, 0.45)
            sample(db, 3, IN_2, "SPY:close:mid", "close", "filled", 0.40, 0.41)
            sample(db, 4, BEFORE, "SPY:open:mid", "open", "filled", 0.55, 0.45)
        with fixture(self.root / "observe.sqlite") as db:
            db.executescript(OBS.SCHEMA)
            event(db, 1, "2026-10-05", "fill", {"action": "open", "price": 1.10, "quantity": 2, "decision_mid": 1.05,
                                                "decision_natural": 1.10, "slippage_to_decision_mid_usd": 10.0})
            event(db, 2, "2026-10-06", "fill", {"action": "close", "price": 0.90, "quantity": 1, "decision_mid": 0.93,
                                                "decision_natural": 0.85, "slippage_to_decision_mid_usd": 3.0})
            event(db, 3, "2026-10-06", "rejected", {"reason": "fam-alpha: the shadow book has no room"})
            for n in (4, 5, 6):
                event(db, n, "2026-10-07", "order", {})
            event(db, 7, "2026-10-02", "fill", {"action": "open", "price": 9, "quantity": 1, "slippage_to_decision_mid_usd": 99})
        sha = "a" * 40
        deploys = [{"deploy": "d1", "release": "r1", "sha": sha, "stage": "start", "at": IN_1},
                   {"deploy": "d1", "release": "r1", "sha": sha, "stage": "promote", "ok": True, "at": IN_1},
                   {"deploy": "d1", "release": "r1", "sha": sha, "stage": "verdict", "verdict": "promoted", "at": IN_1},
                   {"deploy": "d2", "release": "r2", "sha": "b" * 40, "stage": "promote", "ok": True, "at": IN_2},
                   {"deploy": "d2", "release": "r2", "sha": "b" * 40, "stage": "verdict", "verdict": "rolled_back", "at": IN_2},
                   {"deploy": "d0", "release": "r0", "sha": "c" * 40, "stage": "promote", "ok": True, "at": BEFORE},
                   {"deploy": "o1", "release": "o1", "stage": "verdict", "verdict": "promoted", "at": IN_2}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in deploys))
        (self.root / "harness").mkdir()
        with fixture(self.root / "harness" / "engineer.sqlite") as db:
            db.execute("CREATE TABLE candidates (id INTEGER PRIMARY KEY, opened_at REAL, status TEXT, lane TEXT)")
            db.executemany("INSERT INTO candidates(opened_at, status, lane) VALUES(?, ?, 'research')",
                           [(at(IN_1), "retained"), (at(IN_2), "open"), (at(BEFORE), "reverted")])
            db.execute("CREATE TABLE notes (at REAL, text TEXT)")
        ops = OpsStore(self.root)
        ops.record("economics", "2026-10-06T20:10:00Z", "ok", "2026-10-06T20:20:00Z")
        ops.record("preopen", "2026-10-07T12:30:00Z", "missed", "2026-10-07T13:30:00Z", error="late")
        ops.record("scoreboard", "2026-10-07T23:30:00Z", "failed", "2026-10-07T23:31:00Z", error="gateway")
        ops.close()
        self.economics("20261002-close", summary("2026-10-02T20:00:00Z", {"Sail (models + boxes)": "100.00", "ThetaData": "20.00",
                                                                          "Claude (Anthropic via the gateway)": "50.00"},
                                                 [("2026-09-29", 1, "0.50"), ("2026-10-02", 1, "1.00")]))
        self.economics("20261009-close", summary("2026-10-09T20:00:00Z", {"Sail (models + boxes)": "130.00", "ThetaData": "38.40",
                                                                          "Claude (Anthropic via the gateway)": "60.00"},
                                                 [("2026-09-29", 1, "0.50"), ("2026-10-02", 1, "1.00"), ("2026-10-05", 2, "2.50"),
                                                  ("2026-10-08", 1, "-0.75")], p30={"usd": "3.25"}))
        self.opener = FakeOpener()
        self.meter = FakeClaudeMeter(100)
        self.swarm_json({"claude": {"stream": False}})
        self.budget_json(B.ceiling_usd_day("claude"))

    def budget_json(self, claude_usd_day):
        """A fresh budget.json (RULE_VERSION 2) giving Claude `claude_usd_day` research dollars today: the job is judged
        inside the Claude meter at its ceiling. `settings.load` reads it on the real clock."""
        (self.root / "budget.json").write_text(json.dumps({"schema": B.SCHEMA, "rule_version": B.RULE_VERSION,
                                                           "at": time.time(), "meters": {
                                                               "sail": {"research_usd_day": B.ceiling_usd_day("sail")},
                                                               "claude": {"research_usd_day": claude_usd_day}}}))

    def economics(self, name, value):
        folder = self.root / "economics" / name
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps(value))

    def swarm_json(self, value):
        (self.root / "swarm.json").write_text(json.dumps(value))

    def claude(self, model):
        return Claude(GATEWAY, lambda: "synthetic", model=model, opener=self.opener)

    def run_job(self, *, due=DUE, gateway=None, settings=None):
        self.gateway = gateway or FakeGateway()
        ctx = self.last_ctx = self.ctx("postmortem", gateway=self.gateway, settings=settings, due=at(due))
        return PM.run(ctx, claude_factory=self.claude, claude_meter=self.meter)

    def alerts(self):
        return [a for a in self.last_ctx.alerts if a["text"].startswith("postmortem: no reading")]

    def week(self):
        start, end = PM.window(at(DUE))
        return PM.facts(self.root, self.base, start, end)


class Week(House):
    def test_the_window_is_the_seven_days_to_the_run_and_the_review_is_monthly(self):
        self.assertEqual(PM.window(at(DUE)), (at("2026-10-03T14:00:00Z"), at(DUE)))
        self.assertTrue(PM.month_first(at(FIRST)))
        self.assertFalse(PM.month_first(at(DUE)))
        job = registry.by_name()["postmortem"]
        self.assertEqual((job.module, job.triggers[0].describe()), ("league.ops.postmortem", "weekly Sat 14:00Z"))
        self.assertTrue(module_present(job.module))

    def test_real_orders_count_the_week_by_outcome_and_route_with_their_reasons(self):
        o = self.week()["orders"]
        self.assertEqual(o["placed"], 4)
        self.assertEqual(o["by_status"], {"filled": 1, "cancelled": 1, "rejected": 1, "refused": 1})
        self.assertEqual(o["by_route"]["calibration"], {"cancelled": 1})
        self.assertEqual(o["fill_rate"], round(1 / 3, 4))
        self.assertEqual(o["fills"], {"n": 2, "contracts": 2, "fees_usd": 1.3})
        reasons = [r["text"] for r in o["reasons"]]
        self.assertTrue(any(r.startswith("venue: insufficient buying power") for r in reasons))
        self.assertIn("before the venue: over the gateway's order cap", reasons)

    def test_real_fills_against_the_mid_beside_the_practice_books_under_the_gyms_rules(self):
        week = self.week()
        c, p = week["calibration"], week["practice"]
        self.assertEqual(c["cells"]["SPY:open:mid"], {"attempts": 2, "ended": 2, "filled": 1, "fill_rate": 0.5,
                                                      "mean_worse_ticks": 2.0, "mean_worse_usd_per_contract": 2.0})
        self.assertEqual(c["cells"]["SPY:close:mid"]["mean_worse_usd_per_contract"], 1.0)
        self.assertEqual((c["attempts"], c["fills"], c["mean_worse_usd_per_contract"]), (3, 2, 1.5))
        self.assertEqual((p["orders"], p["fills"], p["rejected"]), (3, 2, 1))
        self.assertEqual(p["slippage_usd_per_contract"], {"all": 4.0, "open": 5.0, "close": 3.0})
        self.assertEqual(p["share_at_natural"], 0.5)

    def test_band_moves_harness_changes_jobs_and_spend(self):
        week = self.week()
        b, h, j, s = week["bands"], week["harness"], week["jobs"], week["spend"]
        self.assertEqual((b["demotions"], b["promotions"], b["retirements"]), (1, 1, 1))
        self.assertEqual(b["moves"], {"gym -> probe": 1, "probe -> candidate": 1})
        self.assertEqual(b["demoted"][0]["family"], "fam-alpha")
        self.assertEqual(h["self_deploys"], {"promoted": 1, "rolled_back": 1})
        self.assertEqual(h["owner_deploys"], {"promoted": 1})
        self.assertEqual(h["engineer"], {"candidates": {"retained": 1, "open": 1}})
        self.assertEqual(j["failed"], {"scoreboard": 1})
        self.assertEqual(j["missed"], {"preopen": 1})
        self.assertEqual(s["by_kind"], {"claude": 0.4, "sail_model": 3.5})
        self.assertEqual(s["claude_by_role"], {"strategist": 0.4})
        self.assertEqual(week["unread"], {})

    def test_the_weeks_costs_are_the_newest_close_economics_less_the_one_before_the_week(self):
        costs = self.week()["costs"]
        self.assertEqual((costs["from"], costs["to"], costs["partial"]), ("2026-10-02T20:00:00Z", "2026-10-09T20:00:00Z", False))
        self.assertEqual({r["service"]: r["usd"] for r in costs["by_service"]},
                         {"Sail (models + boxes)": "30.00", "ThetaData": "18.40", "Claude (Anthropic via the gateway)": "10.00"})
        self.assertEqual((costs["total_usd"], costs["realized_options_pnl_usd"], costs["net_usd"], costs["closed_positions"]),
                         ("58.40", "1.75", "-56.65", 3))

    def test_a_part_that_cannot_be_read_is_named_and_the_others_still_count(self):
        (self.root / "observe.sqlite").write_bytes(b"not a database at all, just bytes" * 10)
        week = self.week()
        self.assertIn("practice", week["unread"])
        self.assertEqual(week["orders"]["placed"], 4)

    def test_nothing_is_written_while_the_week_is_read(self):
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*.sqlite")}
        self.week()
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob("*.sqlite")}, before)


class CostReview(House):
    def test_the_rule_keeps_standard_until_the_ladder_is_live_and_the_universe_stops_moving(self):
        self.assertEqual(PM.propose(ladder_live=False, new_roots=[], universe=["SPY"], price_usd=100)["decision"], "keep_standard")
        moving = PM.propose(ladder_live=True, new_roots=["IWM"], universe=["SPY", "IWM"], price_usd=100)
        self.assertEqual(moving["decision"], "keep_standard")
        self.assertIn("still moves", moving["why"])
        self.assertEqual(PM.propose(ladder_live=True, new_roots=[], universe=[], price_usd=None)["decision"], "keep_standard")

    def test_then_a_one_time_purchase_when_it_pays_back_else_the_value_plan(self):
        bought = PM.propose(ladder_live=True, new_roots=[], universe=["QQQ", "SPY"], price_usd=400)
        self.assertEqual((bought["decision"], bought["payback_months"], bought["saves_usd_month"]), ("one_time_purchase", 5.0, 80.0))
        slow = PM.propose(ladder_live=True, new_roots=[], universe=["SPY"], price_usd=2000)
        self.assertEqual((slow["decision"], slow["saves_usd_month"]), ("drop_to_value", 40.0))
        self.assertIn("25.0 months", slow["why"])
        wide = PM.propose(ladder_live=True, new_roots=[], universe=["SPY", "TSLA"], price_usd=100)
        self.assertEqual(wide["decision"], "drop_to_value")
        unpriced = PM.propose(ladder_live=True, new_roots=[], universe=["SPY"], price_usd=None)
        self.assertIn("no price yet", unpriced["why"])
        self.assertEqual(PM.VENDOR_PLANS_USD_MONTH["standard"], 80.0)
        from league.publish import SUBSCRIPTIONS_MONTHLY_USD

        self.assertEqual(float(SUBSCRIPTIONS_MONTHLY_USD["thetadata_usd"]), PM.VENDOR_PLANS_USD_MONTH["standard"])

    def test_the_review_reads_thirty_days_from_t0_and_the_research_universe(self):
        review = PM.cost_review(self.root, at(FIRST))
        costs = review["costs"]
        self.assertEqual((costs["from"], costs["total_usd"], costs["realized_options_pnl_usd"]),
                         ("2026-09-26T06:23:14Z", "170.00", "1.50"))
        self.assertEqual(review["vendor"]["usd"], "20.00")
        self.assertEqual(review["vendor"]["share_of_costs"], round(20 / 170, 4))
        self.assertEqual(review["research"]["universe"], ["SPY"])
        self.assertEqual(review["research"]["births"], 2)
        self.assertEqual(review["proposal"]["decision"], "keep_standard")  # no forward ladder yet

    def test_the_review_runs_on_the_first_saturday_and_ops_json_overrides(self):
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")] * 3
        self.assertIsNotNone(self.run_job(due=FIRST)["cost_review"])
        self.assertIsNone(self.run_job()["cost_review"])
        self.assertEqual(self.run_job(settings={"postmortem": {"cost_review": "always", "model": False}})["cost_review"],
                         "keep_standard")
        self.assertIn("Cost review", (self.root / "postmortem" / "2026-10-10.md").read_text())


class Model(House):
    def test_scrub_and_the_model_safety_check(self):
        text = PM.scrub("fam-alpha rejected SPY261009C00600000 on 2026-10-08T15:00:00Z; café 2026", {"fam-alpha"})
        self.assertEqual(text, "<program> rejected <contract> on <date>; caf? <year>")
        self.assertEqual(PM.model_problems(text, {"fam-alpha"}), [])
        # A reason that names a Validation or holdout figure is withheld whole: the figure beside the word goes too.
        for gated in ("demoted: holdout t -0.4 below the bar", "the Validation Sharpe 0.31", "held-out t 2.1", "held out 1.9"):
            self.assertEqual(PM.scrub(gated, {"fam-alpha"}), PM.WITHHELD_REASON, gated)
        self.assertNotIn("0.4", PM.scrub("holdout t -0.4", ()))
        self.assertEqual(PM.model_problems(PM.WITHHELD_REASON), [])
        for bad, problem in (("café", "non-ASCII text"), ("the fam-alpha family", "a family name"),
                             ("its Validation t", "a Validation or holdout figure"), ("on 2026-10-08", "a date"),
                             ("SPY261009C00600000", "an option contract symbol")):
            self.assertIn(problem, PM.model_problems(bad, {"fam-alpha"}), bad)
        self.assertEqual(PM.model_problems("orders 2045 this week", set()), [])  # a count is not a date
        # A one-word id is an ordinary word: it never withholds a page or keeps the model from being asked.
        self.assertEqual(PM.model_problems("an iron condor", {"condor"}), [])
        self.assertTrue(PM.public_text_ok("an iron condor", {"condor", "fam-alpha"}))
        self.assertFalse(PM.public_text_ok("FAM-ALPHA again", {"fam-alpha"}))
        for spelling in ("the held-out t was 2.1", "held out at 1.9", "the holdout failed", "Validation was weak"):
            self.assertFalse(PM.public_text_ok(spelling, set()), spelling)

    def test_the_prompt_is_aggregates_only_and_model_safe(self):
        week = self.week()
        text = PM.prompt(week, PM.cost_review(self.root, at(DUE)), PM.family_ids(self.root))
        self.assertEqual(PM.model_problems(text, PM.family_ids(self.root)), [])
        self.assertTrue(PM.SYSTEM.isascii())
        self.assertIn("SPY:open:midpoint: 2, 2, 1, 0.5, 2.0, 2.0", text)
        self.assertIn("opens 5.0, closes 3.0", text)
        self.assertIn("demotions 1, promotions 1, retirements 1", text)
        self.assertIn("<program>", text)
        self.assertNotIn("fam-alpha", text)
        self.assertNotIn("condor-vrp", text)
        self.assertLessEqual(len(text), PM.PROMPT_MAX_CHARS)

    def test_one_call_on_the_postmortem_role_booked_in_the_swarms_spend(self):
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        out = self.run_job()
        self.assertEqual(len(self.opener.calls), 1)
        request = self.opener.calls[0][0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["output_config"]["format"]["schema"], PM.SCHEMA)
        self.assertEqual(request.get_header("X-ltcm-role"), "postmortem")
        self.assertEqual(out["model"]["model"], "claude-opus-5-5")
        self.assertAlmostEqual(out["model"]["cost_usd"], 0.31)
        self.assertLessEqual(out["model"]["worst_case_usd"], PM.RUN_CAP_USD)
        rows = [json.loads(r["detail"]) for r in self.store._all("SELECT detail FROM spend WHERE kind='claude'")]
        self.assertTrue(any(r.get("role") == "postmortem" and "hold" in r for r in rows))
        self.assertAlmostEqual(self.store.spent(["claude"]) - 0.4, 0.31, places=6)
        report = (self.root / "postmortem" / "2026-10-10.md").read_text()
        self.assertIn(ANSWER["headline"], report)
        self.assertIn("fam-alpha", report)  # private: the families by name
        self.assertEqual(json.loads((self.root / "postmortem" / "2026-10-10.json").read_text())["narrative"]["answer"]["actions"],
                         ANSWER["actions"])

    def test_a_rerun_of_the_week_reuses_the_narrative_it_paid_for(self):
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        self.run_job()
        out = self.run_job()
        self.assertEqual(len(self.opener.calls), 1)
        self.assertTrue(out["model"]["reused"])

    def test_the_roles_own_line_holds_the_run_to_a_dollar_a_day(self):
        self.store.add_spend("claude", 0.8, detail={"role": "postmortem"})
        out = self.run_job()
        self.assertEqual(self.opener.calls, [])
        self.assertIn("postmortem line for today has no room", out["model"]["missing"])
        self.assertEqual(out["model"]["kind"], "line")  # the refusal's kind is in the receipt
        alerts = self.alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["level"], "warning")
        self.assertIn("(line)", alerts[0]["text"])
        self.assertIn("No narrative this week", (self.root / "postmortem" / "2026-10-10.md").read_text())
        self.assertEqual(out["posted"], "docs/runs/desk/2026-10-10-postmortem.md")  # the facts are still published

    def test_the_budgets_claude_line_holds_the_run_inside_the_claude_meter(self):
        # Budget rule v2: the post-mortem's call is admitted inside the day's Claude research dollars less the gate's
        # two holds. With no budget.json (the floor, $2 of Claude) the line has $0.05 for this role: no call, the
        # refusal's kind in the receipt, a warning, and the week's facts still written and published.
        (self.root / "budget.json").unlink()
        out = self.run_job()
        self.assertEqual(self.opener.calls, [])
        self.assertEqual(out["model"]["kind"], "line")
        self.assertIn("research budget's Claude line", out["model"]["missing"])
        self.assertEqual(len(self.alerts()), 1)
        self.assertEqual(out["posted"], "docs/runs/desk/2026-10-10-postmortem.md")
        # Two dollars of Claude left today at the ceiling's rule: the call (its hold under a dollar) is asked.
        self.budget_json(2.0 + sum(B.GATE_HOLDS_USD.values()))
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        self.assertAlmostEqual(self.run_job()["model"]["cost_usd"], 0.31)

    def test_the_run_cap_is_checked_before_the_call(self):
        with mock.patch.object(PM, "RUN_CAP_USD", 0.05):
            out = self.run_job()
        self.assertEqual(self.opener.calls, [])
        self.assertIn("over the run's cap", out["model"]["missing"])

    def test_it_may_spend_the_reserve_kept_for_it_but_not_past_the_funded_total(self):
        self.meter.value = 1.0  # under the swarm's 5-dollar reserve: no other role could call now
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        self.assertIn("cost_usd", self.run_job()["model"])
        self.meter.value = 0.1
        (self.root / "postmortem" / "2026-10-10.json").unlink()
        self.assertIn("no room", self.run_job()["model"]["missing"])
        self.assertEqual(len(self.opener.calls), 1)

    def test_a_swarm_json_that_replaces_the_roles_still_serves_the_postmortem_at_a_small_hold(self):
        # The House's swarm.json (scratch/v3/migrate) names its own roles and 32,000 max_tokens; `_merge` replaces lists.
        house = {"claude": {"stream": False, "max_tokens": 32000,
                            "roles": ["architect", "audit", "diagnostician", "rewrite", "review", "researcher", "strategist"]}}
        self.swarm_json(house)
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        out = self.run_job()
        self.assertEqual(len(self.opener.calls), 1)
        self.assertEqual(json.loads(self.opener.calls[0][0].data)["max_tokens"], PM.MAX_TOKENS)
        self.assertLess(out["model"]["worst_case_usd"], 0.6)  # about $0.52, not the $0.87 of 32,000
        self.assertEqual(self.alerts(), [])
        self.assertEqual(json.loads((self.root / "swarm.json").read_text()), house)  # the box's own file is untouched

    def test_the_jobs_router_adds_the_role_and_holds_max_tokens_on_its_own_copy(self):
        for claude, tokens in (({"roles": ["architect"], "max_tokens": 32000}, 16000), ({"roles": None, "max_tokens": 8000}, 8000),
                               ({"max_tokens": "junk"}, 16000), ({"roles": ["postmortem"], "max_tokens": 0}, 16000)):
            with self.subTest(claude=claude):
                self.swarm_json({"claude": {"stream": False, **claude}})
                ctx = self.ctx("postmortem", gateway=FakeGateway(), due=at(DUE))
                router = PM.router_for(ctx, self.store, claude_factory=self.claude, claude_meter=self.meter)
                cfg = router.settings["claude"]
                self.assertEqual(cfg["roles"].count("postmortem"), 1)
                self.assertEqual(cfg["max_tokens"], tokens)
                self.assertEqual(cfg["reserve_usd"], 0.0)
                self.assertTrue(router.claude_enabled("postmortem"))

    def test_claude_not_configured_is_a_missing_reading_with_an_alert(self):
        self.swarm_json({"claude": {"stream": False, "model": ""}})
        out = self.run_job()
        self.assertEqual(self.opener.calls, [])
        self.assertEqual(out["model"]["kind"], "off")
        self.assertIn("not configured for the postmortem role", out["model"]["missing"])
        self.assertEqual(len(self.alerts()), 1)

    def test_a_router_that_fails_leaves_the_report_without_a_narrative(self):
        with mock.patch.object(PM, "router_for", side_effect=RuntimeError("settings unreadable")):
            out = self.run_job()
        self.assertIn("could not be made (RuntimeError: settings unreadable)", out["model"]["missing"])
        self.assertEqual(out["model"]["kind"], "router")
        self.assertEqual(len(self.alerts()), 1)
        self.assertTrue((self.root / "postmortem" / "2026-10-10.md").exists())
        self.assertEqual(out["posted"], "docs/runs/desk/2026-10-10-postmortem.md")

    def test_ops_json_can_switch_the_model_off(self):
        out = self.run_job(settings={"postmortem": {"model": False}})
        self.assertEqual(self.opener.calls, [])
        self.assertIn("switched off", out["model"]["missing"])
        self.assertEqual(self.alerts(), [])  # the owner's own off switch is quiet


class Pages(House):
    def test_the_public_page_is_posted_through_the_docs_route_and_passes_the_filter(self):
        self.opener.script = [message(json.dumps(ANSWER), cost="0.31")]
        out = self.run_job()
        path, body = self.gateway.posts[0]
        self.assertEqual((path, body["path"]), ("/v1/github/docs", "docs/runs/desk/2026-10-10-postmortem.md"))
        self.assertTrue(body["message"].startswith("desk:"))
        text = body["content"]
        self.assertEqual(SB.public_problems(text), [])
        for private in ("fam-alpha", "condor-vrp", "SPY261009C00600000", "buying power", "order cap"):
            self.assertNotIn(private, text)
        self.assertIn(ANSWER["headline"], text)
        self.assertIn("| 4 | 1 | 1 | 1 | 1 | 0.3333 |", text)
        self.assertIn("| **Total** | **58.40** |", text)
        self.assertFalse(out["withheld"])
        self.assertEqual(out["posted"], body["path"])

    def test_a_reading_that_names_a_family_or_fails_the_filter_stays_private(self):
        for findings in (["fam-alpha lost the most."], ["The bid was too high."]):
            with self.subTest(findings=findings):
                (self.root / "postmortem").mkdir(exist_ok=True)
                for f in (self.root / "postmortem").iterdir():
                    f.unlink()
                self.opener.script = [message(json.dumps({**ANSWER, "findings": findings}), cost="0.31")]
                out = self.run_job()
                text = self.gateway.posts[0][1]["content"]
                self.assertTrue(out["withheld"])
                self.assertNotIn(findings[0], text)
                self.assertIn("kept private", text)
                self.assertIn(findings[0], (self.root / "postmortem" / "2026-10-10.md").read_text())

    def test_the_monthly_review_joins_the_public_page(self):
        out = self.run_job(due=FIRST, settings={"postmortem": {"model": False}})
        text = self.gateway.posts[0][1]["content"]
        self.assertEqual(SB.public_problems(text), [])
        self.assertIn("Proposal (D6): keep the Standard plan.", text)
        self.assertEqual(out["cost_review"], "keep_standard")

    def test_without_the_docs_route_the_page_is_kept_and_the_run_is_skipped(self):
        gateway = FakeGateway(post_error=GatewayError("POST /v1/github/docs: HTTP 404", status=404))
        out = self.run_job(gateway=gateway, settings={"postmortem": {"model": False}})
        self.assertEqual(out["status"], "skipped")
        self.assertTrue((self.root / "postmortem" / "2026-10-10-public.md").exists())
        self.assertTrue((self.root / "postmortem" / "2026-10-10.md").exists())

    def test_another_gateway_error_fails_the_run_after_the_report_is_written(self):
        gateway = FakeGateway(post_error=GatewayError("POST /v1/github/docs: HTTP 429", status=429))
        with self.assertRaises(GatewayError):
            self.run_job(gateway=gateway, settings={"postmortem": {"model": False}})
        self.assertTrue((self.root / "postmortem" / "2026-10-10.md").exists())

    def test_a_page_that_fails_the_filter_is_never_posted(self):
        with mock.patch.object(PM, "public_page", return_value=("the account equity is 1300", False)):
            with self.assertRaises(ValueError):
                self.run_job(settings={"postmortem": {"model": False}})
        self.assertEqual(self.gateway.posts, [])

    def test_ops_json_can_keep_the_page_private(self):
        out = self.run_job(settings={"postmortem": {"model": False, "public": False}})
        self.assertEqual(self.gateway.posts, [])
        self.assertIsNone(out["posted"])

    def test_the_private_files_are_owner_only(self):
        self.run_job(settings={"postmortem": {"model": False}})
        for name in ("2026-10-10.md", "2026-10-10.json", "2026-10-10-public.md"):
            self.assertEqual((self.root / "postmortem" / name).stat().st_mode & 0o777, 0o600, name)


if __name__ == "__main__":
    unittest.main()
