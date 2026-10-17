"""S3's report: counts only, for the captain (R1 is report-only: births see nothing).

Owner: R1 (plumbing: outside the deep identity). `summary` reads the look ledger and nothing else: what it returns is
integers, booleans, words, the receipt's own synthetic figures and identifiers, never a DVAL figure, a price or a
series. `write` keeps it at `<state>/equity-deep/report.json` (0600): the House's, read by the captain; no swarm
reader, no public surface and no generator reads it.

THE LINES: eligible (looked plus waiting), looked (real looks spent), passed (both keys), deep_passed and
recent_passed (each key), failed (spent and failed), under_way, the canaries (looked, passed, the band's upper end,
halted, and the report-only alarm at the receipt's own canary rate), the refusals by rule, the House's errors (versions,
and how many are refused for them), the budget (spent of 150), the ledger's state ("ok" or "damaged"), BY SEAT and BY
SOURCE (a seated version's recent key re-reads the windows S2 seated it on; a captain's seed carries a mechanism
published with DVAL in its discovery sample: the reviews of Oct 17), the level readers (the level test, report-only),
THE RECEIPT'S PREDICTION (the passes expected among the looks if no program had any edge: looks x the receipt's
zero-edge rates, beside the passes seen) and the receipt's unstated limits (`config.LIMITS`, words).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from . import config
from .gate import Ledger, band_upper


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    done = [r for r in rows if isinstance(r.get("verdict"), dict)]
    return {"looked": len(rows), "passed": sum(1 for r in done if r["verdict"].get("passed")),
            "deep_passed": sum(1 for r in done if r["verdict"].get("deep")),
            "recent_passed": sum(1 for r in done if r["verdict"].get("recent")),
            "failed": sum(1 for r in rows if r.get("verdict") == "failed")}


def summary(ledger: Ledger, *, waiting: int = 0, identity: str = "") -> dict[str, Any]:
    """The report (the module docstring). `waiting`: eligible versions whose look waits this run."""
    real = ledger.real()
    done = [r for r in real if isinstance(r.get("verdict"), dict)]
    canaries = ledger.canaries()
    fp0 = config.RECEIPT.get("fp_zero_edge")
    house_refused = sum(1 for v in ledger.refused.values() if str(v.get("why", "")).startswith("the House could not"))
    return {
        "screen": "S3", "mode": "report", "identity": str(identity)[:12], "receipt": config.RECEIPT_SHA256[:12],
        "ledger": "damaged" if ledger.damaged else "ok",
        "eligible": len(real) + int(waiting), "waiting": int(waiting), **_counts(real),
        "under_way": sum(1 for r in real if r.get("verdict") is None),
        "by_seat": {name: _counts([r for r in real if bool(r.get("seated")) == flag])
                    for name, flag in (("seated", True), ("unseated", False))},
        "by_source": {name: _counts([r for r in real if str(r.get("source") or "born") == name])
                      for name in sorted({str(r.get("source") or "born") for r in real} | {"born", "seed"})},
        "level_readers": sum(1 for r in real if r.get("level") is False),
        "canaries": {"looked": len(canaries), "passed": sum(1 for r in canaries if r["verdict"].get("deep")),
                     "band_upper": band_upper(len(canaries)) if canaries else None, "halted": ledger.halted(),
                     "alarm": ledger.canary_alarm(),
                     "alarm_band_upper": band_upper(len(canaries), config.CANARY_REFERENCE) if canaries else None},
        "refused": dict(sorted(Counter(str(v.get("why")) for v in ledger.refused.values()).items())),
        "house_errors": {"versions": len(ledger.errors), "refused": house_refused},
        "budget": {"spent": len(ledger.spent()), "of": config.LOOK_BUDGET},
        "prediction": {"zero_edge_rate": fp0,
                       "zero_edge_passes": None if fp0 is None else round(len(done) * float(fp0), 2),
                       "deep_zero_edge_rate": config.RECEIPT.get("fp_deep"),
                       "deep_zero_edge_passes": round(len(done) * float(config.RECEIPT.get("fp_deep") or 0.0), 2),
                       "recent_zero_edge_rate": config.RECEIPT.get("fp_recent"),
                       "recent_zero_edge_passes": round(len(done) * float(config.RECEIPT.get("fp_recent") or 0.0), 2),
                       "deep_passes_seen": sum(1 for r in done if r["verdict"].get("deep")),
                       "recent_passes_seen": sum(1 for r in done if r["verdict"].get("recent")),
                       "passes_seen": sum(1 for r in done if r["verdict"].get("passed"))},
        "readings": len(config.READINGS),
        "limits": list(config.LIMITS),
    }


def write(root: str | Path, report: Mapping[str, Any]) -> Path:
    """`<root>/report.json` (0600, atomic)."""
    path = Path(root) / config.REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(dict(report), handle, sort_keys=True, indent=1)
    os.replace(tmp, path)
    return path


__all__ = ["summary", "write"]
