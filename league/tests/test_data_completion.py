"""The private-model receipt and resumable full-store stages, with synthetic metadata only."""

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
sys.path.insert(0, str(DATA))
import boxlib as bl
import calibration
import complete
import images
import nightly
import storelib as sl


class CalibrationReceipt(unittest.TestCase):
    def test_receipt_contains_identity_and_counts_without_the_fitted_table(self):
        table = {"source": "league.gym.calibrate", "hazard": {"q2|s|d0|k0|t0": 0.1},
                 "meta": {"fitted_on": {"days": 2, "prints": 20}}}
        receipt = calibration.model_receipt(json.dumps(table).encode())
        self.assertTrue(receipt["model_version"].startswith("fm-"))
        self.assertEqual(receipt["samples"]["days"], 2)
        self.assertNotIn("hazard", receipt)
        for bad in (float("nan"), float("inf"), -0.1, 1.1, True):
            table["hazard"]["q2|s|d0|k0|t0"] = bad
            with self.assertRaises(ValueError):
                calibration.model_receipt(json.dumps(table).encode())

    def test_both_images_receive_the_same_private_model_before_any_checkpoint(self):
        blob = json.dumps({"source": "league.gym.calibrate", "hazard": {"q2|s|d0|k0|t0": 0.1},
                           "meta": {"fitted_on": {"days": 2, "prints": 20}}}).encode()
        class API:
            def __init__(self):
                self.files = {}
            def get(self, box): return {"status": "running"}
            def egress(self, box): return {"document": {"no_network": True}}
            def exec(self, *args, **kwargs):
                result = SimpleNamespace(ok=True)
                result.check = lambda: result
                return result
            def upload(self, box, path, value, **kwargs):
                self.files[box, path] = value
                assert kwargs["mode"] == 0o600
            def download(self, box, path, **kwargs): return self.files[box, path]
            def sleep(self, box): pass
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            initial = {kind: {"current": {"box_id": "sb_" + kind, "checkpoints": ["old-" + kind, "old-backup"]}}
                       for kind in ("gym", "gate")}
            bl.write_json(bl.IMAGES, initial)
            api = API()
            calls = []
            def finish(kind, box, **kwargs):
                self.assertEqual(api.files["sb_gym", calibration.MODEL_PATH], blob)
                self.assertEqual(api.files["sb_gate", calibration.MODEL_PATH], blob)
                calls.append(kind)
                records = bl.read_json(bl.IMAGES)
                records[kind]["current"]["checkpoints"] = ["new-" + kind, "backup-" + kind]
                bl.write_json(bl.IMAGES, records)
                return records[kind]["current"]
            with patch.object(calibration, "fit_on_gym", return_value=(blob, "engine")), patch.object(images, "finish", finish):
                receipt = calibration.prepare_pair(version="test", api=api)
            self.assertEqual(calls, ["gym", "gate"])
            self.assertEqual(receipt["checkpoints"]["gym"], ["new-gym", "backup-gym"])
            self.assertNotIn("hazard", receipt)


