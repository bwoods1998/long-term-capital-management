"""The Foundry: an hourly evidence loop for the floor's strategies (leap: foundry).

The floor already learns, but slowly: a shadow variant needs twelve settlements before
`Strategies.promote` reads it, the committee's gates need days, and the lab sits down once a
night. The Foundry turns that into an evidence loop that runs around the clock:

1. **Candidates.** Every `interval_minutes` (30) it takes the next family in round-robin, and the
   next of that family's strategies (its house starter, then whatever its live desk runs). It
   builds the baselines (the live desk's settings and the best shadow's), `param_candidates`
   (10) settings jittered around the best-known ones with categorical flips drawn from the
   family's `STARTER_VARIANTS`, all seeded by the cycle, and `code_candidates` (2) mutations of
   the code written by a model and validated with the lab's own `validate_change`.
2. **Backtests.** Every candidate is replayed on the last `window_days` (5) of real Kalshi and
   Coinbase history by the backtest engine (`python3 -m ltcm.backtest --spec FILE`), one run per
   Sail sandbox (`foundry-0` .. `foundry-7`), side by side.
3. **Selection** reads only the out-of-sample third of each run's closed positions: enough
   trades, a return on notional above the best baseline's by `margin`, and a 95% confidence
   lower bound on the mean P&L per trade above `min_ci_lower`.
4. **Shadow.** The best qualifier goes onto the family's worst-performing shadow desk at once:
   new params on that desk's strategy row, or new code through `Strategies.install`. A live
   desk is never touched here.
5. **Live.** A deployed candidate whose backtest cleared the confidence bound and whose forward
   shadow record since deployment has `min_forward_settled` (5) settlements at P&L >= 0 is
   adopted by the family's live desk, the way `Strategies.promote` moves settings; its
   `promoted_at` resets the evidence. Risk limits, sizes, caps and capital never change here.

Everything is on the tape with existing kinds: a `lab.hypothesis` per cycle, a `desk.code_run`
on every desk that received a deployment or an adoption, an `ops.alert` for an adoption. A
cycle never raises and never runs twice at once. Standard library only.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import queue
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from .events import now_iso
from .lab import KIT_API, LabError, validate_change
from .strategies import (
    QUOTE_VARIANTS,
    SECOND_STARTERS,
    STARTER_CADENCE,
    STARTER_VARIANTS,
    STARTERS,
    STARTERS_DIR,
    _epoch,
    _return_on_notional,
)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "interval_minutes": 30,
    # Weather is not backtestable: its starter prices from NWS forecasts, which have no history.
    "families": ["kalshi", "ranges", "crypto"],
    "param_candidates": 10,
    "code_candidates": 2,
    "profile": "k3",
    "reasoning_effort": "high",
    "max_output_tokens": 16000,
    "budget_usd_per_day": "25",
    "sandboxes": 8,
    "backtest_timeout_seconds": 900,
    # Each backtest sandbox's own daily fuse; a desk's fuse would stop the loop by mid-morning.
    "sandbox_daily_seconds": 43200,
    "window_days": 5,
    "step_minutes": 15,
    "family_step_minutes": {"ranges": 5},
    "learning_usd": 10,
    "fill_model": "conservative",
    "max_markets": 3000,
    "seed": 7,
    "split_fraction": 0.66,
    "min_oos_trades": 25,
    "min_trades": 60,
    "margin": 0.01,
    "min_ci_lower": 0.0,
    "min_forward_settled": 5,
    "jitter_min": 0.10,
    "jitter_max": 0.50,
    "code_chars": 14000,
    # A shadow desk that received a candidate is not handed another for this long, so the
    # candidate earns a forward record; after `forward_max_hours` without one it expires.
    "protect_hours": 6,
    "forward_max_hours": 72,
    # Size, order counts and price guards are the floor's, never a candidate's: they are neither
    # jittered nor taken from a model's params, and a desk keeps its own values when it adopts.
    "frozen_params": [
        "notional_usd", "no_max", "max_new", "max_intents", "max_quotes", "max_symbols",
        "max_open_per_series", "max_open_per_event", "pages",
    ],
}
UNBACKTESTABLE_FAMILIES = ("weather",)
UNBACKTESTABLE_STRATEGIES = ("daily_temps",)
BUDGET_DESK = "foundry"
RESULT_MARKER = "BACKTEST-RESULT "
#: The longest result line the sandbox prints: its output is bounded at 4,000 characters.
RESULT_LINE_CHARS = 3600
#: A Foundry-made strategy name: `<starter>_f<cycle>` or `<starter>_f<cycle>_<n>`.
FOUNDRY_NAME = re.compile(r"_f\d+(?:_\d+)?$")
STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PAYLOAD_BYTES = 3000
DIRECTIONS = (
    "the pricing or selection model: which markets it trades and what it believes they are worth",
    "entries and exits: the price it pays, when it steps back, and what it declines to trade",
    "a filter that removes the kind of trade that loses out of sample",
)


# --------------------------------------------------------------------------- evidence
def split_evidence(trade_pnls, notional_usd, fraction=0.66):
    """In-sample and out-of-sample evidence from a backtest's closed positions, in order.

    The first `fraction` of the positions are in sample, the rest out of sample. Return on
    notional charges each position the run's average notional per position; the confidence
    interval is the normal one on the mean P&L per position (None under two positions). This
    function is also shipped verbatim inside the backtest runner, so it uses `math` only.
    """
    pnls = []
    for value in trade_pnls or []:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            pnls.append(number)
    count = len(pnls)
    cut = int(math.floor(count * float(fraction)))
    try:
        notional = float(notional_usd or 0.0)
    except (TypeError, ValueError):
        notional = 0.0
    per_position = notional / count if count and notional > 0 else 0.0

    def part(rows):
        n = len(rows)
        total = sum(rows)
        ron = round(total / (per_position * n), 6) if n and per_position > 0 else None
        ci = None
        if n >= 2:
            mean = total / n
            sd = math.sqrt(sum((x - mean) ** 2 for x in rows) / (n - 1))
            half = 1.96 * sd / math.sqrt(n)
            ci = [round(mean - half, 6), round(mean + half, 6)]
        return {"trades": n, "pnl_usd": round(total, 6), "return_on_notional": ron, "ci95_mean_pnl": ci}

    return {"in_sample": part(pnls[:cut]), "out_of_sample": part(pnls[cut:])}


#: Uploaded as the sandbox's `main.py` for one backtest: write the spec, run the engine's main,
#: and print one compact result line (the engine's report with its split, sized to the sandbox's
#: bounded output). A failure of any kind is a report with `unsupported`, never a bare traceback.
RUNNER = r'''
import contextlib, io, json, math, sys, traceback
sys.path.insert(0, "/lab")
sys.path.insert(0, "/lab/floor")
SPEC = json.loads(%(spec)s)
FRACTION = %(fraction)r
LIMIT = %(limit)d
MARKER = "BACKTEST-RESULT "

%(split_source)s

SCALARS = ("strategy", "start", "end", "steps", "trades", "fills", "settled", "wins", "notional_usd", "pnl_usd",
           "fees_usd", "return_on_notional", "max_drawdown_usd", "ci95_mean_pnl", "errors", "unsupported")

def compact(report, split):
    keep = {key: report[key] for key in SCALARS if key in report}
    if isinstance(keep.get("unsupported"), str):
        keep["unsupported"] = keep["unsupported"][:400]
    keep["notes"] = [str(note)[:200] for note in (report.get("notes") or [])[:4]]
    keep["daily"] = list(report.get("daily") or [])[-7:]
    keep["split"] = split
    pnls = [x for x in (report.get("trade_pnls") or []) if isinstance(x, (int, float))]
    for digits in (4, 2):
        keep["trade_pnls"] = [round(float(x), digits) for x in pnls]
        line = json.dumps(keep, separators=(",", ":"), default=str)
        if len(line) <= LIMIT:
            return line
    keep["trade_pnls"] = []
    keep["trade_pnls_dropped"] = len(pnls)
    keep["daily"] = keep["daily"][-2:]
    line = json.dumps(keep, separators=(",", ":"), default=str)
    if len(line) > LIMIT:
        keep["notes"], keep["daily"] = [], []
        line = json.dumps(keep, separators=(",", ":"), default=str)
    return line

report, failure, text = None, None, ""
path = "/lab/run/foundry-spec.json"
try:
    with open(path, "w") as handle:
        json.dump(SPEC, handle)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            try:
                from ltcm import backtest
                backtest.main(["--spec", path])
            except SystemExit:
                pass
    finally:
        text = buffer.getvalue()
except Exception:
    failure = traceback.format_exc()[-400:]
marker = text.rfind(MARKER)
if marker >= 0:
    try:
        report = json.loads(text[marker + len(MARKER):].split("\n", 1)[0])
    except ValueError:
        failure = failure or "the engine's result line did not parse"
if not isinstance(report, dict):
    report = {"strategy": SPEC.get("strategy"), "trades": 0, "errors": 1, "trade_pnls": [],
              "unsupported": "engine failed: " + str(failure or ("no result line; " + text[-300:]))}
split = None
try:
    from ltcm import backtest as engine
    split = engine.split_report(report, FRACTION)
except Exception:
    split = None
if not isinstance(split, dict) or not isinstance(split.get("out_of_sample"), dict):
    split = split_evidence(report.get("trade_pnls") or [], report.get("notional_usd"), FRACTION)
print(MARKER + compact(report, split))
'''


def runner_code(spec: Mapping[str, Any], *, fraction: float = 0.66) -> str:
    """The sandbox program for one backtest of `spec`."""
    return RUNNER % {
        "spec": json.dumps(json.dumps(dict(spec), default=str)),
        "fraction": float(fraction),
        "limit": RESULT_LINE_CHARS,
        "split_source": inspect.getsource(split_evidence),
    }


def parse_result(stdout: str | None) -> dict[str, Any] | None:
    """The report on the last `BACKTEST-RESULT` line, or None."""
    text = str(stdout or "")
    marker = text.rfind(RESULT_MARKER)
    if marker < 0:
        return None
    line = text[marker + len(RESULT_MARKER):].split("\n", 1)[0].strip()
    try:
        data = json.loads(line)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- candidates
def literal_defaults(code: str | None) -> dict[str, Any]:
    """A strategy module's `DEFAULTS = {...}`, read without running the module."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULTS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                return {}
            return dict(value) if isinstance(value, dict) else {}
    return {}


