"""WHAT MAIN'S THREE NEW RULES DO FOR A PANEL PROGRAM (release E4 merged with main 8ab31e32: releases E5-A and E3.1).

Release E4 ships in two steps. In STEP ONE the panel lane's switch reaches "train" at most: no panel look runs, no
panel family is banded, the book holds no panel instance and no money row names the panel. The release main deployed
beside it (22:51Z Oct 11, 2026) brought three rules the panel kind had never met. Each is decided, said in
league/swarm/E4.md ("The merge with main's releases E5-A and E3.1") and held here.

1. THE SEAT RULE (A24 with A30; league/equity/live.py `_seat_bands`). IN STEP ONE A PANEL FAMILY NEVER ENTERS THE
   SEAT PLAN, never counts against the six seats, never holds a seat and never yields one. The book builds its plan
   from the rows the swarm's reader gives it and from nothing else, and the reader gives a panel family a row only
   while the lane's effective mode is "live" (league/swarm/bands.py `_read_equity`: a panel Candidate is seatless, a
   panel family in a running band is hidden), which step one cannot reach at any setting: the universe deploy is
   step two's. `APanelFamilyNeverReachesTheSeatPlan` puts into the store what step one cannot make (a panel family in
   each of the Candidate, Probe and Sized bands, passed, its proof current) and holds that the reader shows none of
   them, queued or not, at every setting, and that the book's plan, its six seats, its yield and its orders are main's
   own record to the row. The swarm's side of the rule, the backfill of K's two counts (league/swarm/elane.py
   `seat_backfill`), reads the Candidate, Probe and Sized bands: it passes a panel family in Train research by and
   writes a share program's counts as on main. (STEP TWO gives the panel its own pool of seats,
   `equity_money.panel`: a panel family that does reach the plan enters that pool alone, never the six:
   league/tests/test_equity_panel_seats.py.)
2. AN EXIT'S WAIT FOR THE PRACTICE PROOF HAS AN END (A28; `_work_exit`). It covers a panel basket's exits like any
   other: `_work_exit` asks nothing of an instance's kind. A rotation's sale and the House's exit of a name that left
   the eligible set wait for the SELL stage inside the open window and go at the entry cut-off, with the one alert a
   session. What is the panel kind's own is stated beside it: the basket's buy of that open is sized against the lots
   not yet sold (B8), so it waits with them and the cut-off records it missed; the standing target plans it again at
   the next close (`TheExitWaitsEndCoversAPanelBasket`).
3. THE TWIN IS RE-BASED AFTER A DIFFERENCE (A29; league/ops/forward_twins.py). STEP TWO APPLIES IT, AS REGISTERED,
   TO THE PANEL TWIN, on the panel night's own code (league/ops/forward_xs.py `PanelChain` over league/xs/book.py
   `TwinAccount`, the Gym engine's account driven from ops): a differing session counts once, a `twin_rebased`
   event is written, and the rows carry A29's two columns. E3.1's code is still never handed a panel instance.
   `ThePanelTwinIsReBasedByItsOwnNight` holds it; league/tests/test_forward_xs_twin.py holds the re-base itself.

Every program, price, panel and figure here is invented."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401 - the panel adapter and the synthetic panel need it
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league.equity import LANES
from league.equity import live as L
from league.tests import equity_week as W

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "equity_etf_orders.json"
#: Every value `elane.panel.mode` can be set to, and no key at all. Step one's effective mode is never "live".
SETTINGS = ("", "off", "train", "gate", "live")
#: The bands a panel family is forced into (step one makes none of them).
FORCED = ("candidate", "probe", "sized")
PANEL_IDS = [f"xs-forced-{band}" for band in FORCED]
TOLD = "the sale path is unproven"


@unittest.skipUnless(HAVE, "numpy not installed")
class APanelFamilyNeverReachesTheSeatPlan(unittest.TestCase):
    maxDiff = None

    def store(self, setting: str):
        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        clock = W.Clock(W.at(W.FRIDAY, 16, 0))
        families = W.store_families(root, W.ranked_programs(1), clock, setting, forced=FORCED)
        self.addCleanup(lambda: families._store is not None and families._store.close())
        return root, clock, families

    def test_the_reader_gives_the_book_no_panel_row_at_any_setting(self):
        from league.swarm import bands, elane_xs
        from league.swarm import settings as settings_mod
        from league.swarm.store import SwarmStore

        etf = sorted(p["family"] for p in W.ranked_programs(1))
        for setting in SETTINGS:
            with self.subTest(setting=setting or "no key"):
                root, clock, families = self.store(setting)
                store = SwarmStore(root, clock=clock)
                self.addCleanup(store.close)
                held = {f["id"]: f["band"] for f in store.families(lanes="all") if f["structure"] == "panel"}
                self.assertEqual({k: v for k, v in held.items() if k in PANEL_IDS},
                                 dict(zip(PANEL_IDS, FORCED)), "the store holds a panel family in every band")
                self.assertNotEqual(elane_xs.mode(settings_mod.load(root), root), "live",
                                    "step one: the universe deploy is step two's, so no setting reads live")
                # THE SEAT RULE's read (`queued`): every passed ETF Candidate has a row; no panel family has.
                queued = bands.read(root, lanes=LANES, strict=True, queued=True)
                self.assertEqual(sorted(r["family"] for r in queued), etf)
                self.assertEqual({r["structure"] for r in queued}, {"etf"})
                self.assertEqual(sorted(r["family"] for r in queued if r["seat"] == "queue"), ["bred-e-wait"])
                # ... and the read under "first-come" (the rollback): the six that hold a seat.
                plain = bands.read(root, lanes=LANES, strict=True)
                self.assertEqual(sorted(r["family"] for r in plain), sorted(set(etf) - {"bred-e-wait"}))
                # The book's own reader, the rule in force:
                rows = families.read()
                self.assertEqual((families.last_error, sorted(r["family"] for r in rows)), ("", etf))
                for fid in PANEL_IDS:
                    self.assertEqual(families.read(fid), [], fid)
                # The roster's report says where the panel Candidate stands and why: seatless, never waiting.
                roster = bands.roster(root, lanes=LANES)
                self.assertEqual(roster["seatless"], ["xs-forced-candidate"])
                # (the captain's A34, release U: a panel Candidate that holds no FWD1-R forward seat holds no seat at
                # all, at any setting; under the route as built the reason is the lane's leg)
                self.assertEqual(roster["seatless_why"]["xs-forced-candidate"], elane_xs.A34_SEATLESS)
                with mock.patch.object(elane_xs, "A34_FORWARD_ONLY", False):
                    built = bands.roster(root, lanes=LANES)
                self.assertEqual(built["seatless"], ["xs-forced-candidate"])
                self.assertIn("the panel lane is not live", built["seatless_why"]["xs-forced-candidate"])
                self.assertEqual(roster["waiting"], ["bred-e-wait"])

    def test_the_plan_the_six_seats_the_yield_and_the_orders_are_mains_with_panel_families_in_every_band(self):
        """The thirteen sessions of the seat rule through the REAL reader, the store also holding a panel family in
        the Candidate, the Probe and the Sized band: what main's book did with no panel family anywhere, to the row
        (main's record), so none of them took a seat, counted against the six, or yielded."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["store"]
        for name in ("fortnight: an idle seat yields to the waiting program",
                     "fortnight: two programs wait, one idle seat yields a decision day",
                     "fortnight: nobody waits, the idle seats are kept"):
            for setting in ("train", "live"):
                with self.subTest(scenario=name, setting=setting):
                    snap = W.run(name, reader="store", panel=setting, forced=FORCED)
                    self.assertEqual(W.kept(snap, whole=False), fixture[name])
                    plan = json.loads(snap["kv"]["eq_seat"])
                    self.assertEqual((plan["rule"], plan["seats"]), ("activity-1-free", 6))
                    # (Six ETF holders while a program waits; five at the end of the scenario with nobody waiting,
                    # where main's own band rule demoted one on the last decision day and no one took its seat.)
                    self.assertEqual(len(plan["holders"]), 5 if "nobody waits" in name else 6)
                    named = {h["family"] for h in plan["holders"]} | {w["family"] for w in plan["waiting"]} \
                        | set(plan["idle"]) | set(plan["sticky"])
                    self.assertFalse({n for n in named if n.startswith("xs-")}, "no panel family in the plan")
                    text = json.dumps([snap["seats"], snap["records"], snap["alerts"], snap["instances"]])
                    self.assertNotIn("xs-forced", text, "nor in a seat's record, an alert or an instance row")
                    self.assertEqual({row[W.E4_COLUMN] for row in snap["instances"]}, {"equity"})

    def test_a_forced_panel_family_takes_no_seat_from_an_etf_candidate(self):
        """NEVER COUNTED AGAINST THE SIX SEATS, with seats to count: four ETF programs seated and two ETF Candidates
        passed (the recorded scenario of Friday's decide). With a panel family forced into the Probe and the Sized
        band both Candidates still take their seats, as on main: the book counts the rows it is given.

        THE ROLLBACK, stated: under "first-come" it is the swarm's roster that counts, and it counts the families
        the store holds in the Probe band A POOL AT A TIME (step two: league/swarm/bands.py `equity_seating`). A
        panel family in the Probe band holds the panel pool's seat, never one of the six, so a forced panel Probe
        family costs no ETF Candidate its seat under the rollback either. Step one puts no panel family in any band
        (no panel look runs under "gate"); what "train" makes is held below on the store."""
        from league.swarm.store import SwarmStore
        from league.tests.equity_design import seat_rule

        name = "two Candidates take their seats at Friday's decide"
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["store"]
        snap = W.run(name, reader="store", panel="train", forced=("probe", "sized"))
        self.assertEqual(W.kept(snap, whole=False), fixture[name])
        self.assertEqual(len(json.loads(snap["kv"]["eq_seat"])["holders"]), 6)
        with seat_rule("first-come"):
            plain = W.run(name, reader="store", panel="train")
            forced = W.run(name, reader="store", panel="train", forced=("probe",))
        seated = lambda s: sorted(r["family"] for r in s["instances"] if r["retired_at"] is None)  # noqa: E731
        self.assertEqual(len(seated(plain)), 6, "the rollback on the store as step one makes it: six ETF seats")
        self.assertEqual(len([f for f in seated(forced) if not f.startswith("xs-")]), 6,
                         "a panel family in the Probe band holds the panel pool's seat, never an ETF one")
        # What "train" makes: a panel family in Train research, band "gym". None in a band the roster reads.
        root, clock, families = self.store("train")
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)
        made = [f for f in store.families(lanes="all") if f["structure"] == "panel" and not f["id"].startswith("xs-forced")]
        self.assertEqual([(f["id"], f["band"]) for f in made], [("xs-in-train", "gym")])

    def test_the_backfill_of_the_seat_rules_counts_passes_a_panel_family_by(self):
        """THE SWARM'S SIDE OF THE SEAT RULE (league/swarm/elane.py `seat_backfill`: K's two counts for the programs
        that passed before they were kept). It reads the Candidate, Probe and Sized bands. At "train" a panel family
        is in Train research (band "gym"): the backfill makes the count an ETF program is owed, exactly as on main,
        and neither runs nor names the panel family."""
        from types import SimpleNamespace

        from league.swarm import elane
        from league.swarm import settings as settings_mod
        from league.swarm.store import SwarmStore

        tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        clock = W.Clock(W.at(W.FRIDAY, 16, 0))
        families = W.store_families(root, W.ranked_programs(1), clock, "train")
        self.addCleanup(lambda: families._store is not None and families._store.close())
        store = SwarmStore(root, clock=clock)
        self.addCleanup(store.close)
        self.assertEqual([(f["id"], f["band"]) for f in store.families(lanes="all") if f["structure"] == "panel"],
                         [("xs-in-train", "gym")])
        store.set_state("bred-e-wait", **{elane.SEAT_KEY: None})            # one ETF program is owed its counts
        asked: list[str] = []

        class Runner:
            """The House's isolated runner at the interface the backfill reads: invented whole runs."""

            def validation(self, code, params, *, name, k):
                asked.append(name)
                return SimpleNamespace(result={"status": "ok", "daily": [{}] * 250,
                                               "lots": [{"exit_day": f"2025-03-{d:02d}", "weight": 0.3} for d in (3, 4, 5)]})

            def segments(self, code, params, *, name):
                asked.append(name)
                return [SimpleNamespace(result={"status": "ok", "daily": [{}] * 500,
                                                "lots": [{"exit_day": "2023-05-02", "weight": 0.3}]})]

        gate = SimpleNamespace(store=store, settings=settings_mod.load(root), clock=clock, equity_runner=Runner())
        self.assertEqual(elane.seat_backfill(gate), ["bred-e-wait"])
        self.assertEqual(asked, ["bred-e-wait", "bred-e-wait"], "the one program owed, and no panel program")
        held = store.family("bred-e-wait")["state"][elane.SEAT_KEY]
        self.assertEqual((held["validation"], held["train"]), ({"close_days": 3, "sessions": 250},
                                                               {"close_days": 1, "sessions": 500}))
        self.assertNotIn(elane.SEAT_KEY, store.family("xs-in-train")["state"])
        counted = [e["family"] for e in store.events_after(0, limit=5000)
                   if str((e["payload"] or {}).get("action") or "").startswith(("seat_counts", "equity_seat_counts"))]
        self.assertEqual(counted, ["bred-e-wait"], "one event, the ETF program's; none names the panel family")
        self.assertEqual(elane.seat_backfill(gate), [], "once")

    def test_the_plan_is_built_from_the_readers_rows_alone(self):
        """Why the reader's answer is the whole proof: `_seat_bands` counts its holders and its waiting from the rows
        it is handed (the seats there are less the rows in a running band), and `_sync_instances` hands it
        `families.read()` and nothing else."""
        import inspect

        sync = inspect.getsource(L.EquityBook._sync_instances)
        self.assertIn("rows = [dict(r) for r in self.families.read() if str(r.get(\"lane\") or \"\") in _pkg.LANES]", sync)
        self.assertIn("pools = self._pools(rows)", sync)
        self.assertIn("self._seat_bands(part, et, rule, sticky, since, day, now, out, late=late, counts_from=counts_from,",
                      sync)
        # (STEP TWO: a pool at a time; the ETF pool is the rows of the book's own kind, `_pools`)
        pools = inspect.getsource(L.EquityBook._pools)
        self.assertIn("etf = [r for r in rows if K.kind_of(r.get(\"structure\")) == EQUITY_KIND]", pools)
        seat = inspect.getsource(L.EquityBook._seat_bands)
        self.assertIn("holders = [r for r in rows if r.get(\"band\") in LIVE_BANDS]", seat)
        self.assertIn("waiting = [r for r in rows if r.get(\"band\") == \"candidate\" and r.get(\"holdout_passed\") "
                      "and key_of(r) not in sticky]", seat)
        self.assertIn("free = max(0, seats - len(holders))", seat)


