"""The `french` job: the Kenneth French library's daily factors on the House, when a route to them exists.

Owner: package B of release E4. Protected (league/ops/). STEP 0 STUB: the constants are the contract; every function
raises NotImplementedError until B lands. The registry row is package A's patch (E4-SPEC 13: monthly).

STATED PLAINLY: the library serves ZIP files only, the gateway's reader refuses a zip and the House has no other
egress. So `run` tries its `ROUTES` in order (a future gateway data route, 404 today; then
`<state>/equity-daily/french/inbox/` for files an operator placed) and with none returns {"status": "skipped", "why":
"no route to the French library from the House"}: not an alarm. Until a route exists XS1's French label reads
"unmeasured" (`league.xs.screen.UNMEASURED`) and the receipt's "style-open" flag attaches to every panel program.

THE SEAL. The library serves whole files, every year in one member: `parse` reads line by line and DROPS, unparsed,
every line whose first four characters are a year of `DROPPED_YEARS` (never held, never written); lines of
`SEALED_FROM` on go to a second file only the look's reader opens (specified with the route, not built now).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

ROUTES = ("/v1/data/french/", "french/inbox")
DIR = "french"
#: Lines of these years are dropped unparsed (2020 the reserve, 2021 history only).
DROPPED_YEARS = ("2020", "2021")
#: Lines from this year on are the look's reader's alone.
SEALED_FROM = 2025
FACTORS = ("Mkt-RF", "SMB", "HML", "Mom", "ST_Rev")
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 300

_STUB = "league.ops.french is a Step 0 stub: package B builds it (league/xs/E4_INTERFACES.md)"


def parse(lines: Iterable[str]) -> dict[str, Any]:
    """{"days": [ISO day...], "factors": {name: [float...]}, "sealed": {the same, for the years from `SEALED_FROM`
    on}} of one library file's lines; a line of `DROPPED_YEARS` is dropped without being split or parsed."""
    raise NotImplementedError(_STUB)


def write(root: str | Path, name: str, days: Sequence[str], factors: Any) -> Path:
    """Write one factor file under `<root>/french/` atomically (600) and return its path."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    raise NotImplementedError(_STUB)


__all__ = ["ROUTES", "DIR", "DROPPED_YEARS", "SEALED_FROM", "FACTORS", "WALL_S", "parse", "write", "run"]
