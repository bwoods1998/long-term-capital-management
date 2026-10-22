"""RELEASE 1019h'S FIX ROUND: THE BIRTHS ARCHITECT'S CALL ON OPUS 5.5 IS STREAMED, AND A LOST CALL IS NEVER ASKED AGAIN
AND IS COUNTED (league/events/births.py `propose`, `STREAM`, `LOST`; league/events/gw.py `post_stream`;
league/events/house.py `LaneGateway.post_stream`, `_births`), on invented data only.

The money and rules reviews of A109 (release 1019h, head 2fd0c096) found the architect's call, Claude Opus 5.5 with its
thinking always on and 6,000 tokens, sent UNSTREAMED through the lane's gateway client, whose read waits 45 s, while the
gateway answers only when Anthropic has finished (gateway/lib/router.mjs `claudeCall` awaits the whole body): a
thinking answer of 1,750-4,500 tokens takes about 22-90 s. On such a night the call timed out, was ASKED AGAIN under the
same request id (the gateway does not refuse a repeated id), ended "no answer", stored nothing and counted $0 in the
night's cap, the lane's line, the budget rule's measure and the site's bill, while Anthropic could bill both
generations; the night finished its receipt "ok", so the House never warned. Held here, each failing on 2fd0c096:

- THE REVIEWER'S PROBE: the real `gw.Gateway` over an opener that times out: one POST, never two; the night's row is
  `lost` at the call's worst case, counted in the night's spend, the lane's line (league/events/house.py `birth_usd`)
  and the site's bill (league/site_lane.py);
- THE CALL IS STREAMED: `stream` true with the thinking summarized (its deltas keep the bytes flowing), every key one the
  gateway admits, the socket's wait `STREAM_GAP` (never the client's 45 s) and the whole answer `CALL_LIMIT`; the
  relayed stream is read to its text and its stop reason, and the gateway's `ltcm.cost` is the stored cost;
- A STREAM LOST AFTER IT BEGAN (it ran past its limit, broke, or Anthropic's stream failed) is `lost`, never asked again,
  at the gateway's stated cost when the gateway read the usage, else the worst case;
- WHAT MAY BE ASKED AGAIN: a request that never reached the gateway (urllib's `URLError`), a 429 and a 5xx the gateway
  settled, their stated costs counted; a 5xx the gateway did not settle is `lost` at the worst case; the gateway's own
  refusal (its `cap`) stores nothing;
- THE HOUSE: the lane's streamed call starts only with its whole limit and one gap left before the task's bound
  (`room`: refused before it goes out, nothing stored); a night whose call ended without an answer finishes its receipt
  `unanswered`, the House warns, and the report reads the last call's status, cost and seconds."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import unittest
import urllib.error
from pathlib import Path

from league.events import births as BI
from league.events import gw as G
from league.events import house as H
from league.events import report as RP
from league.events import store as S
from league.events import verdicts as V
from league.tests import test_events_births as TB
from league.tests import test_events_births_names as BN
from league.tests import test_events_house as TH

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]


# ======================================================================================================== fakes
class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def sse(*events: dict) -> list[bytes]:
    """Server-sent events as the gateway relays them: Anthropic's own, then its `ltcm.cost`."""
    out: list[bytes] = []
    for event in events:
        out += [f"event: {event['type']}\n".encode(), f"data: {json.dumps(event)}\n".encode(), b"\n"]
    return out


