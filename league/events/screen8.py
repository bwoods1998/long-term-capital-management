"""PREREG-EVL-8 SECTION 5: THE PX SCREEN AND THE META SCREEN, this file's judge (new code beside league/events/screen.py,
behind league/ci.py's wall; PREREG-EVL-1 to -7's paths intact: PREREG-EVL-8 section 5.3). Standard library only.

THE ONE NARROW INTERFACE (`judge_blocks`): PREREG-EVL-6 sections 1.2-1.4 AS FROZEN (docs/prereg/PREREG-EVL-6.md at tag
prereg-evl-6, sha256 0f67f94ecac93f6b5542654e33ce5180fdbac254238badd571a37bcb0950f057), WORD FOR WORD, with ONE
reading F4 gives this file's versions: the frozen text's 14 in the values y_s = min(n_s, 14) x (B_s - 0.0010), in the
lower tail and in THE MONEY'S EVENTS is THE OPEN CAP OF THE VERSION'S BAND at the look (`CAP`: 4 for a PX version's run,
judged in learning, by its money row event.max_open_v8.learning; 8 for a meta-learner's run; 14 for a Probe stay; 8
for a Sized stay). Every other figure is the frozen one: the looks at S_k = 22, 25, 30, 35, 40, 50, 60 blocks (F1: the
frozen 22nd block is the PX seats' first look too), alpha(S) 0.020 / 0.006 / 0.001, the exact count at S <= 16 and the
Monte Carlo over 99,999 vectors of the seed string f"{id}|v{version}|evl6|{tag}S{S}" (this file's ids), RETIRE first
(mean a < 0 and q <= alpha + 1e-12), PASS (p <= alpha, no tolerance; >= 30 TRADABLE events and >= 30 issuers, >= 6
blocks; mean a > 0, mean r > 0; the money's events' pooled mean a > 0 and mean r > 0; the control condition; p_I <=
0.10). The sign-flip primitives are league/events/screen.py's own (`_count`, `_flips`, `seed_of`, `issuer_values`,
`control_mean`): nothing of PREREG-EVL-6's arithmetic is copied but its two new pieces (the exact count over all 2^S
vectors and alpha(S)); league/tests/test_events_evl8.py holds `judge_blocks` at cap 14 equal to PREREG-EVL-6's
`screen.v6_judge` wherever the tree carries it.

THE RUNS, STAYS AND DEMOTION (section 5.1-5.2, F2, F3, F12; PREREG-EVL-6 section 3 as frozen): run 1 from the version's
registration; a run ends at its PASS, its RETIRE or its 60th block, never the version (F2); run n + 1 is charged 0.13
when it starts and starts only when the lane's budget (3.9, the SEATING sum of every seatable version and run) holds it,
in registration order (`start_runs`); a Probe stay's fixed reads at every 100th real-money Probe+ event (p <= 0.15 for a
mean below zero), the money stop (10% of the stay's buy cost) and the stay's looks (its lower tail demotes; its PASS with
>= 30 at-size real events of positive summed P&L and fills within 15 bp moves Probe to Sized), in that order at each
close (`review8`). The runs' and looks' records use PREREG-EVL-6's own keys (meta `evl6:run:...`, `evl6:end:...`; a
look's k is 1000 n + S, a stay's 1,000,000 + 1000 n + S), so a tree with PREREG-EVL-6's code counts this file's runs in
the same budget.

THE RECORD of a PX seat is the shadow of its LIVE decisions (league/events/px.py `judged_days`: a catch-up's intents are
never a judged block) with the hourly re-decision's removals, its events knowable after REGISTERED_AT_8; its control is
CTRL-PX-ALL-ON / -O1 (screen.CONTROLS is not edited: `CONTROL_OF`). A meta-learner's record is its own settled TRADABLE
picks of its LIVE decisions; its control its POOL (league/events/meta.py `pool_rows`). THE PLACEBOS and THE CANARY
(section 3.3) are screened by THE PX SCREEN without its control condition, records only (`audit`): a placebo never moves
a band. NOTHING HERE RUNS while REGISTERED_AT_8 is None."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import screen as SN
from . import store as S

# ----------------------------------------------------------------------------------------------------- the constants
LOOKS: tuple[int, ...] = (22, 25, 30, 35, 40, 50, 60)
ALPHAS: tuple[tuple[int, float], ...] = ((30, 0.020), (40, 0.006), (60, 0.001))
MARGIN = 0.0010
MIN_EVENTS = 30
MIN_ISSUERS = 30
MIN_BLOCKS = 6
ISSUER_P = 0.10
EXACT = 16
RUN_BLOCKS = 60
TIE = SN.TIE
B = SN.B
#: F4: THE CAP of a look, by the version's part and the band it is judged in.
CAP = {"px": {"run": 4, "probe": 14, "sized": 8}, "meta": {"run": 8, "probe": 14, "sized": 8}}
#: Section 6.6 (F12): every version and every fresh run 0.13, the lane's budget 3.9, in hundredths.
CHARGE_HUNDREDTHS = 13
BUDGET_HUNDREDTHS = 390
#: Section 6.6's three ways of the count beside this file's: the base model and the stresses' worst, a run.
BASE_HUNDREDTHS = {"px": 2, "meta": 1}
STRESS_HUNDREDTHS = {"px": 15, "meta": 4}
PER_VERSION = {"px": 0.214, "meta": 0.063}
#: PREREG-EVL-6 section 3: the fixed reads, the money stop, Sized's real-money conditions.
READ_EVERY = 100
READ_P = 0.15
STOP_SHARE = 0.10
SIZED_MIN = 30
FILL_BP = 15.0
STUCK_AFTER = 6
#: The record's keys (PREREG-EVL-6's own formats: a tree with its code reads this file's runs in the same budget).
RUN_KEY = "evl6:run:{program}:{version}:{n}"
END_KEY = "evl6:end:{program}:{version}:{n}"
STAY_KEY = "evl8:stay:{program}:{version}:{n}"
STAY_BASE = 1_000_000
#: Section 3.2: the PX seats' controls (the control condition); the meta-learners' is their POOL.
CONTROL_OF = {"PX-DROP-ON": "CTRL-PX-ALL-ON", "PX-SURGE-ON": "CTRL-PX-ALL-ON", "PX-GAP-O1": "CTRL-PX-ALL-O1"}
#: px.sqlite's audit key of a placebo's or the canary's last look written.
AUDIT_CANARY = ("CTRL-PX-ALL-ON", "CTRL-PX-ALL-O1")


# ----------------------------------------------------------------------------------------------------- the test
def alpha(S_: int) -> float | None:
    """alpha(S) by the record's own S; None below the 22nd block or above the 60th."""
    S_ = int(S_)
    if S_ < LOOKS[0] or S_ > RUN_BLOCKS:
        return None
    for upper, a in ALPHAS:
        if S_ <= upper:
            return a
    return None


