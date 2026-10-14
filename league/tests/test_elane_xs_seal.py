"""THE PANEL LANE'S SEALS in the swarm (release E4; league/swarm/elane_xs.py), each a test of what cannot cross:
X6  nothing after Train reaches a generator: two stores that differ only in a panel family's Validation, look, floor,
    placebo, halves, out-of-fold, band or forward rows give the same request, brief, Train map and route choice,
    byte for byte;
X7  the reserve and the hidden year: two markets that differ only in 2021, or only inside a family's hidden year,
    give the same Train record, map, brief and stored runs, byte for byte, because no session of either is ever a
    run session of what the bar reads; a result that carries such a day is refused whole;
X8  the salt never leaves (the swarm's half): the swarm opens no SALT file, asks the store for no id, half or symbol,
    and no request, brief, event, state, stored run or decider payload holds one;
X14 the swarm reads only the twin marker (the swarm's half): ids and days of one JSON file, whatever else it holds,
    and never the forward record's own store.
league.xs is faked at its interfaces (league/tests/elane_xs_fakes.py): there the engine is an invented one whose
every run is a function of its own span alone, so what is proved is the swarm's conduct (which spans it asks for, and
what of each answer it keeps where). X7 IS ALSO HELD ON THE REAL ENGINE (`TheReserveAndTheHiddenYearOnTheRealEngine`:
package C's store and synthetic panel, package D's engine and runner through the decider's own in-process double),
from the moment those packages and package G's patches are in the tree; until then that class is skipped and says
so. Every family, program and number is invented."""

from __future__ import annotations

import builtins
import datetime as dt
import json
import re
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import elane, elane_xs, elane_yield
from league.swarm.gate import run_sha
from league.tests import elane_xs_fakes as F
from league.tests.elane_e2_fakes import FakeRouter, review_answer
from league.xs import config as xconfig

REPO = Path(__file__).resolve().parents[2]


def router():
    return FakeRouter(lambda call: review_answer("pass"))


class World(unittest.TestCase):
    """One store a world: a panel family scored on Train (and, when asked, taken through everything after it)."""

    def build(self, *, after: str | None = None, market=None, hidden=2018, code=None, settings=None):
        """A store with two panel families scored on Train. `after`: what then happens to the first ("pass": its
        Validation and a passed look; "fail": a failed look and its retirement; "refused": refused at the pre-check),
        with every sealed row those write, a band and forward rows."""
        world = F.switch_on(self)
        # THE PROGRAMS ARE THE SAME IN EVERY WORLD: what happens after Train is the market's doing (2025 and 2026 are
        # no Train year), so two worlds differ in nothing a generator may read.
        world.runner.market = {**dict(market or {}), **{"fail": {2026: -0.003}, "refused": {2025: -0.004}}.get(after, {})}
        store = F.new_store(self)
        F.ready(store.root)
        settings = settings or F.settings("gate")
        owner = F.owner(store, world, settings, router=router())
        codes = {"rev-a": code or F.good(tag="a", mkt=1.0), "mom-a": F.good(tag="b", mkt=1.0, edge=0.0)}
        for slug, agenda in (("rev-a", "xs_reversal"), ("mom-a", "xs_momentum")):
            fam = F.panel_family(store, slug, agenda=agenda, code=codes[slug], hidden=hidden)
            elane_xs.score(owner, fam, store.latest_version(slug))
        if after is not None:
            fam = store.family("rev-a")
            version = store.version("rev-a", 1)
            elane_xs.validate(owner, fam, version)
            looked = elane_xs.look(owner, store.family("rev-a"), version, run_sha(version))
            if after == "pass":
                self.assertIs(looked, True)
                store.set_band("rev-a", "probe", reason="the EquityBook")
                store.add_forward("rev-a", "real", [{"id": "eq-1", "day": "2026-10-13", "pnl": 12.5, "max_loss": 100.0}],
                                  version=1)
                store.add_forward("rev-a", "shadow", [{"id": "sh-1", "day": "2026-10-13", "pnl": 11.0,
                                                       "max_loss": 100.0}], version=1)
            elif after == "fail":
                self.assertIs(looked, False)
                store.retire("rev-a", elane.SPENT_LOOK)
            else:
                self.assertIsNone(looked)
                store.retire("rev-a", elane.SPENT_TRY)
        return store, world, owner, settings

    def views(self, store, owner, settings):
        """Everything a generator of the panel lane is shown or steered by."""
        out = {"request": elane_xs.request_text(store, settings, 4), "map": elane_xs.train_map_text(store, settings),
               "map_rows": json.dumps(elane_xs.train_map(store), sort_keys=True),
               "closed": json.dumps(elane_xs.closed_cells(store, settings)),
               "quota": str(elane_xs.quota(store, settings, 4)), "researching": str(elane_xs.researching(store))}
        for fid in ("rev-a", "mom-a"):
            fam = store.family(fid)
            out[f"brief:{fid}"] = elane_xs.brief(owner, fam)
            out[f"facts:{fid}"] = json.dumps(elane_xs.train_facts(fam), sort_keys=True)
            out[f"review:{fid}"] = elane_xs.review_question(fam, store.version(fid, 1), card={}, stage="review",
                                                            train=elane_xs.version_text(1, elane_xs.versions_of(
                                                                elane_xs.record_of(fam)).get("1") or {}))
        routes = [elane_yield.Route.of(key) for key in elane_yield.cfg(settings)["routes"]]
        for turn in range(4):
            picked, why = elane_yield.choose(store, settings, routes, turn=turn, train_key=elane_xs.STATE_KEY)
            out[f"route:{turn}"] = f"{picked.key if picked else None}|{why}"
        return out


