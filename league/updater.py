"""How merged code reaches the House with no human step -- and why the code it brings cannot be
the judge that lets it in.

GitHub is the source of truth. The repository is public, so the House box needs no credential to
read it: every half hour the House reads the commit at the head of `main`, downloads THAT commit
(by its sha, never "whatever main is now") as a tarball, unpacks the trees a release is made of,
and compares the tree's digest with the release it is running. When they differ, and only when
every wall below holds, it hands the tree to the in-box watchdog (`league/watchdog.py`), which
runs it as a canary, promotes it, watches the House, and rolls back by itself if health degrades.
A tree that was refused on its content or rolled back once is never tried again: only new content.

The walls, in the order they are asked, each one fail-closed (no deploy, a warning on the ledger):

1. **Exact-commit attestation.** GitHub's own check runs, read from its public API, must show that
   every required job (`REQUIRED_CHECKS`) of the Checks workflow completed with `success` on the
   exact sha the tarball was downloaded for, reported by the GitHub Actions app itself
   (`CHECKS_APP`). Nothing is cached from one head to the next, and a check run for any other sha
   is ignored, so a later head never inherits an earlier head's approval. Commit statuses are
   ignored too: any token with write access can set one, while only GitHub Actions can create a
   check run in its own name. No answer from GitHub is no attestation: nothing deploys.
2. **The judges do not change by this path.** A candidate that changes any file the RUNNING
   release's `league/ci.py` lists as `FORBIDDEN` (the constitution, the ledger, the book, the
   evaluator, the auditor, this file, the watchdog, ci.py itself, the campaign and live-money
   files...) or whose `.github/workflows/` differ from `TRUSTED_WORKFLOWS_SHA256` is refused. Those
   files decide what "passed" means -- the workflow file decides what the attestation above even
   attests -- so a commit that changes them reaches the box only as the owner's own deploy
   (`scripts/floor_box.py deploy`), never through the gate it would loosen.
3. **The trusted content checks.** The RUNNING release's copy of `league/ci.py` (strategies and
   tools pass the safety check and replay without error, `game.json` is inside its bounds,
   `config.json` moved only its operating dials from the release it replaces) is run against the
   candidate tree, from the running release's directory, as its own process, with a scrubbed
   environment and a verdict line keyed by a nonce the judged code never sees.
4. **`real_money` may not change by this path.** Turning real money on is the owner's deploy from
   his own machine, never something `main` does to the box by itself.

Then the watchdog's canary, promotion, watch and rollback, exactly as before. The attestation
travels with the release: into the watchdog's deploy record (`deploys.jsonl`, whose every row of
this deploy then carries the sha) and onto the ledger (`ops.deploy`), and the watchdog refuses to
stage a tree whose digest is not the attested one.

Sept 20, 2026 went the other way -- the incoming tree judged itself -- because a judge one commit
out of date refused, silently and for ever, a commit that widened a bound and used the wider value
(`inference_daily_cap_usd`). That fixed a stall by handing the candidate its own verdict, which is
exactly what an autonomous engineer must not have. The stall is answered differently now: the
refusal is a warning on the ledger that names the rule and the commit, and a change to the judges
is, by design, the owner's deploy.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from .watchdog import Releases, iso, tree_digest

REPO = "bwoods1998/long-term-capital-management"
TREES = ("league", "ltcm", "playbooks", "scripts", "deploy")  # what scripts/floor_box.py sends too
MAX_TARBALL_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{40}$")

#: The jobs of `.github/workflows/checks.yml` whose check runs must all have succeeded on the exact
#: commit. `league/tests/test_updater.py` holds this list to the workflow file.
REQUIRED_CHECKS = ("gateway", "tests (3.11)", "tests (3.14)")
#: The only app whose check runs count. A personal token cannot create a check run at all, and a
#: GitHub App can create them only in its own name, so nothing an engineer holds can forge one of
#: these; it can forge a commit status, which is why statuses are not read.
CHECKS_APP = "github-actions"
#: sha256 over every file under `.github/workflows/` (see `workflows_digest`). The workflows decide
#: what a green check run means, so a candidate that changes them is refused here and reaches the
#: box only as the owner's deploy. The test suite fails on GitHub when this pin and the files
#: disagree, so a workflow edit that forgets the pin cannot pass its own checks either.
TRUSTED_WORKFLOWS_SHA256 = "7765396b4a6a9dd811ab9ab24bc9c9eba8b3279de8528e991bca1bacae4f950f"
#: How long main's head may sit with no completed required checks before the owner is told.
PENDING_ALERT_SECONDS = 2 * 3600
EGRESS_HINT = ("api.github.com is not on the box's egress allowlist; the owner adds it with "
               "`python3 scripts/floor_box.py hosts --add api.github.com`")


class UpdateError(RuntimeError):
    pass


def _open(opener: Any, request: urllib.request.Request, timeout: float, limit: int) -> bytes:
    with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError(f"{request.full_url} answered with more than {limit} bytes")
    return data


def resolve_head(repo: str = REPO, *, opener: Any = None, timeout: float = 30.0, branch: str = "main") -> str:
    """The sha at the head of `branch`, from github.com's git smart-HTTP ref advertisement.

    github.com is on the box's egress list and this endpoint has no API rate limit (it is what
    `git ls-remote` reads), so the head is known even when the API is out of reach."""
    request = urllib.request.Request(f"https://github.com/{repo}.git/info/refs?service=git-upload-pack",
                                     headers={"User-Agent": "ltcm-floor/1.0"})
    data = _open(opener, request, timeout, 4 * 1024 * 1024)
    wanted = f"refs/heads/{branch}"
    at = 0
    while at + 4 <= len(data):
        # pkt-lines: four hex digits of length (counting themselves), then the payload; "0000" is
        # a flush. A ref line is "<sha> <ref>", the first one with capabilities after a NUL.
        try:
            size = int(data[at:at + 4].decode("ascii"), 16)
        except ValueError as exc:
            raise UpdateError("github.com answered with something that is not a ref advertisement") from exc
        if size == 0:
            at += 4
            continue
        if size < 4:
            raise UpdateError("github.com answered with a malformed ref advertisement")
        body = data[at + 4:at + size].decode("utf-8", "replace").split("\0", 1)[0].strip()
        at += size
        parts = body.split(" ")
        if len(parts) == 2 and parts[1] == wanted and SHA.match(parts[0]):
            return parts[0]
    raise UpdateError(f"github.com did not advertise {wanted}")


def fetch_commit(sha: str, repo: str = REPO, *, opener: Any = None, timeout: float = 120.0) -> bytes:
    """The tarball of exactly this commit. By sha, never by branch name: the branch can move between
    the attestation and the download, and the tree that deploys must be the tree that was attested."""
    if not SHA.match(str(sha)):
        raise UpdateError(f"not a commit sha: {sha!r}")
    request = urllib.request.Request(f"https://codeload.github.com/{repo}/tar.gz/{sha}", headers={"User-Agent": "ltcm-floor/1.0"})
    data = _open(opener, request, timeout, MAX_TARBALL_BYTES)
    return data


def workflows_digest(tarball: bytes) -> str:
    """sha256 over `.github/workflows/*` in a GitHub tarball: each file's path and content digest,
    sorted. The same function over a checkout's `.github/workflows` gives the same value."""
    rows = []
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        for member in archive:
            parts = Path(member.name).parts[1:]
            if len(parts) >= 3 and parts[0] == ".github" and parts[1] == "workflows" and member.isfile():
                source = archive.extractfile(member)
                content = source.read() if source is not None else b""
                rows.append(f"{'/'.join(parts)}\0{hashlib.sha256(content).hexdigest()}\n")
    return hashlib.sha256("".join(sorted(rows)).encode("utf-8")).hexdigest()