def base_name(name: str) -> str:
    """`kalshi_favorites_f12_2` -> `kalshi_favorites`."""
    return FOUNDRY_NAME.sub("", str(name or ""))


def categorical_pool(variants: list[Mapping[str, Any]], defaults: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Every choice (a string, a boolean, a list) the family's variants explore, with the code's
    default among them, for the keys where there is more than one value to flip between."""
    pool: dict[str, list[Any]] = {}
    for row in variants:
        for key, value in row.items():
            if isinstance(value, (bool, str, list)):
                values = pool.setdefault(key, [])
                if key in defaults and defaults[key] not in values and isinstance(defaults[key], (bool, str, list)):
                    values.append(defaults[key])
                if value not in values:
                    values.append(value)
    return {key: values for key, values in sorted(pool.items()) if len(values) >= 2}


def jitter_variants(
    base: Mapping[str, Any],
    *,
    seed: str,
    count: int,
    low: float = 0.10,
    high: float = 0.50,
    frozen: tuple[str, ...] | list[str] = (),
    pool: Mapping[str, list[Any]] | None = None,
    exclude: list[Mapping[str, Any]] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """`count` distinct settings around `base`, decided by `seed`.

    Variant i moves every number by up to a scale that runs from `low` to `high` across the
    variants (integers stay integers and at least one; a fraction stays inside [0, 1]); every
    other variant also flips one choice to another value from `pool`. Frozen keys never move.
    Returns (params, how) pairs; a setting equal to `base`, to one in `exclude` or to an earlier
    variant is drawn again, a bounded number of times."""
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big"))
    choices = {k: list(v) for k, v in (pool or {}).items() if k not in frozen}
    seen = [dict(base)] + [dict(row) for row in (exclude or [])]
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    count = max(0, int(count))
    attempt = 0
    while len(out) < count and attempt < count * 6:
        index = attempt % max(1, count)
        attempt += 1
        scale = low + (high - low) * (index / max(1, count - 1))
        params: dict[str, Any] = {}
        for key in sorted(base):
            value = base[key]
            if key in frozen or isinstance(value, bool) or not isinstance(value, (int, float)):
                params[key] = value
                continue
            moved = value * (1.0 + rng.uniform(-scale, scale))
            if isinstance(value, int):
                moved = int(round(moved))
                if value >= 1:
                    moved = max(1, moved)
            else:
                moved = round(moved, 4)
                if 0.0 <= value <= 1.0:
                    moved = min(1.0, max(0.0, moved))
            params[key] = moved
        flipped = None
        if choices and index % 2 == 1:
            keys = sorted(choices)
            key = keys[rng.randrange(len(keys))]
            others = [v for v in choices[key] if v != params.get(key)]
            if others:
                params[key] = others[rng.randrange(len(others))]
                flipped = key
        if params in seen:
            continue
        seen.append(params)
        out.append((params, {"scale": round(scale, 3), "flip": flipped}))
    return out


def parse_reply(body: str | None) -> dict[str, Any] | None:
    """The JSON object in a model reply, tolerating prose and a fence around it."""
    text = str(body or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- small helpers
def _sha(text: str | None) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _dec(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _clean(value: Any) -> Any:
    """Safe for the public tape: no markup, recursively."""
    if isinstance(value, str):
        return value.replace("<", "\u2039")
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _fmt(value: Any, spec: str = "+.3f") -> str:
    number = _float(value)
    return "n/a" if number is None else format(number, spec)


def _full(params: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {**dict(defaults), **dict(params)}


def _compact(full: Mapping[str, Any], defaults: Mapping[str, Any], keep: set[str]) -> dict[str, Any]:
    """The overrides a strategy row needs: keys the code lacks, keys set away from the code's
    default, and keys the best-known setting already named."""
    return {k: v for k, v in sorted(full.items()) if k in keep or k not in defaults or defaults[k] != v}


class Foundry:
    """Generate, backtest, select, deploy, fast-track. Owned by the service; `cycle()` is the
    whole loop and runs off the tick."""

    def __init__(
        self,
        *,
        log: Any,
        strategies: Any,
        sandboxes: Any,
        manifests: Callable[[], Mapping[str, Any]],
        state_path: str | Path,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        alert: Callable[[str, str], None] | None = None,
        config: Mapping[str, Any] | None = None,
        equity: Callable[[str], Any] | None = None,
        halted: Callable[[], bool] | None = None,
    ):
        self.log = log
        self.strategies = strategies
        self._sandboxes = sandboxes
        self.manifests = manifests
        self.state_path = Path(state_path)
        self.provider = provider
        self.clock = clock
        self._alert = alert
        self.config = {**DEFAULTS, **dict(config or {})}
        self.equity = equity
        #: True while the kill switch is engaged: a cycle that started before it keeps its
        #: backtests but moves nothing onto a live desk.
        self.halted = halted
        self._running = threading.Lock()
        self._state_lock = threading.RLock()

    # ------------------------------------------------------------------ handles
    def sandboxes(self) -> Any:
        handle = self._sandboxes
        if callable(handle) and not hasattr(handle, "run"):
            try:
                return handle()
            except Exception:
                return None
        return handle

    def store(self) -> Any:
        return self.strategies.store

    def now(self) -> str:
        return now_iso(self.clock)

    def alert(self, level: str, text: str) -> None:
        if self._alert is None:
            return
        try:
            self._alert(level, _clean(str(text))[:500])
        except Exception:
            pass

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True)) and self.strategies is not None and self.sandboxes() is not None

    def due(self, at: str, last: str | None) -> bool:
        if not last:
            return True
        return _epoch(at) - _epoch(last) >= float(self.config["interval_minutes"]) * 60.0

    def running(self) -> bool:
        return self._running.locked()

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: Mapping[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + f".tmp-{threading.get_ident()}")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.state_path)

    def _save(self, **updates: Any) -> dict[str, Any]:
        with self._state_lock:
            data = {**self.state(), **updates}
            self._write(data)
            return data

    def _deployment(self, fid: str | None, **fields: Any) -> None:
        if not fid:
            return
        with self._state_lock:
            data = self.state()
            deployments = dict(data.get("deployments") or {})
            if fid not in deployments:
                return
            deployments[fid] = {**deployments[fid], **fields}
            data["deployments"] = deployments
            self._write(data)

    def _add_deployment(self, record: Mapping[str, Any]) -> None:
        with self._state_lock:
            data = self.state()
            deployments = dict(data.get("deployments") or {})
            for fid, other in list(deployments.items()):
                if other.get("status") == "shadow" and other.get("desk_id") == record["desk_id"] and (
                    other.get("strategy") == record["strategy"] or (other.get("kind") == "code" and record["kind"] == "code")
                ):
                    deployments[fid] = {**other, "status": "replaced", "ended_at": record["deployed_at"]}
            deployments[record["id"]] = dict(record)
            # Bounded: every open deployment, and the newest sixty that ended.
            ended = sorted((d for d in deployments.values() if d.get("status") != "shadow"), key=lambda d: str(d.get("deployed_at")))
            for old in ended[:-60]:
                deployments.pop(old["id"], None)
            data["deployments"] = deployments
            self._write(data)

    def summary(self) -> dict[str, Any] | None:
        """The last cycle, for the health file."""
        last = self.state().get("last")
        if not isinstance(last, Mapping):
            return None
        keys = ("at", "cycle", "family", "strategy", "candidates", "backtested", "qualified", "best_oos_return", "winner", "deployed_to", "fast_tracked", "seconds", "sandbox_seconds", "model_cost_usd", "skipped", "failed")
        return {k: last.get(k) for k in keys if k in last}

    def _next_cycle(self, state: Mapping[str, Any]) -> int:
        known = _int(state.get("cycle"))
        if known is not None:
            return known + 1
        # A lost state file must not reuse a cycle number (names and event ids carry it).
        highest = 0
        reader = getattr(self.log, "read", None)
        if callable(reader):
            try:
                for event in reader(kind="lab.hypothesis", limit=500, newest=True):
                    match = re.match(r"^foundry-(\d+)$", str(event.payload.get("hypothesis_id") or ""))
                    if match:
                        highest = max(highest, int(match.group(1)))
            except Exception:
                highest = 0
        return highest + 1

    # ------------------------------------------------------------------ the family
    @staticmethod
    def live_desk(family: str, manifests: Mapping[str, Any]) -> Any:
        live = sorted((m for m in manifests.values() if m.family == family and m.live), key=lambda m: m.id)
        return live[0] if live else None

    @staticmethod
    def shadow_desks(family: str, manifests: Mapping[str, Any]) -> list[Any]:
        return sorted((m for m in manifests.values() if m.family == family and not m.live), key=lambda m: m.id)

    def subjects(self, family: str, manifests: Mapping[str, Any]) -> list[str]:
        """The family's house starter, then every other strategy its live desk runs."""
        names: list[str] = []
        house = STARTERS.get(family)
        if house and house not in UNBACKTESTABLE_STRATEGIES:
            names.append(house)
        live = self.live_desk(family, manifests)
        if live is not None:
            for name, row in sorted(self.store().for_desk(live.id).items()):
                if row.get("enabled", True) and name not in names and base_name(name) not in UNBACKTESTABLE_STRATEGIES:
                    names.append(name)
        return names

    def source_of(self, name: str, live: Any) -> str | None:
        """The code the live desk runs under `name`, else the house starter's file."""
        if not STRATEGY_NAME.match(str(name or "")):
            return None
        manager = self.sandboxes()
        if live is not None and manager is not None and hasattr(manager, "toolbox_files"):
            try:
                code = manager.toolbox_files(live.id).get(f"{name}.py")
            except Exception:
                code = None
            if code:
                return code
        path = STARTERS_DIR / f"{name}.py"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    @staticmethod
    def variants_for(family: str, name: str) -> list[Mapping[str, Any]]:
        root = base_name(name)
        if root == STARTERS.get(family):
            return list(STARTER_VARIANTS.get(family) or [])
        if root == SECOND_STARTERS.get(family):
            return list(QUOTE_VARIANTS.get(family) or [])
        return []

    def cadence_of(self, family: str, name: str, live: Any) -> int:
        row = self.store().for_desk(live.id).get(name) if live is not None else None
        return int((row or {}).get("cadence_seconds") or STARTER_CADENCE.get(base_name(name)) or STARTER_CADENCE.get(family) or 600)

    def _pick(self, manifests: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[str, str, int, dict[str, int]] | None:
        families = [f for f in (self.config.get("families") or []) if f not in UNBACKTESTABLE_FAMILIES]
        if not families:
            return None
        start = int(state.get("family_index") or 0) % len(families)
        subject_index = {str(k): int(v) for k, v in dict(state.get("subject_index") or {}).items()}
        for offset in range(len(families)):
            family = families[(start + offset) % len(families)]
            if not any(m.family == family for m in manifests.values()):
                continue
            names = self.subjects(family, manifests)
            if not names:
                continue
            index = subject_index.get(family, 0) % len(names)
            subject_index[family] = index + 1
            return family, names[index], (start + offset + 1) % len(families), subject_index
        return None

    def _record(self, desk_id: str, name: str, since: str | None) -> dict[str, Any]:
        try:
            return dict(self.strategies.record(desk_id, name, since=since) or {})
        except Exception:
            return {}

    def _equity(self, desk_id: str) -> Decimal | None:
        if self.equity is None:
            return None
        try:
            return _dec(self.equity(desk_id))
        except Exception:
            return None

    # ------------------------------------------------------------------ the cycle
    def cycle(self, at: str | None = None) -> dict[str, Any]:
        """One pass of the loop. Never raises; a cycle already running is not started again."""
        if not self._running.acquire(blocking=False):
            return {"skipped": "a foundry cycle is already running"}
        started = time.monotonic()
        at = at or self.now()
        try:
            summary = self._cycle(at)
        except Exception as exc:
            summary = {"at": at, "failed": f"{type(exc).__name__}: {str(exc)[:200]}"}
            self.alert("warning", f"foundry cycle failed: {type(exc).__name__}: {str(exc)[:160]}")
        finally:
            self._running.release()
        summary["seconds"] = round(time.monotonic() - started, 1)
        try:
            with self._state_lock:
                data = self.state()
                history = [row for row in (data.get("history") or []) if isinstance(row, Mapping)][-23:]
                data["last"] = {k: v for k, v in summary.items() if k != "candidates_detail"}
                data["history"] = history + [data["last"]]
                self._write(data)
        except Exception:
            pass
        return summary

    def _cycle(self, at: str) -> dict[str, Any]:
        cfg = self.config
        manager = self.sandboxes()
        if manager is None or self.strategies is None:
            return {"at": at, "skipped": "no sandboxes"}
        problems: list[str] = []
        manifests = dict(self.manifests() or {})
        state = self.state()
        cycle = self._next_cycle(state)
        fast = self.fast_track(manifests, problems)
        pick = self._pick(manifests, state)
        if pick is None:
            self._save(cycle=cycle)
            self._report_problems(cycle, problems)
            return {"at": at, "cycle": cycle, "skipped": "no backtestable family has desks", "fast_tracked": fast}
        family, subject, family_index, subject_index = pick
        self._save(cycle=cycle, family_index=family_index, subject_index=subject_index)
        live = self.live_desk(family, manifests)
        shadows = self.shadow_desks(family, manifests)
        parent = live or (shadows[0] if shadows else None)
        source = self.source_of(subject, live)
        summary: dict[str, Any] = {"at": at, "cycle": cycle, "family": family, "strategy": subject, "fast_tracked": fast}
        if source is None or parent is None:
            summary["skipped"] = f"no source for {subject}"
            self._report_problems(cycle, problems)
            return summary

        defaults = literal_defaults(source)
        frozen = [str(k) for k in (cfg.get("frozen_params") or [])]
        baselines, best_known, records = self.baselines(cycle, family, subject, source, live, shadows, defaults, frozen)
        variants = self.param_candidates(cycle, family, subject, source, defaults, best_known, baselines, frozen)
        cadence = self.cadence_of(family, subject, live)
        for candidate in baselines + variants:
            candidate["cadence_seconds"] = cadence
        end = math.floor(_epoch(at) / 3600.0) * 3600.0
        window = {
            "start": _iso(end - float(cfg["window_days"]) * 86400.0),
            "end": _iso(end),
            "step_minutes": int(dict(cfg.get("family_step_minutes") or {}).get(family, cfg["step_minutes"])),
        }
        summary["window"] = [window["start"], window["end"], window["step_minutes"]]

        workers = max(1, int(cfg["sandboxes"]))
        ids: "queue.Queue[str]" = queue.Queue()
        for index in range(workers):
            ids.put(f"foundry-{index}")
        code: list[dict[str, Any]] = []
        asked: dict[str, Any] = {"asked": 0, "valid": 0, "rejected": [], "skipped": None, "cost_usd": "0"}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="foundry") as pool:
            base_futures = [pool.submit(self._backtest, c, window, ids) for c in baselines]
            variant_futures = [pool.submit(self._backtest, c, window, ids) for c in variants]
            wait_futures(base_futures)
            unsupported = [c for c in baselines if (c.get("report") or {}).get("unsupported")]
            if baselines and len(unsupported) == len(baselines):
                for future in variant_futures:
                    future.cancel()
                reason = str((unsupported[0].get("report") or {}).get("unsupported"))[:200]
                asked["skipped"] = f"the engine cannot backtest {subject}: {reason}"
            else:
                code, asked = self.code_candidates(cycle, family, subject, source, parent, live, baselines, records, window, problems)
                for candidate in code:
                    pool.submit(self._backtest, candidate, window, ids)
        candidates = baselines + variants + code
        for candidate in candidates:
            if candidate.get("report") is None and not candidate.get("error"):
                candidate["error"] = "not run"

        qualified, reference = self.select(candidates)
        scored = [c for c in candidates if c["kind"] != "baseline" and c.get("evidence") and c["evidence"]["out_of_sample"]["return_on_notional"] is not None]
        best = max(scored, key=lambda c: c["evidence"]["out_of_sample"]["return_on_notional"], default=None)
        winner = qualified[0] if qualified else None
        deployment = None
        if winner is not None:
            deployment = self.deploy(winner, family, subject, shadows, problems)
        summary.update(
            {
                "candidates": len(variants) + len(code),
                "baselines": len(baselines),
                "backtested": sum(1 for c in candidates if c.get("evidence")),
                "failed_backtests": sum(1 for c in candidates if c.get("error")),
                "qualified": len(qualified),
                "reference_oos_return": reference,
                "best_oos_return": None if best is None else best["evidence"]["out_of_sample"].get("return_on_notional"),
                "best": None if best is None else best["id"],
                "winner": None if deployment is None else deployment["id"],
                "deployed_to": None if deployment is None else deployment["desk_id"],
                "code": {k: asked.get(k) for k in ("asked", "valid", "rejected", "skipped")},
                "model_cost_usd": asked.get("cost_usd"),
                "sandbox_seconds": round(sum(_float(c.get("seconds")) or 0.0 for c in candidates), 1),
                "candidates_detail": candidates,
            }
        )
        if winner is not None and deployment is None:
            summary["undeployed"] = winner["id"]
        self.publish_cycle(summary, window, reference, winner, deployment)
        self._report_problems(cycle, problems)
        summary["problems"] = problems[:6]
        return summary

    def _report_problems(self, cycle: int, problems: list[str]) -> None:
        if problems:
            self.alert("warning", f"foundry cycle {cycle}: " + "; ".join(p[:160] for p in problems[:3]))

    # ------------------------------------------------------------------ candidates
    def _candidate(self, cycle: int, kind: str, label: str, strategy: str, subject: str, params: Mapping[str, Any], code: str, **extra: Any) -> dict[str, Any]:
        material = json.dumps({"strategy": strategy, "params": params, "code": _sha(code), "kind": kind}, sort_keys=True, default=str)
        return {
            "id": f"fdy-{cycle}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:8]}",
            "kind": kind,
            "label": label,
            "strategy": strategy,
            "subject": subject,
            "params": dict(params),
            "code": code,
            "report": None,
            "evidence": None,
            "error": None,
            "seconds": 0.0,
            **extra,
        }

    def baselines(
        self, cycle: int, family: str, subject: str, source: str, live: Any, shadows: list[Any], defaults: Mapping[str, Any], frozen: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        """The live desk's settings and the best shadow's, the best-known settings between them
        (by forward record), and the family's forward record as lines for the model."""
        store = self.store()
        records: list[str] = []
        live_row = store.for_desk(live.id).get(subject) if live is not None else None
        live_params = {k: v for k, v in dict((live_row or {}).get("params") or {}).items() if k not in frozen}
        live_ron = None
        out = [self._candidate(cycle, "baseline", f"live {live.id}" if live is not None else "house defaults", subject, subject, live_params, source)]
        scored: list[tuple[tuple[int, Decimal, Decimal], str, dict[str, Any]]] = []
        for desk in ([live] if live is not None else []) + list(shadows):
            for name, row in sorted(store.for_desk(desk.id).items()):
                if not row.get("enabled", True):
                    continue
                record = self._record(desk.id, name, row.get("promoted_at") or row.get("deployed_at"))
                ron = _return_on_notional(record) if record else None
                settled = int(record.get("settled") or 0)
                if len(records) < 24:
                    records.append(
                        f"- {desk.id}{' (live)' if desk.live else ''}/{name}: params {json.dumps(row.get('params') or {}, sort_keys=True)[:300]}, "
                        f"{record.get('fills', 0)} fills, {settled} settled, {record.get('wins', 0)} won, "
                        f"P&L {record.get('settled_pnl_usd', '0')}, fees {record.get('fees_usd', '0')}, return per $ {ron if ron is not None else 'n/a'}"
                    )
                if name != subject:
                    continue
                if desk is live:
                    live_ron = ron if settled else None
                    continue
                pnl = _dec(record.get("settled_pnl_usd")) or Decimal(0)
                scored.append(((1 if settled and ron is not None else 0, ron or Decimal(0), pnl), desk.id, row))
        best_known = dict(live_params)
        best_known_from = "live"
        if scored:
            scored.sort(key=lambda s: (-s[0][0], -s[0][1], -s[0][2], s[1]))
            (evidence, ron, _), desk_id, row = scored[0]
            params = {k: v for k, v in dict(row.get("params") or {}).items() if k not in frozen}
            if _full(params, defaults) != _full(live_params, defaults):
                out.append(self._candidate(cycle, "baseline", f"shadow {desk_id}", subject, subject, params, source))
            if evidence and (live_ron is None or ron > live_ron):
                best_known, best_known_from = params, f"shadow {desk_id}"
        for candidate in out:
            candidate["best_known"] = best_known_from
        return out, best_known, records

    def param_candidates(
        self, cycle: int, family: str, subject: str, source: str, defaults: Mapping[str, Any], best_known: Mapping[str, Any], baselines: list[dict[str, Any]], frozen: list[str]
    ) -> list[dict[str, Any]]:
        cfg = self.config
        full = {k: v for k, v in _full(best_known, defaults).items() if k not in frozen}
        pool = categorical_pool(self.variants_for(family, subject), defaults)
        drawn = jitter_variants(
            full,
            seed=f"foundry:{cycle}:{family}:{subject}",
            count=int(cfg["param_candidates"]),
            low=float(cfg["jitter_min"]),
            high=float(cfg["jitter_max"]),
            frozen=frozen,
            pool=pool,
            exclude=[{k: v for k, v in _full(b["params"], defaults).items() if k not in frozen} for b in baselines],
        )
        keep = set(best_known)
        out = []
        for params, how in drawn:
            label = f"settings +-{int(how['scale'] * 100)}%" + (f", {how['flip']} flipped" if how.get("flip") else "")
            out.append(self._candidate(cycle, "params", label, subject, subject, _compact(params, defaults, keep), source))
        return out

    def instructions(self, name: str) -> str:
        cfg = self.config
        return (
            "You are the Foundry of a public, fully automated trading floor: a research loop that runs every half hour, "
            "mutates a strategy's code, backtests every mutation on the last days of real Kalshi and Coinbase history, "
            "deploys the out-of-sample winner to a shadow desk and moves it to real money when its forward record holds.\n"
            "Write ONE mutation of the strategy below that you expect to earn more per dollar out of sample. Change how it "
            "trades (pricing, selection, entries, exits, market filters), not only its settings; keep what already works.\n"
            "Rules: a Python module defining decide(kit, params); standard library only; no files, processes, sockets or "
            "network (the kit is the only door to data; subprocess, os.system, socket, urllib, requests, open( and __import__ "
            f"are refused); at most {int(cfg['code_chars'])} characters. It runs under the strategy name `{name}`: where it "
            f"recognises its own resting orders by kit.context['open_orders'][i]['strategy'], compare with '{name}'. Size from "
            "params.get('notional_usd') or kit.context['learning_usd']; the floor caps size in any case. The backtest replays "
            "kit.kalshi_markets, kit.kalshi_series, kit.kalshi_market, kit.bars, kit.quote and kit.products from history at "
            "each step; kit.weather is not available.\n"
            f"The kit: {KIT_API}\n"
            "Kalshi charges takers ceil(0.07 * p * (1 - p) * 100) / 100 dollars a contract; makers pay nothing. Coinbase "
            "charges 0.25% maker and 0.60% taker.\n"
            f"How it is judged: the closed positions are split in time; on the last third it needs at least "
            f"{int(cfg['min_oos_trades'])} positions ({int(cfg['min_trades'])} trades in all), a return on notional above the "
            f"best baseline's by {cfg['margin']}, and a 95% confidence lower bound on mean P&L per position above "
            f"{cfg['min_ci_lower']}. Fitting the in-sample period does not help.\n"
            f"Reply with JSON only: {{\"name\": \"{name}\", \"code\": \"<the whole module>\", \"params\": {{...}}, "
            "\"hypothesis\": \"one sentence: what you changed and why it should earn more out of sample\"}. params holds "
            "overrides of the module's DEFAULTS as plain strings, numbers, booleans or lists (no null, no nested objects)."
        )

    def packet(
        self, *, family: str, subject: str, name: str, source: str, window: Mapping[str, Any], baselines: list[dict[str, Any]], records: list[str], index: int, count: int
    ) -> str:
        parts = [
            f"# Family {family}, strategy `{subject}`; your mutation is `{name}` (candidate {index + 1} of {count})",
            f"Backtest window {window['start']} to {window['end']}, a decision every {window['step_minutes']} minutes.",
            f"Explore {DIRECTIONS[index % len(DIRECTIONS)]}.",
            "## Baseline backtests (the settings the family trades today)",
        ]
        for candidate in baselines:
            parts.append(self._report_line(candidate))
        parts.append("## Forward record since each setting was dealt (real prices; shadow desks are scored, live desks trade money)")
        parts.append("\n".join(records) if records else "(no strategy records yet)")
        clipped = source[:16000]
        parts.append(f"## Source of `{subject}` ({len(source)} characters{', clipped' if len(source) > len(clipped) else ''})\n```python\n{clipped}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _report_line(candidate: Mapping[str, Any]) -> str:
        report = candidate.get("report") or {}
        evidence = candidate.get("evidence") or {}
        ins, oos = evidence.get("in_sample") or {}, evidence.get("out_of_sample") or {}
        line = (
            f"- {candidate.get('label')} params {json.dumps(candidate.get('params') or {}, sort_keys=True)[:400]}: "
            f"{report.get('trades')} trades, {report.get('settled')} settled, {report.get('wins')} won, P&L {report.get('pnl_usd')} "
            f"after {report.get('fees_usd')} fees on {report.get('notional_usd')} notional, max drawdown {report.get('max_drawdown_usd')}; "
            f"in sample {ins.get('trades')} positions, return {ins.get('return_on_notional')}, CI {ins.get('ci95_mean_pnl')}; "
            f"out of sample {oos.get('trades')} positions, return {oos.get('return_on_notional')}, CI {oos.get('ci95_mean_pnl')}"
        )
        if report.get("unsupported"):
            line += f"; unsupported: {str(report['unsupported'])[:200]}"
        if candidate.get("error") and not report:
            line += f"; failed: {str(candidate['error'])[:200]}"
        notes = [str(n)[:160] for n in (report.get("notes") or [])[:3]]
        return line + (f"; notes: {' | '.join(notes)}" if notes else "")

    def code_candidates(
        self,
        cycle: int,
        family: str,
        subject: str,
        source: str,
        parent: Any,
        live: Any,
        baselines: list[dict[str, Any]],
        records: list[str],
        window: Mapping[str, Any],
        problems: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Ask the model for `code_candidates` mutations, validated before any backtest."""
        cfg = self.config
        count = max(0, int(cfg["code_candidates"]))
        asked: dict[str, Any] = {"asked": 0, "valid": 0, "rejected": [], "skipped": None, "cost_usd": "0"}
        if count == 0:
            return [], asked
        if self.provider is None:
            asked["skipped"] = "no model provider"
            return [], asked
        budget = _dec(cfg["budget_usd_per_day"]) or Decimal(0)
        try:
            spent = _dec(self.provider.spent_today(BUDGET_DESK)) or Decimal(0)
        except Exception:
            spent = Decimal(0)
        if spent >= budget:
            asked["skipped"] = f"model budget used: {spent} of {budget} today"
            return [], asked
        root = base_name(subject)[: 40 - len(f"_f{cycle}_{count}")]
        cadence = self.cadence_of(family, subject, live)
        names = [f"{root}_f{cycle}" if k == 0 else f"{root}_f{cycle}_{k + 1}" for k in range(count)]

        def ask(index: int) -> tuple[int, Any, str | None]:
            name = names[index]
            try:
                response = self.provider.respond(
                    cfg["profile"],
                    [
                        {"role": "system", "content": self.instructions(name)},
                        {"role": "user", "content": self.packet(family=family, subject=subject, name=name, source=source, window=window, baselines=baselines, records=records, index=index, count=count)},
                    ],
                    tools=None,
                    desk_id=BUDGET_DESK,
                    session_id=f"foundry-{cycle}",
                    request_key=f"foundry:{cycle}:{subject}:{index}",
                    reasoning_effort=cfg["reasoning_effort"],
                    max_output_tokens=int(cfg["max_output_tokens"]),
                    desk_cap_usd_per_day=cfg["budget_usd_per_day"],
                )
            except Exception as exc:
                return index, None, f"{type(exc).__name__}: {str(exc)[:160]}"
            return index, response, None

        with ThreadPoolExecutor(max_workers=count, thread_name_prefix="foundry-model") as pool:
            answers = list(pool.map(ask, range(count)))
        out: list[dict[str, Any]] = []
        cost = Decimal(0)
        for index, response, failure in sorted(answers, key=lambda a: a[0]):
            asked["asked"] += 1
            name = names[index]
            if failure is not None:
                if "Budget" in failure:
                    asked["skipped"] = f"model budget: {failure[:120]}"
                else:
                    problems.append(f"model call for {name} failed: {failure}")
                    asked["rejected"].append(f"{name}: no answer")
                continue
            cost += _dec(getattr(response, "cost_usd", None)) or Decimal(0)
            try:
                spec, hypothesis = self.validate_code(parse_reply(getattr(response, "output_text", "") or ""), name, parent, cadence)
            except LabError as exc:
                asked["rejected"].append(f"{name}: {str(exc)[:160]}")
                continue
            asked["valid"] += 1
            out.append(
                self._candidate(cycle, "code", f"model mutation {index + 1}", name, subject, spec["params"], spec["code"], hypothesis=hypothesis, cadence_seconds=spec["cadence_seconds"])
            )
        asked["cost_usd"] = format(cost, "f")
        return out, asked

    def validate_code(self, data: Any, name: str, parent: Any, cadence: int) -> tuple[dict[str, Any], str]:
        """The lab's own strategy validation, and a compile, before a single backtest."""
        if not isinstance(data, Mapping):
            raise LabError("the reply is not a JSON object")
        hypothesis = str(data.get("hypothesis") or "").strip()
        if not hypothesis:
            raise LabError("the reply has no hypothesis")
        frozen = set(str(k) for k in (self.config.get("frozen_params") or []))
        params = data.get("params") if data.get("params") is not None else {}
        if not isinstance(params, Mapping):
            raise LabError("params must be an object")
        params = {k: v for k, v in params.items() if v is not None and k not in frozen}
        change = {"strategy": {"name": name, "cadence_seconds": cadence, "params": params, "code": data.get("code")}}
        spec = validate_change(change, parent, {"strategy_code_chars": int(self.config["code_chars"])})["strategy"]
        try:
            compile(spec["code"], f"{name}.py", "exec")
        except (SyntaxError, ValueError) as exc:
            raise LabError(f"the code does not compile: {str(exc)[:120]}") from None
        return spec, hypothesis[:300]

    # ------------------------------------------------------------------ backtests
    def spec_for(self, candidate: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
        cfg = self.config
        return {
            "strategy": candidate["strategy"],
            "code": candidate["code"],
            "params": dict(candidate.get("params") or {}),
            "start": window["start"],
            "end": window["end"],
            "step_minutes": int(window["step_minutes"]),
            "learning_usd": cfg["learning_usd"],
            "fill_model": cfg["fill_model"],
            "max_markets": int(cfg["max_markets"]),
            "seed": int(cfg["seed"]),
        }

    def _backtest(self, candidate: dict[str, Any], window: Mapping[str, Any], ids: "queue.Queue[str]") -> dict[str, Any]:
        """One backtest in one free sandbox. Fills in the candidate's report and evidence."""
        desk = ids.get()
        try:
            manager = self.sandboxes()
            code = runner_code(self.spec_for(candidate, window), fraction=float(self.config["split_fraction"]))
            run = manager.run(desk, code, purpose=f"foundry backtest {candidate['id']} ({candidate['strategy']})", timeout=int(self.config["backtest_timeout_seconds"]))
            candidate["sandbox"] = desk
            candidate["seconds"] = _float(getattr(run, "seconds", 0)) or 0.0
            report = parse_result(getattr(run, "stdout", ""))
            if report is None:
                candidate["error"] = f"exit {getattr(run, 'exit_code', '?')}: no result line ({str(getattr(run, 'stdout', ''))[-160:]})"
                return candidate
            candidate["report"] = report
            candidate["evidence"] = self.evidence(report)
            if report.get("unsupported"):
                candidate["error"] = f"unsupported: {str(report['unsupported'])[:200]}"
        except Exception as exc:
            candidate["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        finally:
            ids.put(desk)
        return candidate

    def evidence(self, report: Mapping[str, Any]) -> dict[str, Any]:
        """Total trades and the in-sample and out-of-sample halves, as plain numbers."""
        split = report.get("split")
        if not (isinstance(split, Mapping) and isinstance(split.get("out_of_sample"), Mapping)):
            split = split_evidence(report.get("trade_pnls") or [], report.get("notional_usd"), float(self.config["split_fraction"]))

        def plain(part: Any) -> dict[str, Any]:
            part = part if isinstance(part, Mapping) else {}
            ci = part.get("ci95_mean_pnl")
            bounds = [_float(ci[0]), _float(ci[1])] if isinstance(ci, (list, tuple)) and len(ci) == 2 else None
            if bounds is not None and None in bounds:
                bounds = None
            return {"trades": _int(part.get("trades")) or 0, "pnl_usd": _float(part.get("pnl_usd")), "return_on_notional": _float(part.get("return_on_notional")), "ci95_mean_pnl": bounds}

        total = _int(report.get("trades"))
        if total is None:
            total = len(report.get("trade_pnls") or []) or (_int(report.get("trade_pnls_dropped")) or 0)
        return {"trades": total, "in_sample": plain(split.get("in_sample")), "out_of_sample": plain(split.get("out_of_sample"))}

    # ------------------------------------------------------------------ selection
    def select(self, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        """The candidates that qualify on out-of-sample evidence, best first, and the baseline
        return they had to beat. In-sample numbers are never read here."""
        references = []
        measured = False
        for candidate in candidates:
            if candidate["kind"] != "baseline" or not candidate.get("evidence") or candidate.get("error"):
                continue
            measured = True
            oos = candidate["evidence"]["out_of_sample"]
            if oos["trades"] > 0 and oos["return_on_notional"] is not None:
                references.append(oos["return_on_notional"])
        # A baseline that did not trade in the window sets the bar at zero; a baseline that could
        # not be measured at all sets no bar, and nothing qualifies against it.
        reference = max(references) if references else 0.0
        qualified = []
        for candidate in candidates:
            if candidate["kind"] == "baseline":
                continue
            ok, verdict = self.qualifies(candidate, reference) if measured else (False, "no baseline was measured to beat")
            candidate["verdict"] = verdict
            if ok:
                qualified.append(candidate)
        qualified.sort(key=lambda c: (-c["evidence"]["out_of_sample"]["return_on_notional"], -c["evidence"]["out_of_sample"]["ci95_mean_pnl"][0], c["id"]))
        return qualified, reference

    def qualifies(self, candidate: Mapping[str, Any], reference: float) -> tuple[bool, str]:
        cfg = self.config
        if candidate.get("error"):
            return False, str(candidate["error"])[:200]
        evidence = candidate.get("evidence")
        if not evidence:
            return False, "no backtest evidence"
        oos = evidence["out_of_sample"]
        if int(evidence["trades"]) < int(cfg["min_trades"]):
            return False, f"{evidence['trades']} trades, {cfg['min_trades']} needed"
        if int(oos["trades"]) < int(cfg["min_oos_trades"]):
            return False, f"{oos['trades']} out-of-sample positions, {cfg['min_oos_trades']} needed"
        ron = oos["return_on_notional"]
        if ron is None or ron <= reference + float(cfg["margin"]):
            return False, f"out-of-sample return {_fmt(ron)} does not beat {reference:+.3f} by {cfg['margin']}"
        ci = oos["ci95_mean_pnl"]
        if ci is None or ci[0] <= float(cfg["min_ci_lower"]):
            return False, f"out-of-sample 95% lower bound {_fmt(ci[0] if ci else None, '+.4f')} is not above {cfg['min_ci_lower']}"
        return True, "qualified"

    # ------------------------------------------------------------------ shadow deployment
    def target_desk(self, winner: Mapping[str, Any], shadows: list[Any], at: str) -> Any:
        """The family's worst-performing shadow desk that can take the winner: lowest settled
        strategy P&L, then lowest equity. A desk still proving an earlier candidate is spared."""
        store = self.store()
        deployments = dict(self.state().get("deployments") or {})
        protect = float(self.config["protect_hours"]) * 3600.0
        now = _epoch(at)
        protected = {
            d.get("desk_id") for d in deployments.values()
            if d.get("status") == "shadow" and now - _epoch(d.get("deployed_at")) < protect
        }
        rows = {m.id: store.for_desk(m.id) for m in shadows if not m.live}
        pool = [m for m in shadows if not m.live and m.id not in protected]
        name = winner["strategy"]
        if winner["kind"] == "params":
            pool = [m for m in pool if name in rows[m.id] and rows[m.id][name].get("enabled", True)]
            sha = _sha(winner.get("code"))
            same = [m for m in pool if rows[m.id][name].get("code_sha256") == sha]
            pool = same or pool
        else:
            limit = int(dict(getattr(self.strategies, "config", {}) or {}).get("max_per_desk", 3))
            pool = [
                m for m in pool
                if sum(1 for r in rows[m.id].values() if not r.get("foundry_code")) < limit
                # Never over a desk's own strategy of the same name (a house starter, say).
                and (name not in rows[m.id] or rows[m.id][name].get("foundry_code"))
            ]
        if not pool:
            return None

        def score(desk: Any) -> tuple[Decimal, Decimal, str]:
            pnl = Decimal(0)
            for strategy, row in rows[desk.id].items():
                if row.get("enabled", True):
                    record = self._record(desk.id, strategy, row.get("promoted_at") or row.get("deployed_at"))
                    pnl += _dec(record.get("settled_pnl_usd")) or Decimal(0)
            equity = self._equity(desk.id)
            return pnl, equity if equity is not None else Decimal("Infinity"), desk.id

        return min(pool, key=score)

    def deploy(self, winner: dict[str, Any], family: str, subject: str, shadows: list[Any], problems: list[str]) -> dict[str, Any] | None:
        """Put the winner on a shadow desk now. Never a live desk."""
        at = self.now()
        desk = self.target_desk(winner, shadows, at)
        if desk is None and winner["kind"] == "params":
            # No shadow desk runs this strategy (a live desk's own, or an adopted candidate): the
            # settings go out with the live desk's code, installed on the worst shadow desk.
            carried = {**winner, "kind": "code"}
            desk = self.target_desk(carried, shadows, at)
            winner = carried if desk is not None else winner
        if desk is None:
            problems.append(f"{winner['id']} qualified but no shadow desk of {family} can take it")
            return None
        if desk.live:  # belt and braces: the target list never holds a live desk
            return None
        store = self.store()
        manager = self.sandboxes()
        frozen = [str(k) for k in (self.config.get("frozen_params") or [])]
        fid, name = winner["id"], winner["strategy"]
        oos = winner["evidence"]["out_of_sample"]
        note = f"foundry {fid}: out-of-sample {oos['trades']} positions, {_fmt(oos['return_on_notional'])} per $"
        try:
            if winner["kind"] == "params":
                own = dict((store.for_desk(desk.id).get(name) or {}).get("params") or {})
                params = {**{k: v for k, v in winner["params"].items() if k not in frozen}, **{k: own[k] for k in frozen if k in own}}
                store.update(desk.id, name, params=params, promoted_at=at, note=note[:200], foundry_id=fid)
                code_sha = (store.for_desk(desk.id).get(name) or {}).get("code_sha256") or _sha(winner.get("code"))
            else:
                params = dict(winner["params"])
                existed = name in store.for_desk(desk.id)
                for other, row in list(store.for_desk(desk.id).items()):
                    if row.get("foundry_code") and other != name:
                        store.remove(desk.id, other)
                        self._remove_file(manager, desk.id, other)
                        self._deployment(row.get("foundry_id"), status="replaced", ended_at=at)
                try:
                    self.strategies.install(
                        desk,
                        {"name": name, "code": winner["code"], "cadence_seconds": int(winner.get("cadence_seconds") or 600), "params": params},
                        note=f"foundry {fid}",
                    )
                except Exception:
                    if not existed:
                        self._remove_file(manager, desk.id, name)
                    raise
                store.update(desk.id, name, foundry_id=fid, foundry_code=True, promoted_at=at)
                code_sha = _sha(winner["code"])
        except Exception as exc:
            problems.append(f"{fid} not deployed to {desk.id}: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        record = {
            "id": fid,
            "family": family,
            "subject": subject,
            "strategy": name,
            "kind": winner["kind"],
            "desk_id": desk.id,
            "deployed_at": at,
            "status": "shadow",
            "params": params,
            "code_sha256": code_sha,
            "cadence_seconds": int(winner.get("cadence_seconds") or 0) or None,
            "trades": winner["evidence"]["trades"],
            "oos_trades": oos["trades"],
            "oos_return": oos["return_on_notional"],
            "oos_ci_lower": oos["ci95_mean_pnl"][0],
            "hypothesis": winner.get("hypothesis"),
        }
        self._add_deployment(record)
        lines = [
            f"foundry {fid} ({winner['label']}) deployed to shadow desk {desk.id} as {name}",
            f"backtest: {winner['evidence']['trades']} trades; out of sample {oos['trades']} positions, return {_fmt(oos['return_on_notional'])} per $, "
            f"95% CI on mean P&L [{_fmt(oos['ci95_mean_pnl'][0], '+.4f')}, {_fmt(oos['ci95_mean_pnl'][1], '+.4f')}]",
            f"params: {json.dumps(params, sort_keys=True)[:800]}",
        ]
        if winner.get("hypothesis"):
            lines.append(f"hypothesis: {winner['hypothesis']}")
        lines.append(f"live after {self.config['min_forward_settled']} settled positions here at P&L >= 0")
        self.publish_desk(desk, name, f"foundry-{fid}-shadow", at, f"foundry {fid}: {name} on shadow desk {desk.id}", lines, code_sha, winner.get("seconds"))
        return record

    @staticmethod
    def _remove_file(manager: Any, desk_id: str, name: str) -> None:
        remover = getattr(manager, "toolbox_remove", None)
        if callable(remover) and FOUNDRY_NAME.search(str(name)):
            try:
                remover(desk_id, name)
            except Exception:
                pass

    # ------------------------------------------------------------------ fast-track to live
    def fast_track(self, manifests: Mapping[str, Any], problems: list[str]) -> list[dict[str, Any]]:
        """Move every deployed candidate that has earned it onto its family's live desk."""
        cfg = self.config
        store = self.store()
        manager = self.sandboxes()
        frozen = [str(k) for k in (cfg.get("frozen_params") or [])]
        adopted: list[dict[str, Any]] = []
        if self.halted is not None:
            try:
                if self.halted():
                    return adopted
            except Exception:
                return adopted
        for fid, dep in sorted(dict(self.state().get("deployments") or {}).items()):
            if dep.get("status") != "shadow":
                continue
            at = self.now()
            desk = manifests.get(dep.get("desk_id"))
            name = str(dep.get("strategy") or "")
            if desk is None or desk.live:
                self._deployment(fid, status="gone", ended_at=at)
                continue
            row = store.for_desk(desk.id).get(name)
            if not row or not row.get("enabled", True) or row.get("foundry_id") != fid:
                self._deployment(fid, status="superseded", ended_at=at)
                continue
            if dep.get("kind") == "params" and dict(row.get("params") or {}) != dict(dep.get("params") or {}):
                self._deployment(fid, status="superseded", ended_at=at)
                continue
            lower = _float(dep.get("oos_ci_lower"))
            if lower is None or lower <= 0 or int(dep.get("oos_trades") or 0) < int(cfg["min_oos_trades"]):
                continue  # a candidate may trade in shadow, but only a confident backtest goes live
            record = self._record(desk.id, name, dep.get("deployed_at"))
            settled = int(record.get("settled") or 0)
            pnl = _dec(record.get("settled_pnl_usd")) or Decimal(0)
            if settled < int(cfg["min_forward_settled"]) or pnl < 0:
                if _epoch(at) - _epoch(dep.get("deployed_at")) > float(cfg["forward_max_hours"]) * 3600.0:
                    self._deployment(fid, status="expired", ended_at=at, forward={"settled": settled, "pnl_usd": format(pnl, "f")})
                continue
            live = self.live_desk(str(dep.get("family")), manifests)
            if live is None or not live.live:
                continue
            try:
                result = self._adopt(dep, desk, live, name, record, at, store, manager, frozen)
            except Exception as exc:
                attempts = int(dep.get("attempts") or 0) + 1
                # Three refusals (a full live desk, a dry run that fails) and it stays in shadow.
                self._deployment(fid, attempts=attempts, **({"status": "failed", "ended_at": at} if attempts >= 3 else {}))
                problems.append(f"{fid} not adopted by {live.id}: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            if result is not None:
                adopted.append(result)
        return adopted

    def _adopt(self, dep: Mapping[str, Any], desk: Any, live: Any, name: str, record: Mapping[str, Any], at: str, store: Any, manager: Any, frozen: list[str]) -> dict[str, Any] | None:
        fid = str(dep["id"])
        live_rows = store.for_desk(live.id)
        subject = str(dep.get("subject") or name)
        settled, pnl = record.get("settled"), record.get("settled_pnl_usd")
        note = f"foundry {fid} from {desk.id}: {settled} settled at {pnl} since {str(dep.get('deployed_at'))[:16]}"
        if dep.get("kind") == "params":
            own = live_rows.get(name)
            if not own or not own.get("enabled", True):
                # The live desk does not run this strategy: the settings have nowhere to go.
                self._deployment(fid, status="unadoptable", ended_at=at)
                return None
            mine = dict(own.get("params") or {})
            params = {**{k: v for k, v in dict(dep.get("params") or {}).items() if k not in frozen}, **{k: mine[k] for k in frozen if k in mine}}
            store.update(live.id, name, params=params, promoted_at=at, promoted_from=desk.id, foundry_id=fid, note=note[:200])
            code_sha = own.get("code_sha256")
        else:
            code = (manager.toolbox_files(desk.id) if manager is not None and hasattr(manager, "toolbox_files") else {}).get(f"{name}.py")
            if code is None or _sha(code) != dep.get("code_sha256"):
                self._deployment(fid, status="superseded", ended_at=at)
                return None
            parent = live_rows.get(subject)
            mine = dict((parent or {}).get("params") or {})
            params = {**{k: v for k, v in dict(dep.get("params") or {}).items() if k not in frozen}, **{k: mine[k] for k in frozen if k in mine}}
            for other, row in list(live_rows.items()):
                if row.get("foundry_code") and not row.get("enabled", True) and other not in (name, subject):
                    store.remove(live.id, other)
                    self._remove_file(manager, live.id, other)
            limit = int(dict(getattr(self.strategies, "config", {}) or {}).get("max_per_desk", 3))
            current = store.for_desk(live.id)
            set_aside = None
            if name not in current and len(current) >= limit and parent is not None and parent.get("foundry_code") and subject != name:
                # A full live desk: the foundry strategy this one replaces makes the room, and is
                # put back exactly as it was if the new code's dry run refuses.
                set_aside = (dict(current[subject]), (manager.toolbox_files(live.id) or {}).get(f"{subject}.py"))
                store.remove(live.id, subject)
            try:
                self.strategies.install(
                    live,
                    {"name": name, "code": code, "cadence_seconds": int(dep.get("cadence_seconds") or (parent or {}).get("cadence_seconds") or 600), "params": params},
                    note=f"foundry {fid}",
                )
            except Exception:
                if name not in current:
                    self._remove_file(manager, live.id, name)
                if set_aside is not None:
                    store.update(live.id, subject, **set_aside[0])
                raise
            if set_aside is not None:
                self._remove_file(manager, live.id, subject)
                parent = None
            marks = {"foundry_code": True} if name not in current else {}
            store.update(live.id, name, foundry_id=fid, promoted_at=at, promoted_from=desk.id, note=note[:200], **marks)
            if parent is not None and subject != name:
                # The mutation replaces the code it came from; running both would double the exposure.
                store.update(live.id, subject, enabled=False, note=f"replaced by foundry {fid} ({name})"[:200])
            code_sha = _sha(code)
        self._deployment(fid, status="live", live_desk_id=live.id, promoted_at=at, forward={"settled": settled, "pnl_usd": pnl})
        lines = [
            f"foundry {fid}: {name} adopted by live desk {live.id} from shadow desk {desk.id}",
            f"backtest out of sample: {dep.get('oos_trades')} positions, return {_fmt(dep.get('oos_return'))} per $, 95% lower bound {_fmt(dep.get('oos_ci_lower'), '+.4f')}",
            f"forward on {desk.id} since {dep.get('deployed_at')}: {settled} settled, P&L {pnl}",
            f"params: {json.dumps(params, sort_keys=True)[:800]}",
            "sizes, limits and capital unchanged; evidence resets at this promotion",
        ]
        if dep.get("kind") == "code" and subject != name:
            lines.append(f"{subject} paused on {live.id}")
        self.publish_desk(live, name, f"foundry-{fid}-live", at, f"foundry {fid}: {name} takes live desk {live.id}", lines, code_sha, 0)
        self.alert("info", f"foundry: {live.id}/{name} adopts {fid} from {desk.id} ({settled} settled at {pnl}; backtest out-of-sample {_fmt(dep.get('oos_return'))} per $)")
        return {"id": fid, "live_desk_id": live.id, "from": desk.id, "strategy": name, "kind": dep.get("kind")}

    # ------------------------------------------------------------------ publication
    def publish_desk(self, manifest: Any, name: str, suffix: str, at: str, purpose: str, lines: list[str], code_sha: str | None, seconds: Any) -> None:
        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        payload = {
            "session_id": f"{manifest.id}:{stamp}:strategy:{name}",
            "code_sha256": str(code_sha or "")[:64] or "0" * 64,
            "language": "python",
            "stdout": _clean("\n".join(lines))[:2400],
            "exit_code": 0,
            "seconds": f"{_float(seconds) or 0.0:.1f}",
            "sandbox": None,
            "purpose": _clean(purpose)[:200],
        }
        try:
            self.log.append(manifest.stream, "desk.code_run", payload, id=f"{suffix}:{at}"[:200], at=at)
        except Exception as exc:
            self.alert("warning", f"foundry run not published: {type(exc).__name__}")

    def publish_cycle(self, summary: Mapping[str, Any], window: Mapping[str, Any], reference: float, winner: Mapping[str, Any] | None, deployment: Mapping[str, Any] | None) -> None:
        cfg = self.config
        candidates = list(summary.get("candidates_detail") or [])
        family, subject, cycle = summary.get("family"), summary.get("strategy"), summary.get("cycle")
        params_n = sum(1 for c in candidates if c["kind"] == "params")
        code_n = sum(1 for c in candidates if c["kind"] == "code")
        best = summary.get("best_oos_return")
        if deployment is not None and winner is not None:
            outcome = f"winner {deployment['id']} ({winner['label']}) deployed to shadow desk {deployment['desk_id']}"
        elif winner is not None:
            outcome = f"winner {winner['id']} qualified but found no shadow desk"
        else:
            outcome = "no winner"
        text = (
            f"Foundry cycle {cycle}: {params_n + code_n} candidates for {family}/{subject} "
            f"({params_n} settings, {code_n} code) against {summary.get('baselines')} baselines; "
            f"best out-of-sample return {_fmt(best)} per $; {outcome}."
        )
        plan = (
            f"Backtest {window['start']} to {window['end']} every {window['step_minutes']} min, one sandbox per run. "
            f"Qualify on the last {round((1 - float(cfg['split_fraction'])) * 100)}% of positions: >= {cfg['min_oos_trades']} positions, "
            f">= {cfg['min_trades']} trades, return above the best baseline {reference:+.3f} by {cfg['margin']}, 95% lower bound on "
            f"mean P&L above {cfg['min_ci_lower']}. The best goes to the worst shadow desk; live after {cfg['min_forward_settled']} "
            "settled positions there at P&L >= 0."
        )
        top = sorted(
            (c for c in candidates if c.get("evidence")),
            key=lambda c: -(c["evidence"]["out_of_sample"]["return_on_notional"] if c["evidence"]["out_of_sample"]["return_on_notional"] is not None else -1e9),
        )
        rows = []
        for c in top[:6]:
            oos = c["evidence"]["out_of_sample"]
            rows.append({
                "id": c["id"], "kind": c["kind"], "label": str(c["label"])[:60], "trades": c["evidence"]["trades"],
                "oos_trades": oos["trades"], "oos_return": None if oos["return_on_notional"] is None else _fmt(oos["return_on_notional"], "+.4f"),
                "oos_ci_lower": None if not oos["ci95_mean_pnl"] else _fmt(oos["ci95_mean_pnl"][0], "+.4f"), "verdict": str(c.get("verdict") or "baseline")[:100],
            })
        code = dict(summary.get("code") or {})
        payload: dict[str, Any] = {
            "hypothesis_id": f"foundry-{cycle}",
            "text": text,
            "test_plan": plan,
            "family": family,
            "strategy": subject,
            "cycle": cycle,
            "candidates": params_n + code_n,
            "backtested": summary.get("backtested"),
            "qualified": summary.get("qualified"),
            "baseline_oos_return": _fmt(reference, "+.4f"),
            "best_oos_return": None if best is None else _fmt(best, "+.4f"),
            "winner": deployment["id"] if deployment is not None else "no winner",
            "deployed_to": None if deployment is None else deployment["desk_id"],
            "hypothesis": None if winner is None else winner.get("hypothesis"),
            "code_rejected": [str(r)[:160] for r in (code.get("rejected") or [])[:3]],
            "code_skipped": code.get("skipped"),
            "top": rows,
        }
        payload = _clean(payload)
        while len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > PAYLOAD_BYTES:
            if payload["top"]:
                payload["top"] = payload["top"][:-1]
            elif payload["code_rejected"]:
                payload["code_rejected"] = payload["code_rejected"][:-1]
            else:
                payload["text"] = payload["text"][:400]
                payload["test_plan"] = payload["test_plan"][:400]
                payload["hypothesis"] = (payload.get("hypothesis") or "")[:200] or None
                payload["code_skipped"] = (payload.get("code_skipped") or "")[:120] or None
                break
        at = str(summary.get("at") or self.now())
        try:
            self.log.append("lab", "lab.hypothesis", payload, id=f"foundry:{cycle}:{at}"[:200], at=self.now())
        except Exception as exc:
            self.alert("warning", f"foundry cycle not published: {type(exc).__name__}")


__all__ = [
    "DEFAULTS",
    "Foundry",
    "categorical_pool",
    "jitter_variants",
    "literal_defaults",
    "parse_result",
    "runner_code",
    "split_evidence",
]
