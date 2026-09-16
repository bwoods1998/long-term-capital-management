import copy
import datetime as dt
import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument, Quote
from ltcm.tools import ToolError  # leap: lab
from ltcm.manifest import DeskManifest
from ltcm.publish import jsonable
from ltcm.service import DeskContext, Service, load_env
from ltcm.tests.test_gateway import FakeBroker
from ltcm.tests.test_manifest import SAMPLE

UTC = dt.timezone.utc
AAPL = Instrument("equity", "AAPL", "alpaca")
DESK = "earnings-01"


def moment_iso(year, month, day, hour, minute=0):
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00.000Z"


def moment(year, month, day, hour, minute=0):
    """A UTC instant as a POSIX timestamp, for the injected clock."""
    return dt.datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp()


class FakeClock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def set(self, value):
        self.now = value


class FakeMarketData:
    source = "fake"

    def __init__(self, price="100", open_days=True):
        self.price = Decimal(price)
        self.open_days = open_days

    def quote(self, instrument):
        return Quote(
            instrument, self.price - 1, self.price + 1, self.price,
            "2026-09-14T14:00:00.000Z", "fake", False,
        )

    def bars(self, instrument, interval="1d", limit=30):
        return []

    def session(self, day):
        weekday = dt.date.fromisoformat(str(day)[:10]).weekday()
        if weekday >= 5 or not self.open_days:
            return None
        return SimpleNamespace(
            date=str(day)[:10],
            open_at=f"{str(day)[:10]}T13:30:00Z",
            close_at=f"{str(day)[:10]}T20:00:00Z",
            early_close=False,
            to_dict=lambda: {"date": str(day)[:10]},
        )

    def adv_usd(self, instrument):
        return Decimal("50000000")


class FakeDesk:
    """Stands in for `desk.Desk`: emits the session events the schedule reads back."""

    def __init__(self, manifest, ctx, service):
        self.manifest = manifest
        self.ctx = ctx
        self.service = service

    def run_session(self, trigger):
        at = self.service.now()
        session_id = f"{self.manifest.id}:{at[:16]}:{trigger}"
        self.service.log.append(
            self.manifest.stream,
            "desk.session_started",
            {"session_id": session_id, "trigger": trigger},
            id=f"ss:{session_id}",
            at=at,
        )
        self.service.log.append(
            self.manifest.stream,
            "desk.session_ended",
            {"session_id": session_id, "requests": 1, "cost_usd": "0.01", "reason": "done"},
            id=f"se:{session_id}",
            at=at,
        )
        return SimpleNamespace(
            session_id=session_id, turns=1, requests=1, cost_usd=Decimal("0.01"),
            intents=[], reason="done",
        )


class FakeProvider:
    def __init__(self):
        self.floor_cap = Decimal("15")
        self.calls = []
        self.reply = "memo body"  # leap: lab -- a case may script the model's answer

    def respond(self, profile, items, **kwargs):
        self.calls.append(kwargs.get("request_key"))
        return SimpleNamespace(output_text=self.reply, cost_usd=Decimal("0.01"))

    def spent_today(self, desk_id=None):
        return Decimal("0.03")


class FakeMemory:
    """Stands in for `desk.MemoryStore`: records writes and answers reads, scoped by desk."""

    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(dict(entry))
        return {"written": True}

    def read(self, query, limit, *, desk_id=None):
        rows = [e for e in self.entries if desk_id is None or e.get("desk_id") == desk_id]
        return rows[-limit:] if limit else rows


class FakePublisher:
    def __init__(self):
        self.pushes = []
        self.checkpoints = []

    def push_events(self, released_ids=()):
        self.pushes.append(list(released_ids))
        return {"sent": 0, "batches": 0, "last_seq": 0, "held": 0, "skipped": 0}

    def push_checkpoint(self, body):
        self.checkpoints.append(body)
        return {}

    def state(self):
        return {"last_seq": 0, "held": []}


class ServiceCase(unittest.TestCase):
    #: Monday 2026-09-14, 09:50 in New York.
    START = moment(2026, 9, 14, 13, 50)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "playbooks").mkdir()
        self.desks_dir = self.root / "desks"
        self.desks_dir.mkdir()
        self.write_manifest(DESK)
        self.clock = FakeClock(self.START)
        self.brokers = {}
        self.venues = {}
        self.publisher = FakePublisher()
        self.provider = FakeProvider()
        self.memory = FakeMemory()
        self.service = self.build()

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def write_manifest(self, desk_id, **overrides):
        data = copy.deepcopy(SAMPLE)
        data["id"] = desk_id
        data["playbook"] = f"playbooks/{desk_id}.md"
        data["cadence"] = {
            "sessions": ["09:45", "15:30"],
            "timezone": "America/New_York",
            "weekdays_only": True,
        }
        data.update(overrides)
        DeskManifest.from_dict(data)
        (self.desks_dir / f"{desk_id}.json").write_text(json.dumps(data, indent=2))
        (self.root / "playbooks" / f"{desk_id}.md").write_text(f"# {desk_id}\n\nDrift.\n")
        return data

    def broker_factory(self, venue, *, manifest=None, path=None, settings=None, service=None):
        if manifest is None:  # a live venue adapter, which a test supplies only when it needs one
            return self.venues.get(venue)
        broker = self.brokers.get(manifest.id)
        if broker is None:
            broker = self.brokers[manifest.id] = FakeBroker()
        return broker

    def build(self, **config):
        base = {
            "desks_dir": str(self.desks_dir),
            "playbooks_dir": str(self.root / "playbooks"),
            "mark_interval_seconds": 300,
            "sleep_seconds": 0,
            "publish": True,
            # Pinned here so the assertions below test the code, not the deployment's tuning
            # in `ltcm/config.json`.
            "floor_cap_usd_per_day": "15",
            "floor_cap_max_usd_per_day": "60",
            # The capped policy, so the cap assertions test the arithmetic; the runway policy
            # has its own case below with a provider that reports a balance.
            "spend_mode": "capped",
            # No seeding unless a case asks for it: the packaged config breeds families.
            "evolution": {"target_variants": 1},
            # No sandboxes unless a case installs a fake: the packaged config names a lab image.
            "sandbox": {"enabled": False},
            # The ratio allocation rule, so the capital assertions test arithmetic, not a draw;
            # the bandit has its own case in test_committee.
            "committee": {"bandit_enabled": False},
            "sources": {"news": False, "edgar": False, "event": False, "chain": False, "weather": False},
        }
        base.update(config)
        return Service(
            self.root,
            base,
            clock=self.clock,
            sleeper=lambda seconds: None,
            market_data=FakeMarketData(),
            provider=self.provider,
            memory=self.memory,
            publisher=self.publisher,
            broker_factory=self.broker_factory,
            desk_factory=lambda manifest, ctx, service: FakeDesk(manifest, ctx, service),
        )

    def tick(self, at=None):
        if at is not None:
            self.clock.set(at)
        result = self.service.tick()
        for thread in list(self.service._sessions):
            thread.join(timeout=5)
        return result

    def fund(self, at=None):
        """Give the desks their capital, the way the committee does on its cadence."""
        return self.service.committee.allocate(at or self.service.now())

    def sessions_started(self, desk=DESK):
        return [
            event.payload["trigger"]
            for event in self.service.log.read(stream=f"desk:{desk}", kind="desk.session_started")
        ]


class CadenceTests(ServiceCase):
    def test_a_slot_runs_once_per_day_in_the_desk_timezone(self):
        self.tick()  # 09:50 New York, five minutes after the 09:45 slot
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        self.tick(moment(2026, 9, 14, 14, 10))  # still the same slot
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        self.tick(moment(2026, 9, 14, 19, 35))  # 15:35 New York
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:15:30"])

    def test_the_next_day_runs_the_slot_again(self):
        self.tick()
        self.tick(moment(2026, 9, 15, 13, 50))
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:09:45"])

    def test_a_weekend_is_skipped_for_a_weekdays_only_desk(self):
        self.tick(moment(2026, 9, 12, 13, 50))  # Saturday
        self.tick(moment(2026, 9, 13, 13, 50))  # Sunday
        self.assertEqual(self.sessions_started(), [])
        self.tick(moment(2026, 9, 14, 13, 50))  # Monday
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])

    def test_a_long_past_slot_is_not_run_retroactively(self):
        # The box comes back at 14:00 New York; the 09:45 slot is four hours stale.
        self.tick(moment(2026, 9, 14, 18, 0))
        self.assertEqual(self.sessions_started(), [])

    def started_without_end(self, at, trigger="cadence:09:45", desk=DESK, suffix=""):
        """What a restart leaves behind: a session that opened and never wrote its end."""
        from datetime import datetime, timezone

        if not isinstance(at, str):
            at = datetime.fromtimestamp(at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        session_id = f"{desk}:{at[:16]}:{trigger}{suffix}"
        self.service.log.append(
            f"desk:{desk}",
            "desk.session_started",
            {"session_id": session_id, "trigger": trigger},
            id=f"ss:{session_id}",
            at=at,
        )
        return session_id

    def test_a_session_cut_short_by_a_restart_is_sat_down_again_once(self):
        self.started_without_end(moment(2026, 9, 14, 13, 50))
        self.tick(moment(2026, 9, 14, 14, 20))  # the box is back; the start is 30 minutes old
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:09:45"])
        self.tick(moment(2026, 9, 14, 14, 25))  # the retry ended normally: that slot is done
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:09:45"])

    def test_the_retry_is_measured_from_the_interrupted_start_not_the_slot(self):
        # The slot was sat down 55 minutes late (still inside its window) and then killed.
        # At 11:00 New York the slot itself is 75 minutes stale, but the start is 20 minutes old.
        self.started_without_end(moment(2026, 9, 14, 14, 40))
        self.tick(moment(2026, 9, 14, 15, 0))
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:09:45"])

    def test_an_interruption_older_than_the_catch_up_window_is_left_alone(self):
        self.started_without_end(moment(2026, 9, 14, 13, 50))
        self.tick(moment(2026, 9, 14, 15, 0))  # 70 minutes after the start: the afternoon is not replayed
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])

    def test_a_session_that_died_twice_is_a_bug_not_a_loop(self):
        self.started_without_end(moment(2026, 9, 14, 13, 50))
        self.started_without_end(moment(2026, 9, 14, 13, 55), suffix=":2")
        self.tick(moment(2026, 9, 14, 14, 0))
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "cadence:09:45"])

    def test_a_session_still_running_here_is_not_mistaken_for_an_interrupted_one(self):
        import threading

        release = threading.Event()
        worker = threading.Thread(target=release.wait, name=f"session-{DESK}-cadence:09:45", daemon=True)
        worker.start()
        self.addCleanup(release.set)
        self.service._sessions.append(worker)
        self.started_without_end(moment(2026, 9, 14, 13, 50))
        self.tick(moment(2026, 9, 14, 14, 20))
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])

    def test_the_next_session_is_the_next_unrun_slot_in_the_desks_own_time(self):
        manifest = self.service.manifests[DESK]
        # Monday 09:50 New York: the 09:45 slot is five minutes old and has not run: due now.
        self.assertEqual(self.service.next_session_at(manifest, moment_iso(2026, 9, 14, 13, 50)), moment_iso(2026, 9, 14, 13, 50))
        self.tick()  # runs 09:45
        self.assertEqual(self.service.next_session_at(manifest, self.service.now()), "2026-09-14T19:30:00.000Z")  # 15:30 New York
        # Friday evening for a weekdays-only desk: Monday morning.
        self.assertEqual(self.service.next_session_at(manifest, moment_iso(2026, 9, 18, 23, 0)), "2026-09-21T13:45:00.000Z")
        # A slot long past that never ran is not resurrected.
        self.assertEqual(self.service.next_session_at(manifest, moment_iso(2026, 9, 14, 18, 0)), "2026-09-14T19:30:00.000Z")

    def test_the_postmortem_runs_after_the_close_and_only_after_real_work(self):
        # A desk that never sat down has nothing to review: no post-mortem on an empty day.
        self.tick(moment(2026, 9, 15, 1, 40))  # 21:40 New York on the 14th
        self.assertEqual(self.sessions_started(), [])
        # After a trading session the evening review is due, once.
        self.tick(moment(2026, 9, 15, 13, 50))  # 09:50 New York on the 15th: the 09:45 slot
        self.tick(moment(2026, 9, 16, 1, 40))  # 21:40 New York on the 15th
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])
        self.tick(moment(2026, 9, 16, 1, 50))
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])
        # The next evening, with no session in between, there is again nothing to review.
        self.tick(moment(2026, 9, 17, 1, 40))

    def test_the_postmortem_runs_after_the_close_when_there_is_a_session_to_review(self):
        self.tick()  # 09:50 New York: the morning session
        self.tick(moment(2026, 9, 15, 1, 40))  # 21:40 New York on the 14th
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])
        self.tick(moment(2026, 9, 15, 1, 50))
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])

    def test_a_desk_that_did_nothing_gets_no_postmortem(self):
        # Bred at lunchtime, never sat down: a review of nothing wrote invented rules tonight.
        self.tick(moment(2026, 9, 15, 1, 40))
        self.assertEqual(self.sessions_started(), [])
        # After a review, the next review needs a new session too.
        self.tick(moment(2026, 9, 15, 13, 50))  # the 15th: a morning session
        self.tick(moment(2026, 9, 16, 1, 40))   # the 15th's review
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])
        self.tick(moment(2026, 9, 17, 1, 40))   # the 16th's evening with no session that day
        self.assertEqual(self.sessions_started(), ["cadence:09:45", "postmortem"])

    def test_triggers_match_the_desk_runtime_grammar(self):
        import re

        grammar = re.compile(r"^[a-z][a-z0-9_:.\-]{0,48}$")
        due = self.service.due_sessions(self.service.now())
        self.assertTrue(due)
        for _, trigger in due:
            self.assertRegex(trigger, grammar)

    def test_sessions_run_on_their_own_threads(self):
        due = self.service.due_sessions(self.service.now())
        threads = self.service.start_sessions(due)
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0].name, "MainThread")
        threads[0].join(timeout=5)
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])