def checkout_workflows_digest(root: Path) -> str:
    rows = [f"{p.relative_to(root).as_posix()}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n"
            for p in sorted((root / ".github" / "workflows").rglob("*")) if p.is_file()]
    return hashlib.sha256("".join(sorted(rows)).encode("utf-8")).hexdigest()


def unpack(tarball: bytes, target: Path, *, sha: str | None = None) -> int:
    """Write the release trees of a GitHub tarball under `target`. Regular files only, no links, no
    path that leaves the tree; modes are normalized the way `floor_box.py` writes them (0755 for a
    shell script, 0644 otherwise) so the same commit has the same digest whichever way it came.
    With `sha`, every member must sit under GitHub's `<repo>-<sha>/` directory: the archive is
    bound to the commit that was attested, not merely downloaded from a URL that named it."""
    count = 0
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        for member in archive:
            top = Path(member.name).parts[:1]
            if sha is not None and (not top or not top[0].endswith(f"-{sha}")):
                raise UpdateError(f"the tarball holds {member.name!r}, which is not under the commit {sha[:12]}")
            parts = Path(member.name).parts[1:]  # drop GitHub's "<repo>-<ref>/" directory
            if not parts or parts[0] not in TREES or not member.isfile():
                continue
            if any(part in ("..", "") or part.startswith(".") for part in parts) or member.size > MAX_FILE_BYTES:
                continue
            if "__pycache__" in parts or parts[-1].endswith((".pyc", ".pem", ".key", ".sqlite")):
                continue
            path = target.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            path.write_bytes(source.read())
            os.chmod(path, 0o755 if path.suffix == ".sh" else 0o644)
            count += 1
    if count == 0:
        raise UpdateError("the tarball held none of the release trees")
    return count


