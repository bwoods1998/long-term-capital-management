"""The standing grant (LTCM v3, D5): `LiveGrant.standing` and its House job `league/ops/grant.py`, tested only against
disposable state, a fake deploy record and fake account reads (invented figures).

It ratifies the grant in force without the owner in two cases only:
- the money digest moved, and an owner's release change (no updater attestation, no drill) is on record since the
  grant was last pinned;
- a deposit landed since the grant was last pinned.
Capital is the lower of equity and the ceiling, never above the envelope; a revoked grant is never touched; anything
unreadable, an updater-only record, a ceiling raised without the owner, or capital under the smallest stake refuses and
changes nothing.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from league.constitution import CONSTITUTION, money_digest
from league.live_trading import (GRANT_ID, STORE, LiveGrant, _epoch, deposits_after, owner_change, policy,
                                 policy_hash, smallest_stake)
from league.ops import grant as job
from league.tests.fakes import Clock

D = Decimal
EQUITY = "700"
CEILING = "5500"
HOUR = 3600.0


def moved_digest():
    """A money rule changed (as an owner's deploy would): the digest the grant pinned is no longer the one in force."""
    return patch.dict(CONSTITUTION["tuition"], max_agents=CONSTITUTION["tuition"]["max_agents"] + 1)


def deposit(at, *, amount="1000", kind="CSD", status="executed", ident="a1"):
    return {"id": ident, "activity_type": kind, "net_amount": amount, "status": status,
            "transaction_time": _iso(at), "date": _iso(at)[:10]}


def _iso(epoch):
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + ".123456789Z"


def owner_deploy(at, release="r-owner-1", deploy=None):
    """The rows the watchdog writes for the owner's `floor_box.py deploy` (no attested sha)."""
    key = deploy or f"{release}@{int(at)}"
    return [{"ts": at - 5, "deploy": key, "release": release, "stage": "canary", "ok": True},
            {"ts": at, "deploy": key, "release": release, "stage": "promote", "ok": True, "current": release},
            {"ts": at + 1, "deploy": key, "release": release, "stage": "restart", "ok": True}]


def updater_deploy(at, release="main-abcdef123456"):
    key = f"{release}@{int(at)}"
    return [{"ts": at, "deploy": key, "release": release, "stage": "promote", "ok": True, "current": release, "sha": "f" * 40},
            {"ts": at + 600, "deploy": key, "release": release, "stage": "verdict", "verdict": "promoted", "sha": "f" * 40}]


class StandingCase(TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "state"
        self.clock = Clock()

    def grant(self):
        grant = LiveGrant(self.root / STORE, clock=self.clock)
        self.addCleanup(grant.close)
        return grant

    def enabled(self, equity=EQUITY):
        grant = self.grant()
        grant.enable(GRANT_ID, equity, CEILING)
        self.pinned = self.clock()
        self.clock.advance(HOUR)
        return grant

    def standing(self, grant, *, equity=EQUITY, release="r-owner-1", rows=(), funding=(), top=CEILING):
        return grant.standing(self.clock(), equity, release, rows, funding=funding, ceiling_usd=top)


class TheRule(StandingCase):
    def test_no_grant_is_never_created(self):
        grant = self.grant()
        with moved_digest():
            out = self.standing(grant, rows=owner_deploy(self.clock() - 60), funding=[deposit(self.clock() - 60)])
        self.assertEqual((out["action"], out["grant"]), ("none", None))
        self.assertIsNone(grant.current())
        self.assertEqual(grant.ratifications(), [])

    def test_a_revoked_grant_is_never_ratified_or_reactivated(self):
        grant = self.enabled()
        grant.revoke()
        self.clock.advance(60)
        with moved_digest():
            out = self.standing(grant, rows=owner_deploy(self.clock() - 30), funding=[deposit(self.clock() - 30)])
            self.assertEqual(out["action"], "none")
            self.assertIn("revoked", out["why"])
            self.assertFalse(grant.current()["active"])
        self.assertEqual(grant.ratifications(), [])
        self.assertIsNotNone(grant.current()["revoked"])

    def test_nothing_moved_means_nothing_written(self):
        grant = self.enabled()
        before = grant.current()
        out = self.standing(grant, rows=owner_deploy(self.clock() - 60), funding=[deposit(self.pinned - 60)])
        self.assertEqual((out["action"], out["triggers"]), ("none", []))
        self.assertEqual(out["before"], out["after"])
        self.assertEqual(grant.current(), before)
        self.assertEqual(grant.ratifications(), [])

    def test_a_digest_moved_by_the_owners_deploy_is_ratified_and_the_release_recorded(self):
        grant = self.enabled()
        with moved_digest():
            self.assertFalse(grant.current()["active"], "a moved digest holds entries first")
            self.assertTrue(grant.standing_due()["digest_moved"])
            out = self.standing(grant, equity="900", release="r-owner-1", rows=owner_deploy(self.clock() - 120))
            self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
            live = grant.current()
            self.assertTrue(live["active"])
            self.assertTrue(grant.allows_live(2))
            self.assertEqual(live["policy"]["constitution_digest"], money_digest())
            self.assertEqual(live["policy"]["capital_usd"], "900.00", "capital is read afresh at the lower of equity and the ceiling")
            row = grant.ratifications()[-1]
            self.assertIn("r-owner-1", row["why"])
            self.assertIn("r-owner-1@", row["why"], "the deploy that moved it is named")
            self.assertTrue(row["why"].startswith("standing:"))
            self.assertEqual(out["after"], policy_hash(json.loads(row["new_policy"])))
            self.assertEqual(out["before"], policy_hash(json.loads(row["old_policy"])))
            self.assertNotEqual(out["before"], out["after"])
            again = self.standing(grant, rows=owner_deploy(self.clock() - 120))
            self.assertEqual(again["action"], "none", "answered once")
        self.assertFalse(grant.allows_live(2), "back on the old rules, the grant pinned on the new ones holds nothing")

    def test_a_digest_move_with_no_owners_release_change_since_the_pin_is_refused(self):
        grant = self.enabled()
        before = grant.current()["policy"]
        records = {
            "nothing on record": [],
            "only the updater's deploys": updater_deploy(self.clock() - 300),
            "the owner's deploy before the pin": owner_deploy(self.pinned - 60),
            "a failed promotion": [{"ts": self.clock() - 60, "deploy": "x@1", "stage": "promote", "ok": False}],
            "a drill": owner_deploy(self.clock() - 60, deploy="drill@1") + [{"ts": self.clock() - 50, "deploy": "drill@1", "stage": "drill"}],
            "an attested rollback": [{"ts": self.clock() - 60, "deploy": "m@1", "stage": "rollback", "ok": True, "sha": "a" * 40}],
        }
        with moved_digest():
            for name, rows in records.items():
                with self.subTest(name):
                    out = self.standing(grant, rows=rows)
                    self.assertEqual(out["action"], "refused")
                    self.assertEqual(out["triggers"], ["digest"])
                    self.assertFalse(grant.current()["active"])
            unknown = self.standing(grant, release=None, rows=owner_deploy(self.clock() - 60))
            self.assertEqual(unknown["action"], "refused")
            self.assertIn("release is unknown", unknown["why"])
        self.assertEqual(grant.ratifications(), [])
        self.assertEqual(grant.current()["policy"], before)

    def test_the_owners_rollback_counts_as_the_owners_release_change(self):
        grant = self.enabled()
        rows = [{"ts": self.clock() - 60, "deploy": "rollback@1", "release": "r-new", "stage": "rollback", "ok": True,
                 "from": "r-new", "to": "r-old"}]
        with moved_digest():
            out = self.standing(grant, release="r-old", rows=rows)
            self.assertEqual(out["action"], "ratified")
            self.assertTrue(grant.current()["active"])

    def test_a_deposit_that_landed_since_the_pin_reads_capital_again_up_to_the_ceiling(self):
        grant = self.enabled()
        landed = deposit(self.clock() - 60, amount="2000")
        out = self.standing(grant, equity="2700", funding=[landed], rows=[], release=None)
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["deposit"]))
        self.assertEqual(grant.current()["policy"]["capital_usd"], "2700.00")
        self.assertTrue(grant.current()["active"])
        self.assertIn("deposit", grant.ratifications()[-1]["why"])
        self.assertEqual(self.standing(grant, equity="2700", funding=[landed])["action"], "none", "answered once")
        self.clock.advance(HOUR)
        big = deposit(self.clock() - 60, amount="9000", ident="a2")
        high = self.standing(grant, equity="11700", funding=[landed, big])
        self.assertEqual(high["action"], "ratified")
        self.assertEqual(grant.current()["policy"]["capital_usd"], "5500.00", "never above the owner's ceiling")
        self.clock.advance(HOUR)
        same = deposit(self.clock() - 60, amount="10", ident="a3")
        self.assertEqual(self.standing(grant, equity="11710", funding=[same])["action"], "ratified")
        self.assertEqual(len(grant.ratifications()), 3, "a ratification is written even when the policy reads the same")
        self.assertEqual(self.standing(grant, equity="11710", funding=[same])["action"], "none", "so the pin moved past it")

    def test_what_is_no_deposit(self):
        grant = self.enabled()
        later = self.clock() - 60
        for name, row in {
            "landed before the pin": deposit(self.pinned - 1),
            "a withdrawal": deposit(later, amount="-500"),
            "pending": deposit(later, status="queued"),
            "rejected": deposit(later, status="rejected"),
            "a trade": deposit(later, kind="FILL"),
            "a dividend": deposit(later, kind="DIV"),
            "no time": {"id": "x", "activity_type": "CSD", "net_amount": "100", "status": "executed"},
            "no amount": {**deposit(later), "net_amount": "n/a"},
            "a time with no zone": {**deposit(later), "transaction_time": "2026-10-02T15:00:00"},
            "not a row": "CSD",
        }.items():
            with self.subTest(name):
                self.assertEqual(self.standing(grant, funding=[row])["action"], "none")
        self.assertEqual(grant.ratifications(), [])

    def test_capital_is_never_above_the_envelope_and_never_under_the_smallest_stake(self):
        grant = self.enabled()
        before = grant.current()["policy"]
        landed = [deposit(self.clock() - 60)]
        owner = owner_deploy(self.clock() - 60)
        for name, kwargs in {
            "a ceiling above the envelope": {"top": "10000.01", "equity": "20000", "rows": owner},
            "equity under the smallest stake": {"equity": str(smallest_stake() - D("0.01"))},
            "equity unreadable": {"equity": None},
            "equity nonsense": {"equity": "NaN"},
            "ceiling unreadable": {"top": "x"},
        }.items():
            with self.subTest(name):
                out = self.standing(grant, funding=landed, **kwargs)
                self.assertEqual(out["action"], "refused")
                self.assertEqual(out["before"], out["after"])
        self.assertEqual(grant.current()["policy"], before)
        self.assertEqual(grant.ratifications(), [])
        self.assertTrue(grant.current()["active"], "a refused deposit leaves the grant as it was")

    def test_a_higher_ceiling_needs_the_owners_release_change(self):
        grant = self.enabled()
        landed = [deposit(self.clock() - 60)]
        raised = self.standing(grant, equity="7000", top="6000", funding=landed)
        self.assertEqual(raised["action"], "refused")
        self.assertIn("ceiling rose", raised["why"])
        ok = self.standing(grant, equity="7000", top="6000", funding=landed, rows=owner_deploy(self.clock() - 30))
        self.assertEqual(ok["action"], "ratified")
        self.assertEqual(grant.current()["policy"]["capital_usd"], "6000.00")
        self.clock.advance(HOUR)
        lower = self.standing(grant, equity="7000", top="5000", funding=[deposit(self.clock() - 60, ident="b")])
        self.assertEqual(lower["action"], "ratified", "a lower ceiling only tightens")
        self.assertEqual(grant.current()["policy"]["capital_usd"], "5000.00")

    def test_the_house_entries_follow_the_standing_ratification(self):
        grant = self.enabled()
        with moved_digest():
            self.assertFalse(grant.allows_live(2))
            self.standing(grant, rows=owner_deploy(self.clock() - 60))
            self.assertTrue(grant.allows_live(2))
            self.assertTrue(LiveGrant(self.root / STORE, clock=self.clock).allows_live(3), "another process sees it")


