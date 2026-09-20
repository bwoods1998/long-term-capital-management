"""Merton's other five jobs. It is already the auditor; here it is architect, toolsmith, operator,
game designer and teacher, and in every one of them it can do exactly one thing: propose a pull
request. It never picks a trade, never touches the ledger, and never merges.

One pass of one role:

1. the House gathers that role's evidence from the ledger (the league table, the graveyard, the
   tool-request queue, the alerts, the economy's numbers);
2. Merton answers, through the gateway's metered route, with a small set of whole files;
3. the House checks the proposal against the same path guard CI uses (`league/ci.py`) and drops
   anything outside the role's paths;
4. the forge turns it into a branch `merton/<role>/<slug>` and a pull request. In production the
   forge is the gateway (`POST /v1/github/pr`: the GitHub credential lives there, not on Sail);
5. CI judges the pull request; a repository workflow merges a green one; the House notices `main`
   move, and the watchdog stages the new code on a canary before the House runs it.

Every pass and every change is a row on the ledger and a line on the public tape, with its cost.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from . import ci
from .frontier import Frontier, FrontierError
from .ledger import Ledger
from .safety import CodeRefused, check_code, check_strategy_code

REPO = Path(__file__).resolve().parents[1]
CONTRACT = (Path(__file__).resolve().parent / "CONTRACT.md")
ROLES = ("architect", "toolsmith", "operator", "designer", "teacher")

ANSWER = """Answer with ONE JSON object and nothing else:
{"summary": "two or three plain sentences: what you concluded and why",
 "slug": "lowercase-words-with-dashes",
 "title": "the pull request's title, under 100 characters",
 "body": "the pull request's description: the evidence, the change, how it will be judged",
 "files": [{"path": "...", "content": "the WHOLE file"}]}
Give "files": [] when the evidence does not justify a change. Doing nothing is a respectable answer:
every change you propose costs the owner money to test and may cost more if it is wrong."""

BRIEFS: dict[str, str] = {
    "architect": """You are the architect of a small real-money trading league. You do not pick trades. You read the league
table and the graveyard and write NEW STRATEGY PROGRAMS that cheap agents then run, mutate and are judged on.
A new strategy is born on rung 0 and must pass a mechanical replay (deflated Sharpe against every trial its
family has run) before it is forward-tested on paper, then audited, then given $1 to $10 positions.
Every agent is a SPECIALIST: it belongs for life to one specialty of `specialties` below (a venue, a universe of
series or symbols, a brief of what is known there), and a strategy is placed by what its NEEDS ask to see, so name
series or symbols from ONE specialty's universe (a strategy that sits in none is refused). Entries on Kalshi must
resolve within 12 hours (hourly strategies) or 48 (daily); a crypto position is closed after 48 hours.
Write at most two strategies a pass. Aim at specialties that are empty, thinly worked, or where everything has
died for a reason you can name and avoid. Prefer structural edges that survive fees (maker fills, favourites,
settlement mechanics, calendar effects) to pattern-fitting. Each strategy is one file
`league/strategies/<name>.py` that follows the strategy contract EXACTLY, plus the WHOLE updated
`league/strategies/registry.json` (a JSON list of {"name", "family", "file", "why"}; keep every existing row).
Names are lowercase with dashes (under 30 characters); files are the name with underscores.""",
    "toolsmith": """You are the toolsmith of a small trading league. Agents run strategy programs in sealed boxes with no
network; they may only import a short list of standard modules plus `tools`, a package of pure helper modules
you maintain. Agents file requests in plain words. Build what is asked when it can be built as PURE PYTHON over
the data a strategy already receives (indicators, estimators, pricing formulas, calendars). A request that
needs new data cannot be met by you: say so in the summary. Each tool is `league/tools/<name>.py` (same safety
rules as a strategy: whitelisted imports only, no files, no network, no attribute assignment) with a docstring
an agent can learn it from, plus `league/tests/test_tool_<name>.py` (unittest) proving it right on known values.
Also answer every request you read, in an extra key of your JSON:
"answers": [{"request": "<the request's id>", "outcome": "built as tools/<name>.py: how to use it" | "cannot be a pure tool: why, and who could do it"}]""",
    "operator": """You are the operator of a small trading league's House process. You read its alerts, health and budget.
