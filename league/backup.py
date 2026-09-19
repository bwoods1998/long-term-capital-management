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

    def last(self) -> float | None:
        rows = [e for e in self.ledger.read(kinds="ops.deploy", limit=200, newest=True) if e.payload.get("what") == "backup" and e.payload.get("ok")]
        return float(rows[-1].payload["at_epoch"]) if rows else None

    def due(self) -> bool:
        last = self.last()
        return last is None or self.clock() - last >= self.every_hours * 3600

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
