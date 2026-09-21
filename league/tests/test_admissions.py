"""A qualified improvement must survive a full population without duplicate births."""
from unittest.mock import patch

from league.admissions import Admissions
from league.tests.test_house import BUYER, HouseCase


class CandidateAdmissions(HouseCase):
    def candidate(self, agent):
        return {'code': BUYER + '\n# replayed improvement\n', 'params': agent.params,
                'needs': agent.needs, 'purpose': 'a measured improvement', 'passed': True, 'numbers': {}}

    def queued(self, agent, session='candidate-one'):
        return Admissions(self.house.ledger).enqueue(agent.id, self.house._generation(agent.id),
                                                     self.candidate(agent), session)

    def full(self):
        parent = self.seated('parent')
        loser = self.seated('loser')
        rules = self.house.game['economy']
        rules['max_population'] = 2
        rules['newcomer_seconds'] = 600
        self.clock.advance(float(rules['epoch_seconds']) * float(rules['displace_after_epochs']) + 1)
        return parent, loser, rules

    def test_full_population_is_a_durable_wait_with_a_specific_reason(self):
        parent, loser, rules = self.full()
        row = self.queued(parent)
        self.assertIsNone(self.house._admit_candidate(row))
        restored = Admissions(self.house.ledger).pending()
        self.assertEqual(len(restored), 1)
        self.assertIn('population is full', restored[0]['reason'])
        self.assertEqual(restored[0]['_candidate'], self.candidate(parent))
        count = self.house.ledger.count(kinds='agent.research')
        self.house._admit_candidate(restored[0])
        self.assertEqual(self.house.ledger.count(kinds='agent.research'), count)
        self.assertTrue(loser.alive)

    def test_replayed_candidate_precedes_mutation_and_is_admitted_once(self):
        parent, loser, rules = self.full()
        row = self.queued(parent)
        self.house._admit_candidate(row)
        with patch.object(self.house, '_mutated_params', side_effect=AssertionError('candidate has priority')):
            child = self.house._refill(rules)
        self.assertIsNotNone(child)
        self.assertFalse(loser.alive)
        self.assertTrue(parent.alive)
        self.assertEqual(child.parent, parent.id)
        self.assertEqual(child.code, self.candidate(parent)['code'])
        self.assertEqual(self.house.evaluator.rung(child.id), 1)
        self.assertEqual(len(self.house.registry.living()), 2)
        self.assertEqual(Admissions(self.house.ledger).pending(), [])
        self.assertIsNone(self.house._refill(rules))
        self.assertEqual(len(self.house.registry.agents), 3)

    def test_invalid_replacement_never_retires_a_resident(self):
        parent, loser, rules = self.full()
        row = self.queued(parent)
        with patch.object(self.house.sandbox, 'needs', side_effect=RuntimeError('probe unavailable')):
            self.assertIsNone(self.house._admit_candidate(row, displace=True))
        self.assertTrue(loser.alive)
        self.assertEqual(len(self.house.registry.living()), 2)
        self.assertIn('validation unavailable', Admissions(self.house.ledger).pending()[0]['reason'])

    def test_real_money_and_new_paper_seats_are_not_displaced(self):
        parent, loser, rules = self.full()
        self.house.evaluator.seat(loser.id, 2, 'qualified live incumbent')
        row = self.queued(parent)
        self.assertIsNone(self.house._admit_candidate(row, displace=True))
        self.assertTrue(loser.alive)
        self.house.evaluator.seat(loser.id, 1, 'fresh paper observation')
        self.assertIsNone(self.house._admit_candidate(row, displace=True))
        self.assertTrue(loser.alive)

    def test_changed_parent_cancels_the_wait_but_keeps_its_evidence(self):
        parent = self.seated()
        row = self.queued(parent)
        self.house.registry.adopt(parent.id, code=BUYER + '\n# different parent\n',
                                  needs=parent.needs, params=parent.params, reason='changed')
        self.assertIsNone(self.house._admit_candidate(row))
        saved = Admissions(self.house.ledger).rows()[0]
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['_candidate'], self.candidate(parent))

    def test_restart_during_lifecycle_write_does_not_duplicate_a_child(self):
        parent = self.seated()
        row = self.queued(parent)
        Admissions(self.house.ledger).record(row, 'admitting', 'started')
        restored = Admissions(self.house.ledger).pending()[0]
        with patch.object(self.house, 'fork', side_effect=AssertionError('uncertain birth must not repeat')):
            self.house._admit_candidate(restored)
        self.assertEqual(Admissions(self.house.ledger).rows()[0]['status'], 'unconfirmed')
        self.assertEqual(Admissions(self.house.ledger).pending(), [])

    def test_old_deferred_receipt_is_recovered_using_its_saved_session(self):
        parent = self.seated()
        job = self.house.research_jobs.enqueue(parent.id, self.house._generation(parent.id))
        self.house.research_jobs.finish(job['session'])
        self.house.ledger.append('agent.research', {'tool': 'candidate', 'status': 'deferred',
            'session': job['session'], 'reason': 'a child was not admitted', '_candidate': self.candidate(parent)}, agent=parent.id)
        child = self.house._admit_candidate(Admissions(self.house.ledger).pending()[0])
        self.assertIsNotNone(child)
        self.assertEqual(child.parent, parent.id)
        self.assertEqual(Admissions(self.house.ledger).pending(), [])

    def test_failed_candidate_cannot_take_a_paper_seat(self):
        parent, loser, rules = self.full()
        row = self.queued(parent)
        row['_candidate']['passed'] = False
        self.assertIsNone(self.house._admit_candidate(row, displace=True))
        self.assertTrue(loser.alive)
        self.assertEqual(len(self.house.registry.agents), 2)

    def test_a_full_niche_cannot_displace_an_unrelated_niche(self):
        parent = self.seated('parent')
        other = self.seated('other', BUYER.replace('"BTC/USD"', '"AVAX/USD"'))
        niche = self.house.niche_of(parent)
        self.assertNotEqual(other.specialty, parent.specialty)
        niche.max_members = 1
        rules = self.house.game['economy']
        self.clock.advance(float(rules['epoch_seconds']) * float(rules['displace_after_epochs']) + 1)
        row = self.queued(parent)
        self.assertIsNone(self.house._admit_candidate(row, displace=True))
        self.assertTrue(other.alive)
        self.assertIn('niche is full', row['reason'])

    def test_context_uses_recorded_passes_even_if_the_peer_was_retired(self):
        parent = self.seated('parent')
        peer = self.seated('peer')
        self.house.ledger.append('eval.trial', {'passed': True, 'trades': 38, 'blocks': 50,
            'deflated_sharpe': 0.89, 'experiment': {'manifest': 'recorded-evidence'}}, agent=peer.id)
        self.house.registry.died(peer.id, 'displaced')
        standing = self.house._research_standing(parent)
        self.assertEqual(standing['peer_replay_passes'][0]['agent'], peer.id)
        self.assertEqual(standing['peer_replay_passes'][0]['experiment']['manifest'], 'recorded-evidence')
        self.assertNotIn('_code', standing['peer_replay_passes'][0])
        self.assertIsNone(standing['qualification_policy']['hard_trial_limit'])
        self.assertEqual(standing['qualification_policy']['paper']['gate'], 'screen')
