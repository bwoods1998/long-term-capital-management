"""Cheap experiment checks without importing numpy, loading market data, or executing agent code.

This is a contract check, never a profitability or activity gate. A parameter is called unread only
when all uses can be resolved statically; dynamic keys or an escaping mapping make the answer unknown.
An experiment that is valid but trades zero times is still evidence to diagnose, not invalid code.
"""

from __future__ import annotations

import ast
from typing import Any, Mapping

from .safety import CodeRefused, check_program, params_declaration

CONTRACT_VERSION = "params-declaration-v2"


def parameter_reads(tree: ast.Module) -> set[str] | None:
    """Known keys read, or None if a mapping/key escapes static analysis (conservatively accepted)."""
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    aliases = {"PARAMS"}
    bindings: set[ast.AST] = set()

    def reference(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in aliases or
                isinstance(node, ast.Attribute) and node.attr == "params")

    # Alias chains and helper default captures: p = PARAMS; q = p; def helper(p=PARAMS).
    changed = True
    while changed:
        previous = set(aliases)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and reference(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if all(isinstance(target, ast.Name) for target in targets):
                    aliases.update(target.id for target in targets)
                    bindings.add(node.value)
            elif isinstance(node, ast.arguments):
                arguments = node.posonlyargs + node.args
                pairs = list(zip(arguments[-len(node.defaults):], node.defaults)) if node.defaults else []
                pairs += list(zip(node.kwonlyargs, node.kw_defaults))
                for argument, default in pairs:
                    if default is not None and reference(default):
                        aliases.add(argument.arg)
                        bindings.add(default)
        changed = aliases != previous

    keys: set[str] = set()
    for node in ast.walk(tree):
        # getattr(ctx, "params") and other reflected access must never yield a false unread finding.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr"):
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value == "params":
                return None
        if not reference(node) or node in bindings:
            continue
        parent = parents.get(node)
        key = None
        if isinstance(parent, ast.Subscript) and parent.value is node:
            key = parent.slice
        elif isinstance(parent, ast.Attribute) and parent.attr == "get":
            call = parents.get(parent)
            if isinstance(call, ast.Call) and call.func is parent and call.args:
                key = call.args[0]
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            return None
        keys.add(key.value)
    return keys


def check_experiment(code: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a small receipt or raise CodeRefused before a run/sweep creates any version or job.

    Literal PARAMS is required for this static research interface, as it already was for sweeps.
    Runtime load_program remains able to evaluate computed defaults in isolated Gym processes.
    Only *changed* unread overrides are refused: unused defaults or explicit default values do not
    make a baseline invalid. Existing deduplication handles variants with the same effective values.
    """
    from .runtime import canonical, merge_params, parse_needs

    check_program(code)
    tree = ast.parse(code)
    declaration = params_declaration(tree)
    # Literal NEEDS can be fully checked without executing the module. Computed declarations still
    # receive the runtime's normal validation; this static check makes no claim about their value.
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == "NEEDS" for target in targets):
            try:
                needs = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue
            parse_needs(needs)
    try:
        defaults = ast.literal_eval(declaration.value)
    except (ValueError, TypeError, SyntaxError):
        raise CodeRefused("research PARAMS must be a literal dict so variants can be checked before replay") from None
    base = merge_params(defaults, None)
    merged = merge_params(defaults, params)
    reads = parameter_reads(tree)
    changed = sorted(key for key in merged if canonical(merged[key]) != canonical(base[key]))
    unread = sorted(set(changed) - reads) if reads is not None else []
    if unread:
        raise CodeRefused("changed parameter(s) never read by this program: " + ", ".join(unread) +
                          "; use the requested values through ctx.params or PARAMS before replay")
    return {"contract": CONTRACT_VERSION, "params": merged, "changed": changed,
            "parameter_reads": sorted(reads) if reads is not None else None,
            "limits": "static contract only; no assertion about activity, profitability or semantic effect"}


__all__ = ["CONTRACT_VERSION", "check_experiment", "parameter_reads"]
