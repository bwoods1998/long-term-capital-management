"""Economic-book isolation and the non-blocking arena's regression contracts."""
import tempfile
import dataclasses
import time
from types import SimpleNamespace
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.events import EventLog
from ltcm.ledger import DeskLedger
from ltcm.tests.test_ledger import AAPL
from ltcm.tests.test_service import ServiceCase, DESK, moment_iso
from ltcm.tests.test_foundry import FoundryCase, Provider, reply, NOW
from ltcm.tests.test_committee import CommitteeCase, manifest
from ltcm.tests.test_gateway import GatewayCase
from ltcm.tests.test_mind import MindCase, NOON, spot_payload


class EconomicBooksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = EventLog(Path(self.tmp.name) / 'events.sqlite')
        self.addCleanup(self.log.close)
        self.live = DeskLedger(self.log, 'alpha', mode='live')
        self.shadow = DeskLedger(self.log, 'alpha', mode='shadow')
        self.at = '2026-09-17T00:00:00.000Z'

    def allocate(self, amount, shadow):
        self.log.append('committee', 'committee.allocation', {'allocations': {'alpha': str(amount)}, 'shadow': {'alpha': shadow}}, at=self.at)

    def fill(self, side, price, shadow):
        self.log.append('broker:shadow' if shadow else 'broker:alpaca', 'broker.fill',
                        {'desk_id': 'alpha', 'instrument': AAPL.to_dict(), 'side': side, 'price': str(price), 'quantity': '1', 'fee': '1', 'shadow': shadow}, at=self.at)

    def test_promotion_cannot_import_shadow_profits_or_fees(self):
        self.allocate(1000, True)
        self.fill('buy', 100, True)
        self.fill('sell', 150, True)
        self.allocate(100, False)
        # An old mixed-book mark is observational, not authoritative aggregate equity.
        self.log.append('ledger:alpha', 'ledger.mark', {'equity': '148', 'positions': []}, at=self.at)
        real, paper = self.live.state(self.at), self.shadow.state(self.at)
        self.assertEqual((real.equity, real.fees, real.decisions), (Decimal(100), Decimal(0), 0))
        self.assertEqual(paper.equity - paper.net_deposits, Decimal(48))
        self.fill('buy', 40, False)
        self.fill('sell', 30, False)
        self.assertEqual(self.live.state(self.at).equity - self.live.state(self.at).net_deposits, Decimal(-12))

    def test_demotion_and_repromotion_preserve_real_losses_and_reset_mode_cache(self):
        self.allocate(100, False)
        self.fill('buy', 40, False)
        self.fill('sell', 20, False)
        self.allocate(1000, True)
        self.assertEqual(self.live.state(self.at).equity, Decimal(-22))
        self.assertEqual(self.shadow.state(self.at).equity, Decimal(1000))
        self.live.set_mode('shadow')
        self.assertEqual(self.live.state(self.at).equity, Decimal(1000))
        self.live.set_mode('live')
        self.allocate(200, False)
        self.assertEqual(self.live.state(self.at).equity, Decimal(178))

    def test_indexed_reader_matches_full_tape_and_keeps_late_settlements(self):
        self.allocate(1000, True)
        self.fill('buy', 100, True)
        self.log.append('desk:other', 'desk.thought', {'text': 'not an economic event'}, at=self.at)
        selected = self.log.read_ledger('alpha')
        self.assertEqual([e.kind for e in selected], ['committee.allocation', 'broker.fill'])
        last = selected[-1].seq
        self.fill('sell', 110, True)
        self.assertEqual(len(self.log.read_ledger('alpha', after=last)), 1)
        self.assertEqual(self.shadow.state(self.at).equity, Decimal(1008))


