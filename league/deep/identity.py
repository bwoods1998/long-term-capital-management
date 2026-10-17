"""THE DEEP IDENTITY: what an S3 verdict binds to (league/xs/identity.py's pattern; R1 moves no other identity).

Owner: R1. `deep_fingerprint` is the sha256, path and bytes in path order, over: league/deep/<name>.py for
`DEEP_EVIDENCE`, the two date fixtures (`DEEP_DATA`: the calendar and the mask a look reads), and every file the
equity identity reads (league/equity/<name>.py for `EQUITY_EVIDENCE`, `EQUITY_GYM_FILES`, `EQUITY_CALENDAR_FILES`,
spelled out here as league/swarm/evaluator.py spells them: a test holds the lists equal) together with the options
fingerprint's four `LEAGUE_FILES` (league/gym/driver.py). The deep key runs the equity engine, so a change there moves
the deep identity too; a change here moves NEITHER the equity identity NOR the options execution fingerprint
(nothing of league/deep is in their files, and neither tree imports league/deep: league/tests/test_deep_identity.py).

PLUMBING IS OUT: `report` and this file. Every ledger row carries `deep_fingerprint()[:12]` beside the engine
version, so a verdict earned under another deep identity is told apart (R1 seats nothing; H-lite decides what an old
verdict is worth).

A release that lacks one of the files has NO identity (the read raises), never a smaller one.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

DEEP_EVIDENCE = ("__init__", "config", "calendar", "blocks", "relabel", "blind", "stat", "screen3", "gate")
DEEP_DATA = ("calendar_1999_2015.txt", "mask_dval_235.txt")
DEEP_PLUMBING = ("report", "identity")
#: league/swarm/evaluator.py's `EQUITY_EVIDENCE`, `EQUITY_GYM_FILES` and `EQUITY_CALENDAR_FILES` (held equal by a test).
EQUITY_EVIDENCE = ("__init__", "config", "store", "program", "ctx", "engine", "results", "runner", "synth", "sizing",
                   "screen", "child")
EQUITY_GYM_FILES = ("league/gym/__init__.py", "league/gym/safety.py", "league/gym/runtime.py", "league/gym/events.py")
EQUITY_CALENDAR_FILES = ("ltcm/__init__.py", "ltcm/broker.py", "ltcm/data/__init__.py")


def deep_files(repo: Path | None = None) -> list[Path]:
    """Every file the deep identity reads, in path order (the identity's whole definition)."""
    from ..gym.driver import LEAGUE_FILES

    repo = repo or Path(__file__).resolve().parents[2]
    files = {repo / name for name in (*LEAGUE_FILES, *EQUITY_GYM_FILES, *EQUITY_CALENDAR_FILES)}
    files.update(repo / "league" / "deep" / f"{name}.py" for name in DEEP_EVIDENCE)
    files.update(repo / "league" / "deep" / name for name in DEEP_DATA)
    files.update(repo / "league" / "equity" / f"{name}.py" for name in EQUITY_EVIDENCE)
    return sorted(files)


@lru_cache(maxsize=4)
def deep_fingerprint(repo: Path | None = None) -> str:
    """The deep evidence identity of the checkout at `repo` (default: this release)."""
    repo = repo or Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for path in deep_files(repo):
        digest.update(path.relative_to(repo).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


__all__ = ["DEEP_EVIDENCE", "DEEP_DATA", "DEEP_PLUMBING", "EQUITY_EVIDENCE", "EQUITY_GYM_FILES",
           "EQUITY_CALENDAR_FILES", "deep_files", "deep_fingerprint"]
