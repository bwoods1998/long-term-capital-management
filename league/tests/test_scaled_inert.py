"""C3 (A45) of the scaling plan SHIPS DARK: with no matching pin-sha row, every sizing, every line and every Done reading
is C2's head, to the byte (the captain's decision 2 of the C3 build).

The proof is a diff, not an argument. `league/tests/scaled_inert_scenario.py` runs one synthetic book through the House's
own code and reads everything C3 could move (what each entry stated to money's `size_entry` at the send and again, the
orders and the lots they opened with their marks and `info`, each decide view, the panel's budget, the equity rows'
Probe figures, both lanes' Probe budget and its room, each program's EDM1 record, the forward rows, the Done meter's
equity closes, counts and beside-figures, the swarm's family line, the book's kv, records, alerts and health). The same
scenario run on C2's head (22646a97, `feat/scale-c2`) under Python 3.14 and 3.11 wrote
league/tests/fixtures/scaled_inert_c2.json; here it runs on this tree and must give that file back:
- as shipped (the row unset): everything, the book's own memory included;
- with a pin-sha row that is NOT the pin's (the pin there names rungs for two programs): every sizing, line and reading
  (the book then says the mismatch: its memory, a record and one standing alert, and nothing else);
- the same with Blake's Scaled lines and their family-line part in force (no Scaled lot exists, so nothing moves);
- with the row the pin's own and the swarm's setting at "stop the ladder" (`elane.scale.rung` 0): every sizing, line
  and reading (the book keeps the stop as its ratchet for that pin, and says the pin matched, once).
The pin's E_P and every figure are invented. Standard library only."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.constitution import CONSTITUTION
from league.tests import scaled_inert_scenario as SC

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "scaled_inert_c2.json"
#: The golden file's sha256 as C2's head wrote it (its bytes may not drift unseen).
GOLDEN_SHA = "a62f72c0967cf17a924ce936faa0f5be3df8982d946bc8e90f950ad4dfdf9046"
#: The readings a pin-sha row of any kind may never move while no rung is live: the sizings, the lines, the Done reading.
TRADING = ("ticks", "sized_at_send", "sized_now", "decide_views", "panel", "orders", "lots", "exports", "probe_figures",
           "probe_budget", "budget_room", "records", "done", "family_line")
#: What the book keeps of itself; only a row that is unset leaves all of it as C2 had it.
MEMORY = ("kv_keys", "kv", "events", "alerts", "health")


def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


class TheGolden(unittest.TestCase):
    def test_the_golden_file_is_c2s_own(self):
        self.assertEqual(hashlib.sha256(GOLDEN.read_bytes()).hexdigest(), GOLDEN_SHA)
        self.assertEqual(sorted(golden()), sorted(TRADING + MEMORY))

    def test_the_tree_ships_dark(self):
        block = CONSTITUTION["equity_money"]["scaled"]
        self.assertEqual(block["pin_sha256"], "", "no pin-sha row: no rung (the first is Blake's later deploy)")
        self.assertIs(block["lines"]["in_force"], False, "nothing past R1 before Blake's yes")
        self.assertIs(block["lines"]["family_line_probe_only"], False)


class Inert(unittest.TestCase):
    def run_scenario(self, configure=None) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            return json.loads(SC.canonical(SC.run(Path(tmp), configure=configure)))

    def assert_same(self, got: dict, keys) -> None:
        want = golden()
        for key in keys:
            self.assertEqual(got[key], want[key], f"{key} moved")

    def test_as_shipped_everything_is_c2s(self):
        got = self.run_scenario()
        self.assert_same(got, TRADING + MEMORY)
        self.assertEqual(got, golden())

    def test_a_row_that_is_not_the_pins_moves_no_sizing_line_or_reading(self):
        with mock.patch.dict(CONSTITUTION["equity_money"]["scaled"], {"pin_sha256": "cd" * 32}):
            got = self.run_scenario()
        self.assert_same(got, TRADING)
        added = sorted(set(got["kv_keys"]) - set(golden()["kv_keys"]))
        self.assertEqual(added, ["eq_scale"], "the memory holds the mismatch's first minute")
        self.assertEqual(sorted(json.loads(got["kv"]["eq_scale"])), ["mismatch_since"], "no program at a rung was kept")
        said = [e for e in got["events"] if e[0] in ("equity.scale", "ops.alert")]
        self.assertEqual([e[0] for e in said], ["equity.scale", "ops.alert"], "one record and one standing alert")

    def test_with_the_scaled_lines_in_force_nothing_moves_while_no_lot_is_scaled(self):
        with mock.patch.dict(CONSTITUTION["equity_money"]["scaled"], {"pin_sha256": "cd" * 32}), \
                mock.patch.dict(CONSTITUTION["equity_money"]["scaled"]["lines"],
                                {"in_force": True, "family_line_probe_only": True}):
            got = self.run_scenario()
        self.assert_same(got, TRADING)

    def test_the_pins_own_row_with_the_ladder_stopped_is_c2s_too(self):
        sha = hashlib.sha256(SC.pin_body()).hexdigest()

        def stop(h):
            h.families.scale = {"rung": 0, "programs": {}}

        with mock.patch.dict(CONSTITUTION["equity_money"]["scaled"], {"pin_sha256": sha}):
            got = self.run_scenario(configure=stop)
        self.assert_same(got, TRADING + ("alerts",))
        self.assertEqual(sorted(set(got["kv_keys"]) - set(golden()["kv_keys"])), ["eq_scale"])
        self.assertEqual(json.loads(got["kv"]["eq_scale"]), {"ratchet": {"sha256": sha, "rungs": {
            "eq|fam-a|v1": 0, "eq|fam-b|v1": 0}}}, "the stop sticks for this pin: only a new pin raises a rung again")
        self.assertEqual({k: v for k, v in got["kv"].items() if k != "eq_scale"}, golden()["kv"])
        self.assertEqual([e[1]["state"] for e in got["events"] if e[0] == "equity.scale"], ["matched"])


if __name__ == "__main__":
    unittest.main()
