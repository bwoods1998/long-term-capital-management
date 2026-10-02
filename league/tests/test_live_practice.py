"""The live practice league (Sept 29, 2026): every alive Gym-band family with a validated version, or an eligible Train
version, trades live shadow under two caps (instances and distinct roots), sheds its Train tail under sustained pressure,
keeps an honest private record of its practice (realized P&L, forced closes apart, open positions at the mark, drawdown,
coverage), never sends a real order and never writes a forward row; and the forward embargo holds a Sized move until the
forward record after the version was written meets Sized on its own. With the fakes of `live_fakes` (the venue's shapes,
invented numbers), the in-process decider and, where it says so, the swarm's real store."""

import datetime as dt
import json
import random
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from league.tests.test_live_step import HAVE, LiveCase
from league.tests.evaluator_fakes import band_proof, seed_current_run

if HAVE:
    from league.live.decider import BudgetSpent, InlineDecider
    from league.live.families import MemoryFamilies, SwarmFamilies
    from league.live.observe import ObserveStore, practice_summary
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

TUESDAY = MONDAY + dt.timedelta(days=1)


def code_on(root):
    return VERTICAL.replace('"SPY"', f'"{root}"')


def validated(name, *, t=1.0, version=1, roots=("SPY",), params=None):
    return {"family": name, "version": version, "code": code_on(roots[0]), "params": dict(params or {"hold": 600}),
            "structure": "debit_vertical", "roots": list(roots), "needs_roots": list(roots), "run_sha": f"sha-{name}-{version}",
            "tier": "validated", "validation_t": t, "validated_version": version, "lineage": f"{name}-line"}


def trained(name, *, best=1.0, version=1, roots=("SPY",), params=None):
    return {"family": name, "version": version, "code": code_on(roots[0]), "params": dict(params or {"hold": 600}),
            "structure": "debit_vertical", "roots": list(roots), "needs_roots": list(roots), "run_sha": f"sha-{name}-{version}",
            "tier": "train", "best_train": best, "validation_t": None, "validated_version": None, "lineage": f"{name}-line"}


class Pressable(InlineDecider if HAVE else object):
    """The observe child: its batch is skipped (the minute's budget spent) while `pressed`."""

    def __init__(self):
        super().__init__()
        self.pressed = False

    def decide(self, *args, **kwargs):
        if self.pressed:
            raise BudgetSpent("the decider's minute budget is exhausted")
        return super().decide(*args, **kwargs)


@unittest.skipUnless(HAVE, "numpy not installed")
class PracticeCase(LiveCase):
    def switches(self, **live):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, **live}}))

    def build(self, rows=(), observed=(), *, real_money=False, families=None):
        self.families = families if families is not None else MemoryFamilies(rows, observed)
        self.main, self.other = InlineDecider(), Pressable()
        return self.restart(real_money=real_money)

    def restart(self, *, real_money=None):
        """A (new) House process on the same state root and the same swarm, its two decider children apart."""
        if getattr(self, "live", None) is not None:
            self.live.state.close()
            self.live.observe_store.close()
            self.main, self.other = InlineDecider(), Pressable()
        self.real_money = self.real_money if real_money is None else real_money
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=self.main, observe_decider=self.other,
                                config={"require_paper_proof": False}, real_money=self.real_money,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def observing(self):
        return sorted(k for k, i in self.live.instances.items() if i.observe and i.mode == "live")

    def row(self, fid, version=1, **kw):
        return next(r for r in practice_summary(self.root, **kw)["rows"] if (r["family"], r["version"]) == (fid, version))


