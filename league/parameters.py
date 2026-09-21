"""Parameter admission and bounded, deterministic mutations; never executes strategy code.

Standard parameter names have documented units. New numeric knobs must declare bounds in
NEEDS.parameter_rules before the House mutates them. These are structural checks, not an
assessment of whether a strategy will trade, whether its data suffices, or whether it has edge.
"""
from __future__ import annotations

from copy import deepcopy
import ast
import math
import random
from typing import Any, Mapping


WINDOWS = frozenset(('lookback', 'window', 'breakout', 'fast', 'slow', 'exit_bars',
                     'mean_days', 'return_days', 'trend_days', 'breakout_days',
                     'exit_mean_days', 'rsi_period', 'vol_days', 'rv_window', 'min_bars'))
COUNTS = WINDOWS | {'max_open', 'min_days', 'max_days', 'exit_days'}
CLOCKS = frozenset(('entry_start', 'entry_end', 'flat_at', 'buy_start', 'buy_end',
                    'sell_start', 'sell_end', 'act_start', 'act_end'))
NONNEGATIVE = frozenset(('min_hours', 'max_hours', 'max_hold_hours', 'requote_minutes',
                        'min_volume_24h', 'min_open_interest', 'notional', 'notional_usd',
                        'stop_pct', 'take_profit_pct', 'max_spread_pct', 'min_gap_pct',
                        'min_edge_pct', 'replace_pct', 'z_entry', 'z_exit', 'k', 'min_premium'))
PROBABILITIES = frozenset(('bid_min', 'bid_max', 'no_bid_min', 'no_bid_max',
                         'yes_bid_min', 'yes_bid_max', 'underdog_ask_max', 'max_spread'))
ORDERED = (('bid_min', 'bid_max'), ('no_bid_min', 'no_bid_max'), ('yes_bid_min', 'yes_bid_max'),
           ('min_hours', 'max_hours'), ('min_days', 'max_days'), ('fast', 'slow'),
           ('entry_start', 'entry_end'), ('entry_end', 'flat_at'), ('buy_start', 'buy_end'),
           ('sell_start', 'sell_end'), ('act_start', 'act_end'), ('rsi_low', 'rsi_high'))


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _rules(params, needs):
    bounds = {key: [0, None] for key in NONNEGATIVE if key in params}
    bounds.update({key: [1, None] for key in COUNTS if key in params})
    bounds.update({key: [0, 1439] for key in CLOCKS if key in params})
    bounds.update({key: [0, 100] for key in ('rsi_entry', 'rsi_low', 'rsi_high') if key in params})
    if 'target_delta' in params:
        bounds['target_delta'] = [-1, 1]
    if needs.get('venue') == 'kalshi':
        bounds.update({key: [0, 1] for key in PROBABILITIES if key in params})
    # Standard rolling-window knobs cannot request more than the declared input capacity.
    bars = needs.get('bars') or {}
    limit = bars.get('limit') if isinstance(bars, dict) else None
    if number(limit) and limit > 0:
        for key in WINDOWS & params.keys():
            bounds[key][1] = min(500, int(limit))
    ordered = [list(pair) for pair in ORDERED if all(key in params for key in pair)]
    errors, frozen = [], set()
    declared = needs.get('parameter_rules', {})
    if not isinstance(declared, dict) or set(declared) - {'bounds', 'ordered', 'frozen'}:
        return bounds, ordered, frozen, ['parameter_rules must contain only bounds, ordered and frozen']
    extra = declared.get('bounds', {})
    if not isinstance(extra, dict):
        errors.append('parameter_rules.bounds must be an object')
        extra = {}
    for key, pair in extra.items():
        if (key not in params or not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(v is not None and not number(v) for v in pair)
                or (pair[0] is not None and pair[1] is not None and pair[0] > pair[1])):
            errors.append(f'invalid bounds for {key}')
            continue
        low, high = bounds.get(key, [None, None])
        lows, highs = [v for v in (low, pair[0]) if v is not None], [v for v in (high, pair[1]) if v is not None]
        bounds[key] = [max(lows) if lows else None, min(highs) if highs else None]
        if bounds[key][0] is not None and bounds[key][1] is not None and bounds[key][0] > bounds[key][1]:
            errors.append(f'{key} bounds conflict with its standard domain')
    extra = declared.get('ordered', [])
    if not isinstance(extra, list):
        errors.append('parameter_rules.ordered must be a list of [lower, upper] pairs')
        extra = []
    for pair in extra:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(not isinstance(k, str) or k not in params for k in pair):
            errors.append('each parameter order must name two existing parameters')
        elif list(pair) not in ordered:
            ordered.append(list(pair))
    extra = declared.get('frozen', [])
    if not isinstance(extra, list) or any(not isinstance(k, str) or k not in params for k in extra):
        errors.append('parameter_rules.frozen must list existing parameters')
    else:
        frozen.update(extra)
    return bounds, ordered, frozen, errors


