"""PREREG-EVL-10's READER-2 (R2), its seat EVL-R2-ON, its control and its two free records, and the decision scheduler
it needs, on INVENTED rows only (no figure here is a market's; no House or desktop store is opened; no metered call:
the reader's own code path runs against a fake gateway). One test a clause of the frozen text (docs/prereg/
PREREG-EVL-10.md on the tag `prereg-evl-10`; THE FROZEN TEXT WINS):

- THE FREEZE: REGISTERED_AT_10 pinned and tied to the frozen file's sha256 and its 129-file record; the request spec
  verbatim from docs/prereg/evl-10/fix1/r2_spec.py and its two shas; births.RESERVED's 0.13 released at the pin and the
  screen's own count holding it (section 4); the rows (section 2) after every earlier row and R3's births;
- WHAT A READ SEES AND WHAT QUALIFIES (sections 1.2, 1.4): NEWS-ON and 8K-ON as stored at the scan, BUYABLE, LIQUID,
  EXCLUDED, the text's length, v1's scores, the registration time; the hash share, the caps, COMPLETE and q;
- THE ASKS (sections 1.3, 1.5): one stored row each and final, the statuses, a call refused before sending storing
  nothing, THE PIN, THE SCHEMA STOP, THE DAY STOP, R2_LINE and the cap hold (no ask when the line is spent or a cap
  hold names the day), the lane's line counting R2's dollars;
- THE DECISION AND THE ONE READING (sections 2.1-2.4): the filter, the key, the picks and rank_key, the control and the
  records, the E10 bar, FEATURES-R2 v1, one transaction with its receipt; THE LOOK-AHEAD TEST (a read answered after tau
  and an 8-K stored after it change nothing, for the shadow, the book's picks at 15:46 and META's members alike);
- THE HOUSE (section 1.5, 2.4): the slot at 15:40 in its own run, before the lane's close decision, which keeps its time;
  R2's own lane; THE BOOK (section 2.5): ROOM after every earlier pass, the learners' and the births' included, no buy
  when evl7's receipt comes at 15:48:20, the window row, the per-program rules (a)-(d) and A85's reservation;
- THE JUDGE (section 3): PREREG-EVL-6 as frozen with EVL-R2-ON-SET its control, its finality, a run refused when the
  budget cannot hold it and never more than three;
- THE PROOF (the task's item 4): every earlier program's shadow intents, real-money picks and the House's receipts are
  the same with and without this file on an invented week, and the same as on main (a recorded fixture);
- the report's READER block (counts only) and the alarms; births' facts refusing R2's tables."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.equity import live as L
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import gw as G
from league.events import house as H
from league.events import programs as P
from league.events import reader2 as R2
from league.events import scheduler as X
from league.events import screen as SN
from league.events import store as S
from league.events import verdicts as V
from league.tests import test_events_evl7 as T7

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "docs" / "prereg" / "PREREG-EVL-10.md"
SPEC = REPO / "docs" / "prereg" / "evl-10" / "fix1" / "r2_spec.py"
D_DAY, P_DAY, N_DAY = dt.date(2026, 10, 26), dt.date(2026, 10, 23), dt.date(2026, 10, 27)   # Mon, Fri before, Tue
et = T7.et


def frozen_spec():
    """The frozen request spec, run from the tag's copy in the tree (docs/prereg/evl-10/fix1/r2_spec.py) in a module of
    its own, compiled from its text so that no bytecode is written beside the frozen record."""
    import types

    module = types.ModuleType("r2_spec_frozen")
    module.__dict__["__name__"] = "r2_spec_frozen"
    exec(compile(SPEC.read_text(encoding="utf-8"), str(SPEC), "exec"), module.__dict__)
    return module


NEWS_OK = {"type": "contract_product", "new": 2, "corroborated": 1, "price_story": False, "consensus": "not_stated",
           "vs_own_guidance": "not_stated", "magnitude": 2, "specific": 1, "surprise": 2, "p_up": 70}
DOC_OK = {"type": "material_contract", "routine": False, "material": 2, "new": 2, "corroborated": 1,
          "consensus": "not_stated", "vs_own_guidance": "raised", "guide_chg_pct": 2.5, "dilution": False,
          "one_offs": False, "magnitude": 2, "specific": 2, "tone": 1, "surprise": 2, "p_up": 65}


class Gateway:
    """The gateway's `/v1/claude/messages` as R2 calls it (`post_stream`), answering each event's text with the fields
    `answers` gives (by the item's headline or the document's first characters), `stop` and `model` as set; or one of
    the failures a test names. No call leaves the process."""

    def __init__(self, answers=None, *, model: str = R2.PIN, cost: str | None = "0.0071"):
        self.answers = dict(answers or {})
        self.model = model
        self.cost = cost
        self.calls: list[dict] = []
        self.last_headers: dict[str, str] = {}
        self.fail: BaseException | None = None
        self.code = 200
        self.stop = "end_turn"
        self.text: str | None = None

    def post_stream(self, path, body, headers=None, *, limit, gap=None, clock=None):
        self.calls.append({"path": path, "body": body, "headers": dict(headers or {}), "limit": limit, "gap": gap})
        self.last_headers = {} if self.cost is None else {G.COST_HEADER: self.cost}
        if self.fail is not None:
            raise self.fail
        if self.code != 200:
            self.last_headers = {}          # (an error the gateway did not settle at a cost)
            return self.code, {"error": "invented"}
        user = body["messages"][0]["content"]
        fields = next((f for k, f in self.answers.items() if k in user), None)
        kind = "doc" if user.startswith("Company:") else "news"
        fields = fields if fields is not None else (DOC_OK if kind == "doc" else NEWS_OK)
        text = self.text if self.text is not None else json.dumps(fields)
        return 200, {"model": self.model, "content": [{"type": "text", "text": text}], "stop_reason": self.stop,
                     "usage": {"input_tokens": 1356, "output_tokens": 375}}


class World(T7.World):
    """test_events_evl7's invented lane store (the NYSE sessions of Sep-Dec 2026, an equity of $10,000 at every close),
    with R2's own rows: issuers whose live eligibility is decided at 07:00 ET, day-news articles, 8-Ks with a TEXT of
    their own, and v1's verdicts."""

    def uni(self, day: dt.date, symbol: str, cik: str, *, prev: float = 20.0, adv: float = 2e7,
            decided: dt.datetime | None = None, eligible: bool = True) -> None:
        self.universe(day, symbol, cik, prev_close=prev, adv20=adv, decided=decided or et(day, 7, 0))
        if not eligible:
            self.st.db.execute("UPDATE eligibility SET eligible=0 WHERE day=? AND cik=?", (day.isoformat(), cik))

    def news_item(self, ident: str, symbol: str, *, knowable: dt.datetime, score: int | None, answered=None,
                  headline: str | None = None, received: dt.datetime | None = None, symbols=None) -> str:
        ev = self.article(ident, symbol, knowable=knowable, received=received, headline=headline or f"{ident} headline",
                          symbols=symbols)
        if score is not None:
            self.verdict(ev, score, answered=answered or knowable + dt.timedelta(minutes=2))
        return ev

    def eight_k(self, accession: str, cik: str, *, knowable: dt.datetime, score: int | None, items=("8.01",),
                text: str | None = None, stored: dt.datetime | None = None, guidance: str = "none",
                answered=None) -> str:
        body = (text if text is not None else f"{accession}: the company signed an invented agreement. " * 10).encode()
        sha = self.st.put_document(body, "text", now=stored or knowable)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, text_sha, text_len, raw_sha, status) VALUES(?, '8-K', ?, 'Invented Co', "
                           "?, ?, ?, ?, 'current', ?, ?, ?, 'fetched')",
                           (accession, cik, json.dumps(list(items)), S.iso(knowable - dt.timedelta(minutes=10)),
                            S.iso(knowable), S.iso(stored or knowable), sha, len(body), sha))
        ev = f"8k:{accession}"
        if score is not None:
            self.verdict(ev, score, answered=answered or knowable + dt.timedelta(minutes=3), guidance=guidance)
        return ev

    def scans(self, day: dt.date, *, start: dt.datetime | None = None, every: int = 90,
              until: dt.datetime | None = None) -> None:
        """Scans of `day` every `every` seconds (each its own `R2.scan`)."""
        s = self.session(day)
        t = start or (R2.start_of(s) + dt.timedelta(seconds=70))
        end = until or R2.ask_until(s)
        while t <= end:
            R2.scan(self.st, day, t)
            t += dt.timedelta(seconds=every)


class Lane:
    """What `R2.job` reads of the House's event lane: its store's root, its clock, its line and its warnings."""

    def __init__(self, root: Path, gw: Gateway, clock: list, *, line: float = 3.0):
        self.root = root
        self.gw = gw
        self.clock = clock
        self.line = line
        self._paused = False
        self.warned: list[tuple[str, str]] = []

    def ready(self) -> bool:
        return True

    def now(self) -> dt.datetime:
        return self.clock[0]

    def verdict_line(self, now):
        return {"usd_day": self.line, "source": "invented"}

    def gateway(self):
        return self.gw

    def warn(self, task, text):
        self.warned.append((task, str(text)))


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = World(Path(self.tmp.name) / "events")
        self.addCleanup(self.w.close)
        self.st = self.w.st
        self.s = self.w.session(D_DAY)
        self.tau = R2.tau(self.s)

    def issuer(self, *, prev: float = 20.0, adv: float = 2e7, **kw) -> tuple[str, str]:
        cik, symbol = self.w.issuer()
        self.w.uni(D_DAY, symbol, cik, prev=prev, adv=adv, **kw)
        return cik, symbol

    def read_all(self, gw: Gateway, at: dt.datetime | None = None, *, step: int = 1) -> list[dict]:
        """Every due call of D asked now (`next_due` then `ask`), each `step` seconds after the one before."""
        out = []
        t = [at or et(D_DAY, 14, 0)]
        while True:
            due = R2.next_due(self.st, D_DAY, self.s)
            if due is None:
                return out

            def now(t=t):
                return t[0]
            out.append(R2.ask(self.st, gw, due, D_DAY, now=now))
            t[0] += dt.timedelta(seconds=step)

    def receipt(self, at: dt.datetime | None = None) -> int:
        when = at or self.tau + dt.timedelta(seconds=5)
        return self.st.start_receipt(f"{R2.JOB}:{D_DAY.isoformat()}", now=when)

    def decide(self, at: dt.datetime | None = None) -> dict:
        when = at or self.tau + dt.timedelta(seconds=5)
        rid = self.receipt(when)
        return R2.decide(self.st, D_DAY, now=when, rid=rid)

    def intents(self, program: str) -> list[tuple]:
        return [tuple(r) for r in self.st.db.execute("SELECT event, symbol, cik, rank_key, decided_at, entry_day, exit_day, "
                                                     "entry_at, exit_at, status FROM intents WHERE program=? ORDER BY "
                                                     "rank_key DESC, event", (program,))]