def tag(kind: str, n: int) -> str:
    """"" for run 1, f"run{n}|" for run n >= 2, f"stay{n}|" for the n-th Probe stay."""
    if kind == "stay":
        return f"stay{int(n)}|"
    return "" if int(n) == 1 else f"run{int(n)}|"


def seed_string(program: str, version: int, tg: str, S_: int) -> str:
    return f"{program}|v{int(version)}|evl6|{tg}S{int(S_)}"


def look_key(kind: str, n: int, S_: int) -> int:
    return (STAY_BASE if kind == "stay" else 0) + 1000 * int(n) + int(S_)


def key_of(k: int) -> tuple[str, int, int]:
    k = int(k)
    kind = "stay" if k >= STAY_BASE else "run"
    rest = k - (STAY_BASE if kind == "stay" else 0)
    return kind, rest // 1000, rest % 1000


def _exact_flips(n: int) -> Iterable[bytes]:
    width = (n + 7) // 8
    return (b.to_bytes(width, "little") for b in range(1 << n))


def count_p(values: Sequence[float], seed_text: str, draws: int = B) -> float:
    """PREREG-EVL-6 section 1.3's one-sided sign-flip p of mean(values) > 0: EXACT over all 2^S vectors for S <= 16,
    else the Monte Carlo (1 + count) / (1 + draws) over `draws` vectors of the seed string's seed."""
    vals = SN._check_values(values)
    n = len(vals)
    if n <= EXACT:
        return SN._count(vals, _exact_flips(n)) / float(1 << n)
    return (1 + SN._count(vals, SN._flips(SN.seed_of(seed_text), n, draws))) / (1 + int(draws))


@dataclasses.dataclass(frozen=True)
class Block8:
    """One block of a record: its entry session and its TRADABLE events in the program's ranking order."""

    day: dt.date
    events: tuple[Mapping[str, Any], ...]

    @property
    def n(self) -> int:
        return len(self.events)

    @property
    def value(self) -> float:
        return math.fsum(float(e["a"]) for e in self.events) / len(self.events)

    @property
    def mean_r(self) -> float:
        return math.fsum(float(e["r"]) for e in self.events) / len(self.events)

    def top(self, cap: int) -> tuple[Mapping[str, Any], ...]:
        return self.events[:int(cap)]


