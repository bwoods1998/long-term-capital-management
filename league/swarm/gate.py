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
import secrets
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
        #: No Gym job survives its process: a look marked in flight before this moment is owed again.
        self.started_at = clock()

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
                                 max_output=int(self.cfg.get("review_max_output_tokens", 6000)), effort="medium", need_usd=0.5,
                                 desk=f"{fam['id']}:review", cap_usd_day=float(self.cfg.get("review_usd_day", 1.0)))
        verdict = (answer.get("json") or {}).get("verdict")
        return {"verdict": verdict if verdict in ("pass", "fail") else "unclear",
                "reasons": [str(r)[:300] for r in ((answer.get("json") or {}).get("reasons") or [])][:6],
                "route": answer.get("route"), "model": answer.get("model"), "cost_usd": answer.get("cost_usd")}

    # ------------------------------------------------------------------ the audit
    def audit(self, fam: Mapping[str, Any], version: Mapping[str, Any], *, attempt: int = 0) -> dict[str, Any]:
        """The gate's audit (plan: GPT-6 Astra, high, standard) through the gateway when the OpenAI month has room; else a
        SECOND, DIFFERENT model on Sail (`audit_sail_profile`, Kimi-K3 balanced: the reviewer is DeepSeek-V4-Pro), never a
        pass-through."""
        model = self.cfg.get("audit_openai_model", "gpt-6-astra")
        need = float(self.cfg.get("audit_need_usd", 1.0))
        use_openai = bool(model) and self.router.openai_room() >= need
        user = (f"AUDIT. Family {fam['id']}: {fam['mechanism']}\nStructure {fam['structure']}, roots {', '.join(fam['roots'])}.\n\n"
                f"```python\n{version['code']}\n```\nPARAMS overrides: {json.dumps(version.get('params') or {})}")
        answer = self.router.ask(role="audit", system=REVIEW, user=user, family=fam["id"],
                                 key=f"swarm:{fam['id']}:audit:{version['n']}:{attempt}", openai_model=model if use_openai else None,
                                 sail_profile=str(self.cfg.get("audit_sail_profile", "k3_balanced")),
                                 max_output=int(self.cfg.get("review_max_output_tokens", 6000)), effort="high", need_usd=need,
                                 desk=f"{fam['id']}:review", cap_usd_day=float(self.cfg.get("review_usd_day", 1.0)))
        verdict = (answer.get("json") or {}).get("verdict")
        return {"verdict": verdict if verdict in ("pass", "fail") else "unclear",
                "reasons": [str(r)[:300] for r in ((answer.get("json") or {}).get("reasons") or [])][:6],
                "route": answer.get("route"), "model": answer.get("model"), "cost_usd": answer.get("cost_usd")}

    def outcome(self, fid: str, sha: str, result: str) -> None:
        """What the gate did with a version (refused, failed, passed, waiting, demoted): the live path runs a Gym-band
        family's validated version as tuition only while this says nothing worse than waiting (`bands.read`)."""
        self.store.set_state(fid, gate_outcome={"sha": sha, "result": result, "at": self.clock()})

    def refuse(self, fam: Mapping[str, Any], n: int, sha: str, stage: str, reasons: list[str], out: dict[str, Any]) -> None:
        """A refusal, recorded; the version's gate place is cleared only if it is still the one validated."""
        self.store.refuse(fam["id"], n, stage, "; ".join(reasons) or f"refused by the {stage}")
        if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, gated_sha=sha, gate_ready=False):
            return
        self.outcome(fam["id"], sha, "refused")
        self.tell(fam["id"], f"fail (the {stage}: " + "; ".join(reasons)[:400] + ")")
        out["refused"].append(fam["id"])

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
        limit = float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 1200
        for fam in self.store.families():
            state = fam.get("state") or {}
            inflight = state.get("look_inflight") or {}
            if inflight.get("sha"):
                at = float(inflight.get("at") or 0)
                if at < self.started_at or self.clock() - at > limit:
                    # Its job died with a process (no Gym job survives one), or never came back: the look is owed again,
                    # if its version is still the one validated (`owe`); a superseded version's marker is just dropped.
                    self.owe(fam["id"], int(inflight.get("n") or 0), str(inflight["sha"]), marker=inflight)
                    fam = self.store.family(fam["id"]) or fam
                    state = fam.get("state") or {}
            if state.get("look_inflight"):
                continue  # one look per family in flight; its reservation must survive until it resolves
            if fam.get("retired_at") or fam["band"] != "gym" or not state.get("gate_ready"):
                continue
            image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
            if state.get("validation_image") != image or state.get("validation_bundle") != bundle:
                continue  # the tournament owes validation on the current data before any holdout is opened
            n = state.get("validation_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            sha = run_sha(version)
            if self.store.looked(sha) or state.get("gated_sha") == sha:
                continue
            if (state.get("look_inflight") or {}).get("sha") == sha:
                continue  # its look is in flight
            if self.store.lineage_looks(fam["id"], include_inflight=True) >= evidence.LOOKS_PER_LINEAGE:
                if self.store.lineage_looks(fam["id"]) >= evidence.LOOKS_PER_LINEAGE:
                    self.refuse(fam, n, sha, "rations", ["the lineage's three holdout looks are spent"], out)
                else:
                    out["waiting"].append(fam["id"])
                continue
            review = state.get("review") if (state.get("review") or {}).get("sha") == sha else None
            if review is None:  # the review, once a version (kept, so an audit asked again does not redo it)
                if not self._review_current(fam["id"], n, image, bundle):
                    continue
                try:
                    review = self.review(fam, version)
                except Exception as exc:  # noqa: BLE001 - no reviewer, no look
                    self.store.event("swarm.gate", fam["id"], {"action": "review_error", "version": n, "error": str(exc)[:300]})
                    continue
                self.store.event("swarm.gate", fam["id"], {"action": "review", "version": n, **review,
                                                           "not_the_plans_reviewer": review.get("route") != "openai"})
                if review["verdict"] == "unclear":
                    attempts = int(self.store.get("review_attempt:" + fam["id"], 0)) + 1
                    self.store.put("review_attempt:" + fam["id"], attempts)
                    if attempts < 3:
                        continue
                    review = {**review, "verdict": "fail", "reasons": ["the reviewer could not reach a verdict three times"]}
                review = {**review, "sha": sha, "version": n}
                if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, review=review):
                    continue  # the tournament validated a newer version meanwhile: this one is not the gate's
            if review["verdict"] == "pass" and "audit" not in review:  # the audit: a second reader, before any look
                if not self._review_current(fam["id"], n, image, bundle):
                    continue  # the paid review remains evidence; a terminal family starts no new paid stage
                attempts = int(self.store.get("audit_attempt:" + sha, 0))
                try:
                    audit = self.audit(fam, version, attempt=attempts)
                except Exception as exc:  # noqa: BLE001
                    self.store.event("swarm.gate", fam["id"], {"action": "audit_error", "version": n, "error": str(exc)[:300]})
                    continue
                self.store.event("swarm.gate", fam["id"], {"action": "audit", "version": n, **audit})
                if audit["verdict"] == "unclear":
                    self.store.put("audit_attempt:" + sha, attempts + 1)
                    if attempts + 1 < 3:
                        continue  # asked again next round, like an unclear review
                    audit = {**audit, "verdict": "fail", "reasons": ["the audit could not reach a verdict three times"]}
                review = {**review, "audit": audit}
                if audit["verdict"] != "pass":
                    review = {**review, "verdict": "fail", "stage": "audit",
                              "reasons": audit.get("reasons") or ["the audit could not reach a verdict"]}
                if review.get("route") != "openai" or audit.get("route") != "openai":
                    self.store.event("swarm.status", fam["id"], {
                        "action": "not_the_plans_reviewer", "alert": True, "version": n,
                        "review": review.get("model"), "audit": audit.get("model"),
                        "text": "a holdout look was reviewed without the plan's OpenAI models (GPT-6 Sol and Astra): "
                                "the OpenAI month has no room, so Sail models stood in"})
                if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, review=review):
                    continue
            if not self._review_current(fam["id"], n, image, bundle):
                continue
            if review["verdict"] != "pass":
                self.refuse(fam, n, sha, review.get("stage") or "review", review.get("reasons") or [], out)
                continue
            if not self.settings.get("gym", {}).get("gate_checkpoint"):
                out["waiting"].append(fam["id"])
                self.outcome(fam["id"], sha, "waiting")
                self.tell(fam["id"], "waiting (reviewed; the gate image is not ready yet)")
                continue
            look = self.look(fam, version, sha)
            if look is not None:
                out["looked"].append({"family": fam["id"], "passed": look})
            if self.alarm():
                break
        return out

    def _review_current(self, fid: str, n: int, image: Any, bundle: Any) -> bool:
        fam = self.store.family(fid) or {}
        state = fam.get("state") or {}
        return bool(not fam.get("retired_at") and fam.get("band") == "gym" and state.get("gate_ready")
                    and state.get("validation_version") == n and state.get("validation_image") == image
                    and state.get("validation_bundle") == bundle)

    def look(self, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
        """The one holdout look. None when the gate box did not run it (no look is spent). The version is marked as
        looked at BEFORE the box runs it, so a slow look is never started twice; one that lands after the gate stopped
        waiting is recorded and judged when it lands (`finish`), against the validation it was sent for."""
        n = int(version["n"])
        state = fam.get("state") or {}
        vsharpe = (state.get("validation_numbers") or {}).get("sharpe_daily")
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        marker = {"sha": sha, "n": n, "at": self.clock(), "token": secrets.token_hex(8)}
        # Compare-and-set under the store's lock: only the version still validated is looked at; the marker says a look
        # is in flight (not `gated_sha`: a look cut off by a restart must be owed, not forgotten).
        with self.store.atomic():
            current = self.store.family(fam["id"]) or {}
            if current.get("retired_at") or self.store.looked(sha) or \
                    self.store.lineage_looks(fam["id"], include_inflight=True) >= evidence.LOOKS_PER_LINEAGE:
                return None
            if not self.store.compare_and_set_state(fam["id"], {"validation_version": n, "validation_image": image, "validation_bundle": bundle,
                                                               "look_inflight": None}, gate_ready=False, look_inflight=marker):
                return None
        job = GymJob(family=fam["id"], version=n, code=version["code"], params=version.get("params") or {}, window="holdout",
                     roots=tuple(fam["roots"]), gate=f"holdout look {fam['id']} v{n}", purpose="holdout", priority=10.0)
        try:
            result = self.pool.run(job, timeout=float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 600,
                                   late=lambda r: self.finish(fam["id"], version, sha, r, validation_sharpe=vsharpe,
                                                              validation_image=image, validation_bundle=bundle, marker=marker),
                                   late_fail=lambda why: self.owe(fam["id"], n, sha, marker=marker))
        except PoolError as exc:
            self.store.event("swarm.gate", fam["id"], {"action": "look_failed", "version": n, "error": str(exc)[:300]})
            if job.result is None and job.late is None:  # it never ran (or the Gym failed it): the look is still owed
                self.owe(fam["id"], n, sha, marker=marker)
            return None
        return self.finish(fam["id"], version, sha, result, validation_sharpe=vsharpe, validation_image=image,
                           validation_bundle=bundle, marker=marker)

    def clear_marker(self, fid: str, sha: str) -> bool:
        """Drop the in-flight marker only if it is this look's (a newer version's look may be out meanwhile)."""
        marker = ((self.store.family(fid) or {}).get("state") or {}).get("look_inflight")
        if not marker or marker.get("sha") != sha:
            return False
        return self.store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None)

    def owe(self, fid: str, n: int, sha: str, *, marker: Mapping[str, Any] | None = None) -> None:
        """The look did not happen. Its marker goes; if the version is still the one validated it is owed one again, three
        tries, and after the third it is refused as the Gym could not look (one refusal and one alert, never forgotten).
        A superseded version is owed nothing: no try is counted, nothing is refused."""
        with self.store.atomic():
            state = (self.store.family(fid) or {}).get("state") or {}
            if marker is not None and state.get("look_inflight") != marker:
                return  # an old attempt's callback cannot cancel or count a newer attempt
            self._owe(fid, n, sha)

    def _owe(self, fid: str, n: int, sha: str) -> None:
        self.clear_marker(fid, sha)
        if self.store.looked(sha):
            return
        fam = self.store.family(fid) or {}
        if fam.get("retired_at") or (fam.get("state") or {}).get("validation_version") != n:
            return
        tries = int(self.store.get(f"look_tries:{sha}", 0)) + 1
        self.store.put(f"look_tries:{sha}", tries)
        if tries < 3:
            self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=None, gate_ready=True)
        elif self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha, gate_ready=False) and tries == 3:
            self.store.refuse(fid, n, "gym", "the gate box could not make this holdout look three times")
            self.store.event("swarm.status", fid, {"action": "look_failed_three_times", "alert": True, "version": n,
                                                   "text": "the gate box could not make a holdout look three times"})

    def finish(self, fid: str, version: Mapping[str, Any], sha: str, result: Mapping[str, Any], *,
               validation_sharpe: Any = None, validation_image: Any = None, validation_bundle: Any = None,
               marker: Mapping[str, Any] | None = None) -> bool | None:
        """Record a holdout result as the look it is (once: a second result for the same version is ignored) and answer.
        A result the Gym could not produce (an engine error, no data) is no look: it stays owed. Nothing here undoes a
        newer validation the tournament wrote while the look ran."""
        with self.store.atomic():
            return self._finish(fid, version, sha, result, validation_sharpe=validation_sharpe, validation_image=validation_image,
                                validation_bundle=validation_bundle, marker=marker)

    def _finish(self, fid: str, version: Mapping[str, Any], sha: str, result: Mapping[str, Any], *,
                validation_sharpe: Any, validation_image: Any, validation_bundle: Any, marker: Mapping[str, Any] | None) -> bool | None:
        fam = self.store.family(fid)
        if fam is None or self.store.looked(sha):
            return None
        n = int(version["n"])
        if result.get("status") in ("error", "no_data"):
            self.store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "status": result.get("status")})
            self.owe(fid, n, sha, marker=marker)
            return None
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        self.store.add_run(fid, n, result, window="holdout", stress=1.0, purpose="holdout", program_years=years)
        previous = [x["p_value"] for x in self.store.looks() if x["p_value"] is not None]
        line = evidence.holdout_line(result, validation_sharpe=validation_sharpe, previous_ps=previous, seed=sha)
        self.store.add_look(fid, n, sha, passed=line["passed"], p_value=line["p"], detail=line)
        self.clear_marker(fid, sha)  # only its own: a newer version's look may be in flight
        self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha)
        self.store.event("swarm.gate", fid, {"action": "look", "version": n, "passed": line["passed"],
                                             "_line": line})  # the numbers stay private (underscore)
        if not line["numbers"].get("holm_reachable", True):
            self.store.event("swarm.status", None, {"action": "holm_unreachable", "looks": len(previous) + 1})
        self.tell(fid, "pass" if line["passed"] else "fail")
        self.outcome(fid, sha, "passed" if line["passed"] else "failed")
        has_image = callable(getattr(self.pool, "image", None))
        has_bundle = callable(getattr(self.pool, "bundle", None))
        image = self.pool.image("gym") if has_image else None
        gate_image = self.pool.image("gate") if has_image else None
        bundle = self.pool.bundle() if has_bundle else None
        # Opening sealed data consumes the look even when its image was replaced while the job ran. Only a result
        # actually produced by the current gate data and engine can promote. Identity-less pools exist in tests only.
        current_holdout = ((not has_image or (gate_image is not None and result.get("gym_image") == gate_image))
                           and (not has_bundle or (bundle is not None and result.get("gym_bundle") == bundle)))
        if line["passed"] and fam["band"] == "gym" and not fam.get("retired_at") and validation_image == image \
                and validation_bundle == bundle and current_holdout:
            self.store.set_state(fid, banded_version=n, banded_sha=version["sha"], banded_at=self.clock())
            self.store.set_band(fid, "candidate", reason="passed its holdout look")
        return bool(line["passed"])

    # ------------------------------------------------------------------ the nightly forward
    def forward_target(self) -> dict[str, str] | None:
        ready = self.settings.get("forward", {}).get("ready") or {}
        if ready.get("day") and ready.get("gate_checkpoint") == self.settings.get("gym", {}).get("gate_checkpoint"):
            target = {"day": ready["day"], "checkpoint": ready["gate_checkpoint"]}
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
            if bundle is not None:
                target["bundle"] = bundle
            return target
        return None

    def forward_pending(self, target: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [f for f in self.store.families(alive=True) if f["band"] in ("candidate", "probe", "sized")
                and (f.get("state") or {}).get("forward_replay") !=
                {"target": target, "version": (f.get("state") or {}).get("banded_version") or f.get("best_version")}]

    def forward_due(self) -> bool:
        now = self.clock()
        target = self.forward_target()
        if target is not None:
            attempt = self.store.get("forward_attempt") or {}
            return bool(self.forward_pending(target)) and (attempt.get("target") != target or
                   now - float(attempt.get("at") or 0) >= float(self.settings.get("forward", {}).get("every_seconds", 3600)))
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
        after = int(self.settings.get("forward", {}).get("after_hour_utc", 7))
        attempted = self.store.get("forward_legacy_attempt") or {}
        banded = any(f["band"] in ("candidate", "probe", "sized") for f in self.store.families(alive=True))
        return bool(banded and self.settings.get("gym", {}).get("gate_checkpoint")) and today.hour >= after and \
            self.store.get("forward_day") != today.date().isoformat() and (attempted.get("day") != today.date().isoformat() or
            now - float(attempted.get("at") or 0) >= float(self.settings.get("forward", {}).get("every_seconds", 3600)))

    def forward(self) -> dict[str, Any]:
        target = self.forward_target()
        if target is not None:
            return self.forward_ready(target)
        now = self.clock()
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        self.store.put("forward_legacy_attempt", {"day": today, "at": now})
        banded = [f for f in self.store.families(alive=True) if f["band"] in ("candidate", "probe", "sized")]
        out: dict[str, Any] = {"families": len(banded), "trades": 0, "moves": []}
        if not banded or not self.settings.get("gym", {}).get("gate_checkpoint"):
            return out
        jobs = []
        for fam in banded:
            n = (fam.get("state") or {}).get("banded_version") or fam.get("best_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                out.setdefault("failed", []).append(fam["id"])
                continue
            job = GymJob(family=fam["id"], version=int(n), code=version["code"], params=version.get("params") or {}, window="forward",
                         roots=tuple(fam["roots"]), gate="nightly forward replay", purpose="forward", priority=5.0)
            jobs.append((fam, int(n), self.pool.submit(job)))
        for fam, n, job in jobs:
            try:
                result = self.pool.wait(job, float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 600,
                                        late=lambda r, fid=fam["id"], n=n: self.record_forward(fid, n, r))
            except PoolError as exc:
                out.setdefault("errors", {})[fam["id"]] = str(exc)[:200]
                continue
            added = self.record_forward(fam["id"], n, result)
            if added is None:
                out.setdefault("failed", []).append(fam["id"])
            else:
                out["trades"] += added
        for fam in banded:
            move = self.judge_forward(fam["id"])
            if move:
                out["moves"].append(move)
        if jobs and not out.get("failed") and not out.get("errors"):
            self.store.put("forward_day", today)
        self.store.event("swarm.gate", None, {"action": "forward", **out})
        return out

    def forward_ready(self, target: Mapping[str, Any]) -> dict[str, Any]:
        """Replay a delivered checkpoint, retrying only families whose version has not finished it successfully."""
        self.store.put("forward_attempt", {"target": target, "at": self.clock()})
        families = self.forward_pending(target)
        out: dict[str, Any] = {"families": len(families), "trades": 0, "moves": [], "target": target}
        roots = set((self.settings.get("forward", {}).get("ready") or {}).get("roots") or [])
        jobs = []
        for fam in families:
            n = (fam.get("state") or {}).get("banded_version") or fam.get("best_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code") or not set(fam["roots"]).issubset(roots):
                out.setdefault("failed", []).append(fam["id"])
                continue
            job = GymJob(family=fam["id"], version=int(n), code=version["code"], params=version.get("params") or {},
                         window="forward", roots=tuple(fam["roots"]), end=target["day"], gate="nightly forward replay",
                         purpose="forward", priority=5.0)
            jobs.append((fam["id"], int(n), self.pool.submit(job)))
        for fid, n, job in jobs:
            try:
                result = self.pool.wait(job, float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 600,
                                        late=lambda r, fid=fid, n=n: self.record_ready_forward(fid, n, r, target))
            except PoolError as exc:
                out.setdefault("errors", {})[fid] = str(exc)[:200]
                continue
            added = self.record_ready_forward(fid, n, result, target, judge=False)
            if added is None:
                out.setdefault("failed", []).append(fid)
            else:
                out["trades"] += added
            move = self.judge_forward(fid)
            if move:
                out["moves"].append(move)
        self.store.event("swarm.gate", None, {"action": "forward", **out})
        return out

    def record_ready_forward(self, fid: str, n: int, result: Mapping[str, Any], target: Mapping[str, Any], *,
                             judge: bool = True) -> int | None:
        self.store.add_run(fid, n, result, window="forward", stress=1.0, purpose="forward")
        days = {str(row[0]) for row in result.get("daily") or [] if row}
        if target != self.forward_target() or result.get("gym_image") != target["checkpoint"] or \
                result.get("gym_bundle") != target.get("bundle") or target["day"] not in days:
            self.store.event("swarm.gate", fid, {"action": "forward_failed", "version": n,
                                                 "why": "the replay does not cover the ready checkpoint and day"})
            return None
        added = self.record_forward(fid, n, result, record=False)
        if added is not None:
            self.store.set_state(fid, forward_replay={"target": target, "version": n})
            if not self.forward_pending(target):
                self.store.put("forward_day", target["day"])
                self.store.put("forward_completed", {"target": target, "at": self.clock()})
            if judge:
                self.judge_forward(fid)
        return added

    def record_forward(self, fid: str, n: int, result: Mapping[str, Any], *, record: bool = True) -> int | None:
        """A nightly replay's run (a trial) and, ONLY when it ran cleanly, its trades as version n's nightly record (the
        latest good run replaces that version's nightly record: every forward day is rerun each night). A replay that
        erred, found no data or was disqualified leaves the record as it was (None, and a `forward_failed` event)."""
        if record:
            self.store.add_run(fid, n, result, window="forward", stress=1.0, purpose="forward")
        if result.get("status") != "ok":
            self.store.event("swarm.gate", fid, {"action": "forward_failed", "version": n, "status": result.get("status")})
            return None
        # The forward view carries each trade's day, P&L and maximum loss (no ids): a trade is (version, day, its place
        # that day).
        trades, seen = [], {}
        for t in result.get("trades") or []:
            if t.get("pnl") is None:
                continue
            k = seen[t.get("day")] = seen.get(t.get("day"), -1) + 1
            trades.append({"id": f"v{n}:{t.get('day')}:{k}", "day": t.get("day"), "pnl": t.get("pnl"), "max_loss": t.get("max_loss")})
        return self.store.replace_forward(fid, "nightly", trades, version=n)

    def judge_forward(self, fid: str) -> dict[str, Any] | None:
        """The banded version's forward record (`evidence.forward_record`: its own rows, one source a day); a Candidate
        whose record is negative goes back to the Gym, and its version is never tuition again."""
        with self.store.atomic():
            return self._judge_forward(fid)

    def _judge_forward(self, fid: str) -> dict[str, Any] | None:
        fam = self.store.family(fid)
        if fam is None or fam["band"] not in ("candidate", "probe", "sized"):
            return None
        state = fam.get("state") or {}
        n = state.get("banded_version")
        record = evidence.forward_record(self.store.forward(fid), version=n)
        self.store.set_state(fid, forward=record)
        if record["negative"] and fam["band"] == "candidate":
            if self.store.set_band(fid, "gym", reason=f"its forward record turned negative over {record['trades']} trades") is None:
                return None
            if state.get("banded_sha"):
                version = self.store.version(fid, n)
                if version is not None:
                    self.outcome(fid, run_sha(version), "demoted")
            return {"family": fid, "to": "gym"}
        return None


__all__ = ["Gate", "run_sha", "REVIEW"]
