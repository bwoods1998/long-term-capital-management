"""Private pre-Validation observations on invented states/events and a local fake worker only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.ops import scoreboard as SB
from league.swarm import evaluator, settings
from league.swarm.store import SwarmStore
from league.swarm.tournament import Tournament, VALIDATION_DISPOSITIONS, VALIDATION_TELEMETRY_SCHEMA
from league.tests.swarm_fakes import result
from league.tests.test_swarm_rounds import FakeGymPool, weak

NOW = 1791329400.0  # an invented October 6 report instant, never a real evaluation input
SPEC = {"id": "synthetic", "mechanism": "Invented solely for private counter fixtures.",
        "structure": "long_call", "roots": ["SPY"], "dte": [1, 5]}
PROGRAM = "NEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
IDENTITY = {"image": "fixture-image", "bundle": "fixture-bundle", "execution": "fixture-execution"}


def receipt(**counts):
    dispositions = {name: counts.get(name, 0) for name in VALIDATION_DISPOSITIONS}
    return {"schema": VALIDATION_TELEMETRY_SCHEMA, "considered": sum(dispositions.values()),
            "dispositions": dispositions, "worker_errors": 0}


class PrivateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = NOW
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(settings.DEFAULTS)
        self.settings["tournament"].update(require_robustness=False, drift_screen=False)
        self.settings["gate"]["look_holds"] = None


class Admission(PrivateCase):
    def setUp(self):
        super().setUp()
        self.answer = lambda job: {**weak(job), "gym_image": IDENTITY["image"], "gym_bundle": IDENTITY["bundle"],
                                   "roots": list(job.roots), "capital": 10000.0, "fill_model": "fixture-fill"}
        self.pool = FakeGymPool(lambda job: self.answer(job))
        self.pool.image = lambda kind: IDENTITY["image"]
        self.pool.bundle = lambda: IDENTITY["bundle"]
        self.tournament = Tournament(self.store, self.pool, self.settings, clock=lambda: self.now)

    def family(self, fid, *, best=True, current_train=False, parent=None, code=None):
        self.store.add_family({**SPEC, "id": fid}, origin="seed", parent=parent)
        self.store.add_version(fid, PROGRAM + f"# {fid}\n" if code is None else code, {}, author="seed")
        if best:
            self.store.update_family(fid, best_version=1)
        if current_train:
            run = result(fid + "-train")
            run.update(gym_image=IDENTITY["image"], gym_bundle=IDENTITY["bundle"])
            run["summary"].update(gym_image=IDENTITY["image"], gym_bundle=IDENTITY["bundle"], train_eligible=True)
            self.store.add_run(fid, 1, run, window="train", stress=1.0, purpose="train")
            self.store.set_state(fid, best_train_run=run["run_id"], robustness={"1": {"stress_1.5": {"status": "ok", "pnl": 1}}})
        return self.store.family(fid)

    def assert_counts(self, out, **expected):
        self.assertEqual(out["pre_validation"]["dispositions"], receipt(**expected)["dispositions"])
        self.assertEqual(sum(out["pre_validation"]["dispositions"].values()), out["pre_validation"]["considered"])
        self.assertEqual(out["pre_validation"]["worker_errors"], len(out["errors"]))
        self.assertEqual(out["pre_validation"]["dispositions"]["queued"], out["queued"])

    def test_mixed_upstream_waits_have_one_disposition_and_no_extra_evaluations(self):
        self.store.put(evaluator.KEY, IDENTITY)
        self.settings["tournament"]["require_robustness"] = True
        fams = [self.family("none", best=False), self.family("stale")]
        for fid in ("stress", "done", "drift-wait", "drift-fail", "gate-wait", "missing", "queued", "inactive"):
            fams.append(self.family(fid, current_train=True))
        self.store.set_state("stress", robustness={})
        self.store.update_family("done", validated_version=1)
        self.store.set_state("done", validation_image=IDENTITY["image"], validation_bundle=IDENTITY["bundle"])
        self.store.update_family("inactive", retired_at="2026-10-06T23:00:00Z")
        before = {f["id"]: self.store.family(f["id"]) for f in fams}
        version = self.store.version

        def drift(store, fam, n, config):
            return ({"known": fid == "drift-fail", "passed": False} if (fid := fam["id"]).startswith("drift-") else None)

        with mock.patch("league.swarm.tournament.screen_best", return_value=[]), \
             mock.patch("league.swarm.tournament.drift_verdict", side_effect=drift), \
             mock.patch.object(self.store, "version", side_effect=lambda fid, n: None if fid == "missing" else version(fid, n)), \
             mock.patch("league.swarm.tournament.train_gate", side_effect=lambda store, fam, n, cfg: {"ready": fam["id"] != "gate-wait"}):
            out = self.tournament.validate(fams)
        self.assert_counts(out, no_candidate=1, current_train_wait=1, robustness_wait=1, already_validated=1,
                           drift_wait=1, drift_failed=1, train_gate_wait=1, missing_version=1, queued=1, inactive=1)
        self.assertEqual(out["waiting_robustness"], ["stale", "stress"], "existing compatibility field is unchanged")
        self.assertEqual([(j.family, j.window) for j in self.pool.jobs], [("queued", "validation")])
        for fid, before_fam in before.items():
            after = self.store.family(fid)
            if fid == "queued":
                self.assertEqual(after["trials"], before_fam["trials"] + 2)
                self.assertEqual(self.store.lineage_validated(fid)[0], 1)
            else:
                for key in ("trials", "validations", "band", "retired_at", "best_version"):
                    self.assertEqual(after[key], before_fam[key], (fid, key))
                self.assertEqual(self.store.lineage_validated(fid)[0], 0)

    def test_interruption_and_next_round_retry_keep_trial_n_and_completion_semantics(self):
        self.family("retry")
        self.answer = lambda job: {"run_id": "invented-interruption", "status": "error", "reason": "invented timeout",
                                   "trials": 0, "summary": {}, "gym_image": IDENTITY["image"], "gym_bundle": IDENTITY["bundle"]}
        first = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(first, queued=1)
        self.assertEqual(first["pre_validation"]["worker_errors"], 1)
        self.assertEqual((self.store.family("retry")["trials"], self.store.lineage_validated("retry")[0]), (0, 0))
        self.assertIsNone(self.store.family("retry")["validated_version"])
        self.answer = lambda job: {**weak(job), "gym_image": IDENTITY["image"], "gym_bundle": IDENTITY["bundle"],
                                   "roots": list(job.roots), "capital": 10000.0, "fill_model": "fixture-fill"}
        second = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(second, queued=1)
        self.assertEqual(second["pre_validation"]["worker_errors"], 0)
        self.assertEqual((self.store.family("retry")["trials"], self.store.lineage_validated("retry")[0]), (2, 1))
        third = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(third, already_validated=1)
        self.assertEqual(len(self.pool.jobs), 2)
        self.store.update_family("retry", validated_version=None)
        cached = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(cached, recorded_result=1)
        self.assertEqual((self.store.family("retry")["trials"], self.store.lineage_validated("retry")[0]), (2, 1))

    def test_twin_wait_then_failure_inheritance_are_observations_without_duplicate_jobs(self):
        self.family("parent", code=PROGRAM)
        self.family("child", parent="parent", code=PROGRAM)
        self.pool.fail.add("child")  # families are returned alphabetically: child is the submitted twin
        first = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(first, queued=1, twin_wait=1)
        self.assertEqual(first["pre_validation"]["worker_errors"], 1)
        self.pool.fail.clear()
        second = self.tournament.validate(self.store.families(alive=True))
        self.assert_counts(second, queued=1, inherited_result=1)
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(sum(f["trials"] for f in self.store.families(alive=True)), 2)
        self.assertEqual(sum(f["validations"] for f in self.store.families(alive=True)), 2)
        self.assertEqual(self.store.lineage_validated("child")[0], 2)


class WindowObservations(PrivateCase):
    def event(self, telemetry, *, at=None):
        if at is not None:
            self.now = at
        payload = {"validation": {"pre_validation": telemetry}} if telemetry is not None else {"validation": {"queued": 0}}
        self.store.event("swarm.tournament", None, payload)

    def funnel(self):
        return SB.funnel(self.root, NOW, config={})

    def test_known_rounds_repeat_observations_and_legacy_rounds_remain_unknown(self):
        baseline = self.funnel()
        block = receipt(no_candidate=1, current_train_wait=1, queued=1)
        block["worker_errors"] = 1
        self.event(None, at=NOW - 3 * 86400)
        self.event(block, at=NOW - 2 * 86400)
        self.event(block, at=NOW - 3600)
        self.event(None, at=NOW - 1800)
        self.event(receipt(missing_version=99), at=NOW + 1)
        report = self.funnel()
        whole = report["windows"]["since_basis"]["pre_validation"]
        day = report["windows"]["last_24h"]["pre_validation"]
        self.assertEqual((whole["rounds"], whole["observed_rounds"], whole["unknown_rounds"], whole["family_observations"]), (4, 2, 2, 6))
        self.assertEqual((day["rounds"], day["observed_rounds"], day["unknown_rounds"], day["family_observations"]), (2, 1, 1, 3))
        self.assertEqual((whole["dispositions"]["queued"], whole["worker_errors"], day["dispositions"]["queued"]), (2, 2, 1))
        self.assertIsNone(whole["latest"]["receipt"], "the latest legacy event supplies no inferred zero")
        self.assertEqual(SB.funnel_lines(report), SB.funnel_lines(baseline), "public rendering never uses private observations")
        page = lambda record: SB.build(day="2026-10-06", release="fixture", economics=None, deploys={}, budget=None,
                                       ladder={"binding": False}, jobs={}, written_at="23:30Z", funnel=record)
        self.assertEqual(page(report), page(baseline), "the complete public page remains byte-identical")

    def test_malformed_counts_and_no_receipts_never_supply_zero(self):
        for block in self.funnel()["windows"].values():
            self.assertIsNone(block["pre_validation"]["dispositions"])
        invalid = [None, {}, {**receipt(), "schema": True}, {**receipt(), "considered": -1},
                   {**receipt(), "dispositions": {"unknown": 0}}, {**receipt(queued=1), "considered": 2},
                   {**receipt(), "worker_errors": 1}, {**receipt(), "worker_errors": False}]
        bad = receipt(no_candidate=1)
        bad["dispositions"]["no_candidate"] = 1.0
        invalid.append(bad)
        for i, payload in enumerate(invalid):
            self.event(payload, at=NOW - 100 + i)
        for window in self.funnel()["windows"].values():
            block = window["pre_validation"]
            self.assertEqual((block["rounds"], block["observed_rounds"], block["unknown_rounds"]), (len(invalid), 0, len(invalid)))
            self.assertIsNone(block["family_observations"])
            self.assertIsNone(block["dispositions"])
            self.assertIsNone(block["worker_errors"])

    def test_latest_valid_receipt_is_allowlisted_and_real_zero_round_is_known(self):
        self.event({**receipt(no_candidate=1), "secret_reason": "synthetic-private-strategy"}, at=NOW - 2)
        first = self.funnel()["windows"]["last_24h"]["pre_validation"]
        self.assertNotIn("synthetic-private-strategy", json.dumps(first))
        self.assertEqual(first["latest"]["receipt"], receipt(no_candidate=1))
        self.event(receipt(), at=NOW - 1)
        latest = self.funnel()["windows"]["last_24h"]["pre_validation"]
        self.assertEqual(latest["latest"]["receipt"], receipt())
        self.assertEqual((latest["observed_rounds"], latest["family_observations"]), (2, 1))

    def test_slow_private_read_is_unknown_without_changing_other_funnel_parts(self):
        endless = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
                   "SELECT ? AS at, '{}' AS telemetry FROM c WHERE x < 0 AND ? IS NOT NULL")
        with mock.patch.dict(SB.READS, {"pre_validation": endless}), mock.patch.object(SB, "QUERY_SECONDS", 0.01):
            report = self.funnel()
        self.assertIn("pre_validation", report["errors"])
        self.assertEqual(report["windows"]["last_24h"]["born"], 0)
        self.assertIsNone(report["windows"]["last_24h"]["pre_validation"])


if __name__ == "__main__":
    unittest.main()