# ---------------------------------------------------------------------------------------------------- eligibility
@unittest.skipUnless(HAVE, "numpy not installed")
class Eligibility(unittest.TestCase):
    """`bands.observe` on the swarm's real store: the two tiers, what never has a row, the order, the pinned lookup."""

    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock

        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.store = SwarmStore(self.root, clock=SwarmClock())

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def add(self, fid, *, versions=3, roots=("SPY",), validated=None, t=None, best_train_version=None, best_version=None,
            best_train=None, **state):
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": list(roots), "dte": [0, 2]}, origin="test")
        for n in range(versions):
            self.store.add_version(fid, f"# {fid} v{n + 1}\n" + code_on(roots[0]), {"hold": 600}, author="test")
            seed_current_run(self.store, fid, n + 1, window="validation" if validated is not None else "train")
        if state.get("banded_version"):
            state["banded_evaluator"] = band_proof(self.store.version(fid, state["banded_version"]))
        if validated is not None:
            state.update(validation_version=validated, validation_line={"passed": False}, validation_numbers={"t": t})
        if best_train_version is not None:
            state["best_train_version"] = best_train_version
        if state:
            self.store.set_state(fid, **state)
        fields = {k: v for k, v in (("best_version", best_version), ("best_train", best_train)) if v is not None}
        if fields:
            self.store.update_family(fid, **fields)

    def test_the_validated_tier_then_the_train_tier_each_in_its_order(self):
        from league.swarm import bands

        self.add("val-lo", validated=1, t=0.5)
        self.add("val-hi", validated=2, t=2.0, best_train_version=3, best_train=9.0)
        self.add("val-none", validated=1, t=None)
        self.add("tr-best", best_train_version=2, best_train=1.5, roots=("QQQ",))
        self.add("tr-sub", best_version=1, best_train_version=2, best_train=0.7)
        self.add("tr-none", best_train_version=1)
        rows = bands.observe(self.root)
        self.assertEqual([r["family"] for r in rows], ["val-hi", "val-lo", "val-none", "tr-best", "tr-sub", "tr-none"])
        by = {r["family"]: r for r in rows}
        self.assertEqual((by["val-hi"]["tier"], by["val-hi"]["version"]), ("validated", 2), "its validated version, not its best")
        self.assertEqual((by["tr-best"]["tier"], by["tr-best"]["version"]), ("train", 2))
        self.assertEqual(by["tr-sub"]["version"], 1, "the submitted best first, as the tournament validates it")
        self.assertEqual(by["tr-best"]["needs_roots"], ["QQQ"], "the program's NEEDS roots")
        for r in rows:
            self.assertEqual((r["observe"], r["band"], r["holdout_passed"], r["validation_passed"], r["forward"],
                              r["typical_max_loss_usd"]), (True, "gym", False, False, None, None))
            self.assertEqual(r["lineage"], r["family"])
        self.assertIn("tr-best v2", by["tr-best"]["code"])
        self.assertIsNone(by["tr-best"]["validated_version"])

    def test_never_a_row_for_a_demoted_refused_reviewed_retired_non_gym_or_candidateless_family(self):
        from league.swarm import bands
        from league.swarm.gate import run_sha

        self.add("robust", best_train_version=2, robust_failed=[2])
        self.add("drift", best_train_version=1, drift_failed={"1": "its drift-adjusted alpha has t -0.8 over Train"})
        self.add("nothing")
        self.add("dead", best_train_version=1)
        self.store.retire_gym("dead", "finished", floor=0, source="test")
        self.add("cand", validated=1, t=3.0, banded_version=1)
        self.store.set_band("cand", "candidate", reason="passed")
        self.add("reviewed", best_train_version=1)
        self.add("refused", best_train_version=1)
        self.store.set_state("reviewed", review={"sha": run_sha(self.store.version("reviewed", 1)), "verdict": "fail"})
        self.store.set_state("refused", gate_outcome={"sha": run_sha(self.store.version("refused", 1)), "result": "refused"})
        self.add("fine", best_train_version=1)
        self.assertEqual([r["family"] for r in bands.observe(self.root)], ["fine"])
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["cand"], "and no practice row ever reaches read()")

    def test_the_train_tier_is_the_tournaments_candidate(self):
        from league.swarm import bands
        from league.swarm.tournament import Tournament

        rng = random.Random(429)
        tournament = Tournament(self.store, None, {})
        for i in range(40):
            self.add(f"f{i:02d}", best_version=rng.choice([None, 1, 2, 3]),
                     best_train_version=rng.choice([None, 1, 2, 3]), best_train=rng.choice([None, -1.0, 0.5, 2.0]))
        rows = {r["family"]: r for r in bands.observe(self.root)}
        for fam in self.store.families(alive=True):
            n = tournament.candidate_version(fam)
            if n is None:
                self.assertNotIn(fam["id"], rows)
            else:
                self.assertEqual((rows[fam["id"]]["version"], rows[fam["id"]]["tier"]), (n, "train"), fam["id"])

    def test_a_pinned_version_holds_until_the_family_has_no_version_or_it_is_demoted(self):
        from league.swarm import bands

        self.add("tr", best_train_version=1)
        [row] = bands.observe(self.root, family="tr", version=1)
        self.assertEqual((row["version"], row["tier"]), (1, "train"))
        self.store.set_state("tr", best_train_version=2)
        self.assertEqual(bands.observe(self.root)[0]["version"], 2, "the current candidate moved on")
        self.assertEqual(bands.observe(self.root, family="tr", version=1)[0]["version"], 1, "the pinned one still holds")
        self.store.set_state("tr", robust_failed=[1])
        self.assertEqual(bands.observe(self.root, family="tr", version=1), [], "demoted: it winds down")
        self.store.set_state("tr", best_train_version=None)
        self.assertEqual(bands.observe(self.root, family="tr", version=2), [], "no version to practise: no row")
        self.add("val", validated=1, t=1.0, drift_failed={"1": "its drift-adjusted alpha has t -0.8 over Train"})
        self.assertEqual(bands.observe(self.root, family="val", version=1)[0]["tier"], "validated",
                         "the validated tier's rule is the sprint's, unchanged")


