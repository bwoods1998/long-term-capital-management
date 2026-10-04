"""Git artifact and code-only rollback checks with synthetic private state."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("research_release", REPO / "scripts/research_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ResearchRelease(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "checkout"
        self.hashes = {}
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "release-test@example.invalid")
        self.git("config", "user.name", "Synthetic Release Test")
        for name in ("daily_compute", "research_controller", "research_state", "research_adapters", "research_ipc",
                     "research_host", "research_sandbox", "research_transport"):
            self.file(f"league/swarm/{name}.py", "# synthetic artifact\n")
        self.file("league/gym/program.py", "# evaluator bytes\n")
        self.file("league/CONTRACT.md", "Synthetic contract.\n")
        self.file("ltcm/data/calendar.py", "# calendar code only\n")
        self.file("league/tests/test_synthetic.py", "# excluded tests\n")
        self.file(".env", "GATEWAY_TOKEN=synthetic-private-value\n")
        self.file("league/state/swarm.sqlite", "synthetic private database")
        self.file("ltcm/data/prices.parquet", "synthetic market data")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic first release")
        self.first = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout

    def file(self, name, body):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def packed(self, name, head=None):
        result = release.pack(self.repo, head or self.first, self.root / name,
                              config={"swarm": {"gym": {"workers": 8}}}, policy={})
        self.hashes[name] = result["receipt_sha256"]
        return result

    def verify_release(self, path):
        return release.verify_release(path, approved_sha256=self.hashes[path.parent.name])

    def rollback_drill(self, previous, candidate, state, output):
        return release.rollback_drill(previous, candidate, state, output,
                                      previous_sha256=self.hashes[previous.parent.name],
                                      candidate_sha256=self.hashes[candidate.parent.name])

    def test_pack_uses_committed_bytes_and_excludes_private_history_state_and_data(self):
        self.file("league/gym/program.py", "# uncommitted source must not leak\n")
        result = self.packed("first")
        artifact = Path(result["artifact"])
        self.assertEqual((artifact / "league/gym/program.py").read_text(), "# evaluator bytes\n")
        self.assertTrue((artifact / "ltcm/data/calendar.py").is_file())
        self.assertTrue((artifact / "league/CONTRACT.md").is_file())
        for name in (".git", ".env", "league/state/swarm.sqlite", "ltcm/data/prices.parquet", "league/tests/test_synthetic.py"):
            self.assertFalse((artifact / name).exists(), name)
        self.assertEqual(self.verify_release(self.root / "first/release.json"), result)
        self.assertEqual(result["provider_calls"], 0)

    def test_git_commit_and_blob_replacements_cannot_substitute_exact_requested_source(self):
        original_blob = self.git("rev-parse", self.first + ":league/gym/program.py").strip()
        self.file("league/gym/program.py", "# replacement source must not leak\n")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic replacement source")
        replacement = self.git("rev-parse", "HEAD").strip()
        replacement_blob = self.git("rev-parse", replacement + ":league/gym/program.py").strip()
        for kind, original, substitute in (("commit", self.first, replacement),
                                           ("blob", original_blob, replacement_blob)):
            with self.subTest(kind=kind):
                self.git("replace", original, substitute)
                try:
                    # Prove the fixture has an active replacement, then verify the
                    # exporter uses the original object for every Git operation.
                    changed = self.git("show", self.first + ":league/gym/program.py")
                    self.assertEqual(changed, "# replacement source must not leak\n")
                    result = self.packed("replacement-" + kind, self.first)
                    artifact = Path(result["artifact"])
                    self.assertEqual(result["head"], self.first)
                    self.assertEqual((artifact / "league/gym/program.py").read_text(), "# evaluator bytes\n")
                    self.assertEqual(self.verify_release(self.root / ("replacement-" + kind) / "release.json"), result)
                finally:
                    self.git("replace", "-d", original)

    def test_manifest_rejects_modified_extra_missing_and_symlinked_artifact_bytes(self):
        for kind in ("modified", "extra", "missing", "symlink"):
            with self.subTest(kind=kind):
                result = self.packed(kind)
                artifact = Path(result["artifact"])
                target = artifact / "league/gym/program.py"
                if kind == "modified":
                    target.write_text("# edited\n")
                elif kind == "extra":
                    (artifact / "unreviewed.py").write_text("# extra\n")
                elif kind == "missing":
                    target.unlink()
                else:
                    target.unlink()
                    target.symlink_to(self.repo / "league/gym/program.py")
                with self.assertRaises(release.ResearchReleaseError):
                    self.verify_release(self.root / kind / "release.json")

    def test_tracked_code_symlink_refuses_export_without_partial_artifact(self):
        path = self.repo / "league/gym/program.py"
        path.unlink()
        path.symlink_to(self.repo / ".env")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic escaping symlink")
        with self.assertRaisesRegex(release.ResearchReleaseError, "symlinks"):
            self.packed("bad", self.git("rev-parse", "HEAD").strip())
        self.assertFalse((self.root / "bad").exists())

    def test_private_configuration_and_inside_checkout_output_are_refused(self):
        for key in ("gateway_token", "token", "authorization", "credential", "credentials", "auth",
                    "apiKey", "APIKey", "api-key", "api_key", "accessToken", "access-token", "access_token",
                    "privateKey", "private-key", "private_key", "proxyAuthorization", "proxy-authorization",
                    "proxy_authorization"):
            for document in ("config", "policy"):
                with self.subTest(key=key, document=document), self.assertRaisesRegex(release.ResearchReleaseError, "credential"):
                    documents = {"config": {}, "policy": {}}
                    documents[document] = {"swarm": {"options": [{key: "fixture"}]}}
                    release.pack(self.repo, self.first, self.root / "private-config", **documents)
        with self.assertRaisesRegex(release.ResearchReleaseError, "outside"):
            release.pack(self.repo, self.first, self.repo / "artifact", config={}, policy={})
        self.assertFalse((self.root / "private-config").exists())

    def test_noncredential_model_token_limits_remain_exportable(self):
        config = {"swarm": {"model_options": {"max_output_tokens": 1234, "maxOutputTokens": 1234}}}
        result = release.pack(self.repo, self.first, self.root / "token-limits", config=config, policy={})
        artifact = Path(result["artifact"])
        self.assertEqual(json.loads((artifact / "research-config.json").read_text()), config)
        self.assertEqual(release.verify_release(self.root / "token-limits/release.json",
                                                approved_sha256=result["receipt_sha256"]), result)

    def test_rewritten_head_or_self_manifest_cannot_replace_the_approved_receipt(self):
        self.packed("first")
        path = self.root / "first/release.json"
        receipt = json.loads(path.read_text())
        receipt["head"] = "f" * 40
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(release.ResearchReleaseError, "approved SHA256"):
            self.verify_release(path)

    def test_source_pointer_rollback_preserves_unresolved_obligations_and_counter_evidence(self):
        self.packed("previous")
        self.file("league/swarm/research_controller.py", "# changed synthetic code\n")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic second release")
        second = self.git("rev-parse", "HEAD").strip()
        self.packed("candidate", second)
        state = self.root / "private-state"
        state.mkdir(mode=0o700)
        (state / "durable-ledger.json").write_text(json.dumps({"pending_creation": "lost-reply", "consumed_looks": 3,
                                                               "failed_validation": True, "reserved_usd": "13.3250304"}))
        before = (state / "durable-ledger.json").read_bytes()
        result = self.rollback_drill(self.root / "previous/release.json", self.root / "candidate/release.json",
                                       state, self.root / "drill")
        self.assertTrue(result["source_pointer_restored"])
        self.assertTrue(result["durable_state_unchanged"])
        self.assertEqual(result["candidate_head"], second)
        self.assertEqual((state / "durable-ledger.json").read_bytes(), before)
        self.assertFalse(result["controller_lifecycle_rehearsed"])
        self.assertFalse(result["production_deployed"])

    def test_rollback_state_cannot_live_inside_either_code_artifact(self):
        result = self.packed("first")
        with self.assertRaisesRegex(release.ResearchReleaseError, "outside both"):
            self.rollback_drill(self.root / "first/release.json", self.root / "first/release.json",
                                   Path(result["artifact"]), self.root / "drill")

    def test_rollback_output_cannot_change_an_approved_code_artifact(self):
        result = self.packed("first")
        state = self.root / "state"
        state.mkdir()
        with self.assertRaisesRegex(release.ResearchReleaseError, "output must stay outside"):
            self.rollback_drill(self.root / "first/release.json", self.root / "first/release.json",
                                   state, Path(result["artifact"]) / "drill")
        self.assertEqual(self.verify_release(self.root / "first/release.json"), result)
