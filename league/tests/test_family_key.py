"""C8 and C6 of the forward-first run (Sept 25, 2026; docs/goals/LTCM_FORWARD_FIRST.md): a family is its program's
mechanism, and a family's capacity is read at its real size.

C8. A family was the label a birth carried: a research child inherited its parent's family whatever it ran, and an agent
that rewrote itself in place kept it. On the T0 snapshot (04:23Z Sept 25) 343 of 647 births carried a label whose founding
program was another mechanism, and 148 agents had rewritten themselves into another one: meriwether-h2d625d-4 kept the
proven sports-central-run-under's name after it rewrote itself into a KXWNBAGAME favourite maker at 02:37Z, and -2, a CFB
and soccer moneyline file, was born under it. Now the constitution's `allocator.family_key` "mechanism" keys a family by
its program beyond PARAMS (and the venue, series and symbols it trades); the labels born before it are re-keyed once by
`agent.family` rows, and the proven families' records are reproduced to the cent.

C6. A family's capacity row reads the REAL book's fill rate at its stake once it has bid 10 markets there, and reports the
fill curve at 2x and 4x the stake, which the family swing's capacity rule reads too.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league import families
from league.agents import Registry
from league.constitution import CONSTITUTION, money_digest
from league.hypotheses import Foundry
from league.lab import static_literal
from league.ledger import HOUSE, Ledger
from league.tests.fakes import Clock
from league.tests.test_promotion_on_proof import MERIWETHER_BUYS, MERIWETHER_SETTLES, LedgerCase
from league.tests.test_seat_evidence import EvidenceCase

#: The run-unders' shape (meriwether-h2d625d): KXMLBTOTAL central unders, with a knob the House can mutate.
PROGRAM = '''
NEEDS = {"venue": "kalshi", "horizon": "day", "style": "central-run-entertainment-premium", "series": ["KXMLBTOTAL"],
         "max_hours_to_close": 48, "wake_minutes": 30}
PARAMS = {"max_open": 2}

def decide(ctx):
    """Wait for a central under before play."""
    return {"intents": [], "thought": "wait for a central under before play"}
'''
#: Its PARAMS, a docstring and a knob of NEEDS changed: the same mechanism (`parameters.same_logic`'s line).
TUNED = (PROGRAM.replace('PARAMS = {"max_open": 2}', 'PARAMS = {"max_open": 3}')
         .replace('"""Wait for a central under before play."""', '"""Wait longer for a central under."""')
         .replace('"wake_minutes": 30', '"wake_minutes": 60'))
#: A maker entry instead of a taker one: decision code, so another mechanism (the Sept 24 rule kept it in the family).
MAKER = PROGRAM.replace('"thought": "wait for a central under before play"', '"thought": "rest a post-only bid at the bid"')
#: meriwether-h2d625d-2's shape: a moneyline-favourites file on other series.
MONEYLINE = (PROGRAM.replace('"central-run-entertainment-premium"', '"sports-moneyline-deep-favourites"')
             .replace('["KXMLBTOTAL"]', '["KXNCAAFGAME", "KXEPLGAME"]').replace("wait for a central under before play", "buy a deep favourite"))
#: meriwether-h2d625d-4's rewrite of 02:37Z Sept 25: a KXWNBAGAME favourite maker.
WNBA = (PROGRAM.replace('"central-run-entertainment-premium"', '"pregame-wnba-favorite-maker"')
        .replace('["KXMLBTOTAL"]', '["KXWNBAGAME"]').replace("wait for a central under before play", "rest a bid on the favourite"))
#: The same run-under program on another series: its markets differ, so its mechanism does.
OTHER_SERIES = PROGRAM.replace('["KXMLBTOTAL"]', '["KXNFLTOTAL"]')
FAMILY = "sports-central-run-under"


def needs(code):
    return static_literal(code, "NEEDS")


class Keys(unittest.TestCase):
    def test_a_mechanism_is_the_code_beyond_params_with_its_markets(self):
        key = families.mechanism_key(PROGRAM, needs(PROGRAM))
        self.assertEqual(len(key), 16)
        self.assertEqual(families.mechanism_key(TUNED, needs(TUNED)), key, "PARAMS, a docstring and the wake cadence are not the mechanism")
        self.assertNotEqual(families.mechanism_key(MAKER, needs(MAKER)), key, "decision code is")
        self.assertNotEqual(families.mechanism_key(OTHER_SERIES, needs(OTHER_SERIES)), key, "and so are the series it trades")
        held = {**needs(PROGRAM), "series": ["KXMLBTOTAL", "KXNFLTOTAL"]}  # what its desk let it trade, once held (`constrain`)
        self.assertNotEqual(families.mechanism_key(PROGRAM, held), key)
        self.assertIsNone(families.mechanism_key("def decide(:", {}))

    def test_the_constitution_keys_families_by_mechanism(self):
        """C8 is a row of the run's money table: the key moves the money digest the owner's grant pins."""
        import copy

        self.assertEqual(CONSTITUTION["allocator"]["family_key"], "mechanism")
        self.assertEqual(list(CONSTITUTION["allocator"])[-1], "family_key", "appended at the end of the allocator's rules")
        self.assertEqual(families.family_key_rule(), "mechanism")
        without = copy.deepcopy(CONSTITUTION)
        del without["allocator"]["family_key"]
        self.assertEqual(families.family_key_rule(without), "label")
        self.assertNotEqual(money_digest(without), money_digest())

    def test_a_new_mechanisms_name(self):
        self.assertEqual(families.family_name("sports", "moneyline-favourites", "abcdef0123456789"), "sports-moneyline-favourites-abcdef")
        self.assertEqual(families.family_name("sports", "sports-moneyline", "abcdef0123456789"), "sports-moneyline-abcdef")
        long = families.family_name("sports", "central-run-entertainment-premium", "abcdef0123456789", 10)
        self.assertEqual(len(long), 40)
        self.assertTrue(long.endswith("-abcdef0123"))


class Scenario(LedgerCase):
    """A synthetic ledger shaped like the proven sports family of Sept 24-25: the founder's run-unders earned all of its
    record, a House mutation of its PARAMS traded beside it, a moneyline file was born under its name (-2), and a member
    that ran its program rewrote itself into a WNBA favourite maker (-4). `play` writes it; the clean ledger leaves out
    what was never the family's program."""

    def setUp(self):
        super().setUp()
        self.registry = Registry(self.ledger)

    def born(self, registry, name, code, *, family=FAMILY, parent=None, params=None):
        return registry.born(name=name, family=family, code=code, needs=needs(code), params=params or {}, parent=parent,
                             specialty="kalshi-sports")

    def play(self, ledger, registry, *, clean=False):
        """Rows as a Book writes them. `clean`: without the moneyline child and without the rewrite and what followed it."""
        def stake(agent, usd, book="kalshi-shadow"):
            ledger.append("book.stake", {"book": book, "usd": str(usd), "note": "t", "real_money": book == "kalshi"}, agent=agent)

        def trade(agent, ticker, quantity, price, pnl, book="kalshi-shadow"):
            inst = self.inst(ticker, venue=book)
            ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "realized": None, "flat": None, "instrument": inst,
                                        "quantity": str(quantity), "price": str(price), "cash_delta": str(-quantity * float(price)),
                                        "liquidity": "taker"}, agent=agent)
            ledger.append("book.settle", {"book": book, "instrument": inst, "pnl": str(pnl), "cost": "1", "payout": "1",
                                          "quantity": str(quantity), "result": "no"}, agent=agent)

        founder = self.born(registry, "meriwether", PROGRAM)
        stake(founder.id, 200)
        stake(founder.id, 30, book="kalshi")
        for (ticker, quantity, price), (_, pnl) in zip(MERIWETHER_BUYS, MERIWETHER_SETTLES):
            trade(founder.id, ticker, quantity, price, pnl)
        trade(founder.id, "KXMLBTOTAL-26SEP241310TBPHI-8", 10, "0.50", "4.65", book="kalshi")
        trade(founder.id, "KXMLBTOTAL-26SEP241540PITDET-8", 10, "0.52", "-5.20", book="kalshi")
        mutation = self.born(registry, "meriwether", PROGRAM, parent=founder.id, params={"max_open": 3})
        stake(mutation.id, 200)
        trade(mutation.id, "KXMLBTOTAL-26SEP241910TEXMIN-8", 12, "0.45", "6.35")
        misfiled = None
        if not clean:
            misfiled = self.born(registry, "meriwether", MONEYLINE, parent=founder.id)
            stake(misfiled.id, 200)
            trade(misfiled.id, "KXNCAAFGAME-26SEP26ALAAUB-ALA", 10, "0.88", "-8.80")
            trade(misfiled.id, "KXEPLGAME-26SEP27ARSCHE-ARS", 10, "0.81", "1.71")
        rewriter = self.born(registry, "meriwether", PROGRAM, parent=founder.id)
        stake(rewriter.id, 200)
        trade(rewriter.id, "KXMLBTOTAL-26SEP242040AZSD-7", 10, "0.40", "5.65")  # under the family's program: stays in it
        if not clean:
            registry.adopt(rewriter.id, code=WNBA, needs=needs(WNBA), params={}, reason="it rewrote itself: it had no record to protect")
            trade(rewriter.id, "KXWNBAGAME-26SEP25LVAPHX-LVA", 10, "0.70", "-7.00")
            trade(rewriter.id, "KXWNBAGAME-26SEP26NYMIN-NY", 10, "0.66", "3.30")
        return founder, mutation, misfiled, rewriter

    def rekey(self, ledger, registry):
        rows = families.MechanismIndex().refresh(ledger, check_after=0)
        for row in rows:
            ledger.append("agent.family", row["payload"], agent=row["agent"], id=row["id"])
        registry.refresh()
        return rows

    @staticmethod
    def record(ledger, registry, family, venue="kalshi"):
        return families.family_record(SimpleNamespace(ledger=ledger, registry=registry), family, venue, tape=families.TradeTape())

    FIELDS = ("n", "n_eff", "mean_log", "sd", "bound", "honest_bound", "proven", "real_n", "edge_per_dollar", "dollars", "blocks")

    def same(self, a, b):
        for field in self.FIELDS:
            self.assertEqual(a[field], b[field], field)
        for side in ("real", "maker", "taker"):
            for field in ("n", "n_eff", "mean_log", "bound", "honest_bound", "positive"):
                self.assertEqual(a[side][field], b[side][field], f"{side}.{field}")


