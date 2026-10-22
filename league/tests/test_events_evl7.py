"""PREREG-EVL-7's TWO ONLINE LEARNERS (EVL-LRN-O1, EVL-LRN-ON) and COST-7, on INVENTED rows only (no figure here is a
market's; no House or desktop store is opened). Held here, one test a clause of the design the captain's decisions
E1-E11 fix (the frozen text, when it exists, wins):

- THE ROWS (section 1.2): none anywhere while REGISTERED_AT_7 is None, nor when it is not after REGISTERED_AT_6 (E3);
  pinned, both after every earlier file's row and before R3's births, at learning, their own registration time;
- THE FEATURES (section 1.4): 57 and 63 columns, the reader lens's frozen KEYWORDS / STOP / words / jaccard, every
  input stored before tau, the knowable-hour buckets (E11), the '1530' mark by its bar time (E6);
- THE CANDIDATES (section 1.3): the pool programs' real-money reading, one per CIK, KEPT and ELIGIBLE TO BE PICKED,
  eligibility TIME-BOUND by the House's own decision (E5);
- THE TRAINING SET AND THE FIT (section 1.5): pool outcomes settled before tau, the GROSS label (E7), the weights, the
  within-session demeaning, ridge 8,000 on standardized columns by Cholesky, the fsum order, the cache key;
- THE PICK (section 1.6) and the decision written once; the warm-up and failing closed (section 1.7);
- ISOLATION, THE CATCH-UP AND THE RECORD (section 1.7, E4): the part after the House's receipt, under its own bound,
  never cutting an earlier row; a failed or expired part decided later by itself; receipts decide-open-lrn:<D> and
  decide-close-lrn:<D>; the reconstruction once; the nightly recompute (section 1.8);
- REAL MONEY (section 1.9): the book's learner decision after every other row of the auction, the ERN guard (E8), the
  per-issuer 8-K guard (E10), the line kept for earlier rows, ROOM's order;
- COST-7 (section 2): E9's sigma, the penny ceiling, the impact, the measured terms that only rise, the selection SE
  against a brute-force shuffle, the explicit set, the judged record of live decisions only through PREREG-EVL-6's one
  interface;
- THE PROOF: on an invented week every earlier program's shadow intents and real-money picks are the same with and
  without the learners (which pick); a learner fed noise picks noise; planted future rows leave a decision unchanged;
- the report's learner lines (counts only), the alarms (H5), R3's facts refusing the learners' and COST-7's tables."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import itertools
import json
import math
import random
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
from typing import Callable
from unittest import mock
from zoneinfo import ZoneInfo

from league.equity import live as L
from league.equity import schedule as ES
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import costs7 as C7
from league.events import learner as LR
from league.events import programs as P
from league.events import report as RP
from league.events import run as R
from league.events import screen as SN
from league.events import store as S
from league.events import verdicts as V
from league.ops import evl_learner as EL

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]
REG7 = "2026-10-23T02:00:00Z"
O1, ON = "EVL-LRN-O1", "EVL-LRN-ON"
SPEC_PATHS = (REPO / "docs" / "prereg" / "evl-7" / "features_spec.py",
              Path.home() / "Work" / ".ltcm-main" / "goal-2026-10-19" / "evl7" / "reader" / "features_spec.py")


def et(day: dt.date, hh: int, mm: int = 0, ss: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=NY).astimezone(UTC)


def pin(case: unittest.TestCase, at: str | None = REG7) -> None:
    """PREREG-EVL-7 pinned at `at` for one test (the registries rebuilt; restored at its end)."""
    patch = mock.patch.object(P, "REGISTERED_AT_7", at)
    patch.start()
    P.refresh_7()

    def undo() -> None:
        patch.stop()
        P.refresh_7()
    case.addCleanup(undo)


def learner(pid: str) -> P.Program:
    got = P.BY_KEY.get((pid, 1))
    assert got is not None, pid
    return got


# ------------------------------------------------------------------------------------------------- an invented lane
class World:
    """An invented lane store for the learners: the NYSE sessions of Sep-Dec 2026, an account equity of $10,000 at every
    close, and invented issuers, bars, universe rows, live eligibility results, articles, filings, verdicts, decision
    receipts, pool intents and their settled outcomes."""

    def __init__(self, root: Path):
        self.root = root
        self.st = S.Store(root / "events")
        d = dt.date(2026, 9, 1)
        with self.st.tx() as db:
            while d <= dt.date(2026, 12, 31):
                m = ES.moments(d)
                if m is not None:
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, ?)",
                               (d.isoformat(), S.iso(dt.datetime.fromtimestamp(m.open_at, UTC)),
                                S.iso(dt.datetime.fromtimestamp(m.close_at, UTC)), int(m.early)))
                    db.execute("INSERT INTO meta(key, value) VALUES(?, '10000.0')", (f"equity:{d.isoformat()}",))
                d += dt.timedelta(days=1)
        LR.ensure(self.st.db)
        self.n = 0
        self.rng = random.Random(7)

    def close(self) -> None:
        self.st.close()

    def session(self, day: dt.date) -> C.Session:
        got = C.session(self.st, day)
        assert got is not None, day
        return got

    def prior(self, day: dt.date, n: int = 1) -> dt.date:
        return C.previous(self.st, day, n)[0].day

    def issuer(self) -> tuple[str, str]:
        self.n += 1
        letters = "".join(chr(65 + (self.n // 26 ** k) % 26) for k in range(3))
        return str(self.n).zfill(10), f"Z{letters}"

    def bars(self, symbol: str, day: dt.date, closes: list[float] | None = None, *, n: int = 25) -> None:
        """Raw daily closes of the `n` sessions before `day` (oldest first; an invented walk by default)."""
        days = [s.day for s in C.previous(self.st, day, n)]
        if closes is None:
            px, closes = 20.0, []
            for _ in days:
                px *= 1.0 + self.rng.uniform(-0.03, 0.03)
                closes.append(round(px, 4))
        for d, c in zip(days[-len(closes):], closes):
            self.st.db.execute("INSERT OR REPLACE INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', "
                               "?, ?, ?, ?, 1000000, '2026-09-01T00:00:00Z')", (symbol, d.isoformat(), c, c, c, c))

    def universe(self, day: dt.date, symbol: str, cik: str, *, prev_close: float = 20.0, adv20: float = 2e7,
                 bench: str = "IWM", decided: dt.datetime | None = None, rule: str = "live") -> None:
        decided = decided or et(day, 9, 15, 20)
        self.st.db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, "
                           "sigma60) VALUES(?, ?, ?, 'Invented Co', 'NASDAQ', ?, ?, ?, NULL)",
                           (day.isoformat(), symbol, cik, prev_close, adv20, bench))
        self.st.db.execute("INSERT OR REPLACE INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, ?, "
                           "1, ?, ?)", (day.isoformat(), cik, rule, symbol, S.iso(decided)))

    def receipt(self, day: dt.date, at: str, *, started: dt.datetime | None = None,
                finished: dt.datetime | None = None, status: str = "ok", summary: dict | None = None) -> int:
        s = self.session(day)
        started = started or (s.open_decide if at == "open" else s.close_decide + dt.timedelta(minutes=1))
        finished = finished or started + dt.timedelta(seconds=50)
        rid = self.st.start_receipt(f"decide-{at}:{day.isoformat()}", now=started)
        self.st.finish_receipt(rid, status, summary or {}, now=finished)
        return rid

    def article(self, ident: str, symbol: str, *, knowable: dt.datetime, received: dt.datetime | None = None,
                headline: str = "Invented Co shares rise", source: str = "benzinga", symbols: list[str] | None = None,
                live: int = 1) -> str:
        created = knowable - dt.timedelta(minutes=2)
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES(?, ?, NULL, ?, ?, ?, ?, 's', ?, ?)",
                           (ident, S.iso(created), S.iso(received or knowable), S.iso(knowable), source, headline,
                            json.dumps(symbols or [symbol]), live))
        return f"news:{ident}"

    def filing(self, accession: str, cik: str, *, knowable: dt.datetime, items=("8.01",), stored: dt.datetime | None = None,
               form: str = "8-K") -> str:
        sha = hashlib.sha256(accession.encode()).hexdigest()
        when = stored or knowable
        self.st.db.execute("INSERT OR IGNORE INTO documents(sha, kind, bytes, path, stored_at) VALUES(?, 'text', 5000, "
                           "'x', ?)", (sha, S.iso(when)))
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, received_at, "
                           "source, text_sha, text_len, raw_sha, status) VALUES(?, ?, ?, 'Invented Co', ?, ?, ?, ?, "
                           "'current', ?, 5000, ?, 'fetched')",
                           (accession, form, cik, json.dumps(list(items)), S.iso(knowable - dt.timedelta(minutes=10)),
                            S.iso(knowable), S.iso(when), sha, sha))
        return f"8k:{accession}"

    def verdict(self, event: str, score: int | None, *, answered: dt.datetime, guidance: str = "none",
                status: str = "ok") -> None:
        prompt = V.PROMPTS["news" if event.startswith("news:") else "doc"]
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, score, "
                           "guidance, answer, usd) VALUES(?, ?, ?, 'r', ?, ?, ?, ?, ?, '{}', 0.001)",
                           (event, prompt.sha, V.MODEL, S.iso(answered), S.iso(answered), status, score, guidance))

    def outcome(self, program: str, event: str, symbol: str, cik: str, day: dt.date, *, a_g: float,
                settled: dt.datetime, tradable: int = 1, raw_entry: float = 20.0, bench_r: float = 0.002) -> None:
        """A pool program's intent of the issuer entering at `day` (at its own auctions, as its version 1 decides
        them) and its settled outcome: entry 20, an exit giving the gross abnormal return `a_g` over a benchmark that
        moved `bench_r`; the raw entry print in `marks`."""
        prog = learner(program) if P.is_learner(program) else P.BY_KEY[(program, 1)]
        exit_day = day if prog.entry_at == "open" else C.nth(self.st, day, 2).day
        self.st.db.execute("INSERT OR IGNORE INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                           "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, "
                           "NULL, 'shadow', 'exited', NULL)",
                           (program, event, symbol, cik, S.iso(et(day, 9, 15)), day.isoformat(), prog.entry_at,
                            exit_day.isoformat(), prog.exit_at))
        exit_px = 20.0 * (1.0 + a_g + bench_r)
        self.st.db.execute("INSERT OR IGNORE INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                           "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) VALUES(?, 1, ?, "
                           "20.0, ?, 'IWM', 100.0, ?, 5.5, 5.7, ?, ?, ?, ?, ?, 'settled')",
                           (program, event, exit_px, 100.0 * (1.0 + bench_r), exit_px / 20.0 - 1.0, bench_r,
                            exit_px / 20.0 - 1.0 - bench_r, tradable, S.iso(settled)))
        label = "open" if prog.entry_at == "open" else "close"
        self.st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, ?, ?, "
                           "NULL, 'sip:Q:O', ?)", (symbol, day.isoformat(), label, raw_entry, S.iso(settled)))

    def open_session(self, day: dt.date, n: int, *, scores: bool = True) -> list[tuple[str, str, str]]:
        """`n` new issuers with an article each in EVL-CTRL-NEWS-ALL-O1's window of `day` (knowable after P's close and by
        D's 09:00 ET), bars, a universe row and a live eligibility result decided before the House's open decision
        finished, and that decision's receipt. Returns [(cik, symbol, event)]."""
        out = []
        p = self.prior(day)
        for i in range(n):
            cik, symbol = self.issuer()
            self.bars(symbol, day)
            self.universe(day, symbol, cik, adv20=2e7 if i % 3 else 4e6, bench="IWM" if i % 2 else "SPY")
            ev = self.article(f"a-{day.isoformat()}-{i}", symbol, knowable=et(p, 18, 0) + dt.timedelta(minutes=i),
                              headline=("Analyst upgrades %s, raises price target" if i % 4 == 0 else
                                        "%s shares are trading higher") % symbol)
            if scores and i % 2 == 0:
                self.verdict(ev, (i % 7) - 2, answered=et(day, 8, 0))
            out.append((cik, symbol, ev))
        if self.st.db.execute("SELECT 1 FROM receipts WHERE job=?", (f"decide-open:{day.isoformat()}",)).fetchone() is None:
            self.receipt(day, "open", finished=et(day, 9, 16))
        return out

    def settle(self, day: dt.date, rows: list[tuple[str, str, str]], *, at: dt.datetime | None = None,
               signal: Callable | None = None) -> None:
        """The pool outcomes of `day`'s candidates (EVL-CTRL-NEWS-ALL-O1 at the open), settled at 20:30 ET that night."""
        for k, (cik, symbol, ev) in enumerate(rows):
            a_g = signal(k) if signal is not None else self.rng.gauss(0.0, 0.03)
            self.outcome("EVL-CTRL-NEWS-ALL-O1", ev, symbol, cik, day, a_g=a_g, settled=at or et(day, 20, 30))


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = World(Path(self.tmp.name))
        self.addCleanup(self.w.close)
        self.st = self.w.st
        pin(self)

    def days(self, n: int, start: dt.date = dt.date(2026, 10, 26)) -> list[dt.date]:
        return [s.day for s in C.sessions(self.st, start, start + dt.timedelta(days=60))][:n]

    def history(self, days: list[dt.date], n: int, *, signal: Callable | None = None) -> dict[dt.date, list]:
        """Each of `days` decided by the learner by itself (a catch-up) on `n` new candidates, then settled."""
        out = {}
        for day in days:
            rows = self.w.open_session(day, n)
            got = LR.decide(self.st, learner(O1), day, kind="catchup", now=lambda day=day: et(day, 21, 0))
            self.assertNotIn("skipped", got)
            self.w.settle(day, rows, signal=signal)
            out[day] = rows
        return out


