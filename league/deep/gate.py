"""THE DEEP GATE: its capability, one look per version, the look ledger, the look budget, the canaries, and the look.

Owner: R1. Report-only in R1 (`config.cfg` mode "report"): every eligible version gets its ONE S3 look in idle hours,
its verdict is sealed in the ledger, and nothing of it reaches births, the swarm or a public surface (the captain
reads counts: league/deep/report.py). THAT FIRST LOOK IS THE VERSION'S LOOK: it is not repeated when gating starts.

THE CAPABILITY (`DeepGateCapability`, `mint_deep_gate_capability`): an object, not a flag, as the equity store's
(league/equity/store.py `EquityGateCapability`). It cannot be constructed; it is minted on a deep store whose
`sealed/` carries the `DEEP_GATE` mark, for one of `REASONS`, and only `blocks.DeepStore` reads it.

THE LEDGER (`Ledger`, `<state>/equity-deep/ledger.json`, 0600): one row a look ({key, fid, n, cell, kind ("look" |
"canary"), at, attempts, verdict ({"passed", "deep", "recent"}, "failed" or None while under way), identity, engine,
receipt}) and the versions refused before a look ({key: {why, identity, at}}). Verdicts are booleans (and None for a
recent key that is pending): no figure is kept. A version (`version_key`: its code and PARAMS) is looked at once
(`config.LOOKS_PER_VERSION`); at most three real looks a mechanism cell (`config.LOOKS_PER_CELL`; the cell is the
swarm's (lane, agenda, universe group), handed in); at most 150 looks in all before an erosion review
(`config.LOOK_BUDGET`, canaries counted). A look the House could not finish (an exception after the look was begun) is
owed again once; the second time it is spent and failed (`config.LOOK_ATTEMPTS`): no program can stop a look until
DVAL suits it. A run the program's own errors ended is spent and failed at once.

THE RECENT KEY WAITS ON D2. The receipt calibrates the recent key on R + V + H, the reserve in it, and PREREG-H reads
the reserve only inside S3 when the owner's D2 is "judged". Until then a look reads the DEEP key (the sealed look,
once) and its recent key is PENDING: no R, V or H run is made, `passed` is None. `recent_look` reads a pending recent
key once D2 is "judged" (open and gated recent windows only: DVAL is never read again).

THE CANARIES (the receipt's `canary`). In each block of ten consecutive looks exactly one is a random-timing canary, at
the block position default_rng([20261017, 3, 8, block]).integers(10) (`canary_slot`; a slot before the block's first
real look moves to the next one). It mirrors the real version looked at just before it (`canary_for`): its DVAL
universe and history, and per symbol its Train-era round trips a year, mean holding period and mean weight; per symbol
an on/off Markov chain (P(on -> off) = 1 / mean hold, P(off -> on) set so the invested share matches), drawn from
default_rng([20261017, 3, 9, look index]) and written into the program as a schedule (`canary_code`): it reads no
price and no date. It is judged exactly as a version on the deep key alone, counts as a look, is never seated and
never shown to births. When the canaries' deep-key passes exceed the upper end of the central 95% binomial band at 15%
(`band_upper`), S3 HALTS: no further look until the captain clears it (`Ledger.halted`).

THE LOOK (`look`), in order, nothing sealed opened before step 4:
1. the ledger's walls (halted, already looked, the budget, the cell);
2. eligibility, no look spent (league/deep/screen3.py `rules`): ETF only, the calendar-blind scan and behavioural
   test (league/deep/blind.py), turnover and the close-to-next-open share on the Train-era runs, the scored layout
   (>= 750 DVAL sessions), the route's recall (unmeasured: the look WAITS);
3. the own deep floor from the Train-era runs and the relabeled TRAIN-D run (open data only), and the bar c_D (no
   floor: INELIGIBLE, no look spent);
4. the look is begun (the ledger row written first), the deep gate's capability minted, each scored DVAL segment
   written into a temporary store and run at k 2.0 (removed after, `relabel.relabeled`), x2 full and masked and the
   k 3.0 sum, the deep key;
5. the recent key (a real look, D2 "judged" only): its own floor, c_R, and the caller's R + V + H series
   (`Runs.recent`);
6. the verdict, written to the ledger. What `look` returns is the status and booleans.

`Runs` is the caller's: league/ops/deep_report.py builds one over the decider-isolated child; tests over the
in-process decider.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

from ..equity.program import CodeRefused
from . import DEEP_ENGINE_VERSION, blind, blocks, calendar, config, relabel, screen3
from . import stat as S

REASONS = ("s3-look", "contamination-probe")
LEDGER_VERSION = "deep-ledger-1"


class DeepGateCapability:
    """Proof that the caller is the deep gate. It cannot be constructed; `mint_deep_gate_capability` mints one."""

    __slots__ = ("reason", "store_root")

    def __init__(self, *args: Any, **kwargs: Any):
        raise TypeError("a DeepGateCapability is minted by mint_deep_gate_capability(), never constructed")

    def __repr__(self) -> str:
        return f"<DeepGateCapability {self.reason!r}>"


def mint_deep_gate_capability(root: str | Path, reason: str) -> DeepGateCapability:
    """The deep gate's capability for the deep store at `root` (its `sealed/` must carry the `DEEP_GATE` mark),
    for one of `REASONS`. `blocks.DeepRefused` otherwise."""
    root = Path(root)
    if not (root / config.SEALED_DIR / config.GATE_MARK).is_file():
        raise blocks.DeepRefused(f"{root} is not the House's deep store (no {config.GATE_MARK} mark)")
    if reason not in REASONS:
        raise blocks.DeepRefused(f"the deep gate opens the sealed era for {', '.join(REASONS)}, not {reason!r}")
    cap = object.__new__(DeepGateCapability)
    object.__setattr__(cap, "reason", reason)
    object.__setattr__(cap, "store_root", str(root.resolve()))
    return cap


def version_key(code: str, params: Mapping[str, Any] | None) -> str:
    """A version's identity for the ledger: the sha256 of its code and its PARAMS (24 hex)."""
    body = str(code).encode() + b"\0" + json.dumps(dict(params or {}), sort_keys=True, default=str).encode()
    return hashlib.sha256(body).hexdigest()[:24]


