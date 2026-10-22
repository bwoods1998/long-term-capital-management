"""PREREG-EVL-7's LEARNER ALARMS (the judge's H5; league/ops/evl_health.py's cause `evl_learner`), read-only from the
lane's store: a learner fails quietly (it trains on old rows, or picks nothing), so the stall job says when

- A LIVE PART FAILED OR EXPIRED (league/events/learner.py `PART_KEY`): that auction is decided later by the learner by
  itself (shadow only, never traded, never judged), and the alarm says whether it has been;
- A DECISION IS OWED: a session whose House decision finished more than `OWED_HOURS` ago with no learner decision on
  record (the catch-up did not run);
- THE TRAINING LAGS: the latest live decision trained on no row of the session it should have (EVL-LRN-O1 at D's open
  reads D-1's settled outcomes, EVL-LRN-ON at D's close reads D-2's: section 1.5's lag 1 and lag 2), as when the
  evening score chain ran late (A95);
- THE NIGHTLY RECOMPUTE MISMATCHED (`RECOMPUTE_KEY`): a decision re-decided on unchanged inputs gave other picks or
  another beta;
- THE WARM-UP IS UNMET after `WARM_SESSIONS_MAX` live decisions.

Counts and dates only: no fitted figure (beta, e, z, ahat) is read into the alarm. Nothing is judged while
REGISTERED_AT_7 is None (no learner exists)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import guard

CAUSE = "evl_learner"
STORE = Path("events") / "events.sqlite"
OWED_HOURS = 2.0
LOOK_SESSIONS = 5
WARM_SESSIONS_MAX = 5
DOING = ("A learner's part of each live decision runs after the House's own decision of the auction, under its own "
         "bound (90 s at the open, 120 s at the close); one that fails or runs past its bound is never traded at that "
         "auction and is decided later by the learner by itself (the lane's learner task, shadow only); the nightly "
         "recompute re-decides each live decision and alarms on any mismatch on unchanged inputs; the training lag "
         "follows the evening score. Each stall here is the captain's to read (a release, or the score chain).")


class _View:
    """A read-only connection in the shape league/events/learner.py reads (`.db`, `.meta`)."""

    def __init__(self, db: Any):
        self.db = db

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])


def facts(root: str | Path, now: float) -> dict[str, Any] | None:
    """What the alarm reads, in one read-only transaction; None while no learner is pinned or the store is missing."""
    from ..events import calendar as C
    from ..events import learner as LR
    from ..events import programs as P
    from ..events import store as S

    learners = P.learners()
    path = Path(root) / STORE
    if not learners or not path.exists():
        return None
    moment = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    today = moment.astimezone(C.NY).date()

    def read(db: Any) -> dict[str, Any]:
        view = _View(db)
        tables = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out: dict[str, Any] = {"learners": {}}
        for learner in learners:
            sessions = [s for s in C.sessions(view, today - dt.timedelta(days=14), today)]
            mine: dict[str, Any] = {"parts": [], "owed": [], "lag": None, "warm": None, "recompute": []}
            for s in sessions[-LOOK_SESSIONS:]:
                key = LR.PART_KEY.format(program=learner.id, version=learner.version, day=s.day.isoformat())
                raw = view.meta(key)
                rec = LR.decided(view, learner, s.day) if "learner_fits" in tables else None
                if raw is not None:
                    try:
                        part = json.loads(raw)
                    except ValueError:
                        part = {"status": "unreadable"}
                    mine["parts"].append({"day": s.day.isoformat(), "status": part.get("status"),
                                          "decided_since": rec is not None})
                tau = LR.tau_of(view, learner, s.day)
                first = LR.house_receipt(view, learner, s.day)
                if rec is None and first is not None and tau is not None and tau > S.parse_iso(P.REGISTERED_AT_7):
                    try:
                        finished = S.parse_iso(str(first["finished_at"]))
                    except (TypeError, ValueError):
                        continue
                    if moment - finished > dt.timedelta(hours=OWED_HOURS):
                        mine["owed"].append(s.day.isoformat())
            if "learner_fits" in tables:
                live = [dict(r) for r in db.execute("SELECT day, status, n_rows, n_sessions, train_last FROM learner_fits "
                                                    "WHERE program=? AND version=? AND kind='live' ORDER BY day DESC "
                                                    "LIMIT ?", (learner.id, learner.version, WARM_SESSIONS_MAX))]
                if live:
                    last = live[0]
                    day = dt.date.fromisoformat(str(last["day"]))
                    back = C.previous(view, day, 1 if learner.entry_at == "open" else 2)
                    want = back[0].day.isoformat() if back else None
                    mine["lag"] = {"day": last["day"], "want": want, "trained_through": last.get("train_last"),
                                   "lagging": want is not None and (last.get("train_last") or "") < want}
                    mine["warm"] = {"live": len(live), "unmet": sum(1 for r in live if r["status"] == "warmup")}
            for s in sessions[-2:]:
                raw = view.meta(LR.RECOMPUTE_KEY.format(day=s.day.isoformat()))
                if raw is None:
                    continue
                try:
                    got = json.loads(raw).get(f"{learner.id}@v{learner.version}") or {}
                except ValueError:
                    got = {"status": "unreadable"}
                mine["recompute"].append({"day": s.day.isoformat(), "status": got.get("status"),
                                          "cause": str(got.get("cause") or "")[:200]})
            out["learners"][learner.id] = mine
        return out
    with guard.readonly():
        return guard.read(path, read)


def judge(now: float, f: dict[str, Any] | None) -> dict[str, Any]:
    """The cause's answer in league/ops/evl_health.py's shape."""
    if f is None:
        return {"stalled": False, "judged": False, "what": "Not judged: no PREREG-EVL-7 learner is registered "
                "(REGISTERED_AT_7 is None) or the lane has no store.", "numbers": {"judged": False}, "doing": DOING,
                "owner_step": None, "onset": None}
    said: list[str] = []
    numbers: dict[str, Any] = {"judged": True}
    for pid, m in f["learners"].items():
        open_parts = [p for p in m["parts"] if not p["decided_since"]]
        for p in m["parts"]:
            said.append(f"{pid}'s part of {p['day']} {p['status']} (never traded at that auction; "
                        f"{'decided since by itself' if p['decided_since'] else 'not decided by itself yet'})")
        if m["owed"]:
            said.append(f"{pid} owes its own decision of {', '.join(m['owed'])} (the House's decision finished over "
                        f"{OWED_HOURS:g} h ago)")
        lag = m.get("lag") or {}
        if lag.get("lagging"):
            said.append(f"{pid}'s live decision of {lag['day']} trained through {lag.get('trained_through') or 'no row'}, "
                        f"not {lag['want']} (its training lags: the evening score?)")
        warm = m.get("warm") or {}
        if warm.get("live", 0) >= WARM_SESSIONS_MAX and warm.get("unmet", 0) >= WARM_SESSIONS_MAX:
            said.append(f"{pid} is still in its warm-up after {warm['live']} live decisions")
        for r in m["recompute"]:
            if r["status"] == "mismatch":
                said.append(f"{pid}'s nightly recompute of {r['day']} MISMATCHED on unchanged inputs: {r['cause']}")
        numbers[pid] = {"parts_failed": len(m["parts"]), "parts_open": len(open_parts), "owed": len(m["owed"]),
                        "lagging": bool(lag.get("lagging")), "warmup": warm,
                        "mismatch": sum(1 for r in m["recompute"] if r["status"] == "mismatch")}
    stalled = bool(said)
    what = ("PREREG-EVL-7's learners: " + "; ".join(said) + ".") if stalled else \
        "PREREG-EVL-7's learners decided every auction they owe, on fresh training rows, with no recompute mismatch."
    return {"stalled": stalled, "judged": True, "what": what[:1200], "numbers": numbers, "doing": DOING,
            "owner_step": None, "onset": None}


def check(root: str | Path, now: float) -> dict[str, Any]:
    return judge(now, facts(root, now))


__all__ = ["CAUSE", "DOING", "check", "facts", "judge", "OWED_HOURS", "LOOK_SESSIONS", "WARM_SESSIONS_MAX"]
