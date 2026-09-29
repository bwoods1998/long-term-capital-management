"""The researcher's tool loop on Claude (Sept 29, 2026, the owner's decision: be bold with Claude Sonnet 5.5).

The bandit's top `researcher.claude_top` families run their research cycles on Claude Sonnet 5.5 through the gateway
(`ModelRouter.claude_turn`), the rest on Sail as before. This module is the adapter between the two worlds; the loop,
the tools, their limits and their semantics are the researcher's own and do not change (league/swarm/researcher.py).

- THE TOOLS (`anthropic_tools`): the researcher's tool schemas `{name, description, parameters}` become Anthropic's
  `{name, description, input_schema}`, with `eager_input_streaming` (a program streams as it is written) and a cache
  marker on the last. Claude is always given the FULL constant list (every tool, `gym_sweep` at the configured variant
  limit), whatever the turn offers: the tools render first in the prompt, so a list that changed from turn to turn would
  void the prompt cache and every thinking block after it (Anthropic's preserved thinking binds a thinking block to the
  tools, the system prompt and every earlier turn). The turn's own offer (REVISE: a run or a sweep; READ: every tool;
  `retire` only when the family may retire) is said in a note at the end of the turn and enforced in code: a call to a
  tool not offered is answered with a plain refusal, never run.
- THE CONVERSATION (`anthropic_messages`): the Sail/Responses history (user text, assistant messages, function calls and
  their outputs) becomes Anthropic turns: same-role items merged into one turn, each turn's tool results first (Anthropic
  requires it), empty text dropped, a result with no call before it (or a call to a tool that is not declared) kept as
  text, a call with no result answered "(no result was recorded)". Call ids are made Anthropic's shape one-to-one.
- WHAT IS STORED (`sail_items`): a Claude answer goes into the family's history as Sail items (its text as an assistant
  message, its calls as function calls), so a later cycle on Sail reads it like any other. Its thinking is NOT stored:
  the next cycle's history carries none, so the history's trimming (`Researcher.trim`) can never invalidate one.
- THE SESSION (`ClaudeSession`): one cycle's Claude conversation, APPEND-ONLY. The first call converts the history once;
  each later call appends one user turn (the loop's tool results, then the turn's note) after the previous answer, which
  is kept exactly as it came (thinking blocks and their signatures included). No earlier turn is ever edited; only the
  one cache marker at its tail moves (moving a marker is not an edit). Markers: the last tool, the system prompt (the
  same bytes for every family, so tools and system are one cached prefix across the whole Claude band) and the tail.
- THE INPUTS (`tool_calls`, `validate`): every call's input is checked against its tool's schema BEFORE it runs: types
  (a boolean is not a number), required keys, enums, arrays' items and no unknown key (Sonnet 5.5 now and then renames
  a parameter). An optional key sent as null is dropped, and a tool name miscased is taken when it names exactly one
  tool (both unambiguous; "accept the call when the match is unambiguous, even if the letter case is wrong" is the first
  of Anthropic's two ways in "Tolerant tool-call handling", prompting Claude Sonnet 5.5). The loop runs and stores the
  declared name; the answer itself goes back to Claude byte for byte as it came (preserved thinking binds its blocks to
  every earlier turn, so no block is ever rewritten). A number must be finite as a float (a 400-digit integer is not). An
  input that did not parse or does not validate is an error on its call, answered as an error and never run; the
  researcher then finishes its cycle on Sail.

Standard library only.
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

MARK = {"type": "ephemeral"}
#: Turns a Claude request carries at most (the gateway takes 64): a longer history finishes its turn on Sail.
MAX_TURNS = 60
#: The characters of an input that did not parse kept beside its error.
RAW_CHARS = 4000
_BAD_ID = re.compile(r"[^A-Za-z0-9_-]")


# ---------------------------------------------------------------------------------------------------------- the tools
def anthropic_tools(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The researcher's tools as Anthropic's (the module docstring): the same names, descriptions and schemas, streamed
    eagerly, a cache marker on the last."""
    out = [{"name": str(t["name"]), "description": str(t.get("description") or ""),
            "input_schema": copy.deepcopy(dict(t["parameters"])), "eager_input_streaming": True} for t in tools]
    if out:
        out[-1]["cache_control"] = dict(MARK)
    return out


@dataclass(frozen=True)
class ToolCall:
    """One call as the researcher's loop reads it (the attribute names of `ltcm.provider.FunctionCall`): `error` is set
    when its input did not parse or does not validate, and then it never runs."""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    raw_arguments: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None


