"""R3: BIRTHS, THE SWARM'S GENERATOR (goal-2026-10-19/R3-SPEC.md; league/events/births.py), on synthetic data only.

Held here: the GRAMMAR (its fields and only those, every family the lane reads, verdict thresholds on stored scores
only) and the canonical sha; the VALIDATOR's refusals (rate, duplicate, id, budget, three a night) and its budget
arithmetic (A81: 0.10 a seatable birth, the lane's stated 3.0 over every seatable version, counted from SEATING's own
sum with PREREG-EVL-1 to -4's 1.2 included, at most 3 a night, records free); the FACTS
never reading bars, marks, outcomes, looks, bands (nor band_history, real_fills, the universe or meta); the PROPOSER
through a fake gateway (one Haiku call at temperature 0, its prompt sha and answer stored, never asked twice, the
night's $0.25 cap); REGISTRATION through a fake docs route (the later of GitHub's commit time and the House's receipt;
an answer that never came posted again); the LOADER (births after every PREREG program, counted by the screen's
expected false passes); EVERY PREREG PROGRAM'S INTENTS IDENTICAL WITH AND WITHOUT BIRTHS while the births take their own
events after their own registration; the screen judging a seatable birth (and never a record or a control); the
House's event book trading a seated birth at learning size, after every PREREG program in ROOM's order; and the House's
lane running the births job after the night's report."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from typing import Any
from unittest import mock

from league.events import births as BI
from league.events import calendar as C
from league.events import programs as P
from league.events import run as R
from league.events import screen as SN
from league.events import store as S
from league.events import verdicts as V
from league.tests import test_events_house as TH

UTC = dt.timezone.utc
NY = C.NY
ISSUERS = {f"{i:010d}": chr(64 + i) * 3 for i in range(1, 27)}     # AAA .. ZZZ
CIK = {sym: cik for cik, sym in ISSUERS.items()}
TEXT = ("The company announced results and a change in its management today, with guidance for the year. " * 4).encode()


def et(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=NY).astimezone(UTC)


def spec(ident: str, family: str, rule: dict, *, rank: str = "none", seatable: bool = True, hold: int = 1,
         exit_: str | None = None) -> dict:
    entry = BI.ENTRY[family]
    return {"id": ident, "version": 1, "family": family, "rule": rule, "entry": entry,
            "exit": exit_ or "close", "hold": hold, "rank": rank, "seatable": seatable}


def unload() -> None:
    P.load_births(None)


class Synth:
    """A lane store of invented events: the calendar (weekdays), a ticker snapshot, eligibility results kept as the
    lane's decisions keep them, 8-K and Form 4 filings with their documents, news, and stored verdicts."""

    def __init__(self, root: Path):
        self.st = S.Store(root)
        C.refresh(self.st, TH.FakeGateway(), dt.date(2026, 8, 3), dt.date(2026, 12, 31))
        tickers = {str(i): {"cik_str": int(cik), "ticker": sym, "title": f"{sym} Inc."}
                   for i, (cik, sym) in enumerate(ISSUERS.items())}
        self.st.set_meta("tickers@2026-10-01T11:00:05Z", self.st.put_document(json.dumps(tickers).encode(),
                                                                             "company_tickers"))
        self.text_sha = self.st.put_document(TEXT, "ex99")
        self.n = 0

    def eligible(self, day: dt.date, sym: str, ok: bool = True) -> None:
        self.st.db.execute("INSERT OR REPLACE INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, "
                           "sigma60) VALUES(?, ?, ?, ?, 'NASDAQ', 20.0, 5e6, 'IWM', 0.02)",
                           (day.isoformat(), sym, CIK[sym], f"{sym} Inc."))
        self.st.db.execute("INSERT OR REPLACE INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, "
                           "'live', ?, ?, 'x')", (day.isoformat(), CIK[sym], int(ok), sym if ok else None))

    def bar(self, day: dt.date, sym: str, close: float = 20.0) -> None:
        """A raw SIP daily bar (the reaction's base: the last close before the event)."""
        self.st.db.execute("INSERT OR REPLACE INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', ?, ?, "
                           "?, ?, 1e6, 'x')", (sym, day.isoformat(), close, close, close, close))

    def filing(self, sym: str, accepted: dt.datetime, items=("2.02",), *, form: str = "8-K") -> str:
        self.n += 1
        acc = f"00{self.n:08d}-26-{self.n:06d}"
        knowable = accepted + dt.timedelta(minutes=10)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, text_sha, text_len, status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'current', ?, ?, "
                           "'fetched')", (acc, form, CIK[sym], f"{sym} Inc.", json.dumps(list(items)), S.iso(accepted),
                                          S.iso(knowable), S.iso(accepted + dt.timedelta(minutes=2)),
                                          self.text_sha if form == "8-K" else None, len(TEXT) if form == "8-K" else None))
        return acc

    def doc_verdict(self, acc: str, score: int, guidance: str = "none") -> None:
        self._verdict(f"8k:{acc}", V.PROMPTS["doc"], score, guidance)

    def news_verdict(self, ident: str, score: int) -> None:
        self._verdict(f"news:{ident}", V.PROMPTS["news"], score, None)

    def _verdict(self, event: str, prompt: V.Prompt, score: int, guidance: str | None) -> None:
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, "
                           "score, guidance, answer, usd) VALUES(?, ?, ?, 'r', '2026-10-01T00:00:00Z', "
                           "'2026-10-01T00:00:01Z', 'ok', ?, ?, '{}', 0.001)", (event, prompt.sha, V.MODEL, score, guidance))

    def article(self, sym: str, created: dt.datetime, source: str = "benzinga") -> str:
        self.n += 1
        ident = f"n{self.n}"
        self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                           "summary, symbols, live) VALUES(?, ?, NULL, ?, ?, ?, 'h', 's', ?, 1)",
                           (ident, S.iso(created), S.iso(created + dt.timedelta(minutes=1)),
                            S.iso(created + dt.timedelta(minutes=2)), source, json.dumps([sym])))
        return ident

    def insider(self, sym: str, accepted: dt.datetime, usd: float, *, director: bool = True, officer: bool = False) -> str:
        acc = self.filing(sym, accepted, (), form="4")
        self.st.db.execute("INSERT INTO form4_owners(accession, owner_cik, owner_name, is_director, is_officer, "
                           "officer_title, is_ten_pct) VALUES(?, '99', 'Owner', ?, ?, NULL, 0)",
                           (acc, int(director), int(officer)))
        self.st.db.execute("INSERT INTO form4_tx(accession, seq, security, tx_date, code, shares, price, acquired, "
                           "owned_after) VALUES(?, 1, 'Common', ?, 'P', ?, 10.0, 'A', 1)",
                           (acc, accepted.astimezone(NY).date().isoformat(), usd / 10.0))
        return acc

    def register(self, sp: dict, at: str, *, night: str = "2026-11-02", seq: int = 0, why: str = "invented") -> None:
        """A registered birth as `births.register` writes it from the gateway's receipt."""
        text = BI.canonical(sp)
        line = json.dumps({"spec": json.loads(text), "sha": BI.sha(sp)}, sort_keys=True, separators=(",", ":"))
        self.st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, "
                           "path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                           "'captain', ?)", (sp["id"], BI.sha(sp), text, int(sp["seatable"]), at, at, at,
                                             f"docs/births/{night}.jsonl", "c" * 40, seq, line, why, night))


def sessions_between(st: S.Store, first: dt.date, last: dt.date) -> list[dt.date]:
    return [s.day for s in C.sessions(st, first, last)]


#: A clean record pass's summary (league/events/house.py `_record_steps`' blocks; league/ops/evl_health.py `_failing`).
CLEAN_PASS = {"8-K": {"new": 1, "fetched": 1, "failed": 0, "unlisted": 0}, "4": {"new": 0, "fetched": 0, "failed": 0},
              "news": {"new": 2}}


def record_passes(st: S.Store, first: dt.datetime, last: dt.datetime, *, every: dt.timedelta = dt.timedelta(minutes=10),
                  outages: tuple[tuple[dt.datetime, dt.datetime], ...] = (), summary: dict | None = None,
                  status: str = "ok") -> int:
    """The House's record passes as their receipts tell them (league/events/house.py `_record`): one every `every` from
    `first` to `last`, none inside an outage [start, end); each finished `status` with `summary` (a clean one by
    default). Returns how many."""
    at, n = first, 0
    while at <= last:
        if not any(a <= at < b for a, b in outages):
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, ?, ?)",
                          (S.iso(at - dt.timedelta(seconds=20)), S.iso(at), status, json.dumps(summary or CLEAN_PASS)))
            n += 1
        at += every
    return n


