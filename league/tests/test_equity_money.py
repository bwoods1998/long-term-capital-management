"""THE EQUITY LANE's money table (release E1; league/equity/INTERFACES.md section 7): the constitution's `equity_money`
inside its bounds (`equity_money_problems`), parsed by `league/live/money.py` (`EquityTable`, `Table.equity`), the
House-wide cash rule (`available_cash`, A8.1), the standing grant's re-ratification on the money digest E1 moves, and
the pre-open job's equity check (league/ops/preopen.py, check 10). Invented figures only; standard library only."""

import copy
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from league.constitution import (CONSTITUTION, EQUITY_MONEY_BOUNDS, EQUITY_ORDER_OFFSETS, equity_money_problems,
                                 money_digest)
from league.live import money as M
from league.tests.test_standing_grant import HOUR, StandingCase, owner_deploy, updater_deploy


def changed(**rows):
    """A copy of the constitution with `equity_money` rows set by path (`probe__sleeve_share="0.20"`); `None` deletes."""
    c = copy.deepcopy(CONSTITUTION)
    for path, value in rows.items():
        node = c["equity_money"]
        *parents, last = path.split("__")
        for key in parents:
            node = node[key]
        if value is None:
            del node[last]
        else:
            node[last] = value
    return c


def problems(**rows):
    return equity_money_problems(changed(**rows))


def e1_universe():
    """The constitution's universe as release E1 shipped it, by class and in its order: `league.equity.config.UNIVERSE`,
    an evidence module's constant that release E4 never changes. E4's universe (scripts/gen_universe.py) grows the
    stock list around it, which moves the money digest and nothing else: a figure pinned for E1 is read with this put
    back, and so holds before and after the universe deploy."""
    from league.equity import config

    return {klass: [s for s, k in config.UNIVERSE.items() if k == klass] for klass in config.CLASSES}


class TheTable(unittest.TestCase):
    def test_the_block_as_e1_deploys_it_is_inside_its_bounds_and_its_switch_is_off_since_the_old_lanes_stop(self):
        self.assertEqual(equity_money_problems(), [])
        t = M.Table.from_constitution()
        e = t.equity
        self.assertIsInstance(e, M.EquityTable)
        self.assertEqual(e, M.EquityTable.from_constitution())
        self.assertIs(e.enabled, False, "the old lanes are exits only (PREREG-EVL-1 section 8): A10.2's switch, off")
        self.assertEqual((e.invested_share, e.cash_reserve, e.min_order_usd), (D("1.00"), D("50"), D("10")))
        from league.tests.equity_design import CANDIDATES, in_force

        seats, sleeve = in_force()
        self.assertIn((seats, sleeve), CANDIDATES, "the two numbers of release E5-S are one of the grid's pairs")
        self.assertEqual((e.probe_sleeve_share, e.probe_max_programs), (D(sleeve), seats))
        # A stock at 0.10 since release R2 (the goal of Oct 19, 2026: "<= 10% of equity per name"), under the code's 0.20.
        self.assertEqual(dict(e.position_share), {"etf": D("0.50"), "stock": D("0.10")})
        self.assertEqual(dict(e.open_risk_weight), {"etf": D("0.20"), "stock": D("0.40")})
        self.assertEqual((e.sized_min_trades, e.sized_confidence, e.sized_kelly_fraction, e.sized_sleeve_share,
                          e.sized_beat_bh, e.sized_min_probe_sessions), (1000, 0.80, 0.25, D("0.50"), True, 5),
                         "the sizing-up step is parked (min_trades 1000); the rule's other rows are as pre-registered")
        self.assertEqual((e.demotion_rule, e.demotion_min_trades, e.demotion_z, e.program_loss_usd, e.twin_gap_bp,
                          e.twin_min_closes), ("edm1", 10, 1.645, D("-300"), D("15"), 5))
        self.assertEqual((e.min_hold_sessions, e.default_max_hold_sessions, e.max_hold_sessions, e.failed_decides_exit),
                         (1, 20, 60, 2))
        self.assertEqual((dict(e.entry_collar_bp), dict(e.max_collar_bp), e.max_orders_day),
                         ({"etf": 10, "stock": 25}, {"etf": 50, "stock": 100}, 60))
        # The close window (A2): sends at 15:55:00, re-priced to 15:59:30.
        self.assertEqual((e.offsets["close_send_before_close_s"], e.offsets["close_until_before_close_s"]), (300, 30))
        self.assertEqual(sorted(e.offsets), sorted(EQUITY_ORDER_OFFSETS))
        # Read-only, and a Table that carries one hashes as before.
        with self.assertRaises(TypeError):
            e.universe["TQQQ"] = "etf"
        self.assertTrue(hash(t))

    def test_the_universe_and_shares_are_the_lanes_constants(self):
        """`league.equity.config.UNIVERSE` (release E1's 35: hashed into the equity identity and into every ETF run, so
        never changed) is INSIDE the constitution's universe, classes equal: every symbol the lane's own programs name
        is one the money rule admits. Since release E4 the constitution's STOCK list may be the longer one: the
        panel's tradable union, generated (scripts/gen_universe.py: 450 to 650 names, E1's 18 among them), which
        `league.ci` holds to the gateway's STOCK_UNIVERSE. Its ETFs are E1's exactly, in E1's order. No position share
        is above `config.POSITION_SHARE`."""
        from league.equity import config

        e = M.EquityTable.from_constitution()
        self.assertEqual({symbol: e.universe.get(symbol) for symbol in config.UNIVERSE}, config.UNIVERSE)
        self.assertEqual(CONSTITUTION["equity_money"]["universe"]["etf"], e1_universe()["etf"])
        beyond = [symbol for symbol in e.universe if symbol not in config.UNIVERSE]
        self.assertEqual({e.universe[symbol] for symbol in beyond} - {"stock"}, set(), "what E4 adds is stocks")
        stocks = CONSTITUTION["equity_money"]["universe"]["stock"]
        if beyond:
            self.assertTrue(450 <= len(stocks) <= 650, f"{len(stocks)} stocks: a generated union has 450 to 650")
            self.assertEqual(stocks, sorted(stocks), "generated: sorted")
        else:
            self.assertEqual(stocks, e1_universe()["stock"], "release E1's list, in its order")
        for klass in config.CLASSES:
            self.assertLessEqual(e.position_share[klass], config.POSITION_SHARE[klass])
        self.assertEqual((e.min_hold_sessions, e.default_max_hold_sessions, e.max_hold_sessions, e.failed_decides_exit),
                         (config.MIN_HOLD_SESSIONS, config.DEFAULT_MAX_HOLD, config.MAX_HOLD_CAP,
                          config.FAILED_DECIDES_EXIT))

    def test_the_offsets_are_the_schedules(self):
        from league.equity.schedule import DEFAULTS

        self.assertEqual(dict(M.EquityTable.from_constitution().offsets), DEFAULTS)

    def test_a_bad_block_is_refused_and_the_whole_table_with_it(self):
        bad = changed(invested_share="1.50")
        for read in (M.EquityTable.from_constitution, M.Table.from_constitution):
            with self.assertRaises(ValueError) as caught:
                read(bad)
            self.assertIn("equity_money.invested_share", str(caught.exception))

    def test_a_constitution_before_e1_has_no_equity_table(self):
        before = copy.deepcopy(CONSTITUTION)
        del before["equity_money"]
        self.assertIsNone(M.Table.from_constitution(before).equity)
        self.assertEqual(equity_money_problems(before), ["equity_money: the table is missing"])
        with self.assertRaises(ValueError):
            M.EquityTable.from_constitution(before)

    def test_exposure_carries_the_equity_figures(self):
        x = M.Exposure()
        self.assertEqual((x.equity_open_risk, x.equity_invested), (M.ZERO, M.ZERO))
        x = M.Exposure(equity_open_risk=D("134"), equity_invested=D("670"))
        self.assertEqual((x.equity_open_risk, x.equity_invested), (D("134"), D("670")))


