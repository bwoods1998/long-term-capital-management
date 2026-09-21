"""The House's current research contract, separate from fallible historical journals."""
from __future__ import annotations

from functools import lru_cache
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from .ledger import now_iso
from .parameters import inspect as inspect_parameters


def coverage_needs(agent, proposed, niche=None):
    """Validate bounded candidate data reads without importing or adopting strategy code."""
    from .agents import niche_of
    from .niches import constrain
    from .tapes import TIMEFRAME_SECONDS

    needs = deepcopy(agent.needs if proposed is None else proposed)
    if not isinstance(needs, dict) or len(json.dumps(needs)) > 16384:
        raise ValueError('coverage needs must be a bounded complete NEEDS object')
    venue, horizon, _ = niche_of(needs)
    if (venue, horizon) != (agent.venue, agent.horizon):
        raise ValueError('candidate coverage must keep the current venue and horizon')
    watched, bars = needs.get('observe', {}), needs.get('bars', {})
    if not isinstance(watched, dict) or not isinstance(bars, dict):
        raise ValueError('observe and bars must be objects')
    for source, maximum in ((needs, 12), (watched, 6)):
        for key in ('symbols', 'series'):
            values = source.get(key, [])
            if (not isinstance(values, list) or len(values) > maximum
                    or any(not isinstance(s, str) or not s.strip() or len(s) > 64 for s in values)):
                raise ValueError(f'{key} must be a list of at most {maximum} nonempty names')
    if bars:
        limit = bars.get('limit', 60 if venue == 'kalshi' else 120)
        if type(limit) is not int or not 1 <= limit <= (200 if venue == 'kalshi' else 500):
            raise ValueError('bars.limit exceeds the supported candidate coverage bounds')
        if bars.get('timeframe', '1Hour' if venue == 'kalshi' else '5Min') not in TIMEFRAME_SECONDS:
            raise ValueError('unsupported bars.timeframe')
    return constrain(needs, niche) if niche is not None else needs


@lru_cache(maxsize=1)
def revision():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ('capabilities.py', 'house.py', 'tapes.py', 'replay.py', 'parameters.py'):
        digest.update(name.encode() + b'\0' + (root / name).read_bytes())
    return digest.hexdigest()


def describe(agent, settings, niche, *, clock=time.time, alpaca=False, kalshi=False):
    replay = niche is None or niche.replay
    bars = agent.needs.get('bars') or {}
    days = (settings.kalshi_replay_days * (7 if agent.horizon == 'day' else 1)
            if agent.venue == 'kalshi' else settings.replay_days * (6 if agent.horizon == 'day' else 1))
    return {
        'as_of': now_iso(clock), 'revision': revision(),
        'parameters': {**inspect_parameters(agent.params, agent.needs),
            'note': 'Invalid configurations are refused for new births, adoption and replay. An empty rung-0 agent may repair invalid parameters through research with unchanged decision logic/NEEDS even after a failed replay; it stays on rung 0 and retains every trial. House mutations change one bounded numeric knob. Unknown knobs are frozen until NEEDS.parameter_rules declares their bounds. Structural validity is not evidence of an edge.'},
        'scope': {'agent': agent.id, 'venue': agent.venue, 'horizon': agent.horizon},
        'authority': 'Current House implementation and configuration. Older journals/library notes may describe earlier releases. Support does not establish data coverage or profitability.',
        'replay': {
            'mode': 'historical_development' if replay else 'smoke_only_no_historical_option_chains',
            'requested_window_days': days if replay else None,
            'window_ends': 'time the tape is first built; cached up to 24h; not a fixed August tape' if replay else None,
            'coverage': 'Actual dates, markets and samples depend on returned data. A requested window is not proof of coverage.',
            'signal_timeframe': str(bars.get('timeframe') or ('1Hour' if agent.venue == 'kalshi' else '5Min')),
            'alpaca_warmup': 'Implemented: pre-window bars from NEEDS.bars.limit, capped at 500; never future bars.',
            'daily_execution_clock': 'Implemented: Alpaca daily signals execute on 5Min bars. Equity daily bars become available at the next New York midnight; crypto daily bars at the next UTC midnight.',
            'settlement_clock': 'Implemented: Kalshi cash waits for reported settlement_ts. Unknown settlements remain unresolved and cannot qualify.',
            'selection': 'Reused history is development evidence. A smoke pass tests code execution only. Paper/forward risk and live-capital gates still apply.',
            'limitations': ['bar-based fills; no historical queue position or adverse-selection calibration',
                            'Kalshi historical selection is limited to returned settled markets',
                            'no historical option-chain replay'],
        },
        'observations': {
            'alpaca_source_configured': alpaca, 'kalshi_source_configured': kalshi,
            'cross_venue': 'Implemented: NEEDS.observe.symbols supplies Alpaca bars/quotes; NEEDS.observe.series supplies Kalshi markets in live views. No Kalshi event-series observation in Alpaca replay.',
            'kalshi_observed_bars': 'Implemented: replay uses NEEDS.bars timeframe and limit, with warmup. Missing bars or more than 4,000 bars per symbol is unsupported, never silently resampled.',
            'not_supplied': ['perpetual funding/open-interest feed', 'point-in-time earnings-surprise panel', 'live sports score feed'],
            'recording': 'Shared sampled REST snapshots with receive times; not tick/depth history. Experiment inputs/results are archived separately.',
        },
        'execution_feedback': 'Forward strategy snapshots and research standing include owned recent_order_outcomes, including House refusals before venue submission. Kalshi markets_now includes effective limits and event_risk remaining principal per market after shared holdings and working buys. A fresh current-book refusal pulls the next research pass forward, subject to earned credits and provider budget.',
        'research': 'Model turns spend credits even when no replay or search is purchased. A retained candidate is proposed until the House records adoption/forking. Use runtime_status to check changed capabilities. replay_coverage accepts complete proposed NEEDS and reports each missing observed symbol before any sandbox replay or selection trial. One missing symbol does not mean the whole feed is absent. Toolsmith advice is not implementation; blocked requests remain in the engineering backlog.',
    }


