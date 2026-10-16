"""THE INERTNESS SCENARIO of C3 (A45) of the scaling plan (league/tests/test_scaled_inert.py): one synthetic equity book
run through the House's own code, measured on everything C3 could move. It uses ONLY what C2's head (`feat/scale-c2`,
22646a97) already had, so the same scenario run on C2's tree wrote the golden file it is compared with
(league/tests/fixtures/scaled_inert_c2.json): `python3 -m league.tests.scaled_inert_scenario OUT.json` from a C2 tree
writes it again (the module is copied there, or loaded by path, and imports that tree's league).

What it does: a state root holding a Probe pin (C2's E_P and, beside it, C3's fields: the plan's sha256 and rungs that
name two of the programs, which C2 does not read), four programs (two ETF programs in the Probe band, a Sized one and a
panel), held and closed lots of each mark, a session's open window worked by the book (sends, fills, an exit) and its
close window (a buy left working), and then
every reading: what each entry stated to money's `size_entry`, the send's orders and the lots they opened (their marks
and `info`), each program's decide view, the panel's budget, the equity rows' Probe figures and both lanes' Probe
budget, the budget's room, each program's EDM1 record, the forward rows, the Done meter's equity closes, counts and
beside-figures (league/ops/dlane_report.py), the swarm's family loss line, and the book's own memory (its kv keys, the
records and alerts it wrote, its health without C3's own key). Every figure is invented; no account's, no market's.
Standard library only."""

from __future__ import annotations

import dataclasses
import json
import sys
from contextlib import ExitStack, contextmanager
from decimal import Decimal as D
from pathlib import Path
from typing import Any, Iterator
from unittest import mock

#: The pin's synthetic figures and C3's fields beside them (C2 reads `probe_e_usd` only).
E = "5000"
E_P = "1937.41"
PLAN_SHA = "ab" * 32
NONCE = "00112233445566778899aabbccddeeff"
#: The programs: (family, lane, band).
PROGRAMS = (("fam-a", "beta", "probe"), ("fam-b", "equity", "probe"), ("fam-sized", "equity", "sized"))


def pin_body() -> bytes:
    """The pin's bytes: E_P, the plan's sha256 and rungs for fam-a (R2) and fam-b (R1), and a nonce."""
    return json.dumps({"probe_e_usd": E_P, "plan_sha256": PLAN_SHA,
                       "rungs": {"eq|fam-a|v1": 2, "eq|fam-b|v1": 1}, "money_digest": "0" * 64, "basis": "synthetic",
                       "at": "2026-10-16T04:30:00+00:00", "nonce": NONCE}, sort_keys=True).encode()


@contextmanager
def stubs() -> Iterator[None]:
    """league/tests/test_equity_book.py's `BookTest` stubs (money's `size_entry` recording what it was told, the House's
    cash rule, core's fees and ctx constructors, swarm's `next_band` and money's Sized share), for the body."""
    from league.equity import bands as B
    from league.equity import config
    from league.equity import ctx as C
    from league.equity import sizing as Z
    from league.live import money as M
    from league.tests import test_equity_book as T

    T.SIZED.clear()
    with ExitStack() as stack:
        for target, name, value in ((Z, "size_entry", T.fake_size), (M, "available_cash", T.fake_available),
                                    (config, "sell_fees", lambda proceeds, shares: D("0.01") if proceeds > 0 else D(0)),
                                    (C, "inputs_from_fetch", lambda raw, adj, **kw: {"raw": raw, "all": adj, **kw}),
                                    (C, "lot_row", lambda **kw: dict(kw)), (C, "closed_row", lambda **kw: dict(kw)),
                                    (B, "next_band", lambda row, record, table, *, seat_free, sticky=None:
                                     (row["band"], "unchanged")),
                                    (B, "sized_sleeve_share", lambda record, table: D("0.50"))):
            stack.enter_context(mock.patch.object(target, name, value))
        yield


