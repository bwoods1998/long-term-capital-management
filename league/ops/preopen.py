"""The `preopen` job (each trading day, an hour before the open): the operator's nine pre-open checks, on the House.

Ported from the private laptop tool (`preopen.py`, Sept 28-Oct 2, 2026). Its House half ran on the box already; the
laptop half read things only the laptop has (wrangler's deployed version, the box record, the site's events API), and
those lines are gone: the gateway's caps are read from its own `/v1/health`, the backup from the ledger alone. Its
fixed expectations (a named release, a fill-model sha, an image pair, `observe_max` 48) were the runbook's of one day
and went stale (GOAL Appendix C 7); here each check asks what the running House itself says it should be.

 1 release   health.json is fresh, names the release `current` points at, real money on, no health failure, a fill
             model loaded (its cells and file sha256 recorded)
 2 grant     the latest grant is not revoked, is active on the running money digest, has capital; a settled deposit
             above its capital is a FAIL (the standing grant re-ratifies it)
 3 gateway   `/v1/health` readable; its caps by maximum loss equal the constitution's
 4 account   the account is ACTIVE, readable and not blocked, options level >= 3; the kill switch off; no House stop
             tripped; the real book not frozen (open orders and option positions are listed, not judged)
 5 swarm     swarm.json is an object with a `live` block the live path reads as such; population at or above the
             floor; heartbeat fresh and on the current release; the Gym on with images named; the Sail guard not
             braked, or braked by THE BUDGET's daily caps alone on a fresh balance above its line (research at its cap
             until 00:00 UTC is the day as designed; any other cause, a budget rule that could not be read among them,
             or one not named, is a FAIL)
 6 bands     the observe rows the swarm offers the live path (when observe is on; a count of rows offered, not of
             cohorts pinned or practising); every Probe/Sized row fits the Probe cap
 7 mirror    the House's swarm mirror keeps up with the swarm's events (lag <= one batch)
 8 backup    the latest House backup row is ok and at most 30 hours old
 9 compute   Sail balance above the guard's line now and, at the last hour's pace, at the close; Claude and OpenAI
             spend under their caps

Read-only (`guard.readonly()`; GET only). Each FAIL is one House warning ("preopen 5 swarm FAIL: ..."); the receipt
holds every line. The warning is PUBLIC (`ops.alert`) and the runner scrubs only what carries a `$`
(`league/ops/runner.py` `public_text`): a text that holds the account's numbers bare (the Sail guard's reason) is never
part of a FAIL's line; it goes on a line of its own, which only the receipt holds.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from . import guard
from . import schedule as S
from .context import read_json

MAX_AGE = {"health": 180, "heartbeat": 120, "backup_ok_h": 30}
MIRROR_LAG_MAX = 200


def dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def usd(value: Any) -> str:
    d = dec(value)
    return "?" if d is None else f"${d:,.2f}"


def ago(seconds: Any) -> str:
    if seconds is None:
        return "?"
    s = float(seconds)
    return f"{s:.0f}s" if s < 120 else f"{s / 60:.0f}m" if s < 7200 else f"{s / 3600:.1f}h"


def fresh(age: Any, limit: float) -> bool:
    return age is not None and float(age) <= limit


class Check:
    def __init__(self, n: int, name: str):
        self.n, self.name, self.items = n, name, []

    def req(self, ok: Any, text: str) -> bool:
        self.items.append((bool(ok), text))
        return bool(ok)

    def info(self, text: str) -> None:
        self.items.append((None, text))

    @property
    def ok(self) -> bool:
        return any(o is True for o, _ in self.items) and all(o is not False for o, _ in self.items)

    def headline(self) -> str:
        bad = [t for o, t in self.items if o is False]
        good = [t for o, t in self.items if o is True]
        return bad[0] if bad else (good[0] if good else "no evidence")

    def row(self) -> dict[str, Any]:
        return {"n": self.n, "name": self.name, "ok": self.ok, "headline": self.headline(),
                "items": [{"ok": o, "text": t} for o, t in self.items]}


# ------------------------------------------------------------------------------------------------ the House reads
def collect(root: Path, base: Path, release: Path, gateway: Any, *, now: float, config: Mapping[str, Any]) -> dict[str, Any]:
    """What the checks read, one section at a time (a section that cannot be read is an error, never a pass)."""
    out: dict[str, Any] = {"at": now, "errors": {}}

    def section(name: str, fn: Callable[[], Any]) -> None:
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            out["errors"][name] = type(exc).__name__ + ": " + str(exc)[:400]

    def epoch(text: Any) -> float:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()

    def release_() -> dict:
        h = json.loads((root / "health.json").read_text())
        ol = h.get("options_live") or {}
        fm = ol.get("fill_model") or {}
        src = fm.get("source") or ""
        sha = hashlib.sha256(Path(src).read_bytes()).hexdigest() if src and Path(src).is_file() else None
        stops = ol.get("stops") or {}
        return {"current": os.path.realpath(base / "current"), "running": release.name,
                "health_age_s": round(now - epoch(h["at"]), 1) if h.get("at") else None,
                "release": h.get("release"), "real_money": h.get("real_money"), "failures": h.get("failures"),
                "fill_model": fm, "fill_model_file_sha256": sha,
                "live": {"summary": ol.get("summary"), "blocked": ol.get("blocked"), "frozen": ol.get("frozen"),
                         "stops": {k: stops.get(k) for k in ("daily_tripped", "daily_why", "drawdown_tripped", "drawdown_why",
                                                             "provisional", "start_equity")},
                         "instances": len(ol.get("instances") or {}), "paper_proof": ol.get("paper_proof")}}

    def grant() -> dict:
        from .. import live_trading as LT
        from ..constitution import money_digest

        def read(db: Any) -> tuple:
            return (guard.rows(db, "SELECT id, started, revoked, policy FROM grants ORDER BY started DESC, rowid DESC"),
                    guard.rows(db, "SELECT at FROM ratifications ORDER BY at"))

        rows, rats = guard.read(root / LT.STORE, read)
        latest = rows[0] if rows else None
        policy = json.loads(latest["policy"]) if latest else {}
        holds = bool(latest) and LT.holds(policy)
        return {"latest": latest["id"] if latest else None, "revoked": latest["revoked"] if latest else None,
                "policy": {k: policy.get(k) for k in ("capital_usd", "equity_usd", "ceiling_usd", "constitution_digest")},
                "holds": holds, "active": bool(latest) and latest["revoked"] is None and latest["started"] <= now and holds,
                "running_money_digest": money_digest(), "ratifications": len(rats)}

    def money() -> dict:
        from ..constitution import CONSTITUTION
        from ..live import money as M

        t = M.Table.from_constitution()
        om = CONSTITUTION["options_money"]
        return {"real_types": list(t.real_types), "gateway": om["gateway"], "credit_min_equity_usd": om["credit_min_equity_usd"]}

    def gateway_() -> dict:
        def get(path: str, params: Any = None) -> dict:
            try:
                return {"body": gateway.get(path, params)}
            except Exception as exc:  # noqa: BLE001
                return {"error": type(exc).__name__ + ": " + str(exc)[:200]}

        h, a = get("/v1/health"), get("/v1/alpaca/v2/account")
        o, p = get("/v1/alpaca/v2/orders", {"status": "open", "limit": 100}), get("/v1/alpaca/v2/positions")
        hb = h.get("body") if isinstance(h.get("body"), dict) else {}
        ab = a.get("body") if isinstance(a.get("body"), dict) else None
        fr = hb.get("frontier") or {}
        return {"health_error": None if hb else h.get("error"), "kill_switch": hb.get("kill_switch"), "max_loss": hb.get("max_loss"),
                "frontier": {k: fr.get(k) for k in ("month", "spent_usd", "cap_usd", "inflight_usd")},
                "claude": {k: (hb.get("claude") or {}).get(k) for k in ("cap_usd", "spent_usd", "inflight_usd", "remaining_usd")},
                "sail": hb.get("sail"),
                "account_error": None if ab else a.get("error"),
                "account": {k: ab.get(k) for k in ("status", "equity", "cash", "options_buying_power", "options_trading_level",
                                                    "trading_blocked", "account_blocked")} if ab else None,
                "orders": [{k: x.get(k) for k in ("symbol", "side", "qty", "status")} for x in o["body"]]
                if isinstance(o.get("body"), list) else None,
                "positions": [{k: x.get(k) for k in ("symbol", "qty", "asset_class")} for x in p["body"]]
                if isinstance(p.get("body"), list) else None}

    def swarm() -> dict:
        from ..swarm import settings as SS

        raw = json.loads((root / "swarm.json").read_text())
        eff = SS.load(root, config=config)
        hb = json.loads((root / "swarm.heartbeat").read_text())
        st = hb.get("status") or {}
        alive = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT count(*) FROM families WHERE retired_at IS NULL"))[0]
        return {"raw_is_object": isinstance(raw, dict), "raw_live": raw.get("live") if isinstance(raw, dict) else None,
                "defaults_live": dict(SS.DEFAULTS["live"]),
                "eff_gym": {k: (eff.get("gym") or {}).get(k) for k in ("enabled", "image_checkpoint", "gate_checkpoint")},
                "eff_guard": eff.get("guard"), "eff_claude": {k: (eff.get("claude") or {}).get(k) for k in ("usd_cap",)},
                "floor": int((eff.get("population") or {}).get("floor", 0) or 0),
                "alive": alive, "heartbeat_age_s": round(now - float(hb["at"]), 1), "heartbeat_release": hb.get("release"),
                "status": {k: st.get(k) for k in ("spend_last_hour", "usd_per_hour", "braked")}, "guard": st.get("guard")}

    def bands() -> dict:
        from ..live import money as M
        from ..swarm import bands as B

        obs = B.observe(root)
        rows = B.read(root)
        live_fams = guard.read(root / "swarm.sqlite", lambda db: guard.rows(
            db, "SELECT id, band FROM families WHERE retired_at IS NULL AND band IN ('candidate','probe','sized') ORDER BY id"))
        acct = (out.get("gateway") or {}).get("account") or {}
        cap = ((out.get("grant") or {}).get("policy") or {}).get("capital_usd")
        E = min(M.D(acct["equity"]), M.D(cap)) if acct.get("equity") is not None and cap is not None else None
        table = M.Table.from_constitution()
        evals = []
        for r in rows:
            e = {"family": r["family"], "band": r["band"], "version": r["version"], "typical_max_loss_usd": r.get("typical_max_loss_usd")}
            unit = r.get("typical_max_loss_usd")
            if E is not None and unit is not None and M.D(unit) > 0:
                e["fits_probe"] = M.fits_probe(table, E, M.D(unit))
            evals.append(e)
        ids = {r["family"] for r in rows}
        return {"observe": len(obs), "read": evals, "live_missing_from_read": [f["id"] for f in live_fams if f["id"] not in ids],
                "sizing_equity": None if E is None else str(E)}

    def backup() -> dict:
        rows = guard.read(root / "ledger.sqlite", lambda db: guard.rows(
            db, "SELECT seq, at, payload FROM ledger WHERE kind='ops.deploy' AND payload LIKE '%\"what\":\"backup\"%' "
                "ORDER BY seq DESC LIMIT 1"))
        if not rows:
            return {"latest": None}
        p = json.loads(rows[0]["payload"])
        return {"latest": {"at": rows[0]["at"], "age_h": round((now - epoch(rows[0]["at"])) / 3600, 2), "ok": p.get("ok"),
                           "error": p.get("error")}}

    def mirror() -> dict:
        cursor = read_json(root / "swarm-mirror.json", None)
        top = guard.read(root / "swarm.sqlite", lambda db: guard.ids(db, "SELECT max(seq) FROM events"))[0]
        seq = cursor.get("seq") if isinstance(cursor, dict) else None
        return {"cursor": seq, "events_top_seq": top,
                "lag": None if seq is None or top is None else max(0, int(top) - int(seq))}

    for name, fn in (("release", release_), ("grant", grant), ("money", money), ("gateway", gateway_), ("swarm", swarm),
                     ("bands", bands), ("backup", backup), ("mirror", mirror)):
        section(name, fn)
    return out


# ------------------------------------------------------------------------------------------------ the checks
def live_switches(s: Mapping[str, Any]) -> dict[str, Any]:
    """The live path's switches as `league/live/step.py` `switches()` reads swarm.json (the laptop tool's reading)."""
    defaults = s.get("defaults_live") or {"observe": True, "observe_max": 48, "calibration": False}
    if not s.get("raw_is_object"):
        return {"observe": False, "observe_max": 0, "calibration": False, "why": "swarm.json is not a JSON object"}
    raw = s.get("raw_live") if s.get("raw_live") is not None else {}
    if not isinstance(raw, dict):
        return {"observe": False, "observe_max": 0, "calibration": False, "why": 'swarm.json "live" is not an object'}
    value = raw.get("observe_max", defaults.get("observe_max", 48))
    count = int(defaults.get("observe_max", 48)) if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 256 else value
    return {"observe": raw.get("observe", defaults.get("observe")) is True, "observe_max": count,
            "calibration": raw.get("calibration", defaults.get("calibration")) is True, "why": None}


def check_release(h: Mapping[str, Any]) -> Check:
    c = Check(1, "release")
    r = h.get("release")
    if not r:
        c.req(False, "health.json unreadable: " + str(h.get("errors", {}).get("release")))
        return c
    c.req(r.get("release") == r.get("running"), f"health.release {r.get('release')} (this release is {r.get('running')})")
    c.req(Path(r.get("current") or "").name == r.get("running"), f"current -> {Path(r.get('current') or '').name}")
    c.req(r.get("real_money") is True, f"health.real_money {json.dumps(r.get('real_money'))}")
    c.req(fresh(r.get("health_age_s"), MAX_AGE["health"]), f"health.json written {ago(r.get('health_age_s'))} ago")
    c.req(not r.get("failures"), f"health.failures {r.get('failures') or 'none'}")
    fm = r.get("fill_model") or {}
    c.req(bool(fm) and (fm.get("cells") or 0) > 0, f"options_live.fill_model {fm.get('version')} ({fm.get('cells')} cells)")
    c.info(f"fill model file sha256 {(r.get('fill_model_file_sha256') or 'unreadable')[:12]}")
    live = r.get("live") or {}
    c.info(f"options_live: {(live.get('summary') or {}).get('state')}; blocked: {live.get('blocked') or 'no'}; instances {live.get('instances')}")
    return c


def check_grant(h: Mapping[str, Any]) -> Check:
    c = Check(2, "grant")
    g = h.get("grant")
    if not g:
        c.req(False, "grant store unreadable: " + str(h.get("errors", {}).get("grant")))
        return c
    p = g.get("policy") or {}
    c.req(g.get("latest") is not None and g.get("revoked") is None, f"latest grant {g.get('latest')}, revoked {g.get('revoked')}")
    c.req(g.get("active") is True, f"active {g.get('active')} (holds on the running money rules: {g.get('holds')})")
    pinned, running = str(p.get("constitution_digest") or ""), str(g.get("running_money_digest") or "")
    c.req(pinned == running and pinned, f"pinned money digest {pinned[:8]}, running {running[:8]}")
    cap = dec(p.get("capital_usd"))
    c.req(cap is not None and cap >= Decimal("100"), f"capital {usd(cap)} (ceiling {usd(p.get('ceiling_usd'))})")
    acct = (h.get("gateway") or {}).get("account") or {}
    eq, bp = dec(acct.get("equity")), dec(acct.get("options_buying_power"))
    ceiling = dec(p.get("ceiling_usd"))
    if cap is not None and eq is not None and bp is not None and (ceiling is None or cap < ceiling):
        if bp > cap * Decimal("1.05") and eq > cap * Decimal("1.05"):
            c.req(False, f"deposit settled: options buying power and equity are above the grant's capital {usd(cap)}: "
                         "the standing grant must re-ratify")
    c.info(f"ratifications {g.get('ratifications')}")
    return c


def check_gateway(h: Mapping[str, Any]) -> Check:
    c = Check(3, "gateway")
    g, m = h.get("gateway") or {}, h.get("money") or {}
    ml = g.get("max_loss") or {}
    if not ml:
        c.req(False, f"gateway /v1/health unreadable: {g.get('health_error') or h.get('errors', {}).get('gateway')}")
        return c
    if not m or (h.get("errors") or {}).get("money"):
        # Nothing to compare is no PASS: a constitution that failed to read would otherwise skip every pair.
        c.req(False, f"the constitution's money table is unreadable: {(h.get('errors') or {}).get('money') or 'no money section'}")
        return c
    gw = m.get("gateway") or {}
    pairs = (("order_equity_share", ml.get("order_equity_share"), gw.get("order_equity_share")),
             ("max_order_max_loss_usd", ml.get("max_order_max_loss_usd"), gw.get("order_max_loss_usd")),
             ("day_equity_share", ml.get("day_equity_share"), gw.get("day_equity_share")),
             ("credit_min_equity_usd", ml.get("credit_min_equity_usd"), m.get("credit_min_equity_usd")))
    bad = [f"{k} {a} vs the constitution's {b}" for k, a, b in pairs if b is not None and dec(a) != dec(b)]
    c.req(not bad, "the gateway's caps equal the constitution's" if not bad else "the gateway's caps differ: " + "; ".join(bad))
    c.info(f"opens admitted {ml.get('opens_admitted')}; orders today {ml.get('orders_today')}; real types {','.join(m.get('real_types') or [])}")
    return c


def check_account(h: Mapping[str, Any]) -> Check:
    c = Check(4, "account")
    g = h.get("gateway") or {}
    acct = g.get("account")
    if not acct:
        c.req(False, f"the account is unreadable: {g.get('account_error') or h.get('errors', {}).get('gateway')}")
    else:
        eq = dec(acct.get("equity"))
        c.req(eq is not None and eq > 0 and acct.get("status") == "ACTIVE", f"account status {acct.get('status')}, equity readable")
        c.req(not acct.get("trading_blocked") and not acct.get("account_blocked"),
              f"trading_blocked {acct.get('trading_blocked')}, account_blocked {acct.get('account_blocked')}")
        c.req(int(acct.get("options_trading_level") or 0) >= 3, f"options level {acct.get('options_trading_level')}")
    orders, pos = g.get("orders"), g.get("positions")
    c.info(f"open orders {len(orders) if orders is not None else 'unreadable'}; positions {len(pos) if pos is not None else 'unreadable'}")
    c.req(g.get("kill_switch") is False, f"kill switch {json.dumps(g.get('kill_switch'))}")
    live = (h.get("release") or {}).get("live") or {}
    stops = live.get("stops") or {}
    c.req(not stops.get("daily_tripped") and not stops.get("drawdown_tripped") and not stops.get("provisional"),
          f"House stops: daily {stops.get('daily_tripped')}, drawdown {stops.get('drawdown_tripped')}, provisional {stops.get('provisional') or 'none'}")
    c.req(not live.get("frozen"), f"real book frozen: {live.get('frozen') or 'no'}")
    return c


def budget_brake(gd: Mapping[str, Any], funded: bool, now: Any, stale_seconds: float) -> tuple[bool, str]:
    """A braked Sail guard, from its own record in the heartbeat: (the brake is THE BUDGET's daily stop and nothing else,
    what the line says). It is the budget's alone when the record itself is braked, every cause it names is one of the
    budget's daily caps (`league/swarm/guard.py` BUDGET_CAUSES; the names, never the reason's text), the balance was read
    above the line (`funded`), and that reading is fresh by the guard's own `stale_seconds`. No named cause (a record
    from before the list was kept, or a brake only the swarm's status says: no good reading) is cause unknown: never
    the budget's."""
    from ..swarm.guard import BUDGET_CAUSES, causes_of

    causes = causes_of(gd) if gd.get("braked") is True else None
    if not causes:
        return False, "braked True, cause unknown"
    if any(cause not in BUDGET_CAUSES for cause in causes):
        return False, "braked True, causes " + ", ".join(causes)
    said = "the day's " + " and ".join(cause.replace("_", " ") for cause in causes)
    if not funded:
        return False, f"braked True by {said}, and no balance read above the line"
    age = None if now is None or gd.get("at") is None else float(now) - float(gd["at"])
    if age is None or not 0 <= age < stale_seconds:
        return False, f"braked True by {said}, on a reading {ago(age)} old (no fresh reading of the balance)"
    return True, f"braked by {said} alone, as designed"


