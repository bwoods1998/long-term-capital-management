"""The `french` job: the Kenneth French library's daily factors on the House, when a route to them exists.

Owner: package B of release E4. Protected (league/ops/). The registry row is package A's patch (E4-SPEC 13: monthly).

STATED PLAINLY: the library serves ZIP files only, the gateway's reader refuses a zip and the House has no other
egress. So `run` tries its `ROUTES` in order (a future gateway data route, 404 today; then
`<state>/equity-daily/french/inbox/` for files an operator placed) and with none returns {"status": "skipped", "why":
"no route to the French library from the House"}: not an alarm. Until a route exists XS1's French label reads
"unmeasured" (`league.xs.screen.UNMEASURED`) and the receipt's "style-open" flag attaches to every panel program.

THE ROUTES, as this release reads them:
- `GET /v1/data/french/<file>` through the gateway. No such route exists today (the gateway answers 404, and this
  release does not add it: an owner option, E4-SPEC 19). The one answer read is a JSON object {"text": <the file's
  one member, as text>}; any error, and any other shape, is "no answer" and the next route is tried.
- the inbox: a file an operator placed under `<state>/equity-daily/french/inbox/`, named as the library names it
  (`FILES`' stems; `INBOX_SUFFIXES`: the member as text, or the library's own zip, whose one member is read as a
  stream). A file that was read and kept is REMOVED from the inbox in the same run: it holds every year, and the
  lines this job may not keep must not stay on the House's disk either.

THE SEAL. The library serves whole files, every year in one member: `parse` reads line by line and DROPS, unparsed,
every line whose first four characters are a year of `DROPPED_YEARS` (never split, never held, never written: seal
X13, `test_french.ParseDropsTheReserve`); a line of those years that does not BEGIN with its year is not the
library's format and refuses the whole file. Lines of `SEALED_FROM` on are the look's reader's alone: that reader and
its file come with the route and are not built now, so `run` COUNTS them and writes none of them anywhere. WHAT
THAT MEANS TODAY: an inbox file gives the House the factor days of the Train era and before; XS1's French label is
read on Validation and the holdout (2025 on), so it stays "unmeasured" until the look's file and its reader exist.

WHAT IS WRITTEN: `<state>/equity-daily/french/<file>.json` (600, atomic): {"version", "name", "unit": "fraction",
"days": [ISO day...], "factors": {name: [float | null...]}, "rows", "first", "last"}: the library's percent figures
as fractions (the decimal point moved two places, never a float division), null where the library marks a missing
value; days of 1926 through 2019 and of 2022 through 2024, never another. The receipt carries counts, days and
verdicts, never a factor value.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

ROUTES = ("/v1/data/french/", "french/inbox")
DIR = "french"
#: Lines of these years are dropped unparsed (2020 the reserve, 2021 history only).
DROPPED_YEARS = ("2020", "2021")
#: Lines from this year on are the look's reader's alone.
SEALED_FROM = 2025
FACTORS = ("Mkt-RF", "SMB", "HML", "Mom", "ST_Rev")
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 300
#: The equity lane's state directory (`league.ops.equity_data.STORE_DIR`; spelled here, a test holds them equal).
STORE_DIR = "equity-daily"
VERSION = "french-v1"
INBOX = "inbox"
#: The library's daily files this job reads (its own file stems), and the factors each one carries.
FILES: dict[str, tuple[str, ...]] = {"F-F_Research_Data_Factors_daily": ("Mkt-RF", "SMB", "HML"),
                                     "F-F_Momentum_Factor_daily": ("Mom",),
                                     "F-F_ST_Reversal_Factor_daily": ("ST_Rev",)}
#: How an inbox file may be named after its stem (case-blind): the member as text, or the library's own zip.
INBOX_SUFFIXES = (".csv", ".txt", "_csv.zip", ".zip")
#: The library marks a missing value with -99.99 or -999 (percent): a figure at or under this is no value.
MISSING_AT = Decimal("-99")
SKIPPED = "no route to the French library from the House"


def _blank() -> dict[str, Any]:
    return {"days": [], "factors": {}}


def parse(lines: Iterable[str]) -> dict[str, Any]:
    """{"days": [ISO day...], "factors": {name: [float | None...]}, "sealed": {the same, for the years from
    `SEALED_FROM` on}, "dropped": the lines dropped unparsed} of one library file's lines; a line of `DROPPED_YEARS` is
    dropped without being split or parsed.

    The library's daily format: some lines of text, ONE header line that begins with a comma and names the columns,
    then a line a day (`YYYYMMDD, value, ...`, percent), then a blank line or text (the table's end: nothing after it
    is read). Of the header's columns the ones named in `FACTORS` are kept, as fractions; a missing value (`MISSING_AT`)
    is None. ValueError (nothing of the file is then kept by the caller) for: no header; a header naming none of
    `FACTORS` or one of them twice; a day line whose fields are not the header's count, whose day is not a date or
    does not come after the line before it, or a value that is not a number; and A RESERVE LINE THAT DOES NOT BEGIN
    WITH ITS YEAR (it is refused before it is split)."""
    names: list[str] | None = None
    keep: list[tuple[int, str]] = []
    seen, sealed = _blank(), _blank()
    dropped = 0
    started = ended = False
    last: dt.date | None = None
    for line in lines:
        if not isinstance(line, str):
            raise ValueError("the lines are text (a file's bytes are decoded before they are read)")
        if line[:4] in DROPPED_YEARS:
            dropped += 1  # the reserve and its history year: never split, never parsed, never held
            continue
        if ended:
            continue
        text = line.strip()
        if text[:4] in DROPPED_YEARS:
            raise ValueError("a line of a dropped year does not begin with its year: not the library's format, "
                             "nothing of the file is kept")
        if names is None:
            if text.startswith(","):
                names = [name.strip() for name in text.split(",")]
                keep = [(i, name) for i, name in enumerate(names) if name in FACTORS]
                if not keep:
                    raise ValueError("the header names none of the factors " + ", ".join(FACTORS))
                if len({name for _, name in keep}) != len(keep):
                    raise ValueError("the header names a factor twice")
                for part in (seen, sealed):
                    part["factors"] = {name: [] for _, name in keep}
            continue
        stamp, _, rest = text.partition(",")
        stamp = stamp.strip()
        if not (len(stamp) == 8 and stamp.isdigit()):
            ended = started  # a blank line or text after the days: the table's end (before them: more preamble)
            continue
        fields = [stamp, *(field.strip() for field in rest.split(","))]
        if len(fields) != len(names):
            raise ValueError(f"the line of {stamp} has {len(fields)} fields, the header {len(names)}")
        try:
            day = dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
        except ValueError:
            raise ValueError(f"{stamp} is not a day") from None
        if last is not None and day <= last:
            raise ValueError(f"the line of {stamp} does not come after the line before it")
        last, started = day, True
        part = sealed if day.year >= SEALED_FROM else seen
        values = []
        for i, name in keep:
            try:
                value = Decimal(fields[i])
            except InvalidOperation:
                raise ValueError(f"the {name} of {stamp} is not a number") from None
            if not value.is_finite():
                raise ValueError(f"the {name} of {stamp} is not a number")
            values.append(None if value <= MISSING_AT else float(value.scaleb(-2)))
        part["days"].append(day.isoformat())
        for (_, name), value in zip(keep, values):
            part["factors"][name].append(value)
    if names is None:
        raise ValueError("no header line (the library's begins with a comma)")
    return {"days": seen["days"], "factors": seen["factors"], "sealed": sealed, "dropped": dropped}


def write(root: str | Path, name: str, days: Sequence[str], factors: Any) -> Path:
    """Write one factor file under `<root>/french/` atomically (600) and return its path. `root` is
    `<state>/equity-daily`; `name` a plain file stem. ValueError, and nothing written, for a name that is not one, no
    day, factor lists that are not the days' length, days that do not ascend, and A DAY THIS FILE MAY NOT HOLD (a
    year of `DROPPED_YEARS`, or from `SEALED_FROM` on)."""
    from .context import write_json

    name = str(name)
    if not name or name != Path(name).name or name.startswith(".") or "\\" in name:
        raise ValueError(f"{name[:60]!r} is not a plain file name")
    days = [str(day) for day in days]
    if not days:
        raise ValueError("no day to write")
    if not isinstance(factors, Mapping) or not factors:
        raise ValueError("no factor to write")
    previous = None
    for day in days:
        parsed = dt.date.fromisoformat(day)
        if day[:4] in DROPPED_YEARS or parsed.year >= SEALED_FROM:
            raise ValueError(f"a day of {parsed.year} is never written to this file")
        if previous is not None and parsed <= previous:
            raise ValueError("the days do not ascend")
        previous = parsed
    out: dict[str, list[float | None]] = {}
    for factor, values in factors.items():
        values = list(values)
        if len(values) != len(days):
            raise ValueError(f"{factor}: {len(values)} values for {len(days)} days")
        out[str(factor)] = [None if value is None else float(value) for value in values]
    return write_json(Path(root) / DIR / f"{name}.json",
                      {"version": VERSION, "name": name, "unit": "fraction", "days": days, "factors": out,
                       "rows": len(days), "first": days[0], "last": days[-1]}, indent=None)


def inbox(root: str | Path) -> dict[str, Path]:
    """{file stem of `FILES`: the inbox file an operator placed for it} (`<root>/french/inbox/`; the first of
    `INBOX_SUFFIXES` that exists, names compared case-blind). {} when there is no inbox."""
    folder = Path(root) / DIR / INBOX
    try:
        present = {path.name.lower(): path for path in sorted(folder.iterdir()) if path.is_file()}
    except OSError:
        return {}
    out: dict[str, Path] = {}
    for stem in FILES:
        for suffix in INBOX_SUFFIXES:
            path = present.get((stem + suffix).lower())
            if path is not None:
                out[stem] = path
                break
    return out


def _zip_lines(path: Path) -> Iterator[str]:
    """The lines of a library zip's ONE member, as a stream (the member is never extracted to disk)."""
    with zipfile.ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) != 1:
            raise ValueError(f"the zip holds {len(members)} files, the library's holds one")
        with archive.open(members[0]) as raw, io.TextIOWrapper(raw, encoding="latin-1") as handle:
            yield from handle