class KillSwitchTests(ServiceCase):
    def test_the_kill_switch_stops_sessions_but_not_the_books(self):
        self.fund()
        self.service.kill("testing the switch")
        result = self.tick()
        self.assertTrue(result["kill_switch"])
        self.assertEqual(result["sessions"], [])
        self.assertEqual(self.sessions_started(), [])
        self.assertEqual(result["marked"], 1)  # the floor still values itself
        self.assertEqual(self.service.status()["status"], "halted")
        self.assertEqual(self.service.desk_status(DESK), "halted")

    def test_unkill_lets_the_desks_run_again(self):
        self.service.kill()
        self.tick()
        self.assertTrue(self.service.unkill())
        self.tick(moment(2026, 9, 14, 14, 0))
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        self.assertFalse(self.service.unkill())


class MarkTests(ServiceCase):
    def test_a_new_desk_is_funded_before_its_first_session_and_mark(self):
        # The first tick allocates capital ahead of sessions, so a desk never sees an unfunded book.
        self.tick()
        allocations = self.service.log.read(kind="committee.allocation")
        self.assertEqual(len(allocations), 1)
        self.assertIn(DESK, allocations[0].payload["allocations"])
        self.assertEqual(len(self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")), 1)
        self.assertGreater(self.service.ledgers[DESK].state().equity, 0)
        self.assertEqual(self.service.log.read(kind="risk.breaker"), [])

    def test_marks_run_on_the_interval(self):
        self.fund()
        self.tick()
        marks = self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")
        self.assertEqual(len(marks), 1)
        self.tick(self.START + 60)  # under the 300s interval
        self.assertEqual(len(self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")), 1)
        self.tick(self.START + 400)
        self.assertEqual(len(self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")), 2)

    def test_a_mark_carries_the_shape_the_site_needs(self):
        self.fund()
        broker = self.brokers[DESK]
        from ltcm.broker import OrderIntent

        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity="2",
            rationale="a documented beat", created_at=self.service.now(), session_id="s",
        )
        result = self.service.gateway.propose(intent, self.service.now())
        self.assertTrue(result["approved"], result["reasons"])
        self.tick()
        mark = self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark")[-1]
        self.assertIn("equity", mark.payload)
        row = mark.payload["positions"][0]
        for key in ("instrument", "quantity", "price", "market_value"):
            self.assertIn(key, row)
        self.assertEqual(broker.submitted, [intent.id])


class BudgetTests(ServiceCase):
    def test_the_daily_cap_is_published_and_pushed_to_the_provider(self):
        result = self.tick()
        self.assertEqual(result["budget"]["cap_usd"], "15.00")
        self.assertEqual(self.provider.floor_cap, Decimal("15.00"))
        event = self.service.log.last("ops", "ops.budget")
        self.assertEqual(event.payload["scope"], "floor")
        self.assertEqual(event.payload["cap_usd"], "15.00")
        self.assertEqual(event.payload["base_usd"], "15")
        self.assertEqual(event.payload["profit_share"], "0.25")
        self.assertEqual(event.payload["spent_usd"], "0.03")

    def test_realized_profit_raises_the_cap(self):
        log = self.service.log
        log.append(
            "committee", "committee.allocation",
            {"allocations": {DESK: "2000"}, "reasons": {}}, at="2026-09-10T13:00:00.000Z",
        )
        for n, (side, price) in enumerate((("buy", "100"), ("sell", "120"))):
            log.append(
                "broker:shadow", "broker.fill",
                {"fill_id": f"f{n}", "order_id": "o1", "desk_id": DESK,
                 "instrument": AAPL.to_dict(), "side": side, "quantity": "10",
                 "price": price, "fee": "0", "at": f"2026-09-1{1 + n}T14:00:00.000Z"},
                at=f"2026-09-1{1 + n}T14:00:00.000Z",
            )
        budget = self.service.apply_budget(self.service.now())
        self.assertEqual(budget["trailing_realized_usd"], Decimal("200.00"))
        self.assertEqual(budget["cap_usd"], Decimal("65.00").min(Decimal("60")))
        self.assertEqual(self.provider.floor_cap, Decimal("60"))


class RunwayProvider(FakeProvider):
    """A provider that reports a Sail balance and a trailing burn, the way the real one does."""

    def __init__(self, balance="279.82", burn="0.40"):
        super().__init__()
        self.balance = None if balance is None else Decimal(balance)
        self.burn = Decimal(burn)
        self.desk_fuse = None

    def check_balance(self):
        return self.balance

    def spent_since(self, hours=24.0):
        return self.burn

    sail_burn = None
    sail_period = None

    def sail_burn_usd_per_day(self):
        return self.sail_burn

    def sail_spend_period_usd(self):
        return self.sail_period


class RunwayPolicyTests(ServiceCase):
    """No daily cap: the credit above the reserve is the limit, and the floor's posture toward
    it is published, throttled and stopped in public."""

    def setUp(self):
        super().setUp()
        self.provider = RunwayProvider()
        self.service.close()
        self.service = self.build(spend_mode="runway")

    def test_open_credit_means_no_cap_and_a_published_runway(self):
        result = self.tick()
        self.assertEqual(result["spend_mode"], "open")
        self.assertEqual(self.provider.floor_cap, Decimal("269.82"))  # everything above the reserve
        self.assertEqual(self.provider.desk_fuse, Decimal("67.45"))
        event = self.service.log.last("ops", "ops.budget")
        self.assertEqual(event.payload["mode"], "open")
        self.assertEqual(event.payload["balance_usd"], "279")  # the tape speaks in dollars
        self.assertEqual(event.payload["runway_days"], "385")
        self.assertEqual(event.payload["spent_usd"], "0")  # dollars: the checkpoint carries the cents
        checkpoint = self.publisher.checkpoints[-1]
        self.assertEqual(checkpoint["budget"]["mode"], "open")
        self.assertEqual(str(checkpoint["budget"]["balance_usd"]), "279.82")  # exact, here
        self.assertEqual(str(checkpoint["budget"]["cap_usd"]), "269.82")
        # A steady picture is one public event, not one per tick, and a balance that moves by
        # cents between ticks is the same picture: the tick must never fail on its own event.
        self.provider.balance = Decimal("279.61")
        self.tick(moment(2026, 9, 14, 13, 51))
        self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual(len(self.service.log.read(kind="ops.budget")), 1)
        self.assertEqual([e for e in self.service.log.read(kind="ops.alert") if "tick failed" in e.payload["text"]], [])
        # A dollar of balance, or a dollar of spend, is a new picture; a cent of spend is not.
        self.provider.balance = Decimal("270.10")
        self.tick(moment(2026, 9, 14, 13, 53))
        self.assertEqual(len(self.service.log.read(kind="ops.budget")), 2)

    def test_at_the_reserve_the_floor_stops_says_so_once_and_resumes_when_credit_arrives(self):
        self.provider.balance = Decimal("9.50")
        result = self.tick()
        self.assertEqual(result["spend_mode"], "stopped")
        self.assertEqual(result["sessions"], [])
        self.assertEqual(self.sessions_started(), [])
        self.assertEqual(self.provider.floor_cap, Decimal("0"))
        alerts = [e.payload for e in self.service.log.read(kind="ops.alert")]
        paused = [a for a in alerts if a["text"].startswith("floor paused")]
        self.assertEqual(len(paused), 1)
        self.assertEqual(paused[0]["level"], "critical")
        self.tick(moment(2026, 9, 14, 13, 51))
        self.assertEqual(len([e for e in self.service.log.read(kind="ops.alert") if e.payload["text"].startswith("floor paused")]), 1)
        # Marks and publication went on regardless.
        self.assertTrue(self.publisher.checkpoints)
        self.assertEqual(self.publisher.checkpoints[-1]["budget"]["mode"], "stopped")

        self.provider.balance = Decimal("120")  # the owner topped up
        result = self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual(result["spend_mode"], "open")
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        opened = [e for e in self.service.log.read(kind="ops.alert") if e.payload["text"].startswith("floor open")]
        self.assertEqual(len(opened), 1)

    def test_a_short_runway_keeps_the_live_desks_and_pauses_the_shadow_race(self):
        self.write_manifest(DESK, capital={"mode": "live", "usd": "1000"})
        self.write_manifest("earnings-02", capital={"mode": "shadow", "usd": "1000"})
        self.service.close()
        self.service = self.build(spend_mode="runway", live_venues=["alpaca"])
        self.provider.balance = Decimal("20")
        self.provider.burn = Decimal("5")
        result = self.tick()
        self.assertEqual(result["spend_mode"], "throttled")
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        self.assertEqual(self.sessions_started("earnings-02"), [])
        self.assertEqual(self.provider.floor_cap, Decimal("2.00"))
        throttled = [e for e in self.service.log.read(kind="ops.alert") if e.payload["text"].startswith("floor throttled")]
        self.assertEqual(len(throttled), 1)

    def test_sails_own_burn_wins_when_it_is_larger_than_the_ledgers(self):
        self.provider.sail_burn = Decimal("4.73")  # the box, sandboxes and image builds too
        self.tick()
        event = self.service.log.last("ops", "ops.budget")
        # $269.82 above the reserve at $4.73 plus the policy's $0.30 box line a day is 53 days,
        # not the ledger's 385.
        self.assertEqual(event.payload["runway_days"], "53")

    def test_infrastructure_spend_is_sails_day_less_the_ledgers_day_summed_from_the_floors_own_days(self):
        self.provider.sail_period = Decimal("4.73")  # Sail's last 24 hours, everything included
        self.provider.burn = Decimal("0.40")           # the ledger's last 24 hours of model cost
        self.tick()
        run = self.publisher.checkpoints[-1]["run"]
        self.assertEqual(str(run["sail_infra_spend_total_usd"]), "4.33")
        # The next day adds its own figure; the earlier day is kept, not recomputed away.
        self.provider.sail_period = Decimal("2.10")
        self.tick(moment(2026, 9, 15, 13, 50))
        run = self.publisher.checkpoints[-1]["run"]
        self.assertEqual(str(run["sail_infra_spend_total_usd"]), "6.03")
        self.assertEqual(sorted(self.service.state()["infra_spend_by_day"]), ["2026-09-14", "2026-09-15"])

    def test_an_unreadable_balance_never_stops_the_floor(self):
        self.provider.balance = None
        result = self.tick()
        self.assertEqual(result["spend_mode"], "unknown")
        self.assertEqual(self.sessions_started(), ["cadence:09:45"])
        self.assertEqual(self.provider.floor_cap, Decimal("40"))


class SeedingTests(ServiceCase):
    """The floor breeds shadow variants of its live desks so the promotion race is always on."""

    def setUp(self):
        super().setUp()
        self.service.close()
        self.service = self.build(evolution={"target_variants": 3}, seed_batch=1)

    def test_families_are_topped_up_a_child_per_pass_and_wired_in_at_once(self):
        result = self.tick()
        self.assertEqual([a["action"] for a in result["evolution"]], ["spawned"])
        self.assertIn("earnings-01-2", self.service.manifests)
        self.assertEqual(self.service.manifests["earnings-01-2"].capital_mode, "shadow")
        self.assertIn("earnings-01-2", self.service.shadow_books)
        # Within the interval nothing more is bred; after it the family is completed.
        self.assertEqual(self.tick(moment(2026, 9, 14, 14, 20))["evolution"], [])
        result = self.tick(moment(2026, 9, 14, 15, 0))
        self.assertEqual([a["desk_id"] for a in result["evolution"]], ["earnings-01-3"])
        self.assertEqual(self.tick(moment(2026, 9, 14, 16, 5))["evolution"], [])
        self.assertEqual(len(self.service.log.read(kind="evolution.spawned")), 2)
        # The children are funded before their first session, like any new desk.
        allocations = self.service.log.read(kind="committee.allocation")
        self.assertIn("earnings-01-3", allocations[-1].payload["allocations"])


class ScheduleTests(ServiceCase):
    def test_the_committee_runs_on_sunday_evening(self):
        self.tick()  # Monday: no committee
        self.assertEqual(self.service.log.read(kind="committee.memo"), [])
        self.tick(moment(2026, 9, 13, 22, 5))  # Sunday 18:05 New York
        self.assertEqual(self.service.state()["last_committee_day"], "2026-09-13")
        self.assertEqual(len(self.service.log.read(kind="committee.allocation")), 1)
        self.assertEqual(len(self.service.log.read(kind="committee.memo")), 1)
        self.tick(moment(2026, 9, 13, 22, 30))  # the same evening: once only
        self.assertEqual(len(self.service.log.read(kind="committee.allocation")), 1)

    def test_the_memo_is_written_every_evening_while_capital_moves_weekly(self):
        self.fund()  # the roster's first allocation, so the tick has nothing new to fund
        result = self.tick(moment(2026, 9, 14, 22, 5))  # Monday 18:05 New York
        self.assertTrue(result["memo"])
        self.assertFalse(result["committee"])
        memos = self.service.log.read(kind="committee.memo")
        self.assertEqual([m.payload["period"] for m in memos], ["2026-09-14"])
        self.assertTrue(memos[0].payload["text"].endswith("— Meriwether"))
        self.assertEqual(len(self.service.log.read(kind="committee.allocation")), 1)
        self.assertEqual(self.service.state()["last_committee_day"], "2026-09-14")
        # Twice in one evening is still one memo, and one model call.
        self.tick(moment(2026, 9, 14, 22, 40))
        self.assertEqual(len(self.service.log.read(kind="committee.memo")), 1)
        # The next evening is a new memo, and still no capital moves.
        self.tick(moment(2026, 9, 15, 22, 5))
        self.assertEqual(len(self.service.log.read(kind="committee.memo")), 2)
        self.assertEqual(len(self.service.log.read(kind="committee.allocation")), 1)

    def test_the_daily_memo_can_be_switched_off(self):
        self.service.close()
        self.service = self.build(committee_memo_daily=False)
        self.fund()
        result = self.tick(moment(2026, 9, 14, 22, 5))  # Monday
        self.assertFalse(result["memo"])
        self.assertEqual(self.service.log.read(kind="committee.memo"), [])
        self.assertIsNone(self.service.state().get("last_committee_day"))

    def test_evolution_runs_daily_after_its_slot(self):
        result = self.tick(moment(2026, 9, 14, 23, 5))  # 19:05 New York
        self.assertEqual(self.service.state()["last_evolution_day"], "2026-09-14")
        self.assertEqual(result["evolution"], [])  # one variant, nothing to select

    def test_publishing_happens_every_tick(self):
        self.tick()
        self.assertEqual(len(self.publisher.pushes), 1)
        checkpoint = self.publisher.checkpoints[0]
        self.assertEqual(checkpoint["schema_version"], 1)
        self.assertEqual([d["id"] for d in checkpoint["desks"]], [DESK])
        self.assertEqual(checkpoint["budget"]["cap_usd"], Decimal("15.00"))
        self.assertEqual(sorted(checkpoint["committee"]), ["allocations", "last_memo_at"])
        self.assertLessEqual(checkpoint["desks"][0]["updated_at"], checkpoint["published_at"])


class CriticWiringTests(ServiceCase):
    def test_the_gateway_gets_a_critic_built_from_the_configuration(self):
        critic = self.service.gateway.critic
        self.assertIsNotNone(critic)
        self.assertIs(critic, self.service.critic)
        self.assertIs(critic.provider, self.provider)
        self.assertEqual(critic.profile, "glm_asap")
        self.assertEqual(critic.reasoning_effort, "low")
        self.assertEqual(critic.max_output_tokens, 1024)

    def test_a_configured_profile_reaches_the_critic(self):
        self.service.close()
        self.service = self.build(critic_profile="glm_flash_asap")
        self.assertEqual(self.service.gateway.critic.profile, "glm_flash_asap")

    def test_the_critic_can_be_switched_off(self):
        self.service.close()
        self.service = self.build(critic_enabled=False)
        self.assertIsNone(self.service.critic)
        self.assertIsNone(self.service.gateway.critic)

    def test_a_shadow_desk_order_never_reaches_the_critic(self):
        from ltcm.broker import OrderIntent

        self.fund()
        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity="2",
            rationale="a documented beat", created_at=self.service.now(), session_id="s",
        )
        result = self.service.gateway.propose(intent, self.service.now())
        self.assertTrue(result["approved"], result["reasons"])
        self.assertEqual(self.service.log.read(kind="risk.review"), [])
        self.assertEqual(self.provider.calls, [])


class CheckpointTests(ServiceCase):
    """What the site is told. A shadow book is legible, and never counted as money."""

    def live_desk(self, desk_id="live-01"):
        self.write_manifest(
            desk_id, venues=["kalshi"], capital={"mode": "live", "usd": "500"},
            instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
        )
        self.service.close()
        self.service = self.build()
        return desk_id

    def test_the_floor_block_counts_live_desks_only(self):
        live = self.live_desk()
        self.fund()
        self.tick()
        body = self.service.checkpoint()
        floor = body["floor"]
        self.assertEqual(floor["live_desks"], 1)
        self.assertEqual(floor["shadow_desks"], 1)
        self.assertEqual(floor["equity"], floor["live_equity"])
        self.assertEqual(floor["daily_pnl"], floor["live_daily_pnl"])
        rows = {row["id"]: row for row in body["desks"]}
        self.assertEqual(rows[DESK]["mode"], "shadow")
        self.assertEqual(rows[live]["mode"], "live")
        # The shadow desk carries its notional book; the floor's equity is the live sleeve alone.
        self.assertEqual(rows[DESK]["equity"], Decimal("1000.00"))
        self.assertEqual(floor["live_equity"], rows[live]["equity"])
        self.assertEqual(floor["capital_usd"], Decimal("500.00"))

    def test_a_floor_of_shadow_desks_publishes_no_equity_at_all(self):
        self.fund()
        self.tick()
        floor = self.service.checkpoint()["floor"]
        self.assertEqual(floor["live_desks"], 0)
        self.assertEqual(floor["shadow_desks"], 1)
        self.assertEqual(floor["live_equity"], Decimal("0"))
        self.assertEqual(floor["since_inception_pct"], Decimal("0"))

    def test_the_infra_block_reports_the_box_and_the_spend(self):
        self.fund()
        self.tick()
        infra = self.service.checkpoint()["infra"]
        self.assertEqual(
            sorted(infra),
            ["box_id", "checkpoint_count", "host", "region", "requests_today", "spend_usd",
             "uptime_seconds"],
        )
        self.assertIn(infra["host"], ("local", "sailbox"))
        self.assertEqual(infra["checkpoint_count"], 1)
        self.assertEqual(infra["spend_usd"], Decimal("0.03"))  # the fake provider's spend
        self.assertGreaterEqual(infra["uptime_seconds"], 0)
        # Nothing the site was not promised leaks out of describe_host().
        self.assertNotIn("hostname", infra)
        self.assertNotIn("pid", infra)

    def test_a_missing_hostinfo_module_degrades_to_the_local_box(self):
        import builtins

        real_import = builtins.__import__

        def blocked(name, globals=None, locals=None, fromlist=(), level=0):
            if "hostinfo" in (fromlist or ()) or name.endswith("hostinfo"):
                raise ImportError("no hostinfo on this box")
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked
        try:
            infra = self.service.infra(self.service.now())
        finally:
            builtins.__import__ = real_import
        self.assertEqual(infra["host"], "local")
        self.assertIsNone(infra["box_id"])
        self.assertIsNone(infra["region"])

    def test_a_hostinfo_that_names_a_sailbox_is_published_as_one(self):
        from ltcm import hostinfo

        real = hostinfo.describe_host
        hostinfo.describe_host = lambda *a, **k: {
            "host": "sailbox", "box_id": "sb-77c1", "region": "us-east",
            "uptime_seconds": 4200.5, "hostname": "private-box", "pid": 4,
        }

        try:
            infra = self.service.infra(self.service.now())
        finally:
            hostinfo.describe_host = real
        self.assertEqual(infra["host"], "sailbox")
        self.assertEqual(infra["box_id"], "sb-77c1")
        self.assertEqual(infra["region"], "us-east")
        self.assertEqual(infra["uptime_seconds"], 4200)
        self.assertNotIn("hostname", infra)

    def test_an_environment_variable_cannot_break_publication(self):
        """A box id or region is a guest environment string. The site refuses markup; clean it."""
        from ltcm import hostinfo

        real = hostinfo.describe_host
        hostinfo.describe_host = lambda *a, **k: {
            "host": "sailbox", "box_id": "sb-<script>77c1", "region": "us east\n", "uptime_seconds": 1,
        }
        try:
            infra = self.service.infra(self.service.now())
        finally:
            hostinfo.describe_host = real
        self.assertEqual(infra["box_id"], "sb-script77c1")
        self.assertEqual(infra["region"], "us east")


class ShadowRoutingTests(ServiceCase):
    """A shadow desk runs the whole session and reaches a scoring book, never a venue."""

    def test_a_shadow_desk_gets_its_own_book_under_the_shadow_key(self):
        self.assertEqual(sorted(self.service.shadow_books), [DESK])
        self.assertIn("shadow", self.service.brokers)
        self.assertEqual(self.service.brokers["shadow"].venue, "shadow")
        self.assertEqual(self.service.live_ids(), set())

    def test_a_book_written_under_the_old_name_is_kept(self):
        """The directory was renamed; the desk's positions and cash were not."""
        legacy = self.root / ".data" / "ltcm" / "paper"
        legacy.mkdir(parents=True, exist_ok=True)
        (legacy / f"{DESK}.sqlite").write_bytes(b"")
        self.assertEqual(self.service.book_path(DESK), legacy / f"{DESK}.sqlite")
        current = self.root / ".data" / "ltcm" / "shadow" / f"{DESK}.sqlite"
        current.parent.mkdir(parents=True, exist_ok=True)
        current.write_bytes(b"")
        self.assertEqual(self.service.book_path(DESK), current)

    def test_a_live_desk_has_no_shadow_book(self):
        self.write_manifest(DESK, capital={"mode": "live", "usd": "1000"})
        self.service.close()
        self.service = self.build(live_venues=[])
        self.assertEqual(self.service.shadow_books, {})
        self.assertEqual(self.service.live_ids(), {DESK})
        alerts = [e.payload["text"] for e in self.service.log.read(kind="ops.alert", limit=50)]
        self.assertTrue(any("has no broker" in text for text in alerts), alerts)


class HealthTests(ServiceCase):
    def test_the_health_file_is_written_every_tick(self):
        self.fund()
        self.tick()
        path = self.root / ".data" / "ltcm" / "health.json"
        self.assertEqual(path, self.service.health_path)
        report = json.loads(path.read_text())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "running")
        self.assertEqual([d["id"] for d in report["desks"]], [DESK])
        self.assertEqual(report["budget"]["cap_usd"], "15.00")
        self.assertEqual(report["last_tick"]["marked"], 1)
        self.assertFalse(report["kill_switch"])
        self.assertEqual(oct(path.stat().st_mode)[-3:], "600")

    def test_run_once_ticks_and_stops(self):
        result = self.service.run(once=True)
        self.assertEqual(result["at"][:10], "2026-09-14")
        self.assertTrue((self.root / ".data" / "ltcm" / "health.json").exists())

    def test_status_reports_the_roster_without_writing(self):
        status = self.service.status()
        self.assertEqual(status["desks"][0]["id"], DESK)
        self.assertEqual(status["desks"][0]["mode"], "shadow")
        self.assertEqual(status["floor"]["equity"], "0")
        self.assertFalse((self.root / ".data" / "ltcm" / "health.json").exists())


class ContextTests(ServiceCase):
    def context(self):
        return DeskContext(self.service, self.service.manifests[DESK], session_id="s1")

    def test_quote_positions_and_balance_return_domain_objects(self):
        from ltcm.broker import Balance, Position

        ctx = self.context()
        self.assertIsInstance(ctx.quote(AAPL), Quote)
        self.assertEqual(ctx.positions(), [])
        self.assertIsInstance(ctx.balance(), Balance)
        self.service.committee.allocate(self.service.now())
        self.assertEqual(ctx.balance().cash, Decimal("1000.00"))
        self.assertEqual(ctx.positions(), [])
        self.assertIsInstance(ctx.positions(), list)
        self.assertNotIsInstance(ctx.positions(), dict)
        self.assertTrue(all(isinstance(p, Position) for p in ctx.positions()))

    def test_memo_emits_a_desk_memo_event(self):
        ctx = self.context()
        result = ctx.memo("Monday note", "The beat was cash, not accruals.")
        event = self.service.log.last(f"desk:{DESK}", "desk.memo")
        self.assertEqual(event.id, result["event_id"])
        self.assertEqual(event.payload["title"], "Monday note")
        self.assertEqual(event.payload["session_id"], "s1")

    def test_propose_order_returns_a_decision_and_owns_the_events(self):
        from ltcm.broker import OrderIntent

        self.service.committee.allocate(self.service.now())
        ctx = self.context()
        intent = OrderIntent.new(
            desk_id=DESK, instrument=AAPL, side="buy", quantity="2",
            rationale="a documented beat", created_at=self.service.now(), session_id="s1",
        )
        result = ctx.propose_order(intent)
        self.assertTrue(result["approved"], result["reasons"])
        self.assertIn("decision", result)
        self.assertEqual(result["order"]["status"], "filled")
        self.assertEqual(len(self.service.log.read(kind="desk.intent")), 1)
        self.assertEqual(len(self.service.log.read(kind="risk.decision")), 1)
        self.assertEqual(len(self.service.log.read(kind="broker.order")), 1)

    def test_a_desk_cannot_propose_for_another_desk(self):
        from ltcm.broker import OrderIntent

        intent = OrderIntent.new(
            desk_id="kalshi-01", instrument=AAPL, side="buy", quantity="1",
            rationale="not mine", created_at=self.service.now(),
        )
        with self.assertRaises(ValueError):
            self.context().propose_order(intent)

    def test_memory_and_playbook_round_trip(self):
        ctx = self.context()
        ctx.memory_write({"kind": "note", "text": "AAPL beat on cash"})
        self.assertEqual(ctx.memory_read("AAPL", 5)[0]["text"], "AAPL beat on cash")
        # Another desk's notes are its own: a child must race its parent, not read its mind.
        self.write_manifest("earnings-02")
        self.service.close()
        self.service = self.build()
        other = self.service.context(self.service.manifests["earnings-02"], session_id="s-2")
        self.assertEqual(other.memory_read("", 10), [])
        other.memory_write({"kind": "note", "text": "MSFT guided down"})
        self.assertEqual([e["text"] for e in other.memory_read("", 10)], ["MSFT guided down"])
        mine = self.service.context(self.service.manifests[DESK], session_id="s-3")
        self.assertEqual([e["text"] for e in mine.memory_read("", 10)], ["AAPL beat on cash"])
        ctx = mine
        self.assertIn("Drift", ctx.playbook_read())
        ctx.playbook_write("# new\n\nRules.\n", "learned something")
        self.assertEqual(ctx.playbook_read(), "# new\n\nRules.\n")
        # Versioning belongs to the desk runtime, not to the context.
        self.assertEqual(self.service.log.read(kind="desk.playbook_updated"), [])

    def test_bars_reach_the_desk_without_the_instrument_echoed_on_every_row(self):
        from types import SimpleNamespace

        rows = [SimpleNamespace(to_dict=lambda: {"instrument": {"symbol": "BTC-USD"}, "start": "2026-09-14T00:00:00Z", "close": "76799.85"})]
        self.service.market_data.bars = lambda instrument, interval, limit: rows
        out = self.context().bars(AAPL, "1d", 1)
        self.assertEqual(out, [{"start": "2026-09-14T00:00:00Z", "close": "76799.85"}])

    def test_market_search_matches_tickers_inside_and_titles_as_whole_words(self):
        fed = {"ticker": "KXFEDDECISION-26SEP-H25", "event_ticker": "KXFEDDECISION-26SEP", "series_ticker": "KXFEDDECISION",
               "title": "Will the Federal Reserve hike rates by 25bps at their September 2026 meeting?", "volume_24h": "100"}
        fight = {"ticker": "KXUFC-26SEP20-DEC", "event_ticker": "KXUFC-26SEP20", "series_ticker": "KXUFC",
                 "title": "Will the fight end by decision?", "volume_24h": "9000"}
        self.service.event_index = lambda source: [fight, fed]
        self.service.source = lambda name: object()
        ctx = self.context()
        self.assertEqual([r["ticker"] for r in ctx.event_markets("fed decision")], [fed["ticker"], fight["ticker"]])
        self.assertEqual([r["ticker"] for r in ctx.event_markets("fed")], [fed["ticker"]])
        self.assertEqual([r["ticker"] for r in ctx.event_markets("federal reserve")], [fed["ticker"]])

    def test_calendar_returns_one_row_per_day(self):
        rows = self.context().calendar(3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["date"], "2026-09-14")
        self.assertTrue(rows[0]["open"])

    def test_a_missing_source_says_so_rather_than_inventing(self):
        ctx = self.context()
        with self.assertRaises(RuntimeError):
            ctx.news("AAPL earnings", 5)


class WeatherToolTests(ServiceCase):
    """leap: weather -- the desk context reads the NWS source, or says there is none."""

    def context(self):
        return self.service.context(self.service.manifests[DESK], session_id="s-w")

    def test_the_forecast_comes_from_the_weather_source(self):
        class Source:
            def forecast(self, city):
                return {"city": city, "days": [], "hourly": [], "observation": None}

        self.service._sources["weather"] = Source()
        ctx = self.context()
        self.assertEqual(ctx.weather_forecast("Chicago")["city"], "Chicago")

    def test_without_a_weather_source_the_tool_says_so(self):
        with self.assertRaises(RuntimeError):
            self.context().weather_forecast("Chicago")


class EnvTests(unittest.TestCase):
    def test_env_parsing_handles_comments_quotes_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# a comment\n"
                "CAPITAL_PUBLISH_TOKEN=abc123\n"
                'export ALPACA_PAPER_KEY_ID="PK123"\n'
                "EMPTY=\n"
                "not a pair\n"
                "SPACED = value \n"
            )
            env = load_env(path)
        self.assertEqual(env["CAPITAL_PUBLISH_TOKEN"], "abc123")
        self.assertEqual(env["ALPACA_PAPER_KEY_ID"], "PK123")
        self.assertEqual(env["EMPTY"], "")
        self.assertEqual(env["SPACED"], "value")
        self.assertNotIn("not a pair", env)

    def test_a_missing_env_file_is_not_an_error(self):
        self.assertEqual(load_env("/nonexistent/.env"), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class EventResolutionTests(ServiceCase):
    """A settled market wakes the desk that held it, at most twice an hour."""

    TICKER = "KXCPI-26SEP-T3.0"

    def setUp(self):
        super().setUp()
        self.write_manifest(
            DESK,
            cadence={
                "sessions": ["09:45"],
                "timezone": "America/New_York",
                "weekdays_only": True,
                "triggers": ["event_resolution"],
            },
        )
        self.service.close()
        self.service = self.build()

    def outcome(self, at, ticker=None, desk=DESK):
        return self.service.log.append(
            f"desk:{desk}",
            "desk.outcome",
            {
                "instrument": f"event:CPI:kalshi:yes:{ticker or self.TICKER}",
                "market_id": ticker or self.TICKER,
                "result": "yes",
                "entry_price": "0.40",
                "exit_price": "1",
                "quantity": "10",
                "pnl": "6.00",
                "held_for_hours": "27.0",
                "rationale_excerpt": "base rates said 62%",
            },
            id=f"outcome:{desk}:{ticker or self.TICKER}:{at}",
            at=at,
        )

    def triggers(self, at=None):
        return [t for _, t in self.service.due_sessions(at or self.service.now())]

    def test_a_new_outcome_makes_a_resolution_session_due(self):
        self.assertNotIn("event_resolution", self.triggers())
        self.outcome("2026-09-14T13:45:00.000Z")
        self.assertIn("event_resolution", self.triggers())

    def test_the_session_runs_and_then_stops_being_due(self):
        self.outcome("2026-09-14T13:45:00.000Z")
        self.assertIn("event_resolution", self.tick()["sessions"][0])
        self.assertIn("event_resolution", self.sessions_started())
        self.assertNotIn("event_resolution", self.triggers())

    def test_a_second_outcome_inside_thirty_minutes_does_not_fire_again(self):
        self.outcome("2026-09-14T13:45:00.000Z")
        self.tick()
        self.outcome("2026-09-14T13:55:00.000Z", ticker="KXJOBS-26SEP")
        self.clock.set(moment(2026, 9, 14, 14, 10))  # 20 minutes after the session
        self.assertNotIn("event_resolution", self.triggers())

    def test_a_second_outcome_after_thirty_minutes_fires_again(self):
        self.outcome("2026-09-14T13:45:00.000Z")
        self.tick()
        self.outcome("2026-09-14T14:30:00.000Z", ticker="KXJOBS-26SEP")
        self.clock.set(moment(2026, 9, 14, 14, 35))
        self.assertIn("event_resolution", self.triggers())

    def test_a_weekend_resolution_still_wakes_a_weekdays_only_desk(self):
        """Markets settle on Saturdays; the cadence slots are what weekdays_only governs."""
        self.outcome("2026-09-12T13:45:00.000Z")
        self.clock.set(moment(2026, 9, 12, 14, 0))  # Saturday
        self.assertEqual(self.triggers(), ["event_resolution"])

    def test_a_desk_that_does_not_declare_the_trigger_is_never_woken_by_one(self):
        self.write_manifest(
            DESK,
            cadence={"sessions": ["09:45"], "timezone": "America/New_York", "weekdays_only": True},
        )
        self.service.close()
        self.service = self.build()
        self.outcome("2026-09-14T13:45:00.000Z")
        self.assertNotIn("event_resolution", self.triggers())

    def test_another_desks_outcome_does_not_wake_this_one(self):
        self.outcome("2026-09-14T13:45:00.000Z", desk="someone-else")
        self.assertNotIn("event_resolution", self.triggers())


class OutcomeContextTests(ServiceCase):
    def context(self):
        return DeskContext(self.service, self.service.manifests[DESK], session_id="s1")

    def outcome(self, at, ticker, pnl):
        self.service.log.append(
            f"desk:{DESK}",
            "desk.outcome",
            {
                "instrument": f"event:CPI:kalshi:yes:{ticker}",
                "market_id": ticker,
                "result": "yes",
                "entry_price": "0.40",
                "exit_price": "1",
                "quantity": "10",
                "pnl": pnl,
                "held_for_hours": "27.0",
                "rationale_excerpt": "base rates",
            },
            id=f"outcome:{DESK}:{ticker}:{at}",
            at=at,
        )

    def test_outcomes_are_the_scored_records_newest_first(self):
        self.outcome("2026-09-10T18:00:00.000Z", "KXA", "1.00")
        self.outcome("2026-09-11T18:00:00.000Z", "KXB", "2.00")
        self.outcome("2026-09-12T18:00:00.000Z", "KXC", "3.00")
        rows = self.context().outcomes(2)
        self.assertEqual([r["market_id"] for r in rows], ["KXC", "KXB"])
        self.assertEqual(rows[0]["pnl"], "3.00")

    def test_a_desk_with_nothing_resolved_sees_an_empty_list(self):
        self.assertEqual(self.context().outcomes(10), [])

    def test_another_desks_outcomes_are_not_visible(self):
        self.service.log.append(
            "desk:someone-else",
            "desk.outcome",
            {"instrument": "event:X:kalshi:yes:KXZ", "market_id": "KXZ", "result": "no",
             "entry_price": "0.10", "exit_price": "0", "quantity": "1", "pnl": "-0.10",
             "held_for_hours": "1.0", "rationale_excerpt": ""},
            id="outcome:someone-else:KXZ:1",
            at="2026-09-12T18:00:00.000Z",
        )
        self.assertEqual(self.context().outcomes(10), [])


class SettlementSweepTests(ServiceCase):
    """One tick: sweep the venue's settlements, close the book, wake the desk."""

    TICKER = "KXCPI-26SEP-T3.0"

    def setUp(self):
        super().setUp()
        self.write_manifest(
            DESK,
            venues=["kalshi"],
            instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
            cadence={
                "sessions": ["09:45"],
                "timezone": "America/New_York",
                "weekdays_only": True,
                "triggers": ["event_resolution"],
            },
        )
        self.service.close()
        self.service = self.build()
        self.service.gateway.brokers["kalshi"] = self.settling()

    def settling(self):
        from ltcm.tests.test_gateway import SettlingBroker

        return SettlingBroker(
            rows=[
                {
                    "ticker": self.TICKER,
                    "result": "yes",
                    "yes_count": Decimal("10"),
                    "no_count": Decimal("0"),
                    "revenue": Decimal("10"),
                    "settled_time": "2026-09-14T13:00:00Z",
                }
            ]
        )

    def hold(self):
        instrument = Instrument("event", "CPI", "kalshi", market_id=self.TICKER, right="no")
        self.service.log.append(
            "broker:kalshi",
            "broker.fill",
            {
                "id": "fl-open", "fill_id": "fl-open", "order_id": "ord-open", "desk_id": DESK,
                "instrument": instrument.to_dict(), "side": "buy", "quantity": "10",
                "price": "0.60", "fee": "0.17", "at": "2026-09-13T15:00:00.000Z",
                "venue": "kalshi",
            },
            id="fill:kalshi:fl-open",
            at="2026-09-13T15:00:00.000Z",
        )

    def test_a_settlement_closes_the_book_and_wakes_the_desk_on_the_same_tick(self):
        self.hold()
        result = self.tick()
        self.assertEqual(
            result["settlements"],
            [f"settlement:{self.TICKER}:2026-09-14T13:00:00.000Z"],
        )
        outcome = self.service.log.read(kind="desk.outcome")[0].payload
        self.assertEqual(outcome["market_id"], self.TICKER)
        # A NO position on a market that resolved yes is worth nothing.
        self.assertEqual(outcome["exit_price"], "0")
        self.assertEqual(outcome["pnl"], "-6.00")
        self.assertIn("event_resolution", self.sessions_started())
        self.assertEqual(
            self.service.ledgers[DESK].state(self.service.now()).positions, {}
        )

    def test_a_tick_with_no_settlements_writes_nothing(self):
        result = self.tick()
        self.assertEqual(result["settlements"], [])
        self.assertEqual(self.service.log.read(kind="desk.outcome"), [])

    def test_a_venue_without_a_settlements_endpoint_is_skipped(self):
        self.service.gateway.brokers.pop("kalshi")
        self.assertEqual(self.tick()["settlements"], [])


class RateCardTickTests(ServiceCase):
    """The frozen rate card is verified against Sail's published one, once a day."""

    class Checking(FakeProvider):
        def __init__(self, result=None, error=None):
            super().__init__()
            self.result = result or {"checked": 14, "drift": [], "unchecked": []}
            self.error = error
            self.checks = 0

        def rate_card_check(self):
            self.checks += 1
            if self.error is not None:
                raise self.error
            return self.result

    def build_with(self, provider):
        self.provider = provider
        self.service.close()
        self.service = self.build()
        return provider

    def test_the_card_is_checked_once_a_day_and_the_result_rides_the_tick(self):
        provider = self.build_with(self.Checking())
        result = self.tick()
        self.assertEqual(provider.checks, 1)
        self.assertEqual(result["rate_card"]["checked"], 14)
        self.tick(moment(2026, 9, 14, 19, 35))  # later the same day
        self.assertEqual(provider.checks, 1)
        self.tick(moment(2026, 9, 15, 13, 50))  # the next day
        self.assertEqual(provider.checks, 2)

    def test_a_check_that_raises_is_an_alert_not_a_broken_tick(self):
        self.build_with(self.Checking(error=RuntimeError("docs are down")))
        result = self.tick()
        self.assertIsNone(result["rate_card"])
        self.assertIsNotNone(result["published"])
        alerts = [e.payload["text"] for e in self.service.log.read(kind="ops.alert")]
        self.assertTrue(any("rate card check failed" in text for text in alerts), alerts)

    def test_a_provider_without_the_check_is_not_an_error(self):
        result = self.tick()  # the plain FakeProvider has no rate_card_check
        self.assertIsNone(result["rate_card"])
        alerts = [e.payload["text"] for e in self.service.log.read(kind="ops.alert")]
        self.assertFalse(any("rate card" in text for text in alerts), alerts)


class FakeVenue:
    """A live venue adapter that answers with whatever the test put in it, or refuses to."""

    def __init__(self, venue, *, equity="500", cash="500", as_of="2026-09-14T13:50:00Z"):
        self.venue = venue
        self.equity = Decimal(equity)
        self.cash = Decimal(cash)
        self.as_of = as_of
        self.error = None
        self.delay = 0.0
        self.calls = 0

    def balance(self):
        from ltcm.broker import Balance

        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return Balance(self.venue, self.cash, self.equity, self.cash, self.as_of)


class FakeHub:
    """Stands in for `feeds.FeedHub`: what the sockets saw, handed to the tick on request."""

    def __init__(self, *, fill_venues=(), resolutions=(), quote=None):
        self.pending = {"fill_venues": list(fill_venues), "resolutions": list(resolutions)}
        self.fixed_quote = quote
        self.drains = 0
        self.health_checks = 0
        self.started = False

    def drain(self):
        self.drains += 1
        out, self.pending = self.pending, {"fill_venues": [], "resolutions": []}
        return out

    def quote(self, instrument):
        return self.fixed_quote

    def check_health(self):
        self.health_checks += 1
        return []

    def start(self):
        self.started = True

    def stop(self, timeout=2.0):
        self.started = False


class FillingVenue(FakeVenue):
    """A venue whose REST fills endpoint answers, so a socket candidate can be confirmed."""

    def __init__(self, venue, fills=(), **kw):
        super().__init__(venue, **kw)
        self.fill_rows = list(fills)
        self.fill_calls = 0
        self.upgrades = 0
        self.upgrade_error = None

    def fills(self, since=None):
        self.fill_calls += 1
        return list(self.fill_rows)

    def upgrade_api_tier(self):
        self.upgrades += 1
        if self.upgrade_error is not None:
            raise self.upgrade_error
        return {"usage_tier": "advanced"}


class FeedsTests(ServiceCase):
    """leap: feeds -- the sockets make the REST sweeps run sooner; they never write the ledger."""

    def live(self, **venues):
        self.venues = venues
        self.service.close()
        self.service = self.build(live_venues=sorted(venues))
        return self.service

    def test_without_a_gateway_there_are_no_feeds_and_a_tick_says_so(self):
        self.assertIsNone(self.service.feeds)
        self.assertIsNone(self.tick()["feeds"])

    def test_a_socket_fill_candidate_is_confirmed_by_rest_on_the_same_tick(self):
        from ltcm.broker import Fill, Instrument

        instrument = Instrument("event", "KXFED-26SEP-T3.75", "kalshi", market_id="KXFED-26SEP-T3.75")
        fill = Fill("t-1", "o-1", "", instrument, "buy", Decimal("10"), Decimal("0.89"), Decimal("0.05"), "2026-09-14T13:49:00.000Z")
        venue = FillingVenue("kalshi", fills=[fill])
        service = self.live(kalshi=venue)
        service.feeds = FakeHub(fill_venues=["kalshi"])
        result = self.tick()
        self.assertEqual(result["feeds"]["fill_venues"], ["kalshi"])
        self.assertEqual(result["feeds"]["fills_confirmed"], ["t-1"])
        self.assertEqual(venue.fill_calls, 1)
        events = service.log.read(stream="broker:kalshi", kind="broker.fill")
        self.assertEqual([e.id for e in events], ["fill:kalshi:t-1"])
        self.assertEqual(service.feeds.health_checks, 1)
        # Nothing pending: the next tick confirms nothing and the ledger is not written twice.
        self.tick(moment(2026, 9, 14, 13, 51))
        self.assertEqual(len(service.log.read(stream="broker:kalshi", kind="broker.fill")), 1)

    def test_a_fresh_socket_price_beats_every_poll_and_its_absence_changes_nothing(self):
        from ltcm.broker import Instrument, Quote

        instrument = Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")
        live = Quote(instrument, Decimal("76790"), Decimal("76800"), Decimal("76795"), "2026-09-14T13:50:00.000Z", "coinbase:ws", False)
        self.service.feeds = FakeHub(quote=live)
        self.assertEqual(self.service.quote(instrument).source, "coinbase:ws")
        self.service.feeds = FakeHub(quote=None)
        self.assertEqual(self.service.quote(instrument).source, "fake")

    def test_the_kalshi_tier_is_asked_for_once_after_the_first_api_fill(self):
        venue = FillingVenue("kalshi")
        service = self.live(kalshi=venue)
        self.tick()
        self.assertEqual(venue.upgrades, 0, "no fill yet, nothing to ask for")
        service.log.append(
            "broker:kalshi", "broker.fill",
            {"fill_id": "t-1", "order_id": "o-1", "desk_id": DESK, "side": "buy", "quantity": "10", "price": "0.89", "fee": "0.05"},
            id="fill:kalshi:t-1", at="2026-09-14T13:50:30.000Z",
        )
        self.tick(moment(2026, 9, 14, 13, 51))
        self.assertEqual(venue.upgrades, 1)
        self.assertEqual(service.state()["kalshi_tier_upgraded"], "2026-09-14T13:51:00.000Z")
        texts = [e.payload["text"] for e in service.log.read(kind="ops.alert") if "tier" in e.payload["text"]]
        self.assertEqual(len(texts), 1)
        self.assertIn("upgraded to advanced", texts[0])
        self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual(venue.upgrades, 1, "granted once, never asked again")

    def test_a_refused_upgrade_is_retried_a_day_later_not_every_tick(self):
        from ltcm.broker import BrokerError

        venue = FillingVenue("kalshi")
        venue.upgrade_error = BrokerError("kalshi api tier upgrade: 403 No API-created order was found")
        service = self.live(kalshi=venue)
        service.log.append("broker:kalshi", "broker.fill", {"fill_id": "t-1"}, id="fill:kalshi:t-1", at="2026-09-14T13:49:00.000Z")
        self.tick()
        self.assertEqual(venue.upgrades, 1)
        self.assertNotIn("kalshi_tier_upgraded", service.state())
        self.tick(moment(2026, 9, 14, 15, 0))
        self.assertEqual(venue.upgrades, 1, "inside the day: not again")
        self.tick(moment(2026, 9, 15, 14, 0))
        self.assertEqual(venue.upgrades, 2, "a day later: asked again")


class AccountBalanceTests(ServiceCase):
    """The masthead number the owner asked for: the venues' own balances, added up."""

    KALSHI = "492.29"
    COINBASE = "487.40"

    def live_floor(self, **venues):
        self.venues = venues or {
            "kalshi": FakeVenue("kalshi", equity=self.KALSHI, cash=self.KALSHI),
            "coinbase": FakeVenue("coinbase", equity=self.COINBASE, cash="12.60"),
        }
        self.service.close()
        self.service = self.build(live_venues=sorted(self.venues))
        return self.service

    def marks(self):
        return [
            event.payload["account_equity"]
            for event in self.service.log.read(stream="ops", kind="floor.mark")
        ]

    def test_the_checkpoint_carries_every_venue_balance_and_their_sum(self):
        floor = self.live_floor().checkpoint()["floor"]
        self.assertEqual(floor["account_equity"], Decimal("979.69"))
        self.assertEqual(floor["account_cash"], Decimal("504.89"))
        # Kalshi first, the way the owner reads the two accounts.
        self.assertEqual([row["venue"] for row in floor["venues"]], ["kalshi", "coinbase"])
        self.assertEqual(floor["venues"][0]["equity"], Decimal(self.KALSHI))
        self.assertEqual(floor["venues"][1]["cash"], Decimal("12.60"))
        # A venue stamps to the second; the site accepts milliseconds and nothing else.
        self.assertEqual(floor["venues"][0]["as_of"], "2026-09-14T13:50:00.000Z")
        self.assertNotIn("stale", floor["venues"][0])
        # The ledger's own number is untouched: it is what attributes a gain to a desk.
        self.assertEqual(floor["live_equity"], Decimal("0"))

    def test_a_floor_with_no_live_venue_publishes_no_account_block_at_all(self):
        floor = self.service.checkpoint()["floor"]
        for field in ("account_equity", "account_cash", "venues"):
            self.assertNotIn(field, floor)
        self.assertEqual(self.marks(), [])

    def test_a_venue_that_never_answered_is_absent_rather_than_zero(self):
        broken = FakeVenue("kalshi")
        broken.error = RuntimeError("down")
        floor = self.live_floor(kalshi=broken, coinbase=FakeVenue("coinbase", equity="10")).checkpoint()["floor"]
        self.assertEqual([row["venue"] for row in floor["venues"]], ["coinbase"])
        self.assertEqual(floor["account_equity"], Decimal("10"))

    def test_a_venue_that_stops_answering_keeps_its_last_numbers_and_says_they_are_stale(self):
        service = self.live_floor()
        service.checkpoint()
        self.venues["kalshi"].error = RuntimeError("venue down")
        self.clock.set(self.START + 61)
        floor = service.checkpoint()["floor"]
        kalshi = floor["venues"][0]
        self.assertEqual(kalshi["venue"], "kalshi")
        self.assertTrue(kalshi["stale"])
        self.assertEqual(kalshi["equity"], Decimal(self.KALSHI))
        self.assertNotIn("stale", floor["venues"][1])
        # The total still counts the stale sleeve: the money is there, the reading is old.
        self.assertEqual(floor["account_equity"], Decimal("979.69"))
        alerts = [e.payload["text"] for e in service.log.read(kind="ops.alert")]
        self.assertEqual([t for t in alerts if "stale" in t], ["kalshi balance is stale: the venue did not answer"])
        # An outage every half minute must not become a wall of identical alerts.
        self.clock.set(self.START + 122)
        service.checkpoint()
        alerts = [e.payload["text"] for e in service.log.read(kind="ops.alert")]
        self.assertEqual(len([t for t in alerts if "stale" in t]), 1)

    def test_a_balance_is_read_once_a_minute_however_often_the_floor_publishes(self):
        service = self.live_floor()
        service.checkpoint()
        service.checkpoint()
        self.assertEqual(self.venues["kalshi"].calls, 1)
        self.clock.set(self.START + 30)
        service.checkpoint()
        self.assertEqual(self.venues["kalshi"].calls, 1)
        self.clock.set(self.START + 61)
        service.checkpoint()
        self.assertEqual(self.venues["kalshi"].calls, 2)

    def test_a_slow_venue_never_holds_up_the_checkpoint(self):
        from ltcm import service as service_module

        service = self.live_floor()
        service.checkpoint()  # both venues answer, so both have something to fall back on
        self.venues["kalshi"].delay = 5.0
        self.clock.set(self.START + 61)
        timeout = service_module.VENUE_BALANCE_TIMEOUT
        service_module.VENUE_BALANCE_TIMEOUT = 0.05
        try:
            started = time.monotonic()
            floor = service.checkpoint()["floor"]
        finally:
            service_module.VENUE_BALANCE_TIMEOUT = timeout
        self.assertLess(time.monotonic() - started, 4.0)
        self.assertTrue(floor["venues"][0]["stale"])
        self.assertEqual(floor["account_equity"], Decimal("979.69"))

    def test_the_floor_mark_is_written_at_most_every_five_minutes_and_only_on_a_change(self):
        service = self.live_floor()
        service.checkpoint()
        self.assertEqual(self.marks(), ["979.69"])
        self.venues["kalshi"].equity = Decimal("500.00")
        self.clock.set(self.START + 61)
        service.checkpoint()  # the balance moved, but only a minute has passed
        self.assertEqual(self.marks(), ["979.69"])
        self.clock.set(self.START + 400)
        service.checkpoint()  # five minutes on, and the balance moved
        self.assertEqual(self.marks(), ["979.69", "987.40"])
        self.clock.set(self.START + 800)
        service.checkpoint()  # five minutes on, and nothing moved
        self.assertEqual(self.marks(), ["979.69", "987.40"])

    def test_the_floor_mark_is_a_public_ops_record_the_site_will_accept(self):
        from ltcm.publish import shape_problem

        service = self.live_floor()
        service.checkpoint()
        event = service.log.last("ops", "floor.mark")
        self.assertTrue(event.public)
        self.assertEqual(event.stream, "ops")
        self.assertEqual(
            sorted(event.payload), ["account_cash", "account_equity", "as_of", "venues"]
        )
        self.assertEqual(event.payload["as_of"], event.at)
        self.assertEqual(
            event.payload["venues"][0],
            {"venue": "kalshi", "equity": self.KALSHI, "cash": self.KALSHI,
             "as_of": "2026-09-14T13:50:00.000Z"},
        )
        self.assertIsNone(shape_problem(event))

    def test_the_health_file_shows_the_venue_balances_and_their_staleness(self):
        service = self.live_floor()
        self.venues["coinbase"].error = RuntimeError("down")
        service.health()
        self.venues["coinbase"].error = None
        self.clock.set(self.START + 61)
        report = service.health()
        self.assertEqual(report["floor"]["account_equity"], "979.69")
        self.assertEqual(report["floor"]["account_cash"], "504.89")
        self.assertEqual([row["venue"] for row in report["floor"]["venues"]], ["kalshi", "coinbase"])
        written = json.loads(self.service.health_path.read_text())
        self.assertEqual(written["floor"]["venues"][1]["equity"], self.COINBASE)


class FakeSandboxes:
    """Stands in for `ltcm.sandbox.SandboxManager`: one recorded run, never a network."""

    def __init__(self):
        self.runs = []
        self.slept = False

    def run(self, desk_id, code, *, purpose="", save_as=None, timeout=120):
        from ltcm.sandbox import CodeRun

        self.runs.append((desk_id, code, purpose, save_as))
        return CodeRun(desk_id, "ab" * 32, "42\n", 0, Decimal("1.5"), "sb_lab-x", purpose, saved_as=save_as)

    def sleep_all(self):
        self.slept = True
        return 1


class LeapSandboxAndRunClockTests(ServiceCase):
    """leap: sandbox and run clock -- a desk runs code in its own box; the public sees the run."""

    def test_run_code_publishes_the_run_and_returns_it_to_the_desk(self):
        self.service.sandboxes = FakeSandboxes()
        ctx = self.service.context(self.service.manifests[DESK], session_id="s-9")
        out = ctx.run_code("print(6*7)", "a probe", "answer")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(out["output"], "42\n")
        self.assertEqual(out["saved_as"], "answer")
        event = self.service.log.read(kind="desk.code_run")[0]
        self.assertEqual(event.stream, f"desk:{DESK}")
        self.assertEqual(event.payload["session_id"], "s-9")
        self.assertEqual(event.payload["exit_code"], 0)
        self.assertEqual(event.payload["language"], "python")
        self.assertEqual(event.payload["sandbox"], "sb_lab-x"[-12:])
        self.assertEqual(self.service.sandboxes.runs, [(DESK, "print(6*7)", "a probe", "answer")])
        self.service.close()
        self.assertTrue(self.service.sandboxes.slept)

    def test_without_a_lab_image_the_tool_answers_rather_than_failing(self):
        self.assertIsNone(self.service.sandboxes)  # no image configured in tests
        ctx = self.service.context(self.service.manifests[DESK], session_id="s-9")
        out = ctx.run_code("print(1)", "probe", None)
        self.assertEqual(out["exit_code"], 3)
        self.assertEqual(self.service.log.read(kind="desk.code_run"), [])

    def test_the_checkpoint_carries_the_run_clock(self):
        self.fund()
        self.tick()
        run = self.publisher.checkpoints[-1]["run"]
        for key in ("started_at", "uptime_seconds", "availability_7d_pct", "sessions_total", "sessions_today",
                    "decisions_total", "sail_model_spend_today_usd", "sail_model_spend_total_usd",
                    "sail_infra_spend_total_usd", "sail_spend_total_usd", "pnl_total_usd", "pnl_per_sail_dollar",
                    "models_used"):
            self.assertIn(key, run)
        self.assertEqual(run["sessions_total"], 1)
        self.assertEqual(run["sessions_today"], 1)
        self.assertEqual(str(run["sail_model_spend_today_usd"]), "0.03")
        self.assertIsInstance(run["models_used"], list)
        desk = self.publisher.checkpoints[-1]["desks"][0]
        self.assertEqual(desk["next_session_at"], "2026-09-14T19:30:00.000Z")  # 15:30 New York, after the 09:45 ran


class ForecastResolverTests(ServiceCase):
    """Kalshi reports a settled market as `finalized`; the resolver must read it that way."""

    def resolver_with(self, row):
        self.service.source = lambda name: SimpleNamespace(market=lambda ticker: row) if name == "event" else None
        return self.service._forecast_resolver()

    def test_a_finalized_market_resolves_and_a_determined_one_waits(self):
        finalized = {"status": "finalized", "result": "no", "close_time": "2026-09-15T22:00:00Z", "expiration_time": "2026-09-15T22:05:00Z", "settlement_time": None}
        self.clock.set(moment(2026, 9, 15, 22, 10))
        answer = self.resolver_with(finalized)("kalshi", "KXBTCD-26SEP1518-T86799.99")
        self.assertEqual(answer["result"], "no")
        self.assertEqual(answer["settled_at"], "2026-09-15T22:00:00Z")
        self.assertEqual(self.resolver_with({**finalized, "status": "settled"})("kalshi", "X")["result"], "no")
        self.assertIsNone(self.resolver_with({**finalized, "status": "determined"})("kalshi", "X"))
        self.assertIsNone(self.resolver_with({**finalized, "status": "active", "result": ""})("kalshi", "X"))
        self.assertIsNone(self.resolver_with(finalized)("coinbase", "X"))


class MemoryScopeTests(ServiceCase):
    def test_a_desk_reads_only_its_own_memory(self):
        self.write_manifest("earnings-02")
        self.service.close()
        self.service = self.build()
        mine = self.service.context(self.service.manifests[DESK], session_id="s-1")
        other = self.service.context(self.service.manifests["earnings-02"], session_id="s-2")
        mine.memory_write({"kind": "note", "text": "AAPL trend up"})
        other.memory_write({"kind": "note", "text": "Fed hike at 93%"})
        texts = [row["text"] for row in mine.memory_read("", 10)]
        self.assertEqual(texts, ["AAPL trend up"])
        self.assertEqual([row["text"] for row in other.memory_read("", 10)], ["Fed hike at 93%"])


class DeferredRewriteTests(ServiceCase):
    """A spawn copies the parent's playbook at once; the model's rewrite lands on a later tick."""

    def setUp(self):
        super().setUp()
        self.service.close()
        self.service = self.build(evolution={"target_variants": 2}, seed_batch=1)

    def test_the_child_is_born_with_the_parents_playbook_and_rewritten_off_the_tick(self):
        import time

        self.assertIsNotNone(self.service.evolution.rewriter, "the service defers rewrites by default")
        jobs = []
        self.service.evolution.rewriter = jobs.append  # hold the job so the two halves are observable
        result = self.tick()
        self.assertEqual([a["desk_id"] for a in result["evolution"]], ["earnings-01-2"])
        self.assertEqual(result["rewrites"], [])
        child = self.service.manifests["earnings-01-2"]
        parent_text = (self.root / "playbooks" / "earnings-01.md").read_text(encoding="utf-8")
        self.assertEqual((self.root / "playbooks" / "earnings-01-2.md").read_text(encoding="utf-8"), parent_text)
        self.assertEqual([j["desk_id"] for j in jobs], ["earnings-01-2"])
        self.assertEqual(jobs[0]["parent_id"], "earnings-01")

        # The worker asks the model off the tick (the fake answers "memo body") ...
        self.service._schedule_rewrite(jobs[0])
        deadline = time.monotonic() + 5
        while self.service._rewrite_done.qsize() == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.service._rewrite_done.qsize(), 1)
        self.assertTrue(any("playbook" in str(c) for c in self.provider.calls))
        # ... and the next tick applies it on the tick's own thread, versioned and published.
        result = self.tick(moment(2026, 9, 14, 13, 51))
        self.assertEqual(result["rewrites"], ["earnings-01-2"])
        self.assertEqual((self.root / "playbooks" / "earnings-01-2.md").read_text(encoding="utf-8").strip(), "memo body")
        history = self.root / "playbooks" / "history" / "earnings-01-2"
        self.assertEqual(sorted(p.name for p in history.iterdir()), ["v1.md", "v2.md"])
        event = self.service.log.read(stream=child.stream, kind="desk.playbook_updated")[-1]
        self.assertIn("bred from earnings-01", event.payload["reason"])
        self.assertEqual(event.payload["version"], 2)
        self.assertIn("+memo body", event.payload["diff"])
        # A tick with nothing finished is a no-op, and a failed model call never blocks the tick.
        self.assertEqual(self.service.apply_rewrites(moment(2026, 9, 14, 13, 52)), [])
        self.assertEqual(self.service.state().get("pending_rewrites"), {})

    def test_a_queued_rewrite_survives_a_restart(self):
        import time

        jobs = []
        self.service.evolution.rewriter = jobs.append
        self.tick()
        self.service._schedule_rewrite(jobs[0])  # queued, and remembered in the state file
        self.assertEqual(list(self.service.state()["pending_rewrites"]), ["earnings-01-2"])
        self.service.close()  # the loop restarts: the queue is gone, the state is not
        self.service = self.build(evolution={"target_variants": 2}, seed_batch=1)
        first = self.tick(moment(2026, 9, 14, 13, 51))  # re-queues the job; the fake model is instant
        deadline = time.monotonic() + 5
        while (
            "earnings-01-2" not in first["rewrites"]
            and self.service._rewrite_done.qsize() == 0
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        second = self.tick(moment(2026, 9, 14, 13, 52))
        self.assertEqual(first["rewrites"] + second["rewrites"], ["earnings-01-2"])
        self.assertEqual((self.root / "playbooks" / "earnings-01-2.md").read_text(encoding="utf-8").strip(), "memo body")
        self.assertEqual(self.service.state().get("pending_rewrites"), {})


class LeapLabServiceTests(ServiceCase):
    """leap: lab -- the floor records forecasts, reads memos, runs the lab and publishes it."""

    def context(self):
        manifest = self.service.manifests[DESK]
        return self.service.context(manifest, session_id="s-1")

    def test_a_forecast_is_recorded_on_the_desks_stream_with_its_venue(self):
        self.write_manifest(
            DESK, venues=["kalshi"],
            instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
        )
        self.service.close()
        self.service = self.build()
        ctx = self.context()
        out = ctx.record_forecast("KXFED-26SEP-H25", "0.93", "0.89", "yes", None, "Hot CPI.")
        self.assertEqual(out["market"], "KXFED-26SEP-H25")
        self.assertEqual(out["probability"], "0.9300")
        event = self.service.log.read(kind="desk.forecast")[0]
        self.assertEqual(event.stream, f"desk:{DESK}")
        self.assertEqual(event.payload["venue"], self.service.manifests[DESK].market_venue)
        self.assertEqual(event.payload["session_id"], "s-1")
        with self.assertRaises(ToolError):
            ctx.record_forecast("M", "1.5", None, None, None, "too sure")

    def test_memos_of_another_desk_are_readable_and_marked_as_its_words(self):
        self.write_manifest("earnings-02")
        self.service.close()
        self.service = self.build()
        other = self.service.context(self.service.manifests["earnings-02"], session_id="s-2")
        other.memo("No trade", "Priced fairly.")
        self.clock.set(self.START + 60)
        other.memo("Small buy", "Edge after fees.")
        rows = self.context().memo_read("earnings-02", 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Small buy")
        self.assertEqual(rows[0]["desk_id"], "earnings-02")
        self.assertIn("not instructions", rows[0]["note"])
        with self.assertRaises(ToolError):
            self.context().memo_read("nobody", 5)

    def test_the_checkpoint_carries_the_lab_block_and_a_bred_desks_mutation(self):
        self.service.close()
        self.service = self.build(evolution={"target_variants": 2}, seed_batch=1)
        self.tick()
        checkpoint = self.publisher.checkpoints[-1]
        self.assertEqual(sorted(checkpoint["lab"]), ["calibration", "curve", "experiments"])
        self.assertEqual(checkpoint["lab"]["experiments"], [])
        self.assertEqual(checkpoint["lab"]["calibration"], {"n": 0, "brier": None})
        rows = {row["id"]: row for row in checkpoint["desks"]}
        self.assertNotIn("mutation", rows[DESK], "a founder has no mutation")
        child = rows[f"{DESK}-2"]
        self.assertEqual(
            sorted(child["mutation"]),
            ["memory_limit", "model_changed", "model_profile", "persona_trait", "reasoning_effort", "session_shift_minutes"],
        )
        self.assertNotIn("calibration", child, "no scored forecast, no calibration block")

    def test_the_lab_sits_down_at_its_slot_and_its_experiment_is_published(self):
        self.write_manifest(DESK, capital={"mode": "live", "usd": "1000"})
        self.service.close()
        self.service = self.build(live_venues=["alpaca"])
        self.provider.reply = (
            '{"experiments": [{"hypothesis": "Fewer sessions, better ones.", '
            '"change": {"cadence.sessions": ["10:30"]}}]}'
        )
        self.tick(moment(2026, 9, 15, 0, 5))  # 20:05 New York on the 14th: the lab's slot; the ask
        self.assertEqual(self.service.state()["lab_pending_day"], "2026-09-14")
        self.assertEqual(self.service.log.read(kind="lab.experiment"), [], "one model call per tick: the ask first")
        self.tick(moment(2026, 9, 15, 0, 6))  # the next tick breeds the proposal
        experiments = self.service.log.read(kind="lab.experiment")
        self.assertEqual([e.payload["status"] for e in experiments], ["proposed", "running"])
        self.assertIn(f"{DESK}-2", self.service.manifests)
        self.assertEqual(self.service.manifests[f"{DESK}-2"].cadence.sessions, ("10:30",))
        self.assertEqual(self.service.state()["last_lab_day"], "2026-09-14")
        self.assertIsNone(self.service.state().get("lab_pending_day"))
        # The same evening again: nothing more is asked for.
        self.tick(moment(2026, 9, 15, 0, 40))
        self.assertEqual(len(self.service.log.read(kind="lab.experiment")), 2)
        checkpoint = self.publisher.checkpoints[-1]
        self.assertEqual(checkpoint["lab"]["experiments"][0]["status"], "running")
        self.assertEqual(checkpoint["lab"]["experiments"][0]["variant_desk_id"], f"{DESK}-2")

    def test_calibration_runs_on_its_own_clock_and_publishes_yesterday(self):
        self.write_manifest(
            DESK, venues=["kalshi"],
            instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []},
        )
        self.service.close()
        self.service = self.build()
        ctx = self.context()
        ctx.record_forecast("M1", "0.8", None, None, None, "r")
        self.service.log.append(
            f"desk:{DESK}", "desk.outcome",
            {"instrument": "event:M1:kalshi:yes:M1", "market_id": "M1", "result": "yes", "entry_price": "0.5",
             "exit_price": "1", "quantity": "1", "pnl": "0.5", "held_for_hours": 1, "rationale_excerpt": ""},
            at="2026-09-14T20:00:00.000Z",
        )
        self.tick(moment(2026, 9, 15, 0, 5))  # the first tick after midnight UTC
        published = self.service.log.read(kind="lab.calibration")
        self.assertTrue(published)
        self.assertEqual(published[0].id, f"calibration:2026-09-14:desk:{DESK}")
        self.assertEqual(published[0].payload["n"], 1)
        rows = {row["id"]: row for row in self.publisher.checkpoints[-1]["desks"]}
        self.assertEqual(rows[DESK]["calibration"]["n"], 1)
        self.assertEqual(str(rows[DESK]["calibration"]["brier"]), "0.0400")
        self.assertEqual(self.publisher.checkpoints[-1]["lab"]["calibration"]["n"], 1)



class WorkingOrdersCheckpointTests(ServiceCase):
    def test_the_desk_row_carries_its_resting_orders_and_its_budget_factor(self):
        # The site shows the book as it stands, so a visitor never opens Kalshi to see what the
        # desk is bidding. Both fields ride only when the deployment publishes strategies.
        self.service.close()
        self.service = self.build(checkpoint_strategies=True)
        row = {
            "order_id": "ord-7", "intent_id": "oi-7", "market_id": "KXBTC-1", "symbol": "KXBTC-1", "right": "no",
            "asset_class": "event", "venue": "kalshi", "side": "buy", "purpose": "entry", "strategy": "hourly_quotes",
            "quantity": "13", "limit_price": "0.75", "submitted_at": "2026-09-13T13:00:00.000Z",
        }
        self.service.strategies.open_orders_for = lambda manifest: [dict(row)] if manifest.id == DESK else []
        self.tick()
        desk = {r["id"]: r for r in self.publisher.checkpoints[-1]["desks"]}[DESK]
        self.assertEqual(jsonable(desk["working"]), [{
            "order_id": "ord-7",
            "instrument": {"symbol": "KXBTC-1", "asset_class": "event", "venue": "kalshi", "market_id": "KXBTC-1", "right": "no"},
            "side": "buy", "quantity": "13", "limit_price": "0.75", "submitted_at": "2026-09-13T13:00:00.000Z",
            "purpose": "entry", "strategy": "hourly_quotes", "intent_id": "oi-7",
        }])
        self.assertEqual(desk["budget_factor"], "1", "no record yet: the manifest's budget as written")
        self.service.close()
        self.service = self.build(checkpoint_strategies=False)
        self.tick()
        desk = {r["id"]: r for r in self.publisher.checkpoints[-1]["desks"]}[DESK]
        self.assertNotIn("working", desk)
        self.assertNotIn("budget_factor", desk)


class DiskCheckTests(ServiceCase):
    def test_low_disk_trims_the_cache_files_an_alert_and_mails_the_owner_below_the_stop_line(self):
        import ltcm.service as service_module

        posted = []
        trimmed = []
        self.service.notifier.gateway_url = "https://gateway.test"
        self.service.notifier.token = "t"
        self.service.notifier.poster = lambda url, token, facts: posted.append((url, facts)) or {"sent": True}
        self.service._http_transport = type("T", (), {"trim": lambda self, force=False: trimmed.append(force) or 7})()
        free = {"gb": 10.0}
        original = service_module._disk_free_gb
        service_module._disk_free_gb = lambda path: free["gb"]
        try:
            self.service._disk_check(moment_iso(2026, 9, 14, 19, 5))
            self.assertEqual(trimmed, [], "plenty of room: nothing happens")
            free["gb"] = 3.0
            self.service._disk_check(moment_iso(2026, 9, 14, 19, 5))
            self.assertEqual(trimmed, [], "the ten-minute interval has not passed")
            self.service._disk_check(moment_iso(2026, 9, 14, 19, 16))
            self.assertEqual(trimmed, [True])
            alerts = [e.payload for e in self.service.log.read(kind="ops.alert") if e.payload.get("text", "").startswith("disk:")]
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["level"], "warning")
            self.assertIn("trimmed 7", alerts[0]["text"])
            self.assertEqual(posted, [], "a warning does not mail")
            free["gb"] = 1.2
            self.service._disk_check(moment_iso(2026, 9, 14, 19, 27))
            alerts = [e.payload for e in self.service.log.read(kind="ops.alert") if e.payload.get("text", "").startswith("disk:")]
            self.assertEqual([a["level"] for a in alerts], ["warning", "error"])
            self.assertEqual(len(posted), 1)
            self.assertEqual(posted[0][1]["kind"], "disk_low")
            self.assertEqual(posted[0][1]["free_gb"], 1.2)
            self.service._disk_check(moment_iso(2026, 9, 14, 19, 38))
            self.assertEqual(len(posted), 1, "one mail per level per hour")
        finally:
            service_module._disk_free_gb = original

    def test_the_health_record_carries_free_disk(self):
        self.tick()
        health = json.loads(self.service.health_path.read_text(encoding="utf-8"))
        self.assertIsInstance(health.get("disk_free_gb"), float)


class ShardFundingTests(ServiceCase):
    def test_a_shard_under_the_floor_is_topped_up_from_the_richest_other_shard_once_an_hour(self):
        moves = []

        class Kalshi:
            balances = {0: Decimal("360.51"), 1: Decimal("0"), 2: Decimal("12.30"), 3: Decimal("0")}

            def shard_balances(self):
                return dict(self.balances)

            def transfer_between_shards(self, usd, source, destination):
                moves.append((Decimal(usd), source, destination))
                self.balances[source] -= Decimal(usd)
                self.balances[destination] += Decimal(usd)
                return "tr-1"

        self.service.close()
        self.service = self.build(live_venues=["kalshi"])
        broker = Kalshi()
        self.service.gateway.brokers["kalshi"] = broker
        self.service._fund_kalshi_shards(moment_iso(2026, 9, 14, 19, 5))
        self.assertEqual(moves, [(Decimal("60"), 0, 2)])
        alerts = [e.payload["text"] for e in self.service.log.read(kind="ops.alert") if "kalshi collateral" in e.payload.get("text", "")]
        self.assertEqual(len(alerts), 1)
        self.assertIn("moved 60.00 from shard 0 to shard 2", alerts[0])
        self.service._fund_kalshi_shards(moment_iso(2026, 9, 14, 19, 30))
        self.assertEqual(len(moves), 1, "once an hour")
        broker.balances[0] = Decimal("65")
        broker.balances[2] = Decimal("5")
        self.service._fund_kalshi_shards(moment_iso(2026, 9, 14, 20, 6))
        self.assertEqual(len(moves), 1, "the donor keeps its floor: 65 - 60 keep leaves 5, under the 10 minimum move")
        warnings = [e.payload for e in self.service.log.read(kind="ops.alert") if "no other shard can spare" in e.payload.get("text", "")]
        self.assertEqual(len(warnings), 1)


class FloorBoardContextTests(ServiceCase):
    def test_the_board_carries_one_newest_memo_per_other_desk_from_the_last_day(self):
        self.write_manifest("mullins", venues=["kalshi"], instruments={**SAMPLE["instruments"], "asset_classes": ["event"], "deny": []})
        self.service.close()
        self.service = self.build()
        at = self.service.now()
        self.service.log.append("desk:mullins", "desk.memo", {"session_id": "mullins:s1", "title": "Old", "text": "stale"}, at="2026-09-01T00:00:00.000Z")
        self.service.log.append("desk:mullins", "desk.memo", {"session_id": "mullins:s2", "title": "Fed hike priced", "text": "89 vs my 93. " * 60}, at=at)
        self.service.log.append(f"desk:{DESK}", "desk.memo", {"session_id": f"{DESK}:s1", "title": "Mine", "text": "my own memo"}, at=at)
        rows = self.service.context(self.service.manifests[DESK]).floor_board(8)
        self.assertEqual([(r["desk_id"], r["title"]) for r in rows], [("mullins", "Fed hike priced")], "newest per desk, never the desk's own, never a stale one")
        self.assertLessEqual(len(rows[0]["text"]), 400)
        self.assertEqual(rows[0]["mode"], self.service.manifests["mullins"].capital_mode)
