"""Re-head the idle rule's graveyard rows with the verdict of their Train record (R11-1, one time, the operator's).

Until R11-1 every idle-rule death was filed as "a time limit, not a finding that the mechanism has no edge", and the
digest tagged it IDLE, which the strategist read as untested. On Sept 29 99% of those deaths had been screened on Train.
The release carrying R11-1 files each new death under its verdict (`league.swarm.researcher.train_record`); this script
re-heads the rows already buried the same way, from the same function over each family's state (`drift_failed`,
`robust_failed`, `robust_why`, `best_train`) and its Train runs (`train_eligible`, `trades`). Train figures only (D2).

Runs ON THE HOUSE, from the release that carries R11-1 (it imports that release's `league`):

    /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state          # dry run
    /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state --apply  # re-head
    /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state \\
        --rollback /workspace/state/backups/graveyard-before-verdicts-<UTC>.json [--apply]                        # restore

A DRY RUN (the default) opens the store read-only and writes nothing: it prints the rows it would change, by verdict and
by the idle clause that retired them, a few examples, and the digest's ladder level before and after at the box's
budget. Only a row whose family's retirement reason carries the idle rule's old words ("not a finding that the mechanism
has no edge") is read; an untested family's row (it never traded on Train) keeps them and its IDLE tag.

APPLY: every row it changes (its lesson and its family's `retire_reason`) is first written to
`<state>/backups/graveyard-before-verdicts-<UTC>.json` (mode 600, written whole, then renamed into place). Then, in one
store transaction, each lesson and reason is replaced only if it is still the text that was read (compare and set), and
the digest's seal is emptied so every process reseals once on its next snapshot. Apply it right after the release is
promoted and before the next architect pass, so the digest reseals once for both (the release's new digest format
reseals it too). A fresh read-only store then counts the graveyard's tags.

ROLLBACK: `--rollback BACKUP` writes each row's lesson and reason back from the backup (dry run unless `--apply`), and
empties the seal again.

Standard library only; it never touches an event row (they are append-only) or a living family.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from league.swarm import settings as settings_mod  # noqa: E402
from league.swarm.architect import SEAL_KEY, GraveyardDigest, fit, parse_lesson, tag_of  # noqa: E402
from league.swarm.researcher import IDLE_CAUSE, idle_cause, train_record  # noqa: E402
from league.swarm.store import SwarmStore, iso  # noqa: E402

IDLE_MARK = "not a finding that the mechanism has no edge"
#: The idle rule's old words, whatever their wording at the time (from "Retired by the idle rule" to the mark).
OLD_CAUSE = re.compile(r"Retired by the idle rule\b.*?" + re.escape(IDLE_MARK), re.S)
LESSON_CHARS = 3000  # SwarmStore.bury's cut


def clause_of(reason: str) -> str:
    """Which idle clause retired it, in one word (for the counts)."""
    if "no new Gym evaluation" in reason:
        return "dormancy"
    if "no eligible Train version" in reason:
        return "no_eligible_version"
    if "below zero" in reason:
        return "negative_best"
    return "other"


def rehead(text: str, screen: str) -> str | None:
    """`text` (a retirement reason or a lesson) with the idle rule's old words replaced by the verdict's, once; None when
    they are not found."""
    new = idle_cause(screen)
    if IDLE_CAUSE in text:
        return text.replace(IDLE_CAUSE, new, 1)
    found = OLD_CAUSE.search(text)
    if not found:
        return None
    return text[:found.start()] + new + text[found.end():]


def plan(store: SwarmStore) -> tuple[list[dict[str, Any]], collections.Counter]:
    """The rows to change: [{family, screen, clause, lesson, new_lesson, reason, new_reason}], and the counts of every
    idle row read (by screen, and why a row is left)."""
    counts: collections.Counter = collections.Counter()
    rows = store._all("SELECT g.family AS family, g.lesson AS lesson FROM graveyard g JOIN families f ON f.id = g.family "
                      "WHERE f.retire_reason LIKE ? ORDER BY g.at, g.family", (f"%{IDLE_MARK}%",))
    out = []
    for row in rows:
        fam = store.family(row["family"])
        if fam is None or not fam.get("retired_at"):
            counts["skipped: not a retired family"] += 1
            continue
        reason = str(fam.get("retire_reason") or "")
        screen = train_record(store, fam)["screen"]
        counts[f"screen: {screen}"] += 1
        counts[f"clause: {clause_of(reason)}"] += 1
        if screen == "untested":
            continue  # it never traded on Train: it keeps the idle rule's words and its IDLE tag
        new_reason = rehead(reason, screen)
        new_lesson = rehead(str(row["lesson"] or ""), screen)
        if new_reason is None or new_lesson is None:
            counts["skipped: the idle rule's words were not found"] += 1
            continue
        out.append({"family": row["family"], "screen": screen, "clause": clause_of(reason), "lesson": row["lesson"],
                    "new_lesson": new_lesson[:LESSON_CHARS], "reason": reason, "new_reason": new_reason[:2000]})
    return out, counts


def ladder(store: SwarmStore, settings: dict[str, Any], changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The digest's ladder at the box's budget over every row now, or with `changes` applied in memory: its level, scale,
    characters and tags (`architect.fit`, as `GraveyardDigest.reseal` sizes it)."""
    digest = GraveyardDigest(store, settings)
    families = {f["id"]: f for f in store._all("SELECT id, lineage, retire_reason FROM families")}
    lessons = {c["family"]: c["new_lesson"] for c in changes or []}
    reasons = {c["family"]: c["new_reason"] for c in changes or []}
    rows = []
    for raw in store.graveyard(limit=10 ** 9):
        fam = families.get(raw["family"])
        if raw["family"] in lessons:
            raw = {**raw, "lesson": lessons[raw["family"]]}
            fam = {**(fam or {}), "retire_reason": reasons[raw["family"]]}
        rows.append(parse_lesson(raw, fam))
    rows.sort(key=lambda p: (p["at"], p["id"]))
    room = int(digest.budget_chars() * (1 - digest.tail_share())) - len(digest.header(len(rows), iso(time.time())))
    level, scale, body, keep = fit(rows, room)
    return {"rows": len(rows), "level": level, "scale": scale, "chars": len(body), "keep": keep,
            "tags": dict(collections.Counter(p["tag"] for p in rows).most_common())}


