"""research-workflow-v3: how many programs that cannot run still reach a Gym replay, and how many sound ones are stopped.

The tree under test screens each synthetic program the way its researcher does before a Train run is spent: the static
experiment check (`league.gym.experiment.check_experiment`), the researcher's own admission (`Researcher._admit`, where
a research-lane candidate gates its change per family) and the runtime preflight when the tree has one
(`league.swarm.preflight.screen(code, params, roots=...)` if defined, else `preflight.run` on an in-process decider).
A BROKEN program errs on the calls the Gym would make (25 errors disqualify a run) or is refused by the Gym's worker; a
VALID one never errs. Labels are fixed by construction, never by the tree under test.

dev (this file): the failure shapes of the Sept 30, 2026 House disqualifications (list used as a mapping, the underlying
read as a dict, arithmetic and comparison on None, a root not in NEEDS, NEEDS out of bounds, a JSON literal, a misspelled
name) plus sound controls. heldout: PRIVATE classes the dev split never uses (misuses at decide time, load failures,
placements that err only at some minutes, sound programs of other shapes), from the lane's pool, which lives outside this
public repo and reaches the judge only on standard input (`_common.args`, `--pool-stdin`); every class in every
placement, inside a random sound body with random names, from a seed that exists only once the candidate is committed.

Answer: broken_reaching_gym, broken_cases, false_refusals, gym_seconds_wasted (broken_reaching_gym x GYM_SECONDS_PER_DQ,
the mean Gym seconds a disqualified Train run's cycle took on the House, Sept 29-30, 2026), screen_cpu_seconds (the
screens' process CPU time, the lane's cost: CPU time, so a loaded machine does not charge a candidate for waiting),
screen_seconds (their wall time, reported), cases, and the refusals by stage and by misuse class.
"""
from __future__ import annotations

import itertools
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _common

PROTOCOL = "research-workflow-v3"
GYM_SECONDS_PER_DQ = 130.0
HEAD = ('import math\nimport numpy as np\n\n'
        'NEEDS = {{"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": {cadence}, "history": {history}}}\n'
        'PARAMS = {{"k": {k}, "on": True, "label": "a"}}\nSTATE = {{}}\n{extra}\n')

#: Sound programs (the dev split's controls).
VALID = {
    "last_price": ['u = ctx.under', 'if u is None:', '    return []', 'STATE["{a}"] = u.price'],
    "chain_median": ['c = ctx.chain', 'if c is None or c.n == 0:', '    return []', '{a} = float(np.median(c.mid))',
                     'STATE["{b}"] = {a}'],
    "close_return": ['u = ctx.under', 'if u is None or len(u.closes) < 2:', '    return []',
                     '{a} = u.closes[-1] / u.closes[-2] - 1.0', 'STATE["{b}"] = {a} * ctx.params.get("k", 1.0)'],
    "book_scan": ['for {a} in ctx.positions:', '    if {a}["qty"] > 99:', '        return []', 'for {b} in ctx.orders:',
                  '    if {b}["age_minutes"] > 30:', '        return []'],
    "event_gate": ['if ctx.events.get("fomc") or ctx.minutes_to_close < 10:', '    return []',
                   '{a} = ctx.params.get("k", 1.0) / 2.0', 'STATE["{b}"] = {a}'],
    "day_high": ['{a} = ctx.underlyings.get("SPY")', 'if {a} is None:', '    return []',
                 '{b} = float(np.max({a}.prices)) if len({a}.prices) else {a}.price', 'STATE["hi"] = {b}'],
}
#: The dev split's misuses at decide time: each errs on every call it runs.
MISUSE = {
    "positions_items": ['for {a}, {b} in ctx.positions.items():', '    pass'],
    "positions_values": ['for {a} in ctx.positions.values():', '    pass'],
    "under_subscript": ['{a} = ctx.under["price"]'],
    "under_get": ['{a} = ctx.under.get("price")'],
    "none_div": ['{a} = ctx.params.get("missing") / 2.0'],
    "none_compare": ['if ctx.params.get("missing") > 1.0:', '    pass'],
    "unknown_root": ['{a} = ctx.underlyings["QQQ"]'],
    "list_index_dict": ['{a} = ctx.orders[{{"id": 1}}]'],
    "ctx_needs": ['{a} = ctx.needs'],
    "undefined_name": ['{a} = PARES["k"]'],
}
#: The dev split's misuses before decide runs: the load fails or the Gym's worker refuses the program.
LOAD = {
    "json_true": {"extra": "{a} = true\n"},
    "needs_cadence": {"cadence": 45},
    "needs_history": {"history": 90},
}
DEV_BROKEN = [("positions_items", "always"), ("positions_values", "always"), ("under_subscript", "always"),
              ("under_get", "always"), ("none_div", "always"), ("none_compare", "always"), ("unknown_root", "always"),
              ("list_index_dict", "always"), ("ctx_needs", "always"), ("undefined_name", "always"),
              ("json_true", "load"), ("needs_cadence", "load"), ("needs_history", "load")]


