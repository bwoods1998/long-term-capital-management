"""COST-7, PREREG-EVL-7 SECTION 2: THE COST BASIS OF PREREG-EVL-7's VERSIONS ONLY (`VERSIONS`, an explicit set, never
"prereg >= 7"; E11), and THE ONE NARROW INTERFACE through which those versions are judged by PREREG-EVL-6's screen
(`judge_record`). Standard library only. No frozen judge, no frozen program's cost, no column of `outcomes` and no line
of score.py's frozen costs changes: everything here is additive (`costs7`, `cost_basis`) and read only for the two
learners' judged returns.

THE PER-EVENT COST (section 2.1). For an event with entry session D:
- r7 = exit_px (1 - (M_out + FEE_out + IMP) / 1e4) / (entry_px (1 + (M_in + FEE_in + IMP) / 1e4)) - 1 - G / 1e4, the
  prices adjusted as score.py adjusts them; a7 = r7 - b (b as PREREG-EVL-1 section 5's, the outcome's own).
- IMP (bp a side) = 1e4 x 1.0 x sigma x sqrt(0.10 x E_prev / ADV20): SIGMA (E9) the event's sig20 (the sample sd of
  the 19 daily log changes of its 20 latest stored raw SIP closes of sessions before D), FLOORED AT 0.02 AND CAPPED AT
  0.25, 0.04 when fewer than 20 closes are stored (the universe row's `sigma60` is never read); ADV20 the universe
  row's; an event with no E_prev or no ADV20 is not TRADABLE.
- FEE (bp a side) = the larger of THE PENNY CEILING at the event's Probe size (n_ref = max(1, floor(PS x E_prev /
  (1.25 x prev_close))), PS = 0.035 FIXED HERE; N_in = n_ref x the raw entry print, N_out = n_ref x the raw exit print,
  N_in when the exit print is 0; FEE_in = 1e4 x $0.01 / N_in; FEE_out = 1e4 x ($0.01 + ceilcent($27.80e-6 x N_out) +
  ceilcent(min($0.000166 x n_ref, $8.30))) / N_out) and THE MEASURED RATE 1.25 x Fbar_side.
- M_in, M_out, G and Fbar: THE LATEST `cost_basis` ROW WRITTEN BEFORE THE LOOK IS COMPUTED (E11). M, G and Fbar only
  rise; the penny ceiling and the impact of an event are fixed at its own entry (`costs7`, written once).

THE MEASURED TERMS (section 2.2), one `cost_basis` row a night after the score and before the screen (`nightly`):
(a) SLIPPAGE: the real event fills' gaps as league/events/done.py measures them (entry (fill / raw shadow print - 1)
    x 1e4, exit (1 - fill / raw shadow print) x 1e4), over the trailing 250 fills of a side by fill time, once at least
    100 over at least 5 sessions: UCB = mean + 1.645 x SE (SE = the sd of the session means / sqrt(sessions)); M_side =
    max(2.5 bp, the previous M_side, UCB).
(b) SELECTION: every buy attempt of a seating program since Oct 20, 2026 in the attempt ledger (`real_attempts`,
    section 2.3; release 1019i's infrastructure writes it) whose shadow intent settled TRADABLE; per entry session n_s
    attempts, k_s fills, the means of the gross abnormal return a_g over the attempts and over the fills, v_s its
    population variance over the attempts; G_w = (1 / n_F) sum_s k_s (mA_s - mF_s), SE = sqrt(sum over 0 < k_s < n_s
    of k_s (n_s - k_s) / (n_s - 1) v_s) / n_F; at the CHECKPOINTS n_A = 100, 200, 400, ... (every doubling), each once
    every attempt through the n_A-th's entry session has settled and only with at least 10 unfilled:
    G = max(G, max(0, G_w - 0.84 SE)). G starts at 0 and is never lowered.
(c) A session whose attempt record is incomplete (a real event buy fill of it with no ledger row; every session while
    the store holds no ledger) is left out of (b), and its fills out of (a); the terms in force are kept and the
    row's `why` says so (the alarm reads it).
(d) NO ROW FOR THE NIGHT, or one that cannot be read: every look of these versions WAITS (`basis_for`).

THE JUDGED RECORD (section 3.1; `record7`, `control7`): a learner's settled TRADABLE intents OF DECISIONS MADE LIVE BY
THE HOUSE (league/events/learner.py kind `live`, never a catch-up's nor a late decision's), knowable after its
registration, each with a = a7 and r = r7; its control, the POOL record of those same live decisions (section 6),
valued on a7. `judge_record` hands them to PREREG-EVL-6's screen as frozen (league/events/screen.py `v6_judge` over
`blocks6`, PREREG-EVL-6's code), its ranking for the top-CAP guard the intents' rank_key (ahat). With no PREREG-EVL-6
screen in the tree (this branch alone), no look is judged: the answer says so and nothing moves."""