class ReKey(Scenario):
    def test_the_re_key_reproduces_the_familys_own_program_to_the_cent(self):
        founder, mutation, misfiled, rewriter = self.play(self.ledger, self.registry)
        before = self.record(self.ledger, self.registry, FAMILY)
        # The clean ledger: the same rows less what was never the family's program.
        other = Ledger(Path(self.dir.name) / "clean.sqlite", clock=Clock())
        clean_registry = Registry(other)
        self.play(other, clean_registry, clean=True)
        clean = self.record(other, clean_registry, FAMILY)
        self.assertEqual((before["members"], before["n"]), (4, 10))  # six events of the program, two moneyline, two WNBA
        self.assertEqual((clean["members"], clean["n"]), (3, 6))
        self.assertAlmostEqual(before["dollars"]["practice"] - clean["dollars"]["practice"], -8.80 + 1.71 - 7.00 + 3.30, places=9)
        # The moneyline child's record by itself, read before the re-key: every one of its rows, under a name of its own.
        alone = SimpleNamespace(agents={misfiled.id: SimpleNamespace(id=misfiled.id, family="alone", venue="kalshi", alive=True)})
        expected = self.record(self.ledger, alone, "alone")

        rows = self.rekey(self.ledger, self.registry)
        self.assertEqual([(r["agent"], r["payload"]["was"], r["payload"]["since_seq"]) for r in rows],
                         [(misfiled.id, FAMILY, self.ledger.get(f"born:{misfiled.id}").seq),
                          (rewriter.id, FAMILY, self.ledger.last("agent.strategy", agent=rewriter.id).seq)])
        after = self.record(self.ledger, self.registry, FAMILY)
        self.same(after, clean)
        self.assertEqual(after["dollars"], clean["dollars"])
        self.assertEqual((after["members"], after["members_living"]), (3, 2), "-4 keeps its stretch under the program; -2 has none")
        # Each moved program's record is its own, exactly.
        moneyline = self.registry.get(misfiled.id).family
        self.assertTrue(moneyline.startswith("sports-moneyline-deep-favourites-"), moneyline)
        self.same(self.record(self.ledger, self.registry, moneyline), expected)
        wnba = self.registry.get(rewriter.id).family
        self.assertTrue(wnba.startswith("sports-pregame-wnba-favorite-make-"), wnba)
        moved = self.record(self.ledger, self.registry, wnba)
        self.assertEqual((moved["n"], moved["members"], moved["dollars"]["practice"]), (2, 1, round(-7.00 + 3.30, 6)))
        # Nothing was lost or counted twice.
        total = sum(self.record(self.ledger, self.registry, f)["dollars"]["practice"] for f in (FAMILY, moneyline, wnba))
        self.assertAlmostEqual(total, before["dollars"]["practice"], places=9)
        # The birth rows keep the label they were born with; the lineage stays.
        self.assertEqual(self.ledger.get(f"born:{misfiled.id}").payload["family"], FAMILY)
        self.assertEqual(self.registry.get(misfiled.id).parent, founder.id)
        self.assertEqual(self.registry.get(mutation.id).family, FAMILY, "a House mutation of its PARAMS is the family's program")

    def test_the_re_key_is_once_and_a_second_look_finds_nothing(self):
        self.play(self.ledger, self.registry)
        rows = self.rekey(self.ledger, self.registry)
        self.assertEqual(len(rows), 2)
        self.assertEqual(families.MechanismIndex().refresh(self.ledger, check_after=0),
                         [dict(r) for r in rows], "a full look after the rows are written computes the same rows")
        index = families.MechanismIndex()
        self.assertEqual(index.refresh(self.ledger, check_after=self.ledger.head()[0]), [])
        for row in rows:
            self.assertEqual(index.family(row["agent"]), row["payload"]["family"])

    def test_without_the_re_key_the_family_carries_what_it_never_ran(self):
        """The regression: before C8 the record read the label, so the rewrite's WNBA losses and the moneyline file's trades
        were the run-unders' (on the T0 snapshot they were not, by luck: -2 and -4 had no fill yet)."""
        self.play(self.ledger, self.registry)
        other = Ledger(Path(self.dir.name) / "clean.sqlite", clock=Clock())
        clean_registry = Registry(other)
        self.play(other, clean_registry, clean=True)
        self.assertNotEqual(self.record(self.ledger, self.registry, FAMILY)["n"], self.record(other, clean_registry, FAMILY)["n"])


