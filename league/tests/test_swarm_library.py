"""THE RESEARCH LIBRARY, the House's side (Sept 29, 2026; league/swarm/library.py): the client over the gateway's
`/v1/research/*`, the date rule checked again on every answer, the three lines and the event, the `literature` tool's
adapter, the architect's retrieval and its seed rotation, and that nothing in league/swarm/ reads the open web.

The gateway's answers here are SYNTHETIC, shaped as gateway/lib/library.mjs answers them (gateway/test/library.test.mjs
tests the gateway itself). No network."""

from __future__ import annotations

import copy
import io
import json
import re
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path

from league.swarm import claude_research as CR
from league.swarm import library as L
from league.swarm import settings as S
from league.swarm.hook import PUBLIC_KINDS, SKIPPED_KINDS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from league.tests.test_frontier import GATEWAY, SECRET, FakeOpener, FakeResponse

REPO = Path(__file__).resolve().parents[2]
CASES = json.loads((REPO / "gateway" / "test" / "library-date-cases.json").read_text())


def item(base="1602.00865", v=1, first="2016-02-02", day=None, *, title="Tail Risk Premia for Long-Term Equity Investors",
         abstract="We measure the variance risk premium in index options and the returns of selling tail insurance.",
         authors=("Ada Quill", "Ben Harrow")):
    """An item as the gateway answers one (ITEM in gateway/lib/library.mjs)."""
    return {"id": f"arXiv:{base}v{v}", "title": title, "authors": list(authors), "first_posted": first, "version": v,
            "version_date": day or first, "primary_category": "q-fin.PM", "categories": ["q-fin.PM", "q-fin.RM"],
            "abstract": abstract, "url": f"https://arxiv.org/abs/{base}v{v}"}


ITEMS = [item(), item("2207.00949", 1, "2022-07-03", title="Stochastic arbitrage with market index options",
                      abstract="Stochastic arbitrage opportunities in market index options and the variance risk premium."),
         item("2412.09999", 1, "2024-12-31", title="Year-end order flow in index options",
              abstract="Order flow around the turn of the year; forecasts to [date] are given.")]


def search_answer(items=None, **more):
    return {"query": ["variance", "risk", "premium"], "category": "all", "last_day": "2024-12-31",
            "items": copy.deepcopy(ITEMS if items is None else items),
            "withheld": {"after_cutoff": 4, "revised_earlier": 1, "revised_unmatched": 1, "off_topic": 0, "no_date": 0, "unresolved": 0,
                         "too_many_versions": 0},
            "cached": False, **more}


def read_answer(base="2409.06496", v=1, *, text="1 Introduction\nThe premium is large.\n2 Results\nSelling puts earns it.",
                source="arxiv_html", start=0, **more):
    body = {**item(base, v, "2024-09-10", title="Valuation of convertible bonds by simulation",
                   abstract="A least-squares Monte Carlo valuation of convertible bonds."),
            "asked": f"arXiv:{base}", "served_earlier_version": False, "text_source": source,
            "sections": [{"title": "1 Introduction", "start": 0}, {"title": "2 Results", "start": text.find("2 Results")}],
            "start": start, "text": text, "next_start": None, "total_chars": start + len(text), "last_day": "2024-12-31",
            "cached": False}
    body.update(more)
    return body


class FakeClient:
    """The gateway's library as the House's policy sees it: scripted answers, each call recorded. `during` runs inside
    every call (a test's probe of what the caller holds); an exception in `raises` is raised by the next call."""

    def __init__(self, *, searches=None, reads=None, raises=None, during=None):
        self.searches = searches if searches is not None else {"*": search_answer()}
        self.reads = reads if reads is not None else {"*": read_answer()}
        self.raises = list(raises or [])
        self.during = during
        self.calls: list[tuple] = []
        self.timeouts: list[float | None] = []

    def _step(self):
        if self.during:
            self.during()
        if self.raises:
            error = self.raises.pop(0)
            if error is not None:
                raise error

    def search(self, query, *, category="all", max_items=5, agent=None, role=None, timeout=None):
        self.calls.append(("search", query, category, max_items, agent, role))
        self.timeouts.append(timeout)
        self._step()
        return copy.deepcopy(self.searches.get(query, self.searches.get("*")))

    def read(self, item_id, *, start=0, chars=8000, agent=None, role=None, timeout=None):
        self.calls.append(("read", item_id, start, chars, agent, role))
        self.timeouts.append(timeout)
        self._step()
        return copy.deepcopy(self.reads.get(item_id, self.reads.get("*")))


