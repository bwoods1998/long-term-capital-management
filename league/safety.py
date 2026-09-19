"""What a strategy program may contain.

A strategy is code an agent (or the architect) wrote. It runs in the agent's own Sailbox, never in
the House's process, and the box has no network and no credential. This check is the second wall:
the same replay simulator scores the code inside that box, and code that could reach the
interpreter could print its own score (the first run caught a candidate doing exactly that with
an `atexit` handler on Sept 16, 2026). So a strategy imports only `SAFE_MODULES`, never touches an
underscore attribute, a frame or a module that a safe module re-exports, never assigns an
attribute, and never uses `BANNED_NAMES`. Ported unchanged from the first run's
`ltcm/foundry.py`, where it was hardened against real attempts.

This module imports nothing from the league, so it ships to the agent box as it is.
"""

from __future__ import annotations

import ast
import importlib
import types
from typing import Any

MAX_CODE_CHARS = 40_000


class CodeRefused(ValueError):
    """The strategy code breaks a rule. The message names the line and the rule."""


SAFE_MODULES = frozenset({
    "__future__", "bisect", "collections", "datetime", "decimal", "fractions", "functools", "heapq",
    "itertools", "json", "math", "random", "re", "statistics", "time", "typing", "zoneinfo",
})
SAFE_TYPING = frozenset({
    "Any", "Callable", "DefaultDict", "Dict", "FrozenSet", "Iterable", "Iterator", "List", "Mapping",
    "MutableMapping", "Optional", "Sequence", "Set", "Tuple", "Union",
})
#: Names a strategy may not use at all: evaluation, files, the interpreter's namespaces, and
#: library helpers that set attributes or evaluate annotations on the caller's behalf.
BANNED_NAMES = frozenset({
    "__import__", "breakpoint", "compile", "delattr", "eval", "exec", "exit", "globals", "help", "input",
    "locals", "memoryview", "open", "quit", "setattr", "vars",
    "get_type_hints", "singledispatch", "singledispatchmethod", "total_ordering", "update_wrapper", "wraps",
})
#: Attributes a strategy may not read: frames and code, dynamic lookups, and the modules a safe
#: module happens to import (statistics.sys, typing.types, fractions.operator, ...).
BANNED_ATTRIBUTES = frozenset({
    "ag_await", "ag_code", "ag_frame", "co_code", "co_consts", "cr_await", "cr_code", "cr_frame", "cr_origin",
    "f_back", "f_builtins", "f_code", "f_globals", "f_locals", "f_trace", "gi_code", "gi_frame", "gi_suspended",
    "gi_yieldfrom", "tb_frame", "tb_next",
    "format", "format_map", "attrgetter", "methodcaller",
    "get_type_hints", "singledispatch", "singledispatchmethod", "total_ordering", "update_wrapper", "wraps",
    "asyncio", "atexit", "builtins", "codecs", "concurrent", "copyreg", "ctypes", "enum", "environ",
    "gc", "importlib", "inspect", "io", "labkit", "ltcm", "marshal", "modules", "multiprocessing", "nt", "numbers",
    "operator", "os", "pathlib", "pickle", "popen", "posix", "runpy", "shutil", "signal", "socket", "stderr", "stdin",
    "stdout", "string", "subprocess", "sys", "system", "tempfile", "threading", "traceback", "types", "typing",
    "warnings", "weakref",
})
_REEXPORTED: frozenset[str] | None = None


def _reexported_modules() -> frozenset[str]:
    """Attribute names under which a safe module exposes a module that is not safe."""
    global _REEXPORTED
    if _REEXPORTED is not None:
        return _REEXPORTED
    found: set[str] = set()
    seen: set[int] = set()

    def scan(module: Any, depth: int) -> None:
        if id(module) in seen or depth > 3:
            return
        seen.add(id(module))
        for attr in dir(module):
            if attr.startswith("_"):
                continue
            try:
                value = getattr(module, attr)
            except Exception:
                continue
            if isinstance(value, types.ModuleType):
                if value.__name__.split(".")[0] in SAFE_MODULES:
                    scan(value, depth + 1)
                elif attr != "copy":  # dict.copy() is everywhere; the copy module is harmless
                    found.add(attr)

    for name in sorted(SAFE_MODULES - {"__future__"}):
        try:
            scan(importlib.import_module(name), 0)
        except Exception:
            continue
    _REEXPORTED = frozenset(found)
    return _REEXPORTED