# --------------------------------------------------------------------------------------------------------- the freeze
class TheFreeze(unittest.TestCase):
    def test_registered_at_10_is_a144s_and_names_the_frozen_file_and_its_record(self):
        """A144: REGISTERED_AT_10 is the latest of the commit's 07:10:41Z, GitHub's 07:10:43Z and the client's 07:10:45Z;
        the tag's file is in the tree byte for byte (sha256 ab7e587c) with its 129-file record, every file its
        SHA256SUMS.all lists, and no other."""
        self.assertEqual(P.REGISTERED_AT_10, "2026-10-23T07:10:45Z")
        self.assertEqual(hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
                         "ab7e587cf35fcb9ae598a5089208c02a28ca89f2a08fe5fd77202900103c6207")
        root = FROZEN.parent / "evl-10"
        listed = {}
        for line in (root / "SHA256SUMS.all").read_text().splitlines():
            if line.strip():
                digest, name = line.split(None, 1)
                listed[name.strip().lstrip("*").removeprefix("./")] = digest
        for name, digest in listed.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
        files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(files, set(listed) | {"SHA256SUMS.all"}, "every file listed, no other")
        self.assertEqual(len(files), 129, "A144: 129 files")
        self.assertLess(S.parse_iso(P.REGISTERED_AT_7), S.parse_iso(P.REGISTERED_AT_10))

    def test_the_request_spec_is_the_fix_rounds_verbatim_and_its_shas_are_section_11s(self):
        """Section 1.1: the fix round's r2_spec.py (sha256 fd5c040e) copied verbatim between the module's two markers;
        the two request shas recomputed: R2-NEWS a8239614..., R2-DOC 127c19f3..."""
        frozen = SPEC.read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(frozen.encode()).hexdigest(),
                         "fd5c040e739f433c013c86f49caf70f2645d87015d6c645ab04b049b42d82a28")
        mine = (REPO / "league" / "events" / "reader2.py").read_text(encoding="utf-8")
        begin, end = "VERBATIM: BEGIN\n", "\n# ===================================== THE FROZEN REQUEST SPEC"
        block = mine[mine.index(begin) + len(begin):mine.index(end, mine.index(begin))]
        theirs = frozen[frozen.index('MODEL = "claude-sonnet-5-5"'):frozen.index('\nif __name__ == "__main__":')]
        self.assertEqual(block.rstrip("\n"), theirs.rstrip("\n"), "the block is the frozen file's, byte for byte")
        F = frozen_spec()
        for kind in R2.KINDS:
            self.assertEqual(R2.spec(kind), F.spec(kind))
            self.assertEqual(R2.sha(kind), F.sha(kind))
            self.assertEqual(R2.sha(kind), R2.SHAS[kind])
        self.assertEqual(R2.SHAS, {"news": "a82396145a28dd4d98d6878e515cc26c26fd70c6c29f2642d4e1c4241642d694",
                                   "doc": "127c19f36f3811afaf4401c35e7620618a27ca0eb32795d0b19ba45a87522c5b"})
        self.assertEqual((R2.MODEL, R2.PIN), ("claude-sonnet-5-5", "claude-sonnet-5-5"), "A144's pin")
        body = R2.body("news", "x")
        self.assertNotIn("temperature", body)
        self.assertEqual((body["stream"], body["thinking"], body["output_config"]["effort"]),
                         (True, {"type": "adaptive", "display": "omitted"}, "low"))
        self.assertEqual(R2.h("ON", "2026-10-26", "0000000001"),
                         int.from_bytes(hashlib.sha256(b"R2|ON|2026-10-26|0000000001").digest()[:8], "big") / 2 ** 64)
        self.assertEqual((R2.share([]), R2.share([10, 12]), R2.share([80, 80])), (0.5, 1.0, 0.5))

    def test_the_charge_is_counted_once_reserved_released_and_held_by_the_screens_count(self):
        """Section 4: c10 = 0.13 through the screen's own count (EVL-R2-ON is a PREREG-EVL-6 version in SEATING), and
        births.RESERVED's PREREG-EVL-10 hold released at the pin, so the lane's sum is the same 3.81 either way."""
        from league.tests import evl10_fakes as F10

        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp) / "events")
            try:
                pinned = SN.budget6(st)["used"] + BI.budget_reserved_hundredths()
                self.assertIn(P.BY_KEY[(P.R2_ON, 1)], SN._v6_programs())
                with F10.unpinned_10():
                    self.assertNotIn(P.R2_ON, {p.id for p in P.SEATING})
                    unpinned = SN.budget6(st)["used"] + BI.budget_reserved_hundredths()
                    self.assertEqual(BI.budget_reserved_hundredths(), 65 + 30 + 13, "the hold while unpinned")
            finally:
                st.close()
        self.assertEqual(BI.budget_reserved_hundredths(), 65 + 30, "released at the pin")
        self.assertEqual(pinned, unpinned, "0.13 counted once: the screen's count holds what RESERVED released")
        self.assertIn(("PREREG-EVL-10", "REGISTERED_AT_10", 13), BI.RESERVED)


class TheRows(unittest.TestCase):
    def test_four_rows_after_every_earlier_row_and_the_births_evl6_on_the_seat_only(self):
        rows = P.reader2_rows()
        self.assertEqual([p.id for p in rows], ["EVL-R2-ON", "EVL-R2-ON-SET", "REC-R2-ON-PASS", "REC-R2-ON-AVOID"])
        for p in rows:
            self.assertEqual((p.version, p.entry_at, p.exit_at, p.hold, p.prereg, p.family),
                             (1, "close", "open", 1, 10, "reader2"))
            self.assertEqual(p.registered_at, S.parse_iso("2026-10-23T07:10:45Z"))
        on = P.BY_KEY[(P.R2_ON, 1)]
        self.assertTrue(on.seatable and on.can_seat and on.evl6 and on.reads)
        self.assertEqual([p.evl6 or p.can_seat for p in rows[1:]], [False, False, False], "never seated, never judged")
        self.assertEqual(P.SEATING[-1], on, "after every earlier file's seat and R3's births")
        self.assertEqual(P.PROGRAMS[-4:], rows)
        self.assertEqual(EB.settings().max_open("probe", on), 14, "section 2.5 (a)-(b): 14 Probe slots")
        self.assertEqual(SN.CONTROLS[P.R2_ON], P.R2_SET)
        self.assertEqual(P.SEATING_PREREGS, (3, 4, 5, 10))
        self.assertEqual(R2.meta_sources(), ("EVL-R2-ON", "EVL-R2-ON-SET", "REC-R2-ON-PASS", "REC-R2-ON-AVOID"))

    def test_unpinned_nothing_of_this_file_is_in_any_registry_or_runs(self):
        from league.tests import evl10_fakes as F10

        with F10.unpinned_10():
            self.assertEqual(P.reader2_rows(), ())
            self.assertFalse(any(P.is_reader2(p) for p in P.PROGRAMS + P.SEATING))
            self.assertFalse(R2.pinned())
            self.assertNotIn("evl10", [s.file for s in X.live_files("close")])
            self.assertEqual(R2.job(Lane(Path("/nonexistent"), Gateway(), [et(D_DAY, 10, 0)])),
                             {"skipped": "PREREG-EVL-10 is not pinned"})
        self.assertEqual([s.file for s in X.live_files("close")], ["evl10"])

    def test_the_rows_are_decided_only_by_their_slot_never_by_the_houses_decisions(self):
        import inspect

        from league.events import run as R

        self.assertIn("P.R2_FAMILIES", inspect.getsource(R.decide_open))
        self.assertIn("P.R2_FAMILIES", inspect.getsource(R.decide_close))
        self.assertEqual(X.file_of(P.R2_ON), "evl10")
        self.assertEqual([X.file_of(p) for p in P.reader2_rows()], ["evl10"] * 4)
        self.assertEqual({X.file_of(p) for p in P.SEATING if not P.is_reader2(p)}, {"main"})


# ------------------------------------------------------------------------------------------------- what qualifies
class TheQualification(Case):
    def test_news_on_and_8k_on_as_stored_at_the_scan(self):
        """Section 1.4: a DAY(D) article of an eligible, liquid, BUYABLE issuer with a stored ok PROMPT-NEWS score >= 2;
        an F8K(D) filing of an issuer not EXCLUDED with a 200-character TEXT and a stored ok PROMPT-DOC score <= 1."""
        a, sa = self.issuer()
        b, sb = self.issuer(adv=9_999_999.0)                       # not LIQUID
        c, sc = self.issuer(prev=401.0)                            # 1.25 x 401 > 0.05 x 10,000: not BUYABLE
        d, sd = self.issuer(eligible=False)                        # its live eligibility: ineligible
        e, se = self.issuer(decided=et(D_DAY, 12, 0))              # its eligibility decided only at 12:00 ET
        f, sf = self.issuer()
        g, sg = self.issuer()
        k, sk = self.issuer()
        good = self.w.news_item("n-a", sa, knowable=et(D_DAY, 9, 30), score=2)
        self.w.news_item("n-a1", sa, knowable=et(D_DAY, 8, 59), score=3)          # before 09:00 ET: not DAY(D)
        self.w.news_item("n-a2", sa, knowable=et(D_DAY, 10, 0), score=1)          # score 1
        for x, sx in ((b, sb), (c, sc), (d, sd), (e, se)):
            self.w.news_item(f"n-{sx}", sx, knowable=et(D_DAY, 9, 40), score=3)
        doc = self.w.eight_k("acc-f", f, knowable=et(D_DAY, 8, 0), score=1)
        self.w.eight_k("acc-f2", f, knowable=et(D_DAY, 8, 5), score=2)            # score 2: v1's own rows take it
        self.w.eight_k("acc-g", g, knowable=et(D_DAY, 8, 0), score=0, text="short")  # under 200 characters
        self.w.eight_k("acc-k", k, knowable=et(D_DAY, 8, 0), score=0, items=("2.02",))  # earnings: not F8K(D)
        self.w.eight_k("acc-k2", k, knowable=et(D_DAY, 8, 1), score=0)            # k is EXCLUDED (ERN(D))
        got = {c_["event"]: c_["kind"] for c_ in R2.qualify(self.st, D_DAY, et(D_DAY, 11, 0))}
        self.assertEqual(got, {good: "news", doc: "doc"})
        later = {c_["event"] for c_ in R2.qualify(self.st, D_DAY, et(D_DAY, 12, 30))}
        self.assertIn(f"news:n-{se}", later, "qualifies once its eligibility is stored")
        self.assertNotIn(good, {c_["event"] for c_ in R2.qualify(self.st, D_DAY, et(D_DAY, 9, 31))},
                         "its verdict is answered at 09:32: not yet")

    def test_an_issuer_with_a_day_news_article_is_excluded_from_8k_on_and_registration_bounds_every_event(self):
        a, sa = self.issuer()
        doc = self.w.eight_k("acc-a", a, knowable=et(D_DAY, 8, 0), score=0)
        self.assertEqual([c["event"] for c in R2.qualify(self.st, D_DAY, et(D_DAY, 9, 0))], [doc])
        self.w.news_item("n-a", sa, knowable=et(D_DAY, 9, 30), score=-1)          # DAY(D) whatever its score
        self.assertEqual([c["event"] for c in R2.qualify(self.st, D_DAY, et(D_DAY, 10, 0))], [])
        b, sb = self.issuer()
        early = et(P_DAY, 2, 0)                                                     # before REGISTERED_AT_10
        self.w.uni(P_DAY, sb, b)
        self.w.eight_k("acc-b", b, knowable=early, score=0)
        self.assertEqual(R2.qualify(self.st, P_DAY, et(P_DAY, 11, 0)), [], "knowable before the registration: none")

    def test_no_e_prev_no_qualification(self):
        a, sa = self.issuer()
        self.w.news_item("n-a", sa, knowable=et(D_DAY, 9, 30), score=3)
        self.st.db.execute("DELETE FROM meta WHERE key LIKE 'equity:%'")
        self.assertEqual(R2.qualify(self.st, D_DAY, et(D_DAY, 11, 0)), [], "fail closed")


