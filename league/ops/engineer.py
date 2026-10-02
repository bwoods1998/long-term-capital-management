"""The `engineer` job (LTCM v3, Phase 4, B5): the harness improves itself inside its walls, with no human step.

One candidate at a time walks the loop of `playbooks/harness-improvement.md` on the House, each step a receipt in the
journal `<state>/harness/engineer.sqlite` (mode 0600):

1. PICK (the daily occurrence, 04:00Z, after the scoreboard; only when no candidate is in flight or reverting, none was
   authored today, New York's day, the gateway's /v1/health shows the engineer's pull requests with room today, and the
   engineer's and the reviewer's Claude together have an attempt's cap left of `usd_day`). The lanes' measurement: the
   supervised observer's `<state>/harness/lanes-ranked.json` and `lanes-measurement.json` when they are fresh and of the
   running release, else the job measures the last day itself, read-only (`harness_lanes.measure`, `rank`). The top
   CAPTURED bottleneck of an engineer lane (research, memory, data: the research-class lanes the gateway's engineer role
   may write; execution is an evidence reset, never this path) that is not cooling down. Its predeclared metric is the
   lane's primary metric and `min_effect`, frozen in the journal with the lane's hash (`lane_sha`), the capture's
   population and its motivating units.
2. AUTHOR (`league/ops/author.py`). The base is the running release's commit: the updater's attested sha for it in
   `<base>/deploys.jsonl` (an owner deploy's: the observer policy's `base` when its digest is this release's), fetched
   as a codeload tarball as the updater does and checked against the running tree's digest. Claude Opus 5.5 (role
   `engineer`, effort high, at most $3 an attempt) edits it through confined tools; the static guards run git-free.
3. PULL REQUEST through the gateway (`POST /v1/github/pr`, role `engineer`, the lane named): the measurement, the
   metric, the predicted effect and the canary plan in its body. First `main`'s head is read: when it is not the base,
   each file the candidate touches must read on `main` as it does in the base (else the full-file proposal would undo
   `main`'s change), or the candidate is dropped.
4. CI (`GET /v1/github/pr/<n>`), then THE REVIEWER (`league/ops/reviewer.py`; Opus 5.5, at most $1; two for a money-path
   candidate) on the exact diff between the pull request's head and the `main` it was cut from, verdict posted to
   `POST /v1/github/review`. A CI failure or a reject goes back to the engineer ONCE (a revision: a new pull request);
   a second is final.
5. MERGE (`POST /v1/github/merge`, exact head). A window-lane candidate merges only once its control window (the
   observation length before the deploy) can lie wholly after the capture's window.
6. DEPLOY: the updater ships `main` at its train; the job sees the running release carry the candidate's inserted code.
7. CANARY. Arms lanes (research, memory): the arm `{lane, fraction, salt, state: canary, since}` goes into
   `<state>/harness/canary.json` (merged with the arms already there, atomically, mode 0600). The window lane (data):
   the control is measured now, the observation length before the release's promotion. A money-path gate starts and
   is retained only outside New York's session.
8. RETAIN OR REVERT, once, after the window ends, on a read-only measurement of exactly that window
   (`harness_lanes.retention`, motivating units excluded; another release promoted or started inside the window, or a
   changed lane definition, voids it). Retained: the gate says `retained`. Anything else (reverted, too little activity,
   voided, a watchdog rollback, never deployed) fails closed: the gate flips to `reverted` and a REVERT pull request
   (each touched file put back as it was, against `main` as it is now) goes through the same route, its review
   mechanical (code checks the exact bytes), then the merge.
9. THE GLOBAL GUARD: for `guard_sessions` (20) sessions after retention, the forward record (shadow and real) of the
   promoted programs (bands probe and sized, or any family with real trades) must not fall below its record over the
   same number of sessions before the canary: a one-sided test at 10% on per-trade P&L per dollar of maximum loss, with
   at least `GUARD_MIN_TRADES` trades on each side. A breach reverts the change, however late.

THE HELD-OUT JUDGE on the House is the canary window's data: units and sessions the author never saw. The laptop's
held-out pools stay where they are. Every step's spend goes through the swarm's `ModelRouter` (roles `engineer` and
`reviewer`: their `claude.role_usd_day` lines, which the budget may only tighten). Off unless the swarm's settings say
`engineer.enabled` true; the roles must also be in `claude.roles`.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import shutil
import sqlite3
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import schedule as S
from .author import NEW_TEST, Outcome, Workspace, is_new_test, run_loop, sha256, static_guards, writable_paths
from .context import GatewayError, read_json, write_json

FILE = Path("harness") / "engineer.sqlite"
WORK = Path("harness") / "engineer"
CANARY = Path("harness") / "canary.json"
RANKED = Path("harness") / "lanes-ranked.json"
MEASUREMENT = Path("harness") / "lanes-measurement.json"
RUNTIME = Path("harness") / "runtime.json"
ENGINEER_LANES = ("research", "memory", "data")
#: The daily occurrence (UTC) that may author; every other occurrence only moves the candidates along.
AUTHOR_AT = (4, 0)
#: Hard caps whatever the settings say: an authoring attempt, a review.
AUTHOR_USD_CAP, REVIEW_USD_CAP = 3.0, 1.0
LANES_WINDOW = 86400
ALPHA = 0.05
GUARD_Z = 1.2816  # one-sided 10%
GUARD_MIN_TRADES = 10
DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "lanes": list(ENGINEER_LANES),
    "author_usd": AUTHOR_USD_CAP,
    "review_usd": REVIEW_USD_CAP,
    "max_turns": 24,
    "author_minutes": 30,
    "effort": "high",
    "review_effort": "high",
    "max_tokens": 16000,
    "keep_usd": 5.0,
    # The engineer's and the reviewer's Claude together, a UTC day (holds included, `claude_spent`): an attempt is
    # capped at what is left, and no attempt or review starts with less than its own cap left.
    "usd_day": 10.0,
    "ranked_max_age_hours": 36,
    "cooldown_hours": 72,
    "attempts_per_base": 3,
    "pr_pending_hours": 72,
    "ci_hours": 6,
    "review_hours": 24,
    "deploy_days": 7,
    "guard_sessions": 20,
}
OPEN_STATES = ("pr_pending", "pr_open", "revise", "merged", "canary", "retained", "reverting")
#: At most one candidate in flight: authored and not yet decided. A retained change under the global guard does not hold
#: the next one back.
IN_FLIGHT = ("pr_pending", "pr_open", "revise", "merged", "canary")
#: What holds authoring: a candidate in flight, or a revert not yet merged (a new candidate cut from a base that still
#: carries the change could lean on code the revert takes out, and CI judges only its head, not main after both merge).
HOLDS_AUTHORING = IN_FLIGHT + ("reverting",)
SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL UNIQUE, lane TEXT NOT NULL, metric TEXT NOT NULL,
    state TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, ny_day TEXT NOT NULL, base_sha TEXT,
    release TEXT, record TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
SHA40 = re.compile(r"[0-9a-f]{40}")
UTC = timezone.utc


def ny_day(moment: float) -> str:
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(moment, ZoneInfo("America/New_York")).date().isoformat()


# ------------------------------------------------------------------------------------------------ the journal
class Journal:
    """`<state>/harness/engineer.sqlite`: a candidate row each (its whole record as JSON) and an event per step."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / FILE
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        self.db = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def create(self, key: str, lane: str, metric: str, *, at: float, base_sha: str, release: str,
               record: Mapping[str, Any], state: str = "authoring") -> dict[str, Any]:
        self.db.execute("INSERT INTO candidates(key, lane, metric, state, created_at, updated_at, ny_day, base_sha, release, "
                        "record) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (key, lane, metric, state, at, at, ny_day(at), base_sha, release, json.dumps(record, default=str)))
        self.event(key, at, "created", {"lane": lane, "metric": metric, "base": base_sha, "release": release})
        return self.get(key)  # type: ignore[return-value]

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM candidates WHERE key=?", (key,)).fetchone()
        return None if row is None else self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        out["record"] = json.loads(out["record"] or "{}")
        return out

    def save(self, cand: Mapping[str, Any], *, at: float, state: str | None = None, kind: str | None = None,
             detail: Mapping[str, Any] | None = None) -> dict[str, Any]:
        new = state or cand["state"]
        self.db.execute("UPDATE candidates SET state=?, updated_at=?, record=? WHERE key=?",
                        (new, at, json.dumps(cand["record"], default=str), cand["key"]))
        if kind or new != cand["state"]:
            self.event(cand["key"], at, kind or new, {"from": cand["state"], "to": new, **dict(detail or {})})
        return self.get(cand["key"])  # type: ignore[return-value]

    def event(self, key: str | None, at: float, kind: str, detail: Mapping[str, Any] | None = None) -> None:
        self.db.execute("INSERT INTO events(key, at, kind, detail) VALUES(?,?,?,?)",
                        (key, at, kind, json.dumps(dict(detail or {}), default=str)[:20_000]))

    def open(self) -> list[dict[str, Any]]:
        return [self._row(r) for r in self.db.execute(
            f"SELECT * FROM candidates WHERE state IN ({','.join('?' * len(OPEN_STATES))}) ORDER BY id", OPEN_STATES)]

    def all(self) -> list[dict[str, Any]]:
        return [self._row(r) for r in self.db.execute("SELECT * FROM candidates ORDER BY id")]

    def authored_on(self, day: str) -> bool:
        return self.db.execute("SELECT 1 FROM candidates WHERE ny_day=? LIMIT 1", (day,)).fetchone() is not None

    def events(self, key: str | None = None) -> list[dict[str, Any]]:
        rows = (self.db.execute("SELECT * FROM events WHERE key=? ORDER BY seq", (key,)) if key else
                self.db.execute("SELECT * FROM events ORDER BY seq"))
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]


