"""The standing grant (LTCM v3, D5): `LiveGrant.standing` and its House job `league/ops/grant.py`, tested only against
disposable state, a fake deploy record and fake account reads (invented figures).

It ratifies the grant in force without the owner in two cases only:
- the money digest moved, and an owner's release change (no updater attestation, no drill) is on record since the
  grant was last pinned;
- a deposit landed since the grant was last pinned (by its id: one still pending at a ratification is answered when it
  settles, whatever time the venue gives it).
Capital is the lower of equity and the ceiling, never above the envelope; a revoked grant is never touched; anything
unreadable, an updater-only record, a ceiling raised without the owner, or capital under the smallest stake refuses and
changes nothing.
"""
from contextlib import ExitStack
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase, skipUnless
from unittest.mock import patch

from league.constitution import CONSTITUTION, money_digest
from league.live_trading import (DEPOSIT_LOOKBACK_SECONDS, GRANT_ID, STORE, LiveGrant, _epoch, deposits_after,
                                 owner_change, policy, policy_hash, smallest_stake)
from league.ops import grant as job
from league.tests.fakes import Clock

D = Decimal
EQUITY = "700"
CEILING = "5500"
HOUR = 3600.0
DAY = 86400.0


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
        old = deposit(self.pinned - DEPOSIT_LOOKBACK_SECONDS - 60)
        out = self.standing(grant, rows=owner_deploy(self.clock() - 60), funding=[old])
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
            "timed before the lookback": deposit(self.pinned - DEPOSIT_LOOKBACK_SECONDS - 1),
            "no id, timed before the pin": {**deposit(self.pinned - 1), "id": None},
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

    def test_a_deposit_pending_across_a_ratification_is_answered_when_it_settles(self):
        # The venue times a funding row at its request: an ACH deposit started before a ratification lands with a
        # time before the pin it moved.
        grant = self.enabled()
        asked = self.clock() - 10
        first = deposit(asked, amount="4000", status="queued", ident="ach-1")
        self.assertEqual(self.standing(grant, funding=[first])["action"], "none", "pending is no deposit")
        self.clock.advance(HOUR)
        with moved_digest():
            out = self.standing(grant, funding=[first], rows=owner_deploy(self.clock() - 60))
            self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
            self.clock.advance(2 * DAY)
            second = deposit(asked + 5, amount="300", status="queued", ident="ach-2")
            settled = {**first, "status": "executed"}
            out = self.standing(grant, equity="4700", funding=[settled, second])
            self.assertEqual((out["action"], out["triggers"]), ("ratified", ["deposit"]))
            self.assertEqual(grant.current()["policy"]["capital_usd"], "4700.00")
            self.assertEqual(self.standing(grant, equity="4700", funding=[settled, second])["action"], "none", "answered once")
            self.clock.advance(DAY)
            out = self.standing(grant, equity="5000", funding=[settled, {**second, "status": "executed"}])
            self.assertEqual(out["action"], "ratified", "the second one, pending while the first was answered, too")
            self.assertEqual(grant.current()["policy"]["capital_usd"], "5000.00")

    def test_a_date_only_deposit_settling_later_the_same_day_is_answered(self):
        grant = self.enabled()
        day = {"id": "d-1", "activity_type": "CSD", "net_amount": "500", "date": _iso(self.clock())[:10]}
        self.clock.advance(60)
        with moved_digest():
            self.standing(grant, funding=[{**day, "status": "pending"}], rows=owner_deploy(self.clock() - 30))
            self.clock.advance(HOUR)
            out = self.standing(grant, equity="1200", funding=[{**day, "status": "executed"}])
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["deposit"]))

    def test_a_deposit_seen_settled_before_a_pin_is_held_by_that_pin(self):
        grant = self.enabled()
        landed = deposit(self.clock() - 60, ident="seen-1")
        self.assertEqual([d["id"] for d in grant.landed([landed], self.clock())], ["seen-1"])
        self.clock.advance(60)
        grant.ratify(GRANT_ID, "1700", CEILING)  # the owner's --ratify, after the look that saw it settled
        self.clock.advance(HOUR)
        self.assertEqual(grant.landed([landed], self.clock()), [])
        self.assertEqual(self.standing(grant, equity="1700", funding=[landed])["action"], "none")

    def test_a_refusal_carries_no_figures(self):
        grant = self.enabled()
        landed = [deposit(self.clock() - 60)]
        low = self.standing(grant, equity="42.17", funding=landed)
        self.assertEqual(low["action"], "refused")
        self.assertEqual(low["why"], "standing: capital does not cover the smallest real stake")
        high = self.standing(grant, equity="20000", top="10000.01", funding=landed, rows=owner_deploy(self.clock() - 30))
        self.assertEqual(high["why"], "standing: the owner's ceiling is above the project envelope")
        for out in (low, high):
            self.assertFalse(any(ch.isdigit() for ch in out["why"]), out["why"])

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


