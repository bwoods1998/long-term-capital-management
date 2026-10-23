"""A95: R3's FIRST BIRTHS NIGHT ACCEPTED NONE (night 2026-10-21, births receipt 02:11:44Z Oct 22: one Haiku call, six
specs, all six refused by the grammar), and the fix (league/events/births.py), on invented data only.

Held here: (1) THE HOUSE NAMES AN ID that lacks "EVL-B-" canonically (`canonical_name`: a leading "EVL-" becomes
"EVL-B-", any other id takes "EVL-B-" in front), every check of an id applies to the new name, the canonical line and
the sha carry it, and the candidate row keeps the proposed id (`figures.named`); (2) a ONE-ROLE LIST reads as its role,
any other list is refused as before; (3) the PROMPT shows two valid specs and the 8k line, and its sha moved (release
1019e's answer is never read again by this code); (4) THE ONE RE-RUN OF AN EMPTY NIGHT (`rerun_due`, the House's lane):
an older reading's night that accepted and registered none runs once more, before 12:55Z of the session day after it,
reusing a stored answer at the running prompt sha or making the night's call inside its cap, its births counting only
events after their own registration; a night with an accepted birth, a night the running reading wrote, a night re-run
once, or a night past its cut-off never runs again; and (5) A REPLAY OF THE SIX: the ids renamed, the ern and news
specs accepted by the validator on invented facts, the ins-buy judged by the validator's count alone, the three 8k
score/guidance specs still refused.

THE SIX ARE RECONSTRUCTED from the captain's read of the House's `birth_candidates` (A95; this repository never reads
the House's store): the four ids named there and the fields refused there are as written ("guidance": {"verdict":
"none"}; items 5.02/5.03/5.07, 9.01 and 3.01-3.03 with score and guidance fields; "roles": ["officer"]); the other two
8k ids and every other value are invented."""

from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import births as BI
from league.events import calendar as C
from league.events import programs as P
from league.events import store as S
from league.events import verdicts as V
from league.tests import test_events_births as TB
from league.tests import test_events_house as TH

UTC = dt.timezone.utc
spec = TB.spec
et = TB.et

#: Release 1019e's prompt sha (the first births night asked under it) and this reading's: a prompt change is a new
#: PARSE_VERSION (A95), so the pair is pinned here together.
PROMPT_1019E = "2203fda336035feb3786317af09cee9f32b77353999a67e58c18911a41518a77"
#: (Release 1019h, the captain's A97: SUP-3's rate rule moved the prompt's rate lines and added the Nov 6 line: version 3.
#: Release 1019h too, the captain's A109: the architect on Claude Opus 5.5, with no temperature, effort low and 6000
#: tokens, all in the sha's spec: version 4. Version 3 was never live. Release 1019i, PREREG-EVL-6 section 5: the prompt
#: tells the restated charge from the budget, 0.13 where version 4 said 0.10: version 5.)
PROMPT_BY_VERSION = {2: "8294fe777c44b1cd06d04c48af9a60dade4f5443e9597a4f77fe853dd9affdce",
                     3: "890806ff38f09b7e810cbbfef1159ca85f39d568105537d8eca4d7e60c022b06",
                     4: "0cae215b0cebb21e9313d392e358c443a4d2caf06554e593f32fbaba8cfe6c21",
                     5: "1442a2a23637e66158ad01b072b2df85f4c6d9fa60b2d7640c8ff98226a6914e"}

NIGHT = dt.date(2026, 10, 21)           # Wed: the first births night
RECEIPT_AT = dt.datetime(2026, 10, 22, 2, 11, 33, tzinfo=UTC)

SIX = [
    {"spec": {"id": "EVL-8K-ITEMS-5-O1", "version": 1, "family": "8k",
              "rule": {"items": ["5.02", "5.03", "5.07"], "score_min": 1, "guidance": {"verdict": "none"}},
              "entry": "open", "exit": "close", "hold": 1, "rank": "score", "seatable": True},
     "why": "officer and governance changes read by the verdict"},
    {"spec": {"id": "EVL-8K-ITEMS-9-O1", "version": 1, "family": "8k",
              "rule": {"items": ["9.01"], "score_min": 1, "guidance": {"verdict": "none"}},
              "entry": "open", "exit": "close", "hold": 1, "rank": "score", "seatable": False},
     "why": "exhibit-only 8-Ks read by the verdict"},
    {"spec": {"id": "EVL-8K-ITEMS-3-O1", "version": 1, "family": "8k",
              "rule": {"items": ["3.01", "3.02", "3.03"], "score_max": -1, "guidance": {"verdict": "none"}},
              "entry": "open", "exit": "close", "hold": 1, "rank": "none", "seatable": False},
     "why": "listing and securities notices read by the verdict"},
    {"spec": {"id": "EVL-ERN-NEGATIVE-O1", "version": 1, "family": "ern", "rule": {"score_max": -2},
              "entry": "open", "exit": "close", "hold": 1, "rank": "none", "seatable": True},
     "why": "earnings read as clearly negative"},
    {"spec": {"id": "EVL-NEWS-EARLY-MORNING-O1", "version": 1, "family": "news", "rule": {"hours": [5, 6, 7, 8]},
              "entry": "open", "exit": "close", "hold": 1, "rank": "none", "seatable": True},
     "why": "single-company articles in the early morning"},
    {"spec": {"id": "EVL-INS-BUY-OFFICER-O1", "version": 1, "family": "ins-buy",
              "rule": {"value_min": 100000, "roles": ["officer"]},
              "entry": "open", "exit": "close", "hold": 1, "rank": "value", "seatable": True},
     "why": "an officer's open-market buy of at least $100,000"},
]
GUIDANCE_WHY = "guidance must be a proper subset of"
READ_ITEMS_WHY = "a READ birth of the 8k family names only items whose verdicts the lane asks (1.01, 2.01, 7.01, 8.01)"


