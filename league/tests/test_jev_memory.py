"""J3, the swarm's shared memory: choice and partial answers in the Sensor, the index and its
labels, the three-arm retrieval, the graveyard query, the report and the House wiring.

No network and no paid call anywhere: the gateway is a stand-in."""
import email.message
import io
import json
import tempfile
import unittest
import urllib.error
from decimal import Decimal
from pathlib import Path

from league.jev import CHOICE_BATCH, MODEL, PARTIAL_HEADER, Sensor
from league.tests.fakes import Clock

KINDS = {"a": "the first kind", "b": "the second kind", "c": "the third kind"}


def choice(options=KINDS, text="Which kind does the document in state describe?"):
    return {"instructions": text, "criteria": dict(options)}


class TypedJev:
    """A gateway stand-in for typed questions. noul -> `p`; choice -> `pick(name, options)` (default
    the first option) with 0.7 on the choice. A name in `bad` gets an invalid answer, or, with
    `partial`, is listed in `rejected` as the gateway's opt-in partial response does."""

    def __init__(self, p=0.7, pick=None, *, bad=(), partial=False, cost="0.0001", fail=None):
        self.p, self.pick, self.bad, self.partial, self.cost, self.fail = p, pick, set(bad), partial, cost, fail
        self.calls = []

    def __call__(self, ident, body):
        request = json.loads(body)
        self.calls.append((ident, request))
        if self.fail is not None:
            raise self.fail
        answers, rejected = {}, {}
        items = request["state"].get("items") or {} if isinstance(request["state"], dict) else {}
        for name, q in request["questions"].items():
            if name in self.bad:
                if self.partial:
                    rejected[name] = "the choice is not one of the options"
                    continue
                answers[name] = {"type": q["type"], "choice": "nonsense", "noul": 7}
                continue
            if q["type"] == "noul":
                p = self.p(items.get(name, name)) if callable(self.p) else self.p
                answers[name] = {"type": "noul", "noul": p}
            else:
                options = list(q["criteria"])
                picked = self.pick(name, options) if self.pick else options[0]
                rest = (1 - 0.7) / (len(options) - 1)
                answers[name] = {"type": "choice", "choice": picked, "confidence": 0.7,
                                 "probabilities": {o: (0.7 if o == picked else rest) for o in options}}
        response = {"model": MODEL, "answers": answers, "usage": {"input_tokens": 100}}
        if rejected:
            response["rejected"] = rejected
        return response, Decimal(self.cost)


def gateway_refusal(code, body, *, cost=None):
    """An HTTPError as urllib raises it for the gateway's non-2xx answer, with its cost headers."""
    headers = email.message.Message()
    if cost is not None:
        headers["X-LTCM-Cost-USD"] = cost
        headers["X-LTCM-Cost-Known"] = "true"
    return urllib.error.HTTPError("https://gateway/v1/typesafe/systemone", code, "refused", headers,
                                  io.BytesIO(json.dumps(body).encode()))


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def sensor(self, client, name="jev.sqlite", **kw):
        return Sensor(self.root / name, client, clock=self.clock, **kw)

    def statuses(self, sensor):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(sensor.path)) as db:
            return [row[0] for row in db.execute("SELECT status FROM calls ORDER BY rowid")]


