"""THE OLD LANES ARE EXITS ONLY (the owner's goal of Oct 19, 2026; the frozen pre-registration PREREG-EVL-1, section 8:
"the index ETF and options programs take no new entries from the first House release after the registration time (it
switches equity opens off; options reads are already off); their open lots exit by their own rules"): the
constitution's `equity_money.enabled` is False, and no other row moved.

Held here: the row in force, and the table with it set back being the one before to the last hex (money digest
5ea6f99f, constitution 82a9a5a4); the digests it moved, every pair of the grid's once (`equity_design.DIGESTS`, the
older pins in `DIGESTS_OPENS_ON`); the standing grant, re-ratified on the owner's deploy alone, and the rollback (the row
alone, True) ratified the same way; the CI agreement with the gateway's STOCK_BUYS_REAL "on" (the House's row is the
switch); and THE EQUITY BOOK ON THE TABLE IN FORCE (league/equity/live.py, the harness of
league/tests/test_equity_book.py with the constitution's own equity table): no real buy ever goes, at the open or at
the close; a program's own sell, a carried exit, the close window, the maximum hold and the owner's flatten all go;
and the decide still runs while the book holds a lot (the programs' sells are planned), and rests once it holds
nothing. Invented figures only; standard library only."""

import re
import unittest
from unittest.mock import patch

from league import ci
from league.constitution import CONSTITUTION, PINNED_DIGEST, digest, equity_money_problems, money_digest
from league.live import money as M
from league.tests import equity_design as X
from league.tests import test_equity_book as T
from league.tests.test_standing_grant import HOUR, StandingCase, owner_deploy, updater_deploy

#: The table before the stop (release 1017r's and release R0's, `set_design 6 0.25`): money digest, constitution digest.
ON = ("5ea6f99f0978374d78ffad577e70574cef4b83314da8a7b0be72cc16031f633c",
      "82a9a5a4d5feab292ea0fb72a0382db4d5d893be93695c905897f6939feb219b")
#: The table in force, the stop: the same table with `equity_money.enabled` False.
OFF = ("f4fc39ff3b39635e7351c2f01cb0c84adf109a57d41f0eb0599d628dffa51117",
       "34bbe7a594468a6b3ea12d3e96c4a8a6ed8f320936faa1a87d8cf4e66f31beeb")
#: What the book answers an open while the row is False (league/equity/live.py `_open_block`).
EXITS_ONLY = "equity_money.enabled is false: exits only"


