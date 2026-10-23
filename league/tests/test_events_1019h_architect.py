"""RELEASE 1019h, THE BIRTHS ARCHITECT ON CLAUDE OPUS 5.5 (the captain's A109, 06:05Z Oct 22, 2026; league/events/births.py
`MODEL`, `PRICES`, `request_body`, `worst_usd`, `propose`), on invented data only.

A109: the Oct 21 night's re-run (receipt 3068) accepted none; besides the rate's denominator (SUP-3), the architect,
Haiku 4.5, proposed narrow rules and duplicates. From release 1019h the births architect is claude-opus-5-5, in the
gateway's CLAUDE_MODELS allowlist at $4 input and $20 output a million tokens; the verdict reader stays Haiku 4.5.
Held here, each failing on release 1019h's minors (`fix/1019h-minors` 8e83ad1b, whose architect is Haiku 4.5):

- the architect is Opus 5.5 and the verdict reader Haiku 4.5, each in the gateway's allowlist;
- THE WORST CASE AT THE MODEL'S OWN PRICES: `PRICES` is the gateway's row of the model (gateway/wrangler.jsonc
  CLAUDE_MODELS: input, output and the geography multipliers), priced at its dearest geography as the gateway reserves;
  the night's cap ($0.25) and the lane's line hold the call to that worst case (a cap or a line between Haiku's worst
  case and Opus's refuses the call, which release 1019h's minors made); the fullest night the facts can describe fits
  the cap;
- THE CALL'S FORM: Opus 5.5 takes no sampling parameter (`temperature` is Anthropic's 400, and a 4xx is never asked
  again) and always thinks, its thinking inside `max_tokens`: the body carries no temperature, effort "low" and 6000
  tokens, every key one the gateway admits (from the fix round, streamed with its thinking summarized:
  test_events_1019h_births_stream); an answer cut at `max_tokens` is stored `cut`, never parsed, never asked again;
- THE PROMPT'S SHA AND `PARSE_VERSION` MOVE (the model, the temperature, the effort and `max_tokens` are in the sha's
  spec): 4 and `0cae215b`; a night's answer stored under the minors' prompt (`890806ff`, Haiku) is never read by this
  code, and a night whose receipts are at version 3 is due its one re-run (A95) before its cut-off."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import unittest
from pathlib import Path

from league.events import births as BI
from league.events import programs as P
from league.events import verdicts as V
from league.tests import test_events_births as TB

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]
#: The minors' architect, for the comparisons (release 1019e to the minors: Haiku 4.5 at $1 and $5, 3000 tokens).
HAIKU = "claude-haiku-4-5-20251001"
PROMPT_MINORS = "890806ff38f09b7e810cbbfef1159ca85f39d568105537d8eca4d7e60c022b06"
PROMPT_1019H = "0cae215b0cebb21e9313d392e358c443a4d2caf06554e593f32fbaba8cfe6c21"
#: (release 1019i: the prompt tells PREREG-EVL-6's restated charge, so its sha moved again with PARSE_VERSION 5)
PROMPT_1019I = "1442a2a23637e66158ad01b072b2df85f4c6d9fa60b2d7640c8ff98226a6914e"


def gateway_models() -> dict:
    """The gateway's CLAUDE_MODELS (gateway/wrangler.jsonc, read as text: the var set once), the price table and the
    allowlist, dollars a million tokens."""
    text = (REPO / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
    [raw] = re.findall(r'"CLAUDE_MODELS":\s*("(?:[^"\\]|\\.)*")', text)
    return json.loads(json.loads(raw))


def gateway_claude() -> str:
    return (REPO / "gateway" / "lib" / "claude.mjs").read_text(encoding="utf-8")


def haiku_worst(user: str) -> float:
    """The minors' worst case of the same call (Haiku 4.5's $1 and $5, 3000 tokens out)."""
    return math.ceil((len(BI.SYSTEM) + len(user)) / BI.CHARS_A_TOKEN) * 1.0e-6 + 3000 * 5.0e-6


class Cut(TB.FakeArchitect):
    """The gateway answering with a stop reason (`stop`): `max_tokens`, an answer cut short."""

    def __init__(self, answer: str, *, stop: str, **kw):
        super().__init__(answer, **kw)
        self.stop = stop

    def post_json(self, path, body, headers=None):
        code, payload = super().post_json(path, body, headers)
        if path == V.PATH and code == 200:
            payload = dict(payload, stop_reason=self.stop)
        return code, payload


# ======================================================================================================== the model
class TheArchitect(unittest.TestCase):
    def test_the_architect_is_opus_5_5_and_the_verdict_reader_stays_haiku_both_in_the_allowlist(self):
        self.assertEqual(BI.MODEL, "claude-opus-5-5", "A109")
        self.assertEqual(V.MODEL, HAIKU, "the verdict reader stays Haiku 4.5")
        models = gateway_models()
        self.assertIn(BI.MODEL, models, "a model absent from CLAUDE_MODELS is the gateway's 403")
        self.assertIn(V.MODEL, models)
        self.assertEqual(BI.request_body("u")["model"], BI.MODEL)
        self.assertEqual(BI.parse_answer(json.dumps({"specs": [{"spec": {"id": "EVL-B-X"}, "why": "w"}]}))[0][0]["by"],
                         "architect:claude-opus-5-5")

    def test_the_prices_are_the_gateways_row_of_the_model_at_its_dearest_geography(self):
        row = gateway_models()[BI.MODEL]
        self.assertEqual((row["input"], row["output"]), (4, 20), "A109: $4 input and $20 output a million tokens")
        self.assertEqual((BI.PRICES["input"], BI.PRICES["output"], BI.PRICES["geo"]),
                         (row["input"], row["output"], row.get("geo") or {}), "births.py's prices are the gateway's row")
        # The gateway settles at the geography Anthropic reports and reserves at the dearest (gateway/lib/claude.mjs
        # `dearestGeo`); the worst case prices every token there too: $4.40 and $22 (US-only at 1.1x).
        self.assertIn("const dearestGeo = price => Math.max(1, ...Object.values(price.geo || {}));", gateway_claude())
        self.assertEqual(BI.GEO_MAX, max([1.0, *(row.get("geo") or {}).values()]))
        self.assertEqual(BI.GEO_MAX, 1.1)
        self.assertAlmostEqual(BI.PRICE_IN * 1e6, 4.4, places=9)
        self.assertAlmostEqual(BI.PRICE_OUT * 1e6, 22.0, places=9)
        # Never under what league/claude.py's own hold for the model assumes for an uncached input and the output.
        from league.claude import MODEL_CEILINGS
        _, out = MODEL_CEILINGS[BI.MODEL]
        self.assertAlmostEqual(BI.PRICE_OUT * 1e6, float(out), places=9)

    def test_the_worst_case_is_the_whole_max_tokens_and_the_prompt_at_the_models_prices(self):
        user = "x" * 30_000
        tokens_in = math.ceil((len(BI.SYSTEM) + len(user)) / BI.CHARS_A_TOKEN)
        self.assertAlmostEqual(BI.worst_usd(user), tokens_in * 4.4e-6 + 6000 * 22e-6, places=12)
        self.assertGreater(BI.worst_usd(user), 3 * haiku_worst(user), "the minors' Haiku prices undercount it")


# ======================================================================================================== the call
class TheCall(unittest.TestCase):
    """test_events_births's `Validation` world (twenty invented sessions to Fri Nov 6, 2026), its tests left there."""

    AS_OF = TB.Validation.AS_OF
    setUp = TB.Validation.setUp
    candidate = TB.Validation.candidate
    NOW = dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC)

    def now(self) -> dt.datetime:
        return self.NOW

    def sheet(self) -> dict:
        return BI.Facts(self.s.st, self.AS_OF).facts()

    def test_no_temperature_effort_low_6000_tokens_and_every_key_the_gateway_admits(self):
        st = self.s.st
        answer = json.dumps({"specs": [self.candidate("EVL-B-P1", ["1.02"])]})
        gw = TB.FakeArchitect(answer)
        got = BI.propose(st, gw, self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(got["proposals"])), ("ok", 1))
        [(path, body, _)] = gw.calls
        self.assertEqual(path, V.PATH)
        self.assertNotIn("temperature", body, "Opus 5.5 answers any temperature with Anthropic's 400")
        self.assertEqual((body["model"], body["output_config"], body["max_tokens"]),
                         ("claude-opus-5-5", {"effort": "low"}, 6000))
        # (release 1019h's fix round: the call is STREAMED, its adaptive thinking summarized so its deltas keep the
        # bytes flowing; test_events_1019h_births_stream holds the stream)
        self.assertEqual(body["thinking"], {"type": "adaptive", "display": "summarized"},
                         "Opus 5.5 always thinks (adaptive); effort is the control, the display only what is shown")
        js = gateway_claude()
        [allowed] = re.findall(r"const allowed = new Set\(\[([^\]]*)\]\);", js)
        admitted = set(re.findall(r"'([a-z_]+)'", allowed))
        self.assertLessEqual(set(body), admitted, "every key one the gateway admits")
        [ceiling] = re.findall(r"export const MAX_TOKENS = (\d+);", js)
        self.assertLessEqual(body["max_tokens"], int(ceiling), "inside the gateway's unstreamed ceiling too")
        [efforts] = re.findall(r"export const EFFORTS = \[([^\]]*)\];", js)
        self.assertIn("'low'", efforts)
        self.assertIs(body["stream"], True, "streamed: the lane's client reads the relayed events")

    def test_the_nights_cap_holds_the_call_to_opus_prices(self):
        st = self.s.st
        sheet = self.sheet()
        user = BI.render(sheet, BI.budget(st, self.AS_OF))
        worst, cheap = BI.worst_usd(user), haiku_worst(user)
        self.assertLess(cheap, worst)
        gw = TB.FakeArchitect("{}")
        capped = BI.propose(st, gw, sheet, night=self.AS_OF, now=self.now, cap=(cheap + worst) / 2)
        self.assertEqual((capped["status"], gw.calls), ("cap", []),
                         "a cap the minors' Haiku worst case fit under refuses the Opus call")
        self.assertIn(f"${worst:.4f}", capped["why"])
        made = BI.propose(st, gw, sheet, night=self.AS_OF, now=self.now, cap=worst + 0.0001)
        self.assertEqual((made["status"], len(gw.calls)), ("ok", 1))

    def test_the_lanes_line_holds_the_call_to_opus_prices(self):
        st = self.s.st
        sheet = self.sheet()
        user = BI.render(sheet, BI.budget(st, self.AS_OF))
        worst, cheap = BI.worst_usd(user), haiku_worst(user)
        gw = TB.FakeArchitect("{}")
        got = BI.propose(st, gw, sheet, night=self.AS_OF, now=self.now, line_left=(cheap + worst) / 2)
        self.assertEqual((got["status"], gw.calls), ("cap", []))
        self.assertIn("left of the lane's line today", got["why"])

    def test_an_answer_cut_at_max_tokens_is_stored_cut_never_parsed_never_asked_again(self):
        st = self.s.st
        answer = json.dumps({"specs": [self.candidate("EVL-B-P1", ["1.02"])]})
        gw = Cut(answer, stop="max_tokens", cost="0.1300")
        got = BI.propose(st, gw, self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], got["proposals"], got["offered"], got["usd"]), ("cut", [], 0, 0.13))
        row = dict(st.db.execute("SELECT status, usd, model FROM birth_calls").fetchone())
        self.assertEqual(row, {"status": "cut", "usd": 0.13, "model": "claude-opus-5-5"}, "its cost stays counted")
        again = BI.propose(st, gw, self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((again["status"], again["proposals"], len(gw.calls)), ("stored:cut", [], 1))
        self.assertAlmostEqual(BI.spent(st, self.AS_OF), 0.13)

    def test_a_night_stored_under_the_minors_prompt_is_asked_again_under_the_new_one(self):
        """`birth_calls` is keyed by night, prompt sha and model: the minors' Haiku answer (prompt `890806ff`) is never
        read by this code; the night's call is made inside what the night has left (the old answer's cost counts)."""
        st = self.s.st
        with st.tx() as db:
            db.execute("INSERT INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, status, "
                       "user_sha, facts_sha, answer, usd) VALUES(?, ?, ?, 'r', 'x', 'x', 'ok', 'u', 'f', ?, 0.0080)",
                       (self.AS_OF.isoformat(), PROMPT_MINORS, HAIKU, json.dumps({"specs": []})))
        gw = TB.FakeArchitect(json.dumps({"specs": [self.candidate("EVL-B-P1", ["1.02"])]}))
        got = BI.propose(st, gw, self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(gw.calls), got["prompt_sha"]), ("ok", 1, PROMPT_1019I))
        self.assertEqual(st.db.execute("SELECT COUNT(*) FROM birth_calls").fetchone()[0], 2)
        tight = TB.FakeArchitect("{}")
        st.db.execute("DELETE FROM birth_calls WHERE model=?", (BI.MODEL,))
        user = BI.render(self.sheet(), BI.budget(st, self.AS_OF))
        held = BI.propose(st, tight, self.sheet(), night=self.AS_OF, now=self.now,
                          cap=0.0080 + BI.worst_usd(user) - 0.0001)
        self.assertEqual((held["status"], tight.calls), ("cap", []), "the night's first call counts in its cap")