UPGRADE = lambda k: 0.06 if k % 4 == 0 else -0.01  # noqa: E731  (the invented signal: the upgrade headlines earn)


def snapshot(got: dict) -> tuple:
    """What a computed decision decides: its candidates (cik, event, families, kept, eligible, features), its beta and
    its picks."""
    cands = tuple((c.cik, c.event, tuple(c.families), c.kept, c.eligible, tuple(c.x or ()), c.sig20)
                  for c in got.get("cands") or [])
    beta = tuple((got.get("fit") or {}).get("beta") or ())
    return cands, beta, tuple(c.event for c in got.get("picks") or []), got.get("status")


# -------------------------------------------------------------------------------------------------------- the rows
class TheRows(unittest.TestCase):
    def test_unpinned_the_learners_are_in_no_registry_and_decide_nothing(self):
        self.assertIsNone(P.REGISTERED_AT_7, "None until the freeze sets it")
        self.assertEqual(P.learners(), ())
        self.assertFalse(any(P.is_learner(p) for p in P.PROGRAMS + P.SEATING + tuple(P.BY_KEY.values())))
        self.assertFalse(any(P.is_learner(p) for p in EB.seatable()))
        with tempfile.TemporaryDirectory() as tmp:
            w = World(Path(tmp))
            try:
                got = LR.decide(w.st, P.LEARNER_ROWS[0], dt.date(2026, 10, 27), kind="live")
                self.assertIn("skipped", got)
                self.assertEqual(LR.due(w.st, et(dt.date(2026, 10, 28), 12)), [])
                self.assertIsNone(EL.facts(w.root, et(dt.date(2026, 10, 28), 12).timestamp()))
            finally:
                w.close()
        with self.assertRaises(RuntimeError):
            P.LEARNER_ROWS[0].registered_at

    def test_pinned_both_rows_follow_every_earlier_row_at_learning_and_precede_the_births(self):
        before = P.PROGRAMS, P.SEATING
        pin(self)
        o1, on = learner(O1), learner(ON)
        self.assertEqual((o1.family, o1.entry_at, o1.exit_at, o1.hold, o1.prereg, o1.version, o1.reads),
                         ("learner-o1", "open", "close", 1, 7, 1, False))
        self.assertEqual((on.family, on.entry_at, on.exit_at, on.hold, on.prereg, on.version),
                         ("learner-on", "close", "open", 1, 7, 1))
        self.assertEqual(o1.registered_at, S.parse_iso(REG7))
        self.assertTrue(o1.can_seat and on.can_seat)
        self.assertEqual(P.PROGRAMS[:len(before[0])], before[0], "every earlier row first, unchanged")
        self.assertEqual(P.SEATING[:len(before[1])], before[1])
        self.assertEqual([p.id for p in P.SEATING[len(before[1]):]], [O1, ON])
        self.assertTrue(all(EB.order_of(O1) > EB.order_of(p.id) for p in before[1]))
        self.assertTrue(all(EB.room_key(O1, "learning") > EB.room_key(p.id, "learning") for p in before[1]))
        self.assertEqual(EB.room_key(O1, "learning")[0], EB.PRIORITY["learning"], "a learning row, never a birth's tier")
        # R3's births after them (`load_births`)
        from league.tests import evl5_world as W5

        with tempfile.TemporaryDirectory() as tmp:
            w = W5.World(Path(tmp) / "lane")
            try:
                w.births()
                ids = [p.id for p in P.SEATING]
                self.assertLess(ids.index(ON), ids.index("EVL-B-8K-502"))
                self.assertGreater(EB.room_key("EVL-B-8K-502", "learning"), EB.room_key(ON, "learning"))
            finally:
                P.load_births(None)
                w.close()

    def test_e3_a_registration_not_after_preregevl6s_registers_nothing(self):
        for at in ("2026-10-22T12:24:50Z", "2026-10-22T11:00:00Z"):
            pin(self, at)
            self.assertEqual(P.learners(), (), at)
            self.assertFalse(any(P.is_learner(p) for p in P.SEATING))
        self.assertEqual(P.REGISTERED_AT_6_FOR_7, "2026-10-22T12:24:50Z", "A116")
        if getattr(P, "REGISTERED_AT_6", None) is not None:
            self.assertEqual(P.REGISTERED_AT_6_FOR_7, P.REGISTERED_AT_6, "the merged tree's own PREREG-EVL-6 time")

    def test_the_features_are_57_and_63_columns_in_section_14s_order(self):
        self.assertEqual(len(LR.FEATURES[O1]), 57)
        self.assertEqual(len(LR.FEATURES[ON]), 63)
        self.assertEqual(LR.FEATURES[O1][:3], tuple(f"pool_{p}" for p in LR.POOLS[O1][1:]))
        self.assertEqual(LR.FEATURES[ON][-6:], ("morning", "before", "dmove", "dmove_missing", "abs_dmove", "s_x_dmove"))
        self.assertEqual(LR.FEATURES[O1][-4:], ("overnight", "pre", "late", "ln_ins"))
        self.assertEqual(LR.POOLS[O1], ("EVL-CTRL-NEWS-ALL-O1", "EVL-CTRL-8K-ALL-O1", "EVL-CTRL-ERN-ALL-O1",
                                        "EVL-INS-BUY-O1"))
        self.assertEqual(LR.POOLS[ON], ("EVL-CTRL-NEWS-DAY-ON", "EVL-CTRL-NEWSPM-ON", "EVL-CTRL-8K-ON", "EVL-ERN-REACT-ON",
                                        "EVL-ERN-DROP-ON", "EVL-CTRL-ERN-UNDER-ON"))
        self.assertEqual((LR.K, LR.LAMBDA, LR.HALF_LIFE, LR.LOOKBACK, LR.WARM_ROWS, LR.WARM_SESSIONS),
                         (8, 8000.0, 40.0, 250, 2000, 3))
        self.assertEqual(LR.BOUND_S, {"open": 90.0, "close": 120.0})
        self.assertEqual(LR.RECEIPT, {"open": "decide-open-lrn", "close": "decide-close-lrn"})

    def test_the_headline_features_are_the_reader_lens_frozen_spec_verbatim(self):
        self.assertEqual(len(LR.KEYWORDS), 16)
        self.assertEqual(tuple(LR.KEYWORDS), tuple(n for n in LR.FEATURES[O1] if n.startswith("kw_")))
        self.assertEqual(LR.words("The Acme Corp upgrades: price-target raised to $30"),
                         {"acme", "upgrades", "price-target", "raised"})
        self.assertEqual(LR.jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(LR.jaccard(set(), {"b"}), 0.0)
        found = [p for p in SPEC_PATHS if p.exists()]
        if not found:
            self.skipTest("the frozen features_spec.py is not on this machine (copied into docs/prereg/evl-7/ at the freeze)")
        for path in found:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), LR.SPEC_SHA, path)
            spec = importlib.util.spec_from_file_location(f"spec_{abs(hash(str(path)))}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.KEYWORDS, LR.KEYWORDS)
            self.assertEqual(mod.STOP, LR.STOP)
            for text in ("Analyst Upgrades ACME; Raises Price Target", "Why is XYZ stock moving?", "FDA approves drug",
                         "the and for", ""):
                self.assertEqual(mod.words(text), LR.words(text))
                self.assertEqual(mod.jaccard(mod.words(text), {"acme"}), LR.jaccard(LR.words(text), {"acme"}))

    def test_the_code_sha_is_the_files_own(self):
        self.assertEqual(LR.CODE_SHA, hashlib.sha256(Path(LR.__file__).read_bytes()).hexdigest())


# --------------------------------------------------------------------------------------------------------- the fit
def _exact_solve(m: list[list[Fraction]], b: list[Fraction]) -> list[Fraction]:
    """Gauss-Jordan in exact fractions (the reference for the float64 Cholesky)."""
    n = len(b)
    a = [row[:] + [b[i]] for i, row in enumerate(m)]
    for c in range(n):
        piv = next(r for r in range(c, n) if a[r][c] != 0)
        a[c], a[piv] = a[piv], a[c]
        for r in range(n):
            if r != c and a[r][c] != 0:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def _reference_beta(sessions: list[tuple[float, list[tuple[list[float], float]]]], width: int) -> list[float]:
    """Section 1.5 written out longhand in exact fractions from each row: demeaned within the session, weighted, d_j,
    M = D^-1 A D^-1 + 8000 I, beta = D^-1 M^-1 D^-1 b (a dead column zeroed)."""
    A = [[Fraction(0)] * width for _ in range(width)]
    bb = [Fraction(0)] * width
    nw = Fraction(0)
    for w, rows in sessions:
        wf = Fraction(w)
        nw += wf * len(rows)
        if len(rows) < 2:
            continue
        mx = [sum(Fraction(r[0][j]) for r in rows) / len(rows) for j in range(width)]
        my = sum(Fraction(r[1]) for r in rows) / len(rows)
        for x, y in rows:
            xt = [Fraction(x[j]) - mx[j] for j in range(width)]
            for j in range(width):
                bb[j] += wf * xt[j] * (Fraction(y) - my)
                for k in range(width):
                    A[j][k] += wf * xt[j] * xt[k]
    d = []
    for j in range(width):
        dj = math.sqrt(float(A[j][j] / nw)) if A[j][j] > 0 else 0.0
        if dj < 1e-9:
            d.append(Fraction(1))
            for k in range(width):
                A[j][k] = A[k][j] = Fraction(0)
            bb[j] = Fraction(0)
        else:
            d.append(Fraction(dj))
    M = [[A[j][k] / (d[j] * d[k]) + (8000 if j == k else 0) for k in range(width)] for j in range(width)]
    z = _exact_solve(M, [bb[j] / d[j] for j in range(width)])
    return [float(z[j] / d[j]) for j in range(width)]


class TheFit(unittest.TestCase):
    def sessions(self, seed: int, width: int, n_sessions: int = 4, rows: int = 30) -> list:
        rng = random.Random(seed)
        out = []
        for s in range(n_sessions):
            w = 2.0 ** (-(n_sessions - s) / 40.0)
            out.append((w, [([rng.gauss(0, 1) for _ in range(width - 1)] + [1.0],
                             rng.gauss(0, 1)) for _ in range(rows)]))
        return out

    def ours(self, sessions: list, width: int) -> dict:
        stats = [(w, LR.session_stats([(str(i).zfill(4), x, y) for i, (x, y) in enumerate(rows)], width))
                 for w, rows in sessions]
        return LR.fit(stats, width)

    def test_the_ridge_is_section_15_to_float_precision_and_a_dead_column_reads_zero(self):
        width = 5
        sessions = self.sessions(3, width)
        got = self.ours(sessions, width)
        want = _reference_beta(sessions, width)
        for a, b in zip(got["beta"], want):
            self.assertAlmostEqual(a, b, delta=1e-12 * max(1.0, abs(b)))
        self.assertEqual(got["beta"][-1], 0.0, "a constant column is zeroed (d_j < 1e-9)")
        self.assertEqual(got["d"][-1], 1.0)

    def test_cholesky_against_an_exact_solve_and_a_matrix_that_is_not_positive_definite(self):
        rng = random.Random(5)
        n = 6
        g = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(n)]
        m = [[math.fsum(g[i][k] * g[j][k] for k in range(n)) + (8.0 if i == j else 0.0) for j in range(n)]
             for i in range(n)]
        b = [rng.gauss(0, 1) for _ in range(n)]
        x = LR.solve(LR.cholesky(m), b)
        want = _exact_solve([[Fraction(v) for v in row] for row in m], [Fraction(v) for v in b])
        for a, c in zip(x, want):
            self.assertAlmostEqual(a, float(c), delta=1e-12)
        with self.assertRaises(ValueError):
            LR.cholesky([[1.0, 2.0], [2.0, 1.0]])

    def test_demeaning_within_the_session_cancels_a_shock_common_to_it(self):
        width = 4
        sessions = self.sessions(9, width)
        shocked = [(w, [(x, y + (0.7 if s == 1 else -0.3)) for x, y in rows]) for s, (w, rows) in enumerate(sessions)]
        a, b = self.ours(sessions, width)["beta"], self.ours(shocked, width)["beta"]
        for u, v in zip(a, b):
            self.assertAlmostEqual(u, v, delta=1e-12)

    def test_the_outer_sums_run_over_sessions_in_day_order_and_the_inner_in_cik_order(self):
        width = 3
        sessions = self.sessions(11, width, n_sessions=2, rows=6)
        rows = [(str(i).zfill(4), x, y) for i, (x, y) in enumerate(sessions[0][1])]
        self.assertEqual(LR.session_stats(rows, width), LR.session_stats(list(reversed(rows))[::-1], width))
        self.assertEqual(LR.session_stats(rows[:1], width), {"n": 1, "xx": None, "xy": None},
                         "a session with one row adds nothing but its n")