def check_swarm(h: Mapping[str, Any]) -> Check:
    c = Check(5, "swarm")
    s = h.get("swarm")
    if not s:
        c.req(False, "swarm unreadable: " + str(h.get("errors", {}).get("swarm")))
        return c
    sw = live_switches(s)
    c.req(s.get("raw_is_object") and isinstance(s.get("raw_live"), dict) and not sw["why"],
          f"swarm.json live: observe {sw['observe']}, observe_max {sw['observe_max']}, calibration {sw['calibration']}"
          + (f" ({sw['why']})" if sw["why"] else ""))
    eg = s.get("eff_gym") or {}
    c.req(eg.get("enabled") and eg.get("image_checkpoint") and eg.get("gate_checkpoint"),
          f"the Gym {'on' if eg.get('enabled') else 'OFF'}, image {str(eg.get('image_checkpoint') or '-')[:13]}, gate {str(eg.get('gate_checkpoint') or '-')[:13]}")
    c.req((s.get("alive") or 0) >= (s.get("floor") or 0), f"population {s.get('alive')} alive (floor {s.get('floor')})")
    age = s.get("heartbeat_age_s")
    c.req(fresh(age, MAX_AGE["heartbeat"]), f"heartbeat {ago(age)} old")
    cur = ((h.get("release") or {}).get("current")) or ""
    c.req(s.get("heartbeat_release") == cur, f"the swarm runs {Path(str(s.get('heartbeat_release'))).name}"
          + ("" if s.get("heartbeat_release") == cur else f" but current is {Path(cur).name}"))
    gd = s.get("guard") or {}
    braked = bool(gd.get("braked")) or (s.get("status") or {}).get("braked") is True
    bal, line = gd.get("balance"), gd.get("line")
    funded = bool(gd) and bal is not None and line is not None and bal > line
    # THE BUDGET's day is no alarm: under v3 the guard brakes for the rest of each UTC day once the day's research
    # dollars are spent. That brake alone passes, said plainly; the balance must still be read and above the line.
    budget, said = budget_brake(gd, funded, h.get("at"), float((s.get("eff_guard") or {}).get("stale_seconds", 600))) \
        if braked else (False, "braked False")
    ok, reason = funded and (not braked or budget), gd.get("reason")
    # The guard's reason holds the balance and the day's dollars as bare numbers, which the runner's scrub of the public
    # warning does not see: a passing line (never a warning) says it, a FAIL keeps it to a line only the receipt holds.
    c.req(ok, f"the Sail guard: balance vs line {usd(bal)} / {usd(line)}; {said}" + (f" ({reason})" if ok and reason else ""))
    if reason and not ok:
        c.info(f"the guard's reason: {reason}")
    return c


