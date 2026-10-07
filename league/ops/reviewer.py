"""The engineer's reviewer (LTCM v3, Phase 4, B5): an adversarial read of one pull request's exact diff.

A second Claude role (`reviewer`, Opus 5.5, at most $1 a review, through `ModelRouter.ask`: its own line, the funded
room, the gateway's meter) reads the EXACT change the pull request carries and the contract it must keep, and answers
approve or reject with reasons. The engineer job posts the verdict to the gateway (`POST /v1/github/review`, for that
exact head commit), which the merge route requires.

THE EXACT DIFF. The gateway's `GET /v1/github/pr/<n>` names the head commit; the repository is public, so the House
downloads the tarball of exactly that commit (codeload, unauthenticated, as the updater does) and of the `main` commit
the pull request was cut from, and compares the two trees (`tar_index`, `tree_changes`). Before any model reads it, the
comparison is checked by code (`mechanical`): the pull request must change exactly the candidate's files, each to exactly
the candidate's bytes. A mismatch is a reject with no model call. What the reviewer reads is the unified diff of those
files (`unified_diff`).

THE CONTRACT (`contract_text`): the lane, its predeclared metric and effect, the files it may touch, the canary gate it
must sit under (arms lanes), and the review checklist of `playbooks/harness-improvement.md` ("The adversarial review").
All of it is fixed text and the public repository's own code: no Validation or holdout figure, no family name, no date.

A money-path candidate (a module the live path loads) needs two approving reviews (`harness_lanes.DEPLOY_RULES`): two
independent calls, the second told it is the second. A review that cannot be read as a verdict is a reject (fail closed).

Standard library only.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import tarfile
from pathlib import Path
from typing import Any, Mapping, Sequence

TREES = ("league", "ltcm", "playbooks", "scripts", "deploy")
#: The reviewer's hard cap a review (the brief: at most $1).
USD_CAP = 1.0
DIFF_CONTEXT = 12
MAX_DIFF_CHARS = 120_000
SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["approve", "reject"]},
                   "reasons": {"type": "array", "items": {"type": "string"}}},
    "required": ["verdict", "reasons"], "additionalProperties": False,
}

SYSTEM = """You are the adversarial reviewer of an automated harness change to an autonomous options-research swarm.
Another agent (the engineer) wrote the change to move one predeclared operational metric. Your job is to try to break
it, then answer approve or reject. Approve only a change you could not break.

The hard walls the change must keep:
- It touches only the files its lane allows, and never the objective, the evaluator, sealed data, spend limits,
  capital permissions, the release train, the judges or the canary gate (the machine checks already refused those).
- It never changes, by any route, a trial count, a lineage, an eligibility mark, a look, the graveyard, the cycle
  record or a practice receipt (a record writer reached through a helper, a callback, a guarded binding passed to new
  code and mutated there, an element of a guarded list).
- No text a model reads gains a Validation or holdout figure, a check's name, or forward evidence (through the store, a
  family's state, a tool's answer or a cached object).
- It does not write, move or delete a file (the canary file included), open a process or a connection, or reach a
  refused module through one already loaded.
- In an arms lane, every change sits in `if canary.enabled(KEY, unit, root=...): new else: old` with the old branch
  the baseline's own code: with the gate closed nothing may run differently (no new module-level effect, no dispatch
  by name, no changed default, no shared state an arm's branch mutates and the control reads). The gate is asked about
  the lane's unit (a family id in the research lane; canary.mechanism_unit(...) of the admitted text in the memory lane).