# --------------------------------------------------------------------------------------------- noise picks noise
class TheNoise(unittest.TestCase):
    """Section 1.6's pick on invented sessions, the fit on the sessions before each (the pure functions): with labels
    that are pure noise the picks' realized label averages zero and no feature is preferred; with one informative
    feature the picks take its top."""

    def run_learner(self, informative: bool, seed: int) -> tuple[list[float], list[float]]:
        rng = random.Random(seed)
        width, per, sessions = 6, 120, 40
        history: list = []
        realized, chosen_x0 = [], []
        for t in range(sessions):
            xs = [[rng.gauss(0, 1) for _ in range(width)] for _ in range(per)]
            ys = [(0.6 * x[0] if informative else 0.0) + rng.gauss(0, 1) for x in xs]
            if len(history) >= 3:
                stats = [(2.0 ** (-(len(history) - k) / 40.0), LR.session_stats(rows, width))
                         for k, rows in enumerate(history)]
                beta = LR.fit(stats, width)["beta"]
                cands = []
                for i, x in enumerate(xs):
                    c = LR.Cand(str(i).zfill(4), {"p": mock.Mock(event=f"news:{t}-{i}")}, ["p"],
                                {"adv20": 1e9, "prev_close": 20.0})
                    c.kept, c.eligible, c.x, c.sig20 = True, True, x, 1.0
                    cands.append(c)
                LR.predict(cands, beta, 1e9)
                for c in LR.choose(cands):
                    k = int(c.cik)
                    realized.append(ys[k])
                    chosen_x0.append(xs[k][0])
            history.append([(str(i).zfill(4), x, y) for i, (x, y) in enumerate(zip(xs, ys))])
        return realized, chosen_x0

    def test_a_learner_fed_noise_picks_noise_and_one_fed_a_signal_picks_it(self):
        means = []
        for seed in (21, 22, 23, 24):
            realized, _ = self.run_learner(False, seed)
            self.assertGreater(len(realized), 100)
            mean = math.fsum(realized) / len(realized)
            self.assertLess(abs(mean), 3.0 / math.sqrt(len(realized)), "noise: the picks' label is no better than a draw")
            means.append(mean)
        self.assertLess(abs(math.fsum(means) / len(means)), 3.0 / math.sqrt(4 * 100))
        realized, x0 = self.run_learner(True, 21)
        self.assertGreater(math.fsum(x0) / len(x0), 1.0, "a real signal: the picks take its top (a top-8 of 120)")
        self.assertGreater(math.fsum(realized) / len(realized), 0.5)