def check_bands(h: Mapping[str, Any]) -> Check:
    c = Check(6, "bands")
    b, s = h.get("bands"), h.get("swarm") or {}
    if not b:
        c.req(False, "the bands could not be read: " + str(h.get("errors", {}).get("bands")))
        return c
    sw = live_switches(s) if s else {"observe": False, "observe_max": 0}
    # The count is of the rows the swarm OFFERS (`league/swarm/bands.py` `observe`), not of the cohorts the live path has
    # pinned: a pass here is rows on offer, never a practice league seen running.
    c.req(b.get("observe") or not sw["observe"],
          f"observe rows the swarm offers: {b.get('observe')} (a count of rows on offer, not of cohorts the live path has "
          f"pinned or practises); the live path pins up to {sw['observe_max']}" if sw["observe"] else "observe is off for the live path")
    for r in b.get("read") or []:
        text = f"{r['band']} {r['family']} v{r['version']}: typical max loss {usd(r.get('typical_max_loss_usd'))}"
        if r["band"] in ("probe", "sized"):
            c.req(r.get("fits_probe") is True, text + f"; fits the Probe cap: {r.get('fits_probe')}")
        else:
            c.info(text)
    missing = b.get("live_missing_from_read") or []
    c.req(not missing, "every Candidate/Probe/Sized family has a band row" if not missing
          else f"live-band families with no band row: {missing}")
    return c