# ----------------------------------------------------------------------------------------------------------- the band
def band_upper(n: int, p: float = config.CANARY_RATE, band: float = config.CANARY_BAND) -> int:
    """The upper end of the central `band` binomial interval of n trials at p: the smallest u with P(X <= u) >= 1 -
    (1 - band) / 2."""
    n = int(n)
    target = 1.0 - (1.0 - band) / 2.0
    total = 0.0
    for u in range(n + 1):
        total += math.comb(n, u) * p ** u * (1.0 - p) ** (n - u)
        if total >= target - 1e-12:
            return u
    return n


def canary_slot(block: int) -> int:
    """The canary's position in look block `block` (the receipt's schedule)."""
    return int(np.random.default_rng([*config.CANARY_SLOT_SEED, int(block)]).integers(config.CANARY_EVERY))


# ---------------------------------------------------------------------------------------------------------- the ledger
class Ledger:
    """The look ledger at `<root>/ledger.json` (the module docstring). `save` writes it atomically (0600)."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / config.LEDGER
        try:
            doc = json.loads(self.path.read_text())
        except (OSError, ValueError):
            doc = {}
        if not isinstance(doc, dict) or doc.get("version") != LEDGER_VERSION:
            doc = {}
        self.looks: list[dict[str, Any]] = [dict(r) for r in doc.get("looks") or [] if isinstance(r, dict)]
        self.refused: dict[str, dict[str, Any]] = {str(k): dict(v) for k, v in (doc.get("refused") or {}).items()
                                                   if isinstance(v, dict)}
        self.cleared: list[str] = [str(x) for x in doc.get("cleared") or []]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"version": LEDGER_VERSION, "looks": self.looks, "refused": self.refused,
                           "cleared": self.cleared}, sort_keys=True, indent=1).encode()
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def row(self, key: str) -> dict[str, Any] | None:
        return next((r for r in self.looks if r.get("key") == key), None)

    def spent(self) -> list[dict[str, Any]]:
        """The looks spent: begun (a look under way is spent), canaries included."""
        return list(self.looks)

    def real(self) -> list[dict[str, Any]]:
        return [r for r in self.looks if r.get("kind") == "look"]

    def canaries(self) -> list[dict[str, Any]]:
        return [r for r in self.looks if r.get("kind") == "canary" and isinstance(r.get("verdict"), dict)]

    def pending(self) -> list[dict[str, Any]]:
        """Real looks whose recent key waits on D2."""
        return [r for r in self.real() if isinstance(r.get("verdict"), dict) and r["verdict"].get("recent") is None]

    def cell_count(self, cell: str) -> int:
        return sum(1 for r in self.real() if r.get("cell") == cell)

    def canary_due(self) -> bool:
        """The next look slot is its block's canary's (`canary_slot`), or past it with none in the block yet; never
        before a real look exists to mirror."""
        index = len(self.looks)
        block, at = divmod(index, config.CANARY_EVERY)
        mine = self.looks[block * config.CANARY_EVERY:]
        if any(r.get("kind") == "canary" for r in mine) or not any(r.get("kind") == "look" for r in self.looks):
            return False
        return at >= canary_slot(block)

    def halted(self) -> bool:
        """The canary halt: the canaries' deep-key passes above `band_upper` of their count (cleared by the captain
        for the canaries counted at the clearing, `cleared`)."""
        rows = [r for r in self.canaries() if r.get("key") not in self.cleared]
        passes = sum(1 for r in rows if r["verdict"].get("deep"))
        return bool(rows) and passes > band_upper(len(rows))

    def begin(self, row: Mapping[str, Any]) -> dict[str, Any]:
        found = self.row(str(row["key"]))
        if found is None:
            found = {**row, "attempts": 0, "verdict": None}
            self.looks.append(found)
        found["attempts"] = int(found.get("attempts") or 0) + 1
        self.save()
        return found

    def finish(self, key: str, verdict: Any) -> None:
        found = self.row(key)
        if found is None:
            raise KeyError(f"no look {key} under way")
        found["verdict"] = verdict
        self.save()

    def refuse(self, key: str, why: str, *, identity: str, at: str) -> None:
        self.refused[key] = {"why": str(why)[:200], "identity": identity, "at": at}
        self.save()


# ------------------------------------------------------------------------------------------------------- the canaries
CANARY = '''NEEDS = {{"symbols": {symbols}, "history": {history}, "max_hold_sessions": 60}}
PARAMS = {{}}
STATE = {{"n": 0}}
#: per symbol and decision: "." off, "o" on (an entry here goes at the open), "c" on (an entry here goes at the close)
PLAN = {plan}
SHARE = {share}


def decide(ctx):
    n = STATE["n"]
    STATE["n"] = n + 1
    held = {{}}
    for p in ctx.positions:
        held.setdefault(p["symbol"], []).append(p["id"])
    out = []
    for s in ctx.symbols:
        mark = PLAN[s][n] if n < len(PLAN[s]) else "."
        if mark == "." and s in held:
            for lid in held[s]:
                out.append({{"sell": lid, "at": "open", "tag": "canary"}})
        elif mark != "." and s not in held:
            out.append({{"buy": s, "share": SHARE[s], "at": "close" if mark == "c" else "open", "tag": "canary"}})
    return out
'''


def canary_plan(per_symbol: Mapping[str, Mapping[str, float]], seed: int,
                steps: int = config.CANARY_STEPS) -> dict[str, str]:
    """THE CANARY'S TIMING (the receipt's construction): per symbol (in the given order) an on/off Markov chain over
    `steps` decisions from default_rng([20261017, 3, 9, seed]): P(on -> off) = 1 / hold, P(off -> on) so that the
    invested share is round_trips x hold / 252 (at most 0.9); an entry goes at the close with the symbol's share of
    close entries. `per_symbol[sym]`: {"round_trips", "hold", "close"}."""
    rng = np.random.default_rng([*config.CANARY_SEED, int(seed)])
    out = {}
    for sym, row in per_symbol.items():
        hold = max(1.0, float(row.get("hold") or 1.0))
        share = min(0.9, max(0.0, float(row.get("round_trips") or 0.0) * hold / 252.0))
        p_off = 1.0 / hold
        p_on = share * p_off / (1.0 - share) if share > 0 else 0.0
        draws = rng.random((int(steps), 2))
        marks, on, kind = [], False, "o"
        for t in range(int(steps)):
            if on and draws[t, 0] < p_off:
                on = False
            elif not on and draws[t, 0] < p_on:
                on, kind = True, ("c" if draws[t, 1] < float(row.get("close") or 0.0) else "o")
            marks.append(kind if on else ".")
        out[sym] = "".join(marks)
    return out


def canary_code(*, symbols: Sequence[str], history: int, per_symbol: Mapping[str, Mapping[str, float]],
                seed: int) -> str:
    """A random-timing canary matched to a version (`canary_plan`), its weights the version's mean weight per held
    symbol (`per_symbol[sym]["share"]`, 0.01..0.5). It reads no price and no date."""
    names = [str(s) for s in symbols]
    rows = {s: dict(per_symbol.get(s) or {}) for s in names}
    plan = canary_plan(rows, seed)
    # three decimals: no four-digit run in the program's text can read as a year (league/gym/safety.py)
    share = {s: round(min(max(float(rows[s].get("share") or 0.1), 0.01), 0.5), 3) for s in names}
    return CANARY.format(symbols=json.dumps(names), history=int(history), plan=json.dumps(plan),
                         share=json.dumps(share))


# ------------------------------------------------------------------------------------------------------------ the look
@dataclass(frozen=True)
class Version:
    """What the look is told of a version: its swarm ids (`fid`, `n`), `code`, `params`, its mechanism `cell` and
    whether its route is a strong recall of 2001-08 (`strong_recall`: None when unmeasured)."""

    fid: str
    n: int
    code: str
    params: Mapping[str, Any]
    cell: str
    strong_recall: bool | None

    @property
    def key(self) -> str:
        return version_key(self.code, self.params)

    @property
    def tag(self) -> int:
        """int(version sha256[:8], 16), the version's sha256 the swarm's (its program text's: league/swarm/store.py
        `code_sha`): the version's own floors' seed (the receipt's `floor.seeds`)."""
        return int(hashlib.sha256(str(self.code).encode("utf-8")).hexdigest()[:8], 16)


class Runs(Protocol):
    """The caller's runs (the module docstring). `needs` -> {"symbols", "history", "max_hold_sessions"}; `segments` ->
    the Train-era `runner.Run`s (2016-19, 2022-24); `on_store(root, code, params, start, end, k)` -> one `runner.Run`
    on a store root; `recent(code, params)` -> the R, V and H windows' daily r arrays at k 1.0 (H last), or None when
    the program's own errors ended one of those runs ("disqualified": the recent key fails); a run the House could not
    make raises (the look is owed again once)."""

    def needs(self, code: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def segments(self, code: str, params: Mapping[str, Any]) -> Sequence[Any]: ...

    def on_store(self, root: Path, code: str, params: Mapping[str, Any], start: dt.date, end: dt.date,
                 k: float) -> Any: ...

    def recent(self, code: str, params: Mapping[str, Any]) -> Sequence[np.ndarray] | None: ...


def _capital(result: Mapping[str, Any]) -> float:
    try:
        value = float(str(result.get("capital")))
    except (TypeError, ValueError):
        value = 1000.0
    return value if math.isfinite(value) and value > 0 else 1000.0


def _part(run: Any, symbols: Sequence[str], keep: np.ndarray | None = None) -> S.Part:
    bars = run.bars
    return S.Part(lots=list(run.result.get("lots") or []), bars=bars, symbols=tuple(symbols),
                  capital=_capital(run.result), first=int(bars.first), last=int(bars.n) - 1, keep=keep)


def _usable(run: Any) -> bool:
    return isinstance(run.result, Mapping) and run.result.get("status") == "ok"


def _first_days(store: blocks.DeepStore, symbols: Sequence[str]) -> dict[str, dt.date | None]:
    out: dict[str, dt.date | None] = {}
    for sym in symbols:
        days = [store.first_day(span, sym) for span in ("history", "dval")]
        known = [d for d in days if d is not None]
        out[sym] = min(known) if known else None
    return out


def _late_clean(store: blocks.DeepStore) -> dict[str, bool]:
    audit = store.audit()
    stale = (audit.get("stale") or {}) if isinstance(audit, dict) else {}
    return {sym: bool(isinstance(row, dict) and row.get("clean")) for sym, row in stale.items()}


@dataclass
class _Prepared:
    needs: Mapping[str, Any]
    symbols: tuple[str, ...]
    history: int
    layout: Mapping[str, Any]
    c_D: float
    segments: Sequence[Any]
    pool: Sequence[Mapping[str, np.ndarray]]


def _pool(store: blocks.DeepStore, code: str, params: Mapping[str, Any], runs: Runs, segments: Sequence[Any],
          symbols: Sequence[str], parent: Path | None) -> list[dict[str, np.ndarray]] | None:
    """The own floors' pool (open data only): the Train-era runs and the relabeled TRAIN-D run at k 2.0, each from its
    first decision + 2 sessions (`stat.piece`). None when the TRAIN-D run did not finish."""
    with relabel.relabeled(store, "traind", symbols, parent=parent) as rl:
        traind = runs.on_store(rl.root, code, params, rl.scored_pseudo[0], rl.pseudo_days[-1], config.K_JUDGED)
    if not _usable(traind):
        return None
    return [S.piece(_part(r, symbols), skip=config.POOL_SKIP) for r in [*segments, traind]]


def _prepare(store: blocks.DeepStore, code: str, params: Mapping[str, Any], runs: Runs, *, tag: int,
             strong_recall: bool | None, check_blind: bool, worlds: int,
             parent: Path | None) -> tuple[_Prepared | None, dict[str, Any] | None]:
    """Steps 2 and 3: (the prepared look, None) or (None, a refusal or a wait). Opens nothing sealed."""
    needs = runs.needs(code, params)
    symbols = tuple(str(s).upper() for s in needs.get("symbols") or ())
    history = int(needs.get("history") or 0)
    if not screen3.etf_only(symbols):
        return None, {"status": "refused", "why": "not ETF only (DVAL's 15)"}
    seen = {"blind": True}
    if check_blind:
        seen = blind.check(code, params, lambda root, start, end: runs.on_store(root, code, params, start, end,
                                                                               config.K_RECENT).result,
                           symbols=symbols, history=history, parent=parent)
        if not seen["blind"]:
            return None, {"status": "refused", "why": "not calendar-blind"}
    segments = list(runs.segments(code, params))
    if not segments or not all(_usable(r) for r in segments):
        return None, {"status": "refused", "why": "its Train-era runs did not finish"}
    lots = [lot for r in segments for lot in r.result.get("lots") or []]
    trips = screen3.round_trips_a_year([(r.result.get("lots") or [], int(r.bars.n) - int(r.bars.first))
                                        for r in segments])
    plan = screen3.rules(symbols=symbols, history=history, first_days=_first_days(store, symbols),
                         late_clean=_late_clean(store), round_trips=trips, overnight=screen3.overnight_share(lots),
                         strong_recall=strong_recall, blind=seen["blind"])
    if plan.get("wait"):
        return None, {"status": "waits", "why": plan["why"]}
    if not plan["eligible"]:
        return None, {"status": "refused", "why": plan["why"]}
    pool = _pool(store, code, params, runs, segments, symbols, parent)
    if pool is None:
        return None, {"status": "refused", "why": "its TRAIN-D run did not finish"}
    floor_d = screen3.deep_floor(pool, _layout_keep(plan["layout"]), version_tag=tag, worlds=worlds)
    c_D = screen3.bar(float(config.RECEIPT["c_D"]), floor_d)
    if c_D is None:
        return None, {"status": "refused", "why": "no deep floor (no pool, no exposure, or past 5.00)"}
    return _Prepared(needs=needs, symbols=symbols, history=history, layout=plan["layout"], c_D=c_D,
                     segments=segments, pool=pool), None


def _layout_keep(plan: Mapping[str, Any]) -> np.ndarray:
    """The unmasked flags of a scored layout's sessions, segment by segment."""
    masked = set(calendar.mask())
    out = []
    for name, seg in plan["segments"].items():
        if not seg:
            continue
        back, scored = calendar.segment(name)
        days = (back + scored)[seg["start"]:]
        out.extend(d not in masked for d in days)
    return np.array(out, dtype=bool)


def _deep(store_root: Path, code: str, params: Mapping[str, Any], runs: Runs, prepared: _Prepared, *,
          parent: Path | None) -> dict[str, Any]:
    """Step 4: the DVAL runs inside temporary stores and the deep key (booleans only)."""
    cap = mint_deep_gate_capability(store_root, "s3-look")
    sealed = blocks.DeepStore(store_root, gate=cap)
    masked = set(calendar.mask())
    parts = []
    for name, seg in prepared.layout["segments"].items():
        if not seg:
            continue
        with relabel.relabeled(sealed, name, prepared.symbols, parent=parent) as rl:
            start = seg["start"]
            run = runs.on_store(rl.root, code, params, rl.pseudo_days[start], rl.pseudo_days[-1], config.K_JUDGED)
            if isinstance(run.result, Mapping) and run.result.get("status") == "disqualified":
                # the program's own errors ended its sealed run: the look is spent and the key failed (a partial
                # series is never judged), as an equity holdout run that ends disqualified is (league/swarm/elane.py)
                return {"passed": False, "checks": {"full": False, "masked": False, "stress": False}}
            if not _usable(run):
                raise RuntimeError(f"the DVAL run of segment {name} did not finish ({run.result.get('status')})")
            keep = np.array([d not in masked for d in rl.true_days[start:]], dtype=bool)
            part = _part(run, prepared.symbols, keep)
            if part.n != len(keep):
                raise RuntimeError(f"segment {name}'s run covers {part.n} sessions, its layout {len(keep)}")
            parts.append(part)
    x_full = S.x2(parts, k=config.K_JUDGED)
    x_masked = S.x2(parts, k=config.K_JUDGED, masked=True)
    x3 = float(np.sum(S.x2(parts, k=config.K_STRESS)))
    return screen3.deep_key(x_full, x_masked, x3, prepared.c_D)


def _recent(version: Version, runs: Runs, pool: Sequence[Mapping[str, np.ndarray]], *,
            worlds: int) -> dict[str, Any]:
    """Step 5: the recent key on R + V + H at c_R = max(receipt, own floor + 0.05); a floor past the grid or a run the
    program ended fails it (the look is spent)."""
    floor_r = screen3.recent_floor(pool, version_tag=version.tag, worlds=worlds)
    c_R = screen3.bar(float(config.RECEIPT["c_R"]), floor_r)
    failed = {"passed": False, "checks": {"t": False, "sum_h": False}}
    if c_R is None:
        return failed
    arrays = runs.recent(version.code, dict(version.params))
    if arrays is None:  # the program's own errors ended a recent window's run
        return failed
    return screen3.recent_key(list(arrays), c_R)


def look(store_root: str | Path, version: Version, runs: Runs, *, ledger: Ledger, identity: str, now: str,
         reserve: bool = False, kind: str = "look", worlds: int = config.FLOOR_WORLDS,
         parent: str | Path | None = None) -> dict[str, Any]:
    """ONE S3 LOOK (the module docstring): {"status": "looked" | "refused" | "waits" | "halted" | "budget" | "cell" |
    "already" | "failed", "why"?, "passed"?, "deep"?, "recent"?}. `reserve`: the owner's D2 is "judged" (the recent
    key is read; else it is pending, `passed` None). `kind` "canary" judges the deep key alone and skips the blind
    test (the canary is ours). Raises after a look was begun and could not finish (owed once)."""
    store_root = Path(store_root)
    parent = None if parent is None else Path(parent)
    key = version.key
    if ledger.halted():
        return {"status": "halted", "why": "the canaries' deep-key passes are above their band: S3 halts"}
    found = ledger.row(key)
    if found is not None and found.get("verdict") is not None:
        return {"status": "already", "why": "one look a version"}
    if found is None and len(ledger.spent()) >= config.LOOK_BUDGET:
        return {"status": "budget", "why": "150 looks: an erosion review first"}
    if found is None and kind == "look" and ledger.cell_count(version.cell) >= config.LOOKS_PER_CELL:
        return {"status": "cell", "why": f"three looks in cell {version.cell}"}
    if found is not None and int(found.get("attempts") or 0) >= config.LOOK_ATTEMPTS:
        ledger.finish(key, "failed")
        return {"status": "failed", "why": "the look could not be finished twice: spent and failed"}
    store = blocks.DeepStore(store_root)
    try:
        prepared, stop = _prepare(store, version.code, dict(version.params), runs, tag=version.tag,
                                  strong_recall=version.strong_recall if kind == "look" else False,
                                  check_blind=kind == "look", worlds=worlds, parent=parent)
    except CodeRefused as exc:  # the program does not load (the child's reason): a refusal, no look spent
        prepared, stop = None, {"status": "refused", "why": f"the program does not load: {str(exc)[:120]}"}
    if stop is not None:
        if stop["status"] == "refused":
            ledger.refuse(key, stop["why"], identity=identity, at=now)
        return stop
    assert prepared is not None
    ledger.begin({"key": key, "fid": version.fid, "n": int(version.n), "cell": version.cell, "kind": kind, "at": now,
                  "identity": identity, "engine": DEEP_ENGINE_VERSION, "receipt": config.RECEIPT_SHA256[:12]})
    deep = _deep(store_root, version.code, dict(version.params), runs, prepared, parent=parent)
    if kind != "look":
        verdict = screen3.verdict(deep, None)
    elif reserve:
        verdict = screen3.verdict(deep, _recent(version, runs, prepared.pool, worlds=worlds))
    else:
        verdict = {"passed": None, "deep": bool(deep.get("passed")), "recent": None}
    ledger.finish(key, verdict)
    return {"status": "looked", **verdict}


def recent_look(store_root: str | Path, version: Version, runs: Runs, *, ledger: Ledger,
                worlds: int = config.FLOOR_WORLDS, parent: str | Path | None = None) -> dict[str, Any]:
    """A PENDING RECENT KEY read once the owner's D2 is "judged": {"status": "looked", "passed", "deep", "recent"} or
    {"status": "none"} when the version has no pending look. DVAL is not read again; the own floor's pool is rebuilt
    from the open Train-era and TRAIN-D runs."""
    row = ledger.row(version.key)
    verdict = row.get("verdict") if row else None
    if not (row and row.get("kind") == "look" and isinstance(verdict, dict) and verdict.get("recent") is None):
        return {"status": "none"}
    parent = None if parent is None else Path(parent)
    store = blocks.DeepStore(Path(store_root))
    needs = runs.needs(version.code, dict(version.params))
    symbols = tuple(str(s).upper() for s in needs.get("symbols") or ())
    segments = list(runs.segments(version.code, dict(version.params)))
    pool = _pool(store, version.code, dict(version.params), runs, segments, symbols, parent) \
        if segments and all(_usable(r) for r in segments) else None
    recent = _recent(version, runs, pool, worlds=worlds) if pool is not None else \
        {"passed": False, "checks": {"t": False, "sum_h": False}}
    done = screen3.verdict({"passed": verdict.get("deep")}, recent)
    ledger.finish(version.key, done)
    return {"status": "looked", **done}


def canary_for(ledger: Ledger, versions: Mapping[str, Version], runs: Runs) -> Version | None:
    """The canary of the real version looked at just before it (it must be among `versions`, by key), or None."""
    last = next((r for r in reversed(ledger.real()) if r.get("key") in versions), None)
    if last is None:
        return None
    source = versions[last["key"]]
    needs = runs.needs(source.code, dict(source.params))
    symbols = [str(s).upper() for s in needs.get("symbols") or ()]
    segments = [r for r in runs.segments(source.code, dict(source.params)) if _usable(r)]
    years = sum(int(r.bars.n) - int(r.bars.first) for r in segments) / 252.0
    per_symbol = {}
    for sym in symbols:
        lots = [lot for r in segments for lot in r.result.get("lots") or [] if lot.get("symbol") == sym]
        closed = [lot for lot in lots if lot.get("exit_day") not in (None, "")]
        per_symbol[sym] = {
            "round_trips": len(closed) / years if years > 0 else 0.0,
            "hold": float(np.mean([int(lot.get("held_sessions") or 1) for lot in lots])) if lots else 1.0,
            "share": float(np.mean([float(lot.get("weight") or 0.0) for lot in lots])) if lots else 0.1,
            "close": float(np.mean([lot.get("entry_at") == "close" for lot in lots])) if lots else 0.0,
        }
    code = canary_code(symbols=symbols, history=int(needs.get("history") or 0), per_symbol=per_symbol,
                       seed=len(ledger.looks))
    return Version(fid=source.fid, n=int(source.n), code=code, params={}, cell="canary", strong_recall=False)


__all__ = ["REASONS", "LEDGER_VERSION", "DeepGateCapability", "mint_deep_gate_capability", "version_key",
           "band_upper", "canary_slot", "Ledger", "CANARY", "canary_plan", "canary_code", "Version", "Runs", "look",
           "recent_look", "canary_for"]
