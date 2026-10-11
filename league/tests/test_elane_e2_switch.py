"""Release E2 as it ships on E1 (league/swarm/ELANE_E2.md, "The switch"): THE SHIPPED SWITCHES and what they keep still.

- policy.json ships `elane.mode` "off" and `elane.birth_share` 0, and its `elane.e2` block is the code's defaults, key
  for key; the settings layers (league/swarm/settings.py: DEFAULTS < policy.json < swarm.json) take the captain's keys
  (`elane.birth_share`, `elane.e2.usd_day`, any other `elane.e2` key) from swarm.json, one key at a time, and the code
  holds each inside its bound.
- THE LOOP (league/swarm/loop.py `Swarm.step`, E1's real store and settings, no fake of the switch): with `elane.mode`
  "off", or with `elane.birth_share` 0, neither of E2's rounds starts and E2 writes no key, makes no event and asks no
  model. The one thing a zero `birth_share` leaves running is stated and tested: families the equity pass ALREADY bore
  finish their Train research (inside `elane.e2.usd_day`; zero there asks no model).
- THE THREE IDENTITIES: nothing E2 ships is hashed into the equity evidence identity (A13) or the options execution
  fingerprint, and the money rules do not read it.
- THE SCREEN'S NAME (A11): the text every equity generator and reviewer reads names the screen policy.json pins.

Every family and number here is invented."""

from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import elane, elane_births, elane_review, elane_seal, elane_train, elane_yield
from league.swarm import settings as S
from league.tests import REAL_POLICY_PATH
from league.tests import elane_e2_fakes as fx
from league.tests.test_swarm_loop import LoopCase

REPO = Path(__file__).resolve().parents[2]
E2_MODULES = (elane_births, elane_train, elane_review, elane_yield)
E2_FILES = tuple(f"league/swarm/elane_{name}.py" for name in ("births", "train", "yield", "seal", "review"))
#: E2's own footprints in the store's kv: its two rounds' clocks, the last pass, the Train liveness mark, the ledger.
E2_KEYS = (elane_births.BIRTHS_AT_KEY, elane_births.LAST_KEY, elane_train.TRAIN_AT_KEY, elane_train.TRAIN_OK_KEY,
           elane_yield.LEDGER_KEY)


def policy() -> dict:
    """The committed policy.json (the league's other tests read an empty layer in its place: league/tests/__init__.py)."""
    return json.loads(Path(REAL_POLICY_PATH).read_text(encoding="utf-8"))


def shipped() -> dict:
    """The settings as the layers give them with no swarm.json: DEFAULTS under the committed policy.json."""
    return S.load(config={}, policy=policy())


def with_elane(**block) -> dict:
    """`shipped` with `elane` keys laid over as the box's swarm.json lays them (the deep merge `settings.load` does)."""
    return S._merge(shipped(), {"elane": block})


