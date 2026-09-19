"""The replay regression: every founding seed over the canned tapes must produce exactly the
recorded result. A change to the simulator, the fee model, the safety rules or a seed that moves
any number shows up here, named. To accept an intended change, regenerate the record:

    python3 -m league.tests.test_replay_regression --record
"""

import json
import sys
import unittest
from pathlib import Path

from league import ci, seeds
from league.replay import run_replay
from league.runner import needs_of

RECORD = Path(__file__).resolve().parent / "fixtures" / "replay_regression.json"
KEYS = ("ok", "trades", "fills", "maker_fills", "refused", "errors", "steps")


def measure() -> dict:
    out = {}
    for seed in seeds.all_seeds():
        venue = needs_of(seed["code"])["needs"]["venue"]
        result = run_replay(seed["code"], {}, ci.regression_tape(venue))
        row = {k: result.get(k) for k in KEYS}
        row["final_equity"] = round(float(result.get("final_equity") or 0), 6)
        row["fees_usd"] = round(float(result.get("fees_usd") or 0), 6)
        row["blocks"] = len(result.get("blocks") or [])
        out[seed["name"]] = row
    return out


class ReplayRegression(unittest.TestCase):
    def test_every_seed_replays_to_the_recorded_result(self):
        recorded = json.loads(RECORD.read_text(encoding="utf-8"))
        measured = measure()
        self.assertEqual(sorted(measured), sorted(recorded))
        for name in measured:
            self.assertEqual(measured[name], recorded[name], name)

    def test_no_seed_errors_on_the_canned_tape(self):
        for name, row in json.loads(RECORD.read_text(encoding="utf-8")).items():
            self.assertTrue(row["ok"], name)
            self.assertEqual(row["errors"], 0, name)


if __name__ == "__main__":
    if "--record" in sys.argv:
        RECORD.write_text(json.dumps(measure(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("recorded", RECORD)
    else:
        unittest.main()
