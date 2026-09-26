"""Deterministic checks for public helper proposals and owner releases.

Only engineer branches may modify pure helpers and their tests. Protected runtime,
judges, data, money code and operator tools require owner review. Content checks
validate public Gym examples, helper safety, operating bounds and the money table;
the suite covers the current House, Gym, swarm, live path and gateway contract.
Green CI supplies evidence for review; it never merges or deploys a change.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]

ROLE_PATHS: dict[str, tuple[str, ...]] = {
    "engineer": ("league/tools/", "league/tests/test_tool_"),
}
# Automatic proposals cannot change their judges, money rules, runner, data, or operator tools.
FORBIDDEN = ("gateway/", ".github/", "scripts/", "deploy/", "league/live/", "league/gym/",
             "league/swarm/", "league/constitution.py", "league/ledger.py", "league/ci.py",
             "league/updater.py", "league/watchdog.py", "league/house.py", "league/service.py",
             "league/live_trading.py", "league/safety.py", "league/engineer.json")
CONFIG_DIALS = {"tick_seconds": (30, 600), "publish_seconds": (30, 1800), "release_train_hours": (2, 6)}
PREFIXES = ("merton", "astra")


def role_of(branch: str) -> str | None:
    parts = str(branch or "").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] in PREFIXES else None


def guard(paths: Iterable[str], role: str | None) -> list[str]:
    """Why these paths may not be changed by this role. Empty means they may."""
    problems = []
    for path in paths:
        clean = os.path.normpath(path).replace("\\", "/")
        if clean.startswith(("../", "/")) or clean != path:
            problems.append(f"{path}: not a plain repository path")
            continue
        lowered = clean.lower()
        if any(lowered == f or (f.endswith("/") and lowered.startswith(f)) for f in FORBIDDEN):
            problems.append(f"{path}: no role may change this file")
        elif role is not None:
            allowed = ROLE_PATHS.get(role, ())
            if not any(clean == a or (a.endswith(("/", "_")) and clean.startswith(a)) for a in allowed):
                problems.append(f"{path}: outside what the {role} may change ({', '.join(allowed)})")
    return problems


def changed_paths(base: str, head: str = "HEAD", *, cwd: Path = REPO) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=cwd, capture_output=True, text=True, check=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def check_programs(root: Path = REPO) -> list[str]:
    """Public examples contain no learned parameters and obey the same sealed program contract."""
    from .gym.safety import check_program, CodeRefused
    problems = []
    for path in sorted((root / "league/gym/examples").glob("*.py")):
        try:
            check_program(path.read_text(encoding="utf-8"))
        except (CodeRefused, OSError) as exc:
            problems.append(f"{path.relative_to(root)}: {exc}")
    return problems


def check_tools(root: Path = REPO) -> list[str]:
    from .safety import CodeRefused, check_strategy_code

    problems = []
    for path in sorted((root / "league" / "tools").glob("*.py")):
        if path.name == "__init__.py":
            continue
        try:
            check_strategy_code(path.read_text(encoding="utf-8"))
        except CodeRefused as exc:
            problems.append(f"league/tools/{path.name}: {exc}")
    return problems


def check_config(base: str | None, root: Path = REPO, *, baseline: Path | None = None) -> list[str]:
    """The operator may move the operating dials, inside bounds, and nothing else in config.json.

    `base` is a git ref (a pull request is measured against main); `baseline` is a code tree (the
    box's updater measures an incoming tree against the release it is running). Without either,
    only the dials' bounds are checked."""
    now = json.loads((root / "league" / "config.json").read_text(encoding="utf-8"))
    problems = [f"league/config.json: {key} = {now[key]} is outside [{low}, {high}]" for key, (low, high) in CONFIG_DIALS.items()
                if key in now and not low <= float(now[key]) <= high]
    before = None
    if base:
        shown = subprocess.run(["git", "show", f"{base}:league/config.json"], cwd=root, capture_output=True, text=True)
        if shown.returncode == 0:
            before = json.loads(shown.stdout)
    elif baseline is not None:
        before = json.loads((Path(baseline) / "league" / "config.json").read_text(encoding="utf-8"))
    if before is not None:
        for key in sorted(set(before) | set(now)):
            if before.get(key) != now.get(key) and key not in CONFIG_DIALS:
                problems.append(f"league/config.json: {key} is not an operating dial; only the owner changes it")
    return problems


#: The gateway's line that names the structure types the REAL Alpaca account admits (`gateway/lib/caps.mjs`
#: `admittedStructures`), in `gateway/wrangler.jsonc` (JSON with comments: the line itself is read, as the gateway's own test does).
GATEWAY_STRUCTURES_LINE = re.compile(r'^\s*"OPTION_STRUCTURES_REAL"\s*:\s*"([^"\\]*)"\s*,?\s*(//.*)?$')


def gateway_structures(root: Path = REPO) -> tuple[list[str], list[str]]:
    """(the structure types the deployed gateway admits on the real account, why it could not be read): read from
    `gateway/wrangler.jsonc` as `admittedStructures` reads the variable -- "off" or empty admits none. A name that is not a
    structure type is a problem here (the gateway would admit none, silently: a typo is never a way to switch it)."""
    from .structure_core import TYPES

    try:
        text = (root / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"gateway/wrangler.jsonc: {exc}"]
    lines = [m.group(1) for m in (GATEWAY_STRUCTURES_LINE.match(line) for line in text.splitlines()) if m]
    if len([line for line in text.splitlines() if '"OPTION_STRUCTURES_REAL"' in line]) != 1 or len(lines) != 1:
        return [], ["gateway/wrangler.jsonc: OPTION_STRUCTURES_REAL must be set once, on its own line, to a quoted list"]
    raw = lines[0].strip()
    if not raw or raw.lower() == "off":
        return [], []
    names = [n for n in re.split(r"[\s,]+", raw) if n]
    unknown = [n for n in names if n not in TYPES]
    if unknown:
        return [], [f"gateway/wrangler.jsonc: OPTION_STRUCTURES_REAL names {', '.join(unknown)}, not a structure type"]
    return sorted(set(names)), []


def gateway_caps_problems(root: Path, table: dict[str, Any], names: dict[str, str]) -> list[str]:
    """The gateway's caps that repeat the options money table (`constitution.GATEWAY_VARS`), equal to it: a cap changes
    only with the money row it repeats (the review of #362, m17)."""
    from decimal import Decimal, InvalidOperation

    try:
        text = (root / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
    except OSError as exc:
        return [f"gateway/wrangler.jsonc: {exc}"]
    problems = []
    for var, path in names.items():
        found = re.findall(rf'^\s*"{var}"\s*:\s*"([^"]*)"', text, flags=re.M)
        node: Any = table
        for key in path.split("."):
            node = node.get(key) if isinstance(node, dict) else None
        if len(found) != 1:
            problems.append(f"gateway/wrangler.jsonc: {var} must be set once (it repeats options_money.{path})")
            continue
        try:
            same = Decimal(found[0]) == Decimal(str(node))
        except (InvalidOperation, ValueError):
            same = False
        if not same:
            problems.append(f"gateway/wrangler.jsonc: {var} is {found[0]!r} but options_money.{path} is {node!r}: they change together")
    return problems


def check_structures(root: Path = REPO) -> list[str]:
    """ONE source of truth for the structure types real money may open, and the money rows inside their bounds.

    Since the options swarm (Sept 26, 2026, Wave 5) the constitution's `options_money` table governs real money: its rows
    inside `constitution.OPTIONS_MONEY_BOUNDS` (`options_money_problems`), and the gateway's `OPTION_STRUCTURES_REAL`
    disabled, or admitting exactly its `real_types` (the gateway holds credit types back under $2,000 of equity). A tree
    whose constitution has no such table is judged by the options-desk run's rows (O1-O5, G of Sept 25, 2026): the gateway
    admits exactly `allocator.spread_types_real()` (`option_spread_real_types` while O1 is on, none while it is off). The
    constitution is read from `root` without importing the tree's package."""
    path = root / "league" / "constitution.py"
    try:
        # Compiled from its text, never through the import system: a cached bytecode file keyed by the source's mtime and
        # size could stand in for a file rewritten within the same second (the constitution imports only the standard library).
        namespace: dict[str, Any] = {"__name__": "_ci_constitution", "__file__": str(path)}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102 - the tree's own constitution
        constitution = namespace["CONSTITUTION"]
    except Exception as exc:  # noqa: BLE001 - a constitution that cannot be read is a refusal
        return [f"league/constitution.py could not be read: {type(exc).__name__}: {exc}"]
    table = constitution.get("options_money")
    if not isinstance(table, dict):
        return ["league/constitution.py: options_money is required"]
    problems = [f"league/constitution.py: {p}" for p in namespace["options_money_problems"](constitution)]
    wanted = sorted(set(table.get("real_types") or []))
    source = f"options_money.real_types {wanted}"
    gateway, unreadable = gateway_structures(root)
    problems += unreadable
    if table is not None and isinstance(table, dict):
        problems += gateway_caps_problems(root, table, namespace.get("GATEWAY_VARS") or {})
    if not problems and gateway != wanted and not (table is not None and not gateway):
        problems.append(f"gateway/wrangler.jsonc: OPTION_STRUCTURES_REAL admits {gateway or 'none'} on the real account, "
                        f"but the constitution opens {wanted or 'none'} ({source}): the two change together, in one deploy")
    return problems


def run_tests(root: Path = REPO) -> list[str]:
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "league/tests", "-t", "."], cwd=root, capture_output=True, text=True)
    if done.returncode != 0:
        tail = "\n".join((done.stderr or done.stdout).splitlines()[-25:])
        return [f"the test suite failed:\n{tail}"]
    return []


