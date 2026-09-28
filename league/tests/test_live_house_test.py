"""The House live test (`league/live/house_test.py`; the owner, Sept 28, 2026): one frozen, pre-registered program traded
1-lot as the House's own real instance, through the families' decider and order path, bounded by the money table's
`options_money.house_test`, yielding to the families, never evidence, in Profit as the House's own rows. With the fakes
of `live_fakes` and a STAND-IN program whose hashes are patched in for the pre-registered ones: the real program and its
parameters never enter the repository."""

import datetime as dt
import hashlib
import json
import os
import sqlite3
import unittest
from decimal import Decimal as D
from unittest import mock

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.gym.runtime import canonical, load_program
    from league.live import house_test as HT
    from league.live import money as M
    from league.live.chains import session_minutes
    from league.live.decider import InlineDecider
    from league.live.real import RLeg, ROrder, RPosition
    from league.live.step import OptionsLive
    from league.tests.live_fakes import MONDAY, at, family

#: The stand-in: a program of the frozen one's shape (NEEDS, PARAMS, STATE, decide) that opens `opens` $1-wide SPY call
#: verticals from minute `at`, `step` strikes apart, asking for `qty`, and closes each after `hold` minutes. Its notes
#: carry signal-like words that must never reach a public row.
STAND_IN = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"at": 571, "opens": 1, "qty": 3, "hold": 3, "limit": "natural", "atm": 0, "width": 1.0, "step": 2, "tif": 30}
STATE = {"opened": 0}

def decide(ctx):
    p = ctx.params
    out = []
    for pos in ctx.positions:
        if pos["held_minutes"] >= p["hold"]:
            out.append({"close": pos["id"], "limit": "natural", "note": "time exit z5 -2.31"})
    if STATE["opened"] < p["opens"] and ctx.minute >= p["at"] and not ctx.orders:
        k = p["atm"] + p["step"] * STATE["opened"]
        STATE["opened"] += 1
        out.append({"open": "debit_vertical", "root": "SPY", "qty": p["qty"], "limit": p["limit"], "tif": p["tif"],
                    "tag": "rebound_up", "note": "streak 3 z5 -2.31 trend 0.0123 dte 1",
                    "legs": [{"side": "long", "right": "C", "dte": 1, "atm": k},
                             {"side": "short", "right": "C", "rel": 0, "offset": p["width"]}]})
    return out
'''
BASE = {"at": 571, "opens": 1, "qty": 3, "hold": 3, "limit": "natural", "atm": 0, "width": 1.0, "step": 2, "tif": 30}

#: A probe family's real open of the stand-in's own first contracts (the nearest-the-money $1 call vertical a day out),
#: tried every minute from `at` while it holds and works nothing.
SAME = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"at": 573}
STATE = {}

def decide(ctx):
    if ctx.positions or ctx.orders or ctx.minute < ctx.params["at"]:
        return []
    return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": "natural", "tag": "t", "note": "family",
             "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                      {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
'''


def frozen_of(code: str, params: dict) -> dict:
    return {"code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "merged_params_sha256": hashlib.sha256(canonical(params).encode("utf-8")).hexdigest(),
            "run_sha": load_program(code, params=params).run_sha}


def session_back(n: int) -> dt.date:
    """The day `n` NYSE sessions back from MONDAY, MONDAY counted as the first."""
    day, count = MONDAY, 0
    while True:
        if session_minutes(day) is not None:
            count += 1
            if count == n:
                return day
        day -= dt.timedelta(days=1)


