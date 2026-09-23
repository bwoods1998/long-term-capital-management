"""The Alpha Lab (league/lab.py): the archive, the search tape's seals, batch evaluation, graduation
through the House's replay and the holdout's rationing, the birth cap, royalties, the lab's spend line,
and the researchers' lab tools -- against a fake lab box that runs the real replay engine locally and
fake Luna and Sol clients."""

import importlib.util
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

from league import lab as lab_module
from league.frontier import Answer, FrontierError
from league.lab import (LAB_JOB, Lab, LabError, SealedTape, cell_key, check_dev_only, corr_bucket, score, search_tape,
                        static_literal, tpd_bucket, with_params)
from league.replay import run_replay
from league.researcher import LAB_TOOLS, TOOLS, Researcher
from league.tests.test_house import IDLE, HouseCase
from league.tests.test_hypotheses import PASSER

D = Decimal
DESK = "alpaca-crypto-majors"

#: The sawtooth passer with a knob: it buys the low leg with `notional` dollars.
KNOB = PASSER.replace("PARAMS = {}", 'PARAMS = {"notional": 50.0}').replace('"notional_usd": 50', '"notional_usd": ctx["params"]["notional"]')
#: The same mechanism with a different size: another program for the archive.
SMALLER = KNOB.replace('PARAMS = {"notional": 50.0}', 'PARAMS = {"notional": 25.0}')
#: The same mechanism, entered at most once every three hours: another row of the grid.
SPARSE = KNOB.replace("if low and not held:", 'if low and not held and int(ctx["now"][11:13]) % 3 == 0 and int(ctx["now"][14:16]) < 10:')
#: One that buys the HIGH leg and sells the low one: it trades as much and loses.
LOSER = PASSER.replace("low = bars[-1][\"c\"] < 80000", "low = bars[-1][\"c\"] > 80000")


class FakeBox:
    """The lab box's contract (league/labbox.py): one run_replay-shaped result per candidate, plus
    its id, in order. Runs the real replay engine in this process."""

    def __init__(self):
        self.calls = []

    def evaluate(self, candidates, tape_id, tape, *, stake, limits, timeout=600):
        self.calls.append({"tape_id": tape_id, "ids": [c["id"] for c in candidates], "steps": len(tape["steps"])})
        return [{**run_replay(c["code"], c["params"], tape, stake=stake, limits=limits), "id": c["id"]} for c in candidates]


class FakeModel:
    """Luna or Sol: answers with the programs it is given, at a fixed cost."""

    def __init__(self, model, programs=(), cost="0.01", fail=False):
        self.model = model
        self.programs = list(programs)
        self.cost = D(cost)
        self.fail = fail
        self.asked = []

    def ask(self, *, system, user, agent, max_output_tokens=6000, effort="medium"):
        self.asked.append({"system": system, "user": json.loads(user), "agent": agent})
        if self.fail:
            raise FrontierError("frontier call refused: HTTP 402")
        return Answer(json.dumps({"candidates": [{"name": f"p{i}", "idea": f"idea {i}", "code": code}
                                                 for i, code in enumerate(self.programs)]}), self.cost,
                      {"input_tokens": 100, "output_tokens": 100}, self.model)


class LabCase(HouseCase):
    def setUp(self):
        super().setUp()
        self.house.pacer.may_spend = lambda kind: True  # the test clock is outside the expedition's calendar
        self.house.game["lab"] = {**(self.house.game.get("lab") or {}), "enabled": True, "step_seconds": 600,
                                  "stats_every_minutes": 0, "leap_every": 1000}
        self.box = FakeBox()
        self.luna = FakeModel("gpt-6-luna", [SMALLER])
        self.sol = FakeModel("gpt-6-sol", [])
        self.lab = Lab(self.house, box=self.box, mutator=self.luna, leaper=self.sol)
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        self.niche = self.house.niches[DESK]

    def queue(self, code, origin="seed", lineage="founder:test"):
        return self.lab.admit(code, niche=self.niche, origin=origin, author="house", lineage=lineage)

    def candidate(self, ident):
        return self.lab._q("SELECT * FROM candidates WHERE id=?", (ident,))[0]


