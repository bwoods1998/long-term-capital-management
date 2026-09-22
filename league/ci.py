"""The judge of every change Merton proposes. It runs in GitHub Actions on every pull request,
and again on the House box before a merged change is staged, and it decides alone: nothing here
asks a model anything.

    python3 -m league.ci --base origin/main [--branch merton/architect/some-slug]

1. **Path guard.** A branch named `merton/<role>/...` may touch only that role's paths. The
   constitution, the ledger, the book, the evaluator, the statistics, the auditor, the watchdog,
   this file, the gateway and the workflows are out of reach of every role. (The gateway enforces
   the same list before a branch exists; this is the second wall, and it also covers a branch
   pushed some other way.)
2. **Content checks.** Strategy files must pass the sandbox safety check, declare valid NEEDS, be
   listed in the registry, and run through the replay simulator on a canned tape without one
   error. `game.json` must stay inside its bounds. `config.json` may change only its operating
   dials, never where money or secrets are concerned. Tools must pass the same safety check as
   strategies, because they run in the same boxes.
3. **The whole test suite**, and with it the replay regression: every founding seed replayed over
   the canned tapes must produce exactly the recorded result, so a change that shifts the
   simulator's arithmetic cannot slip through as a refactor.

Exit 0 means the change may merge. Anything else is a refusal, with the reasons printed.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]

ROLE_PATHS: dict[str, tuple[str, ...]] = {
    "architect": ("league/strategies/",),
    "toolsmith": ("league/tools/", "league/tests/test_tool_"),
    "operator": ("league/config.json",),
    "designer": ("league/game.json",),
    "teacher": ("league/playbook/",),
}
#: Never, for any role, whatever the table above comes to say.
FORBIDDEN: tuple[str, ...] = (
    "league/constitution.py", "league/ci.py", "league/ledger.py", "league/book.py", "league/evaluator.py",
    "league/stats.py", "league/auditor.py", "league/watchdog.py", "league/safety.py", "league/replay.py", "league/updater.py",
    "gateway/", ".github/",
    "league/campaigns.json", "league/campaigns.py", "league/funded.py", "league/experiments.py", "league/recordings.py", "league/research_jobs.py", "league/capabilities.py", "league/parameters.py",
    "league/live_trading.py", "league/live_pilot.py", "scripts/live_trading.py", "scripts/live_pilot.py",
    # The history a strategy is judged on and the seal on its holdout are judges too.
    "league/history.py", "league/deep_replay.py",
)
#: The only keys of league/config.json the operator may move, with their bounds.
CONFIG_DIALS: dict[str, tuple[float, float]] = {
    "tick_seconds": (30, 600), "mark_every_seconds": (60, 1800), "replay_days": (7, 60), "inference_daily_cap_usd": (0.5, 25.0),
}


#: The branch prefixes a proposal of Merton's may arrive under. `merton/` is what the gateway's
#: source emits; `astra/` is what the DEPLOYED gateway still emitted on Sept 20, 2026, months after
#: the rename -- so every pull request he opened landed on a branch the merge workflow ignored, sat
#: open for ever, and nothing anywhere said so. The floor could propose changes to itself and never
#: land one. Both are accepted until the gateway is redeployed; the role is the second segment
#: either way, so the path guard is exactly as tight.
PREFIXES = ("merton", "astra")


def role_of(branch: str) -> str | None:
    parts = str(branch or "").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] in PREFIXES and parts[1] in ROLE_PATHS else None


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
            allowed = ROLE_PATHS[role]
            if not any(clean == a or (a.endswith(("/", "_")) and clean.startswith(a)) for a in allowed):
                problems.append(f"{path}: outside what the {role} may change ({', '.join(allowed)})")
    return problems


def changed_paths(base: str, head: str = "HEAD", *, cwd: Path = REPO) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...{head}"], cwd=cwd, capture_output=True, text=True, check=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


# ------------------------------------------------------------------------ canned tapes
def regression_tape(venue: str, *, steps: int = 600, seed: int = 7) -> dict[str, Any]:
    """A deterministic synthetic tape: enough structure for a strategy to trade on, no meaning."""
    rng = random.Random(seed)
    if venue == "alpaca":
        prices = {"BTC/USD": 80000.0, "ETH/USD": 2600.0, "SOL/USD": 150.0, "SPY": 650.0, "QQQ": 560.0, "IWM": 230.0, "TLT": 90.0, "GLD": 300.0}
        rows = []
        for i in range(steps):
            minute = i * 15
            bars = {}
            for symbol in prices:
                drift = 0.004 * (1 if (i // 40) % 2 == 0 else -1) / 40
                move = rng.gauss(drift, 0.004)
                opened = prices[symbol]
                closed = max(opened * (1 + move), 0.01)
                high, low = max(opened, closed) * (1 + abs(rng.gauss(0, 0.001))), min(opened, closed) * (1 - abs(rng.gauss(0, 0.001)))
                prices[symbol] = closed
                bars[symbol] = {"o": round(opened, 4), "h": round(high, 4), "l": round(low, 4), "c": round(closed, 4), "v": 10.0}
            day, rest = divmod(minute, 1440)
            rows.append({"t": f"2026-08-{3 + day:02d}T{rest // 60:02d}:{rest % 60:02d}:00Z", "bars": bars})
        return {"venue": "alpaca", "horizon": "hour", "step_seconds": 900, "half_spread_bps": 2.0, "steps": rows, "results": {}}
    rows, results = [], {}
    for hour in range(max(steps // 12, 8)):
        day, clock = divmod(hour, 24)
        close = f"2026-08-{3 + day:02d}T{clock:02d}:55:00Z"
        markets = []
        for strike in range(4):
            name = f"KXBTCD-REG{hour:03d}-T{80000 + strike * 250}"
            fair = min(max(0.97 - strike * 0.27 + rng.gauss(0, 0.02), 0.03), 0.97)
            results[name] = "yes" if rng.random() < fair else "no"
            markets.append((name, fair))
        for minute in range(0, 55, 5):
            stamp = f"2026-08-{3 + day:02d}T{clock:02d}:{minute:02d}:00Z"
            listed = []
            for name, fair in markets:
                bid = round(min(max(fair + rng.gauss(0, 0.01) - 0.01, 0.01), 0.98), 2)
                ask = round(min(bid + 0.02, 0.99), 2)
                listed.append({"market": name, "series": "KXBTCD", "title": "Bitcoin price", "yes_bid": bid, "yes_ask": ask,
                               "yes_ask_low": round(max(ask - 0.02, 0.01), 2), "yes_bid_high": round(min(bid + 0.02, 0.99), 2),
                               "close_time": close, "volume_24h": 20000.0, "open_interest": 5000.0, "strike": float(name.rsplit("T", 1)[1])})
            rows.append({"t": stamp, "markets": listed})
        rows.append({"t": close, "markets": []})
    return {"venue": "kalshi", "horizon": "hour", "step_seconds": 300, "steps": rows, "results": results}


# ------------------------------------------------------------------------- content checks
def check_strategy(path: Path) -> list[str]:
    from .replay import run_replay
    from .runner import needs_of

    code = path.read_text(encoding="utf-8")
    described = needs_of(code)
    if not described.get("ok"):
        return [f"{path.name}: {described.get('error')}"]
    try:
        from .agents import niche_of

        venue, _, _ = niche_of(described["needs"])
        from .parameters import require_valid
        require_valid(described.get("params") or {}, described["needs"])
    except ValueError as exc:
        return [f"{path.name}: {exc}"]
    from . import niches

    if niches.match(described["needs"], niches.load()) is None:
        return [f"{path.name}: its NEEDS sit in no open specialty of league/niches.json (the House would refuse to let it be born)"]
    result = run_replay(code, {}, regression_tape(venue, steps=240))
    if not result.get("ok"):
        return [f"{path.name}: the replay did not run: {result.get('error')}"]
    if int(result.get("errors") or 0) > 0:
        return [f"{path.name}: decide raised {result['errors']} times on the canned tape ({result.get('last_error')})"]
    return []


def check_strategies(root: Path = REPO) -> list[str]:
    from . import strategies

    problems = []
    rows = strategies.registry(root / "league" / "strategies")
    listed = {row["file"] for row in rows}
    for path in sorted((root / "league" / "strategies").glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.name not in listed:
            problems.append(f"{path.name}: not listed in league/strategies/registry.json")
        problems.extend(check_strategy(path))
    for row in rows:
        if not (root / "league" / "strategies" / row["file"]).exists():
            problems.append(f"registry.json lists {row['file']}, which does not exist")
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


def check_game(root: Path = REPO) -> list[str]:
    from .economy import check_bounds

    try:
        check_bounds(json.loads((root / "league" / "game.json").read_text(encoding="utf-8")))
    except (ValueError, KeyError) as exc:
        return [f"league/game.json: {exc}"]
    return []


def check_config(base: str | None, root: Path = REPO) -> list[str]:
    """The operator may move the operating dials, inside bounds, and nothing else in config.json."""
    now = json.loads((root / "league" / "config.json").read_text(encoding="utf-8"))
    problems = [f"league/config.json: {key} = {now[key]} is outside [{low}, {high}]" for key, (low, high) in CONFIG_DIALS.items()
                if key in now and not low <= float(now[key]) <= high]
    if base:
        shown = subprocess.run(["git", "show", f"{base}:league/config.json"], cwd=root, capture_output=True, text=True)
        if shown.returncode == 0:
            before = json.loads(shown.stdout)
            for key in sorted(set(before) | set(now)):
                if before.get(key) != now.get(key) and key not in CONFIG_DIALS:
                    problems.append(f"league/config.json: {key} is not an operating dial; only the owner changes it")
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
    problems.extend(check_strategies(root))
    problems.extend(check_tools(root))
    problems.extend(check_game(root))
    problems.extend(check_config(base if role == "operator" or "league/config.json" in paths and (branch or "").startswith(tuple(f"{p}/" for p in PREFIXES)) else None, root))
    if tests and not problems:
        problems.extend(run_tests(root))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=None, help="the ref the change is measured against (origin/main)")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or "")
    parser.add_argument("--head", default="HEAD", help="the commit being judged")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--guard-only", action="store_true", help="only the path guard (run from main's copy of this file)")
    parser.add_argument("--content-only", action="store_true",
                        help="only the content checks, with no git and no test run: what the box's updater asks an incoming tree")
    args = parser.parse_args(argv)
    if args.content_only:
        # Run by `Updater.vet` in the INCOMING tree, so a tree is judged by its own rules rather
        # than by a judge one commit out of date -- the two disagreed, and a commit that widened a
        # bound and used the wider value could never reach the box.
        problems = check_strategies() + check_tools() + check_game() + check_config(None)
    elif args.guard_only:
        problems = guard_branch(args.base or "origin/main", args.head, args.branch)
    else:
        problems = check(args.base, args.branch, tests=not args.no_tests, head=args.head)
    for problem in problems:
        print("REFUSED:", problem)
    print("ci:", "refused" if problems else "passed", f"({args.branch or 'no branch'})")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
