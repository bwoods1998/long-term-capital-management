"""The gate and the nightly forward replays: the only code that opens sealed days, on gate boxes only.

THE GATE (when a family's validated best meets the validation line):
1. RATIONS: one holdout look per program version (code + parameters), at most three per LINEAGE (a fork
   inherits its parent's looks); the leakage alarm (>= 10 looks, > 30% passing) stops the gate.
2. THE REVIEW: GPT-6 Sol through the gateway when OpenAI has room, else DeepSeek-V4-Pro balanced on Sail,
   reads the program for lookahead, leakage (calendar recognition, hard-coded regimes) and fill abuse. A
   failed review is a recorded refusal and costs no look. An unclear answer is asked again next round.
3. ONE HOLDOUT LOOK on a gate box (a fork of the gate image; the Gym image has no holdout days), judged by
   the plan's holdout line (`evidence.holdout_line`, with Holm-Bonferroni across every look the swarm has
   made). The researcher is told PASS or FAIL, never a number.
4. A pass makes the family a Candidate (live shadow). Candidate <-> Probe <-> Sized is the LIVE PATH's
   (the Money table), written through `SwarmStore.set_band`; the swarm never makes a Probe or a Sized.

THE NIGHTLY FORWARD: once a day (after `forward.after_hour_utc`), every Candidate, Probe and Sized family's
banded version runs over the forward days the gate image holds; the trades are the family's `nightly`
forward record (the live path adds `shadow` and `real` through `SwarmStore.add_forward`). Forward records
move bands and never select among Gym programs: a CANDIDATE whose forward record (nightly + shadow + real)
is negative over 20 trades goes back to the Gym; a Probe or Sized family's record is kept in its state
(`forward`, flagged `negative`) for the live path, which alone moves those bands.

Every step is a `swarm.gate` event; band moves are `swarm.band` events (the site's news).
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from typing import Any, Callable, Mapping

from . import evidence
from .pool import GymJob, PoolError
from .store import SwarmStore, dumps

REVIEW = """You review option-trading programs before they meet sealed data. A program is one Python file (NEEDS, PARAMS,
decide(ctx)) that runs in a replay of recorded one-minute option quotes and then, unchanged, on live quotes and real
money. Refuse it (verdict "fail") for any of:
- LOOKAHEAD: anything that could know the future inside the replay (it only sees ctx; flag code that tries to reach
  outside ctx, reads module state written by another run, or infers future data).
- LEAKAGE: recognizing the calendar or a specific period. Refuse ABSOLUTE PRICE-LEVEL CONSTANTS (an underlying or
  strike level, e.g. "SPY above 550", identifies the years), CALENDAR RECONSTRUCTION (counting sessions, weekdays or
  event flags across a run to work out the date or the year), regime switches keyed to values that identify periods,
  and any table of dates, levels or events. Relative measures (returns, ratios, vol, moneyness, z-scores) are fine.