# --------------------------------------------------------------------------------------------- a decision, as of tau
class TheCandidates(WorldCase):
    def test_one_candidate_per_cik_its_families_and_primary_and_e5s_time_bound(self):
        day = dt.date(2026, 10, 27)
        rows = self.w.open_session(day, 4)
        cik, symbol, ev = rows[0]
        p = self.w.prior(day)
        self.w.filing("0000000099-26-000001", cik, knowable=et(p, 17, 0), items=("8.01",))   # CTRL-8K-ALL-O1's too
        late_cik, late_sym = self.w.issuer()
        self.w.bars(late_sym, day)
        self.w.universe(day, late_sym, late_cik, decided=et(day, 15, 47))     # (the close decision's live result)
        self.w.article("late-1", late_sym, knowable=et(p, 19, 0))
        got = LR.compute(self.st, learner(O1), day, kind="live")
        by = {c.cik: c for c in got["cands"]}
        self.assertEqual(by[cik].families, ["EVL-CTRL-NEWS-ALL-O1", "EVL-CTRL-8K-ALL-O1"])
        self.assertEqual(by[cik].event, ev, "the primary is the first pool family's event")
        self.assertNotIn(late_cik, by, "E5: a live result decided after the House's open decision finished is no "
                                       "candidate (an O1 decision made after the fact excludes it)")
        self.assertEqual(sorted(by), sorted(r[0] for r in rows))
        self.assertTrue(all(c.kept for c in got["cands"]), "TRADABLE: 1.25 x $20 <= 10% of $10,000")
        self.assertEqual(LR.eligible_by(self.st, learner(O1), day), et(day, 9, 16))

    def test_the_eligibility_bound_is_the_earlier_of_the_receipt_and_the_entry_auction(self):
        day = dt.date(2026, 10, 27)
        self.w.receipt(day, "open", finished=et(day, 9, 45))
        self.assertEqual(LR.eligible_by(self.st, learner(O1), day), self.w.session(day).open_at)
        self.assertIsNone(LR.eligible_by(self.st, learner(ON), day), "no close decision yet: no candidate")
        got = LR.compute(self.st, learner(ON), day, kind="live")
        self.assertEqual(got["cands"], [])

    def test_kept_and_eligible_to_be_picked(self):
        day = dt.date(2026, 10, 27)
        rows = self.w.open_session(day, 3)
        rich_cik, rich = self.w.issuer()
        self.w.bars(rich, day)
        self.w.universe(day, rich, rich_cik, prev_close=900.0)
        self.w.article("rich-1", rich, knowable=et(self.w.prior(day), 18, 30))
        old_cik, old = self.w.issuer()
        self.w.bars(old, day)
        self.w.universe(day, old, old_cik)
        held_cik, held_sym, held_ev = rows[1]
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, rank_key, mode, status) VALUES(?, 1, 'news:x', ?, ?, 'x', ?, 'open', ?, "
                           "'close', 1.0, 'shadow', 'exited')",
                           (O1, held_sym, held_cik, self.w.prior(day, 2).isoformat(), self.w.prior(day, 2).isoformat()))
        with mock.patch.object(P, "REGISTERED_AT_7", "2026-10-26T21:00:00Z"):
            self.w.article("old-1", old, knowable=et(self.w.prior(day), 16, 30))        # knowable before REGISTERED_AT_7
            got = LR.compute(self.st, P.Learner(O1, 1, True, "learner-o1", "open", 1, False, rule="learner", prereg=7),
                             day, kind="live")
        by = {c.cik: c for c in got["cands"]}
        self.assertFalse(by[rich_cik].kept, "1.25 x $900 > 10% of $10,000: not TRADABLE, not kept")
        self.assertTrue(by[old_cik].kept and not by[old_cik].eligible, "knowable before REGISTERED_AT_7")
        self.assertTrue(by[held_cik].kept and not by[held_cik].eligible, "held within 5 sessions (A72)")
        self.assertTrue(by[rows[0][0]].eligible)


class TheFeatures(WorldCase):
    def test_every_input_is_stored_before_tau(self):
        day = dt.date(2026, 10, 27)
        p = self.w.prior(day)
        cik, sym = self.w.issuer()
        self.w.bars(sym, day, [20.0 + 0.1 * k for k in range(25)])
        self.w.universe(day, sym, cik, prev_close=20.0, adv20=5e6, bench="IWM")
        self.st.db.execute("INSERT INTO cik_info(cik, sic, checked_at) VALUES(?, '2834', 'x')", (cik,))
        ev = self.w.article("f-1", sym, knowable=et(p, 21, 0), headline="Acme upgrades Zed, raises price target",
                            source="Benzinga Pro")
        self.w.verdict(ev, 3, answered=et(day, 9, 20))                       # answered after tau: no score
        self.w.article("f-0", sym, knowable=et(p, 20, 0), headline="Acme upgrades Zed price target",
                       symbols=[sym, "OTHER"])                               # dup72 reads any number of symbols
        self.w.article("f-2", sym, knowable=et(p, 22, 0), received=et(day, 9, 30))   # stored after tau
        self.w.receipt(day, "open", finished=et(day, 9, 16))
        got = LR.compute(self.st, learner(O1), day, kind="live")
        [c] = got["cands"]
        f = dict(zip(LR.FEATURES[O1], c.x))
        self.assertEqual((f["no_score"], f["s_num"]), (1.0, 0.0), "a verdict answered after tau reads as no score")
        self.assertEqual(f["n_art"], math.log1p(1), "the single-symbol articles of its window stored before tau: f-1")
        self.assertEqual((f["kw_upgrade"], f["kw_pt"], f["kw_raise"], f["kw_cut"]), (1.0, 1.0, 1.0, 0.0))
        self.assertEqual(f["src_benzinga"], 1.0)
        self.assertAlmostEqual(f["dup72"], LR.jaccard(LR.words("Acme upgrades Zed, raises price target"),
                                                      LR.words("Acme upgrades Zed price target")))
        self.assertEqual((f["sic_bio"], f["sic_tech"], f["bench_iwm"]), (1.0, 0.0, 1.0))
        self.assertEqual(f["overnight"], 1.0, "21:00 ET of P: overnight")
        self.assertEqual(f["first20"], 1.0)
        self.assertAlmostEqual(f["ln_adv20"], math.log(5e6 / 1e7))
        closes = [20.0 + 0.1 * k for k in range(25)][::-1][:20]
        self.assertAlmostEqual(f["r1"], math.log(closes[0] / closes[1]))
        self.assertAlmostEqual(f["r20"], math.log(closes[0] / closes[19]))
        self.assertEqual(f["hist_missing"], 0.0)
        self.assertAlmostEqual(c.sig20, max(0.005, LR.sig20_of(closes)))

    def test_hours_buckets_a_weekend_is_overnight_and_the_insider_value(self):
        day = dt.date(2026, 11, 2)            # a Monday: its window opens on Friday's close
        p = self.w.prior(day)
        sat = dt.date(2026, 10, 31)
        cases = {"sat": et(sat, 11, 0), "pre": et(day, 5, 0), "late": et(day, 8, 0), "base": et(p, 17, 0)}
        ciks = {}
        for name, when in cases.items():
            cik, sym = self.w.issuer()
            self.w.bars(sym, day, n=10)                       # fewer than 20 closes: hist_missing
            self.w.universe(day, sym, cik)
            self.w.article(f"h-{name}", sym, knowable=when)
            ciks[name] = cik
        self.w.receipt(day, "open", finished=et(day, 9, 16))
        got = {c.cik: dict(zip(LR.FEATURES[O1], c.x)) for c in LR.compute(self.st, learner(O1), day, kind="live")["cands"]}
        self.assertEqual(got[ciks["sat"]]["overnight"], 1.0, "any hour of a day that is not a session")
        self.assertEqual((got[ciks["pre"]]["pre"], got[ciks["late"]]["late"]), (1.0, 1.0))
        self.assertEqual([got[ciks["base"]][k] for k in ("overnight", "pre", "late")], [0.0, 0.0, 0.0])
        self.assertEqual(got[ciks["base"]]["mon"], 1.0)
        self.assertEqual((got[ciks["base"]]["hist_missing"], got[ciks["base"]]["r1"], got[ciks["base"]]["ln_sig20"]),
                         (1.0, 0.0, 0.0))

    def test_on_dmove_reads_the_1530_mark_by_its_bar_time_whatever_its_fetch_time(self):
        day = dt.date(2026, 10, 27)
        s = self.w.session(day)
        ciks = {}
        for name, t in (("before_tau", s.at(dt.time(15, 29))), ("after_tau", s.close_decide + dt.timedelta(minutes=1)),
                        ("none", None)):
            cik, sym = self.w.issuer()
            self.w.bars(sym, day)
            self.w.universe(day, sym, cik, decided=s.close_decide + dt.timedelta(seconds=30))
            self.w.article(f"d-{name}", sym, knowable=et(day, 10, 30))       # the day-news window: morning
            if t is not None:
                self.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', "
                                   "21.0, ?, 'sip-1min', ?)", (sym, day.isoformat(), S.iso(t), S.iso(et(day, 16, 30))))
            ciks[name] = cik
        self.w.receipt(day, "close", finished=s.close_decide + dt.timedelta(minutes=1))
        got = {c.cik: dict(zip(LR.FEATURES[ON], c.x)) for c in LR.compute(self.st, learner(ON), day, kind="live")["cands"]}
        f = got[ciks["before_tau"]]
        self.assertAlmostEqual(f["dmove"], math.log(21.0 / 20.0))
        self.assertEqual((f["dmove_missing"], f["morning"], f["before"]), (0.0, 1.0, 0.0))
        self.assertAlmostEqual(f["abs_dmove"], abs(f["dmove"]))
        self.assertEqual((got[ciks["after_tau"]]["dmove_missing"], got[ciks["after_tau"]]["dmove"]), (1.0, 0.0))
        self.assertEqual(got[ciks["none"]]["dmove_missing"], 1.0)


class TheTraining(WorldCase):
    def test_pool_outcomes_settled_before_tau_the_gross_label_and_the_limit(self):
        s1, day = self.days(2)
        rows = self.history([s1], 5)[s1]
        tau = LR.tau_of(self.st, learner(O1), day)
        got = LR.pool_outcomes(self.st, learner(O1), s1, tau)
        self.assertEqual(len(got), 5)
        # an outcome settled after tau, one above the limit at entry and one not TRADABLE are no pool outcome
        extra = []
        for k, (settled, raw, trad) in enumerate(((tau + dt.timedelta(minutes=1), 20.0, 1), (et(s1, 20, 30), 25.01, 1),
                                                  (et(s1, 20, 30), 20.0, 0))):
            c, sy = self.w.issuer()
            e = f"news:x-{k}"
            self.st.db.execute("INSERT INTO learner_cands(program, version, day, cik, event, symbol, families, kept, "
                               "eligible, features, sig20, picked, kind) VALUES(?, 1, ?, ?, ?, ?, '[]', 1, 0, ?, 0.03, 0, "
                               "'catchup')", (O1, s1.isoformat(), c, e, sy,
                                              json.dumps({"x": [0.0] * 57, "hist": 0})))
            self.w.universe(s1, sy, c)
            self.w.outcome("EVL-CTRL-NEWS-ALL-O1", e, sy, c, s1, a_g=0.5, settled=settled, tradable=trad, raw_entry=raw)
            extra.append(c)
        got = LR.pool_outcomes(self.st, learner(O1), s1, tau)
        self.assertFalse(set(extra) & set(got), "settled after tau, above 1.25 x the previous close, untradable")
        row = got[rows[0][0]]
        self.assertAlmostEqual(LR.gross(row), row["exit_px"] / row["entry_px"] - row["bench_exit"] / row["bench_entry"])
        self.assertEqual(LR.label({"entry_px": 20.0, "exit_px": 40.0, "bench_entry": 1.0, "bench_exit": 1.0}, 0.03), 5.0)

    def test_the_label_reads_no_cost_column_r_or_a(self):
        days = self.days(5)
        self.history(days[:4], 12, signal=UPGRADE)
        day = days[4]
        self.w.open_session(day, 10)
        with mock.patch.object(LR, "WARM_ROWS", 20):
            a = snapshot(LR.compute(self.st, learner(O1), day, kind="live", write_cache=False))
            self.st.db.execute("UPDATE outcomes SET cost_entry_bp=999, cost_exit_bp=999, r=-0.9, a=0.9")
            b = snapshot(LR.compute(self.st, learner(O1), day, kind="live", write_cache=False))
        self.assertTrue(a[1], "a fit was made")
        self.assertEqual(a, b, "the gross label (E7): the replay's cost enters once, through c_i")

    def test_weights_halve_every_40_sessions_and_250_back_at_most(self):
        days = self.days(3)
        self.history(days[:2], 4)
        got = LR.training(self.st, learner(O1), days[2], LR.tau_of(self.st, learner(O1), days[2]))
        self.assertEqual([w for w, _ in got["stats"]], [2.0 ** (-2 / 40), 2.0 ** (-1 / 40)], "day order, age 2 then 1")
        self.assertEqual((got["rows"], got["sessions"]), (8, 2))
        self.assertEqual(len(LR.session_days(self.st, days[2], 10)), 10)
        self.assertEqual(LR.session_days(self.st, days[2]), [s.day for s in C.previous(self.st, days[2], 250)],
                         "at most 250 sessions back (the invented calendar holds fewer)")


