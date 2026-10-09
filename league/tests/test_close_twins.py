"""THE PER-CLOSE FILL REPLAY (Oct 10, 2026; league/ops/twins.py; the readiness audit's B1 (c)): every real close of an
agent program gets its own replay twin, the real trade's own orders replayed on the gate image by the Gym's own engine and
fill model, and the direction lane's operator report matches a close to its twin.

What is pinned here:
- the puppet is an admissible Gym program, and a plan reads the real trade from the live book's own rows (the shapes of
  pid 14, the Oct 8 tuition close, and pid 41, the first Probe trade): contracts, the open's decision minute, limit, size
  and time in force, the close orders the venue received (never the House's expiry close, which the Gym makes itself,
  nor a refused one), the trade's NYSE sessions; a trade the puppet cannot replay is said so, never guessed;
- end to end through the REAL batch runner, on a synthetic gate store (the gate's mark, the forward window, the gate's
  capability, a natural-only fill model): the twin finds the exact contract among decoys, fills as the Gym fills, and
  leaves as the trade did (the House's expiry close, a program close, expiry); the model's no-fill, a contract the image
  lacks at the minute, and an image without the entry day are each their own verdict;
- the round: one gate job a close (never a run row, never a trial), only once the image holds its exit day, never a
  House route's close, a failed job asked again at most `attempts` times, its own switch, and the loop runs it as its own
  round after the nightly forward;
- the report: a close with a priced twin is matched to it; a close whose twin is final but unpriced is never matched to
  the nightly replay instead; with no twin records the figures are D5's exactly, key for key.

No league/live, league/gym or constitution file changes (rule F0): `test_no_live_gym_or_constitution_file_names_the_twins`.
Every figure is invented; the synthetic stores are tiny and skip cleanly without numpy/pyarrow."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from league.live.state import LiveState
from league.ops import twins as T
from league.swarm.pool import PoolError
from league.swarm.store import SwarmStore

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import batch as B
    from league.gym import runtime as RT
    from league.gym import synth

REPO = Path(__file__).resolve().parents[2]
_ALARM: dict = {}


def setUpModule():
    if HAVE and hasattr(signal, "SIGALRM"):
        _ALARM.update(handler=signal.getsignal(signal.SIGALRM), installed=RT._ALARM_INSTALLED)


def tearDownModule():
    # The Gym's runtime installs its SIGALRM handler once a process (`runtime._can_alarm`) and trusts it to stay. These
    # tests run Gym programs in the main thread earlier in the suite's order than any Gym test did, and a later module's
    # run of `league/runner.py` installs that runner's handler: the Gym's two timeout tests then met its alarm (Oct 10,
    # 2026, the full suite). So the process is put back as these tests found it, the Gym's flag included.
    if "installed" in _ALARM:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, _ALARM["handler"])
        RT._ALARM_INSTALLED = _ALARM["installed"]


D1, D2, D3, D4, D5 = (dt.date(2026, 10, 9), dt.date(2026, 10, 12), dt.date(2026, 10, 13), dt.date(2026, 10, 14),
                      dt.date(2026, 10, 16))
NY = T.NY


def ny(day: dt.date, hh: int, mm: int = 0) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY).timestamp()


def leg(expiry: dt.date, strike: float, *, call: bool = True, side: int = 1) -> dict:
    right = "C" if call else "P"
    return {"expiry": expiry.isoformat(), "is_call": call, "key": int(strike * 1000), "ratio": 1, "side": side,
            "strike": float(strike), "symbol": f"SPY{expiry:%y%m%d}{right}{int(strike * 1000):08d}"}


class Book:
    """A live book (the House's own schema, `LiveState`) with positions and their orders, as the House writes them."""

    def __init__(self, root: Path):
        self.state = LiveState(root / "live.sqlite")
        self.oid = 0

    def close(self):
        self.state.close()

    def order(self, pid: int, *, action: str, day: dt.date, minute: int, limit: float, tif=None, status="filled",
              filled=1, forced=0, why="", family="dir-a", instance="dir-a@1:r", type_="long_call", legs=()) -> int:
        self.oid += 1
        self.state.upsert("orders", {
            "oid": self.oid, "client_id": f"lv-x-{self.oid}", "venue_id": None, "instance": instance, "family": family,
            "action": action, "type": type_, "root": "SPY", "legs": json.dumps(list(legs)), "qty": 1, "limit_value": limit,
            "limit_price": f"{limit:.2f}", "tif": tif, "placed_at": ny(day, 10) + minute * 60, "day": day.isoformat(),
            "placed_minute": minute, "status": status, "filled_qty": filled, "fill_value": limit if filled else 0.0,
            "pid": pid, "forced": forced, "why": why, "updated_at": ny(day, 10)}, "oid")
        return self.oid

    def position(self, pid: int, *, legs: list, opened: dt.date, minute: int, cash: float, max_loss: float, closed_at: float,
                 reason: str = "program", family="dir-a", instance="dir-a@1:r", type_="long_call", order: int | None = None,
                 status: str = "closed") -> None:
        self.state.upsert("positions", {
            "pid": pid, "instance": instance, "family": family, "type": type_, "root": "SPY", "legs": json.dumps(legs),
            "qty": 0, "opened_qty": 1, "entry": max_loss / 100.0, "max_loss_share": max_loss / 100.0, "collateral": 0.0,
            "fees": 0.10, "cash": cash, "opened_at": ny(opened, 10) + minute * 60, "opened_day": opened.isoformat(),
            "opened_minute": minute, "tag": "t", "note": "", "status": status, "closed_at": closed_at,
            "exit_value_qty": 0.0, "reason": reason, "tuition": 1 if instance.endswith((":t", ":i")) else 0,
            "info": json.dumps({"order": order} if order else {})}, "pid")


def trades(book: Book) -> None:
    """The book of every scenario below (each a real close as the House books it; figures invented):
    41 the Probe long call held to the House's expiry close; 42 a long call the program closed the next session; 43 a
    passive open the live market filled and the natural-only model never would; 44 a contract the image quotes only from
    11:40; 45 a far call vertical left to expire; 46 a trade opened on a day the image lacks; 47 a broken structure closed
    leg by leg; 48 a House calibration round trip; 49 a trade whose exit day the image does not hold yet."""
    a = [leg(D2, 781)]
    o = book.order(41, action="open", day=D1, minute=56, limit=0.43, tif=10, legs=a)
    book.order(41, action="close", day=D2, minute=345, limit=0.19, forced=1, legs=a,
               why="an expiring long call: closed before the close cutoff whatever its moneyness")
    book.position(41, legs=a, opened=D1, minute=56, cash=-24.10, max_loss=43.0, closed_at=ny(D2, 15, 16), reason="forced",
                  order=o)
    b = [leg(D5, 785)]
    o = book.order(42, action="open", day=D1, minute=100, limit=0.50, tif=5, legs=b)
    book.order(42, action="close", day=D2, minute=40, limit=0.80, tif=3, status="refused", filled=0, legs=b)  # never sent
    book.order(42, action="close", day=D2, minute=60, limit=0.68, tif=10, legs=b)
    book.position(42, legs=b, opened=D1, minute=100, cash=19.90, max_loss=50.0, closed_at=ny(D2, 10, 31), order=o)
    c = [leg(D5, 790)]
    o = book.order(43, action="open", day=D1, minute=56, limit=0.22, tif=5, legs=c)
    book.order(43, action="close", day=D2, minute=60, limit=0.25, tif=10, legs=c)
    book.position(43, legs=c, opened=D1, minute=56, cash=2.90, max_loss=22.0, closed_at=ny(D2, 10, 31), order=o)
    d = [leg(D5, 795)]
    o = book.order(44, action="open", day=D1, minute=56, limit=0.30, tif=10, legs=d)
    book.order(44, action="close", day=D2, minute=60, limit=0.20, tif=10, legs=d)
    book.position(44, legs=d, opened=D1, minute=56, cash=-10.10, max_loss=30.0, closed_at=ny(D2, 10, 31), order=o)
    e = [leg(D2, 800), leg(D2, 805, side=-1)]
    o = book.order(45, action="open", day=D1, minute=56, limit=0.10, tif=10, legs=e, type_="debit_vertical",
                   family="alp-b", instance="alp-b@3:t")
    book.position(45, legs=e, opened=D1, minute=56, cash=-10.20, max_loss=10.0, closed_at=ny(D3, 1, 11) - 4 * 3600,
                  reason="expired", type_="debit_vertical", family="alp-b", instance="alp-b@3:t", order=o)
    f = [leg(D2, 781)]
    o = book.order(46, action="open", day=dt.date(2026, 10, 8), minute=56, limit=0.80, tif=10, legs=f)
    book.position(46, legs=f, opened=dt.date(2026, 10, 8), minute=56, cash=-80.05, max_loss=80.0,
                  closed_at=ny(D2, 16, 0) + 4 * 3600, reason="expired", order=o)
    g = [leg(D2, 781), leg(D2, 782, side=-1)]
    o = book.order(47, action="open", day=D1, minute=56, limit=0.30, tif=10, legs=g, type_="debit_vertical")
    book.order(47, action="close_leg", day=D2, minute=200, limit=0.10, forced=1, legs=g[:1], type_="debit_vertical")
    book.position(47, legs=g, opened=D1, minute=56, cash=-20.0, max_loss=30.0, closed_at=ny(D2, 14), type_="debit_vertical",
                  order=o)
    h = [leg(D2, 781), leg(D2, 782, side=-1)]
    o = book.order(48, action="open", day=D1, minute=56, limit=0.40, tif=10, legs=h, type_="debit_vertical",
                   family="house:calibration", instance="house:calibration@0:c")
    book.position(48, legs=h, opened=D1, minute=56, cash=-1.0, max_loss=40.0, closed_at=ny(D1, 11), type_="debit_vertical",
                  family="house:calibration", instance="house:calibration@0:c", order=o)
    i = [leg(D4, 781)]
    o = book.order(49, action="open", day=D3, minute=56, limit=0.40, tif=10, legs=i)
    book.position(49, legs=i, opened=D3, minute=56, cash=-40.05, max_loss=40.0, closed_at=ny(D4, 16) + 4 * 3600,
                  reason="expired", order=o)


def market(root: str | Path) -> None:
    """The synthetic gate store the scenarios replay on: Oct 9 (Fri), Oct 12 (Mon) and Oct 13 (Tue), SPY at 777-779."""
    w = synth.Writer(root)
    w.calendar([D1, D2, D3])
    w.gate_mark()
    synth.flat_day(w, "SPY", D1, [
        # 41 and its decoys: the same strike a later expiry, the next strike, the put.
        {"expiration": D2, "strike": 781, "right": "C", "quotes": {571: (0.40, 0.42), 627: (0.42, 0.43), 640: (0.50, 0.52)}},
        {"expiration": D4, "strike": 781, "right": "C", "quotes": {571: (0.90, 0.95)}},
        {"expiration": D2, "strike": 780, "right": "C", "quotes": {571: (0.70, 0.72)}},
        {"expiration": D2, "strike": 781, "right": "P", "quotes": {571: (3.00, 3.10)}},
        {"expiration": D2, "strike": 782, "right": "C", "quotes": {571: (0.30, 0.32)}},
        {"expiration": D5, "strike": 785, "right": "C", "quotes": {571: (0.45, 0.50)}},
        {"expiration": D5, "strike": 790, "right": "C", "quotes": {571: (0.20, 0.30)}},
        {"expiration": D5, "strike": 795, "right": "C", "quotes": {700: (0.28, 0.30)}},
        {"expiration": D2, "strike": 800, "right": "C", "quotes": {571: (0.10, 0.12)}},
        {"expiration": D2, "strike": 805, "right": "C", "quotes": {571: (0.02, 0.04)}},
    ], prices=777.0)
    synth.flat_day(w, "SPY", D2, [
        {"expiration": D2, "strike": 781, "right": "C", "quotes": {571: (0.30, 0.32), 915: (0.20, 0.22)}},
        {"expiration": D4, "strike": 781, "right": "C", "quotes": {571: (0.60, 0.65)}},
        {"expiration": D5, "strike": 785, "right": "C", "quotes": {571: (0.70, 0.75)}},
        {"expiration": D5, "strike": 790, "right": "C", "quotes": {571: (0.24, 0.26)}},
        {"expiration": D5, "strike": 795, "right": "C", "quotes": {571: (0.20, 0.22)}},
        {"expiration": D2, "strike": 800, "right": "C", "quotes": {571: (0.01, 0.02)}},
        {"expiration": D2, "strike": 805, "right": "C", "quotes": {571: (0.01, 0.02)}},
    ], prices=779.0)
    synth.flat_day(w, "SPY", D3, [
        {"expiration": D4, "strike": 781, "right": "C", "quotes": {571: (0.40, 0.42)}},
    ], prices=778.0)
    w.finish()
    (Path(root) / "fill_model.json").write_text(json.dumps({"hazard": {}}))  # natural fills only: the figures by hand


class BatchPool:
    """The pool's two doors (`submit`, `wait`) over the REAL batch runner on the synthetic gate store: what a gate box runs
    (`driver.run` -> `batch.run_batch` with the gate's reason), and the pool's own stamps on a result."""

    def __init__(self, store_root: str | Path, *, fail: set | None = None):
        self.store_root = str(store_root)
        self.jobs = []
        self.fail = set(fail or ())

    def submit(self, job):
        self.jobs.append(job)
        if job.family in self.fail:
            job.error = "the batch timed out twice"
        else:
            doc = B.run_batch([(job.name, job.code, dict(job.params))], store_root=self.store_root, window=job.window,
                              roots=list(job.roots), start=dt.date.fromisoformat(job.start), end=dt.date.fromisoformat(job.end),
                              gate_reason=job.gate, fill_model_path=str(Path(self.store_root) / "fill_model.json"))
            job.result = {**doc["results"][0], "gym_image": "sbcp_gate", "gym_bundle": "gym-engine-4-test"}
        job.done.set()
        return job

    def wait(self, job, timeout=None, **_):
        if job.error:
            raise PoolError(job.error)
        return job.result


class Gate:
    def __init__(self, day: dt.date | None = D3):
        self.day = day

    def forward_target(self):
        return None if self.day is None else {"day": self.day.isoformat(), "checkpoint": "sbcp_gate", "bundle": "b"}


# ================================================================================================== the puppet and the plan
class ThePlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.book = Book(Path(self.tmp.name))
        self.addCleanup(self.book.close)
        trades(self.book)
        self.live = T.read_live(Path(self.tmp.name) / "live.sqlite")

    def plan(self, pid):
        pos = next(p for p in self.live["positions"] if p["pid"] == pid)
        return T.plan(pos, self.live["orders"].get(pid, []))

    def test_the_book_is_read_read_only_and_never_a_house_route(self):
        self.assertEqual([p["pid"] for p in self.live["positions"]], [41, 42, 43, 44, 45, 46, 47, 49])
        self.assertEqual([o["oid"] for o in self.live["orders"][42]], [3, 4, 5])
        since = T.read_live(Path(self.tmp.name) / "live.sqlite", since=ny(D2, 20, 30))
        self.assertEqual([p["pid"] for p in since["positions"]], [45, 49], "closed at or after `since` only")

    def test_pid_41s_twin_is_its_own_contract_minute_limit_size_and_sessions(self):
        p = self.plan(41)
        self.assertTrue(p["ok"], p["why"])
        self.assertEqual((p["start"], p["end"], p["first_expiry"], p["sessions"]),
                         ("2026-10-09", "2026-10-12", "2026-10-12", ["2026-10-09", "2026-10-12"]))
        self.assertEqual(p["params"], {
            "root": "SPY", "type": "long_call", "qty": 1, "leg_strike": [781.0], "leg_call": [1], "leg_side": [1],
            "leg_ratio": [1], "leg_dte": [3], "open_minute": 626, "open_limit": 0.43, "open_natural": 0, "open_tif": 10,
            "close_expiry": [], "close_minute": [], "close_limit": [], "close_natural": [], "close_tif": [],
            "dte_lo": 3, "dte_hi": 3})
        self.assertEqual(p["live"]["exit"], "house_close", "the House's expiry close: the Gym makes its own, never replayed")
        self.assertEqual((p["live"]["cash"], p["live"]["max_loss"], p["live"]["r"]), (-24.1, 43.0, -0.56047))

    def test_the_close_orders_the_venue_received_are_replayed_on_their_own_day_and_minute(self):
        p = self.plan(42)
        self.assertTrue(p["ok"], p["why"])
        # The refused close (minute 40) never reached the venue: only the filled one (minute 60, 10:30 ET) is replayed,
        # keyed by the first leg's days to expiry that day (Oct 16 - Oct 12 = 4).
        self.assertEqual({k: p["params"][k] for k in ("close_expiry", "close_minute", "close_limit", "close_natural",
                                                      "close_tif")},
                         {"close_expiry": [4], "close_minute": [630], "close_limit": [0.68], "close_natural": [0],
                          "close_tif": [10]})
        self.assertEqual((p["end"], p["live"]["exit"]), ("2026-10-12", "program_close"))

    def test_an_orphans_forced_close_is_replayed_at_the_natural(self):
        pos = next(p for p in self.live["positions"] if p["pid"] == 41)
        orders = [dict(o) for o in self.live["orders"][41]]
        orders[1].update(why="its program is gone (no instance): the House closes it", placed_minute=100)
        p = T.plan(pos, orders)
        self.assertEqual((p["params"]["close_minute"], p["params"]["close_natural"]), ([670], [1]))
        self.assertEqual(p["live"]["exit"], "house_forced")

    def test_a_vertical_left_to_expire_ends_on_its_expiry_day(self):
        p = self.plan(45)
        self.assertTrue(p["ok"], p["why"])
        self.assertEqual((p["end"], p["live"]["exit"], p["params"]["leg_side"], p["params"]["leg_strike"]),
                         ("2026-10-12", "expired", [1, -1], [800.0, 805.0]))

    def test_what_the_puppet_cannot_replay_is_said_never_guessed(self):
        self.assertIn("close_leg", self.plan(47)["why"])
        pos = dict(next(p for p in self.live["positions"] if p["pid"] == 41))
        far = dict(pos, legs=json.dumps([leg(dt.date(2026, 12, 18), 800)]))
        self.assertIn("days from expiry", T.plan(far, self.live["orders"][41])["why"])
        self.assertIn("no open order", T.plan(pos, [])["why"])
        self.assertIn("legs cannot be read", T.plan(dict(pos, legs="[]"), self.live["orders"][41])["why"])

    @unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
    def test_the_puppet_is_an_admissible_gym_program_with_the_trades_needs(self):
        program = RT.load_program(T.PUPPET, name="twin", params=self.plan(45)["params"])
        self.assertEqual(program.needs.as_dict(), {"roots": ["SPY"], "dte": [3, 3], "band": 0.3, "cadence": 1, "history": 0,
                                                   "start": 571, "end": 958})
        self.assertEqual(len(T.PUPPET_SHA), 64)
        job = T.job_for(self.plan(41))
        self.assertEqual((job.family, job.window, job.gate, job.purpose, job.priority, job.start, job.end, job.roots),
                         ("twin.41", "forward", T.GATE_REASON, "twin", 4.0, "2026-10-09", "2026-10-12", ("SPY",)))
        from league.gym.driver import programs_archive

        self.assertTrue(programs_archive({job.name: (job.code, job.params)}), "a plain file stem in the box's archive")


# ================================================================================================== end to end
@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class EndToEnd(unittest.TestCase):
    """Each scenario through the real batch runner on the synthetic gate store, judged."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="close-twins-")
        market(Path(cls.dir) / "store")
        cls.book = Book(Path(cls.dir))
        trades(cls.book)
        cls.live = T.read_live(Path(cls.dir) / "live.sqlite")

    @classmethod
    def tearDownClass(cls):
        cls.book.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def twin(self, pid):
        pos = next(p for p in self.live["positions"] if p["pid"] == pid)
        p = T.plan(pos, self.live["orders"].get(pid, []))
        pool = BatchPool(Path(self.dir) / "store")
        result = pool.wait(pool.submit(T.job_for(p)))
        return T.judge(p, result, at=ny(D3, 6))

    def test_pid_41_finds_its_contract_among_decoys_and_leaves_by_the_gyms_expiry_close(self):
        rec = self.twin(41)
        self.assertEqual(rec["status"], "priced", rec["why"])
        # Decided at 10:26 (626), met 10:27's quotes: the 781 call expiring Oct 12 at its ask 0.43 (not Oct 14's 0.95, nor
        # the 780 call's 0.72, nor the put). The Gym's expiry close at 15:15 Monday sells it at the bid 0.20. Fees 0.05 a
        # side: -43.05 + 19.95 = -23.10 on a maximum loss of 43.
        self.assertEqual(rec["twin"], {"pnl": -23.1, "max_loss": 43.0, "r": -0.53721, "exit": "house_close"})
        self.assertEqual((rec["gap_r"], rec["exit_agrees"]), (-0.02326, True))  # live sold at 0.19: a cent worse
        self.assertEqual((rec["image"], rec["days"], rec["puppet"]), ("sbcp_gate", ["2026-10-09", "2026-10-12"],
                                                                      T.PUPPET_SHA[:16]))

    def test_a_program_close_is_replayed_on_its_day_and_minute(self):
        rec = self.twin(42)
        self.assertEqual(rec["status"], "priced", rec["why"])
        # Open at 11:11 (671) at the ask 0.50; the close decided Monday 10:30 (630) with its 0.68 limit takes 10:31's
        # natural, the bid 0.70: 70 - 50 - 0.10 = 19.90, as the live fill.
        self.assertEqual(rec["twin"], {"pnl": 19.9, "max_loss": 50.0, "r": 0.398, "exit": "program_close"})
        self.assertEqual((rec["gap_r"], rec["exit_agrees"]), (0.0, True))
        self.assertEqual(rec["fills"]["closes"], 1, "the refused close was never sent")

    def test_the_models_no_fill_is_its_own_verdict_never_a_gap(self):
        rec = self.twin(43)
        self.assertEqual((rec["status"], rec["twin"], rec["gap_r"]), ("no_fill", None, None))
        self.assertEqual(rec["fills"]["opens"], 1)

    def test_a_contract_the_image_lacks_at_the_minute_is_no_contract(self):
        rec = self.twin(44)
        self.assertEqual((rec["status"], rec["fills"]["opens"]), ("no_contract", 0))

    def test_a_vertical_left_to_expire_expires_in_the_gym_too(self):
        rec = self.twin(45)
        self.assertEqual(rec["status"], "priced", rec["why"])
        self.assertEqual((rec["twin"]["exit"], rec["exit_agrees"]), ("expired", True))
        self.assertEqual(rec["twin"]["max_loss"], 10.0)

    def test_an_image_without_the_entry_day_is_no_contract(self):
        rec = self.twin(46)
        self.assertEqual(rec["status"], "no_contract")
        self.assertIn("no SPY day 2026-10-08", rec["why"])


class TheVerdict(unittest.TestCase):
    """`judge` on Gym answers that never reach a priced twin."""

    def plan(self):
        return {"pid": 7, "family": "f", "instance": "f@1:r", "root": "SPY", "type": "long_call", "start": "2026-10-09",
                "end": "2026-10-12", "first_expiry": "2026-10-12", "sessions": ["2026-10-09", "2026-10-12"],
                "params": {}, "live": {"cash": -10.0, "max_loss": 40.0, "r": -0.25, "exit": "program_close"}}

    def test_a_run_that_did_not_finish_failed(self):
        rec = T.judge(self.plan(), {"status": "error", "reason": "the unit timed out"}, at=0)
        self.assertEqual(rec["status"], "failed")
        self.assertIn("timed out", rec["why"])

    def test_an_image_missing_a_session_cannot_price_it_and_one_that_stops_short_is_asked_again(self):
        plan = dict(self.plan(), end="2026-10-13", sessions=["2026-10-09", "2026-10-12", "2026-10-13"])
        hole = {"status": "ok", "daily": [["2026-10-09", 0, 1], ["2026-10-13", 0, 1]], "trades": [], "fills": {}}
        self.assertEqual(T.judge(plan, hole, at=0)["status"], "unpriceable")
        short = {"status": "ok", "daily": [["2026-10-09", 0, 1]], "trades": [], "fills": {}}
        self.assertEqual(T.judge(plan, short, at=0)["status"], "failed")

    def test_two_trades_are_never_one_twin(self):
        result = {"status": "ok", "daily": [["2026-10-09", 0, 1], ["2026-10-12", 0, 1]], "fills": {"opens": 1},
                  "trades": [{"day": "2026-10-09", "pnl": 1, "max_loss": 40}, {"day": "2026-10-12", "pnl": 1, "max_loss": 40}]}
        self.assertEqual(T.judge(self.plan(), result, at=0)["status"], "unpriceable")

    def test_a_window_end_close_disagrees_with_a_program_close(self):
        result = {"status": "ok", "daily": [["2026-10-09", 0, 1], ["2026-10-12", 0, 1]],
                  "fills": {"opens": 1, "closes": 1, "filled": 1},
                  "trades": [{"day": "2026-10-09", "pnl": -12.0, "max_loss": 40}]}
        plan = dict(self.plan(), first_expiry="2026-10-16")
        rec = T.judge(plan, result, at=0)
        self.assertEqual((rec["status"], rec["twin"]["exit"], rec["exit_agrees"], rec["gap_r"]),
                         ("priced", "window_end", False, 0.05))


# ================================================================================================== the round
@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class TheRound(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        market(self.root / "store")
        self.book = Book(self.root)
        self.addCleanup(self.book.close)
        trades(self.book)
        self.now = ny(D3, 3)
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.settings = {"forward": {"every_seconds": 3600, "twins": {"max_jobs": 12, "attempts": 3}}}
        self.pool = BatchPool(self.root / "store")

    def twins(self, gate=None, settings=None):
        return T.Twins(self.store, self.pool, settings or self.settings, root=self.root, gate=gate or Gate(),
                       clock=lambda: self.now, since=ny(dt.date(2026, 9, 26), 2))

    def test_one_gate_job_a_close_whose_exit_day_the_image_holds_never_a_run_or_a_trial(self):
        tw = self.twins()
        self.assertTrue(tw.due())
        out = tw.run()
        self.assertEqual(sorted(j.family for j in self.pool.jobs),
                         ["twin.41", "twin.42", "twin.43", "twin.44", "twin.45", "twin.46"])
        self.assertTrue(all((j.window, j.gate, j.priority) == ("forward", T.GATE_REASON, 4.0) for j in self.pool.jobs))
        recs = T.records(self.store)
        self.assertEqual({k: v["status"] for k, v in recs.items()},
                         {"41": "priced", "42": "priced", "43": "no_fill", "44": "no_contract", "45": "priced",
                          "46": "no_contract", "47": "unpriceable"})
        self.assertNotIn("48", recs, "a House route's close is never twinned")
        self.assertNotIn("49", recs, "its exit day (Oct 14) is not on the image yet (ready Oct 13)")
        self.assertEqual(out["judged"], {"priced": 3, "no_fill": 1, "no_contract": 2, "unpriceable": 1})
        self.assertEqual(self.store._one("SELECT COUNT(*) AS n FROM runs")["n"], 0, "a twin is not a research run")
        self.assertEqual([e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.twin"], ["round"])
        # Due again only after `every_seconds` or a new ready day; nothing final is asked again.
        self.assertFalse(tw.due())
        self.now += 3600
        self.assertTrue(tw.due())
        self.pool.jobs.clear()
        tw.run()
        self.assertEqual(self.pool.jobs, [])
        later = self.twins(gate=Gate(D4))
        self.assertTrue(later.due(), "a new ready day")

    def test_a_failed_job_is_asked_again_at_most_attempts_times(self):
        self.pool.fail = {"twin.42"}
        tw = self.twins()
        for n in (1, 2, 3):
            self.now += 3600
            tw.run()
            rec = T.records(self.store)["42"]
            self.assertEqual((rec["status"], rec["attempts"]), ("failed", n))
        self.now += 3600
        self.pool.jobs.clear()
        tw.run()
        self.assertNotIn("twin.42", [j.family for j in self.pool.jobs], "three failures on one image: not asked again")
        self.assertEqual(T.records(self.store)["41"]["status"], "priced", "the others were judged the first time")
        self.pool.fail = set()
        tw = self.twins(gate=Gate(D4))
        tw.run()
        self.assertEqual([j.family for j in self.pool.jobs], ["twin.42", "twin.49"], "a new image: asked again; 49's exit day")
        recs = T.records(self.store)
        self.assertEqual(recs["42"]["status"], "priced")
        # The ready day says Oct 14, but this image's SPY files stop at Oct 13: no verdict on 49, asked again later.
        self.assertEqual((recs["49"]["status"], recs["49"]["attempts"], recs["49"]["ready_day"]), ("failed", 1, "2026-10-14"))

    def test_at_most_max_jobs_a_pass(self):
        tw = self.twins(settings={"forward": {"every_seconds": 3600, "twins": {"max_jobs": 2}}})
        out = tw.run()
        self.assertEqual((out["jobs"], out["waiting"]), (2, 4))

    def test_switched_off_it_reads_nothing_and_runs_nothing(self):
        for off in (None, False):
            tw = self.twins(settings={"forward": {"twins": off}})
            self.assertFalse(tw.due())
            self.assertEqual(tw.run()["off"], True)
        self.assertEqual(self.pool.jobs, [])
        self.assertFalse(self.twins(gate=Gate(None)).due(), "no ready forward day on the gate image")

    def test_an_unreadable_book_judges_nothing_and_says_so(self):
        (self.root / "live.sqlite").rename(self.root / "elsewhere.sqlite")
        out = self.twins().run()
        self.assertIn("cannot be read", out["error"])
        self.assertEqual(T.records(self.store), {})


class TheSwitch(unittest.TestCase):
    def test_on_by_default_with_its_bounds_and_off_by_null_or_false(self):
        from league.swarm import settings as S

        self.assertEqual(S.DEFAULTS["forward"]["twins"], {"max_jobs": 12, "attempts": 3})
        self.assertEqual(T.cfg({}), {"max_jobs": 12, "attempts": 3})
        self.assertEqual(T.cfg({"forward": {"twins": {"max_jobs": 4, "attempts": 0}}}), {"max_jobs": 4, "attempts": 3})
        self.assertIsNone(T.cfg({"forward": {"twins": None}}))
        self.assertIsNone(T.cfg({"forward": {"twins": False}}))

    def test_no_live_gym_or_constitution_file_names_the_twins(self):
        # Rule F0: the execution fingerprint (every league/gym and league/live file) and the money digest stay put.
        paths = [p for tree in ("league/live", "league/gym") for p in (REPO / tree).rglob("*.py")]
        paths.append(REPO / "league" / "constitution.py")
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for needle in ("close_twins", "ops.twins", "ops import twins", "per-close fill replay"):
                self.assertNotIn(needle, text, f"{path.relative_to(REPO)} names the twins")

    def test_the_twins_are_behind_the_updaters_wall_as_the_report_that_reads_them(self):
        # The Done meter's input: only the owner's deploy changes how a twin is made or judged (`ci.FORBIDDEN`).
        from league import ci

        for path in ("league/ops/twins.py", "league/ops/dlane_report.py"):
            self.assertEqual(ci.guard([path], None), [f"{path}: no role may change this file"])


# ================================================================================================== the loop
try:
    from league.tests.test_swarm_loop import LoopCase
except Exception:  # pragma: no cover - the loop's fixture needs the swarm's fakes
    LoopCase = None


if LoopCase is not None:
    class TheLoop(LoopCase):
        def test_the_twins_are_their_own_round_after_the_forward_and_never_under_the_brake(self):
            sw = self.swarm()
            ran = threading.Event()
            with patch.object(sw.twins, "due", return_value=True), \
                    patch.object(sw.twins, "run", side_effect=lambda: ran.set() or {"jobs": 0}):
                self.guard.braked = True
                sw.step()
                self.assertNotIn("twins", sw.rounds)
                self.guard.braked = False
                sw.step()
                self.join_rounds()
            self.assertIn("twins", sw.rounds)
            self.assertTrue(ran.is_set())
            self.assertIs(sw.twins.gate, sw.gate)


# ================================================================================================== the report
from league.tests.test_dlane_report import Fixture  # noqa: E402


class TheReport(Fixture):
    def twin(self, pid, status, *, pnl=None, max_loss=50.0, live_exit="program_close", twin_exit="program_close"):
        recs = T.records(self.store)
        recs[str(pid)] = {"pid": pid, "status": status, "why": None if status == "priced" else "a reason",
                          "twin": None if pnl is None else {"pnl": pnl, "max_loss": max_loss, "r": round(pnl / max_loss, 5),
                                                            "exit": twin_exit},
                          "live": {"exit": live_exit}, "exit_agrees": live_exit == twin_exit}
        self.store.put(T.TWINS_KEY, recs)

    def test_a_close_with_a_priced_twin_is_matched_to_it_and_the_rest_fall_back_or_are_counted(self):
        from league.ops import dlane_report as R

        self.fam("dir-a", lane="direction")
        days = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
        pids = [self.close("dir-a", pnl=5.0, max_loss=50.0, day=d) for d in days]
        # Five twins priced (each 0.05 a dollar of maximum loss below live), one the model would not fill, one with no
        # record: that one alone meets the nightly replay of its day.
        for pid in pids[:5]:
            self.twin(pid, "priced", pnl=2.5)
        self.twin(pids[5], "no_fill")
        self.store.add_forward("dir-a", "nightly", [{"id": f"n{i}", "day": d, "pnl": 5.0, "max_loss": 50.0}
                                                    for i, d in enumerate(days)], version=1)
        row = {p["family"]: p for p in self.report()["done"]["screen"]["running"]["by_program"]}["dir-a"]["replay"]
        # Matched: 6 closes (5 against their twins, 1 against the nightly replay), each +5 on 50 live; replay 5 x 2.5 + 5.
        self.assertEqual({k: row[k] for k in ("matched", "twinned", "nightly_matched", "twin_unpriced", "consistent")},
                         {"matched": 6, "twinned": 5, "nightly_matched": 1, "twin_unpriced": {"no_fill": 1},
                          "consistent": True})
        self.assertAlmostEqual(row["gap"], 30.0 / 300.0 - 17.5 / 300.0, places=4)
        block = self.report()["replay_twins"]
        self.assertEqual((block["closes"], block["priced"], block["by_status"]),
                         (7, 5, {"no_fill": 1, "none": 1, "priced": 5}))
        first = block["rows"][0]
        self.assertEqual((first["pid"], first["status"], first["live_r"], first["twin_r"], first["gap_r"]),
                         (pids[0], "priced", 0.1, 0.05, 0.05))
        self.assertEqual(R.twin_records(self.store)[str(pids[0])]["status"], "priced")

    def test_with_no_twin_record_the_figures_are_d5s_key_for_key(self):
        self.fam("dir-a", lane="direction")
        for d in ("2026-10-01", "2026-10-02"):
            self.close("dir-a", pnl=5.0, max_loss=50.0, day=d)
        self.store.add_forward("dir-a", "nightly", [{"id": "n0", "day": "2026-10-01", "pnl": 5.0, "max_loss": 50.0}], version=1)
        out = self.report()
        row = out["done"]["screen"]["running"]["by_program"][0]["replay"]
        self.assertEqual(row, {"matched": 1, "gap": 0.0, "consistent": None})
        self.assertEqual(out["replay_twins"]["by_status"], {"none": 2})

    # A1.4 and the twins (the integration of the weekend fixes, Oct 10, 2026): with the twins on, a close's replay has
    # landed when its own twin is final, never before; the nightly's landing is read only with the switch off.
    def test_finality_reads_a_final_twin_as_the_landed_replay(self):
        from league.ops import dlane_report as R

        row = {"pid": 7, "family": "f", "day": "2026-10-08", "pnl_usd": 1, "fee_basis": "broker"}
        lagging = {"f": {"replayed": True, "day": "2026-10-07"}}
        for status in T.FINAL:
            out = R.finality([row], replay_days=lagging, fees_as_of="2026-10-09", twins={"7": {"status": status}},
                             twins_on=True)
            self.assertEqual((out["final"], out["pending_twin"], out["pending_replay"]), (True, 0, 0), status)
        for twins in ({}, {"7": {"status": "failed"}}):
            out = R.finality([row], replay_days={}, fees_as_of="2026-10-09", twins=twins, twins_on=True)
            self.assertEqual((out["final"], out["pending_twin"]), (False, 1), twins)
            self.assertIn("the per-close twin of 1 closes has not landed", out["why"])
        off = R.finality([row], replay_days=lagging, fees_as_of="2026-10-09", twins={"7": {"status": "failed"}})
        self.assertEqual((off["final"], off["pending_twin"], off["pending_replay"]), (False, 0, 1),
                         "the switch off: the nightly's landing, as before")

    def test_with_the_twins_on_a_reading_is_final_only_once_every_close_has_a_final_twin(self):
        from league.tests.test_dlane_report import NIGHTLY

        self.fam("dir-a", lane="direction")
        self.fam("dir-b", lane="direction")
        pids = []
        for _ in range(15):
            pids += [self.close("dir-a", pnl=5.0), self.close("dir-b", pnl=5.0)]
        # dir-a is at Probe and its nightly has replayed only to the 7th; every close exits on the 8th.
        self.store.set_band("dir-a", "probe", reason="fixture")
        self.store.set_state("dir-a", forward_replay={"target": {"day": "2026-10-07"}, "version": 1})
        self.steady()
        self.posted()
        cp = self.report()["done"]["screen"]["latest"]
        self.assertFalse(cp["final"], "the twins are on by default: no twin yet, no final reading")
        self.assertIn("the per-close twin of 30 closes has not landed", cp["final_why"])
        off = self.report(settings=NIGHTLY)["done"]["screen"]["latest"]
        self.assertFalse(off["final"], "the switch off: dir-a's nightly has not replayed the exit day")
        self.assertIn("the nightly replay has not yet replayed the exit day of 15 closes", off["final_why"])
        self.assertNotIn("per-close twin", off["final_why"])
        for pid in pids[:-1]:
            self.twin(pid, "priced", pnl=5.0)
        self.twin(pids[-1], "failed")
        cp = self.report()["done"]["screen"]["latest"]
        self.assertFalse(cp["final"])
        self.assertIn("the per-close twin of 1 closes has not landed", cp["final_why"])
        self.twin(pids[-1], "no_fill")
        out = self.report()
        cp = out["done"]["screen"]["latest"]
        self.assertEqual((cp["holds"], cp["final"], out["done"]["screen"]["holds"]), (True, True, True),
                         "every twin final: dir-a's lagging nightly no longer holds the reading back")
        self.assertEqual(cp["replay_coverage"]["matched"], 29, "29 priced twins; the no_fill is counted, never matched")
        self.assertTrue(self.report(settings=NIGHTLY)["done"]["screen"]["latest"]["final"],
                        "a final twin is its close's landed replay whatever the switch says now")


if __name__ == "__main__":
    unittest.main()