class NothingAfterTrainReachesAGenerator(World):
    """Seal X6."""

    def test_what_happened_after_train_moves_no_generators_view(self):
        plain = self.build()
        base = self.views(plain[0], plain[2], plain[3])
        for after in ("pass", "fail", "refused"):
            store, _, owner, settings = self.build(after=after)
            state = store.family("rev-a")["state"]
            self.assertIn(elane_xs.PRECHECK_KEY, state, "the world differs: it was taken past Train")
            self.assertIn(elane_xs.TRAIN_X_KEY, state)
            got = self.views(store, owner, settings)
            self.assertEqual(sorted(got), sorted(base))
            for name in base:
                self.assertEqual(got[name], base[name], f"{name} moved with what happened after Train ({after})")

    def test_the_sealed_keys_differ_between_the_worlds_and_no_view_reads_one(self):
        store, _, owner, settings = self.build(after="pass")
        state = store.family("rev-a")["state"]
        for key in elane_xs.SEALED:
            self.assertIn(key, state, f"{key} is written in a world taken through its look")
        self.assertEqual(store.family("rev-a")["band"], "probe")
        text = "\n".join(self.views(store, owner, settings).values())
        look = state[elane_xs.LOOK_KEY]
        for secret in (look["beside"], repr(look["verdict"]["t_H"]), repr(look["verdict"]["sum_h"]),
                       repr(look["verdict"]["sum_h15"]), "own floor", "candidate", "probe", "style-open:",
                       str(state[elane_xs.HALVES_KEY]["1"]["sum_x"][0]), str(state[elane_xs.OOF_KEY]["1"]["1"]["sum_x"]),
                       str(state[elane_xs.OOF_KEY]["1"]["1.5"]["t_x"]), "identity_share", F.FAKE_SHA):
            self.assertNotIn(secret, text)

    def test_train_facts_are_built_by_whitelist(self):
        store, _, owner, settings = self.build(after="pass")
        fam = store.family("rev-a")
        facts = elane_xs.train_facts(fam)
        self.assertEqual(sorted(facts), ["agenda", "born_at", "held_out", "id", "lane", "lineage", "max_names",
                                         "mechanism", "panel", "rebalance", "record", "route", "structure", "weekday"])
        self.assertEqual(sorted(facts["record"]), ["passed_version", "status", "versions"])
        poisoned = dict(fam)
        poisoned["state"] = {**fam["state"], elane_xs.STATE_KEY: {
            **fam["state"][elane_xs.STATE_KEY], "look": "LEAK", "validation": "LEAK",
            "versions": {"1": {**fam["state"][elane_xs.STATE_KEY]["versions"]["1"], "p_plac": "LEAK", "halves": "LEAK",
                               "hidden_year": "LEAK"}}}}
        self.assertNotIn("LEAK", json.dumps(elane_xs.train_facts(poisoned)), "an unknown field of the record is not shown")
        self.assertNotIn("LEAK", elane_xs.brief(owner, poisoned))

    @unittest.skipUnless(F.PATCHED, F.HOLDS.format(n="6 and 7"))
    def test_e2s_own_request_and_brief_are_as_blind(self):
        from league.swarm import elane_births, elane_train
        from league.swarm.elane_train import EquityResearcher

        def shown(store, owner, settings):
            architect = type("A", (), {"store": store, "router": owner.router, "settings": settings,
                                       "clock": store.clock})()
            passing = elane_births.EquityPass(architect)
            quota = elane_births.EquityQuota(store, settings, now=store.clock())
            system, request = passing.request(quota)
            researcher = EquityResearcher(store, owner.router, settings, root=store.root, clock=store.clock)
            return {"system": system, "request": request, "quota": quota.text(),
                    "map": elane_train.train_map_text(store, settings),
                    "brief": researcher.brief(store.family("mom-a")), "brief-a": researcher.brief(store.family("rev-a")),
                    "counts": json.dumps(elane_yield.train_counts(store, elane_train.STATE_KEY), sort_keys=True)}

        store, _, owner, settings = self.build()
        base = shown(store, owner, settings)
        self.assertIn("THE PANEL (structure \"panel\", lane equity)", base["request"])
        self.assertIn("PANEL TRAIN MAP", base["request"])
        for after in ("pass", "fail", "refused"):
            store, _, owner, settings = self.build(after=after)
            got = shown(store, owner, settings)
            for name in base:
                self.assertEqual(got[name], base[name], f"E2's {name} moved with what happened after Train ({after})")


