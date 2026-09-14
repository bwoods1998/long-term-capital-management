"""End-to-end synthetic research, mocked inference, real isolated paper journals."""

from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import hashlib
import inspect
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid
from portfolio_runtime import runner as r
from portfolio_runtime.research import (
    Research,
    grade_result,
    grade_allocation_v2,
    allocation_company_evidence,
    ALLOCATION_BODY_LIMIT,
    ALLOCATION_PROPOSAL_LIMIT,
    REQUEST_BODY_LIMIT,
    DECISION_OUTPUT_LIMIT,
    critic_packet,
)
from portfolio_runtime.provider import Client, canonical, body_for

CREATED = "2026-09-13T14:00:00Z"
AT = "2026-09-13T15:00:00Z"
EPOCH = datetime.fromisoformat(AT.replace("Z", "+00:00")).timestamp()


def evidence():
    companies = []
    for symbol in ("AAPL", "MSFT"):
        facts = {}
        for metric, tag, value in [
            ("operating_cash", "NetCashProvidedByUsedInOperatingActivities", 100),
            ("capital_spending", "PaymentsToAcquirePropertyPlantAndEquipment", 25),
            ("net_income", "NetIncomeLoss", 50),
        ]:
            facts[metric] = [
                {
                    "tag": tag,
                    "unit": "USD",
                    "observations": [
                        {"start": "2025-01-01", "end": "2025-12-31", "val": value}
                    ],
                }
            ]
        companies.append(
            {
                "symbol": symbol,
                "cik": "0000000001",
                "facts": facts,
                "source": "https://data.sec.gov/example.json",
                "sha256": "a" * 64,
            }
        )
    return {
        "companies": companies,
        "overview": [],
        "universe": {
            "id": "membership-test",
            "effective_at": CREATED,
            "captured_at": CREATED,
            "expires_at": "2026-09-20T00:00:00Z",
            "source": "https://example.com/universe",
            "companies": companies,
        },
    }


def answer(targets=None):
    company = evidence()["companies"][0]
    claims = []
    for metric, variants in company["facts"].items():
        variant = variants[0]
        obs = variant["observations"][0]
        claims.append(
            {
                "symbol": "AAPL",
                "metric": metric,
                "tag": variant["tag"],
                "start": obs["start"],
                "end": obs["end"],
                "value": obs["val"],
                "unit": "USD",
            }
        )
    return {
        "thesis": "Synthetic evidence suggests a business worth further research.",
        "claims": claims,
        "questions": [],
        "targets": targets or [],
        "confidence": "low",
        "abstain_reason": None,
    }