try:
    from league.tests import test_equity_book_panel as P
except Exception:  # noqa: BLE001 - no numpy: the class below is skipped with its base
    P = None


@unittest.skipUnless(HAVE and P is not None and P.APPLIED, "the panel kind is not in this tree's book")
class TheExitWaitsEndCoversAPanelBasket(P.PanelCase if P is not None else unittest.TestCase):
    """A basket of five names; the program rotates one out (its own sale) and one in at Monday's open, and the House
    exits a second name that left the eligible set. The practice sale is not witnessed."""

    def setUp(self):
        super().setUp()
        lots = {lot.symbol: lot for lot in self.basket(("N000", "N001", "N002", "N003"))}
        self.h.seed("N004", "71.45")
        self.h.plan(["N000", "N001", "N002", "N004", "N010"])         # N003 out, N010 in
        self.h.decide(P.FRIDAY)
        self.h.intent(self.h.instance_now(), "house_exit", symbol="N001", lid=lots["N001"].lid, tag="ineligible")
        self.lots = lots
        self.h.proof.sell = False                                     # stage BUY passed; the SELL stage has not

    def exits(self):
        return [i for i in self.h.panel_intents() if i.kind in L.EXIT_KINDS]

    def test_its_exits_wait_inside_the_open_window_and_go_at_the_cut_off(self):
        h = self.h
        self.assertEqual(h.instance_now().kind, "panel")
        self.assertEqual(sorted((i.kind, i.symbol) for i in self.exits()), [("house_exit", "N001"), ("sell", "N003")])
        h.run(P.MONDAY, (9, 26), *[(9, mm) for mm in range(31, 45)])
        self.assertEqual(h.venue.sent, [], "the practice sale has the open window to go first: a basket's too")
        for intent in self.exits():
            self.assertEqual(intent.status, "planned")
            self.assertIn("SELL stage", intent.why)
        self.assertEqual(h.said(TOLD), [])
        h.tick(9, 45, day=P.MONDAY)
        self.assertEqual(sorted(b["symbol"] for b in h.sent("sell")), ["N001", "N003"], "both go at the cut-off")
        h.tick(9, 46, day=P.MONDAY)
        closed = {s: h.book._lot(self.lots[s].lid) for s in ("N001", "N003")}
        self.assertEqual({s: (lot.status, lot.reason, lot.exit_at) for s, lot in closed.items()},
                         {"N001": ("closed", "ineligible", "open"), "N003": ("closed", "program", "open")})
        self.assertEqual(len(h.said(TOLD)), 1, "the owner is told once a session, whatever the number of exits")
        self.assertEqual(h.state.get("eq_sell_unproven")["day"], P.MONDAY.isoformat())

    def test_the_baskets_buy_of_that_open_waits_with_its_sales_and_is_missed_not_cut(self):
        """THE PANEL KIND'S OWN COST of an unwitnessed practice sale: the rotation's buy is sized against the lots
        its own program has not sold yet (B8), so it waits as long as they do, and the cut-off that lets the sales
        go is the minute that records the buy missed. It is never sent at the cut size."""
        h = self.h
        h.run(P.MONDAY, (9, 26), *[(9, mm) for mm in range(31, 47)])
        self.assertEqual(h.sent("buy"), [])
        [buy] = h.panel_intents(kind="buy")
        self.assertEqual((buy.symbol, buy.status), ("N010", "missed"))
        self.assertIn("exit(s) of its own program", buy.why)
        self.assertEqual(h.held(), ["N000", "N002", "N004"], "the two exits are out; nothing was bought")
        # ... and the standing target plans the name again at Monday's close, for Tuesday's open (a hold day: no
        # program code runs).
        h.proof.sell = True
        h.decide(P.MONDAY)
        again = [(i.kind, i.symbol, i.status, i.exec_day) for i in h.panel_intents(decided_day=P.MONDAY.isoformat())]
        self.assertEqual(again, [("buy", "N010", "planned", P.TUESDAY.isoformat())])

    def test_a_stage_that_passes_in_the_window_releases_the_basket_at_once(self):
        h = self.h
        h.run(P.MONDAY, (9, 26), (9, 31))
        self.assertEqual(h.venue.sent, [])
        h.proof.sell = True
        h.tick(9, 32, day=P.MONDAY)
        self.assertEqual(sorted(b["symbol"] for b in h.sent("sell")), ["N001", "N003"])
        h.run(P.MONDAY, *[(9, mm) for mm in range(33, 47)])
        self.assertEqual(h.said(TOLD), [])
        self.assertEqual([b["symbol"] for b in h.sent("buy")], ["N010"], "and its buy goes whole once they filled")


