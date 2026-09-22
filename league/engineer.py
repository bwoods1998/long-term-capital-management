"""The repair engineer: the worker that turns the worklist into running fixes.

It is Merton's sixth job, and it has no more authority than the other five. It takes the
highest-priority admitted repair job (`league/worklist.py`), shows the frontier model the job's
original evidence and the code it concerns, and turns the answer into a pull request through
the same gateway route, the same path guard (`league/ci.py`) and the same CI as every other
proposal. It follows that pull request: a refusal is read back as CI's own failure text and
sent for a revision, at most `max_attempts` times; a merge is not the end -- the job waits
until the RUNNING release holds the exact files (`canary`), then watches the triggering signal
for an observation window (`observing`) and is `verified` only if it has not come back.

Authority, deliberately unchanged (the chief-architect handoff, Sept 20, 2026: do not broaden
the file allowlist before an external spending broker and an independent release verifier
exist). The engineer may write what the architect, toolsmith, operator and teacher may:
strategies, tools and their tests, the operating dials, lessons. A strategy defect is fixed by
a NEW child strategy file, born on rung 0 in the parent's family, with no record: it qualifies
on its own evidence and never inherits its parent's results. A fix that needs anything else --
the House, the books, the venues, replay, data adapters, CI, the gateway -- is recorded as
`dormant` with the reason "needs core authority", and costs nothing more.

Money. Every paid call goes through the House's `Frontier` (the campaign reserves its worst case
before the call and settles after) and is written as a `merton.pass` row with role "engineer",
which is what the pacer reads for the day's OpenAI spend. Each job has its own ceiling
(`max_job_usd`) checked against the call's worst case BEFORE it is made, so a job can never
spend past it; the rows keep every dollar a rejected or dormant job cost. The engineer's own
settings live in `league/engineer.json`, which no Merton role may write.

Restarts. Every transition is a `repair.status` row, written before the work it announces. A job
found in `reproducing` or `patching` when a step begins was interrupted (one step runs at a
time): the interrupted call's worst-case hold is booked as spent and the next attempt is a new,
recorded request -- never an untracked duplicate. An answer already paid for is kept in the row
that follows it (`_files`), so a forge outage re-proposes the same files without buying them
again.
"""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from . import ci
from .frontier import MODEL_CEILINGS, FrontierError
from .ledger import now_iso
from .worklist import Job, Worklist

REPO = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).resolve().parent / "engineer.json"
CONTRACT = Path(__file__).resolve().parent / "CONTRACT.md"
#: The roles whose paths a repair may use. Not the designer: `game.json` is the economy's rules.
ROLES = ("architect", "toolsmith", "operator", "teacher")
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "max_attempts": 3,
    "max_job_usd": "5.00",
    "admit_priority": 2.0,
    "observe_hours": 24.0,
    "synthetic_observe_minutes": 20.0,
    "min_seconds_between_calls": 1800.0,
    "max_output_tokens": 12000,
    "effort": "high",
    "step_seconds": 120.0,
}
#: The kinds whose fix is a corrected child of one agent's strategy.
STRATEGY_KINDS = ("strategy_defect", "audit_veto")
NEEDS_CORE = "needs core authority"

