"""THE WHOLE AGENDA (LTCM v3, league/swarm/strategist.py with `strategist.writes` "agenda"): the strategist writes all of
the agenda once a day on its own round, under the rules fixed in code (the locked preamble retires), through the same
validator plus a rule that it names no family; a refusal keeps the agenda in force and leaves a receipt; the architect
reads the rules, then the agenda quoted. Synthetic families and lessons only."""

from __future__ import annotations

import json
import time
import unittest
from types import SimpleNamespace

from league.swarm.architect import (AGENDA_KEY, AGENDA_MAX, AGENDA_MODE, NO_AGENDA_YET, STRATEGIST_AGENDA_TITLE, Architect,
                                    rules_text)
from league.swarm.loop import Swarm
from league.swarm.models import ModelError
from league.swarm.strategist import (AGENDA_SYSTEM, DAILY_TRIES, KV_DAY, RECEIPT_KEY, RETRY_SECONDS, check_section)
from league.tests.test_swarm_strategist import CITES, CLEAN, LOCKED, FakeRouter, StrategistCase, quoted

AGENDA = ("(a) Put the index variance premium to work with centered XSP and SPY butterflies one to two sessions out, entered "
          "only when implied volatility is rich against realized; the refuted rows show that unconditional entries lose to the "
          "spread.\n"
          "(b) Post-event crush on the broad ETFs: defined-risk short premium opened after the release prints, never through it.\n"
          "(c) Stop proposing single-name directional singles; every such lineage died of drift.\n"
          "(d) Do not re-propose squeeze straddles on SPY.")


def answer(text=AGENDA, cites=CITES, **more):
    data = {"agenda": text, "evidence": "gap-revert-spy lost fading; the refuted rows lost to the spread.", "cites": cites}
    return {"text": json.dumps(data), "json": data, "route": "claude", "model": "claude-opus-5-5", "cost_usd": 0.31,
            "usage": {"input_tokens": 20000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 85000,
                      "output_tokens": 9000}, **more}


class Validator(unittest.TestCase):
    def test_the_whole_agenda_names_no_family_and_has_its_own_ceiling(self):
        known = frozenset(CITES) | {"lead-lag"}
        ok = check_section(AGENDA, max_chars=AGENDA_MAX, cites=CITES, known_ids=known, min_cites=3, names=True, cap=AGENDA_MAX)
        self.assertEqual(ok.reasons, [])
        named = check_section(AGENDA + "\n(e) Build on gap-revert-spy.", max_chars=AGENDA_MAX, cites=CITES, known_ids=known,
                              min_cites=3, names=True, cap=AGENDA_MAX)
        self.assertTrue(any(r.startswith("names:") and "gap-revert-spy" in r for r in named.reasons), named.reasons)
        self.assertTrue(check_section(AGENDA + "\n(e) Build on gap-revert-spy.", max_chars=1600, cites=CITES, known_ids=known,
                                      min_cites=3).ok, "the section may still name a row")
        compound = check_section(AGENDA + "\n(e) Pool lead-lag pairs across the broad ETFs.", max_chars=AGENDA_MAX, cites=CITES,
                                 known_ids=known, min_cites=3, names=True, cap=AGENDA_MAX)
        self.assertTrue(compound.ok, "a two-part id reads as an ordinary compound word")
        long = AGENDA + "\n" + "(e) Keep pooled index butterflies centered on the money each morning. " * 40
        self.assertGreater(len(long), 2000)
        self.assertLessEqual(len(long), AGENDA_MAX)
        self.assertTrue(check_section(long, max_chars=AGENDA_MAX, cites=CITES, known_ids=known, min_cites=3, names=True,
                                      cap=AGENDA_MAX).ok, "the whole agenda's ceiling is 4,000")
        self.assertFalse(check_section(long, max_chars=AGENDA_MAX, cites=CITES, known_ids=known, min_cites=3).ok,
                         "a section keeps its 2,000 ceiling")
        for bad in ("(e) Lower the DSR bar for index structures.", "(e) The 2025 results favour short-dated SPY verticals.",
                    "(e) Revisit the rebound family on QQQ.", "(e) Use $1 wide verticals on SPY."):
            self.assertFalse(check_section(AGENDA + "\n" + bad, max_chars=AGENDA_MAX, cites=CITES, known_ids=known, min_cites=3,
                                           names=True, cap=AGENDA_MAX).ok, bad)


class AgendaCase(StrategistCase):
    def setUp(self):
        super().setUp()
        self.settings["strategist"]["writes"] = AGENDA_MODE

    def receipts(self):
        return [e["payload"]["receipt"] for e in self.store.events_after(0) if e["kind"] == "swarm.strategist"]