class Place(Scenario):
    """`MechanismIndex.place`: the family a program is born into."""

    def index(self):
        index = families.MechanismIndex()
        index.refresh(self.ledger, check_after=0)
        return index

    def key(self, code):
        return families.mechanism_key(code, needs(code))

    def test_a_params_only_child_stays_in_its_parents_family_whatever_it_was_labelled(self):
        founder = self.born(self.registry, "meriwether", PROGRAM)
        index = self.index()
        self.assertEqual(index.place(FAMILY, "kalshi", self.key(TUNED), parent=founder.id, desk="sports")[0], FAMILY)
        # An Alpha Lab graduate that nudged its parent's PARAMS carries a lab label of its own: it is the parent's family
        # (five lab families of the T0 snapshot were such nudges).
        self.assertEqual(index.place("sports-lab-123abc", "kalshi", self.key(TUNED), parent=founder.id, desk="sports")[0], FAMILY)

    def test_a_code_changed_child_founds_a_family_and_a_second_one_joins_it(self):
        founder = self.born(self.registry, "meriwether", PROGRAM)
        index = self.index()
        family, why = index.place(FAMILY, "kalshi", self.key(MAKER), parent=founder.id, desk="sports",
                                  style="central-run-entertainment-premium")
        self.assertEqual(family, f"sports-central-run-entertainment-{self.key(MAKER)[:6]}")
        self.assertIn(f"differs from {founder.id}'s program beyond PARAMS", why)
        child = self.born(self.registry, "meriwether", MAKER, family=family, parent=founder.id)
        index.refresh(self.ledger, check_after=0)
        self.assertEqual(index.family(child.id), family)
        again = index.place(FAMILY, "kalshi", self.key(MAKER.replace('"max_open": 2', '"max_open": 4')), parent=founder.id,
                            desk="sports", style="central-run-entertainment-premium")
        self.assertEqual(again[0], family, "a second program with the same mechanism joins the family it founded")
        # A child whose label is not its parent's family founds that label (a graduate with new code).
        self.assertEqual(index.place("sports-lab-123abc", "kalshi", self.key(MONEYLINE), parent=founder.id, desk="sports")[0],
                         "sports-lab-123abc")

    def test_a_founder_founds_its_own_family(self):
        self.born(self.registry, "meriwether", PROGRAM)
        index = self.index()
        self.assertEqual(index.place("weather-new", "kalshi", self.key(MONEYLINE), desk="sports")[0], "weather-new",
                         "a label no program ever carried is the founder's")
        self.assertEqual(index.place(FAMILY, "kalshi", self.key(TUNED), desk="sports")[0], FAMILY,
                         "a founder of the family's own mechanism is its member")
        taken = index.place(FAMILY, "kalshi", self.key(MONEYLINE), desk="sports", style="sports-moneyline-deep-favourites")[0]
        self.assertEqual(taken, f"sports-moneyline-deep-favourites-{self.key(MONEYLINE)[:6]}",
                         "a founder given a label another mechanism holds founds the family of its own mechanism")

    def test_an_unreadable_program_keeps_what_it_was_given(self):
        self.assertEqual(self.index().place(FAMILY, "kalshi", None)[0], FAMILY)