def rank_order(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Section 1.4's order of a session's events: rank_key descending (a missing key last), then adv20 descending (a
    missing one 0), then the event id."""
    rank = row.get("rank_key")
    adv = row.get("adv20")
    return (rank is None, -(float(rank) if rank is not None else 0.0), -(float(adv) if adv is not None else 0.0),
            str(row.get("event")))


def blocks(rows: Iterable[Mapping[str, Any]]) -> list[Block8]:
    """Every entry session with at least one TRADABLE event, in session order, its events in the ranking order."""
    groups: dict[dt.date, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("tradable") not in (True, 1):
            continue
        a, r = row.get("a"), row.get("r")
        if a is None or r is None or not (math.isfinite(float(a)) and math.isfinite(float(r))):
            raise ValueError(f"event {row.get('event')} has no finite a and r")
        groups.setdefault(SN._day(row["entry_day"]), []).append(row)
    return [Block8(day, tuple(sorted(g, key=rank_order))) for day, g in sorted(groups.items())]


def values(blks: Sequence[Block8], cap: int) -> list[float]:
    """y_s = min(n_s, CAP) x (B_s - 0.0010) (F4's cap)."""
    return [min(b.n, int(cap)) * (b.value - MARGIN) for b in blks]


def lower(blks: Sequence[Block8], cap: int) -> list[float]:
    """The lower tail's values: -min(n_s, CAP) x B_s (no margin)."""
    return [-min(b.n, int(cap)) * b.value for b in blks]


def _mean(xs: Sequence[float]) -> float | None:
    return math.fsum(xs) / len(xs) if xs else None


def judge_blocks(blks: Sequence[Block8], *, cap: int, program: str, version: int, tag: str = "",
                 control_rows: Sequence[Mapping[str, Any]] | None = None, control: str | None = None,
                 draws: int = B) -> dict[str, Any]:
    """ONE LOOK OF PREREG-EVL-6 (sections 1.3-1.4) WITH F4's CAP on a record's blocks: {S, alpha, p, q, p_issuer, guards,
    decision ("retire" | "pass" | None), why, cap, ...}. RETIRE first (nothing else is checked when it holds); PASS
    needs every condition. `control` with `control_rows` (its settled rows of these sessions, knowable after the
    version's registration): the control condition; None (a placebo, the canary): none."""
    S_ = len(blks)
    a_ = alpha(S_)
    events = [e for b in blks for e in b.events]
    issuers = SN.issuer_values(events)
    mean_a = _mean([float(e["a"]) for e in events])
    mean_r = _mean([float(e["r"]) for e in events])
    tops = [e for b in blks for e in b.top(cap)]
    top_a = _mean([float(e["a"]) for e in tops])
    top_r = _mean([float(e["r"]) for e in tops])
    weights = [min(b.n, int(cap)) for b in blks]
    money_a = (math.fsum(w * b.value for w, b in zip(weights, blks)) / sum(weights)) if weights else None
    block_mean = _mean([b.value for b in blks])
    text = seed_string(program, version, tag, S_)
    out: dict[str, Any] = {"S": S_, "alpha": a_, "tag": tag, "seed": text, "cap": int(cap), "n": len(events),
                           "issuers": len(issuers), "mean_a": mean_a, "mean_r": mean_r, "money_a": money_a,
                           "top": {"cap": int(cap), "n": len(tops), "mean_a": top_a, "mean_r": top_r},
                           "block_mean": block_mean, "p": None, "q": None, "p_issuer": None, "control": None,
                           "guards": {}, "decision": None, "why": ""}
    if S_ == 0:
        out["why"] = "no block"
        return out
    p = count_p(values(blks, cap), text, draws)
    q = count_p(lower(blks, cap), text, draws)
    p_i = SN.signflip_p([v for _, v in issuers], SN.seed_of(text + "|issuer"), draws)
    out.update(p=p, q=q, p_issuer=p_i)
    c_mean = None
    if control is not None:
        c_mean, c_blocks = SN.control_mean(control_rows or [], [b.day for b in blks])
        out["control"] = {"program": control, "mean_block": c_mean, "blocks": c_blocks, "program_mean_block": block_mean}
    if a_ is None:
        out["why"] = f"no look at {S_} blocks (looks from the {LOOKS[0]}nd block to the {RUN_BLOCKS}th)"
        return out
    if mean_a is not None and mean_a < 0 and q <= a_ + TIE:
        out.update(decision="retire", why=f"RETIRE: mean a {mean_a:.6f} < 0 and q {q:.6f} <= alpha {a_:.3f}")
        return out
    guards = {"p": p <= a_, "events": len(events) >= MIN_EVENTS, "issuers": len(issuers) >= MIN_ISSUERS,
              "blocks": S_ >= MIN_BLOCKS, "mean_a": mean_a is not None and mean_a > 0,
              "mean_r": mean_r is not None and mean_r > 0, "top_a": top_a is not None and top_a > 0,
              "top_r": top_r is not None and top_r > 0, "issuer": p_i <= ISSUER_P}
    if control is not None:
        guards["control"] = c_mean is not None and block_mean is not None and block_mean > c_mean
    out["guards"] = guards
    fails = [k for k, ok in guards.items() if not ok]
    if not fails:
        out.update(decision="pass", why=f"PASS: p {p:.6f} <= alpha {a_:.3f}, every guard holds (cap {cap})")
    else:
        out["why"] = "fail: " + ", ".join(fails)
    return out


def minimums(n: int, issuers: int, S_: int) -> bool:
    return n >= MIN_EVENTS and issuers >= MIN_ISSUERS and S_ >= MIN_BLOCKS


def part_of(prog: Any) -> str:
    return "meta" if P.is_meta8(prog) else "px"


def cap_of(prog: Any, kind: str, band: str = "learning") -> int:
    """F4: a run's cap (judged in learning: 4 PX, 8 META), a stay's at its band (Probe 14, Sized 8)."""
    return CAP[part_of(prog)]["run" if kind == "run" else ("sized" if band == "sized" else "probe")]


# ----------------------------------------------------------------------------------------------------- the records
def _knowable(store: Any, event: str) -> dt.datetime | None:
    from . import meta as MT

    return MT.event_knowable(store, event)


def record_rows(store: Any, prog: Any) -> list[dict[str, Any]]:
    """A version's judged rows (section 5): its settled events of LIVE decisions only, knowable after its registration,
    each with its intent's `rank_key` and `decided_at` and the issuer's `adv20` on the entry session."""
    from . import meta as MT
    from . import px as PXL

    rows = SN.settled_rows(store, prog.id, prog.version)
    if not rows:
        return []
    reg = prog.registered_at
    extra = {str(r["event"]): (r["rank_key"], r["decided_at"]) for r in store.db.execute(
        "SELECT event, rank_key, decided_at FROM intents WHERE program=? AND version=?", (prog.id, int(prog.version)))}
    if P.is_meta8(prog):
        live = {str(r[0]) for r in store.db.execute("SELECT day FROM mrl_decisions WHERE program=? AND version=? AND "
                                                    "kind='live' AND status='ok'", (prog.id, prog.version))} \
            if MT.has_tables(store.db) else set()
        adv = {(str(r["day"]), str(r["cik"])): r["adv20"] for r in store.db.execute(
            "SELECT day, cik, adv20 FROM mrl_pool WHERE program=? AND version=?", (prog.id, prog.version))} \
            if MT.has_tables(store.db) else {}
    else:
        db = PXL.read_only(store.root) if hasattr(store, "root") else None
        try:
            live = PXL.judged_days(db, PXL.auction_of(prog)) if db is not None else set()
            adv = {(str(r["day"]), str(r["cik"])): r["adv20"] for r in db.execute(
                "SELECT day, cik, adv20 FROM px_universe WHERE rule='live'")} if db is not None else {}
        finally:
            if db is not None:
                db.close()
    out = []
    for r in rows:
        day = r["entry_day"].isoformat()
        if day not in live:
            continue
        k = _knowable(store, str(r["event"]))
        if k is None or k <= reg:
            continue
        rank, decided = extra.get(str(r["event"]), (None, None))
        out.append(dict(r) | {"rank_key": rank, "decided_at": decided, "adv20": adv.get((day, str(r["issuer"])))})
    return out


def control_rows(store: Any, prog: Any) -> list[dict[str, Any]] | None:
    """A version's control record: a PX seat's control's settled rows of live decisions knowable after the seat's
    registration; a meta-learner's POOL (league/events/meta.py `pool_rows`)."""
    from . import meta as MT

    if P.is_meta8(prog):
        return MT.pool_rows(store, prog)
    ctl = CONTROL_OF.get(prog.id)
    if ctl is None:
        return None
    c = P.BY_KEY.get((ctl, 1))
    return [] if c is None else record_rows(store, c)


# ----------------------------------------------------------------------------------------------------- the runs
def _meta_json(store: Any, key: str) -> dict[str, Any] | None:
    raw = store.meta(key) if hasattr(store, "meta") else None
    try:
        got = json.loads(raw) if raw else None
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def runs(store: Any, prog: Any) -> list[dict[str, Any]]:
    """The version's runs: [{n, after_day, after, started, ended}] (run 1 needs no record; a fresh run is the one
    `start_runs` wrote). A run ends at a written look that passed or retired, or at its 60th block's end record."""
    out = [{"n": 1, "after_day": None, "after": None, "started": None, "ended": None}]
    n = 2
    while True:
        rec = _meta_json(store, RUN_KEY.format(program=prog.id, version=int(prog.version), n=n))
        if rec is None:
            break
        out.append({"n": n, "after_day": rec.get("after_day"), "after": rec.get("after"), "started": rec.get("started"),
                    "ended": None})
        n += 1
    looks = {int(r["k"]): r for r in SN.look_rows(store, prog.id, prog.version)}
    for run in out:
        for k, r in sorted(looks.items()):
            kind, rn, _ = key_of(k)
            if kind == "run" and rn == run["n"]:
                d = (SN.look_detail(store, prog.id, prog.version, k) or {}).get("v6") or {}
                if d.get("decision") in ("pass", "retire"):
                    run["ended"] = {"why": d["decision"], "at": str(r["at"])}
        end = _meta_json(store, END_KEY.format(program=prog.id, version=int(prog.version), n=run["n"]))
        if run["ended"] is None and end is not None:
            run["ended"] = {"why": "horizon", "at": end.get("at"), "last_day": end.get("last_day")}
    return out


def _after(row: Mapping[str, Any], moment: dt.datetime | None) -> bool:
    if moment is None:
        return True
    try:
        return S.parse_iso(str(row["decided_at"])) > moment
    except (KeyError, TypeError, ValueError):
        return False


def run_record(rows: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    after_day = dt.date.fromisoformat(str(run["after_day"])) if run.get("after_day") else None
    after = S.parse_iso(str(run["after"])) if run.get("after") else None
    return [r for r in rows if (after_day is None or SN._day(r["entry_day"]) > after_day) and _after(r, after)]


def written(store: Any, prog: Any, kind: str, n: int) -> dict[str, Any]:
    """The looks on record of one run or stay: {consumed (1-based thresholds used), last (as-of day), S}."""
    consumed: set[int] = set()
    last: dt.date | None = None
    top = 0
    for r in SN.look_rows(store, prog.id, prog.version):
        k = int(r["k"])
        knd, rn, s = key_of(k)
        if knd != kind or rn != int(n):
            continue
        d = SN.look_detail(store, prog.id, prog.version, k) or {}
        consumed |= {int((d.get("v6") or {}).get("look", 0))} | {int(x) for x in d.get("merged") or []}
        day = S.parse_iso(str(r["at"])).astimezone(C.NY).date()
        last = day if last is None or day > last else last
        top = max(top, s)
    consumed.discard(0)
    return {"consumed": consumed, "last": last, "S": top}


def schedule(store: Any, record: Sequence[Mapping[str, Any]], today: dt.date, *,
             pending: Sequence[tuple[dt.date, dt.date]] = (), consumed: Iterable[int] = (),
             after: dt.date | None = None, final: tuple[dt.date | None, str] | None = None) -> dict[str, Any]:
    """Section 2's looks of one run (or stay) from where the record on file left it (PREREG-EVL-6's schedule)."""
    out: dict[str, Any] = {"looks": [], "horizon": None, "stopped": None, "why": None}
    if not record:
        return out
    used = set(int(k) for k in consumed)
    j = max(used) if used else 0
    first = min(SN._day(r["entry_day"]) for r in record)
    for s in C.sessions(store, first, today):
        if after is not None and s.day <= after:
            continue
        if any(x <= s.day for _, x in pending):
            out["stopped"], out["why"] = s.day, f"an intent scheduled to exit by {s.day.isoformat()} has not settled"
            break
        every = blocks(SN.covered(record, s.day))
        blk = every[:RUN_BLOCKS]
        S_ = len(blk)
        events = [e for b in blk for e in b.events]
        held = j < len(LOOKS) and S_ >= LOOKS[j] and minimums(len(events), len({str(e["issuer"]) for e in events}), S_)
        horizon = len(every) >= RUN_BLOCKS
        if (held or horizon) and final is not None and (final[0] is None or s.day > final[0]):
            what = f"look {j + 1}" if held else "the run's 60th block"
            out["stopped"], out["why"] = s.day, f"{what} falls due at {s.day.isoformat()}, not final yet: {final[1]}"
            break
        if held:
            reached = [i for i in range(j, len(LOOKS)) if S_ >= LOOKS[i]]
            out["looks"].append((reached[0] + 1, s.day, [i + 1 for i in reached[1:]], S_))
            j = reached[-1] + 1
        if horizon:
            out["horizon"] = (s.day, every[RUN_BLOCKS - 1].day)
            break
    return out


def look_row(prog: Any, kind: str, n: int, k: int, merged: list[int], at: Any, days: int,
             judged: Mapping[str, Any]) -> dict[str, Any]:
    """A look as screen.write_look writes it (its `v6` detail carries the cap)."""
    decision = judged.get("decision")
    return {
        "program": prog.id, "version": int(prog.version), "k": look_key(kind, n, judged["S"]),
        "at": S.iso(at) if isinstance(at, dt.datetime) else str(at), "sessions": int(days), "n": judged["n"],
        "issuers": judged["issuers"], "blocks": judged["S"], "mean_a": judged["mean_a"], "mean_r": judged["mean_r"],
        "mean_a_tradable": judged["mean_a"], "p": judged["p"], "alpha": judged["alpha"], "fp_check": None, "held": 1,
        "passed": int(decision == "pass"), "why": str(judged["why"])[:400],
        "issuer": {"p": judged["p_issuer"], "alpha": ISSUER_P}, "control": judged.get("control"), "skew": None,
        "beside": None, "retirement": {"retire": decision == "retire", "q": judged["q"]}, "merged": list(merged),
        "v6": {"rule": "PREREG-EVL-6 with PREREG-EVL-8's F4 cap", "kind": kind, "n": int(n), "tag": judged["tag"],
               "look": int(k), "S": judged["S"], "seed": judged["seed"], "p": judged["p"], "q": judged["q"],
               "p_issuer": judged["p_issuer"], "alpha": judged["alpha"], "guards": judged.get("guards"),
               "top": judged.get("top"), "cap": judged.get("cap"), "money_a": judged.get("money_a"),
               "block_mean": judged.get("block_mean"), "decision": decision}}


def on_look(store: Any, look: Mapping[str, Any], *, now: Any = None, db: Any = None) -> str | None:
    """A look's move (PREREG-EVL-6 section 1.4 and 3), in the look's own transaction: a RUN's RETIRE retires the version,
    its PASS moves `learning` to `probe`; a STAY's RETIRE demotes it to `learning`, its PASS with the real-money
    conditions moves `probe` to `sized`."""
    from . import bands as BA

    key = (str(look["program"]), int(look["version"]))
    if key not in BA.seating():
        return None
    v6 = look.get("v6") or {}
    decision = v6.get("decision")
    band = BA.bands(store)[key]
    at = str(look["at"])
    tg = v6.get("tag") or ""
    if v6.get("kind") == "stay":
        if decision == "retire" and band in BA.PROBE_PLUS:
            if BA.set_band(store, key[0], key[1], "learning", since=at, now=now, db=db,
                           why=f"stay look {tg}S{v6.get('S')}: mean a < 0, q <= alpha (PREREG-EVL-8 section 5, "
                               "PREREG-EVL-6 section 3, demotion 2)"):
                return "learning"
        if decision == "pass" and band == "probe" and (v6.get("sized") or {}).get("ok"):
            if BA.set_band(store, key[0], key[1], "sized", since=at, now=now, db=db,
                           why=f"stay look {tg}S{v6.get('S')} passed with its real-money conditions (Sized)"):
                return "sized"
        return None
    if decision == "retire":
        if BA.set_band(store, key[0], key[1], "retired", since=at, now=now, db=db,
                       why=f"look {tg}S{v6.get('S')}: RETIRE (PREREG-EVL-8 section 5, PREREG-EVL-6 section 1.4)"):
            return "retired"
        return None
    if decision == "pass" and band == "learning":
        if BA.set_band(store, key[0], key[1], "probe", since=at, now=now, db=db,
                       why=f"look {tg}S{v6.get('S')} passed (cap {v6.get('cap')}; PREREG-EVL-8 section 5)"):
            return "probe"
    return None


def run_looks(store: S.Store, prog: Any, today: dt.date, *, now: dt.datetime, draws: int = B) -> dict[str, Any]:
    """One version's looks of its current run (in `learning`): each due look whose close is final, every intent of it
    and of its control scheduled to exit by then settled, written once with its band move; the run's END at its 60th
    block (meta `END_KEY`). A version at Probe or Sized is `review8`'s; a waiting or retired version has no look."""
    from . import bands as BA

    out: dict[str, Any] = {"written": [], "waiting": []}
    band = BA.bands(store).get((prog.id, int(prog.version)), "learning")
    if band != "learning":
        return out
    rs = runs(store, prog)
    run = rs[-1]
    if run["ended"] is not None:
        out["waiting"].append({"program": prog.id, "version": prog.version, "k": None,
                               "why": f"run {run['n']} ended ({run['ended']['why']}): run {run['n'] + 1} waits for "
                                      "the budget"})
        return out
    record = run_record(record_rows(store, prog), run)
    if not record:
        return out
    ctl = "POOL" if P.is_meta8(prog) else CONTROL_OF.get(prog.id)
    ctl_rows = control_rows(store, prog)
    pend = SN._pending(store, prog.id, prog.version) + (SN._pending(store, CONTROL_OF[prog.id], 1)
                                                        if prog.id in CONTROL_OF else [])
    on = written(store, prog, "run", run["n"])
    tg = tag("run", run["n"])
    plan = schedule(store, record, today, pending=pend, consumed=on["consumed"], after=on["last"],
                    final=SN.final_until(store, prog.id, prog.version, today, now))
    if plan["stopped"] is not None:
        out["waiting"].append({"program": prog.id, "version": prog.version, "k": None, "why": plan["why"]})
    cap = cap_of(prog, "run")
    ended = False
    for k, as_of, merged, S_ in plan["looks"]:
        session = C.session(store, as_of)
        blk = blocks(SN.covered(record, as_of))[:RUN_BLOCKS]
        first_entry = min(SN._day(r["entry_day"]) for r in record)
        days = len(C.sessions(store, first_entry, as_of))
        cov = SN.covered(ctl_rows, as_of) if ctl_rows is not None else None
        judged = judge_blocks(blk, cap=cap, program=prog.id, version=prog.version, tag=tg, control_rows=cov,
                              control=ctl, draws=draws)
        look = look_row(prog, "run", run["n"], k, merged, session.close_at, days, judged)
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            moved[0] = on_look(store, look, now=now, db=db)
        if SN.write_look(store, look, apply=apply, now=now):
            out["written"].append({c: look[c] for c in ("program", "version", "k", "held", "passed", "p", "alpha", "why")}
                                  | {"band": moved[0], "merged": merged, "tag": tg, "S": S_, "cap": cap})
        if judged.get("decision") in ("pass", "retire"):
            ended = True
            break
    if not ended and plan["horizon"] is not None:
        at, last_day = plan["horizon"]
        session = C.session(store, at)
        key = END_KEY.format(program=prog.id, version=int(prog.version), n=run["n"])
        with store.tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                             (key, json.dumps({"at": S.iso(session.close_at), "last_day": last_day.isoformat(),
                                               "n": run["n"], "written_at": S.iso(now)}, sort_keys=True)))
        if cur.rowcount == 1:
            out["written"].append({"program": prog.id, "version": prog.version, "k": None, "held": 0, "passed": 0,
                                   "p": None, "alpha": None, "tag": tg, "end": at.isoformat(),
                                   "why": f"run {run['n']} ended at its {RUN_BLOCKS}th block (F2): the version stays in "
                                          "learning; its next run waits for the budget"})
    return out


# ----------------------------------------------------------------------------------------------------- the budget
def budget(store: Any) -> dict[str, int]:
    """THE LANE'S CHARGES (section 6.6, F12), in hundredths: PREREG-EVL-6's own count where the tree carries it
    (screen.py `budget6`, the SEATING sum of every seatable version and run), else the same sum here: 0.13 for every
    version in SEATING (its run 1) and every fresh run on record (meta `RUN_KEY`); 3.9 in all."""
    own = getattr(SN, "budget6", None)
    if own is not None:
        got = dict(own(store))
        return {k: int(v) for k, v in got.items() if isinstance(v, (int, float))}
    seating = list(P.SEATING)
    fresh = 0
    for p in seating:
        n = 2
        while store.meta(RUN_KEY.format(program=p.id, version=int(p.version), n=n)) is not None:
            fresh += 1
            n += 1
    used = CHARGE_HUNDREDTHS * (len(seating) + fresh)
    return {"versions": len(seating), "runs": fresh, "used": used, "left": BUDGET_HUNDREDTHS - used}


def waiting_runs(store: Any) -> list[dict[str, Any]]:
    """This file's versions in `learning` whose last run ended at its 60th block, or that were demoted after a pass,
    with no run since, in registration order then id."""
    from . import bands as BA

    band_of = BA.bands(store)
    out = []
    for p in seating8():
        if band_of.get((p.id, p.version), "learning") != "learning":
            continue
        rs = runs(store, p)
        last = rs[-1]
        ended = last.get("ended")
        if ended is None:
            continue
        item = {"program": p.id, "version": p.version, "n": last["n"] + 1, "registered_at": S.iso(p.registered_at)}
        if ended["why"] == "horizon":
            item |= {"why": f"run {last['n']} reached its {RUN_BLOCKS}th block unpassed", "after_day": ended.get("last_day"),
                     "at": ended.get("at"), "after": None}
        elif ended["why"] == "pass":
            demoted = [s for s in stays(store, p) if s.get("ended") == "learning" and s["until"] is not None]
            if not demoted:
                continue
            item |= {"why": f"demoted from its stay {demoted[-1]['n']}", "after_day": None, "at": None,
                     "after": S.iso(demoted[-1]["until"])}
        else:
            continue
        out.append(item)
    return sorted(out, key=lambda x: (x["registered_at"], x["program"], x["version"]))


def start_runs(store: Any, now: dt.datetime) -> list[dict[str, Any]]:
    """Every waiting run of this file (`waiting_runs`, in registration order) starts while the lane's budget holds its
    0.13, each written once (meta `RUN_KEY`) with its record's bounds; the earlier files' runs come first (their
    versions are registered earlier: PREREG-EVL-6's own `start_runs` runs before this one)."""
    started = []
    used = budget(store)["used"]
    for item in waiting_runs(store):
        if used + CHARGE_HUNDREDTHS > BUDGET_HUNDREDTHS:
            break
        record = {"n": item["n"], "after_day": item.get("after_day"), "after": item.get("after"), "started": S.iso(now),
                  "why": item["why"], "charge": CHARGE_HUNDREDTHS / 100}
        key = RUN_KEY.format(program=item["program"], version=item["version"], n=item["n"])
        cur = store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(record,
                                                                                              sort_keys=True)))
        if cur.rowcount == 1:
            used += CHARGE_HUNDREDTHS
            started.append({"program": item["program"], "version": item["version"]} | record)
    return started