def enabled_settings(**research):
    settings = copy.deepcopy(S.DEFAULTS)
    settings["research"].update({"enabled": True, **research})
    return settings


class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = enabled_settings()
        self.client = FakeClient()
        self.library = L.Library(self.store, self.client, self.settings, clock=self.clock)
        self.fam = {"id": "condor-vrp"}

    def call(self, args, out=None, *, left=170.0):
        out = {} if out is None else out
        return self.library.tool(self.fam, args, out, deadline=self.clock() + left), out

    def events(self):
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == L.EVENT]


# ------------------------------------------------------------------------------------------------------------ the client
class Client(unittest.TestCase):
    def client(self, *script):
        opener = FakeOpener(*script)
        return L.LibraryClient(GATEWAY + "/", lambda: SECRET, opener=opener, timeout=60), opener

    def test_a_search_and_a_read_are_gets_with_the_bearer_token_and_their_params(self):
        client, opener = self.client(FakeResponse(search_answer()), FakeResponse(read_answer()))
        self.assertEqual(client.search("variance risk premium", category="q-fin", max_items=4, agent="condor-vrp", role="researcher",
                                       timeout=30)["items"][0]["id"], "arXiv:1602.00865v1")
        request, timeout = opener.calls[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, f"{GATEWAY}/v1/research/search?q=variance+risk+premium&cat=q-fin&max=4&agent=condor-vrp&role=researcher")
        self.assertEqual(opener.headers()["authorization"], f"Bearer {SECRET}")
        self.assertIsNone(request.data)
        self.assertEqual(timeout, L.CLIENT_FLOOR_SECONDS, "never less than the gateway's longest request")
        client.read("arXiv:2409.06496v1", start=8000, chars=4000)
        self.assertEqual(opener.calls[1][0].full_url, f"{GATEWAY}/v1/research/read?id=arXiv%3A2409.06496v1&start=8000&chars=4000")
        self.assertEqual(opener.calls[1][1], 60)

    def test_each_failure_is_a_library_error_and_only_a_5xx_or_a_timeout_counts(self):
        def refused(code, body):
            return urllib.error.HTTPError(GATEWAY, code, "x", {}, io.BytesIO(json.dumps(body).encode()))

        cases = [
            (refused(429, {"error": "spent", "cap": "library_day"}), dict(cap="library_day", busy=False, counted=False)),
            (refused(429, {"error": "busy", "busy": True}), dict(cap=None, busy=True, counted=False)),
            (refused(403, {"error": "later", "refused": "after_cutoff"}), dict(refused="after_cutoff", counted=False)),
            (refused(400, {"error": "q", "refused": "query"}), dict(refused="query", counted=False)),
            (refused(502, {"error": "arXiv failed", "upstream": True}), dict(status=502, counted=True)),
            (refused(503, {"error": "slow down", "backoff": True}), dict(status=503, counted=True)),
            (urllib.error.URLError("timed out"), dict(status=None, counted=True)),
            (TimeoutError("read"), dict(counted=True)),
            (FakeResponse(raw=b"not json"), dict(counted=True)),
            (FakeResponse([1, 2]), dict(counted=True)),
        ]
        for failure, expect in cases:
            client, _ = self.client(failure)
            with self.assertRaises(L.LibraryError) as caught:
                client.search("tail risk")
            for key, value in expect.items():
                self.assertEqual(getattr(caught.exception, key), value, (failure, key))


