"""THE EVENT LANE'S OWN STALL CAUSES (release 1019c; the owner's goal of Oct 19, 2026, item 5: "Self-running: alarms on
stalls, missed events, fill gaps and cap breaches"), judged for the `stall` job (league/ops/stall.py), which raises them
like any cause. Each judges PROGRESS, never a receipt's status alone (the review of r1/alarms, its major 2: a record pass
that read nothing and a score pass that settled nothing both said `ok`).

Every cause reads the lane's own store, `<state>/events/events.sqlite` (league/events/store.py; every open `mode=ro`,
inside `guard.readonly()`), on the House's NYSE calendar (`ltcm.data.us_equity_session`), with no recursion into a judge
(no program is run, no verdict asked, no outcome computed), against the receipts the House's lane writes
(league/events/house.py, league/events/run.py; their contract is league/events/__init__.py, THE EVENT LANE'S RECEIPTS):

- `evl_record`: no CLEAN record pass finished in the last `RECORD_MINUTES` (30). A pass is clean when it finished `ok`
  and its three reads ran without error: EDGAR's current 8-K feed and its Form 4 feed (each block present, no `error`,
  not every fetch of the pass failed) and Alpaca's news (present, no `error`; a read its bound cut short is no error),
  with a tickers copy to fetch 8-Ks by. The numbers name the feeds that failed in the window's passes. The recorder runs
  round the clock (PREREG-EVL-1 section 3), so this is judged at every hour.
- `evl_decide`: a session's open (09:15 ET) or close (the close - 14 minutes) decision not MADE IN ITS WINDOW (`made`:
  a receipt `decide-<kind>:<day>` finished `ok` or `pending` by `DECIDE_GRACE_MINUTES` (10) after its time, the lane's
  own LIVE_WITHIN: the live decision every real-money auction reads) over the last `DECIDE_LOOKBACK_HOURS` (24):
  missing, failed, cut by the lane's bound, unfinished or finished after its window. One decided later still
  stands (its real-money auction was missed: "missed events"), named so. Which kinds exist comes from the programs' rows.
- `evl_verdicts`: verdicts a decision needs that stay UNANSWERED PAST THE DECISION: a decision whose time has passed and
  whose latest receipt (its tally, run.py's `verdicts: {needed, answered}`, the close decision's included; a receipt from
  before the tally, its `pending` counts) still lacks an answer `VERDICT_GRACE_MINUTES` (15) after the later of the
  decision's time and the start of its run of receipts that lacked one. The numbers say the UTC day's verdict dollars
  and the lane's line (league/events/house.py: the lower of `events.verdict_usd_day` and the budget's allowance, held on
  the UTC day), which holds READ events over it by design: the alarm stands all the same, as their decisions wait.
- `evl_score`: intents due by the latest session whose 23:00 ET has passed (`SCORE_BY`) still `planned` or `entered`:
  the night's score passes left them open. An intent whose exit print the tape showed absent (a `marks` row with no
  price at or after its exit day: PREREG-EVL-1 section 5's ladder waits on a later session) is waiting by design and is
  counted apart. A night with nothing due is no stall.
- `evl_fills` (the goal's "fill gaps"): the lane's real fills set beside the shadow's own auction prices (the House's
  EVENT TWINS, league/ops/twins.py `event_twin`, in the swarm store's kv `equity_twins`: `entry_gap_bp` and
  `exit_gap_bp`, signed, positive when the real fill was worse): over the last `FILL_LOOK` (20) priced twins with a
  figure on a side, the signed mean of that side more than `FILL_GAP_BP` (15 bp) from the prints IN EITHER DIRECTION
  (the goal's Done item "fills within 15 bp of replay", PREREG-EVL-3 section 5's signed mean per side, A50's size of
  the mean gap; the review of r2/alarms, its major 3: a gap either way means the fills or the shadow's prices, the
  evidence the screen judges, are mis-measured), with at least `FILL_MIN` (5) of them; the text says which way. Not
  judged before the first real fill is priced.

IDLE BY DESIGN: while `<state>/events/STOP` stands (the lane records, decides and asks nothing) the four are not judged,
nor for `RESUME_MINUTES` after it goes (the lane's first passes); a decision whose window fell inside it is excused for
good. While the House's maintenance `<state>/PAUSE` stands (no paid call: no verdict) `evl_verdicts` is not judged, and a
run of unanswered receipts is counted from the pause's end. The stall job keeps the windows it saw (`idle_windows`,
stall.json `evl_idle`). WHEN THEY ARE JUDGED AT ALL: only while the lane runs on the House (league/config.json
`events.enabled` true) and `<state>/ops.json` `stall.evl` is not false. A store that cannot be read is "Not judged" and an
entry of the job's `errors`; a lane switched on with no store yet has recorded nothing (`evl_record` stands). All four are
INFO with no owner step: each is the House's to fix (a release or the captain).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import guard
from . import schedule as S

CAUSES = ("evl_record", "evl_decide", "evl_verdicts", "evl_score", "evl_fills")
#: The stall job's key in `<state>/ops.json` that switches these four off: `{"stall": {"evl": false}}`.
SWITCH = "evl"
#: The lane's state under the House's state root (league/events/store.py `DB_NAME`), its idle switch and the House's pause.
STORE = Path("events") / "events.sqlite"
STOP = Path("events") / "STOP"
PAUSE = "PAUSE"
NY = ZoneInfo("America/New_York")
RECORD_MINUTES = 30
DECIDE_GRACE_MINUTES = 10
DECIDE_LOOKBACK_HOURS = 24.0
VERDICT_GRACE_MINUTES = 15
RESUME_MINUTES = 30
#: The decisions' times (league/events/calendar.py): 09:15 ET, and the close - 14 minutes.
OPEN_DECIDE = dt.time(9, 15)
CLOSE_DECIDE_BEFORE = dt.timedelta(minutes=14)
SCORE_BY = dt.time(23, 0)
#: THE FILL GAP (`evl_fills`): the priced event twins read, the most a side's signed mean may be worse than the shadow's
#: auction prices (the goal's Done item: "fills within 15 bp of replay"), and the fewest that judge it.
FILL_LOOK = 20
FILL_GAP_BP = 15.0
FILL_MIN = 5
TWINS_KEY = "equity_twins"
#: The record pass's three reads (league/events/house.py `_record_steps`: the summary's blocks), and their names here.
FEEDS = (("8-K", "8k"), ("4", "form4"), ("news", "news"))
#: The idle windows the stall job keeps (`idle_windows`): this many of each kind, none older than this.
IDLE_KEEP = 8
IDLE_DAYS = 3
DOING = {
    "not_judged": "Nothing: the cause is not judged while it reads so.",
    "evl_record": ("The House's tick runs a record pass every 2 minutes (EDGAR's current 8-K and Form 4 feeds, Alpaca's "
                   "news through the gateway), each bounded; a filing a pass could not fetch is tried again at the next "
                   "passes and then by the daily-index backfill, and the shadow record decides every event by its "
                   "knowable time whenever it was stored (PREREG-EVL-1 section 3): an outage removes nothing from the "
                   "shadow record, but real money can use only what was stored before its decision."),
    "evl_decide": ("The House's tick runs a due decision before any other task of the lane, again a minute after one that "
                   "failed while it is live, and decides a missed one later from what was knowable at its time (the "
                   "shadow rule). A decision not made in its window missed its auction: real money took none of its "
                   "events."),
    "evl_verdicts": ("The lane asks each verdict as soon as its event is recorded and eligible, and again before each "
                     "decision, at most 3 calls a pass; a call with no answer stores nothing and is asked again "
                     "(PREREG-EVL-1 section 4). Reading programs wait (pending) until every verdict they need is stored, "
                     "then decide by the shadow rule; over the lane's daily line (the budget's allowance, held on the UTC "
                     "day) they wait for the next UTC day's."),
    "evl_score": ("The lane's nightly score settles every due intent at the listing exchange's auction prints once the tape "
                  "is 16 minutes old (league/events/score.py), resumable pass by pass; the next night's passes try again "
                  "what this one left. The screen's looks wait for every block they cover (PREREG-EVL-1 section 7)."),
    "evl_fills": ("Each real event lot buys at the opening or closing auction with a limit-on-open or limit-on-close order "
                  "and sells at its own auction; the House sets every closed lot beside the shadow's auction print (the "
                  "equity_twins job, daily and before each open). Once real fills exist PREREG-EVL-1 section 5 checks the "
                  "cost allowance against the signed mean gap per side (raised, never lowered, when the fills are worse); "
                  "the goal's Done asks fills within 15 bp of replay either way, so a gap either way is the House's to "
                  "explain: the fills or the shadow's auction prices are mis-measured."),
}


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def switched_off(ctx: Any) -> bool:
    """THE OWNER'S SWITCH (`<state>/ops.json` `stall.evl` false): the four are not judged; absent, they are."""
    settings = _get(ctx, "settings")
    block = settings.get("stall") if isinstance(settings, Mapping) else None
    return isinstance(block, Mapping) and block.get(SWITCH) is False


