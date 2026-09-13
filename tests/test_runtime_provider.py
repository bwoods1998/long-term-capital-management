"""Isolated request ledgers and scripted provider responses; no paid work."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sqlite3
import json
import tempfile
import unittest
from unittest.mock import patch
from portfolio_runtime import provider as p
from portfolio_runtime.accounting import estimate_cost


class Script:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return deepcopy(reply)


def response(status="completed", model=None, usage=True):
    result = {
        "id": "resp_one",
        "status": status,
        "model": model or p.PROFILES["kimi_flex"][0],
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "{}"}]}
        ],
    }
    if usage:
        result["usage"] = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 400},
        }
    return result


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "requests.sqlite"
        self.at = 1000
        self.config = {
            "run_id": "frozen-run",
            "inference_budget_usd": "10",
            "started_epoch": 1000,
            "ends_epoch": 19000,
            "key_fingerprint": "a" * 64,
            "injected_auth": True,
            "drain_seconds": 300,
        }
        self.script = Script()
        self.client = p.Client(
            self.path, self.config, transport=self.script, clock=lambda: self.at
        )

    def tearDown(self):
        self.tmp.cleanup()

    def intent(self, key="one", **kwargs):
        return self.client.submit_intent(
            key,
            "kimi_flex",
            p.body_for("kimi_flex", "public evidence", "question", **kwargs),
            cache=kwargs.get("cache", "ordinary"),
        )

    def test_asap_only_models_and_injected_credential_boundaries(self):
        self.assertFalse(p.body_for("k3", "x", "y")["background"])
        self.assertFalse(p.body_for("flash", "x", "y")["background"])
        self.assertFalse(p.body_for("kimi_asap", "x", "y")["background"])
        self.assertFalse(p.body_for("pro_asap", "x", "y")["background"])
        self.assertTrue(p.body_for("kimi_flex", "x", "y")["background"])
        with self.assertRaises(ValueError):
            p.Transport(
                injected=True,
                key_fingerprint="a" * 64,
                headers={"Authorization": "never"},
            )
        with self.assertRaises(ValueError):
            p.Transport(injected=True)

    def test_explicit_pre_admission_rejection_settles_zero_and_does_not_repeat(self):
        self.script.replies = [p.SubmissionRejected("unsupported_asap_request")]
        identity = self.intent()
        row = self.client.step(identity)
        self.assertEqual((row["status"], row["cost"], row["response_id"]), ("failed", "0", None))
        self.assertEqual(self.client.totals()["unsettled_requests"], 0)
        self.client.step(identity)
        self.assertEqual(len(self.script.calls), 1)

    def test_generic_bad_request_cannot_release_an_uncertain_reservation(self):
        self.script.replies = [RuntimeError("provider_http_400")]
        identity = self.intent()
        row = self.client.step(identity)
        self.assertIsNone(row["cost"])
        self.assertEqual(self.client.totals()["unsettled_requests"], 1)

    def test_asap_requests_admit_synchronous_bodies(self):
        for name in ("kimi_asap", "pro_asap", "k3", "flash"):
            self.assertTrue(self.client.submit_intent(name, name, p.body_for(name, "facts", "question")))

    def test_external_spend_guard_blocks_new_reservations_but_preserves_recovery(self):
        identity = self.intent()
        observed = []
        self.client.reservation_guard = lambda amount: observed.append(amount) or False
        self.assertEqual(self.intent(), identity)
        self.assertEqual(observed, [])
        with self.assertRaises(p.AdmissionClosed):
            self.intent("new-task")
        self.assertEqual(len(observed), 1)
        self.assertGreater(observed[0], Decimal(0))
        self.assertEqual(self.client.totals()["requests"], 1)

    def test_available_credit_releases_full_snapshot_but_requires_live_reservation_authority(self):
        config = {**self.config, "spending_mode": "available_credit", "inference_budget_usd": "175.25"}
        client = p.Client(self.path.parent/"credit.sqlite", config, transport=self.script, clock=lambda: self.at)
        self.assertEqual(client.allowance(), Decimal("175.25"))
        body = p.body_for("k3", "source"*10000, "review", max_output=16384)
        with self.assertRaises(p.AdmissionClosed):
            client.submit_intent("critical", "k3", body)
        with self.assertRaises(p.AdmissionClosed):
            client.allocate("branch", "1")
        observed = []
        client.reservation_guard = lambda value: observed.append(value) or True
        identity = client.submit_intent("critical", "k3", body)
        self.assertGreater(observed[0], Decimal("0.3"))  # Old$2 initial release cannot fit this.
        client.reservation_guard = lambda value: False
        self.assertEqual(client.submit_intent("critical", "k3", body), identity)
        with self.assertRaises(p.AdmissionClosed):
            client.submit_intent("another", "k3", body)
        self.assertEqual(client.totals()["requests"], 1)
        with self.assertRaises(ValueError):
            p.Client(client.path, {**config, "spending_mode": "capped", "inference_budget_usd": "100"}, transport=self.script)

    def test_available_credit_snapshot_still_bounds_aggregate_reservations(self):
        config = {**self.config, "spending_mode": "available_credit", "inference_budget_usd": ".5"}
        client = p.Client(self.path.parent/"credit.sqlite", config, transport=self.script, clock=lambda: self.at)
        client.reservation_guard = lambda amount: True
        body = p.body_for("k3", "source"*10000, "review", max_output=16384)
        client.submit_intent("first", "k3", body)
        with self.assertRaises(p.AdmissionClosed):
            client.submit_intent("second", "k3", body)
        with self.assertRaises(ValueError):
            p.Client(client.path, {**config, "spending_mode": "capped"}, transport=self.script)

    def test_available_credit_rechecks_first_dispatch_but_preserves_ambiguous_and_accepted_recovery(self):
        config = {**self.config, "spending_mode": "available_credit"}
        client = p.Client(self.path.parent/"credit.sqlite", config, transport=self.script, clock=lambda: self.at)
        client.reservation_guard = lambda amount: True
        body = p.body_for("kimi_flex", "evidence", "question")
        identity = client.submit_intent("one", "kimi_flex", body)
        original = client.rows()[0]
        restarted = p.Client(client.path, config, transport=self.script, clock=lambda: self.at)
        self.assertEqual(restarted.step(identity), original)  # No restored authority yet.
        checked = []
        restarted.reservation_guard = lambda amount: checked.append(amount) or False
        self.assertEqual(restarted.step(identity), original)
        self.assertEqual(checked, [Decimal(0)])
        self.assertEqual(self.script.calls, [])
        restarted.reservation_guard = lambda amount: True
        self.script.replies = [TimeoutError("ambiguous"), response("queued"), response()]
        self.assertEqual(restarted.step(identity)["attempts"], 1)
        restarted.reservation_guard = lambda amount: self.fail("Already-attempted recovery must retain its identity")
        self.assertEqual(restarted.step(identity)["status"], "queued")
        self.assertEqual(restarted.step(identity)["status"], "completed")
        self.assertEqual([call[0] for call in self.script.calls], ["POST", "POST", "GET"])
        self.assertEqual(self.script.calls[0], self.script.calls[1])

    def test_available_credit_revoked_never_dispatched_hold_still_cancels_at_deadline(self):
        config = {**self.config, "spending_mode": "available_credit"}
        client = p.Client(self.path.parent/"credit.sqlite", config, transport=self.script, clock=lambda: self.at)
        client.reservation_guard = lambda amount: True
        identity = client.submit_intent("one", "kimi_flex", p.body_for("kimi_flex", "evidence", "question"))
        client.reservation_guard = lambda amount: False
        self.at = config["ends_epoch"]
        row = client.step(identity)
        self.assertEqual((row["status"], row["cost"], row["attempts"]), ("cancelled", "0", 0))
        self.assertEqual(self.script.calls, [])

    def test_never_dispatched_crash_gap_retires_at_drain_cutoff(self):
        identity = self.intent()
        self.at = self.config["ends_epoch"] + 86400
        row = self.client.step(identity)
        self.assertEqual((row["status"],row["cost"]), ("cancelled","0"))
        self.assertEqual(row["error"],"never_dispatched_before_deadline")
        self.assertEqual(self.script.calls, [])

    def test_intent_and_money_contract_are_immutable(self):
        identity = self.intent()
        self.assertEqual(self.intent(), identity)
        body = p.body_for("kimi_flex", "different", "question")
        with self.assertRaises(ValueError):
            self.client.submit_intent("one", "kimi_flex", body)
        with self.assertRaises(ValueError):
            p.Client(
                self.path,
                {**self.config, "inference_budget_usd": "11"},
                transport=self.script,
            )
        with self.client.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE requests SET reserved=? WHERE id=?", ("0", identity))
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE metadata SET value='{}' WHERE key='profiles'")

    def test_timeout_retries_same_key_then_fresh_client_gets_same_accepted_id(self):
        self.script.replies = [TimeoutError("unknown"), response("queued"), response()]
        identity = self.intent()
        first = self.client.step(identity)
        self.assertEqual(first["attempts"], 1)
        self.client.step(identity)
        self.assertEqual(self.script.calls[0], self.script.calls[1])
        restarted = p.Client(
            self.path, self.config, transport=self.script, clock=lambda: self.at
        )
        final = restarted.step(identity)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(self.script.calls[-1], ("GET", "/v1/responses/resp_one"))
        count = len(self.script.calls)
        restarted.step(identity)
        self.assertEqual(len(self.script.calls), count)

    def test_wrong_returned_model_preserves_handle_and_hold(self):
        self.script.replies = [response(model="other/model"), response()]
        identity = self.intent()
        row = self.client.step(identity)
        self.assertIsNone(row["cost"])
        self.assertEqual(row["response_id"], "resp_one")
        self.assertEqual(row["status"], "prepared")
        row = self.client.step(identity)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(self.script.calls[-1], ("GET", "/v1/responses/resp_one"))

    def test_wrong_returned_response_identity_cannot_replace_accepted_handle(self):
        wrong = response()
        wrong["id"] = "resp_wrong"
        self.script.replies = [response("queued"), wrong]
        identity = self.intent()
        self.client.step(identity)
        row = self.client.step(identity)
        self.assertEqual(row["response_id"], "resp_one")
        self.assertEqual(row["status"], "queued")
        self.assertIsNone(row["cost"])

    def test_unknown_usage_retains_full_hold_and_terminal_result(self):
        self.script.replies = [response(usage=False)]
        identity = self.intent()
        row = self.client.step(identity)
        self.assertEqual(row["error"], "terminal_usage_unsettled")
        self.assertEqual(self.client.totals()["committed_usd"], row["reserved"])
        self.assertEqual(self.client.totals()["known_cost_usd"], "0")

    def test_known_usage_exact_cost_and_frozen_rates_survive_profile_drift(self):
        identity = self.intent()
        original = self.client.profiles["kimi_flex"][2:]
        changed = list(p.PROFILES["kimi_flex"])
        changed[2] = "99"
        with patch.dict(p.PROFILES, {"kimi_flex": tuple(changed)}):
            restarted = p.Client(
                self.path,
                self.config,
                transport=Script(response()),
                clock=lambda: self.at,
            )
            self.assertEqual(restarted.profiles["kimi_flex"][2:], original)
            row = restarted.step(identity)
        self.assertEqual(Decimal(row["cost"]), Decimal("0.00045"))
        self.assertEqual(
            Decimal(self.client.totals()["committed_usd"]), Decimal(".00045")
        )

    def test_over_hold_actual_cost_closes_all_new_admissions(self):
        big = response()
        big["usage"]["output_tokens"] = 20000
        self.script.replies = [big]
        identity = self.intent()
        row = self.client.step(identity)
        self.assertEqual(row["error"], "cost_exceeds_reservation")
        with self.assertRaises(p.AdmissionClosed):
            self.intent("two")
        with self.assertRaises(p.AdmissionClosed):
            self.client.allocate("branch", "0.1")

    def test_branch_reservations_are_atomic_paced_and_not_double_counted(self):
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(lambda _: self.client.allocate("branch", "1.4"), range(2))
            )
        self.assertEqual(self.client.totals()["committed_usd"], "1.4")
        with self.assertRaises(ValueError):
            self.client.allocate("branch", "1.3")
        with self.assertRaises(p.AdmissionClosed):
            self.client.allocate("branch2", "0.2")
        self.at = 10000
        self.client.allocate("branch2", "0.2")
        self.assertEqual(self.client.totals()["committed_usd"], "1.6")

    def test_prepared_deadline_blocks_first_dispatch_but_accepted_get_continues(self):
        one = self.intent("one")
        two = self.intent("two")
        self.script.replies = [response("queued"), response()]
        self.client.step(one)
        self.at = self.config["ends_epoch"] + 60
        self.client.step(two)
        self.assertEqual(len(self.script.calls), 1)
        self.assertEqual(self.client.step(one)["status"], "completed")
        with self.assertRaises(p.AdmissionClosed):
            self.intent("three")
        self.assertEqual(self.intent("one"), one)

    def test_malformed_envelopes_cannot_mint_negative_or_unpriced_holds(self):
        body = p.body_for("kimi_flex", "x", "y")
        for mutate in [
            lambda b: b.update(max_output_tokens=-1),
            lambda b: b.update(max_output_tokens=True),
            lambda b: b.update(tools=[{"type": "web_search"}]),
            lambda b: b.update(background=False),
            lambda b: b["metadata"].update(supercache_write="24h"),
        ]:
            bad = deepcopy(body)
            mutate(bad)
            with self.assertRaises(ValueError):
                self.client.submit_intent("bad", "kimi_flex", bad)
        self.assertEqual(self.client.totals()["requests"], 0)

    def test_branch_can_admit_only_parent_assigned_tasks(self):
        config = {
            **self.config,
            "research_only": True,
            "assigned_task_ids": ["approved"],
        }
        client = p.Client(
            Path(self.tmp.name) / "branch.sqlite",
            config,
            transport=self.script,
            clock=lambda: self.at,
        )
        body = p.body_for("kimi_flex", "x", "y")
        client.submit_intent("approved", "kimi_flex", body)
        with self.assertRaises(ValueError):
            client.submit_intent("not-assigned", "kimi_flex", body)

    def test_supercache_partition_counts_write_once_and_default_prohibits_it(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 400},
        }
        metadata = {
            "supercached_input_tokens": "300",
            "supercache_write_input_tokens": "500",
        }
        rates = {"input": ".35", "cached": ".1", "output": "2"}
        with self.assertRaises(ValueError):
            estimate_cost(usage, rates, metadata)
        cost = estimate_cost(usage, rates, metadata, supercache_contract="write-24h-v1")
        self.assertEqual(
            cost,
            (
                Decimal(100) * Decimal(".35")
                + Decimal(100) * Decimal(".1")
                + Decimal(300) * Decimal(".01")
                + Decimal(500) * 35
                + Decimal(100) * 2
            )
            / 1000000,
        )

    def test_observations_omit_large_prompts_and_model_output_but_keep_receipts(self):
        frozen = p.body_for("kimi_flex", "x" * 300000, "question")
        identity = self.client.submit_intent("large", "kimi_flex", frozen)
        receipt = response()
        receipt["output"][0]["content"][0]["text"] = "PRIVATE MODEL OUTPUT" * 10000
        receipt["metadata"] = {
            "supercached_input_tokens": "0",
            "supercache_write_input_tokens": "0",
        }
        self.script.replies = [receipt]
        self.client.step(identity)
        view = self.client.observations()[0]
        self.assertNotIn("body", view)
        self.assertNotIn("PRIVATE MODEL OUTPUT", json.dumps(view))
        self.assertEqual(
            json.loads(view["response"]),
            {"usage": receipt["usage"], "metadata": receipt["metadata"]},
        )
        self.assertEqual(next(self.client.iter_rows())["body"], p.canonical(frozen))
        self.assertEqual(self.script.calls[0][2], frozen)
        self.assertLess(len(json.dumps(view)), 2000)

    def test_zero_cost_totals_use_plain_public_decimals(self):
        receipt = response()
        receipt["usage"] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "input_tokens_details": {"cached_tokens": 0},
        }
        self.script.replies = [receipt]
        self.client.step(self.intent())
        for key in ("known_cost_usd", "committed_usd", "branch_committed_usd"):
            self.assertRegex(self.client.totals()[key], r"^\d+(?:\.\d+)?$")
            self.assertEqual(Decimal(self.client.totals()[key]), Decimal(0))


if __name__ == "__main__":
    unittest.main()
