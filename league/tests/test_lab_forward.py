"""The Alpha Lab after S2 (Sept 23, 2026): the LLM-written children reach batches, the holdout ration
is checked before any House trial whatever the tape cache holds, forward windows score only data that
came after a program's code was frozen and rank (seats, cells, breeding) without ever promoting or
touching the seal, the floor's practice and real records feed the search share within bounds, and
the teacher's lessons pause a lineage's parameter forks until its forward window is positive."""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

from league.lab import PRIORITY, Lab, forward_cut, parse_priors, static_literal, tape_key, with_params
from league.tests.test_house import IDLE
from league.tests.test_lab import DESK, KNOB, SMALLER, SPARSE, FakeBox, LabCase

#: The elite's program written again by Luna: another style, another set of bounds, the same tape.
LLM_CHILDREN = [KNOB.replace('"style": "sawtooth"', f'"style": "{style}"') for style in ("bolder", "sparser", "crossed")]
LESSON = Path(__file__).resolve().parents[1] / "playbook" / "2026-09-23-pause-prior-window-fade-forks.md"


class RecordingBox(FakeBox):
    """`FakeBox` that also keeps every tape it was handed."""

    def __init__(self):
        super().__init__()
        self.tapes = []

    def evaluate(self, candidates, tape_id, tape, *, stake, limits, timeout=600):
        self.tapes.append(tape)
        return super().evaluate(candidates, tape_id, tape, stake=stake, limits=limits, timeout=timeout)


class ForwardCase(LabCase):
    def setUp(self):
        super().setUp()
        self.box = RecordingBox()
        self.lab.use_box(self.box)

    def elite(self, code=KNOB, origin="luna", lineage="founder:test"):
        ident = self.queue(code, origin=origin, lineage=lineage)
        self.lab.evaluate_batch()
        return ident

    def forward_row(self, ident, mean, active=5, blocks=6, ok=1):
        self.lab._x("INSERT INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                    " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ident, self.clock(), self.clock() - 3600, self.clock(), "fwd:test", ok, blocks, active, mean * blocks, mean, 4, None))
        self.lab._weights = None


