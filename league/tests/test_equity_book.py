"""The equity book (`league/equity/live.py`): its order path, windows, lots, reconciliation, corporate actions, decide,
exit rules and exports, against an in-memory venue with Alpaca's documented stock-order shapes and invented prices.

DESIGN 11's EquityBook list and league/equity/INTERFACES.md 5.2's: write before send, unknown then lookup, restart
recovery mid-window (open and close), fractional partial fills, FIFO between two instances on one symbol, DIV and SPLIT
booking, Decimal reconcile with assignment shares, one working order per symbol across both books, exits first then
entries on post-fill cash, collar escalation and the cut-offs, the close window re-priced to 15:59:30 then missed,
cancel then resend after a terminal state (a fill after the cancel), kill / stop / freeze blocking opens and not exits,
the day order cap and A8.5's exit rules.

Other packages' functions are stubbed at their interface (league/equity/INTERFACES.md 12): money's `size_entry` and
`available_cash`, core's `sell_fees` and ctx constructors, swarm's `next_band`, the hooks' decider kind; their own
packages test them. No price here is a market's."""

import dataclasses
import datetime as dt
import tempfile
import unittest
import uuid
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal as D
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.equity import bands as B
from league.equity import config
from league.equity import ctx as C
from league.equity import live as L
from league.equity import schedule as S
from league.equity import sizing as Z
from league.equity.families import MemoryEquityFamilies
from league.live import money as M
from league.live.state import LiveState
from league.live.venue import Submitted

NY = ZoneInfo("America/New_York")
FRIDAY, MONDAY, TUESDAY, WEDNESDAY = (dt.date(2026, 10, 9), dt.date(2026, 10, 12), dt.date(2026, 10, 13),
                                      dt.date(2026, 10, 14))
CODE = "def decide(ctx):\n    return []\n"


def at(day: dt.date, hh: int, mm: int, ss: int = 3) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=NY).timestamp()


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = float(t)


