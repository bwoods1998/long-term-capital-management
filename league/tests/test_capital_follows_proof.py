"""Capital follows proof: the forward-first run's money rules M1-M5 and the Alpaca maker record, M6 (Sept 25, 2026).

The run's plan (docs/goals/LTCM_FORWARD_FIRST.md, "C. Capital follows proof" and the closed "Money-rule bounds" table)
and the main session's verification of the one proven family (the run record's "The proven sports family, verified",
07:11Z Sept 25): its 25 events lie on 3 slate dates inside one five-day MLB under-regime, the same program lost 12-14% a
dollar over Sept 4-24 on Kalshi's public record, and one observation per date gives an 80% bound of -0.0665 -- a count of
events cannot tell a regime from an edge.

- M1: the family swing's entry look at 10 real settlements (15 before; every 5 more, at 90%), and at every look --
  entry, hold, doubling -- the real events must span 5 distinct settlement dates, each event's own date. The auditor's
  packet is prepared ahead of a look (`game.json` `audit.pre_pack`, 8) so a passing look is not delayed by its audit.
- M2: a PROBE may enter as a taker (one position at its cap); a bunt or a swing stays post-only until the family's
  taker record is positive, counted from 5 taker events (`taker_proof_min`); the book's refusal names the band.
- M3: a proven family's practice member with a closed practice trade and W_paper >= 1 is seated on the family's proof,
  best W_paper first, up to `economy.proven_family_members` seats, only on a proof spanning 5 dates and only running
  the proven code.
- M4: a stock or ETF program's real stake at Alpaca is $50, probe or bunt (crypto stays $25, options $80).
- M5: a hold turns on the record since the demotion's 80% lower bound, one observation a block period, over 6.
- M6: an Alpaca fill carries its own role (`liquidity_role`), maker for a limit that was not marketable when placed.
"""

import copy
import json
import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ltcm.broker import Instrument

from league import allocator, families
from league.book import Book, Limits
from league.constitution import CONSTITUTION, digest, money_digest
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock
from league.tests.test_allocator import HouseCaseReal, IDLE
from league.tests.test_book import BookCase
from league.tests.test_families import GATE, WIN, LOSS, AtRiskCase, events, real_record
from league.tests.test_family_probe import READY, ForwardBlocks
from league.tests.test_promotion_on_proof import KALSHI_IDLE, KalshiHouse, canned, ev
from league.tests.test_real_entry_rules import RealEntryCase, event, rules as entry_rules

D = Decimal
R = CONSTITUTION["allocator"]


def dated(n, per_day=1, start=1):
    """First close -> its own settlement date, `per_day` events a date (September 2026)."""
    return {i + 1: f"2026-09-{start + i // per_day:02d}" for i in range(n)}


# ------------------------------------------------------------------------------------------ the rows
class TheRows(unittest.TestCase):
    """Each rule is a row of the run's closed money table, with the value the main session chose inside it."""

    def test_the_values_inside_the_table(self):
        swing = R["family_swing"]
        self.assertEqual((swing["min_real_settlements"], swing["min_distinct_dates"]), (10, 5))  # M1: 10-15; 5 dates
        self.assertEqual((swing["entry_every"], D(swing["entry_confidence"])), (5, D("0.9")))  # unchanged
        self.assertEqual((R["real_entry_liquidity"], R["taker_proof_min"]), ("probe_may_take", 5))  # M2: 5-10
        self.assertEqual(R["proven_family_member"], {"min_practice_closed": 1, "min_w_paper": "1.0", "min_distinct_dates": 5,
                                                     "same_code": True})  # M3
        self.assertEqual(R["probe_bunt_usd"]["alpaca_equity"], "50")  # M4: $25-60
        self.assertTrue(D("25") <= D(R["probe_bunt_usd"]["alpaca_equity"]) <= D("60"))
        self.assertEqual((R["probe_bunt_usd"]["alpaca"], R["option_bunt_usd"]), ("25", "80"))  # crypto and options unchanged
        self.assertEqual(R["family_probe"], {"losing_min_blocks": 6, "reseat": "bound_since_demotion", "reseat_confidence": "0.8"})
        self.assertEqual(R["max_event_share"], "0.25")  # not this run's (the Kalshi-scale run's table)
        with open("league/game.json") as f:
            game = json.load(f)
        self.assertEqual((game["audit"]["pre_pack"], game["audit_bounds"]["pre_pack"]), (8, [5, 9]))
        self.assertEqual(game["economy"]["proven_family_members"], 4)  # stays 4 (the main session, 07:11Z)

    def test_every_rule_moves_the_money_digest_the_grant_pins(self):
        for path in (("family_swing", "min_real_settlements"), ("family_swing", "min_distinct_dates"), ("taker_proof_min",),
                     ("real_entry_liquidity",), ("proven_family_member",), ("proven_family_member", "min_distinct_dates"),
                     ("proven_family_member", "same_code"), ("probe_bunt_usd", "alpaca_equity"), ("family_probe", "reseat"),
                     ("family_probe", "reseat_confidence")):
            changed = copy.deepcopy(CONSTITUTION)
            node = changed["allocator"]
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            self.assertNotEqual(money_digest(changed), money_digest(), path)
            self.assertNotEqual(digest(changed), digest(), path)

    def test_the_pre_pack_dial_stays_in_its_bounds(self):
        from league.economy import check_bounds

        with open("league/game.json") as f:
            game = json.load(f)
        check_bounds(game)
        for value in (4, 10):
            game["audit"]["pre_pack"] = value
            with self.assertRaisesRegex(ValueError, "audit.pre_pack"):
                check_bounds(game)


# ------------------------------------------------------------------------------------------ M1: dates
class EventDays(unittest.TestCase):
    def test_an_event_is_dated_by_its_own_date_code(self):
        day = families.event_day
        self.assertEqual(day("KXMLBTOTAL-26SEP241915CINATL", 1790000000.0), "2026-09-24")  # the slate, not the UTC settle
        self.assertEqual(day("KXHIGHNY-26SEP24", None), "2026-09-24")
        self.assertEqual(day("KXBTCD-26SEP2401", None), "2026-09-24")
        self.assertEqual(day("kxmlbhit-26sep222140laaath", None), "2026-09-22")
        # No date code (an Alpaca trade's key, a monthly series): the UTC date of its last close, else no date at all.
        noon = 1790337600.0  # 12:00Z Sept 25
        self.assertEqual(day("alpaca:m1:17", noon), "2026-09-25")
        self.assertEqual(day("KXCPI-26SEP", noon), "2026-09-25")
        self.assertIsNone(day("alpaca:m1:17", None))

    def test_a_night_slate_is_one_date_though_it_settles_on_two(self):
        """The real Sept 24 slate on the T0 snapshot: one event settled on Sept 24 UTC and five on Sept 25."""
        before_midnight, after = 1790288400.0, 1790302800.0  # 22:20Z Sept 24, 02:20Z Sept 25
        self.assertEqual({families.event_day("KXMLBTOTAL-26SEP241420MIACHC", before_midnight),
                          families.event_day("KXMLBTOTAL-26SEP242140LAASEA", after)}, {"2026-09-24"})


