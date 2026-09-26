"""R5 (the close-the-gaps run, Sept 24, 2026): no probe on a losing family.

`allocator.family_probe` rests on these readings, taken on the read-only 15:06Z snapshot of the live House:

1. Every allocator promotion to real money (an `eval.verdict` promote to rung 2, `via` "allocator") since
   Sept 23 00:00Z, with its family's pooled forward record AT THE PROMOTION -- `House.family_forward`'s
   definition exactly: the count of active `eval.block` rows and their summed `log_growth`, over every agent
   ever born into the family (living or dead), through the promotion's ledger position -- and whether it was
   LOSING by the House's own line (`families.losing`: 6 or more active blocks, `game.json`
   `economy.losing_family_min_blocks`, and a sum at or below -1e-9). Then the stay's realized real P&L: every
   settlement and every closing sale on the real book (dust excluded) after the promotion, until the stay's
   first demotion below rung 2.
2. Every agent seated on real money at the snapshot as a probe (the board's band), with its family's forward
   record at the snapshot and its stake.
3. Every demotion from rung 2 on the ledger, how the rule's hold classifies it (the row's `band_from`; a row that
   does not name its band, by its family's state in the mechanism ledger's last `family.record` row before it),
   and its family's forward record since it.

Usage: python3 R5-family-probe.py <ledger.sqlite> <allocator-board.json> [since]
"""
import collections
import json
import sqlite3
import sys

LOSING_MIN_BLOCKS = 6
REAL_BOOKS = ("kalshi", "alpaca")

db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
board = json.load(open(sys.argv[2]))
since = sys.argv[3] if len(sys.argv) > 3 else "2026-09-23T00:00:00Z"
head = db.execute("select max(seq), max(at) from ledger").fetchone()
print(f"ledger through seq {head[0]} ({head[1]}); board at {board.get('at')}")

born = {}
for agent, payload in db.execute("select agent, payload from ledger where kind='agent.born'"):
    p = json.loads(payload)
    born[agent] = (p.get("family"), p.get("venue"))
family_of = {a: f for a, (f, _) in born.items()}
blocks = [(seq, agent, json.loads(payload)) for seq, agent, payload in
          db.execute("select seq, agent, payload from ledger where kind='eval.block' order by seq")]


def forward(family, after=0, through=None):
    """(active blocks, summed log growth) of `family` over (after, through]: House.family_forward's sum."""
    n, growth = 0, 0.0
    for seq, agent, p in blocks:
        if seq <= after:
            continue
        if through is not None and seq > through:
            break
        if p.get("active") and family_of.get(agent) == family:
            n += 1
            growth += float(p.get("log_growth") or 0.0)
    return n, growth


def losing(n, growth):
    return n >= LOSING_MIN_BLOCKS and growth <= -1e-9


verdicts = [(seq, at, agent, json.loads(payload)) for seq, at, agent, payload in
            db.execute("select seq, at, agent, payload from ledger where kind='eval.verdict' order by seq")]
closes = collections.defaultdict(list)
for seq, agent, kind, payload in db.execute(
        "select seq, agent, kind, payload from ledger where kind in ('book.settle', 'book.fill') order by seq"):
    p = json.loads(payload)
    if p.get("book") not in REAL_BOOKS or p.get("source") == "dust":
        continue
    made = p.get("pnl") if kind == "book.settle" else p.get("realized")
    if made is not None:
        closes[agent].append((seq, float(made)))

print("\n1. Allocator promotions to real money since", since)
totals = {True: [0, 0.0, 0, 0, 0], False: [0, 0.0, 0, 0, 0]}  # promotions, $, closes, positive closes, positive stays
for seq, at, agent, p in verdicts:
    if at < since or p.get("decision") != "promote" or int(p.get("to_rung") or 0) != 2 or p.get("via") != "allocator":
        continue
    end = next(((s, a2, q) for s, a2, who, q in verdicts if s > seq and who == agent and q.get("decision") == "demote"
                and int(q.get("to_rung") or 0) < 2), None)
    made = [v for s, v in closes[agent] if s > seq and (end is None or s <= end[0])]
    n, growth = forward(family_of.get(agent), through=seq)
    lose = losing(n, growth)
    row = totals[lose]
    row[0] += 1
    row[1] += sum(made)
    row[2] += len(made)
    row[3] += sum(1 for v in made if v > 0)
    row[4] += sum(made) > 0
    print(f"  {at[:19]} {agent:22} {str(family_of.get(agent))[:34]:34} {p.get('band_to') or '?':6} "
          f"forward {n:3d} blocks {growth:+.4f} {'LOSING' if lose else '      '} stay {sum(made):+7.2f} on {len(made):2d} closes "
          f"({sum(1 for v in made if v > 0)} positive); ended {end[1][11:19] if end else 'open'} {(end[2].get('reason') or '')[:60] if end else ''}")
for lose, (count, usd, n, positive, stays) in totals.items():
    print(f"  {'losing' if lose else 'not losing'}: {count} promotions, {usd:+.2f} realized on {n} closes, "
          f"{positive} positive closes, {stays} stays positive")

print("\n2. Probes seated at the snapshot")
seated, on_losing = 0, []
for agent, row in sorted(board["agents"].items()):
    if row.get("band") != "probe":
        continue
    seated += 1
    n, growth = forward(row.get("family"))
    stake = float(row.get("stake_usd") or 0)
    lose = losing(n, growth)
    if lose:
        on_losing.append((agent, stake))
    print(f"  {agent:22} {row.get('venue'):7} {str(row.get('family'))[:34]:34} stake {stake:6.2f} forward {n:3d} blocks {growth:+.4f}"
          f"{'  LOSING' if lose else ''}")
print(f"  {len(on_losing)} of {seated} seated probes on a losing family: ${sum(s for _, s in on_losing):.2f} of stake "
      f"({', '.join(a for a, _ in on_losing)})")

print("\n3. Demotions from rung 2, the hold's classification, and each family's forward record since")
states = collections.defaultdict(list)
for seq, payload in db.execute("select seq, payload from ledger where kind='family.record' order by seq"):
    p = json.loads(payload)
    states[(p.get("family"), p.get("venue"))].append((seq, p.get("state")))
for seq, at, agent, p in verdicts:
    if p.get("decision") != "demote" or int(p.get("from_rung") or 0) != 2 or int(p.get("to_rung") or 0) > 1:
        continue
    family, venue = born.get(agent, (None, None))
    before = [state for s, state in states.get((family, venue), []) if s < seq]
    band = p.get("band_from")
    probe = band == "probe" if band else (before[-1] == "unproven" if before else False)
    n, growth = forward(family, after=seq)
    print(f"  {at[:19]} {agent:22} {str(family)[:32]:32} band_from {str(band):5} ledger state {before[-1] if before else '-':8} "
          f"{'PROBE' if probe else '     '} since: {n:3d} blocks {growth:+.4f}{'  turned' if n >= LOSING_MIN_BLOCKS and growth >= 1e-9 else ''}")