class ChoiceAnswerTest(Case):
    """`ask_state` asks named-option questions beside noul ones, over one state."""

    def test_choice_and_noul_answers_share_one_request_and_are_cached(self):
        jev = TypedJev(0.25, pick=lambda name, options: options[1])
        sensor = self.sensor(jev)
        questions = {"kind": choice(), "shape": choice({"x": "ex", "y": "why"}), "names_data": "Does it name a feed?"}
        receipt = {}
        answers = sensor.ask_state("memory", "doc:1", {"document": "text"}, questions, receipt=receipt)
        self.assertEqual(answers["kind"][0], "b")
        self.assertEqual(set(answers["kind"][1]), set(KINDS))
        self.assertAlmostEqual(sum(answers["kind"][1].values()), 1.0)
        self.assertEqual(answers["shape"][0], "y")
        self.assertEqual(answers["names_data"], 0.25)
        self.assertEqual(len(jev.calls), 1)
        sent = jev.calls[0][1]["questions"]
        self.assertEqual(sent["kind"], {"type": "choice", "instructions": questions["kind"]["instructions"], "criteria": KINDS})
        self.assertEqual(sent["names_data"], {"type": "noul", "instructions": "Does it name a feed?"})
        self.assertEqual(receipt["bought"], 3)
        again = sensor.ask_state("memory", "doc:1", {"document": "text"}, questions)
        self.assertEqual(again, answers)
        self.assertEqual(len(jev.calls), 1, "every answer is bought once")
        self.assertEqual(sensor.stats()["cached_choices"], 2)
        self.assertEqual(sensor.stats()["today"]["memory"]["cache_hits"], 3)

    def test_a_request_holding_a_choice_carries_at_most_four_questions(self):
        jev = TypedJev()
        sensor = self.sensor(jev)
        sensor.ask_state("memory", "doc:2", "state", {f"c{n}": choice() for n in range(6)})
        self.assertEqual([len(r["questions"]) for _, r in jev.calls], [CHOICE_BATCH, 2])
        jev.calls.clear()
        sensor.ask_state("memory", "doc:3", "state", {f"n{n}": "A yes/no question?" for n in range(6)})
        self.assertEqual([len(r["questions"]) for _, r in jev.calls], [6], "noul-only requests keep the 16 limit")
        jev.calls.clear()
        sensor.ask_state("memory", "doc:4", "state", {f"n{n}": "A yes/no question?" for n in range(6)}, batch=4)
        self.assertEqual([len(r["questions"]) for _, r in jev.calls], [4, 2])

    def test_an_answer_over_other_options_is_not_served_from_the_cache(self):
        jev = TypedJev()
        sensor = self.sensor(jev)
        sensor.ask_state("memory", "doc:5", "state", {"kind": choice()})
        changed = {**KINDS, "d": "a fourth kind"}
        answers = sensor.ask_state("memory", "doc:5", "state", {"kind": choice(changed)})
        self.assertEqual(len(jev.calls), 2, "a changed taxonomy is asked again")
        self.assertEqual(set(answers["kind"][1]), set(changed))

    def test_a_malformed_choice_raises_before_anything_is_bought(self):
        jev = TypedJev()
        sensor = self.sensor(jev)
        for bad in ({"instructions": "x", "criteria": {"only": "one option"}},
                    {"instructions": "x", "criteria": {"has space": "a", "b": "b"}},
                    {"instructions": "", "criteria": KINDS}, 42):
            with self.assertRaises(ValueError):
                sensor.ask_state("memory", "doc:6", "state", {"q": bad})
        self.assertEqual(jev.calls, [])

    def test_an_invalid_choice_without_partial_answers_is_an_outage_as_before(self):
        jev = TypedJev(bad={"kind"})
        sensor = self.sensor(jev)
        receipt = {}
        answers = sensor.ask_state("memory", "doc:7", "state", {"kind": choice(), "other": choice()}, receipt=receipt)
        self.assertEqual(answers, {"kind": None, "other": None})
        self.assertTrue(receipt["failed"])
        self.assertIn("breaker open", sensor.refusal("memory"))
        self.assertEqual(self.statuses(sensor), ["rejected"])

    def test_caps_and_the_breaker_apply_to_choices(self):
        jev = TypedJev()
        sensor = self.sensor(jev, purpose_calls={"memory": 1})
        sensor.ask_state("memory", "doc:8", "state", {"kind": choice()})
        receipt = {}
        answers = sensor.ask_state("memory", "doc:9", "state", {"kind": choice()}, receipt=receipt)
        self.assertEqual(answers, {"kind": None})
        self.assertIn("memory call cap", receipt["refused"])
        self.assertEqual(len(jev.calls), 1)
        self.assertEqual(sensor.refusal("gate"), "", "another purpose is not capped by this one")


