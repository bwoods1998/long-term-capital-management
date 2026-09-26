"""A deterministic options deployment proof on synthetic quotes. It is never trading evidence."""
from __future__ import annotations
from pathlib import Path


def verify_runtime() -> dict:
    import numpy as np
    from .gym import ENGINE_VERSION, ctx, greeks, legs, runtime, venue
    from .live.money import Table

    strikes = np.repeat(np.arange(440.0, 461.0), 2)
    calls = np.tile([True, False], strikes.size // 2)
    dte = np.zeros(strikes.size, dtype=int)
    minute, spot = 700, 450.0
    mid = greeks.bs_price(spot, strikes, greeks.years_to_expiry(dte, minute), 0.04, 0.25, calls)
    snap = ctx.Snapshot("SPY", minute, spot, dte, strikes, calls,
                        np.maximum(np.round(mid - 0.02, 2), 0.0), np.round(mid + 0.02, 2) + 0.01,
                        np.full(strikes.size, 50), np.full(strikes.size, 50), rate=0.04)
    code = (Path(__file__).parent / "gym" / "examples" / "condor_vrp.py").read_text()
    program = runtime.load_program(code, name="synthetic-canary", params={"vrp_min": 0.1, "dte_min": 0})
    closes = [440.0, 442.0, 441.0, 444.0, 445.0, 443.0]
    under = ctx.underlying_view("SPY", np.full(minute - 570 + 1, spot), closes=closes,
                                opens=closes, highs=closes, lows=closes)
    needs = program.needs
    chain = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band))
    rules = venue.rules_for("SPY")
    context = ctx.build_ctx(minute=minute, open_minute=570, close_minute=960, weekday=0,
                            chains={"SPY": chain}, underlyings={"SPY": under}, positions=[], orders=[],
                            cash=5000.0, equity=5000.0, budget=5000.0, buying_power=5000.0,
                            params=program.params, rules={"SPY": rules.as_dict()}, events={}, events_next={})
    runner = program.start()
    orders = [value for value in runner.decide(context) if "open" in value]
    if runner.errors or len(orders) != 1:
        raise RuntimeError("synthetic options program did not produce its expected intent")
    opened = legs.resolve_open(orders[0], snap, rules, buying_power=5000.0)
    if opened.type != "iron_condor" or [leg.side for leg in opened.legs] != [1, -1, -1, 1]:
        raise RuntimeError("synthetic option legs did not resolve")
    if not 0 < opened.max_loss + 2 * opened.fees <= 150.0:
        raise RuntimeError("synthetic maximum loss or fees changed")
    legs.resolve_close({"close": 1, "limit": {"mid": 1}}, opened.type, opened.legs,
                       opened.qty, snap, rules, position=1)
    Table.from_constitution()  # validates the actual money table before the release is accepted
    return {"synthetic": True, "engine": ENGINE_VERSION, "program_runtime": "ok",
            "structure_resolution": "ok", "maximum_loss_and_fees": "ok", "money_table": "ok"}
