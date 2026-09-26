"""Public progress follows current proof and keeps private evidence private; all programs/results are invented."""

import copy
import datetime as dt
import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import publish
from league.gym.driver import build_bundle
from league.live import money as M
from league.swarm import progress, sitefeed
from league.swarm.gate import run_sha
from league.swarm.store import SwarmStore

MONDAY = dt.datetime(2026, 9, 28, 13, 30, tzinfo=dt.timezone.utc).timestamp()
NOW = MONDAY + 86400 + 3600
SPEC = {"id": "synthetic-family", "mechanism": "An invented mechanism for a public checklist test.",
        "structure": "debit_vertical", "roots": ["SPY"], "dte": [0, 2]}


class ProgressCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = NOW
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.bundle = build_bundle()[1]
        (self.root / "swarm.json").write_text(json.dumps({"gym": {
            "image_checkpoint": "sbcp_synthetic_gym", "gate_checkpoint": "sbcp_synthetic_gate"}}))
        self.local = {}
        self.live = SimpleNamespace(table=M.Table.from_constitution(), real_money=True, book=object(),
            _grant=lambda: {"active": True, "policy": {"capital_usd": "5500"}},
            state=SimpleNamespace(get=lambda key, default=None: self.local.get(key, default)))

    def family(self, fid="synthetic-family", band="gym", *, parent=None, prior=None):
        self.store.add_family({**SPEC, "id": fid}, origin="test", parent=parent, prior_lineage=prior)
        version = self.store.add_version(fid, f"# invented {fid}\nPARAMS = {{'private_marker': 'never-publish-this'}}\n", {}, author="test")
        self.store.update_family(fid, best_version=version["n"], validated_version=version["n"])
        self.store.bump(fid, trials=1)
        checks = {k: True for k in ("status_ok", "trades", "days", "mean_positive", "t", "dsr", "quarters", "stress")}
        self.store.set_state(fid, validation_version=version["n"], validation_image="sbcp_synthetic_gym",
            validation_bundle=self.bundle, validation_line={"passed": True, "checks": checks,
                "numbers": {"trades": 112, "days": 71, "quarters": "4/4", "lineage_trials": self.store.lineage_trials(fid),
                            "mean": 0.314159, "t": 9.876543, "dsr": 0.998765, "stress_pnl": 98765.4321}},
            review={"sha": run_sha(version), "version": version["n"], "verdict": "pass", "audit": {"verdict": "pass"}},
            banded_version=version["n"], banded_sha=version["sha"], typical_by_version={str(version["n"]): 50},
            forward={"version": version["n"], "negative": False}, live_promoted_at=MONDAY - 86400)
        if band != "gym":
            self.store.add_look(fid, version["n"], run_sha(version), passed=True, p_value=.001, detail={"private": 123.456789})
            self.store.set_band(fid, band, reason="synthetic")
        return version

    def account(self):
        return {"equity": "5481.65", "cash": "5481.65", "stale": False,
                "as_of": dt.datetime.fromtimestamp(self.now, dt.timezone.utc).isoformat()}

    def read(self, fid="synthetic-family", *, rows=None, account=None):
        agents = sitefeed.site_inputs(self.root)["agents"] if rows is None else rows
        values = progress.attach(agents, self.root, live=self.live, account=account or self.account(), now=self.now)
        return next(a for a in values if a["id"] == fid)["progress"]

    def checks(self, value):
        return {r["key"]: (r["done"], r["need"]) for r in value["checks"]}

    def forward(self, fid="synthetic-family", *, source="real", day="2026-09-28", version=1, n=20, pnl=2):
        self.store.add_forward(fid, source, [{"id": f"{source}:{day}:{version}:{i}:{pnl}", "day": day,
            "pnl": pnl, "max_loss": 50, "version": version} for i in range(n)])