# ------------------------------------------------------------------------------ attestation
def judge_check_runs(sha: str, data: Mapping[str, Any], *, required: tuple[str, ...] = REQUIRED_CHECKS,
                     app: str = CHECKS_APP) -> dict[str, Any]:
    """GitHub's check runs for one commit -> `{"state": passed | pending | failed, "ok", ...}`.

    Only runs whose `head_sha` IS this sha and whose app is GitHub Actions count; for each required
    name the newest such run decides (a re-run supersedes the run it repeats). Anything missing or
    still running is pending; any other conclusion than `success` -- failure, cancelled, timed_out,
    skipped, neutral, action_required, stale -- is a failure. Pure, so the rule is testable alone."""
    runs = data.get("check_runs") if isinstance(data, Mapping) else None
    runs = [r for r in runs if isinstance(r, Mapping)] if isinstance(runs, list) else []
    counted = [r for r in runs if r.get("head_sha") == sha and ((r.get("app") or {}).get("slug") == app)]
    ignored = len(runs) - len(counted)
    checks, reasons, state = [], [], "passed"
    for name in required:
        mine = [r for r in counted if r.get("name") == name]
        if not mine:
            reasons.append(f"no check run named {name!r} from {app} on {sha[:12]} yet")
            state = "failed" if state == "failed" else "pending"
            continue
        newest = max(mine, key=lambda r: (int(r.get("id") or 0), str(r.get("started_at") or "")))
        row = {"name": name, "id": newest.get("id"), "status": newest.get("status"), "conclusion": newest.get("conclusion"),
               "completed_at": newest.get("completed_at"), "details_url": newest.get("details_url")}
        checks.append(row)
        if newest.get("status") != "completed":
            reasons.append(f"{name!r} is {newest.get('status')} on {sha[:12]}")
            state = "failed" if state == "failed" else "pending"
        elif newest.get("conclusion") != "success":
            reasons.append(f"{name!r} concluded {newest.get('conclusion')!r} on {sha[:12]}")
            state = "failed"
    total = data.get("total_count") if isinstance(data, Mapping) else None
    if isinstance(total, int) and total > len(runs):
        reasons.append(f"GitHub reported {total} check runs and returned {len(runs)}; the rest were not read")
        state = "failed" if state == "failed" else "pending"
    return {"sha": sha, "state": state, "ok": state == "passed", "checks": checks, "required": list(required),
            "app": app, "ignored_runs": ignored, "reasons": reasons, "source": "api.github.com check-runs"}