class TheReserveAndTheHiddenYear(World):
    """Seal X7 (the swarm's half; the module docstring says whose the engine's half is)."""

    MARKET = {year: 0.0001 * (i + 1) for i, year in enumerate((2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024))}

    def kept(self, store, owner, settings):
        """What Train leaves of a family where a generator, a map or a later reader of the store can reach it."""
        out = {}
        for fid in ("rev-a", "mom-a"):
            fam = store.family(fid)
            out[f"record:{fid}"] = json.dumps(fam["state"][elane_xs.STATE_KEY], sort_keys=True)
            out[f"brief:{fid}"] = elane_xs.brief(owner, fam)
            rows = store._all("SELECT run_id, \"window\", stress, status, summary FROM runs WHERE family=? ORDER BY run_id",
                              (fid,))
            out[f"runs:{fid}"] = json.dumps([[dict(r), store.run_result(r["run_id"])] for r in rows], sort_keys=True)
            out[f"best:{fid}"] = json.dumps([fam["best_version"], fam["best_train"]])
        out["map"] = elane_xs.train_map_text(store, settings)
        scored = [e["payload"] for e in store.events_after(0, limit=5000)
                  if e["kind"] == "swarm.elane" and e["payload"].get("pass") == "scored"]
        out["events"] = json.dumps(scored, sort_keys=True)
        return out

    def test_two_markets_that_differ_only_in_2021_or_2020_give_the_same_train(self):
        store, world, owner, settings = self.build(market=self.MARKET)
        base = self.kept(store, owner, settings)
        years = {c["start"].year for c in world.runner.calls} | {c["end"].year for c in world.runner.calls}
        self.assertFalse(years & {2016, 2020, 2021}, "no run session of a history year or of the reserve is ever asked")
        for year in (2021, 2020, 2016):
            other = self.build(market={**self.MARKET, year: -0.05})
            self.assertEqual(self.kept(other[0], other[2], other[3]), base, f"{year} reached Train")

    def test_two_markets_that_differ_only_inside_the_hidden_year_give_the_same_train(self):
        store, world, owner, settings = self.build(market=self.MARKET, hidden=2018)
        base = self.kept(store, owner, settings)
        store2, world2, owner2, settings2 = self.build(market={**self.MARKET, 2018: -0.05}, hidden=2018)
        self.assertEqual(self.kept(store2, owner2, settings2), base, "the hidden year reached the record, the map, "
                                                                   "the brief, the stored runs or an event")
        first, second = (s.family("rev-a")["state"][elane_xs.OOF_KEY]["1"]["1"]["sum_x"] for s in (store, store2))
        self.assertNotEqual(first, second, "the hidden run did read the changed year: into the sealed key alone")
        seen = [c for c in world.runner.calls if not (c["start"].year == 2018 and c["end"].year == 2018)]
        self.assertTrue(all(c["start"].year != 2018 and c["end"].year != 2018 for c in seen))
        self.assertEqual(sum(1 for c in world.runner.calls if c["start"].year == 2018), 4,
                         "two hidden runs a family, each asked after its verdict was recorded")

    def test_a_seen_year_does_move_train(self):
        base = self.build(market=self.MARKET)
        moved = self.build(market={**self.MARKET, 2019: -0.05})
        self.assertNotEqual(self.kept(moved[0], moved[2], moved[3]), self.kept(base[0], base[2], base[3]),
                            "the test would see a leak: a seen year's market reaches the record")

    def test_the_hidden_run_writes_no_run_row_no_record_field_and_no_event(self):
        store, world, owner, settings = self.build(market=self.MARKET, hidden=2023)
        rows = store._all("SELECT run_id FROM runs WHERE family='rev-a'")
        for row in rows:
            kept = store.run_result(row["run_id"])
            self.assertFalse(str(kept["start"]).startswith("2023") or str(kept["end"]).startswith("2023"))
        everything = json.dumps([e["payload"] for e in store.events_after(0, limit=5000)]) + json.dumps(
            store.family("rev-a")["state"][elane_xs.STATE_KEY])
        self.assertNotIn("2023", everything)
        self.assertNotIn(elane_xs.OOF_KEY, everything)
        self.assertNotIn("hidden", everything)

    def test_a_result_that_carries_a_day_of_the_hidden_year_or_the_reserve_is_refused_whole(self):
        for leak in ("2018-06-01", "2021-03-01", "2020-03-02", "2016-05-02", "2025-01-02"):
            store, world, owner, settings = self.build(code=F.good(tag="a", leak_day=leak), hidden=2018)
            fam = store.family("rev-a")
            self.assertEqual(elane_xs.record_of(fam)["versions"], {}, leak)
            self.assertEqual(elane_xs.record_of(fam)["infra"]["kind"], "window")
            self.assertEqual(store._all("SELECT 1 FROM runs WHERE family='rev-a'"), [])
            self.assertNotIn(elane_xs.OOF_KEY, fam["state"])
            self.assertEqual(elane_xs.train_map(store)[0]["scored"] + elane_xs.train_map(store)[1]["scored"], 1,
                             "the other family was scored; this one is judged on nothing")

    def test_the_bar_never_names_a_reserve_or_history_year_as_a_run_year(self):
        self.assertEqual(xconfig.TRAIN_YEARS, (2017, 2018, 2019, 2022, 2023, 2024))
        for hidden in (None, *xconfig.TRAIN_YEARS):
            for first, last in (*elane_xs.seen_spans(hidden), *((elane_xs.hidden_span(hidden),) if hidden else ())):
                self.assertFalse(set(range(first.year, last.year + 1)) & {2016, 2020, 2021})


