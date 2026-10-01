"""R11b (Sept 29, 2026): the strategist's corrections land and births have a class cap (R11-2), per-role Claude effort
and the architect's truncation salvage (R11-3), the bandit exploits only positive evidence (R11-5), and the Gym's
zero-trade probe (R11-6)."""

from __future__ import annotations

import json
import random

from league.swarm import evidence as E
from league.swarm.architect import SALVAGE_MIN, Architect, salvage_families
from league.swarm.models import ModelRouter
from league.swarm.pool import PoolError
from league.swarm.researcher import ALREADY_RUN
from league.swarm.strategist import check_section, mask_ids, overflow_only, target_chars, trim_section
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import result
from league.tests.test_claude import message
from league.tests.test_frontier import FakeOpener
from league.tests.test_swarm_graveyard_digest import RouteCase
from league.tests.test_swarm_researcher import ResearcherCase
from league.tests.test_swarm_rounds import RoundCase
from league.tests.test_swarm_strategist import CITES, CLEAN, FakeRouter, StrategistCase, reply

ID = "letf-rebalance-notional-giveback"


def verdict(text, cites=CITES, known=frozenset(CITES), max_chars=1600):
    return check_section(text, max_chars=max_chars, cites=cites, known_ids=known, min_cites=3)


# ------------------------------------------------------------------------------------------------------------------ R11-2
class ValidatorMasksKnownIds(StrategistCase):
    def test_a_known_ids_own_words_never_void_a_section(self):
        known = frozenset(CITES) | {ID}
        text = CLEAN + f"\n(e) Stop proposing LETF flow puts: {ID} showed the rebalance edge is the index's own move."
        self.assertTrue(verdict(text, known=known).ok, verdict(text, known=known).reasons)
        self.assertEqual(verdict(text, known=known).text, text, "the section keeps the id as written")
        unknown = verdict(text)  # the same words, the id not a real row: its "notional" is read as written
        self.assertIn("money", [r.split(":")[0] for r in unknown.reasons])
        worse = verdict(CLEAN + f"\n(e) Relax the t threshold for {ID} and its siblings.", known=known)
        self.assertTrue(any(r.startswith("threshold:") for r in worse.reasons), "the words around an id still count")
        self.assertEqual(mask_ids(f"{ID}, notional, gap-revert-spy and budget", {ID, "budget"}),
                         "ROW, notional, gap-revert-spy and budget", "only hyphenated known ids are names")

    def test_the_prompt_aims_at_85_percent_of_the_cap(self):
        self.assertEqual(target_chars(1600), 1350)
        self.assertEqual(target_chars(2000), 1700)
        s = self.strategist(FakeRouter(reply()))
        self.assertIn("(at most 1,600 characters; about 1,350 is right)", s.system())


def over(n):
    """CLEAN, then lettered lines until the section is about `n` characters."""
    text, i = CLEAN, 0
    while len(text) < n:
        text += f"\n({chr(ord('e') + i % 20)}) Pool debit verticals on SPY and QQQ through the session after a gap that holds."
        i += 1
    return text


class ShapeOnlyOverflowIsTrimmed(StrategistCase):
    def test_a_section_up_to_15_percent_over_is_cut_at_a_sentence_end_and_accepted(self):
        text = over(1700)
        self.assertTrue(1600 < len(text) <= 1840)
        first = verdict(text)
        self.assertTrue(overflow_only(first.reasons), first.reasons)
        router = FakeRouter(reply(text))
        out = self.strategist(router).run()
        self.assertTrue(out["accepted"], out.get("reasons"))
        self.assertEqual((out["turns"], len(router.calls)), (1, 1), "no repair turn paid for")
        self.assertLessEqual(out["trimmed"]["to"], 1600)
        self.assertEqual(out["trimmed"]["from"], len(text))
        kept = self.store.get("architect_agenda_section")["text"]
        self.assertTrue(text.startswith(kept) and kept.endswith("holds."), "cut at the last sentence end inside the cap")

    def test_past_15_percent_or_with_another_reason_it_is_not_trimmed(self):
        self.assertIsNone(trim_section(over(1900), 1600))
        router = FakeRouter([reply(over(1900)), reply()])
        out = self.strategist(router).run()
        self.assertEqual((out["accepted"], out["turns"]), (True, 2), "rejected, then repaired")
        self.assertNotIn("trimmed", out)
        bad = over(1700) + "\n(z) Loosen the t threshold for pooled families."
        self.assertFalse(overflow_only(verdict(bad).reasons))
        self.clock.advance(4 * 3600)
        out = self.strategist(FakeRouter(reply(bad))).run()
        self.assertFalse(out["accepted"])
        self.assertNotIn("trimmed", out)