# ------------------------------------------------------------------------------------------------------------ the checks
class DateRule(unittest.TestCase):
    def test_the_cutoff_is_the_gateways_constant(self):
        self.assertEqual(L.CUTOFF, "2025-01-01T00:00:00Z")
        text = (REPO / "gateway" / "lib" / "library.mjs").read_text()
        self.assertIn("export const CUTOFF = '2025-01-01T00:00:00Z';", text)
        self.assertIn("export const LAST_YYMM = 2412;", text)

    def test_the_date_scan_holds_every_shared_case(self):
        for text in CASES["match"]:
            self.assertTrue(L.has_post_cutoff(text), text)
            self.assertFalse(L.has_post_cutoff(L.scrub(text)), text)
        for text in CASES["clean"]:
            self.assertFalse(L.has_post_cutoff(text), text)
            self.assertEqual(L.scrub(text), text)

    def test_the_patterns_are_the_gateways_branch_for_branch(self):
        """The JavaScript pattern, its `${YEAR}` and `${MONTH}` filled in and its escapes read, is the Python one."""
        js = (REPO / "gateway" / "lib" / "library.mjs").read_text()
        year = re.search(r"const YEAR = '([^']+)';", js).group(1)
        month = "".join(re.findall(r"'([^']*)'", js.split("const MONTH = ", 1)[1].split(";", 1)[0])).replace("\\\\", "\\")
        source = js.split("export const POST_CUTOFF_SOURCE = [", 1)[1].split("].join('|');", 1)[0]
        branches = [b.replace("${YEAR}", year).replace("${MONTH}", month).replace("\\\\", "\\")
                    for b in re.findall(r"^  [`']([^\n]*)[`'],$", source, re.M)]
        self.assertEqual(branches, list(L.POST_CUTOFF_BRANCHES))

    def test_an_item_after_the_cutoff_or_with_a_bad_date_is_dropped(self):
        self.assertEqual(L.check_item(item())["id"], "arXiv:1602.00865v1")
        bad = {
            "a version dated 2025-01-02": item(day="2025-01-02"),
            "first posted 2025": item("2412.00001", first="2025-01-03"),
            "a 2501 id": item("2501.00001", first="2024-12-30"),
            "a 2613 id": item("2613.00001", first="2024-12-30"),
            "no version in the id": {**item(), "id": "arXiv:1602.00865"},
            "the version disagrees": {**item(), "version": 2},
            "the version before the first posting": item(first="2016-02-02", day="2015-01-01"),
            "an unparseable date": item(first="Feb 2016"),
            "no date": {**item(), "first_posted": None},
            "not a mapping": ["arXiv:1602.00865v1"],
        }
        for why, row in bad.items():
            self.assertIsNone(L.check_item(row), why)

    def test_a_kept_item_is_scrubbed_and_holds_only_the_model_facing_fields(self):
        row = item(abstract="Notes maturing on 2026-12-14 pay a premium by December 2025; write to a.b@univ.example.edu.",
                   authors=[f"Author {i}" for i in range(9)])
        kept = L.check_item(row)
        self.assertEqual(set(kept), {"id", "title", "authors", "first_posted", "version_date", "category", "abstract"})
        self.assertEqual(kept["abstract"], "Notes maturing on [date] pay a premium by [date]; write to [email].")
        self.assertEqual(kept["authors"].count(","), 6, "at most seven names")
        self.assertFalse(L.has_post_cutoff(json.dumps(kept, ensure_ascii=False)))

    def test_a_read_is_checked_again_windowed_and_bounded(self):
        out = L.check_read(read_answer(text="The notes mature on 2026-12-14. Contact me@univ.example.edu. " + "x" * 9000),
                           read_chars=8000)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["text"].startswith("The notes mature on [date]. Contact [email]."))
        self.assertEqual(len(out["text"]), 8000)
        self.assertEqual(out["next_start"], 8000)
        for key in ("served_earlier_version", "asked", "cached", "last_day", "url", "categories"):
            self.assertNotIn(key, out)
        late = L.check_read(read_answer(source="ar5iv", text="Momentum. This draft March 2025."))
        self.assertEqual((late["text_source"], late["text"], late["next_start"]), ("none", "", None), "ar5iv's text withheld whole")
        wide = L.check_read(read_answer(text="σ" * 9000), read_chars=8000)
        self.assertLessEqual(len(json.dumps(wide)), L.MAX_OUTPUT_CHARS, "under the loop's 12,000 even when every character escapes")
        self.assertEqual(wide["next_start"], len(wide["text"]))
        self.assertEqual(L.check_read(read_answer(version_date="2025-02-01"))["status"], "refused")
        later = L.check_read(read_answer(start=8000))
        self.assertNotIn("abstract", later, "the abstract comes with the first window only")
        none = L.check_read(read_answer(source="none", text="", text_note="busy"))
        self.assertIn("ask again later", none["note"])

    def test_a_read_that_names_a_version_gets_that_version_or_no_such_paper(self):
        """Review of #428, look-ahead F3: a gateway that served v1 for a named v4 dated 2025 told the agent the paper was
        revised after 2024. The House holds the served id to the one asked, whatever the gateway does."""
        asked = L.check_read(read_answer("2409.06496", 1), asked=("2409.06496", 1))
        self.assertEqual((asked["status"], asked["id"]), ("ok", "arXiv:2409.06496v1"))
        self.assertEqual(L.check_read(read_answer("2409.06496", 1), asked=("2409.06496", None))["status"], "ok", "unversioned: any")
        swapped = L.check_read(read_answer("2409.06496", 1), asked=("2409.06496", 4))
        self.assertEqual(swapped, {"status": "refused", "reason": L.NO_SUCH_PAPER})
        self.assertEqual(swapped["reason"], L._why(L.LibraryError("x", status=404, refused="not_found")),
                         "the same words as a version that does not exist")
        other = L.check_read(read_answer("2409.06496", 1), asked=("1602.00865", None))
        self.assertEqual(other["status"], "refused")
        self.assertEqual(L.check_read(read_answer("cond-mat/0601001", 1), asked=("Cond-Mat/0601001", 1))["status"], "ok")

    def test_the_client_outwaits_the_gateways_longest_request(self):
        js = (REPO / "gateway" / "lib" / "library.mjs").read_text()
        budget = int(re.search(r"export const REQUEST_BUDGET_MS = (\d+);", js).group(1))
        fetch = max(int(x) for x in re.findall(r"\[\w+_HOST\]: (\d+)", re.search(r"export const FETCH_TIMEOUT_MS = \{([^}]*)\}", js).group(1)))
        self.assertIn("export const WORST_MS = REQUEST_BUDGET_MS + 15000;", js)
        self.assertEqual(fetch, 15000)
        self.assertGreaterEqual(L.CLIENT_FLOOR_SECONDS * 1000, budget + fetch + 5000, "a margin past the gateway's WORST_MS")

    def test_the_ids_an_agent_may_write(self):
        self.assertEqual(L.parse_id("arXiv:1602.00865v1"), ("1602.00865", 1))
        self.assertEqual(L.parse_id(" 1602.00865 "), ("1602.00865", None))
        self.assertEqual(L.parse_id("cond-mat/0601001v2"), ("cond-mat/0601001", 2))
        for bad in ("", "1602.00865v0", "https://arxiv.org/abs/1602.00865", "1602.00865; drop", None, 7):
            self.assertIsNone(L.parse_id(bad), bad)
        self.assertTrue(L.id_after_cutoff("2501.00001"))
        self.assertFalse(L.id_after_cutoff("2412.99999"))

    def test_email_redaction_matches_the_gateways(self):
        self.assertEqual(L.redact_emails("write to a.b-c@dept.univ.edu. Thanks"), "write to [email]. Thanks")
        self.assertEqual(L.redact_emails("x@y and me@site.org, you@x.co.uk"), "x@y and [email], [email]")
        self.assertEqual(L.redact_emails("an @ sign, a@b, @handle"), "an @ sign, a@b, @handle")


