"""THE DEEP GATE: its capability, one look per version, the look ledger, the look budget, the canaries, and the look.

Owner: R1. Report-only in R1 (`config.cfg` mode "report"): every eligible version gets its ONE S3 look in idle hours,
its verdict is sealed in the ledger, and nothing of it reaches births, the swarm or a public surface (the captain
reads counts: league/deep/report.py). THAT FIRST LOOK IS THE VERSION'S LOOK: it is not repeated when gating starts.

THE CAPABILITY (`DeepGateCapability`, `mint_deep_gate_capability`): an object, not a flag, as the equity store's
(league/equity/store.py `EquityGateCapability`). It cannot be constructed; it is minted on a deep store whose
`sealed/` carries the `DEEP_GATE` mark, for one of `REASONS`, and only `blocks.DeepStore` reads it. Two callers mint
it, and a test holds the list (league/tests/test_deep_identity.py): this module's look and the contamination probe.

THE LEDGER (`Ledger`, `<state>/equity-deep/ledger.json`, 0600): one row a look ({key, fid, n, cell, kind ("look" |
"canary"), seated, source, level, at, attempts, verdict ({"passed", "deep", "recent"}, "failed" or None while under
way), identity, engine, receipt}), the versions refused before a look ({key: {why, identity, at}}) and the House's
errors by version ({key: {count, identity, stage, error, at}}). Verdicts are booleans: no figure is kept. A version
(`version_key`: its code and PARAMS) is looked at once (`config.LOOKS_PER_VERSION`); at most three real looks a
mechanism cell (`config.LOOKS_PER_CELL`; the cell is the swarm's (lane, agenda, universe group), handed in); at most
150 looks in all before an erosion review (`config.LOOK_BUDGET`, canaries counted).
THE LEDGER FAILS CLOSED: a file that is there but does not parse, or is of another version, is DAMAGED: every look is
refused (`look` "ledger") and nothing is written over it, until the captain restores it (`ledger.json.prev`, the file
as it stood before its last save, is kept beside it) or migrates it on purpose. A missing file is an empty ledger.

WHAT SPENDS A LOOK. A look is begun (its row written, `attempts` + 1) before anything sealed is opened, and is then
spent: its verdict is written, or it is "failed". Three things can end a begun look without a verdict:
- the program's own errors ended a sealed run ("disqualified"): spent and failed at once (a partial series is never
  judged);
- a sealed run was sent whole and not answered (league/equity/runner.py `RunLost`: the program held its bars and ran
  past its budget or exited), or the look's process was killed (nothing ran after): the attempt STANDS, so the look is
  owed once more and the second time it is spent and failed (`config.LOOK_ATTEMPTS`; league/swarm/elane.py
  `LOOK_SENDS`'s rule), and no program can stop answering until DVAL suits it;
- ANY OTHER ERROR IS THE HOUSE'S (a child that could not start, a store's slice, an answer that is not a result, a
  missing price): the attempt is WITHDRAWN (`Ledger.withdraw`), so no look is spent, and the error goes up to the job
  (league/ops/deep_report.py), which records it (`Ledger.house_error`), raises a House warning and goes on with the
  next version; at `config.HOUSE_ERRORS_MAX` errors under one deep identity the version is refused (no look spent)
  until a release moves the identity.

D2: THE RESERVE IS JUDGED, NEVER ALONE (the captain's A58, by the owner's delegation). The receipt calibrates the
recent key on R + V + H, the reserve in it, and PREREG-H reads the reserve only inside S3. So a real look reads BOTH
keys or NEITHER: with `elane.deep.reserve` "judged" (the default) each look reads the deep key and then the recent key;
with "sealed" (the switch back) no look is made at all (`look` "waits": no DVAL and no reserve run). HOW THE RESERVE
STAYS SEALED UNTIL THE LOOK: its bars are in the House's equity store (the Train window; the store asks no capability
for them: the swarm's own seal keeps every reserve session unrun, league/swarm/elane_seal.py), and here the only call
that runs one is `Runs.recent` (league/ops/deep_report.py `HouseRuns.recent`), made by `_recent_key` alone, which only
`look` calls, for a real look (never a canary), after every eligibility rule held and both own floors were computed
from open data only (the Train-era runs 2016-19 and 2022-24 and the relabeled TRAIN-D run: never a reserve session; R's
dates enter the recent floor's CRASH set as positions, never as bars), after the ledger row was written (the look is
spent) and after the deep key's DVAL runs. The R, V and H arrays live in memory inside that call; `screen3.recent_key`
returns booleans, and the ledger keeps booleans. Tests pin the order (league/tests/test_deep_gate.py
`TheReserveStaysSealed`).

THE CANARIES (the receipt's `canary`). In each block of ten consecutive looks exactly one is a random-timing canary, at
the block position default_rng([20261017, 3, 8, block]).integers(10) (`canary_slot`; a slot before the block's first
real look moves to the next one). It mirrors the real version looked at just before it (`canary_for`): its DVAL
universe and history, and per symbol its Train-era round trips a year, mean holding period and mean weight; per symbol
an on/off Markov chain (P(on -> off) = 1 / mean hold, P(off -> on) set so the invested share matches), drawn from
default_rng([20261017, 3, 9, look index]) and written into the program as a schedule (`canary_code`): it reads no
price and no date. It is judged exactly as a version on the deep key alone (its recent key is not read), counts as a
look, is never seated and never shown to births. When the canaries' deep-key passes exceed the upper end of the
central 95% binomial band at 15% (`band_upper`), S3 HALTS: no further look until the captain clears it
(`Ledger.halted`). Beside it, REPORT-ONLY, `Ledger.canary_alarm` reads the same band at the receipt's own synthetic
canary rate (`config.CANARY_REFERENCE`): the halt at 15% sees gross breakage only (`config.LIMITS`).

THE LOOK (`look`), in order, nothing sealed opened before step 5:
1. the ledger's walls (damaged, halted, D2 sealed, already looked, the budget, the cell, the attempts);
2. the version's NEEDS; ETF only; the route's recall (unmeasured: the look WAITS, before any run is made);
3. the calendar-blind scan and behavioural test (league/deep/blind.py; the level test beside it, report-only), the
   Train-era runs, turnover and the close-to-next-open share, the scored layout (>= 750 DVAL sessions, no segment
   with a data gap): eligibility, no look spent;
4. the own deep floor from the Train-era runs and the relabeled TRAIN-D run (open data only), c_D, and for a real look
   the own recent floor from the same pool, c_R (no floor: INELIGIBLE, no look spent);
5. the look is begun (the ledger row written first), the deep gate's capability minted, each scored DVAL segment
   written into a temporary store inside `sealed/.looks/` and run at k 2.0 (removed after, `relabel.relabeled`), x2
   full and masked and the k 3.0 sum, the deep key;
6. the recent key (a real look): the caller's R + V + H series (`Runs.recent`) at c_R;
7. the verdict, written to the ledger. What `look` returns is the status and booleans.

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
from ..equity.runner import RunLost
from . import DEEP_ENGINE_VERSION, blind, blocks, calendar, config, relabel, screen3
from . import stat as S

REASONS = ("s3-look", "contamination-probe")
LEDGER_VERSION = "deep-ledger-1"


class LedgerDamaged(RuntimeError):
    """The look ledger is there and cannot be read as this version's: nothing is written over it."""


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
    """The look ledger at `<root>/ledger.json` (the module docstring). `save` writes it atomically (0600), the file
    it replaces kept as `ledger.json.prev`. `damaged`: the file is there and not this version's (`problem` says why):
    every look is refused and `save` raises `LedgerDamaged`."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / config.LEDGER
        self.damaged = False
        self.problem: str | None = None
        doc: Any = {}
        if self.path.exists():
            try:
                doc = json.loads(self.path.read_text())
            except (OSError, ValueError) as exc:
                doc, self.damaged, self.problem = {}, True, f"it does not parse ({type(exc).__name__})"
            else:
                if not isinstance(doc, dict) or doc.get("version") != LEDGER_VERSION:
                    found = doc.get("version") if isinstance(doc, dict) else type(doc).__name__
                    doc, self.damaged = {}, True
                    self.problem = f"it is not a {LEDGER_VERSION} ledger ({str(found)[:40]})"
                elif not (isinstance(doc.get("looks") or [], list) and isinstance(doc.get("refused") or {}, dict)
                          and isinstance(doc.get("errors") or {}, dict) and isinstance(doc.get("cleared") or [], list)):
                    doc, self.damaged, self.problem = {}, True, "its looks, refusals or errors are malformed"
        self.looks: list[dict[str, Any]] = [dict(r) for r in doc.get("looks") or [] if isinstance(r, dict)]
        self.refused: dict[str, dict[str, Any]] = {str(k): dict(v) for k, v in (doc.get("refused") or {}).items()
                                                   if isinstance(v, dict)}
        self.errors: dict[str, dict[str, Any]] = {str(k): dict(v) for k, v in (doc.get("errors") or {}).items()
                                                  if isinstance(v, dict)}
        self.cleared: list[str] = [str(x) for x in doc.get("cleared") or []]

    def save(self) -> None:
        if self.damaged:
            raise LedgerDamaged(f"the look ledger is damaged ({self.problem}): nothing is written over it")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"version": LEDGER_VERSION, "looks": self.looks, "refused": self.refused,
                           "errors": self.errors, "cleared": self.cleared}, sort_keys=True, indent=1).encode()
        if self.path.exists():
            prev = self.path.with_name(config.LEDGER_PREV)
            old = self.path.read_bytes()
            fd = os.open(prev.with_name(f".{prev.name}.{os.getpid()}.tmp"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                         0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(old)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(prev.with_name(f".{prev.name}.{os.getpid()}.tmp"), prev)
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

    def _counted_canaries(self) -> list[dict[str, Any]]:
        return [r for r in self.canaries() if r.get("key") not in self.cleared]

    def halted(self) -> bool:
        """The canary halt: the canaries' deep-key passes above `band_upper` of their count (cleared by the captain
        for the canaries counted at the clearing, `cleared`)."""
        rows = self._counted_canaries()
        passes = sum(1 for r in rows if r["verdict"].get("deep"))
        return bool(rows) and passes > band_upper(len(rows))

    def canary_alarm(self) -> bool:
        """REPORT-ONLY (never a halt): the canaries' deep-key passes above the central 95% band at the receipt's own
        synthetic canary rate (`config.CANARY_REFERENCE`)."""
        rows = self._counted_canaries()
        passes = sum(1 for r in rows if r["verdict"].get("deep"))
        return bool(rows) and passes > band_upper(len(rows), config.CANARY_REFERENCE)

    def begin(self, row: Mapping[str, Any]) -> dict[str, Any]:
        found = self.row(str(row["key"]))
        if found is None:
            found = {**row, "attempts": 0, "verdict": None}
            self.looks.append(found)
        found["attempts"] = int(found.get("attempts") or 0) + 1
        self.save()
        return found

    def withdraw(self, key: str) -> None:
        """An attempt the House could not make: it is taken back (the look is not spent); a row with no attempt left
        is removed."""
        found = self.row(key)
        if found is None or found.get("verdict") is not None:
            return
        found["attempts"] = int(found.get("attempts") or 0) - 1
        if found["attempts"] <= 0:
            self.looks.remove(found)
        self.save()

    def finish(self, key: str, verdict: Any) -> None:
        found = self.row(key)
        if found is None:
            raise KeyError(f"no look {key} under way")
        found["verdict"] = verdict
        self.errors.pop(key, None)
        self.save()

    def refuse(self, key: str, why: str, *, identity: str, at: str) -> None:
        self.refused[key] = {"why": str(why)[:200], "identity": identity, "at": at}
        self.save()

    def house_error(self, key: str, *, identity: str, at: str, stage: str, error: str) -> int:
        """One more error of the House's for this version under `identity` (a count under another identity starts
        again): the count. Names only: the error's class, never its text."""
        held = self.errors.get(key) or {}
        count = (int(held.get("count") or 0) if held.get("identity") == identity else 0) + 1
        self.errors[key] = {"count": count, "identity": identity, "stage": str(stage)[:40], "error": str(error)[:60],
                            "at": at}
        self.save()
        return count


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
    """What the look is told of a version: its swarm ids (`fid`, `n`), `code`, `params`, its mechanism `cell`, whether
    its route is a strong recall of 2001-08 (`strong_recall`: None when unmeasured), whether its family names a route
    at all (`route_known`: a captain's seed needs none), whether it holds a seat (`seated`: its recent key re-reads
    the windows that seated it) and its `source` ("seed" for a captain's seed and its lineage, "born" otherwise): the
    report counts seated versions and the sources apart."""

    fid: str
    n: int
    code: str
    params: Mapping[str, Any]
    cell: str
    strong_recall: bool | None
    route_known: bool = True
    seated: bool = False
    source: str = "born"

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
    the program's own errors ended one of those runs ("disqualified": the recent key fails). A run sent whole and not
    answered raises `RunLost`; any other run the House could not make raises another error (the module docstring)."""

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


def _gaps(store: blocks.DeepStore) -> dict[str, dict[str, int]]:
    """{SYMBOL: {span: sessions missing after its first bar}} from the data audit (league/ops/equity_deep.py)."""
    audit = store.audit()
    by_span = (audit.get("gaps") or {}) if isinstance(audit, dict) else {}
    out: dict[str, dict[str, int]] = {}
    for span, rows in by_span.items() if isinstance(by_span, dict) else ():
        for sym, count in (rows.items() if isinstance(rows, dict) else ()):
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                out.setdefault(str(sym), {})[str(span)] = count
    return out


@dataclass
class _Prepared:
    needs: Mapping[str, Any]
    symbols: tuple[str, ...]
    history: int
    layout: Mapping[str, Any]
    c_D: float
    c_R: float | None
    level: bool | None


def _pool(store: blocks.DeepStore, code: str, params: Mapping[str, Any], runs: Runs, segments: Sequence[Any],
          symbols: Sequence[str], parent: Path | None) -> list[dict[str, np.ndarray]] | None:
    """The own floors' pool (open data only): the Train-era runs and the relabeled TRAIN-D run at k 2.0, each from its
    first decision + 2 sessions (`stat.piece`). None when the TRAIN-D run did not finish."""
    with relabel.relabeled(store, "traind", symbols, parent=parent) as rl:
        traind = runs.on_store(rl.root, code, params, rl.scored_pseudo[0], rl.pseudo_days[-1], config.K_JUDGED)
    if not _usable(traind):
        return None
    return [S.piece(_part(r, symbols), skip=config.POOL_SKIP) for r in [*segments, traind]]


def _refused(why: str) -> tuple[None, dict[str, Any]]:
    return None, {"status": "refused", "why": why}


def _prepare(store: blocks.DeepStore, version: Version, runs: Runs, *, kind: str, worlds: int,
             parent: Path | None) -> tuple[_Prepared | None, dict[str, Any] | None]:
    """Steps 2 to 4: (the prepared look, None) or (None, a refusal or a wait). Opens nothing sealed and runs no
    reserve session. The route's recall is read before any run is made, so a version that waits costs none."""
    code, params = version.code, dict(version.params)
    needs = runs.needs(code, params)
    symbols = tuple(str(s).upper() for s in needs.get("symbols") or ())
    history = int(needs.get("history") or 0)
    if not screen3.etf_only(symbols):
        return _refused("not ETF only (DVAL's 15)")
    real = kind == "look"
    recall = version.strong_recall if real else False
    if real and not version.route_known:
        return _refused("no route is named: its 2001-08 recall cannot be read")
    if recall is True:
        return _refused("a strong-recall route on contam_probe's 2001-08 cells")
    if recall is None:
        return None, {"status": "waits", "why": "the route's 2001-08 recall is not measured yet"}
    seen: dict[str, Any] = {"blind": True, "level": None}
    if real:
        seen = blind.check(code, params, lambda root, start, end: runs.on_store(root, code, params, start, end,
                                                                               config.K_RECENT).result,
                           symbols=symbols, history=history, parent=parent, level=True)
        if not seen["blind"]:
            return _refused("not calendar-blind")
    segments = list(runs.segments(code, params))
    if not segments or not all(_usable(r) for r in segments):
        return _refused("its Train-era runs did not finish")
    lots = [lot for r in segments for lot in r.result.get("lots") or []]
    trips = screen3.round_trips_a_year([(r.result.get("lots") or [], int(r.bars.n) - int(r.bars.first))
                                        for r in segments])
    plan = screen3.rules(symbols=symbols, history=history, first_days=_first_days(store, symbols),
                         late_clean=_late_clean(store), round_trips=trips, overnight=screen3.overnight_share(lots),
                         strong_recall=recall, blind=seen["blind"], gaps=_gaps(store))
    if plan.get("wait"):
        return None, {"status": "waits", "why": plan["why"]}
    if not plan["eligible"]:
        return _refused(plan["why"])
    pool = _pool(store, code, params, runs, segments, symbols, parent)
    if pool is None:
        return _refused("its TRAIN-D run did not finish")
    c_D = screen3.bar(float(config.RECEIPT["c_D"]), screen3.deep_floor(pool, _layout_keep(plan["layout"]),
                                                                       version_tag=version.tag, worlds=worlds))
    if c_D is None:
        return _refused("no deep floor (no pool, no exposure, or past 5.00)")
    c_R = None
    if real:
        c_R = screen3.bar(float(config.RECEIPT["c_R"]), screen3.recent_floor(pool, version_tag=version.tag,
                                                                             worlds=worlds))
        if c_R is None:
            return _refused("no recent floor (no pool, no exposure, or past 5.00)")
    return _Prepared(needs=needs, symbols=symbols, history=history, layout=plan["layout"], c_D=c_D, c_R=c_R,
                     level=seen.get("level")), None


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


