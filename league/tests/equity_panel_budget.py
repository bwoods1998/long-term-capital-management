"""THE `equity_panel` JOB AT THE REAL PANEL'S SIZE, under the ops child's own address-space limit (the review's
live-5; `league/tests/test_equity_panel.py` `TheJobFitsItsMemory` drives it). Not a test module: a made-up world that
is cheap to build at 700 assets x 2,455 sessions, and the child that runs the job in it.

THE WORLD. `N_OPEN` open members and `N_ENDED` ended ones (the captain's probe counted about these) beside the 12 REF
columns, from 2016 through `LAST`, every price a FORMULA of (aid, session number) on the cent grid (`cents`): the
store on disk (`build`, the parent's: vectorised, a second) and the venue's answers (`Venue`, the child's: a page of
rows at a time, nothing held) are the same numbers without either side keeping the other's arrays. No event, so
adjusted equals raw, except the names that go ex-dividend on `LAST` (`restated`): every earlier adjusted bar of
theirs is restated by the venue, the daily run's vintage test sees it, and each is fetched again whole.

THE CHILD (`child`, started by `BOOT`): exactly the ops child's order (`league/ops/__main__.py`): THE LIMIT FIRST
(`limit(None, extra_mb)`: RLIMIT_AS = the address space now + `extra_mb`), then the job's imports, then the job.
It prints one JSON line: the receipt's counts, the kernel's high-water mark of the address space and the cap.
Synthetic figures only; nothing here is market data.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

N_OPEN, N_ENDED = 470, 230
LAST = dt.date(2026, 10, 9)                # the session the daily run appends
BEFORE = dt.date(2026, 10, 8)              # the store on disk is through this one
NOW = dt.datetime(2026, 10, 10, 1, 55, tzinfo=dt.timezone.utc).timestamp()      # the job's own time of night
#: What the child is started with: `python -c BOOT <state> <extra_mb> <restated>` (the limit before any import of the
#: job's, numpy among them; `OPENBLAS_NUM_THREADS` 1 in its environment, as the ops runner sets it).
BOOT = ("import sys; from league.ops import __main__ as ops; limits = ops.limit(None, int(sys.argv[2])); "
        "from league.tests import equity_panel_budget as B; B.child(sys.argv[1], int(sys.argv[3]), limits)")
SWITCH_ON = '{"elane": {"panel": {"mode": "train"}}}'


def layout() -> tuple[list[tuple[str, dt.date, dt.date | None]], dict[str, dt.date]]:
    """([(ticker, start, end | None)], {ticker: the last day it has a bar}) of the made-up index."""
    names = ["Q" + "".join(chr(ord("A") + (k // 26 ** p) % 26) for p in (2, 1, 0)) for k in range(N_OPEN + N_ENDED)]
    ends = [dt.date(y, m, 15) for y in (2017, 2018, 2019, 2022, 2023, 2024, 2025) for m in (2, 5, 8, 11)]
    spells: list[tuple[str, dt.date, dt.date | None]] = []
    last: dict[str, dt.date] = {}
    for k, name in enumerate(names):
        end = None if k < N_OPEN else ends[k % len(ends)]
        spells.append((name, dt.date(2010, 1, 4), end))
        if end is not None:
            last[name] = end - dt.timedelta(days=1)
    return spells, last


def cents(aid: Any, i: Any) -> Any:
    """The raw close in cents of asset `aid` at session number `i` (ints, or numpy arrays that broadcast): a slow
    sawtooth, never a jump."""
    return 3000 + 7 * (aid % 3000) + (i * (3 + aid % 7)) % 40


def volume(aid: Any, i: Any) -> Any:
    return 2_000_000 + 1000 * ((i + aid) % 50)


def restated_aids(assets: dict, restated: int) -> set[int]:
    """The first `restated` open members, by aid: ex-dividend on `LAST`."""
    opened = sorted(int(a) for a, row in assets.items() if not row.get("ref") and row["spells"][-1][2] is None)
    return set(opened[:int(restated)])


def build(state: Path) -> dict[str, Any]:
    """The universe and the panel store on disk under `state`, through `BEFORE`, as the two jobs leave them (the
    lane's switch up). Returns {"sessions", "assets"}."""
    import numpy as np

    from league.ops import equity_panel as P
    from league.ops import equity_universe as U
    from league.xs import config as xs_config
    from league.xs import store as xs_store

    state.mkdir(parents=True, exist_ok=True)
    (state / "swarm.json").write_text(SWITCH_ON, encoding="utf-8")
    root = state / U.STORE_DIR
    spells, last = layout()
    venue = {t: {"id": "fake", "status": "active", "tradable": True, "fractionable": True, "exchange": "FAKE"}
             for t, _, _ in spells}
    table = U.assign(spells, None, (), exits={}, venue=venue)
    U.ensure_salt(root)
    U._publish(root, files={U.SOURCE_FILE: U._json_bytes({"commit": "0" * 40}),
                            U.SPELLS_FILE: U._spells_csv(spells, set(spells)), U.ASSETS_FILE: U._json_bytes(table),
                            U.TRADABLE_FILE: U._json_bytes({"as_of": LAST.isoformat(), "stock": U.tradable(table, LAST)})},
               manifest={"version": xs_store.UNIVERSE_VERSION, "audit": {"passed": True}})
    assets = U.read_universe(root)["assets"]
    calendar = U.store_sessions(BEFORE)
    days = [d for d, _ in calendar]
    aids = U.columns(assets)
    n, m = len(days), len(aids)
    i = np.arange(n, dtype=np.int64)[:, None]
    a = np.array(aids, dtype=np.int64)[None, :]
    close = cents(a, i).astype(np.float64)
    raw = np.empty((n, m, 5))
    raw[..., 0], raw[..., 1], raw[..., 2], raw[..., 3] = (close - 5) / 100, (close + 10) / 100, (close - 12) / 100, close / 100
    raw[..., 4] = volume(a, i)
    ordinals = np.array([d.toordinal() for d in days])
    for k, aid in enumerate(aids):
        ended = last.get(str(assets[str(aid)]["symbol"]))
        if ended is not None:
            raw[ordinals > ended.toordinal(), k, :] = np.nan
    adj = np.array(raw[..., :4])
    member = U.membership(assets, days)
    hidden = np.zeros(m, dtype=bool)
    tradable = np.ones((n, m), dtype=bool)
    tradable[:, :len(xs_config.REF)] = False
    xs_store.write_panel(root, days=days, early=[bool(e) for _, e in calendar], aids=aids, raw=raw, adj=adj,
                         member=member, tradable=tradable, hs=P.hs_table(root, aids), fetched_through=BEFORE,
                         vintage={aid: BEFORE for aid in aids}, audit={"reads": {}, "blank": [], "full_failures": 0},
                         masked=hidden.tolist(), coverage=P.coverage(member, raw, days, masked=hidden, floor=0.97),
                         full_at=BEFORE, revisions=0, hs_share=0.0, live_from=None, i6=None)
    return {"sessions": n, "assets": m - len(xs_config.REF)}


class Venue:
    """The made-up venue behind the gateway, by formula: `GET` of the bars route answers a page of at most `limit`
    rows, the symbols in order and each one's sessions in order, with a page token while more remain. It holds the
    calendar and one small table an asset, never a bar."""

    def __init__(self, root: Path, restated: int):
        from league.ops import equity_universe as U
        from league.tests.test_equity_panel import stamp

        assets = U.read_universe(root)["assets"]
        _, last = layout()
        self.days = [d for d, _ in U.store_sessions(LAST)]
        self.stamps = [stamp(d) for d in self.days]
        self.row = {d: i for i, d in enumerate(self.days)}
        self.aid = {str(row["symbol"]): int(aid) for aid, row in assets.items()}
        self.until = {t: last[t] for t in last}
        self.restated = restated_aids(assets, restated)
        self.requests = 0

    def _span(self, symbol: str, start: str, end: str) -> range:
        first, final = dt.date.fromisoformat(start[:10]), dt.date.fromisoformat(end[:10])
        final = min(final, self.until.get(symbol, final))
        inside = [i for i, d in enumerate(self.days) if first <= d <= final]
        return range(inside[0], inside[-1] + 1) if inside else range(0)

    def _bar(self, aid: int, i: int, adjustment: str) -> dict[str, Any]:
        c = cents(aid, i)
        o, h, l = c - 5, c + 10, c - 12                                          # noqa: E741
        if adjustment == "all" and aid in self.restated and self.days[i] < LAST:
            o, h, l, c = (round(x * 0.99) for x in (o, h, l, c))                 # noqa: E741 - served to the cent
        return {"t": self.stamps[i], "o": o / 100, "h": h / 100, "l": l / 100, "c": c / 100, "v": volume(aid, i),
                "n": 100, "vw": c / 100}

    def get(self, path: str, params: Any = None) -> dict[str, Any]:
        from league.ops import equity_panel as P

        self.requests += 1
        if path != P.BARS or str(params.get("timeframe")) != "1Day":
            raise AssertionError(f"the made-up venue has no answer for {path} {params.get('timeframe')}")
        symbols = [s for s in str(params["symbols"]).split(",") if s in self.aid]
        spans = [(s, self._span(s, str(params["start"]), str(params["end"]))) for s in symbols]
        skip, room = int(params.get("page_token") or 0), int(params.get("limit") or P.PAGE_LIMIT)
        bars: dict[str, list] = {}
        seen = 0
        for symbol, span in spans:
            if seen + len(span) <= skip:
                seen += len(span)
                continue
            for i in span[max(0, skip - seen):]:
                if not room:
                    return {"bars": bars, "next_page_token": str(skip + sum(len(v) for v in bars.values()))}
                bars.setdefault(symbol, []).append(self._bar(self.aid[symbol], i, str(params["adjustment"])))
                room -= 1
            seen += len(span)
        return {"bars": bars, "next_page_token": None}


def vm_peak_mb() -> float:
    """The kernel's own high-water mark of this process's address space (VmPeak), in MB; 0.0 where /proc does not say."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmPeak:"):
                return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def child(state: str, restated: int, limits: dict[str, Any]) -> None:
    """The job in this process, the limit already set: one JSON line on stdout."""
    from league.ops import equity_panel as P
    from league.ops import equity_universe as U
    from league.ops.context import Context

    root = Path(state)
    venue = Venue(root / U.STORE_DIR, restated)
    ctx = Context("equity_panel", root=root, due_at=NOW, clock=lambda: NOW, gateway=venue, config={}, settings_value={})
    try:
        receipt = P.run(ctx, sleep=lambda seconds: None)
    except MemoryError:
        receipt = {"status": "raised", "error": "MemoryError"}
    keep = ("ok", "status", "error", "why", "mode", "sessions", "assets", "members", "calls", "refetched", "appended",
            "verdict", "fetched_through", "revisions")
    out = {"receipt": {k: receipt.get(k) for k in keep if k in receipt}, "i6": receipt.get("i6"),
           "vm_peak_mb": round(vm_peak_mb(), 1), "cap_mb": round(int(limits.get("as_bytes") or 0) / 2 ** 20, 1),
           "requests": venue.requests, "alerts": [a.get("text", "")[:200] for a in ctx.alerts][:6]}
    sys.stdout.write(json.dumps(out) + "\n")
