"""What a Gym program may contain: numpy and math, no I/O, no way out, and no calendar.

A program is one Python file an agent wrote (`PROGRAM.md`). It runs inside the engine's process on a
sealed box, and the live path runs the same file in the House, so this check is a wall, not advice.
It is the league's strategy check (`league/safety.py`, hardened against real attempts) with the
Gym's rules on top:

- imports: `math` and `numpy` only (plus `from __future__ import annotations`); no submodule import;
- no underscore attribute, no attribute assignment, no frame or code object, no `getattr` with a
  computed name, none of `league.safety.BANNED_NAMES` (eval, exec, open, globals, ...), and no `print`;
- numpy's doors to files, memory, randomness and dates are shut by name: `load`, `save*`, `fromfile`,
  `tofile`, `memmap`, `lib`, `ctypes`, `ctypeslib`, `random`, `datetime64`, `busday_*`, `base`,
  `setflags`, `seterr`, `testing`, ... (`NUMPY_BANNED`);
- no date: an integer or float literal from 2019 to 2030 (a year), an eight-digit YYYYMMDD integer,
  or a string holding an ISO date or such a year is refused. The models know what happened in those
  years; a program that could recognize one could replay it.

Standard library only (the live path imports it without numpy).
"""

from __future__ import annotations

import ast
import re
from typing import Any

from ..safety import BANNED_ATTRIBUTES, BANNED_NAMES, CodeRefused

MAX_CODE_CHARS = 60_000
ALLOWED_IMPORTS = frozenset({"math", "numpy"})
NUMPY_BANNED = frozenset({
    # files and serialized arrays
    "load", "loads", "save", "savez", "savez_compressed", "savetxt", "loadtxt", "genfromtxt", "fromfile", "tofile",
    "fromregex", "memmap", "open_memmap", "DataSource", "dump", "dumps", "tobytes_file",
    # memory, pointers and internals
    "lib", "ctypes", "ctypeslib", "base", "setflags", "from_dlpack", "frombuffer", "getbuffer", "newbuffer",
    "f2py", "distutils", "testing", "typing", "core", "rec", "ma", "char", "strings", "polynomial_utils",
    "show_config", "show_runtime", "info", "source", "lookfor", "get_include",
    # global state the engine shares
    "seterr", "seterrcall", "setbufsize", "set_printoptions", "set_string_function", "_set_promotion_state",
    # randomness (a program is deterministic) and the calendar
    "random", "datetime64", "timedelta64", "datetime_data", "datetime_as_string", "busday_count", "busday_offset",
    "is_busday", "busdaycalendar",
})
#: Output, class machinery, and the two builtins whose answers change from one process to the next
#: (`id` is an address, `hash` of a string is salted per process): a program is deterministic.
EXTRA_BANNED_NAMES = frozenset({"print", "type", "object", "super", "classmethod", "staticmethod", "property",
                                "id", "hash", "dir", "aiter", "anext"})
_YEAR_TEXT = re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}[-/.][01]?[0-9][-/.][0-3]?[0-9](?![0-9])|(?<![0-9])20(?:19|2[0-9]|30)(?![0-9])")


