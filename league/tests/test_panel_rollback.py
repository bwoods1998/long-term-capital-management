"""scripts/panel_rollback.py: before a CODE rollback past release E4, every alive panel family is retired.

A release from before E4 (main 8ab31e32) scopes its options readers by "structure NOT IN ('etf', 'stock')", so an
alive panel family is an options family to it (the independent check of E4 measured main's tournament giving the
class "panel x none" half its allocation). The script lists the alive panel families and, with `--apply`, retires
them, refusing while `elane.panel.mode` is not "off" or while one of them is outside the Gym band. Every family here
is invented."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from league.swarm.store import OPTIONS_ONLY_SQL, SwarmStore
from league.tests import elane_xs_fakes as F
from league.tests.swarm_fakes import Clock

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "panel_rollback.py"
_spec = importlib.util.spec_from_file_location("panel_rollback", SCRIPT)
PR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PR)  # type: ignore[union-attr]

#: The options readers' scope of a release from before E4 (league/swarm/store.py at main 8ab31e32).
MAIN_OPTIONS_ONLY_SQL = "structure NOT IN ('etf', 'stock')"
MECHANISM = "After a large overnight gap the first hour keeps going; buy the side of the gap, calls up and puts down."


class PanelRollback(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        store = SwarmStore(self.root, clock=Clock())
        try:
            store.add_family({"id": "gap-side", "mechanism": MECHANISM, "structure": "long_single", "roots": ["SPY"],
                              "dte": [0, 2]}, origin="architect")
            store.add_family({"id": "beta-a", "mechanism": "Hold the ETF overnight from each close to the next open.",
                              "structure": "etf", "roots": ["SPY"], "symbols": ["SPY"], "lane": "beta"}, origin="seed")
            for slug in ("rev-a", "rev-b", "rev-c"):
                F.panel_family(store, slug)
            store.retire("rev-c", "retired by its research before the rollback")
        finally:
            store.close()

    def store(self) -> SwarmStore:
        store = SwarmStore(self.root, readonly=True)
        self.addCleanup(store.close)
        return store

    def alive(self, scope: str) -> list[str]:
        return [r["id"] for r in self.store()._all(f"SELECT id FROM families WHERE retired_at IS NULL AND {scope} "
                                                   "ORDER BY born_at, id")]

    def swarm_json(self, mode: str) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"panel": {"mode": mode}}}))

    def test_the_list_names_the_alive_panel_families_and_writes_nothing(self):
        before = self.alive("1=1")
        report = PR.main(["--state", str(self.root)])
        self.assertEqual(report["mode"], "list")
        self.assertEqual(report["setting"], "off", "policy.json ships the lane off")
        self.assertEqual([(r["family"], r["band"]) for r in report["alive_panel"]], [("rev-a", "gym"), ("rev-b", "gym")])
        self.assertEqual(report["retired"], [])
        self.assertEqual(self.alive("1=1"), before)

    def test_apply_retires_them_and_a_release_from_before_e4_then_reads_no_panel_family_as_options(self):
        self.assertEqual(self.alive(MAIN_OPTIONS_ONLY_SQL), ["gap-side", "rev-a", "rev-b"], "main's options readers")
        self.assertEqual(self.alive(OPTIONS_ONLY_SQL), ["gap-side"], "this release's")
        report = PR.main(["--state", str(self.root), "--apply"])
        self.assertNotIn("refused", report)
        self.assertEqual(report["retired"], ["rev-a", "rev-b"])
        self.assertEqual(report["alive_panel"], [])
        self.assertEqual(self.alive(MAIN_OPTIONS_ONLY_SQL), ["gap-side"])
        self.assertEqual(self.alive("1=1"), ["beta-a", "gap-side"], "the options and ETF families are untouched")
        events = [e for e in self.store().events_after(0, limit=5000) if e["kind"] == "swarm.retired"]
        self.assertEqual([(e["family"], e["payload"]["cause"]) for e in events[-2:]],
                         [("rev-a", PR.REASON), ("rev-b", PR.REASON)])
        self.assertEqual(PR.main(["--state", str(self.root), "--apply"])["retired"], [], "a second run retires none")

    def test_apply_refuses_while_the_lane_is_not_off(self):
        for mode in ("train", "gate", "live"):
            self.swarm_json(mode)
            report = PR.main(["--state", str(self.root), "--apply"])
            self.assertIn("set it to 'off' first", report["refused"])
            self.assertEqual(report["retired"], [])
        self.assertEqual(self.alive(MAIN_OPTIONS_ONLY_SQL), ["gap-side", "rev-a", "rev-b"], "nothing was retired")
        self.swarm_json("off")
        self.assertEqual(PR.main(["--state", str(self.root), "--apply"])["retired"], ["rev-a", "rev-b"])

    def test_apply_refuses_while_a_panel_family_is_outside_the_gym_band(self):
        store = SwarmStore(self.root, clock=Clock())
        try:
            store.update_family("rev-b", band="candidate")
        finally:
            store.close()
        report = PR.main(["--state", str(self.root), "--apply"])
        self.assertIn("outside the Gym band: rev-b", report["refused"])
        self.assertEqual(self.alive(MAIN_OPTIONS_ONLY_SQL), ["gap-side", "rev-a", "rev-b"], "nothing was retired")

    def test_the_command_prints_json_and_exits_1_on_a_refusal(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        listed = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", str(self.root)], capture_output=True,
                                text=True, env=env, timeout=120)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(len(json.loads(listed.stdout)["alive_panel"]), 2)
        self.swarm_json("train")
        refused = subprocess.run([sys.executable, "-B", str(SCRIPT), "--state", str(self.root), "--apply"],
                                 capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("refused", json.loads(refused.stdout))


if __name__ == "__main__":
    unittest.main()