from __future__ import annotations

import datetime as dt
import json
import math
from decimal import ROUND_CEILING, Decimal
from typing import Any, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import store as S

#: E11: COST-7 applies to these versions only (PREREG-EVL-7's two ids at version 1; a later file says so for its own).
VERSIONS = frozenset({("EVL-LRN-O1", 1), ("EVL-LRN-ON", 1)})
PS = 0.035                  # section 2.1 (i): the Probe position share, FIXED HERE (never read from the money table)
CAT_USD = 0.01
SEC_RATE = 27.80e-6         # the SEC fee at the rate the equity book uses, on the sale's notional
TAF_RATE, TAF_MAX = 0.000166, 8.30
LIMIT_MULTIPLE = 1.25
IMPACT_COEF, SIZED_SHARE = 1.0, 0.10
SIG_FLOOR, SIG_CAP, SIG_MISSING = 0.02, 0.25, 0.04     # E9
CLOSES = 20
M_FLOOR = 2.5               # section 2.2 (a)
FILLS_TRAIL, FILLS_MIN, SESSIONS_MIN = 250, 100, 5
Z_UCB = 1.645
Z_G = 0.84                  # section 2.2 (b)
CHECKPOINT_FIRST = 100
UNFILLED_MIN = 10
FBAR_SCALE, FBAR_MIN, FBAR_SESSIONS = 1.25, 50, 20
SINCE = dt.date(2026, 10, 20)      # section 2.2 (b): the lane's first real buy
ATTEMPTS = "real_attempts"
SCHEMA = """
CREATE TABLE IF NOT EXISTS costs7(program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
  sigma REAL, adv20 REAL, e_prev REAL, prev_close REAL, n_ref INTEGER, raw_in REAL, raw_out REAL, fee_in_bp REAL,
  fee_out_bp REAL, imp_bp REAL, tradable INTEGER NOT NULL, at TEXT NOT NULL, PRIMARY KEY(program, version, event));
CREATE TABLE IF NOT EXISTS cost_basis(id INTEGER PRIMARY KEY AUTOINCREMENT, night TEXT NOT NULL, at TEXT NOT NULL,
  m_in REAL NOT NULL, m_out REAL NOT NULL, g_bp REAL NOT NULL, ucb_in REAL, ucb_out REAL, n_fill_in INTEGER,
  n_fill_out INTEGER, fbar_in REAL NOT NULL, fbar_out REAL NOT NULL, n_att INTEGER, n_unf INTEGER, g_w REAL, g_se REAL,
  checkpoints TEXT, incomplete TEXT, why TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS cost_basis_night ON cost_basis(night);
"""
TABLES = ("costs7", "cost_basis")


def ensure(db: Any) -> None:
    db.executescript(SCHEMA)


def applies(program: str, version: int) -> bool:
    """Whether COST-7 is the cost basis of (program, version): PREREG-EVL-7's explicit set only (E11)."""
    return (str(program), int(version)) in VERSIONS


# --------------------------------------------------------------------------------------------- the per-event parts
def ceilcent(usd: float) -> float:
    """Dollars rounded UP to the cent (the SEC fee's and FINRA TAF's own rounding)."""
    return float((Decimal(repr(float(usd))) * 100).to_integral_value(rounding=ROUND_CEILING) / 100)


def sigma7(closes: Sequence[float]) -> float:
    """E9's sigma from the latest raw closes (latest first): sig20 floored at 0.02 and capped at 0.25; 0.04 with fewer
    than 20 closes."""
    from .learner import sig20_of

    raw = sig20_of(list(closes))
    return SIG_MISSING if raw is None else min(SIG_CAP, max(SIG_FLOOR, raw))


def n_ref(equity: float, prev_close: float) -> int:
    """Section 2.1 (i): max(1, floor(PS x E_prev / (1.25 x prev_close)))."""
    return max(1, math.floor(PS * float(equity) / (LIMIT_MULTIPLE * float(prev_close))))


def penny(n: int, raw_in: float, raw_out: float) -> tuple[float, float]:
    """THE PENNY CEILING (section 2.1 (i)) in bp a side: (FEE_in, FEE_out) at n_ref shares."""
    n_in = n * float(raw_in)
    n_out = n * float(raw_out) if raw_out and raw_out > 0 else n_in
    fee_in = 1e4 * CAT_USD / n_in
    fee_out = 1e4 * (CAT_USD + ceilcent(SEC_RATE * n_out) + ceilcent(min(TAF_RATE * n, TAF_MAX))) / n_out
    return fee_in, fee_out


