"""memory-rebirth-v4: how many restated graveyard mechanisms the architect lets be born again, how many new ones it
stops, and whether what it admits keeps its lineage's trials and its own words, under the admission production runs
since release B' (family cards, league/swarm/cards.py).

A synthetic store holds a graveyard of buried families (mechanisms on slices). The tree under test's architect admits a
batch of proposals (`league.swarm.architect.Architect.admit(rows, digest=True)`, the Claude route's admission, its card
settings at their defaults as production runs them: `architect.require_card` on, `architect.card_rebirth` "refuse"):
each proposal is a REBIRTH (the buried claim restated on the buried slice) or NOVEL (a mechanism nobody buried, on a
buried slice, or a buried mechanism on another slice: new conditions). Labels are fixed by construction. Each proposal
carries a marker in its sketch, so a birth is matched to its proposal whatever the admission does to the text.

WRITING (one form for every proposal). Every proposal's text is written by `restate` from its claim (its `idea`):
synonym swaps, maybe a reordered clause, a new second sentence, maybe a hedge, with one draw rule whatever its label. A
restatement is its buried claim written so, a new idea its own claim written the same way. So no form (two sentences, a
parameter-level second sentence, a hedge, a reordered clause, a swapped word) tells a restatement from a new idea: only
what the first claim says, against the graveyard's, does (found while fixing the citations: until then only
restatements were written so, and a lever refusing every proposal of two sentences, reading no graveyard at all, cut
the rebirths to 0 on dev and the test pool with `novel_refused` 0).

CITATIONS (one shape for every proposal). Every proposal names one buried row in `differs_from`, as the digest route
asks of every proposal: a restatement its buried row, a moved idea the row it moved from, a same-cell control its row,
any other new idea the row on its slice (else an idea row by its place); each citation's "how" is the proposal's own
mechanism text. So neither a citation's presence, nor its row on the proposal's slice, nor its form tells a restatement
from a new idea (the review of the controls: until then only restatements cited, and a lever refusing every citation,
reading no words, cut the rebirths on both splits with `novel_refused` 0). A citation never changes admission
(`Architect.differs` writes notes only, and `architect.require_differs` stays at its default, off).

FAMILY CARDS (v4: release B' refuses a proposal without a complete card). Every buried family and every proposal carries
a complete card, which the judge derives at evaluation time from the case's own fields (never from the pool, which is
gone by then) and checks with `cards.validate` before the tree's architect loads (an invalid card is a judge defect: no
answer). The hypothesis is the case's mechanism text; the class and the inputs are production's own reading of that
text (`cards.infer_key`, `cards.infer_inputs`: a text with no class word gets a class by its hash, one with no input
word reads the underlying price); the holding is the bucket of the case's days to expiry (`infer_key`'s rule); the
cost, comparison, ablation (the contract's default switch) and falsification are fixed sentences. A restatement keeps
its buried row's terms (class, inputs, holding: the same idea on the same terms) with its own words as its hypothesis,
and so does a moved idea (a buried mechanism on another slice). The card module is the pinned base's (no lane's surface
holds it) and is read before any of the tree's code loads (the held-out draw uses its keyword reading too).

SAME-CELL CONTROLS (the card fields never tell a rebirth from a new idea). A restatement carries its buried row's exact
card key on that row's slice, so without controls "the card equals a dead family's on its slice" would separate the
rebirths perfectly: a lever refusing such cards would cut every rebirth here while, in production, refusing every new
idea whose card reads like an idle death beside it (the vocabulary is coarse; those deaths are no finding about the
mechanism). So every idea row's slice also holds a NOVEL proposal under that row's exact class, inputs and holding,
with a new idea's text as its mechanism and hypothesis (dev: one of the public novel texts, never the one already on
that slice, or a public text whose words read exactly as the row's, `SAME_READING`; held-out: a novel text from the
pool, never one already on that slice). The card rules admit it (an idea row is no refuted cell, and its holding is
short), so a card-keyed refusal, exact or on overlapping inputs, refuses these controls too and `novel_refused` rises;
with the citations' one shape (CITATIONS), only the words tell a restatement from a control, and the words are what
the lane's lever reads (`same_cell_proposed`, `same_cell_refused` report them). The controls' words are their own
idea's: a refusal that also asks the words to read (production's keyword reading) as the dead row's class or inputs
refuses on the words' coarse reading, and is caught where a new idea's words read like a dead row's. On dev, rows 2 and
3's controls read exactly as their rows (class and inputs), one of them a text from outside every lane's surface (so
an exemption keyed to the surface's own texts, the founding families', does not shield such a refusal), and row 1's
as its class; on held-out, each control takes the pool's novel text that reads closest to its row's first (the seed
breaking ties), so how often the held-out split sees such a refusal depends on the pool's texts.

TWO KINDS OF DEATH. The card check (`cards.RebirthIndex`) covers only rows killed by a mechanism verdict
(`cards.MECHANISM_VERDICTS`); the rest of the graveyard, most of the House's, is left to idea admission, the memory lane's
lever. The graveyard holds both, and the judge refuses to answer when the tree's tags read it otherwise (the card check
must index the card-path rows and nothing else):
- IDEA rows (the dev split's eight; the pool's `buried`): retired by the idle rule's THIN or EXHAUSTED verdict or by the
  tournament's STALL, in turn, all short-dated (0 to 5 days to expiry: days_1_3). Their restatements and every novel
  proposal reach idea admission; `rebirths_admitted` measures the lever on them.
- CARD-PATH rows (the dev split's two; from the pool's bank, at most two and only those it can spare without repeating
  a novel text: a pool with no spare text has none, and then only the dev split exercises the card path): REFUTED and
  long-dated (21 to 45 days: days_11_plus, a holding no other case has). Each is restated once, on its slice, with its
  terms and no `rebirth` case, so production's card check must refuse it: `card_path_admitted` must be 0, and a
  restatement it lets through counts in `rebirths_admitted` too.
No novel card falls in a refuted cell (a refuted cell is a card-path row's class, structure family and holding). A new
idea inside a refuted cell owes a rebirth case under the card rules; the judge builds none, so `novel_refused` counts
refusals of new ideas outside every refuted cell: 0 by construction for a sound admission. The construction is checked
with the card module's own matching before the tree's architect loads (`carded`: each card-path restatement falls in its
own row's refuted cell and no other proposal falls in any; every control carries its row's exact key on its row's
slice), or no answer.

dev (this file): eight idea rows, two card-path rows, their light restatements and sixteen novel proposals (six on
idea rows' slices under their own reading, two buried mechanisms moved to another root, eight same-cell controls), each
written with every table entry and no draw (every synonym that occurs, the first second sentence, no hedge).
heldout: a PRIVATE bank of buried mechanisms, novel ideas, synonyms, second sentences, hedges and slices from the lane's
pool, which lives outside this public repo and reaches the judge only on standard input (`_common.args`,
`--pool-stdin`), every proposal written with synonym swaps, reordered clauses and hedges from a seed that exists only
once the candidate is committed. The pool needs no card field: every card is derived from the drawn cases.

Answer: rebirths_admitted, novel_refused, trials_uncounted (a birth on a slice with a buried family that neither
continues a lineage nor counts the slice's trials: the multiple-testing control loosened; must be 0),
mechanism_rewritten (a birth whose mechanism is not its proposal's text: the rebirth detector would be fooled; must be
0), rebirths_fresh_lineage (admitted rebirths that start a lineage other than their buried row's: a fresh look ration),
card_path_admitted (card-path restatements born: the card check bypassed; must be 0), same_cell_proposed and
same_cell_refused (the controls, refused ones counted in novel_refused too), sqlite_statements (the store work, the
lane's cost).
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any

import _common

PROTOCOL = "memory-rebirth-v4"
BANK = [
    "Small caps lag large caps after a strong opening drive, and IWM catches up to SPY over the session.",
    "Implied volatility is bid before scheduled macro releases and decays after the print, so short-dated premium is rich into the event.",
    "Month-end rebalancing flows push index funds toward the close on the last trading day, and the move partly reverses the next morning.",
    "Put skew overshoots after a sharp selloff because hedgers overpay for protection, and it mean-reverts over the following week.",
    "Gold and long bonds compete for the same haven flow, so a wide gap between their recent returns tends to close.",
    "Retail call buying in high-attention names inflates call implied volatility relative to puts, which fades once attention cools.",
    "Overnight gaps in QQQ that are not confirmed by futures volume tend to fill during the first hour of trading.",
    "Dealer gamma positioning pins the index near large open-interest strikes on expiration afternoons.",
]
SLICES = [("debit_vertical", ["SPY"]), ("credit_vertical", ["QQQ"]), ("long_straddle", ["IWM"]), ("debit_vertical", ["QQQ"]),
          ("long_strangle", ["SPY"]), ("credit_vertical", ["SPY"]), ("debit_vertical", ["IWM"]), ("iron_condor", ["SPY"])]
#: The dev split's card-path rows: mechanisms a mechanism verdict buried, on slices of their own. New public text (first
#: pushed in aa2fbe9c, Oct 1, 2026, after the memory pool was last rotated in e67bfa18): under the playbook's burn rule
#: the families they name are burned, and the owner scans the private memory pool against them again before the lane's
#: next evaluation (the operator step in PR #466). Every other mechanism text in this file was public before that
#: rotation (the cards' fixed sentences name no mechanism).
CARD_BANK = ["Back-month implied volatility stays too steep after a volatility spike, so the term premium bleeds out of "
             "longer expiries over the following month.",
             "Income funds overwrite index calls every month, so one-month call implied volatility stays underpriced "
             "relative to the move that follows in rising markets."]
CARD_SLICES = [("long_butterfly", ["SPY"]), ("calendar", ["QQQ"])]
#: Card-path rows the held-out split draws from the pool's bank, at most (fewer when the bank cannot spare them).
CARD_PATH = 2
#: The dev split's same-cell control on idea row n's slice takes NOVEL[(n + CONTROL_SHIFT) % len(NOVEL)], never the text
#: of the novel proposal already there (NOVEL[n % len(NOVEL)]), or its row's entry in SAME_READING.
CONTROL_SHIFT = 3
#: Dev controls whose words read exactly as their row's (production's keyword reading: the same class and inputs) while
#: saying another idea, each copied verbatim from a public file (never read from the tree under test) that was public
#: before the private pools were drawn: row 2's a graveyard-digest test fixture
#: (league/tests/test_swarm_graveyard_digest.py, outside every lane's surface: no candidate edits it, and an exemption
#: keyed to the founding families' texts does not cover it), row 3's a founding family's mechanism
#: (league/swarm/seeds.py).
#: No public novel text above reads exactly as a dev row.
SAME_READING = {
    2: "Owning a QQQ straddle before the open pays when overnight gaps extend.",
    3: "Short-dated index options price a bigger move than follows on average (the variance risk premium); an iron condor "
       "sells it with the loss capped at the wing.",
}
SYNONYMS = {"lag": "trail", "catches up": "closes the distance", "tends to": "usually", "bid": "elevated", "decays": "fades",
            "rich": "overpriced", "partly": "partially", "reverses": "unwinds", "overshoots": "overreacts",
            "mean-reverts": "normalizes", "compete for": "share", "wide gap": "large spread", "inflates": "raises",
            "fades": "declines", "continues": "persists", "predicts": "leads", "respond to": "react to",
            "too cheaply": "below fair value", "collapses": "deflates", "pins": "anchors", "strong": "forceful",
            "sharp": "steep", "several": "a few", "resolves": "clears", "lifts": "pushes up"}
SECONDS = ["This version holds for three sessions instead of one.", "The entry now waits for a confirming close.",
           "Width and delta are tuned more tightly this time.", "It trades only when the signal is in its top decile.",
           "The exit moves to the second session."]
NOVEL = ["Index dispersion rises when single-name implied correlation falls, so wings on the index are cheap.",
         "Pre-holiday sessions carry lower realized volatility than the options market prices.",
         "A fund's premium to its intraday net asset value closes by the next open.",
         "Vol-of-vol spikes after flat weeks mark mispriced wings that normalize within days.",
         "Close auctions with large imbalances extend in the imbalance direction at the next open."]
HEDGE = " The idea is kept but the timing differs."
SHORT, LONG = [0, 5], [21, 45]
#: How the graveyard's rows died: (retirement reason, lesson), as the House writes them (league/swarm/researcher.py's
#: idle-rule verdicts, the tournament's stall). IDEA deaths are none of `cards.MECHANISM_VERDICTS`; the card path's is.
IDEA_DEATHS = (
    ("Retired by the idle rule after its Train record was screened. Idle verdict THIN, a tested finding: it traded on "
     "Train, but no version made 40 trades on 20 days in every Train year",
     "Thin: it traded on Train, but no version made 40 trades on 20 days in every Train year."),
    ("Retired by the idle rule after its Train record was screened. Idle verdict EXHAUSTED, a tested finding: it reached "
     "a Train score, then its research ran dry (no new evaluation, or a best that stayed below zero)",
     "Exhausted: it reached a Train score, then its research ran dry."),
    ("no validation improvement in 12 revisions", "Stalled: no improvement over twelve revisions."),
)
CARD_DEATH = ("the mechanism was refuted on Train", "Refuted: the signal did not beat its placebo after costs.")
#: A card's fixed fields (the judge's cases carry no quotes, so the hurdle is an estimate like the architect's).
CARD_FIXED = {"cost": {"hurdle": 0.1, "why": "a fixed estimate of the round trip's spread and fees for the judge's cases"},
              "comparison": "The same structure entered on the same schedule without the signal's condition.",
              "falsification": "Its entries do not beat the comparison's entries after the spread and fees on Train."}
HYPOTHESIS_PAD = " (the judge's case, restated as its card's hypothesis)"


def restate(text: str, r: Any | None, pool: dict | None = None) -> str:
    """A claim written as the judge writes every proposal (WRITING in the module docstring): synonym swaps, maybe a
    reordered clause, a new second sentence, maybe a hedge (the dev split's tables, or the private pool's on the
    held-out split). A restatement is its buried claim written so; a new idea is its own claim written the same way."""
    pool = pool or {}
    synonyms = pool.get("synonyms") or SYNONYMS
    seconds = pool.get("seconds") or SECONDS
    hedges = pool.get("hedges") or [HEDGE]
    out = text
    for word, other in synonyms.items():
        if word in out and (r is None or r.random() < 0.7):
            out = out.replace(word, other, 1)
    if r is not None and ", " in out and r.random() < 0.5:
        head, tail = out.rstrip(".").split(", ", 1)
        out = f"{tail[0].upper()}{tail[1:]}, as {head[0].lower()}{head[1:]}."
    second = seconds[0] if r is None else r.choice(seconds)
    hedge = "" if r is None or r.random() < 0.5 else " " + r.choice(hedges).strip()
    return f"{out} {second}{hedge}"


def cases(split: str, seed: str, pool: dict | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(buried, proposals). A buried row's `path` is "idea" or "card" (the module docstring) and its `dte` its days to
    expiry; a proposal's `idea` is the claim its text is written from (`restate`, WRITING: a restatement's is its
    buried row's), a restatement or a moved idea names its buried row by index (`source`), a same-cell control the idea
    row whose card key and slice it takes (`cell`), and every proposal the buried row its citation names (`cites`,
    `cited`)."""
    if split == "dev":
        idea = [{"mechanism": text, "structure": s, "roots": roots, "path": "idea", "dte": SHORT}
                for text, (s, roots) in zip(BANK, SLICES[:8])]
        card = [{"mechanism": text, "structure": s, "roots": roots, "path": "card", "dte": LONG}
                for text, (s, roots) in zip(CARD_BANK, CARD_SLICES)]
        buried = idea + card
        proposals = [{"label": "rebirth", "idea": b["mechanism"], "structure": b["structure"], "roots": b["roots"],
                      "dte": b["dte"], "path": b["path"], "source": n} for n, b in enumerate(buried)]
        proposals += [{"label": "novel", "idea": NOVEL[n % len(NOVEL)], "structure": SLICES[n][0],
                       "roots": SLICES[n][1], "dte": SHORT} for n in range(6)]
        proposals += [{"label": "novel", "idea": idea[n]["mechanism"], "structure": SLICES[(n + 3) % 8][0],
                       "roots": ["DIA"], "dte": SHORT, "source": n} for n in range(2)]
        proposals += [{"label": "novel", "idea": SAME_READING.get(n, NOVEL[(n + CONTROL_SHIFT) % len(NOVEL)]),
                       "structure": b["structure"], "roots": b["roots"], "dte": SHORT, "cell": n}
                      for n, b in enumerate(idea)]
        return buried, cited(buried, written(proposals, None))
    if not pool:
        raise ValueError("the held-out split is drawn from the lane's private pool")
    r = _common.rng(seed, PROTOCOL)
    order = list(pool["bank"])
    r.shuffle(order)
    slices = [(str(s), list(roots)) for s, roots in pool["slices"]]
    r.shuffle(slices)
    n_buried = int(pool.get("buried", 8))
    novel_count = int(pool.get("novel_count", 8))
    idea = [{"mechanism": text, "structure": s, "roots": roots, "path": "idea", "dte": SHORT}
            for text, (s, roots) in zip(order[:n_buried], slices)]
    # The card path takes bank texts only while every novel proposal still gets a text of its own.
    spare = len(order[n_buried:]) + len(pool["novel"]) - novel_count
    k = max(0, min(CARD_PATH, len(order[n_buried:]), spare))
    card = [{"mechanism": text, "structure": slices[(len(idea) + n) % len(slices)][0],
             "roots": slices[(len(idea) + n) % len(slices)][1], "path": "card", "dte": LONG}
            for n, text in enumerate(order[n_buried:n_buried + k])]
    buried = idea + card
    proposals = [{"label": "rebirth", "idea": b["mechanism"], "structure": b["structure"], "roots": b["roots"],
                  "dte": b["dte"], "path": b["path"], "source": n} for n, b in enumerate(buried)]
    fresh = order[n_buried + k:] + list(pool["novel"])
    r.shuffle(fresh)
    elsewhere = list(pool.get("elsewhere_roots") or ["DIA", "TLT", "GLD"])
    novel = [{"label": "novel", "idea": fresh[n % len(fresh)], "structure": slices[n % len(slices)][0],
              "roots": slices[n % len(slices)][1], "dte": SHORT} for n in range(novel_count)]
    proposals += novel
    proposals += [{"label": "novel", "idea": idea[n]["mechanism"], "structure": idea[n]["structure"],
                   "roots": [r.choice(elsewhere)], "dte": SHORT, "source": n}
                  for n in range(int(pool.get("moved_count", 4)))]
    # The same-cell controls: one per idea row, on its slice, a novel text not yet there, the one whose own words read
    # closest to the row's (production's keyword reading: class and inputs, then class) first, the seed breaking ties.
    from league.swarm import cards  # the pinned base's (no lane's surface holds it): nothing of the tree's loads here

    there: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for p in novel:
        there.setdefault((p["structure"], tuple(sorted(p["roots"]))), set()).add(p["idea"])
    for n, b in enumerate(idea):
        taken = there.setdefault((b["structure"], tuple(sorted(b["roots"]))), set())
        options = [text for text in dict.fromkeys(fresh) if text not in taken]
        if options:
            near = {text: reads_as(cards, text, b) for text in options}
            text = r.choice([text for text in options if near[text] == max(near.values())])
            taken.add(text)
            proposals.append({"label": "novel", "idea": text, "structure": b["structure"], "roots": b["roots"],
                              "dte": SHORT, "cell": n})
    proposals = cited(buried, written(proposals, r, pool))
    r.shuffle(proposals)
    return buried, proposals


