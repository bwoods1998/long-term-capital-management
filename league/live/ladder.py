"""THE FORWARD LADDER: evidence v3, the route from practice to real money (the owner's D2 of Oct 2, 2026: "forward
ladder YES"; the plan's Phase 3).

    Train (the Gym, 2020-2024) -> Validation (2025; its line unchanged) -> PRE-FILTER (the 2026 holdout read once on a
    gate box as a FREE read: no look row, no Holm, no look budget; not negative) -> PRACTICE (shadow on live quotes, an
    immutable version, every session recorded) -> PROBE (real, the money table's sizes) -> SIZED (real, Kelly on the
    real fills' lower bound: `league/live/money.py`)

ENTRANTS. Every practice cohort frozen from this release on (`ObserveStore.freeze`: the validated tier and the Train
tier, as the practice league takes them) is a ladder cohort and an ENTRANT: one `entrants` row with its admission, a
trial of its lineage and of the desk. Its program and parameters are its snapshot's, for good.

THE PROBE LINE, judged at each session's end (`end_of_day`, from `OptionsLive._end_of_day`) on the cohort's own
practice record alone (its immutable version, its own practice evaluator, its PROGRAM closes: the House's wind-down
closes are left out), every line of the constitution's `options_money.ladder` (`Rules`):

  L1 RECORD    at least `min_sessions` sessions practised (its practice row's sessions) and `min_closes` program
               closes (a close is counted on its exit day: the per-session counts are in the receipt);
  L2 BOUND     a day-block bootstrap (the session days that closed a trade, resampled with replacement, `draws` times;
               deterministic, seeded by the record's inputs) of the mean return per dollar of maximum loss: its
               one-sided `confidence` lower bound above zero. Its p-value (the share of resampled means at or below
               zero) is the entrant's; a mean at or below zero, or fewer than two session days, is p = 1 and no bound;
  L3 WINDOWS   the cohort's calendar sessions from its first day split in `windows` equal contiguous sub-windows: the
               returns of the closes in at least `windows_positive` of them sum above zero;
  L4 DRIFT     THE DRIFT CONTROL: each close's P&L net of its ENTRY DELTA times the underlying's move over its holding
               period (the position's dollar delta at the decision, from the engine's own context: each leg's delta x
               side x ratio x 100 x quantity; times the underlying at its exit, recorded with the trade, less the
               underlying at its entry), per dollar of maximum loss: their mean above zero, with those figures known for
               at least `drift_known_share` of its closes. A program whose P&L is its delta riding the market's move
               (drift) fails it; one whose edge does not come from its delta (premium, volatility, timing of the
               option's price rather than the underlying's) keeps it. It is deliberately strict: a directional timing
               edge, whose P&L IS its delta times the move it timed, fails it too (the benchmark's planted directional
               world measures what this costs);
  L5 FDR       Benjamini-Hochberg at `fdr_q` over every entrant of the trailing `fdr_days` days (each with its latest
               p-value; an entrant without a full record, L1, counts with p = 1): its p-value is one the procedure
               rejects;
  L6 PRE-FILTER the gate's free read of the 2026 holdout (`league/swarm/gate.py`, `Gate.prefilter_round`), requested
               when a cohort first meets L1-L5 (kv `ladder_prefilter_requests`, the House's) and written by the gate
               (kv `ladder_prefilter:<run_sha>`, the gate's): its net P&L after fees is not negative, on the Gym bundle
               the House runs. A negative read fails the cohort for good.

Every judgement is a `ladder_decisions` row (its inputs' hash, its figures, its BH rank and family size, its verdict):
the PRACTICE RECEIPT. A cohort that meets every line is PROMOTED (only while `binding` is true) through the swarm's
store (`SwarmStore.set_band(family, "probe")`, the receipt's id in its reason and in the family's `banded_evaluator`
proof, `route` "ladder"): its banded version is the cohort's version, whose code and parameters in the store must be
the snapshot's (`run_sha` too), so the real instance runs exactly the practised program, and it trades real money from
the session after its promotion (`OptionsLive._real_eligible`). THE LADDER'S BELT comes first (`bands.ladder_refusal`:
the family alive in the Gym band, the version undemoted, no review, audit, refusal or bar against the program). A
cohort whose family retired or holds another band cannot be promoted: it fails. `binding` false: the ladder judges and
records everything ("would_promote") and promotes nothing.

A cohort runs until it is promoted, failed, or its practice window ends (`max_sessions`, `ObserveStore.
cohort_candidates`); the old observation target (3 sessions, 10 closes) never ends a ladder cohort.

DEMOTION (at each session's end): a ladder Probe or Sized family (and a Candidate the money table moved down) goes back
to the GYM, its cohort "demoted", when its forward record since its promotion (`money.one_record`: its own version,
one source a day, real first) is negative over 20 trades, or the one-sided `demote_confidence` lower bound of the
mean of its trailing `demote_sessions` session days is below zero (`money.session_bound`). A demoted program never
returns to Probe but through a new version's new cohort.

NEVER EVIDENCE: the incubator's trades (`:i`), tuition, the calibration round trips and the House live test are never
in a practice record (`observe.sqlite`'s trades are the shadow book's alone), so none of them is ladder evidence.

Every write here is the House's: the practice record and its receipts in `<state>/observe.sqlite`, the band and the
pre-filter request in `<state>/swarm.sqlite` (through the House's own connection, `SwarmFamilies`).
"""