class TheBounds(unittest.TestCase):
    """Each row inside, at its owner's line and past it (test_constitution has every row's line and one step past it);
    here the shape rules: missing, not a number, not a whole count, the exclusive lows, the exact rows and the order."""

    def test_every_row_is_required(self):
        for path in EQUITY_MONEY_BOUNDS:
            self.assertIn(f"equity_money.{path} is missing", problems(**{path.replace(".", "__"): None}), path)
        for path in ("enabled", "sized__beat_bh", "demotion__rule"):
            self.assertTrue(any(path.replace("__", ".") in p for p in problems(**{path: None})), path)

    def test_numbers_counts_and_the_exclusive_lows(self):
        self.assertIn("equity_money.cash_reserve_usd = 'fifty' is not a number", problems(cash_reserve_usd="fifty"))
        self.assertIn("equity_money.probe.max_programs = 2.0 is not a whole count", problems(probe__max_programs=2.0))
        self.assertIn("equity_money.order_path.max_orders_day = '30.5' is not a whole count",
                      problems(order_path__max_orders_day="30.5"))
        self.assertTrue(problems(cash_reserve_usd=True), "a bool is no amount")
        self.assertTrue(problems(cash_reserve_usd="NaN"))
        for path in ("position_share__etf", "position_share__stock", "invested_share"):
            self.assertIn(f"equity_money.{path.replace('__', '.')} = '0' is outside (0, ", " ".join(problems(**{path: "0"})))
        # Tightenings are accepted, a zero among them where zero stops the route. (A Probe sleeve of zero takes the
        # panel's with it: a panel program's sleeve is never above a Probe's, `TheRowsThatKeepAnOrder`.)
        for rows in ({"probe__sleeve_share": "0", "panel__sleeve_share": "0"}, {"probe__max_programs": 0},
                     {"panel__seats": 0}, {"panel__sleeve_share": "0"}, {"order_path__max_orders_day": 0},
                     {"position_share__etf": "0.10"}, {"invested_share": "0.50"}, {"cash_reserve_usd": "200"},
                     {"open_risk_weight__etf": "1.00"}, {"demotion__program_loss_usd": "-25"}, {"demotion__z": "0"},
                     {"sized__min_trades": 1000}, {"sized__kelly_fraction": "0.125"}, {"holds__failed_decides_exit": 1}):
            self.assertEqual(problems(**rows), [], rows)

    def test_the_exact_rows(self):
        for path, value in (("enabled", 0), ("enabled", "false"), ("enabled", None), ("sized__beat_bh", False),
                            ("sized__beat_bh", 1), ("demotion__rule", "dm1"), ("demotion__rule", "EDM1"),
                            ("demotion__rule", " edm1")):
            self.assertTrue(any(f"equity_money.{path.replace('__', '.')} = " in p and "is not exactly one of" in p
                                for p in problems(**{path: value})), (path, value))
        self.assertEqual(problems(enabled=True), [], "the switch-on is a constitution-only change")

    def test_the_universe_shape(self):
        self.assertIn("equity_money.universe lists symbols under exactly ['etf', 'stock']",
                      problems(universe={"etf": ["SPY"]}))
        self.assertIn("equity_money.universe lists SPY more than once",
                      problems(universe={"etf": ["SPY", "QQQ"], "stock": ["SPY"]}))
        self.assertTrue(any("equity_money.universe.etf is a list of tickers" in p for p in
                            problems(universe={"etf": ["spy"], "stock": []})))
        self.assertTrue(any("equity_money.universe.stock is a list of tickers" in p for p in
                            problems(universe={"etf": [], "stock": "AAPL"})))
        self.assertEqual(problems(universe={"etf": ["SPY", "BRK.B"], "stock": []}), [])

    def test_the_panel_row_is_inside_its_bounds_and_under_the_probe_sleeve(self):
        """THE PANEL ROW (release E4 step two): at most two seats of its own, a whole count; a sleeve of at most 0.25 x
        E and never above the Probe's."""
        self.assertEqual(problems(), [])
        self.assertIn("equity_money.panel.seats = 3 is outside [0, 2]", problems(panel__seats=3))
        self.assertIn("equity_money.panel.seats = 1.0 is not a whole count", problems(panel__seats=1.0))
        self.assertIn("equity_money.panel.sleeve_share = '0.26' is outside [0, 0.25]", problems(panel__sleeve_share="0.26"))
        self.assertIn("equity_money.panel.sleeve_share = '-0.01' is outside [0, 0.25]",
                      problems(panel__sleeve_share="-0.01"))
        self.assertIn("equity_money.panel.sleeve_share (0.10) is above probe.sleeve_share (0.05): a panel program's "
                      "sleeve is never larger than a Probe's", problems(probe__sleeve_share="0.05"))
        self.assertEqual(problems(probe__sleeve_share="0.10"), [], "equal is allowed")
        self.assertEqual(problems(panel__seats=2, panel__sleeve_share="0.25"), [], "the loose ends")
        self.assertIn("equity_money.panel.seats is missing", problems(panel__seats=None))

    def test_the_rows_that_keep_an_order(self):
        self.assertIn("equity_money.holds.default_max_hold_sessions (30) is above holds.max_hold_sessions (20): the "
                      "default hold is inside the lane's cap",
                      problems(holds__default_max_hold_sessions=30, holds__max_hold_sessions=20))
        self.assertTrue(any("a collar only widens" in p for p in problems(order_path__entry_collar_bp__etf=40,
                                                                          order_path__max_collar_bp__etf=30)))
        self.assertTrue(any("entries are sent before their cut-off" in p
                            for p in problems(order_path__open_send_after_open_s=600, order_path__entry_until_after_open_s=300)))
        self.assertTrue(any("the close window is sent before its cut-off" in p
                            for p in problems(order_path__close_until_before_close_s=300)))
        self.assertTrue(any("programs decide on the day's bars" in p
                            for p in problems(order_path__bars_after_close_s=1800)))
        self.assertTrue(any("the bars' audit comes before the pre-open" in p
                            for p in problems(order_path__audit_before_open_s=300)))
        # At the loose ends the open window's entries still close before the close window opens on a 13:00 half day.
        from league.constitution import EQUITY_MONEY_BOUNDS as B

        self.assertLess(int(B["order_path.entry_until_after_open_s"][1]) + int(B["order_path.close_send_before_close_s"][1]),
                        12600)
        self.assertEqual(problems(order_path__entry_until_after_open_s=3600, order_path__close_send_before_close_s=1800),
                         [])