class GitHubChecks:
    """The production attestor: `(sha) -> attestation`, unauthenticated, from api.github.com.

    Unauthenticated means 60 requests an hour per address; the updater asks once per new tree, at
    most every half hour. A refusal, a rate limit, an unreachable host or an unreadable answer is
    `unavailable`, and unavailable deploys nothing."""

    def __init__(self, repo: str = REPO, *, opener: Any = None, timeout: float = 30.0, api: str = "https://api.github.com",
                 required: tuple[str, ...] = REQUIRED_CHECKS, app: str = CHECKS_APP):
        self.repo, self.opener, self.timeout, self.api = repo, opener, timeout, api.rstrip("/")
        self.required, self.app = tuple(required), app

    def __call__(self, sha: str) -> dict[str, Any]:
        url = f"{self.api}/repos/{self.repo}/commits/{sha}/check-runs?per_page=100"
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "ltcm-floor/1.0",
                                                       "X-GitHub-Api-Version": "2022-11-28"})
        try:
            data = json.loads(_open(self.opener, request, self.timeout, 4 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            limited = exc.headers.get("X-RateLimit-Remaining") == "0" if exc.headers else False
            return unavailable(sha, f"api.github.com answered HTTP {exc.code}" + (" (the hourly rate limit is spent)" if limited else ""))
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            hint = f": {EGRESS_HINT}" if "name resolution" in reason or "Name or service" in reason or "nodename" in reason else ""
            return unavailable(sha, f"api.github.com could not be reached ({reason[:160]}){hint}")
        except (OSError, ValueError, UpdateError) as exc:
            return unavailable(sha, f"api.github.com gave no readable answer ({type(exc).__name__}: {str(exc)[:160]})")
        return judge_check_runs(sha, data, required=self.required, app=self.app)


def unavailable(sha: str | None, reason: str) -> dict[str, Any]:
    return {"sha": sha, "state": "unavailable", "ok": False, "checks": [], "required": list(REQUIRED_CHECKS),
            "reasons": [reason], "source": "api.github.com check-runs"}


# ---------------------------------------------------------------------------------- updater
class Updater:
    def __init__(self, base: str | Path = "/workspace", *, repo: str = REPO, fetch: Callable[[str], bytes] | None = None,
                 launch: Callable[..., None] | None = None, clock: Callable[[], float] = time.time, every_seconds: int = 1800,
                 judge: Callable[[Path, Path], list[str]] | None = None, head: Callable[[], str] | None = None,
                 attest: Callable[[str], Mapping[str, Any]] | None = None, trusted: str | Path | None = None,
                 workflows_pin: str = TRUSTED_WORKFLOWS_SHA256):
        self.base = Path(base)
        self.releases = Releases(self.base)
        self.head = head or (lambda: resolve_head(repo))
        self.fetch = fetch or (lambda sha: fetch_commit(sha, repo))
        self.launch = launch or self._launch
        self.attest = attest or GitHubChecks(repo)
        #: The release whose checker judges: this process's own code, which is the release the
        #: watchdog made current and restarted the House into. Never the candidate's.
        self.trusted = Path(trusted) if trusted else Path(__file__).resolve().parents[1]
        #: (candidate tree, running tree) -> what refuses it. The TRUSTED release's content checks
        #: run against the candidate (`_judged_by_trusted`). Tests hand in a stub; nothing else should.
        self.judge = judge or self._judged_by_trusted
        self.workflows_pin = workflows_pin
        self.clock = clock
        self.every = every_seconds
        self._last = 0.0
        self._told: set[tuple[str, str]] = set()
        self._pending_since: dict[str, float] = {}

    def due(self) -> bool:
        return self.clock() - self._last >= self.every

    def _launch(self, source: Path, release_id: str, attestation: Path | None = None) -> None:
        """Hand the tree to the watchdog, detached: the canary and the watch outlive this process,
        which the promotion itself will restart. The known-good release's watchdog does the judging."""
        current = self.base / "current"
        log = open(self.base / "deploy.log", "ab")
        argv = [sys.executable, "-m", "league.watchdog", "deploy", "--base", str(self.base), "--source", str(source), "--id", release_id]
        if attestation is not None:
            argv += ["--attestation", str(attestation)]
        subprocess.Popen(
            argv, cwd=str(current if current.exists() else source), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "LEAGUE_ENV": str(self.base / ".env")},
        )

    def tried(self) -> set[str]:
        """The releases the watchdog has really judged. A row marked `busy` is not one of them: it
        means another deploy held the lock, so the code was never unpacked, let alone run. And the
        promotion's own restart makes that race the NORMAL case -- the House comes up, its updater
        checks on the first tick, and the previous deploy is still inside its ten-minute watch. A
        commit retired on one of those was retired for good, with no retry and no expiry, silently:
        a floor that rewrites itself would have dropped its own improvements one at a time.

        Nor is a row marked `unjudged`: a head not yet (or not) attested by GitHub, or one refused
        for workflows that are not part of the tree. Those verdicts belong to a commit, and the same
        tree under a later commit whose checks pass must still be deployable."""
        return {str(row["release"]) for row in self.releases.history()
                if row.get("release") and not row.get("busy") and not row.get("unjudged")}

    def _trusted_identity(self) -> dict[str, Any]:
        def sha_of(name: str) -> str | None:
            try:
                return hashlib.sha256((self.trusted / "league" / name).read_bytes()).hexdigest()
            except OSError:
                return None

        return {"release": self.trusted.name, "ci_sha256": sha_of("ci.py"), "updater_sha256": sha_of("updater.py"),
                "workflows_pin": self.workflows_pin}

    def check(self) -> dict[str, Any]:
        """One look at main. Returns what was found and what was done. `new` is True the first
        time a refusal or a block is seen for this commit, which is when the House says so."""
        self._last = self.clock()
        current = self.releases.current()
        if current is None:
            return {"action": "none", "reason": "there is no current release to compare with"}
        running = self.base / "releases" / current
        try:
            sha = str(self.head()).strip().lower()
            if not SHA.match(sha):
                raise UpdateError(f"main's head is not a commit sha: {sha[:60]!r}")
        except Exception as exc:  # noqa: BLE001 - no head, no deploy
            return self._blocked(None, None, unavailable(None, f"main's head could not be read ({type(exc).__name__}: {str(exc)[:200]})"))
        incoming = self.base / "incoming" / f"main-{int(self.clock())}"
        try:
            tarball = self.fetch(sha)
            unpack(tarball, incoming, sha=sha)
        except Exception as exc:  # noqa: BLE001
            _remove(incoming)
            return self._blocked(None, sha, unavailable(sha, f"the tarball of {sha[:12]} could not be read ({type(exc).__name__}: {str(exc)[:200]})"))
        digest, files = tree_digest(incoming)
        if digest == tree_digest(running)[0]:
            _remove(incoming)
            return {"action": "none", "reason": "the box already runs main", "digest": digest[:12], "sha": sha}
        release_id = f"main-{digest[:12]}"
        if release_id in self.tried():
            _remove(incoming)
            return {"action": "none", "reason": f"{release_id} was already tried; only a new commit is tried again", "digest": digest[:12], "sha": sha}
        # 1. GitHub's checks on this exact commit. Asked afresh for every head: nothing is carried over.
        try:
            attestation = dict(self.attest(sha))
        except Exception as exc:  # noqa: BLE001 - an attestor that fails has attested nothing
            attestation = unavailable(sha, f"the attestation could not be read ({type(exc).__name__}: {str(exc)[:200]})")
        if attestation.get("sha") != sha:
            attestation = {**unavailable(sha, f"the attestation names {str(attestation.get('sha'))[:12]}, not {sha[:12]}"), "claimed": attestation.get("sha")}
        attestation.update(tree_digest=digest, workflows_sha256=workflows_digest(tarball), trusted=self._trusted_identity(), at=iso(self.clock()))
        if not attestation.get("ok") or attestation.get("state") != "passed":
            _remove(incoming)
            return self._blocked(release_id, sha, attestation)
        self._pending_since.pop(sha, None)
        # 2 + 3 + 4. What the candidate may not decide for itself, judged by code it could not edit.
        workflow_problems = self.workflow_problems(attestation["workflows_sha256"])
        if workflow_problems:
            _remove(incoming)
            return self._refused(release_id, sha, attestation, workflow_problems, unjudged=True)
        problems = self.vet(incoming, running)
        if problems:
            _remove(incoming)
            return self._refused(release_id, sha, attestation, problems)
        final = self.base / "incoming" / release_id
        _remove(final)
        incoming.rename(final)
        record = self.base / "incoming" / f"{release_id}.attestation.json"
        record.write_text(json.dumps(attestation, sort_keys=True, default=str), encoding="utf-8")
        self.launch(final, release_id, record)
        return {"action": "deploying", "release": release_id, "files": files, "sha": sha, "attestation": attestation}

    def _blocked(self, release_id: str | None, sha: str | None, attestation: Mapping[str, Any]) -> dict[str, Any]:
        """Not attested: nothing deploys. Pending is the normal state of a fresh head (the checks
        take minutes) and is only reported once it has lasted `PENDING_ALERT_SECONDS`; a failure or
        an unreachable GitHub is reported the first time it is seen for a commit."""
        state = str(attestation.get("state") or "unavailable")
        key = (sha or "-", state)
        if state == "pending" and sha:
            since = self._pending_since.setdefault(sha, self.clock())
            new = self.clock() - since >= PENDING_ALERT_SECONDS and key not in self._told
        else:
            new = key not in self._told
        if new:
            self._told.add(key)
            self.releases.record({"release": release_id, "stage": "attest", "verdict": "waiting" if state == "pending" else "blocked",
                                  "unjudged": True, "sha": sha, "reasons": list(attestation.get("reasons") or [])[:10],
                                  "attestation": dict(attestation)})
        action = "waiting" if state == "pending" else "blocked"
        return {"action": action, "release": release_id, "sha": sha, "reasons": list(attestation.get("reasons") or []),
                "attestation": dict(attestation), "new": new}

    def _refused(self, release_id: str, sha: str, attestation: Mapping[str, Any], problems: list[str], *, unjudged: bool = False) -> dict[str, Any]:
        self.releases.record({"release": release_id, "stage": "vet", "verdict": "refused", "reasons": problems[:10], "sha": sha,
                              "attestation": dict(attestation), **({"unjudged": True} if unjudged else {})})
        key = (sha, "refused")
        new = key not in self._told
        self._told.add(key)
        return {"action": "refused", "release": release_id, "sha": sha, "reasons": problems, "attestation": dict(attestation), "new": new}

    def workflow_problems(self, digest: str) -> list[str]:
        if digest == self.workflows_pin:
            return []
        return [f".github/workflows differ from the ones this release trusts (sha256 {digest[:12]}, trusted {self.workflows_pin[:12]}): "
                "the workflows decide what a passing check means, so a change to them is the owner's deploy"]

    def vet(self, incoming: Path, running: Path) -> list[str]:
        """What the candidate may not decide for itself, judged by the RUNNING release.

        The real-money switch is the owner's own deploy. The judges -- every file the running
        `league/ci.py` forbids to every role -- do not change by this path at all. Then the running
        release's content checks, run against the candidate tree. GitHub has already run the
        candidate's OWN checks and its whole test suite on the same commit (the attestation); those
        are the supplement, not the judge."""
        problems = []
        try:
            new = json.loads((incoming / "league" / "config.json").read_text(encoding="utf-8"))
            old = json.loads((running / "league" / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"league/config.json cannot be read: {exc}"]
        if bool(new.get("real_money")) != bool(old.get("real_money")):
            problems.append("league/config.json changes real_money: that switch is the owner's own deploy, never an automatic update")
        problems += protected_changes(incoming, running)
        if problems:
            return problems  # a candidate that edits its judges is not run through them
        return list(self.judge(incoming, running))

    def _judged_by_trusted(self, incoming: Path, running: Path) -> list[str]:
        """The TRUSTED release's content checks, applied to the candidate tree, as their own process.

        A subprocess, not an import: the checks execute the candidate's strategy files (their module
        bodies and a canned replay), and this process holds the House's secrets. The subprocess runs
        from the trusted release's directory with only that directory on its path, so every line of
        judging code -- ci.py, the replay simulator, the safety scanner, the bounds -- is the
        running release's; the candidate supplies only the files being judged. The verdict must
        come back on a line carrying a nonce handed over stdin before any candidate code is loaded."""
        trusted = self.trusted
        if not (trusted / "league" / "ci.py").exists():
            return [f"the trusted release {trusted.name} has no league/ci.py to judge with"]
        nonce = secrets.token_hex(16)
        env = {**vet_environment(), "PYTHONPATH": str(trusted), "PYTHONDONTWRITEBYTECODE": "1"}
        argv = [sys.executable, "-m", "league.ci", "--content-only", "--root", str(Path(incoming).resolve()),
                "--baseline", str(Path(running).resolve()), "--nonce-stdin"]
        try:
            done = subprocess.run(argv, cwd=str(trusted), input=nonce + "\n", capture_output=True, text=True, timeout=600, env=env)
        except (OSError, subprocess.SubprocessError) as exc:
            return [f"the trusted checks could not be run: {type(exc).__name__}: {str(exc)[:200]}"]
        verdict = None
        for line in done.stdout.splitlines():
            if line.startswith(f"VERDICT {nonce} "):
                try:
                    verdict = json.loads(line[len(f"VERDICT {nonce} "):])
                except ValueError:
                    verdict = None
        if not isinstance(verdict, dict):
            return [f"the trusted checks gave no verdict (exit {done.returncode}): {(done.stderr or done.stdout)[-300:]}"]
        if done.returncode == 0 and verdict.get("passed") is True and not verdict.get("problems"):
            return []
        return [str(p) for p in verdict.get("problems") or []] or [f"the trusted checks refused it (exit {done.returncode})"]


def protected_changes(incoming: Path, running: Path) -> list[str]:
    """The files of the running release's judges that the candidate adds, removes or changes.

    The list is the RUNNING `league/ci.py`'s `FORBIDDEN`, imported from this process's own package
    (importing it executes no candidate code). Only the release trees are compared: `gateway/` and
    `.github/` never reach the box as files (the workflows are pinned by `TRUSTED_WORKFLOWS_SHA256`)."""
    from .ci import FORBIDDEN

    def files(root: Path) -> dict[str, Path]:
        out = {}
        for top in TREES:
            for path in (root / top).rglob("*") if (root / top).is_dir() else ():
                if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"):
                    out[path.relative_to(root).as_posix()] = path
        return out

    def guarded(name: str) -> bool:
        lowered = name.lower()
        return any(lowered == f or (f.endswith("/") and lowered.startswith(f)) for f in FORBIDDEN)

    mine, theirs = files(Path(running)), files(Path(incoming))
    changed = []
    for name in sorted(set(mine) | set(theirs)):
        if not guarded(name):
            continue
        if name not in mine or name not in theirs or mine[name].read_bytes() != theirs[name].read_bytes():
            changed.append(name)
    if not changed:
        return []
    return [f"{name}: the release's judges and money rules do not change by an automatic update; this one is the owner's deploy "
            "(scripts/floor_box.py deploy)" for name in changed]


#: All the trusted checks may see of the House's environment. Those checks EXECUTE strategy code
#: Merton wrote (its module body and a canned replay), and this process holds the House's three
#: secrets in its environment (`service.load_env`): until Sept 22, 2026 nothing but the source
#: scanner stood between that code and the gateway, Sail and site tokens. The checks need no
#: credential and no network, so they get neither the secrets nor the path to the file that holds
#: them (`LEAGUE_ENV`).
VET_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "PYTHONHASHSEED", "SYSTEMROOT")


def vet_environment() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if name in VET_ENV_KEEP}


def _remove(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