# ------------------------------------------------------------------------------------------------------------ the policy
class Lines(LibraryCase):
    def test_the_three_lines_refuse_with_no_client_call(self):
        out = {}
        for _ in range(2):
            answer, out = self.call({"action": "search", "query": "variance risk premium"}, out)
            self.assertEqual(answer["status"], "ok")
        answer, out = self.call({"action": "search", "query": "tail risk"}, out)
        self.assertEqual(answer["status"], "refused")
        self.assertIn("research.cycle_calls", answer["reason"])
        self.assertEqual((out["literature_calls"], out["literature_refused"]), (2, 1))
        self.assertEqual(len(self.client.calls), 2)
        self.settings["research"]["family_requests_day"] = 3
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertEqual(answer["status"], "ok")
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertIn("research.family_requests_day", answer["reason"])
        self.fam = {"id": "other-family"}
        self.settings["research"]["requests_day"] = 3
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertIn("research.requests_day", answer["reason"])
        self.assertEqual(len(self.client.calls), 3)
        self.clock.advance(86400)
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertEqual(answer["status"], "ok", "a new UTC day")

    def test_a_busy_queue_or_a_refusal_counts_as_no_call_and_a_timeout_does(self):
        self.client.raises = [L.LibraryError("busy", status=429, busy=True), L.LibraryError("later", status=403, refused="after_cutoff"),
                              L.LibraryError("gone", counted=True)]
        busy, out = self.call({"action": "search", "query": "tail risk"})
        self.assertEqual(busy["status"], "busy")
        self.assertIn("not counted", busy["reason"])
        self.assertEqual(out.get("literature_calls"), 0, "the cycle keeps its call")
        refused, out = self.call({"action": "read", "id": "arXiv:2502.00001"}, out)
        self.assertIn("by the end of 2024", refused["reason"])
        self.assertEqual(len(self.client.calls), 1, "a 25xx id is refused before any call")
        refused, out = self.call({"action": "read", "id": "arXiv:2212.06888v3"}, out)
        self.assertIn("by the end of 2024 only", refused["reason"])
        self.assertNotIn("withheld", json.dumps(refused))
        failed, out = self.call({"action": "search", "query": "skew"}, out)
        self.assertEqual(failed["status"], "refused")
        self.assertEqual(out["literature_calls"], 1)
        self.assertEqual(self.library.used(), (1, {"condor-vrp": 1}))
        self.assertEqual([e["counted"] for e in self.events()], [False, False, True])

    def test_too_little_of_the_cycle_left_or_the_library_off_refuses(self):
        answer, _ = self.call({"action": "search", "query": "tail risk"}, left=30)
        self.assertIn("too little of this cycle", answer["reason"])
        self.settings["research"]["enabled"] = False
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertIn("not switched on", answer["reason"])
        self.assertEqual(self.client.calls, [])
        self.assertIsNotNone(L.Library(self.store, None, enabled_settings()).room("researcher", "x"), "no client: off")

    def test_a_typo_in_a_line_never_lifts_it(self):
        for bad in ("many", -1, True, float("nan"), None):
            self.settings["research"]["requests_day"] = bad
            self.assertIsNone(self.library.room("researcher", "x"), bad)  # the default, 300, binds
        self.settings["research"]["requests_day"] = 0
        self.assertIn("research.requests_day", self.library.room("researcher", "x"))