def resolve_name(name: str, names: Sequence[str]) -> str | None:
    """The declared tool a call names: the exact name, else the one name it matches ignoring case, else None."""
    if name in names:
        return name
    matches = [n for n in names if n.lower() == str(name).lower()]
    return matches[0] if len(matches) == 1 else None


def _finite(value: int | float) -> bool:
    """A number a tool can use: a finite float, or an integer a float can hold (a 400-digit JSON integer cannot: float()
    raises OverflowError, which must never escape the input check)."""
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _type_error(schema: Mapping[str, Any], value: Any, where: str) -> str | None:
    kind = schema.get("type")
    if kind == "string" and not isinstance(value, str):
        return f"{where} must be a string"
    if kind == "boolean" and not isinstance(value, bool):
        return f"{where} must be true or false"
    if kind == "integer" and (isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, float) and value.is_integer())):
        return f"{where} must be an integer"
    if kind in ("integer", "number") and not isinstance(value, bool) and isinstance(value, (int, float)) and not _finite(value):
        return f"{where} must be a finite number"
    if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return f"{where} must be a number"
    if kind == "object" and not isinstance(value, dict):
        return f"{where} must be an object"
    if kind == "array" and not isinstance(value, list):
        return f"{where} must be an array"
    return None


def check_input(schema: Mapping[str, Any], value: Any, where: str = "the input") -> str | None:
    """Why `value` does not meet `schema` (the JSON-Schema subset the researcher's tools use: type, properties, required,
    enum, items; an object that declares properties takes no other key; one that declares none is free-form), or None."""
    error = _type_error(schema, value, where)
    if error:
        return error
    if "enum" in schema and value not in schema["enum"]:
        return f"{where} must be one of {', '.join(map(str, schema['enum']))}"
    if isinstance(value, dict) and isinstance(schema.get("properties"), Mapping):
        props = schema["properties"]
        missing = [k for k in schema.get("required") or [] if k not in value]
        if missing:
            return f"{where} is missing {', '.join(missing)}"
        unknown = [k for k in value if k not in props]
        if unknown:
            return f"{where} has no key {', '.join(unknown)} (its keys are {', '.join(props)})"
        for key, item in value.items():
            error = check_input(props[key], item, key if where == "the input" else f"{where}.{key}")
            if error:
                return error
    if isinstance(value, list) and isinstance(schema.get("items"), Mapping):
        for i, item in enumerate(value):
            error = check_input(schema["items"], item, f"{where}[{i}]")
            if error:
                return error
    return None


