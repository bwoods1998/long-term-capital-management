"""How merged code reaches the House with no human step -- and why the code it brings cannot be
the judge that lets it in.

GitHub is the source of truth. The repository is public, so the House box needs no credential to
read it: every half hour the House reads the commit at the head of `main`, downloads THAT commit
(by its sha, never "whatever main is now") as a tarball, unpacks the trees a release is made of,
and compares the tree's digest with the release it is running. When they differ, and only when
every wall below holds, it hands the tree to the in-box watchdog (`league/watchdog.py`), which
runs it as a canary, promotes it, watches the House, and rolls back by itself if health degrades.
A tree that was refused on its content is never tried again, nor one rolled back twice: only new
content (a first rollback is retried once, at the next release train; wall 5).

The walls, in the order they are asked, each one fail-closed (no deploy, a warning on the ledger):

1. **Exact-commit attestation.** GitHub's public API must show a run of the pinned Checks workflow
   (`CHECKS_WORKFLOW`) on the exact sha the tarball was downloaded for, started by a push to main,
   a dispatch or the schedule, completed with `success`, and every required job of it
   (`REQUIRED_CHECKS`) completed with `success` on that sha. Workflow runs and their jobs, not bare
   check runs or commit statuses: a status can be set by any token with write access, and a check
   run can be created through the API by ANY workflow granted `checks: write`, in the name of
   GitHub Actions itself -- but only a real run of the workflow file has jobs. Nothing is cached
   from one head to the next and anything about another sha is ignored, so a later head never
   inherits an earlier head's approval. No answer from GitHub is no attestation: nothing deploys.
2. **The judges do not change by this path.** A candidate that changes any file the RUNNING
   release's `league/ci.py` lists as `FORBIDDEN` (the constitution, the ledger, the book, the
   evaluator, the auditor, this file, the watchdog, ci.py itself, the campaign and live-money
   files, the horizon rule's answer `resolution.py`...) or whose `.github/workflows/` differ from
   `TRUSTED_WORKFLOWS_SHA256` is refused. Those files decide what "passed" means -- the workflow
   file decides what the attestation above even attests -- so a commit that changes them reaches
   the box only as the owner's own deploy (`scripts/floor_box.py deploy`), never through the gate
   it would loosen.
3. **The trusted content checks.** The RUNNING release's copy of `league/ci.py` (strategies and
   tools pass the safety check and replay without error, `game.json` is inside its bounds,
   `config.json` moved only its operating dials from the release it replaces) is run against the
   candidate tree, from the running release's directory, as its own process, with a scrubbed
   environment and a verdict line keyed by a nonce the judged code never sees.
4. **`real_money` may not change by this path.** Turning real money on is the owner's deploy from
   his own machine, never something `main` does to the box by itself.
5. **The release train** (H3 of the forward-first run, Sept 25, 2026). A head that passed the walls
   above waits, before the trusted content checks run, while any of three holds stands (`schedule`):
   - *the train*: one updater release every `release_train_hours` (config.json, default 4, bounds
     2-6 in `league/ci.py` `CONFIG_DIALS`), measured from the last updater release that restarted
     the House (its `promote` row in `deploys.jsonl`); a rolled-back attempt counts, a canary
     refusal (the House never restarted) does not;
   - *the US session*: no launch on a day the House's session calendar (`ltcm.data.
     us_equity_session`, the function `league/house.py` imports) calls a trading day, from 30
     minutes before 13:25Z to 20:05Z (the session's own open less five minutes to its close plus
     five when that is wider: 14:25-21:05Z in winter). The 30-minute lead is the deploy itself: the
     canary took 2.2-4.0 minutes from launch to restart on Sept 24-25, then the watch is ten
     minutes, and a rollback restarts the House again inside it;
   - *a recent start*: none within 30 minutes of the ledger's last `ops.started`, read read-only.
   Measured: the House restarted 26 times in the 24 hours to 04:23Z Sept 25 (24-37 a day Sept
   20-24), seven of them inside the Sept 24 US session, and every restart kills the research and
   wakes in flight. The updater shipped at 21:16, 22:21, 23:00, 23:39, 00:38 and 01:14Z, 35 to 65
   minutes apart. A hold is `held` with its reasons and the next eligible time, written to
   `deploys.jsonl` and the ledger once per head per reason, never every look. A rolled-back head
   is not retired: it may be retried once, at the next train; a second rollback retires it.

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
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

# The House's own session calendar: `league/house.py` imports this function (`_session_open`,
# `session_time`) and `market_open_at` built on it (`_shut_session`). The holiday list lives there once.
from ltcm.data import DataError, to_datetime, us_equity_session

from .watchdog import Releases, _ledger_ro, epoch, iso, tree_digest

REPO = "bwoods1998/long-term-capital-management"
TREES = ("league", "ltcm", "playbooks", "scripts", "deploy")  # what scripts/floor_box.py sends too
MAX_TARBALL_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
SHA = re.compile(r"^[0-9a-f]{40}$")

#: The jobs of `.github/workflows/checks.yml` that must all have succeeded on the exact commit.
#: `league/tests/test_updater.py` holds this list to the workflow file.
REQUIRED_CHECKS = ("gateway", "tests (3.11)", "tests (3.14)")
#: The workflow whose runs attest a commit, and the events on main that may start one. A pull
#: request's run tests a merge preview, not the commit on main; a `pull_request_target` run is the
#: Merton judge, which never runs the suite.
CHECKS_WORKFLOW = ".github/workflows/checks.yml"
ATTESTING_EVENTS = ("push", "workflow_dispatch", "schedule")
FAILED = ("failure", "timed_out", "action_required", "startup_failure", "stale")
#: sha256 over every file under `.github/workflows/` (see `workflows_digest`). The workflows decide
#: what a green check run means, so a candidate that changes them is refused here and reaches the
#: box only as the owner's deploy. The test suite fails on GitHub when this pin and the files
#: disagree, so a workflow edit that forgets the pin cannot pass its own checks either.
TRUSTED_WORKFLOWS_SHA256 = "41a12b3a08a2d4388b01b3e28bc364b762f2668665b3438a286643759365ac00"
#: How long main's head may sit with no completed required checks before the owner is told.
PENDING_ALERT_SECONDS = 2 * 3600
EGRESS_HINT = ("api.github.com is not on the box's egress allowlist; the owner adds it with "
               "`python3 scripts/floor_box.py hosts --add api.github.com`")

#: The release train (wall 5 above). The hours are the running release's `league/config.json`
#: `release_train_hours`, held inside the bounds `league/ci.py` `CONFIG_DIALS` gives it; this is
#: only the value when the key is absent.
RELEASE_TRAIN_HOURS = 4.0
RELEASE_TRAIN_KEY = "release_train_hours"
#: No updater release within this long of the House's last `ops.started`.
RESTART_QUIET_SECONDS = 30 * 60
#: The no-release window of a trading day, in UTC: never narrower than 13:25-20:05Z (the EDT session
#: 13:30-20:00Z with five minutes each side), and the session's own open and close with the same
#: five minutes when that is wider (EST, 14:30-21:00Z).
SESSION_WINDOW_UTC = (clock_time(13, 25), clock_time(20, 5))
SESSION_PAD_SECONDS = 5 * 60
#: How long before the window a launch is already too late: the canary took 2.2-4.0 minutes from
#: launch to restart on Sept 24-25, 2026 (six updater deploys), the watch is ten minutes, and a
#: rollback restarts the House a second time inside it.
DEPLOY_LEAD_SECONDS = 30 * 60


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
def judge_workflow_runs(sha: str, data: Mapping[str, Any], jobs_of: Callable[[int], Mapping[str, Any]], *,
                        required: tuple[str, ...] = REQUIRED_CHECKS, workflow: str = CHECKS_WORKFLOW,
                        events: tuple[str, ...] = ATTESTING_EVENTS, branch: str = "main") -> dict[str, Any]:
    """GitHub's workflow runs for one commit -> `{"state": passed | pending | failed, "ok", ...}`.

    Counted: runs of `workflow` whose `head_sha` IS this sha, on `branch`, started by one of
    `events`. The newest counted run that finished with a verdict (success, or a failing
    conclusion; a cancelled or skipped run says nothing) decides, so a flaky failure that a re-run
    or the next scheduled run turns green does not block the commit for ever, and a later failure
    does block it. A run still going that is newer than that verdict is waited for. A successful
    deciding run's jobs (read with `jobs_of(run id)`) must include every required name, each
    completed with `success` on this sha. Pure apart from `jobs_of`, so the rule is testable alone."""
    runs = data.get("workflow_runs") if isinstance(data, Mapping) else None
    runs = [r for r in runs if isinstance(r, Mapping)] if isinstance(runs, list) else []
    counted = [r for r in runs if r.get("head_sha") == sha and r.get("path") == workflow
               and r.get("event") in events and r.get("head_branch") == branch]
    base = {"sha": sha, "required": list(required), "workflow": workflow, "ignored_runs": len(runs) - len(counted),
            "source": "api.github.com actions runs"}
    def order(r: Mapping[str, Any]) -> tuple[int, int]:
        return int(r.get("id") or 0), int(r.get("run_attempt") or 0)

    decided = [r for r in counted if r.get("status") == "completed" and (r.get("conclusion") == "success" or r.get("conclusion") in FAILED)]
    going = [r for r in counted if r.get("status") != "completed"]
    newest = max(decided, key=order) if decided else None
    if newest is None or (going and order(max(going, key=order)) > order(newest)):
        why = (f"{workflow} is {max(going, key=order).get('status')} on {sha[:12]}" if going
               else f"no completed run of {workflow} on {sha[:12]} yet")
        return {**base, "state": "pending", "ok": False, "checks": [], "reasons": [why]}
    if newest.get("conclusion") != "success":
        return {**base, "state": "failed", "ok": False, "checks": [], "run": _run_row(newest),
                "reasons": [f"{workflow} concluded {newest.get('conclusion')!r} on {sha[:12]} ({newest.get('event')} run {newest.get('id')})"]}
    run = newest
    listed = jobs_of(int(run.get("id") or 0))
    jobs = listed.get("jobs") if isinstance(listed, Mapping) else None
    jobs = [j for j in jobs if isinstance(j, Mapping)] if isinstance(jobs, list) else []
    checks, reasons, state = [], [], "passed"
    for name in required:
        mine = [j for j in jobs if j.get("name") == name and j.get("head_sha") == sha]
        if not mine:
            reasons.append(f"run {run.get('id')} of {workflow} has no job named {name!r}")
            state = "failed"
            continue
        job = max(mine, key=lambda j: int(j.get("id") or 0))
        checks.append({"name": name, "id": job.get("id"), "status": job.get("status"), "conclusion": job.get("conclusion"),
                       "completed_at": job.get("completed_at"), "url": job.get("html_url")})
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            reasons.append(f"job {name!r} is {job.get('status')}/{job.get('conclusion')} on {sha[:12]}")
            state = "failed"
    return {**base, "state": state, "ok": state == "passed", "checks": checks, "run": _run_row(run), "reasons": reasons}


def _run_row(run: Mapping[str, Any]) -> dict[str, Any]:
    return {k: run.get(k) for k in ("id", "event", "path", "head_branch", "status", "conclusion", "run_attempt", "html_url", "updated_at")}


class GitHubChecks:
    """The production attestor: `(sha) -> attestation`, unauthenticated, from api.github.com.

    Two requests per new tree (the commit's workflow runs, then the jobs of the one that decides),
    at most every half hour, against an unauthenticated limit of 60 an hour per address. A
    refusal, a rate limit, an unreachable host or an unreadable answer is `unavailable`, and
    unavailable deploys nothing."""

    def __init__(self, repo: str = REPO, *, opener: Any = None, timeout: float = 30.0, api: str = "https://api.github.com",
                 required: tuple[str, ...] = REQUIRED_CHECKS):
        self.repo, self.opener, self.timeout, self.api = repo, opener, timeout, api.rstrip("/")
        self.required = tuple(required)

    def _get(self, path: str) -> Any:
        request = urllib.request.Request(f"{self.api}/repos/{self.repo}/{path}",
                                         headers={"Accept": "application/vnd.github+json", "User-Agent": "ltcm-floor/1.0",
                                                  "X-GitHub-Api-Version": "2022-11-28"})
        return json.loads(_open(self.opener, request, self.timeout, 4 * 1024 * 1024).decode("utf-8"))

    def __call__(self, sha: str) -> dict[str, Any]:
        try:
            runs = self._get(f"actions/runs?head_sha={sha}&per_page=100")
            return judge_workflow_runs(sha, runs, lambda run_id: self._get(f"actions/runs/{int(run_id)}/jobs?per_page=100"),
                                       required=self.required)
        except urllib.error.HTTPError as exc:
            limited = exc.headers.get("X-RateLimit-Remaining") == "0" if exc.headers else False
            return unavailable(sha, f"api.github.com answered HTTP {exc.code}" + (" (the hourly rate limit is spent)" if limited else ""))
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            hint = f": {EGRESS_HINT}" if "name resolution" in reason or "Name or service" in reason or "nodename" in reason else ""
            return unavailable(sha, f"api.github.com could not be reached ({reason[:160]}){hint}")
        except (OSError, ValueError, TypeError, UpdateError) as exc:
            return unavailable(sha, f"api.github.com gave no readable answer ({type(exc).__name__}: {str(exc)[:160]})")


def unavailable(sha: str | None, reason: str) -> dict[str, Any]:
    return {"sha": sha, "state": "unavailable", "ok": False, "checks": [], "required": list(REQUIRED_CHECKS),
            "reasons": [reason], "source": "api.github.com actions runs"}


# ---------------------------------------------------------------------------- the release train
def _stamp(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_ts(row: Mapping[str, Any]) -> float | None:
    ts = row.get("ts")
    return float(ts) if isinstance(ts, (int, float)) else epoch(row.get("at"))


def train_hours(trusted: str | Path | None = None) -> float:
    """`release_train_hours` of the running release's `league/config.json`, inside the bounds the
    running `league/ci.py` gives it (`CONFIG_DIALS`: the same number the operator's checker holds a
    pull request to). Absent, unreadable or not a number: `RELEASE_TRAIN_HOURS`."""
    from .ci import CONFIG_DIALS

    low, high = CONFIG_DIALS.get(RELEASE_TRAIN_KEY, (2.0, 6.0))
    root = Path(trusted) if trusted else Path(__file__).resolve().parents[1]
    try:
        value = float(json.loads((root / "league" / "config.json").read_text(encoding="utf-8")).get(RELEASE_TRAIN_KEY, RELEASE_TRAIN_HOURS))
    except (OSError, ValueError, TypeError, AttributeError):
        value = RELEASE_TRAIN_HOURS
    if value != value:  # NaN
        value = RELEASE_TRAIN_HOURS
    return min(float(high), max(float(low), value))


def updater_ships(history: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The updater's deploys that restarted the House, oldest first, from `deploys.jsonl`.

    An updater deploy is one whose rows carry the attested `sha` (the watchdog writes it into every
    row of an attested deploy; the owner's `floor_box.py` deploy has none). It restarted the House at
    its `promote` row, whatever its verdict: a rolled-back attempt restarted it twice. One with no
    verdict yet is in flight and counts from its `start`. One refused before promotion (the canary)
    never restarted anything and does not count."""
    deploys: dict[str, dict[str, Any]] = {}
    for row in history:
        key, sha = row.get("deploy"), row.get("sha")
        if not key or not sha:
            continue
        seen = deploys.setdefault(str(key), {"deploy": str(key), "release": row.get("release"), "sha": sha})
        stage, ts = row.get("stage"), _row_ts(row)
        if stage == "start":
            seen["started_ts"] = ts
        elif stage == "promote" and row.get("ok"):
            seen["promoted_ts"] = ts
        elif stage == "verdict":
            seen["verdict"] = row.get("verdict")
    ships = []
    for seen in deploys.values():
        at = seen.get("promoted_ts")
        if at is None and seen.get("verdict") is None:
            at = seen.get("started_ts")
        if at is not None:
            ships.append({**seen, "ts": at, "at": _stamp(at), "verdict": seen.get("verdict") or "in flight"})
    return sorted(ships, key=lambda s: s["ts"])


def last_start(state_dir: str | Path) -> tuple[float | None, str | None]:
    """(epoch, problem) of the ledger's last `ops.started`, read through a connection that cannot
    write (the watchdog's). No ledger: (None, None). A ledger that cannot be read is `problem`."""
    path = Path(state_dir) / "ledger.sqlite"
    if not path.exists():
        return None, None
    try:
        with _ledger_ro(path) as db:
            row = db.execute("SELECT at FROM ledger WHERE kind = 'ops.started' ORDER BY seq DESC LIMIT 1").fetchone()
    except sqlite3.Error as exc:
        return None, f"the ledger could not be read ({type(exc).__name__}: {str(exc)[:120]})"
    return (epoch(row[0]) if row else None), None


def session_window(moment: float) -> dict[str, Any] | None:
    """The no-release window of `moment`'s UTC day, or None on a day the House's calendar calls
    closed (a weekend, an NYSE holiday). The window lies inside one UTC day, 12:55Z at its earliest
    with the lead to 21:05Z at its latest, where New York's date is the same day."""
    day = datetime.fromtimestamp(float(moment), tz=timezone.utc).date()
    floor_open = datetime.combine(day, SESSION_WINDOW_UTC[0], timezone.utc).timestamp()
    floor_close = datetime.combine(day, SESSION_WINDOW_UTC[1], timezone.utc).timestamp()
    try:
        session = us_equity_session(day)
    except DataError:
        # A year outside the computed calendar: every weekday is a trading day, at winter's hours.
        if day.weekday() >= 5:
            return None
        return {"day": day.isoformat(), "session": "outside the computed calendar", "opens": floor_open,
                "closes": floor_close + 3600, "starts": floor_open - DEPLOY_LEAD_SECONDS}
    if session is None:
        return None
    opened, closed = to_datetime(session.open_at).timestamp(), to_datetime(session.close_at).timestamp()
    opens = min(floor_open, opened - SESSION_PAD_SECONDS)
    closes = max(floor_close, closed + SESSION_PAD_SECONDS)
    return {"day": day.isoformat(), "session": f"{_stamp(opened)[11:16]}-{_stamp(closed)[11:16]}Z" + (" (an early close)" if session.early_close else ""),
            "opens": opens, "closes": closes, "starts": opens - DEPLOY_LEAD_SECONDS}


def schedule(base: str | Path, now: float, *, history: list[Mapping[str, Any]] | None = None, hours: float | None = None,
             trusted: str | Path | None = None) -> dict[str, Any]:
    """What holds an updater release at `now`, and when the next one may go. Read-only: the deploy
    record and the ledger are read, nothing is written, so `scripts/floor_watch.py` asks the very
    same question on the box. `holds` is empty when a head may ship now; each hold names its kind
    (`train`, `session`, `recent_start`), the moment it lifts and why, in the owner's words."""
    base = Path(base)
    rows = list(history) if history is not None else Releases(base).history()
    hours = float(hours) if hours is not None else train_hours(trusted)
    holds: list[dict[str, Any]] = []
    ships = updater_ships(rows)
    last = ships[-1] if ships else None
    if last is not None and now < last["ts"] + hours * 3600:
        until = last["ts"] + hours * 3600
        holds.append({"hold": "train", "until": _stamp(until), "until_ts": until,
                      "why": (f"the release train: the last updater release, {last.get('release')} ({last['verdict']}), restarted the "
                              f"House at {last['at']}; one updater release every {hours:g} h, so the next at {_stamp(until)}")})
    started, problem = last_start(base / "state")
    if problem is not None:
        started = now  # a ledger that cannot be read is no evidence of quiet: wait as if the House just started
    if started is not None and now < started + RESTART_QUIET_SECONDS:
        until = started + RESTART_QUIET_SECONDS
        holds.append({"hold": "recent_start", "until": _stamp(until), "until_ts": until,
                      "why": (problem or f"the House started at {_stamp(started)}")
                             + f"; no updater release within {RESTART_QUIET_SECONDS // 60} minutes of a start, so not before {_stamp(until)}"})
    window = session_window(now)
    if window is not None and window["starts"] <= now < window["closes"]:
        holds.append({"hold": "session", "until": _stamp(window["closes"]), "until_ts": window["closes"],
                      "why": (f"the US session: {window['day']} is a trading day on the House's calendar (the session {window['session']}); "
                              f"no updater release from {_stamp(window['starts'])} to {_stamp(window['closes'])}: the window opens at "
                              f"{_stamp(window['opens'])[11:16]}Z, and a release's canary, promotion and ten-minute watch take up to "
                              f"{DEPLOY_LEAD_SECONDS // 60} minutes")})
    # The earliest moment no hold stands: past the train and the quiet, then out of any session window
    # that moment falls in (a window's end is never inside the next day's).
    moment = max([now] + [h["until_ts"] for h in holds if h["hold"] != "session"])
    for _ in range(4):
        inside = session_window(moment)
        if inside is None or not inside["starts"] <= moment < inside["closes"]:
            break
        moment = inside["closes"]
    return {"at": _stamp(now), "train_hours": hours, "holds": holds, "next_eligible_ts": moment, "next_eligible_at": _stamp(moment),
            "last_ship": {k: last.get(k) for k in ("release", "sha", "at", "verdict")} if last else None,
            "last_start_at": _stamp(started) if started is not None and problem is None else None}


# ---------------------------------------------------------------------------------- updater
class Updater:
    def __init__(self, base: str | Path = "/workspace", *, repo: str = REPO, fetch: Callable[[str], bytes] | None = None,
                 launch: Callable[..., None] | None = None, clock: Callable[[], float] = time.time, every_seconds: int = 1800,
                 judge: Callable[[Path, Path], list[str]] | None = None, head: Callable[[], str] | None = None,
                 attest: Callable[[str], Mapping[str, Any]] | None = None, trusted: str | Path | None = None,
                 workflows_pin: str = TRUSTED_WORKFLOWS_SHA256, hours: float | None = None):
        self.base = Path(base)
        self.releases = Releases(self.base, clock=clock)  # its rows are dated by the clock the train is measured on
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
        #: The train's hours; None reads the running release's config.json at every look (`train_hours`).
        self.hours = hours
        self._last = 0.0
        #: When the last hold lifts: the next look is then, not up to half an hour later.
        self._wake_at: float | None = None
        self._told: set[tuple[str, str]] = set()
        self._pending_since: dict[str, float] = {}

    def due(self) -> bool:
        now = self.clock()
        if now - self._last >= self.every:
            return True
        return self._wake_at is not None and self._last < self._wake_at <= now

    def schedule(self, history: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        """The release train's holds now (module `schedule`), from this release's own dial."""
        return schedule(self.base, self.clock(), history=history, hours=self.hours, trusted=self.trusted)

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
        for workflows that are not part of the tree, or one the release train held. Those verdicts
        belong to a commit or a moment, and the same tree must still be deployable later.

        Nor, once, is a release whose only verdict is one rollback (the release train, Sept 25,
        2026): it is tried again at the next train, which its own restart holds off for
        `release_train_hours`. On Sept 24-25 five updater releases in a row (22:21Z to 01:14Z) were
        rolled back by Sail's checkpoint outage, not by anything in them, the two heads carrying the
        backup fix (#289) among them. A second rollback, or a refusal, retires it for good."""
        judged: set[str] = set()
        verdicts: dict[str, list[str]] = {}
        starts: dict[str, int] = {}
        for row in self.releases.history():
            release = row.get("release")
            if not release or row.get("busy") or row.get("unjudged"):
                continue
            release = str(release)
            judged.add(release)
            if row.get("stage") == "verdict":
                verdicts.setdefault(release, []).append(str(row.get("verdict")))
            elif row.get("stage") == "start":
                starts[release] = starts.get(release, 0) + 1
        again = {r for r in judged if verdicts.get(r) == ["rolled_back"] and starts.get(r, 0) <= 1}
        return judged - again

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
        time a refusal or a block is seen for this commit, which is when the House says so.
        `held` is a head the release train keeps back: `holds` names why (train, session,
        recent_start), `reasons` says it with the next eligible time, `next_eligible_at` is when."""
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
        problems = self.walls(incoming, running)
        if problems:
            _remove(incoming)
            return self._refused(release_id, sha, attestation, problems)
        # 5. The release train: a head that may ship waits for its moment. Before the trusted content
        #    checks, which replay every strategy on the box's one vCPU: a held head is judged once, when
        #    it goes, not at every look.
        history = self.releases.history()
        plan = self.schedule(history)
        if plan["holds"]:
            _remove(incoming)
            return self._held(release_id, sha, plan, history)
        self._wake_at = None
        problems = list(self.judge(incoming, running))
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

    def _held(self, release_id: str, sha: str, plan: Mapping[str, Any], history: list[Mapping[str, Any]]) -> dict[str, Any]:
        """A head that may ship, held by the release train. `new` (the House's cue for one
        `ops.deploy` row) is True only for a hold not yet recorded for this head, read from
        `deploys.jsonl` so a restart does not repeat it: at most one row per head per reason."""
        holds = [str(h["hold"]) for h in plan["holds"]]
        reasons = [str(h["why"]) for h in plan["holds"]] + [f"next eligible {plan['next_eligible_at']}"]
        told = {(row.get("sha"), hold) for row in history if row.get("stage") == "train" for hold in row.get("holds") or []}
        new = any((sha, hold) not in told for hold in holds)
        if new:
            self.releases.record({"release": release_id, "stage": "train", "verdict": "held", "unjudged": True, "sha": sha,
                                  "holds": holds, "reasons": reasons, "next_eligible_at": plan["next_eligible_at"]})
        self._wake_at = float(plan["next_eligible_ts"])
        return {"action": "held", "release": release_id, "sha": sha, "holds": holds, "reasons": reasons,
                "next_eligible_at": plan["next_eligible_at"], "schedule": dict(plan), "new": new}

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
        problems = self.walls(incoming, running)
        if problems:
            return problems  # a candidate that edits its judges is not run through them
        return list(self.judge(incoming, running))

    def walls(self, incoming: Path, running: Path) -> list[str]:
        """The real-money switch and the judges' files: what refuses a candidate before any of its
        code is run, and whatever the release train says (a protected head is refused at once)."""
        problems = []
        try:
            new = json.loads((incoming / "league" / "config.json").read_text(encoding="utf-8"))
            old = json.loads((running / "league" / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"league/config.json cannot be read: {exc}"]
        if bool(new.get("real_money")) != bool(old.get("real_money")):
            problems.append("league/config.json changes real_money: that switch is the owner's own deploy, never an automatic update")
        return problems + protected_changes(incoming, running)

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