#: The Probe row before release L-D (Oct 9, 2026): the incubator cap's (1665c385) and fast lane v2's.
PRE_LD_PROBE = {"max_loss_share": "0.10", "contracts": 1, "open_per_family": 3, "family_share": "0.15", "floor_usd": "0",
                "max_open": 3, "loss_budget_usd": "400"}


def pre_ld():
    """The constitution's Probe row as it was before release L-D (its three rule rows gone, three slots)."""
    return patch.dict(CONSTITUTION["options_money"]["probe"], PRE_LD_PROBE, clear=True)


def ld_as_set():
    """The constitution's Probe row as release L-D set it (Oct 9, 2026): a $400 total, before the Probe total at
    $800."""
    return patch.dict(CONSTITUTION["options_money"]["probe"], loss_total_usd="400")


class TheIncubatorCap(StandingCase):
    """The incubator cap (Oct 8, 2026): `incubator.max_loss_usd` $50 -> $75 moves the money digest from fast lane v2's
    da5c7542 to 1665c385. A grant pinned on the $50 row holds nothing on the $75 one until the standing grant re-ratifies
    it, which it does by itself only on an owner's release change (`floor_box.py deploy`, or its rollback back across it).
    Run on the Probe row before release L-D (`pre_ld`), which moved the digest again (`TheReleaseLD`)."""

    FAST_LANE = "da5c7542d7b78f967c12c3b2d98140153026c98b5fea9de27b6cf912eff85694"
    CAP = "1665c3858bce937617a339dfa56ae9a38a51e9fd763225ec10a645d3d5bafa08"

    def setUp(self):
        super().setUp()
        patcher = pre_ld()
        patcher.start()
        self.addCleanup(patcher.stop)

    def at_fifty(self):
        return patch.dict(CONSTITUTION["options_money"]["incubator"], max_loss_usd="50")

    def pinned_at_fifty(self):
        with self.at_fifty():
            self.assertEqual(money_digest(), self.FAST_LANE)
            grant = self.enabled()
        self.assertEqual(money_digest(), self.CAP)
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.FAST_LANE)
        return grant

    def test_the_owners_deploy_re_ratifies_it_at_the_houses_start(self):
        grant = self.pinned_at_fifty()
        self.assertFalse(grant.allows_live(2), "real entries are held until it is ratified")
        out = self.standing(grant, release="r-cap-75", rows=owner_deploy(self.clock() - 60, release="r-cap-75"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertIn(f"money digest {self.FAST_LANE[:12]} -> {self.CAP[:12]}", grant.ratifications()[-1]["why"])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.CAP)
        self.assertTrue(grant.allows_live(2))

    def test_the_updater_alone_never_ratifies_it(self):
        grant = self.pinned_at_fifty()
        out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))
        self.assertEqual(grant.ratifications(), [])

    def test_the_owners_rollback_across_it_re_ratifies_on_the_fifty_dollar_row(self):
        grant = self.pinned_at_fifty()
        self.standing(grant, release="r-cap-75", rows=owner_deploy(self.clock() - 60, release="r-cap-75"))
        self.clock.advance(HOUR)
        back = [{"ts": self.clock() - 60, "deploy": "rollback@2", "release": "r-cap-75", "stage": "rollback", "ok": True,
                 "from": "r-cap-75", "to": "r-fast-lane"}]
        with self.at_fifty():
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-fast-lane", rows=back)
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.FAST_LANE)
            self.assertTrue(grant.allows_live(2))