class Shipped(unittest.TestCase):
    def test_policy_ships_the_lanes_off_no_births_and_the_codes_defaults(self):
        block = policy()["elane"]
        self.assertEqual(block["mode"], "off")
        self.assertEqual(block["birth_share"], 0)
        code: dict = {}
        for module in E2_MODULES:
            for key, value in module.DEFAULTS.items():
                self.assertNotIn(key, code, f"{key}: two E2 modules hold a default for it")
                code[key] = value
        self.assertEqual(block["e2"], code, "policy.json's elane.e2 block is the code's defaults, key for key")
        loaded = shipped()
        self.assertEqual(loaded["_policy"]["state"], "ok", loaded["_policy"])
        self.assertFalse(elane.on(loaded))
        self.assertFalse(elane_train.lane_on(loaded))
        self.assertFalse(elane_births.births_on(loaded))
        self.assertEqual(elane_births.birth_share(loaded), 0.0)

    def test_the_settings_take_the_captains_keys_one_at_a_time(self):
        # What the captain sets at the first switch-on (amendment A16): the lanes' share of births and E2's day line.
        s = with_elane(mode="gate", birth_share=0.25, e2={"usd_day": 8.0})
        self.assertEqual(S.policy_shape(policy()), [], "the nested e2 object breaks no shape of the defaults")
        self.assertTrue(elane_births.births_on(s))
        self.assertEqual(elane.cfg(s)["birth_share"], 0.25)
        self.assertEqual(elane_yield.cfg(s)["usd_day"], 8.0)
        # One key of the block moved; every other key is still policy.json's (the layers merge deep).
        block = policy()["elane"]["e2"]
        self.assertEqual({k: v for k, v in s["elane"]["e2"].items() if k != "usd_day"},
                         {k: v for k, v in block.items() if k != "usd_day"})
        self.assertEqual(s["elane"]["screens"], policy()["elane"]["screens"], "the pinned screens are not the switch's")
        half = with_elane(mode="gate", birth_share=0.25, e2={"usd_day": 3.5, "max_alive": 12})
        self.assertEqual(elane_yield.cfg(half)["usd_day"], 3.5)
        self.assertEqual(elane_births.cfg(half)["max_alive"], 12)
        self.assertEqual(elane_births.cfg(half)["max_per_pass"], block["max_per_pass"])

    def test_every_key_is_held_inside_its_bound(self):
        # `elane.birth_share` is E1's (`elane.cfg`): held to [0, 0.5], and anything that is no number is zero.
        for raw, want in ((0.25, 0.25), (0.5, 0.5), (0.9, 0.5), (5, 0.5), (-0.1, 0.0), ("0.25", 0.0), (True, 0.0),
                          (None, 0.0), (math.nan, 0.0), (math.inf, 0.0), ([0.25], 0.0)):
            s = with_elane(mode="gate", birth_share=raw)
            self.assertEqual(elane_births.birth_share(s), want, raw)
            self.assertEqual(elane_births.births_on(s), want > 0, raw)
        # `elane.e2.usd_day`: 0 (no model is asked) to 100 dollars a UTC day; anything else is the default.
        default = elane_yield.DEFAULTS["usd_day"]
        for raw, want in ((8.0, 8.0), (0, 0.0), (0.0, 0.0), (100, 100.0), (100.01, default), (-1, default),
                          ("8", default), (True, default), (None, default), (math.nan, default), (math.inf, default)):
            self.assertEqual(elane_yield.cfg(with_elane(e2={"usd_day": raw}))["usd_day"], want, raw)
        # Every numeric key of the block: a value outside its bound, or no number, is the code's default.
        for module in E2_MODULES:
            self.assertTrue(module.BOUNDS)
            for key, (low, high) in module.BOUNDS.items():
                self.assertIn(key, module.DEFAULTS)
                self.assertTrue(low <= module.DEFAULTS[key] <= high, key)
                for raw in (low - 1, high + 1, "x", True, None, math.nan):
                    got = module.cfg(with_elane(e2={key: raw}))[key]
                    self.assertEqual(got, module.DEFAULTS[key], (module.__name__, key, raw))
                for raw in (low, high):
                    self.assertEqual(module.cfg(with_elane(e2={key: raw}))[key], raw, (module.__name__, key, raw))
        # A block that is no object at all is the defaults, and the lanes' own switch still reads.
        for raw in ("x", 5, None, [1]):
            s = with_elane(mode="gate", birth_share=0.25, e2=raw)
            for module in E2_MODULES:
                self.assertEqual(module.cfg(s), module.cfg({}), (module.__name__, raw))
            self.assertTrue(elane_births.births_on(s))