class Helpers(unittest.TestCase):
    def test_literals_are_read_without_running_the_file_and_params_are_rewritten(self):
        self.assertEqual(static_literal(KNOB, "PARAMS"), {"notional": 50.0})
        self.assertEqual(static_literal(KNOB, "NEEDS")["symbols"], ["BTC/USD"])
        self.assertIsNone(static_literal("NEEDS = dict(a=1)\n", "NEEDS"))
        changed = with_params(KNOB, {"notional": 12.5})
        self.assertEqual(static_literal(changed, "PARAMS"), {"notional": 12.5})
        self.assertEqual(static_literal(changed, "NEEDS"), static_literal(KNOB, "NEEDS"))
        self.assertIsNone(with_params("def decide(ctx):\n    return {}\n", {"a": 1}))

    def test_the_grid(self):
        self.assertEqual([tpd_bucket(x) for x in (0, 0.2, 0.99, 1, 5, 19.9, 20, 500)], [0, 1, 1, 2, 3, 3, 4, 4])
        self.assertEqual([corr_bucket(x) for x in (None, float("nan"), -0.9, 0.0, 0.3, 0.9)], [0, 0, 1, 2, 3, 4])
        self.assertEqual(cell_key(DESK, "hour", 2, 0), f"{DESK}|hour|t2|c0")

    def test_no_tape_that_reaches_the_sealed_holdout_is_searched(self):
        holdout = ("2025-11-14", "2026-05-15")
        clean = {"steps": [{"t": "2025-05-01T00:00:00Z"}, {"t": "2025-11-13T23:55:00Z"}], "source": {"window": ["2025-03-01", "2025-11-14"]}}
        check_dev_only(clean, holdout)  # [start, end): a window ending where the holdout begins is clean
        live = {"steps": [{"t": "2026-09-01T00:00:00Z"}, {"t": "2026-09-22T00:00:00Z"}]}
        check_dev_only(live, holdout)
        for tape in ({"steps": clean["steps"], "source": {"window": ["2025-03-01", "2025-11-15"]}},
                     {"steps": [{"t": "2025-11-10T00:00:00Z"}, {"t": "2025-11-20T00:00:00Z"}]},
                     {"steps": [{"t": "2026-05-14T00:00:00Z"}, {"t": "2026-06-01T00:00:00Z"}]},
                     {"steps": live["steps"], "warmup_bars": {"BTC/USD": [{"t": "2026-01-02T00:00:00Z"}]}},
                     {"steps": live["steps"], "observed_bars": {"BTC/USD": [{"t": "2026-03-02T00:00:00Z"}]}}):
            with self.assertRaises(SealedTape):
                check_dev_only(tape, holdout)

    def test_the_search_tape_is_the_first_two_thirds_and_the_house_tape_is_untouched(self):
        tape = {"venue": "alpaca", "steps": [{"t": f"2026-09-10T{h:02d}:00:00Z"} for h in range(24)]}
        cut = search_tape(tape, 0.66)
        self.assertEqual(len(cut["steps"]), 15)
        self.assertEqual(len(tape["steps"]), 24)
        self.assertEqual(cut["steps"][-1]["t"], "2026-09-10T14:00:00Z")

    def test_score_needs_the_gates_trades_and_blocks(self):
        blocks = [{"key": f"k{i}", "log_growth": 0.001, "active": True} for i in range(30)]
        good = {"ok": True, "blocks": blocks, "trades": 12, "out_of_sample": {"blocks": 10, "mean_log_growth": 0.001, "active_blocks": 10}}
        tape = {"steps": [{"t": "2026-09-10T00:00:00Z"}, {"t": "2026-09-12T00:00:00Z"}]}
        scored = score(good, tape)
        self.assertTrue(scored["eligible"] and scored["gate"])
        self.assertEqual(scored["fitness"], 0.001)
        self.assertEqual(scored["trades_per_day"], 6.0)
        few = score({**good, "trades": 3}, tape)
        self.assertFalse(few["eligible"])
        self.assertIsNone(few["fitness"])
        losing = score({**good, "out_of_sample": {"blocks": 10, "mean_log_growth": -0.01, "active_blocks": 10}}, tape)
        self.assertTrue(losing["eligible"])
        self.assertFalse(losing["gate"])
        self.assertFalse(score({"ok": False, "error": "boom"}, tape)["eligible"])