from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
#: The snapshot marker of a ladder cohort (`ObserveStore.freeze`).
LADDER_VERSION = 1
#: Contracts a structure is quoted for (the venue's multiplier).
MULTIPLIER = 100.0
#: An exit's underlying is the last price read at most this many minutes before its fill (`exit_spot`).
EXIT_SPOT_STALE_MINUTES = 5
#: The swarm store's key-values of the pre-filter (`league/swarm/gate.py`): the House's requests, the gate's results.
PREFILTER_REQUESTS = "ladder_prefilter_requests"
PREFILTER_KEY = "ladder_prefilter:"
#: The verdicts a receipt can carry.
VERDICTS = ("short", "ineligible", "fail", "await_prefilter", "prefilter_negative", "would_promote", "promote",
            "promoted", "blocked", "demote")


# ------------------------------------------------------------------------------------------------------- the rules
@dataclass(frozen=True)
class Rules:
    """The constitution's `options_money.ladder`, read (the module docstring)."""

    binding: bool
    min_sessions: int
    min_closes: int
    confidence: float
    draws: int
    windows: int
    windows_positive: int
    fdr_q: float
    fdr_days: int
    max_sessions: int
    drift_known_share: float
    demote_sessions: int
    demote_confidence: float

    @classmethod
    def from_constitution(cls, constitution: Mapping[str, Any] | None = None) -> "Rules":
        """The ladder in force; ValueError when the money table is refused (nothing is promoted on a bad table)."""
        from ..constitution import CONSTITUTION, options_money_problems

        rules = dict(constitution or CONSTITUTION)
        problems = options_money_problems(rules)
        if problems:
            raise ValueError("the forward ladder's table is refused: " + "; ".join(problems))
        t = rules["options_money"]["ladder"]
        return cls(binding=t["binding"] is True, min_sessions=int(t["min_sessions"]), min_closes=int(t["min_closes"]),
                   confidence=float(t["confidence"]), draws=int(t["draws"]), windows=int(t["windows"]),
                   windows_positive=int(t["windows_positive"]), fdr_q=float(t["fdr_q"]), fdr_days=int(t["fdr_days"]),
                   max_sessions=int(t["max_sessions"]), drift_known_share=float(t["drift_known_share"]),
                   demote_sessions=int(t["demote_sessions"]), demote_confidence=float(t["demote_confidence"]))


# ------------------------------------------------------------------------------------------------------ the record
@dataclass(frozen=True)
class Close:
    """One program close of a practice record: its exit day, its return on maximum loss, the same net of its entry
    delta times the underlying's move (None when a figure is unknown), and its one-lot unit (maximum loss a lot plus
    twice the fees a lot; None without a quantity)."""

    day: str
    r: float
    r_adj: float | None
    unit: float | None
    key: str = ""


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _body(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        out = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def entry_delta(body: Mapping[str, Any]) -> float | None:
    """The position's dollar delta at its decision (per dollar of the underlying): each leg's delta (the engine's
    context, in the legs' order) x its side (+1 long, -1 short) x its ratio, x 100 x the quantity. None when a figure is
    missing or not finite."""
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}
    legs, deltas = body.get("legs"), context.get("delta")
    qty = _num(body.get("qty"))
    if not isinstance(legs, list) or not isinstance(deltas, list) or not legs or len(legs) != len(deltas) or not qty:
        return None
    total = 0.0
    for leg, delta in zip(legs, deltas):
        d = _num(delta)
        side = {"long": 1.0, "short": -1.0}.get(str((leg or {}).get("side"))) if isinstance(leg, Mapping) else None
        ratio = _num(leg.get("ratio") if isinstance(leg, Mapping) else None)
        if d is None or side is None or ratio is None:
            return None
        total += side * ratio * d
    return total * MULTIPLIER * qty