def real_engine() -> str | None:
    """Why the real-engine tests cannot run in this tree, or None: package G's patches are applied and packages C, D
    and E are built (each of their functions raised NotImplementedError as a Step 0 stub)."""
    if not F.PATCHED:
        return F.HOLDS.format(n="1 and 7")
    try:
        from league.xs import results, style

        xconfig.decision_due(dt.date(2024, 1, 2), "weekly", 0)
        results.t_stat([0.0, 1.0, 2.0])
        style.style_open(None)
    except NotImplementedError:
        return "packages C, D and E of release E4 are stubs in this tree: the real engine is not built"
    return None


REVERSAL = '''import math

NEEDS = {"panel": "sp500", "history": 20, "max_names": 5, "rebalance": "weekly", "weekday": 0, "max_hold_sessions": 30}
PARAMS = {"back": 5}


def decide(ctx):
    back = int(ctx.params["back"])
    scored = []
    for row in range(ctx.n):
        total = 0.25 * float(ctx.iret[row][-1])
        for value in ctx.ret[row][-back:]:
            total += float(value)
        if total == total:
            scored.append((total, int(ctx.ids[row])))
    scored.sort()
    if len(scored) < 5:
        return {"hold": True}
    return {"target": {slot: 0.2 for _, slot in scored[:5]}, "at": "open"}
'''