class Archive(LabCase):
    def test_a_cell_keeps_its_fittest_program(self):
        cell = cell_key(DESK, "hour", 3, 0)
        self.assertTrue(self.lab._place(cell, DESK, "a", 0.001))
        self.assertFalse(self.lab._place(cell, DESK, "b", 0.0005))
        self.assertFalse(self.lab._place(cell, DESK, "c", 0.001))  # strictly fitter only
        self.assertTrue(self.lab._place(cell, DESK, "d", 0.002))
        self.assertTrue(self.lab._place(cell_key(DESK, "hour", 1, 0), DESK, "e", -0.5))  # another cell is another niche
        rows = {r["cell"]: (r["candidate"], r["replaced"]) for r in self.lab._q("SELECT * FROM archive")}
        self.assertEqual(rows[cell], ("d", 1))
        self.assertEqual(rows[cell_key(DESK, "hour", 1, 0)], ("e", 0))

    def test_admission_applies_the_code_check_the_desk_and_parameter_validation(self):
        with self.assertRaisesRegex(LabError, "strategy check"):
            self.queue("import os\n\nNEEDS = {}\nPARAMS = {}\n\ndef decide(ctx):\n    return {}\n")
        with self.assertRaisesRegex(LabError, "literal"):
            self.queue(PASSER.replace("PARAMS = {}", "PARAMS = dict()"))
        kalshi = PASSER.replace('"venue": "alpaca"', '"venue": "kalshi"')
        with self.assertRaisesRegex(LabError, "outside"):
            self.queue(kalshi)
        with self.assertRaisesRegex(LabError, "NEEDS name"):
            self.queue(PASSER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]'))
        with self.assertRaisesRegex(LabError, "invalid parameters"):
            self.queue(PASSER.replace("PARAMS = {}", 'PARAMS = {"lookback": -3}'))
        ident = self.queue(PASSER)
        with self.assertRaisesRegex(LabError, "already"):
            self.queue(PASSER)
        self.assertEqual(self.candidate(ident)["status"], "queued")

    def test_a_batch_is_evaluated_on_the_search_tape_scored_and_archived(self):
        good, bad = self.queue(KNOB), self.queue(LOSER)
        idle = self.queue(IDLE)  # other NEEDS (no bars declared): another tape, so another batch
        done = self.lab.evaluate_batch()
        self.assertEqual(done["candidates"], 2)
        self.assertEqual(self.lab.evaluate_batch()["candidates"], 1)
        self.assertIsNone(self.lab.evaluate_batch())
        self.assertEqual(len(self.box.calls), 2)
        full = self.house.tape_for(static_literal(KNOB, "NEEDS"))[1]
        self.assertEqual(self.box.calls[0]["steps"], int(len(full["steps"]) * 0.66))  # the last third is never searched
        winner, loser, sitter = self.candidate(good), self.candidate(bad), self.candidate(idle)
        self.assertEqual(winner["status"], "evaluated")
        self.assertTrue(winner["eligible"] and winner["gate"])
        self.assertGreater(winner["fitness"], 0)
        self.assertTrue(loser["eligible"])
        self.assertFalse(loser["gate"])
        self.assertFalse(sitter["eligible"])  # never traded: no fitness, no cell
        self.assertIsNone(sitter["cell"])
        cells = {r["cell"]: r["candidate"] for r in self.lab._q("SELECT * FROM archive")}
        self.assertEqual(cells[winner["cell"]], good)
        self.assertEqual(winner["cell"].split("|")[-1], "c0")  # no live book to correlate with: `na`
        summary = json.loads(winner["summary"])
        self.assertEqual(len(summary["folds"]), 3)

    def test_the_house_keeps_no_tape_only_the_lab_asked_for(self):
        self.house.tape_for(static_literal(KNOB, "NEEDS"))  # an agent's replay built this one
        known = set(self.house._tapes)
        self.queue(KNOB)
        self.queue(IDLE)  # this one's tape only the lab wants
        while self.lab.evaluate_batch():
            pass
        self.assertEqual(set(self.house._tapes), known)
        self.assertEqual(len(self.lab._tapes), 2)

    def test_a_tape_in_the_holdout_is_never_sent_to_the_box(self):
        ident = self.queue(KNOB)
        sealed = {"venue": "alpaca", "horizon": "hour", "steps": [{"t": "2026-01-05T00:00:00Z", "bars": {}},
                                                                    {"t": "2026-01-05T00:05:00Z", "bars": {}}]}
        with patch.object(self.house, "tape_for", return_value=("alpaca:sealed", sealed)):
            self.assertIsNone(self.lab.evaluate_batch())
        self.assertEqual(self.box.calls, [])
        row = self.candidate(ident)
        self.assertEqual(row["status"], "blocked")
        self.assertIn("holdout", row["error"])

    def test_a_box_failure_leaves_the_candidates_queued_and_the_box_alone_for_a_while(self):
        ident = self.queue(KNOB)

        class Down:
            def evaluate(self, *a, **k):
                raise OSError("the lab box is asleep")

        self.lab.use_box(Down())
        self.assertIsNone(self.lab.evaluate_batch())
        self.assertEqual(self.candidate(ident)["status"], "queued")
        self.assertIn("lab box", self.lab.open())
        self.clock.advance(301)
        self.assertEqual(self.lab.open(), "")

    def test_a_tape_the_box_refuses_blocks_its_candidates(self):
        ident = self.queue(KNOB)

        class TapeRefused(ValueError):
            pass

        class Sealed:
            def evaluate(self, *a, **k):
                raise TapeRefused("unsupported input: the tape reaches into the sealed holdout")

        self.lab.use_box(Sealed())
        done = self.lab.evaluate_batch()
        self.assertEqual(done["refused"], 1)
        row = self.candidate(ident)
        self.assertEqual(row["status"], "blocked")
        self.assertIn("refused the tape", row["error"])
        self.assertEqual(self.lab.open(), "")  # not an outage


