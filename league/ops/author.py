"""The engineer's authoring leg (LTCM v3, Phase 4, B5): one Claude tool loop that writes an isolated harness change.

The engineer job (`league/ops/engineer.py`) unpacks the running release's commit into a private work tree and hands it
here with the bottleneck it picked. Claude Opus 5.5 (role `engineer`, through `ModelRouter.claude_turn`: the role's line,
the funded room and the gateway's meter, like every other Claude call of the House) reads the tree and edits it through
the tools below, and nothing else:

- `list_dir`, `read_file`, `grep`: read anywhere inside the work tree (the public repository's own files);
- `edit_file`: one exact, unique replacement in a file the candidate may change: the lane's surface
  (`harness_lanes.LANES[lane].surface`) AND the gateway's engineer allowlist for that lane (`GATEWAY_LANE_PATHS`), never a
  protected path (`harness_lanes.protected_reason`), and never a path the job HOLDS for this attempt (`Workspace.held`:
  the engineer holds every module the live path loads, so its changes stay research-class);
- `create_file`: a NEW test file only (`league/tests/test_harness_candidate_*.py`, absent from the base);
- `check`: the static guards now (`static_guards`);
- `finish` (the change, its title, what it predicts and its canary plan) or `give_up` (no viable change). After either,
  every later tool call (even in the same reply) is refused, and the guards run once more on the tree as submitted.

THE STATIC GUARDS (`static_guards`), git-free, the same functions the owner's controller runs: the surface and the
protected paths (`surface_check`, `protected_touch`), the gateway's limits (at most `MAX_FILES` files, `MAX_FILE_BYTES`
each, `MAX_TOTAL_BYTES` together), each Python file compiles, `content_guard` (no new route to a protected module, a
process, a file write, reflection, a store writer, a sealed read ...), `symbol_guard` (no frozen symbol, no new path to a
record writer) and, in an arms lane, `gate_coverage` (every change sits under `canary.enabled(KEY, unit, root=...)` with
the old branch the baseline's own code, so the closed gate runs the baseline). They are defense in depth, never a proof:
the reviewer (`league/ops/reviewer.py`), CI and the canary stand behind them.

SPEND. An attempt stops before a turn that would take its settled spend past `usd_cap` (at most $3, and never more than
the engineer's and the reviewer's day line has left: the next turn is estimated from the last one's settled cost and its
growth), at `max_turns`, or at its wall-clock `deadline`. A turn whose bill is unknown
counts at its hold. The router's own fuses (the `engineer` line a UTC day, the funded room less `keep_usd`) refuse a
turn before it is sent; any refusal ends the attempt.

Standard library only.
"""
from __future__ import annotations

import copy
import fnmatch
import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

#: The files the gateway's engineer role may write, by lane (V3-A WP8b; the merge route checks the same list).
GATEWAY_LANE_PATHS: dict[str, tuple[str, ...]] = {
    "scheduler": ("league/swarm/loop.py",),
    "research": ("league/swarm/researcher.py", "league/swarm/preflight.py", "league/swarm/claude_research.py"),
    "memory": ("league/swarm/architect.py", "league/swarm/strategist.py", "league/swarm/diagnostician.py",
               "league/swarm/seeds.py", "league/swarm/mechanisms.py"),
    "data": ("league/sailbox.py", "league/data_job.py"),
}
NEW_TEST = "league/tests/test_harness_candidate_*.py"
#: The exact names the gateway admits for a new test (`ENGINEER_TEST` in gateway/lib/github.mjs; ci.py `_allows`):
#: lower-case letters, digits and underscores only. `NEW_TEST` is the glob for prose; this is the rule.
NEW_TEST_RE = re.compile(r"league/tests/test_harness_candidate_[a-z0-9_]+\.py")
#: The gateway's limits on one engineer pull request (WP8b): files, bytes a file, bytes a request.
MAX_FILES = 6
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 1536 * 1024
#: A new test file is small: it pins the change, it does not carry data.
MAX_TEST_BYTES = 64 * 1024
#: What one tool answer may carry back to the model, in characters.
RESULT_CHARS = 24_000
READ_LINES, READ_LINES_MAX = 400, 800
GREP_RESULTS = 60
#: The grep tool's bounds on a model-written pattern: its length, the line prefix searched, the wall time, and no shape
#: known to backtrack catastrophically (a quantified group holding a quantifier, a backreference).
GREP_PATTERN_CHARS = 200
GREP_LINE_CHARS = 2000
GREP_SECONDS = 20.0
NESTED_QUANTIFIER = re.compile(r"[*+?}]\)*\)[*+{]")
BACKREFERENCE = re.compile(r"\\[1-9]|\(\?P=")
LIST_ENTRIES = 300
TEXT_SUFFIXES = (".py", ".md", ".json", ".txt", ".toml", ".cfg", ".sh", ".yml", ".yaml")
MARK = {"type": "ephemeral"}


