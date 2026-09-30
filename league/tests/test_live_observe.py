"""The observe band (the sprint, B4, Sept 26, 2026): every alive Gym-band family's validated version trades live shadow,
pinned for the session, never real, never a forward row, never on the site; its programs in their own decider child.
With the fakes of `live_fakes` (the venue's shapes, invented numbers) and the in-process decider."""

import datetime as dt
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.live.decider import DeciderError, InlineDecider
    from league.live.families import MemoryFamilies, SwarmFamilies, _entry_matches
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, VERTICAL, at, family

TUESDAY = MONDAY + dt.timedelta(days=1)


def observed(name, *, version=1, t=1.0, params=None, code=None):
    return {"family": name, "version": version, "code": code or VERTICAL, "params": dict(params or {"hold": 600}),
            "structure": "debit_vertical", "roots": ["SPY"], "run_sha": f"sha-{name}-{version}", "validation_t": t,
            "validated_version": version}


@unittest.skipUnless(HAVE, "numpy not installed")
class ObserveCase(LiveCase):
    def switches(self, **live):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, **live}}))

    def restart(self, **kw):
        """A new House process on the same state root and the same swarm."""
        self.live.state.close()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=kw.get("decider") or InlineDecider(),
                                config={"require_paper_proof": False}, real_money=kw.get("real_money", False),
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live


class TheBand(ObserveCase):
    def test_every_validated_gym_family_trades_shadow_only_and_never_reaches_the_forward_record(self):
        live = self.make([], observed=[observed("obs", params={"hold": 3})])
        self.run_to(9, 45)
        inst = live.instances["obs@1:o"]
        self.assertEqual((inst.kind, inst.observe, inst.tuition, inst.band), ("shadow", True, False, "gym"))
        acc = live.shadow.accounts["obs@1:o"]
        self.assertTrue(acc.trades, "it traded the shadow book on live quotes")
        self.assertEqual(self.venue.sent, [], "never real")
        self.assertEqual(self.families.forward, {}, "never a forward row")
        self.assertEqual(self.families.moves, [], "never a band move")
        self.assertEqual(acc.new_trades(), [], "its trades are consumed, not kept to be sent")
        self.assertTrue(live.health()["instances"]["obs@1:o"]["observe"])
        self.assertEqual(live.state.get("observe_pins")["versions"], {"obs": 1})

    def test_the_site_never_shows_an_observe_structure(self):
        live = self.make([family("vert", VERTICAL, band="candidate", params={"hold": 600})],
                         observed=[observed("obs")], real_money=False)
        self.run_to(9, 36)
        self.assertTrue(live.shadow.accounts["obs@1:o"].positions)
        agents = {row["agent"] for row in live.site_inputs()["structures"]}
        self.assertEqual(agents, {"vert"})

    def test_a_family_never_validated_has_no_instance_until_it_is(self):
        live = self.make([], observed=[])
        self.run_to(9, 33)
        self.assertFalse([k for k in live.instances if k.endswith(":o")])
        self.families.observed["late"] = {1: dict(observed("late"), observe=True, band="gym")}
        self.clock.set(self.clock() + 300)
        live.minute()
        self.assertIn("late@1:o", live.instances, "validated mid-session: it joins, its version pinned from then")


