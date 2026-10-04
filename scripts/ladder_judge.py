"""THE LADDER'S BINDING VERDICT: rule v2 of PREREG-LADDER-BINDING.md, as DESIGN.md pins its reading.

    python3 judge_confirm.py DESKS.json [DESKS.json ...]

Each file is a benchmark output holding {"desks": [{"world", "replication", "rows": [...]}]}; a row is one entrant:
{"id", "world", "kind", "ladder", "ladder_outcome", "sealed", "sealed_bare"} (and "start", its admission session, for
the secondary readings). Standard library only. Frozen by its sha256 in DESIGN.md before the confirmation run: this
file, unchanged, gives the verdict; nothing else does.

THE COUNT (primary): the first COUNTED entrants of each desk in admission order (ids 0..31: two whole generations of the
16 slots), whatever their outcome, for the ladder and for the sealed look alike. An entrant among them still "running"
at the desk's end is an error (the run is not judged). No entrant is counted or left out on its own outcome.

THE RULE (all three items must hold):
 1. every negative world W of the single-world desks, and the mixed desks' negatives taken together as one W: the
    ladder's false-promotion rate <= 1.0%, AND the one-sided Fisher exact test of "the ladder's rate > the sealed
    look's (with holds)" has p >= 0.05;
 2. pooled over the single-world desks' negatives, and over the mixed desks' negatives: the ladder's false promotions
    <= the sealed look's, with and without its holds (the fewer of the two);
 3. the mixed desks' positives: the ladder's missed signals <= the sealed look's, with and without its holds (the fewer).

Exit 0: every item holds (the ladder may bind). Exit 1: one does not (the ladder records). Exit 2: the input is not
what the design pins (a world or a replication missing, a counted entrant still running, a duplicate desk).
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict

COUNTED = 32
NEGATIVE = ("absent", "absent_fat", "absent_sparse", "cost_erased", "drift_only", "fading", "skewed_null")
POSITIVE = ("planted_dense", "planted_directional", "planted_premium", "planted_sparse")
MIXED = "mixed"
FP_CAP = 0.01
FISHER_MIN = 0.05


def fisher_greater(a: int, n1: int, b: int, n2: int) -> float:
    """One-sided Fisher exact p of "rate 1 > rate 2" for a of n1 against b of n2 (exact integers)."""
    k, total = a + b, n1 + n2
    if k == 0:
        return 1.0
    return sum(math.comb(n1, x) * math.comb(n2, k - x) for x in range(a, min(k, n1) + 1)) / math.comb(total, k)


def load(paths: list[str]) -> dict[str, dict[int, list[dict]]]:
    desks: dict[str, dict[int, list[dict]]] = defaultdict(dict)
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for desk in json.load(handle)["desks"]:
                world, replication = str(desk["world"]), int(desk["replication"])
                if replication in desks[world]:
                    raise SystemExit(f"judge: {world} replication {replication} appears twice ({path})")
                desks[world][replication] = desk["rows"]
    return desks


def counted(rows: list[dict], world: str, replication: int) -> list[dict]:
    first = [r for r in rows if int(r["id"]) < COUNTED]
    if len(first) != COUNTED or sorted(int(r["id"]) for r in first) != list(range(COUNTED)):
        raise SystemExit(f"judge: {world} replication {replication} has not its first {COUNTED} entrants")
    running = [r["id"] for r in first if r["ladder_outcome"] == "running"]
    if running:
        raise SystemExit(f"judge: {world} replication {replication}: counted entrants {running} are still running")
    return first


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    desks = load(argv)
    missing = [w for w in NEGATIVE + (MIXED,) if w not in desks]
    if missing:
        raise SystemExit(f"judge: no desks of {missing}")
    sizes = {w: len(desks[w]) for w in NEGATIVE + (MIXED,)}
    if len(set(sizes.values())) != 1 or min(sizes.values()) < 30:
        raise SystemExit(f"judge: every judged world needs the same number of replications, at least 30: {sizes}")
    for world, by in desks.items():
        if sorted(by) != list(range(len(by))):
            raise SystemExit(f"judge: {world}'s replications are not 0..{len(by) - 1}")
    rows = {w: [r for rep in sorted(by) for r in counted(by[rep], w, rep)] for w, by in desks.items()}

    print(f"rule v2, the first {COUNTED} entrants a desk; replications a world: {sizes[MIXED]}")
    results: dict[str, bool] = {}
    pooled = [0, 0, 0, 0]
    for world in NEGATIVE + (MIXED,):
        neg = [r for r in rows[world] if r["kind"] == "negative"]
        n = len(neg)
        k = sum(bool(r["ladder"]) for r in neg)
        s = sum(bool(r["sealed"]) for r in neg)
        sb = sum(bool(r["sealed_bare"]) for r in neg)
        p = fisher_greater(k, n, s, n)
        cap, fisher = k / n <= FP_CAP, p >= FISHER_MIN
        results[f"1 cap {world}"], results[f"1 fisher {world}"] = cap, fisher
        print(f"  item 1  {world:14s} ladder {k:4d}/{n:5d} = {100 * k / n:6.3f}%  sealed {s:4d}  bare {sb:4d}  "
              f"Fisher p {p:.4f}  {'ok' if cap and fisher else 'FAIL'}")
        if world != MIXED:
            for i, v in enumerate((k, s, sb, n)):
                pooled[i] += v
        else:
            mixed = (k, s, sb, n)
    results["2 pooled single"] = pooled[0] <= min(pooled[1], pooled[2])
    results["2 pooled mixed"] = mixed[0] <= min(mixed[1], mixed[2])
    print(f"  item 2  single-world negatives: ladder {pooled[0]}/{pooled[3]}  sealed {pooled[1]}  bare {pooled[2]}  "
          f"{'ok' if results['2 pooled single'] else 'FAIL'}")
    print(f"  item 2  mixed negatives:        ladder {mixed[0]}/{mixed[3]}  sealed {mixed[1]}  bare {mixed[2]}  "
          f"{'ok' if results['2 pooled mixed'] else 'FAIL'}")
    pos = [r for r in rows[MIXED] if r["kind"] == "positive"]
    n = len(pos)
    lm = sum(not r["ladder"] for r in pos)
    sm = sum(not r["sealed"] for r in pos)
    smb = sum(not r["sealed_bare"] for r in pos)
    results["3 missed"] = n > 0 and lm <= min(sm, smb)
    print(f"  item 3  mixed positives missed: ladder {lm}/{n} = {lm / n:.4f}  sealed {sm} = {sm / n:.4f}  bare {smb} = "
          f"{smb / n:.4f}  margin {min(sm, smb) - lm:+d}  {'ok' if results['3 missed'] else 'FAIL'}")

    print("  secondary readings (not judged):")
    for label, lo, hi in (("ids 0-15 ", 0, 16), ("ids 16-31", 16, 32)):
        part = [r for r in pos if lo <= int(r["id"]) < hi]
        print(f"    mixed positives {label}: {len(part)}  ladder promoted {sum(bool(r['ladder']) for r in part)}  "
              f"sealed promoted {sum(bool(r['sealed']) for r in part)}")
    by_world: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for r in pos:
        acc = by_world[str(r["world"])]
        acc[0] += 1
        acc[1] += bool(r["ladder"])
        acc[2] += bool(r["sealed"])
    print("    mixed positives by world (of / ladder / sealed): "
          + ", ".join(f"{w} {a}/{b}/{c}" for w, (a, b, c) in sorted(by_world.items())))
    for world in POSITIVE:
        if world in rows:
            part = rows[world]
            print(f"    {world:20s} missed: ladder {sum(not r['ladder'] for r in part)}/{len(part)}  "
                  f"sealed {sum(not r['sealed'] for r in part)}")
    ended = [r for by in desks[MIXED].values() for r in by if r["ladder_outcome"] != "running" and r["kind"] == "positive"]
    print(f"    the benchmark's old count (ended inside the desk), mixed positives missed: ladder "
          f"{sum(not r['ladder'] for r in ended)}/{len(ended)}  sealed {sum(not r['sealed'] for r in ended)}")

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        print(f"VERDICT: rule v2 is NOT met ({', '.join(failed)}): ladder.binding stays false; the ladder records.")
        return 1
    print("VERDICT: rule v2 is met on every item: ladder.binding may be true.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