You may propose changes ONLY to the operating dials in `league/config.json`: tick_seconds (30-600),
mark_every_seconds (60-1800), replay_days (7-60), inference_daily_cap_usd (0.5-10). Give the WHOLE file back with
only those values changed. Everything else (real_money, URLs, the performance baseline) belongs to the owner.
Most passes should change nothing: say what you saw, what it means, and what the owner should know.""",
    "designer": """You are the game designer of a small trading league's compute economy. Agents earn compute credits by
evidence-weighted performance, pay for every token and sandbox second, die at zero and may fork when rich. You
may propose changes ONLY to `league/game.json`, inside the bounds that file itself lists, and never to the
statistical thresholds (they are constitutional). Give the WHOLE file back. Judge the game by: is the population
diverse, do the dead die for good reasons, is compute going to agents whose evidence is improving, is the
owner's budget being spent on research that raises the odds of a verified edge? Change one thing at a time.""",
    "teacher": """You are the teacher of a small trading league. You read the graveyard (every dead agent's post-mortem), the
replay trials and the forward records, and you write LESSONS the living agents will read before they spend
credits on research. A lesson is specific and checkable: what was tried, what the numbers were, why it failed or
worked, what to do differently. No platitudes. Each lesson is one markdown file `league/playbook/<date>-<slug>.md`
under 600 words. Write at most two a pass, and none when the graveyard has taught nothing new.""",
}


class ForgeError(RuntimeError):
    pass


