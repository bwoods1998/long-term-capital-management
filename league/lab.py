"""The Alpha Lab: machine-scale search for strategy programs, graded by a verifier the searchers
cannot see past, whose survivors are born on paper.

What the House had before (Sept 23, 2026): one sandboxed replay took about ten seconds, the foundry
wrote one card per call and cards passed replay about a fifth of the time, and 70% of research
sessions abstained. Search was the scarce thing. The lab makes it plentiful and keeps the verifier
honest:

**The archive (MAP-Elites).** `lab.sqlite`, beside the ledger, keeps every candidate the lab has
seen and, per cell of a grid, the best one. A cell is a desk (which fixes the venue and the markets
a program's results are comparable on), a horizon, a trades-per-day bucket and a bucket of the
correlation of the program's block returns with the live book's recorded real-money returns over
the same blocks (`na` where the two never overlap, as on the history store's development window).
Diversity comes from the grid: a program that trades differently, or earns when the live book does
not, has a cell of its own to win, whatever it does. No House template is imposed on anyone.

**Fitness.** Out-of-sample log growth after fees per block, on the lab's SEARCH TAPE: the first
`search_fraction` (two thirds) of the very tape the House replays that program on (`House.tape_for`:
the development window of the history store, or the recent live tape). A candidate is eligible only
with the replay gate's minimum trades, blocks and out-of-sample blocks. The last third of the tape is
never shown to the search, so when a winner is graduated, the House's own replay judges its
out-of-sample third on history no selection in the lab ever touched.

**The loop** (`step`, off the tick on a background lane; the tick only schedules it):
1. Seeds: living agents' programs, the foundry's cards that reached code, and the founders.
2. Children: cheap parameter mutants of the archive's elites (`parameters.mutate`, bounded and
   deterministic), and batches Luna writes -- mutations and crossovers, told the parent's results
   fold by fold and its niche neighbours in words and numbers. Every `leap_every` Luna batches, Sol
   makes a conceptual leap for the desk whose grid is emptiest, told the archive's shape and the
   league's edge map.
3. Every program passes `safety.check_code` and parameter validation before it is queued.
4. Batch evaluation on the lab box (`league/labbox.py`): many candidates against one uploaded tape.
5. Graduation: the fittest elite of a cell that clears the replay gate's numbers is replayed by the
   House itself (`House._candidate_replay`: the sealed NEEDS probe, a counted trial on its own line)
   and, when that tape is the history store's development window, sent to the sealed holdout
   through `House._holdout` -- the one door, with its per-version and per-line rationing, plus a
   per-lab-lineage budget here so that many lines of one lineage cannot probe it. A survivor is born
   with `founder="lab:<lineage>"` and seated on paper exactly as a replay-passing foundry card is,
   at most `max_births_per_hour`, under the league's population and desk caps.
6. Royalties: 10% of the performance fee a graduate earns on realized real profit is paid to the
   lab's compute line (idempotent per fee), and lineages whose graduates lose are searched less.

Spend: OpenAI through the lab's own line (`budget_usd_per_hour`, plus royalties), inside the House's
campaign allowance (every call reserves through the same metered `Frontier` client and its spend
guard) and only while the frontier tier is "all"; the lab box's Sail time is recorded as it runs and
stops with the Sail allowance.

What the agents get (`league/researcher.py`): `lab_query` (the archive and leaderboard for their
desk, and their own submissions' results) and `lab_submit` (queue up to `submit_max` programs for
the next batch). Candidate CODE is never shown to an agent except its own: a mechanism travels as
words, as in the foundry.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import pprint
import random
import re
import sqlite3
import threading
import time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .constitution import CONSTITUTION
from .ledger import now_iso

#: The background job the tick schedules (`House._background`): the replay lane, beside the
#: agents' own replays and the foundry's card evaluations, never the ops lane Merton, the backup
#: and the updater share. A colon cannot be in an agent id, so it cannot collide with `replay:<agent>`.
LAB_JOB = "replay:lab:step"

PROMPT_VERSION = "lab-2026-09-23.1"

#: The dials, overridden by `game.json` `lab`.
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # OpenAI: Luna's mutations and Sol's leaps, per trailing hour, before royalties.
    "budget_usd_per_hour": "1.50",
    # The lab box's price, for the record of what its Sail time cost (the box is one machine: it
    # cannot run more than an hour an hour).
    "box_usd_per_hour": "0.20",
    "batch_size": 32,
    "param_children": 16,
    "llm_children": 6,
    "leap_every": 10,
    "leap_candidates": 4,
    "search_fraction": 0.66,
    "step_seconds": 240,
    "max_births_per_hour": 6,
    "max_graduations_per_step": 1,
    "submit_max": 8,
    "royalty_share": "0.10",
    "min_overlap": 8,
    "timeout": 600,
    "max_tapes_per_step": 4,
    "seed_every_minutes": 60,
    "max_queue": 600,
    "stats_every_minutes": 10,
    "luna_model": "gpt-6-luna",
    "luna_effort": "low",
    "luna_max_output_tokens": 12000,
    "sol_model": "gpt-6-sol",
    "sol_effort": "medium",
    "sol_max_output_tokens": 16000,
}

#: Trades per day on the search tape: the grid's first behavioural axis.
TPD_EDGES = (0.2, 1.0, 5.0, 20.0)
TPD_LABELS = ("under 0.2", "0.2 to 1", "1 to 5", "5 to 20", "20 or more")
#: Correlation of block returns with the live book's: the second. `na` where they never overlap.
CORR_LABELS = ("na", "negative", "low", "medium", "high")

#: Where a candidate stands. `queued` waits for the box; the rest are final for that version.
STATUSES = ("queued", "evaluated", "failed", "invalid", "blocked")

#: Queue order: an agent's own submissions first, then seeds (the archive needs its first elites),
#: then children.
PRIORITY = {"agent": 0, "seed": 1, "param": 2, "luna": 2, "sol": 2}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(
    id TEXT PRIMARY KEY, code TEXT NOT NULL, code_sha256 TEXT NOT NULL, params TEXT NOT NULL,
    needs TEXT NOT NULL, niche TEXT NOT NULL, venue TEXT NOT NULL, horizon TEXT NOT NULL,
    origin TEXT NOT NULL, author TEXT NOT NULL, lineage TEXT NOT NULL, parents TEXT NOT NULL,
    idea TEXT NOT NULL, priority INTEGER NOT NULL, created REAL NOT NULL, status TEXT NOT NULL,
    evaluated REAL, tape_id TEXT, error TEXT, eligible INTEGER, gate INTEGER, fitness REAL,
    trades INTEGER, trades_per_day REAL, corr REAL, cell TEXT, summary TEXT);
CREATE INDEX IF NOT EXISTS candidates_queue ON candidates(status, priority, created);
CREATE INDEX IF NOT EXISTS candidates_niche ON candidates(niche, status);
CREATE INDEX IF NOT EXISTS candidates_author ON candidates(author, created);
CREATE TABLE IF NOT EXISTS archive(
    cell TEXT PRIMARY KEY, niche TEXT NOT NULL, candidate TEXT NOT NULL, fitness REAL NOT NULL,
    since REAL NOT NULL, replaced INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS calls(
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT, at REAL NOT NULL, niche TEXT,
    cost_usd TEXT NOT NULL, royalty_usd TEXT NOT NULL DEFAULT '0', written INTEGER NOT NULL,
    refused INTEGER NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS batches(
    id TEXT PRIMARY KEY, at REAL NOT NULL, tape_id TEXT NOT NULL, niche TEXT, candidates INTEGER NOT NULL,
    ok INTEGER NOT NULL, eligible INTEGER NOT NULL, gate INTEGER NOT NULL, archived INTEGER NOT NULL,
    seconds REAL NOT NULL, sail_usd TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS graduations(
    candidate TEXT PRIMARY KEY, niche TEXT NOT NULL, lineage TEXT NOT NULL, line TEXT NOT NULL,
    family TEXT NOT NULL, state TEXT NOT NULL, agent TEXT, at REAL NOT NULL, detail TEXT NOT NULL,
    needs TEXT, params TEXT);
"""


class LabError(ValueError):
    """A candidate the lab refuses before it costs anything."""


class SealedTape(LabError):
    """A tape that reaches into the sealed holdout. The lab never evaluates on one."""


# ---------------------------------------------------------------------------------- pure helpers

def static_literal(code: str, name: str) -> dict[str, Any] | None:
    """A module-level `NAME = {...}` literal read WITHOUT running the file, or None."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                return None
            return value if isinstance(value, dict) else None
    return None


def with_params(code: str, params: Mapping[str, Any]) -> str | None:
    """The same program with its `PARAMS` literal replaced, so a candidate carries its own
    parameters: the House's replay reads a file's PARAMS in the probe box, and a graduate must be
    replayed as it was evaluated. None when the file has no single literal PARAMS assignment."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    spans = [node for node in tree.body if isinstance(node, ast.Assign) and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "PARAMS"]
    if len(spans) != 1:
        return None
    node = spans[0]
    try:
        if not isinstance(ast.literal_eval(node.value), dict):
            return None
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    lines = code.splitlines()
    lines[node.lineno - 1:node.end_lineno] = ("PARAMS = " + pprint.pformat(dict(params), width=110, sort_dicts=True)).splitlines()
    return "\n".join(lines) + ("\n" if code.endswith("\n") else "")


