"""Release E3's seal T1, `TheForwardRecordIsOpsOnly`: the import rules of league/ops/E3_INTERFACES.md section 1, held
by reading the source (an AST walk for the imports, a text scan for the names), never by running it.

- THE SEAL BY PROCESS. `league/swarm`, `league/equity`, `league/live` and `league/gym` import no E3 ops module and
  never name the forward store, its report, the fill minutes, the probe's file or a forward table: no generator, no
  evidence module and no live path can read a forward row, because none of them can reach the code or the file that
  holds one. (A module check is an import check: `forward_stats` is also the name of a function of
  league/live/money.py, so a bare name is never searched for.)
- THE HIDDEN YEAR's two sealed tables are named only by their keepers: `elane_memory.py`, `elane_seal.py` and
  league/ops.
- WHAT E3 MAY REACH. Its ops modules import only the modules the contract lists; the three memory modules import the
  equity lane's `config`, `results`, `screen` and `store` at their top and `elane_train` and `elane_seal` inside
  functions only; only `elane_train`, `elane_births` and ops import the memory modules; and the ops jobs open the
  swarm store read-only (the probe alone books its dollars).

`TheCheckCatchesWhatItShould` runs the same readers over invented sources that break each rule, so a green run here is
never an empty scan."""

from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path
from typing import Iterator

from league.ops import forward_db
from league.swarm import elane_memory

REPO = Path(__file__).resolve().parents[2]
#: The trees no forward row may reach (the swarm's process, the evidence, the live path, the Gym).
SEALED_TREES = ("league/swarm", "league/equity", "league/live", "league/gym")
#: Release E3's ops modules (league/ops/E3_INTERFACES.md, the ownership map).
E3_OPS = ("forward_db", "forward_register", "forward_controls", "forward_shadow", "forward_audit", "forward_stats",
          "forward_report", "forward_twins", "fill_minutes", "contam_probe", "release_receipts")
#: The files and the directory the forward record lives in: named by ops alone.
NAMES = ("forward.sqlite", "forward-report.json", "equity-fill-minutes", "contamination.json")
#: The memory modules (league/swarm) and what each may import of the league, at its top and inside its functions.
MEMORY = ("elane_folds", "elane_effects", "elane_memory")
MEMORY_TOP = {"league.equity", "league.equity.config", "league.equity.results", "league.equity.screen",
              "league.equity.store", "league.swarm", *(f"league.swarm.{name}" for name in MEMORY)}
MEMORY_INSIDE = MEMORY_TOP | {"league.swarm.elane_train", "league.swarm.elane_seal"}
#: What an E3 ops module may import of the league (section 1's second rule), E3's own ops modules beside.
OPS_MAY = {
    "league.equity", *(f"league.equity.{name}" for name in ("config", "store", "program", "ctx", "engine", "results",
                                                            "runner", "screen", "schedule")),
    "league.live.decider",
    "league.swarm", *(f"league.swarm.{name}" for name in ("store", "settings", "evaluator", "gate", "elane",
                                                          "elane_train", "elane_seal", "elane_yield", "elane_memory",
                                                          "models")),
    "league.ops", *(f"league.ops.{name}" for name in ("guard", "context", "schedule", "twins", "funnel", "equity_data",
                                                      *E3_OPS)),
}
#: Who may import a memory module: the two swarm modules the spec patches, the memory modules themselves, and ops.
MEMORY_IMPORTERS = ("league/swarm/elane_train.py", "league/swarm/elane_births.py",
                    *(f"league/swarm/{name}.py" for name in MEMORY))