@unittest.skipIf(real_engine(), real_engine() or "")
class TheReserveAndTheHiddenYearOnTheRealEngine(unittest.TestCase):
    """Seal X7 with the REAL engine (one run a seen span: no rebased view of a whole-span run could pass this). Two
    synthetic markets that differ only INSIDE the hidden year, or only inside 2021 (the OPENS of the members' bars
    from February through October: the year's closes, volumes and last sessions are the same, as release E3's fixture
    keeps them, because the stretch after reads those as look-back: 252 returns of closes for the characteristics, a
    program's `history` sessions for its fields), give the same Train record, map, brief and stored figures. The
    hidden run does read the moved opens, into the sealed key alone. STATED: a stored run's id is a hash over the
    store's files, so the two markets' run ids differ; every figure stored under them is compared."""

    base: Path

    @classmethod
    def setUpClass(cls):
        import tempfile

        from league.xs import synth

        cls._tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls._tmp.name) / "base"
        synth.synthetic_panel(cls.base / elane_xs.STORE_DIR, n_assets=30, seed=11)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def market(self, *, years_ok, moved=None):
        """A state root holding the base panel, its manifest naming `years_ok` as the covered Train years, and (with
        `moved` = (first, last)) every member bar's OPEN from `first` through `last` set to that bar's high."""
        import hashlib
        import shutil
        import tempfile

        import numpy as np

        from league.equity.store import from_ordinal

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copytree(self.base, root, dirs_exist_ok=True)
        folder = root / elane_xs.STORE_DIR / "panel"
        manifest = json.loads((root / elane_xs.STORE_DIR / elane_xs.PANEL_MANIFEST).read_text())
        if moved is not None:
            days = [from_ordinal(int(d)) for d in np.load(folder / "days.npy")]
            raw, adj = np.load(folder / "raw.npy"), np.load(folder / "adj.npy")
            rows = [i for i, day in enumerate(days) if moved[0] <= day <= moved[1]]
            self.assertGreater(len(rows), 150)
            members = slice(len(xconfig.REF), None)
            opened, high = raw[rows, members, 0], raw[rows, members, 1]
            ok = np.isfinite(opened) & np.isfinite(high) & (opened > 0)
            self.assertTrue(bool(np.any(ok & (high > opened))), "the move changes something")
            adj[rows, members, 0] = np.where(ok, adj[rows, members, 0] * np.where(ok, high / np.where(ok, opened, 1.0),
                                                                                  1.0), adj[rows, members, 0])
            raw[rows, members, 0] = np.where(ok, high, opened)
            for name, array in (("raw.npy", raw), ("adj.npy", adj)):
                np.save(folder / name, array)
                manifest["sha256"][name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        manifest["train_years_ok"] = list(years_ok)
        (root / elane_xs.STORE_DIR / elane_xs.PANEL_MANIFEST).write_text(json.dumps(manifest))
        return root

    def scored(self, root, *, hidden):
        """The family's whole Train judgment on the market at `root`, on the real engine: what Train leaves of it."""
        from league.live.decider import InlineDecider
        from league.swarm.store import SwarmStore
        from league.xs import runner as xrunner

        store = SwarmStore(root, clock=F.Clock())
        self.addCleanup(store.close)
        settings = F.settings("train")
        self.assertEqual(elane_xs.mode(settings, root), "train")
        owner = F.owner(store, F.World(), settings)
        owner.xs_runner = xrunner.Isolated(InlineDecider(), root / elane_xs.STORE_DIR, nice=None)
        fam = F.panel_family(store, "rev-real", code=REVERSAL, hidden=hidden)
        out = elane_xs.score(owner, fam, store.latest_version("rev-real"))
        fam = store.family("rev-real")
        record = fam["state"][elane_xs.STATE_KEY]
        self.assertIn("1", record["versions"], out)
        self.assertTrue(record["versions"]["1"]["facts"], "the bar read the real runs")
        rows = store._all("SELECT run_id, \"window\", stress, status, summary FROM runs WHERE family='rev-real' ORDER BY rowid")
        stored = []
        for row in rows:
            kept = store.run_result(row["run_id"])
            stored.append([row["window"], row["stress"], row["status"], row["summary"],
                           {k: kept.get(k) for k in ("status", "summary", "by_year", "pick_counts", "start", "end", "k")}])
        return {"record": json.dumps(record, sort_keys=True), "brief": elane_xs.brief(owner, fam),
                "map": elane_xs.train_map_text(store, settings), "runs": json.dumps(stored, sort_keys=True),
                "sealed": json.dumps({k: fam["state"].get(k) for k in (elane_xs.HALVES_KEY, elane_xs.PLACEBO_KEY)},
                                     sort_keys=True)}, fam["state"].get(elane_xs.OOF_KEY)

    def test_a_market_that_differs_only_inside_the_hidden_year_gives_the_same_train(self):
        years = [2017, 2018, 2019]
        plain, oof = self.scored(self.market(years_ok=years), hidden=2018)
        moved = self.market(years_ok=years, moved=(dt.date(2018, 2, 1), dt.date(2018, 10, 31)))
        other, other_oof = self.scored(moved, hidden=2018)
        for name in plain:
            self.assertEqual(other[name], plain[name], f"the hidden year reached Train's {name}")
        self.assertIsNotNone(oof)
        self.assertNotEqual(other_oof, oof, "the hidden run did read the moved opens: into the sealed key alone")

    def test_a_market_that_differs_only_inside_2021_gives_the_same_train(self):
        plain, _ = self.scored(self.market(years_ok=[2022]), hidden=None)
        moved = self.market(years_ok=[2022], moved=(dt.date(2021, 2, 1), dt.date(2021, 10, 29)))
        other, _ = self.scored(moved, hidden=None)
        for name in plain:
            self.assertEqual(other[name], plain[name], f"2021 reached Train's {name}")

    def test_a_seen_year_that_differs_does_move_train(self):
        plain, _ = self.scored(self.market(years_ok=[2022]), hidden=None)
        moved = self.market(years_ok=[2022], moved=(dt.date(2022, 2, 1), dt.date(2022, 10, 31)))
        other, _ = self.scored(moved, hidden=None)
        self.assertNotEqual(other["record"], plain["record"], "the test would see a leak")


class TheSaltNeverLeaves(World):
    """Seal X8 (the swarm's half)."""

    SALT = bytes(range(200, 232))

    def test_the_swarm_opens_no_salt_and_nothing_it_writes_or_sends_holds_one(self):
        world = F.switch_on(self)
        store = F.new_store(self)
        F.ready(store.root)
        salt = Path(store.root) / elane_xs.STORE_DIR / "universe" / "SALT"
        salt.parent.mkdir(parents=True)
        salt.write_bytes(self.SALT)
        opened: list[str] = []
        real_open, real_bytes, real_text = builtins.open, Path.read_bytes, Path.read_text

        def spy_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        def spy_bytes(path, *args, **kwargs):
            opened.append(str(path))
            return real_bytes(path, *args, **kwargs)

        def spy_text(path, *args, **kwargs):
            opened.append(str(path))
            return real_text(path, *args, **kwargs)

        settings = F.settings("live")
        owner = F.owner(store, world, settings, router=router())
        texts = []
        with mock.patch.object(builtins, "open", spy_open), mock.patch.object(Path, "read_bytes", spy_bytes), \
                mock.patch.object(Path, "read_text", spy_text):
            fam = F.panel_family(store, "rev-a", code=F.good(tag="a"), hidden=2019)
            elane_xs.score(owner, fam, store.latest_version("rev-a"))
            version = store.version("rev-a", 1)
            elane_xs.validate(owner, store.family("rev-a"), version)
            self.assertIs(elane_xs.look(owner, store.family("rev-a"), version, run_sha(version)), True)
            self.assertEqual(elane_xs.live_ready(store.root, settings), (True, None))
            texts += [elane_xs.request_text(store, settings, 4), elane_xs.brief(owner, store.family("rev-a")),
                      elane_xs.train_map_text(store, settings), json.dumps(elane_xs.view(store.family("rev-a")))]
        self.assertTrue(opened, "the spies saw the swarm's own reads")
        universe = [p for p in opened if "/universe/" in p]
        self.assertFalse([p for p in opened if p.endswith("SALT")], "the swarm never opens the salt")
        self.assertLessEqual({Path(p).name for p in universe}, {"UNIVERSE_MANIFEST.json"},
                             "of the universe's files the swarm reads the manifest's counts (the map's label), no other")
        secrets = [self.SALT.hex(), repr(self.SALT), self.SALT.decode("latin-1")]
        blob = "\n".join([*texts,
                          json.dumps([e["payload"] for e in store.events_after(0, limit=5000)]),
                          json.dumps(store.family("rev-a")["state"]), json.dumps(store.looks(), default=str),
                          json.dumps([store.run_result(r["run_id"]) for r in store._all("SELECT run_id FROM runs")]),
                          json.dumps([c for c in owner.router.calls], default=str),
                          json.dumps([i["payload"] for i in world.runner.decider.instances.values()])])
        for secret in secrets:
            self.assertNotIn(secret, blob)
        self.assertIsNone(re.search(r"\bS\d{3}\b", blob), "no symbol of the universe crosses (the fake's are S000..S499)")
        self.assertNotIn("half_of", blob)
        self.assertNotIn("\"aid\"", blob)

    def test_what_the_swarm_sends_the_decider_is_the_program_and_the_rebuilt_inputs_alone(self):
        world = F.switch_on(self)
        sent: list[tuple[str, dict]] = []
        decider = world.runner.decider
        load, kind = decider.kind_load, decider.kind
        decider.kind_load = lambda k, key, payload, **kw: (sent.append(("load", dict(payload))), load(k, key, payload))[1]
        decider.kind = lambda k, op, payload, **kw: (sent.append((op, dict(payload))), kind(k, op, payload))[1]
        code = F.good()
        run = world.runner.train(code, {}, name="p", start=xconfig.TRAIN_SEGMENTS[0][0],
                                 end=xconfig.TRAIN_SEGMENTS[0][1], k=1.5, calls=True)
        elane_xs.state_check(decider, code, {}, name="fam", runs=[run])
        self.assertEqual({tuple(sorted(p)) for op, p in sent if op == "load"},
                         {("code", "max_errors", "name", "params", "timeout")})
        for op, payload in sent:
            if op == "decide":
                self.assertEqual(sorted(payload), ["jobs"])
                for job in payload["jobs"]:
                    self.assertEqual(sorted(job), ["called", "inputs", "key"])

    def test_the_modules_name_no_salt_no_half_and_no_id_map(self):
        for name in ("league/swarm/elane_xs.py", "league/ops/xs_zero_edge.py"):
            source = (REPO / name).read_text()
            code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith(("#", "\"\"\"")))
            for word in ("read_salt", "run_salt", "ids_for", "half_of", "dither_key(", "sector_perm(", "SALT_FILE",
                         ".aid(", ".symbol(", "aids"):
                self.assertNotIn(word, code, f"{name} reaches for {word}")
        source = (REPO / "league" / "swarm" / "elane_xs.py").read_text()
        self.assertEqual(sorted(set(re.findall(r"\buniverse\.(\w+)\(", source))), ["members", "stale_days", "tradable"],
                         "of the universe the swarm asks who the members are (to count them), which are tradable, and "
                         "how stale the membership is")
        self.assertEqual(len(re.findall(r"\bUniverse\(", source)), 2, "and it builds one nowhere else")

    def test_the_tradable_share_leaves_as_a_number_and_a_refusal_names_no_symbol(self):
        world = F.switch_on(self)
        store = F.new_store(self)
        F.ready(store.root)
        world.tradable = 0.5
        ok, why = elane_xs.live_ready(store.root, F.settings("live"))
        self.assertFalse(ok)
        self.assertIsNone(re.search(r"S\d{3}", why))