# ======================================================================================================== the grammar
class TheGrammar(unittest.TestCase):
    def test_every_family_the_lane_reads_parses_with_its_own_fields(self):
        good = [spec("EVL-B-ERN-TOP", "ern", {"score_min": 3, "guidance": ["raised"]}, rank="score"),
                spec("EVL-B-ERNREACT-DIP", "ern-react", {"react_max": 0.97, "score_min": 1}, rank="reaction",
                     exit_="open"),
                spec("EVL-B-8K-502", "8k", {"items": ["5.02", "1.02"]}),
                spec("EVL-B-8K-READ", "8k", {"items": ["8.01"], "score_min": 2}, rank="score"),
                spec("EVL-B-INS-BIG", "ins", {"value_min": 200000}, rank="value", seatable=False),   # A89: a record
                spec("EVL-B-INS-DIR", "ins-buy", {"value_min": 100000, "roles": "director"}, rank="value"),
                spec("EVL-B-NEWS-BZ", "news", {"sources": ["Benzinga"], "hours": [7, 8], "score_min": 2}, rank="score"),
                spec("EVL-B-NEWSDAY", "news-day", {"score_max": -2}, exit_="open"),
                spec("EVL-B-NEWSREACT", "news-react", {"react_min": 1.05, "sources": ["benzinga"]}, rank="reaction",
                     exit_="close"),
                spec("EVL-B-ERN-O3", "ern", {}, hold=3, seatable=False)]
        for sp in good:
            parsed = BI.parse(sp)
            self.assertEqual(set(parsed), set(BI.FIELDS), sp["id"])
        self.assertEqual(BI.parse(good[2])["rule"]["items"], ["1.02", "5.02"], "lists are sorted")
        self.assertEqual(BI.parse(good[6])["rule"]["sources"], ["benzinga"], "sources lower-cased")
        self.assertTrue(BI.reads(BI.parse(good[0])) and BI.reads(BI.parse(good[3])))
        self.assertFalse(BI.reads(BI.parse(good[2])) or BI.reads(BI.parse(good[4])))

    def test_anything_outside_the_grammar_is_refused_with_its_reasons(self):
        base = spec("EVL-B-8K-502", "8k", {"items": ["5.02"]})
        cases = {
            "fields outside the grammar": base | {"code": "import os"},
            "missing fields": {k: v for k, v in base.items() if k != "rank"},
            "rule fields outside": base | {"rule": {"items": ["5.02"], "react_min": 1.05}},
            "version must be 1": base | {"version": 2},
            "the 8k family enters at the open": base | {"entry": "close"},
            "an open entry exits at a close": base | {"exit": "open"},
            "hold must be an integer": base | {"hold": 6},
            "a seatable birth holds one session": base | {"hold": 2},
            "seatable must be true or false": base | {"seatable": 1},
            "rank must be one of": base | {"rank": "reaction"},
            # (A95: an id lacking "EVL-B-" is named by the House now, "EVL-ERN-READ-O1" becoming "EVL-B-ERN-READ-O1";
            # an id that fails as named is refused: league/tests/test_events_births_names.py)
            "id must match": base | {"id": "EVL-B-lower-case"},
            "family must be one of": base | {"family": "options"},
            "items must be a list of 8-K items": base | {"rule": {"items": ["2.02"]}},
            "the 8k family names its item set": base | {"rule": {}},
            "a READ birth of the 8k family names only items": base | {"rule": {"items": ["5.02"], "score_min": 2}},
            "a react family names react_min or react_max": spec("EVL-B-R", "ern-react", {}, exit_="open"),
            "react_min and react_max together": spec("EVL-B-R", "ern-react", {"react_min": 1.05, "react_max": 0.95}),
            "react_min must be a ratio": spec("EVL-B-R", "ern-react", {"react_min": 1.5}),
            "score_min must be an integer -3..3": spec("EVL-B-E", "ern", {"score_min": 4}),
            "score_min is above score_max": spec("EVL-B-E", "ern", {"score_min": 2, "score_max": 1}),
            "guidance must be a proper subset": spec("EVL-B-E", "ern", {"guidance": list(V.GUIDANCE)}),
            "value_min must be whole dollars": spec("EVL-B-I", "ins-buy", {"value_min": 10000}),
            "roles must be director or officer": spec("EVL-B-I", "ins-buy", {"roles": "ten_pct"}),
            "hours must be 1..23 distinct": spec("EVL-B-N", "news", {"hours": [25]}),
            "a source name": spec("EVL-B-N", "news", {"sources": ["bad;source"]}),
        }
        for want, bad in cases.items():
            with self.assertRaises(BI.SpecError, msg=want) as caught:
                BI.parse(bad)
            self.assertTrue(any(want in r for r in caught.exception.reasons), (want, caught.exception.reasons))
        for bad in ("not json", "[1, 2]", 5, None, {"id": "EVL-B-X"}):
            with self.assertRaises(BI.SpecError):
                BI.parse(bad)
        with self.assertRaises(BI.SpecError, msg="a control's id is never proposed"):
            BI.parse(base | {"id": "EVL-B-8K-502-CTRL"})
        with self.assertRaises(BI.SpecError, msg="no free code in the rule either"):
            BI.parse(base | {"rule": {"items": ["5.02"], "lambda": "x"}})

    def test_the_canonical_form_and_its_sha_ignore_order_and_spacing_and_name_the_rule(self):
        a = spec("EVL-B-8K-502", "8k", {"items": ["5.02", "1.02"]})
        b = json.loads(json.dumps(dict(reversed(list(a.items())))))
        b["rule"] = {"items": ["1.02", "5.02"]}
        self.assertEqual(BI.canonical(a), BI.canonical(json.dumps(b, indent=2)))
        self.assertEqual(BI.sha(a), BI.sha(b))
        self.assertEqual(BI.canonical(a), '{"entry":"open","exit":"close","family":"8k","hold":1,"id":"EVL-B-8K-502",'
                                          '"rank":"none","rule":{"items":["1.02","5.02"]},"seatable":true,"version":1}')
        self.assertEqual(BI.sha(a), "%s" % __import__("hashlib").sha256(BI.canonical(a).encode()).hexdigest())
        self.assertNotEqual(BI.sha(a), BI.sha(a | {"seatable": False}))
        self.assertNotEqual(BI.sha(a), BI.sha(a | {"rule": {"items": ["5.02"]}}))

    def test_a_read_birth_carries_its_control_and_a_birth_is_a_program_row_of_prereg_3(self):
        sp = BI.parse(spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"))
        ctl = BI.control_spec(sp)
        self.assertEqual((ctl["id"], ctl["rule"], ctl["rank"], ctl["seatable"]), ("EVL-B-ERN-TOP-CTRL", {}, "none", False))
        prog = BI.program(sp, born_at="2026-11-03T01:00:00Z")
        self.assertEqual((prog.id, prog.version, prog.family, prog.entry_at, prog.exit_at, prog.hold, prog.prereg),
                         ("EVL-B-ERN-TOP", 1, "ern", "open", "close", 1, 3))
        self.assertTrue(prog.can_seat and prog.reads and prog.born)
        self.assertEqual(prog.registered_at, dt.datetime(2026, 11, 3, 1, 0, tzinfo=UTC))
        self.assertFalse(BI.program(ctl, born_at="2026-11-03T01:00:00Z").can_seat)


# ======================================================================================================== the loader
def count(efp: dict) -> dict:
    """The four figures of the lane's count the loader's test reads (league/events/screen.py `expected_false_passes`)."""
    return {k: efp[k] for k in ("versions", "expected", "budget", "left")}


class TheLoader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)
        self.s = Synth(Path(self.tmp.name))
        self.addCleanup(self.s.st.close)

    def test_births_come_after_every_prereg_program_and_the_screen_counts_each_seatable_one(self):
        # (release 1019g: PREREG-EVL-5's three seatable programs too: fifteen seatable versions; release 1019i:
        # PREREG-EVL-6 section 5, 0.13 each of the restated 3.9)
        self.assertEqual(count(SN.expected_false_passes(self.s.st)),
                         {"versions": 15, "expected": 1.95, "budget": 3.9, "left": 1.95})
        self.s.register(spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"), "2026-11-03T01:00:00Z", seq=1)
        self.s.register(spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}), "2026-11-03T01:00:00Z", seq=0)
        self.s.register(spec("EVL-B-NEWSDAY", "news-day", {"sources": ["benzinga"]}, seatable=False, exit_="open"),
                        "2026-11-04T01:00:00Z", night="2026-11-03")
        born = P.load_births(self.s.st)
        self.assertEqual([p.id for p in born], ["EVL-B-8K-502", "EVL-B-ERN-TOP", "EVL-B-ERN-TOP-CTRL", "EVL-B-NEWSDAY"],
                         "registration order (time, then the line), a READ birth followed by its control")
        self.assertEqual(P.PROGRAMS[:len(P.PREREG_PROGRAMS)], P.PREREG_PROGRAMS, "the PREREG rows first and unchanged")
        self.assertEqual(P.SEATING[:15], P.PREREG_SEATING)
        self.assertEqual([p.id for p in P.SEATING[15:]], ["EVL-B-8K-502", "EVL-B-ERN-TOP"], "records and controls never seat")
        self.assertIs(P.BY_KEY[("EVL-B-ERN-TOP-CTRL", 1)], born[2])
        self.assertEqual(count(SN.expected_false_passes(self.s.st)),
                         {"versions": 17, "expected": 2.21, "budget": 3.9, "left": 1.69})
        self.assertEqual(SN.control_of("EVL-B-ERN-TOP"), "EVL-B-ERN-TOP-CTRL")
        self.assertIsNone(SN.control_of("EVL-B-8K-502"))
        for prog in ("EVL-ERN-READ-O1", "EVL-ERN-GUIDE-O1", "EVL-NEWS-READ-ON", "EVL-INS-BUY-O1"):
            self.assertEqual(SN.control_of(prog), SN.CONTROLS.get(prog), "every PREREG answer is its table's")
        self.assertEqual(P.load_births(self.s.st), born, "idempotent")
        unload()
        self.assertEqual((P.PROGRAMS, P.SEATING, len(P.BIRTHS)), (P.PREREG_PROGRAMS, P.PREREG_SEATING, 0))

    def test_a_store_without_the_table_or_a_row_that_no_longer_parses_seats_nothing(self):
        self.s.register(spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}), "2026-11-03T01:00:00Z")
        self.s.st.db.execute("UPDATE births SET sha='0' WHERE id='EVL-B-8K-502'")
        self.assertEqual(P.load_births(self.s.st), ())
        self.s.st.db.execute("DROP TABLE births")
        self.assertEqual(P.load_births(self.s.st), ())
        self.assertEqual(P.PROGRAMS, P.PREREG_PROGRAMS)


