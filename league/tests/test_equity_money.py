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


class TheTable(unittest.TestCase):
    def test_the_block_as_e1_deploys_it_is_inside_its_bounds_and_switched_on(self):
        self.assertEqual(equity_money_problems(), [])
        t = M.Table.from_constitution()
        e = t.equity
        self.assertIsInstance(e, M.EquityTable)
        self.assertEqual(e, M.EquityTable.from_constitution())
        self.assertIs(e.enabled, True, "A10.2: the switch ships on (elane.mode off and the stock proof hold the lane)")
        self.assertEqual((e.invested_share, e.cash_reserve, e.min_order_usd), (D("1.00"), D("50"), D("10")))
        self.assertEqual((e.probe_sleeve_share, e.probe_max_programs), (D("0.50"), 3), "A20: 0.50 x E, three seats")
        self.assertEqual(dict(e.position_share), {"etf": D("0.50"), "stock": D("0.20")})
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
        """The constitution's universe is `league.equity.config.UNIVERSE` exactly (symbols and classes; `league.ci` holds
        it to the gateway's STOCK_UNIVERSE), and no position share is above `config.POSITION_SHARE`."""
        from league.equity import config

        e = M.EquityTable.from_constitution()
        self.assertEqual(dict(e.universe), config.UNIVERSE)
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
        # Tightenings are accepted, a zero among them where zero stops the route.
        for rows in ({"probe__sleeve_share": "0"}, {"probe__max_programs": 0}, {"order_path__max_orders_day": 0},
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
    release before E1 brings fdf2ac7c back on the owner's deploy of it."""

    BEFORE = "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7"
    E1 = "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a"
    OFF = "23f17a1467610f8d252b55c6d6748f8fb1311a0142e3f92c43d4bff710886579"
    QUARTER = "3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2"

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
        self.assertIs(CONSTITUTION["equity_money"]["enabled"], True, "A10.2: the block as deployed is on")
        self.assertIn("equity_money.enabled is true but the gateway's STOCK_BUYS_REAL admits no buy",
                      self.check(self.house(gateway__stock_buys__enabled=False))[1], "so the deployed block needs it")
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


if __name__ == "__main__":
    unittest.main()
