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
never shown to the lab's search, so when a winner is graduated, the House's own replay judges its
out-of-sample third on history no selection in the lab touched. An agent's own `replay` does see
the whole tape, so a program that grew from an agent's line (its seeded program, a mutant of it,
its `lab_submit`) is judged against every trial on that line, as the agent's own child would be.

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
   House itself (`House._candidate_replay`: the sealed NEEDS probe, a counted trial judged against its
   whole selection path -- its lab lineage's earlier lines and the agent, card or founder line it
   grew from, whose descendant it is born) and, when that tape is the history store's development
   window, sent to the sealed holdout through `House._holdout` -- the one door, with its per-version
   and per-lineage rationing keyed by that path's root, plus a per-lab-lineage budget here so that
   many lines of one lineage cannot probe it. While a line living on that root is judged by the
   seal, the lab never spends the root's last `holdout_reserve` evaluations: they are what lets
   the living line fork and grow. A survivor is born
   with `founder="lab:<lineage>"` and seated on paper exactly as a replay-passing foundry card is,
   at most `max_births_per_hour`, under the league's population and desk caps.
6. Royalties: 10% of the performance fee a graduate earns on realized real profit is paid to the
   lab's compute line (idempotent per fee), and lineages whose graduates lose are searched less.

Spend: OpenAI through the lab's own line (`budget_usd_per_hour`, plus royalties), inside the House's
campaign allowance (every call reserves through the same metered `Frontier` client and its spend
guard) and only while the frontier tier is "all"; the lab box's Sail time is recorded as it runs and
stops with the Sail allowance. Only Luna and Sol spend OpenAI: below the "all" tier they are skipped
(`breed`, `_llm_pause`) and the rest of the loop -- seeds, parameter children, batches on the lab
box, graduation -- goes on (Sept 23, 2026, C2: `open()` used to stop the whole lab with the tier,
which the House's OpenAI line was to fall under that evening with the month resetting on Oct 1).

The lab watches itself (`_watch`, on every tick, Sept 23, 2026): closed for longer than
`closed_alert_minutes` it says so once (a warning naming the refusal, an info when it works again;
the since-when lives in `meta`, so a restart does not reset it), and a graduate that has waited for a
seat longer than `seat_wait_alert_hours` is named once. `health()` is the lab's line in health.json.

**The step says why it failed, and no candidate stops it (D1, Sept 24, 2026).** From 23:21:59Z Sept
23 the step failed every one to three minutes with "IndexError: list index out of range" and nothing
escalated: one queued Luna child asked for ADA/USD alone, whose hourly development window the history
store had fetched and found empty (ADA/USD trades on Alpaca from Feb 2026), and `_search_tape` read
the first step of a tape that had none. Now a tape with no steps is unsupported input, and its row is
blocked like any other; anything else a queued row's NEEDS, tape or result raises blocks that row
(`_block_row`, at most `row_errors_per_step` a step) and the step goes on. Each phase of the step is
guarded on its own (`_guarded`): its warning names the `phase` and carries the traceback
(`_traceback`, private), and the phases after it still run. `failures_alert_after` failed steps in a
row raise one error alert and set `failing_since` in health.json (kept in `meta`, so a restart does
not reset it); a step that works again clears it with an info. The lab's tape index (tape key ->
when it was built, the lab's tape id, the House's tape id, its source) is kept in `meta` too, so
after a restart `ready_queued` counts the rows whose tape the House holds or rebuilds from its own
disk, and the step evaluates before it breeds.

**Forward windows (S2, Sept 23, 2026).** Every `forward_every_minutes` the lab replays its archived
elites and its graduates waiting for seats (`forward_windows`) on tape data that arrived AFTER their
code was frozen: the tape is cut at the hour after the candidate's evaluation (or its graduation),
so no search, no House replay and no holdout has seen a step of it. Since Sept 24, 2026 (S2 of the
close-the-gaps run) every living resident's current program is scored too, its window cut after the
program was frozen (its birth or its latest rewrite), so the House's seat market can compare a
newcomer's forward score with the resident's own record (`resident_forward`) before a trader's seat
is taken. Replay fills, on the lab box's
lane, bounded per run. The record (`forward` table, one row per candidate and run, never the
archive's fitness) RANKS: seats (`forward_score`, which the House's seat market reads), the archive's
cell ordering (`elites`: a program whose forward window wins comes before every untested one, one
whose window loses after them) and the breeding weights (`lineage_weights`: a lineage whose forward
record loses gets fewer children). It never counts as practice evidence, never promotes anyone,
never writes to the ledger's `eval.*` or `holdout.*` kinds and never changes a gate result. The
study behind it (Sept 23, 17:05Z): replay did not predict practice (0 of 20 passes positive after
6 active blocks, Spearman -0.68), so new data ranks and old data only admits.

The floor feeds back the same way: a born graduate's practice and real record (the allocator's
board) moves its lineage's search share, within the documented bounds of `lineage_weights`. And
the teacher's lessons are priors (`priors`): a lesson may carry a ```lab-prior``` block naming a
family, lineage, desk or cell and a rule, and the lab honours it (`pause-param-forks` breeds no
parameter mutant of the named lineages until their forward window is positive).

Tapes are keyed by what they depend on (`tape_key`: NEEDS without `style`, `parameter_rules`,
`wake_minutes` and `max_hours_to_close`), since Sept 23, 2026: keyed by the whole NEEDS, every
Luna child (which always differs from its parent in `style`, and usually in `parameter_rules`)
looked like a tape of its own, cost one of the step's few tape builds and never reached a batch
while its parent's tape sat in the cache: 0 of 394 LLM-written children were ever evaluated.

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
import traceback
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .constitution import CONSTITUTION
from .ledger import now_iso

#: The background job the tick schedules (`House._background`): the replay lane, beside the
#: agents' own replays and the foundry's card evaluations, never the ops lane Merton, the backup
#: and the updater share. A colon cannot be in an agent id, so it cannot collide with `replay:<agent>`.
LAB_JOB = "replay:lab:step"

PROMPT_VERSION = "lab-2026-09-24.1"

#: The dials, overridden by `game.json` `lab`.
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # OpenAI: Luna's mutations and Sol's leaps, per trailing hour, before royalties.
    "budget_usd_per_hour": "1.50",
    # The lab box's price, for the record of what its Sail time cost (the box is one machine: it
    # cannot run more than an hour an hour).
    "box_usd_per_hour": "0.20",
    "batch_size": 32,
    # E1 (the close-the-gaps run, Sept 24, 2026): the share of each batch reserved for the programs someone
    # wrote (`RESERVED_ORIGINS`: an agent's submission, Luna's and Sol's) whenever any wait on the chosen tape
    # (`reserved_quota`, held to `RESERVED_SHARE_BOUNDS`). It was a third.
    "reserved_share": 0.5,
    "param_children": 16,
    "llm_children": 6,
    "leap_every": 10,
    "leap_candidates": 4,
    "search_fraction": 0.66,
    "step_seconds": 240,
    "max_births_per_hour": 6,
    "max_graduations_per_step": 1,
    # Sealed-holdout evaluations of a lineage root that the lab never spends while a line living on
    # that root is judged by the seal: its forks and new versions keep them (`Lab._holdout_refusal`).
    "holdout_reserve": 1,
    "submit_max": 8,
    "royalty_share": "0.10",
    "min_overlap": 8,
    "timeout": 600,
    "max_tapes_per_step": 4,
    "seed_every_minutes": 60,
    "max_queue": 600,
    "stats_every_minutes": 10,
    # The lab's own invariants (Sept 23, 2026): one warning when it has been closed this long, one
    # when a graduate has waited this long for a seat.
    "closed_alert_minutes": 30,
    "seat_wait_alert_hours": 6,
    # D1 (Sept 24, 2026): this many failed steps in a row raise one error alert (`_note_step`); a
    # queued row the lab cannot handle is blocked, at most this many a step before the step fails
    # instead (`_block_row`: a defect that breaks every row is the lab's, not the rows').
    "failures_alert_after": 5,
    "row_errors_per_step": 8,
    # Forward windows (S2, Sept 23, 2026): every `forward_every_minutes`, at most
    # `forward_candidates_per_run` archived elites and waiting graduates (least recently scored
    # first) are replayed on tape data that arrived after their code was frozen, on the lab box, for
    # at most `forward_box_seconds` of its time a run; a live tape the lab builds for the forward
    # window (the deep-replay Alpaca desks, whose House tape is history) covers the last
    # `forward_days` days and is rebuilt at most once a run. A forward record ranks only with
    # `forward_min_active_blocks` active blocks; the floor's practice record counts from
    # `forward_min_trades` closed trades. Cost, from the box's measured rates that day (11 candidates
    # a second on Kalshi tapes, 1.7 on crypto) and windows a tenth of a search tape: 48 candidates
    # are some 5-30 box-seconds an hour, under a cent of Sail at $0.20 an hour. But the budget is the
    # run's own time, and the tapes it builds fill it: measured Sept 23 (22:11Z, 23:14Z), a run scored
    # 4 and 5 of its 48 due and skipped the rest when its 90 s were spent.
    "forward_every_minutes": 60,
    "forward_candidates_per_run": 48,
    "forward_box_seconds": 90,
    "forward_days": 7,
    "forward_min_active_blocks": 3,
    "forward_min_trades": 3,
    # S2 (the close-the-gaps run, Sept 24, 2026): every living resident's current program is scored too, in
    # the run's own budget, its window cut after its program was frozen on a grid of this many hours, so
    # the residents of one tape frozen within a few hours share one batch (a window a few hours shorter,
    # of the days a resident has lived).
    "forward_resident_cut_hours": 6,
    # A tape the House fails to build the same way this many hourly tries in a row is unsupported input and
    # its rows are blocked (Sept 24, 2026: three submissions failed every hour and sat at the queue's front).
    "tape_failures_before_block": 12,
    # E1 (the close-the-gaps run, Sept 24, 2026): no graduate is born onto a desk whose members were offered
    # markets for this many hours and wrote no intent, unless a feed the desk asked for arrived in that time
    # (`_idle_desk`; the attention desk went 48 h without an intent at T0 and still received graduates). 0 is off.
    "idle_desk_hours": 48,
    # The deep-market desks (E1): Sol's leaps go to them first (`leap`). game.json names them.
    "deep_desks": [],
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

#: Queue order: an agent's own submissions first, then seeds (the archive needs its first elites)
#: and the LLM-written children beside them, then parameter mutants. Sept 23, 2026: at priority 2
#: behind the parameter mutants, which share their elite's tape and arrive in dozens, none of the
#: lab's 394 Luna and Sol children was evaluated in its first six hours.
PRIORITY = {"agent": 0, "seed": 1, "param": 2, "luna": 1, "sol": 1}
#: The origins `reserved_share` of every batch is reserved for (`_next_batch`), when any wait on its
#: tape: the programs someone wrote, against the free mutants of what is already in the archive.
RESERVED_ORIGINS = ("agent", "luna", "sol")
#: `lab.reserved_share` as the plan bounds it (docs/goals/LTCM_CLOSE_THE_GAPS.md, "Risk-free dials"; `game.json`
#: `lab_bounds` says the same and `economy.check_bounds` refuses a game file outside it): enforced where it is read.
RESERVED_SHARE_BOUNDS = (0.33, 0.75)
#: NEEDS keys the House's tape never depends on (`House.tape_for` reads none of them): two programs
#: that differ only here replay on one tape, and are cached and batched as one (`tape_key`).
TAPE_KEY_IGNORED = ("style", "parameter_rules", "wake_minutes", "max_hours_to_close")
#: How the toolsmith answers a tool request it cannot build (`Commons.fulfil`, and `Merton._fulfil_deployed`
#: when the answer rides a merged change): a `tool.fulfilled` row whose outcome begins with these words is a
#: refusal, whatever its `status` (`Commons._requests` folds the 'answered' ones as blocked; the 'deployed'
#: ones of Sept 22, 2026, 15:29Z say "BLOCKED" in the same words). No feed arrived (`Lab._feed_arrived`).
DECLINED = "cannot be a pure tool"
#: How long a search tape is used before it is built again (the House rebuilds its own tapes daily),
#: and how long the tape index (`Lab._tape_index`) keeps a tape the lab built.
SEARCH_TAPE_SECONDS = 6 * 3600
#: Tapes the persisted index keeps at most (its newest); the search copies in memory are six.
TAPE_INDEX_MAX = 64
#: The tail of a traceback an alert carries (`_traceback`, a private key: `ledger.public_view`
#: strips it from everything published).
TRACEBACK_CHARS = 2000
#: What the House's tape reader says when NEEDS ask for more history than it will ever fetch
#: (`league/tapes.py`: at most `MAX_PAGES` pages a read): unsupported input, never re-queued.
TOO_LONG = "ask for a shorter window"

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
CREATE TABLE IF NOT EXISTS forward(
    candidate TEXT NOT NULL, at REAL NOT NULL, window_start REAL NOT NULL, window_end REAL NOT NULL,
    tape_id TEXT NOT NULL, ok INTEGER NOT NULL, blocks INTEGER NOT NULL, active_blocks INTEGER NOT NULL,
    log_growth REAL, mean_log_growth REAL, trades INTEGER, error TEXT, PRIMARY KEY(candidate, at));
"""


class LabError(ValueError):
    """A candidate the lab refuses before it costs anything."""


class SealedTape(LabError):
    """A tape that reaches into the sealed holdout. The lab never evaluates on one."""


# ---------------------------------------------------------------------------------- pure helpers

def _iso(epoch: float) -> str:
    """An epoch as the ledger writes times, to the second."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


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


def tape_key(needs: Mapping[str, Any]) -> str:
    """What decides a program's tape: its NEEDS without the keys the tape never depends on."""
    return json.dumps({k: v for k, v in dict(needs).items() if k not in TAPE_KEY_IGNORED}, sort_keys=True)


def _share(share: Any) -> float:
    low, high = RESERVED_SHARE_BOUNDS
    try:
        return min(max(float(share), low), high)
    except (TypeError, ValueError):
        return low


def batch_turn(turn: int, share: Any) -> str:
    """Whose turn batch number `turn` (1, 2, ...) is (`Lab._next_batch`; E1, Sept 24, 2026): "reserved" for
    `share` of the turns (held to its bounds) -- the tape where the programs someone wrote wait, the most rows
    first -- and the others alternating "queue" (the queue's oldest row: a seed or a lone row keeps its turn)
    and "largest" (the largest group of any origin: the batch the box fills). A step builds at most
    `max_tapes_per_step` tapes, one a turn, so this is also how a step's builds are shared. With the half:
    queue, reserved, largest, reserved, and again."""
    share = _share(share)

    def quota(t: int) -> int:  # ceil(t x share): turn t is reserved when it moves between t and t + 1
        return math.ceil(round(t * share, 9))

    if quota(turn + 1) > quota(turn):
        return "reserved"
    others = turn - (quota(turn + 1) - quota(1))  # the turns up to this one that were not reserved
    return "queue" if others % 2 == 1 else "largest"


def reserved_quota(size: int, share: Any) -> int:
    """How many of a batch's `size` rows the reserved origins may claim first: `share` of it, rounded up,
    at least one; `share` held to `RESERVED_SHARE_BOUNDS` (a game file outside them is refused by CI too)."""
    return max(1, math.ceil(round(int(size) * _share(share), 9)))


#: NEEDS keys that are knobs of how one program runs, not what it is (E1, Sept 24, 2026): a program that
#: differs from another only in these and its PARAMS literal is the same mechanism (`mechanism_digest`).
MECHANISM_IGNORED_NEEDS = TAPE_KEY_IGNORED