# ------------------------------------------------------------------------------------------------------------ caps
class Caps(PracticeCase):
    def test_validated_first_then_train_under_the_instance_cap(self):
        self.switches(observe_max=3)
        self.build(observed=[validated("a", t=1.0), trained("c", best=5.0), validated("b", t=2.0), trained("d", best=1.0)])
        self.run_to(9, 32)
        pins = self.live.state.get("observe_pins")
        self.assertEqual(pins["order"], ["b", "a", "c"])
        self.assertEqual(pins["tiers"], {"b": "validated", "a": "validated", "c": "train"})
        self.assertEqual(self.observing(), ["a@1:o", "b@1:o", "c@1:o"])
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual((record["capped"], record["why"], record["cap"]), (["d"], "cap", 3))

    def test_the_roots_cap_skips_a_family_that_adds_roots_and_a_later_one_on_read_roots_joins(self):
        self.switches(observe_roots_max=2)
        self.build(observed=[validated("a", t=3.0), validated("b", t=2.0, roots=("QQQ",)), validated("c", t=1.0, roots=("IWM",)),
                             trained("d", best=1.0, roots=("SPY", "QQQ"))])
        self.run_to(9, 34)
        self.assertEqual(self.live.state.get("observe_pins")["order"], ["a", "b", "d"])
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual((record["capped"], record["why"], record["roots_max"]), (["c"], "roots", 2))
        health = self.live.health()["observe"]
        self.assertEqual((health["roots_used"], health["roots_max"], health["max"], health["effective_cap"]), (2, 2, 48, 48))
        self.assertEqual(health["tiers"], {"validated": 2, "train": 1})
        self.run_to(9, 40)
        self.assertEqual(len(self.ledger.of("live.observe")), 1, "said once a day")
        self.assertNotIn("IWM", [r for r, _ in self.market.chain_reads], "a skipped family's root is never read")

    def test_the_train_switch_winds_the_train_pins_down_at_the_next_pass(self):
        self.build(observed=[validated("a"), trained("c")])
        self.run_to(9, 33)
        self.assertEqual(self.observing(), ["a@1:o", "c@1:o"])
        self.switches(observe_train=False)
        self.live._switches = None
        self.live.sync_families(self.clock(), force=True)
        self.assertEqual(self.live.instances["c@1:o"].mode, "wind_down")
        self.assertEqual(self.live.instances["a@1:o"].mode, "live")
        self.assertEqual(self.live.state.get("observe_pins")["order"], ["a"])

    def test_malformed_values_are_the_defaults_and_the_read_budget_follows_swarm_json(self):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"observe_roots_max": "lots", "observe_train": "yes",
                                                                   "observe_read_calls": 5, "observe_max": -1}}))
        live = self.build()
        sw = live.switches()
        self.assertEqual((sw["observe_roots_max"], sw["observe_train"], sw["observe_read_calls"], sw["observe_max"]),
                         (24, False, 120, 48), "a switch is on only while JSON true; a bad count is its default")
        (self.root / "swarm.json").unlink()
        live._switches = None
        self.assertEqual((live.switches()["observe_train"], live.switches()["observe_roots_max"]), (True, 24))
        self.switches(observe_read_calls=10)
        live = self.build(observed=[validated("q", roots=("QQQ",))])
        self.assertEqual(live.switches()["observe_read_calls"], 10)
        self.run_to(9, 33)
        self.assertIn("QQQ", [r for r, _ in self.market.chain_reads])
        for _ in range(10):
            self.market.minute_calls.take(force=True)
        del self.market.chain_reads[:]
        out = self.run_to(9, 34)
        self.assertNotIn("QQQ", [r for r, _ in self.market.chain_reads], "the minute's calls reached swarm.json's budget")
        self.assertGreaterEqual(out.get("observe_reads_skipped", 0), 1)