def plain(value: Any) -> Any:
    """A reading as JSON: Decimals and floats as text, dataclasses as dicts, keys sorted."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return plain(dataclasses.asdict(value))
    if isinstance(value, D):
        return f"D:{value}"
    if isinstance(value, float):
        return f"F:{value!r}"
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


#: Columns that differ run to run whatever the code (a process nonce in the client id, the fake venue's uuids).
VOLATILE = {"client_id", "venue_id", "_answer", "id"}


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def run(root: Path, *, configure: Any = None) -> dict[str, Any]:
    """The scenario under `root` (an empty directory): the readings, as JSON. `configure(h)`, when given, is called on the
    harness once its programs exist (the C3 test sets C3's own settings there; C2's run passes none)."""
    from league.equity import live as L
    from league.live import real as R
    from league.ops import dlane_report as DR
    from league.swarm import elane
    from league.swarm.store import SwarmStore
    from league.tests import test_equity_book as T
    from league.tests.swarm_fakes import Clock as StoreClock
    from league.tests.test_equity_probe_pin import PinHarness

    out: dict[str, Any] = {}
    (root / L.PROBE_PIN_FILE).write_bytes(pin_body())
    state = root / "state"
    state.mkdir()
    with stubs():
        h = PinHarness(state, root, E=E, cash="20000")
        try:
            insts = {fam: h.instance(fam, lane=lane, band=band) for fam, lane, band in PROGRAMS}
            if configure is not None:
                configure(h)
            a, b, sized = insts["fam-a"], insts["fam-b"], insts["fam-sized"]
            # The book as it stands before the session: a held Probe lot of each ETF program, a held Sized lot, closed
            # lots of each mark (a Probe loss and a Probe gain, a Sized loss).
            held_a = h.lot(a, "SPY", "0.5", "590")
            h.lot(b, "QQQ", "0.4", "480")
            h.lot(sized, "IWM", "1.2", "210", probe=False)
            for inst, symbol, qty, px, cash, day, probe in ((b, "QQQ", "0.5", "470", "-31.25", "2026-10-07", True),
                                                            (a, "SPY", "0.3", "580", "12.40", "2026-10-08", True),
                                                            (sized, "IWM", "0.8", "215", "-9.10", "2026-10-08", False)):
                lot = L.Lot(h.book._next("eq_lots", "lid"), inst.id, inst.family, inst.version, inst.lane, symbol,
                            "etf", D(qty), D(qty), D(px), D(qty) * D(px), "close", opened_at=T.at(T.FRIDAY, 15, 56) - 86400 * 7,
                            opened_day="2026-10-01", status=L.LOT_CLOSED, exit_px=D(px), exit_at="open", exit_day=day,
                            closed_at=T.at(T.FRIDAY, 9, 31) - 86400 * 2, cash=D(cash), reason="program", probe=probe)
                h.book._save_lot(lot)
            # The day's intents (decided Friday): each program buys at the open; fam-a sells its held SPY lot.
            h.intent(a, "buy", symbol="QQQ", share="0.5")
            h.intent(b, "buy", symbol="DIA", share="0.4")
            h.intent(sized, "buy", symbol="IWM", share="0.3")
            h.intent(a, "sell", lid=held_a.lid)
            ticks = []
            for hh, mm in ((9, 25), (9, 31), (9, 32), (9, 33), (9, 34), (9, 40), (9, 46)):
                ticks.append(scrub(plain(h.tick(hh, mm))))
            # The close window: one more buy that the venue leaves working, so the readings below hold a working buy.
            h.intent(b, "buy", symbol="SPY", share="0.2", at_="close")
            h.venue.fill = "none"
            for hh, mm in ((15, 55), (15, 56)):
                ticks.append(scrub(plain(h.tick(hh, mm))))
            out["ticks"] = ticks
            out["sized_at_send"] = [plain(x) for x in T.SIZED]
            # Each program's entry sized again now (what it states to size_entry) and its decide view.
            day = T.MONDAY.isoformat()
            direct = {}
            for fam, inst in insts.items():
                before = len(T.SIZED)
                intent = h.intent(inst, "buy", symbol="SPY", share="0.5")
                got = h.book._size(intent, inst, "SPY", "etf", D("100"), None, day)
                direct[fam] = {"sized": plain(got), "stated": plain(T.SIZED[before:]),
                               "why": h.get_intent(intent.iid).why}
            out["sized_now"] = direct
            bars = {"raw": {"SPY": [{"t": "2026-10-09", "c": "100"}]}, "all": {"SPY": [{"t": "2026-10-09", "c": "100"}]},
                    "shas": {}}
            views = {}
            for fam, inst in insts.items():
                inputs, _ = h.book._inputs(inst, T.MONDAY, {"symbols": ["SPY"], "history": 0}, bars)
                views[fam] = plain({k: inputs.get(k) for k in ("budget", "cash", "equity", "caps")})
            out["decide_views"] = views
            panel = L.replace(h.instance("fam-panel", band="probe", lane="equity"), kind="panel")
            h.book._save_instance(panel)
            before = len(T.SIZED)
            got = h.book._size(h.intent(panel, "buy", symbol="SPY", share="0.5"), panel, "SPY", "etf", D("100"), None, day)
            out["panel"] = {"sized": plain(got), "stated": plain(T.SIZED[before:]),
                            "budget": plain(h.book._panel_budget(panel, day, []))}
            # THE LINES: the equity rows' Probe figures, both lanes' Probe budget, its room, each program's record.
            weights = {"etf": D("0.20"), "stock": D("0.40")}
            out["probe_figures"] = plain(L.probe_figures(h.state.rows, weights=weights))
            out["probe_budget"] = plain(list(R.probe_figures(h.state.rows, day=day, table=h.table)))
            out["budget_room"] = plain(h.book._budget_room(day))
            out["records"] = {fam: plain(h.book._record_of(fam, 1, None)) for fam in insts}
            out["orders"] = scrub(plain([dict(r) for r in h.state.rows("SELECT * FROM eq_orders ORDER BY eid")]))
            out["lots"] = plain([dict(r) for r in h.state.rows("SELECT * FROM eq_lots ORDER BY lid")])
            out["exports"] = plain([L.export_row(lot) for lot in h.book._lots(open_only=False)
                                    if lot.status == L.LOT_CLOSED])
            # THE DONE READING (league/ops/dlane_report.py over this live.sqlite).
            book = DR.read_book(state / "live.sqlite")
            closes = DR.equity_closes(book["lots"], since=0.0, seeded=("fam-a",))
            out["done"] = plain({"closes": closes, "counts": DR.done_counts(closes),
                                 "beside": DR.equity_beside(closes)})
            # THE BOOK'S OWN MEMORY: kv, what it recorded and alerted, its health (C3's own key left out).
            kv = {r["key"]: r["value"] for r in h.state.rows("SELECT key, value FROM kv ORDER BY key")}
            out["kv_keys"] = sorted(kv)
            out["kv"] = {k: v for k, v in kv.items() if k not in ("eq_recon",)}
            out["events"] = scrub(plain([[kind, payload] for kind, payload in h.events]))
            out["alerts"] = plain(h.alerts)
            health = h.book.health()
            health.pop("scaled", None)
            out["health"] = scrub(plain(health))
        finally:
            h.state.close()
    # THE SWARM'S FAMILY LINE (league/swarm/elane.py `loss_line`): fam-a's real forward rows, then one more loss. The
    # swarm's store sits beside the book's live.sqlite, as on the House (one state root).
    store = SwarmStore(state, clock=StoreClock())
    try:
        store.add_family({"id": "fam-a", "mechanism": "Hold the ETF overnight from each close to the next open.",
                          "structure": "etf", "roots": ["SPY"], "symbols": ["SPY"], "lane": "beta"}, origin="seed")
        fam = store.family("fam-a")
        rows = [{"id": f"eq-{r['lid']}", "day": r["exit_day"], "pnl": float(D(r["cash"])), "max_loss": 600.0}
                for r in out["lots"] if r["family"] == "fam-a" and r["status"] == "closed"]
        store.add_forward("fam-a", "real", [dict(r, pnl=r["pnl"]) for r in rows])
        line = [elane.loss_line(store, fam, {})]
        store.add_forward("fam-a", "real", [{"id": "eq-900", "day": "2026-10-09", "pnl": -320.0, "max_loss": 600.0}])
        line.append(elane.loss_line(store, fam, {}))
        out["family_line"] = line
    finally:
        store.close()
    return out


def canonical(out: dict[str, Any]) -> str:
    return json.dumps(out, sort_keys=True, indent=1)


if __name__ == "__main__":  # pragma: no cover - the golden file's writer (run on C2's tree)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = run(Path(tmp))
    Path(sys.argv[1]).write_text(canonical(result) + "\n", encoding="utf-8")
    print(sys.argv[1])