class ArenaServiceTests(ServiceCase):
    def test_marking_deduplicates_quotes_across_desks(self):
        seen = []
        marks = []
        position = SimpleNamespace(instrument=AAPL)
        state = SimpleNamespace(net_deposits=Decimal(100), positions={AAPL.key: position})
        self.service.ledgers = {
            desk: SimpleNamespace(state=lambda at: state,
                                  mark=lambda quotes, at, shadow: marks.append((quotes, shadow)))
            for desk in ('one', 'two')
        }
        self.service.live_ids = lambda: {'one'}
        quote = object()
        self.service.quote = lambda instrument: seen.append(instrument.key) or quote
        self.assertEqual(self.service.mark_all(self.service.now()), 2)
        self.assertEqual(seen, [AAPL.key])
        self.assertEqual(marks, [({AAPL.key: quote}, False), ({AAPL.key: quote}, True)])

    def test_infrastructure_billing_failure_preserves_last_known_total(self):
        policy = {'app_id': 'arena', 'since': '2026-09-15T00:00:00Z', 'cache_seconds': 300}
        self.service.config['sail_cost'] = policy
        self.service._save_state(infra_app_spend={**policy, 'usd': '1.25', 'checked_at': '2026-09-01T00:00:00Z'})
        def failed(**kwargs):
            raise OSError('provider unavailable')
        self.service.sandboxes = SimpleNamespace(client=SimpleNamespace(spend=failed))
        result = self.service._sail_usage()
        self.assertEqual(result['infra_spend_usd'], Decimal('1.25'))
        self.assertTrue(result['stale'])

    def test_event_pump_publishes_without_waiting_for_a_tick(self):
        thread = threading.Thread(target=self.service._stream_events)
        thread.start()
        try:
            for _ in range(100):
                if self.publisher.pushes:
                    break
                self.service._stream_stop.wait(0.01)
            self.assertTrue(self.publisher.pushes)
            self.assertFalse(self.publisher.checkpoints, 'the event path does not build a checkpoint')
        finally:
            self.service._stream_stop.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_reconciliation_success_survives_restart_but_failure_does_not(self):
        class Venue:
            def positions(self):
                return []
        self.service.close()
        self.service = self.build(live_venues=['kalshi'])
        self.service.gateway.brokers['kalshi'] = Venue()
        first = moment_iso(2026, 9, 14, 18)
        self.assertEqual(self.service._reconcile_venues(first), ['kalshi'])
        self.service.close()
        self.service = self.build(live_venues=['kalshi'])
        self.service.gateway.brokers['kalshi'] = Venue()
        self.assertEqual(self.service._reconcile_venues(moment_iso(2026, 9, 14, 18, 10)), [])
        self.assertEqual(self.service._reconcile_venues(moment_iso(2026, 9, 14, 19, 1)), ['kalshi'])

    def test_retired_family_cannot_be_bootstrapped_or_run_again(self):
        runner = self.service.strategies
        manifest = self.service.manifests[DESK]
        self.service.config['strategy_lifecycle'] = {'retired_families': [manifest.family], 'controls': []}
        self.assertFalse(runner.family_enabled(manifest))
        self.assertEqual(runner.due({DESK: manifest}, self.service.now()), [])
        self.assertIsNone(runner._run_guarded(manifest, 'fake', {}, self.service.now()))
        self.service.config['strategy_lifecycle']['controls'] = [DESK]
        self.assertTrue(runner.family_enabled(manifest))


class RepairTests(FoundryCase):
    def test_paused_family_can_research_without_reenabling_live_parent(self):
        self.strategies.store.update('mullins', 'kalshi_favorites', enabled=False)
        foundry = self.foundry(paused_research_families=['kalshi'])
        self.assertEqual(foundry.subjects('kalshi', self.manifests), ['kalshi_favorites'])
        self.assertFalse(self.row('mullins')['enabled'])
        self.assertEqual(self.foundry().subjects('kalshi', self.manifests), [])
        self.assertEqual(self.foundry(paused_research_families=['kalshi'], excluded_families=['kalshi']).subjects('kalshi', self.manifests), [])
        self.strategies.store.update('mullins', 'kalshi_favorites_f99', enabled=True)
        self.assertEqual(foundry.subjects('kalshi', self.manifests), ['kalshi_favorites_f99'])

    def test_a_valid_candidate_starts_testing_before_the_slowest_model_finishes(self):
        gate = threading.Event()
        class Staggered(Provider):
            def respond(self, profile, items, **kwargs):
                if kwargs['request_key'].endswith(':1'):
                    gate.wait(4)
                return super().respond(profile, items, **kwargs)
        provider = Staggered()
        provider.replies = {0: reply('kalshi_favorites_f1'), 1: reply('kalshi_favorites_f1_2')}
        foundry = self.foundry(provider)
        worker = threading.Thread(target=lambda: foundry.cycle(NOW))
        worker.start()
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not any(s['strategy'] == 'kalshi_favorites_f1' for s in self.manager.specs):
                time.sleep(0.01)
            self.assertTrue(any(s['strategy'] == 'kalshi_favorites_f1' for s in self.manager.specs))
            self.assertFalse(gate.is_set())
        finally:
            gate.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())

    def test_invalid_candidate_gets_one_bounded_repair_then_all_original_checks(self):
        class Repairing(Provider):
            def respond(self, profile, items, **kwargs):
                self.replies[0] = reply('kalshi_favorites_f1') if ':repair:' in kwargs['request_key'] else 'broken JSON'
                return super().respond(profile, items, **kwargs)
        provider = Repairing()
        summary = self.foundry(provider, code_candidates=1, repair_invalid_code=True).cycle(NOW)
        self.assertEqual(summary['code']['asked'], 2)
        self.assertEqual(summary['code']['repaired'], 1)
        self.assertEqual(summary['model_cost_usd'], '0.14')
        self.assertTrue(self.log.kinds('lab.progress'))

    def test_repair_cannot_admit_forbidden_code_or_loop_forever(self):
        provider = Provider()
        provider.replies[0] = reply('kalshi_favorites_f1', code='import subprocess\n')
        summary = self.foundry(provider, code_candidates=1, repair_invalid_code=True).cycle(NOW)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(summary['code']['valid'], 0)
        self.assertEqual(len(summary['code']['rejected']), 1)