# -------------------------------------------------------------------------------------------------------- shedding
class Shedding(PracticeCase):
    def test_sustained_pressure_sheds_the_train_tail_once_for_the_session(self):
        self.build(observed=[validated("v"), trained("t1", best=4.0), trained("t2", best=3.0), trained("t3", best=2.0),
                             trained("t4", best=1.0)])
        self.run_to(9, 34)
        self.assertEqual(len(self.observing()), 5)
        self.other.pressed = True
        self.run_to(9, 36)
        self.assertFalse(self.ledger.of("live.observe"), "two pressed minutes of ten: not yet")
        self.run_to(9, 37)
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual((record["shed"], record["effective_cap"]), (["t4"], 4), "a quarter of four, the lowest first")
        self.assertEqual(self.live.instances["t4@1:o"].mode, "wind_down")
        self.assertEqual(self.live.state.get("observe_pins")["order"], ["v", "t1", "t2", "t3"])
        self.assertEqual(len([t for _, t in self.alerts if "under pressure" in t]), 1)
        self.other.pressed = False
        self.run_to(9, 50)
        self.assertEqual(len(self.ledger.of("live.observe")), 1, "one shed while the pressure passed")
        self.assertNotIn("t4@1:o", self.live.instances)
        self.restart()
        self.clock.set(self.clock() + 60)
        self.live.minute()
        self.assertEqual(self.live.state.get("observe_pins")["order"], ["v", "t1", "t2", "t3"], "a restart keeps the shed")
        self.assertNotIn("t4@1:o", self.live.instances)
        self.assertEqual(self.live.health()["observe"]["effective_cap"], 4)
        self.clock.set(at(TUESDAY, 9, 31))
        self.live.minute()
        self.assertEqual(self.live.state.get("observe_pins")["order"], ["v", "t1", "t2", "t3", "t4"],
                         "the next session pins afresh at the full caps")
        self.assertEqual(self.live.health()["observe"]["effective_cap"], 48)

    def test_validated_pins_are_never_shed(self):
        self.build(observed=[validated("a", t=2.0), validated("b", t=1.0)])
        self.run_to(9, 33)
        self.other.pressed = True
        self.run_to(10, 0)
        self.assertFalse([p for p, _ in self.ledger.of("live.observe") if "shed" in p])
        self.assertEqual(self.observing(), ["a@1:o", "b@1:o"])
        self.assertGreater(self.live.health()["budget_spent"]["observe_decider"], 20, "their degradation is the budget")


