"""Strategies written after the founding: by Merton as architect, through pull requests.

A founding seed starts on paper. A strategy from this directory does not: it is born on rung 0
and must pass replay, against every trial its family has run, before it is forward-tested.
`registry.json` lists what is here; the House spawns what is listed and not yet born whenever
the population has room.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def registry(directory: Path = HERE) -> list[dict[str, Any]]:
    path = directory / "registry.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and all(isinstance(row.get(k), str) and row[k] for k in ("name", "family", "file", "why")):
            if "/" not in row["file"] and row["file"].endswith(".py"):
                out.append({k: row[k] for k in ("name", "family", "file", "why")})
    return out


def all_strategies(directory: Path = HERE) -> list[dict[str, Any]]:
    rows = []
    for row in registry(directory):
        path = directory / row["file"]
        if path.exists():
            rows.append({**row, "code": path.read_text(encoding="utf-8")})
    return rows