class TheReleaseLD(StandingCase):
    """Release L-D (Oct 9, 2026): the Probe row's `max_open` 3 -> 8, its new `loss_basis` "net" and `demotion` "dm1", and
    THE ROLLING PROBE BUDGET's `loss_window_sessions` 20 and `loss_total_usd` "400" (the operator's setting of Oct 9,
    inside the owner's $800 ceiling) move the money digest from the incubator cap's 1665c385 to 0310779c. A grant pinned on 1665c385 holds nothing after the deploy until the standing
    grant re-ratifies it at the House's start, on the owner's release change only. Its CON-only rollback (`loss_basis`
    "gross", `max_open` 3, `demotion` "dm0", `loss_total_usd` "400", `loss_window_sessions` 2000) is a digest of its own,
    320899d6, ratified the same way on the owner's deploy of it; `floor_box.py rollback` to the release before L-D brings
    1665c385 back. Run on L-D's own $400 total (`ld_as_set`): THE PROBE TOTAL AT $800 moved the digest again
    (`TheProbeTotal800`)."""

    BEFORE = "1665c3858bce937617a339dfa56ae9a38a51e9fd763225ec10a645d3d5bafa08"
    LD = "0310779c2f58eaf453835f1c989f130cf92a74198198b624cf021298a9e43945"
    CON_ROLLBACK = "320899d675059182509a62b67d122afd2fdc54b08c59b2053a684d88fc8b55f2"

    def setUp(self):
        super().setUp()
        patcher = ld_as_set()
        patcher.start()
        self.addCleanup(patcher.stop)

    def pinned_before(self):
        with pre_ld():
            self.assertEqual(money_digest(), self.BEFORE)
            grant = self.enabled()
        self.assertEqual(money_digest(), self.LD)
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.BEFORE)
        return grant

    def test_the_owners_deploy_re_ratifies_it_at_the_houses_start(self):
        grant = self.pinned_before()
        self.assertFalse(grant.allows_live(2), "real entries are held until it is ratified")
        out = self.standing(grant, release="r-ld", rows=owner_deploy(self.clock() - 60, release="r-ld"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertIn(f"money digest {self.BEFORE[:12]} -> {self.LD[:12]}", grant.ratifications()[-1]["why"])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.LD)
        self.assertTrue(grant.allows_live(2))

    def test_the_updater_alone_never_ratifies_it(self):
        grant = self.pinned_before()
        out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))

    def test_the_con_only_rollback_is_ratified_on_the_owners_deploy_of_it(self):
        grant = self.pinned_before()
        self.standing(grant, release="r-ld", rows=owner_deploy(self.clock() - 60, release="r-ld"))
        self.clock.advance(HOUR)
        rollback = {"loss_basis": "gross", "max_open": 3, "demotion": "dm0", "loss_total_usd": "400",
                    "loss_window_sessions": 2000}
        with patch.dict(CONSTITUTION["options_money"]["probe"], rollback):
            self.assertEqual(money_digest(), self.CON_ROLLBACK)
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-ld-con", rows=owner_deploy(self.clock() - 60, release="r-ld-con"))
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.CON_ROLLBACK)
            self.assertTrue(grant.allows_live(2))