def impact_bp(sigma: float, equity: float, adv20: float) -> float:
    """IMP (section 2.1), bp a side: 1e4 x 1.0 x sigma x sqrt(0.10 x E_prev / ADV20)."""
    return 1e4 * IMPACT_COEF * float(sigma) * math.sqrt(SIZED_SHARE * float(equity) / float(adv20))


def r7(entry_px: float, exit_px: float, *, m_in: float, m_out: float, fee_in: float, fee_out: float, imp: float,
       g: float) -> float:
    return exit_px * (1.0 - (m_out + fee_out + imp) / 1e4) / (entry_px * (1.0 + (m_in + fee_in + imp) / 1e4)) - 1.0 - g / 1e4


def _closes(store: Any, symbol: str, day: dt.date) -> list[float]:
    from .learner import _closes as closes_of

    return closes_of(store, symbol, day)


def _equity(store: Any, day: dt.date) -> float | None:
    from . import score as SC

    prior = C.previous(store, day, 1)
    return SC.equity_on(store, prior[0].day) if prior else None


def _print(store: Any, symbol: str, day: str, label: str) -> float | None:
    row = store.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label=?", (symbol, day, label)).fetchone()
    try:
        px = float(row["px"])
    except (TypeError, ValueError, IndexError):
        return None
    return px if math.isfinite(px) else None


def fixed_parts(store: Any, program: str, version: int, event: str) -> dict[str, Any] | None:
    """THE PARTS OF AN EVENT'S COST FIXED AT ITS OWN ENTRY (section 2.1): sigma, ADV20, E_prev, prev_close, n_ref, the raw
    prints, the penny ceiling and the impact, from stored fields only; None while the event has no settled outcome."""
    o = store.db.execute("SELECT * FROM outcomes WHERE program=? AND version=? AND event=? AND status='settled'",
                         (program, int(version), event)).fetchone()
    i = store.db.execute("SELECT * FROM intents WHERE program=? AND version=? AND event=?",
                         (program, int(version), event)).fetchone()
    if o is None or i is None:
        return None
    symbol, entry_day = str(i["symbol"]).upper(), dt.date.fromisoformat(str(i["entry_day"]))
    uni = store.db.execute("SELECT prev_close, adv20 FROM universe WHERE day=? AND symbol=?",
                           (entry_day.isoformat(), symbol)).fetchone()
    equity = _equity(store, entry_day)
    prev = None if uni is None else uni["prev_close"]
    adv = None if uni is None else uni["adv20"]
    label_in = "close" if str(i["entry_at"]) == "close" else "open"
    raw_in = _print(store, symbol, entry_day.isoformat(), label_in)
    exit_day, exit_kind = str(i["exit_day"]), str(i["exit_at"])
    moved = store.meta(f"exit:{program}:{int(version)}:{event}")
    if moved:
        try:
            got = json.loads(moved)
            exit_day, exit_kind = str(got["day"]), str(got["kind"])
        except (ValueError, KeyError, TypeError):
            pass
    raw_out = 0.0 if exit_kind == "zero" else _print(store, symbol, exit_day, exit_kind)
    sigma = sigma7(_closes(store, symbol, entry_day))
    ok = equity is not None and equity > 0 and adv is not None and float(adv) > 0 and prev is not None and \
        float(prev) > 0 and raw_in is not None and raw_in > 0
    out: dict[str, Any] = {"program": program, "version": int(version), "event": event, "sigma": sigma,
                           "adv20": None if adv is None else float(adv), "e_prev": equity,
                           "prev_close": None if prev is None else float(prev), "n_ref": None, "raw_in": raw_in,
                           "raw_out": raw_out, "fee_in_bp": None, "fee_out_bp": None, "imp_bp": None, "tradable": 0}
    if not ok:
        return out
    n = n_ref(equity, float(prev))
    fee_in, fee_out = penny(n, raw_in, raw_out or 0.0)
    out.update(n_ref=n, fee_in_bp=fee_in, fee_out_bp=fee_out, imp_bp=impact_bp(sigma, equity, float(adv)),
               tradable=int(LIMIT_MULTIPLE * float(prev) <= 0.10 * equity))
    return out


def write_fixed(store: Any, parts: Mapping[str, Any], now: dt.datetime) -> bool:
    """A `costs7` row, once (INSERT OR IGNORE): the event's fixed parts never change."""
    cols = ("program", "version", "event", "sigma", "adv20", "e_prev", "prev_close", "n_ref", "raw_in", "raw_out",
            "fee_in_bp", "fee_out_bp", "imp_bp", "tradable")
    cur = store.db.execute(f"INSERT OR IGNORE INTO costs7({', '.join(cols)}, at) VALUES({', '.join('?' * len(cols))}, ?)",
                           tuple(parts[c] for c in cols) + (S.iso(now),))
    return cur.rowcount == 1


