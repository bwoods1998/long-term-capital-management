"""THE XS IDENTITY (league/xs/identity.py; release E4; seal X9): what a panel band's proof binds to.

Fingerprint: the identity is the xs evidence modules, the E1 evidence modules they import, the 4 LEAGUE_FILES and the
gym and calendar files, each of them and nothing else; plumbing, documentation and every other lane move nothing.
TheClosure: `XS_EVIDENCE` is held to the import closure, inside league/xs, of the runner, the child, the screen and the
engine, plus `synth` (THE STYLE RULE IS IN IT: the captain's A22); `XS_EQUITY_DEPS` to that closure's league.equity
modules; the gym and calendar lists to E1's; every module of the package imports only what the release's contract
lets it; and the three private E1 names are the only ones. E4MovesNoIdentity: nothing release E4 adds or patches is a
file the equity identity or the options execution fingerprint reads, and neither reaches league/xs. Adoption: an xs
evidence change resets panel families only, keeps their tries, looks and lineage records, and touches no ETF and no
options family (`league.swarm.evaluator.adopt_xs`: package E's patch, league/swarm/e4_patches/E.md).

WHILE THE RELEASE IS BEING BUILT some modules of league/xs are still Step 0 stubs (their `_STUB`), which import less
than they will: until none is left the closure is held ONE WAY (nothing the roots reach is outside the identity:
the direction that matters), and from then on to equality. The adoption tests need the panel structure in the swarm's
store (package G's patch 1) and `adopt_xs` (package E's patch 3): they are skipped until both are applied, and a
release whose swarm calls `adopt_xs` without it fails here.
"""

from __future__ import annotations

import ast
import hashlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from league.equity import ctx as e1ctx
from league.gym.driver import LEAGUE_FILES
from league.swarm import evaluator
from league.swarm import store as swarm_store
from league.tests.test_swarm_store import SPEC, StoreCase
from league.xs import KIND, STRUCTURE, XS_ENGINE_VERSION, identity
from league.xs.identity import (PROOF_KEYS, XS_CALENDAR_FILES, XS_EQUITY_DEPS, XS_EVIDENCE, XS_EVIDENCE_EXTRA,
                                XS_EVIDENCE_ROOTS, XS_GYM_FILES, XS_KEY, XS_PLUMBING, XS_PRIVATE_E1, xs_band_current,
                                xs_files, xs_fingerprint, xs_identity)

REPO = Path(__file__).resolve().parents[2]
XS = REPO / "league" / "xs"
PATCHES = REPO / "league" / "swarm" / "e4_patches"
#: The release's contract (E4-SPEC 2.1; league/xs/E4_INTERFACES.md): the evidence modules and the plumbing.
EVIDENCE = ("__init__", "config", "store", "ctx", "program", "engine", "results", "placebo", "style", "screen",
            "runner", "child", "synth")
PLUMBING = ("book", "identity")
EQUITY_DEPS = ("__init__", "config", "store", "ctx", "program", "engine", "results", "sizing", "screen", "runner",
               "synth")
#: What a module of league/xs may import of this repository beside league/xs itself and `XS_EQUITY_DEPS`.
LEAGUE_ALLOWED = {"league", "league.safety", "league.structure_core", "league.stats", "league.gym", "league.gym.safety",
                  "league.gym.runtime", "league.gym.events"}
#: ... and what its two plumbing modules may import beside (never an evidence module: it would be unhashed evidence).
PLUMBING_ALLOWED = {"book": {"league.equity.schedule"}, "identity": {"league.gym.driver"}}
THIRD_PARTY = {"numpy"}


def module_file(module: str) -> Path | None:
    """The file of a module of this repository (None for anything that is not one)."""
    path = REPO.joinpath(*module.split("."))
    if path.with_suffix(".py").is_file():
        return path.with_suffix(".py")
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    return None


def imports(path: Path, *, at_import: bool = False) -> set[str]:
    """Every MODULE `path` imports, at module level or inside a function (absolute names; relative imports resolved
    against its package): `from a import b` names `a`, and `a.b` when that is itself a module. `at_import`: only what
    importing the module executes (function bodies left out: they run later, or never)."""
    package = path.relative_to(REPO).with_suffix("").parts[:-1]
    out: set[str] = set()
    pending = list(ast.parse(path.read_text()).body)
    while pending:
        node = pending.pop()
        if at_import and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package) - node.level + 1]) if node.level else []
            module = ".".join([*base, *(node.module.split(".") if node.module else [])])
            out.add(module)
            out.update(f"{module}.{alias.name}" for alias in node.names
                       if module_file(f"{module}.{alias.name}") is not None)
        pending.extend(ast.iter_child_nodes(node))
    return out


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
        for module in imports(path):
            target = module_file(module) if module.startswith("league.") else None
            if target is not None:
                pending.append(target)
    return {p.relative_to(REPO).as_posix() for p in seen}