class TheCashRule(unittest.TestCase):
    """THE HOUSE-WIDE CASH RULE (A8.1): cash - |short market value| - every working buy's worst cost (both books) -
    working reservations - the reserve; never clamped; nothing unreadable is read as room."""

    def test_the_formula(self):
        account = {"cash": "1000.00", "short_market_value": "-120.50", "buying_power": "4000", "multiplier": "2"}
        self.assertEqual(M.available_cash(account, working_buys_worst=D("300"), reserved=D("80"), reserve_usd=D("50")),
                         D("449.50"))
        self.assertEqual(M.available_cash({"cash": "100"}, working_buys_worst=D("0"), reserved=D("0"), reserve_usd=D("50")),
                         D("50"), "no short market value on the row reads as none")

    def test_margin_never_adds_room(self):
        """Buying power and the multiplier are never read: a margin account's 2x is not cash."""
        base = {"cash": "500", "short_market_value": "0"}
        rich = {**base, "buying_power": "100000", "regt_buying_power": "100000", "multiplier": "4",
                "non_marginable_buying_power": "100000"}
        for account in (base, rich):
            self.assertEqual(M.available_cash(account, working_buys_worst=D("0"), reserved=D("0"), reserve_usd=D("50")),
                             D("450"))

    def test_it_is_never_clamped(self):
        self.assertEqual(M.available_cash({"cash": "-25"}, working_buys_worst=D("0"), reserved=D("0"), reserve_usd=D("50")),
                         D("-75"))
        self.assertEqual(M.available_cash({"cash": "100"}, working_buys_worst=D("90"), reserved=D("0"), reserve_usd=D("50")),
                         D("-40"))

    def test_what_cannot_be_read_refuses(self):
        for account in ({}, {"cash": None}, {"cash": "n/a"}, {"cash": "NaN"}, {"cash": True}, None,
                        {"cash": "100", "short_market_value": "?"}):
            with self.assertRaises(ValueError, msg=account):
                M.available_cash(account, working_buys_worst=D("0"), reserved=D("0"), reserve_usd=D("50"))
        for kw in ({"working_buys_worst": D("-1")}, {"reserved": D("-0.01")}, {"reserve_usd": D("-50")},
                   {"working_buys_worst": 10.0}, {"reserved": D("NaN")}, {"reserve_usd": "50"}):
            args = {"working_buys_worst": D("0"), "reserved": D("0"), "reserve_usd": D("50"), **kw}
            with self.assertRaises(ValueError, msg=kw):
                M.available_cash({"cash": "100"}, **args)


