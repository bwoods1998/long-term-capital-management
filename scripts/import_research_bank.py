"""Seed the Merton desk's memory with the first-generation research bank.

The first generation (Portfolio Agent, September 2026) spent a week reading primary filings for
one S&P 500 paper portfolio and left its work in a SQLite research database: a `tasks` table whose
completed rows carry a JSON `result` with a written case for a company, the open questions that
case could not answer, and the dated claims it was built on, plus a `decisions` table recording the
portfolio-level allocation reviews.

That work does not belong in an archive. This script folds it into `ltcm`'s own memory store as one
entry per company for the desk that inherits the mandate -- `merton`, the filings desk -- so the
first session after the import starts with the questions the first generation was still asking.

    python3 scripts/import_research_bank.py --dry-run     # what it would write
    python3 scripts/import_research_bank.py               # write it

It is idempotent: each entry's id is derived from the desk and the company, so a second run writes
nothing and says so. It reads the research database read-only, never edits it, and makes no network
request. Nothing about this script is scheduled: it is run once, by hand, and the count it prints is
the count the floor can check with `python3 -m ltcm status`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ltcm.desk import MemoryStore  # noqa: E402  (the path above makes this importable)

#: Where the first generation left its week of reading, and where this generation keeps memory.
DEFAULT_RESEARCH = ROOT / ".data" / "runtime" / "five-hour" / "host" / "drained-backup" / "research.sqlite"
DEFAULT_MEMORY = ROOT / ".data" / "ltcm" / "memory.sqlite"

DESK_ID = "merton"
KIND = "research"
TAGS = ["portfolio-agent", "2026-09"]
SOURCE_EVENT = "import:portfolio-agent"

#: `MemoryStore` refuses anything longer. The case is clipped before the questions are dropped.
TEXT_LIMIT = 4000
MAX_QUESTIONS = 6


class ResearchBankError(RuntimeError):
    """The research database is missing or not shaped the way this script expects."""


def _connect_readonly(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.exists():
        raise ResearchBankError(f"no research database at {path}")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _tables(db: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _result(row: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = row["result"]
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def case_text(result: Mapping[str, Any]) -> str:
    """The written case. The first generation called it `thesis`; early rows called it `case`."""
    for key in ("case", "thesis"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def questions_of(result: Mapping[str, Any]) -> list[str]:
    """The open questions, highest priority first, as plain sentences."""
    rows = result.get("questions")
    if not isinstance(rows, list):
        return []
    ranked: list[tuple[int, int, str]] = []
    for index, row in enumerate(rows):
        if isinstance(row, str):
            text, priority = row, 9
        elif isinstance(row, Mapping):
            text = row.get("question") or row.get("text") or ""
            priority = row.get("priority")
            priority = int(priority) if isinstance(priority, int) else 9
        else:
            continue
        text = " ".join(str(text).split())
        if text:
            ranked.append((priority, index, text))
    ranked.sort(key=lambda item: (item[0], item[1]))
    out: list[str] = []
    for _, _, text in ranked:
        if text not in out:
            out.append(text)
    return out[:MAX_QUESTIONS]


def compose(symbol: str, case: str, questions: Iterable[str], limit: int = TEXT_LIMIT) -> str:
    """The memory entry's text: the case, then the questions it left open, inside the limit."""
    head = f"{symbol}: {case}".strip()
    questions = [q for q in questions]
    if not questions:
        return head[:limit].strip()
    tail_lines = ["", "Open questions:"] + [f"- {q}" for q in questions]
    tail = "\n".join(tail_lines)
    while tail and len(head) + 1 + len(tail) > limit and len(tail_lines) > 3:
        tail_lines.pop()  # drop the lowest-priority question rather than truncate a sentence
        tail = "\n".join(tail_lines)
    room = limit - len(tail) - 1
    if room < 0:  # pathological: keep the case, drop the questions
        return head[:limit].strip()
    return (head[:room].strip() + "\n" + tail).strip()


def entry_id(desk_id: str, symbol: str) -> str:
    """Stable per desk and company, so re-running the import is a no-op."""
    return f"mem-import-{desk_id}-{symbol.lower()}"


