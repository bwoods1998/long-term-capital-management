"""Private, cached Train input metadata for hypothesis selection; no remote reads or paid queries.

The operator installs an audited `input-capabilities.json` beside `swarm.sqlite`. Its image must
match the running Gym exactly. Raw file coverage never overrides the executable context contract:
the historical reader currently loads no volume publication receipts, so strategy volume is unknown.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any, Iterable

CARD_NAME = "input-capabilities.json"
MAX_BYTES = 128 * 1024


def _stamp(path: Path) -> tuple[int, ...]:
    row = path.stat()
    if not stat.S_ISREG(row.st_mode) or row.st_size > MAX_BYTES:
        raise ValueError("not a bounded regular file")
    return row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns


def _count(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError("invalid count")
    return value


@lru_cache(maxsize=16)
def _read(path: Path, stamp: tuple[int, ...]) -> dict[str, Any] | None:
    """Cache only local bytes by file revision; callers never change the returned metadata."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES or _stamp(path) != stamp:
            return None  # incomplete/in-place replacement: wait for a stable local card
        card = json.loads(raw)
        if type(card) is not dict or type(card.get("schema")) is not int or card["schema"] != 1:
            return None
        if not isinstance(card.get("image_checkpoint"), str) or not card["image_checkpoint"].strip():
            return None
        dt.datetime.fromisoformat(card["audited_at"])
        first, last = (dt.date.fromisoformat(card[key]) for key in ("train_from", "train_through"))
        if first > last:
            return None
        total = _count(card, "raw_file_count")
        volume = _count(card, "raw_volume_file_count")
        complete = _count(card, "raw_complete_volume_sessions")
        verified = _count(card, "point_in_time_verified_volume_sessions")
        if not 0 <= complete <= volume <= total or verified > volume:
            return None
        roots = card["roots"]
        if type(roots) is not dict or len(roots) > 256:
            return None
        for root, row in roots.items():
            if not re.fullmatch(r"[A-Z0-9.]{1,12}", root) or type(row) is not dict:
                return None
            sessions, raw_sessions, full, asof = (_count(row, key) for key in (
                "train_sessions", "raw_volume_sessions", "raw_complete_sessions", "asof_verified_sessions"))
            if not 0 <= full <= raw_sessions <= sessions or asof > raw_sessions:
                return None
            if raw_sessions:
                if not first <= dt.date.fromisoformat(row["raw_first"]) <= dt.date.fromisoformat(row["raw_last"]) <= last:
                    return None
            elif row.get("raw_first") is not None or row.get("raw_last") is not None:
                return None
        for key, root_key in (("raw_file_count", "train_sessions"), ("raw_volume_file_count", "raw_volume_sessions"),
                              ("raw_complete_volume_sessions", "raw_complete_sessions"),
                              ("point_in_time_verified_volume_sessions", "asof_verified_sessions")):
            if card[key] != sum(row[root_key] for row in roots.values()):
                return None
        card["digest"] = hashlib.sha256(raw).hexdigest()[:16]
        return card
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


def context(root: str | Path, image: Any, roots: Iterable[str]) -> str:
    """A bounded prompt block, refreshed on local file replacement or a different active image."""
    image = str(image or "")
    card = None
    reason = "image_unknown" if not image else "missing_or_invalid"
    if image:
        try:
            path = Path(root) / CARD_NAME
            card = _read(path, _stamp(path))
        except (OSError, ValueError):
            pass
        if card is not None and card["image_checkpoint"] != image:
            reason, card = "image_mismatch", None
    lines = ["INPUT AVAILABILITY (before hypothesis selection; cached local Train metadata, no new data/model query):"]
    if card is None:
        lines.append(f"Card: unknown ({reason}). Raw column coverage and verified as-of counts are unknown for the active "
                     "Gym image; do not reuse another image's counts or infer zero coverage.")
    else:
        total, volume = card["raw_file_count"], card["raw_volume_file_count"]
        share = f"{100 * volume / total:.2f}%" if total else "unknown share"
        lines.append(f"Card: exact image {image}; audit {card['audited_at']}; sha256 {card['digest']}. "
                     f"Audited Train span {card['train_from']} through {card['train_through']} (all card roots).")
        lines.append(f"Raw volume columns: {volume}/{total} root-sessions ({share}); "
                     f"{card['raw_complete_volume_sessions']} have all expected raw bars. "
                     f"Point-in-time verified volume sessions: {card['point_in_time_verified_volume_sessions']}. "
                     "Raw completeness is not strategy usability or evidence of edge.")
        lines.append("Requested roots (raw-volume sessions / all Train sessions; complete raw sessions; raw dates):")
        for symbol in sorted(set(str(r).upper() for r in roots))[:64]:
            row = card["roots"].get(symbol)
            if row is None:
                lines.append(f"- {symbol}: unknown (not audited in this card).")
                continue
            dates = f"{row['raw_first']} through {row['raw_last']}" if row["raw_volume_sessions"] else "none"
            lines.append(f"- {symbol}: {row['raw_volume_sessions']}/{row['train_sessions']}; "
                         f"{row['raw_complete_sessions']} complete; {dates}.")
    lines.append("Historical strategy volume: unavailable. The current historical reader loads no publication/as-of "
                 "receipts: minute_volumes, volume, daily_volumes and prior_volume remain NaN even when raw columns exist. "
                 "Choose hypotheses supported by the current inputs or record the missing-input dependency; do not "
                 "substitute finalized volume, provider daily totals or fabricated zeros. Live first-observation "
                 "volume is a separate source; complete live-session coverage remains unverified by this card.")
    return "\n".join(lines)
