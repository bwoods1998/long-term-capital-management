"""Alpaca (Benzinga) news for the event lane: `GET v1beta1/news` through the gateway (gateway G1 signs that path).

A row is stored once per article id with the time the lane first stored it. KNOWABLE = created_at + 2 minutes
(PREREG-EVL-1 section 3). `live` is 1 when the recorder stored the article within 10 minutes of its creation, else 0
(backfilled); a backfilled article edited more than 10 minutes after publication is excluded at selection
(league.events.programs.news_in). Headlines are licensed: they stay in the private store and never reach the site.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Iterable

from . import store as S

PATH = "/v1/alpaca/v1beta1/news"
KNOWABLE_LAG = dt.timedelta(minutes=2)
LIVE_WITHIN = dt.timedelta(minutes=10)
PAGE = 50
MAX_PAGES = 400


def record(store: S.Store, gw: Any, start: dt.datetime, end: dt.datetime, *, now: dt.datetime | None = None) -> dict[str, int]:
    """Store every article created in [start, end) (oldest first, paginated). Idempotent by article id."""
    now = now or S.utc_now()
    token = None
    seen = stored = 0
    for _ in range(MAX_PAGES):
        page = gw.get_json(PATH, {"start": S.iso(start), "end": S.iso(min(end, now)), "limit": PAGE, "sort": "asc",
                                  "include_content": "false", "page_token": token})
        rows = (page or {}).get("news") or []
        with store.tx() as db:
            for a in rows:
                seen += 1
                created = S.parse_iso(str(a["created_at"]))
                updated = S.parse_iso(str(a["updated_at"])) if a.get("updated_at") else None
                live = int(now - created <= LIVE_WITHIN)
                cur = db.execute("INSERT OR IGNORE INTO news(id, created_at, updated_at, received_at, knowable_at, source, "
                                 "headline, summary, symbols, live) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (str(a["id"]), S.iso(created), S.iso(updated) if updated else None, S.iso(now),
                                  S.iso(created + KNOWABLE_LAG), a.get("source"), a.get("headline"), a.get("summary"),
                                  json.dumps([str(s).upper() for s in a.get("symbols") or []]), live))
                stored += cur.rowcount
        token = (page or {}).get("next_page_token")
        if not token:
            break
    return {"seen": seen, "stored": stored}


def latest_created(store: S.Store) -> dt.datetime | None:
    row = store.db.execute("SELECT max(created_at) FROM news").fetchone()
    return S.parse_iso(row[0]) if row and row[0] else None


__all__ = ["record", "latest_created", "PATH"]