class TheReaders(TestCase):
    def test_deposit_times_are_when_the_money_moved(self):
        at = 1789000000.0
        rows = [{"id": "1", "activity_type": "CSD", "net_amount": "5", "transaction_time": "2026-09-10T00:26:40.5Z",
                 "date": "2026-09-14"},
                {"id": "2", "activity_type": "JNLC", "net_amount": "5", "date": "2026-09-14"}]
        self.assertEqual([r["id"] for r in deposits_after(rows, at)], ["1", "2"])
        self.assertEqual([r["id"] for r in deposits_after(rows, at + 1)], ["2"], "a date alone is read as 00:00Z")

    def test_owner_change_is_the_newest_unattested_promotion_or_rollback_after_the_pin(self):
        rows = owner_deploy(100.0, release="a") + updater_deploy(200.0) + owner_deploy(300.0, release="b")
        self.assertEqual(owner_change(rows, 0.0)["release"], "b")
        self.assertEqual(owner_change(rows, 250.0)["deploy"], "b@300")
        self.assertIsNone(owner_change(rows, 300.0))
        self.assertIsNone(owner_change([{"at": "2026-10-02T00:00:00Z", "stage": "promote", "ok": True}, "junk", None], 1e12))
        self.assertIsNotNone(owner_change([{"at": "2026-10-02T00:00:00Z", "stage": "promote", "ok": True}], 0.0))