class TheProbeTotal800(StandingCase):
    """THE PROBE TOTAL AT $800 (Oct 10, 2026; PREREG-T, under the owner's goal as re-set on Oct 9, item 4):
    `loss_total_usd` "400" -> "800" moves the money digest from release L-D's 0310779c to fdf2ac7c (no fingerprint
    move). A grant pinned on 0310779c holds nothing after the deploy until the standing grant re-ratifies it at the
    House's start, on the owner's release change only. Its rollback (`loss_total_usd` "400") is L-D's digest again,
    ratified the same way on the owner's deploy of it."""

    LD = TheReleaseLD.LD
    T800 = "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7"

    def pinned_before(self):
        with ld_as_set():
            self.assertEqual(money_digest(), self.LD)
            grant = self.enabled()
        self.assertEqual(money_digest(), self.T800)
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.LD)
        return grant

    def test_the_owners_deploy_re_ratifies_it_at_the_houses_start(self):
        grant = self.pinned_before()
        self.assertFalse(grant.allows_live(2), "real entries are held until it is ratified")
        out = self.standing(grant, release="r-t800", rows=owner_deploy(self.clock() - 60, release="r-t800"))
        self.assertEqual((out["action"], out["triggers"]), ("ratified", ["digest"]))
        self.assertIn(f"money digest {self.LD[:12]} -> {self.T800[:12]}", grant.ratifications()[-1]["why"])
        self.assertEqual(grant.current()["policy"]["constitution_digest"], self.T800)
        self.assertTrue(grant.allows_live(2))

    def test_the_updater_alone_never_ratifies_it(self):
        grant = self.pinned_before()
        out = self.standing(grant, release="main-abcdef123456", rows=updater_deploy(self.clock() - 60))
        self.assertEqual(out["action"], "refused")
        self.assertFalse(grant.allows_live(2))
        self.assertEqual(grant.ratifications(), [])

    def test_its_rollback_is_lds_digest_ratified_on_the_owners_deploy_of_it(self):
        grant = self.pinned_before()
        self.standing(grant, release="r-t800", rows=owner_deploy(self.clock() - 60, release="r-t800"))
        self.clock.advance(HOUR)
        with ld_as_set():
            self.assertEqual(money_digest(), self.LD)
            self.assertFalse(grant.allows_live(2))
            out = self.standing(grant, release="r-t400", rows=owner_deploy(self.clock() - 60, release="r-t400"))
            self.assertEqual(out["action"], "ratified")
            self.assertEqual(grant.current()["policy"]["constitution_digest"], self.LD)
            self.assertTrue(grant.allows_live(2))


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

    def test_the_rollback_drills_copy_is_never_an_owner_change(self):
        """Its promote row lands before the drill's own `stage: "drill"` row, and the House started from the copy runs
        the grant job at once: the copy's rows are told apart by the copy's name."""
        drill = owner_deploy(400.0, release="drill-20261003T150000Z")
        rows = owner_deploy(100.0, release="a") + drill + [
            {"ts": 410.0, "deploy": drill[0]["deploy"], "release": "drill-20261003T150000Z", "stage": "rollback", "ok": True,
             "from": "drill-20261003T150000Z", "to": "a"},
            {"ts": 420.0, "deploy": "rollback@420", "release": "drill-20261003T150000Z", "stage": "rollback", "ok": True,
             "from": "drill-20261003T150000Z", "to": "a"}]
        self.assertEqual(owner_change(rows, 0.0)["release"], "a")
        self.assertIsNone(owner_change(rows, 150.0))


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

    def test_a_moved_digest_without_the_owner_fails_the_occurrence_and_changes_nothing(self):
        grant = self.enabled()
        ctx, calls = self.ctx(deploy_rows=updater_deploy(self.clock() - 60), release_id="main-abcdef123456")
        with moved_digest():
            with self.assertRaises(job.GrantRefused) as caught:
                job.run(ctx)
            self.assertIn("refused", str(caught.exception))
            self.assertIn("no owner's deploy", str(caught.exception))
            self.assertIn("triggers digest", str(caught.exception))
            self.assertFalse(grant.current()["active"])
        self.assertEqual(calls.alerts, [], "the runner raises the failed occurrence's warning")
        self.assertEqual(grant.ratifications(), [])

    def test_a_refused_occurrence_carries_no_figures(self):
        self.enabled()
        ctx, calls = self.ctx(_funding=[deposit(self.clock() - 60, amount="1234.56")], _equity="42.17")
        with self.assertRaises(job.GrantRefused) as caught:
            job.run(ctx)
        text = str(caught.exception) + json.dumps(calls.alerts)
        self.assertIn("smallest real stake", text)
        for figure in ("42.17", "1234.56", "5500", "700"):
            self.assertNotIn(figure, text)

    def test_unreadable_reads_fail_closed(self):
        grant = self.enabled()
        ctx, calls = self.ctx(_funding=OSError("gateway down"))
        with self.assertRaisesRegex(job.GrantRefused, "funding cannot be read"):
            job.run(ctx)
        self.assertEqual(calls.equity, 0)
        ctx, calls = self.ctx(_funding=[deposit(self.clock() - 60)], _equity=OSError("gateway down"))
        with self.assertRaisesRegex(job.GrantRefused, "equity cannot be read.*triggers deposit"):
            job.run(ctx)
        ctx, calls = self.ctx(config={"live_trading": {}})
        with self.assertRaisesRegex(job.GrantRefused, "ceiling cannot be read"):
            job.run(ctx)
        self.assertEqual(grant.ratifications(), [])

    def test_a_moved_digest_answered_without_the_funding_read_is_degraded_and_warned(self):
        self.enabled()
        ctx, calls = self.ctx(_funding=OSError("gateway down"), deploy_rows=owner_deploy(self.clock() - 60), release_id="r-x")
        with moved_digest():
            out = job.run(ctx)
        self.assertEqual((out["status"], out["action"], out["triggers"]), ("ok", "ratified", ["digest"]))
        self.assertIn("funding cannot be read", out["degraded"])
        self.assertEqual([level for level, _ in calls.alerts], ["warning"])
        self.assertIn("a deposit waits", calls.alerts[0][1])

    def test_no_root_fails_the_occurrence(self):
        with self.assertRaises(job.GrantRefused):
            job.run({})
        self.assertEqual(job.run(SimpleNamespace(house=SimpleNamespace(root=self.root)))["action"], "none")

    def wp2_context(self, base):
        """Shaped like the ops runner's `Context` (`league/ops/context.py`): `release` is the release's directory, and
        whatever else it carries is never a money input of this job."""
        alerts = []

        def poisoned():
            raise AssertionError("a context attribute was read as a money input")

        ctx = SimpleNamespace(job="grant", root=self.root, base=base, release=base / "releases" / "main-0123456789ab",
                              clock=self.clock, config={"live_trading": {"ceiling_usd": "9999"}}, read_equity=poisoned,
                              read_funding=poisoned, deploy_rows=owner_deploy(self.clock() - 60, release="ctx-rows"),
                              alerts=alerts, alert=lambda level, text: alerts.append({"level": level, "text": text}))
        return ctx

    def own_reads(self, *, equity=EQUITY, funding=()):
        stack = ExitStack()
        stack.enter_context(patch.object(job, "own_config", lambda: {"live_trading": {"ceiling_usd": CEILING}}))
        stack.enter_context(patch.object(job, "read_equity_now", lambda config: D(equity)))
        stack.enter_context(patch.object(job, "_gateway_funding", lambda config: (lambda after: list(funding))))
        return stack

    def test_under_the_runners_context_the_money_inputs_are_the_jobs_own(self):
        grant = self.enabled()
        base = Path(self.dir.name)
        (base / "releases" / "r-owner-3").mkdir(parents=True)
        os.symlink("releases/r-owner-3", base / "current")
        (base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in owner_deploy(self.clock() - 60, release="r-owner-3")))
        ctx = self.wp2_context(base)
        with moved_digest(), self.own_reads(equity="6000"):
            out = job.run(ctx)
            self.assertEqual((out["status"], out["action"]), ("ok", "ratified"))
            self.assertEqual(out["release"], "r-owner-3", "the release id from <base>/current, not the context's path")
            self.assertIsInstance(out["release"], str)
            self.assertEqual(grant.current()["policy"]["ceiling_usd"], "5500.00", "the ceiling from the job's own config")
            self.assertIn("r-owner-3", grant.ratifications()[-1]["why"])

    def test_under_the_runners_context_an_unknown_release_refuses(self):
        grant = self.enabled()
        base = Path(self.dir.name)
        (base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in owner_deploy(self.clock() - 60)))
        with moved_digest(), self.own_reads():
            with self.assertRaisesRegex(job.GrantRefused, "release is unknown"):
                job.run(self.wp2_context(base))
            self.assertFalse(grant.current()["active"])

    @skipUnless(importlib.util.find_spec("league.ops.context") and importlib.util.find_spec("league.ops.registry"),
                "the ops runner (WP2) is not in this tree")
    def test_the_ops_runner_stores_a_refusal_as_failed(self):
        from league.ops.__main__ import run_job
        from league.ops.context import Context

        self.enabled()
        base = Path(self.dir.name)
        with moved_digest(), self.own_reads():
            ctx = Context("grant", root=self.root, due_at=self.clock(), base=base, clock=self.clock)
            result = run_job("grant", root=self.root, due_at=self.clock(), base=base, ctx=ctx)
        self.assertEqual(result["status"], "failed")
        self.assertIn("GrantRefused", result["error"])

    def test_the_schedule_the_registry_reads(self):
        self.assertEqual((job.NAME, job.EVERY_SECONDS, job.AT_START), ("grant", 3600, True))


class ThePolicyStaysTheOwners(TestCase):
    def test_policy_is_unchanged_by_the_standing_grant(self):
        # The owner's --ratify and the standing grant write the same policy for the same inputs.
        self.assertEqual(policy(EQUITY, CEILING)["capital_usd"], "700.00")
        self.assertEqual(policy(EQUITY, CEILING)["constitution_digest"], money_digest())
