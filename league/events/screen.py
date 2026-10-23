"""The event lane's judge: PREREG-EVL-1 section 7 (the screen), and the bootstrap bounds sections 8 and 9 read.

Built to the frozen text (docs/prereg/PREREG-EVL-1.md, sha256 f8254c19..., tag prereg-evl-1, registered
2026-10-19T01:08:38Z). What section 7 says, and all this module does with it:
- SESSIONS AND BLOCKS. A program's sessions are numbered from its first entry session; each entry session is one block
  (every seatable program holds one session); an empty session has no block. A block's value is the mean abnormal
  return `a` of its TRADABLE events.
- LOOKS. Look k = 1..7 is as of the close of the program's session S_k (10, 15, 20, 30, 40, 60, 90), counting the
  session of its first settled exit as session 1. It covers every block whose scheduled exits are at or before that
  close and is computed once all of them have settled (fallback exits included): late data delays the computation,
  never its as-of date. HELD only with >= 60 settled TRADABLE events, >= 40 distinct issuers among them and >= 10
  blocks; otherwise skipped, never deferred.
- SIGN-FLIP p: (1 + #{v : mean(s_v x) >= mean(x) - 1e-12}) / (1 + 99,999), the sign vectors
  `random.Random(seed).getrandbits(n)` (bit j set = +1 for value j), seed = int.from_bytes(sha256(seed string)
  .digest()[:8], "big"), seed string f"{id}|v{version}|look{k}"; ties count against the program.
- SKEW CHECK at every held look, before p: the values centred to mean zero, 1,000 bootstrap samples of the same count
  (each index `r.randrange(n)`, r seeded by the seed string + "|skew"), f = the share with mean > 0 and p <= alpha, every
  p over one shared set of 1,999 sign vectors (seed string + "|skewflip"); alpha starts at 0.024 and falls by 0.002
  while f > 0.024 (floor 0.002). f and alpha are recorded before p.
- PASS: session-block p <= alpha AND the ISSUER-block test (each issuer's TRADABLE events averaged into one value, in
  ascending CIK order, seed string + "|issuer", its own skew check) has p <= its alpha AND the TRADABLE events' mean a
  > 0 AND their mean r > 0 AND, for a READ program, its mean block value exceeds its control's over the same sessions
  (the control's TRADABLE events in those blocks).

Speed (the captain's method): a vector's signed sum is read from 8-bit tables, one 256-entry table of partial signed
sums per run of 8 consecutive values, summed over the n/8 bytes of the same getrandbits bits; with the prereg's 1e-12
tie tolerance it counts exactly the vectors the direct sum counts (tests compare the two). Every pinned sum is a
`math.fsum`, so Python 3.11 and 3.14 agree to the bit (3.12+ compensates plain `sum()` of floats, 3.11 does not).

Readings taken where the prereg leaves room (the one LESS LIKELY TO PASS; recorded as amendments):
- A session whose events include no TRADABLE one has no block value, so it is no block: it neither counts toward the
  10 nor enters the test. An event whose tradability is unknown (no equity on record) is not TRADABLE.
- "Its first settled exit" is the session in which the program's first settled event actually exited (a fallback exit
  counts where it happened).
- The control's mean block value is over the program's block sessions in which the control has TRADABLE events; with
  none, the condition fails.
- Bootstrap bounds: Done's 95% and Sized's 80% lower bounds are two-sided percentile bounds (the 2.5th and 10th
  percentiles); Kill's 95% upper bound (issuer blocks) is one-sided (the 95th percentile), so Kill fires sooner.

Standard library only. `calibration` re-implements calibrate_looks.py's null (beside the prereg) without numpy.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import random
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import store as S

ALPHA = 0.024
B = 99_999
TIE = 1e-12
LOOKS: tuple[tuple[int, int], ...] = ((1, 10), (2, 15), (3, 20), (4, 30), (5, 40), (6, 60), (7, 90))
MIN_EVENTS = 60
MIN_ISSUERS = 40
MIN_BLOCKS = 10
SKEW_SAMPLES = 1000
SKEW_DRAWS = 1999
SKEW_CAP = 0.024
SKEW_STEP = 0.002
SKEW_FLOOR = 0.002
FALSE_PASS_RATE = 0.10  # expected false passes = 0.10 x every seatable version ever registered
#: PREREG-EVL-4 section 3: THE LANE'S LIFETIME BUDGET, STATED: 3.0 expected false passes (thirty seatable versions at
#: 0.10); each later file states its draw against what is left.
LANE_BUDGET = 3.0
#: PREREG-EVL-3 section 3: version 2's looks are counted in settled TRADABLE events, each with >= 40 issuers and
#: >= 8 session blocks; the skew check starts (and caps, the stricter reading of the frozen text: A65) at 0.018.
V2_NS: tuple[int, ...] = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
V2_MIN_ISSUERS = 40
V2_MIN_BLOCKS = 8
V2_ALPHA = 0.018

SEATABLE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1",
            # PREREG-EVL-2 (registered 2026-10-19T03:04:07Z), judged by this screen unchanged
            "EVL-ERN-REACT-ON", "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON",
            # PREREG-EVL-4 (registered 2026-10-19T16:01:05Z): seatable from birth at version 1, judged by PREREG-EVL-3's
            # screen unchanged (`_seating`: their version 1 runs `_run_v2`)
            "EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON",
            # PREREG-EVL-5 (registered 2026-10-21T21:26:21Z): the same, at version 1 (its section 2)
            "EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON")
RECORDS = ("EVL-ERN-READ-O3", "EVL-INS-CLUSTER-O5", "EVL-CTRL-ERN-ALL-O1", "EVL-CTRL-8K-ALL-O1", "EVL-CTRL-NEWS-ALL-O1",
           "EVL-INS-BUY-O5", "EVL-ERN-REACT-READ-C1", "EVL-ERN-READ3-O1", "EVL-CTRL-NEWS-DAY-ON",
           # PREREG-EVL-4's controls (free records: never seated, never screened)
           "EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON",
           # PREREG-EVL-5's control (section 4)
           "EVL-CTRL-ERN-UNDER-ON")
#: A READ program's control (its mean block value must exceed the control's over the same sessions).
CONTROLS: dict[str, str] = {"EVL-ERN-READ-O1": "EVL-CTRL-ERN-ALL-O1", "EVL-8K-READ-O1": "EVL-CTRL-8K-ALL-O1",
                            "EVL-NEWS-READ-O1": "EVL-CTRL-NEWS-ALL-O1",
                            "EVL-ERN-GUIDE-O1": "EVL-CTRL-ERN-ALL-O1", "EVL-NEWS-READ-ON": "EVL-CTRL-NEWS-DAY-ON",
                            # PREREG-EVL-4 section 4 (EVL-8K-REACT-ON reads no verdict and has no control condition)
                            "EVL-8K-READ-ON": "EVL-CTRL-8K-ON", "EVL-NEWSPM-READ-ON": "EVL-CTRL-NEWSPM-ON",
                            # PREREG-EVL-5 section 4 (EVL-ERN-DROP-ON and EVL-NEWS-NIGHT2-ON read no verdict and have none)
                            "EVL-ERN-UNDER-ON": "EVL-CTRL-ERN-UNDER-ON",
                            # PREREG-EVL-8 section 3.2 (A122, release 1019n: "screen.CONTROLS gains these three rows"):
                            # its PX seats' control condition, judged by its own screen (league/events/screen8.py),
                            # never by this module's; a look of one freezes its group's re-decision (run.py `_group`)
                            "PX-DROP-ON": "CTRL-PX-ALL-ON", "PX-SURGE-ON": "CTRL-PX-ALL-ON", "PX-GAP-O1": "CTRL-PX-ALL-O1"}
#: Sessions held as the prereg counts them (C1, close to next close, holds one; PREREG-EVL-2's, PREREG-EVL-4's and
#: PREREG-EVL-5's close-to-next-open programs hold one). The screen judges only the seatable programs, every one a one-session hold,
#: so each of their blocks is one entry session.
HOLDS: dict[str, int] = {"EVL-ERN-READ-O1": 1, "EVL-ERN-REACT-C1": 1, "EVL-8K-READ-O1": 1, "EVL-NEWS-READ-O1": 1,
                         "EVL-ERN-READ-O3": 3, "EVL-INS-CLUSTER-O5": 5, "EVL-CTRL-ERN-ALL-O1": 1, "EVL-CTRL-8K-ALL-O1": 1,
                         "EVL-CTRL-NEWS-ALL-O1": 1,
                         "EVL-ERN-REACT-ON": 1, "EVL-ERN-GUIDE-O1": 1, "EVL-INS-BUY-O1": 1, "EVL-NEWS-READ-ON": 1,
                         "EVL-NEWS-REACT-ON": 1, "EVL-INS-BUY-O5": 5, "EVL-ERN-REACT-READ-C1": 1, "EVL-ERN-READ3-O1": 1,
                         "EVL-CTRL-NEWS-DAY-ON": 1,
                         "EVL-8K-REACT-ON": 1, "EVL-8K-READ-ON": 1, "EVL-NEWSPM-READ-ON": 1, "EVL-CTRL-8K-ON": 1,
                         "EVL-CTRL-NEWSPM-ON": 1,
                         "EVL-ERN-DROP-ON": 1, "EVL-ERN-UNDER-ON": 1, "EVL-NEWS-NIGHT2-ON": 1, "EVL-CTRL-ERN-UNDER-ON": 1}


# ----------------------------------------------------------------------------------------------------------- basics
def _day(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def _mean(xs: Sequence[float]) -> float | None:
    return math.fsum(xs) / len(xs) if xs else None


def _tradable(row: Mapping[str, Any]) -> bool:
    return row.get("tradable") in (True, 1)


def seed_string(program: str, version: int, k: int) -> str:
    return f"{program}|v{version}|look{k}"


def seed_of(text: str) -> int:
    """int.from_bytes(sha256(text).digest()[:8], "big")."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def values_sha(values: Sequence[float]) -> str:
    """A fingerprint of a test's values (a skew check on record is reused only for the very values it was run on)."""
    return hashlib.sha256(",".join(repr(float(v)) for v in values).encode("ascii")).hexdigest()


def look_seed(program: str, version: int, k: int) -> int:
    """The session-block test's seed at look k (the issuer-block test's is seed_of(seed_string(...) + "|issuer"))."""
    return seed_of(seed_string(program, version, k))


# ----------------------------------------------------------------------------------------------------------- blocks
@dataclasses.dataclass(frozen=True)
class Block:
    index: int       # position of the entry session among the program's sessions (first entry session = 0) // hold
    day: dt.date     # its (first) entry session
    n: int           # its TRADABLE events
    value: float     # their mean a (the test's unit)
    mean_r: float    # their mean after-cost r (the raw-r test beside the look)


def blocks(rows: Iterable[Mapping[str, Any]], sessions: Sequence[Any], hold: int = 1) -> list[Block]:
    """The blocks of settled events `rows` ({entry_day, a, r, tradable, ...}), in order. `sessions` is the ordered list
    of the program's session dates from its first entry session on; block index = floor(position / hold) (hold = 1 for
    every seatable program). A block's value is the mean a of its TRADABLE events; a block without one does not exist."""
    if int(hold) < 1:
        raise ValueError("a hold is at least one session")
    days = [_day(d) for d in sessions]
    if any(b <= a for a, b in zip(days, days[1:])):
        raise ValueError("sessions must be strictly increasing")
    pos = {d: i for i, d in enumerate(days)}
    groups: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        day = _day(row["entry_day"])
        if day not in pos:
            raise ValueError(f"entry day {day} is not one of the program's sessions")
        if not _tradable(row):
            continue
        a, r = row["a"], row["r"]
        if a is None or r is None or not (math.isfinite(float(a)) and math.isfinite(float(r))):
            raise ValueError(f"event {row.get('event')} has no finite a and r")
        groups.setdefault(pos[day] // int(hold), []).append(row)
    return [Block(i, days[i * int(hold)], len(g), math.fsum(float(x["a"]) for x in g) / len(g),
                  math.fsum(float(x["r"]) for x in g) / len(g)) for i, g in sorted(groups.items())]


def issuer_values(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, float]]:
    """[(issuer, mean a of its TRADABLE events)] in ascending CIK order: the issuer-block test's values."""
    groups: dict[str, list[float]] = {}
    for row in rows:
        if _tradable(row):
            groups.setdefault(str(row["issuer"]), []).append(float(row["a"]))
    return [(k, math.fsum(v) / len(v)) for k, v in sorted(groups.items())]


# ------------------------------------------------------------------------------------------------------------ looks
def look_schedule() -> list[tuple[int, int]]:
    """[(k, S_k)]: look k as of the close of session S_k, the first settled exit's session being session 1."""
    return list(LOOKS)


def look_number(sessions_count: int) -> int | None:
    for k, s in LOOKS:
        if s == sessions_count:
            return k
    return None


def minimums(n_tradable: int, issuers: int, n_blocks: int, *, mins: tuple[int, int, int] | None = None) -> tuple[bool, str]:
    """(held, why): >= 60 settled TRADABLE events, >= 40 distinct issuers among them, >= 10 blocks (version 1);
    `mins` = (events, issuers, blocks) for another version's look (PREREG-EVL-3: (N_k, 40, 8))."""
    min_events, min_issuers, min_blocks = mins or (MIN_EVENTS, MIN_ISSUERS, MIN_BLOCKS)
    short = []
    if n_tradable < min_events:
        short.append(f"tradable events {n_tradable} < {min_events}")
    if issuers < min_issuers:
        short.append(f"issuers {issuers} < {min_issuers}")
    if n_blocks < min_blocks:
        short.append(f"blocks {n_blocks} < {min_blocks}")
    return (not short, "held" if not short else "skipped: " + "; ".join(short))


# ------------------------------------------------------------------------------------------------------- sign flips
def _check_values(values: Sequence[Any]) -> list[float]:
    out = [float(v) for v in values]
    if not out:
        raise ValueError("a sign-flip test needs at least one value")
    if not all(math.isfinite(v) for v in out):
        raise ValueError("a sign-flip test needs finite values")
    return out


def _tables(values: Sequence[float]) -> list[list[float]]:
    """For each run of 8 consecutive values (the last may be shorter), the table of its signed sums: entry b = the
    sum over the run of (+v_i when bit i of b is set, else -v_i), built in one fixed order."""
    out = []
    for start in range(0, len(values), 8):
        t = [0.0]
        for v in values[start:start + 8]:
            t = [x - v for x in t] + [x + v for x in t]
        out.append(t)
    return out


def _count(values: Sequence[float], flips: Iterable[bytes], stop: int | None = None) -> int:
    """#{v : mean(s_v x) >= mean(x) - 1e-12}, s_v's bits given as little-endian bytes (byte k = values 8k..8k+7).
    With `stop`, counting ends once the count passes it (the caller needs only to know that)."""
    tables = _tables(values)
    threshold = math.fsum(values) - len(values) * TIE  # n mean(s x) >= n mean(x) - n 1e-12
    fsum, getitem = math.fsum, list.__getitem__
    count = 0
    for flip in flips:
        if fsum(map(getitem, tables, flip)) >= threshold:
            count += 1
            if stop is not None and count > stop:
                break
    return count


def _flips(seed: int, n: int, draws: int) -> Iterable[bytes]:
    rng = random.Random(seed)
    width = (n + 7) // 8
    return (rng.getrandbits(n).to_bytes(width, "little") for _ in range(int(draws)))


def _stop(alpha: float, draws: int) -> int:
    """The largest count c with (1 + c) / (1 + draws) <= alpha (-1: none)."""
    stop = -1
    while (stop + 2) / (draws + 1) <= alpha:
        stop += 1
    return stop


def signflip_p(values: Sequence[float], seed: int, B: int = B) -> float:  # noqa: N803 - the prereg's name
    """One-sided sign-flip p of the mean of `values`: (1 + #{v : mean(s_v x) >= mean(x) - 1e-12}) / (1 + B), the B
    sign vectors `random.Random(seed).getrandbits(n)` (bit j set = +1 for value j); ties count against the program."""
    vals = _check_values(values)
    return (1 + _count(vals, _flips(seed, len(vals), B))) / (1 + int(B))