class GatewayForge:
    """Pull requests through the gateway: the only forge the House uses. It holds no GitHub token."""

    def __init__(self, gateway_url: str, token_source: Callable[[], str], *, opener: Any = None):
        self.base = gateway_url.rstrip("/") + "/v1/github/pr"
        self.token_source = token_source
        self.opener = opener or urllib.request.urlopen

    def _call(self, method: str, url: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            url, data=None if body is None else json.dumps(body).encode("utf-8"), method=method,
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json", "User-Agent": "ltcm-floor/1.0"},
        )
        try:
            with self.opener(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ForgeError(f"HTTP {exc.code}: {exc.read()[:300].decode('utf-8', 'replace')}") from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ForgeError(f"the gateway did not answer: {type(exc).__name__}") from None

    def propose(self, *, role: str, slug: str, title: str, body: str, files: list[dict[str, str]]) -> dict[str, Any]:
        return self._call("POST", self.base, {"role": role, "slug": slug, "title": title, "body": body, "files": files})

    def status(self, number: int) -> dict[str, Any]:
        return self._call("GET", f"{self.base}/{int(number)}")


class GhForge:
    """The same forge from the owner's own machine, through `git` and the `gh` CLI he is signed in
    to. It is how a pass is run by hand, and how the flow was proven before the gateway held a
    GitHub token. It is never used on Sail: nothing there holds a GitHub credential."""

    def __init__(self, repo: Path = REPO, *, remote: str = "origin", base: str = "main"):
        self.repo, self.remote, self.base = Path(repo), remote, base

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        done = subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True)
        if done.returncode != 0:
            raise ForgeError(f"git {args[0]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip()

    def propose(self, *, role: str, slug: str, title: str, body: str, files: list[dict[str, str]]) -> dict[str, Any]:
        digest = hashlib.sha256(json.dumps(sorted((f["path"], f["content"]) for f in files)).encode("utf-8")).hexdigest()[:8]
        branch = f"merton/{role}/{slug}-{digest}"
        self._git("fetch", "--quiet", self.remote, self.base)
        work = Path(tempfile.mkdtemp(prefix="merton-"))
        try:
            self._git("worktree", "add", "--quiet", "-b", branch, str(work), f"{self.remote}/{self.base}")
            for row in files:
                target = work / row["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(row["content"], encoding="utf-8")
                self._git("add", "--", row["path"], cwd=work)
            message = f"{title}\n\n{body}\n\nOpened by Merton ({role}).\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
            self._git("commit", "--quiet", "-m", message, cwd=work)
            head = self._git("rev-parse", "HEAD", cwd=work)
            self._git("push", "--quiet", "-u", self.remote, branch, cwd=work)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=self.repo, capture_output=True)
        made = subprocess.run(["gh", "pr", "create", "--base", self.base, "--head", branch, "--title", title,
                               "--body", body + f"\n\nOpened by Merton ({role}).\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"],
                              cwd=self.repo, capture_output=True, text=True)
        if made.returncode != 0:
            raise ForgeError(f"gh pr create failed: {made.stderr.strip()[:300]}")
        url = made.stdout.strip().splitlines()[-1]
        return {"ok": True, "branch": branch, "number": int(url.rstrip("/").rsplit("/", 1)[1]), "url": url, "head": head}

    def status(self, number: int) -> dict[str, Any]:
        done = subprocess.run(["gh", "pr", "view", str(int(number)), "--json", "state,mergedAt,headRefOid,statusCheckRollup"], cwd=self.repo, capture_output=True, text=True)
        if done.returncode != 0:
            raise ForgeError(f"gh pr view failed: {done.stderr.strip()[:300]}")
        row = json.loads(done.stdout)
        runs = [r for r in row.get("statusCheckRollup") or [] if r.get("status")]
        finished = [r for r in runs if r.get("status") == "COMPLETED"]
        failed = [r for r in finished if r.get("conclusion") not in ("SUCCESS", "SKIPPED", "NEUTRAL")]
        conclusion = "failure" if failed else ("success" if runs and len(finished) == len(runs) else "pending")
        return {"number": int(number), "state": str(row.get("state") or "").lower(), "merged": bool(row.get("mergedAt")), "head": row.get("headRefOid"),
                "checks": {"total": len(runs), "completed": len(finished), "failed": len(failed), "conclusion": conclusion}}


@dataclass
class Proposal:
    role: str
    summary: str
    slug: str
    title: str
    body: str
    files: list[dict[str, str]]
    dropped: list[str]
    cost_usd: Decimal
    answers: list[dict[str, Any]] = field(default_factory=list)


def parse_proposal(role: str, answer: Mapping[str, Any], cost: Decimal) -> Proposal:
    """Merton's answer, reduced to what the role may actually change. Anything else is dropped here,
    refused again by the gateway, and refused a third time by CI."""
    files, dropped = [], []
    listed = answer.get("files") if isinstance(answer.get("files"), list) else []
    for row in listed[:12]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not isinstance(row.get("content"), str):
            dropped.append("a file entry without a path and content")
            continue
        path, content = row["path"].strip(), row["content"]
        problems = ci.guard([path], role)
        if not problems and path.startswith(("league/strategies/", "league/tools/")) and path.endswith(".py"):
            try:
                (check_code if path.startswith("league/strategies/") else check_strategy_code)(content)
            except CodeRefused as exc:
                problems = [f"{path}: {exc}"]
        if not problems and path.endswith(".json"):
            try:
                json.loads(content)
            except ValueError:
                problems = [f"{path}: not valid JSON"]
        if problems or len(content) > 60_000:
            dropped.extend(problems or [f"{path}: over 60,000 characters"])
        else:
            files.append({"path": path, "content": content})
    slug = re.sub(r"[^a-z0-9-]+", "-", str(answer.get("slug") or role).lower()).strip("-")[:48] or role
    answers = [a for a in (answer.get("answers") if isinstance(answer.get("answers"), list) else []) if isinstance(a, dict)][:20]
    return Proposal(role, str(answer.get("summary") or "")[:1500], slug, str(answer.get("title") or f"Merton ({role})")[:110],
                    str(answer.get("body") or "")[:7000], files, dropped, cost, answers)


CONSULT = """You are Merton, the firm's theorist. One of its trading agents is paying you, out of the compute
credits it earned by performing, to think about ITS problem. It cannot do this often: the better it trades the
more it can afford you, so treat its question as expensive and answer the question it asked.

You are given everything it knows: its strategy file, its parameters, its specialty's brief (what is measured in
its markets, and what is known not to work), its journal, its own recent trades, and where its replays won and
lost. You are NOT given the power to trade, to promote it, or to change the rules.

WRITE IT A STRATEGY FILE. That is what it is paying for and what it cannot get anywhere else: the cheap model
in its research pass can already reason about its evidence, and so can it. Measured on the floor's first night,
ten agents hired you and ten got advice alone -- mostly "audit this before you spend another trial" -- which is
counsel any of them could have written for itself, at the price of the best mind in the firm. Advice is the
EXCEPTION here, not the default. If it has not traded at all, a file is the only answer that can help it: no
amount of judgement unfreezes rules that never fire.

Answer in one of three ways, in this order of preference.
- A WHOLE STRATEGY FILE, whenever you can write one that is better for a reason you can state -- which is nearly
  always, because you are reading its file and its evidence and you can see what it is missing. It must follow
  the strategy contract exactly and keep the agent inside its specialty (the same venue, the same block length,
  series or symbols from its own universe), and it must be a REASONED change, not a tuned parameter. Write the
  whole file, not a diff. Say in `answer` what you changed and what evidence would show you were right.
- A TOOL, when what stops it is missing DATA (below).
- ADVICE ALONE, only when no file could help: its idea is structurally dead and it must ask something different,
  or the thing it needs is data you are naming as a tool. Then say so plainly and briefly.

- A TOOL the House does not offer, when what stops the agent is missing DATA or a missing venue
  feature and no strategy file can get round it (a live score, an order book's depth, a chain's
  greeks, an economic release). Name it and say in one or two sentences what it must do and why
  this agent cannot work without it. It goes to the queue the toolsmith builds from; it is not
  built today, so say what the agent should do in the meantime.

Answer with ONE JSON object and nothing else:
{"answer": "what you concluded, in plain words, addressed to the agent",
 "code": "the whole strategy file -- the usual answer; empty only when no file could help",
 "tool": {"name": "lower_case_with_underscores", "description": "what it must do and why"} or null,
 "confidence": "high | medium | low: how sure you are that this beats what it runs now"}"""


class Merton:
    def __init__(self, frontier: Frontier, forge: Any, ledger: Ledger, *, evidence: Callable[[str], dict[str, Any]], clock=time.time,
                 schedule_hours: Mapping[str, float] | None = None, first_after_hours: Mapping[str, float] | None = None, pace: Any = None,
                 effort: Mapping[str, str] | None = None):
        self.frontier = frontier
        self.forge = forge
        self.ledger = ledger
        self.evidence = evidence
        self.clock = clock
        #: How often each role sits down. One architect pass is about $1.25 of the $100 month.
        self.schedule_hours = dict(schedule_hours or {"operator": 24, "teacher": 72, "toolsmith": 24, "designer": 168, "architect": 168})
        #: () -> the share of its usual wait a role serves, so the House can bring the roles round
        #: sooner while the day's frontier allowance is unspent (`House.frontier_pace`). Never
        #: longer than the game file's number, and never under a quarter of it.
        self.pace = pace or (lambda: 1.0)
        #: A role's FIRST pass waits until the league has something to show it: an architect shown
        #: an empty table on the first morning would be a dollar spent on nothing.
        self.first_after_hours = dict(first_after_hours or {"operator": 6, "toolsmith": 12, "teacher": 24, "architect": 48, "designer": 72})
        #: How hard each role thinks (the frontier model's reasoning effort). The roles that write code think hardest.
        self.effort = dict(effort or {})

    # ---------------------------------------------------------------- consult
    def consult(self, agent: Any, question: str, evidence: Mapping[str, Any], *, contract: str) -> dict[str, Any]:
        """One agent hires Merton with its own credits. Returns `{"answer", "code", "confidence",
        "cost_usd"}`; `code` is empty unless Merton wrote a whole strategy file. Never raises: a
        frontier failure is an answer that says so and costs the agent nothing."""
        system = CONSULT + "\n\nTHE STRATEGY CONTRACT (the file format any code you write must follow)\n\n" + contract
        try:
            reply = self.frontier.ask(system=system, user=json.dumps(evidence, default=str),
                                      agent=f"consult-{agent.id}", max_output_tokens=12000, effort="high")
            answer = reply.json()
        except FrontierError as exc:
            row = {"answer": f"Merton could not be reached ({exc}).", "code": "", "confidence": "low", "cost_usd": "0", "error": True}
            self.ledger.append("merton.pass", {"role": "consultant", "agent": agent.id, "at_epoch": self.clock(), **row})
            return row
        code = str(answer.get("code") or "")
        tool = answer.get("tool") if isinstance(answer.get("tool"), dict) else None
        row = {
            "answer": str(answer.get("answer") or "")[:4000],
            "code": code,
            "tool": {"name": str(tool.get("name") or "")[:40], "description": str(tool.get("description") or "")[:1200]} if tool else None,
            "confidence": str(answer.get("confidence") or "")[:10],
            "cost_usd": format(reply.cost_usd, "f"),
        }
        self.ledger.append("merton.pass", {"role": "consultant", "agent": agent.id, "at_epoch": self.clock(),
                                           "question": str(question)[:600], "wrote_code": bool(code.strip()),
                                           **{k: v for k, v in row.items() if k != "code"}})
        return row

    # ---------------------------------------------------------------- schedule
    def last_pass(self, role: str) -> float | None:
        rows = [e for e in self.ledger.read(kinds="merton.pass", limit=500, newest=True) if e.payload.get("role") == role]
        return float(rows[-1].payload["at_epoch"]) if rows else None

    def _pace(self) -> float:
        try:
            share = self.pace()
            return 1.0 if share is None else max(0.25, min(float(share), 1.0))
        except Exception:  # noqa: BLE001 - a pacer that cannot answer leaves the schedule alone
            return 1.0

    def due(self) -> list[str]:
        now = self.clock()
        started = self.ledger.read(kinds="ops.started", limit=1)
        running_hours = (now - _epoch(started[0].at)) / 3600 if started else 0.0
        out = []
        for role in ROLES:
            last = self.last_pass(role)
            if last is None:
                if running_hours >= self.first_after_hours.get(role, 0):
                    out.append(role)
            elif now - last >= self.schedule_hours[role] * self._pace() * 3600:
                out.append(role)
        return out

    # -------------------------------------------------------------------- pass
    def run(self, role: str) -> dict[str, Any]:
        """One pass of one role. Never raises: a failed pass is a row that says why."""
        if role not in ROLES:
            raise ValueError(f"no such role {role!r}")
        evidence = self.evidence(role)
        if role == "toolsmith" and not evidence.get("open_requests"):
            return self._record(role, {"summary": "no tool requests are waiting", "cost_usd": "0", "files": 0, "skipped": True})
        system = BRIEFS[role] + "\n\n" + ANSWER
        if role in ("architect", "toolsmith"):
            system += "\n\nTHE STRATEGY CONTRACT\n\n" + CONTRACT.read_text(encoding="utf-8")
        try:
            answer = self.frontier.ask(system=system, user=json.dumps(evidence, default=str), agent=f"merton-{role}",
                                       max_output_tokens=12000 if role in ("architect", "toolsmith") else 5000,
                                       effort=str(self.effort.get(role) or "medium"))
            proposal = parse_proposal(role, answer.json(), answer.cost_usd)
        except FrontierError as exc:
            return self._record(role, {"summary": f"the pass could not run: {exc}", "cost_usd": "0", "files": 0, "error": True})
        row = {"summary": proposal.summary, "cost_usd": format(proposal.cost_usd, "f"), "files": len(proposal.files), "dropped": proposal.dropped[:10]}
        if role == "toolsmith":
            # Every request gets an answer the agents can read, so the queue does not fill with
            # things that will never be built.
            waiting = {r["id"] for r in evidence.get("open_requests") or []}
            for item in proposal.answers:
                if item.get("request") in waiting and str(item.get("outcome") or "").strip():
                    self.ledger.append("tool.fulfilled", {"request": item["request"], "outcome": str(item["outcome"])[:1200], "change": None})
        if proposal.files:
            try:
                made = self.forge.propose(role=role, slug=proposal.slug, title=proposal.title, body=proposal.body, files=proposal.files)
                row.update(branch=made.get("branch"), number=made.get("number"), url=made.get("url"))
                self.ledger.append("merton.change", {"role": role, "branch": made.get("branch"), "number": made.get("number"), "title": proposal.title,
                                                    "status": "opened", "paths": [f["path"] for f in proposal.files]})
            except ForgeError as exc:
                row["forge_error"] = str(exc)[:300]
        return self._record(role, row)

    def _record(self, role: str, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"role": role, "at_epoch": self.clock(), **dict(row)}
        self.ledger.append("merton.pass", payload)
        return payload

    # ------------------------------------------------------------------ follow
    def follow(self) -> list[dict[str, Any]]:
        """Ask the gateway what CI made of each open change, and record the verdicts."""
        latest: dict[int, dict[str, Any]] = {}
        for entry in self.ledger.iter(kinds="merton.change"):
            if entry.payload.get("number") is not None:
                latest[int(entry.payload["number"])] = dict(entry.payload)
        out = []
        for number, row in latest.items():
            if row.get("status") not in ("opened", "pending"):
                continue
            try:
                status = self.forge.status(number)
            except ForgeError:
                continue
            checks = (status.get("checks") or {}).get("conclusion")
            verdict = "merged" if status.get("merged") else ("refused by CI" if checks == "failure" else ("closed" if status.get("state") == "closed" else "pending"))
            if verdict != row.get("status") and verdict != "pending":
                row = {**row, "status": verdict}
                self.ledger.append("merton.change", row)
                out.append(row)
        return out


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


def evidence_from(house: Any) -> Callable[[str], dict[str, Any]]:
    """What each role is shown, gathered from the House. Plain data, public rows only, no code secrets."""

    def table() -> list[dict[str, Any]]:
        rows = []
        for agent in house.registry.living():
            blocks = house.evaluator.blocks(agent.id)
            growth = [float(b["log_growth"]) for b in blocks]
            rows.append({"agent": agent.id, "family": agent.family, "niche": agent.niche, "generation": agent.generation, "rung": house.evaluator.rung(agent.id),
                         "credits_usd": format(house.economy.balance(agent.id), "f"), "blocks": len(blocks), "total_log_growth": round(sum(growth), 6)})
        return rows

    def gather(role: str) -> dict[str, Any]:
        ledger = house.ledger
        graveyard = [{"agent": e.agent, "text": e.payload.get("text")} for e in ledger.read(kinds="agent.postmortem", limit=40, newest=True)]
        trials = [{"agent": e.agent, **{k: e.payload.get(k) for k in ("family", "passed", "sharpe", "deflated_sharpe", "trials", "trades", "return_pct", "reasons")}}
                  for e in ledger.read(kinds="eval.trial", limit=60, newest=True)]
        base = {"league_table": table(), "graveyard": graveyard}
        if role == "architect":
            from . import seeds, strategies

            base.update(replay_trials=trials, occupied_niches=sorted({a.niche for a in house.registry.living()}),
                        specialties=[{"id": n.id, "title": n.title, "venue": n.venue, "horizons": list(n.horizons), "open": not n.dormant,
                                      "members": house.members(n.id), "universe": list(n.universe[:24]), "brief": n.brief[:700]}
                                     for n in house.niches.values()],
                        founding_seeds=[{k: s[k] for k in ("name", "family", "why")} for s in seeds.SEEDS],
                        registry=strategies.registry(), library=house.commons.library_search("edge evidence fees maker", 8)["results"])
        elif role == "toolsmith":
            base = {"open_requests": house.commons.open_requests()[:10], "existing_tools": sorted(p.name for p in (Path(__file__).resolve().parent / "tools").glob("*.py"))}
        elif role == "operator":
            alerts = [{"at": e.at, **e.payload} for e in ledger.read(kinds="ops.alert", limit=60, newest=True)]
            budget = [{"at": e.at, **e.payload} for e in ledger.read(kinds="ops.budget", limit=20, newest=True)]
            base = {"alerts": alerts, "budget": budget, "books": {n: {"frozen": b.frozen, "open_orders": len(b.open_orders())} for n, b in house.books.items()},
                    "config": json.loads((Path(__file__).resolve().parent / "config.json").read_text(encoding="utf-8")), "living": len(house.registry.living())}
        elif role == "designer":
            base.update(game=house.game, deaths=[{"agent": a.id, "cause": a.cause, "niche": a.niche} for a in house.registry.dead()][-30:],
                        payouts=[e.payload for e in ledger.read(kinds="ops.budget", limit=30, newest=True) if e.payload.get("what") == "payout"])
        elif role == "teacher":
            base.update(replay_trials=trials, lessons_so_far=[e.payload.get("title") for e in ledger.read(kinds="playbook.entry", limit=40, newest=True)],
                        today=time.strftime("%Y-%m-%d", time.gmtime(house.clock())))
        return base

    return gather