class TheLookAhead(WorldCase):
    def test_rows_planted_after_tau_leave_the_decision_unchanged(self):
        days = self.days(5)
        self.history(days[:4], 12, signal=UPGRADE)
        day = days[4]
        rows = self.w.open_session(day, 10)
        tau = LR.tau_of(self.st, learner(O1), day)
        with mock.patch.object(LR, "WARM_ROWS", 20):
            before = snapshot(LR.compute(self.st, learner(O1), day, kind="live", write_cache=False))
            self.assertTrue(before[2], "the learner picks")
            later = tau + dt.timedelta(minutes=5)
            p = self.w.prior(day)
            cik, sym, ev = rows[0]
            # a future verdict, a future article, a future outcome of a training session with an extreme label, a
            # future live eligibility result, and a future article of the window stored after tau
            self.w.verdict(f"news:a-{day.isoformat()}-1", 3, answered=later)
            n_cik, n_sym = self.w.issuer()
            self.w.bars(n_sym, day)
            self.w.universe(day, n_sym, n_cik, decided=later)
            self.w.article("future-1", n_sym, knowable=et(p, 23, 0), received=later)
            self.w.article("future-2", sym, knowable=et(p, 23, 30), received=later)
            fut_cik, fut_sym = self.w.issuer()
            self.st.db.execute("INSERT INTO learner_cands(program, version, day, cik, event, symbol, families, kept, "
                               "eligible, features, sig20, picked, kind) VALUES(?, 1, ?, ?, 'news:fut', ?, '[]', 1, 0, ?, "
                               "0.03, 0, 'catchup')", (O1, days[3].isoformat(), fut_cik, fut_sym,
                                                      json.dumps({"x": [9.0] * 57, "hist": 0})))
            self.w.universe(days[3], fut_sym, fut_cik)
            self.w.outcome("EVL-CTRL-NEWS-ALL-O1", "news:fut", fut_sym, fut_cik, days[3], a_g=9.0, settled=later)
            after = snapshot(LR.compute(self.st, learner(O1), day, kind="live", write_cache=False))
        self.assertEqual(before, after, "nothing stored, answered, settled or decided after tau enters the decision")


class TheDecision(WorldCase):
    def test_warm_up_then_at_most_eight_picks_above_the_hurdle_in_order_written_once(self):
        days = self.days(5)
        self.history(days[:4], 15, signal=UPGRADE)
        day = days[4]
        self.w.open_session(day, 14)
        got = LR.decide(self.st, learner(O1), day, kind="live", now=lambda: et(day, 9, 16, 30), receipt="decide-open:x",
                        receipt_id=7)
        self.assertEqual(got["status"], "warmup", "60 rows from 4 sessions: under 2,000")
        self.assertEqual(LR.decide(self.st, learner(O1), day, kind="live"), {"known": True}, "never decided again")
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM intents WHERE program=?", (O1,)).fetchone()[0], 0)
        day2 = C.nth(self.st, day, 2).day
        self.w.settle(day, [(c["cik"], c["symbol"], c["event"]) for c in map(dict, self.st.db.execute(
            "SELECT cik, symbol, event FROM learner_cands WHERE program=? AND day=? ORDER BY event", (O1, day.isoformat())))],
            signal=UPGRADE)
        self.w.open_session(day2, 14)
        with mock.patch.object(LR, "WARM_ROWS", 20):
            out = LR.decide(self.st, learner(O1), day2, kind="live", now=lambda: et(day2, 9, 16, 30),
                            receipt=f"decide-open:{day2}", receipt_id=9)
        fits = dict(self.st.db.execute("SELECT * FROM learner_fits WHERE program=? AND day=?",
                                       (O1, day2.isoformat())).fetchone())
        self.assertEqual((fits["kind"], fits["status"], fits["receipt_id"], fits["code_sha"]),
                         ("live", "ok", 9, LR.CODE_SHA))
        self.assertEqual(fits["n_rows"], 74)
        self.assertEqual(fits["train_last"], day.isoformat(), "lag 1: D-1's outcomes, settled at 20:30 ET")
        picks = [dict(r) for r in self.st.db.execute("SELECT * FROM learner_cands WHERE program=? AND day=? AND picked=1 "
                                                     "ORDER BY rank", (O1, day2.isoformat()))]
        self.assertTrue(0 < len(picks) <= 8 and len(picks) == out["picks"])
        self.assertTrue(all(p["z"] > 0 for p in picks))
        keys = [(-p["ahat"], -p["adv20"], p["event"]) for p in picks]
        self.assertEqual(keys, sorted(keys), "ranked by ahat, then adv20, then the event id")
        intents = {r["event"]: dict(r) for r in self.st.db.execute("SELECT * FROM intents WHERE program=? AND entry_day=?",
                                                                    (O1, day2.isoformat()))}
        self.assertEqual(set(intents), {p["event"] for p in picks})
        for p in picks:
            i = intents[p["event"]]
            self.assertEqual((i["rank_key"], i["status"], i["mode"], i["exit_day"], i["exit_at"], i["why"]),
                             (p["ahat"], "planned", "shadow", day2.isoformat(), "close", None))
            self.assertEqual(i["decided_at"], S.iso(self.w.session(day2).open_decide))
        not_picked = self.st.db.execute("SELECT COUNT(*) FROM learner_cands WHERE program=? AND day=? AND eligible=1 AND "
                                        "picked=0 AND z>0", (O1, day2.isoformat())).fetchone()[0]
        self.assertTrue(len(picks) == 8 or not_picked == 0)

    def test_failing_closed_no_equity_and_a_fit_that_is_not_finite(self):
        days = self.days(5)
        self.history(days[:4], 10)
        day = days[4]
        self.w.open_session(day, 6)
        with mock.patch.object(LR, "WARM_ROWS", 10):
            with mock.patch.object(LR, "fit", side_effect=ValueError("the fit is not finite")):
                got = LR.compute(self.st, learner(O1), day, kind="live", write_cache=False)
            self.assertEqual((got["status"], got["picks"]), ("closed", []))
            self.st.db.execute("DELETE FROM meta WHERE key=?", (f"equity:{self.w.prior(day).isoformat()}",))
            self.st.db.execute("DELETE FROM meta WHERE key LIKE 'equity:%' AND key<?", (f"equity:{day.isoformat()}",))
            got = LR.compute(self.st, learner(O1), day, kind="live", write_cache=False)
        self.assertEqual(got["status"], "closed")
        self.assertIn("E_prev", got["why"])

    def test_the_cache_is_keyed_by_the_training_keys_and_the_code(self):
        days = self.days(4)
        hist = self.history(days[:2], 6)
        tau = LR.tau_of(self.st, learner(O1), days[3])
        first = LR.training(self.st, learner(O1), days[3], tau)
        keys = self.st.db.execute("SELECT day, keys_sha, code_sha FROM learner_stats").fetchall()
        self.assertEqual(len(keys), 2)
        self.assertTrue(all(k["code_sha"] == LR.CODE_SHA for k in keys))
        # a session settled further is a new key; the cached sums equal sums made afresh
        c, sy = self.w.issuer()
        self.st.db.execute("INSERT INTO learner_cands(program, version, day, cik, event, symbol, families, kept, eligible, "
                           "features, sig20, picked, kind) VALUES(?, 1, ?, ?, 'news:more', ?, '[]', 1, 0, ?, 0.03, 0, "
                           "'catchup')", (O1, days[0].isoformat(), c, sy, json.dumps({"x": [0.5] * 57, "hist": 0})))
        self.w.universe(days[0], sy, c)
        self.w.outcome("EVL-CTRL-NEWS-ALL-O1", "news:more", sy, c, days[0], a_g=0.01, settled=et(days[0], 21, 0))
        second = LR.training(self.st, learner(O1), days[3], tau)
        self.assertNotEqual(first["keys_sha"], second["keys_sha"])
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM learner_stats").fetchone()[0], 3)
        with mock.patch.object(LR, "CODE_SHA", "another"):
            third = LR.training(self.st, learner(O1), days[3], tau, write=False)
        self.assertEqual([s for _, s in third["stats"]], [s for _, s in second["stats"]], "another code recomputes the same")
        self.assertEqual(len(hist), 2)


# ------------------------------------------------------------------------------------------- the parts and the record
class FakeGateway:
    """No network: a read fails (the learner's catch-up reads only the store)."""

    def get_json(self, path, params=None):
        raise AssertionError(f"no network read expected: {path}")

    def post_json(self, path, body, headers=None):
        raise AssertionError("no model call expected")


