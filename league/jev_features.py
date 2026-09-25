"""The move sensor (J1, docs/goals/LTCM_JEV_SENSES.md): will this Kalshi midpoint move soon, recorded point in time.

Why (Sept 25, 2026). The lab's data (semantic.sqlite, Sept 21-22, events unseen in training) says a
FREE model of 23 quote-and-contract features predicts "the midpoint moves at all" at AUC 0.859 /
0.829 / 0.806 at 5 / 15 / 60 minutes, where the lab's numeric model plus eight Jev answers reached
0.769 / 0.760 / 0.683, and Jev's answers add nothing on top of the free model. So the SERVED model
(`jev_move_model.json`, version move-v1-20260924) uses no Jev at all. Jev keeps a SHADOW model
(`jev_move_model_jev_shadow.json`): the free features plus six static answers about the contract's
own text, asked once per market, recorded as `jev_p` so the post-ship data can say whether Jev earns
anything. The lab's five-feature baseline (`numeric_only` of the served file) is recorded as
`numeric_p`. Direction is not what any of them predicts: a maker needs to know when a price is about
to move so it is not picked off.

Every `interval_seconds` (300) the House runs `MoveSensor.run` as its `jev:move` background job:

1. It reads every `markets:` snapshot the House recorded (`recordings.sqlite`, read-only) past its
   own cursor, oldest first, streamed one at a time, at most `max_snapshots_per_cycle` (1,000; a
   larger backlog waits for the next cycle). The first run only sets the cursor at the newest
   snapshot: nothing is back-filled, and rows from before the recorder existed are unavailable. A
   corrupt snapshot is counted and passed over. The cursor moves with the quotes it kept.
2. Every snapshot read gives its minute quotes (`move_quotes`: one per market and minute bucket,
   first seen wins, as the lab's `semantic_quotes`), even one too old to make rows, so the features'
   history keeps the training cadence when the job waited behind the ops lane. They are each
   state's earlier quotes, the features' history (>= 4 hours of it) and the evaluation's outcomes.
   Only snapshots newer than two intervals make rows (older ones are `stale`).
3. It writes a row for every market shown (at most `max_markets_per_cycle`, 800; never-recorded
   markets first, then the one recorded longest ago). The free features cost nothing. The Jev asks
   are the only paced part, inside the move share of the pool (`move.daily_usd`, $0.75): first the
   static labels of markets that have none (the shadow's per-market questions, over the lab's exact
   state, cached per market text and question set), then, with what the rest of the day's static
   labels leave at today's measured rate of new markets, the two recorded-only questions
   (`moves_15m`, `moves_60m`) over a sample of states chosen by a hash of market and minute, spread
   evenly over the day. No ask is made for a market the models do not apply to. At most 4 asks run
   at once, each waiting at most what the cycle has left; none starts after the House begins to
   close or after `max_seconds_per_cycle` (60). After a failure the Sensor lets one probe through.
4. Each row: the features, the answers, `move_p5/15/60` (served), `numeric_p5/15/60` (lab-5
   baseline), `jev_p5/15/60` (shadow, when the market's static answers exist), and `why` for every
   null, the models' identities (version and file digest) and `lag_seconds` (recorded_at -
   observed). `recorded_at` is taken inside the insert's transaction once its write lock is held,
   and the commit follows the inserts at once: a row is visible within milliseconds after its
   `recorded_at`, never before it. A consumer or replay at time T may see only rows with
   `recorded_at <= T` (`latest`).

Rules:
- Jev is a label source only. Nothing here places an order, changes a money rule, promotes or
  spends beyond the Sensor's caps (`league/jev.py`).
- A model file must define every numeric feature it uses exactly as `DEFINITIONS` does (compared
  ignoring whitespace and case), carry a parseable `fitted_on.to`, and keep its digest for its
  version (`move_models`), else it is refused with an alert: coefficients fitted on one definition
  are never applied to another. A placeholder version counts as no model.
- The feature is not served to strategies here. `latest` is the future `ctx["feeds"]["move"]`
  read. Before a strategy relies on it, `evaluate` (held-out rows after a cutoff no earlier than the
  model's `fitted_on.to`, event-clustered bootstrap, per model version) must show AUC >= 0.70 for
  "moves at all" on post-ship events.

    python -m league.jev_features evaluate --store /workspace/state/jev-features.sqlite --cutoff 2026-09-26T00:00:00Z [--json]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import re
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .ledger import canonical
from .semantic_lab import FEATURES, QUESTION_GUARD, market_state, point, questions

PURPOSE = "move"
MODEL_PATH = Path(__file__).with_name("jev_move_model.json")
SHADOW_PATH = Path(__file__).with_name("jev_move_model_jev_shadow.json")
#: A model file with this version (or `fitted_on.placeholder`) is no model.
PLACEHOLDER = "move-v0-placeholder"
HORIZONS = (5, 15, 60)
#: Asked over a paced sample of states and recorded for the post-ship evaluation. No model uses
#: them: the lab never asked them, so no coefficient for them was fitted on development data.
RECORDED_ONLY = {
    "moves_15m": "Will this contract's quoted midpoint change within the next 15 minutes?" + QUESTION_GUARD,
    "moves_60m": "Will this contract's quoted midpoint change within the next 60 minutes?" + QUESTION_GUARD,
}
#: The lab's question texts, exactly (`semantic_lab.questions('market')`), so answers are comparable.
LAB_QUESTIONS = {name: q["instructions"] for name, q in questions("market").items()}
#: A market's text that does not move with its quote: what its per-market answers are cached by.
STATIC_FIELDS = ("market", "series", "title", "subtitle", "rules_primary", "rules_secondary", "strike", "close_time")
#: A lab-sized state measured $0.000107 a call (Sept 20-22: $13.67 for 128,179 labels); the pace
#: assumes this until today's own move calls say otherwise.
DEFAULT_CALL_USD = Decimal("0.0001")
#: New markets a day needing static labels, until today's own rate is measured (an hour and 20 asks):
#: the Sept 25 estimate (~4,500 a day, ~$0.48). The per-state sample gets what their reserve leaves.
DEFAULT_NEW_MARKETS_PER_DAY = 4500
MIN_FREE_BYTES = 2 * 1024 ** 3  # below this the recorder skips its cycle with an alert
MAX_WORKERS = 4  # concurrent asks; each holds a gateway reservation while in flight
HISTORY_SECONDS = 4 * 3600  # the features read at most four hours of a market's own quotes
SHIP_AUC = 0.70
EPS = 1e-9

# --------------------------------------------------------------------------- features
#: The coarse categories, in order: the first group whose prefix a series starts with, else "other".
CATS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("crypto", ("KXBTC", "KXETH", "KXSOL", "KXDOGE", "KXXRP", "KXNEAR", "KXZEC", "KXHYPE", "KXBNB", "KXCRYPTO",
                "KXLTC", "KXADA", "KXAVAX", "KXLINK", "KXSHIB")),
    ("weather", ("KXHIGH", "KXLOW", "KXRAIN", "KXSNOW", "KXTEMP", "KXHURR", "KXTORN")),
    ("sports", ("KXMLB", "KXNFL", "KXNBA", "KXWNBA", "KXNHL", "KXMLS", "KXNCAA", "KXT20", "KXODI", "KXTEST", "KXLOL",
                "KXCS2", "KXDOTA", "KXVAL", "KXUCL", "KXEPL", "KXLALIGA", "KXLIGUE1", "KXSERIEA", "KXBUNDES", "KXLIGA",
                "KXBRASILEIRO", "KXARGPREM", "KXPGA", "KXATP", "KXWTA", "KXUFC", "KXF1", "KXNASCAR", "KXUEFA", "KXWT20",
                "KXINTLFRIENDLY", "KXVALORANT", "KXFIFA", "KXCFB")),
    ("finance", ("KXWTI", "KXGOLD", "KXSILVER", "KXDIESEL", "KXAAAGAS", "KXINX", "KXNASDAQ", "KXDOW", "KXDJI", "KXUSD",
                 "KXEUR", "KXGBP", "KXJPY", "KXTNOTE", "KXSOFR", "KXFED", "KXCPI", "KXNATGAS", "KXCOPPER", "KXBRENT")),
)
CATEGORY_NAMES = ("crypto", "weather", "sports", "finance", "other")


def category(series: str | None) -> str:
    s = (series or "").upper()
    for name, prefixes in CATS:
        if s.startswith(prefixes):
            return name
    return "other"


_H = ("H = the recorder's own recorded minute quotes of this market with observed < observed_minute (one quote per "
      "market and minute bucket, first seen wins, recorded from every markets: snapshot as the lab's semantic_quotes; "
      "keep >= 4 h); mid of a quote = (bid+ask)/2")
_E = "E = earlier_quotes (oldest first; the last <= 4 recorded minute quotes before observed_minute)"
_CAT_TABLE = "; ".join(f"{name}: {', '.join(prefixes)}" for name, prefixes in CATS)
#: Every numeric feature a model file may name, with its canonical definition. The J1 analysis
#: (scripts in the Sept 25 run's scratchpad, `fit_final.py`) wrote these same strings into the model
#: files; `features` below is its pure-Python reference, ported line for line.
DEFINITIONS: dict[str, str] = {
    "mid": "(yes_bid+yes_ask)/2",
    "spread": "yes_ask-yes_bid",
    "log_oi": "log1p(max(0,open_interest))/15, 0 if missing",
    "hours": "min(max(hours_to_close,0),48)/48, 1 if missing",
    "drift": "mid minus the mid of earlier_quotes[0] (the oldest of up to four prior minute buckets), 0 if none",
    "absdrift": "abs(drift)",
    "ext": "abs(mid-0.5)*2",
    "lvol": "log1p(max(0,volume_24h))/15, 0 if missing",
    "lhrs": "log1p(max(hours_to_close,0))/log1p(720), not clamped, 1 if missing",
    "hres": "min(max(hours_to_resolve,0),48)/48, 1 if missing",
    "nhist": "len(earlier_quotes)/4",
    "chg4": (_E + "; S = [mid of each quote in E..., mid]; number of consecutive pairs in S whose values differ by "
             "more than 1e-9, divided by 4 (0 if E is empty)"),
    "rng4": _E + "; S = [mid of each quote in E..., mid]; max(S)-min(S)",
    "tchg": (_H + ". Walk H from its newest quote backwards while observed_minute-observed <= 14400 s; at the first "
             "quote whose mid differs by more than 1e-9 from the mid of the quote after it (the current mid for the newest "
             "quote), T = (observed_minute - observed of that later quote, or 0 if the later one is the current quote)/60. "
             "If no such quote is found, T = (observed_minute - observed of the oldest quote visited)/60, or 0 if none was "
             "visited. T = min(T,240). Feature = log1p(T)/log1p(240)"),
    "nochg": "1 if the tchg walk found no mid change (including an empty H), else 0",
    "rng60": _H + ". max-min of {mid of every quote in H with observed_minute-observed <= 3600 s} together with the current mid",
    "tight": "1 if spread <= 0.01+1e-9 else 0",
    "pinned": "1 if yes_bid <= 0.01+1e-9 or yes_ask >= 0.99-1e-9 else 0",
    **{f"cat_{c}": (f"1 if category(series) == '{c}' else 0; category = the first group whose prefix tuple "
                    f"series.upper() starts with, else 'other'. Groups: {_CAT_TABLE}") for c in CATEGORY_NAMES},
}


def numeric_spec(names: Iterable[str] | None = None) -> list[dict[str, str]]:
    """The `numeric` list a model file carries: each feature with its canonical definition."""
    return [{"name": name, "definition": DEFINITIONS[name]} for name in (names or DEFINITIONS)]


def _same_definition(a: Any, b: str) -> bool:
    return isinstance(a, str) and re.sub(r"\s+", "", a).lower() == re.sub(r"\s+", "", b).lower()


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def features(state: Mapping[str, Any], history: Sequence[Mapping[str, Any]] | None = None) -> dict[str, float] | None:
    """Every numeric feature of one lab state, or None where the model does not apply (no valid
    two-sided quote inside [0, 1], or the market at or after its close).

    `history` is the recorder's own minute quotes of THIS market ({observed, bid, ask}); only those
    strictly before `observed_minute` count, in any order. drift/nhist/chg4/rng4 read the state's
    `earlier_quotes` (the last <= 4 of that same history); tchg/nochg/rng60 read `history`. With
    history None the earlier quotes stand in (about 0.01 AUC worse in the analysis)."""
    m = state["market"]
    bid, ask = _num(m.get("yes_bid")), _num(m.get("yes_ask"))
    if bid is None or ask is None or not 0 <= bid <= ask <= 1:
        return None
    hours = _num(m.get("hours_to_close"))
    if hours is not None and hours <= 0:
        return None
    nb = int(state["observed_minute"])
    eq = sorted((float(q["observed"]), float(q["bid"]), float(q["ask"]))
                for q in (state.get("earlier_quotes") or []) if float(q["observed"]) < nb)[-4:]
    src = eq if history is None else [(float(q["observed"]), float(q["bid"]), float(q["ask"])) for q in history]
    hist = sorted(q for q in src if q[0] < nb)
    mid = (bid + ask) / 2
    spread = ask - bid
    oi = _num(m.get("open_interest"))
    vol = _num(m.get("volume_24h"))
    hres = _num(m.get("hours_to_resolve"))
    seq = [(q[1] + q[2]) / 2 for q in eq] + [mid]
    drift4 = mid - seq[0] if eq else 0.0
    chg4 = sum(1 for a, b in zip(seq, seq[1:]) if abs(a - b) > EPS)
    rng4 = max(seq) - min(seq)
    # Minutes since the mid last changed, looking back at most 240 minutes.
    tchg: float | None = None
    prev_mid, oldest = mid, nb
    j = len(hist) - 1
    while j >= 0 and nb - hist[j][0] <= 240 * 60:
        qm = (hist[j][1] + hist[j][2]) / 2
        if abs(qm - prev_mid) > EPS:
            later_t = hist[j + 1][0] if j + 1 < len(hist) else nb
            tchg = (nb - later_t) / 60
            break
        prev_mid, oldest = qm, hist[j][0]
        j -= 1
    nochg = 0.0
    if tchg is None:
        tchg, nochg = (nb - oldest) / 60, 1.0
    tchg = min(tchg, 240.0)
    w60 = [(q[1] + q[2]) / 2 for q in hist if nb - q[0] <= 3600] + [mid]
    cat = category(m.get("series"))
    x = {
        "mid": mid,
        "spread": spread,
        "log_oi": math.log1p(max(0.0, oi)) / 15 if oi is not None else 0.0,
        "hours": min(max(hours, 0.0), 48.0) / 48 if hours is not None else 1.0,
        "drift": drift4,
        "absdrift": abs(drift4),
        "ext": abs(mid - 0.5) * 2,
        "lvol": math.log1p(max(0.0, vol or 0.0)) / 15,
        "lhrs": math.log1p(max(hours, 0.0)) / math.log1p(720) if hours is not None else 1.0,
        "hres": min(max(hres, 0.0), 48.0) / 48 if hres is not None else 1.0,
        "nhist": len(eq) / 4,
        "chg4": chg4 / 4,
        "rng4": rng4,
        "tchg": math.log1p(tchg) / math.log1p(240),
        "nochg": nochg,
        "rng60": max(w60) - min(w60),
        "tight": 1.0 if spread <= 0.01 + EPS else 0.0,
        "pinned": 1.0 if (bid <= 0.01 + EPS or ask >= 0.99 - EPS) else 0.0,
    }
    for c in CATEGORY_NAMES:
        x["cat_" + c] = 1.0 if cat == c else 0.0
    return x


# --------------------------------------------------------------------------- the frozen models
def logistic(block: Mapping[str, Any], values: Mapping[str, float | None]) -> float | None:
    """p = 1 / (1 + exp(-clip(w0 + sum w_i (x_i - mean_i) / sd_i, -30, 30))); None if an input is missing."""
    score = block["weights"][0]
    for name, mean, sd, weight in zip(block["features"], block["mean"], block["sd"], block["weights"][1:]):
        value = values.get(name)
        if value is None or not math.isfinite(value):
            return None
        score += weight * (value - mean) / sd
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, score))))


def _block(raw: Any, allowed: set[str], where: str) -> dict[str, Any]:
    """One horizon's fitted block, checked: known features, matching lengths, finite numbers, sd > 0."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: not an object")
    names = raw.get("features")
    if not isinstance(names, list) or not all(isinstance(f, str) for f in names) or len(set(names)) != len(names):
        raise ValueError(f"{where}: features must be distinct names")
    unknown = [f for f in names if f not in allowed]
    if unknown:
        raise ValueError(f"{where}: unknown or undeclared feature {unknown[0]!r}")
    numbers = {key: raw.get(key) for key in ("mean", "sd", "weights")}
    for key, value in numbers.items():
        size = len(names) + (1 if key == "weights" else 0)
        if (not isinstance(value, list) or len(value) != size
                or not all(type(v) in (int, float) and math.isfinite(v) for v in value)):
            raise ValueError(f"{where}: {key} must be {size} finite numbers")
    if any(sd <= 0 for sd in numbers["sd"]):
        raise ValueError(f"{where}: every sd must be positive")
    return {"features": names, "mean": [float(v) for v in numbers["mean"]], "sd": [float(v) for v in numbers["sd"]],
            "weights": [float(v) for v in numbers["weights"]], "dev_auc": raw.get("dev_auc"),
            "dev_auc_numeric": raw.get("dev_auc_numeric")}


