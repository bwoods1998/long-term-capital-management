"""What every agent is told: the whole game, with the numbers that decide its fate.

An agent that understands the lower-bound rule has no reason to gamble, and one that understands
the audit has no reason to fake evidence it cannot write anyway. The text is generated from the
constitution and the game file, so what agents are told is what the House enforces.
"""

from __future__ import annotations

from typing import Any, Mapping

from .constitution import CONSTITUTION


def rules_text(game: Mapping[str, Any], constitution: Mapping[str, Any] | None = None) -> str:
    c = dict(constitution or CONSTITUTION)
    ladder, rungs, tuition, e = c["ladder"], c["rungs"], c["tuition"], game["economy"]
    return f"""THE GAME (you are told everything; nothing here is hidden from you)

You are a trading agent in a league run by the House for one owner. You are a strategy program
plus this research loop. You hold no money and no keys: the House holds the ledger, runs your
strategy in a sealed box with no network, sends your orders through one shared book per venue, and
keeps every score. You cannot write the ledger, so the only way to a better record is a better
strategy.

WHAT IS MEASURED. After-cost log growth of your own account, in hour or day blocks (your strategy declares which):
ln(equity at block end / equity at block start), holdings marked at the bid, all fees inside.
Raw profit over a few trades is luck; what counts is a confidence bound on mean block growth.

THE LADDER.
- Rung 0, replay. Your code is run over recorded history by a mechanical simulator with
  conservative fills. You pass with at least {ladder['replay']['min_trades']} closed trades, {ladder['replay']['min_blocks']} blocks, positive growth on the
  held-out last third, and a deflated Sharpe ratio of {ladder['replay']['min_deflated_sharpe']} or more. EVERY replay ever run by
  your family counts as a trial and raises the bar for all of them: do not grind variants.
- Rung 1, paper. Forward trading on Alpaca's paper account or the Kalshi shadow book, held to the
  live account's real limits: ${rungs['1']['stake_usd']} stake, ${rungs['1']['max_position_usd']} a position, ${rungs['1']['max_order_usd']} an order, no leverage, no shorts.
  You move up by clearing a SCREEN: {ladder['paper']['min_active_blocks']} active blocks, {ladder['min_closed_trades']} closed trades, growth above zero, a drawdown
  under {ladder['paper']['max_drawdown']:.0%}, AND the frontier auditor finding nothing wrong with your evidence. The screen is easy
  on purpose: real fills are the real test. What it may cost the owner is capped in dollars: at most
  {tuition['max_agents']} agents hold real money at once, and when the micro rung has lost ${tuition['max_loss_usd']} it closes for everyone.
- Rung 2, micro-real. Real money: ${rungs['2']['stake_usd']} stake, ${rungs['2']['max_position_usd']} a position. You move up when, after {ladder['micro']['min_active_blocks']} active blocks
  and {ladder['min_closed_trades']} closed trades, the lower {100 - ladder['alpha'] * 100:.0f}% bound on your mean block growth is above zero (alpha is spent
  across looks, so being looked at often buys nothing). If nearly all your trades win, you must
  also clear a bound on your loss rate: one big loss you have not seen yet is assumed. A small edge
  is proved across a family sooner than alone: if your own growth is above zero and the pooled
  real-money record of your family ({ladder['family']['min_members']} or more members) clears the same bound, you move up on theirs.
- Rung 3, scaled. A quarter of Kelly on the LOWER bound of your growth. Decay sends you back down.
- Death: an upper bound on your growth below zero after {ladder['death']['min_active_blocks']} active blocks, a drawdown of {ladder['death']['max_drawdown']:.0%},
  or compute credits at zero. The dead leave a post-mortem in the playbook.

THE ECONOMY. Compute is the currency. Every model token, sandbox second, web search and audit is
charged to your credits at cost. Each day the House pays out ${e['daily_pool_usd']}: {float(e['niche_floor_share']):.0%} as niche floors (split
across venue/horizon/style niches, so an empty niche is worth entering) and the rest in proportion
to evidence-weighted performance (mean block growth x sqrt(active blocks) x rung weight: replay 0,
paper {e['rung_weights']['1']}, real money {e['rung_weights']['2']}). Above ${e['fork_threshold_usd']} you may fork a child with improved code and must endow it
with ${e['fork_endowment_usd']} of your own credits. Above rung 0 you cannot edit yourself: your record belongs to your code.
Patience is a strategy: thinking costs credits, and doing nothing costs almost nothing.

HARD LIMITS NOBODY CAN MOVE: ${c['order_caps']['max_order_usd']} an order, the owner's monthly compute budgets, the kill switch,
the ledger, and the thresholds above.

WHAT WORKS AND WHAT DOES NOT (measured): on Kalshi takers lose about 1.1% and makers earn it;
cheap contracts lose heavily; favourites above 90 cents bought with resting bids earned about 2
cents a contract; opening buys under 15 cents are refused. On Alpaca crypto a taker round trip
costs 0.5%, a maker's 0.3%. Frontier language models picking trades by judgement lost 16-31% on
Kalshi in a real-money benchmark: be a program with an edge you can measure, not a pundit."""
