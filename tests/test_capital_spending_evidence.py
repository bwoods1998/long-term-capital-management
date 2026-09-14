import hashlib
import json
import unittest
import copy

from portfolio_runtime.evidence import compact_facts
from portfolio_runtime.research import Research, allocation_company_evidence, grade_result
from portfolio_runtime.service import Service

PPE = 'PaymentsToAcquirePropertyPlantAndEquipment'
PRODUCTIVE = 'PaymentsToAcquireProductiveAssets'


def observation(value, start='2026-01-01', end='2026-06-30', filed='2026-08-01'):
    return dict(val=value, start=start, end=end, filed=filed, form='10-Q', accn='0000000001-26-000001')


def source(ppe=(), productive=()):
    return json.dumps({'facts': {'us-gaap': {
        PPE: {'units': {'USD': list(ppe)}},
        PRODUCTIVE: {'units': {'USD': list(productive)}},
        'NetCashProvidedByUsedInOperatingActivities': {'units': {'USD': [observation(200)]}},
        'NetIncomeLoss': {'units': {'USD': [observation(150)]}},
        # Acquisition cash must not silently become organic capital spending.
        'PaymentsToAcquireBusinessesNetOfCashAcquired': {'units': {'USD': [observation(999)]}},
    }}}).encode()


def company(raw):
    return compact_facts(raw, {'symbol': 'TEST', 'cik': '0000000001'},
                         '2026-09-13T19:00:00Z', '2026-09-13')


class CapitalSpendingEvidenceTests(unittest.TestCase):
    def test_explanatory_labels_do_not_create_new_business_evidence(self):
        current = company(source([observation(90)]))
        historical = copy.deepcopy(current)
        for variant in historical['facts']['capital_spending']:
            variant.pop('definition')
        before = copy.deepcopy(current)
        self.assertEqual(Research.source_fingerprint(historical), Research.source_fingerprint(current))
        old = Service.fundamental_fingerprints({'companies': [historical]})
        self.assertEqual(old, Service.fundamental_fingerprints({'companies': [current]}))
        from portfolio_runtime.provider import canonical
        self.assertEqual(old['TEST'], hashlib.sha256(canonical(historical['facts']).encode()).hexdigest())
        self.assertEqual(current, before)
        productive = company(source([observation(90)], [observation(100)]))
        self.assertNotEqual(Research.source_fingerprint(current), Research.source_fingerprint(productive))
        self.assertNotEqual(old, Service.fundamental_fingerprints({'companies': [productive]}))

    def test_current_productive_assets_replace_missing_or_historical_ppe_evidence(self):
        raw = source([observation(5, '2020-01-01', '2020-06-30', '2020-08-01')],
                     [observation(100), observation(1000, filed='2026-09-14')])
        c = company(raw)
        self.assertEqual(c['sha256'], hashlib.sha256(raw).hexdigest())
        facts = {v['tag']: v for v in c['facts']['capital_spending']}
        self.assertEqual(facts[PPE]['observations'][0]['end'], '2020-06-30')
        self.assertEqual(facts[PRODUCTIVE]['observations'][0]['val'], 100)
        self.assertEqual(len(facts[PRODUCTIVE]['observations']), 1)
        self.assertIn('software', facts[PRODUCTIVE]['definition'])
        self.assertNotIn('PaymentsToAcquireBusinessesNetOfCashAcquired', facts)
        self.assertEqual(company(source(productive=[observation(100)]))['facts']['capital_spending'][0]['tag'], PRODUCTIVE)

    def test_overlapping_definitions_survive_allocation_compaction_without_being_added(self):
        c = company(source([observation(90)], [observation(100)]))
        projected = allocation_company_evidence(c)
        facts = {v['tag']: v for v in projected['facts']['capital_spending']}
        self.assertEqual(set(facts), {PPE, PRODUCTIVE})
        self.assertEqual(facts[PPE]['observations'][0]['val'], 90)
        self.assertEqual(facts[PRODUCTIVE]['observations'][0]['val'], 100)
        self.assertNotEqual(facts[PPE]['definition'], facts[PRODUCTIVE]['definition'])
        self.assertTrue(any('do not add' in warning for warning in c['limitations']))
        self.assertEqual(projected['sha256'], c['sha256'])

    def test_frozen_grader_checks_new_tag_exactly_and_rejects_fabricated_combination(self):
        c = company(source([observation(90)], [observation(100)]))
        claims = []
        for metric, tag in [('capital_spending', PRODUCTIVE),
                            ('operating_cash', 'NetCashProvidedByUsedInOperatingActivities'),
                            ('net_income', 'NetIncomeLoss')]:
            variant = next(v for v in c['facts'][metric] if v['tag'] == tag)
            o = variant['observations'][0]
            claims.append(dict(symbol='TEST', metric=metric, tag=tag, start=o['start'],
                               end=o['end'], value=o['val'], unit='USD'))
        result = dict(thesis='Cash productive-asset purchases include software and intangibles.',
                      claims=claims, questions=[], targets=[], confidence='low', abstain_reason=None)
        self.assertTrue(grade_result(result, {'TEST': c})['source_check_passed'])
        claims[0]['value'] = 190
        self.assertIn('source_mismatch', grade_result(result, {'TEST': c})['errors'])
        claims[0].update(tag=PPE, value=90)
        self.assertTrue(grade_result(result, {'TEST': c})['source_check_passed'])


if __name__ == '__main__':
    unittest.main()
