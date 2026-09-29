"""The practice league's feedback to research (Sept 29, 2026; league/swarm/practice.py): the strategist's PRACTICE table
and the architect's PRACTICE BY CLASS lines carry signs, counts and t's (never dollars, dates, versions or code), the
bandit's bonus is bounded (a family gains at most `practice.bonus` of its share, the bonus moves at most
`practice.bonus_total`), and nothing on the way to real money reads the weight it changes."""

from __future__ import annotations

import copy
import inspect
import random
import re
import tempfile
import unittest
from pathlib import Path

from league.live.observe import ObserveStore, practice_summary
from league.swarm import bands, evidence, practice
from league.swarm.architect import Architect
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.swarm.strategist import Strategist, check_section
from league.swarm.tournament import Tournament
from league.tests.swarm_fakes import Clock

REPO = Path(__file__).resolve().parents[2]
VERTICAL = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {"hold": 3}

def decide(ctx):
    return []
'''


class PracticeStoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock()
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        self.settings["architect"]["openai_model"] = None
        self.ledger = ObserveStore(self.root)
        self.addCleanup(self.ledger.close)
        practice.clear_cache()
        self.addCleanup(practice.clear_cache)
        self.at = 1_790_000_000.0

    def family(self, fid, *, structure="long_put", roots=("SPY",), **state):
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": structure, "roots": list(roots),
                               "dte": [0, 5]}, origin="test")
        self.store.add_version(fid, f"# {fid}\n" + VERTICAL.replace('"SPY"', f'"{roots[0]}"'), {"hold": 3}, author="test")
        if state:
            self.store.set_state(fid, **state)

    def practised(self, fid, trades, *, version=1, tier="validated", structure="long_put", roots=("SPY",), days=("2026-09-29",)):
        """A practice record: a live minute on each of `days`, then `trades` [(exit day, pnl, max loss, forced)]."""
        for day in days:
            self.at += 60
            self.ledger.practice([{"family": fid, "version": version, "tier": tier, "lineage": fid, "structure": structure,
                                   "roots": list(roots), "capital": 10000.0, "account": "a", "at": self.at, "day": day,
                                   "equity": 10000.0, "open_positions": 0, "open_mark_pnl": 0.0, "due": True, "made": True,
                                   "status": "live"}])
        self.ledger.add(f"{fid}@{version}:o", fid, version,
                        [{"id": i, "day": d, "exit_day": d, "pnl": p, "max_loss": m, "exit_reason": "program", "forced": f,
                          "type": structure, "root": roots[0]} for i, (d, p, m, f) in enumerate(trades, 1)], account="a")
        practice.clear_cache()


# ---------------------------------------------------------------------------------------------------------- inputs
class Inputs(PracticeStoreCase):
    def test_without_a_record_or_with_feedback_off_there_is_nothing(self):
        self.assertEqual(practice.summary(None, 10), {})
        self.assertEqual(practice.summary(self.root, 10), {}, "the file exists with no practice yet")
        self.assertIsNone(practice.table(self.store, self.settings))
        self.assertEqual(practice.class_lines(self.store, self.settings), [])
        self.family("fam")
        self.practised("fam", [("2026-09-29", 10.0, 50.0, False)] * 4, days=("2026-09-29",))
        self.assertIsNotNone(practice.table(self.store, self.settings))
        self.settings["practice"]["feedback"] = False
        self.assertIsNone(practice.table(self.store, self.settings))
        self.assertEqual(practice.class_lines(self.store, self.settings), [])
        shares = {"fam": 0.5, "x": 0.5}
        self.assertEqual(practice.apply_bonus(shares, self.store, self.settings), (shares, {}))

    def test_the_strategists_packet_has_signs_counts_and_ts_and_never_dollars_dates_versions_or_code(self):
        self.family("put-etf", roots=("QQQ",))
        self.family("straddle-names", structure="long_straddle", roots=("AAPL",))
        self.family("thin")
        self.practised("put-etf", [("2026-09-29", 12.34, 50.0, False), ("2026-09-29", -3.21, 50.0, False),
                                   ("2026-09-30", 7.5, 50.0, False), ("2026-09-30", 4.0, 40.0, True)],
                       roots=("QQQ",), days=("2026-09-29", "2026-09-30"), version=7)
        self.practised("straddle-names", [("2026-09-30", -20.0, 80.0, False)] * 3, structure="long_straddle",
                       roots=("AAPL",), tier="train")
        self.practised("thin", [("2026-09-30", 5.0, 50.0, False)] * 2)
        self.store.retire_gym("thin", "finished", floor=0, source="test")
        packet = Strategist(self.store, None, self.settings, clock=self.clock).packet()
        self.assertIn("PRACTICE (shadow trades on the live market under the Gym's own fill rules, the last 10 sessions: a "
                      "research signal, never evidence", packet)
        part = packet.split("PRACTICE (", 1)[1].split("\n\n", 1)[0]
        self.assertLess(packet.index("THE LAST 24 HOURS"), packet.index("PRACTICE ("))
        self.assertNotIn("$", part)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}", part), "no dates")
        for word in ("version", "12.34", "3.21", "NEEDS", "decide", "pnl", "usd"):
            self.assertNotIn(word, part)
        table = practice.table(self.store, self.settings)
        fams = {r["family"]: r for r in table["families"]}
        self.assertEqual((fams["put-etf"]["trades"], fams["put-etf"]["sign"], fams["put-etf"]["class"], fams["put-etf"]["tier"]),
                         (3, "+", "long_put x etf", "validated"), "program-closed trades only: the forced close is not one")
        self.assertIsNotNone(fams["put-etf"]["t"])
        self.assertEqual((fams["straddle-names"]["sign"], fams["straddle-names"]["tier"]), ("-", "train"))
        self.assertIsNone(fams["thin"]["t"], "a t is null below three trades")
        self.assertTrue(fams["thin"]["status"].startswith("retired"), "the record outlives the family")
        classes = {r["class"]: r for r in table["by_class"]}
        self.assertEqual(set(classes), {"long_put x etf", "long_straddle x names"})
        self.assertEqual((classes["long_put x etf"]["families"], classes["long_put x etf"]["trades"]), (2, 5))

    def test_the_validator_takes_practice_and_still_refuses_paper_trading_and_the_forward_window(self):
        from league.tests.test_swarm_strategist import CITES, CLEAN

        ok = check_section(CLEAN + "\n(e) Practice favours long puts on liquid ETFs: give that class one deeper family.",
                           max_chars=1600, cites=CITES, known_ids=frozenset(CITES), min_cites=3)
        self.assertTrue(ok.ok, ok.reasons)
        for text, rule in (("(e) Paper trading favours long puts on liquid ETFs.", "real_money"),
                           ("(e) The forward window favours long puts on liquid ETFs.", "d2"),
                           ("(e) Live trading favours long puts on liquid ETFs.", "real_money")):
            v = check_section(CLEAN + "\n" + text, max_chars=1600, cites=CITES, known_ids=frozenset(CITES), min_cites=3)
            self.assertFalse(v.ok)
            self.assertTrue(any(r.startswith(rule) for r in v.reasons), (text, v.reasons))

    def test_the_architect_reads_at_most_twelve_class_lines_and_none_when_feedback_is_off(self):
        structures = ["long_call", "long_put", "debit_vertical", "long_straddle", "long_strangle", "long_butterfly"]
        roots = [("SPY",), ("AAPL",), ("SPXW",)]
        n = 0
        for structure in structures:
            for root in roots:
                fid = f"f{n:02d}"
                self.family(fid, structure=structure, roots=root)
                self.practised(fid, [("2026-09-29", 1.0 + n, 50.0, False)] * (1 + n % 4), structure=structure, roots=root)
                n += 1
        prompt = Architect(self.store, None, self.settings, clock=self.clock).prompt()
        self.assertIn("PRACTICE BY CLASS (shadow trades on the live market under the Gym's fill rules, the last 10 sessions; "
                      "a research signal, never evidence", prompt)
        block = prompt.split("PRACTICE BY CLASS", 1)[1].split("\n\n", 1)[0].splitlines()[1:]
        self.assertEqual(len(block), 12)
        self.assertRegex(block[0], r"^[a-z_]+ x [a-z+]+: \d+ famil(y|ies), \d+ trades on \d+ sessions, net [+-0], t (n/a|-?\d+\.\d)$")
        self.assertLess(prompt.index("RESEARCH COVERAGE"), prompt.index("PRACTICE BY CLASS"))
        self.assertLess(prompt.index("PRACTICE BY CLASS"), prompt.index("GAPS"))
        self.settings["practice"]["feedback"] = False
        self.assertNotIn("PRACTICE", Architect(self.store, None, self.settings, clock=self.clock).prompt())


# ----------------------------------------------------------------------------------------------------------- bandit
class Bandit(PracticeStoreCase):
    def test_the_bonus_is_bounded_whatever_the_shares_and_records(self):
        rng = random.Random(29)
        c = practice.cfg(self.settings)
        for _ in range(400):
            ids = [f"f{i}" for i in range(rng.randint(1, 30))]
            raw = [rng.random() for _ in ids]
            shares = {f: v / sum(raw) for f, v in zip(ids, raw)}
            records = {f: {"trades": rng.randint(0, 30), "days": rng.randint(0, 6), "pnl": rng.uniform(-50, 50),
                           "t": rng.choice([None, rng.uniform(-4, 6)])} for f in ids if rng.random() < 0.7}
            b = practice.bonuses(shares, records, c)
            self.assertLessEqual(sum(shares[f] * v for f, v in b.items()), c["bonus_total"] + 1e-12)
            for f, v in b.items():
                rec = records[f]
                self.assertTrue(0 < v <= c["bonus"] + 1e-12)
                self.assertTrue(rec["trades"] >= c["min_trades"] and rec["pnl"] > 0 and rec["t"] is not None and rec["t"] > 0)
            raised = {f: w * (1 + b.get(f, 0.0)) for f, w in shares.items()}
            norm = sum(raised.values())
            new = {f: v / norm for f, v in raised.items()}
            self.assertAlmostEqual(sum(new.values()), 1.0, places=9)
            for f in ids:
                self.assertLessEqual(new[f], shares[f] * (1 + c["bonus"]) + 1e-12, "at most +25% of its own share")
            moved = sum(max(0.0, new[f] - shares[f]) for f in ids)
            self.assertLessEqual(moved, c["bonus_total"] + 1e-12, "at most 10% of all share moves")

    def test_one_day_is_a_third_three_days_the_whole_and_a_short_negative_or_forced_record_nothing(self):
        c = practice.cfg(self.settings)
        shares = {"one": 0.01, "three": 0.01, "short": 0.01, "negative": 0.01, "rest": 0.96}
        records = {"one": {"trades": 5, "days": 1, "pnl": 10.0, "t": 2.5}, "three": {"trades": 9, "days": 3, "pnl": 10.0, "t": 4.0},
                   "short": {"trades": 2, "days": 2, "pnl": 10.0, "t": 5.0},
                   "negative": {"trades": 9, "days": 3, "pnl": -1.0, "t": 3.0}}
        b = practice.bonuses(shares, records, c)
        self.assertAlmostEqual(b["one"], 0.25 / 3)
        self.assertAlmostEqual(b["three"], 0.25)
        self.assertNotIn("short", b)
        self.assertNotIn("negative", b)
        self.family("forced")
        self.practised("forced", [("2026-09-29", 30.0, 50.0, True)] * 5 + [("2026-09-29", -1.0, 50.0, False)] * 3)
        self.assertEqual(practice.family_records(self.store, self.settings)["forced"]["pnl"], -3.0, "forced closes never count")
        self.assertEqual(practice.apply_bonus({"forced": 0.5, "x": 0.5}, self.store, self.settings)[1], {})

    def test_the_settings_are_bounded_by_the_code(self):
        self.settings["practice"].update(bonus=5.0, bonus_total=0.9, sessions=1000, min_trades=0, feedback="true")
        c = practice.cfg(self.settings)
        self.assertEqual((c["bonus"], c["bonus_total"], c["sessions"], c["min_trades"], c["feedback"]), (0.5, 0.2, 60, 1, False))
        self.settings["practice"] = {"bonus": "lots", "bonus_total": None}
        c = practice.cfg(self.settings)
        self.assertEqual((c["bonus"], c["bonus_total"], c["feedback"]), (0.25, 0.10, True))

    def test_the_tournament_applies_it_and_records_it(self):
        for fid in ("star", "plain", "other"):
            self.family(fid)
            self.store.update_family(fid, validations=3)
        self.practised("star", [("2026-09-29", 10.0, 50.0, False), ("2026-09-30", 12.0, 50.0, False),
                                ("2026-10-01", 9.0, 50.0, False), ("2026-10-01", 11.0, 50.0, False)],
                       days=("2026-09-29", "2026-09-30", "2026-10-01"))
        on = Tournament(self.store, None, self.settings, clock=self.clock, rng=random.Random(7))
        with_bonus = on.allocate(self.store.families(alive=True))
        self.assertEqual(set(on.practice_bonus), {"star"})
        self.assertLessEqual(on.practice_bonus["star"], 0.25)
        off_settings = copy.deepcopy(self.settings)
        off_settings["practice"]["feedback"] = False
        off = Tournament(self.store, None, off_settings, clock=self.clock, rng=random.Random(7))
        without = off.allocate(self.store.families(alive=True))
        self.assertEqual(off.practice_bonus, {})
        self.assertAlmostEqual(sum(with_bonus.values()), 1.0)
        self.assertGreater(with_bonus["star"] / without["star"], 1.0)
        self.assertLessEqual(with_bonus["star"] / without["star"], 1.25 + 1e-9)


# ---------------------------------------------------------------------------------------------------- cannot promote
class CannotPromote(PracticeStoreCase):
    """The bonus changes `families.weight` only. Nothing on the way to real money reads it."""

    WEIGHT = re.compile(r"\bweight\b")

    def test_the_money_and_evidence_paths_never_read_the_weight(self):
        files = [REPO / "league" / "swarm" / "gate.py", REPO / "league" / "swarm" / "bands.py", REPO / "league" / "publish.py",
                 REPO / "league" / "trading_profit.py", *sorted((REPO / "league" / "live").glob("*.py"))]
        for path in files:
            self.assertIsNone(self.WEIGHT.search(path.read_text(encoding="utf-8")), path.name)
        for fn in (evidence.validation_line, evidence.holdout_line, evidence.drift_screen, evidence.forward_record,
                   Tournament.validate, Tournament.judge, Tournament._verdict, Tournament.candidate_version,
                   Tournament.gate_spent):
            self.assertIsNone(self.WEIGHT.search(inspect.getsource(fn)), fn.__qualname__)

    def test_a_huge_practice_record_changes_the_weight_and_nothing_else(self):
        for fid in ("star", "plain"):
            self.family(fid, validation_version=1, validation_line={"passed": True}, validation_numbers={"t": 1.0, "mean": 0.01},
                        best_train_version=1)
            self.store.update_family(fid, validations=3, best_train=1.0)

        def everything():
            fams = self.store.families(alive=True)
            t = Tournament(self.store, None, self.settings, clock=self.clock)
            return {"read": bands.read(self.root), "observe": bands.observe(self.root),
                    "candidates": {f["id"]: t.candidate_version(f) for f in fams},
                    "why": {f["id"]: t._why(f, (None, None)) for f in fams},
                    "state": {f["id"]: {k: v for k, v in f.items() if k != "weight"} for f in fams}}

        Tournament(self.store, None, self.settings, clock=self.clock, rng=random.Random(3)).allocate(self.store.families())
        before = everything()
        weights_before = {f["id"]: f["weight"] for f in self.store.families()}
        self.practised("star", [(f"2026-10-{d:02d}", 30.0 + 3 * d, 50.0, False) for d in range(1, 9)],
                       days=tuple(f"2026-10-{d:02d}" for d in range(1, 9)))
        self.assertGreater(practice_summary(self.root)["rows"][0]["trades"], 5)
        Tournament(self.store, None, self.settings, clock=self.clock, rng=random.Random(3)).allocate(self.store.families())
        after = everything()
        self.assertEqual(before, after, "validation's choice, the bands, the practice rows and every rule read the same")
        weights_after = {f["id"]: f["weight"] for f in self.store.families()}
        self.assertGreater(weights_after["star"], weights_before["star"], "only the weight moved")


if __name__ == "__main__":
    unittest.main()