class Schedule(AgendaCase):
    def test_once_an_agenda_day_on_its_own_clock_never_inside_the_pass(self):
        s = self.strategist(FakeRouter(answer()))
        self.assertFalse(s.in_pass())
        self.assertTrue(s.due(), "at once on the first run, at any hour")
        self.settings["architect"]["agenda_locked"] = ""
        self.assertTrue(s.due(), "the locked preamble is not needed")
        s.run()
        self.assertFalse(s.due(), "answered today")
        hour = int(time.gmtime(self.clock()).tm_hour)
        to_next = ((24 - hour + 3) % 24 or 24) * 3600 - int(self.clock()) % 3600
        self.clock.advance(to_next - 60)
        self.assertFalse(s.due(), "the agenda day turns at 03:00 UTC")
        self.clock.advance(120)
        self.assertTrue(s.due())
        self.settings["strategist"]["writes"] = "section"
        self.assertTrue(s.in_pass(), "the section rides the architect's pass as before")

    def test_a_run_no_model_answered_is_tried_again_after_an_hour_at_most_three_times_a_day(self):
        s = self.strategist(FakeRouter(raises=ModelError("no route")))
        s.run()
        self.assertEqual(self.store.get(KV_DAY)["tries"], 1)
        self.assertFalse(self.store.get(KV_DAY)["answered"])
        self.assertFalse(s.due())
        for _ in range(DAILY_TRIES - 1):
            self.clock.advance(RETRY_SECONDS)
            self.assertTrue(s.due())
            s.run()
        self.clock.advance(RETRY_SECONDS)
        self.assertEqual(self.store.get(KV_DAY)["tries"], DAILY_TRIES)
        self.assertFalse(s.due(), "tries spent: tomorrow")
        self.assertEqual({r["verdict"] for r in self.receipts()}, {"failed"})


class Runs(AgendaCase):
    def test_an_accepted_agenda_is_the_whole_agenda_under_the_rules(self):
        self.settings["architect"]["library"] = True
        router = FakeRouter(answer())
        out = self.strategist(router).run()
        self.assertTrue(out["accepted"], out.get("reasons"))
        call = router.calls[0]
        self.assertEqual(call["role"], "strategist")
        self.assertTrue(call["claude_system"].startswith(AGENDA_SYSTEM.split("{", 1)[0][:200]))
        packet = call["claude_user"]
        self.assertIn("THE RULES FIXED IN CODE", packet)
        self.assertIn(rules_text(self.settings), packet)
        self.assertIn("THE MECHANISM LIBRARY", packet)
        self.assertNotIn("THE LOCKED PREAMBLE", packet, "the preamble retires")
        self.assertIn("THE CURRENT AGENDA (the agenda yours replaces):\n" + LOCKED, packet,
                      "before the first: the agenda it replaces, as context")
        self.assertIn("Write THE RESEARCH AGENDA now: ONE JSON object with agenda, evidence and cites", packet)
        stored = self.store.get(AGENDA_KEY)
        self.assertEqual((stored["mode"], stored["text"], stored["model"]), (AGENDA_MODE, AGENDA, "claude-opus-5-5"))
        title, agenda = Architect(self.store, router, self.settings, clock=self.clock).agenda()
        self.assertEqual(title, STRATEGIST_AGENDA_TITLE)
        self.assertTrue(agenda.startswith(rules_text(self.settings)), "the rules fixed in code come first")
        self.assertTrue(agenda.endswith(quoted(AGENDA)), "the agenda, every line quoted")
        self.assertNotIn(LOCKED, agenda)
        receipt = self.store.get(RECEIPT_KEY)
        self.assertEqual((receipt["verdict"], receipt["agenda_in_force"], receipt["model"]),
                         ("accepted", stored["at"], "claude-opus-5-5"))
        self.assertEqual(out["receipt"], receipt)

    def test_a_refusal_keeps_yesterdays_agenda_and_is_a_receipt(self):
        self.strategist(FakeRouter(answer())).run()
        kept = self.store.get(AGENDA_KEY)
        self.clock.advance(86400)
        bad = AGENDA + "\n(e) Loosen the t threshold for pooled families."
        out = self.strategist(FakeRouter([answer(bad), answer(bad)])).run()
        self.assertFalse(out["accepted"])
        self.assertEqual(out["turns"], 2, "one repair turn with the reasons")
        self.assertEqual(self.store.get(AGENDA_KEY), kept, "yesterday's agenda stands")
        receipt = self.store.get(RECEIPT_KEY)
        self.assertEqual((receipt["verdict"], receipt["agenda_in_force"]), ("refused", kept["at"]))
        self.assertTrue(any(r.startswith("threshold:") for r in receipt["reasons"]), receipt["reasons"])
        self.assertTrue(self.store.get(KV_DAY)["answered"], "a refusal is an answer: no retry today")
        self.assertEqual([r["verdict"] for r in self.receipts()], ["accepted", "refused"])

    def test_a_named_family_is_refused_and_the_repair_asks_for_the_agenda(self):
        router = FakeRouter([answer(AGENDA + "\n(e) Build on gap-revert-spy."), answer()])
        out = self.strategist(router).run()
        self.assertTrue(out["accepted"])
        self.assertEqual(out["attempts"][0]["reasons"][0][:6], "names:")
        self.assertIn("Your agenda was:", router.calls[1]["claude_user"])
        self.assertIn("ONE JSON object with agenda, evidence and cites", router.calls[1]["claude_user"])

    def test_before_the_first_agenda_the_architect_reads_the_rules_alone(self):
        self.store.put(AGENDA_KEY, {"text": CLEAN, "at": "2026-10-01T00:00:00Z", "run": 1})  # a section from before the switch
        title, agenda = Architect(self.store, None, self.settings, clock=self.clock).agenda()
        self.assertEqual((title, agenda), (STRATEGIST_AGENDA_TITLE, f"{rules_text(self.settings)}\n\n{NO_AGENDA_YET}"))
        self.assertNotIn("MECHANISM LIBRARY", agenda, "the library's rules only while the library is on")
        self.settings["strategist"]["writes"] = "section"
        self.store.put(AGENDA_KEY, {"text": AGENDA, "at": "2026-10-02T03:00:00Z", "run": 2, "mode": AGENDA_MODE})
        _, agenda = Architect(self.store, None, self.settings, clock=self.clock).agenda()
        self.assertNotIn(AGENDA.splitlines()[0], agenda, "back on the section: a whole agenda is not read as a section")