def lane_on(ctx: Any) -> bool:
    """The lane runs on the House: league/config.json `events.enabled` true (release R1; default false)."""
    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    return isinstance(block, Mapping) and block.get("enabled") is True


def _not_judged(why: str) -> dict[str, Any]:
    return {"stalled": False, "judged": False, "what": f"Not judged: {why}.", "numbers": {"judged": False},
            "doing": DOING["not_judged"], "owner_step": None, "onset": None}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _loads(text: Any) -> Any:
    try:
        return json.loads(text) if isinstance(text, str) and text else None
    except ValueError:
        return None


def _hhmm(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, NY).strftime("%H:%M")


# ---------------------------------------------------------------------------------------------- idle by design
def idle_windows(kept: Any, root: str | Path, now: float) -> dict[str, list[list[float | None]]]:
    """The lane's STOP and the House's PAUSE as the stall job has seen them: {"stop": [[start, end], ...], "pause": ...},
    `end` None while the file stands. A file seen now opens a window at its mtime (or keeps the open one); a window
    open at the last run and gone now ends now (the file went between the two runs: the later end excuses more). Kept:
    the last `IDLE_KEEP` of each, none ended more than `IDLE_DAYS` ago."""
    kept = kept if isinstance(kept, Mapping) else {}
    out: dict[str, list[list[float | None]]] = {}
    for kind, path in (("stop", Path(root) / STOP), ("pause", Path(root) / PAUSE)):
        rows = [[_num(r[0]), _num(r[1])] for r in kept.get(kind) or [] if isinstance(r, (list, tuple)) and len(r) == 2
                and _num(r[0]) is not None]
        try:
            since = path.stat().st_mtime
        except OSError:
            since = None
        if since is not None:
            if not rows or rows[-1][1] is not None:
                rows.append([min(since, now), None])
        elif rows and rows[-1][1] is None:
            rows[-1][1] = now
        horizon = now - IDLE_DAYS * 86400
        out[kind] = [r for r in rows if r[1] is None or r[1] >= horizon][-IDLE_KEEP:]
    return out


