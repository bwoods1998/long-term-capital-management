"""A RECORDED SEQUENCE OF THE SEATS UNDER "first-come" (release E5-A): one scripted week of the real `EquityBook` over
the real swarm store and its real reader, and everything the House did in it, as plain data.

    python3 -m league.tests.equity_seat_sequence > league/tests/fixtures/equity_seat_first_come.json

The file in league/tests/fixtures was written by this module run on the tree BEFORE the seat rule (release E5-S,
e36c7e39: seats granted first come by `league.swarm.bands.seating` and `EquityBook._sync_instances`). The tree's
test (league/tests/test_equity_seats.py) runs the same script with `equity_money.probe.seat.rule` "first-come" and
holds the result to that file, entry for entry: the rollback value IS the behaviour it replaced.

THE SCRIPT (three seats; five programs pass their looks at five different times, their ids in another order):
- Sunday: the House's first minutes seat the first three by pass time and ask them for Friday's close; two wait.
- Monday: the open window sends the planned buys; one seated program's realized net is at the program loss line, so
  the decision's band sync demotes it (EDM1, sticky) and the seating pass gives its seat to the next by pass time.
- Tuesday: the swarm retires one seated family; the decision retires its instance and plans its lot's exit; the
  seating pass seats the last waiting program. The demoted one queues behind and is never seated again.
- Wednesday: the exit goes at the open; the day ends.

Everything is invented (prices, sizes, programs); nothing here is a market's or an account's. The module uses only
what the tree before the seat rule already had, so it runs unchanged on both."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sys
import tempfile
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

SUNDAY, MONDAY, TUESDAY, WEDNESDAY = (dt.date(2026, 10, 11), dt.date(2026, 10, 12), dt.date(2026, 10, 13),
                                      dt.date(2026, 10, 14))
E = D("2229")
SEATS, SLEEVE = 3, "0.50"
#: (family, the seconds after the first pass at which it passed its look, its ETF): pass order is not id order.
PROGRAMS = (("m-first", 0.0, "SPY"), ("z-second", 1.0, "QQQ"), ("a-third", 2.0, "IWM"), ("k-fourth", 3.0, "DIA"),
            ("b-fifth", 4.0, "SPY"))
CODE = "NEEDS = {'symbols': ['SPY'], 'history': 2}\nPARAMS = {}\n\n\ndef decide(ctx):\n    return []\n"
MINUTES = ((9, 26), (9, 31), (9, 33), (12, 0), (15, 55), (15, 58), (16, 21), (16, 31), (16, 32), (16, 33))
#: Columns that differ from run to run (a process nonce, the fake venue's uuid) and are left out of the record.
VOLATILE = {"eq_orders": ("client_id", "venue_id")}


@contextlib.contextmanager
def interfaces() -> Iterator[None]:
    """The book's harness as league/tests/test_equity_book.py `BookTest` stubs it (core's fee and ctx constructors at
    their interface), with money's and the swarm's REAL functions (`size_entry`, `available_cash`, `next_band`)."""
    from league.equity import config
    from league.equity import ctx as C

    with contextlib.ExitStack() as stack:
        for target, name, value in ((config, "sell_fees", lambda proceeds, shares: D("0.01") if proceeds > 0 else D(0)),
                                    (C, "inputs_from_fetch", lambda raw, adj, **kw: {"raw": raw, "all": adj, **kw}),
                                    (C, "lot_row", lambda **kw: dict(kw)), (C, "closed_row", lambda **kw: dict(kw))):
            stack.enter_context(mock.patch.object(target, name, value))
        yield


def swarm(root: Path) -> Any:
    """The real swarm store at `root`: every program of `PROGRAMS` a Candidate that passed its look at its own time."""
    from league.swarm import evaluator
    from league.swarm.gate import run_sha
    from league.swarm.store import SwarmStore
    from league.tests.swarm_fakes import Clock as SwarmClock

    store = SwarmStore(root, clock=SwarmClock())
    identity = evaluator.equity_identity()
    t0 = float(store.clock())
    for fid, after, symbol in PROGRAMS:
        store.add_family({"id": fid, "mechanism": "Hold the ETF overnight from each close to the next open (MARKET "
                                                  "BETA).", "structure": "etf", "roots": [symbol],
                          "symbols": [symbol], "lane": "beta"}, origin="seed")
        version = store.add_version(fid, CODE.replace("SPY", symbol) + f"# {fid}\n", {}, author="test")
        store.set_state(fid, banded_version=1, banded_at=t0 + after,
                        banded_evaluator={"engine": identity["engine"], "equity_sha256": identity["equity"],
                                          "run_sha": run_sha(version)})
        store.set_band(fid, "candidate", reason="passed its sealed look")
    return store


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (D, dt.date)):
        return str(value)
    if isinstance(value, float):
        return round(value, 6)
    return value


def run(root: Path) -> dict[str, Any]:
    """The script on a House at `root` (a fresh directory); what it did, as plain data."""
    from league.equity import live as L
    from league.equity.families import EquityFamilies
    from league.swarm import elane
    from league.tests import equity_design as X
    from league.tests import test_equity_book as T

    with interfaces(), mock.patch.dict(elane.DEFAULTS, {"roster": SEATS}):
        store = swarm(root)
        h = T.Harness(root, cash=str(E), E=str(E), table=X.table_at(SEATS, SLEEVE).equity)
        h.families = EquityFamilies(root)
        h.book = h.new_book()
        h.state.execute("DELETE FROM kv WHERE key='eq_decide'")
        key = {fid: L.instance_key(fid, 1) for fid, _, _ in PROGRAMS}
        for fid, _, symbol in PROGRAMS:
            h.decider.needs[key[fid]] = {"symbols": [symbol], "history": 5, "max_hold_sessions": 5}
        for symbol in ("SPY", "QQQ", "IWM", "DIA"):
            h.market.make_bars(symbol, WEDNESDAY, n=20, price=float(sum(h.market.quote(symbol)) / 2))
        h.decider.plans[key["m-first"]] = [{"buy": "SPY", "share": 0.5, "at": "open"}]
        h.decider.plans[key["z-second"]] = [{"buy": "QQQ", "share": 0.5, "at": "close"}]
        h.decider.plans[key["k-fourth"]] = [{"buy": "DIA", "share": 0.5, "at": "open"}]
        ticks: list[dict[str, Any]] = []

        def tick(day: dt.date, hh: int, mm: int) -> None:
            out = h.tick(hh, mm, day=day)
            ticks.append({"day": day.isoformat(), "at": f"{hh:02d}:{mm:02d}",
                          "out": {k: v for k, v in out.items() if k in ("decided", "decide_failed", "families", "bands",
                                                                        "errors", "entries", "frozen", "working")},
                          "rows": sorted(f"{r['family']}:{r['band']}" for r in h.families.read())})

        try:
            tick(SUNDAY, 14, 0)
            tick(SUNDAY, 14, 1)
            tick(SUNDAY, 14, 2)
            h.decider.plans[key["m-first"]] = []                     # one lot each: no second buy
            for hh, mm in MINUTES[:6]:
                tick(MONDAY, hh, mm)
            # Monday afternoon: a-third's realized Probe net stands at the program loss line (a closed lot, by hand).
            lost = h.lot(h.book._instance(key["a-third"]), "IWM", "1", "220", opened=dt.date(2026, 10, 9))
            h.venue.held["IWM"] -= D("1")
            lost.status, lost.qty, lost.cash, lost.exit_day, lost.closed_at = "closed", D(0), D("-301"), MONDAY.isoformat(), \
                T.at(MONDAY, 15, 59)
            lost.exit_px, lost.exit_at, lost.reason = D("219"), "close", "program"
            h.book._save_lot(lost)
            for hh, mm in MINUTES[6:]:
                tick(MONDAY, hh, mm)
            for hh, mm in MINUTES[:6]:
                tick(TUESDAY, hh, mm)
            store.retire("m-first", "the script retires it")         # the swarm's own retirement of a seated family
            for hh, mm in MINUTES[6:]:
                tick(TUESDAY, hh, mm)
            for hh, mm in MINUTES:
                tick(WEDNESDAY, hh, mm)
            tables = {}
            for table in ("eq_instances", "eq_intents", "eq_orders", "eq_lots"):
                rows = [dict(r) for r in h.state.rows(f"SELECT * FROM {table} ORDER BY 1")]
                for row in rows:
                    for column in VOLATILE.get(table, ()):
                        row.pop(column, None)
                    if table == "eq_orders":
                        row["answer"] = sorted(json.loads(row["answer"] or "{}"))    # the keys an answer carries
                tables[table] = rows
            families = {fid: {"band": (store.family(fid) or {}).get("band"),
                              "retired": bool((store.family(fid) or {}).get("retired_at"))} for fid, _, _ in PROGRAMS}
            kv = {k: h.state.get(k) for k in ("eq_sticky", "eq_band_since", "eq_decide", "eq_synced", "eq_failed")}
            events = [[kind, {k: v for k, v in payload.items() if k not in ("client_id", "_answer")}]
                      for kind, payload in h.events if kind != "equity.error"]
            errors = [payload.get("where") for kind, payload in h.events if kind == "equity.error"]
            return _plain({"ticks": ticks, "tables": tables, "families": families, "kv": kv, "events": events,
                           "errors": errors, "alerts": [list(a) for a in h.alerts],
                           "sent": [{k: v for k, v in body.items() if k != "client_order_id"} for body in h.venue.sent]})
        finally:
            h.state.close()
            if h.families._store is not None:
                h.families._store.close()
            store.close()


def record() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return json.dumps(run(Path(tmp)), indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(record())