def outside(files: set[str]) -> set[str]:
    """Every file of the repository OUTSIDE league/ that importing what `files` import executes (E1's own reading of
    its calendar's closure: a module outside league/ is followed by what its import runs, never by a function it may
    never call)."""
    pending = [target for name in sorted(files) for module in imports(REPO / name)
               if not module.startswith("league") and (target := module_file(module)) is not None]
    seen: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        parts = path.relative_to(REPO).parts
        pending += [init for i in range(1, len(parts)) if (init := REPO.joinpath(*parts[:i], "__init__.py")).is_file()]
        pending += [target for module in imports(path, at_import=True) if (target := module_file(module)) is not None]
    return {p.relative_to(REPO).as_posix() for p in seen}


def xs_closure(names=XS_EVIDENCE_ROOTS) -> set[str]:
    return closure([XS / f"{name}.py" for name in names])


def stems(files: set[str], folder: str) -> set[str]:
    return {Path(f).stem for f in files if f.startswith(folder) and f.count("/") == folder.count("/")}


def unbuilt() -> list[str]:
    """The evidence modules of league/xs that are still Step 0 stubs: a module-level `_STUB` (what a stub's unbuilt
    functions raise), or the child's `REFUSAL` (the slot that refuses every op)."""
    out = []
    for name in XS_EVIDENCE:
        tree = ast.parse((XS / f"{name}.py").read_text())
        marks = {target.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
                 if isinstance(target, ast.Name)}
        if "_STUB" in marks or (name == "child" and "REFUSAL" in marks):
            out.append(name)
    return out