def _deep(store_root: Path, code: str, params: Mapping[str, Any], runs: Runs, prepared: _Prepared) -> dict[str, Any]:
    """Step 5: the DVAL runs inside temporary stores in the sealed tree's looks directory and the deep key (booleans
    only)."""
    cap = mint_deep_gate_capability(store_root, "s3-look")
    sealed = blocks.DeepStore(store_root, gate=cap)
    masked = set(calendar.mask())
    parts = []
    for name, seg in prepared.layout["segments"].items():
        if not seg:
            continue
        with relabel.relabeled(sealed, name, prepared.symbols) as rl:
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


def _recent_key(version: Version, runs: Runs, c_R: float) -> dict[str, Any]:
    """Step 6, THE ONLY PLACE A RESERVE SESSION IS RUN (`Runs.recent`): the recent key on R + V + H at c_R (computed
    before the look from open data); a run the program ended fails it (the look is spent)."""
    arrays = runs.recent(version.code, dict(version.params))
    if arrays is None:  # the program's own errors ended a recent window's run
        return {"passed": False, "checks": {"t": False, "sum_h": False}}
    return screen3.recent_key(list(arrays), c_R)


def look(store_root: str | Path, version: Version, runs: Runs, *, ledger: Ledger, identity: str, now: str,
         reserve: bool = True, kind: str = "look", worlds: int = config.FLOOR_WORLDS,
         parent: str | Path | None = None) -> dict[str, Any]:
    """ONE S3 LOOK (the module docstring): {"status": "looked" | "refused" | "waits" | "halted" | "budget" | "cell" |
    "already" | "failed" | "lost" | "ledger", "why"?, "passed"?, "deep"?, "recent"?}. `reserve`: the owner's D2 is
    "judged" (False: a real look is not made at all, "waits": both keys or neither). `kind` "canary" judges the deep
    key alone and skips the blind test (the canary is ours). `parent`: where the open segments' and the behavioural
    test's temporary stores go (default: the deep store's looks directory, as the DVAL segments' always). An error of
    the House's is raised with the attempt withdrawn (no look spent); `RunLost` after the look began is "lost" (owed
    once more)."""
    store_root = Path(store_root)
    key = version.key
    if ledger.damaged:
        return {"status": "ledger", "why": f"the look ledger is damaged ({ledger.problem}): no look until the captain "
                                           f"restores it"}
    if ledger.halted():
        return {"status": "halted", "why": "the canaries' deep-key passes are above their band: S3 halts"}
    found = ledger.row(key)
    if found is not None and found.get("verdict") is not None:
        return {"status": "already", "why": "one look a version"}
    if kind == "look" and not reserve:
        return {"status": "waits", "why": "elane.deep.reserve is sealed: a version is judged on both keys or not at all"}
    if found is None and len(ledger.spent()) >= config.LOOK_BUDGET:
        return {"status": "budget", "why": "150 looks: an erosion review first"}
    if found is None and kind == "look" and ledger.cell_count(version.cell) >= config.LOOKS_PER_CELL:
        return {"status": "cell", "why": f"three looks in cell {version.cell}"}
    if found is not None and int(found.get("attempts") or 0) >= config.LOOK_ATTEMPTS:
        ledger.finish(key, "failed")
        return {"status": "failed", "why": "the look was begun twice and never finished (a sealed run that did not "
                                           "return, or its process killed): spent and failed"}
    store = blocks.DeepStore(store_root)
    parent = blocks.looks_dir(store_root, make=True) if parent is None else Path(parent)
    try:
        prepared, stop = _prepare(store, version, runs, kind=kind, worlds=worlds, parent=parent)
    except CodeRefused as exc:  # the program does not load (the child's reason): a refusal, no look spent
        prepared, stop = _refused(f"the program does not load: {str(exc)[:120]}")
    except RunLost:  # an open-data run sent whole and not answered: the program's, before anything sealed was opened
        prepared, stop = _refused("a run on open data was sent and did not return (past its budget, or it exited)")
    if stop is not None:
        if stop["status"] == "refused":
            ledger.refuse(key, stop["why"], identity=identity, at=now)
        return stop
    assert prepared is not None
    ledger.begin({"key": key, "fid": version.fid, "n": int(version.n), "cell": version.cell, "kind": kind, "at": now,
                  "seated": bool(version.seated), "source": str(version.source), "level": prepared.level,
                  "identity": identity, "engine": DEEP_ENGINE_VERSION, "receipt": config.RECEIPT_SHA256[:12]})
    try:
        deep = _deep(store_root, version.code, dict(version.params), runs, prepared)
        if kind != "look":
            verdict = screen3.verdict(deep, None)
        else:
            assert prepared.c_R is not None
            verdict = screen3.verdict(deep, _recent_key(version, runs, prepared.c_R))
    except RunLost:
        # A SEALED RUN SENT WHOLE AND NOT ANSWERED: the attempt stands; owed once more, the second time spent and failed
        attempts = int((ledger.row(key) or {}).get("attempts") or 0)
        if attempts >= config.LOOK_ATTEMPTS:
            ledger.finish(key, "failed")
            return {"status": "failed", "why": f"a sealed run was sent {attempts} times and did not return: spent and "
                                               f"failed"}
        return {"status": "lost", "why": f"a sealed run was sent and did not return ({attempts} of "
                                         f"{config.LOOK_ATTEMPTS}): owed once more"}
    except Exception:
        ledger.withdraw(key)   # THE HOUSE'S ERROR: no look is spent; the job records it and goes on
        raise
    ledger.finish(key, verdict)
    return {"status": "looked", **verdict}


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
    return Version(fid=source.fid, n=int(source.n), code=code, params={}, cell="canary", strong_recall=False,
                   source="canary")


__all__ = ["REASONS", "LEDGER_VERSION", "LedgerDamaged", "DeepGateCapability", "mint_deep_gate_capability",
           "version_key", "band_upper", "canary_slot", "Ledger", "CANARY", "canary_plan", "canary_code", "Version",
           "Runs", "look", "canary_for"]
