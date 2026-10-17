"""THE DEEP IDENTITY AND THE LEGACY IDS (HISTORY-PLAN.md section 5.3, "Legacy"; league/deep/identity.py): R1 moves no
identity. The equity identity (78022ca6) and the options execution fingerprint (b60410ad) read no file of league/deep
and no tree they hash imports it; the S2 path is league/equity/screen.py, untouched; league/deep's own identity is the
league/xs pattern, its lists held to the evaluator's and to the package's imports; and births see nothing: no module
of league/swarm, league/equity, league/live, league/gym or league/xs imports league/deep or names its store."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from league.deep import config, identity
from league.gym.driver import LEAGUE_FILES
from league.swarm import evaluator

REPO = Path(__file__).resolve().parents[2]
DEEP = REPO / "league" / "deep"
#: What a module of league/deep may import of the league beside league/deep itself.
ALLOWED = {f"league.equity.{name}" for name in ("config", "store", "screen", "synth", "program")} | {"league.equity"}
#: ... and the identity module, inside its functions, the options fingerprint's four files' list.
IDENTITY_ALLOWED = {"league.gym.driver", "league.gym"}
SEALED_FROM_DEEP = ("league/swarm", "league/equity", "league/live", "league/gym", "league/xs")


def imports(path: Path) -> set[str]:
    package = path.relative_to(REPO).with_suffix("").parts[:-1]
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package) - node.level + 1]) if node.level else []
            module = ".".join([*base, *(node.module.split(".") if node.module else [])])
            out.add(module)
            for alias in node.names:
                full = f"{module}.{alias.name}"
                if (REPO.joinpath(*full.split(".")).with_suffix(".py")).is_file():
                    out.add(full)
    return {name for name in out if name.split(".")[0] == "league"}


class TheLegacyIdsHold(unittest.TestCase):
    def test_r1_moves_neither_the_equity_identity_nor_the_options_fingerprint(self):
        self.assertEqual(evaluator.equity_fingerprint()[:8], config.LEGACY_IDS["equity"],
                         "the equity identity moved: the deep key's relabel equivalence was proven on 78022ca6; re-run "
                         "league/tests/test_deep_relabel.py on the new engine and name the new id in LEGACY_IDS")
        self.assertEqual(evaluator.execution_fingerprint()[:8], config.LEGACY_IDS["options"])

    def test_no_file_of_league_deep_is_in_either_identity(self):
        equity = {*LEAGUE_FILES, *evaluator.EQUITY_GYM_FILES, *evaluator.EQUITY_CALENDAR_FILES,
                  *(f"league/equity/{name}.py" for name in evaluator.EQUITY_EVIDENCE)}
        options = {*LEAGUE_FILES, *(p.relative_to(REPO).as_posix() for tree in ("gym", "live")
                                    for p in (REPO / "league" / tree).rglob("*.py"))}
        for name in equity | options:
            self.assertFalse(name.startswith("league/deep/"), name)
        self.assertEqual(identity.EQUITY_EVIDENCE, evaluator.EQUITY_EVIDENCE)
        self.assertEqual(identity.EQUITY_GYM_FILES, evaluator.EQUITY_GYM_FILES)
        self.assertEqual(identity.EQUITY_CALENDAR_FILES, evaluator.EQUITY_CALENDAR_FILES)


class TheDeepIdentity(unittest.TestCase):
    def test_its_files_are_the_evidence_modules_the_fixtures_and_the_equity_identitys(self):
        files = {p.relative_to(REPO).as_posix() for p in identity.deep_files()}
        modules = {p.stem for p in DEEP.glob("*.py")}
        self.assertEqual(modules, set(identity.DEEP_EVIDENCE) | set(identity.DEEP_PLUMBING))
        for name in identity.DEEP_EVIDENCE:
            self.assertIn(f"league/deep/{name}.py", files)
        for name in identity.DEEP_PLUMBING:
            self.assertNotIn(f"league/deep/{name}.py", files)
        for name in identity.DEEP_DATA:
            self.assertIn(f"league/deep/{name}", files)
        for name in identity.EQUITY_EVIDENCE:
            self.assertIn(f"league/equity/{name}.py", files)
        self.assertTrue(set(LEAGUE_FILES) <= files)
        self.assertEqual(len(identity.deep_fingerprint()), 64)

    def test_a_change_to_an_evidence_module_or_a_fixture_moves_it_and_plumbing_does_not(self):
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for path in identity.deep_files():
                target = repo / path.relative_to(REPO)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, target)
            for name in identity.DEEP_PLUMBING:
                shutil.copy(DEEP / f"{name}.py", repo / "league" / "deep" / f"{name}.py")
            base = identity.deep_fingerprint.__wrapped__(repo)
            self.assertEqual(base, identity.deep_fingerprint())
            (repo / "league/deep/report.py").write_text("# plumbing\n")
            self.assertEqual(identity.deep_fingerprint.__wrapped__(repo), base)
            mask = repo / "league/deep/mask_dval_235.txt"
            mask.write_text(mask.read_text() + "2009-01-02\n")
            self.assertNotEqual(identity.deep_fingerprint.__wrapped__(repo), base)
            mask.unlink()
            with self.assertRaises(FileNotFoundError):
                identity.deep_fingerprint.__wrapped__(repo)

    def test_the_package_imports_only_its_own_modules_and_five_equity_evidence_modules(self):
        for path in sorted(DEEP.glob("*.py")):
            found = {m for m in imports(path) if m != "league.deep" and not m.startswith("league.deep.") and m != "league"}
            allowed = ALLOWED | (IDENTITY_ALLOWED if path.stem == "identity" else set())
            self.assertEqual(found - allowed, set(), path.name)
        for module in ALLOWED - {"league.equity"}:
            self.assertIn(module.rsplit(".", 1)[1], identity.EQUITY_EVIDENCE)


class BirthsSeeNothing(unittest.TestCase):
    def test_no_sealed_tree_imports_league_deep_or_names_its_store(self):
        pattern = re.compile(r"league\.deep\b|league/deep\b|equity-deep|from \.\.deep|from \.deep\b")
        hits = []
        for tree in SEALED_FROM_DEEP:
            for path in sorted((REPO / tree).rglob("*.py")):
                for number, line in enumerate(path.read_text().splitlines(), 1):
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(REPO)}:{number}")
        self.assertEqual(hits, [])

    def test_only_ops_and_tests_import_league_deep(self):
        hits = []
        for path in sorted((REPO / "league").rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel.startswith(("league/deep/", "league/ops/", "league/tests/")):
                continue
            if any(m == "league.deep" or m.startswith("league.deep.") for m in imports(path)):
                hits.append(rel)
        self.assertEqual(hits, [])

    def test_the_ops_jobs_open_the_swarm_store_read_only(self):
        from league.tests.test_e3_seal_imports import writable_swarm_opens

        for name in ("equity_deep", "deep_report"):
            self.assertEqual(writable_swarm_opens(REPO, REPO / "league" / "ops" / f"{name}.py"), [], name)


if __name__ == "__main__":
    unittest.main()
