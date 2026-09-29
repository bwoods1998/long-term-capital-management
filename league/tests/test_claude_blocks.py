"""`league.claude` system blocks (Sept 29, 2026): a list of system blocks with their own cache markers (the graveyard digest
ahead of a role's own text), checked against Anthropic's rules before anything is sent
(platform.claude.com/docs/en/build-with-claude/prompt-caching: at most 4 breakpoints; a 1-hour entry before any 5-minute
one), the 1-hour marker only when the gateway admits it, its hold priced at the 1-hour write rate, and a string system
prompt's body byte-identical to what it has always been."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from league.claude import (HOUR_WRITE_FACTOR, MAX_TOKENS_STREAM, MODEL_CEILINGS, ClaudeError, request_body, reservation_ceiling,
                           system_blocks)
from league.tests.test_claude import client, message
from league.tests.test_frontier import FakeOpener

TURN = [{"role": "user", "content": "the packet"}]


class StringSystemIsUnchanged(unittest.TestCase):
    """The golden bodies: exactly what origin/main (6c2de074, #415) built for a string system prompt, byte for byte."""

    GOLDEN = {
        "plain": '{"model": "claude-opus-5-5", "max_tokens": 16000, "system": [{"type": "text", "text": "THE RULES", '
                 '"cache_control": {"type": "ephemeral"}}], "messages": [{"role": "user", "content": "the packet"}], '
                 '"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}',
        "uncached_stream": '{"model": "claude-sonnet-5-5", "max_tokens": 32000, "stream": true, "system": [{"type": "text", '
                           '"text": "THE RULES"}], "messages": [{"role": "user", "content": "the packet"}], "thinking": '
                           '{"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "medium"}}',
        "schema_no_system": '{"model": "claude-opus-5-5", "max_tokens": 16000, "messages": [{"role": "user", "content": '
                            '"the packet"}], "thinking": {"type": "adaptive"}, "output_config": {"effort": "high", '
                            '"format": {"type": "json_schema", "schema": {"type": "object"}}}}',
    }

    def test_a_string_system_prompt_gives_the_same_bytes_as_before(self):
        bodies = {
            "plain": request_body("claude-opus-5-5", "THE RULES", TURN),
            "uncached_stream": request_body("claude-sonnet-5-5", "THE RULES", TURN, max_tokens=10 ** 6, effort="medium",
                                            cache=False, stream=True),
            "schema_no_system": request_body("claude-opus-5-5", "", TURN, schema={"type": "object"}),
        }
        for name, body in bodies.items():
            self.assertEqual(json.dumps(body), self.GOLDEN[name], name)
        self.assertEqual(bodies["uncached_stream"]["max_tokens"], MAX_TOKENS_STREAM)

    def test_the_ceiling_of_a_string_body_is_unchanged(self):
        body = request_body("claude-sonnet-5-5", "rules " * 3000, TURN, max_tokens=32000, stream=True)
        size = len(json.dumps(body).encode("utf-8"))
        worst = (Decimal(size + 4096) * Decimal("2.50") + 32000 * Decimal("10")) / 10 ** 6
        self.assertGreaterEqual(reservation_ceiling(body), worst)
        self.assertLess(reservation_ceiling(body) - worst, Decimal("0.00001"))


class Blocks(unittest.TestCase):
    def test_blocks_keep_their_order_and_their_own_markers(self):
        blocks = system_blocks([{"text": "DIGEST", "cache": "5m"}, {"text": "TAIL", "cache": None}, {"text": "ROLE"}], cache=True)
        self.assertEqual(blocks, [{"type": "text", "text": "DIGEST", "cache_control": {"type": "ephemeral"}},
                                  {"type": "text", "text": "TAIL"}, {"type": "text", "text": "ROLE"}])
        hour = system_blocks([{"text": "DIGEST", "cache": "1h"}, {"text": "ROLE", "cache": "5m"}], allow_hour=True)
        self.assertEqual([b.get("cache_control") for b in hour], [{"type": "ephemeral", "ttl": "1h"}, {"type": "ephemeral"}],
                         "a 1-hour entry before a 5-minute one is Anthropic's order")
        self.assertEqual(system_blocks([{"text": "D", "cache": "5m"}], cache=False), [{"type": "text", "text": "D"}],
                         "cache off sends no marker")

    def test_what_anthropic_or_the_gateway_would_refuse_is_refused_before_sending(self):
        bad = {
            "1h after 5m": ([{"text": "a", "cache": "5m"}, {"text": "b", "cache": "1h"}], True),
            "1h not admitted": ([{"text": "a", "cache": "1h"}], False),
            "five markers": ([{"text": str(i), "cache": "5m"} for i in range(5)], False),
            "seventeen blocks": ([{"text": str(i)} for i in range(17)], False),
            "no blocks": ([], False),
            "empty text": ([{"text": "", "cache": None}], False),
            "not text": ([{"text": 3}], False),
            "unknown ttl": ([{"text": "a", "cache": "10m"}], False),
            "unknown key": ([{"text": "a", "cache_control": {"type": "ephemeral"}}], False),
            "a mapping": ({"text": "a"}, False),
        }
        for name, (given, hour) in bad.items():
            with self.assertRaises(ClaudeError, msg=name):
                system_blocks(given, allow_hour=hour)
        self.assertEqual(len(system_blocks([{"text": str(i), "cache": "5m"} for i in range(4)])), 4, "four markers are allowed")

    def test_a_one_hour_body_is_held_at_the_one_hour_write_rate(self):
        self.assertEqual(HOUR_WRITE_FACTOR, Decimal("2") / Decimal("1.25"), "2x base input over 1.25x (the pricing page)")
        system = [{"text": "digest " * 4000, "cache": "1h"}, {"text": "rules"}]
        hour = request_body("claude-sonnet-5-5", system, TURN, max_tokens=1000, allow_hour=True)
        five = request_body("claude-sonnet-5-5", [{"text": "digest " * 4000, "cache": "5m"}, {"text": "rules"}], TURN, max_tokens=1000)
        write, output = MODEL_CEILINGS["claude-sonnet-5-5"]
        size = len(json.dumps(hour).encode("utf-8"))
        worst = (Decimal(size + 4096) * write * HOUR_WRITE_FACTOR + 1000 * output) / 10 ** 6
        self.assertGreaterEqual(reservation_ceiling(hour), worst)
        self.assertLess(reservation_ceiling(hour) - worst, Decimal("0.00001"))
        self.assertEqual(write * HOUR_WRITE_FACTOR, Decimal("4.000"), "Sonnet 5.5's 1-hour write: $4 a million")
        self.assertLess(reservation_ceiling(five), reservation_ceiling(hour))

    def test_the_client_sends_the_blocks_and_refuses_an_hour_it_was_not_allowed(self):
        opener = FakeOpener(message("{}"))
        client(opener).ask([{"text": "DIGEST", "cache": "5m"}, {"text": "TAIL"}, {"text": "RULES"}], "q", agent="swarm-architect")
        self.assertEqual(opener.body()["system"], [{"type": "text", "text": "DIGEST", "cache_control": {"type": "ephemeral"}},
                                                   {"type": "text", "text": "TAIL"}, {"type": "text", "text": "RULES"}])
        self.assertEqual(opener.body()["messages"], [{"role": "user", "content": "q"}], "turns stay plain strings")
        quiet = FakeOpener()
        with self.assertRaises(ClaudeError):
            client(quiet).ask([{"text": "DIGEST", "cache": "1h"}], "q", agent="a")
        self.assertEqual(quiet.calls, [], "refused before any request: today's gateway answers a 1-hour marker with a 400")


if __name__ == "__main__":
    unittest.main()
