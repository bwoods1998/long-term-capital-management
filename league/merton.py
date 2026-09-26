"""Repair proposals through the gateway. The swarm's architect keeps programs in private state.

Only the repair engineer proposes public, pure helper code and its tests. The gateway and CI repeat
its path guard; every PR requires an owner merge. This module never trades or deploys.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping
from . import ci
from .safety import CodeRefused, check_strategy_code
REPO = Path(__file__).resolve().parents[1]

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
    files, dropped, seen = [], [], set()
    listed = answer.get("files") if isinstance(answer.get("files"), list) else []
    for row in listed[:12]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not isinstance(row.get("content"), str):
            dropped.append("a file entry without a path and content")
            continue
        path, content = row["path"], row["content"]
        problems = ci.guard([path], role) if role in ci.ROLE_PATHS else ["unknown repair role"]
        if path in seen:
            problems.append(f"{path}: duplicate file")
        seen.add(path)
        if not problems and path.startswith("league/tools/") and path.endswith(".py"):
            try:
                check_strategy_code(content)
            except CodeRefused as exc:
                problems.append(f"{path}: {exc}")
        if problems or len(content) > 60_000:
            dropped.extend(problems or [f"{path}: over 60,000 characters"])
        else:
            files.append({"path": path, "content": content})
    slug = re.sub(r"[^a-z0-9-]+", "-", str(answer.get("slug") or role).lower()).strip("-")[:48] or role
    return Proposal(role, str(answer.get("summary") or "")[:1500], slug,
                    str(answer.get("title") or "Repair engineer")[:110], str(answer.get("body") or "")[:7000],
                    files, dropped, cost)

class ProposalFollower:
    """Read CI/owner merge results and recognize deployment by exact file digests. Never merge."""
    REFUSED_POLL_SECONDS = 900.0
    REFUSED_FOLLOW_DAYS = 14.0
    def __init__(self, forge: Any, ledger: Any, *, clock: Callable[[], float]):
        self.forge, self.ledger, self.clock = forge, ledger, clock
        self._polled = {}

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
            if ci.guard([name], "engineer"):
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


def _epoch(value: str) -> float:
    from .broker import instant
    moment = instant(value)
    return moment.timestamp() if moment is not None else 0.0