@unittest.skipUnless(HAVE, "numpy not installed")
class HouseCase(LiveCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(HT.FROZEN, {})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.install()
        self.switch(True)

    def tearDown(self):
        live = getattr(self, "live", None)
        for part in (getattr(live, "house_test", None), getattr(live, "calibration", None)):
            if part is not None:
                part.recorder.close()
        super().tearDown()

    def install(self, code: str = STAND_IN, **params) -> dict:
        """The operator's upload: the program and its merged params, the directory 700 and the files 600; the stand-in's
        hashes patched in as the pre-registered ones."""
        merged = {**BASE, **params}
        folder = self.root / HT.PRIVATE_DIR
        folder.mkdir(parents=True, exist_ok=True)
        os.chmod(folder, 0o700)
        for name, data in ((HT.PROGRAM, code.encode("utf-8")), (HT.PARAMS, canonical(merged).encode("utf-8"))):
            path = folder / name
            path.write_bytes(data)
            os.chmod(path, 0o600)
        HT.FROZEN.update(frozen_of(code, merged))
        return merged

    def switch(self, on: bool, **more) -> None:
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, "observe": False,
                                                                    "house_test": on, **more}}))

    def start(self, rows=(), *, hh=9, mm=30, proof=True, **kw):
        self.clock.set(at(MONDAY, hh, mm))
        live = self.make(list(rows), **kw)
        if proof:
            live.state.put("paper_proof", {"schema": 2, "status": "passed", "open_witness": True, "close_witness": True})
        return live

    def restart(self):
        self.live.close()
        self.live.state.close()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(),
                                config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def mine(self):
        return [b for b in self.venue.sent if str(b.get("client_order_id") or "").endswith("house-rebound-live")]

    def opens(self):
        return [b for b in self.mine() if b.get("legs") and b["legs"][0]["position_intent"] == "buy_to_open"]

    def refusals(self):
        return [p["why"] for p, _ in self.ledger.of("live.refusal") if p.get("instance") == HT.INSTANCE]

    def samples(self):
        db = sqlite3.connect(self.root / HT.FILE)
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM samples ORDER BY oid")]
        finally:
            db.close()

    def st(self):
        return self.live.state.get("house_test") or {}

    # ------------------------------------------------------------------ rows written straight to the live state
    def put_position(self, *, pid: int, status: str, cash: float = 0.0, max_loss_share: float = 0.0, fees: float = 0.0,
                     qty: int = 0) -> None:
        leg = RLeg(f"SPY260929C{600000 + pid:08d}", 1, 1, True, 600.0 + pid, "2026-09-29", 10_000 + pid)
        pos = RPosition(pid, HT.INSTANCE, HT.FAMILY, "debit_vertical", "SPY", [leg], qty, 1, max_loss_share,
                        max_loss_share, 0.0, fees=fees, cash=cash, opened_at=self.clock(), opened_day=MONDAY.isoformat(),
                        status=status, closed_at=self.clock() if status == "closed" else None)
        self.live.state.upsert("positions", pos.row(), "pid")

    def put_working_open(self, *, oid: int, max_loss: float, fees: float = 0.65) -> None:
        leg = RLeg(f"SPY260929C{700000 + oid:08d}", 1, 1, True, 700.0 + oid, "2026-09-29", 20_000 + oid)
        order = ROrder(oid, f"lv-test-{oid}", HT.INSTANCE, HT.FAMILY, "open", "debit_vertical", "SPY", [leg], 1,
                       max_loss / 100, f"{max_loss / 100:.2f}", 30, self.clock(), MONDAY.isoformat(), 0, status="working",
                       max_loss=max_loss, fees_est=fees)
        self.live.state.upsert("orders", order.row(), "oid")

    def plan(self, unit, *, exposure=None, equity="5481.65"):
        return self.live.house_test.plan(unit=D(str(unit)), equity=D(equity), exposure=exposure or M.Exposure(),
                                         day=self.live.day)