class Tool(LibraryCase):
    def test_the_tool_is_anthropics_shape_and_its_inputs_validate(self):
        [tool] = CR.anthropic_tools([L.LITERATURE_TOOL])
        self.assertEqual(tool["name"], "literature")
        self.assertEqual(tool["input_schema"]["required"], ["action"])
        schema = L.LITERATURE_TOOL["parameters"]
        self.assertEqual(CR.validate(schema, {"action": "search", "query": "vrp", "category": "q-fin"})[1], None)
        self.assertEqual(CR.validate(schema, {"action": "read", "id": "arXiv:1602.00865v1", "start": 8000})[1], None)
        self.assertIn("one of", CR.validate(schema, {"action": "browse"})[1])
        self.assertIn("no key url", CR.validate(schema, {"action": "read", "url": "https://x"})[1])
        self.assertIn("one of", CR.validate(schema, {"action": "search", "query": "x", "category": "physics"})[1])
        self.assertIn("must be an integer", CR.validate(schema, {"action": "read", "id": "x", "start": "0"})[1])
        self.assertNotIn("2025", json.dumps(L.LITERATURE_TOOL) + L.LIBRARY_RULE + L.BLOCK_HEADER, "the prompts name no later year")

    def test_a_search_answers_compact_checked_items_and_an_event_with_the_query_and_ids_only(self):
        self.client.searches = {"*": search_answer(ITEMS + [item(day="2025-03-01", base="2001.00009")])}
        answer, out = self.call({"action": "search", "query": "variance risk premium", "category": "q-fin"})
        self.assertEqual(answer["status"], "ok")
        self.assertEqual([i["id"] for i in answer["items"]], [i["id"] for i in ITEMS], "the 2025 version dropped again")
        self.assertNotIn("withheld", json.dumps(answer), "no count of later work reaches a model")
        self.assertNotIn("cached", answer)
        self.assertEqual(self.client.calls[0][1:], ("variance risk premium", "q-fin", 5, "condor-vrp", "researcher"))
        self.assertEqual(out["literature_ids"], [i["id"] for i in ITEMS])
        [event] = self.events()
        self.assertEqual({k: event[k] for k in ("role", "family", "action", "query", "category", "status", "counted")},
                         {"role": "researcher", "family": "condor-vrp", "action": "search", "query": "variance risk premium",
                          "category": "q-fin", "status": "ok", "counted": True})
        self.assertEqual(event["ids"], [i["id"] for i in ITEMS])
        self.assertEqual(event["withheld"]["after_cutoff"], 4, "the operator's log keeps the counts")
        text = json.dumps(event)
        for private in ("abstract", "text", "variance risk premium in index options", "Tail Risk Premia"):
            self.assertNotIn(private if private != "text" else '"text"', text)
        self.assertNotIn(L.EVENT, PUBLIC_KINDS)
        self.assertIn(L.EVENT, SKIPPED_KINDS)

    def test_a_read_answers_a_checked_window(self):
        answer, out = self.call({"action": "read", "id": "arXiv:2409.06496v1", "start": 0})
        self.assertEqual((answer["status"], answer["id"], answer["text_source"]), ("ok", "arXiv:2409.06496v1", "arxiv_html"))
        self.assertEqual(self.client.calls[0][:4], ("read", "2409.06496v1", 0, 8000))
        [event] = self.events()
        self.assertEqual((event["action"], event["id"], event["ids"]), ("read", "arXiv:2409.06496v1", ["arXiv:2409.06496v1"]))
        self.assertNotIn("premium is large", json.dumps(event))

    def test_a_version_served_in_place_of_the_one_named_is_no_such_paper(self):
        self.client.reads = {"*": read_answer("2212.06888", 1)}  # a gateway that still served v1 for a later version
        swapped, out = self.call({"action": "read", "id": "arXiv:2212.06888v3"})
        self.client.reads = {}
        self.client.raises = [L.LibraryError("gone", status=404, refused="not_found")]
        missing, out = self.call({"action": "read", "id": "arXiv:2212.06888v9"}, out)
        self.assertEqual(swapped, missing, "a later version and a missing one read the same")
        self.assertEqual(swapped, {"status": "refused", "reason": "no such paper"})
        self.assertEqual(out["literature_refused"], 2)
        self.assertNotIn("literature_ids", out)

    def test_every_call_waits_at_least_the_client_floor_and_ends_before_the_cycle(self):
        self.call({"action": "search", "query": "tail risk"}, left=170)
        self.call({"action": "read", "id": "2409.06496"}, left=45)
        self.assertEqual(self.client.timeouts, [60, L.CLIENT_FLOOR_SECONDS])
        refused, _ = self.call({"action": "search", "query": "skew"}, left=L.CLIENT_FLOOR_SECONDS + 4)
        self.assertIn("too little of this cycle", refused["reason"])
        self.settings["research"]["min_seconds_left"] = 0
        refused, _ = self.call({"action": "search", "query": "skew"}, left=L.CLIENT_FLOOR_SECONDS)
        self.assertIn("too little of this cycle", refused["reason"], "a setting of 0 never cuts under the floor")
        self.assertEqual(len(self.client.calls), 2)

    def test_the_semantics_search_needs_a_query_and_read_an_id(self):
        for args, why in (({"action": "search"}, "needs a query"), ({"action": "search", "query": "vol 2025"}, "no year"),
                          ({"action": "search", "query": "cat:q-fin.PR"}, "plain words"), ({"action": "read"}, "needs an id"),
                          ({"action": "read", "id": "https://arxiv.org/abs/1"}, "needs an id"), ({"action": "fetch"}, "search or read"),
                          ({"action": "read", "id": "1602.00865", "start": -5}, "0 or more")):
            answer, _ = self.call(args)
            self.assertEqual(answer["status"], "refused", args)
            self.assertIn(why, answer["reason"], args)
        self.assertEqual(self.client.calls, [])

    def test_the_call_is_made_outside_any_store_transaction(self):
        took = []

        def probe():
            def other():
                with self.store.atomic():
                    self.store.put("probe", 1)
                took.append(True)
            thread = threading.Thread(target=other)
            thread.start()
            thread.join(5)
            took.append(not thread.is_alive())

        self.client.during = probe
        answer, _ = self.call({"action": "search", "query": "tail risk"})
        self.assertEqual(answer["status"], "ok")
        self.assertEqual(took, [True, True], "another connection took the store's lock while the call was out")

    def test_no_tool_output_names_a_post_cutoff_date(self):
        poisoned = search_answer([item(abstract="Out of sample through 2030 and by Q3 2027; see arXiv:2501.01234."),
                                  item("2311.04444", 1, "2023-11-08", title="Bonds maturing 2026-12-14")])
        self.client.searches = {"*": poisoned}
        self.client.reads = {"*": read_answer(text="In 2026 the notes mature (2027). This draft March 2025.")}
        outputs = [self.call({"action": "search", "query": "variance"})[0], self.call({"action": "read", "id": "2409.06496"})[0]]
        for answer in outputs:
            self.assertEqual(answer["status"], "ok")
            for dumped in (json.dumps(answer), json.dumps(answer, ensure_ascii=False)):
                self.assertFalse(L.has_post_cutoff(dumped), dumped)