# ======================================================================================================== decisions
class PreregIntentsAreUnchanged(unittest.TestCase):
    """The same invented week decided twice, without births and with five registered, through the lane's own
    decide_open and decide_close: every PREREG program's intents are identical; the births take only their own
    events, knowable after their own registration."""

    DAYS = (dt.date(2026, 11, 2), dt.date(2026, 11, 3), dt.date(2026, 11, 4), dt.date(2026, 11, 5), dt.date(2026, 11, 6))
    BORN_AT = "2026-11-03T01:00:00Z"     # Mon Nov 2, 20:00 ET
    SPECS = (spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}),
             spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"),
             spec("EVL-B-NEWSDAY-BZ", "news-day", {"sources": ["benzinga"]}, seatable=False, exit_="open"),
             spec("EVL-B-ERNREACT-ON", "ern-react", {"react_min": 1.02}, rank="reaction", exit_="open"),
             spec("EVL-B-INS-DIR", "ins-buy", {"value_min": 100000, "roles": "director"}, rank="value"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)

    def week(self, root: Path, births: bool, *, keep: bool = False):
        s = Synth(root)
        for day in self.DAYS:
            prior = C.previous(s.st, day, 1)[0].day
            for sym in ISSUERS.values():
                s.eligible(day, sym)
                s.bar(prior, sym)
                s.bar(day, sym)
            a = s.filing("AAA", et(prior, 16, 30))
            s.doc_verdict(a, 3, "raised")
            b = s.filing("BBB", et(prior, 16, 35))
            s.doc_verdict(b, 1)
            s.filing("CCC", et(prior, 17), ("5.02",))
            d = s.filing("DDD", et(prior, 17, 10), ("8.01",))
            s.doc_verdict(d, 2)
            s.insider("EEE", et(prior, 18), 120_000, director=True)
            s.insider("FFF", et(prior, 18, 5), 60_000, director=False, officer=True)
            s.news_verdict(s.article("AAA", et(prior, 19)), 2)
            s.news_verdict(s.article("GGG", et(day, 7), "globenewswire"), 3)
            h = s.filing("HHH", et(day, 12))
            s.doc_verdict(h, 2)
            s.news_verdict(s.article("BBB", et(day, 11)), 3)
            s.news_verdict(s.article("III", et(day, 13), "prnewswire"), -1)
            # PREREG-EVL-4's rows (release 1019e: the merged tree's twelve seatable versions): JJJ's 8.01 8-K inside D's
            # close window (F8K(D): EVL-8K-REACT-ON at its stored 15:30 mark, 21.2 / 20 = 1.06; EVL-8K-READ-ON at
            # score 2; their control), and the pre-market articles above (PM(D): EVL-NEWSPM-READ-ON, its control).
            j = s.filing("JJJ", et(day, 11), ("8.01",))
            s.doc_verdict(j, 2)
            s.st.db.execute("INSERT OR REPLACE INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('JJJ', ?, "
                            "'1530', 21.2, 'x', 'sip-1min', 'x')", (day.isoformat(),))
        if births:
            for i, sp in enumerate(self.SPECS):
                s.register(sp, self.BORN_AT, seq=i)
            self.assertEqual(len(P.load_births(s.st)), 6)
        else:
            unload()
        gw = TH.FakeGateway()
        ctx = R.Context(s.st, gw, lambda url: b"", now=lambda: dt.datetime(2026, 11, 7, 1, 0, tzinfo=UTC))
        for day in self.DAYS:
            R.decide_open(ctx, day)
            R.decide_close(ctx, day)
        self.assertEqual(gw.claude_calls, [], "every verdict read was stored: none asked")
        for row in s.st.db.execute("SELECT job, status, summary FROM receipts WHERE job LIKE 'decide-%'"):
            body = json.loads(row["summary"])
            self.assertEqual(row["status"], "ok", row["job"])
            self.assertNotIn("evl4_error", body, f"{row['job']}: PREREG-EVL-4's part ran whole")
        rows = [dict(r) for r in s.st.db.execute("SELECT * FROM intents ORDER BY program, version, event")]
        self.picks = self.real_picks(s.st)
        if keep:
            self.addCleanup(s.st.close)
            return rows, s.st
        s.st.close()
        return rows

    def real_picks(self, st: S.Store) -> dict[str, list[tuple]]:
        """THE REAL-MONEY PICKS (league/events/book.py `picks`, on the lane's store read-only as the House's book reads
        it) of every program real money trades at each auction of the week, at its decision time: {"program@vN@day":
        [(event, symbol, cik, rank, adv20, prev_close)]}. A REACT row's ratio is read as 1.05 (the book's T29 reading).
        A program whose picks raise plans nothing that auction, the others go on (league/equity/live.py's event
        decision): its entry is the error's name."""
        from league.events import book as EB

        out: dict[str, Any] = {}
        lane = EB.Lane(Path(st.root) / S.DB_NAME)
        try:
            for day in self.DAYS:
                session = C.session(lane, day)
                for p in EB.seatable():
                    moment = session.open_decide if p.entry_at == "open" else session.close_decide
                    key = f"{p.id}@v{p.version}@{day.isoformat()}"
                    try:
                        got = EB.picks(lane, p, day, decided_at=moment, reaction=lambda row, uni: 1.05)
                    except Exception as exc:  # noqa: BLE001 - as the House's book: that program plans nothing
                        out[key] = type(exc).__name__
                        continue
                    out[key] = [(x.event, x.symbol, x.cik, x.rank, x.adv20, str(x.prev_close)) for x in got]
        finally:
            lane.close()
        return out

    def test_every_prereg_programs_intents_are_identical_with_and_without_births(self):
        without = self.week(Path(self.tmp.name) / "a", births=False)
        picks_without = self.picks
        with_births = self.week(Path(self.tmp.name) / "b", births=True)
        picks_with = self.picks
        prereg = {p.id for p in P.PREREG_PROGRAMS}
        mine = [r for r in with_births if r["program"] in prereg]
        self.assertGreater(len(without), 60)
        self.assertEqual(mine, without, "no PREREG program's selection moves")
        four = {p.id for p in P.PREREG_PROGRAMS if p.prereg == 4}
        self.assertEqual(four, {r["program"] for r in without} & four,
                         "every PREREG-EVL-4 program decides in the week: the merged tree's twelve seatable versions")
        # THE REAL-MONEY PICKS (release 1019e): every PREREG program real money trades picks the same events at every
        # auction with and without the five births (the twelve seating versions, PREREG-EVL-4's three included).
        seating = {f"{p.id}@v{p.version}" for p in P.PREREG_SEATING}
        self.assertEqual(len(seating), 15, "(release 1019g: PREREG-EVL-5's three too)")
        prereg_with = {k: v for k, v in picks_with.items() if k.rsplit("@", 1)[0] in seating}
        self.assertEqual(set(picks_without), set(prereg_with), "the same programs and auctions")
        self.assertEqual(prereg_with, picks_without, "no PREREG program's real-money pick moves")
        picked = {k.split("@")[0] for k, v in picks_without.items() if v}
        self.assertTrue({"EVL-ERN-READ-O1", "EVL-INS-BUY-O1", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON"} <= picked, picked)
        self.assertEqual(sum(len(v) for v in picks_without.values()) > 20, True)
        born_picks = {k.split("@")[0] for k, v in picks_with.items() if v and k.rsplit("@", 1)[0] not in seating}
        self.assertTrue({"EVL-B-INS-DIR", "EVL-B-ERN-TOP"} <= born_picks, "the seatable births pick their own events")
        born = [r for r in with_births if r["program"] not in prereg]
        by = {}
        for r in born:
            by.setdefault(r["program"], []).append(r)
        self.assertEqual(sorted(by), ["EVL-B-8K-502", "EVL-B-ERN-TOP", "EVL-B-ERN-TOP-CTRL", "EVL-B-ERNREACT-ON",
                                      "EVL-B-INS-DIR", "EVL-B-NEWSDAY-BZ"])
        filings = {}
        db = sqlite3.connect(str(Path(self.tmp.name) / "b" / S.DB_NAME))
        db.row_factory = sqlite3.Row
        for row in db.execute("SELECT accession, cik, knowable_at FROM filings"):
            filings[f"8k:{row['accession']}"] = filings[f"f4:{row['accession']}"] = dict(row)
        for row in db.execute("SELECT id, knowable_at FROM news"):
            filings[f"news:{row['id']}"] = dict(row)
        db.close()
        for r in born:
            self.assertGreater(filings[r["event"]]["knowable_at"], self.BORN_AT, "only events after its registration")
            self.assertEqual(r["version"], 1)
        self.assertEqual({r["symbol"] for r in by["EVL-B-8K-502"]}, {"CCC"})
        self.assertEqual({r["symbol"] for r in by["EVL-B-ERN-TOP"]}, {"AAA"}, "score 3 only")
        self.assertEqual({r["symbol"] for r in by["EVL-B-ERN-TOP-CTRL"]}, {"AAA", "BBB", "HHH"},
                         "its control: any verdict (HHH's mid-session 8-K is the next open's event too)")
        self.assertEqual({r["symbol"] for r in by["EVL-B-INS-DIR"]}, {"EEE"}, "the director's $120,000, not the officer's")
        self.assertEqual({r["symbol"] for r in by["EVL-B-NEWSDAY-BZ"]}, {"BBB"}, "benzinga's day article")
        self.assertEqual({(r["entry_at"], r["exit_at"]) for r in by["EVL-B-NEWSDAY-BZ"]}, {("close", "open")})
        self.assertEqual({r["symbol"] for r in by["EVL-B-ERNREACT-ON"]}, {"AAA", "BBB", "HHH"}, "reaction 1.05 >= 1.02")
        self.assertEqual(sorted({r["entry_day"] for r in by["EVL-B-8K-502"]}), ["2026-11-04", "2026-11-05", "2026-11-06"],
                         "Monday evening's 8-K (17:10 ET, before 20:00 ET) is not the birth's")

    def test_a_birth_that_raises_fails_only_itself(self):
        """A registered birth whose rule raises (a bug) never fails the decision: every PREREG program's intents and
        receipts are as without births, the failure is in the summary's `births_failed`, and the screen holds only
        that birth's looks (league/events/screen.py `final_until`)."""
        from league.events import births as births_module

        real = births_module.select

        def broken(program, rows, **kw):
            if program.id == "EVL-B-8K-502":
                raise KeyError("invented bug")
            return real(program, rows, **kw)
        without = self.week(Path(self.tmp.name) / "a", births=False)
        with mock.patch.object(births_module, "select", side_effect=broken):
            rows, st = self.week(Path(self.tmp.name) / "b", births=True, keep=True)
        prereg = {p.id for p in P.PREREG_PROGRAMS}
        self.assertEqual([r for r in rows if r["program"] in prereg], without)
        self.assertNotIn("EVL-B-8K-502", {r["program"] for r in rows})
        self.assertIn("EVL-B-INS-DIR", {r["program"] for r in rows}, "the other births decide")
        opens = [dict(r) for r in st.db.execute("SELECT status, summary FROM receipts WHERE job LIKE 'decide-open:%'")]
        self.assertEqual({r["status"] for r in opens}, {"ok"}, "the decision is made, for every PREREG program")
        failed = [json.loads(r["summary"]).get("births_failed") for r in opens]
        self.assertTrue(all(f == {"EVL-B-8K-502": "KeyError: 'invented bug'"} for f in failed), failed)
        now = dt.datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        later = sessions_between(st, dt.date(2026, 11, 9), dt.date(2026, 11, 12))
        earlier = sessions_between(st, dt.date(2026, 10, 19), dt.date(2026, 10, 30))   # PREREG-EVL-3's sessions before
        for day in earlier + later:
            for kind in ("open", "close"):
                # (each a whole decision made with the births loaded: it names every program of its kind, as
                # league/events/run.py's receipts do; release 1019e's review: one that names no birth is not made for it)
                named = {SN.program_key(p.id, p.version): {"planned": 0} for p in P.PROGRAMS if p.entry_at == kind}
                rid = st.start_receipt(f"decide-{kind}:{day}", now=now)
                st.finish_receipt(rid, "ok", named, now=now)
        for day in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10",
                    "2026-11-11", "2026-11-12"):
            st.set_meta(f"evl:backfill:{day}", "done")
        horizon, why = SN.final_until(st, "EVL-B-8K-502", 1, dt.date(2026, 11, 13), now)
        self.assertIn("the open decision of 2026-11-02 is failed", why)
        self.assertIsNone(horizon, "no close of it is final: its looks wait for a pass that decides it")
        other, _ = SN.final_until(st, "EVL-B-INS-DIR", 1, dt.date(2026, 11, 13), now)
        prereg_horizon, _ = SN.final_until(st, "EVL-8K-READ-O1", 2, dt.date(2026, 11, 13), now)
        self.assertEqual((other, prereg_horizon), (dt.date(2026, 11, 9), dt.date(2026, 11, 9)),
                         "every other program's closes are final as before")


# ======================================================================================================== the facts
class Validation(unittest.TestCase):
    """Twenty invented sessions (Oct 12 to Nov 6): four 8-Ks a session of each of items 5.02, 1.02, 2.03 and 3.01, two of
    1.05, three earnings 8-Ks with their verdicts, and bars, marks, outcomes, looks and bands the facts must not read; a
    clean record pass every 10 minutes from Oct 8 to Nov 10 (every session holds a complete record pass). This class
    holds the grammar, the duplicate, the budget, the proposer and registration on figures worked at release 1019e's
    rate of 3 a session, so a seatable birth's `MIN_RATE` is set to that 3 here (`SeatableRate` holds release 1019h's
    20 over the complete-record sessions on its own sessions)."""

    AS_OF = dt.date(2026, 11, 6)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(unload)
        self.s = Synth(Path(self.tmp.name))
        self.addCleanup(self.s.st.close)
        st = self.s.st
        rate = mock.patch.object(BI, "MIN_RATE", 3)
        rate.start()
        self.addCleanup(rate.stop)
        record_passes(st, et(dt.date(2026, 10, 8), 0), et(dt.date(2026, 11, 10), 23))
        self.days = [x.day for x in C.previous(st, self.AS_OF + dt.timedelta(days=1), 20)]
        self.assertEqual((self.days[0], len(self.days)), (dt.date(2026, 10, 12), 20))
        syms = list(ISSUERS.values())
        for sym in syms:
            self.s.eligible(self.days[0], sym)       # one kept result an issuer: the nearest reads for every session
        for day in self.days:
            prior = C.previous(st, day, 1)[0].day
            k = 0
            for item, count in (("5.02", 4), ("1.02", 4), ("2.03", 4), ("3.01", 4), ("1.05", 2)):
                for _ in range(count):
                    self.s.filing(syms[k], et(prior, 17, k), (item,))
                    k += 1
            for score in (3, 2, 1):
                acc = self.s.filing(syms[k], et(prior, 16, 30 + score))
                self.s.doc_verdict(acc, score, "raised" if score == 3 else "none")
                k += 1
        st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('AAA', '2026-11-05', 'raw', "
                      "1, 1, 1, 1, 1, 'x')")
        st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('AAA', '2026-11-05', 'open', "
                      "1, 'x', 'x', 'x')")
        st.db.execute("INSERT INTO outcomes(program, version, event, r, a, settled_at, status) VALUES('EVL-ERN-READ-O1', 2, "
                      "'8k:x', 0.5, 0.5, 'x', 'settled')")
        st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES('EVL-ERN-READ-O1', 2, 1, 'x', 1, 1)")
        st.db.execute("INSERT INTO bands(program, version, band, since, why) VALUES('EVL-ERN-READ-O1', 2, 'probe', 'x', 'x')")
        st.set_meta("look:EVL-ERN-READ-O1:2:1", json.dumps({"p": 0.001}))

    def candidate(self, ident: str, items, *, seatable: bool = True, **kw) -> dict:
        return {"spec": spec(ident, "8k", {"items": list(items)}, seatable=seatable, **kw), "why": f"{ident} in one line"}

    def test_the_facts_never_read_a_price_after_an_event_a_return_a_look_or_a_band(self):
        st = self.s.st
        said: list[str] = []
        st.db.set_trace_callback(said.append)
        self.addCleanup(st.db.set_trace_callback, None)
        facts = BI.Facts(st, self.AS_OF)
        sheet = facts.facts()
        facts.count(BI.program(BI.parse(self.candidate("EVL-B-X", ["5.02"])["spec"]), born_at="2026-11-07T00:00:00Z"))
        st.db.set_trace_callback(None)
        self.assertGreater(len(said), 100)
        refused = re.compile(r"\b(bars|marks|outcomes|looks|bands|band_history|real_fills|universe|meta)\b", re.I)
        self.assertEqual([q for q in said if refused.search(q)], [], "no statement names a refused table")
        with BI.outcome_free(st.db):
            for table in sorted(BI.FACTS_DENY):
                with self.assertRaises(sqlite3.DatabaseError, msg=table):
                    st.db.execute(f"SELECT * FROM {table}").fetchall()
            with BI.outcome_free(st.db):
                pass
            with self.assertRaises(sqlite3.DatabaseError, msg="an inner block's end keeps the outer wall up"):
                st.db.execute("SELECT c FROM bars").fetchall()
        self.assertEqual(st.db.execute("SELECT c FROM bars").fetchone()[0], 1, "and the store reads as before after")
        # The refused tables' contents change nothing the facts say.
        for table in ("bars", "marks", "outcomes", "looks", "bands"):
            st.db.execute(f"DELETE FROM {table}")
        self.assertEqual(BI.Facts(st, self.AS_OF).facts(), sheet)
        self.assertEqual(sheet["sessions"], 20)
        self.assertEqual(sheet["forms"], {"8-K": 420, "4-buys": 0})
        self.assertEqual(sheet["items_8k"], {"1.02": 80, "1.05": 40, "2.03": 80, "3.01": 80, "5.02": 80})
        counts = facts.candidates([self.candidate("EVL-B-8K-102", ["1.02"])["spec"],
                                   spec("EVL-B-R", "ern-react", {"react_min": 1.05}, exit_="open"), {"id": "EVL-B-BAD"}])
        self.assertEqual(counts["EVL-B-8K-102"], {"selected": 80, "per_session": 4.0, "by_session": [4] * 20,
                                                  "per_recorded_session": 4.0, "upper_bound": False})
        self.assertEqual(sheet["recorded_sessions"], 20, "every session holds a complete record pass here")
        self.assertEqual((counts["EVL-B-R"]["selected"], counts["EVL-B-R"]["upper_bound"]), (60, True),
                         "a react rule's count: every earnings 8-K, the reaction never read")
        self.assertIn("missing fields", counts["EVL-B-BAD"]["refused"][0])
        self.assertEqual(sheet["families"]["ern"]["eligible"], 60)
        self.assertEqual(sheet["scores"]["ern"], {"1": 20, "2": 20, "3": 20})
        self.assertEqual(sheet["guidance_ern"], {"none": 40, "raised": 20})
        self.assertEqual(sheet["unprogrammed"]["items_8k"], ["1.02", "1.05", "2.03", "3.01", "5.02"])
        self.assertIn("news-react", [p["family"] for p in sheet["programs"]])
        self.assertNotIn("p", json.dumps(sheet["programs"][0]).replace('"per_session"', "")
                         .replace('"per_recorded_session"', ""), "no look's p")

    def test_the_validator_refuses_by_rate_duplicate_id_and_grammar_and_accepts_the_rest(self):
        st = self.s.st
        self.s.register(spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}), "2026-10-01T00:00:00Z")
        P.load_births(st)
        facts = BI.Facts(st, self.AS_OF)
        out = BI.validate(st, facts, [
            self.candidate("EVL-B-8K-102", ["1.02"]),                              # 80: accepted
            self.candidate("EVL-B-8K-105", ["1.05"]),                              # 40 < 60: the rate
            self.candidate("EVL-B-8K-502-AGAIN", ["5.02"], seatable=False, hold=2),  # the registered birth's events
            self.candidate("EVL-B-8K-102-TWIN", ["1.02"]),                         # tonight's first one's events
            self.candidate("EVL-B-8K-502", ["2.03"]),                              # the id is registered
            {"spec": {"id": "EVL-B-CODE", "exec": "rm -rf /"}, "why": "free code"},
            self.candidate("EVL-B-8K-102-502", ["1.02", "5.02"]),                  # Jaccard 0.5 with each: accepted
        ], night=self.AS_OF)
        self.assertEqual([c["ok"] for c in out], [True, False, False, False, False, False, True])
        self.assertEqual((out[0]["selected"], out[0]["per_session"], out[0]["charge"]), (80, 4.0, 13),
                         "PREREG-EVL-6 section 5: 0.13 a seatable birth, in hundredths")
        self.assertIn("40 selected events over the 20 sessions of the last 20 with a complete record pass: under 3 a "
                      "session", out[1]["reasons"][0])
        self.assertEqual(out[2]["jaccard"], {"max": 1.0, "with": "EVL-B-8K-502"})
        self.assertIn("a duplicate of EVL-B-8K-502", out[2]["reasons"][0])
        self.assertIn("a duplicate of EVL-B-8K-102", out[3]["reasons"][0])
        self.assertIn("registered already", out[4]["reasons"][0])
        self.assertIn("fields outside the grammar", out[5]["reasons"][0])
        self.assertEqual(out[6]["jaccard"]["max"], 0.5)

    def test_the_budget_charges_013_a_seatable_birth_to_39_and_three_a_night_records_free(self):
        """PREREG-EVL-6 section 5 (release 1019i): 0.13 a seatable birth, the lane's restated 3.9 (15 x 0.13 used by the
        fifteen new versions), three a night, records free."""
        st = self.s.st
        self.assertEqual(BI.budget(st, self.AS_OF), {"used": 1.95, "limit": 3.9, "left": 1.95, "waiting_runs": 0.0,
                                                     "left_for_births": 1.95, "seatable_left_tonight": 3,
                                                     "charge": 0.13})
        four = [self.candidate(f"EVL-B-8K-{i}", [item]) for i, item in enumerate(("5.02", "1.02", "2.03", "3.01"))]
        out = BI.validate(st, BI.Facts(st, self.AS_OF), four, night=self.AS_OF)
        self.assertEqual([c["ok"] for c in out], [True, True, True, False])
        self.assertIn("3 seatable births a night at most", out[3]["reasons"][0])
        record = self.candidate("EVL-B-8K-REC", ["3.01"], seatable=False)
        self.assertTrue(BI.validate(st, BI.Facts(st, self.AS_OF), four[:3] + [record], night=self.AS_OF)[3]["ok"],
                        "records are free")
        # fourteen seatable births registered on earlier nights, before REGISTERED_AT_6: each seats at its PREREG-EVL-6
        # version 2 (section 1.1), 0.13 each: 1.95 + 1.82 = 3.77
        for i in range(14):
            self.s.register(spec(f"EVL-B-OLD-{i}", "8k", {"items": ["9.01"]}), "2026-10-01T00:00:00Z",
                            night=f"2026-09-{10 + i}", seq=i)
        P.load_births(st)
        self.assertEqual(SN.expected_false_passes(st)["versions"], 29)
        self.assertAlmostEqual(BI.budget(st, self.AS_OF)["left"], 0.13)
        out = BI.validate(st, BI.Facts(st, self.AS_OF), four[:2] + [record], night=self.AS_OF)
        self.assertEqual([c["ok"] for c in out], [True, False, True])
        self.assertIn("the false-pass budget: 3.90 of 3.90 used", out[1]["reasons"][0])
        self.assertEqual([c["charge"] for c in out], [13, 0, 0])

    def test_a81_the_budget_is_the_lanes_restated_39_counted_from_the_screens_own_sum(self):
        """A81 as PREREG-EVL-6 section 5 restates it (D6, D11; release 1019i): the validator's lifetime cap is the
        lane's restated 3.9 (the screen's V6_BUDGET, 30 x 0.13), counted from the screen's own sum (the fifteen new
        versions: 1.95; never a written figure), 0.13 a seatable birth, at most 3 a night: at most fifteen seatable
        births after the new versions; a retired program's looks stay counted."""
        st = self.s.st
        self.assertEqual((BI.BUDGET_HUNDREDTHS, BI.CHARGE_HUNDREDTHS, BI.SEATABLE_A_NIGHT), (390, 13, 3))
        self.assertEqual((BI.BUDGET_HUNDREDTHS, BI.CHARGE_HUNDREDTHS),
                         (SN.V6_BUDGET_HUNDREDTHS, SN.V6_CHARGE_HUNDREDTHS), "read from the screen, never restated")
        self.assertEqual((SN.V6_BUDGET, SN.V6_CHARGE), (3.9, 0.13))
        self.assertEqual(len(P.PREREG_SEATING), 15, "the new versions: the nine at 3, PREREG-EVL-4's and -5's three at 2")
        self.assertEqual({p.regfile for p in P.PREREG_SEATING}, {6})
        self.assertEqual(BI.budget_used_hundredths(st), 195)
        self.assertEqual(BI.budget(st, self.AS_OF)["used"], SN.expected_false_passes(st)["expected"])
        # The screen's own sum, whatever SEATING holds: without PREREG-EVL-4's and -5's three it would read 1.17.
        with mock.patch.object(P, "SEATING", tuple(p for p in P.PREREG_SEATING if p.prereg not in (4, 5))):
            self.assertEqual(BI.budget_used_hundredths(st), 117)
        self.assertEqual(BI.budget_used_hundredths(st), 195)
        # A retired program stays counted (a test that was run is never refunded).
        from league.events import bands as BA

        BA.set_band(st, "EVL-ERN-READ-O1", 3, "retired", since="2026-11-01T21:00:00Z", why="invented")
        self.assertEqual(BI.budget_used_hundredths(st), 195)
        # 15 seatable births exhaust it: 1.95 + 1.95 = 3.9, and the 16th is refused (PREREG-EVL-6 section 5).
        for i in range(15):
            self.s.register(spec(f"EVL-B-OLD-{i}", "8k", {"items": ["9.01"]}), "2026-10-01T00:00:00Z",
                            night=f"2026-09-{10 + i}", seq=i)
        P.load_births(st)
        self.assertEqual(BI.budget(st, self.AS_OF), {"used": 3.9, "limit": 3.9, "left": 0.0, "waiting_runs": 0.0,
                                                     "left_for_births": 0.0, "seatable_left_tonight": 0,
                                                     "charge": 0.13})
        [out] = BI.validate(st, BI.Facts(st, self.AS_OF), [self.candidate("EVL-B-8K-102", ["1.02"])], night=self.AS_OF)
        self.assertFalse(out["ok"])
        self.assertIn("the false-pass budget: 3.90 of 3.90 used or held for the runs waiting for it, a seatable birth "
                      "adds 0.13", out["reasons"][0])
        [rec] = BI.validate(st, BI.Facts(st, self.AS_OF), [self.candidate("EVL-B-8K-102", ["1.02"], seatable=False)],
                            night=self.AS_OF)
        self.assertTrue(rec["ok"], "records are free")

    def test_twenty_sessions_or_no_rate_for_a_record_and_a_seatable_birth_over_its_complete_record_sessions(self):
        st = self.s.st
        out = BI.validate(st, BI.Facts(st, self.AS_OF, sessions=10),
                          [self.candidate("EVL-B-8K-102", ["1.02"], seatable=False)])
        self.assertFalse(out[0]["ok"])
        self.assertIn("not the 20 the rate is read over", out[0]["reasons"][0], "a record: release 1019e's rule")
        [seat] = BI.validate(st, BI.Facts(st, self.AS_OF, sessions=10), [self.candidate("EVL-B-8K-102", ["1.02"])])
        self.assertTrue(seat["ok"], "a seatable birth: its rate over the sessions holding a complete record pass")
        self.assertEqual(seat["per_session"], 4.0)