class Breeding(LabCase):
    def test_seeds_are_living_programs_cards_and_founders(self):
        agent = self.seated("sawtooth", KNOB)
        added = self.lab.seed(force=True)
        self.assertGreaterEqual(added, 1)
        rows = self.lab._q("SELECT * FROM candidates WHERE origin='seed'")
        self.assertIn(f"agent:{agent.id}", {r["lineage"] for r in rows})
        self.assertTrue(any(r["lineage"].startswith("founder:") for r in rows))
        self.assertEqual(self.lab.seed(), 0)  # at most once an hour

    def test_children_are_parameter_mutants_and_luna_programs_that_pass_the_checks(self):
        self.queue(KNOB)
        self.lab.evaluate_batch()
        self.luna.programs = [SMALLER, "import os\n", KNOB.replace('"BTC/USD"', '"SPY"')]
        calls = self.lab.breed()
        self.assertEqual(calls, 1)
        origins = {}
        for row in self.lab._q("SELECT * FROM candidates WHERE status='queued'"):
            origins[row["origin"]] = origins.get(row["origin"], 0) + 1
            self.assertIsNotNone(static_literal(row["code"], "PARAMS"))
        self.assertGreaterEqual(origins.get("param", 0), 1)
        self.assertEqual(origins.get("luna"), 1)  # the unsafe file and the other desk's were refused
        call = self.lab._q("SELECT * FROM calls")[0]
        self.assertEqual((call["kind"], call["written"], call["refused"]), ("luna", 1, 2))
        packet = self.luna.asked[0]["user"]
        self.assertIn("folds", packet["parent"]["results"])
        self.assertIn("code", packet["parent"])
        self.assertTrue(all("code" not in n for n in packet["neighbours"]))

    def test_every_nth_call_is_a_sol_leap(self):
        self.house.game["lab"]["leap_every"] = 1
        self.house.niches = {DESK: self.niche}  # the leap goes to the emptiest desk: here the only one
        self.queue(KNOB)
        self.lab.evaluate_batch()
        self.sol.programs = [KNOB.replace("notional", "size")]
        self.lab.breed()  # no Luna call yet since the last Sol one: 0 < 1
        self.lab.breed()
        kinds = [r["kind"] for r in self.lab._q("SELECT kind FROM calls ORDER BY at")]
        self.assertEqual(kinds, ["luna", "sol"])
        self.assertIn("archive", self.sol.asked[0]["user"])
        leapt = self.lab._q("SELECT * FROM candidates WHERE origin='sol'")
        self.assertEqual(len(leapt), 1)
        self.assertTrue(leapt[0]["lineage"].startswith("sol:"))


