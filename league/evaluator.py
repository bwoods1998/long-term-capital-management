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
  nearly every trade (favourites) must ALSO clear an exact (Clopper-Pearson) bound on its loss
  rate: a t-interval flatters that shape until the first loss arrives.
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
from .ledger import HOUSE, Ledger, now_iso


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

    def max_rung(self, agent: str) -> int:
        """The highest rung the agent has ever stood on."""
        return max((int(e.payload["to_rung"]) for e in self.ledger.iter(kinds="eval.verdict", agent=agent)
                    if e.payload.get("decision") in ("promote", "demote", "seat")), default=0)

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
    def family_trials(self, family: str, lineage: Sequence[str] | None = None) -> list[float | None]:
        """One entry for every replay in this candidate's SELECTION PATH, passed, failed or crashed:
        its Sharpe ratio, or None when it had none. A failed replay is still a try, so it still
        raises the bar; only the defined Sharpes feed the variance.

        The path is the agent's lineage: itself, its parent, its parent's parent. That is what a
        deflated Sharpe corrects for: picking the best of several tries at ONE idea. Six founders
        of one family testing six different rules once each are six hypotheses, not a selection,
        and deflating each by six is a correction for something that did not happen (measured
        Sept 19, 2026: the six sports founders burned their family's whole trial budget on their
        own first replays, and every agent then refused to experiment at all). Grinding variants
        down one lineage still raises that lineage's bar, and a child inherits its parent's count,
        so there is no way to spend the budget and start again.

        With no lineage the family is the path, which is what it was before and what tests use."""
        wanted = set(lineage) if lineage else None
        return [
            (float(entry.payload["sharpe"]) if entry.payload.get("sharpe") is not None else None)
            for entry in self.ledger.iter(kinds="eval.trial")
            if (entry.agent in wanted if wanted is not None else entry.payload.get("family") == family)
        ]

    def record_trial(self, agent: str, family: str, result: Mapping[str, Any], *, tape_id: str = "", promote: bool = True,
                     lineage: Sequence[str] | None = None) -> Verdict:
        """Score one replay. It is recorded as a trial whatever it shows, and it is judged against
        every trial in its selection path (`family_trials`), this one included."""
        rules = self.ladder["replay"]
        growth = [float(b["log_growth"]) for b in result.get("blocks") or []]
        sharpe = stats.sharpe(growth) if result.get("ok") else None
        trials = self.family_trials(family, lineage) + [sharpe]
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
            return self.promote(agent, 1, "passed replay against every trial in its own line", numbers)
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

    def trade_returns(self, agent: str, book: str, *, since_seq: int = 0, until_seq: int | None = None) -> tuple[list[float], float]:
        """Closed trades as a fraction of the stake, and the average fraction put at risk.

        With `until_seq` the record is a finished stay, whose account may since have been swept:
        the stake is then the most the agent was ever lent up to that point, not what is left."""
        stakes = [(e.seq, float(e.payload["usd"])) for e in self.ledger.iter(kinds="book.stake", agent=agent) if e.payload.get("book") == book]
        if until_seq is None:
            staked = sum(usd for _, usd in stakes)
        else:
            staked = running_stake = 0.0
            for seq, usd in stakes:
                if seq <= until_seq:
                    running_stake += usd
                    staked = max(staked, running_stake)
        if staked <= 0:
            return [], 0.0
        returns, risked = [], []
        running: dict[str, float] = {}  # a position sold in ten fills is one trade, closed when it is flat
        for entry in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent):
            p = entry.payload
            if entry.seq <= since_seq or p.get("book") != book or (until_seq is not None and entry.seq > until_seq):
                continue
            inst = p.get("instrument") or {}
            # One trade is one instrument gone flat: for an option that is the contract (its expiry
            # and strike), not every contract on the same underlying and side.
            key = ":".join(str(inst.get(k)) for k in ("market_id", "symbol", "right", "expiry", "strike") if inst.get(k) is not None)
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

    def judge(self, agent: str, book: str, *, peers: Sequence[str] = (), family: str = "", horizon: str = "hour") -> Verdict:
        """Look at an agent on the book of its current rung and say what the rules say.

        Two tests share the looks and nothing else. Death (an upper bound on growth below zero)
        and promotion (a lower bound above it) are errors in opposite directions, so each spends
        its own alpha across the looks where it was really tested: a look that could only kill
        spends none of promotion's. A rung whose gate is a `screen` promotes on plain conditions
        and spends no alpha at all; what it lets through is bounded in dollars by the House.

        `peers` are the other agents of this agent's `family`: on a `bound` rung an agent whose own
        record is positive but not yet decisive may pass on the family's pooled record."""
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
            e.payload for e in self.ledger.iter(kinds="eval.verdict", agent=agent)
            if e.seq > entered and e.payload.get("decision") == "look"
        ]
        gate = self._gate(rung)
        blocks_needed = self._gate_blocks(rung, horizon)
        every = int(self.ladder["look_every_active_blocks"])
        needed = min([death["min_active_blocks"]] + ([blocks_needed] if gate else []))
        last_look_active = int(looks[-1].get("active_blocks") or 0) if looks else 0
        if active < needed or active - last_look_active < every and looks:
            return Verdict(agent, rung, "hold", f"{active} active blocks; the next look is at {max(needed, last_look_active + every)}", numbers)
        alpha = float(self.ladder["alpha"])
        tests_death = active >= death["min_active_blocks"]
        tests_bound = bool(gate) and gate.get("gate", "bound") == "bound" and active >= blocks_needed
        # A row written before the tests were told apart tested both whenever it looked.
        k_death = 1 + sum(1 for row in looks if row.get("tested_death", True))
        k_promote = 1 + sum(1 for row in looks if row.get("tested_promotion", True))
        alpha_death, alpha_promote = stats.spend(alpha, k_death), stats.spend(alpha, k_promote)
        lower, upper = stats.mean_bounds(growth, alpha_promote), stats.mean_bounds(growth, alpha_death)
        if lower is None or upper is None:
            return Verdict(agent, rung, "hold", "not enough blocks for a bound", numbers)
        returns, risk = self.trade_returns(agent, book, since_seq=entered)
        lopsided = stats.lopsided(returns, float(self.ladder["lopsided_win_rate"]))
        loss_gate = stats.lopsided_growth_lcb(returns, risk, alpha_promote) if lopsided else None
        # `lcb` and `ucb` are always shown, at the alpha their test would spend at this look;
        # `alpha_spent` and `alpha_death` say which of the two tests this look really ran.
        numbers.update(
            look=len(looks) + 1, tested_death=tests_death, tested_promotion=tests_bound,
            alpha_spent=alpha_promote if tests_bound else None, alpha_death=alpha_death if tests_death else None,
            mean=lower["mean"], sd=lower["sd"], lcb=lower["lcb"], ucb=upper["ucb"],
            trades=len(returns), lopsided=lopsided, loss_gate_lcb=loss_gate,
        )
        self.ledger.append("eval.verdict", {"decision": "look", "rung": rung, **numbers}, agent=agent)
        if tests_death and upper["ucb"] < 0:
            return self._decide(agent, rung, "die", "the upper bound on its growth is below zero", numbers)
        if not gate or active < blocks_needed:
            return Verdict(agent, rung, "hold", "the evidence does not decide yet", numbers)
        if len(returns) < int(self.ladder["min_closed_trades"]):
            return Verdict(agent, rung, "hold", f"{len(returns)} closed trades; {self.ladder['min_closed_trades']} needed before any promotion", numbers)
        if gate.get("gate", "bound") == "screen":
            limit = float(gate["max_drawdown"])
            if level > 0 and drawdown < limit:
                return Verdict(agent, rung, "eligible", f"it cleared the screen: {active} active {horizon} blocks, {len(returns)} closed trades, growth above zero and a drawdown under {limit:.0%}", numbers)
            why = "its growth is not above zero" if level <= 0 else f"its drawdown of {drawdown:.0%} is not under {limit:.0%}"
            return Verdict(agent, rung, "hold", f"it has not cleared the screen: {why}", numbers)
        if lower["sd"] <= 0:
            return Verdict(agent, rung, "hold", "its block growth has no variance yet: nothing to bound", numbers)
        if lower["lcb"] > 0 and (loss_gate is None or loss_gate > 0):
            return Verdict(agent, rung, "eligible", "the lower bound on its growth is above zero", numbers)
        if lower["mean"] > 0 and peers:
            pooled = self._judge_family(agent, family, [agent, *peers], book, numbers, horizon)
            if pooled is not None:
                return pooled
        return Verdict(agent, rung, "hold", "the evidence does not decide yet", numbers)

    def _gate(self, rung: int) -> Mapping[str, Any] | None:
        """The promotion rule out of this rung, or None from the top."""
        return None if rung >= 3 else self.ladder["paper" if rung == 1 else "micro"]

    def _gate_blocks(self, rung: int, horizon: str = "hour") -> int:
        """The active blocks this rung's gate asks for, by the strategy's block length."""
        gate = self._gate(rung) or self._gate(2)
        key = "min_active_blocks_day" if horizon == "day" and "min_active_blocks_day" in gate else "min_active_blocks"
        return int(gate[key])

    def _promotion_blocks(self, rung: int, horizon: str = "hour") -> int:
        return self._gate_blocks(min(rung, 2), horizon)

    # ------------------------------------------------------------------ family
    def family_record(self, members: Sequence[str], book: str) -> tuple[list[float], list[float], float, int]:
        """The pooled real-money record of a family on one book: block by block, the mean growth
        of the members that were on a real-money rung in that block (one series, so members that
        trade the same hour are one observation, not several); their closed trades; the average
        fraction they put at risk; and how many members had enough blocks to count."""
        rules = self.ladder["family"]
        by_block: dict[str, list[float]] = {}
        trades: list[float] = []
        risks: list[float] = []
        counted = 0
        for member in dict.fromkeys(members):
            changes = [e for e in self.ledger.iter(kinds="eval.verdict", agent=member) if e.payload.get("decision") in ("promote", "demote", "seat")]
            rows: list[dict[str, Any]] = []
            for index, change in enumerate(changes):
                if int(change.payload["to_rung"]) < 2:
                    continue
                until = changes[index + 1].seq if index + 1 < len(changes) else None
                rows += self.blocks(member, since_seq=change.seq, until_seq=until, book=book)
                returns, risk = self.trade_returns(member, book, since_seq=change.seq, until_seq=until)
                trades += returns
                risks += [risk] * len(returns)
            if sum(1 for r in rows if r.get("active")) < int(rules["min_member_active_blocks"]):
                continue
            counted += 1
            for row in rows:
                by_block.setdefault(str(row["key"]), []).append(float(row["log_growth"]))
        series = [sum(values) / len(values) for _, values in sorted(by_block.items())]
        return series, trades, (sum(risks) / len(risks) if risks else 1.0), counted

    def _judge_family(self, agent: str, family: str, members: Sequence[str], book: str, own: Mapping[str, Any], horizon: str = "hour") -> Verdict | None:
        rules = self.ladder["family"]
        series, trades, risk, counted = self.family_record(members, book)
        if counted < int(rules["min_members"]) or len(series) < self._promotion_blocks(2, horizon):
            return None
        looks = [e.payload for e in self.ledger.iter(kinds="eval.verdict", agent=HOUSE)
                 if e.payload.get("decision") == "family-look" and e.payload.get("family") == family and e.payload.get("book") == book]
        if looks and len(series) - int(looks[-1].get("blocks") or 0) < int(self.ladder["look_every_active_blocks"]):
            return None
        alpha = stats.spend(float(rules["alpha"]), len(looks) + 1)
        bounds = stats.mean_bounds(series, alpha)
        if bounds is None or bounds["sd"] <= 0:
            return None
        lopsided = stats.lopsided(trades, float(self.ladder["lopsided_win_rate"]))
        loss_gate = stats.lopsided_growth_lcb(trades, risk, alpha) if lopsided else None
        pooled = {"family": family, "book": book, "look": len(looks) + 1, "alpha_spent": alpha, "members": counted, "blocks": len(series),
                  "mean": bounds["mean"], "sd": bounds["sd"], "lcb": bounds["lcb"], "trades": len(trades), "lopsided": lopsided, "loss_gate_lcb": loss_gate}
        self.ledger.append("eval.verdict", {"decision": "family-look", **pooled}, agent=HOUSE)
        if bounds["lcb"] > 0 and (loss_gate is None or loss_gate > 0):
            return Verdict(agent, 2, "eligible", f"its own growth is above zero and the lower bound on its family's pooled growth ({counted} members) is above zero",
                           {**own, "via": "family", "family_lcb": bounds["lcb"], "family_blocks": len(series), "family_members": counted})
        return None

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
    def trade_edges(self, agent: str, book: str, horizon: str, *, since_seq: int = 0, until_seq: int | None = None) -> list[list[float]]:
        """The edge of each closed trade (what it made over what the units sold had cost, fees
        in), grouped by the block it closed in. An edge does not depend on how large the position
        was against the stake, so it can be compared across rungs, where the same strategy has a
        fifth of its stake at work on paper and a third on the micro-real rung."""
        by_block: dict[str, list[float]] = {}
        for entry in self.ledger.iter(kinds=("book.fill", "book.settle"), agent=agent, after=since_seq):
            p = entry.payload
            if p.get("book") != book or (until_seq is not None and entry.seq > until_seq):
                continue
            if entry.kind == "book.settle":
                made, cost = float(p["pnl"]), float(p["cost"])
            elif p.get("realized") is not None and p.get("source") in ("venue", "cross"):
                made = float(p["realized"])
                cost = float(p["cash_delta"]) - made
            else:
                continue
            if cost > 0:
                by_block.setdefault(block_key(entry.at, horizon), []).append(made / cost)
        return [v for _, v in sorted(by_block.items())]

    def drift(self, agent: str, book: str, horizon: str = "hour") -> Verdict:
        """At rungs 2 and 3, compare the agent's recent edge per trade with the edge of the record
        that earned the rung. A sustained fall (a one-sided CUSUM alarm) sends the agent down a rung:
        promotion is not tenure. Real fills that are worse than the paper fills that earned rung 2
        are exactly such a fall, and are meant to be caught here."""
        rung = self.rung(agent)
        if rung < 2:
            return Verdict(agent, rung, "hold", "drift is watched on real-money rungs only")
        entered = self._rung_entered(agent)
        below = self._record_below(agent, rung)
        minimum = int(self.ladder["drift"].get("min_reference_blocks", 10))
        rules = self.ladder["drift"]
        if below and any(r.get("first_mark_seq") for r in below):
            start = min(int(r["first_mark_seq"]) for r in below if r.get("first_mark_seq"))
            earned_blocks = self.trade_edges(agent, str(below[0].get("book")), horizon, since_seq=max(start - 1, 0), until_seq=entered)
            recent_blocks = self.trade_edges(agent, book, horizon, since_seq=entered)[-int(rules["window_blocks"]):]
            trades = [edge for block in earned_blocks for edge in block]
            reference = stats.mean_bounds(trades, 0.5)
            if len(earned_blocks) >= minimum and recent_blocks and reference is not None and reference["sd"] > 0:
                # Each recent block is one observation: the mean edge of the trades it closed, in
                # units of its own standard error (a block that closed one trade is a noisier
                # reading than one that closed six, and is weighed as such).
                scores = [(sum(b) / len(b) - reference["mean"]) * (len(b) ** 0.5) / reference["sd"] for b in recent_blocks]
                result = stats.cusum_decay(scores, 0.0, 1.0, k=float(rules["k"]), h=float(rules["h"]))
                numbers = {"book": book, "measure": "edge per trade", "reference_mean": reference["mean"], "reference_sd": reference["sd"],
                           "reference_trades": len(trades), "recent_blocks": len(recent_blocks), **result}
                self.ledger.append("eval.drift", {"rung": rung, **numbers}, agent=agent)
                if result["alarm"]:
                    return self.demote(agent, "its edge per trade has decayed from the record that earned this rung", numbers)
                return Verdict(agent, rung, "hold", "no decay", numbers)
        # No trade-by-trade record to compare (older rows, or a stay too short): block growth per
        # unit of exposure is the fallback.
        earned = _per_exposure(below)
        recent = _per_exposure(self.blocks(agent, since_seq=entered, book=book))
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