def check_strategy_code(code: str) -> None:
    """Refuse model-written strategy code that could reach outside `decide(kit, params)`.

    The backtest runs a candidate inside the engine's own process, and a candidate that reached
    the interpreter could print its own result or rewrite the engine's (Sept 16, 2026: a
    candidate that registered an `atexit` handler printed a result line that qualified). So a
    candidate imports only `SAFE_MODULES`; never reads or writes an attribute that starts with an
    underscore (`__name__` read aside), a frame, or a module a safe module re-exports; never
    assigns or deletes an attribute at all (a module's function or a shared class's method would
    change for the engine too); calls `getattr` only with a plain literal name; and never uses
    `BANNED_NAMES` (evaluation, files, namespaces, `str.format` field lookups). Raises CodeRefused
    with the first reason."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError) as exc:
        raise CodeRefused(f"the code does not compile: {str(exc)[:120]}") from None
    banned_attributes = BANNED_ATTRIBUTES | _reexported_modules()
    literal_getattr: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr"):
            name = node.args[1] if len(node.args) >= 2 else None
            if (
                isinstance(name, ast.Constant) and isinstance(name.value, str) and not name.value.startswith("_")
                and name.value not in banned_attributes and len(node.args) <= 3 and not node.keywords
            ):
                literal_getattr.add(id(node.func))

    def refuse(node: Any, text: str) -> None:
        raise CodeRefused(f"line {getattr(node, 'lineno', '?')}: {text}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_MODULES or root in ("typing", "__future__"):
                    refuse(node, f"import {alias.name} is not allowed; a strategy imports only {', '.join(sorted(SAFE_MODULES - {'__future__'}))}")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            if node.level or module.split(".")[0] not in SAFE_MODULES:
                refuse(node, f"from {'.' * node.level}{module} import is not allowed")
            for alias in node.names:
                if alias.name == "*" or alias.name.startswith("_") or alias.name in banned_attributes:
                    refuse(node, f"from {module} import {alias.name} is not allowed")
                if module == "typing" and alias.name not in SAFE_TYPING:
                    refuse(node, f"from typing import {alias.name} is not allowed")
                if module == "__future__" and alias.name != "annotations":
                    refuse(node, f"from __future__ import {alias.name} is not allowed")
        elif isinstance(node, ast.Attribute):
            if not isinstance(node.ctx, ast.Load):
                refuse(node, f"assigning or deleting an attribute (.{node.attr}) is not allowed; keep state in dicts")
            if (node.attr.startswith("_") and node.attr != "__name__") or node.attr in banned_attributes:
                refuse(node, f".{node.attr} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id != "__name__":
                refuse(node, f"{node.id} is not allowed")
            if node.id in BANNED_NAMES:
                refuse(node, f"{node.id} is not allowed")
            if node.id == "getattr" and id(node) not in literal_getattr:
                refuse(node, "getattr takes a literal attribute name here")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("__"):
                refuse(node, f"defining {node.name} is not allowed")
            if isinstance(node, ast.ClassDef) and node.keywords:
                refuse(node, "class keywords (a metaclass) are not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if any(name.startswith("__") for name in node.names):
                refuse(node, "a dunder global is not allowed")
        elif isinstance(node, ast.MatchClass):
            for attr in node.kwd_attrs:
                if attr.startswith("_") or attr in banned_attributes:
                    refuse(node, f"matching on .{attr} is not allowed")


def check_code(code: str) -> None:
    """Raise `CodeRefused` unless `code` is a well-formed strategy: safe, and defining `decide`."""
    text = str(code or "")
    if not text.strip():
        raise CodeRefused("the strategy is empty")
    if len(text) > MAX_CODE_CHARS:
        raise CodeRefused(f"the strategy is over {MAX_CODE_CHARS} characters")
    check_strategy_code(text)
    tree = ast.parse(text)
    decides = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "decide"]
    if len(decides) != 1:
        raise CodeRefused("a strategy defines exactly one top-level function decide(ctx)")
    if len(decides[0].args.args) != 1:
        raise CodeRefused("decide takes exactly one argument, ctx")