def write(repo: Path, name: str, text: str = "VALUE = 1\n") -> Path:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class Fingerprint(unittest.TestCase):
    def tearDown(self):
        xs_fingerprint.cache_clear()
        evaluator.equity_fingerprint.cache_clear()
        evaluator.execution_fingerprint.cache_clear()

    def test_the_lists_are_the_contracts(self):
        self.assertEqual((XS_EVIDENCE, XS_PLUMBING, XS_EQUITY_DEPS), (EVIDENCE, PLUMBING, EQUITY_DEPS))
        self.assertEqual((XS_EVIDENCE_ROOTS, XS_EVIDENCE_EXTRA), (("runner", "child", "screen", "engine"), ("synth",)))
        self.assertEqual(XS_KEY, "xs_evaluator")
        self.assertIn("style", XS_EVIDENCE, "the captain's A22: the rule that marks a program style-open is evidence")
        self.assertIn("screen", XS_EVIDENCE)
        self.assertIn("placebo", XS_EVIDENCE)
        self.assertFalse(set(XS_EVIDENCE) & set(XS_PLUMBING))
        self.assertEqual(PROOF_KEYS, ("engine", "xs_sha256", "run_sha"))

    def test_it_moves_for_the_evidence_and_what_it_imports_only(self):
        """The identity is the xs evidence modules (each one), the E1 evidence modules they import, the 4 LEAGUE_FILES
        and the gym and calendar files. The panel's plumbing, a new module beside them, documentation, league/equity's
        own plumbing and its child, league/live, the swarm and the jobs move nothing."""
        evidence = [f"league/xs/{name}.py" for name in EVIDENCE]
        deps = [f"league/equity/{name}.py" for name in EQUITY_DEPS]
        plumbing = [f"league/xs/{name}.py" for name in PLUMBING]
        others = ["league/equity/child.py", "league/equity/live.py", "league/equity/kinds.py",
                  "league/equity/schedule.py", "league/xs/newcomer.py", "league/xs/deep/module.py", "league/xs/XS.md",
                  "league/xs/E4_INTERFACES.md", "league/live/step.py", "league/gym/fills.py", "league/swarm/elane_xs.py",
                  "league/swarm/evaluator.py", "league/ops/equity_panel.py", "league/constitution.py",
                  "ltcm/data/kalshi.py", "docs/benchmarks/equity_screen_xs_1.json", "league/swarm/policy.json"]
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            for name in (*LEAGUE_FILES, *XS_GYM_FILES, *XS_CALENDAR_FILES, *evidence, *deps, *plumbing, *others):
                write(repo, name)
            original = xs_fingerprint(repo)
            self.assertRegex(original, r"^[0-9a-f]{64}$")
            for name in (*plumbing, *others):
                write(repo, name, "VALUE = 2\n")
                xs_fingerprint.cache_clear()
                self.assertEqual(xs_fingerprint(repo), original, name)
            for name in (*evidence, *deps, *XS_GYM_FILES, *LEAGUE_FILES, *XS_CALENDAR_FILES):
                write(repo, name, "VALUE = 3\n")
                xs_fingerprint.cache_clear()
                self.assertNotEqual(xs_fingerprint(repo), original, name)
                write(repo, name)
            xs_fingerprint.cache_clear()
            self.assertEqual(xs_fingerprint(repo), original)
            # A release that lacks one of its files has no identity (no band proof, no look), never a smaller one.
            for name in ("league/xs/style.py", "league/xs/screen.py", "league/equity/sizing.py", "ltcm/broker.py"):
                (repo / name).unlink()
                xs_fingerprint.cache_clear()
                with self.assertRaises(OSError, msg=name):
                    xs_fingerprint(repo)
                write(repo, name)
            xs_fingerprint.cache_clear()
            self.assertEqual(xs_fingerprint(repo), original)
            # the same bytes under another name are another identity (the path is hashed with them)
            write(repo, "league/xs/style.py", "VALUE = 7\n")
            write(repo, "league/xs/screen.py", "VALUE = 1\n")
            xs_fingerprint.cache_clear()
            one = xs_fingerprint(repo)
            write(repo, "league/xs/style.py", "VALUE = 1\n")
            write(repo, "league/xs/screen.py", "VALUE = 7\n")
            xs_fingerprint.cache_clear()
            self.assertNotEqual(xs_fingerprint(repo), one)

    def test_the_real_fingerprint_reads_exactly_the_listed_files(self):
        """The repository's own identity: the digest taken by hand over the lists, path and bytes in path order, and
        unmoved by a byte of plumbing (read through a copy)."""
        names = sorted({*(f"league/xs/{name}.py" for name in EVIDENCE),
                        *(f"league/equity/{name}.py" for name in EQUITY_DEPS), *LEAGUE_FILES, *XS_GYM_FILES,
                        *XS_CALENDAR_FILES}, key=lambda name: Path(name))
        self.assertEqual(len(names), len(EVIDENCE) + len(EQUITY_DEPS) + len(LEAGUE_FILES) + len(XS_GYM_FILES)
                         + len(XS_CALENDAR_FILES))
        self.assertEqual([p.relative_to(REPO).as_posix() for p in xs_files()], names)
        digest = hashlib.sha256()
        for name in names:
            digest.update(name.encode() + b"\0" + (REPO / name).read_bytes() + b"\0")
        xs_fingerprint.cache_clear()
        self.assertEqual(xs_fingerprint(), digest.hexdigest())
        self.assertEqual(xs_identity(), {"xs": digest.hexdigest(), "engine": XS_ENGINE_VERSION})
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for name in (*names, *(f"league/xs/{name}.py" for name in PLUMBING)):
                (copy / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, copy / name)
            self.assertEqual(xs_fingerprint(copy), digest.hexdigest())
            for name in PLUMBING:
                with (copy / "league" / "xs" / f"{name}.py").open("a") as handle:
                    handle.write("\n# a plumbing fix\n")
            xs_fingerprint.cache_clear()
            self.assertEqual(xs_fingerprint(copy), digest.hexdigest(), "plumbing retires no panel lineage")
            for name in ("style", "screen", "placebo"):
                with (copy / "league" / "xs" / f"{name}.py").open("a") as handle:
                    handle.write("\n# an evidence change\n")
                xs_fingerprint.cache_clear()
                self.assertNotEqual(xs_fingerprint(copy), digest.hexdigest(), name)
                shutil.copyfile(REPO / "league" / "xs" / f"{name}.py", copy / "league" / "xs" / f"{name}.py")
        xs_fingerprint.cache_clear()

    def test_the_band_proof(self):
        expected = {"xs": "a" * 64, "engine": XS_ENGINE_VERSION}
        proof = {"engine": XS_ENGINE_VERSION, "xs_sha256": "a" * 64, "run_sha": "r"}
        self.assertTrue(xs_band_current({"banded_evaluator": proof}, expected))
        for other in ({**proof, "xs_sha256": "b" * 64}, {**proof, "engine": "xs-engine-0"},
                      {k: v for k, v in proof.items() if k != "xs_sha256"}, {"engine": XS_ENGINE_VERSION,
                                                                           "equity_sha256": "a" * 64}, None, "proof"):
            self.assertFalse(xs_band_current({"banded_evaluator": other}, expected), other)
        self.assertFalse(xs_band_current({}, expected))
        self.assertFalse(xs_band_current(None, expected))
        # an identity that names nothing proves nothing: two missing shas are no agreement
        for unknown in ({}, {"engine": XS_ENGINE_VERSION}, {"xs": None, "engine": None}, None):
            self.assertFalse(xs_band_current({"banded_evaluator": {"engine": None}}, unknown), unknown)
            self.assertFalse(xs_band_current({"banded_evaluator": {}}, unknown), unknown)