class TheIdentities(unittest.TestCase):
    """E2 moves none of the three ids (the equity evidence identity, the options execution fingerprint, the money
    digest): it adds no file to what any of them hashes and none of those files reads it."""

    def hashed(self) -> dict[str, list[Path]]:
        from league.gym.driver import LEAGUE_FILES
        from league.swarm import evaluator

        equity = [REPO / name for name in (*LEAGUE_FILES, *evaluator.EQUITY_GYM_FILES)]
        equity += [REPO / "league" / "equity" / f"{name}.py" for name in evaluator.EQUITY_EVIDENCE]
        options = [REPO / name for name in LEAGUE_FILES]
        for tree in ("gym", "live"):
            options += sorted((REPO / "league" / tree).rglob("*.py"))
        return {"equity": equity, "options": options, "money": [REPO / "league" / "constitution.py"]}

    def test_no_e2_file_is_in_an_identity_and_no_identity_file_reads_e2(self):
        from league.swarm import evaluator

        self.assertEqual(evaluator.EQUITY_EVIDENCE, ("__init__", "config", "store", "program", "ctx", "engine", "results",
                                                     "runner", "synth", "sizing", "screen", "child"),
                         "A13's list: release E2 adds nothing to the equity evidence")
        self.assertFalse([name for name in evaluator.EQUITY_EVIDENCE if "elane" in name])
        names = re.compile(r"\belane_(births|train|yield|seal|review)\b")
        for identity, files in self.hashed().items():
            self.assertTrue(files, identity)
            for path in files:
                rel = path.relative_to(REPO).as_posix()
                self.assertNotIn(rel, E2_FILES, identity)
                self.assertFalse(rel.startswith("league/swarm/"), (identity, rel))
                self.assertIsNone(names.search(path.read_text(encoding="utf-8")), (identity, rel))
        # Nor does any other file of the equity tree or of the live path's hook into it (plumbing outside A13's list).
        for path in sorted((REPO / "league" / "equity").rglob("*.py")) + sorted((REPO / "league" / "xs").rglob("*.py")):
            self.assertIsNone(names.search(path.read_text(encoding="utf-8")), path.relative_to(REPO).as_posix())

    def test_the_money_rules_hold_no_e2_setting(self):
        from league import constitution

        text = json.dumps(constitution.CONSTITUTION, sort_keys=True)
        for word in ("birth_share", "usd_day", "e2", "elane"):
            self.assertNotIn(f'"{word}"', text, "the constitution (so the money digest) knows nothing of E2's switches")

    def test_e2s_own_events_stay_in_the_swarms_table(self):
        # One kind for the equity pass and the Train round (every ten minutes while a family researches): the House's
        # mirror skips it as it skips the researchers' cycles; before, the mirror dropped each as an unknown kind and
        # told the owner so. Births and retirements are the public kinds every lane writes.
        from league.ledger import KINDS
        from league.swarm.hook import PUBLIC_KINDS, SKIPPED_KINDS

        written: set[str] = set()
        for rel in E2_FILES:
            written |= set(re.findall(r"\.event\(\s*\"(swarm\.[a-z_]+)\"", (REPO / rel).read_text(encoding="utf-8")))
        self.assertEqual(written, {"swarm.elane", "swarm.born", "swarm.status"})
        self.assertIn("swarm.elane", SKIPPED_KINDS)
        self.assertNotIn("swarm.elane", KINDS)
        self.assertNotIn("swarm.elane", PUBLIC_KINDS)
        self.assertIn("swarm.born", PUBLIC_KINDS)
        self.assertIs(KINDS["swarm.status"], False, "an alert of E2's is a private row the House reads")

    def test_the_five_modules_are_protected(self):
        from league import ci

        for rel in E2_FILES:
            self.assertTrue((REPO / rel).is_file(), rel)
            self.assertIn(rel, ci.FORBIDDEN)
            self.assertTrue(ci.guard([rel], None), rel)
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([rel], role), (rel, role))


class TheScreensName(unittest.TestCase):
    """Amendment A11: the share screen is S2. Whatever a generator or a reviewer is told of the screen names the one
    policy.json pins, and tells no outcome and no threshold."""

    def texts(self) -> dict[str, str]:
        on = with_elane(mode="gate", birth_share=0.25)
        return {"the architect's system text": elane_births.SYSTEM, "the lanes block": elane_births.lanes_text(on),
                "the agenda": elane_births.agenda_text(), "the bar": elane_train.bar_text(),
                "the researcher's system text": elane_train.RESEARCHER_SYSTEM, "the review's rubric": elane_review.REVIEW,
                "the Train map's label": elane_train.MAP_LABEL}

    def test_the_architect_is_told_the_pinned_screen(self):
        pinned = {elane.screen_name(lane, policy=policy()) for lane in elane.LANES}
        self.assertEqual(pinned, {"S2"}, "policy.json pins S2 for both lanes (A11)")
        self.assertIn("by the share screen S2,", " ".join(elane_births.SYSTEM.split()))
        for where, text in self.texts().items():
            self.assertTrue(text, where)
            self.assertIsNone(re.search(r"\bS1\b", text), f"{where} still names S1")
            for name in re.findall(r"\bshare screen (S\d)\b", " ".join(text.split())):
                self.assertIn(name, pinned, where)

    def test_the_text_tells_no_threshold_of_the_screen(self):
        # The receipt's figures are the operator's: no generator text carries one (the seal is about outcomes; a
        # threshold in a prompt would be a target to fit). No sentence that speaks of the screen, Validation or the
        # look holds one of the pinned block's figures, and no text anywhere names one of the receipt's quantities.
        block = policy()["elane"]["screens"]
        figures = {str(block[lane][key]) for lane in block for key in ("c_H_floor", "c_H_margin", "c_X", "fp_cap", "owner_wall")}
        figures.discard("0.0")
        self.assertEqual(len(figures), 5, figures)
        spoken = 0
        for where, text in self.texts().items():
            for word in ("c_H", "c_R", "c_X", "c_p", "fp_cap", "t_H"):
                self.assertNotIn(word, text, where)
            for sentence in re.split(r"(?<=[.;:])\s+", " ".join(text.split())):
                if not re.search(r"screen|Validation|\blook\b|holdout", sentence):
                    continue
                spoken += 1
                for figure in figures:
                    self.assertIsNone(re.search(rf"(?<![\d.]){re.escape(figure)}(?!\d)", sentence), (where, figure, sentence))
                    percent = f"{float(figure) * 100:g}%"
                    self.assertNotIn(percent, sentence, (where, percent))
        self.assertGreaterEqual(spoken, 5, "the texts do speak of the screen, Validation and the look")