# ------------------------------------------------------------------------------------------------------- skew check
def skew_check(values: Sequence[float], seed_text: str, *, alpha: float = ALPHA, samples: int = SKEW_SAMPLES,
               draws: int = SKEW_DRAWS, cap: float = SKEW_CAP, step: float = SKEW_STEP,
               floor: float = SKEW_FLOOR) -> dict[str, Any]:
    """One test's skew check: the values centred to mean zero, `samples` bootstrap samples of the same count (each
    index `r.randrange(n)`, r = random.Random(seed_of(seed_text + "|skew"))), f(alpha) = the share of samples with
    mean > 0 and p <= alpha, every p over the same `draws` sign vectors (seed_text + "|skewflip"). alpha starts at
    `alpha` and falls by `step` while f > cap, never below `floor`. A sample's count stops once it cannot pass."""
    started = time.perf_counter()
    vals = _check_values(values)
    n = len(vals)
    centre = math.fsum(vals) / n
    centred = [v - centre for v in vals]
    rng = random.Random(seed_of(seed_text + "|skew"))
    flips = list(_flips(seed_of(seed_text + "|skewflip"), n, draws))
    stop = _stop(alpha, draws)
    counts: list[int] = []  # per sample that could pass: its count
    for _ in range(int(samples)):
        x = [centred[rng.randrange(n)] for _ in range(n)]
        if math.fsum(x) > 0.0:
            c = _count(x, flips, stop=stop)
            if c <= stop:
                counts.append(c)
    grid = []
    for j in range(int(round(float(alpha) / step)) + 1):
        a = round(float(alpha) - j * step, 6)
        if a < floor - 1e-12:
            break
        grid.append(a)
    f_by = {a: sum(1 for c in counts if (1 + c) / (1 + draws) <= a) / int(samples) for a in grid}
    chosen = grid[-1]
    for a in grid:
        if f_by[a] <= cap:
            chosen = a
            break
    return {"f": f_by[chosen], "alpha": chosen, "f_start": f_by[grid[0]],
            "f_by_alpha": {f"{a:.3f}": f_by[a] for a in grid}, "samples": int(samples), "draws": int(draws), "n": n,
            "seed": seed_text, "values_sha": values_sha(vals), "seconds": round(time.perf_counter() - started, 3)}


# ------------------------------------------------------------------------------------------------------- judge look
def look_figures(rows: Sequence[Mapping[str, Any]], sessions: Sequence[Any], *,
                 mins: tuple[int, int, int] | None = None) -> dict[str, Any]:
    """Everything a look reads from its covered settled events `rows` (tradable or not), no test."""
    trad = [r for r in rows if _tradable(r)]
    blk = blocks(rows, sessions, 1)
    iss = issuer_values(rows)
    held, why = minimums(len(trad), len(iss), len(blk), mins=mins)
    bench = [float(r["b"]) for r in trad if r.get("b") is not None]
    stress = [float(r["stress_r"]) for r in trad if r.get("stress_r") is not None]
    late = [r["late"] for r in rows if r.get("late") is not None]
    mean_r = _mean([float(r["r"]) for r in trad])
    mean_b = _mean(bench) if trad and len(bench) == len(trad) else None
    return {
        "tradable": trad, "block_list": blk, "issuer_list": iss, "held": held, "why": why,
        "n": len(trad), "issuers": len(iss), "blocks": len(blk),
        "mean_a": _mean([float(r["a"]) for r in trad]), "mean_r": mean_r,
        "block_mean": _mean([b.value for b in blk]),
        "all": {"n": len(rows), "issuers": len({str(r["issuer"]) for r in rows}),
                "mean_a": _mean([float(r["a"]) for r in rows]), "mean_r": _mean([float(r["r"]) for r in rows])},
        "mean_b": mean_b, "market_share": (mean_b / mean_r) if (mean_b is not None and mean_r) else None,
        "n_stress": len(stress), "mean_stress_r": _mean(stress) if trad and len(stress) == len(trad) else None,
        "late_share": (sum(1 for x in late if x) / len(late)) if late else None,
    }


def control_mean(control_rows: Iterable[Mapping[str, Any]], days: Iterable[dt.date]) -> tuple[float | None, int]:
    """(the control's mean block value over these sessions, how many of them it has a block in): the control's
    TRADABLE events in each session averaged, then the sessions averaged."""
    want = set(days)
    groups: dict[dt.date, list[float]] = {}
    for row in control_rows:
        day = _day(row["entry_day"])
        if day in want and _tradable(row):
            groups.setdefault(day, []).append(float(row["a"]))
    values = [math.fsum(v) / len(v) for _, v in sorted(groups.items())]
    return _mean(values), len(values)


LOOK_COLUMNS = ("program", "version", "k", "at", "sessions", "n", "issuers", "blocks", "mean_a", "mean_r",
                "mean_a_tradable", "p", "alpha", "fp_check", "held", "passed", "why")


def judge_look(rows: Sequence[Mapping[str, Any]], sessions: Sequence[Any], k: int, *, program: str, version: int,
               at: Any, control_rows: Sequence[Mapping[str, Any]] | None = None,
               alphas: Mapping[str, Any] | None = None, record: Callable[[dict[str, Any]], None] | None = None,
               draws: int = B, beside: bool = True, alpha: float = ALPHA,
               mins: tuple[int, int, int] | None = None, sessions_at: int | None = None,
               retire: bool = False) -> dict[str, Any]:
    """Look k of (program, version) on its covered settled events `rows` (all of them; the rule reads the TRADABLE
    ones), `sessions` the program's session dates from its first entry session through the as-of session.

    At a held look the two skew checks run first and `record(checks)` is called with them before any p is computed
    (`alphas` = checks already on record: reused when they were run on these very values, else run again). The `looks`
    row carries the judged (TRADABLE) figures and the
    session-block test (so mean_a_tradable equals mean_a); the issuer-block test, the control comparison, the checks
    and the figures beside the look are under `issuer`, `control`, `skew` and `beside`."""
    f = look_figures(rows, sessions, mins=mins)
    look: dict[str, Any] = {
        "program": program, "version": int(version), "k": int(k),
        "at": S.iso(at) if isinstance(at, dt.datetime) else str(at),
        "sessions": dict(LOOKS)[int(k)] if sessions_at is None else int(sessions_at),
        "n": f["n"], "issuers": f["issuers"], "blocks": f["blocks"], "mean_a": f["mean_a"], "mean_r": f["mean_r"],
        "mean_a_tradable": f["mean_a"], "p": None, "alpha": alpha, "fp_check": None, "held": int(f["held"]),
        "passed": 0, "why": f["why"], "issuer": None, "control": None, "skew": None, "retirement": None,
    }
    extra: dict[str, Any] = {"all": f["all"], "block_mean": f["block_mean"], "mean_b": f["mean_b"],
                             "market_share": f["market_share"], "n_stress": f["n_stress"],
                             "mean_stress_r": f["mean_stress_r"], "late_share": f["late_share"]}
    look["beside"] = extra
    if not f["held"]:
        return look
    text = seed_string(program, version, k)
    session_values = [b.value for b in f["block_list"]]
    issuer_vals = [v for _, v in f["issuer_list"]]
    fresh = alphas is None or any((alphas.get(t) or {}).get("values_sha") != values_sha(v)
                                  for t, v in (("session", session_values), ("issuer", issuer_vals)))
    if fresh:
        checks = {"session": skew_check(session_values, text, alpha=alpha, cap=min(SKEW_CAP, alpha)),
                  "issuer": skew_check(issuer_vals, text + "|issuer", alpha=alpha, cap=min(SKEW_CAP, alpha))}
        if record is not None:
            record(checks)  # f and alpha are on record before any p is computed
    else:
        checks = {"session": dict(alphas["session"]), "issuer": dict(alphas["issuer"])}
    a_s, a_i = float(checks["session"]["alpha"]), float(checks["issuer"]["alpha"])
    if a_s > alpha or a_i > alpha:
        raise ValueError(f"the threshold is {alpha} or lower (the skew check only tightens)")
    p_s = signflip_p(session_values, seed_of(text), draws)
    p_i = signflip_p(issuer_vals, seed_of(text + "|issuer"), draws)
    fails = []
    if not p_s <= a_s:
        fails.append(f"session p {p_s:.5f} > alpha {a_s:.3f}")
    if not p_i <= a_i:
        fails.append(f"issuer p {p_i:.5f} > alpha {a_i:.3f}")
    if not (f["mean_a"] is not None and f["mean_a"] > 0):
        fails.append("mean a <= 0")
    if not (f["mean_r"] is not None and f["mean_r"] > 0):
        fails.append("mean r <= 0")
    control = control_of(program)
    if control is not None:
        c_mean, c_blocks = control_mean(control_rows or [], [b.day for b in f["block_list"]])
        look["control"] = {"program": control, "mean_block": c_mean, "blocks": c_blocks,
                           "program_mean_block": f["block_mean"]}
        if c_mean is None:
            fails.append(f"no {control} block in these sessions")
        elif not f["block_mean"] > c_mean:
            fails.append(f"mean block {f['block_mean']:.5f} <= control {c_mean:.5f}")
    look.update(p=p_s, alpha=a_s, fp_check=float(checks["session"]["f"]), passed=int(not fails),
                why="pass" if not fails else "fail: " + "; ".join(fails), skew=checks,
                issuer={"p": p_i, "alpha": a_i, "f": float(checks["issuer"]["f"]), "values": len(issuer_vals)})
    if retire:
        from .bands import retire_test

        look["retirement"] = retire_test(session_values, f["mean_a"], text, draws)
    if beside:
        extra["p_r"] = signflip_p([b.mean_r for b in f["block_list"]], seed_of(text), draws)
    return look


def write_look(store: S.Store, look: Mapping[str, Any], *,
               apply: Callable[[Any], None] | None = None, now: dt.datetime | None = None) -> bool:
    """Write one look (one row per (program, version, k), never rewritten): False when it exists. The issuer-block
    test, the control comparison, the skew checks, the figures beside, the retirement test, (version 2) the looks
    merged into it and WHEN IT WAS WRITTEN (`written_at`, `now`: from then on a look freezes its group's records over
    the sessions it covers, league/events/run.py `_scope`; release 1019c's judges review) go to meta
    `look:<program>:<version>:<k>`. `apply(db)` runs INSIDE the same transaction once the look is new (release 1019b's
    review: the band move a version 2 look makes, league/events/bands.py `on_look`, is written with the look or not at
    all, so a look on record has always moved its band)."""
    with store.tx() as db:
        cur = db.execute(f"INSERT OR IGNORE INTO looks({', '.join(LOOK_COLUMNS)}) VALUES({', '.join('?' * len(LOOK_COLUMNS))})",
                         tuple(look[c] for c in LOOK_COLUMNS))
        if cur.rowcount != 1:
            return False
        detail = {c: look[c] for c in LOOK_COLUMNS} | {x: look.get(x) for x in ("issuer", "control", "skew", "beside",
                                                                              "retirement")}
        if look.get("v6") is not None:      # (PREREG-EVL-6: its tag, its look and S, q, p_I, the guards and figures)
            detail["v6"] = look["v6"]
        detail["written_at"] = S.iso(now or S.utc_now())
        if look.get("merged") is not None:
            detail["merged"] = [int(k) for k in look["merged"]]
        db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                   (f"look:{look['program']}:{look['version']}:{look['k']}", json.dumps(detail, sort_keys=True, default=str)))
        if apply is not None:
            apply(db)
    return True


def look_detail(store: S.Store, program: str, version: int, k: int) -> dict[str, Any] | None:
    raw = store.meta(f"look:{program}:{version}:{k}")
    return None if raw is None else json.loads(raw)


