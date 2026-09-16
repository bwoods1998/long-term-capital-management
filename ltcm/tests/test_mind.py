"""The Firm Mind: rules scored on every desk's outcomes, admitted on evidence, retired in code."""

import importlib.util
import io
import json
import math
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm import mind as mind_module
from ltcm.events import EventLog, canonical
from ltcm.publish import shape_problem
from ltcm.mind import (
    FirmMind,
    MindError,
    aggregate,
    applies,
    bootstrap_ci,
    evaluate,
    evidence_text,
    matches,
    parse_outcome,
    parse_reply,
    render_rules,
    rules_for_family,
    validate_filter,
    validate_rule,
    verdict,
)
from ltcm.tests.test_desk import DeskCase, FakeProvider as DeskProvider, provider_response, tool_call
from ltcm.tests.test_lab import NIGHT, LabCase, manifest as lab_manifest
from ltcm.tests.test_service import DESK, ServiceCase, moment

T0 = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


def stamp(i):
    return (T0 + timedelta(minutes=17 * i)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def kalshi_payload(ticker, *, leg="no", entry="0.90", quantity="10", won=True, pnl=None, held="6.0", real=False, strategy=None):
    entry_d, qty = Decimal(entry), Decimal(quantity)
    if pnl is None:
        pnl = ((1 - entry_d) if won else -entry_d) * qty
    result = leg if won else ("yes" if leg == "no" else "no")
    return {
        "instrument": f"event:{ticker}:kalshi:{leg}:{ticker}",
        "market_id": ticker,
        "result": result,
        "entry_price": entry,
        "exit_price": "1" if won else "0",
        "quantity": quantity,
        "pnl": str(pnl),
        "held_for_hours": held,
        "rationale_excerpt": (f"[strategy {strategy}] " if strategy else "") + "the forecast disagrees with the book",
        "real_money": real,
    }


def spot_payload(*, entry="60000", exit_price="60600", quantity="0.0004", real=True, strategy="momentum"):
    pnl = (Decimal(exit_price) - Decimal(entry)) * Decimal(quantity)
    return {
        "instrument": "crypto:BTC-USD:coinbase",
        "market_id": "BTC-USD",
        "result": "sold",
        "entry_price": entry,
        "exit_price": exit_price,
        "quantity": quantity,
        "pnl": str(pnl),
        "held_for_hours": "3.5",
        "rationale_excerpt": f"[strategy {strategy}] breakout",
        "real_money": real,
    }


def event(desk, payload, i=0):
    return SimpleNamespace(stream=f"desk:{desk}", payload=payload, seq=i + 1, at=stamp(i))


class Tape:
    """Writes synthetic `desk.outcome` events the way the gateway does."""

    def __init__(self, log):
        self.log = log
        self.i = 0

    def add(self, desk, payload):
        self.i += 1
        return self.log.append(f"desk:{desk}", "desk.outcome", payload, id=f"outcome:{desk}:{self.i}", at=stamp(self.i))

    def weather_losers(self, count=20, losses=8, desk="haghani", ticker="KXHIGHNY-26SEP{:02d}-B81.5"):
        """NO legs bought at 92 cents on the NYC high that lose often: an avoid rule."""
        for k in range(count):
            self.add(desk, kalshi_payload(ticker.format(k % 28 + 1), leg="no", entry="0.92", won=k % count >= losses))

    def weather_winners(self, count=40, desk="haghani-2"):
        """NO legs at 92 cents that always pay: enough of them flips the losers' interval."""
        for k in range(count):
            self.add(desk, kalshi_payload(f"KXHIGHNY-26OCT{k % 28 + 1:02d}-B75.5", leg="no", entry="0.92", won=True))

    def cheap_yes_winners(self, count=24, desk="mullins"):
        """YES legs at 20 cents that pay one time in two: a prefer rule."""
        for k in range(count):
            self.add(desk, kalshi_payload(f"KXBTCD-26SEP{k % 28 + 1:02d}-T60000", leg="yes", entry="0.20", won=k % 2 == 0, strategy="hourly_ranges"))


AVOID = {
    "id": "nyc-high-no-legs-above-90c",
    "statement": "Do not buy NO on the NYC daily high above 90 cents: the tail pays for every win.",
    "filter": {"series_prefix": ["KXHIGHNY"], "result_side": "no", "entry_price": [0.9, 1.0]},
    "direction": "avoid",
}
PREFER = {
    "id": "cheap-btc-yes-legs",
    "statement": "Buy cheap YES legs on the hourly Bitcoin ranges when the strategy fires.",
    "filter": {"series_prefix": ["KXBTCD"], "result_side": "yes", "entry_price": [0.1, 0.3], "strategy": ["hourly_ranges"]},
    "direction": "prefer",
}


class ScriptedProvider:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": list(items), **kwargs})
        reply = self.replies.pop(0) if self.replies else {"rules": [], "retire": []}
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else "Here is the book:\n```json\n" + json.dumps(reply) + "\n```"
        return SimpleNamespace(output_text=text, cost_usd=Decimal("0.11"))


class MindCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.log = EventLog(self.root / "events.sqlite")
        self.tape = Tape(self.log)
        self.alerts = []

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def mind(self, provider=None, **config):
        return FirmMind(
            self.log,
            path=self.root / "mind.json",
            provider=provider,
            config=config,
            families=lambda: {"haghani": "weather", "haghani-2": "weather", "mullins": "kalshi"},
            alert=lambda level, text: self.alerts.append(text),
            register=False,
        )

    def lab_events(self, kind):
        return self.log.read(stream="lab", kind=kind)


# --------------------------------------------------------------------------- filters


class FilterTests(unittest.TestCase):
    def outcomes(self):
        rows = [
            event("haghani", kalshi_payload("KXHIGHNY-26SEP16-B81.5", leg="no", entry="0.92", won=False), 0),
            event("haghani", kalshi_payload("KXHIGHCHI-26SEP16-B70.5", leg="yes", entry="0.10", won=True, real=True), 1),
            event("mullins", kalshi_payload("KXBTCD-26SEP16-T60000", leg="yes", entry="0.25", strategy="hourly_ranges"), 2),
            event("hilibrand-3", spot_payload(), 3),
        ]
        families = {"haghani": "weather", "mullins": "kalshi"}
        return [parse_outcome(e, families) for e in rows]

    def selected(self, raw_filter):
        rule_filter = validate_filter(raw_filter)
        return [o.ticker for o in self.outcomes() if matches(rule_filter, o)]

    def test_a_series_prefix_matches_the_start_of_the_ticker(self):
        self.assertEqual(self.selected({"series_prefix": ["kxhigh"]}), ["KXHIGHNY-26SEP16-B81.5", "KXHIGHCHI-26SEP16-B70.5"])
        self.assertEqual(self.selected({"series_prefix": ["KXHIGHNY"]}), ["KXHIGHNY-26SEP16-B81.5"])
        self.assertEqual(self.selected({"series_prefix": ["BTC-USD"]}), ["BTC-USD"])

    def test_the_leg_is_read_from_the_instrument_key_not_the_markets_result(self):
        lost_no = self.outcomes()[0]
        self.assertEqual(lost_no.leg, "no")
        self.assertEqual(self.outcomes()[0].series, "KXHIGHNY")
        # The market resolved YES, the desk held NO: a rule about NO legs still selects it.
        self.assertEqual(self.selected({"result_side": "no"}), ["KXHIGHNY-26SEP16-B81.5"])
        self.assertEqual(self.selected({"result_side": "yes"}), ["KXHIGHCHI-26SEP16-B70.5", "KXBTCD-26SEP16-T60000"])
        spot = self.outcomes()[3]
        self.assertIsNone(spot.leg)
        self.assertEqual((spot.venue, spot.series, spot.family), ("coinbase", "BTC", "hilibrand"))

    def test_the_price_band_is_inclusive_at_both_ends(self):
        self.assertEqual(self.selected({"entry_price": [0.1, 0.25]}), ["KXHIGHCHI-26SEP16-B70.5", "KXBTCD-26SEP16-T60000"])
        self.assertEqual(self.selected({"entry_price": [0.9, 1]}), ["KXHIGHNY-26SEP16-B81.5"])
        self.assertEqual(self.selected({"entry_price": [0.11, 0.24]}), [])

    def test_the_strategy_is_the_tag_the_rationale_opens_with(self):
        self.assertEqual(self.selected({"strategy": ["hourly_ranges"]}), ["KXBTCD-26SEP16-T60000"])
        self.assertEqual(self.selected({"strategy": ["discretionary"]}), ["KXHIGHNY-26SEP16-B81.5", "KXHIGHCHI-26SEP16-B70.5"])
        self.assertEqual(self.selected({"strategy": ["momentum"], "venue": "coinbase"}), ["BTC-USD"])

    def test_real_money_selects_live_or_shadow_and_an_unknown_matches_neither(self):
        self.assertEqual(self.selected({"real_money": True}), ["KXHIGHCHI-26SEP16-B70.5", "BTC-USD"])
        self.assertEqual(self.selected({"real_money": False}), ["KXHIGHNY-26SEP16-B81.5", "KXBTCD-26SEP16-T60000"])
        payload = kalshi_payload("KXHIGHNY-26SEP17-B80.5")
        payload.pop("real_money")
        old = parse_outcome(event("haghani", payload), {})
        self.assertIsNone(old.real_money)
        self.assertFalse(matches({"real_money": False}, old))
        self.assertTrue(matches({"series_prefix": ["KXHIGHNY"]}, old))

    def test_families_come_from_the_roster_and_held_hours_must_be_known(self):
        self.assertEqual(self.selected({"family": ["weather"]}), ["KXHIGHNY-26SEP16-B81.5", "KXHIGHCHI-26SEP16-B70.5"])
        self.assertEqual(self.selected({"family": ["hilibrand"]}), ["BTC-USD"])  # no roster entry: its id's root
        self.assertEqual(mind_module.family_of("haghani-3-2", {"haghani": "weather"}), "weather")
        self.assertEqual(mind_module.family_of("haghani-3-2", {"haghani-3": "storms", "haghani": "weather"}), "storms")
        self.assertEqual(self.selected({"held_hours": [3, 4]}), ["BTC-USD"])
        payload = kalshi_payload("KXHIGHNY-26SEP17-B80.5", held=None)
        self.assertFalse(matches({"held_hours": [0, 1000]}, parse_outcome(event("haghani", payload), {})))

    def test_an_outcome_without_a_notional_or_a_desk_is_not_scored(self):
        self.assertIsNone(parse_outcome(event("haghani", {**kalshi_payload("KXA-1"), "entry_price": "0"})))
        self.assertIsNone(parse_outcome(event("haghani", {**kalshi_payload("KXA-1"), "quantity": None})))
        self.assertIsNone(parse_outcome(SimpleNamespace(stream="ops", payload=kalshi_payload("KXA-1"), seq=1, at=stamp(0))))
        short = parse_outcome(event("haghani", {**kalshi_payload("KXA-1"), "quantity": "-5"}))
        self.assertEqual(short.quantity, 5.0)


# --------------------------------------------------------------------------- scoring


class BootstrapTests(unittest.TestCase):
    def test_the_interval_is_seeded_so_the_same_tape_scores_the_same(self):
        rng = random.Random(3)
        values = [rng.gauss(-0.05, 0.3) for _ in range(200)]
        first = bootstrap_ci(values)
        self.assertEqual(first, bootstrap_ci(list(values)))
        self.assertNotEqual(first, bootstrap_ci(values, seed=1))
        mean = math.fsum(values) / len(values)
        self.assertLess(first[0], mean)
        self.assertGreater(first[1], mean)
        self.assertIsNone(bootstrap_ci([]))
        self.assertEqual(bootstrap_ci([0.25]), (0.25, 0.25))

    def test_a_score_is_a_function_of_the_tape(self):
        outcomes = [parse_outcome(event("haghani", kalshi_payload(f"KXHIGHNY-{i}", entry="0.92", won=i % 3 != 0), i), {}) for i in range(30)]
        first = evaluate(AVOID, outcomes)
        self.assertEqual(first, evaluate(AVOID, list(outcomes)))
        self.assertEqual(first["n"], 30)
        self.assertEqual(first["wins"], 20)
        self.assertAlmostEqual(first["pnl_usd"], 20 * 0.8 - 10 * 9.2, places=6)
        self.assertAlmostEqual(first["notional_usd"], 30 * 9.2, places=6)
        self.assertAlmostEqual(first["mean_pnl_per_dollar"], (20 * (0.08 / 0.92) - 10) / 30, places=5)
        self.assertEqual((first["first_seen"], first["last_seen"]), (stamp(0), stamp(29)))
        self.assertEqual(evaluate({"filter": {"venue": "coinbase"}}, outcomes)["ci"], None)

    def test_evidence_reads_in_cents_per_dollar(self):
        score = {"n": 47, "mean_pnl_per_dollar": -0.061, "ci": [-0.09, -0.032]}
        self.assertEqual(evidence_text(score), "n=47, -6.1 cents per $, CI [-9.0, -3.2]")


class ValidationTests(unittest.TestCase):
    def test_a_good_rule_is_normalized(self):
        rule = validate_rule(
            {
                "id": "nyc-high-no-legs",
                "statement": "  Avoid NO legs on the\nNYC high above 90 cents.  ",
                "filter": {"series_prefix": ["kxhighny", "KXHIGHNY"], "result_side": "no", "entry_price": ["0.9", 1], "real_money": None, "venue": None},
                "direction": "avoid",
            }
        )
        self.assertEqual(rule["statement"], "Avoid NO legs on the NYC high above 90 cents.")
        self.assertEqual(rule["filter"], {"series_prefix": ["KXHIGHNY"], "result_side": "no", "entry_price": [0.9, 1.0]})

    def test_bad_rules_are_refused_with_the_reason(self):
        good = dict(AVOID)
        cases = [
            ("not an object", "a rule must be an object"),
            ({**good, "confidence": 0.9}, "unknown rule keys: confidence"),
            ({**good, "id": "Bad Id"}, "id must be"),
            ({**good, "statement": "short"}, "statement must be"),
            ({**good, "statement": "Avoid <script> legs on every market."}, "markup"),
            ({**good, "direction": "short"}, "direction must be"),
            ({**good, "filter": {}}, "at least one field"),
            ({**good, "filter": {"ticker": ["KX"]}}, "unknown filter keys: ticker"),
            ({**good, "filter": {"series_prefix": "KXHIGH"}}, "filter.series_prefix must list"),
            ({**good, "filter": {"series_prefix": ["KX HIGH"]}}, "malformed"),
            ({**good, "filter": {"family": ["Weather"]}}, "malformed"),
            ({**good, "filter": {"strategy": ["Hourly-Ranges"]}}, "malformed"),
            ({**good, "filter": {"result_side": "maybe"}}, "result_side"),
            ({**good, "filter": {"entry_price": [0.9, 0.1]}}, "0 <= lo <= hi"),
            ({**good, "filter": {"entry_price": [-0.1, 0.5]}}, "0 <= lo <= hi"),
            ({**good, "filter": {"entry_price": [0.1]}}, "[lo, hi]"),
            ({**good, "filter": {"held_hours": ["x", 3]}}, "must be numbers"),
            ({**good, "filter": {"real_money": "yes"}}, "real_money"),
            ({**good, "filter": {"venue": "alpaca"}}, "venue"),
        ]
        for raw, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(MindError) as caught:
                    validate_rule(raw)
                self.assertIn(reason, str(caught.exception))

    def test_a_reply_is_read_from_the_first_object_in_the_text(self):
        rules, retire = parse_reply('Thinking...\n```json\n{"rules": [{"id": "x"}], "retire": ["old-rule", 3]}\n```')
        self.assertEqual((rules, retire), ([{"id": "x"}], ["old-rule"]))
        self.assertEqual(parse_reply("no json here"), ([], []))
        self.assertEqual(parse_reply('{"rules": "nope"}'), ([], []))


class AdmissionTests(MindCase):
    def test_a_rule_is_admitted_only_when_its_interval_excludes_zero_in_its_direction(self):
        self.tape.weather_losers()
        outcomes, _ = self.mind().outcomes()
        score = evaluate(validate_rule(AVOID), outcomes)
        self.assertEqual(score["n"], 20)
        self.assertLess(score["ci"][1], 0)
        self.assertEqual(verdict(score, "avoid", 15), (True, "admitted"))
        ok, reason = verdict(score, "prefer", 15)
        self.assertFalse(ok)
        self.assertIn("does not sit above zero", reason)
        ok, reason = verdict(score, "avoid", 25)
        self.assertFalse(ok)
        self.assertIn("n=20 is below the 25", reason)
        noise = {"n": 40, "mean_pnl_per_dollar": 0.001, "ci": [-0.05, 0.06]}
        self.assertFalse(verdict(noise, "avoid", 15)[0])
        self.assertFalse(verdict(noise, "prefer", 15)[0])

    def test_the_scientist_proposes_and_only_the_evidence_admits(self):
        self.tape.weather_losers()
        self.tape.cheap_yes_winners()
        provider = ScriptedProvider(
            {
                "rules": [
                    AVOID,
                    PREFER,
                    {**AVOID, "id": "nyc-high-no-legs-prefer", "direction": "prefer"},
                    {**AVOID, "id": "tiny-cell", "filter": {"series_prefix": ["KXHIGHNY-26SEP01"]}},
                    {"id": "Broken Rule", "statement": "x", "filter": {}, "direction": "avoid"},
                    {**AVOID, "id": "same-as-avoid"},
                ],
                "retire": ["nothing-by-this-id"],
            }
        )
        mind = self.mind(provider)
        summary = mind.run("2026-09-16T12:00:00.000Z")
        self.assertTrue(summary["asked"])
        statuses = {p["id"]: p["status"] for p in summary["proposals"]}
        self.assertEqual(
            statuses,
            {
                AVOID["id"]: "admitted",
                PREFER["id"]: "admitted",
                "nyc-high-no-legs-prefer": "rejected",
                "tiny-cell": "rejected",
                "Broken Rule": "invalid",
                "same-as-avoid": "rejected",
            },
        )
        book = json.loads((self.root / "mind.json").read_text())
        self.assertEqual({r["id"] for r in book["rules"]}, {AVOID["id"], PREFER["id"]})
        for rule in book["rules"]:
            self.assertRegex(rule["evidence"], r"^n=\d+, -?\d+\.\d cents per \$, CI \[-?\d+\.\d, -?\d+\.\d\]$")
        # The call: one model, the mind's own budget desk, a deterministic key, the table in the packet.
        call = provider.calls[0]
        self.assertEqual((call["profile"], call["desk_id"], call["reasoning_effort"]), ("k3", "mind", "high"))
        self.assertEqual(call["desk_cap_usd_per_day"], "8")
        self.assertEqual(call["request_key"], "mind:2026-09-16T12:00")
        packet = call["items"][1]["content"]
        self.assertIn("family | strategy | series | entry band | leg | n", packet)
        self.assertIn("weather | discretionary | KXHIGHNY | 0.90-1.00 | no | 20 | 12 |", packet)
        self.assertIn("kalshi | hourly_ranges | KXBTCD | 0.10-0.25 | yes | 24 | 12 |", packet)
        self.assertIn("avoid needs the upper bound below zero", call["items"][0]["content"])
        self.assertEqual(book["spend"], {"day": "2026-09-16", "usd": "0.11"})
        # The record: a hypothesis for the pass and a result for the change, small and markup-free.
        hypothesis = self.lab_events("lab.hypothesis")
        result = self.lab_events("lab.result")
        self.assertEqual(len(hypothesis), 1)
        self.assertEqual(len(result), 1)
        self.assertIn("read 44 settled outcomes from 2 desks and scored 6 proposed rules, 2 admitted", hypothesis[0].payload["text"])
        added = {row["id"]: row for row in result[0].payload["metrics"]["added"]}
        self.assertEqual(set(added), {AVOID["id"], PREFER["id"]})
        self.assertEqual(added[AVOID["id"]]["n"], "20")
        self.assertIn(AVOID["id"], result[0].payload["verdict"])
        for e in hypothesis + result:
            text = canonical(e.payload)
            self.assertLess(len(text.encode()), 3000)
            self.assertNotIn("<", text)
            self.assertIsNone(shape_problem(e))

    def test_the_book_keeps_the_strongest_rules_up_to_its_cap(self):
        self.tape.weather_losers()
        self.tape.cheap_yes_winners()
        weak = {**AVOID, "id": "all-weather-no-legs", "filter": {"family": ["weather"], "result_side": "no"}}
        weak["filter"] = {"family": ["weather"], "result_side": "no", "held_hours": [0, 100]}
        mind = self.mind(ScriptedProvider({"rules": [AVOID, PREFER, weak]}), max_rules=2)
        summary = mind.run("2026-09-16T12:00:00.000Z")
        ranks = sorted((evaluate(validate_rule(r), mind.outcomes()[0]) for r in (AVOID, PREFER, weak)), key=mind_module.rank_of, reverse=True)
        book = mind.book()
        self.assertEqual(len(book["rules"]), 2)
        self.assertEqual([r["rank"] for r in book["rules"]], sorted((r["rank"] for r in book["rules"]), reverse=True))
        self.assertAlmostEqual(book["rules"][0]["rank"], mind_module.rank_of(ranks[0]), places=5)
        self.assertEqual(len(summary["retired"]), 1)
        self.assertIn("outranked", book["retired"][0]["reason"])


class RetirementTests(MindCase):
    def admit(self):
        self.tape.weather_losers()
        mind = self.mind(ScriptedProvider({"rules": [AVOID]}))
        mind.run("2026-09-16T12:00:00.000Z")
        self.assertEqual([r["id"] for r in mind.rules()], [AVOID["id"]])
        return mind

    def test_a_rule_that_stops_holding_is_retired_without_a_model(self):
        self.admit()
        self.tape.weather_winners()
        mind = self.mind(provider=None)
        summary = mind.run("2026-09-16T13:00:00.000Z")
        self.assertFalse(summary["asked"])
        self.assertEqual(summary["retired"], [AVOID["id"]])
        book = mind.book()
        self.assertEqual(book["rules"], [])
        self.assertIn("re-scored: the interval", book["retired"][0]["reason"])
        self.assertEqual(book["retired"][0]["score"]["n"], 60)
        result = self.lab_events("lab.result")[-1].payload
        self.assertEqual(result["metrics"]["retired"][0]["id"], AVOID["id"])
        self.assertIn("re-scored", result["metrics"]["retired"][0]["reason"])
        self.assertIn("retired " + AVOID["id"], result["verdict"])

    def test_a_hand_edited_rule_that_breaks_the_schema_is_retired(self):
        self.admit()
        book = json.loads((self.root / "mind.json").read_text())
        book["rules"][0]["filter"] = {"ticker": ["KX"]}
        (self.root / "mind.json").write_text(json.dumps(book))
        self.tape.cheap_yes_winners()
        mind = self.mind()
        summary = mind.run("2026-09-16T13:00:00.000Z")
        self.assertEqual(summary["retired"], [AVOID["id"]])
        self.assertIn("invalid in the book: unknown filter keys: ticker", mind.book()["retired"][0]["reason"])

    def test_a_mass_retirement_sheds_detail_to_stay_small(self):
        rules = []
        for k in range(12):
            rule = validate_rule({
                "id": f"long-rule-{k:02d}",
                "statement": f"Rule {k}: " + "avoid the thing that the evidence once said was bad, " * 4,
                "filter": {"series_prefix": [f"KXNEVER{k}"]},
                "direction": "avoid",
            })
            rules.append({**rule, "score": SCORE_AVOID})
        (self.root / "mind.json").write_text(json.dumps({"rules": rules}))
        self.tape.weather_losers()
        summary = self.mind().run("2026-09-16T12:00:00.000Z")
        self.assertEqual(len(summary["retired"]), 12)
        event = self.lab_events("lab.result")[-1]
        self.assertLessEqual(len(canonical(event.payload).encode()), 3000)
        self.assertIsNone(shape_problem(event))
        self.assertTrue(all("statement" not in row for row in event.payload["metrics"]["retired"]))

    def test_the_scientist_may_retire_a_rule_by_id(self):
        self.admit()
        self.tape.cheap_yes_winners()
        mind = self.mind(ScriptedProvider({"rules": [], "retire": [AVOID["id"]]}))
        summary = mind.run("2026-09-16T13:00:00.000Z")
        self.assertEqual(summary["retired"], [AVOID["id"]])
        self.assertEqual(mind.book()["retired"][0]["reason"], "retired by the scientist")

    def test_a_pass_with_no_new_outcomes_does_nothing_and_pays_nothing(self):
        self.admit()
        provider = ScriptedProvider()
        mind = self.mind(provider)
        summary = mind.run("2026-09-16T13:00:00.000Z")
        self.assertEqual(summary["skipped"], "no new outcomes since the last pass")
        self.assertEqual(provider.calls, [])
        self.assertEqual(mind.book()["last_pass_at"], "2026-09-16T13:00:00.000Z")
        self.assertEqual(len(self.lab_events("lab.hypothesis")), 1)

    def test_the_daily_budget_holds_even_when_the_provider_would_admit_the_call(self):
        self.tape.weather_losers()
        (self.root / "mind.json").write_text(json.dumps({"spend": {"day": "2026-09-16", "usd": "7.95"}}))
        provider = ScriptedProvider({"rules": [AVOID]})
        summary = self.mind(provider).run("2026-09-16T12:00:00.000Z")
        self.assertFalse(summary["asked"])
        self.assertEqual(provider.calls, [])
        self.assertTrue(any("skipped its model call" in a for a in self.alerts))


class SchedulingTests(MindCase):
    def test_a_pass_is_due_on_its_interval_and_never_raises(self):
        self.tape.weather_losers()
        provider = ScriptedProvider(RuntimeError("provider_transport_timeout"))
        mind = self.mind(provider, interval_minutes=60)
        self.assertTrue(mind.due("2026-09-16T12:00:00.000Z"))
        summary = mind.run("2026-09-16T12:00:00.000Z")
        self.assertFalse(summary["asked"])
        self.assertTrue(any("model call failed" in a for a in self.alerts))
        self.assertFalse(mind.due("2026-09-16T12:59:00.000Z"))
        self.assertTrue(mind.due("2026-09-16T13:00:00.000Z"))

        class Broken:
            def read(self, **kwargs):
                raise RuntimeError("disk")

        broken = FirmMind(Broken(), path=self.root / "broken.json", alert=lambda level, text: self.alerts.append(text), register=False)
        self.assertEqual(broken.run("2026-09-16T12:00:00.000Z")["failed"], "RuntimeError")
        # The attempt was stamped before the failure, so the next try is an interval away.
        self.assertFalse(broken.due("2026-09-16T12:30:00.000Z"))
        self.assertFalse(self.mind(enabled=False).due("2026-09-16T12:00:00.000Z"))


# --------------------------------------------------------------------------- the feedback


def book_with(*rules):
    rows = []
    for rule, score in rules:
        rows.append({**validate_rule(rule), "score": score, "evidence": evidence_text(score)})
    return {"version": 1, "rules": rows, "retired": []}


SCORE_AVOID = {"n": 47, "mean_pnl_per_dollar": -0.061, "ci": [-0.09, -0.032]}
SCORE_PREFER = {"n": 24, "mean_pnl_per_dollar": 0.5, "ci": [0.1, 0.9]}
WEATHER_ONLY = {
    "id": "weather-only",
    "statement": "Weather desks: skip NO legs the night before a front comes through.",
    "filter": {"family": ["weather"], "result_side": "no"},
    "direction": "avoid",
}
COINBASE_ONLY = {
    "id": "coinbase-only",
    "statement": "Let the momentum strategy's Coinbase entries run to their targets.",
    "filter": {"venue": "coinbase", "strategy": ["momentum"]},
    "direction": "prefer",
}


class PromptTests(MindCase):
    def test_the_block_lists_each_rule_with_its_evidence_and_how_to_use_it(self):
        text = render_rules([{"statement": AVOID["statement"], "direction": "avoid", "score": SCORE_AVOID}])
        self.assertIn("measured across every desk's settled trades", text)
        self.assertIn("unless your own settled record says otherwise", text)
        self.assertIn(f"- AVOID: {AVOID['statement']} (n=47, -6.1 cents per $, CI [-9.0, -3.2])", text)
        self.assertEqual(render_rules([]), "")

    def test_a_rule_speaks_to_its_family_and_its_venue_only(self):
        self.assertTrue(applies(validate_rule(AVOID), family="earnings", venues=["alpaca"]))
        self.assertFalse(applies(validate_rule(WEATHER_ONLY), family="kalshi", venues=["kalshi"]))
        self.assertTrue(applies(validate_rule(WEATHER_ONLY), family="weather", venues=["kalshi"]))
        self.assertFalse(applies(validate_rule(COINBASE_ONLY), family="kalshi", venues=["kalshi"]))
        path = self.root / "mind.json"
        path.write_text(json.dumps(book_with((AVOID, SCORE_AVOID), (WEATHER_ONLY, SCORE_AVOID), (COINBASE_ONLY, SCORE_PREFER))))
        mind = self.mind()
        self.assertEqual([r["id"] for r in mind.rules_for(family="kalshi", venues=["kalshi"])], [AVOID["id"]])
        self.assertEqual([r["id"] for r in mind.rules_for(family="weather", venues=["kalshi"])], [AVOID["id"], "weather-only"])
        block = rules_for_family("kalshi", path=path)
        self.assertIn("- AVOID: " + AVOID["statement"], block)
        self.assertIn("- PREFER: " + COINBASE_ONLY["statement"], block)  # a generator sees every venue's rules
        self.assertNotIn(WEATHER_ONLY["statement"], block)
        self.assertIn(WEATHER_ONLY["statement"], rules_for_family("weather", path=path))
        self.assertEqual(rules_for_family("kalshi", path=self.root / "missing.json"), "")

    def test_rules_for_family_reads_the_floors_own_book_by_default(self):
        saved = mind_module._ACTIVE_PATH
        try:
            path = self.root / "floor-mind.json"
            path.write_text(json.dumps(book_with((AVOID, SCORE_AVOID))))
            FirmMind(self.log, path=path)
            self.assertIn(AVOID["statement"], rules_for_family("weather"))
            mind_module._ACTIVE_PATH = None
            self.assertEqual(rules_for_family("weather"), "")
        finally:
            mind_module._ACTIVE_PATH = saved


class DeskPromptTests(DeskCase):
    def test_the_session_reads_what_the_firm_has_learned_after_the_standings(self):
        provider = DeskProvider(provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-1"))
        self.ctx.standings = lambda: [{"desk_id": "hilibrand", "desk_name": "Hilibrand", "mode": "live", "family": "crypto", "pnl_usd": "12.40", "budget_factor": "2.10"}]
        self.ctx.floor_calls = lambda limit=12: [{"market": "KXHIGHNY-26SEP16-B81.5", "desk_name": "Haghani", "mode": "live", "probability": "0.18"}]
        self.ctx.firm_rules = lambda: [{"id": AVOID["id"], "statement": AVOID["statement"], "direction": "avoid", "evidence": evidence_text(SCORE_AVOID)}]
        self.desk(provider).run_session("market_close")
        text = provider.calls[0]["items"][1]["content"]
        self.assertIn(f"# What the firm has learned\nRules the firm measured", text)
        self.assertIn(f"- AVOID: {AVOID['statement']} (n=47, -6.1 cents per $, CI [-9.0, -3.2])", text)
        self.assertLess(text.index("# Standings"), text.index("# What the firm has learned"))
        self.assertLess(text.index("# What the firm has learned"), text.index("# The floor's calls"))

    def test_a_desk_without_rules_or_with_a_broken_mind_keeps_its_prompt(self):
        provider = DeskProvider(provider_response(calls=[tool_call("end_session", summary="done")], request_id="req-1"))
        self.ctx.firm_rules = lambda: (_ for _ in ()).throw(RuntimeError("book unreadable"))
        self.desk(provider).run_session("market_close")
        self.assertNotIn("What the firm has learned", str(provider.calls[0]["items"]))


class LabPacketTests(LabCase):
    def test_the_labs_packet_carries_the_familys_rules(self):
        path = self.root / "mind.json"
        path.write_text(json.dumps(book_with((AVOID, SCORE_AVOID), (WEATHER_ONLY, SCORE_AVOID))))
        lab = self.lab()
        parent = lab_manifest("earnings-01", capital={"mode": "live", "usd": "1000"})
        self.assertNotIn("What the firm has learned", lab.packet("earnings", parent, NIGHT))
        lab.mind = FirmMind(self.log, path=path, register=False)
        packet = lab.packet("earnings", parent, NIGHT)
        self.assertIn("## What the firm has learned", packet)
        self.assertIn(AVOID["statement"], packet)
        self.assertNotIn(WEATHER_ONLY["statement"], packet)


# --------------------------------------------------------------------------- the floor


class ServiceHookTests(ServiceCase):
    def outcomes(self, count, start=0):
        for k in range(start, start + count):
            self.service.log.append(
                "desk:haghani", "desk.outcome",
                kalshi_payload(f"KXHIGHNY-26SEP{k % 28 + 1:02d}-B81.5", entry="0.92", won=k % 5 >= 2),
                id=f"outcome:haghani:{k}", at=stamp(k),
            )

    def join(self):
        slot = getattr(self.service, "_workers", {}).get("mind")
        if slot is not None:
            slot["thread"].join(timeout=30)

    def test_the_pass_runs_off_the_tick_at_its_interval_and_never_raises(self):
        self.service.close()
        self.service = self.build(mind={"enabled": True, "interval_minutes": 60, "min_n": 15})
        workers = []
        real_off_tick = self.service._off_tick

        def off_tick(name, work):
            workers.append(name)
            if name != "mind":
                return real_off_tick(name, work)
            # The mind's pass on a real worker thread, the way the floor runs it.
            self.service.config["background_work"] = True
            try:
                return real_off_tick(name, work)
            finally:
                self.service.config["background_work"] = False

        self.service._off_tick = off_tick
        self.assertIsNotNone(self.service.mind)
        self.assertIs(self.service.lab.mind, self.service.mind)
        self.outcomes(20)
        provider = ScriptedProvider(RuntimeError("provider_transport_timeout"), {"rules": [AVOID]})
        self.service.mind.provider = provider
        book = self.service.capital_dir / "mind.json"

        result = self.tick(moment(2026, 9, 14, 14, 0))
        self.join()
        self.assertIn("mind", workers)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(json.loads(book.read_text())["last_pass_at"], "2026-09-14T14:00:00.000Z")
        alerts = [e.payload["text"] for e in self.service.log.read(stream="ops", kind="ops.alert", limit=1000)]
        self.assertTrue(any("firm mind model call failed" in a for a in alerts))

        workers.clear()
        self.tick(moment(2026, 9, 14, 14, 30))  # inside the interval: no pass
        self.join()
        self.assertNotIn("mind", workers)
        self.assertEqual(len(provider.calls), 1)

        self.outcomes(5, start=20)
        self.tick(moment(2026, 9, 14, 15, 1))
        self.join()
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual([r["id"] for r in self.service.mind.rules()], [AVOID["id"]])
        manifest = self.service.manifests[DESK]
        rules = self.service.context(manifest).firm_rules()
        self.assertEqual([r["id"] for r in rules], [AVOID["id"]])
        self.assertIn("cents per $", rules[0]["evidence"])

    def test_a_switched_off_mind_is_absent_and_the_desk_reads_nothing(self):
        self.service.close()
        self.service = self.build(mind={"enabled": False})
        self.assertIsNone(self.service.mind)
        self.tick(moment(2026, 9, 14, 14, 0))
        self.assertEqual(self.service.context(self.service.manifests[DESK]).firm_rules(), [])


# --------------------------------------------------------------------------- a realistic tape


class RealisticTapeTests(MindCase):
    """A synthetic floor shaped like the real one: weather NO legs that bleed on the tail, hourly
    Bitcoin ranges from a strategy, a crypto desk's spot round trips, live and shadow."""

    def build_floor(self):
        rng = random.Random(16)
        for k in range(160):  # weather: NO legs at 85-97 cents; the tail loses 14% of the time
            entry = rng.choice(["0.85", "0.88", "0.91", "0.94", "0.97"])
            city = rng.choice(["NY", "CHI", "MIA", "AUS"])
            self.tape.add(
                rng.choice(["haghani", "haghani-2", "haghani-3"]),
                kalshi_payload(f"KXHIGH{city}-26SEP{k % 28 + 1:02d}-B8{k % 9}.5", leg="no", entry=entry,
                               quantity=str(rng.choice([5, 10, 15])), won=rng.random() > 0.14,
                               held=f"{rng.uniform(2, 20):.1f}", real=k % 4 == 0),
            )
        for k in range(120):  # the hourly range strategy: cheap YES legs that pay about a third of the time
            entry = rng.choice(["0.12", "0.18", "0.22"])
            self.tape.add(
                "mullins",
                kalshi_payload(f"KXBTCD-26SEP{k % 28 + 1:02d}-T6{k % 7}000", leg="yes", entry=entry,
                               quantity="20", won=rng.random() < 0.34, held="1.0", real=k % 3 == 0, strategy="hourly_ranges"),
            )
        for k in range(40):  # spot round trips, a coin flip after fees
            exit_price = str(60000 + rng.choice([-450, -300, 280, 420]))
            self.tape.add("hilibrand", spot_payload(exit_price=exit_price, real=k % 2 == 0))

    def test_the_table_and_a_pass_on_a_realistic_floor(self):
        self.build_floor()
        mind = self.mind()
        outcomes, latest = mind.outcomes()
        self.assertEqual(len(outcomes), 320)
        self.assertEqual(latest, self.log.latest_seq())
        cells = aggregate(outcomes, 60)
        self.assertLessEqual(len(cells), 60)
        self.assertEqual(sum(c["n"] for c in aggregate(outcomes, 10_000)), 320)
        self.assertEqual({c["band"] for c in cells if c["series"] == "BTC"}, {"spot"})
        top = max(cells, key=lambda c: abs(c["pnl_usd"]))
        self.assertEqual(cells[0], top)

        tail = {
            "id": "weather-no-tail",
            "statement": "Avoid NO legs on the daily highs priced at 85 cents or more: the tail costs more than the carry pays.",
            "filter": {"series_prefix": ["KXHIGH"], "result_side": "no", "entry_price": [0.85, 1.0]},
            "direction": "avoid",
        }
        ranges = {
            "id": "hourly-ranges-cheap-yes",
            "statement": "Keep buying the hourly Bitcoin range YES legs under 25 cents that the range strategy picks.",
            "filter": {"strategy": ["hourly_ranges"], "result_side": "yes", "entry_price": [0.1, 0.25]},
            "direction": "prefer",
        }
        spot = {
            "id": "spot-round-trips",
            "statement": "Avoid short spot round trips on Bitcoin: the moves do not cover the spread.",
            "filter": {"venue": "coinbase", "series_prefix": ["BTC-USD"]},
            "direction": "avoid",
        }
        provider = ScriptedProvider({"rules": [tail, ranges, spot]})
        mind = self.mind(provider)
        summary = mind.run("2026-09-16T12:00:00.000Z")
        by_id = {p["id"]: p for p in summary["proposals"]}
        scores = {r["id"]: evaluate(validate_rule(r), outcomes) for r in (tail, ranges, spot)}
        for rule_id, score in scores.items():
            expected = verdict(score, next(r for r in (tail, ranges, spot) if r["id"] == rule_id)["direction"], 15)[0]
            self.assertEqual(by_id[rule_id]["status"] == "admitted", expected, (rule_id, score))
        self.assertEqual({r["id"] for r in mind.rules()}, {k for k, p in by_id.items() if p["status"] == "admitted"})
        self.assertLess(len(provider.calls[0]["items"][1]["content"]), 20_000)


class ScriptTests(MindCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("mind_pass", ROOT / "scripts" / "mind_pass.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_a_dry_run_prints_the_table_and_the_book_and_writes_nothing(self):
        capital = self.root / "box" / ".data" / "ltcm"
        capital.mkdir(parents=True)
        log = EventLog(capital / "events.sqlite")
        Tape(log).weather_losers()
        log.close()
        (capital / "mind.json").write_text(json.dumps(book_with((AVOID, SCORE_AVOID))))
        before = (capital / "mind.json").read_text()

        def latest_seq():
            log = EventLog(capital / "events.sqlite")
            try:
                return log.latest_seq()
            finally:
                log.close()

        seq_before = latest_seq()
        out = io.StringIO()
        with redirect_stdout(out):
            code = self.load().main(["--root", str(self.root / "box"), "--dry-run"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("20 scoreable outcomes", text)
        self.assertIn("weather | discretionary | KXHIGHNY | 0.90-1.00 | no | 20 | 12", text)
        self.assertIn(f"{AVOID['id']} [avoid] n=20", text)
        self.assertIn("holds", text)
        self.assertEqual((capital / "mind.json").read_text(), before)
        self.assertEqual(latest_seq(), seq_before)


if __name__ == "__main__":
    unittest.main()
