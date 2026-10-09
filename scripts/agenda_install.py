"""THE AGENDA GUARD's operator tool (release D-1, Oct 9, 2026; the plan's D9): install a locked agenda into the House's
`swarm.json`, or refuse it.

    python3 scripts/agenda_install.py check FILE [--state /workspace/state]
    python3 scripts/agenda_install.py apply FILE [--state /workspace/state] [--keep-section]

WHY. The architect reads at most `architect.AGENDA_LOCKED_MAX` (4,000) characters of the locked preamble
(`architect.agenda_locked`) and of the fallback agenda (`architect.agenda`) and silently drops the rest: agenda v19
(4,407 characters) lost the end of its item 7 and all of item 8 from T0 until v19.1 replaced it. The agendas are the
operator's private text (the public repository never holds them), installed by hand on the box; this tool is the one
way to do it that checks the text first.

`check` (read-only) prints, as JSON, the new text's length and sha256, the problems (`dlane.agenda_problems`: empty,
longer than the architect reads, not ASCII, naming a hidden year), and the lengths and sha256 of the two agendas now in
`swarm.json`. It never prints the text. Exit 0 when the text may be installed, 2 when it is refused.

`apply` REFUSES (exit 2, nothing written) any text `check` refuses. Otherwise it keeps a before-copy
(`swarm.json.before-agenda-<UTC stamp>`), writes the text (stripped, as the architect reads it) into BOTH
`architect.agenda_locked` and `architect.agenda` through a temporary file it reads back, mode 600, and an atomic replace,
and clears the strategist's WHERE TO LOOK section (the store's kv `architect_agenda_section`: it was written under the
old preamble; `--keep-section` leaves it). The swarm reads `swarm.json` on its next loop: no restart. The architect's
next pass carries the new preamble whole (its request's agenda length is the text's).

Run it on the box from the running release: `cd /workspace/current && /workspace/.venv/bin/python
scripts/agenda_install.py check /path/to/agenda.txt`, then `apply` (docs/operations.md, **Release D-1**, the runbook).
Standard library and the release's own `league` package only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the checkout's own league package

from league.swarm import dlane  # noqa: E402 - after the checkout's path

STATE = Path("/workspace/state")
SECTION_KEY = "architect_agenda_section"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _describe(text: Any) -> dict[str, Any]:
    text = str(text or "")
    return {"length": len(text), "sha256": _sha(text) if text else None}


def check(path: Path, state: Path) -> dict[str, Any]:
    """What `apply` would do (read-only): {file, length, sha256, problems, may_install, now: {agenda_locked, agenda}}."""
    text = path.read_text(encoding="utf-8").strip()
    problems = dlane.agenda_problems(text)
    try:
        current = json.loads((state / "swarm.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        current, problems = {}, problems + [f"swarm.json cannot be read ({type(exc).__name__})"]
    block = current.get("architect") if isinstance(current, dict) and isinstance(current.get("architect"), dict) else {}
    return {"file": str(path), **_describe(text), "limit": dlane.AGENDA_MAX, "problems": problems,
            "may_install": not problems,
            "now": {key: _describe(block.get(key)) for key in ("agenda_locked", "agenda")}}


def apply(path: Path, state: Path, *, keep_section: bool = False) -> dict[str, Any]:
    """Install the text (the module docstring), or refuse it: {applied, backup, ...check's fields, section_cleared}."""
    out = check(path, state)
    if out["problems"]:
        return {**out, "applied": False}
    text = path.read_text(encoding="utf-8").strip()
    target = state / "swarm.json"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = state / f"swarm.json.before-agenda-{stamp}"
    shutil.copy2(target, backup)
    doc = json.loads(target.read_text(encoding="utf-8"))
    block = doc.setdefault("architect", {})
    block["agenda_locked"] = text
    block["agenda"] = text
    tmp = target.with_name("swarm.json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    again = json.loads(tmp.read_text(encoding="utf-8"))  # it reads back whole before it replaces anything
    assert again["architect"]["agenda_locked"] == text and again["architect"]["agenda"] == text
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    cleared = False
    if not keep_section:
        from league.swarm.store import SwarmStore

        store = SwarmStore(state)
        try:
            cleared = store.get(SECTION_KEY) is not None
            store.put(SECTION_KEY, None)
        finally:
            store.close()
    written = json.loads(target.read_text(encoding="utf-8"))["architect"]
    return {**out, "applied": True, "backup": str(backup), "section_cleared": cleared,
            "written": {key: _describe(written.get(key)) for key in ("agenda_locked", "agenda")}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("check", "apply"))
    parser.add_argument("file", type=Path, help="the agenda's text (the operator's private file)")
    parser.add_argument("--state", type=Path, default=STATE, help="the House's state root (default /workspace/state)")
    parser.add_argument("--keep-section", action="store_true", help="leave the strategist's WHERE TO LOOK section")
    args = parser.parse_args(argv)
    out = check(args.file, args.state) if args.command == "check" else apply(args.file, args.state,
                                                                             keep_section=args.keep_section)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0 if not out["problems"] else 2


if __name__ == "__main__":
    sys.exit(main())