class AuthorError(RuntimeError):
    pass


def is_new_test(path: Any) -> bool:
    """Whether `path` is a name the gateway admits for a candidate's new test (`NEW_TEST_RE`, exactly)."""
    return isinstance(path, str) and NEW_TEST_RE.fullmatch(path) is not None


def writable(lane: str, path: str, held: Mapping[str, str] | None = None) -> bool:
    """Whether a candidate of `lane` may change `path`: the lane's surface and the gateway's allowlist, never protected,
    never one of the paths `held` (path -> why) for this attempt."""
    from ..swarm import harness_lanes as lanes

    spec = lanes.LANES.get(lane)
    if spec is None or lanes.protected_reason(path) is not None:  # a new candidate test file is not protected
        return False
    if held and path in held:
        return False
    in_surface = any(fnmatch.fnmatchcase(path, pattern) for pattern in spec.surface)
    in_gateway = path in GATEWAY_LANE_PATHS.get(lane, ()) or is_new_test(path)
    return in_surface and in_gateway


def writable_paths(lane: str, held: Mapping[str, str] | None = None) -> list[str]:
    """The lane's editable files the gateway also admits (tests aside), less the paths `held`, for the brief."""
    return [p for p in GATEWAY_LANE_PATHS.get(lane, ()) if writable(lane, p, held)]