class TheLoop(LoopCase):
    """E1's real loop, store, settings layers and switch, on the committed policy.json under a swarm.json; the rounds
    a pass would start are recorded, not run."""

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH)
        patch.start()
        self.addCleanup(patch.stop)

    def asked(self) -> list[dict]:
        """The model requests that carry a text of E2's (its two system prompts and its review's rubric)."""
        marks = ("EQUITY LANES", "long-only ETF programs")
        return [b for b in self.sail.bodies if any(m in json.dumps(b, default=str) for m in marks)]

    def started(self, block: dict | None, *, passes: int = 2) -> tuple[list[str], object]:
        doc = {"enabled": True, "gym": self.settings["gym"], "researcher": {"idle_seconds": 0}}
        if block is not None:
            doc["elane"] = block
        (self.root / "swarm.json").write_text(json.dumps(doc))
        sw = self.swarm()
        names: list[str] = []
        sw._round = lambda name, fn: names.append(name)
        for _ in range(passes):
            sw.step()
        self.assertTrue(sw.gym_ready(), "the rounds' own precondition holds, so a round not started was held by the switch")
        self.assertTrue(self.guard.allows("research"))
        return names, sw

    def footprints(self) -> dict:
        events = self.store._all("SELECT COUNT(*) AS n FROM events WHERE kind='swarm.elane'")[0]["n"]
        return {"keys": {k: self.store.get(k) for k in E2_KEYS if self.store.get(k) is not None}, "events": events}

    def e2_families(self) -> list[str]:
        return [str(f["id"]) for f in elane_seal.equity_families(self.store) if elane_train.e2_family(f)]

    def assert_still(self, names: list[str], sw) -> None:
        self.assertNotIn("elane", names)
        self.assertNotIn("elane_train", names)
        self.assertFalse(sw.architect.equity_due())
        self.assertFalse(sw.elane_train.due())
        self.assertEqual(self.footprints(), {"keys": {}, "events": 0})
        self.assertEqual(self.asked(), [], "no model was asked")

    def test_as_shipped_nothing_of_e2_acts(self):
        names, sw = self.started(None)
        self.assertEqual(elane.cfg(sw.settings)["mode"], "off")
        self.assert_still(names, sw)
        self.assertEqual(elane_seal.equity_families(self.store), [], "nor are E1's seeds born while the lanes are off")

    def test_the_lanes_off_nothing_of_e2_acts_whatever_the_share(self):
        # Even with a share set and families the equity pass bore earlier still on record: `elane.mode` "off" stops all.
        fx.e2_family(self.store, "e2-earlier", code=fx.program())
        names, sw = self.started({"mode": "off", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        self.assert_still(names, sw)
        self.assertEqual(elane_train.record_of(self.store.family("e2-earlier"))["versions"], {}, "nothing was scored")

    def test_no_share_nothing_of_e2_acts_while_e1_runs(self):
        # E1 switched on (the captain's first step), E2's births not yet: the seeds are born, E2 does nothing.
        names, sw = self.started({"mode": "gate", "birth_share": 0.0})
        self.assertTrue(elane.on(sw.settings))
        self.assertEqual(len(elane_seal.equity_families(self.store)), 3, "E1's three seeds, born by the same pass")
        self.assertEqual(self.e2_families(), [])
        self.assert_still(names, sw)
        # The same with the key absent (policy.json's zero), a share that is no number, and one below zero.
        for block in ({"mode": "gate"}, {"mode": "gate", "birth_share": "0.25"}, {"mode": "gate", "birth_share": -1}):
            names, sw = self.started(block)
            self.assert_still(names, sw)

    def test_the_share_set_back_to_zero_stops_the_births_and_lets_the_born_finish(self):
        # Stated in ELANE_E2.md and docs/operations.md: a zero share stops BIRTHS at once; the families already born
        # finish their Train research, and `elane.e2.usd_day` 0 keeps that from asking a model.
        fx.e2_family(self.store, "e2-born", code=fx.program())        # a program to Train-score: no model needed
        fx.e2_family(self.store, "e2-unwritten", symbols=("QQQ",))    # no program yet: its next step asks a model
        names, sw = self.started({"mode": "gate", "birth_share": 0.0, "e2": {"usd_day": 0.0}})
        self.assertNotIn("elane", names, "no equity pass: no birth")
        self.assertFalse(sw.architect.equity_due())
        self.assertIn("elane_train", names, "the family already born still has its Train round")
        out = sw.elane_train.run()
        steps = {s["family"]: s for s in out["steps"]}
        self.assertEqual(steps["e2-unwritten"].get("skipped"), elane_yield.DAY_SPENT)
        self.assertEqual(elane_yield.DAY_SPENT, "E2's model dollars for the day are spent (elane.e2.usd_day)")
        self.assertIsNotNone(steps["e2-born"].get("house"), "no equity store under this root: the House's, a backoff")
        self.assertEqual(self.asked(), [], "with the day line at zero no model is asked")
        self.assertEqual(self.e2_families(), ["e2-born", "e2-unwritten"])
        # What is left needs a model E2 may not ask (and a family waiting out its backoff): no round has work, so none
        # starts and nothing is written (the review's merge-4: an empty round every ten minutes before).
        self.assertTrue(sw.elane_train.idle())
        self.store.put(elane_train.TRAIN_AT_KEY, 0)
        events = self.footprints()["events"]
        names.clear()
        sw.step()
        self.assertNotIn("elane_train", names)
        self.assertFalse(sw.elane_train.due())
        self.assertEqual(self.footprints()["events"], events)

    def test_the_switch_on_starts_both_rounds(self):
        # The positive control: the recorder sees E2's rounds once the captain's two keys are set.
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        self.assertIn("elane", names)
        self.assertNotIn("elane_train", names, "no family of E2's yet: no Train round")
        fx.e2_family(self.store, "e2-first")
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        self.assertIn("elane", names)
        self.assertIn("elane_train", names)

    def test_one_equity_pass_on_the_real_router_is_born_and_booked(self):
        # The wiring production runs: the loop's own Architect and EquityResearcher, the real ModelRouter and Provider (a
        # scripted Sail), E1's real card admission and store. The pass asks ONE question on the first route, bears the
        # family in its own lane's population, and books its dollars on the route's row and on the Sail research meter.
        row = fx.proposal("e2-wired", lane="beta", agenda="overnight", symbols=("DIA",), code=fx.program("DIA"))
        self.sail.script = lambda body: {"text": json.dumps({"families": [row]})}
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        self.assertIn("elane", names)
        options_before = len(self.store.families(alive=True))
        out = sw.architect.equity_pass()
        self.assertEqual(out.get("born"), ["e2-wired"], json.dumps(out, default=str)[:900])
        self.assertEqual(len(self.asked()), 1, "one question, on one route")
        self.assertIn("by the share screen S2,", " ".join(json.dumps(self.asked()[0]).split()))
        fam = self.store.family("e2-wired")
        self.assertEqual((fam["structure"], fam["spec"]["lane"], fam["spec"]["e2_route"], fam["band"]),
                         ("etf", "beta", "sail:pro_asap", "gym"))
        self.assertTrue(elane_train.e2_family(fam))
        self.assertEqual(len(self.store.families(alive=True)), options_before, "an equity birth takes no options place")
        born = [e["payload"] for e in self.store.events_after(0, limit=10_000)
                if e["kind"] == "swarm.born" and e.get("family") == "e2-wired"]
        self.assertEqual([(b["lane"], b["origin"], b["route"]) for b in born], [("beta", "architect", "sail:pro_asap")])
        book = elane_yield.ledger(self.store)
        self.assertEqual((book["routes"]["sail:pro_asap"]["births"], book["routes"]["sail:pro_asap"]["requests"]), (1, 1))
        spent = book["routes"]["sail:pro_asap"]["usd"]
        self.assertGreater(spent, 0.0)
        self.assertAlmostEqual(elane_yield.spent_today(self.store, sw.clock()), spent, places=6)
        self.assertGreaterEqual(self.store.spent(["sail_model"]), spent, "E2's dollars are Sail research dollars")
        # E1's tournament leaves it alone until its Train pass and review (patch 5), and its Train round is now due.
        self.assertFalse(elane_train.may_validate(self.store, fam, elane.next_try(self.store, fam, sw.settings)))
        self.assertTrue(sw.elane_train.due())
        # No equity store under this root (E1's data job never ran here), and outside a root House the decider child
        # refuses to run a program at all: either way the House's failure, a backoff and never a verdict.
        step = sw.elane_train.run()
        self.assertEqual(elane_train.record_of(self.store.family("e2-wired")).get("versions"), {}, json.dumps(step)[:600])
        self.assertEqual([s.get("house") is not None for s in step["steps"]], [True], json.dumps(step)[:600])
        self.assertEqual(len(self.asked()), 1, "a House failure asks no model")
        # The operator's record reads it (league/ops/dlane_report.py `equity_yield`).
        from league.ops import dlane_report

        record = dlane_report.equity_yield(self.store, sw.settings)
        self.assertEqual(record["routes"]["sail:pro_asap"]["families"], 1, record)
        self.assertEqual(record["usd_day"], 8.0)

    # ------------------------------------------------------------------ E2's dollars and the researchers' pace
    def unpace(self, sw) -> dict:
        """The pace as a fresh read (its spend is cached for 10 s)."""
        sw._pace = (float("-inf"), "", 0.0, 0.0)
        return sw.pace_status()

    def e2_row(self, usd: float, n: int) -> None:
        """A model call of E2's as the router books it (kind `sail_model`, its request key in the detail)."""
        key = f"swarm:elane:train:e2-wired:{n}:sail:pro_asap"
        self.store.add_spend("sail_model", usd, family="e2-wired", detail={"profile": "pro_asap", "key": key, "desk": "e2-wired"})

    def test_e2s_dollars_never_pause_the_researchers_and_e2_waits_at_its_own_pace(self):
        # The review's blocker (loop-1, merge-1), on the real loop, router, Provider and the committed policy.json: E2's
        # calls are booked as `sail_model` with keys "swarm:elane:...", the meter the researchers' hourly pace sums, and
        # nothing held E2's own rounds. E2's first switch values gave it the whole pace: every options researcher slept.
        from league.swarm.loop import architect_spent

        row = fx.proposal("e2-wired", lane="beta", agenda="overnight", symbols=("DIA",), code=fx.program("DIA"))
        self.sail.script = lambda body: {"text": json.dumps({"families": [row]})}
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        limit = sw.pace_status()["limit_usd_per_hour"]
        share = elane_yield.cfg(sw.settings)["pace_share"]
        self.assertGreater(limit, 0.0)
        self.assertEqual(elane_yield.model_line(sw.settings), (limit, True), "E2 reads the line the loop's pace reads")
        self.assertEqual(share, 0.25)
        out = sw.architect.equity_pass()
        self.assertEqual(out.get("born"), ["e2-wired"], json.dumps(out, default=str)[:600])
        booked = elane_yield.spent_since(self.store, sw.clock() - 3600)
        self.assertGreater(booked, 0.0)
        self.assertAlmostEqual(booked, elane_yield.ledger(self.store)["routes"]["sail:pro_asap"]["usd"], places=6)
        self.assertAlmostEqual(self.store.spent(["sail_model"], since=sw.clock() - 3600), booked, places=6)
        self.assertEqual(architect_spent(self.store, ["sail_model"], sw.clock() - 3600), 0.0, "no key of the architect's")
        pace = self.unpace(sw)
        self.assertEqual((pace["spent_last_hour_usd"], pace["paused"]), (0.0, False), "E2's pass is not the researchers' spend")
        self.assertAlmostEqual(pace["equity"]["spent_last_hour_usd"], booked, places=6)
        self.assertAlmostEqual(pace["equity"]["limit_usd_per_hour"], share * limit, places=6)
        # E2 at three times the whole line in the hour: the researchers are not paused, and E2 is, by its own pace.
        self.e2_row(3 * limit, 1)
        pace = self.unpace(sw)
        self.assertFalse(sw.over_pace(), pace)
        self.assertTrue(pace["equity"]["paused"])
        self.assertAlmostEqual(pace["equity"]["taken_usd"], share * limit, places=6)
        held = elane_yield.hold(self.store, sw.settings, sw.clock())
        self.assertIsNotNone(held)
        self.assertIn("pace", held)
        # Neither of E2's rounds asks a model while it waits: no equity pass is due, and a family that needs a program
        # is skipped, the reason named.
        self.store.put(elane_births.BIRTHS_AT_KEY, 0)
        self.assertFalse(sw.architect.equity_due())
        names.clear()
        sw.step()
        self.assertNotIn("elane", names)
        asked = len(self.asked())
        self.assertEqual(sw.architect.equity_pass().get("skipped"), "pace")
        fx.e2_family(self.store, "e2-needs-a-program")
        steps = {s["family"]: s for s in sw.elane_train.run()["steps"]}
        self.assertEqual(steps["e2-needs-a-program"].get("skipped"), held)
        self.assertEqual(len(self.asked()), asked, "no model was asked")
        # The researchers keep the line less E2's share, whatever E2 spent over it: under it they run, at it they pause.
        self.store.add_spend("sail_model", (1 - share) * limit - 0.001, family="a-family",
                             detail={"desk": "a-family", "key": "swarm:a-family:c3:m0:2", "profile": "flash_asap"})
        self.assertFalse(self.unpace(sw)["paused"])
        self.store.add_spend("sail_model", 0.002, family="a-family",
                             detail={"desk": "a-family", "key": "swarm:a-family:c4:m0:2", "profile": "flash_asap"})
        pace = self.unpace(sw)
        self.assertTrue(pace["paused"])
        self.assertTrue(sw.over_pace())
        self.assertIn("the equity lanes took", pace["reason"])
        self.assertAlmostEqual(pace["spent_last_hour_usd"], (1 - share) * limit + 0.001, places=6)

    def test_with_e2_idle_the_researchers_have_the_whole_line(self):
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        limit = sw.pace_status()["limit_usd_per_hour"]
        self.store.add_spend("sail_model", limit - 0.001, family="a-family",
                             detail={"desk": "a-family", "key": "swarm:a-family:c3:m0:2", "profile": "flash_asap"})
        pace = self.unpace(sw)
        self.assertEqual((pace["paused"], pace["equity"]["taken_usd"]), (False, 0.0), "nothing is set aside for an idle E2")
        self.e2_row(0.002, 1)
        self.assertTrue(self.unpace(sw)["paused"], "the two together fit the line")

    def test_the_budgets_floor_tightens_e2s_day_with_the_line(self):
        # No budget.json under this root: the budget rule's floor. E2's day is a quarter of the floor's model dollars,
        # whatever `elane.e2.usd_day` says (the review: at the floor E2's line was still $8 against a $4 research day).
        from league.ops import budget

        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        line = budget.knobs(budget.floor_usd_day("sail"), budget.floor_usd_day("claude"))["researcher.sail_usd_per_hour"]
        self.assertAlmostEqual(sw.pace_status()["limit_usd_per_hour"], line, places=6)
        self.assertAlmostEqual(elane_yield.day_line(sw.settings), 0.25 * line * 24, places=6)
        self.assertLess(elane_yield.day_line(sw.settings), 8.0)
        self.assertEqual(elane_yield.cfg(sw.settings)["usd_day"], 8.0)

    # ------------------------------------------------------------------ the routes when Sail is slow or silent
    def bar_passed(self, fid: str) -> None:
        """A family whose v1 passed the bar and awaits its review (what `EquityResearcher.score` writes)."""
        fx.e2_family(self.store, fid, code=fx.program())
        verdict = {"passed": True, "fails": [], "score": 1.0, "years": {}, "summary": {}, "beside": {}}
        elane_train._update(self.store, fid, lambda r: r.update(
            versions={"1": elane_train.compact(verdict, at=self.store.now(), ident=None)},
            review={"version": 1, "unclear": {}, "at": self.store.now()}))

    def test_the_audit_finds_a_second_model_while_the_balanced_window_is_stalled(self):
        # The integration review's seal-7 and loop-3, on the real router: with Sail's balanced window flagged stalled
        # (one poll timeout flags it for an hour) the router answers pro_balanced AND k3_balanced on pro_asap for E2's
        # role, so the audit's first candidate came back from the reviewer's own model, was discarded, glm_balanced was
        # never asked, and the same key was re-read every round (booked again each time; empty once the router had
        # blanked it; three empty reads failed the version at REVIEW).
        from league.swarm import models

        self.sail.script = lambda body: {"text": json.dumps({"verdict": "pass", "reasons": ["invented"], "findings": []})}
        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        self.assertEqual(sw.router.sail_fallback("k3_balanced", role=elane_yield.ROLE), ("balanced", "pro_asap"))
        self.bar_passed("e2-a")
        now = sw.clock()
        self.store.put(models.STALL_KEY, {"balanced": {"until": now + 3600, "since": now, "at": now, "profile": "pro_balanced",
                                                       "fallback": "pro_asap", "role": "elane",
                                                       "code": "provider_poll_timeout"}})
        asked = len(self.sail.bodies)
        out = sw.elane_train.review_step(self.store.family("e2-a"), 1)
        self.assertEqual((out.get("passed"), out.get("review")), (True, "pass"), json.dumps(out)[:400])
        rec = elane_train.record_of(self.store.family("e2-a"))
        held = rec["passed_review"]
        self.assertEqual((held["route"], held["audit"]["route"]), ("sail:pro_asap", "sail:glm_balanced"))
        self.assertNotEqual(elane_review.model_of(held["route"]), elane_review.model_of(held["audit"]["route"]))
        self.assertEqual(len(self.sail.bodies) - asked, 2, "one review, one audit: k3_balanced was never sent to pro_asap")
        rows = elane_yield.ledger(self.store)["routes"]
        self.assertEqual({k: v["requests"] for k, v in rows.items()}, {"review:sail:pro_asap": 1, "review:sail:glm_balanced": 1})
        self.assertAlmostEqual(elane_yield.ledger(self.store)["days"][elane_yield._today(now)],
                               self.store.spent(["sail_model"]), places=6, msg="E2's ledger books each call once")
        self.assertEqual(rec["passed_version"], 1)

    def test_a_call_that_timed_out_after_it_was_sent_is_booked_and_ends_the_question(self):
        # The review's loop-2, on the real router and Provider with a transport that times out: one family's write sent
        # three calls (every route in turn), the swarm's meter booked three holds, E2's own day booked nothing, and the
        # family asked all three again next round under a new key.
        def boom(body):
            raise TimeoutError("the socket timed out after the request went")

        names, sw = self.started({"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 8.0}})
        fx.e2_family(self.store, "e2-a")
        self.sail.script = boom
        sent = len(self.sail.bodies)
        out = sw.elane_train.write(self.store.family("e2-a"))
        self.assertEqual(out.get("error"), "no route answered", json.dumps(out)[:400])
        self.assertTrue(out["errors"][0].startswith(elane_yield.SENT_UNANSWERED), out["errors"])
        self.assertGreater(out["retry_in"], 0)
        booked = self.store.spent(["sail_model"])
        self.assertGreater(booked, 0.0, "the Provider's hold for the call that may still be billed")
        self.assertEqual(len(self.store._all("SELECT 1 FROM spend WHERE kind='sail_model'")), 1, "one call, one hold")
        rows = elane_yield.ledger(self.store)["routes"]
        self.assertEqual(list(rows), ["sail:pro_asap"], "no other route was asked the same question on top of it")
        self.assertEqual((rows["sail:pro_asap"]["failed"], rows["sail:pro_asap"]["unknown_cost"]), (1, 1))
        self.assertAlmostEqual(rows["sail:pro_asap"]["usd"], booked, places=6)
        self.assertAlmostEqual(elane_yield.spent_today(self.store, sw.clock()), booked, places=6)
        # The family waits out its backoff: the next round asks nothing for it.
        rec = elane_train.record_of(self.store.family("e2-a"))
        self.assertEqual((rec["unanswered"]["count"], rec["unanswered"]["sent"], rec.get("attempts")), (1, True, None))
        tried = len(self.sail.bodies)
        self.assertEqual(sw.elane_train.run()["steps"], [])
        self.assertEqual(len(self.sail.bodies), tried)
        self.assertGreaterEqual(tried - sent, 1)


if __name__ == "__main__":
    unittest.main()