def proposal(i, structure="debit_vertical", roots=("SPY",)):
    return {"slug": f"idea-{i}", "mechanism": f"Mechanism number {i}: dealers rebalance and the move reverts within the day.",
            "structure": structure, "roots": list(roots), "dte": [0, 5], "rejection": "no reversion", "sketch": "enter late"}


class ClassCap(RoundCase):
    def test_births_past_the_class_cap_are_refused_and_the_request_names_the_class(self):
        for i in range(12):
            self.store.add_family({"id": f"straddle-{i}", "mechanism": f"Straddle idea {i} on a quiet ETF before its data day.",
                                   "structure": "long_straddle", "roots": ["QQQ" if i % 2 else "SPY"]}, origin="architect")
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.assertEqual(a.full_classes(), {"long_straddle x etf": 12})
        self.assertIn('FULL MECHANISM CLASSES', a.prompt())
        self.assertIn('{"long_straddle x etf": 12}', a.prompt())
        born = a.admit([proposal(1, "long_straddle", ("IWM",)), proposal(2), proposal(3, "long_straddle", ("SPXW",))])
        self.assertEqual(born, ["idea-2", "idea-3"], "an index straddle is another class")
        self.assertEqual(a.capped, {"long_straddle x etf": 1})
        self.settings["architect"]["max_alive_per_class"] = 0
        self.assertEqual(Architect(self.store, self.router, self.settings, clock=self.clock).admit(
            [proposal(4, "long_straddle", ("IWM",))]), ["idea-4"], "0 turns the cap off")
        self.assertNotIn("FULL MECHANISM CLASSES", Architect(self.store, self.router, self.settings, clock=self.clock).prompt())

    def test_the_cap_counts_births_of_the_same_pass(self):
        self.settings["architect"]["max_alive_per_class"] = 2
        a = Architect(self.store, self.router, self.settings, clock=self.clock)
        born = a.admit([proposal(i) for i in range(4)])
        self.assertEqual(born, ["idea-0", "idea-1"])
        self.assertEqual(a.capped, {"debit_vertical x etf": 2})


# ------------------------------------------------------------------------------------------------------------------ R11-3
class RoleEffort(RoundCase):
    def test_a_roles_effort_applies_when_the_caller_names_none(self):
        self.settings["claude"]["role_effort"] = {"architect": "medium", "review": "turbo"}
        router = ModelRouter(self.store, self.provider, settings=self.settings)

        def effort(**kw):
            return router.claude_request("system", "user", **kw)[0]["output_config"]["effort"]

        self.assertEqual(effort(role="architect"), "medium")
        self.assertEqual(effort(role="architect", effort="low"), "low", "the caller's effort wins")
        self.assertEqual(effort(role="audit"), "high", "no entry: claude.effort (the gate keeps high)")
        self.assertEqual(effort(role="review"), "high", "a typo is never the call's effort")
        self.settings["claude"]["role_effort"] = None
        self.assertEqual(effort(role="architect"), "high")


