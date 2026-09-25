"""What the agents share: a web search, a research library, a tool-request queue, the playbook.

- **Web search.** Sail's search API (real pages with excerpts), with Google News RSS as the
  fallback. The House runs the search; an agent's box has no network. Each search is charged to
  the agent that asked.
- **Web fetch.** One public page's text, read by the gateway (`POST /v1/web/fetch`,
  gateway/lib/fetch.mjs), never by the House box, whose egress stays exact-host. The gateway
  refuses private and local addresses, re-checks every redirect, forwards no credential and caps
  the text; what comes back is untrusted data from the open web.
- **Research library.** Notes any agent writes and every agent can search: a finding costs one
  agent the compute once. Notes are rows on the ledger, so the library is public and permanent.
- **Tool requests.** An agent that needs something the House does not offer (a data feed, an
  indicator, a venue feature) asks for it in plain words. Merton, as toolsmith, reads the queue
  and fulfils requests by pull request.
- **Playbook.** The graveyard's lessons: every dead agent's post-mortem, and what Merton, as
  teacher, distils from them. New agents and every research pass read it.
"""

from __future__ import annotations

import json
import socket
import time
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .ledger import HOUSE, Ledger, now_iso

SEARCH_URL = "https://api.sailresearch.com/v1/search"
MAX_NOTE_CHARS = 4000
#: Sail does not publish a price for search. The House charges this per query until the usage
#: record shows the real number; it errs high.
SEARCH_CHARGE_USD = "0.01"
#: The gateway's research web reader (gateway/lib/fetch.mjs).
FETCH_PATH = "/v1/web/fetch"
#: A page read through the gateway is charged like a search. What it costs the firm is the
#: Worker's time, well under a cent; the page's tokens are charged as the research turns that read it.
FETCH_CHARGE_USD = SEARCH_CHARGE_USD
#: The gateway refuses a longer URL; the House does not send one.
MAX_FETCH_URL_CHARS = 2048
#: The gateway's answer: at most 200,000 characters of text, JSON-escaped, and a few fields.
MAX_FETCH_ANSWER_BYTES = 2 * 1024 * 1024
#: The page fields the gateway answers (gateway/lib/fetch.mjs `webFetch`).
PAGE_FIELDS = ("url", "final_url", "status", "content_type", "title", "text", "truncated", "bytes", "fetched_at")
#: The most of each string field kept from the gateway's answer. The gateway bounds them too; what
#: reaches the model and the ledger is bounded here whatever the gateway (or a page) sent.
PAGE_FIELD_CHARS = {"url": MAX_FETCH_URL_CHARS, "final_url": MAX_FETCH_URL_CHARS, "content_type": 127, "title": 300,
                    "text": 200_000, "fetched_at": 40}
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


def gateway_fetch(gateway_url: str, token_source: Callable[[], str], *, opener: Any = None,
                  timeout: float = 40.0) -> Callable[[str, str], tuple[int, dict[str, Any]]]:
    """A `fetch(url, agent) -> (HTTP status, answer)` function over the gateway's `/v1/web/fetch`.

    The House calls the gateway as it does for everything else it may not do itself: the bearer
    token and a JSON body. An HTTP error is returned with its status, not raised; a gateway that
    cannot be reached raises (`URLError`, `OSError`), and `Commons.web_fetch` answers it."""
    endpoint = gateway_url.rstrip("/") + FETCH_PATH

    def fetch(url: str, agent: str) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            endpoint, data=json.dumps({"url": url, "agent": agent}).encode(), method="POST",
            headers={"Authorization": "Bearer " + token_source(), "Content-Type": "application/json", "User-Agent": "ltcm-floor/1.0"},
        )
        try:
            with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
                status = int(getattr(response, "status", None) or response.getcode())
                raw = response.read(MAX_FETCH_ANSWER_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, raw = int(exc.code), exc.read(MAX_FETCH_ANSWER_BYTES + 1)
        if len(raw) > MAX_FETCH_ANSWER_BYTES:
            raise ValueError("the gateway's answer is larger than a page can be")
        try:
            answer = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            answer = {}
        return status, answer if isinstance(answer, dict) else {}

    return fetch


def _page_field(key: str, value: Any) -> Any:
    """One field of a page the gateway answered, as the House keeps it: a string cut to its bound, a
    count as an int, a flag as a bool; anything else None."""
    if key == "truncated":
        return value is True
    if key in ("status", "bytes"):
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    return value[:PAGE_FIELD_CHARS[key]] if isinstance(value, str) else None


def _may_have_read(exc: BaseException) -> bool:
    """Whether a call that failed may still have had the gateway read the page. A connection never
    made (refused, no such host) did not; a timeout, a dropped answer or an answer too large to be
    a page may have, and the gateway may have spent its time on it."""
    reason = exc.reason if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError) else exc
    return not isinstance(reason, (ConnectionRefusedError, socket.gaierror))