class TheGrantReRatifies(StandingCase):
    """Release E1's `equity_money` moves the money digest (THE PROBE TOTAL AT $800's fdf2ac7c -> 7e41909a, the block with
    `enabled` True: the switch ships on, A10.2; and with the Probe sleeve at 0.50 x E and the sizing-up step parked,
    A20 and its study's review: one move with the block): a
    grant pinned on fdf2ac7c holds nothing after the deploy until the standing grant re-ratifies it at the House's
    start, on the owner's release change only. The stop (`enabled` False, a constitution-only change) is a digest of
    its own, ratified the same way, and so is A20's rollback (the sleeve back at 0.25: 3a7c52d5); the rollback to a
    release before E1 brings fdf2ac7c back on the owner's deploy of it.

    THESE ARE E1's DIGESTS, at A20's design (three seats at 0.50): every test here runs with the two rows at that
    design (`setUp`: `reference`), whatever pair release E5-S's `set_design` has put in force. A MOVE OF THE PAIR is a
    digest of its own, ratified the same way and by the owner's deploy alone (`test_a_design_move_...`), and the move
    back to A20's design lands on E1's digest exactly. SINCE RELEASE E5-A the table also carries the seat rule's
    block (`equity_money.probe.seat`), a money rule of its own digest: E1's digests are read with that block left out
    (`equity_design.e1`), and the block's own move, and its rollback row, are held in league/tests/test_equity_seats.py."""

    BEFORE = "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7"
    E1 = "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a"
    OFF = "23f17a1467610f8d252b55c6d6748f8fb1311a0142e3f92c43d4bff710886579"
    QUARTER = "3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2"

    def setUp(self):
        from league.tests.equity_design import e1

        super().setUp()
        at_a20 = e1()
        at_a20.__enter__()
        self.addCleanup(at_a20.__exit__, None, None, None)
        # These digests are release E1's: read with E1's universe (release E4's is a digest of its own, below).
        pin = patch.dict(CONSTITUTION["equity_money"], universe=e1_universe())
        pin.start()
        self.addCleanup(pin.stop)

    def pre_e1(self):
        patcher = patch.dict(CONSTITUTION)
        patcher.start()
        CONSTITUTION.pop("equity_money", None)
        return patcher

    def pinned_before(self):
        patcher = self.pre_e1()
        try:
            self.assertEqual(money_digest(), self.BEFORE)
            grant = self.enabled()
        finally:
            patcher.stop()
        self.assertEqual(money_digest(), self.E1)
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.BEFORE)
        return grant

    def test_the_owners_deploy_re_ratifies_it_at_the_houses_start(self):
        grant = self.pinned_before()
        self.assertFalse(grant.allows_live(2), "real entries are held until it is ratified")
        out = self.standing(grant, release="r-e1", rows=owner_deploy(self.clock() - 60, release="r-e1"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertIn(f"money digest {self.BEFORE[:12]} -> {self.E1[:12]}", grant.ratifications()[-1]["why"])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.E1)
        self.assertTrue(grant.allows_live(2))

    def test_the_updater_alone_never_ratifies_it(self):
        grant = self.pinned_before()
        out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))
        self.assertEqual(grant.ratifications(), [])

    def test_the_switch_off_is_a_digest_of_its_own_ratified_the_same_way(self):
        grant = self.pinned_before()
        self.standing(grant, release="r-e1", rows=owner_deploy(self.clock() - 60, release="r-e1"))
        self.clock.advance(HOUR)
        with patch.dict(CONSTITUTION["equity_money"], enabled=False):
            self.assertEqual(money_digest(), self.OFF)
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-off", rows=owner_deploy(self.clock() - 60, release="r-off"))
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.OFF)
            self.assertTrue(grant.allows_live(2))

    def test_the_sleeve_back_at_a_quarter_is_a_digest_of_its_own_ratified_the_same_way(self):
        """A20's rollback (`probe.sleeve_share` "0.25", a constitution-only change): the grant ratified on E1's digest
        holds nothing under it until the owner's deploy of that release re-ratifies it; the updater alone never does."""
        grant = self.pinned_before()
        self.standing(grant, release="r-e1", rows=owner_deploy(self.clock() - 60, release="r-e1"))
        self.clock.advance(HOUR)
        with patch.dict(CONSTITUTION["equity_money"]["probe"], sleeve_share="0.25"):
            self.assertEqual(money_digest(), self.QUARTER)
            self.assertFalse(grant.allows_live(2), "a moved sleeve is a moved money rule: nothing real until ratified")
            out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
            self.assertEqual(out["action"], "refused")
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-quarter", rows=owner_deploy(self.clock() - 60, release="r-quarter"))
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.QUARTER)
            self.assertTrue(grant.allows_live(2))

    def test_a_design_move_is_a_digest_of_its_own_ratified_the_same_way_and_so_is_the_move_back(self):
        """Release E5-S: the seats and the sleeve move together (`set_design SEATS SLEEVE`), each pair of the grid a
        money digest of its own (league/tests/equity_design.py `DIGESTS`). A grant ratified on E1's digest holds
        nothing under any other pair until the owner's deploy of that release re-ratifies it; the updater alone
        never does; and `set_design 3 0.50` is E1's digest again, on which the grant is ratified as before. (Read on
        the table before the seat rule's block, as every test of this class: the pins are release E5-S's,
        `DIGESTS_E5S`. With the block, each pair is on its own pin of `DIGESTS`: league/tests/test_constitution.py.)"""
        from league.tests.equity_design import CANDIDATES, REFERENCE, design
        from league.tests.equity_design import DIGESTS_E5S as DIGESTS

        grant = self.pinned_before()
        self.standing(grant, release="r-e1", rows=owner_deploy(self.clock() - 60, release="r-e1"))
        self.assertEqual(DIGESTS[REFERENCE][0], self.E1)
        for n, pair in enumerate(c for c in CANDIDATES if c != REFERENCE):
            self.clock.advance(HOUR)
            with design(*pair):
                self.assertEqual(money_digest(), DIGESTS[pair][0], pair)
                self.assertFalse(grant.allows_live(2), f"{pair}: a moved pair is a moved money rule")
                out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
                self.assertEqual(out["action"], "refused", pair)
                self.assertFalse(grant.allows_live(2))
                release = f"r-design-{n}"
                out = self.standing(grant, release=release, rows=owner_deploy(self.clock() - 60, release=release))
                self.assertEqual(out["action"], "ratified", pair)
                self.assertEqual(grant.current()["policy"]["constitution_digest"], DIGESTS[pair][0])
                self.assertTrue(grant.allows_live(2))
            # The move back (the rollback): E1's digest again, held until the owner's deploy of it ratifies it.
            self.clock.advance(HOUR)
            self.assertEqual(money_digest(), self.E1)
            self.assertFalse(grant.allows_live(2))
            back = f"r-back-{n}"
            out = self.standing(grant, release=back, rows=owner_deploy(self.clock() - 60, release=back))
            self.assertEqual(out["action"], "ratified", pair)
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.E1)
            self.assertTrue(grant.allows_live(2))

    def test_the_rollback_before_e1_is_ratified_on_the_owners_deploy_of_it(self):
        grant = self.pinned_before()
        self.standing(grant, release="r-e1", rows=owner_deploy(self.clock() - 60, release="r-e1"))
        self.clock.advance(HOUR)
        patcher = self.pre_e1()
        self.addCleanup(patcher.stop)
        self.assertFalse(grant.allows_live(2))
        back = [{"ts": self.clock() - 60, "deploy": "rollback@2", "release": "r-e1", "stage": "rollback", "ok": True,
                 "from": "r-e1", "to": "r-t800"}]
        out = self.standing(grant, release="r-t800", rows=back)
        self.assertEqual(out["action"], "ratified")
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.BEFORE)
        self.assertTrue(grant.allows_live(2))