# ------------------------------------------------------------------------------------------------ the base
def deploy_rows(base: str | Path) -> list[dict[str, Any]]:
    out = []
    try:
        with (Path(base) / "deploys.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def attested_sha(rows: Iterable[Mapping[str, Any]], release: str) -> str | None:
    """The commit the updater attested for `release` and the watchdog promoted (its `promote` ok or `promoted` verdict
    row carries the sha), the newest such deploy; None for an owner deploy (no attestation)."""
    found = None
    for row in rows:
        if row.get("release") != release or not SHA40.fullmatch(str(row.get("sha") or "")):
            continue
        if (row.get("stage") == "promote" and row.get("ok") is True) or (
                row.get("stage") == "verdict" and row.get("verdict") == "promoted"):
            found = str(row["sha"])
    return found


def deploy_window(rows: Sequence[Mapping[str, Any]], release: str) -> tuple[float | None, float | None]:
    """(when the deploy that last promoted `release` began, when it was promoted), from the watchdog's rows."""
    promoted, deploy = None, None
    for row in rows:
        if row.get("release") == release and ((row.get("stage") == "promote" and row.get("ok") is True) or (
                row.get("stage") == "verdict" and row.get("verdict") == "promoted")):
            promoted, deploy = S.epoch(row.get("at")) or promoted, row.get("deploy") or deploy
    if promoted is None:
        return None, None
    began = [S.epoch(r.get("at")) for r in rows if deploy is not None and r.get("deploy") == deploy]
    began = [b for b in began if b is not None]
    return (min(began) if began else promoted), promoted


def segments(before: str | None, after: str) -> list[tuple[str, str]]:
    """The candidate's hunks as (old text, new text) pairs of whole lines, from the base to the candidate."""
    import difflib

    old = (before or "").splitlines(keepends=True)
    new = after.splitlines(keepends=True)
    return [("".join(old[i1:i2]), "".join(new[j1:j2]))
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if tag != "equal"]


def _marks(before: str | None, after: str) -> list[str]:
    """The hunks' new texts the base does not already hold: what tells the candidate's code apart."""
    return [new for _, new in segments(before, after) if new.strip() and new not in (before or "")]


def carries(before: str | None, after: str, text: str | None) -> bool:
    """Whether `text` (a file of the running release) carries the candidate's change: every hunk's new text the base
    does not hold is in it; a change with no such hunk (it only deletes) only when `text` is the candidate's."""
    if text is None:
        return False
    marks = _marks(before, after)
    return all(seg in text for seg in marks) if marks else text == after


def revert_text(before: str | None, after: str, current: str | None) -> str | None:
    """`current` (the file on `main` now) with the candidate's change taken out, a line-level three-way revert: the
    base text when `main` still reads as the candidate; `current` itself when `main` holds none of the candidate's new
    lines any more; otherwise each hunk of candidate -> base applied where the candidate's lines still stand, together,
    in `current`. None when a hunk's lines were changed on `main` (it cannot be taken out exactly)."""
    import difflib

    if current is None:
        return None
    if current == after:
        return before
    base_lines = set((before or "").splitlines())
    marks = {line for seg in _marks(before, after) for line in seg.splitlines() if line.strip() and line not in base_lines}
    if marks and not marks & set(current.splitlines()):
        return current
    a = after.splitlines(keepends=True)
    b = (before or "").splitlines(keepends=True)
    c = current.splitlines(keepends=True)
    where: dict[int, int] = {}
    for i, j, size in difflib.SequenceMatcher(None, a, c, autojunk=False).get_matching_blocks():
        for k in range(size):
            where[i + k] = j + k
    edits = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            spots = [where.get(k) for k in range(i1, i2)]
            if None in spots or spots != list(range(spots[0], spots[0] + len(spots))):
                return None
            lo, hi = spots[0], spots[-1] + 1
        elif i1 > 0 and i1 - 1 in where:
            lo = hi = where[i1 - 1] + 1
        elif i1 in where:
            lo = hi = where[i1]
        elif i1 == 0:
            lo = hi = 0
        else:
            return None
        edits.append((lo, hi, b[j1:j2]))
    for lo, hi, lines in sorted(edits, reverse=True):
        c[lo:hi] = lines
    return "".join(c)


# ------------------------------------------------------------------------------------------------ model-safe text
def scrub_examples(lane: str, examples: Sequence[Mapping[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    """The capture's examples as the brief may show them: error shapes and counts, never a family or box id, a date or
    a figure of a run."""
    out = []
    for row in list(examples)[:limit]:
        if lane in ("research", "data"):
            item = {"signature": str(row.get("signature") or "")[:160], "count": row.get("n")}
            if lane == "data" and row.get("slots") is not None:
                item["job_slots"] = row.get("slots")
        else:
            text = " ".join(str(row.get("mechanism") or "").split())[:160]
            for ident in (row.get("family"), row.get("graveyard_row"), row.get("unit")):
                if ident:
                    text = text.replace(str(ident), "<family>")
            item = {"structure": str(row.get("structure") or ""), "similarity_to_a_buried_mechanism": row.get("similarity"),
                    "mechanism": text}
        out.append(item)
    return out


def _ascii(text: Any) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


AUTHOR_SYSTEM = """You are the engineer of an autonomous options-research swarm's harness. You change the harness's own code
to remove one measured operational bottleneck, inside hard walls, and nothing else. You work in a copy of the public
repository through tools. You never see trading results, and you must never make a model-facing text carry an
evaluation figure.

How to work:
1. Read the brief: the lane, the bottleneck and its predeclared metric, the files you may change, the gate rule.
2. Read the code that produces the bottleneck (read_file, grep). Find the cause before you write.
3. Make the smallest change that removes the cause, with edit_file (exact, unique replacements). Optionally add one
   small new test file named league/tests/test_harness_candidate_<name>.py that pins the new behaviour.
4. Run check, fix every problem it names, then call finish with a one-line title, a summary, the predicted effect on
   the metric and what the canary should show. If no change inside the rules can move the metric, call give_up.

The walls (the static guards enforce them; a reviewer and CI check again):
- Change only the listed files. Never import os, subprocess, shutil, socket, pathlib, io, logging, tempfile, importlib
  or ctypes anew, never write files, open processes or connections, use reflection, or touch the swarm's store writers,
  its settings, the evaluator, the gate or the bands. Never change a trial count, a lineage, an eligibility mark or a
  receipt by any route.
- In an arms lane every change sits in `if canary.enabled("KEY", unit, root=...): <new> else: <old>` where <old> is the
  existing code byte for byte, so with the gate closed the module runs exactly as before. New helper functions and
  constants under new names are allowed. Import the gate as `from league.swarm import canary` (or the module's existing
  relative style) only if the file does not have it.
- Keep the code in the surrounding style. Small, explicit, correct."""


def brief(*, lane: str, row: Mapping[str, Any], key: str, examples: Sequence[Mapping[str, Any]],
          feedback: Sequence[str] = (), revision: bool = False) -> str:
    """The author's first message (model-safe: no Validation or holdout figure, no family name, no date)."""
    from ..swarm import harness_lanes as lanes

    spec = lanes.LANES[lane]
    bottleneck = spec.bottleneck(str(row["metric"]))
    m = bottleneck.metric
    canary = spec.canary_for(bottleneck)
    value = row.get("value")
    lines = [f"LANE: {spec.id} ({spec.title})",
             f"BOTTLENECK: {bottleneck.summary}",
             f"METRIC: {m.name} = {m.numerator} / {m.denominator}; {m.direction} is better. Measured over the last day: "
             f"{value if value is None else round(float(value), 4)} over {row.get('denominator')} {m.denominator} "
             f"(a bottleneck from {m.threshold}). The change is kept only if a concurrent canary shows a relative "
             f"improvement of at least {m.min_effect:.0%} with p <= {ALPHA}, and nothing below worsens:",
             "  " + (", ".join(x.name for x in list(bottleneck.secondary) + list(spec.guards)) or "(none)"),
             f"FILES YOU MAY CHANGE: {', '.join(writable_paths(lane))}; and one new test file {NEW_TEST} (the * of "
             "lower-case letters, digits and underscores only)."]
    if canary.get("mode") == "arms":
        unit = ('the family id: a name for it such as fam["id"]' if canary.get("unit") == "family" else
                "canary.mechanism_unit(mechanism) of the text Architect.admit admits, asked inside Architect.admit (a "
                "per-pass prompt cannot be gated per mechanism)")
        lines += [f"GATE KEY: {key}",
                  f"Every change must sit under canary.enabled({key!r}, <unit>, root=<the swarm's state directory, e.g. "
                  f"self.store.root>) with <unit> = {unit}; the else branch is the existing code unchanged. The canary "
                  f"gives the new behaviour to {float(canary.get('fraction', 0.5)):.0%} of units for "
                  f"{int(canary.get('observe_seconds', 0)) // 3600} hours against the rest."]
    else:
        lines.append(f"CANARY: the {int(canary.get('observe_seconds', 0)) // 3600} hours after the release against the same "
                     "length before it (no gate).")
    shown = scrub_examples(lane, examples)
    if shown:
        lines.append("EXAMPLES FROM THE MEASUREMENT (shapes and counts):")
        lines += ["  " + json.dumps(e, sort_keys=True) for e in shown]
    if revision:
        lines.append("REVISION: your previous change is already applied in the tree. It came back with these findings; "
                     "address every one, then check and finish again:")
        lines += ["  - " + " ".join(str(f).split())[:900] for f in list(feedback)[:16]]
    return _ascii("\n".join(lines))


#: What a public pull request may never carry (account figures, contract symbols, box ids, secrets).
PUBLIC_FORBIDDEN = (
    re.compile(r"\b[A-Z]{1,6}\d{6}[CP]\d{8}\b"), re.compile(r"\bsb(?:cp)?_[0-9a-fA-F-]{6,}"),
    re.compile(r"\bequity\b", re.I), re.compile(r"\bbalances?\b", re.I), re.compile(r"buying\s+power", re.I),
    re.compile(r"\bholdout\b", re.I),
)
SECRETISH = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")


def public_problems(text: str) -> list[str]:
    found = [p.pattern for p in PUBLIC_FORBIDDEN if p.search(text)]
    found += [t[:12] + "..." for t in SECRETISH.findall(text) if not SHA40.fullmatch(t) and not t.startswith("harness")][:3]
    return found


def _public(text: str) -> str:
    return text if not public_problems(text) else "(withheld: the text did not pass the public filter)"


# ------------------------------------------------------------------------------------------------ the forward guard
def trading_days(start: date, end: date) -> list[str]:
    """New York trading days in [start, end]."""
    from ltcm.data import DataError, us_equity_session

    out, day = [], start
    while day <= end:
        try:
            if us_equity_session(day) is not None:
                out.append(day.isoformat())
        except DataError:
            pass
        day += timedelta(days=1)
    return out


def forward_returns(root: str | Path, first: str, last: str) -> list[float]:
    """Per-trade P&L per dollar of maximum loss of the promoted programs' forward trades (shadow and real) with `day` in
    [first, last]: families in bands probe or sized, or with any real trade. Read-only."""
    from . import guard

    path = Path(root) / "swarm.sqlite"
    if not path.exists():
        return []

    def read(db: sqlite3.Connection) -> list[dict[str, Any]]:
        families = set(guard.ids(db, "SELECT id FROM families WHERE band IN ('probe','sized')"))
        families |= set(guard.ids(db, "SELECT DISTINCT family FROM forward WHERE source='real'"))
        if not families:
            return []
        return [r for r in guard.rows(db, "SELECT family, day, pnl, max_loss FROM forward WHERE source IN ('shadow','real') "
                                          "AND day>=? AND day<=?", (first, last)) if r["family"] in families]

    rows = guard.read(path, read)
    return [float(r["pnl"]) / float(r["max_loss"]) for r in rows
            if r["max_loss"] and float(r["max_loss"]) > 0 and math.isfinite(float(r["pnl"]))]


def guard_verdict(pre: Sequence[float], post: Sequence[float]) -> dict[str, Any]:
    """A breach when the post record is lower than the pre record at one-sided 10% (both with enough trades)."""
    out: dict[str, Any] = {"pre_trades": len(pre), "post_trades": len(post), "breach": False}
    if len(pre) < GUARD_MIN_TRADES or len(post) < GUARD_MIN_TRADES:
        out["note"] = f"fewer than {GUARD_MIN_TRADES} promoted-program trades on a side: the guard holds"
        return out
    mean_a, mean_b = statistics.fmean(pre), statistics.fmean(post)
    se = math.sqrt(statistics.pvariance(pre) / len(pre) + statistics.pvariance(post) / len(post))
    z = (mean_b - mean_a) / se if se > 0 else (0.0 if mean_b == mean_a else math.copysign(math.inf, mean_b - mean_a))
    out.update(pre_mean=round(mean_a, 6), post_mean=round(mean_b, 6), z=round(z, 4) if math.isfinite(z) else z,
               breach=z < -GUARD_Z)
    return out


# ------------------------------------------------------------------------------------------------ canary.json
def write_arm(root: str | Path, key: str, arm: Mapping[str, Any] | None) -> Path:
    """Put `arm` under `key` in `<state>/harness/canary.json` (None drops it), keeping every other arm, atomically."""
    path = Path(root) / CANARY
    arms: dict[str, Any] = {}
    if path.exists():
        # An existing file that does not read as schema 1 (a transient read failure, a torn or foreign file) is never
        # overwritten: that would drop every other arm, retained ones included. The step raises and runs again next hour.
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"{path} could not be read ({type(exc).__name__}); no arm was written") from None
        if not isinstance(current, dict) or current.get("schema") != 1 or not isinstance(current.get("arms") or {}, dict):
            raise RuntimeError(f"{path} is not a schema-1 canary file; no arm was written")
        arms = dict(current.get("arms") or {})
    if arm is None:
        arms.pop(key, None)
    else:
        arms[key] = dict(arm)
    return write_json(path, {"schema": 1, "arms": arms})


# ------------------------------------------------------------------------------------------------ the job
class Engineer:
    def __init__(self, ctx: Any, *, router_factory: Callable[[], Any] | None = None,
                 fetch: Callable[[str], bytes] | None = None, resolve_head: Callable[[], str] | None = None,
                 measure: Callable[..., dict[str, Any]] | None = None, digest: Callable[[Path], str] | None = None,
                 swarm_settings: Mapping[str, Any] | None = None):
        self.ctx = ctx
        self.root = Path(ctx.root)
        self._router_factory = router_factory
        self._router = None
        self._fetch = fetch
        self._resolve_head = resolve_head
        self._measure = measure
        self._digest = digest
        self._swarm = swarm_settings
        self.actions: list[str] = []
        self.spend = 0.0

    # dependencies
    @property
    def swarm(self) -> Mapping[str, Any]:
        if self._swarm is None:
            from ..swarm import settings as settings_mod

            self._swarm = settings_mod.load(self.root, config=self.ctx.config)
        return self._swarm

    def cfg(self) -> dict[str, Any]:
        out = dict(DEFAULTS)
        mine = self.swarm.get("engineer") if isinstance(self.swarm.get("engineer"), Mapping) else {}
        out.update(mine)
        out["author_usd"] = min(float(out["author_usd"]), AUTHOR_USD_CAP)
        out["review_usd"] = min(float(out["review_usd"]), REVIEW_USD_CAP)
        try:
            out["usd_day"] = max(0.0, float(out["usd_day"])) if math.isfinite(float(out["usd_day"])) else 0.0
        except (TypeError, ValueError):
            out["usd_day"] = 0.0  # a typo never lifts the line
        out["lanes"] = [lane for lane in out.get("lanes") or [] if lane in ENGINEER_LANES]
        return out

    @property
    def router(self) -> Any:
        if self._router is None:
            if self._router_factory is not None:
                self._router = self._router_factory()
            else:
                from ..swarm.models import build_router
                from ..swarm.store import SwarmStore

                self._router = build_router(self.root, SwarmStore(self.root), self.swarm, config=self.ctx.config)
        return self._router

    def fetch(self, sha: str) -> bytes:
        if self._fetch is not None:
            return self._fetch(sha)
        from ..updater import fetch_commit

        return fetch_commit(sha)

    def head(self) -> str:
        if self._resolve_head is not None:
            return self._resolve_head()
        from ..updater import resolve_head

        return resolve_head()

    def measure(self, **kwargs: Any) -> dict[str, Any]:
        if self._measure is not None:
            return self._measure(self.root, **kwargs)
        from ..swarm import harness_lanes as lanes

        return lanes.measure(self.root, **kwargs)

    def digest(self, path: Path) -> str:
        if self._digest is not None:
            return self._digest(path)
        from ..watchdog import tree_digest

        return tree_digest(path)[0]

    # helpers
    def now(self) -> float:
        return self.ctx.now()

    def work(self, key: str) -> Path:
        return self.root / WORK / key.replace(":", "_")

    def note(self, text: str) -> None:
        self.actions.append(text[:300])

    def tarball(self, key: str, name: str, sha: str) -> bytes:
        """The tarball of `sha`, cached beside the candidate (`base`, `main`, `head`)."""
        folder = self.work(key)
        path = folder / f"{name}-{sha}.tar.gz"
        if path.exists():
            return path.read_bytes()
        held = sorted(folder.glob(f"*-{sha}.tar.gz")) if folder.exists() else []
        data = held[0].read_bytes() if held else self.fetch(sha)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        for old in folder.glob(f"{name}-*.tar.gz"):
            old.unlink()
        path.write_bytes(data)
        return data

    def save_files(self, key: str, kind: str, files: Mapping[str, str | None]) -> None:
        folder = self.work(key) / kind
        shutil.rmtree(folder, ignore_errors=True)
        for rel, text in files.items():
            if text is None:
                continue
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_text(text, encoding="utf-8")

    def load_files(self, key: str, kind: str, paths: Iterable[str]) -> dict[str, str | None]:
        folder = self.work(key) / kind
        out: dict[str, str | None] = {}
        for rel in paths:
            try:
                out[rel] = (folder / rel).read_text(encoding="utf-8")
            except OSError:
                out[rel] = None
        return out

    def running_text(self, rel: str) -> str | None:
        try:
            return (Path(self.ctx.release) / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def deployed(self, cand: Mapping[str, Any]) -> bool:
        """The running release carries the candidate's change (its tests aside)."""
        rec = cand["record"]
        paths = [p for p in rec.get("files") or {} if not is_new_test(p)]
        if not paths:
            return False
        after = self.load_files(cand["key"], "cand", paths)
        before = self.load_files(cand["key"], "base", paths)
        return all(after[p] is not None and carries(before[p], after[p] or "", self.running_text(p)) for p in paths)

    # ------------------------------------------------------------------ the run
    def run(self) -> dict[str, Any]:
        cfg = self.cfg()
        if cfg.get("enabled") is not True:
            return {"status": "skipped", "why": "engineer.enabled is not true in the swarm's settings"}
        journal = Journal(self.root)
        try:
            for cand in journal.all():
                if cand["state"] == "authoring" and cand["updated_at"] < self.now() - 2 * 3600:
                    self.close(journal, cand, "closed_failed", "the authoring attempt was interrupted")
            for cand in journal.open():
                self.advance(journal, cand, cfg)
            busy = [c for c in journal.open() if c["state"] in HOLDS_AUTHORING]
            due = datetime.fromtimestamp(float(self.ctx.due_at), UTC)
            authoring = (due.hour, due.minute) == AUTHOR_AT
            if busy:
                self.note(f"in flight: {busy[0]['key']} ({busy[0]['state']})")
            elif not authoring:
                self.note("no candidate in flight; authoring waits for the daily occurrence")
            elif journal.authored_on(ny_day(self.now())):
                self.note("a candidate was already authored today")
            else:
                self.author_new(journal, cfg)
            states: dict[str, int] = {}
            for cand in journal.all():
                states[cand["state"]] = states.get(cand["state"], 0) + 1
            return {"actions": self.actions, "states": states, "spend_usd": round(self.spend, 6)}
        finally:
            journal.close()

    def advance(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> None:
        steps = {"pr_pending": self.step_pr_pending, "pr_open": self.step_pr_open, "revise": self.step_revise,
                 "merged": self.step_merged,
                 "canary": self.step_canary, "retained": self.step_retained, "reverting": self.step_reverting}
        for _ in range(8):
            before = cand["state"]
            step = steps.get(before)
            if step is None:
                return
            try:
                cand = step(journal, cand, cfg)
            except GatewayError as exc:
                journal.event(cand["key"], self.now(), "gateway_error", {"state": before, "error": str(exc)[:400]})
                self.note(f"{cand['key']}: the gateway answered {str(exc)[:160]}; next run")
                return
            except Exception as exc:  # noqa: BLE001 - one candidate's fault never stops the others; it is a warning
                journal.event(cand["key"], self.now(), "error", {"state": before, "error": f"{type(exc).__name__}: {str(exc)[:400]}"})
                self.ctx.alert("warning", f"engineer: {cand['key']} ({before}): {type(exc).__name__}: {str(exc)[:200]}")
                self.note(f"{cand['key']}: {type(exc).__name__} in {before}")
                return
            if cand["state"] == before:
                return

    # ------------------------------------------------------------------ 1-3: pick, author, open
    def ranked(self, cfg: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
        """(ranked bottlenecks, the measurement they came from, its source): the observer's when fresh and of this
        release, else a measurement taken now."""
        from ..swarm import harness_lanes as lanes

        now = self.now()
        ranked = read_json(self.root / RANKED, None)
        doc = read_json(self.root / MEASUREMENT, None)
        if isinstance(ranked, dict) and isinstance(doc, dict) and ranked.get("policy") == lanes.POLICY:
            fresh = float(ranked.get("at") or 0) >= now - float(cfg["ranked_max_age_hours"]) * 3600
            source = ranked.get("source") or {}
            mine = Path(str(source.get("release") or "")).name == Path(self.ctx.release).name
            if fresh and mine and abs(float(doc.get("until") or 0) - float(ranked.get("at") or -1)) < 1:
                return list(ranked.get("candidates") or []), doc, "observer"
        doc = self.measure(now=now, seconds=LANES_WINDOW, examples=20)
        return lanes.rank(doc), doc, "engineer"

    def pick(self, journal: Journal, rows: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any],
             base_sha: str) -> dict[str, Any] | None:
        now = self.now()
        history = journal.all()
        for row in rows:
            lane, metric = row.get("lane"), row.get("metric")
            if not row.get("captured") or lane not in cfg["lanes"]:
                continue
            mine = [c for c in history if c["lane"] == lane and c["metric"] == metric]
            if sum(1 for c in mine if c["base_sha"] == base_sha) >= int(cfg["attempts_per_base"]):
                continue
            cooling = [c for c in mine if c["state"] != "closed_retained" and c["updated_at"] >= now - float(cfg["cooldown_hours"]) * 3600]
            if cooling:
                continue
            return dict(row)
        return None

    def base_of_running(self) -> tuple[str | None, str]:
        release = Path(self.ctx.release).name
        sha = attested_sha(deploy_rows(self.ctx.base), release)
        if sha:
            return sha, "attested"
        policy = read_json(self.root / RUNTIME, {}) or {}
        if SHA40.fullmatch(str(policy.get("base") or "")) and policy.get("release_digest") == self.digest(Path(self.ctx.release)):
            return str(policy["base"]), "observer policy"
        return None, "the running release has no attested commit (an owner deploy with no observer policy for it)"

    def author_new(self, journal: Journal, cfg: Mapping[str, Any]) -> None:
        from ..swarm import harness_lanes as lanes

        now = self.now()
        base_sha, how = self.base_of_running()
        if base_sha is None:
            self.note(f"no authoring: {how}")
            return
        try:
            rows, doc, source = self.ranked(cfg)
        except Exception as exc:  # noqa: BLE001 - no measurement, no candidate
            self.note(f"no authoring: the lanes could not be measured ({type(exc).__name__}: {str(exc)[:200]})")
            return
        why = self.no_room(cfg)
        if why:
            self.note(f"no authoring: {why}")
            return
        row = self.pick(journal, rows, cfg, base_sha)
        if row is None:
            self.note("no authoring: no captured bottleneck in an engineer lane that is not cooling down")
            return
        lane, metric = str(row["lane"]), str(row["metric"])
        spec = lanes.LANES[lane]
        key = f"harness:{lane}:{metric}:{hashlib.sha256(f'{base_sha}:{lane}:{metric}:{now}'.encode()).hexdigest()[:16]}"
        measured = (doc.get("lanes") or {}).get(lane) or {}
        record = {"capture": {k: row.get(k) for k in ("value", "denominator", "threshold", "min_effect", "direction",
                                                       "summary", "rank", "stake", "required_units")},
                  "capture_until": float(doc.get("until") or now), "capture_source": source,
                  "population": dict(measured.get("population") or {}),
                  "motivating": lanes.motivating_units(lane, measured), "lane_sha": lanes.lane_sha(spec),
                  "base_how": how, "attempts": [], "revisions_left": 1, "files": {}}
        cand = journal.create(key, lane, metric, at=now, base_sha=base_sha, release=Path(self.ctx.release).name,
                              record=record)
        self.note(f"picked {lane}/{metric} on {base_sha[:12]} ({source}); key {key}")
        examples = measured.get("examples") or row.get("examples") or []
        cand = self.attempt(journal, cand, cfg, brief_text=brief(lane=lane, row=row, key=key, examples=examples), start=None)
        self.advance(journal, cand, cfg)

    def no_room(self, cfg: Mapping[str, Any]) -> str | None:
        """Why no attempt can start now (the roles not configured for Claude, the engineer's line short), or None."""
        try:
            router = self.router
            for role in ("engineer", "reviewer"):
                if not router.claude_enabled(role):
                    return f"Claude is not configured for the {role} role (claude.roles)"
            room = router.claude_role_room("engineer")
        except Exception as exc:  # noqa: BLE001 - a router that cannot be built is no attempt
            return f"the model router could not be built ({type(exc).__name__}: {str(exc)[:200]})"
        if room is not None and room < min(1.0, float(cfg["author_usd"])):
            return f"the engineer's Claude line has ${room:.2f} left today"
        left = self.day_room(cfg)
        if left < min(1.0, float(cfg["author_usd"])):
            return f"the engineer and the reviewer have ${left:.2f} left of their ${float(cfg['usd_day']):.2f} today"
        try:
            health = self.ctx.gateway.get("/v1/health") or {}
        except Exception as exc:  # noqa: BLE001 - an unknown gateway is no attempt
            return f"the gateway's health could not be read ({type(exc).__name__}: {str(exc)[:160]})"
        pulls = (health.get("autonomy") or {}).get("engineer_pulls") if isinstance(health, Mapping) else None
        if not isinstance(pulls, Mapping) or "cap" not in pulls:
            return "the gateway does not take the engineer's pull requests (no autonomy.engineer_pulls in /v1/health)"
        try:
            full = float(pulls.get("count") or 0) >= float(pulls["cap"])
        except (TypeError, ValueError):
            full = True
        if full:
            return f"the gateway's engineer pull requests for today are used ({pulls.get('count')} of {pulls.get('cap')})"
        return None

    def day_spent(self) -> float:
        """The engineer's and the reviewer's Claude spend this UTC day (holds included)."""
        now = self.now()
        since = now - now % 86400
        return sum(max(0.0, float(self.router.claude_spent(role=role, since=since))) for role in ("engineer", "reviewer"))

    def day_room(self, cfg: Mapping[str, Any]) -> float:
        """What is left of `usd_day` today; 0 when the spend cannot be read (fail closed)."""
        try:
            spent = self.day_spent()
        except Exception:  # noqa: BLE001 - an unreadable meter is no room
            return 0.0
        return max(0.0, float(cfg["usd_day"]) - spent) if math.isfinite(spent) else 0.0

    def attempt(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any], *, brief_text: str,
                start: Mapping[str, str] | None) -> dict[str, Any]:
        """One authoring attempt on a fresh work tree of the base: a `pr_pending` candidate, or a closed one."""
        from ..swarm import harness_lanes as lanes
        from ..updater import unpack

        key, lane = cand["key"], cand["lane"]
        now = self.now()
        rec = cand["record"]
        tree = self.work(key) / "tree"
        shutil.rmtree(tree, ignore_errors=True)
        try:
            data = self.tarball(key, "base", cand["base_sha"])
            unpack(data, tree, sha=cand["base_sha"])
            if self.digest(tree) != self.digest(Path(self.ctx.release)):
                raise ValueError("the base commit's tree is not the running release's")
        except Exception as exc:  # noqa: BLE001 - no base, no attempt
            shutil.rmtree(tree, ignore_errors=True)
            return self.close(journal, cand, "closed_failed", f"the base tree could not be had: {type(exc).__name__}: {str(exc)[:300]}")
        usd_cap = min(float(cfg["author_usd"]), self.day_room(cfg))
        if usd_cap < min(1.0, float(cfg["author_usd"])):
            shutil.rmtree(tree, ignore_errors=True)
            return self.close(journal, cand, "closed_failed",
                              f"the engineer and the reviewer have ${usd_cap:.2f} left of their line today")
        try:
            ws = Workspace(tree, lane, start=start)
            n = len(rec["attempts"]) + 1
            outcome: Outcome = run_loop(self.router, ws=ws, lane=lane, key=key, system=AUTHOR_SYSTEM, brief=brief_text,
                                        request_key=f"engineer:{key}:{n}", usd_cap=usd_cap,
                                        max_turns=int(cfg["max_turns"]), deadline=time.time() + 60 * float(cfg["author_minutes"]),
                                        effort=str(cfg["effort"]), max_tokens=int(cfg["max_tokens"]),
                                        keep_usd=float(cfg["keep_usd"]))
            if outcome.status == "finished":
                # Defense in depth: the guards once more on the tree as it is now, and the files exactly that tree's.
                final = static_guards(lane, ws, key=key)
                if final or ws.files() != outcome.files:
                    outcome = Outcome("failed", why="the submitted change no longer passes the static guards",
                                      usd=outcome.usd, turns=outcome.turns,
                                      guards=final or ["the submitted files differ from the work tree"])
            classified = lanes.classify(list(outcome.files), lanes.live_path_modules(tree)) if outcome.files else None
        finally:
            shutil.rmtree(tree, ignore_errors=True)
        self.spend += outcome.usd
        rec["author_usd"] = round(float(rec.get("author_usd") or 0.0) + outcome.usd, 6)
        rec["attempts"].append({"n": len(rec["attempts"]) + 1, "at": now, "status": outcome.status, "why": outcome.why,
                                "usd": outcome.usd, "turns": outcome.turns, "guards": outcome.guards[:12]})
        if outcome.status != "finished":
            return self.close(journal, cand, "closed_failed", f"the authoring attempt {outcome.status}: {outcome.why}")
        rec.update(files={p: sha256(t) for p, t in outcome.files.items()},
                   originals={p: None if t is None else sha256(t) for p, t in outcome.originals.items()},
                   title=outcome.title, summary=outcome.summary, predicted_effect=outcome.predicted_effect,
                   canary_plan=outcome.canary_plan, release_class=(classified or {}).get("release_class", "research"),
                   pr=None, head=None, reviews=[], pending_since=now)
        rec.pop("revise", None)
        self.save_files(key, "cand", outcome.files)
        self.save_files(key, "base", outcome.originals)
        cand = journal.save(cand, at=now, state="pr_pending", kind="authored",
                            detail={"files": sorted(outcome.files), "usd": outcome.usd, "turns": outcome.turns})
        self.note(f"{key}: authored {len(outcome.files)} file(s) for ${outcome.usd:.2f}")
        return cand

    def close(self, journal: Journal, cand: dict[str, Any], state: str, why: str) -> dict[str, Any]:
        rec = cand["record"]
        rec["closed_why"] = why
        # The gateway has no route that closes a pull request: the ones this candidate leaves open (a superseded head,
        # an unmerged one, a revert that did not merge) are listed for the owner (the scoreboard).
        leftover = [int(n) for n in rec.get("superseded_prs") or [] if n is not None]
        if state in ("closed_failed", "closed_rejected") and rec.get("pr") is not None and not rec.get("merged"):
            leftover.append(int(rec["pr"]))
        revert = rec.get("revert") or {}
        if state == "closed_reverted" and revert.get("pr") is not None and why != revert.get("why"):
            leftover.append(int(revert["pr"]))
        if leftover:
            rec["leftover_prs"] = sorted(set(leftover))
        self.note(f"{cand['key']}: {state}: {why}")
        cand = journal.save(cand, at=self.now(), state=state, detail={"why": why[:600]})
        if state.startswith("closed_"):
            shutil.rmtree(self.work(cand["key"]) / "tree", ignore_errors=True)
            for old in self.work(cand["key"]).glob("*.tar.gz"):
                old.unlink()
        return cand

    def pr_body(self, cand: Mapping[str, Any]) -> str:
        from ..swarm import harness_lanes as lanes

        rec = cand["record"]
        lane = lanes.LANES[cand["lane"]]
        bottleneck = lane.bottleneck(cand["metric"])
        m = bottleneck.metric
        canary = lane.canary_for(bottleneck)
        cap = rec.get("capture") or {}
        hours = int(canary.get("observe_seconds", 0)) // 3600
        plan = (f"arms: {float(canary.get('fraction', 0.5)):.0%} of {canary.get('unit')} units get the change through "
                f"`<state>/harness/canary.json` for {hours} h after the deploy, the rest are the concurrent control"
                if canary.get("mode") == "arms" else
                f"window: the {hours} h after the release's promotion against the {hours} h before its deploy")
        parts = ["Automated harness change by the House's engineer (LTCM v3, Phase 4). Merges only on green CI and the "
                 "automated adversarial review; the canary decides retain or revert.", "",
                 f"- Lane: `{lane.id}` ({lane.title})", f"- Canary key: `{cand['key']}`",
                 f"- Base: `{cand['base_sha']}` (the running release, {rec.get('base_how')})",
                 f"- Release class: {rec.get('release_class')}", "",
                 "## Measurement", "",
                 f"`{m.name}` = {cap.get('value')} over {cap.get('denominator')} `{m.denominator}` in the last day "
                 f"(a bottleneck from {m.threshold}; measured by the {rec.get('capture_source')}).", "",
                 "## Predeclared metric", "",
                 f"`{m.name}`, {m.direction} is better. Retained only if the canary shows a relative improvement of at "
                 f"least {m.min_effect:.0%} at one-sided p <= {ALPHA}, with "
                 + (", ".join(f"`{x.name}`" for x in list(bottleneck.secondary) + list(lane.guards)) or "no other metric")
                 + " not worse than its tolerance; and, for 20 sessions after, the promoted programs' forward record not "
                   "lower (the global guard).", "",
                 "## Predicted effect", "", _public(rec.get("predicted_effect") or "(none given)"), "",
                 "## Canary plan", "", plan + ". " + _public(rec.get("canary_plan") or ""), "",
                 "## Change", "", _public(rec.get("summary") or ""), "",
                 "## Static guards", "", "surface_check, content_guard, symbol_guard"
                 + (", gate_coverage" if canary.get("mode") == "arms" else "") + ": passed (git-free, on the House).", "",
                 f"Authoring: ${float(rec.get('author_usd') or 0):.2f} of Claude over {len(rec.get('attempts') or [])} attempt(s)."]
        return "\n".join(parts)[:7900]

    def main_check(self, cand: Mapping[str, Any], files: Mapping[str, str]) -> tuple[str, str | None]:
        """(main's head, a problem): each touched file must read on main as in the base."""
        from .reviewer import tar_index

        head = self.head()
        if head == cand["base_sha"]:
            return head, None
        hashes, _ = tar_index(self.tarball(cand["key"], "main", head))
        originals = cand["record"].get("originals") or {}
        moved = [p for p in files if hashes.get(p) != originals.get(p)]
        return head, (f"main moved {moved[:4]} since the base: the change would undo it" if moved else None)

    def step_pr_pending(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        rec = cand["record"]
        now = self.now()
        if now - float(rec.get("pending_since") or now) > float(cfg["pr_pending_hours"]) * 3600:
            return self.close(journal, cand, "closed_failed", "the pull request could not be opened in time")
        files = {p: t for p, t in self.load_files(cand["key"], "cand", rec["files"]).items() if t is not None}
        main, problem = self.main_check(cand, files)
        if problem:
            return self.close(journal, cand, "closed_failed", problem)
        slug = re.sub(r"[^a-z0-9-]", "-", f"{cand['lane']}-{cand['metric']}".lower())[:40].strip("-")
        title = _public(f"engineer({cand['lane']}): {rec.get('title') or cand['metric']}")[:120]
        body = {"role": "engineer", "lane": cand["lane"], "slug": slug, "title": title, "body": self.pr_body(cand),
                "files": [{"path": p, "content": t} for p, t in sorted(files.items())]}
        try:
            answer = self.ctx.gateway.post("/v1/github/pr", body)
        except GatewayError as exc:
            if exc.status in (400, 403, 409, 413, 422):
                return self.close(journal, cand, "closed_failed", f"the gateway refused the pull request: {str(exc)[:300]}")
            journal.event(cand["key"], now, "pr_wait", {"error": str(exc)[:300]})
            self.note(f"{cand['key']}: the pull request waits ({str(exc)[:120]})")
            return cand
        rec.update(pr=int(answer["number"]), head=str(answer["head"]), branch=answer.get("branch"), main_sha=main,
                   pr_at=now, reviews=[])
        self.note(f"{cand['key']}: opened #{rec['pr']}")
        return journal.save(cand, at=now, state="pr_open", kind="pr_opened",
                            detail={"pr": rec["pr"], "head": rec["head"], "branch": rec.get("branch"), "main": main})

    # ------------------------------------------------------------------ 4-5: CI, review, merge
    def step_pr_open(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        rec = cand["record"]
        now = self.now()
        status = self.ctx.gateway.get(f"/v1/github/pr/{rec['pr']}") or {}
        if status.get("merged") is True:
            rec["merged"] = {"at": now, "sha": None}
            return journal.save(cand, at=now, state="merged", kind="merged", detail={"pr": rec["pr"], "seen": "already merged"})
        if status.get("state") != "open":
            return self.close(journal, cand, "closed_failed", f"pull request #{rec['pr']} was closed outside the loop")
        if status.get("head") != rec["head"]:
            return self.close(journal, cand, "closed_failed", f"pull request #{rec['pr']}'s head moved")
        checks = status.get("checks") or {}
        conclusion = checks.get("conclusion")
        if conclusion == "pending" or conclusion is None:
            if now - float(rec.get("pr_at") or now) > float(cfg["ci_hours"]) * 3600:
                return self.close(journal, cand, "closed_failed", "CI did not finish in time")
            self.note(f"{cand['key']}: CI pending on #{rec['pr']}")
            return cand
        if conclusion != "success":
            found = self.ctx.gateway.get(f"/v1/github/pr/{rec['pr']}/failures") or {}
            reasons = []
            for failure in (found.get("failures") or [])[:6]:
                reasons.append(f"CI {failure.get('name')}: {failure.get('title') or failure.get('conclusion')}")
                reasons += [f"  {a.get('title')}: {str(a.get('message'))[:600]}" for a in (failure.get("annotations") or [])[:6]]
            journal.event(cand["key"], now, "ci_failed", {"pr": rec["pr"], "reasons": reasons[:20]})
            return self.revise(journal, cand, cfg, reasons or ["CI failed with no annotation"], why="CI failed")
        # Green: the reviews of this exact head (two for a money-path change), then the verdict, then the merge.
        if not rec.get("verdict_posted"):
            needed = 2 if rec.get("release_class") in ("money_path", "evidence_reset") else 1
            others = [r for r in rec.get("reviews") or [] if r.get("head") != rec["head"]]
            done = [r for r in rec.get("reviews") or [] if r.get("head") == rec["head"]]
            problems, files = self.exact_diff(cand)
            if problems and not done:
                done.append({"head": rec["head"], "verdict": "reject", "reasons": problems, "usd": 0.0, "mechanical": True})
            while len(done) < needed and all(r["verdict"] == "approve" for r in done):
                left = self.day_room(cfg)
                got = (self.review_once(cand, cfg, files, second=len(done) == 1) if left >= float(cfg["review_usd"]) else
                       {"ok": False, "usd": 0.0,
                        "why": f"${left:.2f} left of the engineer's and the reviewer's ${float(cfg['usd_day']):.2f} today"})
                if not got.get("ok"):
                    rec["reviews"] = others + done
                    rec["review_failures"] = int(rec.get("review_failures") or 0) + (1 if got.get("usd") else 0)
                    # A billed failure (a refusal, a cut answer) is paid for: three end the candidate, whatever the line.
                    if rec["review_failures"] >= 3 or now - float(rec.get("pr_at") or now) > float(cfg["review_hours"]) * 3600:
                        return self.close(journal, cand, "closed_failed", f"no review could be had: {got.get('why')}")
                    self.note(f"{cand['key']}: the review waits ({str(got.get('why'))[:120]})")
                    return journal.save(cand, at=now, kind="review_wait", detail={"why": str(got.get("why"))[:300]})
                done.append({"head": rec["head"], "verdict": got["verdict"], "reasons": got["reasons"], "usd": got["usd"]})
            rec["reviews"] = others + done
            cand = journal.save(cand, at=now, kind="reviews", detail={"reviews": len(done)})  # paid for: kept if the post fails
            rec = cand["record"]
            verdict = "approve" if len(done) >= needed and all(r["verdict"] == "approve" for r in done) else "reject"
            reasons = [str(x)[:1000] for r in done for x in r["reasons"]][:20] or ["no reason given"]
            self.ctx.gateway.post("/v1/github/review", {"pr": rec["pr"], "head_sha": rec["head"], "verdict": verdict,
                                                         "reasons": reasons})
            rec["verdict_posted"] = verdict
            cand = journal.save(cand, at=now, kind="reviewed", detail={"pr": rec["pr"], "verdict": verdict, "reasons": reasons})
            self.note(f"{cand['key']}: review {verdict} on #{rec['pr']}")
            if verdict != "approve":
                return self.revise(journal, cand, cfg, reasons, why="the review rejected it")
        return self.merge(journal, cand, cfg)

    def exact_diff(self, cand: Mapping[str, Any]) -> tuple[list[str], dict[str, tuple[str | None, str]]]:
        """Code's own check of the pull request's exact head against the main it was cut from, and the files to review."""
        from .reviewer import mechanical, tar_index, tree_changes

        rec = cand["record"]
        paths = list(rec["files"])
        expected = {p: t for p, t in self.load_files(cand["key"], "cand", paths).items() if t is not None}
        originals = self.load_files(cand["key"], "base", paths)
        main_hashes, main_texts = tar_index(self.tarball(cand["key"], "main", rec["main_sha"]), want=paths)
        head_hashes, head_texts = tar_index(self.tarball(cand["key"], "head", rec["head"]), want=paths)
        problems = mechanical(tree_changes(main_hashes, head_hashes), head_texts, expected)
        files = {p: (main_texts.get(p, originals.get(p)), head_texts.get(p, expected[p])) for p in expected}
        return problems, files

    def review_once(self, cand: Mapping[str, Any], cfg: Mapping[str, Any], files: Mapping[str, tuple[str | None, str]],
                    *, second: bool) -> dict[str, Any]:
        from . import reviewer

        rec = cand["record"]
        contract = reviewer.contract_text(lane=cand["lane"], metric=cand["metric"], key=cand["key"],
                                          release_class=str(rec.get("release_class")))
        claims = {"title": rec.get("title"), "summary": rec.get("summary"), "predicted_effect": rec.get("predicted_effect"),
                  "canary_plan": rec.get("canary_plan")}
        guards = ("The surface and protected-path checks, content_guard, symbol_guard"
                  + (" and gate_coverage" if cand["lane"] in ("research", "memory") else "")
                  + " passed on the House; the pull request carries exactly the candidate's bytes; CI is green on this "
                  "exact head.")
        got = reviewer.review(self.router, request_key=f"reviewer:{cand['key']}:{rec['head']}:{int(second)}",
                              contract=contract, files=files, claims=claims, guards=guards, second=second,
                              usd_cap=float(cfg["review_usd"]), effort=str(cfg["review_effort"]))
        self.spend += float(got.get("usd") or 0.0)
        rec["review_usd"] = round(float(rec.get("review_usd") or 0.0) + float(got.get("usd") or 0.0), 6)
        return got

    def revise(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any], reasons: Sequence[str], *,
               why: str) -> dict[str, Any]:
        """Back to the engineer once (a new attempt starting from its previous change, a new pull request)."""
        rec = cand["record"]
        if int(rec.get("revisions_left") or 0) < 1:
            return self.close(journal, cand, "closed_rejected", f"{why} after its revision")
        rec["revisions_left"] = int(rec["revisions_left"]) - 1
        rec["superseded_prs"] = list(rec.get("superseded_prs") or []) + [rec.get("pr")]
        rec.pop("verdict_posted", None)
        rec["revise"] = {"why": why, "reasons": [str(r)[:900] for r in reasons][:16]}
        self.note(f"{cand['key']}: {why}; back to the engineer once")
        return journal.save(cand, at=self.now(), state="revise", kind="revise", detail=rec["revise"])

    def step_revise(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        """The revision's authoring, outside the session (and its half hour each side): the House's one CPU trades then."""
        if S.in_session(self.now(), pad_minutes=30):
            self.note(f"{cand['key']}: the revision waits for the close")
            return cand
        left = self.day_room(cfg)
        if left < min(1.0, float(cfg["author_usd"])):
            self.note(f"{cand['key']}: the revision waits for room (${left:.2f} left of the day's ${float(cfg['usd_day']):.2f})")
            return cand
        rec = cand["record"]
        rec["revise"]["tries"] = int(rec["revise"].get("tries") or 0) + 1
        if rec["revise"]["tries"] > 2:
            return self.close(journal, cand, "closed_failed", "the revision was interrupted twice")
        cand = journal.save(cand, at=self.now(), kind="revising", detail={"try": rec["revise"]["tries"]})
        rec = cand["record"]
        start = {p: t for p, t in self.load_files(cand["key"], "cand", rec["files"]).items() if t is not None}
        text = brief(lane=cand["lane"], row={"metric": cand["metric"], **(rec.get("capture") or {})}, key=cand["key"],
                     examples=[], feedback=rec["revise"]["reasons"], revision=True)
        return self.attempt(journal, cand, cfg, brief_text=text, start=start)

    def merge(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        from ..swarm import harness_lanes as lanes

        rec = cand["record"]
        now = self.now()
        canary = lanes.LANES[cand["lane"]].canary_for(lanes.LANES[cand["lane"]].bottleneck(cand["metric"]))
        if canary.get("mode") != "arms":
            ready = float(rec["capture_until"]) + float(canary.get("observe_seconds", 0))
            if now < ready:
                self.note(f"{cand['key']}: the merge waits until {S.iso(ready)} so its control window follows the capture")
                return cand
        try:
            answer = self.ctx.gateway.post("/v1/github/merge", {"pr": rec["pr"], "head_sha": rec["head"]})
        except GatewayError as exc:
            if exc.status == 429 or exc.status is None or exc.status >= 500:
                self.note(f"{cand['key']}: the merge waits ({str(exc)[:120]})")
                return cand
            status = self.ctx.gateway.get(f"/v1/github/pr/{rec['pr']}") or {}
            if status.get("merged") is True:
                answer = {"sha": None}
            else:
                return self.close(journal, cand, "closed_failed", f"the merge was refused: {str(exc)[:300]}")
        rec["merged"] = {"at": now, "sha": (answer or {}).get("sha")}
        self.note(f"{cand['key']}: merged #{rec['pr']}")
        return journal.save(cand, at=now, state="merged", kind="merged", detail={"pr": rec["pr"], "sha": rec["merged"]["sha"]})

    # ------------------------------------------------------------------ 6-8: deploy, canary, decide
    def money_hours(self, cand: Mapping[str, Any]) -> bool:
        """A money-path gate moves only outside New York's session (09:30-16:05)."""
        return cand["record"].get("release_class") in ("money_path", "evidence_reset") and S.in_session(self.now(), pad_minutes=5)

    def step_merged(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        from ..swarm import harness_lanes as lanes

        rec = cand["record"]
        now = self.now()
        if not self.deployed(cand):
            if now - float(rec["merged"]["at"]) > float(cfg["deploy_days"]) * 86400:
                return self.start_revert(journal, cand, "merged but never deployed")
            self.note(f"{cand['key']}: waiting for the updater to deploy the merge")
            return cand
        lane = lanes.LANES[cand["lane"]]
        bottleneck = lane.bottleneck(cand["metric"])
        canary = lane.canary_for(bottleneck)
        if rec.get("lane_sha") != lanes.lane_sha(lane):
            return self.start_revert(journal, cand, "voided: the lane's predeclared definition changed after the capture")
        if self.money_hours(cand):
            self.note(f"{cand['key']}: a money-path gate opens only outside the session")
            return cand
        window = float(canary.get("observe_seconds", 0))
        release = Path(self.ctx.release).name
        began, promoted = deploy_window(deploy_rows(self.ctx.base), release)
        if promoted is None and canary.get("mode") != "arms":
            # No promote row for the running release (an owner deploy, rows missing): the control window cannot be put
            # before the deploy, and a window ending now would hold treated hours. Fail closed.
            return self.start_revert(journal, cand, "voided: the running release has no promote row, so the control "
                                                    "window cannot be placed before the deploy")
        promoted = promoted or now
        began = began or promoted
        rec["deployed"] = {"at": now, "release": release, "began_at": began, "promoted_at": promoted}
        if canary.get("mode") == "arms":
            arm = {"lane": lane.id, "mode": "arms", "fraction": float(canary.get("fraction", 0.5)),
                   "salt": secrets.token_hex(8), "state": "canary", "since": round(now + 60.0, 3), "release": release,
                   "by": "engineer"}
            write_arm(self.root, cand["key"], arm)
            rec["canary"] = arm
        else:
            control = self.measure(since=began - window, now=began, lanes=[lane.id])
            capture_until = float(rec["capture_until"])
            if float(control["since"]) < capture_until - 60:
                return self.start_revert(journal, cand, "voided: the control window overlaps the capture")
            if any(float(control["since"]) < float(s) < float(control["until"]) for s in control.get("starts") or []):
                return self.start_revert(journal, cand, "voided: the swarm restarted inside the control window")
            data = (control.get("lanes") or {}).get(lane.id) or {}
            rec["control"] = {"units": data.get("units") or {}, "population": dict(data.get("population") or {}),
                              "extra": {k: v for k, v in lanes.lane_tallies(lane.id, data).items() if k in EXTRAS},
                              "window": control.get("window")}
            rec["canary"] = {"lane": lane.id, "mode": "window", "since": round(promoted, 3), "release": release}
        rec["canary"]["until"] = round(float(rec["canary"]["since"]) + window, 3)
        self.note(f"{cand['key']}: canary started ({rec['canary']['mode']}), window ends {S.iso(rec['canary']['until'])}")
        return journal.save(cand, at=now, state="canary", kind="canary_started", detail={"canary": rec["canary"]})

    def step_canary(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        from ..swarm import harness_lanes as lanes

        rec = cand["record"]
        now = self.now()
        arm = rec["canary"]
        if not self.deployed(cand):
            return self.start_revert(journal, cand, "the watchdog rolled the candidate's release back")
        if now < float(arm["until"]):
            self.note(f"{cand['key']}: canary runs until {S.iso(arm['until'])}")
            return cand
        lane = lanes.LANES[cand["lane"]]
        bottleneck = lane.bottleneck(cand["metric"])
        if "decision" not in rec:
            since, end = float(arm["since"]), float(arm["until"])
            measurement = self.measure(since=since, now=end, lanes=[lane.id])
            rec["decision"] = decide(lane, bottleneck, measurement, rec, key=cand["key"])
            journal.save(cand, at=now, kind="decided", detail={"decision": rec["decision"]})
        decision = rec["decision"]["decision"]
        if decision != "retained":
            return self.start_revert(journal, cand, f"the canary decided {decision}"
                                     + (f" ({rec['decision'].get('reason')})" if rec["decision"].get("reason") else ""))
        if arm.get("mode") == "arms":
            if self.money_hours(cand):
                self.note(f"{cand['key']}: retained; the gate flips for everyone after the close")
                return cand
            write_arm(self.root, cand["key"], {**arm, "state": "retained"})
        rec["retained_at"] = now
        self.note(f"{cand['key']}: retained")
        return journal.save(cand, at=now, state="retained", kind="retained", detail={"primary": rec["decision"].get("primary")})

    def step_retained(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        rec = cand["record"]
        now = self.now()
        if not self.deployed(cand):
            return self.start_revert(journal, cand, "the running release no longer carries the retained change")
        n = int(cfg["guard_sessions"])
        start_day = datetime.fromtimestamp(float(rec["canary"]["since"]), UTC).date()
        retained_day = datetime.fromtimestamp(float(rec["retained_at"]), UTC).date()
        yesterday = datetime.fromtimestamp(now, UTC).date() - timedelta(days=1)  # whole sessions only
        pre_days = trading_days(start_day - timedelta(days=60), start_day - timedelta(days=1))[-n:]
        post_days = trading_days(retained_day + timedelta(days=1), yesterday)[:n]
        if not post_days or rec.get("guard_sessions_seen") == len(post_days):
            return cand
        pre = forward_returns(self.root, pre_days[0], pre_days[-1]) if pre_days else []
        post = forward_returns(self.root, post_days[0], post_days[-1])
        verdict = guard_verdict(pre, post)
        verdict["sessions"] = len(post_days)
        rec["guard"] = verdict
        rec["guard_sessions_seen"] = len(post_days)
        if verdict["breach"]:
            return self.start_revert(journal, cand, "the global guard: the promoted programs' forward record fell after it")
        if len(post_days) >= n:
            self.note(f"{cand['key']}: the global guard held over {n} sessions")
            return journal.save(cand, at=now, state="closed_retained", kind="guard_held", detail={"guard": verdict})
        return journal.save(cand, at=now, kind="guard", detail={"guard": verdict})

    # ------------------------------------------------------------------ reverts
    def start_revert(self, journal: Journal, cand: dict[str, Any], why: str) -> dict[str, Any]:
        rec = cand["record"]
        arm = rec.get("canary") or {}
        if arm.get("mode") == "arms":
            write_arm(self.root, cand["key"], {**arm, "state": "reverted"})
        rec["revert"] = {"why": why, "at": self.now(), "pr": None}
        self.note(f"{cand['key']}: reverting: {why}")
        return journal.save(cand, at=self.now(), state="reverting", kind="revert", detail={"why": why})

    def step_reverting(self, journal: Journal, cand: dict[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
        from .reviewer import mechanical, tar_index, tree_changes

        rec = cand["record"]
        rev = rec["revert"]
        now = self.now()
        gated = (rec.get("canary") or {}).get("mode") == "arms"
        if now - float(rev.get("at") or now) > float(cfg["deploy_days"]) * 86400:
            # A revert holds the next authoring (HOLDS_AUTHORING): one that never lands is handed over, not waited on.
            if not gated:
                self.ctx.alert("warning", f"engineer: the revert of {cand['key']} did not land in {cfg['deploy_days']} days; "
                                          "revert by hand")
            return self.close(journal, cand, "closed_reverted", f"{rev['why']}; the revert did not land in time"
                              + ("; the gate is reverted" if gated else "; revert by hand"))
        if rev.get("pr") is None:
            paths = list(rec["files"])
            after = self.load_files(cand["key"], "cand", paths)
            before = self.load_files(cand["key"], "base", paths)
            main = self.head()
            _, current = tar_index(self.tarball(cand["key"], "main", main), want=paths)
            files: dict[str, str] = {}
            for p in paths:
                if before.get(p) is None:
                    # The candidate's own new test pins the change: it cannot be deleted through a proposal, so it is
                    # emptied of tests (a docstring that says why).
                    stub = '"""Reverted by the engineer: ' + cand["key"] + '. The change this file tested was taken out."""\n'
                    if current.get(p) is not None and current.get(p) != stub:
                        files[p] = stub
                    continue
                text = revert_text(before[p], after[p] or "", current.get(p))
                if text is None:
                    rev["manual"] = f"{p}: main moved around the change; it cannot be taken out exactly"
                    break
                if text != current.get(p):
                    files[p] = text
            if rev.get("manual"):
                if not gated:
                    self.ctx.alert("warning", f"engineer: {cand['key']} must be reverted by hand ({rev['manual']})")
                return self.close(journal, cand, "closed_reverted",
                                  f"{rev['why']}; the gate is reverted" if gated else f"{rev['why']}; revert by hand")
            if not files:
                return self.close(journal, cand, "closed_reverted", f"{rev['why']}; main no longer carries it")
            body = {"role": "engineer", "lane": cand["lane"], "slug": f"revert-{cand['lane']}-{cand['key'][-8:]}",
                    "title": f"engineer({cand['lane']}): revert {cand['key'][-16:]}",
                    "body": (f"Automated revert of #{rec.get('pr')} (canary key `{cand['key']}`): {_public(rev['why'])}. "
                             "Each file is put back as it was before the change, against main as it is now; the review "
                             "is mechanical (the exact bytes)."),
                    "files": [{"path": p, "content": t} for p, t in sorted(files.items())]}
            try:
                answer = self.ctx.gateway.post("/v1/github/pr", body)
            except GatewayError as exc:
                if exc.status in (400, 403, 409, 413, 422):
                    if not gated:
                        self.ctx.alert("warning", f"engineer: the revert of {cand['key']} was refused ({str(exc)[:200]})")
                    return self.close(journal, cand, "closed_reverted", f"{rev['why']}; the revert pull request was refused")
                self.note(f"{cand['key']}: the revert pull request waits ({str(exc)[:120]})")
                return cand
            self.save_files(cand["key"], "revert", files)
            rev.update(pr=int(answer["number"]), head=str(answer["head"]), main_sha=main, at_pr=now, files=sorted(files))
            return journal.save(cand, at=now, kind="revert_opened", detail={"pr": rev["pr"], "head": rev["head"]})
        status = self.ctx.gateway.get(f"/v1/github/pr/{rev['pr']}") or {}
        if status.get("merged") is True:
            return self.close(journal, cand, "closed_reverted", rev["why"])
        conclusion = (status.get("checks") or {}).get("conclusion")
        if status.get("state") != "open" or status.get("head") != rev["head"] or conclusion not in (None, "pending", "success"):
            if not gated:
                self.ctx.alert("warning", f"engineer: the revert of {cand['key']} (#{rev['pr']}) did not pass; revert by hand")
            return self.close(journal, cand, "closed_reverted", f"{rev['why']}; the revert pull request failed")
        if conclusion != "success":
            return cand
        paths = list(rev["files"])
        expected = {p: t for p, t in self.load_files(cand["key"], "revert", paths).items() if t is not None}
        main_hashes, _ = tar_index(self.tarball(cand["key"], "main", rev["main_sha"]))
        head_hashes, head_texts = tar_index(self.tarball(cand["key"], "head", rev["head"]), want=paths)
        problems = mechanical(tree_changes(main_hashes, head_hashes), head_texts, expected)
        if not rev.get("verdict_posted"):
            verdict = "reject" if problems else "approve"
            reasons = problems or [f"mechanical revert of the engineer's change {cand['key']}: each file is exactly its "
                                   "text before the change, against main as it was when the revert was cut"]
            self.ctx.gateway.post("/v1/github/review", {"pr": rev["pr"], "head_sha": rev["head"], "verdict": verdict,
                                                         "reasons": reasons})
            rev["verdict_posted"] = verdict
            journal.save(cand, at=now, kind="revert_reviewed", detail={"verdict": verdict, "reasons": reasons})
            if problems:
                return self.close(journal, cand, "closed_reverted", f"{rev['why']}; the revert's bytes were not exact")
        try:
            self.ctx.gateway.post("/v1/github/merge", {"pr": rev["pr"], "head_sha": rev["head"]})
        except GatewayError as exc:
            if exc.status == 429 or exc.status is None or exc.status >= 500:
                self.note(f"{cand['key']}: the revert's merge waits ({str(exc)[:120]})")
                return cand
            if (self.ctx.gateway.get(f"/v1/github/pr/{rev['pr']}") or {}).get("merged") is not True:
                if not gated:
                    self.ctx.alert("warning", f"engineer: the revert of {cand['key']} (#{rev['pr']}) could not merge; revert by hand")
                return self.close(journal, cand, "closed_reverted", f"{rev['why']}; the revert's merge was refused ({str(exc)[:200]})")
        return self.close(journal, cand, "closed_reverted", rev["why"])


EXTRAS = ("runs", "error_runs", "restarts", "restart_failures", "live_errors", "restarts_or_one")


def decide(lane: Any, bottleneck: Any, measurement: Mapping[str, Any], rec: Mapping[str, Any], *, key: str) -> dict[str, Any]:
    """The registered decision on the canary window (the module docstring, step 8): `harness_lanes.retention` on the
    arms (motivating units excluded) or on the window against its control; voided when another release was promoted or
    started inside the window or the lane's definition changed."""
    from ..swarm import harness_lanes as lanes

    arm = rec["canary"]
    since, end = float(arm["since"]), float(arm["until"])
    seed = hashlib.sha256(json.dumps([key, arm.get("salt") or arm["since"]]).encode()).hexdigest()
    others = sorted({str(r.get("release")) for r in measurement.get("deploys") or []
                     if r.get("stage") == "verdict" and r.get("verdict") == "promoted" and r.get("release") != arm.get("release")
                     and since < (lanes.epoch_of(r.get("at")) or 0.0) < end})
    foreign = sorted({str(s.get("release")) for s in measurement.get("start_releases") or []
                      if since < float(s.get("at") or 0.0) < end and s.get("release") != arm.get("release")})
    void = (f"another release ({', '.join(others)[:200]}) was promoted inside the window" if others else
            f"the swarm ran another release ({', '.join(foreign)[:200]}) inside the window" if foreign else
            "the lane's predeclared definition changed during the canary" if rec.get("lane_sha") != lanes.lane_sha(lane) else None)
    data = (measurement.get("lanes") or {}).get(lane.id)
    if void is None and not isinstance(data, Mapping):
        void = f"the measurement has no {lane.id} lane ({(measurement.get('errors') or {}).get(lane.id)})"
    if void is not None:
        return {"decision": "voided", "reason": void}
    if arm.get("mode") == "arms":
        treated, control = lanes.split_arms(data.get("units") or {}, key=key, salt=arm["salt"], fraction=float(arm["fraction"]),
                                            exclude=list(rec.get("motivating") or []) + list(lane.arm_exclude),
                                            needs=lane.arm_needs)
        result = lanes.retention(lane, bottleneck, treated, control, seed=seed, alpha=ALPHA,
                                 population=(lanes.lane_tallies(lane.id, {"population": data.get("population")}),
                                             dict(rec.get("population") or {})),
                                 fraction=float(arm["fraction"]))
    else:
        before = rec.get("control") or {}
        after = {k: v for k, v in lanes.lane_tallies(lane.id, data).items() if k in EXTRAS}
        result = lanes.retention(lane, bottleneck, dict(data.get("units") or {}), dict(before.get("units") or {}), seed=seed,
                                 alpha=ALPHA, extra_treated=after or None, extra_control=dict(before.get("extra") or {}) or None,
                                 population=(lanes.lane_tallies(lane.id, {"population": data.get("population")}),
                                             dict(before.get("population") or {})))
    result.update(window={"since": S.iso(since), "until": S.iso(end)}, mode=arm.get("mode"),
                  limitations="Operational evidence of the harness change, not strategy alpha or profitability.")
    return json.loads(json.dumps(result, default=str))


def public_summary(root: str | Path) -> dict[str, Any] | None:
    """The scoreboard's counts (public-safe: lanes and counts, no metric figure, key or family): None with no journal."""
    path = Path(root) / FILE
    if not path.exists():
        return None
    from . import guard

    rows = guard.read(path, lambda db: guard.rows(db, "SELECT lane, state, record FROM candidates"))
    out: dict[str, Any] = {"authored": len(rows), "merged": 0, "retained": 0, "reverted": 0, "rejected": 0, "failed": 0,
                           "in_flight": None, "claude_usd": 0.0, "leftover_prs": []}
    for row in rows:
        rec = json.loads(row["record"] or "{}")
        out["leftover_prs"] += [int(n) for n in rec.get("leftover_prs") or [] if isinstance(n, int)]
        out["claude_usd"] += float(rec.get("author_usd") or 0.0) + float(rec.get("review_usd") or 0.0)
        if rec.get("merged"):
            out["merged"] += 1
        state = row["state"]
        if state in ("retained", "closed_retained"):
            out["retained"] += 1
        elif state in ("reverting", "closed_reverted"):
            out["reverted"] += 1
        elif state == "closed_rejected":
            out["rejected"] += 1
        elif state == "closed_failed":
            out["failed"] += 1
        if state in IN_FLIGHT:
            out["in_flight"] = f"{row['lane']} ({state.replace('_', ' ')})"
    out["claude_usd"] = round(out["claude_usd"], 2)
    out["leftover_prs"] = sorted(set(out["leftover_prs"]))
    return out


def run(ctx: Any) -> dict[str, Any]:
    return Engineer(ctx).run()


__all__ = ["Engineer", "Journal", "run", "decide", "brief", "public_summary", "attested_sha", "deploy_window", "carries",
           "revert_text", "segments", "write_arm", "guard_verdict", "forward_returns", "trading_days", "scrub_examples",
           "public_problems", "DEFAULTS", "AUTHOR_SYSTEM", "IN_FLIGHT", "HOLDS_AUTHORING", "OPEN_STATES"]