def guard_branch(base: str, head: str, branch: str, *, root: Path = REPO) -> list[str]:
    """The path guard alone. GitHub runs this from `main`'s copy of this file against the pull
    request's commits, so a branch cannot loosen the guard that judges it."""
    role = role_of(branch)
    if role is None:
        return [f"{branch}: not a branch name of the form merton/<role>/<slug>"]
    paths = changed_paths(base, head, cwd=root)
    if not paths:
        return ["the branch changes nothing"]
    return guard(paths, role)


def check(base: str | None, branch: str | None, *, root: Path = REPO, tests: bool = True, head: str = "HEAD") -> list[str]:
    problems: list[str] = []
    role = role_of(branch or "")
    paths = changed_paths(base, head, cwd=root) if base else []
    if (branch or "").startswith(tuple(f"{p}/" for p in PREFIXES)):
        if role is None:
            problems.append(f"{branch}: not a branch name of the form merton/<role>/<slug>")
        problems.extend(guard(paths, role))
    problems.extend(check_programs(root))
    problems.extend(check_tools(root))
    problems.extend(check_structures(root))
    problems.extend(check_config(base if role == "operator" or "league/config.json" in paths and (branch or "").startswith(tuple(f"{p}/" for p in PREFIXES)) else None, root))
    if tests and not problems:
        problems.extend(run_tests(root))
    return problems