def candidate_id(code: str) -> str:
    """A candidate is its whole file (its PARAMS literal included)."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:24]


def tpd_bucket(trades_per_day: float) -> int:
    return sum(1 for edge in TPD_EDGES if trades_per_day >= edge)


def corr_bucket(corr: float | None) -> int:
    if corr is None or not math.isfinite(corr):
        return 0
    return 1 if corr < -0.25 else 2 if corr < 0.25 else 3 if corr < 0.6 else 4


def cell_key(niche: str, horizon: str, tpd: int, corr: int) -> str:
    return f"{niche}|{horizon}|t{tpd}|c{corr}"


def describe_cell(cell: str) -> dict[str, Any]:
    niche, horizon, tpd, corr = cell.split("|")
    return {"desk": niche, "horizon": horizon, "trades_per_day": TPD_LABELS[int(tpd[1:])],
            "correlation_with_live_book": CORR_LABELS[int(corr[1:])]}


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.fsum((x - mx) ** 2 for x in xs)
    sy = math.fsum((y - my) ** 2 for y in ys)
    if sx <= 0 or sy <= 0:
        return None
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


def _ts(text: Any) -> float | None:
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def tape_days(tape: Mapping[str, Any]) -> float:
    steps = tape.get("steps") or []
    if len(steps) < 2:
        return 1.0
    first, last = _ts(steps[0].get("t")), _ts(steps[-1].get("t"))
    if first is None or last is None:
        return 1.0
    return max((last - first) / 86400.0, 1.0 / 24)


def check_dev_only(tape: Mapping[str, Any], holdout: tuple[str, str]) -> None:
    """Refuse a tape any part of which lies in the sealed holdout window [start, end)."""
    start, end = str(holdout[0])[:10], str(holdout[1])[:10]
    window = (tape.get("source") or {}).get("window") if isinstance(tape.get("source"), Mapping) else None
    if window and str(window[0])[:10] < end and str(window[1])[:10] > start:
        raise SealedTape(f"the tape's window {window[0]}..{window[1]} overlaps the sealed holdout {start}..{end}")
    steps = tape.get("steps") or []
    if steps:
        first, last = str(steps[0].get("t") or ""), str(steps[-1].get("t") or "")
        if first[:10] < end and last[:10] >= start:
            raise SealedTape(f"the tape's steps {first}..{last} reach into the sealed holdout {start}..{end}")
    for name in ("warmup_bars", "observed_bars"):
        series = tape.get(name) if isinstance(tape.get(name), Mapping) else {}
        for rows in series.values():
            for bar in rows or []:
                stamp = str((bar or {}).get("t") or "")[:10] if isinstance(bar, Mapping) else ""
                if start <= stamp < end:
                    raise SealedTape(f"the tape's {name.replace('_', ' ')} reach into the sealed holdout")


def search_tape(tape: Mapping[str, Any], fraction: float) -> dict[str, Any]:
    """The first `fraction` of a tape's steps: what the search may see. The rest of the tape is the
    House's out-of-sample test at graduation. The House's cached tape is never mutated."""
    steps = list(tape.get("steps") or [])
    cut = max(2, int(len(steps) * max(0.1, min(1.0, float(fraction)))))
    return {**dict(tape), "steps": steps[:cut]}


def folds_of(result: Mapping[str, Any], tape: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The candidate's blocks cut into chronological folds: the history store's own folds on a
    development tape, else thirds. Development diagnostics only."""
    blocks = list(result.get("blocks") or [])
    if not blocks:
        return []
    if (tape.get("source") or {}).get("window") if isinstance(tape.get("source"), Mapping) else None:
        from .deep_replay import walk_forward

        rows = walk_forward(result, tape)
        if rows:
            return rows
    size = max(1, math.ceil(len(blocks) / 3))
    out = []
    for index in range(0, len(blocks), size):
        part = blocks[index:index + size]
        growth = [float(b.get("log_growth") or 0.0) for b in part]
        out.append({"fold": [str(part[0].get("key")), str(part[-1].get("key"))], "blocks": len(part),
                    "active_blocks": sum(1 for b in part if b.get("active")), "log_growth": round(sum(growth), 6),
                    "mean_log_growth": round(sum(growth) / len(growth), 8)})
    return out