class RekeyedTape(Scenario):
    def test_a_rewrites_stretches_are_the_families_it_ran(self):
        founder, _, misfiled, rewriter = self.play(self.ledger, self.registry)
        self.rekey(self.ledger, self.registry)
        tape = families.TradeTape()
        tape.refresh(self.ledger)
        born = self.ledger.get(f"born:{rewriter.id}").seq
        rewrite = self.ledger.last("agent.strategy", agent=rewriter.id).seq
        wnba = self.registry.get(rewriter.id).family
        self.assertEqual(tape.spans(rewriter.id, FAMILY), [(born, rewrite)])
        self.assertEqual(tape.spans(rewriter.id, wnba), [(rewrite, float("inf"))])
        self.assertEqual(tape.spans(rewriter.id), [(rewrite, float("inf"))], "its current family's")
        self.assertEqual(tape.spans(misfiled.id, FAMILY), [], "a birth re-keyed from its first row leaves the label no stretch")
        self.assertIsNone(tape.spans(founder.id), "an agent that never changed family: all of its rows")
        self.assertEqual(tape.current(rewriter.id), wnba)
        self.assertEqual((tape.family_at(rewriter.id, rewrite - 1), tape.family_at(rewriter.id, rewrite)), (FAMILY, wnba))
        self.assertIsNone(tape.family_at(founder.id, rewrite))
        head = self.ledger.head()[0]
        self.assertEqual(tape.spans(rewriter.id, FAMILY, through=rewrite + 1), [(born, float("inf"))],
                         "read through a position before the re-key's rows, the label held all of it")
        self.assertGreater(head, rewrite)
        self.assertGreaterEqual(tape.born[rewriter.id], rewrite, "joining a family counts as a birth into it for a swing's audit")

    def test_the_registry_folds_the_family_change(self):
        _, _, misfiled, _ = self.play(self.ledger, self.registry)
        self.rekey(self.ledger, self.registry)
        fresh = Registry(self.ledger)  # a restart folds the rows again
        self.assertEqual(fresh.get(misfiled.id).family, self.registry.get(misfiled.id).family)
        self.assertNotEqual(fresh.get(misfiled.id).family, FAMILY)