class TheChoice(Case):
    def q_issuers(self, q: float):
        """Issuers whose hash draw is under and over `q`."""
        low = high = None
        while low is None or high is None:
            cik, symbol = self.issuer()
            hh = R2.h("ON", D_DAY.isoformat(), cik)
            if hh < q and low is None:
                low = (cik, symbol)
            elif hh >= q and high is None:
                high = (cik, symbol)
        return low, high

    def test_the_hash_share_the_score_3_rule_and_the_second_read(self):
        """(i) the first qualifying article when h < q, or else the first of score 3; (ii) once more for the first later
        one strictly higher than (i)'s; never a third."""
        self.st.set_meta(R2.Q_KEY.format(day=D_DAY.isoformat()), json.dumps({"q": 0.5}))
        (lc, ls), (hc, hs) = self.q_issuers(0.5)
        l1 = self.w.news_item("l1", ls, knowable=et(D_DAY, 9, 10), score=2)
        l2 = self.w.news_item("l2", ls, knowable=et(D_DAY, 9, 20), score=2)
        l3 = self.w.news_item("l3", ls, knowable=et(D_DAY, 9, 30), score=3)
        l4 = self.w.news_item("l4", ls, knowable=et(D_DAY, 9, 40), score=3)
        h1 = self.w.news_item("h1", hs, knowable=et(D_DAY, 9, 10), score=2)
        h2 = self.w.news_item("h2", hs, knowable=et(D_DAY, 9, 20), score=3)
        h3 = self.w.news_item("h3", hs, knowable=et(D_DAY, 9, 30), score=3)
        for t in (et(D_DAY, 9, 25), et(D_DAY, 10, 0)):
            R2.scan(self.st, D_DAY, t)
        rows = {r["event"]: (r["chosen"], r["q"]) for r in self.st.db.execute("SELECT * FROM r2_qual")}
        self.assertEqual({e: c for e, (c, _) in rows.items()},
                         {l1: 1, l2: 0, l3: 1, l4: 0, h1: 0, h2: 1, h3: 0})
        self.assertEqual({q for _, q in rows.values()}, {0.5}, "q fixed for the session")
        with self.assertRaises(Exception):
            self.st.db.execute("UPDATE r2_qual SET chosen=1 WHERE event=?", (l2,))      # write-once

    def test_the_caps_64_news_and_8_docs_a_session_in_qualification_order(self):
        self.st.set_meta(R2.Q_KEY.format(day=D_DAY.isoformat()), json.dumps({"q": 1.0}))
        news = []
        for i in range(66):
            cik, symbol = self.issuer()
            news.append(self.w.news_item(f"n{i:02d}", symbol, knowable=et(D_DAY, 9, 1) + dt.timedelta(seconds=30 * i),
                                         score=2))
        docs = []
        for i in range(9):
            cik, symbol = self.issuer()
            docs.append(self.w.eight_k(f"acc{i}", cik, knowable=et(D_DAY, 8, 0) + dt.timedelta(minutes=i), score=0))
        got = R2.scan(self.st, D_DAY, et(D_DAY, 10, 0))
        self.assertTrue(got["capped"])
        chosen = [r["event"] for r in self.st.db.execute("SELECT event FROM r2_qual WHERE chosen=1 AND kind='news' "
                                                         "ORDER BY qualified_at, rowid")]
        self.assertEqual(chosen, news[:64], "the session's latest are the ones past the cap")
        self.assertEqual([r[0] for r in self.st.db.execute("SELECT event FROM r2_qual WHERE chosen=1 AND kind='doc' "
                                                           "ORDER BY rowid")], docs[:8])
        self.assertIsNotNone(self.st.meta(R2.CAP_KEY.format(day=D_DAY.isoformat())))

    def test_complete_and_the_share_q(self):
        """COMPLETE (F17): scans from 07:31:10 every 90 s to 15:38:40 make the session COMPLETE; one gap of 5 minutes
        1 second does not. q = min(1, 40 / m) over the last 5 complete sessions, 0.5 with none."""
        s = self.s
        grid = [s.at(dt.time(7, 31, 10)) + dt.timedelta(seconds=90 * i) for i in range(326)]
        self.assertEqual(grid[-1].astimezone(NY).time(), dt.time(15, 38, 40))
        self.assertTrue(R2.complete(grid, s))
        gap = [t for t in grid if not (s.at(dt.time(12, 0)) < t < s.at(dt.time(12, 5, 1)))]
        gap.append(s.at(dt.time(12, 0)))
        gap = sorted(set(gap))
        hole = max(b - a for a, b in zip(gap, gap[1:]))
        self.assertGreater(hole, R2.COMPLETE_GAP)
        self.assertFalse(R2.complete(gap, s))
        self.assertEqual(R2.share_of(self.st, D_DAY), (0.5, []), "no complete session: Q_DEFAULT")
        days = [x.day for x in C.previous(self.st, D_DAY, 6)]
        for n, day in zip((300, 100, 100, 100, 100, 80), days):
            x = self.w.session(day)
            with self.st.tx() as db:
                for t in [x.at(dt.time(7, 31, 10)) + dt.timedelta(seconds=90 * i) for i in range(326)]:
                    db.execute("INSERT INTO r2_scan(day, scanned_at) VALUES(?, ?)", (day.isoformat(), S.iso(t)))
                for i in range(n):
                    db.execute("INSERT INTO r2_qual(window, day, cik, event, kind, qualified_at, v1_score, h, q, chosen) "
                               "VALUES('ON', ?, ?, ?, 'news', ?, 2, 0.5, 0.5, 0)",
                               (day.isoformat(), f"c{i}", f"news:{day}-{i}", S.iso(x.at(dt.time(10, 0)))))
        q, read = R2.share_of(self.st, D_DAY)
        self.assertEqual(read, [d.isoformat() for d in days[1:]], "the last five complete sessions")
        self.assertAlmostEqual(q, 40 / ((100 * 4 + 80) / 5))


