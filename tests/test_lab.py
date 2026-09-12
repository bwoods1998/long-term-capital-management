import concurrent.futures
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import lab


class LabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'runs.sqlite'
        self.case = lab.fixture()

    def correct(self):
        return {k: {'value': v, 'currency': 'USD', 'unit': 'millions',
                    'period_end': '2025-06-30', 'evidence': self.case['evidence_rows'][k]}
                for k, v in self.case['expected'].items()}

    def test_grade_rejects_wrong_year_units_and_unrelated_evidence(self):
        answer = self.correct()
        self.assertTrue(all(v['passed'] for v in lab.grade(answer, self.case).values()))
        answer['total_revenue']['period_end'] = '2024-06-30'
        answer['gross_margin']['unit'] = 'percent'
        answer['net_income']['evidence'] = self.case['evidence_rows']['total_revenue']
        self.assertEqual(sum(v['passed'] for v in lab.grade(answer, self.case).values()), 2)
        self.assertFalse(any(v['passed'] for v in lab.grade(None, self.case).values()))

    def test_cost_cached_input_is_not_double_counted(self):
        usage = {'input_tokens': 1000, 'input_tokens_details': {'cached_tokens': 200}, 'output_tokens': 100}
        self.assertEqual(lab.estimate_cost(usage), Decimal('0.000094'))
        usage['input_tokens_details']['cached_tokens'] = 1001
        with self.assertRaises(ValueError): lab.estimate_cost(usage)
        with self.assertRaises(ValueError): lab.estimate_cost({})

    def test_concurrent_reservations_cannot_exceed_budget(self):
        with closing(lab.database(self.path)) as db, db:
            db.execute('INSERT INTO runs(id,created,reserved_cents,request,case_json,prediction,rates,pricing_date) VALUES(?,?,?,?,?,?,?,?)',
                       ('previous', 0, 99, '{}', '{}', '', '{}', '2026-09-07'))
        def attempt(_):
            with closing(lab.database(self.path)) as db, db:
                try:
                    lab.reserve(db, lab.build_request(self.case), self.case, 'test')
                    return True
                except ValueError: return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_uncertain_submission_reuses_same_id_and_body(self):
        with closing(lab.database(self.path)) as db, db:
            rid = lab.reserve(db, lab.build_request(self.case), self.case, 'test')
            with patch.object(lab, 'api', side_effect=RuntimeError('network uncertain')) as api, patch.object(lab, 'report'), patch('builtins.print'):
                lab.execute(db, rid)
                lab.execute(db, rid)
            self.assertEqual(api.call_args_list[0], api.call_args_list[1])
            self.assertEqual(db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 1)
            db.execute('UPDATE runs SET created=0 WHERE id=?', (rid,))
            with patch.object(lab, 'api') as api, patch.object(lab, 'report'), patch('builtins.print'):
                lab.execute(db, rid)
                api.assert_not_called()

    def test_resume_uses_get_and_terminal_incomplete_does_not_resubmit(self):
        with closing(lab.database(self.path)) as db, db:
            rid = lab.reserve(db, lab.build_request(self.case), self.case, 'test')
            db.execute('UPDATE runs SET response_id=? WHERE id=?', ('resp_test', rid))
            result = {'id': 'resp_test', 'status': 'incomplete', 'output': None}
            with patch.object(lab, 'api', return_value=result) as api, patch.object(lab, 'report'):
                lab.execute(db, rid)
                lab.execute(db, rid)
            api.assert_called_once_with('GET', '/v1/responses/resp_test')

    def test_request_does_not_include_reference_answer_structure(self):
        body = lab.build_request(self.case)
        self.assertNotIn('expected', json.dumps(body))
        self.assertLess(len(json.dumps(body).encode()), 8000)
        self.assertEqual(body['max_output_tokens'], 2048)


if __name__ == '__main__': unittest.main()