try:
    from league.tests import test_forward_xs_twin as XT
except Exception:  # noqa: BLE001 - no numpy
    XT = None


@unittest.skipUnless(HAVE and XT is not None, "numpy not installed")
class ThePanelTwinIsReBasedByItsOwnNight(unittest.TestCase):
    """A29's re-base is E3.1's for the twins E3's night makes; STEP TWO applies it, as registered, to the panel
    night's own twin (league/ops/forward_xs.py `PanelChain`, over league/xs/book.py `TwinAccount`): E3.1's code is
    never handed a panel instance, and the panel twin's rows carry A29's two columns."""

    def test_a_differing_session_counts_once_and_the_twin_is_re_based(self):
        from league.ops import forward_db, forward_report, forward_twins

        s = XT.Seated(self)
        day = s.reweighted()

        def never(*args, **kw):
            raise AssertionError("a panel instance's twin was handed to E3.1's re-base")

        with mock.patch.object(forward_twins, "RebasedTwin", never), mock.patch.object(forward_twins, "live_seed", never):
            s.night(15)
        rows = s.rows()
        self.assertGreater(len(rows), 8)
        self.assertEqual([r["day"] for r in rows if r["agree"] == 0], [day], "the differing session, as registered")
        self.assertEqual([e["day"] for e in forward_db.events(s.h.db, "twin_rebased")], [day])
        self.assertTrue(all(r["rebased"] == (1 if r["day"] > day else 0) for r in rows))
        self.assertTrue(all(r["base_agree"] is not None for r in rows if r["agree"] is not None))
        closes = [{"equity": True, "pid": f"eq:{lot['lid']}", "instance": s.iid, "day": lot["exit_day"],
                   "opened_day": lot["entry_day"]} for lot in s.lots
                  if lot.get("exit_day") and lot["exit_day"] <= s.days[13].isoformat()]
        reading = forward_twins.a14_reading(s.h.root, closes)
        [beside] = reading["rebase"]["by_instance"]
        self.assertEqual(beside["rebases"], 1)
        self.assertEqual(reading["intents"]["disagreed"], 1)
        seen = forward_report._rebase([dict(r) for r in rows], {s.pid})
        self.assertEqual(seen["rebases"], 1)

    def test_the_hand_over_comes_before_e3_1s_re_base(self):
        """Where it is decided: `_one_instance` hands a panel instance to the panel night before the first line of
        A29's loop for E3's twins; the panel night re-bases with its own chain and writes A29's two columns."""
        import inspect

        from league.ops import forward_twins, forward_xs

        source = inspect.getsource(forward_twins._one_instance)
        self.assertLess(source.index("return forward_xs.twin("), source.index("RebasedTwin("))
        twin = inspect.getsource(forward_xs.twin)
        self.assertNotIn("RebasedTwin", twin)
        self.assertIn("PanelChain(", twin)
        self.assertIn("rebased, base_agree) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", twin)


if __name__ == "__main__":
    unittest.main()