def costed(parts: Mapping[str, Any], outcome: Mapping[str, Any], basis: Mapping[str, Any]) -> tuple[float, float] | None:
    """(a7, r7) of an event under a `cost_basis` row (section 2.1), None when it is not TRADABLE under COST-7."""
    if not parts.get("tradable"):
        return None
    try:
        e_in, e_out, b = float(outcome["entry_px"]), float(outcome["exit_px"]), float(outcome["b"])
    except (TypeError, ValueError, KeyError):
        return None
    if not e_in > 0:
        return None
    fee_in = max(float(parts["fee_in_bp"]), FBAR_SCALE * float(basis["fbar_in"]))
    fee_out = max(float(parts["fee_out_bp"]), FBAR_SCALE * float(basis["fbar_out"]))
    r = r7(e_in, e_out, m_in=float(basis["m_in"]), m_out=float(basis["m_out"]), fee_in=fee_in, fee_out=fee_out,
           imp=float(parts["imp_bp"]), g=float(basis["g_bp"]))
    return r - b, r


# ---------------------------------------------------------------------------------------------- the measured terms
def basis_for(store: Any, before: dt.datetime | None = None) -> dict[str, Any] | None:
    """THE LATEST `cost_basis` ROW WRITTEN BEFORE THE LOOK IS COMPUTED (E11; `before` None: the latest), None when there
    is none or it cannot be read (section 2.2 (d): the look waits)."""
    try:
        if before is None:
            row = store.db.execute("SELECT * FROM cost_basis ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = store.db.execute("SELECT * FROM cost_basis WHERE at<? ORDER BY id DESC LIMIT 1",
                                   (S.iso(before),)).fetchone()
    except Exception:  # noqa: BLE001 - no table, or unreadable: no basis (the look waits)
        return None
    return None if row is None else dict(row)


def _has(store: Any, table: str) -> bool:
    return store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _session_of(store: Any, moment: Any) -> str | None:
    try:
        return S.parse_iso(str(moment)).astimezone(C.NY).date().isoformat()
    except (TypeError, ValueError):
        return None


def incomplete_sessions(store: Any) -> set[str]:
    """Section 2.2 (c): the sessions whose attempt record is incomplete: a real event BUY fill of the session with no
    row in the attempt ledger (`real_attempts`, by program, version, event and side buy); with no ledger at all, every
    session holding a real buy fill."""
    buys = [dict(r) for r in store.db.execute("SELECT program, version, event, filled_at FROM real_fills WHERE side='buy'")] \
        if _has(store, "real_fills") else []
    if not _has(store, ATTEMPTS):
        return {d for d in (_session_of(store, b["filled_at"]) for b in buys) if d}
    have = {(str(r[0]), int(r[1]), str(r[2])) for r in store.db.execute(
        f"SELECT program, version, event FROM {ATTEMPTS} WHERE side='buy'")}
    return {d for b in buys if (str(b["program"]), int(b["version"]), str(b["event"])) not in have
            for d in [_session_of(store, b["filled_at"])] if d}


def gaps(store: Any, skip: set[str]) -> dict[str, list[tuple[str, str, float]]]:
    """Section 2.2 (a)'s real fill gaps per side as league/events/done.py measures them (against the shadow's auction
    print made raw again), [(fill time, its session, gap bp)] by fill time; fills of `skip` sessions left out."""
    from . import done as DN
    from . import screen as SN

    out: dict[str, list[tuple[str, str, float]]] = {"buy": [], "sell": []}
    if not _has(store, "real_fills"):
        return out
    for f in store.db.execute("SELECT f.*, o.entry_px, o.exit_px, i.symbol, i.entry_day, i.exit_day FROM real_fills f JOIN "
                              "outcomes o ON o.program=f.program AND o.version=f.version AND o.event=f.event JOIN intents i "
                              "ON i.program=f.program AND i.version=f.version AND i.event=f.event WHERE o.status='settled' "
                              "ORDER BY f.filled_at, f.program, f.event").fetchall():
        day = _session_of(store, f["filled_at"])
        if day is None or day in skip:
            continue
        try:
            price = float(f["price"])
        except (TypeError, ValueError):
            continue
        symbol = str(f["symbol"])
        if f["side"] == "buy":
            shadow = float(f["entry_px"] or 0)
            if shadow > 0 and price > 0:
                raw = shadow / DN._ratio(store, symbol, str(f["entry_day"]))
                out["buy"].append((str(f["filled_at"]), day, (price / raw - 1.0) * 1e4))
        else:
            shadow = float(f["exit_px"] or 0)
            exit_day = SN.exit_overrides(store, str(f["program"]), int(f["version"])).get(str(f["event"]))
            exit_day = exit_day.isoformat() if exit_day is not None else str(f["exit_day"])
            if shadow > 0 and price > 0:
                raw = shadow / DN._ratio(store, symbol, exit_day)
                out["sell"].append((str(f["filled_at"]), day, (1.0 - price / raw) * 1e4))
    return out