class AdmissionTests(CommitteeCase):
    def test_a_cluster_sums_losing_legs_and_partial_exits_instead_of_choosing_a_winner(self):
        from ltcm.strategies import _evidence_fields
        from ltcm.evidence import assess
        rows = []
        for n, pnl in enumerate(['0.10', '-0.90']):
            rows.append(SimpleNamespace(stream='desk:mullins', seq=n+1, at='2026-09-16T20:00:00.000Z', payload={
                'instrument': 'event:KXA-DATE-T1:kalshi:yes:KXA-DATE-T1', 'market_id': 'KXA-DATE-T1',
                'entry_price': '0.90', 'quantity': '1', 'pnl': pnl, 'entry_fees': '0.01',
            }))
        fields = _evidence_fields(rows)
        self.assertEqual(fields['independent_settled'], 1)
        self.assertEqual(fields['losses'], 1)
        self.assertLess(fields['returns'][0][1], 0)
        self.assertEqual(assess({'settled': 100, **fields})['n'], 1, 'a claimed raw count cannot inflate admission or sizing')

    def test_many_fills_without_independent_settlements_cannot_earn_real_capital(self):
        self.add(manifest())
        self.allocate_event({'earnings-01': '1000'}, '2026-09-01T00:00:00.000Z')
        for _ in range(30):
            self.fill('earnings-01', 'buy', 1, 100, '2026-09-02T00:00:00.000Z')
            self.fill('earnings-01', 'sell', 1, 101, '2026-09-03T00:00:00.000Z')
        committee = self.committee(require_settled_evidence=True)
        report = committee.gates('earnings-01', '2026-09-17T00:00:00.000Z')
        self.assertTrue(report['checks']['decisions'])
        self.assertTrue(report['checks']['cost_adjusted_return'])
        self.assertFalse(report['checks']['settled_evidence'])
        for index in range(60):
            self.log.append('desk:earnings-01', 'desk.outcome', {
                'instrument': f'event:KXHIGHNY-26SEP16-B{index}:kalshi:yes:KXHIGHNY-26SEP16-B{index}',
                'market_id': f'KXHIGHNY-26SEP16-B{index}', 'entry_price': '0.90', 'quantity': '1',
                'pnl': '0.10', 'entry_fees': '0', 'real_money': False,
            }, at='2026-09-16T20:00:00.000Z')
        report = committee.gates('earnings-01', '2026-09-17T00:00:00.000Z')
        self.assertEqual(report['evidence']['settled_positions'], 1, '60 correlated strikes are one observation')
        self.assertFalse(report['passed'])


class LifecycleGatewayTests(GatewayCase):
    def test_position_entry_read_does_not_mix_shadow_and_live_fills(self):
        self.ledger.set_mode('live')
        instrument = self.intent().instrument
        for shadow, at in ((True, '2026-09-15T10:00:00.000Z'), (False, '2026-09-16T10:00:00.000Z')):
            self.log.append('broker:shadow' if shadow else 'broker:alpaca', 'broker.fill',
                            {'desk_id': self.intent().desk_id, 'instrument': instrument.to_dict(),
                             'side': 'buy', 'quantity': '1', 'price': '100', 'fee': '1', 'shadow': shadow}, at=at)
        opened_at, _ = self.gateway._open_of(self.intent().desk_id, instrument.key)
        self.assertEqual(opened_at, '2026-09-16T10:00:00.000Z')

    def test_retired_family_refuses_entries_but_preserves_risk_checked_exits(self):
        opening = self.gateway.propose(self.intent(), NOW)
        self.assertTrue(opening['approved'])
        self.gateway.entry_allowed = lambda desk_id: False
        denied = self.gateway.propose(self.intent(nonce='retired-entry'), NOW)
        self.assertFalse(denied['approved'])
        self.assertIn('family lifecycle', denied['reasons'][0])
        closing = dataclasses.replace(self.intent(side='sell', nonce='exit'), purpose='exit', exit_of=self.intent().id, exit_reason='desk')
        self.assertTrue(self.gateway.propose(closing, NOW)['approved'])
        self.assertFalse(self.ledger.state(NOW).positions)


class FeedbackWakeTests(MindCase):
    def test_independent_new_evidence_wakes_learning_without_waiting_an_hour(self):
        mind = self.mind(interval_minutes=60, new_outcomes_trigger=4, feedback_min_minutes=5)
        mind.run(NOON, ask=False)
        for n in range(8):
            self.tape.add('hilibrand', spot_payload(opened_at='2026-09-16T10:00:00.000Z'))
        self.assertFalse(mind.due('2026-09-16T12:06:00.000Z'), 'partial exits of one position are not eight new observations')
        for hour in range(11, 14):
            self.tape.add('hilibrand', spot_payload(opened_at=f'2026-09-16T{hour}:00:00.000Z'))
        self.assertFalse(mind.due('2026-09-16T12:04:00.000Z'), 'minimum interval still binds')
        self.assertTrue(mind.due('2026-09-16T12:06:00.000Z'))
