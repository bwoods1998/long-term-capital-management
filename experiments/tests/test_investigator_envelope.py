"""Transport-format recovery must not repair or reinterpret research content."""
import unittest

import investigator as agent


def response(text):
    return {'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': text}]}]}


class EnvelopeTests(unittest.TestCase):
    def parse(self, text, state=None):
        return agent._response_object(response(text), state or {
            'response_policy': agent.RESPONSE_POLICY})

    def test_exact_wrapper_and_plain_object_agree(self):
        original = '{"verdict":"pass","summary":"Source support checked.","issues":[]}'
        for wrapped in (original, '```json\n' + original + '\n```',
                        '```\r\n' + original + '\r\n```'):
            self.assertEqual(self.parse(wrapped), self.parse(original))

    def test_original_protocol_stays_strict(self):
        with self.assertRaises(ValueError):
            agent._response_object(response('```json\n{}\n```'), {})

    def test_no_extra_prose_objects_duplicate_fields_or_nonfinite(self):
        for text in ('Here is the answer:\n```json\n{}\n```', '{} {}',
                     '```json\n{}\n```\nExtra', '[{}]', '{"a":1,"a":2}',
                     '{"nested":{"a":1,"a":2}}', '{"a":NaN}',
                     '```javascript\n{}\n```', '```json\n{\n```'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)

    def test_content_contract_is_still_enforced(self):
        value = self.parse('```json\n{"verdict":"pass","summary":"OK","issues":[]}\n```')
        self.assertEqual(agent.critique(value, {'draft': {'claims': []}}), value)
        value['extra'] = 'unsupported content'
        with self.assertRaises(ValueError):
            agent.critique(value, {'draft': {'claims': []}})

    def test_unknown_policy_does_not_guess(self):
        with self.assertRaises(ValueError):
            self.parse('{}', {'response_policy': 'future-v2'})


if __name__ == '__main__':
    unittest.main()
