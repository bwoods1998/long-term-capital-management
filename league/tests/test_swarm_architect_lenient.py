"""The architect reads a complete answer whose JSON has stray trailing commas (Oct 1, 2026: Sail k3 at medium effort), and
one whose families array still does not parse whole (15:59Z: a stray `}` after two of its six families) object by object."""
import json
import unittest

from league.swarm.architect import read_families, recover_families, salvage_families, without_trailing_commas
from league.swarm.models import extract_json

FAMILY = {"slug": "a-b", "mechanism": "Commas, and \"quotes\", stay: ,} ,] inside strings.", "structure": "debit_vertical",
          "roots": ["SLV"], "card": {"hypothesis": "h", "falsification": "f"}}


def sloppy(n: int) -> str:
    """A fenced answer of n families, each with a trailing comma after its card and one after the array's last item."""
    body = ",\n".join(json.dumps({**FAMILY, "slug": f"fam-{i}"})[:-1] + ",}" for i in range(n))
    return "```json\n{\"families\": [\n" + body + ",\n]}\n```"


class LenientRead(unittest.TestCase):
    def test_the_strict_reader_loses_every_family(self):
        text = sloppy(3)
        self.assertNotIn("families", extract_json(text) or {})
        self.assertEqual(salvage_families(text), [])

    def test_a_complete_answer_with_trailing_commas_is_read_whole(self):
        text = sloppy(3)
        rows, lenient, _ = read_families({"text": text, "json": extract_json(text)})
        self.assertTrue(lenient)
        self.assertEqual([r["slug"] for r in rows], ["fam-0", "fam-1", "fam-2"])
        self.assertEqual(rows[0]["mechanism"], FAMILY["mechanism"])  # commas and brackets inside strings are kept

    def test_a_valid_answer_is_read_as_before(self):
        text = json.dumps({"families": [FAMILY]})
        rows, lenient, _ = read_families({"text": text, "json": extract_json(text)})
        self.assertFalse(lenient)
        self.assertEqual(rows, [FAMILY])

    def test_an_answer_with_no_families_stays_none(self):
        for answer in ({"text": "", "json": None}, {"text": "no json here", "json": None},
                       {"text": "{\"note\": \"nothing\",}", "json": None}):
            self.assertEqual(read_families(answer), (None, False, None))

    def test_an_empty_array_is_a_real_zero(self):
        text = "{\"families\": []}"
        self.assertEqual(read_families({"text": text, "json": extract_json(text)}), ([], False, None))

    def test_a_cut_answer_keeps_its_complete_families_even_with_trailing_commas(self):
        text = sloppy(3)
        cut = text[: text.index("fam-2")]
        rows, lenient, _ = read_families({"text": cut, "json": None, "truncated": True})
        self.assertEqual([r["slug"] for r in rows], ["fam-0", "fam-1"])
        self.assertFalse(lenient)

    def test_commas_only_close_containers(self):
        self.assertEqual(without_trailing_commas('{"a": [1, 2,], "b": "x,}",}'), '{"a": [1, 2], "b": "x,}"}')
        self.assertEqual(without_trailing_commas('{"a": "\\\\",}'), '{"a": "\\\\"}')


def between(first: dict, rest: list, sep: str) -> str:
    """A bare answer: the first family, `sep` right after its own closing brace, then the rest of the families."""
    return '{"families": [' + json.dumps(first) + sep + ", ".join(json.dumps(r) for r in rest) + "]}"