class PartialAnswerTest(Case):
    """The gateway's opt-in partial answers (J5): valid answers kept, rejected names unanswered,
    never an outage."""

    def test_a_partial_response_keeps_the_valid_answers_and_opens_no_breaker(self):
        jev = TypedJev(0.6, bad={"kind"}, partial=True)
        sensor = self.sensor(jev)
        questions = {"kind": choice(), "shape": choice(), "names_data": "Does it name a feed?"}
        receipt = {}
        answers = sensor.ask_state("memory", "doc:10", "state", questions, receipt=receipt)
        self.assertIsNone(answers["kind"])
        self.assertEqual(answers["shape"][0], "a")
        self.assertEqual(answers["names_data"], 0.6)
        self.assertEqual(receipt["rejected"], {"kind": "the choice is not one of the options"})
        self.assertEqual(receipt["bought"], 2)
        self.assertNotIn("failed", receipt)
        self.assertNotIn("refused", receipt)
        self.assertEqual(sensor.refusal("memory"), "", "a rejected answer is not an outage")
        self.assertEqual(self.statuses(sensor), ["partial"])
        self.assertEqual(sensor.spent_today("memory"), Decimal("0.0001"))
        jev.bad.clear()
        answers = sensor.ask_state("memory", "doc:10", "state", questions)
        self.assertEqual(list(jev.calls[-1][1]["questions"]), ["kind"], "only the rejected name is asked again")
        self.assertEqual(answers["kind"][0], "a")

    def test_partial_answers_in_ask_come_back_none(self):
        jev = TypedJev(0.8, bad={"q1"}, partial=True)
        sensor = self.sensor(jev)
        answers = sensor.ask("memory", {"strategy": "s"}, {f"k{n}": (f"item {n}", "Relevant?") for n in range(10)}, batch=4)
        self.assertEqual([len(r["questions"]) for _, r in jev.calls], [4, 4, 2], "a partial batch does not stop the next")
        self.assertEqual([k for k, v in answers.items() if v is None], ["k1", "k5", "k9"])
        self.assertEqual(sensor.refusal("memory"), "")

    def test_a_502_naming_rejected_answers_is_not_an_outage(self):
        refusal = gateway_refusal(502, {"error": "TypeSafe returned incompatible typed answers.",
                                        "rejected": {"kind": "no probabilities"}}, cost="0.000042")
        jev = TypedJev(fail=refusal)
        sensor = self.sensor(jev)
        receipt = {}
        answers = sensor.ask_state("memory", "doc:11", "state", {"kind": choice(), "shape": choice()}, receipt=receipt)
        self.assertEqual(answers, {"kind": None, "shape": None})
        self.assertEqual(receipt["rejected"], {"kind": "no probabilities"})
        self.assertNotIn("failed", receipt)
        self.assertEqual(sensor.refusal("memory"), "")
        self.assertEqual(self.statuses(sensor), ["answers_rejected"])
        self.assertEqual(sensor.spent_today("memory"), Decimal("0.000042"), "the gateway's own count of the call")

    def test_any_other_502_is_still_an_outage(self):
        jev = TypedJev(fail=gateway_refusal(502, {"error": "TypeSafe returned HTTP 500; no automatic retry."}))
        sensor = self.sensor(jev)
        receipt = {}
        sensor.ask_state("memory", "doc:12", "state", {"kind": choice()}, receipt=receipt)
        self.assertTrue(receipt["failed"])
        self.assertIn("breaker open", sensor.refusal("memory"))
        other = TypedJev(fail=gateway_refusal(502, {"rejected": {"never_asked": "x"}}))
        second = self.sensor(other, name="second.sqlite")
        second.ask_state("memory", "doc:12", "state", {"kind": choice()}, receipt=(r := {}))
        self.assertTrue(r["failed"], "a rejection naming questions that were not asked is not believed")

    def test_a_partial_response_must_cover_every_name_exactly_once(self):
        for response in ({"model": MODEL, "answers": {"kind": {"type": "noul", "noul": 0.5}}, "rejected": {"kind": "x"}},
                         {"model": MODEL, "answers": {"kind": {"type": "noul", "noul": 0.5}}},
                         {"model": MODEL, "answers": {}, "rejected": {"kind": "x", "extra": "y"}},
                         {"model": MODEL, "answers": {"kind": {"type": "noul", "noul": 0.5}, "extra": {"type": "noul", "noul": 1}},
                          "rejected": {"other": "x"}}):
            sensor = self.sensor(lambda ident, body, r=response: (r, Decimal("0.0001")), name=f"{id(response)}.sqlite")
            receipt = {}
            answers = sensor.ask_state("memory", "doc:13", "state", {"kind": "Q?", "other": "Q?"}, receipt=receipt)
            self.assertEqual(answers, {"kind": None, "other": None})
            self.assertTrue(receipt["failed"], response)

    def test_the_header_is_sent_through_the_gateway_client(self):
        from league.semantic_lab import JevClient

        seen = []

        class Response:
            headers = {"X-LTCM-Cost-USD": "0.0001", "X-LTCM-Cost-Known": "true"}

            def __init__(self, body):
                self.body = body

            def read(self, n):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def opener(request, timeout=None):
            seen.append({k.lower(): v for k, v in request.header_items()})
            question = next(iter(json.loads(request.data)["questions"]))
            return Response(json.dumps({"model": MODEL, "answers": {question: {"type": "noul", "noul": 0.5}}}).encode())

        client = JevClient("https://gateway.invalid", lambda: "token", opener=opener)
        sensor = self.sensor(client, partial=True)
        self.assertTrue(sensor.partial)
        sensor.request_partial_answers()  # twice is once: the header is not stacked
        self.assertEqual(sensor.ask_state("memory", "doc:14", "state", {"q": "Q?"}), {"q": 0.5})
        self.assertEqual(seen[0][PARTIAL_HEADER.lower()], "1")
        self.assertEqual(seen[0]["x-ltcm-request"][:7], "sensor-")
        plain = self.sensor(JevClient("https://gateway.invalid", lambda: "token", opener=opener), name="plain.sqlite")
        plain.ask_state("memory", "doc:15", "state", {"q": "Q?"})
        self.assertNotIn(PARTIAL_HEADER.lower(), seen[1], "without the opt-in nothing changes")
        self.assertFalse(plain.stats()["partial_answers"])


if __name__ == "__main__":
    unittest.main()