class EntryLooksWithDates(unittest.TestCase):
    def setUp(self):
        self.rule = families.swing_rule()

    def test_the_looks_are_10_15_20(self):
        c = lambda n: families.entry_checkpoint(n, self.rule)  # noqa: E731
        self.assertEqual([c(n) for n in (9, 10, 14, 15, 19, 20, 25)], [None, 10, 10, 15, 15, 20, 25])

    def test_ten_events_on_two_slates_do_not_pass_whatever_their_bound(self):
        """The sports family's first 10 real events lay on 2 slate dates (Sept 23 and 24)."""
        wins = [WIN] * 10
        look = families.entry_look(events(wins), self.rule, gate=GATE, days=dated(10, per_day=5))
        self.assertEqual((look["checkpoint"], look["dates"]), (10, 2))
        self.assertGreater(look["honest_bound"], 0)
        self.assertFalse(look["ready"])
        look = families.entry_look(events(wins), self.rule, gate=GATE, days=dated(10, per_day=2))
        self.assertEqual((look["dates"], look["ready"]), (5, True))

    def test_the_look_counts_the_dates_of_its_own_first_events(self):
        """Events 11-15 on new dates do not rescue the look at 10: it stands on its first 10 (2 dates) until the look
        at 15, which reads the first 15."""
        days = {**dated(10, per_day=5), **{i: f"2026-09-{i:02d}" for i in range(11, 15)}}
        look = families.entry_look(events([WIN] * 14), self.rule, gate=GATE, days=days)
        self.assertEqual((look["checkpoint"], look["dates"], look["ready"], look["next_checkpoint"], look["dates_so_far"]),
                         (10, 2, False, 15, 6))
        days[15] = "2026-09-15"
        look = families.entry_look(events([WIN] * 15), self.rule, gate=GATE, days=days)
        self.assertEqual((look["checkpoint"], look["dates"], look["ready"]), (15, 7, True))

    def test_the_hold_and_so_every_doubling_need_the_dates(self):
        """A swinging family stays -- and its ramp doubles -- only while `swing_ready` holds on the whole real record."""
        self.assertFalse(families.swing_ready(real_record(n=30, bound=0.5, dates=4), self.rule))
        self.assertTrue(families.swing_ready(real_record(n=30, bound=0.5, dates=5), self.rule))
        self.assertEqual(families.next_state("swing", proven=True, entry=True, hold=False, approved=True), "proven")

    def test_without_the_key_no_dates_are_asked(self):
        with patch.dict(CONSTITUTION["allocator"]["family_swing"]):
            del CONSTITUTION["allocator"]["family_swing"]["min_distinct_dates"]
            rule = families.swing_rule()
            self.assertEqual(rule["min_distinct_dates"], 0)
            self.assertTrue(families.entry_look(events([WIN] * 10), rule, gate=GATE)["ready"])
            self.assertTrue(families.swing_ready(real_record(n=10, dates=0), rule))


class TheAgentLevelSwingAsksTheDatesToo(KalshiHouse):
    """M1's "every swing look" holds for the agent-level swing (`swing_at`) as for the family's: at T0 meriwether-h2d625d
    stood at E 2.0725 on 11 real events of 2 slates, its swing audit vetoed at 01:20Z, its cooldown ending about 23:20Z."""

    def test_the_rule(self):
        p = allocator._params()
        ready = dict(rung=2, e=2.0725, w_paper=1.4261, w_real=1.7355, real_trades=11, family_proven=True)
        self.assertEqual(allocator.target_band(ev(**ready), p)[0], "swing")
        band, why = allocator.target_band(ev(**ready, swing_dates=(2, 5)), p)
        self.assertEqual(band, "bunt")
        self.assertIn("its family's real record spans 2 distinct settlement dates: every swing asks 5", why)
        band, why = allocator.target_band(ev(**dict(ready, rung=3), swing_dates=(4, 5)), p)
        self.assertEqual(band, "bunt")
        self.assertIn("a swing holds on 5", why)

    def test_no_swing_audit_until_the_real_record_spans_the_dates(self):
        room = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"})
        room.start()
        self.addCleanup(room.stop)
        proof = {**canned("weather-favorites", proven=True, n=25, bound=0.03), "dates": 3, "real_n": 11}  # the sports family at T0
        self.families["weather-favorites"] = {**proof, "real": {**families.empty_record("weather-favorites", "kalshi")["real"], "n": 11, "dates": 2}}
        a = self.agent("meriwether")
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        swing_ready = {a.id: dict(e=2.0725, w_paper=1.4261, w_real=1.7355, real_trades=11, paper_trades=19, paper_settled=19)}
        with self.evidence_of(swing_ready):
            self.tick()
        self.house.wait(5)
        self.assertEqual((self.house.evaluator.rung(a.id), self.auditor.seen), (2, []))
        self.families["weather-favorites"] = {**proof, "real": {**self.families["weather-favorites"]["real"], "n": 20, "dates": 5}}
        self.house.allocator._families.clear()
        with self.evidence_of(swing_ready):
            self.tick()
        self.house.wait(5)
        self.assertEqual(self.auditor.seen, [a.id])  # on 5 dates the swing's audit is asked


class DatesOnTheLedger(AtRiskCase):
    """`family_record` dates every observation: the pooled record's dates, the real record's, and the entry look's."""

    def slate(self, date_code, games, *, book="kalshi", agent="m1", won=True):
        for g in range(games):
            ticker = f"KXMLBTOTAL-{date_code}1840G{g:02d}{self.n:03d}-7"
            self.n += 1
            self.buy(ticker, 10, "0.50", agent=agent, book=book, liquidity="maker")
            self.settle(ticker, "5" if won else "-5", agent=agent, book=book)

    def setUp(self):
        super().setUp()
        self.n = 0
        self.member("m1")
        self.stake(30, agent="m1", book="kalshi")
        self.stake(200, agent="m1", book="kalshi-shadow")

    def test_ten_real_events_on_two_slates_are_two_dates_and_no_entry(self):
        self.slate("26SEP23", 5)
        self.slate("26SEP24", 5)
        self.slate("26SEP22", 3, book="kalshi-shadow")
        record = self.record()
        self.assertEqual((record["real"]["n"], record["real"]["dates"], record["dates"], record["n"]), (10, 2, 3, 13))
        look = record["real"]["entry"]
        self.assertEqual((look["checkpoint"], look["dates"]), (10, 2))
        self.assertGreater(look["honest_bound"], 0)
        self.assertFalse(look["ready"])
        self.assertFalse(families.entry_ready(record, families.swing_rule()))
        self.assertFalse(families.swing_ready(record, families.swing_rule()))
        row = families.row_of(record, {"state": "proven"}, swing=None, members_real=1, stake_usd=D("30"))
        self.assertEqual((row["dates"], row["real"]["dates"], row["real"]["entry"]["dates"]), (3, 2, 2))

    def test_five_slates_make_the_look_at_10(self):
        for code in ("26SEP20", "26SEP21", "26SEP22", "26SEP23", "26SEP24"):
            self.slate(code, 2)
        record = self.record()
        self.assertEqual((record["real"]["dates"], record["real"]["entry"]["dates"], record["real"]["entry"]["ready"]), (5, 5, True))
        self.assertTrue(families.entry_ready(record, families.swing_rule()))