class Batches(LabCase):
    """The study of Sept 23, 2026 (17:05Z): none of the lab's 394 Luna and Sol children had been
    evaluated in six hours while 1,358 parameter mutants were, because a child sat at priority 2
    behind its elite's dozens of mutants, and -- keyed by its whole NEEDS, which always differ from
    the parent's in `style` -- looked like a tape of its own that the step's few builds never reached."""

    def test_llm_children_are_evaluated_within_two_batches_behind_forty_mutants_and_a_queue_of_seeds(self):
        self.house.game["lab"]["max_tapes_per_step"] = 1
        self.house.game["lab"]["reserved_share"] = 0.5  # E1's turns (F1's game file keeps a third: test_lab_forward_first)
        elite = self.queue(KNOB)
        self.lab.evaluate_batch()  # the elite: its tape built and kept by the lab
        for n in range(40):  # its parameter mutants, oldest, all on its tape
            self.lab.admit(with_params(KNOB, {"notional": 10.0 + n}), niche=self.niche, origin="param", author="house", lineage="founder:test", parents=[elite])
        self.clock.advance(60)
        variants = [KNOB.replace('"symbols": ["BTC/USD"]', f'"symbols": ["{symbol}"]').replace('"timeframe": "5Min"', f'"timeframe": "{frame}"')
                    for symbol in ("BTC/USD", "ETH/USD") for frame in ("15Min", "1Hour", "1Day")]
        for n, code in enumerate(variants):  # seeds ahead of the children, each on a tape not built yet
            self.lab.admit(code, niche=self.niche, origin="seed", author="house", lineage=f"seed:{n}", idea=f"seed {n}")
        self.clock.advance(60)
        children = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:test", parents=[elite]) for code in LLM_CHILDREN]
        self.assertEqual({self.candidate(c)["priority"] for c in children}, {PRIORITY["luna"]})
        sizes = []
        for _ in range(2):
            self.lab._tapes_built = 0  # a new step's tape budget
            out = self.lab.evaluate_batch()
            sizes.append(out["candidates"] if out else 0)
        self.assertEqual([self.candidate(c)["status"] for c in children], ["evaluated"] * 3, sizes)
        self.assertGreaterEqual(max(sizes), 32)  # the mutants ran with the children on the elite's tape
        # The seeds still have their turn, once the mutants left over have had the largest group's (since
        # Sept 24, 2026 one batch in four is the queue's at the half, E1: `batch_turn`).
        self.lab._tapes_built = 0
        self.assertEqual(self.lab.evaluate_batch()["candidates"], 1)

    def test_a_share_of_a_batch_is_the_written_programs_and_the_rest_the_mutants(self):
        """A third until Sept 24, 2026; `reserved_share`, a half, since (E1, test_lab_search)."""
        self.house.game["lab"]["batch_size"] = 6
        elite = self.queue(KNOB)
        self.lab.evaluate_batch()
        for n in range(12):
            self.lab.admit(with_params(KNOB, {"notional": 10.0 + n}), niche=self.niche, origin="param", author="house", lineage="founder:test", parents=[elite])
        self.clock.advance(60)
        children = [self.lab.admit(code, niche=self.niche, origin="luna", author="luna", lineage="founder:test") for code in LLM_CHILDREN]
        self.lab._batch_turn = 1  # the next turn serves the largest group
        picked = self.lab._next_batch()
        self.assertIsNotNone(picked)
        _, _, chosen = picked
        self.assertEqual(len(chosen), 6)
        self.assertEqual([r["origin"] for r in chosen[:3]], ["luna", "luna", "luna"])  # half of six, first
        self.assertEqual({r["id"] for r in chosen[:3]}, set(children))

    def test_a_queue_admitted_at_the_old_priority_is_re_keyed_when_the_lab_opens(self):
        """The floor's lab.sqlite of Sept 23, 2026 held 394 Luna and Sol children queued at priority 2."""
        ident = self.lab.admit(LLM_CHILDREN[0], niche=self.niche, origin="luna", author="luna", lineage="founder:test")
        self.lab._x("UPDATE candidates SET priority=2 WHERE id=?", (ident,))
        self.lab.close()
        self.lab = Lab(self.house, box=FakeBox(), mutator=self.luna, leaper=self.sol)
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        self.assertEqual(self.candidate(ident)["priority"], PRIORITY["luna"])

    def test_the_tape_key_ignores_what_the_tape_does_not_depend_on(self):
        needs = static_literal(KNOB, "NEEDS")
        same = {**needs, "style": "another", "parameter_rules": {"bounds": {"notional": [1, 100]}}, "wake_minutes": 15, "max_hours_to_close": 2}
        self.assertEqual(tape_key(same), tape_key(needs))
        self.assertNotEqual(tape_key({**needs, "symbols": ["ETH/USD"]}), tape_key(needs))
        ident = self.queue(KNOB)
        self.lab.evaluate_batch()
        self.lab._tapes_built = 0
        tape_id, _ = self.lab._search_tape(same)  # the parent's tape, no build of its own
        self.assertEqual(tape_id, self.candidate(ident)["tape_id"])
        self.assertEqual(self.lab._tapes_built, 0)
        self.assertEqual(self.lab.ready_queued(), 0)
        self.lab.admit(LLM_CHILDREN[0], niche=self.niche, origin="luna", author="luna", lineage="founder:test")
        self.assertEqual(self.lab.ready_queued(), 1)  # a child on a built tape counts as ready