# ------------------------------------------------------------------------------------------------------- isolation
class Isolation(PracticeCase):
    """The money path (the design's section 4): with real money on, the grant active and the paper proof requirement met,
    a validated and a Train-tier practice family trading every minute beside a Probe family send no real order, hold no
    real position, write no forward row and move no band; the order path is never asked for an observe key."""

    def test_practice_never_reaches_the_order_path_the_forward_record_or_a_band(self):
        live = self.build([family("vert", VERTICAL, band="probe")],
                          [validated("obs", params={"hold": 3, "opens": 3}), trained("tr", params={"hold": 3, "opens": 3})],
                          real_money=True)
        asked = []
        real_intent = live._real_intent

        def spy(inst, *args, **kwargs):
            asked.append(inst.key)
            return real_intent(inst, *args, **kwargs)

        live._real_intent = spy
        self.run_to(9, 50)
        self.assertTrue(asked)
        self.assertEqual({k for k in asked}, {"vert@1:r"}, "only the Probe's real instance ever reached the order path")
        self.assertTrue(self.venue.sent)
        self.assertTrue(all(o.family == "vert" for o in live.book.orders.values()))
        self.assertTrue(all(p.family == "vert" for p in live.book.positions.values()))
        self.assertEqual(set(self.families.forward), {"vert"}, "never a forward row")
        self.assertFalse([k for k in self.families.forward["vert"] if ":o" in k[1]])
        self.assertEqual([m for m in self.families.moves if m[0] != "vert"], [], "never a band move")
        self.assertFalse([k for k in live.instances if k.endswith(":t")], "never tuition")
        for table, column in (("instances", "id"), ("orders", "instance"), ("positions", "instance")):
            ids = [str(r[column]) for r in live.state.rows(f"SELECT {column} FROM {table}")]
            self.assertFalse([i for i in ids if i.endswith(":o")], table)
            self.assertFalse(live.state.rows(f"SELECT family FROM {table} WHERE family IN ('obs', 'tr')"), table)
        summary = practice_summary(self.root)
        self.assertEqual({r["family"] for r in summary["rows"]}, {"obs", "tr"})
        self.assertTrue(all(r["trades"] > 0 for r in summary["rows"]), "they practised")
        self.assertEqual({(r["family"], r["tier"]) for r in summary["rows"]}, {("obs", "validated"), ("tr", "train")})
        self.assertFalse([t for _, t in self.alerts if "not a real instance" in t])

    def test_nothing_reaches_the_swarms_store(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock

        store = SwarmStore(self.root, clock=SwarmClock())
        self.addCleanup(store.close)
        for fid, state in (("val", {"validation_version": 1, "validation_numbers": {"t": 1.0}}), ("tr", {"best_train_version": 1})):
            store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                              "roots": ["SPY"], "dte": [0, 2]}, origin="test")
            store.add_version(fid, f"# {fid}\n" + VERTICAL, {"hold": 3, "opens": 3}, author="test")
            store.set_state(fid, **state)
            seed_current_run(store, fid, 1, window="validation" if state.get("validation_version") else "train")
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        self.build(families=families, real_money=True)
        self.run_to(9, 50)
        self.assertEqual({r["family"]: r["tier"] for r in practice_summary(self.root)["rows"]}, {"val": "validated", "tr": "train"})
        self.assertEqual((store.forward("val"), store.forward("tr")), ([], []))
        self.assertEqual(store._all("SELECT count(*) AS n FROM forward")[0]["n"], 0)
        self.assertEqual([f["band"] for f in store.families(alive=True)], ["gym", "gym"])
        self.assertEqual(self.venue.sent, [])


