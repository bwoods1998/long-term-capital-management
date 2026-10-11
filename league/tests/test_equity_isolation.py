"""THE LANES' BOUNDARY (release E1; amendment A8.8, invariant I5; league/equity/INTERFACES.md section 2): read from the
code itself, by its syntax tree.

1. league/live reaches league.equity through exactly two modules: league/live/equity_hook.py (any of it) and
   league/live/decider.py (`league.equity.kinds` only: the generic kind table, so a later equity kind needs no
   league/live edit).
2. league/live/step.py contains `.equity.tick(` exactly once, inside `OptionsLive.minute`: equity behaviour cannot hide
   in the options step.
3. The evidence modules of league/equity (and its kind table) import nothing of league.live and nothing of
   league.swarm, and the kind table names only modules of league/equity and of league/xs (the panel kind's slot, A13).
4. league/xs (A13) imports nothing of league.live and nothing of league.swarm, and league/live never names it: the
   decider reaches it through the kind table alone.

A change to league/live moves the options execution fingerprint; one to league/equity's evidence modules the equity
fingerprint only (A13: its plumbing moves neither). These tests are what keep the second true."""

import ast
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE = REPO / "league" / "live"
EQUITY = REPO / "league" / "equity"
XS = REPO / "league" / "xs"
#: league/live module -> the league.equity modules it may name (None: any).
DOORS = {"equity_hook.py": None, "decider.py": {"league.equity.kinds"}}
#: INTERFACES.md 2.2: the evidence modules (their code decides what a program's evidence is) and the decider's kind
#: table (plumbing since A13, outside the equity identity, but read inside the child like them).
EVIDENCE = ("config", "store", "program", "ctx", "engine", "results", "runner", "synth", "sizing", "screen", "child",
            "kinds")
#: The packages a decider kind's module may live in: the equity lane's, and the panel kind's slot (A13).
KIND_HOMES = ("league.equity", "league.xs")
MODULE_NAME = re.compile(r"^league(\.[A-Za-z_][A-Za-z0-9_]*)+$")


def module_of(path: Path) -> str:
    return ".".join(path.relative_to(REPO).with_suffix("").parts)