def written(proposals: list[dict[str, Any]], r: Any | None, pool: dict | None = None) -> list[dict[str, Any]]:
    """Each proposal with its `mechanism`, its `idea` written by `restate` (WRITING in the module docstring), in batch
    order with one draw rule for every proposal: nothing about its label decides how its text is written."""
    return [{**p, "mechanism": restate(p["idea"], r, pool)} for p in proposals]


def cited(buried: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each proposal with `cites`, the buried row its `differs_from` names (CITATIONS in the module docstring): its
    own (a restatement's or a moved idea's `source`, a control's `cell`), else the first buried row on its slice, else
    an idea row by its place in the batch. Nothing about its label decides whether or how it cites."""
    idea = [n for n, b in enumerate(buried) if b["path"] == "idea"]
    on: dict[tuple[str, tuple[str, ...]], int] = {}
    for n, b in enumerate(buried):
        on.setdefault((b["structure"], tuple(sorted(b["roots"]))), n)
    out = []
    for k, p in enumerate(proposals):
        at = p.get("source", p.get("cell"))
        if at is None:
            at = on.get((p["structure"], tuple(sorted(p["roots"]))), idea[k % len(idea)])
        out.append({**p, "cites": at})
    return out


def citation(row_id: str, mechanism: str) -> list[dict[str, str]]:
    """A proposal's `differs_from` as the tree sees it: one graveyard row, and the proposal's own mechanism text as the
    "how" (the same shape for every proposal, CITATIONS)."""
    return [{"row": row_id, "how": " ".join(mechanism.split())}]


def reads_as(cards: Any, text: str, row: dict[str, Any]) -> int:
    """How closely a text's own words read as a buried row's (production's keyword reading, `cards.infer_key` and
    `cards.infer_inputs`): 2 the same class and inputs, 1 the same class, else 0."""
    mine, theirs = cards.infer_key(text, None, row["dte"]), cards.infer_key(row["mechanism"], None, row["dte"])
    if not (mine and theirs and mine["class"] == theirs["class"]):
        return 0
    return 2 if cards.infer_inputs(text) == cards.infer_inputs(row["mechanism"]) else 1


def holding(dte: list[int]) -> str:
    """The days to expiry's holding bucket (`cards.infer_key`'s rule for a text that names none)."""
    hi = max(dte)
    return "intraday" if hi <= 0 else "days_1_3" if hi <= 5 else "days_4_10" if hi <= 14 else "days_11_plus"


def terms(cards: Any, text: str, dte: list[int]) -> dict[str, Any]:
    """A card's cell from a case's own fields: production's reading of its text, its days to expiry's holding."""
    key = cards.infer_key(text, None, dte)
    classes = sorted(cards.MECHANISM_CLASSES)
    cls = key["class"] if key else classes[int(hashlib.sha256(text.encode()).hexdigest()[:8], 16) % len(classes)]
    inputs = cards.infer_inputs(text)[:cards.MAX_INPUTS] or ["underlying_price"]
    return {"mechanism_class": cls, "inputs": inputs, "holding": holding(dte)}


def card(text: str, cell: dict[str, Any]) -> dict[str, Any]:
    hypothesis = " ".join(text.split())
    if len(hypothesis) < 60:
        hypothesis += HYPOTHESIS_PAD
    return {"hypothesis": hypothesis, **cell, **CARD_FIXED}


def carded(cards: Any, buried: list[dict[str, Any]], proposals: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """(the buried rows' cards, the proposals' cards), from the cases alone (the module docstring), each valid, and the
    construction checked with the card module's own matching (`match_keys`, `matches`, `match_inputs`, as
    `cards.RebirthIndex` reads a carded row): each card-path restatement falls in its own row's refuted cell, no other
    proposal falls in any, and every same-cell control carries its idea row's exact key on that row's slice. A defect
    is no answer."""
    cells = [terms(cards, b["mechanism"], b["dte"]) for b in buried]

    def cell(p: dict[str, Any]) -> dict[str, Any]:
        at = p.get("cell", p.get("source"))
        return cells[at] if at is not None else terms(cards, p["mechanism"], p["dte"])

    dead = [card(b["mechanism"], cells[n]) for n, b in enumerate(buried)]
    live = [card(p["mechanism"], cell(p)) for p in proposals]
    for c, structure in [*zip(dead, (b["structure"] for b in buried)), *zip(live, (p["structure"] for p in proposals))]:
        valid, problems = cards.validate(c, structure)
        if valid is None:
            raise SystemExit(f"the judge built an invalid card ({'; '.join(problems)[:300]})")
    refuted = {n: {**cards.key_of(dead[n], b["structure"]), "inputs": cards.match_inputs(dead[n], b["mechanism"])}
               for n, b in enumerate(buried) if b["path"] == "card"}
    for p, c in zip(proposals, live):
        keys, _ = cards.match_keys(c, p["structure"], p["mechanism"], p["dte"])
        hit = {n for n, row in refuted.items() if any(cards.matches(k, row) for k in keys)}
        if (p["source"] not in hit) if p.get("path") == "card" else bool(hit):
            raise SystemExit("the judge's cards do not fall as built (a card-path restatement falls in its row's refuted "
                             "cell, and nothing else falls in any)")
        if "cell" in p:
            row = buried[p["cell"]]
            if (row["path"] != "idea" or (p["structure"], sorted(p["roots"])) != (row["structure"], sorted(row["roots"]))
                    or cards.key_of(c, p["structure"]) != cards.key_of(dead[p["cell"]], row["structure"])):
                raise SystemExit("a same-cell control does not carry its idea row's key on that row's slice")
    return dead, live


def main() -> None:
    opts = _common.args()
    # The cases are drawn before the tree's code loads; the pool is not kept past this point.
    buried, proposals = cases(opts.split, opts.seed, opts.pool)
    opts.pool = None

    def body() -> dict[str, Any]:
        # The cards, from the cases alone, with the pinned base's card module (outside every lane's surface), before the
        # tree's architect loads: each is valid and falls as built, or the judge has no answer.
        from league.swarm import cards

        dead_cards, live_cards = carded(cards, buried, proposals)

        from league.swarm.architect import Architect
        from league.swarm.store import SwarmStore

        class Clock:
            now = 1_790_000_000.0

            def __call__(self):
                return self.now

        clock = Clock()
        roots = sorted({r for row in buried + proposals for r in row["roots"]})
        # Release B's birth quota (league/swarm/allocation.py `BirthQuota`, a structure-family diversity pressure outside
        # this lane's surface) rests here (`min_alive` above any population), as the class cap does: the judge measures
        # the architect's admission (idea admission, which the lane's lever changes, and the card checks, which it may
        # not loosen), and nothing else refuses a proposal. The card settings stay at their defaults, as in production.
        settings = {"population": {"start": 0, "ceiling": 10_000}, "architect": {"max_new": 1000, "max_alive_per_class": 0},
                    "gym": {"roots": roots}, "allocation": {"births": {"min_alive": 10 ** 6}}}
        with tempfile.TemporaryDirectory() as temp:
            store = SwarmStore(Path(temp), clock=clock)
            try:
                ids = []
                for n, row in enumerate(buried):
                    spec = {"id": f"buried-{n}", "mechanism": row["mechanism"], "structure": row["structure"],
                            "roots": row["roots"], "dte": row["dte"], "card_sha": cards.card_sha(dead_cards[n])}
                    with store.atomic():
                        fam = store.add_family(spec, origin="seed")
                        cards.put(store, fam["id"], dead_cards[n], row["structure"])
                    clock.now += 60
                    reason, lesson = CARD_DEATH if row["path"] == "card" else IDEA_DEATHS[n % len(IDEA_DEATHS)]
                    store.retire(fam["id"], reason)
                    store.bury(fam["id"], lesson)
                    ids.append(fam["id"])
                clock.now += 3600
                # The graveyard must read as built: the card check covers the card-path rows and nothing else.
                covered = {r["row"] for r in cards.RebirthIndex(store, settings).rows}
                if covered != {i for i, b in zip(ids, buried) if b["path"] == "card"}:
                    raise SystemExit("the tree's tags do not read the judge's graveyard as built (the card check covers "
                                     f"{len(covered)} rows)")
                statements: list[str] = []
                store._db.set_trace_callback(statements.append)
                rows = []
                for n, p in enumerate(proposals):
                    rows.append({"slug": f"proposal-{n}", "mechanism": p["mechanism"], "structure": p["structure"],
                                 "roots": p["roots"], "dte": list(p["dte"]), "sketch": f"judge case {n}",
                                 "card": live_cards[n], "differs_from": citation(ids[p["cites"]], p["mechanism"])})
                Architect(store, None, settings, clock=clock).admit(rows, digest=True)
                store._db.set_trace_callback(None)
                # A birth is its proposal by the sketch's marker, whatever the admission did to the mechanism text.
                by_case: dict[int, dict[str, Any]] = {}
                for fam in store.families(alive=True):
                    sketch = str((fam.get("spec") or {}).get("sketch") or "")
                    if sketch.startswith("judge case "):
                        by_case[int(sketch.split()[-1])] = fam
                dead_slices = {(b["structure"], tuple(sorted(b["roots"]))) for b in buried}
                lineage_of = [(store.family(i) or {}).get("lineage") for i in ids]
                rebirths = novel_born = uncounted = rewritten = fresh = card_born = controls_born = 0
                controls = sum(1 for p in proposals if "cell" in p)
                for n, p in enumerate(proposals):
                    fam = by_case.get(n)
                    if fam is None:
                        continue
                    rebirths += p["label"] == "rebirth"
                    novel_born += p["label"] == "novel"
                    card_born += p.get("path") == "card"
                    controls_born += "cell" in p
                    if fam["mechanism"] != " ".join(p["mechanism"].split())[:600]:
                        rewritten += 1
                    if ((p["structure"], tuple(sorted(p["roots"]))) in dead_slices and not fam.get("parent")
                            and not (fam.get("spec") or {}).get("prior_lineage")):
                        uncounted += 1
                    if p["label"] == "rebirth" and fam.get("lineage") != lineage_of[p["source"]]:
                        fresh += 1
                novel_total = sum(1 for p in proposals if p["label"] == "novel")
                return {"rebirths_admitted": rebirths, "novel_refused": novel_total - novel_born,
                        "trials_uncounted": uncounted, "mechanism_rewritten": rewritten, "rebirths_fresh_lineage": fresh,
                        "card_path_admitted": card_born,
                        "card_path_proposed": sum(1 for p in proposals if p.get("path") == "card"),
                        "same_cell_proposed": controls, "same_cell_refused": controls - controls_born,
                        "rebirths_proposed": sum(1 for p in proposals if p["label"] == "rebirth"), "novel_proposed": novel_total,
                        "born": len(by_case), "sqlite_statements": len(statements), "cases": len(proposals)}
            finally:
                store.close()

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
