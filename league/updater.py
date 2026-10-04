"""How merged code reaches the House with no human step -- and why the code it brings cannot be
the judge that lets it in.

ON again since V3-A (Oct 2026): `"auto_update": true` in `league/config.json` (a missing key is off, `league/service.py`
`auto_update`; it was off from the options overhaul of Sept 26, 2026, when every release was an owner deploy). The owner's
own deploy (`scripts/floor_box.py deploy`) remains the only way the files below the walls change.

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
     us_equity_session`, the function `league/house.py` imports) calls a trading day, during the
     session or in the owner's 90-minute preopen exclusion. The existing conservative floor and
     five-minute padding stay: the hold begins at 11:55Z and ends at 20:05Z, or five minutes after
     the calendar's close when later (21:05Z in winter);
   - *a recent start*: none within 30 minutes of the ledger's last `ops.started`, read read-only.
   Measured: the House restarted 26 times in the 24 hours to 04:23Z Sept 25 (24-37 a day Sept
   20-24), seven of them inside the Sept 24 US session, and every restart kills the research and
   wakes in flight. The updater shipped at 21:16, 22:21, 23:00, 23:39, 00:38 and 01:14Z, 35 to 65
   minutes apart. A hold is `held` with its reasons and the next eligible time, written to
   `deploys.jsonl` and the ledger once per head per reason, never every look. A rolled-back head
   is not retired: it may be retried once, at the next train; a second rollback retires it.

Then the launch (V3-A). No other deploy may be in flight (`deploy.pid` or the watchdog's lock names
a live watchdog: a held head, tried at the next look). The nightly forward daemon is stopped first,
as the owner's release procedure does by hand: `<state>/data/nightly.stop` is written with the marker
`updater:<release-id>` (an operator's own stop is left as it is and obeyed) once the daemon is idle
with its next job at least two minutes off (`league/watchdog.py` `nightly_busy`: the House's
supervisor kills a stopped daemon two minutes on, busy or not), and the launch waits, look by look
and never inside one, until the daemon lets go of `nightly.lock`, at most `NIGHTLY_WAIT_SECONDS`
in all; past that the head is held, its stop lifted, and tried again at the next look. When the
daemon has kept every updater release out for `NIGHTLY_FORCE_AFTER_SECONDS` (never once seen idle by
a launch in that time), the stop is written over a busy daemon and the House warns: a night that never goes idle,
or a heartbeat this release cannot read, must not keep out the release that fixes it. The release
train and the deploys in flight are asked again at the moment of launch. The watchdog runs detached with a
scrubbed environment (`watchdog_environment`: no secret, only the path to the file that holds them,
as the owner's deploy launches it) and its pid goes into `<base>/deploy.pid`, where
`scripts/floor_box.py deploy` sees it and refuses to send a second release. Once no deploy is in
flight any more (the verdict is in: promoted, rolled back, refused or failed), the stop is removed
if it still carries the marker; a House that starts and finds an `updater:` stop with no deploy in
flight removes it the same way, so a crash never leaves the daemon stopped. The trees the updater
and the drill leave in `incoming/` are removed once nothing is in flight (`INCOMING_STALE_SECONDS`).

Then the watchdog's canary, promotion, watch and rollback, exactly as before. The attestation
travels with the release: into the watchdog's deploy record (`deploys.jsonl`, whose every row of
this deploy then carries the sha) and onto the ledger (`ops.deploy`), and the watchdog refuses to
stage a tree whose digest is not the attested one.

A release that is a rollback drill's copy (`league/watchdog.py` `drill_marker`: `DRILL_BREAK` in a
`drill-...` release) never looks at main: every look is the drill's deliberate break, which
`House._update` raises as an error alert so the watch rolls the copy back. If the drill's own process
is gone (no deploy in flight) for `DRILL_ORPHAN_SECONDS`, nothing will: that House launches `python -m
league.watchdog drill-recover`, detached, which rolls the copy back and lifts the drill's stop.
The drill itself is launched here too: the House's monthly `drills` job (league/ops/drills.py) only
writes `<state>/ops/drill-request.json` (`DRILL_REQUEST`), and a full look with nothing in flight
launches `python -m league.watchdog drill-rollback` detached from the House's own process, never from
the job's child, whose nice 19 and CPU and memory limits the watchdog and its canary would inherit.

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
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, time as clock_time, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

# The House's own session calendar: `league/house.py` imports this function (`_session_open`,
# `session_time`) and `market_open_at` built on it (`_shut_session`). The holiday list lives there once.
from ltcm.data import DataError, to_datetime, us_equity_session

from .watchdog import (DRILL_DETACHED_FLAG, DRILL_PREFIX, NIGHTLY_MARKERS, NIGHTLY_STOP, NIGHTLY_WAIT_SECONDS, Releases, _ledger_ro,
                       deploy_in_flight, drill_marker, epoch, iso,
                       nightly_busy as _nightly_busy, nightly_lock_held, nightly_marker, stop_nightly, tree_digest, unstop_nightly, write_pid)

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
TRUSTED_WORKFLOWS_SHA256 = "d18239dccc55896f7f9878690da04df2351c5bbff349a45bbf17ed8652f0cb08"
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
#: The owner's minimum preopen exclusion. It precedes the padded session window, preserving the
#: existing conservative UTC floor and five-minute margin as well as the calendar's own hours.
DEPLOY_LEAD_SECONDS = 90 * 60
#: While a launch waits for the nightly daemon to stop, the next look comes this soon (the House's tick
#: is 30 s; the daemon polls its stop every 30 s).
NIGHTLY_POLL_SECONDS = 20
#: Between full looks, a nightly stop this updater's deploys wrote is looked at this often, so it is
#: lifted within about a minute of the verdict, not half an hour.
SETTLE_EVERY_SECONDS = 60
#: A `drill:` stop is the drill's own to lift (`league/watchdog.py` `drill_rollback`, in a `finally`);
#: one older than this with no deploy in flight is a drill that died, and is lifted here.
DRILL_STOP_STALE_SECONDS = 2 * 3600
#: A drill copy's House that has seen no deploy in flight for this long is one whose drill died after the
#: promotion (`league/watchdog.py` `drill_recover`). The drill holds `deploy.pid` from before its copy is
#: promoted to after its rollback's restart, so this is only the margin for that restart to land.
DRILL_ORPHAN_SECONDS = 15 * 60
#: A nightly daemon that every launch has found not stoppable for this long (never once idle when asked)
#: is stopped anyway, busy or not, with a House warning: a job it kills is retried by its controller.
NIGHTLY_FORCE_AFTER_SECONDS = 6 * 3600
#: What the updater and the drill leave in `incoming/` (`main-*`, `drill-*`, the attestation records)
#: is removed once no deploy is in flight and it is this old (its newest mtime or ctime).
INCOMING_STALE_SECONDS = 3600
INCOMING_OWNED = ("main-", DRILL_PREFIX)
#: The House's monthly `drills` job (league/ops/drills.py) asks for the rollback drill with this file, under
#: the House's state directory; the updater, in the House's own process, launches it detached (a job child
#: runs at nice 19 under CPU and memory limits that a watchdog and its canary would inherit, and the House's
#: next start kills a job child it finds). A request older than this is dropped unlaunched.
DRILL_REQUEST = Path("ops") / "drill-request.json"
DRILL_REQUEST_TTL_SECONDS = 6 * 3600


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


def _attempt_token(row: Mapping[str, Any]) -> str | None:
    value = row.get("attempt")
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) else None


def _timing_deferred(row: Mapping[str, Any]) -> bool:
    return (row.get("stage") == "verdict" and row.get("verdict") == "refused"
            and row.get("unjudged") is True and row.get("deferred") in ("session", "calendar"))


def updater_ships(history: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The updater's deploys that restarted the House, oldest first, from `deploys.jsonl`.

    An updater deploy is one whose rows carry the attested `sha` (the watchdog writes it into every
    row of an attested deploy; the owner's `floor_box.py` deploy has none). It restarted the House at
    its `promote` row, whatever its verdict: a rolled-back attempt restarted it twice. One with no
    verdict yet is in flight and counts from its `start`. One refused before promotion (the canary)
    never restarted anything and does not count."""
    deploys: dict[tuple[str, str], dict[str, Any]] = {}
    for row in history:
        key, sha = row.get("deploy"), row.get("sha")
        if not key or not sha:
            continue
        attempt = _attempt_token(row)
        grouped = ("attempt", attempt) if attempt else ("legacy", str(key))
        seen = deploys.setdefault(grouped, {"deploy": str(key), "release": row.get("release"), "sha": sha,
                                           **({"attempt": attempt} if attempt else {})})
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
    closed (a weekend, an NYSE holiday). The window lies inside one UTC day, 11:55Z at its earliest
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
                              f"no updater release from {_stamp(window['starts'])} to {_stamp(window['closes'])}: the owner's "
                              f"{DEPLOY_LEAD_SECONDS // 60}-minute preopen exclusion precedes the conservative padded window "
                              f"that opens at {_stamp(window['opens'])[11:16]}Z")})
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
                 workflows_pin: str = TRUSTED_WORKFLOWS_SHA256, hours: float | None = None,
                 in_flight: Callable[[], str | None] | None = None, nightly_held: Callable[[], bool] | None = None,
                 nightly_busy: Callable[[], str | None] | None = None, launch_watchdog: Callable[[list[str]], int] | None = None):
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
        #: Why a deploy is running under the base now, or None (`league/watchdog.py` `deploy_in_flight`).
        self.in_flight = in_flight or (lambda: deploy_in_flight(self.base))
        #: Does the nightly daemon still hold its lock (`league/watchdog.py` `nightly_lock_held`)?
        self.nightly_held = nightly_held or (lambda: nightly_lock_held(self.base))
        #: Why the nightly daemon may not be stopped now, or None (`league/watchdog.py` `nightly_busy`).
        self.nightly_busy = nightly_busy or (lambda: _nightly_busy(self.base, self.clock()))
        #: A head that passed every wall and waits for the nightly daemon to stop: launched at a later look.
        self._launching: dict[str, Any] | None = None
        #: Since when every launch has found the nightly daemon not stoppable (`NIGHTLY_FORCE_AFTER_SECONDS`);
        #: None once one finds it idle.
        self._nightly_busy_since: float | None = None
        #: `due` said yes only to look at a nightly stop this updater wrote: `check` does only that.
        self._light = False
        self._settle_next = 0.0
        #: The drill's deliberate break, read once when the House starts (`league/watchdog.py` `drill_marker`).
        self.drill = drill_marker(self.trusted)
        #: In a drill copy: since when no deploy has been in flight, and the recovery once launched.
        self._orphan_since: float | None = None
        self._recovery: dict[str, Any] | None = None
        #: The watchdogs this process started: polled so one that exits without restarting the House is
        #: reaped, not left a zombie whose pid in `deploy.pid` `floor_box.py` reads as a deploy running.
        self._children: list[subprocess.Popen] = []
        self._children_lock = threading.Lock()  # `due` runs on the tick, `check` (which spawns) on a background lane
        #: (candidate digest, running digest) the trusted checks passed in this process: a head held at
        #: the launch (a deploy in flight, the nightly daemon) is not judged again at the next look.
        self._judged: set[tuple[str, str]] = set()
        #: Starts `python -m league.watchdog <args>` detached (`_spawn`), its pid in `deploy.pid`; returns the pid.
        #: The monthly rollback drill's launch (`_drill_request`). Tests hand in a stub.
        self.launch_watchdog = launch_watchdog or (lambda args: self._spawn(args, "drill-request", fallback_cwd=self.trusted))

    def due(self) -> bool:
        now = self.clock()
        with self._children_lock:
            self._children = [child for child in self._children if child.poll() is None]
        if self.drill is not None:
            return True  # the drill's break is raised at every tick
        full = now - self._last >= self.every or (self._wake_at is not None and self._last < self._wake_at <= now)
        self._light = False
        if not full and self._launching is None and now >= self._settle_next:
            self._settle_next = now + SETTLE_EVERY_SECONDS
            marker = nightly_marker(self.base)
            self._light = bool(marker) and marker.startswith(NIGHTLY_MARKERS)
        return full or self._light

    def schedule(self, history: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
        """The release train's holds now (module `schedule`), from this release's own dial."""
        return schedule(self.base, self.clock(), history=history, hours=self.hours, trusted=self.trusted)

    def _launch(self, source: Path, release_id: str, attestation: Path | None = None) -> None:
        """Hand the tree to the watchdog, detached: the canary and the watch outlive this process,
        which the promotion itself will restart. The known-good release's watchdog does the judging.
        Its environment is scrubbed (`watchdog_environment`), and its pid goes into `<base>/deploy.pid`
        as `scripts/floor_box.py deploy` writes it, so the owner's deploy sees this one in flight."""
        argv = ["deploy", "--base", str(self.base), "--source", str(source), "--id", release_id]
        if attestation is not None:
            argv += ["--attestation", str(attestation)]
        self._spawn(argv, release_id, fallback_cwd=source)

    def _spawn(self, argv: list[str], release_id: str, *, fallback_cwd: Path | None = None) -> int:
        """`python -m league.watchdog <argv>` detached, from the current release, scrubbed, its pid in `deploy.pid`."""
        current = self.base / "current"
        cwd = current if current.exists() or fallback_cwd is None else fallback_cwd
        with open(self.base / "deploy.log", "ab") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "league.watchdog", *argv], cwd=str(cwd), stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                start_new_session=True, env=watchdog_environment(self.base),
            )
        with self._children_lock:
            self._children.append(process)
        try:
            write_pid(self.base / "deploy.pid", process.pid)
        except OSError as exc:  # the watchdog's own lock still keeps a second deploy out
            self.releases.record({"stage": "launch", "release": release_id, "unjudged": True, "pid": process.pid,
                                  "error": f"deploy.pid could not be written ({type(exc).__name__}: {str(exc)[:160]})"})
        return process.pid

    def _drill_request(self) -> dict[str, Any] | None:
        """The rollback drill the `drills` job asked for (`DRILL_REQUEST`): launched here, detached, once nothing is
        in flight; the drill refuses by itself what it must (the session window, a stopped House, auto_update off) and
        writes its `stage: "drill"` row either way. A request past `DRILL_REQUEST_TTL_SECONDS` is dropped.

        Launched with `DRILL_DETACHED_FLAG`: `_spawn` already gives it a session of its own and puts ITS pid in
        `deploy.pid`, which the drill ignores as its own. Without the flag the command would re-run itself as a child
        (`league/watchdog.py` `_drill_detached`), and that child would find this launch's pid in `deploy.pid` -- a live
        watchdog -- and refuse as a deploy in flight."""
        path = self.releases.state_dir / DRILL_REQUEST
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            request = {}
        now = self.clock()
        asked = epoch(request.get("at")) if isinstance(request, dict) else None
        if asked is None or not -300 <= now - asked <= DRILL_REQUEST_TTL_SECONDS:
            path.unlink(missing_ok=True)
            self.releases.record({"stage": "drill", "outcome": "dropped", "unjudged": True,
                                  "reasons": ["the drill request was unreadable or older than "
                                              f"{DRILL_REQUEST_TTL_SECONDS // 3600} h; nothing was launched"]})
            return {"drill_request": "dropped"}
        if self._launching is not None:
            return {"drill_request": "waiting", "why": "a release launch is pending"}
        why = self.in_flight()
        if why:
            return {"drill_request": "waiting", "why": why}
        path.unlink(missing_ok=True)
        try:
            pid = self.launch_watchdog(["drill-rollback", "--base", str(self.base), DRILL_DETACHED_FLAG])
        except Exception as exc:  # noqa: BLE001 - the drills job's next receipt reads the row
            self.releases.record({"stage": "drill", "outcome": "failed", "unjudged": True,
                                  "reasons": [f"the drill could not be launched ({type(exc).__name__}: {str(exc)[:200]})"]})
            return {"drill_request": "failed"}
        return {"drill_request": "launched", "pid": pid}

    def tried(self) -> set[str]:
        """The releases the watchdog has really judged. A row marked `busy` is not one of them: it
        means another deploy held the lock, so the code was never unpacked, let alone run. And the
        promotion's own restart makes that race the NORMAL case -- the House comes up, its updater
        checks on the first tick, and the previous deploy is still inside its ten-minute watch. A
        commit retired on one of those was retired for good, with no retry and no expiry, silently:
        a floor that rewrites itself would have dropped its own improvements one at a time.

        Nor is an attempt finally deferred by the watchdog's deployment timing check: its unique attempt token
        excludes only that attempt's rows, preserving any earlier real verdict for the same release.
        Nor is a row marked `unjudged`: a head not yet (or not) attested by GitHub, or one refused
        for workflows that are not part of the tree, or one the release train held. Those verdicts
        belong to a commit or a moment, and the same tree must still be deployable later.

        Nor, once, is a release whose only verdict is one rollback (the release train, Sept 25,
        2026): it is tried again at the next train, which its own restart holds off for
        `release_train_hours`. On Sept 24-25 five updater releases in a row (22:21Z to 01:14Z) were
        rolled back by Sail's checkpoint outage, not by anything in them, the two heads carrying the
        backup fix (#289) among them. A second rollback, or a refusal, retires it for good.

        Nor is a tree that was promoted and never rolled back from, while the box runs ANOTHER updater
        release (V3-A): main reverted to it (the engineer's revert of a bad change that passed its
        watch) and that revert is the way back. Not while the box runs the owner's release (main may
        lag what the owner deployed by hand), and not once anything rolled back from it."""
        judged: set[str] = set()
        verdicts: dict[str, list[str]] = {}
        starts: dict[str, int] = {}
        backed_out: set[str] = set()
        history = self.releases.history()
        attempts: dict[str, list[Mapping[str, Any]]] = {}
        for row in history:
            token = _attempt_token(row)
            if token is not None:
                attempts.setdefault(token, []).append(row)
        deferred_attempts = set()
        for token, rows in attempts.items():
            verdict_rows = [row for row in rows if row.get("stage") == "verdict"]
            if (verdict_rows and _timing_deferred(verdict_rows[-1])
                    and not any(row.get("stage") in ("promote", "rollback")
                                or (row.get("stage") == "verdict" and not _timing_deferred(row)) for row in rows)):
                deferred_attempts.add(token)
        for row in history:
            if _attempt_token(row) in deferred_attempts:
                continue
            if row.get("stage") == "rollback" and row.get("ok") is not False:
                backed_out.add(str(row.get("from") or row.get("release")))
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
        current = self.releases.current() or ""
        if current.startswith("main-"):
            again |= {r for r in judged if r != current and r.startswith("main-") and r not in backed_out
                      and verdicts.get(r) and set(verdicts[r]) == {"promoted"}}
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
        recent_start; at the launch, deploy and nightly), `reasons` says it with the next eligible
        time, `next_eligible_at` is when. `stopping_nightly` is a head that passed everything and
        waits, look by look, for the nightly daemon to stop before it launches. `drill` is this House
        running a rollback drill's copy: nothing else is done."""
        light, self._light = self._light, False
        if self.drill is not None:
            return self._drill_check()
        if self._launching is not None:
            self._last = self.clock()
            return self._continue_launch()
        resumed = self._settle_nightly()
        if light:
            return {"action": "none", "reason": "looked only at the nightly stop", **({"nightly_resumed": resumed} if resumed else {})}
        drill = self._drill_request()
        if drill is not None and drill.get("drill_request") == "launched":
            self._last = self.clock()
            return {"action": "drill_launched", "reason": "the monthly rollback drill was launched", "new": True,
                    "reasons": [f"the monthly rollback drill was launched (pid {drill['pid']}); it restarts the House twice"], **drill}
        self._last = self.clock()
        self._sweep_incoming()
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
        running_digest = tree_digest(running)[0]
        if digest == running_digest:
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
        # 6. The launch: no deploy beside another (asked before the judge, which is the costly part),
        #    then the trusted content checks once per tree, then the nightly daemon stopped first.
        why = self.in_flight()
        if why:
            _remove(incoming)
            return self._held(release_id, sha, self._hold("deploy", f"another deploy is in flight ({why}); tried again at the next look"), history)
        if (digest, running_digest) not in self._judged:
            problems = list(self.judge(incoming, running))
            if problems:
                _remove(incoming)
                return self._refused(release_id, sha, attestation, problems)
            self._judged.add((digest, running_digest))
        final = self.base / "incoming" / release_id
        _remove(final)
        incoming.rename(final)
        record = self.base / "incoming" / f"{release_id}.attestation.json"
        record.write_text(json.dumps(attestation, sort_keys=True, default=str), encoding="utf-8")
        self._launching = {"release": release_id, "sha": sha, "final": final, "record": record, "files": files, "attestation": attestation,
                           "marker": f"updater:{release_id}", "standing": None, "since": self.clock(), "told": False, "forced": None}
        return self._continue_launch()

    def _hold(self, kind: str, why: str, until: float | None = None) -> dict[str, Any]:
        """One hold of the launch, shaped as `schedule` shapes the train's (for `_held`): by default it
        lifts at the next ordinary look."""
        until = float(until if until is not None else self.clock() + self.every)
        return {"holds": [{"hold": kind, "until": _stamp(until), "until_ts": until, "why": why}],
                "next_eligible_at": _stamp(until), "next_eligible_ts": until}

    def _continue_launch(self) -> dict[str, Any]:
        """The launch of a head that passed every wall, once the nightly daemon has let go of its lock.
        Asked at this look and the ones after it (`NIGHTLY_POLL_SECONDS` apart), never by waiting
        inside one: the House's update job must not sit on a lane for ten minutes."""
        pending = self._launching
        assert pending is not None
        now = self.clock()
        release_id, sha, marker = pending["release"], pending["sha"], pending["marker"]
        waiting = None
        if pending["standing"] is None:
            waiting = self.nightly_busy()
            if waiting is None:
                self._nightly_busy_since = None
            else:
                self._nightly_busy_since = now if self._nightly_busy_since is None else self._nightly_busy_since
                if now - self._nightly_busy_since >= NIGHTLY_FORCE_AFTER_SECONDS:
                    pending["forced"], waiting = {"why": waiting, "since": self._nightly_busy_since}, None
            if waiting is None:
                try:
                    pending["standing"] = stop_nightly(self.base, marker)
                except OSError as exc:
                    self._drop_launch()
                    return self._held(release_id, sha, self._hold("nightly", f"the nightly stop could not be written ({type(exc).__name__}: "
                                                                             f"{str(exc)[:160]}); tried again at the next look"),
                                      self.releases.history())
        if pending["standing"] is not None and not self.nightly_held():
            # Asked again at the moment of launch: the session's lead or a start may have begun while
            # the daemon stopped, and another deploy may have begun beside this one.
            history = self.releases.history()
            plan = self.schedule(history)
            why = self.in_flight()
            if plan["holds"] or why:
                self._drop_launch()
                if not plan["holds"]:
                    plan = self._hold("deploy", f"another deploy is in flight ({why}); tried again at the next look")
                return self._held(release_id, sha, plan, history)
            self._launching = None
            self._wake_at = None
            self.launch(pending["final"], release_id, pending["record"])
            out = {"action": "deploying", "release": release_id, "files": pending["files"], "sha": sha, "attestation": pending["attestation"],
                   "nightly": {"stop": pending["standing"], "waited_seconds": round(now - pending["since"], 1)}}
            if pending.get("forced"):
                out["nightly"]["forced"] = pending["forced"]
                out["warn"] = (f"the nightly data job kept every updater release out since {_stamp(pending['forced']['since'])}, never "
                               f"once idle at a launch ({pending['forced']['why']}); its stop was written anyway so {release_id} could launch")
            return out
        if waiting is None:
            waiting = f"the nightly data job has not let go of its lock since the stop ({pending['standing'] or 'an operator stop'})"
        if now - pending["since"] >= NIGHTLY_WAIT_SECONDS:
            self._drop_launch()
            return self._held(release_id, sha, self._hold("nightly", (
                f"the nightly data job was not stopped within {NIGHTLY_WAIT_SECONDS // 60} minutes: {waiting}; a release change never "
                "lands mid-job, so tried again at the next look")), self.releases.history())
        self._wake_at = now + NIGHTLY_POLL_SECONDS
        new, pending["told"] = not pending["told"], True
        return {"action": "stopping_nightly", "release": release_id, "sha": sha, "new": new, "waited_seconds": round(now - pending["since"], 1),
                "reasons": [f"waiting for the nightly data job before {release_id} launches: {waiting}"]}

    def _drop_launch(self) -> None:
        """Give up a launch that has not happened: its stop lifted (only if still this updater's), its tree removed."""
        pending, self._launching = self._launching, None
        if pending is None:
            return
        unstop_nightly(self.base, pending["marker"])
        _remove(pending["final"])
        _remove(pending["record"])

    def _drill_check(self) -> dict[str, Any]:
        """A look from a drill copy: the deliberate break, and the way back if the drill is gone. The
        drill's own process holds `deploy.pid` until its rollback has restarted this House, so a copy
        that has seen no deploy in flight for `DRILL_ORPHAN_SECONDS` was left current by a drill that
        died: `drill-recover` is launched, once per process, as the updater launches a watchdog."""
        now = self._last = self.clock()
        reasons = [f"drill: deliberate break (this House runs {self.trusted.name}, a rollback drill's copy of "
                   f"{self.drill.get('copy_of') or 'the running release'}); the watch rolls it back"]
        out: dict[str, Any] = {"action": "drill", "release": self.trusted.name, "drill": dict(self.drill), "new": False, "reasons": reasons}
        if self.in_flight():
            self._orphan_since = None
        elif self._recovery is None:
            self._orphan_since = self._orphan_since if self._orphan_since is not None else now
            if now - self._orphan_since >= DRILL_ORPHAN_SECONDS:
                why = f"drill orphaned: no deploy in flight since {_stamp(self._orphan_since)}, and {self.trusted.name} is still running"
                try:
                    pid = self._spawn(["drill-recover", "--base", str(self.base), "--reason", why], self.trusted.name)
                    self._recovery = {"pid": pid, "at": _stamp(now)}
                except OSError as exc:
                    self._recovery = {"error": f"{type(exc).__name__}: {str(exc)[:160]}", "at": _stamp(now)}
                self.releases.record({"stage": "drill", "outcome": "orphaned", "release": self.trusted.name, "reasons": [why],
                                      "recovery": dict(self._recovery)})
                out["recovery"], out["new"] = dict(self._recovery), True
        if self._recovery is not None:
            reasons.append(f"the drill's process is gone; drill-recover launched at {self._recovery['at']}"
                           + (f" failed to start: {self._recovery['error']}" if "error" in self._recovery else f" (pid {self._recovery['pid']})"))
        # A stop automation wrote with nothing in flight (a `drill:` one only once it is stale) is lifted here too:
        # `drill-recover` lifts the drill's own, and this is the net under a recovery that could not start.
        resumed = self._settle_nightly()
        if resumed:
            out["nightly_resumed"] = resumed
        return out

    def _sweep_incoming(self, now: float | None = None) -> list[str]:
        """Remove the trees (and attestation records) the updater and the drill left in `incoming/`, once
        no deploy is in flight and none is waiting to launch: the watchdog stages a copy into
        `releases/`, so a tree here is spent after its verdict. The owner's own uploads (`floor_box.py`)
        are left alone. Age is the later of mtime and ctime: a copied tree keeps its source's mtime."""
        root = self.base / "incoming"
        if self._launching is not None or not root.is_dir() or self.in_flight():
            return []
        now = time.time() if now is None else now
        removed = []
        for entry in root.iterdir():
            if not entry.name.startswith(INCOMING_OWNED):
                continue
            try:
                stat = entry.lstat()
            except OSError:
                continue
            if now - max(stat.st_mtime, stat.st_ctime) >= INCOMING_STALE_SECONDS:
                _remove(entry)
                removed.append(entry.name)
        return removed

    def _settle_nightly(self) -> str | None:
        """Lift a nightly stop that automation wrote, once no deploy is in flight: the verdict of the
        deploy it was written for is in, or that deploy never began (a House that died while it waited
        for the daemon; the House's start reaches this at its first look). A `drill:` stop is the drill's
        to lift, and is lifted here only when it is `DRILL_STOP_STALE_SECONDS` old. An operator's stop is
        never lifted. Returns the marker lifted, or None."""
        marker = nightly_marker(self.base)
        if not marker or not marker.startswith(NIGHTLY_MARKERS):
            return None
        if self._launching is not None and self._launching["marker"] == marker:
            return None
        if marker.startswith("drill:"):
            try:
                age = time.time() - (self.base / NIGHTLY_STOP).stat().st_mtime
            except OSError:
                return None
            if age < DRILL_STOP_STALE_SECONDS:
                return None
        if self.in_flight():
            return None
        if not unstop_nightly(self.base, marker):
            return None
        self.releases.record({"stage": "nightly", "action": "resumed", "marker": marker, "unjudged": True})
        return marker

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
    (importing it executes no candidate code); the gateway's merge route refuses the same list and the House's
    configuration (`ci.MERGE_ONLY`, whose dials only the running release's checks let through here). Only the release
    trees are compared: `gateway/` and `.github/` never reach the box as files (the workflows are pinned by
    `TRUSTED_WORKFLOWS_SHA256`)."""
    from .ci import guard

    def files(root: Path) -> dict[str, Path]:
        out = {}
        for top in TREES:
            for path in (root / top).rglob("*") if (root / top).is_dir() else ():
                if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"):
                    out[path.relative_to(root).as_posix()] = path
        return out

    def guarded(name: str) -> bool:
        return bool(guard([name], None))

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


#: All the watchdog the updater launches may see of the House's environment (V3-A): what the trusted
#: checks keep, and where the TLS trust store is. The House's process holds its three secrets in its
#: environment (`service.load_env`); the watchdog needs none of them (it judges files, reads health and
#: runs `restart.sh`, which needs only PATH), and its canary House reads the secrets file named by
#: `LEAGUE_ENV`, exactly as when the owner's deploy launches the watchdog (`scripts/floor_box.py`
#: `watchdog_launch`: the exec's own environment plus `LEAGUE_ENV`).
WATCHDOG_ENV_KEEP = VET_ENV_KEEP + ("SSL_CERT_FILE", "SSL_CERT_DIR")


def watchdog_environment(base: str | Path) -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name in WATCHDOG_ENV_KEEP}
    env["LEAGUE_ENV"] = str(Path(base) / ".env")
    return env


def _remove(path: Path) -> None:
    import shutil

    if path.is_file() or path.is_symlink():
        path.unlink(missing_ok=True)
        return
    shutil.rmtree(path, ignore_errors=True)