class TheClosure(unittest.TestCase):
    """Seal X9: a new module the panel's evidence comes to import cannot hide outside the identity."""

    def test_the_evidence_list_is_the_import_closure_of_the_roots_and_synth(self):
        inside = stems(xs_closure(), "league/xs/")
        waiting = unbuilt()
        self.assertLessEqual(inside, set(XS_EVIDENCE), "the roots reach a module the identity does not hash")
        self.assertFalse(inside & set(XS_PLUMBING), "plumbing in the evidence's imports is evidence: name it so")
        self.assertFalse(inside & set(XS_EVIDENCE_EXTRA), "an extra the roots import is no extra: drop it from the list")
        for root in XS_EVIDENCE_ROOTS:
            self.assertIn(root, inside)
        for name in XS_EVIDENCE_EXTRA:
            reached = stems(xs_closure((name,)), "league/xs/") - {name}
            self.assertLessEqual(reached, set(XS_EVIDENCE), name)
            if not waiting:
                self.assertLessEqual(reached, inside, f"{name} brings nothing new into the identity")
        missing = set(XS_EVIDENCE) - inside - set(XS_EVIDENCE_EXTRA)
        if not waiting:
            self.assertEqual(missing, set(), "a listed module the roots never import is no evidence: the list is the "
                                             "closure, to equality")
        # what is always in it, stubs or not: the screen's and the style rule's own modules
        self.assertLessEqual({"__init__", "screen", "config", "results", "placebo", "engine", "runner", "child"}, inside)
        if "engine" not in waiting:
            self.assertIn("style", inside, "the captain's A22: the engine imports the style reading")

    def test_every_module_of_the_package_is_named_evidence_or_plumbing(self):
        on_disk = {p.stem for p in XS.glob("*.py")}
        self.assertEqual(on_disk, set(EVIDENCE) | set(PLUMBING), "a new module of league/xs is named evidence "
                         "(XS_EVIDENCE, by the closure) or plumbing (here), never left unsaid")
        self.assertFalse([p for p in XS.rglob("*.py") if p.parent != XS and "__pycache__" not in p.parts],
                         "the identity lists files of league/xs itself: a sub-package would be outside it")

    def test_the_equity_modules_it_hashes_are_the_ones_the_evidence_reaches(self):
        reached = xs_closure(XS_EVIDENCE)
        deps = stems(reached, "league/equity/")
        self.assertLessEqual(deps, set(XS_EQUITY_DEPS), "the panel's evidence reaches an E1 module the identity does "
                                                        "not hash")
        self.assertLessEqual(set(XS_EQUITY_DEPS), set(evaluator.EQUITY_EVIDENCE),
                             "each is an E1 evidence module: a change there moves both identities")
        if not unbuilt():
            self.assertEqual(deps, set(XS_EQUITY_DEPS))
        self.assertLessEqual({"__init__", "config", "screen", "runner", "program"}, deps, "what the stubs already import")

    def test_the_gym_and_calendar_files_are_e1s_and_the_ones_reached(self):
        self.assertEqual(XS_GYM_FILES, evaluator.EQUITY_GYM_FILES)
        self.assertEqual(XS_CALENDAR_FILES, evaluator.EQUITY_CALENDAR_FILES)
        self.assertEqual(XS_EVIDENCE_ROOTS, evaluator.EQUITY_EVIDENCE_ROOTS)
        self.assertEqual(XS_EVIDENCE_EXTRA, evaluator.EQUITY_EVIDENCE_EXTRA)
        reached = xs_closure(XS_EVIDENCE)
        gym = {f for f in reached if f.startswith("league/gym/")}
        self.assertLessEqual(gym, set(XS_GYM_FILES), "the evidence reaches a league/gym file the identity does not hash")
        if not unbuilt():
            self.assertEqual(gym, set(XS_GYM_FILES))
        top = {f for f in reached if f.startswith("league/") and f.count("/") == 1}
        self.assertLessEqual(top, set(LEAGUE_FILES), top)
        # what it reaches of this repository OUTSIDE league/ is the calendar, and the identity hashes all of it
        beyond = outside(reached)
        self.assertLessEqual({f for f in beyond if not f.startswith("league/")}, set(XS_CALENDAR_FILES),
                             "the evidence reaches a file outside league/ the identity does not hash")
        self.assertFalse({f for f in beyond if f.startswith("league/")} - {"league/__init__.py"},
                         "the calendar reaches nothing of league/ (it would be evidence too)")
        if not unbuilt():
            self.assertEqual({f for f in beyond if not f.startswith("league/")}, set(XS_CALENDAR_FILES))
        self.assertFalse(sorted(f for f in reached if f.startswith(("league/live/", "league/swarm/", "league/ops/"))),
                         "the panel's evidence reaches the House's plumbing")
        for name in (*XS_GYM_FILES, *XS_CALENDAR_FILES, *LEAGUE_FILES):
            self.assertTrue((REPO / name).is_file(), name)

    def test_each_module_imports_only_what_the_contract_lets_it(self):
        """E4-SPEC 2.1: numpy and the standard library; league/xs itself; the 4 LEAGUE_FILES; the hashed league/gym
        modules; and the E1 evidence modules of `XS_EQUITY_DEPS`. The plumbing may also read `league.equity.schedule`
        (the book adapter) and `league.gym.driver` (this identity's LEAGUE_FILES). Nothing of league.live,
        league.swarm or league.ops, in any module, at any depth of a function."""
        allowed = LEAGUE_ALLOWED | {"league.xs", "league.equity"} | {f"league.equity.{n}" for n in XS_EQUITY_DEPS
                                                                       if n != "__init__"}
        for path in sorted(XS.glob("*.py")):
            name = path.stem
            mine = allowed | {f"league.xs.{n}" for n in (*EVIDENCE, *PLUMBING) if n != "__init__"}
            mine |= PLUMBING_ALLOWED.get(name, set())
            for module in sorted(imports(path)):
                with self.subTest(module=name, imports=module):
                    self.assertIsNone(re.match(r"league\.(live|swarm|ops)(\.|$)", module), "the House's plumbing")
                    top = module.split(".")[0]
                    if module_file(module) is not None or top in ("league", "ltcm"):
                        self.assertIn(module, mine, f"league/xs/{name}.py imports {module}: name it in XS_EQUITY_DEPS "
                                                    f"(evidence, hashed) or in this test's plumbing allowance")
                    else:
                        self.assertTrue(top in sys.stdlib_module_names or top in THIRD_PARTY,
                                        f"league/xs/{name}.py imports {module}: standard library and numpy only")
            if name in EVIDENCE:
                reach = {m for m in imports(path) if m.startswith("league.xs.")}
                self.assertFalse(reach & {f"league.xs.{n}" for n in PLUMBING}, f"{name} (evidence) imports plumbing")

    def test_the_three_private_e1_names_and_no_other(self):
        """`league.equity.ctx._encode`, `_ro` and `_factor_row`: pinned by name, so an E1 rename fails here and not in
        a decision; and league/xs reads no other private name of league/equity (the screen: E1's public names only)."""
        self.assertEqual(XS_PRIVATE_E1, ("_encode", "_ro", "_factor_row"))
        for private in XS_PRIVATE_E1:
            self.assertTrue(callable(getattr(e1ctx, private, None)), f"league.equity.ctx.{private} is gone")
        used: set[tuple[str, str]] = set()
        for path in sorted(XS.glob("*.py")):
            parts = path.relative_to(REPO).with_suffix("").parts[:-1]
            tree = ast.parse(path.read_text())
            aliases: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    base = list(parts[:len(parts) - node.level + 1]) if node.level else []
                    module = ".".join([*base, *(node.module.split(".") if node.module else [])])
                    for alias in node.names:
                        target = f"{module}.{alias.name}"
                        if module_file(target) is not None and target.startswith("league.equity"):
                            aliases[alias.asname or alias.name] = target
                        elif module.startswith("league.equity") and alias.name.startswith("_") \
                                and not alias.name.startswith("__"):
                            used.add((module, alias.name))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("league.equity") and alias.asname:
                            aliases[alias.asname] = alias.name
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases \
                        and node.attr.startswith("_") and not node.attr.startswith("__"):
                    used.add((aliases[node.value.id], node.attr))
        self.assertLessEqual(used, {("league.equity.ctx", name) for name in XS_PRIVATE_E1}, sorted(used))
        if "ctx" not in unbuilt():
            self.assertEqual(used, {("league.equity.ctx", name) for name in XS_PRIVATE_E1},
                             "a pinned name league/xs no longer reads: drop it from XS_PRIVATE_E1")

    def test_the_names_of_the_lane(self):
        self.assertEqual((KIND, STRUCTURE), ("panel", "panel"))
        self.assertEqual(XS_ENGINE_VERSION, "xs-engine-1")