class TheRoute(HouseCase):
    def test_one_lot_of_the_program_through_the_order_path_the_houses_own_never_evidence(self):
        live = self.start()
        self.run_to(9, 30)
        start = self.st()["start"]
        self.assertEqual((start["day"], start["minute"]), (MONDAY.isoformat(), 570))
        self.assertTrue(start["release"])
        self.assertEqual(start["fill_model"], str(live.shadow.fill_model.version))
        self.assertEqual(live.instances[HT.INSTANCE].band, HT.BAND)
        self.run_to(9, 31)
        [opened] = self.mine()
        self.assertEqual(opened["qty"], "1", "one lot, whatever the program asks")
        [pos] = live.book.positions.values()
        self.assertEqual((pos.family, pos.instance, pos.qty, pos.tag), (HT.FAMILY, HT.INSTANCE, 1, HT.OPEN_WHY))
        self.assertFalse([row for row in live.site_inputs()["structures"] if row["real"]], "never an agent's structure")
        self.run_to(9, 36)
        opened_, closed = self.mine()
        self.assertEqual([leg["position_intent"] for leg in closed["legs"]], ["sell_to_close", "buy_to_close"])
        self.assertEqual(live.book.positions, {})
        whys = [r["why"] for r in live.state.rows("SELECT why FROM orders WHERE family=? ORDER BY oid", (HT.FAMILY,))]
        self.assertEqual(whys, [HT.OPEN_WHY, HT.CLOSE_WHY])
        # The public tape: the fixed text, never the program's note (nor anywhere in the ledger).
        fills = self.ledger.of("book.fill")
        self.assertEqual([(p["side"], p.get("reason"), p.get("entry_reason")) for p, _ in fills],
                         [("buy", HT.OPEN_WHY, None), ("sell", "program", HT.OPEN_WHY)])
        self.assertNotIn("z5", json.dumps([row[1] for row in self.ledger.rows], default=str))
        # Never evidence: no forward row, marked exported.
        [trade] = live.book.closed_trades()
        self.assertEqual(self.families.forward, {})
        self.assertEqual(live.state.rows("SELECT pid FROM forward_exports"), [{"pid": trade["pid"]}])
        # Its own private record: each leg's NBBO in the snapshot, the mid and natural, the program's rule, tag and note.
        rows = self.samples()
        self.assertEqual([(r["action"], r["offset"], r["outcome"], r["tag"]) for r in rows],
                         [("open", "natural", "filled", "rebound_up"), ("close", "natural", "filled", "")])
        self.assertIn("z5", rows[0]["note"])
        self.assertIn("z5", rows[1]["note"])
        quote = json.loads(rows[0]["quote"])
        self.assertEqual(len(quote["legs"]), 2)
        self.assertTrue(all(leg["bid"] is not None and leg["ask"] is not None for leg in quote["legs"]))
        self.assertIsNotNone(rows[0]["mid"])
        self.assertEqual(rows[1]["pid"], trade["pid"])
        self.assertEqual(oct(os.stat(self.root / HT.FILE).st_mode & 0o777), "0o600")
        status = live.health()["house_test"]
        self.assertEqual(status["numbers"]["round_trips"], 1)
        self.assertEqual(status["files"], "verified")

    def test_its_rows_are_profit_labelled_the_houses_in_the_positions_ledger(self):
        from league import publish, trading_profit

        live = self.start()
        self.run_to(9, 36)
        [trade] = live.book.closed_trades()
        at_ = "2026-09-28T13:40:00.000Z"
        read = trading_profit.ledger(self.root, live, at=at_)
        [row] = read["rows"]
        self.assertEqual((row["source"], row["family"], row["status"], row["structure"], row["right"]),
                         ("house", HT.FAMILY, "closed", "debit_vertical", "call"))
        self.assertEqual(D(read["pnl_usd"]), D(str(trade["pnl"])).quantize(D("0.01")))
        self.assertEqual(trading_profit.snapshot(self.root, live, at=at_)["pnl_usd"], read["pnl_usd"])
        site = publish.site_position(row, at_)
        self.assertIsNotNone(site)
        self.assertEqual(site["source"], "house")
        self.assertNotIn("compute", live.site_inputs())