def answer_events(text: str, *, stop: str = "end_turn", cost: str | None = "0.061500", known: bool = True,
                  thinking: str = "Counting the uncovered items first.") -> list[bytes]:
    events = [{"type": "message_start", "message": {"id": "msg_1", "model": "claude-opus-5-5", "content": [],
                                                    "usage": {"input_tokens": 9000, "output_tokens": 1}}},
              {"type": "ping"},
              {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
              {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": thinking}},
              {"type": "content_block_stop", "index": 0},
              {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}]
    half = len(text) // 2
    events += [{"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text[:half]}},
               {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": text[half:]}},
               {"type": "content_block_stop", "index": 1},
               {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 2100}},
               {"type": "message_stop"}]
    if cost is not None:
        events.append({"type": "ltcm.cost", "cost_usd": cost, "known": known, "stop": stop})
    return sse(*events)


class Stream:
    """An open stream from the gateway: `lines` read one at a time; `clock`/`step` move a clock with each read; `fail`
    raises at that read (a socket that went quiet: TimeoutError)."""

    def __init__(self, lines, *, status=200, headers=None, clock=None, step=0.0, fail=None, body=None):
        self.lines, self.status, self.clock, self.step, self.fail, self.body = list(lines), status, clock, step, fail, body
        self.headers = headers if headers is not None else {"Content-Type": "text/event-stream; charset=utf-8"}
        self.read_lines = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def readline(self):
        if self.clock is not None:
            self.clock.t += self.step
        if self.fail is not None and self.read_lines >= self.fail:
            raise TimeoutError("timed out")
        self.read_lines += 1
        return self.lines.pop(0) if self.lines else b""

    def read(self):
        return self.body or b""


class Opener:
    """urllib's opener as `gw.Gateway` calls it: each request answered by the next of `answers` (a Stream, an exception
    to raise, or a callable)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list = []

    def __call__(self, req, timeout=None):
        self.requests.append((req, timeout))
        got = self.answers.pop(0)
        if isinstance(got, BaseException):
            raise got
        return got

    def bodies(self) -> list[dict]:
        return [json.loads(req.data) for req, _ in self.requests]


def http_error(code: int, payload: dict, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://gw/v1/claude/messages", code, "no", headers or {},
                                  io.BytesIO(json.dumps(payload).encode()))


class World(unittest.TestCase):
    """test_events_births's `Validation` world (twenty invented sessions to Fri Nov 6, 2026)."""

    AS_OF = TB.Validation.AS_OF
    setUp = TB.Validation.setUp
    candidate = TB.Validation.candidate
    NOW = dt.datetime(2026, 11, 7, 2, 15, tzinfo=UTC)

    def now(self) -> dt.datetime:
        return self.NOW

    def sheet(self) -> dict:
        return BI.Facts(self.s.st, self.AS_OF).facts()

    def worst(self) -> float:
        return BI.worst_usd(BI.render(self.sheet(), BI.budget(self.s.st, self.AS_OF)))

    def gateway(self, opener, clock=None) -> G.Gateway:
        gw = G.Gateway("tok", url="https://gw.invalid", opener=opener)
        if clock is not None:   # the stream's clock (post_stream's `clock`), as the tests move it
            plain = gw.post_stream
            gw.post_stream = lambda *a, **k: plain(*a, **k, clock=clock)
        return gw

    def rows(self) -> list[dict]:
        return [dict(r) for r in self.s.st.db.execute("SELECT * FROM birth_calls ORDER BY night")]

    def specs(self) -> str:
        return json.dumps({"specs": [self.candidate("EVL-B-P1", ["1.02"])]})


# ======================================================================================================== the probe
class TheReviewersProbe(World):
    def test_a_call_that_times_out_is_asked_once_stored_lost_at_its_worst_case_and_counted(self):
        st = self.s.st
        from league import site_lane as SL
        bill = float(SL.verdict_usd(st))       # (the world's verdicts)
        opener = Opener(TimeoutError("timed out"), TimeoutError("timed out"))
        got = BI.propose(st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        worst = self.worst()
        self.assertEqual(len(opener.requests), 1, "a call that went out is never asked twice (the same request id)")
        self.assertEqual((got["status"], got["proposals"], round(got["usd"], 6)), ("lost", [], round(worst, 6)))
        self.assertIn("TimeoutError", got["why"])
        [row] = self.rows()
        self.assertEqual((row["status"], row["model"], row["answer"]), ("lost", BI.MODEL, None))
        self.assertAlmostEqual(row["usd"], worst, places=9, msg="unknown is not free: the call's worst case")
        self.assertAlmostEqual(BI.spent(st, self.AS_OF), worst, places=9, msg="in the night's cap")
        day, (lo, hi) = H.verdict_day(self.NOW)
        self.assertAlmostEqual(H.birth_usd(st.db, lo, hi), worst, places=9, msg="in the lane's line")
        self.assertAlmostEqual(float(SL.verdict_usd(st)) - bill, worst, places=9, msg="in the site's bill")
        again = BI.propose(st, self.gateway(Opener()), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual(again["status"], "stored:lost", "never asked again that night")

    def test_the_socket_waits_the_streams_gap_never_the_clients_45_seconds(self):
        opener = Opener(TimeoutError("timed out"))
        BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        [(req, timeout)] = opener.requests
        self.assertEqual(G.Gateway("t").timeout, 45.0, "the lane's client's own read")
        self.assertEqual(timeout, BI.STREAM_GAP)
        self.assertEqual(req.get_header("Accept"), "text/event-stream")
        self.assertEqual(req.get_header("X-ltcm-request")[:21], "evl-births:2026-11-06")


# ======================================================================================================== the stream
class TheStream(World):
    def test_the_call_is_streamed_with_its_thinking_summarized_and_every_key_the_gateway_admits(self):
        body = BI.request_body("u")
        self.assertIs(body["stream"], True)
        self.assertEqual(body["thinking"], {"type": "adaptive", "display": "summarized"},
                         "summarized: the thinking's deltas keep the bytes flowing (display is never billed)")
        js = (REPO / "gateway" / "lib" / "claude.mjs").read_text(encoding="utf-8")
        [allowed] = re.findall(r"const allowed = new Set\(\[([^\]]*)\]\);", js)
        self.assertLessEqual(set(body), set(re.findall(r"'([a-z_]+)'", allowed)))
        self.assertIn("['omitted', 'summarized'].includes(thinking.display)", js, "the gateway admits the display")
        [ceiling] = re.findall(r"export const MAX_TOKENS_STREAM = (\d+);", js)
        self.assertLessEqual(body["max_tokens"], int(ceiling))
        self.assertNotIn("temperature", body)
        # The stream and the display are how the answer arrives, not what is asked: the prompt's sha stays A109's.
        self.assertEqual(BI.prompt_sha(), "0cae215b0cebb21e9313d392e358c443a4d2caf06554e593f32fbaba8cfe6c21")
        self.assertEqual(BI.PARSE_VERSION, 4)

    def test_a_streamed_answer_is_read_to_its_text_and_the_gateways_cost(self):
        st = self.s.st
        opener = Opener(Stream(answer_events(self.specs())))
        got = BI.propose(st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(got["proposals"]), got["usd"]), ("ok", 1, 0.0615))
        [row] = self.rows()
        self.assertEqual((row["status"], row["answer"], row["usd"]), ("ok", self.specs(), 0.0615),
                         "the text blocks only: the thinking's summary is never the answer")
        [sent] = opener.bodies()
        self.assertEqual((sent["stream"], sent["model"], sent["max_tokens"]), (True, "claude-opus-5-5", 6000))

    def test_an_answer_whose_cost_the_gateway_could_not_read_counts_the_worst_case(self):
        opener = Opener(Stream(answer_events(self.specs(), cost="0.900000", known=False)))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual(got["status"], "ok")
        self.assertAlmostEqual(got["usd"], self.worst(), places=9)

    def test_a_stream_past_its_limit_is_lost_never_asked_again(self):
        clock = Clock()
        lines = answer_events(self.specs())
        opener = Opener(Stream(lines, clock=clock, step=BI.CALL_LIMIT / 10), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener, clock), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests)), ("lost", 1))
        self.assertIn(f"ran past its {BI.CALL_LIMIT:.0f}-second limit", got["why"])
        self.assertAlmostEqual(got["usd"], self.worst(), places=9)

    def test_a_stream_that_went_quiet_is_lost(self):
        opener = Opener(Stream(answer_events(self.specs()), fail=5))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests)), ("lost", 1))
        self.assertIn("went quiet or broke: TimeoutError", got["why"])

    def test_anthropics_failed_stream_counts_the_cost_the_gateway_read(self):
        lines = sse({"type": "message_start", "message": {"id": "m", "usage": {"input_tokens": 9000}}},
                    {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
                    {"type": "ltcm.cost", "cost_usd": "0.031000", "known": True, "stop": "stream_error"})
        opener = Opener(Stream(lines), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], got["usd"], len(opener.requests)), ("lost", 0.031, 1))
        self.assertIn("overloaded_error", got["why"])

    def test_a_whole_answer_stands_when_the_gateways_last_event_is_late(self):
        """After `message_stop` the answer is whole: a quiet socket waiting for the gateway's cost cuts nothing (the
        cost is then the worst case)."""
        lines = answer_events(self.specs(), cost=None)
        opener = Opener(Stream(lines, fail=len(lines)))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(got["proposals"])), ("ok", 1))
        self.assertAlmostEqual(got["usd"], self.worst(), places=9)