def program(valid: str, *, misuse: str | None = None, wrap: str = "always", names=("px", "row"), k: float = 1.0,
            pool: dict | None = None) -> str:
    """A program from a sound body and, for a broken one, a misuse placed under a wrap (a list of lines whose last is
    the condition the misuse sits under; none: unconditional). `pool`: the private held-out classes, when drawn."""
    pool = pool or {}
    valids = {**VALID, **(pool.get("valid") or {})}
    misuses = {**MISUSE, **(pool.get("misuse") or {})}
    loads = {**LOAD, **(pool.get("load") or {})}
    wraps = pool.get("wraps") or {}
    template = valids[valid]
    a, b = names
    head: dict[str, Any] = {"cadence": 5, "history": 10, "k": k, "extra": ""}
    body: list[str] = []
    if misuse in loads:
        for key, value in loads[misuse].items():
            head[key] = value.format(a=a) if isinstance(value, str) else value
    elif misuse:
        lines = [line.format(a=a + "m", b=b + "m") for line in misuses[misuse]]
        guard = [line.format(a=a + "w", b=b + "w") for line in (wraps.get(wrap) or [])]
        if guard:
            body.extend(guard)
            body.extend("    " + line for line in lines)
        else:
            body.extend(lines)
    body.extend(line.format(a=a, b=b) for line in template)
    body.append("return []")
    return HEAD.format(**head) + "\ndef decide(ctx):\n" + "".join("    " + line + "\n" for line in body)


def cases(split: str, seed: str, pool: dict | None = None) -> list[dict[str, Any]]:
    out = []
    if split == "dev":
        bodies = sorted(VALID)
        for n, (misuse, wrap) in enumerate(DEV_BROKEN):
            out.append({"label": "broken", "class": misuse, "wrap": wrap,
                        "code": program(bodies[n % len(bodies)], misuse=misuse, wrap="always")})
        for n, valid in enumerate(bodies + ["close_return", "event_gate"]):
            out.append({"label": "valid", "class": valid, "wrap": "-", "code": program(valid, k=0.5 + n / 4)})
        return out
    if not pool:
        raise ValueError("the held-out split is drawn from the lane's private pool")
    r = _common.rng(seed, PROTOCOL)

    def name() -> str:
        return r.choice("abcdefghjkmnpqrstuvwxyz") + "".join(r.choice("abcdefghjkmnpqrstuvwxyz0123456789") for _ in range(5))

    held_valid = sorted(pool.get("valid") or {})
    bodies = sorted(VALID) + held_valid
    # Every held-out class in every placement (unconditional and each private wrap), each in a random sound body with
    # random names (stratified: the baseline's count on this split does not depend on the seed's luck).
    for misuse in sorted(pool.get("misuse") or {}):
        for wrap in ["always"] + sorted(pool.get("wraps") or {}):
            out.append({"label": "broken", "class": misuse, "wrap": wrap,
                        "code": program(r.choice(bodies), misuse=misuse, wrap=wrap, names=(name(), name()),
                                        k=round(r.uniform(0.1, 3.0), 3), pool=pool)})
    for misuse in sorted(pool.get("load") or {}):
        for _ in range(int(pool.get("load_draws", 2))):
            out.append({"label": "broken", "class": misuse, "wrap": "load",
                        "code": program(r.choice(bodies), misuse=misuse, names=(name(), name()),
                                        k=round(r.uniform(0.1, 3.0), 3), pool=pool)})
    for valid in held_valid * int(pool.get("valid_repeats", 2)) + [r.choice(sorted(VALID))
                                                                    for _ in range(int(pool.get("valid_draws", 6)))]:
        out.append({"label": "valid", "class": valid, "wrap": "-",
                    "code": program(valid, names=(name(), name()), k=round(r.uniform(0.1, 3.0), 3), pool=pool)})
    r.shuffle(out)
    return out