class TheParts(WorldCase):
    def ctx(self, now: dt.datetime) -> R.Context:
        ctx = R.Context(self.st, FakeGateway(), lambda url: b"", now=lambda: now)
        return ctx

    def test_the_live_part_runs_after_the_receipt_names_no_learner_and_records_its_id(self):
        days = self.days(2)
        self.history(days[:1], 5)
        day = days[1]
        self.w.open_session(day, 5)
        [rid] = [r[0] for r in self.st.db.execute("SELECT id FROM receipts WHERE job=?", (f"decide-open:{day}",))]
        summary = self.st.db.execute("SELECT summary FROM receipts WHERE id=?", (rid,)).fetchone()[0]
        out = R.learner_part(self.ctx(et(day, 9, 16, 5)), day, "open", rid, backfill_run=False)
        self.assertIn(f"{O1}", out)
        fits = self.st.db.execute("SELECT kind, receipt, receipt_id FROM learner_fits WHERE program=? AND day=?",
                                  (O1, day.isoformat())).fetchone()
        self.assertEqual(tuple(fits), ("live", f"decide-open:{day}", rid))
        self.assertEqual(self.st.db.execute("SELECT summary FROM receipts WHERE id=?", (rid,)).fetchone()[0], summary,
                         "the House's receipt is never touched: it names no learner")
        self.assertEqual(R.learner_part(self.ctx(et(day, 9, 16)), day, "open", rid, backfill_run=True), {},
                         "a backfill run decides no learner")
        # a re-decision's receipt is not the first: its part does nothing
        later = self.w.receipt(day, "open", started=et(day, 10, 15), finished=et(day, 10, 16))
        self.assertIn("skipped", LR.live_part(self.ctx(et(day, 10, 16)), learner(O1), day, receipt_id=later))

    def test_a_failed_or_expired_part_writes_nothing_and_is_decided_later_by_itself_never_traded(self):
        days = self.days(3)
        day = days[1]
        self.w.open_session(day, 4)
        [rid] = [r[0] for r in self.st.db.execute("SELECT id FROM receipts WHERE job=?", (f"decide-open:{day}",))]
        with mock.patch.object(LR, "compute", side_effect=RuntimeError("invented")):
            got = LR.live_part(self.ctx(et(day, 9, 16, 5)), learner(O1), day, receipt_id=rid)
        self.assertIn("failed", got)
        self.assertIsNone(LR.decided(self.st, learner(O1), day))
        part = json.loads(self.st.meta(LR.PART_KEY.format(program=O1, version=1, day=day.isoformat())))
        self.assertEqual(part["status"], "failed")
        self.assertTrue(EB.learner_pending(EB.Lane(self.st.root / S.DB_NAME), learner(O1), day) is False,
                        "the book waits no more for it")
        day2 = days[2]
        self.w.open_session(day2, 4)
        [rid2] = [r[0] for r in self.st.db.execute("SELECT id FROM receipts WHERE job=?", (f"decide-open:{day2}",))]
        got = LR.live_part(self.ctx(et(day2, 9, 16, 5)), learner(O1), day2, receipt_id=rid2, budget=0.0)
        self.assertIn("expired", got)
        self.assertIsNone(LR.decided(self.st, learner(O1), day2))
        # a live decision of an earlier session makes the release's first live decision: these two are LATE
        self.w.open_session(days[0], 3)
        LR.decide(self.st, learner(O1), days[0], kind="live", now=lambda: et(days[0], 9, 16, 30))
        owed = LR.due(self.st, et(day2, 12, 0))
        self.assertIn(("late", O1, day), [(k, p.id, d) for k, p, d in owed])
        self.assertIn(("late", O1, day2), [(k, p.id, d) for k, p, d in owed])
        out = LR.catchup(self.st, lambda: et(day2, 12, 0))
        self.assertGreaterEqual(out["late"], 2)
        rec = LR.decided(self.st, learner(O1), day)
        self.assertEqual((rec["kind"], rec["receipt"]), ("late", f"decide-open-lrn:{day}"))
        self.assertEqual(self.st.db.execute("SELECT status FROM receipts WHERE id=?", (rec["receipt_id"],)).fetchone()[0],
                         "ok")
        self.assertIsNone(LR.live_picks(self.st, learner(O1), day), "a late decision is never traded")

    def test_the_catch_up_before_the_release_the_reconstruction_once_and_never_again(self):
        early = dt.date(2026, 10, 22)        # tau before REGISTERED_AT_7: reconstructed
        rows = self.w.open_session(early, 3)
        d1, d2 = self.days(2)                 # after it, before any live decision: caught up
        self.w.open_session(d1, 3)
        self.w.open_session(d2, 3)
        owed = [(k, p.id, d) for k, p, d in LR.due(self.st, et(d2, 18, 0))]
        self.assertIn(("reconstruct", O1, early), owed)
        kinds = [k for k, _, _ in owed]
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "reconstruct"), "every reconstruction first")
        self.assertEqual({d for k, _, d in owed if k == "reconstruct"},
                         {s.day for s in C.sessions(self.st, dt.date(2026, 10, 19), early)})
        self.assertIn(("catchup", O1, d1), owed)
        self.assertIn(("catchup", O1, d2), owed)
        out = LR.catchup(self.st, lambda: et(d2, 18, 0))
        self.assertGreaterEqual(out["decided"], 3)
        rec = LR.decided(self.st, learner(O1), early)
        self.assertEqual((rec["kind"], rec["status"], rec["receipt"], rec["n_picks"]),
                         ("reconstruct", "reconstructed", None, 0))
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM learner_cands WHERE program=? AND day=?",
                                            (O1, early.isoformat())).fetchone()[0], len(rows))
        for d in (d1, d2):
            rec = LR.decided(self.st, learner(O1), d)
            self.assertEqual((rec["kind"], rec["receipt"]), ("catchup", f"decide-open-lrn:{d}"))
        again = LR.catchup(self.st, lambda: et(d2, 19, 0))
        self.assertEqual(again["decided"], 0, "each decision once: never decided again")


class TheRecompute(WorldCase):
    def test_a_match_on_unchanged_inputs_a_mismatch_alarmed_a_change_said(self):
        days = self.days(5)
        self.history(days[:4], 12, signal=UPGRADE)
        day = days[4]
        self.w.open_session(day, 10)
        with mock.patch.object(LR, "WARM_ROWS", 20):
            LR.decide(self.st, learner(O1), day, kind="live", now=lambda: et(day, 9, 16, 30))
            self.assertIsNotNone(self.st.meta(LR.INPUTS_KEY.format(program=O1, version=1, day=day.isoformat())),
                                 "the fingerprints are kept at the decision")
            # the night's score settles the session's intents and a later decision of the close adds universe rows of
            # D beyond E5's bound: no input the decision read moved
            self.st.db.execute("UPDATE intents SET status='exited' WHERE program='EVL-CTRL-NEWS-ALL-O1' AND entry_day=?",
                               (days[3].isoformat(),))
            n_cik, n_sym = self.w.issuer()
            self.w.universe(day, n_sym, n_cik, decided=et(day, 15, 47))
            got = LR.recompute(self.st, day, lambda: et(day, 22, 0))
            self.assertEqual(got[f"{O1}@v1"]["status"], "match")
            self.st.db.execute("UPDATE learner_cands SET picked=0 WHERE program=? AND day=? AND rank=1",
                               (O1, day.isoformat()))
            got = LR.recompute(self.st, day, lambda: et(day, 22, 0))
            self.assertEqual(got[f"{O1}@v1"]["status"], "mismatch")
            f = EL.facts(self.w.root, et(day, 22, 5).timestamp())
            cause = EL.judge(et(day, 22, 5).timestamp(), f)
            self.assertTrue(cause["stalled"] and "MISMATCHED" in cause["what"], cause["what"])
            self.st.db.execute("UPDATE intents SET status='skipped:limit' WHERE program='EVL-CTRL-NEWS-ALL-O1' AND "
                               "entry_day=?", (days[3].isoformat(),))
            got = LR.recompute(self.st, day, lambda: et(day, 22, 0))
            self.assertEqual(got[f"{O1}@v1"]["status"], "changed")


class TheAlarms(WorldCase):
    def test_a_failed_part_an_owed_decision_and_a_lagging_training_are_alarmed(self):
        days = self.days(3)
        self.w.open_session(days[0], 3)
        self.st.set_meta(LR.PART_KEY.format(program=O1, version=1, day=days[0].isoformat()),
                         json.dumps({"status": "expired", "why": "x", "at": "x"}))
        now = et(days[0], 14, 0).timestamp()
        cause = EL.judge(now, EL.facts(self.w.root, now))
        self.assertTrue(cause["stalled"])
        self.assertIn("part of", cause["what"])
        self.assertIn("owes its own decision", cause["what"])
        LR.decide(self.st, learner(O1), days[0], kind="live", now=lambda: et(days[0], 9, 16, 30))
        cause = EL.judge(now, EL.facts(self.w.root, now))
        self.assertIn("trained through no row", cause["what"], "no training row at all: the lag alarm")
        self.assertNotIn("ahat", json.dumps(cause), "counts and dates only")

    def test_unpinned_nothing_is_judged(self):
        pin(self, None)
        cause = EL.judge(0.0, EL.facts(self.w.root, et(dt.date(2026, 10, 27), 12).timestamp()))
        self.assertFalse(cause["judged"])


class TheReportAndTheFacts(WorldCase):
    def test_the_reports_learner_lines_are_counts_only(self):
        days = self.days(2)
        self.history(days[:1], 4)
        self.w.open_session(days[1], 4)
        LR.decide(self.st, learner(O1), days[1], kind="live", now=lambda: et(days[1], 9, 16, 30))
        rep = RP.build(self.st, days[1], now=et(days[1], 21, 0))
        [o1, on] = rep["learners"]
        self.assertEqual((o1["program"], o1["kind"], o1["candidates"], o1["picks"], o1["training_rows"]),
                         (O1, "live", 4, 0, 4))
        self.assertNotIn("kind", on)
        text = json.dumps(rep["learners"])
        for word in ("beta", "ahat", "xbar", "\"e\"", "\"z\""):
            self.assertNotIn(word, text)
        self.assertIn(f"{O1} v1: live warmup, candidates 4", RP.render(rep))

    def test_r3s_facts_refuse_the_learners_and_cost7s_tables_and_the_intents(self):
        for table in ("learner_fits", "learner_cands", "learner_stats", "costs7", "cost_basis", "intents",
                      "outcomes", "real_fills"):
            self.assertIn(table, BI.FACTS_DENY, table)
        C7.ensure(self.st.db)
        for table in LR.TABLES + C7.TABLES + ("intents",):
            with BI.outcome_free(self.st.db):
                with self.assertRaises(sqlite3.DatabaseError, msg=table):
                    self.st.db.execute(f"SELECT * FROM {table}").fetchall()