def file_lines(path: str | Path) -> Iterator[str]:
    """The lines of an inbox file, one at a time (a zip's one member, or the text file itself)."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        yield from _zip_lines(path)
        return
    with path.open(encoding="latin-1") as handle:
        yield from handle


def _from_gateway(ctx: Any, stem: str) -> Iterator[str] | None:
    """The lines of `stem` from the gateway's data route, or None: no such route today (404), and any error or any
    answer but {"text": str} is no answer."""
    try:
        answer = ctx.gateway.get(ROUTES[0] + stem)
    except Exception:  # noqa: BLE001 - no route (404 today), no gateway, a refusal: the next route is tried
        return None
    text = answer.get("text") if isinstance(answer, Mapping) else None
    return iter(text.splitlines()) if isinstance(text, str) and text else None


def _run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`. {"ok": True, "files": {stem:
    {"route", "days", "first", "last", "dropped", "sealed"}}, "missing": [stems with no route]}; {"status": "skipped",
    "why"} with no route at all (not an alarm) or inside a quiet window; {"status": "failed", "ok": False, "error",
    ...} when a file a route gave could not be read (it is left where it was, and nothing of it is written)."""
    from ..xs import config as xs_config
    from .equity_universe import lane_off

    off = lane_off(ctx.root)    # WITH THE LANE'S SWITCH OFF NOTHING OF E4 RUNS (`elane.panel.mode`): its data too
    if off is not None:
        return {"status": "skipped", "why": off}
    try:
        why = xs_config.quiet(ctx.now(), WALL_S)
    except Exception as exc:  # noqa: BLE001 - a job that cannot learn whether it stands at a wall does not start
        why = f"the quiet windows could not be read ({type(exc).__name__}: {str(exc)[:160]})"
        ctx.alert("warning", f"french: {why}; the job did not run")
    if why is not None:
        return {"status": "skipped", "why": why}
    root = Path(ctx.root) / STORE_DIR
    placed = inbox(root)
    files: dict[str, dict[str, Any]] = {}
    problems: dict[str, str] = {}
    missing: list[str] = []
    for stem, wanted in FILES.items():
        lines, route = _from_gateway(ctx, stem), "gateway"
        if lines is None and stem in placed:
            lines, route = file_lines(placed[stem]), "inbox"
        if lines is None:
            missing.append(stem)
            continue
        try:
            parsed = parse(lines)
            absent = [factor for factor in wanted if factor not in parsed["factors"]]
            if absent:
                raise ValueError("the file lacks " + ", ".join(absent))
            if not parsed["days"]:
                raise ValueError("the file holds no day this job may keep")
            write(root, stem, parsed["days"], {factor: parsed["factors"][factor] for factor in wanted})
        except Exception as exc:  # noqa: BLE001 - this file is not kept; the others still are
            problems[stem] = f"{route}: {type(exc).__name__}: {str(exc)[:200]}"
            continue
        finally:
            close = getattr(lines, "close", None)  # a file's stream is closed whether or not it was read to its end
            if close is not None:
                close()
        files[stem] = {"route": route, "days": len(parsed["days"]), "first": parsed["days"][0],
                       "last": parsed["days"][-1], "dropped": parsed["dropped"],
                       "sealed": len(parsed["sealed"]["days"])}
        del parsed  # the sealed lines are counted above and held no longer
        if route == "inbox":
            try:
                placed[stem].unlink()
            except OSError as exc:
                ctx.alert("warning", f"french: the inbox file of {stem} was read and kept but could not be removed "
                                     f"({type(exc).__name__}): it holds every year, remove it by hand")
    if not files and not problems:
        return {"status": "skipped", "why": SKIPPED}
    out: dict[str, Any] = {"ok": not problems, "files": files, "missing": missing}
    if problems:
        out.update(status="failed", problems=problems,
                   error="; ".join(f"{stem}: {text}" for stem, text in sorted(problems.items()))[:600])
    return out



def run(ctx: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """The job as the registry runs it: `_run` with the wall detector around it (`equity_universe.watched`: a job found
    RUNNING at a wall says so, critically)."""
    from .equity_universe import watched

    return watched("french", _run)(ctx, *args, **kwargs)

__all__ = ["ROUTES", "DIR", "DROPPED_YEARS", "SEALED_FROM", "FACTORS", "WALL_S", "STORE_DIR", "VERSION", "INBOX",
           "FILES", "INBOX_SUFFIXES", "MISSING_AT", "SKIPPED", "parse", "write", "inbox", "file_lines", "run"]