def ucb(rows: Sequence[tuple[str, str, float]]) -> tuple[float | None, int]:
    """Section 2.2 (a): over the trailing FILLS_TRAIL fills of a side, once at least FILLS_MIN over at least
    SESSIONS_MIN sessions, mean + 1.645 x (the sd of the session means / sqrt(sessions)); (UCB or None, fills used)."""
    tail = list(rows)[-FILLS_TRAIL:]
    by: dict[str, list[float]] = {}
    for _, day, gap in tail:
        by.setdefault(day, []).append(gap)
    if len(tail) < FILLS_MIN or len(by) < SESSIONS_MIN:
        return None, len(tail)
    mean = math.fsum(g for _, _, g in tail) / len(tail)
    means = [math.fsum(v) / len(v) for _, v in sorted(by.items())]
    mu = math.fsum(means) / len(means)
    sd = math.sqrt(math.fsum((m - mu) ** 2 for m in means) / (len(means) - 1))
    return mean + Z_UCB * sd / math.sqrt(len(means)), len(tail)


def selection(attempts: Sequence[Mapping[str, Any]]) -> dict[str, float] | None:
    """Section 2.2 (b)'s G_w and its SE over `attempts` ({session, filled, a_g}): None with no fill."""
    by: dict[str, list[Mapping[str, Any]]] = {}
    for a in attempts:
        by.setdefault(str(a["session"]), []).append(a)
    n_f = sum(1 for a in attempts if a["filled"])
    if n_f == 0:
        return None
    terms, var = [], []
    for _, xs in sorted(by.items()):
        n, k = len(xs), sum(1 for a in xs if a["filled"])
        if k == 0:
            continue
        m_a = math.fsum(float(a["a_g"]) for a in xs) / n
        m_f = math.fsum(float(a["a_g"]) for a in xs if a["filled"]) / k
        terms.append(k * (m_a - m_f))
        if 0 < k < n:
            v = math.fsum((float(a["a_g"]) - m_a) ** 2 for a in xs) / n
            var.append(k * (n - k) / (n - 1) * v)
    g_w = math.fsum(terms) / n_f
    se = math.sqrt(math.fsum(var)) / n_f
    return {"g_w": g_w, "se": se, "n_f": n_f}


def attempts(store: Any, skip: set[str]) -> list[dict[str, Any]]:
    """Section 2.2 (b)'s population, in (entry session, send time, program, event) order: each first send of an event
    buy in the ledger since SINCE whose shadow intent of the same program, version and event settled TRADABLE, with
    whether real_fills holds its buy and its shadow a_g (a re-send is the same attempt); sessions of `skip` left out.
    Empty with no ledger."""
    from .learner import gross

    if not _has(store, ATTEMPTS):
        return []
    filled = {(str(r[0]), int(r[1]), str(r[2])) for r in store.db.execute(
        "SELECT program, version, event FROM real_fills WHERE side='buy'")} if _has(store, "real_fills") else set()
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for a in store.db.execute(f"SELECT a.program, a.version, a.event, a.day, a.sent_at, o.entry_px, o.exit_px, "
                              f"o.bench_entry, o.bench_exit, o.tradable, o.status FROM {ATTEMPTS} a LEFT JOIN outcomes o "
                              f"ON o.program=a.program AND o.version=a.version AND o.event=a.event WHERE a.side='buy' AND "
                              f"a.day>=? ORDER BY a.day, a.sent_at, a.program, a.event", (SINCE.isoformat(),)).fetchall():
        key = (str(a["program"]), int(a["version"]), str(a["event"]))
        if key in seen or str(a["day"]) in skip:
            continue
        seen.add(key)
        settled = a["status"] == "settled"
        out.append({"program": key[0], "version": key[1], "event": key[2], "session": str(a["day"]),
                    "settled": settled, "tradable": bool(a["tradable"]) if settled else None,
                    "filled": key in filled, "a_g": gross(dict(a)) if settled else None})
    return out