def _within(at: float, windows: list[list[float | None]], now: float) -> bool:
    return any(start <= at <= (now if end is None else end) for start, end in windows)


def _open(windows: list[list[float | None]]) -> bool:
    return bool(windows) and windows[-1][1] is None


def _ended_lately(windows: list[list[float | None]], now: float) -> float | None:
    """When the latest window ended, when that was under `RESUME_MINUTES` ago; else None."""
    if windows and windows[-1][1] is not None and now - float(windows[-1][1]) < RESUME_MINUTES * 60:
        return float(windows[-1][1])
    return None


# ---------------------------------------------------------------------------------------------- the calendar
def sessions(first: dt.date, last: dt.date) -> list[dict[str, Any]]:
    """The House's NYSE sessions from `first` to `last`: [{day, open_at, close_at}] (epochs), oldest first."""
    from ltcm.data import us_equity_session

    out, day = [], first
    while day <= last:
        try:
            session = us_equity_session(day)
        except Exception:  # noqa: BLE001 - a year the calendar does not hold has no session here
            session = None
        if session is not None:
            out.append({"day": day, "open_at": S.epoch(session.open_at), "close_at": S.epoch(session.close_at)})
        day += dt.timedelta(days=1)
    return out


def _ny(day: dt.date, wall: dt.time) -> float:
    return dt.datetime.combine(day, wall, tzinfo=NY).timestamp()