def annotate(problems: list[str], *, out: Any = None) -> None:
    """Each refusal again as a GitHub error annotation, which the check run keeps and the gateway
    can read back (`GET /v1/github/pr/<n>/failures`). The plain log is not reachable without a
    download credential, so until Sept 22, 2026 the House learned only that CI said no, never why,
    and a failed proposal could not be revised. Annotations add nothing to the verdict."""
    stream = out or sys.stdout
    for problem in problems[:40]:
        text = str(problem)[:4000].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=league.ci refused::{text}", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=None, help="the ref the change is measured against (origin/main)")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or "")
    parser.add_argument("--head", default="HEAD", help="the commit being judged")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--guard-only", action="store_true", help="only the path guard (run from main's copy of this file)")
    parser.add_argument("--content-only", action="store_true",
                        help="only the content checks, with no git and no test run: what the box's updater asks an incoming tree")
    parser.add_argument("--root", default=None,
                        help="with --content-only: the tree to judge (default: this file's own tree). The box's updater runs "
                             "the RUNNING release's copy of this file against the incoming tree this way")
    parser.add_argument("--baseline", default=None,
                        help="with --content-only: the tree the judged one replaces; config.json may move only its dials from it")
    parser.add_argument("--nonce-stdin", action="store_true",
                        help="read one line from stdin before anything is judged and end with `VERDICT <line> <json>`")
    args = parser.parse_args(argv)
    nonce = sys.stdin.readline().strip() if args.nonce_stdin else ""
    if args.nonce_stdin:
        # Read, and stdin closed, BEFORE any strategy file is loaded: the verdict line carries a
        # secret the judged code never had a chance to see, so a module body that prints
        # "ci: passed" and exits proves nothing (the safety check already bans `input` and `exit`;
        # this is the second wall).
        sys.stdin.close()
    if args.content_only:
        # Run by `Updater.vet` from the RUNNING release (`--root` names the incoming tree), so a
        # candidate is judged by code it could not have edited. See `league/updater.py` for why
        # this reversed the Sept 20, 2026 choice to let a tree judge itself.
        root = Path(args.root).resolve() if args.root else REPO
        baseline = Path(args.baseline).resolve() if args.baseline else None
        problems = check_programs(root) + check_tools(root) + check_structures(root) + check_config(None, root, baseline=baseline)
    elif args.guard_only:
        problems = guard_branch(args.base or "origin/main", args.head, args.branch)
    else:
        problems = check(args.base, args.branch, tests=not args.no_tests, head=args.head)
    for problem in problems:
        print("REFUSED:", problem)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        annotate(problems)
    print("ci:", "refused" if problems else "passed", f"({args.branch or 'no branch'})")
    if args.nonce_stdin:
        print("VERDICT", nonce, json.dumps({"passed": not problems, "problems": problems}, sort_keys=True), flush=True)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
