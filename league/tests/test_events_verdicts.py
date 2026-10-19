import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from league.events import store as S
from league.events import verdicts as V

REPO = Path(__file__).resolve().parents[2]
PREREG = REPO / "docs" / "prereg" / "PREREG-EVL-1.md"
UTC = dt.timezone.utc


def prereg_block(after_label):
    """The indented code block that follows `after_label` in the prereg, dedented by its 4 spaces."""
    text = PREREG.read_text(encoding="utf-8")
    start = text.index(after_label)
    block = re.search(r"\n\n((?:    .*\n)+)", text[start:])
    return "\n".join(line[4:] for line in block.group(1).rstrip("\n").split("\n"))


class PromptConformanceTest(unittest.TestCase):
    def test_prompts_are_the_prereg_text_exactly(self):
        doc = prereg_block("PROMPT-DOC (for E8K)")
        news = prereg_block("PROMPT-NEWS (for ENEWS)")
        self.assertEqual(V.USER_DOC.replace("{{", "{").replace("}}", "}"), doc)
        self.assertEqual(V.USER_NEWS.replace("{{", "{").replace("}}", "}"), news)
        text = " ".join(PREREG.read_text(encoding="utf-8").split())
        self.assertIn(f'system: "{V.SYSTEM_DOC}"', text)
        self.assertIn(V.MODEL, text)
        self.assertEqual(V.SYSTEM_NEWS, V.SYSTEM_DOC.replace("a company's SEC filing", "a news headline"))

    def test_prompt_shas_are_stable(self):
        self.assertEqual(len({p.sha for p in V.PROMPTS.values()}), 2)
        self.assertEqual(V.PROMPTS["doc"].sha, V.Prompt("doc", V.SYSTEM_DOC, V.USER_DOC).sha)

    def test_render(self):
        user = V.render_doc(name="GoPro, Inc.", ticker="GPRO", items=["2.02", "9.01"],
                            accepted_at=dt.datetime(2026, 10, 16, 21, 30, 16, tzinfo=UTC), text="Revenue rose.")
        self.assertTrue(user.startswith("Company: GoPro, Inc. (ticker GPRO). SEC Form 8-K, items 2.02, 9.01, accepted "
                                        "2026-10-16 17:30 ET."))
        self.assertIn("<document>\nRevenue rose.\n</document>", user)
        self.assertIn('{"score": an integer from -3', user)


class ParseTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(V.parse_answer('{"score": 2, "guidance": "raised", "reasons": []}', kind="doc"), ("ok", 2, "raised"))
        self.assertEqual(V.parse_answer('```json\n{"score": -1, "reasons": ["a"]}\n```', kind="news"), ("ok", -1, None))
        self.assertEqual(V.parse_answer('{"score": 2, "guidance": "up"}', kind="doc"), ("ok", 2, None))
        for bad in ('{"score": 4}', '{"score": "2"}', '{"score": 2.0}', 'score 2', '[2]', '{"score": true}'):
            self.assertEqual(V.parse_answer(bad, kind="doc")[0], "unparsed", bad)


class FakeGateway:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.last_headers = {}

    def post_json(self, path, body, headers=None):
        self.calls.append((path, body, headers))
        code, payload, cost = self.answers.pop(0)
        self.last_headers = {"x-ltcm-cost-usd": cost} if cost else {}
        return code, payload


def message(text, stop="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop, "model": V.MODEL}


class AskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.clock = lambda: dt.datetime(2026, 10, 19, 13, 0, tzinfo=UTC)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_asks_once_and_replays_the_stored_verdict(self):
        gw = FakeGateway([(200, message('{"score": 3, "guidance": "raised", "reasons": []}'), "0.0041")])
        got = V.ask(self.st, gw, "8k:a", V.PROMPTS["doc"], "user text", now=self.clock)
        self.assertEqual((got["status"], got["score"], got["guidance"]), ("ok", 3, "raised"))
        self.assertAlmostEqual(got["usd"], 0.0041)
        path, body, headers = gw.calls[0]
        self.assertEqual(path, "/v1/claude/messages")
        self.assertEqual((body["model"], body["temperature"], body["max_tokens"]), (V.MODEL, 0, 300))
        self.assertNotIn("thinking", body)
        self.assertEqual(headers["X-LTCM-Request"], f"evl:8k:a:{V.PROMPTS['doc'].sha[:12]}")
        again = V.ask(self.st, gw, "8k:a", V.PROMPTS["doc"], "user text", now=self.clock)
        self.assertEqual(len(gw.calls), 1)
        self.assertEqual(again["score"], 3)

    def test_transient_failures_retry_and_refusals_are_final(self):
        gw = FakeGateway([(502, {"error": "x"}, None), (200, message('{"score": 1, "reasons": []}'), "0.001")])
        self.assertEqual(V.ask(self.st, gw, "news:1", V.PROMPTS["news"], "u", now=self.clock)["status"], "ok")
        gw = FakeGateway([(200, message("", stop="refusal"), "0.0001")])
        self.assertEqual(V.ask(self.st, gw, "news:2", V.PROMPTS["news"], "u", now=self.clock)["status"], "refused")
        # the gateway refusing the call itself (temperature not admitted yet, an unpriced model): nothing stored
        gw = FakeGateway([(400, {"error": "temperature may only be 0"}, None)])
        self.assertIsNone(V.ask(self.st, gw, "news:3", V.PROMPTS["news"], "u", now=self.clock))
        self.assertIsNone(V.stored(self.st, "news:3", V.PROMPTS["news"]))
        self.assertEqual(len(gw.calls), 1)
        gw = FakeGateway([(503, None, None)] * 3)
        self.assertIsNone(V.ask(self.st, gw, "news:4", V.PROMPTS["news"], "u", now=self.clock))
        self.assertEqual(len(gw.calls), 3)
        # a later pass asks again and the first ANSWER is final
        gw = FakeGateway([(200, message('{"score": -2, "reasons": []}'), "0.001")])
        self.assertEqual(V.ask(self.st, gw, "news:4", V.PROMPTS["news"], "u", now=self.clock)["score"], -2)
        gw = FakeGateway([])
        self.assertEqual(V.ask(self.st, gw, "news:4", V.PROMPTS["news"], "u", now=self.clock)["score"], -2)


if __name__ == "__main__":
    unittest.main()