class Salvage(RouteCase):
    def families(self, n, start=0):
        return [proposal(start + i, roots=(("SPY", "QQQ", "IWM")[i % 3],)) for i in range(n)]

    def cut(self, n):
        """An answer cut inside its (n+1)th family: n complete."""
        text = json.dumps({"families": self.families(n + 1)})
        return message(text[: text.rfind('"sketch"')], stop="max_tokens", cost="0.31")

    def test_the_complete_families_of_a_cut_answer_are_born_and_nothing_falls_to_sail(self):
        opener = FakeOpener(self.cut(4))
        out = self.architect(self.router(opener)).run()
        self.assertEqual(len(out["born"]), 4)
        self.assertEqual(out["truncated"], {"salvaged": 4, "born": 4})
        self.assertEqual((self.sail_calls, len(opener.calls)), ([], 1), "no Kimi-K3 refill, no retry")

    def test_fewer_than_three_buy_one_medium_retry_on_claude(self):
        opener = FakeOpener(self.cut(1), self.answer(self.families(2, start=10)))
        out = self.architect(self.router(opener)).run()
        self.assertEqual(len(out["born"]), 3)
        retry = out["truncated"]["retry"]
        self.assertEqual((retry["born"], retry["effort"], retry["route"], retry["truncated"]), (2, "medium", "claude", False))
        self.assertEqual(opener.body()["output_config"]["effort"], "medium")
        self.assertEqual(self.sail_calls, [])
        self.assertLess(1, SALVAGE_MIN)

    def test_a_retry_claude_has_no_line_for_leaves_the_pass_and_never_asks_sail(self):
        router = self.router(FakeOpener(self.cut(0)))
        real, seen = router._claude_admit, []

        def admit(**kw):
            seen.append(kw["key"])
            if len(seen) > 1:
                kw["errors"].append("claude: the architect line for today has no room")
                return None, "line"
            return real(**kw)

        router._claude_admit = admit
        out = self.architect(router).run()
        self.assertEqual(out["born"], [])
        self.assertEqual(out["truncated"]["retry"]["kind"], "line")
        self.assertTrue(seen[1].endswith(":salvage"))
        self.assertEqual(self.sail_calls, [], "never a full refill on Sail after a cut")

    def test_salvage_reads_only_complete_objects(self):
        self.assertEqual(salvage_families('{"families": [{"a": 1}, {"b": [1, {"c": 2}]}, {"d": "cut'), [{"a": 1}, {"b": [1, {"c": 2}]}])
        self.assertEqual(salvage_families('```json\n{"families": [\n {"a": 1},\n'), [{"a": 1}])
        self.assertEqual(salvage_families("thinking about families"), [])


# ------------------------------------------------------------------------------------------------------------------ R11-5
class ExploitPool(RoundCase):
    def old(self, fid, mean, t):
        return {"id": fid, "validations": 3, "mean": mean, "t": t}

    def test_only_positive_old_families_are_exploited_each_at_most_15_percent(self):
        fams = [self.old("pos", 0.02, 0.16), self.old("neg1", -0.01, -0.53), self.old("neg2", -0.03, -1.95),
                self.old("neg3", -0.02, -1.67)] + [{"id": f"new{i}", "validations": 0} for i in range(60)]
        shares = E.thompson(fams, rng=random.Random(1))
        self.assertAlmostEqual(sum(shares.values()), 1.0)
        self.assertAlmostEqual(shares["pos"], 0.15, msg="Sept 29: the four old families held 75%")
        self.assertLess(max(shares[f] for f in ("neg1", "neg2", "neg3")), 0.05, "a negative mean explores with the new")
        legacy = E.thompson(fams, rng=random.Random(1), exploit_per_positive=None)
        self.assertAlmostEqual(legacy["pos"], 0.75, msg="None: the explore share alone")

    def test_the_explore_floor_and_the_edges(self):
        fams = [self.old(f"p{i}", 0.01 * (i + 1), 1.0) for i in range(7)] + [{"id": "new", "validations": 0}]
        shares = E.thompson(fams, rng=random.Random(2))
        self.assertAlmostEqual(shares["new"], 0.25, msg="seven positive: 1 - 1.05 < 0.25, the floor holds")
        only_negative = [self.old("n", -0.01, -1.0), {"id": "new", "validations": 0}]
        self.assertAlmostEqual(sum(E.thompson(only_negative, rng=random.Random(3)).values()), 1.0)
        self.assertEqual(E.thompson([self.old("p", 0.02, 2.0)], rng=random.Random(4)), {"p": 1.0})

    def test_the_tournament_reads_its_setting(self):
        for fid, mean in (("pos", 0.02), ("neg", -0.02)):
            self.family(fid)
            self.store.update_family(fid, validations=3)
            self.store.set_state(fid, validation_numbers={"mean": mean, "t": 1.0 if mean > 0 else -1.0})
        self.family("new")
        self.settings["allocation"] = {"mode": "bandit"}  # R11-5's bandit (Release B's default is the value allocation)
        t = Tournament(self.store, self.pool, self.settings, rng=random.Random(5))
        self.assertAlmostEqual(t.allocate(self.store.families(alive=True))["pos"], 0.15)
        self.settings["tournament"]["exploit_per_positive"] = None
        self.assertAlmostEqual(t.allocate(self.store.families(alive=True))["pos"], 0.75)