def decisions(now: float, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """The scheduled decisions whose window (`DECIDE_GRACE_MINUTES` after their time) has ended, their time inside the
    last `DECIDE_LOOKBACK_HOURS`: [{kind, day, at, ends}] (epochs), oldest first."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    out = []
    for s in sessions(today - dt.timedelta(days=4), today):
        for kind in kinds:
            if kind == "open":
                at = _ny(s["day"], OPEN_DECIDE)
            elif s["close_at"] is not None:
                at = s["close_at"] - CLOSE_DECIDE_BEFORE.total_seconds()
            else:
                continue
            ends = at + DECIDE_GRACE_MINUTES * 60
            if now - DECIDE_LOOKBACK_HOURS * 3600 <= at and ends <= now:
                out.append({"kind": kind, "day": s["day"].isoformat(), "at": at, "ends": ends})
    return sorted(out, key=lambda d: d["at"])


def entry_kinds() -> tuple[str, ...]:
    """The decisions the registered programs need (league/events/programs.py `PROGRAMS`: each row's `entry_at`)."""
    try:
        from ..events import programs as P

        kinds = {str(p.entry_at) for p in P.PROGRAMS}
    except Exception:  # noqa: BLE001 - both, when the table cannot be read
        kinds = {"open", "close"}
    return tuple(k for k in ("open", "close") if k in kinds)


# ---------------------------------------------------------------------------------------------- the reads
def facts(root: str | Path, now: float, score_day: str | None) -> dict[str, Any]:
    """Every receipt the four causes read, and the intents due by `score_day` still open, in one read-only transaction:
    {record: [...], decide: {job: [...]}, score: [...], open_due: [...], none_marks: {(symbol, day)}}."""
    since = S.iso(now - 5 * 86400)

    def read(db: Any) -> dict[str, Any]:
        rows = guard.rows(db, "SELECT id, job, started_at, finished_at, status, summary FROM receipts WHERE started_at>=? "
                              "AND (job='record' OR job LIKE 'decide-%' OR job='score') ORDER BY id", (since,))
        out: dict[str, Any] = {"record": [], "decide": {}, "score": [], "open_due": [], "none_marks": set()}
        for r in rows:
            job = str(r["job"])
            if job == "record":
                out["record"].append(r)
            elif job == "score":
                out["score"].append(r)
            else:
                out["decide"].setdefault(job, []).append(r)
        if score_day is not None:
            out["open_due"] = guard.rows(db, "SELECT i.program, i.version, i.event, i.symbol, i.entry_day, i.exit_day, "
                                             "i.exit_at, (SELECT u.bench FROM universe u WHERE u.day=i.entry_day AND "
                                             "u.symbol=i.symbol) AS bench FROM intents i WHERE i.status IN ('planned', "
                                             "'entered') AND i.exit_day<=?", (score_day,))
            symbols = sorted({str(r["symbol"]) for r in out["open_due"]} | {str(r["bench"]) for r in out["open_due"]
                                                                            if r["bench"]})
            if symbols:
                first = min(str(r["entry_day"]) for r in out["open_due"])
                marks = guard.batched(db, "SELECT symbol, day FROM marks WHERE px IS NULL AND day>=? AND symbol IN "
                                          "({marks})", symbols, params=(first,))
                out["none_marks"] = {(str(m["symbol"]), str(m["day"])) for m in marks}
        return out
    return guard.read(Path(root) / STORE, read)


def event_twins(root: str | Path) -> list[dict[str, Any]]:
    """The House's PRICED event twins (league/ops/twins.py `event_twin`; the swarm store's kv `equity_twins`, read-only),
    oldest exit first; [] with no swarm store or no such record."""
    path = Path(root) / "swarm.sqlite"
    if not path.exists():
        return []

    def read(db: Any) -> Any:
        row = db.execute("SELECT value FROM kv WHERE key=?", (TWINS_KEY,)).fetchone()
        return None if row is None else row[0]
    raw = guard.read(path, read)
    records = _loads(raw) if isinstance(raw, str) else None
    rows = [dict(r) for r in (records or {}).values() if isinstance(r, Mapping) and r.get("kind") == "event"
            and r.get("status") == "priced"] if isinstance(records, Mapping) else []
    return sorted(rows, key=lambda r: (str(r.get("exit_day") or ""), str(r.get("judged_at") or ""), str(r.get("key"))))


def fill_gaps(twins: list[Mapping[str, Any]], look: int = FILL_LOOK) -> dict[str, Any]:
    """The signed mean gap per side (bp, positive when the real fill was worse than the shadow's auction print) over the
    last `look` priced event twins with a figure on that side: {entry_n, entry_mean_bp, exit_n, exit_mean_bp}."""
    out: dict[str, Any] = {}
    for side in ("entry", "exit"):
        values = [v for v in (_num(t.get(f"{side}_gap_bp")) for t in twins) if v is not None][-look:]
        out[f"{side}_n"] = len(values)
        out[f"{side}_mean_bp"] = None if not values else round(math.fsum(values) / len(values), 2)
    return out


# ---------------------------------------------------------------------------------------------- the causes
def _fills(now: float, twins: list[Mapping[str, Any]]) -> dict[str, Any]:
    """`evl_fills` (the module docstring): a side whose signed mean gap is more than `FILL_GAP_BP` from the shadow's
    auction prints IN EITHER DIRECTION (the review of r2/alarms, its major 3: the Done item and PREREG-EVL-3 section 5 ask
    fills WITHIN 15 bp, the signed mean per side, and A50 reads the SIZE of the mean gap; a gap either way says the fills
    or the shadow's prices, the evidence the screen judges, are mis-measured), with at least `FILL_MIN` twins on it."""
    if not twins:
        return _not_judged("no real fill of the event lane is priced beside its auction yet (the equity_twins job)")
    gaps = fill_gaps(twins)

    def mean(side: str) -> float | None:
        return gaps[f"{side}_mean_bp"] if gaps[f"{side}_n"] >= FILL_MIN else None
    off = [side for side in ("entry", "exit") if mean(side) is not None and abs(mean(side)) > FILL_GAP_BP]

    def said(side: str) -> str:
        value, n = gaps[f"{side}_mean_bp"], gaps[f"{side}_n"]
        if value is None:
            return f"{side} n/a (no priced fill)"
        if n < FILL_MIN:
            return f"{side} {value:+.1f} bp over {n} (too few to judge: {FILL_MIN} at least)"
        if abs(value) <= FILL_GAP_BP:
            return f"{side} {value:+.1f} bp over {n} (within {FILL_GAP_BP:g} bp)"
        return f"{side} {value:+.1f} bp over {n} ({'worse' if value > 0 else 'better'} than the prints by more than " \
               f"{FILL_GAP_BP:g} bp)"
    if off:
        what = (f"The event lane's real fills strayed from the shadow's auction prices: the signed mean gap "
                f"{', '.join(said(s) for s in off)}, over the last {FILL_LOOK} priced fills (the Done item asks within "
                f"{FILL_GAP_BP:g} bp a side, either way)"
                + "".join(f"; {said(s)}" for s in ("entry", "exit") if s not in off) + ".")
    else:
        what = (f"The event lane's real fills against the shadow's auction prices, the signed mean gap over the last "
                f"{FILL_LOOK} priced fills: {said('entry')}; {said('exit')}.")
    worse = [s for s in off if (mean(s) or 0.0) > 0]
    better = [s for s in off if (mean(s) or 0.0) < 0]
    return {"stalled": bool(off), "judged": True, "what": what,
            "numbers": {**gaps, "off": ",".join(off) or "none", "worse": ",".join(worse) or "none",
                        "better": ",".join(better) or "none", "last_exit_day": twins[-1].get("exit_day")},
            "doing": DOING["evl_fills"], "owner_step": None, "onset": None}


def _failing(row: Mapping[str, Any]) -> list[str]:
    """The feeds a finished record pass did not read cleanly (`FEEDS`' names), [] for a clean pass."""
    summary = _loads(row.get("summary"))
    summary = summary if isinstance(summary, Mapping) else {}
    bad = []
    for key, name in FEEDS:
        block = summary.get(key)
        if not isinstance(block, Mapping) or block.get("error"):
            bad.append(name)
        elif key != "news" and (_num(block.get("failed")) or 0) > 0 and not (_num(block.get("fetched")) or 0):
            bad.append(name)   # every fetch of the pass failed: the feed reads, its documents do not
    tickers = summary.get("tickers")
    if isinstance(tickers, Mapping) and tickers.get("error") and "8k" not in bad:
        bad.insert(0, "8k")    # no tickers copy: no 8-K can be fetched
    return bad


def _record(now: float, f: Mapping[str, Any]) -> dict[str, Any]:
    window = now - RECORD_MINUTES * 60
    finished = [r for r in f["record"] if r.get("finished_at") and S.epoch(r["finished_at"]) is not None]
    passes = [r for r in finished if str(r.get("status") or "") == "ok"]
    clean = [r for r in passes if not _failing(r)]
    last = max((S.epoch(r["finished_at"]) for r in clean), default=None)
    recent = [r for r in finished if S.epoch(r["finished_at"]) >= window]
    failed = [r for r in recent if str(r.get("status") or "") != "ok"]
    seen = [r for r in recent if str(r.get("status") or "") == "ok"] or passes[-1:]
    feeds: list[str] = []
    for r in seen:
        for name in _failing(r):
            if name not in feeds:
                feeds.append(name)
    stalled = last is None or last < window
    words = {"8k": "the 8-K feed", "form4": "the Form 4 feed", "news": "the news"}
    named = " and ".join(words[n] for n in feeds) if feeds else None
    if last is None and not finished:
        what = "The event lane has finished no record pass on record (none in the last 5 days)."
    elif stalled:
        what = (f"The event lane finished no clean record pass in the last {RECORD_MINUTES} minutes"
                + (f": {named} could not be read" if named else (": its passes failed" if failed else ""))
                + ("" if last is None else f" (the last clean one ended {_hhmm(last)} ET, "
                                           f"{round((now - last) / 60)} minutes ago).")
                + ("." if last is None else ""))
    else:
        what = f"The event lane's last clean record pass ended {_hhmm(last)} ET."
        if named:
            what += f" Some passes of the last {RECORD_MINUTES} minutes could not read {named}."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"last_clean_at": None if last is None else S.iso(last),
                        "minutes_since_clean": None if last is None else round((now - last) / 60.0, 1),
                        f"passes_{RECORD_MINUTES}m": len([r for r in recent if str(r.get('status') or '') == 'ok']),
                        f"clean_{RECORD_MINUTES}m": len([r for r in clean if S.epoch(r["finished_at"]) >= window]),
                        f"failed_{RECORD_MINUTES}m": len(failed), "failing": ",".join(feeds) or "none"},
            "doing": DOING["evl_record"], "owner_step": None, "onset": last if stalled else None}