class Spend(LabCase):
    def test_the_lab_stays_under_its_line(self):
        self.house.game["lab"]["budget_usd_per_hour"] = "0.05"
        self.luna.cost = D("0.02")
        self.queue(KNOB)
        self.lab.evaluate_batch()
        made = sum(self.lab.mutate_llm() for _ in range(6))
        self.assertLessEqual(self.lab.spent_last_hour(), D("0.05"))
        self.assertLess(made, 6)
        self.assertIn("line", self.lab.refusal)
        self.clock.advance(3601)
        self.assertTrue(self.lab.mutate_llm())  # a new hour, a new line

    def test_no_paid_call_below_the_all_tier_or_with_the_allowance_closed(self):
        self.queue(KNOB)
        self.lab.evaluate_batch()
        with patch.object(self.house, "frontier_tier", return_value="earned"):
            self.assertFalse(self.lab.mutate_llm())
            self.assertIn("tier", self.lab.open())
        self.house.pacer.may_spend = lambda kind: kind != "openai"
        self.assertFalse(self.lab.mutate_llm())
        self.assertEqual(self.luna.asked, [])

    def test_royalties_extend_the_line(self):
        self.house.game["lab"]["budget_usd_per_hour"] = "0"
        self.queue(KNOB)
        self.lab.evaluate_batch()
        self.assertFalse(self.lab.mutate_llm())
        self.house.ledger.append("lab.royalty", {"fee": "f", "agent": "x", "lineage": "l", "fee_usd": "10", "usd": "1.00", "share": "0.10"},
                                 id="lab.royalty:f")
        self.assertTrue(self.lab.mutate_llm())
        self.assertEqual(self.lab.royalty_balance(), D("1.00") - D("0.01"))


