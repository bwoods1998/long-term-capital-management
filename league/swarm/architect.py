"""The architect: every `every_seconds` (four hours by default), 3-6 new families from the leaderboard, the graveyard
and the gaps.

The population (plan: 48 at the start, a ceiling of 96, a floor of 16; `population` in swarm.json may set others): while
fewer families live than the start (retirements drained it), it REFILLS: every `refill_seconds` (an hour by default), up
to the gap to the start (at most `max_refill` a pass). At or above the start it grows toward the ceiling at the plan's
pace, and the loop runs that growth only while the swarm's hourly spend is under its pace (money allows). A birth spends
nothing by itself: the hourly pace caps every researcher's cycles together.

Claude first (`claude.model`, or `claude.role_model["architect"]`; "architect" is a default `claude.roles` entry) while
its funded total has room; every other pass asks GPT-6 Astra first only while `architect.openai_model` names it (null
makes the architect Claude-only); else Kimi-K3 balanced on Sail. It reads the leaderboard (families, bands, shares, and
of Validation only whether the line was met and how many of its checks passed: the owner's decision D2a), the
graveyard's lessons, and the GAPS (roots x structure types no living family covers), and answers with new families: a
mechanism (why it should make money), a structure, a universe slice (one to five pooled roots of the admitted list, days
to expiry) and a rejection test. The swarm admits those that are well-formed, distinct from the living families and
inside the population ceiling; each new family's researcher writes its first program (no starter). The operator steers
it without a deploy through `architect.agenda` (swarm.json): a non-empty agenda closes the request as "THE OPERATOR'S
RESEARCH AGENDA".

Each pass is a `swarm.architect` event; each birth a `swarm.born` event (the site's news).
Standard library only.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping

from . import diagnostics
from . import settings as settings_mod
from .researcher import MAX_ROOTS
from .store import STRUCTURES, SwarmStore

#: Two mechanisms are the same idea when their content words overlap this much (Jaccard).
SAME_IDEA = 0.5
_STOP = frozenset("a an and are as at be by for from in into is it its of on or than that the their then this to when with "
                  "options option sell buy".split())


def words(text: str) -> frozenset[str]:
    return frozenset(w for w in "".join(c if c.isalnum() else " " for c in str(text).lower()).split()
                     if len(w) > 2 and w not in _STOP)


def same_idea(a: str, b: str) -> bool:
    x, y = words(a), words(b)
    return bool(x and y) and len(x & y) / len(x | y) >= SAME_IDEA

SYSTEM = """You are the architect of a swarm of AI researchers that trade level-3 options (defined-risk structures only) on one
brokerage account. Each researcher owns one family: a mechanism, a structure type and a universe slice, and improves a
program for it in a Gym of real recorded one-minute option quotes (Train 2022-2024; Validation 2025 by summary only; a
sealed holdout at the gate). Propose NEW families that are likely to clear the validation line (>= 50 trades on >= 25
days a year, mean P&L per dollar of max loss > 0 with t >= 2 after fees and the spread, a deflated Sharpe on traded days
that survives the lineage's validated versions, 3 of 4 quarters positive, positive at 1.5x the half-spread). A family's
Train score is its WORST Train year, so a mechanism must earn in 2022, 2023 and 2024 alike, with at least 40 trades on
20 days in each. Prefer mechanisms with a reason to exist
(a risk premium, a flow, a behavioral bias, a venue rule), horizons supported by the available data, and slices the
swarm does not cover. The strategy still needs enough independent trades to be evaluated. Learn from the graveyard:
do not re-propose what failed unless you say what is different.

Use only the available roots listed in the current request; that configured list is the Gym's data universe. A
family may pool one to five of them: the same mechanism on several roots trades more often and is measured sooner
(days traded on several roots count once a day, so pool roots that trade on different days).
XSP and SPXW are cash-settled index options with no calendars or diagonals. XSP costs $0.50 a contract, which makes a
narrow XSP structure uneconomic: use XSP only for structures wide enough to carry that fee. The other available roots
are physically settled equity or ETF options. Structure types: long_call, long_put, debit_vertical, credit_vertical, iron_condor, iron_butterfly,
long_butterfly, long_straddle, long_strangle, calendar, diagonal. All listed types compete on the same evidence:
complexity earns no preference. Single calls and puts are first-class research choices. Consider the simplest
expression of each mechanism before adding legs; use additional legs when they serve the hypothesis. Use the coverage
counts and gaps to explore neglected types and roots, while retaining the lessons and trial history of failed ideas.
Research support does not imply brokerage execution support; the House checks that separately. Do not invent a data
source, a supported strategy type, or evidence to fill a coverage gap.

Reply with ONE JSON object: {"families": [{"slug": "short-kebab-name", "mechanism": "one or two sentences: why it should
make money", "structure": "<type>", "roots": ["SPY", "QQQ"], "dte": [0, 2], "rejection": "the result that would prove it
wrong", "sketch": "how the program should decide, in plain words", "parent": "retired family id, if revising its idea"}]}.
A renamed or revised version of a retired mechanism must name its parent; it inherits the entire lineage's trials
and three-look holdout ration. Only a different economic mechanism starts a new lineage."""


class Architect:
    def __init__(self, store: SwarmStore, router: Any, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time):
        self.store = store
        self.router = router
        self.settings = settings
        self.clock = clock

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("architect", {})

    def refilling(self) -> bool:
        """Fewer families live than the swarm starts with."""
        return len(self.store.families(alive=True)) < int(self.settings.get("population", {}).get("start", 48))

    def due(self) -> bool:
        every = float(self.cfg.get("refill_seconds", 3600)) if self.refilling() else float(self.cfg.get("every_seconds", 14400))
        return self.clock() - float(self.store.get("architect_at", 0.0) or 0.0) >= every

    def want(self) -> int:
        """How many families this pass may admit: the gap to the start while refilling (at most `max_refill`), else
        `max_new`; never past the ceiling."""
        pop = self.settings.get("population", {})
        alive = len(self.store.families(alive=True))
        start, ceiling = int(pop.get("start", 48)), int(pop.get("ceiling", 96))
        n = min(int(self.cfg.get("max_refill", 12)), start - alive) if alive < start else int(self.cfg.get("max_new", 6))
        return max(0, min(n, ceiling - alive))

    def _gaps_by_root(self) -> dict[str, list[str]]:
        roots = list(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        covered = {(r, f["structure"]) for f in self.store.families(alive=True) for r in f["roots"]}
        out = {}
        for root in roots:
            out[root] = []
            for structure in STRUCTURES:
                if root in ("XSP", "SPXW") and structure in ("calendar", "diagonal"):
                    continue
                if (root, structure) not in covered:
                    out[root].append(structure)
        return out

    def gaps(self) -> list[str]:
        return [f"{structure} on {root}" for root, structures in self._gaps_by_root().items() for structure in structures]

    def coverage(self) -> dict[str, dict[str, int]]:
        """Research effort by supported type, including retired ideas; never a claim about returns or fills.

        Count each family's own evaluations once. Inherited lineage counts remain the gate's evidence adjustment,
        not extra work to add again to this coverage table. Families outside this image's root list are excluded.
        """
        roots = set(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        rows = {kind: {"active_families": 0, "retired_families": 0, "trials": 0, "validated_families": 0}
                for kind in STRUCTURES}
        for family in self.store.families():
            if not roots.intersection(family["roots"]):
                continue
            row = rows[family["structure"]]
            row["retired_families" if family["retired_at"] else "active_families"] += 1
            row["trials"] += int(family.get("trials") or 0)
            row["validated_families"] += int(int(family.get("validations") or 0) > 0)
        return rows

    def prompt(self) -> str:
        alive = self.store.families(alive=True)
        living_ids = {f["id"] for f in alive}
        board = (self.store.get("leaderboard") or {}).get("board") or []
        # Of Validation the architect sees what a researcher sees (D2a): the line met or not and the checks passed.
        lines = {f["id"]: (f.get("state") or {}).get("validation_line") for f in alive}
        living = [{"family": r["family"], "band": r["band"], "structure": r["structure"], "roots": r["roots"],
                   "validation": diagnostics.validation_view({}, lines.get(r["family"])) if lines.get(r["family"]) else None,
                   "share": r.get("share")} for r in board if r["family"] in living_ids][:60]
        if not living:
            living = [{"family": f["id"], "structure": f["structure"], "roots": f["roots"], "mechanism": f["mechanism"][:160]}
                      for f in alive][:60]
        graves = [{"family": g["family"], "structure": g["structure"], "roots": g["roots"], "lesson": diagnostics.scrub(g["lesson"])[:400]}
                  for g in self.store.graveyard(limit=20)]
        want = self.want()
        roots = ", ".join(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        gaps = json.dumps(self._gaps_by_root(), separators=(",", ":"))
        coverage = json.dumps(self.coverage(), separators=(",", ":"))
        # During a burst refill, ask for the whole bounded gap. Asking for "3 to 12" repeatedly underfilled a
        # population losing families faster than three births per hour. The admission and spending caps still bind.
        number = str(want) if self.refilling() and want > 0 else f"{min(max(int(self.cfg.get('min_new', 3)), 1), max(want, 1))} to {max(want, 1)}"
        agenda = str(self.cfg.get("agenda") or "").strip()[:4000]
        return (f"Propose {number} new families, on these roots only (the Gym "
                f"holds their data): {roots}.\n\nLIVING FAMILIES "
                f"(leaderboard):\n{json.dumps(living)}\n\nTHE GRAVEYARD:\n{json.dumps(graves)}\n\n"
                f"RESEARCH COVERAGE (effort, not profitability; validated means evaluated, not passed):\n{coverage}\n\n"
                f"GAPS (uncovered structure types by root; [] means all covered):\n{gaps}"
                + (f"\n\nTHE OPERATOR'S RESEARCH AGENDA:\n{agenda}" if agenda else ""))

    def admit(self, rows: Any) -> list[str]:
        cap = self.want()
        living = {(f["mechanism"].lower()[:80], tuple(f["roots"]), f["structure"]) for f in self.store.families(alive=True)}
        allowed_roots = set(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        born = []
        for row in rows if isinstance(rows, list) else []:
            if len(born) >= cap or not isinstance(row, dict):
                break
            structure = row.get("structure")
            named = [row["roots"]] if isinstance(row.get("roots"), str) else (row.get("roots") or [])
            roots = list(dict.fromkeys(str(r).upper() for r in named if str(r).upper() in allowed_roots))[:MAX_ROOTS]
            dte = row.get("dte") if isinstance(row.get("dte"), list) and len(row.get("dte")) == 2 else [0, 5]
            mechanism = " ".join(str(row.get("mechanism") or "").split())[:600]
            if structure not in STRUCTURES or not roots or len(mechanism) < 30:
                continue
            if any(r in ("XSP", "SPXW") for r in roots) and structure in ("calendar", "diagonal"):
                continue
            if (mechanism.lower()[:80], tuple(roots), structure) in living:
                continue
            try:
                lo, hi = sorted((max(0, min(45, int(dte[0]))), max(0, min(45, int(dte[1])))))
            except (TypeError, ValueError):
                lo, hi = 0, 5
            # Three distinct lessons: many open with the same wording (the idle rule's), and 300 characters is all a
            # family is born with, so a repeat would only crowd out another lesson.
            lessons = list(dict.fromkeys(diagnostics.scrub(g["lesson"])[:300]
                                         for g in self.store.graveyard(f"{structure} {' '.join(roots)} {mechanism}", limit=12)))[:3]
            spec = {"id": row.get("slug") or mechanism, "mechanism": mechanism, "structure": structure, "roots": roots, "dte": [lo, hi],
                    "rejection": str(row.get("rejection") or "")[:400], "sketch": str(row.get("sketch") or "")[:800],
                    "lessons": lessons}
            # A slice a retired family searched (same structure and roots): the same idea again continues its lineage
            # (its trials and holdout looks, so re-proposing never resets the count its evidence is deflated by); another
            # idea is a new lineage that still counts the slice's trials (`prior_lineage`) but not its look ration.
            dead = [f for f in self.store.families(alive=False) if f["structure"] == structure and sorted(f["roots"]) == sorted(roots)]
            same = [f for f in dead if f["id"] in (row.get("parent"), row.get("slug")) or same_idea(f["mechanism"], mechanism)]
            declared = self.store.family(str(row.get("parent"))) if row.get("parent") else None
            parent = declared["id"] if declared and declared["structure"] == structure else (same[-1]["id"] if same else None)
            prior = dead[-1]["lineage"] if dead and not parent else None
            with self.store.lock:
                if len(self.store.families(alive=True)) >= int(self.settings.get("population", {}).get("ceiling", 96)):
                    break
                fam = self.store.add_family(spec, origin="architect", parent=parent, prior_lineage=prior)
                living.add((mechanism.lower()[:80], tuple(roots), structure))
            if spec["sketch"]:
                self.store.note(fam["id"], f"The architect's sketch: {spec['sketch']}")
            self.store.event("swarm.born", fam["id"], {"parent": parent, "mechanism": mechanism, "structure": structure,
                                                        "roots": roots, "origin": "architect"})
            born.append(fam["id"])
        return born

    def run(self) -> dict[str, Any]:
        began = self.clock()
        self.store.put("architect_at", began)
        room = int(self.settings.get("population", {}).get("ceiling", 96)) - len(self.store.families(alive=True))
        if room <= 0:
            out = {"born": [], "why": "the population is at its ceiling"}
            self.store.event("swarm.architect", None, out)
            return out
        try:
            # SYSTEM itself while Train is 2022-2024; else the running swarm's span (its store's migrated objective)
            system = settings_mod.train_span_text(SYSTEM, settings_mod.objective_span(self.store.get("train_objective")))
            answer = self.router.ask(role="architect", system=system, user=self.prompt(), family=None,
                                     key=f"swarm:architect:{int(began)}", openai_model=self.cfg.get("openai_model"),
                                     sail_profile=str(self.cfg.get("sail_profile", "k3_balanced")),
                                     max_output=int(self.cfg.get("max_output_tokens", 12000)), effort="high", need_usd=2.0,
                                     claude=True, rotate=True)  # Claude first; Astra every other pass if openai_model
        except Exception as exc:  # noqa: BLE001
            out = {"born": [], "error": str(exc)[:300]}
            self.store.event("swarm.architect", None, out)
            return out
        rows = (answer.get("json") or {}).get("families")
        born = self.admit(rows)
        out = {"born": born, "proposed": len(rows) if isinstance(rows, list) else 0, "route": answer.get("route"),
               "model": answer.get("model"), "cost_usd": answer.get("cost_usd"), "seconds": round(self.clock() - began, 1)}
        self.store.event("swarm.architect", None, out)
        return out


__all__ = ["Architect", "SYSTEM"]
