"""The lab: a bounded vocabulary, directed variants, verdicts on gate evidence, a house genome."""

import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.evolve import Evolution, apply_change
from ltcm.events import EventLog
from ltcm.lab import Lab, LabError, experiment_id, parse_proposals, validate_change
from ltcm.manifest import DeskManifest, load_manifest
from ltcm.tests.test_manifest import SAMPLE

NIGHT = "2026-09-15T00:00:00.000Z"
LATER = "2026-10-10T00:00:00.000Z"


def manifest(desk_id="earnings-01", **overrides):
    data = copy.deepcopy(SAMPLE)
    data["id"] = desk_id
    data["playbook"] = f"playbooks/{desk_id}.md"
    data.update(overrides)
    return DeskManifest.from_dict(data)


class FakeProvider:
    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = []

    def respond(self, profile, items, **kwargs):
        self.calls.append({"profile": profile, "items": items, **kwargs})
        text = self.replies.pop(0) if self.replies else "Rewritten playbook.\n"
        if isinstance(text, Exception):
            raise text
        return SimpleNamespace(output_text=text, cost_usd=Decimal("0.02"))

    def spent_today(self, desk_id=None):
        return Decimal("0")


def reply(*experiments):
    return "Here you go:\n```json\n" + json.dumps({"experiments": list(experiments)}) + "\n```"


class VocabularyTests(unittest.TestCase):
    def setUp(self):
        self.parent = manifest(instruments={**SAMPLE["instruments"], "allow": ["AAPL"]})

    def test_every_key_in_the_vocabulary_normalizes(self):
        change = validate_change(
            {
                "model.profile": "kimi_flex",
                "model.reasoning_effort": "high",
                "cadence.sessions": ["10:00", "09:45", "10:00"],
                "memory_limit": 60,
                "tools_add": ["memo_read"],
                "instruments.allow_add": ["msft"],
                "limits": {"max_position_pct": "0.2", "max_orders_per_day": 5},
                "playbook_note": "Size into a position over two sessions.",
            },
            self.parent,
        )
        self.assertEqual(change["cadence.sessions"], ["09:45", "10:00"])
        self.assertEqual(change["instruments.allow_add"], ["MSFT"])
        self.assertEqual(change["limits"], {"max_position_pct": "0.2", "max_orders_per_day": 5})
        self.assertEqual(change["tools_add"], ["memo_read"])

    def test_a_change_that_repeats_the_parent_is_not_an_experiment(self):
        cases = [
            {"model.profile": self.parent.model.profile},
            {"model.reasoning_effort": self.parent.model.reasoning_effort},
            {"cadence.sessions": list(self.parent.cadence.sessions)},
            {"memory_limit": self.parent.memory_limit},
            {"tools_add": list(self.parent.tools)[:1]},
            {"instruments.allow_add": ["AAPL"]},
            {"limits": {"max_orders_per_day": self.parent.limits.max_orders_per_day}},
        ]
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(LabError):
                    validate_change(change, self.parent)

    def test_anything_outside_the_vocabulary_or_the_bounds_is_refused_not_clamped(self):
        bad = [
            ({}, "non-empty"),
            ({"mandate": "trade everything"}, "unknown change keys"),
            ({"model.profile": "gpt-9"}, "not a priced profile"),
            ({"model.reasoning_effort": "max"}, "not allowed"),
            ({"cadence.sessions": ["25:00"]}, "malformed"),
            ({"cadence.sessions": []}, "1 to 8"),
            ({"memory_limit": 500}, "between 20 and 120"),
            ({"memory_limit": "40"}, "integer"),
            ({"tools_add": ["shell"]}, "unknown tools"),
            ({"limits": {"max_position_pct": "0.9"}}, "between 0.01 and 0.50"),
            ({"limits": {"max_orders_per_day": 99}}, "between 1 and 40"),
            ({"limits": {"max_gross_pct": "2"}}, "outside the vocabulary"),
            ({"playbook_note": "<b>bold</b>"}, "markup"),
            ({"playbook_note": "x" * 2000}, "1 to 1500"),
        ]
        for change, message in bad:
            with self.subTest(change=change):
                with self.assertRaises(LabError) as caught:
                    validate_change(change, self.parent)
                self.assertIn(message, str(caught.exception))

    def test_symbols_cannot_be_added_to_a_desk_that_allows_everything(self):
        with self.assertRaises(LabError) as caught:
            validate_change({"instruments.allow_add": ["MSFT"]}, manifest())
        self.assertIn("every symbol", str(caught.exception))

    def test_apply_change_is_the_vocabulary_made_concrete(self):
        data, note = apply_change(
            self.parent.to_dict(),
            {"model.profile": "kimi_flex", "limits": {"max_orders_per_day": 5, "max_position_pct": "0.2"},
             "tools_add": ["memo_read"], "playbook_note": "House view."},
        )
        self.assertEqual(data["model"]["profile"], "kimi_flex")
        self.assertEqual(data["limits"]["max_orders_per_day"], 5)
        self.assertEqual(data["limits"]["max_position_pct"], "0.2")
        self.assertIn("memo_read", data["tools"])
        self.assertEqual(note, "House view.")
        DeskManifest.from_dict(data)  # still a valid manifest

    def test_proposals_are_read_out_of_prose_and_fences(self):
        rows = parse_proposals(reply({"hypothesis": "Less is more.", "change": {"memory_limit": 20}}))
        self.assertEqual(rows, [{"hypothesis": "Less is more.", "change": {"memory_limit": 20}}])
        self.assertEqual(parse_proposals("no json here"), [])
        self.assertEqual(parse_proposals('{"experiments": [{"change": {}}]}'), [])
        self.assertEqual(parse_proposals('{"experiments": []}'), [])

    def test_the_experiment_id_is_the_content(self):
        a = experiment_id("earnings", "h", {"memory_limit": 20}, "2026-09-15")
        b = experiment_id("earnings", "h", {"memory_limit": 20}, "2026-09-15")
        c = experiment_id("earnings", "h", {"memory_limit": 40}, "2026-09-15")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertRegex(a, r"^exp-[0-9a-f]{12}$")


class LabCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.desks = self.root / "desks"
        self.playbooks = self.root / "playbooks"
        self.desks.mkdir()
        self.playbooks.mkdir()
        self.log = EventLog(self.root / "events.sqlite")
        self.provider = FakeProvider()
        self.write_manifest("earnings-01", capital={"mode": "live", "usd": "1000"})
        self.allocate({"earnings-01": "1000"}, "2026-09-01T13:00:00.000Z")

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def write_manifest(self, desk_id, **overrides):
        data = copy.deepcopy(SAMPLE)
        data["id"] = desk_id
        data["playbook"] = f"playbooks/{desk_id}.md"
        data.update(overrides)
        DeskManifest.from_dict(data)
        (self.desks / f"{desk_id}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        (self.playbooks / f"{desk_id}.md").write_text(f"# {desk_id} playbook\n\nDrift.\n", encoding="utf-8")
        return data

    def allocate(self, allocations, at):
        self.log.append(
            "committee", "committee.allocation",
            {"allocations": {k: str(v) for k, v in allocations.items()}, "reasons": {}}, at=at,
        )

    def lab(self, **config):
        evolution = Evolution(
            self.log, self.desks, self.playbooks, provider=self.provider,
            config={"live_venues": ("alpaca", "kalshi"), "min_days": 3, "min_decisions": 2},
        )
        return Lab(self.log, evolution, provider=self.provider, config=config)

    def fill(self, desk, side, quantity, price, at):
        seq = self.log.latest_seq() + 1
        self.log.append(
            "broker:shadow", "broker.fill",
            {"fill_id": f"f{seq}", "order_id": f"o{seq}", "desk_id": desk,
             "instrument": {"asset_class": "equity", "symbol": "AAPL", "venue": "alpaca"},
             "side": side, "quantity": str(quantity), "price": str(price), "fee": "0", "at": at},
            at=at,
        )

    def record(self, desk, *, exit_price, days_from=1):
        """A short forward record: a buy, a close at `exit_price`, and a mark."""
        buy_at = f"2026-09-{days_from:02d}T14:00:00.000Z"
        sell_at = f"2026-09-{days_from + 2:02d}T15:00:00.000Z"
        self.fill(desk, "buy", "10", "100", buy_at)
        self.fill(desk, "sell", "10", exit_price, sell_at)
        self.log.append(
            f"ledger:{desk}", "ledger.mark",
            {"equity": "0", "cash": "0", "positions": [], "daily_pnl": "0", "as_of": "2026-09-30T20:00:00.000Z"},
            at="2026-09-30T20:00:00.000Z",
        )


class ProposalTests(LabCase):
    def test_a_valid_proposal_becomes_a_running_experiment_and_a_directed_variant(self):
        self.provider.replies = [
            reply({"hypothesis": "A tighter memory keeps the thesis honest.", "change": {"memory_limit": 20}}),
        ]
        lab = self.lab()
        actions = lab.propose(NIGHT)
        self.assertEqual([a["status"] for a in actions], ["running"])
        exp = actions[0]
        self.assertEqual(exp["family"], "earnings")
        self.assertEqual(exp["parent_id"], "earnings-01")
        self.assertEqual(exp["change"], {"memory_limit": 20})
        self.assertEqual(exp["variant_desk_id"], "earnings-01-2")
        self.assertEqual(exp["evaluate_after"], "2026-09-18T00:00:00.000Z")
        child = load_manifest(self.desks / "earnings-01-2.json")
        self.assertEqual(child.memory_limit, 20)
        self.assertEqual(child.capital_mode, "shadow")
        spawned = self.log.read(kind="evolution.spawned")[0].payload
        self.assertEqual(spawned["experiment_id"], exp["experiment_id"])
        self.assertEqual(spawned["mutation"]["change"], {"memory_limit": 20})
        self.assertEqual(spawned["mutation"]["memory_limit"], 20)
        # Two public records: proposed, then running; the ids say which is which.
        ids = [e.id for e in self.log.read(kind="lab.experiment")]
        self.assertEqual(ids, [f"{exp['experiment_id']}:proposed", f"{exp['experiment_id']}:running"])
        # The model was asked once, on a deterministic key, with the family's evidence.
        self.assertEqual(len(self.provider.calls), 2)  # the proposal and the child's playbook
        ask = self.provider.calls[0]
        self.assertEqual(ask["request_key"], "lab:earnings:2026-09-15")
        self.assertEqual(ask["desk_id"], "lab")
        self.assertIn("Family earnings, live desk", ask["items"][1]["content"])
        self.assertIn("Reply with JSON only", ask["items"][0]["content"])

    def test_an_invalid_proposal_is_withdrawn_in_public_with_the_reason(self):
        self.provider.replies = [
            reply({"hypothesis": "Go big.", "change": {"limits": {"max_position_pct": "0.95"}}}),
        ]
        actions = self.lab().propose(NIGHT)
        self.assertEqual([a["status"] for a in actions], ["withdrawn"])
        self.assertIn("between 0.01 and 0.50", actions[0]["reason"])
        self.assertEqual(self.log.read(kind="evolution.spawned"), [])
        event = self.log.read(kind="lab.experiment")[0]
        self.assertTrue(event.public)
        self.assertEqual(event.payload["change"], {"limits": {"max_position_pct": "0.95"}})

    def test_a_family_without_a_live_desk_is_left_alone(self):
        self.write_manifest("crypto-01", family="crypto", capital={"mode": "shadow", "usd": "500"})
        self.provider.replies = [reply({"hypothesis": "h", "change": {"memory_limit": 20}})]
        actions = self.lab().propose(NIGHT)
        self.assertEqual({a["family"] for a in actions}, {"earnings"})

    def test_caps_hold_per_family_and_per_day(self):
        self.provider.replies = [
            reply(
                {"hypothesis": "one", "change": {"memory_limit": 20}},
                {"hypothesis": "two", "change": {"memory_limit": 60}},
                {"hypothesis": "three", "change": {"memory_limit": 80}},
            ),
        ]
        lab = self.lab(max_experiments_per_family=2)
        actions = lab.propose(NIGHT)
        self.assertEqual(len(actions), 2)
        self.assertEqual(len(lab.running("earnings")), 2)
        # The next night the family is at its running ceiling: nothing is asked for.
        self.provider.replies = [reply({"hypothesis": "four", "change": {"memory_limit": 100}})]
        self.assertEqual(lab.propose("2026-09-16T00:00:00.000Z"), [])
        self.assertEqual(lab.proposed_on("2026-09-15"), 2)

    def test_a_model_failure_is_an_alert_and_no_experiment(self):
        self.provider.replies = [RuntimeError("provider_transport_timeout")]
        self.assertEqual(self.lab().propose(NIGHT), [])
        alerts = self.log.read(kind="ops.alert")
        self.assertEqual(len(alerts), 1)
        self.assertIn("lab proposals for earnings not written", alerts[0].payload["text"])

    def test_a_night_is_paid_for_once(self):
        self.provider.replies = [reply({"hypothesis": "h", "change": {"memory_limit": 20}})]
        lab = self.lab()
        lab.propose(NIGHT)
        self.provider.replies = [reply({"hypothesis": "h", "change": {"memory_limit": 20}})]
        lab.propose(NIGHT)
        self.assertEqual(len([e for e in self.log.read(kind="lab.experiment") if e.payload["status"] == "running"]), 1)

    def test_the_recent_list_is_the_checkpoint_shape(self):
        self.provider.replies = [reply({"hypothesis": "h", "change": {"memory_limit": 20}})]
        lab = self.lab()
        lab.propose(NIGHT)
        rows = lab.recent()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            sorted(rows[0]),
            ["change", "evaluate_after", "experiment_id", "family", "hypothesis", "parent_id",
             "proposed_at", "status", "variant_desk_id"],
        )


