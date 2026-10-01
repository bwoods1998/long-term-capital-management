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
