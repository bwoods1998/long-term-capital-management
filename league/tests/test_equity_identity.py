"""The equity lane's evidence identity (A8.8, I5, as amended by the captain's A13): its own fingerprint over the
EVIDENCE modules only (`EQUITY_EVIDENCE`, held equal to the import closure of the runner, the child, the screen and the
engine, plus `synth`; league/equity's plumbing moves nothing), the league/gym modules it hashes held equal to the ones
the evidence imports, evidence modules that never reach league.live or league.swarm, and an adoption that resets equity
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
from league.swarm.evaluator import (EQUITY_CALENDAR_FILES, EQUITY_EVIDENCE, EQUITY_EVIDENCE_EXTRA, EQUITY_EVIDENCE_ROOTS,
                                    EQUITY_GYM_FILES, EQUITY_KEY, adopt, adopt_equity, equity_fingerprint,
                                    equity_identity, execution_fingerprint, identity, is_equity_family)
from league.tests.test_swarm_store import SPEC, StoreCase

REPO = Path(__file__).resolve().parents[2]
EQUITY = REPO / "league" / "equity"
#: A13, as the captain listed them: the evidence modules (the identity) and the plumbing (out of it).
EVIDENCE = ("__init__", "config", "store", "program", "ctx", "engine", "results", "runner", "synth", "sizing",
            "screen", "child")
PLUMBING = ("live", "actions", "schedule", "families", "bands", "kinds", "bugstop")   # (bugstop: release 1019m's latch)


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


def closure(roots: list[Path]) -> set[str]:
    """Every file of the repository's league package the `roots` reach (repository-relative): the roots, what they
    import (at module level or inside a function: the child imports per op), what those import, and the __init__ of
    every package on the way (importing a module runs them)."""
    pending = list(roots)
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        parts = path.relative_to(REPO).parts
        pending += [init for i in range(1, len(parts)) if (init := REPO.joinpath(*parts[:i], "__init__.py")).is_file()]
        for module in _imports(path):
            target = _file_of(module) if module.startswith("league.") else None
            if target is not None:
                pending.append(target)
    return {p.relative_to(REPO).as_posix() for p in seen}


def evidence_closure(roots=EQUITY_EVIDENCE_ROOTS) -> set[str]:
    return closure([EQUITY / f"{name}.py" for name in roots])


def gym_closure() -> set[str]:
    """The league/gym files the equity evidence reaches (the modules of `EQUITY_EVIDENCE`, synth included)."""
    return {f for f in evidence_closure(EQUITY_EVIDENCE) if f.startswith("league/gym/")}


def write(repo: Path, name: str, text: str = "VALUE = 1\n") -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class Fingerprint(unittest.TestCase):
    def tearDown(self):
        equity_fingerprint.cache_clear()
        execution_fingerprint.cache_clear()

    def test_it_moves_for_the_evidence_modules_and_what_they_import_only(self):
        """A13: the identity is the evidence modules (each one), the 4 LEAGUE_FILES and the gym files they import.
        league/equity's plumbing, a new module beside them, league/xs, league/live, the swarm and the documentation
        move nothing: a plumbing fix never sends a live equity band back to the Gym."""
        evidence = [f"league/equity/{name}.py" for name in EVIDENCE]
        plumbing = [f"league/equity/{name}.py" for name in PLUMBING]
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in (*LEAGUE_FILES, *EQUITY_GYM_FILES, *EQUITY_CALENDAR_FILES, *evidence, *plumbing,
                         "league/gym/fills.py", "league/live/step.py", "league/equity/deep/kind.py",
                         "league/equity/newcomer.py", "league/xs/__init__.py", "league/xs/child.py",
                         "league/swarm/elane.py", "ltcm/data/kalshi.py"):
                write(repo, name)
            original = equity_fingerprint(repo)
            options = execution_fingerprint(repo)
            for name in (*plumbing, "league/equity/deep/kind.py", "league/equity/newcomer.py", "league/xs/child.py",
                         "league/xs/__init__.py", "league/equity/EQUITY.md", "league/equity/INTERFACES.md",
                         "league/live/step.py", "league/gym/fills.py", "league/swarm/elane.py", "ltcm/data/kalshi.py"):
                write(repo, name, "VALUE = 2\n")
                equity_fingerprint.cache_clear()
                self.assertEqual(equity_fingerprint(repo), original, name)
            for name in (*evidence, *EQUITY_GYM_FILES, *LEAGUE_FILES, *EQUITY_CALENDAR_FILES):
                write(repo, name, "VALUE = 3\n")
                equity_fingerprint.cache_clear()
                self.assertNotEqual(equity_fingerprint(repo), original, name)
                write(repo, name)
            equity_fingerprint.cache_clear()
            self.assertEqual(equity_fingerprint(repo), original)
            # A release that lacks an evidence module has no identity (no band proof, no look), never a smaller one.
            (repo / "league/equity/sizing.py").unlink()
            equity_fingerprint.cache_clear()
            with self.assertRaises(OSError):
                equity_fingerprint(repo)
            write(repo, "league/equity/sizing.py")
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
    def test_the_evidence_list_is_the_import_closure_of_the_runner_the_child_the_screen_and_the_engine(self):
        """A13's CI test: `EQUITY_EVIDENCE` equals the import closure, inside league/equity, of the runner, the child,
        the screen and the engine, plus `synth` (named apart: the four never import it, and it imports nothing outside
        the closure). So a new module the evidence comes to import cannot hide outside the identity: the closure grows
        and this fails until the list, and with it the fingerprint, names it. The plumbing is none of it."""
        self.assertEqual(EQUITY_EVIDENCE, EVIDENCE)
        self.assertEqual((EQUITY_EVIDENCE_ROOTS, EQUITY_EVIDENCE_EXTRA), (("runner", "child", "screen", "engine"),
                                                                        ("synth",)))
        inside = {Path(f).stem for f in evidence_closure() if f.startswith("league/equity/")}
        self.assertEqual(inside | set(EQUITY_EVIDENCE_EXTRA), set(EQUITY_EVIDENCE))
        self.assertFalse(inside & set(EQUITY_EVIDENCE_EXTRA), "an extra the roots import is no extra: drop it from the list")
        for name in EQUITY_EVIDENCE_EXTRA:
            reached = {Path(f).stem for f in evidence_closure((name,)) if f.startswith("league/equity/")}
            self.assertLessEqual(reached - {name}, inside, f"{name} brings nothing new into the identity")
        self.assertFalse(set(EQUITY_EVIDENCE) & set(PLUMBING))
        on_disk = {p.stem for p in EQUITY.glob("*.py")}
        self.assertEqual(on_disk, set(EVIDENCE) | set(PLUMBING), "a new module of league/equity is named evidence "
                         "(EQUITY_EVIDENCE, by the closure) or plumbing (here), never left unsaid")
        self.assertFalse([p for p in EQUITY.rglob("*.py") if p.parent != EQUITY and "__pycache__" not in p.parts],
                         "the identity lists files of league/equity itself: a sub-package would be outside it")

    def test_the_real_fingerprint_reads_exactly_the_listed_files(self):
        """The repository's own identity: the same digest as one taken over EQUITY_EVIDENCE, LEAGUE_FILES,
        EQUITY_GYM_FILES and EQUITY_CALENDAR_FILES by hand, and unmoved by a byte of plumbing (read through a copy)."""
        import hashlib
        import shutil

        files = sorted({*(f"league/equity/{name}.py" for name in EVIDENCE), *LEAGUE_FILES, *EQUITY_GYM_FILES,
                        *EQUITY_CALENDAR_FILES})
        self.assertEqual(len(files), len(EVIDENCE) + len(LEAGUE_FILES) + len(EQUITY_GYM_FILES)
                         + len(EQUITY_CALENDAR_FILES))
        digest = hashlib.sha256()
        for name in files:
            digest.update(name.encode() + b"\0" + (REPO / name).read_bytes() + b"\0")
        equity_fingerprint.cache_clear()
        self.assertEqual(equity_fingerprint(), digest.hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for name in (*files, *(f"league/equity/{name}.py" for name in PLUMBING)):
                (copy / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, copy / name)
            self.assertEqual(equity_fingerprint(copy), digest.hexdigest())
            for name in PLUMBING:
                with (copy / "league" / "equity" / f"{name}.py").open("a") as handle:
                    handle.write("\n# a plumbing fix\n")
            equity_fingerprint.cache_clear()
            self.assertEqual(equity_fingerprint(copy), digest.hexdigest(), "plumbing retires no lineage")
            with (copy / "league" / "equity" / "screen.py").open("a") as handle:
                handle.write("\n# an evidence change\n")
            equity_fingerprint.cache_clear()
            self.assertNotEqual(equity_fingerprint(copy), digest.hexdigest())
        equity_fingerprint.cache_clear()

    def test_the_hashed_gym_files_are_exactly_the_ones_the_evidence_reaches(self):
        self.assertEqual(gym_closure(), set(EQUITY_GYM_FILES))
        # ... and what it reaches of league/ itself is inside the 4 LEAGUE_FILES (hashed whole, reached or not).
        top = {f for f in evidence_closure(EQUITY_EVIDENCE) if f.count("/") == 1}
        self.assertLessEqual(top, set(LEAGUE_FILES), top)

    def test_evidence_modules_never_import_league_live_or_league_swarm(self):
        reached = evidence_closure(EQUITY_EVIDENCE)
        self.assertFalse(sorted(f for f in reached if f.startswith(("league/live/", "league/swarm/", "league/xs/"))))
        for name in (*EVIDENCE, "kinds"):
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
                             elane_train_r={"days": [1, 2, 3], "r": [0.01, -0.02, 0.0]}, elane_template="beta:t",
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
        for key in ("validation_r_sd_by_version", "elane_floor"):
            self.assertIsNone(state[key])
        # The look's lineage record stays with the look (A9 D3 reads it for every later program; nothing rewrites it).
        self.assertEqual(state["elane_train_r"], {"days": [1, 2, 3], "r": [0.01, -0.02, 0.0]})
        self.assertEqual(state["elane_template"], "beta:t")
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