def inspect(params: Mapping[str, Any], needs: Mapping[str, Any] | None = None) -> dict:
    needs = needs or {}
    bounds, ordered, frozen, errors = _rules(params, needs)

    def finite(value, path):
        if type(value) in (int, float) and not number(value):
            errors.append(f'{path} must be finite')
        elif isinstance(value, dict):
            for k, v in value.items():
                finite(v, f'{path}.{k}')
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                finite(v, f'{path}[{i}]')

    finite(params, 'params')
    for key, (low, high) in bounds.items():
        value = params[key]
        if not number(value):
            errors.append(f'{key} must be a finite number, not a boolean or string')
        elif key in COUNTS | CLOCKS and type(value) is not int:
            errors.append(f'{key} must be an integer')
        elif (low is not None and value < low) or (high is not None and value > high):
            errors.append(f'{key}={value} outside [{low}, {high}]')
    for lower, upper in ordered:
        if not number(params[lower]) or not number(params[upper]):
            errors.append(f'{lower} and {upper} must be finite numbers')
        elif params[lower] > params[upper]:
            errors.append(f'{lower}={params[lower]} must be <= {upper}={params[upper]}')
    mutable = sorted(key for key in bounds if key not in frozen and number(params[key]))
    return {'valid': not errors, 'errors': errors, 'bounds': bounds, 'ordered': ordered,
            'mutable': mutable, 'frozen': sorted(set(params) - set(mutable))}


def require_valid(params, needs=None):
    errors = inspect(params, needs)['errors']
    if errors:
        raise ValueError('invalid parameters: ' + '; '.join(errors))


def same_logic(before: str, after: str) -> bool:
    """A repair may change literal PARAMS and comments, never decision code or NEEDS."""
    def normalized(code):
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PARAMS' for t in node.targets):
                if len(node.targets) != 1 or not isinstance(ast.literal_eval(node.value), dict):
                    raise ValueError('only a literal parameter dictionary can be repaired')
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'PARAMS')]
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                    node.body.pop(0)
        return ast.dump(tree, include_attributes=False)
    try:
        return normalized(before) == normalized(after)
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return False


def mutate(params: Mapping[str, Any], *, seed: str, scale: float = 0.2,
           needs: Mapping[str, Any] | None = None, excluded=()) -> dict[str, Any]:
    """Change one declared/standard numeric knob; reject invalid and duplicate proposals.

    At most 64 proposals, using no market data, inference or sandbox. Never clamp an experiment
    into a different one, silently repair its parent, or return an unchanged duplicate child.
    """
    require_valid(params, needs)
    if not number(scale) or not 0 < scale <= 1:
        raise ValueError('mutation scale must be in (0, 1]')
    report = inspect(params, needs)
    choices = report['mutable']
    rng = random.Random(seed)
    for _ in range(64 if choices else 0):
        key = rng.choice(choices)
        value = params[key]
        low, high = report['bounds'][key]
        try:
            width = abs(value) * scale if value else scale * (high - low if low is not None and high is not None else 1)
            if type(value) is int:
                width = max(1, width)
            changed = value + rng.uniform(-width, width)
        except OverflowError:
            continue
        if not number(changed):
            continue
        child = deepcopy(dict(params))
        child[key] = int(round(changed)) if type(value) is int else round(changed, 6)
        if child != params and child not in excluded and inspect(child, needs)['valid']:
            return child
    raise ValueError('no distinct valid parameter mutation within 64 proposals')
