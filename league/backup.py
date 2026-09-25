"""The league's memory, kept somewhere other than the one disk it lives on.

Everything an agent is lives on the House's ledger: its code, its record, its journal, its family's
trials. The ledger is one SQLite file on one Sailbox. A superstar that took a fortnight to find
must not be lost to a dead disk, so once a day the House checkpoints its own box with Sail (a
snapshot of the whole disk, kept by Sail outside the box) under a rolling name, each kept for a
week. Restoring is `python3 scripts/floor_box.py restore`-style work for the owner: a new box from
the newest checkpoint comes back with the ledger, the agents' state and the promoted release.

The snapshot holds what the box holds, including its three credentials (never a venue key), and
stays inside the owner's Sail account, like the checkpoints `floor_box.py checkpoint` takes.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .ledger import Ledger, now_iso


class Backup:
    def __init__(self, client: Any, ledger: Ledger, *, box_name: str = "ltcm-floor", every_hours: float = 24.0, keep_days: int = 7,
                 clock: Callable[[], float] = time.time):
        self.client = client
        self.ledger = ledger
        self.box_name = box_name
        self.every_hours = float(every_hours)
        self.keep_days = int(keep_days)
        self.clock = clock

    #: After a failed checkpoint the next try waits this long, doubling with each failure in a row, up to
    #: `RETRY_MAX_SECONDS`. Sept 24, 2026, 21:31-21:45Z: Sail's checkpoint service answered 503 ("prewarm base
    #: snapshot ... DeadlineExceeded"), and because `due` read only the last SUCCESSFUL backup the House tried again at
    #: every tick -- five tries and five error alerts in 13 minutes -- against a service that was down.
    RETRY_SECONDS = 1800
    RETRY_MAX_SECONDS = 6 * 3600

    def attempts(self) -> list[dict[str, Any]]:
        """The recent backup rows, oldest first (`ops.deploy` rows with `what: backup`, ok or not)."""
        return [e.payload for e in self.ledger.read(kinds="ops.deploy", limit=200, newest=True) if e.payload.get("what") == "backup"]

    def failures_in_a_row(self) -> list[dict[str, Any]]:
        """The failed tries since the last success, oldest first (empty after a success)."""
        out: list[dict[str, Any]] = []
        for row in reversed(self.attempts()):
            if row.get("ok"):
                break
            out.append(row)
        return list(reversed(out))

    def retry_after(self, failures: int) -> float:
        """Seconds to wait after the `failures`-th failure in a row."""
        return float(min(self.RETRY_MAX_SECONDS, self.RETRY_SECONDS * 2 ** max(0, failures - 1)))

    def last(self) -> float | None:
        rows = [row for row in self.attempts() if row.get("ok")]
        return float(rows[-1]["at_epoch"]) if rows else None

    def due(self) -> bool:
        last = self.last()
        if last is not None and self.clock() - last < self.every_hours * 3600:
            return False
        failed = self.failures_in_a_row()
        if failed:
            return self.clock() - float(failed[-1]["at_epoch"]) >= self.retry_after(len(failed))
        return True

    def run(self) -> dict[str, Any]:
        """One checkpoint of the House's own box. Never raises: a failed backup is a row that says why."""
        row: dict[str, Any] = {"what": "backup", "at_epoch": self.clock(), "ledger_rows": self.ledger.head()[0]}
        try:
            boxes = [b for b in self.client.list_boxes(limit=300) if b.get("name") == self.box_name and b.get("status") == "running"]
            if len(boxes) != 1:
                raise RuntimeError(f"{len(boxes)} running boxes are named {self.box_name}")
            name = "league-" + now_iso(self.clock)[:10]
            made = self.client.checkpoint(boxes[0]["sailbox_id"], name=name, ttl_seconds=self.keep_days * 86400)
            row.update(ok=True, name=name, checkpoint_id=made.get("checkpoint_id"), box=boxes[0]["sailbox_id"])
        except Exception as exc:  # noqa: BLE001 - the floor outlives a failed backup; the alert says so
            row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}")
        self.ledger.append("ops.deploy", row, public=False)
        return row