class GymProgress(ProgressCase):
    def test_current_validation_counts_are_clipped_and_private_metrics_never_publish(self):
        self.family()
        value = self.read()
        counts = self.checks(value)
        self.assertEqual((value["target"], value["blocked"]), ("candidate", "holdout_pending"))
        self.assertEqual((counts["validation_trades"], counts["validation_days"], counts["validation_quarters"]),
                         ((100, 100), (60, 60), (3, 3)))
        self.assertEqual(counts["holdout"], (0, 1))
        encoded = json.dumps(value)
        for secret in ("never-publish-this", "0.314159", "9.876543", "0.998765", "98765.4321", "private_marker", "sbcp_"):
            self.assertNotIn(secret, encoded)

    def test_partial_validation_shows_its_counts_without_borrowing_training_trials(self):
        self.family()
        state = self.store.family("synthetic-family")["state"]
        line = copy.deepcopy(state["validation_line"])
        line.update(passed=False)
        line["numbers"].update(trades=17, days=9, quarters="1/4")
        line["checks"].update(trades=False, days=False, quarters=False)
        self.store.set_state("synthetic-family", validation_line=line)
        value = self.read()
        self.assertEqual(self.checks(value)["validation_trades"], (17, 100))
        self.assertEqual(value["blocked"], "validation_failed")

    def test_missing_or_changed_selected_version_image_and_bundle_are_unavailable(self):
        self.family()
        state = self.store.family("synthetic-family")["state"]
        for key, value in (("validation_version", 2), ("validation_image", None),
                           ("validation_image", "old-image"), ("validation_bundle", "old-engine")):
            with self.subTest(key=key, value=value):
                self.store.set_state("synthetic-family", **{key: value})
                self.assertIsNone(self.read())
                self.store.set_state("synthetic-family", **{key: state[key]})
        v2 = self.store.add_version("synthetic-family", "# a newer selected program", {}, author="test")
        self.store.update_family("synthetic-family", best_version=v2["n"])
        self.assertIsNone(self.read(), "the old validated program cannot lend progress to a newer selected one")

    def test_connected_and_prior_lineage_trials_withhold_only_the_cached_dsr_pass(self):
        self.family("prior")
        self.family("selected", prior="prior")
        self.family("sibling", parent="selected")
        state = self.store.family("selected")["state"]
        line = copy.deepcopy(state["validation_line"])
        line["numbers"]["lineage_trials"] = self.store.lineage_trials("selected")
        self.store.set_state("selected", validation_line=line)
        before = self.read("selected")
        self.assertEqual(self.checks(before)["validation_dsr"], (1, 1))
        self.store.bump("prior", trials=1)
        after = self.read("selected")
        self.assertEqual(after["blocked"], "evidence_stale")
        self.assertEqual(self.checks(after)["validation_dsr"], (0, 1))
        expected = copy.deepcopy(self.checks(before))
        expected["validation_dsr"] = (0, 1)
        self.assertEqual(self.checks(after), expected)
        self.assertEqual(progress._lines(self.store.family("selected"),
            {f["id"]: f for f in self.store.families()}, [], prior=True), set(self.store.lineages("selected")))

    def test_review_audit_failure_and_stale_review_are_distinct(self):
        version = self.family()
        review = {"sha": run_sha(version), "version": 1, "verdict": "fail", "stage": "audit", "audit": {"verdict": "fail"}}
        self.store.set_state("synthetic-family", review=review)
        value = self.read()
        self.assertEqual((self.checks(value)["review"], self.checks(value)["audit"], value["blocked"]),
                         ((1, 1), (0, 1), "audit_failed"))
        review.update(sha="another-program")
        self.store.set_state("synthetic-family", review=review)
        self.assertEqual(self.read()["blocked"], "review_pending")

    def test_exact_code_links_and_forks_match_the_store_lineage_trial_set(self):
        version = self.family("first")
        self.family("prior")
        self.family("clone", prior="prior")
        self.store.add_version("clone", version["code"], version["params"], author="synthetic clone")
        self.family("child", parent="clone")
        families = {f["id"]: f for f in self.store.families()}
        links = [(r["a"], r["b"]) for r in self.store._all("SELECT a,b FROM lineage_links")]
        self.assertEqual(progress._lines(families["first"], families, links, prior=True),
                         set(self.store.lineages("first")))
        value = self.read("first")
        self.assertEqual((value["blocked"], self.checks(value)["validation_dsr"]), ("evidence_stale", (0, 1)))

    def test_a_past_holdout_pass_while_back_in_gym_cannot_claim_fresh_promotion(self):
        version = self.family()
        self.store.add_look("synthetic-family", 1, run_sha(version), passed=True, p_value=.01, detail={})
        value = self.read()
        self.assertEqual((value["blocked"], self.checks(value)["holdout"]), ("evidence_stale", (0, 1)))