def references(path: Path, module: str | None = None) -> set[str]:
    """Every module `path` imports (absolute names; `from X import Y` names X.Y when Y is a module of the repository,
    else X), and every string that is exactly a league module name (an `importlib.import_module` target). `module`:
    the file's own dotted name when it is not inside the repository (the reader's own test)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = (module or module_of(path)).rsplit(".", 1)[0]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            for alias in node.names:
                full = f"{module}.{alias.name}"
                as_path = REPO.joinpath(*full.split("."))
                out.add(full if as_path.with_suffix(".py").is_file() or (as_path / "__init__.py").is_file() else module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and MODULE_NAME.match(node.value):
            out.add(node.value)
    return out


def within(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


class TheOneDoor(unittest.TestCase):
    def test_league_live_reaches_the_equity_lane_only_through_its_two_doors(self):
        found = {}
        for path in sorted(LIVE.rglob("*.py")):
            names = {n for n in references(path) if within(n, "league.equity")}
            if names:
                found[path.relative_to(LIVE).as_posix()] = names
        self.assertLessEqual(set(found), set(DOORS), f"league/live modules naming league.equity: {found}")
        for name, allowed in DOORS.items():
            if allowed is not None:
                self.assertLessEqual(found.get(name, set()), allowed, f"{name} may name only {sorted(allowed)}")
        self.assertIn("equity_hook.py", found, "the door is used")
        self.assertEqual(found.get("decider.py"), {"league.equity.kinds"})

    def test_league_live_never_names_the_panel_slot(self):
        """A13: league/xs is reached only through the kind table (league/equity/kinds.py), never by a league/live
        import, so building the panel lane there needs no league/live edit (the options fingerprint does not move)."""
        found = {path.relative_to(LIVE).as_posix(): names for path in sorted(LIVE.rglob("*.py"))
                 if (names := {n for n in references(path) if within(n, "league.xs")})}
        self.assertEqual(found, {})

    def test_the_reader_sees_every_spelling(self):
        """The check itself: relative, absolute, package-level and string spellings are all caught."""
        import tempfile

        samples = {"from ..equity import live\n": {"league.equity.live"}, "from .. import equity\n": {"league.equity"},
                   "import league.equity.ctx as C\n": {"league.equity.ctx"},
                   "from ..equity import LANES\n": {"league.equity"},
                   "import importlib\nimportlib.import_module('league.equity.engine')\n": {"league.equity.engine"},
                   '"""league.equity is named in prose."""\n': set()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            for code, want in samples.items():
                path.write_text(code)
                with self.subTest(code=code):
                    self.assertEqual({n for n in references(path, "league.live.sample") if within(n, "league.equity")},
                                     want)


class TheOneCall(unittest.TestCase):
    def test_step_calls_the_equity_book_once_a_minute_and_nowhere_else(self):
        text = (LIVE / "step.py").read_text(encoding="utf-8")
        self.assertEqual(text.count(".equity.tick("), 1)
        tree = ast.parse(text)
        [live] = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OptionsLive"]
        [minute] = [n for n in live.body if isinstance(n, ast.FunctionDef) and n.name == "minute"]
        self.assertIn(".equity.tick(", ast.get_source_segment(text, minute))
        # ... once in the method's body, not in a loop: one call each time the minute runs.
        loops = [n for n in ast.walk(minute) if isinstance(n, (ast.For, ast.While))]
        self.assertFalse([n for n in loops if ".equity.tick(" in ast.get_source_segment(text, n)])

    def test_the_book_is_built_once_through_the_door(self):
        text = (LIVE / "step.py").read_text(encoding="utf-8")
        self.assertEqual(text.count("equity_hook.build_book("), 1)
        self.assertEqual(len(re.findall(r"self\.equity\s*=", text)), 1)

    def test_the_options_path_never_names_the_stock_paper_proof(self):
        """A10.1: the staged stock proof (kv `paper_proof_stock_buy`, `paper_proof_stock_sell`) is checked only by the
        equity book; an options entry never waits on either stage. In league/live it is defined in paper.py and handed
        to the EquityBook by equity_hook.py, and no other module of the options path names it."""
        words = ("StockPaperProof", "stock_proof", "paper_proof_stock", "STOCK_KEY", "STOCK_BUY_KEY", "STOCK_SELL_KEY")
        named = {path.relative_to(LIVE).as_posix() for path in sorted(LIVE.rglob("*.py"))
                 if any(word in path.read_text(encoding="utf-8") for word in words)}
        self.assertEqual(named, {"paper.py", "equity_hook.py"})
        book = (EQUITY / "live.py").read_text(encoding="utf-8")
        for call in ("stock_proof.buy_passed()", "stock_proof.sell_failed()", "stock_proof.sell_passed()"):
            self.assertIn(call, book, "the equity book's own gates: BUY for every real buy, SELL for every real sale")


class TheEvidenceModules(unittest.TestCase):
    def test_they_import_nothing_of_the_live_path_or_the_swarm(self):
        for name in EVIDENCE:
            path = EQUITY / f"{name}.py"
            with self.subTest(module=name):
                self.assertTrue(path.is_file())
                bad = {n for n in references(path) if within(n, "league.live") or within(n, "league.swarm")}
                self.assertEqual(bad, set())

    def test_the_kind_table_names_modules_of_the_lane_and_of_the_panel_slot(self):
        from league.equity import kinds

        self.assertEqual(kinds.KINDS, {"equity": "league.equity.child", "panel": "league.xs.child"})
        for kind, module in kinds.KINDS.items():
            with self.subTest(kind=kind):
                self.assertTrue(any(within(module, home) for home in KIND_HOMES), module)
                self.assertTrue(REPO.joinpath(*module.split(".")).with_suffix(".py").is_file(), module)
                self.assertTrue(callable(getattr(kinds.module_for(kind), "handle", None)))
                # Each kind's package is in the child's sealed runtime, whole.
                self.assertIn("/".join(module.split(".")[:-1]) + "/", kinds.RUNTIME)

    def test_the_panel_slot_imports_nothing_of_the_live_path_or_the_swarm(self):
        """A13's slot is the panel lane's package since release E4: a FLAT package (the decider child's runtime copies
        league/xs/*.py only) that still holds the kind's child, and no module of it names the live path or the swarm."""
        modules = sorted(XS.rglob("*.py"))
        names = [p.relative_to(XS).as_posix() for p in modules]
        self.assertLessEqual({"__init__.py", "child.py"}, set(names), "the package and the kind's child")
        self.assertEqual([name for name in names if "/" in name], [], "league/xs stays flat")
        for path in modules:
            with self.subTest(module=path.name):
                bad = {n for n in references(path) if within(n, "league.live") or within(n, "league.swarm")}
                self.assertEqual(bad, set())


if __name__ == "__main__":
    unittest.main()