def charges(store: Any) -> dict[str, Any]:
    """THE LANE'S EXPECTED FALSE PASSES THREE WAYS for this file (section 6.6): this file's count (0.13 a version or a
    run started), the base model's and the stresses' worst, and the per-version figures beside; {} while unpinned."""
    if not P.registers_8():
        return {}
    rows = seating8()
    fresh = {p.id: max(0, len(runs(store, p)) - 1) for p in rows}
    n = {p.id: 1 + fresh[p.id] for p in rows}
    count = CHARGE_HUNDREDTHS * sum(n.values())
    base = sum(BASE_HUNDREDTHS[part_of(p)] * n[p.id] for p in rows)
    stress = sum(STRESS_HUNDREDTHS[part_of(p)] * n[p.id] for p in rows)
    return {"runs": n, "count": count / 100, "base": base / 100, "stress": stress / 100,
            "per_version": dict(PER_VERSION), "budget": budget(store)}


# ----------------------------------------------------------------------------------------------------- the stays
def stays(store: Any, prog: Any) -> list[dict[str, Any]]:
    """The version's Probe stays: [{n, since, until, sized, ended}], stay n beginning at the n-th move to probe."""
    out: list[dict[str, Any]] = []
    for r in store.db.execute("SELECT id, band, since, written_at FROM band_history WHERE program=? AND version=? ORDER "
                              "BY id", (prog.id, int(prog.version))):
        moments = []
        for text in (r["since"], r["written_at"]):
            try:
                moments.append(S.parse_iso(str(text)))
            except (TypeError, ValueError):
                continue
        at = max(moments) if moments else None
        band = str(r["band"])
        if band == "probe" and (not out or out[-1]["until"] is not None):
            out.append({"n": len(out) + 1, "since": at, "until": None, "sized": None})
        elif out and out[-1]["until"] is None:
            if band == "sized":
                out[-1]["sized"] = at
            elif band in ("learning", "retired"):
                out[-1]["until"], out[-1]["ended"] = at, band
    return out