# ------------------------------------------------------------------------------------------ M1: the pre-pack
def ahead(n, *, dates_so_far=5, upcoming=10, bound=0.05):
    """A proven family's record `n` real settlements into the count before its look at `upcoming`."""
    rec = real_record(n=n, bound=bound, entry=False)
    rec["real"]["entry"] = {"checkpoint": None if upcoming == 10 else upcoming - 5, "next_checkpoint": upcoming, "confidence": 0.9,
                            "honest_bound": None, "ready": False, "dates": None, "dates_so_far": dates_so_far, "min_dates": 5}
    return rec


class PrePack(KalshiHouse):
    """M1 (C1): the auditor's packet for the swing's entry is prepared at the 8th real settlement (`audit.pre_pack`), so
    the look at 10 is not delayed by its audit; an approval so prepared lapses at a look that does not pass."""

    def setUp(self):
        super().setUp()
        room = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"})
        room.start()
        self.addCleanup(room.stop)
        self.verdicts = []

        def audit(agent, verdict, **kwargs):
            self.verdicts.append(verdict)
            row = {"approve": self.auditor.approve, "summary": "test", "family_swing": verdict.numbers.get("family_swing")}
            self.house.ledger.append("audit.verdict", row, agent=agent.id)
            return row

        self.auditor.audit = audit
        self.families["weather-favorites"] = real_record(n=5, bound=-0.5)
        self.a = self.agent("kay")
        self.table = {self.a.id: dict(e=1.10, w_paper=1.21, w_real=1.0, paper_trades=6, paper_settled=6)}
        self.rebalance()
        self.assertEqual(self.house.books["kalshi"].account(self.a.id).staked, D("30"))

    def rebalance(self):
        with self.evidence_of(self.table):
            return self.house.allocator.rebalance()

    def audits(self):
        return self.house.allocator.state.get("family_audits", {}).get("weather-favorites@kalshi") or {}

    def test_the_packet_is_prepared_at_the_8th_and_the_look_at_10_enters_at_once(self):
        self.families["weather-favorites"] = ahead(7)
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(self.verdicts, [])  # 7: not yet
        self.families["weather-favorites"] = ahead(8)
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)
        verdict = self.verdicts[0]
        self.assertEqual(verdict.numbers["pre_pack"], {"look": 10, "real_n": 8, "dates": 8})
        self.assertIn("prepared AHEAD of that look (game.json audit.pre_pack)", verdict.reason)
        self.assertIn("on at least 5 distinct settlement dates", verdict.reason)
        self.rebalance()
        self.assertEqual((self.audits()["status"], self.audits()["approve"], self.audits()["look"]), ("prepared", True, 10))
        self.assertEqual(self.house.allocator.family_state(self.a), "proven")  # approved ahead: no look has passed
        self.families["weather-favorites"] = real_record(n=10, bound=0.05)  # the look at 10 passes
        self.rebalance()
        self.assertEqual(self.house.allocator.family_state(self.a), "swing")  # the same pass: no audit to wait for
        self.assertEqual(len(self.verdicts), 1)
        self.assertEqual(self.house.books["kalshi"].account(self.a.id).staked, D("60.00"))
        self.assertEqual(self.audits()["status"], "done")  # it licensed its look: the entry's approval now

    def test_a_prepared_approval_licenses_nothing_to_a_release_without_the_pre_pack(self):
        """The Deploy B money review (Sept 25, 2026): Deploy A reads an audit "done" and approved as its license at ANY
        passing look (its `_swing_approval` reads status and approve only), and its look has no dates gate. An approval
        prepared ahead of a look is kept "prepared" until that look passes, so after a rollback A asks its own auditor
        (its `_request_family_audit` waits only on "running" and "done") instead of entering on it."""
        self.families["weather-favorites"] = ahead(8)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        audit = self.audits()
        a_licensed = audit.get("status") == "done" and audit.get("approve") is True  # Deploy A's `_swing_approval`
        a_waits = audit.get("status") in ("running", "done")  # Deploy A's `_request_family_audit`
        self.assertEqual((a_licensed, a_waits), (False, False))
        # A restart that finds the audit's own row on the ledger keeps it prepared (`_family_verdict_on_ledger`).
        running = {**audit, "status": "running"}
        found = self.house.allocator._family_verdict_on_ledger("weather-favorites@kalshi", running)
        self.assertEqual((found["status"], found["approve"], found["look"]), ("prepared", True, 10))

    def test_a_veto_ahead_of_its_look_is_asked_again_when_the_look_passes(self):
        """The Deploy B money review (Sept 25, 2026): a veto of the packet prepared at the 8th settlement held the look at
        10, when it passed, for the audit's whole cooldown: the pre-pack delayed the look it was meant to hurry."""
        self.auditor.approve = False
        self.families["weather-favorites"] = ahead(8)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual((self.audits()["status"], self.audits()["approve"]), ("prepared", False))
        self.families["weather-favorites"] = ahead(9)  # still ahead of its look: the veto waits out its cooldown
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)
        self.auditor.approve = True
        self.families["weather-favorites"] = real_record(n=10, bound=0.05)  # the look at 10 passes: asked again at once
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 2)
        self.assertNotIn("pre_pack", self.verdicts[1].numbers)
        self.rebalance()
        self.assertEqual(self.house.allocator.family_state(self.a), "swing")

    def test_an_approval_prepared_for_a_look_that_does_not_pass_lapses(self):
        self.families["weather-favorites"] = ahead(9)
        self.rebalance()
        self.house.wait(5)
        self.rebalance()
        self.assertEqual((self.audits()["status"], self.audits()["look"]), ("prepared", 10))
        self.families["weather-favorites"] = real_record(n=10, bound=-0.01, entry=False)  # the look at 10 fails
        self.rebalance()
        self.assertEqual(self.audits()["status"], "lapsed")
        self.assertIn("prepared for the look at 10 real settlements, and the look at 10 did not pass", self.audits()["why"])
        self.families["weather-favorites"] = real_record(n=12, bound=0.05, entry=False)  # 12: no packet for 15 yet
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)
        self.families["weather-favorites"] = ahead(13, upcoming=15, dates_so_far=4)  # 13 for the look at 15
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 2)
        self.assertEqual(self.verdicts[1].numbers["pre_pack"]["look"], 15)
        self.rebalance()
        self.families["weather-favorites"] = real_record(n=15, bound=0.05)
        self.rebalance()
        self.assertEqual(self.house.allocator.family_state(self.a), "swing")

    def test_no_packet_for_a_look_whose_dates_cannot_be_met(self):
        """The sports family at T0: its first 8 real events on 2 slate dates cannot span 5 by the 10th."""
        self.families["weather-favorites"] = ahead(8, dates_so_far=2)
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(self.verdicts, [])
        self.families["weather-favorites"] = ahead(9, dates_so_far=4)  # four dates and one more event: it can
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(len(self.verdicts), 1)

    def test_without_the_dial_the_audit_waits_for_a_passing_look(self):
        del self.house.game["audit"]["pre_pack"]
        self.families["weather-favorites"] = ahead(9)
        self.rebalance()
        self.house.wait(5)
        self.assertEqual(self.verdicts, [])


