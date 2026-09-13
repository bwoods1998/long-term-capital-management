import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sail_sandbox as s


class SailSandboxTests(unittest.TestCase):
    def test_creation_request_has_explicit_current_isolation_and_small_ceilings(self):
        body = s.create_body('app_synthetic', 'portfolio-proof-synthetic')
        self.assertEqual(body['egress_policy'], {'no_network': True})
        self.assertEqual(body['network_policy'], {'mode': 'no_network'})
        self.assertEqual(body['visibility'], 'private')
        self.assertEqual(body['memory_limit_gib'], 2)
        self.assertEqual(body['state_disk_limit_gib'], 8)
        self.assertFalse(body['ingress_ports'])
        self.assertFalse(body['volume_mounts'])
        maximum = Decimal('.005') + (Decimal('.015') + 2 * Decimal('.008') + 8 * Decimal('.0007')) / 2
        self.assertLess(maximum, s.RESERVE_USD)

    def test_readback_must_confirm_isolation_before_files_are_uploaded(self):
        row = {'egress_policy': {'document': {'no_network': True}}, 'visibility': 'private',
               'memory_mib': 2048, 'vcpu_count': 1, 'state_disk_size_gib': 8, 'volume_mounts': []}
        s.validate_isolation(row)
        legacy = {key: value for key, value in row.items() if key != 'egress_policy'}
        legacy['network_policy'] = {'mode': 'no_network'}
        s.validate_isolation(legacy)
        with self.assertRaises(ValueError):
            s.validate_isolation({**row, 'network_policy': {'mode': 'public'}})
        for key, value in [('egress_policy', {}), ('visibility', 'org'), ('memory_mib', 16384),
                           ('vcpu_count', 8), ('state_disk_size_gib', 32), ('volume_mounts', [{}])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.validate_isolation({**row, key: value})

    def test_nanodollars_are_never_treated_as_cents(self):
        usage = {'estimated_total_cost_usd_nanos': 17000000, 'finalized_cost_usd_nanos': 5000000,
                 'estimated_active_cost_usd_nanos': 12000000}
        self.assertEqual(s.costs(usage), {'estimated_total_cost_usd': '0.017',
                                          'finalized_cost_usd': '0.005',
                                          'estimated_active_cost_usd': '0.012'})
        for bad in [{}, {**usage, 'estimated_total_cost_usd_nanos': -1},
                    {**usage, 'estimated_total_cost_usd_nanos': True}]:
            with self.assertRaises(ValueError):
                s.costs(bad)

    def test_live_rate_ceiling_covers_all_configured_resources_and_creation(self):
        rates = {'vcpu_second_usd_nanos': 4167, 'memory_gib_second_usd_nanos': 2223,
                 'state_disk_gib_second_usd_nanos': 195, 's_creation_usd_nanos': 5000000}
        self.assertEqual(s.maximum_cost(rates), Decimal('0.0233114'))
        self.assertLess(s.maximum_cost(rates), s.RESERVE_USD)
        for bad in [{}, {**rates, 'vcpu_second_usd_nanos': -1},
                    {**rates, 'vcpu_second_usd_nanos': '4167'}]:
            with self.assertRaises(ValueError):
                s.maximum_cost(bad)

    def test_ambiguous_create_cleanup_reconciles_all_pages_and_exact_app_name(self):
        state = {'name': 'portfolio-proof-synthetic', 'app_id': 'app_synthetic',
                 'operations': {'terminate': 'same-termination-key'}}
        first = {'data': [{'sailbox_id': 'sb_other', 'name': 'other', 'app_id': 'app_synthetic'}],
                 'has_more': True}
        second = {'data': [{'sailbox_id': 'sb_match', 'name': state['name'], 'app_id': state['app_id']},
                           {'sailbox_id': 'sb_wrongapp', 'name': state['name'], 'app_id': 'app_other'}],
                  'has_more': False}
        with patch.object(s, 'api', side_effect=[first, second, {}, {'status': 'terminated'}]) as api:
            self.assertEqual(s._cleanup(state), [{'sailbox_id': 'sb_match', 'status': 'terminated'}])
            self.assertIn('offset=1', api.call_args_list[1].args[1])
            self.assertEqual(api.call_args_list[2].args,
                             ('POST', '/v1/sailboxes/sb_match/terminate', {}, 'same-termination-key'))

    def test_upload_allowlist_excludes_brokerage_private_database_and_environment(self):
        for name in s.FILES:
            self.assertNotIn('schwab', name)
            self.assertNotIn('brokerage', name)
            self.assertNotIn('.env', name)
            self.assertNotIn('.data', name)
            self.assertNotIn('sqlite', name)
        self.assertIn('tests/test_research_eval.py', s.FILES)
        self.assertIn('tests/test_investigator.py', s.FILES)


if __name__ == '__main__':
    unittest.main()