class TheUniverseReRatifies(StandingCase):
    """Release E4's universe (R-E4b: the panel's tradable union in `equity_money.universe.stock`, written by
    scripts/gen_universe.py) is a money rule and NOTHING ELSE moves with it: a grant ratified on release E1's digest
    holds nothing under the grown list until the standing grant re-ratifies it at the House's start, on the owner's
    release change only; with E1's list put back the digest is E1's again, and the rollback to it is ratified the same
    way. Invented tickers: the list the House generates is never in a test."""

    GROWN = [f"ZZ{a}{b}" for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRST"]

    def grown(self):
        universe = e1_universe()
        return {"etf": universe["etf"], "stock": sorted(universe["stock"] + self.GROWN)}

    def ratified_on_e1(self):
        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
            e1 = money_digest()
            grant = self.enabled()
            self.assertEqual(grant.current()["policy"]["constitution_digest"], e1)
            self.assertTrue(grant.allows_live(2))
        return grant, e1

    def test_the_universe_moves_the_money_digest_and_nothing_else_does(self):
        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
            e1, e1_full = money_digest(), copy.deepcopy(CONSTITUTION)
        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
            self.assertNotEqual(money_digest(), e1)
            self.assertEqual(equity_money_problems(), [], "538 stocks sit inside the table's bounds")
            table = M.EquityTable.from_constitution()
            self.assertEqual(len(table.universe), 17 + 18 + 520)
            self.assertEqual({table.universe[s] for s in self.GROWN}, {"stock"})
            back = copy.deepcopy(CONSTITUTION)
            back["equity_money"]["universe"] = e1_universe()
            self.assertEqual(back, e1_full, "the list is all that differs")
            self.assertEqual(money_digest(back), e1)
        # The tree as it stands: E1's rules but for the stock list (the same figure before and after the deploy).
        back = copy.deepcopy(CONSTITUTION)
        back["equity_money"]["universe"] = e1_universe()
        self.assertEqual(money_digest(back), e1)

    def test_the_owners_deploy_re_ratifies_it_and_the_updater_alone_never_does(self):
        grant, e1 = self.ratified_on_e1()
        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
            universe = money_digest()
            self.assertFalse(grant.allows_live(2), "a moved universe is a moved money rule: nothing real until ratified")
            out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
            self.assertEqual(out["action"], "refused")
            self.assertFalse(grant.allows_live(2))
            self.assertEqual(grant.ratifications(), [])
            out = self.standing(grant, release="r-e4b", rows=owner_deploy(self.clock() - 60, release="r-e4b"))
            self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
            self.assertIn(f"money digest {e1[:12]} -> {universe[:12]}", grant.ratifications()[-1]["why"])
            self.assertEqual(grant.current()["policy"]["constitution_digest"], universe)
            self.assertTrue(grant.allows_live(2))

    def test_the_rollback_to_e1s_list_is_ratified_on_the_owners_deploy_of_it(self):
        grant, e1 = self.ratified_on_e1()
        with patch.dict(CONSTITUTION["equity_money"], universe=self.grown()):
            self.standing(grant, release="r-e4b", rows=owner_deploy(self.clock() - 60, release="r-e4b"))
            self.assertTrue(grant.allows_live(2))
        self.clock.advance(HOUR)
        with patch.dict(CONSTITUTION["equity_money"], universe=e1_universe()):
            self.assertFalse(grant.allows_live(2))
            back = [{"ts": self.clock() - 60, "deploy": "rollback@2", "release": "r-e4b", "stage": "rollback", "ok": True,
                     "from": "r-e4b", "to": "r-e4a"}]
            out = self.standing(grant, release="r-e4a", rows=back)
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], e1)
            self.assertTrue(grant.allows_live(2))