class VerdictTests(LabCase):
    def start(self, change=None):
        self.provider.replies = [reply({"hypothesis": "h", "change": change or {"memory_limit": 20}})]
        lab = self.lab()
        [exp] = lab.propose(NIGHT)
        return lab, exp

    def test_nothing_is_judged_before_its_time_or_without_evidence(self):
        lab, exp = self.start()
        self.assertEqual(lab.evaluate("2026-09-16T00:00:00.000Z"), [])
        # Due, but the variant has no decisions and the grace period is running.
        self.assertEqual(lab.evaluate("2026-09-19T00:00:00.000Z"), [])
        # After the grace period an unproven variant is rejected and retired.
        [verdict] = lab.evaluate("2026-09-26T00:00:00.000Z")
        self.assertEqual(verdict["status"], "rejected")
        self.assertIn("decisions", verdict["reason"])
        self.assertEqual(self.log.read(kind="evolution.retired")[0].payload["desk_id"], "earnings-01-2")
        self.assertEqual(lab.experiments()[exp["experiment_id"]]["status"], "rejected")

    def test_a_variant_that_beats_its_parent_is_adopted_into_the_genome_and_inherited(self):
        lab, exp = self.start()
        self.allocate({"earnings-01": "1000", "earnings-01-2": "1000"}, "2026-09-15T01:00:00.000Z")
        self.record("earnings-01", exit_price="99", days_from=16)
        self.record("earnings-01-2", exit_price="130", days_from=16)
        [verdict] = lab.evaluate(LATER)
        self.assertEqual(verdict["status"], "adopted")
        self.assertIn("cost-adjusted excess", verdict["reason"])
        self.assertEqual(sorted(verdict["evidence"]), ["parent", "variant"])
        event = self.log.read(kind="lab.verdict")[0]
        self.assertEqual(event.id, f"{exp['experiment_id']}:verdict")
        genome = json.loads((self.desks / "genomes" / "earnings.json").read_text())
        self.assertEqual(genome["changes"][0]["change"], {"memory_limit": 20})
        self.assertEqual(genome["changes"][0]["experiment_id"], exp["experiment_id"])
        # The live desk was never edited; every future child carries the change.
        self.assertEqual(load_manifest(self.desks / "earnings-01.json").memory_limit, manifest().memory_limit)
        parent = load_manifest(self.desks / "earnings-01.json")
        data, mutation = lab.evolution.mutate(parent, "earnings-01-9", 9)
        self.assertEqual(data["memory_limit"], 20)
        self.assertEqual(mutation["genome"], [exp["experiment_id"]])
        # A genome file is not a manifest: the roster still loads.
        self.assertEqual(sorted(lab.evolution.manifests()), ["earnings-01", "earnings-01-2"])
        self.assertEqual(lab.evaluate(LATER), [], "a verdict is final")

    def test_a_variant_that_loses_is_rejected_and_retired(self):
        lab, exp = self.start()
        self.allocate({"earnings-01": "1000", "earnings-01-2": "1000"}, "2026-09-15T01:00:00.000Z")
        self.record("earnings-01", exit_price="120", days_from=16)
        self.record("earnings-01-2", exit_price="90", days_from=16)
        [verdict] = lab.evaluate(LATER)
        self.assertEqual(verdict["status"], "rejected")
        self.assertEqual(self.log.read(kind="evolution.retired")[0].payload["desk_id"], "earnings-01-2")
        self.assertFalse((self.desks / "genomes" / "earnings.json").exists())

    def test_an_adopted_playbook_note_lands_in_every_future_childs_playbook(self):
        lab, exp = self.start({"playbook_note": "Write the counter-argument first."})
        self.allocate({"earnings-01": "1000", "earnings-01-2": "1000"}, "2026-09-15T01:00:00.000Z")
        self.record("earnings-01", exit_price="99", days_from=16)
        self.record("earnings-01-2", exit_price="130", days_from=16)
        lab.evaluate(LATER)
        self.provider.replies = ["Fresh playbook.\n"]
        parent = load_manifest(self.desks / "earnings-01.json")
        spawned = lab.evolution.spawn(parent, parent, LATER)
        body = (self.playbooks / f"{spawned['desk_id']}.md").read_text()
        self.assertIn("## House view", body)
        self.assertIn("- Write the counter-argument first.", body)
        self.assertNotIn("playbook_notes", spawned["mutation"])


if __name__ == "__main__":
    unittest.main()