class Graduation(LabCase):
    def test_a_seed_or_a_running_program_is_never_graduated(self):
        seed = self.queue(KNOB)  # a seed: a parent only
        child = self.queue(SPARSE, origin="luna")
        self.lab.evaluate_batch()
        self.seated("already", SPARSE)  # and a living agent already runs the child's program
        self.assertEqual(self.lab.graduate(), [])
        self.assertTrue(self.candidate(seed)["gate"] and self.candidate(child)["gate"])

    def evolve(self, *codes):
        ids = [self.queue(code, origin="luna") for code in codes]
        self.lab.evaluate_batch()
        return ids

    def test_seeds_to_mutations_to_the_archive_to_a_graduate_born_on_paper(self):
        seed = self.seated("sawtooth", KNOB)
        self.lab.seed(force=True)
        out = self.lab.step()
        self.house.wait()
        self.assertGreaterEqual(out["evaluated"], 2)
        self.assertGreaterEqual(out["archived"], 1)
        self.assertGreaterEqual(out["calls"], 1)  # Luna was asked once the seeds were in the archive
        self.assertTrue(self.luna.asked)
        born = [a for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")]
        self.assertEqual(len(born), 1)
        child = born[0]
        self.assertEqual(self.house.evaluator.rung(child.id), 1)  # seated on paper
        self.assertEqual(child.specialty, DESK)
        self.assertIsNotNone(self.house.books["alpaca-paper"].accounts.get(child.id))
        trials = [e for e in self.house.ledger.iter(kinds="eval.trial", agent=child.id)]
        self.assertEqual(len(trials), 1)  # the House's own replay, a counted trial on its own line
        self.assertTrue(trials[0].payload["passed"])
        route = self.house.ledger.get(f"birth-route:{child.id}")
        self.assertEqual(route.payload["route"], "lab")
        grads = [e.payload for e in self.house.ledger.iter(kinds="lab.graduate")]
        self.assertEqual([g["state"] for g in grads], ["passed", "born"])
        self.assertEqual(grads[-1]["agent"], child.id)
        self.assertIn(grads[-1]["origin"], ("param", "luna"))  # a seed is a parent, never a graduate
        self.assertIn(grads[-1]["author"], ("house", "luna"))  # authorship on every graduate
        self.assertEqual(grads[-1]["lineage"], f"agent:{seed.id}")
        self.assertTrue(grads[-1]["lineage"])
        stats = [e.payload for e in self.house.ledger.iter(kinds="lab.stats")]
        self.assertTrue(stats and stats[-1]["evaluated"] >= 2 and stats[-1]["born_total"] == 1)

    def test_a_failed_house_replay_is_not_born(self):
        (ident,) = self.evolve(KNOB)
        with patch.object(self.house, "_candidate_replay", return_value={"counted_as_trial": True, "passed": False,
                                                                        "numbers": {"reasons": ["out-of-sample growth is not above zero"]}}):
            out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "replay_failed")
        self.assertFalse([a for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")])
        self.assertEqual(self.lab.graduate(), [])  # tried once

    def test_the_birth_cap(self):
        self.house.game["lab"]["max_births_per_hour"] = 1
        self.house.game["lab"]["max_graduations_per_step"] = 5
        self.evolve(KNOB, SPARSE)
        self.assertEqual(len({r["cell"] for r in self.lab._q("SELECT cell FROM archive")}), 2, "two cells: two graduates to be")
        self.lab.graduate()
        self.assertEqual(self.lab.births_last_hour(), 1)
        self.assertEqual(self.lab.graduate(), [])
        self.clock.advance(3601)
        self.lab.graduate()
        self.assertEqual(sum(1 for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")), 2)

    def test_a_full_desk_makes_the_graduate_wait_for_a_seat(self):
        self.evolve(KNOB)
        self.niche.max_members = 1
        self.seated("resident", IDLE)
        with patch.object(self.house, "_weakest", return_value=None):
            out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "waiting_seat")
        self.assertEqual(self.lab._q("SELECT state FROM graduations")[0]["state"], "passed")
        resident = self.house.registry.get("resident")
        with patch.object(self.house, "_weakest", return_value=resident):
            out = self.lab.graduate()
        self.assertEqual(out[0]["state"], "born")
        self.assertFalse(self.house.registry.get("resident").alive)

    def test_a_development_pass_goes_to_the_sealed_holdout_through_the_house(self):
        self.evolve(KNOB)
        passed = {"counted_as_trial": True, "passed": True, "numbers": {}, "needs": static_literal(KNOB, "NEEDS"),
                  "params": {"notional": 50.0}, "walk_forward": []}
        with patch.object(self.house, "_candidate_replay", return_value=passed), \
                patch.object(self.house, "_holdout", return_value={"evaluated": True, "passed": False}) as holdout:
            out = self.lab.graduate()
        holdout.assert_called_once()
        self.assertEqual(out[0]["state"], "holdout_failed")
        self.assertFalse([a for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")])

    def test_one_lineage_cannot_probe_the_holdout_through_many_lines(self):
        first, second = self.evolve(KNOB, SPARSE)
        lineage = self.candidate(first)["lineage"]
        self.assertEqual(lineage, self.candidate(second)["lineage"])
        budget = self.house.settings.holdout_lineage_budget
        for n in range(budget):
            line = f"meriwether-lspent{n}"
            self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                        (f"spent{n}", DESK, lineage, line, "f", "holdout_failed", self.clock(), ""))
            self.house.ledger.append("holdout.access", {"agent": line, "lineage": line, "version": f"v{n}", "state": "opened",
                                                        "window": ["a", "b"]}, agent=line, id=f"holdout:v{n}:opened")
        with patch.object(self.lab, "_deep", return_value=True), patch.object(self.house, "_candidate_replay") as replay:
            out = self.lab.graduate()
        replay.assert_not_called()
        self.assertEqual(out[0]["state"], "holdout_rationed")


class Royalties(LabCase):
    def test_a_graduates_performance_fee_pays_the_lab_once(self):
        graduate = self.house.spawn("grad", "lab-family", KNOB, reason="a lab graduate", founder="lab:agent:mullins-2")
        other = self.house.spawn("other", "test-family", SMALLER, reason="not the lab's")
        before = self.house.economy.balance(graduate.id)
        self.house.economy.grant(graduate.id, "2.00", "performance fee", id="fee:settle:1")
        self.house.economy.grant(other.id, "2.00", "performance fee", id="fee:settle:2")
        self.house.economy.grant(graduate.id, "1.00", "payout", id="payout:1")
        self.assertEqual(self.lab.royalties(), 1)
        self.assertEqual(self.lab.royalties(), 0)
        self.lab._set_meta("fee_cursor", "0")  # a crash before the cursor was saved: replayed, never doubled
        self.lab.royalties()
        rows = [e.payload for e in self.house.ledger.iter(kinds="lab.royalty")]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["usd"], rows[0]["lineage"], rows[0]["fee"]), ("0.2000", "agent:mullins-2", "fee:settle:1"))
        self.assertEqual(self.house.economy.balance(graduate.id), before + D("2.00") + D("1.00") - D("0.20"))
        self.assertEqual(self.lab.royalty_balance(), D("0.2000"))
        self.assertGreater(self.lab.lineage_weights()["agent:mullins-2"], 1.0)  # royalties buy the lineage more search


class Search(LabCase):
    def test_a_lineage_whose_graduates_lose_is_searched_less(self):
        winner = self.house.spawn("winner", "lab-a", KNOB, reason="a lab graduate", founder="lab:founder:a")
        loser = self.house.spawn("loser", "lab-b", SMALLER, reason="a lab graduate", founder="lab:founder:b")
        for agent, lineage in ((winner, "founder:a"), (loser, "founder:b")):
            self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, agent, at, detail) VALUES(?,?,?,?,?,?,?,?,?)",
                        (agent.id, DESK, lineage, agent.id, agent.family, "born", agent.id, self.clock(), ""))
        self.house.kill(loser, "paper death", "lost")
        standings = {winner.id: {"earned_growth": 0.01, "earned_observations": 6}}
        with patch.object(self.house, "standing_of", side_effect=lambda a: standings.get(a, {})):
            weights = self.lab.lineage_weights()
        self.assertEqual(weights["founder:a"], 2.0)
        self.assertEqual(weights["founder:b"], 0.5)

    def test_stats_report_throughput_and_pass_rates(self):
        self.queue(KNOB)
        self.queue(LOSER)
        self.lab.evaluate_batch()
        stats = self.lab.publish(force=True)
        self.assertEqual(stats["evaluated"], 2)
        self.assertEqual(stats["stages"]["eligible"], 2)
        self.assertEqual(stats["stages"]["gate"], 1)
        self.assertEqual(stats["pass_rates"]["gate"], 0.5)
        self.assertEqual(stats["coverage"]["by_desk"], {DESK: 1})
        row = self.house.ledger.last("lab.stats")
        self.assertFalse(row.public)
        self.assertEqual(row.payload["evaluated"], 2)