def companies(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """One row per company: the newest completed research task that wrote a case.

    A symbol is researched several times over a week (a first pass, then fresh reviews). The
    newest task is the one that saw the most, so it is the one the desk inherits.
    """
    tables = _tables(db)
    if "tasks" not in tables:
        raise ResearchBankError("the research database has no `tasks` table")
    rows = db.execute(
        "SELECT id, wave, kind, symbol, status, created, result FROM tasks"
        " WHERE symbol IS NOT NULL AND result IS NOT NULL"
    ).fetchall()
    newest: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for row in rows:
        if (row["status"] or "") != "complete":
            continue
        symbol = str(row["symbol"] or "").strip()
        result = _result(row)
        if not symbol or result is None:
            continue
        case = case_text(result)
        if not case:
            continue
        rank = (int(row["wave"] or 0), float(row["created"] or 0), str(row["id"]))
        record = {
            "symbol": symbol,
            "case": case,
            "questions": questions_of(result),
            "claims": result.get("claims") if isinstance(result.get("claims"), list) else [],
            "task_id": str(row["id"]),
            "task_kind": str(row["kind"] or ""),
        }
        held = newest.get(symbol)
        if held is None or rank > held[0]:
            newest[symbol] = (rank, record)
    return [record for _, (_, record) in sorted(newest.items(), key=lambda kv: kv[0])]


def decision_count(db: sqlite3.Connection) -> int:
    """How many portfolio decisions the first generation recorded. Context for the operator."""
    if "decisions" not in _tables(db):
        return 0
    return int(db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])


def entries(
    records: Iterable[Mapping[str, Any]], *, desk_id: str = DESK_ID, at: str | None = None
) -> list[dict[str, Any]]:
    """`MemoryStore` entries for the companies, in symbol order."""
    out: list[dict[str, Any]] = []
    for record in records:
        symbol = str(record["symbol"])
        entry = {
            "id": entry_id(desk_id, symbol),
            "desk_id": desk_id,
            "kind": KIND,
            "symbol": symbol,
            "text": compose(symbol, str(record.get("case") or ""), record.get("questions") or []),
            "tags": list(TAGS),
            "source_event": SOURCE_EVENT,
        }
        if at is not None:
            entry["at"] = at
        out.append(entry)
    return out


def import_bank(
    research_path: str | Path,
    memory_path: str | Path,
    *,
    desk_id: str = DESK_ID,
    at: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read the bank, write the entries that are not already there, and report the counts."""
    db = _connect_readonly(research_path)
    try:
        records = companies(db)
        decisions = decision_count(db)
    finally:
        db.close()
    if limit is not None:
        records = records[: max(0, int(limit))]
    rows = entries(records, desk_id=desk_id, at=at)
    summary = {
        "research": str(research_path),
        "memory": str(memory_path),
        "desk_id": desk_id,
        "companies": len(rows),
        "decisions": decisions,
        "imported": 0,
        "skipped": 0,
        "symbols": [row["symbol"] for row in rows],
    }
    if dry_run:
        return summary
    store = MemoryStore(memory_path)
    try:
        for row in rows:
            if store.get(row["id"]) is not None:
                summary["skipped"] += 1
                continue
            store.write(row)
            summary["imported"] += 1
        summary["desk_entries"] = store.count(desk_id)
    finally:
        store.close()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--research", default=str(DEFAULT_RESEARCH), help="first-generation research.sqlite")
    parser.add_argument("--memory", default=str(DEFAULT_MEMORY), help="the floor's memory.sqlite")
    parser.add_argument("--desk", default=DESK_ID, help="the desk that inherits the bank")
    parser.add_argument("--at", default=None, help="timestamp to stamp the entries with")
    parser.add_argument("--limit", type=int, default=None, help="import at most this many companies")
    parser.add_argument("--dry-run", action="store_true", help="read and report, write nothing")
    args = parser.parse_args(argv)

    try:
        summary = import_bank(
            args.research,
            args.memory,
            desk_id=args.desk,
            at=args.at,
            dry_run=args.dry_run,
            limit=args.limit,
        )
    except ResearchBankError as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 2

    verb = "would import" if args.dry_run else "imported"
    print(
        f"{summary['companies']} companies in the research bank "
        f"({summary['decisions']} portfolio decisions recorded)"
    )
    if args.dry_run:
        print(f"{verb} {summary['companies']} entries for desk {summary['desk_id']}")
    else:
        print(
            f"{verb} {summary['imported']} entries for desk {summary['desk_id']} "
            f"({summary['skipped']} already present) into {summary['memory']}"
        )
        print(f"{summary['desk_entries']} memory entries now belong to {summary['desk_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
