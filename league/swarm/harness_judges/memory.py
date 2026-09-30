"""memory-rebirth-v2: how many restated graveyard mechanisms the architect lets be born again, how many new ones it
stops, and whether what it admits keeps its lineage's trials and its own words.

A synthetic store holds a graveyard of buried families (mechanisms on slices). The tree under test's architect admits a
batch of proposals (`league.swarm.architect.Architect.admit(rows, digest=True)`, the Claude route's admission): each
proposal is a REBIRTH (the buried claim restated on the buried slice, with a new second sentence) or NOVEL (a mechanism
nobody buried, on a buried slice, or a buried mechanism on another slice: new conditions). Labels are fixed by
construction. Proposals that cite the buried row in `differs_from` do so with a parameter-level "how" only (a restated
claim with new parameters is still the same idea). Each proposal carries a marker in its sketch, so a birth is matched
to its proposal whatever the admission does to the text.

dev: eight buried mechanisms from the dev bank, their light restatements and eight novel proposals. heldout: SEEDED
VARIANTS FROM A DISJOINT BANK (the other twelve buried mechanisms, their own novel ideas), restated with synonym swaps,
reordered clauses and hedges. The bank is in this public file: the split is held out from the dev split and the brief,
not from a determined reader; the concurrent canary is the held-out test no one can read in advance.

Answer: rebirths_admitted, novel_refused, trials_uncounted (a birth on a slice with a buried family that neither
continues a lineage nor counts the slice's trials: the multiple-testing control loosened; must be 0),
mechanism_rewritten (a birth whose mechanism is not its proposal's text: the rebirth detector would be fooled; must be
0), rebirths_fresh_lineage (admitted rebirths that start a lineage of their own: a fresh look ration),
sqlite_statements (the store work, the lane's cost).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import _common

PROTOCOL = "memory-rebirth-v2"
BANK = [
    "Small caps lag large caps after a strong opening drive, and IWM catches up to SPY over the session.",
    "Implied volatility is bid before scheduled macro releases and decays after the print, so short-dated premium is rich into the event.",
    "Month-end rebalancing flows push index funds toward the close on the last trading day, and the move partly reverses the next morning.",
    "Put skew overshoots after a sharp selloff because hedgers overpay for protection, and it mean-reverts over the following week.",
    "Gold and long bonds compete for the same haven flow, so a wide gap between their recent returns tends to close.",
    "Retail call buying in high-attention names inflates call implied volatility relative to puts, which fades once attention cools.",
    "Overnight gaps in QQQ that are not confirmed by futures volume tend to fill during the first hour of trading.",
    "Dealer gamma positioning pins the index near large open-interest strikes on expiration afternoons.",
    "Semiconductor leadership over the broad growth index predicts a catch-up move in the laggard fund within two weeks.",
    "Earnings drift continues in the direction of the surprise for several sessions as slower holders adjust.",
    "Realized volatility clusters, so a quiet week after a volatile one prices straddles too cheaply.",
    "Friday afternoon option premium underprices weekend headline risk in commodity funds.",
    "The opening range breakout on high relative volume continues in the breakout direction through midday.",
    "Treasury yields respond to equity growth surprises with a lag, so TLT follows a large SMH move.",
    "Credit spreads widen before equity volatility rises, so a jump in high-yield spreads precedes index put demand.",
    "Energy stocks react to crude inventory surprises faster than the energy fund's options reprice.",
    "Short-dated call skew in crowded names collapses after a squeeze peaks and the chasers leave.",
    "Volatility term structure inversion signals panic that resolves within days, so the front month is too expensive.",
    "Airline stocks lag oil price moves by a session because hedging disclosures slow the repricing.",
    "Quarter-end window dressing lifts recent winners into the last week of the quarter.",
]
SLICES = [("debit_vertical", ["SPY"]), ("credit_vertical", ["QQQ"]), ("long_straddle", ["IWM"]), ("debit_vertical", ["QQQ"]),
          ("long_strangle", ["SPY"]), ("credit_vertical", ["SPY"]), ("debit_vertical", ["IWM"]), ("iron_condor", ["SPY"]),
          ("long_straddle", ["QQQ"]), ("credit_vertical", ["IWM"]), ("debit_vertical", ["XSP"]), ("long_strangle", ["QQQ"])]
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
#: The held-out split's own novel ideas (the dev split never proposes them).
NOVEL_HELD = ["Lunchtime liquidity gaps widen spreads enough that midday entries overpay against the afternoon.",
              "Weekly expiries concentrate hedging demand on Thursdays, which lifts short-dated premium a day early.",
              "Sector rotation into defensives shows up in utility call volume before the index turns.",
              "Large single-name earnings in the index's top weights move index implied volatility more than its peers.",
              "A holiday-shortened week compresses theta decay into fewer sessions than the calendar suggests.",
              "Dealers short gamma after a large down day amplify the next morning's move in either direction."]
DEV_BANK = BANK[:8]
HELD_BANK = BANK[8:]


def restate(text: str, r: Any | None) -> str:
    out = text
    for word, other in SYNONYMS.items():
        if word in out and (r is None or r.random() < 0.7):
            out = out.replace(word, other, 1)
    if r is not None and ", " in out and r.random() < 0.5:
        head, tail = out.rstrip(".").split(", ", 1)
        out = f"{tail[0].upper()}{tail[1:]}, as {head[0].lower()}{head[1:]}."
    second = SECONDS[0] if r is None else r.choice(SECONDS)
    hedge = "" if r is None or r.random() < 0.5 else " The idea is kept but the timing differs."
    return f"{out} {second}{hedge}"


def cases(split: str, seed: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(buried, proposals)."""
    if split == "dev":
        slices = SLICES[:8]
        buried = [{"mechanism": text, "structure": s, "roots": roots} for text, (s, roots) in zip(DEV_BANK, slices)]
        proposals = [{"label": "rebirth", "mechanism": restate(b["mechanism"], None), "structure": b["structure"],
                      "roots": b["roots"], "cites": n % 2 == 0} for n, b in enumerate(buried)]
        spare = NOVEL
        proposals += [{"label": "novel", "mechanism": spare[n % len(spare)], "structure": slices[n][0], "roots": slices[n][1],
                       "cites": False} for n in range(6)]
        proposals += [{"label": "novel", "mechanism": buried[n]["mechanism"], "structure": slices[(n + 3) % 8][0],
                       "roots": ["DIA"], "cites": False} for n in range(2)]
        return buried, proposals
    r = _common.rng(seed, PROTOCOL)
    order = list(HELD_BANK)
    r.shuffle(order)
    slices = list(SLICES)
    r.shuffle(slices)
    buried = [{"mechanism": text, "structure": s, "roots": roots} for text, (s, roots) in zip(order[:8], slices)]
    proposals = [{"label": "rebirth", "mechanism": restate(b["mechanism"], r), "structure": b["structure"], "roots": b["roots"],
                  "cites": r.random() < 0.5} for b in buried]
    fresh = order[8:] + list(NOVEL_HELD)
    r.shuffle(fresh)
    proposals += [{"label": "novel", "mechanism": fresh[n % len(fresh)], "structure": slices[n % len(slices)][0],
                   "roots": slices[n % len(slices)][1], "cites": False} for n in range(8)]
    proposals += [{"label": "novel", "mechanism": buried[n]["mechanism"], "structure": buried[n]["structure"],
                   "roots": [r.choice(["DIA", "TLT", "GLD"])], "cites": False} for n in range(4)]
    r.shuffle(proposals)
    return buried, proposals


