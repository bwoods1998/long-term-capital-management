"""Offline regression checks for the frozen critic task and its local grading."""
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest

import research_eval as evaluation


class ResearchEvalTests(unittest.TestCase):
    def setUp(self):
        self.cases = evaluation.load_cases()
        self.by_id = {case['id']: case for case in self.cases}

    def answer(self, case):
        return {'verdict': case['expected']['verdict'],
                'evidence_ids': sorted({group[0] for group in case['expected']['required_evidence_groups']}),
                'reason': 'Local synthetic oracle used only to check the grader.'}

    def test_frozen_suite_has_required_label_balance_and_traps(self):
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(Counter(case['expected']['verdict'] for case in self.cases),
                         {'supported': 6, 'unsupported': 7, 'insufficient': 3})
        self.assertTrue({'scope', 'cash-versus-capex', 'lease-cashflow',
                         'forecast-versus-realized', 'period', 'units',
                         'citation-entailment', 'publication-cutoff', 'missing-evidence'} <=
                        {case['category'] for case in self.cases})

    def test_every_evidence_item_matches_checked_packet(self):
        packet = json.loads((evaluation.ROOT / 'data/thesis/msft-ai-infrastructure.json').read_text())
        sources = {source['id']: source for source in packet['sources']}
        items = {item['id']: item for item in packet['facts'] + packet['context']}
        for case in self.cases:
            for evidence in case['evidence']:
                with self.subTest(case=case['id'], evidence=evidence['id']):
                    item = items[evidence['id']]
                    source = sources[item['source_id']]
                    text = item.get('text') or (
                        f"Microsoft {item['period']} {item['label']}: {item['value']} {item['unit']}.")
                    self.assertEqual(evidence['text'], text)
                    self.assertEqual(evidence['published_at'], source['published_at'])
                    self.assertEqual(evidence['source_url'], source['url'])

    def test_model_input_contains_only_allowed_case_fields_and_no_answers(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                messages = evaluation.build_case_input(case)
                self.assertEqual([message['role'] for message in messages], ['system', 'user'])
                user_data = json.loads(messages[1]['content'])
                self.assertEqual(user_data, {key: case[key] for key in ('claim', 'as_of', 'evidence')})
                poisoned = copy.deepcopy(case)
                poisoned['id'] = 'PRIVATE_CASE_MARKER'
                poisoned['category'] = 'PRIVATE_CATEGORY_MARKER'
                poisoned['expected'] = {'verdict': 'PRIVATE_LABEL', 'rationale': 'PRIVATE_ANSWER',
                                        'required_evidence_groups': [['PRIVATE_EVIDENCE_ANSWER']]}
                self.assertEqual(messages, evaluation.build_case_input(poisoned))
                self.assertNotIn(case['expected']['rationale'], json.dumps(messages))

    def test_local_expected_answers_pass_every_case(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                self.assertTrue(evaluation.grade(self.answer(case), case)['passed'])

    def test_calculation_groups_allow_derived_result_or_both_inputs(self):
        case = self.by_id['supported-cash-proxy']
        answer = self.answer(case)
        for ids in (['cash-after-ppe-2026', 'calculation-scope'],
                    ['ocf-2026', 'ppe-2026', 'calculation-scope']):
            answer['evidence_ids'] = ids
            self.assertTrue(evaluation.grade(answer, case)['passed'])
        answer['evidence_ids'] = ['ocf-2026', 'calculation-scope']
        self.assertFalse(evaluation.grade(answer, case)['expected_evidence_covered'])

    def test_unknown_citation_is_measured_even_when_label_is_correct(self):
        case = self.cases[0]
        answer = self.answer(case)
        answer['evidence_ids'].append('invented-source')
        evaluation.validate_verdict(answer, case)
        result = evaluation.grade(answer, case)
        self.assertTrue(result['label_correct'])
        self.assertFalse(result['citation_membership_correct'])
        self.assertFalse(result['passed'])

    def test_valid_citation_without_required_support_does_not_pass(self):
        case = self.by_id['unsupported-valid-source-without-support']
        answer = self.answer(case)
        answer['evidence_ids'] = ['margin-pressure']
        result = evaluation.grade(answer, case)
        self.assertTrue(result['label_correct'])
        self.assertTrue(result['citation_membership_correct'])
        self.assertTrue(result['citation_cutoff_correct'])
        self.assertFalse(result['expected_evidence_covered'])
        self.assertFalse(result['passed'])

    def test_future_evidence_cannot_be_cited_even_when_abstaining(self):
        case = self.by_id['insufficient-future-evidence']
        answer = self.answer(case)
        self.assertEqual(answer['evidence_ids'], [])
        self.assertTrue(evaluation.grade(answer, case)['passed'])
        answer['evidence_ids'] = ['ocf-2026']
        result = evaluation.grade(answer, case)
        self.assertTrue(result['label_correct'])
        self.assertTrue(result['citation_membership_correct'])
        self.assertFalse(result['citation_cutoff_correct'])
        self.assertFalse(result['passed'])
        answer['verdict'] = 'supported'
        self.assertFalse(evaluation.grade(answer, case)['label_correct'])

    def test_same_day_publication_is_eligible(self):
        case = self.by_id['supported-ocf-units']
        self.assertEqual(case['as_of'], case['evidence'][0]['published_at'])
        self.assertTrue(evaluation.grade(self.answer(case), case)['citation_cutoff_correct'])

    def test_empty_citations_allowed_only_for_insufficient(self):
        for case in self.cases:
            answer = self.answer(case)
            answer['evidence_ids'] = []
            with self.subTest(case=case['id']):
                if answer['verdict'] == 'insufficient':
                    self.assertEqual(evaluation.validate_verdict(answer, case)['evidence_ids'], [])
                    self.assertTrue(evaluation.grade(answer, case)['passed'])
                else:
                    with self.assertRaises(ValueError):
                        evaluation.validate_verdict(answer, case)

    def test_strict_schema_rejects_malformed_outputs(self):
        case = self.cases[0]
        valid = self.answer(case)
        malformed = [None, [], 1, 'not json', {'verdict': 'supported'},
                     {**valid, 'extra': 'hidden'}, {**valid, 'verdict': 'SUPPORTED'},
                     {**valid, 'verdict': ['supported']}, {**valid, 'reason': ''},
                     {**valid, 'reason': '   '}, {**valid, 'reason': 'x' * 601},
                     {**valid, 'reason': 1}, {**valid, 'evidence_ids': 'ocf-2026'},
                     {**valid, 'evidence_ids': [1]}, {**valid, 'evidence_ids': [{}]},
                     {**valid, 'evidence_ids': ['  ']},
                     {**valid, 'evidence_ids': ['ocf-2026', 'ocf-2026']},
                     '{"verdict":"supported","verdict":"insufficient",'
                     '"evidence_ids":[],"reason":"duplicate field"}']
        for output in malformed:
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    evaluation.validate_verdict(output, case)
                result = evaluation.grade(output, case)
                self.assertFalse(result['passed'])
                self.assertFalse(result['format_correct'])
                self.assertIsNone(result['predicted'])
        self.assertEqual(evaluation.validate_verdict(json.dumps(valid), case), valid)

    def test_fixture_validation_rejects_duplicate_ids_and_future_ground_truth(self):
        bad_cases = []
        duplicate = copy.deepcopy(self.cases)
        duplicate[1]['id'] = duplicate[0]['id']
        bad_cases.append(duplicate)
        unknown = copy.deepcopy(self.cases)
        unknown[0]['expected']['required_evidence_groups'] = [['absent']]
        bad_cases.append(unknown)
        future = copy.deepcopy(self.cases)
        future[0]['as_of'] = '2026-07-28'
        bad_cases.append(future)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.json'
            for cases in bad_cases:
                path.write_text(json.dumps(cases))
                with self.assertRaises(ValueError):
                    evaluation.load_cases(path)

    def test_aggregate_confusion_precision_recall_and_invalid_outputs(self):
        results = [evaluation.grade(self.answer(case), case) for case in self.cases]
        perfect = evaluation.aggregate(results)
        self.assertEqual(perfect['passed'], 16)
        self.assertEqual(perfect['pass_rate'], 1)
        self.assertEqual(perfect['abstention_recall'], 1)
        self.assertEqual(perfect['unsupported_recall'], 1)
        for expected_label, prediction in [('supported', 'unsupported'),
                                           ('unsupported', 'insufficient'), ('insufficient', None)]:
            index = next(index for index, case in enumerate(self.cases)
                         if case['expected']['verdict'] == expected_label)
            case = self.cases[index]
            answer = self.answer(case)
            if prediction:
                answer['verdict'] = prediction
            else:
                answer['unexpected'] = True
            results[index] = evaluation.grade(answer, case)
        summary = evaluation.aggregate(results)
        self.assertEqual(summary['passed'], 13)
        self.assertEqual(summary['cases'], 16)
        self.assertEqual(summary['confusion_matrix']['supported']['unsupported'], 1)
        self.assertEqual(summary['confusion_matrix']['insufficient']['invalid'], 1)
        self.assertAlmostEqual(summary['per_class']['supported']['recall'], 5 / 6)
        self.assertAlmostEqual(summary['per_class']['unsupported']['precision'], 6 / 7)
        self.assertAlmostEqual(summary['unsupported_recall'], 6 / 7)
        self.assertAlmostEqual(summary['abstention_recall'], 2 / 3)
        self.assertEqual(evaluation.aggregate([])['pass_rate'], 0)


if __name__ == '__main__':
    unittest.main()
