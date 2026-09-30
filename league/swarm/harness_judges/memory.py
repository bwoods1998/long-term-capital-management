"""memory-rebirth-v1: how many restated graveyard mechanisms the architect lets be born again, and how many new ones it
stops.

A synthetic store holds a graveyard of buried families (mechanisms on slices). The tree under test's architect admits a
batch of proposals (`league.swarm.architect.Architect.admit(rows, digest=True)`, the Claude route's admission): each
proposal is a REBIRTH (the buried claim restated on the buried slice, with a new second sentence) or NOVEL (a mechanism
nobody buried, on a buried slice, or a buried mechanism on another slice: new conditions). Labels are fixed by
construction. Proposals that cite the buried row in `differs_from` do so with a parameter-level "how" only (a restated
claim with new parameters is still the same idea).

dev: eight buried mechanisms, their light restatements and eight novel proposals. heldout: twelve buried mechanisms
drawn from a wider bank, restatements with synonym swaps, reordered clauses and hedges, and novel proposals, drawn
from the seed. Answer: rebirths_admitted, novel_refused, sqlite_statements (the store work, the lane's cost).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import _common

PROTOCOL = "memory-rebirth-v1"
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
        chosen = list(range(8))
        slices = SLICES[:8]
        buried = [{"mechanism": BANK[i], "structure": s, "roots": roots} for i, (s, roots) in zip(chosen, slices)]
        proposals = [{"label": "rebirth", "mechanism": restate(b["mechanism"], None), "structure": b["structure"],
                      "roots": b["roots"], "cites": n % 2 == 0} for n, b in enumerate(buried)]
        spare = [BANK[i] for i in range(8, 12)] + NOVEL[:2]
        proposals += [{"label": "novel", "mechanism": spare[n % len(spare)], "structure": slices[n][0], "roots": slices[n][1],
                       "cites": False} for n in range(6)]
        proposals += [{"label": "novel", "mechanism": buried[n]["mechanism"], "structure": slices[(n + 3) % 8][0],
                       "roots": ["DIA"], "cites": False} for n in range(2)]
        return buried, proposals
    r = _common.rng(seed, PROTOCOL)
    order = list(range(len(BANK)))
    r.shuffle(order)
    slices = list(SLICES)
    r.shuffle(slices)
    buried = [{"mechanism": BANK[i], "structure": s, "roots": roots} for i, (s, roots) in zip(order[:12], slices)]
    proposals = [{"label": "rebirth", "mechanism": restate(b["mechanism"], r), "structure": b["structure"], "roots": b["roots"],
                  "cites": r.random() < 0.5} for b in buried]
    fresh = [BANK[i] for i in order[12:]] + NOVEL
    r.shuffle(fresh)
    proposals += [{"label": "novel", "mechanism": fresh[n % len(fresh)], "structure": slices[n][0], "roots": slices[n][1],
                   "cites": False} for n in range(8)]
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
                           "roots": p["roots"], "dte": [0, 5]}
                    if p["cites"]:
                        home = next((i for i, b in zip(ids, buried) if b["mechanism"] in p["mechanism"] or
                                     (b["structure"], b["roots"]) == (p["structure"], p["roots"])), ids[0])
                        row["differs_from"] = [{"row": home, "how": "different parameters"}]
                    rows.append(row)
                born = set(Architect(store, None, settings, clock=clock).admit(rows, digest=True))
                store._db.set_trace_callback(None)
                mechanisms = {f["mechanism"]: f["id"] for f in store.families(alive=True)}
                admitted = [p for p in proposals if " ".join(p["mechanism"].split())[:600] in mechanisms]
                rebirths = sum(1 for p in admitted if p["label"] == "rebirth")
                novel_born = sum(1 for p in admitted if p["label"] == "novel")
                novel_total = sum(1 for p in proposals if p["label"] == "novel")
                return {"rebirths_admitted": rebirths, "novel_refused": novel_total - novel_born,
                        "rebirths_proposed": sum(1 for p in proposals if p["label"] == "rebirth"), "novel_proposed": novel_total,
                        "born": len(born), "sqlite_statements": len(statements), "cases": len(proposals)}
            finally:
                store.close()

    _common.answer(PROTOCOL, opts.split, opts.seed, body)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    main()