def screens():
    """The tree's pre-Gym screens in the researcher's order; absent ones are skipped (the baseline may lack one)."""
    try:
        from league.gym.experiment import check_experiment
    except ImportError:  # pragma: no cover - every supported tree has it
        check_experiment = None
    admit = None
    try:
        from league.swarm.researcher import Researcher
        from league.swarm.store import SwarmStore

        store = SwarmStore(Path(tempfile.mkdtemp(prefix="judge-research-")), clock=lambda: 1_790_000_000.0)
        admit = Researcher(store, None, None, {"gym": {"roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"]}},
                           background=False)._admit
    except Exception:  # noqa: BLE001 - a tree whose researcher cannot be built here is judged without its admission
        admit = None
    try:
        from league.swarm import preflight
    except ImportError:
        preflight = None
    decider = None
    if preflight is not None and not hasattr(preflight, "screen") and hasattr(preflight, "run"):
        from league.live.decider import InlineDecider

        decider = InlineDecider(timeout=1.0, max_errors=10 ** 9)
    families = itertools.count()

    def screen(code: str, params: dict, roots: list[str]) -> str | None:
        if check_experiment is not None:
            try:
                check_experiment(code, params)
            except Exception:  # noqa: BLE001 - any refusal (or crash) of the static check stops the program
                return "static"
        if admit is not None:
            family = {"id": f"judge-family-{next(families):04d}", "roots": list(roots), "band": "gym"}
            try:
                refused = admit(family, code, {})[0]
            except Exception:  # noqa: BLE001 - an admission that crashes stops the program (the cycle errs)
                return "admit"
            if refused is not None:
                return "admit"
        if preflight is not None:
            try:
                if hasattr(preflight, "screen"):
                    verdict = preflight.screen(code, params, roots=roots)
                elif decider is not None:
                    verdict = preflight.run(code, params, decider, universe=roots)
                else:
                    verdict = {}
            except Exception:  # noqa: BLE001 - a crashing preflight lets the program through, as the researcher does
                verdict = {}
            if dict(verdict or {}).get("status") == "refused":
                return "preflight"
        return None

    return screen


def main() -> None:
    opts = _common.args()
    # The cases are drawn before the tree's code loads; the pool is not kept past this point.
    chosen = cases(opts.split, opts.seed, opts.pool)
    opts.pool = None

    def body() -> dict[str, Any]:
        screen = screens()
        reaching = refused_valid = 0
        stages: dict[str, int] = {}
        missed: dict[str, int] = {}
        began, cpu = time.monotonic(), time.process_time()
        for case in chosen:
            stage = screen(case["code"], {}, ["SPY"])
            if stage:
                stages[stage] = stages.get(stage, 0) + 1
            if case["label"] == "broken" and stage is None:
                reaching += 1
                key = f"{case['class']}/{case['wrap']}"
                missed[key] = missed.get(key, 0) + 1
            elif case["label"] == "valid" and stage is not None:
                refused_valid += 1
        return {"broken_reaching_gym": reaching, "false_refusals": refused_valid,
                "broken_cases": sum(1 for c in chosen if c["label"] == "broken"),
                "gym_seconds_wasted": reaching * GYM_SECONDS_PER_DQ,
                "screen_cpu_seconds": round(time.process_time() - cpu, 4),
                "screen_seconds": round(time.monotonic() - began, 3), "refused_by_stage": stages, "missed": missed,
                "cases": len(chosen)}

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
