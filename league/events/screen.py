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
#: PREREG-EVL-3 section 3: version 2's looks are counted in settled TRADABLE events, each with >= 40 issuers and
#: >= 8 session blocks; the skew check starts (and caps, the stricter reading of the frozen text: A65) at 0.018.
V2_NS: tuple[int, ...] = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
V2_MIN_ISSUERS = 40
V2_MIN_BLOCKS = 8
V2_ALPHA = 0.018

SEATABLE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1",
            # PREREG-EVL-2 (registered 2026-10-19T03:04:07Z), judged by this screen unchanged
            "EVL-ERN-REACT-ON", "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON")
RECORDS = ("EVL-ERN-READ-O3", "EVL-INS-CLUSTER-O5", "EVL-CTRL-ERN-ALL-O1", "EVL-CTRL-8K-ALL-O1", "EVL-CTRL-NEWS-ALL-O1",
           "EVL-INS-BUY-O5", "EVL-ERN-REACT-READ-C1", "EVL-ERN-READ3-O1", "EVL-CTRL-NEWS-DAY-ON")
#: A READ program's control (its mean block value must exceed the control's over the same sessions).
CONTROLS: dict[str, str] = {"EVL-ERN-READ-O1": "EVL-CTRL-ERN-ALL-O1", "EVL-8K-READ-O1": "EVL-CTRL-8K-ALL-O1",
                            "EVL-NEWS-READ-O1": "EVL-CTRL-NEWS-ALL-O1",
                            "EVL-ERN-GUIDE-O1": "EVL-CTRL-ERN-ALL-O1", "EVL-NEWS-READ-ON": "EVL-CTRL-NEWS-DAY-ON"}
#: Sessions held as the prereg counts them (C1, close to next close, holds one; PREREG-EVL-2's close-to-next-open
#: programs hold one). The screen judges only the seatable programs, every one a one-session hold, so each of their
#: blocks is one entry session.
HOLDS: dict[str, int] = {"EVL-ERN-READ-O1": 1, "EVL-ERN-REACT-C1": 1, "EVL-8K-READ-O1": 1, "EVL-NEWS-READ-O1": 1,
                         "EVL-ERN-READ-O3": 3, "EVL-INS-CLUSTER-O5": 5, "EVL-CTRL-ERN-ALL-O1": 1, "EVL-CTRL-8K-ALL-O1": 1,
                         "EVL-CTRL-NEWS-ALL-O1": 1,
                         "EVL-ERN-REACT-ON": 1, "EVL-ERN-GUIDE-O1": 1, "EVL-INS-BUY-O1": 1, "EVL-NEWS-READ-ON": 1,
                         "EVL-NEWS-REACT-ON": 1, "EVL-INS-BUY-O5": 5, "EVL-ERN-REACT-READ-C1": 1, "EVL-ERN-READ3-O1": 1,
                         "EVL-CTRL-NEWS-DAY-ON": 1}


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
    control = CONTROLS.get(program)
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


def write_look(store: S.Store, look: Mapping[str, Any]) -> bool:
    """Write one look (one row per (program, version, k), never rewritten): False when it exists. The issuer-block
    test, the control comparison, the skew checks and the figures beside go to meta `look:<program>:<version>:<k>`."""
    with store.tx() as db:
        cur = db.execute(f"INSERT OR IGNORE INTO looks({', '.join(LOOK_COLUMNS)}) VALUES({', '.join('?' * len(LOOK_COLUMNS))})",
                         tuple(look[c] for c in LOOK_COLUMNS))
        if cur.rowcount != 1:
            return False
        detail = {c: look[c] for c in LOOK_COLUMNS} | {x: look.get(x) for x in ("issuer", "control", "skew", "beside",
                                                                              "retirement")}
        db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                   (f"look:{look['program']}:{look['version']}:{look['k']}", json.dumps(detail, sort_keys=True, default=str)))
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


def run(store: S.Store, today: dt.date, *, programs: Sequence[tuple[str, int]] | None = None,
        now: dt.datetime | None = None, draws: int = B) -> dict[str, Any]:
    """The screen job: every seatable program's looks whose as-of session is on or before `today` and not yet written,
    each read from the record as of its session, once every intent (the control's too) scheduled to exit by then has
    settled. At a held look the skew checks go to meta `skew:<program>:<version>:<k>` before p is computed. Returns
    {written, waiting}."""
    now = now or S.utc_now()
    written, waiting = [], []
    for program, version in programs or program_versions(store):
        if program not in SEATABLE:
            continue
        if _seating(program, version):
            out = _run_v2(store, program, version, today, now=now, draws=draws)
            written += out["written"]
            waiting += out["waiting"]
            continue
        if version != 1:
            continue
        rows = settled_rows(store, program, version)
        anchor = min((r["exited"] for r in rows), default=None)
        if anchor is None:
            continue
        done = {r["k"] for r in look_rows(store, program, version)}
        pending = _pending(store, program, version)
        control = CONTROLS.get(program)
        ctl_pending = _pending(store, control, version) if control else []
        for k, s_k in LOOKS:
            session = C.nth(store, anchor, s_k)
            if session is None or session.day > today:
                break
            if k in done:
                continue
            as_of = session.day
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
            if write_look(store, look):
                written.append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")})
    return {"written": written, "waiting": waiting}