class CompletionReadiness(unittest.TestCase):
    def test_every_theta_stage_must_finish_before_sip(self):
        progress = {"stages": {str(s): {"planned": 10, "done": 10, "failing": 0} for s in complete.STAGES}}
        self.assertTrue(complete.theta_ready(progress, False))
        self.assertFalse(complete.theta_ready(progress, True))
        progress["stages"]["6"]["done"] = 9
        self.assertFalse(complete.theta_ready(progress, False))
        progress["stages"]["6"]["done"] = 10
        progress["stages"].pop("4")
        self.assertFalse(complete.theta_ready(progress, False))

    def test_failed_sip_chunk_retries_without_skipping_then_ready_is_metadata_only(self):
        class Ops:
            failed = True
            calls = []
            def relay_chunk(self, start, end):
                self.calls.append(("sip", start, end))
                if self.failed:
                    raise RuntimeError("missing SIP day")
                return {"start": start.isoformat(), "end": end.isoformat()}
            def build(self, kind, version):
                self.calls.append(("build", kind))
                return {"box_id": "sb_" + kind, "checkpoints": ["sbcp_" + kind, "sbcp_" + kind + "_backup"]}
            def calibrate(self, version):
                self.calls.append(("fit", version))
                return {"checkpoints": {k: ["sbcp_" + k, "sbcp_" + k + "_backup"] for k in ("gym", "gate")},
                        "sha256": "abc", "model_version": "fm_test", "samples": {"days": 5}}
            def schedule(self):
                return "2026-09-29T06:00:00Z"
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            bl.write_json(state / "completion-config.json", {"enabled": True})
            bl.write_json(state / "completion.json", {"phase": "sip", "next_day": sl.HOLDOUT[1].isoformat()})
            bl.write_json(bl.UNIVERSE, {"roots": ["SPY"]})
            now = [1000.0]
            ops = Ops()
            worker = complete.Completion(state, operations=ops, clock=lambda: now[0])
            self.assertEqual(worker.tick()["phase"], "sip")
            self.assertEqual(worker.tick()["phase"], "sip")
            self.assertEqual(len(ops.calls), 1)
            now[0] += 300
            ops.failed = False
            self.assertEqual(worker.tick()["phase"], "gym")
            self.assertEqual(worker.tick()["phase"], "gate")
            self.assertEqual(worker.tick()["phase"], "calibrate")
            self.assertFalse((state / "images-ready.json").exists())
            self.assertEqual(worker.tick()["phase"], "complete")
            ready = bl.read_json(state / "images-ready.json")
            self.assertEqual(ready["gate_checkpoint"], "sbcp_gate")
            self.assertEqual(ready["calibration"]["model_version"], "fm_test")
            count = len(ops.calls)
            self.assertEqual(complete.Completion(state, operations=ops).tick()["phase"], "complete")
            self.assertEqual(len(ops.calls), count)

    def test_staged_build_cannot_replace_nightlys_active_gate(self):
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            active = {"gate": {"current": {"box_id": "sb_old_gate"}}}
            bl.write_json(bl.IMAGES, active)
            bl.write_json(bl.DATA_BOX, {"box_id": "sb_data"})
            bl.write_json(bl.UNIVERSE, {"roots": ["SPY"]})
            ops = object.__new__(complete.Operations)
            ops.state = state
            def build(kind, **kwargs):
                self.assertEqual(kwargs["needs"], complete.STAGES)
                self.assertNotIn("force", kwargs)
                entry = {"box_id": "sb_new_gate", "checkpoints": ["a", "b"]}
                bl.write_json(bl.IMAGES, {kind: {"current": entry}})
                return entry
            with patch.object(images, "build", build):
                ops.build("gate", "new")
            self.assertEqual(bl.STATE_DIR, state)
            self.assertEqual(bl.read_json(bl.IMAGES), active)
            self.assertEqual(bl.read_json(state / "next-images" / "images.json")["gate"]["current"]["box_id"], "sb_new_gate")

    def test_disabled_completion_opens_no_vendor_client(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(complete, "Operations", side_effect=AssertionError("no API")):
            self.assertEqual(complete.Completion(Path(tmp)).tick(), {"phase": "disabled"})


class ProcessIdentity(unittest.TestCase):
    def test_exact_script_and_startticks_identify_the_stopped_backfill(self):
        ns = {}
        exec(nightly.BACKFILL_IDENTITY, ns)
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp) / "123"
            proc.mkdir()
            (proc / "cwd").symlink_to("/data/code")
            def stat(start):
                fields = ["S", "1", "123"] + ["0"] * 16 + [str(start)]
                (proc / "stat").write_text("123 (python) " + " ".join(fields))
            stat(900)
            (proc / "cmdline").write_bytes(b"python\0backfill.py\0run\0")
            first = ns["identity"](123, tmp)
            self.assertEqual(first, ("900", 123))
            stat(901)
            self.assertNotEqual(ns["identity"](123, tmp), first)
            (proc / "cmdline").write_bytes(b"python\0other-backfill.py\0run\0")
            self.assertIsNone(ns["identity"](123, tmp))
            (proc / "cmdline").write_bytes(b"python\0/tmp/backfill.py\0run\0")
            self.assertIsNone(ns["identity"](123, tmp))

    def test_failed_session_restart_is_explicit_and_an_empty_queue_is_ok(self):
        class API:
            code = "1"
            def exec(self, *args, **kwargs):
                result = SimpleNamespace(stdout="" if kwargs.get("background") else self.code, ok=True)
                result.check = lambda: result
                return result
        api = API()
        data = nightly.BoxHandle(api, "sb_data")
        with patch.object(data, "backfill_running", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "restart exited"):
                data.start_backfill("--stages 1,2")
            api.code = "0"
            data.start_backfill("--stages 1,2")
        with patch.object(data, "backfill_running", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "second backfill"):
                data.start_backfill("--stages 1,2")
