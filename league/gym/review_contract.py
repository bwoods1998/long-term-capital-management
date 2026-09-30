"""Source-grounded context for the two independent gate readers; no market data or sealed results."""

from __future__ import annotations

import ast
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from . import ENGINE_VERSION
from .experiment import CONTRACT_VERSION

FACTS = {
    "state": "Program.start creates a new Runner and executes the module in a fresh namespace. Module STATE persists "
             "between that runner's decisions and sessions, never across independent replay runs. Causal within-run "
             "state is permitted. Claim cross-run leakage only with a concrete route beyond this fresh namespace.",
    "parameters": "Overrides are merged and bound to PARAMS at its declaration, before aliases, derived module values "
                  "and helper defaults capture values. ctx.params receives the same initial values. Parameter changes "
                  "need an effective behavioral ablation; syntactic access alone does not prove the switch works.",
    "context": "Only the supplied context fields exist. Underlying objects have attributes, not dict subscripts. "
               "No date, year, session_id or bar_id is supplied. Propose repairs against the actual fields below. "
               "Arrays contain current/past observations and prior-session history; they are read-only copies.",
    "calendar": "Date/year literals, hard-coded absolute price regimes, and reconstruction of historical dates to "
                "select known periods are prohibited. Relative signals and causal within-run state are permitted. "
                "A dynamically observed prior close used for deduplication is not itself a hard-coded price level; "
                "it can still have collisions. Identify the actual data flow and failure mechanism.",
    "fills": "Orders first meet the next minute's quotes. Natural fills are size limited; passive fills are modelled "
             "only in calibrated coverage and penalized by stress/adverse-selection rules. Bounded packages cannot "
             "fill outside their payoff bounds. Intent is not a fill. Identify a concrete unsupported assumption.",
    "risk": "Only supported defined-risk structures may execute. Venue cutoffs, sizing, fees and order limits are "
            "enforced by the engine and live adapter. Research support does not imply live-adapter support.",
}


def _node_source(source: str, path: tuple[str, ...]) -> str:
    nodes = ast.parse(source).body
    for name in path:
        node = next(n for n in nodes if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
        nodes = node.body
    return ast.get_source_segment(source, node) or ""


@lru_cache(maxsize=1)
def review_contract() -> dict[str, Any]:
    """Fingerprint actual loaded source files and include the critical implementation/API excerpts."""
    root = Path(__file__).resolve().parent
    sources = {name: (root / name).read_text() for name in ("runtime.py", "safety.py", "ctx.py", "engine.py", "fills.py",
                                                          "experiment.py", "review_contract.py")}
    excerpt = {}
    for filename, path in (("runtime.py", ("Program", "start")), ("runtime.py", ("_fresh_namespace",)),
                           ("runtime.py", ("load_program",)), ("runtime.py", ("Runner", "__init__"))):
        excerpt[filename + ":" + ".".join(path)] = _node_source(sources[filename], path)
    fields = {}
    for node in ast.parse(sources["ctx.py"]).body:
        if isinstance(node, ast.ClassDef) and node.name in ("Ctx", "UnderlyingView", "ChainView"):
            for child in node.body:
                if isinstance(child, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__slots__" for t in child.targets):
                    fields[node.name] = [name for name in ast.literal_eval(child.value) if not name.startswith("_")]
    packet = {"engine": ENGINE_VERSION, "parameter_contract": CONTRACT_VERSION, "facts": FACTS, "context_fields": fields,
              "source_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in sources.items()},
              "source_excerpts": excerpt}
    return {"sha256": hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest(), **packet}


def grounded_answer(answer: Mapping[str, Any], code: str) -> dict[str, Any]:
    """A rejection needs a source location, a real contract reference and a causal counterexample.

    This verifies the receipt's shape/location, not the truth of the model's conclusion. Ungrounded
    failures become unclear and therefore cannot open a holdout; existing retry limits still apply.
    No model rejection is converted to a pass.
    """
    raw = answer.get("json") or {}
    if not isinstance(raw, Mapping):
        raw = {}
    verdict = raw.get("verdict") if raw.get("verdict") in ("pass", "fail") else "unclear"
    reasons = raw.get("reasons") or []
    reasons = [str(reason)[:500] for reason in reasons[:6]] if isinstance(reasons, list) else [str(reasons)[:500]]
    findings = raw.get("findings") or []
    verified = []
    if isinstance(findings, list):
        for finding in findings[:6]:
            if not isinstance(finding, Mapping):
                continue
            quote = finding.get("code_excerpt")
            reference = finding.get("contract_reference")
            counterexample = finding.get("counterexample")
            if (isinstance(quote, str) and len(quote.strip()) >= 4 and quote in code and reference in FACTS and
                    isinstance(counterexample, str) and len(counterexample.strip()) >= 20):
                verified.append({"code_excerpt": quote[:1000], "contract_reference": reference,
                                 "counterexample": counterexample[:1500]})
    missing = verdict == "fail" and (not verified or len(verified) != len(findings))
    return {"verdict": "unclear" if missing else verdict, "claimed_verdict": verdict, "reasons": reasons,
            "findings": verified, "grounding": "missing source-grounded counterexample; another review is required" if missing else
            "source references checked; factual claims still require review", "contract_sha": review_contract()["sha256"],
            "route": answer.get("route"), "model": answer.get("model"), "cost_usd": answer.get("cost_usd")}


__all__ = ["review_contract", "grounded_answer"]