def old_receipt(st: S.Store, *, night: dt.date = NIGHT, at: dt.datetime = RECEIPT_AT, accepted=(), **extra) -> int:
    """A births receipt as release 1019e's code wrote it (no `parse_version`)."""
    rid = st.start_receipt(BI.JOB, now=at)
    summary = {"night": night.isoformat(), "proposed": 6, "accepted": list(accepted),
               "refused": [{"id": None, "why": ["id must match ..."]}] * (6 - len(accepted)),
               "call": {"status": "ok", "offered": 6, "usd": 0.0084, "why": None}} | extra
    st.finish_receipt(rid, "ok", summary, now=at + dt.timedelta(seconds=11))
    return rid


def stored_call(st: S.Store, *, prompt: str, usd: float = 0.0084, night: dt.date = NIGHT, answer: str | None = None):
    """The night's answer as `propose` stores it."""
    st.db.execute("INSERT INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, status, user_sha, "
                  "facts_sha, answer, usd) VALUES(?, ?, ?, ?, ?, ?, 'ok', 'u', 'f', ?, ?)",
                  (night.isoformat(), prompt, BI.MODEL, f"evl-births:{night}:{prompt[:12]}", S.iso(RECEIPT_AT),
                   S.iso(RECEIPT_AT + dt.timedelta(seconds=8)), answer if answer is not None else
                   json.dumps({"specs": SIX}), usd))


