"""What the swarm lets reach the public site (league/swarm/public.py, researcher._public_note, sitefeed): never code,
never a parameter, never a number from a result. The data licenses forbid publishing anything fitted to the quotes,
and the page and the repository are public. The swarm strips; the publisher masks again."""

from __future__ import annotations

import copy
import re
import tempfile
import unittest
from pathlib import Path

from league import publish
from league.ledger import Entry
from league.swarm import public, settings as S, sitefeed
from league.swarm.models import ModelRouter
from league.swarm.researcher import Researcher
from league.swarm.seeds import SEEDS, family_spec, program_for
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, provider, result

LEAKY = [
    "Set PARAMS short_delta=16, wing_width=5, entry_minute=35, iv_rank_min=70, credit_pct=30 on SPY.",
    'PARAMS = {"short_delta": 16, "stop_mult": 2, "take_profit_pct": 50}',
    "if ctx.minute >= 35 and chain.iv[atm] > 18: sell the condor.",
    "Raised cadence to 10 and entry_minute=35; take profit at 50%, stop at 200% of credit, hold 2 DTE. Train t 3.",
    "The vrp_min threshold of 1.3 works best.",
    "Selling at delta 16 with wings 5 wide made the most.",
]


def tape(kind, agent, payload):
    entry = Entry(seq=1, id="swarm:1", kind=kind, agent=agent, at="2026-09-26T12:00:00.000Z", public=True, payload=payload,
                  previous_hash="x", digest="y")
    return publish.to_events(entry)


WORDS = [
    "Moving the short leg to a twenty five delta and taking profit at half the credit lifted the score.",
    "I now enter only when implied vol rank is above sixty and exit at two thirds of max profit.",
    "Selling the put at point one eight delta beats point three.",
    "The rule: enter late.",
    "Wider wings (as the graveyard said) cost less.",
]


class NoteText(unittest.TestCase):
    def test_fitted_values_in_words_never_pass(self):
        for text in WORDS:
            self.assertIsNone(public.note_text(text), text)

    def test_the_model_is_told_its_notes_are_public(self):
        from league.swarm.researcher import ROLE, TOOLS

        self.assertIn("PUBLIC", ROLE)
        for tool in TOOLS:
            if tool["name"] == "gym_run":
                self.assertIn("PUBLIC", tool["parameters"]["properties"]["note"]["description"])
            if tool["name"] == "notebook":
                self.assertIn("PUBLIC", tool["description"])

    def test_code_params_and_numbers_never_pass(self):
        for text in LEAKY:
            out = public.note_text(text, param_names=("short_delta", "vrp_min", "wing_width", "cadence"))
            self.assertTrue(out is None or not re.search(r"[0-9=_{}\[\]()]", out), (text, out))
            self.assertFalse(out and "vrp" in out.lower(), out)

    def test_plain_words_pass(self):
        text = "Condors lost on trend days. Waiting for a quiet midday cut the losers. Next I will test the Friday expiry."
        self.assertEqual(public.note_text(text), text)

    def test_a_parameter_name_in_words_is_dropped(self):
        out = public.note_text("Raising the entry delta helped. The wing width barely mattered.", param_names=("entry_delta",))
        self.assertEqual(out, "The wing width barely mattered.")

    def test_news_keeps_words_and_drops_code_and_decimals(self):
        self.assertEqual(public.news_text("its trial-adjusted evidence fell below the line (deflated Sharpe probability 0.012)"),
                         "its trial-adjusted evidence fell below the line")
        self.assertEqual(public.news_text("no validation improvement in 30 revisions"), "no validation improvement in 30 revisions")
        self.assertIsNone(public.news_text("x = {'a': 1}"))


class NotesReachingTheTape(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.steps = []
        self.provider, self.sail = provider(self.root / "p.sqlite", lambda body: self.steps.pop(0) if self.steps else {"text": "ok"})
        self.addCleanup(self.provider.close)
        self.spec = next(s for s in SEEDS if s["id"] == "condor-vrp")
        self.fam = self.store.add_family(family_spec(self.spec), origin="seed")

        class Pool:
            def run(self, job, timeout=None, late=None):
                return result(job.name, roots=job.roots)

        self.r = Researcher(self.store, ModelRouter(self.store, self.provider, settings=self.settings), Pool(), self.settings,
                            clock=self.clock, starter=program_for, background=False)
        self.r.cycle(self.fam["id"])

    def test_a_leaky_note_never_becomes_a_public_row(self):
        for text in LEAKY:
            self.steps = [{"calls": [("notebook", {"action": "append", "text": text})]}, {"text": "ok"}]
            self.clock.advance(3600)
            self.store.set_state(self.fam["id"], public_note_cycle=-100)
            self.r.cycle(self.fam["id"])
        for event in self.store.events_after(0):
            if event["kind"] == "swarm.note":
                for row in tape("swarm.note", self.fam["id"], event["payload"]):
                    self.assertFalse(re.search(r"[0-9=_{}\[\]]", row["payload"]["text"]), row)
        self.assertEqual(self.store.notebook(self.fam["id"])[-1]["text"], LEAKY[-1], "the private notebook keeps it all")

    def test_a_program_parameter_named_in_a_note_is_dropped(self):
        self.steps = [{"calls": [("notebook", {"action": "append", "text": "The vrp min barely mattered. Quiet days paid."})]},
                      {"text": "ok"}]
        self.store.set_state(self.fam["id"], public_note_cycle=-100)
        self.r.cycle(self.fam["id"])
        [note] = [e for e in self.store.events_after(0) if e["kind"] == "swarm.note"]
        self.assertEqual(note["payload"]["text"], "Quiet days paid.")

    def test_site_mechanisms_are_news_text(self):
        self.store.add_family({"id": "leaky", "mechanism": "Sell when iv_rank_min=70 and short_delta = 0.16 because premium is rich.",
                               "structure": "iron_condor", "roots": ["SPY"]}, origin="architect")
        rows = {a["id"]: a for a in sitefeed.site_inputs(self.root)["agents"]}
        self.assertIsNone(rows["leaky"]["mechanism"])
        self.assertIn("iron condor", rows["condor-vrp"]["mechanism"])


if __name__ == "__main__":
    unittest.main()