class Bounds(HouseCase):
    def test_a_structure_over_its_cap_is_refused(self):
        self.install(atm=-3, width=3.0)                         # about $3 of debit: $300 of maximum loss
        live = self.start()
        self.run_to(9, 33)
        self.assertEqual(self.mine(), [])
        self.assertTrue(any("over its $100 cap" in why for why in self.refusals()), self.refusals())
        del live

    def test_the_fourth_open_is_refused(self):
        self.install(opens=4, hold=600)
        live = self.start()
        self.run_to(9, 40)
        self.assertEqual(len(self.opens()), 3)
        self.assertEqual(len(live.book.positions), 3)
        self.assertTrue(any("the most it holds is 3" in why for why in self.refusals()), self.refusals())

    def test_the_envelope_holds_realized_held_and_working_under_three_hundred(self):
        self.install(opens=0)
        live = self.start()
        self.run_to(9, 31)
        self.put_position(pid=1001, status="closed", cash=-140.0)             # R = 140
        self.put_position(pid=1002, status="open", max_loss_share=0.60, fees=0.65, qty=1)   # H = 60 + 1.30
        self.assertEqual(live.house_test.tally(MONDAY.isoformat())["possible"], D("201.30"))
        self.assertEqual(self.plan("98.70").qty, 1)
        refused = self.plan("98.71")
        self.assertEqual(refused.qty, 0)
        self.assertIn("over its $300", refused.reason)
        self.put_working_open(oid=2001, max_loss=40.0)                         # W = 40 + 1.30
        self.assertEqual(live.house_test.tally(MONDAY.isoformat())["possible"], D("242.60"))
        self.assertEqual(self.plan("57.40").qty, 1)
        self.assertEqual(self.plan("57.41").qty, 0)

    def test_it_leaves_the_families_the_calibrations_room_of_the_day_cap(self):
        self.grant.capital = "481.63"
        self.install(opens=0)
        live = self.start()
        self.run_to(9, 31)
        exposure = M.Exposure(day_opened=D("250"))
        self.assertEqual(self.plan("31.63", exposure=exposure, equity="481.63").qty, 1)
        refused = self.plan("31.64", exposure=exposure, equity="481.63")
        self.assertEqual(refused.qty, 0)
        self.assertIn("$200.00 is kept for the families' opens", refused.reason)
        del live

    def test_the_stop_latches_at_150_for_good_and_its_exits_still_run(self):
        self.install(opens=2, hold=5)
        live = self.start()
        self.run_to(9, 31)
        self.assertEqual(len(live.book.positions), 1)
        self.put_position(pid=1001, status="closed", cash=-150.0)             # R reaches $150
        self.run_to(9, 32)
        stopped = self.st()["stopped"]
        self.assertIn("reached the $150 stop", stopped["why"])
        self.assertEqual(len([t for _, t in self.alerts if "House live test stopped" in t]), 1)
        self.run_to(9, 33)
        self.assertEqual(live.instances[HT.INSTANCE].mode, "exit_only")
        self.run_to(9, 45)
        self.assertEqual(len(self.opens()), 1, "no open after the stop")
        self.assertEqual(live.book.positions, {}, "its program's own close went")
        whys = [r["why"] for r in live.state.rows("SELECT why FROM orders WHERE family=? AND action='close'", (HT.FAMILY,))]
        self.assertEqual(whys, [HT.CLOSE_WHY])
        self.assertNotIn(HT.INSTANCE, live.instances, "flat: retired")
        # For good: a later gain that brings R back under $150 opens nothing.
        self.put_position(pid=1002, status="closed", cash=200.0)
        live._families_at = float("-inf")
        self.run_to(9, 50)
        self.assertNotIn(HT.INSTANCE, live.instances)
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(self.plan("50").qty, 0)
        self.assertEqual(len([t for _, t in self.alerts if "House live test stopped" in t]), 1, "alerted once")

    def test_the_twentieth_session_opens_and_the_twenty_first_ends_it(self):
        self.assertEqual(session_back(1), MONDAY)
        live = self.start()
        live.state.put("house_test", {"start": {"day": session_back(20).isoformat()}})
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1, "the 20th session")
        self.assertIsNone(self.st().get("ended"))
        self.restart()
        self.live.state.put("house_test", {"start": {"day": session_back(21).isoformat()}})
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        self.assertIn("its 20 sessions are over", self.st()["ended"]["why"])
        self.assertEqual(len(self.opens()), 1, "nothing opens on the 21st")
        self.assertEqual(self.live.house_test.sessions_used(MONDAY), 21)

    def test_thirty_round_trips_open_or_working_refuse_and_thirty_closed_end_it(self):
        self.install(opens=0)
        live = self.start()
        self.run_to(9, 31)
        for n in range(29):
            self.put_position(pid=1000 + n, status="closed", cash=0.0)
        self.assertEqual(self.plan("50").qty, 1)
        self.put_working_open(oid=2001, max_loss=40.0)
        refused = self.plan("50")
        self.assertEqual(refused.qty, 0)
        self.assertIn("30 round trips closed, open or working", refused.reason)
        self.assertIsNone(self.st().get("ended"), "a working open is not a closed round trip")
        self.put_position(pid=1029, status="closed", cash=0.0)
        self.run_to(9, 32)
        self.assertIn("30 round trips closed", self.st()["ended"]["why"])


