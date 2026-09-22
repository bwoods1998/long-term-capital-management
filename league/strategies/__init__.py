"""Strategies written after the founding: by Merton as architect, through pull requests.

A founding seed starts on paper. A strategy from this directory does not: it is born on rung 0
and must pass replay, against every trial its family has run, before it is forward-tested.
The House spawns what is listed and not yet born whenever the population has room.

**One description file per strategy.** `<stem>.py` is described by `<stem>.json`:
`{"name", "family", "why"}`, optionally `"file"` (which must be `<stem>.py`) and `"repair"`
(the repair job and parent agent a corrected child descends from). Until Sept 22, 2026 every
strategy was a row of one shared `registry.json`, and every architect pull request rewrote that
whole file from the copy the RUNNING release held: PRs #72 and #73 were cut after #71 merged,
carried a registry without #71's row, and would have deleted it on merge (CI refused them for
other reasons first). Two proposals now add two different files and cannot collide. A tree
that still carries `registry.json` is read as a legacy list, after the per-strategy files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LEGACY = "registry.json"
FIELDS = ("name", "family", "file", "why")
#: A strategy file's basename: what `file` may say, and what a description file is named after.
STEM = re.compile(r"[a-z][a-z0-9_]*")


def describe(row: dict[str, Any]) -> tuple[str, str]:
    """`(path under league/strategies, content)` of one strategy's description file."""
    stem = str(row["file"])[:-3]
    body = {k: row[k] for k in ("name", "family", "why")}
    if isinstance(row.get("repair"), dict):
        body["repair"] = row["repair"]
    return f"{stem}.json", json.dumps(body, indent=2, sort_keys=True) + "\n"


def _row(raw: Any, *, stem: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """One valid row, or why not. `stem` is the description file's own name, when it has one."""
    if not isinstance(raw, dict):
        return None, "not a JSON object"
    row = dict(raw)
    if stem is not None:
        if row.get("file") not in (None, f"{stem}.py"):
            return None, f"file says {row.get('file')!r}, but a description file describes {stem}.py"
        row["file"] = f"{stem}.py"
    missing = [k for k in FIELDS if not (isinstance(row.get(k), str) and row[k].strip())]
    if missing:
        return None, "missing " + ", ".join(missing)
    if not (row["file"].endswith(".py") and STEM.fullmatch(row["file"][:-3])):
        return None, f"file {row['file']!r} is not a plain strategy basename"
    out = {k: row[k] for k in FIELDS}
    if isinstance(row.get("repair"), dict):
        out["repair"] = {k: str(v)[:200] for k, v in row["repair"].items() if isinstance(k, str)}
    return out, None


def _read(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == LEGACY:
            continue
        stem = path.name[:-5]
        if not STEM.fullmatch(stem):
            problems.append(f"{path.name}: a description file is named after its strategy file (lowercase, underscores)")
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            problems.append(f"{path.name}: not valid JSON")
            continue
        row, why = _row(raw, stem=stem)
        if row is None:
            problems.append(f"{path.name}: {why}")
        else:
            rows.append(row)
    legacy = directory / LEGACY
    if legacy.exists():
        try:
            listed = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            listed = None
            problems.append(f"{LEGACY}: not valid JSON")
        for raw in listed if isinstance(listed, list) else []:
            row, _ = _row(raw, stem=None)
            if row is not None:
                rows.append(row)
    kept: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    files: dict[str, str] = {}
    for row in rows:
        # The per-strategy file is read first and wins; a legacy row saying the same is harmless.
        if row["name"] in names or row["file"] in files:
            if names.get(row["name"]) != row["file"] or files.get(row["file"]) != row["name"]:
                problems.append(f"{row['name']} ({row['file']}): the name or the file is already described differently")
            continue
        names[row["name"]], files[row["file"]] = row["file"], row["name"]
        kept.append(row)
    return kept, problems


def registry(directory: Path = HERE) -> list[dict[str, Any]]:
    return _read(Path(directory))[0]


def problems(directory: Path = HERE) -> list[str]:
    """What is wrong with the descriptions themselves (CI's content check reads this)."""
    return _read(Path(directory))[1]


def all_strategies(directory: Path = HERE) -> list[dict[str, Any]]:
    rows = []
    for row in registry(directory):
        path = Path(directory) / row["file"]
        if path.exists():
            rows.append({**row, "code": path.read_text(encoding="utf-8")})
    return rows