class ThePreopenEquityCheck(unittest.TestCase):
    """Check 10 (league/ops/preopen.py): cash at or above zero, no us_equity short, the equity book reconciled, the
    deployed gateway's stock route equal to the constitution's; the multiplier and the PDT flag reported, never a bar."""

    def house(self, **over):
        em = copy.deepcopy(CONSTITUTION["equity_money"])
        h = {"errors": {},
             "money": {"equity_money": em, "equity_release_gateway": None},
             "release": {"live": {"equity": {"frozen": ""}}},
             "gateway": {"account": {"cash": "900.00", "short_market_value": "0", "multiplier": "2",
                                     "pattern_day_trader": False, "daytrade_count": 1},
                         "positions": [{"symbol": "SPY", "qty": "1.5", "asset_class": "us_equity", "side": "long"},
                                       {"symbol": "SPY261016P00600000", "qty": "-1", "asset_class": "us_option",
                                        "side": "short"}],
                         "stock_buys": {"enabled": True, "symbols": {k: list(v) for k, v in em["universe"].items()},
                                        "etf_equity_share": "0.5", "stock_equity_share": "0.2"}}}
        for path, value in over.items():
            node = h
            *parents, last = path.split("__")
            for key in parents:
                node = node[key]
            node[last] = value
        return h

    def check(self, h):
        from league.ops.preopen import check_equity

        c = check_equity(h)
        return c.ok, c.headline(), [t for ok, t in c.items if ok is None]

    def test_a_clean_account_passes_and_reports_the_margin_figures(self):
        ok, headline, info = self.check(self.house())
        self.assertTrue(ok, headline)
        self.assertEqual(headline, "account cash $900.00: at or above $0, no margin in use")
        self.assertIn("margin multiplier 2 (reported, never a bound: E1 trades cash only); pattern_day_trader False, "
                      "daytrade_count 1", info)
        h = self.house(gateway__account__pattern_day_trader=True, gateway__account__daytrade_count=4)
        self.assertTrue(self.check(h)[0], "the PDT flag is reported, never a bar")

    def test_each_fault_fails(self):
        for over, said in (({"gateway__account__cash": "-0.01"}, "BELOW $0"),
                           ({"gateway__account__cash": None}, "BELOW $0 or unreadable"),
                           ({"gateway__account": None}, "the account is unreadable"),
                           ({"gateway__positions": [{"symbol": "QQQ", "qty": "-2", "asset_class": "us_equity"}]},
                            "us_equity positions held short: QQQ"),
                           ({"gateway__positions": [{"symbol": "IWM", "qty": "2", "side": "short"}]},
                            "us_equity positions held short: IWM"),
                           ({"gateway__positions": None}, "positions unreadable"),
                           ({"release__live__equity": {"frozen": "2 mismatched readings: SPY"}},
                            "the equity book is frozen: 2 mismatched readings: SPY"),
                           ({"gateway__stock_buys": None}, "the gateway reports no stock route"),
                           ({"gateway__stock_buys__etf_equity_share": "0.4"}, "position_share.etf"),
                           ({"money__equity_release_gateway": ["gateway/wrangler.jsonc: STOCK_BUYS_REAL must be set once"]},
                            "STOCK_BUYS_REAL must be set once"),
                           ({"money__equity_money": None}, "no equity_money table"),
                           ({"errors": {"money": "ValueError: refused"}}, "unreadable")):
            ok, headline, _ = self.check(self.house(**over))
            self.assertFalse(ok, over)
            self.assertIn(said, headline, over)
        h = self.house()
        h["gateway"]["stock_buys"]["symbols"]["etf"].append("TQQQ")
        self.assertIn("gateway only: TQQQ (etf)", self.check(h)[1])

    def test_the_switch_and_the_book(self):
        # The gateway off and the House's row off passes (A8: the row is the switch); the row on needs the gateway on.
        self.assertTrue(self.check(self.house(money__equity_money__enabled=False, gateway__stock_buys__enabled=False))[0])
        on = self.house(money__equity_money__enabled=True, gateway__stock_buys__enabled=False)
        self.assertIn("equity_money.enabled is true but the gateway's STOCK_BUYS_REAL admits no buy", self.check(on)[1])
        self.assertTrue(self.check(self.house(money__equity_money__enabled=True))[0])
        # THE OLD LANES ARE EXITS ONLY (PREREG-EVL-1 section 8): the block in force is off, so it agrees with the
        # gateway on (as deployed) and off alike; its rollback (True) needs the gateway on again.
        self.assertIs(CONSTITUTION["equity_money"]["enabled"], False, "the old lanes' stop: the block in force is off")
        self.assertTrue(self.check(self.house())[0], "the block in force beside the gateway's buys on")
        self.assertTrue(self.check(self.house(gateway__stock_buys__enabled=False))[0], "and beside them off")
        # No book health: reported while the lane is off, a FAIL once it is on.
        ok, _, info = self.check(self.house(release__live__equity=None, money__equity_money__enabled=False))
        self.assertTrue(ok)
        self.assertIn("the equity book reports no freeze state (equity_money.enabled false: no equity open goes)", info)
        ok, headline, _ = self.check(self.house(release__live__equity=None, money__equity_money__enabled=True))
        self.assertEqual((ok, headline), (False, "the equity book reports no freeze state while equity_money.enabled is true"))
        self.assertFalse(self.check(self.house(release__live__equity={}, money__equity_money__enabled=True))[0])

    def test_collect_reads_what_the_check_needs(self):
        """The House's reads: the account's cash, short value, multiplier and PDT fields, positions with their side, the
        gateway's stock route from /v1/health, the book's health, and the release's own gateway files only when it
        carries them (the House's release trees do not)."""
        from league.ops import preopen as PO

        em = CONSTITUTION["equity_money"]
        health = {"kill_switch": False, "max_loss": {},
                  "stock_buys": {"enabled": True, "symbols": {k: list(v) for k, v in em["universe"].items()},
                                 "etf_equity_share": "0.5", "stock_equity_share": "0.2", "day_buys_usd": "0.00"}}

        class Gateway:
            def get(self, path, params=None):
                return {"/v1/health": health,
                        "/v1/alpaca/v2/account": {"status": "ACTIVE", "equity": "1000", "cash": "990",
                                                  "short_market_value": "0", "multiplier": "1",
                                                  "pattern_day_trader": False, "daytrade_count": 0},
                        "/v1/alpaca/v2/orders": [], "/v1/alpaca/v2/positions": [
                            {"symbol": "SPY", "qty": "1", "asset_class": "us_equity", "side": "long"}]}[path]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            h = PO.collect(root, root, root, Gateway(), now=1789000000.0, config={})
            self.assertNotIn("money", h["errors"])
            self.assertIsNone(h["money"]["equity_release_gateway"])
            self.assertEqual(h["money"]["equity_money"], em)
            self.assertEqual(h["gateway"]["stock_buys"]["enabled"], True)
            self.assertEqual(h["gateway"]["account"]["multiplier"], "1")
            self.assertEqual(h["gateway"]["positions"][0]["side"], "long")
            ok, headline, _ = self.check({**h, "release": {"live": {"equity": {"frozen": ""}}}})
            self.assertTrue(ok, headline)
            # A release that carries its gateway files is judged by league.ci's own comparison.
            (root / "gateway" / "lib").mkdir(parents=True)
            from league import ci

            for rel in ("gateway/wrangler.jsonc", "gateway/lib/caps.mjs"):
                (root / rel).write_text((ci.REPO / rel).read_text(encoding="utf-8"), encoding="utf-8")
            h = PO.collect(root, root, root, Gateway(), now=1789000000.0, config={})
            self.assertEqual(h["money"]["equity_release_gateway"], [])

    def test_a_live_panel_program_needs_the_panel_lane_ready(self):
        """Release E4: while the equity book holds a panel program (not retired, or with a lot), the lane's own
        readiness rule must hold; the leg that fails is named. With none, nothing of the panel is a bar."""
        for h in (self.house(), self.house(panel={"instances": 0}), self.house(panel=None)):
            ok, headline, info = self.check(h)
            self.assertTrue(ok, headline)
            self.assertIn("no live panel program (the panel lane's readiness is not read)", info)
        from league.ops.preopen import check_equity

        ready = self.house(panel={"instances": 2, "holding": 1, "ready": True, "why": None})
        self.assertTrue(self.check(ready)[0])
        self.assertIn((True, "2 live panel program(s), 1 holding a lot: the panel lane is ready (the store's freshness, "
                             "the universe deploy, the tradable share, the universe's age, the nightly I6, the twin marker)"), check_equity(ready).items)
        ok, headline, _ = self.check(self.house(panel={"instances": 1, "holding": 1, "ready": False,
                                                       "why": "the twin marker is two sessions behind"}))
        self.assertEqual((ok, headline), (False, "1 live panel program(s), 1 holding a lot, and the panel lane is NOT ready: the "
                                                 "twin marker is two sessions behind (its opens stop; exits go on)"))
        # A reading with no verdict is no pass, and neither is a section that could not be read.
        ok, headline, _ = self.check(self.house(panel={"instances": 1}))
        self.assertEqual((ok, headline), (False, "1 live panel program(s), 0 holding a lot, and the panel lane is NOT ready: no "
                                                 "leg named (its opens stop; exits go on)"))
        self.assertFalse(self.check(self.house(panel={"instances": 1, "ready": "yes"}))[0], "True, and nothing like it")
        ok, headline, _ = self.check(self.house(errors={"panel": "OperationalError: database is locked"}))
        self.assertEqual((ok, headline), (False, "the panel lane could not be read (a live panel program cannot be ruled "
                                                 "ready): OperationalError: database is locked"))

    def test_collect_reads_the_panel_only_while_a_panel_program_is_live(self):
        """`collect`'s panel section: no live book, a book from before the panel's live path (E1's own tables: no `kind`
        column) and a book with no panel program read NOTHING of the panel (`live_ready` is not called: with every
        E4 switch off nothing of E4 runs). A panel program that is not retired, or a retired one still holding a lot,
        is live; then the lane's rule is asked once, and a rule that cannot answer is an error, never a pass."""
        import sqlite3

        from league.equity import live as book
        from league.ops import preopen as PO
        from league.swarm import elane_xs

        source = (Path(book.__file__).resolve().parents[1] / "xs" / "book.py").read_text(encoding="utf-8")
        self.assertIn('KIND = "panel"', source)
        self.assertIn("INSTANCE_KIND_DDL = \"ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'\"", source)
        asked = []

        def rule(root, settings, *, now=None):
            asked.append((root, settings))
            clocks.append(now)
            return False, "the universe deploy is not in force"

        clocks = []

        def instance(db, iid, *, kind=None, retired=None):
            cols = "id, family, version, lane, run_sha, code, params, band, max_hold, created_at, retired_at"
            row = (iid, iid.split("@")[0], 1, "equity", "sha", "", "{}", "probe", 20, 1.0, retired)
            if kind is None:
                db.execute(f"INSERT INTO eq_instances ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
            else:
                db.execute(f"INSERT INTO eq_instances ({cols}, kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*row, kind))
            db.commit()

        def lot(db, iid, status):
            db.execute("INSERT INTO eq_lots (instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                       "entry_notional, entry_at, opened_at, opened_day, status) VALUES (?,?,1,'equity','ZZAA','stock','1',"
                       "'1','10','10','open',1.0,'2031-03-04',?)", (iid, iid.split("@")[0], status))
            db.commit()

        with tempfile.TemporaryDirectory() as tmp, patch.object(elane_xs, "live_ready", side_effect=rule):
            root = Path(tmp)

            def read():
                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
                self.assertNotIn("panel", h["errors"], h["errors"])
                return h["panel"]

            self.assertEqual(read(), {"instances": 0}, "no live book")
            db = sqlite3.connect(root / "live.sqlite")
            self.addCleanup(db.close)
            self.assertEqual(read(), {"instances": 0}, "a book with no equity table")
            db.executescript(book.SCHEMA)
            instance(db, "seed-a@1:r")
            self.assertEqual(read(), {"instances": 0}, "release E1's tables: no kind column, so no panel program")
            db.execute("ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'")
            instance(db, "seed-b@1:r", kind="equity")
            instance(db, "xs-gone@1:r", kind="panel", retired=5.0)
            lot(db, "xs-gone@1:r", "closed")
            self.assertEqual(read(), {"instances": 0}, "an equity program, and a panel program retired and flat")
            self.assertEqual(asked, [], "nothing of the panel was read")
            instance(db, "xs-a@1:r", kind="panel")
            self.assertEqual(read(), {"instances": 1, "holding": 0, "ready": False,
                                      "why": "the universe deploy is not in force"})
            self.assertEqual([r for r, _ in asked], [root])
            self.assertEqual(clocks, [1789000000.0], "the store's freshness is read by the job's own clock")
            self.assertIsInstance(asked[0][1], dict, "the swarm's settings as the swarm loads them")
            lot(db, "xs-gone@1:r", "closing")
            lot(db, "xs-a@1:r", "open")
            lot(db, "xs-a@1:r", "open")
            self.assertEqual(read(), {"instances": 2, "holding": 2, "ready": False,
                                      "why": "the universe deploy is not in force"}, "a retired program still holding a lot is live")
            ok, headline, _ = self.check({**self.house(), "panel": read()})
            self.assertEqual((ok, headline), (False, "2 live panel program(s), 2 holding a lot, and the panel lane is NOT ready: "
                                                     "the universe deploy is not in force (its opens stop; exits go on)"))
            # No symbol and no long text leaves the section.
            self.assertNotIn("ZZAA", repr(read()))
            with patch.object(elane_xs, "live_ready", return_value=(True, None)):
                self.assertEqual(read(), {"instances": 2, "holding": 2, "ready": True, "why": None})
            with patch.object(elane_xs, "live_ready", return_value=(False, "x" * 900)):
                self.assertEqual(len(read()["why"]), 200)
            with patch.object(elane_xs, "live_ready", return_value=("ready", None)):
                self.assertIs(read()["ready"], False, "True, and nothing like it")
            # The rule itself failing (a release whose panel lane is not built, a store it cannot read).
            with patch.object(elane_xs, "live_ready", side_effect=NotImplementedError("not built")):
                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
            self.assertEqual(h["errors"]["panel"], "NotImplementedError: not built")
            self.assertNotIn("panel", h)
            ok, headline, _ = self.check({**self.house(), "errors": h["errors"]})
            self.assertFalse(ok)
            self.assertIn("the panel lane could not be read", headline)

    def test_the_options_population_is_counted_by_the_stores_own_guard(self):
        """Check 5 holds the OPTIONS population to its floor; an equity family is its own lane's, and a panel family
        is one (release E4). The count reads `league.swarm.store.OPTIONS_ONLY_SQL`, the one guard the store's own
        readers use, never a list of structures of its own: a panel family is out of it the day the store says so."""
        import json
        import sqlite3

        from league.ops import preopen as PO
        from league.swarm import store as swarm_store

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "swarm.json").write_text(json.dumps({"live": {}, "population": {"floor": 2}}))
            (root / "swarm.heartbeat").write_text(json.dumps({"at": 1789000000.0, "status": {}}))
            db = sqlite3.connect(root / "swarm.sqlite")
            db.execute("CREATE TABLE families (id TEXT PRIMARY KEY, structure TEXT, retired_at TEXT)")
            db.executemany("INSERT INTO families VALUES (?, ?, ?)",
                           [("o1", "debit_vertical", None), ("o2", "long_single", None), ("o3", "long_single", "2031-03-04"),
                            ("e1", "etf", None), ("e2", "stock", None), ("p1", "panel", None), ("p2", "panel", None)])
            db.commit()

            def alive():
                h = PO.collect(root, root, root, None, now=1789000000.0, config={})
                self.assertNotIn("swarm", h["errors"], h["errors"])
                return h["swarm"]["alive"]

            [(wanted,)] = db.execute(f"SELECT count(*) FROM families WHERE retired_at IS NULL AND "
                                     f"{swarm_store.OPTIONS_ONLY_SQL}").fetchall()
            db.close()
            self.assertEqual(alive(), wanted)
            with patch.object(swarm_store, "OPTIONS_ONLY_SQL", "structure NOT IN ('etf', 'stock', 'panel')"):
                self.assertEqual(alive(), 2, "the two options families; neither panel family")
            with patch.object(swarm_store, "OPTIONS_ONLY_SQL", "structure NOT IN ('etf', 'stock')"):
                self.assertEqual(alive(), 4)



# (release 1019l, the owner's goal V3: these mechanisms on release 1019i's money table, league/tests/v2_walls.py;
# the V3 rows' own effects are league/tests/test_v3_walls.py's)
from league.tests.v2_walls import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