class StrayBrace(unittest.TestCase):
    """A complete answer whose families array does not parse whole (Oct 1, 2026, 15:59Z: Sail k3 wrote a stray `}` after
    the fourth and the fifth of six families, and the pass read as no proposals) is read object by object, nothing inside a family
    changed."""

    cards = [{**FAMILY, "slug": f"fam-{i}"} for i in range(3)]

    def read(self, text: str):
        return read_families({"text": text, "json": extract_json(text)})

    def test_the_strict_and_the_trailing_comma_readers_lose_every_family(self):
        text = between(self.cards[0], self.cards[1:], "}, ")
        self.assertEqual(extract_json(text), self.cards[0])  # the router's reader falls back to the first card
        self.assertEqual(without_trailing_commas(text), text)  # #472's read has nothing to strip
        self.assertEqual(salvage_families(text), self.cards[:1])  # the cut salvage stops at the stray brace

    def test_a_stray_brace_between_two_families_is_skipped(self):
        rows, lenient, recovered = self.read(between(self.cards[0], self.cards[1:], "}, "))
        self.assertEqual(rows, self.cards)  # every family, byte for byte
        self.assertFalse(lenient)
        self.assertEqual(recovered["count"], 3)
        self.assertIn("Expecting ',' delimiter", recovered["why"])
        self.assertIn("stray '}' between the families skipped", recovered["why"])
        self.assertNotIn("passed", recovered)

    def test_a_stray_comma_and_a_stray_brace_together(self):
        rows, lenient, recovered = self.read(between(self.cards[0], self.cards[1:], "},, "))  # a doubled comma
        self.assertEqual((rows, lenient, recovered["count"]), (self.cards, False, 3))
        self.assertIn("stray '},' between the families skipped", recovered["why"])
        rows, lenient, recovered = self.read(between(self.cards[0], self.cards[1:], ",}, "))  # a trailing comma too
        self.assertEqual((rows, lenient, recovered["count"]), (self.cards, True, 3))  # #472's strip, then the walk
        self.assertIn("stray '}' between the families skipped", recovered["why"])

    def test_a_stray_bracket_that_a_family_follows_is_skipped_and_the_real_end_stops_the_walk(self):
        rows, _, recovered = self.read(between(self.cards[0], self.cards[1:], "], "))
        self.assertEqual((rows, recovered["count"]), (self.cards, 3))
        after = between(self.cards[0], self.cards[1:], "}, ") + ', {"slug": "after", "mechanism": "not in the array"}'
        rows, _, recovered = self.read(after)
        self.assertEqual((rows, recovered["count"]), (self.cards, 3))

    def test_a_cut_answer_is_still_the_salvage(self):
        text = between(self.cards[0], self.cards[1:], ", ")
        cut = text[: text.index("fam-2")]
        self.assertEqual(read_families({"text": cut, "json": None, "truncated": True}), (self.cards[:2], False, None))
        rows, lenient, recovered = self.read(cut)  # the same cut, unmarked: what completed, and the cut object passed over
        self.assertEqual((rows, lenient, recovered["count"], recovered["passed"]), (self.cards[:2], False, 2, 1))

    def test_an_object_that_does_not_decode_is_passed_over_not_repaired(self):
        text = ('{"families": [' + json.dumps(self.cards[0]) + ', {"slug": "fam-1" "mechanism": "no colon"}, '
                + json.dumps(self.cards[2]) + "]}")
        rows, lenient, recovered = self.read(text)
        self.assertEqual((rows, lenient), ([self.cards[0], self.cards[2]], False))
        self.assertEqual((recovered["count"], recovered["passed"]), (2, 1))
        self.assertIn("1 object that did not decode passed over", recovered["why"])

    def test_a_decoded_object_that_is_no_family_is_dropped(self):
        text = '{"families": [{"param": "signal_on", "off": 0}, }' + json.dumps(self.cards[1]) + "]}"
        rows, _, recovered = self.read(text)
        self.assertEqual((rows, recovered["count"]), ([self.cards[1]], 1))
        self.assertIn("1 object without a mechanism dropped", recovered["why"])
        self.assertEqual(recover_families(text)[1], {"stray": "}", "passed": 0, "dropped": 1})

    def test_an_answer_with_no_readable_family_stays_none(self):
        for text in ('{"families": [{"slug": "x" "bad"}]}', '{"families": [}, {"param": 1}]}',
                     'prose with "families": [ and no object'):
            self.assertEqual(self.read(text), (None, False, None))

    def test_a_long_prose_preamble_with_braces_before_the_json(self):
        line = 'Think in {sets}: {"a": 1} is an object, {"b": {"c": 2}} nests, 2" of rain, "quoted", ] and } close. '
        prose = (line * 400)[:30000]
        text = prose + "\n" + between(self.cards[0], self.cards[1:], "}, ")
        self.assertEqual(extract_json(text), {"a": 1})  # the router's reader takes the first object in the prose
        rows, lenient, recovered = self.read(text)
        self.assertEqual((rows, lenient, recovered["count"]), (self.cards, False, 3))
        self.assertIn("stray '}' between the families skipped", recovered["why"])
        text = prose + "\n" + json.dumps({"families": self.cards})  # a valid answer after it: whole, from its own brace
        rows, lenient, recovered = self.read(text)
        self.assertEqual((rows, lenient, recovered["count"]), (self.cards, False, 3))
        self.assertIn("parses from its own `{`", recovered["why"])


if __name__ == "__main__":
    unittest.main()


from league.tests.test_swarm_architect_sail import CUT, SailCase, cut_text, families  # noqa: E402


