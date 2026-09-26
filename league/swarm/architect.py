"""The architect: every four hours, 3-6 new families from the leaderboard, the graveyard and the gaps.

The population (plan: 48 at the start, a ceiling of 96, a floor of 16): while fewer families live than the
start (retirements drained it), it REFILLS: every `refill_seconds` (an hour), up to the gap to the start
(at most `max_refill` a pass). At or above the start it grows toward the ceiling at the plan's pace, and
the loop runs that growth only while the swarm's hourly spend is under its pace (money allows). A birth
spends nothing by itself: the hourly pace caps every researcher's cycles together.

GPT-6 Astra through the gateway when the OpenAI month has room (and the swarm's OpenAI cap allows), else
Kimi-K3 balanced on Sail. It reads the leaderboard (families, bands, validation summaries, shares), the
graveyard's lessons, and the GAPS (roots x structure types no living family covers), and answers with new
families: a mechanism (why it should make money), a structure, a universe slice (roots, days to expiry)
and a rejection test. The swarm admits those that are well-formed, distinct from the living families and
inside the population ceiling; each new family's researcher writes its first program (no starter).

Each pass is a `swarm.architect` event; each birth a `swarm.born` event (the site's news).
Standard library only.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Mapping

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
sealed holdout at the gate). Propose NEW families that are likely to clear the validation line (>= 100 trades on >= 60
days a year, mean P&L per dollar of max loss > 0 with t >= 2 after fees and the spread, a deflated Sharpe that survives the
lineage's trials, 3 of 4 quarters positive, positive at 1.5x the half-spread). Prefer mechanisms with a reason to exist
(a risk premium, a flow, a behavioral bias, a venue rule), short horizons (0-5 days to expiry), and slices the swarm does
not cover. Learn from the graveyard: do not re-propose what failed unless you say what is different.

Roots: SPY, QQQ, IWM (ETF options, physically settled, daily expiries), XSP and SPXW (index, cash-settled, no calendars or
diagonals). Structure types: long_call, long_put, debit_vertical, credit_vertical, iron_condor, iron_butterfly,
long_butterfly, long_straddle, long_strangle, calendar, diagonal. Only the first five multi-leg types (verticals, iron
condors, iron butterflies, long butterflies) can reach real money soon.

Reply with ONE JSON object: {"families": [{"slug": "short-kebab-name", "mechanism": "one or two sentences: why it should
make money", "structure": "<type>", "roots": ["SPY"], "dte": [0, 2], "rejection": "the result that would prove it
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

    def gaps(self) -> list[str]:
        roots = list(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        covered = {(r, f["structure"]) for f in self.store.families(alive=True) for r in f["roots"]}
        out = []
        for root in roots:
            for structure in STRUCTURES:
                if root in ("XSP", "SPXW") and structure in ("calendar", "diagonal"):
                    continue
                if (root, structure) not in covered:
                    out.append(f"{structure} on {root}")
        return out

    def prompt(self) -> str:
        board = (self.store.get("leaderboard") or {}).get("board") or []
        living = [{"family": r["family"], "band": r["band"], "structure": r["structure"], "roots": r["roots"],
                   "validation": r.get("validation"), "share": r.get("share")} for r in board[:60]]
        if not living:
            living = [{"family": f["id"], "structure": f["structure"], "roots": f["roots"], "mechanism": f["mechanism"][:160]}
                      for f in self.store.families(alive=True)][:60]
        graves = [{"family": g["family"], "structure": g["structure"], "roots": g["roots"], "lesson": g["lesson"][:400]}
                  for g in self.store.graveyard(limit=20)]
        want = self.want()
        roots = ", ".join(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        return (f"Propose {min(max(int(self.cfg.get('min_new', 3)), 1), max(want, 1))} to {max(want, 1)} new families, on these roots only (the Gym "
                f"holds their data): {roots}.\n\nLIVING FAMILIES "
                f"(leaderboard):\n{json.dumps(living)}\n\nTHE GRAVEYARD:\n{json.dumps(graves)}\n\nGAPS (no living family):\n"
                f"{', '.join(self.gaps()[:60])}")

    def admit(self, rows: Any) -> list[str]:
        cap = self.want()
        living = {(f["mechanism"].lower()[:80], tuple(f["roots"]), f["structure"]) for f in self.store.families(alive=True)}
        allowed_roots = set(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        born = []
        for row in rows if isinstance(rows, list) else []:
            if len(born) >= cap or not isinstance(row, dict):
                break
            structure = row.get("structure")
            roots = [str(r).upper() for r in (row.get("roots") or []) if str(r).upper() in allowed_roots][:2]
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
            lessons = [g["lesson"][:300] for g in self.store.graveyard(f"{structure} {' '.join(roots)} {mechanism}", limit=3)]
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
            answer = self.router.ask(role="architect", system=SYSTEM, user=self.prompt(), family=None,
                                     key=f"swarm:architect:{int(began)}", openai_model=self.cfg.get("openai_model"),
                                     sail_profile=str(self.cfg.get("sail_profile", "k3_balanced")),
                                     max_output=int(self.cfg.get("max_output_tokens", 12000)), effort="high", need_usd=2.0)
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