class MoveModel:
    """A frozen move model file. Loading never raises: what cannot be used is listed in `problems`.

    `horizons` are the model (`predict`); `numeric_only` its baseline (`baseline_p`). Every numeric
    feature a block uses must be declared in `numeric` with the canonical definition
    (`DEFINITIONS`); an unknown or differently defined numeric feature refuses the whole file. Its
    Jev features are lab questions named in `questions.per_market` (asked once per market) or
    `questions.per_state`. Its identity is (version, sha256 of the file): a model without a
    parseable `fitted_on.to` cannot be held out honestly and is refused; `fitted_on.events_sha256`
    lists the fit's events (sha256(event)[:16]), which evaluate never counts as unseen."""

    def __init__(self, data: Any, *, source: str = "", digest: str | None = None):
        self.source = source
        self.problems: list[str] = []
        self.digest = digest or hashlib.sha256(canonical(data).encode()).hexdigest()
        data = data if isinstance(data, dict) else {}
        self.version = str(data.get("version") or "unknown")
        self.fitted_on = dict(data["fitted_on"]) if isinstance(data.get("fitted_on"), dict) else {}
        self.placeholder = self.version == PLACEHOLDER or bool(self.fitted_on.get("placeholder"))
        self.fit_events = frozenset(str(e) for e in self.fitted_on.get("events_sha256") or ())
        try:
            self.fitted_to: float | None = parse_time(str(self.fitted_on["to"]))
        except (KeyError, ValueError, TypeError):
            self.fitted_to = None
        self.per_market: list[str] = []
        self.per_state: list[str] = []
        self.blocks: dict[int, dict[str, Any]] | None = None
        self.baseline: dict[int, dict[str, Any]] | None = None
        try:
            declared = set()
            for row in data.get("numeric") or ():
                name = row.get("name") if isinstance(row, dict) else None
                if name not in DEFINITIONS:
                    raise ValueError(f"numeric: unknown feature {name!r}")
                if not _same_definition(row.get("definition"), DEFINITIONS[name]):
                    raise ValueError(f"numeric: {name!r} is defined as {str(row.get('definition'))[:80]!r}, "
                                     f"not as the registry defines it")
                declared.add(name)
            asked = data.get("questions") or {}
            per_market, per_state = list(asked.get("per_market") or ()), list(asked.get("per_state") or ())
            unknown = [name for name in per_market + per_state if name not in FEATURES]
            if unknown or len(set(per_market + per_state)) != len(per_market + per_state):
                raise ValueError(f"questions must be distinct lab questions (unknown: {unknown[:1]})")
        except (ValueError, TypeError, AttributeError) as exc:
            self.problems.append(f"model refused: {exc}")
            return
        self.per_market, self.per_state = per_market, per_state
        try:
            self.baseline = {h: _block((data.get("numeric_only") or {}).get(str(h)), declared, f"numeric_only.{h}")
                             for h in HORIZONS}
        except (ValueError, KeyError, TypeError) as exc:
            self.problems.append(f"baseline refused: {exc}")
        try:
            allowed = declared | set(per_market) | set(per_state)
            self.blocks = {h: _block((data.get("horizons") or {}).get(str(h)), allowed, f"horizons.{h}") for h in HORIZONS}
        except (ValueError, KeyError, TypeError) as exc:
            self.problems.append(f"model refused: {exc}")
        if self.fitted_to is None and not self.placeholder:
            self.refuse("fitted_on.to is missing or unparseable: its held-out rows could not be told from its training rows")

    def refuse(self, reason: str) -> None:
        """No prediction and no baseline from this file."""
        self.problems.append(f"model refused: {reason}")
        self.blocks = self.baseline = None

    @classmethod
    def load(cls, path: str | Path) -> "MoveModel":
        try:
            raw = Path(path).read_bytes()
            data = json.loads(raw)
        except (OSError, ValueError) as exc:
            model = cls({}, source=str(path))
            model.problems = [f"model file unreadable: {type(exc).__name__}: {str(exc)[:120]}"]
            model.blocks = model.baseline = None
            return model
        return cls(data, source=str(path), digest=hashlib.sha256(raw).hexdigest())

    @property
    def ready(self) -> bool:
        return self.blocks is not None and not self.placeholder

    @property
    def questions(self) -> list[str]:
        return self.per_market + self.per_state

    @property
    def why_not(self) -> str:
        if self.placeholder:
            return f"placeholder model {self.version}"
        return next((p for p in self.problems if p.startswith(("model", "model file"))), "")

    def predict(self, values: Mapping[str, float | None]) -> dict[int, float | None]:
        return {h: logistic(self.blocks[h], values) if self.ready else None for h in HORIZONS}

    def baseline_p(self, values: Mapping[str, float | None]) -> dict[int, float | None]:
        return {h: logistic(self.baseline[h], values) if self.baseline is not None else None for h in HORIZONS}


