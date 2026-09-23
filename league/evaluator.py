"""The ladder: who climbs, who stays, who dies, and the statistics that decide it.

Four rungs. 0 is mechanical replay, 1 a forward test on paper (Alpaca's paper account, the Kalshi
shadow book), 2 real money at the micro stake, 3 real money sized by Kelly on the lower bound
(full Kelly since the owner's swing-and-bunt revision of Sept 23, 2026). Every threshold is in
`league/constitution.py`; the owner's revisions to them are recorded there with their reasons.

What is measured is after-cost log growth of the agent's own account, in blocks (an hour or a
day, by the strategy's declared horizon): ln(equity at the block's end / equity at its start),
stakes added or withdrawn taken out. Equity is cash plus holdings at the bid, so fees, spread and
slippage are all inside the number.

- **Promotion** needs a lower confidence bound on mean block growth above zero. Looks are taken
  every few active blocks, and look k spends alpha * 6 / (pi^2 k^2), so an agent that is looked at
  a hundred times gets no more than alpha of false-pass chance in total. Promotion to scaled size
  spends `promotion_alpha`, death spends `alpha`. A record that wins
  nearly every trade (favourites) must ALSO clear an exact (Clopper-Pearson) bound on its loss
  rate: a t-interval flatters that shape until the first loss arrives.
- **Death** is the mirror: an upper bound below zero, or a drawdown past the limit. (The economy
  adds the third way to die: compute credits at zero.)
- **Replay** counts every run as a trial, against the candidate's own LINE -- itself, its parent,
  its parent's parent, never its cousins. A line that ground two hundred variants must beat the
  Sharpe ratio two hundred unskilled tries would reach by luck (the deflated Sharpe ratio).

The evaluator only reads the ledger and writes `eval.*` rows. It never trades and never kills: the
House acts on the verdicts it returns.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
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


#: Books whose trades end in a settlement (an event contract's outcome), paper and real.
EVENT_BOOKS = ("kalshi-shadow", "kalshi")


def block_key(at: str, horizon: str) -> str:
    """`2026-09-20T13` for an hour block, `2026-09-20` for a day block."""
    return at[:13] if horizon == "hour" else at[:10]


class Evaluator:
    def __init__(self, ledger: Ledger, *, constitution: Mapping[str, Any] | None = None, clock=time.time, archive=None):
        self.ledger = ledger
        self.c = dict(constitution or CONSTITUTION)
        self.ladder = self.c["ladder"]
        self.clock = clock
        self.archive = archive
        self._evaluation_policy = None

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

    def replay_gate(self, family: str, result: Mapping[str, Any], *, lineage: Sequence[str] | None = None,
                    counted: bool = False) -> tuple[bool, list[str]]:
        """The replay gate `record_trial` applies, without recording anything: whether this result
        would pass against its selection path, and why not. `counted=True` when the result is
        already one of the path's trials (a sealed-holdout replay of a version whose development
        trial was recorded is judged with that trial's deflation, not one more)."""
        return self._replay_reasons(family, result, lineage, counted=counted)[:2]

    def _replay_reasons(self, family: str, result: Mapping[str, Any], lineage: Sequence[str] | None, *,
                        counted: bool = False) -> tuple[bool, list[str], list[float], Any, Any, list[Any], Mapping[str, Any]]:
        rules = self.ladder["replay"]
        growth = [float(b["log_growth"]) for b in result.get("blocks") or []]
        sharpe = stats.sharpe(growth) if result.get("ok") else None
        trials = self.family_trials(family, lineage) + ([] if counted else [sharpe])
        defined = [t for t in trials if t is not None]
        deflated = stats.deflated_sharpe(growth, defined, n_trials=len(trials)) if sharpe is not None else None
        oos = result.get("out_of_sample") or {}
        reasons = []
        if not result.get("ok"):
            reasons.append(f"the replay failed: {result.get('error')}")
        if int(result.get("unresolved") or 0):
            reasons.append("positions lack a completed settlement within the recorded scoring window")
        if int(result.get("trades") or 0) < rules["min_trades"]:
            reasons.append(f"{int(result.get('trades') or 0)} closed trades, {rules['min_trades']} needed")
        if len(growth) < rules["min_blocks"]:
            reasons.append(f"{len(growth)} blocks, {rules['min_blocks']} needed")
        # A floor below zero (owner revision, Sept 23, 2026) lets a near-breakeven idea earn a paper
        # seat: forward fills judge it there, and `paper_death` takes the seat back from a loser.
        floor = float(rules.get("min_oos_growth", 0.0))
        if int(oos.get("blocks") or 0) < rules["min_oos_blocks"] or float(oos.get("mean_log_growth") or 0.0) <= floor:
            reasons.append("out-of-sample growth is not above zero" if floor == 0.0 else
                           f"out-of-sample growth is not above {floor:+.3%} a block")
        if deflated is None or deflated["dsr"] < rules["min_deflated_sharpe"]:
            shown = "undefined" if deflated is None else f"{deflated['dsr']:.3f}"
            reasons.append(f"deflated Sharpe {shown} against {len(trials)} trials, {rules['min_deflated_sharpe']} needed")
        return not reasons, reasons, growth, sharpe, deflated, trials, oos

    def record_trial(self, agent: str, family: str, result: Mapping[str, Any], *, tape_id: str = "", promote: bool = True,
                     lineage: Sequence[str] | None = None) -> Verdict:
        """Score one replay. It is recorded as a trial whatever it shows, and it is judged against
        every trial in its selection path (`family_trials`), this one included."""
        passed, reasons, growth, sharpe, deflated, trials, oos = self._replay_reasons(family, result, lineage)
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
        if result.get("experiment"):
            numbers["experiment"] = result["experiment"]
        if self.archive is not None:
            if self._evaluation_policy is None:
                from . import ledger as ledger_module

                self._evaluation_policy = self.archive.put({"constitution": self.c, "python": list(sys.version_info[:3]),
                    "sources": {"evaluator.py": Path(__file__).read_text(encoding="utf-8"),
                                "stats.py": Path(stats.__file__).read_text(encoding="utf-8"),
                                "ledger.py": Path(ledger_module.__file__).read_text(encoding="utf-8")}})
            numbers["evaluation_artifact"] = self.archive.put({"schema": 1, "policy": self._evaluation_policy,
                "prior_trial_sharpes": trials[:-1], "lineage": list(lineage) if lineage is not None else None,
                "result": self.archive.put(result), "verdict": numbers})
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
        from .accounting import evidence_cutoffs
        cutoff = evidence_cutoffs(self.ledger, agent).get(book, 0)
        done = [e.payload for e in self.ledger.iter(kinds="eval.block", agent=agent)
                if e.payload.get("book") == book and int(e.payload.get("first_mark_seq") or e.seq) > cutoff
                and e.payload.get("last_mark_seq")]
        resume = done[-1] if done else None
        since = int(resume["last_mark_seq"]) if resume else cutoff
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
                start_equity = (float(first.payload['equity']) if cutoff else
                                sum(float(s.payload["usd"]) for s in stakes if s.seq < first.seq))
                flow = sum(float(s.payload["usd"]) for s in stakes if first.seq < s.seq <= last.seq)
            else:
                start_equity = previous_equity
                flow = sum(float(s.payload["usd"]) for s in stakes if previous_seq < s.seq <= last.seq)
            if start_equity <= 0 < flow:
                # The account was funded INSIDE this block: its marks read zero until the stake
                # landed. The block starts from the stake, not from nothing, and it counts. Measured
                # Sept 22, 2026: meriwether-32 was marked at $0 from 22:48, staked at 01:00, and its
                # whole first funded day was dropped from its paper record.
                start_equity, flow = flow, 0.0
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
        from .accounting import evidence_cutoffs
        cutoffs = evidence_cutoffs(self.ledger, agent)
        out = []
        for e in self.ledger.iter(kinds="eval.block", agent=agent):
            began = int(e.payload.get("first_mark_seq") or e.seq)
            if began > max(since_seq, cutoffs.get(e.payload.get('book'), 0)) and (until_seq is None or began <= until_seq) and (book is None or e.payload.get("book") == book):
                out.append(e.payload)
        return out

    def trade_returns(self, agent: str, book: str, *, since_seq: int = 0, until_seq: int | None = None) -> tuple[list[float], float]:
        """Closed trades as a fraction of the stake, and the average fraction put at risk.

        With `until_seq` the record is a finished stay, whose account may since have been swept:
        the stake is then the most the agent was ever lent up to that point, not what is left."""
        from .accounting import evidence_cutoffs
        since_seq = max(since_seq, evidence_cutoffs(self.ledger, agent).get(book, 0))
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
        # The screen asks a different question from death. Death asks what this agent has ever
        # done, over its whole stay, and a high-water mark is exactly right for that. The screen
        # asks whether it is fit to trade real money NOW -- and a lifetime high-water mark never
        # falls, so one bad afternoon early on would have made promotion unreachable for the rest
        # of the stay, whatever it did afterwards. An agent that drew down between the screen's
        # limit and death's could then be neither promoted nor killed, for ever. So the screen
        # reads the recent window, where "recent" is the window the gate itself asks for.
        recent = stats.max_drawdown(wealth[-(int(self.ladder.get("screen_drawdown_blocks", 30)) + 1):])
        numbers: dict[str, Any] = {"book": book, "blocks": len(rows), "active_blocks": active,
                                   "drawdown": drawdown, "recent_drawdown": recent}
        if drawdown >= death["max_drawdown"]:
            return self._decide(agent, rung, "die", f"drawdown of {drawdown:.0%} is past the {death['max_drawdown']:.0%} limit", numbers)
        paper_death = self.ladder.get("paper_death")
        if rung == 1 and paper_death and active >= int(paper_death["min_active_blocks"]):
            # A paper seat is the scarcest free thing the league has: a clear loser gives it up.
            change = math.exp(max(sum(growth), -700.0)) - 1.0
            if change <= -float(paper_death["max_loss"]):
                return self._decide(agent, rung, "die", f"down {-change:.1%} on paper after {active} active blocks; "
                                    f"paper keeps no agent down {float(paper_death['max_loss']):.0%}", numbers)
            if active >= int(paper_death["unprofitable_blocks"]) and change <= 0:
                return self._decide(agent, rung, "die", f"not profitable on paper after {active} active blocks "
                                    f"({change:+.1%}); {int(paper_death['unprofitable_blocks'])} is the chance a paper seat gives", numbers)
        fast = self._completed_exposure_gate(agent, book, rung, entered, numbers)
        if fast is not None:
            numbers['completed_exposure_evidence'] = fast.numbers
            if fast.decision in ('eligible', 'die'):
                return fast
        from .accounting import evidence_cutoffs
        cutoff = evidence_cutoffs(self.ledger, agent).get(book, 0)
        look_entries = [
            e for e in self.ledger.iter(kinds="eval.verdict", agent=agent)
            if e.seq > entered and e.payload.get("decision") == "look"
        ]
        looks = [e.payload for e in look_entries]
        gate = self._gate(rung)
        blocks_needed = self._gate_blocks(rung, horizon)
        settled = self._settled_lane(agent, book, rung, horizon, max(entered, cutoff))
        if settled is not None:
            numbers["settled_trades"] = settled["settled"]
            if settled["open"]:
                blocks_needed = min(blocks_needed, settled["blocks"])
        every = int(self.ladder["look_every_active_blocks"])
        needed = min([death["min_active_blocks"]] + ([blocks_needed] if gate else []))
        # Rationed by the looks that SPENT something, not by every look taken: a screen-only look
        # costs no alpha, so letting it start the clock would push the death test out of reach.
        spent_looks = [e.payload for e in look_entries if e.seq > cutoff
                       and (e.payload.get("tested_death", True) or e.payload.get("tested_promotion", True))]
        last_look_active = int(spent_looks[-1].get("active_blocks") or 0) if spent_looks else 0
        # Looking often is rationed because each look that runs a STATISTICAL test spends alpha,
        # and an agent looked at often enough would pass one by luck. A screen runs no such test --
        # it counts blocks and trades and reads two numbers -- so it spends nothing, and rationing
        # it only makes an agent wait. hilibrand-2 cleared everything but cumulative growth at its
        # first look on Sept 20, 2026, was 0.35% of one block away, and would not have been looked
        # at again for five hours. A free check is not rationed.
        statistical_due = not spent_looks or active - last_look_active >= every
        screening = bool(gate) and gate.get("gate", "bound") == "screen"
        screen_due = screening and active >= blocks_needed
        if active < needed or (not statistical_due and not screen_due):
            # A screen looks as soon as it has its blocks; only a statistical look waits for the
            # cadence. Until Sept 23, 2026 this said "the next look is at 5" to every paper agent,
            # and the screen looked at 2 (daily) or 4 (hourly): agents planned against the wrong day.
            when = blocks_needed if screening else max(needed, last_look_active + every)
            hint = ""
            if settled is not None and not settled["open"]:
                hint = (f" (or {settled['blocks']} once {settled['needed']} trades have settled on this rung; "
                        f"{settled['settled']} so far)")
            return Verdict(agent, rung, "hold", f"{active} active blocks; the next look is at {when}{hint}", numbers)
        alpha = float(self.ladder["alpha"])
        # Promotion to scaled size spends its own budget (`promotion_alpha`, the owner's swing-and-bunt
        # revision of Sept 23, 2026); death spends `alpha`. They are errors in opposite directions.
        alpha_up = float(self.ladder.get("promotion_alpha", alpha))
        # Once death tests begin, their cadence must still not delay the free paper screen.
        # A check between paid looks reads the screen without spending either test's alpha.
        tests_death = statistical_due and active >= death["min_active_blocks"]
        tests_bound = statistical_due and bool(gate) and gate.get("gate", "bound") == "bound" and active >= blocks_needed
        # A row written before the tests were told apart tested both whenever it looked.
        k_death = 1 + sum(1 for row in looks if row.get("tested_death", True))
        k_promote = 1 + sum(1 for row in looks if row.get("tested_promotion", True))
        episode_share = float(self.ladder.get('completed_exposures', {}).get('promotion_alpha_share', 0))
        share = episode_share if rung == 2 else 0
        alpha_death, alpha_promote = stats.spend(alpha * (1 - episode_share), k_death), stats.spend(alpha_up * (1 - share), k_promote)
        lower, upper = stats.mean_bounds(growth, alpha_promote), stats.mean_bounds(growth, alpha_death)
        if lower is None or upper is None:
            if not (screen_due and growth and not tests_death and not tests_bound):
                return Verdict(agent, rung, "hold", "not enough blocks for a bound", numbers)
            # A screen reads growth and drawdown, not a bound: one settled day has no variance to
            # bound, and it needs none (the settled lane of the Sept 23, 2026 revision).
            mean = sum(growth) / len(growth)
            lower = {"mean": mean, "sd": None, "lcb": None}
            upper = {"mean": mean, "sd": None, "ucb": None}
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
            window = int(self.ladder.get("screen_drawdown_blocks", 30))
            # The block in progress counts too, settlements and sales included. Measured Sept 22,
            # 2026: hawkins passed on finished days (+1.4%) while six settlements that morning had
            # lost $15.50, and the auditor, not the screen, had to say the snapshot was stale.
            pending = self._unfinished_growth(agent, book, max(entered, cutoff))
            numbers["unfinished_log_growth"] = pending
            level_now = level + pending
            recent_now = stats.max_drawdown((wealth + [math.exp(max(level_now, -700.0))])[-(window + 1):]) if pending < 0 else recent
            if level > 0 and level_now > 0 and recent_now < limit:
                return Verdict(agent, rung, "eligible", f"it cleared the screen: {active} active {horizon} blocks, {len(returns)} closed trades, "
                                                        f"growth above zero (the block in progress included) and a drawdown "
                                                        f"under {limit:.0%} over its last {window} blocks", numbers)
            if level <= 0:
                why = "its growth is not above zero"
            elif level_now <= 0:
                why = "its growth is not above zero once the block in progress is counted"
            else:
                why = f"its drawdown of {recent_now:.0%} over its last {window} blocks is not under {limit:.0%}"
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

    def _completed_exposure_gate(self, agent, book, rung, entered, block_numbers):
        rules = self.ladder.get('completed_exposures')
        if not rules or rung not in (1, 2, 3):
            return None
        from .episodes import completed
        rows = completed(self.ledger, agent, book, since_seq=entered)
        if not rows:
            return Verdict(agent, rung, 'hold', 'more completed portfolio exposures are needed',
                           {'episodes': len(rows), 'required_episodes': rules['min_episodes']})
        growth = [r['log_growth'] for r in rows]
        level, wealth = 0.0, [1.0]
        for value in growth:
            level += value
            wealth.append(math.exp(max(min(level, 700), -700)))
        drawdown = stats.max_drawdown(wealth)
        numbers = {'book': book, 'via': 'completed_exposures', 'episodes': len(rows),
                   'trades': sum(r['trades'] for r in rows), 'active_blocks': block_numbers['active_blocks'],
                   'drawdown': drawdown, 'mean': sum(growth) / len(growth),
                   'first_seq': rows[0]['first_seq'], 'last_seq': rows[-1]['last_seq'],
                   'tested_promotion': rung == 2, 'tested_death': False}
        if drawdown >= self.ladder['death']['max_drawdown']:
            return self._decide(agent, rung, 'die', 'completed exposures breached the drawdown limit', numbers)
        if len(rows) < int(rules['min_episodes']) or numbers['trades'] < int(self.ladder['min_closed_trades']):
            return Verdict(agent, rung, 'hold', 'more completed exposures and closed trades are needed', numbers)
        from .accounting import evidence_cutoffs
        cutoff = evidence_cutoffs(self.ledger, agent).get(book, 0)
        look_entries = [e for e in self.ledger.iter(kinds='eval.verdict', agent=agent, after=entered)
                        if e.payload.get('decision') == 'episode-look']
        looks = [e.payload for e in look_entries]
        fresh_looks = [e.payload for e in look_entries if e.seq > cutoff]
        # Evidence counters restart after a repair; statistical error allowances do not.
        due = not fresh_looks or len(rows) - int(fresh_looks[-1]['episodes']) >= int(rules['look_every_episodes'])
        promotion_budget = self._episode_allowance(agent, entered, 'promotion')
        death_budget = self._episode_allowance(agent, entered, 'death')
        alpha = stats.spend(promotion_budget, len(looks) + 1) if promotion_budget > 0 else None
        alpha_death = stats.spend(death_budget, len(looks) + 1) if death_budget > 0 else None
        bounds = stats.mean_bounds(growth, alpha) if alpha else None
        death_bounds = stats.mean_bounds(growth, alpha_death) if alpha_death else None
        if due:
            numbers.update(alpha_death=alpha_death, tested_death=bool(alpha_death),
                           ucb=death_bounds['ucb'] if death_bounds else None)
        # Promote only from a fully marked, flat portfolio on this fast route. Otherwise a
        # sequence of realized winners could conceal an open loser between hourly blocks.
        clean_since = max(entered, cutoff)
        marks = [e for e in self.ledger.iter(kinds='book.mark', agent=agent, after=clean_since)
                 if e.payload.get('book') == book]
        events = [e for e in self.ledger.iter(kinds=('book.fill', 'book.settle', 'book.stake'), agent=agent, after=entered)
                  if e.payload.get('book') == book]
        mark = marks[-1] if marks else None
        marked_flat = bool(mark and mark.seq >= max((e.seq for e in events), default=rows[-1]['last_seq'])
                           and mark.payload.get('holdings') == 0)
        equity, staked = (float(mark.payload.get(k, 'nan')) for k in ('equity', 'staked')) if mark else (math.nan, math.nan)
        positive = marked_flat and math.isfinite(equity) and math.isfinite(staked) and equity > staked
        numbers['fresh_flat_profitable_mark'] = bool(positive)
        if rung == 1:
            limit = float(self.ladder['paper']['max_drawdown'])
            recent = stats.max_drawdown(wealth[-(int(self.ladder.get('screen_drawdown_blocks', 30)) + 1):])
            numbers.update(recent_drawdown=max(recent, block_numbers['recent_drawdown']), alpha_spent=None)
            if due:
                self.ledger.append('eval.verdict', {'decision': 'episode-look', 'rung': rung, **numbers}, agent=agent)
                if death_bounds and death_bounds['ucb'] < 0:
                    return self._decide(agent, rung, 'die', 'the completed-exposure growth upper bound is below zero', numbers)
            passed = positive and level > 0 and numbers['recent_drawdown'] < limit
            return Verdict(agent, rung, 'eligible' if passed else 'hold',
                'completed-exposure screen passed: closed trades, positive marked equity and bounded drawdown' if passed
                else 'completed exposures have not cleared positive-equity and drawdown checks', numbers)
        if not due:
            return Verdict(agent, rung, 'hold', 'no new completed-exposure look is due', numbers)
        returns = [r['return'] for r in rows]
        lopsided = stats.lopsided(returns, float(self.ladder['lopsided_win_rate']))
        risk = sum(r['risk_fraction'] for r in rows) / len(rows)
        loss_gate = stats.lopsided_growth_lcb(returns, risk, alpha) if lopsided and alpha else None
        numbers.update(alpha_spent=alpha if rung == 2 else None, look=len(looks)+1, lopsided=lopsided, loss_gate_lcb=loss_gate,
                       lcb=bounds['lcb'] if bounds else None, sd=bounds['sd'] if bounds else None)
        self.ledger.append('eval.verdict', {'decision': 'episode-look', 'rung': rung, **numbers}, agent=agent)
        if death_bounds and death_bounds['ucb'] < 0:
            return self._decide(agent, rung, 'die', 'the completed-exposure growth upper bound is below zero', numbers)
        if rung == 3:
            return Verdict(agent, rung, 'hold', 'the scaled record remains under observation', numbers)
        passed = bool(positive and bounds and bounds['sd'] > 0 and bounds['lcb'] > 0 and (loss_gate is None or loss_gate > 0))
        return Verdict(agent, rung, 'eligible' if passed else 'hold',
            'the completed-exposure growth bound is above zero' if passed else 'completed-exposure confidence does not establish positive growth', numbers)

    def _episode_allowance(self, agent, entered, test):
        """Legacy full-alpha block looks remain spent when adding a second evidence route."""
        alpha = float(self.ladder['alpha'])
        if test == 'promotion':
            alpha = float(self.ladder.get('promotion_alpha', alpha))
        share = float(self.ladder['completed_exposures']['promotion_alpha_share'])
        excess, k = 0.0, 0
        field = 'alpha_spent' if test == 'promotion' else 'alpha_death'
        for entry in self.ledger.iter(kinds='eval.verdict', agent=agent, after=entered):
            row = entry.payload
            if row.get('decision') != 'look' or not row.get('tested_' + test, True):
                continue
            k += 1
            spent = row.get(field)
            if spent is None and 'tested_' + test not in row:
                spent = row.get('alpha_spent', stats.spend(alpha, k))
            excess += max(0.0, float(spent or 0) - stats.spend(alpha * (1 - share), k))
        return max(0.0, alpha * share - excess)

    def _settled_lane(self, agent: str, book: str, rung: int, horizon: str, since_seq: int) -> dict[str, Any] | None:
        """The paper screen's settled lane (owner revision, Sept 23, 2026): a daily agent on an
        event-contract book is judged by OUTCOMES, and once `settled_day.min_settled_trades` of its
        trades have settled on this rung it may be screened after `settled_day.min_active_blocks`
        finished day(s) instead of `min_active_blocks_day`. A settlement is the market's verdict,
        not a mark; a daily agent otherwise waits two calendar days for evidence it already has.
        None where the lane does not apply (another rung, an hourly agent, a book that does not
        settle, or a constitution without the lane)."""
        rule = (self._gate(rung) or {}).get("settled_day") if rung == 1 and horizon == "day" else None
        if not isinstance(rule, Mapping) or book not in EVENT_BOOKS:
            return None
        settled = sum(1 for e in self.ledger.iter(kinds="book.settle", agent=agent, after=since_seq)
                      if e.payload.get("book") == book)
        needed = int(rule["min_settled_trades"])
        return {"blocks": int(rule["min_active_blocks"]), "needed": needed, "settled": settled, "open": settled >= needed}

    def _unfinished_growth(self, agent: str, book: str, since_seq: int) -> float:
        """The growth of the block in progress so far: the latest mark on this book against the
        equity the last finished block ended on, stakes in between taken out -- exactly what the
        block would read if it closed now, settlements and sales included. 0.0 with no finished
        block or no mark since."""
        last = None
        for entry in self.ledger.iter(kinds="eval.block", agent=agent):
            p = entry.payload
            if p.get("book") == book and int(p.get("first_mark_seq") or entry.seq) > since_seq:
                last = (entry, p)
        if last is None:
            return 0.0
        entry, block = last
        boundary = int(block.get("last_mark_seq") or entry.seq)
        end = float(block.get("end_equity") or 0.0)
        marks = [e for e in self.ledger.iter(kinds="book.mark", agent=agent, after=boundary) if e.payload.get("book") == book]
        if end <= 0 or not marks:
            return 0.0
        flow = sum(float(e.payload["usd"]) for e in self.ledger.iter(kinds="book.stake", agent=agent, after=boundary)
                   if e.payload.get("book") == book and e.seq <= marks[-1].seq)
        return stats.log_growth(end, float(marks[-1].payload["equity"]), flow)

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
        fraction they put at risk; and how many members had enough blocks to qualify the family.

        Every member's outcomes count, including agents that died before qualifying. Requiring
        mature members must never erase early losses. Every stay is read through a fixed ledger
        position so that sweeping an account cannot erase or rescale its closed trades."""
        rules = self.ladder["family"]
        through, _ = self.ledger.head()
        by_block: dict[str, list[float]] = {}
        trades: list[float] = []
        risks: list[float] = []
        counted = 0
        for member in dict.fromkeys(members):
            changes = [e for e in self.ledger.iter(kinds="eval.verdict", agent=member)
                       if e.seq <= through and e.payload.get("decision") in ("promote", "demote", "seat")]
            rows: list[dict[str, Any]] = []
            for index, change in enumerate(changes):
                if int(change.payload["to_rung"]) < 2:
                    continue
                until = changes[index + 1].seq if index + 1 < len(changes) else through
                rows += self.blocks(member, since_seq=change.seq, until_seq=until, book=book)
                returns, risk = self.trade_returns(member, book, since_seq=change.seq, until_seq=until)
                trades += returns
                risks += [risk] * len(returns)
            if sum(1 for r in rows if r.get("active")) >= int(rules["min_member_active_blocks"]):
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
        """Move an agent up one rung. Under the constitution's `ladder.paper.audit` "after" (Sept 23,
        2026) the House calls this for rung 2 when the screen and the allocation gates pass, and the
        frontier audit follows on the micro rung; under "before", only once the audit passes."""
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
        from .accounting import evidence_cutoffs
        since_seq = max(since_seq, evidence_cutoffs(self.ledger, agent).get(book, 0))
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
        admission = next((e.payload for e in self.ledger.iter(kinds='eval.verdict', agent=agent)
                          if e.seq == entered and e.payload.get('via') == 'completed_exposures'), None)
        if admission:
            from .episodes import completed
            earned = completed(self.ledger, agent, admission['book'],
                               since_seq=int(admission['first_seq']) - 1, until_seq=entered)
            recent = completed(self.ledger, agent, book, since_seq=entered)[-int(rules['window_blocks']):]
            # Normalize the realized result by cash exposed so a larger earned stake alone
            # does not look like a changed strategy. Keep the qualifying record across rungs.
            reference = stats.mean_bounds([r['return'] / r['risk_fraction'] for r in earned
                                           if r['risk_fraction'] > 0], .5)
            values = [r['return'] / r['risk_fraction'] for r in recent if r['risk_fraction'] > 0]
            if len(earned) >= int(self.ladder['completed_exposures']['min_episodes']) and values and reference and reference['sd'] > 0:
                result = stats.cusum_decay(values, reference['mean'], reference['sd'],
                                          k=float(rules['k']), h=float(rules['h']))
                numbers = {'book': book, 'measure': 'completed exposure return per risk',
                           'reference_episodes': len(earned), 'recent_episodes': len(values), **result}
                self.ledger.append('eval.drift', {'rung': rung, **numbers}, agent=agent)
                if result['alarm']:
                    return self.demote(agent, 'completed-exposure performance decayed from the qualifying record', numbers)
                return Verdict(agent, rung, 'hold', 'no completed-exposure decay', numbers)
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