class LiveProgress(ProgressCase):
    def test_candidate_checks_fit_use_grant_ceiling_and_disabled_execution_cannot_complete(self):
        self.family(band="candidate")
        self.assertIsNone(self.read()["blocked"])
        self.live.real_money = False
        value = self.read()
        self.assertEqual((value["blocked"], self.checks(value)["execution_ready"]), ("real_money_off", (0, 1)))
        self.live.real_money = True
        self.live._grant = lambda: {"active": True, "policy": {"capital_usd": "1000"}}
        self.store.set_state("synthetic-family", typical_by_version={"1": 150})
        self.assertEqual(self.read()["blocked"], "risk_too_large", "unratified account capital cannot enlarge the cap")

    def test_missing_grant_or_stale_account_cannot_complete_the_execution_check(self):
        self.family(band="candidate")
        self.live._grant = lambda: None
        self.assertEqual(self.read()["blocked"], "grant_inactive")
        self.live._grant = lambda: {"active": True, "policy": {"capital_usd": "5500"}}
        value = self.read(account={**self.account(), "stale": True})
        self.assertEqual((value["blocked"], self.checks(value)["execution_ready"]), ("account_unavailable", (0, 1)))

    def test_forward_progress_counts_selected_version_once_per_day_preferring_real(self):
        self.family(band="probe")
        self.forward(source="nightly", n=80, pnl=50)
        self.forward(source="shadow", n=60, pnl=30)
        self.forward(source="real", n=3, pnl=-2)
        self.forward(source="real", version=2, n=90, pnl=100)
        value = self.read()
        checks = self.checks(value)
        self.assertEqual((checks["forward_trades"], checks["real_trades"]), ((3, 20), (3, 5)))
        self.assertEqual((checks["forward_mean"], checks["forward_confidence"]), ((0, 1), (0, 1)))
        self.assertEqual(value["blocked"], "forward_incomplete")

    def test_qualified_probe_uses_latest_durable_promotion_time_and_complete_sessions(self):
        self.family(band="probe")
        self.forward()
        self.local["band_moves"] = {"synthetic-family": {"band": "probe", "at": MONDAY - 7 * 86400}}
        self.store.set_state("synthetic-family", live_promoted_at=MONDAY + 30 * 60)
        value = self.read()
        self.assertEqual((self.checks(value)["probe_sessions"], value["blocked"]), ((0, 1), "probe_incomplete"))
        self.now += 86400
        self.assertEqual(self.checks(self.read())["probe_sessions"], (1, 1))
        self.assertIsNone(self.read()["blocked"])

    def test_no_promotion_stamp_never_borrows_an_older_family_age(self):
        self.family(band="probe")
        self.forward()
        self.store.set_state("synthetic-family", live_promoted_at=None)
        self.assertEqual(self.checks(self.read())["probe_sessions"], (0, 1))
        self.assertEqual(self.local, {}, "publishing cannot initialize the trading clock")

    def test_sized_means_maintain_and_a_new_gym_image_does_not_revoke_its_held_band(self):
        self.family(band="sized")
        self.forward()
        (self.root / "swarm.json").write_text(json.dumps({"gym": {"image_checkpoint": "sbcp_expanded_gym"}}))
        value = self.read()
        self.assertEqual(value["target"], "maintain")
        self.assertNotIn("probe_sessions", self.checks(value))
        self.assertIsNone(value["blocked"])

    def test_unknown_typical_loss_blocks_a_candidate_but_does_not_erase_established_probe_evidence(self):
        self.family(band="candidate")
        self.store.set_state("synthetic-family", typical_by_version={})
        self.assertEqual((self.read()["blocked"], self.checks(self.read())["risk_fit"]), ("evidence_stale", (0, 1)))
        self.store.set_band("synthetic-family", "probe", reason="synthetic established band")
        self.forward()
        value = self.read()
        self.assertEqual(self.checks(value)["risk_fit"], (1, 1))
        self.assertIsNone(value["blocked"])

    def test_negative_real_subset_cannot_be_hidden_by_winning_other_days(self):
        self.family(band="sized")
        self.forward(source="real", n=10, pnl=-2)
        self.forward(source="shadow", day="2026-09-29", n=100, pnl=50)
        value = self.read()
        self.assertEqual((value["blocked"], self.checks(value)["real_record"]), ("real_record_negative", (0, 1)))

    def test_band_version_identity_and_roster_snapshot_mismatch_are_unavailable(self):
        self.family(band="candidate")
        rows = sitefeed.site_inputs(self.root)["agents"]
        self.store.set_band("synthetic-family", "probe", reason="changed after roster read")
        self.assertIsNone(self.read(rows=rows))
        self.store.set_state("synthetic-family", banded_sha="wrong-code")
        self.assertIsNone(self.read())

    def test_publishing_is_read_only_and_uses_no_network(self):
        self.family(band="probe")
        self.forward()
        before = self.store._db.execute("PRAGMA data_version").fetchone()[0]
        with patch.object(socket, "socket", side_effect=AssertionError("no new network work")):
            self.assertIsNotNone(self.read())
        after = self.store._db.execute("PRAGMA data_version").fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.local, {})