- FILL ABUSE: relying on fills the live market will not give (limits far through the mid expected to fill, sizes beyond
  the quoted size, orders sent after the venue's cutoffs, churning cancels).
- DANGER on real money: naked short exposure, structures that cannot be closed in one order, unbounded order loops.
Otherwise pass it. Reply with ONE JSON object: {"verdict": "pass" or "fail", "reasons": ["..."], "notes": "..."}."""


def run_sha(version: Mapping[str, Any]) -> str:
    return hashlib.sha256((str(version["sha"]) + dumps(version.get("params") or {})).encode()).hexdigest()


class Gate:
    def __init__(self, store: SwarmStore, pool: Any, router: Any, settings: Mapping[str, Any], *,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.pool = pool
        self.router = router
        self.settings = settings
        self.clock = clock

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("gate", {})

    def due(self) -> bool:
        return self.clock() - float(self.store.get("gate_at", 0.0) or 0.0) >= float(self.cfg.get("every_seconds", 300))

    def alarm(self) -> bool:
        looks = self.store.looks()
        return evidence.leakage_alarm(len(looks), sum(1 for x in looks if x["passed"]))

    def tell(self, fid: str, answer: str) -> None:
        """What the researcher hears (its status line): pass or fail, and for a refusal before the look, why."""
        self.store.set_state(fid, gate=answer)

    # ------------------------------------------------------------------ the review
    def review(self, fam: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
        user = (f"Family {fam['id']}: {fam['mechanism']}\nStructure {fam['structure']}, roots {', '.join(fam['roots'])}.\n\n"
                f"```python\n{version['code']}\n```\nPARAMS overrides: {json.dumps(version.get('params') or {})}")
        answer = self.router.ask(role="review", system=REVIEW, user=user, family=fam["id"],
                                 key=f"swarm:{fam['id']}:review:{version['n']}:{self.store.get('review_attempt:' + fam['id'], 0)}",
                                 openai_model=self.cfg.get("review_openai_model"), sail_profile=str(self.cfg.get("review_sail_profile",
                                                                                                                   "pro_balanced")),
                                 max_output=int(self.cfg.get("review_max_output_tokens", 6000)), effort="medium", need_usd=0.5)
        verdict = (answer.get("json") or {}).get("verdict")
        return {"verdict": verdict if verdict in ("pass", "fail") else "unclear",
                "reasons": [str(r)[:300] for r in ((answer.get("json") or {}).get("reasons") or [])][:6],
                "route": answer.get("route"), "model": answer.get("model"), "cost_usd": answer.get("cost_usd")}

    # ------------------------------------------------------------------ one round
    def run(self) -> dict[str, Any]:
        self.store.put("gate_at", self.clock())
        out: dict[str, Any] = {"looked": [], "refused": [], "waiting": []}
        if self.alarm():
            if not self.store.get("leakage_alarm"):
                self.store.put("leakage_alarm", {"at": self.clock(), "looks": len(self.store.looks())})
                self.store.event("swarm.gate", None, {"action": "leakage_alarm", "looks": len(self.store.looks()),
                                                      "passes": sum(1 for x in self.store.looks() if x["passed"])})
            out["alarm"] = True
            return out
        for fam in self.store.families(alive=True):
            state = fam.get("state") or {}
            if fam["band"] != "gym" or not state.get("gate_ready"):
                continue
            n = state.get("validation_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            sha = run_sha(version)
            if self.store.looked(sha) or state.get("gated_sha") == sha:
                continue
            if self.store.lineage_looks(fam["id"]) >= evidence.LOOKS_PER_LINEAGE:
                self.store.refuse(fam["id"], n, "rations", "the lineage's three holdout looks are spent")
                self.store.set_state(fam["id"], gated_sha=sha, gate_ready=False)
                self.tell(fam["id"], "fail (the lineage's three holdout looks are spent)")
                out["refused"].append(fam["id"])
                continue
            if not self.settings.get("gym", {}).get("gate_checkpoint"):
                out["waiting"].append(fam["id"])
                self.tell(fam["id"], "waiting (the gate image is not ready yet)")
                continue
            try:
                review = self.review(fam, version)
            except Exception as exc:  # noqa: BLE001 - no reviewer, no look
                self.store.event("swarm.gate", fam["id"], {"action": "review_error", "version": n, "error": str(exc)[:300]})
                continue
            self.store.event("swarm.gate", fam["id"], {"action": "review", "version": n, **review})
            if review["verdict"] == "unclear":
                attempts = int(self.store.get("review_attempt:" + fam["id"], 0)) + 1
                self.store.put("review_attempt:" + fam["id"], attempts)
                if attempts < 3:
                    continue
                review = {**review, "verdict": "fail", "reasons": ["the reviewer could not reach a verdict three times"]}
            if review["verdict"] == "fail":
                self.store.refuse(fam["id"], n, "review", "; ".join(review["reasons"]) or "refused by the review")
                self.store.set_state(fam["id"], gated_sha=sha, gate_ready=False)
                self.tell(fam["id"], "fail (the review: " + "; ".join(review["reasons"])[:400] + ")")
                out["refused"].append(fam["id"])
                continue
            look = self.look(fam, version, sha)
            if look is not None:
                out["looked"].append({"family": fam["id"], "passed": look})
            if self.alarm():
                break
        return out

    def look(self, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
        """The one holdout look. None when the gate box could not run it (no look is spent)."""
        n = int(version["n"])
        job = GymJob(family=fam["id"], version=n, code=version["code"], params=version.get("params") or {}, window="holdout",
                     roots=tuple(fam["roots"]), gate=f"holdout look {fam['id']} v{n}", purpose="holdout", priority=10.0)
        try:
            result = self.pool.run(job, timeout=float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 600)
        except PoolError as exc:
            self.store.event("swarm.gate", fam["id"], {"action": "look_failed", "version": n, "error": str(exc)[:300]})
            return None
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        self.store.add_run(fam["id"], n, result, window="holdout", stress=1.0, purpose="holdout", program_years=years)
        state = fam.get("state") or {}
        previous = [x["p_value"] for x in self.store.looks() if x["p_value"] is not None]
        line = evidence.holdout_line(result, validation_sharpe=(state.get("validation_numbers") or {}).get("sharpe_daily"),
                                     previous_ps=previous, seed=sha)
        self.store.add_look(fam["id"], n, sha, passed=line["passed"], p_value=line["p"], detail=line)
        self.store.set_state(fam["id"], gated_sha=sha, gate_ready=False)
        self.store.event("swarm.gate", fam["id"], {"action": "look", "version": n, "passed": line["passed"],
                                                   "_line": line})  # the numbers stay private (underscore)
        self.tell(fam["id"], "pass" if line["passed"] else "fail")
        if line["passed"]:
            self.store.update_family(fam["id"], best_version=n)
            self.store.set_state(fam["id"], banded_version=n, banded_sha=version["sha"], banded_at=self.clock())
            self.store.set_band(fam["id"], "candidate", reason="passed its holdout look")
        return bool(line["passed"])

    # ------------------------------------------------------------------ the nightly forward
    def forward_due(self) -> bool:
        now = self.clock()
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
        after = int(self.settings.get("forward", {}).get("after_hour_utc", 7))
        return today.hour >= after and self.store.get("forward_day") != today.date().isoformat()

    def forward(self) -> dict[str, Any]:
        now = self.clock()
        self.store.put("forward_day", dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat())
        banded = [f for f in self.store.families(alive=True) if f["band"] in ("candidate", "probe", "sized")]
        out: dict[str, Any] = {"families": len(banded), "trades": 0, "moves": []}
        if not banded or not self.settings.get("gym", {}).get("gate_checkpoint"):
            return out
        jobs = []
        for fam in banded:
            n = (fam.get("state") or {}).get("banded_version") or fam.get("best_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            job = GymJob(family=fam["id"], version=int(n), code=version["code"], params=version.get("params") or {}, window="forward",
                         roots=tuple(fam["roots"]), gate="nightly forward replay", purpose="forward", priority=5.0)
            jobs.append((fam, int(n), self.pool.submit(job)))
        for fam, n, job in jobs:
            try:
                result = self.pool.wait(job, float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 600)
            except PoolError as exc:
                out.setdefault("errors", {})[fam["id"]] = str(exc)[:200]
                continue
            self.store.add_run(fam["id"], n, result, window="forward", stress=1.0, purpose="forward")
            # The forward view carries each trade's day, P&L and maximum loss (no ids): a trade is (version, day, its place
            # that day). Every forward day is rerun each night, so the latest run replaces the nightly record whole.
            trades, seen = [], {}
            for t in result.get("trades") or []:
                if t.get("pnl") is None:
                    continue
                k = seen[t.get("day")] = seen.get(t.get("day"), -1) + 1
                trades.append({"id": f"v{n}:{t.get('day')}:{k}", "day": t.get("day"), "pnl": t.get("pnl"), "max_loss": t.get("max_loss")})
            out["trades"] += self.store.replace_forward(fam["id"], "nightly", trades)
        for fam in banded:
            move = self.judge_forward(fam["id"])
            if move:
                out["moves"].append(move)
        self.store.event("swarm.gate", None, {"action": "forward", **out})
        return out

    def judge_forward(self, fid: str) -> dict[str, Any] | None:
        fam = self.store.family(fid)
        if fam is None or fam["band"] not in ("candidate", "probe", "sized"):
            return None
        record = evidence.forward_record(self.store.forward(fid))
        self.store.set_state(fid, forward=record)
        if record["negative"] and fam["band"] == "candidate":
            self.store.set_band(fid, "gym", reason=f"its forward record turned negative over {record['trades']} trades")
            return {"family": fid, "to": "gym"}
        return None


__all__ = ["Gate", "run_sha", "REVIEW"]