class Commons:
    def __init__(self, ledger: Ledger, *, search: Callable[[str, int], list[dict[str, Any]]] | None = None, news: Any = None,
                 clock: Callable[[], float] = time.time, fetch: Callable[[str, str], tuple[int, dict[str, Any]]] | None = None):
        self.ledger = ledger
        self.clock = clock
        self._search = search
        self._news = news  # an ltcm.data.news.News: the keyless fallback
        self._fetch = fetch  # `gateway_fetch(...)`: None, and `web_fetch` says it is not configured

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

    # -------------------------------------------------------------- web fetch
    def web_fetch(self, url: str, agent: str) -> dict[str, Any]:
        """One public page, read by the gateway: its fields (`PAGE_FIELDS`, bounded), or `{"error"}`.

        Errors are answers, never exceptions. `judged` says whether the gateway answered about this
        URL -- a page (whatever the page's own status), a refusal of the URL, a redirect or a
        content type, or the page's host failing to answer -- as opposed to a gateway that could not
        act at all (unreachable, its token, its day's cap, busy, a Worker error). Every answer the
        gateway gives about a URL names it (`url`); nothing else does.

        `reached` says whether the gateway may have read the page, which is what the researcher
        charges and counts: a judged answer, and also a Worker error (5xx naming no url: a page
        that exhausted the Worker's CPU or memory ends that way) or a call that timed out or lost
        its answer. Only a request the gateway refused before reading (4xx naming no url: its body,
        its token, its day's cap, busy) or a connection never made is free -- otherwise a page
        that kills the Worker could be asked for again and again at no cost to anyone."""
        url = str(url or "").strip()
        if not url:
            return {"error": "give the url of one public page", "judged": False, "reached": False}
        if len(url) > MAX_FETCH_URL_CHARS:
            return {"error": f"the url is longer than {MAX_FETCH_URL_CHARS} characters", "judged": False, "reached": False}
        if not url.lower().startswith(("http://", "https://")):
            return {"error": "only a public http or https url can be read", "judged": False, "reached": False}
        if self._fetch is None:
            return {"error": "web fetch is not configured on this floor", "judged": False, "reached": False}
        try:
            status, answer = self._fetch(url, str(agent or ""))
        except Exception as exc:  # noqa: BLE001 - a gateway that cannot be reached is an answer, not a crash
            return {"error": f"the gateway could not be reached: {type(exc).__name__}", "judged": False, "reached": _may_have_read(exc)}
        answer = answer if isinstance(answer, dict) else {}
        judged = isinstance(answer.get("url"), str)
        reached = judged or (isinstance(status, int) and status >= 500)
        if status == 200 and judged and isinstance(answer.get("text"), str):
            return {**{key: _page_field(key, answer.get(key)) for key in PAGE_FIELDS}, "judged": True, "reached": True}
        error = str(answer.get("error") or f"the gateway answered HTTP {status}")[:400]
        out: dict[str, Any] = {"error": error, "gateway_status": status, "judged": judged, "reached": reached}
        for key in ("url", "final_url", "status", "content_type", "refused", "cap"):
            value = answer.get(key)
            if isinstance(value, str):
                out[key] = value[:400]
            elif isinstance(value, (int, float)):
                out[key] = value
        return out

    # ---------------------------------------------------------------- library
    def library_write(self, agent: str, title: str, text: str, tags: list[str] | None = None, *, niche: str | None = None) -> dict[str, Any]:
        title = str(title or "").strip()[:160]
        text = str(text or "").strip()[:MAX_NOTE_CHARS]
        if len(title) < 4 or len(text) < 40:
            return {"error": "a note needs a title and at least a few sentences"}
        entry = self.ledger.append(
            "library.note",
            {"title": title, "text": text, "tags": [str(t)[:30] for t in (tags or [])][:8], **({"niche": niche} if niche else {})},
            agent=agent,
        )
        return {"saved": entry.id, "title": title}

    def _notes(self) -> list[Any]:
        return list(self.ledger.iter(kinds="library.note"))

    def library_search(self, query: str, limit: int = 5, *, niche: str | None = None) -> dict[str, Any]:
        """Notes matching the query. A specialist's own niche comes first: a match there outranks
        the same match elsewhere, so a niche's library compounds for the agents that work it."""
        wanted = _words(query)
        scored = []
        for entry in self._notes():
            p = entry.payload
            have = _words(p["title"]) | _words(" ".join(p.get("tags") or [])) | _words(p["text"])
            score = len(wanted & have) + 2 * len(wanted & _words(p["title"]))
            if score:
                if niche and p.get("niche") == niche:
                    score += 3
                scored.append((score, entry.seq, entry))
        scored.sort(key=lambda row: (-row[0], -row[1]))
        return {
            "results": [
                {"id": e.id, "title": e.payload["title"], "by": e.agent, "niche": e.payload.get("niche"), "at": e.at, "excerpt": e.payload["text"][:240]}
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
        for row in self.open_requests() + self.blocked_requests():
            if row['by'] == agent and row['name'] == name:
                return {'queued': row['id'], 'status': row['status'], 'existing': True,
                        'note': 'This request remains unresolved; repeating it does not create another task.'}
        entry = self.ledger.append("tool.request", {"name": name, "description": description}, agent=agent)
        return {"queued": entry.id, "note": "the architect reads this queue; a tool that is built is announced in the playbook"}

    def _requests(self) -> list[dict[str, Any]]:
        """Fold the latest resolution, preserving old advice incorrectly labeled fulfilled."""
        rows = {}
        for entry in self.ledger.iter(kinds=('tool.request', 'tool.fulfilled', 'tool.blocked')):
            p = entry.payload
            if entry.kind == 'tool.request':
                rows[entry.id] = {'id': entry.id, 'by': entry.agent, 'at': entry.at, **p, 'status': 'open'}
                continue
            row = rows.get(p.get('request'))
            if row is None:
                continue
            legacy_blocked = (entry.kind == 'tool.fulfilled' and p.get('status') == 'answered'
                              and str(p.get('outcome') or '').lower().startswith('cannot be a pure tool'))
            blocked = entry.kind == 'tool.blocked' or legacy_blocked
            row.update(status='blocked' if blocked else 'fulfilled', outcome=p.get('outcome'),
                       owner=p.get('owner', 'house-engineering') if blocked else None,
                       reviewed_at=entry.at, legacy_advice=legacy_blocked)
        return list(rows.values())

    def blocked_requests(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Unimplemented requests have no age expiry; advice is not a shipped capability."""
        rows = [r for r in self._requests() if r['status'] == 'blocked']
        rows.sort(key=lambda r: r['at'])
        return rows[:limit] if limit else rows

    def open_requests(self, *, limit: int | None = None, stale_days: float = 3.0) -> list[dict[str, Any]]:
        """What the toolsmith is waiting on, most-asked-for first and newest before oldest.

        It used to be plain ledger order -- oldest first -- and the toolsmith was shown the first
        ten. With eighteen open on the floor's first night, the newest eight could never be seen,
        and the oldest ten were ones he had already looked at and could not build, so the window
        was clogged with the same rows for ever. A request nothing has closed after `stale_days`
        is dropped from the queue rather than blocking it: an agent that still needs the thing
        will ask again, and its asking again is the signal that it matters.

        `want` counts how many different agents have asked for the same tool by name, which is the
        best evidence the floor produces about what is actually missing -- six agents across four
        desks asked for the price behind their strikes before anyone noticed."""
        oldest = now_iso(lambda: self.clock() - stale_days * 86400) if stale_days else ""
        rows = [r for r in self._requests() if r['status'] == 'open' and r['at'] >= oldest]
        want: dict[str, set[str]] = {}
        for row in rows:
            name = str(row.get("name") or "")
            want.setdefault(name, set()).add(row['by'])
        for row in rows:
            row["asked_by_agents"] = len(want[str(row.get("name") or "")])
        rows.sort(key=lambda row: row["at"], reverse=True)          # newest first
        rows.sort(key=lambda row: -row["asked_by_agents"])           # then what most agents want
        return rows[:limit] if limit else rows

    def fulfil(self, request_id: str, outcome: str, *, change: str | None = None) -> None:
        self.ledger.append("tool.fulfilled", {"request": request_id, "outcome": str(outcome)[:1200], "change": change}, agent=HOUSE)

    def block(self, request_id: str, outcome: str, *, owner: str, change: str | None = None) -> None:
        """Answer a request with the rule that keeps it from being built (`tool.blocked`, as `fulfil` answers
        one that shipped): `owner` is who could unlock it -- "owner" for a key, a login or a paid plan,
        "no-source" when nothing that passes the data-host rule publishes it (league/open_feeds.py, Sept 25, 2026)."""
        self.ledger.append("tool.blocked", {"request": request_id, "outcome": str(outcome)[:1200], "change": change,
                                            "status": "blocked", "owner": str(owner)}, agent=HOUSE)

    # ---------------------------------------------------------------- playbook
    def playbook_add(self, title: str, text: str, *, source: str, agent: str = HOUSE) -> str:
        entry = self.ledger.append(
            "playbook.entry", {"title": str(title)[:160], "text": str(text)[:MAX_NOTE_CHARS], "source": source}, agent=agent
        )
        return entry.id

    def playbook_read(self, query: str = "", limit: int = 8, *, keep: Callable[[Any], bool] | None = None) -> dict[str, Any]:
        """The newest `limit` playbook entries matching `query`. `keep` (Sept 25, 2026): the entries this
        reader may see, when some are held back from it (the teacher's control arm, league/research_gate.py
        `ResearchGate.withheld`); a `keep` that raises holds nothing back."""
        entries = list(self.ledger.iter(kinds="playbook.entry"))
        if keep is not None:
            def kept(entry: Any) -> bool:
                try:
                    return bool(keep(entry))
                except Exception:  # noqa: BLE001 - the control arm must never cost a reader the playbook
                    return True
            entries = [e for e in entries if kept(e)]
        wanted = _words(query)
        if wanted:
            entries = [e for e in entries if wanted & (_words(e.payload["title"]) | _words(e.payload["text"]))]
        entries = entries[-max(1, min(int(limit), 20)):]
        return {"entries": [{"title": e.payload["title"], "text": e.payload["text"], "source": e.payload.get("source"), "at": e.at} for e in entries]}
