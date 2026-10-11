"""RELEASE E4, PACKAGE A: the `equity_universe` job (league/ops/equity_universe.py): the point-in-time membership
from a free source, the changes table read through the gateway's reader, the assets (D2, D2r), membership (D3), the
tradable union (section 11) and the audit.

EVERYTHING HERE IS FAKE: the tickers are made-up letter strings, the spell file, the changes article and the venue's
answers are built in the test, and a recording fake gateway stands for the reader and the venue. No membership
history, no price and no market row is in this file or read by it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from league.ops import equity_universe as U
from league.ops.context import Context, GatewayError
from league.xs import config as xs_config
from league.xs import store as xs_store

D = dt.date
VENUE_OK = {"id": "fake", "symbol": "X", "status": "active", "tradable": True, "fractionable": True,
            "exchange": "FAKE"}
#: A clock after a close and outside every wall: Friday 2022-04-01 01:45Z (Thursday 2022-03-31's session is closed).
NOW = dt.datetime(2022, 4, 1, 1, 45, tzinfo=dt.timezone.utc).timestamp()
LAST = D(2022, 3, 31)


def name(k: int) -> str:
    """A made-up ticker: Q and three letters (no real symbol is meant)."""
    return "Q" + "".join(chr(ord("A") + (k // 26 ** p) % 26) for p in (2, 1, 0))


def fake_file(spells) -> str:
    lines = ["ticker,start_date,end_date"]
    for ticker, start, end in spells:
        lines.append(f"{ticker},{start.isoformat()},{'' if end is None else end.isoformat()}")
    return "\n".join(lines) + "\n"


def fake_index(n: int = 500, *, changes=()) -> list[tuple]:
    """`n` made-up members from 2010, with `changes` [(day, added, removed)] already in the file."""
    spells = {name(k): [name(k), D(2010, 1, 4), None] for k in range(n)}
    for day, added, removed in changes:
        if removed:
            spells[removed][2] = day
        if added:
            spells[added] = [added, day, None]
    return [tuple(s) for s in spells.values()]


def fake_table(rows, *, closed: bool = True, refs: bool = True) -> str:
    """A changes table in wikitext, newest first: rows (day, added, removed, reason)."""
    out = ["Some lead text with a [[link|label]] and a note.<ref>{{cite web |title=a | b}}</ref>", "",
           '{| class="wikitable sortable" id="changes"', "|-",
           '! data-sort-type="date" rowspan="2" | Effective Date', '! colspan="2" | Added', '! colspan="2" | Removed',
           '! rowspan="2" | Reason', '! rowspan="2" | Refs', "|-", "! Ticker || Security || Ticker || Security"]
    for day, added, removed, reason in rows:
        out.append("|-")
        out.append(f"|{day.strftime('%B')} {day.day}, {day.year}")
        out.append(f"|{added or ''}")
        out.append(f"|[[Fake {added} Corp|{added} Corp]]" if added else "|")
        out.append(f"|{removed or ''}")
        out.append(f"|[[Fake {removed} Corp]]" if removed else "|")
        out.append(f"|{reason}")
        out.append('|<ref name=":1">{{Cite web |title=Fake press release | url=https://example.invalid/x |date=x}}</ref>'
                   if refs else "|")
    if closed:
        out.append("|}")
        out.append("")
        out.append("==See also==")
    return "\n".join(out)


def parse_answer(wikitext: str, revid: int = 777) -> str:
    return json.dumps({"parse": {"title": "Fake", "pageid": 1, "revid": revid, "wikitext": wikitext}})


def sections_answer(lines=()) -> str:
    return json.dumps({"parse": {"title": "Fake", "pageid": 1,
                                 "sections": [{"index": str(i + 1), "line": line} for i, line in enumerate(lines)]}})


class FakeGateway:
    """The reader (`post`) and the venue (`get`), recording every call. `pages`: {url or a function of the url: the
    reader's answer, a text, or an exception}."""

    def __init__(self):
        self.pages: dict[str, object] = {}
        self.venue: dict[str, object] = {}
        self.bars = None
        self.calls: list[tuple] = []

    def page(self, url: str, text, *, status: int = 200, truncated: bool = False) -> None:
        self.pages[url] = text if isinstance(text, BaseException) else {
            "url": url, "final_url": url, "status": status, "content_type": "text/plain", "title": "", "text": text,
            "truncated": truncated, "bytes": len(text), "fetched_at": "x"}

    def post(self, path: str, body):
        self.calls.append(("POST", path, dict(body)))
        assert path == U.WEB and set(body) == {"url", "agent"} and body["agent"] == U.AGENT, body
        answer = self.pages.get(body["url"])
        if answer is None:
            raise GatewayError(f"POST {path}: HTTP 502 no such fake page", status=502)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def get(self, path: str, params=None):
        self.calls.append(("GET", path, dict(params or {})))
        if path.startswith(U.ASSETS):
            symbol = urllib.parse.unquote(path[len(U.ASSETS):])
            answer = self.venue.get(symbol, GatewayError("GET: HTTP 404 asset not found", status=404))
            if isinstance(answer, BaseException):
                raise answer
            return {**answer, "symbol": symbol} if isinstance(answer, dict) else answer
        if self.bars is not None:
            return self.bars(path, dict(params or {}))
        raise AssertionError(f"an unexpected GET {path}")

    def posts(self) -> list[str]:
        return [c[2]["url"] for c in self.calls if c[0] == "POST"]

    def gets(self, prefix: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == "GET" and c[1].startswith(prefix)]


def fake_bars(path: str, params: dict) -> dict:
    """A made-up venue: every symbol its own closes (no two companies agree), on the sessions asked for."""
    assert path == "/v1/alpaca/v2/stocks/bars", path
    out = {}
    for symbol in params["symbols"].split(","):
        base = 20.0 + sum(ord(c) for c in symbol) % 60
        days = [d for d, _ in U.store_sessions(D.fromisoformat(params["end"])) if d.isoformat() >= params["start"]]
        out[symbol] = [{"t": f"{d.isoformat()}T05:00:00Z", "o": base, "h": base + 1, "l": base - 1,
                        "c": round(base + 0.01 * k, 2), "v": 1000} for k, d in enumerate(days)]
    return {"bars": out, "next_page_token": None}


def wiki_urls(page: str = U.WIKI_PAGES[0]) -> dict[str, str]:
    return {"sections": U._wiki_url(page, sections=True), "lead": U._wiki_url(page, section=0),
            "whole": U._wiki_url(page)}


class ParseSpells(unittest.TestCase):
    def test_the_rows_of_the_file(self):
        text = "ticker,start_date,end_date\nqaaa,2010-01-04,\nQAAB,2011-03-01,2017-06-19\n\nBRK-B,2010-01-04,\n"
        self.assertEqual(U.parse_spells(text), [("QAAA", D(2010, 1, 4), None), ("QAAB", D(2011, 3, 1), D(2017, 6, 19)),
                                                ("BRK.B", D(2010, 1, 4), None)])
        self.assertEqual(U.known_through(U.parse_spells(text)), D(2017, 6, 19))

    def test_a_malformed_row_is_named_by_its_number_never_its_content(self):
        for bad in ("QAAA\n", "QAAA,2010-01-04,2009-01-01\n", "QAAA,notaday,\n", "Q1,2010-01-04,\n", "a,b,c,d\n"):
            with self.assertRaises(ValueError) as caught:
                U.parse_spells("ticker,start_date,end_date\nQZZZ,2010-01-04,\n" + bad)
            self.assertIn("row 3", str(caught.exception))
            self.assertNotIn("QAAA", str(caught.exception))
        with self.assertRaises(ValueError):
            U.parse_spells("ticker,start_date,end_date\n")


class AppendOnly(unittest.TestCase):
    """A new pin may only end open spells after `known_through` and add spells starting after it."""

    OLD = [("QAAA", D(2010, 1, 4), None), ("QAAB", D(2010, 1, 4), D(2018, 5, 1)), ("QAAC", D(2000, 1, 3), D(2014, 2, 3))]
    THROUGH = D(2018, 5, 1)

    def test_the_old_file_grown_has_no_problem(self):
        self.assertEqual(U.append_only(self.OLD, self.OLD, self.THROUGH), [])
        grown = [("QAAA", D(2010, 1, 4), D(2019, 2, 1)), self.OLD[1], self.OLD[2], ("QAAD", D(2019, 2, 1), None)]
        self.assertEqual(U.append_only(self.OLD, grown, self.THROUGH), [])

    def test_an_open_spell_ended_on_or_before_the_old_last_date_is_a_problem(self):
        changed = [("QAAA", D(2010, 1, 4), D(2018, 5, 1)), self.OLD[1], self.OLD[2]]
        self.assertEqual(len(U.append_only(self.OLD, changed, self.THROUGH)), 1)

    def test_a_new_spell_starting_on_or_before_it_is_a_problem(self):
        self.assertEqual(len(U.append_only(self.OLD, [*self.OLD, ("QAAD", D(2018, 5, 1), None)], self.THROUGH)), 1)
        self.assertEqual(U.append_only(self.OLD, [*self.OLD, ("QAAD", D(2018, 5, 2), None)], self.THROUGH), [])

    def test_a_past_spell_changed_or_gone_is_a_problem(self):
        moved = [self.OLD[0], ("QAAB", D(2010, 1, 4), D(2018, 4, 30)), self.OLD[2]]
        self.assertEqual(len(U.append_only(self.OLD, moved, self.THROUGH)), 1, "one spell, another end")
        self.assertEqual(len(U.append_only(self.OLD, [self.OLD[0], self.OLD[2]], self.THROUGH)), 1)

    def test_a_difference_confined_to_spells_that_ended_before_2016_is_not_one(self):
        """Upstream corrects old dates: no panel session reads them, and the pin must not freeze for good on one."""
        corrected = [self.OLD[0], self.OLD[1], ("QAAC", D(2000, 1, 4), D(2014, 2, 4)), ("QAAE", D(1999, 1, 4), D(2001, 1, 2))]
        self.assertEqual(U.append_only(self.OLD, corrected, self.THROUGH), [])
        into_the_store = [self.OLD[0], self.OLD[1], ("QAAC", D(2000, 1, 3), D(2016, 2, 3))]
        self.assertEqual(len(U.append_only(self.OLD, into_the_store, self.THROUGH)), 1)


class LatestCommit(unittest.TestCase):
    SHA = "0123456789abcdef0123456789abcdef01234567"

    def test_the_commits_api(self):
        gateway = FakeGateway()
        gateway.page(U.COMMITS, json.dumps([{"sha": self.SHA, "commit": {}}]))
        self.assertEqual(U.latest_commit(gateway), self.SHA)
        self.assertEqual(gateway.posts(), [U.COMMITS])

    def test_the_atom_feed_when_the_api_refuses(self):
        gateway = FakeGateway()
        gateway.pages[U.COMMITS] = GatewayError("POST: HTTP 403 rate limit", status=403)
        gateway.page(U.ATOM, f"<feed><entry><id>tag:github.com,2008:Grit::Commit/{self.SHA}</id></entry></feed>",
                     truncated=True)
        self.assertEqual(U.latest_commit(gateway), self.SHA)
        self.assertEqual(gateway.posts(), [U.COMMITS, U.ATOM])

    def test_none_when_neither_answers(self):
        gateway = FakeGateway()
        gateway.page(U.COMMITS, "[]")
        gateway.page(U.ATOM, "<feed></feed>")
        self.assertIsNone(U.latest_commit(gateway))


class TheReader(unittest.TestCase):
    def test_a_refusal_a_bad_status_and_a_cut_page_are_value_errors(self):
        gateway = FakeGateway()
        gateway.page("https://example.invalid/a", "text")
        gateway.page("https://example.invalid/b", "text", status=404)
        gateway.page("https://example.invalid/c", "text", truncated=True)
        self.assertEqual(U.web(gateway, "https://example.invalid/a"), "text")
        for url in ("https://example.invalid/b", "https://example.invalid/c", "https://example.invalid/none"):
            with self.assertRaises(ValueError):
                U.web(gateway, url)
        self.assertEqual(U.web(gateway, "https://example.invalid/c", allow_truncated=True), "text")

    def test_the_refusals_text_never_carries_the_gateways_own(self):
        gateway = FakeGateway()
        gateway.pages["https://example.invalid/x"] = GatewayError("POST /v1/web/fetch: HTTP 403 secret-looking", status=403)
        with self.assertRaises(ValueError) as caught:
            U.web(gateway, "https://example.invalid/x")
        self.assertNotIn("secret-looking", str(caught.exception))
        self.assertIn("403", str(caught.exception))


class TheChangesTable(unittest.TestCase):
    ROWS = [(D(2022, 3, 21), "QZZA", "QAAA", "Market capitalization change."),
            (D(2022, 3, 1), "QZZB", "QAAB", "Fake Holdings acquired QAAB Corp."),
            (D(2021, 6, 4), None, "QAAC", "QAAC was taken private."),
            (D(2021, 6, 1), "QZZC", None, "Spun off from QAAD."),
            (D(2018, 3, 19), "QZZD", "QAAE", "Market capitalization change.")]

    def test_every_row_of_a_whole_table(self):
        table = U.parse_changes(fake_table(self.ROWS))
        self.assertEqual([(r["date"], r["added"], r["removed"]) for r in table["rows"]],
                         [(d, a, r) for d, a, r, _ in self.ROWS])
        self.assertEqual(table["rows"][1]["reason"], "Fake Holdings acquired QAAB Corp.")
        self.assertEqual((table["reach"], table["closed"], table["malformed"]), (D(2018, 3, 19), True, 0))

    def test_rowspans_inline_cells_and_markup(self):
        text = "\n".join([
            '{| class="wikitable"', "|-", "! Date !! Added !! Security !! Removed !! Security !! Reason", "|-",
            '| rowspan="2" | {{dts|2022|3|21}} || QZZA || [[A]] || QAAA || [[B]] || rowspan="2" | One reason<ref>x | y</ref>',
            "|-", "| {{NYSE link|QZZB}} || [[C]] || QAAB |", "| [[D|d]]", "|-",
            "|| March 1, 2022", "|| qzzc", "|| [[E]]", "|| ", "|| ", "|| '''Bold''' &amp; plain<ref name=x />", "|}"])
        table = U.parse_changes(text)
        self.assertEqual([(r["date"], r["added"], r["removed"], r["reason"]) for r in table["rows"]],
                         [(D(2022, 3, 21), "QZZA", "QAAA", "One reason"), (D(2022, 3, 21), "QZZB", "QAAB", "One reason"),
                          (D(2022, 3, 1), "QZZC", None, "Bold & plain")])

    def test_a_cut_table_gives_only_the_complete_rows_above_the_cut(self):
        whole = fake_table(self.ROWS)
        cut = whole[:whole.index("QAAC was taken") + 4]  # mid-row: the third row's reason is half written
        table = U.parse_changes(cut)
        self.assertEqual(len(table["rows"]), 2)
        self.assertEqual((table["reach"], table["closed"]), (D(2022, 3, 1), False))
        # a cut exactly after a row's last line still drops that row: nothing says it was whole
        self.assertEqual(len(U.parse_changes(fake_table(self.ROWS[:3], closed=False))["rows"]), 2)

    def test_a_malformed_row_ends_what_the_read_can_vouch_for(self):
        rows = [self.ROWS[0], (D(2022, 3, 1), "not a ticker!", "QAAB", "x"), self.ROWS[4]]
        table = U.parse_changes(fake_table(rows))
        self.assertEqual((len(table["rows"]), table["malformed"], table["reach"]), (2, 1, D(2022, 3, 21)),
                         "the older row is read, and the reach stops above the row that was not")

    def test_no_table_is_a_value_error(self):
        with self.assertRaises(ValueError):
            U.parse_changes("no table here\n{| class=x\n|-\n! Symbol !! Security\n|-\n| QAAA || x\n|}")

    def test_the_wikitext_of_a_cut_answer(self):
        answer = parse_answer(fake_table(self.ROWS) + "\n\"quoted\" \\ back é \U0001F600 end")
        text, whole, revid = U._wikitext(answer)
        self.assertEqual((text, whole, revid), (json.loads(answer)["parse"]["wikitext"], True, 777))
        for at in (len(answer) // 2, len(answer) - 3, answer.index("\\u") + 3):
            text, whole, revid = U._wikitext(answer[:at])
            self.assertFalse(whole)
            self.assertTrue(json.loads(answer)["parse"]["wikitext"].startswith(text))
        with self.assertRaises(ValueError):
            U._wikitext('{"error": {"code": "missingtitle"}}')

    def test_the_articles_are_tried_in_order_and_the_table_found_by_its_header(self):
        gateway = FakeGateway()
        first, second = wiki_urls(U.WIKI_PAGES[0]), wiki_urls(U.WIKI_PAGES[1])
        gateway.page(first["sections"], sections_answer(["See also"]))
        gateway.page(first["lead"], parse_answer("no table in this lead"))
        gateway.page(first["whole"], parse_answer("{| class=x\n|-\n! Symbol\n|-\n| QAAA\n|}"))
        gateway.page(second["sections"], sections_answer(["Components", "Selected changes to the list"]))
        gateway.page(U._wiki_url(U.WIKI_PAGES[1], section=2), parse_answer(fake_table(self.ROWS), revid=42))
        read = U.wiki_changes(gateway)
        self.assertEqual((len(read["rows"]), read["reach"], read["complete"], read["revid"], read["page"]),
                         (5, D(2018, 3, 19), True, 42, U.WIKI_PAGES[1]))
        self.assertEqual(gateway.posts(), [first["sections"], first["lead"], first["whole"], second["sections"],
                                           U._wiki_url(U.WIKI_PAGES[1], section=2)])

    def test_a_truncated_answer_is_read_and_is_not_complete(self):
        gateway = FakeGateway()
        urls = wiki_urls()
        answer = parse_answer(fake_table(self.ROWS))
        gateway.page(urls["sections"], sections_answer([]))
        gateway.page(urls["lead"], answer[:answer.index("QZZD")], truncated=True)
        read = U.wiki_changes(gateway)
        self.assertEqual((len(read["rows"]), read["complete"], read["reach"]), (4, False, D(2021, 6, 1)))

    def test_no_article_with_a_table_is_a_value_error(self):
        with self.assertRaises(ValueError):
            U.wiki_changes(FakeGateway())


class Extend(unittest.TestCase):
    """A row applies when its removed ticker is a member and its added one is not, once two runs at least 20 hours
    apart have both read it."""

    SPELLS = [("QAAA", D(2010, 1, 4), None), ("QAAB", D(2010, 1, 4), None), ("QAAC", D(2010, 1, 4), D(2022, 2, 1)),
              ("QAAD", D(2022, 2, 1), None)]
    ROW = {"date": D(2022, 3, 21), "added": "QZZA", "removed": "QAAA", "reason": "x"}

    def seen(self, hours: float, row=None) -> dict:
        return {U.row_key(row or self.ROW): {"first": 1000.0, "last": 1000.0 + hours * 3600}}

    def test_a_row_read_once_waits(self):
        self.assertEqual(U.extend(self.SPELLS, [self.ROW], {}), sorted(self.SPELLS))
        self.assertEqual(U.extend(self.SPELLS, [self.ROW], self.seen(19.9)), sorted(self.SPELLS))
        self.assertEqual(U.apply_changes(self.SPELLS, [self.ROW], self.seen(19.9))[2]["pending"], 1)

    def test_a_row_two_runs_twenty_hours_apart_have_read_applies(self):
        spells = U.extend(self.SPELLS, [self.ROW], self.seen(20))
        self.assertIn(("QAAA", D(2010, 1, 4), D(2022, 3, 21)), spells, "the removed spell ends on the row's date")
        self.assertIn(("QZZA", D(2022, 3, 21), None), spells, "the added one starts on it")
        self.assertEqual(len(spells), len(self.SPELLS) + 1)

    def test_a_row_on_or_before_the_files_last_date_is_the_files_own(self):
        row = {**self.ROW, "date": D(2022, 2, 1)}
        self.assertEqual(U.extend(self.SPELLS, [row], self.seen(48, row)), sorted(self.SPELLS))

    def test_a_row_the_spells_already_show_and_a_conflict_apply_nothing(self):
        shown = {"date": D(2022, 3, 21), "added": "QAAD", "removed": "QAAC", "reason": "x"}
        half = {"date": D(2022, 3, 21), "added": "QAAB", "removed": "QAAA", "reason": "x"}  # the added one is in already
        for row, kind in ((shown, "already"), (half, "conflict")):
            spells, applied, counts = U.apply_changes(self.SPELLS, [row], self.seen(48, row))
            self.assertEqual((spells, applied, counts[kind]), (sorted(self.SPELLS), [], 1))

    def test_one_sided_rows_and_the_order_of_dates(self):
        rows = [{"date": D(2022, 4, 4), "added": "QAAA", "removed": None, "reason": "back"},
                {"date": D(2022, 3, 21), "added": None, "removed": "QAAA", "reason": "out"}]
        spells, applied, _ = U.apply_changes(self.SPELLS, rows, None)
        self.assertIn(("QAAA", D(2010, 1, 4), D(2022, 3, 21)), spells)
        self.assertIn(("QAAA", D(2022, 4, 4), None), spells)
        self.assertEqual(applied, [U.row_key(rows[1]), U.row_key(rows[0])])


class Exits(unittest.TestCase):
    """How a spell ended: a membership fact from the change row's reason, never a price."""

    def test_deal_other_unknown(self):
        spells = [("QAAA", D(2010, 1, 4), D(2018, 6, 5)), ("QAAB", D(2010, 1, 4), D(2018, 6, 5)),
                  ("QAAC", D(2010, 1, 4), D(2018, 6, 5)), ("QAAD", D(2010, 1, 4), None)]
        rows = [{"date": D(2018, 6, 7), "added": "QZZA", "removed": "QAAA", "reason": "Fake Corp ACQUIRED QAAA."},
                {"date": D(2018, 6, 1), "added": "QZZB", "removed": "QAAB", "reason": "Market capitalization change."},
                {"date": D(2018, 6, 11), "added": "QZZC", "removed": "QAAC", "reason": "A merger, six days off."}]
        self.assertEqual(U.exits(spells, rows), {("QAAA", D(2018, 6, 5)): "deal", ("QAAB", D(2018, 6, 5)): "other",
                                                 ("QAAC", D(2018, 6, 5)): "unknown"})

    def test_every_word_of_the_deal_pattern_and_the_nearest_row(self):
        for reason in ("acquired by X", "Merger with X", "taken PRIVATE", "a leveraged buyout", "takeover", "tender offer"):
            self.assertTrue(xs_config.VANISH_DEAL.search(reason), reason)
        spells = [("QAAA", D(2010, 1, 4), D(2018, 6, 5))]
        rows = [{"date": D(2018, 6, 9), "added": None, "removed": "QAAA", "reason": "merger"},
                {"date": D(2018, 6, 5), "added": None, "removed": "QAAA", "reason": "index rebalance"}]
        self.assertEqual(U.exits(spells, rows), {("QAAA", D(2018, 6, 5)): "other"})


class TheVenue(unittest.TestCase):
    def test_a_row_none_for_a_symbol_it_does_not_know_and_a_retry(self):
        gateway = FakeGateway()
        gateway.venue["QAAA"] = dict(VENUE_OK, id="abc", fractionable=False, extra="dropped")
        waits = []
        self.assertEqual(U.assets(gateway, ["qaaa", "QAAB"], sleep=waits.append),
                         {"QAAA": {"id": "abc", "status": "active", "tradable": True, "fractionable": False,
                                   "exchange": "FAKE"}, "QAAB": None})
        self.assertEqual([c[1] for c in gateway.gets(U.ASSETS)], [U.ASSETS + "QAAA", U.ASSETS + "QAAB"])
        gateway.venue["QAAC"] = GatewayError("GET: HTTP 500", status=500)
        with self.assertRaises(GatewayError):
            U.assets(gateway, ["QAAC"], sleep=waits.append)
        self.assertEqual(waits, [5, 20], "three tries, backing off 5 then 20 seconds")
        self.assertEqual(len(gateway.gets(U.ASSETS + "QAAC")), 3)

    def test_a_ticker_the_path_cannot_name_is_refused_unsent(self):
        gateway = FakeGateway()
        with self.assertRaises(ValueError):
            U.assets(gateway, ["../account"])
        self.assertEqual(gateway.calls, [])


class Assign(unittest.TestCase):
    """D2: REF aids 1..12; member aids from 100 by (first spell start, ticker), never reused, never renumbered."""

    SPELLS = [("QAAB", D(2012, 5, 1), None), ("QAAA", D(2012, 5, 1), D(2018, 3, 1)), ("QAAC", D(2010, 1, 4), None),
              ("QOLD", D(2001, 1, 2), D(2015, 6, 1)), ("QRES", D(2020, 2, 3), D(2020, 11, 2))]

    def test_ref_first_then_members_by_first_start_and_ticker(self):
        table = U.assign(self.SPELLS, None, [])
        self.assertEqual([table[str(k)]["symbol"] for k in range(1, 13)], list(xs_config.REF))
        self.assertTrue(all(table[str(k)]["ref"] and table[str(k)]["spells"] == [] for k in range(1, 13)))
        self.assertEqual({aid: row["symbol"] for aid, row in table.items() if not row["ref"]},
                         {"100": "QAAC", "101": "QAAA", "102": "QAAB"})
        self.assertEqual(table["101"]["spells"], [["QAAA", "2012-05-01", "2018-03-01", "unknown"]])
        self.assertEqual(U.columns(table), [*range(1, 13), 100, 101, 102])

    def test_a_spell_with_no_day_the_store_can_hold_is_no_asset(self):
        table = U.assign(self.SPELLS, None, [])
        symbols = {row["symbol"] for row in table.values()}
        self.assertNotIn("QOLD", symbols, "ended before the store begins")
        self.assertNotIn("QRES", symbols, "a member only in 2020, which the store never holds")
        self.assertTrue(U.in_store(D(2019, 6, 3), D(2020, 6, 1)))
        self.assertFalse(U.in_store(D(2020, 1, 2), D(2021, 1, 4)), "the end day is no member day")
        self.assertTrue(U.in_store(D(2020, 1, 2), D(2021, 1, 5)))

    def test_a_later_run_keeps_every_aid_and_a_new_asset_goes_above_them_all(self):
        first = U.assign(self.SPELLS, None, [])
        again = U.assign([*self.SPELLS, ("QNEW", D(2009, 1, 5), None)], first, [])
        for aid, row in first.items():
            self.assertEqual(again[aid]["spells"], row["spells"], aid)
        self.assertEqual(again["103"]["symbol"], "QNEW", "above them all, whatever its dates")
        self.assertEqual(U.assign([*self.SPELLS, ("QNEW", D(2009, 1, 5), None)], again, []), again)

    def test_an_asset_the_spells_no_longer_show_keeps_its_aid_and_is_a_member_nowhere(self):
        first = U.assign(self.SPELLS, None, [])
        fewer = U.assign([s for s in self.SPELLS if s[0] != "QAAA"] + [("QNEW", D(2021, 3, 1), None)], first, [])
        self.assertEqual((fewer["101"]["spells"], fewer["101"]["symbol"]), ([], "QAAA"))
        self.assertEqual(fewer["103"]["symbol"], "QNEW", "101 is never given again")
        self.assertNotIn(101, U.columns(fewer))

    def test_a_date_upstream_corrected_keeps_the_aid(self):
        first = U.assign(self.SPELLS, None, [])
        moved = [("QAAA", D(2012, 5, 2), D(2018, 3, 1)) if s[0] == "QAAA" else s for s in self.SPELLS]
        self.assertEqual(U.assign(moved, first, [])["101"]["spells"][0][:2], ["QAAA", "2012-05-02"])

    def test_a_rename_is_one_asset_d2r(self):
        spells = [("QOLD", D(2012, 5, 1), D(2019, 6, 3)), ("QNEW", D(2019, 6, 3), None), ("QAAC", D(2010, 1, 4), None)]
        exits = {("QOLD", D(2019, 6, 3)): "unknown"}
        apart = U.assign(spells, None, [], exits=exits)
        self.assertEqual(sorted(row["symbol"] for row in apart.values() if not row["ref"]), ["QAAC", "QNEW", "QOLD"])
        joined = U.assign(spells, None, [("QOLD", "QNEW")], exits=exits)
        row = joined["101"]
        self.assertEqual(row["spells"], [["QOLD", "2012-05-01", "2019-06-03", "other"], ["QNEW", "2019-06-03", None, None]])
        self.assertEqual((row["symbol"], row["renames"]), ("QNEW", [["QOLD", "QNEW", "2019-06-03"]]))
        self.assertEqual(len([r for r in joined.values() if not r["ref"]]), 2)
        self.assertEqual(U._exit_counts(joined), {"deal": 0, "other": 0, "unknown": 0},
                         "a spell a rename continues did not leave the index")

    def test_a_join_never_renumbers_a_spell_that_has_its_aid(self):
        spells = [("QOLD", D(2012, 5, 1), D(2019, 6, 3)), ("QNEW", D(2019, 6, 3), None)]
        apart = U.assign(spells, None, [])
        self.assertEqual(U.assign(spells, apart, [("QOLD", "QNEW")]), apart)

    def test_the_same_ticker_out_and_back_within_five_days_is_one_asset_and_later_is_two(self):
        near = U.assign([("QAAA", D(2012, 5, 1), D(2019, 6, 3)), ("QAAA", D(2019, 6, 6), None)], None, [])
        self.assertEqual(len(near["100"]["spells"]), 2)
        far = U.assign([("QAAA", D(2012, 5, 1), D(2017, 6, 1)), ("QAAA", D(2021, 6, 1), None)], None, [])
        self.assertEqual((len(far["100"]["spells"]), len(far["101"]["spells"])), (1, 1))

    def test_how_a_spell_ended_the_venues_row_and_the_masks(self):
        venue = {"QAAB": dict(VENUE_OK), "QAAC": dict(VENUE_OK, fractionable=False), "SPY": dict(VENUE_OK)}
        table = U.assign(self.SPELLS, None, [], exits={("QAAA", D(2018, 3, 1)): "deal"}, venue=venue)
        self.assertEqual(table["101"]["spells"][0][3], "deal")
        self.assertEqual((table["100"]["masked"], table["102"]["masked"], table["101"]["alpaca"]),
                         ("not_fractionable", None, None))
        table["102"]["masked"] = "no_bars"   # the panel job's mark
        table["101"]["masked"] = "nonsense"
        again = U.assign(self.SPELLS, table, [], venue={"QAAC": dict(VENUE_OK)})
        self.assertEqual((again["102"]["masked"], again["101"]["masked"], again["100"]["masked"]), ("no_bars", None, None))
        self.assertEqual(again["102"]["alpaca"], venue["QAAB"], "a ticker not asked again keeps its row")


class RenameTest(unittest.TestCase):
    """D2r: the same raw closes on at least 20 common sessions, read with `asof` inside each spell."""

    A, B = ("QOLD", D(2012, 5, 1), D(2022, 2, 1)), ("QNEW", D(2022, 2, 1), None)

    def fetch(self, left: dict, right: dict):
        calls = []

        def fake(gateway, symbols, start, end, *, adjustment, asof, sleep=None):
            calls.append({"symbols": list(symbols), "start": start, "end": end, "asof": asof, "adjustment": adjustment})
            series = left if symbols[0] == "QOLD" else right
            return {symbols[0]: [{"t": day, "c": close} for day, close in sorted(series.items()) if start <= day <= end]}
        return fake, calls

    def series(self, shift: float = 0.0) -> dict:
        days = [d for d, _ in U.store_sessions(LAST) if d >= D(2021, 11, 1)]
        return {d.isoformat(): round(50.0 + 0.25 * k + shift, 2) for k, d in enumerate(days)}

    def test_the_same_company_is_joined(self):
        fetch, calls = self.fetch(self.series(), self.series())
        self.assertIs(U.rename_test(None, self.A, self.B, last=LAST, fetch=fetch), True)
        self.assertEqual([c["symbols"] for c in calls], [["QOLD"], ["QNEW"]])
        self.assertEqual(calls[0]["asof"], "2022-01-31", "inside spell a: its last member session")
        self.assertEqual(calls[1]["asof"], "2022-03-03", "inside spell b: its first session thirty days in")
        self.assertTrue(all(c["adjustment"] == "raw" for c in calls))

    def test_two_companies_are_not(self):
        other = self.series()
        other[sorted(other)[40]] += 0.01
        fetch, _ = self.fetch(self.series(), other)
        self.assertIs(U.rename_test(None, self.A, self.B, last=LAST, fetch=fetch), False, "one close differs")
        short = dict(sorted(self.series().items())[:19])
        fetch, _ = self.fetch(self.series(), short)
        self.assertIs(U.rename_test(None, self.A, self.B, last=LAST, fetch=fetch), False, "19 common sessions")
        fetch, _ = self.fetch(self.series(), {})
        self.assertIs(U.rename_test(None, self.A, self.B, last=LAST, fetch=fetch), False, "no bars on one side")

    def test_a_join_in_2020_is_never_asked(self):
        fetch, calls = self.fetch(self.series(), self.series())
        for a, b in ((("QOLD", D(2012, 5, 1), D(2020, 6, 1)), ("QNEW", D(2020, 6, 1), None)),
                     (("QOLD", D(2012, 5, 1), D(2020, 1, 2)), ("QNEW", D(2020, 1, 3), None)),
                     (("QOLD", D(2012, 5, 1), D(2020, 12, 30)), ("QNEW", D(2020, 12, 30), None))):
            self.assertIsNone(U.rename_test(None, a, b, last=LAST, fetch=fetch), (a, b))
        self.assertEqual(calls, [], "2020 is never fetched: nothing is asked")

    def test_the_real_fetch_never_names_2020(self):
        """A join in the first days of 2021: the window is cut at the span's first session."""
        seen = []

        def bars(path, params):
            seen.append(params)
            return {"bars": {}}
        gateway = FakeGateway()
        gateway.bars = bars
        a, b = ("QOLD", D(2012, 5, 1), D(2021, 2, 1)), ("QNEW", D(2021, 2, 1), None)
        self.assertIs(U.rename_test(gateway, a, b, last=LAST, sleep=lambda s: None), False)
        self.assertEqual(len(seen), 2)
        for params in seen:
            self.assertEqual(params["start"], "2021-01-04")
            for key in ("start", "end", "asof"):
                self.assertNotEqual(str(params.get(key))[:4], "2020", params)

    def test_the_candidates(self):
        spells = [self.A, self.B, ("QAAC", D(2010, 1, 4), None), ("QAAD", D(2022, 2, 4), None),
                  ("QAAE", D(2022, 2, 8), None), ("QOLD", D(2001, 1, 2), D(2010, 1, 4))]
        self.assertEqual(U.rename_candidates(spells), [(self.A, ("QAAD", D(2022, 2, 4), None)), (self.A, self.B)])
        self.assertEqual(U.pair_key(self.A, self.B), "QOLD|2022-02-01|QNEW|2022-02-01")


class Membership(unittest.TestCase):
    """D3: member[d, i] = some spell of i has start <= d and (end is null or d < end)."""

    def test_the_end_day_is_no_member_day_and_ref_never_is(self):
        table = U.assign([("QAAA", D(2018, 3, 5), D(2018, 3, 8)), ("QAAB", D(2018, 3, 7), None)], None, [])
        days = [D(2018, 3, 2), D(2018, 3, 5), D(2018, 3, 6), D(2018, 3, 7), D(2018, 3, 8), D(2018, 3, 9)]
        member = U.membership(table, days)
        self.assertEqual(member.shape, (6, 14))
        self.assertFalse(member[:, :12].any())
        self.assertEqual(member[:, 12].tolist(), [False, True, True, True, False, False])
        self.assertEqual(member[:, 13].tolist(), [False, False, False, True, True, True])

    def test_a_joined_asset_is_a_member_through_its_rename(self):
        table = U.assign([("QOLD", D(2018, 3, 5), D(2018, 3, 8)), ("QNEW", D(2018, 3, 8), None)], None, [("QOLD", "QNEW")])
        member = U.membership(table, [D(2018, 3, 6), D(2018, 3, 7), D(2018, 3, 8), D(2018, 3, 9)])
        self.assertEqual(member[:, 12].tolist(), [True, True, True, True])


class Tradable(unittest.TestCase):
    """Section 11: every symbol that was a member on ANY session of the 36 months through the day and is tradable,
    fractionable and unmasked today; sorted; no date beside any of them."""

    def test_the_36_month_union(self):
        day = D(2022, 3, 31)
        spells = [("QNOW", D(2010, 1, 4), None), ("QOUT", D(2010, 1, 4), D(2019, 4, 1)),
                  ("QOLD", D(2010, 1, 4), D(2019, 3, 29)), ("QMSK", D(2010, 1, 4), None),
                  ("QFRC", D(2010, 1, 4), None), ("QDED", D(2010, 1, 4), D(2021, 6, 1)), ("QSOON", D(2022, 4, 4), None)]
        venue = {s[0]: dict(VENUE_OK) for s in spells}
        venue["QFRC"] = dict(VENUE_OK, fractionable=False)
        venue["QDED"] = dict(VENUE_OK, status="inactive", tradable=False)
        table = U.assign(spells, None, [], venue=venue)
        next(row for row in table.values() if row["symbol"] == "QMSK")["masked"] = "no_bars"
        listed = U.tradable(table, day)
        self.assertEqual(listed, ["QNOW", "QOUT"])
        self.assertEqual(U._months_before(D(2024, 2, 29), 36), D(2021, 2, 28))
        self.assertEqual(U._months_before(day, 36), D(2019, 3, 31))
        self.assertTrue(all(isinstance(s, str) for s in listed))


class Audit(unittest.TestCase):
    DAYS = [d for d, _ in U.store_sessions(LAST)]

    def audit(self, spells=None, **over):
        spells = fake_index() if spells is None else spells
        venue = {t: dict(VENUE_OK) for t, _, e in spells if e is None}
        args = {"previous": None, "source": {"sha256": "a", "recorded": None, "spells": spells}, "venue": venue,
                "days": self.DAYS, "rows": []}
        args.update(over)
        return U.audit(spells, **args)

    def test_a_good_universe_passes_every_check(self):
        result = self.audit()
        self.assertTrue(result["passed"])
        self.assertEqual(tuple(result["checks"]), U.CHECKS)
        self.assertEqual((result["checks"]["count"]["min"], result["checks"]["count"]["max"]), (500, 500))

    def test_source_the_pinned_files_sha_is_the_one_first_recorded(self):
        self.assertTrue(self.audit(source={"sha256": "a", "recorded": "a"})["passed"])
        result = self.audit(source={"sha256": "a", "recorded": "b"})
        self.assertEqual((result["passed"], result["checks"]["source"]["passed"]), (False, False))

    def test_append_only_holds_a_new_pin_to_the_old(self):
        old = fake_index()
        new = fake_index(changes=[(D(2019, 5, 1), name(600), name(3))])
        source = {"sha256": "a", "recorded": None, "spells": new, "known_through": D(2019, 4, 30)}
        self.assertTrue(self.audit(new, previous=old, source=source)["passed"])
        result = self.audit(new, previous=old, source={**source, "known_through": D(2019, 5, 1)})
        self.assertEqual((result["passed"], result["checks"]["append_only"]["count"]), (False, 2))

    def test_count_480_to_520_members_on_every_store_session(self):
        self.assertFalse(self.audit(fake_index(479))["passed"])
        self.assertTrue(self.audit(fake_index(480))["passed"])
        self.assertTrue(self.audit(fake_index(520))["passed"])
        result = self.audit(fake_index(521))
        self.assertEqual((result["checks"]["count"]["passed"], result["checks"]["count"]["count"]), (False, len(self.DAYS)))
        one_day = fake_index(480, changes=[(D(2018, 3, 5), None, name(0)), (D(2018, 3, 6), name(700), None)])
        self.assertEqual(self.audit(one_day)["checks"]["count"]["count"], 1, "479 on one session")

    def test_overlap_no_ticker_in_two_overlapping_spells(self):
        spells = [*fake_index(), (name(1), D(2015, 1, 5), D(2016, 6, 1))]
        result = self.audit(spells)
        self.assertEqual((result["checks"]["overlap"]["passed"], result["checks"]["overlap"]["count"]), (False, 1))

    def test_assets_at_most_ten_current_members_without_a_tradable_asset_each_listed(self):
        spells = fake_index()
        venue = {t: dict(VENUE_OK) for t, _, _ in spells}
        for k in range(10):
            venue[name(k)] = None if k % 2 else dict(VENUE_OK, status="inactive")
        result = self.audit(spells, venue=venue)
        self.assertTrue(result["checks"]["assets"]["passed"])
        self.assertEqual(result["checks"]["assets"]["problems"], [name(k) for k in range(10)])
        venue[name(10)] = dict(VENUE_OK, tradable=False)
        result = self.audit(spells, venue=venue)
        self.assertEqual((result["passed"], result["checks"]["assets"]["count"]), (False, 11))

    def test_wiki_agreement_is_reported_and_never_fails(self):
        spells = fake_index(changes=[(D(2021, 9, 20), name(600), name(3))])
        rows = [{"date": D(2021, 9, 20), "added": name(600), "removed": name(3), "reason": "x"},
                {"date": D(2021, 9, 1), "added": name(601), "removed": name(4), "reason": "the file lacks this one"},
                {"date": D(2019, 1, 2), "added": name(602), "removed": name(5), "reason": "older than a year"}]
        check = self.audit(spells, rows=rows)["checks"]["wiki_agreement"]
        self.assertEqual((check["passed"], check["rows"], check["agreed"], check["share"]), (True, 2, 1, 0.5))
        self.assertTrue(self.audit(spells, rows=rows)["passed"])


def fake_ctx(root: Path, gateway, now: float = NOW, settings=None) -> Context:
    clock = {"now": now}
    ctx = Context("equity_universe", root=root, due_at=now, clock=lambda: clock["now"], gateway=gateway,
                  config={}, settings_value=settings or {})
    ctx.clock_box = clock  # type: ignore[attr-defined]
    return ctx


class TheJob(unittest.TestCase):
    """`run`: the files, the seal on the salt and on the receipt, the audit's refusal, the changes table's
    confirmation, the pin's advance."""

    FILED = fake_index(500, changes=[(D(2018, 6, 5), name(600), name(1)), (D(2019, 9, 23), name(601), name(2)),
                                     (D(2021, 9, 20), name(602), name(3))])
    TABLE = [(D(2022, 3, 21), name(610), name(4), "Market capitalization change."),
             (D(2021, 9, 20), name(602), name(3), "Fake Holdings acquired the company."),
             (D(2019, 9, 23), name(601), name(2), "Market capitalization change."),
             (D(2018, 6, 5), name(600), name(1), "Taken private by Fake Partners.")]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.root.mkdir()
        self.gateway = FakeGateway()
        self.gateway.page(U.RAW.format(commit=U.PIN), fake_file(self.FILED))
        self.gateway.page(U.COMMITS, json.dumps([{"sha": U.PIN}]))
        urls = wiki_urls()
        self.gateway.page(urls["sections"], sections_answer(["See also"]))
        self.gateway.page(urls["lead"], parse_answer(fake_table(self.TABLE)))
        for ticker, _, end in self.FILED:
            if end is None or end > D(2019, 1, 1):
                self.gateway.venue[ticker] = dict(VENUE_OK)
        self.gateway.venue[name(610)] = dict(VENUE_OK)
        self.gateway.bars = fake_bars
        quiet = mock.patch.object(xs_config, "quiet", return_value=None)
        quiet.start()
        self.addCleanup(quiet.stop)
        self.base = self.root / U.STORE_DIR / xs_store.UNIVERSE_DIR

    def run_job(self, now: float = NOW, **kw):
        ctx = fake_ctx(self.root, self.gateway, now, **kw)
        return U.run(ctx, sleep=lambda s: None), ctx

    def read(self, name_: str):
        return json.loads((self.base / name_).read_text(encoding="utf-8"))

    def test_the_first_run_writes_the_universe_owner_only_the_manifest_last(self):
        receipt, ctx = self.run_job()
        self.assertTrue(receipt.get("ok"), receipt)
        self.assertEqual(sorted(p.name for p in self.base.iterdir()),
                         sorted([xs_store.SALT_FILE, U.SOURCE_FILE, U.SPELLS_FILE, U.ASSETS_FILE, U.TRADABLE_FILE,
                                 U.MANIFEST_FILE, U.VENUE_FILE]))
        for path in self.base.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)
        self.assertEqual(stat.S_IMODE(self.base.stat().st_mode), 0o700)
        manifest = self.read(U.MANIFEST_FILE)
        self.assertEqual(manifest["version"], xs_store.UNIVERSE_VERSION)
        for name_ in U.HASHED:
            self.assertEqual(manifest["sha256"][name_], hashlib.sha256((self.base / name_).read_bytes()).hexdigest())
        self.assertGreaterEqual((self.base / U.MANIFEST_FILE).stat().st_mtime_ns,
                                max((self.base / n).stat().st_mtime_ns for n in U.HASHED), "the manifest is last")
        self.assertTrue(manifest["audit"]["passed"])
        self.assertEqual(manifest["exits"], {"deal": 2, "other": 1, "unknown": 0})
        self.assertEqual(manifest["wiki_reach"], "2018-06-05")
        source = self.read(U.SOURCE_FILE)
        self.assertEqual((source["repo"], source["commit"], source["path"], source["rows"], source["known_through"]),
                         (U.REPO, U.PIN, U.FILE, 503, "2021-09-20"))
        self.assertEqual(source["sha256"], hashlib.sha256(fake_file(self.FILED).encode()).hexdigest())
        self.assertEqual((source["wiki"]["verdict"], source["wiki"]["revid"], source["wiki"]["changes_applied"]),
                         ("ok", 777, 0))
        table = self.read(U.ASSETS_FILE)
        self.assertEqual(len(table), 12 + 503)
        self.assertEqual(self.read(U.TRADABLE_FILE)["as_of"], LAST.isoformat())
        self.assertEqual(len(self.read(U.TRADABLE_FILE)["stock"]), 502, "the members, and the two out since March 2019")
        lines = (self.base / U.SPELLS_FILE).read_text().splitlines()
        self.assertEqual((lines[0], len(lines)), ("ticker,start,end,source", 504))
        self.assertTrue(all(line.endswith(",fja") for line in lines[1:]))
        self.assertEqual(ctx.alerts, [])
        self.assertEqual(U.read_universe(self.root / U.STORE_DIR)["assets"], table)

    def test_the_receipt_holds_counts_and_verdicts_never_a_ticker_a_change_date_or_the_salt(self):
        receipt, _ = self.run_job()
        text = json.dumps(receipt)
        for ticker, start, end in self.FILED:
            self.assertNotIn(f'"{ticker}"', text)
        for day, *_ in self.TABLE:
            self.assertNotIn(day.isoformat(), text)
        self.assertEqual((receipt["spells"], receipt["assets"], receipt["members"], receipt["new_assets"]),
                         (503, 503, 500, 515))
        self.assertEqual(receipt["audit"], {n: {"passed": True, "count": 0} for n in U.CHECKS})
        self.assertEqual(receipt["wiki"], {"verdict": "ok", "rows": 4, "applied": 0, "pending": 1, "complete": True,
                                           "malformed": 0})
        self.assertEqual((receipt["commit"], receipt["stale_days"], receipt["tradable"]), (U.PIN[:12], 0, 502))
        salt = (self.base / xs_store.SALT_FILE).read_bytes()
        self.assertEqual(len(salt), xs_store.SALT_BYTES)
        self.assertEqual(receipt["salt"], hashlib.sha256(salt).hexdigest()[:8], "only its sha256's first 8 hex")
        for path in self.base.iterdir():
            if path.name != xs_store.SALT_FILE:
                data = path.read_bytes()
                self.assertNotIn(salt, data)
                self.assertNotIn(salt.hex().encode(), data)
        self.assertNotIn(salt.hex(), text)
        for call in self.gateway.calls:
            self.assertNotIn(salt.hex(), json.dumps(call[2]))

    def test_the_salt_is_written_once_and_never_rewritten(self):
        self.run_job()
        salt = (self.base / xs_store.SALT_FILE).read_bytes()
        self.run_job(NOW + 86400)
        self.assertEqual((self.base / xs_store.SALT_FILE).read_bytes(), salt)
        (self.base / xs_store.SALT_FILE).write_bytes(b"short")
        receipt, _ = self.run_job(NOW + 2 * 86400)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual((self.base / xs_store.SALT_FILE).read_bytes(), b"short", "never repaired, never written over")

    def test_a_change_after_the_file_applies_once_two_runs_twenty_hours_apart_have_read_it(self):
        first, _ = self.run_job()
        before = self.read(U.ASSETS_FILE)
        early, _ = self.run_job(NOW + 19 * 3600)
        self.assertEqual((early["wiki"]["applied"], early["wiki"]["pending"], early["members"]), (0, 1, 500))
        later, _ = self.run_job(NOW + 24 * 3600)
        self.assertEqual((later["wiki"]["applied"], later["wiki"]["pending"], later["new_assets"]), (1, 0, 1))
        table = self.read(U.ASSETS_FILE)
        for aid, row in before.items():
            self.assertEqual(table[aid]["symbol"], row["symbol"], "no aid moved")
        self.assertEqual(table[str(max(map(int, before)) + 1)]["spells"], [[name(610), "2022-03-21", None, None]])
        out = next(row for row in table.values() if row["symbol"] == name(4))
        self.assertEqual(out["spells"][0][2:], ["2022-03-21", "other"])
        lines = (self.base / U.SPELLS_FILE).read_text().splitlines()
        self.assertEqual(sum(1 for line in lines if line.endswith(",wiki")), 2, "the spell ended and the one begun")
        self.assertEqual(self.read(U.MANIFEST_FILE)["known_through"], "2022-04-02")

    def test_an_unverified_read_applies_nothing_new_and_keeps_what_was_applied(self):
        self.run_job()
        self.run_job(NOW + 24 * 3600)
        applied = self.read(U.ASSETS_FILE)
        answer = parse_answer(fake_table(self.TABLE))
        self.gateway.page(wiki_urls()["lead"], answer[:answer.index(name(602))], truncated=True)
        receipt, ctx = self.run_job(NOW + 48 * 3600)
        self.assertTrue(receipt["ok"])
        self.assertEqual((receipt["wiki"]["verdict"], receipt["wiki"]["applied"], receipt["wiki"]["complete"]),
                         ("unverified", 1, False), "the cut falls above the file's last date")
        self.assertEqual(self.read(U.ASSETS_FILE), applied, "the row applied by a verified read stands")
        self.assertEqual(self.read(U.MANIFEST_FILE)["known_through"], "2022-04-02", "known through the verified read")
        self.assertEqual(receipt["stale_days"], 1)
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])
        del self.gateway.pages[wiki_urls()["lead"]]
        receipt, ctx = self.run_job(NOW + 72 * 3600)
        self.assertEqual((receipt["ok"], receipt["wiki"]["verdict"]), (True, "unverified"), "an unreadable table too")
        self.assertEqual(self.read(U.ASSETS_FILE), applied)

    def test_a_stale_membership_is_an_alarm(self):
        answer = parse_answer(fake_table(self.TABLE))
        self.gateway.page(wiki_urls()["lead"], answer[:answer.index(name(602))], truncated=True)
        receipt, ctx = self.run_job()
        self.assertEqual(receipt["stale_days"], (D(2022, 4, 1) - D(2021, 9, 20)).days)
        self.assertEqual(len([a for a in ctx.alerts if "days stale" in a["text"]]), 1)
        receipt, ctx = self.run_job(settings={"equity_universe": {"max_stale_days": 400}})
        self.assertEqual([a for a in ctx.alerts if "days stale" in a["text"]], [])

    def test_a_failed_audit_writes_nothing_and_the_last_good_universe_stays(self):
        self.run_job()
        kept = {p.name: p.read_bytes() for p in self.base.iterdir()}
        self.gateway.page(U.RAW.format(commit=U.PIN), fake_file(fake_index(470)))
        receipt, ctx = self.run_job(NOW + 86400)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual({n: c["passed"] for n, c in receipt["audit"].items() if not c["passed"]},
                         {"source": False, "count": False}, "another file under the same pin, and too few members")
        for name_ in (*U.HASHED, U.MANIFEST_FILE, xs_store.SALT_FILE):
            self.assertEqual((self.base / name_).read_bytes(), kept[name_], name_)
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])
        self.assertNotIn(name(0), json.dumps(receipt) + json.dumps(ctx.alerts))

    def test_a_reader_that_does_not_answer_is_a_failed_receipt(self):
        self.gateway.pages[U.RAW.format(commit=U.PIN)] = GatewayError("POST: HTTP 504", status=504)
        receipt, _ = self.run_job()
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse((self.base / U.MANIFEST_FILE).exists())

    def test_the_first_statement_is_the_quiet_window(self):
        with mock.patch.object(xs_config, "quiet", return_value="a wall") as quiet:
            receipt, _ = self.run_job()
        self.assertEqual(receipt, {"status": "skipped", "why": "a wall"})
        quiet.assert_called_once_with(NOW, float(U.WALL_S))
        self.assertEqual(self.gateway.calls, [], "nothing is asked, nothing is written")
        self.assertFalse(self.base.exists())

    def test_without_c0_the_job_is_skipped_never_a_crash(self):
        with mock.patch.object(xs_config, "quiet", side_effect=NotImplementedError("a stub")):
            receipt, _ = self.run_job()
        self.assertEqual(receipt["status"], "skipped")
        self.assertEqual(self.gateway.calls, [])

    def test_the_pin_advances_only_onto_the_old_file_grown(self):
        self.run_job()
        newer = "f" * 40
        grown = fake_index(500, changes=[(D(2018, 6, 5), name(600), name(1)), (D(2019, 9, 23), name(601), name(2)),
                                         (D(2021, 9, 20), name(602), name(3)), (D(2022, 3, 21), name(610), name(4))])
        self.gateway.page(U.COMMITS, json.dumps([{"sha": newer}]))
        self.gateway.page(U.RAW.format(commit=newer), fake_file(grown))
        early, _ = self.run_job(NOW + 86400)
        self.assertEqual((early["pin"]["advanced"], self.read(U.SOURCE_FILE)["commit"]), (False, U.PIN),
                         "the pin is looked at weekly")
        receipt, ctx = self.run_job(NOW + 7 * 86400)
        self.assertEqual((receipt["pin"], receipt["commit"]), ({"advanced": True, "refused": False}, newer[:12]))
        source = self.read(U.SOURCE_FILE)
        self.assertEqual((source["commit"], source["known_through"], source["rows"]), (newer, "2022-03-21", 504))
        self.assertEqual(sum(1 for line in (self.base / U.SPELLS_FILE).read_text().splitlines() if line.endswith(",wiki")), 0)

    def test_a_newer_file_that_rewrites_the_past_is_refused_and_the_old_pin_stays(self):
        self.run_job()
        before = self.read(U.ASSETS_FILE)
        newer = "e" * 40
        rewritten = [(t, s, D(2017, 3, 1) if t == name(7) else e) for t, s, e in self.FILED] + [(name(650), D(2017, 3, 1), None)]
        self.gateway.page(U.COMMITS, json.dumps([{"sha": newer}]))
        self.gateway.page(U.RAW.format(commit=newer), fake_file(rewritten))
        receipt, ctx = self.run_job(NOW + 7 * 86400)
        self.assertTrue(receipt["ok"])
        self.assertEqual((receipt["pin"], receipt["commit"]), ({"advanced": False, "refused": True}, U.PIN[:12]))
        self.assertEqual(self.read(U.SOURCE_FILE)["commit"], U.PIN)
        table = self.read(U.ASSETS_FILE)
        self.assertEqual(next(r["spells"] for r in table.values() if r["symbol"] == name(7)),
                         next(r["spells"] for r in before.values() if r["symbol"] == name(7)), "the past is not rewritten")
        self.assertNotIn(name(650), {r["symbol"] for r in table.values()})
        self.assertEqual({a: r["symbol"] for a, r in table.items() if a in before},
                         {a: r["symbol"] for a, r in before.items()})
        self.assertEqual(len(self.gateway.gets("/v1/alpaca/v2/stocks/bars")), 0,
                         "refused before a bar or an asset row is asked for it")
        self.assertEqual(len([a for a in ctx.alerts if "newer commit is not adopted" in a["text"]]), 1)
        self.assertEqual(self.gateway.posts().count(U.COMMITS), 2, "asked at the first run and a week later")

    def test_the_venue_is_asked_once_a_week_and_a_run_out_of_its_wall_resumes(self):
        clock = {"t": NOW}
        ctx = Context("equity_universe", root=self.root, due_at=NOW, clock=lambda: clock["t"], gateway=self.gateway,
                      config={}, settings_value={})
        real_get = self.gateway.get

        def slow_get(path, params=None):
            clock["t"] += 2.0  # every venue call takes two seconds of the wall
            return real_get(path, params)
        self.gateway.get = slow_get
        receipt = U.run(ctx, sleep=lambda s: None)
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("OutOfWall", receipt["error"])
        self.assertFalse((self.base / U.MANIFEST_FILE).exists())
        asked = len(self.gateway.gets(U.ASSETS))
        self.assertEqual(asked, int(U.WALL_SHARE * U.WALL_S / 2.0) + 1)
        done = json.loads((self.base / U.VENUE_FILE).read_text())
        self.assertEqual(len(done["done"]), asked, "what it read is kept")
        clock["t"] = NOW + 3600
        receipt = U.run(ctx, sleep=lambda s: None)
        self.assertTrue(receipt["ok"], receipt)
        self.assertEqual(receipt["venue"]["venue_asked"], 502 - asked, "the next run goes on from there")
        self.gateway.get = real_get
        again, _ = self.run_job(NOW + 2 * 86400)
        self.assertEqual(again["venue"]["venue_asked"], 1, "only the ticker the changes table has brought in since")
        same, _ = self.run_job(NOW + 3 * 86400)
        self.assertEqual(same["venue"]["venue_asked"], 0)
        week, _ = self.run_job(NOW + 8 * 86400)
        self.assertEqual(week["venue"]["venue_asked"], 503, "every row again after a week (one more ticker is in by now)")

    def test_remask_is_the_panel_jobs_one_write(self):
        self.run_job()
        root = self.root / U.STORE_DIR
        table = self.read(U.ASSETS_FILE)
        aid = next(int(a) for a, row in table.items() if row["symbol"] == name(20))
        venue_masked = next(int(a) for a, row in table.items() if row["symbol"] == name(21))
        table[str(venue_masked)]["masked"] = U.VENUE_MASK
        U._publish(root, files={U.ASSETS_FILE: U._json_bytes(table)}, manifest=self.read(U.MANIFEST_FILE))
        counts = U.remask(root, {aid: "no_bars", venue_masked: "reused", 99999: "insane", 1: "no_bars"}, day=LAST)
        self.assertEqual(counts, {"no_bars": 1, U.VENUE_MASK: 1})
        after = U.read_universe(root)
        self.assertEqual((after["assets"][str(aid)]["masked"], after["assets"][str(venue_masked)]["masked"],
                          after["assets"]["1"]["masked"]), ("no_bars", U.VENUE_MASK, None))
        self.assertNotIn(name(20), self.read(U.TRADABLE_FILE)["stock"])
        self.assertEqual(after["manifest"]["masked"], {"no_bars": 1, U.VENUE_MASK: 1})
        self.assertEqual(U.remask(root, {aid: None}, day=LAST), {U.VENUE_MASK: 1})
        self.assertIn(name(20), self.read(U.TRADABLE_FILE)["stock"])
        with self.assertRaises(ValueError):
            U.remask(root, {aid: U.VENUE_MASK}, day=LAST)
        receipt, _ = self.run_job(NOW + 3600)
        self.assertEqual(receipt["masked"], {}, "the venue's mark is the venue's: read again each run")

    def test_a_universe_that_does_not_match_its_manifest_is_never_read_or_written_over(self):
        self.run_job()
        (self.base / U.ASSETS_FILE).write_text("{}")
        with self.assertRaises(ValueError):
            U.read_universe(self.root / U.STORE_DIR)
        receipt, _ = self.run_job(NOW + 3600)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual((self.base / U.ASSETS_FILE).read_text(), "{}")