class TheFamiliesFirst(HouseCase):
    def test_a_working_open_yields_to_a_family_refused_on_its_contracts(self):
        def hook(body):
            house = str(body.get("client_order_id") or "").endswith("house-rebound-live")
            self.venue.fill = "none" if house else "natural"

        self.venue.on_submit = hook
        self.install(limit="mid")
        live = self.start([family("fam", SAME, band="probe")])
        self.run_to(9, 32)
        [house_open] = self.mine()
        self.run_to(9, 33)
        self.assertEqual(len(self.venue.cancels), 1, "cancelled the minute the family was refused")
        self.run_to(9, 36)
        fam = live.state.rows("SELECT status, legs FROM orders WHERE family='fam' AND action='open'")
        self.assertEqual(fam[0]["status"], "filled")
        self.assertEqual({leg["symbol"] for leg in json.loads(fam[0]["legs"])},
                         {leg["symbol"] for leg in house_open["legs"]}, "the same contracts")
        [row] = self.samples()
        self.assertEqual((row["action"], row["outcome"], row["cancel_reason"]), ("open", "interrupted", HT.YIELDED))
        self.assertTrue([p for p, _ in self.ledger.of("live.instance") if p.get("state") == "house test yielded"])

    def test_the_families_intents_are_applied_before_its_own(self):
        self.venue.fill = "none"
        self.install(at=575, limit="mid")
        live = self.start()
        self.run_to(9, 31)
        self.families.rows["fam"] = family("fam", SAME.replace('"at": 573', '"at": 575'), band="probe")
        live._families_at = float("-inf")
        self.run_to(9, 32)
        self.assertEqual(list(live.instances)[:2], [HT.INSTANCE, "fam@1:s"], "the House's instance came first")
        self.run_to(9, 35)
        working = [o for o in live.book.orders.values() if o.working]
        self.assertEqual([o.family for o in working], ["fam"])
        self.assertEqual(self.mine(), [])
        self.assertTrue(any(why.startswith("one order stream per contract") for why in self.refusals()), self.refusals())