def mechanism_digest(code: str) -> str | None:
    """What a program IS, beyond its parameters (E1, the close-the-gaps run, Sept 24, 2026): a digest of
    its syntax tree without the module's PARAMS literal, without any docstring or bare string, and with
    its NEEDS literal read without `MECHANISM_IGNORED_NEEDS` (a style label, parameter bounds, the wake
    cadence, a market window). Two programs with one digest differ only in parameters: a nudge, as 16 of
    the lab's 18 born graduates were at T0 (an impulse floor 0.0006 -> 0.000686). Comments and layout
    never count. None for a file that does not parse."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets):
            continue
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
            try:
                needs = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                needs = None
            if isinstance(needs, dict):
                kept = {k: v for k, v in needs.items() if k not in MECHANISM_IGNORED_NEEDS}
                body.append(ast.parse(f"NEEDS = {json.dumps(kept, sort_keys=True, default=str)!r}").body[0])
                continue
        body.append(node)
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            node.body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                                                      and isinstance(n.value.value, str))] or [ast.Pass()]
    body = [n for n in body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    return hashlib.sha256(ast.dump(ast.Module(body=body, type_ignores=[])).encode()).hexdigest()[:24]


def family_at_capacity(record: Mapping[str, Any] | None, rule: Mapping[str, Any] | None) -> bool:
    """Whether the family ledger says a family is at its measured capacity (E3, Sept 24, 2026), read from
    what `league/families.py` computed, never measured again here: its family swing's stake is held by
    capacity (`swing.limit`), or `families.capacity_holds` says the fill rate at twice its current position
    size is under `capacity_fill_ratio` of the rate at that size, both measured on `capacity_min_markets`
    markets (`record["capacity"]`: its `fill_rates` and `size_usd`). More search on such a family finds
    no more room: the markets it bids are full at the size it can already put in them."""
    from .families import capacity_holds

    if not isinstance(record, Mapping):
        return False
    swing = record.get("swing") if isinstance(record.get("swing"), Mapping) else {}
    if swing.get("limit") == "capacity":
        return True
    cap = record.get("capacity") if isinstance(record.get("capacity"), Mapping) else {}
    try:
        size = float(cap.get("size_usd") or 0.0)
    except (TypeError, ValueError):
        return False
    if rule is None or size <= 0 or not isinstance(cap.get("fill_rates"), Mapping):
        return False
    return capacity_holds(cap["fill_rates"], size, 2 * size, ratio=float(rule.get("capacity_fill_ratio", 0.5)),
                          min_markets=int(rule.get("capacity_min_markets", 5)))


#: The candidates' columns graduation reads for every gate-passing program of a pass (`Lab._graduation_order`):
#: all but the code.
GRADUATION_COLUMNS = ("id, code_sha256, params, needs, niche, venue, horizon, origin, author, lineage, parents, idea, priority,"
                      " created, status, evaluated, tape_id, error, eligible, gate, fitness, trades, trades_per_day, corr, cell, summary")

#: A parent's own forward window in its breeding weight (`Lab._pick_parent`, E1, Sept 24, 2026): a window
#: that wins doubles it, one that loses quarters it, none leaves it; within the lineage weight's bounds.
FORWARD_BREEDING = (2.0, 0.25)


def forward_factor(score: float | None) -> float:
    if score is None:
        return 1.0
    return FORWARD_BREEDING[0] if score > 0 else FORWARD_BREEDING[1]


def forward_cut(tape: Mapping[str, Any], cut: float) -> dict[str, Any] | None:
    """The forward window of a tape: only the steps strictly after `cut` (an epoch), so a replay of
    it sees no step any search, replay or holdout saw. On an Alpaca tape the bars of the steps
    before the cut become warm-up history (the last `replay.MAX_BARS` a symbol), so the first
    decision sees the same bars a live wake would; a Kalshi tape's observed bars and feeds are
    whole series the engine slices by time and stay as they are. None when no step follows the
    cut: there is no forward data yet. The House's cached tape is never mutated."""
    from .replay import MAX_BARS

    before, after = [], []
    for step in tape.get("steps") or []:
        stamp = _ts(step.get("t")) if isinstance(step, Mapping) else None
        (after if stamp is not None and stamp > cut else before).append(step)
    if not after:
        return None
    out = {k: v for k, v in dict(tape).items() if k != "steps"}
    out["steps"] = after
    if str(tape.get("venue") or "") == "alpaca":
        warm: dict[str, list[dict[str, Any]]] = {s: list(rows or []) for s, rows in (tape.get("warmup_bars") or {}).items()}
        for step in before:
            for symbol, bar in (step.get("bars") or {}).items():
                if isinstance(bar, Mapping):
                    warm.setdefault(str(symbol), []).append({**bar, "t": bar.get("t") or step.get("t")})
        out["warmup_bars"] = {s: rows[-MAX_BARS:] for s, rows in warm.items()}
    out["forward_cut"] = _iso(cut)
    return out


PRIOR_BLOCK = re.compile(r"```lab-prior\s*\n(.*?)```", re.S)
PRIOR_RULES = ("pause-param-forks",)


def parse_priors(text: str) -> list[dict[str, Any]]:
    """The lab priors a lesson carries: each ```lab-prior``` block is one JSON object with a `rule`
    (`pause-param-forks`), what it names (`family`, a substring of the House family the lineage
    grew from; `lineage`, a lab lineage; `niche`, a desk; `cell`, a cell prefix) and `until`
    (`forward-positive`, a `YYYY-MM-DD` day, or nothing: for good). Blocks that are not that are
    ignored, never an error: a lesson is prose first."""
    out = []
    for raw in PRIOR_BLOCK.findall(str(text or "")):
        try:
            prior = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(prior, dict) or prior.get("rule") not in PRIOR_RULES:
            continue
        if not any(prior.get(k) for k in ("family", "lineage", "niche", "cell")):
            continue
        out.append({k: (str(v) if v is not None else None) for k, v in prior.items()})
    return out


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
  NEEDS unless your change needs other data: a program on the parent's data runs in the parent's next batch, while
  one with NEEDS of its own waits for a tape of its own (the lab builds a few a step);