def validate(schema: Mapping[str, Any], value: Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    """(the input to run, None) or ({}, why it is invalid): optional keys sent as null are dropped first."""
    required = set(schema.get("required") or [])
    clean = {k: v for k, v in dict(value).items() if not (v is None and k not in required)}
    error = check_input(schema, clean)
    return (clean, None) if error is None else ({}, error)


def tool_calls(tool_uses: Sequence[Any], schemas: Mapping[str, Mapping[str, Any]]) -> list[ToolCall]:
    """An answer's calls (`league.claude.ToolUse`) as the loop runs them, each checked against its tool's schema."""
    out = []
    for use in tool_uses:
        name = resolve_name(use.name, list(schemas))
        if use.error:
            out.append(ToolCall(use.id, name or use.name, {}, f"INVALID_JSON ({use.error}): {use.raw[:500]}", use.raw))
        elif name is None:
            out.append(ToolCall(use.id, use.name, {}, f"unknown tool {use.name!r}: the tools are {', '.join(schemas)}", use.raw))
        else:
            args, error = validate(schemas[name], use.input)
            out.append(ToolCall(use.id, name, args, None if error is None else f"invalid input for {name}: {error}", use.raw))
    return out


# --------------------------------------------------------------------------------------------------- the conversation
class _Ids:
    """Call ids made Anthropic's shape (`[A-Za-z0-9_-]{1,128}`), one-to-one: a collision gets a stable suffix. A source id
    that a SECOND call reuses (`fresh`) gets a new id from then on, so no two `tool_use` blocks share one (Anthropic refuses
    that) and each result pairs with the latest call of its id, as the history reads."""

    def __init__(self) -> None:
        self.map: dict[str, str] = {}
        self.used: set[str] = set()

    def _new(self, key: str) -> str:
        base = _BAD_ID.sub("_", key)[:120] or "call"
        out, n = base, 1
        while out in self.used:
            out, n = f"{base}_{n}", n + 1
        self.map[key] = out
        self.used.add(out)
        return out

    def __call__(self, call_id: Any) -> str:
        key = str(call_id)
        return self.map[key] if key in self.map else self._new(key)

    def fresh(self, call_id: Any) -> str:
        """A new id for a call whose source id an earlier call already had."""
        return self._new(str(call_id))


def _text(content: Any) -> str:
    """A message's text: a string, or the text of its parts (`output_text`, `input_text`, `text`)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text") or "") for p in content
                       if isinstance(p, Mapping) and p.get("type") in ("output_text", "input_text", "text"))
    return ""


def _object(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def anthropic_messages(items: Sequence[Mapping[str, Any]], names: Sequence[str], ids: _Ids | None = None) -> list[dict[str, Any]]:
    """Sail/Responses items as Anthropic turns (the module docstring's THE CONVERSATION)."""
    ids = ids or _Ids()
    declared = set(names)
    turns: list[dict[str, Any]] = []
    named: dict[str, str] = {}
    emitted: set[str] = set()

    def add(role: str, block: dict[str, Any]) -> None:
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].append(block)
        else:
            turns.append({"role": role, "content": [block]})

    for item in items:
        kind, role = item.get("type"), item.get("role")
        if kind == "reasoning":
            continue
        if kind == "function_call":
            name, raw = str(item.get("name") or ""), str(item.get("arguments") or "")
            if name in declared:
                args = _object(raw)
                tool_id = ids(item.get("call_id"))
                if tool_id in emitted:  # a reused source id: this call gets its own
                    tool_id = ids.fresh(item.get("call_id"))
                emitted.add(tool_id)
                named[tool_id] = name
                add("assistant", {"type": "tool_use", "id": tool_id, "name": name,
                                  "input": args if args is not None else {"INVALID_JSON": raw[:RAW_CHARS]}})
            else:
                add("assistant", {"type": "text", "text": f"(I called {name or 'a tool'} with {raw[:RAW_CHARS]})"})
        elif kind == "function_call_output":
            output = item.get("output")
            output = output if isinstance(output, str) else json.dumps(output, default=str)
            add("user", {"type": "tool_result", "tool_use_id": ids(item.get("call_id")), "content": output or "(empty)"})
        else:
            text = _text(item.get("content"))
            if text.strip():
                add("assistant" if role == "assistant" else "user", {"type": "text", "text": text})
    return _paired(turns, named)


def _paired(turns: list[dict[str, Any]], named: Mapping[str, str]) -> list[dict[str, Any]]:
    """Every call answered in the next turn and every result right after its call, tool results first in their turn."""
    out: list[dict[str, Any]] = []
    for i, turn in enumerate(turns):
        if turn["role"] == "assistant":
            out.append(turn)
            calls = [b["id"] for b in turn["content"] if b["type"] == "tool_use"]
            answered = {b.get("tool_use_id") for b in turns[i + 1]["content"]} if i + 1 < len(turns) else set()
            missing = [{"type": "tool_result", "tool_use_id": c, "content": "(no result was recorded)", "is_error": True}
                       for c in calls if c not in answered]
            if missing and i + 1 >= len(turns):
                out.append({"role": "user", "content": missing})
            elif missing:
                turns[i + 1] = {"role": "user", "content": missing + turns[i + 1]["content"]}
            continue
        before = {b["id"] for b in out[-1]["content"] if b["type"] == "tool_use"} if out and out[-1]["role"] == "assistant" else set()
        results, rest, seen = [], [], set()
        for block in turn["content"]:
            if block["type"] == "tool_result" and block["tool_use_id"] in before and block["tool_use_id"] not in seen:
                seen.add(block["tool_use_id"])
                results.append(block)
            elif block["type"] == "tool_result":
                rest.append({"type": "text", "text": f"Result of {named.get(block['tool_use_id'], 'a tool')}: {block['content']}"})
            else:
                rest.append(block)
        if out and out[-1]["role"] == "user":  # an earlier turn's blocks became text: still one user turn
            out[-1] = {"role": "user", "content": out[-1]["content"] + results + rest}
        else:
            out.append({"role": "user", "content": results + rest})
    return out


def sail_items(content: Sequence[Mapping[str, Any]], calls: Sequence[ToolCall]) -> list[dict[str, Any]]:
    """A Claude answer as the Sail items the family's history keeps (the module docstring's WHAT IS STORED): its text,
    its calls (the name as the loop ran it; an input that did not parse kept as `{"INVALID_JSON": raw}`), no thinking."""
    by_id = {c.call_id: c for c in calls}
    out: list[dict[str, Any]] = []
    for block in content:
        kind = block.get("type")
        if kind == "text" and str(block.get("text") or "").strip():
            out.append({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": block["text"]}]})
        elif kind == "tool_use":
            call = by_id.get(str(block.get("id")))
            name = call.name if call is not None else str(block.get("name") or "")
            if call is not None and call.error and call.error.startswith("INVALID_JSON"):
                arguments = json.dumps({"INVALID_JSON": call.raw_arguments[:RAW_CHARS]})
            else:
                arguments = json.dumps(block.get("input") if isinstance(block.get("input"), dict) else {})
            out.append({"type": "function_call", "call_id": str(block.get("id")), "name": name, "arguments": arguments})
    return out


@dataclass
class ClaudeTurn:
    """A Claude answer as the researcher's loop reads a Sail response (the fields of `ltcm.provider.ProviderResponse` it
    uses), with the exact blocks, the usage and the model beside them."""

    cost_usd: float
    output_items: list[dict[str, Any]]
    function_calls: list[ToolCall]
    output_text: str
    content: list[dict[str, Any]]
    usage: dict[str, Any]
    stop_reason: str
    model: str


class ClaudeSession:
    """One cycle's Claude conversation, append-only (the module docstring's THE SESSION)."""

    def __init__(self, system: str, tools: Sequence[Mapping[str, Any]]):
        self.system = [{"type": "text", "text": system, "cache_control": dict(MARK)}]
        self.tools = [dict(t) for t in tools]
        self.schemas = {t["name"]: t["input_schema"] for t in self.tools}
        self.turns: list[dict[str, Any]] = []
        self.cursor = 0
        self.ids = _Ids()
        self.started = False

    def start(self, brief: str, items: Sequence[Mapping[str, Any]], cursor: int) -> None:
        """The first call's conversation: the brief, then the family's history and this cycle's items so far (`items`,
        sanitized); `cursor` is how many of this cycle's items it has."""
        self.turns = anthropic_messages([{"role": "user", "content": brief}, *items], list(self.schemas), self.ids)
        if not self.turns or self.turns[0]["role"] != "user" or self.turns[-1]["role"] != "user":
            raise ValueError("the conversation must begin and end with the user's turn")
        self.cursor = cursor
        self.started = True

    def request(self, current: Sequence[Mapping[str, Any]], note: str) -> list[dict[str, Any]]:
        """The next call's turns: every turn so far unchanged, then this cycle's new items (the loop's tool results,
        first) and `note`, as one user turn, with the one tail cache marker on its last block."""
        if not self.started:
            raise ValueError("the session has not started")
        blocks: list[dict[str, Any]] = []
        calls = ({b["id"] for b in self.turns[-1]["content"] if b.get("type") == "tool_use"}
                 if self.turns[-1]["role"] == "assistant" else set())
        results, rest = [], []
        for item in current[self.cursor:]:
            if item.get("type") == "function_call_output":
                output = item.get("output")
                output = output if isinstance(output, str) else json.dumps(output, default=str)
                tool_id = self.ids(item.get("call_id"))
                if tool_id in calls:
                    calls.discard(tool_id)
                    results.append({"type": "tool_result", "tool_use_id": tool_id, "content": output or "(empty)"})
                else:
                    rest.append({"type": "text", "text": f"Result: {output}"})
            elif item.get("type") != "function_call" and item.get("role") != "assistant":
                text = _text(item.get("content"))
                if text.strip():
                    rest.append({"type": "text", "text": text})
        results += [{"type": "tool_result", "tool_use_id": c, "content": "(no result was recorded)", "is_error": True} for c in sorted(calls)]
        blocks = results + rest + ([{"type": "text", "text": note}] if note else [])
        if self.turns[-1]["role"] == "user":  # before the first answer: the opening turn is not sent yet
            self.turns[-1] = {"role": "user", "content": self.turns[-1]["content"] + blocks}
        elif blocks:
            self.turns.append({"role": "user", "content": blocks})
        else:
            raise ValueError("nothing to send after the last answer")
        self.cursor = len(current)
        if len(self.turns) > MAX_TURNS:
            raise ValueError(f"the conversation holds {len(self.turns)} turns, more than {MAX_TURNS}")
        turns = copy.deepcopy(self.turns)
        turns[-1]["content"][-1]["cache_control"] = dict(MARK)
        return turns

    def record(self, content: Sequence[Mapping[str, Any]], cursor: int) -> None:
        """The answer, exactly as it came, as the next assistant turn; `cursor` is how many of this cycle's items the loop
        holds after appending the answer's own (they are this turn, not the next)."""
        if content:
            self.turns.append({"role": "assistant", "content": copy.deepcopy(list(content))})
        self.cursor = cursor


__all__ = ["ClaudeSession", "ClaudeTurn", "ToolCall", "anthropic_messages", "anthropic_tools", "check_input", "resolve_name",
           "sail_items", "tool_calls", "validate", "MAX_TURNS", "MARK"]