def checkpoints(population: Sequence[Mapping[str, Any]], done: Iterable[int], g: float) -> tuple[float, list[int], dict]:
    """Section 2.2 (b)'s CHECKPOINTS: n_A = 100, 200, 400, ... settled TRADABLE attempts, each once every attempt through
    the n_A-th's entry session has settled, with at least 10 unfilled: G = max(G, max(0, G_w - 0.84 SE)). Returns (G,
    the checkpoints done, the last figures)."""
    done = sorted(set(int(x) for x in done))
    counted = [a for a in population if a["settled"] and a["tradable"] and a["a_g"] is not None]
    last: dict[str, Any] = {}
    n_a = CHECKPOINT_FIRST
    while n_a <= len(counted):
        if n_a not in done:
            through = counted[n_a - 1]["session"]
            if any(not a["settled"] for a in population if a["session"] <= through):
                break
            upto = [a for a in counted if a["session"] <= through]
            unfilled = sum(1 for a in upto if not a["filled"])
            if unfilled >= UNFILLED_MIN:
                got = selection(upto)
                if got is not None:
                    g = max(g, max(0.0, (got["g_w"] - Z_G * got["se"]) * 1e4))
                    last = {"g_w": got["g_w"] * 1e4, "se": got["se"] * 1e4, "n_att": len(upto), "n_unf": unfilled}
                    done.append(n_a)
        n_a *= 2
    return g, done, last


def fbar(store: Any, side: str, now: dt.datetime) -> float | None:
    """Section 2.1 (ii)'s rate of one side tonight: 1e4 x the posted fees over qty x price of the real event fills of
    that side of lots BOUGHT AT PROBE SIZE OR ABOVE in the trailing 20 sessions; None until 50 such fills exist."""
    if not _has(store, "real_fills"):
        return None
    days = C.previous(store, now.astimezone(C.NY).date() + dt.timedelta(days=1), FBAR_SESSIONS)
    if not days:
        return None
    first = days[0].day.isoformat()
    rows = store.db.execute("SELECT f.qty, f.price, f.fee, f.filled_at FROM real_fills f JOIN real_fills b ON "
                            "b.program=f.program AND b.version=f.version AND b.event=f.event AND b.side='buy' WHERE "
                            "f.side=? AND b.band IN ('probe', 'sized') AND f.fee IS NOT NULL", (side,)).fetchall()
    use = [r for r in rows if (_session_of(store, r["filled_at"]) or "") >= first]
    if len(use) < FBAR_MIN:
        return None
    notional = math.fsum(float(r["qty"]) * float(r["price"]) for r in use)
    return 1e4 * math.fsum(float(r["fee"]) for r in use) / notional if notional > 0 else None


def nightly(store: Any, night: dt.date, now: dt.datetime) -> dict[str, Any]:
    """THE NIGHT'S `cost_basis` ROW (section 2.2), once a night (a night on record is kept), after the score and before
    the screen; and the `costs7` rows of every newly settled outcome of these versions and of their POOL records (the
    backfill of section 2.2 is the same pass: every outcome settled since REGISTERED_AT_7 without its row)."""
    ensure(store.db)
    have = store.db.execute("SELECT * FROM cost_basis WHERE night=?", (night.isoformat(),)).fetchone()
    if have is not None:
        return {"kept": dict(have)["id"]}
    prev = basis_for(store) or {"m_in": M_FLOOR, "m_out": M_FLOOR, "g_bp": 0.0, "fbar_in": 0.0, "fbar_out": 0.0,
                                "checkpoints": "[]"}
    skip = incomplete_sessions(store)
    fills = gaps(store, skip)
    u_in, n_in = ucb(fills["buy"])
    u_out, n_out = ucb(fills["sell"])
    m_in = max(M_FLOOR, float(prev["m_in"]), u_in if u_in is not None else M_FLOOR)
    m_out = max(M_FLOOR, float(prev["m_out"]), u_out if u_out is not None else M_FLOOR)
    pop = attempts(store, skip)
    try:
        done = json.loads(prev.get("checkpoints") or "[]")
    except ValueError:
        done = []
    g, done, last = checkpoints(pop, done, float(prev["g_bp"]))
    f_in = max(float(prev["fbar_in"]), fbar(store, "buy", now) or 0.0)
    f_out = max(float(prev["fbar_out"]), fbar(store, "sell", now) or 0.0)
    why = []
    if not _has(store, ATTEMPTS):
        why.append("no attempt ledger in the store: every session with a real buy is incomplete (section 2.2 (c))")
    elif skip:
        why.append(f"{len(skip)} sessions with an incomplete attempt record left out (section 2.2 (c))")
    row = {"night": night.isoformat(), "at": S.iso(now), "m_in": m_in, "m_out": m_out, "g_bp": g, "ucb_in": u_in,
           "ucb_out": u_out, "n_fill_in": n_in, "n_fill_out": n_out, "fbar_in": f_in, "fbar_out": f_out,
           "n_att": last.get("n_att", len(pop)), "n_unf": last.get("n_unf"), "g_w": last.get("g_w"),
           "g_se": last.get("se"), "checkpoints": json.dumps(done), "incomplete": json.dumps(sorted(skip)),
           "why": "; ".join(why) or None}
    written = 0
    with store.tx() as db:
        db.execute(f"INSERT OR IGNORE INTO cost_basis({', '.join(row)}) VALUES({', '.join('?' * len(row))})",
                   tuple(row.values()))
        for program, version, event in to_cost(store):
            parts = fixed_parts(store, program, version, event)
            if parts is not None:
                written += write_fixed(store, parts, now)
    return row | {"costs7_written": written}