# ------------------------------------------------------------------------------------------ M2: probes may take
class ProbeMayTake(RealEntryCase):
    """The book: under "probe_may_take" the allocator's `may_take` decides, and the refusal names the band."""

    TICKER = "KXMLBTOTAL-26SEP251840TBPHI-8"

    def setUp(self):
        super().setUp()
        self.seat("kay", usd="10", position="2.00", order="2.00")
        self.quote(self.TICKER, "0.48", "0.50")
        self.inst = event(self.TICKER, "no", self.venue)
        # BookCase takes the real book's entry keys out for its tests; this one puts the live rule back. Stopped in
        # tearDown, BEFORE BookCase restores the constitution (a patch restores what it found when it started).
        self._live = patch.dict(CONSTITUTION["allocator"], {"real_entry_liquidity": "probe_may_take", "taker_proof_min": 5})
        self._live.start()

    def tearDown(self):
        self._live.stop()
        super().tearDown()

    def test_a_probe_takes_the_price_inside_its_position_cap(self):
        self.taker_record = {"family": "sports-central-run-under", "positive": False, "n": 3, "mean_log": 0.1, "bound": None,
                             "band": "probe", "may_take": True, "proof_min": 5}
        out = self.book.submit([self.intent("kay", self.inst, "buy", "4")])[0]
        self.assertEqual(out.status, "filled", out.detail)  # $2.00 at the ask: its whole position
        more = self.book.submit([self.intent("kay", self.inst, "buy", "2")])[0]
        self.assertEqual(more.status, "refused")  # one position at its cap: position_share_event of the stake
        self.assertNotIn("post-only", more.detail)

    def test_a_probe_takes_one_position_in_all_not_one_on_every_event(self):
        """The Deploy B money review (Sept 25, 2026): the per-market cap alone let this $10 probe take $2 on each of
        KXMLBTOTAL-26SEP251840TBPHI-8, -1905PITDET-8 and -2010TEXMIN-8 (all three filled), and five events would take its
        whole stake at the ask. A probe takes one position at its cap, in all; making is not taking."""
        self.taker_record = {"family": "sports-central-run-under", "positive": False, "n": 3, "mean_log": 0.1, "bound": None,
                             "band": "probe", "may_take": True, "proof_min": 5, "probe_cap_usd": "2.00"}
        self.assertEqual(self.book.submit([self.intent("kay", self.inst, "buy", "4")])[0].status, "filled")
        games = ("KXMLBTOTAL-26SEP251905PITDET-8", "KXMLBTOTAL-26SEP252010TEXMIN-8")
        for game in games:
            self.quote(game, "0.48", "0.50")
        out = self.book.submit([self.intent("kay", event(games[0], "no", self.venue), "buy", "2")])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("a probe takes the price for one position at its cap: it holds or bids $2.", out.detail)
        self.assertIn("over its $2.00", out.detail)
        resting = self.bid("kay", games[0], "2", "0.48")
        self.assertEqual(resting.status, "resting", resting.detail)  # a post-only bid is not taking
        self.taker_record = {**self.taker_record, "positive": True, "n": 5, "bound": 0.01}  # the family's taker proof
        self.assertEqual(self.book.submit([self.intent("kay", event(games[1], "no", self.venue), "buy", "2")])[0].status, "filled")

    def test_a_bunt_does_not_take_without_the_familys_taker_proof(self):
        self.taker_record = {"family": "sports-central-run-under", "positive": False, "n": 3, "mean_log": 0.1, "bound": None,
                             "band": "bunt", "may_take": False, "proof_min": 5}
        out = self.book.submit([self.intent("kay", self.inst, "buy", "2")])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("a real entry by a bunt on sports-central-run-under must be a post-only limit until the family's pooled "
                      "taker record is positive (3 taker settlements; positive from 5 with the bound above zero; a probe may take)",
                      out.detail)
        resting = self.bid("kay", self.TICKER, "2", "0.48")
        self.assertEqual(resting.status, "resting", resting.detail)
        self.taker_record = {**self.taker_record, "positive": True, "may_take": True, "n": 5, "bound": 0.01}
        self.assertEqual(self.book.submit([self.intent("kay", self.inst, "buy", "1")])[0].status, "filled")

    def test_an_unmeasured_family_is_refused_whatever_the_rule(self):
        self.taker_record = None
        out = self.book.submit([self.intent("kay", self.inst, "buy", "2")])[0]
        self.assertEqual(out.status, "refused")
        self.assertIn("no pooled taker record is measured", out.detail)

    def test_the_entry_rules_say_the_rule_in_force(self):
        self.assertEqual(self.book.entry_rules()["real_entry_liquidity"], "probe_may_take")


