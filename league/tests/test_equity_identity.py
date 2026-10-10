"""The equity lane's evidence identity (A8.8, I5): its own fingerprint, the league/gym modules it hashes held equal
to the ones it imports, evidence modules that never reach league.live or league.swarm, and an adoption that resets equity
families only (and `adopt`, the options one, that never touches them).
"""

from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path

from league.equity import EQUITY_ENGINE_VERSION
from league.gym.driver import LEAGUE_FILES
from league.swarm import bands
from league.swarm.evaluator import (EQUITY_GYM_FILES, EQUITY_KEY, adopt, adopt_equity, equity_fingerprint,
                                    equity_identity, execution_fingerprint, identity, is_equity_family)
from league.tests.test_swarm_store import SPEC, StoreCase

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = ("__init__", "config", "store", "program", "ctx", "engine", "results", "runner", "synth", "sizing",
            "screen", "child", "kinds")


def _imports(path: Path) -> set[str]:
    """Every module `path` imports (absolute names; relative imports resolved against its package)."""
    package = path.relative_to(REPO).with_suffix("").parts[:-1]
    if path.name == "__init__.py":
        package = path.relative_to(REPO).parts[:-1]
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package) - node.level + 1]) if node.level else []
            module = ".".join([*base, *(node.module.split(".") if node.module else [])])
            out.add(module)
            out.update(f"{module}.{alias.name}" for alias in node.names)
    return out


def _file_of(module: str) -> Path | None:
    parts = module.split(".")
    path = REPO.joinpath(*parts)
    if path.with_suffix(".py").is_file():
        return path.with_suffix(".py")
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    return None


def gym_closure() -> set[str]:
    """The league/gym files league/equity reaches: what it imports, what those import, and the package's __init__."""
    pending = [p for p in (REPO / "league" / "equity").rglob("*.py")]
    seen: set[Path] = set()
    found: set[str] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in _imports(path):
            if not module.startswith("league.gym"):
                continue
            target = _file_of(module)
            if target is None:
                continue
            found.add(target.relative_to(REPO).as_posix())
            found.add("league/gym/__init__.py")
            pending.append(target)
    return found


def write(repo: Path, name: str, text: str = "VALUE = 1\n") -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class Fingerprint(unittest.TestCase):
    def tearDown(self):
        equity_fingerprint.cache_clear()
        execution_fingerprint.cache_clear()

    def test_it_moves_for_equity_code_and_what_it_imports_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in (*LEAGUE_FILES, *EQUITY_GYM_FILES, "league/gym/fills.py", "league/live/step.py",
                         "league/equity/engine.py", "league/equity/deep/kind.py", "league/swarm/elane.py"):
                write(repo, name)
            original = equity_fingerprint(repo)
            options = execution_fingerprint(repo)
            for name in ("league/equity/EQUITY.md", "league/equity/INTERFACES.md", "league/live/step.py",
                         "league/gym/fills.py", "league/swarm/elane.py"):
                write(repo, name, "VALUE = 2\n")
                equity_fingerprint.cache_clear()
                self.assertEqual(equity_fingerprint(repo), original, name)
            for name in ("league/equity/engine.py", "league/equity/deep/kind.py", "league/gym/runtime.py",
                         "league/gym/events.py", "league/stats.py"):
                write(repo, name, "VALUE = 3\n")
                equity_fingerprint.cache_clear()
                self.assertNotEqual(equity_fingerprint(repo), original, name)
                write(repo, name)
            equity_fingerprint.cache_clear()
            self.assertEqual(equity_fingerprint(repo), original)
            write(repo, "league/equity/engine.py", "VALUE = 4\n")
            execution_fingerprint.cache_clear()
            fills = execution_fingerprint(repo)
            self.assertNotEqual(fills, options, "this temp repo's fills.py moved above")
            write(repo, "league/equity/engine.py", "VALUE = 5\n")
            execution_fingerprint.cache_clear()
            self.assertEqual(execution_fingerprint(repo), fills, "an equity change never moves the options identity")

    def test_the_identity(self):
        current = equity_identity()
        self.assertEqual(set(current), {"equity", "engine"})
        self.assertRegex(current["equity"], r"^[0-9a-f]{64}$")
        self.assertEqual(current["engine"], EQUITY_ENGINE_VERSION)


class Boundaries(unittest.TestCase):
    def test_the_hashed_gym_files_are_exactly_the_ones_league_equity_reaches(self):
        self.assertEqual(gym_closure(), set(EQUITY_GYM_FILES))

    def test_evidence_modules_never_import_league_live_or_league_swarm(self):
        for name in EVIDENCE:
            path = REPO / "league" / "equity" / f"{name}.py"
            with self.subTest(module=name):
                bad = sorted(m for m in _imports(path) if re.match(r"league\.(live|swarm)(\.|$)", m))
                self.assertEqual(bad, [])


EQUITY_SPEC = {**SPEC, "id": "eq-beta", "lane": "beta", "structure": "etf",
               "mechanism": "The overnight session carries the index's drift."}