def stay_events(store: Any, prog: Any, since: Any) -> list[dict[str, Any]]:
    """THE STAY'S REAL-MONEY EVENTS (PREREG-EVL-6 section 3): the version's real-money buys at Probe or Sized bought after
    the stay began, ordered by scheduled exit, then entry decision time, then event id; with pnl and r once settled
    (bands.real_events), the buy's cost (filled shares x fill price), target_usd and sized_usd."""
    from . import bands as BA

    fills: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in store.db.execute("SELECT * FROM real_fills WHERE program=? AND version=?", (prog.id, int(prog.version))):
        fills.setdefault(str(row["event"]), {})[str(row["side"])] = dict(row)
    settled = {e["event"]: e for e in BA.real_events(store, prog.id, prog.version)}
    out = []
    for event, sides in fills.items():
        buy = sides.get("buy")
        if buy is None or str(buy["band"]) not in BA.PROBE_PLUS:
            continue
        try:
            bought = S.parse_iso(str(buy["filled_at"]))
        except (TypeError, ValueError):
            bought = None
        if since is not None and (bought is None or bought <= since):
            continue
        intent = store.db.execute("SELECT entry_day, exit_day, decided_at, cik, symbol FROM intents WHERE program=? AND "
                                  "version=? AND event=?", (prog.id, int(prog.version), event)).fetchone()
        done = settled.get(event)
        row = {"event": event, "entry_day": str(intent["entry_day"]) if intent else str(buy["filled_at"])[:10],
               "exit_day": str(intent["exit_day"]) if intent else str(buy["filled_at"])[:10],
               "decided_at": str(intent["decided_at"]) if intent else str(buy["filled_at"]),
               "settled": done is not None, "cost": float(buy["qty"]) * float(buy["price"]),
               "target_usd": buy.get("target_usd"), "sized_usd": buy.get("sized_usd")}
        if done is not None:
            row |= {"pnl": float(done["pnl"]), "r": float(done["r"])}
        out.append(row)
    out.sort(key=lambda e: (e["exit_day"], e["decided_at"], e["event"]))
    return out