def sources(root: Path, tree: str) -> Iterator[Path]:
    """Every Python source under `<root>/<tree>`."""
    for path in sorted((root / tree).rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def texts(root: Path, tree: str) -> Iterator[tuple[Path, str]]:
    """Every text file under `<root>/<tree>` with its content (a file that is not UTF-8 text holds no name to find)."""
    for path in sorted((root / tree).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            try:
                yield path, path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def module_of(root: Path, name: str) -> str | None:
    """The longest prefix of a dotted name that is a module or a package of the checkout (`league.equity.LANES` is
    `league.equity`); None for a name outside it."""
    parts = name.split(".")
    for end in range(len(parts), 0, -1):
        path = root.joinpath(*parts[:end])
        if path.with_suffix(".py").is_file() or (path / "__init__.py").is_file():
            return ".".join(parts[:end])
    return None


def imports(root: Path, path: Path) -> list[tuple[str, bool, int]]:
    """Every league module `path` imports: (module, whether the import sits inside a function, its line). Relative
    imports are resolved against the file's package; `from x import y` counts `x` and, when it is one, the module
    `x.y`."""
    relative = path.relative_to(root)
    package = list(relative.parts[:-1])
    found: list[tuple[str, bool, int]] = []

    def visit(node: ast.AST, inside: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                names = [alias.name for alias in child.names]
            elif isinstance(child, ast.ImportFrom):
                base = package[:len(package) - child.level + 1] if child.level else []
                module = ".".join([*base, *(child.module.split(".") if child.module else [])])
                names = [module, *(f"{module}.{alias.name}" for alias in child.names)]
            else:
                visit(child, inside or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)))
                continue
            for name in names:
                module = module_of(root, name) if name.split(".")[0] == "league" else None
                if module is not None:
                    found.append((module, inside, child.lineno))

    visit(ast.parse(path.read_text(encoding="utf-8")), False)
    return found


def e3_ops_imports(root: Path, tree: str) -> list[str]:
    """Where a source of `tree` imports an E3 ops module, or names one as a dotted module (a string an importer could
    be handed)."""
    wanted = {f"league.ops.{name}" for name in E3_OPS}
    dotted = re.compile(r"\bops\.(?:" + "|".join(E3_OPS) + r")\b")
    out = []
    for path in sources(root, tree):
        for module, _, line in imports(root, path):
            if module in wanted:
                out.append(f"{path.relative_to(root)}:{line} imports {module}")
        for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if dotted.search(text):
                out.append(f"{path.relative_to(root)}:{number} names {dotted.search(text).group(0)}")
    return out


def named(root: Path, tree: str, words: tuple[str, ...], *, pattern: str | None = None) -> list[str]:
    """Where a text file of `tree` holds one of `words` (or matches `pattern`)."""
    regex = re.compile("|".join([*(re.escape(word) for word in words), *([pattern] if pattern else [])]))
    out = []
    for path, text in texts(root, tree):
        for number, line in enumerate(text.splitlines(), 1):
            hit = regex.search(line)
            if hit:
                out.append(f"{path.relative_to(root)}:{number} names {hit.group(0)}")
    return out


def outside(root: Path, path: Path, allowed: set[str], *, inside: set[str] | None = None) -> list[str]:
    """The league imports of `path` outside `allowed` (`inside`: what an import inside a function may add)."""
    out = []
    for module, in_function, line in imports(root, path):
        may = (inside if inside is not None else allowed) if in_function else allowed
        if module != "league" and module not in may:
            out.append(f"{path.relative_to(root)}:{line} imports {module}{' inside a function' if in_function else ''}")
    return out


def writable_swarm_opens(root: Path, path: Path) -> list[str]:
    """Where `path` opens the swarm store without `readonly=True`."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "SwarmStore":
            readonly = [k.value for k in node.keywords if k.arg == "readonly"]
            if not (readonly and isinstance(readonly[0], ast.Constant) and readonly[0].value is True):
                out.append(f"{path.relative_to(root)}:{node.lineno} opens the swarm store writable")
    return out


class TheForwardRecordIsOpsOnly(unittest.TestCase):
    """T1 (the spec's section 9)."""

    def test_the_sealed_trees_import_no_e3_ops_module(self):
        for tree in SEALED_TREES:
            self.assertTrue(list(sources(REPO, tree)), tree)
            self.assertEqual(e3_ops_imports(REPO, tree), [], tree)

    def test_the_sealed_trees_never_name_the_forward_store_its_files_or_a_forward_table(self):
        self.assertEqual(forward_db.DB, "forward.sqlite")
        self.assertTrue(all(table.startswith("fwd_") for table in forward_db.TABLES))
        for tree in SEALED_TREES:
            self.assertEqual(named(REPO, tree, NAMES, pattern=r"\bfwd_[a-z0-9_]+"), [], tree)

    def test_the_names_are_the_ones_the_ops_modules_use(self):
        # The scan looks for what the jobs really write (a renamed file would slip past a stale list).
        from league.ops import contam_probe, fill_minutes, forward_report

        self.assertEqual({forward_db.DB, forward_report.FILE, fill_minutes.DIR, contam_probe.FILE}, set(NAMES))
        for name in E3_OPS:
            self.assertTrue((REPO / "league" / "ops" / f"{name}.py").is_file(), name)

    def test_the_sealed_memory_tables_are_named_only_by_their_keepers(self):
        self.assertEqual(elane_memory.SEALED_TABLES, ("mem_contrib", "mem_series"))
        keepers = {"league/swarm/elane_memory.py", "league/swarm/elane_seal.py"}
        hits = [hit for hit in named(REPO, "league", elane_memory.SEALED_TABLES)
                if not hit.startswith(("league/ops/", "league/tests/")) and hit.split(":")[0] not in keepers]
        self.assertEqual(hits, [])
        self.assertTrue(named(REPO, "league/swarm", elane_memory.SEALED_TABLES), "their keeper does name them")

    def test_e3s_ops_modules_import_only_what_the_contract_lists(self):
        for name in E3_OPS:
            self.assertEqual(outside(REPO, REPO / "league" / "ops" / f"{name}.py", OPS_MAY), [], name)

    def test_the_memory_modules_import_the_equity_lane_and_the_swarm_inside_functions_only(self):
        for name in MEMORY:
            path = REPO / "league" / "swarm" / f"{name}.py"
            self.assertEqual(outside(REPO, path, MEMORY_TOP, inside=MEMORY_INSIDE), [], name)

    def test_only_the_train_the_births_and_ops_import_the_memory_modules(self):
        wanted = {f"league.swarm.{name}" for name in MEMORY}
        hits = []
        for path in sources(REPO, "league"):
            relative = path.relative_to(REPO).as_posix()
            if relative.startswith(("league/ops/", "league/tests/")) or relative in MEMORY_IMPORTERS:
                continue
            hits += [f"{relative}:{line} imports {module}" for module, _, line in imports(REPO, path) if module in wanted]
        self.assertEqual(hits, [])
        # Ops reads the tables' counts and nothing else of them.
        for name in E3_OPS:
            reached = {module for module, _, _ in imports(REPO, REPO / "league" / "ops" / f"{name}.py")}
            self.assertFalse(reached & {"league.swarm.elane_folds", "league.swarm.elane_effects"}, name)

    def test_the_ops_jobs_open_the_swarm_store_read_only(self):
        for name in E3_OPS:
            if name == "contam_probe":          # it books its dollars (league/swarm/elane_yield.py `book`)
                continue
            self.assertEqual(writable_swarm_opens(REPO, REPO / "league" / "ops" / f"{name}.py"), [], name)


class TheCheckCatchesWhatItShould(unittest.TestCase):
    """The readers above, on an invented checkout that breaks each rule once."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for package in ("league", "league/ops", "league/swarm", "league/equity", "league/live"):
            self.write(f"{package}/__init__.py", "")
        for name in ("forward_db", "forward_twins", "guard", "dlane_report"):
            self.write(f"league/ops/{name}.py", "VALUE = 1\n")
        for name in ("elane_train", "elane_seal", "elane_memory", "store", "loop"):
            self.write(f"league/swarm/{name}.py", "VALUE = 1\n")
        for name in ("config", "sizing"):
            self.write(f"league/equity/{name}.py", "VALUE = 1\n")

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_every_way_of_importing_an_ops_module_is_seen(self):
        for i, line in enumerate(("from ..ops import forward_db", "from ..ops.forward_db import open_db",
                                  "import league.ops.forward_twins as twins", "from league.ops import forward_twins",
                                  "def f():\n    from ..ops import forward_db\n    return forward_db",
                                  "import importlib\nX = importlib.import_module('league.ops.forward_db')",
                                  "try:\n    from ..ops import forward_db\nexcept ImportError:\n    forward_db = None")):
            self.write(f"league/swarm/case{i}.py", line + "\n")
            self.assertTrue(e3_ops_imports(self.root, "league/swarm"), line)
            (self.root / f"league/swarm/case{i}.py").unlink()
        # What is no import of one: another ops module, and the bare word (a function of that name lives in league/live).
        self.write("league/swarm/fine.py", "from ..ops import guard\n\n\ndef forward_stats(x):\n    return guard\n")
        self.write("league/live/money.py", "def forward_stats(rows):\n    return len(rows)\n")
        self.assertEqual(e3_ops_imports(self.root, "league/swarm") + e3_ops_imports(self.root, "league/live"), [])

    def test_a_name_in_any_text_is_seen(self):
        for i, text in enumerate(('PATH = "forward.sqlite"\n', "# reads <state>/forward-report.json\n",
                                  'SQL = "SELECT r FROM fwd_days WHERE pid=?"\n', "see equity-fill-minutes/2026\n",
                                  '{"file": "contamination.json"}\n')):
            self.write(f"league/equity/note{i}.md", text)
            self.assertEqual(len(named(self.root, "league/equity", NAMES, pattern=r"\bfwd_[a-z0-9_]+")), 1, text)
            (self.root / f"league/equity/note{i}.md").unlink()
        self.write("league/equity/fine.py", "forward = 1\nfwd = 2\nsqlite = 'swarm.sqlite'\n")
        self.assertEqual(named(self.root, "league/equity", NAMES, pattern=r"\bfwd_[a-z0-9_]+"), [])
        self.write("league/swarm/prompt.py", 'TEXT = "the mem_contrib rows"\n')
        self.assertEqual(len(named(self.root, "league", ("mem_contrib", "mem_series"))), 1)

    def test_an_import_outside_the_list_is_seen_and_where_it_sits(self):
        path = self.write("league/ops/forward_twins.py",
                          "from . import guard, forward_db\nfrom ..equity import config, VALUE\n"
                          "from ..equity import sizing\nfrom . import dlane_report\n")
        got = outside(self.root, path, OPS_MAY)
        self.assertEqual([hit.split(" imports ")[1] for hit in got], ["league.equity.sizing", "league.ops.dlane_report"])
        memory = self.write("league/swarm/elane_memory.py",
                            "from ..equity import config\nfrom . import elane_train\n\n\ndef ingest():\n"
                            "    from . import elane_seal, elane_train\n    from . import store\n    return store\n")
        got = outside(self.root, memory, MEMORY_TOP, inside=MEMORY_INSIDE)
        self.assertEqual([hit.split(" imports ")[1] for hit in got],
                         ["league.swarm.elane_train", "league.swarm.store inside a function"])

    def test_a_writable_open_of_the_swarm_store_is_seen(self):
        path = self.write("league/ops/forward_db.py",
                          "from ..swarm.store import SwarmStore\n\n\ndef a(root):\n    return SwarmStore(root)\n\n\n"
                          "def b(root):\n    return SwarmStore(root, readonly=False)\n\n\n"
                          "def c(root, flag):\n    return SwarmStore(root, readonly=flag)\n\n\n"
                          "def d(root):\n    return SwarmStore(root, readonly=True)\n")
        self.assertEqual(len(writable_swarm_opens(self.root, path)), 3)


if __name__ == "__main__":
    unittest.main()