- a program that differs from the parent only in PARAMS (or in NEEDS style, parameter_rules, wake_minutes or
  max_hours_to_close) is a nudge: it graduates only when its forward results beat the desk's living programs.
  Change the mechanism;
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
        #: Why Luna and Sol are being skipped ('' when they are asked), and the phases skipped since
        #: this process started: what `stats` and `health` show for the paid work (C2, Sept 23, 2026).
        self._llm_paused = ""
        self._skipped: dict[str, Any] = {"luna": 0, "sol": 0, "since": now_iso(house.clock)}
        self._watch_error = ""
        #: Forward windows (S2): the live tapes the lab builds for them, the last run's numbers, and
        #: the priors' pauses counted since this process started. The record itself is in the store.
        self._forward_tapes: dict[str, tuple[float, str, dict[str, Any]]] = {}
        self._forward_last: dict[str, Any] | None = None
        self._forward_error = ""
        self._priors: tuple[float, list[dict[str, Any]]] | None = None
        self._prior_skips: dict[str, int] = {}
        #: A resident's program's lab id, by (agent, code, parameters) (`resident_candidate`, S2).
        self._resident_ids: dict[tuple[str, str, str], str | None] = {}
        #: E1 (Sept 24, 2026): each desk's idleness as last read (`_idle_desk`: when, and why it is idle or
        #: None), the programs' mechanism digests by code hash (`_twins`), and what the last graduation
        #: pass held back and why (`held`, in `stats` and health.json).
        self._idle: dict[str, tuple[float, str | None]] = {}
        self._digests: dict[str, str | None] = {}
        self._held: dict[str, Any] = {}
        #: D1 (Sept 24, 2026): what the step's phases raised (`_guarded`) and the queued rows it
        #: blocked for an error of the lab's own (`_block_row`), told at the end of each step.
        self._failures: list[dict[str, str]] = []
        self._row_errors: list[dict[str, str]] = []
        #: The tape index: every search tape built in the last `SEARCH_TAPE_SECONDS`, tape key ->
        #: {at, ident, house, source}, persisted in `meta` `tape_index` so a restart keeps it
        #: (`_ready_keys`). The search copies themselves stay in memory (`_tapes`).
        self._tape_index: dict[str, dict[str, Any]] = self._load_tape_index()
        if self._meta("fee_cursor") is None:
            # A graduate cannot exist before the lab, so no older fee can owe it a royalty.
            self._set_meta("fee_cursor", str(house.ledger.head()[0]))
        # Queued rows keep the priority they were admitted with, so a change of `PRIORITY` reaches
        # the queue only if it is re-keyed here (Sept 23, 2026: 394 Luna and Sol children sat
        # queued at the old priority 2). Every stored priority comes from `PRIORITY`, so this is safe.
        for origin, priority in PRIORITY.items():
            self._x("UPDATE candidates SET priority=? WHERE status='queued' AND origin=? AND priority!=?", (priority, origin, priority))

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
        """The lab box's batch evaluator (`league/labbox.py`). On the floor it is the one the service
        built with `LabBox.from_config`, bound to the box `config.json` names (`use_box`). Without
        one, a sandbox that makes real boxes must already hold a box bound under `box_key`: the lab
        never has the sandbox make itself an agent-sized box from the agents' image instead of the
        lab box (a `SandboxError`, which `evaluate_batch` reports as the box's failure). A local
        sandbox (tests, a developer's machine) runs the batch in a subprocess under `box_key`."""
        if self._box is None:
            from .labbox import LabBox
            from .sandbox import SandboxError

            sandbox = self.house.sandbox
            bound = getattr(sandbox, "bound", None)
            if getattr(sandbox, "secure", False) and (bound is None or bound(self.box_key) is None):
                raise SandboxError(f"no lab box is bound under {self.box_key!r}: the service binds league/config.json's "
                                   f"lab.box_id (LabBox.from_config) and hands it to the lab")
            self._box = LabBox(sandbox, box_key=self.box_key, clock=self.house.clock, holdout=self.house.holdout_window)
        return self._box

    def use_box(self, box: Any) -> None:
        """The evaluator the service built for the configured lab box (`LabBox.from_config`); its
        box key is the lab's from now on, so the two can never name different boxes."""
        self._box = box
        self.box_key = str(getattr(box, "box_key", None) or self.box_key)

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
        or out of Sail allowance stops it, and so does a failed lab box. The OpenAI tier does not:
        the lab's search runs on Sail time, and only its Luna and Sol calls are the tier's
        (`_llm_pause`; C2, Sept 23, 2026)."""
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
        budget = getattr(house, "budget", None)
        if budget is not None and getattr(budget, "mode", "open") == "stopped":
            # The Sail meter's monthly line or the reserve that keeps the House box alive (Deploy 3 review).
            return "the Sail meter has stopped the floor"
        if self.box_down():
            return "the lab box failed a batch in the last five minutes"
        return ""

    def tick(self, *, open_for_business: bool) -> bool:
        """Called from `House.tick`: schedules one bounded `step` on a background lane, and runs the
        lab's own watch (`_watch`). Never works on the tick itself."""
        if not open_for_business:
            self.refusal = "the House is not open for business"
            self._watch(self.refusal)
            return False
        job = self.house._jobs.get(LAB_JOB)
        if job is not None and job.is_alive():
            self._watch(None)  # a step is running: the lab is not closed, whatever `refusal` says of its paid calls
            return False
        self.refusal = self.open()
        self._watch(self.refusal)
        if self.refusal:
            return False
        return bool(self.house._background(LAB_JOB, self.step))

    # ----------------------------------------------------------------- watch
    def _watch(self, closed: str | None) -> None:
        """The lab's two invariants (Sept 23, 2026), checked on every tick and each told once: closed
        for longer than `closed_alert_minutes` (`closed` is why, '' when it works now, None when a
        step is running and the question is not asked), and a graduate waiting for a seat longer than
        `seat_wait_alert_hours`. Never raises into the tick (`House.tick` calls `tick` bare); a
        failure is told once per distinct message."""
        try:
            if closed is not None:
                self._watch_closed(closed)
            self._watch_waiting()
        except Exception as exc:  # noqa: BLE001 - the watch must never take the tick down
            text = f"the lab's watch failed ({type(exc).__name__}: {str(exc)[:160]})"
            if text != self._watch_error:
                self._watch_error = text
                self.house.alert("warning", text)

    def _watch_closed(self, refusal: str) -> None:
        """Since when the lab has been closed is `meta` `closed_since` (a restart does not reset it:
        a deploy's own minutes closed count), `closed_told` once the warning went out."""
        now = self._now()
        since = self._meta("closed_since")
        if refusal:
            if since is None:
                self._set_meta("closed_since", str(now))
                return
            minutes = (now - float(since)) / 60
            if minutes >= float(self.settings["closed_alert_minutes"]) and self._meta("closed_told") is None:
                self._set_meta("closed_told", str(now))
                self.house.alert("warning", f"the Alpha Lab has been closed for {minutes:.0f} minutes (since {_iso(float(since))}): {refusal}")
            return
        if since is None:
            return
        told = self._meta("closed_told")
        self._x("DELETE FROM meta WHERE key IN ('closed_since', 'closed_told')")
        if told is not None:
            self.house.alert("info", f"the Alpha Lab is open again after {(now - float(since)) / 60:.0f} minutes closed")

    def _watch_waiting(self) -> None:
        """One warning per graduate that has waited `seat_wait_alert_hours` for a seat (`meta`
        `seat_told:<candidate>` keeps it to one across restarts)."""
        limit = float(self.settings["seat_wait_alert_hours"])
        for row in self.waiting():
            if row["hours"] < limit or self._meta(f"seat_told:{row['candidate']}") is not None:
                continue
            self._set_meta(f"seat_told:{row['candidate']}", str(self._now()))
            self.house.alert("warning", f"the Alpha Lab graduate {row['line']} ({row['candidate'][:12]}, {row['niche']}) has waited "
                                        f"{row['hours']:.1f} hours for a seat: {row['detail']}")

    def waiting(self) -> list[dict[str, Any]]:
        """Graduates that passed the House's replay and wait for a seat (`waiting_seat`: their desk or
        the league is full of agents that have earned their seats), longest wait first. The wait is
        counted from the ledger's `lab.graduate:<id>:passed` row, written once: the table's `at`
        moves at every retry (`graduate` asks again every ten minutes)."""
        from .house import _epoch

        now = self._now()
        out = []
        for row in self._q("SELECT candidate, niche, line, at, detail FROM graduations WHERE state='passed' AND detail LIKE '%earned their seats%'"):
            passed = self.house.ledger.get(f"lab.graduate:{row['candidate']}:passed")
            since = _epoch(passed.at) if passed is not None else float(row["at"])
            out.append({"candidate": row["candidate"], "line": row["line"], "niche": row["niche"], "since": _iso(since),
                        "hours": round(max(0.0, now - since) / 3600, 1), "detail": row["detail"],
                        "forward": self.forward_score(row["candidate"])})
        return sorted(out, key=lambda r: -r["hours"])

    def health(self) -> dict[str, Any]:
        """The lab's line in health.json (`House._health`, every tick): whether it may work now and
        why not, since when it has been closed, whether its step is failing (`failing_since`, set
        after `failures_alert_after` failures in a row; `failures_in_a_row`; the last `error`), the
        paid phases skipped and why, the graduates waiting for seats, and its tapes (search copies in
        memory, tapes in the persisted index). Cheap (a few small queries, no lock the House's tape
        builds hold), and never raises."""
        try:
            since = self._meta("closed_since")
            waiting = self.waiting()
            return {
                "refusal": self.refusal or None,
                "closed_since": _iso(float(since)) if since is not None else None,
                "closed_minutes": round((self._now() - float(since)) / 60, 1) if since is not None else 0,
                **self._failing(),
                "tapes": {"search_copies": len(self._tapes), "indexed": len(self._tape_index)},
                "llm": {"paused": self._llm_paused or None, "skipped": dict(self._skipped)},
                "waiting_seat": {"count": len(waiting), "longest_hours": waiting[0]["hours"] if waiting else 0,
                                 "graduates": [{k: r[k] for k in ("candidate", "line", "niche", "since", "hours", "forward")} for r in waiting[:8]]},
                "queued": self.queued(),
                "born_total": int(self._q("SELECT COUNT(*) AS n FROM graduations WHERE state='born'")[0]["n"]),
                "forward": self.forward_stats(),
                # E1 (Sept 24, 2026): what the last graduation pass held back, by reason (`_hold`).
                "held": self._held or None,
            }
        except Exception as exc:  # noqa: BLE001 - health is written on the tick
            return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    def step(self) -> dict[str, Any]:
        """One bounded pass: collect royalties, seed, breed, evaluate in batches until
        `step_seconds`, graduate, run the forward windows, publish. Never raises into its lane.

        Each phase is guarded on its own (D1, Sept 24, 2026; `_guarded`): a phase that raises is
        told as a warning carrying its `phase` and its traceback, and the phases after it still run,
        so a fee that cannot be read does not stop the batches and a birth that breaks does not stop
        the forward windows. A step with any failure counts toward `failures_alert_after`
        (`_note_step`). Before, one try held the whole pass and its alert carried only the
        exception's text: 115 identical warnings in 2 h 18 min said nothing of where."""
        started = time.monotonic()
        out: dict[str, Any] = {"batches": 0, "evaluated": 0, "archived": 0, "calls": 0, "graduations": []}
        self._tapes_built = 0
        self._failures, self._row_errors = [], []

        def graduate() -> None:
            if not self.open():
                out["graduations"] = self.graduate()

        def forward() -> None:
            if not self.open():
                out["forward"] = self.forward_windows()

        self._guarded("royalties", self.royalties)
        self._guarded("seed", self.seed)
        self._guarded("batches", lambda: self._batches(started, out))
        self._guarded("graduate", graduate)
        self._guarded("forward", forward)
        failures, self._failures = self._failures, []
        if failures:
            out["error"] = failures[0]["error"]
        try:
            self._tell_row_errors()
            for failure in failures:
                self.house.alert("warning", f"the lab's step failed ({failure['error']})", phase=failure["phase"],
                                 _traceback=failure["traceback"])
        except Exception:  # noqa: BLE001 - a ledger that cannot take an alert fails the House's own writes too
            pass
        self._note_step(failures)
        try:
            self.publish()
        except Exception as exc:  # noqa: BLE001
            self.house.alert("warning", f"the lab could not publish its stats ({type(exc).__name__}: {str(exc)[:160]})")
        return out

    def _batches(self, started: float, out: dict[str, Any]) -> None:
        """The step's batches, until `step_seconds`, the lab closes or nothing is ready. Breeding is
        guarded on its own: a parent that cannot be bred never stops the batches."""
        settings = self.settings
        while time.monotonic() - started < float(settings["step_seconds"]):
            if self.open():
                break
            # Breed when fewer than a batch wait on tapes already built: seeds each need their own
            # tape (a few a step), so counting every queued row starved breeding behind them
            # (Sept 23, 2026: 191 seeds queued, 4 elites with cached tapes, 2-6 candidates a batch).
            if self.ready_queued() < int(settings["batch_size"]):
                out["calls"] += self._guarded("breed", self.breed) or 0
            done = self.evaluate_batch()
            if not done:
                break
            if done.get("refused"):
                continue
            out["batches"] += 1
            out["evaluated"] += done["candidates"]
            out["archived"] += done["archived"]

    def _guarded(self, phase: str, work: Callable[[], Any]) -> Any:
        """One phase of the step. What it raises is kept for the step's report (`_failures`, once
        per phase and error, with the last `TRACEBACK_CHARS` of its traceback), never raised."""
        try:
            return work()
        except Exception as exc:  # noqa: BLE001 - the lab must never take a lane or the tick down
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            if not any(f["phase"] == phase and f["error"] == error for f in self._failures):
                self._failures.append({"phase": phase, "error": error, "traceback": traceback.format_exc()[-TRACEBACK_CHARS:]})
            return None

    def _note_step(self, failures: Sequence[Mapping[str, str]]) -> None:
        """The step's record of itself (D1, Sept 24, 2026), in `meta` so a restart does not reset it
        (the failures of Sept 23 ran across two restarts): `failures_in_a_row`, `failures_first_at`
        (the run's first failure) and `last_failure` (its phase and error). At
        `failures_alert_after` failures in a row, ONE error alert carrying the traceback, and
        `failing_since` (the run's first failure), which health.json shows. A step with no failure
        clears them all, with an info alert if the run had been escalated. Never raises."""
        try:
            now = self._now()
            count = int(self._meta("failures_in_a_row") or 0)
            if not failures:
                if count:
                    escalated = self._meta("failing_since")
                    self._x("DELETE FROM meta WHERE key IN ('failures_in_a_row', 'failures_first_at', 'last_failure', 'failing_since')")
                    if escalated is not None:
                        self.house.alert("info", f"the Alpha Lab's step works again after {count} failures in a row since {_iso(float(escalated))}")
                return
            first = failures[0]
            count += 1
            since = float(self._meta("failures_first_at") or now)
            self._set_meta("failures_in_a_row", str(count))
            self._set_meta("failures_first_at", str(since))
            self._set_meta("last_failure", json.dumps({"phase": first["phase"], "error": first["error"], "at": now}))
            if count >= int(self.settings["failures_alert_after"]) and self._meta("failing_since") is None:
                self._set_meta("failing_since", str(since))
                self.house.alert("error", f"the Alpha Lab's step has failed {count} times in a row since {_iso(since)} ({first['error']})",
                                 phase=first["phase"], failures_in_a_row=count, _traceback=first["traceback"])
        except Exception as exc:  # noqa: BLE001 - keeping the record of a failure must not be one
            text = f"the lab could not record its step ({type(exc).__name__}: {str(exc)[:160]})"
            if text != self._watch_error:
                self._watch_error = text
                try:
                    self.house.alert("warning", text)
                except Exception:  # noqa: BLE001
                    pass

    def _failing(self) -> dict[str, Any]:
        """The step's failure record as health.json and `lab.stats` show it: `failing_since` (None
        until `failures_alert_after` steps in a row have failed), `failures_in_a_row`, and the last
        failure's `error` (None once a step succeeds)."""
        count = int(self._meta("failures_in_a_row") or 0)
        since = self._meta("failing_since")
        try:
            last = json.loads(self._meta("last_failure") or "null") if count else None
        except ValueError:
            last = None
        return {"failing_since": _iso(float(since)) if since is not None else None, "failures_in_a_row": count,
                "error": last.get("error") if isinstance(last, dict) else None}

    def _block_row(self, row: Mapping[str, Any], exc: BaseException, what: str) -> bool:
        """Block one queued row the lab's own code could not handle (D1, Sept 24, 2026): its NEEDS,
        its tape or its result raised something no refusal names. `status='blocked'` with the error,
        as `_next_batch` blocks a row whose data is unsupported, and the step goes on; the rows are
        told once at the end of the step (`_tell_row_errors`). Call it while handling `exc`. False,
        and nothing written, past `row_errors_per_step` rows in one step: a defect that breaks every
        row is the lab's, and the caller re-raises it rather than block the queue."""
        if len(self._row_errors) >= int(self.settings["row_errors_per_step"]):
            return False
        error = f"{type(exc).__name__}: {str(exc)[:240]}"
        self._x("UPDATE candidates SET status='blocked', error=?, evaluated=? WHERE id=?", (f"{what}: {error}"[:300], self._now(), row["id"]))
        self._row_errors.append({"candidate": str(row["id"]), "error": error, "traceback": traceback.format_exc()[-TRACEBACK_CHARS:]})
        return True

    def _tell_row_errors(self) -> None:
        """One warning for the rows `_block_row` blocked this step, naming them, with the first
        one's traceback."""
        errors, self._row_errors = self._row_errors, []
        if errors:
            self.house.alert("warning", f"the lab could not evaluate {len(errors)} queued candidate(s) and blocked them ({errors[0]['error']})",
                             candidates=[e["candidate"] for e in errors], _traceback=errors[0]["traceback"])

    # ----------------------------------------------------------------- queue
    def queued(self) -> int:
        return int(self._q("SELECT COUNT(*) AS n FROM candidates WHERE status='queued'")[0]["n"])

    def ready_queued(self) -> int:
        """Queued candidates whose search tape the next batches can have without fetching anything
        (`_ready_keys`): what they can run now."""
        fresh = self._ready_keys()
        if not fresh:
            return 0
        count = 0
        for row in self._q("SELECT needs FROM candidates WHERE status='queued'"):
            try:
                count += tape_key(json.loads(row["needs"])) in fresh
            except (TypeError, ValueError):
                continue
        return count

    def _ready_keys(self) -> set[str]:
        """The tape keys a batch can have now without a fetch: a fresh search copy in memory; or, from
        the tape index (which a restart keeps), a tape the lab built in the last `SEARCH_TAPE_SECONDS`
        that the House holds in its cache (an agent's replay built it again) or rebuilds from its own
        disk (the history store's development window: `source` "history-dev"). D1, Sept 24, 2026:
        after the 23:40Z restart the in-memory copies were gone, `ready_queued()` was 0 and every
        step went to `breed()` first. Takes the House's tape lock: the step's lane only, never the
        tick (`health` does not call it)."""
        now = self._now()
        ready = {key for key, hit in self._tapes.items() if now - hit[0] < SEARCH_TAPE_SECONDS}
        fresh = {key: entry for key, entry in self._tape_index.items() if key not in ready and now - entry["at"] < SEARCH_TAPE_SECONDS}
        if fresh:
            house = self.house
            with house._tape_lock:
                held = set(house._tapes)
            ready |= {key for key, entry in fresh.items() if entry["source"] == "history-dev" or entry["house"] in held}
        return ready

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
        `search_fraction`. Keyed by `tape_key` (Sept 23, 2026): a Luna child that differs from its
        parent only in `style` or `parameter_rules` is the parent's tape, not a build of its own.

        A tape with no steps is unsupported input (D1, Sept 24, 2026), kept for the hour like any
        tape that failed: nothing was recorded in its window, so there is nothing to search. The
        history store holds ADA/USD only from 2026-02-01, so an hourly development window
        (2025-09-12..2025-11-14) of ADA/USD alone is fetched and empty; this function read the
        cut's first step outside its guard, and one queued Luna child asking for ADA/USD alone
        failed every step for over two hours with an IndexError. Every tape built is entered in the
        tape index (`_index_tape`), which a restart keeps."""
        key = tape_key(needs)
        hit = self._tapes.get(key)
        if hit is not None and self._now() - hit[0] < SEARCH_TAPE_SECONDS:  # the House rebuilds its own tapes daily
            return hit[1], hit[2]
        failed = self._tape_errors.get(key)
        if failed is not None and self._now() - failed[0] < 3600:
            raise LabError(failed[1])
        if self._tapes_built >= int(self.settings["max_tapes_per_step"]):
            raise TimeoutError("the step's tape budget is spent")
        house = self.house
        with house._tape_lock:
            cached = set(house._tapes)
        try:
            wanted = house._feeds_wanted(needs)
            if wanted:
                start, end = house._live_window(needs)
                house._require_feeds(needs, wanted, house.feeds.coverage(wanted, start, end) if house.feeds is not None else {})
            tape_id, tape = house.tape_for(needs)
            if tape_id not in cached:
                # Only a tape the House had to build counts against the step's budget: one it already
                # held (an agent's replay built it, or a sibling's search) costs a copy, not a build.
                self._tapes_built += 1
            if wanted:
                house._require_feeds(needs, wanted, tape.get("feeds_coverage") or {})
            observed = needs.get("observe") or {}
            missing = [s for s in observed.get("symbols") or [] if not (tape.get("observed_bars") or {}).get(s)]
            if needs.get("venue") == "kalshi" and missing:
                raise LabError("unsupported input: observed bars are missing for " + ", ".join(missing))
            if needs.get("venue") == "alpaca" and observed.get("series"):
                raise LabError("unsupported input: cross-venue event observations are not recorded on equity tapes")
            check_dev_only(tape, house.holdout_window)
        except TimeoutError:
            raise
        except LabError:
            self._forget_tape(key)
            raise
        except Exception as exc:  # noqa: BLE001 - no tape is a blocked candidate, not a crash
            message = self._tape_failure(key, f"{type(exc).__name__}: {str(exc)[:200]}")
            self._tape_errors[key] = (self._now(), message)
            self._forget_tape(key)
            raise LabError(message) from None
        if not tape.get("steps"):
            message = (f"unsupported input: the House's tape for these NEEDS has no steps ({str(tape_id)[:120]}): "
                       "nothing was recorded in its window")
            self._tape_errors[key] = (self._now(), message)
            self._forget_tape(key)
            if tape_id not in cached:
                with house._tape_lock:
                    house._tapes.pop(tape_id, None)
            raise LabError(message)
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
        source = tape.get("source") if isinstance(tape.get("source"), Mapping) else {}
        self._index_tape(key, ident, str(tape_id), "history-dev" if source.get("window") else "live")
        self._tape_built(key)
        return ident, cut

    def _tape_failures(self) -> dict[str, dict[str, Any]]:
        """Tape key -> its failed builds in a row (`meta` `tape_failures`): the folded error, how many
        hourly tries in a row it came back, since when."""
        try:
            raw = json.loads(self._meta("tape_failures") or "{}")
        except ValueError:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _tape_failure(self, key: str, message: str) -> str:
        """What a failed build of the House's tape for these NEEDS means for the rows that need it.

        Unsupported input -- the row is blocked, not re-queued -- when the House's tape reader refuses the
        size of what the NEEDS ask for (`TOO_LONG`: it follows at most `tapes.MAX_PAGES` pages a read, so the
        same NEEDS get the same answer on every try). mcentee-hddb4ae's three alpaca-megacaps submissions
        (12 names of daily bars with a 260-bar warm-up) failed that way every hour on Sept 23-24, 2026 and
        were re-queued at priority 0 for ever, at the front of the queue.

        And the invariant for the answers nobody wrote down: the same failure (numbers folded) that has come
        back `tape_failures_before_block` hourly tries in a row is unsupported input too, with ONE warning;
        the count is kept in `meta` (`tape_failures`), so a restart does not start it again, and a build that
        works clears it (`_tape_built`). Anything else: the message as it is, tried again after the hour."""
        if TOO_LONG in message:
            return f"unsupported input: {message}"
        failures = self._tape_failures()
        folded = re.sub(r"\d+", "#", message)
        row = failures.pop(key, None) or {}
        same = row.get("error") == folded
        tries = int(row.get("tries") or 0) + 1 if same else 1
        since = float(row.get("since") or self._now()) if same else self._now()
        failures[key] = {"error": folded, "tries": tries, "since": since}
        self._set_meta("tape_failures", json.dumps(dict(list(failures.items())[-TAPE_INDEX_MAX:])))
        limit = int(self.settings["tape_failures_before_block"])
        if tries < limit:
            return message
        if tries == limit:
            self.house.alert("warning", f"the lab blocks the queued rows whose tape failed the same way {tries} times in a row since "
                                        f"{_iso(since)}: {message}")
        return f"unsupported input: the House's tape for these NEEDS failed the same way {tries} times in a row ({message})"

    def _tape_built(self, key: str) -> None:
        """A tape that built clears its failures in a row."""
        failures = self._tape_failures()
        if failures.pop(key, None) is not None:
            self._set_meta("tape_failures", json.dumps(failures))

    def _load_tape_index(self) -> dict[str, dict[str, Any]]:
        """The tape index as `meta` `tape_index` holds it, its fresh entries only, oldest first."""
        try:
            raw = json.loads(self._meta("tape_index") or "{}")
        except ValueError:
            return {}
        now, rows = self._now(), []
        for key, entry in (raw.items() if isinstance(raw, dict) else ()):
            try:
                row = {"at": float(entry["at"]), "ident": str(entry["ident"]), "house": str(entry["house"]), "source": str(entry["source"])}
            except (KeyError, TypeError, ValueError):
                continue
            if now - row["at"] < SEARCH_TAPE_SECONDS:
                rows.append((str(key), row))
        return dict(sorted(rows, key=lambda item: item[1]["at"]))

    def _index_tape(self, key: str, ident: str, house_id: str, source: str) -> None:
        """Enter a search tape just built in the tape index and persist it. What is kept, and why:
        the tape key (the NEEDS it serves), when it was built (fresh for `SEARCH_TAPE_SECONDS`), its
        lab id (what `batches.tape_id` and `candidates.tape_id` name it), the House's own tape id
        (whether the House holds it now) and its source ("history-dev" when the House rebuilds it
        from the history store on its own disk, "live" when it must fetch). Not the tape: a search
        copy is some MB and is cut again from the House's tape. Never raises: an index that cannot
        be written costs a breeding step after a restart, never a candidate."""
        self._tape_index.pop(key, None)
        self._tape_index[key] = {"at": self._now(), "ident": ident, "house": house_id, "source": source}
        self._save_tape_index()

    def _forget_tape(self, key: str) -> None:
        """A tape that failed or was refused is not one a batch can have."""
        if self._tape_index.pop(key, None) is not None:
            self._save_tape_index()

    def _save_tape_index(self) -> None:
        now = self._now()
        kept = [(k, e) for k, e in self._tape_index.items() if now - e["at"] < SEARCH_TAPE_SECONDS][-TAPE_INDEX_MAX:]
        self._tape_index = dict(kept)
        try:
            self._set_meta("tape_index", json.dumps(self._tape_index))
        except Exception as exc:  # noqa: BLE001 - see `_index_tape`
            text = f"the lab could not keep its tape index ({type(exc).__name__}: {str(exc)[:160]})"
            if text != self._watch_error:
                self._watch_error = text
                try:
                    self.house.alert("warning", text)
                except Exception:  # noqa: BLE001
                    pass

    # --------------------------------------------------------------- evaluate
    def _next_batch(self) -> tuple[str, dict[str, Any], list[sqlite3.Row]] | None:
        """(lab tape id, search tape, the rows to evaluate) of the next batch: the queued rows grouped by
        the tape they need, one tape a batch, at most one tape BUILT a batch (a step builds at most
        `max_tapes_per_step`). None when nothing is ready.

        Whose turn it is decides which tape (`batch_turn`, E1 of the close-the-gaps run, Sept 24, 2026):
        - "reserved", `reserved_share` of the turns (half): the tape where the programs someone wrote
          wait (an agent's submission first, then Luna's and Sol's), grouped by tape, the one with the
          most rows waiting first; with none waiting, the largest group;
        - "queue", every other remaining turn: the queue's oldest row's tape (a seed, or a lone row of any
          origin, keeps its turn);
        - "largest": the largest group of any origin, the batch the box fills.
        And whatever the turn, `reserved_share` of the batch (`reserved_quota`) is the written programs'
        when any wait on the chosen tape; the rest is filled with whatever else waits on it.

        Why the shares (measured): on Sept 23 the 394 Luna and Sol children waited six hours behind
        1,358 parameter mutants (so a third of every batch went to them, and their tapes were built
        first); then, after Deploy A (Sept 24, 05:37Z), the lab ran 63 batches of 84 candidates in its
        first hour, 1.3 a batch: 65 of the 69 Luna children queued at T4 asked for NEEDS of their own
        (other symbols 42, bars 27), so each needed a tape, the step's four builds all went to them and
        the archive's mutants, 24 to 42 to a tape, never ran. Built one a turn, the builds are shared:
        on the T4 queue the first hour after a restart evaluates far more candidates a build (the PR
        of Sept 24 has the numbers) while the written programs still get half the builds.

        A row the lab cannot serve now never decides a turn (Sept 24, 2026: three submissions whose tape
        never built sat at priority 0): its tape's failure is kept for the hour (`_tape_errors`) and the
        turn goes to the next tape in its order."""
        settings = self.settings
        size = int(settings["batch_size"])
        # A wide look: rows whose tape is not built yet are passed over (at most `max_tapes_per_step` new
        # tapes a step), so children on a ready tape are not starved behind seeds on unbuilt ones.
        rows = self._q("SELECT * FROM candidates WHERE status='queued' ORDER BY priority, created LIMIT ?", (size * 16,))
        if not rows:
            return None
        self._batch_turn = getattr(self, "_batch_turn", 0) + 1
        turn = batch_turn(self._batch_turn, settings.get("reserved_share"))

        def needs_key(row: sqlite3.Row) -> str:
            try:
                return tape_key(json.loads(row["needs"]))
            except (TypeError, ValueError):
                return str(row["needs"])

        groups: dict[str, list[sqlite3.Row]] = {}  # tape key -> its rows, in queue order; keys in queue order
        for row in rows:
            groups.setdefault(needs_key(row), []).append(row)
        position = {key: n for n, key in enumerate(groups)}
        order = list(groups)
        if turn == "largest":
            order.sort(key=lambda key: (-len(groups[key]), position[key]))
        elif turn == "reserved":
            def mine(key: str) -> int:
                return sum(1 for r in groups[key] if r["origin"] in RESERVED_ORIGINS)

            order.sort(key=lambda key: (not mine(key), not any(r["origin"] == "agent" for r in groups[key]),
                                        -len(groups[key]), position[key]))
        for key in order:
            group = groups[key]
            try:
                tape_id, tape = self._search_tape(json.loads(group[0]["needs"]))
            except TimeoutError:
                continue  # its tape waits for the next step
            except LabError as exc:
                # One answer for the tape is one for every row on it (`_search_tape` reads only the tape key).
                for row in group:
                    if isinstance(exc, SealedTape) or "unsupported input" in str(exc) or "invalid" in str(exc).lower():
                        self._x("UPDATE candidates SET status='blocked', error=?, evaluated=? WHERE id=?", (str(exc)[:300], self._now(), row["id"]))
                    else:  # a venue or store that failed now: to the back of the queue, tried again after the hour's cache
                        self._x("UPDATE candidates SET created=?, error=? WHERE id=?", (self._now(), str(exc)[:300], row["id"]))
                continue
            except Exception as exc:  # noqa: BLE001 - D1 (Sept 24, 2026): one row never stops the lab
                # Anything else these rows' NEEDS or tape raise escaped the walk before: nothing moved the
                # row, so it failed every step from the front of the queue.
                for row in group:
                    if not self._block_row(row, exc, "the lab could not read its NEEDS or its tape"):
                        raise
                continue
            reserved = [r for r in group if r["origin"] in RESERVED_ORIGINS][: reserved_quota(size, settings.get("reserved_share"))]
            taken = {r["id"] for r in reserved}
            return tape_id, tape, (reserved + [r for r in group if r["id"] not in taken])[:size]
        return None

    def evaluate_batch(self) -> dict[str, Any] | None:
        """One batch on the lab box (`_next_batch`). None when nothing could be evaluated."""
        settings = self.settings
        picked = self._next_batch()
        if picked is None:
            return None
        tape_id, tape, chosen = picked
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
                        self._forget_tape(key)
                        self._tape_errors[key] = (self._now(), f"unsupported input: {str(exc)[:200]}")
                for r in chosen:
                    self._x("UPDATE candidates SET status='blocked', error=?, evaluated=? WHERE id=?",
                            (f"the lab box refused the tape: {str(exc)[:260]}", self._now(), r["id"]))
                return {"candidates": 0, "ok": 0, "eligible": 0, "gate": 0, "archived": 0, "refused": len(chosen)}
            if type(exc).__name__ == "BoundBoxGone":
                # The configured lab box is terminated. The sandbox does not replace it from the agents'
                # image (a small box, leaked at every restart); the owner makes a new one. Loud, and
                # asked again hourly rather than every step.
                self._box_down_until = self._now() + 3600
                self.house.alert("error", f"the Alpha Lab is stopped: its box is gone ({str(exc)[:300]})")
                return None
            # Infrastructure, never the candidates' fault: they stay queued, and the box is left alone
            # for five minutes rather than asked again every tick.
            self._box_down_until = self._now() + 300
            self.house.alert("warning", f"the lab box could not evaluate a batch ({type(exc).__name__}: {str(exc)[:200]})")
            return None
        seconds = time.monotonic() - started
        by_id = {str(r.get("id")): r for r in results or [] if isinstance(r, Mapping)}
        counts = {"candidates": 0, "ok": 0, "eligible": 0, "gate": 0, "archived": 0}
        live = self._live_series(tape.get("horizon") or chosen[0]["horizon"])
        # Whether this tape is the history store's development window is kept with each result: the
        # graduation's holdout question (`_deep`) must not depend on a tape cache of six entries.
        source = tape.get("source") if isinstance(tape.get("source"), Mapping) else {}
        tape_source = "history-dev" if source.get("window") else "live"
        infrastructure = 0
        for row in chosen:
            result = by_id.get(row["id"])
            if result is None or str(result.get("error") or "").startswith("not evaluated"):
                # The batch's budget did not reach it, or the box could not start its process: it
                # stays queued, and neither is a result against it.
                infrastructure += bool(result is not None and result.get("infrastructure"))
                continue
            try:
                scored = score(result, tape)
                corr = self._correlation(result, live)
                cell = cell_key(row["niche"], row["horizon"], tpd_bucket(scored["trades_per_day"]), corr_bucket(corr))
                status = "evaluated" if scored["ok"] else "failed"
                self._x("UPDATE candidates SET status=?, evaluated=?, tape_id=?, error=?, eligible=?, gate=?, fitness=?, trades=?,"
                        " trades_per_day=?, corr=?, cell=?, summary=? WHERE id=?",
                        (status, self._now(), tape_id, None if scored["ok"] else str(result.get("error") or "")[:300],
                         int(scored["eligible"]), int(scored["gate"]), scored["fitness"], scored["trades"],
                         scored["trades_per_day"], corr, cell if scored["eligible"] else None,
                         json.dumps({**_summary(result, scored), "tape_source": tape_source}, default=str), row["id"]))
            except Exception as exc:  # noqa: BLE001 - D1 (Sept 24, 2026): a result the lab cannot score blocks its own row
                # Left queued, the whole batch would run on the box again every step and fail again.
                if not self._block_row(row, exc, "the lab could not score its result"):
                    raise
                continue
            counts["candidates"] += 1
            counts["ok"] += scored["ok"]
            counts["eligible"] += scored["eligible"]
            counts["gate"] += scored["gate"]
            if scored["eligible"] and self._place(cell, row["niche"], row["id"], float(scored["fitness"])):
                counts["archived"] += 1
        box_usd = Decimal(str(self.settings["box_usd_per_hour"])) * Decimal(str(round(seconds, 3))) / Decimal(3600)
        self._x("INSERT INTO batches(id, at, tape_id, niche, candidates, ok, eligible, gate, archived, seconds, sail_usd)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (f"batch:{self._now():.6f}:{tape_id[-8:]}:{self._rng.random():.6f}", self._now(), tape_id, chosen[0]["niche"],
                 counts["candidates"], counts["ok"], counts["eligible"], counts["gate"], counts["archived"], round(seconds, 3),
                 format(box_usd.quantize(Decimal("0.000001")), "f")))
        if infrastructure:
            # The box could not start processes for some candidates (out of processes or memory):
            # its failure, not theirs. They wait queued, and the box is left alone for a while.
            self._box_down_until = self._now() + 300
            self.house.alert("warning", f"the lab box could not start {infrastructure} of {len(chosen)} candidates' processes "
                                        f"(infrastructure; they stay queued)")
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
        """How much search each lineage gets: two to the power of a score clamped to [-3, 3] (so
        between 1/8 and 8), times one plus its royalties. The score, within these bounds: each born
        graduate adds its floor record (`_floor_score`: +1 or -1 for its practice record, +1 or -1
        again for its real one, -1 for a death that was not redundancy), each lineage its own
        forward windows (`lineage_forward`, S2, Sept 23, 2026: +1 when the pooled window wins,
        -1 when it loses), and royalties +1. A lineage whose graduates or windows lose is searched
        less; one that earns is searched more; nothing here moves anyone's rung or band.

        The family ledger (E1 and E3 of the close-the-gaps run, Sept 24, 2026; `league/families.py`,
        read through the allocator): every lineage in the archive adds its family's score (`_family_score`:
        the family of the agents it grew from, `Allocator.family` read through `families.score`, as
        `Allocator.lineage_score` reads it: +1 for a proven or swinging family, -1 for one whose pooled
        record is negative past the proof's count), so a lineage whose family has a
        positive pooled record gets more of Luna's calls, which pick their parent by these weights; and a
        lineage whose family is at its measured capacity (`family_at_capacity`) weighs 0: no more search
        there (`_pick_parent` passes it over)."""
        now = self._now()
        if self._weights is not None and now - self._weights[0] < 600:
            return self._weights[1]
        min_trades = int(self.settings["forward_min_trades"])
        score_of: dict[str, int] = {}
        for row in self._q("SELECT lineage, agent FROM graduations WHERE state='born' AND agent IS NOT NULL"):
            agent = self.house.registry.get(row["agent"])
            if agent is None:
                continue
            score_of[row["lineage"]] = score_of.get(row["lineage"], 0) + self._floor_score(agent, min_trades)
        for row in self._q("SELECT DISTINCT c.lineage AS lineage FROM forward f JOIN candidates c ON c.id = f.candidate"):
            record = self.lineage_forward(row["lineage"])
            if record["positive"] is True:
                score_of[row["lineage"]] = score_of.get(row["lineage"], 0) + 1
            elif record["positive"] is False and float(record["log_growth"]) < 0:
                score_of[row["lineage"]] = score_of.get(row["lineage"], 0) - 1
        full: set[str] = set()
        for row in self._q("SELECT DISTINCT c.lineage AS lineage FROM archive a JOIN candidates c ON c.id = a.candidate"):
            family = self._family_score(row["lineage"])
            if family is None:
                continue
            score, at_capacity = family
            if score:
                score_of[row["lineage"]] = score_of.get(row["lineage"], 0) + score
            if at_capacity:
                full.add(row["lineage"])
        royalties: dict[str, Decimal] = {}
        for entry in self.house.ledger.iter(kinds="lab.royalty"):
            lineage = str(entry.payload.get("lineage") or "")
            royalties[lineage] = royalties.get(lineage, Decimal(0)) + Decimal(str(entry.payload.get("usd") or 0))
        weights = {}
        for lineage in set(score_of) | set(royalties) | full:
            base = 2.0 ** max(-3, min(3, score_of.get(lineage, 0) + (1 if royalties.get(lineage, 0) > 0 else 0)))
            weights[lineage] = 0.0 if lineage in full else base * (1.0 + float(royalties.get(lineage, Decimal(0))))
        self._weights = (now, weights)
        return weights

    def _family_score(self, lineage: str) -> tuple[int, bool] | None:
        """(the family ledger's score of the family a lineage grew from, whether that family is at its
        measured capacity), from the allocator (`Allocator.family`, `families.score`), or None for a lineage
        that grew from no registry agent (a Sol leap) or while there is no allocator. Never raises: a family
        that cannot be read weighs nothing either way."""
        from .families import score as family_score, swing_rule

        allocator = getattr(self.house, "allocator", None)
        if allocator is None or not hasattr(allocator, "family"):
            return None
        registry = self.house.registry
        agent = next((a for a in (registry.get(i) for i in self._origin(lineage)) if a is not None), None)
        if agent is None or not agent.family:
            return None
        try:
            record = allocator.family(agent.family, agent.venue)
            return (family_score(record, str(record.get("state") or "unproven")),
                    family_at_capacity(record, swing_rule()))
        except Exception:  # noqa: BLE001 - see above
            return None

    def _floor_score(self, agent: Any, min_trades: int) -> int:
        """What one born graduate adds to its lineage's search score, in [-2, 2]: from the
        allocator's board when it has read the agent's evidence (practice: W_paper above or below 1
        after `min_trades` closed trades; real money: W_real above or below 1 after a real trade),
        else from its standing; a dead graduate -1 unless it died redundant."""
        if not agent.alive:
            return 0 if agent.cause in ("redundant",) else -1
        evidence = None
        try:
            board = getattr(self.house, "allocator", None)
            row = (board.board().get("agents") or {}).get(agent.id) if board is not None else None
            evidence = row.get("evidence") if isinstance(row, Mapping) else None
        except Exception:  # noqa: BLE001 - a board that cannot be read moves nothing
            evidence = None
        if isinstance(evidence, Mapping):
            delta = 0
            trades, real_trades = int(evidence.get("trades") or 0), int(evidence.get("real_trades") or 0)
            w_paper, w_real = float(evidence.get("W_paper") or 1.0), float(evidence.get("W_real") or 1.0)
            if trades >= min_trades:
                delta += 1 if w_paper > 1.0 else -1 if w_paper < 1.0 else 0
            if real_trades >= 1:
                delta += 1 if w_real > 1.0 else -1 if w_real < 1.0 else 0
            return delta
        try:
            standing = self.house.standing_of(agent.id)
        except Exception:  # noqa: BLE001 - an unreadable record moves nothing
            standing = {}
        growth, seen = float(standing.get("earned_growth") or 0.0), int(standing.get("earned_observations") or 0)
        return 1 if seen > 0 and growth > 0 else -1 if seen >= 5 and growth < 0 else 0

    def elites(self, niche: str | None = None) -> list[sqlite3.Row]:
        """The archive's elites, ranked: a program whose forward window wins (`forward_score`)
        before every program without a record, those by their fitness on the search tape, and a
        program whose forward window loses after them all (S2, Sept 23, 2026). The order decides
        who graduates first and what an agent is shown first; fitness itself never moves."""
        sql = ("SELECT a.cell, a.fitness AS elite_fitness, a.replaced, c.* FROM archive a JOIN candidates c ON c.id = a.candidate"
               + (" WHERE a.niche=?" if niche else "") + " ORDER BY a.fitness DESC")
        rows = self._q(sql, (niche,) if niche else ())
        scores = self.forward_scores()

        def rank(row: sqlite3.Row) -> tuple[int, float]:
            forward = scores.get(row["id"])
            if forward is None:
                return 1, -float(row["elite_fitness"])
            return (0 if forward > 0 else 2), -forward

        return sorted(rows, key=rank)

    def _pick_parent(self, niche: str | None = None) -> sqlite3.Row | None:
        """The elite a parameter child or a Luna batch is bred from, drawn by weight: its lineage's
        (`lineage_weights`, where the family ledger's score and capacity are) times its own forward
        window's (`forward_factor`, E1, Sept 24, 2026: a winning window doubles it, a losing one quarters
        it; before, breeding read only the lineage's pooled windows and the order `elites` ranks never
        reached it). A lineage at its family's capacity is not drawn at all."""
        rows = [r for r in self.elites(niche) if self._desk(r["niche"]) is not None]
        if not rows:
            return None
        weights = self.lineage_weights()
        scores = self.forward_scores()
        pool, scale = [], []
        for row in rows:
            weight = weights.get(row["lineage"], 1.0)
            if weight <= 0:
                continue  # E3: its family is at its measured capacity
            pool.append(row)
            scale.append(max(0.01, weight) * forward_factor(scores.get(row["id"])))
        if not pool:
            return None
        return self._rng.choices(pool, weights=scale, k=1)[0]

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
            paused = self.paused(parent)
            if paused:
                # A lesson's prior: no parameter-only fork of this lineage (its Luna and Sol
                # children, which change the mechanism, still come).
                self._prior_skips[paused] = self._prior_skips.get(paused, 0) + 1
                continue
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
        kind = "sol" if luna_since_sol >= int(settings["leap_every"]) else "luna"
        # Below the "all" tier (or with the House's OpenAI allowance closed) no packet is built and
        # no client asked: the phase is skipped on the record, and the step's time goes to parameter
        # children and batches (C2, Sept 23, 2026). `_ask` refuses for the same reasons regardless.
        self._llm_paused = self._llm_pause()
        if self._llm_paused:
            self._skipped[kind] += 1
            self.refusal = self._llm_paused
            return 0
        if kind == "sol":
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

    def _llm_pause(self) -> str:
        """Why no Luna or Sol call may be made now, whatever the call: an OpenAI tier below "all"
        (`House.frontier_tier`) or the House's OpenAI allowance closed. '' when one may be tried."""
        house = self.house
        tier = house.frontier_tier()
        if tier != "all":
            return f"the OpenAI tier is {tier!r}"
        if not house.pacer.may_spend("openai"):
            return "the House's OpenAI allowance is closed"
        return ""

    def _llm_refusal(self, client: Any, hold: Decimal) -> str:
        if client is None:
            return "no model client"
        pause = self._llm_pause()
        if pause:
            return pause
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
            self._llm_paused = self._llm_pause()  # the tier or the allowance; '' when it was this call's own client or hold
            return None
        self._llm_paused = ""  # a call is being made: the paid phases are not paused
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
        """One Sol call for a replayable desk, told the archive's shape and the league's edge map: the
        deep-market desks first (`deep_desks`: stocks, index ETFs, the crypto majors, the open desks; E1 of
        the close-the-gaps run, Sept 24, 2026: the search had nudged parameters on thin Kalshi markets, where
        the one earning family's capacity was measured at about $7.81 a day), the one whose grid is emptiest;
        the other desks when no deep desk can be searched. A desk the idle rule holds (`_idle_desk`) comes
        after every desk a leap's graduates may be born onto (the review of #262: at T4 alpaca-open, offered
        markets with no intent ever, tied alpaca-crypto-majors for the emptiest deep desk, and 18 of the lab's
        Sol programs were already there, every one held from graduating)."""
        from .hypotheses import REPLAY_VIEW
        from .house import CONTRACT_PATH

        desks = [n for n in self.house.niches.values() if self._desk(n.id) is not None]
        if not desks:
            return False
        deep = {str(d) for d in (self.settings.get("deep_desks") or [])}
        filled = {r["niche"]: r["n"] for r in self._q("SELECT niche, COUNT(*) AS n FROM archive GROUP BY niche")}
        niche = min(desks, key=lambda n: (bool(self._idle_desk(n.id)), n.id not in deep, filled.get(n.id, 0), self._rng.random()))
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
        holdout where it applies, and birth. Passers waiting for a seat go first.

        E1 (the close-the-gaps run, Sept 24, 2026): the order is `elites`' (a winning forward window
        first), and a candidate the evidence does not support is HELD, before the House's replay and
        again before its birth (`_hold`): a losing forward window, a desk idle for `idle_desk_hours`, or
        a parameter change of a program the desk already runs without a forward score above the desk's
        living median. A held candidate is not tried and not refused: it graduates when the reason goes
        (its window wins, the desk trades again, a feed it asked for arrives); a passer held before its birth
        is in its own state, `held`. What was held, and why, is `held` in `stats` and health.json."""
        settings = self.settings
        out = []
        scores = self.forward_scores()
        held: dict[str, int] = {}
        cache: dict[str, Any] = {}  # the desks' medians and living programs, read once a pass

        def hold(row: Mapping[str, Any]) -> str | None:
            reason = self._hold(row, scores=scores, cache=cache)
            if reason:
                kind = reason.split(":", 1)[0]
                held[kind] = held.get(kind, 0) + 1
            return reason

        # A passer that found its desk or the league full is asked again at most every ten minutes: each
        # try ranks every living agent under the House's lifecycle lock (Deploy 3 review). So is one held:
        # its own state, `held`, which the House's seat market does not read as a waiter (`graduations`
        # 'passed' is what `House._waiting_graduates` and the scoreboard count), so it reserves no seat.
        for row in self._q("SELECT g.candidate, g.lineage, c.code_sha256 FROM graduations g JOIN candidates c ON c.id = g.candidate"
                           " WHERE (g.state='passed' AND (g.detail NOT LIKE '%earned their seats%' OR g.at < ?))"
                           " OR (g.state='held' AND g.at < ?) ORDER BY g.at", (self._now() - 600, self._now() - 600)):
            # A birth a crash interrupted is finished whatever the cap: its agent already exists.
            resumed = self._born_already(row["lineage"], row["code_sha256"])
            if self.births_last_hour() >= int(settings["max_births_per_hour"]) and resumed is None:
                continue
            if resumed is None:
                candidate = self._q("SELECT * FROM candidates WHERE id=?", (row["candidate"],))[0]
                reason = hold(candidate)
                if reason:
                    grad = self._q("SELECT line, family FROM graduations WHERE candidate=?", (row["candidate"],))[0]
                    out.append(self._record(candidate, "held", f"held: {reason}", line=grad["line"], family=grad["family"]))
                    continue
            out.append(self._birth(row["candidate"]))
        budget = int(settings["max_graduations_per_step"])
        # An infrastructure failure is not the candidate's: it may be tried again after an hour.
        tried = {r["candidate"] for r in self._q("SELECT candidate FROM graduations WHERE state!='replay_unavailable' OR at>=?",
                                                  (self._now() - 3600,))}
        # Seeds are parents, never graduates: a living agent's own program, a card or a founder has had
        # its own chance. Neither is a program a living agent already runs.
        running = {a.code_sha256 for a in self.house.registry.living()}
        # A cell graduates its best program that may graduate: past one that is held, never past one that was
        # tried (as its elite alone was before E1).
        decided: set[str] = set()
        for row in self._graduation_order(scores):
            if budget <= 0 or self.births_last_hour() >= int(settings["max_births_per_hour"]):
                break
            if row["cell"] in decided or row["code_sha256"] in running or self._desk(row["niche"]) is None:
                continue
            if hold(row):
                continue
            decided.add(row["cell"])
            if row["id"] in tried or not row["gate"]:
                continue
            budget -= 1
            out.append(self._graduate_one(self._q("SELECT * FROM candidates WHERE id=?", (row["id"],))[0]))
        self._held = {"at": now_iso(self.house.clock), "counts": held}
        return out

    def _graduation_order(self, scores: Mapping[str, float] | None = None) -> list[sqlite3.Row]:
        """What graduation considers, in its order (E1, Sept 24, 2026): for each cell of the archive, in
        `elites`' order, the cell's gate-passing programs other than seeds ranked as `elites` ranks (a winning
        forward window first, then fitness on the search tape, a losing window last), so a cell's elite comes
        first -- and when it may not graduate (`_hold`: a nudge, a losing window; a seed, or a program a
        living agent runs), the next program of its cell may (`graduate`). Keeping only the elite, a cell whose
        fittest program on the search tape was a parameter nudge of a living program would never graduate the
        mechanism changes beside it: on the T4 snapshot (05:28Z Sept 24) 12 of the 26 cells with a graduate to
        offer offered one that was not their elite (a seed's cell, or one whose elite is a nudge)."""
        scores = self.forward_scores() if scores is None else scores

        def rank(row: sqlite3.Row) -> tuple[int, float]:
            forward = scores.get(row["id"])
            if forward is None:
                return 1, -float(row["fitness"] or 0.0)
            return (0 if forward > 0 else 2), -forward

        cells: dict[str, list[sqlite3.Row]] = {}
        # Without the code (thousands of files a pass): `_twins` reads a program's digest by its hash, and
        # `graduate` reads the whole row of the one it tries.
        for row in self._q(f"SELECT {GRADUATION_COLUMNS} FROM candidates WHERE gate=1 AND status='evaluated' AND cell IS NOT NULL"
                           " AND origin!='seed'"):
            cells.setdefault(row["cell"], []).append(row)
        out: list[sqlite3.Row] = []
        for elite in self.elites():
            out.extend(sorted(cells.pop(elite["cell"], []), key=rank))
        return out

    # ------------------------------------------------------------ the holds (E1)
    def _hold(self, row: Mapping[str, Any], *, scores: Mapping[str, float] | None = None,
              cache: dict[str, Any] | None = None) -> str | None:
        """Why this candidate may not graduate now, or None (E1 of the close-the-gaps run, Sept 24, 2026).
        Each reason starts with its kind and a colon (`held` counts them):

        - "forward": its forward window loses (`forward_score` at or below zero). The search tape only
          admits; data that came after the code was frozen ranks, and a losing window keeps a
          candidate from graduating whatever its search fitness (study of Sept 23, 17:05Z: replay did
          not predict practice, 0 of 20 passes positive after 6 active blocks). A candidate with no
          window of its own is judged by the windows of its mechanism (`_mechanism_forward`: the other
          programs of its desk with its code beyond PARAMS): held while their mean loses. The review of
          #262: only elites, waiting graduates and residents are ever scored, so walking a cell past an
          elite held for a losing window reached its untested parameter twins -- on the T4 snapshot 2 of
          the 26 cells on offer offered one, the twin of a window losing 0.0699 a block.
        - "idle": its desk wrote no intent in `idle_desk_hours` while its members were offered markets,
          and no feed the desk asked for arrived in that time (`_idle_desk`).
        - "nudge": no code change beyond PARAMS (`mechanism_digest`) relative to a living program of its
          desk -- every living member of its lineage there, and any other: a program the desk already
          runs is not a new mechanism whoever's line it is on -- unless its forward score is above the
          desk's living median (`_desk_median`: the residents' ranked forward scores). A desk whose
          residents have no ranked score yet has no median, and the candidate's own window must then
          win (above zero): so a desk still waiting for its residents' windows keeps its code-changing
          graduates, and its nudges wait for a window of their own, never for good (the PR of Sept 24
          measured the T4 queue and waiting list)."""
        ident, niche = str(row["id"]), str(row["niche"])
        scores = self.forward_scores() if scores is None else scores
        cache = {} if cache is None else cache
        forward = scores.get(ident)
        if forward is not None and forward <= 0:
            return (f"forward: its forward window loses ({forward:+.6f} a block on data after its code was frozen); "
                    "the search tape only admits")
        if forward is None:
            mechanism = self._mechanism_forward(row, scores, cache)
            if mechanism is not None and mechanism[0] <= 0:
                return (f"forward: it has no window of its own, and the {mechanism[1]} forward window(s) of its mechanism on {niche} "
                        f"(the same code beyond PARAMS) lose {mechanism[0]:+.6f} a block on average; the search tape only admits")
        idle = self._idle_desk(niche)
        if idle:
            return f"idle: {idle}"
        twins = self._twins(row, cache)
        if twins:
            if f"median:{niche}" not in cache:
                cache[f"median:{niche}"] = self._desk_median(niche)
            median = cache[f"median:{niche}"]
            bar = 0.0 if median is None else median
            if forward is None or forward <= bar:
                where = (f"the desk's living median {median:+.6f}" if median is not None
                         else "zero (no resident of the desk has a ranked forward score yet)")
                mine = "no forward score yet" if forward is None else f"its forward score {forward:+.6f}"
                return (f"nudge: a parameter change of {twins[0]}'s program on {niche} ({len(twins)} living program(s) with "
                        f"the same code beyond PARAMS); it graduates with a code change or a forward score above {where}, "
                        f"and has {mine}")
        return None

    def _mechanism(self, code: str | None, key: str | None = None, ident: str | None = None) -> str | None:
        """`mechanism_digest` of a program, remembered by its code's SHA-256 (`key`, the candidates' own
        `code_sha256`, or hashed here); a candidate row read without its code is read by `ident` once."""
        key = key or hashlib.sha256(str(code or "").encode("utf-8")).hexdigest()
        if key not in self._digests:
            if code is None and ident is not None:
                found = self._q("SELECT code FROM candidates WHERE id=?", (ident,))
                code = found[0]["code"] if found else None
            if len(self._digests) >= 16384:
                self._digests.clear()
            self._digests[key] = mechanism_digest(code) if code is not None else None
        return self._digests[key]

    def _row_mechanism(self, row: Mapping[str, Any]) -> str | None:
        """`_mechanism` of a candidate row, read with its code or without it (by its hash and id)."""
        keys = row.keys() if hasattr(row, "keys") else ()
        return self._mechanism(row["code"] if "code" in keys else None, key=row["code_sha256"] if "code_sha256" in keys else None,
                               ident=str(row["id"]))

    def _mechanism_forward(self, row: Mapping[str, Any], scores: Mapping[str, float],
                           cache: dict[str, Any]) -> tuple[float, int] | None:
        """(the mean ranked forward score, how many) of the OTHER programs of the candidate's desk that are its
        mechanism beyond PARAMS (`mechanism_digest`), or None when none has a ranked window: what a program with no
        window of its own is judged by (`_hold`; the review of #262). The lab's ranked windows are grouped by desk
        and mechanism once a pass (`cache`)."""
        if "mechanisms" not in cache:
            grouped: dict[tuple[str, str], list[tuple[str, float]]] = {}
            ranked = list(scores)
            for start in range(0, len(ranked), 500):
                chunk = ranked[start:start + 500]
                marks = ",".join("?" for _ in chunk)
                for found in self._q(f"SELECT id, niche, code_sha256 FROM candidates WHERE id IN ({marks})", chunk):
                    digest = self._mechanism(None, key=found["code_sha256"], ident=found["id"])
                    if digest is not None:
                        grouped.setdefault((str(found["niche"]), digest), []).append((str(found["id"]), float(scores[found["id"]])))
            cache["mechanisms"] = grouped
        digest = self._row_mechanism(row)
        if digest is None:
            return None
        windows = [score for ident, score in cache["mechanisms"].get((str(row["niche"]), digest), ()) if ident != str(row["id"])]
        if not windows:
            return None
        return math.fsum(windows) / len(windows), len(windows)

    def _twins(self, row: Mapping[str, Any], cache: dict[str, Any] | None = None) -> list[str]:
        """The living agents of the candidate's desk whose current program is the candidate's beyond its
        parameters (`mechanism_digest`), its lineage's first: the programs it would only nudge. The desk's
        programs are read once a graduation pass (`cache`)."""
        digest = self._row_mechanism(row)
        if digest is None:
            return []
        cache = {} if cache is None else cache
        key = f"programs:{row['niche']}"
        if key not in cache:
            programs: dict[str, list[Any]] = {}
            for agent in self.house.registry.living():
                if agent.specialty == row["niche"]:
                    programs.setdefault(self._mechanism(agent.code) or "", []).append(agent)
            cache[key] = programs
        origin = set(self._origin(str(row["lineage"])))
        founder = f"lab:{row['lineage']}"[:120]
        twins = cache[key].get(digest) or []
        return [a.id for a in sorted(twins, key=lambda a: (a.id not in origin and a.founder != founder, a.id))]

    def _desk_median(self, niche: str) -> float | None:
        """The median of the desk's living residents' ranked forward scores (`resident_forward`, S2), or
        None while none has one."""
        values = sorted(v for v in (self.resident_forward(a, ranked=True) for a in self.house.registry.living()
                                    if a.specialty == niche) if v is not None)
        if not values:
            return None
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2

    def _idle_desk(self, niche: str) -> str | None:
        """Why the desk counts as idle for a graduation (E1, Sept 24, 2026), or None: its members, living or
        dead in the window, were offered markets in the last `idle_desk_hours` (`agent.woke` `offered`) and
        wrote no intent (`agent.intent`), and no feed the desk asked for arrived in that time
        (`_feed_arrived`). A desk that was offered nothing is shut by the calendar, not idle. Read at most
        every ten minutes a desk: a few indexed reads an agent."""
        now = self._now()
        hit = self._idle.get(niche)
        if hit is not None and now - hit[0] < 600:
            return hit[1]
        try:
            reason = self._idle_reason(niche, now)
        except Exception as exc:  # noqa: BLE001 - a record that cannot be read holds nobody back
            reason = None
            self._forward_warn(f"the lab could not read whether {niche} is idle ({type(exc).__name__}: {str(exc)[:160]})")
        self._idle[niche] = (now, reason)
        return reason

    def _idle_reason(self, niche: str, now: float) -> str | None:
        hours = float(self.settings.get("idle_desk_hours") or 0)
        if hours <= 0:
            return None
        since = now - hours * 3600
        ledger = self.house.ledger
        members = [a for a in list(self.house.registry.agents.values()) if a.specialty == niche
                   and (a.alive or (_ts(a.died_at) or 0.0) >= since)]
        if not members:
            return None  # nobody sat there in the window: nothing is measured
        last = None
        for agent in members:
            entry = ledger.last("agent.intent", agent=agent.id)
            at = _ts(entry.at) if entry is not None else None
            if at is not None and (last is None or at > last):
                last = at
        if last is not None and last >= since:
            return None
        offered = 0
        for agent in members:
            for entry in reversed(ledger.read(kinds="agent.woke", agent=agent.id, limit=300, newest=True)):
                at = _ts(entry.at)
                if at is None or at < since:
                    break
                offered += int(entry.payload.get("offered") or 0) > 0
            if offered:
                break
        if not offered:
            return None
        arrived = self._feed_arrived(niche, since)
        if arrived:
            return None
        quiet = f"since {_iso(last)}" if last is not None else "ever"
        return (f"{niche} was offered markets and wrote no intent in {hours:g} h (none {quiet}), and no feed it asked for "
                f"arrived since {_iso(since)}")

    def _feed_arrived(self, niche: str, since: float) -> str | None:
        """A feed the desk asked for that arrived after `since`, or None: a `tool.fulfilled` row for a
        `tool.request` of one of its agents, living or dead (the recorders of Deploy B answer requests that
        way, `feeds.fulfil_requests`), never the toolsmith's refusal (`DECLINED`), or a recorded feed its
        programs declare (`NEEDS["feeds"]`) or its requests name (`feeds.request_feed`) whose recording began
        then (its first `data.coverage` row with data).

        The review of #262 (Sept 24, 2026): on the T0 and T4 snapshots the "answer" that let seven of the eight
        desks with one past the rule was the toolsmith's "cannot be a pure tool ... BLOCKED" (the rows of Sept
        22, 15:29Z and Sept 23, 02:17Z), which says that nothing will arrive."""
        from .feeds import request_feed, requested

        ledger = self.house.ledger
        agents = {a.id: a for a in list(self.house.registry.agents.values()) if a.specialty == niche}
        asked: dict[str, str] = {}
        feeds: set[str] = set()
        for entry in ledger.iter(kinds="tool.request"):
            if entry.agent in agents:
                asked[entry.id] = str(entry.payload.get("name") or "")
                feed = request_feed(entry.payload.get("name"))
                if feed:
                    feeds.add(feed)
        for entry in ledger.iter(kinds="tool.fulfilled"):
            at = _ts(entry.at)
            if at is None or at < since or str(entry.payload.get("request") or "") not in asked:
                continue
            if str(entry.payload.get("outcome") or "").strip().lower().startswith(DECLINED):
                continue  # a refusal: nothing arrived
            return f"the request {asked[str(entry.payload['request'])][:80]!r} was answered at {_iso(at)}"
        for agent in agents.values():
            if agent.alive:
                feeds |= set(requested((agent.needs or {}).get("feeds")))
        if not feeds:
            return None
        began: dict[str, float] = {}
        for entry in ledger.iter(kinds="data.coverage"):
            p = entry.payload
            feed = str(p.get("feed") or "")
            if p.get("asset") != "feed" or feed not in feeds or feed in began or not p.get("start"):
                continue
            # When the House first held its data: the row's own time, not `start`, which is where the data
            # begin. The review of #262: a backfilled feed's first row starts months back (T4: `vol` from
            # 2026-07-24 and `funding` from 2026-06-25, both first recorded Sept 23, 03:56Z), so read from
            # `start` a feed whose recording began in the window never arrived.
            recorded = _ts(entry.at)
            if recorded is not None:
                began[feed] = recorded
        fresh = sorted(feed for feed, start in began.items() if start >= since)
        return f"the {fresh[0]} feed began recording at {_iso(began[fresh[0]])}" if fresh else None

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

    def _origin(self, lineage: str) -> list[str]:
        """The registry lines a lab lineage grew from, nearest first and root last: an agent's own
        selection path (itself, its parent, ...) for `agent:<id>`, a card's line for `card:<id>`, a
        founder's line for `founder:<key>`. Empty for Sol's leaps, which start from nothing."""
        registry = self.house.registry
        kind, _, key = str(lineage).partition(":")
        start: list[str] = []
        if kind == "agent" and key:
            start = [key]
        elif kind == "card" and key:
            start = [a.id for a in registry.agents.values() if a.founder == f"card:{key}"]
            if not start:
                foundry = getattr(self.house, "hypotheses", None)
                try:
                    card = foundry.cards().get(key) if foundry is not None else None
                except Exception:  # noqa: BLE001 - an unreadable card adds no line; the lab's own still count
                    card = None
                if card and card.get("line_id"):
                    start = [str(card["line_id"])]
        elif kind == "founder" and key:
            start = [a.id for a in registry.agents.values() if a.founder == key]
        out: list[str] = []
        for ident in start:
            for step in registry.lineage(ident) or [ident]:
                if step not in out:
                    out.append(step)
        return out

    def _selection_path(self, row: Mapping[str, Any], line: str, family: str) -> list[str]:
        """Every line whose House replays selected this graduate, as the House's own lineage is read
        (`Registry.lineage`: nearest first, root last): its own line; the lines this lab lineage has
        already sent to the House's replay (their trials carry its family), newest first; then the
        selection path the lineage grew from (`_origin`).

        This is what its deflated Sharpe is judged against and whose sealed-holdout ration it spends
        (the ration is keyed by the path's root). A program an agent ground variants of on its own
        line, and saw on the whole tape, is not judged as a first try: 'a child inherits its
        parent's count, so there is no way to spend the budget and start again' holds through the
        lab too."""
        earlier: list[str] = []
        for entry in self.house.ledger.iter(kinds="eval.trial"):
            if entry.payload.get("family") == family and entry.agent and entry.agent != line and entry.agent not in earlier:
                earlier.append(entry.agent)
        path = [line]
        for ident in [*reversed(earlier), *self._origin(row["lineage"])]:
            if ident not in path:
                path.append(ident)
        return path

    def _parent(self, lineage: str) -> str | None:
        """The registry agent a graduate descends from (its lineage's origin), so that its own later
        replays inherit that selection path as every House child does. None for Sol's leaps."""
        origin = self._origin(lineage)
        return origin[0] if origin and self.house.registry.get(origin[0]) is not None else None

    def _virtual(self, row: Mapping[str, Any], line: str, family: str) -> Any:
        from .agents import Agent, niche_of

        needs = json.loads(row["needs"])
        venue, horizon, style = niche_of(needs)
        return Agent(id=line, name=line, family=family, venue=venue, horizon=horizon, style=style, generation=1,
                     parent=self._parent(row["lineage"]), code=row["code"], params={}, wake_minutes=15,
                     born_at=now_iso(self.house.clock), needs=needs, specialty=row["niche"], line=line, founder=None)

    def _holdouts_used(self, row: Mapping[str, Any], path: Sequence[str]) -> int:
        """Sealed-holdout evaluations already spent against this graduate: by the lab lineage's lines,
        and by the root of the selection path it grew from (the key the House's seal rations)."""
        from .deep_replay import HoldoutSeal

        house = self.house
        seal = HoldoutSeal(house.ledger, budget=house.settings.holdout_lineage_budget, window=house.holdout_window)
        return max(self._lineage_holdouts(row["lineage"]), seal.used(path[-1]))

    def _holdout_refusal(self, row: Mapping[str, Any], path: Sequence[str]) -> str | None:
        """Why this graduate may not open the sealed holdout; None when it may. Two rations.

        The lineage's: many lines of one lab lineage must not be a way to probe the sealed window, so
        its budget is the House's per-line budget, counted over all of its lines and the root of the
        selection path it grew from (`_holdouts_used`).

        The living line's reserve. That root's ration is the one the House reads before forking any
        agent descending from it (`House._holdout_spent`) and the one its replays of that agent's
        new versions spend: once it is gone the line can grow no more, for good. The review of
        Deploy 3 (Sept 23, 2026) measured 5 of 14 roots on the live ledger at 3 of 3; a lab that
        seeds every living agent and graduates its mutants every few minutes would spend a
        promising line's remaining evaluations within hours. So while a line living on the root is
        judged by the seal (`House._seal_applies`), the lab leaves it its last `holdout_reserve`
        evaluations. The reserve comes out of the lab's share: the root's ration is never enlarged."""
        from .deep_replay import HoldoutSeal

        house = self.house
        budget = int(house.settings.holdout_lineage_budget)
        if self._holdouts_used(row, path) >= budget:
            return f"the lab lineage {row['lineage']} has spent its {budget} sealed-holdout evaluations"
        reserve = max(0, int(self.settings["holdout_reserve"]))
        if not reserve or not path:
            return None
        root = path[-1]
        registry = house.registry
        living = [a.id for a in registry.living() if (registry.lineage(a.id) or [a.id])[-1] == root and house._seal_applies(a)]
        if not living:
            return None
        seal = HoldoutSeal(house.ledger, budget=budget, window=house.holdout_window)
        used = seal.used(root)
        if used + reserve >= budget:
            return (f"the line {root} has spent {used} of its {budget} sealed-holdout evaluations and {living[0]} lives on it: "
                    f"its last {budget - used} stay with the living line's own forks")
        return None

    def _graduate_one(self, row: Mapping[str, Any]) -> dict[str, Any]:
        house = self.house
        line, family = self._names(row)
        if house.registry.get(line) is not None:
            return self._record(row, "refused", f"the line {line} already exists", line=line, family=family)
        path = self._selection_path(row, line, family)
        if self._deep(row) and house.settings.holdout_gate:
            # Refused before the replay, which would be a trial spent on nothing.
            refusal = self._holdout_refusal(row, path)
            if refusal:
                return self._record(row, "holdout_rationed", refusal, line=line, family=family)
        agent = self._virtual(row, line, family)
        result = house._candidate_replay(agent, row["code"], lineage=path)
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
            # Asked again: the House's own forks may have opened the seal during the replay.
            refusal = self._holdout_refusal(row, path)
            if refusal:
                try:
                    house.sandbox.retire(line)
                except Exception:  # noqa: BLE001
                    pass
                return self._record(row, "holdout_rationed", refusal, line=line, family=family)
            holdout = house._holdout(agent, row["code"], needs, params, lineage=path)
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
        """Was this candidate searched on the history store's development window? Its own result
        says (`tape_source`, kept at evaluation since Sept 23, 2026, so a restart or the tape cache's
        turnover cannot lose the answer); older rows fall back to the cache and the desk's rule."""
        try:
            source = (json.loads(row["summary"] or "{}") or {}).get("tape_source")
        except (TypeError, ValueError, KeyError, IndexError):
            source = None
        if source in ("history-dev", "live"):
            return source == "history-dev"
        for _, tape_id, tape in self._tapes.values():
            if tape_id == row["tape_id"]:
                return bool((tape.get("source") or {}).get("window"))
        needs = json.loads(row["needs"])
        return needs.get("venue") == "alpaca" and bool(self.house.settings.deep_replay) and not self.house._feeds_wanted(needs)

    def _birth(self, ident: str) -> dict[str, Any]:
        """Born on paper exactly as a replay-passing foundry card is: `spawn` with the House's
        endowment on the desk, seated on rung 1 with its code marked as tried, displacing the
        desk's (or the league's) weakest eligible agent when full. Waits when nobody may be displaced.

        No Sail call is made under the House's lifecycle lock, which every wake of the tick takes
        (E3's rule for background work; the review of PR 160 found this birth holding it through the
        child's NEEDS probe in the probe box and the displaced agent's `retire`). So: the seat is
        checked first under the lock (a birth that must wait buys no probe); then the NEEDS are read
        holding only the probe box, claimed for at most `probe_wait_seconds` (busy, or Sail failing,
        the birth waits for the next step as `waiting_probe`); then, under the lock again, the seat
        is checked once more and the child is spawned from that probe, seated and routed; and the
        displaced agent is killed after the lock is let go, so its box is retired outside it."""
        from contextlib import nullcontext

        from .house import PROBE_BOX
        from .sandbox import SandboxError

        house = self.house
        row = self._q("SELECT * FROM candidates WHERE id=?", (ident,))[0]
        grad = self._q("SELECT * FROM graduations WHERE candidate=?", (ident,))[0]
        line, family = grad["line"], grad["family"]
        niche = house.niches.get(row["niche"])
        rules = house.game["economy"]
        with house._lifecycle_lock:
            child = self._born_already(row["lineage"], row["code_sha256"])
            if child is not None:
                displaced = self._finish_birth(row, child, niche=niche, rules=rules, resumed=True)
            else:
                _, refusal = self._seat_for(row, niche, rules, line=line, family=family)
                if refusal is not None:
                    return refusal
        if child is None:
            claim = getattr(house.sandbox, "claim", None)
            described = None
            try:
                with (claim(PROBE_BOX, wait=float(house.settings.probe_wait_seconds)) if claim is not None else nullcontext(True)) as free:
                    if free:
                        described = house.sandbox.needs(PROBE_BOX, row["code"])
            except SandboxError as exc:
                return self._record(row, "waiting_probe", f"infrastructure, tried again next step: {type(exc).__name__}: {str(exc)[:200]}",
                                    line=line, family=family, table_state="passed")
            if described is None:
                return self._record(row, "waiting_probe", "the House's probe box is in use by other work; tried again next step",
                                    line=line, family=family, table_state="passed")
            with house._lifecycle_lock:
                child = self._born_already(row["lineage"], row["code_sha256"])
                if child is not None:  # finished meanwhile: a birth is never made twice
                    displaced = self._finish_birth(row, child, niche=niche, rules=rules, resumed=True)
                else:
                    displaced, refusal = self._seat_for(row, niche, rules, line=line, family=family)
                    if refusal is not None:
                        return refusal
                    params = json.loads(grad["params"] or "{}")
                    passed = house.ledger.get(f"lab.graduate:{ident}:passed")
                    sealed = passed is not None and "holdout" in str(passed.payload.get("detail") or "")
                    why = (f"an Alpha Lab graduate ({row['origin']}, by {row['author']}, lineage {row['lineage']}): {str(row['idea'] or '')[:220]} "
                           f"-- fittest in its cell ({row['cell']}) at {float(row['fitness'] or 0):+.6f} a block out of sample on the lab's "
                           f"search tape, then passed the House's replay{' and the sealed holdout' if sealed else ''}")
                    try:
                        child = house.spawn(line, family, row["code"], parent=self._parent(row["lineage"]), reason=why[:1500], params=params,
                                            endowment=rules["endowment_usd"], specialty=niche.id, founder=f"lab:{row['lineage']}"[:120],
                                            described=described)
                    except ValueError as exc:
                        return self._record(row, "refused_at_birth", str(exc), line=line, family=family)
                    displaced = self._finish_birth(row, child, niche=niche, rules=rules, displaced=displaced, sealed=sealed)
        if displaced is not None and displaced.alive and displaced.id != child.id:
            # `kill` takes the lifecycle lock for its own writes and retires the box after it lets go.
            house.kill(displaced, "displaced", house.postmortem(displaced, "displaced",
                       "an Alpha Lab graduate that passed the House's replay takes the seat of the weakest eligible agent"))
        seated = child.id == line and child.code_sha256 == row["code_sha256"]
        return self._record(row, "born", f"born as {child.id}" + ("" if seated else " (not seated: its probe read other NEEDS)"),
                            line=line, family=family, agent=child.id)

    def _seat_for(self, row: Mapping[str, Any], niche: Any, rules: Mapping[str, Any], *, line: str,
                  family: str) -> tuple[Any, dict[str, Any] | None]:
        """(the agent a birth now would displace or None, None), or (None, the outcome recorded) when
        the desk is closed or full of agents that have earned their seats. No Sail call."""
        house = self.house
        living = house.registry.living()
        if niche is None or niche.dormant:
            return None, self._record(row, "refused", "its desk is closed", line=line, family=family)
        newcomer = self._newcomer(row, family)
        if sum(1 for a in living if a.specialty == niche.id) >= niche.max_members:
            displaced = house._weakest(rules, specialty=niche.id, evidenced=True, newcomer=newcomer)
            if displaced is None:
                return None, self._record(row, "waiting_seat", "its desk is full of agents that have earned their seats",
                                          line=line, family=family, table_state="passed")
            return displaced, None
        if len(living) >= int(rules["max_population"]):
            displaced = house._weakest(rules, evidenced=True, newcomer=newcomer)
            if displaced is None:
                return None, self._record(row, "waiting_seat", "the league is full of agents that have earned their seats",
                                          line=line, family=family, table_state="passed")
            return displaced, None
        return None, None

    def _newcomer(self, row: Mapping[str, Any], family: str) -> Any:
        """The graduate as the House's seat market reads a newcomer (S1, Sept 24, 2026): its family (a lab
        family, proven only by its own members' record) and its forward score, which must beat a trading
        resident's own forward record before that resident's seat is its."""
        from .house import Newcomer

        return Newcomer(family=family, venue=str(row["venue"]), forward=self.forward_score(str(row["id"])),
                        what=f"the Alpha Lab graduate {row['id']}")

    def _born_already(self, lineage: str, code_sha256: str) -> Any:
        """The agent an earlier `_birth` of this candidate spawned, if any (living or not). The
        graduation row is marked born only after the seat, the route row and the displacement, so a
        crash or a deploy's shutdown in between leaves it 'passed' with the agent already in the
        registry: the next step must finish that birth, never spawn and endow a second one."""
        founder = f"lab:{lineage}"[:120]
        for agent in list(self.house.registry.agents.values()):
            if agent.founder != founder:
                continue
            born = self.house.ledger.get(f"born:{agent.id}")
            spawned = str((born.payload if born is not None else {}).get("code_sha256") or agent.code_sha256)
            if spawned == code_sha256:  # the program it was born with: this candidate, whatever it runs now
                return agent
        return None

    def _finish_birth(self, row: Mapping[str, Any], child: Any, *, niche: Any, rules: Mapping[str, Any],
                      displaced: Any = None, sealed: bool | None = None, resumed: bool = False) -> Any:
        """Seat a newborn graduate and write its route row, under the lifecycle lock and with no
        Sail call; return the agent whose seat it takes (the caller kills it after letting the lock
        go, then records the birth). Each step is idempotent, so a birth resumed after a crash
        (`_born_already`) finishes exactly once: it is seated only if it is not on a rung yet,
        endowed only if it never was, and displaces someone only while its desk or the league is
        still over its cap because of it."""
        house = self.house
        ident = row["id"]
        line = self._q("SELECT line FROM graduations WHERE candidate=?", (ident,))[0]["line"]
        if sealed is None:
            passed = house.ledger.get(f"lab.graduate:{ident}:passed")
            sealed = passed is not None and "holdout" in str(passed.payload.get("detail") or "")
        seated = child.id == line and child.code_sha256 == row["code_sha256"]
        if resumed and child.alive:
            if house.ledger.get(f"endow:{child.id}") is None:
                house.economy.grant(child.id, rules["endowment_usd"], "endowment", id=f"endow:{child.id}")
            living = house.registry.living()
            newcomer = self._newcomer(row, str(child.family))
            if niche is not None and sum(1 for a in living if a.specialty == niche.id) > niche.max_members:
                displaced = house._weakest(rules, specialty=niche.id, exclude=[child.id], evidenced=True, newcomer=newcomer)
            elif len(living) > int(rules["max_population"]):
                displaced = house._weakest(rules, exclude=[child.id], evidenced=True, newcomer=newcomer)
        if seated and child.alive:
            if house.evaluator.rung(child.id) < 1:
                house.evaluator.seat(child.id, 1, f"an Alpha Lab graduate: candidate {ident} passed the House's replay before birth, on its own line")
            with house._state_lock:
                house._state["tried"][child.id] = child.code_sha256
            house.seat(child)
        evidence = {"candidate": ident, "lineage": row["lineage"], "origin": row["origin"], "author": row["author"],
                    "cell": row["cell"], "fitness": row["fitness"], "replay_passed": True, "holdout_passed": sealed,
                    "seated_on_paper": seated, "displaced": displaced.id if displaced is not None else None,
                    "parent": child.parent}
        if house.ledger.get(f"birth-route:{child.id}") is None:  # before the foundry's labeller can call it something else
            house.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": "lab", "model": None,
                                                   "reason": f"an Alpha Lab graduate for {row['niche']}", "evidence": evidence},
                                id=f"birth-route:{child.id}")
        return displaced

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

    # --------------------------------------------------------------- forward
    def forward_due(self, limit: int, residents: Mapping[str, Any] | None = None) -> list[sqlite3.Row]:
        """The archived elites, the graduates waiting for seats and every living resident's current program
        (S2, Sept 24, 2026: `_residents`, whatever its search status but blocked) whose forward window is
        next: never scored first -- the graduates waiting for seats, then the residents, then the elites --
        then least recently scored (the table decides, so a restart resumes). D1, Sept 24, 2026: the runs
        of Sept 23 at 22:11Z and 23:14Z scored 4 and 5 of their 48 due candidates (the rest skipped
        when the run's time was spent), in evaluation order, so the graduates whose forward score the
        seat market reads waited behind the archive's never-scored elites."""
        ids = list(residents if residents is not None else self._residents())[:400]
        marks = ",".join("?" for _ in ids)
        # A graduate held before its birth (E1, Sept 24, 2026: `held`) is scored as a waiting one is: a forward
        # window is what releases it.
        rows = self._q("SELECT c.*, MAX(f.at) AS scored, c.id IN (SELECT candidate FROM graduations WHERE state IN ('passed', 'held'))"
                       f" AS waiting, c.id IN ({marks}) AS resident FROM candidates c LEFT JOIN forward f ON f.candidate = c.id"
                       " WHERE (c.status='evaluated' AND c.id IN (SELECT candidate FROM archive UNION SELECT candidate FROM graduations"
                       f" WHERE state IN ('passed', 'held'))) OR (c.status IN ('queued', 'evaluated', 'failed') AND c.id IN ({marks}))"
                       " GROUP BY c.id ORDER BY (scored IS NULL) DESC, (scored IS NULL AND waiting) DESC, (scored IS NULL AND resident) DESC,"
                       " scored, c.evaluated LIMIT ?", (*ids, *ids, int(limit)))
        return [r for r in rows if self._desk(r["niche"]) is not None]

    def resident_candidate(self, agent: Any) -> str | None:
        """The lab's id of a living agent's current program: its file with its parameters written in,
        exactly as `seed` admits it, so its seed row (once seeded) is this id. None for a file with no
        single literal PARAMS."""
        key = (str(agent.id), str(agent.code_sha256), json.dumps(agent.params or {}, sort_keys=True))
        cache = self._resident_ids
        if key not in cache:
            literal = static_literal(agent.code, "PARAMS") or {}
            params = {**literal, **dict(agent.params or {})}
            code = with_params(agent.code, params) if params != literal else agent.code
            if len(cache) >= 4096:
                cache.clear()
            cache[key] = candidate_id(code) if code else None
        return cache[key]

    def _residents(self) -> dict[str, Any]:
        """Candidate id -> the living agent whose current program it is, on every desk the lab searches."""
        out: dict[str, Any] = {}
        for agent in self.house.registry.living():
            if self._desk(agent.specialty or "") is None:
                continue
            ident = self.resident_candidate(agent)
            if ident and (ident not in out or self._program_frozen(agent) > self._program_frozen(out[ident])):
                out[ident] = agent  # twins: the later freeze, so the window is after both
        return out

    def _program_frozen(self, agent: Any) -> float:
        """When a resident's current program was frozen: its birth, or its latest `agent.strategy` row
        (a rewrite; a parameter repair). Its selection -- the replay that seated it -- saw nothing after."""
        from .house import _epoch

        last = self.house.ledger.last("agent.strategy", agent=agent.id)
        return max(_epoch(agent.born_at), _epoch(last.at) if last is not None else 0.0)

    def resident_forward(self, agent: Any, *, ranked: bool = False) -> float | None:
        """A resident's own forward record (S2), which the House's seat market compares a newcomer's
        forward score with (`House._displaceable`): the mean log growth per block of its current program's
        latest forward window, whatever its active blocks (a resident that barely traded in its window has
        that record, and a newcomer must beat it); `ranked`, its `forward_score` (only with
        `forward_min_active_blocks`). None before its first window, or when the window failed."""
        ident = self.resident_candidate(agent)
        if not ident:
            return None
        if ranked:
            return self.forward_score(ident)
        row = self.forward_record(ident)
        if row is None or not row["ok"] or row["mean_log_growth"] is None:
            return None
        return float(row["mean_log_growth"])

    def can_score(self, agent: Any) -> bool:
        """Whether a forward window can ever give this living agent's current program a record (the House's
        seat market keeps a trader's seat while it waits for one): its desk is one the lab searches (`_desk`:
        never a dormant, unreplayed or options desk), its file has a single literal PARAMS
        (`resident_candidate`), and the lab has not blocked that program. The review of #245 (Sept 24, 2026):
        alpaca-options is never searched, so krasker-6, -10, -11 and -14 (3-8 fills at T0) could never have a
        record, and the forward rule kept their seats against every newcomer for good."""
        if self._desk(getattr(agent, "specialty", None) or "") is None:
            return False
        ident = self.resident_candidate(agent)
        if not ident:
            return False
        rows = self._q("SELECT status FROM candidates WHERE id=?", (ident,))
        return not rows or rows[0]["status"] != "blocked"

    def _frozen_at(self, row: Mapping[str, Any]) -> float:
        """When this candidate's code was frozen: its evaluation, or its graduation's pass (the
        House's replay, whose tape ended no later) when it has one. Nothing after it was seen."""
        from .house import _epoch

        frozen = float(row["evaluated"] or row["created"])
        passed = self.house.ledger.get(f"lab.graduate:{row['id']}:passed")
        if passed is not None:
            frozen = max(frozen, _epoch(passed.at))
        return frozen

    def _forward_tape(self, needs: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        """(tape id, tape) a forward window is cut from: the House's own tape for these NEEDS, with
        the same seal (`check_dev_only`), except on the desks the House replays on the history store
        (Alpaca, no live feed, not options), whose House tape is 2025: there the lab builds the live
        tape of the last `forward_days` days through the House's own data adapter, as `House.tape_for`
        builds a live one, once a run."""
        from .agents import niche_of

        house = self.house
        venue, horizon, _ = niche_of(needs)
        option = venue == "alpaca" and str(needs.get("asset_class") or "") == "option"
        wanted = house._feeds_wanted(needs)
        if not (venue == "alpaca" and bool(house.settings.deep_replay) and not option and not wanted):
            tape_id, tape = house.tape_for(needs)
            check_dev_only(tape, house.holdout_window)
            return tape_id, tape
        if needs.get("options_features"):
            raise LabError("no live tape carries options features for a forward window")
        if getattr(house, "alpaca_data", None) is None:
            raise LabError("no Alpaca data adapter to build a live tape from")
        key = tape_key(needs)
        hit = self._forward_tapes.get(key)
        if hit is not None and self._now() - hit[0] < float(self.settings["forward_every_minutes"]) * 60:
            return hit[1], hit[2]
        end = self._now()
        start = end - float(self.settings["forward_days"]) * 86400
        watched = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
        symbols = sorted(str(s) for s in (needs.get("symbols") or []))[:12]
        symbols = sorted(set(symbols) | {str(s) for s in (watched.get("symbols") or [])[:6]})
        timeframe = str((needs.get("bars") or {}).get("timeframe") or "5Min")
        warmup = max(1, min(500, int((needs.get("bars") or {}).get("limit") or 120)))
        tape = house.alpaca_data.tape(symbols, timeframe, start=now_iso(lambda: start), end=now_iso(lambda: end), horizon=horizon,
                                      warmup_bars=warmup)
        check_dev_only(tape, house.holdout_window)
        ident = f"live:alpaca:{','.join(symbols)}:{timeframe}:{warmup}:{horizon}:{_iso(end)}"
        if len(self._forward_tapes) >= 8:
            self._forward_tapes.pop(next(iter(self._forward_tapes)))
        self._forward_tapes[key] = (self._now(), ident, tape)
        return ident, tape

    def _forward_warn(self, text: str) -> None:
        if text != self._forward_error:
            self._forward_error = text
            self.house.alert("warning", text)

    def forward_windows(self, *, force: bool = False) -> dict[str, Any] | None:
        """One forward-window run (S2, Sept 23, 2026), every `forward_every_minutes`: the due
        elites, waiting graduates and living residents' programs (`forward_due`) are replayed on the
        lab box on the steps of their tape that came after their code was frozen (`forward_cut`, at
        the hour after the freeze, so one batch serves every candidate frozen in that hour; a
        resident's on the `forward_resident_cut_hours` grid after its program's freeze), and each
        gets one row of the `forward` table. Bounded: `forward_candidates_per_run` candidates, `forward_box_seconds`
        of box time. What it never does: write to the ledger, touch a candidate's fitness, gate or
        cell, the archive, the holdout or anyone's rung. The stamp `forward_at` is set after the
        run, so a run a crash interrupts is run again next step, least recently scored first."""
        settings = self.settings
        every = float(settings["forward_every_minutes"]) * 60
        if not force and self._now() - float(self._meta("forward_at") or 0) < every:
            return None
        out: dict[str, Any] = {"candidates": 0, "scored": 0, "batches": 0, "seconds": 0.0, "skipped": {}}
        started = time.monotonic()
        row1 = CONSTITUTION["rungs"]["1"]
        limits = {"max_position_usd": float(row1["max_position_usd"]), "max_order_usd": float(row1["max_order_usd"])}
        groups: dict[tuple[str, float], list[sqlite3.Row]] = {}
        residents = self._residents()
        grid = max(1.0, float(settings["forward_resident_cut_hours"])) * 3600.0
        for row in self.forward_due(int(settings["forward_candidates_per_run"]), residents):
            try:
                key = tape_key(json.loads(row["needs"]))
            except (TypeError, ValueError):
                continue
            out["candidates"] += 1
            resident = residents.get(row["id"])
            if resident is not None:
                # A resident's program: its window starts after its program was frozen (S2), on a coarser grid.
                cut = math.ceil(self._program_frozen(resident) / grid) * grid
                out["residents"] = out.get("residents", 0) + 1
            else:
                cut = math.ceil(self._frozen_at(row) / 3600.0) * 3600.0
            groups.setdefault((key, cut), []).append(row)

        def skip(why: str, n: int) -> None:
            out["skipped"][why] = out["skipped"].get(why, 0) + n

        for (key, cut), rows in groups.items():
            if time.monotonic() - started >= float(settings["forward_box_seconds"]):
                skip("the run's box seconds are spent", len(rows))
                continue
            if self.open():
                skip("the lab closed", len(rows))
                continue
            try:
                base_id, base = self._forward_tape(json.loads(rows[0]["needs"]))
            except LabError as exc:
                skip(str(exc)[:80], len(rows))
                continue
            except Exception as exc:  # noqa: BLE001 - no tape is no window, never a crash of the step
                self._forward_warn(f"the lab could not build a forward tape ({type(exc).__name__}: {str(exc)[:160]})")
                skip("no tape", len(rows))
                continue
            tape = forward_cut(base, cut)
            if tape is None:
                skip("no forward data yet", len(rows))
                continue
            steps = tape["steps"]
            ident = "fwd:" + hashlib.sha256(f"{base_id}|{cut}|{steps[0].get('t')}|{steps[-1].get('t')}|{len(steps)}".encode()).hexdigest()[:24]
            batch = [{"id": r["id"], "code": r["code"], "params": {}} for r in rows]
            try:
                results = self.box.evaluate(batch, ident, tape, stake=float(row1["stake_usd"]), limits=limits, timeout=float(settings["timeout"]))
            except Exception as exc:  # noqa: BLE001 - the box's failure, never a record against anyone
                self._forward_warn(f"the lab box could not run a forward window ({type(exc).__name__}: {str(exc)[:160]})")
                skip("the lab box failed", len(rows))
                break
            by_id = {str(r.get("id")): r for r in results or [] if isinstance(r, Mapping)}
            end = _ts(steps[-1].get("t")) or self._now()
            for r in rows:
                result = by_id.get(r["id"])
                if result is None or str(result.get("error") or "").startswith("not evaluated"):
                    skip("not evaluated", 1)
                    continue
                self._record_forward(r["id"], result, cut, end, ident)
                out["scored"] += 1
            out["batches"] += 1
        out["seconds"] = round(time.monotonic() - started, 3)
        out["at"] = now_iso(self.house.clock)
        self._set_meta("forward_at", str(self._now()))
        self._forward_last = out
        self._weights = None
        return out

    def _record_forward(self, candidate: str, result: Mapping[str, Any], start: float, end: float, tape_id: str) -> None:
        blocks = [b for b in (result.get("blocks") or []) if isinstance(b, Mapping)]
        growth = [float(b.get("log_growth") or 0.0) for b in blocks]
        ok = bool(result.get("ok"))
        self._x("INSERT OR REPLACE INTO forward(candidate, at, window_start, window_end, tape_id, ok, blocks, active_blocks, log_growth,"
                " mean_log_growth, trades, error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (candidate, self._now(), start, end, tape_id, int(ok), len(blocks), sum(1 for b in blocks if b.get("active")),
                 round(math.fsum(growth), 12) if growth else None, round(math.fsum(growth) / len(growth), 12) if growth else None,
                 int(result.get("trades") or 0), None if ok else str(result.get("error") or "")[:300]))

    def forward_record(self, candidate: str) -> dict[str, Any] | None:
        """The candidate's latest forward window, or None: `window_start`/`window_end` (epochs),
        `blocks`, `active_blocks`, `log_growth`, `mean_log_growth`, `trades`, `ok`, `error`, `at`."""
        rows = self._q("SELECT * FROM forward WHERE candidate=? ORDER BY at DESC LIMIT 1", (candidate,))
        return dict(rows[0]) if rows else None

    def forward_score(self, candidate: str) -> float | None:
        """The candidate's forward record as a rank: its mean log growth per block on data that came
        after its code was frozen, or None without `forward_min_active_blocks` active blocks of
        it. A number to sort by (the House's seat market reads it), never practice evidence and
        never a promotion."""
        row = self.forward_record(candidate)
        if row is None or not row["ok"] or row["mean_log_growth"] is None:
            return None
        if int(row["active_blocks"]) < int(self.settings["forward_min_active_blocks"]):
            return None
        return float(row["mean_log_growth"])

    def forward_scores(self) -> dict[str, float]:
        """`forward_score` for every candidate with one, in one query."""
        floor = int(self.settings["forward_min_active_blocks"])
        rows = self._q("SELECT f.candidate, f.ok, f.active_blocks, f.mean_log_growth FROM forward f"
                       " JOIN (SELECT candidate, MAX(at) AS at FROM forward GROUP BY candidate) m ON m.candidate = f.candidate AND m.at = f.at")
        return {r["candidate"]: float(r["mean_log_growth"]) for r in rows
                if r["ok"] and r["mean_log_growth"] is not None and int(r["active_blocks"]) >= floor}

    def lineage_forward(self, lineage: str) -> dict[str, Any]:
        """A lineage's pooled forward record: the latest window of each of its candidates.
        `positive` is None until the pool has `forward_min_active_blocks` active blocks."""
        rows = self._q("SELECT f.blocks, f.active_blocks, f.log_growth FROM forward f"
                       " JOIN (SELECT candidate, MAX(at) AS at FROM forward GROUP BY candidate) m ON m.candidate = f.candidate AND m.at = f.at"
                       " JOIN candidates c ON c.id = f.candidate WHERE c.lineage=? AND f.ok=1", (lineage,))
        active = sum(int(r["active_blocks"]) for r in rows)
        growth = math.fsum(float(r["log_growth"] or 0.0) for r in rows)
        return {"candidates": len(rows), "blocks": sum(int(r["blocks"]) for r in rows), "active_blocks": active,
                "log_growth": round(growth, 12),
                "positive": None if active < int(self.settings["forward_min_active_blocks"]) else growth > 0}

    def forward_stats(self) -> dict[str, Any]:
        """The forward windows' line in `lab.stats` and health.json: the last run, how many
        candidates carry a record, how many rank (and win), and the priors in force."""
        at = self._meta("forward_at")
        records = int(self._q("SELECT COUNT(DISTINCT candidate) AS n FROM forward")[0]["n"])
        scores = self.forward_scores()
        return {"last_run_at": _iso(float(at)) if at else None, "last_run": self._forward_last, "records": records,
                "ranked": len(scores), "positive": sum(1 for s in scores.values() if s > 0),
                "priors": {"active": sorted({str(p.get("title")) for p in self.priors()}), "skipped": dict(self._prior_skips)}}

    # ---------------------------------------------------------------- priors
    def priors(self) -> list[dict[str, Any]]:
        """The lab priors in force (S2, Sept 23, 2026): every ```lab-prior``` block in the latest
        text of each lesson in the ledger's playbook (`playbook.entry`, which `House.learn` writes
        from `league/playbook/*.md`, once per lesson and again when its text changes), each with the
        lesson's title. Read at most every ten minutes."""
        now = self._now()
        if self._priors is not None and now - self._priors[0] < 600:
            return self._priors[1]
        latest: dict[str, str] = {}
        for entry in self.house.ledger.iter(kinds="playbook.entry"):
            latest[str(entry.payload.get("title"))] = str(entry.payload.get("text") or "")
        out = []
        for title, text in latest.items():
            out.extend({**prior, "title": title} for prior in parse_priors(text))
        self._priors = (now, out)
        return out

    def _family_of(self, lineage: str) -> str:
        """The House family the lab lineage grew from ('' for a Sol leap)."""
        registry = self.house.registry
        for ident in self._origin(lineage):
            agent = registry.get(ident)
            if agent is not None:
                return str(agent.family or "")
        return ""

    def _prior_matches(self, prior: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
        if prior.get("lineage") and prior["lineage"] != row["lineage"]:
            return False
        if prior.get("niche") and prior["niche"] != row["niche"]:
            return False
        if prior.get("cell") and not str(row["cell"] or "").startswith(str(prior["cell"])):
            return False
        if prior.get("family") and str(prior["family"]).lower() not in self._family_of(row["lineage"]).lower():
            return False
        return True

    def _prior_lifted(self, prior: Mapping[str, Any], lineage: str) -> bool:
        until = str(prior.get("until") or "")
        if until == "forward-positive":
            return self.lineage_forward(lineage)["positive"] is True
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
            return _iso(self._now())[:10] >= until
        return False

    def paused(self, row: Mapping[str, Any]) -> str | None:
        """Why no parameter mutant of this elite is bred now: the title of the lesson whose
        `pause-param-forks` prior names its lineage (by family, lineage, desk or cell) and has not
        been lifted (`until`), or None."""
        for prior in self.priors():
            if prior.get("rule") != "pause-param-forks":
                continue
            if self._prior_matches(prior, row) and not self._prior_lifted(prior, row["lineage"]):
                return str(prior.get("title"))
        return None

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
                     "the whole tape (its last third unseen by the lab's search) and, on the history store, by the sealed holdout; only "
                     "then is it born, and only with a change to its code beyond PARAMS relative to the desk's living programs or a "
                     "forward score above the desk's living median, never on a losing forward window, and never onto a desk that "
                     "wrote no order in 48 hours of markets unless a feed it asked for arrived. Submitting is not a trial against you, but a program that grew from your line is "
                     "judged at graduation against every trial on your line, as your own child would be. To adopt or fork "
                     "a program you still `replay` it."),
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
        waiting = self.waiting()
        closed = self._meta("closed_since")
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
            # Sept 23, 2026: the paid phases skipped and why (C2), since when the lab has been closed,
            # and the graduates waiting for seats (the two invariants), as `health()` shows them.
            "llm": {"paused": self._llm_paused or None, "skipped": dict(self._skipped)},
            "closed_since": _iso(float(closed)) if closed is not None else None,
            # D1 (Sept 24, 2026): whether the step is failing, as `health()` shows it.
            **self._failing(),
            "waiting_seat": {"count": len(waiting), "longest_hours": waiting[0]["hours"] if waiting else 0},
            # S2 (Sept 23, 2026): the forward windows' last run and records, and the priors in force.
            "forward": self.forward_stats(),
            # E1 (Sept 24, 2026): the written programs' share of the window's evaluations, beside the
            # share of each batch reserved for them, and what the last graduation pass held back and why.
            "reserved": {"share": _share(self.settings.get("reserved_share")),
                         "evaluated": int(self._q(f"SELECT COUNT(*) AS n FROM candidates WHERE evaluated>=? AND status!='queued' AND origin IN "
                                                  f"({','.join('?' for _ in RESERVED_ORIGINS)})", (since, *RESERVED_ORIGINS))[0]["n"])},
            "held": self._held or None,
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