# ------------------------------------------------------------------------------------------------------ accounting
class Accounting(PracticeCase):
    def test_realized_is_the_engines_pnl_open_positions_are_apart_and_a_forced_close_is_counted_apart(self):
        live = self.build(observed=[validated("obs", params={"hold": 3, "opens": 3}),
                                    validated("held", t=0.5, params={"hold": 600, "opens": 1})])
        self.run_to(9, 45)
        acc = live.shadow.accounts["obs@1:o"]
        row = self.row("obs")
        self.assertEqual(row["trades"], len(acc.trades))
        self.assertGreaterEqual(row["trades"], 2)
        self.assertAlmostEqual(row["pnl_usd"], round(sum(t["pnl"] for t in acc.trades), 2), places=2)
        self.assertAlmostEqual(row["max_loss_usd"], round(sum(t["max_loss"] for t in acc.trades), 2), places=2)
        self.assertEqual((row["forced"], row["program"]["trades"], row["tier"], row["lineage"]), (0, row["trades"], "validated",
                                                                                               "obs-line"))
        held = live.shadow.accounts["held@1:o"]
        [pos] = held.positions.values()
        mark = round(pos.cash + pos.last_mark * 100 * pos.qty, 2)
        row = self.row("held")
        self.assertEqual((row["trades"], row["pnl_usd"], row["open_positions"]), (0, 0.0, 1), "open is never realized")
        self.assertAlmostEqual(row["open_mark_pnl_usd"], mark, places=2)
        # Explicit practice disable winds down even an unfinished frozen cohort; research retirement alone does not.
        self.switches(observe=False)
        live.sync_families(self.clock(), force=True)
        self.run_to(9, 53)  # refresh switches, submit the close, then meet the next minute's quotes
        self.assertNotIn("held@1:o", live.instances)
        row = self.row("held")
        self.assertEqual((row["trades"], row["forced"], row["program"]["trades"], row["status"]), (1, 1, 0, "wound_down"),
                         "the wind-down close is in the headline and out of the statistics; the record outlives the family")
        self.assertNotEqual(row["pnl_usd"], 0.0)

    def test_coverage_counts_what_was_due_and_why_it_was_missed(self):
        live = self.build(observed=[validated("q", roots=("QQQ",), params={"hold": 600, "opens": 1})])
        self.run_to(9, 35)
        self.market.dead.add("QQQ")
        self.run_to(9, 39)
        self.market.dead.discard("QQQ")
        self.other.pressed = True
        self.run_to(9, 42)
        self.other.pressed = False
        self.run_to(9, 45)
        row = self.row("q")
        self.assertGreaterEqual(row["missed_quotes"], 2)
        self.assertGreaterEqual(row["missed_budget"], 2)
        self.assertEqual(row["decisions_due"], row["decisions_made"] + row["missed_quotes"] + row["missed_budget"])
        self.assertLess(row["coverage"], 1.0)
        self.assertGreater(row["decisions_made"], 0)
        self.assertGreaterEqual(row["minutes"], row["decisions_due"], "every minute stepped is counted, due or not")
        self.assertIn("q@1:o", live.instances)

    def test_sessions_minutes_and_a_restart_continue_one_record(self):
        self.build(observed=[validated("obs", params={"hold": 3, "opens": 2})])
        self.run_to(9, 40)
        first = self.row("obs")
        nonce = self.live.shadow.accounts["obs@1:o"].nonce
        self.restart()
        self.clock.set(self.clock() + 60)
        self.run_to(9, 45)
        self.assertEqual(self.live.shadow.accounts["obs@1:o"].nonce, nonce, "the same account")
        again = self.row("obs")
        self.assertEqual((again["sessions"], again["minutes"]), (1, first["minutes"] + 5))
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 35)
        row = self.row("obs")
        self.assertEqual(row["sessions"], 2)
        self.assertEqual(row["first_day"], MONDAY.isoformat())

    def test_the_marked_path_and_a_remade_account(self):
        now = [1000.0]
        store = ObserveStore(self.root, clock=lambda: now[0])
        self.addCleanup(store.close)

        def minute(account, equity, day="2026-09-28"):
            now[0] += 60
            store.practice([{"family": "f", "version": 1, "tier": "train", "lineage": "f", "structure": "long_call",
                             "roots": ["SPY"], "capital": 10000.0, "account": account, "at": now[0], "day": day,
                             "equity": equity, "open_positions": 0, "open_mark_pnl": 0.0, "due": True, "made": True,
                             "status": "live"}])

        for equity in (10000.0, 10020.0, 9990.0, 10010.0):                 # marked 0, +20, -10, +10: down 30 from +20
            minute("a", equity)
        store.add("f@1:o", "f", 1, [{"id": 1, "day": "2026-09-28", "exit_day": "2026-09-28", "pnl": 10.0, "max_loss": 50.0,
                                     "exit_reason": "program"}], account="a")
        for equity in (10000.0, 9970.0):                                     # remade: +10 carried, then -20: down 40
            minute("b", equity, day="2026-09-29")
        row = self.row("f", sessions=None)
        self.assertEqual((row["drawdown_marked_usd"], row["minutes"], row["sessions"]), (40.0, 6, 2))
        db = sqlite3.connect(self.root / "observe.sqlite")
        self.assertEqual(db.execute("SELECT pnl_marked, peak_marked FROM practice").fetchone(), (-20.0, 20.0))
        db.close()

    def test_realized_drawdown_and_the_statistics_by_hand(self):
        store = ObserveStore(self.root)
        self.addCleanup(store.close)
        trades = [(1, "2026-09-28", 10.0, False), (2, "2026-09-28", -5.0, False), (3, "2026-09-29", -20.0, False),
                  (4, "2026-09-29", 8.0, False), (5, "2026-09-30", 100.0, True)]
        store.add("f@1:o", "f", 1, [{"id": i, "day": d, "exit_day": d, "pnl": p, "max_loss": 50.0, "exit_reason": "program",
                                     "forced": forced} for i, d, p, forced in trades], account="a")
        row = self.row("f", sessions=None)
        self.assertEqual((row["trades"], row["forced"], row["pnl_usd"]), (5, 1, 93.0), "forced is in the headline")
        self.assertEqual(row["drawdown_realized_usd"], 25.0, "cumulative 10, 5, -15, -7, 93: down 25 from 10")
        program = row["program"]
        self.assertEqual((program["trades"], program["wins"], program["pnl_usd"], program["days"]), (4, 2, -7.0, 2))
        returns = [0.2, -0.1, -0.4, 0.16]
        mean = sum(returns) / 4
        sd = (sum((x - mean) ** 2 for x in returns) / 3) ** 0.5
        self.assertAlmostEqual(program["t_trade"], mean / (sd / 2), places=3)
        daily = [0.1, -0.24]
        mean = sum(daily) / 2
        sd = (sum((x - mean) ** 2 for x in daily)) ** 0.5
        self.assertAlmostEqual(program["t_daily"], mean / (sd / 2 ** 0.5), places=3)
        self.assertAlmostEqual(row["return_on_risk"], 93.0 / 250.0, places=4)
        self.assertEqual(self.row("f", sessions=1)["trades"], 1, "the window: the last session only")

    def test_the_summary_is_read_only_and_never_raises(self):
        self.assertEqual(practice_summary(self.root), {}, "no file")
        path = self.root / "observe.sqlite"
        old = sqlite3.connect(path)
        old.executescript("CREATE TABLE trades (seq INTEGER PRIMARY KEY, instance TEXT, account TEXT, family TEXT, "
                          "version INTEGER, trade_id TEXT, day TEXT, pnl REAL, max_loss REAL, recorded_at REAL, body TEXT);")
        old.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body) "
                    "VALUES('f@1:o', 'a', 'f', 1, '1', '2026-09-28', 4.0, 20.0, 0, ?)",
                    (json.dumps({"exit_day": "2026-09-28", "exit_reason": "program", "type": "long_call", "root": "SPY"}),))
        old.commit()
        old.close()
        self.assertEqual(practice_summary(self.root), {}, "a file from before the practice table")
        store = ObserveStore(self.root)
        self.assertTrue(store.add("f@1:o", "f", 1, [], account="a"))
        store._connect()
        store.close()
        [row] = practice_summary(self.root)["rows"]
        self.assertEqual((row["family"], row["tier"], row["structure"], row["pnl_usd"], row["roots"]),
                         ("f", "validated", "long_call", 4.0, ["SPY"]), "migrated: a trade from before the ledger is kept")
        before = path.stat().st_mtime_ns
        self.assertEqual(len(practice_summary(self.root)["rows"]), 1)
        self.assertEqual(path.stat().st_mtime_ns, before, "read-only: the file is never written")
        lock = sqlite3.connect(path, isolation_level=None)
        lock.execute("PRAGMA journal_mode=DELETE")
        lock.execute("BEGIN EXCLUSIVE")
        try:
            began = time.monotonic()
            self.assertEqual(practice_summary(self.root), {}, "a locked file: nothing, never an error")
            self.assertLess(time.monotonic() - began, 5.0, "within its one-second timeout")
        finally:
            lock.execute("ROLLBACK")
            lock.close()


