"""Merton's other five jobs. It is already the auditor; here it is architect, toolsmith, operator,
game designer and teacher, and in every one of them it can do exactly one thing: propose a pull
request. It never picks a trade, never touches the ledger, and never merges.

One pass of one role:

1. the House gathers that role's evidence from the ledger (the league table, the graveyard, the
   tool-request queue, the alerts, the economy's numbers);
2. Merton answers, through the gateway's metered route, with a small set of whole files;
3. the House checks the proposal against the same path guard CI uses (`league/ci.py`) and drops
   anything outside the role's paths;
4. the forge turns it into a branch `merton/<role>/<slug>` and a pull request (the DEPLOYED gateway
   still emits `astra/...`; both are judged, and the role is the second segment either way). In production the
   forge is the gateway (`POST /v1/github/pr`: the GitHub credential lives there, not on Sail);
5. CI judges the pull request; a repository workflow merges a green one (it accepts a branch under
   `merton/` or `astra/`, because the deployed gateway still names the old prefix); the House notices `main`
   move, and the watchdog stages the new code on a canary before the House runs it.

Every pass and every change is a row on the ledger and a line on the public tape, with its cost.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

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

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

BRIEFS: dict[str, str] = {
    "architect": """You are the architect of a small real-money trading league. You do not pick trades. You read the league
table and the graveyard and write NEW STRATEGY PROGRAMS that cheap agents then run, mutate and are judged on.
A new strategy is born on rung 0 and must pass a mechanical replay (deflated Sharpe against every trial its
family has run) before it is forward-tested on paper, then audited, then given $1 to $10 positions.
Every agent is a SPECIALIST: it belongs for life to one specialty of `specialties` below (a venue, a universe of
series or symbols, a brief of what is known there), and a strategy is placed by what its NEEDS ask to see, so name
series or symbols from ONE specialty's universe (a strategy that sits in none is refused). Entries on Kalshi must
resolve within 12 hours (hourly strategies) or 48 (daily); a crypto position is closed after 48 hours.
Write at most two strategies a pass. Aim at the specialties where the EVIDENCE IS WORST, which is almost never
an empty one: `specialties` carries `barren_agents` (members that have looked at a live market and placed nothing)
and `losing_agents` (members that trade and lose). A specialty having members is not a reason to leave it alone --
they may all be failing, and a strategy that works where others fail is worth far more than one in an empty corner.
Twice on Sept 20, 2026 you declined a pass with "every specialty is occupied" while twenty-six agents across the
floor had never placed a single order. An occupied desk full of agents that cannot trade is the emptiest thing
here. Take an empty specialty only when one exists. Prefer structural edges that survive fees (maker fills, favourites,
settlement mechanics, calendar effects) to pattern-fitting. Each strategy is two files: `league/strategies/<stem>.py`,
which follows the strategy contract EXACTLY, and its own description `league/strategies/<stem>.json`, a JSON object
{"name", "family", "why"}. Never write `league/strategies/registry.json`: it is retired, and CI refuses it.
Names are lowercase with dashes (under 30 characters); the stem is the name with underscores.""",
    "toolsmith": """You are the toolsmith of a small trading league. Agents run strategy programs in sealed boxes with no
network; they may only import a short list of standard modules plus `tools`, a package of pure helper modules
you maintain. Agents file requests in plain words. Build what is asked when it can be built as PURE PYTHON over
the data a strategy already receives (indicators, estimators, pricing formulas, calendars). A request that
needs new data cannot be met by you: identify the specific missing input, smallest reproduction and
acceptance check. It will remain BLOCKED in the engineering backlog; an answer does not fulfill it.
Each tool is `league/tools/<name>.py` (same safety
rules as a strategy: whitelisted imports only, no files, no network, no attribute assignment) with a docstring
an agent can learn it from, plus `league/tests/test_tool_<name>.py` (unittest) proving it right on known values.
Also answer every request you read, in an extra key of your JSON:
"answers": [{"request": "<the request's id>", "outcome": "built as tools/<name>.py: how to use it" | "cannot be a pure tool: why, and who could do it"}]""",
    "operator": """You are the operator of a small trading league's House process. You read its alerts, health and budget.