def drift_usd(body: Mapping[str, Any]) -> float | None:
    """THE DRIFT CONTROL's charge on one close: its entry delta times the underlying's move from its entry (the
    decision's spot) to its exit (`exit_spot`, recorded with the trade). None when a figure is unknown."""
    delta = entry_delta(body)
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}
    entry, exit_ = _num(context.get("spot")), _num(body.get("exit_spot"))
    if delta is None or entry is None or exit_ is None or entry <= 0 or exit_ <= 0:
        return None
    return delta * (exit_ - entry)


def close_of(row: Mapping[str, Any]) -> Close | None:
    """A ledger row (`ObserveStore.ladder_rows`: pnl, max_loss, exit_day, body) as a `Close`; None when it has no
    positive maximum loss (no return)."""
    pnl, max_loss = _num(row.get("pnl")), _num(row.get("max_loss"))
    day = str(row.get("exit_day") or "")
    if pnl is None or max_loss is None or max_loss <= 0 or not day:
        return None
    body = _body(row.get("body"))
    drift = drift_usd(body)
    qty, fees = _num(body.get("qty")), _num(body.get("fees")) or 0.0
    unit = max_loss / qty + 2.0 * fees / qty if qty and qty >= 1 else None
    return Close(day=day[:10], r=pnl / max_loss, r_adj=None if drift is None else (pnl - drift) / max_loss,
                 unit=unit if unit is not None and math.isfinite(unit) and unit > 0 else None,
                 key=str(row.get("seq") if row.get("seq") is not None else row.get("trade_id") or ""))


def sessions_between(first: str, last: str) -> list[str]:
    """The NYSE session days from `first` to `last`, both included (the live path's own calendar)."""
    from .chains import session_minutes

    out, day, end = [], dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    while day <= end:
        if session_minutes(day) is not None:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------------------------------------------ the lines