# --------------------------------------------------------------------------------------------------------- the asks
class TheAsks(Case):
    def one(self, gw: Gateway, *, kind: str = "news") -> dict:
        cik, symbol = self.issuer()
        if kind == "news":
            self.w.news_item(f"n-{symbol}", symbol, knowable=et(D_DAY, 9, 30), score=3)
        else:
            self.w.eight_k(f"acc-{symbol}", cik, knowable=et(D_DAY, 8, 0), score=0)
        R2.scan(self.st, D_DAY, et(D_DAY, 10, 0))
        due = R2.next_due(self.st, D_DAY, self.s)
        self.assertIsNotNone(due)
        return R2.ask(self.st, gw, due, D_DAY, now=lambda: et(D_DAY, 10, 1))

    def row(self) -> dict:
        rows = [dict(r) for r in self.st.db.execute("SELECT * FROM reads2")]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_an_ok_read_its_body_its_stored_row_and_the_first_stored_row_final(self):
        gw = Gateway()
        got = self.one(gw)
        self.assertEqual(got["status"], "ok")
        [call] = gw.calls
        self.assertEqual((call["path"], call["limit"], call["gap"]), (V.PATH, 90.0, 30.0))
        body = call["body"]
        self.assertEqual(body, R2.body("news", body["messages"][0]["content"]), "section 1.1's body exactly")
        user = body["messages"][0]["content"]
        self.assertIn("Read on 2026-10-26.", user)
        self.assertIn("p_up: the probability", user)
        r = self.row()
        self.assertEqual((r["status"], r["model"], r["prompt_sha"], r["response_model"], r["usd"], r["window"], r["day"]),
                         ("ok", R2.MODEL, R2.SHAS["news"], R2.PIN, 0.0071, "ON", "2026-10-26"))
        self.assertEqual(json.loads(r["fields"]), NEWS_OK)
        self.assertEqual(r["user_sha"], hashlib.sha256(user.encode()).hexdigest())
        self.assertEqual((r["in_tokens"], r["out_tokens"]), (1356, 375))
        self.assertIsNone(R2.next_due(self.st, D_DAY, self.s), "never asked again")
        with self.assertRaises(Exception):
            self.st.db.execute("UPDATE reads2 SET status='unparsed'")                 # the stored answer is final

    def test_the_statuses_unparsed_refused_cut_and_lost_at_the_hold(self):
        for setup, status, usd in ((lambda g: setattr(g, "text", "{not json"), "unparsed", 0.0071),
                                   (lambda g: setattr(g, "stop", "refusal"), "refused", 0.0071),
                                   (lambda g: setattr(g, "stop", "max_tokens"), "cut", 0.0071),
                                   (lambda g: setattr(g, "fail", G.StreamLost("gone quiet")), "lost", R2.HOLD_USD["news"]),
                                   (lambda g: setattr(g, "cost", None), "ok", R2.HOLD_USD["news"])):
            with self.subTest(status=status):
                self.st.db.execute("DELETE FROM reads2")
                self.st.db.execute("DELETE FROM r2_qual")
                gw = Gateway()
                setup(gw)
                self.assertEqual(self.one(gw)["status"], status)
                self.assertEqual((self.row()["status"], self.row()["usd"]), (status, usd), "an unpriced call at its hold")

    def test_a_call_refused_before_sending_stores_nothing_and_three_4xx_stop_the_day(self):
        gw = Gateway()
        gw.fail = G.NotSent("the lane refused it")
        self.assertEqual(self.one(gw)["status"], "not sent")
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM reads2").fetchone()[0], 0)
        self.assertIsNotNone(R2.next_due(self.st, D_DAY, self.s), "it may be asked again")
        gw.fail = None
        gw.code = 403
        due = R2.next_due(self.st, D_DAY, self.s)
        for _ in range(3):
            self.assertEqual(R2.ask(self.st, gw, due, D_DAY, now=lambda: et(D_DAY, 11, 0))["status"], "not sent")
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM reads2").fetchone()[0], 0)
        self.assertEqual(R2.fourxx(self.st, et(D_DAY, 11, 0)), 3)
        lane = Lane(self.w.root / "events", Gateway(), [et(D_DAY, 11, 5)])
        got = R2.job(lane)
        self.assertEqual(got["skipped"], "the day stop")
        self.assertIn("reader_stop", [k for k, _ in lane.warned])
        self.assertEqual(R2.fourxx(self.st, et(N_DAY, 11, 0)), 0, "the next UTC day asks again")

    def test_the_pin_stops_r2_for_good(self):
        gw = Gateway(model="claude-sonnet-5-5-20261101")
        got = self.one(gw)
        self.assertEqual((got["status"], got["pin"]), ("refused", False))
        self.assertEqual(self.row()["response_model"], "claude-sonnet-5-5-20261101")
        self.assertEqual(R2.stopped(self.st)["kind"], "pin")
        cik, symbol = self.issuer()
        self.w.news_item("n-later", symbol, knowable=et(D_DAY, 10, 30), score=3)
        lane = Lane(self.w.root / "events", Gateway(), [et(D_DAY, 11, 0)])
        got = R2.job(lane)
        self.assertEqual(got["stopped"]["kind"], "pin")
        self.assertEqual(lane.gw.calls, [], "R2 asks nothing more")
        self.assertIn("reader_pin", [k for k, _ in lane.warned])
        self.assertIn("reader_pin", [a["kind"] for a in R2.alarms(self.st, et(D_DAY, 11, 0))])

    def test_the_schema_stop_two_consecutive_sessions_of_ten_answered_with_a_tenth_broken(self):
        prior = C.previous(self.st, D_DAY, 2)
        def put(day, n, bad):
            for i in range(n):
                self.st.db.execute("INSERT INTO reads2(event, prompt_sha, model, window, day, asked_at, answered_at, status, "
                                   "usd) VALUES(?, ?, ?, 'ON', ?, '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z', ?, 0.01)",
                                   (f"news:{day}-{i}", R2.sha("news"), R2.MODEL, day.isoformat(),
                                    "unparsed" if i < bad else "ok"))
        put(prior[0].day, 10, 1)
        put(prior[1].day, 9, 9)            # (under ten answered: not judged)
        self.assertEqual(R2.schema_failing(self.st), [])
        put(D_DAY, 20, 2)
        self.assertEqual(R2.schema_failing(self.st), [], "the two failing sessions are not consecutive")
        self.st.db.execute("DELETE FROM reads2 WHERE day=?", (prior[1].day.isoformat(),))
        put(prior[1].day, 10, 1)
        self.assertEqual(R2.schema_failing(self.st), [prior[1].day.isoformat(), D_DAY.isoformat()])
        lane = Lane(self.w.root / "events", Gateway(), [et(D_DAY, 11, 0)])
        self.assertEqual(R2.job(lane)["stopped"]["kind"], "schema")
        self.assertIn("reader_schema", [k for k, _ in lane.warned])

    def test_one_call_a_job_inside_the_window_and_a_read_that_cannot_be_rendered_never_holds_the_queue(self):
        a, sa = self.issuer()
        b, sb = self.issuer()
        self.w.eight_k("acc-a", a, knowable=et(D_DAY, 8, 0), score=0)
        self.w.news_item("n-b", sb, knowable=et(D_DAY, 9, 30), score=3)
        doc = self.st.db.execute("SELECT d.path FROM documents d JOIN filings f ON f.text_sha=d.sha WHERE f.accession="
                                 "'acc-a'").fetchone()[0]
        (self.st.root / doc).unlink()                          # (its TEXT document is gone from the store)
        root = self.w.root / "events"
        clock = [et(D_DAY, 7, 29)]
        lane = Lane(root, Gateway(), clock)
        self.assertEqual(R2.job(lane), {"skipped": "outside R2's window"}, "before 07:30:00 ET")
        clock[0] = et(D_DAY, 10, 0)
        first = R2.job(lane)
        self.assertEqual(first["ask"]["status"], "unrendered")
        self.assertEqual(lane.gw.calls, [], "nothing sent, nothing stored")
        clock[0] += dt.timedelta(seconds=90)
        second = R2.job(lane)
        self.assertEqual((second["ask"]["status"], second["ask"]["event"]), ("ok", "news:n-b"), "the next one asked")
        self.assertEqual(len(lane.gw.calls), 1, "one call a job")
        clock[0] += dt.timedelta(seconds=90)
        self.assertEqual(R2.job(lane)["due"], None)
        clock[0] = R2.ask_until(self.s)
        self.assertEqual(R2.job(lane), {"skipped": "outside R2's window"}, "from tau - 30 s: nothing")
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM r2_scan").fetchone()[0], 3)

    def test_what_a_read_sees_its_priors_newest_first_received_before_the_ask_and_the_item_left_out(self):
        cik, symbol = self.issuer()
        for i in range(45):
            self.w.article(f"p{i:02d}", symbol, knowable=et(D_DAY, 8, 0) - dt.timedelta(days=1, minutes=i),
                           headline=f"prior {i:02d}", symbols=[symbol, "ZZZZ"])
        self.w.article("late", symbol, knowable=et(D_DAY, 8, 30), received=et(D_DAY, 12, 0), headline="stored late")
        self.w.article("old", symbol, knowable=et(D_DAY, 9, 0) - dt.timedelta(days=31), headline="too old")
        self.w.eight_k("acc-1", cik, knowable=et(D_DAY, 7, 0), score=None, items=("8.01", "9.01"))
        ev = self.w.news_item("item", symbol, knowable=et(D_DAY, 9, 30), score=3, headline="the item")
        R2.scan(self.st, D_DAY, et(D_DAY, 10, 0))
        due = R2.next_due(self.st, D_DAY, self.s)
        self.assertEqual(due["event"], ev)
        text, prior = R2.render(self.st, due, D_DAY, et(D_DAY, 10, 1))
        self.assertEqual(prior["n"], 40, "at most 40 lines")
        self.assertEqual(prior["news"][:3], ["p00", "p01", "p02"], "newest first")
        self.assertNotIn("late", prior["news"], "received after the ask")
        self.assertNotIn("old", prior["news"])
        self.assertNotIn("item", prior["news"], "the item itself excluded")
        self.assertEqual(prior["filings"], ["acc-1"])
        self.assertIn("SEC 8-K items 8.01, 9.01", text)
        self.assertIn(" ET | benzinga | prior 00", text)


class TheLine(Case):
    def test_r2_line_at_the_texts_table_and_a_day_at_every_line_stays_inside_l(self):
        """Section 11: at L = $3 and V = $1.30 / $1.42 / $1.60 / $1.83, R2_LINE is $0.75 / $0.62 / $0.35 / $0 (rounded
        down to the cent: the reading that asks less), and R2 at its line + v1 at 1.5 V + the births' $0.25 <= L."""
        self.assertEqual([R2.r2_line(3, v) for v in ("1.30", "1.42", "1.60", "1.83")],
                         [D("0.75"), D("0.62"), D("0.35"), D("0.00")])
        self.assertEqual(R2.r2_line("3.75", "1.83"), D("0.75"))
        self.assertEqual(R2.BIRTHS_NIGHT, D(str(BI.NIGHT_USD)))
        self.assertEqual(R2.VERDICT_USD_UNKNOWN, H.VERDICT_USD_UNKNOWN)
        for cents in range(0, 400, 7):
            V_ = D(cents) / 100
            for L_ in (D("3"), D("3.75"), D("6")):
                line = R2.r2_line(L_, V_)
                self.assertGreaterEqual(line, 0)
                self.assertLessEqual(line, D("0.75"))
                if line > 0:
                    self.assertLessEqual(line + D("1.5") * V_ + D("0.25"), L_)

    def test_the_line_is_fixed_at_the_days_first_ask_from_the_heaviest_v1_day_of_seven(self):
        for days, usd in ((1, 1.30), (3, 1.42), (8, 2.50)):         # (eight days back: outside the seven)
            when = et(D_DAY, 12, 0) - dt.timedelta(days=days)
            for i in range(10):
                self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, "
                                   "score, guidance, answer, usd) VALUES(?, 'p', 'm', 'r', ?, ?, 'ok', 1, NULL, '{}', ?)",
                                   (f"news:v{days}-{i}", S.iso(when), S.iso(when), usd / 10))
        line = R2.line_of_day(self.st, et(D_DAY, 9, 0), lambda now: {"usd_day": 3.0, "source": "x"})
        self.assertEqual((line["line"], line["V"], line["L"]), ("0.62", "1.42", "3.0"))
        again = R2.line_of_day(self.st, et(D_DAY, 13, 0), lambda now: {"usd_day": 6.0, "source": "y"})
        self.assertEqual(again["line"], "0.62", "fixed at the day's first ask")

    def test_no_ask_is_sent_when_the_line_is_spent_or_a_cap_hold_names_the_day(self):
        """The task's item 4: no R2 ask goes out when R2's dollars of the day plus the call's hold pass R2_LINE, when a
        cap hold names the day, or when the lane's whole spend plus the hold would pass L."""
        cik, symbol = self.issuer()
        self.w.news_item("n-1", symbol, knowable=et(D_DAY, 9, 30), score=3)
        root = self.w.root / "events"
        clock = [et(D_DAY, 10, 0)]
        # (1) the line spent: R2's own dollars today at $0.70 of $0.75, the call's hold $0.0552
        self.st.db.execute("INSERT INTO reads2(event, prompt_sha, model, window, day, asked_at, answered_at, status, usd) "
                           "VALUES('news:spent', ?, ?, 'ON', ?, ?, ?, 'ok', 0.70)",
                           (R2.sha("news"), R2.MODEL, D_DAY.isoformat(), S.iso(clock[0]), S.iso(clock[0])))
        lane = Lane(root, Gateway(), clock)
        got = R2.job(lane)
        self.assertIn("R2_LINE", got["refused"])
        self.assertEqual(lane.gw.calls, [])
        self.assertIn("reader_line", [k for k, _ in lane.warned])
        self.st.db.execute("DELETE FROM reads2")
        # (2) a cap hold names the day
        hold = {"schema": 1, "day": clock[0].astimezone(UTC).date().isoformat(), "at": clock[0].timestamp(),
                "since": clock[0].timestamp(), "spent_usd": 12.0, "cap_usd": 10.0}
        (root.parent / "cap-hold.json").write_text(json.dumps(hold))
        lane = Lane(root, Gateway(), clock)
        self.assertIn("cap breach hold", R2.job(lane)["refused"])
        self.assertEqual(lane.gw.calls, [])
        (root.parent / "cap-hold.json").unlink()
        # (3) the lane's line: v1 already spent $2.98 of L = $3 today
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, score, "
                           "guidance, answer, usd) VALUES('news:v1', 'p', 'm', 'r', ?, ?, 'ok', 1, NULL, '{}', 2.98)",
                           (S.iso(clock[0]), S.iso(clock[0])))
        self.st.db.execute("DELETE FROM meta WHERE key LIKE 'evl10:line:%'")
        lane = Lane(root, Gateway(), clock, line=3.0)
        self.assertIsNotNone(R2.job(lane).get("refused"))
        self.assertEqual(lane.gw.calls, [], "R2's line is 0 here (V = $2.98) and the lane's line has no room")
        # and with room, the call goes
        self.st.db.execute("DELETE FROM verdicts")
        self.st.db.execute("DELETE FROM meta WHERE key LIKE 'evl10:line:%'")
        lane = Lane(root, Gateway(), clock)
        self.assertEqual(R2.job(lane)["ask"]["status"], "ok")
        self.assertEqual(len(lane.gw.calls), 1)

    def test_the_lanes_line_counts_r2s_dollars_and_a_call_in_flight_at_its_hold(self):
        house = mock.Mock()
        house.clock = lambda: et(D_DAY, 10, 0).timestamp()
        lane = H.EventLane(house, self.w.root / "events", gateway=Gateway())
        lane.verdict_line = lambda now: {"usd_day": 3.0, "source": "x"}
        lane._spend_today(self.st, et(D_DAY, 10, 0))
        before = lane._usd["usd"]
        self.st.db.execute("INSERT INTO reads2(event, prompt_sha, model, window, day, asked_at, answered_at, status, usd) "
                           "VALUES('news:a', ?, ?, 'ON', ?, ?, ?, 'ok', 0.0071)",
                           (R2.sha("news"), R2.MODEL, D_DAY.isoformat(), S.iso(et(D_DAY, 9, 0)), S.iso(et(D_DAY, 9, 0))))
        self.st.db.execute("INSERT INTO reads2(event, prompt_sha, model, window, day, asked_at, answered_at, status, usd) "
                           "VALUES('8k:b', ?, ?, 'ON', ?, ?, ?, 'asked', 0.1036)",
                           (R2.sha("doc"), R2.MODEL, D_DAY.isoformat(), S.iso(et(D_DAY, 9, 1)), S.iso(et(D_DAY, 9, 1))))
        lane._spend_today(self.st, et(D_DAY, 10, 0))
        self.assertAlmostEqual(lane._usd["usd"] - before, 0.0071 + 0.1036)
        from league.ops import budget as B
        self.assertGreaterEqual(B.lane_spend(self.w.root, et(D_DAY, 10, 0).timestamp())["today_usd"], 0.1107)

    def test_r2s_writes_leave_the_verdicts_byte_identical(self):
        cik, symbol = self.issuer()
        self.w.news_item("n-1", symbol, knowable=et(D_DAY, 9, 30), score=3)
        before = [tuple(r) for r in self.st.db.execute("SELECT * FROM verdicts ORDER BY event")]
        R2.scan(self.st, D_DAY, et(D_DAY, 10, 0))
        self.read_all(Gateway())
        self.decide()
        self.assertEqual([tuple(r) for r in self.st.db.execute("SELECT * FROM verdicts ORDER BY event")], before)