# ======================================================================================================== the full night
class TheFullestNight(unittest.TestCase):
    """The largest prompt the facts can make: every 8-K item, the fifteen news sources at the longest name the grammar
    takes, every hour of the three hour tables, every score of every family, every guidance, every PREREG program and
    forty more births at the longest id, every count five digits: its worst case at Opus 5.5's prices fits the night's
    $0.25 (the cap would otherwise refuse every call, and the night would propose nothing)."""

    def test_its_worst_case_fits_the_nights_cap(self):
        big = 99_999
        programs = [{"id": p.id, "family": p.family, "seatable": True, "birth": False, "selected": big,
                     "per_session": 9999.99, "per_recorded_session": 9999.99} for p in P.PROGRAMS]
        programs += [{"id": ("EVL-B-" + "X" * 40)[:BI.ID_MAX - 3] + f"{i:03d}", "family": "news-react",
                      "seatable": True, "birth": True, "selected": big, "per_session": 9999.99,
                      "per_recorded_session": 9999.99} for i in range(40)]
        fam = {"events": big, "eligible": big, "per_session": 9999.99, "per_recorded_session": 9999.99}
        facts = {
            "as_of": "2026-11-06", "sessions": 20, "first": "2026-10-12", "last": "2026-11-06", "recorded_sessions": 20,
            "families": {f: dict(fam) for f in BI.FAMILIES}, "forms": {"8-K": big, "4-buys": big},
            "items_8k": {i: big for i in BI.ITEMS_8K + ("2.02",)},
            "news_sources": {f"{chr(97 + k)}" * 32: big for k in range(15)},
            "hours": {k: {str(h): big for h in range(24)} for k in ("8k", "news", "news-day")},
            "scores": {f: {str(s): big for s in range(-3, 4)} for f in BI.FAMILIES},
            "guidance_ern": {g: big for g in ("lowered", "maintained", "none", "raised", "unclear")},
            "ins_buy": {"value": {"50k-100k": big, "100k-250k": big, "250k-1m": big, "1m+": big},
                        "roles": {"director": big, "officer": big, "both": big}},
            "programs": programs,
            "unprogrammed": {"families": list(BI.FAMILIES), "items_8k": list(BI.ITEMS_8K)},
            "react_counts": "upper bounds: a reaction is a price after the event, never read here (so the rate floor "
                            "barely binds a react rule)",
        }
        user = BI.render(facts, {"used": 3.0, "limit": 3.0, "seatable_left_tonight": 3})
        worst = BI.worst_usd(user)
        self.assertLess(worst, BI.NIGHT_USD, f"{len(user)} characters: worst case ${worst:.4f}")
        self.assertLess(worst, 0.25 - 0.03, "room left for a re-run night's first call (about $0.03 at Opus prices)")

    def test_the_night_cap_and_the_line_are_unchanged(self):
        self.assertEqual(BI.NIGHT_USD, 0.25)
        self.assertEqual(BI.K, 6)