class Allowlist(ProgressCase):
    def test_optional_field_preserves_old_checkpoint_shape_and_filters_every_nested_field(self):
        self.family()
        row = sitefeed.site_inputs(self.root)["agents"][0]
        at = self.account()["as_of"]
        old = publish.site_agent(row, at)
        self.assertNotIn("progress", old)
        value = self.read()
        new = publish.site_agent(dict(row, progress=value), at)
        self.assertEqual(new["progress"], value)
        self.assertIsNone(publish.site_agent(dict(row, band="probe", progress=value), at)["progress"])
        for mutate in (
            lambda x: x.update(code="never-publish-this"),
            lambda x: x.update(blocked="fitted 0.12345"),
            lambda x: x["checks"][0].update(private="never-publish-this"),
            lambda x: x["checks"][0].update(done=True),
            lambda x: x["checks"][0].update(done=0.75),
            lambda x: x["checks"][0].update(need=17),
            lambda x: x["checks"][1].update(done=101),
            lambda x: x["checks"].__setitem__(1, x["checks"][0]),
        ):
            bad = copy.deepcopy(value)
            mutate(bad)
            self.assertIsNone(publish.site_agent(dict(row, progress=bad), at)["progress"])

    def test_publisher_attaches_progress_from_existing_swarm_and_account_reads(self):
        from league.ledger import Ledger
        from league.tests.test_publish import Broker, FakeHouse

        self.family(band="candidate")
        ledger = Ledger(self.root / "ledger.sqlite")
        self.addCleanup(ledger.close)
        house = FakeHouse(ledger)
        house.swarm, house.options_live = SimpleNamespace(root=self.root), self.live
        house.site_inputs = lambda: sitefeed.site_inputs(self.root)
        publisher = publish.Publisher("https://example.invalid", lambda: "t" * 40, self.root / "publish.json",
            clock=lambda: self.now, real_brokers={"alpaca": Broker(equity="5481.65")})
        body = publisher.checkpoint(house)
        self.assertEqual(body["agents"][0]["progress"]["target"], "probe")
        self.assertIsNone(body["agents"][0]["progress"]["blocked"])

    @unittest.skipUnless(os.environ.get("LTCM_SITE_SCHEMA"), "set LTCM_SITE_SCHEMA to the site's exact schema.js for the cross-repo contract")
    def test_python_output_matches_the_sites_exact_progress_contract(self):
        rows = []
        for band in ("gym", "candidate", "probe", "sized"):
            self.family(band, band=band)
            self.forward(band)
        agents = progress.attach(sitefeed.site_inputs(self.root)["agents"], self.root, live=self.live,
                                 account=self.account(), now=self.now)
        at = publish.site_instant(self.account()["as_of"])
        body = publish.build_checkpoint({"agents": agents, "account": self.account()}, at)
        rows.extend(body["agents"])
        self.assertTrue(all(row.get("progress") for row in rows))
        source = """import fs from 'node:fs'; import {pathToFileURL} from 'node:url';
const {validCheckpoint, validProgress} = await import(pathToFileURL(process.argv[1]).href);
const body = JSON.parse(fs.readFileSync(0, 'utf8'));
if (!validCheckpoint(body)) throw new Error('Python checkpoint rejected');
for (const row of body.agents) if (!validProgress(row.progress, row.band)) throw new Error('progress rejected: '+row.band);
for (const row of body.agents) delete row.progress;
if (!validCheckpoint(body)) throw new Error('old optional-field shape rejected');
process.stdout.write('all four progress targets and old checkpoint accepted\\n');
"""
        done = subprocess.run(["node", "--input-type=module", "-e", source, os.environ["LTCM_SITE_SCHEMA"]],
                              input=json.dumps(body), text=True, capture_output=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("all four progress targets", done.stdout)


if __name__ == "__main__":
    unittest.main()