def made(rows: list[Mapping[str, Any]], ends: float) -> bool:
    """A decision MADE IN ITS WINDOW: a receipt that finished `ok` or `pending` by `ends` (its time and the lane's own
    LIVE_WITHIN: what the real-money decision of that auction waits for, league/events/book.py `decided`)."""
    return any(str(r.get("status") or "") in ("ok", "pending") and r.get("finished_at")
               and (S.epoch(r["finished_at"]) or float("inf")) <= ends for r in rows)


def _decide(now: float, f: Mapping[str, Any], kinds: tuple[str, ...], stops: list) -> dict[str, Any]:
    due = decisions(now, kinds)
    missed, excused = [], 0
    for d in due:
        rows = f["decide"].get(f"decide-{d['kind']}:{d['day']}", [])
        if made(rows, d["ends"]):
            continue
        if _within(d["at"], stops, now) or _within(d["ends"], stops, now):
            excused += 1
            continue
        tried = [r for r in rows if (S.epoch(r["started_at"]) or float("inf")) <= d["ends"]]
        if not tried:
            state = "missing"
        else:
            status, done = str(tried[-1].get("status") or ""), tried[-1].get("finished_at")
            state = ("late" if done and status in ("ok", "pending") else "unfinished" if not done or status == "running"
                     else status if status in ("failed", "cut") else "failed")
        later = any(str(r.get("status") or "") in ("ok", "pending") and r.get("finished_at") for r in rows)
        missed.append({**d, "state": state, "later": later})
    first = missed[0] if missed else None
    if first is None:
        what = (f"Every scheduled decision of the last {DECIDE_LOOKBACK_HOURS:g} h was made in its window ({len(due)})."
                if due else f"No decision was due in the last {DECIDE_LOOKBACK_HOURS:g} h.")
    else:
        words = {"missing": "was never started", "failed": "failed", "cut": "was cut by the lane's time bound",
                 "unfinished": "never finished", "late": "finished after its window"}
        what = (f"The event lane's {first['kind']} decision of {first['day']} ({_hhmm(first['at'])} ET) was not made in "
                f"its {DECIDE_GRACE_MINUTES}-minute window: it {words.get(first['state'], first['state'])}"
                + ("; it was decided later, for the shadow record only" if first["later"] else "")
                + (f". {len(missed)} decisions of the last {DECIDE_LOOKBACK_HOURS:g} h were missed in all." if len(missed) > 1
                   else "."))
    return {"stalled": bool(missed), "judged": True, "what": what,
            "numbers": {"decisions_due": len(due), "missed": len(missed), "excused_stop": excused,
                        "first_missed": None if first is None else f"{first['kind']}:{first['day']}",
                        "first_missed_at": None if first is None else S.iso(first["at"]),
                        "first_state": None if first is None else first["state"],
                        "decided_later": sum(1 for m in missed if m["later"])},
            "doing": DOING["evl_decide"], "owner_step": None, "onset": None if first is None else first["ends"]}