class TheStoresSessions(unittest.TestCase):
    def test_no_2020_session_and_the_spans(self):
        days = [d for d, _ in U.store_sessions(D(2021, 1, 8))]
        self.assertEqual((days[0], days[-1]), (D(2016, 1, 4), D(2021, 1, 8)))
        self.assertFalse(any(d.year in xs_config.RESERVE_YEARS for d in days))
        self.assertEqual(days[days.index(D(2019, 12, 31)) + 1], D(2021, 1, 4))
        self.assertEqual([d for d, _ in U.store_sessions(D(2020, 6, 1))][-1], D(2019, 12, 31))
        self.assertEqual(U.spans(), ((D(2016, 1, 4), D(2019, 12, 31)), (D(2021, 1, 4), None)))


class TheContract(unittest.TestCase):
    def test_the_pin_is_a_commit_sha_and_the_wall_is_the_registrys(self):
        self.assertRegex(U.PIN, r"^[0-9a-f]{40}$")
        self.assertEqual(U.RAW.format(commit=U.PIN).count(U.PIN), 1)
        self.assertEqual(U.WALL_S, 900)
        self.assertEqual((U.MEMBERS_MIN, U.MEMBERS_MAX, U.ASSETS_MISSING_MAX, U.RENAME_DAYS, U.RENAME_SESSIONS,
                          U.CONFIRM_HOURS, U.UNION_MONTHS), (480, 520, 10, 5, 20, 20, 36))
        self.assertEqual(U.FIRST_AID, 100)
        self.assertEqual(os.path.basename(U.RAW), U.FILE)


if __name__ == "__main__":
    unittest.main()