def expected_false_passes(store: S.Store) -> dict[str, Any]:
    """0.10 x every version that can seat (PREREG-EVL-3 section 4: the nine version 2 programs; version 1 never seats),
    plus any later version of a seatable program seen in the store."""
    from .programs import SEATING

    versions = {(p.id, p.version) for p in SEATING} | {(p, v) for p, v in program_versions(store)
                                                       if p in SEATABLE and v > 2}
    return {"versions": len(versions), "expected": round(FALSE_PASS_RATE * len(versions), 3)}


# ------------------------------------------------------------------------------------------- version 2: PREREG-EVL-3
def _seating(program: str, version: int) -> bool:
    from .programs import BY_KEY

    p = BY_KEY.get((program, int(version)))
    return bool(p is not None and p.can_seat)


def v2_schedule(store: S.Store, rows: Sequence[Mapping[str, Any]], today: dt.date,
                pending: Sequence[tuple[dt.date, dt.date]] = ()) -> dict[str, Any]:
    """PREREG-EVL-3's looks of one program from its settled rows: [(k, as_of day, merged ks)] in order, and where the
    scan stopped. Look k is at the first session close with >= V2_NS[k-1] settled TRADABLE events, >= 40 issuers among
    them and >= 8 session blocks (covered: scheduled exits at or before that close); thresholds first reached at the
    same close are one look (the lowest k; the others merged into it). The scan stops at the first close by which an
    intent scheduled to exit has not settled (`pending`), so no look reads an incomplete record."""
    if not rows:
        return {"looks": [], "stopped": None}
    first_entry = min(_day(r["entry_day"]) for r in rows)
    looks: list[tuple[int, dt.date, list[int]]] = []
    j = 0
    stopped = None
    for s in C.sessions(store, first_entry, today):
        if any(x <= s.day for _, x in pending):
            stopped = s.day
            break
        if j >= len(V2_NS):
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
        reached = [i for i in range(j, len(V2_NS)) if n >= V2_NS[i]]
        looks.append((reached[0] + 1, s.day, [i + 1 for i in reached[1:]]))
        j = reached[-1] + 1
    return {"looks": looks, "stopped": stopped}


def _run_v2(store: S.Store, program: str, version: int, today: dt.date, *, now: dt.datetime,
            draws: int = B) -> dict[str, Any]:
    from . import bands as BA

    written, waiting = [], []
    rows = settled_rows(store, program, version)
    if not rows:
        return {"written": written, "waiting": waiting}
    done = {r["k"] for r in look_rows(store, program, version)}
    control = CONTROLS.get(program)
    pending = _pending(store, program, version) + (_pending(store, control, 1) if control else [])
    plan = v2_schedule(store, rows, today, pending)
    if plan["stopped"] is not None:
        waiting.append({"program": program, "version": version, "k": None,
                        "why": f"an intent scheduled to exit by {plan['stopped']} has not settled"})
    for k, as_of, merged in plan["looks"]:
        if k in done:
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
        if write_look(store, look):
            moved = BA.on_look(store, look, now=now)
            written.append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")}
                           | {"band": moved, "merged": merged})
    return {"written": written, "waiting": waiting}


def next_look_v2(store: S.Store, program: str, version: int, today: dt.date) -> dict[str, Any]:
    """Version 2's next unwritten look: {k, events_needed, events, issuers, blocks, status}."""
    done = {r["k"] for r in look_rows(store, program, version)}
    rows = settled_rows(store, program, version)
    trad = [r for r in rows if _tradable(r)]
    nxt = next((i + 1 for i in range(len(V2_NS)) if i + 1 not in done and not any(
        k in done for k in range(i + 2, len(V2_NS) + 1))), None)
    if nxt is None:
        return {"k": None, "status": "all looks written"}
    return {"k": nxt, "events_needed": V2_NS[nxt - 1], "events": len(trad),
            "issuers": len({str(r["issuer"]) for r in trad}), "blocks": len({_day(r["entry_day"]) for r in trad}),
            "status": "upcoming"}


__all__ = ["ALPHA", "V2_ALPHA", "V2_NS", "V2_MIN_ISSUERS", "V2_MIN_BLOCKS", "v2_schedule", "next_look_v2", "B", "TIE", "LOOKS", "SEATABLE", "RECORDS", "CONTROLS", "HOLDS", "Block", "blocks", "issuer_values",
           "look_schedule", "look_number", "minimums", "seed_string", "seed_of", "look_seed", "values_sha", "signflip_p",
           "skew_check", "look_figures", "control_mean", "judge_look", "write_look", "look_detail", "bootstrap_bounds",
           "bounds_seed", "done_bounds", "kill_bounds", "sized_bound", "calibration", "program_versions",
           "exit_overrides", "settled_rows", "first_settled_exit", "covered", "skew_records", "look_rows", "next_look",
           "run", "expected_false_passes"]
