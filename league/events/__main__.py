"""`python -m league.events --state DIR <command>`: the event lane's passes (see league/events/run.py).

Commands: sessions --from D --to D | record | backfill --from D --to D | decide-open --day D [--backfill] |
decide-close --day D [--backfill] [--evl4-only | --evl5-only] | catchup (every past decision from the registration time
not yet made, as a backfill, PREREG-EVL-4's rows of every older close a release without them decided, PREREG-EVL-5's
rows of every close a release without them decided or whose part for them failed, and the registered births of every
older decision a release without them made) | births [--day D] [--specs
FILE] [--dry-run] (R3's births job: the architect's one call, or the captain's own specs from FILE, a JSON list of
{spec, why}, with no call; validated and registered through the gateway's docs route, `--dry-run` validated only) |
facts [--day D] [--specs FILE] (R3's outcome-free facts, with each spec's selection counts) | learners (PREREG-EVL-7's
owed decisions, nothing while REGISTERED_AT_7 is None) | score-unlatch (release 1019i: the captain's clearing of the
batched score's parity latch, league/events/score.py `unlatch`, once its flag 0 is explained; no gateway is read).
Prints one JSON summary.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from . import calendar as C
from . import report as RP
from . import score as SC
from . import screen as SN
from . import gw as G
from . import programs as P
from . import run as R
from . import store as S


def _day(text: str) -> dt.date:
    return dt.date.fromisoformat(text)


#: Sessions re-decided on every catchup (idempotent: known events are skipped and stored verdicts reused), so an event
#: that reached the store late (a recorder outage, news backfilled after the gateway could read it) still gets its
#: shadow decision (PREREG-EVL-1 section 3: an outage removes nothing from the shadow record). The judge's reach
#: (league/events/screen.py FINAL_SESSIONS, as the House's lane takes it).
REDECIDE_SESSIONS = SN.FINAL_SESSIONS


def catchup(ctx: R.Context) -> dict:
    """Every scheduled decision from the registration time to now without an ok receipt, oldest first, and the last
    REDECIDE_SESSIONS due sessions again. A decision run at its scheduled minute (within 10 minutes) is live; any other
    is a backfill.

    Then PREREG-EVL-4'S ROWS (release 1019c's review): every close since its registration that a release without its
    rows decided last (league/events/screen.py `made_without`: the closes older than the re-decision reach, which the
    loop above leaves as they are) gets their own decision, once, as a backfill (`decide_evl4`), and the earlier rows of
    those closes are never decided again. Then PREREG-EVL-5'S ROWS the same way (its section 3: `made_without(prereg=5)`,
    `decide_evl5`, oldest first, once), and R3'S REGISTERED BIRTHS the same way (release 1019e's review): every
    decision a release or a turn without them made last (`births_made_without`) gets the births' own decision
    (`births_only`), as a backfill, and no PREREG row of it is decided again. PREREG-EVL-6 (section 1.1, D8): the
    release's mark is written first (once: `programs.mark_release`), and last every new version's copy of its
    superseded version's record of the sessions decided before the release (`programs.copy_all_before_release`), as
    the House's lane makes them."""
    st = ctx.store
    now = ctx.now()
    P.mark_release(st, now)
    start = P.registered().astimezone(C.NY).date()
    done = {r[0] for r in st.db.execute("SELECT job FROM receipts WHERE status='ok' AND job LIKE 'decide-%'")}
    due = [s for s in C.sessions(st, start, now.astimezone(C.NY).date()) if s.open_decide <= now]
    recent = {s.day for s in due[-REDECIDE_SESSIONS:]}
    out = {}
    for s in due:
        live_open = R.live_run(s.open_decide, now)      # (the judge's rule: league/events/run.py LIVE_WITHIN)
        if f"decide-open:{s.day}" not in done or s.day in recent:
            out[f"open:{s.day}"] = R.decide_open(ctx, s.day, backfill_run=not live_open)
        if s.close_decide + dt.timedelta(minutes=1) <= now and (f"decide-close:{s.day}" not in done or s.day in recent):
            live_close = R.live_run(s.close_decide, now)
            out[f"close:{s.day}"] = R.decide_close(ctx, s.day, backfill_run=not live_close)
    for day in SN.made_without(st, now.astimezone(C.NY).date()):
        out[f"{SN.FOUR_KIND}:{day}"] = decide_evl4(ctx, day)
    for day in sorted(SN.made_without(st, now.astimezone(C.NY).date(), prereg=5)):
        out[f"{SN.FIVE_KIND}:{day}"] = decide_evl5(ctx, day)
    for kind, day in SN.births_made_without(st, now.astimezone(C.NY).date()):
        decide = R.decide_open if kind == "open" else R.decide_close
        out[f"{SN.BIRTHS_KIND[kind]}:{day}"] = decide(ctx, day, backfill_run=True, births_only=True)
    out["copy-evl6"] = P.copy_all_before_release(st, through=now.astimezone(C.NY).date())
    return out


def decide_evl4(ctx: R.Context, day: dt.date) -> dict:
    """PREREG-EVL-4's rows of the close of `day` decided by themselves, as a backfill (`decide_close` with
    `evl4_only`); when their PM rows wait on verdicts only the session's OPEN decision asks, that decision's own asks
    are made (`decide_open` with `ask_only`: no intent, no receipt) and the rows are decided again."""
    out = R.decide_close(ctx, day, backfill_run=True, evl4_only=True)
    if out.get("pending") and R.waits_on_open(out):
        R.decide_open(ctx, day, backfill_run=True, ask_only=True)
        out = R.decide_close(ctx, day, backfill_run=True, evl4_only=True)
    return out