def bootstrap(closes: Sequence[Close], *, confidence: float, draws: int, seed: str) -> dict[str, Any]:
    """L2: the day-block bootstrap of the mean return on maximum loss (the module docstring): {mean, lcb, p, days}.
    Deterministic for a seed. A mean at or below zero, or fewer than two session days with a close, gives p = 1 and no
    bound (the resampled means could not be above zero at the line's confidence, or have no spread)."""
    import numpy as np

    by_day: dict[str, list[float]] = {}
    for c in closes:
        acc = by_day.setdefault(c.day, [0.0, 0.0])
        acc[0] += c.r
        acc[1] += 1.0
    n = sum(v[1] for v in by_day.values())
    mean = sum(v[0] for v in by_day.values()) / n if n else None
    out = {"mean": mean, "lcb": None, "p": 1.0, "days": len(by_day), "draws": 0}
    if mean is None or not mean > 0 or len(by_day) < 2:
        return out
    sums = np.array([v[0] for _, v in sorted(by_day.items())])
    counts = np.array([v[1] for _, v in sorted(by_day.items())])
    rng = np.random.default_rng(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    idx = rng.integers(0, len(sums), size=(int(draws), len(sums)))
    means = np.sort(sums[idx].sum(axis=1) / counts[idx].sum(axis=1))
    out.update(lcb=float(means[int((1.0 - float(confidence)) * len(means))]),
               p=max(float((means <= 0).sum()) / len(means), 1.0 / (len(means) + 1)), draws=int(draws))
    return out


def windows(closes: Sequence[Close], sessions: Sequence[str], k: int) -> list[float]:
    """L3: the returns of the closes in each of `k` equal contiguous sub-windows of `sessions` (sizes differ by at most
    one session), summed. A close outside the sessions is placed by its day."""
    sessions = sorted(sessions)
    n = len(sessions)
    if n == 0 or k < 1:
        return [0.0] * max(0, k)
    starts = [sessions[(i * n) // k] for i in range(k)]
    sums = [0.0] * k
    for c in closes:
        i = min(k - 1, max(0, bisect.bisect_right(starts, c.day) - 1))
        sums[i] += c.r
    return sums


def drift_line(closes: Sequence[Close], known_share: float) -> dict[str, Any]:
    """L4: THE DRIFT CONTROL (the module docstring): {known, share, mean, passed}."""
    known = [c.r_adj for c in closes if c.r_adj is not None]
    share = len(known) / len(closes) if closes else 0.0
    mean = sum(known) / len(known) if known else None
    return {"known": len(known), "share": round(share, 6), "mean": mean,
            "passed": bool(closes) and share >= float(known_share) and mean is not None and mean > 0}


def benjamini_hochberg(ps: Iterable[float], q: float) -> tuple[float | None, int]:
    """L5: (the largest p-value Benjamini-Hochberg rejects at level `q` over `ps`, every p at or under it rejected;
    None when it rejects none) and the family size m."""
    ordered = sorted(float(p) for p in ps)
    m = len(ordered)
    cut = None
    for k, p in enumerate(ordered, 1):
        if p <= k * float(q) / m:
            cut = p
    return cut, m


def inputs_hash(cohort: Mapping[str, Any], through: str, sessions: Any, closes: Sequence[Close], rules: Rules) -> str:
    """The receipt's inputs: the cohort, the day, its sessions, every close's figures and the rules, hashed."""
    snap = cohort.get("snapshot") or {}
    body = {"family": cohort["family"], "version": int(cohort["version"]), "run_sha": snap.get("run_sha"),
            "evaluator": snap.get("practice_evaluator"), "first_day": cohort["first_day"], "through": through,
            "sessions": sessions, "closes": [[c.key, c.day, round(c.r, 10), None if c.r_adj is None else round(c.r_adj, 10)]
                                             for c in closes], "rules": asdict(rules)}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def judge(cohort: Mapping[str, Any], practice: Mapping[str, Any] | None, rows: Sequence[Mapping[str, Any]], *,
          through: str, rules: Rules) -> dict[str, Any]:
    """Lines L1-L4 of one cohort's record through the session day `through`, and its p-value (L5's input): {inputs,
    sessions, closes, per_session, mean, lcb, p, days, windows, windows_positive, drift, typical, lines {record, bound,
    windows, drift}, full, eligible}. `practice` is its practice row (`sessions` None, ineligible, when that row began
    before the cohort did)."""
    first = str(cohort["first_day"])
    if practice is None:
        sessions: int | None = 0
    elif str(practice.get("first_day") or "") < first:
        sessions = None
    else:
        sessions = int(practice.get("sessions") or 0)
    closes = [c for c in (close_of(r) for r in rows) if c is not None]
    inputs = inputs_hash(cohort, through, sessions, closes, rules)
    per_session: dict[str, int] = {}
    for c in closes:
        per_session[c.day] = per_session.get(c.day, 0) + 1
    calendar = sessions_between(first, through) if first <= through else []
    full = sessions is not None and sessions >= rules.min_sessions and len(closes) >= rules.min_closes
    boot = bootstrap(closes, confidence=rules.confidence, draws=rules.draws, seed=inputs) if full else \
        {"mean": (sum(c.r for c in closes) / len(closes)) if closes else None, "lcb": None, "p": 1.0,
         "days": len(per_session), "draws": 0}
    sums = windows(closes, calendar, rules.windows)
    positive = sum(1 for s in sums if s > 0)
    drift = drift_line(closes, rules.drift_known_share)
    units = sorted(c.unit for c in closes if c.unit is not None)
    lines = {"record": full, "bound": boot["lcb"] is not None and boot["lcb"] > 0,
             "windows": positive >= rules.windows_positive, "drift": drift["passed"]}
    return {"inputs": inputs, "sessions": sessions, "calendar_sessions": len(calendar), "closes": len(closes),
            "per_session": dict(sorted(per_session.items())), "mean": boot["mean"], "lcb": boot["lcb"],
            "p": float(boot["p"]) if full else 1.0, "days": boot["days"], "draws": boot["draws"],
            "windows": [round(s, 6) for s in sums], "windows_positive": positive, "drift": drift,
            "typical": round(units[len(units) // 2], 2) if units else None, "lines": lines, "full": full,
            "eligible": sessions is not None}


# ---------------------------------------------------------------------------------------------- the exit's spot
def exit_spot(trade: Mapping[str, Any], day: Any) -> float | None:
    """The underlying at a practice close's exit (THE DRIFT CONTROL's figure), read from the session's own grids while the
    trade is exported (`OptionsLive._export_one`): the last price at or at most `EXIT_SPOT_STALE_MINUTES` minutes before
    its exit minute, or the settlement level for a close without one (an expiry). None when that is not today's session,
    the root was not read or no price is known."""
    if day is None or str(trade.get("exit_day") or "")[:10] != day.day.isoformat():
        return None
    chain = getattr(day, "chains", {}).get(str(trade.get("root") or "").upper())
    if chain is None:
        return None
    under = chain.underlying
    minute = trade.get("exit_minute")
    try:
        if minute is None:
            from ..gym.engine import settlement_level

            level = float(settlement_level(under))
        else:
            mi = int(minute) - int(day.open_min)
            prices = under.price
            level = float("nan")
            for i in range(min(mi, len(prices) - 1), max(-1, mi - EXIT_SPOT_STALE_MINUTES - 1), -1):
                if math.isfinite(float(prices[i])):
                    level = float(prices[i])
                    break
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
    return round(level, 4) if math.isfinite(level) and level > 0 else None


# ------------------------------------------------------------------------------------------------ the swarm's side
class SwarmBridge:
    """The ladder's reads and writes in the swarm's store (`<state>/swarm.sqlite`), through the House's own connection
    and lock (`league.live.families.SwarmFamilies`)."""

    def __init__(self, families: Any):
        self.families = families

    def _store(self) -> Any:
        return self.families._db()

    def prefilter(self, run_sha: str) -> dict[str, Any] | None:
        with self.families.lock:
            value = self._store().get(PREFILTER_KEY + str(run_sha))
        return dict(value) if isinstance(value, Mapping) else None

    def request_prefilter(self, run_sha: str, *, family: str, version: int, bundle: str | None, day: str) -> None:
        """The House's request (only the House writes `PREFILTER_REQUESTS`; the gate reads it and writes the result)."""
        with self.families.lock:
            store = self._store()
            with store.atomic():
                requests = dict(store.get(PREFILTER_REQUESTS) or {})
                old = requests.get(run_sha) or {}
                if old.get("bundle") == bundle and old.get("family") == family and old.get("version") == int(version):
                    return
                requests[str(run_sha)] = {"family": str(family), "version": int(version), "bundle": bundle, "day": day}
                store.put(PREFILTER_REQUESTS, requests)

    def settle_prefilter(self, run_sha: str) -> None:
        """A request the ladder is done with (its cohort promoted or failed) leaves the requests."""
        with self.families.lock:
            store = self._store()
            with store.atomic():
                requests = dict(store.get(PREFILTER_REQUESTS) or {})
                if requests.pop(str(run_sha), None) is not None:
                    store.put(PREFILTER_REQUESTS, requests)

    def refusal(self, family: str, version: int, run_sha: str) -> str | None:
        from ..swarm.bands import ladder_refusal

        return ladder_refusal(self.families.root, family=family, version=version, run_sha=run_sha)

    def promote(self, *, family: str, version: int, snapshot: Mapping[str, Any], receipt: int,
                typical: float | None, at: float) -> str | None:
        """The promotion (the module docstring), in one transaction of the swarm's store: None when it landed, else why
        not (nothing written)."""
        from ..gym import ENGINE_VERSION
        from ..gym.experiment import CONTRACT_VERSION
        from ..swarm.evaluator import execution_fingerprint
        from ..swarm.gate import run_sha

        class _Refused(Exception):
            pass

        try:
            with self.families.lock:
                store = self._store()
                with store.atomic():
                    fam = store.family(str(family))
                    if fam is None or fam.get("retired_at"):
                        raise _Refused("the family retired: it has no band to promote")
                    if fam["band"] != "gym":
                        raise _Refused(f"the family is at {fam['band']}, not in the Gym band")
                    row = store.version(str(family), int(version))
                    if row is None or row.get("code") != snapshot.get("code") or \
                            (row.get("params") or {}) != (snapshot.get("params") or {}):
                        raise _Refused("the store's version is not the practised program")
                    sha = run_sha(row)
                    if sha != snapshot.get("run_sha"):
                        raise _Refused("the store's version is not the practised program (its run sha)")
                    state = fam.get("state") or {}
                    typical_by = dict(state.get("typical_by_version") or {})
                    if typical is not None:
                        typical_by[str(int(version))] = typical
                    store.set_state(str(family), banded_version=int(version), banded_sha=row["sha"], banded_at=float(at),
                                    live_promoted_at=float(at), typical_by_version=typical_by, forward=None,
                                    ladder_receipt=int(receipt),
                                    banded_evaluator={"route": "ladder", "engine": ENGINE_VERSION,
                                                      "parameter_contract": CONTRACT_VERSION,
                                                      "execution_sha256": execution_fingerprint(), "run_sha": sha,
                                                      "practice_evaluator": snapshot.get("practice_evaluator"),
                                                      "receipt": int(receipt), "at": float(at)})
                    if store.set_band(str(family), "probe", reason=f"the forward ladder promoted it (practice receipt "
                                                                   f"{int(receipt)})") != "gym":
                        raise _Refused("its band could not be moved")
        except _Refused as exc:
            return str(exc)
        return None

    def ladder_families(self) -> list[dict[str, Any]]:
        """The alive families on a band the ladder gave (`banded_evaluator.route` "ladder"), at candidate, probe or
        sized: [{family, band, version, promoted_at}]."""
        with self.families.lock:
            fams = self._store().families(alive=True)
        out = []
        for fam in fams:
            state = fam.get("state") or {}
            proof = state.get("banded_evaluator") or {}
            if fam["band"] in ("candidate", "probe", "sized") and proof.get("route") == "ladder":
                out.append({"family": fam["id"], "band": fam["band"], "version": state.get("banded_version"),
                            "promoted_at": _num(state.get("live_promoted_at") or proof.get("at"))})
        return out

    def forward_rows(self, family: str) -> list[dict[str, Any]]:
        with self.families.lock:
            return [dict(r) for r in self._store().forward(str(family))]

    def demote(self, family: str, *, why: str, receipt: int, at: float) -> bool:
        with self.families.lock:
            store = self._store()
            with store.atomic():
                fam = store.family(str(family))
                if fam is None or fam.get("retired_at") or fam["band"] not in ("candidate", "probe", "sized"):
                    return False
                store.set_state(str(family), ladder_demoted={"receipt": int(receipt), "why": why, "at": float(at),
                                                             "version": (fam.get("state") or {}).get("banded_version")},
                                dormant_cycles=0)
                return store.set_band(str(family), "gym", reason=f"the forward ladder demoted it: {why} (receipt "
                                                                 f"{int(receipt)})") is not None


def default_bridge(live: Any) -> Any:
    """The swarm's store when the House runs the swarm (`SwarmFamilies`), else None: the ladder then judges and records,
    and promotes nothing."""
    families = getattr(live, "families", None)
    if families is not None and callable(getattr(families, "_db", None)) and getattr(families, "root", None) is not None:
        return SwarmBridge(families)
    return None


# ------------------------------------------------------------------------------------------------------- the ladder
class Ladder:
    """The forward ladder's session end (the module docstring). `live` is the House's `OptionsLive`."""

    def __init__(self, live: Any, *, bridge: Any = None):
        self.live = live
        self.bridge = bridge if bridge is not None else default_bridge(live)

    def _bundle(self) -> str | None:
        try:
            from .observe import evaluator_bundle

            return evaluator_bundle()
        except Exception:  # noqa: BLE001 - no bundle: no pre-filter read can be matched (fail-closed)
            return None

    def end_of_day(self, day: str) -> dict[str, Any]:
        """Judge every active ladder cohort through the session day `day`, then the demotions."""
        rules = Rules.from_constitution()
        store = self.live.observe_store
        evaluator = store.evaluator
        out: dict[str, Any] = {"day": day, "binding": rules.binding, "judged": 0, "verdicts": {}}
        judged = []
        for cohort in store.ladder_cohorts():
            snap = cohort["snapshot"]
            if snap.get("practice_evaluator") != evaluator:
                continue  # completed at the next session's pins ("evaluator changed")
            practice, rows = store.ladder_rows(cohort["family"], cohort["version"], evaluator=evaluator,
                                               first_day=cohort["first_day"], through=day)
            figures = judge(cohort, practice, rows, through=day, rules=rules)
            store.set_entrant_p(cohort["family"], cohort["version"], figures["p"], day=day)
            judged.append((cohort, figures))
        since = (dt.date.fromisoformat(day) - dt.timedelta(days=rules.fdr_days)).isoformat()
        entrants = {(e["family"], int(e["version"])): (1.0 if e["p_value"] is None else float(e["p_value"]))
                    for e in store.entrants(since=since)}
        for cohort, figures in judged:  # a judged cohort is always an entrant (`freeze`); counted once if not
            entrants.setdefault((cohort["family"], int(cohort["version"])), figures["p"])
        cut, m = benjamini_hochberg(entrants.values(), rules.fdr_q)
        ordered = sorted(entrants.values())
        for cohort, figures in judged:
            try:
                verdict = self._decide(cohort, figures, day=day, rules=rules, cut=cut, m=m,
                                       rank=bisect.bisect_left(ordered, figures["p"]) + 1)
            except Exception as exc:  # noqa: BLE001 - one cohort's error promotes nothing and stops no other's judgement
                verdict = "error"
                alert = getattr(self.live, "alert", None)
                if callable(alert):
                    alert("warning", f"live: the forward ladder could not judge {cohort['family']}@{cohort['version']} "
                                     f"({type(exc).__name__}: {str(exc)[:160]}); judged again at the next session's end")
            out["judged"] += 1
            out["verdicts"][verdict] = out["verdicts"].get(verdict, 0) + 1
        out["entrants"], out["bh_size"] = len(entrants), m
        out["demoted"] = self.demotions(day, rules)
        return out

    def _receipt(self, cohort: Mapping[str, Any], figures: Mapping[str, Any], *, day: str, rules: Rules, verdict: str,
                 reasons: list[str], rank: int | None, m: int, cut: float | None) -> int:
        stats = {k: figures[k] for k in ("sessions", "calendar_sessions", "closes", "per_session", "mean", "lcb", "days",
                                         "draws", "windows", "windows_positive", "drift", "typical", "lines")}
        return self.live.observe_store.add_decision({
            "day": day, "family": cohort["family"], "version": cohort["version"],
            "run_sha": (cohort.get("snapshot") or {}).get("run_sha"), "inputs": figures["inputs"], "stats": stats,
            "p_value": figures["p"], "bh_rank": rank, "bh_size": m, "bh_threshold": cut, "verdict": verdict,
            "reasons": reasons, "binding": rules.binding})

    def _decide(self, cohort: Mapping[str, Any], figures: Mapping[str, Any], *, day: str, rules: Rules,
                cut: float | None, m: int, rank: int) -> str:
        store = self.live.observe_store
        snap = cohort["snapshot"]
        f, n, sha = cohort["family"], int(cohort["version"]), str(snap.get("run_sha") or "")
        lines = figures["lines"]
        bh = figures["full"] and cut is not None and figures["p"] <= cut
        receipt = lambda verdict, reasons: self._receipt(cohort, figures, day=day, rules=rules, verdict=verdict,  # noqa: E731
                                                         reasons=reasons, rank=rank, m=m, cut=cut)
        if not figures["eligible"]:
            receipt("ineligible", ["its practice record began before its cohort"])
            return "ineligible"
        if not lines["record"]:
            receipt("short", [f"{figures['sessions']} sessions and {figures['closes']} program closes; the line is "
                              f"{rules.min_sessions} and {rules.min_closes}"])
            return "short"
        failed = [name for name, ok in (("bound", lines["bound"]), ("windows", lines["windows"]), ("drift", lines["drift"]),
                                        ("fdr", bh)) if not ok]
        if failed:
            receipt("fail", [f"the {name} line" for name in failed])
            return "fail"
        if not sha:
            receipt("blocked", ["its snapshot names no run sha"])
            return "blocked"
        bundle = self._bundle()
        result = self.bridge.prefilter(sha) if self.bridge is not None else None
        current = (result is not None and result.get("status") == "done" and bundle is not None
                   and result.get("bundle") == bundle and result.get("ran_bundle") == bundle)
        if not current:
            if self.bridge is not None and bundle is not None:
                self.bridge.request_prefilter(sha, family=f, version=n, bundle=bundle, day=day)
            why = ("no swarm store to ask" if self.bridge is None else "the pre-filter read is requested from the gate"
                   if result is None or result.get("bundle") != bundle else
                   "the pre-filter read ran on another Gym bundle" if result.get("status") == "done" else
                   f"the pre-filter read is {result.get('status')}")
            receipt("await_prefilter", [why])
            return "await_prefilter"
        if not result.get("passed"):
            receipt("prefilter_negative", ["the 2026 holdout read (the pre-filter) is negative"])
            store.close_cohort(f, n, status="failed", day=day, reason="ladder: the pre-filter read was negative")
            self.bridge.settle_prefilter(sha)
            return "prefilter_negative"
        if not rules.binding:
            receipt("would_promote", ["every line met; the ladder does not bind (options_money.ladder.binding)"])
            return "would_promote"
        why = self.bridge.refusal(f, n, sha)
        if why:
            receipt("blocked", [f"the ladder's belt: {why}"])
            store.close_cohort(f, n, status="failed", day=day, reason=f"ladder: {why}")
            self.bridge.settle_prefilter(sha)
            return "blocked"
        receipt_id = receipt("promote", ["every line met: promoted to Probe"])
        why = self.bridge.promote(family=f, version=n, snapshot=snap, receipt=receipt_id, typical=figures["typical"],
                                  at=float(self.live.clock()))
        if why:
            store.set_verdict(receipt_id, "blocked", [why])
            store.close_cohort(f, n, status="failed", day=day, reason=f"ladder: {why}")
            self.bridge.settle_prefilter(sha)
            return "blocked"
        store.close_cohort(f, n, status="promoted", day=day, reason=f"ladder: promoted to Probe (receipt {receipt_id})")
        self.bridge.settle_prefilter(sha)
        self.live.record("live.band", {"family": f, "from": "gym", "to": "probe", "version": n, "receipt": receipt_id,
                                       "why": "the forward ladder promoted it"}, agent=f)
        return "promoted"

    def demotions(self, day: str, rules: Rules) -> list[dict[str, Any]]:
        """DEMOTION (the module docstring) of the families the ladder banded."""
        from . import money as M

        if self.bridge is None:
            return []
        out = []
        for fam in self.bridge.ladder_families():
            version = fam.get("version")
            since = None
            if fam.get("promoted_at") is not None:
                since = dt.datetime.fromtimestamp(float(fam["promoted_at"]), NEW_YORK).date().isoformat()
            rows = [r for r in self.bridge.forward_rows(fam["family"]) if since is None or str(r.get("day") or "") > since]
            fwd = M.forward_stats(rows, rules.demote_confidence, version=version)
            days, lcb = M.session_bound(rows, sessions=rules.demote_sessions, confidence=rules.demote_confidence,
                                        version=version)
            if fwd.negative:
                why = f"its forward record is negative over {fwd.n} trades"
            elif lcb is not None and lcb < 0:
                why = f"the lower bound of its trailing {days} sessions is below zero"
            else:
                continue
            receipt = self.live.observe_store.add_decision({
                "day": day, "family": fam["family"], "version": int(version or 0), "run_sha": None,
                "inputs": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(),
                "stats": {"trades": fwd.n, "mean": fwd.mean, "session_days": days, "session_lcb": lcb, "band": fam["band"]},
                "p_value": None, "verdict": "demote", "reasons": [why], "binding": rules.binding})
            if self.bridge.demote(fam["family"], why=why, receipt=receipt, at=float(self.live.clock())):
                self.live.observe_store.close_cohort(fam["family"], int(version or 0), status="demoted", day=day,
                                                     reason=f"ladder: {why}", was=("promoted",))
                self.live.record("live.band", {"family": fam["family"], "from": fam["band"], "to": "gym",
                                               "version": version, "receipt": receipt,
                                               "why": f"the forward ladder demoted it: {why}"}, agent=fam["family"])
                out.append({"family": fam["family"], "why": why, "receipt": receipt})
        return out


def end_of_day(live: Any, day: str) -> dict[str, Any]:
    """`OptionsLive._end_of_day`'s hook: the House's ladder (made once, `live.ladder`), judged through `day`."""
    ladder = getattr(live, "ladder", None)
    if ladder is None:
        ladder = Ladder(live)
        live.ladder = ladder
    return ladder.end_of_day(day)


# ------------------------------------------------------------------------------------------------- the scoreboard
def counts(root: str | Path, *, day: str | None = None) -> dict[str, Any] | None:
    """The ladder's PUBLIC-SAFE counts (the daily scoreboard's, `league/ops`): {binding, entrants (the trailing
    `fdr_days` window's: the BH family size), in_practice, promoted, demoted, failed, would_promote (receipts of the
    last judged day)}: counts only, never a figure, a family or a program. Read-only (`mode=ro`), never raising: None
    when the record cannot be read; zeros without one."""
    try:
        rules = Rules.from_constitution()
        path = Path(root) / "observe.sqlite"
        out = {"binding": rules.binding, "entrants": 0, "in_practice": 0, "promoted": 0, "demoted": 0, "failed": 0,
               "would_promote": 0}
        if not path.exists():
            return out
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "entrants" not in tables:
                return out
            last = day or (db.execute("SELECT MAX(day) FROM ladder_decisions").fetchone()[0] or
                           dt.date.today().isoformat())
            since = (dt.date.fromisoformat(str(last)) - dt.timedelta(days=rules.fdr_days)).isoformat()
            out["entrants"] = int(db.execute("SELECT COUNT(*) FROM entrants WHERE entered_day>=?", (since,)).fetchone()[0])
            for status, key in (("active", "in_practice"), ("promoted", "promoted"), ("demoted", "demoted"),
                                ("failed", "failed")):
                out[key] = int(db.execute("SELECT COUNT(*) FROM cohorts c JOIN entrants e ON e.family=c.family AND "
                                          "e.version=c.version WHERE c.status=?", (status,)).fetchone()[0])
            out["would_promote"] = int(db.execute("SELECT COUNT(DISTINCT family || '@' || version) FROM ladder_decisions "
                                                  "WHERE day=? AND verdict='would_promote'", (str(last),)).fetchone()[0])
            return out
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - the scoreboard says "n/a"
        return None


__all__ = ["Rules", "Close", "Ladder", "SwarmBridge", "LADDER_VERSION", "PREFILTER_REQUESTS", "PREFILTER_KEY", "VERDICTS",
           "bootstrap", "windows", "drift_line", "benjamini_hochberg", "judge", "close_of", "entry_delta", "drift_usd",
           "exit_spot", "sessions_between", "end_of_day", "counts", "default_bridge"]