# ======================================================================================================== (1) names
class TheHouseNamesAnId(unittest.TestCase):
    def test_an_id_lacking_the_prefix_is_named_canonically_and_every_check_is_the_names(self):
        self.assertEqual(BI.canonical_name("EVL-8K-ITEMS-5-O1"), "EVL-B-8K-ITEMS-5-O1", "a leading EVL- becomes EVL-B-")
        self.assertEqual(BI.canonical_name("ERN-NEG"), "EVL-B-ERN-NEG", "any other id takes EVL-B- in front")
        self.assertEqual(BI.canonical_name("EVL-B-ERN-NEG"), "EVL-B-ERN-NEG", "a prefixed id is as it was")
        self.assertEqual(BI.canonical_name(5), 5)
        named = spec("EVL-ERN-NEGATIVE-O1", "ern", {"score_max": -2})
        canon = spec("EVL-B-ERN-NEGATIVE-O1", "ern", {"score_max": -2})
        self.assertEqual(BI.parse(named)["id"], "EVL-B-ERN-NEGATIVE-O1")
        self.assertEqual(BI.canonical(named), BI.canonical(canon), "the canonical line carries the House's name")
        self.assertEqual(BI.sha(named), BI.sha(canon), "and so does the digest: a name is not part of the rule")
        self.assertEqual(BI.renamed(named), {"from": "EVL-ERN-NEGATIVE-O1", "to": "EVL-B-ERN-NEGATIVE-O1"})
        self.assertEqual(BI.renamed(json.dumps(named)), BI.renamed(named))
        self.assertIsNone(BI.renamed(canon))
        self.assertIsNone(BI.renamed({"id": 7}))
        # Every check of an id is the new name's.
        base = spec("EVL-B-8K-502", "8k", {"items": ["5.02"]})
        for bad, name in (("ABCDEFGHIJKL-ABCDEFGHIJKL-ABCDEFGHIJ", "over 40 characters as named"),
                          ("EVL-FOO-CTRL", "a control's name"),
                          ("evl-lower", "lower case"),
                          ("EVL-", "nothing after the prefix"),
                          ("EVL-A-B-C-D-E-F", "six groups after EVL-B-")):
            with self.assertRaises(BI.SpecError, msg=name) as caught:
                BI.parse(base | {"id": bad})
            [why] = caught.exception.reasons
            self.assertIn("id must match", why, name)
            self.assertIn(f"(the House's name {BI.canonical_name(bad)} of {bad})", why, name)

    def test_a_named_id_that_is_registered_already_is_refused_and_the_row_keeps_both(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(TB.unload)
        s = TB.Synth(Path(tmp.name))
        self.addCleanup(s.st.close)
        s.register(spec("EVL-B-8K-502", "8k", {"items": ["5.02"]}), "2026-10-01T00:00:00Z")
        P.load_births(s.st)
        facts = BI.Facts(s.st, TB.Validation.AS_OF, sessions=1)
        [out] = BI.validate(s.st, facts, [{"spec": spec("EVL-8K-502", "8k", {"items": ["1.02"]}), "why": "x"}])
        self.assertFalse(out["ok"])
        self.assertIn("EVL-B-8K-502 is registered already", out["reasons"][0])
        self.assertEqual((out["id"], out["named"]), ("EVL-B-8K-502", {"from": "EVL-8K-502", "to": "EVL-B-8K-502"}))


# ======================================================================================================== (2) roles
class AOneRoleList(unittest.TestCase):
    def test_a_one_role_list_reads_as_its_role_and_any_other_list_is_refused(self):
        for role in ("officer", "director"):
            listed = spec("EVL-B-INS-ONE", "ins-buy", {"value_min": 100000, "roles": [role]}, rank="value")
            plain = spec("EVL-B-INS-ONE", "ins-buy", {"value_min": 100000, "roles": role}, rank="value")
            self.assertEqual(BI.parse(listed)["rule"]["roles"], role)
            self.assertEqual((BI.canonical(listed), BI.sha(listed)), (BI.canonical(plain), BI.sha(plain)))
        for bad in (["director", "officer"], [], ["ten_pct"], [["officer"]], ["officer", "officer"], "ten_pct", 1,
                    {"role": "officer"}):
            with self.assertRaises(BI.SpecError, msg=repr(bad)) as caught:
                BI.parse(spec("EVL-B-INS-ONE", "ins-buy", {"value_min": 100000, "roles": bad}, rank="value"))
            self.assertEqual(caught.exception.reasons, ["roles must be director or officer (no role filter: leave it out)"])


# ======================================================================================================== (3) the prompt
class ThePrompt(unittest.TestCase):
    def test_the_prompt_shows_two_valid_specs_and_the_8k_line(self):
        eightk, news = BI.EXAMPLES
        for example in BI.EXAMPLES:
            parsed = BI.parse(example)
            self.assertEqual(BI.renamed(example), None, "the examples' ids are canonical")
            self.assertTrue(parsed["seatable"] and parsed["hold"] == 1)
            self.assertIn(json.dumps(example, separators=(", ", ": ")), BI.USER, "shown whole")
        self.assertEqual(eightk["family"], "8k")
        self.assertFalse(set(eightk["rule"]["items"]) & set(BI.READ_ITEMS_8K), "items outside READ_ITEMS")
        self.assertEqual(set(eightk["rule"]), {"items"}, "no score or guidance field")
        self.assertFalse(BI.reads(BI.parse(eightk)))
        self.assertEqual(news["family"], "news")
        text = BI.render({"sessions": 20}, {"used": 1.2, "limit": 3.0, "seatable_left_tonight": 3})
        self.assertIn('An 8k spec may carry score_min, score_max or guidance (or rank "score") only when every one of '
                      "its items is among\n  1.01, 2.01, 7.01, 8.01, and guidance is a list", text)
        self.assertIn('roles (one string, "director" or "officer")', text)
        self.assertIn("Every id starts\n  with EVL-B-.", text)
        self.assertNotIn("with a verdict field", text, "release 1019e's line that read as an object")
        self.assertNotIn("<<", text, "every placeholder filled")

    def test_the_prompt_sha_moved_and_a_prompt_change_is_a_new_parse_version(self):
        self.assertNotEqual(BI.prompt_sha(), PROMPT_1019E)
        self.assertEqual(BI.PARSE_VERSION, 5, "release 1019h's SUP-3 (A97: 3) and its architect on Opus 5.5 (A109: 4); "
                                              "release 1019i's restated charge (PREREG-EVL-6 section 5: 5)")
        self.assertEqual(BI.prompt_sha(), PROMPT_BY_VERSION[BI.PARSE_VERSION],
                         "the prompt changed: give it a new PARSE_VERSION (A95) and pin both here")


# ======================================================================================================== invented facts
class Replay(unittest.TestCase):
    """Twenty invented sessions through Wed Oct 21, 2026 (Sept 24 to Oct 21), each with: six earnings 8-Ks (four read
    -2 "lowered", two +2), four other 8-Ks (5.02 twice, 9.01, 3.01), six single-company articles (four at 06:10-06:40
    ET of the session, two at 19:00 ET the evening before) and four Form 4 buys (two by officers at $150,000, two by
    directors at $60,000). No bar, mark or outcome: the facts never read one. RELEASE 1019h (the captain's A97, SUP-3): a
    clean record pass every 10 minutes from Sept 22 to Oct 22 (every session holds a complete record pass), and a
    seatable birth's `MIN_RATE` at release 1019e's 3, the rate these figures were worked at (league/tests/
    test_events_births.py `SeatableRate` holds 20 over the complete-record sessions on its own sessions)."""

    AS_OF = NIGHT

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(TB.unload)
        self.s = TB.Synth(Path(self.tmp.name))
        self.addCleanup(self.s.st.close)
        st = self.s.st
        rate = mock.patch.object(BI, "MIN_RATE", 3)
        rate.start()
        self.addCleanup(rate.stop)
        TB.record_passes(st, et(dt.date(2026, 9, 22), 0), et(dt.date(2026, 10, 22), 23))
        self.days = [x.day for x in C.previous(st, self.AS_OF + dt.timedelta(days=1), 20)]
        self.assertEqual((self.days[0], self.days[-1], len(self.days)), (dt.date(2026, 9, 24), NIGHT, 20))
        syms = list(TB.ISSUERS.values())
        for sym in syms:
            self.s.eligible(self.days[0], sym)
        for day in self.days:
            prior = C.previous(st, day, 1)[0].day
            for k in range(6):
                acc = self.s.filing(syms[k], et(prior, 16, 30 + k))
                self.s.doc_verdict(acc, -2 if k < 4 else 2, "lowered" if k < 4 else "none")
            for k, item in enumerate(("5.02", "5.02", "9.01", "3.01")):
                self.s.filing(syms[6 + k], et(prior, 17, k), (item,))
            for k in range(4):
                self.s.article(syms[10 + k], et(day, 6, 10 * (k + 1)))
            for k in range(2):
                self.s.article(syms[14 + k], et(prior, 19, k))
            for k in range(2):
                self.s.insider(syms[16 + k], et(prior, 17, 30 + k), 150_000.0, director=False, officer=True)
                self.s.insider(syms[18 + k], et(prior, 17, 40 + k), 60_000.0, director=True, officer=False)


# ======================================================================================================== (5) the replay
class TheSixOfTheFirstNight(Replay):
    def test_the_six_replayed_ids_renamed_the_two_clean_specs_accepted_the_8k_reads_still_refused(self):
        st = self.s.st
        out = BI.validate(st, BI.Facts(st, self.AS_OF), SIX, night=self.AS_OF)
        self.assertEqual([c["named"]["to"] for c in out],
                         ["EVL-B-8K-ITEMS-5-O1", "EVL-B-8K-ITEMS-9-O1", "EVL-B-8K-ITEMS-3-O1", "EVL-B-ERN-NEGATIVE-O1",
                          "EVL-B-NEWS-EARLY-MORNING-O1", "EVL-B-INS-BUY-OFFICER-O1"], "every id renamed")
        self.assertEqual([c["named"]["from"] for c in out], [x["spec"]["id"] for x in SIX])
        # The three 8k specs: their score and guidance fields are still refused, the id no longer is.
        for c in out[:3]:
            self.assertFalse(c["ok"])
            self.assertEqual(len(c["reasons"]), 2, c["reasons"])
            self.assertTrue(c["reasons"][0].startswith(GUIDANCE_WHY), c["reasons"])
            self.assertEqual(c["reasons"][1], READ_ITEMS_WHY)
            self.assertFalse(any("id must match" in r for r in c["reasons"]))
        # The two refused for the id alone: accepted by the validator's counts and Jaccard on these invented facts.
        ern, news, ins = out[3], out[4], out[5]
        self.assertEqual([ern["ok"], news["ok"]], [True, True], (ern["reasons"], news["reasons"]))
        self.assertEqual((ern["id"], ern["selected"], ern["per_session"], ern["charge"]),
                         ("EVL-B-ERN-NEGATIVE-O1", 80, 4.0, 13))
        self.assertEqual(ern["jaccard"]["max"], round(80 / 120, 4),
                         "four of the six earnings 8-Ks a session: under the 0.8 duplicate line")
        self.assertIn(ern["jaccard"]["with"], ("EVL-CTRL-ERN-ALL-O1", "EVL-ERN-REACT-C1"), "a program of all six")
        self.assertEqual((news["id"], news["selected"], news["charge"]), ("EVL-B-NEWS-EARLY-MORNING-O1", 80, 13))
        self.assertEqual(news["jaccard"]["max"], round(80 / 120, 4))
        # The ins-buy's grammar passes now ("roles": ["officer"] reads as "officer"); the validator's count judges it.
        self.assertEqual((ins["ok"], ins["id"], ins["selected"]), (False, "EVL-B-INS-BUY-OFFICER-O1", 40))
        self.assertEqual(ins["reasons"], ["40 selected events over the 20 sessions of the last 20 with a complete record "
                                          "pass: under 3 a session"])
        self.assertEqual(json.loads(ins["spec"])["rule"], {"roles": "officer", "value_min": 100000})


# ======================================================================================================== (4) the re-run
class TheRerunOfAnEmptyNight(Replay):
    def docs(self, committed_at: str):
        posted = []

        def answer(body):
            posted.append(body)
            return 200, {"ok": True, "committed": True, "path": body["path"], "commit": "d" * 40,
                         "committed_at": committed_at, "lines": len(body["lines"]), "docs_today": 2}
        return answer, posted

    def first_night(self) -> int:
        """The night of Oct 21 as release 1019e's code left it: its receipt, its six refused candidates, its one call
        under release 1019e's prompt."""
        st = self.s.st
        stored_call(st, prompt=PROMPT_1019E)
        with st.tx() as db:
            for seq, x in enumerate(SIX):
                db.execute("INSERT INTO birth_candidates(night, seq, sha, id, spec, why, by, status, reasons, figures, "
                           "line, at) VALUES(?, ?, NULL, NULL, ?, ?, ?, 'refused', ?, ?, NULL, ?)",
                           (NIGHT.isoformat(), seq, json.dumps(x["spec"], sort_keys=True), x["why"],
                            f"architect:{BI.MODEL}", json.dumps(["id must match ..."]),
                            json.dumps({"selected": None, "per_session": None, "jaccard": None, "charge": 0}),
                            S.iso(RECEIPT_AT)))
        return old_receipt(st)

    def test_an_older_readings_empty_night_runs_once_more_its_call_inside_the_nights_cap(self):
        st = self.s.st
        rid = self.first_night()
        now = dt.datetime(2026, 10, 22, 11, 30, 5, tzinfo=UTC)
        due = BI.rerun_due(st, now)
        self.assertEqual(due, {"night": "2026-10-21", "of": [rid], "parse_version": 1, "until": "2026-10-22T12:55:00Z"})
        route, posted = self.docs("2026-10-22T11:30:09Z")
        gw = TB.FakeArchitect(json.dumps({"specs": SIX}), docs=route)      # (the same six, under the new prompt)
        out = BI.night(st, gw, today=NIGHT, now=lambda: now, rerun=due)
        self.assertEqual(out["_status"], "ok", out)
        # ONE new call, under the running prompt (its examples), never release 1019e's stored answer read again.
        [(path, body, headers)] = [c for c in gw.calls if c[0] == V.PATH]
        self.assertIn(json.dumps(BI.EXAMPLES[0], separators=(", ", ": ")), body["messages"][0]["content"])
        self.assertEqual(headers[V.REQUEST_HEADER], f"evl-births:2026-10-21:{BI.prompt_sha()[:12]}")
        self.assertEqual(sorted(r[0] for r in st.db.execute("SELECT prompt_sha FROM birth_calls WHERE night=?",
                                                             (NIGHT.isoformat(),))),
                         sorted([PROMPT_1019E, BI.prompt_sha()]))
        self.assertAlmostEqual(BI.spent(st, NIGHT), 0.0084 + 0.0042, msg="the night's first call counts in its cap")
        self.assertEqual(out["call"]["prompt_sha"], BI.prompt_sha())
        # The two clean specs accepted and registered at the later of GitHub's commit time and the House's receipt.
        self.assertEqual(out["accepted"], ["EVL-B-ERN-NEGATIVE-O1", "EVL-B-NEWS-EARLY-MORNING-O1"])
        [body] = posted
        self.assertEqual(body["path"], "docs/births/2026-10-21.jsonl", "the night's own file")
        lines = [json.loads(x) for x in body["lines"]]
        self.assertEqual([x["spec"]["id"] for x in lines], out["accepted"])
        self.assertEqual([x["sha"] for x in lines], [BI.sha(SIX[3]["spec"]), BI.sha(SIX[4]["spec"])])
        self.assertNotIn("EVL-ERN-NEGATIVE-O1", "".join(body["lines"]), "the line carries the House's name only")
        rows = [dict(r) for r in st.db.execute("SELECT id, registered_at, received_at, night FROM births ORDER BY seq")]
        self.assertEqual(rows, [{"id": i, "registered_at": "2026-10-22T11:30:09Z", "received_at": "2026-10-22T11:30:05Z",
                                 "night": "2026-10-21"} for i in out["accepted"]])
        # The candidate rows: seq after the night's first six, each keeping the proposed id and the House's name.
        cands = [dict(r) for r in st.db.execute("SELECT seq, id, status, figures FROM birth_candidates WHERE night=? "
                                                "AND seq >= 6 ORDER BY seq", (NIGHT.isoformat(),))]
        self.assertEqual([c["seq"] for c in cands], list(range(6, 12)))
        self.assertEqual([c["status"] for c in cands], ["refused"] * 3 + ["registered", "registered", "refused"])
        self.assertEqual([json.loads(c["figures"])["named"] for c in cands],
                         [{"from": x["spec"]["id"], "to": BI.canonical_name(x["spec"]["id"])} for x in SIX])
        # The receipt: the running reading, the re-run it was, the names.
        receipt = json.loads(st.db.execute("SELECT summary FROM receipts WHERE job='births' ORDER BY id DESC").fetchone()[0])
        self.assertEqual((receipt["night"], receipt["parse_version"], receipt["rerun"]),
                         ("2026-10-21", BI.PARSE_VERSION, due))
        self.assertEqual(receipt["named"]["EVL-B-INS-BUY-OFFICER-O1"], "EVL-INS-BUY-OFFICER-O1")
        # A re-run birth counts only events knowable after its registration (the morning of Oct 22, not the night).
        birth = next(p for p in P.BIRTHS if p.id == "EVL-B-ERN-NEGATIVE-O1")
        acc_early, acc_late = (self.s.filing("AAA", dt.datetime(2026, 10, 22, h, 0, tzinfo=UTC)) for h in (11, 12))
        for acc in (acc_early, acc_late):
            self.s.doc_verdict(acc, -3)
        rows8k = P.filings_in(st, "8-K", dt.datetime(2026, 10, 22, 2, tzinfo=UTC), dt.datetime(2026, 10, 22, 13, tzinfo=UTC))
        picked = BI.select(birth, rows8k, eligible=lambda cik: {"cik": cik, "symbol": "AAA"},
                           verdict=lambda row: -3)
        self.assertEqual([c.event for c in picked], [f"8k:{acc_late}"],
                         "the 11:10Z filing is before the 11:30:09Z registration; the 12:10Z one after it")
        # Never again: it accepted and it was the night's re-run.
        self.assertIsNone(BI.rerun_due(st, now + dt.timedelta(minutes=5)))

    def test_a_stored_answer_at_the_running_prompt_is_read_again_with_no_call(self):
        st = self.s.st
        rid = old_receipt(st)
        stored_call(st, prompt=BI.prompt_sha())        # (a parser change alone: the prompt the night was asked is ours)
        due = BI.rerun_due(st, dt.datetime(2026, 10, 22, 3, 0, tzinfo=UTC))
        self.assertEqual(due["of"], [rid])
        route, posted = self.docs("2026-10-22T03:00:04Z")
        gw = TB.FakeArchitect("{}", docs=route)
        out = BI.night(st, gw, today=NIGHT, now=lambda: dt.datetime(2026, 10, 22, 3, 0, tzinfo=UTC), rerun=due)
        self.assertEqual([c for c in gw.calls if c[0] == V.PATH], [], "no call: the stored answer is read again")
        self.assertEqual((out["call"]["status"], out["call"]["usd"]), ("stored:ok", 0.0084))
        self.assertEqual(out["accepted"], ["EVL-B-ERN-NEGATIVE-O1", "EVL-B-NEWS-EARLY-MORNING-O1"])
        self.assertEqual(len(posted), 1)

    def test_the_rerun_call_is_held_to_what_the_night_has_left(self):
        st = self.s.st
        old_receipt(st)
        stored_call(st, prompt=PROMPT_1019E, usd=0.24)
        due = BI.rerun_due(st, dt.datetime(2026, 10, 22, 3, 0, tzinfo=UTC))
        gw = TB.FakeArchitect(json.dumps({"specs": SIX}))
        out = BI.night(st, gw, today=NIGHT, now=lambda: dt.datetime(2026, 10, 22, 3, 0, tzinfo=UTC), rerun=due)
        self.assertEqual((out["call"]["status"], gw.calls), ("cap", []), "the night's $0.24 first call leaves too little")
        self.assertIn("over the night's $0.0100 left", out["call"]["why"])
        self.assertEqual(out["accepted"], [])
        self.assertIsNone(BI.rerun_due(st, dt.datetime(2026, 10, 22, 3, 5, tzinfo=UTC)), "at most one re-run a night")
        held = BI.night(st, gw, today=NIGHT, now=lambda: dt.datetime(2026, 10, 22, 3, 6, tzinfo=UTC),
                        rerun=dict(due), line_left=0.001)
        self.assertEqual(held["call"]["status"], "cap", "and to the lane's line, as `propose` always is")


class WhenTheNightIsDue(Replay):
    """`rerun_due`'s conditions, one at a time, on the first night's receipt as release 1019e wrote it."""

    def at(self, text: str) -> dt.datetime:
        return S.parse_iso(text)

    def test_until_1255z_of_the_session_day_after_the_night_a_weekend_included(self):
        st = self.s.st
        old_receipt(st)
        self.assertIsNotNone(BI.rerun_due(st, self.at("2026-10-22T02:30:00Z")), "the same evening")
        self.assertIsNotNone(BI.rerun_due(st, self.at("2026-10-22T12:54:59Z")))
        self.assertIsNone(BI.rerun_due(st, self.at("2026-10-22T12:55:00Z")), "the deploy-blocked window's start")
        self.assertIsNone(BI.rerun_due(st, self.at("2026-10-22T20:05:00Z")), "the evening deploy: the next night's")
        friday = dt.date(2026, 10, 23)
        old_receipt(st, night=friday, at=dt.datetime(2026, 10, 24, 1, 20, tzinfo=UTC))
        self.assertEqual(BI.rerun_due(st, self.at("2026-10-24T15:00:00Z"))["until"], "2026-10-26T12:55:00Z",
                         "a Friday night's: until Monday's 12:55Z")
        self.assertIsNotNone(BI.rerun_due(st, self.at("2026-10-26T12:54:00Z")))
        self.assertIsNone(BI.rerun_due(st, self.at("2026-10-26T12:55:00Z")))
        st.db.execute("DELETE FROM sessions WHERE day>?", (friday.isoformat(),))
        self.assertIsNone(BI.rerun_due(st, self.at("2026-10-24T15:00:00Z")), "no session after it known: never")

    def test_a_night_with_an_accepted_or_registered_birth_never_runs_again(self):
        st = self.s.st
        now = self.at("2026-10-22T03:00:00Z")
        rid = old_receipt(st, accepted=["EVL-B-X"])
        self.assertIsNone(BI.rerun_due(st, now), "its receipt names an accepted id")
        st.db.execute("UPDATE receipts SET summary=? WHERE id=?",
                      (json.dumps({"night": "2026-10-21", "accepted": []}), rid))
        self.assertIsNotNone(BI.rerun_due(st, now))
        for status in ("accepted", "unknown", "registered"):
            st.db.execute("INSERT INTO birth_candidates(night, seq, status, at) VALUES('2026-10-21', 99, ?, 'x')",
                          (status,))
            self.assertIsNone(BI.rerun_due(st, now), status)
            st.db.execute("DELETE FROM birth_candidates WHERE seq=99")
        st.db.execute("INSERT INTO birth_candidates(night, seq, status, at) VALUES('2026-10-21', 99, 'refused', 'x')")
        self.assertIsNotNone(BI.rerun_due(st, now), "refused rows are an empty night")
        self.s.register(spec("EVL-B-Y", "8k", {"items": ["5.02"]}), "2026-10-22T02:12:00Z", night="2026-10-21")
        self.assertIsNone(BI.rerun_due(st, now), "a birth registered for the night")

    def test_a_night_the_running_reading_wrote_or_re_ran_never_runs_again(self):
        st = self.s.st
        now = self.at("2026-10-22T03:00:00Z")
        old_receipt(st, parse_version=BI.PARSE_VERSION)
        self.assertIsNone(BI.rerun_due(st, now), "the running reading read this night already")
        self.assertIsNotNone(BI.rerun_due(st, now, version=BI.PARSE_VERSION + 1), "a newer one would read it again")
        st.db.execute("DELETE FROM receipts")
        old_receipt(st)
        old_receipt(st, at=dt.datetime(2026, 10, 22, 2, 40, tzinfo=UTC), rerun={"night": "2026-10-21"}, parse_version=1)
        self.assertIsNone(BI.rerun_due(st, now), "a night is re-run once")
        # A re-run that died running is the night's one re-run too: `night` writes its head when it starts.
        st.db.execute("DELETE FROM receipts")
        old_receipt(st)
        due = BI.rerun_due(st, now)
        with mock.patch.object(BI, "Facts", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                BI.night(st, TB.FakeArchitect("{}"), today=NIGHT, now=lambda: now, rerun=due)
        [running] = [dict(r) for r in st.db.execute("SELECT status, summary FROM receipts WHERE status='running'")]
        self.assertEqual(json.loads(running["summary"]), {"night": "2026-10-21", "parse_version": BI.PARSE_VERSION,
                                                          "rerun": due})
        self.assertIsNone(BI.rerun_due(st, now))

    def test_only_the_latest_night_and_only_within_reach(self):
        st = self.s.st
        old_receipt(st)                                                          # Wed Oct 21 (empty, older reading)
        old_receipt(st, night=dt.date(2026, 10, 22), at=dt.datetime(2026, 10, 23, 1, 20, tzinfo=UTC),
                    parse_version=BI.PARSE_VERSION)                             # Thu Oct 22 by the running reading
        self.assertIsNone(BI.rerun_due(st, self.at("2026-10-23T03:00:00Z")), "the latest night is Thursday's")
        st.db.execute("DELETE FROM receipts")
        old_receipt(st)
        self.assertIsNone(BI.rerun_due(st, self.at("2026-11-02T03:00:00Z")), "out of reach (and past its cut-off)")
        st.db.execute("INSERT INTO receipts(job, started_at, status, summary) VALUES('births', ?, 'ok', 'not json')",
                      (S.iso(RECEIPT_AT),))
        self.assertIsNotNone(BI.rerun_due(st, self.at("2026-10-22T03:00:00Z")), "an unreadable summary is passed over")


# ======================================================================================================== the House's lane
class BirthsGateway(TH.FakeGateway):
    """The House's fake gateway with R3's births answer (`births`) for the architect's call and the docs route."""

    def __init__(self, births: str = '{"specs": []}'):
        super().__init__()
        self.births = births
        self.docs = []

    def post_json(self, path, body, headers=None):
        if path == BI.DOCS_ROUTE:
            self.docs.append(body)
            return 200, {"ok": True, "committed": True, "path": body["path"], "commit": "d" * 40,
                         "committed_at": "2026-10-20T11:05:30Z", "lines": len(body["lines"])}
        if isinstance(body, dict) and body.get("system") == BI.SYSTEM:
            self.claude_calls.append(body)
            self.last_headers = {V.COST_HEADER: "0.0042"}
            return 200, {"content": [{"type": "text", "text": self.births}], "stop_reason": "end_turn"}
        return super().post_json(path, body, headers)


class TheHousesRerun(TH.LaneCase):
    """Tue Oct 20, 2026 in the House's lane harness (Monday Oct 19's score, screen and report as the House made them):
    Monday night's births receipt as release 1019e's code wrote it, and the lane on this code the next morning."""

    def setUp(self):
        super().setUp()
        self.addCleanup(TB.unload)
        self.gw = BirthsGateway()
        with self.store() as st:
            self.first = old_receipt(st, night=dt.date(2026, 10, 19), at=TH.et("2026-10-19", "21:16"))

    def turns(self, *walls: str, day: str = "2026-10-20") -> list:
        out = []
        for wall in walls:
            self.at(TH.et(day, wall))
            self.mark_recorded()
            out.append(self.turn().get("task"))
        return out

    def births_calls(self) -> list:
        return [c for c in self.gw.claude_calls if c.get("system") == BI.SYSTEM]

    def test_an_older_readings_empty_night_runs_once_more_the_next_morning(self):
        self.lane = self.new_lane(births=True)
        tasks = self.turns("07:05", "07:06", "07:20")
        self.assertEqual(tasks[0], "births")
        self.assertNotIn("births", tasks[1:], "at most one re-run a night")
        first, again = self.receipts("births")
        self.assertEqual(first["id"], self.first)
        summary = json.loads(again["summary"])
        self.assertEqual((again["status"], summary["night"], summary["parse_version"]),
                         ("ok", "2026-10-19", BI.PARSE_VERSION))
        self.assertEqual(summary["rerun"], {"night": "2026-10-19", "of": [self.first], "parse_version": 1,
                                            "until": "2026-10-20T12:55:00Z"})
        [call] = self.births_calls()
        self.assertIn("TWO VALID SPECS", call["messages"][0]["content"], "asked under the running prompt")
        self.assertEqual(self.lane._tasks["births"]["summary"]["rerun"], True)
        # Tuesday's own births night is the regular job's, at 21:15 ET, at the running reading.
        with self.store() as st:
            for job, wall in (("score", "20:31"), ("screen", "20:32")):
                rid = st.start_receipt(job, now=TH.et("2026-10-20", wall))
                st.finish_receipt(rid, "ok", {"day": "2026-10-20"}, now=TH.et("2026-10-20", wall))
            (st.root / "reports" / "2026-10-20.txt").write_text("Tuesday's report\n", encoding="utf-8")
            st.set_meta(TH.SC.equity_key(dt.date(2026, 10, 20)), repr(2000.0))
        for kind, wall in (("open", "09:15"), ("close", "15:46")):
            with self.store() as st:
                rid = st.start_receipt(f"decide-{kind}:2026-10-20", now=TH.et("2026-10-20", wall))
                st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-20", wall))
        self.assertIn("births", self.turns("21:16", "21:17"))
        self.assertEqual(json.loads(self.receipts("births")[-1]["summary"])["parse_version"], BI.PARSE_VERSION)
        self.assertEqual(len(self.receipts("births")), 3)
        self.assertNotIn("births", self.turns("07:05", "08:00", day="2026-10-21"),
                         "a night the running reading wrote never runs again")

    def test_never_from_1255z_of_the_session_day_after_the_night(self):
        self.lane = self.new_lane(births=True)
        self.assertNotIn("births", self.turns("08:55", "09:00", "11:00"), "08:55 ET is 12:55Z in October")
        self.assertEqual(len(self.receipts("births")), 1)
        self.assertEqual(self.births_calls(), [])

    def test_a_stored_answer_at_the_running_prompt_is_read_again_with_no_call(self):
        with self.store() as st:
            stored_call(st, prompt=BI.prompt_sha(), night=dt.date(2026, 10, 19), answer='{"specs": []}')
        self.lane = self.new_lane(births=True)
        self.assertIn("births", self.turns("08:50", "08:51", "08:52"), "(after the open decision's verdicts)")
        self.assertEqual(self.births_calls(), [], "no call: the night's stored answer is the running prompt's")
        self.assertEqual(json.loads(self.receipts("births")[-1]["summary"])["call"]["status"], "stored:ok")

    def test_a_night_with_an_accepted_birth_or_at_the_running_reading_never_runs_again(self):
        with self.store() as st:
            st.db.execute("UPDATE receipts SET summary=? WHERE id=?",
                          (json.dumps({"night": "2026-10-19", "accepted": ["EVL-B-X"]}), self.first))
        self.lane = self.new_lane(births=True)
        self.assertNotIn("births", self.turns("07:05", "07:06"))
        with self.store() as st:
            st.db.execute("UPDATE receipts SET summary=? WHERE id=?",
                          (json.dumps({"night": "2026-10-19", "accepted": [], "parse_version": BI.PARSE_VERSION}),
                           self.first))
        self.assertNotIn("births", self.turns("07:10", "07:11"))
        self.assertEqual((len(self.receipts("births")), self.births_calls()), (1, []))

    def test_off_by_default(self):
        self.assertNotIn("births", self.turns("07:05", "07:06"))
        self.assertEqual(len(self.receipts("births")), 1)


if __name__ == "__main__":
    unittest.main()