class Births(EvidenceCase):
    """The House's births under C8 (`House._placed_family`), with a Kalshi practice book (as test_seat_capacity's)."""

    def setUp(self):
        super().setUp()
        self.house.close(wait=None)
        from league.economy import load_game
        from league.house import House, Settings
        from league.sandbox import LocalSandbox
        from league.tests.fakes import FakeBroker

        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.new = lambda: House(Path(self.dir.name) / "house-keys", brokers={"alpaca-paper": self.broker,
                                                                             "kalshi-shadow": FakeBroker("kalshi-shadow", family="kalshi")},
                                 sandbox=LocalSandbox(Path(self.dir.name) / "boxes-keys"), alpaca_data=self.data, clock=self.clock,
                                 settings=Settings(mark_every_seconds=0, research=False), game=game)
        self.house = self.new()

    def parent(self):
        parent = self.house.spawn("meriwether", FAMILY, PROGRAM, reason="the run-unders")
        self.house.evaluator.seat(parent.id, 1, "test")
        self.house.economy.grant(parent.id, "100", "test: a parent that can fork")
        return parent

    def test_a_house_mutation_and_a_params_only_fork_stay_in_the_parents_family(self):
        parent = self.parent()
        mutation = self.house.fork(parent)
        self.assertEqual((mutation.family, mutation.code_sha256), (FAMILY, parent.code_sha256))
        tuned = self.house.fork(parent, code=TUNED, reason="a research candidate that changed its PARAMS", passed_replay=True)
        self.assertEqual(tuned.family, FAMILY)
        self.assertNotIn("born into", self.house.ledger.get(f"born:{tuned.id}").payload["reason"])

    def test_a_code_changed_fork_founds_its_own_family(self):
        parent = self.parent()
        maker = self.house.fork(parent, code=MAKER, reason="a maker fix", passed_replay=True)
        key = families.mechanism_key(MAKER, maker.needs)
        self.assertEqual(maker.family, f"sports-central-run-entertainment-{key[:6]}",
                         "a maker fix is decision code: under C8 a mechanism of its own, with no share of the family's proof")
        born = self.house.ledger.get(f"born:{maker.id}").payload
        self.assertEqual(born["family"], maker.family)
        self.assertIn(f"born into its own family {maker.family}, not {FAMILY}", born["reason"])
        moneyline = self.house.fork(parent, code=MONEYLINE, reason="another research candidate", passed_replay=True)
        self.assertTrue(moneyline.family.startswith("sports-moneyline-deep-favourites-"), moneyline.family)
        self.assertEqual(self.house._candidate_family(parent, {"code": MONEYLINE, "needs": moneyline.needs}, self.house.niche_of(parent)),
                         moneyline.family, "the seat market asks as the family the candidate will be born into")

    def test_a_founder_whose_label_holds_another_mechanism_founds_its_own(self):
        first = self.house.spawn("meriwether", FAMILY, PROGRAM, reason="a founder")
        second = self.house.spawn("meriwether", FAMILY, MONEYLINE, reason="another founder given the same label")
        self.assertEqual(first.family, FAMILY)
        self.assertNotEqual(second.family, FAMILY)
        self.assertTrue(second.family.startswith("sports-moneyline-deep-favourites-"), second.family)

    def test_the_one_time_re_key_at_a_start_and_none_after(self):
        founder = self.house.spawn("meriwether", FAMILY, PROGRAM, reason="the run-unders")
        # Born before C8: the label, whatever the program (written straight to the registry, as the old House did).
        misfiled = self.house.registry.born(name="meriwether", family=FAMILY, code=MONEYLINE, needs=needs(MONEYLINE), params={},
                                            parent=founder.id, specialty="kalshi-sports")
        self.house.close(wait=None)
        self.house = self.new()
        moved = self.house.registry.get(misfiled.id).family
        self.assertTrue(moved.startswith("sports-moneyline-deep-favourites-"), moved)
        rows = list(self.house.ledger.iter(kinds="agent.family"))
        self.assertEqual([(r.agent, r.payload.get("family")) for r in rows[:-1]], [(misfiled.id, moved)])
        marker = rows[-1]
        self.assertEqual((marker.id, marker.agent, marker.payload["rows"]), (families.REKEY_ID, HOUSE, 1))
        self.assertEqual(marker.payload["families"][f"{FAMILY}@kalshi"], {"out": [misfiled.id]})
        self.assertTrue(any("one-time re-key" in (e.payload.get("text") or "") for e in self.house.ledger.iter(kinds="ops.alert")))
        self.house.close(wait=None)
        self.house = self.new()
        self.assertEqual(len(list(self.house.ledger.iter(kinds="agent.family"))), len(rows), "a second start writes nothing")
        self.assertEqual(self.house.registry.get(misfiled.id).family, moved)

    def test_an_in_place_rewrite_moves_the_agent_from_its_rewrite_on(self):
        agent = self.house.spawn("meriwether", FAMILY, PROGRAM, reason="the run-unders")
        self.house.registry.adopt(agent.id, code=WNBA, needs=needs(WNBA), params={}, reason="a rewrite")
        self.house._rekey_rewrite()
        row = self.house.ledger.last("agent.family", agent=agent.id)
        self.assertEqual(row.payload["since_seq"], self.house.ledger.last("agent.strategy", agent=agent.id).seq)
        self.assertEqual(row.payload["was"], FAMILY)
        self.assertEqual(self.house.registry.get(agent.id).family, row.payload["family"])
        self.assertTrue(row.payload["family"].startswith("sports-pregame-wnba-favorite-make-"), row.payload)

    def test_the_label_rule_without_the_key(self):
        """The rollback: without `allocator.family_key` a birth keeps the label it is given (and the Sept 24 rule for a
        research fork's other markets or style), and no start re-keys."""
        with patch.dict(CONSTITUTION["allocator"], {"family_key": "label"}):
            parent = self.parent()
            maker = self.house.fork(parent, code=MAKER, reason="a maker fix", passed_replay=True)
            self.assertEqual(maker.family, FAMILY)
            second = self.house.spawn("meriwether", FAMILY, MONEYLINE, reason="a founder")
            self.assertEqual(second.family, FAMILY)