def differences(a, b, path=()):
    """Every path at which two nested JSON-like values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b), key=str):
            if key not in a or key not in b:
                out.append(path + (key,))
            else:
                out += differences(a[key], b[key], path + (key,))
        return out
    return [] if type(a) is type(b) and a == b else [path]


class TheRow(unittest.TestCase):
    def test_the_row_is_off_and_it_alone_moved(self):
        self.assertIs(CONSTITUTION["equity_money"]["enabled"], False)
        self.assertEqual(equity_money_problems(), [], "False is inside its choices: the stop is a constitution-only change")
        self.assertIs(M.Table.from_constitution().equity.enabled, False)
        before = X.opens_on()
        self.assertEqual(differences(CONSTITUTION, before), [("equity_money", "enabled")])
        self.assertEqual((money_digest(before), digest(before)), ON,
                         "with the row set back the constitution is the one before, to the last hex")
        self.assertEqual((money_digest(), digest()), OFF)
        self.assertEqual(digest(), PINNED_DIGEST)

    def test_every_pair_moved_once_and_the_older_pins_hold_with_the_row_set_back(self):
        self.assertEqual((money_digest(), PINNED_DIGEST), X.DIGESTS[X.in_force()])
        self.assertEqual(X.DIGESTS_OPENS_ON[X.in_force()], ON)
        for pair in X.CANDIDATES:
            at = X.constitution_at(*pair)
            self.assertIs(at["equity_money"]["enabled"], False)
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS[pair], pair)
            back = X.opens_on(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_OPENS_ON[pair], f"{pair}: before the row")
            # Every older table's helper sets the row back too: E4's step two is on its own pins as before.
            self.assertIs(X.before_opf1(at)["equity_money"]["enabled"], X.ENABLED_BEFORE)
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_OPENS_ON.values()), set(), "every pin moved with the row")
        self.assertEqual(len({money for money, _ in X.DIGESTS.values()}), len(X.CANDIDATES), "every pair is its own")
        # The constitution in force is untouched by the helpers (each works on a copy).
        self.assertIs(CONSTITUTION["equity_money"]["enabled"], False)

    def test_the_documents_name_the_digests_in_force(self):
        line = X.block("operations")[-1]
        self.assertIn(f"Money digest `{OFF[0][:8]}`, full digest `{OFF[1][:8]}`", line)
        self.assertIn(f"`{X.DIGESTS[X.REFERENCE][0][:8]}` / `{X.DIGESTS[X.REFERENCE][1][:8]}`", line,
                      "the pair's rollback under the stop is the grid's own pin")
        for kind in X.BLOCKS:
            self.assertEqual(X.read_block(kind), X.block(kind), kind)


class TheGrant(StandingCase):
    """The stop is a money rule (no row of `equity_money` is in `RISK_FREE`): a grant ratified on the table before it
    holds nothing after the owner's deploy until the standing grant re-ratifies it at the House's start, on the owner's
    release change only; the rollback (True) is the digest before, ratified the same way."""

    def pinned_on(self):
        with patch.dict(CONSTITUTION["equity_money"], enabled=True):
            self.assertEqual(money_digest(), ON[0])
            grant = self.enabled()
        self.assertEqual(money_digest(), OFF[0])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], ON[0])
        return grant

    def test_the_owners_deploy_re_ratifies_it_and_the_updater_never_does(self):
        grant = self.pinned_on()
        self.assertFalse(grant.allows_live(2), "a moved money rule holds every real entry until it is ratified")
        self.assertTrue(grant.standing_due()["digest_moved"])
        out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))
        out = self.standing(grant, release="r-opens-off", rows=owner_deploy(self.clock() - 60, release="r-opens-off"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertIn(f"money digest {ON[0][:12]} -> {OFF[0][:12]}", grant.ratifications()[-1]["why"])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], OFF[0])
        self.assertTrue(grant.allows_live(2))

    def test_the_rollback_is_the_row_alone_ratified_the_same_way(self):
        grant = self.pinned_on()
        self.standing(grant, release="r-opens-off", rows=owner_deploy(self.clock() - 60, release="r-opens-off"))
        self.clock.advance(HOUR)
        with patch.dict(CONSTITUTION["equity_money"], enabled=True):
            self.assertEqual((money_digest(), digest()), ON, "the rollback lands on the digests before, exactly")
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-back", rows=owner_deploy(self.clock() - 60, release="r-back"))
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], ON[0])
            self.assertTrue(grant.allows_live(2))


class TheGateway(unittest.TestCase):
    def test_the_gateway_stays_on_and_ci_agrees(self):
        """`enabled` True needs the gateway's STOCK_BUYS_REAL "on"; False agrees with the gateway on or off (the House's
        row is the switch, A8). The gateway is not changed by the stop: it still reads "on"."""
        wrangler = (ci.REPO / "gateway" / "wrangler.jsonc").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'^\s*"STOCK_BUYS_REAL"\s*:\s*"([^"]*)"', wrangler, flags=re.M), ["on"])
        self.assertEqual(ci.check_equity(), [], "the tree as it stands: enabled False beside the gateway's buys on")
        table = CONSTITUTION["equity_money"]
        universe = {s: k for k in ("etf", "stock") for s in table["universe"][k]}
        shares = {"etf": "0.5", "stock": "0.2"}
        for buys_on in (True, False):
            self.assertEqual(ci.stock_agreement(table, universe=universe, buys_on=buys_on, shares=shares, source="t"), [],
                             buys_on)
        refused = ci.stock_agreement(X.opens_on()["equity_money"], universe=universe, buys_on=False, shares=shares,
                                     source="t")
        self.assertTrue(any("STOCK_BUYS_REAL admits no buy" in p for p in refused), "the rollback needs the gateway on")


class TheBookInForce(T.BookTest):
    """The equity book on the constitution's own equity table (`enabled` False), every other gate open."""

    def in_force(self) -> T.Harness:
        table = M.Table.from_constitution().equity
        self.assertIs(table.enabled, False)
        return self.harness(table=table)

    def buys(self, h: T.Harness) -> list[dict]:
        return [b for b in h.venue.sent if b["side"] == "buy"]

    def test_no_buy_goes_at_the_open_or_the_close_and_a_programs_sell_does(self):
        h = self.in_force()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        sell = h.intent(a, "sell", symbol="SPY", lid=lot.lid)
        opening = h.intent(b, "buy", symbol="QQQ", share="0.2")
        closing = h.intent(b, "buy", symbol="IWM", share="0.2", at_="close")
        for hh, mm in ((9, 31), (9, 32), (9, 34)):
            h.tick(hh, mm)
        self.assertEqual([s["side"] for s in h.venue.sent], ["sell"])
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual(h.get_intent(sell.iid).status, "done")
        self.assertEqual(h.get_intent(opening.iid).why, EXITS_ONLY)
        h.tick(9, 46)
        self.assertEqual(h.get_intent(opening.iid).status, "missed")
        self.assertIn(EXITS_ONLY, h.get_intent(opening.iid).why)
        for hh, mm, ss in ((15, 55, 3), (15, 56, 3), (15, 59, 3), (15, 59, 33), (16, 0, 3)):
            h.tick(hh, mm, ss)
        self.assertEqual(self.buys(h), [], "no real equity buy, at the open or at the close")
        self.assertEqual(h.get_intent(closing.iid).status, "missed")
        self.assertIn(EXITS_ONLY, h.get_intent(closing.iid).why)
        self.assertEqual(h.book.health()["enabled"], False)

    def test_a_carried_exit_and_the_close_window_go(self):
        h = self.in_force()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.venue.fill = "none"
        for hh, mm in ((9, 31), (9, 32), (12, 0), (15, 55), (15, 56), (15, 59), (16, 0)):
            h.tick(hh, mm)
        orders = h.orders()
        self.assertTrue(orders and all(o.side == "sell" for o in orders))
        self.assertEqual(orders[-1].at, "close", "the close window sent it")
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        carried = h.intents(kind="house_exit")
        self.assertEqual([(c.exec_day, c.at, c.lid, c.status) for c in carried],
                         [("2026-10-13", "open", lot.lid, "planned")])
        h.venue.fill = "cross"
        h.tick(9, 31, day=T.TUESDAY)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual(self.buys(h), [])

    def test_the_owners_flatten_goes(self):
        h = self.in_force()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.clock.set(T.at(T.MONDAY, 12, 0))
        self.assertEqual(h.book.flatten("the old lanes"), 1)
        h.tick(12, 1)
        self.assertEqual(h.book._lot(lot.lid).reason, "flatten")
        self.assertEqual(self.buys(h), [])

    def setup_decide(self, h: T.Harness, *, needs=None):
        h.families.rows = {"seed-overnight-spy": T.family_row()}
        inst = h.instance()
        if needs is not None:
            h.decider.needs[inst.id] = needs
        h.decide_setup(T.MONDAY, symbols=("SPY", "QQQ"))
        h.decide_setup(T.TUESDAY, symbols=("SPY", "QQQ"))
        return inst

    def test_the_decide_runs_while_a_lot_is_held_and_rests_once_none_is(self):
        h = self.in_force()
        inst = self.setup_decide(h)
        mine = h.lot(inst, "SPY", "0.4", "590")
        h.decider.plans[inst.id] = [{"sell": mine.lid}, {"buy": "SPY", "share": 0.5, "at": "close"}]
        h.tick(16, 21)
        h.tick(16, 31)
        self.assertEqual(h.state.get("eq_decide")["status"], "done", "a lot is held: the programs are asked")
        self.assertEqual(len(h.decider.jobs), 1)
        planned = [(i.kind, i.at, i.exec_day) for i in h.intents(instance=inst.id, status="planned")]
        self.assertEqual(planned, [("sell", "open", "2026-10-13"), ("buy", "close", "2026-10-13")])
        h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5}]
        for hh, mm, ss in ((9, 31, 3), (9, 34, 3), (15, 55, 3), (15, 59, 33), (16, 0, 3)):
            h.tick(hh, mm, ss, day=T.TUESDAY)
        self.assertEqual(h.book._lot(mine.lid).status, "closed", "the program's sell went")
        self.assertEqual(self.buys(h), [])
        self.assertEqual([i.status for i in h.intents(instance=inst.id, kind="buy")], ["missed"])
        h.tick(16, 21, day=T.TUESDAY)
        h.tick(16, 31, day=T.TUESDAY)
        self.assertEqual(h.state.get("eq_decide")["status"], "idle", "nothing held: no program is asked")
        self.assertEqual(h.state.get("eq_decide")["why"], "the lane is off and holds nothing")
        self.assertEqual(len(h.decider.jobs), 1)

    def test_the_maximum_hold_exits_at_the_next_open(self):
        h = self.in_force()
        inst = self.setup_decide(h, needs={"symbols": ["SPY"], "history": 5, "max_hold_sessions": 2})
        old = h.lot(inst, "SPY", "0.4", "590", opened=T.FRIDAY)
        h.tick(16, 31)
        exits = h.intents(kind="house_exit")
        self.assertEqual([(e.lid, e.tag, e.exec_day, e.at) for e in exits], [(old.lid, "max_hold", "2026-10-13", "open")])
        h.tick(9, 31, day=T.TUESDAY)
        self.assertEqual(h.book._lot(old.lid).reason, "max_hold")
        self.assertEqual(self.buys(h), [])


if __name__ == "__main__":
    unittest.main()
