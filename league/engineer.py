"""Optional helper repair loop. It proposes pure helpers and their tests, follows CI,
and verifies a repair only after the exact files run through an observation window.
Private strategy changes belong to the swarm. The engineer never merges, deploys,
changes money rules, or receives a private program through its code callback.
Interrupted calls retain their cost reservation; forge retries reuse paid proposals.
"""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import ci
from .frontier import MODEL_CEILINGS, FrontierError
from .ledger import now_iso
from .worklist import Job, Worklist

REPO = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).resolve().parent / "engineer.json"
CONTRACT = Path(__file__).resolve().parent / "CONTRACT.md"
#: The sole public repair role. Private strategy work never uses a GitHub proposal.
ROLES = ("engineer",)
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_attempts": 3,
    "max_job_usd": "5.00",
    "admit_priority": 2.0,
    "observe_hours": 24.0,
    "synthetic_observe_minutes": 20.0,
    "min_seconds_between_calls": 1800.0,
    # Measured Sept 22, 2026 on consultations: at 12,000 tokens and "high" effort five of seven
    # spent the whole allowance reasoning and came back incomplete; the auditor at "medium" never has.
    "max_output_tokens": 16000,
    "effort": "medium",
    "step_seconds": 120.0,
    "failure_text_wait_hours": 6.0,
    "canary_timeout_hours": 72.0,
}
#: Refusals that are a protective rule working as designed. The constitution's money rules and the
#: books' risk limits are frozen, so a repair has nothing to change there; the strategy that keeps
#: asking is the thing to fix, and only when it is named as a defect. Read from the production
#: ledger on Sept 22, 2026, where these were five of the fourteen refusal reasons.
PROTECTIVE = ("daily loss", "at risk on one market", "at risk across the live desks", "gross exposure would be",
              "paused for maintenance", "only risk-reducing orders", "trade against the house's own resting order",
              "one account cannot hold both")
#: Refusals caused by House code (seat allocation, reconciliation): outside every role's paths.
CORE_REFUSALS = ("has no seat on the", "is frozen until it reconciles")
#: Legacy program reports are retained as dormant private research work.
STRATEGY_KINDS = ("strategy_defect", "audit_veto")
NEEDS_CORE = "needs core authority"

BRIEF = """You are the options House repair engineer. Fix one reported helper defect using the provided evidence.
You may propose ONLY pure Python helpers in league/tools/ and tests in league/tests/test_tool_*.py.
The role is engineer. Never trade, merge, deploy, change money rules, or publish a program, quote or fitted value.
The swarm's architect owns private strategy changes; report a program defect with needs_core instead.
If the fix needs any other path, return needs_core with its reason and paths. Do not hide the defect with a workaround.
When CI refuses a prior attempt, use its actual failure text and send complete corrected files.
Return one JSON object:
{"summary":"defect, fix and observation", "role":"engineer", "slug":"lowercase-words", "title":"PR title",
 "body":"evidence and validation", "files":[{"path":"...", "content":"whole file"}],
 "needs_core":null}
Use files:[] for no justified change, or needs_core:{"reason":"...","paths":["..."]} for owner work."""


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    return {**DEFAULTS, **{k: v for k, v in (raw if isinstance(raw, dict) else {}).items() if k in DEFAULTS}}


def _files_digest(files: list[dict[str, str]]) -> dict[str, str]:
    return {f["path"]: hashlib.sha256(f["content"].encode("utf-8")).hexdigest() for f in files}


def hold_usd(model: str, request_bytes: int, max_output_tokens: int) -> Decimal:
    """The worst case the campaign will reserve for one call (`Frontier.ask`'s own formula)."""
    input_rate, output_rate = MODEL_CEILINGS.get(model, (Decimal("25"), Decimal("75")))
    return (Decimal(request_bytes + 4096) * input_rate + Decimal(max_output_tokens) * output_rate) / 1000000