class MechanismWords(Scenario):
    """`Foundry._mechanism` (league/hypotheses.py) walks up past a child that runs its parent's program: under C8, past
    every child in its parent's family (a research candidate that changed only its PARAMS literal is one)."""

    def words(self, agent):
        foundry = Foundry.__new__(Foundry)
        foundry.house = SimpleNamespace(niches={}, registry=self.registry, ledger=self.ledger)
        foundry.cards = lambda: {}
        return foundry._mechanism(agent)

    def test_a_params_only_research_child_has_its_parents_words(self):
        parent = self.registry.born(name="meriwether", family=FAMILY, code=PROGRAM, needs=needs(PROGRAM), params={},
                                    reason="Recreational bettors overpay for runs: buy the central under before first pitch")
        child = self.registry.born(name="meriwether", family=FAMILY, code=TUNED, needs=needs(TUNED), params={}, parent=parent.id,
                                   reason="tighten the entry band to 0.40-0.55")
        parent_words = "Recreational bettors overpay for runs: buy the central under before first pitch"
        self.assertEqual(self.words(child), (parent_words, f"the birth of {parent.id}"))
        with patch.dict(CONSTITUTION["allocator"], {"family_key": "label"}):
            self.assertEqual(self.words(child)[0], "tighten the entry band to 0.40-0.55", "before C8: any change of code")
        own = self.registry.born(name="meriwether", family="sports-moneyline-deep-favourites-abcdef", code=MONEYLINE,
                                 needs=needs(MONEYLINE), params={}, parent=parent.id, reason="buy deep favourites")
        self.assertEqual(self.words(own)[0], "buy deep favourites")
        self.assertNotEqual(self.words(own)[0], parent_words)