def check_mirror(h: Mapping[str, Any]) -> Check:
    c = Check(7, "mirror")
    m = h.get("mirror")
    if not m:
        c.req(False, "the mirror cursor or the swarm's events could not be read: " + str(h.get("errors", {}).get("mirror")))
        return c
    lag = m.get("lag")
    c.req(lag is not None and lag <= MIRROR_LAG_MAX, f"the House's mirror: cursor {m.get('cursor')}, events top {m.get('events_top_seq')}, "
                                                     f"lag {lag if lag is not None else '?'} (<= {MIRROR_LAG_MAX})")
    return c


def check_backup(h: Mapping[str, Any]) -> Check:
    c = Check(8, "backup")
    b = h.get("backup")
    if not b:
        c.req(False, "backup rows unreadable: " + str(h.get("errors", {}).get("backup")))
        return c
    latest = b.get("latest")
    c.req(bool(latest) and latest.get("ok") is True and latest["age_h"] <= MAX_AGE["backup_ok_h"],
          f"latest House backup {latest['at']} ({latest['age_h']}h ago): ok {latest.get('ok')}" if latest else "no House backup row")
    return c


def check_compute(h: Mapping[str, Any], now: float) -> Check:
    c = Check(9, "compute")
    g, s = h.get("gateway") or {}, h.get("swarm") or {}
    gd, cfg = s.get("guard") or {}, s.get("eff_guard") or {}
    sail = g.get("sail") or {}
    bal = sail.get("balance_usd") if sail.get("balance_usd") is not None else gd.get("balance")
    line = float(gd.get("line") or (2 * float(cfg.get("house_burn_usd_day", 1.0)) + float(cfg.get("margin_usd", 30.0))))
    hour = (s.get("status") or {}).get("spend_last_hour") or {}
    sail_h = float(hour.get("sail_model") or 0) + float(hour.get("gym_box") or 0)
    house_h = float(cfg.get("house_burn_usd_day", 1.0)) / 24
    to_close = max(0.0, (_next_close(now) - now) / 3600)
    projected = None if bal is None else float(bal) - (sail_h + house_h) * to_close
    c.req(bal is not None and float(bal) > line, f"Sail balance {usd(bal)} vs the ${line:.0f} line")
    c.req(projected is not None and projected > line, f"projected at the close, at the last hour's pace (${sail_h:.2f}/h for {to_close:.1f}h): {usd(projected)}")
    cl = g.get("claude") or {}
    cap_sw = (s.get("eff_claude") or {}).get("usd_cap")
    spent = dec(cl.get("spent_usd"))
    c.req(spent is not None and spent < (dec(cl.get("cap_usd")) or 0) and (cap_sw is None or spent < dec(cap_sw)),
          f"Claude spent {usd(spent)} of the gateway's {usd(cl.get('cap_usd'))} (swarm cap {usd(cap_sw)})")
    fr = g.get("frontier") or {}
    fs, fcap = dec(fr.get("spent_usd")), dec(fr.get("cap_usd"))
    c.req(fs is not None and fcap is not None and fs <= fcap, f"OpenAI spent {usd(fs)} of {usd(fcap)} this month")
    return c


