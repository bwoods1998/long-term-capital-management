"""research-workflow-v2: how many programs that cannot run still reach a Gym replay, and how many sound ones are stopped.

The tree under test screens each synthetic program the way its researcher does before a Train run is spent: the static
experiment check (`league.gym.experiment.check_experiment`), the researcher's own admission (`Researcher._admit`, where
a research-lane candidate gates its change per family) and the runtime preflight when the tree has one
(`league.swarm.preflight.screen(code, params, roots=...)` if defined, else `preflight.run` on an in-process decider).
A BROKEN program errs on the calls the Gym would make (25 errors disqualify a run) or is refused by the Gym's worker; a
VALID one never errs. Labels are fixed by construction, never by the tree under test.

dev: the failure shapes of the Sept 30, 2026 House disqualifications (list used as a mapping, the underlying read as a
dict, arithmetic and comparison on None, a root not in NEEDS, NEEDS out of bounds, a JSON literal, a misspelled name)
plus sound controls. heldout: SEEDED VARIANTS OF CLASSES THE DEV SPLIT NEVER USES (misspelled attributes, calling a
value, an index past the history, an unset STATE key, iterating an int, ...), every held-out class placed
unconditionally, after 10:00 and only in the last hour (the Gym still disqualifies a program that errs every afternoon),
inside a random sound body with random names, and sound programs from a wider pool of templates. The classes are in
this public file: the split is held out from the dev split and from the brief, not from a determined reader; the
concurrent canary is the held-out test no one can read in advance.

Answer: broken_reaching_gym, broken_cases, false_refusals, gym_seconds_wasted (broken_reaching_gym x GYM_SECONDS_PER_DQ,
the mean Gym seconds a disqualified Train run's cycle took on the House, Sept 29-30, 2026), screen_seconds (the screens'
wall time, the lane's cost), cases, and the refusals by stage and by misuse class.
"""
from __future__ import annotations

import itertools
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import _common

PROTOCOL = "research-workflow-v2"
GYM_SECONDS_PER_DQ = 130.0
HEAD = ('import math\nimport numpy as np\n\n'
        'NEEDS = {{"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": {cadence}, "history": {history}}}\n'
        'PARAMS = {{"k": {k}, "on": True, "label": "a"}}\nSTATE = {{}}\n{extra}\n')

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
#: Sound programs only the held-out split draws (over-refusal of shapes the dev split never shows is measurable).
VALID_HELD = {
    "minute_gate": ['if ctx.minute < 600 or ctx.minute > 900:', '    return []', '{a} = ctx.params.get("k", 1.0)',
                    'STATE["{b}"] = {a}'],
    "close_mean": ['u = ctx.under', 'if u is None or len(u.closes) < 3:', '    return []',
                   '{a} = float(np.mean(u.closes[-3:]))', 'STATE["{b}"] = {a} - u.price'],
    "state_counter": ['{a} = STATE.get("{b}", 0) + 1', 'STATE["{b}"] = {a}', 'if {a} % 7 == 0 and ctx.under is not None:',
                      '    STATE["last"] = ctx.under.price'],
    "position_count": ['{a} = len(ctx.positions) + len(ctx.orders)', 'if {a} > 3:', '    return []',
                       'STATE["{b}"] = {a}'],
}
#: Misuses at decide time: each errs on every call it runs.
MISUSE = {
    "positions_items": ['for {a}, {b} in ctx.positions.items():', '    pass'],
    "positions_values": ['for {a} in ctx.positions.values():', '    pass'],
    "orders_keys": ['for {a} in ctx.orders.keys():', '    pass'],
    "under_subscript": ['{a} = ctx.under["price"]'],
    "under_get": ['{a} = ctx.under.get("price")'],
    "none_div": ['{a} = ctx.params.get("missing") / 2.0'],
    "none_compare": ['if ctx.params.get("missing") > 1.0:', '    pass'],
    "unknown_root": ['{a} = ctx.underlyings["QQQ"]'],
    "list_index_dict": ['{a} = ctx.orders[{{"id": 1}}]'],
    "ctx_needs": ['{a} = ctx.needs'],
    "undefined_name": ['{a} = PARES["k"]'],
    "state_unset": ['{a} = STATE["seen_{b}"]', 'STATE["seen_{b}"] = 1.0'],
    "empty_index": ['{a} = ctx.orders[0]'],
    "attr_typo": ['{a} = ctx.under.prce'],
    "chain_typo": ['{a} = ctx.chain.strikes'],
    "call_value": ['{a} = ctx.under.price()'],
    "history_index": ['{a} = ctx.under.closes[99]'],
    "int_iter": ['for {a} in ctx.weekday:', '    pass'],
    "str_arith": ['{a} = ctx.params["label"] * 1.5'],
}
#: Misuses before decide runs: the load fails or the Gym's worker refuses the program.
LOAD = {
    "json_true": {"extra": "{a} = true\n"},
    "needs_cadence": {"cadence": 45},
    "needs_history": {"history": 90},
    "import_os": {"extra": "import os\n"},
    "json_null": {"extra": "{a} = null\n"},
}
DEV_BROKEN = [("positions_items", "always"), ("positions_values", "always"), ("under_subscript", "always"),
              ("under_get", "always"), ("none_div", "always"), ("none_compare", "always"), ("unknown_root", "always"),
              ("list_index_dict", "always"), ("ctx_needs", "always"), ("undefined_name", "always"),
              ("json_true", "load"), ("needs_cadence", "load"), ("needs_history", "load")]