# ======================================================================================================== asked again
class WhatMayBeAskedAgain(World):
    def test_a_request_that_never_reached_the_gateway_is_asked_once_more(self):
        opener = Opener(urllib.error.URLError(ConnectionRefusedError("refused")), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests), got["usd"]), ("ok", 2, 0.0615))

    def test_a_5xx_the_gateway_settled_is_asked_once_more_and_its_cost_counted(self):
        opener = Opener(http_error(529, {"type": "error"}, {"X-LTCM-Cost-USD": "0.000400"}),
                        Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests)), ("ok", 2))
        self.assertAlmostEqual(got["usd"], 0.0619, places=9)
        both = Opener(http_error(429, {}, {"X-LTCM-Cost-USD": "0.000000"}),
                      http_error(529, {}, {"X-LTCM-Cost-USD": "0.002000"}))
        self.s.st.db.execute("DELETE FROM birth_calls")
        got = BI.propose(self.s.st, self.gateway(both), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], got["usd"], len(both.requests)), ("lost", 0.002, 2),
                         "a cost the gateway settled with no answer is stored and counted")

    def test_a_second_ask_only_inside_the_nights_cap_with_the_first_asks_cost_counted(self):
        worst = self.worst()
        opener = Opener(http_error(529, {}, {"X-LTCM-Cost-USD": "0.000500"}), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now,
                         cap=worst + 0.0001)
        self.assertEqual((got["status"], got["usd"], len(opener.requests)), ("lost", 0.0005, 1))
        self.assertIn("no second ask", got["why"])
        self.s.st.db.execute("DELETE FROM birth_calls")
        line = Opener(http_error(529, {}, {"X-LTCM-Cost-USD": "0.000500"}), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(line), self.sheet(), night=self.AS_OF, now=self.now,
                         line_left=worst + 0.0001)
        self.assertEqual((got["status"], len(line.requests)), ("lost", 1), "nor past the lane's line")

    def test_a_5xx_the_gateway_did_not_settle_is_lost_at_the_worst_case(self):
        opener = Opener(http_error(502, {"error": "bad gateway"}), Stream(answer_events(self.specs())))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests)), ("lost", 1))
        self.assertAlmostEqual(got["usd"], self.worst(), places=9)
        self.s.st.db.execute("DELETE FROM birth_calls")
        cut = Opener(http_error(502, {"error": "cut off"}, {"X-LTCM-Cost-USD": "0.700000", "X-LTCM-Cost-Known": "false"}))
        got = BI.propose(self.s.st, self.gateway(cut), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual(got["status"], "lost", "a body cut off: the gateway kept its hold, the cost unknown")
        self.assertAlmostEqual(got["usd"], self.worst(), places=9)

    def test_the_gateways_own_refusal_stores_nothing(self):
        opener = Opener(http_error(402, {"error": "over", "cap": "claude_funded"}),
                        http_error(503, {"error": "not configured", "cap": "setup"}))
        got = BI.propose(self.s.st, self.gateway(opener), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(opener.requests), self.rows()), ("no answer", 1, []))
        setup = Opener(http_error(503, {"error": "not configured", "cap": "setup"}),
                       http_error(503, {"error": "not configured", "cap": "setup"}))
        got = BI.propose(self.s.st, self.gateway(setup), self.sheet(), night=self.AS_OF, now=self.now)
        self.assertEqual((got["status"], len(setup.requests), self.rows()), ("no answer", 2, []))