def tally(row: Mapping[str, Any]) -> tuple[int | None, int] | None:
    """(needed, unanswered) of one decision receipt: its tally (run.py `verdicts`), else, for a receipt from before the
    tally, (None, the sum of its `pending` counts) when it waits; None when it says nothing of verdicts."""
    summary = _loads(row.get("summary"))
    summary = summary if isinstance(summary, Mapping) else {}
    counts = summary.get("verdicts")
    if isinstance(counts, Mapping):
        n, a = _num(counts.get("needed")), _num(counts.get("answered"))
        if n is not None and a is not None and n >= 0 and 0 <= a <= n:
            return int(n), int(n - a)
    pending = summary.get("pending")
    if isinstance(pending, Mapping):
        waiting = [_num(v) for v in pending.values()]
        if all(v is not None and v >= 0 for v in waiting):
            return None, int(sum(waiting))
    return None


def _verdicts(now: float, f: Mapping[str, Any], kinds: tuple[str, ...], idle: Mapping[str, list],
              line: Mapping[str, Any] | None) -> dict[str, Any]:
    due = decisions(now, kinds)
    held, needed_all, unanswered_all, read = [], 0, 0, 0
    quiet_until = max([float(end) for start, end in (idle.get("stop") or []) + (idle.get("pause") or [])
                       if end is not None], default=None)
    for d in due:
        rows = [r for r in f["decide"].get(f"decide-{d['kind']}:{d['day']}", []) if r.get("finished_at")]
        counted = [(r, tally(r)) for r in rows]
        counted = [(r, t) for r, t in counted if t is not None]
        if not counted:
            continue
        read += 1
        latest, (needed, missing) = counted[-1]
        if needed is not None:
            needed_all += needed
        unanswered_all += missing
        if missing <= 0:
            continue
        streak = latest
        for r, t in reversed(counted):
            if t[1] <= 0:
                break
            streak = r
        since = max(d["at"], S.epoch(streak["started_at"]) or d["at"])
        if quiet_until is not None and since <= quiet_until:
            since = max(since, quiet_until)
        if _within(d["at"], idle.get("stop") or [], now):
            continue
        if now - since >= VERDICT_GRACE_MINUTES * 60:
            held.append({**d, "missing": missing, "needed": needed, "since": since})
    first = held[0] if held else None
    spent, limit = (None, None) if not line else (_num(line.get("spent_usd")), _num(line.get("line_usd")))
    at_line = spent is not None and limit is not None and spent >= limit - 1e-9
    if first is None:
        what = (f"No verdict a decision of the last {DECIDE_LOOKBACK_HOURS:g} h needed is unanswered past it." if read
                else f"No decision of the last {DECIDE_LOOKBACK_HOURS:g} h carries a verdict tally.")
    else:
        what = (f"{first['missing']} verdicts the event lane's {first['kind']} decision of {first['day']} needs have no "
                f"answer {round((now - first['since']) / 60)} minutes past it"
                + (f" ({len(held)} decisions in all)" if len(held) > 1 else "")
                + ("; the lane's verdict line for the day is reached" if at_line else "") + ".")
    return {"stalled": bool(held), "judged": True, "what": what,
            "numbers": {"decisions_read": read, "held": len(held), "unanswered": unanswered_all, "needed": needed_all,
                        "first_held": None if first is None else f"{first['kind']}:{first['day']}",
                        "unanswered_since": None if first is None else S.iso(first["since"]),
                        "verdict_usd_today": None if spent is None else round(spent, 4),
                        "verdict_line_usd": None if limit is None else round(limit, 4), "at_line": at_line},
            "doing": DOING["evl_verdicts"], "owner_step": None, "onset": None if first is None else first["since"]}