# ------------------------------------------------------------------------------------------------------------ retrieval
class Retrieval(LibraryCase):
    def test_a_block_merges_by_rank_and_paper_and_is_kept_for_its_life(self):
        self.client.searches = {"variance risk premium": search_answer(ITEMS[:2]),
                                "overnight returns index options": search_answer([ITEMS[1], ITEMS[2], item("1805.01234", 2, "2018-05-03", "2019-02-11")])}
        block = self.library.retrieve(["variance risk premium", "overnight returns index options", "bad: query", "the 2026 crash"])
        self.assertEqual(block.ids, ("arXiv:1602.00865v1", "arXiv:2207.00949v1", "arXiv:2412.09999v1", "arXiv:1805.01234v2"))
        self.assertEqual(block.queries, ("variance risk premium", "overnight returns index options"), "bad searches never sent")
        self.assertTrue(block.text.startswith("THE LIBRARY: 4 items retrieved for these searches: variance risk premium; overnight"))
        self.assertIn("[arXiv:1805.01234v2] Tail Risk Premia", block.text)
        self.assertIn("First posted 2018-05; this version 2019-02. q-fin.PM.", block.text)
        self.assertNotIn("2025", block.text.split("\n", 1)[1])
        self.assertEqual([c[5] for c in self.client.calls], ["architect", "architect"])
        self.assertEqual([c[3] for c in self.client.calls], [4, 4], "per_query")
        again = self.library.retrieve(["variance risk premium", "overnight returns index options"])
        self.assertEqual(len(self.client.calls), 2, "the kept block: no call")
        self.assertEqual(again.text, block.text)
        self.clock.advance(10800)
        self.library.retrieve(["variance risk premium", "overnight returns index options"])
        self.assertEqual(len(self.client.calls), 4, "past its life: asked again")
        self.assertEqual([e["role"] for e in self.events()], ["architect"] * 4)

    def test_a_retrieval_search_waits_at_least_the_client_floor(self):
        clock = self.clock

        def slow():
            clock.advance(55)

        self.client.during = slow
        self.library.retrieve(["variance risk premium", "tail risk", "skew"])
        self.assertEqual(self.client.timeouts, [60, L.CLIENT_FLOOR_SECONDS], "the second search had 5 s of the budget left")
        self.assertIsNone(self.store.get(L.BLOCK_KEY), "past the budget: the third is not asked, and the block is not kept")

    def test_cited_ids_resolve_to_the_block_by_paper(self):
        block = self.library.retrieve(["variance risk premium"])
        cited, dropped = block.resolve(["1602.00865", "arXiv:2207.00949v3", "arXiv:9999.00001v1", 7, "arXiv:1602.00865v1"])
        self.assertEqual(cited, [{"id": "arXiv:1602.00865v1", "title": "Tail Risk Premia for Long-Term Equity Investors"},
                                 {"id": "arXiv:2207.00949v1", "title": "Stochastic arbitrage with market index options"}])
        self.assertEqual(dropped, 2)

    def test_the_seed_rotation_moves_only_when_the_block_expires(self):
        seeds = self.settings["research"]["seed_queries"]
        first = self.library.queries_for(None)
        self.assertEqual(first, seeds[:4])
        self.assertEqual(self.library.queries_for({}), seeds[:4], "inside the block's life: the same searches")
        self.clock.advance(10800)
        self.assertEqual(self.library.queries_for(None), seeds[4:8])
        self.clock.advance(10800)
        self.assertEqual(self.library.queries_for(None), seeds[:4])
        section = {"text": "x", "library_queries": ["dealer gamma", "the 2027 crash"]}
        self.assertEqual(self.library.queries_for(section), ["dealer gamma"], "the strategist's searches first")

    def test_retrieval_off_busy_or_capped(self):
        self.settings["research"]["enabled"] = False
        self.assertIsNone(self.library.retrieve(["variance risk premium"]))
        self.settings["research"]["enabled"] = True
        self.client.raises = [L.LibraryError("busy", status=429, busy=True), None]
        block = self.library.retrieve(["variance risk premium", "tail risk"])
        self.assertEqual(len(block.ids), 3, "the second search answered")
        self.assertIsNone(self.store.get(L.BLOCK_KEY), "an incomplete block is not kept")
        self.client.raises = [L.LibraryError("spent", status=429, cap="library_day")]
        self.assertIsNone(self.library.retrieve(["variance risk premium", "tail risk"]))
        self.assertEqual(len(self.client.calls), 3, "the day's cap ends the retrieval")


# ------------------------------------------------------------------------------------------------------------ no web
class NoWeb(unittest.TestCase):
    def test_the_swarm_never_names_the_open_web_reader(self):
        for path in sorted((REPO / "league" / "swarm").glob("*.py")):
            text = path.read_text()
            for name in ("/v1/web/fetch", "web_fetch", "Commons"):
                self.assertNotIn(name, text, f"{path.name} names {name}")

    def test_the_client_reaches_only_the_library_routes(self):
        text = (REPO / "league" / "swarm" / "library.py").read_text()
        self.assertEqual(sorted(set(re.findall(r'"(/v1/[a-z/]+)"', text))), ["/v1/research/read", "/v1/research/search"])


if __name__ == "__main__":
    unittest.main()