class Pins(ObserveCase):
    def test_the_version_is_frozen_across_a_restart_and_the_next_session(self):
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 33)
        self.assertIn("obs@1:o", live.instances)
        before = dict(live.shadow.accounts["obs@1:o"].positions)
        self.assertTrue(before)
        self.families.observed["obs"][2] = dict(observed("obs", version=2), observe=True, band="gym")
        live.sync_families(self.clock(), force=True)
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["obs@1:o"], "pinned for the session")
        live = self.restart()
        self.clock.set(self.clock() + 60)
        live.minute()
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["obs@1:o"],
                         "a restart keeps the session's pin (the live state), not the swarm's newer version")
        self.assertEqual(set(live.shadow.accounts["obs@1:o"].positions), set(before), "and its shadow book")
        self.clock.set(at(TUESDAY, 9, 31))
        live.minute()
        self.assertNotIn("obs@2:o", live.instances, "the cohort needs several sessions before replacing its program")
        self.assertEqual(live.instances["obs@1:o"].mode, "live")
        self.clock.set(at(TUESDAY, 9, 40))
        for _ in range(3):
            live.minute()
            self.clock.set(self.clock() + 60)
        self.assertIn("obs@1:o", live.instances)
        self.assertIn("obs@1:o", live.shadow.accounts)
        self.assertEqual(self.families.forward, {})

    def test_research_retirement_keeps_the_frozen_practice_cohort(self):
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 34)
        self.assertTrue(live.shadow.accounts["obs@1:o"].positions)
        del self.families.observed["obs"]                                  # retired (or promoted out of the Gym band)
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["obs@1:o"].mode, "live")
        self.run_to(9, 40)
        self.assertIn("obs@1:o", live.instances)
        self.assertIn("obs@1:o", live.shadow.accounts)
        self.assertEqual(live.state.get("observe_pins")["order"], ["obs"])
        self.assertEqual(self.families.forward, {})
        self.assertEqual(self.venue.sent, [])

    def test_the_cap_holds_the_likeliest_and_says_which_it_held_back(self):
        self.switches(observe_max=2)
        live = self.make([], observed=[observed("a", t=1.0), observed("b", t=3.0), observed("c", t=2.0)])
        self.run_to(9, 32)
        self.assertEqual(sorted(k for k in live.instances if k.endswith(":o")), ["b@1:o", "c@1:o"])
        [(record, _)] = self.ledger.of("live.observe")
        self.assertEqual(record["capped"], ["a"])
        self.run_to(9, 40)
        self.assertEqual(len(self.ledger.of("live.observe")), 1, "said once a day")
        # Lowered at runtime (no deploy): the first pinned stay. The switches are read once a minute pass; the families
        # every five minutes (here at once).
        self.switches(observe_max=1)
        live._switches = None
        live.sync_families(self.clock(), force=True)
        self.assertEqual(live.instances["c@1:o"].mode, "wind_down")
        self.assertEqual(live.instances["b@1:o"].mode, "live")

    def test_the_switch_turns_it_off_and_on_without_a_deploy(self):
        self.switches(observe=False)
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 33)
        self.assertFalse([k for k in live.instances if k.endswith(":o")])
        self.switches(observe=True)
        self.run_to(9, 34)
        self.assertIn("obs@1:o", live.instances, "the first minute after it is switched on pins it")
        self.switches(observe=False)
        self.run_to(9, 39)                                                   # the next families pass (every five minutes)
        self.assertEqual(live.instances["obs@1:o"].mode, "wind_down")

    def test_a_malformed_switch_is_off_and_a_malformed_cap_is_the_default(self):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"observe": "true", "observe_max": "lots", "calibration": 1}}))
        live = self.make([])
        sw = live.switches()
        self.assertEqual((sw["observe"], sw["observe_max"], sw["calibration"]), (False, 48, False))


class NeverACandidate(ObserveCase):
    def test_an_observe_row_admits_only_an_observe_shadow_open(self):
        row = dict(observed("obs"), observe=True, band="gym")
        ident = {"family": "obs", "version": 1, "code": VERTICAL, "params": {"hold": 600}, "band": "gym", "tuition": False,
                 "observe": True}
        self.assertTrue(_entry_matches(row, ident, False))
        self.assertFalse(_entry_matches(row, ident, True), "never real")
        self.assertFalse(_entry_matches(row, dict(ident, tuition=True), False), "never tuition")
        self.assertFalse(_entry_matches(row, dict(ident, observe=False), False), "an observe row is no Candidate's row")
        cand = dict(row, observe=False, band="candidate")
        self.assertFalse(_entry_matches(cand, ident, False), "a Candidate's row admits no observe instance")
        self.assertFalse(_entry_matches(dict(row, band="candidate"), ident, False), "promoted: it leaves the band")
        families = MemoryFamilies([], [observed("obs")])
        with families.admit_open(ident, real=True) as allowed:
            self.assertFalse(allowed)
        with families.admit_open(ident, real=False) as allowed:
            self.assertTrue(allowed)
        with families.admit_open(dict(ident, version=2), real=False) as allowed:
            self.assertFalse(allowed, "only the pinned version's program")


