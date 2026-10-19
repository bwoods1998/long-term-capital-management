"""`python -m league.events --state DIR <command>`: the event lane's passes (see league/events/run.py).

Commands: sessions --from D --to D | record | backfill --from D --to D | decide-open --day D [--backfill] |
decide-close --day D [--backfill] | catchup (every past decision from the registration time not yet made, as a
backfill). Prints one JSON summary.
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
    is a backfill."""
    st = ctx.store
    now = ctx.now()
    start = P.registered().astimezone(C.NY).date()
    done = {r[0] for r in st.db.execute("SELECT job FROM receipts WHERE status='ok' AND job LIKE 'decide-%'")}
    due = [s for s in C.sessions(st, start, now.astimezone(C.NY).date()) if s.open_decide <= now]
    recent = {s.day for s in due[-REDECIDE_SESSIONS:]}
    out = {}
    for s in due:
        live_open = now - s.open_decide <= dt.timedelta(minutes=10)
        if f"decide-open:{s.day}" not in done or s.day in recent:
            out[f"open:{s.day}"] = R.decide_open(ctx, s.day, backfill_run=not live_open)
        if s.close_decide + dt.timedelta(minutes=1) <= now and (f"decide-close:{s.day}" not in done or s.day in recent):
            live_close = now - s.close_decide <= dt.timedelta(minutes=10)
            out[f"close:{s.day}"] = R.decide_close(ctx, s.day, backfill_run=not live_close)
    return out


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
    sub.add_parser("catchup")
    sub.add_parser("tickers")
    sub.add_parser("equity")
    sub.add_parser("score")
    sub.add_parser("screen")
    sub.add_parser("bands")
    rp = sub.add_parser("report")
    rp.add_argument("--day", type=_day, default=None)
    args = ap.parse_args(argv)
    with S.Store(args.state) as st:
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