class TheJob(StandingCase):
    def ctx(self, **extra):
        calls = SimpleNamespace(equity=0, funding=[], alerts=[])

        def read_equity():
            calls.equity += 1
            value = extra.pop("_equity", EQUITY)
            if isinstance(value, Exception):
                raise value
            return D(value)

        def read_funding(after):
            calls.funding.append(after)
            value = extra.get("_funding", [])
            if isinstance(value, Exception):
                raise value
            return value

        ctx = {"root": self.root, "clock": self.clock, "config": {"live_trading": {"ceiling_usd": CEILING}},
               "read_equity": read_equity, "read_funding": read_funding,
               "alert": lambda level, text: calls.alerts.append((level, text))}
        ctx.update({k: v for k, v in extra.items() if not k.startswith("_")})
        return ctx, calls

    def test_no_store_is_not_made(self):
        ctx, calls = self.ctx()
        out = job.run(ctx)
        self.assertEqual((out["status"], out["action"]), ("ok", "none"))
        self.assertFalse((self.root / STORE).exists())
        self.assertEqual((calls.equity, calls.funding), (0, []))

    def test_a_revoked_grant_reads_nothing(self):
        self.enabled().revoke()
        ctx, calls = self.ctx()
        out = job.run(ctx)
        self.assertEqual((out["status"], out["action"]), ("ok", "none"))
        self.assertEqual((calls.equity, calls.funding), (0, []))

    def test_a_quiet_hour_reads_funding_only(self):
        self.enabled()
        ctx, calls = self.ctx()
        out = job.run(ctx)
        self.assertEqual((out["status"], out["action"], out["triggers"]), ("ok", "none", []))
        self.assertEqual(out["before"], out["after"])
        self.assertEqual(calls.equity, 0, "no equity read when nothing is to be answered")
        self.assertEqual(len(calls.funding), 1)
        self.assertLess(_epoch(calls.funding[0]), self.pinned, "asked from before the pin")

    def test_a_deposit_is_ratified_and_the_receipt_carries_hashes_not_figures(self):
        grant = self.enabled()
        ctx, calls = self.ctx(_funding=[deposit(self.clock() - 60, amount="1234.56")], _equity="1934.56")
        out = job.run(ctx)
        self.assertEqual((out["status"], out["action"], out["triggers"]), ("ok", "ratified", ["deposit"]))
        self.assertNotEqual(out["before"], out["after"])
        self.assertEqual(out["after"], policy_hash(grant.current()["policy"]))
        self.assertEqual(grant.current()["policy"]["capital_usd"], "1934.56")
        text = json.dumps(out)
        for figure in ("1934.56", "1234.56", "5500.00", "700.00"):
            self.assertNotIn(figure, text)

    def test_a_moved_digest_with_the_owners_deploy_on_record(self):
        grant = self.enabled()
        base = Path(self.dir.name)
        (base / "releases" / "r-owner-2").mkdir(parents=True)
        os.symlink("releases/r-owner-2", base / "current")
        with (base / "deploys.jsonl").open("w") as handle:
            for row in updater_deploy(self.pinned - 900) + owner_deploy(self.clock() - 120, release="r-owner-2"):
                handle.write(json.dumps(row) + "\n")
            handle.write('{"torn": ')
        ctx, _ = self.ctx()
        with moved_digest():
            out = job.run(ctx)
            self.assertEqual((out["status"], out["action"], out["triggers"]), ("ok", "ratified", ["digest"]))
            self.assertEqual(out["release"], "r-owner-2")
            self.assertTrue(grant.current()["active"])
            self.assertIn("r-owner-2", grant.ratifications()[-1]["why"])

    def test_a_moved_digest_without_the_owner_fails_loudly_and_changes_nothing(self):
        grant = self.enabled()
        ctx, calls = self.ctx(deploy_rows=updater_deploy(self.clock() - 60), release="main-abcdef123456")
        with moved_digest():
            out = job.run(ctx)
            self.assertEqual((out["status"], out["action"]), ("failed", "refused"))
            self.assertFalse(grant.current()["active"])
        self.assertEqual(calls.alerts[0][0], "warning")
        self.assertIn("no owner's deploy", calls.alerts[0][1])
        self.assertEqual(grant.ratifications(), [])

    def test_unreadable_reads_fail_closed(self):
        grant = self.enabled()
        ctx, calls = self.ctx(_funding=OSError("gateway down"))
        out = job.run(ctx)
        self.assertEqual(out["status"], "failed")
        self.assertEqual(calls.equity, 0)
        ctx, calls = self.ctx(_funding=[deposit(self.clock() - 60)], _equity=OSError("gateway down"))
        out = job.run(ctx)
        self.assertEqual((out["status"], out["triggers"]), ("failed", ["deposit"]))
        ctx, calls = self.ctx(config={"live_trading": {}})
        self.assertEqual(job.run(ctx)["status"], "failed")
        self.assertEqual(grant.ratifications(), [])
        # A moved digest is still answered while funding is unreadable: only the deposit waits.
        ctx, calls = self.ctx(_funding=OSError("gateway down"), deploy_rows=owner_deploy(self.clock() - 60), release="r-x")
        with moved_digest():
            out = job.run(ctx)
            self.assertEqual((out["status"], out["action"], out["triggers"]), ("ok", "ratified", ["digest"]))

    def test_no_root_is_a_failed_receipt(self):
        self.assertEqual(job.run({})["status"], "failed")
        self.assertEqual(job.run(SimpleNamespace(house=SimpleNamespace(root=self.root)))["action"], "none")

    def test_the_schedule_the_registry_reads(self):
        self.assertEqual((job.NAME, job.EVERY_SECONDS, job.AT_START), ("grant", 3600, True))


class ThePolicyStaysTheOwners(TestCase):
    def test_policy_is_unchanged_by_the_standing_grant(self):
        # The owner's --ratify and the standing grant write the same policy for the same inputs.
        self.assertEqual(policy(EQUITY, CEILING)["capital_usd"], "700.00")
        self.assertEqual(policy(EQUITY, CEILING)["constitution_digest"], money_digest())