class SeatableRate(unittest.TestCase):
    """SUP-3's RATE RULE (the captain's A97, release 1019h): a seatable birth must select >= `MIN_RATE` (20) events a
    session over the sessions of the last 20 that hold a COMPLETE RECORD PASS (an outage session left out, at least 3 of
    them); a record keeps release 1019e's 3 a session over the calendar's 20, free. Twenty invented sessions (Oct 12 to
    Nov 6): 21 issuers file an 8-K of item 5.02 and 19 one of item 3.01 each session (one event an issuer a decision)."""

    AS_OF = dt.date(2026, 11, 6)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(unload)
        self.s = Synth(Path(tmp.name))
        self.addCleanup(self.s.st.close)
        st = self.s.st
        self.days = [x.day for x in C.previous(st, self.AS_OF + dt.timedelta(days=1), 20)]
        syms = list(ISSUERS.values())
        for sym in syms:
            self.s.eligible(self.days[0], sym)
        for day in self.days:
            prior = C.previous(st, day, 1)[0].day
            for k in range(21):
                self.s.filing(syms[k], et(prior, 17, k), ("5.02",))
            for k in range(19):
                self.s.filing(syms[k], et(prior, 18, k), ("3.01",))

    def candidate(self, ident: str, items, *, seatable: bool = True) -> dict:
        return {"spec": spec(ident, "8k", {"items": list(items)}, seatable=seatable), "why": f"{ident} in one line"}

    def judge(self, *candidates) -> list[dict]:
        return BI.validate(self.s.st, BI.Facts(self.s.st, self.AS_OF), list(candidates), night=self.AS_OF)

    def span(self, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
        """A session's event span: the prior session's 09:00 ET to its close decision."""
        prior = C.previous(self.s.st, day, 1)[0]
        return prior.open_cutoff, C.session(self.s.st, day).close_decide

    def test_the_rows(self):
        self.assertEqual((BI.MIN_RATE, BI.MIN_RECORDED, BI.RECORD_MIN_RATE, BI.SESSIONS), (20, 3, 3, 20))
        from league.ops import evl_health as EH

        self.assertEqual(EH.RECORD_MINUTES, 30, "an outage is the evl_record alarm's own line")

    def test_twenty_a_session_over_the_complete_record_sessions_and_records_free_as_before(self):
        record_passes(self.s.st, et(dt.date(2026, 10, 8), 0), et(dt.date(2026, 11, 7), 0))
        self.assertEqual(BI.Facts(self.s.st, self.AS_OF).recorded, self.days, "every session recorded whole")
        out = self.judge(self.candidate("EVL-B-8K-502", ["5.02"]), self.candidate("EVL-B-8K-301", ["3.01"]),
                         self.candidate("EVL-B-8K-301-REC", ["3.01"], seatable=False))
        self.assertEqual([c["ok"] for c in out], [True, False, True])
        self.assertEqual((out[0]["selected"], out[0]["per_session"]), (420, 21.0))
        self.assertEqual(out[1]["reasons"], ["380 selected events over the 20 sessions of the last 20 with a complete "
                                             "record pass: under 20 a session"])
        self.assertEqual((out[2]["per_session"], out[2]["charge"]), (19.0, 0), "a record: 3 a session, free")

    def test_an_outage_session_is_left_out_never_counted_at_a_low_count(self):
        """Three sessions with a feed outage recorded only 2 of 5.02's 21 events (the rest never stored): counted, the
        rule's rate would read (17 x 21 + 3 x 2) / 20 = 18.15, under 20; left out, 21 over the 17 recorded whole."""
        st = self.s.st
        out_days = self.days[5:8]
        for day in out_days:
            lo, hi = self.span(day)
            st.db.execute("DELETE FROM filings WHERE accession IN (SELECT accession FROM filings WHERE items='[\"5.02\"]' "
                          "AND accepted_at>=? AND accepted_at<? ORDER BY accepted_at LIMIT 19)",
                          (S.iso(lo), S.iso(hi)))
        outages = tuple((self.span(d)[0] + dt.timedelta(hours=10), self.span(d)[0] + dt.timedelta(hours=11))
                        for d in out_days)
        record_passes(st, et(dt.date(2026, 10, 8), 0), et(dt.date(2026, 11, 7), 0), outages=outages)
        facts = BI.Facts(st, self.AS_OF)
        self.assertEqual(facts.recorded, [d for d in self.days if d not in out_days])
        [seat] = self.judge(self.candidate("EVL-B-8K-502", ["5.02"]))
        self.assertTrue(seat["ok"], seat["reasons"])
        self.assertEqual(seat["per_session"], 21.0)
        with mock.patch.object(BI, "recorded_sessions", lambda store, days: list(days)):
            [counted] = self.judge(self.candidate("EVL-B-8K-502", ["5.02"]))
        self.assertFalse(counted["ok"], "had the outage sessions counted, the birth would be refused")
        self.assertIn("363 selected events over the 20 sessions", counted["reasons"][0])

    def test_fewer_than_three_complete_record_sessions_rates_nothing(self):
        st = self.s.st
        lo = self.span(self.days[-2])[0] - dt.timedelta(minutes=5)
        record_passes(st, lo, et(dt.date(2026, 11, 7), 0))           # the recorder began two sessions ago
        self.assertEqual(BI.Facts(st, self.AS_OF).recorded, self.days[-2:])
        [seat, rec] = self.judge(self.candidate("EVL-B-8K-502", ["5.02"]),
                                 self.candidate("EVL-B-8K-502-REC", ["5.02"], seatable=False))
        self.assertEqual(seat["reasons"], ["2 of the last 20 sessions hold a complete record pass, under the 3 a "
                                           "seatable birth's rate is read over"])
        self.assertTrue(rec["ok"], "a record reads the calendar's 20, as before")
        record_passes(st, self.span(self.days[-3])[0] - dt.timedelta(minutes=5), lo)
        [seat] = self.judge(self.candidate("EVL-B-8K-502", ["5.02"]))
        self.assertTrue(seat["ok"], "three sessions recorded whole: 21 a session over them")

    def test_what_a_complete_record_pass_is(self):
        st = self.s.st
        day = self.days[10]
        lo, hi = self.span(day)
        gap, TEN = dt.timedelta(minutes=30), dt.timedelta(minutes=10)

        def recorded(*runs) -> bool:
            st.db.execute("DELETE FROM receipts")
            for kw in runs:
                record_passes(st, **kw)
            return BI.recorded_sessions(st, [day]) == [day]
        self.assertTrue(recorded({"first": lo - gap, "last": hi}), "a clean pass every 10 minutes through the span")
        self.assertTrue(recorded({"first": lo, "last": hi}), "one at the span's start")
        self.assertFalse(recorded({"first": lo + dt.timedelta(minutes=1), "last": hi}), "none at or before its start")
        self.assertFalse(recorded({"first": lo - gap, "last": hi - dt.timedelta(minutes=40)}), "its end not recorded")
        self.assertTrue(recorded({"first": lo - gap, "last": hi, "outages": ((lo + gap, lo + gap + 2 * TEN),)}),
                        "a 30-minute gap is no outage (the alarm's line)")
        self.assertFalse(recorded({"first": lo - gap, "last": hi, "outages": ((lo + gap, lo + gap + 3 * TEN),)}),
                         "a 40-minute gap is")
        bad = {"8-K": {"error": "HTTPError: 503"}, "4": CLEAN_PASS["4"], "news": CLEAN_PASS["news"]}
        self.assertFalse(recorded({"first": lo - gap, "last": hi, "summary": bad}), "a feed that failed: not clean")
        self.assertFalse(recorded({"first": lo - gap, "last": hi, "status": "failed"}), "a failed pass")
        self.assertFalse(recorded({"first": lo - gap, "last": hi, "summary": {**CLEAN_PASS, "news": {"error": "x"}}}))
        self.assertTrue(recorded({"first": lo - gap, "last": hi, "every": dt.timedelta(minutes=30)}))

    def test_the_proposer_is_told_the_rule_and_the_nov_6_line_with_no_steering(self):
        user = BI.render({"as_of": "2026-11-06"}, {"used": 1.5, "limit": 3.0, "seatable_left_tonight": 3})
        flat = " ".join(user.split())
        self.assertIn("refuses a seatable spec that selects fewer than 20 events a session over the sessions of the "
                      "last 20 that hold a complete record pass", flat)
        self.assertIn("a record spec that selects fewer than 3 a session over the last 20 sessions", flat)
        self.assertIn("Propose no spec of an earnings-only family (ern, ern-react) after Nov 6, 2026", flat)
        self.assertIn("the rate floor barely binds a react rule", flat)
        for steering in ("close-entry", "overnight evidence", "attention", "intraday reversal"):
            self.assertNotIn(steering, flat, "SUP-3's check: no steering line")


# ======================================================================================================== the proposer
class FakeArchitect:
    """The gateway as the births job meets it: Claude's answer (`answer`) with a stated cost, and the docs route
    (`docs`: a function of the body returning (status, answer))."""

    def __init__(self, answer: str, *, status: int = 200, cost: str | None = "0.0042", docs=None):
        self.answer, self.status, self.cost, self.docs = answer, status, cost, docs
        self.calls: list[tuple[str, dict, dict | None]] = []
        self.last_headers: dict = {}

    def post_json(self, path, body, headers=None):
        self.calls.append((path, body, headers))
        if path == V.PATH:
            self.last_headers = {V.COST_HEADER: self.cost} if self.cost else {}
            if self.status != 200:
                return self.status, {"error": "no"}
            return 200, {"content": [{"type": "text", "text": self.answer}], "stop_reason": "end_turn"}
        if path == BI.DOCS_ROUTE and self.docs is not None:
            return self.docs(body)
        raise AssertionError(path)

    def post_stream(self, path, body, headers=None, *, limit, gap=None):
        """The births call streamed (release 1019h's fix round): the gateway's relayed stream, already rebuilt into its
        message (league/events/gw.py `post_stream`, tested on its own in test_events_1019h_architect), as `post_json`."""
        self.stream_args = {"limit": limit, "gap": gap}
        return self.post_json(path, body, headers)


class TheProposer(Validation):
    def test_one_architect_call_its_prompt_and_answer_stored_and_never_asked_twice(self):
        st = self.s.st
        answer = json.dumps({"specs": [self.candidate(f"EVL-B-P{i}", ["1.02"]) for i in range(9)]})
        gw = FakeArchitect(answer)
        sheet = BI.Facts(st, self.AS_OF).facts()
        now = lambda: dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC)  # noqa: E731
        got = BI.propose(st, gw, sheet, night=self.AS_OF, now=now)
        self.assertEqual((got["status"], len(got["proposals"]), got["offered"], got["usd"]), ("ok", BI.K, 9, 0.0042),
                         "at most K specs a night")
        [(path, body, headers)] = gw.calls
        # (Release 1019h, A109: Claude Opus 5.5 at effort low, no sampling parameter; release 1019g's was Haiku 4.5 at
        # temperature 0 with 3000 tokens.)
        self.assertEqual((path, body["model"], body.get("temperature"), body["output_config"], body["max_tokens"],
                          body["system"]),
                         (V.PATH, "claude-opus-5-5", None, {"effort": "low"}, 6000, BI.SYSTEM))
        self.assertTrue(headers[V.REQUEST_HEADER].startswith("evl-births:2026-11-06:"))
        user = body["messages"][0]["content"]
        self.assertIn(json.dumps(sheet, sort_keys=True, separators=(",", ":")), user, "the facts, whole")
        self.assertIn("1.95 of 3.90 used", user)
        row = dict(st.db.execute("SELECT * FROM birth_calls").fetchone())
        self.assertEqual((row["prompt_sha"], row["model"], row["status"], row["answer"], row["usd"]),
                         (BI.prompt_sha(), BI.MODEL, "ok", answer, 0.0042))
        again = BI.propose(st, gw, sheet, night=self.AS_OF, now=now)
        self.assertEqual((again["status"], len(again["proposals"])), ("stored:ok", BI.K))
        self.assertEqual(len(gw.calls), 1, "a night's stored answer is read again, never asked again")

    def test_the_nights_cap_holds_the_call_and_a_refusal_stores_nothing(self):
        st = self.s.st
        sheet = BI.Facts(st, self.AS_OF).facts()
        now = lambda: dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC)  # noqa: E731
        gw = FakeArchitect("{}")
        capped = BI.propose(st, gw, sheet, night=self.AS_OF, now=now, cap=0.001)
        self.assertEqual((capped["status"], gw.calls), ("cap", []))
        self.assertLess(BI.worst_usd(BI.render(sheet, BI.budget(st))), BI.NIGHT_USD, "a real night fits the $0.25 cap")
        # (the gateway's own refusal states no cost: release 1019h's fix round counts a cost the gateway states)
        refused = FakeArchitect("{}", status=403, cost=None)
        self.assertEqual(BI.propose(st, refused, sheet, night=self.AS_OF, now=now)["status"], "no answer")
        self.assertEqual(len(refused.calls), 1, "a 4xx is not asked again")
        self.assertIsNone(st.db.execute("SELECT 1 FROM birth_calls").fetchone(), "no answer, nothing stored")
        self.assertEqual(BI.parse_answer("```json\n[{\"spec\": {\"id\": 1}}]\n```")[1], 1)
        self.assertEqual(BI.parse_answer("not json"), ([], 0))