class Engineer:
    def __init__(self, frontier: Any, forge: Any, ledger: Any, worklist: Worklist, *, clock: Callable[[], float] = time.time,
                 settings: Mapping[str, Any] | None = None, may_spend: Callable[[], bool] = lambda: True,
                 code_of: Callable[[str], Mapping[str, Any] | None] = lambda agent: None, repo: Path = REPO,
                 evidence: Callable[[], Mapping[str, Any]] = lambda: {}, sources: Any = None, summary_path: Path | None = None,
                 inbox: Path | None = None, evidence_weight: Callable[[Iterable[str]], float] = lambda agents: 1.0):
        from .merton import ProposalFollower
        self.follower = ProposalFollower(forge, ledger, clock=clock)
        self.frontier = frontier
        self.forge = forge
        self.ledger = ledger
        self.worklist = worklist
        self.clock = clock
        self.settings = {**DEFAULTS, **dict(settings or load_settings())}
        self.may_spend = may_spend
        self.code_of = code_of
        self.repo = Path(repo)
        self.evidence = evidence
        self.sources = sources
        #: Where each step leaves the worklist's summary (the state directory's `repairs.json`), so
        #: the queue can be read without opening the ledger. None writes nothing.
        self.summary_path = Path(summary_path) if summary_path else None
        #: A directory where the owner (or `scripts/repair_drill.py`) drops a request file; the
        #: House, the ledger's only writer, turns each into a report on its next step.
        self.inbox = Path(inbox) if inbox else None
        #: How much the forward record of a job's agents raises or lowers its turn (`_by_evidence`).
        self.evidence_weight = evidence_weight
        self._last_step = float("-inf")
        self._last_call: float | None = None
        self._asked = False

    # ------------------------------------------------------------------------ schedule
    def due(self) -> bool:
        return self.clock() - self._last_step >= float(self.settings["step_seconds"])

    def last_call(self) -> float:
        """When the engineer last bought a call. Read from its own `merton.pass` rows the first
        time, so a restart does not reset the pace and buy the next patch at once."""
        if self._last_call is None:
            rows = [e.payload for e in self.ledger.read(kinds="merton.pass", limit=2000, newest=True)
                    if e.payload.get("role") == "engineer" and not e.payload.get("interrupted")]
            paid = [float(r.get("at_epoch") or 0) for r in rows if Decimal(str(r.get("cost_usd") or "0")) > 0]
            self._last_call = max(paid) if paid else float("-inf")
        return self._last_call

    def step(self) -> dict[str, Any]:
        """One bounded unit of work: report what is new, admit, move every job waiting on the
        outside world (free), and make at most one paid attempt. Never raises for one job.

        Switched off (`enabled: false` in `engineer.json`) it still reports -- the sources are
        code and free -- but admits, follows and buys nothing; its jobs keep their states."""
        self._last_step = self.clock()
        out: dict[str, Any] = {"reported": [], "admitted": [], "advanced": [], "attempted": None}
        try:
            out["filed"] = self._read_inbox()
            if self.sources is not None:
                out["reported"] = self.sources.scan()
            if self.settings.get("enabled"):
                self.follower.follow()
                self._work(out)
        finally:
            self._summarize(out)
        return out

    def _read_inbox(self) -> list[str]:
        """Each `<name>.json` in the inbox becomes one report, then `<name>.json.filed`. A drill
        request is `{"drill": "<stamp>"}`; anything else is an operator's report
        `{"key", "kind", "summary", "agents", "severity"}`, admitted whatever its priority."""
        if self.inbox is None or not self.inbox.is_dir():
            return []
        filed = []
        for path in sorted(self.inbox.glob("*.json"))[:20]:
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("not an object")
                if body.get("drill"):
                    key = drill_report(self.worklist, str(body["drill"]))
                else:
                    key = str(body["key"])[:200]
                    self.worklist.report(key=key, kind=str(body.get("kind") or "bug_report"), summary=str(body.get("summary") or key),
                                         evidence=[{"seq": None, "at": "", "agent": "house", "excerpt": str(body.get("evidence") or body.get("summary") or "")}],
                                         agents=[str(a) for a in body.get("agents") or [] if isinstance(a, str)], source="operator",
                                         severity=body.get("severity") or "medium", id=f"repair-inbox:{path.stem}:{digest_of(body)}")
                filed.append(key)
                path.replace(path.with_name(path.name + ".filed"))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                try:
                    path.replace(path.with_name(path.name + ".refused"))
                    path.with_name(path.name + ".why").write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
                except OSError:
                    pass
        return filed

    def _summarize(self, out: Mapping[str, Any]) -> None:
        if self.summary_path is None:
            return
        try:
            body = {"at": now_iso(self.clock), "enabled": bool(self.settings.get("enabled")), "last_step": dict(out),
                    **self.worklist.summary()}
            temporary = self.summary_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
            temporary.replace(self.summary_path)
        except (OSError, TypeError, ValueError):
            pass  # a summary is a convenience; the ledger is the record

    def _work(self, out: dict[str, Any]) -> None:
        out["admitted"] = self.worklist.admit(threshold=float(self.settings["admit_priority"]))
        for job in self.worklist.queue(("reproducing", "patching")):
            self._interrupted(job)
        for job in self.worklist.queue(("testing", "canary", "observing", "verified")):
            moved = self._advance(job)
            if moved:
                out["advanced"].append({"key": job.key, "state": moved})
        out["decided"] = []
        for job in self._by_evidence(self.worklist.queue(("revising", "admitted"))):
            self._asked = False
            result = self._attempt(job)
            if result is None:
                if self._asked:
                    break  # the frontier refused a call: no second call this step
                continue
            if not self._asked:
                out["decided"].append({"key": job.key, "state": result})  # settled by code, for free
                continue
            out["attempted"] = {"key": job.key, "state": result}
            break

    def _by_evidence(self, jobs: list[Job]) -> list[Job]:
        """The paid queue in the order worth paying for: priority x the forward record of the agents
        a job concerns (`evidence_weight`). Measured Sept 23, 2026: twelve of the sixteen repairs
        merged since Sept 22 failed replay once born -- a correct fix to the execution of a strategy
        with no edge buys nothing -- while the agents with real-money or earning records waited
        behind them. Requested jobs (operator, synthetic) keep their place at the front."""
        requested = {"operator", "synthetic"}

        def weight(job: Job) -> float:
            try:
                return float(self.evidence_weight(sorted(job.agents)))
            except Exception:  # noqa: BLE001 - an unreadable record leaves the job where priority put it
                return 1.0

        return sorted(jobs, key=lambda j: (not (j.sources & requested), -(j.priority() * weight(j)), j.first_at, j.key))

    # ----------------------------------------------------------------------- one attempt
    def _scripted(self, job: Job) -> bool:
        return job.key.startswith("synthetic:") and "synthetic" in job.sources and bool(job.details.get("drill"))

    def _dormant(self, job: Job, reason: str, **extra: Any) -> str:
        self.worklist.transition(job.key, "dormant", note=reason, pr=job.pr, attempt=job.attempt, **extra)
        return "dormant"

    def _attempt(self, job: Job) -> str | None:
        """Carry one admitted or revising job through one patch. Returns the state it ends in,
        or None when nothing was done (so the next job may be tried)."""
        settings = self.settings
        if job.kind == "missing_data":
            if job.details.get("blocked"):
                # The toolsmith already read this request and found it needs data or House code.
                return self._dormant(job, f"{NEEDS_CORE}: the toolsmith found this cannot be a pure tool; it needs House data or "
                                          "engine work outside every Merton role's paths")
            if job.key.startswith("missing_data:research:"):
                return self._dormant(job, f"{NEEDS_CORE}: research keeps naming a missing input, and acquiring data is House work; "
                                          "a matching tool request would reach the toolsmith")
            return None  # the toolsmith reads tool requests first, on its own schedule; its verdict decides
        if job.kind == "order_refusal":
            reason = job.key.lower()
            if any(marker in reason for marker in PROTECTIVE):
                self.worklist.transition(job.key, "rejected", attempt=job.attempt, pr=job.pr,
                                         note="a protective rule working as designed: money and risk rules are not a repair's to loosen")
                return "rejected"
            if any(marker in reason for marker in CORE_REFUSALS):
                return self._dormant(job, f"{NEEDS_CORE}: the refusal comes from House code (seats, reconciliation), "
                                          "outside every Merton role's paths")
        if job.attempt >= int(settings["max_attempts"]):
            return self._dormant(job, f"attempt limit reached ({job.attempt} of {settings['max_attempts']}); costs kept")
        if job.kind in STRATEGY_KINDS:
            return self._dormant(job, "private program changes belong to the swarm researcher; no public repair proposed")
        scripted = self._scripted(job)
        prior = job.state
        packet = self._packet(job)
        user = json.dumps(packet, default=str)
        system = BRIEF + "\n\nTHE STRATEGY CONTRACT\n\n" + (CONTRACT.read_text(encoding="utf-8") if CONTRACT.exists() else "")
        max_out = int(settings["max_output_tokens"])
        model = getattr(self.frontier, "model", "gpt-6-astra")
        worst = Decimal(0) if scripted else hold_usd(model, len(system.encode()) + len(user.encode()) + 400, max_out)
        ceiling = Decimal(str(settings["max_job_usd"]))
        if job.cost_usd + worst > ceiling:
            return self._dormant(job, f"per-job spend limit: ${job.cost_usd:.4f} spent of ${ceiling}; the next attempt could cost up to ${worst:.4f}")
        if not scripted and not self.may_spend():
            return None  # the day's allowance or the frontier tier says not now; the job waits
        if not scripted and self.clock() - self.last_call() < float(settings["min_seconds_between_calls"]):
            return None  # paced: one paid patch per interval, across restarts
        attempt = job.attempt + 1
        self._asked = True
        self.worklist.transition(job.key, "reproducing", attempt=job.attempt, pr=job.pr,
                                 note=f"attempt {attempt}: {len(job.evidence)} evidence rows, {len(packet.get('code') or {})} code excerpts"
                                      + (", CI's failure text" if packet.get("previous") else ""))
        commitment = f"engineer:{job.key}:{attempt}:{self.ledger.head()[0]}"
        self.worklist.transition(job.key, "patching", attempt=attempt, pr=job.pr, note=f"asking for patch {attempt}",
                                 extra={"request": commitment, "hold_usd": format(worst, "f"), "scripted": scripted})
        cost = Decimal(0)
        try:
            if scripted:
                answer = drill_answer(job, attempt, packet)
            else:
                self._last_call = self.clock()
                reply = None
                try:
                    reply = self.frontier.ask(system=system, user=user, agent="merton-engineer", max_output_tokens=max_out,
                                              effort=str(settings["effort"]))
                    cost = reply.cost_usd
                    answer = reply.json()
                except FrontierError as exc:
                    if reply is None and not _ambiguous(exc):
                        # Refused before anything was bought (the campaign's line, the gateway's 4xx):
                        # the attempt is not counted, and the job waits.
                        self._pass(job, attempt, Decimal(0), f"the frontier call was refused: {exc}", error=True)
                        self.worklist.transition(job.key, prior, attempt=job.attempt, pr=job.pr,
                                                 note=f"the frontier call was refused ({str(exc)[:200]}); the job waits")
                        return None
                    if reply is None:
                        # No answer, but the provider may have done the work and billed it: book the
                        # worst case and count the attempt, as for a restart mid-call.
                        self._pass(job, attempt, worst, f"no answer ({exc}); the worst-case hold is counted as spent",
                                   error=True, ambiguous=True)
                        return self._after_failure(job, attempt, worst, f"patch {attempt} got no answer ({str(exc)[:200]}); "
                                                   f"its worst-case hold ${worst:.4f} is counted as spent")
                    self._pass(job, attempt, cost, f"the answer was unreadable: {exc}", error=True)
                    return self._after_failure(job, attempt, cost, f"patch {attempt}'s answer was unreadable ({str(exc)[:200]})")
        except Exception as exc:  # noqa: BLE001 - one job's crash must not stop the worker
            self._pass(job, attempt, cost, f"the attempt failed: {type(exc).__name__}", error=True)
            return self._after_failure(job, attempt, cost, f"patch {attempt} failed: {type(exc).__name__}: {str(exc)[:200]}")
        return self._propose(job, attempt, cost, answer)


    def _after_failure(self, job: Job, attempt: int, cost: Decimal, note: str, **extra: Any) -> str:
        if attempt >= int(self.settings["max_attempts"]):
            self.worklist.transition(job.key, "dormant", note=f"{note}; attempt limit reached", attempt=attempt, pr=job.pr,
                                     cost_usd=cost, extra=extra or None)
            return "dormant"
        self.worklist.transition(job.key, "revising", note=note, attempt=attempt, pr=job.pr, cost_usd=cost, extra=extra or None)
        return "revising"

    def _propose(self, job: Job, attempt: int, cost: Decimal, answer: Mapping[str, Any]) -> str:
        from .merton import parse_proposal

        core = answer.get("needs_core") if isinstance(answer.get("needs_core"), dict) else None
        if core:
            paths = [str(p)[:200] for p in (core.get("paths") or []) if isinstance(p, str)][:12]
            self._pass(job, attempt, cost, f"needs core authority: {str(core.get('reason') or '')[:300]}")
            self.worklist.transition(job.key, "dormant", attempt=attempt, pr=job.pr, cost_usd=cost,
                                     note=f"{NEEDS_CORE}: {str(core.get('reason') or '')[:1200]}", extra={"paths": paths})
            return "dormant"
        role = answer.get("role") if answer.get("role") in ROLES else None
        if role is None:
            self._pass(job, attempt, cost, "no role inside the repair allowlist")
            return self._after_failure(job, attempt, cost, f"patch {attempt} named no allowed role ({str(answer.get('role'))[:40]})")
        proposal = parse_proposal(role, dict(answer), cost)
        files, notes = proposal.files, []
        outside = [d for d in proposal.dropped if "outside what the" in d or "no role may change" in d]
        if not files:
            summary = proposal.summary or "no change"
            if outside:
                self._pass(job, attempt, cost, f"needs core authority: {summary}")
                self.worklist.transition(job.key, "dormant", attempt=attempt, pr=job.pr, cost_usd=cost,
                                         note=f"{NEEDS_CORE}: the fix touches {'; '.join(outside[:4])}")
                return "dormant"
            if proposal.dropped or notes:
                self._pass(job, attempt, cost, f"refused before CI: {'; '.join((proposal.dropped + notes)[:3])}")
                return self._after_failure(job, attempt, cost, "patch refused before CI: " + "; ".join((proposal.dropped + notes)[:6]),
                                           _failure="\n".join(proposal.dropped + notes)[:8000])
            self._pass(job, attempt, cost, f"no change justified: {summary}")
            self.worklist.transition(job.key, "rejected", attempt=attempt, pr=job.pr, cost_usd=cost,
                                     note=f"the engineer found no change the evidence justifies: {summary[:1200]}")
            return "rejected"
        self._pass(job, attempt, cost, proposal.summary, files=len(files))
        body = (f"{proposal.body}\n\nRepair job `{job.key}` ({job.kind}, priority {job.priority()}), attempt {attempt} of "
                f"{self.settings['max_attempts']}. Affected agents: {', '.join(sorted(job.agents)[:12]) or 'the House'}."
                + (" SYNTHETIC: a labeled repair drill, not a fix of a real defect." if self._scripted(job) else ""))[:7000]
        pending = {"role": role, "slug": f"repair-{proposal.slug}"[:48].rstrip("-"), "title": proposal.title, "body": body,
                   "files": files}
        # Paid for: kept before the forge is asked, so an outage never buys the same files twice.
        self.worklist.transition(job.key, "testing", attempt=attempt, cost_usd=cost, note=f"patch {attempt} written; proposing",
                                 extra={"_proposal": pending, "digests": _files_digest(files), "dropped": proposal.dropped[:8] + notes[:4]})
        return self._open(self.worklist.get(job.key) or job)


    def _open(self, job: Job) -> str:
        """Propose the files the last `testing` row holds (paid for already)."""
        pending = job.carry.get("_proposal") if job.state == "testing" or job.last_status.get("_proposal") else None
        if not isinstance(pending, dict):
            return self._after_failure(job, job.attempt, Decimal(0), "the paid patch was not kept; nothing to propose")
        try:
            made = self.forge.propose(**pending)
        except Exception as exc:  # noqa: BLE001 - ForgeError or a transport fault: the files wait
            self.worklist.transition(job.key, "testing", attempt=job.attempt, note=f"the forge refused ({str(exc)[:300]}); proposed again next step",
                                     extra={"_proposal": pending, "digests": job.carry.get("digests")})
            return "testing"
        number = made.get("number")
        paths = [f["path"] for f in pending["files"]]
        self.ledger.append("merton.change", {"role": pending["role"], "branch": made.get("branch"), "number": number,
                                             "title": pending["title"], "status": "opened", "paths": paths, "tool_answers": [],
                                             "file_digests": job.carry.get("digests") or _files_digest(pending["files"]),
                                             "repair": job.key, "attempt": job.attempt})
        self.worklist.transition(job.key, "testing", attempt=job.attempt, pr=number if isinstance(number, int) else None,
                                 note=f"PR #{number} opened on {made.get('branch')}; waiting for CI",
                                 extra={"branch": made.get("branch"), "head": made.get("head"), "digests": job.carry.get("digests"),
                                        "_proposal": None,
                                        "_files": pending["files"] if sum(len(f["content"]) for f in pending["files"]) < 120_000 else None})
        return "testing"

    def _interrupted(self, job: Job) -> None:
        """A job left mid-call: this process did not finish it. Its hold is booked as spent (the
        campaign keeps it until the gateway settles) and the next attempt is new and recorded."""
        hold = Decimal(str(job.last_status.get("hold_usd") or "0")) if job.state == "patching" else Decimal(0)
        attempt = job.attempt if job.state == "patching" else job.attempt
        if job.state == "patching" and hold > 0:
            self._pass(job, attempt, hold, "interrupted by a restart; the worst-case hold is counted as spent", error=True, interrupted=True)
        note = (f"patch {attempt} was interrupted (restart); its worst-case hold ${hold:.4f} is counted as spent, and the next "
                "attempt is a new, recorded request" if job.state == "patching" else "interrupted before any call; nothing was bought")
        if job.state == "reproducing":
            self.worklist.transition(job.key, "revising" if job.attempt else "admitted", attempt=job.attempt, pr=job.pr, note=note)
            return
        self._after_failure(job, attempt, hold, note)

    # --------------------------------------------------------------------- following

    def _change(self, number: int) -> dict[str, Any] | None:
        rows = [e.payload for e in self.ledger.read(kinds="merton.change", limit=2000, newest=True) if e.payload.get("number") == number]
        return dict(rows[-1]) if rows else None

    def _advance(self, job: Job) -> str | None:
        if job.kind in STRATEGY_KINDS:
            return self._dormant(job, "private program changes belong to the swarm researcher; no public repair followed")
        if job.state == "testing":
            if job.pr is None:
                return self._open(job) if isinstance(job.last_status.get("_proposal"), dict) else None
            change = self._change(job.pr)
            status = (change or {}).get("status")
            if status == "refused by CI":
                return self._refused(job)
            if status in ("merged", "deployed"):
                self.worklist.transition(job.key, "canary", attempt=job.attempt, pr=job.pr, commit=(change or {}).get("head"),
                                         note=f"PR #{job.pr} merged; waiting for the running release to hold its files",
                                         extra={"digests": job.carry.get("digests"), "merged_at": now_iso(self.clock)})
                return "canary"
            if status == "closed":
                self.worklist.transition(job.key, "rejected", attempt=job.attempt, pr=job.pr, note=f"PR #{job.pr} was closed without merging")
                return "rejected"
            return None
        if job.state == "canary":
            digests = job.carry.get("digests") or {}
            if digests and all(self._running(path, want) for path, want in digests.items()):
                release = self.repo.name
                self.worklist.transition(job.key, "observing", attempt=job.attempt, pr=job.pr, commit=job.commit,
                                         note=f"the running release ({release}) holds PR #{job.pr}'s files; watching for recurrence",
                                         extra={"deployed_at": now_iso(self.clock), "release": release, "digests": digests,
                                                "exclude": []})
                return "observing"
            merged_at = job.last_status.get("merged_at") or job.state_at
            if self.clock() - _epoch(str(merged_at)) > float(self.settings["canary_timeout_hours"]) * 3600:
                # Merged, but the running release never held these exact files: a later change
                # rewrote them, or the updater refused the release. Not a verified repair.
                return self._dormant(job, f"PR #{job.pr} merged but its files never ran as written for "
                                          f"{self.settings['canary_timeout_hours']} h; not verified")
            return None
        if job.state == "observing":
            since = str(job.last_status.get("deployed_at") or job.state_at)
            excluded = job.last_status.get("exclude") or []
            again = job.evidence_after(since, excluding=excluded)
            if again:
                latest = [row for row in job.evidence if (row.get("at") or "") > since][-3:]
                text = (f"The fix in PR #{job.pr} was running from {since}, and the problem recurred: {len(again)} new reports. "
                        "Latest: " + " | ".join(str(r.get("excerpt") or "")[:400] for r in latest))
                return self._after_failure(job, job.attempt, Decimal(0), f"recurred after deployment: {len(again)} new reports since {since}",
                                           _failure=text, _files=job.carry.get("_files"), failed_pr=job.pr)
            window = (float(self.settings["synthetic_observe_minutes"]) * 60 if job.key.startswith("synthetic:")
                      else float(self.settings["observe_hours"]) * 3600)
            if self.clock() - _epoch(since) < window:
                return None
            self.worklist.transition(job.key, "verified", attempt=job.attempt, pr=job.pr, commit=job.commit,
                                     note=f"no recurrence for {window / 3600:.2f} h after the fix was running ({job.last_status.get('release')})")
            return "verified"
        if job.state == "verified":
            again = job.evidence_after(job.state_at)
            if again:
                self.worklist.transition(job.key, "admitted", attempt=job.attempt, pr=job.pr,
                                         note=f"recurred after verification: {len(again)} new reports")
                return "admitted"
        return None

    def _failure_text(self, number: int) -> str | None:
        """CI's own words for why it refused a pull request, or None when they cannot be read."""
        try:
            found = self.forge.failures(int(number))
        except Exception:  # noqa: BLE001 - ForgeError: the gateway does not offer the read yet
            return None
        parts = []
        for run in found.get("failures") or []:
            for note in run.get("annotations") or []:
                parts.append(str(note.get("message") or ""))
            if not run.get("annotations") and run.get("summary"):
                parts.append(str(run.get("summary")))
        return "\n".join(p for p in parts if p.strip())[:8000] or None

    def _refused(self, job: Job) -> str:
        text = self._failure_text(job.pr)
        if text is None:
            # Not bought blind. The read may simply not be deployed yet: wait for it, boundedly.
            waiting = job.last_status.get("waiting_for_failure")
            if not waiting:
                self.worklist.transition(job.key, "testing", attempt=job.attempt, pr=job.pr,
                                         note=f"CI refused PR #{job.pr}; waiting for its failure text (GET /v1/github/pr/{job.pr}/failures)",
                                         extra={"waiting_for_failure": now_iso(self.clock)})
                return "testing"
            if self.clock() - _epoch(str(waiting)) < float(self.settings["failure_text_wait_hours"]) * 3600:
                return None
            return self._dormant(job, f"CI refused PR #{job.pr} and its failure text could not be read (the gateway's "
                                      f"GET /v1/github/pr/{job.pr}/failures) for {self.settings['failure_text_wait_hours']} h; "
                                      "a blind revision is not bought")
        previous = job.carry.get("_files") or (job.carry.get("_proposal") or {}).get("files")
        return self._after_failure(job, job.attempt, Decimal(0), f"CI refused PR #{job.pr}: {text[:600]}",
                                   _failure=text, _files=previous, failed_pr=job.pr)

    def _running(self, path: str, want: str) -> bool:
        if ci.guard([path], None):
            return False
        try:
            return hashlib.sha256((self.repo / path).read_bytes()).hexdigest() == want
        except OSError:
            return False



    # ----------------------------------------------------------------------- evidence
    def _packet(self, job: Job) -> dict[str, Any]:
        view = job.view()
        view["evidence"] = job.evidence
        packet: dict[str, Any] = {"job": view, "details": job.details, "attempt": job.attempt + 1,
                                  "max_attempts": self.settings["max_attempts"], "today": time.strftime("%Y-%m-%d", time.gmtime(self.clock()))}
        if job.attempt and job.carry.get("_failure"):
            packet["previous"] = {"ci_failure": job.carry.get("_failure"), "files": job.carry.get("_files") or [],
                                  "pr": job.carry.get("failed_pr")}
        if job.kind == "ci_failure" and isinstance(job.details.get("pr"), int) and "previous" not in packet:
            # The refused proposal's own CI text is its reproduction; its files are not readable here.
            text = self._failure_text(job.details["pr"])
            if text:
                packet["ci_failure_of_the_reported_pr"] = text
        packet["existing_tools"] = sorted(p.name for p in (self.repo / "league" / "tools").glob("*.py"))
        try:
            packet.update(self.evidence() or {})
        except Exception:  # noqa: BLE001 - extra context is optional
            pass
        return packet

    def _pass(self, job: Job, attempt: int, cost: Decimal, summary: str, **extra: Any) -> None:
        """The cost row the pacer reads (`merton.pass`), for every call, paid or not."""
        self.ledger.append("merton.pass", {"role": "engineer", "at_epoch": self.clock(), "repair": job.key, "attempt": attempt,
                                           "summary": str(summary)[:600], "cost_usd": format(cost, "f"),
                                           "files": int(extra.pop("files", 0)), **extra})