# ----------------------------------------------------------------------------------------------------- the decision
def fields(**kw) -> dict:
    return dict(NEWS_OK) | kw


class TheDecision(Case):
    def world(self) -> dict[str, tuple[str, str, str]]:
        """Eleven news issuers and two 8-K issuers read before tau, each with the fields its headline names."""
        made = {}
        answers = {}
        for i, (p_up, surprise) in enumerate(((90, 3), (85, 2), (80, 2), (75, 1), (70, 1), (70, 1), (65, 1), (60, 1),
                                              (60, 2), (55, 3), (90, 0))):
            cik, symbol = self.issuer()
            head = f"item {i:02d}"
            ev = self.w.news_item(f"n{i:02d}", symbol, knowable=et(D_DAY, 9, 5) + dt.timedelta(minutes=i), score=3,
                                  headline=head)
            answers[head] = fields(p_up=p_up, surprise=surprise)
            made[head] = (cik, symbol, ev)
        cik, symbol = self.issuer()
        ev = self.w.eight_k("acc-doc", cik, knowable=et(D_DAY, 8, 0), score=1, text="DOCDOC " + "x" * 300)
        answers["DOCDOC"] = dict(DOC_OK) | {"p_up": 95}
        made["doc"] = (cik, symbol, ev)
        cik, symbol = self.issuer()
        ev = self.w.eight_k("acc-dil", cik, knowable=et(D_DAY, 8, 1), score=0, text="DILUTE " + "x" * 300)
        answers["DILUTE"] = dict(DOC_OK) | {"dilution": True}
        made["dil"] = (cik, symbol, ev)
        self.w.scans(D_DAY, until=et(D_DAY, 10, 0))
        self.gw = Gateway(answers)
        self.read_all(self.gw, et(D_DAY, 11, 0))
        return made

    def test_the_filter_the_key_the_picks_and_their_rank_keys_one_transaction_with_its_receipt(self):
        made = self.world()
        got = self.decide()
        self.assertEqual(got["candidates"], 13)
        on = self.intents(P.R2_ON)
        # the filter: p_up >= 60, surprise >= 1, new >= 1, no dilution; the key: p_up, surprise, ... then the lower h
        passing = ["doc", "item 00", "item 01", "item 02", "item 03"]
        self.assertEqual([e for e, *_ in on][:5], [made[k][2] for k in passing])
        self.assertEqual(len(on), 8, "the first 8 passing")
        self.assertEqual([r[3] for r in on], [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0], "rank_key 9 - position")
        tau = S.iso(self.tau)
        self.assertEqual({(r[4], r[5], r[6], r[7], r[8], r[9]) for r in on},
                         {(tau, "2026-10-26", "2026-10-27", "close", "open", "planned")})
        self.assertEqual(len(self.intents(P.R2_SET)), 13, "the control: every candidate whatever the filter")
        self.assertEqual(len(self.intents(P.R2_PASS)), 10, "every passing one, no cut at 8")
        self.assertEqual({e for e, *_ in self.intents(P.R2_AVOID)}, {made["item 09"][2], made["item 10"][2],
                                                                    made["dil"][2]})
        rec = json.loads(self.st.db.execute("SELECT summary FROM receipts WHERE job=?",
                                            (f"{R2.JOB}:{D_DAY.isoformat()}",)).fetchone()[0])
        self.assertEqual({k: rec[k] for k in (P.R2_ON, P.R2_SET, P.R2_PASS, P.R2_AVOID)},
                         {P.R2_ON: {"planned": 8}, P.R2_SET: {"planned": 13}, P.R2_PASS: {"planned": 10},
                          P.R2_AVOID: {"planned": 3}})
        self.assertTrue(SN.names(rec, P.R2_ON), "the receipt names the seat as its judge reads it")
        self.assertEqual(R2.decided(self.st, D_DAY), "ok")
        feats = {r[0]: json.loads(r[1]) for r in self.st.db.execute("SELECT event, columns FROM r2_features")}
        self.assertEqual(len(feats), 13, "FEATURES-R2 v1 of every candidate")
        doc = feats[made["doc"][2]]["x"]
        self.assertEqual(len(doc), 21)
        self.assertEqual(doc[:7], [1.0, 1.0, 0.5, 2 / 3, 1.0, 2 / 3, 0.9])
        self.assertEqual(doc[15:17], [1.0, 0.0], "vs_own_guidance raised")
        self.assertEqual(doc[20], 0.0)
        self.assertEqual(len(R2.MISSING_ROW), 21)
        self.assertEqual(R2.MISSING_ROW[20], 1.0)

    def test_a_failing_run_writes_nothing_and_a_run_before_tau_is_refused(self):
        self.world()
        with mock.patch.object(R2, "features", side_effect=RuntimeError("an invented failure")):
            with self.assertRaises(RuntimeError):
                self.decide()
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM intents WHERE program LIKE '%R2%'").fetchone()[0], 0)
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM r2_features").fetchone()[0], 0)
        with self.assertRaises(RuntimeError):
            R2.decide(self.st, D_DAY, now=self.tau - dt.timedelta(seconds=1))

    def test_held_issuers_the_e10_bar_buyable_at_tau_and_an_8k_on_issuer_that_became_a_day_issuer(self):
        made = self.world()
        cik0, sym0, ev0 = made["item 00"]
        # EVL-R2-ON held item 00's issuer four sessions ago (an intent exiting within five sessions)
        back = C.previous(self.st, D_DAY, 4)[0].day
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 1, 'news:old', ?, ?, 'x', ?, 'close', "
                           "?, 'open', 8, 'shadow', 'exited', NULL)", (P.R2_ON, sym0, cik0, back.isoformat(),
                                                                       C.nth(self.st, back, 2).day.isoformat()))
        # item 01's issuer files an 8-K at 11:00 ET scored 2 (the E10 bar)
        cik1, sym1, _ = made["item 01"]
        self.w.eight_k("acc-bar", cik1, knowable=et(D_DAY, 11, 0), score=2)
        # the doc issuer gets a day-news article (it is now in DAY(D): an 8K-ON issuer EXCLUDED at tau)
        cikd, symd, _ = made["doc"]
        self.w.article("n-day", symd, knowable=et(D_DAY, 12, 0))
        self.decide()
        on = [e for e, *_ in self.intents(P.R2_ON)]
        self.assertNotIn(ev0, on, "held within five sessions")
        self.assertNotIn(made["item 01"][2], on, "barred by an 8-K scored 2 after 09:00 ET")
        self.assertNotIn(made["doc"][2], on, "an 8K-ON issuer that became a DAY(D) issuer is dropped")
        self.assertIn(ev0, {e for e, *_ in self.intents(P.R2_SET)}, "the control has its own one-position rule")

    def test_the_look_ahead_a_read_after_tau_and_an_8k_stored_after_it_change_nothing(self):
        """THE LOOK-AHEAD TEST (sections 2.4 and 11): the decision is identical with rows stored, answered or written
        after tau added; a read answered at tau + 1 s is missing for the shadow and for money; a read answered at
        tau + 30 s and an 8-K stored at tau + 60 s change neither the book's picks at 15:46 nor META's members."""
        def run(late: bool) -> tuple:
            with tempfile.TemporaryDirectory() as tmp:
                case = TheDecision()
                case.tmp = tempfile.TemporaryDirectory(dir=tmp)
                case.w = World(Path(case.tmp.name) / "events")
                case.st, case.s = case.w.st, case.w.session(D_DAY)
                case.tau = R2.tau(case.s)
                try:
                    case.world()
                    if late:
                        cik, symbol = case.issuer()
                        case.w.news_item("late-news", symbol, knowable=et(D_DAY, 15, 0), score=3, headline="late one",
                                         answered=et(D_DAY, 15, 1))
                        R2.scan(case.st, D_DAY, et(D_DAY, 15, 2))
                        due = R2.next_due(case.st, D_DAY, case.s)
                        self.assertEqual(due["event"], "news:late-news")
                        got = R2.ask(case.st, Gateway({"late one": fields(p_up=100, surprise=3)}), due, D_DAY,
                                     now=lambda: case.tau + dt.timedelta(seconds=1))
                        self.assertEqual(got["status"], "ok", "answered at tau + 1 s: stored, and missing for both")
                        # an 8-K of a candidate's issuer stored at tau + 60 s (scored 3: before tau it would bar it)
                        first = case.st.db.execute("SELECT cik FROM r2_qual WHERE kind='news' ORDER BY rowid LIMIT 1"
                                                   ).fetchone()[0]
                        case.w.eight_k("acc-late", first, knowable=et(D_DAY, 15, 30), score=3,
                                       stored=case.tau + dt.timedelta(seconds=60))
                    got = case.decide(case.tau + dt.timedelta(seconds=90))
                    lane = EB.Lane(case.w.root / "events" / S.DB_NAME)
                    try:
                        moment = case.s.close_at - dt.timedelta(minutes=14)
                        book = {pid: [(p.event, p.symbol, p.rank) for p in
                                      EB.picks(lane, P.BY_KEY[(pid, 1)], D_DAY, decided_at=moment)]
                                for pid in R2.meta_sources()}
                        later = {pid: [(p.event, p.symbol, p.rank) for p in
                                       EB.picks(lane, P.BY_KEY[(pid, 1)], D_DAY,
                                                decided_at=case.s.close_at + dt.timedelta(hours=5))]
                                 for pid in R2.meta_sources()}
                        members = {pid: [r["event"] for r in R2.one_reading(lane, pid, D_DAY)] for pid in R2.meta_sources()}
                    finally:
                        lane.close()
                    shadow = {pid: case.intents(pid) for pid in R2.meta_sources()}
                    return got, shadow, book, later, members
                finally:
                    case.w.close()
                    case.tmp.cleanup()
        plain, late = run(False), run(True)
        self.assertEqual(late[1], plain[1], "the shadow: identical")
        self.assertEqual(late[2], plain[2], "the book's picks at 15:46: identical")
        self.assertEqual(late[3], plain[2], "the reading is the live receipt's whatever its time")
        self.assertEqual(late[4], plain[4], "META's members (the one reading): identical")
        self.assertEqual({k: v for k, v in late[0].items() if k != "tau"}, {k: v for k, v in plain[0].items() if k != "tau"})
        self.assertTrue(plain[2][P.R2_ON], "the reading is not vacuous")

    def test_with_no_ok_receipt_the_reading_is_empty(self):
        self.world()
        rid = self.receipt()
        R2.decide(self.st, D_DAY, now=self.tau + dt.timedelta(seconds=5), rid=None)     # (its writes, no receipt made)
        self.st.finish_receipt(rid, "cut", {"why": "invented"})
        self.assertTrue(self.intents(P.R2_ON))
        self.assertEqual(R2.one_reading(self.st, P.R2_ON, D_DAY), [], "a receipt that is not ok: no decision of it")
        self.assertEqual(EB.picks(self.st, P.BY_KEY[(P.R2_ON, 1)], D_DAY, decided_at=self.tau), [])