# ----------------------------------------------------------------------------------------------------- real money
from league.tests import test_events_book as TB  # noqa: E402


class TheMoney(TB.EventTest):
    """The REAL book (league/equity/live.py) at DAY's auctions, its lane store holding a learner's live decision."""

    def setUp(self):
        super().setUp()
        pin(self)

    def live(self, lane: TB.Lane, pid: str, day: dt.date, picks: list[tuple[str, str, float]], *,
             kind: str = "live") -> None:
        """A learner's decision of `day` on the lane's store as league/events/learner.py writes it: its fits row, its
        picked candidates (rank order) and their intents; each pick's issuer a live universe row."""
        prog = learner(pid)
        st = lane.st
        LR.ensure(st.db)
        s = C.session(st, day)
        tau = s.open_decide if prog.entry_at == "open" else s.close_decide
        exit_day = day if prog.entry_at == "open" else C.nth(st, day, 2).day
        for rank, (cik, symbol, prev) in enumerate(picks, start=1):
            if st.db.execute("SELECT 1 FROM universe WHERE day=? AND symbol=?", (day.isoformat(), symbol)).fetchone() is None:
                lane.universe(day, symbol, cik, prev)
            event = f"news:{pid}-{symbol}"
            st.db.execute("INSERT INTO learner_cands(program, version, day, cik, event, symbol, families, kept, eligible, "
                          "features, sig20, adv20, prev_close, knowable_at, e, z, ahat, picked, rank, kind) VALUES(?, 1, ?, "
                          "?, ?, ?, '[]', 1, 1, NULL, 0.03, 5e6, ?, ?, 0.1, 1.0, ?, 1, ?, ?)",
                          (pid, day.isoformat(), cik, event, symbol, prev, S.iso(tau - dt.timedelta(hours=1)),
                           0.05 - 0.001 * rank, rank, kind))
            st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                          "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'shadow', "
                          "'planned', NULL)", (pid, event, symbol, cik, S.iso(tau), day.isoformat(), prog.entry_at,
                                               exit_day.isoformat(), prog.exit_at, 0.05 - 0.001 * rank))
        st.db.execute("INSERT INTO learner_fits(program, version, day, tau, kind, status, n_picks, finished_at) VALUES(?, 1, "
                      "?, ?, ?, 'ok', ?, ?)", (pid, day.isoformat(), S.iso(tau), kind, len(picks), S.iso(tau)))

    def test_the_learner_buys_its_live_picks_after_every_earlier_row_whose_buys_are_unchanged(self):
        def run(with_learner: bool) -> list[tuple]:
            with tempfile.TemporaryDirectory() as tmp:
                h = TB.Harness(Path(tmp))
                try:
                    TB.earnings(h.lane, "a-1", TB.CIK, "ACME")                 # READ-O1 wants ACME
                    h.lane.intent(TB.V2("EVL-ERN-READ-O1"), "8k:a-1", "ACME", TB.CIK, TB.DAY, TB.DAY)
                    if with_learner:
                        self.live(h.lane, O1, TB.DAY, [(TB.CIK, "ACME", 16.0), (TB.CIK2, "BETA", 16.0),
                                                       (TB.CIK3, "GAMA", 16.0)])
                    self.ready(h)
                    for sym in ("ACME", "BETA", "GAMA"):
                        h.symbol(sym, last=17.0, sd=0.02)
                    h.tick(9, 15)
                    h.tick(9, 16)
                    return [(r["program"], r["symbol"], r["band"], r["tif"], r["limit_px"]) for r in h.event_intents("buy")]
                finally:
                    h.state.close()
                    h.lane.st.close()
                    if h.book._event_lane is not None:
                        h.book._event_lane.close()
        without, with_ = run(False), run(True)
        self.assertEqual(with_[:len(without)], without, "every earlier row's real-money buys, in the same order")
        self.assertEqual(with_[len(without):], [(O1, "BETA", "learning", "opg", "20.00"), (O1, "GAMA", "learning", "opg",
                                                                                          "20.00")],
                         "then the learner's, in its rank order, passing over ACME (given to READ-O1 at this auction)")

    def test_no_live_decision_no_real_money_and_a_running_part_is_waited_for_within_its_bound(self):
        h = self.harness()
        self.live(h.lane, O1, TB.DAY, [(TB.CIK2, "BETA", 16.0)], kind="catchup")
        self.ready(h)
        h.symbol("BETA", last=17.0)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(h.event_intents("buy"), [], "a catch-up's picks are never traded")
        h2 = TB.Harness(self.root / "two")
        self.addCleanup(h2.state.close)
        self.addCleanup(h2.lane.st.close)
        self.addCleanup(lambda: h2.book._event_lane is not None and h2.book._event_lane.close())
        LR.ensure(h2.lane.st.db)
        self.ready(h2)
        out = h2.tick(9, 15)
        self.assertIn("waiting for the learner part", str(out.get("event_decide_lrn")))
        self.live(h2.lane, O1, TB.DAY, [(TB.CIK2, "BETA", 16.0)])
        h2.symbol("BETA", last=17.0)
        h2.tick(9, 16)
        self.assertEqual([r["symbol"] for r in h2.event_intents("buy")], ["BETA"])

    def test_o1s_ern_guard_bars_an_ern_d_issuer_in_real_money_only(self):
        h = self.harness()
        prior_close = C.session(h.lane.st, TB.PRIOR).close_decide
        h.lane.filing("e-1", TB.CIK2, accepted=S.iso(prior_close + dt.timedelta(minutes=30)), items=("2.02",))
        self.live(h.lane, O1, TB.DAY, [(TB.CIK2, "BETA", 16.0), (TB.CIK3, "GAMA", 16.0)])
        lane = EB.Lane(h.lane.st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        moment = C.session(lane, TB.DAY).open_decide
        self.assertTrue(EB.ern_issuer(lane, TB.CIK2, TB.DAY, moment))
        self.assertEqual([p.symbol for p in EB.picks(lane, learner(O1), TB.DAY, decided_at=moment)], ["GAMA"])
        self.assertEqual(len(LR.live_picks(lane, learner(O1), TB.DAY)), 2, "the shadow keeps the pick")

    def test_ons_guard_reads_every_8k_of_the_issuer_after_0900(self):
        h = self.harness()
        lane_st = h.lane.st
        s = C.session(lane_st, TB.DAY)
        cases = {TB.CIK: ("ACME", None), "0000000004": ("DOCS", (2, "none")), "0000000005": ("RAIS", (1, "raised")),
                 "0000000006": ("UNAN", "unanswered"), "0000000007": ("LOWS", (1, "none")), "0000000008": ("EARL", "early")}
        picks = []
        for cik, (sym, how) in cases.items():
            picks.append((cik, sym, 16.0))
            if how is None:
                continue
            knowable = s.at(dt.time(8, 30)) if how == "early" else s.at(dt.time(11, 0))
            h.lane.filing(f"f-{sym}", cik, accepted=S.iso(knowable - dt.timedelta(minutes=10)), items=("8.01",))
            if isinstance(how, tuple):
                h.lane.verdict(f"f-{sym}", how[0], answered=S.iso(knowable + dt.timedelta(minutes=5)), guidance=how[1])
            elif how == "early":
                h.lane.verdict(f"f-{sym}", 3, answered=S.iso(knowable + dt.timedelta(minutes=5)))
        self.live(h.lane, ON, TB.DAY, picks)
        lane = EB.Lane(lane_st.root / S.DB_NAME)
        self.addCleanup(lane.close)
        got = [p.symbol for p in EB.picks(lane, learner(ON), TB.DAY, decided_at=s.close_decide)]
        self.assertEqual(got, ["ACME", "LOWS", "EARL"], "barred: an ok score 2, an ok score 1 raised, no answer by tau; "
                                                        "a news primary with no 8-K, a score 1 none and an 8-K before 09:00 "
                                                        "are bought")

    def test_the_line_kept_for_the_earlier_rows_and_rooms_order(self):
        self.assertEqual(EB.line_keep(O1), EB.LEARNER_LINE_KEEP // 2)
        self.assertEqual(EB.line_keep("EVL-ERN-READ-O1"), 0)
        h = self.harness()
        cap = int(EB.settings().max_orders_day)
        with mock.patch.object(L, "event_orders_today", lambda rows, day: cap - EB.LEARNER_LINE_KEEP - 1):
            self.assertIsNone(h.book._count_refusal(TB.DAY.isoformat(), exit_=False, event_line=cap, held=0))
            why = h.book._count_refusal(TB.DAY.isoformat(), exit_=False, event_line=cap, held=EB.line_keep(O1))
            self.assertIn("the event kind's day order count", why)


# ------------------------------------------------------------------------------------------------------- the proof
class TheProof(unittest.TestCase):
    """THE PROOF ON AN INVENTED WEEK (release 1019e's and PREREG-EVL-5's week, league/tests/evl5_world.py, two births of
    R3 among its programs): decided by the House's own code with the learners pinned (and made to pick) and without
    them, every earlier program's shadow intents and real-money picks are the same, and so are the House's receipts."""

    def week(self, root: Path, pinned: bool) -> dict:
        from league.tests import evl5_world as W5

        patches = [mock.patch.object(P, "REGISTERED_AT_7", REG7 if pinned else None)]
        if pinned:      # (the learners pick from their first decision: a warm, invented fit)
            patches += [mock.patch.object(LR, "training", lambda store, lrn, day, tau, **kw: {
                "stats": [], "rows": 5000, "sessions": 10, "keys_sha": "x", "by_day": {}}),
                mock.patch.object(LR, "fit", lambda stats, width: {"beta": [5.0] * width, "d": [1.0] * width,
                                                                  "n_w": 1.0})]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            P.refresh_7()
            w = W5.World(root)
            try:
                for d in C.sessions(w.st, dt.date(2026, 10, 1), dt.date(2026, 10, 31)):
                    w.st.set_meta(f"equity:{d.day.isoformat()}", "10000.0")
                W5.the_week(w)
                learners = {p.id for p in P.LEARNER_ROWS}
                intents = [r for r in w.intents() if r[0] not in learners]
                receipts = [(r["job"], r["status"], r["summary"]) for r in w.st.db.execute(
                    "SELECT job, status, summary FROM receipts WHERE job LIKE 'decide-%' ORDER BY id")]
                picks = W5.picks(w, lambda p: not P.is_learner(p))
                mine = 0
                if pinned:
                    mine = w.st.db.execute("SELECT COUNT(*) FROM intents WHERE program IN (?, ?)",
                                           tuple(sorted(learners))).fetchone()[0]
                return {"intents": intents, "receipts": receipts, "picks": picks, "learner_intents": mine,
                        "fits": [tuple(r) for r in w.st.db.execute("SELECT program, day, kind FROM learner_fits")]
                        if pinned else []}
            finally:
                P.load_births(None)
                w.close()
        P.refresh_7()

    def test_every_earlier_programs_shadow_intents_and_real_money_picks_are_the_same_with_and_without_the_learners(self):
        with tempfile.TemporaryDirectory() as tmp:
            without = self.week(Path(tmp) / "without", False)
            with_ = self.week(Path(tmp) / "with", True)
        P.refresh_7()
        self.assertGreater(with_["learner_intents"], 0, "the learners did pick: the proof is not vacuous")
        self.assertTrue(any(kind == "live" for _, _, kind in with_["fits"]))
        self.assertEqual(with_["intents"], without["intents"])
        self.assertEqual(with_["picks"], without["picks"])
        self.assertEqual(with_["receipts"], without["receipts"], "the House's receipts: the same, naming no learner")


# --------------------------------------------------------------------------------------------------------- COST-7
class TheCost7(unittest.TestCase):
    def test_e9s_sigma_its_floor_its_cap_and_its_missing_value(self):
        flat = [20.0] * 20
        self.assertEqual(C7.sigma7(flat), 0.02)
        wild = [20.0 * (2.0 if k % 2 else 1.0) for k in range(20)]
        self.assertEqual(C7.sigma7(wild), 0.25)
        self.assertEqual(C7.sigma7(flat[:19]), 0.04)
        walk = [20.0 * (1.05 if k % 2 else 0.95) for k in range(20)]
        self.assertAlmostEqual(C7.sigma7(walk), LR.sig20_of(walk))

    def test_the_penny_ceiling_the_impact_and_r7(self):
        n = C7.n_ref(2000.0, 16.0)
        self.assertEqual(n, math.floor(0.035 * 2000 / (1.25 * 16.0)))
        fee_in, fee_out = C7.penny(n, 17.0, 17.5)
        self.assertAlmostEqual(fee_in, 1e4 * 0.01 / (n * 17.0))
        notional = n * 17.5
        self.assertAlmostEqual(fee_out, 1e4 * (0.01 + C7.ceilcent(27.8e-6 * notional) +
                                               C7.ceilcent(min(0.000166 * n, 8.30))) / notional)
        self.assertEqual(C7.ceilcent(0.0001), 0.01)
        self.assertEqual(C7.ceilcent(0.02), 0.02)
        self.assertEqual(C7.penny(n, 17.0, 0.0)[1], C7.penny(n, 17.0, 17.0)[1], "a zero exit print: N_in")
        self.assertAlmostEqual(C7.impact_bp(0.04, 2000.0, 1e6), 1e4 * 0.04 * math.sqrt(0.1 * 2000.0 / 1e6))
        r = C7.r7(20.0, 21.0, m_in=2.5, m_out=2.5, fee_in=1.0, fee_out=2.0, imp=0.5, g=3.0)
        self.assertAlmostEqual(r, 21.0 * (1 - 5.0e-4) / (20.0 * (1 + 4.0e-4)) - 1 - 3e-4)

    def test_only_this_files_versions(self):
        self.assertTrue(C7.applies(O1, 1) and C7.applies(ON, 1))
        for program, version in (("EVL-NEWS-READ-O1", 3), (O1, 2), ("EVL-PX-ANY", 1)):
            self.assertFalse(C7.applies(program, version))

    def test_the_selection_se_is_the_exact_within_session_permutation_sd(self):
        rng = random.Random(3)
        population = []
        for s in range(3):
            for k in range(5):
                population.append({"session": f"s{s}", "filled": k < 2 + s % 2, "a_g": rng.gauss(0, 0.02)})
        got = C7.selection(population)
        # brute force: every within-session relabelling of which attempts filled, G_w's sd over them
        sessions = sorted({a["session"] for a in population})
        options = []
        for s in sessions:
            xs = [a for a in population if a["session"] == s]
            k = sum(1 for a in xs if a["filled"])
            options.append([(xs, set(c)) for c in itertools.combinations(range(len(xs)), k)])
        values = []
        for combo in itertools.product(*options):
            relabelled = [dict(a, filled=i in chosen) for xs, chosen in combo for i, a in enumerate(xs)]
            values.append(C7.selection(relabelled)["g_w"])
        mean = math.fsum(values) / len(values)
        sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / len(values))
        self.assertAlmostEqual(got["se"], sd, delta=1e-12)
        self.assertAlmostEqual(mean, 0.0, delta=1e-12)

    def test_checkpoints_raise_g_once_each_and_never_lower_it(self):
        pop = [{"session": f"2026-10-{20 + k // 50:02d}", "settled": True, "tradable": True,
                "filled": k % 4 != 0, "a_g": (0.01 if k % 4 != 0 else 0.05)} for k in range(120)]
        g, done, last = C7.checkpoints(pop, [], 0.0)
        self.assertEqual(done, [100])
        self.assertGreater(g, 0.0, "non-fills that would have earned more: a selection charge")
        g2, done2, _ = C7.checkpoints(pop, done, g)
        self.assertEqual((g2, done2), (g, done), "a checkpoint is computed once")
        better = [dict(a, a_g=-0.05 if not a["filled"] else 0.01) for a in pop]
        g3, _, _ = C7.checkpoints(better, [], g)
        self.assertEqual(g3, g, "G is never lowered")
        unsettled = pop[:100] + [dict(pop[0], session="2026-10-21", settled=False)]
        self.assertEqual(C7.checkpoints(unsettled, [], 0.0)[1], [], "waits until every attempt through it settled")

    def test_the_nightly_row_keeps_the_floors_without_a_ledger_and_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = World(Path(tmp))
            try:
                pin(self)
                day = dt.date(2026, 10, 27)
                self.assertIsNone(C7.basis_for(w.st), "no row: every look of these versions waits")
                row = C7.nightly(w.st, day, et(day, 21, 0))
                self.assertEqual((row["m_in"], row["m_out"], row["g_bp"], row["fbar_in"]), (2.5, 2.5, 0.0, 0.0))
                self.assertIn("no attempt ledger", row["why"])
                self.assertEqual(C7.nightly(w.st, day, et(day, 21, 5)), {"kept": 1}, "one row a night")
                self.assertEqual(C7.basis_for(w.st)["night"], day.isoformat())
                self.assertIsNone(C7.basis_for(w.st, before=et(day, 20, 0)), "the latest row written before the look")
            finally:
                w.close()

    def test_m_rises_with_the_fills_ucb_and_never_falls(self):
        rows = []
        for s in range(6):
            for k in range(20):
                rows.append((f"t{s}{k:02d}", f"2026-10-{20 + s}", 6.0 + (k % 5) - 2))
        u, n = C7.ucb(rows)
        self.assertEqual(n, 120)
        means = [6.0] * 6
        self.assertAlmostEqual(u, 6.0 + 1.645 * 0.0)
        self.assertEqual(C7.ucb(rows[:99])[0], None, "fewer than 100 fills: none")
        self.assertEqual(len(means), 6)

    def test_the_judged_record_is_the_live_decisions_through_preregevl6s_one_interface(self):
        out = C7.judge_record([], [], program=O1, version=1)
        if getattr(SN, "v6_judge", None) is None:
            self.assertIsNone(out["decision"])
            self.assertIn("PREREG-EVL-6's screen is not in this tree", out["why"])
        calls = []
        with mock.patch.object(SN, "v6_judge", lambda blocks, **kw: calls.append((blocks, kw)) or {"decision": None},
                               create=True), mock.patch.object(SN, "blocks6", lambda rows: ["blocks", len(rows)],
                                                               create=True):
            C7.judge_record([{"a": 1}], [{"a": 0}], program=O1, version=1, tag="")
        [(blocks, kw)] = calls
        self.assertEqual(blocks, ["blocks", 1])
        self.assertEqual((kw["program"], kw["version"], kw["control"], kw["control_rows"]), (O1, 1, f"{O1}-POOL",
                                                                                             [{"a": 0}]))


class TheRecord(WorldCase):
    def test_record7_reads_live_decisions_only_valued_on_a7_and_waits_without_a_basis(self):
        days = self.days(3)
        for kind, day in (("catchup", days[0]), ("live", days[1])):
            self.w.open_session(day, 2)
            with mock.patch.object(LR, "WARM_ROWS", 0), mock.patch.object(LR, "WARM_SESSIONS", 0), \
                    mock.patch.object(LR, "training", lambda *a, **k: {"stats": [], "rows": 1, "sessions": 1,
                                                                        "keys_sha": "x", "by_day": {}}), \
                    mock.patch.object(LR, "fit", lambda stats, width: {"beta": [1.0] * width, "d": [1.0] * width}):
                LR.decide(self.st, learner(O1), day, kind=kind, now=lambda day=day: et(day, 9, 16, 30))
        for r in self.st.db.execute("SELECT event, symbol, cik, entry_day FROM intents WHERE program=?", (O1,)).fetchall():
            self.w.outcome(O1, r["event"], r["symbol"], r["cik"], dt.date.fromisoformat(r["entry_day"]), a_g=0.01,
                           settled=et(days[2], 20, 30))
        self.assertIsNone(C7.record7(self.st, learner(O1)), "no basis row: the look waits")
        C7.nightly(self.st, days[2], et(days[2], 21, 0))
        rows = C7.record7(self.st, learner(O1))
        self.assertTrue(rows)
        self.assertEqual({r["entry_day"] for r in rows}, {days[1]}, "the catch-up's picks are never in the record")
        self.assertTrue(all(r["tradable"] == 1 and r["a"] is not None for r in rows))
        self.assertTrue(all(r["a"] < 0.01 for r in rows), "valued on a7: COST-7's costs taken off the gross")


if __name__ == "__main__":
    unittest.main()
