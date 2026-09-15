"""The desk runtime: build the context, run the tool-calling loop, emit everything.

`Desk.run_session` is the only entry point the service needs. It assembles a prompt from the
manifest, the playbook, the desk's own memory and its current book, then runs the Responses API
loop until the model calls `end_session`, stops calling tools, runs out of turns, hits the budget
or returns an incomplete response. Every step is written to the event log as it happens.

Identity is derived everywhere, so a crash and a retry inside the same minute reproduce the same
session id, the same request keys, the same event ids and the same order intent ids. Nothing is
duplicated by a restart.

Two small stores live here because they are the desk's own state rather than the service's:
`PlaybookStore` (the versioned markdown file the desk is allowed to edit) and `MemoryStore` (the
notes it carries between sessions).

Standard library only.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

from . import tools as tools_module
from .events import EventConflict, EventLog, canonical, now_iso
from .manifest import DeskManifest
from .provider import BudgetExceeded, Provider, ProviderError
from .tools import ToolContext, ToolSession

ZERO = Decimal(0)
# Triggers name a cadence slot or a calendar event: "market_open", "cadence:09:45",
# "earnings_release". They land inside a session id, so the character set stays narrow.
TRIGGER = re.compile(r"^[a-z][a-z0-9_:.\-]{0,48}$")
MAX_PLAYBOOK_CHARS = 20_000
MAX_DIFF_CHARS = 20_000
MEMORY_POOL = 500  # rows scanned before ranking

HEADER = """You are an autonomous portfolio manager on the Long Term Capital Management floor.

What you are
- You research, argue and trade a small book on your own. There is no human in the loop during a
  session, and no one will correct a lazy answer before it costs money.
- You act only through the tools listed below. You have no shell, no network and no filesystem.
- The date in the session header is today's real date, and your training data ends before it.
  The quotes, bars, filings, news and markets you read through your tools are live and real:
  nothing here is a simulation, a backtest or a test environment. When the world differs from
  what you remember, the world is right.

What you may do
- Read market data, filings, news and your own memory; write memory entries and public memos;
  edit your playbook; propose orders; cancel your own working orders; end the session.

What you may not do
- You may not exceed your mandate, your instrument rules or your limits. They are enforced in
  code by a deterministic risk engine that runs after every proposal and that you cannot reach,
  influence or talk out of a decision. Do not try to evade them, and do not argue with a
  rejection: read the reasons, fix the order or drop the idea.
- You may not publish credentials, account numbers, personal data or licensed real-time quotes.
- You may not claim a fact you have not read this session or recorded in memory with a source.

Everything you write is public
- Your reasoning summaries, tool calls, memos, playbook edits and orders are published on a
  public site as they happen, with your name on them. Write as if a skeptical reader is watching,
  because one is.

How to work
- Cite sources: name the filing, the release or the URL a claim comes from, and prefer a document
  you read this session over a memory of one.
- Say plainly when the data cannot answer the question, and end the session rather than trade to
  look busy.
- Every order proposal names the catalyst, the expected holding period and the exit rule.
- Leave a memo at the end of every session, trade or no trade: what you looked at, your
  number, why you acted or passed. It is your public record and your post-mortem's raw
  material; a session without a memo is a session nobody can learn from.
- When you price an event contract, record the probability with record_forecast whether or
  not you trade it; your calibration is scored at resolution and read back to you.
- When you have run_code, test a rule on real history before you trust it, and save what
  works in your toolbox; your children inherit it.
- Call end_session when you are done. Unused turns cost nothing; a bad trade costs real money."""

#: Appended to the header for a desk on real capital.
LIVE_NOTE = """Your capital is real
- Every order you propose that passes the risk engine and the critic is sent to a real venue and
  settles in a real account. The money is the owner's. Losses are permanent and public.
- You are on a live sleeve because a shadow desk before you earned it. The committee can take it
  back: a mandate breach or a drawdown past your limit cuts you to zero and returns you to a
  shadow book."""

#: Appended to the header for a desk whose orders are scored rather than sent.
SHADOW_NOTE = """Your book is a shadow book, and it is how you earn real capital
- You are not funded. No order you propose is ever sent to a venue, and no money moves.
- Every order you propose is still scored as though it were: it passes the same risk engine as a
  live desk's, it fills at the real venue's quote, and it is charged the real venue's fees. Your
  equity, your return and your drawdown are hypothetical, and they are published as hypothetical.