class Rationing(LabCase):
    """The ration check comes before the House's replay (a counted trial on the lineage's line):
    the ledger of Sept 23, 2026 shows no trial on any of the 14 rationed lines, and after S2 the
    answer to 'was this searched on the development window' is kept with the candidate's own
    result, so a restart (an empty tape cache) cannot turn the check off."""

    def test_a_rationed_lineage_is_refused_before_any_trial_after_a_restart(self):
        ident = self.queue(KNOB, origin="luna")
        real = self.house.tape_for

        def development(needs):
            key, tape = real(needs)
            return key, {**tape, "source": {"store": "history", "window": ["2025-03-01", "2025-11-14"]}}

        with patch.object(self.house, "tape_for", side_effect=development):
            self.lab.evaluate_batch()
        self.forward_wins(ident)  # F1: a winning forward window of its own before the House's replay
        row = self.candidate(ident)
        self.assertEqual(json.loads(row["summary"])["tape_source"], "history-dev")
        lineage = row["lineage"]
        for n in range(self.house.settings.holdout_lineage_budget):
            line = f"rosenfeld-lspent{n}"
            self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                        (f"spent{n}", DESK, lineage, line, "f", "holdout_failed", self.clock(), ""))
            self.house.ledger.append("holdout.access", {"agent": line, "lineage": line, "version": f"v{n}", "state": "opened",
                                                        "window": ["a", "b"]}, agent=line, id=f"holdout:v{n}:opened")
        self.lab._tapes.clear()  # a restart emptied the cache
        with patch.object(self.house.settings, "deep_replay", False), patch.object(self.house, "_candidate_replay") as replay:
            out = self.lab.graduate()
        replay.assert_not_called()
        self.assertEqual(out[0]["state"], "holdout_rationed")
        self.assertEqual([e.kind for e in self.house.ledger.iter(kinds="eval.trial")], [])