BRIEF = """You are the repair engineer of a small real-money trading league. You are given ONE job from its repair
worklist: a defect or missing input the floor's own records keep reporting, with the original evidence, the agents
it affects, and the code it concerns. Fix it with the smallest change that makes the reported problem stop, or say
plainly that you cannot. You never trade, never merge, and never judge your own work: CI does, then the running
floor does, by whether the problem comes back.

You may write ONLY these paths, and one answer uses ONE role's paths:
- architect: league/strategies/<stem>.py (the strategy contract below) plus its own description
  league/strategies/<stem>.json = {"name", "family", "why"}. Never league/strategies/registry.json.
- toolsmith: league/tools/<name>.py (pure Python: whitelisted imports only, no files, no network, no attribute
  assignment) plus league/tests/test_tool_<name>.py (unittest, proving it on known values).
- operator: league/config.json, the WHOLE file, changing only keys in permitted_dials, inside their bounds.
- teacher: league/playbook/<YYYY-MM-DD>-<slug>.md, one specific, checkable lesson under 600 words.
Everything else -- the House, the books, the venues, replay, data adapters, the evaluator, CI, the gateway -- is
outside your authority. If the real fix needs any of it, answer with needs_core naming the paths; do not write a
workaround that hides the defect, and do not write a lesson that only restates it.

A defect in ONE agent's strategy is fixed by a NEW corrected child strategy: a new file with a new name, never an
edit of an existing file. It is born on rung 0 with no record and must qualify on its own evidence. Keep it in the
parent's specialty (same venue, horizon, series or symbols) and write the parent's family in its description.

When CI refused your previous attempt you are shown its failure text and the files you sent: fix exactly what it
says and send the WHOLE corrected files again.

Answer with ONE JSON object and nothing else:
{"summary": "two or three plain sentences: the defect, the fix, and how its absence will be observed",
 "role": "architect | toolsmith | operator | teacher",
 "slug": "lowercase-words-with-dashes",
 "title": "the pull request's title, under 100 characters",
 "body": "the pull request's description: the evidence, the change, how it will be judged",
 "files": [{"path": "...", "content": "the WHOLE file"}],
 "needs_core": null or {"reason": "what must change and why no allowed path can do it", "paths": ["..."]}}
Give "files": [] and "needs_core": null when the evidence does not support a change; the job is then closed as
rejected, with its cost."""


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
                 evidence: Callable[[], Mapping[str, Any]] = lambda: {}, sources: Any = None):
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
        self._last_step = float("-inf")
        self._last_call = float("-inf")

    # ------------------------------------------------------------------------ schedule
    def due(self) -> bool:
        return bool(self.settings.get("enabled")) and self.clock() - self._last_step >= float(self.settings["step_seconds"])

    def step(self) -> dict[str, Any]:
        """One bounded unit of work: report what is new, admit, move every job waiting on the
        outside world (free), and make at most one paid attempt. Never raises for one job."""
        self._last_step = self.clock()
        out: dict[str, Any] = {"reported": [], "admitted": [], "advanced": [], "attempted": None}
        if not self.settings.get("enabled"):
            return out
        if self.sources is not None:
            out["reported"] = self.sources.scan()
        out["admitted"] = self.worklist.admit(threshold=float(self.settings["admit_priority"]))
        for job in self.worklist.queue(("reproducing", "patching")):
            self._interrupted(job)
        for job in self.worklist.queue(("testing", "canary", "observing", "verified")):
            moved = self._advance(job)
            if moved:
                out["advanced"].append({"key": job.key, "state": moved})
        for job in self.worklist.queue(("revising", "admitted")):
            if self.clock() - self._last_call < float(self.settings["min_seconds_between_calls"]) and not self._scripted(job):
                break
            result = self._attempt(job)
            if result is not None:
                out["attempted"] = {"key": job.key, "state": result}
                break
        return out

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
        if job.attempt >= int(settings["max_attempts"]):
            return self._dormant(job, f"attempt limit reached ({job.attempt} of {settings['max_attempts']}); costs kept")
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
        attempt = job.attempt + 1
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
                    if reply is None:
                        # Refused or unreachable: nothing was bought, and the attempt is not counted.
                        self._pass(job, attempt, Decimal(0), f"the frontier call was refused: {exc}", error=True)
                        self.worklist.transition(job.key, prior, attempt=job.attempt, pr=job.pr,
                                                 note=f"the frontier call was refused ({str(exc)[:200]}); the job waits")
                        return None
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
        files, notes = self._child_only(job, role, proposal.files)
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

    def _child_only(self, job: Job, role: str, files: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
        """A strategy defect is fixed by a NEW child file whose description names its parent and
        the repair: an existing strategy file is never rewritten, so no record can carry over."""
        if role != "architect":
            return files, []
        from . import strategies

        parent = sorted(job.agents)[0] if job.kind in STRATEGY_KINDS and job.agents else None
        family = (self.code_of(parent) or {}).get("family") if parent else None
        kept, notes = [], []
        for row in files:
            path = row["path"]
            if path.endswith(".py") and (self.repo / path).exists():
                notes.append(f"{path}: already exists; a repair adds a new child strategy instead of editing one")
                continue
            if path.endswith(".json") and path.startswith("league/strategies/"):
                try:
                    described = json.loads(row["content"])
                except ValueError:
                    kept.append(row)
                    continue
                if isinstance(described, dict):
                    if family:
                        described["family"] = family
                    described["repair"] = {"key": job.key, **({"parent": parent} if parent else {})}
                    described["file"] = path.rsplit("/", 1)[1][:-5] + ".py"
                    try:
                        _, content = strategies.describe(described)
                    except KeyError:
                        kept.append(row)
                        continue
                    row = {"path": path, "content": content}
            kept.append(row)
        stems = {r["path"][:-3] for r in kept if r["path"].endswith(".py")}
        kept = [r for r in kept if not (r["path"].endswith(".json") and r["path"][:-5] not in stems)]
        return kept, notes

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
                                                "exclude": sorted(job.agents) if job.kind in STRATEGY_KINDS else []})
                return "observing"
            return None
        if job.state == "observing":
            since = str(job.last_status.get("deployed_at") or job.state_at)
            excluded = job.last_status.get("exclude") or []
            again = job.evidence_after(since, excluding=excluded)
            if again:
                return self._after_failure(job, job.attempt, Decimal(0), f"recurred after deployment: {len(again)} new reports since {since}")
            window = (float(self.settings["synthetic_observe_minutes"]) * 60 if job.key.startswith("synthetic:")
                      else float(self.settings["observe_hours"]) * 3600)
            if self.clock() - _epoch(since) < window:
                return None
            child = self._child_born(job)
            if child is False:
                return None  # a corrected strategy is only a fix once it is alive and judged on its own
            self.worklist.transition(job.key, "verified", attempt=job.attempt, pr=job.pr, commit=job.commit,
                                     note=f"no recurrence for {window / 3600:.2f} h after the fix was running ({job.last_status.get('release')})"
                                          + (f"; child {child} is born on rung 0" if isinstance(child, str) else ""))
            return "verified"
        if job.state == "verified" and job.kind not in STRATEGY_KINDS:
            again = job.evidence_after(job.state_at)
            if again:
                self.worklist.transition(job.key, "admitted", attempt=job.attempt, pr=job.pr,
                                         note=f"recurred after verification: {len(again)} new reports")
                return "admitted"
        return None

    def _refused(self, job: Job) -> str:
        text = None
        try:
            found = self.forge.failures(job.pr)
            parts = []
            for run in found.get("failures") or []:
                for note in run.get("annotations") or []:
                    parts.append(str(note.get("message") or ""))
                if not run.get("annotations") and run.get("summary"):
                    parts.append(str(run.get("summary")))
            text = "\n".join(p for p in parts if p.strip())[:8000] or None
        except Exception:  # noqa: BLE001 - ForgeError: the gateway does not offer the read yet
            text = None
        if text is None:
            return self._dormant(job, f"CI refused PR #{job.pr} and its failure text could not be read (the gateway's "
                                      f"GET /v1/github/pr/{job.pr}/failures); a blind revision is not bought")
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

    def _child_born(self, job: Job) -> str | bool | None:
        """None when this job has no child to wait for; the child's id once born; else False."""
        if job.kind not in STRATEGY_KINDS:
            return None
        names = []
        for path in (job.carry.get("digests") or {}):
            if path.startswith("league/strategies/") and path.endswith(".json"):
                try:
                    names.append(json.loads((self.repo / path).read_text(encoding="utf-8")).get("name"))
                except (OSError, ValueError):
                    continue
        if not names:
            return None
        for entry in self.ledger.iter(kinds="agent.born"):
            if entry.payload.get("founder") in names:
                return entry.agent
        return False

    # ----------------------------------------------------------------------- evidence
    def _packet(self, job: Job) -> dict[str, Any]:
        view = job.view()
        view["evidence"] = job.evidence
        packet: dict[str, Any] = {"job": view, "details": job.details, "attempt": job.attempt + 1,
                                  "max_attempts": self.settings["max_attempts"], "today": time.strftime("%Y-%m-%d", time.gmtime(self.clock()))}
        code = {}
        for agent in sorted(job.agents)[:3]:
            found = self.code_of(agent)
            if found:
                code[agent] = {k: found.get(k) for k in ("family", "niche", "venue", "horizon", "needs", "params", "code")}
        packet["code"] = code
        if job.attempt and job.carry.get("_failure"):
            packet["previous"] = {"ci_failure": job.carry.get("_failure"), "files": job.carry.get("_files") or [],
                                  "pr": job.carry.get("failed_pr")}
        packet["permitted_dials"] = {key: {"min": low, "max": high} for key, (low, high) in ci.CONFIG_DIALS.items()}
        packet["existing_tools"] = sorted(p.name for p in (self.repo / "league" / "tools").glob("*.py"))
        packet["existing_strategies"] = sorted(p.name for p in (self.repo / "league" / "strategies").glob("*.py"))
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


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


# ------------------------------------------------------------------------------ the drill
DRILL_TOOL = "league/tools/repair_drill.py"
DRILL_TEST = "league/tests/test_tool_repair_drill.py"


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

    base = {"role": "toolsmith", "slug": f"drill-{drill}", "needs_core": None}
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