class TakerRecordForTheBook(KalshiHouse):
    """The allocator's `family_taker`: a probe may take; a bunt only on its family's taker proof."""

    def test_a_probe_takes_only_as_a_probe(self):
        """The Deploy B money review (Sept 25, 2026): `may_take` read the band's label alone. A family record that cannot be
        read counts as an unproven family's, so its $30 bunts read "probe" and could take $6 positions (the fallback was
        post-only before M2), and a family that loses its proof leaves its bunts staked by free cash only."""
        a = self.agent("kay")
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)}):
            self.tick()
        alloc = self.house.allocator
        row = alloc.family_taker(a.id)
        self.assertEqual((row["band"], row["may_take"], row["probe_cap_usd"]), ("probe", True, "2.00"))  # $2 of a $10 probe
        with patch.object(allocator, "family_record", side_effect=ValueError("unreadable")):
            alloc._families.clear()
            row = alloc.family_taker(a.id)
        self.assertEqual((row["band"], row["may_take"]), ("probe", False))  # unreadable: post-only, as the alert says
        alloc._families.clear()
        self.house.books["kalshi"].account(a.id).staked = D("30")  # a bunt of a family that lost its proof, still lent $30
        row = alloc.family_taker(a.id)
        self.assertEqual((row["band"], row["may_take"]), ("probe", False))

    def test_may_take_by_band(self):
        a = self.agent("kay")
        with self.evidence_of({a.id: dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        alloc = self.house.allocator
        row = alloc.family_taker(a.id)
        self.assertEqual((row["band"], row["positive"], row["may_take"], row["proof_min"]), ("probe", False, True, 5))
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=12, bound=0.002)
        alloc._families.clear()
        row = alloc.family_taker(a.id)
        self.assertEqual((row["band"], row["may_take"]), ("bunt", False))  # M2: never a bunt without the proof
        self.families["weather-favorites"] = canned("weather-favorites", proven=True, n=12, bound=0.002, taker_positive=True)
        alloc._families.clear()
        self.assertEqual(alloc.family_taker(a.id)["may_take"], True)
        self.assertIsNone(alloc.family_taker(a.id)["probe_cap_usd"])  # a bunt on the proof: no probe's cap
        with patch.dict(CONSTITUTION["allocator"], {"real_entry_liquidity": "maker_unless_family_taker_positive"}):
            self.families["weather-favorites"] = canned("weather-favorites")
            alloc._families.clear()
            self.assertEqual(alloc.family_taker(a.id)["may_take"], False)  # the rollback: probes post-only too


class TakerProofFromFive(AtRiskCase):
    """`taker_proof_min` 5: the family's TAKER record is positive from 5 independent taker events with its honest bound
    above zero (the proof's own 10 before); the maker record and the pooled proof keep 10."""

    def taker_events(self, n, start=0):
        for i in range(start, start + n):
            ticker = f"KXMLBTOTAL-26SEP{i % 28 + 1:02d}1840G{i:02d}-7"
            self.buy(ticker, 10, "0.50", agent="m1", book="kalshi", liquidity="taker")
            self.settle(ticker, "5" if i % 3 else "-2", agent="m1", book="kalshi")

    def test_five_taker_events_prove_the_taker_record(self):
        self.member("m1")
        self.stake(30, agent="m1", book="kalshi")
        self.taker_events(4)
        record = self.record()
        self.assertEqual((record["taker"]["n"], record["taker"]["positive"]), (4, False))
        self.taker_events(1, start=4)
        record = self.record()
        self.assertEqual(record["taker"]["n"], 5)
        self.assertGreater(record["taker"]["honest_bound"], 0)
        self.assertTrue(record["taker"]["positive"])
        self.assertFalse(record["proven"])  # the pooled proof still needs 10
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["taker_proof_min"]
            self.assertFalse(self.record()["taker"]["positive"])  # without the key: the proof's own count


class ThinProofsStakeProbes(KalshiHouse):
    """The Deploy B review (Sept 25, 2026; `Allocator.thin_proof`): a family proven on fewer than M3's 5 distinct settlement
    dates while its real record alone is short of the proof's count stakes its members as probes. C8's re-key of the T0
    snapshot made two single-program 15-minute BTC taker families proven on 2 practice dates, and the first pass seated
    both agents as $30 Kalshi bunts; sports-central-run-under (3 dates, real n 11) keeps its bunt as decided at 07:11Z."""

    READY = dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6)

    def seat(self, **proof):
        self.families["weather-favorites"] = {**canned("weather-favorites", proven=True, n=20, bound=0.0927, taker_positive=True),
                                              **proof}
        a = self.agent("huang")
        with self.evidence_of({a.id: self.READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        return a, self.house.books["kalshi"].account(a.id).staked

    def test_a_practice_proof_on_two_dates_seats_a_probe_not_a_bunt(self):
        a, staked = self.seat(dates=2)  # crypto-15m-btc-15m-taker-momentum-7fd732 on the re-keyed T0 snapshot
        self.assertEqual(staked, D("10"))
        alloc = self.house.allocator
        self.assertTrue(alloc.thin_proof("weather-favorites", "kalshi"))
        self.assertEqual((alloc.tier(a), alloc.rung2_band(a), alloc.family_state(a)), ("probe", "probe", "proven"))
        self.assertEqual(self.promote_row(a)["band_to"], "probe")

    def test_a_real_record_of_the_proofs_count_keeps_the_bunt(self):
        a, staked = self.seat(dates=3, real_n=11)  # sports-central-run-under at T0
        self.assertEqual(staked, D("30"))
        self.assertEqual(self.house.allocator.tier(a), "bunt")

    def test_a_proof_on_five_dates_is_a_bunts(self):
        a, staked = self.seat(dates=5)
        self.assertEqual(staked, D("30"))

    def test_without_the_members_rule_the_proof_alone_decides(self):
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["proven_family_member"]
            a, staked = self.seat(dates=2)
        self.assertEqual(staked, D("30"))


# ------------------------------------------------------------------------------------------ M3: members on the proof
class MembersOnTheProof(KalshiHouse):
    """M3 (C3): a proven family's practice member is seated as a bunt on the family's proof."""

    NEAR = dict(e=1.0018, w_paper=1.0036, w_real=1.0, paper_trades=13, paper_settled=13)  # mcentee-hddb4ae at T0

    def setUp(self):
        super().setUp()
        self.proof = {**canned("weather-favorites", proven=True, n=13, bound=0.001), "dates": 5}
        self.families["weather-favorites"] = self.proof
        self.code = {}
        proven = patch.object(allocator.Allocator, "proven_code",
                              lambda alloc, family, venue: self.code.get(family) or {"code": None, "events": 0, "of": 0, "codes": {}})
        proven.start()
        self.addCleanup(proven.stop)

    def runs(self, agent, family="weather-favorites"):
        self.code[family] = {"code": agent.code_sha256, "events": 13, "of": 13, "codes": {agent.code_sha256: 13}}

    def status(self, agent):
        return (self.house._state.get("promotion_status") or {}).get(agent.id) or {}

    def test_a_proven_familys_member_is_seated_as_a_bunt_without_the_bunt_line(self):
        a = self.agent("mcentee")
        self.runs(a)
        with self.evidence_of({a.id: self.NEAR}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        self.assertEqual(self.house.books["kalshi"].account(a.id).staked, D("30"))  # the proven family's bunt
        row = self.promote_row(a)
        self.assertEqual((row["band_to"], row["rule"]), ("bunt", "allocator.proven_family_member"))
        self.assertIn("seated on its family's proof (allocator.proven_family_member): W_paper 1.0036 on 13 closed practice trades",
                      row["reason_detail"])
        self.assertIn("on 5 distinct dates and it runs the code that entered 13 of them", row["reason_detail"])
        with self.evidence_of({a.id: self.NEAR}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)  # E 1.0018 holds the band (the exit line is 0.8585)

    def test_never_a_member_of_an_unproven_family(self):
        a = self.agent("mcentee")
        self.runs(a)
        self.families["weather-favorites"] = {**canned("weather-favorites", proven=False, n=13, bound=-0.001), "dates": 9}
        with self.evidence_of({a.id: self.NEAR}):
            self.tick(2)
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertNotIn(self.status(a).get("stage"), ("promoted", "family_dates", "family_code"))

    def test_a_proof_on_four_dates_seats_nobody(self):
        """The sports family's pooled proof spans 3 slate dates; the megacaps family's 2 trading dates (T0)."""
        a = self.agent("mcentee")
        self.runs(a)
        self.families["weather-favorites"] = {**self.proof, "dates": 4}
        with self.evidence_of({a.id: self.NEAR}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        status = self.status(a)
        self.assertEqual((status["stage"], status["family_dates"]), ("family_dates", 4))
        self.assertEqual(status["reason"], "its family weather-favorites is proven on 13 independent settlements that span 4 "
                                           "distinct settlement dates: a member is seated on the family's proof once they span 5 "
                                           "(allocator.proven_family_member)")

    def test_only_a_member_running_the_proven_code(self):
        """meriwether-h2d625d-4 rewrote itself into a KXWNBAGAME favourite maker and kept the family's name."""
        a, other = self.agent("mcentee"), self.agent("rewritten")
        self.code["weather-favorites"] = {"code": "f" * 64, "events": 13, "of": 13, "codes": {"f" * 64: 13}}
        with self.evidence_of({a.id: self.NEAR}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)
        self.assertEqual(self.status(a)["stage"], "family_code")
        self.assertIn(f"it runs {a.code_sha256[:8]}, not the family's proven code ffffffff (which entered 13 of its 13 settled "
                      "observations)", self.status(a)["reason"])
        self.code["weather-favorites"] = {"code": None, "events": 6, "of": 13, "codes": {"f" * 64: 6, a.code_sha256: 5}}
        with self.evidence_of({a.id: self.NEAR}):
            self.tick()
        self.assertIn("no one program entered more than half of the family's 13 settled observations", self.status(a)["reason"])
        self.assertEqual(self.house.evaluator.rung(other.id), 1)

    def test_the_lines_of_the_member_itself(self):
        a = self.agent("mcentee")
        self.runs(a)
        for evidence in (dict(self.NEAR, paper_trades=0, paper_settled=0),  # no closed practice trade (-3, -5, -6 at T0)
                         dict(self.NEAR, w_paper=0.9990),  # W_paper under 1.0
                         dict(self.NEAR, e=0.85)):  # under the exit line: a member the exit sent back waits for its own E
            with self.evidence_of({a.id: evidence}):
                self.tick()
            self.assertEqual(self.house.evaluator.rung(a.id), 1, evidence)

    def test_the_seats_best_w_paper_first(self):
        self.house.game["economy"]["proven_family_members"] = 2
        seated = self.agent("anchor")
        a, b = self.agent("mcentee"), self.agent("mcentee-2")
        self.runs(a)
        table = {seated.id: dict(e=1.10, w_paper=1.21, paper_trades=6, paper_settled=6),  # on its own E: a seat taken
                 a.id: dict(self.NEAR, e=1.009, w_paper=1.02), b.id: dict(self.NEAR, e=1.005, w_paper=1.05)}
        self.code["weather-favorites"]["code"] = a.code_sha256  # all three run one program here
        with self.evidence_of(table):
            self.tick()
        self.assertEqual([self.house.evaluator.rung(x.id) for x in (seated, a, b)], [2, 1, 2])  # b's W_paper first
        self.assertEqual(self.status(a)["stage"], "family_seats")
        self.assertEqual(self.status(a)["reason"], "its family weather-favorites already holds 2 of its 2 seats on real money "
                                                   "(allocator.proven_family_member; game.json economy.proven_family_members)")

    def test_without_the_key_the_bunt_line_is_the_only_door(self):
        a = self.agent("mcentee")
        self.runs(a)
        with patch.dict(CONSTITUTION["allocator"]):
            del CONSTITUTION["allocator"]["proven_family_member"]
            with self.evidence_of({a.id: self.NEAR}):
                self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)


class TheProvenCode(unittest.TestCase):
    """`Allocator.proven_code`: the program that entered a majority of the family's settled observations, from the
    ledger's own rows (each observation credited to the code its member ran at the event's first entry)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.agents = {}
        registry = SimpleNamespace(agents=self.agents, get=self.agents.get)
        self.house = SimpleNamespace(ledger=self.ledger, registry=registry, clock=self.clock)
        self.alloc = allocator.Allocator(self.house, self.dir.name)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def born(self, agent, code):
        self.agents[agent] = SimpleNamespace(id=agent, family="sports-central-run-under", venue="kalshi", alive=True)
        self.ledger.append("agent.born", {"code_sha256": code, "family": "sports-central-run-under"}, agent=agent)
        self.ledger.append("book.stake", {"book": "kalshi-shadow", "usd": "200", "note": "t", "real_money": False}, agent=agent)

    def event(self, agent, n):
        for _ in range(n):
            self.games = getattr(self, "games", 0) + 1
            ticker = f"KXMLBTOTAL-26SEP{self.games % 28 + 1:02d}1840G{self.games:03d}-7"  # one game each
            inst = {"asset_class": "event", "symbol": ticker, "venue": "kalshi-shadow", "market_id": ticker, "right": "no", "multiplier": "1"}
            self.ledger.append("book.fill", {"book": "kalshi-shadow", "source": "venue", "side": "buy", "realized": None, "flat": None,
                                             "instrument": inst, "quantity": "10", "price": "0.5", "cash_delta": "-5",
                                             "liquidity": "taker"}, agent=agent)
            self.ledger.append("book.settle", {"book": "kalshi-shadow", "instrument": inst, "pnl": "5", "cost": "5", "payout": "10",
                                               "quantity": "10", "result": "no"}, agent=agent)

    def read(self):
        self.alloc._codes = {}
        self.alloc._tape.refresh(self.ledger)
        return self.alloc.proven_code("sports-central-run-under", "kalshi")

    def test_the_founders_code_and_a_rewrite(self):
        self.born("m1", "a" * 64)
        self.event("m1", 7)
        self.born("m4", "a" * 64)
        self.event("m4", 2)
        self.ledger.append("agent.strategy", {"code_sha256": "b" * 64}, agent="m4")  # -4 rewrote itself
        self.event("m4", 3)
        code = self.read()
        self.assertEqual((code["code"], code["events"], code["of"]), ("a" * 64, 9, 12))
        self.assertEqual(code["codes"], {"a" * 64: 9, "b" * 64: 3})

    def test_no_majority_no_proven_code(self):
        self.born("m1", "a" * 64)
        self.event("m1", 3)
        self.born("m2", "b" * 64)
        self.event("m2", 3)
        self.assertEqual((self.read()["code"], self.read()["of"]), (None, 6))


# ------------------------------------------------------------------------------------------ M4: stocks at $50
class EquityStakes(HouseCaseReal):
    """M4 (C4): a stock or ETF program's real stake at Alpaca is $50, probe or bunt; crypto stays $25, options $80."""

    def stake_of(self, niche, band, *, proven=False):
        a = self.house.spawn("haghani", "alloc-test", IDLE, reason="test", endowment="2.5")
        record = canned("alloc-test", "alpaca", proven=proven, n=12, bound=0.002 if proven else -0.01)
        with patch.object(allocator, "family_record", return_value=record), \
                patch.object(self.house, "niche_of", return_value=self.house.niches[niche]):
            self.house.allocator._families.clear()
            return self.house.allocator.target_stake(a, band, ev(agent=a.id, venue="alpaca"))

    def test_by_asset_class(self):
        self.assertEqual(self.stake_of("alpaca-megacaps", "probe"), D("50"))
        self.assertEqual(self.stake_of("alpaca-index-etfs", "probe"), D("50"))
        self.assertEqual(self.stake_of("alpaca-crypto-majors", "probe"), D("25"))
        self.assertEqual(self.stake_of("alpaca-options", "probe"), D("80"))
        # A proven family's stock bunt is never staked less than an unproven family's stock probe.
        self.assertEqual(self.stake_of("alpaca-megacaps", "bunt", proven=True), D("50"))
        self.assertEqual(self.stake_of("alpaca-crypto-majors", "bunt", proven=True), D("25"))
        # Its position is half the stake, under the gateway's $68.18 Alpaca order cap.
        self.assertEqual(allocator.limits_for(D("50"), "alpaca"), (D("25.00"), D("25.00")))

    def test_an_open_desks_program_by_what_its_needs_name(self):
        niche = self.house.niches["alpaca-open"]
        program = lambda *symbols: SimpleNamespace(venue="alpaca", needs={"symbols": list(symbols)})  # noqa: E731
        self.assertTrue(allocator.equity_program(program("NVDA", "SPY", "BRK.B"), niche))
        self.assertFalse(allocator.equity_program(program("BTC/USD"), niche))
        self.assertFalse(allocator.equity_program(program("NVDA", "ETH/USD"), niche))
        self.assertFalse(allocator.equity_program(program(), niche))
        self.assertFalse(allocator.equity_program(program("NVDA"), self.house.niches["alpaca-crypto-alts"]))
        self.assertFalse(allocator.equity_program(SimpleNamespace(venue="kalshi", needs={}), self.house.niches["kalshi-open"]))

    def test_without_the_key_a_stock_probe_is_the_venues(self):
        with patch.dict(CONSTITUTION["allocator"]["probe_bunt_usd"]):
            del CONSTITUTION["allocator"]["probe_bunt_usd"]["alpaca_equity"]
            self.assertEqual(self.stake_of("alpaca-megacaps", "probe"), D("25"))


# ------------------------------------------------------------------------------------------ M5: re-admission by bound
class ReseatByBound(unittest.TestCase):
    def test_a_record_like_crypto_alts_reversions_does_not_turn(self):
        """+0.0113 over 375 blocks (the family's forward record when it flipped back in at 21:01Z Sept 24): positive
        by its sum, its 80% lower bound below zero."""
        values = [0.004 if i % 2 else -0.004 for i in range(374)] + [0.0113]
        self.assertAlmostEqual(math.fsum(values), 0.0113, places=12)
        self.assertTrue(families.gaining(len(values), math.fsum(values), 6))  # the old rule let it back in
        turned, bound = families.bound_gaining(values, 6, 0.8)
        self.assertFalse(turned)
        self.assertLess(bound, 0)

    def test_the_lines(self):
        self.assertEqual(families.bound_gaining([0.01] * 5, 6, 0.8)[0], False)  # five periods are not a record
        self.assertEqual(families.bound_gaining([0.01] * 6, 6, 0.8), (True, 0.01))
        self.assertFalse(families.bound_gaining([0.03, -0.02, 0.025, -0.015, 0.01, -0.01], 6, 0.8)[0])  # +0.02, noisy
        self.assertEqual(families.bound_gaining([], 6, 0.8), (False, None))


class ReseatByBoundInTheHouse(ForwardBlocks, KalshiHouse):
    """M5 in a House: the record since a probe's demotion is read one observation a block period, and turns on its bound."""

    reseat = None  # the constitution's: "bound_since_demotion"

    def seated(self, name="kay"):
        a = self.agent(name)
        with self.evidence_of({a.id: READY}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 2)
        return a

    def drawdown(self, a):
        with self.evidence_of({a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)}):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(a.id), 1)

    def hourly(self, *rows):
        """Active blocks of the family's dead member, each (its period, its log growth)."""
        ghost = self.ghost("weather-favorites", KALSHI_IDLE)
        for period, growth in rows:
            self.house.ledger.append("eval.block", {"book": "kalshi-shadow", "active": True, "log_growth": growth, "key": period},
                                     agent=ghost.id)

    def status(self, agent):
        return (self.house._state.get("promotion_status") or {}).get(agent.id) or {}

    def test_one_hours_blocks_are_one_observation(self):
        """The 18:47Z Sept 24 hold of crypto-alts-reversion turned at 21:00:53Z on six blocks since, +0.0101: two hours,
        five of them written in the same second. Read a period at a time, it waited until 01:02Z."""
        self.hourly(*[(f"2026-09-24T{h:02d}", 0.05) for h in range(6)])  # +0.30 before: the whole record never loses
        a = self.seated()
        self.drawdown(a)
        b = self.agent("hawk")
        table = {a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36), b.id: READY}
        self.hourly(*[("2026-09-24T20", 0.0017)] * 6)  # six blocks since, all in one hour: +0.0102
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))
        self.assertIn("has a one-sided 80% lower bound above zero over 6 or more block periods (it is +0.0102 over 6 active blocks "
                      "in 1 periods, no bound yet; allocator.family_probe)", self.status(b)["reason"])
        self.hourly(*[(f"2026-09-24T{h}", 0.0012 + 0.0001 * (h % 3)) for h in range(21, 25)])  # 5 periods: not yet
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 1)
        self.hourly(("2026-09-25T01", 0.0013))  # the sixth period, every one of them up: its bound clears zero
        with self.evidence_of(table):
            self.tick()
        self.assertEqual(self.house.evaluator.rung(b.id), 2)

    def test_a_noisy_record_that_sums_up_stays_held(self):
        self.hourly(*[(f"2026-09-23T{h:02d}", 0.05) for h in range(6)])
        a = self.seated()
        self.drawdown(a)
        b = self.agent("hawk")
        table = {a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36), b.id: READY}
        self.hourly(*[(f"2026-09-24T{h:02d}", 0.004 if h % 2 else -0.004) for h in range(20)], ("2026-09-24T20", 0.002))
        with self.evidence_of(table):
            self.tick()
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))  # +0.002 over 21 periods

    def test_the_deploy_judges_every_demotion_again_under_the_new_rule(self):
        """A hold released under the old rule (a positive sum) is folded again from the ledger and holds under the bound."""
        self.hourly(*[(f"2026-09-23T{h:02d}", 0.05) for h in range(6)])
        a = self.seated()
        with patch.dict(CONSTITUTION["allocator"]["family_probe"], {"reseat": "gain_since_demotion"}):
            self.drawdown(a)
            self.hourly(*[("2026-09-24T20", 0.0017)] * 6)
            with self.evidence_of({a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36)}):
                self.tick()
            self.assertNotIn("weather-favorites", self.house.allocator.holds()["families"])  # turned for good
            self.assertEqual(self.house.allocator.holds()["reseat"], "gain_since_demotion")
        b = self.agent("hawk")
        with self.evidence_of({a.id: dict(READY, e=0.9, w_real=0.64, real_drawdown=0.36), b.id: READY}):
            self.tick()
        holds = self.house.allocator.holds()
        self.assertEqual((holds["reseat"], [d["agent"] for d in holds["families"]["weather-favorites"]]), ("bound_since_demotion", [a.id]))
        self.assertEqual((self.house.evaluator.rung(b.id), self.status(b)["stage"]), (1, "family_held"))


    def test_the_holds_keyed_by_mechanism_leave_the_label_holds_for_a_rollback(self):
        """The Deploy B money review (Sept 25, 2026): Deploy A reads `probe_holds` from its own cursor and looks a hold up by
        the family LABEL. Had Deploy B replaced it with holds keyed by mechanism and its cursor at the ledger's head, a
        rollback would never fold the demotions made meanwhile and would seat probes from a family its own R5 holds."""
        left_by_a = {"cursor": 7, "families": {"crypto-alts-reversion": [{"seq": 5, "at": "2026-09-24T18:47:39Z",
                                                                         "agent": "haghani-58", "why": "hysteresis"}]},
                     "states": {}}
        self.house.allocator.state["probe_holds"] = json.loads(json.dumps(left_by_a))
        a = self.seated()
        self.drawdown(a)
        self.tick()
        alloc = self.house.allocator
        self.assertEqual(alloc.holds_key(), "probe_holds_mechanism")
        self.assertEqual([d["agent"] for d in alloc.holds()["families"]["weather-favorites"]], [a.id])
        self.assertEqual(alloc.state["probe_holds"], left_by_a, "Deploy A's holds and cursor as it left them")
        saved = json.loads(alloc.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["probe_holds"], left_by_a)
        self.assertIn(a.id, [d["agent"] for d in saved["probe_holds_mechanism"]["families"]["weather-favorites"]])
        with patch.dict(CONSTITUTION["allocator"], {"family_key": "label"}):
            self.assertEqual(alloc.holds_key(), "probe_holds")  # the label's rule reads the label's holds