- It does what the bottleneck needs, not what a narrow example alone rewards. In the memory lane a refusal may rest
  only on the proposal's words against the graveyard's, never on surface features of the proposal (length, sentence
  shape, keyword density, a citation's form, its place in a batch, a fixed list of texts).
- The code is correct: no crash on the paths it changes, no silent behaviour change outside the gate, no new
  unbounded cost (loops, model calls, file reads) on the House's one CPU.

Answer with JSON only: {"verdict": "approve" or "reject", "reasons": ["...", ...]}. Give 1 to 8 reasons, each one
short sentence naming the exact code it is about. A reject says what must change."""


def tar_index(tarball: bytes, *, want: Sequence[str] = ()) -> tuple[dict[str, str], dict[str, str]]:
    """({path: sha256} of every regular file under the release trees, {path: text} of the `want` paths) of a GitHub
    tarball (its top `<repo>-<sha>/` directory dropped)."""
    wanted = set(want)
    hashes: dict[str, str] = {}
    texts: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        for member in archive:
            parts = Path(member.name).parts[1:]
            if not parts or parts[0] not in TREES or not member.isfile():
                continue
            rel = "/".join(parts)
            source = archive.extractfile(member)
            if source is None:
                continue
            data = source.read()
            hashes[rel] = hashlib.sha256(data).hexdigest()
            if rel in wanted:
                texts[rel] = data.decode("utf-8", "replace")
    return hashes, texts


def tree_changes(before: Mapping[str, str], after: Mapping[str, str]) -> list[str]:
    """Every path added, removed or changed between two `tar_index` hash maps, sorted."""
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def mechanical(changed: Sequence[str], head_texts: Mapping[str, str], expected: Mapping[str, str]) -> list[str]:
    """Code's own check of the exact pull request: it changes exactly `expected`'s paths, each to exactly its text."""
    problems = []
    extra = sorted(set(changed) - set(expected))
    missing = sorted(set(expected) - set(changed))
    if extra:
        problems.append(f"the pull request changes files the candidate did not: {extra[:8]}")
    if missing:
        problems.append(f"the pull request does not carry the candidate's change to {missing[:8]}")
    for path, text in expected.items():
        if path in changed and head_texts.get(path) != text:
            problems.append(f"{path}: the pull request's bytes are not the candidate's")
    return problems


def unified_diff(files: Mapping[str, tuple[str | None, str]], *, context: int = DIFF_CONTEXT) -> str:
    """The unified diff of `{path: (before or None, after)}`."""
    out = []
    for path, (before, after) in sorted(files.items()):
        out.extend(difflib.unified_diff((before or "").splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"a/{path}" if before is not None else "/dev/null", tofile=f"b/{path}",
                                        n=context))
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
    return "".join(out)


def contract_text(*, lane: str, metric: str, key: str, release_class: str) -> str:
    """The contract a reviewer judges against (fixed text and the lane's own definition)."""
    from ..swarm import harness_lanes as lanes
    from .author import NEW_TEST, writable_paths

    spec = lanes.LANES[lane]
    bottleneck = spec.bottleneck(metric)
    m = bottleneck.metric
    canary = spec.canary_for(bottleneck)
    lines = [f"Lane: {spec.id} ({spec.title}).",
             f"Bottleneck: {bottleneck.summary}",
             f"Predeclared metric: {m.name} = {m.numerator} / {m.denominator}, {m.direction} is better; the canary must "
             f"show a relative improvement of at least {m.min_effect:.0%} against the control.",
             "Must not worsen: " + (", ".join(x.name for x in list(bottleneck.secondary) + list(spec.guards)) or "nothing listed") + ".",
             f"Files the lane may change: {', '.join(writable_paths(lane))}, and one new test file {NEW_TEST}.",
             f"Release class: {release_class} ({lanes.DEPLOY_RULES.get(release_class, '')}).",
             f"Canary: {canary.get('mode')} over {canary.get('unit')} units."]
    if canary.get("mode") == "arms":
        unit = ("a name for the family id (fam['id'])" if canary.get("unit") == "family" else
                "canary.mechanism_unit(mechanism) of the admitted text")
        lines.append(f"Gate: every change must sit under canary.enabled({key!r}, <unit>, root=<the swarm state directory>) "
                     f"with <unit> {unit}, the else branch the baseline's own code.")
    return "\n".join(lines)


def _ascii(text: Any, limit: int) -> str:
    return str(text or "").encode("ascii", "replace").decode("ascii")[:limit]


def prompt(*, contract: str, diff: str, claims: Mapping[str, str], guards: str, second: bool) -> str:
    claim_lines = "\n".join(f"- {k}: {_ascii(v, 1500)}" for k, v in claims.items() if v)
    return ("THE CONTRACT\n" + contract + "\n\nTHE AUTHOR'S CLAIMS (an interested party: verify, do not trust)\n"
            + (claim_lines or "- (none)") + "\n\nTHE MACHINE CHECKS\n" + guards
            + ("\n\nYou are the SECOND of two independent money-path reviewers: review from scratch." if second else "")
            + "\n\nTHE EXACT DIFF OF THE PULL REQUEST\n" + diff)


def verdict_of(answer: Mapping[str, Any] | None) -> tuple[str, list[str]] | None:
    """(verdict, reasons) from a model answer's JSON, or None when it is not one."""
    if not isinstance(answer, Mapping):
        return None
    verdict = answer.get("verdict")
    reasons = answer.get("reasons")
    if verdict not in ("approve", "reject"):
        return None
    if isinstance(reasons, str):
        reasons = [reasons]
    if not isinstance(reasons, list):
        return None
    cleaned = [" ".join(str(r).split())[:900] for r in reasons if str(r).strip()][:12]
    return (verdict, cleaned) if cleaned else None


def review(router: Any, *, request_key: str, contract: str, files: Mapping[str, tuple[str | None, str]],
           claims: Mapping[str, str], guards: str, second: bool = False, usd_cap: float = USD_CAP,
           effort: str = "high") -> dict[str, Any]:
    """One review: {"verdict", "reasons", "usd", "ok"}. `ok` False when no review could be had (no room, the role is not
    configured, the model erred): the caller asks again later. A review that is not a readable verdict is a reject."""
    from ..swarm.models import ModelError

    usd_cap = min(float(usd_cap), USD_CAP)
    diff = ""
    user = ""
    for context in (DIFF_CONTEXT, 4, 1):
        diff = unified_diff(files, context=context)
        if len(diff) > MAX_DIFF_CHARS:
            continue
        user = prompt(contract=contract, diff=diff, claims=claims, guards=guards, second=second)
        try:
            _, ceiling = router.claude_request(SYSTEM, user, schema=SCHEMA, effort=effort, role="reviewer")
        except Exception as exc:  # noqa: BLE001 - a body that cannot be built is no review
            return {"ok": False, "why": f"the review request could not be built: {type(exc).__name__}: {str(exc)[:200]}",
                    "usd": 0.0}
        if float(ceiling) <= usd_cap:
            break
    else:
        return {"ok": True, "verdict": "reject", "usd": 0.0,
                "reasons": [f"the diff is too large to review within ${usd_cap:.2f}: split the change"]}
    try:
        answer = router.ask(role="reviewer", system=SYSTEM, user=user, family=None, key=request_key, openai_model=None,
                            sail_profile=None, claude=True, schema=SCHEMA, claude_effort=effort, need_usd=0.0)
    except ModelError as exc:
        billed = sum(float(b.get("cost_usd") or 0.0) for b in exc.billed) + float(exc.held_usd or 0.0)
        return {"ok": False, "why": f"no review: {str(exc)[:300]}", "usd": round(billed, 6)}
    usd = float(answer.get("cost_usd") if answer.get("cost_usd") is not None else answer.get("held_usd") or 0.0)
    found = verdict_of(answer.get("json")) or verdict_of(_loads(answer.get("text")))
    if found is None:
        return {"ok": True, "verdict": "reject", "usd": round(usd, 6),
                "reasons": ["the review did not come back as a verdict: fail closed"]}
    return {"ok": True, "verdict": found[0], "reasons": found[1], "usd": round(usd, 6)}


def _loads(text: Any) -> Any:
    from ..swarm.models import extract_json

    return extract_json(str(text or ""))


__all__ = ["SYSTEM", "SCHEMA", "USD_CAP", "tar_index", "tree_changes", "mechanical", "unified_diff", "contract_text",
           "prompt", "review", "verdict_of"]