class Adoption(StoreCase):
    def setUp(self):
        super().setUp()
        self.store.add_family({**SPEC, "id": "opt"}, origin="test")
        self.store.add_family(EQUITY_SPEC, origin="seed")
        self.store.set_band("opt", "probe", reason="qualified")
        self.store.set_state("opt", banded_version=1, banded_evaluator={"engine": "old"}, robustness={"1": {}})
        self.store.set_band("eq-beta", "probe", reason="its look passed")
        self.store.update_family("eq-beta", best_validation=3, validated_version=1)
        self.store.set_state("eq-beta", banded_version=1, elane_try={"version": 1, "precheck": True},
                             elane_look={"version": 1, "verdict": {"passed": True}}, gate_ready=True,
                             validation_r_sd_by_version={"1": 0.01}, elane_floor={"1": {"c_p": 1.2}},
                             banded_evaluator={"engine": EQUITY_ENGINE_VERSION, "equity_sha256": "old-equity-code",
                                               "run_sha": "r"})

    def test_lanes(self):
        self.assertTrue(is_equity_family(self.store.family("eq-beta")))
        self.assertFalse(is_equity_family(self.store.family("opt")))
        self.assertFalse(is_equity_family(None))

    def test_an_engine_change_resets_equity_families_only_and_keeps_tries_and_looks(self):
        opt_before = self.store.family("opt")
        current = equity_identity()
        outcome = adopt_equity(self.store, current)
        self.assertEqual((outcome["adopted"], outcome["families"], outcome["current"]), (True, 1, current))
        fam = self.store.family("eq-beta")
        self.assertEqual(fam["band"], "gym", "the band is earned again under the new engine")
        state = fam["state"]
        self.assertEqual(state["elane_try"], {"version": 1, "precheck": True}, "a spent try stays spent")
        self.assertEqual(state["elane_look"]["version"], 1, "a spent look stays spent")
        for key in ("validation_r_sd_by_version", "elane_floor", "elane_train_r"):
            self.assertIsNone(state[key])
        self.assertFalse(state["gate_ready"])
        self.assertEqual(state["equity_evaluator"], current)
        self.assertEqual(state["previous_evaluator_selection"]["elane_floor"], {"1": {"c_p": 1.2}})
        self.assertIsNone(fam["best_validation"])
        self.assertEqual(self.store.get(EQUITY_KEY), current)
        opt = self.store.family("opt")
        self.assertEqual((opt["band"], opt["state"]), (opt_before["band"], opt_before["state"]))
        self.assertFalse(adopt_equity(self.store, current)["adopted"], "once per identity")
        self.assertEqual(adopt_equity(self.store, None), {"adopted": False, "families": 0,
                                                          "reason": "equity identity unavailable"})

    def test_a_validated_family_not_yet_looked_at_is_validated_again(self):
        """A16: a version validated and gate-ready under the old engine, its look not taken, is owed its Validation
        again (the same try: no look was spent): adoption marks its verdicts stale, so `elane.next_try` asks for it."""
        from league.swarm import elane

        spec = {**EQUITY_SPEC, "id": "eq-waiting", "mechanism": "An invented overnight idea, awaiting its look."}
        self.store.add_family(spec, origin="seed")
        self.store.add_version("eq-waiting", "NEEDS = {'symbols': ['SPY']}\ndef decide(ctx):\n    return []\n", {},
                               author="t")
        self.store.update_family("eq-waiting", best_version=1, validated_version=1)
        self.store.add_run("eq-waiting", 1, {"run_id": "v1", "status": "ok", "trials": 1, "summary": {}},
                           window="validation", stress=1.0, purpose="validation")
        self.store.set_state("eq-waiting", validation_version=1, gate_ready=True,
                             **{elane.TRY_KEY: {"version": 1, "entered": True, "precheck": True},
                                elane.VERDICTS_KEY: {"1": {"entered": True, "at": "x", "stale": False}},
                                elane.VALIDATION_KEY: {"version": 1, "passed": True, "stale": False}})
        on = {"elane": {"mode": "gate"}}
        self.assertIsNone(elane.next_try(self.store, self.store.family("eq-waiting"), on), "current: awaits its look")
        adopt_equity(self.store, equity_identity())
        fam = self.store.family("eq-waiting")
        self.assertEqual(fam["state"][elane.VERDICTS_KEY]["1"]["stale"], True)
        self.assertEqual(fam["state"][elane.VALIDATION_KEY]["stale"], True)
        self.assertEqual(elane.next_try(self.store, fam, on), 1, "validated again under the new engine")
        self.assertIsNone(elane.lineage_spent(self.store, fam, on), "no try and no look spent by the adoption")

    def test_a_current_band_proof_keeps_its_band(self):
        current = equity_identity()
        proof = {"engine": current["engine"], "equity_sha256": current["equity"], "run_sha": "r"}
        self.store.set_state("eq-beta", banded_evaluator=proof)
        adopt_equity(self.store, current)
        self.assertEqual(self.store.family("eq-beta")["band"], "probe")

    def test_the_options_adoption_never_touches_an_equity_family(self):
        before = self.store.family("eq-beta")
        outcome = adopt(self.store, identity("new-image", bands._bundle()))
        self.assertEqual(outcome["families"], 1)
        after = self.store.family("eq-beta")
        self.assertEqual((after["band"], after["state"], after["best_validation"]),
                         (before["band"], before["state"], before["best_validation"]))
        self.assertEqual(self.store.family("opt")["band"], "gym")


if __name__ == "__main__":
    unittest.main()