def score_session(now: float) -> dict[str, Any] | None:
    """The latest session whose 23:00 ET (`SCORE_BY`) has passed, within the last 10 days."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    for s in reversed(sessions(today - dt.timedelta(days=10), today)):
        if _ny(s["day"], SCORE_BY) <= now:
            return s
    return None


def _waiting_on_tape(row: Mapping[str, Any], marks: set) -> bool:
    """An open intent whose exit print, or its benchmark's print, the tape showed absent (a `marks` row with no price on
    its entry day or at or after its exit day): PREREG-EVL-1 section 5's ladder waits on a later session by design."""
    for symbol in (str(row["symbol"]), str(row.get("bench") or "")):
        if not symbol:
            continue
        if any(m_symbol == symbol and (m_day >= str(row["exit_day"]) or (symbol != str(row["symbol"])
                                                                           and m_day == str(row["entry_day"])))
               for m_symbol, m_day in marks):
            return True
    return False


def _score(now: float, f: Mapping[str, Any], latest: Mapping[str, Any]) -> dict[str, Any]:
    day = latest["day"].isoformat()
    open_due = list(f["open_due"])
    waiting = [r for r in open_due if _waiting_on_tape(r, f["none_marks"])]
    stuck = [r for r in open_due if r not in waiting]
    after = latest["close_at"] + 16 * 60
    passes = [r for r in f["score"] if (S.epoch(r["started_at"]) or 0.0) >= after]
    last = passes[-1] if passes else (f["score"][-1] if f["score"] else None)
    summary = _loads(last.get("summary")) if last else None
    summary = summary if isinstance(summary, Mapping) else {}
    errors = int(_num(summary.get("errors")) or 0) if not isinstance(summary.get("errors"), list) else len(summary["errors"])
    stalled = bool(stuck)
    if stalled:
        what = (f"{len(stuck)} intents due by the session of {day} are still open after the night's score "
                + (f"passes (the last at {_hhmm(S.epoch(last['started_at']))} ET, {str(last.get('status') or 'running')}, "
                   f"{errors} errors)." if passes else "passes: no score pass ran after its close."))
    elif open_due:
        what = f"Every intent due by the session of {day} is settled but {len(waiting)} the tape keeps waiting (no print)."
    else:
        what = f"Every intent due by the session of {day} is settled."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"day": day, "open_due": len(stuck), "waiting_on_tape": len(waiting), "passes": len(passes),
                        "last_pass_at": None if last is None else last["started_at"],
                        "last_pass_status": None if last is None else str(last.get("status") or "running")[:20],
                        "last_pass_errors": errors},
            "doing": DOING["evl_score"], "owner_step": None,
            "onset": _ny(latest["day"], SCORE_BY) if stalled else None}


