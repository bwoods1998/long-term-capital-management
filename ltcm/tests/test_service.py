import copy
import datetime as dt
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from ltcm.broker import Instrument, Quote
from ltcm.manifest import DeskManifest
from ltcm.service import DeskContext, Service, load_env
from ltcm.tests.test_gateway import FakeBroker
from ltcm.tests.test_manifest import SAMPLE

UTC = dt.timezone.utc
AAPL = Instrument("equity", "AAPL", "paper")
DESK = "earnings-01"


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

    def respond(self, profile, items, **kwargs):
        self.calls.append(kwargs.get("request_key"))
        return SimpleNamespace(output_text="memo body", cost_usd=Decimal("0.01"))

    def spent_today(self, desk_id=None):
        return Decimal("0.03")


class FakeMemory:
    def __init__(self):
        self.entries = []

    def write(self, entry):
        self.entries.append(entry)
        return {"written": True, "id": f"m{len(self.entries)}"}

    def read(self, query, limit):
        return self.entries[-limit:]


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
        if manifest is None:
            return None
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
            "sources": {"news": False, "edgar": False, "event": False, "chain": False},
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

    def test_the_postmortem_runs_after_the_close(self):
        self.tick(moment(2026, 9, 15, 1, 40))  # 21:40 New York on the 14th
        self.assertEqual(self.sessions_started(), ["postmortem"])
        self.tick(moment(2026, 9, 15, 1, 50))
        self.assertEqual(self.sessions_started(), ["postmortem"])

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
    def test_an_unfunded_desk_is_not_marked(self):
        self.tick()
        self.assertEqual(self.service.log.read(stream=f"ledger:{DESK}", kind="ledger.mark"), [])
        self.assertEqual(self.service.ledgers[DESK].state().days_live, 0)
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
                "broker:paper", "broker.fill",
                {"fill_id": f"f{n}", "order_id": "o1", "desk_id": DESK,
                 "instrument": AAPL.to_dict(), "side": side, "quantity": "10",
                 "price": price, "fee": "0", "at": f"2026-09-1{1 + n}T14:00:00.000Z"},
                at=f"2026-09-1{1 + n}T14:00:00.000Z",
            )
        budget = self.service.apply_budget(self.service.now())
        self.assertEqual(budget["trailing_realized_usd"], Decimal("200.00"))
        self.assertEqual(budget["cap_usd"], Decimal("65.00").min(Decimal("60")))
        self.assertEqual(self.provider.floor_cap, Decimal("60"))


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

    def test_a_paper_desk_order_never_reaches_the_critic(self):
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
        self.assertEqual(status["desks"][0]["mode"], "paper")
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
        self.assertIn("Drift", ctx.playbook_read())
        ctx.playbook_write("# new\n\nRules.\n", "learned something")
        self.assertEqual(ctx.playbook_read(), "# new\n\nRules.\n")
        # Versioning belongs to the desk runtime, not to the context.
        self.assertEqual(self.service.log.read(kind="desk.playbook_updated"), [])

    def test_calendar_returns_one_row_per_day(self):
        rows = self.context().calendar(3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["date"], "2026-09-14")
        self.assertTrue(rows[0]["open"])

    def test_a_missing_source_says_so_rather_than_inventing(self):
        ctx = self.context()
        with self.assertRaises(RuntimeError):
            ctx.news("AAPL earnings", 5)


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