# --------------------------------------------------------------------------- helpers
def event_of(market: str) -> str:
    """The event a Kalshi ticker belongs to: the ticker minus its last '-' segment (the lab's rule)."""
    return market.rsplit("-", 1)[0]


def _digest(value: Any, size: int = 16) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()[:size]


def _draw(market: str, minute: int) -> float:
    """A deterministic uniform draw for (market, minute): which states the per-state sample takes."""
    return int(hashlib.sha256(f"{market}:{minute}".encode()).hexdigest()[:12], 16) / float(16 ** 12)


def _iso(moment: float | None) -> str | None:
    if moment is None:
        return None
    return datetime.fromtimestamp(float(moment), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text: str) -> float:
    """An ISO timestamp (Z or offset; a bare date is midnight UTC) or epoch seconds."""
    try:
        return float(text)
    except ValueError:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()


P_COLUMNS = tuple(f"{kind}_p{h}" for kind in ("move", "numeric", "jev") for h in HORIZONS)
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS move_meta(name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS move_quotes(market TEXT NOT NULL, minute INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL,
    PRIMARY KEY(market, minute)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS move_quotes_minute ON move_quotes(minute);
CREATE TABLE IF NOT EXISTS move_rows(id INTEGER PRIMARY KEY, market TEXT NOT NULL, event TEXT NOT NULL, series TEXT,
    observed REAL NOT NULL, minute INTEGER NOT NULL, bid REAL NOT NULL, ask REAL NOT NULL, numeric TEXT NOT NULL,
    answers TEXT, {', '.join(f'{c} REAL' for c in P_COLUMNS)}, model_version TEXT NOT NULL, model_digest TEXT NOT NULL,
    shadow_version TEXT, shadow_digest TEXT, sampled INTEGER NOT NULL DEFAULT 0, snapshot INTEGER NOT NULL,
    recorded_at REAL NOT NULL, lag_seconds REAL NOT NULL, why TEXT,
    UNIQUE(market, snapshot, observed));  -- a replaced recordings store numbers its snapshots from 1 again
CREATE INDEX IF NOT EXISTS move_rows_market ON move_rows(market, recorded_at);
CREATE INDEX IF NOT EXISTS move_rows_market_observed ON move_rows(market, observed);
CREATE INDEX IF NOT EXISTS move_rows_observed ON move_rows(observed);
CREATE INDEX IF NOT EXISTS move_rows_event ON move_rows(event, observed);
CREATE TABLE IF NOT EXISTS move_markets(market TEXT PRIMARY KEY, last_row REAL NOT NULL);
CREATE INDEX IF NOT EXISTS move_markets_last ON move_markets(last_row);
CREATE TABLE IF NOT EXISTS move_models(version TEXT NOT NULL, digest TEXT NOT NULL, fitted_on TEXT NOT NULL,
    first_seen REAL NOT NULL, PRIMARY KEY(version, digest));
"""
#: What a cycle writes per row; `recorded_at` and `lag_seconds` (= recorded_at - observed) are added in the insert.
ROW_COLUMNS = ("market", "event", "series", "observed", "minute", "bid", "ask", "numeric", "answers", *P_COLUMNS,
               "model_version", "model_digest", "shadow_version", "shadow_digest", "sampled", "snapshot", "why")


@contextmanager
def _connect(path: Path, *, readonly: bool = False):
    if readonly:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    else:
        db = sqlite3.connect(path, timeout=30)
    try:
        if not readonly:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
        yield db
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- the recorder
class MoveSensor:
    """J1's recorder: point-in-time move features for every Kalshi market the House shows."""

    def __init__(self, root: str | Path, sensor: Any, *, clock: Callable[[], float] = time.time,
                 alert: Callable[[str, str], Any] | None = None, settings: Mapping[str, Any] | None = None,
                 model_path: str | Path | None = None, shadow_path: str | Path | None = None,
                 recordings: str | Path | None = None, closing: Callable[[], bool] | None = None):
        self.root = Path(root)
        self.sensor, self.clock = sensor, clock
        self._alert = alert
        self._closing = closing or (lambda: False)
        s = dict(settings or {})
        self.interval = float(s.get("interval_seconds", 300))
        self.max_markets = max(1, int(s.get("max_markets_per_cycle", 800)))
        self.retention_days = float(s.get("retention_days", 14))
        # Snapshots read a cycle for their quotes (streamed, oldest first; a larger backlog waits for the
        # next cycle); only those newer than two intervals also make rows.
        self.max_snapshots = max(1, int(s.get("max_snapshots_per_cycle", 1000)))
        self.workers = max(1, min(MAX_WORKERS, int(s.get("workers", MAX_WORKERS))))
        self.max_seconds = float(s.get("max_seconds_per_cycle", 60))
        self.max_static = max(0, int(s.get("max_static_per_cycle", 400)))
        self.min_free_bytes = int(s.get("min_free_bytes", MIN_FREE_BYTES))
        self.daily_usd = Decimal(str(s["daily_usd"])) if s.get("daily_usd") is not None else None
        self.new_markets_per_day = float(s.get("new_markets_per_day", DEFAULT_NEW_MARKETS_PER_DAY))
        self.recordings = Path(recordings) if recordings is not None else self.root / "recordings.sqlite"
        self.path = self.root / "jev-features.sqlite"
        self.served = MoveModel.load(s.get("model_path") or model_path or MODEL_PATH)
        self.shadow = MoveModel.load(s.get("shadow_model_path") or shadow_path or SHADOW_PATH)
        self.root.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            for model in (self.served, self.shadow):
                # A model's identity is (version, digest): the same version with other contents is refused.
                other = db.execute("SELECT digest FROM move_models WHERE version=? AND digest<>? LIMIT 1",
                                   (model.version, model.digest)).fetchone()
                if other is not None:
                    model.refuse(f"version {model.version} was recorded as {other[0][:12]}, this file is "
                                 f"{model.digest[:12]}: a changed model needs a new version")
                else:
                    # What `evaluate` needs to know of every model that wrote rows: its fitted_on.
                    db.execute("INSERT OR IGNORE INTO move_models VALUES(?,?,?,?)",
                               (model.version, model.digest, canonical(model.fitted_on), self.clock()))
        for model in (self.served, self.shadow):
            for problem in model.problems:
                self.alert("warning", f"jev move model ({model.source}): {problem}")
        if not self.served.ready:
            self.alert("warning", f"the served move model {self.served.version} is not ready "
                                  f"({self.served.why_not or 'no model'}): move_p stays null")
        # Static questions are about the contract's own text: bought once per market. The rest are
        # about one state: bought only for the sampled states, with the recorded-only pair.
        static = dict.fromkeys(self.served.per_market + self.shadow.per_market)
        per_state = dict.fromkeys(self.served.per_state + self.shadow.per_state)
        self.static = {name: LAB_QUESTIONS[name] for name in static}
        self.per_state = {**{name: LAB_QUESTIONS[name] for name in per_state if name not in static}, **RECORDED_ONLY}
        # The question-set versions are in the cache keys: a changed text is a new question.
        self._static_version, self._state_version = _digest(self.static, 10), _digest(self.per_state, 10)
        self._run_lock = threading.Lock()
        self._last_run = 0.0
        self._last_prune = 0.0
        self._last_error = ""
        self._deadline = float("inf")
        self._stats: dict[str, Any] = {}
        self._refresh_stats(None)

    # ------------------------------------------------------------------ plumbing
    def _db(self, *, readonly: bool = False):
        return _connect(self.path, readonly=readonly)

    def alert(self, level: str, text: str) -> None:
        if self._alert is not None:
            try:
                self._alert(level, text)
            except Exception:  # noqa: BLE001 - an alert that fails must not stop the recorder
                pass

    def _alert_once(self, text: str) -> None:
        """One alert per distinct trouble, not one every five minutes."""
        if text != self._last_error:
            self.alert("warning", text)
        self._last_error = text

    def _meta(self, db: sqlite3.Connection, name: str) -> str | None:
        row = db.execute("SELECT value FROM move_meta WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _set(db: sqlite3.Connection, **values: Any) -> None:
        db.executemany("INSERT INTO move_meta VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                       [(name, str(value)) for name, value in values.items()])

    def due(self) -> bool:
        return self.clock() - self._last_run >= self.interval

    def _stop(self) -> str:
        """Why no further ask may start this cycle, or ""."""
        try:
            if self._closing():
                return "the House is closing"
        except Exception:  # noqa: BLE001 - a broken probe must not keep asks running
            return "the House is closing"
        if time.monotonic() > self._deadline:
            return f"time budget: the cycle's {self.max_seconds:g} s are spent"
        return ""

    # ------------------------------------------------------------------ the cycle
    def run(self) -> dict[str, Any] | None:
        """One cycle. A failure is an alert and None, never an exception into the House."""
        if not self._run_lock.acquire(blocking=False):
            return None
        started, began = self.clock(), time.perf_counter()
        self._last_run = started
        self._deadline = time.monotonic() + self.max_seconds
        cycle: dict[str, Any] = {}
        failed = False
        try:
            cycle = self._cycle(started)
            if "refusal" not in cycle:
                self._last_error = ""
        except Exception as exc:  # noqa: BLE001 - the recorder is informational; the House goes on
            failed = True
            text = f"jev move sensor cycle failed ({type(exc).__name__}: {str(exc)[:160]})"
            self._alert_once(text)
            cycle = {"refusal": text}
        finally:
            try:
                cycle.update(at=started, seconds=round(time.perf_counter() - began, 3))
                self._refresh_stats(cycle)
            except Exception:  # noqa: BLE001
                pass
            self._run_lock.release()
        return None if failed else cycle

    def _today(self, db: sqlite3.Connection, now: float) -> dict[str, Any]:
        """This UTC day's counts of the recorder's own work (meta `today`), zeroed at a new day."""
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        tally = json.loads(self._meta(db, "today") or "{}")
        if tally.get("day") != day:
            tally = {"day": day, "calls": 0, "bought": 0, "cost_usd": "0", "static_asked": 0, "rows": 0, "move_rows": 0,
                     "jev_rows": 0, "sampled_rows": 0}
        return tally

    def _cycle(self, now: float) -> dict[str, Any]:
        free = shutil.disk_usage(self.root).free
        if free < self.min_free_bytes:
            text = (f"jev move sensor skipped its cycle: {free / 1024 ** 3:.1f} GB free, "
                    f"below {self.min_free_bytes / 1024 ** 3:.1f} GB")
            self._alert_once(text)
            return {"rows": 0, "refusal": text}
        read = self._read_snapshots(now)
        if isinstance(read, str):
            return {"rows": 0, "note": read}
        shown, cycle = read
        cycle["markets_shown"] = len(shown)
        rows, refusal, receipt = self._observe(shown, now) if shown else ([], "", {})
        with self._db() as db:
            # recorded_at is taken once this transaction holds the write lock; the commit follows
            # the inserts at once (see the module docstring).
            db.execute("BEGIN IMMEDIATE")
            recorded_at = self.clock()
            db.executemany(f"INSERT OR IGNORE INTO move_rows({','.join(ROW_COLUMNS)},recorded_at,lag_seconds) "
                           f"VALUES({','.join('?' * (len(ROW_COLUMNS) + 2))})",
                           [(*(row[c] for c in ROW_COLUMNS), recorded_at, round(recorded_at - row["observed"], 3)) for row in rows])
        counts = {"rows": len(rows), "move_rows": sum(r["move_p15"] is not None for r in rows),
                  "jev_rows": sum(r["jev_p15"] is not None for r in rows), "sampled_rows": sum(r["sampled"] for r in rows)}
        with self._db() as db:
            db.executemany("INSERT INTO move_markets VALUES(?,?) ON CONFLICT(market) DO UPDATE SET last_row=excluded.last_row",
                           [(row["market"], row["observed"]) for row in rows])
            tally = self._today(db, now)
            tally.update(calls=tally["calls"] + int(receipt.get("calls") or 0),
                         bought=tally["bought"] + int(receipt.get("bought") or 0),
                         static_asked=tally["static_asked"] + int(receipt.get("static") or 0),
                         cost_usd=format(Decimal(tally["cost_usd"]) + Decimal(str(receipt.get("cost") or 0)), "f"),
                         **{k: int(tally.get(k) or 0) + v for k, v in counts.items()})
            self._set(db, today=canonical(tally))
        cycle.update(counts, calls=int(receipt.get("calls") or 0), static_asked=int(receipt.get("static") or 0),
                     cost_usd=format(Decimal(str(receipt.get("cost") or 0)), "f"))
        if rows:
            lags = sorted(recorded_at - r["observed"] for r in rows)
            cycle["lag_seconds"] = {"p50": round(lags[len(lags) // 2], 1), "max": round(lags[-1], 1)}
        if refusal:
            cycle["refusal"] = refusal
        if now - self._last_prune >= 3600:
            self._last_prune = now
            cycle["pruned"] = self.prune(now)
        return cycle

    def _read_snapshots(self, now: float):
        """Every `markets:` snapshot past the cursor, oldest first, streamed and parsed one at a time,
        at most `max_snapshots` a cycle (a larger backlog is read next cycle: the cursor stops at the
        last one read). Returns (shown, counts) or a note.

        Every snapshot read gives its minute quotes (first seen in a minute wins), so the features'
        history keeps the lab's cadence even when this job waited behind the ops lane. Only snapshots
        newer than two intervals make rows: `shown` maps each market to its latest appearance among
        them, (snapshot id, received, market row, the first nine rows of its series in that snapshot,
        which is all `market_state` needs for eight peers). Older ones are `stale`, unreadable ones
        `corrupt`. The cursor moves with the last batch of quotes, whatever happens next."""
        if not self.recordings.exists():
            return "no market recordings yet"
        fresh_after = now - 2 * self.interval
        source = sqlite3.connect(self.recordings.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        shown: dict[str, tuple[int, float, dict[str, Any], list[dict[str, Any]]]] = {}
        batch: list[tuple[str, int, float, float]] = []
        read = corrupt = stale = 0
        try:
            newest = int(source.execute("SELECT COALESCE(MAX(id),0) FROM snapshots").fetchone()[0])
            with self._db() as db:
                cursor = self._meta(db, "cursor")
                if cursor is None or newest < int(cursor):
                    # First run, or a replaced recordings store: start at its newest snapshot. No back-fill.
                    note = "started" if cursor is None else "recordings replaced"
                    self._set(db, cursor=newest, **({"started_at": now, "started_cursor": newest} if cursor is None else {}))
                    return f"{note}: cursor at snapshot {newest}, nothing earlier is read"
            cursor = last = int(cursor)
            window = "id>? AND id<=? AND source LIKE 'markets:%'"
            for ident, received, payload in source.execute(
                    f"SELECT id, received, payload FROM snapshots WHERE {window} ORDER BY id LIMIT ?",
                    (cursor, newest, self.max_snapshots)):
                read, last = read + 1, int(ident)
                try:
                    markets = json.loads(gzip.decompress(payload))
                    valid = [m for m in markets if isinstance(m, dict) and isinstance(m.get("market"), str) and point(m)] \
                        if isinstance(markets, list) else []
                except Exception:  # noqa: BLE001 - zlib.error, RecursionError, anything: a corrupt snapshot is skipped
                    corrupt += 1
                    continue
                finally:
                    payload = None  # noqa: F841 - one payload in memory at a time
                bucket = int(float(received) // 60) * 60
                batch.extend((m["market"], bucket, point(m)["bid"], point(m)["ask"]) for m in valid)
                if float(received) < fresh_after:
                    stale += 1
                else:
                    series: dict[Any, list[dict[str, Any]]] = {}
                    for m in valid:
                        group = series.setdefault(m.get("series"), [])
                        if len(group) < 9:
                            group.append(m)
                    for m in valid:  # oldest first: the latest appearance wins
                        shown[m["market"]] = (int(ident), float(received), m, series[m.get("series")])
                if len(batch) >= 20_000:
                    self._keep_quotes(batch)  # oldest first, so INSERT OR IGNORE keeps the first in a minute
                    batch = []
            backlog = 0
            if read >= self.max_snapshots:
                backlog = int(source.execute(f"SELECT COUNT(*) FROM snapshots WHERE {window}", (last, newest)).fetchone()[0])
            end = last if backlog else newest
        finally:
            source.close()
        self._keep_quotes(batch, cursor=end)
        return shown, {"snapshots": read - corrupt, "stale_snapshots": stale, "corrupt_snapshots": corrupt,
                       "backlog_snapshots": backlog}

    def _keep_quotes(self, batch: list[tuple[str, int, float, float]], *, cursor: int | None = None) -> None:
        with self._db() as db:
            db.executemany("INSERT OR IGNORE INTO move_quotes VALUES(?,?,?,?)", batch)
            if cursor is not None:
                self._set(db, cursor=cursor)

    def _allowance(self, now: float, static_today: int) -> tuple[int, int, int]:
        """(static labels this cycle may buy, sampled states this cycle may buy, calls left today).

        The move budget is the tighter of the Sensor's call headroom and `daily_usd` (else the move
        call cap's share of the pool) at today's measured cost a call. Static labels come first, up
        to `max_static_per_cycle`: a market's jev_p needs them once. The rest of the day's static
        labels are reserved at today's measured rate of new markets (`new_markets_per_day` until an
        hour and 20 asks are measured); the per-state sample gets what that leaves, spread evenly over
        the cycles left in the UTC day and never more than twice an even share in one cycle."""
        left = int(self.sensor.headroom(PURPOSE))
        budget = self.daily_usd
        cap = getattr(self.sensor, "purpose_calls", {}).get(PURPOSE)
        if budget is None and cap is not None and getattr(self.sensor, "daily_calls", 0):
            budget = Decimal(self.sensor.daily_usd) * Decimal(int(cap)) / Decimal(int(self.sensor.daily_calls))
        spent, calls = Decimal(self.sensor.spent_today(PURPOSE)), int(self.sensor.calls_today(PURPOSE))
        per_call = max(spent / calls if calls >= 20 else DEFAULT_CALL_USD, Decimal("0.000001"))
        if budget is not None:
            left = min(left, max(0, int((budget - spent) / per_call)))
        day_start = int(now // 86400) * 86400
        day_end = day_start + 86400
        with self._db() as db:
            started = float(self._meta(db, "started_at") or day_start)
        watched = now - max(day_start, started)
        rate = static_today / watched if watched >= 3600 and static_today >= 20 else self.new_markets_per_day / 86400
        reserve = math.ceil(rate * (day_end - now))
        cycles_left = max(1, math.ceil((day_end - now) / max(1.0, self.interval)))
        even = max(0.0, calls + left - static_today - reserve) / max(1, math.ceil(86400 / max(1.0, self.interval)))
        sample = min(math.ceil(max(0, left - reserve) / cycles_left), math.ceil(2 * even))
        return min(left, self.max_static), sample, left

    def _observe(self, shown, now: float) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        """Rows for the chosen markets. Returns (rows, the first refusal, receipt)."""
        names = list(shown)
        with self._db() as db:
            last: dict[str, float] = {}
            for start in range(0, len(names), 500):
                chunk = names[start:start + 500]
                last.update(db.execute(f"SELECT market, last_row FROM move_markets WHERE market IN ({','.join('?' * len(chunk))})",
                                       chunk).fetchall())
            static_today = int(self._today(db, now).get("static_asked") or 0)
            # Never-recorded first, then the market recorded longest ago; ties to the most recently shown.
            chosen = sorted(names, key=lambda m: (last.get(m, 0.0), -shown[m][1], m))[:self.max_markets]
            states, feats = {}, {}
            for market in chosen:
                _, received, m, peers = shown[market]
                bucket = int(received // 60) * 60
                recent = [{"observed": float(o), "bid": b, "ask": a} for o, b, a in db.execute(
                    "SELECT minute, bid, ask FROM move_quotes WHERE market=? AND minute<? ORDER BY minute DESC LIMIT 244",
                    (market, bucket))]
                states[market] = market_state(m, peers, bucket, recent[:4][::-1])
                feats[market] = features(states[market], [q for q in recent if bucket - q["observed"] <= HISTORY_SECONDS])
        keys = {}
        for market in chosen:
            m = shown[market][2]
            static = _digest({k: m[k] for k in STATIC_FIELDS if k in m})
            keys[market] = {name: f"move:m:{self._static_version}:{market}:{static}:{name}" for name in self.static}
        known = self.sensor.cached([k for per in keys.values() for k in per.values()]) if self.static else {}
        static_limit, sample, left = self._allowance(now, static_today)
        # No ask for a market the models do not apply to (no two-sided quote, at or after close).
        usable = [m for m in chosen if feats[m] is not None]
        need = sorted((m for m in usable if any(k not in known for k in keys[m].values())), key=lambda m: (-shown[m][1], m))
        static_asks = need[:static_limit]
        sample = min(sample, max(0, left - len(static_asks)))
        sampled = set(sorted(usable, key=lambda m: (_draw(m, int(shown[m][1] // 60) * 60), m))[:sample])
        asks = {m: dict(self.static) for m in static_asks}
        for m in sampled:
            asks[m] = {**self.static, **self.per_state}
        results: dict[str, tuple[dict[str, float | None], str]] = {}
        receipt: dict[str, Any] = {"calls": 0, "cost": Decimal(0), "bought": 0, "static": len(static_asks)}
        lock = threading.Lock()

        def ask(market: str) -> None:
            stop = self._stop()
            if stop:
                results[market] = ({}, stop)
                return
            mine: dict[str, Any] = {}
            try:
                # The request may wait at most what the cycle has left, so a closing House is not held.
                answers = self.sensor.ask_state(PURPOSE, f"move:s:{self._state_version}:{_digest(states[market], 32)}",
                                                states[market], asks[market], receipt=mine, keys=keys[market],
                                                timeout=max(1.0, self._deadline - time.monotonic()))
            except Exception as exc:  # noqa: BLE001 - one market's failure is that row's null, not the cycle's
                answers, mine = {}, {"refused": f"{type(exc).__name__}: {str(exc)[:80]}"}
            with lock:
                receipt["calls"] += int(mine.get("calls") or 0)
                receipt["cost"] += Decimal(str(mine.get("cost") or 0))
                receipt["bought"] += int(mine.get("bought") or 0)
            results[market] = (answers, str(mine.get("refused") or ""))

        if asks:
            pool = ThreadPoolExecutor(max_workers=min(self.workers, len(asks)))
            try:
                pending = {pool.submit(ask, market) for market in [*static_asks, *(m for m in sampled if m not in static_asks)]}
                while pending:
                    _, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                    if pending and self._stop():
                        break  # the House is closing or the time is spent: queued asks never start
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
        stopped = self._stop()
        rows, refusal = [], ""
        for market in chosen:
            ident, received, m, _ = shown[market]
            x = feats[market]
            got, why = results.get(market, ({}, (stopped or "cancelled") if market in asks else ""))
            answers = {name: known.get(key) for name, key in keys[market].items()}
            answers.update({k: v for k, v in (got or {}).items() if v is not None})
            if market in sampled:
                answers.update({name: (got or {}).get(name) for name in self.per_state})
            reasons = []
            if x is None:
                reasons.append("the model does not apply: no two-sided quote in [0, 1], or at or after close")
                move = base = jev = dict.fromkeys(HORIZONS)
            else:
                values = {**x, **{k: v for k, v in answers.items() if v is not None}}
                move, base, jev = self.served.predict(values), self.served.baseline_p(x), self.shadow.predict(values)
                if move[15] is None:
                    reasons.append(f"served: {self.served.why_not or 'a model answer is missing'}")
                if jev[15] is None:
                    missing = [q for q in self.shadow.questions if answers.get(q) is None]
                    cause = self.shadow.why_not or (
                        f"jev: {why}" if why else "jev: paced: static labels wait for budget" if missing else "no answer")
                    reasons.append(f"shadow: {cause}")
                    if why and not refusal:
                        refusal = f"jev: {why}"
            q = point(m)
            row = {"market": market, "event": event_of(market), "series": m.get("series"), "observed": received,
                   "minute": int(received // 60) * 60, "bid": q["bid"], "ask": q["ask"],
                   "numeric": canonical({k: round(v, 9) for k, v in (x or {}).items()}),
                   "answers": canonical({k: (None if v is None else round(v, 6)) for k, v in answers.items()})
                   if any(v is not None for v in answers.values()) else None,
                   "model_version": self.served.version, "model_digest": self.served.digest,
                   "shadow_version": self.shadow.version, "shadow_digest": self.shadow.digest,
                   "sampled": int(market in sampled), "snapshot": ident, "why": "; ".join(reasons) or None}
            for kind, found in (("move", move), ("numeric", base), ("jev", jev)):
                for h in HORIZONS:
                    row[f"{kind}_p{h}"] = None if found[h] is None else round(found[h], 9)
            rows.append(row)
        return rows, refusal, receipt

    def prune(self, now: float | None = None) -> dict[str, int]:
        """Keep `retention_days` of quotes, rows and markets (each by an index); drop this sensor's
        cached Jev answers once they cannot recur (a state's after a day, a market's text after the
        retention); prune the Sensor's `calls` rows past its own keep."""
        now = self.clock() if now is None else now
        cutoff = now - self.retention_days * 86400
        with self._db() as db:
            out = {"quotes": db.execute("DELETE FROM move_quotes WHERE minute<?", (cutoff,)).rowcount,
                   "rows": db.execute("DELETE FROM move_rows WHERE observed<?", (cutoff,)).rowcount,
                   "markets": db.execute("DELETE FROM move_markets WHERE last_row<?", (cutoff,)).rowcount}
        forget = getattr(self.sensor, "forget", None)
        if callable(forget):
            out["answers"] = int(forget("move:s:", now - 86400)) + int(forget("move:m:", cutoff))
        prune_calls = getattr(self.sensor, "prune_calls", None)
        if callable(prune_calls):
            out["calls"] = int(prune_calls())
        return out

    # ------------------------------------------------------------------ reads
    def latest(self, market: str, at: float) -> dict[str, Any] | None:
        """The newest row for `market` that existed at `at` (recorded_at <= at): what a live wake
        or a replay at `at` may read. `age_seconds` is how old its observation is at `at`."""
        with self._db(readonly=True) as db:
            row = db.execute("SELECT move_p5, move_p15, move_p60, model_version, observed FROM move_rows "
                             "WHERE market=? AND recorded_at<=? ORDER BY recorded_at DESC, id DESC LIMIT 1",
                             (market, float(at))).fetchone()
        if row is None:
            return None
        return {"move_p5": row[0], "move_p15": row[1], "move_p60": row[2], "model_version": row[3],
                "age_seconds": round(float(at) - float(row[4]), 3)}

    def evaluate(self, cutoff: float, horizons: Sequence[int] = HORIZONS, **kw: Any) -> dict[str, Any]:
        return evaluate(self.path, cutoff, horizons, **kw)

    def _refresh_stats(self, cycle: dict[str, Any] | None) -> None:
        """Counted once a cycle, in the background job, so health.json never waits on the store."""
        with self._db() as db:
            rows = db.execute("SELECT COUNT(*) FROM move_rows").fetchone()[0]
            markets = db.execute("SELECT COUNT(*) FROM move_markets").fetchone()[0]
            today = json.loads(self._meta(db, "today") or "{}")
            started_at, cursor = self._meta(db, "started_at"), self._meta(db, "cursor")
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        if today.get("day") != day:
            today = {"day": day, "calls": 0, "bought": 0, "cost_usd": "0", "static_asked": 0, "rows": 0, "move_rows": 0,
                     "jev_rows": 0, "sampled_rows": 0}
        last = dict(cycle or self._stats.get("last_cycle") or {})
        self._stats = {"model_version": self.served.version, "model_ready": self.served.ready,
                       "shadow_version": self.shadow.version, "shadow_ready": self.shadow.ready,
                       "model_problems": list(self.served.problems) + list(self.shadow.problems),
                       "rows": int(rows), "markets": int(markets),
                       "started_at": _iso(float(started_at)) if started_at else None,
                       "cursor": int(cursor) if cursor is not None else None, "today": today,
                       "labels_bought_today": int(today.get("bought") or 0),
                       "last_cycle_at": _iso(last.get("at")), "last_cycle_seconds": last.get("seconds"),
                       "last_cycle": {k: v for k, v in last.items() if k not in ("at", "seconds")},
                       "refusal": last.get("refusal"), "interval_seconds": self.interval,
                       "max_markets_per_cycle": self.max_markets,
                       "daily_usd": format(self.daily_usd, "f") if self.daily_usd is not None else None,
                       "authority": "labels only: no order, promotion, spending or merge authority"}

    def stats(self) -> dict[str, Any]:
        return dict(self._stats)


# --------------------------------------------------------------------------- evaluation
class _Ranked:
    """Scores sorted once into tie groups of event indices, so a bootstrap resample's AUC is one
    weighted pass (events drawn with replacement are weights), not a sort per resample."""

    def __init__(self, scores: Sequence[float], labels: Sequence[int], events: Sequence[int]):
        order = sorted(range(len(scores)), key=scores.__getitem__)
        self.groups: list[tuple[list[int], list[int]]] = []
        last = None
        for i in order:
            if last is None or scores[i] != last:
                self.groups.append(([], []))
                last = scores[i]
            self.groups[-1][0 if labels[i] else 1].append(events[i])

    def auc(self, weights: Sequence[int] | None = None) -> float | None:
        below = numerator = positives = negatives = 0.0
        for pos, neg in self.groups:
            p = len(pos) if weights is None else sum(weights[e] for e in pos)
            n = len(neg) if weights is None else sum(weights[e] for e in neg)
            numerator += p * (below + 0.5 * n)
            below += n
            positives += p
            negatives += n
        return numerator / (positives * negatives) if positives and negatives else None


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _interval(draws: Sequence[float]) -> list[float] | None:
    return [round(_quantile(draws, 0.025), 4), round(_quantile(draws, 0.975), 4)] if draws else None


def _resamples(size: int, reps: int, seed: int):
    """Event weights for each bootstrap resample: events drawn with replacement, seeded."""
    rng = random.Random(seed)
    for _ in range(reps):
        weights = [0] * size
        for pick in rng.choices(range(size), k=size):
            weights[pick] += 1
        yield weights


def auc_with_interval(scores: Sequence[float], labels: Sequence[int], events: Sequence[str], *,
                      reps: int = 200, seed: int = 7) -> dict[str, Any]:
    """AUC (ties averaged) with a 95% event-clustered bootstrap interval (events resampled with replacement)."""
    index = {e: n for n, e in enumerate(dict.fromkeys(events))}
    ranked = _Ranked(scores, labels, [index[e] for e in events])
    estimate = ranked.auc()
    out: dict[str, Any] = {"auc": None if estimate is None else round(estimate, 4), "ci95": None,
                           "rows": len(scores), "events": len(index),
                           "base_rate": round(sum(labels) / len(labels), 4) if labels else None}
    if estimate is None or len(index) < 2 or reps <= 0:
        return out
    draws = [a for a in (ranked.auc(w) for w in _resamples(len(index), reps, seed)) if a is not None]
    out["ci95"] = _interval(draws)
    return out


def paired_auc(a: Sequence[float], b: Sequence[float], labels: Sequence[int], events: Sequence[str], *,
               names: tuple[str, str] = ("a", "b"), reps: int = 200, seed: int = 7) -> dict[str, Any]:
    """Two scores on the SAME rows, resampled together: each AUC and `difference` (first minus
    second), each with a 95% event-clustered interval."""
    index = {e: n for n, e in enumerate(dict.fromkeys(events))}
    ids = [index[e] for e in events]
    ra, rb = _Ranked(a, labels, ids), _Ranked(b, labels, ids)
    x, y = ra.auc(), rb.auc()
    out: dict[str, Any] = {"rows": len(labels), "events": len(index),
                           "base_rate": round(sum(labels) / len(labels), 4) if labels else None,
                           names[0]: {"auc": None if x is None else round(x, 4), "ci95": None},
                           names[1]: {"auc": None if y is None else round(y, 4), "ci95": None},
                           "difference": {"of": f"{names[0]} - {names[1]}",
                                          "diff": None if x is None or y is None else round(x - y, 4), "ci95": None}}
    if x is None or y is None or len(index) < 2 or reps <= 0:
        return out
    draws_a, draws_b, diffs = [], [], []
    for weights in _resamples(len(index), reps, seed):
        u, v = ra.auc(weights), rb.auc(weights)
        if u is not None and v is not None:
            draws_a.append(u)
            draws_b.append(v)
            diffs.append(u - v)
    out[names[0]]["ci95"], out[names[1]]["ci95"], out["difference"]["ci95"] = (
        _interval(draws_a), _interval(draws_b), _interval(diffs))
    return out


def _fit_summary(fitted_on: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if fitted_on is None:
        return None
    return {**{k: v for k, v in fitted_on.items() if k != "events_sha256"}, "events": len(fitted_on.get("events_sha256") or ())}


def evaluate(store: str | Path, cutoff: float, horizons: Iterable[int] = HORIZONS, *, reps: int = 200,
             seed: int = 7, fitted_on: Mapping[tuple[str, str], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Held-out evaluation of recorded rows observed at or after `cutoff`, read-only.

    It needs nothing but the store, opened read-only, so it can run on a copy (`sqlite3 SRC
    ".backup COPY"`, or the file with its -wal) off the House box. Rows are streamed once, ordered by
    market, with each market's quotes read once; what is kept per row is a few numbers in compact
    arrays, not the rows.

    - Outcome: the market's first own minute quote in [observed + h, observed + h + 10 min] whose
      minute is also strictly after the row's `recorded_at` (it must come after the row could be
      read). "Moves at all": |that mid - the row's mid| > 1e-9, the lab's target.
    - Groups: (served version, digest) with (shadow version, digest), never pooled. A cutoff earlier
      than the `fitted_on.to` of any model that wrote the rows (the store's `move_models`, or
      `fitted_on` keyed by (version, digest) here) is refused: rows before it may be training data.
    - Populations: every post-cutoff row; rows of `unseen_events`, observed neither before the
      cutoff in this store nor in the models' fit (`fitted_on.events_sha256`); rows read within two
      minutes (`lag_le_120s`: recorded_at - observed <= 120 s). Lag quantiles per group.
    - Scores: `served` (move_p, the free model), `shadow` (jev_p, free + static Jev answers),
      `baseline` (numeric_p, the lab's five features), the recorded-only answers; each alone on
      the rows that have it, and paired where they share rows: `served_vs_baseline`,
      `jev_increment` (AUC(jev_p) - AUC(move_p) on the same rows: does Jev add anything?) and each
      recorded-only answer against served. Seeded 95% event-clustered bootstrap intervals, overall
      and per coarse category."""
    from array import array
    from bisect import bisect_left, bisect_right

    path = Path(store)
    horizons = [int(h) for h in horizons]
    cutoff = float(cutoff)
    names = [f"{kind}_p{h}" for kind in ("move", "numeric", "jev") for h in HORIZONS]
    with _connect(path, readonly=True) as db:
        known = {(v, d): json.loads(f or "{}") for v, d, f in db.execute("SELECT version, digest, fitted_on FROM move_models")}
        known.update({tuple(k): dict(v) for k, v in (fitted_on or {}).items()})
        groups = [tuple(g) for g in db.execute("SELECT DISTINCT model_version, model_digest, shadow_version, shadow_digest "
                                              "FROM move_rows WHERE observed>=? ORDER BY 1, 2, 3, 4", (cutoff,))]
        for group in groups:
            for version, digest in (group[:2], group[2:]):
                to = (known.get((version, digest)) or {}).get("to") if version else None
                if to is not None and cutoff < parse_time(str(to)):
                    raise ValueError(f"cutoff {_iso(cutoff)} is before model {version}'s fitted_on.to {to}: "
                                     f"rows before it may be in its training data")
        index = {g: n for n, g in enumerate(groups)}
        fit = [frozenset((known.get(g[:2]) or {}).get("events_sha256") or ()) | frozenset((known.get(g[2:]) or {}).get("events_sha256") or ())
               for g in groups]
        seen = {e for (e,) in db.execute("SELECT DISTINCT event FROM move_rows WHERE observed<?", (cutoff,))}
        events: dict[str, int] = {}
        cols = {"group": array("i"), "event": array("i"), "category": array("b"), "unseen": array("b"), "lag": array("d")}
        scores = {name: array("d") for name in [*names, *RECORDED_ONLY]}
        outcome = {h: array("b") for h in horizons}
        market, minutes, quotes = None, [], []
        for row in db.execute(f"SELECT market, event, series, observed, bid, ask, recorded_at, sampled, answers, {', '.join(names)}, "
                              f"model_version, model_digest, shadow_version, shadow_digest FROM move_rows WHERE observed>=? "
                              f"ORDER BY market, observed", (cutoff,)):
            if row[0] != market:
                market = row[0]
                found = db.execute("SELECT minute, bid, ask FROM move_quotes WHERE market=? AND minute>=? ORDER BY minute",
                                   (market, row[3])).fetchall()
                minutes, quotes = [q[0] for q in found], [(q[1] + q[2]) / 2 for q in found]
            _, event, series, observed, bid, ask, recorded_at, sampled, answers = row[:9]
            g = index[tuple(row[-4:])]
            cols["group"].append(g)
            cols["event"].append(events.setdefault(event, len(events)))
            cols["category"].append(CATEGORY_NAMES.index(category(series or market.split("-", 1)[0])))
            cols["unseen"].append(int(event not in seen and hashlib.sha256(event.encode()).hexdigest()[:16] not in fit[g]))
            cols["lag"].append(float(recorded_at) - float(observed))
            for name, value in zip(names, row[9:9 + len(names)]):
                scores[name].append(math.nan if value is None else float(value))
            given = json.loads(answers) if sampled and answers else {}
            for name in RECORDED_ONLY:
                scores[name].append(math.nan if given.get(name) is None else float(given[name]))
            mid = (bid + ask) / 2
            for h in horizons:
                lo, hi = observed + 60 * h, observed + 60 * h + 600
                i = max(bisect_left(minutes, lo), bisect_right(minutes, recorded_at))
                outcome[h].append(-1 if i >= len(minutes) or minutes[i] > hi else int(abs(quotes[i] - mid) > 1e-9))
    count = len(cols["group"])

    def score(i: int, name: str, h: int) -> float | None:
        value = scores[name][i] if name in RECORDED_ONLY else scores[f"{name}_p{h}"][i] if f"{name}_p{h}" in scores else math.nan
        return None if math.isnan(value) else value

    def alone(rows: list[int], name: str, h: int) -> dict[str, Any]:
        found = [(score(i, name, h), outcome[h][i], cols["event"][i]) for i in rows if score(i, name, h) is not None]
        return (auc_with_interval(*zip(*found), reps=reps, seed=seed) if found
                else {"auc": None, "ci95": None, "rows": 0, "events": 0, "base_rate": None})

    def pair(rows: list[int], a: str, b: str, h: int, labels: tuple[str, str]) -> dict[str, Any]:
        found = [(score(i, a, h), score(i, b, h), outcome[h][i], cols["event"][i]) for i in rows
                 if score(i, a, h) is not None and score(i, b, h) is not None]
        if not found:
            return {"rows": 0, "events": 0, "base_rate": None, labels[0]: {"auc": None, "ci95": None},
                    labels[1]: {"auc": None, "ci95": None}, "difference": {"of": f"{labels[0]} - {labels[1]}", "diff": None, "ci95": None}}
        return paired_auc(*zip(*found), names=labels, reps=reps, seed=seed)

    def block(h: int, rows: list[int]) -> dict[str, Any]:
        out: dict[str, Any] = {"rows": len(rows), "events": len({cols["event"][i] for i in rows}),
                               "base_rate": round(sum(outcome[h][i] for i in rows) / len(rows), 4) if rows else None,
                               "served": alone(rows, "move", h), "shadow": alone(rows, "jev", h),
                               "baseline": alone(rows, "numeric", h),
                               "served_vs_baseline": pair(rows, "move", "numeric", h, ("served", "baseline")),
                               "jev_increment": pair(rows, "jev", "move", h, ("shadow", "served")),
                               "recorded_only": {name: {"alone": alone(rows, name, h),
                                                        "vs_served": pair(rows, name, "move", h, (name, "served"))}
                                                 for name in RECORDED_ONLY}}
        served = out["served"]["auc"]
        out["meets_ship_rule"] = None if served is None else served >= SHIP_AUC
        return out

    report: dict[str, Any] = {
        "store": str(path), "cutoff": _iso(cutoff), "rows_after_cutoff": count,
        "target": "the quoted midpoint moves at all (|change| > 1e-9); outcome quote after observed + h and after recorded_at",
        "ship_rule": f"the served move_p AUC >= {SHIP_AUC} on unseen events after a post-ship cutoff",
        "scores": {"served": "move_p: the free model (no Jev), what latest() serves",
                   "shadow": "jev_p: the free features plus the six static Jev answers, recorded only",
                   "baseline": "numeric_p: the lab's five numeric features",
                   "jev_increment": "shadow minus served on the same rows: whether Jev adds anything",
                   "recorded_only": "the moves_15m / moves_60m answers on the sampled states"},
        "populations": {"all_after_cutoff": "every row observed at or after the cutoff",
                        "unseen_events": "rows of events neither observed before the cutoff in this store nor in the fit",
                        "lag_le_120s": "rows written within 120 s of their observation"},
        "models": {}}
    for g, (mv, md, sv, sd) in enumerate(groups):
        mine = [i for i in range(count) if cols["group"][i] == g]
        lags = sorted(cols["lag"][i] for i in mine)
        quantile = (lambda q: round(_quantile(lags, q), 1)) if lags else (lambda q: None)
        entry: dict[str, Any] = {
            "served": {"version": mv, "digest": md, "fitted_on": _fit_summary(known.get((mv, md)))},
            "shadow": {"version": sv, "digest": sd, "fitted_on": _fit_summary(known.get((sv, sd)))} if sv else None,
            "lag_seconds": {"p50": quantile(0.5), "p90": quantile(0.9), "p99": quantile(0.99),
                            "max": round(lags[-1], 1) if lags else None,
                            "share_le_120s": round(sum(v <= 120 for v in lags) / len(lags), 4) if lags else None},
            "populations": {}}
        for population, keep in (("all_after_cutoff", lambda i: True), ("unseen_events", lambda i: cols["unseen"][i] == 1),
                                 ("lag_le_120s", lambda i: cols["lag"][i] <= 120)):
            found: dict[str, Any] = {}
            for h in horizons:
                kept = [i for i in mine if outcome[h][i] >= 0 and keep(i)]
                by: dict[str, list[int]] = {}
                for i in kept:
                    by.setdefault(CATEGORY_NAMES[cols["category"][i]], []).append(i)
                found[str(h)] = {"overall": block(h, kept), "by_category": {k: block(h, v) for k, v in sorted(by.items())}}
            entry["populations"][population] = found
        report["models"][f"{mv}@{md[:12]}" + (f" / {sv}@{sd[:12]}" if sv else "")] = entry
    return report


def _print(report: Mapping[str, Any], out: Any) -> None:
    print(f"{report['store']}: {report['rows_after_cutoff']} rows observed at or after {report['cutoff']}. "
          f"{report['ship_rule']}.", file=out)

    def cell(entry: Mapping[str, Any]) -> str:
        if entry.get("auc") is None:
            return "-"
        ci = entry.get("ci95")
        return f"{entry['auc']:.3f}" + (f" [{ci[0]:.3f},{ci[1]:.3f}]" if ci else "")

    def diff(entry: Mapping[str, Any]) -> str:
        d = entry["difference"]
        if d["diff"] is None:
            return "-"
        return f"{d['diff']:+.3f}" + (f" [{d['ci95'][0]:+.3f},{d['ci95'][1]:+.3f}]" if d["ci95"] else "") + f" n={entry['rows']}"

    for key, entry in report["models"].items():
        print(f"\nmodels {key}; fit {canonical(entry['served']['fitted_on'] or {})}; lag {canonical(entry['lag_seconds'])}", file=out)
        for population, found in entry["populations"].items():
            for h, blocks in found.items():
                print(f"  {population}, {h} min", file=out)
                for label, b in [("overall", blocks["overall"]), *blocks["by_category"].items()]:
                    moves = "  ".join(f"{k}={cell(v['alone'])}" for k, v in b["recorded_only"].items())
                    print(f"    {label:9s} rows={b['rows']} events={b['events']} base={b['base_rate']} | "
                          f"served={cell(b['served'])} shadow={cell(b['shadow'])} baseline={cell(b['baseline'])} | "
                          f"jev increment={diff(b['jev_increment'])} served-baseline={diff(b['served_vs_baseline'])} | "
                          f"{moves}", file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.jev_features", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    ev = commands.add_parser("evaluate", help="held-out AUC of the recorded move feature (read-only)")
    ev.add_argument("--store", required=True, help="jev-features.sqlite (opened read-only)")
    ev.add_argument("--cutoff", required=True, help="ISO time (or epoch seconds): only rows observed at or after it")
    ev.add_argument("--horizons", default="5,15,60")
    ev.add_argument("--reps", type=int, default=200, help="bootstrap resamples")
    ev.add_argument("--seed", type=int, default=7)
    ev.add_argument("--model", action="append", default=[],
                    help="a model file whose fitted_on to use for its (version, digest) (repeatable; the store keeps its own)")
    ev.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    fitted = {}
    for path in args.model:
        model = MoveModel.load(path)
        fitted[(model.version, model.digest)] = model.fitted_on
    try:
        report = evaluate(args.store, parse_time(args.cutoff), [int(h) for h in args.horizons.split(",") if h.strip()],
                          reps=args.reps, seed=args.seed, fitted_on=fitted)
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print(report, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