class TheSwarmReadsOnlyTheMarker(unittest.TestCase):
    """Seal X14 (the swarm's half)."""

    def setUp(self):
        self.world = F.switch_on(self)
        self.store = F.new_store(self)
        self.root = self.store.root
        self.settings = F.settings("live")
        F.ready(self.root)

    def test_two_markers_that_differ_in_everything_but_ids_and_days_read_the_same(self):
        from league.xs import book

        rows = {"fam@1:r": {"due": "2026-10-08", "last": "2026-10-08"}, "oth@2:r": {"due": None, "last": None}}
        F.write_twins(self.root, instances=rows)
        plain = (elane_xs.live_ready(self.root, self.settings), elane_xs.mode(self.settings, self.root))
        path = Path(self.root) / elane_xs.STORE_DIR / book.TWINS_FILE
        doc = json.loads(path.read_text())
        doc["agreement"] = {"fam@1:r": 0.25}
        doc["at"] = "2030-01-01T00:00:00Z"
        doc["instances"] = {key: {**row, "agree": False, "gap_bp": 99.0, "symbols": ["AAPL"]} for key, row in rows.items()}
        path.write_text(json.dumps(doc))
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
        self.assertEqual((elane_xs.live_ready(self.root, self.settings), elane_xs.mode(self.settings, self.root)), plain)
        self.assertEqual(plain, ((True, None), "live"))

    def test_the_live_legs_open_no_database(self):
        with mock.patch.object(sqlite3, "connect", side_effect=AssertionError("a database was opened")):
            self.assertEqual(elane_xs.live_ready(self.root, self.settings), (True, None))
            self.assertEqual(elane_xs.mode(self.settings, self.root), "live")
            self.assertTrue(elane_xs.seatable(self.root)("etf"))

    def test_no_file_of_the_swarm_names_the_forward_store_or_one_of_its_tables(self):
        source = (REPO / "league" / "swarm" / "elane_xs.py").read_text()
        self.assertNotIn("forward.sqlite", source, "release E3's seal T1 reads every file of league/swarm")
        self.assertIsNone(re.search(r"\bfwd_\w+", source))
        self.assertNotIn("sqlite", source, "the panel lane opens no database of its own: the swarm's store is handed in")
        self.assertNotIn("forward", (REPO / "league" / "ops" / "xs_zero_edge.py").read_text())

    def test_with_no_marker_live_reads_as_gate(self):
        from league.xs import book

        (Path(self.root) / elane_xs.STORE_DIR / book.TWINS_FILE).unlink()
        with elane_xs._cache_lock:
            elane_xs._mode_cache.clear()
        self.assertEqual(elane_xs.mode(self.settings, self.root), "gate", "no marker: no twin, no live seat")
        self.assertFalse(elane_xs.seatable(self.root)("panel"))


if __name__ == "__main__":
    unittest.main()