class ImmediatePool:
    def __init__(self, **kwargs):
        pass

    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future

    def shutdown(self, **kwargs):
        pass


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = evidence()
        self.at = EPOCH
        self.config = {
            "schema_version": 1,
            "run_id": "test-run",
            "state_dir": str(self.root / "state"),
            "evidence_path": str(self.root / "evidence.json"),
            "evidence_sha256": "",
            "started_epoch": EPOCH,
            "ends_epoch": EPOCH + 360,
            "inference_budget_usd": "10",
            "key_fingerprint": "a" * 64,
            "injected_auth": True,
            "account_created_at": CREATED,
            "drain_seconds": 60,
            "fetch_filings": False,
            "wave_seconds": 120,
            "min_wave_seconds": 30,
            "wave_size": 1,
            "max_concurrency": 1,
        }
        raw = canonical(self.data).encode()
        Path(self.config["evidence_path"]).write_bytes(raw)
        self.config["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
        self.research = Research(self.root / "research.sqlite", self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exhausted_ambiguous_requests_keep_holds_but_allow_another_profile(self):
        self.config.update(
            spending_mode="available_credit", max_concurrency=8, ends_epoch=EPOCH + 3600
        )
        calls = []

        def transport(method, path, body, identity):
            calls.append((method, body["model"]))
            return {"id": "resp_other", "status": "queued", "model": body["model"]}

        client = Client(
            self.root / "requests.sqlite",
            self.config,
            transport=transport,
            clock=lambda: self.at,
        )
        client.reservation_guard = lambda amount: True
        for i in range(8):
            task = "exhausted-" + str(i)
            self.research.add(
                task,
                0,
                "company",
                "AAPL",
                "kimi_flex",
                "source",
                "question",
                max_output=16,
            )
            with self.research.connect() as db:
                body = json.loads(
                    db.execute("SELECT body FROM tasks WHERE id=?", (task,)).fetchone()[
                        0
                    ]
                )
            identity = client.submit_intent(task, "kimi_flex", body)
            self.research.attach(task, identity)
        with client.connect() as db:
            db.execute(
                "UPDATE requests SET attempts=10,error='provider_transport_unconfirmed'"
            )
        before = client.rows()
        self.research.add(
            "same-profile",
            0,
            "company",
            "MSFT",
            "kimi_flex",
            "source",
            "question",
            max_output=16,
        )
        self.research.add(
            "other-profile",
            0,
            "company",
            "MSFT",
            "pro_asap",
            "source",
            "question",
            max_output=16,
        )
        with self.research.connect() as db:
            db.execute("INSERT INTO waves VALUES(0,?,?)", (self.at, "{}"))
        with (
            patch.object(
                r, "initialize", return_value=(client, self.research, self.ledger())
            ),
            patch.object(r, "ThreadPoolExecutor", ImmediatePool),
            patch.object(r.time, "time", side_effect=lambda: self.at),
            patch.object(r, "utc_now", return_value=AT),
        ):
            r.run(self.config, self.data, once=True)
        self.assertEqual(
            calls, [("POST", body_for("pro_asap", "", "", max_output=16)["model"])]
        )
        self.assertEqual(client.totals()["requests"], 9)
        after = {row["id"]: row for row in client.rows()}
        for old in before:
            self.assertEqual(after[old["id"]], old)
            self.assertIsNone(old["cost"])
        self.assertEqual(client.totals()["unsettled_requests"], 9)

    def test_final_live_attempt_and_accepted_flex_keep_slots_without_false_stall(self):
        rows = [
            {
                "id": "final",
                "profile": "kimi_flex",
                "status": "prepared",
                "response_id": None,
                "attempts": 10,
                "created": EPOCH,
            },
            {
                "id": "accepted",
                "profile": "kimi_flex",
                "status": "queued",
                "response_id": "resp_flex",
                "attempts": 50,
                "created": EPOCH,
            },
            {
                "id": "never-sent",
                "profile": "pro_asap",
                "status": "prepared",
                "response_id": None,
                "attempts": 0,
                "created": EPOCH - 86400,
            },
        ]
        work = r.request_schedule(rows, at=EPOCH + 60, live_ids={"final"})
        self.assertEqual(work["occupied"], {"final", "accepted", "never-sent"})
        self.assertEqual(work["exhausted"], [])
        self.assertEqual(work["blocked_profiles"], set())
        settled_attempt = r.request_schedule(rows, at=EPOCH + 60)
        self.assertEqual(settled_attempt["occupied"], {"accepted", "never-sent"})
        self.assertEqual(settled_attempt["blocked_profiles"], {"kimi_flex"})
        aged = r.request_schedule([{**rows[0], "attempts": 1}], at=EPOCH + 86400)
        self.assertEqual(len(aged["exhausted"]), 1)

    def test_new_window_triplets_share_16384_output_bound_and_preserve_prior_intents(
        self,
    ):
        from portfolio_runtime.evaluation import _window_body

        self.research.add(
            "prior-window",
            0,
            "window_pair",
            "AAPL",
            "kimi_flex",
            "old source",
            "old question",
            max_output=8192,
        )
        with self.research.connect() as db:
            previous = db.execute(
                "SELECT body FROM tasks WHERE id='prior-window'"
            ).fetchone()[0]
        self.research.plan_wave(1, size=1)
        with self.research.connect() as db:
            bodies = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT body FROM tasks WHERE kind='window_pair' AND wave=1"
                )
            ]
            self.assertEqual(
                db.execute("SELECT body FROM tasks WHERE id='prior-window'").fetchone()[
                    0
                ],
                previous,
            )
        self.assertEqual(len(bodies), 3)
        self.assertEqual({body["max_output_tokens"] for body in bodies}, {16384})
        self.assertEqual(len({canonical(_window_body(body)) for body in bodies}), 1)
        self.assertEqual(
            {body["metadata"]["completion_window"] for body in bodies},
            {"asap", "balanced", "flex"},
        )

    def test_full_constituent_evidence_over_eight_megabytes_preserves_every_source_observation(
        self,
    ):
        from portfolio_runtime.evidence import TAGS

        data = evidence()
        companies = []
        for i in range(503):
            ticker = "".join(chr(65 + (i // divisor) % 26) for divisor in (676, 26, 1))
            company = deepcopy(data["companies"][0])
            company.update(
                symbol=ticker, cik=str(i + 1).zfill(10), captured_at=AT, cutoff=AT[:10]
            )
            company["facts"] = {
                metric: [
                    {
                        "tag": tags[0],
                        "unit": "shares" if metric == "shares" else "USD",
                        "observations": [
                            {
                                "start": f"{year}-01-01",
                                "end": f"{year}-12-31",
                                "val": 1000000000 + year + i,
                                "filed": f"{year + 1}-02-15",
                                "form": "10-K",
                                "accn": f"0000000001-{year % 100:02}-000001",
                                "fy": year,
                                "fp": "FY",
                                "period_kind": "annual",
                            }
                            for year in range(2020, 2026)
                        ],
                    }
                ]
                for metric, tags in TAGS.items()
            }
            companies.append(company)
        data["companies"] = companies
        data["universe"]["companies"] = [
            {"symbol": c["symbol"], "cik": c["cik"]} for c in companies
        ]
        raw = (json.dumps(data, sort_keys=True, indent=2) + "\n").encode()
        self.assertGreater(len(raw), 8_000_000)
        self.assertLess(len(raw), r.MAX_EVIDENCE_BYTES)
        Path(self.config["evidence_path"]).write_bytes(raw)
        self.config["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
        path = self.root / "config.json"
        path.write_text(canonical(self.config))
        config, restored = r.read_config(path)
        self.assertEqual(config["evidence_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(restored, data)
        research = Research(self.root / "full-research.sqlite", restored)
        research.plan_wave(0, size=1)
        self.assertEqual(len(research.companies), 503)
        self.assertTrue(
            all(len(task["body"].encode()) <= 500000 for task in research.waiting())
        )

    def test_evidence_size_and_hash_failures_are_distinct_and_bounded(self):
        path = self.root / "config.json"
        path.write_text(canonical(self.config))
        evidence_path = Path(self.config["evidence_path"])
        with evidence_path.open("ab") as source:
            source.write(b" ")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            r.read_config(path)
        with evidence_path.open("wb") as source:
            source.seek(r.MAX_EVIDENCE_BYTES)
            source.write(b" ")
        with self.assertRaisesRegex(ValueError, "exceeds 32 MiB"):
            r.read_config(path)

    def completed(self, task_id, result, *, kind="company", wave=0):
        with self.research.connect() as db:
            old = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not old:
            self.research.add(
                task_id,
                wave,
                kind,
                "AAPL" if kind == "company" else None,
                "pro_flex",
                "evidence",
                "question",
            )
        identity = "pa-" + str(uuid.uuid4())
        self.research.attach(task_id, identity)
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": canonical(result)}],
                }
            ]
        }
        request = {
            "id": identity,
            "response": canonical(response),
            "status": "completed",
        }
        self.research.complete(request)
        return request

    def checked_allocation(self, verdict="approve", targets=None, wave=0):
        result = answer(
            targets if targets is not None else [{"symbol": "AAPL", "weight": "0.10"}]
        )
        name = f"w{wave:02}-allocation"
        self.completed(name, result, kind="allocation", wave=wave)
        with self.research.connect() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=?", (f"w{wave:02}-critic",)
            ).fetchone()
            self.assertIsNotNone(row)
            packet = json.loads(json.loads(row["body"])["input"][-1]["content"])
        self.assertEqual(packet["proposal"], result)
        critique = answer()
        critique.update(
            review_verdict=verdict,
            proposal_sha256=hashlib.sha256(canonical(result).encode()).hexdigest(),
        )
        self.completed(
            f"w{wave:02}-critic", critique, kind="portfolio_critic", wave=wave
        )
        return name

    def ledger(self):
        from portfolio_runtime import PortfolioLedger, UniverseSnapshot

        ledger = PortfolioLedger(self.root / "paper.sqlite", created_at=CREATED)
        u = self.data["universe"]
        ledger.register_universe(
            UniverseSnapshot(
                u["id"],
                u["effective_at"],
                u["captured_at"],
                tuple(c["symbol"] for c in u["companies"]),
                u["source"],
                u["expires_at"],
            )
        )
        return ledger

    def test_distinct_exact_source_claims_and_malformed_results_fail_without_crashing(
        self,
    ):
        companies = self.research.companies
        good = answer()
        self.assertTrue(grade_result(good, companies)["source_check_passed"])
        duplicate = answer()
        duplicate["claims"] = [
            good["claims"][0],
            deepcopy(good["claims"][0]),
            deepcopy(good["claims"][0]),
        ]
        duplicate["claims"][1]["value"] = "100.0"
        self.assertIn("duplicate_claim", grade_result(duplicate, companies)["errors"])
        for key in good:
            for bad in (None, True, [], {}, "wrong", float("nan")):
                data = deepcopy(good)
                data[key] = bad
                grade = grade_result(data, companies)
                self.assertIsInstance(grade["source_check_passed"], bool)
        for key in good["claims"][0]:
            bad = deepcopy(good)
            bad["claims"][0][key] = {}
            self.assertFalse(grade_result(bad, companies)["source_check_passed"])
        bad = answer()
        bad["questions"] = [{"symbol": {}, "question": "why", "priority": 1}]
        self.assertFalse(grade_result(bad, companies)["source_check_passed"])

    def test_bad_questions_do_not_break_followup_selection(self):
        bad = answer()
        bad["questions"] = None
        self.completed("bad", bad)
        self.assertTrue(self.research.choose(1))

    def test_wave_materialization_rolls_back_as_a_unit_and_cache_pair_matches(self):
        original = self.research.add
        calls = [0]

        def crash(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError("crash")
            return original(*args, **kwargs)

        with (
            patch.object(self.research, "add", side_effect=crash),
            self.assertRaises(RuntimeError),
        ):
            self.research.plan_wave(1, size=2, cache_ready=True)
        self.assertEqual(self.research.waiting(), [])
        self.research.plan_wave(1, size=2, cache_ready=True)
        before = self.research.waiting()
        self.research.plan_wave(1, size=2, cache_ready=True)
        self.assertEqual(self.research.waiting(), before)
        treatment = next(t for t in before if t["kind"] == "company")
        control = next(
            t
            for t in before
            if t["kind"] == "cache_control" and t["symbol"] == treatment["symbol"]
        )
        a = json.loads(treatment["body"])
        b = json.loads(control["body"])
        self.assertEqual(a["input"][-1], b["input"][-1])
        self.assertEqual(
            a["input"][0]["content"].split("\n", 1)[1],
            b["input"][0]["content"].split("\n", 1)[1],
        )
        self.assertNotEqual(a["prompt_cache_key"], b["prompt_cache_key"])

    def test_critic_is_dependent_and_rejection_cannot_promote(self):
        self.checked_allocation("revise")
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(ledger.public_state()["pending_decisions"], [])
        with self.research.connect() as db:
            self.assertEqual(
                db.execute("SELECT status FROM decisions").fetchone()[0],
                "revision_requested",
            )

    def test_primary_allocation_evidence_reaches_the_exact_dependent_critic(self):
        company = self.research.companies["AAPL"]
        company.update(captured_at=AT, cutoff=AT[:10])
        quote = {
            "symbol": "AAPL",
            "price": "100.25",
            "currency": "USD",
            "as_of": "2026-09-11T20:00:00Z",
            "captured_at": AT,
            "price_kind": "daily_close",
            "adjusted": False,
            "source": "https://query1.finance.yahoo.com/example",
            "source_sha256": "b" * 64,
        }
        company["research_price"] = quote
        annual = company["facts"]["operating_cash"][0]["observations"][0]
        annual.update(
            period_kind="annual",
            filed="2026-02-01",
            form="10-K",
            accn="0000000001-26-000001",
        )
        interim = {
            **annual,
            "start": "2026-01-01",
            "end": "2026-06-30",
            "val": 60,
            "period_kind": "year_to_date_or_other",
            "filed": "2026-08-01",
            "form": "10-Q",
            "accn": "0000000001-26-000002",
        }
        company["facts"]["operating_cash"][0]["observations"].append(interim)
        quarter = {
            **interim,
            "start": "2026-04-01",
            "val": 35,
            "period_kind": "quarter",
        }
        company["facts"]["operating_cash"][0]["observations"].append(quarter)
        self.research.portfolio_context = {
            "holdings": [],
            "pending_decisions": [
                {"id": "pending", "targets": [{"symbol": "MSFT", "weight": "0.10"}]}
            ],
        }
        self.completed("company-AAPL", answer())
        original_evidence = canonical(self.research.evidence)
        self.research.plan_wave(1, size=1)
        with self.research.connect() as db:
            before = db.execute(
                "SELECT body FROM tasks WHERE id='w01-allocation'"
            ).fetchone()[0]
        packet = json.loads(json.loads(before)["input"][-1]["content"])
        self.assertEqual(json.loads(before)["max_output_tokens"], DECISION_OUTPUT_LIMIT)
        self.assertEqual(packet["allocation_evidence_version"], 2)
        sources = {row["symbol"]: row for row in packet["candidate_evidence"]}
        self.assertEqual(sources["AAPL"]["research_price"], quote)
        self.assertIsNone(sources["MSFT"]["research_price"])
        self.assertEqual(sources["AAPL"]["sha256"], company["sha256"])
        self.assertEqual(
            [
                row["observations"][0]
                for row in sources["AAPL"]["facts"]["operating_cash"]
            ],
            [annual, interim, quarter],
        )
        self.assertEqual(canonical(self.research.evidence), original_evidence)
        self.completed(
            "w01-allocation",
            answer([{"symbol": "AAPL", "weight": "0.10"}]),
            kind="allocation",
            wave=1,
        )
        with self.research.connect() as db:
            critic = json.loads(
                db.execute("SELECT body FROM tasks WHERE id='w01-critic'").fetchone()[0]
            )
            self.assertEqual(
                db.execute(
                    "SELECT body FROM tasks WHERE id='w01-allocation'"
                ).fetchone()[0],
                before,
            )
        original_input = json.loads(critic["input"][-1]["content"])["original_input"]
        self.assertEqual(original_input, packet)
        self.assertEqual(critic["max_output_tokens"], DECISION_OUTPUT_LIMIT)

    def test_existing_allocation_keeps_its_original_critic_output_allowance(self):
        self.research.add(
            "w00-allocation", 0, "allocation", None, "pro_asap",
            self.research.decision_prefix(),
            canonical(self.research.allocation_packet([])), max_output=16384,
        )
        result = answer([{"symbol": "AAPL", "weight": "0.10"}])
        completed = self.completed("w00-allocation", result, kind="allocation", wave=0)
        with self.research.connect() as db:
            before = db.execute("SELECT body FROM tasks WHERE id='w00-critic'").fetchone()[0]
        self.assertEqual(json.loads(before)["max_output_tokens"], 16384)
        self.research.complete(completed)
        with self.research.connect() as db:
            self.assertEqual(db.execute("SELECT body FROM tasks WHERE id='w00-critic'").fetchone()[0], before)

    def test_target_claim_requirement_applies_only_to_new_allocation_protocol(self):
        self.research.add(
            "w00-allocation",
            0,
            "allocation",
            None,
            "pro_flex",
            "evidence",
            canonical({"task": "allocation"}),
        )
        legacy = self.checked_allocation(targets=[{"symbol": "MSFT", "weight": "0.10"}])
        with self.research.connect() as db:
            before = tuple(
                db.execute(
                    "SELECT body,grade FROM tasks WHERE id=?", (legacy,)
                ).fetchone()
            )
        self.assertTrue(json.loads(before[1])["source_check_passed"])
        self.completed("company-AAPL", answer())
        self.research.plan_wave(1, size=1)
        unsupported = answer([{"symbol": "MSFT", "weight": "0.10"}])
        self.completed("w01-allocation", unsupported, kind="allocation", wave=1)
        with self.research.connect() as db:
            grade = json.loads(
                db.execute(
                    "SELECT grade FROM tasks WHERE id='w01-allocation'"
                ).fetchone()[0]
            )
            self.assertEqual(grade["errors"], ["target_without_filed_claim"])
            self.assertIsNone(
                db.execute("SELECT id FROM tasks WHERE id='w01-critic'").fetchone()
            )
            self.assertEqual(
                tuple(
                    db.execute(
                        "SELECT body,grade FROM tasks WHERE id=?", (legacy,)
                    ).fetchone()
                ),
                before,
            )
        self.research.plan_wave(2, size=1)
        supported = deepcopy(unsupported)
        supported["claims"].append({**supported["claims"][0], "symbol": "MSFT"})
        self.completed("w02-allocation", supported, kind="allocation", wave=2)
        with self.research.connect() as db:
            self.assertTrue(
                json.loads(
                    db.execute(
                        "SELECT grade FROM tasks WHERE id='w02-allocation'"
                    ).fetchone()[0]
                )["source_check_passed"]
            )
            self.assertIsNotNone(
                db.execute("SELECT id FROM tasks WHERE id='w02-critic'").fetchone()
            )
        supported["claims"][-1]["value"] = 999
        grade = grade_allocation_v2(supported, self.research.companies)
        self.assertIn("source_mismatch", grade["errors"])
        self.assertIn("target_without_filed_claim", grade["errors"])
        following = Research(
            self.root / "following-research.sqlite", self.research.evidence
        )
        following.carry_history([self.research.path])
        with following.connect() as db:
            grades = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT grade FROM prior_work WHERE kind='allocation'"
                )
            ]
        self.assertEqual(sum(grade["source_check_passed"] for grade in grades), 2)
        self.assertEqual(
            sum("target_without_filed_claim" in grade["errors"] for grade in grades), 1
        )

    def test_allocation_context_bound_preserves_sources_and_actual_outcome_feedback(
        self,
    ):
        checked = [
            {
                "symbol": "AAPL",
                "result": {**answer(), "thesis": "Earlier narrative. " * 800},
                "research_id": str(i),
            }
            for i in range(36)
        ]
        outcomes = [
            {
                "decision_id": "earlier",
                "market_as_of": AT,
                "benchmark_status": "unavailable",
            }
        ]
        self.research.investment_outcomes = outcomes
        prefix = "Frozen source context. " * 10000
        with patch.object(self.research, "decision_prefix", return_value=prefix):
            packet = self.research.allocation_packet(checked)
        self.assertGreater(packet["context_omissions"]["checked_reviews"], 0)
        self.assertEqual(packet["observed_investment_outcomes"], outcomes)
        self.assertEqual(
            packet["candidate_evidence"][0],
            allocation_company_evidence(self.research.companies["AAPL"]),
        )
        body = body_for(
            self.research.allocation_profile,
            prefix,
            canonical(packet),
            max_output=DECISION_OUTPUT_LIMIT,
        )
        self.assertLessEqual(len(canonical(body).encode()), ALLOCATION_BODY_LIMIT)
        # A maximally escaped permitted proposal still fits its dependent
        # critic; the original evidence remains an object, never serialized twice.
        proposal = "\\" * ((ALLOCATION_PROPOSAL_LIMIT - 2) // 2)
        self.assertEqual(len(canonical(proposal).encode()), ALLOCATION_PROPOSAL_LIMIT)
        critic = body_for(
            "k3",
            prefix,
            canonical(critic_packet("a" * 64, proposal, packet)),
            max_output=DECISION_OUTPUT_LIMIT,
        )
        self.assertLessEqual(len(canonical(critic).encode()), REQUEST_BODY_LIMIT)
        self.assertEqual(
            json.loads(critic["input"][-1]["content"])["original_input"], packet
        )
        self.assertEqual(len(checked), 36)

    def test_new_allocation_proposal_bound_does_not_regrade_legacy_outputs(self):
        result = answer([{"symbol": "AAPL", "weight": "0.10"}])
        # The old numeric checker permits alternative representations of the
        # exact same value; their size cannot consume the critic's envelope.
        result["claims"][0]["value"] = "0" * ALLOCATION_PROPOSAL_LIMIT + "100"
        self.assertTrue(
            grade_result(result, self.research.companies, allocation=True)[
                "source_check_passed"
            ]
        )
        grade = grade_allocation_v2(result, self.research.companies)
        self.assertEqual(grade["errors"], ["proposal_envelope_exceeded"])

    def test_service_reopens_the_pre_v2_frozen_policy_evaluator(self):
        from portfolio_runtime.service import Service
        from portfolio_runtime.improvement import PolicyLab

        # These hashes are from the completed rehearsal's immutable contract
        # and grade_result at 1a8b88c. Allocation-only gates must not migrate it.
        self.assertEqual(
            hashlib.sha256(inspect.getsource(grade_result).encode()).hexdigest(),
            "813258b822db8d15f69e0b39923150d552d41dc20b836c6d619b05371b829c13",
        )
        frozen = {
            "evaluator_sha256": "4a67ad5712fed9d4f53f13bf5830b8438fdec57f54f11069f9de528e06d140d5",
            "system_sha256": "ae0e4b73e0042e406bb65a75662ab004629df3b50dabc5607f8fffe8717ff57a",
            "policies": {"fresh": {"memory_limit": 0}, "memory_3": {"memory_limit": 3}},
            "rules": {
                "family_alpha": "0.01",
                "holdout_modulus": 5,
                "max_cost_ratio": "2",
                "max_non_improving_looks": 2,
                "max_output": 8192,
                "max_promotions": 1,
                "max_rollbacks": 1,
                "min_dates": 2,
                "min_net_wins": 5,
                "min_pass_rate": "0.90",
                "pairs_per_look": 20,
                "profile": "kimi_asap",
                "selection_pairs_per_day": 10,
                "version": 1,
            },
        }
        state = self.root / "restored-service"
        state.mkdir()
        path = state / "improvement.sqlite"
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE policy_contract(id INTEGER PRIMARY KEY,body TEXT NOT NULL)"
            )
            db.execute("INSERT INTO policy_contract VALUES(1,?)", (canonical(frozen),))
            db.execute(
                "CREATE TABLE policies(version INTEGER PRIMARY KEY,name TEXT NOT NULL,action TEXT NOT NULL,at TEXT NOT NULL,decision TEXT)"
            )
            db.execute(
                "INSERT INTO policies VALUES(0,'memory_3','initial',?,NULL)", (AT,)
            )
        config = {
            "state_dir": str(state),
            "spending_mode": "available_credit",
            "week_starts_at": "2026-09-14T04:00:00Z",
            "week_ends_at": "2026-09-19T04:00:00Z",
            "account_created_at": CREATED,
            "session_seconds": 3600,
            "voyage_id": "voy_fixture",
        }
        # Exercise the production service initialization and real PolicyLab;
        # external tracing is isolated and no epoch/inference is launched.
        service = Service(
            config, clock=lambda: EPOCH, trace_factory=lambda *_: object()
        )
        service.initialize()
        self.assertIsInstance(service.lab, PolicyLab)
        self.assertEqual(
            service.lab.policy(), {"version": 0, "name": "memory_3", "memory_limit": 3}
        )
        service.initialize()
        with sqlite3.connect(path) as db:
            self.assertEqual(
                db.execute("SELECT body FROM policy_contract").fetchone()[0],
                canonical(frozen),
            )
            self.assertEqual(
                db.execute("SELECT version,name,action,at FROM policies").fetchall(),
                [(0, "memory_3", "initial", AT)],
            )
        with patch(
            "portfolio_runtime.improvement.inspect.getsource",
            return_value="changed evaluator",
        ):
            with self.assertRaisesRegex(ValueError, "Frozen policy evaluator changed"):
                PolicyLab(path)

    def test_changed_quote_keeps_coverage_priority_on_unreviewed_companies(self):
        company = self.research.companies["AAPL"]
        old_company = {
            **company,
            "research_price": {"price": "100", "as_of": AT, "currency": "USD"},
        }
        question = "Assess the business economics, cash generation, balance-sheet resilience and missing valuation evidence. Identify what would change an investment decision."
        self.research.add(
            "prior-AAPL",
            0,
            "company",
            "AAPL",
            "pro_flex",
            "context",
            canonical({"evidence": old_company, "question": question}),
        )
        self.completed("prior-AAPL", answer())
        updated = deepcopy(self.data)
        updated["companies"][0]["research_price"] = {
            "price": "105",
            "as_of": "2026-09-13T15:05:00Z",
            "currency": "USD",
        }
        following = Research(self.root / "following.sqlite", updated)
        following.carry_history([self.research.path])
        following.bounded_novelty = True
        self.assertNotEqual(
            following.source_fingerprint(old_company),
            following.source_fingerprint(following.companies["AAPL"]),
        )
        choices = following.choose(2)
        self.assertEqual(choices[0][0], "MSFT")
        self.assertEqual({symbol for symbol, _ in choices}, {"MSFT", "AAPL"})

    def test_oversized_new_allocation_stays_unadmitted_without_stopping_research(self):
        self.completed("company-AAPL", answer())
        with patch.object(self.research, "decision_prefix", return_value="x" * 500000):
            self.research.plan_wave(1, size=1)
        with self.research.connect() as db:
            task = db.execute(
                "SELECT status,grade,request_id FROM tasks WHERE id='w01-allocation'"
            ).fetchone()
        self.assertEqual(task["status"], "failed")
        self.assertEqual(
            json.loads(task["grade"])["errors"], ["request_envelope_exceeded"]
        )
        self.assertIsNone(task["request_id"])
        self.assertTrue(
            any(task["kind"] == "company" for task in self.research.waiting())
        )
        self.assertFalse(
            any(task["kind"] == "allocation" for task in self.research.waiting())
        )

    def test_memory_pairs_use_first_three_eligible_followups_after_coverage_slots(self):
        symbols = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOG", "META", "AVGO"]
        for symbol in symbols:
            self.research.companies[symbol] = {
                **deepcopy(self.data["companies"][0]),
                "symbol": symbol,
            }
        history = [{"result": answer(), "grade": {"source_check_passed": True}}]

        def latest(symbol=None, limit=12):
            return history if symbol in symbols[3:] else []

        with (
            patch.object(
                self.research,
                "choose",
                return_value=[(symbol, "Review evidence") for symbol in symbols],
            ),
            patch.object(self.research, "latest", side_effect=latest),
        ):
            self.research.plan_wave(1, size=7, cache_ready=True)
        tasks = self.research.waiting()
        controls = [task for task in tasks if task["kind"] == "fresh_review"]
        self.assertEqual([task["symbol"] for task in controls], symbols[3:6])
        for control in controls:
            company = next(
                task
                for task in tasks
                if task["kind"] == "company" and task["symbol"] == control["symbol"]
            )
            a, b = json.loads(company["body"]), json.loads(control["body"])
            original = json.loads(a["input"][-1]["content"])
            fresh = json.loads(b["input"][-1]["content"])
            self.assertEqual(original.pop("prior_work"), history)
            self.assertEqual(fresh.pop("prior_work"), [])
            self.assertEqual(original, fresh)
            a["input"][-1]["content"] = b["input"][-1]["content"]
            self.assertEqual(a, b)

    def test_oversized_dependent_critic_is_retained_failed_and_recovered(self):
        self.research.add(
            "w00-allocation",
            0,
            "allocation",
            None,
            "pro_flex",
            "evidence",
            "x" * 210000,
        )
        with patch.object(self.research, "prefix", return_value="context " * 40000):
            request = self.completed("w00-allocation", answer(), kind="allocation")
            with self.research.connect() as db:
                allocation = db.execute(
                    "SELECT body FROM tasks WHERE id='w00-allocation'"
                ).fetchone()[0]
                critic = dict(
                    db.execute("SELECT * FROM tasks WHERE id='w00-critic'").fetchone()
                )
                self.assertLess(len(allocation.encode()), 500000)
                self.assertGreater(len(critic["body"].encode()), 500000)
                self.assertEqual(critic["status"], "failed")
                self.assertEqual(
                    json.loads(critic["grade"])["errors"], ["request_envelope_exceeded"]
                )
                # A pre-fix crash could leave the same immutable prompt waiting.
                db.execute(
                    "UPDATE tasks SET status='waiting',grade=NULL WHERE id='w00-critic'"
                )
            self.research.complete(request)
        with self.research.connect() as db:
            recovered = dict(
                db.execute("SELECT * FROM tasks WHERE id='w00-critic'").fetchone()
            )
        self.assertEqual(recovered["body"], critic["body"])
        self.assertEqual(recovered["status"], "failed")
        self.assertNotIn("w00-critic", [task["id"] for task in self.research.waiting()])

    def test_approved_targets_and_hold_cash_supersede_without_stacking(self):
        first = self.checked_allocation()
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(ledger.public_state()["pending_decisions"][0]["id"], first)
            second = self.checked_allocation(targets=[], wave=1)
            r.propose_checked(self.config, self.research, ledger)
            pending = ledger.public_state()["pending_decisions"]
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["id"], second)
            self.assertEqual(pending[0]["targets"], [])
            stub = SimpleNamespace(
                totals=lambda: {
                    "unsettled_requests": 0,
                    "known_cost_usd": "0",
                    "completed": 0,
                    "requests": 0,
                    "committed_usd": "0",
                }
            )
            view = r.public_projection(self.config, ledger, self.research, stub)
            self.assertEqual(view["latest_decision"]["action"], "hold")
            self.assertTrue(view["latest_decision"]["sources"])

    def test_crash_after_paper_commit_replays_frozen_decision_time(self):
        name = self.checked_allocation()
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            original = ledger.propose

            def crash(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError("after ledger commit")

            with (
                patch.object(ledger, "propose", side_effect=crash),
                self.assertRaises(RuntimeError),
            ):
                r.propose_checked(self.config, self.research, ledger)
            with patch.object(r, "utc_now", return_value="2026-09-13T15:05:00Z"):
                r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(
                len([e for e in ledger.events() if e["kind"] == "decision"]), 1
            )
            self.assertEqual(
                ledger.public_state()["pending_decisions"][0]["decided_at"], AT
            )

    def test_reaffirmed_allocation_has_new_review_time_without_a_new_order(self):
        targets = [
            {"symbol": "AAPL", "weight": "0.10"},
            {"symbol": "MSFT", "weight": "0.15"},
        ]
        self.checked_allocation(targets=targets, wave=0)
        client = SimpleNamespace(
            totals=lambda: {
                "unsettled_requests": 0,
                "known_cost_usd": "0",
                "completed": 0,
                "requests": 0,
                "committed_usd": "0",
            }
        )
        reviewed_at = "2026-09-13T15:05:00Z"
        with self.ledger() as ledger:
            with patch.object(r, "utc_now", return_value=AT):
                r.propose_checked(self.config, self.research, ledger)
                first = r.public_projection(self.config, ledger, self.research, client)
            original_state, original_events = ledger.public_state(), ledger.events()
            self.assertEqual(first["latest_decision"]["action"], "rebalance")
            # Equivalent decimal spellings are the same target allocation.
            targets[0]["weight"] = "0.100"
            self.checked_allocation(targets=targets, wave=1)
            with patch.object(r, "utc_now", return_value=reviewed_at):
                r.propose_checked(self.config, self.research, ledger)
                view = r.public_projection(self.config, ledger, self.research, client)
            self.assertEqual(ledger.events(), original_events)
            self.assertEqual(view["portfolio"], original_state)
            self.assertEqual(
                view["portfolio"]["pending_decisions"][0]["decided_at"], AT
            )
            self.assertEqual(view["latest_decision"]["at"], reviewed_at)
            self.assertEqual(view["latest_decision"]["action"], "hold")
            self.assertEqual(
                view["latest_decision"]["summary"],
                "Reaffirmed the existing target allocation.",
            )
            self.assertTrue(view["latest_decision"]["sources"])

    def test_older_approved_wave_cannot_overwrite_newer_paper_allocation(self):
        self.checked_allocation(wave=0)
        newest = self.checked_allocation(
            targets=[{"symbol": "MSFT", "weight": "0.15"}], wave=1
        )
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            r.propose_checked(self.config, self.research, ledger)
            r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(
                [row["id"] for row in ledger.public_state()["pending_decisions"]],
                [newest],
            )
            self.assertEqual(
                len([row for row in ledger.events() if row["kind"] == "decision"]), 1
            )

    def test_approved_paper_decision_is_promoted_during_drain_without_inference(self):
        name = self.checked_allocation()
        self.at = self.config["ends_epoch"] - 30
        client = Client(
            self.root / "requests.sqlite",
            self.config,
            transport=lambda *args: self.fail("Drain must not start inference"),
            clock=lambda: self.at,
        )
        ledger = self.ledger()
        with (
            patch.object(r, "initialize", return_value=(client, self.research, ledger)),
            patch.object(r, "ThreadPoolExecutor", ImmediatePool),
            patch.object(r.time, "time", side_effect=lambda: self.at),
            patch.object(r, "utc_now", side_effect=lambda: r.stamp(self.at)),
        ):
            r.run(self.config, self.data, once=True)
        saved = json.loads((Path(self.config["state_dir"]) / "public.json").read_text())
        self.assertEqual(saved["portfolio"]["pending_decisions"][0]["id"], name)
        self.assertEqual(client.totals()["requests"], 0)

    def test_latest_unchanged_allocation_also_supersedes_older_unprocessed_research(
        self,
    ):
        first = self.checked_allocation(wave=0)
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            r.propose_checked(self.config, self.research, ledger)
            self.checked_allocation(
                targets=[{"symbol": "MSFT", "weight": "0.15"}], wave=1
            )
            newest = self.checked_allocation(wave=2)
            r.propose_checked(self.config, self.research, ledger)
            r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(
                [row["id"] for row in ledger.public_state()["pending_decisions"]],
                [first],
            )
        with self.research.connect() as db:
            self.assertEqual(
                db.execute(
                    "SELECT status FROM decisions WHERE id=?", (newest,)
                ).fetchone()[0],
                "unchanged",
            )

    def test_critique_settled_at_shutdown_can_update_final_paper_state(self):
        self.at = self.config["ends_epoch"]
        client = Client(
            self.root / "requests.sqlite",
            self.config,
            transport=lambda *args: self.fail("Deadline must not start inference"),
            clock=lambda: self.at,
        )
        ledger = self.ledger()
        completed = self.checked_allocation

        class FinishingPool(ImmediatePool):
            def shutdown(self, **kwargs):
                completed()

        with (
            patch.object(r, "initialize", return_value=(client, self.research, ledger)),
            patch.object(r, "ThreadPoolExecutor", FinishingPool),
            patch.object(r.time, "time", side_effect=lambda: self.at),
            patch.object(r, "utc_now", side_effect=lambda: r.stamp(self.at)),
        ):
            r.run(self.config, self.data, once=True)
        saved = json.loads((Path(self.config["state_dir"]) / "public.json").read_text())
        self.assertEqual(
            saved["portfolio"]["pending_decisions"][0]["id"], "w00-allocation"
        )
        self.assertEqual(client.totals()["requests"], 0)

    def test_reconcile_recovers_mapping_and_terminal_before_new_work(self):
        self.research.add(
            "one", 0, "company", "AAPL", "kimi_flex", "evidence", "question"
        )
        task = self.research.waiting()[0]
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": canonical(answer())}],
                }
            ]
        }
        request = {
            "id": "pa-" + str(uuid.uuid4()),
            "task_id": "one",
            "body": task["body"],
            "profile": task["profile"],
            "cache": task["cache"],
            "status": "completed",
            "response": canonical(response),
        }
        self.research.reconcile([request])
        self.research.reconcile([request])
        self.assertEqual(self.research.summary()["tasks"], {"complete": 1})
        with self.assertRaises(ValueError):
            self.research.reconcile([{**request, "body": "{}"}])

    def test_report_retains_unknown_malformed_usage_and_cache_write_acceptance(self):
        row = {
            "profile": "kimi_flex",
            "response": canonical(
                {
                    "usage": {
                        "input_tokens": [],
                        "output_tokens": "wrong",
                        "input_tokens_details": [],
                    },
                    "metadata": {"supercached_input_tokens": "not-int"},
                }
            ),
            "cost": None,
            "status": "incomplete",
            "created": 1,
            "updated": 2,
        }
        client = SimpleNamespace(rows=lambda: [row], totals=lambda: {})
        result = r.report(self.config, client, self.research)
        self.assertEqual(result["profiles"]["kimi_flex"]["usage_unavailable"], 1)
        ack = {
            "task_id": "cache-write-v1",
            "status": "incomplete",
            "cost": ".5",
            "error": None,
            "response": canonical(
                {"metadata": {"supercache_write_input_tokens": "2048"}}
            ),
        }
        self.assertTrue(r.cache_write_confirmed(ack))
        self.assertFalse(r.cache_write_confirmed({**ack, "cost": None}))
        self.assertFalse(r.cache_write_confirmed({**ack, "status": "failed"}))

    def test_future_run_prepare_uses_stable_account_creation(self):
        config = {
            **self.config,
            "started_epoch": EPOCH + 3600,
            "ends_epoch": EPOCH + 3960,
        }
        client, research, ledger = r.initialize(config, self.data)
        try:
            self.assertEqual(ledger.public_state()["created_at"], CREATED)
        finally:
            ledger.close()

    def test_paced_loop_keeps_working_until_wallclock_deadline(self):
        calls = []

        def transport(method, route, body=None, request_id=None):
            self.assertEqual(method, "POST")
            try:
                packet = json.loads(body["input"][-1]["content"])
            except ValueError:
                packet = {"task": "cache_write"}
            result = answer()
            if packet.get("task") == "allocation":
                result["targets"] = [{"symbol": "AAPL", "weight": "0.1"}]
            if packet.get("task") == "portfolio_critic":
                result.update(
                    review_verdict="approve", proposal_sha256=packet["proposal_sha256"]
                )
            calls.append(request_id)
            return {
                "id": "resp_" + str(len(calls)),
                "status": "completed",
                "model": body["model"],
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": canonical(result)}],
                    }
                ],
                "metadata": {
                    "supercached_input_tokens": "0",
                    "supercache_write_input_tokens": "2048"
                    if packet["task"] == "cache_write"
                    else "0",
                },
                "usage": {
                    "input_tokens": 3000,
                    "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 0},
                },
            }

        def client_factory(path, config):
            client = Client(path, config, transport=transport, clock=lambda: self.at)

            def reject_full_snapshot():
                raise AssertionError(
                    "The run must not materialize every historical prompt"
                )

            client.rows = reject_full_snapshot
            return client

        def sleep(seconds):
            self.at += seconds

        with (
            patch.object(r, "Client", side_effect=client_factory),
            patch.object(r, "ThreadPoolExecutor", ImmediatePool),
            patch.object(r.time, "time", side_effect=lambda: self.at),
            patch.object(r.time, "sleep", side_effect=sleep),
            patch.object(r, "utc_now", side_effect=lambda: r.stamp(self.at)),
        ):
            report = r.run(self.config, self.data)
        self.assertGreaterEqual(self.at, self.config["ends_epoch"])
        self.assertGreater(len(calls), 4)
        self.assertEqual(len(calls), len(set(calls)))
        self.assertGreaterEqual(report["elapsed_seconds"], 360)
        saved = json.loads((Path(self.config["state_dir"]) / "public.json").read_text())
        self.assertEqual(saved["research"]["status"], "complete")

    def test_publication_same_second_conflict_waits_for_actual_time(self):
        from urllib.error import HTTPError

        calls = []
        opened = SimpleNamespace()

        class Success:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        def open_request(request, **kwargs):
            calls.append(json.loads(request.data))
            if len(calls) == 1:
                raise HTTPError(request.full_url, 409, "same timestamp", {}, None)
            return Success()

        opened.open = open_request
        config = {
            **self.config,
            "publish_url": "https://blakewoods.us/api/portfolio/state",
        }
        projection = {"published_at": AT, "state": "complete"}

        def sleep(seconds):
            self.at += seconds

        with (
            patch.object(r, "build_opener", return_value=opened),
            patch.object(r.time, "time", side_effect=lambda: self.at),
            patch.object(r.time, "sleep", side_effect=sleep),
            patch.object(r, "utc_now", side_effect=lambda: r.stamp(self.at)),
        ):
            self.assertTrue(r.publish(config, projection))
        self.assertEqual(calls[0]["published_at"], AT)
        self.assertEqual(calls[1]["published_at"], "2026-09-13T15:00:01Z")
        self.assertTrue(
            json.loads(
                (Path(config["state_dir"]) / "publication-health.json").read_text()
            )["published"]
        )

    def test_primary_context_enters_new_requests_without_mutating_baseline(self):
        baseline = canonical(self.data)
        directory = self.root / "filings"
        directory.mkdir()
        calls = []

        def enrich(company, question):
            calls.append(company["symbol"])
            return {
                "source": "https://www.sec.gov/Archives/example.htm",
                "sha256": "b" * 64,
                "excerpts": [{"paragraph": 1, "text": "Synthetic new filing context"}],
            }

        filings = SimpleNamespace(directory=directory, enrich=enrich)
        self.research.plan_wave(0, size=2, filings=filings)
        companies = [t for t in self.research.waiting() if t["kind"] == "company"]
        self.assertEqual(len(calls), 2)
        for task in companies:
            self.assertIn(
                "filing_context",
                json.loads(json.loads(task["body"])["input"][-1]["content"])[
                    "evidence"
                ],
            )
        self.assertEqual(canonical(self.data), baseline)

    def test_oversized_request_is_retained_failed_without_provider_admission(self):
        self.data["overview"] = {"oversized": "x" * 500001}
        research = Research(self.root / "large.sqlite", self.data)
        research.plan_wave(0, size=1)
        self.assertEqual(research.waiting(), [])
        with research.connect() as db:
            rows = db.execute("SELECT status,grade FROM tasks").fetchall()
        self.assertTrue(rows)
        self.assertTrue(
            all(
                row["status"] == "failed"
                and "request_envelope_exceeded" in json.loads(row["grade"])["errors"]
                for row in rows
            )
        )

    def test_paper_command_cannot_submit_inference_or_grant_branch_authority(self):
        calls = []
        market = SimpleNamespace(
            fill_pending=lambda ledger: calls.append("fill")
            or {"status": "waiting_for_market"},
            mark_close=lambda ledger: calls.append("mark")
            or {"status": "no_positions"},
        )
        with (
            patch.object(
                Client, "step", side_effect=AssertionError("No inference allowed")
            ),
            patch.object(r.time, "time", return_value=EPOCH),
        ):
            result = r.paper(self.config, self.data, market=market)
        self.assertEqual(calls, ["fill", "mark"])
        self.assertTrue(result["paper_only"])
        self.assertEqual(result["portfolio"]["holdings"], [])
        with self.assertRaises(ValueError):
            r.paper({**self.config, "research_only": True}, self.data, market=market)
        with self.assertRaises(ValueError):
            r.run({**self.config, "research_only": True}, self.data, once=True)

    def test_critic_must_bind_the_exact_proposal(self):
        self.completed(
            "w00-allocation",
            answer([{"symbol": "AAPL", "weight": "0.1"}]),
            kind="allocation",
        )
        wrong = answer()
        wrong.update(review_verdict="approve", proposal_sha256="b" * 64)
        self.completed("w00-critic", wrong, kind="portfolio_critic")
        with self.ledger() as ledger, patch.object(r, "utc_now", return_value=AT):
            r.propose_checked(self.config, self.research, ledger)
            self.assertEqual(ledger.public_state()["pending_decisions"], [])

    def test_read_config_rejects_changed_evidence_and_invalid_bounds(self):
        path = self.root / "config.json"
        path.write_text(canonical(self.config))
        r.read_config(path)
        bad = {**self.config, "max_concurrency": 1000}
        path.write_text(canonical(bad))
        with self.assertRaises(ValueError):
            r.read_config(path)
        path.write_text(canonical(self.config))
        Path(self.config["evidence_path"]).write_text("{}")
        with self.assertRaises(ValueError):
            r.read_config(path)


if __name__ == "__main__":
    unittest.main()
