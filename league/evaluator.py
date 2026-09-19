"""The ladder: who climbs, who stays, who dies, and the statistics that decide it.

Four rungs. 0 is mechanical replay, 1 a forward test on paper (Alpaca's paper account, the Kalshi
shadow book), 2 real money at $1 to $10 a position, 3 real money sized at a quarter of Kelly on
the lower bound. Every threshold is in `league/constitution.py`, written before any agent traded.

What is measured is after-cost log growth of the agent's own account, in blocks (an hour or a
day, by the strategy's declared horizon): ln(equity at the block's end / equity at its start),
stakes added or withdrawn taken out. Equity is cash plus holdings at the bid, so fees, spread and
slippage are all inside the number.

- **Promotion** needs a lower confidence bound on mean block growth above zero. Looks are taken
  every few active blocks, and look k spends alpha * 6 / (pi^2 k^2), so an agent that is looked at
  a hundred times gets no more than alpha of false-pass chance in total. A record that wins
  nearly every trade (favourites) must ALSO clear a Wilson bound on its loss rate: a t-interval
  flatters that shape until the first loss arrives.
- **Death** is the mirror: an upper bound below zero, or a drawdown past the limit. (The economy
  adds the third way to die: compute credits at zero.)
- **Replay** counts every run as a trial. A family that tried two hundred variants must beat the
  Sharpe ratio two hundred unskilled tries would reach by luck (the deflated Sharpe ratio).

The evaluator only reads the ledger and writes `eval.*` rows. It never trades and never kills: the
House acts on the verdicts it returns.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from . import stats
from .constitution import CONSTITUTION
from .ledger import Ledger, now_iso


@dataclass(frozen=True)
class Verdict:
    agent: str
    rung: int
    decision: str  # hold | look | eligible | promote | demote | die
    reason: str
    numbers: dict[str, Any] = field(default_factory=dict)


def _per_exposure(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    """Block growth per unit of exposure, for comparing an agent with itself across rungs, where
    the same strategy may have a fifth or a third of its stake at work. Blocks with nothing at
    work say nothing about the edge and are left out. Rows that carry no exposure (older rows)
    are compared as they are."""
    if not rows or any(r.get("exposure") is None for r in rows):
        return [float(r["log_growth"]) for r in rows]
    return [float(r["log_growth"]) / float(r["exposure"]) for r in rows if float(r["exposure"]) >= 0.02]


def block_key(at: str, horizon: str) -> str:
    """`2026-09-20T13` for an hour block, `2026-09-20` for a day block."""
    return at[:13] if horizon == "hour" else at[:10]


class Evaluator:
    def __init__(self, ledger: Ledger, *, constitution: Mapping[str, Any] | None = None, clock=time.time):
        self.ledger = ledger
        self.c = dict(constitution or CONSTITUTION)
        self.ladder = self.c["ladder"]
        self.clock = clock

    # ------------------------------------------------------------------ state
    def rung(self, agent: str) -> int:
        for entry in reversed(self.ledger.read(kinds="eval.verdict", agent=agent, limit=10_000, newest=True)):
            if entry.payload.get("decision") in ("promote", "demote", "seat"):
                return int(entry.payload["to_rung"])
        return 0

    def _rung_entered(self, agent: str) -> int:
        """The ledger sequence number at which the agent entered its current rung."""
        for entry in reversed(self.ledger.read(kinds="eval.verdict", agent=agent, limit=10_000, newest=True)):
            if entry.payload.get("decision") in ("promote", "demote", "seat"):
                return entry.seq
        return 0

    def seat(self, agent: str, rung: int, reason: str) -> None:
        """Place an agent on a rung without a test (used once, for nothing above rung 0, and by
        tests). Promotions go through `promote`."""
        self.ledger.append(
            "eval.verdict",
            {"decision": "seat", "from_rung": self.rung(agent), "to_rung": int(rung), "reason": reason},
            agent=agent,
        )

    # ------------------------------------------------------------------ rung 0
    def family_trials(self, family: str) -> list[float | None]:
        """One entry for every replay ever run for this family, passed, failed or crashed: its
        Sharpe ratio, or None when it had none. A failed replay is still a try, so it still raises
        the bar; only the defined Sharpes feed the variance."""
        return [
            (float(entry.payload["sharpe"]) if entry.payload.get("sharpe") is not None else None)
            for entry in self.ledger.iter(kinds="eval.trial")
            if entry.payload.get("family") == family
        ]

    def record_trial(self, agent: str, family: str, result: Mapping[str, Any], *, tape_id: str = "", promote: bool = True) -> Verdict:
        """Score one replay. It is recorded as a trial whatever it shows, and it is judged against
        every trial the family has run, this one included."""
        rules = self.ladder["replay"]
        growth = [float(b["log_growth"]) for b in result.get("blocks") or []]
        sharpe = stats.sharpe(growth) if result.get("ok") else None
        trials = self.family_trials(family) + [sharpe]
        defined = [t for t in trials if t is not None]
        deflated = stats.deflated_sharpe(growth, defined, n_trials=len(trials)) if sharpe is not None else None
        oos = result.get("out_of_sample") or {}
        reasons = []
        if not result.get("ok"):
            reasons.append(f"the replay failed: {result.get('error')}")
        if int(result.get("trades") or 0) < rules["min_trades"]:
            reasons.append(f"{int(result.get('trades') or 0)} closed trades, {rules['min_trades']} needed")
        if len(growth) < rules["min_blocks"]:
            reasons.append(f"{len(growth)} blocks, {rules['min_blocks']} needed")
        if int(oos.get("blocks") or 0) < rules["min_oos_blocks"] or float(oos.get("mean_log_growth") or 0.0) <= 0:
            reasons.append("out-of-sample growth is not above zero")
        if deflated is None or deflated["dsr"] < rules["min_deflated_sharpe"]:
            shown = "undefined" if deflated is None else f"{deflated['dsr']:.3f}"
            reasons.append(f"deflated Sharpe {shown} against {len(trials)} trials, {rules['min_deflated_sharpe']} needed")
        passed = not reasons
        numbers = {
            "family": family,
            "tape": tape_id,
            "code_sha256": result.get("code_sha256"),
            "params": result.get("params"),
            "blocks": len(growth),
            "trades": int(result.get("trades") or 0),
            "sharpe": sharpe,
            "trials": len(trials),
            "deflated_sharpe": None if deflated is None else deflated["dsr"],
            "benchmark_sharpe": None if deflated is None else deflated["benchmark"],
            "return_pct": result.get("return_pct"),
            "max_drawdown": result.get("max_drawdown"),
            "oos_mean_log_growth": oos.get("mean_log_growth"),
            "fees_usd": result.get("fees_usd"),
            "passed": passed,
            "reasons": reasons,
        }
        self.ledger.append("eval.trial", numbers, agent=agent)
        if passed and promote and self.rung(agent) == 0:
            return self.promote(agent, 1, "passed replay against every trial its family has run", numbers)
        return Verdict(agent, self.rung(agent), "hold", "; ".join(reasons) or "passed replay; no promotion was asked for or due", numbers)

    # ------------------------------------------------------------ rungs 1 to 3
    def observe(self, agent: str, book: str, horizon: str) -> int:
        """Turn the agent's equity marks on a book into finished blocks of log growth. A block is
        finished when a mark exists in a later block. Returns how many blocks were added."""
        # Only what has happened since the last finished block is read: the marks of a week are
        # thousands of rows an agent, and this runs for every agent every few minutes.
        done = [e.payload for e in self.ledger.iter(kinds="eval.block", agent=agent) if e.payload.get("book") == book and e.payload.get("last_mark_seq")]
        resume = done[-1] if done else None
        since = int(resume["last_mark_seq"]) if resume else 0
        marks = [e for e in self.ledger.iter(kinds="book.mark", agent=agent, after=since) if e.payload.get("book") == book]
        if not marks:
            return 0
        stakes = [e for e in self.ledger.iter(kinds="book.stake", agent=agent, after=0 if resume is None else since) if e.payload.get("book") == book]
        fills = [
            e for e in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent, after=since) if e.payload.get("book") == book
        ]
        by_block: dict[str, list] = {}
        for entry in marks:
            by_block.setdefault(block_key(entry.at, horizon), []).append(entry)
        keys = sorted(by_block)
        added = 0
        previous_equity: float | None = float(resume["end_equity"]) if resume else None
        previous_seq = since
        recorded = {e.payload.get("key") for e in self.ledger.iter(kinds="eval.block", agent=agent) if e.payload.get("book") == book}
        for index, key in enumerate(keys):
            last = by_block[key][-1]
            end_equity = float(last.payload["equity"])
            finished = index < len(keys) - 1
            if previous_equity is None:
                # The first block starts from what was staked before its first mark.
                first = by_block[key][0]
                start_equity = sum(float(s.payload["usd"]) for s in stakes if s.seq < first.seq)
                flow = sum(float(s.payload["usd"]) for s in stakes if first.seq < s.seq <= last.seq)
            else:
                start_equity = previous_equity
                flow = sum(float(s.payload["usd"]) for s in stakes if previous_seq < s.seq <= last.seq)
            if finished and start_equity > 0 and key not in recorded:
                active = any(int(m.payload.get("holdings") or 0) > 0 for m in by_block[key]) or any(
                    block_key(f.at, horizon) == key for f in fills
                )
                growth = stats.log_growth(start_equity, end_equity, flow)
                # How much of the account was at work, on average over the block's marks. Growth per
                # unit of exposure is what an edge is; growth per block also depends on how big the
                # positions were against the stake, which changes from rung to rung.
                shares = [
                    max(1.0 - float(m.payload.get("cash") or 0) / float(m.payload["equity"]), 0.0)
                    for m in by_block[key] if float(m.payload.get("equity") or 0) > 0
                ]
                exposure = sum(shares) / len(shares) if shares else 0.0
                # A block belongs to the rung the agent was on when the block HAPPENED, so it
                # carries the ledger position of its first mark; when the row was written says
                # nothing (a paper backlog may be written long after a demotion).
                self.ledger.append(
                    "eval.block",
                    {
                        "book": book,
                        "key": key,
                        "horizon": horizon,
                        "start_equity": round(start_equity, 8),
                        "end_equity": round(end_equity, 8),
                        "flow": round(flow, 8),
                        "log_growth": growth,
                        "active": bool(active),
                        "exposure": round(exposure, 6),
                        "first_mark_seq": by_block[key][0].seq,
                        "last_mark_seq": last.seq,
                    },
                    agent=agent,
                    id=f"block:{agent}:{book}:{key}",
                )
                added += 1
            previous_equity, previous_seq = end_equity, last.seq
        return added

    def blocks(self, agent: str, *, since_seq: int = 0, until_seq: int | None = None, book: str | None = None) -> list[dict[str, Any]]:
        """Finished blocks that BEGAN after `since_seq` (and at or before `until_seq`)."""
        out = []
        for e in self.ledger.iter(kinds="eval.block", agent=agent):
            began = int(e.payload.get("first_mark_seq") or e.seq)
            if began > since_seq and (until_seq is None or began <= until_seq) and (book is None or e.payload.get("book") == book):
                out.append(e.payload)
        return out

    def trade_returns(self, agent: str, book: str, *, since_seq: int = 0) -> tuple[list[float], float]:
        """Closed trades as a fraction of the stake, and the average fraction put at risk."""
        staked = sum(float(e.payload["usd"]) for e in self.ledger.iter(kinds="book.stake", agent=agent) if e.payload.get("book") == book)
        if staked <= 0:
            return [], 0.0
        returns, risked = [], []
        running: dict[str, float] = {}  # a position sold in ten fills is one trade, closed when it is flat
        for entry in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent):
            p = entry.payload
            if entry.seq <= since_seq or p.get("book") != book:
                continue
            key = str((p.get("instrument") or {}).get("market_id") or (p.get("instrument") or {}).get("symbol")) + ":" + str((p.get("instrument") or {}).get("right"))
            if entry.kind == "book.settle":
                returns.append((running.pop(key, 0.0) + float(p["pnl"])) / staked)
            elif p.get("realized") is not None and p.get("source") != "dust":
                running[key] = running.get(key, 0.0) + float(p["realized"])
                if p.get("flat", True):
                    returns.append(running.pop(key) / staked)
            elif p.get("side") == "buy" and p.get("source") in ("venue", "cross"):
                risked.append(-float(p["cash_delta"]) / staked)
        # With no entry seen since the rung began (contracts carried in), assume all of it was at risk.
        return returns, (sum(risked) / len(risked) if risked else 1.0)

    def judge(self, agent: str, book: str) -> Verdict:
        """Look at an agent on the book of its current rung and say what the rules say."""
        rung = self.rung(agent)
        if rung == 0:
            return Verdict(agent, 0, "hold", "rung 0 is judged by replay")
        entered = self._rung_entered(agent)
        rows = self.blocks(agent, since_seq=entered, book=book)
        growth = [float(r["log_growth"]) for r in rows]
        active = sum(1 for r in rows if r.get("active"))
        death = self.ladder["death"]
        wealth, level = [1.0], 0.0
        for value in growth:  # the wealth index of the blocks themselves: stakes lent or returned are not losses
            level += value
            wealth.append(math.exp(max(level, -700.0)))
        drawdown = stats.max_drawdown(wealth)
        numbers: dict[str, Any] = {"book": book, "blocks": len(rows), "active_blocks": active, "drawdown": drawdown}
        if drawdown >= death["max_drawdown"]:
            return self._decide(agent, rung, "die", f"drawdown of {drawdown:.0%} is past the {death['max_drawdown']:.0%} limit", numbers)
        looks = [
            e for e in self.ledger.iter(kinds="eval.verdict", agent=agent)
            if e.seq > entered and e.payload.get("decision") == "look"
        ]
        every = int(self.ladder["look_every_active_blocks"])
        needed = min(death["min_active_blocks"], self._promotion_blocks(rung))
        last_look_active = int(looks[-1].payload.get("active_blocks") or 0) if looks else 0
        if active < needed or active - last_look_active < every and looks:
            return Verdict(agent, rung, "hold", f"{active} active blocks; the next look is at {max(needed, last_look_active + every)}", numbers)
        k = len(looks) + 1
        alpha = stats.spend(float(self.ladder["alpha"]), k)
        bounds = stats.mean_bounds(growth, alpha)
        if bounds is None:
            return Verdict(agent, rung, "hold", "not enough blocks for a bound", numbers)
        returns, risk = self.trade_returns(agent, book, since_seq=entered)
        lopsided = stats.lopsided(returns, float(self.ladder["lopsided_win_rate"]))
        wilson = stats.lopsided_growth_lcb(returns, risk, alpha) if lopsided else None
        numbers.update(
            look=k, alpha_spent=alpha, mean=bounds["mean"], sd=bounds["sd"], lcb=bounds["lcb"], ucb=bounds["ucb"],
            trades=len(returns), lopsided=lopsided, wilson_lcb=wilson,
        )
        self.ledger.append("eval.verdict", {"decision": "look", "rung": rung, **numbers}, agent=agent)
        if active >= death["min_active_blocks"] and bounds["ucb"] < 0:
            return self._decide(agent, rung, "die", "the upper bound on its growth is below zero", numbers)
        if len(returns) < int(self.ladder["min_closed_trades"]):
            return Verdict(agent, rung, "hold", f"{len(returns)} closed trades; {self.ladder['min_closed_trades']} needed before any promotion", numbers)
        if bounds["sd"] <= 0:
            return Verdict(agent, rung, "hold", "its block growth has no variance yet: nothing to bound", numbers)
        if rung < 3 and active >= self._promotion_blocks(rung) and bounds["lcb"] > 0 and (wilson is None or wilson > 0):
            return Verdict(agent, rung, "eligible", "the lower bound on its growth is above zero", numbers)
        return Verdict(agent, rung, "hold", "the evidence does not decide yet", numbers)

    def _promotion_blocks(self, rung: int) -> int:
        return int(self.ladder["paper" if rung == 1 else "micro"]["min_active_blocks"])

    def _decide(self, agent: str, rung: int, decision: str, reason: str, numbers: Mapping[str, Any]) -> Verdict:
        self.ledger.append("eval.verdict", {"decision": decision, "rung": rung, "reason": reason, **numbers}, agent=agent)
        return Verdict(agent, rung, decision, reason, dict(numbers))

    def _record_below(self, agent: str, rung: int) -> list[dict[str, Any]]:
        """The blocks of the agent's most recent stay on the rung just below `rung`: the record
        that earned this rung, and nothing else (not older rungs, not a decayed stay above)."""
        changes = [e for e in self.ledger.iter(kinds="eval.verdict", agent=agent) if e.payload.get("decision") in ("promote", "demote", "seat")]
        start = end = None
        for index, entry in enumerate(changes):
            if int(entry.payload["to_rung"]) == rung - 1:
                start = entry.seq
                end = changes[index + 1].seq if index + 1 < len(changes) else None
        if start is None:
            return []
        rows = self.blocks(agent, since_seq=start, until_seq=end)
        # One book only: the book that stay was traded on (a wound-down account elsewhere may
        # still be marked, flat, inside the same window).
        books: dict[str, int] = {}
        for row in rows:
            books[row.get("book")] = books.get(row.get("book"), 0) + (1 if row.get("active") else 0)
        if not books:
            return []
        main = max(books, key=lambda b: books[b])
        return [row for row in rows if row.get("book") == main]

    def promote(self, agent: str, to_rung: int, reason: str, numbers: Mapping[str, Any] | None = None) -> Verdict:
        """Move an agent up one rung. The House calls this for rung 2 only after the audit passes."""
        rung = self.rung(agent)
        if to_rung != rung + 1:
            raise ValueError(f"{agent} is on rung {rung}; it cannot be promoted to {to_rung}")
        self.ledger.append(
            "eval.verdict",
            {"decision": "promote", "from_rung": rung, "to_rung": to_rung, "reason": reason, **dict(numbers or {})},
            agent=agent,
        )
        return Verdict(agent, to_rung, "promote", reason, dict(numbers or {}))

    def demote(self, agent: str, reason: str, numbers: Mapping[str, Any] | None = None) -> Verdict:
        rung = self.rung(agent)
        if rung <= 1:
            raise ValueError(f"{agent} is on rung {rung}; there is nothing below paper but replay")
        self.ledger.append(
            "eval.verdict",
            {"decision": "demote", "from_rung": rung, "to_rung": rung - 1, "reason": reason, **dict(numbers or {})},
            agent=agent,
        )
        return Verdict(agent, rung - 1, "demote", reason, dict(numbers or {}))

    # ------------------------------------------------------------------- drift
    def drift(self, agent: str, book: str) -> Verdict:
        """At rungs 2 and 3, compare recent growth with the record that earned the rung. A
        sustained fall (a one-sided CUSUM alarm) sends the agent down a rung: promotion is not tenure."""
        rung = self.rung(agent)
        if rung < 2:
            return Verdict(agent, rung, "hold", "drift is watched on real-money rungs only")
        entered = self._rung_entered(agent)
        earned = _per_exposure(self._record_below(agent, rung))
        recent = _per_exposure(self.blocks(agent, since_seq=entered, book=book))
        rules = self.ladder["drift"]
        recent = recent[-int(rules["window_blocks"]):]
        reference = stats.mean_bounds(earned, 0.5)
        if reference is None or not recent or reference["sd"] <= 0:
            return Verdict(agent, rung, "hold", "no reference record to drift from")
        result = stats.cusum_decay(recent, reference["mean"], reference["sd"], k=float(rules["k"]), h=float(rules["h"]))
        numbers = {"book": book, "reference_mean": reference["mean"], "reference_sd": reference["sd"], **result}
        self.ledger.append("eval.drift", {"rung": rung, **numbers}, agent=agent)
        if result["alarm"]:
            return self.demote(agent, "its growth has decayed from the record that earned this rung", numbers)
        return Verdict(agent, rung, "hold", "no decay", numbers)