- That score is the whole point. The committee's published gate reads your forward record -- days
  live, independent decisions, cost-adjusted excess return, drawdown inside mandate, no circuit
  breakers -- and a desk that passes it takes over a live sleeve and starts trading the owner's
  money. A desk that stays below its family's median long enough is retired and replaced.
- So trade the shadow book exactly as you would trade real money. Padding the record with trades
  you could not defend buys you nothing: the gate reads the record you actually leave, and the
  desk that takes the sleeve is the one whose hypothetical book would have been worth owning."""


def header_for(manifest: DeskManifest) -> str:
    """The system header for one desk: the shared rules, then what its capital actually is."""
    return HEADER + "\n\n" + (LIVE_NOTE if manifest.live else SHADOW_NOTE)


# --------------------------------------------------------------------------- results


@dataclass(frozen=True)
class SessionResult:
    session_id: str
    turns: int
    requests: int
    cost_usd: Decimal
    intents: list[dict[str, Any]]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turns": self.turns,
            "requests": self.requests,
            "cost_usd": format(self.cost_usd, "f"),
            "intents": list(self.intents),
            "reason": self.reason,
        }


class PlaybookError(ValueError):
    """A playbook edit that is refused before anything is written."""


# --------------------------------------------------------------------------- playbooks


class PlaybookStore:
    """The desk's markdown playbook plus its version history.

    The live file is `playbooks/<id>.md` (whatever the manifest names) and every version is kept
    under `playbooks/history/<id>/v<N>.md`. The first edit seeds the history with the text that
    was already on disk as v1, so v<N> always names a text that really existed and the highest
    numbered history file always equals the live file.
    """

    def __init__(self, repo_root: str | Path, manifest: DeskManifest):
        self.root = Path(repo_root)
        self.desk_id = manifest.id
        relative = Path(manifest.playbook)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "playbooks":
            raise PlaybookError("the playbook path must stay under playbooks/")
        self.path = self.root / relative
        self.history = self.root / "playbooks" / "history" / manifest.id
        self._lock = threading.RLock()

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def versions(self) -> list[int]:
        if not self.history.is_dir():
            return []
        found = []
        for child in self.history.glob("v*.md"):
            digits = child.stem[1:]
            if digits.isdigit():
                found.append(int(digits))
        return sorted(found)

    def version_text(self, version: int) -> str:
        return (self.history / f"v{int(version)}.md").read_text(encoding="utf-8")

    def current_version(self) -> int:
        found = self.versions()
        return found[-1] if found else 1

    def write(self, text: Any, reason: Any) -> dict[str, Any]:
        """Replace the playbook, keeping the old text in history. Returns version, diff, reason."""
        if not isinstance(text, str) or not text.strip():
            raise PlaybookError("the playbook cannot be empty")
        if len(text) > MAX_PLAYBOOK_CHARS:
            raise PlaybookError(
                f"the playbook is {len(text)} characters; the limit is {MAX_PLAYBOOK_CHARS}"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise PlaybookError("a playbook edit needs a reason, which is published with the diff")
        if len(reason) > 500:
            raise PlaybookError("the reason must be at most 500 characters")
        body = text if text.endswith("\n") else text + "\n"
        with self._lock:
            previous = self.read()
            if body == previous:
                raise PlaybookError("the new playbook is identical to the current one")
            self.history.mkdir(parents=True, exist_ok=True)
            existing = self.versions()
            if not existing:
                # Seed the history with what was already on disk, so v1 is a real text.
                (self.history / "v1.md").write_text(previous, encoding="utf-8")
                existing = [1]
            version = existing[-1] + 1
            (self.history / f"v{version}.md").write_text(body, encoding="utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(body, encoding="utf-8")
        return {
            "version": version,
            "previous_version": existing[-1],
            "diff": unified_diff(previous, body, existing[-1], version),
            "reason": reason.strip(),
            "chars": len(body),
            "path": str(Path(self.path).relative_to(self.root)),
        }


def unified_diff(before: str, after: str, from_version: int, to_version: int) -> str:
    """A capped unified diff between two playbook texts, for `desk.playbook_updated`."""
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"v{from_version}",
        tofile=f"v{to_version}",
        lineterm="",
        n=3,
    )
    text = "\n".join(lines)
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + "\n… diff truncated"
    return text


class _PlaybookRouter:
    """Wraps the service's `ToolContext` so playbook reads and writes use the versioned store."""

    def __init__(self, ctx: Any, store: PlaybookStore):
        self._ctx = ctx
        self._store = store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx, name)

    def bind_session(self, session_id: str | None) -> None:
        """Tell the underlying context which session is running, so the events it writes on
        the desk's behalf (memos, memory entries) carry the session id rather than None."""
        if hasattr(self._ctx, "session_id"):
            try:
                setattr(self._ctx, "session_id", session_id)
            except Exception:
                pass

    def playbook_read(self) -> str:
        return self._store.read()

    def playbook_write(self, text: str, reason: str) -> dict[str, Any]:
        try:
            return self._store.write(text, reason)
        except PlaybookError as exc:
            raise tools_module.ToolError(str(exc)) from None