class Market:
    """SIP snapshots and 1Day bars of invented prices."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.quotes = {"SPY": (D("599.90"), D("600.10")), "QQQ": (D("499.90"), D("500.10")),
                       "IWM": (D("219.95"), D("220.05")), "DIA": (D("449.90"), D("450.10")),
                       "AAPL": (D("229.90"), D("230.10"))}
        self.bar_rows: dict[str, dict[str, list[dict]]] = {"raw": {}, "all": {}}
        self.bar_calls: list[tuple] = []
        self.calls = 0

    def quote(self, symbol: str) -> tuple[D, D]:
        return self.quotes[symbol]

    def stocks(self, symbols):
        self.calls += 1
        out = {}
        for s in symbols:
            bid, ask = self.quotes[s]
            t = iso(self.clock() - 1)
            out[s] = {"latestQuote": {"bp": float(bid), "ap": float(ask), "t": t},
                      "latestTrade": {"p": float((bid + ask) / 2), "t": t}}
        return out

    def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
        self.bar_calls.append((tuple(symbols), timeframe, start, end, adjustment))
        return {s: [dict(r) for r in self.bar_rows[adjustment].get(s, [])
                    if start <= r["t"][:10] and (end is None or r["t"][:10] < end)] for s in symbols}

    def make_bars(self, symbol: str, last: dt.date, *, n: int = 12, price: float = 600.0, factor: float = 0.99) -> None:
        days, d = [], last
        while len(days) < n:
            if S.is_session(d):
                days.append(d)
            d -= dt.timedelta(days=1)
        raw, adj = [], []
        for i, day in enumerate(sorted(days)):
            c = round(price + 0.25 * i, 2)
            row = {"t": f"{day.isoformat()}T04:00:00Z", "o": c - 0.5, "h": c + 1.0, "l": c - 1.0, "c": c, "v": 1000000 + i}
            raw.append(row)
            adj.append({**row, **{k: round(row[k] * factor, 4) for k in ("o", "h", "l", "c")}})
        self.bar_rows["raw"][symbol], self.bar_rows["all"][symbol] = raw, adj


class Venue:
    """A stock account as the gateway shows it, in memory. `fill`: "cross" fills whole when the limit crosses the quote,
    "partial" fills `partial` of the order a reading, "none" rests. `submit_mode`: ok | lost (the order is made, the
    answer lost) | lost_absent (nothing made, the answer lost) | reject (the venue) | gateway (a cap) | ratelimited.
    `cancel_delay`: seconds a cancel shows pending_cancel; `fill_in_cancel`: a share of the order filled while it does."""

    def __init__(self, market: Market, clock: Clock, *, cash: str = "2000"):
        self.market, self.clock = market, clock
        self.cash = D(cash)
        self.held: dict[str, D] = {}
        self.book: list[dict] = []
        self.fill = "cross"
        self.partial = D("0.4")
        self.submit_mode = "ok"
        self.sent: list[dict] = []
        self.cancels: list[str] = []
        self.on_submit = None
        self.cancel_delay = 0.0
        self.fill_in_cancel: D | None = None
        self.activity_rows: list[dict] = []
        self.activity_calls: list[tuple] = []
        self.refused_types: set[str] = set()

    # ---------------------------------------------------------------- reads
    def account(self) -> dict:
        value = sum((q * sum(self.market.quote(s)) / 2 for s, q in self.held.items()), D(0))
        return {"equity": str(self.cash + value), "last_equity": str(self.cash + value), "cash": str(self.cash),
                "short_market_value": "0", "buying_power": str(self.cash), "multiplier": "1"}

    def positions(self) -> list[dict]:
        self._advance()
        return [{"symbol": s, "asset_class": "us_equity", "qty": str(q), "qty_available": str(q),
                 "side": "long" if q > 0 else "short", "market_value": str(q * sum(self.market.quote(s)) / 2)}
                for s, q in sorted(self.held.items()) if q != 0]

    def orders(self, *, status="all", after=None, limit=500) -> list[dict]:
        self._advance()
        rows = [self._public(o) for o in self.book]
        if status == "open":
            rows = [r for r in rows if r["status"] in ("new", "accepted", "partially_filled", "pending_cancel")]
        return rows

    def order_by_client_id(self, client_order_id: str):
        self._advance()
        for o in self.book:
            if o["client_order_id"] == client_order_id:
                return self._public(o)
        return None

    def activities(self, types, *, after=None) -> list[dict]:
        self.activity_calls.append((tuple(types), after))
        if set(types) & self.refused_types:
            raise RuntimeError("alpaca activities: HTTP 422 invalid activity type")
        return [dict(r) for r in self.activity_rows if r["activity_type"] in set(types)]

    # ---------------------------------------------------------------- writes
    def submit(self, body, *, exit: bool) -> Submitted:
        body = dict(body)
        self.sent.append(body)
        if self.on_submit is not None:
            self.on_submit(body)
        if self.submit_mode == "reject":
            return Submitted(False, {"code": 40310000, "message": "insufficient qty available"},
                             "HTTP 403 insufficient qty available", status=403)
        if self.submit_mode == "gateway":
            return Submitted(False, {"error": "Real stock buys are off.", "cap": "stock_buys_off"},
                             "HTTP 403 Real stock buys are off.", status=403)
        if self.submit_mode == "ratelimited":
            return Submitted(False, None, "rate", sent=False)
        order = {"id": str(uuid.uuid4()), "client_order_id": body["client_order_id"], "status": "new",
                 "symbol": body["symbol"], "side": body["side"], "qty": body["qty"], "limit_price": body["limit_price"],
                 "type": body["type"], "time_in_force": body["time_in_force"], "filled_qty": "0",
                 "filled_avg_price": None, "submitted_at": iso(self.clock()), "order_class": "simple", "legs": None}
        self.book.append(order)
        if self.submit_mode == "lost":
            return Submitted(False, None, "no answer: timed out", unknown=True)
        if self.submit_mode == "lost_absent":
            self.book.remove(order)
            return Submitted(False, None, "no answer: timed out", unknown=True)
        self._try_fill(order)
        return Submitted(True, self._public(order), "", status=200)

    def cancel(self, venue_id: str):
        self.cancels.append(venue_id)
        for o in self.book:
            if o["id"] == venue_id and o["status"] in ("new", "accepted", "partially_filled"):
                if self.cancel_delay:
                    o["status"], o["_cancel_at"] = "pending_cancel", self.clock() + self.cancel_delay
                else:
                    o["status"], o["canceled_at"] = "canceled", iso(self.clock())
                return True, ""
        return False, "HTTP 422 order is not cancelable"

    # ---------------------------------------------------------------- the venue's side
    def _advance(self) -> None:
        for o in self.book:
            if o["status"] == "pending_cancel":
                if self.fill_in_cancel is not None and not o.get("_cancel_filled"):
                    o["_cancel_filled"] = True
                    self._fill(o, (D(o["qty"]) * self.fill_in_cancel).quantize(D("1e-9"), rounding=ROUND_DOWN))
                    if o["status"] == "partially_filled":
                        o["status"] = "pending_cancel"
                if self.clock() >= o["_cancel_at"]:
                    o["status"], o["canceled_at"] = "canceled", iso(self.clock())
            elif o["status"] in ("new", "accepted", "partially_filled"):
                self._try_fill(o)

    def _try_fill(self, o: dict) -> None:
        if self.fill == "none":
            return
        bid, ask = self.market.quote(o["symbol"])
        limit = D(o["limit_price"])
        buying = o["side"] == "buy"
        if (buying and ask > limit) or (not buying and bid < limit):
            return
        qty, done = D(o["qty"]), D(o["filled_qty"])
        if self.fill == "partial":
            if self.clock() - o.get("_partial_at", float("-inf")) < 60:
                return                                              # one partial fill a minute
            o["_partial_at"] = self.clock()
        add = qty - done if self.fill == "cross" else min(qty - done, (qty * self.partial).quantize(D("1e-9"),
                                                                                                    rounding=ROUND_DOWN))
        self._fill(o, add)

    def _fill(self, o: dict, add: D) -> None:
        if add <= 0:
            return
        bid, ask = self.market.quote(o["symbol"])
        buying = o["side"] == "buy"
        price = ask if buying else bid
        qty, done = D(o["qty"]), D(o["filled_qty"])
        old = D(o["filled_avg_price"] or 0)
        o["filled_avg_price"] = str((old * done + price * add) / (done + add))
        o["filled_qty"] = str(done + add)
        o["status"] = "filled" if done + add >= qty else "partially_filled"
        if o["status"] == "filled":
            o["filled_at"] = iso(self.clock())
        self.held[o["symbol"]] = self.held.get(o["symbol"], D(0)) + (add if buying else -add)
        self.cash += -price * add if buying else price * add

    @staticmethod
    def _public(o: dict) -> dict:
        return {k: v for k, v in o.items() if not k.startswith("_")}


class Decider:
    """The hooks' decider kind at its interface: loads answer NEEDS, a decide answers each job's planned intents."""

    def __init__(self):
        self.needs: dict[str, dict] = {}
        self.plans: dict[str, list] = {}
        self.loads: list[tuple[str, dict]] = []
        self.drops: list[str] = []
        self.jobs: list[dict] = []
        self.fail = False
        self.refuse: set[str] = set()

    def kind_load(self, kind, key, payload, *, budget_seconds=None):
        assert kind == "equity"
        self.loads.append((key, dict(payload)))
        if key in self.refuse:
            raise ValueError("the program did not load")
        return {"ok": True, "needs": self.needs.get(key, {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 20}),
                "sha": "s" * 64, "run_sha": "r" * 64}

    def kind_drop(self, kind, key, *, budget_seconds=10.0):
        self.drops.append(key)

    def kind(self, kind, op, payload, *, budget_seconds=None):
        assert (kind, op) == ("equity", "decide")
        self.jobs.append(payload)
        if self.fail:
            raise RuntimeError("the decider failed")
        return {"ok": True, "results": {job["key"]: {"intents": list(self.plans.get(job["key"], [])), "stats": {},
                                                     "ctx_sha": "c" * 64} for job in payload["jobs"]}}


class Proof:
    """`league.live.paper.StockPaperProof` at its interface (A10.1's two stages): `ok` is the BUY stage, `sell` the
    SELL stage, `failed` a SELL stage that failed (its why)."""

    def __init__(self, passed: bool = True):
        self.ok = passed
        self.sell = passed
        self.failed = ""
        self.steps = 0
        self.seen: list[tuple] = []

    def buy_passed(self) -> bool:
        return self.ok

    def sell_passed(self) -> bool:
        return self.sell

    def sell_failed(self) -> str:
        return self.failed

    def passed(self) -> bool:
        return self.ok and self.sell

    def status(self) -> dict:
        return {"passed": self.passed()}

    def step(self, now, *, market, window=None):
        self.steps += 1
        self.seen.append((now, window))
        return {"status": "waiting"}


class OptionsBook:
    def __init__(self):
        self.busy_symbols: set[str] = set()
        self.count = 0
        self.reserve_n = 0
        self.reserved_usd = 0.0
        self.book_loss = D(0)

    def busy(self):
        return set(self.busy_symbols)

    def count_today(self, day):
        return self.count

    def exit_reserve(self):
        return self.reserve_n

    def reserved(self):
        return self.reserved_usd

    def exposure(self, family, *, day, week_start):
        return M.Exposure(book_loss=self.book_loss)


def equity_table(**over) -> M.EquityTable:
    base = dict(enabled=True, universe=dict(config.UNIVERSE), position_share={"etf": D("0.50"), "stock": D("0.20")},
                invested_share=D("1.00"), cash_reserve=D("50"), open_risk_weight={"etf": D("0.20"), "stock": D("0.40")},
                probe_sleeve_share=D("0.25"), probe_max_programs=3, min_order_usd=D("10"), sized_min_trades=20,
                sized_confidence=0.80, sized_kelly_fraction=0.25, sized_sleeve_share=D("0.50"), sized_beat_bh=True,
                sized_min_probe_sessions=5, demotion_rule="edm1", demotion_min_trades=10, demotion_z=1.645,
                program_loss_usd=D("-300"), twin_gap_bp=D("15"), twin_min_closes=5, min_hold_sessions=1,
                default_max_hold_sessions=20, max_hold_sessions=60, failed_decides_exit=2,
                entry_collar_bp={"etf": 10, "stock": 25}, max_collar_bp={"etf": 50, "stock": 100}, max_orders_day=60,
                offsets=dict(S.DEFAULTS))
    base.update(over)
    return M.EquityTable(**base)


def family_row(family="seed-overnight-spy", *, version=1, band="probe", lane="beta", symbols=("SPY",)):
    return {"family": family, "band": band, "lane": lane, "structure": "etf", "symbols": list(symbols), "seeded": True,
            "holdout_passed": True, "validation_passed": True, "version": version, "code": CODE, "params": {},
            "run_sha": "r1", "validation_r_sd": None}


SIZED: list = []


def fake_size(x: Z.SizingInputs) -> Z.Sized:
    """Money's rule at its interface, enough of it for the book's tests: target, then the sleeve's cash, the House-wide
    cash and the budget's room, then the minimum order."""
    SIZED.append(x)
    if x.cash < 0:
        return Z.Sized(D(0), D(0), "cash_negative", "the account owes cash")
    target = x.usd if x.usd is not None else x.share * x.sleeve_equity
    binding = "intent"
    caps = [(x.sleeve_free_cash, "sleeve_cash"), (x.available_cash, "cash")]
    if x.budget_room is not None:
        caps.append((x.budget_room / x.weight, "budget"))
    for cap, name in caps:
        if cap < target:
            target, binding = max(D(0), cap), name
    if target < x.min_order_usd:
        return Z.Sized(D(0), D(0), "min_order", f"${target} is under ${x.min_order_usd}")
    qty = (target / x.limit_price).quantize(D("1e-6"), rounding=ROUND_DOWN)
    return Z.Sized(qty * x.limit_price, qty, binding, "sized")


def fake_available(account, *, working_buys_worst, reserved, reserve_usd):
    return (D(account["cash"]) - abs(D(account.get("short_market_value") or 0)) - working_buys_worst - reserved
            - reserve_usd)


class Harness:
    def __init__(self, root: Path, *, cash: str = "2000", E: str = "2000", table: M.EquityTable | None = None,
                 rows=()):
        self.clock = Clock(at(MONDAY, 9, 0))
        self.market = Market(self.clock)
        self.venue = Venue(self.market, self.clock, cash=cash)
        self.state = LiveState(root / "live.sqlite", clock=self.clock)
        self.table = dataclasses.replace(M.Table.from_constitution(), equity=table or equity_table())
        self.families = MemoryEquityFamilies(rows)
        self.decider = Decider()
        self.proof = Proof()
        self.options = OptionsBook()
        self.E = D(E)
        self.blocked: str | None = None
        self.kill = False
        self.events: list[tuple[str, dict]] = []
        self.alerts: list[tuple[str, str]] = []
        self.book = self.new_book()
        # Friday's decision is done: the window tests start on Monday morning with no catch-up due.
        self.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})

    def new_book(self) -> L.EquityBook:
        return L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            clock=self.clock, record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))

    def tick(self, hh: int, mm: int, ss: int = 3, *, day: dt.date = MONDAY, positions=None, open_orders=None) -> dict:
        self.clock.set(at(day, hh, mm, ss))
        return self.book.tick(self.clock(), account_row=self.venue.account(), positions=positions,
                              open_orders=open_orders, real_block=lambda opening=True: self.blocked,
                              killed=lambda: self.kill)

    def instance(self, family="seed-overnight-spy", version=1, *, band="probe", lane="beta", max_hold=20) -> L.Instance:
        inst = L.Instance(L.instance_key(family, version), family, version, lane, "r1", CODE, {}, band, True, max_hold,
                          created_at=self.clock())
        self.book._save_instance(inst)
        self.families.rows.setdefault(family, family_row(family, version=version, band=band, lane=lane))
        return inst

    def lot(self, inst: L.Instance, symbol="SPY", qty="0.5", px="590", *, opened=FRIDAY, entry_at="close",
            probe=True) -> L.Lot:
        qty, px = D(qty), D(px)
        lot = L.Lot(self.book._next("eq_lots", "lid"), inst.id, inst.family, inst.version, inst.lane, symbol,
                    config.UNIVERSE[symbol], qty, qty, px, qty * px, entry_at, opened_at=at(opened, 15, 56),
                    opened_day=opened.isoformat(), cash=-(qty * px), probe=probe)
        self.book._save_lot(lot)
        self.venue.held[symbol] = self.venue.held.get(symbol, D(0)) + qty
        return lot

    def intent(self, inst: L.Instance, kind: str, *, symbol=None, lid=None, share=None, usd=None, at_="open",
               exec_day=MONDAY, decided=FRIDAY, tag="") -> L.Intent:
        now = self.clock()
        intent = L.Intent(self.book._next("eq_intents", "iid"), inst.id, inst.family, inst.version, decided.isoformat(),
                          exec_day.isoformat(), at_, kind, "planned", symbol=symbol, lid=lid,
                          share=None if share is None else D(share), usd=None if usd is None else D(usd), tag=tag,
                          created_at=now, updated_at=now)
        self.book._save_intent(intent)
        return intent

    def get_intent(self, iid: int) -> L.Intent:
        return self.book._intent(iid)

    def orders(self) -> list[L.Order]:
        return [L.Order.of(r) for r in self.state.rows("SELECT * FROM eq_orders ORDER BY eid")]

    def lots(self, *, open_only: bool = False) -> list[L.Lot]:
        return self.book._lots(open_only=open_only)

    def intents(self, **where) -> list[L.Intent]:
        rows = [L.Intent.of(r) for r in self.state.rows("SELECT * FROM eq_intents ORDER BY iid")]
        return [i for i in rows if all(getattr(i, k) == v for k, v in where.items())]

    def decide_setup(self, day: dt.date = MONDAY, symbols=("SPY",)) -> None:
        for symbol in symbols:
            self.market.make_bars(symbol, day, price=float(sum(self.market.quote(symbol)) / 2))