def write_backup(state: Path, rows: list[dict[str, Any]]) -> Path:
    """Every changed row's lesson and reason, before the change (mode 600, whole, then renamed into place)."""
    folder = state / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"graveyard-before-verdicts-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    part = path.with_suffix(".json.part")
    body = json.dumps({"at": iso(time.time()), "rows": [{"family": r["family"], "lesson": r["lesson"], "reason": r["reason"]}
                                                        for r in rows]}, indent=1).encode("utf-8")
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(part, path)
    return path


def apply(store: SwarmStore, changes: list[dict[str, Any]]) -> dict[str, int]:
    """Compare and set each row's lesson and its family's reason, in one transaction; then empty the digest's seal."""
    done = {"lessons": 0, "reasons": 0, "changed_since_read": 0}
    with store.atomic():
        for c in changes:
            a = store._exec("UPDATE graveyard SET lesson=? WHERE family=? AND lesson=?", (c["new_lesson"], c["family"], c["lesson"]))
            b = store._exec("UPDATE families SET retire_reason=? WHERE id=? AND retire_reason=? AND retired_at IS NOT NULL",
                            (c["new_reason"], c["family"], c["reason"]))
            done["lessons"] += a.rowcount
            done["reasons"] += b.rowcount
            done["changed_since_read"] += int(not (a.rowcount and b.rowcount))
        store.put(SEAL_KEY, {})  # every process reseals on its next snapshot (its memo is keyed on the seal)
    return done


def tag_counts(state: Path) -> dict[str, int]:
    store = SwarmStore(state, readonly=True)
    try:
        families = {f["id"]: f for f in store._all("SELECT id, retire_reason FROM families")}
        return dict(collections.Counter(tag_of(r, families.get(r["family"])) for r in store.graveyard(limit=10 ** 9)).most_common())
    finally:
        store.close()


def rollback(state: Path, backup: Path, write: bool) -> dict[str, Any]:
    rows = json.loads(backup.read_text())["rows"]
    if not write:
        return {"mode": "rollback dry run", "rows": len(rows)}
    store = SwarmStore(state)
    try:
        done = {"lessons": 0, "reasons": 0}
        with store.atomic():
            for r in rows:
                done["lessons"] += store._exec("UPDATE graveyard SET lesson=? WHERE family=?", (r["lesson"], r["family"])).rowcount
                done["reasons"] += store._exec("UPDATE families SET retire_reason=? WHERE id=? AND retired_at IS NOT NULL",
                                               (r["reason"], r["family"])).rowcount
            store.put(SEAL_KEY, {})
    finally:
        store.close()
    return {"mode": "rollback", "rows": len(rows), **done, "tags_after": tag_counts(state)}


def main(argv: list[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state", default="/workspace/state")
    ap.add_argument("--apply", action="store_true", help="write (a dry run otherwise)")
    ap.add_argument("--rollback", metavar="BACKUP", help="restore the rows a backup holds")
    ap.add_argument("--examples", type=int, default=3, help="examples a verdict in the report")
    a = ap.parse_args(argv)
    state = Path(a.state)
    if a.rollback:
        return rollback(state, Path(a.rollback), a.apply)
    store = SwarmStore(state, readonly=True)
    try:
        changes, counts = plan(store)
        settings = settings_mod.load(state)
        report: dict[str, Any] = {"mode": "apply" if a.apply else "dry run", "read": dict(sorted(counts.items())),
                                  "to_change": len(changes),
                                  "by_screen": dict(collections.Counter(c["screen"] for c in changes).most_common()),
                                  "by_clause": dict(collections.Counter(c["clause"] for c in changes).most_common())}
        shown: collections.Counter = collections.Counter()
        report["examples"] = []
        for c in changes:
            if shown[c["screen"]] < a.examples:
                shown[c["screen"]] += 1
                report["examples"].append({"family": c["family"], "screen": c["screen"], "reason": c["new_reason"][:400]})
        report["digest_before"] = ladder(store, settings)
        report["digest_after"] = ladder(store, settings, changes)
    finally:
        store.close()
    if not a.apply or not changes:
        return report
    report["backup"] = str(write_backup(state, changes))
    writer = SwarmStore(state)
    try:
        report["applied"] = apply(writer, changes)
    finally:
        writer.close()
    report["tags_after"] = tag_counts(state)
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
