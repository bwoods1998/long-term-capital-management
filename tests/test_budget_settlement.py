"""A settlement releases a checked allowance, never an unknown charge or history."""
import concurrent.futures
from contextlib import closing
from decimal import Decimal, localcontext
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import operations
import portfolio as p


class BudgetSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)
        self.packet = p.load_packet()
        self.model = 'deepseek-ai/DeepSeek-V4-Flash-0731'
        self.body = p.build_task_request(self.model, 'Synthetic accounting check')

    def reserve(self, key='case', db=None):
        return p.reserve_task(db or self.db, self.body, self.packet, key, 'investigate')

    def terminal(self, run, **changes):
        response = {'id': 'resp_' + run.replace('-', ''), 'model': self.model,
                    'status': 'completed', 'output': [],
                    'usage': {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150,
                              'input_tokens_details': {'cached_tokens': 20}}}
        response.update(changes)
        with self.db:
            self.db.execute('UPDATE runs SET response_id=?,response=?,key_fingerprint=? WHERE id=?',
                            (response['id'], p.encoded(response), 'a' * 64, run))
        return response

    def activate(self):
        return p.activate_budget_policy(self.db, 'Synthetic owner')

    def test_explicit_opt_in_does_not_settle_or_change_ceiling_or_original_rows(self):
        run = self.reserve()
        self.terminal(run)
        before = dict(p.get_run(self.db, run))
        ceiling = p.budget_limit(self.db)
        with self.assertRaisesRegex(ValueError, 'activation'):
            p.settle_run(self.db, run)
        self.assertEqual(p.budget_accounting(self.db)['policy'], 'gross-reservations-v1')
        policy = self.activate()
        self.assertEqual(self.activate(), policy)
        self.assertEqual(p.budget_accounting(self.db)['committed_usd'], '0.1')
        receipt = p.settle_run(self.db, run)
        self.assertEqual(p.settle_run(self.db, run), receipt)
        accounting = p.budget_accounting(self.db)
        self.assertEqual(Decimal(accounting['committed_usd']), Decimal('0.0000166'))
        self.assertEqual(accounting['gross_historical_reserved_usd'], '0.1')
        self.assertEqual(accounting['settled_requests'], 1)
        self.assertEqual(dict(p.get_run(self.db, run)), before)
        self.assertEqual(p.budget_limit(self.db), ceiling)
        with self.assertRaises(ValueError):
            p.activate_budget_policy(self.db, 'A different owner')
        with self.assertRaises(ValueError):
            p.activate_budget_policy(self.db, 'Synthetic owner', 'unreviewed-policy')

    def test_unknown_inflight_and_unconfirmed_keep_their_full_allowances(self):
        self.activate()
        changes = [None, {'status': 'in_progress'}, {'usage': None},
                   {'usage': {'input_tokens': 10}}, {'model': None}, {'model': 'another-model'},
                   {'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 40}},
                   {'metadata': {'supercached_input_tokens': '1'}},
                   {'metadata': {'supercached_input_tokens': '0', 'supercache_write_input_tokens': '1'}}]
        for index, change in enumerate(changes):
            with self.subTest(change=change):
                run = self.reserve(str(index))
                if change is not None:
                    self.terminal(run, **change)
                with self.assertRaises((ValueError, TypeError)):
                    p.settle_run(self.db, run)
        accounting = p.budget_accounting(self.db)
        self.assertEqual(accounting['settled_requests'], 0)
        self.assertEqual(Decimal(accounting['committed_usd']), Decimal('0.9'))

    def test_terminal_failures_with_valid_usage_still_cost_money(self):
        self.activate()
        for state in ['completed', 'incomplete', 'failed', 'cancelled']:
            run = self.reserve(state)
            self.terminal(run, status=state)
            p.settle_run(self.db, run)
        accounting = p.budget_accounting(self.db)
        self.assertEqual(accounting['settled_requests'], 4)
        self.assertEqual(Decimal(accounting['committed_usd']), Decimal('0.0000664'))

    def test_alias_and_frozen_prices_survive_changes_to_current_rate_card(self):
        run = self.reserve()
        self.terminal(run, model=p.RESPONSE_MODEL_ALIASES[self.model])
        self.activate()
        with patch.dict(p.TASK_PROFILES[self.model], {'rates': {'input': '900', 'cached': '800', 'output': '900'}}):
            p.settle_run(self.db, run)
            self.assertEqual(Decimal(p.budget_accounting(self.db)['committed_usd']), Decimal('0.0000166'))

    def test_retired_model_can_settle_against_its_exact_frozen_request(self):
        run = self.reserve()
        # Represents a historical request whose model is no longer admitted today.
        historic = {**self.body, 'model': 'zai-org/GLM-5.3'}
        with self.db:
            self.db.execute('UPDATE runs SET request=? WHERE id=?', (p.encoded(historic), run))
        self.terminal(run, model=historic['model'], status='incomplete')
        self.activate()
        p.settle_run(self.db, run)
        self.assertEqual(p.budget_accounting(self.db)['settled_requests'], 1)

    def test_identity_mismatch_duplicate_response_and_missing_binding_never_release(self):
        self.activate()
        for index, field in enumerate(['response_id', 'key_fingerprint', 'packet_sha256']):
            run = self.reserve(str(index))
            self.terminal(run)
            with self.db:
                self.db.execute('UPDATE runs SET ' + field + '=? WHERE id=?', ('wrong', run))
            with self.assertRaises(ValueError):
                p.settle_run(self.db, run)
        first, second = self.reserve('duplicate1'), self.reserve('duplicate2')
        for run in [first, second]:
            self.terminal(run, id='resp_shared')
            if run == second:
                with self.assertRaisesRegex(ValueError, 'shared'):
                    p.settle_run(self.db, first)
                with self.assertRaisesRegex(ValueError, 'shared'):
                    p.settle_run(self.db, second)
        self.assertEqual(p.budget_accounting(self.db)['settled_requests'], 0)

    def test_duplicate_json_keys_and_invalid_prices_are_not_settleable(self):
        self.activate()
        run = self.reserve()
        response = self.terminal(run)
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?',
                            (p.encoded(response)[:-1] + ',"status":"completed"}', run))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            p.settle_run(self.db, run)
        self.terminal(run)
        for rates in [{'input': '-1', 'cached': '0', 'output': '0'},
                      {'input': 'NaN', 'cached': '0', 'output': '0'}, {'input': '1'}]:
            with self.db:
                self.db.execute('UPDATE runs SET rates=? WHERE id=?', (p.encoded(rates), run))
            with self.assertRaisesRegex(ValueError, 'prices'):
                p.settle_run(self.db, run)

    def test_immutable_receipts_and_settled_financial_inputs_allow_no_lowering(self):
        self.activate()
        run = self.reserve()
        self.terminal(run)
        p.settle_run(self.db, run)
        statements = ['UPDATE budget_settlements SET body=\'{}\'', 'DELETE FROM budget_settlements',
                      'UPDATE budget_policies SET body=\'{}\'', 'DELETE FROM budget_policies',
                      'UPDATE runs SET reserved_cents=0', 'UPDATE runs SET rates=\'{}\'',
                      'UPDATE runs SET response=\'{}\'', 'UPDATE runs SET request=\'{}\'', 'DELETE FROM runs']
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                with self.db:
                    self.db.execute(statement)
        with self.db:
            self.db.execute('UPDATE runs SET error=? WHERE id=?', ('Local review note', run))
        self.assertEqual(p.budget_accounting(self.db)['settled_requests'], 1)

    def test_recomputed_receipt_hash_cannot_replace_actual_cost_with_zero(self):
        self.activate()
        run = self.reserve()
        self.terminal(run)
        p.settle_run(self.db, run)
        saved = self.db.execute('SELECT * FROM budget_settlements').fetchone()
        body = json.loads(saved['body'])
        body['facts']['estimated_usd'] = '0'
        with self.db:
            self.db.execute('DROP TRIGGER immutable_budget_settlement_update')
            self.db.execute('UPDATE budget_settlements SET body=?,sha256=?',
                            (p.encoded(body), p.digest({'id': saved['id'], 'created': saved['created'], 'body': body})))
        with self.assertRaisesRegex(ValueError, 'Settlement changed'):
            p.budget_accounting(self.db)
        with self.assertRaises(ValueError):
            self.reserve('blocked')

    def test_receipt_identity_and_timestamp_are_hash_bound(self):
        self.activate()
        with self.db:
            self.db.execute('DROP TRIGGER immutable_budget_policy_update')
            self.db.execute('UPDATE budget_policies SET created=created+1')
        with self.assertRaisesRegex(ValueError, 'hash'):
            p.budget_accounting(self.db)

    def test_known_cost_above_allowance_is_visible_and_stops_admissions(self):
        self.activate()
        run = self.reserve()
        self.terminal(run, usage={'input_tokens': 1_000_000, 'output_tokens': 1_000_000})
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            p.settle_run(self.db, run)
        accounting = p.budget_accounting(self.db)
        self.assertEqual(accounting['settled_requests'], 0)
        self.assertEqual(Decimal(accounting['open_reservations_usd']), Decimal('.1'))
        self.assertEqual(Decimal(accounting['committed_usd']), Decimal('.27'))
        self.assertEqual(accounting['over_reservation_requests'], 1)
        self.assertTrue(accounting['admissions_blocked'])
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            self.reserve('blocked')

    def test_settlement_is_exact_even_when_callers_decimal_context_is_small(self):
        self.activate()
        run = self.reserve()
        self.terminal(run, usage={'input_tokens': 99999, 'output_tokens': 7123})
        with localcontext() as context:
            context.prec = 5
            p.settle_run(self.db, run)
            actual = p.budget_accounting(self.db)
        self.assertEqual(Decimal(actual['committed_usd']), Decimal('0.01028205'))

    def test_new_admissions_share_atomic_effective_ceiling_without_erasing_gross_holds(self):
        p.set_budget_limit(self.db, 20)
        runs = [self.reserve('old1'), self.reserve('old2')]
        for run in runs:
            self.terminal(run)
        self.activate()
        for run in runs:
            p.settle_run(self.db, run)
        def attempt(number):
            with closing(p.database(self.path)) as db:
                try:
                    self.reserve('concurrent:' + str(number), db)
                    return 1
                except ValueError:
                    return 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)
        accounting = p.budget_accounting(self.db)
        self.assertEqual(Decimal(accounting['gross_historical_reserved_usd']), Decimal('.3'))
        self.assertEqual(Decimal(accounting['committed_usd']), Decimal('.1000332'))
        self.assertEqual(p.budget_limit(self.db), 20)

    def test_concurrent_settlement_is_once_and_read_only_summary_preserves_transaction(self):
        self.activate()
        run = self.reserve()
        self.terminal(run)
        def settle(number):
            with closing(p.database(self.path)) as db:
                return p.settle_run(db, run)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            self.assertEqual(len(set(pool.map(settle, range(6)))), 1)
        before = self.path.read_bytes()
        with closing(operations.connect(self.path)) as db:
            db.execute('BEGIN')
            result = p.budget_accounting(db)
            self.assertTrue(db.in_transaction)
            self.assertEqual(db.total_changes, 0)
            db.rollback()
            summary = operations.snapshot(db)
            self.assertEqual(summary['budget'], result)
            self.assertEqual(summary['inference']['reserved_usd'], '0.1')
            self.assertNotIn('Synthetic owner', json.dumps(summary))
            self.assertNotIn(run, json.dumps(summary))
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_requires_separate_explicit_policy_and_retains_existing_ceiling(self):
        run = self.reserve()
        self.terminal(run)
        command = [sys.executable, str(p.ROOT / 'portfolio.py'), '--database', str(self.path)]
        rejected = subprocess.run(command + ['budget', '--activate-policy', p.SETTLED_BUDGET_POLICY,
            '--reviewer', 'Synthetic owner', '--limit-usd', '99'], capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(p.budget_accounting(self.db)['policy'], 'gross-reservations-v1')
        activated = subprocess.run(command + ['budget', '--activate-policy', p.SETTLED_BUDGET_POLICY,
            '--reviewer', 'Synthetic owner'], capture_output=True, text=True)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        self.assertEqual(json.loads(activated.stdout)['local_budget_usd'], '2.00')
        settled = subprocess.run(command + ['settle', run], capture_output=True, text=True)
        self.assertEqual(settled.returncode, 0, settled.stderr)
        self.assertEqual(json.loads(settled.stdout)['accounting']['settled_requests'], 1)


if __name__ == '__main__':
    unittest.main()