class BookTest(unittest.TestCase):
    """Every test: a fresh state, money's and core's functions stubbed at their interface."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        SIZED.clear()
        for target, name, value in ((Z, "size_entry", fake_size), (M, "available_cash", fake_available),
                                    (config, "sell_fees", lambda proceeds, shares: D("0.01") if proceeds > 0 else D(0)),
                                    (C, "inputs_from_fetch", lambda raw, adj, **kw: {"raw": raw, "all": adj, **kw}),
                                    (C, "lot_row", lambda **kw: dict(kw)), (C, "closed_row", lambda **kw: dict(kw)),
                                    (B, "next_band", lambda row, record, table, *, seat_free, sticky=None:
                                     (row["band"], "unchanged")),
                                    (B, "sized_sleeve_share", lambda record, table: D("0.50"))):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def harness(self, **kw) -> Harness:
        h = Harness(self.root, **kw)
        self.addCleanup(h.state.close)
        return h


# ------------------------------------------------------------------------------------------------- the pure pieces
class Pieces(BookTest):
    def test_client_ids(self):
        self.assertEqual(L.client_id(7, "Seed Overnight SPY!"), "lq-0000007-seed-overnight-spy")
        self.assertEqual(L.client_id(7, "seed", nonce="a1b2c3d4"), "lq-a1b2c3d4-0000007-seed")
        long = L.client_id(1234567, "x" * 80, nonce="a1b2c3d4")
        self.assertEqual(len(long), 48)
        self.assertTrue(long.startswith(L.CLIENT_PREFIX))

    def test_limits_round_away_from_the_trade(self):
        self.assertEqual(L.limit_for("buy", D("600.10"), 10), D("600.71"))      # 600.7001 up to the cent
        self.assertEqual(L.limit_for("sell", D("599.90"), 10), D("599.30"))     # 599.3001 down to the cent
        self.assertEqual(L.limit_for("buy", D("0.5"), 10), D("0.5005"))         # under $1: four places
        self.assertEqual(L.limit_for("sell", D("0.5"), 10), D("0.4995"))
        self.assertEqual([L.collar_for(k, 10, 50) for k in range(7)], [10, 20, 30, 40, 50, 50, 50])
        self.assertEqual([L.collar_for(k, 25, 100) for k in range(5)], [25, 50, 75, 100, 100])

    def test_the_order_body_is_the_gateways(self):
        order = L.Order(1, "lq-0000001-f", "f@1:r", "f", "buy", "SPY", "etf", "open", D("0.416174"), D("600.71"), 10,
                        "pending", 0.0, "2026-10-12")
        self.assertEqual(L.order_body(order), {"symbol": "SPY", "qty": "0.416174", "side": "buy", "type": "limit",
                                               "limit_price": "600.71", "time_in_force": "day",
                                               "client_order_id": "lq-0000001-f"})
        self.assertEqual(L.qty_text(D("2.500000000")), "2.5")
        self.assertEqual(L.qty_text(D("3")), "3")

    def test_row_figures(self):
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        h.lot(a, "SPY", "1", "500")
        lot = h.lot(a, "QQQ", "2", "400")
        h.lot(b, "AAPL", "1", "200")
        lot.mark = D("410")
        h.book._save_lot(lot)
        closed = h.lot(b, "SPY", "1", "500")
        closed.status, closed.qty, closed.cash, closed.exit_day, closed.closed_at = "closed", D(0), D("-3.5"), "2026-10-09", 1.0
        h.book._save_lot(closed)
        unprobed = h.lot(b, "DIA", "1", "400", probe=False)
        unprobed.status, unprobed.qty, unprobed.cash, unprobed.closed_at = "closed", D(0), D("9"), 2.0
        h.book._save_lot(unprobed)
        order = L.Order(1, "lq-1", a.id, "fam-a", "buy", "IWM", "etf", "open", D("2"), D("220"), 10, "working", 0.0,
                        "2026-10-12", filled_qty=D("0.5"), avg_px=D("219"))
        h.book._save_order(order)
        weights = {"etf": D("0.20"), "stock": D("0.40")}
        fig = L.probe_figures(h.state.rows, weights=weights)
        self.assertEqual(fig.programs, 2)                                 # one slot a program, never one a lot
        self.assertEqual(fig.closes, (("2026-10-09", D("-3.5")),))        # Probe closes only
        # 0.2 x 500 + 0.2 x 2 x 410 (marked) + 0.4 x 200 + 0.2 x 1.5 x 220 (what the buy may still fill)
        self.assertEqual(fig.open_risk, D("100") + D("164") + D("80") + D("66"))
        self.assertEqual(L.working_buys_worst(h.state.rows), D("330"))
        self.assertEqual(L.invested(h.state.rows), D("500") + D("820") + D("200") + D("330"))
        # The order's fill booked to no lot yet: the unbooked part counts as owned.
        self.assertEqual(L.expected_shares_rows(h.state.rows), {"SPY": D("1"), "QQQ": D("2"), "AAPL": D("1"),
                                                                "IWM": D("0.5")})
        h.state.execute("INSERT INTO eq_fills(eid, lid, qty, px, fees, at) VALUES(1, NULL, '0.5', '219', '0', 0)")
        self.assertNotIn("IWM", L.expected_shares_rows(h.state.rows))

    def test_a_state_from_before_the_lane_reads_as_nothing(self):
        state = LiveState(self.root / "old.sqlite")
        self.addCleanup(state.close)
        self.assertEqual(L.probe_figures(state.rows, weights={}), L.ProbeFigures(0, (), D(0)))
        self.assertEqual(L.expected_shares_rows(state.rows), {})
        self.assertEqual((L.working_buys_worst(state.rows), L.orders_today(state.rows, "2026-10-12"),
                          L.invested(state.rows)), (D(0), 0, D(0)))

    def test_the_day_count_counts_cancels_not_refusals(self):
        h = self.harness()
        inst = h.instance()
        for eid, status, answer in ((1, "filled", {}), (2, "canceled", {"cancel_day": "2026-10-12"}),
                                    (3, "refused", {"house": True}), (4, "pending", {})):
            h.book._save_order(L.Order(eid, f"lq-{eid}", inst.id, inst.family, "buy", "SPY", "etf", "open", D(1),
                                       D(600), 10, status, 0.0, "2026-10-12", answer=answer))
        h.book._save_order(L.Order(5, "lq-5", inst.id, inst.family, "buy", "SPY", "etf", "open", D(1), D(600), 10,
                                   "canceled", 0.0, "2026-10-09", answer={"cancel_day": "2026-10-12"}))
        self.assertEqual(L.orders_today(h.state.rows, "2026-10-12"), 5)  # 1, 2 + its cancel, 4, and 5's cancel
        self.assertEqual(L.orders_today(h.state.rows, "2026-10-09"), 1)


# ------------------------------------------------------------------------------------------------- the order path
class OrderPath(BookTest):
    def test_an_entry_is_written_pending_before_it_is_sent(self):
        h = self.harness()
        inst = h.instance()
        it = h.intent(inst, "buy", symbol="SPY", share="0.5")
        seen = []

        def check(body):
            row = h.state.rows("SELECT status, side FROM eq_orders WHERE client_id=?", (body["client_order_id"],))
            seen.append((row[0]["status"], h.get_intent(it.iid).status))

        h.venue.on_submit = check
        h.tick(9, 30, 20)
        self.assertEqual(h.venue.sent, [])                                 # not before 09:30:30
        h.tick(9, 31)
        self.assertEqual(seen, [("pending", "sent")])
        body = h.venue.sent[0]
        limit = D("600.71")
        qty = (D(250) / limit).quantize(D("1e-6"), rounding=ROUND_DOWN)     # 0.5 of a 0.25 x $2,000 sleeve
        self.assertEqual(body, {"symbol": "SPY", "qty": L.qty_text(qty), "side": "buy", "type": "limit",
                                "limit_price": "600.71", "time_in_force": "day",
                                "client_order_id": body["client_order_id"]})
        self.assertTrue(body["client_order_id"].startswith(f"lq-{h.state.nonce}-0000001-seed-overnight-spy"))
        lot = h.lots()[0]
        self.assertEqual((lot.qty, lot.entry_px, lot.entry_notional, lot.cash, lot.entry_at, lot.opened_day, lot.probe),
                         (qty, D("600.10"), qty * D("600.10"), -(qty * D("600.10")), "open", "2026-10-12", True))
        self.assertEqual(h.state.rows("SELECT COUNT(*) AS n FROM eq_fills")[0]["n"], 1)
        h.tick(9, 32)
        self.assertEqual(h.get_intent(it.iid).status, "done")
        self.assertEqual(len(h.venue.sent), 1)

    def test_a_lost_answer_is_looked_up_never_resent(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.submit_mode, h.venue.fill = "lost", "none"
        h.tick(9, 31)
        self.assertEqual(h.orders()[0].status, "unknown")
        h.venue.submit_mode, h.venue.fill = "ok", "cross"
        h.tick(9, 32)
        order = h.orders()[0]
        self.assertEqual((order.status, len(h.venue.sent)), ("filled", 1))
        self.assertEqual(h.lots()[0].qty, order.qty)
        h.tick(9, 33)
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_an_order_the_venue_never_shows_is_lost_and_the_entry_missed(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.submit_mode = "lost_absent"
        for mm in range(31, 37):
            h.tick(9, mm)
        self.assertEqual(h.orders()[0].status, "lost")
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(len(h.venue.sent), 1)                             # never re-sent blind
        self.assertTrue(any("lost" in text for _, text in h.alerts))

    def test_a_lost_sale_goes_again_only_while_the_shares_are_still_held(self):
        for filled in (False, True):
            with self.subTest(filled=filled):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                h = Harness(Path(tmp.name))
                self.addCleanup(h.state.close)
                inst = h.instance()
                lot = h.lot(inst, "SPY", "0.5", "590")
                h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
                h.venue.submit_mode = "lost_absent"
                for mm in range(31, 34):
                    h.tick(9, mm)
                self.assertEqual(h.orders()[0].status, "unknown")
                if filled:                                                  # it filled after all, unseen
                    h.venue.held["SPY"] -= D("0.5")
                h.venue.submit_mode = "ok"
                h.tick(9, 34)                                               # lost now, and the exit decides again
                self.assertEqual(h.orders()[0].status, "lost")
                if filled:
                    self.assertEqual(len(h.venue.sent), 1)
                    self.assertTrue(any("may have filled" in text for _, text in h.alerts))
                    self.assertEqual(h.book._lot(lot.lid).status, "closing")
                else:
                    self.assertEqual(len(h.venue.sent), 2)
                    self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_a_crash_between_the_row_and_the_post(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")

        def die(body):
            raise SystemExit("the House stopped")

        h.venue.on_submit = die
        with self.assertRaises(SystemExit):
            h.tick(9, 31)
        self.assertEqual(h.orders()[0].status, "pending")
        h.venue.on_submit = None
        h.book = h.new_book()                                               # the restart
        for mm in range(32, 40):
            h.tick(9, mm)
        self.assertEqual(h.orders()[0].status, "lost")
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(len(h.venue.sent), 1)

    def test_a_lost_order_the_venue_shows_after_all_is_taken_back(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.submit_mode, h.venue.fill = "lost", "none"
        h.tick(9, 31)
        hidden = h.venue.book.pop()
        for mm in range(32, 36):
            h.tick(9, mm)
        self.assertEqual(h.orders()[0].status, "lost")
        h.venue.book.append(hidden)
        h.venue.fill = "cross"
        h.tick(9, 37)
        self.assertEqual(h.orders()[0].status, "filled")
        self.assertEqual(len(h.lots()), 1)
        self.assertTrue(any("after all" in text for _, text in h.alerts))

    def test_a_gateway_refusal_ends_the_entry_a_rate_refusal_retries(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.submit_mode = "ratelimited"
        h.tick(9, 31)
        self.assertEqual((h.orders()[0].status, h.get_intent(it.iid).status), ("refused", "sent"))
        h.venue.submit_mode = "gateway"
        h.tick(9, 32)
        self.assertEqual(h.orders()[1].answer.get("cap"), "stock_buys_off")
        h.tick(9, 33)
        self.assertEqual(h.get_intent(it.iid).status, "refused")
        self.assertEqual(len(h.venue.sent), 2)


class Restarts(BookTest):
    def test_restart_mid_open_window(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        h.book = h.new_book()
        h.tick(9, 32)                                                       # re-priced by the new process
        h.venue.fill = "cross"
        h.tick(9, 33)
        h.tick(9, 34)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20])
        self.assertEqual(orders[1].replaces, orders[0].eid)
        self.assertEqual([o.status for o in orders], ["canceled", "filled"])
        self.assertEqual(len(h.lots()), 1)
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_restart_mid_close_window_then_missed(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
        h.venue.fill = "none"
        h.tick(15, 54)
        self.assertEqual(h.venue.sent, [])                                  # a close intent waits for 15:55
        h.tick(15, 55)
        h.book = h.new_book()
        for mm in (56, 57, 58, 59):
            h.tick(15, mm)
        h.tick(16, 0)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50])
        self.assertEqual([o.status for o in orders], ["canceled"] * 5)
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(h.lots(), [])
        h.tick(16, 5)
        self.assertEqual(len(h.venue.sent), 5)                              # never chased


class Fills(BookTest):
    def test_fractional_partial_fills_build_one_lot(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "partial"
        for mm in range(31, 46):
            h.tick(9, mm)
        lot = h.lots()[0]
        fills = h.state.rows("SELECT qty, px FROM eq_fills ORDER BY fid")
        orders = h.orders()
        self.assertGreaterEqual(len(fills), 3)
        self.assertGreater(len(orders), 1)
        self.assertLess(orders[1].qty, orders[0].qty)                       # target minus filled, re-priced
        self.assertEqual(lot.qty, sum((D(f["qty"]) for f in fills), D(0)))
        self.assertEqual(lot.qty, sum((o.filled_qty for o in orders), D(0)))
        self.assertEqual(lot.entry_notional, sum((D(f["qty"]) * D(f["px"]) for f in fills), D(0)))
        self.assertEqual(lot.entry_px, D("600.10"))
        self.assertEqual(h.venue.held["SPY"], lot.qty)
        self.assertLessEqual(lot.entry_notional, D(250))
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_a_sale_closes_only_its_own_lot(self):
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        mine, theirs = h.lot(a, "SPY", "1", "590"), h.lot(b, "SPY", "2", "580")
        it = h.intent(a, "sell", symbol="SPY", lid=mine.lid)
        h.tick(9, 31)
        body = h.venue.sent[0]
        self.assertEqual((body["side"], body["qty"], body["limit_price"]), ("sell", "1", "599.30"))
        closed, kept = h.book._lot(mine.lid), h.book._lot(theirs.lid)
        self.assertEqual((closed.status, closed.qty, closed.exit_px, closed.reason), ("closed", D(0), D("599.90"), "program"))
        self.assertEqual(closed.cash, D("-590") + D("599.90") - D("0.01"))
        self.assertEqual(closed.fees, D("0.01"))
        self.assertEqual((kept.status, kept.qty), ("open", D("2")))
        self.assertEqual(h.book.expected_shares(), {"SPY": D("2")})
        self.assertEqual(h.venue.held["SPY"], D("2"))
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_a_fill_after_the_cancel_and_the_replacement_after_the_terminal_state(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill, h.venue.cancel_delay, h.venue.fill_in_cancel = "none", 90.0, D("0.5")
        h.tick(9, 31)
        first = h.orders()[0]
        h.tick(9, 32)                                                       # the cancel goes; the venue fills half meanwhile
        self.assertEqual(len(h.orders()), 1)
        self.assertEqual(h.orders()[0].status, "working")
        self.assertEqual(h.lots()[0].qty, (first.qty * D("0.5")).quantize(D("1e-9"), rounding=ROUND_DOWN))
        h.tick(9, 33)                                                       # still pending_cancel: no replacement yet
        self.assertEqual(len(h.orders()), 1)
        h.tick(9, 34)
        orders = h.orders()
        self.assertEqual(orders[0].status, "canceled")
        second = orders[1]
        filled = orders[0].filled_qty * orders[0].avg_px
        limit = L.limit_for("buy", D("600.10"), 20)
        self.assertEqual(second.replaces, first.eid)
        self.assertEqual(second.qty, ((first.qty * first.limit_px - filled) / limit).quantize(D("1e-6"),
                                                                                                  rounding=ROUND_DOWN))
        self.assertGreaterEqual(second.placed_at, orders[0].updated_at - 1)
        self.assertEqual(SIZED[-1].usd, first.qty * first.limit_px - filled)
        self.assertIsNone(SIZED[-1].share)
        self.assertEqual(h.get_intent(it.iid).status, "sent")


# ------------------------------------------------------------------------------------------------- the windows
class Windows(BookTest):
    def test_exits_first_and_entries_on_the_cash_after_their_fills(self):
        h = self.harness(cash="300")
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        h.intent(a, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(b, "buy", symbol="QQQ", share="1")
        h.venue.fill = "none"
        h.tick(9, 31)
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"])      # the entry waits for the exit
        h.venue.fill = "cross"
        h.tick(9, 32)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell", "buy"])
        sized = SIZED[-1]
        cash_after = D("300") + D("0.5") * D("599.90")
        self.assertEqual(sized.cash, cash_after)
        self.assertEqual(sized.available_cash, cash_after - D("50"))       # the sale's proceeds, less the reserve
        self.assertEqual(D(h.venue.sent[1]["qty"]), (D(500) / D("500.61")).quantize(D("1e-6"), rounding=ROUND_DOWN))
        self.assertEqual(h.book._intent(buy.iid).status, "sent")
        self.assertEqual(h.lots(open_only=True)[0].symbol, "QQQ")

    def test_entries_go_two_minutes_after_the_open_whatever_the_exits(self):
        h = self.harness(cash="300")
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        h.intent(a, "sell", symbol="SPY", lid=lot.lid)
        h.intent(b, "buy", symbol="QQQ", share="1")
        h.venue.fill = "none"
        h.tick(9, 31)
        h.tick(9, 32)
        self.assertNotIn("buy", [b["side"] for b in h.venue.sent])
        h.tick(9, 33)                                                       # 09:32:30 has passed
        self.assertIn("buy", [b["side"] for b in h.venue.sent])
        self.assertEqual(SIZED[-1].available_cash, D("250"))                # nothing from the unfilled sale

    def test_entry_collars_widen_then_the_cut_off(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        for mm in range(31, 50):
            h.tick(9, mm)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50])
        self.assertEqual([L.limit_for("buy", D("600.10"), o.collar_bp) for o in orders], [o.limit_px for o in orders])
        self.assertLess(max(o.placed_at for o in orders), at(MONDAY, 9, 45, 0))
        self.assertTrue(all(o.status == "canceled" for o in orders))
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(L.orders_today(h.state.rows, "2026-10-12"), 10)    # five sends and five cancels

    def test_at_the_widest_collar_only_a_quote_through_the_limit_re_prices(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        for mm in range(31, 39):
            h.tick(9, mm)
        self.assertEqual(len(h.orders()), 5)                                # still marketable at 50 bp: left working
        h.market.quotes["SPY"] = (D("604.00"), D("604.20"))                 # the market ran through its limit
        h.tick(9, 39)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50, 50])
        self.assertEqual(orders[-1].limit_px, L.limit_for("buy", D("604.20"), 50))

    def test_exits_continue_all_day_then_go_at_the_bid_then_carry(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.venue.fill = "none"
        for hh, mm in ((9, 31), (9, 32), (9, 33), (12, 0), (15, 54), (15, 55)):
            h.tick(hh, mm)
        self.assertEqual([o.collar_bp for o in h.orders()], [10, 20, 30, 40, 50])
        h.market.quotes["SPY"] = (D("590.00"), D("590.20"))                 # the bid fell through its limit
        for hh, mm in ((15, 56), (15, 59), (16, 0)):
            h.tick(hh, mm)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50, 50])
        self.assertTrue(all(o.side == "sell" for o in orders))
        self.assertIn("late", orders[5].why)                                # after 15:55: at the bid, the widest collar
        self.assertEqual(orders[5].limit_px, L.limit_for("sell", D("590.00"), 50))
        self.assertEqual([o.at for o in orders], ["open"] * 5 + ["close"])
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        carried = h.intents(kind="house_exit")
        self.assertEqual([(c.exec_day, c.at, c.tag, c.lid, c.status) for c in carried],
                         [("2026-10-13", "open", "program", lot.lid, "planned")])
        h.venue.fill = "cross"
        h.market.quotes["SPY"] = (D("599.90"), D("600.10"))
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual(h.book._lot(lot.lid).reason, "program")

    def test_a_close_exit_left_from_a_past_session_goes_at_the_open(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590", opened=dt.date(2026, 10, 8))
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close", exec_day=FRIDAY, decided=dt.date(2026, 10, 8))
        h.tick(9, 31)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual(h.book._lot(lot.lid).exit_at, "open")             # the window it went in, not the intent's

    def test_a_short_filled_order_ends(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        venue_order = h.venue.book[0]
        venue_order.update(status="filled", filled_qty="0.4", filled_avg_price="600.10")
        h.venue.held["SPY"] = D("0.4")
        h.tick(9, 32)
        order = h.orders()[0]
        self.assertEqual((order.status, order.filled_qty), ("filled", D("0.4")))
        self.assertIn("short_fill", order.answer)
        self.assertEqual(h.book.busy(), set())
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_a_lot_never_sells_in_the_session_it_was_bought(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "600", opened=MONDAY, entry_at="open")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close", decided=FRIDAY)
        for hh, mm in ((15, 55), (15, 56), (16, 0)):
            h.tick(hh, mm)
        self.assertEqual(h.venue.sent, [])
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(h.intents(kind="house_exit")[0].exec_day, "2026-10-13")
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_one_working_order_a_symbol_across_both_books(self):
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        spy = h.intent(a, "buy", symbol="SPY", share="0.2")
        qqq = h.intent(b, "buy", symbol="QQQ", share="0.2")
        h.options.busy_symbols = {"SPY"}
        h.tick(9, 31)
        self.assertEqual([b["symbol"] for b in h.venue.sent], ["QQQ"])
        self.assertIn("options book", h.get_intent(spy.iid).why)
        h.options.busy_symbols = set()
        shares = [{"symbol": "SPY", "client_order_id": "lv-shares-spy-1", "status": "new", "side": "sell"}]
        h.tick(9, 32, open_orders=shares)
        self.assertIn("not the equity book's", h.get_intent(spy.iid).why)
        self.assertEqual(len(h.venue.sent), 1)
        h.venue.fill = "none"
        third = h.intent(b, "buy", symbol="SPY", share="0.2")
        h.tick(9, 33)                                                       # a's SPY goes; b's waits for it
        self.assertEqual([b["symbol"] for b in h.venue.sent], ["QQQ", "SPY"])
        self.assertIn("equity order on SPY is working", h.get_intent(third.iid).why)
        self.assertEqual(h.get_intent(qqq.iid).status, "done")

    def test_kill_stop_and_freeze_block_opens_not_exits(self):
        for gate in ("stop", "kill", "freeze", "disabled", "proof"):
            with self.subTest(gate=gate):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                h = Harness(Path(tmp.name))
                self.addCleanup(h.state.close)
                a, b = h.instance("fam-a"), h.instance("fam-b")
                lot = h.lot(a, "SPY", "0.5", "590")
                h.intent(a, "sell", symbol="SPY", lid=lot.lid)
                buy = h.intent(b, "buy", symbol="QQQ", share="0.2")
                if gate == "stop":
                    h.blocked = "the daily stop: no new real entry today"
                elif gate == "kill":
                    h.kill = True
                elif gate == "freeze":
                    h.state.put("eq_freeze", {"why": "an unexplained corporate action on SPY"})
                elif gate == "disabled":
                    h.table = dataclasses.replace(h.table, equity=equity_table(enabled=False))
                    h.book = h.new_book()
                else:
                    h.proof.ok = False
                h.tick(9, 31)
                h.tick(9, 34)
                sides = [b["side"] for b in h.venue.sent]
                self.assertNotIn("buy", sides)
                self.assertTrue(h.get_intent(buy.iid).why)
                if gate == "kill":
                    self.assertEqual(sides, [])                             # the gateway's kill blocks sells too
                    self.assertIn("kill switch", h.intents(kind="sell")[0].why)
                    h.kill = False
                    h.tick(9, 35)
                self.assertEqual(h.book._lot(lot.lid).status, "closed")
                h.tick(9, 46)
                self.assertEqual(h.get_intent(buy.iid).status, "done" if gate == "kill" else "missed")

    def test_the_day_order_cap(self):
        h = self.harness(table=equity_table(max_orders_day=3))
        inst = h.instance()
        intents = [h.intent(inst, "buy", symbol=s, share="0.2") for s in ("SPY", "QQQ", "IWM")]
        h.tick(9, 31)
        self.assertEqual([b["symbol"] for b in h.venue.sent], ["SPY"])
        self.assertIn("order count", h.get_intent(intents[1].iid).why)      # 1 sent + 1 + 2 kept for the lot's exit > 3
        h2 = Harness(self.root / "house")
        self.addCleanup(h2.state.close)
        inst2 = h2.instance()
        for s in ("SPY", "QQQ"):
            h2.intent(inst2, "buy", symbol=s, share="0.2")
        h2.options.count = int(h2.table.max_orders_day) - 1
        h2.tick(9, 31)
        self.assertEqual(len(h2.venue.sent), 1)                             # the House-wide count had room for one
        self.assertIn("House's day order count", h2.intents(symbol="QQQ")[0].why)


# ------------------------------------------------------------------------------------------------- reconciliation
class Reconciliation(BookTest):
    def test_decimal_shares_with_an_assignments(self):
        h = self.harness()
        inst = h.instance()
        h.lot(inst, "SPY", "1.5", "590")
        h.state.put("shares", {"SPY": "100"})
        h.venue.held["SPY"] = D("101.5")
        out = h.tick(9, 26)
        self.assertEqual(out["reconcile"], "clean")
        h.venue.held["SPY"] = D("101.500000001")                            # inside the 1e-9 tolerance
        self.assertEqual(h.tick(9, 27)["reconcile"], "clean")
        h.venue.held["SPY"] = D("101.4")
        self.assertIn("SPY", h.tick(9, 28)["reconcile"][0])
        self.assertEqual(h.book.frozen, "")                                 # one reading: not yet
        h.tick(9, 29)
        self.assertIn("SPY: the account holds 101.4", h.book.frozen)
        self.assertTrue(any("frozen" in text for _, text in h.alerts))
        buy = h.intent(h.instance("fam-b"), "buy", symbol="QQQ", share="0.2")
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("equity reconciliation", h.get_intent(buy.iid).why)
        h.venue.held["SPY"] = D("101.5")
        h.tick(9, 32)
        self.assertNotEqual(h.book.frozen, "")
        h.tick(9, 33)                                                       # two clean readings lift it
        self.assertEqual(h.book.frozen, "")
        self.assertEqual([b["symbol"] for b in h.venue.sent], ["QQQ"])

    def test_a_symbol_in_flux_is_not_judged(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        stale = [{"symbol": "SPY", "asset_class": "us_equity", "qty": "0.3", "side": "long"}]
        h.tick(9, 32, positions=stale)
        h.tick(9, 33, positions=stale)
        self.assertEqual(h.book.frozen, "")

    def test_an_equity_order_the_book_does_not_know(self):
        h = self.harness()
        stray = [{"symbol": "QQQ", "client_order_id": "lq-ffffffff-0000099-ghost", "status": "new"}]
        h.tick(9, 26, open_orders=stray)
        h.tick(9, 27, open_orders=stray)
        self.assertIn("does not know", h.book.frozen)


# ------------------------------------------------------------------------------------------------- corporate actions
class Activities(BookTest):
    def test_a_dividend_to_the_lots_held_on_its_ex_date(self):
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        sold = h.lot(a, "SPY", "1", "500", opened=dt.date(2026, 9, 28))
        sold.status, sold.qty, sold.exit_day, sold.closed_at = "closed", D(0), "2026-10-02", 1.0
        h.book._save_lot(sold)
        h.venue.held["SPY"] = D("2")
        held = h.lot(b, "SPY", "2", "500", opened=dt.date(2026, 10, 1))
        h.lot(b, "SPY", "3", "500", opened=dt.date(2026, 10, 5))                  # bought after: not entitled
        h.venue.activity_rows = [{"id": "d1", "activity_type": "DIV", "date": "2026-10-09", "symbol": "SPY",
                                  "qty": "3", "net_amount": "4.50", "per_share_amount": "1.5"}]
        h.tick(9, 26)
        self.assertEqual((h.book._lot(sold.lid).div, h.book._lot(sold.lid).cash), (D("1.5"), D("-500") + D("1.5")))
        self.assertEqual(h.book._lot(held.lid).div, D("3.0"))
        self.assertEqual(h.state.rows("SELECT COUNT(*) AS n FROM eq_activities")[0]["n"], 1)
        h.tick(9, 42)                                                       # read again: booked once
        self.assertEqual(h.book._lot(held.lid).div, D("3.0"))

    def test_a_split_and_the_reconciliation_after_it(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "1.5", "600")
        h.venue.held["SPY"] = D("3")                                        # the venue applied a 2:1 split
        h.venue.activity_rows = [{"id": "s1", "activity_type": "SSP", "date": "2026-10-12", "symbol": "SPY",
                                  "qty": "1.5", "net_amount": "0"}]
        h.tick(9, 26)                                                       # no ratio in the row: the account's own
        split = h.book._lot(lot.lid)
        self.assertEqual((split.qty, split.opened_qty, split.entry_px, split.entry_notional),
                         (D("3.000000000"), D("3.000000000"), D("300.000000"), D("900.0")))
        h.tick(9, 27)
        self.assertEqual(h.book.frozen, "")

    def test_a_refused_type_never_hides_the_others(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "2", "500", opened=dt.date(2026, 9, 28))
        h.venue.refused_types = {"DIVTW"}                                   # the venue refuses one listed type
        h.venue.activity_rows = [{"id": "d1", "activity_type": "DIV", "date": "2026-10-09", "symbol": "SPY",
                                  "qty": "2", "net_amount": "1.00", "ex_date": "2026-10-08"}]
        h.tick(9, 26)
        self.assertEqual(h.book._lot(lot.lid).div, D("1.00"))
        self.assertIn("DIVTW", h.state.get("eq_activity_refused"))

    def test_a_booking_that_fails_is_read_again(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "2", "500", opened=dt.date(2026, 9, 28))
        h.venue.activity_rows = [{"id": "d1", "activity_type": "DIV", "date": "2026-10-01", "symbol": "SPY",
                                  "qty": "2", "net_amount": "1.00", "ex_date": "2026-09-30"},
                                 {"id": "d2", "activity_type": "DIV", "date": "2026-10-09", "symbol": "SPY",
                                  "qty": "2", "net_amount": "2.00", "ex_date": "2026-10-08"}]
        h.lot(inst, "QQQ", "1", "400", opened=dt.date(2026, 9, 1))
        real = L.EquityBook._book_activity

        def flaky(book, row, now, out):
            if row["id"] == "d1":
                raise RuntimeError("not today")
            return real(book, row, now, out)

        with mock.patch.object(L.EquityBook, "_book_activity", flaky):
            h.tick(9, 26)
        self.assertEqual(h.state.get("eq_activities_cursor"), "2026-10-01")  # held back to the failed row's day
        self.assertEqual(h.book._lot(lot.lid).div, D("2.00"))
        h.tick(9, 42)
        self.assertEqual(h.book._lot(lot.lid).div, D("3.00"))
        self.assertEqual(h.state.get("eq_activities_cursor"), "2026-10-09")

    def test_any_other_action_on_a_held_symbol_freezes_entries(self):
        h = self.harness()
        inst = h.instance()
        h.lot(inst, "SPY", "1", "600")
        h.venue.activity_rows = [{"id": "x1", "activity_type": "SC", "date": "2026-10-12", "symbol": "SPY"}]
        h.venue.refused_types = {"DIVTXEX"}                                 # a type the venue refuses: skipped from now on
        h.tick(9, 26)
        self.assertIn("SC", h.book.frozen)
        self.assertEqual(h.state.get("eq_activity_refused"), ["DIVTXEX"])
        self.assertTrue(any(level == "error" for level, _ in h.alerts))


# ------------------------------------------------------------------------------------------------- the decide
class Decide(BookTest):
    def setup_decide(self, h: Harness, *, rows=None, needs=None) -> L.Instance:
        h.families.rows = {r["family"]: dict(r) for r in (rows if rows is not None else [family_row()])}
        inst = h.instance()
        if needs is not None:
            h.decider.needs[inst.id] = needs
        h.decide_setup(MONDAY, symbols=("SPY", "QQQ"))
        return inst

    def test_the_bars_then_the_decide_then_the_intents(self):
        h = self.harness()
        inst = self.setup_decide(h)
        other = h.instance("fam-b")
        theirs = h.lot(other, "SPY", "1", "580")
        mine = h.lot(inst, "SPY", "0.4", "590")
        h.families.rows["fam-b"] = family_row("fam-b")
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5, "at": "close", "tag": "overnight"},
                                    {"buy": "AAPL", "share": 0.1}, {"sell": 999}, {"sell": theirs.lid},
                                    {"sell": mine.lid}, {"cancel": 4242}, "junk", {"buy": "SPY", "share": 2}]
        h.tick(16, 21)                                                      # the bars, no decide yet
        self.assertEqual(h.decider.jobs, [])
        self.assertEqual({c[4] for c in h.market.bar_calls}, {"raw", "all"})
        rows = h.state.rows("SELECT * FROM eq_bars WHERE day=? AND symbol='SPY'", ("2026-10-12",))
        self.assertEqual({r["adjustment"] for r in rows}, {"raw", "all"})
        self.assertTrue(all(len(r["sha"]) == 64 for r in rows))
        h.tick(16, 31)
        job = h.decider.jobs[0]["jobs"]
        mine_job = next(j for j in job if j["key"] == inst.id)
        inputs = mine_job["inputs"]
        self.assertEqual((inputs["day"], inputs["needs"].symbols, inputs["budget"]), (MONDAY, ("SPY",), 500.0))
        self.assertEqual([p["lid"] for p in inputs["positions"]], [mine.lid])
        self.assertEqual(inputs["positions"][0]["mark"], float(h.market.bar_rows["raw"]["SPY"][-1]["c"]))
        self.assertEqual(len(inputs["raw"]["SPY"]), 12)
        intents = h.intents(instance=inst.id)
        planned = [(i.kind, i.symbol, i.at, i.exec_day, i.lid) for i in intents if i.status == "planned"]
        self.assertEqual(planned, [("buy", "SPY", "close", "2026-10-13", None), ("sell", "SPY", "open", "2026-10-13", mine.lid)])
        refused = [i.why for i in intents if i.status == "refused"]
        self.assertEqual(len(refused), 6)
        self.assertTrue(any("not one of the program's NEEDS" in w for w in refused))
        self.assertTrue(any(f"lot {theirs.lid!r}" in w or f"lot {theirs.lid}" in w for w in refused))
        self.assertTrue(all(i.ctx_sha == "c" * 64 and len(i.bars_sha or "") == 64 for i in intents))
        self.assertEqual(h.book._instance(inst.id).last_decided_day, "2026-10-12")
        self.assertEqual(h.state.get("eq_decide")["status"], "done")
        h.tick(16, 40)
        self.assertEqual(len(h.decider.jobs), 1)                            # once a session
        # Its rejects reach the next ctx.
        h.decide_setup(TUESDAY, symbols=("SPY", "QQQ"))
        h.decider.plans[inst.id] = []
        h.tick(16, 31, day=TUESDAY)
        nxt = next(j for j in h.decider.jobs[-1]["jobs"] if j["key"] == inst.id)["inputs"]
        self.assertEqual(len(nxt["rejects"]), 6)

    def test_a_missing_bar_waits_then_fails_the_decide(self):
        h = self.harness()
        inst = self.setup_decide(h)
        h.market.bar_rows["raw"]["SPY"] = h.market.bar_rows["raw"]["SPY"][:-1]      # no bar for Monday yet
        h.tick(16, 31)
        self.assertEqual(h.decider.jobs, [])
        h.tick(17, 1)                                                        # its grace passed
        self.assertEqual(h.book._instance(inst.id).failed_decides, 1)
        self.assertIn("no bar of SPY", h.book._instance(inst.id).why)

    def test_max_hold_exits_at_the_next_open(self):
        h = self.harness()
        inst = self.setup_decide(h, needs={"symbols": ["SPY"], "history": 5, "max_hold_sessions": 2})
        old = h.lot(inst, "SPY", "0.4", "590", opened=FRIDAY)               # held 1 session at Monday's close
        young = h.lot(inst, "SPY", "0.4", "590", opened=MONDAY)
        h.tick(16, 31)
        exits = h.intents(kind="house_exit")
        self.assertEqual([(e.lid, e.tag, e.exec_day, e.at) for e in exits], [(old.lid, "max_hold", "2026-10-13", "open")])
        self.assertEqual(h.book._instance(inst.id).max_hold, 2)
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(old.lid).reason, "max_hold")
        self.assertEqual(h.book._lot(young.lid).status, "open")

    def test_a_retired_program_exits_and_never_decides(self):
        h = self.harness()
        inst = self.setup_decide(h, rows=[family_row("someone-else")])
        h.families.rows.pop(inst.family)
        h.instance("someone-else")
        lot = h.lot(inst, "SPY", "0.4", "590")
        h.tick(16, 31)
        retired = h.book._instance(inst.id)
        self.assertIsNotNone(retired.retired_at)
        self.assertTrue(retired.why.startswith("retired"))
        self.assertEqual(h.decider.drops, [inst.id])
        self.assertNotIn(inst.id, [j["key"] for j in h.decider.jobs[0]["jobs"]])
        self.assertEqual([(e.lid, e.tag) for e in h.intents(kind="house_exit")], [(lot.lid, "retired")])

    def test_an_unreadable_store_retires_nobody(self):
        h = self.harness()
        inst = self.setup_decide(h)
        h.lot(inst, "SPY", "0.4", "590")
        h.families.last_error = "OperationalError: database is locked"
        h.tick(16, 31)
        self.assertIsNone(h.book._instance(inst.id).retired_at)
        self.assertEqual(h.intents(kind="house_exit"), [])
        self.assertEqual(len(h.decider.jobs), 1)

    def test_an_edm1_demotion_is_sticky_and_exits(self):
        h = self.harness()
        inst = self.setup_decide(h)
        lot = h.lot(inst, "SPY", "0.4", "590")
        with mock.patch.object(B, "next_band", lambda row, record, table, *, seat_free, sticky=None:
                               ("candidate", "EDM1: the summed returns crossed the band")):
            h.tick(16, 31)
        self.assertEqual(h.families.moves, [("seed-overnight-spy", "candidate", "EDM1: the summed returns crossed the band")])
        self.assertTrue(h.book._instance(inst.id).why.startswith("demoted"))
        self.assertIn(inst.id, h.state.get("eq_sticky"))
        self.assertEqual([(e.lid, e.tag) for e in h.intents(kind="house_exit")], [(lot.lid, "demoted")])

    def test_a_candidate_with_a_seat_reaches_probe(self):
        h = self.harness()
        h.families.rows = {"seed-overnight-spy": family_row(band="candidate")}
        h.decide_setup(MONDAY)
        seen = []

        def next_band(row, record, table, *, seat_free, sticky=None):
            seen.append((row["band"], seat_free, record.n, sticky))
            return ("probe", "passed its look; a seat is free") if row["band"] == "candidate" else (row["band"], "")

        with mock.patch.object(B, "next_band", next_band):
            h.tick(16, 31)
        self.assertEqual(seen, [("candidate", True, 0, None)])
        inst = h.book._instance("seed-overnight-spy@1:r")
        self.assertEqual((inst.band, inst.lane, inst.seeded), ("probe", "beta", True))
        self.assertEqual(h.state.get("eq_band_since")[inst.id], {"band": "probe", "day": "2026-10-12"})
        self.assertEqual(len(h.decider.jobs), 1)

    def test_two_failed_decides_exit_the_programs_lots(self):
        h = self.harness()
        inst = self.setup_decide(h)
        lot = h.lot(inst, "SPY", "0.4", "590")
        h.decider.fail = True
        h.tick(16, 31)
        self.assertEqual(h.book._instance(inst.id).failed_decides, 1)
        self.assertEqual(h.intents(kind="house_exit"), [])
        h.decide_setup(TUESDAY, symbols=("SPY",))
        h.tick(16, 31, day=TUESDAY)
        self.assertEqual(h.book._instance(inst.id).failed_decides, 2)
        self.assertEqual([(e.lid, e.tag, e.exec_day) for e in h.intents(kind="house_exit")],
                         [(lot.lid, "house", "2026-10-14")])
        h.decider.fail = False
        h.decide_setup(WEDNESDAY, symbols=("SPY",))
        h.tick(16, 31, day=WEDNESDAY)
        self.assertEqual(h.book._instance(inst.id).failed_decides, 0)

    def test_a_catch_up_decide_after_a_restart(self):
        h = self.harness()
        inst = self.setup_decide(h)
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        h.book = h.new_book()                                               # no tick on Monday evening
        h.tick(8, 0, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decide")["day"], "2026-10-12")
        self.assertEqual([(i.kind, i.exec_day) for i in h.intents(status="planned")], [("buy", "2026-10-13")])
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.venue.sent[0]["side"], "buy")

    def test_no_decide_when_the_lane_is_off_and_holds_nothing(self):
        h = self.harness(table=equity_table(enabled=False))
        self.setup_decide(h)
        h.tick(16, 31)
        self.assertEqual((h.decider.jobs, h.market.bar_calls), ([], []))
        self.assertEqual(h.state.get("eq_decide")["status"], "idle")


class BandRecord(BookTest):
    def closed_lot(self, h: Harness, inst: L.Instance, cash: str, *, opened=FRIDAY, exit_day=MONDAY, probe=True):
        lot = h.lot(inst, "SPY", "0.5", "600", opened=opened, probe=probe)
        lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), D(cash), exit_day.isoformat(), \
            at(exit_day, 9, 31)
        h.book._save_lot(lot)
        return lot

    def test_the_record_the_band_rules_read(self):
        h = self.harness()
        inst = h.instance()
        win = self.closed_lot(h, inst, "6")
        loss = self.closed_lot(h, inst, "-3", probe=False)
        h.families.twin_rows = {f"eq:{win.lid}": {"status": "priced", "gap_bp": 4.0},
                                f"eq:{loss.lid}": {"status": "no_bar"}}
        h.state.put("eq_band_since", {inst.id: {"band": "probe", "day": "2026-10-05"}})
        for day, close in (("2026-10-08", "100"), ("2026-10-12", "102")):
            h.state.execute("INSERT INTO eq_bars(day, symbol, adjustment, c, fetched_at, sha) VALUES(?,?,?,?,0,'x')",
                            (day, "SPY", "all", close))
        record = h.book._record_of(inst.family, inst.version, {"validation_r_sd": 0.3})
        self.assertEqual((record.n, record.returns), (2, (6 / 300, -3 / 300)))
        self.assertEqual((record.pnl, record.realized_net, record.probe_sessions), (D("3"), D("6"), 5))
        self.assertEqual((record.twin_gaps_bp, record.validation_r_sd), ((4.0,), 0.3))
        # Two lots of $300 held one session each over a span of two sessions: $300 held, 2% from Thursday's close.
        self.assertEqual(record.bh_pnl, D("300") * (D("102") / D("100") - 1))
        h.state.execute("DELETE FROM eq_bars WHERE day='2026-10-08'")
        self.assertIsNone(h.book._record_of(inst.family, inst.version, None).bh_pnl)

    def test_a_full_roster_has_no_seat(self):
        h = self.harness()
        h.families.rows = {f"live-{i}": family_row(f"live-{i}") for i in range(3)}
        h.families.rows["waiting"] = family_row("waiting", band="candidate")
        h.decide_setup(MONDAY)
        seats = {}

        def next_band(row, record, table, *, seat_free, sticky=None):
            seats[row["family"]] = seat_free
            return row["band"], "unchanged"

        with mock.patch.object(B, "next_band", next_band):
            h.tick(16, 31)
        self.assertEqual(seats, {"live-0": True, "live-1": True, "live-2": True, "waiting": False})

    def test_a_sized_program_sizes_on_its_own_sleeve_and_is_never_a_probe_open(self):
        h = self.harness()
        it = h.intent(h.instance(band="sized"), "buy", symbol="SPY", share="0.5")
        h.tick(9, 31)
        self.assertEqual(SIZED[-1].sleeve_equity, D("1000.00"))             # money's sized share (0.50 stubbed) x E
        self.assertFalse(h.lots()[0].probe)
        self.assertFalse(h.orders()[0].probe)
        self.assertEqual(h.get_intent(it.iid).status, "sent")


class Audit(BookTest):
    def decided(self) -> tuple[Harness, L.Intent]:
        h = self.harness()
        h.families.rows = {"seed-overnight-spy": family_row()}
        inst = h.instance()
        h.decide_setup(MONDAY)
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        h.tick(16, 31)
        return h, h.intents(kind="buy")[0]

    def test_the_same_bars_pass(self):
        h, buy = self.decided()
        for row in h.market.bar_rows["all"]["SPY"]:                         # an ex-date after Monday rescales "all"
            for k in ("o", "h", "l", "c"):
                row[k] = round(row[k] * 0.98, 6)
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["audit"], "ok")
        self.assertEqual(h.get_intent(buy.iid).status, "planned")

    def test_a_mismatch_cancels_the_decisions_buys(self):
        h, buy = self.decided()
        h.market.bar_rows["raw"]["SPY"][-1]["c"] += 1.0
        h.tick(8, 31, day=TUESDAY)
        self.assertEqual(h.state.get("eq_decision")["audit"], "mismatch")
        self.assertEqual(h.get_intent(buy.iid).status, "canceled")
        self.assertEqual(h.book._instance("seed-overnight-spy@1:r").failed_decides, 1)
        self.assertEqual({r["audit"] for r in h.state.rows("SELECT audit FROM eq_bars WHERE day='2026-10-12'")},
                         {"mismatch"})
        self.assertIn("2026-10-12", h.state.get("eq_bars_audit"))
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.venue.sent, [])


# ------------------------------------------------------------------------------------------------- the rest
class Exports(BookTest):
    def test_a_closed_lot_reaches_the_forward_record_once(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.tick(9, 31)
        h.tick(9, 32)
        rows = h.families.forward_rows("seed-overnight-spy")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        cash = D("-295") + D("0.5") * D("599.90") - D("0.01")
        self.assertEqual({k: row[k] for k in ("id", "version", "day", "opened_day", "symbol", "class", "lane", "pnl",
                                              "max_loss", "notional", "fees", "div", "hold_sessions", "entry_at",
                                              "exit_at", "probe", "twin_key", "source")},
                         {"id": f"eq-{lot.lid}", "version": 1, "day": "2026-10-12", "opened_day": "2026-10-09",
                          "symbol": "SPY", "class": "etf", "lane": "beta", "pnl": float(cash), "max_loss": 295.0,
                          "notional": 295.0, "fees": 0.01, "div": 0.0, "hold_sessions": 1, "entry_at": "close",
                          "exit_at": "open", "probe": True, "twin_key": f"eq:{lot.lid}", "source": "real"})
        self.assertAlmostEqual(row["return"], float(cash) / 295.0)
        h.tick(9, 33)
        self.assertEqual(len(h.families.forward_rows("seed-overnight-spy")), 1)
        self.assertEqual(h.state.rows("SELECT lid FROM eq_exports")[0]["lid"], lot.lid)


class Operations(BookTest):
    def test_flatten_queues_every_lot_through_the_normal_path(self):
        h = self.harness()
        inst = h.instance()
        old, young = h.lot(inst, "SPY", "0.5", "590"), h.lot(inst, "QQQ", "0.5", "490", opened=MONDAY)
        h.clock.set(at(MONDAY, 12, 0))
        self.assertEqual(h.book.flatten("the rollback"), 2)
        self.assertEqual(h.book.flatten("again"), 0)                        # each lot once
        h.tick(12, 1)
        self.assertEqual(h.book._lot(old.lid).reason, "flatten")
        self.assertEqual(h.book._lot(young.lid).status, "open")             # min hold: tomorrow's open
        self.assertTrue(all(b["type"] == "limit" for b in h.venue.sent))
        h.tick(16, 0)
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(young.lid).reason, "flatten")

    def test_health(self):
        h = self.harness()
        inst = h.instance()
        h.lot(inst, "SPY", "0.5", "590")
        h.tick(9, 26)
        health = h.book.health()
        for key in ("enabled", "frozen", "lots", "working", "orders_today", "phase", "proof", "programs", "last_decide",
                    "last_bars"):
            self.assertIn(key, health)
        self.assertEqual((health["lots"], health["phase"], health["programs"][0]["instance"]), (1, "preopen", inst.id))
        self.assertEqual(health["proof"], {"passed": True})

    def test_no_real_account_keeps_the_tables_only(self):
        h = self.harness()
        book = L.EquityBook(h.state, None, h.market, h.table, h.families, decider=h.decider)
        self.assertEqual(book.tick(at(MONDAY, 9, 31), account_row=None, positions=None, open_orders=None,
                                   real_block=lambda opening=True: None, killed=lambda: False),
                         {"state": "no real account"})

    def test_a_failing_step_never_ends_the_minute(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        with mock.patch.object(L.EquityBook, "_activities", side_effect=RuntimeError("boom")):
            out = h.tick(9, 31)
        self.assertTrue(any("activities" in e for e in out["errors"]))
        self.assertEqual(len(h.venue.sent), 1)

    def test_the_stock_proof_is_stepped_until_it_passes(self):
        h = self.harness()
        h.proof.ok = False
        h.tick(15, 55)
        h.tick(15, 56)
        self.assertEqual(h.proof.steps, 2)
        h.proof.ok = True
        h.tick(15, 57)
        self.assertEqual(h.proof.steps, 2)


class TheStagedProof(BookTest):
    """A10.1: the proof trades in the book's own OPEN window and goes first in it; its BUY stage gates every real buy,
    its SELL stage every real sale, and a failed SELL stage stops new real buys until it passes."""

    def test_the_proof_steps_first_in_the_books_own_window(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        sent_when_stepped = []
        step = h.proof.step

        def first(now, *, market, window=None):
            sent_when_stepped.append(len(h.venue.sent))
            return step(now, market=market, window=window)

        h.proof.step = first
        h.tick(9, 31)
        self.assertEqual(sent_when_stepped, [0], "stepped before the windows send anything")
        _, window = h.proof.seen[-1]
        self.assertEqual(window, S.moments(MONDAY, h.book._offsets()), "the book's own moments of the day")

    def test_real_sales_wait_for_the_sell_stage(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        h.tick(9, 31)
        h.tick(9, 33)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("SELL stage", h.get_intent(sale.iid).why)
        self.assertEqual(h.book._lot(lot.lid).status, "open", "the lot stays held")
        h.proof.sell = True
        h.tick(9, 34)
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"])
        h.tick(9, 35)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_buys_wait_for_the_buy_stage_and_stop_on_a_failed_sell_stage(self):
        h = self.harness()
        inst = h.instance()
        buy = h.intent(inst, "buy", symbol="SPY", share="0.2")
        h.proof.ok, h.proof.sell = False, False
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("BUY stage", h.get_intent(buy.iid).why)
        h.proof.ok = True                                       # stage BUY passed, SELL still to come: buys may go
        h.proof.failed = "the stock paper proof's SELL stage failed on 2026-09-28: the round trip ended without " \
                         "activity_witness"
        h.tick(9, 32)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("new real equity buys stop", h.get_intent(buy.iid).why)
        h.proof.failed = ""
        h.tick(9, 33)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"])



class TheBrokersFees(BookTest):
    """The Done meter's finality (league/ops/dlane_report.py) waits for each equity close's broker fees: the book posts
    the venue's REG and TAF rows of the exit day to that day's equity sales, pro rata by proceeds, and marks the lot's
    `info.fee_basis` "broker"; an option's fee rows and order-attributed rows are never an equity lot's."""

    def sold_monday(self, h, *symbols):
        lots = []
        for symbol in symbols:
            inst = h.instance(f"fam-{symbol.lower()}")
            lot = h.lot(inst, symbol, "0.5", "590")
            h.intent(inst, "sell", symbol=symbol, lid=lot.lid)
            lots.append(lot)
        for mm in range(31, 31 + 2 * len(symbols)):
            h.tick(9, mm)
        for lot in lots:
            self.assertEqual(h.book._lot(lot.lid).status, "closed")
        return lots

    def test_the_days_fee_rows_are_posted_pro_rata_and_the_lot_is_final(self):
        h = self.harness()
        spy, qqq = self.sold_monday(h, "SPY", "QQQ")
        before = {x.lid: h.book._lot(x.lid) for x in (spy, qqq)}
        self.assertEqual({x.fees for x in before.values()}, {D("0.01")}, "the book's estimate at the fill")
        proceeds = {lid: sum((D(r["qty"]) * D(r["px"]) for r in h.state.rows(
            "SELECT qty, px FROM eq_fills WHERE lid=?", (lid,))), D(0)) for lid in before}
        total = sum(proceeds.values())
        h.venue.activity_rows = [
            {"id": "f1", "activity_type": "FEE", "date": "2026-10-12", "net_amount": "-0.03",
             "description": f"REG fee for proceed of ${total} of 2 trades"},
            {"id": "f2", "activity_type": "FEE", "date": "2026-10-12", "net_amount": "-0.02",
             "description": "TAF fee for proceed of 2 trades"},
            {"id": "f3", "activity_type": "FEE", "date": "2026-10-12", "net_amount": "-0.40",
             "description": "OPT TAF fee for proceed of 4 contracts"},
            {"id": "f4", "activity_type": "FEE", "date": "2026-10-12", "net_amount": "-1.00", "order_id": "x",
             "description": "REG fee"}]
        h.tick(9, 50)
        self.assertNotIn("fee_basis", h.book._lot(spy.lid).info, "not before the exit day has ended")
        h.tick(9, 31, day=TUESDAY)
        for lid, lot in before.items():
            now = h.book._lot(lid)
            share = proceeds[lid] / total
            want = (D("0.05") * share).quantize(D("0.0001"), rounding=ROUND_CEILING)
            self.assertEqual((now.info["fee_basis"], now.fees, now.info["fees_estimate"]), ("broker", want, "0.01"))
            self.assertEqual(now.cash, lot.cash + lot.fees - want)
        self.assertEqual([p for k, p in h.events if k == "equity.fees_posted"], [{"lots": 2}])
        fee_reads = lambda: [c for c in h.venue.activity_calls if c[0] == ("FEE",)]  # noqa: E731
        calls = len(fee_reads())
        h.tick(9, 50, day=TUESDAY)
        self.assertEqual(len(fee_reads()), calls, "nothing left to post: no more fee reads")

    def test_a_row_stating_more_proceeds_than_the_books_keeps_the_rest_for_another_sale(self):
        h = self.harness()
        [spy] = self.sold_monday(h, "SPY")
        mine = sum((D(r["qty"]) * D(r["px"]) for r in h.state.rows("SELECT qty, px FROM eq_fills WHERE lid=?",
                                                                     (spy.lid,))), D(0))
        h.venue.activity_rows = [{"id": "f1", "activity_type": "FEE", "date": "2026-10-12", "net_amount": "-0.10",
                                  "description": f"REG fee for proceed of ${mine * 4} of 2 trades"}]
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(spy.lid).fees, D("0.0250"), "a quarter of the day's proceeds: a quarter of it")

    def test_no_fee_row_keeps_the_estimate_and_tells_the_owner_once_after_five_sessions(self):
        h = self.harness()
        [spy] = self.sold_monday(h, "SPY")
        h.tick(9, 31, day=TUESDAY)
        self.assertNotIn("fee_basis", h.book._lot(spy.lid).info)
        self.assertFalse([a for a in h.alerts if "fee row" in a[1]])
        later = dt.date(2026, 10, 19)
        h.tick(9, 31, day=later)
        h.tick(10, 31, day=later)
        told = [a for a in h.alerts if "fee row" in a[1]]
        self.assertEqual(len(told), 1)
        self.assertIn("provisional", told[0][1])
        self.assertEqual(h.book._lot(spy.lid).fees, D("0.01"))


if __name__ == "__main__":
    unittest.main()