You may propose changes ONLY to the operating dials in `league/config.json`, and only inside the bounds listed in
your evidence as `permitted_dials` -- those are read from the checker that will judge your pull request, so they
are the real ones. Do not carry any bound in your head: on Sept 20, 2026 this brief named a maximum that the
checker had since raised, and you proposed the same change three times, one of which merged and throttled the
floor's research below what the owner's budget funds. Give the WHOLE file back with only those values changed. Everything else (real_money, URLs, the performance baseline) belongs to the owner.
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

    def failures(self, number: int) -> dict[str, Any]:
        """Why CI refused: the failed check runs and their error annotations (`league.ci` writes
        each refusal as one). Raises ForgeError when the gateway does not offer the read."""
        return self._call("GET", f"{self.base}/{int(number)}/failures")


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

    def failures(self, number: int) -> dict[str, Any]:
        head = self.status(number).get("head")
        done = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{head}/check-runs?per_page=100"], cwd=self.repo, capture_output=True, text=True)
        if done.returncode != 0:
            raise ForgeError(f"gh api failed: {done.stderr.strip()[:300]}")
        failed = []
        for run in json.loads(done.stdout).get("check_runs") or []:
            if run.get("status") != "completed" or run.get("conclusion") in ("success", "neutral", "skipped"):
                continue
            notes = subprocess.run(["gh", "api", f"repos/{{owner}}/{{repo}}/check-runs/{run['id']}/annotations"], cwd=self.repo, capture_output=True, text=True)
            listed = json.loads(notes.stdout) if notes.returncode == 0 else []
            failed.append({"name": run.get("name"), "conclusion": run.get("conclusion"),
                           "annotations": [{"message": str(a.get("message") or "")[:2000], "title": a.get("title")} for a in listed[:20]]})
        return {"number": int(number), "head": head, "failures": failed}


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
    legacy_rows: list[Any] = []
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
                parsed = json.loads(content)
                if path == ci.RETIRED_REGISTRY:
                    # The shared list is retired (`league/strategies/__init__.py`): a stale whole copy
                    # of it is how one proposal deleted another's row. Only the rows describing files
                    # this proposal itself carries are kept, each as that strategy's own file.
                    legacy_rows.extend(parsed if isinstance(parsed, list) else [])
                    continue
                if path.startswith("league/strategies/"):
                    from .strategies import _row

                    stem = path.rsplit("/", 1)[1][:-5]
                    described, why = _row(parsed, stem=stem)
                    if described is None:
                        problems = [f"{path}: {why}"]
            except ValueError:
                problems = [f"{path}: not valid JSON"]
        if problems or len(content) > 60_000:
            dropped.extend(problems or [f"{path}: over 60,000 characters"])
        else:
            files.append({"path": path, "content": content})
    carried = {f["path"] for f in files}
    for item in legacy_rows:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            continue
        # Repo-relative paths are the one known packaging mismatch; nothing else is collapsed.
        match = re.fullmatch(r"(?:league/strategies/)?([a-z][a-z0-9_]*)\.py", item["file"])
        if not match or f"league/strategies/{match[1]}.py" not in carried or f"league/strategies/{match[1]}.json" in carried:
            continue
        from .strategies import _row, describe

        described, _ = _row({**item, "file": f"{match[1]}.py"}, stem=None)
        if described is not None:
            name, content = describe(described)
            files.append({"path": f"league/strategies/{name}", "content": content})
            carried.add(f"league/strategies/{name}")
    slug = re.sub(r"[^a-z0-9-]+", "-", str(answer.get("slug") or role).lower()).strip("-")[:48] or role
    answers = [a for a in (answer.get("answers") if isinstance(answer.get("answers"), list) else []) if isinstance(a, dict)][:20]
    return Proposal(role, str(answer.get("summary") or "")[:1500], slug, str(answer.get("title") or f"Merton ({role})")[:110],
                    str(answer.get("body") or "")[:7000], files, dropped, cost, answers)


#: A consultation's output room and reasoning effort. Measured Sept 22, 2026: at 12,000 tokens and
#: "high" effort, five of seven consultations after midnight spent the whole allowance reasoning and
#: came back incomplete -- the agent paid about $0.73 each for nothing, and the ones that finished
#: cost the same, so they were at the ceiling too. The auditor answers at "medium" in 12,000 and
#: has never run out. 16,000 is the gateway's ceiling.
CONSULT_OUTPUT_TOKENS = 16000
CONSULT_EFFORT = "medium"

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