def _ambiguous(exc: FrontierError) -> bool:
    """A call that may have reached the provider: the transport failed (no status) or the
    gateway answered 5xx. A 4xx, or the campaign's own refusal before sending, bought nothing."""
    status = getattr(exc, "status", None)
    return (status is None and str(exc).startswith("frontier call failed")) or (status is not None and status >= 500)


def _epoch(iso: str) -> float:
    from league.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


# ------------------------------------------------------------------------------ the drill
DRILL_PREFIX = "synthetic:repair-drill:"
DRILL_TOOL = "league/tools/repair_drill.py"
DRILL_TEST = "league/tests/test_tool_repair_drill.py"


def digest_of(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def drill_report(worklist: Worklist, stamp: str) -> str:
    """The drill's job: `source: synthetic`, a `synthetic:` key, and nothing real to fix."""
    stamp = "".join(c for c in str(stamp).lower() if c.isalnum())[:32] or "drill"
    key = DRILL_PREFIX + stamp
    worklist.report(key=key, kind="bug_report", source="synthetic", severity="low", agents=[],
                    summary="SYNTHETIC repair drill: prove patch -> CI refusal -> revision against CI's failure text -> merge -> deploy -> verified.",
                    evidence=[{"seq": None, "at": "", "agent": "house", "excerpt": "Planted by scripts/repair_drill.py; not a real defect."}],
                    details={"drill": stamp}, id=f"repair-drill:{stamp}")
    return key


def drill_answer(job: Job, attempt: int, packet: Mapping[str, Any]) -> dict[str, Any]:
    """The labeled synthetic exercise (`scripts/repair_drill.py`): no model is asked. Patch 1 is
    deliberately wrong and its own test says so; patch 2 is written only if CI's failure text,
    read back through the gateway, names the failing test -- so the revision proves the loop
    reads the real refusal, not a script's memory."""
    drill = str(job.details.get("drill"))[:40]
    test = f'''"""SYNTHETIC repair drill {drill}: proves the engineer revises against CI's failure text."""

import unittest

from league.tools.repair_drill import checksum


class RepairDrillTest(unittest.TestCase):
    def test_checksum_adds_every_value(self):
        self.assertEqual(checksum([1, 2, 3]), 6)
'''

    def tool(offset: str) -> str:
        return f'''"""SYNTHETIC: the repair drill's artifact (drill {drill}), not a trading tool; do not use it in a strategy.

It exists so the repair engineer's full loop (patch, CI refusal, revision against CI's own
failure text, merge, deployment, observation) is exercised on production with a change that
cannot matter to any agent.
"""


def checksum(values):
    """The sum of the values."""
    return sum(values){offset}
'''

    base = {"role": "engineer", "slug": f"drill-{drill}", "needs_core": None}
    if attempt == 1:
        return {**base, "summary": "SYNTHETIC drill patch 1: deliberately wrong; its own test must fail in CI.",
                "title": f"SYNTHETIC repair drill {drill}: patch 1 (fails by design)",
                "body": "A labeled synthetic exercise of the repair loop. This patch is wrong on purpose.",
                "files": [{"path": DRILL_TOOL, "content": tool(" - 1")}, {"path": DRILL_TEST, "content": test}]}
    failure = str((packet.get("previous") or {}).get("ci_failure") or "")
    if "test_checksum_adds_every_value" not in failure and "repair_drill" not in failure:
        return {**base, "summary": "CI's failure text does not name the drill's test; no revision is written.", "files": [],
                "title": "", "body": ""}
    return {**base, "summary": "SYNTHETIC drill patch 2: fixed against CI's failure text.",
            "title": f"SYNTHETIC repair drill {drill}: patch {attempt} (revised against CI's failure text)",
            "body": "A labeled synthetic exercise of the repair loop. CI's refusal of patch 1 named the failing test; this fixes it.",
            "files": [{"path": DRILL_TOOL, "content": tool("")}, {"path": DRILL_TEST, "content": test}]}