class RealSizeCapacity(LedgerCase):
    """C6: the capacity row reads the real book's fill rate once the family has bid 10 markets there at the stake's size,
    and the fill curve at 1x, 2x and 4x the stake; the swing's capacity rule reads the same rates."""

    def setUp(self):
        super().setUp()
        self.agents = {"m1": SimpleNamespace(id="m1", family="weather-favorites", venue="kalshi", alive=True)}
        self.house = SimpleNamespace(ledger=self.ledger, registry=SimpleNamespace(agents=self.agents))
        self.n = 0

    def bid(self, market, quantity, price, *, book, filled):
        self.n += 1
        order = f"ord-{self.n}"
        inst = {"asset_class": "event", "market_id": market, "symbol": market, "venue": book, "multiplier": "1"}
        self.ledger.append("book.order", {"book": book, "order_id": order, "side": "buy", "status": "new", "limit_price": price,
                                          "quantity": str(quantity), "instrument": inst,
                                          "shares": [{"agent": "m1", "quantity": str(quantity), "intent_id": f"in-{order}"}]})
        if filled:
            self.ledger.append("book.fill", {"book": book, "source": "venue", "side": "buy", "order_id": order, "instrument": inst,
                                             "quantity": str(quantity), "price": price, "cash_delta": str(-quantity * float(price)),
                                             "liquidity": "maker"}, agent="m1")

    def capacity(self):
        self.stake(200, agent="m1")
        self.stake(30, agent="m1", book="kalshi")
        self.buy("KXHIGHNY-26SEP01-B72.5", 10, "0.90", agent="m1")
        self.settle("KXHIGHNY-26SEP01-B72.5", "0.90", agent="m1")  # an edge of 0.10 a dollar at risk
        return families.family_record(self.house, "weather-favorites", "kalshi", tape=families.TradeTape(), now=self.clock() + 2 * 86400,
                                      stake_usd=30)["capacity"]  # a $6 position: 20% of the stake (`position_share_event`)

    def test_the_real_books_rate_counts_from_its_tenth_market(self):
        for i in range(12):  # practice: $6 bids, all filled
            self.bid(f"KXHIGHNY-26SEP{i + 1:02d}-B72.5", 10, "0.60", book="kalshi-shadow", filled=True)
        for i in range(9):  # real: 9 markets at $6, 3 filled
            self.bid(f"KXHIGHMIA-26SEP{i + 1:02d}-B90.5", 10, "0.60", book="kalshi", filled=i < 3)
        cap = self.capacity()
        self.assertEqual((cap["size_usd"], cap["fill_rate_basis"], cap["fill_rates"]["<=$12"]["basis"]), (6.0, "all books", "all"),
                         "nine real markets are not yet a real-money rate (five were, before C6)")
        self.assertAlmostEqual(cap["fill_rate_at_size"], 15 / 21)
        self.bid("KXHIGHMIA-26SEP10-B90.5", 10, "0.60", book="kalshi", filled=False)
        cap = self.capacity()
        self.assertEqual((cap["fill_rate_basis"], cap["fill_rate_at_size"]), ("real", 0.3))

    def test_the_fill_curve_at_one_two_and_four_times_the_stake(self):
        for i in range(10):
            self.bid(f"KXHIGHMIA-26SEP{i + 1:02d}-B90.5", 10, "0.60", book="kalshi", filled=i < 8)   # $6: 8 of 10 real
        for i in range(10):
            self.bid(f"KXHIGHCHI-26SEP{i + 1:02d}-B80.5", 20, "0.60", book="kalshi", filled=i < 2)   # $12: the same bucket
        for i in range(6):
            self.bid(f"KXHIGHAUS-26SEP{i + 1:02d}-B96.5", 30, "0.60", book="kalshi-shadow", filled=i < 3)  # $18: practice only
        cap = self.capacity()
        curve = {pt["multiple"]: pt for pt in cap["curve"]}
        self.assertEqual(sorted(curve), [1, 2, 4])
        self.assertEqual((curve[1]["size_usd"], curve[1]["fill_rate"], curve[1]["basis"]), (6.0, 0.5, "real"))  # 10 of 20 real markets
        self.assertEqual((curve[2]["size_usd"], curve[2]["fill_rate"]), (12.0, 0.5), "$12 is still the <=$12 bucket")
        self.assertEqual((curve[4]["size_usd"], curve[4]["fill_rate"], curve[4]["basis"]), (24.0, 0.5, "all"), "6 practice markets at $12-25")
        per_day, edge = cap["markets_per_day"], cap["edge_per_dollar"]
        self.assertAlmostEqual(curve[4]["usd_per_day"], per_day * 0.5 * edge * 24.0)
        self.assertAlmostEqual(curve[1]["usd_per_day"], cap["usd_per_day"])
        row = families.row_of({**families.empty_record("weather-favorites", "kalshi"), "capacity": cap}, {"state": "unproven"},
                              swing=None, members_real=0, stake_usd=None)
        self.assertEqual([pt["multiple"] for pt in row["capacity"]["curve"]], [1, 2, 4])
        self.assertEqual(row["capacity"]["fill_rate_basis"], "real")
        # The swing's capacity rule reads the same rates: from $12 to $24 a position, 0.5 at $12-25 is not under half of 0.5.
        self.assertFalse(families.capacity_holds(cap["fill_rates"], 12.0, 24.0, ratio=0.5, min_markets=5))
        self.assertTrue(families.capacity_holds(cap["fill_rates"], 12.0, 24.0, ratio=1.01, min_markets=5))

    def test_a_size_never_bid_enough_is_not_assumed_to_fill(self):
        for i in range(10):
            self.bid(f"KXHIGHMIA-26SEP{i + 1:02d}-B90.5", 10, "0.60", book="kalshi", filled=True)
        curve = {pt["multiple"]: pt for pt in self.capacity()["curve"]}
        self.assertEqual((curve[4]["fill_rate"], curve[4]["usd_per_day"], curve[4]["markets_bid"]), (None, None, 0))


if __name__ == "__main__":
    unittest.main()