#: The real-money books (`House.REAL_BOOKS`): the only money the floor's P&L is measured in.
REAL_BOOKS = ("kalshi", "alpaca")


class RealPnl:
    """The floor's 24-hour REAL P&L, as `merton.paused_until_profit` reads it: the realized result of
    the real books over the last `hours` -- each settlement's `pnl` and each closing fill's
    `realized` on `kalshi` and `alpaca`, fees included, practice books never.

    Why the books' realized rows and not the allocator's `floor_pnl` (Sept 24, 2026): `floor_pnl`
    is a level, equity less stake over every account the real books have held since they began (a
    sweep moves cash and stake together, so it keeps an account's result). It has no 24-hour
    window: its change over a day needs a reading from a day before, which the House does not keep
    across a restart, and it moves with the marks of positions still open. The ledger's settlements
    and closing fills are the venue's own verdicts, windowed exactly, and they survive a restart.
    What they leave out is the mark of positions still open, which a day-horizon book settles within
    a day or three. At T0 of the close-the-gaps run this read +$5.10 over 24 hours (34 settlements)
    and -$2.73 over the last six; `floor_pnl` read +$0.75.

    Read incrementally (only rows after the last one seen) at most every `every_seconds`."""

    def __init__(self, ledger: Any, clock: Callable[[], float] = time.time, *, hours: float = 24.0, every_seconds: float = 300.0):
        self.ledger, self.clock = ledger, clock
        self.window, self.every = float(hours) * 3600, float(every_seconds)
        self._rows: deque = deque()
        self._seq = 0
        self._at = float("-inf")
        self._value: tuple[Decimal, int] = (Decimal(0), 0)
        self._lock = threading.Lock()

    def __call__(self) -> tuple[Decimal, int]:
        """(realized USD over the window, the settlements and closing fills it comes from)."""
        with self._lock:
            now = self.clock()
            if now - self._at < self.every:
                return self._value
            for entry in self.ledger.iter(kinds=("book.settle", "book.fill"), after=self._seq):
                self._seq = entry.seq
                p = entry.payload
                if p.get("book") not in REAL_BOOKS or p.get("real_money") is False or p.get("source") == "dust":
                    continue
                amount = p.get("pnl") if entry.kind == "book.settle" else p.get("realized")
                if amount is None:
                    continue  # an opening fill realizes nothing
                try:
                    self._rows.append((_epoch(entry.at), Decimal(str(amount))))
                except (InvalidOperation, ValueError):
                    continue
            while self._rows and self._rows[0][0] < now - self.window:
                self._rows.popleft()
            self._value = (sum((amount for _, amount in self._rows), Decimal(0)), len(self._rows))
            self._at = now
            return self._value