class TheProgram(HouseCase):
    def test_a_changed_program_never_runs(self):
        path = self.root / HT.PRIVATE_DIR / HT.PROGRAM
        path.write_bytes(STAND_IN.encode("utf-8") + b"\n")
        live = self.start()
        self.run_to(9, 35)
        self.assertNotIn(HT.INSTANCE, live.instances)
        self.assertEqual(self.mine(), [])
        self.assertIn("is not the pre-registered", live.health()["house_test"]["files"])

    def test_changed_params_group_readable_files_and_a_missing_file_are_refused(self):
        folder = self.root / HT.PRIVATE_DIR
        self.assertIsInstance(HT.load_private(self.root), tuple)
        (folder / HT.PARAMS).write_text(canonical({**BASE, "hold": 4}))
        self.assertIn("params' sha256", HT.load_private(self.root))
        self.install()
        os.chmod(folder / HT.PROGRAM, 0o640)
        self.assertIn("readable by group or other", HT.load_private(self.root))
        self.install()
        os.chmod(folder, 0o750)
        self.assertIn("open to group or other", HT.load_private(self.root))
        self.install()
        (folder / HT.PARAMS).unlink()
        self.assertEqual(HT.load_private(self.root), "params.json is missing")
        os.symlink(folder / HT.PROGRAM, folder / HT.PARAMS)
        self.assertEqual(HT.load_private(self.root), "params.json is not a regular file")

    def test_a_run_sha_not_the_preregistered_one_fails_for_good(self):
        HT.FROZEN["run_sha"] = "0" * 64
        live = self.start()
        self.run_to(9, 30)
        [saved] = live.state.rows("SELECT why, mode FROM instances WHERE id=?", (HT.INSTANCE,))
        self.assertTrue(saved["why"].startswith("the program does not load: its run sha"), saved)
        self.assertEqual(saved["mode"], "exit_only")
        self.assertTrue(any("House live test's program does not load" in text for _, text in self.alerts))
        self.run_to(9, 33)
        self.assertEqual(self.mine(), [])
        self.assertFalse(live.instances.get(HT.INSTANCE) and not live.instances[HT.INSTANCE].fatal)
        self.restart()
        self.clock.set(self.clock() + 60)
        self.live._families_at = float("-inf")
        self.run_to(9, 40)
        self.assertEqual(self.mine(), [], "sticky across a restart")
        self.assertFalse(self.live.instances.get(HT.INSTANCE) and not self.live.instances[HT.INSTANCE].fatal)

    def test_a_restored_program_that_changed_is_refused_and_its_positions_closed(self):
        self.install(hold=600)
        live = self.start()
        self.run_to(9, 31)
        self.assertEqual(len(live.book.positions), 1)
        live.state.execute("UPDATE instances SET code = code || '\n' WHERE id=?", (HT.INSTANCE,))
        self.restart()
        inst = self.live.instances[HT.INSTANCE]
        self.assertTrue(inst.fatal)
        self.assertIn("is not the pre-registered", inst.error)
        self.clock.set(self.clock() + 60)
        self.run_to(9, 34)
        self.assertEqual(self.live.book.positions, {}, "the House closed it as an orphan's")
        [close] = [b for b in self.mine() if b["legs"][0]["position_intent"] == "sell_to_close"]
        self.assertEqual(len(self.opens()), 1)
        del close