WRAPS = {"always": None, "after_ten": "if ctx.minute >= 600:", "last_hour": "if ctx.minute >= 900:"}
#: The held-out classes: every misuse and load failure the dev split does not use.
HELD_MISUSE = sorted(set(MISUSE) - {m for m, _ in DEV_BROKEN})
HELD_LOAD = sorted(set(LOAD) - {m for m, _ in DEV_BROKEN})


def program(valid: str, *, misuse: str | None = None, wrap: str = "always", names=("px", "row"), k: float = 1.0) -> str:
    template = VALID.get(valid) or VALID_HELD[valid]
    a, b = names
    head: dict[str, Any] = {"cadence": 5, "history": 10, "k": k, "extra": ""}
    body: list[str] = []
    if misuse in LOAD:
        for key, value in LOAD[misuse].items():
            head[key] = value.format(a=a) if isinstance(value, str) else value
    elif misuse:
        lines = [line.format(a=a + "m", b=b + "m") for line in MISUSE[misuse]]
        if WRAPS[wrap]:
            body.append(WRAPS[wrap])
            body.extend("    " + line for line in lines)
        else:
            body.extend(lines)
    body.extend(line.format(a=a, b=b) for line in template)
    body.append("return []")
    return HEAD.format(**head) + "\ndef decide(ctx):\n" + "".join("    " + line + "\n" for line in body)


def cases(split: str, seed: str) -> list[dict[str, Any]]:
    out = []
    if split == "dev":
        bodies = sorted(VALID)
        for n, (misuse, wrap) in enumerate(DEV_BROKEN):
            out.append({"label": "broken", "class": misuse, "wrap": wrap,
                        "code": program(bodies[n % len(bodies)], misuse=misuse, wrap="always")})
        for n, valid in enumerate(bodies + ["close_return", "event_gate"]):
            out.append({"label": "valid", "class": valid, "wrap": "-", "code": program(valid, k=0.5 + n / 4)})
        return out
    r = _common.rng(seed, PROTOCOL)

    def name() -> str:
        return r.choice("abcdefghjkmnpqrstuvwxyz") + "".join(r.choice("abcdefghjkmnpqrstuvwxyz0123456789") for _ in range(5))

    bodies = sorted(VALID) + sorted(VALID_HELD)
    # Every held-out class in every placement, each in a random sound body with random names (stratified: the
    # baseline's count on this split does not depend on the seed's luck).
    for misuse in HELD_MISUSE:
        for wrap in ("always", "after_ten", "last_hour"):
            out.append({"label": "broken", "class": misuse, "wrap": wrap,
                        "code": program(r.choice(bodies), misuse=misuse, wrap=wrap, names=(name(), name()),
                                        k=round(r.uniform(0.1, 3.0), 3))})
    for misuse in HELD_LOAD:
        for _ in range(2):
            out.append({"label": "broken", "class": misuse, "wrap": "load",
                        "code": program(r.choice(bodies), misuse=misuse, names=(name(), name()),
                                        k=round(r.uniform(0.1, 3.0), 3))})
    for valid in sorted(VALID_HELD) * 2 + [r.choice(sorted(VALID)) for _ in range(6)]:
        out.append({"label": "valid", "class": valid, "wrap": "-",
                    "code": program(valid, names=(name(), name()), k=round(r.uniform(0.1, 3.0), 3))})
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

    def body() -> dict[str, Any]:
        screen = screens()
        reaching = refused_valid = 0
        stages: dict[str, int] = {}
        missed: dict[str, int] = {}
        began = time.monotonic()
        chosen = cases(opts.split, opts.seed)
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
                "gym_seconds_wasted": reaching * GYM_SECONDS_PER_DQ, "screen_seconds": round(time.monotonic() - began, 3),
                "refused_by_stage": stages, "missed": missed, "cases": len(chosen)}

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