class Merton:
    def __init__(self, frontier: Frontier, forge: Any, ledger: Ledger, *, evidence: Callable[[str], dict[str, Any]], clock=time.time,
                 schedule_hours: Mapping[str, float] | None = None, first_after_hours: Mapping[str, float] | None = None, pace: Any = None,
                 effort: Mapping[str, str] | None = None, backoff_max: Mapping[str, int] | None = None,
                 paused_until_profit: Iterable[str] | None = None, real_pnl: Callable[[], tuple[Decimal, int]] | None = None):
        self.frontier = frontier
        self.forge = forge
        self.ledger = ledger
        self.evidence = evidence
        self.clock = clock
        #: Roles that do not sit down while the floor's 24-hour real P&L is not positive (game.json
        #: `merton.paused_until_profit`; Sept 24, 2026). `real_pnl` measures it (`RealPnl`).
        self.paused_until_profit = frozenset(r for r in (paused_until_profit or ()) if r in ROLES)
        self.real_pnl = real_pnl or RealPnl(ledger, clock)
        #: role -> paused, as last recorded (seeded from the ledger's newest rows, so a restart does
        #: not record a pause again), and the reading it was decided on.
        self._paused: dict[str, bool] | None = None
        self._pnl_seen: tuple[Decimal, int] | None = None
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
        #: The most times its usual wait a role's empty passes may stretch it (default eight).
        self.backoff_max = dict(backoff_max or {})
        #: When `follow` last asked about each refused change (in memory: a restart asks again once).
        self._polled: dict[int, float] = {}

    # ---------------------------------------------------------------- consult
    def consult(self, agent: Any, question: str, evidence: Mapping[str, Any], *, contract: str,
                max_output_tokens: int = CONSULT_OUTPUT_TOKENS, effort: str = CONSULT_EFFORT) -> dict[str, Any]:
        """One agent hires Merton with its own credits. Returns `{"answer", "code", "confidence",
        "cost_usd"}`; `code` is empty unless Merton wrote a whole strategy file. Never raises: a
        refused call costs nothing; an unreadable paid answer retains its metered cost."""
        system = CONSULT + "\n\nTHE STRATEGY CONTRACT (the file format any code you write must follow)\n\n" + contract
        reply = None
        effort = effort if effort in ("low", "medium", "high") else CONSULT_EFFORT
        try:
            reply = self.frontier.ask(system=system, user=json.dumps({"question": question, "evidence": evidence}, default=str),
                                      agent=f"consult-{agent.id}", max_output_tokens=max(4000, min(int(max_output_tokens), 16000)),
                                      effort=effort)
            answer = reply.json()
        except FrontierError as exc:
            detail = "could not be reached" if reply is None else "returned an unreadable answer"
            row = {"answer": f"Merton {detail} ({exc}).", "code": "", "confidence": "low",
                   "cost_usd": format(reply.cost_usd, "f") if reply is not None else "0", "error": True}
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
        held = self._held()
        out = []
        for role in ROLES:
            if role in held:
                continue  # paused until the floor's 24-hour real P&L is positive
            last = self.last_pass(role)
            if last is None:
                if running_hours >= self.first_after_hours.get(role, 0):
                    out.append(role)
            elif now - last >= self.schedule_hours[role] * self._pace() * self.backoff(role) * 3600:
                out.append(role)
        return out

    def _held(self) -> frozenset[str]:
        """The roles of `paused_until_profit` while the floor's 24-hour real P&L is not positive,
        with one `ops.budget` row ("merton pause") each time a role pauses or resumes.

        Sept 24, 2026 (the close-the-gaps run, L2): the architect ($57), teacher ($21), toolsmith
        ($19), operator ($15) and designer ($8) had spent about $120 of the frontier month for about
        one positive forward record. The auditor, the consultant and the engineer are not roles of
        this class and keep their cadence; the teacher is paced by its schedule instead."""
        if not self.paused_until_profit:
            return frozenset()
        try:
            pnl, count = self.real_pnl()
        except Exception:  # noqa: BLE001 - a P&L that cannot be read pauses nobody
            return frozenset()
        self._pnl_seen = (pnl, count)
        paused = pnl <= 0
        if self._paused is None:
            self._paused = {}
            for entry in self.ledger.read(kinds="ops.budget", limit=2000, newest=True):
                if entry.payload.get("what") == "merton pause" and entry.payload.get("role") in ROLES:
                    self._paused[entry.payload["role"]] = bool(entry.payload.get("paused"))
        for role in sorted(self.paused_until_profit):
            if self._paused.get(role, False) == paused:
                continue
            self._paused[role] = paused
            self.ledger.append("ops.budget", {
                "what": "merton pause", "role": role, "paused": paused, "real_pnl_24h_usd": format(pnl, "f"), "settlements": count,
                "reason": ("the floor's real P&L over the last 24 hours is not positive: the role does not sit down until it is"
                           if paused else "the floor's real P&L over the last 24 hours is positive: the role sits down again")})
        return self.paused_until_profit if paused else frozenset()

    def pause_state(self) -> dict[str, Any] | None:
        """What `health.json` says of the pause: the roles waiting and the reading they wait on."""
        if not self.paused_until_profit:
            return None
        pnl, count = self._pnl_seen if self._pnl_seen is not None else (None, None)
        return {"roles": sorted(self.paused_until_profit), "paused": sorted(r for r, v in (self._paused or {}).items() if v and r in self.paused_until_profit),
                "real_pnl_24h_usd": format(pnl, "f") if pnl is not None else None, "settlements": count,
                "measure": "realized: the real books' settlements and closing fills over the last 24 hours"}

    def backoff(self, role: str) -> int:
        """How many times its usual wait a role serves after passes that changed nothing: one empty
        pass is normal, each further one in a row doubles the wait, up to eight times, and it is
        back to one the moment a pass proposes a change.

        Measured Sept 21, 2026: in four hours the operator sat down fifteen times at a quarter-hour
        cadence and answered "leave the dials unchanged" every time, and the designer, teacher,
        toolsmith and architect mostly the same -- about $4 an hour of the frontier month for no
        change, while agents that had earned him waited on the same month. A pass that was skipped
        (nothing to do, nothing spent) neither counts nor resets."""
        rows = [e.payload for e in self.ledger.read(kinds="merton.pass", limit=500, newest=True) if e.payload.get("role") == role]
        empty = 0
        for row in reversed(rows):
            if row.get("skipped"):
                continue
            if int(row.get("files") or 0) > 0:
                break
            empty += 1
        return min(2 ** min(max(empty - 1, 0), 3), int(self.backoff_max.get(role, 8)))

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
        answer = None
        try:
            answer = self.frontier.ask(system=system, user=json.dumps(evidence, default=str), agent=f"merton-{role}",
                                       max_output_tokens=12000 if role in ("architect", "toolsmith") else 5000,
                                       effort=str(self.effort.get(role) or "medium"))
            proposal = parse_proposal(role, answer.json(), answer.cost_usd)
        except FrontierError as exc:
            return self._record(role, {"summary": f"the pass failed: {exc}",
                                      "cost_usd": format(answer.cost_usd, "f") if answer is not None else "0", "files": 0, "error": True})
        row = {"summary": proposal.summary, "cost_usd": format(proposal.cost_usd, "f"), "files": len(proposal.files), "dropped": proposal.dropped[:10]}
        answers = []
        if role == "toolsmith":
            waiting = {r.get("id") for r in evidence.get("open_requests") or []
                       if isinstance(r, dict) and isinstance(r.get("id"), str)}
            # Model output is untrusted; one request has one durable resolution, even when
            # the model repeats itself. Bad IDs must not discard a paid pass's cost record.
            unique = {item["request"]: {"request": item["request"], "outcome": str(item["outcome"])[:1200]}
                      for item in proposal.answers
                      if isinstance(item.get("request"), str) and item["request"] in waiting
                      and str(item.get("outcome") or "").strip()}
            answers = list(unique.values())
            # A diagnosis does not supply data or ship code. Preserve it for an engineering
            # worker instead of reporting success and deleting the request from the queue.
            if not proposal.files and not proposal.dropped:
                for item in answers:
                    self.ledger.append("tool.blocked", {**item, "change": None, "status": "blocked",
                                                        "owner": "house-engineering"})
        if proposal.files:
            try:
                made = self.forge.propose(role=role, slug=proposal.slug, title=proposal.title, body=proposal.body, files=proposal.files)
                row.update(branch=made.get("branch"), number=made.get("number"), url=made.get("url"))
                self.ledger.append("merton.change", {"role": role, "branch": made.get("branch"), "number": made.get("number"), "title": proposal.title,
                                                    "status": "opened", "paths": [f["path"] for f in proposal.files],
                                                    "tool_answers": answers,
                                                    "file_digests": {f["path"]: hashlib.sha256(f["content"].encode()).hexdigest() for f in proposal.files}})
            except ForgeError as exc:
                row["forge_error"] = str(exc)[:300]
        return self._record(role, row)

    def _record(self, role: str, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = {"role": role, "at_epoch": self.clock(), **dict(row)}
        self.ledger.append("merton.pass", payload)
        return payload

    # ------------------------------------------------------------------ follow
    #: How often a change CI refused is asked about again. It stays followed -- a re-run, a new
    #: commit on its branch or a merge by hand is how a refused proposal gets repaired -- but it
    #: is not asked every tick: a dozen refused changes polled each minute is 1,400 GitHub calls
    #: an hour through one token.
    REFUSED_POLL_SECONDS = 900.0
    #: A refused change untouched for this long is no longer asked about.
    REFUSED_FOLLOW_DAYS = 14.0

    def follow(self) -> list[dict[str, Any]]:
        """Ask the gateway what CI made of each change still in play, and record the verdicts.

        Until Sept 22, 2026 a change CI refused was never asked about again, so a refusal was final
        on the ledger even when the pull request was later fixed and merged: the toolsmith's PR #46
        answered its requests in `tool_answers`, was refused, and those requests could never be
        closed. A refused change is now followed until it merges, closes or goes stale; a new
        refusal of a NEW head is its own row (the repair engineer's revisions are judged per head);
        and a merge still closes its tool requests only once the running release holds the files
        (`_fulfil_deployed`: a merge is not a deployment)."""
        latest: dict[int, dict[str, Any]] = {}
        opened_at: dict[int, str] = {}
        for entry in self.ledger.iter(kinds="merton.change"):
            if entry.payload.get("number") is not None:
                latest[int(entry.payload["number"])] = dict(entry.payload)
                opened_at.setdefault(int(entry.payload["number"]), entry.at)
        polled = self._polled
        now = self.clock()
        out = []
        for number, row in latest.items():
            if row.get("status") == "merged":
                deployed = self._fulfil_deployed(row)
                if deployed is not None:
                    out.append(deployed)
                continue
            if row.get("status") == "refused by CI":
                if now - polled.get(number, float("-inf")) < self.REFUSED_POLL_SECONDS:
                    continue
                if now - _epoch(opened_at[number]) > self.REFUSED_FOLLOW_DAYS * 86400:
                    continue
            elif row.get("status") not in ("opened", "pending"):
                continue
            polled[number] = now
            try:
                status = self.forge.status(number)
            except ForgeError:
                continue
            checks = (status.get("checks") or {}).get("conclusion")
            verdict = ("merged" if status.get("merged") else "closed" if status.get("state") == "closed"
                       else "refused by CI" if checks == "failure" else "pending")
            head = status.get("head") if isinstance(status.get("head"), str) else None
            if verdict == "pending":
                continue
            if verdict == row.get("status") and (verdict != "refused by CI" or head is None or head == row.get("head")):
                continue
            row = {**row, "status": verdict, **({"head": head} if head else {})}
            self.ledger.append("merton.change", row)
            out.append(row)
            if verdict == "merged":
                deployed = self._fulfil_deployed(row)
                if deployed is not None:
                    out.append(deployed)
        return out

    def _fulfil_deployed(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        """Finish a tool request only when this process is running the accepted file contents.

        A merge is not a deployment. Persisting answers and hashes on the change also means
        a restart cannot lose the work waiting for the updater and its canary.
        """
        answers, digests = row.get("tool_answers"), row.get("file_digests")
        if not answers or not digests:
            return None
        root = Path(__file__).resolve().parents[1]
        for name, expected in digests.items():
            if ci.guard([name], "toolsmith"):
                return None
            try:
                if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                    return None
            except OSError:
                return None
        for item in answers:
            self.ledger.append("tool.fulfilled", {**item, "change": row.get("branch"), "status": "deployed"},
                               id=f"tool-deployed:{row['number']}:{item['request']}")
        deployed = {**row, "status": "deployed"}
        self.ledger.append("merton.change", deployed)
        return deployed


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0


def _how_the_desk_is_doing(house: Any, niche_id: str) -> dict[str, Any]:
    """How a specialty's members are really faring: how many cannot trade at all, how many trade
    and lose, and the best growth anyone there has managed. An architect told only that a desk has
    members will leave it alone; told that all six of them have placed nothing, it has work to do."""
    barren = losing = traded = 0
    best = None
    for agent in house.registry.living():
        if agent.niche != niche_id:
            continue
        standing = house.standing_of(agent.id)
        if standing.get('earned_observations', standing['active_blocks']) <= 0:
            barren += 1
            continue
        traded += 1
        growth = standing.get('earned_growth', standing['mean_growth'])
        if growth <= 0:
            losing += 1
        best = growth if best is None else max(best, growth)
    return {"barren_agents": barren, "trading_agents": traded, "losing_agents": losing,
            "best_mean_growth": None if best is None else round(best, 6)}


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
                                      "members": house.members(n.id), "universe": list(n.universe[:24]), "brief": n.brief[:700],
                                      # What actually decides where a new strategy is worth writing: not whether
                                      # anyone sits there, but whether anyone sitting there can trade or profit.
                                      **_how_the_desk_is_doing(house, n.id)}
                                     for n in house.niches.values()],
                        founding_seeds=[{k: s[k] for k in ("name", "family", "why")} for s in seeds.SEEDS],
                        registry=strategies.registry(), library=house.commons.library_search("edge evidence fees maker", 8)["results"])
        elif role == "toolsmith":
            base = {"open_requests": house.commons.open_requests(limit=10), "existing_tools": sorted(p.name for p in (Path(__file__).resolve().parent / "tools").glob("*.py"))}
        elif role == "operator":
            # Private (`_`-prefixed) keys stay out of the packet: since Deploy A (Sept 24, 2026) a failed
            # lab step's alert carries its `_traceback`, up to 2,000 characters, and sixty were copied.
            alerts = [{"at": e.at, **{k: v for k, v in e.payload.items() if not str(k).startswith("_")}}
                      for e in ledger.read(kinds="ops.alert", limit=60, newest=True)]
            budget = [{"at": e.at, **{k: v for k, v in e.payload.items() if not str(k).startswith("_")}}
                      for e in ledger.read(kinds="ops.budget", limit=20, newest=True)]
            from .ci import CONFIG_DIALS

            base = {"alerts": alerts, "budget": budget, "books": {n: {"frozen": b.frozen, "open_orders": len(b.open_orders())} for n, b in house.books.items()},
                    "config": json.loads(CONFIG_PATH.read_text(encoding="utf-8")), "living": len(house.registry.living()),
                    # The bounds from the checker that will judge the pull request, never from the
                    # brief: two places held this number, they disagreed, and the operator proposed
                    # the same reduction three times until one merged and throttled the floor.
                    "permitted_dials": {key: {"min": low, "max": high} for key, (low, high) in CONFIG_DIALS.items()}}
        elif role == "designer":
            from .economy import load_game

            base.update(game=load_game(), active_game=house.game,
                        game_file_note='game is the repository file to edit. active_game includes temporary owner-funded overrides. '
                                       'Do not copy those overrides into game.json; a base-file edit cannot change the active burst policy or its deadline.',
                        deaths=[{"agent": a.id, "cause": a.cause, "niche": a.niche} for a in house.registry.dead()][-30:],
                        payouts=[e.payload for e in ledger.read(kinds="ops.budget", limit=30, newest=True) if e.payload.get("what") == "payout"])
        elif role == "teacher":
            base.update(replay_trials=trials, lessons_so_far=[e.payload.get("title") for e in ledger.read(kinds="playbook.entry", limit=40, newest=True)],
                        today=time.strftime("%Y-%m-%d", time.gmtime(house.clock())))
        living = house.registry.living()
        from .constitution import CONSTITUTION
        guard = getattr(house, 'campaigns', None)
        from .overnight import active
        burst = (active(guard, house.clock) or guard.burst()) if guard else getattr(house, '_burst', None)
        base['qualification_policy'] = CONSTITUTION['ladder']
        base['learning_window'] = ({'id': burst['id'], 'ends': burst['ends'],
            'remaining_seconds': max(0, burst['ends'] - house.clock()) if burst['ends'] is not None else None,
            'guidance': 'Prioritize falsifiable improvements that can produce new forward observations in the remaining window. '
                        'Use shorter settlement/holding opportunities when an after-fee edge supports them. '
                        'Do not force turnover, assume profitability, or mistake repeated historical tests for new evidence.'}
            if burst and 'ends' in burst else None)
        base['live_pilot'] = guard.live_pilot() if guard else None
        base['live_trading'] = guard.live_trading() if guard else None
        states = getattr(house, '_state', {}).get('promotion_status', {})
        base['promotion_holds'] = [states[a.id] for a in living if a.id in states
                                   and states[a.id].get('stage') not in ('evidence', 'promoted')][-12:]
        base['engineering_backlog'] = house.commons.blocked_requests(limit=10)
        if getattr(house, 'semantic_lab', None) is not None:
            base['semantic_research'] = house.semantic_lab.evidence(limit=8)
        base['engineering_note'] = 'These requests remain unimplemented. Advice is not fulfillment. No current Merton role may edit House network adapters or core engine; do not claim those capabilities have been built.'
        if living and callable(getattr(house, 'research_capabilities', None)):
            current = house.research_capabilities(living[0])
            base['runtime_capabilities'] = {
                'as_of': current['as_of'], 'revision': current['revision'], 'authority': current['authority'],
                'implemented_replay_support': {key: current['replay'][key] for key in (
                    'alpaca_warmup', 'daily_execution_clock', 'settlement_clock', 'selection', 'limitations')},
                'observations': current['observations'], 'research': current['research'],
            }
        return base

    return gather