class Gates(HouseCase):
    def test_nothing_with_real_money_off(self):
        live = self.start(real_money=False)
        self.run_to(9, 35)
        self.assertNotIn(HT.INSTANCE, live.instances)
        self.assertEqual(self.venue.sent, [])
        self.assertEqual(live.health()["house_test"]["wanted"], "real money is off (config.json real_money)")

    def test_nothing_without_the_grant(self):
        self.grant.active = False
        live = self.start()
        self.run_to(9, 35)
        self.assertEqual(self.mine(), [])
        self.assertIsNone(self.st().get("start"), "the clock waits for real entries")
        self.assertTrue(any("grant" in why for why in self.refusals()), self.refusals())

    def test_nothing_before_the_paper_proof(self):
        live = self.start(proof=False)
        self.run_to(9, 35)
        self.assertEqual(self.mine(), [])
        self.assertIsNone(self.st().get("start"))
        self.assertTrue(any("paper proof" in why for why in self.refusals()), self.refusals())
        del live

    def test_nothing_with_the_switch_off_and_off_sends_it_to_exits_only_then_it_retires(self):
        self.switch(False)
        live = self.start()
        self.run_to(9, 33)
        self.assertNotIn(HT.INSTANCE, live.instances)
        self.assertEqual(live.health()["house_test"]["wanted"], "live.house_test is off")
        self.assertEqual(live.health()["house_test"]["files"], "verified", "the files are checked before it is on")
        self.switch(True)
        self.install(opens=2, hold=5)
        live._families_at = float("-inf")
        self.run_to(9, 34)
        self.assertEqual(len(live.book.positions), 1)
        self.switch(False)
        live._families_at = float("-inf")
        self.run_to(9, 35)
        self.assertEqual(live.instances[HT.INSTANCE].mode, "exit_only")
        self.run_to(9, 45)
        self.assertEqual(len(self.opens()), 1)
        self.assertEqual(live.book.positions, {})
        self.assertNotIn(HT.INSTANCE, live.instances)

    def test_a_malformed_swarm_json_turns_it_off(self):
        (self.root / "swarm.json").write_text("{\"live\": {\"house_test\": true,")
        live = self.start()
        self.run_to(9, 33)
        self.assertFalse(live.switches()["house_test"])
        self.assertNotIn(HT.INSTANCE, live.instances)


class Restart(HouseCase):
    def test_a_restart_keeps_the_clock_the_trips_and_the_realized_loss(self):
        self.install(opens=3, hold=600)
        live = self.start()
        self.run_to(9, 31)
        self.put_position(pid=1001, status="closed", cash=-40.0)
        self.run_to(9, 32)
        before = dict(self.st())
        self.assertEqual(before["numbers"]["realized_loss_usd"], "40.00")
        self.restart()
        self.assertEqual(self.st()["start"], before["start"])
        inst = self.live.instances[HT.INSTANCE]
        self.assertFalse(inst.fatal)
        self.assertEqual(self.live.house_test.sessions_used(MONDAY), 1)
        t = self.live.house_test.tally(MONDAY.isoformat())
        self.assertEqual((t["realized_loss"], t["closed"]), (D("40"), 1))
        self.assertEqual(t["open"], len(self.live.book.positions))
        self.clock.set(self.clock() + 60)
        self.run_to(9, 40)
        self.assertEqual(self.st()["start"], before["start"], "the clock never restarts")
        self.assertEqual(len(self.live.book.positions), 3, "the 3-open cap counts what the restart restored")
        self.assertEqual(self.st()["numbers"]["realized_loss_usd"], "40.00")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheTable(unittest.TestCase):
    def test_the_pre_registered_bounds_are_the_top_of_their_ranges(self):
        from league.constitution import CONSTITUTION, OPTIONS_MONEY_BOUNDS

        t = M.Table.from_constitution()
        self.assertEqual((t.house_test_structure, t.house_test_open, t.house_test_envelope, t.house_test_stop,
                          t.house_test_sessions, t.house_test_round_trips), (D("100"), 3, D("300"), D("150"), 20, 30))
        for key, value in CONSTITUTION["options_money"]["house_test"].items():
            self.assertEqual(D(OPTIONS_MONEY_BOUNDS[f"house_test.{key}"][1]), D(str(value)), key)

    def test_the_public_module_holds_hashes_only(self):
        self.assertEqual(sorted(HT.FROZEN), ["code_sha256", "merged_params_sha256", "run_sha"])
        for value in (*HT.FROZEN.values(), HT.PREREGISTRATION_SHA256):
            self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertEqual(HT.FAMILY, "house:rebound-live")
        from league import trading_profit

        self.assertEqual(trading_profit.source_of(HT.FAMILY), "house")


if __name__ == "__main__":
    unittest.main()