class OwnChild(ObserveCase):
    def test_observe_programs_run_in_their_own_child_after_the_real_orders_went(self):
        main, other = InlineDecider(), InlineDecider()
        seen = []
        decide = other.decide

        def watched(*args, **kwargs):
            seen.append(len(self.venue.sent))
            return decide(*args, **kwargs)

        other.decide = watched
        self.families = MemoryFamilies([family("vert", VERTICAL, band="probe")], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.run_to(9, 33)
        self.assertIn("obs@1:o", other.loaded)
        self.assertNotIn("obs@1:o", main.loaded)
        self.assertIn("vert@1:r", main.loaded)
        self.assertTrue(seen)
        self.assertEqual(seen[0], 1, "the minute's real open had gone before the observe band was asked")

    def test_a_failing_observe_child_never_costs_a_real_decision(self):
        main, other = InlineDecider(), InlineDecider()

        def broken(*args, **kwargs):
            raise DeciderError("an observe program hung; the child was killed")

        other.decide = broken
        self.families = MemoryFamilies([family("vert", VERTICAL, band="probe")], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        out = self.run_to(9, 33)
        self.assertEqual(len(self.venue.sent), 1)
        self.assertTrue(any("the observe band" in text for _, text in self.alerts))
        self.assertIn("observe_decider", out)
        self.assertNotIn("decider", out)


class TheMinute(ObserveCase):
    """The review of #390 (lenses 1 and 2): the observe band never spends what the real path needs."""

    def test_the_real_batch_keeps_its_budget_and_observe_programs_load_after_it(self):
        main, other = InlineDecider(), InlineDecider()
        log = []
        decide, load = main.decide, other.load

        def timed_decide(*args, **kwargs):
            log.append(("real", kwargs.get("budget_seconds")))
            return decide(*args, **kwargs)

        def slow_load(*args, **kwargs):
            log.append(("load", kwargs.get("budget_seconds")))
            time.sleep(0.01)
            return load(*args, **kwargs)

        main.decide, other.load = timed_decide, slow_load
        self.families = MemoryFamilies([family("vert", VERTICAL, band="probe")],
                                       [observed(f"obs-{i:02d}", t=float(i)) for i in range(48)])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.clock.set(at(MONDAY, 9, 31))
        self.live.minute()
        first = log.index(("real", log[0][1])) if log and log[0][0] == "real" else None
        self.assertEqual(first, 0, "the real batch is asked before any observe program loads")
        self.assertGreater(log[0][1], 30.0, "with the minute's budget intact")
        loads = [e for e in log if e[0] == "load"]
        self.assertEqual(len(loads), 16, "at most `observe_loads_minute` loads a minute")
        self.assertEqual(len(self.venue.sent), 1, "the real open went")
        for _ in range(3):
            self.clock.set(self.clock() + 60)
            self.live.minute()
        self.assertEqual(sum(1 for i in self.live.instances.values() if i.observe and i.loaded and not i.error), 48)

    def test_a_failed_load_gets_its_shadow_account_when_it_loads_again(self):
        main, other = InlineDecider(), InlineDecider()
        load, failures = other.load, [1]

        def flaky(*args, **kwargs):
            if failures:
                failures.pop()
                raise DeciderError("the observe child did not answer in time")
            return load(*args, **kwargs)

        other.load = flaky
        self.families = MemoryFamilies([], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=False,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.run_to(9, 31)
        self.assertTrue(self.live.instances["obs@1:o"].error.startswith("the decider failed"))
        self.assertNotIn("obs@1:o", self.live.shadow.accounts)
        self.run_to(9, 36)
        self.assertEqual(self.live.instances["obs@1:o"].error, "")
        self.assertIn("obs@1:o", self.live.shadow.accounts, "made when it loads again")
        self.assertTrue(self.live.shadow.accounts["obs@1:o"].positions or self.live.shadow.accounts["obs@1:o"].orders)

    def test_observe_chains_are_read_after_the_real_path_under_the_minutes_data_budget(self):
        qqq = VERTICAL.replace('"SPY"', '"QQQ"')
        order = []
        orders = self.venue.orders

        def watched_orders(*args, **kwargs):
            order.append(("orders", None))
            return orders(*args, **kwargs)

        self.venue.orders = watched_orders
        live = self.make([family("vert", VERTICAL, band="probe", params={"hold": 600})], observed=[observed("obs", code=qqq)])
        self.market.chain_reads = order
        self.run_to(9, 33)
        minute = order[-4:] if len(order) >= 4 else order
        roots = [r for r, _ in order]
        self.assertIn("QQQ", roots)
        first_qqq = roots.index("QQQ")
        self.assertLess(roots.index("SPY"), first_qqq)
        self.assertLess(roots.index("orders"), first_qqq, "the account's orders were read before any observe chain")
        self.assertEqual({pages for r, pages in order if r == "QQQ"}, {3}, "each observe root at most three pages")
        self.assertEqual({pages for r, pages in order if r == "SPY"}, {None}, "the real path's reads are whole")
        # With the minute's data budget spent, the observe band reads nothing; the real book is read whatever it holds.
        live.settings["observe_read_calls"] = 0
        del order[:]
        self.run_to(9, 35)
        self.assertNotIn("QQQ", [r for r, _ in order])
        self.assertIn("SPY", [r for r, _ in order])
        self.assertTrue(live.book.positions)
        self.assertIsNotNone(live.day.snapshot("SPY", 5))
        del minute

    def test_observe_trades_are_kept_privately_for_the_post_mortem(self):
        import sqlite3

        live = self.make([], observed=[observed("obs", params={"hold": 3, "opens": 3})])
        self.run_to(9, 50)
        path = self.root / "observe.sqlite"
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        db = sqlite3.connect(path)
        rows = db.execute("SELECT instance, family, version, trade_id, pnl, max_loss FROM trades").fetchall()
        db.close()
        self.assertTrue(rows)
        self.assertEqual({(r[0], r[1], r[2]) for r in rows}, {("obs@1:o", "obs", 1)})
        self.assertEqual(len(rows), len(live.shadow.accounts["obs@1:o"].trades), "each trade once")
        self.assertEqual(self.families.forward, {}, "never a forward row")
        live = self.restart()
        self.clock.set(self.clock() + 60)
        live.minute()
        db = sqlite3.connect(path)
        self.assertEqual(db.execute("SELECT count(*) FROM trades").fetchone()[0], len(rows), "kept across a restart")
        db.close()


class SecondRead(ObserveCase):
    """The review of #390: the observe band's reads come later in the minute and never rewrite what the real phase
    recorded, never outlast the minute's time, and never lose a remade account's trades."""

    def test_a_later_read_of_the_minute_fills_only_empty_cells(self):
        from league.live.chains import LiveChain
        from league.tests.live_fakes import iso

        chain = LiveChain("SPY", MONDAY, 570, 960)
        t = at(MONDAY, 9, 45)
        row = lambda bid, ask: {"latestQuote": {"bp": bid, "ap": ask, "bs": 10, "as": 10, "t": iso(t)}}  # noqa: E731
        first, other = "SPY260929C00600000", "SPY260929C00601000"
        chain.record(15, {first: row(1.00, 1.02)}, open_epoch=at(MONDAY, 9, 30, 0))
        chain.record(15, {first: row(1.50, 1.52), other: row(0.60, 0.62)}, open_epoch=at(MONDAY, 9, 30, 0), only_empty=True)
        i, j = chain.column(first), chain.column(other)
        self.assertEqual((chain.bid[15, i], chain.ask[15, i]), (1.00, 1.02), "the real phase's quote stands")
        self.assertEqual((chain.bid[15, j], chain.ask[15, j]), (0.60, 0.62), "an empty cell is filled")
        chain.record(16, {first: row(1.50, 1.52)}, open_epoch=at(MONDAY, 9, 30, 0))
        self.assertEqual(chain.bid[16, i], 1.50, "a new minute is written as ever")

    def test_observe_reads_have_a_short_timeout_and_stop_when_the_minutes_time_is_spent(self):
        qqq = VERTICAL.replace('"SPY"', '"QQQ"')
        live = self.make([], observed=[observed("obs", code=qqq)])
        self.run_to(9, 33)
        self.assertEqual({t for r, t in self.market.chain_timeouts if r == "QQQ"}, {5.0})
        live._decision_budget = lambda: 2.0                              # a slow minute: under the ten-second floor
        del self.market.chain_timeouts[:]
        out = self.run_to(9, 34)
        self.assertNotIn("QQQ", [r for r, _ in self.market.chain_timeouts])
        self.assertGreaterEqual(out.get("observe_reads_skipped", 0), 1)

    def test_a_remade_account_keeps_its_trades_apart(self):
        from league.live.observe import ObserveStore
        import sqlite3

        store = ObserveStore(self.root)
        trade = {"id": 1, "day": "2026-09-28", "pnl": 3.0, "max_loss": 50.0}
        self.assertTrue(store.add("obs@1:o", "obs", 1, [trade], account="first"))
        self.assertTrue(store.add("obs@1:o", "obs", 1, [trade], account="first"), "the same trade again: once")
        self.assertTrue(store.add("obs@1:o", "obs", 1, [dict(trade, pnl=-2.0)], account="remade"))
        store.close()
        db = sqlite3.connect(self.root / "observe.sqlite")
        self.assertEqual(db.execute("SELECT account, pnl FROM trades ORDER BY seq").fetchall(), [("first", 3.0), ("remade", -2.0)])
        db.close()
        from league.live.shadow import ShadowAccount, needs_of

        needs = needs_of({"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958})
        a, b = (ShadowAccount(instance="obs@1:o", family="obs", needs=needs, params={}, capital=10000.0) for _ in range(2))
        self.assertNotEqual(a.nonce, b.nonce)
        self.assertEqual(ShadowAccount.from_state(a.to_state()).nonce, a.nonce, "kept across a restart")

    def test_a_spent_budget_is_counted_never_alerted(self):
        from league.live.decider import BudgetSpent

        main, other = InlineDecider(), InlineDecider()

        def spent(*args, **kwargs):
            raise BudgetSpent("the decider's minute budget is exhausted")

        other.decide = spent
        self.families = MemoryFamilies([], [observed("obs")])
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=main, observe_decider=other,
                                config={"require_paper_proof": False}, real_money=False,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        self.run_to(9, 40)
        self.assertFalse([t for _, t in self.alerts if "budget" in t])
        self.assertGreater(self.live.health()["budget_spent"]["observe_decider"], 3)


class Switches(ObserveCase):
    def test_a_malformed_swarm_json_switches_observe_and_calibration_off_and_says_so_once(self):
        (self.root / "swarm.json").write_text("{\"live\": {\"calibration\": true,")      # cut short
        live = self.make([], observed=[observed("obs")])
        self.run_to(9, 33)
        self.assertEqual((live.switches()["observe"], live.switches()["calibration"]), (False, False))
        self.assertFalse([k for k in live.instances if k.endswith(":o")])
        told = [text for _, text in self.alerts if "swarm.json could not be read" in text]
        self.assertEqual(len(told), 1, "once, not every minute")
        for bad in ("[]", '{"live": "on"}', '"calibration"'):
            (self.root / "swarm.json").write_text(bad)
            live._switches = None
            self.assertEqual((live.switches()["observe"], live.switches()["calibration"]), (False, False), bad)

    def test_without_a_swarm_json_observe_is_on_and_calibration_off(self):
        (self.root / "swarm.json").unlink()
        live = self.make([])
        self.assertEqual((live.switches()["observe"], live.switches()["observe_max"], live.switches()["calibration"]),
                         (True, 48, False))
        (self.root / "swarm.json").write_text('{"live": {"calibration": true}}')
        live._switches = None
        self.assertEqual((live.switches()["observe"], live.switches()["calibration"]), (True, True))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSwarmsStore(unittest.TestCase):
    """`bands.observe` and `SwarmFamilies` against the swarm's real store."""

    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock

        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.store = SwarmStore(self.root, clock=SwarmClock())

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def add(self, fid, *, validated=True, t=1.0, versions=1):
        self.store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        for n in range(versions):
            self.store.add_version(fid, f"# {fid} v{n + 1}\n" + VERTICAL, {"hold": 600}, author="test")
        if validated:
            self.store.set_state(fid, validation_version=versions, validation_line={"passed": False},
                                 validation_numbers={"t": t})

    def test_only_alive_gym_families_with_a_validated_version_and_never_as_candidates(self):
        from league.swarm import bands

        self.add("gym-a", t=0.5)
        self.add("gym-b", t=2.5, versions=2)
        self.add("never", validated=False)
        self.add("cand")
        self.store.set_state("cand", banded_version=1)
        self.store.set_band("cand", "candidate", reason="passed")
        self.add("dead")
        self.store.retire_gym("dead", "finished", floor=0, source="test")
        rows = bands.observe(self.root)
        self.assertEqual([r["family"] for r in rows], ["gym-b", "gym-a"], "the likeliest first; alive, Gym, validated")
        b = rows[0]
        self.assertEqual((b["version"], b["band"], b["observe"], b["holdout_passed"], b["validation_passed"]),
                         (2, "gym", True, False, False))
        self.assertIn("gym-b v2", b["code"])
        [pinned] = bands.observe(self.root, family="gym-b", version=1)
        self.assertIn("gym-b v1", pinned["code"])
        self.assertEqual(bands.observe(self.root, family="cand", version=1), [], "a Candidate is never an observe row")
        self.assertEqual([r["family"] for r in bands.read(self.root)], ["cand"], "and observe rows never reach read()")
        families = SwarmFamilies(self.root)
        ident = {"family": "gym-b", "version": 1, "code": pinned["code"], "params": pinned["params"], "band": "gym",
                 "tuition": False, "observe": True}
        with families.admit_open(ident, real=False) as allowed:
            self.assertTrue(allowed, "the pinned version, while the family is alive in the Gym band")
        with families.admit_open(ident, real=True) as allowed:
            self.assertFalse(allowed)
        self.store.retire_gym("gym-b", "finished", floor=0, source="test")
        with families.admit_open(ident, real=False) as allowed:
            self.assertFalse(allowed, "retired: no more opens")
        if families._store is not None:
            families._store.close()

    def test_a_version_whose_own_review_failed_or_the_gate_refused_is_not_observed(self):
        from league.swarm import bands
        from league.swarm.gate import run_sha

        for fid in ("reviewed-fail", "refused", "fine", "older-fail"):
            self.add(fid)
        sha = {fid: run_sha(self.store.version(fid, 1)) for fid in ("reviewed-fail", "refused", "fine", "older-fail")}
        self.store.set_state("reviewed-fail", review={"sha": sha["reviewed-fail"], "verdict": "fail"})
        self.store.set_state("refused", gate_outcome={"sha": sha["refused"], "result": "refused"})
        self.store.set_state("older-fail", review={"sha": "another-version", "verdict": "fail"})
        self.assertEqual(sorted(r["family"] for r in bands.observe(self.root)), ["fine", "older-fail"])


@unittest.skipUnless(HAVE, "numpy not installed")
class Capacity(ObserveCase):
    """The House box is size s: one minute's budget is 40 s (`decider.MAX_BATCH_SECONDS`), shared by the minute's loads
    and decisions. 48 observe instances (the default `live.observe_max`), each deciding every minute, on the swarm's real
    store: every minute well inside it, the Gym bundle built once, and the 49th family held back by the cap."""

    def test_forty_eight_observe_instances_fit_in_a_minute(self):
        from league.swarm import bands
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock
        import league.gym.driver as driver

        store = SwarmStore(self.root, clock=SwarmClock())
        self.addCleanup(store.close)
        for i in range(49):
            fid = f"obs-{i:02d}"
            store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                              "roots": ["SPY"], "dte": [0, 2]}, origin="test")
            store.add_version(fid, f"# {fid}\n" + VERTICAL, {"hold": 5, "opens": 3}, author="test")
            store.set_state(fid, validation_version=1, validation_numbers={"t": float(i)})
        self.live = self.make([], real_money=False)
        self.families = self.live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: self.families._store.close() if self.families._store is not None else None)
        built = []
        real_build = driver.build_bundle

        def counted(*args, **kwargs):
            built.append(1)
            return real_build(*args, **kwargs)

        bands._bundle_cache = None
        seconds = []
        with patch("league.gym.driver.build_bundle", counted):
            for _ in range(12):
                began = time.monotonic()
                self.live.minute()
                seconds.append(time.monotonic() - began)
                self.clock.set(self.clock() + 60)
        bands._bundle_cache = None
        observing = [k for k, i in self.live.instances.items() if i.observe and i.mode == "live"]
        self.assertEqual(len(observing), 48)
        self.assertNotIn("obs-00@1:o", observing, "the 49th (the least likely) is held back by the cap")
        decided = sum(1 for acc in self.live.shadow.accounts.values() if acc.trades or acc.positions)
        self.assertEqual(decided, 48, "every one of them traded the shadow book")
        self.assertLessEqual(len(built), 1, "the Gym bundle is built once, not per instance per minute")
        # The first minute loads 48 programs; every minute after decides 48. Far inside the 40 s budget (CI's machines
        # are slower than a laptop, so the bound is generous: the measured figures are printed in the failure).
        self.assertLess(seconds[0], 25.0, seconds)
        self.assertLess(max(seconds[1:]), 15.0, seconds)

    def test_the_practice_league_at_its_caps_thirty_two_validated_and_sixteen_train_over_twenty_four_roots(self):
        """The practice league (Sept 29, 2026) at the default caps: 48 instances and 24 distinct roots, every root read
        every minute. The 25th root's family is held back by the roots cap and a later family on a root already read
        still joins; the 49th family is held back by the instance cap. Every minute well inside its budget."""
        from league.swarm import bands
        from league.swarm.store import SwarmStore
        from league.live.venue import Rate
        from league.tests.live_fakes import Market, iso
        from league.tests.swarm_fakes import Clock as SwarmClock
        import league.gym.driver as driver

        class Wide(Market):
            """Every root trades at its chain's level (the fake's other stocks read 400); its minute's data calls are
            counted on the test's clock (twelve minutes run in seconds here)."""

            def __init__(self, clock):
                super().__init__(clock)
                self.minute_calls = Rate(100000, clock=clock)

            def stocks(self, symbols):
                t = self.clock()
                return {s: {"latestTrade": {"p": self.level(s), "t": iso(t - 2)},
                            "latestQuote": {"bp": self.level(s) - 0.01, "ap": self.level(s) + 0.01, "t": iso(t - 1)}}
                        for s in symbols}

        self.market = Wide(self.clock)
        roots = [f"Z{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(25)]
        store = SwarmStore(self.root, clock=SwarmClock())
        self.addCleanup(store.close)

        def add(fid, root, **state):
            store.add_family({"id": fid, "mechanism": "An invented mechanism.", "structure": "debit_vertical", "roots": [root],
                              "dte": [0, 2]}, origin="test")
            store.add_version(fid, f"# {fid}\n" + VERTICAL.replace('"SPY"', f'"{root}"'), {"hold": 5, "opens": 3}, author="test")
            store.set_state(fid, **state)

        for i in range(32):                                                 # validated, on the first 16 roots
            add(f"v{i:02d}", roots[i // 2], validation_version=1, validation_numbers={"t": 100.0 - i})
        for j in range(15):                                                 # Train, on the next 8: 24 roots in all
            add(f"t{j:02d}", roots[16 + j // 2], best_train_version=1)
            store.update_family(f"t{j:02d}", best_train=50.0 - j)
        for fid, root, best in (("x-new-root", roots[24], 35.0), ("y-read-root", roots[0], 34.0), ("z-over-cap", roots[1], 33.0)):
            add(fid, root, best_train_version=1)
            store.update_family(fid, best_train=best)
        self.live = self.make([], real_money=False)
        self.families = self.live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: self.families._store.close() if self.families._store is not None else None)
        built = []
        real_build = driver.build_bundle

        def counted(*args, **kwargs):
            built.append(1)
            return real_build(*args, **kwargs)

        bands._bundle_cache = None
        seconds, calls = [], []
        with patch("league.gym.driver.build_bundle", counted):
            for _ in range(12):
                began = time.monotonic()
                out = self.live.minute()
                seconds.append(time.monotonic() - began)
                calls.append(out.get("data_calls"))
                self.clock.set(self.clock() + 60)
        bands._bundle_cache = None
        observing = sorted(i.family for i in self.live.instances.values() if i.observe and i.mode == "live")
        self.assertEqual(len(observing), 48)
        self.assertNotIn("x-new-root", observing, "the 25th root is held back by the roots cap")
        self.assertIn("y-read-root", observing, "a later family on a root already read still joins")
        self.assertNotIn("z-over-cap", observing, "the 49th family is held back by the instance cap")
        held = {p["why"]: p["capped"] for p, _ in self.ledger.of("live.observe")}
        self.assertEqual(held, {"cap": ["z-over-cap"], "roots": ["x-new-root"]})
        self.assertEqual(self.live.health()["observe"]["roots_used"], 24)
        self.assertEqual(self.live.state.get("observe_pins")["tiers"]["t00"], "train")
        self.assertEqual({r for r, _ in self.market.chain_reads} - {"SPY"}, set(roots[:24]),
                         "every root read, the 25th never (SPY: the paper proof's own read)")
        traded = sum(1 for acc in self.live.shadow.accounts.values() if acc.trades or acc.positions)
        self.assertEqual(traded, 48, "every one of them traded the shadow book")
        self.assertLessEqual(len(built), 1, "the Gym bundle is built once, not per instance per minute")
        self.assertLessEqual(max(c or 0 for c in calls[1:]), 40, calls)
        self.assertFalse(self.live.state.get("observe_shed"), "no pressure at the caps: nothing shed")
        self.assertLess(seconds[0], 30.0, seconds)
        self.assertLess(max(seconds[1:]), 20.0, seconds)


if __name__ == "__main__":
    unittest.main()