class Researchers(LabCase):
    def researcher(self):
        return Researcher(ledger=self.house.ledger, provider=None, commons=self.house.commons, economy=self.house.economy,
                          rules="", contract="", run_replay=lambda a, c: {}, settings={"max_turns": 10})

    def test_submit_then_query_on_a_later_pass(self):
        agent = self.seated("sawtooth", KNOB)
        research = self.researcher()
        research.lab = self.lab
        out = research._execute(agent, "lab_submit", {"candidates": [{"code": SMALLER, "idea": "half the size"},
                                                                     {"code": "import os\n"}]}, None, "s1")
        self.assertEqual(len(out["queued"]), 1)
        self.assertEqual(len(out["refused"]), 1)
        public = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual(public["arguments"], {"candidates": "2 programs"})  # no code on the public ledger
        self.lab.evaluate_batch()
        seen = research._execute(agent, "lab_query", {}, None, "s2")
        self.assertEqual(seen["desk"], DESK)
        mine = seen["your_submissions"][0]
        self.assertEqual(mine["status"], "evaluated")
        self.assertIn("folds", mine["results"])
        self.assertNotIn("code", json.dumps(seen["archive"]) + json.dumps(seen["leaderboard"]))
        self.assertTrue(seen["archive"])

    def test_submissions_are_capped(self):
        agent = self.seated("sawtooth", KNOB)
        self.lab.seed(force=True)  # its own program queued as a seed is not a submission
        self.house.game["lab"]["submit_max"] = 2
        programs = [{"code": KNOB.replace("50.0", f"{10 + n}.0")} for n in range(4)]
        out = self.lab.submit(agent, programs)
        self.assertEqual(len(out["queued"]), 2)
        self.assertEqual(self.lab.submit(agent, programs[2:])["queued"], [])

    def test_the_lab_tools_are_offered_only_where_the_lab_runs(self):
        names = [t["name"] for t in TOOLS]
        self.assertNotIn("lab_query", names)
        self.assertEqual({t["name"] for t in LAB_TOOLS}, {"lab_query", "lab_submit"})
        agent = self.seated("sawtooth", KNOB)
        research = self.researcher()
        self.assertIn("not running", research._execute(agent, "lab_query", {}, None, "s")["error"])

    def test_agents_with_evidence_get_longer_sessions(self):
        research = self.researcher()
        agent = self.seated("sawtooth", KNOB)
        self.assertEqual(research._evidence_turns(agent, {"max_turns": 10})["max_turns"], 10)
        research.evidence = lambda a: True
        self.assertEqual(research._evidence_turns(agent, {"max_turns": 10})["max_turns"], 20)
        self.assertEqual(research._evidence_turns(agent, {"max_turns": 10, "evidence_max_turns": 14})["max_turns"], 14)
        research.evidence = lambda a: False
        self.assertEqual(research._evidence_turns(agent, {"max_turns": 10})["max_turns"], 10)
        self.assertFalse(lab_module.has_evidence(self.house, agent))  # on paper, but no closed trade yet
        with patch.object(self.house, "_recent_trades", return_value=[{"pnl_usd": "0.1"}]):
            self.assertTrue(lab_module.has_evidence(self.house, agent))