# ======================================================================================================== the version
class TheVersion(unittest.TestCase):
    def test_the_model_is_in_the_shas_spec_so_the_sha_and_the_parse_version_moved(self):
        self.assertEqual((BI.PARSE_VERSION, BI.prompt_sha()), (5, PROMPT_1019I), "release 1019i's restated charge")
        from unittest import mock
        with mock.patch.object(BI, "MODEL", HAIKU):
            self.assertNotEqual(BI.prompt_sha(), PROMPT_1019I, "the model alone moves the sha")
        with mock.patch.object(BI, "EFFORT", "medium"):
            self.assertNotEqual(BI.prompt_sha(), PROMPT_1019I, "so does the effort")

    def test_a_night_read_at_version_3_is_due_its_one_rerun_before_its_cutoff(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(TB.unload)
        st = TB.Synth(Path(tmp.name)).st
        self.addCleanup(st.close)
        night = dt.date(2026, 10, 22)
        rid = st.start_receipt(BI.JOB, now=dt.datetime(2026, 10, 23, 1, 15, tzinfo=UTC))
        st.finish_receipt(rid, "ok", {"night": night.isoformat(), "parse_version": 3, "accepted": []},
                          now=dt.datetime(2026, 10, 23, 1, 16, tzinfo=UTC))
        due = BI.rerun_due(st, dt.datetime(2026, 10, 23, 12, 0, tzinfo=UTC))
        self.assertEqual((due["night"], due["parse_version"], due["until"]),
                         ("2026-10-22", 3, "2026-10-23T12:55:00Z"))
        self.assertIsNone(BI.rerun_due(st, dt.datetime(2026, 10, 23, 12, 55, tzinfo=UTC)), "never from 12:55Z")
        self.assertIsNone(BI.rerun_due(st, dt.datetime(2026, 10, 23, 12, 0, tzinfo=UTC), version=3),
                          "the minors' reading (3) would not re-run it")


if __name__ == "__main__":
    unittest.main()
