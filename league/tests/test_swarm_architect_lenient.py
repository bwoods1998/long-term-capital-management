"""The architect reads a complete answer whose JSON has stray trailing commas (Oct 1, 2026: Sail k3 at medium effort)."""
import json
import unittest

from league.swarm.architect import read_families, salvage_families, without_trailing_commas
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
        rows, lenient = read_families({"text": text, "json": extract_json(text)})
        self.assertTrue(lenient)
        self.assertEqual([r["slug"] for r in rows], ["fam-0", "fam-1", "fam-2"])
        self.assertEqual(rows[0]["mechanism"], FAMILY["mechanism"])  # commas and brackets inside strings are kept

    def test_a_valid_answer_is_read_as_before(self):
        text = json.dumps({"families": [FAMILY]})
        rows, lenient = read_families({"text": text, "json": extract_json(text)})
        self.assertFalse(lenient)
        self.assertEqual(rows, [FAMILY])

    def test_an_answer_with_no_families_stays_none(self):
        for answer in ({"text": "", "json": None}, {"text": "no json here", "json": None},
                       {"text": "{\"note\": \"nothing\",}", "json": None}):
            self.assertEqual(read_families(answer), (None, False))

    def test_an_empty_array_is_a_real_zero(self):
        text = "{\"families\": []}"
        self.assertEqual(read_families({"text": text, "json": extract_json(text)}), ([], False))

    def test_a_cut_answer_keeps_its_complete_families_even_with_trailing_commas(self):
        text = sloppy(3)
        cut = text[: text.index("fam-2")]
        rows, lenient = read_families({"text": cut, "json": None, "truncated": True})
        self.assertEqual([r["slug"] for r in rows], ["fam-0", "fam-1"])
        self.assertFalse(lenient)

    def test_commas_only_close_containers(self):
        self.assertEqual(without_trailing_commas('{"a": [1, 2,], "b": "x,}",}'), '{"a": [1, 2], "b": "x,}"}')
        self.assertEqual(without_trailing_commas('{"a": "\\\\",}'), '{"a": "\\\\"}')


if __name__ == "__main__":
    unittest.main()


from league.tests.test_swarm_architect_sail import SailCase, families  # noqa: E402


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

    def test_a_valid_answer_is_not_marked_lenient(self):
        self.replies = [{"text": "```json\n" + json.dumps({"families": families(2)}) + "\n```"}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 2)
        self.assertNotIn("lenient", out)

    def test_an_unreadable_answer_without_stray_commas_stays_unread(self):
        broken = "```json\n{\"families\": [" + json.dumps(families(1)[0]) + ", {\"slug\": \"x\" \"bad\"}]}\n```"
        self.replies = [{"text": broken}]
        out = self.arch().run()
        self.assertEqual(out["proposed"], 0)
        self.assertNotIn("lenient", out)


class PreambleQuotes(unittest.TestCase):
    def test_prose_before_the_json_cannot_flip_the_string_tracking(self):
        text = 'Use the 2" rule.\n' + sloppy(2).replace("Commas, and", "buy the 5, ] wing; commas, and")
        rows, lenient = read_families({"text": text, "json": extract_json(text)})
        self.assertTrue(lenient)
        self.assertEqual(len(rows), 2)
        self.assertIn("buy the 5, ] wing", rows[0]["mechanism"])

    def test_a_valid_answer_after_an_example_object_reads_as_before(self):
        text = 'Example: {"slug": "example"}\n' + json.dumps({"families": [FAMILY]})
        self.assertEqual(read_families({"text": text, "json": extract_json(text)}), (None, False))