# ------------------------------------------------------------------------------------------------- bootstrap bounds
def _quantile(sorted_xs: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics (numpy's default, 'type 7')."""
    h = (len(sorted_xs) - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (h - lo) * (sorted_xs[hi] - sorted_xs[lo])


def bootstrap_bounds(rows: Sequence[Mapping[str, Any]], by: str, level: float, n: int = 10000, seed: int = 0, *,
                     sided: str = "two", value: str = "r") -> dict[str, Any]:
    """Percentile bounds of the per-event mean `value` (after-cost r) under a block bootstrap: blocks are issuers
    (by="issuer") or entry sessions (by="session"), resampled with replacement to their observed count
    (`random.Random(seed).choices`), each resample's statistic the mean over all its events. sided="two": the
    (1 - level)/2 and (1 + level)/2 percentiles; "one": the 1 - level and level percentiles."""
    if by not in ("issuer", "session"):
        raise ValueError("by is 'issuer' or 'session'")
    if not 0 < level < 1 or sided not in ("one", "two"):
        raise ValueError("level in (0, 1); sided 'one' or 'two'")
    groups: dict[Any, list[float]] = {}
    for row in rows:
        key = str(row["issuer"]) if by == "issuer" else _day(row["entry_day"])
        groups.setdefault(key, []).append(float(row[value]))
    if not groups:
        raise ValueError("no events")
    keys = sorted(groups, key=str)
    sums = [math.fsum(groups[k]) for k in keys]
    counts = [len(groups[k]) for k in keys]
    g = len(keys)
    rng = random.Random(seed)
    idx = range(g)
    stats = []
    for _ in range(int(n)):
        pick = rng.choices(idx, k=g)
        stats.append(math.fsum(map(sums.__getitem__, pick)) / sum(map(counts.__getitem__, pick)))
    stats.sort()
    lo_q, hi_q = ((1 - level) / 2, (1 + level) / 2) if sided == "two" else (1 - level, level)
    events = sum(counts)
    return {"by": by, "level": level, "sided": sided, "n": int(n), "seed": seed, "groups": g, "events": events,
            "mean": math.fsum(sums) / events, "lower": _quantile(stats, lo_q), "upper": _quantile(stats, hi_q)}


def bounds_seed(purpose: str, by: str) -> int:
    """The fixed seed of a Done / Kill / Sized bootstrap."""
    return seed_of(f"EVL-1|{purpose}|{by}")


def done_bounds(rows: Sequence[Mapping[str, Any]], n: int = 10000) -> dict[str, Any]:
    """Done's bootstrap item: the 95% lower bound (two-sided: the 2.5th percentile) of the per-event after-cost return
    above zero under BOTH the issuer-block and the session-block bootstrap."""
    out = {by: bootstrap_bounds(rows, by, 0.95, n, bounds_seed("done", by)) for by in ("issuer", "session")}
    return {"ok": all(out[by]["lower"] > 0 for by in out), **out}


def kill_bounds(rows: Sequence[Mapping[str, Any]], n: int = 10000) -> dict[str, Any]:
    """Kill's bootstrap item: the 95% upper bound (one-sided: the 95th percentile) of the per-event after-cost return
    under the issuer-block bootstrap below zero."""
    out = bootstrap_bounds(rows, "issuer", 0.95, n, bounds_seed("kill", "issuer"), sided="one")
    return {"kill": out["upper"] < 0, "issuer": out}


def sized_bound(rows: Sequence[Mapping[str, Any]], n: int = 10000) -> dict[str, Any]:
    """Sized's item: the 80% session-block lower bound (two-sided: the 10th percentile) above zero."""
    out = bootstrap_bounds(rows, "session", 0.80, n, bounds_seed("sized", "session"))
    return {"ok": out["lower"] > 0, "session": out}


# ------------------------------------------------------------------------------------------------------ calibration
def _t4(rng: random.Random) -> float:
    """Student t with 4 degrees of freedom: Z / sqrt(chi2_4 / 4), chi2_4 = -2 ln(U1 U2) (a Gamma(2, 2) draw)."""
    while True:
        u = (1.0 - rng.random()) * (1.0 - rng.random())
        if u < 1.0:
            return rng.gauss(0.0, 1.0) / math.sqrt(-0.5 * math.log(u))


def _poisson(rng: random.Random, lam: float) -> int:
    """Poisson(lam): multiplication below 10, else Hormann's PTRS (numpy's two methods)."""
    if lam <= 0:
        return 0
    if lam < 10:
        limit = math.exp(-lam)
        k, p = 0, rng.random()
        while p > limit:
            k += 1
            p *= rng.random()
        return k
    slam, loglam = math.sqrt(lam), math.log(lam)
    b = 0.931 + 2.53 * slam
    a = -0.059 + 0.02483 * b
    invalpha = 1.1239 + 1.1328 / (b - 3.4)
    vr = 0.9277 - 3.6224 / (b - 2)
    while True:
        u = rng.random() - 0.5
        v = rng.random()
        us = 0.5 - abs(u)
        if us <= 0.0:
            continue
        k = math.floor((2 * a / us + b) * u + lam + 0.43)
        if us >= 0.07 and v <= vr:
            return k
        if k < 0 or (us < 0.013 and v > us):
            continue
        if v == 0.0 or math.log(v) + math.log(invalpha) - math.log(a / (us * us) + b) <= -lam + k * loglam - math.lgamma(k + 1):
            return k  # log(0) is -inf, which accepts (as numpy's)


#: calibrate_looks.py's looks: the first session close with >= S_k sessions AND >= N_k settled events.
SCRIPT_LOOKS = ((10, 60), (15, 90), (20, 120), (30, 180), (40, 240), (60, 360), (90, 540))


def calibration(reps: int, rate: float, seed: int, *, alpha: float = ALPHA, rule: str = "prereg", skew: bool = True,
                horizon: int = 200, draws: int = B, skew_samples: int = SKEW_SAMPLES,
                skew_draws: int = SKEW_DRAWS) -> dict[str, Any]:
    """The family false-positive rate of a zero-edge program under calibrate_looks.py's null, in the standard library:
    events per session Poisson(rate'), rate' = max(0.3, Gamma(2, rate / 2)) per program; an event's abnormal return =
    the session's residual common shock 0.004 t(4) + its own 0.03 t(4); `horizon` sessions; every event TRADABLE and
    its own issuer, held one session.
    rule="prereg": section 7's looks and session-block test (the prereg's 8.3% at 6 or 40 events a session, 5.6% at
    2, with the skew check): look k as of session S_k counting the first event's session as 1, held with >= 60 events,
    >= 40 issuers and >= 10 blocks, passing when p <= alpha, p over `draws` sign vectors from the look's own seed;
    with `skew`, alpha is the look's skew check's (run only when p <= the starting alpha, the only case it can decide).
    rule="script": calibrate_looks.py's own looks (SCRIPT_LOOKS, deferred until N_k events stand; pass when >= 10
    session means have a positive mean and p <= alpha), the draft-1 figures 5.0 / 8.6 / 8.5 / 8.7%.
    Only pass or fail matters, so a count stops once it can no longer pass."""
    if rule not in ("prereg", "script"):
        raise ValueError("rule is 'prereg' or 'script'")
    started = time.perf_counter()
    rng = random.Random(seed)
    stop = _stop(alpha, draws)
    passes, checks, lowered = 0, 0, 0
    by_look = {k: 0 for k, _ in LOOKS}
    for rep in range(int(reps)):
        lam = max(0.3, rng.gammavariate(2.0, rate / 2.0))
        counts = [_poisson(rng, lam) for _ in range(horizon)]
        common = [_t4(rng) * 0.004 for _ in range(horizon)]
        events = [[common[i] + 0.03 * _t4(rng) for _ in range(counts[i])] for i in range(horizon)]
        means = [math.fsum(e) / len(e) if e else None for e in events]
        name = f"CAL{seed}-{rep}"
        hit = None
        if rule == "script":
            cum, total = [], 0
            for c in counts:
                total += c
                cum.append(total)
            for k, (s_k, n_k) in enumerate(SCRIPT_LOOKS, start=1):
                s = next((i + 1 for i in range(s_k - 1, horizon) if cum[i] >= n_k), None)
                if s is None:
                    break
                x = [v for v in means[:s] if v is not None]
                if len(x) < MIN_BLOCKS or not math.fsum(x) > 0:
                    continue
                # one sign-vector seed per program, as the script's one matrix
                if _count(x, _flips(seed_of(f"{name}|script"), len(x), draws), stop=stop) <= stop:
                    hit = k
                    break
        else:
            first = next((i for i, c in enumerate(counts) if c), None)
            if first is None:
                continue
            for k, s_k in LOOKS:
                last = first + s_k - 1
                if last >= horizon:
                    break
                n = sum(counts[first:last + 1])
                x = [v for v in means[first:last + 1] if v is not None]
                if not minimums(n, n, len(x))[0]:
                    continue
                c = _count(x, _flips(look_seed(name, 1, k), len(x), draws), stop=stop)
                if c > stop:
                    continue
                a = alpha
                if skew:
                    checks += 1
                    a = skew_check(x, seed_string(name, 1, k), alpha=alpha, samples=skew_samples,
                                   draws=skew_draws)["alpha"]
                    lowered += int(a < alpha)
                if (1 + c) / (1 + draws) <= a:
                    hit = k
                    break
        if hit is not None:
            passes += 1
            by_look[hit] += 1
    return {"fp": passes / int(reps), "passes": passes, "reps": int(reps), "rate": rate, "alpha": alpha, "rule": rule,
            "skew": bool(skew and rule == "prereg"), "skew_checks": checks, "skew_lowered": lowered,
            "draws": int(draws), "by_look": by_look, "seconds": round(time.perf_counter() - started, 2)}


# ---------------------------------------------------------------------------------------------------- the screen job
def program_versions(store: S.Store) -> list[tuple[str, int]]:
    return [(r[0], int(r[1])) for r in store.db.execute("SELECT DISTINCT program, version FROM intents ORDER BY 1, 2")]


def exit_overrides(store: S.Store, program: str, version: int) -> dict[str, dt.date]:
    """event -> the session it actually exited in, for exits that left later than planned (score.py keeps them in
    meta `exit:<program>:<version>:<event>` when an exit auction had no print)."""
    prefix = f"exit:{program}:{version}:"
    out = {}
    for row in store.db.execute("SELECT key, value FROM meta WHERE key>=? AND key<?", (prefix, prefix[:-1] + ";")):
        out[str(row["key"])[len(prefix):]] = dt.date.fromisoformat(json.loads(row["value"])["day"])
    return out


def settled_rows(store: S.Store, program: str, version: int) -> list[dict[str, Any]]:
    """The program's settled events: {event, entry_day, exit_day (scheduled), exited (the session it left in), a, r, b,
    stress_r, issuer (CIK, else symbol), tradable (True / False / None), late (its verdict answered after the
    decision; None without a verdict)}."""
    moved = exit_overrides(store, program, version)
    sql = ("SELECT i.event, i.entry_day, i.exit_day, i.symbol, i.cik, i.decided_at, o.a, o.r, o.b, o.stress_r, o.tradable, "
           "(SELECT MIN(v.answered_at) FROM verdicts v WHERE v.event=i.event AND v.status IN ('ok', 'unparsed', 'refused'))"
           " AS verdict_at FROM outcomes o JOIN intents i ON i.program=o.program AND i.version=o.version AND "
           "i.event=o.event WHERE o.program=? AND o.version=? AND o.status='settled' ORDER BY i.entry_day, i.event")
    out = []
    for r in store.db.execute(sql, (program, version)):
        scheduled = _day(r["exit_day"])
        out.append({"program": program, "version": version, "event": r["event"], "entry_day": _day(r["entry_day"]),
                    "exit_day": scheduled, "exited": moved.get(r["event"], scheduled), "a": r["a"], "r": r["r"],
                    "b": r["b"], "stress_r": r["stress_r"], "issuer": r["cik"] or r["symbol"],
                    "tradable": None if r["tradable"] is None else bool(r["tradable"]),
                    "late": None if r["verdict_at"] is None else str(r["verdict_at"]) > str(r["decided_at"])})
    return out


def first_settled_exit(store: S.Store, program: str, version: int) -> dt.date | None:
    """The session of the program's first settled exit (the looks' session 1), or None."""
    return min((r["exited"] for r in settled_rows(store, program, version)), default=None)


def _pending(store: S.Store, program: str, version: int) -> list[tuple[dt.date, dt.date]]:
    """(entry_day, scheduled exit_day) of the program's intents not yet resolved (planned or entered)."""
    return [(_day(r[0]), _day(r[1])) for r in store.db.execute(
        "SELECT entry_day, exit_day FROM intents WHERE program=? AND version=? AND status IN ('planned', 'entered')",
        (program, version))]


def covered(rows: Sequence[Mapping[str, Any]], as_of: dt.date) -> list[Mapping[str, Any]]:
    """The settled events of the blocks a look as of `as_of` covers: those whose scheduled exits are at or before it."""
    return [r for r in rows if _day(r["exit_day"]) <= as_of]


def skew_records(store: S.Store, program: str, version: int, k: int) -> dict[str, Any] | None:
    raw = store.meta(f"skew:{program}:{version}:{k}")
    return None if raw is None else json.loads(raw)


def look_rows(store: S.Store, program: str, version: int) -> list[dict[str, Any]]:
    return [dict(r) for r in store.db.execute("SELECT * FROM looks WHERE program=? AND version=? ORDER BY k",
                                              (program, version))]


def next_look(store: S.Store, program: str, version: int, today: dt.date) -> dict[str, Any]:
    """The program's next unwritten look: {k, at_sessions, sessions (the count today), day, status}."""
    if program not in SEATABLE:
        return {"k": None, "status": "a record: never screened"}
    done = {r["k"] for r in look_rows(store, program, version)}
    pending = [(k, s) for k, s in LOOKS if k not in done]
    if not pending:
        return {"k": None, "status": "all looks written"}
    k, s_k = pending[0]
    anchor = first_settled_exit(store, program, version)
    if anchor is None:
        return {"k": k, "at_sessions": s_k, "sessions": 0, "day": None, "status": "no settled exit yet"}
    count = len(C.sessions(store, anchor, today))
    target = C.nth(store, anchor, s_k)
    status = "upcoming" if count < s_k else ("due" if count == s_k else "overdue")
    return {"k": k, "at_sessions": s_k, "sessions": count, "day": target.day.isoformat() if target else None,
            "status": status}


# --------------------------------------------------------------------------------------- a look's close is final
#: A LOOK WAITS UNTIL ITS AS-OF CLOSE IS FINAL FOR ITS PROGRAM (release 1019b's review; PREREG-EVL-1 section 7's "late
#: data delays the computation, never its as-of date", read for version 2's event-counted looks too and recorded as an
#: amendment). A look is written once and never again, so it reads the record of the sessions it covers only once
#: nothing more can be added to them; a reading program's session that waits on a verdict has no intent yet, so the
#: unsettled intents alone (`_pending`) never showed it. A close X is final for a program when:
#: - the hourly re-decision (league/events/house.py REDECIDE_SESSIONS, the CLI's catchup alike) reaches it no more:
#:   FINAL_SESSIONS later sessions have had their open decision;
#: - every decision of the program's entry kind through X is made: its latest receipt `ok`, or `pending` only on
#:   another program's verdicts (a decision missed, cut, failed, still running or pending on this program's own verdicts
#:   is made again later and adds intents), back to the House's look-back (house.py LOOKBACK: an older one is never
#:   made, so nothing waits for it);
#: - the EDGAR daily-index backfill (house.py BACKFILL_WEEKDAYS) of every weekday through X that the House still
#:   backfills has run (meta `evl:backfill:<day>` "done": it adds the filings the live pass missed, and decides their
#:   sessions again), through `index_through(X)` when X is an SEC holiday NYSE trades (release 1019f's review: the
#:   index that holds the 8-Ks of X's eve; `SEC_HOLIDAYS`).
#: THE REACH IS DEFINED HERE, ONCE (release 1019b's second review): the House's lane takes its REDECIDE_SESSIONS,
#: LOOKBACK and BACKFILL_WEEKDAYS from these three (league/events/house.py imports them; this file is behind the wall,
#: house.py is not), and `_reach` waits out the House's own when it is ever larger: a House change can only delay a
#: look, never move one earlier.
FINAL_SESSIONS = 3
FINAL_LOOKBACK = dt.timedelta(days=45)
FINAL_BACKFILL_WEEKDAYS = 3
#: SEC HOLIDAYS (release 1019f; moved here from league/events/house.py by its review, lens judges, as the reach above
#: is: the House's lane takes this table, house.py `SEC_HOLIDAYS`, and `_sec_holidays` reads the House's own too, so
#: a day only the House's copy lists, whose backfill it marks done, still has the index after it waited for): EDGAR
#: accepts no filing on a US federal holiday and publishes no daily index for it; the House's backfill marks such a
#: weekday done when its index read fails (house.py `_backfill`). The federal holidays of 2026 and 2027 as OPM lists
#: them (https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/, read Oct 21, 2026), and Fri Dec 31,
#: 2027: New Year's Day 2028 falls on a Saturday, so the Friday before is its holiday (5 U.S.C. 6103(b)(1)). A closure
#: by executive order (a Christmas Eve) is not in it: add the day before it falls; 2028's before Jan 2028.
#: THE INDEX THAT HOLDS A HOLIDAY'S EVE (the review's major): EDGAR dates an 8-K accepted after 17:30 ET as filed on
#: the next day it is open (Regulation S-T Rule 13(a)(2); a Section 16 form to 22:00 ET the same day), so on a holiday
#: NYSE trades (Columbus Day, Veterans Day) the 8-Ks accepted after 17:30 ET of the session before it, events of the
#: holiday's open decision, are in the index of the next weekday EDGAR is open, not in the eve's, and the holiday has
#: none. A close X is final (A66's third rule, A69's (iii)) only once the backfill of that index has run too
#: (`index_through`); on any other session the index of X itself is the last, as before.
SEC_HOLIDAYS: dict[dt.date, str] = {
    dt.date(2026, 1, 1): "New Year's Day", dt.date(2026, 1, 19): "Birthday of Martin Luther King, Jr.",
    dt.date(2026, 2, 16): "Washington's Birthday", dt.date(2026, 5, 25): "Memorial Day",
    dt.date(2026, 6, 19): "Juneteenth National Independence Day", dt.date(2026, 7, 3): "Independence Day",
    dt.date(2026, 9, 7): "Labor Day", dt.date(2026, 10, 12): "Columbus Day", dt.date(2026, 11, 11): "Veterans Day",
    dt.date(2026, 11, 26): "Thanksgiving Day", dt.date(2026, 12, 25): "Christmas Day",
    dt.date(2027, 1, 1): "New Year's Day", dt.date(2027, 1, 18): "Birthday of Martin Luther King, Jr.",
    dt.date(2027, 2, 15): "Washington's Birthday", dt.date(2027, 5, 31): "Memorial Day",
    dt.date(2027, 6, 18): "Juneteenth National Independence Day", dt.date(2027, 7, 5): "Independence Day",
    dt.date(2027, 9, 6): "Labor Day", dt.date(2027, 10, 11): "Columbus Day", dt.date(2027, 11, 11): "Veterans Day",
    dt.date(2027, 11, 25): "Thanksgiving Day", dt.date(2027, 12, 24): "Christmas Day",
    dt.date(2027, 12, 31): "New Year's Day",
}


def _sec_holidays() -> frozenset[dt.date]:
    """The SEC holidays a look reads: `SEC_HOLIDAYS`, and the House lane's own table as it runs when it holds more
    (league/events/house.py takes this one; a day only it lists is a backfill it marks done, so the judge reads the
    index after it too: a copy it widened can only delay a look, as `_reach`)."""
    days = set(SEC_HOLIDAYS)
    try:
        from . import house as H

        days |= set(H.SEC_HOLIDAYS)
    except Exception:  # noqa: BLE001 - the House's lane cannot be read here: the judge's own table
        pass
    return frozenset(days)


def index_through(day: dt.date, holidays: Iterable[dt.date] | None = None) -> dt.date:
    """The last EDGAR daily index that can hold a filing of session `day`'s windows (`SEC_HOLIDAYS`' comment): `day`
    itself, or, when EDGAR is closed on it (an SEC holiday NYSE trades), the next weekday EDGAR is open."""
    closed = _sec_holidays() if holidays is None else frozenset(holidays)
    while day.weekday() >= 5 or day in closed:
        day += dt.timedelta(days=1)
    return day
#: A69 (the captain's amendment of 14:25Z Oct 19, 2026; release 1019c): THE FAST PATH TO A FINAL RECORD. The three
#: sessions' wait above is for late data; when there is provably none, a close X is final for a program once the
#: session after X has had its open decision AND
#: (i) EACH FEED WAS READ WHOLE from the start of the earliest window that feeds X's decisions (09:00 ET of the session
#:     before X: the open window's start; never before the program's registration time, before which no event counts)
#:     through that open decision, AS A84 READS IT (the captain's reading of 19:58Z Oct 21, 2026, recorded before any
#:     look; release 1019f): "a record pass whose read of a feed errored, was cut, or had no tickers copy is a MISSING
#:     read of that feed, not a broken span; the span is whole when, for each of 8-K, Form 4 and news separately,
#:     clean reads of that feed are at most FAST_RECORD_GAP (15 min) apart from before the span's start through its
#:     end." A CLEAN READ of a feed is a record pass's receipt (league/events/house.py `_record`, league/events/run.py
#:     `record_pass`) finished `ok` whose part for that feed is present with no `error`: for the 8-K feed with the
#:     tickers copy read too (no `error` under `tickers`: without it no 8-K is fetched), for the news its read not
#:     `cut`; a pass not finished `ok` (failed, running) or with an unreadable summary reads no feed cleanly
#:     (`_feed_problems`). SOUND because EDGAR's current feeds page back to the newest known accession and the news
#:     read restarts from the newest stored less 5 minutes, so a clean read after a missing one recovers what it
#:     missed; a pass that never ran proves nothing (the reading that waits). (Until A84, A69 (i) read "every record
#:     pass ... ran without a feed error", so one 45-second SEC timeout broke a whole span: SEC's getcurrent feed timed
#:     out about four times a night, each followed by a clean pass within 2-4 minutes, and no span was ever whole.);
#: (ii) no filing knowable in those windows (from that start to X's close decision, or a daily-index row stored since
#:     that start) is still listed or failed: a failed one, a listed Form 4, or a listed 8-K whose filer is in X's
#:     tickers copy (an unlisted filer's 8-K is never fetched, and never an event of X);
#: (iii) the daily-index backfill of every weekday from the session before X through X has run (meta
#:     `evl:backfill:<day>` = done: the days whose indexes hold filings of X's windows; the reading that waits), and,
#:     when X is an SEC holiday NYSE trades, through the next weekday EDGAR is open (`index_through`: its index holds
#:     the 8-Ks accepted after 17:30 ET of X's eve; release 1019f's review, lens judges);
#: (iv) every decision of the program's entry kind through X is made as A66's second rule reads it, and the session
#:     after X's open decision is made (its receipt `ok` or `pending`).
#: Otherwise A66's rules apply unchanged. Finality stays contiguous: X is final by the fast path only when every session
#: before it is final (by A66 or by the fast path). It only moves the computation earlier when no late event can
#: exist; the as-of date, the record and the look are the same (a re-decision never writes an intent under a look
#: already written: league/events/run.py `_scope`).
FAST_RECORD_GAP = dt.timedelta(minutes=15)
#: The record pass's receipt, and the reads in it whose failure is a feed error.
RECORD_JOB = "record"
RECORD_FORMS = ("8-K", "4")
#: A84: the three feeds A69 (i) judges, each by its own clean reads, in this order, and their names in a why.
RECORD_FEEDS = RECORD_FORMS + ("news",)
FEED_NAMES = {"8-K": "8-K", "4": "Form 4", "news": "news"}
#: A DECISION MADE BY A RELEASE WITHOUT A PROGRAM'S ROWS IS NOT MADE FOR IT (release 1019c's review; PREREG-EVL-4
#: section 2: "for every event after the registration time that comes before it (backfill included), the programs are
#: decided by the same rules in shadow only"; PREREG-EVL-1 section 3: "all do"). A decision's receipt names every
#: program it decided (its key: the id at version 1, `id@vN` after it) or left pending on its verdicts (under
#: `pending`); one a release without a program's rows made names none of them: release 1019b's receipts of the closes
#: from PREREG-EVL-4's registration (16:01:05Z Oct 19) to the deploy of release 1019c, outside the reach the House
#: decides again. For a program of PREREG-EVL-4 or a later file (`NAMED_FROM`), a decision whose latest receipt is
#: finished `ok` or `pending` and does not name it is NOT MADE for it, unless a later receipt of PREREG-EVL-4's rows
#: decided BY THEMSELVES (`FOUR_KIND`: league/events/run.py `decide_close` with `evl4_only`, a backfill) names it: then
#: that receipt is its decision. Those rows alone are decided again, never the earlier files' rows: a close already
#: final for an earlier program (the rules above) gains nothing, and their receipts are read here exactly as release
#: 1019b reads them. The House's lane and the CLI's catchup run that decision, once, for every such close
#: (`made_without`); until it is made, the close is not final for the program, so no look of it reads a record its rows
#: never decided (the reading that waits: a House that never ran it could only delay the look).
NAMED_FROM = 4
FOUR_KIND = "close-evl4"
#: PREREG-EVL-5 section 3, THE RECORD BEFORE THE RELEASE, the same rule for its rows: a close decided by a release without
#: them, OR WHOSE PART FOR THEM FAILED OR RAN PAST ITS OWN BOUND (section 1.3: its receipt finishes with the earlier rows
#: and names none of them), is not made for them until a later receipt of their rows decided by themselves (`FIVE_KIND`,
#: league/events/run.py `decide_close` with `evl5_only`) names them. A file's rows decided by themselves are named
#: only by that file's kind (`FILE_KINDS`); a close decision made at or before a program's registration time is made for
#: it (none of its events is in that decision's windows: section 3's "every close decision from the registration time").
FIVE_KIND = "close-evl5"
FILE_KINDS = {4: FOUR_KIND, 5: FIVE_KIND}
#: A DECISION MADE WITHOUT A REGISTERED BIRTH'S ROWS IS NOT MADE FOR IT (release 1019e's review; PREREG-EVL-1 section 3:
#: "an outage removes nothing"). A birth (R3, league/events/births.py) is prereg 3, so the rule above (`NAMED_FROM`)
#: never reached it: a receipt that never named a birth, made by a release without births (the documented rollback to
#: release 1019d) or in a turn whose loader had no births, read as made for it, and once outside the re-decision
#: reach its looks counted a record with that session's events missing. So for a registered birth, and for each
#: member of its group (a READ birth's derived control, `control_of`), a decision whose time (09:15 ET, or the close's
#: decision time) is AFTER the birth's registration and whose latest receipt is finished `ok` or `pending` without
#: naming it is NOT MADE for it, unless a later receipt of THE BIRTHS' ROWS DECIDED BY THEMSELVES (`BIRTHS_KIND`:
#: league/events/run.py `decide_open` / `decide_close` with `births_only`, a backfill) names it: then that receipt is
#: its decision. A decision made before the birth's registration is made for it as for every program (none of its
#: events is in that decision's windows). The House's lane and the CLI's catchup run those decisions, once, for every
#: such session (`births_made_without`); until one is made the session is not final for the birth (the reading that
#: waits). A birth's look also waits when any member of its group failed its part of a decision (`births_failed`), or
#: is pending on its verdicts: the look compares the birth with its control, so neither record may be missing a
#: session's events. No PREREG program reads any of this.
BIRTHS_KIND = {"open": "open-births", "close": "close-births"}


def program_key(program: str, version: int) -> str:
    """The key a decision's summary gives (program, version): the id at version 1, `id@vN` after it
    (league/events/run.py `_key`)."""
    return str(program) if int(version) == 1 else f"{program}@v{int(version)}"


def names(summary: Any, key: str) -> bool:
    """Whether a decision receipt's summary (its JSON text, or the mapping) NAMES the program `key`: decided (its counts
    under the key), pending on its verdicts (the key under `pending`) or KEPT (the key under `kept`: a written look of
    its group froze it, A74 (5), league/events/run.py `_scope`; the decision was made for it, writing nothing, as
    `_waits_on` reads it: release 1019d's merge of the two). A receipt that ended in anything else (`cut`, `failed`: a
    reason only) and an unreadable summary name none (the reading that waits)."""
    if isinstance(summary, (str, bytes, bytearray)):
        try:
            summary = json.loads(summary)
        except ValueError:
            return False
    if not isinstance(summary, Mapping):
        return False
    pending, kept = summary.get("pending"), summary.get("kept")
    return (key in summary or (isinstance(pending, Mapping) and key in pending)
            or (isinstance(kept, Mapping) and key in kept))


def _latest_receipts(store: S.Store, kinds: Iterable[str]) -> dict[str, tuple[int, str, Any]]:
    """`decide-<kind>:<day>` -> (id, status, summary) of its latest receipt, for each kind of `kinds`."""
    out: dict[str, tuple[int, str, Any]] = {}
    for kind in kinds:
        for row in store.db.execute("SELECT id, job, status, summary FROM receipts WHERE job>=? AND job<? ORDER BY id",
                                    (f"decide-{kind}:", f"decide-{kind};")):
            out[str(row["job"])] = (int(row["id"]), str(row["status"] or ""), row["summary"])
    return out


def four_programs() -> tuple[Any, ...]:
    """PREREG-EVL-4's programs, every one a close-entry program (`FOUR_KIND` decides them and nothing else)."""
    from .programs import PROGRAMS

    return tuple(p for p in PROGRAMS if p.prereg == 4)


def file_programs(prereg: int) -> tuple[Any, ...]:
    """The programs of PREREG-EVL-`prereg` (4 or 5), every one a close-entry program (that file's kind, `FILE_KINDS`,
    decides them and nothing else)."""
    from .programs import PROGRAMS

    return tuple(p for p in PROGRAMS if p.prereg == int(prereg) and p.spec is None)


def made_without(store: S.Store, last: dt.date, *, first: dt.date | None = None, prereg: int = 4) -> dict[dt.date, bool]:
    """THE CLOSES WHOSE PREREG-EVL-4 ROWS (`prereg` 5: PREREG-EVL-5's) ARE STILL TO DECIDE BY THEMSELVES: the sessions
    from the first close after that file's registration (from `first`, when later) to `last` whose latest `decide-close`
    receipt is finished `ok` or `pending` without naming every one of its programs registered before its decision time
    (a release without their rows made it, or, PREREG-EVL-5 section 1.3, its part for them failed or ran past its own
    bound), and with no later receipt of that file's kind (`FILE_KINDS`: `FOUR_KIND`, `FIVE_KIND`) finished `ok`.
    {day: stale}: stale when the session's latest such receipt is older than that receipt (its rows were decided by
    themselves, then the session again without them: decided again). The House's lane and the CLI's catchup decide each
    of them (that kind), once, as a backfill."""
    own = FILE_KINDS[int(prereg)]
    four = four_programs() if int(prereg) == 4 else file_programs(prereg)
    if not four:
        return {}
    since = min(p.registered_at for p in four).astimezone(C.NY).date()
    if first is not None:
        since = max(since, first)
    if since > last:
        return {}
    from .programs import before_release, release_at

    latest = _latest_receipts(store, ("close", own))
    mark = release_at(store)
    out: dict[dt.date, bool] = {}
    for x in C.sessions(store, since, last):
        rid, status, summary = latest.get(f"decide-close:{x.day.isoformat()}", (0, "", None))
        if status not in ("ok", "pending"):
            continue    # not made (none, cut, failed, running): the House decides it again whole, naming them
        # (PREREG-EVL-6 section 1.1: a new version's record of a close decided before the release is its superseded
        # version's, copied; only the closes from the release on are its own decisions to name)
        keys = [program_key(p.id, p.version) for p in four if p.registered_at < x.close_decide and
                not (getattr(p, "regfile", None) is not None and before_release(store, p, x.day, release=mark,
                                                                                 read=False))]
        if all(names(summary, k) for k in keys):
            continue
        rid4, status4, _ = latest.get(f"decide-{own}:{x.day.isoformat()}", (0, "", None))
        if rid4 > rid and status4 == "ok":
            continue
        out[x.day] = 0 < rid4 < rid
    return out


def _decision_time(x: C.Session, kind: str) -> dt.datetime:
    return x.open_decide if kind == "open" else x.close_decide


def birth_group(prog: Any) -> list[str]:
    """The decision keys a registered birth's look reads (`BIRTHS_KIND`'s comment): its own and its derived control's
    (a READ birth's, when loaded); [] for every PREREG program."""
    if getattr(prog, "spec", None) is None:
        return []
    keys = [program_key(prog.id, prog.version)]
    control = control_of(prog.id)       # (PREREG-EVL-6: a birth's version 2 reads the same control record)
    if control is not None:
        keys.append(program_key(control, 1))
    return keys


def births_made_without(store: S.Store, last: dt.date, *, first: dt.date | None = None
                        ) -> dict[tuple[str, dt.date], bool]:
    """THE DECISIONS WHOSE REGISTERED BIRTHS ARE STILL TO DECIDE BY THEMSELVES (`BIRTHS_KIND`'s comment): {(kind, day):
    again} for every open and close decision of the sessions from the first registered birth's registration (from
    `first`, when later) to `last` whose latest receipt (`decide-<kind>:<day>`) is finished `ok` or `pending` without
    naming every registered birth (and control) of that entry kind registered before its decision time, and with no
    later births-only receipt (`decide-<BIRTHS_KIND[kind]>:<day>`) finished `ok` that names them all. `again` when an
    `ok` births-only receipt of it exists (an older one, the session decided again since by a release without births:
    stale; or a later one that names not all, a birth's part of it having failed): the House decides it again. The
    House's lane and the CLI's catchup decide each of them (`BIRTHS_KIND`), as a backfill."""
    from .programs import BIRTHS

    if not BIRTHS:
        return {}
    since = min(p.registered_at for p in BIRTHS).astimezone(C.NY).date()
    if first is not None:
        since = max(since, first)
    if since > last:
        return {}
    from .programs import before_release, release_at

    latest = _latest_receipts(store, ("open", "close", *BIRTHS_KIND.values()))
    mark = release_at(store)
    out: dict[tuple[str, dt.date], bool] = {}
    for x in C.sessions(store, since, last):
        for kind in ("open", "close"):
            at = _decision_time(x, kind)
            # (PREREG-EVL-6: a birth's version 2 is copied before the release, never decided by the births' kind)
            keys = [program_key(p.id, p.version) for p in BIRTHS if p.entry_at == kind and p.registered_at < at and
                    not (p.regfile is not None and before_release(store, p, x.day, release=mark, read=False))]
            if not keys:
                continue
            rid, status, summary = latest.get(f"decide-{kind}:{x.day.isoformat()}", (0, "", None))
            if status not in ("ok", "pending"):
                continue    # not made (none, cut, failed, running): the House decides it again whole, naming them
            if all(names(summary, k) for k in keys):
                continue
            ridb, statusb, summaryb = latest.get(f"decide-{BIRTHS_KIND[kind]}:{x.day.isoformat()}", (0, "", None))
            if ridb > rid and statusb == "ok" and all(names(summaryb, k) for k in keys):
                continue
            out[(kind, x.day)] = statusb == "ok"
    return out


def _reach() -> tuple[int, dt.timedelta, int]:
    """(sessions, look-back, backfill weekdays) a look waits out: the constants above, or the House lane's as it runs
    when they reach further (league/events/house.py takes these; a copy it widened would only delay looks)."""
    sessions, lookback, weekdays = FINAL_SESSIONS, FINAL_LOOKBACK, FINAL_BACKFILL_WEEKDAYS
    try:
        from . import house as H

        sessions = max(sessions, int(H.REDECIDE_SESSIONS))
        lookback = max(lookback, H.LOOKBACK)
        weekdays = max(weekdays, int(H.BACKFILL_WEEKDAYS))
    except Exception:  # noqa: BLE001 - the House's lane cannot be read here: the judge's own reach
        pass
    return sessions, lookback, weekdays


def _waits_on(status: str, summary: Any, key: str) -> bool:
    """Whether a decision receipt (`status`, `summary`) leaves the decision unmade for the program keyed `key` (A66's
    second rule): anything but `ok`, or `pending` on this program's own verdicts (an unreadable summary waits)."""
    if status == "ok":
        return False
    if status != "pending":
        return True
    try:
        body = json.loads(summary or "{}")
        waits = dict(body.get("pending") or {}) if isinstance(body, dict) else {key: None}
    except (TypeError, ValueError):
        waits = {key: None}     # (unreadable: read as waiting on this program, the reading that waits)
    return key in waits


def final_until(store: S.Store, program: str, version: int, today: dt.date,
                now: dt.datetime) -> tuple[dt.date | None, str]:
    """(the last session close that is final for (program, version) at `now`, None when none is; why the next one is
    not), by A66's three rules above, then A69's fast path (`_fast_until`) from the first session they leave open."""
    from .programs import BY_KEY

    prog = BY_KEY.get((str(program), int(version)))
    if prog is None:
        return None, f"{program} v{version} is no registered program"
    first = prog.registered_at.astimezone(C.NY).date()
    reach_sessions, reach_lookback, reach_weekdays = _reach()
    kind = prog.entry_at
    # (release 1019c's review: a program of PREREG-EVL-4 or later reads a receipt that does not name it as not made,
    # unless a later receipt of its file's rows decided by themselves names it: `NAMED_FROM`, above)
    named = prog.prereg >= NAMED_FROM
    own_kind = FILE_KINDS.get(int(prog.prereg), FOUR_KIND)     # (each file's rows by themselves: PREREG-EVL-4's, -5's)
    group = birth_group(prog)       # (R3: a birth and its control; [] for every PREREG program, which reads none of it)
    born_kind = BIRTHS_KIND.get(kind) if group else None
    latest = _latest_receipts(store, (kind,) + ((own_kind,) if named else ()) + ((born_kind,) if born_kind else ()))
    since = max(first, (now - reach_lookback).astimezone(C.NY).date())
    # A66's second rule and A69's (iv): the first session from the look-back on whose decision is not made for it. A
    # program of PREREG-EVL-4 or later (`named`) reads a receipt finished `ok` or `pending` that does not name it as not
    # made, unless a later receipt of its file's rows decided by themselves (`FOUR_KIND`; `FIVE_KIND` for PREREG-EVL-5,
    # whose close decided at or before its registration time is made for it: `FIVE_KIND`'s comment) names it: then that
    # one is its decision (`NAMED_FROM`, above). A registered birth (`group`) reads a decision made after its registration
    # that does not name every member of its group the same way, with the births' own decision (`BIRTHS_KIND`), and
    # waits when a member of its group failed its part or is pending on its verdicts (`BIRTHS_KIND`'s comment).
    # PREREG-EVL-6 section 1.1 (D8): a NEW VERSION's record of an entry session decided before the release is its
    # superseded version's, copied (league/events/programs.py `copy_before_release`), so that session's decision is
    # read exactly as the superseded version's (its key, its file's own kind, its births' group); the copy itself is
    # complete before any look reads it (`_run_v6`, `programs.uncopied`). From the release on the decision is its own.
    from .programs import before_release, release_at, superseded_of

    sup = superseded_of(prog)
    mark = release_at(store) if sup is not None else None
    unmade: tuple[dt.date, str] | None = None
    for x in C.sessions(store, since, today):
        use = sup if sup is not None and before_release(store, prog, x.day, release=mark, read=False) else prog
        ukey = program_key(use.id, use.version)
        ugroup = birth_group(use)
        # (a new version's own session, from the release on, is made for it only when its receipt names it, whatever
        # its file: a release without the new versions, a rollback, decided it for nothing: the reading that waits)
        unamed = named or (use is prog and sup is not None)
        rid, status, summary = latest.get(f"decide-{kind}:{x.day.isoformat()}", (0, "", None))
        if unamed and status in ("ok", "pending") and not names(summary, ukey) and \
                (own_kind != FIVE_KIND or _decision_time(x, kind) > use.registered_at):
            rid4, status4, summary4 = latest.get(f"decide-{own_kind}:{x.day.isoformat()}", (0, "", None))
            if kind == "close" and rid4 > rid and names(summary4, ukey):
                status, summary = status4, summary4        # its rows decided by themselves, after that decision
            elif kind == "close" and rid4 > rid:
                status = f"made without its rows ({own_kind}: {status4 or 'running'})"
            else:
                status = "made without its rows"
        if ugroup and status in ("ok", "pending") and _decision_time(x, kind) > use.registered_at and \
                not all(names(summary, k) for k in ugroup):
            ridb, statusb, summaryb = latest.get(f"decide-{born_kind}:{x.day.isoformat()}", (0, "", None))
            if ridb > rid and all(names(summaryb, k) for k in ugroup):
                status, summary = statusb, summaryb        # the births' rows decided by themselves, after that decision
            elif ridb > rid:
                status = f"made without its rows ({born_kind}: {statusb or 'running'})"
            else:
                status = "made without its rows"
        if status in ("ok", "pending") and ugroup and any(k in _births_failed(summary) for k in ugroup):
            status = "failed"       # (R3: a member of this birth's group raised in its own part; never a PREREG program)
        if _waits_on(status, summary, ukey) or any(_waits_on(status, summary, k) for k in ugroup[1:]):
            unmade = (x.day, f"the {kind} decision of {x.day.isoformat()} is {status or 'not made'}")
            break
    decided = [x for x in C.sessions(store, first, today) if x.open_decide <= now]
    horizon: dt.date | None = None
    if len(decided) <= reach_sessions:
        why = f"the re-decision window still reaches every session ({len(decided)} decided)"
    else:
        horizon = decided[-(reach_sessions + 1)].day
        why = f"the re-decision window reaches {decided[-reach_sessions].day.isoformat()}"
        if unmade is not None and unmade[0] <= horizon:
            before = [y for y in C.previous(store, unmade[0], 1) if y.day >= first]
            horizon = before[-1].day if before else None
            why = unmade[1]
        reach, day = [], today
        while len(reach) < reach_weekdays:
            day -= dt.timedelta(days=1)
            if day.weekday() < 5:
                reach.append(day)
        # (release 1019f's review: a weekday's index holds the windows of the sessions through it, and of an SEC holiday
        # NYSE trades before it, `index_through`; so a backfill not run holds every session whose last index it is)
        holidays = _sec_holidays()
        for day in sorted(reach):
            if horizon is None:
                break
            if day < first or day > index_through(horizon, holidays) or \
                    store.meta(f"evl:backfill:{day.isoformat()}") == "done":
                continue
            before = [y for y in C.previous(store, day, 3) if y.day >= first and index_through(y.day, holidays) < day]
            horizon = before[-1].day if before else None
            why = f"the daily-index backfill of {day.isoformat()} has not run"
            break
    return _fast_until(store, prog, first, horizon, why, unmade, today, now)


def _fast_until(store: S.Store, prog: Any, first: dt.date, horizon: dt.date | None, why: str,
                unmade: tuple[dt.date, str] | None, today: dt.date, now: dt.datetime) -> tuple[dt.date | None, str]:
    """A69: from the first session after A66's `horizon` (`why` its reason), each next close X that meets the fast
    path's four conditions (`_fast_block`) is final too, in order, until the first that does not."""
    moved = False
    cache: dict[str, Any] = {}
    for x in C.sessions(store, first, today):
        if horizon is not None and x.day <= horizon:
            continue
        block = _fast_block(store, prog, first, x, unmade, now, cache)
        if block is not None:
            return horizon, (f"the fast path (A69) stops at {x.day.isoformat()}: {block}" if moved else
                             f"{why}; the fast path (A69) stops at {x.day.isoformat()}: {block}")
        horizon, moved = x.day, True
    return horizon, why if not moved else f"the fast path (A69) reaches {horizon}"


def _fast_block(store: S.Store, prog: Any, first: dt.date, x: C.Session, unmade: tuple[dt.date, str] | None,
                now: dt.datetime, cache: dict[str, Any]) -> str | None:
    """Why close `x` is not final for `prog` by A69's fast path (the comment above FAST_RECORD_GAP), None when it is."""
    after = C.nth(store, x.day, 2)
    if after is None:
        return "no session after it in the calendar"
    if after.open_decide > now:
        return f"the session after it ({after.day.isoformat()}) has not had its open decision"
    row = store.db.execute("SELECT started_at FROM receipts WHERE job=? AND status IN ('ok', 'pending') ORDER BY id "
                           "LIMIT 1", (f"decide-open:{after.day.isoformat()}",)).fetchone()
    if row is None:
        return f"the open decision of {after.day.isoformat()} is not made"
    if unmade is not None and unmade[0] <= x.day:
        return unmade[1]
    before = C.previous(store, x.day, 1)
    if not before:
        return "no session before it in the calendar"
    prior = before[-1]
    day = max(prior.day, first)
    start = max(prior.open_cutoff, prog.registered_at)     # (no event before its registration counts)
    if getattr(prog, "prereg", None) == 5 and getattr(prog, "spec", None) is None:
        # PREREG-EVL-5 section 2: FOR ITS ROWS A69's span begins at the earliest window that feeds their decision of
        # close X, the close decision time of P' (two sessions before X: where the close window of P, read by NO NEW
        # INFORMATION (ii), begins; the attention articles of P begin at P''s close), and A74 (3)'s daily-index
        # backfill must have run for every weekday from P' through X (through the index that holds X's filings when X
        # is an SEC holiday, `index_through`, as for every program: release 1019f's fix round). The skips those
        # windows feed carry no registration floor, so neither does the span (the reading that waits). A69 (i)'s
        # passes are judged from before that start through the span's end by `_fast_passes`, A84's per-feed clean
        # reads (release 1019g carries both); A69 (ii) reads the filings from that start.
        back = C.previous(store, x.day, 2)
        if len(back) < 2:
            return "not two sessions before it in the calendar"
        day, start = back[0].day, back[0].close_decide
    if "holidays" not in cache:
        cache["holidays"] = _sec_holidays()
    last = index_through(x.day, cache["holidays"])
    while day <= last:
        if day.weekday() < 5 and store.meta(f"evl:backfill:{day.isoformat()}") != "done":
            return f"the daily-index backfill of {day.isoformat()} has not run" + (
                "" if day <= x.day else f" (its index holds the 8-Ks of {prior.day.isoformat()}'s evening: "
                                        f"{x.day.isoformat()} is an SEC holiday)")
        day += dt.timedelta(days=1)
    end = max(after.open_decide, S.parse_iso(row["started_at"]))
    stuck = _fast_filings(store, x, start, x.close_decide, now, cache)
    if stuck is not None:
        return stuck
    return _fast_passes(store, start, end, cache)


def _fast_filings(store: S.Store, x: C.Session, start: dt.datetime, end: dt.datetime, now: dt.datetime,
                  cache: dict[str, Any]) -> str | None:
    """A69 (ii): a filing knowable in [start, end) (or a daily-index row stored since `start`) still listed or failed
    that the lane would fetch: a failed one, a listed Form 4, a listed 8-K of a filer in `x`'s tickers copy."""
    rows = store.db.execute(
        "SELECT accession, form, cik, status FROM filings WHERE (status='listed' OR status LIKE 'failed%') AND "
        "((knowable_at>=? AND knowable_at<?) OR (source='daily-index' AND received_at>=? AND received_at<=?)) "
        "ORDER BY knowable_at, accession", (S.iso(start), S.iso(end), S.iso(start), S.iso(now))).fetchall()
    listed: set[str] | None = None
    for r in rows:
        status = str(r["status"])
        if status.startswith("failed"):
            return f"filing {r['accession']} ({r['form']}) is {status[:80]}"
        if r["form"] != "8-K":
            return f"filing {r['accession']} ({r['form']}) is still listed"
        if listed is None:
            listed = _listed_ciks(store, x.day, x.at(dt.time(7, 30)), cache)
        if listed is None or str(r["cik"]) in listed:
            return f"filing {r['accession']} (8-K) of a listed filer is still listed"
    return None


def _listed_ciks(store: S.Store, day: dt.date, cutoff: dt.datetime, cache: dict[str, Any]) -> set[str] | None:
    """The CIKs of the tickers copy a decision of entry session `day` reads (league/events/run.py `Context.tickers_for`:
    the latest snapshot fetched before 07:30 ET of the day, else the earliest), or None when the store holds none."""
    from . import universe as U

    snaps = [(S.parse_iso(str(r["key"]).split("@", 1)[1]), str(r["value"])) for r in
             store.db.execute("SELECT key, value FROM meta WHERE key LIKE 'tickers@%' ORDER BY key")]
    if not snaps:
        return None
    chosen = [sha for at, sha in snaps if at < cutoff]
    sha = chosen[-1] if chosen else snaps[0][1]
    if f"tickers:{sha}" not in cache:
        data = store.get_document(sha)
        cache[f"tickers:{sha}"] = set(U.sec_tickers(lambda url: data))
    return cache[f"tickers:{sha}"]


def _fast_passes(store: S.Store, start: dt.datetime, end: dt.datetime, cache: dict[str, Any]) -> str | None:
    """A69 (i) as A84 reads it (the comment above FAST_RECORD_GAP): why the record passes from before `start` through
    `end` do not prove EACH FEED read whole, or None. For each of `RECORD_FEEDS` separately (8-K, Form 4, news, in that
    order), its CLEAN reads (a pass `_feed_problems` names no problem of that feed in) must be no more than
    FAST_RECORD_GAP apart from before `start` (the first at or before it, within FAST_RECORD_GAP) through `end` (the
    last within FAST_RECORD_GAP of it). A pass that missed a feed (its read errored or was cut, no tickers copy for the
    8-Ks, or the pass itself failed or never finished) is a missing read of that feed, not a broken span: the why names
    the feed, the gap and the first pass inside it that missed it."""
    span = f"passes:{S.iso(start)}:{S.iso(end)}"
    if span in cache:
        return cache[span]
    rows = store.db.execute("SELECT started_at, status, summary FROM receipts WHERE job=? AND started_at>=? AND "
                            "started_at<=? ORDER BY started_at, id",
                            (RECORD_JOB, S.iso(start - FAST_RECORD_GAP), S.iso(end))).fetchall()
    passes = [(S.parse_iso(str(r["started_at"])), _feed_problems(str(r["status"] or ""), r["summary"])) for r in rows]
    out: str | None = None
    for feed in RECORD_FEEDS:
        reads = [at for at, problems in passes if feed not in problems]
        if not reads or reads[0] > start:
            out = _missing(passes, feed, start - FAST_RECORD_GAP, reads[0] if reads else end)
        else:
            for a, b in zip(reads, reads[1:] + [end]):
                if b - a > FAST_RECORD_GAP:
                    out = _missing(passes, feed, a, b)
                    break
        if out is not None:
            break
    cache[span] = out
    return out


def _missing(passes: Sequence[tuple[dt.datetime, Mapping[str, str]]], feed: str, a: dt.datetime,
             b: dt.datetime) -> str:
    """A84: the why of a gap from `a` to `b` in the clean reads of `feed`: no pass ran in it, or the first pass in it
    missed the feed (and how many did)."""
    missed = [(at, problems[feed]) for at, problems in passes if a <= at < b and feed in problems]
    if not missed:
        return f"no record pass ran from {S.iso(a)} to {S.iso(b)}"
    at, problem = missed[0]
    more = f" ({len(missed)} passes missed it)" if len(missed) > 1 else ""
    return (f"no clean read of the {FEED_NAMES[feed]} feed from {S.iso(a)} to {S.iso(b)}, more than "
            f"{int(FAST_RECORD_GAP.total_seconds() // 60)} minutes: the record pass of {S.iso(at)} {problem}{more}")


def _feed_problems(status: str, summary: Any) -> dict[str, str]:
    """A84: {feed: why} for each feed of `RECORD_FEEDS` one record pass's receipt did NOT read cleanly (A69 (i)), {} for
    a pass that read all three. A pass not finished `ok`, or with an unreadable summary, read none cleanly; the 8-K
    feed's read needs the tickers copy (without it no 8-K is fetched: they wait), the news read must not be cut."""
    whole = None
    if status != "ok":
        whole = f"is {status or 'unfinished'}"
    else:
        try:
            body = json.loads(summary or "{}")
        except (TypeError, ValueError):
            body = None
        if not isinstance(body, dict):
            whole = "has an unreadable summary"
    if whole is not None:
        return {feed: whole for feed in RECORD_FEEDS}
    out: dict[str, str] = {}
    for form in RECORD_FORMS:
        part = body.get(form)
        if not isinstance(part, dict):
            out[form] = f"has no {form} read"
        elif "error" in part:
            out[form] = f"had a {form} feed error ({str(part['error'])[:80]})"
    tickers = body.get("tickers")
    if "8-K" not in out and isinstance(tickers, dict) and "error" in tickers:
        out["8-K"] = "could not read the tickers copy (its 8-Ks waited)"
    news = body.get("news")
    if not isinstance(news, dict):
        out["news"] = "has no news read"
    elif "error" in news:
        out["news"] = f"had a news error ({str(news['error'])[:80]})"
    elif news.get("cut"):
        out["news"] = "cut its news read short"
    return out


def run(store: S.Store, today: dt.date, *, programs: Sequence[tuple[str, int]] | None = None,
        now: dt.datetime | None = None, draws: int = B) -> dict[str, Any]:
    """The screen job: every seatable program's looks whose as-of session is on or before `today` and not yet written,
    each read from the record as of its session, once that close is FINAL for the program (`final_until`) and every
    intent (the control's too) scheduled to exit by then has settled. A registered SEATABLE birth (R3, loaded by
    league/events/programs.py `load_births`) is judged by PREREG-EVL-3's looks unchanged (`_run_v2`); a birth that is
    a record, and a birth's control, are never screened. At a held look the skew checks go to meta
    `skew:<program>:<version>:<k>` before p is computed. One program's failure is its own (release 1019b's review):
    it is in `errors` and the others' looks go on. Returns {written, waiting, errors}."""
    from .programs import BY_KEY

    now = now or S.utc_now()
    written, waiting, errors = [], [], []
    try:
        started = start_runs(store, now)    # (PREREG-EVL-6 section 3: waiting runs the budget holds now, in order)
    except Exception as exc:  # noqa: BLE001 - started again at the next run
        started = []
        errors.append({"program": None, "version": None, "error": f"start_runs: {type(exc).__name__}: {str(exc)[:200]}"})
    for program, version in programs or program_versions(store):
        born = _born(program, version)
        if program not in SEATABLE and born is None:
            continue
        prog = BY_KEY.get((program, int(version)))
        try:
            if prog is not None and prog.evl6:
                # PREREG-EVL-6 (sections 1.2-3): its versions' runs alone; a stay is the night's band review's
                out = _run_v6(store, program, version, today, now=now, draws=draws)
            elif prog is not None and prog.superseded6:
                # PREREG-EVL-6 section 1.1 (D7): a superseded version keeps PREREG-EVL-3's looks as a shadow record,
                # written and reported; league/events/bands.py `on_look` moves no band for it from REGISTERED_AT_6
                out = _run_v2(store, program, version, today, now=now, draws=draws)
            elif _seating(program, version):
                out = _run_v2(store, program, version, today, now=now, draws=draws)
            elif born is not None:
                continue        # (R3: a birth that is a record, or a birth's control, is never screened)
            elif version == 1:
                out = _run_v1(store, program, version, today, now=now, draws=draws)
            else:
                continue
        except Exception as exc:  # noqa: BLE001 - its looks are computed again at the next run
            errors.append({"program": program, "version": version, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        written += out["written"]
        waiting += out["waiting"]
    try:
        started += start_runs(store, now)   # (a run that ended at its 60th block in this job starts when room holds)
    except Exception as exc:  # noqa: BLE001
        errors.append({"program": None, "version": None, "error": f"start_runs: {type(exc).__name__}: {str(exc)[:200]}"})
    out = {"written": written, "waiting": waiting, "errors": errors}
    if started:
        out["runs_started"] = started
    return out


def _run_v1(store: S.Store, program: str, version: int, today: dt.date, *, now: dt.datetime,
            draws: int = B) -> dict[str, Any]:
    """Version 1's looks (PREREG-EVL-1 section 7): look k as of the close of session S_k from the first settled exit."""
    written: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    rows = settled_rows(store, program, version)
    anchor = min((r["exited"] for r in rows), default=None)
    if anchor is None:
        return {"written": written, "waiting": waiting}
    done = {r["k"] for r in look_rows(store, program, version)}
    pending = _pending(store, program, version)
    control = CONTROLS.get(program)
    ctl_pending = _pending(store, control, version) if control else []
    final: tuple[dt.date | None, str] | None = None
    for k, s_k in LOOKS:
        session = C.nth(store, anchor, s_k)
        if session is None or session.day > today:
            break
        if k in done:
            continue
        as_of = session.day
        if final is None:
            final = final_until(store, program, version, today, now)
        if final[0] is None or as_of > final[0]:
            waiting.append({"program": program, "version": version, "k": k,
                            "why": f"its as-of close is not final yet: {final[1]}"})
            break
        if any(x <= as_of for _, x in pending) or any(x <= as_of for _, x in ctl_pending):
            waiting.append({"program": program, "version": version, "k": k,
                            "why": "an intent scheduled to exit by the as-of session has not settled"})
            break
        look_set = covered(rows, as_of)
        first_entry = min((r["entry_day"] for r in rows), default=as_of)
        days = [s.day for s in C.sessions(store, first_entry, as_of)]
        ctl_rows = covered(settled_rows(store, control, version), as_of) if control else None
        have = skew_records(store, program, version, k)

        def record(checks: dict[str, Any], program: str = program, version: int = version, k: int = k) -> None:
            store.set_meta(f"skew:{program}:{version}:{k}", json.dumps(checks | {"at": S.iso(now)}, sort_keys=True))
        look = judge_look(look_set, days, k, program=program, version=version, at=session.close_at,
                          control_rows=ctl_rows, alphas=have, record=record, draws=draws)
        if write_look(store, look, now=now):
            written.append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")})
    return {"written": written, "waiting": waiting}


def expected_false_passes(store: S.Store) -> dict[str, Any]:
    """THE LANE'S EXPECTED FALSE PASSES, PREREG-EVL-6 section 5 (D6, D11), restating PREREG-EVL-3 section 4's and
    PREREG-EVL-4 section 3's count: 0.13 for every seatable version PREREG-EVL-6 registers or judges (its run 1:
    SEATING's versions, fifteen new versions and every seatable birth's, once league/events/programs.py `load_births`
    has loaded them; a later version of a seatable id the store holds beyond them too) and 0.13 for every fresh run when
    it starts (`budget6`); 0 for a version it supersedes (none can make a look that moves a band after REGISTERED_AT_6,
    and none has held one), as PREREG-EVL-3 dropped version 1. THE LANE'S LIFETIME BUDGET, RESTATED: 3.9 (30 x 0.13, a
    relaxation of PREREG-EVL-4's 3.0 by 0.9, accepted by the captain's D6, A107); R3's validator and the House's start
    of a fresh run charge against it (a birth only with room left after every waiting run). Beside the count, as every
    report shows it: the base model's (0.03 a version or run) and the stresses' worst (0.17), and the per-version figure
    (0.24 within 120 sessions at the worst plausible cell)."""
    b = budget6(store)
    charges = b["versions"] + b["runs"]
    return {"versions": b["versions"], "runs": b["runs"], "waiting": b["waiting"], "charge": V6_CHARGE,
            "expected": round(b["used"] / 100, 2), "budget": V6_BUDGET, "left": round(b["left"] / 100, 2),
            "left_after_waiting": round((b["left"] - V6_CHARGE_HUNDREDTHS * b["waiting"]) / 100, 2),
            "base": round(V6_BASE_RATE * charges, 2), "stress": round(V6_STRESS_RATE * charges, 2),
            "per_version": V6_PER_VERSION, "rule": "PREREG-EVL-6 section 5"}


def _births_failed(summary: Any) -> dict[str, Any]:
    """The registered births whose own part of a decision raised (league/events/run.py `BIRTHS_FAILED`), {} when none
    or unreadable."""
    try:
        body = json.loads(summary or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(body.get("births_failed") or {}) if isinstance(body, dict) else {}


def _born(program: str, version: int) -> Any:
    """The registered birth (R3) of this key, or None (every PREREG program)."""
    from .programs import BY_KEY

    p = BY_KEY.get((program, int(version)))
    return p if p is not None and p.spec is not None else None


def control_of(program: str) -> str | None:
    """A READ program's control (PREREG-EVL-1 section 7: its mean block value must exceed the control's): PREREG's own
    table (`CONTROLS`), or a registered READ birth's derived control (R3, league/events/births.py `control_spec`: its
    rule with every verdict condition removed, registered with it). Every PREREG program's answer is its table's."""
    if program in CONTROLS:
        return CONTROLS[program]
    born = _born(program, 1)
    if born is None or not born.reads:
        return None
    from .births import control_id

    return control_id(program)


# ------------------------------------------------------------------------------------------- version 2: PREREG-EVL-3
def _seating(program: str, version: int) -> bool:
    from .programs import BY_KEY

    p = BY_KEY.get((program, int(version)))
    return bool(p is not None and p.can_seat)


def v2_schedule(store: S.Store, rows: Sequence[Mapping[str, Any]], today: dt.date,
                pending: Sequence[tuple[dt.date, dt.date]] = (), *, after: tuple[dt.date, int] | None = None,
                final: tuple[dt.date | None, str] | None = None) -> dict[str, Any]:
    """PREREG-EVL-3's looks of one program from its settled rows: [(k, as_of day, merged ks)] in order, and where the
    scan stopped and why. Look k is at the first session close with >= V2_NS[k-1] settled TRADABLE events, >= 40
    issuers among them and >= 8 session blocks (covered: scheduled exits at or before that close); thresholds first
    reached at the same close are one look (the lowest k; the others merged into it). The scan stops at the first close
    by which an intent scheduled to exit has not settled (`pending`), and (`final`, `final_until`'s answer) at the
    first close a look falls due at before that close is final, so no look reads an incomplete record.

    `after` (the last WRITTEN look's as-of day, the highest k written or merged into a written look; release 1019b's
    review): the looks on record are never derived again from a record that grew since. The scan resumes strictly
    after that close at the next k: "looks happen in order, at most one at a session close ... No other look exists"
    (PREREG-EVL-3 section 3), whatever late events of the sessions it covered are settled later."""
    if not rows:
        return {"looks": [], "stopped": None, "why": None}
    first_entry = min(_day(r["entry_day"]) for r in rows)
    looks: list[tuple[int, dt.date, list[int]]] = []
    j = 0 if after is None else int(after[1])
    resume = None if after is None else after[0]
    stopped = why = None
    for s in C.sessions(store, first_entry, today):
        if resume is not None and s.day <= resume:
            continue
        if j >= len(V2_NS):
            break
        if any(x <= s.day for _, x in pending):
            stopped, why = s.day, f"an intent scheduled to exit by {s.day.isoformat()} has not settled"
            break
        cov = covered(rows, s.day)
        trad = [r for r in cov if _tradable(r)]
        n = len(trad)
        if n < V2_NS[j]:
            continue
        iss = len({str(r["issuer"]) for r in trad})
        blk = len({_day(r["entry_day"]) for r in trad})
        if iss < V2_MIN_ISSUERS or blk < V2_MIN_BLOCKS:
            continue
        if final is not None and (final[0] is None or s.day > final[0]):
            stopped, why = s.day, f"look {j + 1} falls due at {s.day.isoformat()}, not final yet: {final[1]}"
            break
        reached = [i for i in range(j, len(V2_NS)) if n >= V2_NS[i]]
        looks.append((reached[0] + 1, s.day, [i + 1 for i in reached[1:]]))
        j = reached[-1] + 1
    return {"looks": looks, "stopped": stopped, "why": why}


def written_v2(store: S.Store, program: str, version: int) -> dict[str, Any]:
    """The version 2 looks on record: {done: ks written, merged: ks merged into them (the look detail's `merged`),
    last: the as-of New York day of the latest one, next: the next k (None when all ten are used)}."""
    done: set[int] = set()
    merged: set[int] = set()
    last: dt.date | None = None
    for r in look_rows(store, program, version):
        k = int(r["k"])
        done.add(k)
        merged |= {int(x) for x in (look_detail(store, program, version, k) or {}).get("merged") or []}
        day = S.parse_iso(str(r["at"])).astimezone(C.NY).date()
        last = day if last is None or day > last else last
    used = done | merged
    nxt = (max(used) + 1) if used else 1
    return {"done": done, "merged": merged, "last": last, "next": nxt if nxt <= len(V2_NS) else None}


def _run_v2(store: S.Store, program: str, version: int, today: dt.date, *, now: dt.datetime,
            draws: int = B) -> dict[str, Any]:
    from . import bands as BA

    written: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    rows = settled_rows(store, program, version)
    if not rows:
        return {"written": written, "waiting": waiting}
    on_record = written_v2(store, program, version)
    if on_record["done"] and on_record["next"] is None:
        return {"written": written, "waiting": waiting}
    after = (on_record["last"], on_record["next"] - 1) if on_record["done"] else None
    control = control_of(program)
    pending = _pending(store, program, version) + (_pending(store, control, 1) if control else [])
    plan = v2_schedule(store, rows, today, pending, after=after, final=final_until(store, program, version, today, now))
    if plan["stopped"] is not None:
        waiting.append({"program": program, "version": version, "k": None, "why": plan["why"]})
    for k, as_of, merged in plan["looks"]:
        if k in on_record["done"] or k in on_record["merged"]:
            continue
        session = C.session(store, as_of)
        look_set = covered(rows, as_of)
        first_entry = min(_day(r["entry_day"]) for r in rows)
        days = [x.day for x in C.sessions(store, first_entry, as_of)]
        ctl_rows = covered(settled_rows(store, control, 1), as_of) if control else None
        have = skew_records(store, program, version, k)

        def record(checks: dict[str, Any], k: int = k) -> None:
            store.set_meta(f"skew:{program}:{version}:{k}", json.dumps(checks | {"at": S.iso(now)}, sort_keys=True))
        look = judge_look(look_set, days, k, program=program, version=version, at=session.close_at,
                          control_rows=ctl_rows, alphas=have, record=record, draws=draws, alpha=V2_ALPHA,
                          mins=(V2_NS[k - 1], V2_MIN_ISSUERS, V2_MIN_BLOCKS), sessions_at=len(days), retire=True)
        look["merged"] = merged
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            moved[0] = BA.on_look(store, look, now=now, db=db)   # in the look's own transaction
        if write_look(store, look, apply=apply, now=now):
            written.append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")}
                           | {"band": moved[0], "merged": merged})
    return {"written": written, "waiting": waiting}


def next_look_v2(store: S.Store, program: str, version: int, today: dt.date) -> dict[str, Any]:
    """Version 2's next unwritten look: {k, events_needed, events, issuers, blocks, status}: the k after the highest one
    written or merged into a written look (`written_v2`)."""
    nxt = written_v2(store, program, version)["next"]
    if nxt is None:
        return {"k": None, "status": "all looks written"}
    rows = settled_rows(store, program, version)
    trad = [r for r in rows if _tradable(r)]
    return {"k": nxt, "events_needed": V2_NS[nxt - 1], "events": len(trad),
            "issuers": len({str(r["issuer"]) for r in trad}), "blocks": len({_day(r["entry_day"]) for r in trad}),
            "status": "upcoming"}


# ================================================================================ PREREG-EVL-6: ONE MONEY-WEIGHTED SCREEN
#: PREREG-EVL-6 (docs/prereg/PREREG-EVL-6.md, tag prereg-evl-6, sha256 0f67f94e..., REGISTERED_AT_6 2026-10-22T12:24:50Z,
#: A116), sections 1.2-3, for the versions it judges (league/events/programs.py `Program.evl6`: its new versions and
#: every seatable version registered at or after REGISTERED_AT_6), and ONLY for them: PREREG-EVL-1's and -3's screens
#: above stay as they are for every version they judge (the versions PREREG-EVL-6 supersedes keep PREREG-EVL-3's looks
#: as a shadow record, D7). Built to the frozen text and to its reference calibration (docs/prereg/evl-6/calib_v2.py,
#: search_final.py and demotion_v2.py: league/tests/test_events_evl6_calib.py runs their own synthetic arrays through
#: this code and compares every statistic and decision).
#: - THE RECORD (1.2): a run's (or a stay's) settled events (status `settled`, knowable after the registration time:
#:   the version's own intents are), its scheduled exits at or before the as-of close X; only TRADABLE events enter a
#:   figure. BLOCKS: each entry session holding a TRADABLE event, in session order; n_s its TRADABLE count, B_s their
#:   mean a (`math.fsum`).
#: - THE VALUES (D4): y_s = min(n_s, 14) x (B_s - 0.0010); the lower tail's -min(n_s, 14) x B_s (no margin).
#: - p (1.3): the one-sided sign-flip p of mean(y) > 0, EXACT over all 2^S sign vectors for S <= 16 (count / 2^S; `_count`
#:   over `b.to_bytes(width, "little")` for every b), else (1 + count) / (1 + 99,999) over `random.Random(seed)
#:   .getrandbits(S)` (bit j set = +1 for value j), seed = int.from_bytes(sha256(seed string).digest()[:8], "big"), seed
#:   string f"{id}|v{version}|evl6|{tag}S{S}"; a signed sum at or above the observed sum less S x 1e-12 counts against
#:   the program. TAG: "" for run 1, f"run{n}|" for run n >= 2, f"stay{n}|" for the n-th Probe stay. q: the same count on
#:   the lower values over the same vectors. p_I: PREREG-EVL-1 section 7's issuer-block p (each issuer's TRADABLE events
#:   averaged, ascending issuer order, no margin), 99,999 vectors, seed string + "|issuer".
#: - alpha(S) (D14): 0.020 for 22 <= S <= 30, 0.006 for 31-40, 0.001 for 41-60; no look below the 22nd block.
#: - RETIRE (1.4), first: mean a < 0 and q <= alpha(S) + 1e-12 (nothing else is checked). PASS: p <= alpha(S) (no
#:   tolerance); >= 30 TRADABLE events and >= 30 distinct issuers; mean a > 0 and mean r > 0; THE MONEY'S EVENTS: each
#:   block's top 14 TRADABLE events by the program's own ranking (`book.picks`' order: rank_key descending, a missing key
#:   last; then the issuer's adv20 on the entry session descending, missing as 0; then the event id), pooled, mean a > 0
#:   and mean r > 0; a READ version's mean block value (unweighted) above its control's over the same sessions (the
#:   control's TRADABLE events of those sessions knowable after the version's registration time); p_I <= 0.10.
#: - LOOKS (2): look k at the first close X at which the run's covered record holds >= S_k blocks (22, 25, 30, 35, 40,
#:   50, 60) AND the minimums hold (30 events, 30 issuers, 6 blocks); in order, at most one a close; every S_k reached
#:   by then is consumed (the lowest k is the look, the others merged); alpha at the record's own S; never after the
#:   run's 60th block. A look waits until X is final (`final_until`) and every intent of the version and of its control
#:   scheduled to exit by X has settled; written once (INSERT OR IGNORE) under a key that carries its tag (`look_key6`).
#: - RUNS (2-3, D2, D11): a run ends at its PASS, its RETIRE or its 60th block (then the version stays in learning);
#:   run n + 1 starts at the first block after run n's 60th, or at the first decision after a demotion, ONLY WHEN THE
#:   LANE'S BUDGET (3.9 expected false passes) HOLDS ITS 0.13: waiting runs start in their versions' registration order
#:   (`start_runs`), a version waiting holds no run (no look, no pass, no retirement). Each start is charged when written.
#: - STAYS (3): the n-th move to probe begins stay n; its record the version's TRADABLE events whose entry decision is at
#:   or after the first decision made at Probe; its looks as a run's (tag stay{n}|), to its own 60th block; its RETIRE
#:   demotes, its PASS with section 3's real-money conditions moves Probe to Sized (league/events/bands.py `review`, in
#:   section 3's order with the fixed reads and the money stop).
V6_LOOKS: tuple[int, ...] = (22, 25, 30, 35, 40, 50, 60)
V6_ALPHAS: tuple[tuple[int, float], ...] = ((30, 0.020), (40, 0.006), (60, 0.001))
V6_MARGIN = 0.0010
V6_CAP = 14
V6_MIN_EVENTS = 30
V6_MIN_ISSUERS = 30
V6_MIN_BLOCKS = 6
V6_ISSUER_P = 0.10
V6_EXACT = 16
V6_RUN_BLOCKS = 60
#: Section 5: THE LANE'S COUNT (D6) and its restated lifetime budget, in HUNDREDTHS of an expected false pass (integers:
#: no float drift): 0.13 for every seatable version this file registers or judges (its run 1) and for every fresh run
#: when it starts; 0 for a superseded version; 3.9 in all (30 x 0.13, a relaxation of PREREG-EVL-4's 3.0 accepted by
#: the captain's D6, A107). Every report shows the count three ways and the per-version figure beside it.
V6_CHARGE_HUNDREDTHS = 13
V6_BUDGET_HUNDREDTHS = 390
V6_CHARGE = V6_CHARGE_HUNDREDTHS / 100
V6_BUDGET = V6_BUDGET_HUNDREDTHS / 100
V6_BASE_RATE = 0.03
V6_STRESS_RATE = 0.17
V6_PER_VERSION = 0.24
#: The stored key of a look of this file (`looks.k`): it carries the run or stay and the record's own S, so a later run's
#: or a stay's look is never dropped as a duplicate of an earlier one (section 2: "identified by (id, version, its run or
#: stay tag, S)"): 1000 x n + S for run n, STAY_BASE + 1000 x n + S for stay n.
V6_STAY_BASE = 1_000_000
#: meta: a fresh run's start (written once, when the budget holds its charge) and a run's end at its 60th block.
V6_RUN_KEY = "evl6:run:{program}:{version}:{n}"
V6_END_KEY = "evl6:end:{program}:{version}:{n}"


def v6_alpha(S: int) -> float | None:
    """alpha(S) by the record's own S (section 1.3, D14); None below the first look's 22 blocks or above 60."""
    S = int(S)
    if S < V6_LOOKS[0] or S > V6_RUN_BLOCKS:
        return None
    for upper, alpha in V6_ALPHAS:
        if S <= upper:
            return alpha
    return None


def v6_tag(kind: str, n: int) -> str:
    """Section 1.3's TAG: "" for a version's run 1, f"run{n}|" for its run n >= 2, f"stay{n}|" for its n-th stay."""
    if kind == "stay":
        return f"stay{int(n)}|"
    return "" if int(n) == 1 else f"run{int(n)}|"


def v6_seed_string(program: str, version: int, tag: str, S: int) -> str:
    """The session test's (and the lower tail's) seed string; the issuer guard's is this + "|issuer"."""
    return f"{program}|v{int(version)}|evl6|{tag}S{int(S)}"


def look_key6(kind: str, n: int, S: int) -> int:
    """A PREREG-EVL-6 look's stored `k` (`V6_STAY_BASE`'s comment)."""
    return (V6_STAY_BASE if kind == "stay" else 0) + 1000 * int(n) + int(S)


def key_of6(k: int) -> tuple[str, int, int]:
    """(kind, n, S) of a stored PREREG-EVL-6 look key."""
    k = int(k)
    kind = "stay" if k >= V6_STAY_BASE else "run"
    rest = k - (V6_STAY_BASE if kind == "stay" else 0)
    return kind, rest // 1000, rest % 1000


def _exact_flips(n: int) -> Iterable[bytes]:
    """Every sign vector of `n` values (bit j of b set = +1 for value j), as `_count` reads them."""
    width = (n + 7) // 8
    return (b.to_bytes(width, "little") for b in range(1 << n))


#: A source of Monte Carlo sign vectors for given values (league/tests/test_events_evl6_calib.py: the calibration's own
#: fixed vectors, which it applies to |y|, turned into vectors over y): values -> little-endian bytes, bit j = +1.
FlipSource = Callable[[Sequence[float]], Iterable[bytes]]


def v6_count_p(values: Sequence[float], seed_text: str, draws: int = B, *, flips: FlipSource | None = None) -> float:
    """Section 1.3's sign-flip p of mean(values) > 0: EXACT over all 2^S vectors for S <= 16 (count / 2^S), else the
    Monte Carlo (1 + count) / (1 + draws) over `draws` vectors from the seed string's seed. `flips`: another source of
    the Monte Carlo vectors (the reproduction test's), never used by the lane."""
    vals = _check_values(values)
    S = len(vals)
    if S <= V6_EXACT:
        return _count(vals, _exact_flips(S)) / float(1 << S)
    if flips is not None:
        got = list(flips(vals))
        return (1 + _count(vals, got)) / (1 + len(got))
    return (1 + _count(vals, _flips(seed_of(seed_text), S, draws))) / (1 + int(draws))


@dataclasses.dataclass(frozen=True)
class Block6:
    """One block of a PREREG-EVL-6 record: its entry session, its TRADABLE events (in the program's ranking order:
    `rank_order`), their count n, mean a (B) and mean r."""

    day: dt.date
    events: tuple[Mapping[str, Any], ...]

    @property
    def n(self) -> int:
        return len(self.events)

    @property
    def value(self) -> float:
        return math.fsum(float(e["a"]) for e in self.events) / len(self.events)

    @property
    def mean_r(self) -> float:
        return math.fsum(float(e["r"]) for e in self.events) / len(self.events)

    def top(self, cap: int = V6_CAP) -> tuple[Mapping[str, Any], ...]:
        return self.events[:cap]


def rank_order(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Section 1.4's order of a session's events (`book.picks`' before ROOM and the sale gate): `rank_key` descending, a
    missing key last; then the issuer's `adv20` on the entry session descending, a missing adv20 counting as 0; then the
    event id."""
    rank = row.get("rank_key")
    adv = row.get("adv20")
    return (rank is None, -(float(rank) if rank is not None else 0.0), -(float(adv) if adv is not None else 0.0),
            str(row.get("event")))


def blocks6(rows: Iterable[Mapping[str, Any]]) -> list[Block6]:
    """The blocks of a record (section 1.2): every entry session holding at least one TRADABLE event, in session order,
    each with its TRADABLE events in the program's ranking order. An event without a finite a and r is an error."""
    groups: dict[dt.date, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not _tradable(row):
            continue
        a, r = row.get("a"), row.get("r")
        if a is None or r is None or not (math.isfinite(float(a)) and math.isfinite(float(r))):
            raise ValueError(f"event {row.get('event')} has no finite a and r")
        groups.setdefault(_day(row["entry_day"]), []).append(row)
    return [Block6(day, tuple(sorted(g, key=rank_order))) for day, g in sorted(groups.items())]


def v6_values(blocks: Sequence[Block6]) -> list[float]:
    """D4's money-weighted values: y_s = min(n_s, 14) x (B_s - 0.0010)."""
    return [min(b.n, V6_CAP) * (b.value - V6_MARGIN) for b in blocks]


def v6_lower(blocks: Sequence[Block6]) -> list[float]:
    """The lower tail's values: -min(n_s, 14) x B_s (no margin)."""
    return [-min(b.n, V6_CAP) * b.value for b in blocks]


def v6_minimums(n: int, issuers: int, S: int) -> bool:
    return n >= V6_MIN_EVENTS and issuers >= V6_MIN_ISSUERS and S >= V6_MIN_BLOCKS


def v6_judge(blocks: Sequence[Block6], *, program: str, version: int, tag: str, control_rows: Sequence[Mapping[str, Any]]
             | None = None, control: str | None = None, draws: int = B, flips: FlipSource | None = None,
             issuer_flips: FlipSource | None = None, beside: bool = True) -> dict[str, Any]:
    """ONE LOOK OF PREREG-EVL-6 (sections 1.3-1.4) on a record's blocks: {S, alpha, p, q, p_issuer, figures, guards,
    decision ("retire" | "pass" | None), why}. RETIRE is checked first and, when it holds, nothing else is; PASS needs
    every condition. `control` (a READ version's control id) with `control_rows` (its settled rows of these sessions,
    knowable after the version's registration time). `flips` / `issuer_flips`: the calibration's own sign vectors for
    the session tests and the issuer guard (league/tests/test_events_evl6_calib.py); by default the seeded ones."""
    S = len(blocks)
    alpha = v6_alpha(S)
    events = [e for b in blocks for e in b.events]
    n = len(events)
    issuers = issuer_values(events)
    mean_a = _mean([float(e["a"]) for e in events])
    mean_r = _mean([float(e["r"]) for e in events])
    tops = [e for b in blocks for e in b.top()]
    top_a = _mean([float(e["a"]) for e in tops])
    top_r = _mean([float(e["r"]) for e in tops])
    weights = [min(b.n, V6_CAP) for b in blocks]
    money_a = (math.fsum(w * b.value for w, b in zip(weights, blocks)) / sum(weights)) if weights else None
    block_mean = _mean([b.value for b in blocks])
    text = v6_seed_string(program, version, tag, S)
    out: dict[str, Any] = {"S": S, "alpha": alpha, "tag": tag, "seed": text, "n": n, "issuers": len(issuers),
                           "mean_a": mean_a, "mean_r": mean_r, "money_a": money_a, "top14": {"n": len(tops),
                           "mean_a": top_a, "mean_r": top_r}, "block_mean": block_mean, "p": None, "q": None,
                           "p_issuer": None, "control": None, "guards": {}, "decision": None, "why": ""}
    if S == 0:
        out["why"] = "no block"
        return out
    p = v6_count_p(v6_values(blocks), text, draws, flips=flips)
    q = v6_count_p(v6_lower(blocks), text, draws, flips=flips)
    if issuer_flips is not None:
        vals = _check_values([v for _, v in issuers])
        got = list(issuer_flips(vals))
        p_i = (1 + _count(vals, got)) / (1 + len(got))
    else:
        p_i = signflip_p([v for _, v in issuers], seed_of(text + "|issuer"), draws)
    out.update(p=p, q=q, p_issuer=p_i)
    c_mean = c_blocks = None
    if control is not None:
        c_mean, c_blocks = control_mean(control_rows or [], [b.day for b in blocks])
        out["control"] = {"program": control, "mean_block": c_mean, "blocks": c_blocks, "program_mean_block": block_mean}
    if beside:
        out["beside"] = {"p_r": v6_count_p([b.mean_r for b in blocks], text, draws, flips=flips),
                         "event_weighted_a": mean_a, "money_weighted_a": money_a}
    if alpha is None:
        out["why"] = f"no look at {S} blocks (looks from the {V6_LOOKS[0]}nd block to the {V6_RUN_BLOCKS}th)"
        return out
    if mean_a is not None and mean_a < 0 and q <= alpha + TIE:
        out.update(decision="retire", why=f"RETIRE: mean a {mean_a:.6f} < 0 and q {q:.6f} <= alpha {alpha:.3f}")
        return out
    guards = {
        "p": p <= alpha,
        "events": n >= V6_MIN_EVENTS, "issuers": len(issuers) >= V6_MIN_ISSUERS, "blocks": S >= V6_MIN_BLOCKS,
        "mean_a": mean_a is not None and mean_a > 0, "mean_r": mean_r is not None and mean_r > 0,
        "top14_a": top_a is not None and top_a > 0, "top14_r": top_r is not None and top_r > 0,
        "issuer": p_i <= V6_ISSUER_P,
    }
    if control is not None:
        guards["control"] = c_mean is not None and block_mean is not None and block_mean > c_mean
    out["guards"] = guards
    fails = [k for k, ok in guards.items() if not ok]
    if not fails:
        out.update(decision="pass", why=f"PASS: p {p:.6f} <= alpha {alpha:.3f}, every guard holds")
    else:
        out["why"] = "fail: " + ", ".join(fails)
    return out


def settled_rows6(store: Any, program: str, version: int) -> list[dict[str, Any]]:
    """`settled_rows` with what PREREG-EVL-6's record reads beside: each event's `rank_key` and `decided_at` (its intent's)
    and its issuer's `adv20` on the entry session (the largest of the universe rows of that day and CIK, none: None)."""
    rows = settled_rows(store, program, version)
    if not rows:
        return rows
    extra = {str(r["event"]): (r["rank_key"], r["decided_at"]) for r in store.db.execute(
        "SELECT event, rank_key, decided_at FROM intents WHERE program=? AND version=?", (program, int(version)))}
    days = sorted({r["entry_day"].isoformat() for r in rows})
    advs: dict[tuple[str, str], float] = {}
    for lo in range(0, len(days), 400):
        part = days[lo:lo + 400]
        for u in store.db.execute(f"SELECT day, cik, MAX(adv20) AS adv FROM universe WHERE day IN "
                                  f"({', '.join('?' * len(part))}) GROUP BY day, cik", part):
            if u["adv"] is not None:
                advs[(str(u["day"]), str(u["cik"]))] = float(u["adv"])
    for r in rows:
        rank, decided = extra.get(str(r["event"]), (None, None))
        r["rank_key"], r["decided_at"] = rank, decided
        r["adv20"] = advs.get((r["entry_day"].isoformat(), str(r["issuer"])))
    return rows


def _after(row: Mapping[str, Any], moment: dt.datetime | None) -> bool:
    if moment is None:
        return True
    try:
        return S.parse_iso(str(row["decided_at"])) > moment
    except (KeyError, TypeError, ValueError):
        return False        # (a decision time that cannot be read: not in the record, the reading less likely to pass)


def control_rows6(store: Any, control: str, since: dt.datetime) -> list[dict[str, Any]]:
    """A READ version's control record for PREREG-EVL-6 (section 1.4): the control's settled rows (version 1) whose
    events are knowable after `since` (the version's registration time)."""
    from .programs import knowable_of

    out = []
    for r in settled_rows(store, control, 1):
        k = knowable_of(store, str(r["event"]))
        if k is not None and k > since:
            out.append(r)
    return out


def _band_moves(store: Any, program: str, version: int) -> list[dict[str, Any]]:
    """The version's band moves in order: {band, at (the later of since and written_at), id}."""
    out = []
    try:
        rows = store.db.execute("SELECT id, band, since, written_at FROM band_history WHERE program=? AND version=? "
                                "ORDER BY id", (program, int(version))).fetchall()
    except Exception:  # noqa: BLE001 - no band history yet
        return out
    for r in rows:
        moments = []
        for text in (r["since"], r["written_at"]):
            try:
                moments.append(S.parse_iso(str(text)))
            except (TypeError, ValueError):
                continue
        out.append({"id": int(r["id"]), "band": str(r["band"]), "at": max(moments) if moments else None})
    return out


def stays6(store: Any, program: str, version: int) -> list[dict[str, Any]]:
    """The version's Probe stays (section 3): [{n, since (the move to probe), until (its demotion or retirement, None
    while it lasts), sized (the move to sized inside it, or None)}], stay n beginning at the n-th move to probe."""
    out: list[dict[str, Any]] = []
    for m in _band_moves(store, program, version):
        if m["band"] == "probe" and (not out or out[-1]["until"] is not None):
            out.append({"n": len(out) + 1, "since": m["at"], "until": None, "sized": None})
        elif out and out[-1]["until"] is None:
            if m["band"] == "sized":
                out[-1]["sized"] = m["at"]
            elif m["band"] in ("learning", "retired"):
                out[-1]["until"] = m["at"]
                out[-1]["ended"] = m["band"]
    return out


def _meta_json(store: Any, key: str) -> dict[str, Any] | None:
    raw = store.meta(key) if hasattr(store, "meta") else None
    if raw is None:
        return None
    try:
        got = json.loads(raw)
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def runs6(store: Any, program: str, version: int) -> list[dict[str, Any]]:
    """The version's runs (sections 2-3) as the store records them: [{n, after_day, after (its record's bounds), started
    (iso), ended (None, or {why: pass | retire | horizon | probe, at})}]. Run 1 needs no record (charged with its version);
    a fresh run is the one `start_runs` wrote. A run ends at a written look that passed or retired, at its 60th block's
    end record, or (a run that was passing) when the version moved to probe."""
    out = [{"n": 1, "after_day": None, "after": None, "started": None, "ended": None}]
    n = 2
    while True:
        rec = _meta_json(store, V6_RUN_KEY.format(program=program, version=int(version), n=n))
        if rec is None:
            break
        out.append({"n": n, "after_day": rec.get("after_day"), "after": rec.get("after"), "started": rec.get("started"),
                    "ended": None, "why": rec.get("why")})
        n += 1
    looks = {int(r["k"]): r for r in look_rows(store, program, version)}
    for run in out:
        for k, r in sorted(looks.items()):
            kind, rn, _ = key_of6(k)
            if kind == "run" and rn == run["n"]:
                d = (look_detail(store, program, version, k) or {}).get("v6") or {}
                if d.get("decision") in ("pass", "retire"):
                    run["ended"] = {"why": d["decision"], "at": str(r["at"])}
        end = _meta_json(store, V6_END_KEY.format(program=program, version=int(version), n=run["n"]))
        if run["ended"] is None and end is not None:
            run["ended"] = {"why": "horizon", "at": end.get("at"), "last_day": end.get("last_day")}
    return out


def run_record6(rows: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """A run's record of `rows` (the version's settled rows): run 1 every one; a fresh run's from its start record's
    bounds: blocks after `after_day` (the first block after run n - 1's 60th) and entries decided after `after` (a
    demotion's, or the close at which the budget held its charge)."""
    after_day = dt.date.fromisoformat(str(run["after_day"])) if run.get("after_day") else None
    after = S.parse_iso(str(run["after"])) if run.get("after") else None
    return [r for r in rows if (after_day is None or _day(r["entry_day"]) > after_day) and _after(r, after)]


def written6(store: Any, program: str, version: int, kind: str, n: int) -> dict[str, Any]:
    """The PREREG-EVL-6 looks on record of one run or stay: {consumed: threshold indexes used (1-based, the looks' k and
    the ones merged into them), last: the as-of New York day of the latest, S: the largest S looked at}."""
    consumed: set[int] = set()
    last: dt.date | None = None
    top = 0
    for r in look_rows(store, program, version):
        k = int(r["k"])
        knd, rn, s = key_of6(k)
        if knd != kind or rn != int(n):
            continue
        d = look_detail(store, program, version, k) or {}
        consumed |= {int((d.get("v6") or {}).get("look", 0))} | {int(x) for x in d.get("merged") or []}
        day = S.parse_iso(str(r["at"])).astimezone(C.NY).date()
        last = day if last is None or day > last else last
        top = max(top, s)
    consumed.discard(0)
    return {"consumed": consumed, "last": last, "S": top}


def schedule6(store: Any, record: Sequence[Mapping[str, Any]], today: dt.date, *,
              pending: Sequence[tuple[dt.date, dt.date]] = (), consumed: Iterable[int] = (),
              after: dt.date | None = None, final: tuple[dt.date | None, str] | None = None
              ) -> dict[str, Any]:
    """Section 2's looks of one run (or stay) record from where the record on file left it: [(look k, as-of day, merged
    ks, S)] in order, the close its 60th block is covered at (`horizon`, when the scan reaches it), and where the scan
    stopped and why (an intent scheduled to exit by a close not settled; a look or the horizon due at a close not final
    yet). `after`: the as-of day of the run's last written look (the scan resumes after it); `consumed` the thresholds
    already used."""
    out: dict[str, Any] = {"looks": [], "horizon": None, "stopped": None, "why": None}
    if not record:
        return out
    used = set(int(k) for k in consumed)
    j = max(used) if used else 0
    first = min(_day(r["entry_day"]) for r in record)
    for s in C.sessions(store, first, today):
        if after is not None and s.day <= after:
            continue
        if any(x <= s.day for _, x in pending):
            out["stopped"], out["why"] = s.day, f"an intent scheduled to exit by {s.day.isoformat()} has not settled"
            break
        every = blocks6(covered(record, s.day))
        blk = every[:V6_RUN_BLOCKS]
        S_ = len(blk)
        events = [e for b in blk for e in b.events]
        held = j < len(V6_LOOKS) and S_ >= V6_LOOKS[j] and \
            v6_minimums(len(events), len({str(e["issuer"]) for e in events}), S_)
        horizon = len(every) >= V6_RUN_BLOCKS
        if (held or horizon) and final is not None and (final[0] is None or s.day > final[0]):
            what = f"look {j + 1}" if held else "the run's 60th block"
            out["stopped"], out["why"] = s.day, f"{what} falls due at {s.day.isoformat()}, not final yet: {final[1]}"
            break
        if held:
            reached = [i for i in range(j, len(V6_LOOKS)) if S_ >= V6_LOOKS[i]]
            out["looks"].append((reached[0] + 1, s.day, [i + 1 for i in reached[1:]], S_))
            j = reached[-1] + 1
        if horizon:
            out["horizon"] = (s.day, every[V6_RUN_BLOCKS - 1].day)
            break
    return out


def last_close(store: Any, now: dt.datetime) -> C.Session | None:
    """The last session whose close is at or before `now` (the lane's calendar)."""
    row = store.db.execute("SELECT day FROM sessions WHERE close_at<=? ORDER BY day DESC LIMIT 1", (S.iso(now),)).fetchone()
    return None if row is None else C.session(store, dt.date.fromisoformat(str(row[0])))


def _v6_programs() -> list[Any]:
    from .programs import SEATING

    return [p for p in SEATING if p.evl6]


def waiting_runs(store: Any, now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """THE RUNS WAITING FOR THE BUDGET (section 3, D11): every PREREG-EVL-6 version in `learning` whose last run ended
    at its 60th block, or that was demoted after its last run passed, and has no run since: [{program, version, n (the
    run that waits), why, after_day, after (the record's bounds if it started now), registered_at}], in the order they
    start: the versions' registration order (the earliest REGISTERED_AT first, then the id). A retired version waits
    for nothing."""
    from . import bands as BA

    band_of = BA.bands(store)
    out = []
    for p in _v6_programs():
        if band_of.get((p.id, p.version), "learning") != "learning":
            continue
        runs = runs6(store, p.id, p.version)
        last = runs[-1]
        ended = last.get("ended")
        if ended is None:
            continue
        item = {"program": p.id, "version": p.version, "n": last["n"] + 1, "registered_at": S.iso(p.registered_at)}
        if ended["why"] == "horizon":
            item |= {"why": f"run {last['n']} reached its {V6_RUN_BLOCKS}th block unpassed", "after_day":
                     ended.get("last_day"), "at": ended.get("at"), "after": None}
        elif ended["why"] == "pass":
            stays = stays6(store, p.id, p.version)
            demoted = [s for s in stays if s.get("ended") == "learning" and s["until"] is not None]
            if not demoted:
                continue        # (passed: its band moves with the look; a demotion back to learning opens the next run)
            item |= {"why": f"demoted from its stay {demoted[-1]['n']}", "after_day": None, "at": None,
                     "after": S.iso(demoted[-1]["until"])}
        else:
            continue
        out.append(item)
    return sorted(out, key=lambda x: (x["registered_at"], x["program"], x["version"]))


def budget6(store: Any) -> dict[str, int]:
    """THE LANE'S CHARGES (section 5, D6), in hundredths: {versions: each PREREG-EVL-6 version in SEATING (its run 1),
    extra: a later version of a seatable id the store holds intents of beyond SEATING's, runs: the fresh runs started,
    used, waiting: the runs waiting for room (each would charge 0.13), left}."""
    from .programs import BY_KEY, SEATING

    seating = {(p.id, p.version) for p in SEATING}
    top: dict[str, int] = {}
    for pid, version in seating:
        top[pid] = max(top.get(pid, 0), int(version))
    extra = {(p, v) for p, v in program_versions(store) if p in SEATABLE and v > top.get(p, 0)
             and (p, v) not in seating and not getattr(BY_KEY.get((p, v)), "superseded6", False)}
    runs = 0
    for p in SEATING:
        runs += sum(1 for r in runs6(store, p.id, p.version) if r["n"] >= 2)
    versions = len(seating) + len(extra)
    used = V6_CHARGE_HUNDREDTHS * (versions + runs)
    waiting = len(waiting_runs(store))
    return {"versions": versions, "extra": len(extra), "runs": runs, "used": used, "waiting": waiting,
            "left": V6_BUDGET_HUNDREDTHS - used}


def start_runs(store: Any, now: dt.datetime) -> list[dict[str, Any]]:
    """THE HOUSE'S START OF FRESH RUNS (section 3, D11): every waiting run (`waiting_runs`, in registration order)
    starts while the lane's budget holds its 0.13 (used + 0.13 <= 3.9), each written once (meta `V6_RUN_KEY`) with the
    bounds of its record: the first block after the run that ended at its 60th block (`after_day`) or the first
    decision after the demotion (`after`), AND, when it starts at a later close than that end or demotion, only the
    entries decided after that close. A run the budget cannot hold waits (no look, no pass, no retirement), and so does
    every run after it in the order. Returns the runs started."""
    started = []
    budget = budget6(store)
    used = budget["used"]
    close = last_close(store, now)
    for item in waiting_runs(store, now):
        if used + V6_CHARGE_HUNDREDTHS > V6_BUDGET_HUNDREDTHS:
            break
        bound = item.get("after")
        if item.get("at"):          # (a 60th block's end: no extra bound when the room holds it at that very close)
            end_close = S.parse_iso(str(item["at"]))
            if close is not None and close.close_at > end_close:
                bound = S.iso(close.close_at)
        elif bound is not None and close is not None and close.close_at > S.parse_iso(bound):
            bound = S.iso(close.close_at)       # (a demotion before the last close: the room held only at that close)
        record = {"n": item["n"], "after_day": item.get("after_day"), "after": bound, "started": S.iso(now),
                  "why": item["why"], "charge": V6_CHARGE}
        key = V6_RUN_KEY.format(program=item["program"], version=item["version"], n=item["n"])
        cur = store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(record, sort_keys=True)))
        if cur.rowcount == 1:
            used += V6_CHARGE_HUNDREDTHS
            started.append({"program": item["program"], "version": item["version"]} | record)
    return started


def next_look6(store: Any, program: str, version: int, today: dt.date) -> dict[str, Any]:
    """The next PREREG-EVL-6 look of a version (the report's and the site's): {k, kind (run | stay), n, tag, blocks_needed
    (S_k), blocks (now), events, issuers, status}; {k: None, status} for a version waiting for its run, retired, or past
    its looks."""
    from . import bands as BA

    band = BA.bands(store).get((program, int(version)), "learning")
    if band == "retired":
        return {"k": None, "status": "retired"}
    rows = settled_rows6(store, program, version)
    if band in ("probe", "sized"):
        stays = stays6(store, program, version)
        if not stays:
            return {"k": None, "status": "no stay on record"}
        kind, n = "stay", stays[-1]["n"]
        since = stays[-1]["since"]
        record = [r for r in rows if _after(r, since)]
    else:
        runs = runs6(store, program, version)
        run = runs[-1]
        if run["ended"] is not None:
            return {"k": None, "status": f"run {run['n']} ended ({run['ended']['why']}); run {run['n'] + 1} waits for the "
                                         "lane's budget"}
        kind, n = "run", run["n"]
        record = run_record6(rows, run)
    on = written6(store, program, version, kind, n)
    j = max(on["consumed"]) if on["consumed"] else 0
    blk = blocks6(record)[:V6_RUN_BLOCKS]
    events = [e for b in blk for e in b.events]
    if j >= len(V6_LOOKS):
        return {"k": None, "kind": kind, "n": n, "tag": v6_tag(kind, n), "status": "all looks written",
                "blocks": len(blk)}
    return {"k": j + 1, "kind": kind, "n": n, "tag": v6_tag(kind, n), "blocks_needed": V6_LOOKS[j], "blocks": len(blk),
            "events": len(events), "issuers": len({str(e["issuer"]) for e in events}), "status": "upcoming"}


def _look6_row(program: str, version: int, kind: str, n: int, k: int, merged: list[int], at: Any, days: int,
               judged: Mapping[str, Any]) -> dict[str, Any]:
    """A PREREG-EVL-6 look as `write_look` writes it: the `looks` row (k carries the tag: `look_key6`) and its detail
    (`v6`: the tag, the look's k and the thresholds merged into it, S, p, q, p_I, alpha, every guard and figure)."""
    decision = judged.get("decision")
    look: dict[str, Any] = {
        "program": program, "version": int(version), "k": look_key6(kind, n, judged["S"]),
        "at": S.iso(at) if isinstance(at, dt.datetime) else str(at), "sessions": int(days), "n": judged["n"],
        "issuers": judged["issuers"], "blocks": judged["S"], "mean_a": judged["mean_a"], "mean_r": judged["mean_r"],
        "mean_a_tradable": judged["mean_a"], "p": judged["p"], "alpha": judged["alpha"], "fp_check": None, "held": 1,
        "passed": int(decision == "pass"), "why": judged["why"][:400],
        "issuer": {"p": judged["p_issuer"], "alpha": V6_ISSUER_P}, "control": judged.get("control"), "skew": None,
        "beside": judged.get("beside"), "retirement": {"retire": decision == "retire", "q": judged["q"]},
        "merged": list(merged),
        "v6": {"rule": "PREREG-EVL-6", "kind": kind, "n": int(n), "tag": judged["tag"], "look": int(k), "S": judged["S"],
               "seed": judged["seed"], "p": judged["p"], "q": judged["q"], "p_issuer": judged["p_issuer"],
               "alpha": judged["alpha"], "guards": judged.get("guards"), "top14": judged.get("top14"),
               "money_a": judged.get("money_a"), "block_mean": judged.get("block_mean"), "decision": decision},
    }
    return look


def _run_v6(store: S.Store, program: str, version: int, today: dt.date, *, now: dt.datetime,
            draws: int = B) -> dict[str, Any]:
    """PREREG-EVL-6's looks of a version in `learning` (its current run): each look due by `today` whose as-of close is
    final for it (`final_until`), with every intent of it and of its control scheduled to exit by then settled and its
    copied record before the release complete (league/events/programs.py `uncopied`), written once with its band move
    in its own transaction (league/events/bands.py `on_look`: PASS to Probe, RETIRE to retired); the run's END at its
    60th block (section 2: decided with that close's look, after its RETIRE and PASS, or once that close is final)
    written in a transaction of its own (meta `V6_END_KEY`). A version at Probe or Sized is the night's band review's
    (its stay's looks, reads and money stop in section 3's order); a waiting or retired version has no look."""
    from . import bands as BA
    from .programs import BY_KEY, uncopied

    written: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    prog = BY_KEY.get((program, int(version)))
    if prog is None:
        return {"written": written, "waiting": waiting}
    band = BA.bands(store).get((program, int(version)), "learning")
    if band != "learning":
        return {"written": written, "waiting": waiting}
    runs = runs6(store, program, version)
    run = runs[-1]
    if run["ended"] is not None:
        waiting.append({"program": program, "version": version, "k": None,
                        "why": f"run {run['n']} ended ({run['ended']['why']}): run {run['n'] + 1} waits for the budget"})
        return {"written": written, "waiting": waiting}
    rows = settled_rows6(store, program, version)
    record = run_record6(rows, run)
    if not record:
        return {"written": written, "waiting": waiting}
    control = control_of(program)
    ctl_rows = control_rows6(store, control, prog.registered_at) if control else None
    pending = _pending(store, program, version) + (_pending(store, control, 1) if control else [])
    on = written6(store, program, version, "run", run["n"])
    tag = v6_tag("run", run["n"])
    plan = schedule6(store, record, today, pending=pending, consumed=on["consumed"], after=on["last"],
                     final=final_until(store, program, version, today, now))
    if on["S"] >= V6_RUN_BLOCKS and plan["horizon"] is None:
        last = blocks6(covered(record, on["last"]))[V6_RUN_BLOCKS - 1].day if on["last"] else None
        plan["horizon"] = (on["last"], last) if last is not None else None
    if plan["stopped"] is not None:
        waiting.append({"program": program, "version": version, "k": None, "why": plan["why"]})
    ended = False
    for k, as_of, merged, S_ in plan["looks"]:
        missing = uncopied(store, prog, as_of)
        if missing:
            waiting.append({"program": program, "version": version, "k": k,
                            "why": f"{len(missing)} superseded intents through {as_of.isoformat()} are not copied yet"})
            plan["horizon"] = None
            break
        session = C.session(store, as_of)
        cov = covered(record, as_of)
        blk = blocks6(cov)[:V6_RUN_BLOCKS]
        first_entry = min(_day(r["entry_day"]) for r in record)
        days = len(C.sessions(store, first_entry, as_of))
        ctl = covered(ctl_rows, as_of) if ctl_rows is not None else None
        judged = v6_judge(blk, program=program, version=version, tag=tag, control_rows=ctl, control=control,
                          draws=draws)
        look = _look6_row(program, version, "run", run["n"], k, merged, session.close_at, days, judged)
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            moved[0] = BA.on_look(store, look, now=now, db=db)   # (in the look's own transaction)
        if write_look(store, look, apply=apply, now=now):
            written.append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")}
                           | {"band": moved[0], "merged": merged, "tag": tag, "S": S_})
        if judged.get("decision") in ("pass", "retire"):
            ended = True
            break
    if not ended and plan["horizon"] is not None:
        at, last_day = plan["horizon"]
        if not uncopied(store, prog, at):
            session = C.session(store, at)
            key = V6_END_KEY.format(program=program, version=int(version), n=run["n"])
            with store.tx() as db:
                cur = db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                                 (key, json.dumps({"at": S.iso(session.close_at), "last_day": last_day.isoformat(),
                                                   "n": run["n"], "written_at": S.iso(now)}, sort_keys=True)))
            if cur.rowcount == 1:
                written.append({"program": program, "version": version, "k": None, "held": 0, "passed": 0, "p": None,
                                "alpha": None, "why": f"run {run['n']} ended at its {V6_RUN_BLOCKS}th block (D2): the "
                                                      "version stays in learning; its next run waits for the budget",
                                "tag": tag, "end": at.isoformat()})
    return {"written": written, "waiting": waiting}


__all__ = ["ALPHA", "V2_ALPHA", "V2_NS", "V2_MIN_ISSUERS", "V2_MIN_BLOCKS", "v2_schedule", "next_look_v2", "written_v2",
           "final_until", "FINAL_SESSIONS", "FINAL_LOOKBACK", "FINAL_BACKFILL_WEEKDAYS", "SEC_HOLIDAYS", "index_through",
           "FAST_RECORD_GAP", "NAMED_FROM", "FOUR_KIND", "FIVE_KIND", "FILE_KINDS", "file_programs", "BIRTHS_KIND",
           "program_key", "names", "four_programs", "made_without", "births_made_without",
           "birth_group", "B", "TIE", "LOOKS", "SEATABLE",
           "RECORDS", "CONTROLS", "HOLDS", "Block", "blocks", "issuer_values",
           "look_schedule", "look_number", "minimums", "seed_string", "seed_of", "look_seed", "values_sha", "signflip_p",
           "skew_check", "look_figures", "control_mean", "judge_look", "write_look", "look_detail", "bootstrap_bounds",
           "bounds_seed", "done_bounds", "kill_bounds", "sized_bound", "calibration", "program_versions",
           "exit_overrides", "settled_rows", "first_settled_exit", "covered", "skew_records", "look_rows", "next_look",
           "run", "expected_false_passes", "LANE_BUDGET", "control_of"]
#: (PREREG-EVL-6: one money-weighted session-block screen for every seat)
__all__ += ["V6_LOOKS", "V6_ALPHAS", "V6_MARGIN", "V6_CAP", "V6_MIN_EVENTS", "V6_MIN_ISSUERS", "V6_MIN_BLOCKS",
            "V6_ISSUER_P", "V6_EXACT", "V6_RUN_BLOCKS", "V6_CHARGE", "V6_BUDGET", "V6_CHARGE_HUNDREDTHS",
            "V6_BUDGET_HUNDREDTHS", "V6_BASE_RATE", "V6_STRESS_RATE", "V6_PER_VERSION", "V6_STAY_BASE", "V6_RUN_KEY",
            "V6_END_KEY", "v6_alpha", "v6_tag", "v6_seed_string", "look_key6", "key_of6", "v6_count_p", "Block6",
            "rank_order", "blocks6", "v6_values", "v6_lower", "v6_minimums", "v6_judge", "settled_rows6",
            "control_rows6", "stays6", "runs6", "run_record6", "written6", "schedule6", "last_close", "waiting_runs",
            "budget6", "start_runs", "next_look6", "FlipSource"]