def _next_close(now: float) -> float:
    from ltcm.data import DataError, next_session, to_datetime, us_equity_session

    try:
        session = us_equity_session(dt.datetime.fromtimestamp(now, dt.timezone.utc))
        if session is not None and to_datetime(session.close_at).timestamp() > now:
            return to_datetime(session.close_at).timestamp()
        session = next_session(dt.datetime.fromtimestamp(now, dt.timezone.utc))
        if session is not None:
            return to_datetime(session.close_at).timestamp()
    except DataError:
        pass
    return now


def checks(h: Mapping[str, Any], now: float) -> list[Check]:
    out = []
    for n, name, fn in ((1, "release", check_release), (2, "grant", check_grant), (3, "gateway", check_gateway),
                        (4, "account", check_account), (5, "swarm", check_swarm), (6, "bands", check_bands),
                        (7, "mirror", check_mirror), (8, "backup", check_backup), (9, "compute", None)):
        try:
            out.append(check_compute(h, now) if fn is None else fn(h))
        except Exception as exc:  # noqa: BLE001 - a check that breaks is that check's FAIL
            c = Check(n, name)
            c.req(False, f"the check itself broke: {type(exc).__name__}: {str(exc)[:200]}")
            out.append(c)
    return out


def run(ctx: Any) -> dict[str, Any]:
    now = ctx.now()
    with guard.readonly():
        h = collect(ctx.root, ctx.base, ctx.release, ctx.gateway, now=now, config=ctx.config)
    done = checks(h, now)
    failed = [c for c in done if not c.ok]
    for c in failed:
        ctx.alert("warning", f"preopen {c.n} {c.name} FAIL: {c.headline()}")
    return {"at": S.iso(now), "passed": len(done) - len(failed), "of": len(done),
            "failed": [f"{c.n} {c.name}" for c in failed], "checks": [c.row() for c in done],
            "read_errors": h.get("errors") or {}}