def to_cost(store: Any) -> list[tuple[str, int, str]]:
    """The settled outcomes that need a `costs7` row: every one of these versions' and of their pool programs' (version
    1) for entry sessions from REGISTERED_AT_7's day, without one."""
    from .learner import POOLS

    if P.REGISTERED_AT_7 is None:
        return []
    first = S.parse_iso(P.REGISTERED_AT_7).astimezone(C.NY).date().isoformat()
    keys = [(p, v) for p, v in VERSIONS] + [(pid, 1) for pool in POOLS.values() for pid in pool]
    out = []
    for program, version in keys:
        for r in store.db.execute("SELECT o.event FROM outcomes o JOIN intents i ON i.program=o.program AND "
                                  "i.version=o.version AND i.event=o.event LEFT JOIN costs7 c ON c.program=o.program AND "
                                  "c.version=o.version AND c.event=o.event WHERE o.program=? AND o.version=? AND "
                                  "o.status='settled' AND i.entry_day>=? AND c.event IS NULL ORDER BY o.event",
                                  (program, version, first)):
            out.append((program, version, str(r[0])))
    return out


# ------------------------------------------------------------------------------------------------ the judged record
def _parts(store: Any, program: str, version: int, event: str) -> dict[str, Any] | None:
    row = store.db.execute("SELECT * FROM costs7 WHERE program=? AND version=? AND event=?",
                           (program, int(version), event)).fetchone() if _has(store, "costs7") else None
    return dict(row) if row is not None else fixed_parts(store, program, version, event)


def record7(store: Any, learner: P.Program, *, before: dt.datetime | None = None) -> list[dict[str, Any]] | None:
    """THE LEARNER'S JUDGED RECORD (section 3.1): its settled intents OF DECISIONS MADE LIVE BY THE HOUSE (learner_fits
    kind `live`), knowable after its registration, each {event, issuer, entry_day, exited, rank_key, adv20, decided_at,
    tradable, a: a7, r: r7} under the latest cost basis written before `before`; None when no basis row is on record
    (section 2.2 (d): the look waits). An event COST-7 holds untradable is in it with tradable 0."""
    from . import screen as SN

    basis = basis_for(store, before)
    if basis is None:
        return None
    reg = learner.registered_at
    moved = SN.exit_overrides(store, learner.id, learner.version)
    out = []
    for r in store.db.execute("SELECT i.event, i.cik, i.entry_day, i.exit_day, i.rank_key, i.decided_at, o.* FROM intents i "
                              "JOIN learner_fits f ON f.program=i.program AND f.version=i.version AND f.day=i.entry_day "
                              "JOIN outcomes o ON o.program=i.program AND o.version=i.version AND o.event=i.event WHERE "
                              "i.program=? AND i.version=? AND f.kind='live' AND o.status='settled' ORDER BY i.entry_day, "
                              "i.event", (learner.id, learner.version)).fetchall():
        known = knowable(store, str(r["event"]))
        if known is None or known <= reg:
            continue
        parts = _parts(store, learner.id, learner.version, str(r["event"]))
        got = costed(parts or {}, dict(r), basis) if (parts and r["tradable"]) else None
        uni = store.db.execute("SELECT MAX(adv20) FROM universe WHERE day=? AND cik=?", (r["entry_day"], r["cik"])).fetchone()
        scheduled = dt.date.fromisoformat(str(r["exit_day"]))
        out.append({"event": str(r["event"]), "issuer": str(r["cik"]), "entry_day": dt.date.fromisoformat(str(r["entry_day"])),
                    "exit_day": scheduled, "exited": moved.get(str(r["event"]), scheduled), "rank_key": r["rank_key"],
                    "adv20": None if uni is None else uni[0], "decided_at": r["decided_at"],
                    "tradable": int(got is not None), "a": None if got is None else got[0],
                    "r": None if got is None else got[1]})
    return out