def _date_int(value: int) -> bool:
    if 2019 <= value <= 2030:
        return True
    if 19_000_101 <= value <= 20_301_231:
        month, day = (value // 100) % 100, value % 100
        return 1 <= month <= 12 and 1 <= day <= 31
    return False


def check_program(code: str) -> None:
    """Raise `CodeRefused` (naming the line and the rule) unless `code` is an admissible program:
    safe, date-free, and defining `NEEDS`, `PARAMS` and one `decide(ctx)` at the top level."""
    text = str(code or "")
    if not text.strip():
        raise CodeRefused("the program is empty")
    if len(text) > MAX_CODE_CHARS:
        raise CodeRefused(f"the program is over {MAX_CODE_CHARS} characters")
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError) as exc:
        raise CodeRefused(f"the program does not compile: {str(exc)[:160]}") from None
    banned_attributes = BANNED_ATTRIBUTES | NUMPY_BANNED
    banned_names = BANNED_NAMES | EXTRA_BANNED_NAMES

    def refuse(node: Any, why: str) -> None:
        raise CodeRefused(f"line {getattr(node, 'lineno', '?')}: {why}")

    literal_getattr: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr"):
            name = node.args[1] if len(node.args) >= 2 else None
            if (isinstance(name, ast.Constant) and isinstance(name.value, str) and not name.value.startswith("_")
                    and name.value not in banned_attributes and len(node.args) <= 3 and not node.keywords):
                literal_getattr.add(id(node.func))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_IMPORTS:
                    refuse(node, f"import {alias.name} is not allowed; a program imports only math and numpy")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            if node.level:
                refuse(node, "a relative import is not allowed")
            if module == "__future__":
                if any(alias.name != "annotations" for alias in node.names):
                    refuse(node, "only `from __future__ import annotations` is allowed")
                continue
            if module not in ALLOWED_IMPORTS:
                refuse(node, f"from {module} import is not allowed; a program imports only math and numpy")
            for alias in node.names:
                if alias.name == "*" or alias.name.startswith("_") or alias.name in banned_attributes:
                    refuse(node, f"from {module} import {alias.name} is not allowed")
        elif isinstance(node, ast.Attribute):
            if not isinstance(node.ctx, ast.Load):
                refuse(node, f"assigning or deleting an attribute (.{node.attr}) is not allowed; keep state in dicts")
            if node.attr.startswith("_") or node.attr in banned_attributes:
                refuse(node, f".{node.attr} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__"):
                refuse(node, f"{node.id} is not allowed")
            if node.id in banned_names:
                refuse(node, f"{node.id} is not allowed" + ("; a program has no output (return a `note` instead)" if node.id == "print" else ""))
            if node.id == "getattr" and id(node) not in literal_getattr:
                refuse(node, "getattr takes a literal attribute name here")
            if node.id == "hasattr" and id(node) not in literal_getattr:
                refuse(node, "hasattr takes a literal attribute name here")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            name = getattr(node, "name", "")
            if name.startswith("__"):
                refuse(node, f"defining {name} is not allowed")
            if isinstance(node, ast.ClassDef):
                refuse(node, "a program defines functions, not classes (keep state in dicts)")
            if isinstance(node, ast.AsyncFunctionDef):
                refuse(node, "async code is not allowed")
            for deco in getattr(node, "decorator_list", []):
                refuse(deco, "decorators are not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if any(name.startswith("__") for name in node.names):
                refuse(node, "a dunder global is not allowed")
        elif isinstance(node, (ast.Await, ast.Yield, ast.YieldFrom, ast.AsyncFor, ast.AsyncWith)):
            refuse(node, "generators and async code are not allowed")
        elif isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool):
                continue
            if isinstance(value, int) and _date_int(value):
                refuse(node, f"the literal {value} reads as a year or a date; a program never names the calendar")
            if isinstance(value, float) and value.is_integer() and _date_int(int(value)):
                refuse(node, f"the literal {value} reads as a year; a program never names the calendar")
            if isinstance(value, (str, bytes)):
                raw = value.decode("latin-1") if isinstance(value, bytes) else value
                if _YEAR_TEXT.search(raw):
                    refuse(node, "a string naming a year or a date is not allowed; a program never names the calendar")
        elif isinstance(node, ast.MatchClass):
            refuse(node, "class patterns are not allowed")

    decides = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "decide"]
    if len(decides) != 1:
        raise CodeRefused("a program defines exactly one top-level function decide(ctx)")
    args = decides[0].args
    if len(args.args) != 1 or args.vararg or args.kwarg or args.kwonlyargs:
        raise CodeRefused("decide takes exactly one argument, ctx")
    assigned = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    for name in ("NEEDS", "PARAMS"):
        if name not in assigned:
            raise CodeRefused(f"a program assigns {name} at the top level (PROGRAM.md)")


__all__ = ["check_program", "CodeRefused", "NUMPY_BANNED", "ALLOWED_IMPORTS"]