@unittest.skipUnless(importlib.util.find_spec("league.labbox"), "the lab box's evaluator (league/labbox.py) is not in this tree")
class RealLabBox(LabCase):
    """The same batch through D-core's `LabBox` over the local sandbox: the lab scores it exactly as it
    scores a batch of single replays."""

    def test_the_real_batch_evaluator_scores_as_single_replays_do(self):
        from league.labbox import LabBox

        ids = [self.queue(code) for code in (KNOB, LOSER, SPARSE)]
        single = Lab(self.house, box=FakeBox(), mutator=self.luna, leaper=self.sol, path=self.house.root / "lab-single.sqlite")
        self.addCleanup(single.close)
        for code in (KNOB, LOSER, SPARSE):
            single.admit(code, niche=self.niche, origin="seed", author="house", lineage="founder:test")
        single.evaluate_batch()
        self.lab.use_box(LabBox(self.house.sandbox, box_key="lab", clock=self.clock))
        self.assertEqual(self.lab.evaluate_batch()["candidates"], 3)
        for ident in ids:
            batch, alone = self.candidate(ident), single._q("SELECT * FROM candidates WHERE id=?", (ident,))[0]
            for field in ("status", "eligible", "gate", "fitness", "trades", "cell"):
                self.assertEqual(batch[field], alone[field], f"{ident} {field}")


class Wiring(LabCase):
    def test_the_lab_box_key_comes_from_config(self):
        from league.service import lab_box_key

        self.assertEqual(lab_box_key({}), "")
        self.assertEqual(lab_box_key({"lab": {"box_key": "lab"}}), "")  # no box named: no lab
        self.assertEqual(lab_box_key({"lab": {"box_id": "sb_x"}}), "lab")
        self.assertEqual(lab_box_key({"lab": {"box_id": "sb_x", "box_key": "ltcm-lab"}}), "ltcm-lab")
        self.assertEqual(lab_box_key({"lab": {"box_id": "sb_x", "enabled": False}}), "")
        self.assertEqual(lab_box_key({"lab": {"box_id": "sb_x"}}, canary=True), "")

    def test_the_house_builds_the_lab_only_with_a_lab_box(self):
        self.assertIsNone(self.new_house().lab)  # enabled in game.json, but no box configured
        from pathlib import Path

        from league.house import House, Settings
        from league.sandbox import LocalSandbox

        house = House(Path(self.dir.name) / "house2", brokers={"alpaca-paper": self.broker}, sandbox=LocalSandbox(Path(self.dir.name) / "boxes2"),
                      alpaca_data=self.data, clock=self.clock, game=self.house.game,
                      settings=Settings(mark_every_seconds=0, research=False, lab_box="ltcm-lab"))
        try:
            self.assertIsInstance(house.lab, Lab)
            self.assertEqual(house.lab.box_key, "ltcm-lab")
            house.lab.close()
        finally:
            house.close(wait=None)  # before the test's directory is removed

    def test_the_tick_schedules_a_step_off_the_tick(self):
        with patch.object(self.lab, "step") as step:
            self.assertTrue(self.lab.tick(open_for_business=True))
            self.house.wait()
        step.assert_called_once()
        self.assertIn(LAB_JOB, self.house._jobs)
        self.assertTrue(LAB_JOB.startswith("replay"))
        self.assertFalse(self.lab.tick(open_for_business=False))
        with patch.object(self.house, "paused", return_value={"reason": "test"}):
            self.assertFalse(self.lab.tick(open_for_business=True))
            self.assertIn("pause", self.lab.refusal)

    def test_a_house_tick_runs_the_lab(self):
        with patch.object(self.lab, "tick") as tick:
            self.house.tick()
        tick.assert_called_once()


if __name__ == "__main__":
    unittest.main()