class ForwardWindows(ForwardCase):
    def test_a_window_is_only_the_data_after_the_freeze_and_ranks_without_promoting(self):
        ident = self.elite()
        row = self.candidate(ident)
        frozen = float(row["evaluated"])
        cut = math.ceil(frozen / 3600.0) * 3600.0
        archive = self.lab._q("SELECT * FROM archive")[0]
        head = self.house.ledger.head()[0]
        self.assertIsNone(self.lab.forward_score(ident))
        out = self.lab.forward_windows(force=True)
        self.assertEqual((out["candidates"], out["scored"], out["batches"]), (1, 1, 1))
        tape = self.box.tapes[-1]
        from league.lab import _ts

        self.assertTrue(all(_ts(s["t"]) > cut for s in tape["steps"]))
        self.assertTrue(tape["warmup_bars"]["BTC/USD"])  # the bars before the cut are history, not steps
        self.assertTrue(all(_ts(b["t"]) <= cut for b in tape["warmup_bars"]["BTC/USD"]))
        self.assertEqual(tape["forward_cut"], "2026-09-11T12:00:00Z")  # `test_lab.LAB_CLOCK_OFFSET` into the fake tape
        record = self.lab.forward_record(ident)
        self.assertEqual(record["window_start"], cut)
        self.assertGreaterEqual(record["window_start"], frozen)
        self.assertGreater(record["blocks"], 3)
        self.assertGreater(record["trades"], 0)
        self.assertIsInstance(self.lab.forward_score(ident), float)
        # Nothing else moved: not the fitness, the gate, the cell, the archive, the ledger's evidence.
        after = self.candidate(ident)
        for field in ("fitness", "gate", "eligible", "cell", "status"):
            self.assertEqual(after[field], row[field], field)
        self.assertEqual(dict(self.lab._q("SELECT * FROM archive")[0]), dict(archive))
        kinds = {e.kind for e in self.house.ledger.iter(after=head)}
        self.assertFalse(kinds & {"eval.trial", "eval.verdict", "holdout.access", "agent.born", "lab.graduate"}, kinds)
        self.assertEqual([a for a in self.house.registry.living() if str(a.founder or "").startswith("lab:")], [])
        stats = self.lab.stats()["forward"]
        self.assertEqual((stats["records"], stats["ranked"], stats["last_run"]["scored"]), (1, 1, 1))
        self.assertEqual(self.lab.health()["forward"]["records"], 1)

    def test_a_program_frozen_after_the_tapes_end_has_no_window_yet(self):
        self.clock.advance(4 * 86400)  # the fake tape ends on Sept 12
        ident = self.elite()
        out = self.lab.forward_windows(force=True)
        self.assertEqual(out["scored"], 0)
        self.assertEqual(out["skipped"], {"no forward data yet": 1})
        self.assertIsNone(self.lab.forward_record(ident))
        self.assertIsNone(self.lab.forward_score(ident))
        self.assertEqual([t for t in self.box.tapes if "forward_cut" in t], [])  # only the search batch reached the box

    def test_forward_cut_keeps_kalshi_series_whole_and_answers_none_without_data(self):
        steps = [{"t": f"2026-09-10T{h:02d}:00:00Z", "markets": []} for h in range(6)]
        tape = {"venue": "kalshi", "steps": steps, "observed_bars": {"BTC/USD": [{"t": "2026-09-10T00:00:00Z", "c": 1.0}]}, "results": {"m": 1}}
        cut = forward_cut(tape, float(__import__("calendar").timegm((2026, 9, 10, 3, 0, 0))))
        self.assertEqual([s["t"] for s in cut["steps"]], [s["t"] for s in steps[4:]])
        self.assertEqual(cut["observed_bars"], tape["observed_bars"])
        self.assertEqual(cut["results"], tape["results"])
        self.assertEqual(len(tape["steps"]), 6)  # the House's tape is untouched
        self.assertIsNone(forward_cut(tape, float(__import__("calendar").timegm((2026, 9, 10, 6, 0, 0)))))

    def test_runs_are_hourly_bounded_and_resume_from_the_table_after_a_restart(self):
        self.house.game["lab"]["forward_candidates_per_run"] = 1
        first, second = self.elite(KNOB), self.elite(SPARSE, lineage="founder:other")
        self.assertEqual(len(self.lab._q("SELECT * FROM archive")), 2)
        out = self.lab.forward_windows(force=True)
        self.assertEqual(out["scored"], 1)
        scored = {r["candidate"] for r in self.lab._q("SELECT candidate FROM forward")}
        self.assertEqual(scored, {first})  # never scored first, oldest evaluation first
        self.assertIsNone(self.lab.forward_windows())  # not for another hour
        self.lab.close()
        self.lab = Lab(self.house, box=self.box, mutator=self.luna, leaper=self.sol)
        self.house.lab = self.lab
        self.addCleanup(self.lab.close)
        self.assertIsNone(self.lab.forward_windows())  # the stamp is in the store, not in memory
        self.clock.advance(3601)
        out = self.lab.forward_windows()
        self.assertEqual(out["scored"], 1)
        self.assertEqual({r["candidate"] for r in self.lab._q("SELECT candidate FROM forward")}, {first, second})
        self.clock.advance(3601)
        self.house.game["lab"]["forward_box_seconds"] = 0  # the run's box time is spent before it starts
        out = self.lab.forward_windows()
        self.assertEqual(out["scored"], 0)
        self.assertEqual(sum(out["skipped"].values()), 1)
        # A step runs the windows once they are due, on its own lane.
        self.clock.advance(3601)
        self.house.game["lab"]["forward_box_seconds"] = 90
        with patch.object(self.lab, "graduate", return_value=[]):
            out = self.lab.step()
        self.assertEqual(out["forward"]["scored"], 1)

    def test_forward_records_rank_cells_seats_and_breeding(self):
        loser, winner, untested = self.elite(KNOB), self.elite(SPARSE, lineage="founder:winner"), self.elite(IDLE, lineage="founder:new")
        self.assertEqual(len(self.lab._q("SELECT * FROM archive")), 2)  # IDLE never trades: no cell
        self.forward_row(loser, -0.01)
        self.forward_row(winner, 0.005)
        self.forward_row(untested, 0.02, active=1)  # too few active blocks to rank anything
        self.assertGreater(self.lab.forward_score(winner), 0)
        self.assertLess(self.lab.forward_score(loser), 0)
        self.assertIsNone(self.lab.forward_score(untested))
        fitness = {r["id"]: r["fitness"] for r in self.lab._q("SELECT id, fitness FROM candidates")}
        self.assertGreater(fitness[loser], fitness[winner])  # on the search tape the loser looked better ...
        self.assertEqual([r["id"] for r in self.lab.elites()], [winner, loser])  # ... the forward window ranks it last
        weights = self.lab.lineage_weights()
        self.assertEqual((weights["founder:winner"], weights["founder:test"]), (2.0, 0.5))
        self.assertNotIn("founder:new", weights)
        # A graduate waiting for a seat carries its forward score for the House's seat market.
        self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, at, detail) VALUES(?,?,?,?,?,?,?,?)",
                    (winner, DESK, "founder:winner", "rosenfeld-lwinner", "f", "passed", self.clock(), "its desk is full of agents that have earned their seats"))
        self.assertEqual(self.lab.waiting()[0]["forward"], self.lab.forward_score(winner))
        self.assertEqual(self.lab.health()["waiting_seat"]["graduates"][0]["forward"], self.lab.forward_score(winner))