def main() -> None:
    opts = _common.args()

    def body() -> dict[str, Any]:
        from league.swarm.architect import Architect
        from league.swarm.store import SwarmStore

        buried, proposals = cases(opts.split, opts.seed)

        class Clock:
            now = 1_790_000_000.0

            def __call__(self):
                return self.now

        clock = Clock()
        roots = sorted({r for row in buried + proposals for r in row["roots"]})
        settings = {"population": {"start": 0, "ceiling": 10_000}, "architect": {"max_new": 1000, "max_alive_per_class": 0},
                    "gym": {"roots": roots}}
        with tempfile.TemporaryDirectory() as temp:
            store = SwarmStore(Path(temp), clock=clock)
            try:
                ids = []
                for n, row in enumerate(buried):
                    fam = store.add_family({"id": f"buried-{n}", **row}, origin="seed")
                    clock.now += 60
                    store.retire(fam["id"], "the mechanism was refuted on Train")
                    store.bury(fam["id"], "Refuted: the signal did not beat its placebo after costs.")
                    ids.append(fam["id"])
                clock.now += 3600
                statements: list[str] = []
                store._db.set_trace_callback(statements.append)
                rows = []
                for n, p in enumerate(proposals):
                    row = {"slug": f"proposal-{n}", "mechanism": p["mechanism"], "structure": p["structure"],
                           "roots": p["roots"], "dte": [0, 5], "sketch": f"judge case {n}"}
                    if p["cites"]:
                        home = next((i for i, b in zip(ids, buried) if b["mechanism"] in p["mechanism"] or
                                     (b["structure"], b["roots"]) == (p["structure"], p["roots"])), ids[0])
                        row["differs_from"] = [{"row": home, "how": "different parameters"}]
                    rows.append(row)
                Architect(store, None, settings, clock=clock).admit(rows, digest=True)
                store._db.set_trace_callback(None)
                # A birth is its proposal by the sketch's marker, whatever the admission did to the mechanism text.
                by_case: dict[int, dict[str, Any]] = {}
                for fam in store.families(alive=True):
                    sketch = str((fam.get("spec") or {}).get("sketch") or "")
                    if sketch.startswith("judge case "):
                        by_case[int(sketch.split()[-1])] = fam
                dead_slices = {(b["structure"], tuple(sorted(b["roots"]))): i for i, b in zip(ids, buried)}
                lineage_of = {i: (store.family(i) or {}).get("lineage") for i in ids}
                rebirths = novel_born = uncounted = rewritten = fresh = 0
                for n, p in enumerate(proposals):
                    fam = by_case.get(n)
                    if fam is None:
                        continue
                    rebirths += p["label"] == "rebirth"
                    novel_born += p["label"] == "novel"
                    if fam["mechanism"] != " ".join(p["mechanism"].split())[:600]:
                        rewritten += 1
                    home = dead_slices.get((p["structure"], tuple(sorted(p["roots"]))))
                    if home is not None and not fam.get("parent") and not (fam.get("spec") or {}).get("prior_lineage"):
                        uncounted += 1
                    if p["label"] == "rebirth" and fam.get("lineage") != lineage_of.get(home):
                        fresh += 1
                novel_total = sum(1 for p in proposals if p["label"] == "novel")
                return {"rebirths_admitted": rebirths, "novel_refused": novel_total - novel_born,
                        "trials_uncounted": uncounted, "mechanism_rewritten": rewritten, "rebirths_fresh_lineage": fresh,
                        "rebirths_proposed": sum(1 for p in proposals if p["label"] == "rebirth"), "novel_proposed": novel_total,
                        "born": len(by_case), "sqlite_statements": len(statements), "cases": len(proposals)}
            finally:
                store.close()

    _common.answer(PROTOCOL, opts, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