# ======================================================================================================== registration
class Registration(Validation):
    def docs_route(self, *, committed_at="2026-11-07T02:15:09Z", status=200, refused=None):
        posted = []

        def answer(body):
            posted.append(body)
            if status != 200:
                return status, {"error": "no", "refused": refused}
            return 200, {"ok": True, "committed": True, "path": body["path"], "commit": "d" * 40,
                         "committed_at": committed_at, "lines": len(body["lines"]), "docs_today": 1}
        return answer, posted

    def test_the_night_registers_through_the_docs_route_at_the_later_of_githubs_time_and_the_receipt(self):
        st = self.s.st
        route, posted = self.docs_route()
        specs = [self.candidate("EVL-B-8K-102", ["1.02"]), self.candidate("EVL-B-8K-105", ["1.05"]),
                 self.candidate("EVL-B-8K-203", ["2.03"], seatable=False)]
        gw = FakeArchitect(json.dumps({"specs": specs}), docs=route)
        clock = [dt.datetime(2026, 11, 7, 2, 15, 3, tzinfo=UTC)]
        out = BI.night(st, gw, today=self.AS_OF, now=lambda: clock[0])
        self.assertEqual(out["_status"], "ok", out)
        self.assertEqual((out["accepted"], out["proposed"]), (["EVL-B-8K-102", "EVL-B-8K-203"], 3))
        [body] = posted
        self.assertEqual(body["path"], "docs/births/2026-11-06.jsonl")
        lines = [json.loads(x) for x in body["lines"]]
        self.assertEqual([x["spec"]["id"] for x in lines], ["EVL-B-8K-102", "EVL-B-8K-203"])
        self.assertEqual(lines[0]["sha"], BI.sha(specs[0]["spec"]))
        self.assertEqual((lines[0]["why"], lines[0]["by"], lines[0]["prompt_sha"]),
                         ("EVL-B-8K-102 in one line", f"architect:{BI.MODEL}", BI.prompt_sha()))
        self.assertEqual(body["lines"][0], json.dumps(lines[0], sort_keys=True, separators=(",", ":")), "canonical lines")
        rows = [dict(r) for r in st.db.execute("SELECT * FROM births ORDER BY seq")]
        self.assertEqual([(r["id"], r["registered_at"], r["committed_at"], r["received_at"], r["commit_sha"])
                          for r in rows],
                         [("EVL-B-8K-102", "2026-11-07T02:15:09Z", "2026-11-07T02:15:09Z", "2026-11-07T02:15:03Z", "d" * 40),
                          ("EVL-B-8K-203", "2026-11-07T02:15:09Z", "2026-11-07T02:15:09Z", "2026-11-07T02:15:03Z", "d" * 40)],
                         "GitHub's commit time, later than the House's receipt here")
        self.assertEqual([p.id for p in P.BIRTHS], ["EVL-B-8K-102", "EVL-B-8K-203"])
        self.assertEqual(out["budget"]["used"], 2.08, "1.95 and the one seatable birth's 0.13 (PREREG-EVL-6 section 5)")
        statuses = {r["id"]: r["status"] for r in st.db.execute("SELECT id, status FROM birth_candidates")}
        self.assertEqual(statuses, {"EVL-B-8K-102": "registered", "EVL-B-8K-105": "refused",
                                    "EVL-B-8K-203": "registered"})
        figures = json.loads(st.db.execute("SELECT figures FROM birth_candidates WHERE id='EVL-B-8K-105'").fetchone()[0])
        self.assertEqual((figures["selected"], figures["per_session"], figures["charge"]), (40, 2.0, 0),
                         "each candidate's outcome-free figures kept beside its verdict")
        self.assertEqual(out["counts"]["EVL-B-8K-102"]["selected"], 80)
        receipt = st.db.execute("SELECT status FROM receipts WHERE job='births'").fetchone()
        self.assertEqual(receipt[0], "ok")
        # The House's own receipt is later than GitHub's time: the later one is the registration.
        clock[0] = dt.datetime(2026, 11, 8, 2, 20, tzinfo=UTC)
        later = BI.register(st, gw, [{"spec": BI.canonical(spec("EVL-B-LATE", "8k", {"items": ["3.01"]})),
                                      "sha": BI.sha(spec("EVL-B-LATE", "8k", {"items": ["3.01"]})), "line": "{}"}],
                            night=dt.date(2026, 11, 7), now=lambda: clock[0])
        self.assertEqual(later["registered_at"], "2026-11-08T02:20:00Z")

    def test_an_answer_that_never_came_is_posted_again_and_registered_when_it_stands(self):
        st = self.s.st
        lost, posted = self.docs_route(status=502, refused="no_answer")
        gw = FakeArchitect(json.dumps({"specs": [self.candidate("EVL-B-8K-102", ["1.02"])]}), docs=lost)
        out = BI.night(st, gw, today=self.AS_OF, now=lambda: dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC))
        self.assertEqual((out["_status"], out["registration"]["status"]), ("partial", "unknown"))
        self.assertIsNone(st.db.execute("SELECT 1 FROM births").fetchone(), "not registered without a receipt")
        self.assertEqual(st.db.execute("SELECT status FROM birth_candidates").fetchone()[0], "unknown")

        def standing(body):
            posted.append(body)
            return 200, {"ok": True, "committed": False, "unchanged": True, "path": body["path"], "commit": "e" * 40,
                         "committed_at": "2026-11-08T01:00:00Z", "lines": len(body["lines"])}
        gw.docs = standing
        nxt = BI.night(st, gw, today=dt.date(2026, 11, 9), now=lambda: dt.datetime(2026, 11, 10, 2, 15, tzinfo=UTC),
                       proposals=[])
        self.assertEqual(nxt["reconciled"][0]["status"], "unchanged")
        self.assertEqual(posted[1]["lines"], posted[0]["lines"], "the very same lines, to the same night's file")
        self.assertEqual(posted[1]["path"], "docs/births/2026-11-06.jsonl")
        row = dict(st.db.execute("SELECT * FROM births").fetchone())
        self.assertEqual((row["id"], row["registered_at"], row["commit_sha"]),
                         ("EVL-B-8K-102", "2026-11-10T02:15:00Z", "e" * 40),
                         "the later of the file's latest commit and this receipt: never earlier than the true time")
        self.assertEqual(st.db.execute("SELECT status FROM birth_candidates WHERE night='2026-11-06'").fetchone()[0],
                         "registered")

    def test_a_refusal_registers_nothing_and_a_dry_run_posts_nothing(self):
        st = self.s.st
        no, posted = self.docs_route(status=403, refused="path")
        gw = FakeArchitect(json.dumps({"specs": [self.candidate("EVL-B-8K-102", ["1.02"])]}), docs=no)
        out = BI.night(st, gw, today=self.AS_OF, now=lambda: dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC))
        self.assertEqual(out["registration"]["status"], "refused")
        self.assertIsNone(st.db.execute("SELECT 1 FROM births").fetchone())
        dry = BI.night(st, gw, today=dt.date(2026, 11, 9), now=lambda: dt.datetime(2026, 11, 10, 2, tzinfo=UTC),
                       proposals=[{"spec": spec("EVL-B-8K-203", "8k", {"items": ["2.03"]}), "why": "the captain's"}],
                       dry_run=True)
        self.assertEqual((dry["accepted"], len(posted)), (["EVL-B-8K-203"], 1), "validated, never posted")
        self.assertEqual(st.db.execute("SELECT by FROM birth_candidates WHERE id='EVL-B-8K-203'").fetchone()[0], "captain")