# ------------------------------------------------------------------------------------------------------- the House
from league.tests import test_events_house as TH  # noqa: E402


class TheHouse(TH.LaneCase):
    """The House's lane (league/events/house.py) with PREREG-EVL-10 registered from before Tue Oct 20 (its time moved
    for the test only): the slot `decide-close-r2:<D>` at 15:40:00 in its own run, before the lane's close decision."""

    REG = "2026-10-19T12:00:00Z"
    DAY = "2026-10-20"

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(P, "REGISTERED_AT_10", self.REG)
        patch.start()
        self.addCleanup(patch.stop)

    def new_lane(self, redecide=False, **settings):
        """A lane whose sleep moves the House's clock too (the held turn: league/tests/test_events_scheduler.py)."""
        lane = super().new_lane(redecide, **settings)

        def sleep(seconds: float) -> None:
            self.mono.advance(seconds)
            self.clock.advance(seconds)
        lane._sleep = sleep
        return lane

    def opened(self):
        with self.store() as st:
            rid = st.start_receipt(f"decide-open:{self.DAY}", now=TH.et(self.DAY, "09:15"))
            st.finish_receipt(rid, "ok", {}, now=TH.et(self.DAY, "09:16"))

    def close_day(self, pinned: bool) -> tuple[dict, list[dict]]:
        with mock.patch.object(P, "REGISTERED_AT_10", self.REG if pinned else None):
            self.opened()
            self.at(TH.et(self.DAY, "15:40") + dt.timedelta(seconds=5))
            self.mark_recorded()
            self.lane.run()
            self.at(TH.et(self.DAY, "15:44") + dt.timedelta(seconds=40))
            self.mark_recorded()
            self.lane.run()
            [main] = self.receipts(f"decide-close:{self.DAY}")
            return main, self.receipts(f"{R2.JOB}:{self.DAY}")

    def test_the_slot_runs_at_tau_in_its_own_run_and_the_close_decision_keeps_its_time_and_receipt(self):
        plain, none = self.close_day(False)
        self.assertEqual(none, [], "unpinned: no slot")
        self.tearDown()
        self.setUp()
        main, mine = self.close_day(True)
        [r2] = mine
        self.assertEqual(r2["status"], "ok")
        self.assertGreaterEqual(r2["started_at"], TH.et(self.DAY, "15:40").strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertLessEqual(r2["finished_at"], TH.et(self.DAY, "15:44").strftime("%Y-%m-%dT%H:%M:%SZ").replace("44:00", "44:30"))
        self.assertEqual(json.loads(r2["summary"])["slot"]["bound"], 10.0)
        self.assertEqual((main["started_at"], main["status"], main["summary"]),
                         (plain["started_at"], plain["status"], plain["summary"]),
                         "the lane's close decision: the same time, status and summary, naming no row of this file")
        self.assertNotIn("EVL-R2", main["summary"])
        self.assertEqual(self.lane.health()["slots"]["close-evl10"]["status"], "ok")
        self.assertEqual(self.lane.health()["timing_table"], X.digest()[:8])

    def test_a_window_that_closed_with_no_run_is_missed_with_an_alarm_and_no_catch_up(self):
        self.opened()
        self.at(TH.et(self.DAY, "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        [r2] = self.receipts(f"{R2.JOB}:{self.DAY}")
        self.assertEqual(r2["status"], "missed")
        self.assertIn("warning", self.house.levels())
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT COUNT(*) FROM receipts WHERE job LIKE 'decide-close-r2-%'").fetchone()[0],
                             0, "no catch-up kind exists")
            self.assertIn("r2_starve", [a["kind"] for a in R2.alarms(st, TH.et(self.DAY, "16:30"))])

    def test_the_turn_starts_r2s_job_on_its_own_lane_never_feeds_or_ops(self):
        started = []
        self.house._background = lambda key, work, *a: started.append(key) or True
        self.at(TH.et(self.DAY, "10:00"))
        self.lane.turn(self.house)
        self.assertIn(H.READER_KEY, started)
        self.assertEqual(H.READER_KEY, "reader:r2")
        import inspect

        from league import house as HOUSE

        source = inspect.getsource(HOUSE.House.__init__) + inspect.getsource(HOUSE.House._background)
        self.assertIn('"reader": threading.Semaphore(1)', source)
        self.assertIn('"reader" if key.startswith("reader:")', source)
        self.assertNotIn("feeds:", H.READER_KEY)
        self.assertNotIn("ops:", H.READER_KEY)


# --------------------------------------------------------------------------------------------------------- the book
from league.events import learner as LR  # noqa: E402
from league.tests import test_events_book as TB  # noqa: E402

ON7 = "EVL-LRN-ON"


def r2_live(lane: TB.Lane, picks: list[tuple[str, str, float]], *, status: str = "ok", program: str = P.R2_ON,
            day: dt.date = TB.DAY) -> None:
    """THIS FILE'S LIVE DECISION of `day` on the lane's store as league/events/reader2.py `decide` writes it: each pick's
    universe row, its intents (decided_at = tau, rank_key 9 - position) and the slot's receipt `decide-close-r2:<D>`."""
    st = lane.st
    s = C.session(st, day)
    tau = R2.tau(s)
    nxt = C.nth(st, day, 2).day
    for i, (cik, symbol, prev) in enumerate(picks, start=1):
        if st.db.execute("SELECT 1 FROM universe WHERE day=? AND symbol=?", (day.isoformat(), symbol)).fetchone() is None:
            lane.universe(day, symbol, cik, prev, adv20=2e7)
        st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, exit_day, "
                      "exit_at, rank_key, mode, status, why) VALUES(?, 1, ?, ?, ?, ?, ?, 'close', ?, 'open', ?, 'shadow', "
                      "'planned', NULL)", (program, f"news:r2-{symbol}", symbol, cik, S.iso(tau), day.isoformat(),
                                            nxt.isoformat(), float(9 - i)))
    if st.db.execute("SELECT 1 FROM receipts WHERE job=?", (f"{R2.JOB}:{day.isoformat()}",)).fetchone() is None:
        rid = st.start_receipt(f"{R2.JOB}:{day.isoformat()}", now=tau + dt.timedelta(seconds=2))
        st.finish_receipt(rid, status, {program: {"planned": len(picks)}}, now=tau + dt.timedelta(seconds=3))


def day_news(lane: TB.Lane, ident: str, symbol: str, cik: str, *, score: int = 3) -> None:
    """A DAY(D) article of `symbol` and its PROMPT-NEWS verdict: EVL-NEWS-READ-ON's event at D's close (a main row)."""
    lane.article(ident, symbol, knowable=TB.iso(TB.DAY, 11, 0))
    lane.verdict(ident, score, answered=TB.iso(TB.DAY, 11, 5), news=True)
    lane.universe(TB.DAY, symbol, cik, 16.0, adv20=2e7)


class TheBook(TB.EventTest):
    """THE REAL BOOK (league/equity/live.py) at DAY's close, its lane store holding this file's live decision."""

    def setUp(self):
        super().setUp()
        self.addCleanup(P.load_births, None)

    def build(self, *, learners: bool = False) -> TB.Harness:
        T7.pin(self, T7.REG7 if learners else None)
        h = self.harness()
        LR.ensure(h.lane.st.db)
        day_news(h.lane, "n-1", "BETA", TB.CIK2)                    # EVL-NEWS-READ-ON's pick (a main row)
        r2_live(h.lane, [(TB.CIK2, "BETA", 16.0), (TB.CIK3, "GAMA", 16.0), ("0000000009", "DELT", 16.0)])
        self.ready(h)
        for sym in ("BETA", "GAMA", "DELT"):
            h.symbol(sym, last=17.0, sd=0.02)
        return h

    def buys(self, h: TB.Harness) -> list[tuple[str, str, str]]:
        return [(r["program"], r["symbol"], r["status"]) for r in h.event_intents("buy")]

    def sent(self, h: TB.Harness) -> list[str]:
        return [b["symbol"] for b in h.bodies() if b.get("side") == "buy"]

    def test_its_buys_come_after_every_earlier_row_its_names_given_counted_and_its_summary_in_the_closes_row(self):
        h = self.build()
        h.tick(9, 15)
        h.tick(15, 46)
        self.assertEqual(self.buys(h)[:1], [("EVL-NEWS-READ-ON", "BETA", "planned")], "the main pass at 15:46")
        self.assertNotIn(P.R2_ON, [b[0] for b in self.buys(h)], "before its window: nothing of it")
        h.tick(15, 47)
        buys = self.buys(h)
        self.assertEqual([(p, s) for p, s, _ in buys], [("EVL-NEWS-READ-ON", "BETA"), (P.R2_ON, "GAMA"), (P.R2_ON, "DELT")])
        self.assertEqual(self.sent(h)[0], "BETA", "every earlier row's buy is sent first")
        self.assertEqual(self.sent(h), ["BETA", "GAMA", "DELT"])
        mine = h.book._event_summary(TB.DAY.isoformat(), "close-evl10")["programs"][P.R2_ON]
        self.assertEqual((mine["picks"], mine["room"], mine["planned"], mine["skipped"], mine["binding"]),
                         (3, 8, 2, {"name_given": 1}, "given"))
        close = h.book._event_summary(TB.DAY.isoformat(), "close")
        self.assertEqual(close["programs"][P.R2_ON], mine, "(d): in the auction's own row, where A85 and the report read")
        self.assertIn("EVL-NEWS-READ-ON", close["programs"], "beside every main row's, unchanged")
        inst = h.book._instance(L.instance_key(P.R2_ON, 1))
        self.assertEqual(h.book._event_recent(inst, "close", 5)[0], [3])

    def test_every_earlier_rows_real_money_buys_and_sends_are_the_same_with_and_without_this_file(self):
        """THE PROOF IN REAL MONEY: the same day's book with this file's live decision and without the file (its rows in
        no registry): every earlier row's buy intents, their sizes, their order and the bodies sent are the same; this
        file's buys come after them."""
        from league.tests import evl10_fakes as F10

        def run(pinned: bool) -> tuple[list, list]:
            with (contextlib.nullcontext() if pinned else F10.unpinned_10()), tempfile.TemporaryDirectory() as tmp:
                h = TB.Harness(Path(tmp))
                try:
                    LR.ensure(h.lane.st.db)
                    day_news(h.lane, "n-1", "BETA", TB.CIK2)
                    day_news(h.lane, "n-2", "EPSI", "0000000011")
                    r2_live(h.lane, [(TB.CIK2, "BETA", 16.0), (TB.CIK3, "GAMA", 16.0)])
                    self.ready(h)
                    for sym in ("BETA", "GAMA", "EPSI"):
                        h.symbol(sym, last=17.0, sd=0.02)
                    for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47), (15, 48)):
                        h.tick(hh, mm)
                    buys = [(r["program"], r["symbol"], r["band"], r["limit_px"], r["status"]) for r in h.event_intents("buy")]
                    bodies = [(b["symbol"], b["qty"], b.get("limit_price")) for b in h.bodies() if b.get("side") == "buy"]
                    return buys, bodies
                finally:
                    h.state.close()
                    h.lane.st.close()
                    if h.book._event_lane is not None:
                        h.book._event_lane.close()
        T7.pin(self, None)
        with_, without = run(True), run(False)
        mine = [b for b in with_[0] if P.is_reader2(b[0])]
        self.assertEqual([b for b in with_[0] if not P.is_reader2(b[0])], without[0], "every earlier row's buys")
        self.assertEqual(with_[1][:len(without[1])], without[1], "the same bodies, sent first, in the same order")
        self.assertEqual([(p, s) for p, s, *_ in mine], [(P.R2_ON, "GAMA")], "then this file's, BETA given before it")
        self.assertEqual(len(with_[1]), len(without[1]) + 1)

    def test_r3s_births_buy_before_it_its_place_in_room_is_after_every_earlier_row(self):
        """ROOM AFTER BIRTHS (section 2.5, F2): a close-entry birth at learning (R3's tier after every PREREG row) is
        given its name and sent before this file's buy; this file passes over the birth's name."""
        from league.tests import test_events_1019m_learners as TM

        T7.pin(self, None)
        h = self.harness()
        LR.ensure(h.lane.st.db)
        birth = TM.register(h, TM.CLOSE_BIRTH, "news-day", {"score_max": -2}, exit_="open")
        h.lane.article("n-b", "BRTH", knowable=TB.iso(TB.DAY, 11, 0))
        h.lane.verdict("n-b", -3, answered=TB.iso(TB.DAY, 11, 5), news=True)
        h.lane.universe(TB.DAY, "BRTH", TB.CIK2, 16.0)
        h.lane.intent(birth, "news:n-b", "BRTH", TB.CIK2, TB.DAY, TB.NEXT)
        r2_live(h.lane, [(TB.CIK2, "BRTH", 16.0), (TB.CIK3, "GAMA", 16.0)])
        self.ready(h)
        for sym in ("BRTH", "GAMA"):
            h.symbol(sym, last=17.0, sd=0.02)
        for hh, mm in ((9, 15), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.assertEqual([(p, s) for p, s, _ in self.buys(h)], [(TM.CLOSE_BIRTH, "BRTH"), (P.R2_ON, "GAMA")])
        self.assertEqual(self.sent(h), ["BRTH", "GAMA"], "the birth's buy is sent first")
        self.assertEqual(EB.room_key(P.R2_ON, "learning")[0], EB.PRIORITY["learning"],
                         "its ROOM tier is unchanged (A85 reads it); its send order is after every main row's")

    def test_with_evl7s_receipt_at_154820_no_buy_of_it_at_the_1548_tick_nor_at_that_close(self):
        """Section 2.5's TEST: a learner live at the close whose own receipt comes only at 15:48:20 keeps the learners'
        pass undecided until the window's last book minute (A140 then decides it without the learner): this file's pass
        still waits at the 15:48 tick, plans none and writes its window row; nothing of it goes at that close."""
        h = self.build(learners=True)
        on7 = T7.learner(ON7)
        h.book._event_learners = lambda at, adapter: [(h.book._instance(L.instance_key(ON7, 1)), on7)] \
            if at == "close" and h.book._instance(L.instance_key(ON7, 1)) is not None else []
        h.tick(9, 15)
        self.assertIn("before the file's send window", str(h.tick(15, 46).get("event_decide_evl10")))
        self.assertIn("the learners' pass", str(h.tick(15, 47).get("event_decide_evl10")), "it waits, keeping nothing")
        h.tick(15, 48)
        T7.name_live(h.lane.st, ON7, TB.DAY, finished=T7.et(TB.DAY, 15, 48, 20))
        h.tick(15, 49)
        self.assertNotIn(P.R2_ON, [b[0] for b in self.buys(h)])
        row = h.book._event_summary(TB.DAY.isoformat(), "close-evl10")
        self.assertEqual((row["programs"][P.R2_ON]["planned"], row["programs"][P.R2_ON]["binding"]), (0, "window"))
        self.assertEqual(row["programs"][P.R2_ON]["picks"], 3, "(e): its picks read by the one reading")
        self.assertEqual(h.book._event_summary(TB.DAY.isoformat(), "close")["programs"][P.R2_ON]["binding"], "window")

    def test_it_waits_for_an_earlier_files_own_book_pass_too(self):
        """(ii) for a file outside the scheduler (PREREG-EVL-8's late passes when its code is in the tree:
        `EIGHT_PASSES`): while such a pass of a live program is not decided, this file's pass waits."""
        h = self.build()
        h.book.EIGHT_PASSES = {"close": (("close-meta8", ("EVL-NEWS-READ-ON",)),)}
        h.tick(9, 15)
        h.tick(15, 46)
        self.assertIn("close-meta8", str(h.tick(15, 47).get("event_decide_evl10")))
        h.state.upsert("eq_event_decisions", {"day": TB.DAY.isoformat(), "at": "close-meta8", "decided_at": "x",
                                              "status": "done", "summary": "{}", "created_at": 0.0}, "day, at")
        h.tick(15, 48)
        self.assertIn((P.R2_ON, "GAMA"), [(p, s) for p, s, _ in self.buys(h)], "decided: it plans at the next tick")

    def test_a_receipt_that_is_not_ok_trades_nothing(self):
        h = self.harness()
        LR.ensure(h.lane.st.db)
        r2_live(h.lane, [(TB.CIK3, "GAMA", 16.0)], status="cut")
        self.ready(h)
        h.symbol("GAMA", last=17.0, sd=0.02)
        for hh, mm in ((9, 15), (15, 46), (15, 47), (15, 48)):
            h.tick(hh, mm)
        self.assertEqual(self.buys(h), [])
        self.assertIn("no decision of its rows", h.book._event_summary(TB.DAY.isoformat(), "close-evl10")["why"])

    def test_its_entries_keep_every_earlier_rows_orders_on_the_days_line(self):
        h = self.build()
        h.tick(9, 15)
        h.tick(15, 46)
        inst = h.book._instance(L.instance_key(P.R2_ON, 1))
        s = EB.settings()
        keep = h.book._event_line_keep(None, inst, TB.DAY.isoformat(), "close", s, EB)
        self.assertEqual(keep, 1 + 2, "its own exit, and the planned main buy's send and re-send")
        news = h.book._instance(L.instance_key("EVL-NEWS-READ-ON", 3)) or \
            next(i for i in h.book._instances(alive=True) if i.family == "EVL-NEWS-READ-ON")
        self.assertEqual(h.book._event_line_keep(None, news, TB.DAY.isoformat(), "close", s, EB), 0,
                         "a main row keeps nothing: unchanged")


class TheBookRules(TB.EventTest):
    """Section 2.5 (a)-(c) and A85's reservation of a promoted EVL-R2-ON, on the book's own rows (fix2/slot_rules.out)."""

    def test_a_promoted_r2_on_reserves_min14_median6_at_the_next_open_30_percent_never_70(self):
        T7.pin(self, None)
        h = self.harness(E="1906", cash="1906")
        h.lane.band(P.R2_ON, "probe", version=1)
        self.ready(h)
        h.tick(9, 15)
        inst = h.book._instance(L.instance_key(P.R2_ON, 1))
        self.assertEqual((inst.band, EB.settings().max_open("probe", P.BY_KEY[(P.R2_ON, 1)])), ("probe", 14))
        opener = next(i for i in h.book._instances(alive=True) if i.family == "EVL-ERN-READ-O1")
        self.assertEqual(opener.band, "learning")
        s = EB.settings()
        cash, _, _ = h.book._event_reserve(opener, TB.DAY.isoformat(), "open", s, D("1906"))
        self.assertEqual(cash.quantize(D("0.01")), D("1334.20"), "no history: its whole room, 14 x 5% of E")
        for n, day in zip((5, 6, 6, 7, 5), [x.day for x in C.previous(h.lane.st, TB.DAY, 5)]):
            h.state.upsert("eq_event_decisions", {"day": day.isoformat(), "at": "close", "decided_at": "x",
                                                  "status": "done", "summary": json.dumps({"programs": {P.R2_ON: {"picks": n,
                                                                                                              "room": 14}}}),
                                                  "created_at": 0.0}, "day, at")
        cash, _, _ = h.book._event_reserve(opener, TB.DAY.isoformat(), "open", s, D("1906"))
        self.assertEqual(cash.quantize(D("0.01")), D("571.80"), "min(14, 6) x 0.05 x E: 30% of E")

    def test_a_probe_lot_unsettled_past_the_ladder_holds_its_probe_buys(self):
        T7.pin(self, None)
        h = self.harness()
        h.lane.band(P.R2_ON, "probe", version=1)
        r2_live(h.lane, [(TB.CIK3, "GAMA", 16.0)])
        self.ready(h)
        h.symbol("GAMA", last=17.0, sd=0.02)
        h.tick(9, 15)
        inst = h.book._instance(L.instance_key(P.R2_ON, 1))
        with mock.patch.object(L.EquityBook, "_event_unsettled", lambda self, i, day, adapter: ["a lot"] if i.id == inst.id
                               else []), \
                mock.patch.object(L.EquityBook, "_event_unsettled_hold", lambda self, i, lots, day: "held (invented)"):
            for mm in (46, 47):
                h.tick(15, mm)
        row = h.book._event_summary(TB.DAY.isoformat(), "close-evl10")["programs"][P.R2_ON]
        self.assertEqual((row["picks"], row["room"], row["held"]), (None, 0, "unsettled"))
        self.assertEqual([r for r in h.event_intents("buy") if r["program"] == P.R2_ON], [])


# ------------------------------------------------------------------------------------------------------- the proof
from league.tests import evl10_week as WK  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "evl10_week_main.json"


def reads_and_slot(w, day: dt.date) -> None:
    """PREREG-EVL-10 in the invented week at its own times: scans from 07:31 ET to 15:38 ET (every 20 minutes and after
    the lane's 15:17 asks), every due call asked and answered before tau (a fake gateway: no metered call), then its
    slot's decision at tau + 5 s with its receipt."""
    session = C.session(w.st, day)
    gw = Gateway()
    t = session.at(dt.time(7, 31))
    while t <= R2.ask_until(session):
        R2.scan(w.st, day, t)
        due = R2.next_due(w.st, day, session)
        while due is not None:
            R2.ask(w.st, gw, due, day, now=lambda t=t: t + dt.timedelta(seconds=30))
            due = R2.next_due(w.st, day, session)
        t += dt.timedelta(minutes=20)
    when = R2.tau(session) + dt.timedelta(seconds=5)
    rid = w.st.start_receipt(f"{R2.JOB}:{day.isoformat()}", now=when)
    out = R2.decide(w.st, day, now=when, rid=rid)
    w.st.finish_receipt(rid, "ok", out, now=when)


def earlier(program: str) -> bool:
    return not P.is_reader2(program)


class TheProof(unittest.TestCase):
    """THE PROOF ON AN INVENTED WEEK (league/tests/evl10_week.py: release 1019e's and PREREG-EVL-5's week with two births
    of R3): (1) on this tree, with the scheduler and this file pinned, every program's intents, every decision receipt
    (job, status, start, finish, summary: the earlier files' decisions and their timing) and every seatable program's
    real-money picks are main's, recorded on main 1c87837f (a test that fails if the scheduler, or this file's code,
    moves any of them); (2) with this file reading and deciding in its slot, every earlier program's shadow intents,
    real-money picks and the House's receipts are the same as without it, and this file's rows did decide."""

    def test_the_week_on_this_tree_is_mains_recorded_byte_for_byte(self):
        want = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            got = json.loads(json.dumps(WK.run(Path(tmp) / "lane"), default=str))
        self.assertEqual(got["intents"], want["intents"], "every intent, main's")
        self.assertEqual(got["receipts"], want["receipts"], "every decision receipt and its times, main's")
        mine = {k: v for k, v in got["picks"].items() if k.split("@")[0] in R2.meta_sources()}
        self.assertEqual({k: v for k, v in got["picks"].items() if k not in mine}, want["picks"])
        self.assertEqual(set(mine), {f"{P.R2_ON}@v1@2026-10-27", f"{P.R2_ON}@v1@2026-10-28"})
        self.assertEqual(list(mine.values()), [[], []], "no slot ran: no reading of this file's rows")

    def test_every_earlier_programs_shadow_intents_and_real_money_picks_are_the_same_with_and_without_this_file(self):
        from league.tests import evl10_fakes as F10

        with tempfile.TemporaryDirectory() as tmp:
            with_ = WK.run(Path(tmp) / "with", during=reads_and_slot)
            mine = WK.run(Path(tmp) / "mine", during=reads_and_slot, keep=P.is_reader2)
            with F10.unpinned_10():
                without = WK.run(Path(tmp) / "without")
        P.refresh_7()
        own = [r for r in mine["intents"]]
        self.assertTrue(any(r[0] == P.R2_ON for r in own), "this file's seat did pick: the proof is not vacuous")
        self.assertTrue(any(v for k, v in mine["picks"].items()), "and real money read its picks")
        keep = {k: v for k, v in with_["picks"].items() if earlier(k.split("@")[0])}
        self.assertEqual([r for r in with_["intents"] if earlier(r[0])], without["intents"])
        self.assertEqual(keep, without["picks"])
        self.assertEqual(with_["receipts"], without["receipts"], "the House's receipts, naming no row of this file")
        for job, _, _, _, summary in with_["receipts"]:
            self.assertNotIn("EVL-R2", summary, job)


# ------------------------------------------------------------------------------------------------------- the judge
class TheJudge(Case):
    """Section 3: PREREG-EVL-6's screen as frozen judges EVL-R2-ON against EVL-R2-ON-SET; its finality is its slot's
    clock (live only, no catch-up); a run reads the budget once, at the close it would start, and never more than three."""

    def test_its_judge_its_control_and_its_finality(self):
        self.assertIn(P.BY_KEY[(P.R2_ON, 1)], SN._v6_programs())
        self.assertNotIn(P.BY_KEY[(P.R2_SET, 1)], SN._v6_programs())
        self.assertEqual(SN.control_of(P.R2_ON), P.R2_SET)
        day, why = SN.final_until(self.st, P.R2_ON, 1, D_DAY, et(D_DAY, 15, 44, 0))
        self.assertEqual(day, P_DAY, why)
        day, why = SN.final_until(self.st, P.R2_ON, 1, D_DAY, et(D_DAY, 15, 44, 21))
        self.assertEqual(day, D_DAY, "its slot can no longer run after 15:44:20: final, decided or not")

    def end(self, n: int) -> None:
        self.st.set_meta(SN.V6_END_KEY.format(program=P.R2_ON, version=1, n=n),
                         json.dumps({"at": S.iso(et(D_DAY, 16, 0)), "last_day": D_DAY.isoformat()}))

    def test_a_run_starts_when_the_budget_holds_it_at_that_close_else_never(self):
        self.end(1)
        got = SN.start_runs(self.st, et(D_DAY, 20, 40))
        self.assertIn((P.R2_ON, 1, 2), [(r["program"], r["version"], r["n"]) for r in got])
        self.assertNotIn(P.R2_ON, [r["program"] for r in SN.waiting_runs(self.st)], "it never waits")
        self.end(2)
        real = SN.budget6
        with mock.patch.object(SN, "budget6", lambda store: real(store) | {"used": 385, "waiting": 0}):
            self.assertEqual([r for r in SN.start_runs(self.st, et(N_DAY, 20, 40)) if r["program"] == P.R2_ON], [])
        refused = R2._meta_json(self.st, R2.NORUN_KEY.format(program=P.R2_ON, version=1, n=3))
        self.assertIn("cannot hold 0.13", refused["why"])
        self.assertEqual(SN.start_runs(self.st, et(N_DAY + dt.timedelta(days=1), 20, 40)), [],
                         "no later restatement revives it")
        self.assertEqual(R2.stopped(self.st)["kind"], "seat", "a shadow record only: R2 asks nothing more")

    def test_never_more_than_three_runs(self):
        for n in (1, 2, 3):
            if n > 1:
                self.st.set_meta(SN.V6_RUN_KEY.format(program=P.R2_ON, version=1, n=n),
                                 json.dumps({"n": n, "after_day": None, "after": None, "started": "x"}))
            self.end(n)
        self.assertEqual(SN.start_runs_r2(self.st, et(D_DAY, 20, 40)), [])
        refused = R2._meta_json(self.st, R2.NORUN_KEY.format(program=P.R2_ON, version=1, n=4))
        self.assertIn("3 runs are spent", refused["why"])


# ------------------------------------------------------------------------------------------ the report and the facts
class TheReport(Case):
    def test_the_reader_block_counts_only_and_the_alarms(self):
        cik, symbol = self.issuer()
        self.w.news_item("n-1", symbol, knowable=et(D_DAY, 9, 30), score=3, headline="A SECRET HEADLINE")
        self.w.scans(D_DAY, until=et(D_DAY, 10, 0))
        self.read_all(Gateway())
        self.decide()
        got = R2.session_counts(self.st, D_DAY)
        self.assertEqual((got["chosen"], got["reads"], got["decision"], got["answered_by_tau"]),
                         ({"news": 1, "doc": 0}, {"ok": 1}, "ok", 1))
        lines = R2.report_lines(self.st, D_DAY, et(D_DAY, 17, 0))
        text = "\n".join(lines)
        self.assertNotIn("SECRET", text)
        self.assertNotIn(symbol, text, "no symbol, headline or field of any read")
        from league.events import report as RP

        report = RP.build(self.st, D_DAY, now=et(D_DAY, 17, 0))
        self.assertEqual(report["reader2"]["decision"], "ok")
        rendered = RP.render(report)
        self.assertIn("Reader-2: scans", rendered)
        self.assertNotIn("SECRET", rendered)

    def test_r2_starve_reader_missing_and_r2_cap(self):
        kinds = {a["kind"] for a in R2.alarms(self.st, et(D_DAY, 16, 30))}
        self.assertIn("r2_starve", kinds, "no live decision of the session: no intent, block, record or money")
        self.decide()
        self.assertNotIn("r2_starve", {a["kind"] for a in R2.alarms(self.st, et(D_DAY, 16, 30))})
        for day in (C.previous(self.st, D_DAY, 1)[0].day, D_DAY):
            for i in range(10):
                self.st.db.execute("INSERT INTO r2_qual(window, day, cik, event, kind, qualified_at, v1_score, h, q, chosen) "
                                   "VALUES('ON', ?, ?, ?, 'news', '2026-10-01T00:00:00Z', 3, 0.1, 0.5, 1)",
                                   (day.isoformat(), f"c{i}", f"news:{day}-{i}"))
        self.assertIn("reader_missing", {a["kind"] for a in R2.alarms(self.st, et(D_DAY, 16, 30))})
        self.st.set_meta(R2.CAP_KEY.format(day=D_DAY.isoformat()), "x")
        self.assertIn("r2_cap", {a["kind"] for a in R2.alarms(self.st, et(D_DAY, 16, 30))})

    def test_births_facts_refuse_r2s_tables(self):
        for table in ("reads2", "r2_qual", "r2_scan", "r2_features"):
            self.assertIn(table, BI.FACTS_DENY)
        with BI.outcome_free(self.st.db):
            for table in ("reads2", "r2_qual", "r2_scan", "r2_features"):
                with self.assertRaises(Exception):
                    self.st.db.execute(f"SELECT * FROM {table}").fetchall()