def read_p(events: Sequence[Mapping[str, Any]], seed_text: str, draws: int = B) -> float:
    """A fixed read's p: the one-sided session-block sign-flip p for a mean BELOW zero (each entry session's mean r)."""
    groups: list[tuple[str, list[float]]] = []
    for e in events:
        day = str(e["entry_day"])
        if groups and groups[-1][0] == day:
            groups[-1][1].append(float(e["r"]))
        else:
            groups.append((day, [float(e["r"])]))
    return count_p([-(math.fsum(v) / len(v)) for _, v in groups], seed_text, draws)


def money_stop(events: Sequence[Mapping[str, Any]]) -> bool:
    if not events:
        return False
    return math.fsum(float(e["pnl"]) for e in events) < -STOP_SHARE * math.fsum(float(e["cost"]) for e in events)


def sized_conditions(store: Any, prog: Any, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """SIZED's real-money conditions (PREREG-EVL-6 section 3): >= 30 settled real events at Probe size or above (the
    Done reader's `at_size`) with summed P&L above 0 and the signed mean fill gap per side within 15 bp."""
    from . import done as DN

    sized = [e for e in events if e.get("settled") and DN.at_size(e.get("target_usd"), e.get("sized_usd"))]
    pnl = math.fsum(float(e["pnl"]) for e in sized)
    rich = DN._enrich(store, prog.id, prog.version, [dict(e) for e in sized]) if sized else []
    gaps = {}
    for side in ("entry", "exit"):
        vals = [float(r[f"{side}_gap_bp"]) for r in rich if r.get(f"{side}_gap_bp") is not None]
        gaps[side] = (math.fsum(vals) / len(vals)) if vals else None
    fills_ok = all(g is not None and abs(g) <= FILL_BP for g in gaps.values())
    return {"ok": len(sized) >= SIZED_MIN and pnl > 0 and fills_ok, "n": len(sized), "pnl": pnl, "fills_ok": fills_ok}


def review8(store: S.Store, prog: Any, *, now: Any = None, draws: int = B) -> list[dict[str, Any]]:
    """PREREG-EVL-6 section 3 for one of this file's versions at Probe or Sized (its current stay), in section 3's order
    at each close once that close's real-money events have settled: the fixed reads those settlements cross (p <= 0.15
    demotes), then the money stop, then the stay's look when one is due (its lower tail demotes; its PASS with the
    real-money conditions moves Probe to Sized), the stay's looks at the band's cap (F4: 14 at Probe, 8 at Sized). A
    demotion is written at once and the fresh run starts when the budget holds it (`start_runs`). The band changes."""
    from . import bands as BA

    now = now or S.utc_now()
    today = now.astimezone(C.NY).date()
    changes: list[dict[str, Any]] = []
    band = BA.bands(store).get((prog.id, int(prog.version)))
    if band not in BA.PROBE_PLUS:
        return changes
    st = stays(store, prog)
    if not st or st[-1]["until"] is not None:
        return changes
    stay = st[-1]
    n, since = stay["n"], stay["since"]
    key = STAY_KEY.format(program=prog.id, version=int(prog.version), n=n)
    state = _meta_json(store, key) or {"through": None, "looked": None, "read": 0}
    real = stay_events(store, prog, since)
    record = [r for r in record_rows(store, prog) if _after(r, since)]
    ctl = "POOL" if P.is_meta8(prog) else CONTROL_OF.get(prog.id)
    ctl_rows = control_rows(store, prog)
    pend = SN._pending(store, prog.id, prog.version)
    on = written(store, prog, "stay", n)
    j = max(on["consumed"]) if on["consumed"] else 0
    tg = tag("stay", n)
    start = since.astimezone(C.NY).date() if since is not None else today
    closes = [x for x in C.sessions(store, start, today) if x.close_at <= now]
    days = [x.day for x in closes]

    def day_of(text: Any) -> dt.date | None:
        return dt.date.fromisoformat(str(text)[:10]) if text else None
    through, looked = day_of(state.get("through")), day_of(state.get("looked"))

    def exit_of(e: Mapping[str, Any]) -> dt.date:
        return dt.date.fromisoformat(str(e["exit_day"])[:10])

    def stuck(e: Mapping[str, Any]) -> bool:
        return not e["settled"] and sum(1 for d in days if d > exit_of(e)) >= STUCK_AFTER

    def so_far(x: C.Session) -> list[dict[str, Any]]:
        return [e for e in real if e["settled"] and exit_of(e) <= x.day]

    def judge(x: C.Session) -> str | None:
        events = so_far(x)
        read = int(state.get("read") or 0)
        for kk in range((read // READ_EVERY + 1) * READ_EVERY, len(events) + 1, READ_EVERY):
            p = read_p(events[:kk], f"{prog.id}|v{int(prog.version)}|evl6|stay{n}|read{kk}", draws)
            state["read"] = kk
            if p <= READ_P + TIE:
                return f"the fixed read at the stay's {kk}th real-money Probe+ event: p {p:.4f} <= {READ_P}"
        if money_stop(events):
            return f"the money stop: the stay's {len(events)} real-money Probe+ events lost more than 10% of their cost"
        return None

    def save() -> None:
        state.update(through=through.isoformat() if through else None, looked=looked.isoformat() if looked else None)
        store.set_meta(key, json.dumps(state, sort_keys=True))

    def demote(x: C.Session, why: str) -> list[dict[str, Any]]:
        nonlocal through, looked
        if BA.set_band(store, prog.id, int(prog.version), "learning", since=S.iso(x.close_at), why=why, now=now):
            changes.append({"program": prog.id, "version": int(prog.version), "band": "learning", "why": why})
        through, looked = max(through or x.day, x.day), max(looked or x.day, x.day)
        save()
        start_runs(store, now)
        return changes

    final = None
    waiting = False
    for x in closes:
        if through is not None and x.day <= through and looked is not None and x.day <= looked:
            continue
        own = [e for e in real if exit_of(e) == x.day]
        ready = all(e["settled"] or stuck(e) for e in own)
        if ready and (through is None or x.day > through):
            why = judge(x)
            if why is not None:
                return demote(x, why)
            through = x.day
        if waiting or (looked is not None and x.day <= looked):
            continue
        blk = blocks(SN.covered(record, x.day))
        events = [e for b in blk[:RUN_BLOCKS] for e in b.events]
        S_ = min(len(blk), RUN_BLOCKS)
        due = j < len(LOOKS) and len(blk) <= RUN_BLOCKS and S_ >= LOOKS[j] and \
            minimums(len(events), len({str(e["issuer"]) for e in events}), S_) and (on["last"] is None or x.day > on["last"])
        if not due:
            looked = x.day
            continue
        if not ready:
            waiting = True
            continue
        if final is None:
            final = SN.final_until(store, prog.id, prog.version, today, now)
        if final[0] is None or x.day > final[0] or any(d <= x.day for _, d in pend):
            waiting = True
            continue
        why = judge(x)
        if why is not None:
            return demote(x, why)
        reached = [i for i in range(j, len(LOOKS)) if S_ >= LOOKS[i]]
        first_entry = min(SN._day(r["entry_day"]) for r in record)
        cov = SN.covered(ctl_rows, x.day) if ctl_rows is not None else None
        cap = cap_of(prog, "stay", band)
        judged = judge_blocks(blk[:RUN_BLOCKS], cap=cap, program=prog.id, version=prog.version, tag=tg,
                              control_rows=cov, control=ctl, draws=draws)
        look = look_row(prog, "stay", n, reached[0] + 1, [i + 1 for i in reached[1:]], x.close_at,
                        len(C.sessions(store, first_entry, x.day)), judged)
        if judged.get("decision") == "pass":
            look["v6"]["sized"] = sized_conditions(store, prog, so_far(x))
        moved: list[str | None] = [None]

        def apply(db: Any, look: dict[str, Any] = look) -> None:
            moved[0] = on_look(store, look, now=now, db=db)
        SN.write_look(store, look, apply=apply, now=now)
        j = reached[-1] + 1
        if moved[0] is not None:
            changes.append({"program": prog.id, "version": int(prog.version), "band": moved[0], "why": look["why"]})
        looked = x.day
        if moved[0] == "learning":
            through = max(through or x.day, x.day)
            save()
            start_runs(store, now)
            return changes
    save()
    return changes


def next_look(store: Any, prog: Any, today: dt.date) -> dict[str, Any]:
    """The next look of one of this file's versions (the report's): {k, kind, n, tag, blocks_needed (S_k), blocks
    (now), cap, status}; {k: None, status} retired, waiting for its run, or past its looks."""
    from . import bands as BA

    band = BA.bands(store).get((prog.id, int(prog.version)), "learning")
    if band == "retired":
        return {"k": None, "status": "retired"}
    if band in BA.PROBE_PLUS:
        st = stays(store, prog)
        if not st:
            return {"k": None, "status": "no stay on record"}
        kind, n, since = "stay", st[-1]["n"], st[-1]["since"]
        record = [r for r in record_rows(store, prog) if _after(r, since)]
    else:
        rs = runs(store, prog)
        if rs[-1]["ended"] is not None:
            return {"k": None, "status": f"run {rs[-1]['n']} ended: the next run waits for the budget"}
        kind, n = "run", rs[-1]["n"]
        record = run_record(record_rows(store, prog), rs[-1])
    on = written(store, prog, kind, n)
    j = max(on["consumed"]) if on["consumed"] else 0
    if j >= len(LOOKS):
        return {"k": None, "status": "every look of the run written"}
    blk = blocks(SN.covered(record, today))
    return {"k": j + 1, "kind": kind, "n": n, "tag": tag(kind, n), "blocks_needed": LOOKS[j], "blocks": len(blk),
            "cap": cap_of(prog, kind, band), "status": "upcoming" if len(blk) < LOOKS[j] else "due"}


# ----------------------------------------------------------------------------------------------------- the jobs
def seating8() -> list[P.Program8]:
    """This file's seatable versions in force (none while unpinned)."""
    return [p for p in P.rows_8() if p.can_seat]


def run(store: S.Store, today: dt.date, *, now: dt.datetime | None = None, draws: int = B) -> dict[str, Any]:
    """THE SCREEN'S PART FOR THIS FILE (the House's nightly screen and the screen after the open run it after
    screen.run): the fresh runs the budget holds start (`start_runs`), then each version in `learning` gets its run's
    looks (`run_looks`). One version's failure is its own. {written, waiting, errors, started}."""
    now = now or S.utc_now()
    out: dict[str, Any] = {"written": [], "waiting": [], "errors": [], "started": []}
    if not P.registers_8():
        return out
    try:
        out["started"] = start_runs(store, now)
    except Exception as exc:  # noqa: BLE001 - the looks go on
        out["errors"].append({"program": "runs", "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    for prog in seating8():
        try:
            got = run_looks(store, prog, today, now=now, draws=draws)
        except Exception as exc:  # noqa: BLE001 - its looks are computed again at the next run
            out["errors"].append({"program": prog.id, "version": prog.version,
                                  "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        out["written"] += got["written"]
        out["waiting"] += got["waiting"]
    return out


def review(store: S.Store, *, now: Any = None) -> list[dict[str, Any]]:
    """The band review of this file's versions at Probe or Sized (`review8`), the House's nightly; PREREG-EVL-3's review
    (league/events/bands.py) never reads them."""
    out: list[dict[str, Any]] = []
    for prog in seating8():
        out += review8(store, prog, now=now)
    return out


def audit(store: S.Store, today: dt.date, *, now: dt.datetime | None = None, draws: int = B) -> dict[str, Any]:
    """THE PLACEBO AUDIT AND THE CONTROL CANARY (section 3.3), records only: each of the 16 placebos' record (league/
    events/px.py `placebo_rows`) and each PX control's own record judged by THE PX SCREEN without its control condition
    (cap 4, run 1's looks), each look written once into px.sqlite `px_placebo` (machine-only); THE AUDIT ALARMS when 3
    or more of a window's 8 placebos have passed by their 60th block, or a control passes (THE CANARY). Never moves a
    band, never edits a judge. {alarm: [why], passed: {window: n}, canary: [control]} (counts only)."""
    from . import px as PXL

    now = now or S.utc_now()
    out: dict[str, Any] = {"alarm": [], "passed": {}, "canary": []}
    if not P.registers_8():
        return out
    px = PXL.open_px(store.root)
    try:
        jobs: list[tuple[str, str, list[dict[str, Any]]]] = []
        for window in ("ON", "O1"):
            judged = PXL.judged_days(px.db, PXL.window_auction(window))
            for j, pid in enumerate(PXL.placebo_ids(window), 1):
                jobs.append((pid, window, PXL.placebo_rows(store, window, j, judged=judged)))
        for ctl in AUDIT_CANARY:
            c = P.BY_KEY.get((ctl, 1))
            if c is not None:
                jobs.append((ctl, "ON" if ctl.endswith("ON") else "O1", record_rows(store, c)))
        for pid, window, rows in jobs:
            blk_all = blocks(rows)
            have = {int(r[0]) for r in px.db.execute("SELECT k FROM px_placebo WHERE placebo=?", (pid,))}
            passed = px.db.execute("SELECT 1 FROM px_placebo WHERE placebo=? AND passed=1 LIMIT 1", (pid,)).fetchone()
            retired = px.db.execute("SELECT 1 FROM px_placebo WHERE placebo=? AND decision='retire' LIMIT 1",
                                    (pid,)).fetchone()
            if passed is None and retired is None:
                for k, S_k in enumerate(LOOKS, 1):
                    if k in have or len(blk_all) < S_k:
                        continue
                    blk = blk_all[:S_k]
                    judged = judge_blocks(blk, cap=CAP["px"]["run"], program=pid, version=1, tag="", draws=draws)
                    px.db.execute("INSERT OR IGNORE INTO px_placebo(placebo, k, blocks, decision, passed, p, at, "
                                  "written_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                                  (pid, k, S_k, judged.get("decision"), int(judged.get("decision") == "pass"),
                                   judged.get("p"), blk[-1].day.isoformat(), S.iso(now)))
                    if judged.get("decision") in ("pass", "retire"):
                        break
            if px.db.execute("SELECT 1 FROM px_placebo WHERE placebo=? AND passed=1 LIMIT 1", (pid,)).fetchone():
                if pid in AUDIT_CANARY:
                    out["canary"].append(pid)
                else:
                    out["passed"][window] = out["passed"].get(window, 0) + 1
        for window, n in out["passed"].items():
            if n >= PXL.PLACEBO_ALARM:
                out["alarm"].append(f"{n} of the 8 {window} placebos have passed THE PX SCREEN (section 3.3's audit)")
        for ctl in out["canary"]:
            out["alarm"].append(f"{ctl} passed THE PX SCREEN without its control condition (THE CANARY)")
    finally:
        px.close()
    return out


__all__ = ["LOOKS", "ALPHAS", "MARGIN", "MIN_EVENTS", "MIN_ISSUERS", "MIN_BLOCKS", "ISSUER_P", "EXACT", "RUN_BLOCKS",
           "CAP", "CHARGE_HUNDREDTHS", "BUDGET_HUNDREDTHS", "BASE_HUNDREDTHS", "STRESS_HUNDREDTHS", "PER_VERSION",
           "READ_EVERY", "READ_P", "STOP_SHARE", "SIZED_MIN", "FILL_BP", "STUCK_AFTER", "RUN_KEY", "END_KEY",
           "STAY_KEY", "STAY_BASE", "CONTROL_OF", "AUDIT_CANARY", "alpha", "tag", "seed_string", "look_key", "key_of",
           "count_p", "Block8", "rank_order", "blocks", "values", "lower", "judge_blocks", "minimums", "part_of",
           "cap_of", "record_rows", "control_rows", "runs", "run_record", "written", "schedule", "look_row", "on_look",
           "run_looks", "budget", "waiting_runs", "start_runs", "charges", "stays", "stay_events", "read_p",
           "money_stop", "sized_conditions", "review8", "next_look", "seating8", "run", "review", "audit"]