def sha256(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------------ the work tree
class Workspace:
    """The unpacked base tree plus the candidate's edits, applied in place. `originals` holds each edited file's base
    text (None for a new file), so the base is always readable beside the candidate. `held` ({path: why}) names the lane
    files this attempt may not change: the tools refuse them and the static guards count them as problems."""

    def __init__(self, root: str | Path, lane: str, *, start: Mapping[str, str] | None = None,
                 held: Mapping[str, str] | None = None):
        self.root = Path(root).resolve()
        self.lane = lane
        self.held: dict[str, str] = {str(k): str(v) for k, v in (held or {}).items()}
        self.originals: dict[str, str | None] = {}
        for path, text in (start or {}).items():
            self.write(path, text, new_test_ok=True)

    # paths
    def resolve(self, rel: Any) -> Path:
        rel = str(rel or "").strip()
        while rel.startswith("./"):
            rel = rel[2:]
        rel = "" if rel in (".", "") else rel.rstrip("/")
        if rel.startswith("/") or "\\" in rel or "\x00" in rel or any(part == ".." for part in rel.split("/")):
            raise AuthorError(f"{rel!r}: a path inside the tree, with forward slashes and no '..'")
        path = (self.root / rel).resolve() if rel else self.root
        if path != self.root and self.root not in path.parents:
            raise AuthorError(f"{rel!r} is outside the tree")
        return path

    def read_base(self, rel: str) -> str | None:
        if rel in self.originals:
            return self.originals[rel]
        return self.read(rel)

    def read(self, rel: str) -> str | None:
        try:
            return self.resolve(rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, AuthorError):
            return None

    def write(self, rel: str, text: str, *, new_test_ok: bool = False) -> None:
        path = self.resolve(rel)
        before = self.originals[rel] if rel in self.originals else (self.read(rel) if path.exists() else None)
        if before is None and not (new_test_ok and is_new_test(rel)):
            raise AuthorError(f"{rel}: only an existing surface file, or a new test file, may be written")
        self.originals.setdefault(rel, before)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def changes(self) -> dict[str, tuple[str | None, str]]:
        """{path: (base text or None, candidate text)} for every file that differs from the base."""
        out = {}
        for rel, before in sorted(self.originals.items()):
            after = self.read(rel)
            if after is not None and after != before:
                out[rel] = (before, after)
        return out

    def files(self) -> dict[str, str]:
        return {rel: after for rel, (_, after) in self.changes().items()}


# ------------------------------------------------------------------------------------------------ static guards
def static_guards(lane: str, ws: Workspace, *, key: str | None) -> list[str]:
    """Every static guard over the workspace's changes: [] when they all pass (the module docstring)."""
    from ..swarm import harness_lanes as lanes
    from ..swarm.improvement import ImprovementError

    spec = lanes.LANES[lane]
    changes = ws.changes()
    problems: list[str] = []
    if not changes:
        return ["the candidate changes nothing"]
    paths = list(changes)
    try:
        lanes.surface_check(spec, paths)
    except ImprovementError as exc:
        problems.append(str(exc))
    for path in paths:
        if path in ws.held:
            problems.append(f"{path}: held in this release ({ws.held[path]})")
        elif not writable(lane, path):
            problems.append(f"{path}: outside what the gateway's engineer role may write for the {lane} lane")
    touched = lanes.protected_touch([("A" if changes[p][0] is None else "M", p) for p in paths])
    problems += [f"protected: {t}" for t in touched]
    if len(paths) > MAX_FILES:
        problems.append(f"{len(paths)} files: a candidate changes at most {MAX_FILES}")
    total = 0
    for path, (before, after) in changes.items():
        size = len(after.encode("utf-8"))
        total += size
        limit = MAX_TEST_BYTES if before is None else MAX_FILE_BYTES
        if size > limit:
            problems.append(f"{path}: {size} bytes, above the {limit} a file may carry")
    if total > MAX_TOTAL_BYTES:
        problems.append(f"{total} bytes together, above the {MAX_TOTAL_BYTES} a pull request may carry")
    gates = 0
    canary_cfg = spec.canary
    arms = canary_cfg.get("mode") == "arms"
    read_before, read_after = ws.read_base, ws.read
    for path, (before, after) in changes.items():
        if not path.endswith(".py"):
            continue
        try:
            compile(after, path, "exec", dont_inherit=True)
        except SyntaxError as exc:
            problems.append(f"{path}: does not compile ({exc.msg}, line {exc.lineno})")
            continue
        for name, guard in (("content_guard", lambda: lanes.content_guard(path, before, after, read_before=read_before,
                                                                          read_after=read_after)),
                            ("symbol_guard", lambda: lanes.symbol_guard(path, before, after))):
            try:
                guard()
            except Exception as exc:  # noqa: BLE001 - every guard's refusal is a problem the author must answer
                problems.append(f"{name}: {str(exc)[:600]}")
        if arms and before is not None and key:
            try:
                gates += lanes.gate_coverage(path, before, after, key, canary_cfg.get("unit"))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"gate_coverage: {str(exc)[:600]}")
    if arms and key and not problems and gates < 1:
        problems.append(f"no change sits under canary.enabled({key!r}, ...): an arms lane's change must be gated")
    return problems