# --------------------------------------------------------------------------- memory

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL,
    at TEXT NOT NULL,
    symbol TEXT,
    kind TEXT,
    text TEXT NOT NULL,
    tags TEXT,
    source_event TEXT
);
CREATE INDEX IF NOT EXISTS entries_desk ON entries(desk_id, at DESC);
"""

_WORD = re.compile(r"[a-z0-9][a-z0-9.\-]*")


def _terms(query: Any) -> list[str]:
    if not isinstance(query, str):
        return []
    seen: list[str] = []
    for word in _WORD.findall(query.lower()):
        word = word.strip(".-")
        if len(word) >= 2 and word not in seen:
            seen.append(word)
    return seen[:12]


class MemoryStore:
    """The desk's durable notes. Ranking is keyword hits first, recency second, and nothing else."""

    def __init__(self, path: str | Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False, timeout=30
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(MEMORY_SCHEMA)

    def write(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Store one note. The id is derived, so replaying a session never duplicates a row."""
        if not isinstance(entry, dict):
            raise ValueError("a memory entry must be an object")
        desk_id = entry.get("desk_id")
        text = entry.get("text")
        if not isinstance(desk_id, str) or not desk_id:
            raise ValueError("a memory entry needs a desk_id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("a memory entry needs text")
        if len(text) > 4000:
            raise ValueError("a memory entry must be at most 4000 characters")
        at = entry.get("at") if isinstance(entry.get("at"), str) else now_iso(self.clock)
        tags = entry.get("tags") or []
        if not isinstance(tags, list):
            raise ValueError("tags must be a list")
        source = entry.get("source_event") or entry.get("session_id")
        row = {
            "id": entry.get("id") or _memory_id(desk_id, source, entry.get("kind"), text),
            "desk_id": desk_id,
            "at": at,
            "symbol": entry.get("symbol") if isinstance(entry.get("symbol"), str) else None,
            "kind": entry.get("kind") if isinstance(entry.get("kind"), str) else "note",
            "text": text.strip(),
            "tags": canonical([str(t)[:30] for t in tags[:12]]),
            "source_event": source if isinstance(source, str) else None,
        }
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO entries (id, desk_id, at, symbol, kind, text, tags,"
                " source_event) VALUES (:id, :desk_id, :at, :symbol, :kind, :text, :tags,"
                " :source_event)",
                row,
            )
            stored = self._db.execute("SELECT * FROM entries WHERE id = ?", (row["id"],)).fetchone()
        return _memory_dict(stored)

    def read(
        self, query: str = "", limit: int = 20, *, desk_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Rank by keyword hits, then by recency. An empty query is pure recency."""
        limit = max(1, min(int(limit), 500))
        with self._lock:
            if desk_id is None:
                rows = self._db.execute(
                    "SELECT * FROM entries ORDER BY at DESC, id DESC LIMIT ?", (MEMORY_POOL,)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM entries WHERE desk_id = ? ORDER BY at DESC, id DESC LIMIT ?",
                    (desk_id, MEMORY_POOL),
                ).fetchall()
        terms = _terms(query)
        ranked = []
        for recency, row in enumerate(rows):  # 0 is the most recent
            haystack = " ".join(
                str(row[field] or "") for field in ("symbol", "kind", "text", "tags")
            ).lower()
            hits = sum(1 for term in terms if term in haystack)
            ranked.append((-hits, recency, row))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [_memory_dict(row) for _, _, row in ranked[:limit]]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """One entry by id, or None. An importer uses this to skip what it already wrote."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM entries WHERE id = ?", (str(entry_id),)
            ).fetchone()
        return _memory_dict(row) if row is not None else None

    def count(self, desk_id: str | None = None) -> int:
        with self._lock:
            if desk_id is None:
                return self._db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            return self._db.execute(
                "SELECT COUNT(*) FROM entries WHERE desk_id = ?", (desk_id,)
            ).fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()


def _memory_id(desk_id: str, source: Any, kind: Any, text: str) -> str:
    material = "|".join([desk_id, str(source or ""), str(kind or ""), text.strip()])
    return "mem-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _memory_dict(row: Any) -> dict[str, Any]:
    if row is None:  # pragma: no cover - the insert above always leaves a row
        return {}
    try:
        tags = json.loads(row["tags"]) if row["tags"] else []
    except ValueError:  # pragma: no cover - tags are written canonically
        tags = []
    return {
        "id": row["id"],
        "desk_id": row["desk_id"],
        "at": row["at"],
        "symbol": row["symbol"],
        "kind": row["kind"],
        "text": row["text"],
        "tags": tags,
        "source_event": row["source_event"],
    }


# --------------------------------------------------------------------------- the desk


class Desk:
    """One desk's runtime. Stateless between sessions except for the stores it is given."""

    def __init__(
        self,
        manifest: DeskManifest,
        provider: Provider,
        ctx: ToolContext,
        log: EventLog,
        *,
        clock: Callable[[], float] = time.time,
        repo_root: str | Path = ".",
    ):
        self.manifest = manifest
        self.provider = provider
        self.log = log
        self.clock = clock
        self.repo_root = Path(repo_root)
        self.playbooks = PlaybookStore(repo_root, manifest)
        self.ctx = _PlaybookRouter(ctx, self.playbooks)
        self.tool_schemas = tools_module.schemas_for(manifest)

    # ------------------------------------------------------------------ identity
    def session_id(self, trigger: str) -> str:
        """`<desk>:<YYYYMMDD-HHMM>:<trigger>` in UTC, so a retry in the same minute reuses it."""
        if not isinstance(trigger, str) or not TRIGGER.match(trigger):
            raise ValueError(f"invalid trigger {trigger!r}")
        stamp = time.strftime("%Y%m%d-%H%M", time.gmtime(self.clock()))
        return f"{self.manifest.id}:{stamp}:{trigger}"

    # ------------------------------------------------------------------ prompt
    def build_prompt(self, session_id: str, trigger: str) -> list[dict[str, Any]]:
        """The two input items that open a session: stable context first, then today's state."""
        stable = "\n\n".join(
            [
                header_for(self.manifest),
                "# Your desk\n" + self._manifest_block(),
                "# Your playbook\n"
                + (self.playbooks.read().strip() or "(the playbook is empty)"),
            ]
        )
        return [
            {"role": "system", "content": stable},
            {"role": "user", "content": self._state_block(session_id, trigger)},
        ]

    def _manifest_block(self) -> str:
        m = self.manifest
        lines = [
            f"Name: {m.name} ({m.id}, generation {m.generation})",
            f"Persona: {m.persona}",
            f"Mandate: {m.mandate}",
            f"Capital: {m.capital_mode}, ${format(m.capital_usd, 'f')}"
            + ("" if m.live else " (notional: a scoring budget, not money)"),
            f"Venue: {m.market_venue}"
            + ("" if m.live else " -- the venue you would trade on; orders are scored, never sent"),
            "Instruments: "
            + ", ".join(m.instruments.asset_classes)
            + (f"; allowed symbols: {', '.join(m.instruments.allow)}" if m.instruments.allow else "")
            + (f"; never: {', '.join(m.instruments.deny)}" if m.instruments.deny else "")
            + f"; minimum price ${format(m.instruments.min_price, 'f')}"
            + f"; shorting {'allowed' if m.instruments.allow_short else 'not allowed'}",
            "Limits (enforced in code, not by you): "
            + f"position {_pct(m.limits.max_position_pct)} of desk equity, "
            + f"gross {_pct(m.limits.max_gross_pct)}, "
            + f"single order {_pct(m.limits.max_order_notional_pct)}, "
            + f"daily loss stop {_pct(m.limits.max_daily_loss_pct)}, "
            + f"{m.limits.max_orders_per_day} orders per day, "
            + f"limit price within {_pct(m.limits.max_limit_deviation_pct)} of the reference.",
            f"Tools you may call: {', '.join(m.tools)}, end_session",
            f"Session budget: at most {m.model.max_turns} turns; the floor enforces a daily "
            f"model spend cap of ${format(m.budget_usd_per_day, 'f')} for this desk.",
        ]
        return "\n".join(lines)

    def _state_block(self, session_id: str, trigger: str) -> str:
        parts = [f"# Session {session_id}", f"Trigger: {trigger}", f"Now: {now_iso(self.clock)} UTC"]
        memories = self._safe(lambda: self.ctx.memory_read("", self.manifest.memory_limit), [])
        parts.append("\n# Your memory (most relevant first)\n" + _memory_block(memories))
        parts.append("\n# Your book\n" + _book_block(
            self._safe(self.ctx.positions, []), self._safe(self.ctx.balance, None)
        ))
        parts.append("\n# Recent outcomes\n" + _outcomes_block(
            self._safe(lambda: self.ctx.outcomes(10), [])
        ))
        if trigger.startswith("watch:"):  # leap: watch
            parts.append("\n# Why you were woken\n" + self._watch_block())
        # leap: lab -- the desk's own calibration, when it has one; the post-mortem reads it.
        brief = self._safe(lambda: str(getattr(self.ctx, "calibration_brief")() or ""), "")
        if brief:
            parts.append("\n# Your calibration\n" + brief)
        if trigger == "postmortem":
            parts.append(
                "\nThis is a POST-MORTEM session, not a trading session. Do not propose orders. "
                "Read your recent outcomes and memory. Name your single worst decision and your "
                "single best decision since the last post-mortem, with the numbers. State what "
                "evidence you had, what you assumed, and what actually happened. Then write one to "
                "three concrete, testable rules (or delete a rule that failed) and append them under "
                "'Rules I have learned' in your playbook with playbook_write, giving the reason. "
                "Write one memory entry with kind 'lesson' per rule. If a calibration block is "
                "shown above, say in one sentence whether you have been over- or under-confident "
                "and in which range. Finish with end_session whose summary is the post-mortem "
                "itself: worst decision, best decision, rules changed."
            )
        else:
            parts.append(
                "\nWork the playbook for this trigger. Call tools to gather what you need, propose "
                "any orders you can justify, then call end_session with a short summary."
            )
        return "\n".join(parts)

    def _watch_block(self) -> str:
        """The night watch's own words for waking the desk (leap: watch)."""
        try:
            event = self.log.last(self.manifest.stream, "desk.watch")
        except Exception:
            event = None
        if event is None or event.payload.get("decision") != "wake":
            return (
                "The night watch woke you on a trigger. Check your book and the market it "
                "concerns, act if the playbook says so, and end the session if not."
            )
        detail = str(event.payload.get("detail") or "")[:300]
        reason = str(event.payload.get("reason") or "")[:500]
        return (
            f"Trigger: {detail}\nThe watch's reason for waking you: {reason}\n"
            "This is not a scheduled session. Decide quickly whether the event changes a "
            "position you hold or opens something inside your mandate; act if it does, and "
            "end the session if it does not."
        )

    @staticmethod
    def _safe(call: Callable[[], Any], default: Any) -> Any:
        """Context failures degrade the prompt; they never abort a session."""
        try:
            return call()
        except Exception:
            return default

    # ------------------------------------------------------------------ the loop
    def run_session(self, trigger: str) -> SessionResult:
        """Run one full session and return what it did. Never raises for a model or tool failure."""
        session_id = self.session_id(trigger)
        counter = [0]

        def emit(kind: str, payload: dict[str, Any], *, stream: str | None = None) -> None:
            counter[0] += 1
            self._append(stream or self.manifest.stream, kind, payload, session_id, counter[0])

        self.ctx.bind_session(session_id)
        emit("desk.session_started", {"session_id": session_id, "trigger": trigger})
        conversation: list[Any] = list(self.build_prompt(session_id, trigger))
        session = ToolSession(session_id=session_id, desk_id=self.manifest.id)
        requests = 0
        turns = 0
        cost = ZERO
        nudged = False
        reason = "max_turns"

        for turn in range(max(1, self.manifest.model.max_turns)):
            session.now = now_iso(self.clock)
            try:
                response = self.provider.respond(
                    self.manifest.model.profile,
                    conversation,
                    tools=self.tool_schemas,
                    desk_id=self.manifest.id,
                    session_id=session_id,
                    request_key=f"{session_id}:{turn}",
                    reasoning_effort=self.manifest.model.reasoning_effort,
                    max_output_tokens=self.manifest.model.max_output_tokens,
                    desk_cap_usd_per_day=self.manifest.budget_usd_per_day,
                    cache_key=self.manifest.id,
                )
            except BudgetExceeded as exc:
                reason = exc.code
                emit(
                    "ops.alert",
                    {
                        "level": "warn",
                        "text": f"{self.manifest.id} stopped session {session_id} at turn {turn}: "
                        f"{exc.code}",
                    },
                    stream="ops",
                )
                break
            except ProviderError as exc:
                reason = exc.code
                emit(
                    "ops.alert",
                    {"level": "error", "text": f"{self.manifest.id} session {session_id}: {exc.code}"},
                    stream="ops",
                )
                break

            requests += 1
            turns = turn + 1
            cost += response.cost_usd or ZERO
            conversation.extend(response.output_items)
            for summary in response.reasoning_summaries:
                emit("desk.thought", {"session_id": session_id, "text": summary[:8000]})
            if response.output_text.strip():
                emit(
                    "desk.thought",
                    {"session_id": session_id, "text": response.output_text.strip()[:8000]},
                )

            if response.status in ("failed", "cancelled"):
                reason = f"provider_{response.status}"
                break
            if response.incomplete:
                reason = "incomplete:" + (response.incomplete_reason or "unknown")
                break

            calls = response.function_calls
            if not calls:
                # A reply with no tool call is usually a model that forgot the contract, not
                # a model that is done: say so once, then let it try again. A second such reply
                # ends the session and is recorded as what it is.
                if not nudged:
                    nudged = True
                    conversation.append(
                        {
                            "role": "user",
                            "content": (
                                "You replied without calling a tool. Every turn must call a tool: "
                                "research with your tools, record what you concluded with memo, "
                                "and finish with end_session."
                            ),
                        }
                    )
                    continue
                reason = "no_tool_calls"
                break

            for call in calls:
                emit(
                    "desk.tool_call",
                    {
                        "session_id": session_id,
                        "call_id": call.call_id,
                        "tool": call.name,
                        "arguments": tools_module.public_arguments(call.name, call.arguments),
                    },
                )
                if call.error:
                    output = tools_module.error_json(call.error)
                else:
                    output = tools_module.execute(
                        call.name, call.arguments, self.ctx, self.manifest, session
                    )
                result = {
                    "session_id": session_id,
                    "call_id": call.call_id,
                    "tool": call.name,
                    "summary": tools_module.summarize_result(call.name, output),
                }
                sha = tools_module.document_sha256(output)
                if sha:
                    result["document_sha256"] = sha
                emit("desk.tool_result", result)
                if call.name == "playbook_write":
                    self._emit_playbook_update(emit, output)
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )
            if session.ended:
                reason = "end_session"
                break

        if trigger == "postmortem" and session.end_summary:
            emit(
                "desk.postmortem",
                {
                    "session_id": session_id,
                    "period": now_iso(self.clock)[:10],
                    "text": str(session.end_summary)[:6000],
                    "lessons": _lessons_from(str(session.end_summary)),
                },
            )

        emit(
            "desk.session_ended",
            {
                "session_id": session_id,
                "requests": requests,
                "cost_usd": format(cost, "f"),
                "reason": reason,
            },
        )
        return SessionResult(
            session_id=session_id,
            turns=turns,
            requests=requests,
            cost_usd=cost,
            intents=list(session.intents),
            reason=reason,
        )

    # ------------------------------------------------------------------ emission
    def _emit_playbook_update(self, emit: Callable[..., None], output: str) -> None:
        try:
            data = json.loads(output)
        except ValueError:  # pragma: no cover - execute always returns JSON
            return
        if not isinstance(data, dict) or "version" not in data or "diff" not in data:
            return
        emit(
            "desk.playbook_updated",
            {
                "version": data["version"],
                "diff": str(data.get("diff", ""))[:MAX_DIFF_CHARS],
                "reason": str(data.get("reason", ""))[:500],
            },
        )

    def _append(
        self, stream: str, kind: str, payload: dict[str, Any], session_id: str, counter: int
    ) -> None:
        """Append with a derived id so a replayed session reuses ids instead of duplicating."""
        event_id = f"{session_id}:e{counter:04d}"
        try:
            self.log.append(stream, kind, payload, id=event_id)
        except EventConflict:
            # The same slot already holds different content (a replay that diverged). Keep the
            # first record and file this one under a content-addressed id: nothing is lost and
            # the id stays stable if the replay happens again.
            digest = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()[:12]
            self.log.append(stream, kind, payload, id=f"{event_id}-{digest}")


def _pct(value: Decimal) -> str:
    return f"{(value * 100).normalize():f}%"


def _rows(value: Any, *keys: str) -> list[Any]:
    """A list of rows from a context that answered with a list or with a wrapper object."""
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return value[key]
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _lessons_from(summary: str) -> list[str]:
    """Pull bullet or numbered lines out of a post-mortem summary as the lessons list."""
    lessons: list[str] = []
    for line in summary.splitlines():
        stripped = line.strip()
        if len(stripped) > 3 and (stripped[0] in "-*" or stripped[:2].rstrip(".)").isdigit()):
            text = stripped.lstrip("-*0123456789.) ").strip()
            if text:
                lessons.append(text[:400])
    return lessons[:10]


def _memory_block(entries: Iterable[Any]) -> str:
    lines = []
    for entry in _rows(entries, "entries", "memory"):
        if not isinstance(entry, dict):
            continue
        head = " ".join(
            part for part in (str(entry.get("at", ""))[:10], entry.get("symbol"), entry.get("kind"))
            if part
        )
        lines.append(f"- [{head}] {str(entry.get('text', '')).strip()}")
    return "\n".join(lines) if lines else "(no memory yet)"


def _book_block(positions: Iterable[Any], balance: Any) -> str:
    lines = []
    if balance is not None:
        data = balance.to_dict() if hasattr(balance, "to_dict") else balance
        if isinstance(data, dict) and isinstance(data.get("balance"), dict):
            data = data["balance"]
        if isinstance(data, dict):
            lines.append(
                f"Cash {data.get('cash')}, equity {data.get('equity')}, "
                f"buying power {data.get('buying_power')} ({data.get('venue', '')})"
            )
    rows = []
    for position in _rows(positions, "positions"):
        data = position.to_dict() if hasattr(position, "to_dict") else position
        if not isinstance(data, dict):
            continue
        instrument = data.get("instrument") or {}
        symbol = instrument.get("symbol", "?") if isinstance(instrument, dict) else "?"
        rows.append(
            f"- {symbol}: {data.get('quantity')} at {data.get('average_cost')}, "
            f"mark {data.get('mark')}, unrealized {data.get('unrealized_pnl')}"
        )
    lines.append("\n".join(rows) if rows else "(no open positions)")
    return "\n".join(lines)


def _outcomes_block(outcomes: Iterable[Any]) -> str:
    """One line per scored outcome, whole. A `desk.outcome` carries nine fields and the last
    of them is the desk's own rationale, which is the field a post-mortem most needs."""
    lines = []
    for outcome in _rows(outcomes, "outcomes", "fills", "trades"):
        if not isinstance(outcome, dict):
            continue
        lines.append(
            "- "
            + ", ".join(
                f"{key}: {value}"
                for key, value in list(outcome.items())[:12]
                if not str(key).startswith("_")
            )
        )
    return "\n".join(lines) if lines else "(no closed trades yet)"


__all__ = [
    "Desk",
    "MemoryStore",
    "PlaybookError",
    "PlaybookStore",
    "SessionResult",
    "HEADER",
    "LIVE_NOTE",
    "SHADOW_NOTE",
    "header_for",
    "unified_diff",
]