class FloorFeedback(ForwardCase):
    def born(self, name, family, lineage, code=KNOB):
        agent = self.house.spawn(name, family, code, reason="a lab graduate", founder=f"lab:{lineage}")
        self.lab._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, agent, at, detail) VALUES(?,?,?,?,?,?,?,?,?)",
                    (name, DESK, lineage, agent.id, agent.family, "born", agent.id, self.clock(), ""))
        return agent

    def test_practice_and_real_records_move_the_share_within_bounds(self):
        self.born("winner", "lab-a", "founder:a")
        self.born("loser", "lab-b", "founder:b", SMALLER)
        self.born("green", "lab-c", "founder:c", SPARSE)
        board = {"agents": {"winner": {"evidence": {"W_paper": 1.03, "W_real": 1.02, "trades": 5, "real_trades": 2}},
                            "loser": {"evidence": {"W_paper": 0.97, "W_real": 0.90, "trades": 5, "real_trades": 1}},
                            "green": {"evidence": {"W_paper": 1.10, "W_real": 1.0, "trades": 2, "real_trades": 0}}}}
        with patch.object(self.house.allocator, "board", return_value=board):
            weights = self.lab.lineage_weights()
        self.assertEqual(weights["founder:a"], 4.0)  # practice +1, real +1
        self.assertEqual(weights["founder:b"], 0.25)  # practice -1, real -1
        self.assertEqual(weights["founder:c"], 1.0)  # two closed trades say nothing yet
        # The bounds: however many graduates lose, a lineage keeps an eighth of the search; however many win, at most eight times.
        for n in range(4):
            self.born(f"loser{n}", "lab-b", "founder:b", with_params(KNOB, {"notional": 11.0 + n}))
            self.born(f"winner{n}", "lab-a", "founder:a", with_params(KNOB, {"notional": 21.0 + n}))
            board["agents"][f"loser{n}"] = board["agents"]["loser"]
            board["agents"][f"winner{n}"] = board["agents"]["winner"]
        self.lab._weights = None
        with patch.object(self.house.allocator, "board", return_value=board):
            weights = self.lab.lineage_weights()
        self.assertEqual((weights["founder:a"], weights["founder:b"]), (8.0, 0.125))
        # Without a board row, the standing decides as before.
        self.lab._weights = None
        standings = {"winner": {"earned_growth": 0.01, "earned_observations": 6}}
        with patch.object(self.house.allocator, "board", return_value={"agents": {}}), \
                patch.object(self.house, "standing_of", side_effect=lambda a: standings.get(a, {})):
            weights = self.lab.lineage_weights()
        self.assertEqual(weights["founder:a"], 2.0)