# ======================================================================================================== the screen
class TheScreen(unittest.TestCase):
    def test_a_seatable_birth_is_judged_by_preregevl6_and_a_superseded_version_by_preregevl3s_looks(self):
        """PREREG-EVL-6 section 1.1 (release 1019i): a seatable birth registered after REGISTERED_AT_6 is judged by
        PREREG-EVL-6 alone (`_run_v6`); a version it supersedes keeps PREREG-EVL-3's looks as a shadow record
        (`_run_v2`, moving no band: D7); a record or a control is never screened."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(unload)
        s = Synth(Path(tmp.name))
        self.addCleanup(s.st.close)
        s.register(spec("EVL-B-ERN-TOP", "ern", {"score_min": 3}, rank="score"), "2026-11-03T01:00:00Z")
        s.register(spec("EVL-B-REC", "8k", {"items": ["5.02"]}, seatable=False), "2026-11-03T01:00:00Z", seq=1)
        P.load_births(s.st)
        keys = [("EVL-B-ERN-TOP", 1), ("EVL-B-ERN-TOP-CTRL", 1), ("EVL-B-REC", 1), ("EVL-ERN-READ-O1", 2)]
        with mock.patch.object(SN, "_run_v2", return_value={"written": [], "waiting": []}) as v2, \
                mock.patch.object(SN, "_run_v6", return_value={"written": [], "waiting": []}) as v6, \
                mock.patch.object(SN, "_run_v1", return_value={"written": [], "waiting": []}) as v1:
            SN.run(s.st, dt.date(2026, 11, 20), programs=keys, now=dt.datetime(2026, 11, 21, tzinfo=UTC))
        self.assertEqual([c.args[1:3] for c in v6.call_args_list], [("EVL-B-ERN-TOP", 1)])
        self.assertEqual([c.args[1:3] for c in v2.call_args_list], [("EVL-ERN-READ-O1", 2)])
        self.assertEqual(v1.call_args_list, [])
        self.assertEqual(SN.V2_ALPHA, 0.018, "the judge is PREREG-EVL-3's, unchanged")


# ======================================================================================================== the House's book
class TheBook(unittest.TestCase):
    def test_a_seated_birth_buys_at_learning_size_after_every_prereg_program_in_rooms_order(self):
        from league.equity import live as L
        from league.events import book as EB
        from league.tests import test_events_book as TB

        case = TB.EventTest("run")
        case.setUp()
        self.addCleanup(case.tmp.cleanup)
        self.addCleanup(unload)
        h = case.harness()
        self.addCleanup(h.state.close)
        self.addCleanup(h.lane.st.close)
        sp = spec("EVL-B-8K-502", "8k", {"items": ["5.02"]})
        text = BI.canonical(sp)
        h.lane.st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                             "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                             "'docs/births/2026-11-02.jsonl', ?, 0, '{}', 'x', 'captain', '2026-11-02')",
                             (sp["id"], BI.sha(sp), text, "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
                              "2026-11-03T01:00:00Z", "c" * 40))
        TB.earnings(h.lane, "b-1", TB.CIK2, "BRTH", items=("5.02",))      # 5.02: no PREREG program reads it
        birth = P.load_births(h.lane.st)[0]
        self.assertIs(EB.program_of(sp["id"], 1), birth)
        self.assertIsNone(EB.program_of("EVL-ERN-READ-O1", 1), "a PREREG version 1 still never trades")
        h.lane.intent(birth, "8k:b-1", "BRTH", TB.CIK2, TB.DAY, TB.DAY)
        case.ready(h)
        h.symbol("BRTH", last=17.0, sd=0.02)
        h.venue.prints[("BRTH", TB.DAY.isoformat(), "open")] = D("17.00")
        h.tick(9, 15)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["program"], buy["version"], buy["band"], buy["tif"], buy["limit_px"], buy["exit_at"]),
                         (sp["id"], 1, "learning", "opg", "20.00", "close"))
        inst = h.book._instance(L.instance_key(sp["id"], 1))
        self.assertEqual((inst.kind, inst.band, inst.live), ("event", "learning", True))
        self.assertEqual(len([i for i in h.book._instances() if i.kind == "event"]), 16, "the fifteen and the birth")
        h.tick(9, 16)
        [body] = h.bodies()
        self.assertEqual((body["symbol"], body["qty"], body["time_in_force"]), ("BRTH", "2", "opg"),
                         "2% of E=$2,000 at the $20.00 limit: two whole shares, like any version 2 program")
        h.tick(9, 31)
        h.tick(9, 33)
        self.assertEqual([(f["program"], f["version"], f["side"], f["band"]) for f in h.lane.fills()],
                         [(sp["id"], 1, "buy", "learning")], "its fill handed back to the lane at its own version")
        self.assertGreater(EB.room_key(sp["id"], "learning"), EB.room_key("EVL-NEWS-REACT-ON", "learning"),
                           "a birth at learning comes after every PREREG program (R3-SPEC section 4)")
        self.assertGreater(EB.room_key(sp["id"], "sized"), EB.room_key("EVL-NEWS-NIGHT2-ON", "sized"),
                           "a promoted birth comes after its band's PREREG rows (R3-SPEC section 4 as A97 amends it)")
        self.assertLess(EB.room_key(sp["id"], "sized"), EB.room_key("EVL-ERN-READ-O1", "probe"),
                        "... and before every lower band's row (A97, PL-2: release 1019h)")
        self.assertEqual(EB.room_key("EVL-NEWS-REACT-ON", "sized"), (0, 8), "the PREREG keys are as before")


# ======================================================================================================== the House's lane
class TheNight(TH.LaneCase):
    def night(self, **settings) -> list:
        self.lane = self.new_lane(**settings)
        self.at(TH.et("2026-10-20", "20:31"))
        with self.store() as st:
            for kind, t in (("open", "09:15"), ("close", "15:46")):
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=TH.et("2026-10-20", t))
                st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", t))
            st.set_meta(TH.SC.equity_key(dt.date(2026, 10, 20)), repr(2000.0))
        self.lane._redecide_next = TH.et("2026-10-21", "00:00")
        tasks = []
        for when in ("20:31", "20:32", "20:33", "21:10", "21:16", "21:17"):
            self.at(TH.et("2026-10-20", when))
            self.mark_recorded()
            tasks.append(self.turn().get("task"))
        return tasks

    def test_the_births_job_runs_once_after_the_report_at_2115_when_switched_on(self):
        self.addCleanup(unload)
        tasks = self.night(births=True)
        self.assertEqual(tasks[:3], ["score", "screen", "report"])
        self.assertEqual(tasks[4], "births")
        self.assertNotEqual(tasks[3], "births", "not before 21:15 ET")
        [receipt] = self.receipts("births")      # once a night (the turn after it ran no births task)
        self.assertEqual(receipt["status"], "ok")
        self.assertEqual(json.loads(receipt["summary"])["night"], "2026-10-20")
        [call] = [c for c in self.gw.claude_calls if c.get("system") == BI.SYSTEM]
        # (Release 1019h, A109: the architect is Claude Opus 5.5, which takes no temperature; effort low.)
        self.assertEqual((call["model"], call.get("temperature"), call["output_config"]),
                         ("claude-opus-5-5", None, {"effort": "low"}))

    def test_off_by_default(self):
        self.assertNotIn("births", self.night())
        self.assertEqual(self.receipts("births"), [])


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
