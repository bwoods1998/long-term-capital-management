"""The operator's tools stand on `league/` alone (the options overhaul, Sept 26, 2026, trap 4).

Without `scripts/floor_box.py` and `scripts/gateway_admin.py` there is no deploy, no rollback and
no way to release a kill, so they must keep working when the legacy `ltcm/` package is deleted:
neither may import it. Their on-disk state keeps its paths (`.data/ltcm/box.json`, the admin token
under `.data/ltcm/keys/`).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PROBE = """
import importlib.util, json, sys
sys.argv = [{path!r}]
spec = importlib.util.spec_from_file_location("tool_under_test", {path!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(sorted(name for name in sys.modules if name == "ltcm" or name.startswith("ltcm."))))
"""


def legacy_modules_loaded_by(script: str) -> list[str]:
    path = str(ROOT / "scripts" / script)
    out = subprocess.run([sys.executable, "-c", PROBE.format(path=path)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise AssertionError(f"{script} did not import: {out.stderr[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


class TheToolsImportNothingFromTheLegacyPackage(unittest.TestCase):
    def test_floor_box_imports_no_ltcm_module(self):
        self.assertEqual(legacy_modules_loaded_by("floor_box.py"), [])

    def test_gateway_admin_imports_no_ltcm_module_and_reads_no_ltcm_file(self):
        self.assertEqual(legacy_modules_loaded_by("gateway_admin.py"), [])
        text = (ROOT / "scripts" / "gateway_admin.py").read_text()
        self.assertNotIn("ltcm/config.json", text)
        self.assertIn("'.data' / 'ltcm' / 'keys' / 'gateway-admin.token'", text, "the admin token keeps its path")

    def test_the_box_state_keeps_its_path(self):
        source = (ROOT / "scripts" / "floor_box.py").read_text()
        self.assertIn('STATE_PATH = REPO_ROOT / ".data" / "ltcm" / "box.json"', source)

    def test_floor_box_terminal_statuses_are_the_brokers(self):
        import importlib.util

        from ltcm.broker import TERMINAL_STATUSES

        spec = importlib.util.spec_from_file_location("floor_box_for_test", ROOT / "scripts" / "floor_box.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(tuple(module.TERMINAL_STATUSES), tuple(TERMINAL_STATUSES))


class TheLegacySailboxNameIsTheLeagueModule(unittest.TestCase):
    def test_one_module_under_two_names(self):
        import league.sailbox
        import ltcm.sailbox
        from ltcm import sailbox

        self.assertIs(ltcm.sailbox, league.sailbox)
        self.assertIs(sailbox, league.sailbox)
        from ltcm.sailbox import SailboxClient

        self.assertIs(SailboxClient, league.sailbox.SailboxClient)

    def test_the_key_comes_from_the_environment_and_never_into_an_error(self):
        from unittest.mock import patch

        from league import sailbox

        with patch.dict("os.environ", {"SAIL_API_KEY": "sk-test-" + "x" * 24}):
            self.assertEqual(sailbox.default_key_source(), "sk-test-" + "x" * 24)
        with patch.dict("os.environ", {"SAIL_API_KEY": ""}), patch.object(sailbox, "REPO_ROOT", Path("/nonexistent")):
            with self.assertRaises(sailbox.SailboxError) as caught:
                sailbox.default_key_source()
        self.assertEqual(str(caught.exception), "provider_key_missing")


if __name__ == "__main__":
    unittest.main()