# ------------------------------------------------------------------------------------------------ the tools
def _schema(properties: Mapping[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": list(required), "additionalProperties": False}


TOOLS: tuple[dict[str, Any], ...] = (
    {"name": "list_dir", "description": "List the files and directories under a directory of the tree (repository-relative).",
     "input_schema": _schema({"path": {"type": "string"}}, ["path"])},
    {"name": "read_file", "description": "Read a window of a file's lines, numbered. start_line is 1-based; lines at most "
                                         f"{READ_LINES_MAX} (default {READ_LINES}). Reads see your edits.",
     "input_schema": _schema({"path": {"type": "string"}, "start_line": {"type": "integer"}, "lines": {"type": "integer"}},
                             ["path"])},
    {"name": "grep", "description": "Search text files for a Python regular expression: path:line: text, at most "
                                    f"{GREP_RESULTS} hits. path is a file or a directory (default league).",
     "input_schema": _schema({"pattern": {"type": "string"}, "path": {"type": "string"}}, ["pattern"])},
    {"name": "edit_file", "description": "Replace old_text with new_text in a file you may change. old_text must occur "
                                         "exactly once (include enough context). Only the files the brief lists.",
     "input_schema": _schema({"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
                             ["path", "old_text", "new_text"])},
    {"name": "create_file", "description": "Create a NEW test file named league/tests/test_harness_candidate_<name>.py "
                                           f"(at most {MAX_TEST_BYTES} bytes). No other new file is allowed.",
     "input_schema": _schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])},
    {"name": "check", "description": "Run the static guards on your change now; returns ok or the problems to fix.",
     "input_schema": _schema({})},
    {"name": "finish", "description": "Submit the change. The guards run first; a refusal comes back to fix. title: one "
                                      "line; summary: what changed and why; predicted_effect: the metric's expected move; "
                                      "canary_plan: what the canary should show.",
     "input_schema": _schema({"title": {"type": "string"}, "summary": {"type": "string"},
                              "predicted_effect": {"type": "string"}, "canary_plan": {"type": "string"}},
                             ["title", "summary", "predicted_effect", "canary_plan"])},
    {"name": "give_up", "description": "Stop without a change when no change inside the rules can move the metric.",
     "input_schema": _schema({"reason": {"type": "string"}}, ["reason"])},
)


def anthropic_tools() -> list[dict[str, Any]]:
    out = [dict(copy.deepcopy(t), eager_input_streaming=True) for t in TOOLS]
    out[-1]["cache_control"] = dict(MARK)
    return out


def _clip(text: str, limit: int = RESULT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n... ({len(text) - limit} more characters)"


def _ascii(text: Any, limit: int) -> str:
    return " ".join(str(text or "").encode("ascii", "replace").decode("ascii").split())[:limit]


@dataclass
class Outcome:
    """What one authoring attempt came to. `status`: `finished` (files, title, ...), `gave_up`, `failed` (why)."""
    status: str
    why: str = ""
    files: dict[str, str] = field(default_factory=dict)
    originals: dict[str, str | None] = field(default_factory=dict)
    title: str = ""
    summary: str = ""
    predicted_effect: str = ""
    canary_plan: str = ""
    usd: float = 0.0
    turns: int = 0
    guards: list[str] = field(default_factory=list)


class Tools:
    """The tools' semantics over one workspace (the module docstring). Each returns (text, is_error)."""

    def __init__(self, ws: Workspace, lane: str, key: str | None):
        self.ws, self.lane, self.key = ws, lane, key
        self.finished: dict[str, str] | None = None
        self.gave_up: str | None = None

    @property
    def over(self) -> bool:
        return self.finished is not None or self.gave_up is not None

    def call(self, name: str, args: Mapping[str, Any]) -> tuple[str, bool]:
        # After `finish` (or `give_up`) the change is what the guards passed: a later call in the same reply (an edit
        # after the finish) is refused, so the submitted files are exactly the checked ones.
        if self.over:
            return "the attempt is over (finish or give_up was called): nothing more is done", True
        try:
            handler = getattr(self, "t_" + name, None)
            if handler is None:
                return f"unknown tool {name}", True
            return handler(**{k: v for k, v in dict(args).items()})
        except (TypeError, ValueError, OverflowError) as exc:
            return f"bad arguments: {exc}", True
        except (AuthorError, OSError) as exc:
            return str(exc), True

    def t_list_dir(self, path: str) -> tuple[str, bool]:
        target = self.ws.resolve(path)
        if not target.is_dir():
            return f"{path}: not a directory", True
        rows = []
        for entry in sorted(target.iterdir(), key=lambda p: p.name)[:LIST_ENTRIES]:
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            rel = entry.relative_to(self.ws.root).as_posix()
            rows.append(rel + "/" if entry.is_dir() else f"{rel} ({entry.stat().st_size} bytes)")
        return "\n".join(rows) or "(empty)", False

    def t_read_file(self, path: str, start_line: int = 1, lines: int = READ_LINES) -> tuple[str, bool]:
        text = self.ws.read(path)
        if text is None:
            return f"{path}: no such text file", True
        all_lines = text.splitlines()
        start = max(1, int(start_line))
        count = max(1, min(int(lines), READ_LINES_MAX))
        window = all_lines[start - 1:start - 1 + count]
        body = "\n".join(f"{start + i:6d}  {line}" for i, line in enumerate(window))
        return _clip(f"{path}: lines {start}-{start + len(window) - 1} of {len(all_lines)}\n{body}"), False

    def t_grep(self, pattern: str, path: str = "league") -> tuple[str, bool]:
        pattern = str(pattern)
        if len(pattern) > GREP_PATTERN_CHARS:
            return f"bad pattern: at most {GREP_PATTERN_CHARS} characters", True
        if NESTED_QUANTIFIER.search(pattern) or BACKREFERENCE.search(pattern):
            return ("bad pattern: no repeated group that holds a quantifier, and no backreference (they can run for "
                    "hours)"), True
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"bad pattern: {exc}", True
        stop = time.monotonic() + GREP_SECONDS
        target = self.ws.resolve(path)
        files = [target] if target.is_file() else sorted(p for p in target.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES
                                                          and "__pycache__" not in p.parts)
        hits: list[str] = []
        for file in files:
            if time.monotonic() > stop:
                return _clip("\n".join(hits) + f"\n... (stopped after {GREP_SECONDS:.0f} s: narrow the search)"), False
            try:
                for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                    if regex.search(line[:GREP_LINE_CHARS]):
                        hits.append(f"{file.relative_to(self.ws.root).as_posix()}:{n}: {line.strip()[:240]}")
                        if len(hits) >= GREP_RESULTS:
                            return _clip("\n".join(hits) + "\n... (more hits: narrow the search)"), False
            except (OSError, UnicodeDecodeError):
                continue
        return _clip("\n".join(hits) or "(no match)"), False

    def t_edit_file(self, path: str, old_text: str, new_text: str) -> tuple[str, bool]:
        own_test = is_new_test(path) and path in self.ws.originals and self.ws.originals[path] is None
        if path in self.ws.held:
            return (f"{path}: held in this release ({self.ws.held[path]}); you may change only "
                    f"{', '.join(writable_paths(self.lane, self.ws.held)) or 'a new test file'}"), True
        if not writable(self.lane, path) or is_new_test(path) and not own_test:
            return (f"{path}: you may change only {', '.join(writable_paths(self.lane, self.ws.held))} (and your own new "
                    "test file)"), True
        text = self.ws.read(path)
        if text is None:
            return f"{path}: no such file", True
        found = text.count(old_text) if old_text else 0
        if found != 1:
            return f"{path}: old_text occurs {found} times; it must occur exactly once", True
        changed = text.replace(old_text, new_text, 1)
        if len(changed.encode("utf-8")) > MAX_FILE_BYTES:
            return f"{path}: the edit would take it above {MAX_FILE_BYTES} bytes", True
        if path not in self.ws.originals and len(self.ws.changes()) >= MAX_FILES:
            return f"a candidate changes at most {MAX_FILES} files", True
        self.ws.write(path, changed, new_test_ok=True)
        return f"{path}: edited ({len(changed.splitlines())} lines)", False

    def t_create_file(self, path: str, content: str) -> tuple[str, bool]:
        if not is_new_test(path):
            return (f"{path}: the only new file allowed is league/tests/test_harness_candidate_<name>.py, <name> of "
                    "lower-case letters, digits and underscores"), True
        if path not in self.ws.originals and self.ws.resolve(path).exists():
            return f"{path}: exists in the base; an existing test is never edited", True
        if len(content.encode("utf-8")) > MAX_TEST_BYTES:
            return f"{path}: above {MAX_TEST_BYTES} bytes", True
        if path not in self.ws.originals and len(self.ws.changes()) >= MAX_FILES:
            return f"a candidate changes at most {MAX_FILES} files", True
        self.ws.write(path, content, new_test_ok=True)
        return f"{path}: created", False

    def t_check(self) -> tuple[str, bool]:
        problems = static_guards(self.lane, self.ws, key=self.key)
        return ("ok: every static guard passes" if not problems else "problems:\n- " + "\n- ".join(problems)), bool(problems)

    def t_finish(self, title: str, summary: str, predicted_effect: str, canary_plan: str) -> tuple[str, bool]:
        problems = static_guards(self.lane, self.ws, key=self.key)
        if problems:
            return "not submitted; fix these first:\n- " + "\n- ".join(problems), True
        self.finished = {"title": _ascii(title, 100), "summary": _ascii(summary, 1500),
                         "predicted_effect": _ascii(predicted_effect, 600), "canary_plan": _ascii(canary_plan, 600)}
        return "submitted", False

    def t_give_up(self, reason: str) -> tuple[str, bool]:
        self.gave_up = _ascii(reason, 600) or "no reason given"
        return "stopped", False


# ------------------------------------------------------------------------------------------------ the loop
def run_loop(router: Any, *, ws: Workspace, lane: str, key: str | None, system: str, brief: str, request_key: str,
             usd_cap: float, max_turns: int, deadline: float, effort: str = "high", max_tokens: int = 16000,
             keep_usd: float = 0.0, clock: Callable[[], float] = time.time) -> Outcome:
    """One authoring attempt (the module docstring). Never raises: every stop is an `Outcome`."""
    from ..swarm.models import ModelError

    tools = Tools(ws, lane, key)
    system_blocks = [{"type": "text", "text": system, "cache_control": dict(MARK)}]
    schemas = anthropic_tools()
    messages: list[dict[str, Any]] = [{"role": "user", "content": [{"type": "text", "text": brief}]}]
    spent, last, prev, turns = 0.0, 0.0, 0.0, 0
    why = ""
    while True:
        if tools.finished is not None or tools.gave_up is not None:
            break
        if turns >= max_turns:
            why = f"the attempt used its {max_turns} turns without submitting"
            break
        # The next turn resends the whole conversation: at least 1.3 times the last, and twice its growth on top.
        growth = max(0.0, last - prev) if turns >= 2 else 0.0
        estimate = max(0.10, 1.3 * last, last + 2.0 * growth)
        if spent + estimate > usd_cap:
            why = f"the next turn could take the attempt past its ${usd_cap:.2f} (spent ${spent:.2f})"
            break
        left = deadline - clock()
        if left < 60:
            why = "the attempt ran out of wall-clock time"
            break
        sent = copy.deepcopy(messages)
        sent[-1]["content"][-1]["cache_control"] = dict(MARK)
        try:
            reply = router.claude_turn(role="engineer", family=None, key=f"{request_key}:{turns}", system=system_blocks,
                                       tools=schemas, messages=sent, effort=effort, max_tokens=max_tokens,
                                       timeout=min(900.0, left), keep_usd=keep_usd)
        except ModelError as exc:
            spent += sum(float(b.get("cost_usd") or 0.0) for b in exc.billed) + float(exc.held_usd or 0.0)
            why = f"the model call failed ({exc.kind}): {str(exc)[:300]}"
            break
        turns += 1
        prev, last = last, float(reply.cost_usd if reply.cost_usd is not None else reply.held_usd)
        spent += last
        answer = reply.answer
        messages.append({"role": "assistant", "content": [dict(b) for b in answer.content]})
        results: list[dict[str, Any]] = []
        for use in answer.tool_uses:
            if tools.over:
                text, error = tools.call(use.name, use.input)  # refused: the attempt is over
            elif use.error:
                text, error = f"the input did not parse: {use.error}", True
            else:
                text, error = tools.call(use.name, use.input)
            results.append({"type": "tool_result", "tool_use_id": use.id, "content": text or "(empty)",
                            **({"is_error": True} if error else {})})
        if not results:
            results = [{"type": "text", "text": "Use the tools: edit, then call finish (or give_up)."}]
        if tools.finished is None and tools.gave_up is None and turns >= max_turns - 2:
            results.append({"type": "text", "text": f"{max_turns - turns} turn(s) left: finish now or give_up."})
        messages.append({"role": "user", "content": results})
        if len(messages) > 62:
            why = "the conversation reached the gateway's turn limit"
            break
    files = ws.files()
    if tools.finished is not None:
        problems = static_guards(lane, ws, key=key)  # the tree as submitted, whatever came after the finish
        if problems:
            return Outcome("failed", why="the submitted tree no longer passes the static guards", usd=round(spent, 6),
                           turns=turns, guards=problems)
        return Outcome("finished", files=files, originals={p: ws.originals.get(p) for p in files}, usd=round(spent, 6),
                       turns=turns, **tools.finished)
    if tools.gave_up is not None:
        return Outcome("gave_up", why=tools.gave_up, usd=round(spent, 6), turns=turns)
    return Outcome("failed", why=why, usd=round(spent, 6), turns=turns, guards=static_guards(lane, ws, key=key) if files else [])


__all__ = ["GATEWAY_LANE_PATHS", "NEW_TEST", "NEW_TEST_RE", "is_new_test", "MAX_FILES", "MAX_FILE_BYTES", "MAX_TOTAL_BYTES",
           "AuthorError", "Workspace",
           "Tools", "Outcome", "TOOLS", "anthropic_tools", "run_loop", "static_guards", "writable", "writable_paths", "sha256"]