# -------------------------------------------------------------------------------------------------------- embargo
class Embargo(LiveCase):
    """The forward embargo: a Sized move also needs the forward record of sessions after the version was written."""

    RETURNS = [0.30, 0.10, 0.20, -0.10, 0.25] * 5

    def probe(self, created, *, returns=None, real=True):
        live = self.make([dict(family("vert", VERTICAL, band="probe"), version_created_at=created)])
        self.families.add_forward("vert", "shadow", [{"id": f"s{i}", "day": f"2026-09-{i % 25 + 1:02d}", "pnl": r * 100.0,
                                                       "max_loss": 100.0} for i, r in enumerate(returns or self.RETURNS)])
        if real:
            self.families.add_forward("vert", "real", [{"id": f"r{i}", "day": f"2026-08-{i + 1:02d}", "pnl": 6.0,
                                                        "max_loss": 50.0} for i in range(5)])
        live.state.put("band_moves", {"vert": {"band": "probe", "at": at(MONDAY, 9, 0) - 7 * 86400}})
        return live

    def test_sized_needs_the_record_after_the_version_was_written_too(self):
        self.probe("2026-08-31T12:00:00Z")                                   # 25 shadow trades after it: Sized
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "sized")

    def test_days_before_the_version_was_written_never_count_toward_sized(self):
        self.probe("2026-09-26T00:00:00Z")                                   # New York: Sept 25; every row is on or before
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe")
        held = [p for p, _ in self.ledger.of("live.band") if p.get("held")]
        self.assertEqual(len(held), 1)
        self.assertIn("forward embargo", held[0]["why"])
        self.run_to(9, 45)
        self.assertEqual(len([p for p, _ in self.ledger.of("live.band") if p.get("held")]), 1, "said once a day")

    def test_the_same_rows_still_count_toward_negative(self):
        self.probe("2026-09-26T00:00:00Z", returns=[-0.2, 0.1, -0.3, -0.1] * 6)
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "candidate", "demoted on the whole record")

    def test_selection_of_an_old_version_restarts_the_fresh_evaluation_window(self):
        self.probe("2026-08-31T12:00:00Z")
        self.families.rows["vert"]["version_selected_at"] = "2026-09-26T12:00:00Z"
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe", "practice used to select an old program is training")

    def test_a_candidates_move_to_probe_is_unchanged(self):
        self.make([dict(family("cand", VERTICAL, band="candidate"), version_created_at="2026-10-05T00:00:00Z")])
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["cand"]["band"], "probe", "Candidate to Probe reads nothing new")

    def test_an_unknown_writing_day_holds_at_probe(self):
        self.probe("2026-08-31T12:00:00Z")
        del self.families.rows["vert"]["version_created_at"]
        self.run_to(9, 31)
        self.assertEqual(self.families.rows["vert"]["band"], "probe", "fail-closed")


if __name__ == "__main__":
    unittest.main()