# ------------------------------------------------------------------------------------------------------------------ R11-6
class ZeroTradeProbe(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.settings["researcher"]["probe_year"] = 2022
        self.fid = self.fam["id"]
        self.probe_trades = 0
        self.pool.answer = lambda job: result(job.name, roots=job.roots, trades=self.probe_trades if job.purpose == "probe" else 150)

    def run_(self, **args):
        out: dict = {"tool_calls": 0}
        view = self.researcher()._gym_run(self.store.family(self.fid), {"code": self.code, **args}, out, author="synthetic")
        return view, out

    def rows(self, window):
        return self.store._all("SELECT * FROM runs WHERE family=? AND window=?", (self.fid, window))

    def test_a_probe_with_no_trade_is_the_answer_and_one_trial(self):
        view, out = self.run_()
        [job] = self.pool.jobs
        self.assertEqual((job.purpose, job.roots, job.start, job.end, job.window), ("probe", ("SPY",), "2022-01-01", "2022-12-31",
                                                                                     "train"))
        self.assertEqual(view["status"], "disqualified")
        self.assertEqual(view["reason"], "disqualified: no trades in the probe year (2022 on SPY)")
        self.assertIn("full=true", view["next"])
        self.assertEqual((out["trials"], out["run_id"], out["probe"]["skipped_full"]), (1, view["run_id"], True))
        self.assertEqual((len(self.rows("probe")), len(self.rows("train"))), (1, 0), "never a Train row: no score reads it")
        fam = self.store.family(self.fid)
        self.assertEqual((fam["trials"], fam["best_train"]), (1, None))
        again, out = self.run_()
        self.assertEqual((again["already_run"], out["stored"], len(self.pool.jobs)), (ALREADY_RUN, 1, 1), "no second job")
        self.assertEqual(self.store.family(self.fid)["trials"], 1, "no trial")

    def test_full_true_a_trading_probe_1_5x_and_off_run_the_whole_of_train(self):
        view, out = self.run_(full=True)
        self.assertEqual([j.purpose for j in self.pool.jobs], ["train"])
        self.assertEqual((view["status"], out["probe"]), ("ok", {"skipped": "full=true"}))
        self.probe_trades = 12
        self.pool.jobs.clear()
        view, out = self.run_(params={"vrp_min": 1.3})
        self.assertEqual([j.purpose for j in self.pool.jobs], ["probe", "train"])
        self.assertEqual((view["status"], out["probe"]["trades"], out["trials"]), ("ok", 12, 1), "the probe is not a trial then")
        self.assertEqual(self.rows("probe"), [])
        self.pool.jobs.clear()
        self.run_(params={"vrp_min": 1.4}, stress=1.5)
        self.assertEqual([j.purpose for j in self.pool.jobs], ["train"], "a 1.5x run is never probed")
        self.pool.jobs.clear()
        self.run_(params={"vrp_min": 1.4})
        self.assertEqual([j.purpose for j in self.pool.jobs], ["train"], "a version that already ran (at 1.5x) is not new")
        self.settings["researcher"]["probe_year"] = None
        self.pool.jobs.clear()
        self.run_(params={"vrp_min": 1.6})
        self.assertEqual([j.purpose for j in self.pool.jobs], ["train"], "off by default")
        self.settings["researcher"]["probe_year"] = 2019
        self.pool.jobs.clear()
        self.run_(params={"vrp_min": 1.7})
        self.assertEqual([j.purpose for j in self.pool.jobs], ["train"], "a year outside the running span is off")

    def test_a_probe_the_gym_cannot_answer_says_nothing(self):
        real = self.pool.run

        def run(job, timeout=None, late=None):
            if job.purpose == "probe":
                self.pool.jobs.append(job)
                raise PoolError("the Gym did not answer within 300 s")
            return real(job, timeout=timeout, late=late)

        self.pool.run = run
        view, out = self.run_()
        self.assertEqual(view["status"], "ok")
        self.assertIn("did not answer", out["probe"]["error"])
        self.assertEqual([j.purpose for j in self.pool.jobs], ["probe", "train"])

    def test_a_queued_run_that_stops_at_its_probe_says_so(self):
        self.researcher().cycle(self.fid)  # the starter's probe: no trade
        self.steps = [{"calls": [("gym_run", {"params": {"vrp_min": 1.3}})]}, {"calls": [("gym_run", {"params": {"vrp_min": 1.5}})]}]
        self.researcher().cycle(self.fid)  # a probe that made no trade, then a run queued for the next cycle
        self.steps = [{"calls": [("gym_run", {"hold": True, "note": "Rethinking the entry."})]}]
        out = self.researcher().cycle(self.fid)  # the queued run opens this cycle
        self.assertNotIn("error", out)
        said = [i["content"] for i in self.store.convo(self.fid)[0][-1]["items"] if i.get("role") == "user"]
        self.assertTrue(any("made no trade in its probe year" in s for s in said), said[:1])