def tape_coverage(tape):
    """Summarize returned inputs, keeping execution events distinct from market observations."""
    steps = tape.get('steps') or []
    quoted = [s for s in steps if s.get('markets') or s.get('bars') or s.get('execution_bars')]
    markets, series = set(), {}
    for step in steps:
        for market in step.get('markets') or []:
            if not market.get('market'):
                continue
            markets.add(str(market['market']))
            row = series.setdefault(str(market.get('series') or '(unknown)'), {'markets': set(), 'times': []})
            row['markets'].add(str(market['market']))
            if step.get('t'):
                row['times'].append(str(step['t']))
    signals = {}
    for step in steps:
        for symbol, rows in (step.get('history_bars') or {}).items():
            for row in rows:
                signals.setdefault(symbol, []).append(row.get('t'))
        for symbol in step.get('bars') or {}:
            signals.setdefault(symbol, []).append(step.get('t'))

    def span(rows):
        times = sorted(str(r['t']) for r in rows if r.get('t'))
        return {'rows': len(rows), 'first_at': times[0] if times else None, 'last_at': times[-1] if times else None}

    return {
        'mode': 'historical_development', 'counted_as_trial': False,
        'venue': tape.get('venue'), 'horizon': tape.get('horizon'),
        'requested_series': tape.get('series') or [], 'requested_symbols': tape.get('symbols') or [],
        'listing_sample': {k: v for k, v in (tape.get('meta') or {}).items() if k in ('listed', 'scanned', 'kept')},
        'signal_timeframe': tape.get('timeframe'), 'execution_timeframe': tape.get('execution_timeframe'),
        'stock_feed': tape.get('stock_feed'),
        'execution_events': span(steps), 'market_observation_steps': span(quoted), 'distinct_markets': len(markets),
        'markets_by_series': {s: {'markets': len(row['markets']),
                                 'first_at': min(row['times']) if row['times'] else None,
                                 'last_at': max(row['times']) if row['times'] else None}
                              for s, row in series.items()},
        'signal_history': {s: {'rows': len(times), 'first_at': min(t for t in times if t),
                               'last_at': max(t for t in times if t)}
                           for s, times in signals.items() if any(times)},
        'warmup': {s: span(rows) for s, rows in (tape.get('warmup_bars') or {}).items()},
        'observed_bars': {s: span(rows) for s, rows in (tape.get('observed_bars') or {}).items()},
        'reported_settlements': len(tape.get('settlements') or {}),
        'note': 'These are actual returned tape counts/dates, not requested-window coverage or independent forward evidence. Settlement/cutoff events can extend beyond the last market observation. Historical fills remain modeled.',
    }