def decide_evl5(ctx: R.Context, day: dt.date) -> dict:
    """PREREG-EVL-5's rows of the close of `day` decided by themselves, as a backfill (`decide_close` with `evl5_only`:
    its section 3); they ask only the verdicts this file's rows read (section 1.2), never one of the OPEN decision."""
    return R.decide_close(ctx, day, backfill_run=True, evl5_only=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m league.events")
    ap.add_argument("--state", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sessions")
    s.add_argument("--from", dest="first", type=_day, required=True)
    s.add_argument("--to", dest="last", type=_day, required=True)
    sub.add_parser("record")
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="first", type=_day, required=True)
    b.add_argument("--to", dest="last", type=_day, required=True)
    b.add_argument("--forms", default="8-K,4")
    b.add_argument("--no-news", action="store_true")
    for name in ("decide-open", "decide-close"):
        d = sub.add_parser(name)
        d.add_argument("--day", type=_day, required=True)
        d.add_argument("--backfill", action="store_true")
        if name == "decide-close":
            d.add_argument("--evl4-only", action="store_true",
                           help="PREREG-EVL-4's rows alone, as a backfill (their own receipt, decide-close-evl4)")
            d.add_argument("--evl5-only", action="store_true",
                           help="PREREG-EVL-5's rows alone, as a backfill (their own receipt, decide-close-evl5)")
    sub.add_parser("catchup")
    sub.add_parser("tickers")
    sub.add_parser("equity")
    sub.add_parser("score")
    sub.add_parser("screen")
    sub.add_parser("bands")
    sub.add_parser("learners", help="PREREG-EVL-7's owed decisions (the reconstruction, the catch-up, late decisions), "
                                    "oldest first, as the House's learner task makes them")
    rp = sub.add_parser("report")
    rp.add_argument("--day", type=_day, default=None)
    bi = sub.add_parser("births")
    bi.add_argument("--day", type=_day, default=None)
    bi.add_argument("--specs", default=None)
    bi.add_argument("--dry-run", action="store_true")
    fa = sub.add_parser("facts")
    fa.add_argument("--day", type=_day, default=None)
    fa.add_argument("--specs", default=None)
    sub.add_parser("score-unlatch")
    args = ap.parse_args(argv)
    if args.cmd == "score-unlatch":     # (release 1019i: the parity latch, cleared with no gateway and no program read)
        with S.Store(args.state) as st:
            out = {"cleared": SC.unlatch(st)}
        json.dump(out, sys.stdout, default=str, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    with S.Store(args.state) as st:
        P.load_births(st)       # (R3: the registered births, after every PREREG program)
        gw = G.Gateway(G.token_from_env(), min_interval=0.05)
        ctx = R.Context(st, gw, G.sec_getter())
        if args.cmd == "sessions":
            out = {"sessions": C.refresh(st, gw, args.first, args.last)}
        elif args.cmd == "record":
            out = R.record_pass(ctx)
        elif args.cmd == "backfill":
            out = R.backfill(ctx, args.first, args.last, forms=tuple(args.forms.split(",")), news=not args.no_news)
        elif args.cmd == "decide-open":
            out = R.decide_open(ctx, args.day, backfill_run=args.backfill)
        elif args.cmd == "decide-close" and args.evl4_only:
            out = decide_evl4(ctx, args.day)
        elif args.cmd == "decide-close" and args.evl5_only:
            out = decide_evl5(ctx, args.day)
        elif args.cmd == "decide-close":
            out = R.decide_close(ctx, args.day, backfill_run=args.backfill)
        elif args.cmd == "tickers":
            out = {"snapshot": ctx.snapshot_tickers()}
        elif args.cmd == "equity":
            out = SC.record_equity(st, gw, now=ctx.now())
        elif args.cmd == "score":
            out = SC.settle(st, gw, now=ctx.now())
        elif args.cmd == "screen":
            out = SN.run(st, ctx.now().astimezone(C.NY).date(), now=ctx.now())
        elif args.cmd == "bands":
            from . import bands as BA

            out = {"bands": {f"{p}@v{v}": b for (p, v), b in sorted(BA.bands(st).items())},
                   "review": BA.review(st, now=ctx.now())}
        elif args.cmd == "learners":
            from . import learner as LR

            out = {"catchup": LR.catchup(st, ctx.now), "still_owed": len(LR.due(st, ctx.now()))}
        elif args.cmd in ("births", "facts"):
            from . import births as BI

            day = args.day or ctx.now().astimezone(C.NY).date()
            if args.cmd == "facts":
                facts = BI.Facts(st, day)
                out = facts.facts()
                if args.specs:
                    with open(args.specs, encoding="utf-8") as fh:
                        listed = json.load(fh)
                    out["candidates"] = facts.candidates([x.get("spec") if isinstance(x, dict) and "spec" in x else x
                                                          for x in listed])
            else:
                specs = None
                if args.specs:
                    with open(args.specs, encoding="utf-8") as fh:
                        specs = json.load(fh)
                    if not isinstance(specs, list):
                        raise SystemExit("--specs: a JSON list of {spec, why}")
                out = BI.night(st, gw, today=day, now=ctx.now, proposals=specs, dry_run=args.dry_run)
        elif args.cmd == "report":
            day = args.day or ctx.now().astimezone(C.NY).date()
            rep = RP.build(st, day, now=ctx.now())
            text = RP.render(rep)
            path = st.root / "reports" / f"{day.isoformat()}.txt"
            path.parent.mkdir(exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            (st.root / "reports" / f"{day.isoformat()}.json").write_text(json.dumps(rep, default=str, sort_keys=True), encoding="utf-8")
            out = {"report": str(path)}
        else:
            out = catchup(ctx)
    json.dump(out, sys.stdout, default=str, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
