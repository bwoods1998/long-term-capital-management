"""The league's memory, kept somewhere other than the one disk it lives on.

Everything an agent is lives on the House's ledger: its code, its record, its journal, its family's
trials. The ledger is one SQLite file on one Sailbox. A superstar that took a fortnight to find
must not be lost to a dead disk, so once a day the House checkpoints its own box with Sail (a
snapshot of the whole disk, kept by Sail outside the box) under a rolling name, each kept for a
week. Restoring is `python3 scripts/floor_box.py restore`-style work for the owner: a new box from
the newest checkpoint comes back with the ledger, the agents' state and the promoted release.

The snapshot holds what the box holds, including its three credentials (never a venue key), and
stays inside the owner's Sail account, like the checkpoints `floor_box.py checkpoint` takes.

A failed checkpoint is tried again after a backoff (`RETRY_SECONDS`, doubling to `RETRY_MAX_SECONDS`).
When Sail is why it failed (`watchdog.service_failed`: a 5xx, a 429, a timeout, a dropped
connection), the row and every alert about it carry `environment: "sail"`, and the watchdog never
rolls a release back for them (H2, Sept 25, 2026). `notice` is what the House says about each
attempt: ONE error when a run of failures begins, a warning at each later backoff step, an info
with the outage's length when a checkpoint succeeds again. A failure that is this code's own
(anything `service_failed` says no to) is an unmarked error every time, as before.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .ledger import Ledger, now_iso
from .watchdog import ENVIRONMENT, environment


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

    def run(self, *, closing: Callable[[], bool] | None = None) -> dict[str, Any]:
        """One checkpoint of the House's own box. Never raises: a failed backup is a row that says why.

        The row carries `environment: "sail"` when Sail is why it failed (`watchdog.service_failed`), and
        `during_shutdown` when `closing()` says the House began shutting down while the checkpoint was in
        flight: such a failure is recorded, and `notice` never makes it an error (Sept 25, 2026, 00:04:42-
        00:05:55Z: the OLD House's backup, in flight at the owner's promotion, failed 73 s later inside the
        new release's watch and rolled it back)."""
        row: dict[str, Any] = {"what": "backup", "at_epoch": self.clock(), "ledger_rows": self.ledger.head()[0]}
        try:
            boxes = [b for b in self.client.list_boxes(limit=300) if b.get("name") == self.box_name and b.get("status") == "running"]
            if len(boxes) != 1:
                raise RuntimeError(f"{len(boxes)} running boxes are named {self.box_name}")
            name = "league-" + now_iso(self.clock)[:10]
            made = self.client.checkpoint(boxes[0]["sailbox_id"], name=name, ttl_seconds=self.keep_days * 86400)
            row.update(ok=True, name=name, checkpoint_id=made.get("checkpoint_id"), box=boxes[0]["sailbox_id"])
        except Exception as exc:  # noqa: BLE001 - the floor outlives a failed backup; the alert says so
            row.update(ok=False, error=f"{type(exc).__name__}: {str(exc)[:200]}", **environment("sail", exc))
            if closing is not None and closing():
                row["during_shutdown"] = True
        self.ledger.append("ops.deploy", row, public=False)
        return row

    def notice(self, row: dict[str, Any], before: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]] | None:
        """What the House says about one attempt `row`, given the failures in a row BEFORE it (oldest first,
        `failures_in_a_row()` read before the attempt): `(level, text, payload)`, or None for a routine success.

        Sept 24-25, 2026: Sail's checkpoint API answered 503 from 21:31:55Z to 01:55Z, 73 failed tries, and
        every one was an error alert, so every release promoted in those hours was rolled back on one. Now:

        - a Sail failure that begins a run of failures is ONE error alert, marked `environment: "sail"`;
        - a later one in the same run (the backoff's 30 min, 1 h, 2 h, 4 h, then every 6 h) is a warning,
          marked the same way; every alert carries `began_at` (the run's first failure) and `failures`
          (the run's length);
        - a failure that came back while the House was shutting down (`during_shutdown`) is a warning,
          never the run's error: the next House announces the run if it goes on;
        - a failure that is this code's own is an unmarked error every time, its `began_at` the first of
          the House's own failures in a row, so a release that breaks the backup still answers for it;
        - a success after failures is an info alert with the outage's length (`outage_seconds`)."""
        if row.get("ok"):
            if not before:
                return None
            began = float(before[0].get("at_epoch") or row["at_epoch"])
            lasted = max(0.0, float(row["at_epoch"]) - began)
            payload: dict[str, Any] = {"began_at": _iso(began), "failures": len(before), "outage_seconds": round(lasted, 1)}
            marker = next((r[ENVIRONMENT] for r in reversed(before) if r.get(ENVIRONMENT)), None)
            if marker:
                payload[ENVIRONMENT] = marker
            return ("info", f"The daily backup of the House box succeeded again: the outage lasted {_span(lasted)} "
                            f"({len(before)} failed tr{'y' if len(before) == 1 else 'ies'} since {_iso(began)}).", payload)
        failed = [*before, row]
        marker = row.get(ENVIRONMENT)
        began = failed[0]
        if not marker:  # the House's own failures began at the first of them since the last of any other kind
            for earlier in reversed(failed):
                if earlier.get(ENVIRONMENT):
                    break
                began = earlier
        began_at = _iso(float(began.get("at_epoch") or row["at_epoch"]))
        wait = int(self.retry_after(len(failed)) // 60)
        payload = {"began_at": began_at, "failures": len(failed), **({ENVIRONMENT: marker} if marker else {})}
        tries = f"{len(failed)} tr{'y' if len(failed) == 1 else 'ies'} in a row"
        if row.get("during_shutdown"):
            return ("warning", f"The daily backup of the House box failed while the House was shutting down ({row.get('error')}); "
                               f"{tries}. The next House tries again.", payload)
        if not marker:
            return ("error", f"The daily backup of the House box failed ({row.get('error')}); {tries} since {began_at}, the next in "
                             f"{wait} minutes. The ledger lives on one disk until one succeeds.", payload)
        if any(not earlier.get("during_shutdown") for earlier in before):  # the run has been announced
            return ("warning", f"Sail still fails the daily backup of the House box ({row.get('error')}); {tries} since "
                               f"{began_at}, the next in {wait} minutes.", payload)
        return ("error", f"The daily backup of the House box failed on Sail's side ({row.get('error')}). The next try is in {wait} "
                         f"minutes, backing off to {self.RETRY_MAX_SECONDS // 3600} hours; the ledger lives on one disk until one "
                         "succeeds. A warning follows at each later try, and an info when one works again.", payload)


def _iso(epoch: float) -> str:
    return now_iso(lambda: float(epoch))


def _span(seconds: float) -> str:
    """`2 h 24 min`, `14 min`, `40 s`."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"