def patched_paths() -> set[str]:
    """Every existing file release E4 changes: the paths the patch files' table names (README.md) and the paths
    their diffs touch (`--- a/...`, `+++ b/...`)."""
    out: set[str] = set()
    for path in sorted(PATCHES.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        out.update(m.group(1) for m in re.finditer(r"^(?:---|\+\+\+) [ab]/(\S+)", text, re.M))
        if path.name == "README.md":
            out.update(m.group(1) for m in re.finditer(r"`((?:league|gateway|docs|scripts|ltcm)/[\w./-]+\.\w+)`", text))
    return out


class E4MovesNoIdentity(unittest.TestCase):
    """Seal X9 (the captain's A13): release E4 moves neither the equity identity nor the options execution fingerprint.
    The CI job compares the two trees' fingerprints; here the reason they cannot differ is held."""

    def tearDown(self):
        xs_fingerprint.cache_clear()
        evaluator.equity_fingerprint.cache_clear()
        evaluator.execution_fingerprint.cache_clear()

    def equity_files(self) -> set[str]:
        return {*(f"league/equity/{name}.py" for name in evaluator.EQUITY_EVIDENCE), *LEAGUE_FILES,
                *evaluator.EQUITY_GYM_FILES, *evaluator.EQUITY_CALENDAR_FILES}

    def execution_files(self) -> set[str]:
        files = set(LEAGUE_FILES)
        for name in ("gym", "live"):
            files.update(p.relative_to(REPO).as_posix() for p in (REPO / "league" / name).rglob("*.py"))
        return files

    def test_no_file_e4_adds_or_patches_is_read_by_either_identity(self):
        patched = patched_paths()
        self.assertIn("league/swarm/evaluator.py", patched, "the patch table is read")
        self.assertIn("league/equity/live.py", patched)
        for label, files in (("equity", self.equity_files()), ("options execution", self.execution_files())):
            self.assertFalse(sorted(f for f in files if f.startswith("league/xs/")), f"the {label} identity reads the "
                                                                                     f"panel package")
            self.assertEqual(sorted(files & patched), [], f"release E4 patches a file of the {label} identity")
        self.assertNotIn("child", XS_EQUITY_DEPS)
        self.assertFalse({f"league/equity/{name}.py" for name in ("live", "kinds", "schedule", "actions", "families",
                                                                 "bands")} & self.equity_files(),
                         "the files E4's live patch touches are E1's plumbing")

    def test_neither_identity_reaches_the_panel_package(self):
        roots = [REPO / "league" / "equity" / f"{name}.py" for name in evaluator.EQUITY_EVIDENCE]
        reached = closure(roots)
        self.assertFalse(sorted(f for f in reached if f.startswith("league/xs/")),
                         "an equity evidence module imports league/xs: the equity identity would move with the panel")
        for name in sorted(self.execution_files()):
            for module in imports(REPO / name):
                self.assertIsNone(re.match(r"league\.xs(\.|$)", module), f"{name} imports {module}")

    def test_the_three_identities_move_apart(self):
        """On a copy of the real files: a change to any module of league/xs moves the xs identity and neither of the
        others; an E1 evidence module the panel imports moves the equity and the xs identities; E1's child moves the
        equity identity alone; league/live moves the options fingerprint alone."""
        files = self.equity_files() | self.execution_files() | {p.relative_to(REPO).as_posix() for p in xs_files()}
        files |= {f"league/xs/{name}.py" for name in PLUMBING}
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for name in sorted(files):
                (copy / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, copy / name)

            def prints() -> tuple[str, str, str]:
                xs_fingerprint.cache_clear()
                evaluator.equity_fingerprint.cache_clear()
                evaluator.execution_fingerprint.cache_clear()
                return (xs_fingerprint(copy), evaluator.equity_fingerprint(copy), evaluator.execution_fingerprint(copy))

            def touched(name: str) -> tuple[bool, bool, bool]:
                before = prints()
                original = (copy / name).read_bytes()
                (copy / name).write_bytes(original + b"\n# a change\n")
                after = prints()
                (copy / name).write_bytes(original)
                return tuple(a != b for a, b in zip(before, after))          # (xs, equity, options)

            base = prints()
            self.assertEqual(base, (xs_fingerprint(), evaluator.equity_fingerprint(), evaluator.execution_fingerprint()),
                             "the copy is the repository's own three identities")
            for name in EVIDENCE:
                self.assertEqual(touched(f"league/xs/{name}.py"), (True, False, False), name)
            for name in PLUMBING:
                self.assertEqual(touched(f"league/xs/{name}.py"), (False, False, False), name)
            for name in EQUITY_DEPS:
                self.assertEqual(touched(f"league/equity/{name}.py"), (True, True, False), name)
            self.assertEqual(touched("league/equity/child.py"), (False, True, False))
            self.assertEqual(touched("league/live/decider.py"), (False, False, True))
            self.assertEqual(touched("league/gym/runtime.py"), (True, True, True), "a file all three hash")
            self.assertEqual(prints(), base)


#: A panel family as the swarm's store holds one (lane "equity", structure "panel", no symbols).
PANEL_SPEC = {**SPEC, "id": "xs-reversal", "lane": "equity", "structure": STRUCTURE, "roots": [], "agenda": "xs_reversal",
              "panel": "sp500", "max_names": 10, "rebalance": "weekly", "weekday": 0,
              "mechanism": "Last week's losers inside each cell recover against their cell-mates."}
ETF_SPEC = {**SPEC, "id": "eq-beta", "lane": "beta", "structure": "etf",
            "mechanism": "The overnight session carries the index's drift."}
PATCHED = hasattr(evaluator, "adopt_xs") and STRUCTURE in swarm_store.EQUITY_STRUCTURES


class ThePatch(unittest.TestCase):
    """Package E's patch 3 (league/swarm/e4_patches/E.md): `adopt_xs` lives in league/swarm/evaluator.py."""

    def test_a_swarm_that_calls_adopt_xs_has_it(self):
        """The adoption tests below wait for the patches; a release whose swarm names `adopt_xs` or admits the panel
        structure without the patch does not pass here."""
        swarm = REPO / "league" / "swarm"
        callers = [p.name for p in sorted(swarm.glob("*.py")) if p.name != "evaluator.py"
                   and re.search(r"\badopt_xs\b", p.read_text())]
        if callers or STRUCTURE in swarm_store.EQUITY_STRUCTURES:
            self.assertTrue(hasattr(evaluator, "adopt_xs"), f"{callers or 'the store'} needs package E's patch 3 "
                                                            f"(league/swarm/e4_patches/E.md)")
        if hasattr(evaluator, "adopt_xs"):
            self.assertEqual(evaluator.XS_KEY, XS_KEY)
            self.assertEqual(evaluator.XS_SELECTION_KEYS, ("validation_r_sd_by_version", "elane_xs_floor"))
            self.assertEqual(evaluator.XS_STRUCTURE, STRUCTURE)

    def test_the_patch_file_carries_the_diff(self):
        text = (PATCHES / "E.md").read_text(encoding="utf-8")
        touched = set(re.findall(r"^\+\+\+ b/(\S+)", text, re.M))
        self.assertEqual(touched, {"league/swarm/evaluator.py"}, "package E authors patch 3 and no other")
        for words in ("def adopt_xs(", "XS_SELECTION_KEYS", "is_panel_family(fam)", "or is_panel_family(fam)"):
            self.assertIn(words, text)


@unittest.skipUnless(PATCHED, "waits for package G's patch 1 (the panel structure) and package E's patch 3 (adopt_xs)")
class Adoption(StoreCase):
    def add_panel(self, fid: str = "xs-reversal") -> dict:
        try:
            return self.store.add_family({**PANEL_SPEC, "id": fid}, origin="test")
        except ValueError:                                # a store that still wants a root of every family
            return self.store.add_family({**PANEL_SPEC, "id": fid, "roots": ["SPY"]}, origin="test")

    def setUp(self):
        super().setUp()
        from league.equity import EQUITY_ENGINE_VERSION

        self.kept = {
            "elane_try": {"version": 1, "precheck": True}, "elane_template": "xs_reversal:weekly:10",
            "elane_xs_look": {"version": 1, "verdict": {"passed": True}, "beside": "XS1 ..."},
            "elane_xs_train_x": {"days": [1, 2, 3], "x": [0.01, -0.02, 0.0]},
            "elane_xs_train_u": {"days": [1, 2, 3], "u": [0.02, -0.01, 0.01]},
            "elane_xs_precheck": {"version": 1, "passed": True}, "elane_xs_placebo": {"1": {"rank": 0.97}},
            "elane_xs_halves": {"1": {"h0": 0.1, "h1": 0.2}}, "elane_xs_oof": {"1": {"status": "ok"}},
            "elane_xs": {"1": {"n": 1, "verdict": "pass", "style": {"open": False}}}}
        self.store.add_family({**SPEC, "id": "opt"}, origin="test")
        self.store.add_family(ETF_SPEC, origin="seed")
        self.add_panel()
        self.store.set_band("opt", "probe", reason="qualified")
        self.store.set_state("opt", banded_version=1, banded_evaluator={"engine": "old"}, robustness={"1": {}})
        self.store.set_band("eq-beta", "probe", reason="its look passed")
        self.store.set_state("eq-beta", banded_version=1, elane_floor={"1": {"c_p": 1.2}}, gate_ready=True,
                             validation_r_sd_by_version={"1": 0.01},
                             banded_evaluator={"engine": EQUITY_ENGINE_VERSION, "equity_sha256": "old-equity-code",
                                               "run_sha": "r"})
        self.store.set_band("xs-reversal", "candidate", reason="its look passed (XS1)")
        self.store.update_family("xs-reversal", best_validation=3, validated_version=1)
        self.store.set_state("xs-reversal", banded_version=1, gate_ready=True,
                             validation_r_sd_by_version={"1": 0.012}, elane_xs_floor={"1": {"k_p": 86}},
                             banded_evaluator={"engine": XS_ENGINE_VERSION, "xs_sha256": "old-xs-code", "run_sha": "r"},
                             **self.kept)

    def test_families(self):
        panel, etf, opt = (self.store.family(fid) for fid in ("xs-reversal", "eq-beta", "opt"))
        self.assertTrue(evaluator.is_panel_family(panel))
        self.assertTrue(evaluator.is_equity_family(panel), "a panel family is an equity-lane family")
        self.assertFalse(evaluator.is_panel_family(etf))
        self.assertFalse(evaluator.is_panel_family(opt))
        self.assertFalse(evaluator.is_panel_family(None))

    def test_an_xs_change_resets_panel_families_only_and_keeps_tries_looks_and_the_lineage_records(self):
        from league.swarm import elane_xs

        etf_before, opt_before = self.store.family("eq-beta"), self.store.family("opt")
        current = xs_identity()
        outcome = evaluator.adopt_xs(self.store, current)
        self.assertEqual((outcome["adopted"], outcome["families"], outcome["previous"], outcome["current"]),
                         (True, 1, None, current))
        fam = self.store.family("xs-reversal")
        self.assertEqual(fam["band"], "gym", "the band is earned again under the new evidence")
        state = fam["state"]
        for key in evaluator.XS_SELECTION_KEYS:
            self.assertIsNone(state[key], key)
        for key, value in self.kept.items():
            self.assertEqual(state[key], value, f"{key}: a spent try, a spent look and the lineage records stay")
        # every sealed key of the lane but the floor survives: nothing can write the lineage's records again
        for key in elane_xs.SEALED:
            if key != elane_xs.FLOOR_KEY:
                self.assertEqual(state.get(key), self.kept[key], key)
        self.assertEqual(elane_xs.FLOOR_KEY, "elane_xs_floor")
        self.assertIn(elane_xs.FLOOR_KEY, evaluator.XS_SELECTION_KEYS)
        self.assertFalse(state["gate_ready"])
        self.assertEqual(state["xs_evaluator"], current)
        self.assertEqual(state["previous_evaluator_selection"]["elane_xs_floor"], {"1": {"k_p": 86}})
        self.assertIsNone(fam["best_validation"])
        self.assertEqual(self.store.get(XS_KEY), current)
        for before in (etf_before, opt_before):
            after = self.store.family(before["id"])
            self.assertEqual((after["band"], after["state"]), (before["band"], before["state"]), before["id"])
        self.assertIsNone(self.store.get(evaluator.EQUITY_KEY), "the equity identity's own mark is not this one's")
        self.assertFalse(evaluator.adopt_xs(self.store, current)["adopted"], "once per identity")
        self.assertEqual(evaluator.adopt_xs(self.store, None), {"adopted": False, "families": 0,
                                                               "reason": "xs identity unavailable"})

    def test_a_current_band_proof_keeps_its_band(self):
        current = xs_identity()
        self.store.set_state("xs-reversal", banded_evaluator={"engine": current["engine"], "xs_sha256": current["xs"],
                                                              "run_sha": "r"})
        evaluator.adopt_xs(self.store, current)
        self.assertEqual(self.store.family("xs-reversal")["band"], "candidate")

    def test_the_equity_adoption_never_touches_a_panel_family(self):
        """An equity evidence change sends every live ETF band back to the Gym and leaves the panel's: a panel family
        binds to the xs identity (which an E1 evidence module the panel imports moves too, by its own adoption)."""
        before = self.store.family("xs-reversal")
        outcome = evaluator.adopt_equity(self.store, evaluator.equity_identity())
        self.assertEqual((outcome["adopted"], outcome["families"]), (True, 1))
        self.assertEqual(self.store.family("eq-beta")["band"], "gym")
        after = self.store.family("xs-reversal")
        self.assertEqual((after["band"], after["state"], after["best_validation"]),
                         (before["band"], before["state"], before["best_validation"]))

    def test_the_options_adoption_never_touches_a_panel_family(self):
        from league.swarm import bands

        before = self.store.family("xs-reversal")
        outcome = evaluator.adopt(self.store, evaluator.identity("new-image", bands._bundle()))
        self.assertEqual(outcome["families"], 1)
        after = self.store.family("xs-reversal")
        self.assertEqual((after["band"], after["state"]), (before["band"], before["state"]))
        self.assertEqual(self.store.family("opt")["band"], "gym")

    def test_a_validated_family_not_yet_looked_at_is_owed_its_validation_again(self):
        """A16, as E1's: the verdicts of a version validated under the old evidence go stale (no look was spent)."""
        from league.swarm import elane

        self.add_panel("xs-waiting")
        self.store.set_state("xs-waiting", **{elane.VERDICTS_KEY: {"1": {"entered": True, "stale": False}},
                                              elane.VALIDATION_KEY: {"version": 1, "passed": True, "stale": False},
                                              elane.TRY_KEY: {"version": 1, "entered": True, "precheck": True}})
        outcome = evaluator.adopt_xs(self.store, xs_identity())
        self.assertEqual(outcome["families"], 2)
        state = self.store.family("xs-waiting")["state"]
        self.assertEqual(state[elane.VERDICTS_KEY]["1"]["stale"], True)
        self.assertEqual(state[elane.VALIDATION_KEY]["stale"], True)
        self.assertEqual(state[elane.TRY_KEY], {"version": 1, "entered": True, "precheck": True}, "the try stays spent")
        self.assertEqual(self.store.family("xs-waiting")["band"], "gym")

    def test_a_retired_panel_family_is_left_alone(self):
        self.add_panel("xs-dead")
        self.store.set_state("xs-dead", elane_xs_floor={"1": {"k_p": 90}})
        self.store.retire("xs-dead", "refuted on its Train bar")
        evaluator.adopt_xs(self.store, xs_identity())
        self.assertEqual(self.store.family("xs-dead")["state"]["elane_xs_floor"], {"1": {"k_p": 90}})


if __name__ == "__main__":
    unittest.main()