def sloppy_answer(n: int) -> str:
    """A complete fenced Sail answer of n families with a stray comma closing each family and the array."""
    body = ",\n".join(json.dumps(f)[:-1] + ",}" for f in families(n))
    return "```json\n{\"families\": [\n" + body + ",\n]}\n```"


class LenientPass(SailCase):
    def test_a_complete_answer_with_trailing_commas_is_born_and_the_event_says_lenient(self):
        self.replies = [{"text": sloppy_answer(3)}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 3)
        self.assertEqual(out["born"], ["idea-0", "idea-1", "idea-2"])
        self.assertTrue(out.get("lenient"))
        self.assertTrue(self.event().get("lenient"))
        self.assertNotIn("recovered", out)  # read whole once the commas were gone

    def test_a_valid_answer_is_not_marked_lenient(self):
        self.replies = [{"text": "```json\n" + json.dumps({"families": families(2)}) + "\n```"}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 2)
        self.assertFalse({"lenient", "recovered"} & set(out))

    def test_an_answer_with_an_unreadable_object_keeps_the_others(self):
        broken = "```json\n{\"families\": [" + json.dumps(families(1)[0]) + ", {\"slug\": \"x\" \"bad\"}]}\n```"
        self.replies = [{"text": broken}]
        out = self.arch().run()
        self.assertEqual((out["proposed"], out["born"]), (1, ["idea-0"]))  # #472: 0, the whole answer unread
        self.assertNotIn("lenient", out)
        self.assertEqual((out["recovered"]["count"], out["recovered"]["passed"]), (1, 1))
        self.assertIn("1 object that did not decode passed over", out["recovered"]["why"])

    def test_an_answer_with_no_readable_family_stays_unread(self):
        self.replies = [{"text": "```json\n{\"families\": [{\"slug\": \"x\" \"bad\"}]}\n```"}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 0)
        self.assertFalse({"lenient", "recovered"} & set(out))


class PreambleQuotes(unittest.TestCase):
    def test_prose_before_the_json_cannot_flip_the_string_tracking(self):
        text = 'Use the 2" rule.\n' + sloppy(2).replace("Commas, and", "buy the 5, ] wing; commas, and")
        rows, lenient, _ = read_families({"text": text, "json": extract_json(text)})
        self.assertTrue(lenient)
        self.assertEqual(len(rows), 2)
        self.assertIn("buy the 5, ] wing", rows[0]["mechanism"])

    def test_a_valid_answer_after_an_example_object_is_read_from_its_own_brace(self):
        text = 'Example: {"slug": "example"}\n' + json.dumps({"families": [FAMILY]})
        self.assertEqual(extract_json(text), {"slug": "example"})  # the router's reader takes the example (#472: unread)
        rows, lenient, recovered = read_families({"text": text, "json": extract_json(text)})
        self.assertEqual((rows, lenient), ([FAMILY], False))
        self.assertEqual(recovered, {"count": 1, "why": "the families object parses from its own `{`; the router's reader "
                                                        "took an earlier object"})


def stray_answer(n: int, sep: str = "}, ") -> str:
    """A complete fenced Sail answer of n families with `sep` written after the first family's own closing brace."""
    rows = families(n)
    return "```json\n" + between(rows[0], rows[1:], sep) + "\n```"


class RecoveredPass(SailCase):
    def test_a_stray_brace_answer_is_born_and_the_event_says_recovered(self):
        self.replies = [{"text": stray_answer(3)}]
        out = self.arch().run()
        self.assertEqual((out["proposed"], out["born"]), (3, ["idea-0", "idea-1", "idea-2"]))
        self.assertEqual(out["recovered"]["count"], 3)
        self.assertIn("stray '}' between the families skipped", out["recovered"]["why"])
        self.assertNotIn("lenient", out)
        self.assertEqual(self.event()["recovered"], out["recovered"])

    def test_a_stray_comma_and_brace_answer_says_lenient_and_recovered(self):
        self.replies = [{"text": stray_answer(2, ",}, ")}]
        out = self.arch().run()
        self.assertEqual((out["proposed"], out["born"]), (2, ["idea-0", "idea-1"]))
        self.assertTrue(out["lenient"])
        self.assertEqual(self.event()["recovered"]["count"], 2)

    def test_a_cut_answer_is_still_salvaged_not_recovered(self):
        self.replies = [{"text": cut_text(4), **CUT}]
        out = self.arch().run()
        self.assertEqual(out["truncated"], {"salvaged": 4, "born": 4})
        self.assertFalse({"lenient", "recovered"} & set(out))