def checks(ctx: Any, root: str | Path, now: float, *, errors: list[str] | None = None, idle: Any = None,
           line: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """THE STALL JOB'S CALL (league/ops/stall.py `run`): the four causes' checks (the module docstring). `idle` is
    `idle_windows`' answer (None: read now, with nothing kept); `line` the lane's verdict line and the day's spend
    ({line_usd, spent_usd}, `verdict_line`). Never raises: a store that cannot be read is "Not judged" and an entry of
    `errors`."""
    try:
        if switched_off(ctx):
            return {c: _not_judged(f"switched off (ops.json stall.{SWITCH} is false)") for c in CAUSES}
        if not lane_on(ctx):
            return {c: _not_judged("the event lane does not run on the House (league/config.json events.enabled)")
                    for c in CAUSES}
        idle = idle if isinstance(idle, Mapping) else idle_windows(None, root, now)
        stops, pauses = list(idle.get("stop") or []), list(idle.get("pause") or [])
        if _open(stops):
            return {c: _not_judged("the lane is stopped by events/STOP") for c in CAUSES}
        back = _ended_lately(stops, now)
        if back is not None:
            return {c: _not_judged(f"the lane came back from events/STOP at {_hhmm(back)} ET, under {RESUME_MINUTES} "
                                   "minutes ago") for c in CAUSES}
        latest = score_session(now)
        if not (Path(root) / STORE).exists():
            f: dict[str, Any] = {"record": [], "decide": {}, "score": [], "open_due": [], "none_marks": set()}
        else:
            with guard.readonly():
                f = facts(root, now, None if latest is None else latest["day"].isoformat())
        kinds = entry_kinds()
        out = {"evl_record": _record(now, f), "evl_decide": _decide(now, f, kinds, stops)}
        if _open(pauses):
            out["evl_verdicts"] = _not_judged("the House is paused (PAUSE): no verdict is asked while it stands")
        elif _ended_lately(pauses, now) is not None:
            out["evl_verdicts"] = _not_judged(f"the House's PAUSE ended under {RESUME_MINUTES} minutes ago")
        else:
            out["evl_verdicts"] = _verdicts(now, f, kinds, idle, line)
        out["evl_score"] = (_not_judged("no session in the last 10 days has passed its 23:00 ET") if latest is None
                            else _score(now, f, latest))
        out["evl_fills"] = _fills(now, event_twins(root))
        return out
    except Exception as exc:  # noqa: BLE001 - an alarm that cannot see says so, and the rest of the job goes on
        if errors is not None:
            errors.append(f"the event lane's store could not be read ({type(exc).__name__}): its four causes are not judged")
        return {c: _not_judged(f"the event lane's store could not be read ({type(exc).__name__})") for c in CAUSES}


def verdict_line(ctx: Any, root: str | Path, now: float) -> dict[str, Any] | None:
    """The lane's verdict line of the UTC day (league/events/house.py: the lower of `events.verdict_usd_day` and the
    budget's allowance, league/ops/budget.py `lane_allowance`, held on the UTC day: `verdict_day`) and the day's verdict
    dollars so far: {line_usd, spent_usd, source}, or None when the store cannot be read."""
    from . import budget as B
    from ..events.house import VERDICT_USD_DAY, verdict_day   # the House's own default and day: read where they are set

    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    configured = _num((block or {}).get("verdict_usd_day")) if isinstance(block, Mapping) else None
    configured = float(VERDICT_USD_DAY) if configured is None else configured
    allowance = B.lane_allowance(root, now)
    line = min(configured, float(allowance["usd_day"]))
    path = Path(root) / STORE
    if not path.exists():
        return {"line_usd": line, "spent_usd": 0.0, "source": allowance["source"]}
    _, (lo, hi) = verdict_day(dt.datetime.fromtimestamp(now, dt.timezone.utc))
    try:
        with guard.readonly():
            row = guard.read(path, lambda db: db.execute(
                f"SELECT COALESCE(SUM(COALESCE(usd, {B.VERDICT_USD_UNKNOWN})), 0) FROM verdicts WHERE answered_at>=? "
                "AND answered_at<?", (lo, hi)).fetchone()[0])
    except Exception:  # noqa: BLE001 - the line alone
        return None
    return {"line_usd": line, "spent_usd": float(row or 0.0), "source": allowance["source"]}


__all__ = ["CAUSES", "SWITCH", "STORE", "STOP", "PAUSE", "checks", "facts", "switched_off", "lane_on", "decisions",
           "entry_kinds", "sessions", "idle_windows", "made", "tally", "score_session", "verdict_line", "event_twins",
           "fill_gaps", "FILL_LOOK", "FILL_GAP_BP", "FILL_MIN",
           "RECORD_MINUTES", "DECIDE_GRACE_MINUTES", "DECIDE_LOOKBACK_HOURS", "VERDICT_GRACE_MINUTES", "RESUME_MINUTES",
           "SCORE_BY", "FEEDS"]