# ------------------------------------------------------------------------------------------ M6: the Alpaca maker record
class AlpacaFillRoles(BookCase):
    """M6: an Alpaca fill is booked a maker when its order was a limit that was not marketable at the touch the book saw
    when it placed it; its fee stays the taker's (the venue names neither)."""

    venue, family, real, cash = "alpaca", "alpaca", True, "1000"

    def setUp(self):
        super().setUp()
        self.book.reconcile()
        self.seat("haghani", usd="200", position="100", order="75")
        self.btc = Instrument("crypto", "BTC/USD", self.venue)
        self.broker.set_quote(self.btc, "79998", "80002")

    def fills(self):
        return [e.payload for e in self.ledger.iter(kinds="book.fill", agent="haghani")]

    def test_a_resting_dip_bid_is_a_maker_and_pays_the_takers_fee(self):
        out = self.book.submit([self.intent("haghani", self.btc, "buy", "0.0005", order_type="limit", limit_price="79950")])[0]
        self.assertEqual(out.status, "resting", out.detail)
        self.broker.fill_resting(out.order_id, "0.0005")
        self.book.poll()
        fill = self.fills()[-1]
        self.assertEqual((fill["liquidity_role"], fill["liquidity"]), ("maker", "taker"))
        self.assertEqual(D(fill["fee_quantity"]), D("0.00000125"))  # 0.25% in kind: the fee the book always charged

    def test_a_marketable_limit_and_a_market_order_are_takers(self):
        out = self.book.submit([self.intent("haghani", self.btc, "buy", "0.0005", order_type="limit", limit_price="80002")])[0]
        self.assertEqual(out.status, "filled", out.detail)
        out = self.book.submit([self.intent("haghani", self.btc, "buy", "0.0005")])[0]
        self.assertEqual(out.status, "filled", out.detail)
        self.assertEqual([f["liquidity_role"] for f in self.fills()], ["taker", "taker"])

    def test_the_role_survives_a_restart(self):
        out = self.book.submit([self.intent("haghani", self.btc, "buy", "0.0005", order_type="limit", limit_price="79950")])[0]
        self.book = self.new_book()
        self.book.limits["haghani"] = Limits(D("100"), D("75"))
        self.book.reconcile()
        self.broker.fill_resting(out.order_id, "0.0005")
        self.book.poll()
        self.assertEqual(self.fills()[-1]["liquidity_role"], "maker")

    def test_a_kalshi_fill_says_nothing_new(self):
        ledger = Ledger(Path(self.dir.name) / "kalshi.sqlite", clock=self.clock)
        self.addCleanup(ledger.close)
        from league.tests.fakes import FakeBroker

        broker = FakeBroker("kalshi-shadow", family="kalshi")
        book = Book("kalshi-shadow", broker, ledger, fees=Fees("kalshi"), real_money=False, clock=self.clock)
        book.limits["a"] = Limits(D(100), D(75))
        book.stake("a", "200")
        inst = Instrument("event", "KXHIGHNY-26SEP25-B72.5", "kalshi-shadow", market_id="KXHIGHNY-26SEP25-B72.5", right="yes")
        broker.set_quote(inst, "0.40", "0.42")
        self.assertEqual(book.submit([self.intent("a", inst, "buy", "5")])[0].status, "filled")
        self.assertNotIn("liquidity_role", [e.payload for e in ledger.iter(kinds="book.fill")][-1])


class TheRecordReadsTheRole(AtRiskCase):
    """The family record's maker and taker sides read an Alpaca fill's role where it has one; older rows keep theirs."""

    def test_where_present(self):
        self.member("h1", family="crypto-alts-reversion", venue="alpaca")
        self.stake(200, agent="h1", book="alpaca-paper")
        for i, role in enumerate(("maker", "maker", None)):
            payload = {"book": "alpaca-paper", "source": "venue", "side": "buy", "realized": None, "flat": None,
                       "instrument": self.inst(f"SOL{i}/USD", venue="alpaca-paper"), "quantity": "1", "price": "10",
                       "cash_delta": "-10", "liquidity": "taker"}
            if role:
                payload["liquidity_role"] = role
            self.ledger.append("book.fill", payload, agent="h1")
            self.sell(f"SOL{i}/USD", "0.10", agent="h1", book="alpaca-paper")
        record = self.record("crypto-alts-reversion", "alpaca")
        self.assertEqual((record["maker"]["n"], record["taker"]["n"]), (2, 1))