class Sentinels(AgendaCase):
    def test_no_validation_figure_reaches_the_whole_agendas_packet_its_rules_or_the_library(self):
        from league.swarm.mechanisms import library_text
        from league.tests.test_swarm_d2a_sentinel import CHECKS, DSR, LITERALS, MEAN, PATTERN, PNL, SHARPE, T, TRADES

        self.settings["architect"]["library"] = True
        numbers = {"t": T, "mean": MEAN, "dsr": DSR, "trades": TRADES, "pnl": PNL, "sharpe": SHARPE}
        fam = self.store.add_family({"id": "alive-sentinel", "mechanism": "An alive idea about index variance sold through "
                                     "butterflies on calm sessions.", "structure": "long_butterfly", "roots": ["SPY"]},
                                    origin="architect")
        self.store.set_state(fam["id"], validation_line={"passed": False, "checks": CHECKS, "numbers": numbers},
                             validation_numbers=numbers, validation_version=1)
        self.store.put("leaderboard", {"board": [{"family": fam["id"], "band": "gym", "structure": "long_butterfly",
                                                  "roots": ["SPY"], "validation": numbers, "share": 1.0}]})
        router = FakeRouter(answer())
        s = self.strategist(router)
        s.run()
        architect = Architect(self.store, router, self.settings, clock=self.clock)
        texts = {"packet": s.packet(sample=True), "packet (digest)": s.packet(), "system": s.system(),
                 "architect prompt": architect.prompt(), "library": library_text(), "rules": rules_text(self.settings)}
        for where, text in texts.items():
            for literal in LITERALS:
                self.assertNotIn(literal, text, where)
            found = PATTERN.search(text)
            self.assertIsNone(found, f"{where} shows a Validation figure ({found.group(0) if found else ''}): D2a")
        self.assertIn("THE MECHANISM LIBRARY", texts["architect prompt"])


class Wiring(AgendaCase):
    def test_the_pass_no_longer_runs_it(self):
        seen = []
        architect = SimpleNamespace(want=lambda: 3, run=lambda paired=False: seen.append(("architect", paired)) or {"born": []})
        strategist = SimpleNamespace(in_pass=lambda: False, due=lambda: True, run=lambda **kw: seen.append(("strategist",)))
        out = Swarm.architect_pass(SimpleNamespace(architect=architect, strategist=strategist, clock=self.clock))
        self.assertEqual(seen, [("architect", False)])
        self.assertNotIn("strategist", out)

    def test_the_loop_runs_its_own_round(self):
        from league.tests.test_swarm_loop import LoopCase

        class Case(LoopCase):
            def runTest(inner):
                path = inner.root / "swarm.json"
                path.write_text(json.dumps({**json.loads(path.read_text()), "strategist": {"writes": "agenda"}}))
                sw = inner.swarm()
                calls = []
                sw.strategist_pass = lambda: calls.append(1) or {}
                sw.step()
                for t in list(sw.rounds.values()):
                    t.join(30)
                inner.assertEqual(calls, [1])
                inner.assertIn("strategist", sw.rounds)

        result = unittest.TestResult()
        Case().run(result)
        self.assertEqual((result.errors, result.failures), ([], []))


if __name__ == "__main__":
    unittest.main()