def score(result: Mapping[str, Any], tape: Mapping[str, Any], rules: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fitness and the replay gate's numbers for one result on the search tape.

    Eligible: it ran, and it has the gate's minimum trades, blocks and out-of-sample blocks, with no
    unresolved settlement. Fitness: its out-of-sample mean log growth per block (after fees). `gate`:
    eligible, out-of-sample growth above the gate's floor, and active out of sample -- the numeric
    part of `Evaluator._replay_reasons`. The deflated Sharpe is not a lab gate: the House's own
    replay applies it, against the graduate's line, when it graduates."""
    rules = dict(rules or CONSTITUTION["ladder"]["replay"])
    reasons: list[str] = []
    ok = bool(result.get("ok"))
    blocks = list(result.get("blocks") or [])
    trades = int(result.get("trades") or 0)
    oos = result.get("out_of_sample") or {}
    oos_blocks = int(oos.get("blocks") or 0)
    mean_oos = float(oos.get("mean_log_growth") or 0.0)
    days = tape_days(tape)
    if not ok:
        reasons.append(f"the replay failed: {str(result.get('error') or '')[:200]}")
    if int(result.get("unresolved") or 0):
        reasons.append("positions lack a completed settlement")
    if trades < int(rules["min_trades"]):
        reasons.append(f"{trades} closed trades, {rules['min_trades']} needed")
    if len(blocks) < int(rules["min_blocks"]):
        reasons.append(f"{len(blocks)} blocks, {rules['min_blocks']} needed")
    if oos_blocks < int(rules["min_oos_blocks"]):
        reasons.append(f"{oos_blocks} out-of-sample blocks, {rules['min_oos_blocks']} needed")
    eligible = not reasons
    floor = float(rules.get("min_oos_growth", 0.0))
    gate = eligible
    if eligible and mean_oos <= floor:
        gate = False
        reasons.append(f"out-of-sample growth {mean_oos:+.6f} is not above {floor:+.6f} a block")
    if eligible and gate and int(oos.get("active_blocks") or 0) == 0:
        gate = False
        reasons.append("it did not trade out of sample")
    return {
        "ok": ok, "eligible": eligible, "gate": bool(gate), "fitness": mean_oos if eligible else None,
        "trades": trades, "trades_per_day": trades / days, "blocks": len(blocks), "oos_blocks": oos_blocks,
        "reasons": reasons, "folds": folds_of(result, tape) if ok else [],
    }


def _summary(result: Mapping[str, Any], scored: Mapping[str, Any]) -> dict[str, Any]:
    """What is kept of a result: the numbers a mutation writer and an agent are shown."""
    digest = result.get("digest") if isinstance(result.get("digest"), Mapping) else {}
    groups = dict(list((digest.get("by_group") or {}).items())[:6]) if digest else {}
    oos = result.get("out_of_sample") or {}
    return {
        "trades": scored.get("trades"), "trades_per_day": round(float(scored.get("trades_per_day") or 0.0), 4),
        "blocks": scored.get("blocks"), "return_pct": result.get("return_pct"), "max_drawdown": result.get("max_drawdown"),
        "fees_usd": result.get("fees_usd"), "in_sample_mean_log_growth": (result.get("in_sample") or {}).get("mean_log_growth"),
        "oos_mean_log_growth": oos.get("mean_log_growth"), "oos_blocks": oos.get("blocks"), "oos_active_blocks": oos.get("active_blocks"),
        "refusal_reasons": dict(list((result.get("refusal_reasons") or {}).items())[:6]),
        "errors": int(result.get("errors") or 0) if not isinstance(result.get("errors"), list) else len(result.get("errors") or []),
        "last_error": str(result.get("last_error") or "")[:200] or None,
        "folds": scored.get("folds"), "reasons": scored.get("reasons"),
        "digest": {"all": digest.get("all"), "by_group": groups} if digest else None,
    }


def has_evidence(house: Any, agent: Any) -> bool:
    """An agent with evidence: on paper or above (rung >= 1) with at least one closed trade. Such an
    agent's research sessions run longer (`research.evidence_max_turns`)."""
    try:
        if house.evaluator.rung(agent.id) < 1:
            return False
        return bool(house._recent_trades(agent.id, limit=1))
    except Exception:  # noqa: BLE001 - a record that cannot be read buys nothing extra
        return False


# ---------------------------------------------------------------------------------------- prompts

FEES = {
    "kalshi_taker": "0.07 x contracts x price x (1 - price) per order",
    "kalshi_maker": "nothing, except on the desk's maker_fee_series: a quarter of the taker rate",
    "alpaca_crypto": "0.25% taker, 0.15% maker; a round trip 0.50% taker/taker, 0.30% maker/maker",
    "alpaca_equities": "no commission; you cross the spread",
    "replay_fills": "market orders at the touch; resting limits fill only when a later step trades strictly through them",
}

MUTATE_BRIEF = """You write strategy programs for the Alpha Lab of a small real-money trading league. The lab runs
thousands of programs a day against recorded history; the best of each kind is replayed by the House on history
the lab never saw and, if it holds up, is born as a trading agent on practice money. You do not pick trades.

You are shown a PARENT program (and sometimes a PARTNER), how it did on the search tape fold by fold, and the best
programs near it in the archive, in words and numbers. Write the number of NEW complete strategy files asked for in
`batch.candidates` that could earn more OUT OF SAMPLE AFTER FEES. Mix:
- mutations: a changed signal, filter, entry, exit, holding time, sizing or timing rule -- not only other numbers;
- crossovers (when a PARTNER is given): one program that combines what each does well;
- at least one bolder rewrite of the parent's idea.
Every candidate must be a distinct program. Read the parent's folds: an edge that came from one stretch of history
is not an edge. Read `neighbours`: what already fills the archive near the parent; a program that trades at a
different rate, or earns when the live book does not, wins a cell of its own.

The House refuses, before any replay, a file that breaks these rules:
- the strategy contract below, exactly: literal NEEDS and PARAMS dicts, decide(ctx), allowed imports only;
- NEEDS stays on the desk in `desk`: its venue, one of its horizons, markets inside its universe. Keep the parent's
  NEEDS unless your change needs other data;
- PARAMS is a literal dict; every new numeric knob has bounds in NEEDS["parameter_rules"]["bounds"];
- it must TRADE on the tape: `gate` says how many closed trades and blocks a program needs to be scored at all.

Model the fees in `fees`. Size by conviction: the minimum useful size when the signal is marginal, larger only
when the modelled edge is large against its variance. No shorts, no leverage.

Answer with ONE JSON object and nothing else:
{"candidates": [{"name": "short-words-with-dashes", "idea": "one or two sentences: what changed and why it should
earn after fees", "parents": ["the parent and partner ids it came from"], "code": "the WHOLE strategy file"}]}"""

LEAP_BRIEF = """You are Merton, the theorist of a small real-money trading league, making a CONCEPTUAL LEAP for its
Alpha Lab. The lab searches thousands of programs a day by mutating what already exists; mutation climbs the hill
it starts on. Your job is to start new hills. You are shown one desk, the shape of the lab's archive for it (which
cells of its grid -- trades per day by correlation with the live book -- are filled, and how well), what the league
already earns with (`edge_map`, in words), the fees and the gate.

Write the number of programs asked for in `batch.candidates`, each a DIFFERENT MECHANISM -- a different reason the
edge exists, who pays it -- aimed where the archive is empty or weak. Stay on the desk (venue, horizon, universe),
follow the strategy contract below exactly (literal NEEDS and PARAMS, decide(ctx), allowed imports only, bounds in
NEEDS["parameter_rules"] for new numeric knobs), model the fees, size by conviction, and TRADE often enough to be
scored (`gate`). No shorts, no leverage.

Answer with ONE JSON object and nothing else:
{"candidates": [{"name": "short-words-with-dashes", "idea": "why the edge exists and who pays it, in two
sentences", "code": "the WHOLE strategy file"}]}"""


# ------------------------------------------------------------------------------------------- lab

class Lab:
    """The Alpha Lab. One per House; its store is `lab.sqlite` under the House's root."""

    def __init__(self, house: Any, *, box: Any = None, mutator: Any = None, leaper: Any = None,
                 path: str | Path | None = None, box_key: str | None = None):
        self.house = house
        self._box = box
        self._mutator = mutator
        self._leaper = leaper
        self.box_key = box_key or str(getattr(getattr(house, "settings", None), "lab_box", "") or "lab")
        self.path = Path(path or Path(house.root) / "lab.sqlite")
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._tapes: dict[str, tuple[float, str, dict[str, Any]]] = {}  # needs json -> (built at, lab tape id, search tape)
        self._tapes_built = 0
        self._tape_errors: dict[str, tuple[float, str]] = {}
        self._live: tuple[float, dict[str, dict[str, float]]] | None = None
        self._weights: tuple[float, dict[str, float]] | None = None
        self._rng = random.Random(int(house.clock()))
        self.refusal = ""
        if self._meta("fee_cursor") is None:
            # A graduate cannot exist before the lab, so no older fee can owe it a royalty.
            self._set_meta("fee_cursor", str(house.ledger.head()[0]))

    # ------------------------------------------------------------------ store
    def _q(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, tuple(params)).fetchall()

    def _x(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self._lock:
            self._db.execute(sql, tuple(params))

    def _meta(self, key: str) -> str | None:
        rows = self._q("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def _set_meta(self, key: str, value: str) -> None:
        self._x("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ dials
    @property
    def settings(self) -> dict[str, Any]:
        own = (self.house.game.get("lab") or {}) if isinstance(self.house.game, Mapping) else {}
        return {**DEFAULTS, **{k: v for k, v in own.items() if not str(k).startswith("_")}}

    def _now(self) -> float:
        return float(self.house.clock())

    @property
    def box(self) -> Any:
        """The lab box's batch evaluator (`league/labbox.py`): the one the service bound to the box
        `config.json` names (`use_box`), else one over the House's sandbox under `box_key`."""
        if self._box is None:
            from .labbox import LabBox

            self._box = LabBox(self.house.sandbox, box_key=self.box_key, clock=self.house.clock)
        return self._box

    def use_box(self, box: Any) -> None:
        self._box = box

    def _client(self, which: str) -> Any:
        """Luna (mutations) or Sol (leaps): the same metered gateway client every other pass uses,
        on the lab's model; its spend guard is the House's campaign allowance."""
        given = self._mutator if which == "luna" else self._leaper
        if given is not None:
            return given
        model = str(self.settings[f"{which}_model"])
        if which == "sol":
            foundry = getattr(self.house, "hypotheses", None)
            writer = getattr(foundry, "frontier", None) if foundry is not None else None
            if writer is not None and getattr(writer, "model", None) == model:
                return writer
        base = getattr(self.house, "frontier", None)
        if base is None:
            return None
        client = copy.copy(base)
        client.model = model
        if which == "luna":
            self._mutator = client
        else:
            self._leaper = client
        return client

    # ---------------------------------------------------------------- cadence
    def open(self) -> str:
        """'' when the lab may work now, else why not. The House being stopped, paused, deploying
        or out of Sail allowance stops it, and so does an OpenAI tier below "all"."""
        house = self.house
        if not self.settings.get("enabled"):
            return "disabled in game.json"
        if house._closing.is_set():
            return "the House is closing"
        if house.stopped():
            return "the House is stopped"
        if house.paused():
            return "maintenance pause"
        if house.deploying():
            return "a release is being staged"
        if getattr(house, "campaigns", None) and not house.pacer.may_spend("sail"):
            return "the Sail allowance is closed"
        if self.box_down():
            return "the lab box failed a batch in the last five minutes"
        tier = house.frontier_tier()
        if tier != "all":
            return f"the OpenAI tier is {tier!r}"
        return ""

    def tick(self, *, open_for_business: bool) -> bool:
        """Called from `House.tick`: schedules one bounded `step` on a background lane. Never works
        on the tick itself."""
        if not open_for_business:
            self.refusal = "the House is not open for business"
            return False
        job = self.house._jobs.get(LAB_JOB)
        if job is not None and job.is_alive():
            return False
        self.refusal = self.open()
        if self.refusal:
            return False
        return bool(self.house._background(LAB_JOB, self.step))

    def step(self) -> dict[str, Any]:
        """One bounded pass: seed, breed, evaluate in batches until `step_seconds`, graduate,
        collect royalties, publish. Never raises into its lane."""
        started = time.monotonic()
        settings = self.settings
        out: dict[str, Any] = {"batches": 0, "evaluated": 0, "archived": 0, "calls": 0, "graduations": []}
        self._tapes_built = 0
        try:
            self.royalties()
            self.seed()
            while time.monotonic() - started < float(settings["step_seconds"]):
                if self.open():
                    break
                if self.queued() < int(settings["batch_size"]):
                    out["calls"] += self.breed()
                done = self.evaluate_batch()
                if not done:
                    break
                if done.get("refused"):
                    continue
                out["batches"] += 1
                out["evaluated"] += done["candidates"]
                out["archived"] += done["archived"]
            if not self.open():
                out["graduations"] = self.graduate()
        except Exception as exc:  # noqa: BLE001 - the lab must never take a lane or the tick down
            self.house.alert("warning", f"the lab's step failed ({type(exc).__name__}: {str(exc)[:200]})")
            out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        try:
            self.publish()
        except Exception as exc:  # noqa: BLE001
            self.house.alert("warning", f"the lab could not publish its stats ({type(exc).__name__}: {str(exc)[:160]})")
        return out

    # ----------------------------------------------------------------- queue
    def queued(self) -> int:
        return int(self._q("SELECT COUNT(*) AS n FROM candidates WHERE status='queued'")[0]["n"])

    def admit(self, code: str, *, niche: Any, origin: str, author: str, lineage: str, parents: Sequence[str] = (),
              idea: str = "", priority: int | None = None) -> str:
        """Check one program and queue it. Returns its id; raises `LabError` saying why not. The
        checks are the ones replay and birth apply: the code safety check, literal NEEDS on this
        desk, and valid parameters."""
        from . import niches as niches_module
        from .agents import niche_of
        from .parameters import inspect
        from .safety import CodeRefused, check_code

        code = str(code or "")
        if not code.strip():
            raise LabError("an empty file")
        if len(code) > 60_000:
            raise LabError("a file over 60,000 characters")
        try:
            check_code(code)
        except (CodeRefused, SyntaxError) as exc:
            raise LabError(f"the strategy check refused it: {str(exc)[:200]}") from None
        needs = static_literal(code, "NEEDS")
        if needs is None:
            raise LabError("NEEDS must be a literal dict")
        params = static_literal(code, "PARAMS")
        if params is None:
            raise LabError("PARAMS must be a literal dict")
        try:
            venue, horizon, _ = niche_of(needs)
        except ValueError as exc:
            raise LabError(str(exc)) from None
        if venue != niche.venue or horizon not in niche.horizons:
            raise LabError(f"its NEEDS say {venue}/{horizon}, outside the {niche.id} desk")
        asked = needs.get(niche.key) if isinstance(needs.get(niche.key), list) else []
        if not {str(x).upper() for x in asked} & set(niche.universe):
            # The House would show such a program the head of the desk's universe instead
            # (`niches.constrain`): a test of something it never asked about.
            raise LabError(f"its NEEDS name nothing in the {niche.id} universe")
        if (niche.asset_class == "option") != (str(needs.get("asset_class") or "") == "option"):
            raise LabError(f"its NEEDS are not for the {niche.id} desk's asset class")
        try:
            needs = niches_module.constrain(needs, niche)
        except ValueError as exc:
            raise LabError(str(exc)) from None
        report = inspect(params, needs)
        if not report["valid"]:
            raise LabError("invalid parameters: " + "; ".join(report["errors"])[:300])
        ident = candidate_id(code)
        if self._q("SELECT 1 FROM candidates WHERE id=?", (ident,)):
            raise LabError(f"{ident}: this exact program is already in the lab")
        self._x("INSERT INTO candidates(id, code, code_sha256, params, needs, niche, venue, horizon, origin, author, lineage, parents,"
                " idea, priority, created, status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'queued')",
                (ident, code, hashlib.sha256(code.encode("utf-8")).hexdigest(), json.dumps(params, sort_keys=True),
                 json.dumps(needs, sort_keys=True), niche.id, venue, horizon, origin, str(author)[:120], str(lineage)[:120],
                 json.dumps(list(parents)[:4]), str(idea or "")[:600], PRIORITY.get(origin, 2) if priority is None else int(priority),
                 self._now()))
        return ident

    def _desk(self, niche_id: str) -> Any:
        niche = self.house.niches.get(niche_id)
        if niche is None or niche.dormant or not niche.replay or niche.asset_class == "option":
            return None
        return niche

    # ----------------------------------------------------------------- seeds
    def seed(self, *, force: bool = False) -> int:
        """Living agents' programs, the foundry's cards that reached code and the founders, each
        once (a program already in the lab is not queued again)."""
        every = float(self.settings["seed_every_minutes"]) * 60
        last = float(self._meta("seeded_at") or 0)
        if not force and self._now() - last < every:
            return 0
        self._set_meta("seeded_at", str(self._now()))
        added = 0
        rows: list[tuple[str, Any, str, str, str]] = []  # (code, niche, author, lineage, idea)
        for agent in self.house.registry.living():
            niche = self._desk(agent.specialty or "")
            if niche is None:
                continue
            params = {**(static_literal(agent.code, "PARAMS") or {}), **dict(agent.params or {})}
            code = with_params(agent.code, params) if params != (static_literal(agent.code, "PARAMS") or {}) else agent.code
            if code:
                rows.append((code, niche, agent.id, f"agent:{agent.id}", f"the program {agent.id} trades now"))
        foundry = getattr(self.house, "hypotheses", None)
        if foundry is not None:
            try:
                for card in foundry.cards().values():
                    niche = self._desk(str(card.get("niche") or ""))
                    if niche is not None:
                        rows.append((foundry._code(card), niche, "merton", f"card:{card['id']}", str(card.get("mechanism") or "")[:400]))
            except Exception as exc:  # noqa: BLE001 - the other seeds still count
                self.house.alert("warning", f"the lab could not read the foundry's cards ({type(exc).__name__}: {str(exc)[:120]})")
        try:
            for founder in self.house.founders():
                niche = self._desk(founder["niche"])
                if niche is not None:
                    rows.append((founder["code"], niche, "house", f"founder:{founder['key']}", str(founder.get("why") or "")[:400]))
        except Exception as exc:  # noqa: BLE001
            self.house.alert("warning", f"the lab could not read the founders ({type(exc).__name__}: {str(exc)[:120]})")
        for code, niche, author, lineage, idea in rows:
            try:
                self.admit(code, niche=niche, origin="seed", author=author, lineage=lineage, idea=idea)
                added += 1
            except LabError:
                continue
        return added

    # ----------------------------------------------------------------- tapes
    def _search_tape(self, needs: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """(lab tape id, search tape) for these NEEDS: the House's own tape for them, with the same
        input checks its replay makes, never one that reaches the sealed holdout, cut to its first
        `search_fraction`."""
        key = json.dumps(needs, sort_keys=True)
        hit = self._tapes.get(key)
        if hit is not None and self._now() - hit[0] < 6 * 3600:  # the House rebuilds its own tapes daily
            return hit[1], hit[2]
        failed = self._tape_errors.get(key)
        if failed is not None and self._now() - failed[0] < 3600:
            raise LabError(failed[1])
        if self._tapes_built >= int(self.settings["max_tapes_per_step"]):
            raise TimeoutError("the step's tape budget is spent")
        self._tapes_built += 1
        house = self.house
        with house._tape_lock:
            cached = set(house._tapes)
        try:
            wanted = house._feeds_wanted(needs)
            if wanted:
                start, end = house._live_window(needs)
                house._require_feeds(needs, wanted, house.feeds.coverage(wanted, start, end) if house.feeds is not None else {})
            tape_id, tape = house.tape_for(needs)
            if wanted:
                house._require_feeds(needs, wanted, tape.get("feeds_coverage") or {})
            observed = needs.get("observe") or {}
            missing = [s for s in observed.get("symbols") or [] if not (tape.get("observed_bars") or {}).get(s)]
            if needs.get("venue") == "kalshi" and missing:
                raise LabError("unsupported input: observed bars are missing for " + ", ".join(missing))
            if needs.get("venue") == "alpaca" and observed.get("series"):
                raise LabError("unsupported input: cross-venue event observations are not recorded on equity tapes")
            check_dev_only(tape, house.holdout_window)
        except (LabError, TimeoutError):
            raise
        except Exception as exc:  # noqa: BLE001 - no tape is a blocked candidate, not a crash
            message = f"{type(exc).__name__}: {str(exc)[:200]}"
            self._tape_errors[key] = (self._now(), message)
            raise LabError(message) from None
        cut = search_tape(tape, float(self.settings["search_fraction"]))
        if tape_id not in cached:
            # A tape only the lab asked for is not kept in the House's own cache (which keeps one
            # tape a key for a day, and a House box has a few GB): the lab keeps its search copy.
            with house._tape_lock:
                house._tapes.pop(tape_id, None)
        steps = cut["steps"]
        ident = "lab:" + hashlib.sha256(f"{tape_id}|{steps[0].get('t')}|{steps[-1].get('t')}|{len(steps)}".encode()).hexdigest()[:24]
        self._tapes.pop(key, None)
        if len(self._tapes) >= 6:
            self._tapes.pop(next(iter(self._tapes)))
        self._tapes[key] = (self._now(), ident, cut)
        return ident, cut

    # --------------------------------------------------------------- evaluate
    def evaluate_batch(self) -> dict[str, Any] | None:
        """One batch on the lab box: the queue's front, grouped by the tape they need. None when
        nothing could be evaluated."""
        settings = self.settings
        size = int(settings["batch_size"])
        # A wide look: rows whose tape is not built yet are passed over (at most `max_tapes_per_step` new
        # tapes a step), so children on a ready tape are not starved behind seeds on unbuilt ones.
        rows = self._q("SELECT * FROM candidates WHERE status='queued' ORDER BY priority, created LIMIT ?", (size * 16,))
        if not rows:
            return None
        groups: dict[str, list[sqlite3.Row]] = {}
        tapes: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                tape_id, tape = self._search_tape(json.loads(row["needs"]))
            except TimeoutError:
                continue  # its tape waits for the next step
            except LabError as exc:
                if isinstance(exc, SealedTape) or "unsupported input" in str(exc) or "invalid" in str(exc).lower():
                    self._x("UPDATE candidates SET status='blocked', error=?, evaluated=? WHERE id=?", (str(exc)[:300], self._now(), row["id"]))
                else:  # a venue or store that failed now: to the back of the queue, tried again after the hour's cache
                    self._x("UPDATE candidates SET created=?, error=? WHERE id=?", (self._now(), str(exc)[:300], row["id"]))
                continue
            groups.setdefault(tape_id, []).append(row)
            tapes[tape_id] = tape
        if not groups:
            return None
        tape_id = max(groups, key=lambda k: (len(groups[k]), -min(r["priority"] for r in groups[k])))
        chosen = groups[tape_id][:size]
        tape = tapes[tape_id]
        row1 = CONSTITUTION["rungs"]["1"]
        limits = {"max_position_usd": float(row1["max_position_usd"]), "max_order_usd": float(row1["max_order_usd"])}
        started = time.monotonic()
        batch = [{"id": r["id"], "code": r["code"], "params": {}} for r in chosen]
        try:
            results = self.box.evaluate(batch, tape_id, tape, stake=float(row1["stake_usd"]), limits=limits,
                                        timeout=float(settings["timeout"]))
        except Exception as exc:  # noqa: BLE001 - see below
            if type(exc).__name__ == "TapeRefused" or "unsupported input" in str(exc):
                # The box's own seal refused the tape (`labbox.LabBox.check`): unavailable data, never a
                # result. Its candidates are blocked, and the tape is not built for them again.
                for key, hit in list(self._tapes.items()):
                    if hit[1] == tape_id:
                        self._tapes.pop(key)
                        self._tape_errors[key] = (self._now(), f"unsupported input: {str(exc)[:200]}")
                for r in chosen:
                    self._x("UPDATE candidates SET status='blocked', error=?, evaluated=? WHERE id=?",
                            (f"the lab box refused the tape: {str(exc)[:260]}", self._now(), r["id"]))
                return {"candidates": 0, "ok": 0, "eligible": 0, "gate": 0, "archived": 0, "refused": len(chosen)}
            # Infrastructure, never the candidates' fault: they stay queued, and the box is left alone
            # for five minutes rather than asked again every tick.
            self._box_down_until = self._now() + 300
            self.house.alert("warning", f"the lab box could not evaluate a batch ({type(exc).__name__}: {str(exc)[:200]})")
            return None
        seconds = time.monotonic() - started
        by_id = {str(r.get("id")): r for r in results or [] if isinstance(r, Mapping)}
        counts = {"candidates": 0, "ok": 0, "eligible": 0, "gate": 0, "archived": 0}
        live = self._live_series(tape.get("horizon") or chosen[0]["horizon"])
        for row in chosen:
            result = by_id.get(row["id"])
            if result is None or "not evaluated" in str(result.get("error") or ""):
                continue  # the batch's budget did not reach it: it stays queued
            counts["candidates"] += 1
            scored = score(result, tape)
            corr = self._correlation(result, live)
            cell = cell_key(row["niche"], row["horizon"], tpd_bucket(scored["trades_per_day"]), corr_bucket(corr))
            status = "evaluated" if scored["ok"] else "failed"
            counts["ok"] += scored["ok"]
            counts["eligible"] += scored["eligible"]
            counts["gate"] += scored["gate"]
            self._x("UPDATE candidates SET status=?, evaluated=?, tape_id=?, error=?, eligible=?, gate=?, fitness=?, trades=?,"
                    " trades_per_day=?, corr=?, cell=?, summary=? WHERE id=?",
                    (status, self._now(), tape_id, None if scored["ok"] else str(result.get("error") or "")[:300],
                     int(scored["eligible"]), int(scored["gate"]), scored["fitness"], scored["trades"],
                     scored["trades_per_day"], corr, cell if scored["eligible"] else None,
                     json.dumps(_summary(result, scored), default=str), row["id"]))
            if scored["eligible"] and self._place(cell, row["niche"], row["id"], float(scored["fitness"])):
                counts["archived"] += 1
        box_usd = Decimal(str(self.settings["box_usd_per_hour"])) * Decimal(str(round(seconds, 3))) / Decimal(3600)
        self._x("INSERT INTO batches(id, at, tape_id, niche, candidates, ok, eligible, gate, archived, seconds, sail_usd)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f"batch:{self._now():.6f}:{tape_id[-8:]}:{self._rng.random():.6f}", self._now(), tape_id, chosen[0]["niche"],
                 counts["candidates"], counts["ok"], counts["eligible"], counts["gate"], counts["archived"], round(seconds, 3),
                 format(box_usd.quantize(Decimal("0.000001")), "f")))
        return counts if counts["candidates"] else None

    def box_down(self) -> bool:
        return self._now() < float(getattr(self, "_box_down_until", 0.0))

    def _place(self, cell: str, niche: str, ident: str, fitness: float) -> bool:
        """Insert into the archive when the cell is empty or this candidate is fitter (strictly)."""
        with self._lock:
            row = self._db.execute("SELECT * FROM archive WHERE cell=?", (cell,)).fetchone()
            if row is None:
                self._db.execute("INSERT INTO archive(cell, niche, candidate, fitness, since, replaced) VALUES(?,?,?,?,?,0)",
                                 (cell, niche, ident, fitness, self._now()))
                return True
            if fitness > float(row["fitness"]):
                self._db.execute("UPDATE archive SET candidate=?, fitness=?, since=?, replaced=replaced+1 WHERE cell=?",
                                 (ident, fitness, self._now(), cell))
                return True
        return False

    # ------------------------------------------------------------ live book
    def _live_series(self, horizon: str) -> dict[str, float]:
        """The live book's recorded real-money returns by block key: the mean after-cost log growth
        of every agent with an account on a real book, per block (a day block sums its agent's hours)."""
        now = self._now()
        if self._live is None or now - self._live[0] > 600:
            per: dict[str, dict[str, dict[str, float]]] = {"hour": {}, "day": {}}
            for name, book in self.house.books.items():
                if not getattr(book, "real_money", False):
                    continue
                for agent in list(getattr(book, "accounts", {}) or {}):
                    hours: dict[str, float] = {}
                    days: dict[str, float] = {}
                    for entry in self.house.ledger.iter(kinds="eval.block", agent=agent):
                        p = entry.payload
                        if p.get("book") != name or p.get("log_growth") is None:
                            continue
                        key = str(p.get("key") or "")
                        growth = float(p["log_growth"])
                        if len(key) >= 13:
                            hours[key[:13]] = hours.get(key[:13], 0.0) + growth
                        days[key[:10]] = days.get(key[:10], 0.0) + growth
                    for label, rows in (("hour", hours), ("day", days)):
                        for key, value in rows.items():
                            per[label].setdefault(key, {})[agent] = value
            self._live = (now, {label: {key: sum(v.values()) / len(v) for key, v in rows.items()} for label, rows in per.items()})
        return self._live[1].get("day" if horizon == "day" else "hour", {})

    def _correlation(self, result: Mapping[str, Any], live: Mapping[str, float]) -> float | None:
        if not live:
            return None
        pairs = [(float(b.get("log_growth") or 0.0), live[str(b.get("key"))]) for b in result.get("blocks") or []
                 if str(b.get("key")) in live]
        if len(pairs) < int(self.settings["min_overlap"]):
            return None
        return pearson([a for a, _ in pairs], [b for _, b in pairs])

    # ------------------------------------------------------------------ breed
    def lineage_weights(self) -> dict[str, float]:
        """How much search each lineage gets: doubled for each graduate earning forward (or paying
        royalties), halved for each that lost or died, between 1/8 and 8, times one plus its royalties."""
        now = self._now()
        if self._weights is not None and now - self._weights[0] < 600:
            return self._weights[1]
        score_of: dict[str, int] = {}
        for row in self._q("SELECT lineage, agent FROM graduations WHERE state='born' AND agent IS NOT NULL"):
            agent = self.house.registry.get(row["agent"])
            if agent is None:
                continue
            delta = 0
            if not agent.alive:
                delta = 0 if agent.cause in ("redundant",) else -1
            else:
                try:
                    standing = self.house.standing_of(agent.id)
                except Exception:  # noqa: BLE001 - an unreadable record moves nothing
                    standing = {}
                growth, seen = float(standing.get("earned_growth") or 0.0), int(standing.get("earned_observations") or 0)
                delta = 1 if seen > 0 and growth > 0 else -1 if seen >= 5 and growth < 0 else 0
            score_of[row["lineage"]] = score_of.get(row["lineage"], 0) + delta
        royalties: dict[str, Decimal] = {}
        for entry in self.house.ledger.iter(kinds="lab.royalty"):
            lineage = str(entry.payload.get("lineage") or "")
            royalties[lineage] = royalties.get(lineage, Decimal(0)) + Decimal(str(entry.payload.get("usd") or 0))
        weights = {}
        for lineage in set(score_of) | set(royalties):
            base = 2.0 ** max(-3, min(3, score_of.get(lineage, 0) + (1 if royalties.get(lineage, 0) > 0 else 0)))
            weights[lineage] = base * (1.0 + float(royalties.get(lineage, Decimal(0))))
        self._weights = (now, weights)
        return weights

    def elites(self, niche: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT a.cell, a.fitness AS elite_fitness, a.replaced, c.* FROM archive a JOIN candidates c ON c.id = a.candidate"
               + (" WHERE a.niche=?" if niche else "") + " ORDER BY a.fitness DESC")
        return self._q(sql, (niche,) if niche else ())

    def _pick_parent(self, niche: str | None = None) -> sqlite3.Row | None:
        rows = [r for r in self.elites(niche) if self._desk(r["niche"]) is not None]
        if not rows:
            return None
        weights = self.lineage_weights()
        scale = [max(0.01, weights.get(r["lineage"], 1.0)) for r in rows]
        return self._rng.choices(rows, weights=scale, k=1)[0]

    def breed(self) -> int:
        """Children for the next batch: parameter mutants of elites (free), then one paid call
        (Luna, or Sol every `leap_every` Luna calls) when the lab's line has room. Returns the paid
        calls made."""
        from .parameters import mutate

        settings = self.settings
        room = max(0, int(settings["max_queue"]) - self.queued())
        for n in range(min(int(settings["param_children"]), room)):
            parent = self._pick_parent()
            if parent is None:
                break
            params = json.loads(parent["params"])
            needs = json.loads(parent["needs"])
            try:
                child = mutate(params, seed=f"lab:{parent['id']}:{self._now():.3f}:{n}", needs=needs)
            except ValueError:
                continue
            code = with_params(parent["code"], child)
            niche = self._desk(parent["niche"])
            if not code or niche is None:
                continue
            changed = ", ".join(f"{k} {params.get(k)} -> {v}" for k, v in child.items() if params.get(k) != v)
            try:
                self.admit(code, niche=niche, origin="param", author="house", lineage=parent["lineage"], parents=[parent["id"]],
                           idea=f"a parameter mutation of {parent['id'][:8]}: {changed}"[:600])
            except LabError:
                continue
        if self.queued() >= int(settings["max_queue"]):
            return 0
        luna_since_sol = int(self._q("SELECT COUNT(*) AS n FROM calls WHERE kind='luna' AND at > "
                                     "COALESCE((SELECT MAX(at) FROM calls WHERE kind='sol'), 0)")[0]["n"])
        if luna_since_sol >= int(settings["leap_every"]):
            return int(self.leap())
        return int(self.mutate_llm())

    # --------------------------------------------------------------- budget
    def spent_last_hour(self) -> Decimal:
        since = self._now() - 3600
        return sum((Decimal(r["cost_usd"]) - Decimal(r["royalty_usd"]) for r in self._q("SELECT cost_usd, royalty_usd FROM calls WHERE at>=?", (since,))),
                   Decimal(0))

    def royalty_balance(self) -> Decimal:
        earned = sum((Decimal(str(e.payload.get("usd") or 0)) for e in self.house.ledger.iter(kinds="lab.royalty")), Decimal(0))
        used = sum((Decimal(r["royalty_usd"]) for r in self._q("SELECT royalty_usd FROM calls")), Decimal(0))
        return max(Decimal(0), earned - used)

    def room(self) -> tuple[Decimal, Decimal]:
        """(what the hourly line has left, what royalties add)."""
        base = max(Decimal(0), Decimal(str(self.settings["budget_usd_per_hour"])) - self.spent_last_hour())
        return base, self.royalty_balance()

    @staticmethod
    def hold(client: Any, system: str, user: str, max_output_tokens: int) -> Decimal:
        """The call's worst case at the model's ceiling prices, as the Frontier client reserves it."""
        from .frontier import MODEL_CEILINGS

        rates = MODEL_CEILINGS.get(str(getattr(client, "model", "")))
        if rates is None:
            return Decimal("1000")
        size = len(json.dumps({"input": [system, user]}).encode("utf-8")) + 4096
        return (Decimal(size) * rates[0] + Decimal(int(max_output_tokens)) * rates[1]) / Decimal(1_000_000)

    def _llm_refusal(self, client: Any, hold: Decimal) -> str:
        house = self.house
        if client is None:
            return "no model client"
        if house.frontier_tier() != "all":
            return f"the OpenAI tier is {house.frontier_tier()!r}"
        if not house.pacer.may_spend("openai"):
            return "the House's OpenAI allowance is closed"
        base, royalties = self.room()
        if hold > base + royalties:
            return f"the lab's line has ${base + royalties:.4f} left this hour and the call may cost ${hold:.4f}"
        return ""

    def _ask(self, kind: str, client: Any, system: str, user: str, *, niche: str, max_output_tokens: int, effort: str) -> list[dict[str, Any]] | None:
        from .frontier import FrontierError

        hold = self.hold(client, system, user, max_output_tokens)
        refusal = self._llm_refusal(client, hold)
        if refusal:
            self.refusal = refusal
            return None
        base, _ = self.room()
        ident = f"lab-{kind}:{self._now():.6f}:{self._rng.random():.6f}"
        answer = None
        try:
            answer = client.ask(system=system, user=user, agent=f"lab-{kind}", max_output_tokens=max_output_tokens, effort=effort)
            parsed = answer.json()
            listed = parsed.get("candidates") if isinstance(parsed.get("candidates"), list) else []
            error = None
        except FrontierError as exc:
            listed, error = [], str(exc)[:300]
        cost = Decimal(str(getattr(answer, "cost_usd", 0) or 0)) if answer is not None else Decimal(0)
        royalty = max(Decimal(0), cost - base)
        self._x("INSERT INTO calls(id, kind, model, at, niche, cost_usd, royalty_usd, written, refused, error) VALUES(?,?,?,?,?,?,?,0,0,?)",
                (ident, kind, getattr(answer, "model", None) or getattr(client, "model", None), self._now(), niche,
                 format(cost, "f"), format(royalty, "f"), error))
        self._last_call = ident
        return [c for c in listed if isinstance(c, dict)][:12]

    def _note_call(self, written: int, refused: int) -> None:
        ident = getattr(self, "_last_call", None)
        if ident:
            self._x("UPDATE calls SET written=?, refused=? WHERE id=?", (written, refused, ident))

    def _desk_brief(self, niche: Any) -> dict[str, Any]:
        return {"id": niche.id, "title": niche.title, "venue": niche.venue, "horizons": list(niche.horizons),
                "asset_class": niche.asset_class, "universe": list(niche.universe[:24]), "brief": niche.brief[:1500],
                "maker_fee_series": list(niche.maker_fee_series)}

    def _shown(self, row: Mapping[str, Any], *, code: bool) -> dict[str, Any]:
        summary = json.loads(row["summary"] or "{}")
        out = {"id": row["id"], "idea": row["idea"], "origin": row["origin"], "fitness": row["fitness"],
               "cell": describe_cell(row["cell"]) if row["cell"] else None,
               "results": {k: summary.get(k) for k in ("trades", "trades_per_day", "return_pct", "max_drawdown", "fees_usd",
                                                        "in_sample_mean_log_growth", "oos_mean_log_growth", "oos_active_blocks",
                                                        "folds", "reasons", "digest", "refusal_reasons", "last_error")}}
        if code:
            out["code"] = row["code"]
        return out

    def _gate_text(self) -> dict[str, Any]:
        return {**dict(CONSTITUTION["ladder"]["replay"]),
                "note": "a program needs min_trades closed trades, min_blocks blocks and min_oos_blocks out-of-sample blocks to be "
                        "scored; fitness is its out-of-sample mean log growth per block after fees"}

    def mutate_llm(self) -> bool:
        """One Luna batch: mutations and crossovers of a chosen elite, told its folds and neighbours."""
        from .hypotheses import REPLAY_VIEW
        from .house import CONTRACT_PATH

        parent = self._pick_parent()
        if parent is None:
            return False
        niche = self._desk(parent["niche"])
        if niche is None:
            return False
        neighbours = [r for r in self.elites(parent["niche"]) if r["id"] != parent["id"]]
        partner = self._rng.choice(neighbours) if neighbours and self._rng.random() < 0.5 else None
        settings = self.settings
        packet = {
            "batch": {"candidates": int(settings["llm_children"]), "prompt_version": PROMPT_VERSION},
            "desk": self._desk_brief(niche),
            "parent": self._shown(parent, code=True),
            "partner": self._shown(partner, code=True) if partner is not None else None,
            "neighbours": [self._shown(r, code=False) for r in neighbours[:6]],
            "fees": FEES, "gate": self._gate_text(), "replay_view": REPLAY_VIEW,
            "tape": "the first two thirds of the tape the House replays this desk on; the last third is kept for the House's own test",
        }
        system = MUTATE_BRIEF + "\n\nTHE STRATEGY CONTRACT\n\n" + CONTRACT_PATH.read_text(encoding="utf-8")
        client = self._client("luna")
        listed = self._ask("luna", client, system, json.dumps(packet, default=str, sort_keys=True), niche=niche.id,
                           max_output_tokens=int(settings["luna_max_output_tokens"]), effort=str(settings["luna_effort"]))
        if listed is None:
            return False
        parents = [parent["id"]] + ([partner["id"]] if partner is not None else [])
        written = refused = 0
        for raw in listed[: int(settings["llm_children"])]:
            try:
                self.admit(str(raw.get("code") or ""), niche=niche, origin="luna", author="luna", lineage=parent["lineage"],
                           parents=parents, idea=str(raw.get("idea") or raw.get("name") or ""))
                written += 1
            except LabError:
                refused += 1
        self._note_call(written, refused)
        return True

    def leap(self) -> bool:
        """One Sol call for the replayable desk whose grid is emptiest, told the archive's shape and
        the league's edge map."""
        from .hypotheses import REPLAY_VIEW
        from .house import CONTRACT_PATH

        desks = [n for n in self.house.niches.values() if self._desk(n.id) is not None]
        if not desks:
            return False
        filled = {r["niche"]: r["n"] for r in self._q("SELECT niche, COUNT(*) AS n FROM archive GROUP BY niche")}
        niche = min(desks, key=lambda n: (filled.get(n.id, 0), self._rng.random()))
        cells = [{**describe_cell(r["cell"]), "fitness": r["elite_fitness"], "idea": r["idea"], "origin": r["origin"],
                  "trades_per_day": (json.loads(r["summary"] or "{}")).get("trades_per_day")} for r in self.elites(niche.id)]
        foundry = getattr(self.house, "hypotheses", None)
        try:
            edge = foundry.winning_mechanisms() if foundry is not None else {}
        except Exception:  # noqa: BLE001 - the leap is still worth making without it
            edge = {}
        settings = self.settings
        packet = {
            "batch": {"candidates": int(settings["leap_candidates"]), "prompt_version": PROMPT_VERSION},
            "desk": self._desk_brief(niche),
            "archive": {"filled_cells": cells[:24], "grid": {"trades_per_day": list(TPD_LABELS), "correlation_with_live_book": list(CORR_LABELS)},
                        "evaluated_on_this_desk": int(self._q("SELECT COUNT(*) AS n FROM candidates WHERE niche=? AND status!='queued'", (niche.id,))[0]["n"])},
            "edge_map": edge, "fees": FEES, "gate": self._gate_text(), "replay_view": REPLAY_VIEW,
        }
        system = LEAP_BRIEF + "\n\nTHE STRATEGY CONTRACT\n\n" + CONTRACT_PATH.read_text(encoding="utf-8")
        client = self._client("sol")
        listed = self._ask("sol", client, system, json.dumps(packet, default=str, sort_keys=True), niche=niche.id,
                           max_output_tokens=int(settings["sol_max_output_tokens"]), effort=str(settings["sol_effort"]))
        if listed is None:
            return False
        written = refused = 0
        for raw in listed[: int(settings["leap_candidates"])]:
            code = str(raw.get("code") or "")
            try:
                self.admit(code, niche=niche, origin="sol", author="sol", lineage=f"sol:{candidate_id(code)[:12]}",
                           idea=str(raw.get("idea") or raw.get("name") or ""))
                written += 1
            except LabError:
                refused += 1
        self._note_call(written, refused)
        return True

    # -------------------------------------------------------------- graduate
    def births_last_hour(self) -> int:
        return int(self._q("SELECT COUNT(*) AS n FROM graduations WHERE state='born' AND at>=?", (self._now() - 3600,))[0]["n"])

    def _lineage_holdouts(self, lineage: str) -> int:
        """Sealed-holdout evaluations the lines of one lab lineage have opened, from the ledger's own
        `holdout.access` rows: the lab's lineage budget sits on top of each line's own."""
        lines = {r["line"] for r in self._q("SELECT line FROM graduations WHERE lineage=?", (lineage,))}
        if not lines:
            return 0
        return sum(1 for e in self.house.ledger.iter(kinds="holdout.access")
                   if e.payload.get("state") == "opened" and e.agent in lines)

    def graduate(self) -> list[dict[str, Any]]:
        """The fittest gate-passing elites, one at a time, through the House's replay, the sealed
        holdout where it applies, and birth. Passers waiting for a seat go first."""
        settings = self.settings
        out = []
        for row in self._q("SELECT * FROM graduations WHERE state='passed' ORDER BY at"):
            if self.births_last_hour() >= int(settings["max_births_per_hour"]):
                return out
            out.append(self._birth(row["candidate"]))
        budget = int(settings["max_graduations_per_step"])
        # An infrastructure failure is not the candidate's: it may be tried again after an hour.
        tried = {r["candidate"] for r in self._q("SELECT candidate FROM graduations WHERE state!='replay_unavailable' OR at>=?",
                                                  (self._now() - 3600,))}
        # Seeds are parents, never graduates: a living agent's own program, a card or a founder has had
        # its own chance. Neither is a program a living agent already runs.
        running = {a.code_sha256 for a in self.house.registry.living()}
        for row in self.elites():
            if budget <= 0 or self.births_last_hour() >= int(settings["max_births_per_hour"]):
                break
            if (row["id"] in tried or not row["gate"] or row["origin"] == "seed" or row["code_sha256"] in running
                    or self._desk(row["niche"]) is None):
                continue
            budget -= 1
            out.append(self._graduate_one(row))
        return out

    def _names(self, row: Mapping[str, Any]) -> tuple[str, str]:
        niche = self.house.niches[row["niche"]]
        desk = niche.desk or row["niche"].split("-", 1)[-1]
        line = f"{desk}-l{row['id'][:6]}"[:34]
        root = hashlib.sha256(str(row["lineage"]).encode()).hexdigest()[:6]
        family = f"{row['niche'].split('-', 1)[-1]}-lab-{root}"[:40]
        return line, family

    def _record(self, row: Mapping[str, Any], state: str, detail: str, *, line: str, family: str, agent: str | None = None,
                needs: Any = None, params: Any = None, table_state: str | None = None) -> dict[str, Any]:
        """One graduation outcome: the lab's row (its state decides what is tried next) and a private
        `lab.graduate` ledger row, once per candidate and outcome, carrying the authorship."""
        from .ledger import LedgerConflict

        self._x("INSERT INTO graduations(candidate, niche, lineage, line, family, state, agent, at, detail, needs, params)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(candidate) DO UPDATE SET state=excluded.state, agent=excluded.agent,"
                " at=excluded.at, detail=excluded.detail, needs=COALESCE(excluded.needs, graduations.needs),"
                " params=COALESCE(excluded.params, graduations.params)",
                (row["id"], row["niche"], row["lineage"], line, family, table_state or state, agent, self._now(), str(detail)[:600],
                 json.dumps(needs, sort_keys=True) if needs is not None else None,
                 json.dumps(params, sort_keys=True) if params is not None else None))
        payload = {"candidate": row["id"], "state": state, "detail": str(detail)[:600], "niche": row["niche"], "line": line,
                   "family": family, "lineage": row["lineage"], "origin": row["origin"], "author": row["author"],
                   "parents": json.loads(row["parents"] or "[]"), "idea": str(row["idea"] or "")[:400], "fitness": row["fitness"],
                   "cell": row["cell"], "agent": agent, "prompt_version": PROMPT_VERSION,
                   "lab_evaluations_in_lineage": int(self._q("SELECT COUNT(*) AS n FROM candidates WHERE lineage=? AND status!='queued'",
                                                             (row["lineage"],))[0]["n"])}
        key = f"lab.graduate:{row['id']}:{state}"
        if self.house.ledger.get(key) is None:
            try:
                self.house.ledger.append("lab.graduate", payload, id=key)
            except LedgerConflict:
                pass  # written by an earlier step with other counts: the first stands
        return payload

    def _virtual(self, row: Mapping[str, Any], line: str, family: str) -> Any:
        from .agents import Agent, niche_of

        needs = json.loads(row["needs"])
        venue, horizon, style = niche_of(needs)
        return Agent(id=line, name=line, family=family, venue=venue, horizon=horizon, style=style, generation=1, parent=None,
                     code=row["code"], params={}, wake_minutes=15, born_at=now_iso(self.house.clock), needs=needs,
                     specialty=row["niche"], line=line, founder=None)

    def _graduate_one(self, row: Mapping[str, Any]) -> dict[str, Any]:
        house = self.house
        line, family = self._names(row)
        if house.registry.get(line) is not None:
            return self._record(row, "refused", f"the line {line} already exists", line=line, family=family)
        if self._deep(row) and house.settings.holdout_gate and self._lineage_holdouts(row["lineage"]) >= int(house.settings.holdout_lineage_budget):
            # Many lines of one lineage must not be a way to probe the sealed window: the lineage's
            # budget is the House's per-line budget, counted over all of its lines.
            return self._record(row, "holdout_rationed",
                                f"the lab lineage {row['lineage']} has spent its {house.settings.holdout_lineage_budget} sealed-holdout evaluations",
                                line=line, family=family)
        agent = self._virtual(row, line, family)
        result = house._candidate_replay(agent, row["code"])
        if not result.get("counted_as_trial") or not result.get("passed"):
            try:
                house.sandbox.retire(line)
            except Exception:  # noqa: BLE001 - a box already gone is gone
                pass
            reasons = "; ".join(str(r) for r in ((result.get("numbers") or {}).get("reasons") or [])[:3])
            state = "replay_failed" if result.get("counted_as_trial") else "replay_unavailable"
            return self._record(row, state, reasons or str(result.get("error") or "the House's replay did not pass"), line=line, family=family)
        needs, params = result.get("needs") or json.loads(row["needs"]), result.get("params") or {}
        if "walk_forward" in result and house.settings.holdout_gate:
            holdout = house._holdout(agent, row["code"], needs, params)
            if not (holdout.get("evaluated") and holdout.get("passed")):
                try:
                    house.sandbox.retire(line)
                except Exception:  # noqa: BLE001
                    pass
                detail = (f"the sealed holdout refused it: {holdout.get('refused')}" if not holdout.get("evaluated")
                          else "its development replay passed, but the sealed holdout did not")
                return self._record(row, "holdout_failed", detail, line=line, family=family)
        self._record(row, "passed", "passed the House's replay" + (" and the sealed holdout" if "walk_forward" in result else ""),
                     line=line, family=family, needs=needs, params=params)
        return self._birth(row["id"])

    def _deep(self, row: Mapping[str, Any]) -> bool:
        """Was this candidate searched on the history store's development window?"""
        for _, tape_id, tape in self._tapes.values():
            if tape_id == row["tape_id"]:
                return bool((tape.get("source") or {}).get("window"))
        needs = json.loads(row["needs"])
        return needs.get("venue") == "alpaca" and bool(self.house.settings.deep_replay) and not self.house._feeds_wanted(needs)

    def _birth(self, ident: str) -> dict[str, Any]:
        """Born on paper exactly as a replay-passing foundry card is: `spawn` with the House's
        endowment on the desk, seated on rung 1 with its code marked as tried, displacing the
        desk's (or the league's) weakest eligible agent when full. Waits when nobody may be displaced."""
        house = self.house
        row = self._q("SELECT * FROM candidates WHERE id=?", (ident,))[0]
        grad = self._q("SELECT * FROM graduations WHERE candidate=?", (ident,))[0]
        line, family = grad["line"], grad["family"]
        niche = house.niches.get(row["niche"])
        rules = house.game["economy"]
        with house._lifecycle_lock:
            living = house.registry.living()
            displaced = None
            if niche is None or niche.dormant:
                return self._record(row, "refused", "its desk is closed", line=line, family=family)
            if sum(1 for a in living if a.specialty == niche.id) >= niche.max_members:
                displaced = house._weakest(rules, specialty=niche.id)
                if displaced is None:
                    return self._record(row, "waiting_seat", "its desk is full of agents that have earned their seats",
                                        line=line, family=family, table_state="passed")
            elif len(living) >= int(rules["max_population"]):
                displaced = house._weakest(rules)
                if displaced is None:
                    return self._record(row, "waiting_seat", "the league is full of agents that have earned their seats",
                                        line=line, family=family, table_state="passed")
            params = json.loads(grad["params"] or "{}")
            passed = house.ledger.get(f"lab.graduate:{ident}:passed")
            sealed = passed is not None and "holdout" in str(passed.payload.get("detail") or "")
            why = (f"an Alpha Lab graduate ({row['origin']}, by {row['author']}, lineage {row['lineage']}): {str(row['idea'] or '')[:220]} "
                   f"-- fittest in its cell ({row['cell']}) at {float(row['fitness'] or 0):+.6f} a block out of sample on the lab's "
                   f"search tape, then passed the House's replay{' and the sealed holdout' if sealed else ''}")
            try:
                child = house.spawn(line, family, row["code"], reason=why[:1500], params=params, endowment=rules["endowment_usd"],
                                    specialty=niche.id, founder=f"lab:{row['lineage']}"[:120])
            except ValueError as exc:
                return self._record(row, "refused_at_birth", str(exc), line=line, family=family)
            seated = child.id == line and child.code_sha256 == row["code_sha256"]
            if seated:
                house.evaluator.seat(child.id, 1, f"an Alpha Lab graduate: candidate {ident} passed the House's replay before birth, on its own line")
                with house._state_lock:
                    house._state["tried"][child.id] = child.code_sha256
                house.seat(child)
            evidence = {"candidate": ident, "lineage": row["lineage"], "origin": row["origin"], "author": row["author"],
                        "cell": row["cell"], "fitness": row["fitness"], "replay_passed": True, "holdout_passed": sealed,
                        "seated_on_paper": seated, "displaced": displaced.id if displaced is not None else None}
            if house.ledger.get(f"birth-route:{child.id}") is None:  # before the foundry's labeller can call it something else
                house.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": "lab", "model": None,
                                                       "reason": f"an Alpha Lab graduate for {niche.id}", "evidence": evidence},
                                    id=f"birth-route:{child.id}")
            if displaced is not None and displaced.alive:
                house.kill(displaced, "displaced", house.postmortem(displaced, "displaced",
                           "an Alpha Lab graduate that passed the House's replay takes the seat of the weakest eligible agent"))
        return self._record(row, "born", f"born as {child.id}" + ("" if seated else " (not seated: its probe read other NEEDS)"),
                            line=line, family=family, agent=child.id)

    # ------------------------------------------------------------- royalties
    def royalties(self) -> int:
        """10% (`royalty_share`) of each performance fee a lab graduate earns goes to the lab's line:
        the graduate is charged it (the fee's royalty to its author) and a `lab.royalty` row records
        it. Idempotent per fee: both ids derive from the fee's ledger id."""
        share = Decimal(str(self.settings["royalty_share"]))
        cursor = int(self._meta("fee_cursor") or 0)
        graduates = {a.id: a for a in self.house.registry.agents.values() if str(a.founder or "").startswith("lab:")}
        paid = 0
        last = cursor
        for entry in self.house.ledger.iter(kinds="credit.grant", after=cursor):
            last = entry.seq
            p = entry.payload
            what = str(p.get("what") or p.get("reason") or "").lower()
            if entry.agent not in graduates or not what.startswith("performance fee"):
                continue
            fee = Decimal(str(p.get("usd") or 0))
            royalty = (fee * share).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
            if royalty <= 0:
                continue
            lineage = str(graduates[entry.agent].founder)[4:]
            self.house.economy.charge(entry.agent, royalty, "royalty to the Alpha Lab", detail={"fee": entry.id, "lineage": lineage},
                                      id=f"lab-royalty-charge:{entry.id}")
            self.house.ledger.append("lab.royalty", {"fee": entry.id, "agent": entry.agent, "lineage": lineage,
                                                     "fee_usd": format(fee, "f"), "usd": format(royalty, "f"),
                                                     "share": format(share, "f")}, id=f"lab.royalty:{entry.id}")
            paid += 1
        if last != cursor:
            self._set_meta("fee_cursor", str(last))
            self._weights = None
        return paid

    # ------------------------------------------------------------- researchers
    def _brief(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """One program in a line: what an agent is shown of a program not its own."""
        summary = json.loads(row["summary"] or "{}")
        return {"id": row["id"][:12], "idea": str(row["idea"] or "")[:200], "origin": row["origin"], "author": row["author"],
                "fitness": None if row["fitness"] is None else round(float(row["fitness"]), 8),
                "trades": row["trades"], "trades_per_day": summary.get("trades_per_day"), "return_pct": summary.get("return_pct"),
                "max_drawdown": summary.get("max_drawdown"), "cell": describe_cell(row["cell"]) if row["cell"] else None}

    def query(self, agent: Any) -> dict[str, Any]:
        """`lab_query`: the archive and leaderboard for the agent's desk, and its own submissions.
        Words and numbers; nobody's code is shown, not even its own (it has it)."""
        niche = agent.specialty or ""
        born = {r["candidate"]: r["agent"] for r in self._q("SELECT candidate, agent FROM graduations WHERE niche=? AND state='born'", (niche,))}
        cells = [{**self._brief(r), "graduated_as": born.get(r["id"])} for r in self.elites(niche)[:20]]
        board = [self._brief(r) for r in self._q("SELECT * FROM candidates WHERE niche=? AND eligible=1 ORDER BY fitness DESC LIMIT 10", (niche,))]
        since = self._now() - 86400
        stats = self._q("SELECT COUNT(*) AS n, SUM(eligible) AS e, SUM(gate) AS g FROM candidates WHERE niche=? AND evaluated>=?", (niche, since))[0]
        archived = {r["candidate"] for r in self._q("SELECT candidate FROM archive WHERE niche=?", (niche,))}
        own = []
        for r in self._q("SELECT * FROM candidates WHERE author=? AND origin='agent' ORDER BY created DESC LIMIT 8", (agent.id,)):
            summary = json.loads(r["summary"] or "{}")
            own.append({**self._brief(r), "code_sha256": r["code_sha256"], "status": r["status"], "error": r["error"],
                        "passes_gate_numbers": bool(r["gate"]), "archived": r["id"] in archived, "graduated_as": born.get(r["id"]),
                        "submitted_at": now_iso(lambda created=r["created"]: created),
                        "results": {k: summary.get(k) for k in ("oos_mean_log_growth", "oos_active_blocks", "in_sample_mean_log_growth",
                                                                 "fees_usd", "folds", "reasons", "refusal_reasons", "last_error")}})
        desk = self._desk(niche)
        return {
            "desk": niche,
            "archive": cells,
            "coverage": {"filled_cells": len(self.elites(niche)),
                         "cells_in_grid": len(TPD_LABELS) * len(CORR_LABELS) * len(desk.horizons if desk is not None else ()),
                         "evaluated_24h": int(stats["n"] or 0), "eligible_24h": int(stats["e"] or 0), "gate_24h": int(stats["g"] or 0)},
            "leaderboard": board,
            "your_submissions": own,
            "note": ("Development results on the lab's search tape: the first two thirds of the tape the House replays this desk on. "
                     "Fitness is out-of-sample mean log growth per block after fees; a program needs the replay gate's trades and "
                     "blocks to be scored. The fittest program of a cell that clears the gate's numbers is replayed by the House on "
                     "the whole tape (its last third unseen by any search) and, on the history store, by the sealed holdout; only "
                     "then is it born. Nothing here is a trial against you: to adopt or fork a program you still `replay` it."),
        }

    def submit(self, agent: Any, candidates: Sequence[Any]) -> dict[str, Any]:
        """`lab_submit`: queue up to `submit_max` of the agent's programs for the next batch. Each
        passes the same checks as any candidate; none is a trial against its line."""
        limit = int(self.settings["submit_max"])
        niche = self._desk(agent.specialty or "")
        if niche is None:
            return {"error": "the lab searches desks the House can replay; yours is not one of them"}
        waiting = int(self._q("SELECT COUNT(*) AS n FROM candidates WHERE author=? AND origin='agent' AND status='queued'",
                              (agent.id,))[0]["n"])
        queued, refused = [], []
        for raw in list(candidates or [])[: max(0, limit)]:
            if waiting + len(queued) >= limit:
                refused.append({"error": f"you already have {limit} programs waiting for the lab"})
                break
            code, idea = (raw.get("code"), raw.get("idea") or raw.get("purpose") or "") if isinstance(raw, Mapping) else (raw, "")
            try:
                ident = self.admit(str(code or ""), niche=niche, origin="agent", author=agent.id, lineage=f"agent:{agent.id}", idea=str(idea))
                queued.append(ident)
            except LabError as exc:
                refused.append({"error": str(exc)[:300]})
        if len(list(candidates or [])) > limit:
            refused.append({"error": f"at most {limit} programs a submission; the rest were not read"})
        return {"queued": queued, "refused": refused, "queue_ahead": self.queued(),
                "note": "not a trial and not adopted: the lab evaluates them on its search tape in its next batches. "
                        "Call lab_query in a later pass for the results."}

    # ---------------------------------------------------------------- stats
    def stats(self, window: float = 3600.0) -> dict[str, Any]:
        """Throughput, pass rates per stage, coverage, graduates and spend over the last `window`."""
        since = self._now() - window
        batch = self._q("SELECT COUNT(*) AS b, COALESCE(SUM(candidates),0) AS n, COALESCE(SUM(ok),0) AS ok, COALESCE(SUM(eligible),0) AS e,"
                        " COALESCE(SUM(gate),0) AS g, COALESCE(SUM(archived),0) AS a, COALESCE(SUM(seconds),0) AS s FROM batches WHERE at>=?",
                        (since,))[0]
        sail = sum((Decimal(r["sail_usd"]) for r in self._q("SELECT sail_usd FROM batches WHERE at>=?", (since,))), Decimal(0))
        calls = self._q("SELECT kind, COUNT(*) AS n, COALESCE(SUM(written),0) AS w, COALESCE(SUM(refused),0) AS r FROM calls WHERE at>=? GROUP BY kind", (since,))
        spent = sum((Decimal(r["cost_usd"]) for r in self._q("SELECT cost_usd FROM calls WHERE at>=?", (since,))), Decimal(0))
        grads = {r["state"]: r["n"] for r in self._q("SELECT state, COUNT(*) AS n FROM graduations WHERE at>=? GROUP BY state", (since,))}
        origin = {r["origin"]: r["n"] for r in self._q("SELECT origin, COUNT(*) AS n FROM candidates WHERE created>=? GROUP BY origin", (since,))}
        coverage = {r["niche"]: r["n"] for r in self._q("SELECT niche, COUNT(*) AS n FROM archive GROUP BY niche")}
        evaluated = int(batch["n"] or 0)
        return {
            "window_seconds": window, "batches": int(batch["b"] or 0), "evaluated": evaluated,
            "per_hour": round(evaluated * 3600.0 / window, 1),
            "candidates_per_box_second": round(evaluated / float(batch["s"]), 3) if batch["s"] else None,
            "stages": {"written": origin, "ran": int(batch["ok"] or 0), "eligible": int(batch["e"] or 0), "gate": int(batch["g"] or 0),
                       "archived": int(batch["a"] or 0), "graduations": grads},
            "pass_rates": {"ran": round(int(batch["ok"] or 0) / evaluated, 4) if evaluated else None,
                           "eligible": round(int(batch["e"] or 0) / evaluated, 4) if evaluated else None,
                           "gate": round(int(batch["g"] or 0) / evaluated, 4) if evaluated else None},
            "calls": {r["kind"]: {"calls": r["n"], "written": r["w"], "refused": r["r"]} for r in calls},
            "coverage": {"cells": sum(coverage.values()), "by_desk": coverage},
            "queued": self.queued(), "spend": {"openai_usd": format(spent, "f"), "sail_usd_estimate": format(sail.quantize(Decimal("0.0001")), "f"),
                                              "royalty_balance_usd": format(self.royalty_balance(), "f")},
            "born_total": int(self._q("SELECT COUNT(*) AS n FROM graduations WHERE state='born'")[0]["n"]),
            "refusal": self.refusal or None,
        }

    def publish(self, *, force: bool = False) -> dict[str, Any] | None:
        """A private `lab.stats` row at most every `stats_every_minutes`: what the watch reads."""
        every = float(self.settings["stats_every_minutes"]) * 60
        last = float(self._meta("published_at") or 0)
        if not force and self._now() - last < every:
            return None
        self._set_meta("published_at", str(self._now()))
        stats = self.stats()
        self.house.ledger.append("lab.stats", json.loads(json.dumps(stats, default=str)))
        return stats


# ------------------------------------------------------------------------------- the House's wiring

def attach(house: Any) -> None:
    """Wire the lab into a House: the lab itself when `game.json` `lab.enabled` and a lab box is
    configured (`Settings.lab_box`), its tools for researchers, and longer sessions for agents with
    evidence (whether or not the lab runs)."""
    house.lab = None
    if (house.game.get("lab") or {}).get("enabled") and str(getattr(house.settings, "lab_box", "") or ""):
        house.lab = Lab(house)
    if house.researcher is not None:
        house.researcher.lab = house.lab
        house.researcher.evidence = lambda agent: has_evidence(house, agent)
