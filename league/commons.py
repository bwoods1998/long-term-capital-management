"""What the agents share: a web search, a research library, a tool-request queue, the playbook.

- **Web search.** Sail's search API (real pages with excerpts), with Google News RSS as the
  fallback. The House runs the search; an agent's box has no network. Each search is charged to
  the agent that asked.
- **Research library.** Notes any agent writes and every agent can search: a finding costs one
  agent the compute once. Notes are rows on the ledger, so the library is public and permanent.
- **Tool requests.** An agent that needs something the House does not offer (a data feed, an
  indicator, a venue feature) asks for it in plain words. Astra, as toolsmith, reads the queue
  and fulfils requests by pull request.
- **Playbook.** The graveyard's lessons: every dead agent's post-mortem, and what Astra, as
  teacher, distils from them. New agents and every research pass read it.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .ledger import HOUSE, Ledger

SEARCH_URL = "https://api.sailresearch.com/v1/search"
MAX_NOTE_CHARS = 4000
#: Sail does not publish a price for search. The House charges this per query until the usage
#: record shows the real number; it errs high.
SEARCH_CHARGE_USD = "0.01"
WORD = re.compile(r"[a-z0-9]{3,}")


def _words(text: str) -> set[str]:
    return set(WORD.findall(str(text or "").lower()))


def sail_search(key_source: Callable[[], str], *, opener: Any = None, timeout: float = 45.0) -> Callable[[str, int], list[dict[str, Any]]]:
    """A `search(query, limit)` function over Sail's search API."""

    def search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        body = json.dumps({"queries": [query[:300]], "objective": query[:300], "mode": "turbo", "max_results": max(1, min(int(limit), 10))}).encode()
        request = urllib.request.Request(
            SEARCH_URL, data=body, method="POST",
            headers={"Authorization": "Bearer " + key_source(), "Content-Type": "application/json", "User-Agent": "ltcm-floor/1"},
        )
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            payload = json.load(response)
        rows = []
        for row in payload.get("results") or []:
            excerpt = " ".join(str(x) for x in (row.get("excerpts") or []))[:1200]
            rows.append({"title": str(row.get("title") or "")[:200], "url": str(row.get("url") or "")[:400], "published": row.get("published"), "excerpt": excerpt})
        return rows

    return search


class Commons:
    def __init__(self, ledger: Ledger, *, search: Callable[[str, int], list[dict[str, Any]]] | None = None, news: Any = None):
        self.ledger = ledger
        self._search = search
        self._news = news  # an ltcm.data.news.News: the keyless fallback

    # ------------------------------------------------------------- web search
    def web_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        query = str(query or "").strip()[:300]
        if not query:
            return {"error": "give a query"}
        if self._search is not None:
            try:
                return {"source": "web", "results": self._search(query, limit)}
            except (urllib.error.URLError, OSError, ValueError) as exc:
                failure = f"{type(exc).__name__}"
        else:
            failure = "not configured"
        if self._news is not None:
            try:
                rows = self._news.search(query, limit=limit)
                return {"source": "news", "note": f"web search unavailable ({failure}); these are news headlines", "results": rows}
            except Exception as exc:  # noqa: BLE001 - a search that fails is an answer, not a crash
                return {"error": f"search failed: {type(exc).__name__}"}
        return {"error": f"search failed: {failure}"}

    # ---------------------------------------------------------------- library
    def library_write(self, agent: str, title: str, text: str, tags: list[str] | None = None) -> dict[str, Any]:
        title = str(title or "").strip()[:160]
        text = str(text or "").strip()[:MAX_NOTE_CHARS]
        if len(title) < 4 or len(text) < 40:
            return {"error": "a note needs a title and at least a few sentences"}
        entry = self.ledger.append(
            "library.note",
            {"title": title, "text": text, "tags": [str(t)[:30] for t in (tags or [])][:8]},
            agent=agent,
        )
        return {"saved": entry.id, "title": title}

    def _notes(self) -> list[Any]:
        return list(self.ledger.iter(kinds="library.note"))

    def library_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        wanted = _words(query)
        scored = []
        for entry in self._notes():
            p = entry.payload
            have = _words(p["title"]) | _words(" ".join(p.get("tags") or [])) | _words(p["text"])
            score = len(wanted & have) + 2 * len(wanted & _words(p["title"]))
            if score:
                scored.append((score, entry.seq, entry))
        scored.sort(key=lambda row: (-row[0], -row[1]))
        return {
            "results": [
                {"id": e.id, "title": e.payload["title"], "by": e.agent, "at": e.at, "excerpt": e.payload["text"][:240]}
                for _, _, e in scored[: max(1, min(int(limit), 10))]
            ]
        }

    def library_read(self, ref: str) -> dict[str, Any]:
        ref = str(ref or "").strip()
        for entry in reversed(self._notes()):
            if entry.id == ref or entry.payload["title"].lower() == ref.lower():
                return {"id": entry.id, "title": entry.payload["title"], "by": entry.agent, "at": entry.at, "text": entry.payload["text"], "tags": entry.payload.get("tags") or []}
        return {"error": "no such note; search the library first"}

    # ----------------------------------------------------------- tool requests
    def request_tool(self, agent: str, name: str, description: str) -> dict[str, Any]:
        name = re.sub(r"[^a-z0-9_]+", "_", str(name or "").lower()).strip("_")[:40]
        description = str(description or "").strip()[:1200]
        if not name or len(description) < 20:
            return {"error": "name the tool and say what it should do and why you need it"}
        entry = self.ledger.append("tool.request", {"name": name, "description": description}, agent=agent)
        return {"queued": entry.id, "note": "the architect reads this queue; a tool that is built is announced in the playbook"}

    def open_requests(self) -> list[dict[str, Any]]:
        done = {e.payload.get("request") for e in self.ledger.iter(kinds="tool.fulfilled")}
        return [
            {"id": e.id, "by": e.agent, "at": e.at, **e.payload}
            for e in self.ledger.iter(kinds="tool.request")
            if e.id not in done
        ]

    def fulfil(self, request_id: str, outcome: str, *, change: str | None = None) -> None:
        self.ledger.append("tool.fulfilled", {"request": request_id, "outcome": str(outcome)[:1200], "change": change}, agent=HOUSE)

    # ---------------------------------------------------------------- playbook
    def playbook_add(self, title: str, text: str, *, source: str, agent: str = HOUSE) -> str:
        entry = self.ledger.append(
            "playbook.entry", {"title": str(title)[:160], "text": str(text)[:MAX_NOTE_CHARS], "source": source}, agent=agent
        )
        return entry.id

    def playbook_read(self, query: str = "", limit: int = 8) -> dict[str, Any]:
        entries = list(self.ledger.iter(kinds="playbook.entry"))
        wanted = _words(query)
        if wanted:
            entries = [e for e in entries if wanted & (_words(e.payload["title"]) | _words(e.payload["text"]))]
        entries = entries[-max(1, min(int(limit), 20)):]
        return {"entries": [{"title": e.payload["title"], "text": e.payload["text"], "source": e.payload.get("source"), "at": e.at} for e in entries]}