def knowable(store: Any, event: str) -> dt.datetime | None:
    """An event's knowable time from the store (`8k:`/`f4:<accession>` a filing's, `news:<id>` an article's)."""
    kind, _, ident = str(event).partition(":")
    if kind in ("8k", "f4"):
        row = store.db.execute("SELECT knowable_at FROM filings WHERE accession=?", (ident,)).fetchone()
    elif kind == "news":
        row = store.db.execute("SELECT knowable_at FROM news WHERE id=?", (ident,)).fetchone()
    else:
        return None
    try:
        return None if row is None or row[0] is None else S.parse_iso(str(row[0]))
    except (TypeError, ValueError):
        return None


def control7(store: Any, learner: P.Program, *, before: dt.datetime | None = None) -> list[dict[str, Any]] | None:
    """THE POOL CONTROL (section 6) over the learner's LIVE decisions: for each, every kept candidate whose primary event
    is knowable after the registration time, with the POOL OUTCOME of its (D, issuer) (league/events/learner.py
    `pool_outcomes`, as of now) valued on a7; {entry_day, issuer, event, tradable, a, r}. None with no basis row."""
    from . import learner as LR

    basis = basis_for(store, before)
    if basis is None:
        return None
    reg = learner.registered_at
    now = S.utc_now() if before is None else before
    out = []
    days = [dt.date.fromisoformat(str(r[0])) for r in store.db.execute(
        "SELECT day FROM learner_fits WHERE program=? AND version=? AND kind='live' ORDER BY day",
        (learner.id, learner.version))]
    for day in days:
        outs = LR.pool_outcomes(store, learner, day, now)
        for c in store.db.execute("SELECT cik, event, knowable_at FROM learner_cands WHERE program=? AND version=? AND "
                                  "day=? AND kept=1 ORDER BY cik", (learner.id, learner.version, day.isoformat())):
            try:
                if S.parse_iso(str(c["knowable_at"])) <= reg:
                    continue
            except (TypeError, ValueError):
                continue
            o = outs.get(str(c["cik"]))
            if o is None:
                continue
            row = store.db.execute("SELECT * FROM outcomes WHERE program=? AND version=1 AND event=?",
                                   (o["program"], o["event"])).fetchone()
            parts = _parts(store, str(o["program"]), 1, str(o["event"]))
            got = costed(parts or {}, dict(row), basis) if (parts and row is not None and row["tradable"]) else None
            exited = store.db.execute("SELECT exit_day FROM intents WHERE program=? AND version=1 AND event=?",
                                      (o["program"], o["event"])).fetchone()
            out.append({"entry_day": day, "issuer": str(c["cik"]), "event": str(o["event"]), "program": str(o["program"]),
                        "exited": dt.date.fromisoformat(str(exited[0])) if exited is not None else day,
                        "tradable": int(got is not None), "a": None if got is None else got[0],
                        "r": None if got is None else got[1]})
    return out


def judge_record(rows: Sequence[Mapping[str, Any]], control_rows: Sequence[Mapping[str, Any]] | None, *, program: str,
                 version: int, tag: str = "") -> dict[str, Any]:
    """THE ONE NARROW INTERFACE TO PREREG-EVL-6's SCREEN (section 3.1, E1): one look of a learner version's record
    (`record7`'s rows covered by the look's as-of close) with its POOL control (`control7`'s), judged by PREREG-EVL-6's
    sections 1-3 AS FROZEN: league/events/screen.py `v6_judge` over `blocks6` (PREREG-EVL-6's code), the version a READ
    version whose control is its POOL record. With no PREREG-EVL-6 screen in this tree, nothing is judged
    ({decision: None, why}). The code never edits the judge that judges it."""
    from . import screen as SN

    judge, blocks = getattr(SN, "v6_judge", None), getattr(SN, "blocks6", None)
    if judge is None or blocks is None:
        return {"decision": None, "why": "PREREG-EVL-6's screen is not in this tree: no look of PREREG-EVL-7 is judged"}
    return judge(blocks(rows), program=program, version=int(version), tag=tag, control_rows=list(control_rows or []),
                 control=f"{program}-POOL")


__all__ = ["VERSIONS", "PS", "applies", "ceilcent", "sigma7", "n_ref", "penny", "impact_bp", "r7", "fixed_parts",
           "write_fixed", "costed", "basis_for", "incomplete_sessions", "gaps", "ucb", "selection", "attempts",
           "checkpoints", "fbar", "nightly", "to_cost", "record7", "control7", "judge_record", "SCHEMA", "TABLES", "knowable",
           "ensure", "SIG_FLOOR", "SIG_CAP", "SIG_MISSING", "M_FLOOR"]