# ======================================================================================================== the night
class TheNight(World):
    def test_a_lost_night_finishes_its_receipt_unanswered_with_its_cost_and_seconds(self):
        st = self.s.st
        ticks = iter([self.NOW + dt.timedelta(seconds=s) for s in range(0, 600, 1)])
        out = BI.night(st, self.gateway(Opener(TimeoutError("timed out"))), today=self.AS_OF, now=lambda: next(ticks))
        self.assertEqual(out["_status"], "unanswered")
        self.assertEqual(out["call"]["status"], "lost")
        self.assertGreater(out["call"]["seconds"], 0)
        self.assertAlmostEqual(out["call"]["usd"], self.worst(), places=9)
        [receipt] = [dict(r) for r in st.db.execute("SELECT status, summary FROM receipts WHERE job='births'")]
        self.assertEqual(receipt["status"], "unanswered")
        last = BI.summary(st)["last_call"]
        self.assertEqual((last["night"], last["status"], last["usd"]), ("2026-11-06", "lost", round(self.worst(), 4)))
        self.assertGreater(last["seconds"], 0)

    def test_an_answered_night_finishes_ok(self):
        out = BI.night(self.s.st, self.gateway(Opener(Stream(answer_events(self.specs())))), today=self.AS_OF,
                       now=self.now, dry_run=True)
        self.assertEqual((out["_status"], out["call"]["status"]), ("ok", "ok"))


# ======================================================================================================== the House
class LostGateway(BN.BirthsGateway):
    """The House's fake gateway whose births call (streamed) is lost while waiting for its answer."""

    def post_stream(self, path, body, headers=None, *, limit, gap=None):
        if isinstance(body, dict) and body.get("system") == BI.SYSTEM:
            self.claude_calls.append(body)
            self.stream_args = (limit, gap)
            raise TimeoutError("timed out")
        return super().post_stream(path, body, headers, limit=limit, gap=gap)


