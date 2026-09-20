"""How merged code reaches the House with no human step.

GitHub is the source of truth. The repository is public, so the House box needs no credential to
read it: every half hour the House downloads `main` as a tarball, unpacks the trees a release is
made of, and compares the tree's digest with the release it is running. When they differ it
hands the new tree to the in-box watchdog (`league/watchdog.py`), which runs it as a canary,
promotes it, watches the House, and rolls back by itself if health degrades. A tree that was
refused or rolled back once is never tried again: only a new commit is.

Before the watchdog sees it, the CURRENT release's content checks (`league/ci.py`: strategies and
tools pass the safety check and replay without error, `game.json` is inside its bounds,
`config.json` moved only its operating dials) are run against the new tree, and one more rule is
applied that only matters here: **`real_money` may not change by this path**. Turning real money
on is the owner's deploy from his own machine, never something `main` does to the box by itself.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .watchdog import Releases, tree_digest

REPO = "bwoods1998/long-term-capital-management"
TREES = ("league", "ltcm", "playbooks", "scripts", "deploy")  # what scripts/floor_box.py sends too
MAX_TARBALL_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024


class UpdateError(RuntimeError):
    pass


def fetch_main(repo: str = REPO, *, opener: Any = None, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(f"https://codeload.github.com/{repo}/tar.gz/refs/heads/main", headers={"User-Agent": "ltcm-floor/1.0"})
    with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
        data = response.read(MAX_TARBALL_BYTES + 1)
    if len(data) > MAX_TARBALL_BYTES:
        raise UpdateError("the tarball is larger than a release can be")
    return data


def unpack(tarball: bytes, target: Path) -> int:
    """Write the release trees of a GitHub tarball under `target`. Regular files only, no links, no
    path that leaves the tree; modes are normalized the way `floor_box.py` writes them (0755 for a
    shell script, 0644 otherwise) so the same commit has the same digest whichever way it came."""
    count = 0
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        for member in archive:
            parts = Path(member.name).parts[1:]  # drop GitHub's "<repo>-main/" directory
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


class Updater:
    def __init__(self, base: str | Path = "/workspace", *, repo: str = REPO, fetch: Callable[[], bytes] | None = None,
                 launch: Callable[[Path, str], None] | None = None, clock: Callable[[], float] = time.time, every_seconds: int = 1800,
                 judge: Callable[[Path], list[str]] | None = None):
        self.base = Path(base)
        self.releases = Releases(self.base)
        self.fetch = fetch or (lambda: fetch_main(repo))
        self.launch = launch or self._launch
        #: (incoming tree) -> what refuses it. The incoming tree's OWN content checks, run as its
        #: own process, so a tree is judged by its own rules rather than by a judge one commit out
        #: of date. Tests hand in a stub; nothing else should.
        self.judge = judge or self._judged_by_itself
        self.clock = clock
        self.every = every_seconds
        self._last = 0.0

    def due(self) -> bool:
        return self.clock() - self._last >= self.every

    def _launch(self, source: Path, release_id: str) -> None:
        """Hand the tree to the watchdog, detached: the canary and the watch outlive this process,
        which the promotion itself will restart. The known-good release's watchdog does the judging."""
        current = self.base / "current"
        log = open(self.base / "deploy.log", "ab")
        subprocess.Popen(
            [sys.executable, "-m", "league.watchdog", "deploy", "--base", str(self.base), "--source", str(source), "--id", release_id],
            cwd=str(current if current.exists() else source), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "LEAGUE_ENV": str(self.base / ".env")},
        )

    def tried(self) -> set[str]:
        """The releases the watchdog has really judged. A row marked `busy` is not one of them: it
        means another deploy held the lock, so the code was never unpacked, let alone run. And the
        promotion's own restart makes that race the NORMAL case -- the House comes up, its updater
        checks on the first tick, and the previous deploy is still inside its ten-minute watch. A
        commit retired on one of those was retired for good, with no retry and no expiry, silently:
        a floor that rewrites itself would have dropped its own improvements one at a time."""
        return {str(row["release"]) for row in self.releases.history() if row.get("release") and not row.get("busy")}

    def check(self) -> dict[str, Any]:
        """One look at main. Returns what was found and what was done."""
        self._last = self.clock()
        current = self.releases.current()
        if current is None:
            return {"action": "none", "reason": "there is no current release to compare with"}
        running = self.base / "releases" / current
        incoming = self.base / "incoming" / f"main-{int(self.clock())}"
        unpack(self.fetch(), incoming)
        digest, files = tree_digest(incoming)
        if digest == tree_digest(running)[0]:
            _remove(incoming)
            return {"action": "none", "reason": "the box already runs main", "digest": digest[:12]}
        release_id = f"main-{digest[:12]}"
        if release_id in self.tried():
            _remove(incoming)
            return {"action": "none", "reason": f"{release_id} was already tried; only a new commit is tried again", "digest": digest[:12]}
        problems = self.vet(incoming, running)
        if problems:
            _remove(incoming)
            self.releases.record({"release": release_id, "stage": "vet", "verdict": "refused", "reasons": problems[:10]})
            return {"action": "refused", "release": release_id, "reasons": problems}
        final = self.base / "incoming" / release_id
        _remove(final)
        incoming.rename(final)
        self.launch(final, release_id)
        return {"action": "deploying", "release": release_id, "files": files}

    def vet(self, incoming: Path, running: Path) -> list[str]:
        """The content checks, applied to the new tree -- by the NEW tree's own judge.

        This used to import the RUNNING release's `ci`, which judged the incoming tree by rules one
        commit out of date. GitHub judges a branch with the branch's own `ci.py`, so the two
        disagreed by exactly one commit, and a change that widens a bound and uses the wider value
        in the same commit passed there and was refused here -- for ever, because git main is
        cumulative, so the offending file stays in every later tree and the refusal repeats. It
        happened to this repository on Sept 20, 2026 (`inference_daily_cap_usd`), and it would have
        stopped the box taking any update at all, with no alert anywhere.

        What the new tree may not decide for itself stays here, in code the incoming tree cannot
        touch: the real-money switch is the owner's own deploy and no automatic update may flip it.
        The branch's judge is the second wall, not the only one -- GitHub has already run the same
        checks on the same tree before it reached main."""
        problems = []
        try:
            new = json.loads((incoming / "league" / "config.json").read_text(encoding="utf-8"))
            old = json.loads((running / "league" / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [f"league/config.json cannot be read: {exc}"]
        if bool(new.get("real_money")) != bool(old.get("real_money")):
            problems.append("league/config.json changes real_money: that switch is the owner's own deploy, never an automatic update")
        return problems + list(self.judge(incoming))

    @staticmethod
    def _judged_by_itself(incoming: Path) -> list[str]:
        """The incoming tree's own content checks, run inside that tree as its own process.

        A subprocess, not an import: `league/ci.py` reaches the rest of its package by relative
        import, so it can only judge the tree it lives in. This is what GitHub already does to the
        same commit, which is the point -- the two judges must not disagree."""
        if not (incoming / "league" / "ci.py").exists():
            return ["the incoming tree has no league/ci.py to judge itself with"]
        try:
            done = subprocess.run([sys.executable, "-m", "league.ci", "--content-only"], cwd=str(incoming),
                                  capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            return [f"the incoming tree's own checks could not be run: {type(exc).__name__}: {str(exc)[:200]}"]
        if done.returncode == 0:
            return []
        refused = [line[len("REFUSED: "):] for line in done.stdout.splitlines() if line.startswith("REFUSED: ")]
        return refused or [f"the incoming tree's own checks refused it (exit {done.returncode}): {(done.stderr or done.stdout)[-300:]}"]


def _remove(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