class Priors(ForwardCase):
    PRIOR = '```lab-prior\n{"rule": "pause-param-forks", "family": "prior-window-fade", "until": "forward-positive"}\n```\n'

    def test_the_lesson_that_paused_prior_window_fade_forks_carries_a_prior(self):
        priors = parse_priors(LESSON.read_text(encoding="utf-8"))
        self.assertEqual(priors, [{"rule": "pause-param-forks", "family": "prior-window-fade", "until": "forward-positive"}])
        self.assertEqual(parse_priors("# A lesson\n\nprose only\n"), [])
        self.assertEqual(parse_priors('```lab-prior\n{"rule": "burn-it-all", "family": "x"}\n```'), [])  # an unknown rule is ignored
        self.assertEqual(parse_priors('```lab-prior\nnot json\n```'), [])

    def test_a_lesson_prior_pauses_the_named_lineages_parameter_forks_until_its_window_is_positive(self):
        fade = self.house.spawn("fade", "eth-prior-window-fade", KNOB, reason="the ETH prior-window fade")
        self.house.evaluator.seat(fade.id, 1, "test")
        self.house._state["tried"][fade.id] = fade.code_sha256
        self.lab.seed(force=True)
        self.lab.evaluate_batch()
        elite = next(r for r in self.lab.elites() if r["lineage"] == f"agent:{fade.id}")
        self.house.game["lab"]["param_children"] = 8
        self.luna.programs = [SMALLER]
        self.house.commons.playbook_add("Lesson: 2026-09-23-pause-prior-window-fade-forks", "# Pause the forks\n\n" + self.PRIOR, source="teacher")
        self.assertEqual(self.lab.paused(elite), "Lesson: 2026-09-23-pause-prior-window-fade-forks")
        self.lab.breed()
        origins = {r["origin"]: r["n"] for r in self.lab._q("SELECT origin, COUNT(*) AS n FROM candidates WHERE status='queued' GROUP BY origin")}
        self.assertNotIn("param", origins)  # no parameter-only fork of the paused lineage ...
        self.assertEqual(origins.get("luna"), 1)  # ... while Luna's rewrite of it still comes
        self.assertEqual(self.lab.stats()["forward"]["priors"]["skipped"], {"Lesson: 2026-09-23-pause-prior-window-fade-forks": 8})
        self.assertEqual(self.lab.stats()["forward"]["priors"]["active"], ["Lesson: 2026-09-23-pause-prior-window-fade-forks"])
        # Lifted once the lineage's own forward window is positive.
        self.forward_row(elite["id"], 0.004)
        self.assertIsNone(self.lab.paused(elite))
        self.lab.breed()
        self.assertGreater(self.lab._q("SELECT COUNT(*) AS n FROM candidates WHERE origin='param'")[0]["n"], 0)

    def test_a_prior_names_a_lineage_a_desk_or_a_cell_and_can_end_on_a_day(self):
        ident = self.elite()
        elite = self.lab.elites()[0]
        for prior, expected in ((f'{{"rule": "pause-param-forks", "lineage": "{elite["lineage"]}"}}', True),
                                ('{"rule": "pause-param-forks", "lineage": "founder:someone-else"}', False),
                                (f'{{"rule": "pause-param-forks", "niche": "{DESK}"}}', True),
                                (f'{{"rule": "pause-param-forks", "cell": "{elite["cell"][:12]}"}}', True),
                                (f'{{"rule": "pause-param-forks", "niche": "{DESK}", "until": "2026-09-01"}}', False),
                                (f'{{"rule": "pause-param-forks", "niche": "{DESK}", "until": "2026-12-01"}}', True)):
            with self.subTest(prior=prior):
                self.lab._priors = None
                with patch.object(self.lab, "priors", return_value=[{**json.loads(prior), "title": "Lesson: t"}]):
                    self.assertEqual(self.lab.paused(elite) is not None, expected)
        self.assertIsNotNone(ident)


if __name__ == "__main__":
    unittest.main()