class TheHouse(TH.LaneCase):
    """Tue Oct 20, 2026 in the House's lane harness: Monday night's births re-run (A95) the next morning
    (test_events_births_names `TheHousesRerun`'s world), its call lost."""

    turns = BN.TheHousesRerun.turns
    births_calls = BN.TheHousesRerun.births_calls

    def setUp(self):
        super().setUp()
        self.addCleanup(TB.unload)
        self.gw = LostGateway()
        with self.store() as st:
            self.first = BN.old_receipt(st, night=dt.date(2026, 10, 19), at=TH.et("2026-10-19", "21:16"))

    def test_a_lost_call_is_asked_once_the_receipt_unanswered_the_house_warns_and_the_line_counts_it(self):
        self.lane = self.new_lane(births=True)
        self.assertEqual(self.turns("07:05", "07:06", "07:20")[0], "births")
        self.assertEqual(len(self.births_calls()), 1, "never asked twice")
        self.assertEqual(self.gw.stream_args, (BI.CALL_LIMIT, BI.STREAM_GAP))
        summary = json.loads(self.receipts("births")[-1]["summary"])
        self.assertEqual((self.receipts("births")[-1]["status"], summary["call"]["status"]), ("unanswered", "lost"))
        warned = [text for level, text in self.house.alerts if level == "warning" and "births" in text]
        self.assertTrue(warned and "ended unanswered" in warned[0] and "ended lost" in warned[0], self.house.alerts)
        with self.store() as st:
            [row] = [dict(r) for r in st.db.execute("SELECT status, usd FROM birth_calls")]
            self.assertEqual(row["status"], "lost")
            self.assertGreater(row["usd"], 0.13, "at the call's worst case (its 6,000 tokens out alone are $0.132)")
            self.lane._spend_today(st, self.clock_dt())
            text = RP.render(RP.build(st, dt.date(2026, 10, 20), now=self.clock_dt()))
        self.assertGreaterEqual(self.lane._usd["usd"], row["usd"], "the lane's line counts it")
        self.assertRegex(text, r"Births: .*; last call 2026-10-19 lost \$0\.1\d{3} in \d+\.\d s")

    def test_the_streamed_call_starts_only_with_its_limit_and_a_gap_left_before_the_bound(self):
        lane = self.new_lane(births=True)
        with self.store() as st:
            lane._spend_today(st, self.clock_dt())
        lane._line = {"usd_day": 5.0, "source": "test"}
        short = H.LaneGateway(self.gw, lane, self.mono() + BI.CALL_LIMIT + BI.STREAM_GAP - 1, cut=True)
        with self.assertRaises(H.LaneCut) as cut:
            short.post_stream(V.PATH, {"system": BI.SYSTEM}, limit=BI.CALL_LIMIT, gap=BI.STREAM_GAP)
        self.assertIsInstance(cut.exception, G.NotSent, "refused before it went out")
        self.assertEqual((str(cut.exception), dict(short.counts), self.births_calls()), ("room", {"cut_room": 1}, []))
        room = H.LaneGateway(self.gw, lane, self.mono() + BI.CALL_LIMIT + BI.STREAM_GAP + 1, cut=True)
        with self.assertRaises(TimeoutError):
            room.post_stream(V.PATH, {"system": BI.SYSTEM}, limit=BI.CALL_LIMIT, gap=BI.STREAM_GAP)
        self.assertEqual(dict(room.counts), {"asked": 1, "failed": 1})
        self.assertGreater(H.BIRTHS_BUDGET, BI.CALL_LIMIT + BI.STREAM_GAP, "the births job's bound holds the call")

    def test_a_call_the_lane_refused_stores_nothing_and_is_not_asked(self):
        with self.store() as st:
            self.addCleanup(TB.unload)
            sheet = {"as_of": "2026-10-19"}
            lane = self.new_lane(births=True)
            lane._spend_today(st, self.clock_dt())
            lane._line = {"usd_day": 5.0, "source": "test"}
            gw = H.LaneGateway(self.gw, lane, self.mono() + 10, cut=True)
            got = BI.propose(st, gw, sheet, night=dt.date(2026, 10, 19), now=self.clock_dt)
            self.assertEqual((got["status"], got["why"]), ("no answer", "LaneCut: room"))
            self.assertIsNone(st.db.execute("SELECT 1 FROM birth_calls").fetchone())
        self.assertEqual(self.births_calls(), [])


if __name__ == "__main__":
    unittest.main()
