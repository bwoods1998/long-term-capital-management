"""The `economics` job (each trading day, ten minutes after the close): the one-cutoff close economics, on the House.

The operator's laptop pipeline (`economics_daily.sh`: a House read over exec, Sail's box billing, the PR #432 reporter
`league.project_economics.report`, and a render) as one House job, with the same rules and the same arithmetic:

- costs from T0 2026-09-26T06:23:14Z and options cash from the financial basis 06:25:30Z (the Sept 26 reset), both to
  the cutoff (the session's close);
- realized options P&L = closed real positions' cash (fees in, broker-posted fee corrections applied once), all routes,
  + the broker's order-less option regulatory fees - an estimate of the ones not posted yet (a liability);
- deposits, withdrawals and equity changes are never P&L; open positions are listed apart at conservative marks (the
  bid of a long leg, the ask of a short one, floored at intrinsic value at the cutoff);
- every cost on its stated basis, the larger where two exist: Sail (settled model requests + app-scoped box billing,
  vs the balance meter), Claude (the gateway's meter less calls after the cutoff, vs the swarm's record), OpenAI
  (booked), ThetaData and Alpaca market data pro rata, TypeSafe as an upper bound, declared externals from
  `<state>/ops.json` `economics.external`; unknown costs are listed, never zero; one Net.

READ-ONLY: every SQLite open is `mode=ro` (`guard.readonly()` over the release's own readers too), the gateway is
called with GET only, and Sail with GET only. Output, private: `<state>/economics/<YYYYMMDD>-close/` (`summary.json`,
`summary.md`, `receipts/`, `project-economics/`), mode 0600 in 0700 directories. `summary.json` also carries `p30`,
the trailing-30-day realized options P&L (by close day, regulatory fees by posting date) that the budget rule reads.
`render` is the laptop's arithmetic unchanged (a test holds it to the laptop's numbers on the same receipts).
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import time
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import guard
from .context import read_json, write_json, write_text

T0 = "2026-09-26T06:23:14Z"
FS = "2026-09-26T06:25:30Z"
NY = ZoneInfo("America/New_York")
CENT = Decimal("0.01")
ZERO = Decimal(0)
P30_DAYS = 30
ROUTES = ("calibration", "tuition", "house_test", "incubator", "d2_real", "house_other", "agent_other")
ROUTE_WORDS = {"calibration": "Calibration (D3, execution evidence only)", "tuition": "Tuition (D2)", "house_test": "House live test",
               "incubator": "Incubator", "d2_real": "D2 Probe/Sized", "house_other": "Other House family", "agent_other": "Other agent route"}
UNKNOWN_EXTERNAL = ("Codex subscription (engineering)", "Claude Code / Claude subscription (engineering)",
                    "Cloudflare (Workers plan for the gateway and the site)", "Domain (the site's)", "GitHub (plan, Actions minutes)",
                    "TypeSafe/Jev prepaid credit beyond the gateway meter")
SAIL_WINDOWS = ("t0-cutoff", "pre-meter", "last24h", "last4h", "after-cutoff")


# ------------------------------------------------------------------------------------------------ helpers
def D(value: Any) -> Decimal:
    return ZERO if value in (None, "") else Decimal(str(value))


def c2(value: Decimal) -> Decimal:
    out = Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    return out if out else Decimal("0.00")


def usd(value: Any) -> str | None:
    return None if value is None else format(c2(D(value)), ".2f")


def ep(text: Any) -> float:
    return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()


def ep_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return ep(value)
    except ValueError:
        return None


def zulu(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_us(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def plain(value: Any) -> Any:
    """What a JSON file of `value` reads back as (the laptop's receipts were files: the render reads that shape)."""
    return json.loads(json.dumps(jsonable(value), default=str, sort_keys=True))


def cutoff_of(due_at: float) -> float:
    """The cutoff for an occurrence due at `due_at`: the close of New York's session that day (an early close too),
    else the latest regular close (16:00 New York on a weekday) already past."""
    from ltcm.data import DataError, previous_session, to_datetime, us_equity_session

    try:
        session = us_equity_session(dt.datetime.fromtimestamp(due_at, dt.timezone.utc))
        if session is not None and to_datetime(session.close_at).timestamp() <= due_at:
            return to_datetime(session.close_at).timestamp()
        session = previous_session(dt.datetime.fromtimestamp(due_at, dt.timezone.utc))
        if session is not None:
            return to_datetime(session.close_at).timestamp()
    except DataError:
        pass
    day = dt.datetime.fromtimestamp(due_at, NY).date()
    for _ in range(8):
        close = dt.datetime.combine(day, dt.time(16), tzinfo=NY).timestamp()
        if day.weekday() < 5 and close <= due_at:
            return close
        day -= dt.timedelta(days=1)
    raise ValueError("no close found")


# ------------------------------------------------------------------------------------------------ the House read
class _Broker:
    """The shape `league.account_activity` reads through (`_call`), GET only, through the gateway's /v1/alpaca route."""

    def __init__(self, gateway: Any):
        self.gateway = gateway

    def _call(self, method: str, path: str, params: Any = None, what: Any = None) -> Any:
        if method != "GET":
            raise PermissionError("economics is read-only: refused " + method)
        return self.gateway.get("/v1/alpaca" + path, params)


def route_of(position: Mapping[str, Any]) -> str:
    """calibration | house_test | incubator | tuition | d2_real | house_other | agent_other (instance suffix first)."""
    from .. import trading_profit as TP

    family, instance = str(position.get("family") or ""), str(position.get("instance") or "")
    if instance.endswith(":i") and not family.startswith("house:"):
        return "incubator"
    if family == TP.CALIBRATION_FAMILY or instance.endswith(":c"):
        return "calibration"
    if family == TP.HOUSE_TEST_FAMILY or instance.endswith(":h"):
        return "house_test"
    if family.startswith("house:"):
        return "house_other"
    if instance.endswith(":t") or position.get("tuition"):
        return "tuition"
    if instance.endswith(":r"):
        return "d2_real"
    return "agent_other"


def collect_house(root: Path, cutoff: str, gateway: Any, *, now: float, config: Mapping[str, Any]) -> dict[str, Any]:
    """The laptop's House read (`house_collect.py`) as a function: the book, the broker and the library receipt as they
    stood at `cutoff`, costs and meters, the account now. Each section that cannot be read is an error, never a zero."""
    from .. import account_activity as AA
    from .. import project_economics as PE
    from .. import trading_profit as TP

    root = Path(root)
    CUT, T0E, FSE = ep(cutoff), ep(T0), ep(FS)
    if CUT < FSE or CUT > now:
        raise ValueError("the cutoff must be a UTC time after the financial basis and not in the future")
    cut_day_ny = dt.datetime.fromtimestamp(CUT, NY).date().isoformat()
    out: dict[str, Any] = {"schema": "ltcm-econ-close-house-1", "cutoff": cutoff, "errors": {}, "gateway_gets": [],
                           "collected_at": iso_us(now), "release": str(Path(__file__).resolve().parents[2]),
                           "performance": config.get("performance")}
    broker = _Broker(gateway)

    def gw(path: str, params: Any = None) -> Any:
        out["gateway_gets"].append(path)
        return gateway.get(path, params)

    def ro(name: str) -> Any:
        return guard.connect_ro(root / name)

    def section(name: str, fn: Any) -> None:
        try:
            out[name] = jsonable(fn())
        except Exception as exc:  # noqa: BLE001 - a section that cannot be read is an error, never a zero
            out["errors"][name] = type(exc).__name__ + ": " + str(exc)[:400]

    def cut_orders(orders: list) -> list:
        kept = []
        for o in orders:
            if float(o.get("placed_at") or 0) > CUT:
                continue
            o = dict(o)
            if float(o.get("updated_at") or 0) > CUT and o.get("status") not in ("pending", "unknown"):
                o["status_now"], o["status"] = o["status"], "pending"
                o["updated_at"] = CUT
            kept.append(o)
        return kept

    def cut_positions(positions: list, fills: list, action: Mapping[int, Any]) -> list:
        kept = []
        for p in positions:
            if float(p.get("opened_at") or 0) > CUT:
                continue
            p = dict(p)
            if p.get("status") != "open" and p.get("closed_at") is not None and float(p["closed_at"]) > CUT:
                cash = Decimal(0)
                for f in fills:
                    if f.get("pid") is not None and int(f["pid"]) == int(p["pid"]):
                        sign = -1 if action.get(int(f["oid"])) == "open" else 1
                        cash += sign * Decimal(str(f["value"])) * 100 * int(f["qty"]) - Decimal(str(f["fees"]))
                p.update(status_now=p["status"], status="open", closed_at=None, qty=p.get("opened_qty"), cash=float(cash))
            kept.append(p)
        return kept

    start_at = (out.get("performance") or {}).get("start_at") or FS
    rb = AA.read_book(root, start_at)
    if (root / "live.sqlite").exists():
        recon = guard.read(root / "live.sqlite", lambda db: json.loads(
            ((db.execute("SELECT value FROM kv WHERE key='recon'").fetchone() or ["{}"])[0]) or "{}"))
    else:
        recon = {}
    action = {int(o["oid"]): o.get("action") for o in rb["every_order"]}
    fills_c = [f for f in rb["fills"] if float(f["at"]) <= CUT]
    cb = {"orders": cut_orders(rb["orders"]), "fills": fills_c, "positions": cut_positions(rb["positions"], fills_c, action),
          "external": rb["external"], "every_order": cut_orders(rb["every_order"]),
          "every_position": cut_positions(rb["every_position"], fills_c, action), "orders_from": rb["orders_from"]}
    book_now = {"positions": rb["every_position"], "orders": rb["every_order"], "fills": rb["fills"]}
    cbook = {"positions": cb["every_position"], "orders": cb["every_order"], "fills": fills_c, "recon": recon}
    out["book_changes_after_cutoff"] = {
        "fills": sum(float(f["at"]) > CUT for f in book_now["fills"]),
        "orders_placed": sum(float(o.get("placed_at") or 0) > CUT for o in book_now["orders"]),
        "orders_changed": sum(float(o.get("updated_at") or 0) > CUT for o in book_now["orders"]),
        "positions_opened": sum(float(p.get("opened_at") or 0) > CUT for p in book_now["positions"]),
        "positions_closed": sum(p.get("closed_at") is not None and float(p["closed_at"]) > CUT for p in book_now["positions"])}
    out["recon_now"] = recon

    def book() -> dict:
        rows = []
        for p in cbook["positions"]:
            if float(p.get("opened_at") or 0) < FSE:
                continue
            rows.append({"pid": int(p["pid"]), "family": p.get("family"), "instance": p.get("instance"), "route": route_of(p),
                         "type": p.get("type"), "root": p.get("root"), "legs": json.loads(p.get("legs") or "[]"),
                         "qty": int(p.get("qty") or 0), "opened_qty": int(p.get("opened_qty") or 0), "entry": p.get("entry"),
                         "fees": p.get("fees"), "cash": p.get("cash"), "status": p.get("status"), "status_now": p.get("status_now"),
                         "opened_at": iso_us(float(p["opened_at"])),
                         "closed_at": iso_us(float(p["closed_at"])) if p.get("closed_at") else None,
                         "tuition": p.get("tuition"), "reason": p.get("reason")})
        pending = [o["oid"] for o in cbook["orders"] if o.get("status") in ("pending", "unknown")]
        statuses = {o.get("status") for o in cbook["orders"]}
        return {"positions": rows, "orders_at_cutoff": len(cbook["orders"]), "fills_at_cutoff": len(cbook["fills"]),
                "pending_orders_at_cutoff": pending,
                "orders_by_status_at_cutoff": {s: sum(o.get("status") == s for o in cbook["orders"]) for s in statuses}}

    section("book", book)
    acts: list = []

    def broker_at_cutoff() -> dict:
        every = AA.activities_after(broker, FS)
        orders = AA.orders_after(broker, iso_us(FSE - 86400))
        known = {str(o["id"]) for o in orders if (ep_or_none(o.get("submitted_at")) or 0) <= CUT}
        for o in orders:
            for leg in o.get("legs") or []:
                if (ep_or_none(o.get("submitted_at")) or 0) <= CUT and leg.get("id"):
                    known.add(str(leg["id"]))
        kept, later = [], []
        for a in every:
            kind = str(a.get("activity_type") or "")
            when = ep_or_none(a.get("transaction_time"))
            if kind == "FILL":
                (kept if when is not None and when <= CUT else later).append(a)
            elif kind == "FEE" and a.get("order_id") and str(a["order_id"]) in known:
                kept.append(a)
            elif str(a.get("date") or "9999") <= cut_day_ny:
                kept.append(a)
            else:
                later.append(a)
        acts[:] = kept
        vorders = [o for o in orders if (ep_or_none(o.get("submitted_at")) or 0) <= CUT]
        reading = AA.classify(kept, vorders, cb, now=CUT, shares_held=lambda: AA.shares_held(broker))
        by_type: dict[str, Any] = {}
        for a in kept:
            k = str(a.get("activity_type"))
            by_type.setdefault(k, {"n": 0, "net_amount": Decimal(0)})
            by_type[k]["n"] += 1
            by_type[k]["net_amount"] += Decimal(str(a.get("net_amount") or 0))
        broker_opt_cash = Decimal(0)
        for a in kept:
            if a.get("activity_type") == "FILL" and AA.is_option(str(a.get("symbol") or "")):
                q, px = Decimal(str(a["qty"])), Decimal(str(a["price"]))
                broker_opt_cash += (q * px * 100) if a.get("side") == "sell" else -(q * px * 100)
        act_of = {int(o["oid"]): o.get("action") for o in cbook["orders"]}
        book_fill_cash = sum(((Decimal(str(f["value"])) * 100 * int(f["qty"])) * (-1 if act_of.get(int(f["oid"])) == "open" else 1)
                              for f in cbook["fills"] if f.get("pid") is not None), Decimal(0))
        funding = [{k: a.get(k) for k in ("id", "activity_type", "net_amount", "date", "transaction_time")} for a in kept
                   if a.get("activity_type") in AA.FUNDING]
        return {"as_of": cutoff, "read_at": iso_us(time.time()), "start_at": start_at,
                "activities_total": len(every), "activities_at_cutoff": len(kept), "activities_after_cutoff": len(later),
                "activities_after_cutoff_types": sorted({str(a.get("activity_type")) for a in later}),
                "venue_orders_at_cutoff": len(vorders), "by_type": by_type,
                "broker_option_fill_cash": broker_opt_cash, "book_option_fill_cash": book_fill_cash,
                "funding": funding, "funding_net": sum((Decimal(str(f["net_amount"] or 0)) for f in funding), Decimal(0)),
                "reading": reading}

    section("broker_at_cutoff", broker_at_cutoff)

    def regulatory() -> dict:
        import re

        rows, token = [], None
        for _ in range(50):
            params = {"after": FS, "direction": "asc", "page_size": 100}
            if token:
                params["page_token"] = token
            page = gw("/v1/alpaca/v2/account/activities/FEE", params) or []
            rows.extend(page)
            if len(page) < 100 or not page[-1].get("id"):
                break
            token = page[-1]["id"]
        fees = []
        for a in rows:
            if a.get("order_id") or str(a.get("date") or "9999") > cut_day_ny:
                continue
            d = str(a.get("description") or "")
            m = re.match(r"^(ORF|OPT TAF|OPT REG|CAT|TAF|REG|PTC)\b", d)
            n = re.search(r"of (\d+) (contracts|trades)", d)
            proceeds = re.search(r"of \$(\d+(?:\.\d+)?)", d)
            fees.append({"id": a.get("id"), "date": a.get("date"), "net_amount": a.get("net_amount"), "label": m.group(1) if m else "other",
                         "count": int(n.group(1)) if n else None, "proceeds": proceeds.group(1) if proceeds else None})
        volume: dict[str, Any] = {}
        for a in acts:
            if a.get("activity_type") != "FILL" or not AA.is_option(str(a.get("symbol") or "")):
                continue
            day = dt.datetime.fromtimestamp(ep(a["transaction_time"]), NY).date().isoformat()
            v = volume.setdefault(day, {"fills": 0, "contracts": 0, "sold_contracts": 0, "sell_proceeds": Decimal(0)})
            q = int(Decimal(str(a["qty"])))
            v["fills"] += 1
            v["contracts"] += q
            if a.get("side") == "sell":
                v["sold_contracts"] += q
                v["sell_proceeds"] += Decimal(str(a["qty"])) * Decimal(str(a["price"])) * 100
        return {"orderless_fees": fees, "option_volume_by_day": volume}

    section("regulatory_fees", regulatory)

    def marks() -> dict:
        found = {}
        for p in cbook["positions"]:
            if p.get("status") != "open" or float(p.get("opened_at") or 0) < FSE:
                continue
            legs = json.loads(p.get("legs") or "[]")
            qty = int(p.get("qty") or 0)
            symbols = [leg["symbol"] for leg in legs]
            snap = (gw("/v1/alpaca/v1beta1/options/snapshots", {"symbols": ",".join(symbols), "feed": "opra"}) or {}).get("snapshots") or {}
            bars = (gw(f"/v1/alpaca/v2/stocks/{p['root']}/bars", {"timeframe": "1Min", "start": iso_us(CUT - 900), "end": iso_us(CUT),
                                                                   "feed": "sip"}) or {}).get("bars") or []
            before = [b for b in bars if (ep_or_none(b.get("t")) or 0) + 60 <= CUT + 1e-6]
            spot = Decimal(str(before[-1]["c"])) if before else None
            conservative = mid = Decimal(0)
            intrinsic: Decimal | None = Decimal(0)
            leg_rows, fresh = [], True
            for leg in legs:
                q = (snap.get(leg["symbol"]) or {}).get("latestQuote") or {}
                bid, ask, qt = q.get("bp"), q.get("ap"), ep_or_none(q.get("t"))
                side, ratio = int(leg["side"]), int(leg.get("ratio") or 1)
                good = bid is not None and ask is not None and qt is not None and qt <= CUT and CUT - qt <= 3 * 86400 and 0 <= bid <= ask
                fresh = fresh and good
                strike = Decimal(str(leg["strike"]))
                iv = (max(Decimal(0), spot - strike) if leg.get("is_call") else max(Decimal(0), strike - spot)) if spot is not None else None
                if good:
                    conservative += side * ratio * Decimal(str(bid if side > 0 else ask))
                    mid += side * ratio * (Decimal(str(bid)) + Decimal(str(ask))) / 2
                intrinsic = None if iv is None or intrinsic is None else intrinsic + side * ratio * iv
                leg_rows.append({"symbol": leg["symbol"], "side": side, "ratio": ratio, "strike": leg["strike"], "is_call": leg.get("is_call"),
                                 "bid": bid, "ask": ask, "quote_at": q.get("t"), "quote_ok_for_cutoff": good})
            per = basis = None
            if fresh and intrinsic is not None:
                per, basis = max(conservative, intrinsic), ("bid/ask" if conservative >= intrinsic else "intrinsic floor")
            elif intrinsic is not None:
                per, basis = intrinsic, "intrinsic (no quote at or before the cutoff)"
            found[str(p["pid"])] = {"root": p["root"], "qty": qty, "spot_at_cutoff": spot, "spot_bar": before[-1]["t"] if before else None,
                                    "legs": leg_rows, "per_share": {"conservative_bid_ask": conservative if fresh else None,
                                                                    "mid": mid if fresh else None, "intrinsic": intrinsic, "mark": per},
                                    "mark_basis": basis, "value_usd": per * 100 * qty if per is not None else None,
                                    "mid_value_usd": mid * 100 * qty if fresh else None,
                                    "bid_ask_value_usd": conservative * 100 * qty if fresh else None}
        return found

    section("marks", marks)

    def trading() -> dict:
        reading = (out.get("broker_at_cutoff") or {}).get("reading")
        if reading is None:
            raise RuntimeError("no broker reading at the cutoff")
        closed = [p for p in cbook["positions"] if float(p.get("opened_at") or 0) >= FSE and p.get("status") == "closed"]
        rows = TP.position_rows(closed, cbook["orders"], {})
        book_value = {"as_of": cutoff, "pnl_usd": TP.total(closed, {}), "rows": rows}
        other = {k: reading[k] for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd", "unreconciled_usd")}
        other.update(fees_by_pid=reading["fees_by_pid"], blocking=reading["blocking"], as_of=cutoff)
        profit, table = TP.complete(book_value, other, at=cutoff)
        return {"closed_profit_convention": profit, "closed_rows": table["rows"] if table else None,
                "other": table["other"] if table else None, "unreconciled_usd": table["unreconciled_usd"] if table else None,
                "fees_by_pid": reading["fees_by_pid"], "blocking": reading["blocking"], "problems": reading["problems"]}

    section("trading", trading)

    def pe_state() -> dict:
        snaps: dict[str, Any] = {}

        def mem() -> Any:
            import sqlite3

            db = sqlite3.connect(":memory:")
            db.row_factory = sqlite3.Row
            return db

        def swarm_read(db: Any) -> tuple[list, dict]:
            rows = guard.rows(db, "SELECT seq, epoch, kind, usd, detail FROM spend ORDER BY seq")
            kv = {r["key"]: r["value"] for r in guard.rows(db, "SELECT key, value FROM kv WHERE key IN ('unsettled','claude_unsettled')")}
            return rows, kv

        rows, kv = guard.read(root / "swarm.sqlite", swarm_read)
        origins: dict[tuple, list] = {}
        for r in rows:
            if r["kind"] in ("claude", "openai"):
                d = json.loads(r["detail"] or "{}")
                if d.get("hold"):
                    origins.setdefault((r["kind"], str(d.get("request") or d["hold"])), []).append(r["epoch"])
        keep, late_settlements = [], {}
        for r in rows:
            if r["kind"] not in ("claude", "openai"):
                if r["epoch"] <= CUT:
                    keep.append({**r, "detail": None})
                continue
            if r["epoch"] <= CUT:
                keep.append(r)
                continue
            d = json.loads(r["detail"] or "{}")
            if d.get("settles") or d.get("settles_hold"):
                key = d.get("settles_hold") or d.get("request") or d.get("settles")
                admitted = origins.get((r["kind"], str(key))) or []
                if len(admitted) == 1 and admitted[0] <= CUT:
                    keep.append(r)
                    late_settlements[r["kind"]] = late_settlements.get(r["kind"], 0) + 1
        db = mem()
        db.execute("CREATE TABLE spend (seq INTEGER, epoch REAL, kind TEXT, usd REAL, detail TEXT)")
        db.executemany("INSERT INTO spend VALUES (:seq, :epoch, :kind, :usd, :detail)", keep)
        db.execute("CREATE TABLE kv (key TEXT, value TEXT)")
        for key, value in kv.items():
            try:
                items = json.loads(value or "{}")
                items = {k: v for k, v in items.items() if not isinstance(v, dict) or (ep_or_none(v.get("at")) or 0) <= CUT}
                value = json.dumps(items)
            except (ValueError, AttributeError):
                pass
            db.execute("INSERT INTO kv VALUES (?, ?)", (key, value))
        snaps["swarm.sqlite"] = db
        reqs = guard.read(root / "swarm-provider.sqlite", lambda s: guard.rows(
            s, "SELECT status, cost_usd, reserved_usd, error, created_at FROM requests WHERE julianday(created_at)<=julianday(?)", (cutoff,)))
        db = mem()
        db.execute("CREATE TABLE requests (status TEXT, cost_usd REAL, reserved_usd REAL, error TEXT, created_at TEXT)")
        db.executemany("INSERT INTO requests VALUES (:status, :cost_usd, :reserved_usd, :error, :created_at)", reqs)
        snaps["swarm-provider.sqlite"] = db
        led = guard.read(root / "ledger.sqlite", lambda s: guard.rows(
            s, "SELECT kind, at FROM ledger WHERE julianday(at)<=julianday(?) AND kind IN "
               "('provider.request','merton.pass','audit.verdict','credit.charge')", (cutoff,)))
        db = mem()
        db.execute("CREATE TABLE ledger (kind TEXT, at TEXT)")
        db.executemany("INSERT INTO ledger VALUES (:kind, :at)", led)
        snaps["ledger.sqlite"] = db
        db = mem()
        db.execute("CREATE TABLE positions (pid INTEGER, qty INTEGER, cash REAL, fees REAL, status TEXT, opened_at REAL, closed_at REAL)")
        db.executemany("INSERT INTO positions VALUES (:pid, :qty, :cash, :fees, :status, :opened_at, :closed_at)",
                       [{k: p.get(k) for k in ("pid", "qty", "cash", "fees", "status", "opened_at", "closed_at")} for p in cbook["positions"]])
        db.execute("CREATE TABLE orders (status TEXT, updated_at REAL)")
        db.executemany("INSERT INTO orders VALUES (:status, :updated_at)", [{k: o.get(k) for k in ("status", "updated_at")} for o in cbook["orders"]])
        db.execute("CREATE TABLE fills (at REAL)")
        db.executemany("INSERT INTO fills VALUES (?)", [(f["at"],) for f in cbook["fills"]])
        db.execute("CREATE TABLE kv (key TEXT, value TEXT)")
        db.execute("INSERT INTO kv VALUES ('recon', ?)", (json.dumps(cbook["recon"]),))
        snaps["live.sqlite"] = db

        @contextlib.contextmanager
        def snapshot(path: Any) -> Any:
            yield snaps[Path(path).name]

        original = PE.readonly
        PE.readonly = snapshot
        try:
            state = PE.collect(root, clock=lambda: CUT)
        finally:
            PE.readonly = original
            for db in snaps.values():
                db.close()
        reading = (out.get("broker_at_cutoff") or {}).get("reading")
        if reading is not None:
            state["sources"]["broker_activity"] = {
                "as_of": cutoff, "read_at": out["broker_at_cutoff"]["read_at"], "start_at": out["broker_at_cutoff"]["start_at"],
                "fees_by_pid": reading["fees_by_pid"], "blocking": reading["blocking"], "problems": reading["problems"],
                **{k: reading[k] for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd", "unreconciled_usd")}}
        else:
            state["sources"].pop("broker_activity", None)
            state["errors"].append("broker activity at the cutoff unavailable")
        state["collection_provenance"] = {
            "method": "league.project_economics.collect() over in-memory copies cut at the cutoff; clock = cutoff (the House's ops job)",
            "cutoff": cutoff, "collected_at": out["collected_at"], "deployed_release": out["release"],
            "late_settlements_kept": late_settlements,
            "broker_activity": "account_activity.classify() over GET activities/orders cut at the cutoff"}
        return state

    section("pe_state", pe_state)

    def costs() -> dict:
        res: dict[str, Any] = {}
        h = gw("/v1/health") or {}
        fr = dict(h.get("frontier") or {})
        res["gateway_health"] = {"at": iso_us(time.time()), "claude": h.get("claude"), "sail": h.get("sail"), "typesafe": h.get("typesafe"),
                                 "web_fetch": h.get("web_fetch"), "github": h.get("github"), "today": h.get("today"),
                                 "kill_switch": h.get("kill_switch"), "frontier": fr}

        def swarm(db: Any) -> dict:
            q = lambda sql, *a: guard.rows(db, sql, a)  # noqa: E731
            return {
                "swarm_spend_t0_to_cutoff": q("SELECT kind, count(*) n, sum(usd) usd FROM spend WHERE epoch>=? AND epoch<=? GROUP BY kind", T0E, CUT),
                "swarm_spend_after_cutoff": q("SELECT kind, count(*) n, sum(usd) usd, max(epoch) last FROM spend WHERE epoch>? GROUP BY kind", CUT),
                "swarm_spend_24h": q("SELECT kind, sum(usd) usd FROM spend WHERE epoch>? AND epoch<=? GROUP BY kind", CUT - 86400, CUT),
                "swarm_spend_4h": q("SELECT kind, sum(usd) usd FROM spend WHERE epoch>? AND epoch<=? GROUP BY kind", CUT - 4 * 3600, CUT),
                "swarm_spend_by_day": q("SELECT substr(at,1,10) day, kind, sum(usd) usd FROM spend WHERE epoch>=? AND epoch<=? "
                                        "GROUP BY day, kind ORDER BY day, kind", T0E, CUT),
                "swarm_spend_claude_by_role": q("SELECT json_extract(detail,'$.role') role, sum(usd) usd FROM spend WHERE kind='claude' "
                                                "AND epoch>=? AND epoch<=? GROUP BY role", T0E, CUT),
                "guard_meter_now": {r["key"]: r["value"] for r in q(
                    "SELECT key, value FROM kv WHERE key IN ('metered_spent','metered_last_balance','metered_today','burst_started_at')")}}

        res.update(guard.read(root / "swarm.sqlite", swarm))

        def provider(db: Any) -> dict:
            def settled(a: str, b: str) -> dict:
                return guard.rows(db, "SELECT count(*) n, sum(CASE WHEN cost_usd IS NOT NULL AND coalesce(error,'')!='usage_unsettled' THEN cost_usd ELSE 0 END) usd, "
                                      "sum(CASE WHEN cost_usd IS NULL AND status!='abandoned' THEN 1 ELSE 0 END) unpriced, "
                                      "sum(CASE WHEN cost_usd IS NULL AND status!='abandoned' THEN reserved_usd ELSE 0 END) unpriced_reserved "
                                      "FROM requests WHERE julianday(created_at)>julianday(?) AND julianday(created_at)<=julianday(?)", (a, b))[0]
            return {"sail_requests_24h": settled(iso_us(CUT - 86400), cutoff), "sail_requests_4h": settled(iso_us(CUT - 4 * 3600), cutoff),
                    "sail_requests_after_cutoff": settled(cutoff, iso_us(time.time() + 3600)),
                    "sail_requests_by_day": guard.rows(db, "SELECT substr(created_at,1,10) day, sum(CASE WHEN cost_usd IS NOT NULL AND "
                                                           "coalesce(error,'')!='usage_unsettled' THEN cost_usd ELSE 0 END) usd FROM requests "
                                                           "WHERE julianday(created_at)>=julianday(?) AND julianday(created_at)<=julianday(?) "
                                                           "GROUP BY day ORDER BY day", (T0, cutoff))}

        res.update(guard.read(root / "swarm-provider.sqlite", provider))
        try:
            from ..swarm import settings as SS

            eff = SS.load(root, config=config)
            res["settings"] = {"guard": eff.get("guard"), "claude": {k: (eff.get("claude") or {}).get(k) for k in ("usd_cap", "reserve_usd", "role_usd_day")},
                               "openai_model": (eff.get("architect") or {}).get("openai_model")}
        except Exception as exc:  # noqa: BLE001
            res["settings_error"] = type(exc).__name__
        return res

    section("costs", costs)

    def account() -> dict:
        a = gw("/v1/alpaca/v2/account") or {}
        p = gw("/v1/alpaca/v2/positions") or []
        o = gw("/v1/alpaca/v2/orders", {"status": "open", "limit": 100}) or []
        return {"read_at": iso_us(time.time()),
                "account": {k: a.get(k) for k in ("status", "equity", "last_equity", "cash", "long_market_value", "short_market_value",
                                                   "position_market_value", "accrued_fees", "pending_transfer_in", "pending_transfer_out",
                                                   "balance_asof", "options_buying_power")},
                "positions": [{k: x.get(k) for k in ("symbol", "qty", "side", "asset_class", "avg_entry_price", "market_value", "cost_basis",
                                                     "unrealized_pl", "current_price")} for x in p],
                "open_orders": [{k: x.get(k) for k in ("symbol", "side", "qty", "status", "order_class", "submitted_at")} for x in o]}

    section("account", account)
    return plain(out)


# ------------------------------------------------------------------------------------------------ Sail and the reporter
def sail_windows(sail: Any, app: str, cutoff: float, house: Mapping[str, Any], *, now: float) -> dict[str, Any]:
    """Sail's app-scoped box billing (GET /sailboxes/spend) over the laptop's five windows."""
    burst = float(((house.get("costs") or {}).get("guard_meter_now") or {}).get("burst_started_at") or ep(T0))
    windows = {"t0-cutoff": (ep(T0), cutoff), "pre-meter": (ep(T0), burst), "last24h": (cutoff - 86400, cutoff),
               "last4h": (cutoff - 4 * 3600, cutoff), "after-cutoff": (cutoff, now)}
    out = {}
    for name, (a, b) in windows.items():
        a_iso = T0 if name in ("t0-cutoff", "pre-meter") else zulu(a)
        out[name] = plain(sail.spend(app=app, since=a_iso, until=zulu(b)))
    return out


def house_app(sail: Any, box: str | None) -> str:
    """The House box's Sail app id (`SailboxClient.get(SAILBOX_ID)`)."""
    if not box:
        raise RuntimeError("the House box's Sail id is not in the environment (SAILBOX_ID)")
    row = sail.get(box) or {}
    app = row.get("app_id")
    if not app and isinstance(row.get("app"), dict):
        app = row["app"].get("id")
    if not app:
        raise RuntimeError("Sail's row of the House box names no app")
    return str(app)


def external_receipt(external: Mapping[str, Any] | None, end_at: str) -> dict[str, Any] | None:
    """The owner's declared external costs as the reporter's `external` receipt (the laptop's own conversion)."""
    if not external:
        return None
    return {"start_at": T0, "end_at": end_at, "complete": external.get("complete") is True, "incremental_only": True,
            "usd": format(sum((Decimal(str(i.get("usd") or 0)) for i in external.get("items") or []), ZERO), "f"),
            "source": f"owner declaration by {external.get('declared_by')} at {external.get('declared_at')}: "
                      + "; ".join(f"{i.get('name')} {i.get('usd')}" for i in external.get("items") or [])}


def library(house: Mapping[str, Any], boxes: Mapping[str, Any], app: str, external: Mapping[str, Any] | None,
            out: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The unchanged PR #432 reporter over the House's cutoff receipt and Sail's billing: (snapshot, meta). Run twice:
    the snapshot is content-addressed, so both runs must agree."""
    from .. import project_economics as PE

    ext = external_receipt(external, house["pe_state"]["as_of"])
    runs = [PE.report(house["pe_state"], boxes, app_id=app, external=ext) for _ in range(2)]
    meta: dict[str, Any] = {"idempotent": PE.digest(runs[0]) == PE.digest(runs[1]), "snapshot": None}
    if out is not None:
        for receipt in (house["pe_state"], boxes, ext):
            if receipt is not None:
                PE.persist(out / "project-economics" / "receipts", receipt)
        meta["snapshot"] = str(PE.persist(out / "project-economics", runs[0]))
    return plain(runs[0]), meta


# ------------------------------------------------------------------------------------------------ the report
def box_totals(row: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    return D(row.get("finalized_cost_usd_nanos")) / Decimal(10 ** 9), D(row.get("estimated_active_cost_usd_nanos")) / Decimal(10 ** 9)


def unposted_regulatory(reg: Mapping[str, Any], cutoff_day: str) -> tuple[Decimal, list]:
    """Each NY day with option fills and a regulatory fee label the broker posts (seen on some day) but has not posted for
    that day yet: the highest observed rate times that day's volume, rounded up to the cent (a liability estimate)."""
    fees, volume = reg.get("orderless_fees") or [], reg.get("option_volume_by_day") or {}
    unit = {"ORF": "contracts", "OPT TAF": "sold_contracts", "TAF": "sold_contracts", "CAT": "fills", "OPT REG": "sell_proceeds", "REG": "sell_proceeds"}
    rates: dict[str, Decimal] = {}
    posted = set()
    for f in fees:
        label = f["label"]
        posted.add((f["date"], label))
        denom = D(f.get("proceeds")) if unit.get(label) == "sell_proceeds" else D(f.get("count"))
        if label in unit and denom > 0:
            rates[label] = max(rates.get(label, ZERO), -D(f["net_amount"]) / denom)
    total, rows = ZERO, []
    for day, vol in sorted(volume.items()):
        if day > cutoff_day:
            continue
        for label, rate in sorted(rates.items()):
            if (day, label) in posted:
                continue
            base = D(vol.get(unit[label]))
            if base <= 0:
                continue
            estimate = max(CENT, (rate * base).quantize(CENT, rounding=ROUND_CEILING))
            total += estimate
            rows.append({"day": day, "label": label, "volume": str(base), "rate": format(rate, "f"), "estimate_usd": usd(estimate)})
    return total, rows


def render(H: Mapping[str, Any], L: Mapping[str, Any], sail: Mapping[str, Any], external: Mapping[str, Any] | None, *,
           lib_meta: Mapping[str, Any], typesafe_before_t0: Any = 0) -> dict[str, Any]:
    """The laptop's render (`economics_close.py`), unchanged in its arithmetic: the summary from the House receipt `H`,
    the reporter's snapshot `L`, Sail's five windows and the owner's declared externals. `typesafe_before_t0` is the
    TypeSafe meter's reading before T0 (the owner's private figure, `ops.json`; 0, the larger upper bound, without it)."""
    typesafe_before = D(typesafe_before_t0)
    cutoff = H["cutoff"]
    cut = ep(cutoff)
    cutoff_day = dt.datetime.fromtimestamp(cut, NY).date().isoformat()
    days_since_t0 = Decimal(str((cut - ep(T0)) / 86400))

    # ---------------------------------------------------------------- trading
    reading = H["broker_at_cutoff"]["reading"]
    corrections = {int(k): D(v) for k, v in reading["fees_by_pid"].items()}
    closed_rows = {int(r["pid"]): r for r in H["trading"]["closed_rows"]}
    by_route = {r: {"closed": 0, "realized_usd": ZERO, "open": 0, "unrealized_conservative_usd": ZERO, "unrealized_mid_usd": ZERO,
                    "open_cost_usd": ZERO} for r in ROUTES}
    positions_out, checks = [], []
    marks = H.get("marks") or {}
    for p in H["book"]["positions"]:
        pid, route = int(p["pid"]), p["route"]
        b = by_route[route]
        row = {"pid": pid, "route": route, "family": p["family"], "root": p["root"], "type": p["type"], "status_at_cutoff": p["status"],
               "opened_at": p["opened_at"], "closed_at": p["closed_at"], "book_cash_usd": usd(p["cash"]),
               "broker_fee_correction_usd": usd(corrections.get(pid, ZERO))}
        if p["status"] == "closed":
            mine = c2(D(p["cash"]) + corrections.get(pid, ZERO))
            deployed = D((closed_rows.get(pid) or {}).get("pnl_usd"))
            if (closed_rows.get(pid) or {}).get("pnl_usd") is None or c2(deployed) != mine:
                checks.append(f"position {pid}: own P&L {mine} differs from the deployed Profit row {deployed}")
            b["closed"] += 1
            b["realized_usd"] += mine
            row["realized_usd"] = usd(mine)
        else:
            m = marks.get(str(pid)) or {}
            cost = D(p["cash"]) + corrections.get(pid, ZERO)
            value = D(m.get("value_usd")) if m.get("value_usd") is not None else ZERO
            exit_fee = D(p.get("fees")) if value > 0 else ZERO  # closing costs about what opening did; none if it expires worthless
            unreal = c2(cost + value - exit_fee)
            mid = c2(cost + D(m["mid_value_usd"]) - D(p.get("fees"))) if m.get("mid_value_usd") is not None else None
            b["open"] += 1
            b["unrealized_conservative_usd"] += unreal
            b["unrealized_mid_usd"] += mid if mid is not None else unreal
            b["open_cost_usd"] += cost
            row.update(open_qty=p["qty"], legs=[{k: leg.get(k) for k in ("symbol", "side", "strike", "is_call", "bid", "ask", "quote_at")}
                                                for leg in m.get("legs") or []],
                       mark_basis=m.get("mark_basis"), spot_at_cutoff=m.get("spot_at_cutoff"), spot_bar=m.get("spot_bar"),
                       mark_per_share=m.get("per_share"), mark_value_usd=usd(value), exit_fee_estimate_usd=usd(exit_fee),
                       cost_with_fees_usd=usd(cost), unrealized_conservative_usd=usd(unreal), unrealized_mid_usd=usd(mid),
                       bid_ask_value_usd=usd(m.get("bid_ask_value_usd")))
            if m.get("value_usd") is None:
                checks.append(f"position {pid}: no mark at the cutoff; valued at 0 (its whole cost is the conservative loss)")
        positions_out.append(row)
    regulatory = D(reading["fees_usd"])
    unposted, unposted_rows = unposted_regulatory(H.get("regulatory_fees") or {}, cutoff_day)
    by_day: dict[str, Any] = {}
    for row in positions_out:
        if row.get("realized_usd") is None:
            continue
        day = dt.datetime.fromtimestamp(ep(row["closed_at"]), NY).date().isoformat()
        d = by_day.setdefault(day, {"closed": 0, "calibration_usd": ZERO, "strategy_usd": ZERO, "regulatory_usd": ZERO})
        d["closed"] += 1
        d["calibration_usd" if row["route"] == "calibration" else "strategy_usd"] += D(row["realized_usd"])
    for f in (H.get("regulatory_fees") or {}).get("orderless_fees") or []:
        d = by_day.setdefault(f["date"], {"closed": 0, "calibration_usd": ZERO, "strategy_usd": ZERO, "regulatory_usd": ZERO})
        d["regulatory_usd"] += D(f["net_amount"])
    for u in unposted_rows:
        d = by_day.setdefault(u["day"], {"closed": 0, "calibration_usd": ZERO, "strategy_usd": ZERO, "regulatory_usd": ZERO})
        d["regulatory_usd"] -= D(u["estimate_usd"])
    realized_by_day = [{"day": k, "closed_positions": v["closed"], "calibration_usd": usd(v["calibration_usd"]), "strategy_usd": usd(v["strategy_usd"]),
                        "regulatory_fees_usd": usd(v["regulatory_usd"]), "total_usd": usd(v["calibration_usd"] + v["strategy_usd"] + v["regulatory_usd"])}
                       for k, v in sorted(by_day.items())]
    closed_total = sum((by_route[r]["realized_usd"] for r in ROUTES), ZERO)
    strategy_closed = closed_total - by_route["calibration"]["realized_usd"]
    realized = closed_total + regulatory - unposted
    other = {k: D(reading[k]) for k in ("crypto_usd", "interest_usd", "misc_usd", "unreconciled_usd")}
    unrealized = sum((by_route[r]["unrealized_conservative_usd"] for r in ROUTES), ZERO)
    unrealized_mid = sum((by_route[r]["unrealized_mid_usd"] for r in ROUTES), ZERO)
    open_cost = sum((by_route[r]["open_cost_usd"] for r in ROUTES), ZERO)

    # ---------------------------------------------------------------- reconciliation
    broker = H["broker_at_cutoff"]
    acct = H["account"]
    changes = H["book_changes_after_cutoff"]
    broker_opt_mv = sum((D(x["market_value"]) for x in acct["positions"] if x.get("asset_class") == "us_option"), ZERO)
    start_equity = D((H.get("performance") or {}).get("start_equity"))
    equity = D(acct["account"]["equity"])
    flows = D(broker["funding_net"])
    account_pnl = equity - start_equity - flows
    components = closed_total + regulatory + sum(other.values(), ZERO) + open_cost + broker_opt_mv
    fee_total = D((broker["by_type"].get("FEE") or {}).get("net_amount"))
    recon: dict[str, Any] = {
        "broker_option_fill_cash_usd": usd(broker["broker_option_fill_cash"]), "book_option_fill_cash_usd": usd(broker["book_option_fill_cash"]),
        "fills_match": c2(D(broker["broker_option_fill_cash"])) == c2(D(broker["book_option_fill_cash"])),
        "broker_fees_posted_usd": usd(fee_total), "unreconciled_usd": usd(other["unreconciled_usd"]), "blocking": reading["blocking"],
        "diagnostic_notes": len(reading["problems"]), "pending_orders_at_cutoff": H["book"]["pending_orders_at_cutoff"],
        "broker_open_orders_now": len(acct["open_orders"]), "book_changes_after_cutoff": changes,
        "broker_activities_after_cutoff": broker["activities_after_cutoff"],
        "broker_positions_now": [{k: x.get(k) for k in ("symbol", "qty", "market_value", "current_price")} for x in acct["positions"]],
        "accrued_fees_now": acct["account"].get("accrued_fees"), "unposted_regulatory_fee_estimate_usd": usd(unposted),
        "unposted_regulatory_fees": unposted_rows, "recon_now": H.get("recon_now"),
        "deposits": {"net_usd": usd(flows), "rows": broker["funding"], "treatment": "owner funding, never P&L"},
        "equity_identity": {
            "equity_usd": usd(equity), "equity_read_at": acct["read_at"], "start_equity_usd": usd(start_equity), "net_deposits_usd": usd(flows),
            "account_pnl_usd": usd(account_pnl),
            "components_usd": usd(components),
            "components": "closed rows + order-less option fees + other account activity + open positions (cost + broker fee correction) + the broker's own option market value",
            "residual_usd": usd(account_pnl - components),
            "residual_note": "the legacy coins sold at the reset and their dust (their value inside the start mark was never recorded; not options P&L)"}}
    recon["reconciled"] = bool(recon["fills_match"] and not reading["blocking"] and c2(other["unreconciled_usd"]) == 0
                               and not recon["pending_orders_at_cutoff"] and not any(changes.values()) and abs(account_pnl - components) < Decimal("1.00"))
    if not recon["fills_match"]:
        checks.append("the broker's option fill cash and the book's differ")
    if any(changes.values()):
        checks.append("the book changed after the cutoff: the account read (equity, positions) is later than the cutoff state")

    # ---------------------------------------------------------------- costs
    inp = L["inputs"]
    g = H["costs"]["gateway_health"]
    after = {r["kind"]: D(r["usd"]) for r in H["costs"]["swarm_spend_after_cutoff"]}
    box_fin, box_active = box_totals(sail["t0-cutoff"])
    sail_models = D(inp["sail_model"]["usd"])
    sail_receipts = sail_models + box_fin + box_active
    meter_now = D(H["costs"]["guard_meter_now"].get("metered_spent"))
    pre_fin, pre_active = box_totals(sail["pre-meter"])
    aft_fin, aft_active = box_totals(sail["after-cutoff"])
    after_models = D(H["costs"]["sail_requests_after_cutoff"].get("usd"))
    sail_meter = meter_now + pre_fin + pre_active - (after_models + aft_fin + aft_active)
    sail_used = max(sail_receipts, sail_meter)
    claude_gateway = D((g.get("claude") or {}).get("spent_usd")) + D((g.get("claude") or {}).get("inflight_usd")) - after.get("claude", ZERO)
    claude_swarm = D(inp["claude"]["usd"])
    claude_used = max(claude_gateway, claude_swarm)
    openai_settled, openai_booked = D(inp["openai"]["usd"]), D(inp["openai"]["booked_usd"])
    openai_holds = D(inp["openai"]["included_hold_usd"])
    openai_hold_count = ((L["reservations_and_provider_comparison"].get("booked_model_holds") or {}).get("openai") or {}).get("count")
    fr = g.get("frontier") or {}
    swarm_frontier = sum((D(v) for k, v in (fr.get("by_agent") or {}).items() if k.startswith("swarm-")), ZERO)
    typesafe_now = D((g.get("typesafe") or {}).get("spent_usd"))
    typesafe_bound = max(ZERO, typesafe_now - typesafe_before)
    theta, mdata = D(inp["thetadata_usd"]["usd"]), D(inp["market_data_usd"]["usd"])
    declared = ZERO
    declared_rows = []
    if external:
        for item in external.get("items") or []:
            declared += D(item.get("usd"))
            declared_rows.append({k: item.get(k) for k in ("name", "usd", "basis")})
    costs = [
        {"service": "Sail (models + boxes)", "usd": usd(sail_used), "settled_usd": usd(sail_receipts),
         "basis": (f"billed: settled Sail model requests {usd(sail_models)} + app-scoped finalized box billing {usd(box_fin)} (+{usd(box_active)} active) "
                   f"= {usd(sail_receipts)}; metered: the Sail balance meter since the burst start + the pre-meter window, less Sail spend after the cutoff = "
                   f"{usd(sail_meter)}; the larger is used. Comparison only, never added: the Gym's booked box estimate "
                   f"{usd((L.get('comparison_only') or {}).get('booked_gym_box_estimate_usd'))} and the swarm's model booking {usd(inp['sail_model'].get('booked_usd'))}")},
        {"service": "Claude (Anthropic via the gateway)", "usd": usd(claude_used), "settled_usd": usd(claude_gateway),
         "basis": (f"the gateway's metering: spent {usd((g.get('claude') or {}).get('spent_usd'))} + in flight {usd((g.get('claude') or {}).get('inflight_usd'))}, "
                   f"less swarm Claude calls after the cutoff {usd(after.get('claude', ZERO))}; the swarm's own record {usd(claude_swarm)}; Anthropic's invoice not reconciled")},
        {"service": "OpenAI", "usd": usd(openai_booked), "settled_usd": usd(openai_settled),
         "basis": (f"the swarm's record since T0: {usd(openai_settled)} settled + {usd(openai_holds)} in {openai_hold_count} "
                   f"unresolved holds (may yet bill) = {usd(openai_booked)}; the gateway's month: spent {fr.get('spent_usd')} (settled {usd(fr.get('settled_usd'))}, "
                   f"in flight {usd(fr.get('inflight_usd'))}), swarm agents {usd(swarm_frontier)}; month {fr.get('month')}; no role uses OpenAI")},
        {"service": "ThetaData", "usd": usd(theta), "settled_usd": usd(theta),
         "basis": f"pro-rata of ${usd(inp['thetadata_usd']['monthly_usd'])}/month (Options Standard list) from {FS} (365.25-day year); invoice not seen"},
        {"service": "Alpaca market data (Algo Trader Plus)", "usd": usd(mdata), "settled_usd": usd(mdata),
         "basis": f"pro-rata of ${usd(inp['market_data_usd']['monthly_usd'])}/month from {FS}; invoice not seen"},
        {"service": "TypeSafe/Jev (gateway meter)", "usd": usd(typesafe_bound), "settled_usd": usd(ZERO),
         "basis": (f"upper bound: the gateway's lifetime meter {usd(typesafe_now)} less the {usd(typesafe_before)} it read before T0 "
                   "(the owner's figure in ops.json); the options swarm has no TypeSafe caller")},
    ]
    if declared_rows:
        costs.append({"service": "Owner-declared external costs", "usd": usd(declared), "settled_usd": usd(declared),
                      "basis": f"declared by {external.get('declared_by')} at {external.get('declared_at')}: " + "; ".join(f"{r['name']} {r['usd']}" for r in declared_rows)})
    total_costs = sum((D(x["usd"]) for x in costs), ZERO)
    total_settled = sum((D(x["settled_usd"]) for x in costs), ZERO)

    # ---------------------------------------------------------------- burn
    s24 = {r["kind"]: D(r["usd"]) for r in H["costs"]["swarm_spend_24h"]}
    s4 = {r["kind"]: D(r["usd"]) for r in H["costs"]["swarm_spend_4h"]}
    b24f, b24a = box_totals(sail["last24h"])
    b4f, b4a = box_totals(sail["last4h"])
    per_day_theta = D(inp["thetadata_usd"]["monthly_usd"]) * 12 / Decimal("365.25")
    per_day_mdata = D(inp["market_data_usd"]["monthly_usd"]) * 12 / Decimal("365.25")
    burn = [
        {"service": "Claude", "last24h": s24.get("claude", ZERO), "last4h_per_day": s4.get("claude", ZERO) * 6},
        {"service": "Sail models", "last24h": D(H["costs"]["sail_requests_24h"]["usd"]), "last4h_per_day": D(H["costs"]["sail_requests_4h"]["usd"]) * 6},
        {"service": "Sail boxes (billed)", "last24h": b24f + b24a, "last4h_per_day": (b4f + b4a) * 6},
        {"service": "OpenAI", "last24h": s24.get("openai", ZERO), "last4h_per_day": s4.get("openai", ZERO) * 6},
        {"service": "ThetaData (pro-rata)", "last24h": per_day_theta, "last4h_per_day": per_day_theta},
        {"service": "Alpaca market data (pro-rata)", "last24h": per_day_mdata, "last4h_per_day": per_day_mdata},
    ]
    burn_total24 = sum((x["last24h"] for x in burn), ZERO)
    burn_total4 = sum((x["last4h_per_day"] for x in burn), ZERO)

    # ---------------------------------------------------------------- net
    net = realized - total_costs
    net_open = net + unrealized
    unknowns = []
    if not (external and external.get("complete") is True):
        unknowns += [f"{name}: not declared by the owner (not zero)" for name in UNKNOWN_EXTERNAL]
    unknowns += [
        f"OpenAI: the {openai_hold_count} unresolved holds ({usd(openai_holds)}) await the provider's invoice; they are counted in Net",
        "Anthropic: the console invoice is not reconciled to the gateway meter",
        "ThetaData and Alpaca market data: actual invoices, billing cycles and plan dates not seen (pro-rata of list rates used)",
        f"Sail: the provider invoice itself is not seen; receipts {usd(sail_receipts)} vs balance meter {usd(sail_meter)}",
        "Later-posted broker fees can revise the realized figure by cents (the unposted-fee estimate is included)",
    ]
    return {
        "schema": "ltcm-econ-close-1", "cutoff": cutoff, "cost_start": T0, "financial_start": FS, "days_since_t0": format(days_since_t0.quantize(Decimal("0.001")), "f"),
        "collected_at": H["collected_at"], "house_release": H["release"],
        "realized": {
            "by_route": {r: {"closed_positions": v["closed"], "realized_usd": usd(v["realized_usd"]), "open_positions": v["open"],
                             "unrealized_conservative_usd": usd(v["unrealized_conservative_usd"]), "unrealized_mid_usd": usd(v["unrealized_mid_usd"])}
                         for r, v in by_route.items()},
            "calibration_usd": usd(by_route["calibration"]["realized_usd"]), "strategy_routes_usd": usd(strategy_closed),
            "regulatory_fees_orderless_usd": usd(regulatory), "unposted_regulatory_fee_estimate_usd": usd(-unposted),
            "realized_options_pnl_usd": usd(realized),
            "other_account_activity": {k: usd(v) for k, v in other.items()},
            "by_close_day": realized_by_day,
        },
        "open_positions": {"unrealized_conservative_usd": usd(unrealized), "unrealized_mid_usd": usd(unrealized_mid),
                           "cost_with_fees_usd": usd(open_cost)},
        "positions": positions_out,
        "costs": costs, "total_costs_usd": usd(total_costs), "total_costs_settled_basis_usd": usd(total_settled),
        "net": {"net_usd": usd(net), "definition": "realized options P&L since T0 (all routes, fees in) - all input costs since T0 (conservative basis)",
                "net_settled_basis_usd": usd(realized - total_settled),
                "net_with_open_at_conservative_marks_usd": usd(net_open),
                "net_with_open_and_other_account_activity_usd": usd(net_open + sum(other.values(), ZERO)),
                "gap_to_break_even_usd": usd(max(ZERO, -net)), "gap_including_open_positions_usd": usd(max(ZERO, -net_open)),
                "criterion_5_met": bool(net > 0 and net_open > 0 and recon["reconciled"] and external and external.get("complete") is True)},
        "burn_per_day": {"rows": [{"service": x["service"], "last24h_usd": usd(x["last24h"]), "last4h_pace_per_day_usd": usd(x["last4h_per_day"])} for x in burn],
                         "total_last24h_usd": usd(burn_total24), "total_last4h_pace_per_day_usd": usd(burn_total4),
                         "gateway_sail_meter_24h_usd": usd((g.get("sail") or {}).get("spend_usd")),
                         "gateway_sail_meter_checked_at": (g.get("sail") or {}).get("checked_at")},
        "funding_now": {"sail_balance_usd": usd((g.get("sail") or {}).get("balance_usd")), "sail_run_out_at": (g.get("sail") or {}).get("run_out_at"),
                        "claude_remaining_usd": usd((g.get("claude") or {}).get("remaining_usd")), "claude_cap_usd": (g.get("claude") or {}).get("cap_usd"),
                        "openai_month": fr.get("month"), "openai_month_cap_usd": fr.get("cap_usd"), "read_at": g.get("at")},
        "reconciliation": recon, "checks": checks, "unknowns": unknowns,
        "library_report": {"snapshot": lib_meta.get("snapshot"), "idempotent": lib_meta.get("idempotent"), "complete": L["complete"],
                           "known_input_subtotal_usd": L["known_input_subtotal_usd"], "project_net_usd": L["project_net_usd"],
                           "unresolved": L["unresolved"], "trading": L["trading"]},
    }


def p30(summary: Mapping[str, Any], *, days: int = P30_DAYS) -> dict[str, Any]:
    """Trailing realized options P&L over the `days` New York days ending at the cutoff's day (all routes, fees in;
    regulatory fees by their posting day, the unposted estimate included): the budget rule's `p30`."""
    cutoff_day = dt.datetime.fromtimestamp(ep(summary["cutoff"]), NY).date()
    first = (cutoff_day - dt.timedelta(days=days - 1)).isoformat()
    rows = [r for r in (summary.get("realized") or {}).get("by_close_day") or [] if first <= r["day"] <= cutoff_day.isoformat()]
    return {"usd": usd(sum((D(r["total_usd"]) for r in rows), ZERO)), "days": days, "from_day": first,
            "to_day": cutoff_day.isoformat(), "closed_positions": sum(int(r["closed_positions"]) for r in rows)}


def markdown(s: Mapping[str, Any]) -> str:
    r, n = s["realized"], s["net"]
    lines = [f"# LTCM economics at the {s['cutoff']} cutoff", "",
             f"Scope: realized options P&L and every input cost from T0 {s['cost_start']} (the Sept 26 reset) to the cutoff "
             f"({s['days_since_t0']} days). Deposits and equity changes are not P&L. Collected {s['collected_at']} by the House "
             f"(release `{Path(s['house_release']).name}`), read-only.", "",
             "## Net", "", "| Measure | USD |", "|---|---:|",
             f"| Realized options P&L since T0 (all routes, fees in) | {r['realized_options_pnl_usd']} |",
             f"| All input costs since T0 (conservative basis) | {s['total_costs_usd']} |",
             f"| **Net = realized - costs** | **{n['net_usd']}** |",
             f"| Net on the settled-only cost basis | {n['net_settled_basis_usd']} |",
             f"| Open positions at conservative marks (unrealized) | {s['open_positions']['unrealized_conservative_usd']} |",
             f"| Net with open positions at conservative marks | {n['net_with_open_at_conservative_marks_usd']} |",
             f"| Gap to break even (realized profit still needed) | {n['gap_to_break_even_usd']} |",
             f"| Gap including open positions | {n['gap_including_open_positions_usd']} |", ""]
    if s.get("p30"):
        lines += [f"Trailing {s['p30']['days']}-day realized options P&L ({s['p30']['from_day']} to {s['p30']['to_day']}): "
                  f"{s['p30']['usd']} over {s['p30']['closed_positions']} closed positions.", ""]
    lines += [f"Criterion 5 met: **{'yes' if n['criterion_5_met'] else 'no'}**.", "",
              "## Realized options P&L by route", "", "| Route | Closed | Realized | Open | Unrealized (conservative) | Unrealized (mid) |",
              "|---|---:|---:|---:|---:|---:|"]
    for route, v in r["by_route"].items():
        if v["closed_positions"] or v["open_positions"] or route in ("calibration", "tuition", "house_test", "incubator", "d2_real"):
            lines.append(f"| {ROUTE_WORDS[route]} | {v['closed_positions']} | {v['realized_usd']} | {v['open_positions']} | "
                         f"{v['unrealized_conservative_usd']} | {v['unrealized_mid_usd']} |")
    lines += [f"| Option regulatory fees not tied to a position (ORF, TAF, REG, CAT) | | {r['regulatory_fees_orderless_usd']} | | | |",
              f"| Regulatory fees not posted yet (estimate, a liability) | | {r['unposted_regulatory_fee_estimate_usd']} | | | |",
              f"| **Total realized options P&L** | | **{r['realized_options_pnl_usd']}** | | | |", "",
              f"Calibration {r['calibration_usd']}; strategy routes {r['strategy_routes_usd']} (closed). Other account activity, not options and "
              f"not in Net: crypto fees {r['other_account_activity']['crypto_usd']}, interest {r['other_account_activity']['interest_usd']}, "
              f"misc {r['other_account_activity']['misc_usd']}, unreconciled {r['other_account_activity']['unreconciled_usd']}.", ""]
    lines += ["By New York close day (regulatory fees by their posting date, the unposted estimate included):", "",
              "| Day | Closed | Calibration | Strategy routes | Regulatory fees | Total |", "|---|---:|---:|---:|---:|---:|"]
    for d in r["by_close_day"]:
        lines.append(f"| {d['day']} | {d['closed_positions']} | {d['calibration_usd']} | {d['strategy_usd']} | {d['regulatory_fees_usd']} | {d['total_usd']} |")
    lines.append("")
    opens = [p for p in s["positions"] if p["status_at_cutoff"] != "closed"]
    if opens:
        lines += ["### Open at the cutoff", ""]
        for p in opens:
            legs = "; ".join(f"{'long' if leg['side'] > 0 else 'short'} {leg['symbol']} bid {leg['bid']} ask {leg['ask']} ({leg['quote_at']})"
                             for leg in p["legs"])
            per = p.get("mark_per_share") or {}
            lines += [f"- Position {p['pid']} ({ROUTE_WORDS[p['route']]}, {p['family']}), {p['root']} {p['type']} x{p['open_qty']}: cost with fees "
                      f"{p['cost_with_fees_usd']} (book cash {p['book_cash_usd']}, broker fee correction {p['broker_fee_correction_usd']}). "
                      f"Mark per share: bid/ask {per.get('conservative_bid_ask')}, intrinsic {per.get('intrinsic')} (spot {p['spot_at_cutoff']}, bar {p['spot_bar']}), "
                      f"mid {per.get('mid')}; used {per.get('mark')} ({p['mark_basis']}) = {p['mark_value_usd']}. "
                      f"Unrealized: conservative {p['unrealized_conservative_usd']}, mid {p['unrealized_mid_usd']}; at the broker's own bid/ask mark "
                      f"the legs are worth {p['bid_ask_value_usd']}.", f"  Legs: {legs}."]
        lines.append("")
    lines += ["## Input costs since T0", "", "| Service | Used in Net | Settled basis | Basis |", "|---|---:|---:|---|"]
    for c in s["costs"]:
        lines.append(f"| {c['service']} | {c['usd']} | {c['settled_usd']} | {c['basis']} |")
    lines += [f"| **Total** | **{s['total_costs_usd']}** | {s['total_costs_settled_basis_usd']} | |", "",
              "## Daily burn by service", "", "| Service | Last 24 h | Last 4 h pace, per day |", "|---|---:|---:|"]
    for b in s["burn_per_day"]["rows"]:
        lines.append(f"| {b['service']} | {b['last24h_usd']} | {b['last4h_pace_per_day_usd']} |")
    bp = s["burn_per_day"]
    f = s["funding_now"]
    lines += [f"| **Total** | **{bp['total_last24h_usd']}** | **{bp['total_last4h_pace_per_day_usd']}** |", "",
              f"The gateway's own Sail meter reads {bp['gateway_sail_meter_24h_usd']} for the 24 h to {bp['gateway_sail_meter_checked_at']}. "
              f"Funding at {f['read_at']}: Sail balance {f['sail_balance_usd']} (run-out {f['sail_run_out_at']}), Claude room {f['claude_remaining_usd']} "
              f"of {f['claude_cap_usd']}, OpenAI month {f['openai_month']} cap {f['openai_month_cap_usd']}.", ""]
    rc = s["reconciliation"]
    eq = rc["equity_identity"]
    lines += ["## Reconciliation with the broker", "",
              f"- Option fill cash: broker {rc['broker_option_fill_cash_usd']}, book {rc['book_option_fill_cash_usd']} ({'match' if rc['fills_match'] else 'MISMATCH'}).",
              f"- Broker fees posted {rc['broker_fees_posted_usd']}; unreconciled {rc['unreconciled_usd']}; blocking {rc['blocking'] or 'none'}; "
              f"{rc['diagnostic_notes']} diagnostic notes (order-less regulatory fees).",
              f"- Unposted regulatory fees (estimate): {rc['unposted_regulatory_fee_estimate_usd']} "
              + ("(" + "; ".join(f"{u['day']} {u['label']} {u['estimate_usd']}" for u in rc["unposted_regulatory_fees"]) + ")" if rc["unposted_regulatory_fees"] else "") + ".",
              f"- Pending orders at the cutoff: {len(rc['pending_orders_at_cutoff'])}; broker open orders now: {rc['broker_open_orders_now']}; "
              f"book changes after the cutoff: {sum(rc['book_changes_after_cutoff'].values())}; broker activities after the cutoff: {rc['broker_activities_after_cutoff']}.",
              "- Broker positions now: " + ", ".join(f"{x['symbol']} {x['qty']} (mv {x['market_value']})" for x in rc["broker_positions_now"]) + ".",
              f"- Deposits {rc['deposits']['net_usd']} ({', '.join(str(x['date']) + ' ' + str(x['activity_type']) + ' ' + str(x['net_amount']) for x in rc['deposits']['rows'])}): {rc['deposits']['treatment']}.",
              f"- Equity identity (read {eq['equity_read_at']}): equity {eq['equity_usd']} - start {eq['start_equity_usd']} - deposits {eq['net_deposits_usd']} = "
              f"{eq['account_pnl_usd']}; components (at the broker's own marks) {eq['components_usd']}; residual {eq['residual_usd']} ({eq['residual_note']}).",
              f"- Reconciled: **{'yes' if rc['reconciled'] else 'no'}**.", ""]
    if s["checks"]:
        lines += ["Checks raised:", ""] + [f"- {c}" for c in s["checks"]] + [""]
    lines += ["## Unknown or unreconciled", ""] + [f"- {u}" for u in s["unknowns"]] + [""]
    lb = s["library_report"]
    lines += ["## The PR #432 reporter (unchanged)", "",
              f"Snapshot `{Path(str(lb['snapshot'] or '-')).name}` (idempotent: {lb['idempotent']}): known input subtotal {lb['known_input_subtotal_usd']} "
              f"(settled categories only, no TypeSafe, OpenAI holds excluded), complete {lb['complete']}, project Net {lb['project_net_usd']}. "
              f"It leaves Net null while any category or reconciliation is open: {len(lb['unresolved'])} unresolved items, listed in the snapshot.", ""]
    return "\n".join(lines)


def latest(root: str | Path) -> dict[str, Any] | None:
    """The newest `<state>/economics/<YYYYMMDD>-close/summary.json`, or None (the budget rule and the scoreboard)."""
    folder = Path(root) / "economics"
    try:
        dirs = sorted(p for p in folder.iterdir() if p.is_dir() and p.name.endswith("-close"))
    except OSError:
        return None
    for path in reversed(dirs):
        value = read_json(path / "summary.json", None)
        if isinstance(value, dict):
            return value
    return None


def run(ctx: Any) -> dict[str, Any]:
    now = ctx.now()
    cut = cutoff_of(ctx.due_at)
    cutoff = zulu(cut)
    out = ctx.root / "economics" / f"{dt.datetime.fromtimestamp(cut, NY).strftime('%Y%m%d')}-close"
    mine = ctx.job_settings()
    external = mine.get("external") if isinstance(mine.get("external"), dict) else None
    with guard.readonly():
        house = collect_house(ctx.root, cutoff, ctx.gateway, now=now, config=ctx.config)
    write_json(out / "receipts" / "house.json", house)
    if house.get("errors"):
        # As on the laptop: the report goes on without a section it could not read (a missing mark is valued at zero, a
        # check says so); a section the arithmetic needs fails the render, and with it the job.
        ctx.alert("warning", "economics: the House read had errors in " + ", ".join(sorted(house["errors"])))
    app = house_app(ctx.sail, ctx.house_box())
    sail = sail_windows(ctx.sail, app, cut, house, now=now)
    for name, row in sail.items():
        write_json(out / "receipts" / f"sail-boxes-{name}.json", row)
    L, meta = library(house, sail["t0-cutoff"], app, external, out)
    write_json(out / "receipts" / "library-run.json", meta)
    summary = render(house, L, sail, external, lib_meta=meta, typesafe_before_t0=mine.get("typesafe_before_t0_usd") or 0)
    summary["p30"] = p30(summary)
    write_json(out / "summary.json", summary)
    write_text(out / "summary.md", markdown(summary))
    if summary["checks"]:
        ctx.alert("info", f"economics: {len(summary['checks'])} check(s) raised at the {cutoff} cutoff (see the summary)")
    return {"cutoff": cutoff, "dir": str(out), "realized_options_pnl_usd": summary["realized"]["realized_options_pnl_usd"],
            "total_costs_usd": summary["total_costs_usd"], "net_usd": summary["net"]["net_usd"], "p30_usd": summary["p30"]["usd"],
            "reconciled": summary["reconciliation"]["reconciled"], "checks": len(summary["checks"]),
            "house_errors": house.get("errors") or None}
